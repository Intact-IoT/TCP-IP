import json
import time
import datetime
import os
import platform
import sys
import configparser
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException


# LOG FUNCTION
def log(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


# CONFIG FILE LOADING WITH DEBUG
def load_config_debug(filename):
    log(f"Working directory: {os.getcwd()}")
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Config file not found at: {filename}")
    config = configparser.ConfigParser()
    read_files = config.read(filename)
    log(f"Loaded config file(s): {read_files}")
    log(f"Sections found: {config.sections()}")
    if "AWS" not in config:
        raise KeyError("Missing [AWS] section in config file.")
    return config


def load_aws_config(config):
    aws_config = config["AWS"]
    certs_folder = aws_config["certs_folder"]

    # Verify certificate files exist
    for key in ["root_ca", "private_key", "certificate"]:
        cert_path = os.path.join(certs_folder, aws_config[key])
        if not os.path.exists(cert_path):
            raise FileNotFoundError(f"Certificate file {key} not found at: {cert_path}")

    return {
        "thing_name": aws_config["thing_name"],
        "endpoint": aws_config["endpoint"],
        "port": int(aws_config["port"]),
        "root_ca": os.path.join(certs_folder, aws_config["root_ca"]),
        "private_key": os.path.join(certs_folder, aws_config["private_key"]),
        "certificate": os.path.join(certs_folder, aws_config["certificate"]),
        "topic": aws_config["topic"]
    }


def load_plcs_from_config(config):
    plcs = []
    for section in config.sections():
        if section != "AWS":
            queries_raw = config[section].get("queries", "")
            # Expecting queries in format "address,count;address,count" since pymodbus needs address/count
            reads = []
            for q in queries_raw.split(";"):
                if not q.strip():
                    continue
                parts = q.strip().split(",")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    reads.append({"address": int(parts[0]), "count": int(parts[1])})
            plcs.append({
                "name": config[section]["name"],
                "ip": config[section]["ip"],
                "port": int(config[section].get("port", 502)),
                "reads": reads
            })
    log(f"PLC configurations loaded: {[plc['name'] for plc in plcs]}")
    return plcs


def read_holding_registers(client, reads):
    results = []
    for item in reads:
        address = item["address"]
        count = item["count"]
        try:
            response = client.read_holding_registers(address=address, count=count, unit=1)
            if response.isError():
                results.append((address, None, f"Error: {response}"))
            else:
                results.append((address, response.registers, None))
        except ModbusException as e:
            results.append((address, None, f"Modbus Error: {e}"))
        except Exception as e:
            results.append((address, None, f"Error: {e}"))
    return results


def publish_to_aws(mqtt_client, topic, plc_name, address, value):
    payload = {
        "timestamp": int(time.time() * 1000),
        "plc_name": plc_name,
        "register_address": address,
        "value": value
    }
    try:
        mqtt_client.publish(topic, json.dumps(payload), 0)
        log(f"☁️ Published to {topic}: {payload}")
    except Exception as e:
        log(f"⚠️ MQTT publish failed: {e}")


if __name__ == "__main__":
    arch = platform.architecture()[0]
    log(f"Running Python architecture: {arch}")

    config_file = r"D:\Server code\aws\config.ini"
    try:
        config = load_config_debug(config_file)
        aws_settings = load_aws_config(config)
        PLCS = load_plcs_from_config(config)
    except (FileNotFoundError, KeyError) as e:
        log(f"[ERROR] Config error: {e}")
        sys.exit(1)

    mqtt_client = AWSIoTMQTTClient(aws_settings["thing_name"])
    mqtt_client.configureEndpoint(aws_settings["endpoint"], aws_settings["port"])
    mqtt_client.configureCredentials(
        aws_settings["root_ca"],
        aws_settings["private_key"],
        aws_settings["certificate"]
    )
    mqtt_client.configureOfflinePublishQueueing(-1)
    mqtt_client.configureDrainingFrequency(2)
    mqtt_client.configureConnectDisconnectTimeout(10)
    mqtt_client.configureMQTTOperationTimeout(5)

    try:
        mqtt_client.connect()
        log(f"✅ Connected to AWS IoT Core as {aws_settings['thing_name']}")
    except Exception as e:
        log(f"⚠️ MQTT Connection failed: {e}")
        sys.exit(1)

    try:
        while True:
            for plc in PLCS:
                client = ModbusTcpClient(plc["ip"], port=plc["port"])
                if not client.connect():
                    log(f"❌ Failed to connect to {plc['name']} ({plc['ip']}:{plc['port']})")
                    client.close()
                    continue

                log(f"✅ Connected to PLC {plc['name']}")

                results = read_holding_registers(client, plc["reads"])
                for address, values, error in results:
                    if error:
                        log(f"[ERROR] {plc['name']} - Address {address} read failed: {error}")
                    else:
                        log(f"🔍 PLC {plc['name']} Address {address}: Values={values}")
                        # If multiple registers, you can choose how to publish (here publishing full list)
                        publish_to_aws(mqtt_client, aws_settings["topic"], plc["name"], address, values)
                client.close()
                log(f"🔌 Disconnected from PLC {plc['name']}")
            time.sleep(5)
    except KeyboardInterrupt:
        log("🛑 Program stopped by user")
    finally:
        input("Press Enter to exit...")
