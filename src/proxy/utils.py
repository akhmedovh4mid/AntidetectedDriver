from typing import Dict, Union, List


def proxy_config_with_auth(
    host: str, port: int,
    username: str, password: str
) -> Dict[str, Union[Dict[str, str], List[Dict[str, Union[str, int, bool]]]]]:
    return {
            "log": {
                "level": "info"
            },
            "inbounds": [
                {
                "type": "socks",
                "tag": "socks-in",
                "listen": "127.0.0.1",
                "listen_port": 2080,
                "sniff": True
                }
            ],
            "outbounds": [
                {
                "type": "socks",
                "tag": "socks-out",
                "server": host,
                "server_port": port,
                "username": username,
                "password": password
                }
            ]
        }


def proxy_config_without_auth(
    host: str, port: int
) -> Dict[str, Union[Dict[str, str], List[Dict[str, Union[str, int, bool]]]]]:
    return {
            "log": {
                "level": "info"
            },
            "inbounds": [
                {
                "type": "socks",
                "tag": "socks-in",
                "listen": "127.0.0.1",
                "listen_port": 2080,
                "sniff": True
                }
            ],
            "outbounds": [
                {
                "type": "socks",
                "tag": "socks-out",
                "server": host,
                "server_port": port
                }
            ]
        }
