#!/usr/bin/env python3
import sys
import os
sys.path.append('/opt/smart-seller/services')

from base_service import BaseSmartSellerService

class TokenTableRecreator(BaseSmartSellerService):
    def __init__(self):
        super().__init__("token-table-recreator")
    
    def recreate_table(self):
        try:
            print("🗑️ Удаление старой таблицы...")
            self.db_execute("DROP TABLE IF EXISTS avito_tokens CASCADE;")
            
            print("🔨 Создание новой таблицы...")
            create_sql = """
            CREATE TABLE avito_tokens (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                access_token TEXT NOT NULL,
                token_type VARCHAR(50) NOT NULL DEFAULT 'Bearer',
                expires_in INTEGER NOT NULL,
                expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX idx_avito_tokens_active ON avito_tokens(is_active) WHERE is_active = TRUE;
            CREATE INDEX idx_avito_tokens_expires ON avito_tokens(expires_at);
            CREATE INDEX idx_avito_tokens_created ON avito_tokens(created_at);
            """
            
            success = self.db_execute(create_sql)
            
            if success:
                print("✅ Таблица avito_tokens успешно создана")
                
                test_insert = self.db_execute(
                    """INSERT INTO avito_tokens (access_token, token_type, expires_in, expires_at, is_active)
                       VALUES (%s, %s, %s, %s, %s)""",
                    ('test_token_12345', 'Bearer', 86400, '2025-08-08 12:00:00+00', False)
                )
                
                if test_insert:
                    print("✅ Тестовая запись добавлена успешно")
                    
                    test_count = self.db_fetch("SELECT COUNT(*) FROM avito_tokens")
                    print(f"📊 Записей в таблице: {test_count[0][0] if test_count else 0}")
                    
                    self.db_execute("DELETE FROM avito_tokens WHERE access_token = 'test_token_12345'")
                    print("🧹 Тестовая запись удалена")
                    
                    return True
                else:
                    print("❌ Ошибка добавления тестовой записи")
                    return False
            else:
                print("❌ Ошибка создания таблицы")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка пересоздания таблицы: {e}")
            return False
    
    def run(self):
        if not self.connect_postgres():
            print("❌ Ошибка подключения к PostgreSQL")
            sys.exit(1)
        
        success = self.recreate_table()
        self.disconnect_all()
        
        if not success:
            sys.exit(1)
        
        print("🎉 Таблица готова к использованию!")

if __name__ == "__main__":
    recreator = TokenTableRecreator()
    recreator.run()
