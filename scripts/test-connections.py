#!/usr/bin/env python3
import pika
import redis
import psycopg2
import sys
import os
from dotenv import load_dotenv

load_dotenv('/opt/smart-seller/config/services-config.env')

def test_rabbitmq():
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
        
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        
        exchange_name = os.getenv('RABBITMQ_MAIN_EXCHANGE')
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
        
        test_message = "RabbitMQ connection test"
        channel.basic_publish(
            exchange=exchange_name,
            routing_key='test.message',
            body=test_message,
            properties=pika.BasicProperties(delivery_mode=2)
        )
        
        method_frame, header_frame, body = channel.basic_get(queue=test_queue)
        if method_frame:
            channel.basic_ack(method_frame.delivery_tag)
        
        channel.queue_delete(queue=test_queue)
        connection.close()
        
        print("✅ RabbitMQ подключение успешно")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка подключения к RabbitMQ: {e}")
        return False

def test_redis():
    try:
        r = redis.Redis(
            host=os.getenv('REDIS_HOST'),
            port=int(os.getenv('REDIS_PORT')),
            username=os.getenv('REDIS_USERNAME'),
            password=os.getenv('REDIS_PASSWORD'),
            db=int(os.getenv('REDIS_DB', 0)),
            decode_responses=True
        )
        
        r.set('test_key', 'Redis connection test')
        result = r.get('test_key')
        r.delete('test_key')
        
        if result == 'Redis connection test':
            print("✅ Redis подключение успешно")
            return True
        else:
            print("❌ Redis тест не прошел")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка подключения к Redis: {e}")
        return False

def test_postgresql():
    try:
        connection_string = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
        
        conn = psycopg2.connect(connection_string)
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 as test")
        result = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if result and result[0] == 1:
            print("✅ PostgreSQL подключение успешно")
            return True
        else:
            print("❌ PostgreSQL тест не прошел")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка подключения к PostgreSQL: {e}")
        return False

def main():
    print("🔍 Тестирование подключений к внешним сервисам...")
    print("=" * 50)
    
    rabbitmq_ok = test_rabbitmq()
    redis_ok = test_redis()
    postgres_ok = test_postgresql()
    
    print("=" * 50)
    
    if rabbitmq_ok and redis_ok and postgres_ok:
        print("🎉 Все подключения работают успешно!")
        return True
    else:
        print("⚠️ Есть проблемы с подключениями")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
