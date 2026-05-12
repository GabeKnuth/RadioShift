#!/usr/bin/env python3
import threading
import numpy as np

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
        self.pause_write_pos = None
        self.time_shift = 0

        # Lock only for control operations (pause/resume/seek).
        # The audio callback (write/read) runs lock-free in live mode.
        self.control_lock = threading.Lock()

        self.past_frames = int(past_seconds * sample_rate)

    def write(self, data: np.ndarray) -> None:
        frames = len(data)
        wp = self.write_pos

        if wp + frames > self.buffer_size:
            first = self.buffer_size - wp
            self.buffer[wp:] = data[:first]
            self.buffer[:frames - first] = data[first:]
            wp = frames - first
        else:
            self.buffer[wp:wp + frames] = data
            wp = (wp + frames) % self.buffer_size

        self.write_pos = wp
        self.stored_frames = min(self.stored_frames + frames, self.buffer_size)

    def read(self, frames: int) -> np.ndarray:
        if self.playback_paused:
            return np.zeros((frames, self.channels), dtype='int16')

        # In live mode, compute read position from write position on demand
        if self.time_shift == 0:
            rp = (self.write_pos - self.live_delay_frames) % self.buffer_size
        else:
            rp = self.read_pos

        output = np.zeros((frames, self.channels), dtype='int16')
        if rp + frames > self.buffer_size:
            first = self.buffer_size - rp
            output[:first] = self.buffer[rp:]
            output[first:] = self.buffer[:frames - first]
        else:
            output[:] = self.buffer[rp:rp + frames]

        self.read_pos = (rp + frames) % self.buffer_size
        return output

    def reset_to_live(self) -> None:
        with self.control_lock:
            self.time_shift = 0
            self.playback_paused = False
            self.pause_write_pos = None
            self.read_pos = (self.write_pos - self.live_delay_frames) % self.buffer_size

    def pause(self) -> None:
        with self.control_lock:
            self.playback_paused = True
            self.pause_write_pos = self.write_pos

    def resume(self) -> None:
        with self.control_lock:
            if self.pause_write_pos is not None:
                frames_since_pause = (self.write_pos - self.pause_write_pos) % self.buffer_size
                self.time_shift += frames_since_pause
                self.read_pos = (self.write_pos - self.live_delay_frames - self.time_shift) % self.buffer_size
            self.playback_paused = False
            self.pause_write_pos = None

    def move_backward(self, frames: int) -> None:
        with self.control_lock:
            available = min(self.stored_frames, self.past_frames)
            self.time_shift = min(available, self.time_shift + frames)
            if not self.playback_paused:
                self.read_pos = (self.write_pos - self.live_delay_frames - self.time_shift) % self.buffer_size

    def move_forward(self, frames: int) -> None:
        with self.control_lock:
            self.time_shift = max(0, self.time_shift - frames)
            if not self.playback_paused:
                self.read_pos = (self.write_pos - self.live_delay_frames - self.time_shift) % self.buffer_size

    def is_live(self) -> bool:
        return self.time_shift == 0 and not self.playback_paused

    def get_remaining_buffer_time(self) -> float:
        if self.playback_paused and self.pause_write_pos is not None:
            frames_since = (self.write_pos - self.pause_write_pos) % self.buffer_size
            return (self.time_shift + frames_since) / self.sample_rate
        return self.time_shift / self.sample_rate

    def get_buffer_time(self) -> float:
        return self.stored_frames / self.sample_rate
