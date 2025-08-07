#!/usr/bin/env python3
import sys
import os
import requests
import json
import time
from datetime import datetime, timedelta
sys.path.append('/opt/smart-seller/services')

from base_service import BaseSmartSellerService

class AvitoTokenManager(BaseSmartSellerService):
    def __init__(self):
        super().__init__("avito-token-manager")
        self.client_id = os.getenv('AVITO_CLIENT_ID')
        self.client_secret = os.getenv('AVITO_CLIENT_SECRET')
        self.api_base_url = os.getenv('AVITO_API_BASE_URL')
        self.token_endpoint = os.getenv('AVITO_TOKEN_ENDPOINT')
        
        if not self.client_id or not self.client_secret:
            self.logger.error("AVITO_CLIENT_ID и AVITO_CLIENT_SECRET должны быть указаны!")
            sys.exit(1)
    
    def get_access_token(self):
        try:
            url = f"{self.api_base_url}{self.token_endpoint}"
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'client_credentials'
            }
            
            self.logger.info(f"Запрос нового токена к {url}")
            
            response = requests.post(url, headers=headers, data=data, timeout=30)
            
            if response.status_code == 200:
                token_data = response.json()
                
                access_token = token_data.get('access_token')
                expires_in = token_data.get('expires_in', 86400)
                token_type = token_data.get('token_type', 'Bearer')
                
                if access_token:
                    token_info = {
                        'access_token': access_token,
                        'token_type': token_type,
                        'expires_in': expires_in,
                        'expires_at': (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
                        'created_at': datetime.utcnow().isoformat()
                    }
                    
                    success = self.store_token(token_info)
                    
                    if success:
                        self.logger.info(f"Токен успешно получен и сохранен. Истекает через {expires_in} секунд")
                        return token_info
                    else:
                        self.logger.error("Ошибка сохранения токена")
                        return None
                else:
                    self.logger.error("access_token не найден в ответе")
                    return None
            else:
                self.logger.error(f"Ошибка получения токена: {response.status_code}")
                self.logger.error(f"Ответ: {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Ошибка сети при запросе токена: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при получении токена: {e}")
            return None
    
    def store_token(self, token_info):
        try:
            redis_key = "avito:access_token"
            token_json = json.dumps(token_info)
            
            ttl = token_info['expires_in'] - 300
            
            redis_success = self.cache_set(redis_key, token_json, ttl)
            
            if redis_success:
                self.logger.info(f"✅ Токен сохранен в Redis с TTL {ttl} секунд")
            else:
                self.logger.warning("⚠️ Ошибка сохранения в Redis")
            
            try:
                deactivate_result = self.db_execute(
                    "UPDATE avito_tokens SET is_active = FALSE WHERE is_active = TRUE"
                )
                
                if deactivate_result:
                    self.logger.info("✅ Старые токены деактивированы")
                else:
                    self.logger.warning("⚠️ Не удалось деактивировать старые токены (возможно, их не было)")
            except Exception as e:
                self.logger.error(f"❌ Ошибка деактивации старых токенов: {e}")
            
            try:
                expires_at_str = token_info['expires_at']
                
                db_success = self.db_execute(
                    """INSERT INTO avito_tokens (access_token, token_type, expires_in, expires_at, is_active)
                    VALUES (%s, %s, %s, %s, %s)""",
                    (
                        token_info['access_token'], 
                        token_info['token_type'], 
                        token_info['expires_in'], 
                        expires_at_str,
                        True
                    )
                )
                
                if db_success:
                    self.logger.info("✅ Токен сохранен в базе данных")
                    
                    verify_result = self.db_fetch(
                        "SELECT id, access_token FROM avito_tokens WHERE access_token = %s",
                        (token_info['access_token'],)
                    )
                    
                    if verify_result:
                        self.logger.info(f"✅ Токен проверен в БД: ID = {verify_result[0][0]}")
                    else:
                        self.logger.error("❌ Токен не найден в БД после добавления")
                        db_success = False
                else:
                    self.logger.error("❌ Ошибка сохранения в базе данных")
                    
            except Exception as e:
                self.logger.error(f"❌ Ошибка вставки токена в БД: {e}")
                db_success = False
            
            final_success = redis_success and db_success
            
            if final_success:
                self.logger.info("🎉 Токен успешно сохранен во всех хранилищах")
            else:
                self.logger.error("❌ Не все операции сохранения прошли успешно")
            
            return final_success
            
        except Exception as e:
            self.logger.error(f"❌ Критическая ошибка сохранения токена: {e}")
            return False
    
    def get_current_token(self):
        try:
            redis_key = "avito:access_token"
            cached_token = self.cache_get(redis_key)
            
            if cached_token:
                token_info = json.loads(cached_token)
                expires_at = datetime.fromisoformat(token_info['expires_at'])
                
                if datetime.utcnow() < expires_at - timedelta(minutes=5):
                    self.logger.info("Используем токен из кеша")
                    return token_info
                else:
                    self.logger.info("Токен в кеше истекает, получаем новый")
            
            db_token = self.db_fetch(
                """SELECT access_token, token_type, expires_at 
                   FROM avito_tokens 
                   WHERE is_active = TRUE 
                   AND expires_at > NOW() + INTERVAL '5 minutes'
                   ORDER BY created_at DESC 
                   LIMIT 1"""
            )
            
            if db_token:
                token_info = {
                    'access_token': db_token[0][0],
                    'token_type': db_token[0][1],
                    'expires_at': db_token[0][2].isoformat()
                }
                self.logger.info("Используем токен из базы данных")
                return token_info
            
            self.logger.info("Действующий токен не найден, получаем новый")
            return self.get_access_token()
            
        except Exception as e:
            self.logger.error(f"Ошибка получения текущего токена: {e}")
            return None
    
    def is_token_valid(self, token_info):
        if not token_info:
            return False
        
        try:
            expires_at = datetime.fromisoformat(token_info['expires_at'])
            return datetime.utcnow() < expires_at - timedelta(minutes=5)
        except:
            return False
    
    def refresh_token_if_needed(self):
        current_token = self.get_current_token()
        
        if not current_token or not self.is_token_valid(current_token):
            self.logger.info("Токен недействителен или отсутствует, получаем новый")
            new_token = self.get_access_token()
            return new_token
        else:
            self.logger.info("Текущий токен действителен")
            return current_token
    
    def run_token_refresh_scheduler(self):
        self.logger.info("Запуск планировщика обновления токенов")
        
        while self.running:
            try:
                now = datetime.now()
                
                if now.hour == 23 and now.minute == 59:
                    self.logger.info("Время ежедневного обновления токена")
                    new_token = self.get_access_token()
                    
                    if new_token:
                        self.logger.info("Ежедневное обновление токена выполнено успешно")
                    else:
                        self.logger.error("Ошибка ежедневного обновления токена")
                    
                    time.sleep(120)
                else:
                    time.sleep(60)
                    
            except KeyboardInterrupt:
                self.logger.info("Остановка планировщика по сигналу")
                break
            except Exception as e:
                self.logger.error(f"Ошибка в планировщике: {e}")
                time.sleep(60)
    
    def run(self):
        if not self.connect_all():
            sys.exit(1)
        
        self.logger.info("Запуск менеджера токенов Avito")
        
        initial_token = self.refresh_token_if_needed()
        if not initial_token:
            self.logger.error("Не удалось получить начальный токен")
            sys.exit(1)
        
        try:
            self.running = True
            self.run_token_refresh_scheduler()
        except KeyboardInterrupt:
            self.logger.info("Остановка по сигналу")
        finally:
            self.disconnect_all()

if __name__ == "__main__":
    manager = AvitoTokenManager()
    manager.run()
