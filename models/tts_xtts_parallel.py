import os
os.environ["COQUI_TOS_AGREED"] = "1"
from pathlib import Path
import torch
import torchaudio
from concurrent.futures import ThreadPoolExecutor
from config import Config


class XTTSParallelWrapper:
    def __init__(self, config: Config, num_instances: int = 4):
        self.config = config
        self.num_instances = num_instances
        self.models = []
        self.latents = []

    def load(self, reference_audio: str | None = None) -> None:
        from TTS.api import TTS
        print(f"[XTTS] Carregando {self.num_instances} instancias na VRAM...")
        for i in range(self.num_instances):
            tts = TTS(self.config.XTTS_MODEL).to("cuda")
            gpt_cond_latent = None
            speaker_embedding = None
            if reference_audio and Path(reference_audio).exists():
                try:
                    model = tts.synthesizer.tts_model
                    gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
                        audio_path=[reference_audio]
                    )
                except Exception as e:
                    print(f"[XTTS] instancia {i} latent error: {e}")
            self.models.append(tts)
            self.latents.append((gpt_cond_latent, speaker_embedding))
            print(f"[XTTS] instancia {i+1}/{self.num_instances} ok")

    def _synth_one(self, args):
        idx, text, output_path = args
        model_idx = idx % self.num_instances
        tts = self.models[model_idx]
        gpt_cond_latent, speaker_embedding = self.latents[model_idx]
        if gpt_cond_latent is not None:
            try:
                model = tts.synthesizer.tts_model
                out = model.inference(
                    text, self.config.XTTS_LANGUAGE,
                    gpt_cond_latent, speaker_embedding,
                    temperature=self.config.XTTS_TEMPERATURE,
                    repetition_penalty=self.config.XTTS_REPETITION_PENALTY,
                )
                wav = torch.as_tensor(out["wav"]).unsqueeze(0)
                torchaudio.save(output_path, wav, 24000)
                return output_path
            except Exception as e:
                print(f"[XTTS] cue {idx} error: {e}")
        tts.tts_to_file(text=text, language=self.config.XTTS_LANGUAGE, file_path=output_path)
        return output_path

    def synthesize_batch(self, cues, segments_dir) -> list:
        args = [
            (i, cue.text.strip(), str(segments_dir / f"{cue.index:03d}.wav"))
            for i, cue in enumerate(cues) if cue.text.strip()
        ]
        with ThreadPoolExecutor(max_workers=self.num_instances) as ex:
            results = list(ex.map(self._synth_one, args))
        return results

    def unload(self):
        self.models = []
        self.latents = []
        torch.cuda.empty_cache()
