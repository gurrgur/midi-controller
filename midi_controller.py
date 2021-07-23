import json
import logging
import time
from collections import deque
from datetime import datetime, timedelta

logging.basicConfig(format="%(asctime)s %(message)s", level=logging.INFO)

import mido
import systemd.daemon


def get_port(port_name="MidiLink Mini", poll_interval=3):
    while True:
        for i in mido.get_input_names():
            if port_name in i:
                return i
        time.sleep(poll_interval)


class ProgramMapper:
    def __init__(
        self,
        outport,
        state_file="/etc/midi-controller/programs.json",
        in_channel=0,
        out_channel=3,
        n_loops=4,
        bank_size=4,
        n_banks=9,
        tripletap_time=timedelta(seconds=1),
    ):
        # configuration
        self.outport = outport
        self.state_file = state_file
        self.in_channel = in_channel
        self.out_channel = out_channel
        self.n_loops = n_loops
        self.bank_size = bank_size
        self.n_banks = n_banks
        self.n_programs = n_banks * bank_size
        self.tripletap_time = tripletap_time

        # looper program mapping and config
        self.looper_programs = {
            (False, False): 0,
            (True, False): 1,
            (False, True): 2,
            (True, True): 3,
        }
        self.control_commands = [80, 81, 82, 83]

        # each program has a corresponding looper state
        try:
            with open(self.state_file, "r") as f:
                self.programs = json.load(f)
        except FileNotFoundError:
            self.programs = [
                [False for _ in range(n_loops)] for _ in range(bank_size * n_banks)
            ]
            self.save_programs()

        # modal state
        self.edit_mode = False
        self.active_program = 0
        self.apply_program()
        # make current loop state available for manual loop switching
        self.active_state = self.programs[self.active_program].copy()

        # save last program change with corresponding timestamp
        self.ts_history = deque([datetime.now()] * 3)
        self.program_history = deque([-1] * 3)
        self.last_ts = datetime.now()

    def handle(self, message):
        # sometimes switches fire more than one during single button press
        lts = self.last_ts
        self.last_ts = datetime.now()
        if self.last_ts - lts < timedelta(milliseconds=100):
            return

        if message.channel == self.in_channel and datetime.now() - self.ts_history[
            -1
        ] > timedelta(milliseconds=100):
            if message.type == "program_change":
                self.ts_history.popleft()
                self.ts_history.append(datetime.now())

                self.program_history.popleft()
                self.program_history.append(message.program)

            if self.edit_mode:

                # exit edit mode
                if (
                    message.type == "program_change"
                    and self.program_history[-1] != self.active_program
                ):
                    logging.info(f"Program {self.active_program}: Exit edit mode.")
                    self.edit_mode = False

                # edit program
                elif message.type == "control_change" and (80 <= message.control <= 83):
                    p = self.active_program
                    loop = 3 - message.control + 80
                    loop_state = not self.programs[p][loop]
                    self.programs[p][loop] = loop_state
                    logging.info(
                        f"Program {p}: Turn {'on' if loop_state else 'off'} loop {loop}."
                    )
                    self.apply_program()
                    self.save_programs()

            # program mode
            else:

                # hitting the same program button thrice activates edit mode
                if (
                    message.type == "program_change"
                    and self.ts_history[-1] - self.ts_history[0] <= self.tripletap_time
                    and self.program_history[0]
                    == self.program_history[1]
                    == self.program_history[2]
                ):
                    self.edit_mode = True
                    self.active_program = message.program
                    logging.info(f"Program {self.active_program}: Entering edit mode.")

                # change program
                elif (
                    message.type == "program_change"
                    and self.active_program != message.program
                ):
                    self.active_program = message.program
                    logging.info(
                        f"Set program {message.program} "
                        + f"with loop states {[int(b) for b in self.programs[message.program]]}."
                    )
                    self.apply_program()

                # toggle loops manually but dont change program data
                elif message.type == "control_change" and (80 <= message.control <= 83):
                    loop = 3 - message.control + 80
                    self.active_state[loop] = not self.active_state[loop]
                    self.outport.send(
                        mido.Message(
                            channel=self.out_channel,
                            type="control_change",
                            control=80 + loop,
                            value=127 * self.active_state[loop],
                        )
                    )
                    logging.info(
                        f"Turn loop {loop} {'on' if self.active_state[loop] else 'off'}."
                    )

    def apply_program(self):
        self.active_state = self.programs[self.active_program].copy()
        digit_left = 1 + self.looper_programs[tuple(self.active_state[:2])]
        digit_right = self.looper_programs[tuple(self.active_state[2:])]
        looper_program = 10 * digit_left + digit_right

        msg = mido.Message(
            channel=self.out_channel, type="program_change", program=looper_program
        )
        # logging.info(f"Outport::Message {msg}")
        self.outport.send(msg)

    def save_programs(self):
        logging.info("Saving programs to disk.")
        with open(self.state_file, "w") as f:
            json.dump(self.programs, f)


if __name__ == "__main__":
    inport_name = get_port("MidiLink Mini")
    outport_name = get_port("MidiLink Mini")

    logging.info(f'Using midi input  "{inport_name}".')
    logging.info(f'Using midi output "{outport_name}".')
    systemd.daemon.notify('READY=1')
    
    with mido.open_output(outport_name) as outport, mido.open_input(
        inport_name
    ) as inport:
        mapper = ProgramMapper(outport)
        for message in inport:
            mapper.handle(message)
