# ProducerFactory và ConsumerFactory theo thread

Trong Spring Kafka, `ProducerFactory` và `ConsumerFactory` thường được khai báo thành bean dùng chung trong Spring ApplicationContext. Factory có thể được nhiều service hoặc listener sử dụng, nhưng đối tượng Kafka client mà factory tạo ra có quy tắc chia sẻ khác nhau: `KafkaProducer` là thread-safe, còn `KafkaConsumer` không thread-safe và phải được một thread sở hữu.

Vì vậy, không nên hiểu “factory theo thread” là phải tạo một Spring factory mới cho mỗi thread. Cần phân biệt factory quản lý cấu hình và vòng đời client với producer/consumer instance thực tế. Spring Kafka cung cấp cơ chế phù hợp cho hai loại client này, từ producer dùng chung đến producer riêng theo thread và consumer riêng cho từng listener container.

## 1. Factory và Kafka client là hai lớp khác nhau

Một factory mô tả cách tạo client: bootstrap servers, serializer/deserializer, security, group ID, client ID và các thuộc tính Kafka khác. Factory có thể là singleton bean, còn số lượng client được tạo phụ thuộc cách factory và ứng dụng sử dụng nó.

| Thành phần | Vai trò | Quy tắc thread |
|---|---|---|
| `ProducerFactory<K, V>` | Tạo và quản lý producer | Thường được chia sẻ giữa các thread |
| `KafkaProducer<K, V>` | Gửi record đến broker | Thread-safe; nhiều thread có thể gọi `send()` |
| `ConsumerFactory<K, V>` | Tạo consumer | Có thể được chia sẻ để tạo nhiều consumer |
| `KafkaConsumer<K, V>` | Poll và đọc record | Không thread-safe; một consumer chỉ được thao tác bởi thread sở hữu |
| `KafkaTemplate<K, V>` | Abstraction gửi record của Spring Kafka | Có thể dùng như bean singleton từ nhiều thread |
| Listener container | Quản lý consumer, poll, acknowledgement và lifecycle | Mỗi consumer chạy trên thread riêng do container quản lý |

Mô hình thường dùng là một `ProducerFactory` và một `KafkaTemplate` được nhiều service chia sẻ; một `ConsumerFactory` được nhiều listener container dùng chung; mỗi child listener container sở hữu consumer riêng.

## 2. Producer mặc định có thể dùng chung giữa nhiều thread

Kafka producer được thiết kế thread-safe. Nhiều thread có thể gọi `send()` trên cùng một producer mà không cần tự khóa quanh mỗi lời gọi. Producer tự quản lý buffer, batch, network I/O và callback.

`DefaultKafkaProducerFactory` của Spring Kafka mặc định có thể chia sẻ một producer không transactional cho các client sử dụng factory. `KafkaTemplate` lấy producer từ factory khi gửi và trả lại theo cơ chế quản lý của factory.

Ví dụ khai báo factory và template:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.JsonSerializer;

@Configuration
class ProducerConfiguration {

    @Bean
    ProducerFactory<String, OrderEvent> orderProducerFactory() {
        Map<String, Object> properties = new HashMap<>();

        properties.put(
                ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092"
        );
        properties.put(
                ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class
        );
        properties.put(
                ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                JsonSerializer.class
        );
        properties.put(ProducerConfig.ACKS_CONFIG, "all");

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean
    KafkaTemplate<String, OrderEvent> orderKafkaTemplate(
            ProducerFactory<String, OrderEvent> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }
}
```

Các service có thể inject cùng `KafkaTemplate`:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    OrderPublisher(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    void publish(OrderEvent event) {
        kafkaTemplate.send("orders", event.orderId(), event);
    }
}
```

Không cần tạo một `KafkaTemplate` hoặc `ProducerFactory` mới cho mỗi request hay mỗi thread. Chia sẻ producer mặc định thường là lựa chọn đơn giản và hiệu quả vì producer đã hỗ trợ gọi đồng thời.

## 3. Khi nào cần producer riêng cho từng thread?

Với factory không dùng transaction, Spring Kafka cung cấp tùy chọn `producerPerThread` trên `DefaultKafkaProducerFactory`. Khi bật, factory tạo một producer riêng cho từng thread gọi factory lần đầu; producer được lưu theo thread để những lần gọi tiếp theo trên cùng thread có thể tái sử dụng. Tùy chọn này hữu ích trong một số trường hợp `flush()` trên template dùng chung có thể làm các thread khác phải chờ producer chung.

```java
DefaultKafkaProducerFactory<String, OrderEvent> producerFactory =
        new DefaultKafkaProducerFactory<>(properties);

producerFactory.setProducerPerThread(true);
```

Cơ chế này có thể hữu ích khi cần cô lập producer theo thread hoặc muốn mỗi worker có producer instance riêng. Tuy nhiên, producer riêng theo thread không tự làm tăng throughput. Producer mặc định vốn thread-safe và đã có khả năng gửi bất đồng bộ, batching và I/O nền.

Chỉ cân nhắc bật `producerPerThread` khi có lý do đo lường hoặc yêu cầu cô lập cụ thể. Đây là tùy chọn cho cách dùng producer không transactional; khi cần Kafka transaction, hãy dùng transactional producer cache và transaction manager của Spring Kafka. Mỗi producer riêng có buffer, connection, metadata cache và tài nguyên nền riêng; số thread tăng có thể làm số producer và mức tiêu thụ tài nguyên tăng theo.

### Dọn producer gắn với thread

Producer được lưu trong `ThreadLocal` không tự được đóng chỉ vì một task trong thread pool kết thúc. Khi thread không còn cần producer, phải gọi `closeThreadBoundProducer()` trên chính thread đã tạo và sử dụng producer đó. `reset()` và `destroy()` của factory không tự dọn các producer thread-bound này.

Ví dụ với worker có vòng đời rõ ràng:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;

class OrderPublishingWorker implements Runnable {

    private final BlockingQueue<OrderEvent> queue;
    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;
    private final DefaultKafkaProducerFactory<String, OrderEvent> producerFactory;

    OrderPublishingWorker(
            BlockingQueue<OrderEvent> queue,
            KafkaTemplate<String, OrderEvent> kafkaTemplate,
            DefaultKafkaProducerFactory<String, OrderEvent> producerFactory) {
        this.queue = queue;
        this.kafkaTemplate = kafkaTemplate;
        this.producerFactory = producerFactory;
    }

    @Override
    public void run() {
        try {
            while (!Thread.currentThread().isInterrupted()) {
                OrderEvent event = queue.take();

                kafkaTemplate.send(
                        "orders",
                        event.orderId(),
                        event
                ).get(10, TimeUnit.SECONDS);
            }
        }
        catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
        catch (Exception exception) {
            throw new IllegalStateException("Publishing failed", exception);
        }
        finally {
            producerFactory.closeThreadBoundProducer();
        }
    }
}
```

Đoạn code minh họa một worker chuyên dụng: nó chờ các event, chờ kết quả gửi hoàn tất rồi mới kết thúc; phần `finally` đóng producer gắn với thread. Trong ứng dụng thực tế, cần quyết định cách đưa lỗi gửi vào retry hoặc error queue thay vì làm mất event khi worker dừng.

Nếu dùng thread pool sống lâu, không gọi `closeThreadBoundProducer()` sau mỗi task nếu mục tiêu là tái sử dụng producer giữa các task. Hãy gọi khi worker thread kết thúc hoặc khi thread không còn sử dụng producer. Phương thức phải chạy trên đúng thread sở hữu producer; gọi từ thread quản lý pool sẽ không đóng producer của worker khác.

## 4. Producer riêng theo thread có chi phí gì?

Mỗi producer là một Kafka client đầy đủ, không chỉ là một object wrapper. Khi bật `producerPerThread`, số producer có thể gần bằng số thread thực sự sử dụng factory.

| Tài nguyên | Ảnh hưởng khi tăng số producer |
|---|---|
| Network connection | Có thêm kết nối tới broker |
| Buffer và batch | Mỗi producer có vùng buffer và batch riêng |
| Metadata | Mỗi producer quản lý metadata client của mình |
| Background I/O | Mỗi producer có tài nguyên network/I/O riêng |
| Metrics | Có thêm client metrics; không mặc định mỗi thread có `client.id` riêng |
| Shutdown | Cần đóng producer gắn với từng thread |

Ví dụ nếu một worker pool có 20 thread và mỗi producer được cấu hình `buffer.memory` tối đa 32 MiB, tổng ngân sách buffer lý thuyết có thể lên đến khoảng 640 MiB khi các producer sử dụng hết giới hạn. Con số thực tế phụ thuộc mức cấp phát và tải, nhưng cần tính đến khi mở rộng số worker.

Đừng bật producer-per-thread chỉ để tránh lock tự viết. Kafka producer đã thread-safe. Trước tiên hãy đo throughput, latency, buffer availability, request latency và CPU để xác định có bottleneck thực sự hay không.

## 5. ConsumerFactory được chia sẻ, nhưng Consumer phải riêng

Khác với producer, Kafka consumer không thread-safe. Một `KafkaConsumer` không được dùng đồng thời từ nhiều thread. Các thao tác `subscribe()`, `poll()`, `commitSync()`, `pause()` và `close()` phải được thực hiện theo thread sở hữu consumer. `wakeup()` là ngoại lệ được Kafka hỗ trợ để đánh thức consumer từ thread khác.

`DefaultKafkaConsumerFactory` có thể là singleton bean. Mỗi lần gọi `createConsumer()` sẽ tạo một consumer mới với cấu hình của factory. Do đó, nhiều worker có thể dùng chung factory nhưng mỗi worker phải sở hữu consumer instance riêng.

Ví dụ khai báo factory:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.serializer.JsonDeserializer;

@Configuration
class ConsumerConfiguration {

    @Bean
    ConsumerFactory<String, OrderEvent> orderConsumerFactory() {
        Map<String, Object> properties = new HashMap<>();

        properties.put(
                ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092"
        );
        properties.put(
                ConsumerConfig.GROUP_ID_CONFIG,
                "orders-service"
        );
        properties.put(
                ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
                false
        );
        properties.put(
                ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class
        );
        properties.put(
                ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                JsonDeserializer.class
        );
        properties.put(
                JsonDeserializer.TRUSTED_PACKAGES,
                "com.example.orders"
        );

        return new DefaultKafkaConsumerFactory<>(properties);
    }
}
```

Factory trên có thể được nhiều listener container dùng chung. Mỗi container/consumer thread sẽ yêu cầu một consumer mới. Không lưu một `KafkaConsumer` singleton rồi inject vào nhiều service hoặc worker.

## 6. Tạo consumer bên trong thread sở hữu nó

Nếu tự quản lý Kafka consumer thay vì dùng `@KafkaListener`, hãy gọi `consumerFactory.createConsumer()` bên trong worker thread. Worker đó thực hiện subscribe, poll và close consumer trong cùng vòng đời.

```java
import java.time.Duration;
import java.util.List;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.springframework.kafka.core.ConsumerFactory;

class OrderConsumerWorker implements Runnable {

    private final ConsumerFactory<String, OrderEvent> consumerFactory;

    OrderConsumerWorker(
            ConsumerFactory<String, OrderEvent> consumerFactory) {
        this.consumerFactory = consumerFactory;
    }

    @Override
    public void run() {
        try (Consumer<String, OrderEvent> consumer =
                     consumerFactory.createConsumer()) {

            consumer.subscribe(List.of("orders"));

            while (!Thread.currentThread().isInterrupted()) {
                ConsumerRecords<String, OrderEvent> records =
                        consumer.poll(Duration.ofSeconds(1));

                records.forEach(record ->
                        process(record.key(), record.value())
                );

                if (!records.isEmpty()) {
                    // Commit only after every record in this poll was processed successfully.
                    consumer.commitSync();
                }
            }
        }
    }
}
```

Ví dụ dùng try-with-resources để đóng consumer khi worker kết thúc. Phần `process()` là xử lý nghiệp vụ minh họa; ứng dụng thực tế cần xác định commit strategy, retry và cách dừng worker. Không gọi `poll()` hoặc `commitSync()` cho consumer này từ thread khác.

Nếu cần dừng worker từ bên ngoài, có thể giữ tham chiếu consumer và gọi `wakeup()` theo API Kafka để đánh thức vòng poll; sau đó để chính thread sở hữu consumer thoát vòng lặp và đóng nó. Không dùng `close()` từ thread điều khiển để thay thế quy trình dừng có kiểm soát.

## 7. Listener container tự tạo consumer theo concurrency

Với `@KafkaListener`, thông thường không cần tự tạo thread hoặc gọi `ConsumerFactory.createConsumer()`. Spring Kafka listener container quản lý consumer và vòng đời của chúng.

Khi cấu hình concurrency bằng 3, `ConcurrentMessageListenerContainer` tạo ba child container; mỗi child có consumer riêng chạy trên consumer thread riêng. Cả ba dùng chung một `ConsumerFactory` bean.

```java
import org.springframework.boot.autoconfigure.kafka.ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
class ListenerContainerConfiguration {

    @Bean("ordersListenerFactory")
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        configurer.configure(factory, consumerFactory);
        factory.setConcurrency(3);

        return factory;
    }
}
```

Listener chọn factory:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    @KafkaListener(
            id = "ordersListener",
            topics = "orders",
            groupId = "orders-service",
            containerFactory = "ordersListenerFactory"
    )
    public void onOrder(OrderEvent event) {
        orderService.process(event);
    }
}
```

Spring Kafka quản lý tạo consumer, subscribe, poll, commit, rebalance và đóng consumer khi container dừng. Không tự đóng consumer do container sở hữu và không chia sẻ consumer instance giữa các listener thread.

## 8. Concurrency bị giới hạn bởi partition

Concurrency là số consumer thread mà container có thể chạy cho listener. Số consumer thực sự nhận partition trong cùng group bị giới hạn bởi số partition được gán.

Ví dụ topic có 4 partition:

| Concurrency | Số consumer | Hệ quả |
|---:|---:|---|
| 1 | 1 | Một consumer đọc cả bốn partition |
| 2 | 2 | Hai consumer chia bốn partition |
| 4 | 4 | Có thể một partition cho mỗi consumer |
| 6 | 6 | Ít nhất hai consumer có thể không được gán partition |

Tăng concurrency không làm tăng số partition và không tự tăng throughput nếu bottleneck nằm ở database hoặc downstream service. Mỗi consumer còn có connection, buffer fetch và chi phí quản lý riêng.

Hãy chọn concurrency theo số partition, thời gian xử lý record, khả năng downstream và consumer lag. Nếu mỗi partition cần xử lý tuần tự, không chuyển record ra executor không kiểm soát vì có thể làm side effect hoàn tất sai thứ tự.

## 9. Phân biệt producerPerThread với consumer concurrency

Hai khái niệm cùng nói đến thread nhưng giải quyết vấn đề khác nhau:

| Cấu hình/cơ chế | Tác động |
|---|---|
| `DefaultKafkaProducerFactory.setProducerPerThread(true)` | Tạo và cache producer riêng cho mỗi thread sử dụng factory |
| Producer mặc định thread-safe | Nhiều thread chia sẻ producer theo cơ chế factory |
| `ConcurrentMessageListenerContainer` concurrency | Tạo nhiều consumer child và thread xử lý listener |
| `ConsumerFactory.createConsumer()` | Tạo consumer instance mới; ứng dụng phải quản lý thread sở hữu |
| `@KafkaListener(concurrency = "3")` | Yêu cầu listener container chạy tối đa ba consumer thread |

Không cần bật `producerPerThread` chỉ vì listener container có concurrency 3. Producer và consumer là hai luồng client độc lập; một listener có thể gửi output bằng cùng một `KafkaTemplate` thread-safe trong khi container quản lý consumer riêng cho từng child.

## 10. Thread và transaction trong Spring Kafka

Khi sử dụng Kafka transaction, Spring Kafka gắn producer transactional với transaction context trên thread hiện tại. `KafkaTransactionManager` và `KafkaTemplate` phối hợp để lấy producer tham gia transaction; producer được commit hoặc abort theo transaction lifecycle.

Điều này có nghĩa transaction gắn với thread thực thi. Không nên bắt đầu transaction trên một thread rồi chuyển phần gửi Kafka sang thread khác và kỳ vọng transaction context tự đi theo. Các cơ chế `@Async`, executor hoặc callback chạy trên thread khác không tự kế thừa transaction đang mở.

Ví dụ gửi trong transaction bằng `KafkaTemplate`:

```java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders", orderId, orderCreated);
    operations.send("order-audit", orderId, auditEvent);
    return true;
});
```

Ví dụ này yêu cầu producer factory được cấu hình transactional, thường bằng một `transactionIdPrefix` duy nhất cho từng application instance. Các lệnh gửi trong callback tham gia transaction do template mở trên thread hiện tại. Khi callback hoàn tất bình thường, transaction được commit; nếu phát sinh exception, transaction được abort theo semantics của API.

Nếu dùng `KafkaTransactionManager` cùng `@Transactional`, cần cấu hình transaction manager và producer factory theo hướng dẫn của phiên bản Spring Kafka đang chạy. `producerPerThread` được thiết kế cho producer không transactional; khi factory dùng transaction, hãy để transactional producer cache và transaction manager quản lý producer. Không gọi `closeThreadBoundProducer()` trong khi một producer còn được sử dụng.

## 11. Vòng đời và shutdown

Mỗi loại client cần được đóng đúng nơi sở hữu:

| Đối tượng | Ai đóng? | Thời điểm |
|---|---|---|
| Producer dùng chung do `DefaultKafkaProducerFactory` quản lý | Factory/Spring lifecycle | Khi factory bị destroy hoặc reset |
| Producer gắn với thread khi bật `producerPerThread` | Chính thread sở hữu, qua `closeThreadBoundProducer()` | Khi thread không còn cần producer |
| Consumer tự tạo qua `ConsumerFactory` | Worker tạo và sử dụng consumer | Khi worker kết thúc |
| Consumer do listener container tạo | Spring Kafka container | Khi container dừng |
| `KafkaTemplate` | Thông thường không cần đóng riêng | Factory quản lý producer bên dưới |

Khi ứng dụng shutdown, hãy dừng listener container trước khi đóng các tài nguyên mà listener cần dùng. Với worker tự quản lý, yêu cầu worker dừng vòng poll, hoàn tất hoặc xử lý phần việc đang chạy rồi đóng consumer/producer trong đúng thread.

Không dùng `ThreadLocal` để giữ client mà không có chiến lược cleanup. Thread pool thường tái sử dụng thread trong thời gian dài; nếu không giải phóng thread-bound producer, tài nguyên có thể tồn tại lâu hơn dự kiến.

## 12. Khi nào nên tách factory?

Tạo factory riêng theo mục đích cấu hình hoặc cluster, không phải chỉ vì có thêm thread.

| Nhu cầu | Cách thiết kế |
|---|---|
| Nhiều service cùng gửi một cluster với cùng serializer | Chia sẻ `ProducerFactory` và `KafkaTemplate` |
| Cần producer riêng theo thread sau khi đo được nhu cầu | Dùng `producerPerThread` và cleanup đúng thread |
| Gửi đến cluster khác | Tạo `ProducerFactory` riêng, inject bằng `@Qualifier` |
| Serializer hoặc security khác | Tạo factory riêng với cấu hình tương ứng |
| Nhiều listener cùng cluster | Chia sẻ `ConsumerFactory`, dùng factory/container concurrency phù hợp |
| Listener cần concurrency khác nhau | Tạo listener container factory riêng hoặc cấu hình concurrency ở endpoint |
| Consumer thủ công cho tác vụ riêng | Chia sẻ `ConsumerFactory`, tạo một consumer riêng trong từng worker |

Ví dụ có hai producer factory cho hai cluster nên dùng bean name rõ ràng và `@Qualifier` ở nơi tạo template. Không dựa vào thứ tự bean hoặc `@Primary` để định tuyến nghiệp vụ khi nhiều cluster có ý nghĩa khác nhau.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nhiều thread cùng gọi producer gây lo ngại thread safety | Nhầm producer với consumer | Producer thread-safe; chia sẻ factory/template mặc định thường phù hợp |
| Producer tồn tại sau khi worker kết thúc | Bật `producerPerThread` nhưng không cleanup | Gọi `closeThreadBoundProducer()` trên đúng thread |
| Gọi cleanup nhưng producer worker khác vẫn còn | Gọi `closeThreadBoundProducer()` từ thread quản lý | Cleanup phải chạy trên thread sở hữu producer |
| Consumer phát sinh lỗi concurrent access | Chia sẻ một `KafkaConsumer` giữa nhiều thread | Mỗi thread/container phải có consumer instance riêng |
| Tăng concurrency nhưng throughput không tăng | Số partition thấp hoặc downstream đã bão hòa | Kiểm tra assignment, lag và bottleneck |
| Tạo một factory cho mỗi request | Nhầm factory với client instance | Dùng factory bean ổn định, tái sử dụng client theo cơ chế phù hợp |
| Transaction không hoạt động qua executor | Transaction context gắn với thread | Thực hiện thao tác transaction trên cùng thread hoặc thiết kế ranh giới transaction mới |
| Tài nguyên tăng mạnh khi bật producer-per-thread | Mỗi thread tạo thêm producer, connection và buffer | Đo số thread, buffer và network; chỉ bật khi có lợi ích rõ |
| Listener consumer bị đóng thủ công | Can thiệp vào client do container quản lý | Để listener container quản lý lifecycle consumer |

## 14. Checklist thiết kế factory theo thread

1. Dùng `ProducerFactory` và `ConsumerFactory` làm bean dùng chung khi cấu hình client giống nhau.
2. Ưu tiên producer mặc định thread-safe; chỉ bật `producerPerThread` khi có lý do đo lường hoặc cô lập cụ thể.
3. Khi bật `producerPerThread`, gọi `closeThreadBoundProducer()` trên đúng thread khi thread kết thúc sử dụng producer.
4. Không chia sẻ một `KafkaConsumer` cho nhiều thread.
5. Với `@KafkaListener`, để container tạo và quản lý consumer riêng theo concurrency.
6. Chọn concurrency theo partition count và năng lực xử lý downstream.
7. Không tạo factory mới cho mỗi request hoặc mỗi task.
8. Tách factory khi cluster, serializer, security hoặc vai trò producer khác nhau.
9. Giữ transaction trong cùng thread; không giả định context tự truyền qua executor.
10. Kiểm tra shutdown và cleanup để không rò rỉ producer, consumer hoặc connection.

`ProducerFactory` và `ConsumerFactory` thường được chia sẻ như factory bean singleton. Điểm khác biệt nằm ở client được tạo: producer có thể dùng chung vì thread-safe hoặc tách riêng theo thread khi cần; consumer phải có instance riêng cho từng thread sở hữu. Dùng đúng mô hình này giúp Spring Kafka tận dụng concurrency mà vẫn quản lý an toàn vòng đời client và tài nguyên broker.
