"""Check the running app's scene through its local command interface."""
from pathlib import Path
import socket
import json
import time
import deskpal


def command(value):
    with socket.create_connection(("127.0.0.1",50577),timeout=2) as connection:
        connection.settimeout(2)
        connection.sendall(value.encode("ascii"))
        return json.loads(connection.recv(4096))


def main():
    log = Path(deskpal.LOG_PATH)
    offset = log.stat().st_size if log.exists() else 0
    deadline = time.monotonic()+75
    last = None
    while time.monotonic() < deadline:
        try:
            state = command("status")
        except (OSError,ValueError):
            time.sleep(1)
            continue
        assert state.get("scene_error") is None, state
        if state.get("scene") != last:
            print(state,flush=True)
            last = state.get("scene")
        if state.get("scene") == "ready":
            break
        time.sleep(.5)
    else:
        raise AssertionError("Scene did not reach its waiting button")
    print("Starting real two-minute chase:",command("scene_chase"),flush=True)
    started = time.monotonic()
    states = set()
    while time.monotonic()-started < 145:
        state = command("status")
        assert state["running"] and state["visible"],state
        assert state.get("scene_error") is None,state
        scene = state.get("scene")
        states.add(scene)
        if scene != last:
            print("%.1fs" % (time.monotonic()-started),state,flush=True)
            last = scene
        if scene is None:
            break
        time.sleep(.5)
    assert {"chase","catch","share",None}.issubset(states), states
    elapsed = time.monotonic()-started
    assert elapsed >= 119,elapsed
    if log.exists():
        with log.open("rb") as stream:
            stream.seek(offset)
            recent = stream.read().decode("utf-8",errors="replace")
        assert not any(text in recent for text in ("Traceback","CALLBACK ERROR","Modak scene stopped:")),recent
    print("PASS: real-time chase, catch, handoff and cleanup in %.1fs; no recorded scene errors." % elapsed,flush=True)


if __name__ == "__main__":
    main()
