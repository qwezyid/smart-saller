#!/usr/bin/env python3
import sys
import os
import requests
import json
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
sys.path.append('/opt/smart-seller/services')

from base_service import BaseSmartSellerService

class EnhancedAvitoPollerService(BaseSmartSellerService):
    def __init__(self):
        super().__init__("enhanced-avito-poller")
        self.exchange = os.getenv('RABBITMQ_MAIN_EXCHANGE')
        self.user_id = os.getenv('AVITO_USER_ID')
        self.polling_interval = int(os.getenv('AVITO_POLLING_INTERVAL', 30))
        self.api_timeout = int(os.getenv('AVITO_API_TIMEOUT', 30))
        self.api_base_url = 'https://api.avito.ru'
        
        if not self.user_id:
            self.logger.error("❌ AVITO_USER_ID должен быть указан!")
            sys.exit(1)
    
    def get_valid_token(self):
        """Получает действующий токен из Redis или БД"""
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
        """Универсальный метод для API запросов к Avito"""
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
                time.sleep(5)
                return None
            else:
                self.logger.error(f"❌ API ошибка: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка API запроса: {e}")
            return None
    
    def get_chats(self, limit=100):
        """Получает список активных чатов"""
        try:
            endpoint = f"/messenger/v2/accounts/{self.user_id}/chats"
            params = {
                'unread_only': 'false',  # Получаем все чаты
                'limit': limit,
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
    
    def get_all_chat_messages(self, chat_id: str, limit_per_request=100) -> List[Dict]:
        """Получает ВСЕ сообщения из чата с пагинацией и правильной хронологией"""
        all_messages = []
        offset = 0
        
        try:
            while True:
                endpoint = f"/messenger/v3/accounts/{self.user_id}/chats/{chat_id}/messages/"
                params = {
                    'limit': limit_per_request,
                    'offset': offset
                }
                
                response = self.make_avito_api_request(endpoint, params=params)
                
                if not response:
                    break
                
                # Определяем структуру ответа
                messages = []
                if isinstance(response, dict) and 'messages' in response:
                    messages = response['messages']
                elif isinstance(response, list):
                    messages = response
                
                if not messages:
                    break
                
                all_messages.extend(messages)
                
                # Если получили меньше сообщений чем лимит, значит это всё
                if len(messages) < limit_per_request:
                    break
                
                offset += limit_per_request
                time.sleep(0.5)  # Пауза между запросами
            
            # Сортируем по времени создания (от старых к новым для правильной хронологии)
            all_messages.sort(key=lambda x: x.get('created', 0))
            
            self.logger.info(f"✅ Получено {len(all_messages)} сообщений из чата {chat_id}")
            return all_messages
                    
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения всех сообщений из чата {chat_id}: {e}")
            return []
    
    def ensure_conversation_exists(self, chat_id: str, first_author_id: str = None) -> bool:
        """Обеспечивает существование записи диалога в БД"""
        try:
            existing = self.db_fetch(
                "SELECT id FROM conversations WHERE avito_conversation_id = %s",
                (chat_id,)
            )
            
            if not existing:
                # Создаём новый диалог
                author_id = first_author_id or 'unknown'
                participants = [author_id] if author_id != 'unknown' else []
                
                self.db_execute(
                    """INSERT INTO conversations (
                        avito_user_id, avito_conversation_id, current_stage, 
                        participants, ai_context
                    ) VALUES (%s, %s, %s, %s, %s)""",
                    (author_id, chat_id, 'initial', 
                     json.dumps(participants), 
                     json.dumps({"created_from_poller": True}))
                )
                self.logger.info(f"✅ Создан новый диалог: {chat_id}")
                return True
            
            return True
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка создания/проверки диалога {chat_id}: {e}")
            return False
    
    def save_message_to_db(self, conversation_id: str, message: Dict, sequence_num: int) -> bool:
        """Сохраняет сообщение в БД с правильной последовательностью"""
        try:
            direction = 'incoming' if message.get('direction') == 'in' else 'outgoing'
            content = message.get('content', {})
            message_text = content.get('text', '') if isinstance(content, dict) else str(content)
            
            # Проверяем, не существует ли уже это сообщение
            existing = self.db_fetch(
                "SELECT id FROM messages WHERE avito_message_id = %s",
                (message.get('id'),)
            )
            
            if existing:
                return True  # Сообщение уже существует
            
            # Создаём временную метку
            avito_created_at = None
            if message.get('created'):
                avito_created_at = datetime.fromtimestamp(message['created'])
            
            # Сохраняем сообщение
            success = self.db_execute(
                """INSERT INTO messages (
                    conversation_id, avito_message_id, author_id, direction, 
                    message_text, avito_created_at, sequence_number, 
                    has_attachments, processing_status
                ) VALUES (
                    (SELECT id FROM conversations WHERE avito_conversation_id = %s),
                    %s, %s, %s, %s, %s, %s, %s, %s
                )""",
                (conversation_id, message.get('id'), message.get('author_id'),
                 direction, message_text, avito_created_at, sequence_num,
                 bool(content.get('attachments') or content.get('images')),
                 'pending')
            )
            
            return success
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка сохранения сообщения: {e}")
            return False
    
    def create_context_snapshot(self, chat_id: str, messages: List[Dict]) -> bool:
        """Создает или обновляет снапшот контекста диалога"""
        try:
            # Подготавливаем хронологическую историю
            chronological_timeline = []
            for i, msg in enumerate(messages):
                content = msg.get('content', {})
                message_text = content.get('text', '') if isinstance(content, dict) else str(content)
                
                timeline_entry = {
                    'sequence': i + 1,
                    'message_id': msg.get('id'),
                    'timestamp': datetime.fromtimestamp(msg.get('created', 0)).isoformat() if msg.get('created') else None,
                    'direction': 'incoming' if msg.get('direction') == 'in' else 'outgoing',
                    'author_id': msg.get('author_id'),
                    'text': message_text,
                    'has_attachments': bool(content.get('attachments') or content.get('images'))
                }
                chronological_timeline.append(timeline_entry)
            
            # Анализируем недостающие данные для AI
            missing_data = {
                'needs_vehicle_info': True,
                'needs_route_info': True,
                'needs_timing_info': True
            }
            
            # ИСПРАВЛЕНИЕ: Проверяем существует ли уже снапшот для этого диалога
            existing_snapshot = self.db_fetch(
                """SELECT id FROM conversation_context_history 
                WHERE conversation_id = (SELECT id FROM conversations WHERE avito_conversation_id = %s)
                ORDER BY created_at DESC LIMIT 1""",
                (chat_id,)
            )
            
            if existing_snapshot:
                # ОБНОВЛЯЕМ существующий снапшот
                success = self.db_execute(
                    """UPDATE conversation_context_history SET
                    message_count = %s,
                    full_chronological_history = %s,
                    missing_data = %s,
                    next_ai_action = %s,
                    confidence_score = %s,
                    snapshot_at = CURRENT_TIMESTAMP
                    WHERE id = %s""",
                    (len(messages), json.dumps(chronological_timeline),
                    json.dumps(missing_data), 'analyze_conversation', 0.5,
                    existing_snapshot[0][0])
                )
                self.logger.info(f"✅ Обновлен снапшот контекста для {chat_id}")
            else:
                # СОЗДАЁМ новый снапшот только если его нет
                success = self.db_execute(
                    """INSERT INTO conversation_context_history (
                        conversation_id, message_count, full_chronological_history,
                        missing_data, next_ai_action, confidence_score
                    ) VALUES (
                        (SELECT id FROM conversations WHERE avito_conversation_id = %s),
                        %s, %s, %s, %s, %s
                    )""",
                    (chat_id, len(messages), json.dumps(chronological_timeline),
                    json.dumps(missing_data), 'analyze_conversation', 0.5)
                )
                self.logger.info(f"✅ Создан новый снапшот контекста для {chat_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка создания/обновления снапшота контекста: {e}")
            return False
    
    def send_to_ai_processing(self, chat_id: str, new_messages: List[Dict]) -> bool:
        """Отправляет новые сообщения на обработку AI с полным контекстом"""
        try:
            if not new_messages:
                return True
            
            # Получаем полный контекст диалога из БД
            context_data = self.db_fetch(
                """SELECT ch.full_chronological_history, c.ai_context, c.extracted_data
                FROM conversation_context_history ch
                JOIN conversations c ON ch.conversation_id = c.id
                WHERE c.avito_conversation_id = %s
                ORDER BY ch.created_at DESC
                LIMIT 1""",
                (chat_id,)
            )
            
            full_history = []
            ai_context = {}
            extracted_data = {}
            
            if context_data:
                # ИСПРАВЛЕНИЕ: проверяем тип данных перед парсингом
                history_data = context_data[0][0]
                if isinstance(history_data, str):
                    full_history = json.loads(history_data)
                elif isinstance(history_data, list):
                    full_history = history_data
                elif history_data is None:
                    full_history = []
                
                context_raw = context_data[0][1]
                if isinstance(context_raw, str):
                    ai_context = json.loads(context_raw)
                elif isinstance(context_raw, dict):
                    ai_context = context_raw
                elif context_raw is None:
                    ai_context = {}
                
                extracted_raw = context_data[0][2]
                if isinstance(extracted_raw, str):
                    extracted_data = json.loads(extracted_raw)
                elif isinstance(extracted_raw, dict):
                    extracted_data = extracted_raw
                elif extracted_raw is None:
                    extracted_data = {}
            
            # Отправляем каждое новое сообщение с полным контекстом
            for message in new_messages:
                content = message.get('content', {})
                message_text = content.get('text', '') if isinstance(content, dict) else str(content)
                
                # Создаем полную структуру для AI
                ai_message = {
                    'message_id': message.get('id'),
                    'chat_id': chat_id,
                    'author_id': message.get('author_id'),
                    'text': message_text,
                    'timestamp': datetime.fromtimestamp(message.get('created', 0)).isoformat() if message.get('created') else datetime.now().isoformat(),
                    'direction': 'incoming' if message.get('direction') == 'in' else 'outgoing',
                    'source': 'avito',
                    
                    # ПОЛНЫЙ КОНТЕКСТ ДЛЯ AI
                    'conversation_context': {
                        'full_chronological_history': full_history,  # Вся история диалога
                        'current_ai_context': ai_context,           # Текущий контекст AI
                        'extracted_data': extracted_data,           # Уже извлеченные данные
                        'total_messages': len(full_history),
                        'conversation_stage': 'active',
                        'requires_processing': True
                    }
                }
                
                # Отправляем в RabbitMQ для обработки AI
                success = self.publish_message(
                    exchange=self.exchange,
                    routing_key='ai.message.new_with_context',
                    message=ai_message
                )
                
                if success:
                    self.logger.info(f"✅ Отправлено сообщение с контекстом: {message_text[:30]}...")
                else:
                    self.logger.error(f"❌ Ошибка отправки сообщения в RabbitMQ")
                    return False
                
                time.sleep(0.1)  # Небольшая пауза между сообщениями
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки на AI обработку: {e}")
            return False
    
    def process_chat_with_full_context(self, chat_id: str) -> int:
        """Обрабатывает чат с получением полного контекста"""
        try:
            self.logger.info(f"🔄 Обработка чата {chat_id} с полным контекстом...")
            
            # Получаем ВСЕ сообщения из чата
            all_messages = self.get_all_chat_messages(chat_id)
            
            if not all_messages:
                self.logger.warning(f"⚠️ Нет сообщений в чате {chat_id}")
                return 0
            
            # Обеспечиваем существование диалога
            first_author = all_messages[0].get('author_id') if all_messages else None
            if not self.ensure_conversation_exists(chat_id, first_author):
                return 0
            
            # Получаем уже обработанные сообщения из БД
            processed_message_ids = set()
            db_messages = self.db_fetch(
                """SELECT avito_message_id FROM messages 
                   WHERE conversation_id = (
                       SELECT id FROM conversations WHERE avito_conversation_id = %s
                   )""",
                (chat_id,)
            )
            
            if db_messages:
                processed_message_ids = {row[0] for row in db_messages if row[0]}
            
            # Находим новые сообщения
            new_messages = []
            for i, message in enumerate(all_messages):
                message_id = message.get('id')
                if message_id and message_id not in processed_message_ids:
                    # Сохраняем новое сообщение в БД
                    if self.save_message_to_db(chat_id, message, i + 1):
                        new_messages.append(message)
            
            # Создаем/обновляем снапшот контекста
            self.create_context_snapshot(chat_id, all_messages)
            
            # Отправляем только новые входящие сообщения на AI обработку
            incoming_new_messages = [
                msg for msg in new_messages 
                if msg.get('direction') == 'in' and msg.get('content', {}).get('text')
            ]
            
            if incoming_new_messages:
                self.send_to_ai_processing(chat_id, incoming_new_messages)
                self.logger.info(f"✅ Обработано {len(incoming_new_messages)} новых сообщений в чате {chat_id}")
                return len(incoming_new_messages)
            else:
                self.logger.info(f"ℹ️ Нет новых входящих сообщений в чате {chat_id}")
                return 0
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки чата {chat_id}: {e}")
            return 0
    
    def poll_with_full_context(self):
        """Основной метод polling с полным контекстом"""
        try:
            self.logger.info("🔍 Начинаем polling с полным контекстом...")
            
            chats = self.get_chats(limit=50)
            
            if not chats:
                self.logger.info("ℹ️ Активных чатов не найдено")
                return
            
            total_processed = 0
            
            for chat in chats:
                chat_id = chat.get('id')
                if not chat_id:
                    continue
                
                try:
                    processed_count = self.process_chat_with_full_context(chat_id)
                    total_processed += processed_count
                    time.sleep(1)  # Пауза между чатами
                    
                except Exception as e:
                    self.logger.error(f"❌ Ошибка обработки чата {chat_id}: {e}")
                    continue
            
            if total_processed > 0:
                self.logger.info(f"🎉 Всего обработано новых сообщений: {total_processed}")
            else:
                self.logger.info("ℹ️ Новых сообщений для обработки не найдено")
                
        except Exception as e:
            self.logger.error(f"❌ Критическая ошибка в polling: {e}")
    
    def run(self):
        """Запуск enhanced poller service"""
        if not self.connect_all():
            self.logger.error("❌ Не удалось подключиться к сервисам")
            sys.exit(1)
        
        self.logger.info("🚀 Запуск Enhanced Avito Poller с полным контекстом...")
        self.logger.info(f"📋 User ID: {self.user_id}")
        self.logger.info(f"⏱️ Интервал polling: {self.polling_interval} секунд")
        self.logger.info("🧠 Режим: Полный контекст диалогов для AI")
        
        try:
            self.running = True
            while self.running:
                start_time = time.time()
                
                self.poll_with_full_context()
                
                # Вычисляем время выполнения
                execution_time = time.time() - start_time
                sleep_time = max(0, self.polling_interval - execution_time)
                
                if sleep_time > 0:
                    self.logger.info(f"⏰ Следующий опрос через {sleep_time:.1f} секунд")
                    time.sleep(sleep_time)
                else:
                    self.logger.warning(f"⚠️ Обработка заняла {execution_time:.1f}с (больше интервала)")
                
        except KeyboardInterrupt:
            self.logger.info("⚡ Остановка по сигналу")
        finally:
            self.disconnect_all()

if __name__ == "__main__":
    service = EnhancedAvitoPollerService()
    service.run()
