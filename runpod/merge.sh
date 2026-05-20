#!/bin/bash
# Manual merge helper — run from the RunPod web terminal when the merge stage fails
# Usage:
#   bash /app/runpod/merge.sh              → lists all projects + status
#   bash /app/runpod/merge.sh PROJECT_ID   → runs merge for that project
#   bash /app/runpod/merge.sh all          → runs merge for every project missing output

cd /app

list_projects() {
    echo "========================================"
    echo "  Projects in /app/data/projects"
    echo "========================================"
    for dir in /app/data/projects/*/; do
        id=$(basename "$dir")
        video=$(ls "$dir/input/" 2>/dev/null | head -1)
        output=$(ls "$dir/output/"*_dublado_pt.mp4 2>/dev/null | head -1)
        vocals="$dir/work/dubbed_vocals.wav"
        if [ -f "$output" ]; then
            status="DONE"
        elif [ -f "$vocals" ]; then
            status="READY_TO_MERGE"
        else
            stage=$(ls "$dir/work/" 2>/dev/null | tail -1)
            status="IN_PROGRESS ($stage)"
        fi
        echo "  $id  |  ${video:-no video}  |  $status"
    done
    echo ""
}

run_merge() {
    local project_id="$1"
    echo "Running merge for project: $project_id"
    python3 - <<PYEOF
import sys
sys.path.insert(0, '/app')
from pathlib import Path
from config import Config
from stages.merge import merge
import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

project_id = '$project_id'
project_dir = Path('/app/data/projects') / project_id

if not project_dir.exists():
    print(f'ERROR: Project not found: {project_dir}')
    sys.exit(1)

vocals = project_dir / 'work' / 'dubbed_vocals.wav'
if not vocals.exists():
    print(f'ERROR: dubbed_vocals.wav not found — sync stage has not completed yet')
    sys.exit(1)

print(f'Merging {project_id} ...')
result = merge(project_dir, Config())
if result.success:
    print('SUCCESS!')
    for p in result.output_paths:
        print(f'  -> {p}')
else:
    print(f'FAILED: {result.error}')
    sys.exit(1)
PYEOF
}

if [ -z "$1" ]; then
    list_projects
elif [ "$1" = "all" ]; then
    list_projects
    for dir in /app/data/projects/*/; do
        id=$(basename "$dir")
        output=$(ls "$dir/output/"*_dublado_pt.mp4 2>/dev/null | head -1)
        vocals="$dir/work/dubbed_vocals.wav"
        if [ -z "$output" ] && [ -f "$vocals" ]; then
            run_merge "$id"
            echo ""
        fi
    done
else
    run_merge "$1"
fi
