#!/usr/bin/env python3
import threading
import time
import logging
from typing import NoReturn

import sounddevice as sd
import numpy as np

from config import config
from audio_buffer import TimeShiftBuffer
from display import Display
from buttons import ButtonHandler, RotaryHandler
from radio import Radio
from rssi import RSSIHandler
from persistence import FrequencyPersistence
from smbus2 import SMBus, i2c_msg

class FMRadio:
    def __init__(self):
        self._xrun_flag = False

        self._wait_for_i2c()

        config.resolve_audio_devices()
        logging.info(f"Resolved audio devices: input={config.INPUT_DEVICE}, output={config.OUTPUT_DEVICE}")

        self.running = True
        self.audio_buffer = TimeShiftBuffer(
            past_seconds=config.PAST_BUFFER_SECONDS,
            future_seconds=config.FUTURE_BUFFER_SECONDS,
            sample_rate=config.SAMPLE_RATE,
            channels=config.INPUT_CHANNELS
        )

        self.display = Display(config)
        self.rssi_handler = RSSIHandler(config)
        self.persistence = FrequencyPersistence(config)

        self.radio = Radio(config, self.rssi_handler, self.persistence)
        self.radio.on_frequency_changed = self._on_state_changed

        # Prime the tuner
        logging.info("Priming radio")
        self.radio.set_frequency(88.1)
        time.sleep(0.5)

        starting_frequency = self.persistence.load_frequency() or config.DEFAULT_FREQUENCY
        logging.info(f"Setting to target frequency {starting_frequency}")
        self.radio.set_frequency(starting_frequency)

        self.button_callbacks = {
            'backward': self._on_backward,
            'forward': self._on_forward,
            'play_pause': self._on_play_pause,
            'live': self._on_live
        }
        self.button_handler = ButtonHandler(config, self.button_callbacks)
        self.rotary_handler = RotaryHandler(config, self._on_rotary)

    def _wait_for_i2c(self):
        for attempt in range(10):
            try:
                bus = SMBus(config.I2C_BUS_NUMBER)
                read = i2c_msg.read(config.TEA5767_ADDRESS, 5)
                bus.i2c_rdwr(read)
                bus.close()
                logging.info("I2C bus is ready")
                return
            except Exception as e:
                logging.warning(f"I2C not ready on attempt {attempt + 1}: {e}")
                if attempt < 9:
                    time.sleep(1)
                else:
                    raise RuntimeError("Failed to initialize I2C after maximum retries")

    def _on_state_changed(self):
        self._push_display_state()

    def _push_display_state(self, message=None):
        self.display.set_state(
            freq=self.radio.get_frequency(),
            paused=self.audio_buffer.playback_paused,
            rssi_handler=self.rssi_handler,
            audio_buffer=self.audio_buffer,
            message=message
        )

    def _audio_callback(self, indata, outdata, frames, time_info, status):
        if status:
            self._xrun_flag = True

        self.audio_buffer.write(indata.copy())
        buffered_data = self.audio_buffer.read(frames)

        if config.INPUT_CHANNELS == 1 and config.OUTPUT_CHANNELS == 2:
            outdata[:] = np.repeat(buffered_data, 2, axis=1)
        else:
            outdata[:] = buffered_data

    def _on_backward(self):
        half_second = int(config.SAMPLE_RATE * 0.5)
        self.audio_buffer.move_backward(half_second)
        logging.info("Moved playback backward by 0.5 seconds")
        self._push_display_state(message="-0.5s")

    def _on_forward(self):
        half_second = int(config.SAMPLE_RATE * 0.5)
        self.audio_buffer.move_forward(half_second)
        logging.info("Moved playback forward by 0.5 seconds")
        self._push_display_state(message="+0.5s")

    def _on_play_pause(self):
        if not self.audio_buffer.playback_paused:
            self.audio_buffer.pause()
            logging.info("Playback paused")
        else:
            self.audio_buffer.resume()
            logging.info("Playback resumed")
        self._push_display_state()

    def _on_live(self):
        self.audio_buffer.reset_to_live()
        logging.info("Playback reset to live")
        self._push_display_state(message="Reset to Live")

    def _on_rotary(self, value):
        is_buffered = not self.audio_buffer.is_live()
        self.radio.adjust_frequency(value)
        if is_buffered:
            self.audio_buffer.reset_to_live()
            logging.info("Playback reset to live after frequency change")

    def run(self) -> NoReturn:
        try:
            logging.info("Starting FM Radio")
            time.sleep(0.5)

            if config.ENABLE_RSSI:
                self.rssi_handler.read_signal_strength()
            self._push_display_state()

            # Start input threads
            self.button_handler.start_polling()
            self.rotary_handler.start()
            if config.ENABLE_RSSI:
                self.rssi_handler.start_monitoring()

            # Start audio
            with sd.Stream(
                device=(config.INPUT_DEVICE, config.OUTPUT_DEVICE),
                samplerate=config.SAMPLE_RATE,
                blocksize=config.BLOCKSIZE,
                dtype='int16',
                channels=(config.INPUT_CHANNELS, config.OUTPUT_CHANNELS),
                callback=self._audio_callback
            ):
                logging.info("Audio streaming started")
                print("FM Radio is running. Press Ctrl+C to exit.")

                refresh_interval = 1.0 / config.DISPLAY_REFRESH_HZ
                while self.running:
                    # Drain XRUN flag outside the audio callback
                    if self._xrun_flag:
                        self._xrun_flag = False
                        logging.warning("Audio XRUN detected")

                    # Push fresh state to display at the configured rate
                    self._push_display_state()
                    self.display.render_if_dirty()

                    time.sleep(refresh_interval)

        except KeyboardInterrupt:
            logging.info("Keyboard interrupt received")
            print("\nExiting FM Radio")
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            print(f"An unexpected error occurred: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        self.running = False
        self.button_handler.cleanup()
        self.rotary_handler.stop()
        self.rssi_handler.stop_monitoring()
        self.radio.cleanup()
        self.display.cleanup()
        logging.shutdown()

        import subprocess
        subprocess.run(['sync'], check=False)
        logging.info("FM Radio terminated")


if __name__ == "__main__":
    logging.basicConfig(
        filename='/var/tmp/fm_radio/fm_radio.log',
        filemode='a',
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    radio = FMRadio()
    radio.run()
