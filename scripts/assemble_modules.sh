#!/usr/bin/env bash
#
# assemble_modules.sh — populate the BernieBot module mount from sibling repo clones.
#
# Assumed VPS layout:
#   /srv/discord_bots/
#   ├── repositories/
#   │   ├── BernieBot/
#   │   ├── Travus_Bot_Base/
#   │   └── <other repos>/
#   └── berniebot/
#       ├── modules/
#       └── modules_backup/
#
# What it does:
#   - Discovers every directory under repositories/ that has a non-empty modules/ subdir.
#   - Asks whether to back up the current modules/ first; if yes, tars it into
#     modules_backup/modules-<date>.tar.gz before anything is cleared.
#   - Prompts to include each discovered repo's modules (default: no).
#   - Copies the ENTIRE modules/ tree of each selected repo — .py modules plus any
#     companion subdirs and asset files (json, images, ...) a module needs at runtime.
#   - Collision = the same top-level entry name (file or dir) provided by two selected
#     repos. Detected and aborted BEFORE the target is touched, so a collision never
#     leaves the target half-populated (and no backup is taken on abort).
#   - Clears the target completely, then assembles the selected set into it.
#   - Does NOT restart the bot — that is a deploy-plan concern.

set -euo pipefail
shopt -s nullglob

# VPS paths; overridable via env for testing.
REPOS_DIR="${ASSEMBLE_REPOS_DIR:-/srv/discord_bots/repositories}"
TARGET_DIR="${ASSEMBLE_TARGET_DIR:-/srv/discord_bots/berniebot/modules}"
BACKUP_DIR="${ASSEMBLE_BACKUP_DIR:-/srv/discord_bots/berniebot/modules_backup}"

if [[ ! -d "$TARGET_DIR" ]]; then
    echo "ERROR: target dir does not exist: $TARGET_DIR" >&2
    exit 1
fi

# Discover candidate repos: a modules/ subdir with at least one entry.
candidates=()
for repo in "$REPOS_DIR"/*/; do
    entries=("${repo}modules"/*)
    [[ ${#entries[@]} -gt 0 ]] && candidates+=("$repo")
done

if [[ ${#candidates[@]} -eq 0 ]]; then
    echo "ERROR: no repos with a non-empty modules/ dir found under $REPOS_DIR" >&2
    exit 1
fi

# Ask whether to back up the current modules/ before assembling.
printf 'Back up current modules to %s before assembling? [y/N] ' "$BACKUP_DIR"
read -r backup_ans
backup=0
[[ "$backup_ans" =~ ^[Yy] ]] && backup=1

# Prompt for each candidate.
selected=()
for repo in "${candidates[@]}"; do
    name=$(basename "$repo")
    entries=("${repo}modules"/*)
    printf 'Include modules from %s? (%d items: %s) [y/N] ' \
        "$name" "${#entries[@]}" "$(basename -a "${entries[@]}" | paste -sd, -)"
    read -r ans
    [[ "$ans" =~ ^[Yy] ]] && selected+=("$repo")
done

if [[ ${#selected[@]} -eq 0 ]]; then
    echo "Nothing selected; target dir left unchanged." >&2
    exit 1
fi

# Validate: detect collisions on top-level entry names before any change.
declare -A source_of
for repo in "${selected[@]}"; do
    for entry in "${repo}modules"/*; do
        ename=$(basename "$entry")
        if [[ -n "${source_of[$ename]:-}" ]]; then
            echo "ERROR: collision on $ename (from $(basename "$repo") and $(basename "${source_of[$ename]}"))" >&2
            exit 1
        fi
        source_of[$ename]="$repo"
    done
done

# Commit point: optional backup, full clear, then assemble.
if [[ "$backup" -eq 1 ]]; then
    if [[ -n "$(find "$TARGET_DIR" -mindepth 1 -print -quit)" ]]; then
        mkdir -p "$BACKUP_DIR"
        archive="$BACKUP_DIR/modules-$(date +%Y%m%d-%H%M%S).tar.gz"
        tar -czf "$archive" -C "$TARGET_DIR" .
        echo "Backed up current modules to $archive"
    else
        echo "Target is empty; nothing to back up."
    fi
fi

find "$TARGET_DIR" -mindepth 1 -delete
for ename in "${!source_of[@]}"; do
    cp -r "${source_of[$ename]}modules/$ename" "$TARGET_DIR/"
done

echo "Assembled ${#source_of[@]} item(s) from ${#selected[@]} repo(s)."