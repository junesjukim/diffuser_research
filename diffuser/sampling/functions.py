import torch

from diffuser.models.helpers import (
    extract,
    apply_conditioning,
)
from diffuser.models.diffusion import FLOWMATCHING_MODE

@torch.no_grad()
def n_step_guided_p_sample(
    model, x, cond, t, guide, scale=0.001, t_stopgrad=0, n_guide_steps=1, scale_grad_by_std=True,
):
    """
    통합된 가이드 샘플링 함수 (diffusion 및 flowmatching 모두 지원)
    
    인자:
      model: diffusion 또는 flowmatching 방식의 모델
      x: 현재 샘플 텐서
      cond: 조건 정보
      t: 현재 timestep (각 배치마다 동일 혹은 다르게)
      guide: gradient 정보를 제공하는 객체 (guide.gradients 메서드가 있어야 함)
      scale: gradient 업데이트 스케일 (기본값: 0.001)
      t_stopgrad: t 미만에서는 가이드 gradient를 무시 (기본값: 0)
      n_guide_steps: 가이드 업데이트를 몇 번 수행할지 (기본값: 1)
      scale_grad_by_std: posterior variance로 스케일링 여부 (기본값: True)
    """
    
    if not FLOWMATCHING_MODE:
        # Diffusion 방식
        model_log_variance = extract(model.posterior_log_variance_clipped, t, x.shape)
        model_std = torch.exp(0.5 * model_log_variance)
        model_var = torch.exp(model_log_variance)
    
    for _ in range(n_guide_steps):
        with torch.enable_grad():
            y, grad = guide.gradients(x, cond, t)
        
        if scale_grad_by_std and not FLOWMATCHING_MODE:
            # diffusion에서만 variance로 스케일링
            grad = model_var * grad
        
        # t < t_stopgrad 인 경우 gradient 업데이트를 중단
        grad[t < t_stopgrad] = 0
        
        x = x + scale * grad
        x = apply_conditioning(x, cond, model.action_dim)
    
    if FLOWMATCHING_MODE:
        # Flowmatching: 직접 결정론적 업데이트 반환
        x_updated = model.p_mean_variance(x=x, cond=cond, t=t)
        return x_updated, y
    else:
        # Diffusion: 평균과 표준편차로 노이즈 추가
        model_mean, _, model_log_variance = model.p_mean_variance(x=x, cond=cond, t=t)
        
        # no noise when t == 0
        noise = torch.randn_like(x)
        noise[t == 0] = 0
        
        return model_mean + model_std * noise, y
