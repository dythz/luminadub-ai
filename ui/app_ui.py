import gradio as gr

from config import Config
from ui.callbacks import on_start_processing, toggle_subtitles


def build_app(config: Config) -> gr.Blocks:
    """Build the full Gradio application."""

    with gr.Blocks(title="AI Dubbing - English to Portuguese") as app:

        gr.Markdown("# AI Dubbing - English to Portuguese")
        gr.Markdown("Upload a video and get an AI-dubbed version in Portuguese with precise SRT timing.")

        # --- State ---
        project_state = gr.State(value=None)

        # --- Input Section ---
        with gr.Row():
            video_input = gr.Video(label="Upload Video", scale=3)
            with gr.Column(scale=1):
                start_btn = gr.Button("Start Dubbing", variant="primary", size="lg")
                status_text = gr.Textbox(label="Status", value="Ready", interactive=False)

        # --- Progress Dashboard ---
        gr.Markdown("### Pipeline Progress")
        stage_components = {}
        for stage_name in config.STAGE_ORDER:
            display_name = config.STAGE_NAMES.get(stage_name, stage_name)
            with gr.Row():
                icon = gr.Textbox(value="\u25cb", show_label=False, interactive=False, scale=0, min_width=30)
                label = gr.Textbox(value=display_name, show_label=False, interactive=False, scale=1, min_width=150)
                pbar = gr.Slider(0, 100, value=0, show_label=False, interactive=False, scale=2)
                stxt = gr.Textbox(value="Pending", show_label=False, interactive=False, scale=1, min_width=120)
            stage_components[stage_name] = {"icon": icon, "progress": pbar, "status": stxt}

        # --- Settings ---
        with gr.Accordion("Settings", open=False):
            enable_sep = gr.Checkbox(value=config.enable_vocal_separation, label="Enable Vocal Separation (Demucs)")

            tts_engine = gr.Radio(
                choices=[("XTTSv2 (Voice Clone)", "xtts"), ("Edge-TTS (Free Cloud)", "edge")],
                value=config.tts_engine,
                label="TTS Engine",
            )

            edge_voice = gr.Dropdown(
                choices=[
                    "pt-BR-ThalitaMultilingualNeural",
                    "pt-BR-AntonioNeural",
                    "pt-BR-FranciscaNeural",
                    "pt-PT-DuarteNeural",
                    "pt-PT-RaquelNeural",
                ],
                value=config.EDGE_TTS_VOICE,
                label="Edge-TTS Voice",
                visible=(config.tts_engine == "edge"),
            )

            tts_engine.change(
                fn=lambda x: gr.update(visible=(x == "edge")),
                inputs=tts_engine,
                outputs=edge_voice,
            )

            with gr.Row():
                bg_vol = gr.Slider(0.0, 1.5, value=config.BACKGROUND_VOLUME, step=0.05, label="Background Volume")
                dub_vol = gr.Slider(0.0, 1.5, value=config.DUB_VOLUME, step=0.05, label="Dub Volume")

            max_speed = gr.Slider(1.1, 2.0, value=config.MAX_SPEED_RATIO, step=0.05, label="Max Speed Ratio")

            stretch_method = gr.Radio(
                choices=[("Rubberband (Best Quality)", "rubberband"), ("Atempo (Faster)", "atempo")],
                value=config.STRETCH_METHOD,
                label="Stretch Method",
            )

            words_per_cue = gr.Slider(2, 15, value=config.WORDS_PER_CUE, step=1, label="Words per Cue")
            ref_audio = gr.Audio(label="Reference Audio (for XTTS cloning)", type="filepath")

        # --- Preview ---
        gr.Markdown("### Preview")
        with gr.Tabs():
            with gr.Tab("Original Video"):
                original_video = gr.Video(label="Original Video")
            with gr.Tab("Vocals"):
                vocals_audio = gr.Audio(label="Extracted Vocals", type="filepath")
            with gr.Tab("Background"):
                bg_audio = gr.Audio(label="Background Audio", type="filepath")
            with gr.Tab("EN Subtitles"):
                en_srt_text = gr.Textbox(label="English SRT", lines=20, interactive=False)
            with gr.Tab("PT Subtitles"):
                pt_srt_text = gr.Textbox(label="Portuguese SRT", lines=20, interactive=False)
            with gr.Tab("PT Audio"):
                pt_audio = gr.Audio(label="Portuguese Audio", type="filepath")
            with gr.Tab("Final Video"):
                sub_toggle = gr.Radio(
                    choices=["Without Subtitles", "With Subtitles"],
                    value="With Subtitles",
                    label="Subtitles",
                    interactive=True,
                )
                final_video = gr.Video(label="Dubbed Video")

        # --- Downloads ---
        gr.Markdown("### Downloads")
        with gr.Row():
            download_video = gr.File(label="Dubbed Video (.mp4)")
            download_video_sub = gr.File(label="Dubbed w/ Subs (.mp4)")
            download_en = gr.File(label="EN Subtitles (.srt)")
            download_pt = gr.File(label="PT Subtitles (.srt)")

        # --- Wire up events ---
        # Collect all output components in order
        all_outputs = [status_text, project_state, original_video]
        for s in config.STAGE_ORDER:
            all_outputs.extend([
                stage_components[s]["icon"],
                stage_components[s]["progress"],
                stage_components[s]["status"],
            ])
        all_outputs.extend([
            final_video,
            vocals_audio, bg_audio, en_srt_text, pt_srt_text,
            pt_audio, download_video, download_video_sub, download_en, download_pt,
        ])

        start_btn.click(
            fn=on_start_processing,
            inputs=[
                video_input, enable_sep, tts_engine, edge_voice,
                bg_vol, dub_vol, max_speed, stretch_method,
                words_per_cue, ref_audio,
            ],
            outputs=all_outputs,
        )

        # Toggle subtitles: switch between plain and subtitled video
        sub_toggle.change(
            fn=toggle_subtitles,
            inputs=[sub_toggle, project_state],
            outputs=[final_video],
        )

    return app