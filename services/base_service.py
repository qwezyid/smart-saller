#!/usr/bin/env python3
import pika
import redis
import psycopg2
import json
import logging
import os
import sys
import signal
from dotenv import load_dotenv
from typing import Callable, Dict, Any, Optional, List
from datetime import datetime

class BaseSmartSellerService:
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.rabbitmq_connection = None
        self.rabbitmq_channel = None
        self.redis_client = None
        self.postgres_connection = None
        self.running = False
        
        logging.basicConfig(
            level=logging.INFO,
            format=f'%(asctime)s - {service_name} - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f'/opt/smart-seller/logs/{service_name}.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(service_name)
        
        load_dotenv('/opt/smart-seller/config/services-config.env')
        
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        self.logger.info(f"Получен сигнал {signum}, завершаем работу...")
        self.running = False
    
    def connect_rabbitmq(self):
        try:
            credentials = pika.PlainCredentials(
                os.getenv('RABBITMQ_USERNAME'),
                os.getenv('RABBITMQ_PASSWORD')
            )
            
            parameters = pika.ConnectionParameters(
                host=os.getenv('RABBITMQ_HOST'),
                port=int(os.getenv('RABBITMQ_PORT')),
                virtual_host=os.getenv('RABBITMQ_VHOST'),
                credentials=credentials,
                heartbeat=600,
                connection_attempts=3,
                retry_delay=2
            )
            
            self.rabbitmq_connection = pika.BlockingConnection(parameters)
            self.rabbitmq_channel = self.rabbitmq_connection.channel()
            
            self.rabbitmq_channel.basic_qos(
                prefetch_count=int(os.getenv('RABBITMQ_PREFETCH_COUNT', 10))
            )
            
            self.logger.info("✅ RabbitMQ подключение установлено")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка подключения к RabbitMQ: {e}")
            return False
    
    def connect_redis(self):
        try:
            self.redis_client = redis.Redis(
                host=os.getenv('REDIS_HOST'),
                port=int(os.getenv('REDIS_PORT')),
                username=os.getenv('REDIS_USERNAME'),
                password=os.getenv('REDIS_PASSWORD'),
                db=int(os.getenv('REDIS_DB', 0)),
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            
            self.redis_client.ping()
            self.logger.info("✅ Redis подключение установлено")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка подключения к Redis: {e}")
            return False
    
    def connect_postgres(self):
        try:
            connection_string = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
            
            self.postgres_connection = psycopg2.connect(
                connection_string,
                connect_timeout=10
            )
            
            cursor = self.postgres_connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            
            self.logger.info("✅ PostgreSQL подключение установлено")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка подключения к PostgreSQL: {e}")
            return False
    
    def connect_all(self):
        rabbitmq_ok = self.connect_rabbitmq()
        redis_ok = self.connect_redis()
        postgres_ok = self.connect_postgres()
        
        return rabbitmq_ok and redis_ok and postgres_ok
    
    def disconnect_all(self):
        try:
            if self.rabbitmq_connection and not self.rabbitmq_connection.is_closed:
                self.rabbitmq_connection.close()
                self.logger.info("RabbitMQ отключен")
        except Exception as e:
            self.logger.error(f"Ошибка отключения RabbitMQ: {e}")
        
        try:
            if self.redis_client:
                self.redis_client.close()
                self.logger.info("Redis отключен")
        except Exception as e:
            self.logger.error(f"Ошибка отключения Redis: {e}")
        
        try:
            if self.postgres_connection:
                self.postgres_connection.close()
                self.logger.info("PostgreSQL отключен")
        except Exception as e:
            self.logger.error(f"Ошибка отключения PostgreSQL: {e}")
    
    def publish_message(self, exchange: str, routing_key: str, message: Dict[Any, Any]):
        try:
            enriched_message = {
                'timestamp': datetime.utcnow().isoformat(),
                'service': self.service_name,
                'data': message
            }
            
            self.rabbitmq_channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=json.dumps(enriched_message, ensure_ascii=False),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type='application/json'
                )
            )
            
            self.logger.info(f"📤 Сообщение отправлено: {routing_key}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки сообщения: {e}")
            return False

    def publish_messages_batch(self, exchange: str, routing_key: str, messages: List[Dict[Any, Any]]):
        try:
            if not messages:
                return True

            self.rabbitmq_channel.tx_select()

            enriched_message = {
                'timestamp': datetime.utcnow().isoformat(),
                'service': self.service_name,
                'data': messages
            }

            self.rabbitmq_channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=json.dumps(enriched_message, ensure_ascii=False),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type='application/json'
                )
            )

            self.rabbitmq_channel.tx_commit()
            self.logger.info(f"📤 Отправлен пакет сообщений: {len(messages)}")
            return True

        except Exception as e:
            try:
                self.rabbitmq_channel.tx_rollback()
            except Exception:
                pass
            self.logger.error(f"❌ Ошибка отправки пакетных сообщений: {e}")
            return False
    
    def consume_messages(self, queue: str, callback: Callable):
        try:
            def wrapper(ch, method, properties, body):
                try:
                    message = json.loads(body.decode('utf-8'))
                    self.logger.info(f"📥 Получено сообщение из {queue}")

                    data = message.get('data') if isinstance(message, dict) else None
                    if isinstance(data, list):
                        all_success = True
                        for item in data:
                            single_message = {**message, 'data': item}
                            if not callback(single_message):
                                all_success = False
                                break
                        if all_success:
                            ch.basic_ack(delivery_tag=method.delivery_tag)
                            self.logger.info("✅ Пакет сообщений обработан")
                        else:
                            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                            self.logger.error("❌ Ошибка обработки сообщения из пакета")
                    else:
                        success = callback(message)
                        if success:
                            ch.basic_ack(delivery_tag=method.delivery_tag)
                            self.logger.info("✅ Сообщение обработано")
                        else:
                            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                            self.logger.error("❌ Ошибка обработки сообщения")

                except Exception as e:
                    self.logger.error(f"❌ Ошибка в обработчике сообщений: {e}")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            
            self.rabbitmq_channel.basic_consume(
                queue=queue,
                on_message_callback=wrapper
            )
            
            self.logger.info(f"🎧 Начинаем прослушивание очереди: {queue}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка настройки потребителя: {e}")
            return False
    
    def start_consuming(self):
        try:
            self.running = True
            self.logger.info("🚀 Сервис запущен")
            
            while self.running:
                try:
                    self.rabbitmq_connection.process_data_events(time_limit=1)
                except Exception as e:
                    self.logger.error(f"❌ Ошибка обработки событий: {e}")
                    break
            
            self.logger.info("🛑 Сервис остановлен")
            
        except KeyboardInterrupt:
            self.logger.info("⚡ Получен сигнал прерывания")
        finally:
            self.disconnect_all()
    
    def cache_set(self, key: str, value: str, ttl: int = 3600):
        try:
            self.redis_client.setex(key, ttl, value)
            return True
        except Exception as e:
            self.logger.error(f"Ошибка записи в кеш: {e}")
            return False
    
    def cache_get(self, key: str) -> Optional[str]:
        try:
            return self.redis_client.get(key)
        except Exception as e:
            self.logger.error(f"Ошибка чтения из кеша: {e}")
            return None
    
    def db_execute(self, query: str, params: tuple = None):
        try:
            cursor = self.postgres_connection.cursor()
            cursor.execute(query, params)
            self.postgres_connection.commit()
            cursor.close()
            return True
        except Exception as e:
            self.logger.error(f"Ошибка выполнения SQL: {e}")
            self.postgres_connection.rollback()
            return False
    
    def db_fetch(self, query: str, params: tuple = None):
        try:
            cursor = self.postgres_connection.cursor()
            cursor.execute(query, params)
            result = cursor.fetchall()
            cursor.close()
            return result
        except Exception as e:
            self.logger.error(f"Ошибка выполнения SQL запроса: {e}")
            return None
# Новые методы для работы с AI и кешем
    def cache_conversation_context(self, chat_id: str, context_data: dict, ttl: int = 3600):
        """Кеширует контекст диалога"""
        key = f"conversation_context:{chat_id}"
        return self.cache_set(key, json.dumps(context_data), ttl)

    def get_conversation_context(self, chat_id: str) -> dict:
        """Получает контекст диалога из кеша"""
        key = f"conversation_context:{chat_id}"
        cached = self.cache_get(key)
        return json.loads(cached) if cached else {}

    def cache_ai_request(self, request_id: str, request_data: dict, ttl: int = 1800):
        """Кеширует AI запрос"""
        key = f"ai_request:{request_id}"
        return self.cache_set(key, json.dumps(request_data), ttl)

    def mark_message_processing(self, message_id: str, status: str = "processing"):
        """Помечает сообщение как обрабатываемое"""
        key = f"message_status:{message_id}"
        return self.cache_set(key, status, 300)  # 5 минут

    def is_message_processing(self, message_id: str) -> bool:
        """Проверяет обрабатывается ли сообщение"""
        key = f"message_status:{message_id}"
        status = self.cache_get(key)
        return status == "processing"

    def cache_chat_processing_status(self, chat_id: str):
        """Кеширует статус обработки чата"""
        key = f"chat_processed:{chat_id}"
        return self.cache_set(key, "true", 300)  # 5 минут

    def is_chat_recently_processed(self, chat_id: str) -> bool:
        """Проверяет был ли чат недавно обработан"""
        key = f"chat_processed:{chat_id}"
        return bool(self.cache_get(key))
