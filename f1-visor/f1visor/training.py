"""EfficientNet architecture and evaluation shared by train/export."""
import math
import torch
from torch import nn


def build_model(pretrained=False):
    from torchvision.models import efficientnet_b0, EfficientNet_B0_Weights
    backbone = efficientnet_b0(weights=EfficientNet_B0_Weights.DEFAULT if pretrained else None)
    return nn.Sequential(backbone.features, nn.Sequential(
        nn.AdaptiveAvgPool2d((1, 1)), nn.Flatten(), nn.Dropout(0.5),
        nn.Linear(backbone.classifier[1].in_features, 2)))


def choose_threshold(labels, probabilities, target_recall):
    if not 0 < target_recall <= 1:
        raise ValueError("target_recall must be in (0, 1]")
    if len(labels) != len(probabilities) or set(labels) != {0, 1}:
        raise ValueError("Threshold selection requires both classes and paired predictions")
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities):
        raise ValueError("Invalid validation probabilities")
    positive = sorted(p for y, p in zip(labels, probabilities) if y == 1)
    return positive[len(positive) - math.ceil(target_recall * len(positive))]


def metrics(labels, probabilities, threshold):
    matrix = [[0, 0], [0, 0]]
    for label, probability in zip(labels, probabilities):
        matrix[label][int(probability >= threshold)] += 1
    tn, fp = matrix[0]
    fn, tp = matrix[1]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {"confusion_matrix": matrix, "accuracy": (tp + tn) / len(labels),
            "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            "samples": len(labels), "threshold": threshold}


@torch.inference_mode()
def evaluate(model, loader, criterion, device):
    model.eval()
    loss_sum, labels, probabilities = 0.0, [], []
    for x, y in loader:
        x, y = x.to(device), y.to(device)
        logits = model(x)
        loss = criterion(logits, y)
        if not torch.isfinite(loss):
            raise ValueError("Non-finite evaluation loss")
        loss_sum += loss.item() * len(y)
        labels.extend(y.cpu().tolist())
        probabilities.extend(torch.softmax(logits, 1)[:, 1].cpu().tolist())
    return loss_sum / len(labels), labels, probabilities
