#!/usr/bin/env python3
import sys
import os
sys.path.append('/opt/smart-seller/services')

from base_service import BaseSmartSellerService

class TokenTableFixer(BaseSmartSellerService):
    def __init__(self):
        super().__init__("token-table-fixer")
    
    def fix_token_table(self):
        try:
            self.db_execute("DROP TABLE IF EXISTS avito_tokens;")
            print("Старая таблица удалена")
            
            create_table_sql = """
            CREATE TABLE avito_tokens (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                access_token TEXT NOT NULL,
                token_type VARCHAR(50) DEFAULT 'Bearer',
                expires_in INTEGER NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                is_active BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX idx_avito_tokens_active ON avito_tokens(is_active, expires_at);
            CREATE INDEX idx_avito_tokens_expires ON avito_tokens(expires_at);
            """
            
            if self.db_execute(create_table_sql):
                print("✅ Новая таблица avito_tokens создана успешно")
                return True
            else:
                print("❌ Ошибка создания таблицы avito_tokens")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка исправления таблицы: {e}")
            return False
    
    def run(self):
        if not self.connect_postgres():
            sys.exit(1)
        
        success = self.fix_token_table()
        self.disconnect_all()
        
        if not success:
            sys.exit(1)

if __name__ == "__main__":
    fixer = TokenTableFixer()
    fixer.run()
