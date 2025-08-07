#!/usr/bin/env python3
import sys
import os
import json
from datetime import datetime, timedelta
sys.path.append('/opt/smart-seller/services')

from base_service import BaseSmartSellerService

class TokenChecker(BaseSmartSellerService):
    def __init__(self):
        super().__init__("token-checker")
    
    def check_token_status(self):
        print(f"Проверка токенов Avito - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 50)
        
        try:
            redis_key = "avito:access_token"
            cached_token = self.cache_get(redis_key)
            
            if cached_token:
                token_info = json.loads(cached_token)
                expires_at = datetime.fromisoformat(token_info['expires_at'])
                time_left = expires_at - datetime.utcnow()
                
                print(f"✅ Redis токен найден:")
                print(f"  Токен: {token_info['access_token'][:20]}...")
                print(f"  Истекает: {token_info['expires_at']}")
                print(f"  Осталось: {time_left}")
                print(f"  Статус: {'✅ Действителен' if time_left > timedelta(minutes=5) else '⚠️ Истекает'}")
            else:
                print("❌ Токен в Redis не найден")
            
            print()
            
            db_tokens = self.db_fetch(
                """SELECT access_token, expires_at, created_at, is_active
                   FROM avito_tokens 
                   ORDER BY created_at DESC 
                   LIMIT 5"""
            )
            
            if db_tokens:
                print("📊 База данных токенов:")
                for i, token in enumerate(db_tokens):
                    status = "🟢 Активный" if token[3] else "🔴 Неактивный"
                    expires_at = token[1]
                    time_left = expires_at - datetime.utcnow()
                    
                    print(f"  {i+1}. Токен: {token[0][:20]}...")
                    print(f"     Создан: {token[2]}")
                    print(f"     Истекает: {expires_at}")
                    print(f"     Осталось: {time_left}")
                    print(f"     Статус: {status}")
                    print()
            else:
                print("❌ Токены в базе данных не найдены")
                
        except Exception as e:
            print(f"❌ Ошибка проверки токенов: {e}")
            return False
        
        return True
    
    def run(self):
        if not self.connect_all():
            print("❌ Ошибка подключения к сервисам")
            sys.exit(1)
        
        success = self.check_token_status()
        self.disconnect_all()
        
        return success

if __name__ == "__main__":
    checker = TokenChecker()
    success = checker.run()
    sys.exit(0 if success else 1)
