"""Custom video player helpers for the dubbing UI."""


def build_player_placeholder() -> str:
    """Placeholder shown before dubbing completes."""
    return (
        '<div style="text-align:center;padding:40px 20px;background:#1a1a2e;'
        'border-radius:12px;color:#c4b5fd;">'
        '<h3>Dubbed video will appear here</h3>'
        '<p style="color:#888;">Upload a video and click Start Dubbing</p>'
        '</div>'
    )