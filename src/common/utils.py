"""Common utilities"""

import json
import yaml
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pathlib import Path

def load_yaml_file(file_path: str) -> Dict[str, Any]:
    """Load YAML configuration file"""
    try:
        with open(file_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {file_path}: {e}")

def save_yaml_file(data: Dict[str, Any], file_path: str):
    """Save data to YAML file"""
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, indent=2)

def load_json_file(file_path: str) -> Dict[str, Any]:
    """Load JSON file"""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {file_path}: {e}")

def save_json_file(data: Dict[str, Any], file_path: str):
    """Save data to JSON file"""
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2, default=str)

def parse_duration(duration_str: str) -> timedelta:
    """Parse duration string like '2h', '30m', '1d' to timedelta"""
    if not duration_str:
        return timedelta()
    
    unit = duration_str[-1].lower()
    value = int(duration_str[:-1])
    
    if unit == 's':
        return timedelta(seconds=value)
    elif unit == 'm':
        return timedelta(minutes=value)
    elif unit == 'h':
        return timedelta(hours=value)
    elif unit == 'd':
        return timedelta(days=value)
    elif unit == 'w':
        return timedelta(weeks=value)
    else:
        raise ValueError(f"Unsupported duration unit: {unit}")

def format_timestamp(dt: Optional[datetime] = None) -> str:
    """Format datetime as ISO string"""
    if dt is None:
        dt = datetime.utcnow()
    return dt.isoformat() + 'Z'

def safe_json_loads(text: str, default: Any = None) -> Any:
    """Safely load JSON with fallback"""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default

def run_sync_in_async(func, *args, **kwargs):
    """Run synchronous function in async context"""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, func, *args, **kwargs)