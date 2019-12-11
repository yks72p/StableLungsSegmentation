from typing import Optional

import torch
import torch.nn as nn


# inspired with kornia.losses

class NegDiceLoss(nn.Module):
    def __init__(self) -> None:
        super(NegDiceLoss, self).__init__()
        self.eps: float = 1e-6

    def forward(  # type: ignore
            self,
            input: torch.Tensor,
            target: torch.Tensor) -> torch.Tensor:
        if not torch.is_tensor(input):
            raise TypeError("Input type is not a torch.Tensor. Got {}"
                            .format(type(input)))
        if not len(input.shape) == 4:
            raise ValueError("Invalid input shape, we expect BxCxHxW. Got: {}"
                             .format(input.shape))
        if not input.shape[-2:] == target.shape[-2:]:
            raise ValueError("input and target shapes must be the same. Got: {}"
                             .format(input.shape, input.shape))
        if not input.device == target.device:
            raise ValueError(
                "input and target must be in the same device. Got: {}".format(
                    input.device, target.device))

        dims = (1, 2, 3)
        intersection = torch.sum(input * target, dims)
        cardinality = torch.sum(input + target, dims)

        dice_score = 2. * intersection / (cardinality + self.eps)
        neg_mean = -torch.mean(dice_score)
        return neg_mean


class FocalLoss(nn.Module):
    def __init__(self, alpha: float, gamma: Optional[float] = 2.0,
                 reduction: Optional[str] = 'none') -> None:
        """
        :param alpha (float): Weighting factor in [0, 1].
        :param gamma (float): Focusing parameter. gamma >= 0.
        """
        super(FocalLoss, self).__init__()
        self.alpha: float = alpha
        self.gamma: torch.Tensor = torch.tensor(gamma)
        self.reduction: Optional[str] = reduction
        self.eps: float = 1e-6

    def forward(  # type: ignore
            self,
            input: torch.Tensor,
            target: torch.Tensor) -> torch.Tensor:
        if not torch.is_tensor(input):
            raise TypeError("Input type is not a torch.Tensor. Got {}"
                            .format(type(input)))
        if not len(input.shape) == 4:
            raise ValueError("Invalid input shape, we expect BxNxHxW. Got: {}"
                             .format(input.shape))
        if not input.shape[-2:] == target.shape[-2:]:
            raise ValueError("input and target shapes must be the same. Got: {}"
                             .format(input.shape, input.shape))
        if not input.device == target.device:
            raise ValueError(
                "input and target must be in the same device. Got: {}".format(
                    input.device, target.device))

        one = torch.tensor(1.)
        lhs = target * input
        rhs = (one - target) * (one - input)
        preds_t = lhs + rhs
        # todo: add clipping with EPS if unstable
        gamma_device = self.gamma.to(input.device)
        weight = torch.pow(one - preds_t, gamma_device)
        focal = -self.alpha * weight * torch.log(preds_t)
        loss_tmp = torch.sum(focal, dim=(1, 2, 3))

        if self.reduction == 'none':
            loss = loss_tmp
        elif self.reduction == 'mean':
            loss = torch.mean(loss_tmp)
        elif self.reduction == 'sum':
            loss = torch.sum(loss_tmp)
        else:
            raise NotImplementedError("Invalid reduction mode: {}"
                                      .format(self.reduction))
        return loss
