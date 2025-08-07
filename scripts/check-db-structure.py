#!/usr/bin/env python3
import sys
import os
sys.path.append('/opt/smart-seller/services')

from base_service import BaseSmartSellerService

class DatabaseChecker(BaseSmartSellerService):
    def __init__(self):
        super().__init__("db-checker")
    
    def check_database(self):
        try:
            tables = self.db_fetch(
                """SELECT table_name FROM information_schema.tables 
                   WHERE table_schema = 'public' AND table_name LIKE '%token%'"""
            )
            
            print("📊 Таблицы с токенами в базе данных:")
            if tables:
                for table in tables:
                    print(f"  ✅ {table[0]}")
            else:
                print("  ❌ Таблицы с токенами не найдены")
            
            print()
            
            try:
                columns = self.db_fetch(
                    """SELECT column_name, data_type, is_nullable 
                       FROM information_schema.columns 
                       WHERE table_name = 'avito_tokens'
                       ORDER BY ordinal_position"""
                )
                
                if columns:
                    print("📋 Структура таблицы avito_tokens:")
                    for col in columns:
                        print(f"  - {col[0]} ({col[1]}) {'NULL' if col[2] == 'YES' else 'NOT NULL'}")
                else:
                    print("❌ Таблица avito_tokens не существует")
                    return False
                    
            except Exception as e:
                print(f"❌ Ошибка проверки структуры таблицы: {e}")
                return False
            
            print()
            
            try:
                count = self.db_fetch("SELECT COUNT(*) FROM avito_tokens")
                print(f"📈 Количество записей в avito_tokens: {count[0][0] if count else 0}")
                
                if count and count[0][0] > 0:
                    recent = self.db_fetch(
                        """SELECT access_token, created_at, is_active, expires_at 
                           FROM avito_tokens 
                           ORDER BY created_at DESC 
                           LIMIT 3"""
                    )
                    
                    print("📝 Последние записи:")
                    for i, rec in enumerate(recent):
                        print(f"  {i+1}. Токен: {rec[0][:15]}...")
                        print(f"     Создан: {rec[1]}")
                        print(f"     Активен: {rec[2]}")
                        print(f"     Истекает: {rec[3]}")
                        print()
                        
            except Exception as e:
                print(f"❌ Ошибка проверки данных: {e}")
                return False
            
            return True
            
        except Exception as e:
            print(f"❌ Ошибка проверки базы данных: {e}")
            return False
    
    def run(self):
        if not self.connect_postgres():
            print("❌ Ошибка подключения к PostgreSQL")
            sys.exit(1)
        
        success = self.check_database()
        self.disconnect_all()
        
        return success

if __name__ == "__main__":
    checker = DatabaseChecker()
    success = checker.run()
    sys.exit(0 if success else 1)
