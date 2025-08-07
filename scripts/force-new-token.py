#!/usr/bin/env python3
import sys
import os
sys.path.append('/opt/smart-seller/services')

from base_service import BaseSmartSellerService
import requests
import json
from datetime import datetime, timedelta

class ForceTokenRefresh(BaseSmartSellerService):
    def __init__(self):
        super().__init__("force-token-refresh")
        self.client_id = os.getenv('AVITO_CLIENT_ID')
        self.client_secret = os.getenv('AVITO_CLIENT_SECRET')
        
    def force_new_token(self):
        try:
            print("🔄 Принудительное получение нового токена...")
            
            url = "https://api.avito.ru/token"
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'client_credentials'
            }
            
            response = requests.post(url, headers=headers, data=data, timeout=30)
            
            if response.status_code == 200:
                token_data = response.json()
                
                token_info = {
                    'access_token': token_data['access_token'],
                    'token_type': token_data.get('token_type', 'Bearer'),
                    'expires_in': token_data.get('expires_in', 86400),
                    'expires_at': (datetime.utcnow() + timedelta(seconds=token_data.get('expires_in', 86400))).isoformat(),
                    'created_at': datetime.utcnow().isoformat()
                }
                
                print(f"✅ Токен получен: {token_info['access_token'][:20]}...")
                
                redis_key = "avito:access_token"
                redis_success = self.cache_set(redis_key, json.dumps(token_info), token_info['expires_in'] - 300)
                
                if redis_success:
                    print("✅ Токен сохранен в Redis")
                
                self.db_execute("UPDATE avito_tokens SET is_active = FALSE WHERE is_active = TRUE")
                
                db_success = self.db_execute(
                    """INSERT INTO avito_tokens (access_token, token_type, expires_in, expires_at, is_active)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (token_info['access_token'], token_info['token_type'], 
                     token_info['expires_in'], token_info['expires_at'], True)
                )
                
                if db_success:
                    print("✅ Токен сохранен в PostgreSQL")
                
                return redis_success and db_success
            else:
                print(f"❌ Ошибка получения токена: {response.status_code}")
                print(f"Ответ: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return False
    
    def run(self):
        if not self.connect_all():
            print("❌ Ошибка подключения к сервисам")
            sys.exit(1)
        
        success = self.force_new_token()
        self.disconnect_all()
        
        return success

if __name__ == "__main__":
    refresher = ForceTokenRefresh()
    success = refresher.run()
    sys.exit(0 if success else 1)
