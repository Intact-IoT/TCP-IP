from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
import time

# ==============================
# MODBUS TCP CONNECTION SETTINGS
# (Update IP, port, and register addresses for your devices)
# ==============================
DEVICES = [
    {
        "name": "Modbus_Device_1",
        "ip": "192.168.0.12",
        "port": 502,
        "reads": [
            {"address": 0, "count": 2},  # Example registers to read
        ],
    },
    {
        "name": "Modbus_Device_2",
        "ip": "192.168.0.11",
        "port": 502,
        # Updated to addresses 0 and 1 as starting point for safe testing
        "reads": [
            {"address": 0, "count": 2},
            {"address": 1, "count": 2},
        ],
    },
]

# ==============================
# HELPER FUNCTIONS
# ==============================
def read_holding_registers(client, reads):
    results = []
    for item in reads:
        address = item["address"]
        count = item["count"]
        try:
            try:
                response = client.read_holding_registers(address=address, count=count, unit=1)
            except TypeError:
                response = client.read_holding_registers(address=address, count=count)

            if response.isError():
                ex_code = getattr(response, "exception_code", "Unknown")
                results.append((address, None, f"Modbus Exception Code: {ex_code}"))
            else:
                results.append((address, response.registers, None))
        except ModbusException as e:
            results.append((address, None, f"Modbus Error: {e}"))
        except Exception as e:
            results.append((address, None, f"Error: {e}"))
    return results

def connect_and_read(device_config):
    name = device_config["name"]
    ip = device_config["ip"]
    port = device_config.get("port", 502)
    reads = device_config["reads"]

    client = ModbusTcpClient(ip, port=port)
    try:
        print(f"🔌 Connecting to {name} ({ip}:{port}) ...")
        if not client.connect():
            print(f"❌ Failed to connect to {name} ({ip}:{port})")
            return

        print(f"✅ Connected to {name}")

        results = read_holding_registers(client, reads)
        for address, values, error in results:
            if error:
                print(f"⚠️ {name} - Address {address} read error: {error}")
            else:
                print(f"📘 {name} - Address {address} = {values}")

    except Exception as e:
        print(f"⚠️ Error with {name}: {e}")

    finally:
        client.close()
        print(f"🔌 Disconnected from {name}")

# ==============================
# MAIN PROGRAM
# ==============================
if __name__ == "__main__":
    for device in DEVICES:
        connect_and_read(device)
        time.sleep(1)  # Small delay between device reads
