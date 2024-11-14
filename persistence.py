#!/usr/bin/env python3
# persistence.py - Handle frequency persistence across reboots

import os
import logging
from pathlib import Path
from typing import Optional

class FrequencyPersistence:
    """Handle saving and loading the last tuned frequency"""
    
    def __init__(self, config):
        self.config = config
        # Use /var/tmp which is typically writable even on read-only filesystems
        self.persistence_dir = Path("/var/tmp/fm_radio")
        self.frequency_file = self.persistence_dir / "last_frequency"
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Ensure persistence directory exists"""
        try:
            self.persistence_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:


    def save_frequency(self, frequency: float) -> bool:
        """
        Save the current frequency to persistent storage.
        
        Args:
            frequency: The frequency to save
            
        Returns:
            bool: True if save was successful, False otherwise
        """
        try:
            with open(self.frequency_file, 'w') as f:
                f.write(f"{frequency:.1f}")
            return True
        except Exception as e:

            return False

    def load_frequency(self) -> Optional[float]:
        """
        Load the last saved frequency.
        
        Returns:
            float: The last saved frequency or None if no valid frequency found
        """
        try:
            if not self.frequency_file.exists():
                return None
                
            with open(self.frequency_file, 'r') as f:
                frequency = float(f.read().strip())
                
            # Validate frequency is within valid FM range
            if 87.5 <= frequency <= 108.0:
                return frequency
            return None
            
        except (ValueError, IOError) as e:

            return None