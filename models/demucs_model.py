import torch
import torchaudio
from pathlib import Path

from config import Config
from gpu_manager import GPUManager


class DemucsModelWrapper:
    def __init__(self, config: Config):
        self.config = config
        self.model = None

    def load(self) -> None:
        GPUManager.acquire("separate")
        from demucs import pretrained
        self.model = pretrained.get_model(self.config.DEMUCS_MODEL)
        self.model.eval()
        self.model.to(GPUManager.get_device())
        GPUManager.set_model(self.model)

    def separate(self, audio_path: Path) -> dict:
        """Separate vocals and background. Returns {vocals: tensor, background: tensor, sr: int}."""
        waveform, sr = torchaudio.load(str(audio_path))
        if waveform.shape[0] == 1:
            waveform = waveform.repeat(2, 1)

        device = GPUManager.get_device()
        mix = waveform.unsqueeze(0).to(device)

        from demucs.apply import apply_model
        with torch.no_grad():
            sources = apply_model(
                self.model, mix,
                shifts=self.config.DEMUCS_SHIFTS,
                split=True,
                overlap=self.config.DEMUCS_OVERLAP,
                progress=False,
                device=device,
            )

        vocals_idx = self.model.sources.index("vocals")
        vocals = sources[0, vocals_idx].cpu()
        background = sum(sources[0, i].cpu() for i in range(len(self.model.sources)) if i != vocals_idx)

        return {"vocals": vocals, "background": background, "sr": sr}

    def unload(self) -> None:
        del self.model
        self.model = None
        GPUManager.release("separate")