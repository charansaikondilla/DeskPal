"""Audit current DeskPal animation support; optionally play existing live emotes."""
import ast
import json
from pathlib import Path
import time

import deskpal
import deskpal_launch_server as launcher


def main():
    tree = ast.parse(Path(deskpal.__file__).read_text(encoding="utf-8"))
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                  and n.name == "_build_emotes")
    assignment = next(n for n in ast.walk(method) if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "emotes" for t in n.targets))
    emotes = ast.literal_eval(assignment.value)
    errors = []
    deskpal.log_exc = lambda where: errors.append(where)
    checked = []
    for label, state, duration, _ in emotes:
        animator = deskpal.Animator(deskpal.Particles())
        animator.character = "custom"
        animator.set(state, duration, after="idle")
        poses = set()
        for _ in range(int(duration * 60) + 2):
            poses.add(animator.pose().get("custom_pose", "idle"))
            animator.update(1 / 60)
        checked.append({"label": label, "state": state, "duration": duration,
                        "pose_names": sorted(poses), "returned_to_idle": animator.state == "idle"})
    print(json.dumps({"simulated_emotes": len(checked), "caught_code_errors": errors,
                      "results": checked}, indent=2), flush=True)
    print("Requested sheets present:", {name: (Path(deskpal.PROJECT_ASSET_DIR) / name).exists()
          for name in ("vinayaka_sprint_sheet.png", "ganesh_sprint_sheet.png",
                       "rat_sprint_sheet.png", "modak_sprint_sheet.png")}, flush=True)
    print("Missing dedicated frame sets:", {
        state: [frame for frame in frames if not any(Path(paths.get(frame, "__missing__")).is_file()
                for paths in (deskpal.CUSTOM_POSE_PATHS, deskpal._BUNDLED_GANESH_POSES))]
        for state, frames in deskpal.GANESH_EMOTE_FRAME_SETS.items()}, flush=True)
    log = Path(deskpal.LOG_PATH)
    offset = log.stat().st_size if log.exists() else 0
    print("Live launch response:", launcher.desktop("launch"), flush=True)
    for command, expected, duration in (("walk", "walk", 4), ("run", "run_cycle", 3),
            ("hungry", "hungry_cycle", 3), ("laddu", "eat_laddu", 5),
            ("wave", "wave", 2.4), ("celebrate", "celebrate", 3)):
        response = launcher.desktop(command)
        assert response["state"] == expected, response
        time.sleep(duration + 0.5)
        after = launcher.desktop()
        print(json.dumps({"played": command, "acknowledged_state": response["state"],
                          "after": after}), flush=True)
        assert after["running"] and after["visible"], after
    recent = ""
    if log.exists():
        with log.open("rb") as stream:
            stream.seek(offset)
            recent = stream.read().decode("utf-8", errors="replace")
    print("New log contents:", recent or "(none)", flush=True)
    assert not errors, errors
    assert all(result["returned_to_idle"] for result in checked)
    assert "Traceback" not in recent and "TK CALLBACK ERROR" not in recent, recent
    print("PASS: code simulation and six live command acknowledgements; visual quality NOT certified.")


if __name__ == "__main__":
    main()
