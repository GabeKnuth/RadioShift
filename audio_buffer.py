#!/usr/bin/env python3
# audio_buffer.py - Audio buffer implementation

# Standard library imports
from collections import deque
import threading
from typing import Optional

# Third-party imports
import numpy as np

class DynamicBuffer:
    def __init__(self, past_seconds: int, future_seconds: int, sample_rate: int, channels: int):
        self.sample_rate = sample_rate
        self.channels = channels
        self.past_size = int(past_seconds * sample_rate)
        self.future_size = int(future_seconds * sample_rate)
        self.max_size = self.past_size + self.future_size
        self.past_buffer = deque(maxlen=self.past_size)
        self.future_buffer = deque(maxlen=self.future_size)
        self.playback_paused = False
        self.lock = threading.Lock()

    def write(self, data: np.ndarray) -> None:
        with self.lock:
            if not self.playback_paused:
                for frame in data:
                    self.future_buffer.append(frame)
                    self.past_buffer.append(frame)
                    if len(self.past_buffer) + len(self.future_buffer) > self.max_size:
                        self.past_buffer.popleft()
            else:
                for frame in data:
                    if len(self.future_buffer) < self.future_buffer.maxlen:
                        self.future_buffer.append(frame)
                    else:
                        self.reset_to_live()
                        break

    def read(self, frames: int) -> np.ndarray:
        with self.lock:
            if self.playback_paused:
                return np.zeros((frames, self.channels), dtype='int16')
            
            data = []
            for _ in range(frames):
                if self.future_buffer:
                    data.append(self.future_buffer.popleft())
                else:
                    data.append([0] * self.channels)
            return np.array(data, dtype='int16')

    def get_buffer_time(self, rewind_active=False) -> float:
        """Returns the current buffer time in seconds, adjusting for rewind."""
        with self.lock:
            past_time = len(self.past_buffer) / self.sample_rate
            future_time = len(self.future_buffer) / self.sample_rate
            
            # During rewind, focus playback position on past buffer only
            if rewind_active:
                total_time = past_time  # Emphasize past buffer during rewind
            else:
                total_time = past_time + future_time  # Regular playback uses both buffers

            return total_time

    def pause(self) -> None:
        with self.lock:
            self.playback_paused = True

    def resume(self) -> None:
        with self.lock:
            self.playback_paused = False

    def reset_to_live(self) -> None:
        with self.lock:
            self.future_buffer.clear()
            self.past_buffer.clear()
            self.playback_paused = False

    def move_backward(self, frames: int) -> None:
        """Move playback position backward by a specified number of frames."""
        with self.lock:
            moved_frames = 0  # Track the actual number of frames moved
            for _ in range(frames):
                if self.past_buffer:
                    self.future_buffer.appendleft(self.past_buffer.pop())
                    moved_frames += 1
                else:
                    break

    def is_live(self) -> bool:
        """Check if playback is live (playing in real-time)."""
        # Consider live if future_buffer has negligible frames
        return len(self.future_buffer) < self.sample_rate * 0.1  # e.g., 0.1s delay tolerance

    def get_future_buffer_time(self) -> float:
        """Return the buffered time available in future_buffer when paused."""
        with self.lock:
            return len(self.future_buffer) / self.sample_rate

    def get_remaining_buffer_time(self) -> float:
        """Return remaining time in the future buffer when playing from buffer."""
        with self.lock:
            return len(self.future_buffer) / self.sample_rate
