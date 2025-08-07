#!/usr/bin/env python3
import sys
import os
import subprocess
from datetime import datetime
sys.path.append('/opt/smart-seller/services')

from base_service import BaseSmartSellerService

class SystemStatus(BaseSmartSellerService):
    def __init__(self):
        super().__init__("system-status")
    
    def check_services(self):
        services = [
            'avito-token-manager',
            'avito-poller', 
            'message-parser',
            'pricing-calculator',
            'admin-notifier'
        ]
        
        print("🔍 Статус микросервисов:")
        print("=" * 40)
        
        for service in services:
            try:
                result = subprocess.run(['systemctl', 'is-active', service], 
                                      capture_output=True, text=True)
                status = result.stdout.strip()
                
                if status == 'active':
                    print(f"  ✅ {service}")
                else:
                    print(f"  ❌ {service} ({status})")
                    
            except Exception as e:
                print(f"  ❓ {service} (ошибка проверки)")
        
        print()
    
    def check_token_status(self):
        print("🎫 Статус токенов:")
        print("=" * 40)
        
        try:
            if not self.connect_all():
                print("❌ Ошибка подключения к сервисам")
                return
            
            redis_key = "avito:access_token"
            cached_token = self.cache_get(redis_key)
            
            if cached_token:
                import json
                token_info = json.loads(cached_token)
                expires_at = datetime.fromisoformat(token_info['expires_at'])
                time_left = expires_at - datetime.utcnow()
                
                print(f"  ✅ Redis: {token_info['access_token'][:15]}...")
                print(f"     Истекает: {expires_at}")
                print(f"     Осталось: {time_left}")
            else:
                print("  ❌ Redis: токен не найден")
            
            db_tokens = self.db_fetch(
                """SELECT COUNT(*) FROM avito_tokens WHERE is_active = TRUE"""
            )
            
            if db_tokens and db_tokens[0][0] > 0:
                print(f"  ✅ PostgreSQL: {db_tokens[0][0]} активных токенов")
            else:
                print("  ❌ PostgreSQL: активные токены не найдены")
            
            self.disconnect_all()
            
        except Exception as e:
            print(f"  ❌ Ошибка проверки токенов: {e}")
    
    def run(self):
        print(f"📊 Статус системы Smart Seller - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        print()
        
        self.check_services()
        self.check_token_status()
        
        print("⏰ Планировщик обновления токенов:")
        print("=" * 40)
        print("  🕐 Время обновления: 23:59 МСК ежедневно")
        print("  ⚙️ Интервал проверки: каждые 60 секунд")
        print("  🔄 Backup через cron: 23:59 ежедневно")
        print("  📅 Время жизни токена: 24 часа")

if __name__ == "__main__":
    status = SystemStatus()
    status.run()
