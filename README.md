# RadioShift

A Raspberry Pi FM radio with DVR-like time-shifting capabilities that allows you to pause, rewind, and fast-forward through live, analog radio.

## Features

- **Time-Shifting**: Pause live radio and rewind up to 60 seconds, or buffer up to 5 minutes of content
- **TEA5767 Integration**: Uses the TEA5767 FM tuner module via I2C
- **OLED Display**: Shows frequency, signal strength, playback status, and buffer information
- **Physical Controls**: 
  - Four buttons: play/pause, forward, backward, and reset to live
  - Rotary encoder for frequency tuning
- **RSSI Monitoring**: Displays signal strength with a visual indicator
- **Frequency Persistence**: Remembers the last tuned station across reboots

## Hardware Requirements

- Raspberry Pi (any model <= Pi 4. Pi5 is weird with this hardware config.)
- TEA5767 FM tuner module (I2C interface)
- OLED display (SPI interface, SSD1306 controller)
- 4 push buttons
- Rotary encoder
- Audio output (speakers or headphones)

## Software Dependencies

- Python 3.6+
- RPi.GPIO
- sounddevice
- numpy
- smbus2
- Pillow (PIL)
- luma.core and luma.oled
- evdev

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/GabeKnuth/RadioShift.git
   cd RadioShift
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Ensure I2C and SPI are enabled on your Raspberry Pi:
   ```
   sudo raspi-config
   ```
   Navigate to "Interface Options" and enable both I2C and SPI.

4. Connect the hardware:
   - TEA5767 module to the I2C pins (GPIO 2 & 3)
   - OLED display to the SPI pins
   - Buttons to GPIO pins as defined in `config.py`
   - Rotary encoder to appropriate pins

## Usage

1. Run the main application:
   ```
   python main.py
   ```

2. Controls:
   - Rotate the encoder to tune radio frequency
   - Press play/pause button to pause/resume playback
   - Press backward button to rewind by 0.5 seconds
   - Press forward button to advance by 0.5 seconds
   - Press live button to return to live radio

## Configuration

All configuration settings can be adjusted in `config.py`, including:

- Buffer times for past and future content
- Audio settings (sample rate, block size, etc.)
- GPIO pin assignments
- Default frequency
- RSSI display settings

## System Architecture

- `main.py`: Application entry point
- `audio_buffer.py`: Time-shifting buffer implementation
- `radio.py`: TEA5767 FM tuner control
- `display.py`: OLED display interface
- `buttons.py`: Physical controls handling
- `rssi.py`: Signal strength monitoring
- `persistence.py`: Frequency persistence across reboots
- `config.py`: Configuration settings
