# PiSense

A Raspberry Pi application written in Python.

## Project Structure

```
PiSense/
├── src/              # Source code
│   ├── __init__.py
│   └── main.py       # Main application entry point
├── tests/            # Test files
│   ├── __init__.py
│   └── test_main.py
├── docs/             # Documentation
├── requirements.txt  # Python dependencies
├── pyproject.toml    # Project configuration
└── README.md         # This file
```

## Setup

### Prerequisites

- Python 3.9 or higher
- Raspberry Pi OS (for GPIO functionality)

### Installation

1. Clone or navigate to the project directory:
```bash
cd /path/to/PiSense
```

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

### Development Setup

Install development dependencies:
```bash
pip install -e ".[dev]"
```

## Usage

Run the main application:
```bash
python src/main.py
```

## Testing

Run tests using pytest:
```bash
pytest tests/
```

## Development

### Code Formatting

Format code with Black:
```bash
black src/ tests/
```

### Linting

Lint code with Ruff:
```bash
ruff check src/ tests/
```

## Common Raspberry Pi Libraries

The `requirements.txt` includes commented-out libraries for common Raspberry Pi tasks:

- **RPi.GPIO**: Low-level GPIO control
- **gpiozero**: High-level GPIO interface
- **Sensor libraries**: DHT, BME280, etc.
- **Display libraries**: OLED, LCD support
- **Camera**: picamera2 for camera module

Uncomment the libraries you need based on your hardware.

## License

TBD

## Contributing

TBD
