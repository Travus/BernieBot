#!/usr/bin/env bash
#
# Tests for assemble_modules.sh. Pure bash, no external test framework.
# Runs the real script against sandbox dirs via the ASSEMBLE_* env overrides.
#
# Usage: bash scripts/test_assemble_modules.sh

set -uo pipefail
shopt -s nullglob

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASSEMBLE="$SCRIPT_DIR/assemble_modules.sh"

pass=0
fail=0
sandbox=""
out=""
code=0

indent() { local line; while IFS= read -r line; do printf '    %s\n' "$line"; done <<<"$1"; }

setup() {
    sandbox="$(mktemp -d)"
    mkdir -p "$sandbox/repos" "$sandbox/target"
    export ASSEMBLE_REPOS_DIR="$sandbox/repos"
    export ASSEMBLE_TARGET_DIR="$sandbox/target"
    export ASSEMBLE_BACKUP_DIR="$sandbox/backup"
}

teardown() {
    [[ -n "$sandbox" && -d "$sandbox" ]] && rm -rf "$sandbox"
    sandbox=""
}

# make_repo <name> <relpath> [<relpath> ...] — create a repo with module entries.
make_repo() {
    local name="$1"; shift
    local rel
    for rel in "$@"; do
        mkdir -p "$ASSEMBLE_REPOS_DIR/$name/modules/$(dirname "$rel")"
        echo "$name:$rel" > "$ASSEMBLE_REPOS_DIR/$name/modules/$rel"
    done
}

# run <answers> — pipe newline-separated answers; sets $out and $code.
run() {
    out="$(printf '%s\n' "$1" | bash "$ASSEMBLE" 2>&1)"
    code=$?
}

ok()  { pass=$((pass+1)); }
bad() { fail=$((fail+1)); printf '  FAIL: %s\n' "$1"; printf '    --- output ---\n'; indent "$out"; }

assert_code()     { if [[ "$code" -eq "$1" ]]; then ok; else bad "$2 (exit $code, wanted $1)"; fi; }
assert_contains() { if [[ "$out" == *"$1"* ]]; then ok; else bad "$2 (output missing: $1)"; fi; }
assert_file()     { if [[ -f "$1" ]]; then ok; else bad "$2 (missing file $1)"; fi; }
assert_absent()   { if [[ ! -e "$1" ]]; then ok; else bad "$2 (should not exist: $1)"; fi; }
assert_tree()     { # <expected newline list relative to target>
    local actual; actual="$(cd "$ASSEMBLE_TARGET_DIR" && find . -mindepth 1 | sort)"
    if [[ "$actual" == "$1" ]]; then ok; else bad "$2"; printf '    got:\n'; indent "$actual"; fi
}

echo "Running assemble_modules.sh tests..."

# 1. Happy path: single repo selected, flat modules copied.
setup
make_repo RepoA alpha.py beta.py
run $'n\ny'
assert_code 0 "happy: exit 0"
assert_contains "Assembled 2 item(s) from 1 repo(s)." "happy: summary"
assert_tree $'./alpha.py\n./beta.py' "happy: target has both modules"
teardown

# 2. Recursive asset dir copied alongside .py.
setup
make_repo RepoA mod.py assets/data.json assets/sub/img.bin
run $'n\ny'
assert_code 0 "assets: exit 0"
assert_file "$ASSEMBLE_TARGET_DIR/assets/sub/img.bin" "assets: nested asset copied"
assert_file "$ASSEMBLE_TARGET_DIR/mod.py" "assets: module copied"
teardown

# 3. Two repos merged (alphabetical prompt order: RepoA, RepoB).
setup
make_repo RepoA alpha.py
make_repo RepoB gamma.py
run $'n\ny\ny'
assert_code 0 "merge: exit 0"
assert_tree $'./alpha.py\n./gamma.py' "merge: both repos assembled"
teardown

# 4. Collision aborts before touching target; no backup taken.
setup
make_repo RepoA alpha.py
make_repo RepoB alpha.py
echo "preexisting" > "$ASSEMBLE_TARGET_DIR/old.py"
run $'y\ny\ny'
assert_code 1 "collision: nonzero exit"
assert_contains "collision on alpha.py" "collision: error names the file"
assert_tree './old.py' "collision: target left untouched"
assert_absent "$ASSEMBLE_BACKUP_DIR" "collision: no backup created"
teardown

# 5. Backup tars the OLD contents, then target is replaced.
setup
make_repo RepoA newmod.py
echo "old" > "$ASSEMBLE_TARGET_DIR/oldmod.py"
mkdir -p "$ASSEMBLE_TARGET_DIR/olddir" && echo "x" > "$ASSEMBLE_TARGET_DIR/olddir/x.txt"
run $'y\ny'
assert_code 0 "backup: exit 0"
assert_contains "Backed up current modules to" "backup: reports archive"
archives=("$ASSEMBLE_BACKUP_DIR"/modules-*.tar.gz)
arch="${archives[0]:-}"
assert_file "$arch" "backup: archive exists"
if [[ -f "$arch" ]]; then
    contents="$(tar -tzf "$arch" | sort)"
    if [[ "$contents" == *"./oldmod.py"* && "$contents" == *"./olddir/x.txt"* ]]; then ok; else bad "backup: archive holds old contents"; fi
else
    bad "backup: archive missing, cannot inspect"
fi
assert_tree './newmod.py' "backup: target replaced with new set"
teardown

# 6. Backup requested but target empty -> no tar, still assembles.
setup
make_repo RepoA mod.py
run $'y\ny'
assert_code 0 "backup-empty: exit 0"
assert_contains "nothing to back up" "backup-empty: reports nothing to back up"
assert_absent "$ASSEMBLE_BACKUP_DIR" "backup-empty: no archive created"
assert_tree './mod.py' "backup-empty: assembled"
teardown

# 7. Nothing selected -> abort, target unchanged.
setup
make_repo RepoA alpha.py
echo "keep" > "$ASSEMBLE_TARGET_DIR/keep.py"
run $'n\nn'
assert_code 1 "none: nonzero exit"
assert_contains "Nothing selected" "none: reports nothing selected"
assert_tree './keep.py' "none: target untouched"
teardown

# 8. No candidate repos -> error.
setup
mkdir -p "$ASSEMBLE_REPOS_DIR/Empty/modules"   # exists but empty -> not a candidate
run $'n'
assert_code 1 "no-candidates: nonzero exit"
assert_contains "no repos with a non-empty modules/ dir" "no-candidates: clear error"
teardown

# 9. Empty modules/ dir is not offered as a candidate.
setup
make_repo RepoA alpha.py
mkdir -p "$ASSEMBLE_REPOS_DIR/Empty/modules"
run $'n\ny'
assert_code 0 "skip-empty: exit 0"
if [[ "$out" != *"Include modules from Empty"* ]]; then ok; else bad "skip-empty: empty repo must not be offered"; fi
teardown

echo
echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]