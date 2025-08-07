#!/usr/bin/env python3
import sys
import os
import json
sys.path.append('/opt/smart-seller/services')

from base_service import BaseSmartSellerService

class AvitoTokenUtility(BaseSmartSellerService):
    def __init__(self):
        super().__init__("avito-token-utility")
    
    def get_token_info(self):
        try:
            redis_key = "avito:access_token"
            cached_token = self.cache_get(redis_key)
            
            if cached_token:
                token_info = json.loads(cached_token)
                print("Токен из Redis:")
                print(f"  Access Token: {token_info['access_token'][:20]}...")
                print(f"  Token Type: {token_info['token_type']}")
                print(f"  Expires At: {token_info['expires_at']}")
                return token_info['access_token']
            
            db_token = self.db_fetch(
                """SELECT access_token, token_type, expires_at 
                   FROM avito_tokens 
                   WHERE is_active = TRUE 
                   ORDER BY created_at DESC 
                   LIMIT 1"""
            )
            
            if db_token:
                print("Токен из базы данных:")
                print(f"  Access Token: {db_token[0][0][:20]}...")
                print(f"  Token Type: {db_token[0][1]}")
                print(f"  Expires At: {db_token[0][2]}")
                return db_token[0][0]
            
            print("Токен не найден")
            return None
            
        except Exception as e:
            print(f"Ошибка получения токена: {e}")
            return None
    
    def run(self):
        if not self.connect_all():
            sys.exit(1)
        
        token = self.get_token_info()
        self.disconnect_all()
        
        if token:
            return token
        else:
            sys.exit(1)

if __name__ == "__main__":
    utility = AvitoTokenUtility()
    token = utility.run()
    if token:
        print(f"\nПолный токен: {token}")
