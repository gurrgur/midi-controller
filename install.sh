#!/bin/bash

# install systemd unit file

sudo cp ./midi_controller.service /etc/systemd/system/
sudo chown root:root /etc/systemd/system/midi_controller.service
sudo chmod 644 /etc/systemd/system/midi_controller.service

# install midi controller script

sudo mkdir /usr/local/lib/midi_controller
sudo cp ./midi_controller.py /usr/local/lib/midi_controller/
sudo chown root:root /usr/local/lib/midi_controller/midi_controller.py
sudo chmod 644 /usr/local/lib/midi_controller/midi_controller.py