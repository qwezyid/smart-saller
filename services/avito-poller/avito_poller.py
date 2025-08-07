#!/usr/bin/env python3
import sys
import os
import requests
import json
import time
from datetime import datetime, timedelta
sys.path.append('/opt/smart-seller/services')

from base_service import BaseSmartSellerService

class AvitoPollerService(BaseSmartSellerService):
    def __init__(self):
        super().__init__("avito-poller")
        self.exchange = os.getenv('RABBITMQ_MAIN_EXCHANGE')
        self.user_id = os.getenv('AVITO_USER_ID')
        self.polling_interval = int(os.getenv('AVITO_POLLING_INTERVAL', 30))
        self.api_timeout = int(os.getenv('AVITO_API_TIMEOUT', 30))
        self.api_base_url = 'https://api.avito.ru'
        
        if not self.user_id:
            self.logger.error("❌ AVITO_USER_ID должен быть указан!")
            sys.exit(1)
    
    def get_valid_token(self):
        try:
            redis_key = "avito:access_token"
            cached_token = self.cache_get(redis_key)
            
            if cached_token:
                token_info = json.loads(cached_token)
                return token_info['access_token']
            
            db_token = self.db_fetch(
                """SELECT access_token FROM avito_tokens 
                   WHERE is_active = TRUE 
                   AND expires_at > NOW() + INTERVAL '5 minutes'
                   ORDER BY created_at DESC 
                   LIMIT 1"""
            )
            
            if db_token:
                return db_token[0][0]
            
            self.logger.error("❌ Действующий токен не найден!")
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения токена: {e}")
            return None
    
    def make_avito_api_request(self, endpoint, method='GET', params=None):
        try:
            token = self.get_valid_token()
            if not token:
                self.logger.error("❌ Нет действующего токена для API запроса")
                return None
            
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            url = f"{self.api_base_url}{endpoint}"
            
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=self.api_timeout)
            else:
                self.logger.error(f"❌ Неподдерживаемый HTTP метод: {method}")
                return None
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                self.logger.error("❌ Токен недействителен, требуется обновление")
                return None
            elif response.status_code == 429:
                self.logger.warning("⚠️ Rate limit достигнут")
                return None
            else:
                self.logger.error(f"❌ API ошибка: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка API запроса: {e}")
            return None
    
    def get_chats(self):
        try:
            endpoint = f"/messenger/v2/accounts/{self.user_id}/chats"
            params = {
                'unread_only': 'false',
                'limit': 100,
                'offset': 0
            }
            
            response = self.make_avito_api_request(endpoint, params=params)
            
            if response and 'chats' in response:
                self.logger.info(f"✅ Получено {len(response['chats'])} чатов")
                return response['chats']
            else:
                self.logger.warning("⚠️ Чаты не найдены или ошибка API")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения чатов: {e}")
            return []
    
    def get_chat_messages(self, chat_id):
        try:
            endpoint = f"/messenger/v3/accounts/{self.user_id}/chats/{chat_id}/messages/"
            params = {
                'limit': 50,
                'offset': 0
            }
            
            response = self.make_avito_api_request(endpoint, params=params)
            
            if response:
                # Проверяем структуру ответа
                if isinstance(response, dict) and 'messages' in response:
                    messages = response['messages']
                    self.logger.info(f"✅ Получено {len(messages)} сообщений из чата {chat_id}")
                    return messages
                elif isinstance(response, list):
                    self.logger.info(f"✅ Получено {len(response)} сообщений из чата {chat_id} (прямой список)")
                    return response
                else:
                    self.logger.warning(f"⚠️ Неожиданная структура ответа: {type(response)}")
                    self.logger.warning(f"⚠️ Содержимое: {str(response)[:200]}...")
                    return []
            else:
                self.logger.warning(f"⚠️ Пустой ответ для чата {chat_id}")
                return []
                    
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения сообщений из чата {chat_id}: {e}")
            return []
    
    def process_message(self, message, chat_id):
        try:
            # Проверяем, что это входящее сообщение с текстом
            direction = message.get('direction', 'unknown')
            content = message.get('content', {})
            message_id = message.get('id')
            author_id = message.get('author_id')
            
            self.logger.info(f"📍 Сообщение {message_id}: direction={direction}, author={author_id}")
            
            # Обрабатываем только входящие сообщения (от клиентов)
            if direction == 'in' and isinstance(content, dict) and content.get('text'):
                text = content['text']
                
                self.logger.info(f"📝 Входящее сообщение: {text[:50]}...")
                
                # Проверяем существование диалога
                conversation_exists = self.db_fetch(
                    "SELECT id FROM conversations WHERE avito_conversation_id = %s",
                    (chat_id,)
                )
                
                if not conversation_exists:
                    self.db_execute(
                        """INSERT INTO conversations (avito_user_id, avito_conversation_id, current_stage) 
                        VALUES (%s, %s, %s)""",
                        (str(author_id or 'unknown'), chat_id, 'initial')
                    )
                    self.logger.info(f"✅ Создан новый диалог: {chat_id}")
                
                # Проверяем, не обработано ли уже это сообщение
                processed_key = f"processed_message:{message_id}"
                if self.cache_get(processed_key):
                    self.logger.info(f"ℹ️ Сообщение {message_id} уже обработано")
                    return False
                
                # Создаем структуру сообщения для отправки
                message_data = {
                    'id': message_id,
                    'chat_id': chat_id,
                    'author_id': author_id,
                    'text': text,
                    'timestamp': datetime.fromtimestamp(message['created']).isoformat() if message.get('created') else datetime.now().isoformat(),
                    'direction': 'incoming',
                    'source': 'avito'
                }
                
                # Отправляем в RabbitMQ
                success = self.publish_message(
                    exchange=self.exchange,
                    routing_key='avito.message.new',
                    message=message_data
                )
                
                if success:
                    # Сохраняем в базу данных
                    self.db_execute(
                        """INSERT INTO messages (conversation_id, direction, message_text) 
                        VALUES ((SELECT id FROM conversations WHERE avito_conversation_id = %s), %s, %s)""",
                        (chat_id, 'incoming', text)
                    )
                    
                    # Помечаем как обработанное
                    self.cache_set(processed_key, 'true', 3600)
                    self.logger.info(f"✅ Обработано входящее сообщение: {text[:30]}...")
                    return True
                else:
                    self.logger.error(f"❌ Ошибка отправки сообщения в RabbitMQ")
                    return False
            else:
                # Логируем исходящие сообщения для понимания, но не обрабатываем
                if direction == 'out':
                    self.logger.info(f"📤 Исходящее сообщение (пропускаем): {content.get('text', 'без текста')[:30]}...")
                else:
                    self.logger.info(f"ℹ️ Пропускаем сообщение: direction={direction}, тип content={type(content)}")
                return False
                    
        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки сообщения: {e}")
            self.logger.error(f"❌ Содержимое сообщения: {str(message)[:200]}...")
            return False
    
    def poll_messages(self):
        try:
            chats = self.get_chats()
            
            if not chats:
                self.logger.info("ℹ️ Новых чатов не найдено")
                return
            
            processed_count = 0
            
            for chat in chats:
                chat_id = chat.get('id')
                if not chat_id:
                    continue
                
                messages = self.get_chat_messages(chat_id)
                
                for message in messages:
                    if self.process_message(message, chat_id):
                        processed_count += 1
                
                time.sleep(1)
            
            if processed_count > 0:
                self.logger.info(f"🎉 Обработано {processed_count} новых сообщений")
            else:
                self.logger.info("ℹ️ Новых сообщений не найдено")
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка в poll_messages: {e}")
    
    def run(self):
        if not self.connect_all():
            self.logger.error("❌ Не удалось подключиться к сервисам")
            sys.exit(1)
        
        self.logger.info("🚀 Запуск Avito Poller...")
        self.logger.info(f"📋 User ID: {self.user_id}")
        self.logger.info(f"⏱️ Интервал polling: {self.polling_interval} секунд")
        
        try:
            self.running = True
            while self.running:
                self.poll_messages()
                time.sleep(self.polling_interval)
                
        except KeyboardInterrupt:
            self.logger.info("⚡ Остановка по сигналу")
        finally:
            self.disconnect_all()

if __name__ == "__main__":
    service = AvitoPollerService()
    service.run()
