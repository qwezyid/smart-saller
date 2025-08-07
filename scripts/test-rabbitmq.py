#!/usr/bin/env python3
import pika
import sys
import os
from dotenv import load_dotenv

load_dotenv('/opt/smart-seller/config/rabbitmq-config.env')

def test_connection():
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
            heartbeat=int(os.getenv('RABBITMQ_HEARTBEAT', 600)),
            connection_attempts=3,
            retry_delay=2
        )
        
        print(f"Подключаемся к RabbitMQ: {os.getenv('RABBITMQ_HOST')}")
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        
        exchange_name = os.getenv('RABBITMQ_MAIN_EXCHANGE', 'smart-seller-exchange')
        channel.exchange_declare(
            exchange=exchange_name,
            exchange_type='topic',
            durable=True
        )
        
        test_queue = f"{exchange_name}.test"
        channel.queue_declare(queue=test_queue, durable=True)
        channel.queue_bind(
            exchange=exchange_name,
            queue=test_queue,
            routing_key='test.message'
        )
        
        test_message = "Hello from Smart Seller!"
        channel.basic_publish(
            exchange=exchange_name,
            routing_key='test.message',
            body=test_message,
            properties=pika.BasicProperties(delivery_mode=2)
        )
        
        print("Подключение успешно!")
        print("Exchange создан!")
        print("Очередь создана!")
        print("Тестовое сообщение отправлено!")
        
        method_frame, header_frame, body = channel.basic_get(queue=test_queue)
        if method_frame:
            print(f"Сообщение получено: {body.decode()}")
            channel.basic_ack(method_frame.delivery_tag)
        
        channel.queue_delete(queue=test_queue)
        connection.close()
        
        print("Тест RabbitMQ прошел успешно!")
        return True
        
    except Exception as e:
        print(f"Ошибка подключения к RabbitMQ: {e}")
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
