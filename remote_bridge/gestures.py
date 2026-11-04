# SPDX-License-Identifier: GPL-3.0-only
"""Single/double/hold recognition with cancel-safe, injectable scheduling."""
import asyncio

class Gestures:
    def __init__(self, fire, call_later=None, double_seconds=.30, hold_seconds=.55):
        self.fire = fire
        self.later = call_later or (lambda delay, callback: asyncio.get_running_loop().call_later(delay, callback))
        self.double_seconds, self.hold_seconds = double_seconds, hold_seconds
        self.states = {}

    def handle(self, identity, value, single, double=None, hold=None):
        state = self.states.get(identity)
        if value == 1:
            if state and state.get("down"):
                return
            second = bool(state and state.get("click_timer"))
            if second:
                state["click_timer"].cancel()
            state = {"down": True, "second": second, "fired": False, "single": single,
                     "double": double, "hold": hold}
            self.states[identity] = state
            if hold is not None:
                def held():
                    if self.states.get(identity) is state and state["down"]:
                        state["fired"] = True
                        self.fire(hold)
                state["hold_timer"] = self.later(self.hold_seconds, held)
        elif value == 0 and state and state.get("down"):
            state["down"] = False
            timer = state.pop("hold_timer", None)
            if timer:
                timer.cancel()
            if state["fired"]:
                self.states.pop(identity, None)
            elif double is not None and state["second"]:
                self.fire(double)
                self.states.pop(identity, None)
            elif double is not None:
                def clicked():
                    if self.states.get(identity) is state:
                        self.states.pop(identity, None)
                        self.fire(single)
                state["click_timer"] = self.later(self.double_seconds, clicked)
            else:
                self.fire(single)
                self.states.pop(identity, None)

    def cancel(self, path=None):
        for identity, state in list(self.states.items()):
            if path is None or identity[0] == path:
                for key in ("click_timer", "hold_timer"):
                    timer = state.get(key)
                    if timer:
                        timer.cancel()
                self.states.pop(identity, None)
