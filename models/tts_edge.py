import asyncio
import subprocess
from pathlib import Path

from config import Config


class EdgeTTSWrapper:
    def __init__(self, config: Config):
        self.config = config
        self.voice = config.EDGE_TTS_VOICE
        self.rate = config.EDGE_TTS_RATE

    async def _synthesize(self, text: str, output_path: str) -> str:
        import edge_tts
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
        # Edge TTS outputs MP3; save to temp then convert to WAV
        tmp_path = output_path.rsplit(".", 1)[0] + "_tmp.mp3"
        await communicate.save(tmp_path)
        subprocess.run([
            "ffmpeg", "-y", "-i", tmp_path,
            "-ar", "44100", "-ac", "1", "-acodec", "pcm_s16le",
            output_path,
        ], capture_output=True, check=True)
        # Clean up temp MP3
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass
        return output_path

    def synthesize(self, text: str, output_path: str) -> str:
        """Synchronous wrapper for Edge TTS synthesis."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(self._synthesize(text, output_path))
        else:
            return asyncio.run(self._synthesize(text, output_path))

    def set_voice(self, voice: str) -> None:
        self.voice = voice

    def set_rate(self, rate: str) -> None:
        self.rate = rate

    def unload(self) -> None:
        pass