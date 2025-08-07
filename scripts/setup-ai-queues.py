#!/usr/bin/env python3
import pika
import os
import sys
from dotenv import load_dotenv

load_dotenv('/opt/smart-seller/config/rabbitmq-config.env')

def setup_ai_queues():
    try:
        credentials = pika.PlainCredentials(
            os.getenv('RABBITMQ_USERNAME'),
            os.getenv('RABBITMQ_PASSWORD')
        )
        
        connection = pika.BlockingConnection(pika.ConnectionParameters(
            host=os.getenv('RABBITMQ_HOST'),
            port=int(os.getenv('RABBITMQ_PORT', 5672)),
            virtual_host=os.getenv('RABBITMQ_VHOST', '/'),
            credentials=credentials,
            heartbeat=600
        ))
        
        channel = connection.channel()
        main_exchange = os.getenv('RABBITMQ_MAIN_EXCHANGE')
        dlx_exchange = os.getenv('RABBITMQ_DLX_EXCHANGE')
        
        # Новые очереди для AI
        ai_queues = [
            {
                'name': 'ai.messages.new_with_context',
                'routing_key': 'ai.message.new_with_context',
                'description': 'Новые сообщения с полным контекстом для AI'
            },
            {
                'name': 'ai.parser.requests',
                'routing_key': 'ai.parser.extract_data',
                'description': 'Запросы на извлечение данных AI парсером'
            },
            {
                'name': 'ai.calculator.requests',
                'routing_key': 'ai.calculator.price',
                'description': 'Запросы на расчет цены AI калькулятором'
            },
            {
                'name': 'ai.assistant.responses',
                'routing_key': 'ai.assistant.respond',
                'description': 'Генерация ответов AI ассистентом'
            },
            {
                'name': 'avito.send_message',
                'routing_key': 'avito.send.message',
                'description': 'Отправка сообщений в Avito'
            }
        ]
        
        for queue_config in ai_queues:
            queue_args = {
                'x-dead-letter-exchange': dlx_exchange,
                'x-dead-letter-routing-key': f"dlx.{queue_config['routing_key']}",
                'x-message-ttl': 1800000,  # 30 минут для AI запросов
                'x-max-retries': 2
            }
            
            channel.queue_declare(
                queue=queue_config['name'],
                durable=True,
                arguments=queue_args
            )
            
            channel.queue_bind(
                exchange=main_exchange,
                queue=queue_config['name'],
                routing_key=queue_config['routing_key']
            )
            
            dlq_name = f"dlx.{queue_config['name']}"
            channel.queue_declare(queue=dlq_name, durable=True)
            channel.queue_bind(
                exchange=dlx_exchange,
                queue=dlq_name,
                routing_key=f"dlx.{queue_config['routing_key']}"
            )
            
            print(f"✅ AI очередь {queue_config['name']} создана")
        
        connection.close()
        print("🎉 AI очереди настроены!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка создания AI очередей: {e}")
        return False

if __name__ == "__main__":
    success = setup_ai_queues()
    sys.exit(0 if success else 1)
