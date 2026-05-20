import os
os.environ["COQUI_TOS_AGREED"] = "1"

from pathlib import Path

import torch
import torchaudio

from config import Config
from gpu_manager import GPUManager


class XTTSModelWrapper:
    def __init__(self, config: Config):
        self.config = config
        self.tts = None
        self.gpt_cond_latent = None
        self.speaker_embedding = None

    def load(self, reference_audio: str | None = None) -> None:
        GPUManager.acquire("synthesize")
        from TTS.api import TTS
        device = GPUManager.get_device()
        self.tts = TTS(self.config.XTTS_MODEL).to(device)
        GPUManager.set_model(self.tts)

        if reference_audio and Path(reference_audio).exists():
            self._compute_speaker_latents(reference_audio)

    def _compute_speaker_latents(self, audio_path: str) -> None:
        try:
            from TTS.tts.configs.xtts_config import XttsConfig
            from TTS.tts.models.xtts import Xtts

            # Access the underlying model for latent computation
            if hasattr(self.tts, 'synthesizer') and hasattr(self.tts.synthesizer, 'tts_model'):
                model = self.tts.synthesizer.tts_model
                self.gpt_cond_latent, self.speaker_embedding = model.get_conditioning_latents(
                    audio_path=[audio_path]
                )
        except Exception:
            # Fall back to per-call speaker_wav
            self.gpt_cond_latent = None
            self.speaker_embedding = None

    def synthesize(self, text: str, output_path: str, speaker_wav: str | None = None) -> str:
        kwargs = {
            "text": text,
            "language": self.config.XTTS_LANGUAGE,
            "file_path": output_path,
        }
        if speaker_wav and Path(speaker_wav).exists():
            kwargs["speaker_wav"] = speaker_wav

        self.tts.tts_to_file(**kwargs)
        return output_path

    def synthesize_with_latents(self, text: str, output_path: str) -> str:
        """Synthesize using pre-computed latents for faster inference."""
        if self.gpt_cond_latent is not None and self.speaker_embedding is not None:
            try:
                if hasattr(self.tts, 'synthesizer') and hasattr(self.tts.synthesizer, 'tts_model'):
                    model = self.tts.synthesizer.tts_model
                    out = model.inference(
                        text, self.config.XTTS_LANGUAGE,
                        self.gpt_cond_latent, self.speaker_embedding,
                        temperature=self.config.XTTS_TEMPERATURE,
                        repetition_penalty=self.config.XTTS_REPETITION_PENALTY,
                    )
                    wav = torch.as_tensor(out["wav"]).unsqueeze(0)
                    torchaudio.save(output_path, wav, 24000)
                    return output_path
            except Exception:
                pass

        # Fall back to simple API
        return self.synthesize(text, output_path)

    def unload(self) -> None:
        self.gpt_cond_latent = None
        self.speaker_embedding = None
        del self.tts
        self.tts = None
        GPUManager.release("synthesize")