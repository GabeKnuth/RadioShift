#!/usr/bin/env python3
from collections import deque
import threading
import numpy as np

from typing import Optional, Tuple

class TimeShiftBuffer:
    def __init__(self, past_seconds: int, future_seconds: int, sample_rate: int, channels: int):
        self.sample_rate = sample_rate
        self.channels = channels
        self.buffer_size = int((past_seconds + future_seconds) * sample_rate)
        self.buffer = np.zeros((self.buffer_size, channels), dtype='int16')
        
        self.write_pos = 0
        self.read_pos = 0
        self.live_delay_frames = int(0.1 * sample_rate)
        self.stored_frames = 0
        
        self.playback_paused = False
        self.pause_position = None
        self.time_shift = 0
        self.cumulative_shift = 0  # Track total buffered time
        self.lock = threading.RLock()
        
        self.past_frames = int(past_seconds * sample_rate)
        self.future_frames = int(future_seconds * sample_rate)

    def write(self, data: np.ndarray) -> None:
        with self.lock:
            frames_to_write = len(data)
            
            if self.write_pos + frames_to_write > self.buffer_size:
                first_part = self.buffer_size - self.write_pos
                self.buffer[self.write_pos:] = data[:first_part]
                self.buffer[:frames_to_write-first_part] = data[first_part:]
                self.write_pos = frames_to_write - first_part
            else:
                self.buffer[self.write_pos:self.write_pos + frames_to_write] = data
                self.write_pos = (self.write_pos + frames_to_write) % self.buffer_size
            
            self.stored_frames = min(self.stored_frames + frames_to_write, self.buffer_size)
            
            if not self.playback_paused and self.pause_position is None:
                self.read_pos = (self.write_pos - self.live_delay_frames - self.time_shift) % self.buffer_size

    def read(self, frames: int) -> np.ndarray:
        with self.lock:
            if self.playback_paused:
                return np.zeros((frames, self.channels), dtype='int16')

            output = np.zeros((frames, self.channels), dtype='int16')
            read_from = self.read_pos
            
            if read_from + frames > self.buffer_size:
                first_part = self.buffer_size - read_from
                output[:first_part] = self.buffer[read_from:]
                output[first_part:] = self.buffer[:frames-first_part]
            else:
                output = self.buffer[read_from:read_from + frames].copy()
            
            self.read_pos = (read_from + frames) % self.buffer_size
            return output

    def reset_to_live(self) -> None:
        with self.lock:
            self.time_shift = 0
            self.cumulative_shift = 0  # Reset cumulative time
            self.playback_paused = False
            self.pause_position = None
            self.read_pos = (self.write_pos - self.live_delay_frames) % self.buffer_size

    def pause(self) -> None:
        with self.lock:
            self.playback_paused = True
            self.pause_position = (self.write_pos - self.live_delay_frames - self.time_shift) % self.buffer_size

    def resume(self) -> None:
        with self.lock:
            if self.pause_position is not None:
                self.read_pos = self.pause_position
                frames_since_pause = (self.write_pos - self.read_pos) % self.buffer_size
                self.time_shift = frames_since_pause
                self.cumulative_shift = frames_since_pause  # Update cumulative time
            self.playback_paused = False
            self.pause_position = None

    def move_backward(self, frames: int) -> None:
        with self.lock:
            available_frames = min(self.stored_frames, self.past_frames)
            shift = min(available_frames, self.time_shift + frames)
            self.time_shift = shift
            self.cumulative_shift = shift  # Update cumulative time
            if not self.playback_paused:
                self.read_pos = (self.write_pos - self.live_delay_frames - self.time_shift) % self.buffer_size

    def move_forward(self, frames: int) -> None:
        with self.lock:
            new_shift = max(0, self.time_shift - frames)
            self.time_shift = new_shift
            self.cumulative_shift = new_shift  # Update cumulative time
            if not self.playback_paused:
                self.read_pos = (self.write_pos - self.live_delay_frames - self.time_shift) % self.buffer_size

    def is_live(self) -> bool:
        with self.lock:
            return self.time_shift == 0 and not self.playback_paused

    def get_remaining_buffer_time(self) -> float:
        """Return time between live and playback position"""
        with self.lock:
            if self.playback_paused:
                return (self.write_pos - self.pause_position) % self.buffer_size / self.sample_rate
            return self.time_shift / self.sample_rate

    def get_future_buffer_time(self) -> float:
        """Return remaining buffer time after current position"""
        with self.lock:
            return (self.stored_frames - self.time_shift) / self.sample_rate

    def get_buffer_time(self) -> float:
        with self.lock:
            return self.stored_frames / self.sample_rate

    def get_delayed_time(self) -> float:
        with self.lock:
            return self.cumulative_shift / self.sample_rate