import requests
import zipfile
import io
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import os
from dotenv import load_dotenv
from config import Config

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WireGuardManager:
    def __init__(self):
        self.api_url = os.getenv('WG_API_URL')
        self.api_key = os.getenv('WG_API_KEY')
        self.headers = {
            'Content-Type': 'application/json',
            'wg-dashboard-apikey': self.api_key
        }
        
        # Твои три интерфейса
        self._regions = {
            'de': {
                'name': 'Germany',
                'flag': '🇩🇪',
                'endpoint': os.getenv('WG_ENDPOINT_DE'),
                'interface_name': 'wg-de'
            },
            'en': {
                'name': 'England', 
                'flag': '🇬🇧',
                'endpoint': os.getenv('WG_ENDPOINT_EN'),
                'interface_name': 'wg-en'
            },
            'nl': {
                'name': 'Netherlands',
                'flag': '🇳🇱',
                'endpoint': os.getenv('WG_ENDPOINT_NL'),
                'interface_name': 'wg-nl'
            }
        }
        
        self.dns = os.getenv('WG_DNS')
        self.mtu = int(os.getenv('WG_MTU'))
        self.keepalive = int(os.getenv('WG_KEEPALIVE'))
    
    def create_peer(self, interface_name: str, region_code: str, user_id: int, days_valid: int) -> Optional[Dict]:
        """ Создание нового peer в указанном интерфейсе через API /addPeers """
        peer_name = f"{user_id}-{region_code}-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        expires_at = datetime.now() + timedelta(days=days_valid)
        
        payload = {
            "name": peer_name,
            "public_key": "",
            "private_key": "",
            "allowed_ips": [],
            "endpoint_allowed_ip": "0.0.0.0/0",
            "DNS": self.dns,
            "mtu": self.mtu,
            "keepalive": self.keepalive,
            "preshared_key": "",
            "notes": f"Trial period until {expires_at.strftime('%Y-%m-%d %H:%M:%S')}"
        }
        
        try:
            url = f"{self.api_url}/addPeers/{interface_name}"
            logger.info(f"POST {url}")
            
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Response: {result}")
                
                if result.get('status') == True:
                    peer_data = result.get('data', {})
                    
                    # Ответ может быть списком или словарём
                    if isinstance(peer_data, list) and len(peer_data) > 0:
                        peer_info = peer_data[0]
                    else:
                        peer_info = peer_data
                    
                    peer_id = peer_info.get('id')
                    if not peer_id:
                        logger.error(f"No peer ID in response: {peer_info}")
                        return None
                    
                    logger.info(f"✅ Created peer {peer_name} in {interface_name}")
                    logger.info(f"Peer ID: {peer_id}")
                    logger.info(f"Allowed IP: {peer_info.get('allowed_ip')}")
                    
                    return {
                        'config_id': peer_id,
                        'config_name': peer_name,
                        'expires_at': expires_at,
                        'interface_name': interface_name,
                        'private_key': peer_info.get('private_key', ''),
                        'address': peer_info.get('allowed_ip', ''),
                        'dns': self.dns
                    }
                else:
                    error_msg = result.get('message', 'Unknown error')
                    logger.error(f"❌ API error: {error_msg}")
                    return None
            else:
                logger.error(f"❌ HTTP {response.status_code}: {response.text[:200]}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error creating peer: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    
    def get_peer_config(self, interface_name: str, peer_id: str, endpoint: str) -> Optional[str]:
        """
        Получение конфигурации peer через API /downloadPeer
        """
        try:
            url = f"{self.api_url}/downloadPeer/{interface_name}"
            
            response = requests.get(
                url,
                headers=self.headers,
                params={'id': peer_id},
                timeout=30
            )
            
            logger.info(f"Download URL: {url}?id={peer_id}")
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('status') == True:
                    data = result.get('data', {})
                    
                    # Правильное поле - 'file', а не 'config'
                    config_text = data.get('file')
                    
                    if config_text:
                        logger.info(f"✅ Successfully got config for {peer_id}")
                        
                        # Обновляем endpoint в конфиге на правильный
                        lines = config_text.split('\n')
                        for i, line in enumerate(lines):
                            if line.startswith('Endpoint ='):
                                # Используем endpoint из региона
                                lines[i] = f'Endpoint = {endpoint}'
                                break
                        
                        updated_config = '\n'.join(lines)
                        return updated_config
                    else:
                        logger.error(f"No 'file' field in response. Available keys: {list(data.keys())}")
                        return None
                else:
                    logger.error(f"API returned false: {result.get('message')}")
                    return None
            else:
                logger.error(f"HTTP {response.status_code}: {response.text}")
                return None
                    
        except Exception as e:
            logger.error(f"Error getting config for {peer_id}: {e}")
            import traceback
            traceback.print_exc()
            return None
        
    def create_all_regions_configs(self, user_id: int, days_valid: int, device_number: int = None, is_trial: bool = False) -> Dict[str, Dict]:
        """
        Создание конфигураций для всех трёх регионов (de, en, nl)
        is_trial: True если это пробный период, False если платная подписка
        """
        results = {}
        
        # Определяем тип подписки для названия
        if is_trial:
            sub_type = "trial"
        else:
            sub_type = "sub"
        
        for region_code, region_config in self.regions.items():
            logger.info(f"Creating config for {region_config['name']} ({region_config['interface_name']})")
      
            peer_name = f"{user_id}-{sub_type}-{device_number}-{region_code}"
            
            # Расчет даты истечения
            expires_at = datetime.now() + timedelta(days=days_valid)
            
            # Формируем payload для /addPeers
            payload = {
                "name": peer_name,
                "public_key": "",
                "private_key": "",
                "allowed_ips": [],
                "endpoint_allowed_ip": "0.0.0.0/0",
                "DNS": self.dns,
                "mtu": self.mtu,
                "keepalive": self.keepalive,
                "preshared_key": "",
                "notes": f"{'Trial' if is_trial else 'Subscription'} period until {expires_at.strftime('%Y-%m-%d %H:%M:%S')}"
            }
            
            try:
                response = requests.post(
                    f"{self.api_url}/addPeers/{region_config['interface_name']}",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    if result.get('status') == True:
                        peer_data = result.get('data', {})
                        
                        if isinstance(peer_data, list) and len(peer_data) > 0:
                            peer_info = peer_data[0]
                        else:
                            peer_info = peer_data
                        
                        logger.info(f"✅ Created peer {peer_name} in {region_config['interface_name']}")
                        
                        results[region_code] = {
                            'config_text': None,  # Заполним позже
                            'config_name': peer_name,
                            'config_id': peer_info.get('id'),
                            'expires_at': expires_at,
                            'region_name': region_config['name'],
                            'region_flag': region_config['flag'],
                            'interface_name': region_config['interface_name']
                        }
                    else:
                        logger.error(f"Failed to create peer: {result.get('message')}")
                else:
                    logger.error(f"HTTP {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Error creating peer: {e}")
        
        # Получаем конфиги для созданных peer'ов
        for region_code, config_data in results.items():
            region_config = self.regions[region_code]
            config_text = self.get_peer_config(
                region_config['interface_name'],
                config_data['config_id'],
                region_config['endpoint']
            )
            if config_text:
                results[region_code]['config_text'] = config_text
                logger.info(f"✅ Successfully created config for {region_config['name']}")
            else:
                logger.error(f"❌ Failed to get config for {region_config['name']}")
        
        return results
    
    def create_zip_archive(self, configs: Dict[str, Dict]) -> bytes:
        """
        Создание ZIP архива с конфигурациями для всех трёх регионов
        """
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Добавляем каждый конфиг
            for region_code, config_data in configs.items():
                # Имя файла: Германия.conf, Англия.conf, Нидерланды.conf
                filename = f"{config_data['region_name']}.conf"
                zip_file.writestr(filename, config_data['config_text'])
                
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
    
    def delete_peer(self, interface_name: str, peer_id: str) -> bool:
        """
        Удаление peer через API /deletePeers
        """
        try:
            payload = {
                "peers": [peer_id]
            }
            
            response = requests.post(
                f"{self.api_url}/deletePeers/{interface_name}",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('status', False)
            return False
        except Exception as e:
            logger.error(f"Error deleting peer: {e}")
            return False
    
    def restrict_peer(self, interface_name: str, peer_id: str) -> bool:
        """
        Блокировка peer (ограничение доступа)
        """
        try:
            payload = {
                "peers": [peer_id]
            }
            
            response = requests.post(
                f"{self.api_url}/restrictPeers/{interface_name}",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('status', False)
            return False
        except Exception as e:
            logger.error(f"Error restricting peer: {e}")
            return False
    
    def allow_peer(self, interface_name: str, peer_id: str) -> bool:
        """
        Разблокировка peer
        """
        try:
            payload = {
                "peers": [peer_id]
            }
            
            response = requests.post(
                f"{self.api_url}/allowAccessPeers/{interface_name}",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('status', False)
            return False
        except Exception as e:
            logger.error(f"Error allowing peer: {e}")
            return False
    
    def test_connection(self) -> bool:
        """Тестируем подключение к WGDashboard API"""
        try:
            response = requests.get(
                f"{self.api_url}/handshake",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('status', False)
            return False
        except Exception as e:
            logger.error(f"API connection test failed: {e}")
            return False
    
    def get_available_interfaces(self) -> List[str]:
        """Получаем список доступных интерфейсов (конфигураций)"""
        try:
            response = requests.get(
                f"{self.api_url}/getWireguardConfigurations",
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == True:
                    configurations = result.get('data', [])
                    return [conf.get('Name') for conf in configurations if conf.get('Name')]
            return []
        except Exception as e:
            logger.error(f"Error getting interfaces: {e}")
            return []
    

    def get_regions(self):
        """Возвращает словарь с регионами"""
        return self._regions

    @property
    def regions(self):
        return self._regions