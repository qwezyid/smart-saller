#!/usr/bin/env python3
import sys
import os
sys.path.append('/opt/smart-seller/services')

from base_service import BaseSmartSellerService

class DatabaseSchemaCreator(BaseSmartSellerService):
    def __init__(self):
        super().__init__("database-schema")
    
    def create_tables(self):
        tables = [
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                avito_user_id VARCHAR(255) NOT NULL,
                avito_conversation_id VARCHAR(255) UNIQUE NOT NULL,
                current_stage VARCHAR(50) DEFAULT 'initial',
                extracted_params JSONB DEFAULT '{}',
                missing_params TEXT[] DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS messages (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                conversation_id UUID REFERENCES conversations(id),
                direction VARCHAR(20) CHECK (direction IN ('incoming', 'outgoing')),
                message_text TEXT NOT NULL,
                processed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS deals (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                conversation_id UUID REFERENCES conversations(id),
                calculated_price DECIMAL(10,2),
                final_price DECIMAL(10,2),
                status VARCHAR(50) DEFAULT 'calculating',
                admin_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS pricing_rules (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                route_from VARCHAR(100) NOT NULL,
                route_to VARCHAR(100) NOT NULL,
                service_type VARCHAR(100) NOT NULL,
                base_price DECIMAL(10,2) NOT NULL,
                modifiers JSONB DEFAULT '{}',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS admin_users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                telegram_user_id BIGINT UNIQUE NOT NULL,
                username VARCHAR(255),
                is_active BOOLEAN DEFAULT TRUE,
                permissions JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_conversations_avito_id ON conversations(avito_conversation_id);
            CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_deals_conversation_id ON deals(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_pricing_rules_route ON pricing_rules(route_from, route_to);
            """
        ]
        
        for table_sql in tables:
            if self.db_execute(table_sql.strip()):
                print(f"✅ Таблица создана/обновлена успешно")
            else:
                print(f"❌ Ошибка создания таблицы")
                return False
        
        return True
    
    def insert_initial_data(self):
        pricing_data = [
            ("москва", "спб", "car_transport", 25000.00, '{"urgency": 1.3, "weekend": 1.15}'),
            ("москва", "казань", "car_transport", 18000.00, '{"urgency": 1.3, "weekend": 1.15}'),
            ("москва", "екатеринбург", "car_transport", 30000.00, '{"urgency": 1.3, "weekend": 1.15}'),
            ("спб", "москва", "car_transport", 25000.00, '{"urgency": 1.3, "weekend": 1.15}'),
        ]
        
        for route_from, route_to, service_type, base_price, modifiers in pricing_data:
            check_query = "SELECT id FROM pricing_rules WHERE route_from = %s AND route_to = %s AND service_type = %s"
            existing = self.db_fetch(check_query, (route_from, route_to, service_type))
            
            if not existing:
                insert_query = """
                INSERT INTO pricing_rules (route_from, route_to, service_type, base_price, modifiers)
                VALUES (%s, %s, %s, %s, %s)
                """
                if self.db_execute(insert_query, (route_from, route_to, service_type, base_price, modifiers)):
                    print(f"✅ Добавлен тариф: {route_from} -> {route_to}")
                else:
                    print(f"❌ Ошибка добавления тарифа: {route_from} -> {route_to}")
            else:
                print(f"ℹ️ Тариф уже существует: {route_from} -> {route_to}")
        
        return True
    
    def run(self):
        if not self.connect_postgres():
            sys.exit(1)
        
        print("🗄️ Создание схемы базы данных...")
        
        if self.create_tables():
            print("✅ Схема базы данных создана успешно")
        else:
            print("❌ Ошибка создания схемы")
            sys.exit(1)
        
        print("📊 Добавление начальных данных...")
        
        if self.insert_initial_data():
            print("✅ Начальные данные добавлены")
        else:
            print("❌ Ошибка добавления данных")
        
        self.disconnect_all()
        print("🎉 Инициализация базы данных завершена!")

if __name__ == "__main__":
    creator = DatabaseSchemaCreator()
    creator.run()
