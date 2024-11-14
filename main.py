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
from persistence import FrequencyPersistence  # Add at top with other imports
from smbus2 import SMBus, i2c_msg

class FMRadio:
    def __init__(self):
        # Wait for I2C bus to be ready
        max_retries = 10
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                bus = SMBus(config.I2C_BUS_NUMBER)
                read = i2c_msg.read(config.TEA5767_ADDRESS, 5)
                bus.i2c_rdwr(read)
                status = list(read)
                rssi = (status[3] >> 4) & 0x0F

                bus.close()

                break
            except Exception as e:

                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:

                    raise
        
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
        
        # Initialize persistence and get starting frequency
        self.persistence = FrequencyPersistence(config)
        starting_frequency = self.persistence.load_frequency() or config.DEFAULT_FREQUENCY
        
        # Initialize radio without display callback first
        self.radio = Radio(config, 
            None,  # No display callback yet
            self.rssi_handler,
            self.persistence
        )
        
        # Prime the radio silently

        self.radio.set_frequency(88.1)
        time.sleep(0.5)
        
        # Now set the real frequency

        self.radio.set_frequency(starting_frequency)
        
        # Only now set up the display callback
        self.radio.display_callback = lambda: self.display.update(
            self.radio.get_frequency(),
            self.audio_buffer.playback_paused,
            self.rssi_handler,
            self.audio_buffer
        )
        
        # Trigger initial display update
        if self.radio.display_callback:
            self.radio.display_callback()
        
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

            # Write incoming audio to buffer
            self.audio_buffer.write(indata.copy())

            # Get buffered data for playback
            buffered_data = self.audio_buffer.read(frames)
        
        # Handle stereo conversion if needed
        if config.INPUT_CHANNELS == 1 and config.OUTPUT_CHANNELS == 2:
            outdata[:] = np.repeat(buffered_data, 2, axis=1)
        else:
            outdata[:] = buffered_data
     

    def _on_backward(self):
        """Handle backward button press"""
        previous_position = self.audio_buffer.get_delayed_time()
        
        # Original rewind logic
        half_second_frames = int(config.SAMPLE_RATE * 0.5)
        self.audio_buffer.move_backward(half_second_frames)

        
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
        


        self.display.update(
            self.radio.get_frequency(),
            self.audio_buffer.playback_paused,
            self.rssi_handler,
            self.audio_buffer
        )


    def _on_live(self):
        """Handle live button press"""
        self.audio_buffer.reset_to_live()

        self.display.update(
            self.radio.get_frequency(),
            self.audio_buffer.playback_paused,
            self.rssi_handler,
            self.audio_buffer,
            message="Reset to Live"
        )

    def _on_rotary(self, value):
        """Handle rotary encoder rotation"""
        # Check if we're playing from buffer
        is_buffered = not self.audio_buffer.is_live()
        
        # Adjust frequency regardless of playback state
        self.radio.adjust_frequency(value)
        
        # If we were playing from buffer, reset to live
        if is_buffered:
            self.audio_buffer.reset_to_live()

            # Update display with reset message
            self.display.update(
                self.radio.get_frequency(),
                self.audio_buffer.playback_paused,
                self.rssi_handler,
                self.audio_buffer,
                message="Reset to Live"
            )

    def run(self) -> NoReturn:
        """Main run loop"""
        try:

            
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

            print("\nExiting FM Radio")
        except Exception as e:

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


if __name__ == "__main__":
    # Create and run radio
    radio = FMRadio()
    radio.run()
