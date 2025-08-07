#!/usr/bin/env python3
import sys
import os
sys.path.append('/opt/smart-seller/services')

from base_service import BaseSmartSellerService

class TokenTableCreator(BaseSmartSellerService):
    def __init__(self):
        super().__init__("token-table-creator")
    
    def create_token_table(self):
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS avito_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            access_token TEXT NOT NULL,
            token_type VARCHAR(50) DEFAULT 'Bearer',
            expires_in INTEGER NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT unique_active_token UNIQUE (is_active) DEFERRABLE INITIALLY DEFERRED
        );
        
        CREATE INDEX IF NOT EXISTS idx_avito_tokens_active ON avito_tokens(is_active, expires_at);
        CREATE INDEX IF NOT EXISTS idx_avito_tokens_expires ON avito_tokens(expires_at);
        """
        
        if self.db_execute(create_table_sql):
            print("Таблица avito_tokens создана успешно")
            return True
        else:
            print("Ошибка создания таблицы avito_tokens")
            return False
    
    def run(self):
        if not self.connect_postgres():
            sys.exit(1)
        
        success = self.create_token_table()
        self.disconnect_all()
        
        if not success:
            sys.exit(1)

if __name__ == "__main__":
    creator = TokenTableCreator()
    creator.run()
