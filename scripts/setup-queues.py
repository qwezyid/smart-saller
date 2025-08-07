#!/usr/bin/env python3
import pika
import os
import sys
from dotenv import load_dotenv

load_dotenv('/opt/smart-seller/config/rabbitmq-config.env')

def setup_rabbitmq_infrastructure():
    try:
        credentials = pika.PlainCredentials(
            os.getenv('RABBITMQ_USERNAME'),
            os.getenv('RABBITMQ_PASSWORD')
        )
        
        parameters = pika.ConnectionParameters(
            host=os.getenv('RABBITMQ_HOST'),
            port=int(os.getenv('RABBITMQ_PORT', 5672)),
            virtual_host=os.getenv('RABBITMQ_VHOST', '/'),
            credentials=credentials,
            heartbeat=600
        )
        
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        
        print("Создание инфраструктуры RabbitMQ...")
        
        main_exchange = os.getenv('RABBITMQ_MAIN_EXCHANGE', 'smart-seller-exchange')
        dlx_exchange = os.getenv('RABBITMQ_DLX_EXCHANGE', 'smart-seller-dlx')
        
        channel.exchange_declare(
            exchange=main_exchange,
            exchange_type='topic',
            durable=True
        )
        
        channel.exchange_declare(
            exchange=dlx_exchange,
            exchange_type='topic',
            durable=True
        )
        
        print(f"Exchange {main_exchange} создан")
        print(f"Dead Letter Exchange {dlx_exchange} создан")
        
        queues_config = [
            {
                'name': 'avito.messages',
                'routing_key': 'avito.message.new',
                'description': 'Входящие сообщения от Avito'
            },
            {
                'name': 'parser.messages', 
                'routing_key': 'parser.message.parsed',
                'description': 'Обработанные парсером сообщения'
            },
            {
                'name': 'pricing.requests',
                'routing_key': 'pricing.calculate',
                'description': 'Запросы на расчет цены'
            },
            {
                'name': 'admin.notifications',
                'routing_key': 'admin.notify.*',
                'description': 'Уведомления для админов'
            },
            {
                'name': 'admin.actions',
                'routing_key': 'admin.action.*',
                'description': 'Действия админов из Telegram'
            },
            {
                'name': 'avito.outgoing',
                'routing_key': 'avito.message.send',
                'description': 'Исходящие сообщения в Avito'
            },
            {
                'name': 'deals.updates',
                'routing_key': 'deal.update.*',
                'description': 'Обновления сделок'
            },
            {
                'name': 'failed.messages',
                'routing_key': 'failed.*',
                'description': 'Очередь ошибок'
            }
        ]
        
        for queue_config in queues_config:
            queue_args = {
                'x-dead-letter-exchange': dlx_exchange,
                'x-dead-letter-routing-key': f"dlx.{queue_config['routing_key']}",
                'x-message-ttl': 3600000,
                'x-max-retries': 3
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
            
            print(f"Очередь {queue_config['name']} создана ({queue_config['description']})")
        
        connection.close()
        print("Инфраструктура RabbitMQ настроена успешно!")
        return True
        
    except Exception as e:
        print(f"Ошибка настройки RabbitMQ: {e}")
        return False

if __name__ == "__main__":
    success = setup_rabbitmq_infrastructure()
    sys.exit(0 if success else 1)
