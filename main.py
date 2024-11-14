#!/usr/bin/env python3
# main.py - Main application

# Standard library imports
import threading
import time
import logging
from typing import NoReturn

# Third-party imports
import sounddevice as sd
import numpy as np

# Local imports (our modules)
from config import config, RadioConfig
from audio_buffer import TimeShiftBuffer
from display import Display
from buttons import ButtonHandler, RotaryHandler
from radio import Radio
from rssi import RSSIHandler

class FMRadio:
    def __init__(self):
        # Initialize components
        self.running = True
        self.audio_buffer = TimeShiftBuffer(
            past_seconds=config.PAST_BUFFER_SECONDS,
            future_seconds=config.FUTURE_BUFFER_SECONDS,
            sample_rate=config.SAMPLE_RATE,
            channels=config.INPUT_CHANNELS
        )
        
        self.display = Display(config)
        self.rssi_handler = RSSIHandler(config)
        
        # Initialize radio with display callback and rssi_handler
        self.radio = Radio(config, 
            lambda: self.display.update(
                self.radio.get_frequency(),
                self.audio_buffer.playback_paused,
                self.rssi_handler,
                self.audio_buffer
            ),
            self.rssi_handler  # Pass RSSI handler here
        )

        # Set up button callbacks
        self.button_callbacks = {
            'backward': self._on_backward,
            'forward': self._on_forward,
            'play_pause': self._on_play_pause,
            'live': self._on_live
        }
        
        self.button_handler = ButtonHandler(config, self.button_callbacks)
        self.rotary_handler = RotaryHandler(config, self._on_rotary)


    def _audio_callback(self, indata, outdata, frames, time_info, status):
        """Handle audio streaming and playback."""
        if status:
            logging.warning(f"Audio callback status: {status}")

        # Write incoming audio to buffer
        self.audio_buffer.write(indata.copy())

        # Get buffered data for playback
        buffered_data = self.audio_buffer.read(frames)
        
        # Handle stereo conversion if needed
        if config.INPUT_CHANNELS == 1 and config.OUTPUT_CHANNELS == 2:
            outdata[:] = np.repeat(buffered_data, 2, axis=1)
        else:
            outdata[:] = buffered_data
            
    # def _audio_callback(self, indata, outdata, frames, time_info, status):
    #     """Handle audio streaming and playback prioritization in buffered mode."""
    #     if status:
    #         logging.warning(f"Audio callback status: {status}")

    #     # Write incoming audio to buffer
    #     self.audio_buffer.write(indata.copy())

    #     if not self.audio_buffer.playback_paused:
    #         # Buffered playback: prioritize past_buffer temporarily after rewind
    #         if len(self.audio_buffer.past_buffer) > 0:
    #             buffered_data = self.audio_buffer.read(frames)
    #             if buffered_data is not None:
    #                 if config.INPUT_CHANNELS == 1 and config.OUTPUT_CHANNELS == 2:
    #                     outdata[:] = np.repeat(buffered_data, 2, axis=1)
    #                 else:
    #                     outdata[:] = buffered_data
    #             else:
    #                 outdata[:] = np.zeros((frames, config.OUTPUT_CHANNELS), dtype='int16')
    #         else:
    #             # Standard playback from future buffer if no past buffer frames
    #             buffered_data = self.audio_buffer.read(frames)
    #             if buffered_data is not None:
    #                 if config.INPUT_CHANNELS == 1 and config.OUTPUT_CHANNELS == 2:
    #                     outdata[:] = np.repeat(buffered_data, 2, axis=1)
    #                 else:
    #                     outdata[:] = buffered_data
    #             else:
    #                 outdata[:] = np.zeros((frames, config.OUTPUT_CHANNELS), dtype='int16')
    #     else:
    #         # Paused playback: output silence
    #         outdata[:] = np.zeros((frames, config.OUTPUT_CHANNELS), dtype='int16')


    # def _audio_callback(self, indata, outdata, frames, time_info, status):
    #     """Handle audio streaming"""
    #     if status:
    #         logging.warning(f"Audio callback status: {status}")
        
    #     self.audio_buffer.write(indata.copy())

    #     if not self.audio_buffer.playback_paused:
    #         buffered_data = self.audio_buffer.read(frames)
    #         if buffered_data is not None:
    #             if config.INPUT_CHANNELS == 1 and config.OUTPUT_CHANNELS == 2:
    #                 outdata[:] = np.repeat(buffered_data, 2, axis=1)
    #             else:
    #                 outdata[:] = buffered_data
    #         else:
    #             outdata[:] = np.zeros((frames, config.OUTPUT_CHANNELS), dtype='int16')
    #     else:
    #         outdata[:] = np.zeros((frames, config.OUTPUT_CHANNELS), dtype='int16')


    def _on_backward(self):
        """Handle backward button press"""
        previous_position = self.audio_buffer.get_delayed_time()
        
        # Original rewind logic
        half_second_frames = int(config.SAMPLE_RATE * 0.5)
        self.audio_buffer.move_backward(half_second_frames)
        logging.info("Moved playback backward by 0.5 seconds")
        
        new_position = self.audio_buffer.get_delayed_time()

        self.display.update(
            self.radio.get_frequency(),
            self.audio_buffer.playback_paused,
            self.rssi_handler,
            self.audio_buffer,
            message="-0.5s"
        )

    def _on_forward(self):
        """Handle forward button press"""
        previous_position = self.audio_buffer.get_delayed_time()
        
        # Original forward logic
        half_second_frames = int(config.SAMPLE_RATE * 0.5)
        self.audio_buffer.move_forward(half_second_frames)
        logging.info("Moved playback forward by 0.5 seconds")
        
        new_position = self.audio_buffer.get_delayed_time()

        self.display.update(
            self.radio.get_frequency(),
            self.audio_buffer.playback_paused,
            self.rssi_handler,
            self.audio_buffer,
            message="+0.5s"
        )

    def _on_play_pause(self):
        """Handle play/pause button press"""
        current_position = self.audio_buffer.get_delayed_time()
        
        # Original play/pause toggle logic
        if not self.audio_buffer.playback_paused:
            self.audio_buffer.pause()
            state = "paused"
        else:
            self.audio_buffer.resume()
            state = "resumed"
        
        logging.info(f"Playback {state}")

        self.display.update(
            self.radio.get_frequency(),
            self.audio_buffer.playback_paused,
            self.rssi_handler,
            self.audio_buffer
        )


    # def _on_backward(self):
    #     """Handle backward button press"""
    #     half_second_frames = int(config.SAMPLE_RATE * 0.5)
    #     self.audio_buffer.move_backward(half_second_frames)
    #     logging.info("Moved playback backward by 0.5 seconds")
    #     self.display.update(
    #         self.radio.get_frequency(),
    #         self.audio_buffer.playback_paused,
    #         self.rssi_handler,
    #         self.audio_buffer,
    #         message="-0.5s"
    #     )

    # def _on_forward(self):
    #     """Handle forward button press"""
    #     half_second_frames = int(config.SAMPLE_RATE * 0.5)
    #     self.audio_buffer.move_forward(half_second_frames)
    #     logging.info("Moved playback forward by 0.5 seconds")
    #     self.display.update(
    #         self.radio.get_frequency(),
    #         self.audio_buffer.playback_paused,
    #         self.rssi_handler,
    #         self.audio_buffer,
    #         message="+0.5s"
    #     )

    # def _on_play_pause(self):
    #     """Handle play/pause button press"""
    #     if not self.audio_buffer.playback_paused:
    #         self.audio_buffer.pause()
    #         state = "paused"
    #     else:
    #         self.audio_buffer.resume()
    #         state = "resumed"
    #     logging.info(f"Playback {state}")
    #     self.display.update(
    #         self.radio.get_frequency(),
    #         self.audio_buffer.playback_paused,
    #         self.rssi_handler,
    #         self.audio_buffer
    #     )

    def _on_live(self):
        """Handle live button press"""
        self.audio_buffer.reset_to_live()
        logging.info("Playback reset to live")
        self.display.update(
            self.radio.get_frequency(),
            self.audio_buffer.playback_paused,
            self.rssi_handler,
            self.audio_buffer,
            message="Live Reset"
        )

    def _on_rotary(self, value):
        """Handle rotary encoder rotation"""
        if not self.audio_buffer.playback_paused:
            self.radio.adjust_frequency(value)

    def run(self) -> NoReturn:
        """Main run loop"""
        try:
            logging.info("Starting FM Radio")
            
            # Set initial frequency
            self.radio.set_frequency(config.DEFAULT_FREQUENCY)
            time.sleep(0.5)  # Allow PLL to stabilize
            
            # Initial RSSI read and display update
            if config.ENABLE_RSSI:
                self.rssi_handler.read_signal_strength()
            self.display.update(
                self.radio.get_frequency(),
                self.audio_buffer.playback_paused,
                self.rssi_handler,
                self.audio_buffer
            )

            # Start threads
            button_thread = self.button_handler.start_polling()
            rotary_thread = self.rotary_handler.start()
            if config.ENABLE_RSSI:
                rssi_thread = self.rssi_handler.start_monitoring(
                    lambda: self.display.update(
                        self.radio.get_frequency(),
                        self.audio_buffer.playback_paused,
                        self.rssi_handler,
                        self.audio_buffer
                    )
                )

            # Start audio stream
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
                
                # Main loop with periodic display update for buffer duration while paused
                while self.running:
                    time.sleep(0.5)  # Refresh every 0.5 seconds
                    if self.audio_buffer.playback_paused:
                        # Update display with current buffer time while paused
                        self.display.update(
                            self.radio.get_frequency(),
                            self.audio_buffer.playback_paused,
                            self.rssi_handler,
                            self.audio_buffer
                        )

        except KeyboardInterrupt:
            logging.info("Keyboard interrupt received")
            print("\nExiting FM Radio")
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            print(f"An unexpected error occurred: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources"""
        self.running = False
        self.button_handler.cleanup()
        self.rotary_handler.stop()
        self.rssi_handler.stop_monitoring()
        self.display.cleanup()
        logging.info("FM Radio terminated")

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        filename='fm_radio.log',
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Create and run radio
    radio = FMRadio()
    radio.run()
