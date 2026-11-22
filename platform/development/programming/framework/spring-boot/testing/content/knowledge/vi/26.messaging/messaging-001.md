# Phân biệt unit test listener với tích hợp qua broker thật

Trong nhóm **Messaging** của module **Spring Boot - testing**, một listener có thể hoạt động rất tốt khi được gọi trực tiếp bằng JUnit/Mockito nhưng vẫn thất bại khi chạy qua RabbitMQ, Kafka hoặc một message broker thật. Lý do là **gọi một Java method không đồng nghĩa một message đã đi qua exchange/topic, queue/partition, serialization, listener container, acknowledgement, retry và dead-letter handling**.

Bài học này phân biệt hai câu hỏi:

1. **Unit test listener:** Khi nhận một payload hoặc domain event cụ thể, code listener có giải mã, kiểm tra dữ liệu, gọi đúng collaborator và xử lý lỗi như mong muốn không? Đây là test **không mở Spring ApplicationContext hoặc broker** nếu listener được thiết kế tách biệt.
2. **Integration test qua broker thật:** Khi producer publish message qua API Spring, broker có định tuyến đến queue/topic mong muốn, listener container có thực sự consume, converter có hoạt động, message lỗi có được reject/requeue/dead-letter và side effect có thể quan sát được không? Đây là test dùng **broker thực**, ví dụ RabbitMQ qua Testcontainers.

Ví dụ chính dùng **Java 17+, Spring Boot 3.5.x, Spring AMQP, RabbitMQ và Testcontainers 1.x, JUnit Jupiter, Mockito**. Các phần code có đủ file để tạo một project mẫu; test tích hợp yêu cầu Docker và RabbitMQ image. Một chương trình Java SE độc lập chạy bằng `javac/java` để chứng minh codec trước khi đưa nó vào listener. Những lưu ý quan trọng cho **Kafka**, Spring Cloud Stream và message brokers khác được trình bày riêng, vì cơ chế offset/ack/partition của chúng **không được đồng nhất với RabbitMQ**.

## 1. Vì sao unit test listener thường xanh giả?

Xem cấu trúc phổ biến:

```text
Producer / HTTP service
         |
         v
RabbitTemplate.convertAndSend(...)
         |
         v
RabbitMQ exchange + routing key
         |
         v
RabbitMQ queue
         |
         v
Spring AMQP listener container
         |
         v
Message conversion -> @RabbitListener
         |
         v
Business handler -> DB/API/side effects
         |
         v
ACK hoặc reject/nack -> retry/DLQ
```

Một unit test chỉ làm:

```java
OrderQueueListener listener =
        new OrderQueueListener(mockHandler);
listener.accept("ORD-7|2");
verify(mockHandler).handle(
        new OrderCreated("ORD-7", 2));
```

Có thể chứng minh logic của `accept(...)` và dependency interaction, **nhưng không kiểm tra**:

- RabbitMQ server đang chạy và ứng dụng kết nối được hay không.
- Exchange, queue, binding và routing key có đúng không.
- Consumer có subscribe đúng queue không; `@RabbitListener` có được Spring phát hiện không.
- Payload được `RabbitTemplate` serialize với headers/content-type phù hợp hay không.
- Listener container xử lý exception, acknowledgement, redelivery hay dead-letter ra sao.
- Multiple consumers/threads, message ordering, duplicate delivery và transaction/offset semantics.
- Request được publish nhưng không có route thì broker có drop/trả về hay không.
- DB transaction của consumer có commit/rollback; side effect HTTP, cache hoặc events có được xử lý an toàn không.

Đổi lại, unit test **rất nhanh, determinisitic, không cần Docker**, dễ xác định một lỗi business nằm ở dòng nào. Mục tiêu không phải thay unit test bằng mọi integration test; mục tiêu là **kết hợp đúng mức test để bảo vệ các boundary khác nhau**.

## 2. Bảng so sánh: lời gọi trực tiếp và broker thật

| Tiêu chí | Unit test listener (JUnit/Mockito) | Integration test với broker thật |
| --- | --- | --- |
| Khởi động broker | Không | **Có** |
| Spring context | Thường không | Thường có, để kiểm tra wiring |
| Listener method | Gọi trực tiếp | Được gọi bởi listener container |
| Serialization/converter | Chỉ test nếu chủ động gọi | Test đường publish → consume thực |
| Exchange/queue/routing | Không | **Có thể kiểm tra** |
| Header/content-type | Không mặc định | Có thể kiểm tra nếu assert cụ thể |
| ACK/NACK/requeue | Không | Có thể kiểm tra qua broker behavior |
| Retry/DLQ | Không | Có thể kiểm tra bằng message lỗi và DLQ |
| Concurrency/timing | Thường đồng bộ | **Bất đồng bộ**, cần chờ có giới hạn |
| Database commit | Không, nếu chỉ mock handler | Chỉ khi setup DB thật và có assertion |
| Chẩn đoán lỗi code | Rất nhanh | Có thêm nguyên nhân Docker/broker/network |
| Tốc độ | Nhanh | Chậm hơn do startup/transport |
| CI yêu cầu Docker | Không | Có, nếu dùng Testcontainers |
| Mục đích | Logic và contract của method | Tích hợp broker + listener stack |

**Quy tắc:** dùng unit test cho parse/validation/delegation/error propagation; dùng integration test cho routing, delivery, converter, failure policy và cấu hình thực tế. Nếu mục tiêu là kiểm tra DB sau khi listener xử lý, test integration cũng cần **DB thật** hoặc một kiểm chứng persistent side effect phù hợp; broker thật một mình chưa đủ.

## 3. Chọn RabbitMQ cho ví dụ; không áp máy móc sang Kafka

Trong RabbitMQ/AMQP 0-9-1, mô hình minh họa là:

```text
Publisher --(exchange + routing key)--> Exchange
                                             |
                                    Binding route
                                             v
                                           Queue
                                             |
                                             v
                                         Consumer
                                             |
                              success: ACK / failure: reject
                                             |
                                     optional Dead Letter Exchange
```

Trong Apache Kafka, publisher ghi **record vào topic/partition**, consumer group đọc theo offset. Không có exchange + queue + routing-key giống RabbitMQ. Kafka dùng **offset commit**, rebalancing, partition assignment và error-handling theo Spring Kafka container; không thể chỉ đổi `@RabbitListener` thành `@KafkaListener` rồi giữ nguyên test ACK/DLX.

Cùng là “unit test listener vs broker integration”, nhưng **assertions phải đi theo giao thức**:

| Khía cạnh | RabbitMQ | Kafka |
| --- | --- | --- |
| Message route | Exchange, binding, routing key, queue | Topic, key, partition |
| Tiêu thụ | Queue consumers | Consumer group, assigned partitions |
| Xác nhận tiến độ | ACK/NACK/requeue | Offset commit/seek/retry strategies |
| Thất bại | Reject/requeue, dead-letter exchange/queue | Retry topic/DLT hoặc error handler; phụ thuộc cấu hình |
| Thứ tự | Queue/consumer/prefetch/concurrency ảnh hưởng | Thứ tự trong một partition, không toàn topic |
| Test integration | `RabbitMQContainer` | Kafka broker container/embedded broker theo version |

Ví dụ đầy đủ chọn RabbitMQ vì có thể quan sát rõ một **exchange → queue → consumer** và một **dead-letter queue**; các nguyên tắc về test cấp độ, async wait và idempotency vẫn áp dụng cho Kafka nhưng config/code khác nhau.

## 4. Thiết kế listener dễ kiểm thử

Tách thành ba tầng nhỏ:

```text
raw wire payload
       |
       v
OrderEventCodec.decode(...)
       |
       v
OrderCreated (domain event)
       |
       v
OrderQueueListener.accept(...)
       |
       v
OrderEventHandler.handle(...)
       |
       v
side effect / persistence
```

Nhờ vậy:

- `OrderEventCodec` là Java thuần; test không cần Spring.
- `OrderQueueListener` chỉ phối hợp decode và handler; unit test truyền Mockito mock vào constructor.
- `OrderEventHandler` là port; production implementation có thể ghi DB, gọi service hoặc phát domain event.
- Test tích hợp đưa message qua RabbitMQ thật, dùng handler thực và một tín hiệu thread-safe để quan sát message đã được consumer xử lý.

**Lưu ý thiết kế test:** handler lưu sự kiện vào bộ nhớ chỉ để đưa ra tín hiệu quan sát khi kiểm thử broker. Nó **không chứng minh database commit**; nếu production handler ghi Postgres, cần một test riêng với PostgreSQL và transactions tương ứng.

### Hợp đồng payload tối giản

Để tập trung vào broker, wire format của ví dụ là:

```text
ORD-7|2
```

Ý nghĩa là orderId `ORD-7` và quantity 2, phân tách bằng ký tự `|`. Đây là **hợp đồng demo** chứ không phải chuẩn serialization cho message production. Khi chạy hệ thống thật, thường nên dùng JSON/Avro/Protobuf/CloudEvents cùng schema version, content-type, backwards compatibility và test converter riêng.

Với format đơn giản, vẫn có thể kiểm tra quan trọng: parse lỗi, quantity ngoài ngưỡng, exception propagation, message delivery qua queue, DLQ routing. Payload validation là một lớp; broker/message headers/converter là các lớp khác.

## 5. Cấu trúc project Java 17 / Spring Boot 3.5

Các file cần tạo:

```text
src/
├── main/java/example/messaging/
│   ├── MessagingApplication.java
│   ├── OrderCreated.java
│   ├── OrderEventCodec.java
│   ├── OrderEventHandler.java
│   ├── InMemoryOrderHandler.java
│   ├── OrderQueueListener.java
│   ├── RabbitTopology.java
│   └── OrderCodecDemo.java
└── test/java/example/messaging/
    ├── OrderQueueListenerUnitTest.java
    ├── OrderEventCodecTest.java
    └── RabbitBrokerIntegrationTest.java
```

Toàn bộ Java classes cùng package `example.messaging`. Đưa ứng dụng vào package gốc này giúp Spring Boot component scanning thấy listener, handler và topology.

### 5.1. Gradle dependencies

Trong project đã tạo bằng Spring Initializr (đã có Spring Boot Gradle plugin, repositories, BOM và Java toolchain 17+), phần liên quan ở `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:rabbitmq'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn cấu hình phụ thuộc** cho Spring Boot **3.5.x / Testcontainers 1.21.x**, không phải toàn bộ build file độc lập. `spring-boot-starter-test` cung cấp JUnit Jupiter/Mockito; `spring-boot-testcontainers` hỗ trợ `@ServiceConnection`. Artifact `org.testcontainers:rabbitmq` và import `org.testcontainers.containers.RabbitMQContainer` là cách dùng **Testcontainers 1.x**. Với Testcontainers 2.x, module có thể đổi thành `org.testcontainers:testcontainers-rabbitmq` và packages khác; phải kiểm tra đúng BOM, không trộn hai major versions.

**Yêu cầu môi trường:** Docker hoặc container runtime được Testcontainers nhận diện; quyền pull/run image `rabbitmq:4.1-management-alpine`; tài nguyên CPU/RAM và network đủ cho broker khởi động. Unit tests không cần Docker, integration tests cần. Không kết nối broker production hay dùng credentials production trong test.

### 5.2. MessagingApplication.java

Tạo `src/main/java/example/messaging/MessagingApplication.java`:

```java
package example.messaging;

import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@EnableRabbit
public class MessagingApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                MessagingApplication.class, args);
    }
}
```

`@EnableRabbit` giúp đăng ký infrastructure cho các `@RabbitListener` methods. Spring Boot tự cấu hình `ConnectionFactory`, `RabbitTemplate` và listener container factory từ starter/properties khi phù hợp. Dùng nó tường minh ở ví dụ để người học thấy rõ listener annotation không chỉ là một Java method thông thường.

**Không cần mở HTTP server**: ví dụ tập trung messaging, integration test sử dụng `webEnvironment=NONE`.

## 6. Domain event và codec Java thuần

### 6.1. OrderCreated.java

Tạo `src/main/java/example/messaging/OrderCreated.java`:

```java
package example.messaging;

public record OrderCreated(
        String orderId,
        int quantity) {
}
```

Record bất biến này là domain message sau khi parse. Unit test có thể so sánh record bằng `equals` do Java tự sinh. Không nhầm nó với RabbitMQ envelope: record này chưa có delivery tag, exchange, routing key, message headers hoặc acknowledgement metadata.

### 6.2. OrderEventCodec.java

Tạo `src/main/java/example/messaging/OrderEventCodec.java`:

```java
package example.messaging;

import java.util.Objects;

public final class OrderEventCodec {
    private OrderEventCodec() {
    }

    public static OrderCreated decode(String payload) {
        if (payload == null || payload.length() > 100) {
            throw new IllegalArgumentException(
                    "invalid event format");
        }

        String[] fields = payload.split("\\|", -1);

        if (fields.length != 2
                || !fields[0].matches(
                        "ORD-[A-Za-z0-9-]{1,64}")) {
            throw new IllegalArgumentException(
                    "invalid event format");
        }

        final int quantity;
        try {
            quantity = Integer.parseInt(fields[1]);
        } catch (NumberFormatException error) {
            throw new IllegalArgumentException(
                    "invalid quantity", error);
        }

        if (quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException(
                    "invalid quantity");
        }

        return new OrderCreated(fields[0], quantity);
    }

    public static String encode(OrderCreated event) {
        Objects.requireNonNull(event, "event");

        String payload =
                event.orderId() + "|" + event.quantity();

        // Dùng cùng rule để không tạo message
        // mà consumer của chúng ta sẽ từ chối.
        decode(payload);
        return payload;
    }
}
```

Code quyết định rõ:

- Có chính xác hai trường phân tách `|`.
- `orderId` theo allowlist `ORD-...`, không chứa pipe, whitespace hoặc dữ liệu quá dài.
- Quantity là integer trong **[1,100]**.
- Exception không chứa raw payload, giúp tránh vô tình log dữ liệu nhạy cảm khi xử lý message lỗi.
- Hàm `encode` dùng cùng rule để producer trong demo không phát ra payload sai.

**Trong production:** nếu sự kiện có nhiều trường, version, kiểu decimal, Unicode và optional fields, hãy dùng schema/JSON serializer được quản lý, không phát triển một custom pipe-delimited protocol tùy tiện. Phải test charset, content-type, backward compatibility và sự khác biệt giữa missing, null, blank.

### 6.3. Unit tests cho codec có ích thế nào?

Codec test ràng buộc **hợp đồng payload**, không cần RabbitMQ:

- Input đúng trả `OrderCreated` tương ứng.
- Quantity 0/101 bị từ chối.
- Quantity không phải số bị từ chối.
- Payload có format sai bị từ chối.

Một test `listener.accept("ORD-7|2")` không tự chứng minh actual AMQP bytes chuyển đúng sang String. Vì vậy unit codec test và integration wire test **bổ sung cho nhau**.

## 7. Port business và implementation quan sát được

### 7.1. OrderEventHandler.java

Tạo `src/main/java/example/messaging/OrderEventHandler.java`:

```java
package example.messaging;

public interface OrderEventHandler {
    void handle(OrderCreated event);
}
```

### 7.2. InMemoryOrderHandler.java

Tạo `src/main/java/example/messaging/InMemoryOrderHandler.java`:

```java
package example.messaging;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Service;

@Service
public class InMemoryOrderHandler
        implements OrderEventHandler {

    private final ConcurrentMap<String,
            CompletableFuture<OrderCreated>> received =
            new ConcurrentHashMap<>();

    private final ConcurrentMap<String, Integer> processed =
            new ConcurrentHashMap<>();

    @Override
    public void handle(OrderCreated event) {
        processed.merge(event.orderId(), 1, Integer::sum);

        received.computeIfAbsent(
                event.orderId(),
                ignored -> new CompletableFuture<>())
                .complete(event);
    }

    public CompletableFuture<OrderCreated> watch(
            String orderId) {
        return received.computeIfAbsent(
                orderId,
                ignored -> new CompletableFuture<>());
    }

    public int processedTimes(String orderId) {
        return processed.getOrDefault(orderId, 0);
    }
}
```

Đây là một **handler thật** nhưng side effect chỉ ở một concurrent map trong process. Test tích hợp dùng `watch(id).get(timeout)` để chờ signal khi listener xử lý, tránh `Thread.sleep(...)`. `processedTimes(id)` cung cấp số lượt xử lý trong một JVM.

**Giới hạn rất quan trọng:** `CompletableFuture` được complete trong handler **trước khi listener method trả về**, nên test quan sát sự kiện đã đến handler, **không trực tiếp chứng minh AMQP ACK đã được broker xác nhận**. Để test chính xác ack/prefetch/reconnect hay database commit, cần assertions/lifecycle phù hợp ở tầng broker/consumer/DB, không diễn giải kết quả watch vượt khả năng.

Tương tự, xử lý một id đúng một lần trong test không chứng minh delivery semantics là exactly-once. RabbitMQ phổ biến dùng **at-least-once**, trong đó duplicate delivery có thể xảy ra sau crash/redelivery. Production handler nên có idempotency key hoặc deduplication được kiểm thử riêng.

## 8. Listener: chỉ làm parse và delegation

Tạo `src/main/java/example/messaging/OrderQueueListener.java`:

```java
package example.messaging;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderQueueListener {
    private final OrderEventHandler handler;

    public OrderQueueListener(OrderEventHandler handler) {
        this.handler = handler;
    }

    @RabbitListener(queues = RabbitTopology.ORDER_QUEUE)
    public void accept(String rawPayload) {
        OrderCreated event =
                OrderEventCodec.decode(rawPayload);

        handler.handle(event);
    }
}
```

**Chức năng của listener thực sự chỉ gồm hai bước**: deserialize/validate `rawPayload` rồi gọi `handler.handle`. Vì thế ta có thể unit test trực tiếp constructor injection mà không cần Spring context.

Khi chạy với Spring AMQP:

- Annotation `@RabbitListener` được listener endpoint infrastructure tìm và tạo consumer trên queue.
- Message converter chuyển AMQP message body thành String theo content-type/encoding tương ứng. Trong ví dụ, `RabbitTemplate.convertAndSend(..., String)` và default `SimpleMessageConverter` xử lý String message.
- Nếu `decode` hoặc `handler.handle` ném exception, exception đi ra listener adapter/container. Lúc đó **cấu hình retry/requeue/DLQ** (không phải JUnit) quyết định số phận delivery.
- Không bắt mọi `Exception` rồi chỉ log và return bình thường: với AUTO ack, return thành công có thể khiến message được ACK dù chưa xử lý xong, dẫn đến mất sự kiện.

**Một quy tắc hữu ích:** dùng unit test để khẳng định listener không nuốt lỗi. Dùng broker integration để khẳng định lỗi thật được xử lý theo chính sách broker.

## 9. RabbitMQ topology: exchange, queue, binding và DLQ

Tạo `src/main/java/example/messaging/RabbitTopology.java`:

```java
package example.messaging;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RabbitTopology {
    public static final String ORDER_EXCHANGE =
            "lesson.orders.exchange";
    public static final String ORDER_QUEUE =
            "lesson.orders.queue";
    public static final String ORDER_ROUTING =
            "lesson.orders.created";

    public static final String DEAD_EXCHANGE =
            "lesson.orders.dlx";
    public static final String DEAD_QUEUE =
            "lesson.orders.dead";
    public static final String DEAD_ROUTING =
            "lesson.orders.failed";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(
                ORDER_EXCHANGE, true, false);
    }

    @Bean
    DirectExchange deadExchange() {
        return new DirectExchange(
                DEAD_EXCHANGE, true, false);
    }

    @Bean
    Queue ordersQueue() {
        return QueueBuilder.durable(ORDER_QUEUE)
                .deadLetterExchange(DEAD_EXCHANGE)
                .deadLetterRoutingKey(DEAD_ROUTING)
                .build();
    }

    @Bean
    Queue deadQueue() {
        return QueueBuilder.durable(DEAD_QUEUE).build();
    }

    @Bean
    Binding orderBinding(
            @Qualifier("ordersQueue") Queue queue,
            @Qualifier("ordersExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange)
                .with(ORDER_ROUTING);
    }

    @Bean
    Binding deadBinding(
            @Qualifier("deadQueue") Queue queue,
            @Qualifier("deadExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange)
                .with(DEAD_ROUTING);
    }
}
```

**Giải thích topology:**

1. Producer publish đến `lesson.orders.exchange` kèm routing key `lesson.orders.created`.
2. Direct exchange có binding tới `lesson.orders.queue` với đúng key.
3. `@RabbitListener(queues=ORDER_QUEUE)` tiêu thụ queue này.
4. Nếu listener fail và delivery bị **reject mà không requeue**, RabbitMQ dùng dead-letter exchange được khai báo trên queue để route message tới `lesson.orders.dead`.
5. Dead-letter queue **không có listener tự động xử lý** trong ví dụ; test có thể đọc từ nó bằng RabbitTemplate để kiểm tra.

**Tại sao dùng `@Qualifier`?** Configuration có **hai beans loại Queue** và **hai beans loại DirectExchange**. Không thể inject chỉ theo type mà chắc chắn chọn đúng queue/exchange; `@Qualifier("ordersQueue")` và `@Qualifier("deadQueue")` buộc binding trỏ tới đúng bean.

Spring AMQP có `RabbitAdmin` để khai báo queue/exchange/binding bean trên broker khi connection được tạo. Với Spring Boot starter AMQP và dynamic declaration mặc định phù hợp, topology được tạo trên RabbitMQ container trong integration test. Nếu bạn tắt dynamic declaration hoặc thay administration policy, phải khai báo topology bằng hạ tầng ngoài và điều chỉnh test theo contract.

**Lưu ý production:** định nghĩa topology bằng beans là một pattern, không phải bắt buộc. Một số tổ chức quản lý exchanges/queues qua Terraform/Helm/operator. Lúc ấy integration test phải dùng topology giống môi trường đích, đặc biệt durability, queue type, arguments, DLX và permissions.

## 10. Unit test listener: không Spring, không RabbitMQ

Tạo `src/test/java/example/messaging/OrderQueueListenerUnitTest.java`:

```java
package example.messaging;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class OrderQueueListenerUnitTest {

    @Test
    void delegatesValidEventToHandler() {
        OrderEventHandler handler =
                mock(OrderEventHandler.class);
        OrderQueueListener listener =
                new OrderQueueListener(handler);

        listener.accept("ORD-7|2");

        verify(handler).handle(
                new OrderCreated("ORD-7", 2));
    }

    @Test
    void rejectsZeroQuantityWithoutCallingHandler() {
        OrderEventHandler handler =
                mock(OrderEventHandler.class);
        OrderQueueListener listener =
                new OrderQueueListener(handler);

        assertThrows(
                IllegalArgumentException.class,
                () -> listener.accept("ORD-7|0"));

        verifyNoInteractions(handler);
    }

    @Test
    void rejectsMalformedWireMessageWithoutDelegation() {
        OrderEventHandler handler =
                mock(OrderEventHandler.class);
        OrderQueueListener listener =
                new OrderQueueListener(handler);

        assertThrows(
                IllegalArgumentException.class,
                () -> listener.accept("invalid-payload"));

        verifyNoInteractions(handler);
    }

    @Test
    void doesNotSwallowBusinessHandlerFailure() {
        OrderEventHandler handler =
                mock(OrderEventHandler.class);
        OrderQueueListener listener =
                new OrderQueueListener(handler);

        doThrow(new IllegalStateException(
                "storage unavailable"))
                .when(handler)
                .handle(new OrderCreated("ORD-9", 1));

        assertThrows(
                IllegalStateException.class,
                () -> listener.accept("ORD-9|1"));

        verify(handler).handle(
                new OrderCreated("ORD-9", 1));
    }
}
```

**Bốn tests chạy không cần Docker**, không khởi động Spring context, không mở cổng TCP:

- `delegatesValidEventToHandler`: parser tạo đúng domain record và gọi đúng collaborator.
- `rejectsZeroQuantityWithoutCallingHandler`: validation từ chối message sai, business handler không bị gọi.
- `rejectsMalformedWireMessageWithoutDelegation`: malformed payload không được “đoán sửa” rồi xử lý.
- `doesNotSwallowBusinessHandlerFailure`: exception được đẩy ra ngoài listener method, để listener container áp policy của nó.

**Ranh giới kết luận:** test cuối **không chứng minh** RabbitMQ reject/requeue/DLQ. Nó chỉ chứng minh Java method ném exception. Bản thân Mockito mock không kết nối broker.

**Không đặt `@SpringBootTest` ở đây**: nó làm unit test chậm, phụ thuộc Docker/config và tăng rủi ro lỗi startup không liên quan business logic. Nếu muốn kiểm tra annotation scanning/AOP listener registry, đó là integration test ở tầng Spring.

## 11. Unit test codec để giữ contract rõ

Tạo `src/test/java/example/messaging/OrderEventCodecTest.java`:

```java
package example.messaging;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderEventCodecTest {

    @Test
    void encodeAndDecodeRoundTrip() {
        OrderCreated original =
                new OrderCreated("ORD-123", 100);

        String payload = OrderEventCodec.encode(original);

        assertEquals("ORD-123|100", payload);
        assertEquals(
                original, OrderEventCodec.decode(payload));
    }

    @Test
    void quantityAboveMaxIsRejected() {
        assertThrows(
                IllegalArgumentException.class,
                () -> OrderEventCodec.decode("ORD-7|101"));
    }

    @Test
    void nonNumericQuantityIsRejected() {
        assertThrows(
                IllegalArgumentException.class,
                () -> OrderEventCodec.decode("ORD-7|oops"));
    }
}
```

**Ba tests** xác nhận encoder/decoder nhất quán, upper boundary và type mismatch. Đây là nơi tốt để bổ sung cases min/max, missing/blank, malformed Unicode, version/schema khi message format phát triển. Nhưng một codec test vẫn không bảo vệ **AMQP content-type/headers, listener binding, DLQ**, nên cần integration test.

## 12. Integration test: RabbitMQ thật bằng Testcontainers

Tạo `src/test/java/example/messaging/RabbitBrokerIntegrationTest.java`:

```java
package example.messaging;

import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.NONE,
        properties = {
                "spring.rabbitmq.dynamic=true",
                "spring.rabbitmq.listener.simple.default-requeue-rejected=false",
                "spring.rabbitmq.listener.simple.concurrency=1",
                "spring.rabbitmq.listener.simple.max-concurrency=1"
        })
class RabbitBrokerIntegrationTest {

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer(
                    DockerImageName.parse(
                            "rabbitmq:4.1-management-alpine"));

    @Autowired
    private RabbitTemplate template;

    @Autowired
    private InMemoryOrderHandler handler;

    private static String newOrderId() {
        return "ORD-" + UUID.randomUUID();
    }

    @Test
    void messageTravelsThroughRealBrokerToListener()
            throws Exception {
        assertTrue(rabbit.isRunning());

        String id = newOrderId();
        OrderCreated event = new OrderCreated(id, 2);
        CompletableFuture<OrderCreated> arrived =
                handler.watch(id);

        template.convertAndSend(
                RabbitTopology.ORDER_EXCHANGE,
                RabbitTopology.ORDER_ROUTING,
                OrderEventCodec.encode(event));

        OrderCreated actual =
                arrived.get(10, TimeUnit.SECONDS);

        assertEquals(event, actual);
        assertEquals(1, handler.processedTimes(id));
    }

    @Test
    void independentKeysDoNotDependOnDeliveryOrder()
            throws Exception {
        String firstId = newOrderId();
        String secondId = newOrderId();

        CompletableFuture<OrderCreated> first =
                handler.watch(firstId);
        CompletableFuture<OrderCreated> second =
                handler.watch(secondId);

        template.convertAndSend(
                RabbitTopology.ORDER_EXCHANGE,
                RabbitTopology.ORDER_ROUTING,
                OrderEventCodec.encode(
                        new OrderCreated(firstId, 1)));

        template.convertAndSend(
                RabbitTopology.ORDER_EXCHANGE,
                RabbitTopology.ORDER_ROUTING,
                OrderEventCodec.encode(
                        new OrderCreated(secondId, 100)));

        assertEquals(
                new OrderCreated(firstId, 1),
                first.get(10, TimeUnit.SECONDS));
        assertEquals(
                new OrderCreated(secondId, 100),
                second.get(10, TimeUnit.SECONDS));

        assertEquals(1, handler.processedTimes(firstId));
        assertEquals(1, handler.processedTimes(secondId));
    }

    @Test
    void invalidMessageIsRejectedToDeadLetterQueue()
            throws Exception {
        String id = newOrderId();
        String invalid = id + "|0";

        // Producer cố ý bỏ qua encode(): cần gửi
        // payload sai để kiểm tra broker failure path.
        template.convertAndSend(
                RabbitTopology.ORDER_EXCHANGE,
                RabbitTopology.ORDER_ROUTING,
                invalid);

        // Consumer fail; requeue=false; queue có DLX.
        Message dead = template.receive(
                RabbitTopology.DEAD_QUEUE,
                10_000L);

        assertNotNull(dead);
        assertEquals(
                invalid,
                new String(
                        dead.getBody(),
                        StandardCharsets.UTF_8));
        assertTrue(
                dead.getMessageProperties()
                        .getHeaders()
                        .containsKey("x-death"));

        assertEquals(0, handler.processedTimes(id));
    }
}
```

**Ba test methods** này thật sự kết nối tới một RabbitMQ Docker container:

1. **Valid delivery:** publish qua `RabbitTemplate` đến đúng exchange và routing key, RabbitMQ route tới queue; Spring listener container dispatch vào `@RabbitListener`; handler nhận domain event. Test đợi Future theo event ID với timeout rõ.
2. **Hai keys độc lập:** không phụ thuộc event nào đến trước. Test chờ từng Future theo ID, tránh assert một order không được cam kết cho mọi cấu hình broker/concurrency.
3. **Invalid message → DLQ:** gửi raw quantity 0; `OrderEventCodec.decode` ném `IllegalArgumentException`; listener container được cấu hình `default-requeue-rejected=false`, nên message bị reject không requeue, RabbitMQ DLX route tới `lesson.orders.dead`. Test đọc message thực từ DLQ và kiểm tra body + header `x-death`.

**Quan sát chuyên môn:** `template.receive(DEAD_QUEUE, 10_000L)` **lấy message ra khỏi DLQ** để test kiểm tra. Nó không chỉ “peek” vào queue. Đây là hành vi chủ ý để dọn message test. Không áp dụng trực tiếp thao tác consume này trong observability production nếu bạn chỉ muốn đo queue depth.

### Vì sao dùng CompletableFuture thay Thread.sleep?

Việc consume message là **asynchronous**. Một unit test gọi Java method trả về ngay; một integration test publish vào broker rồi có thể phải chờ:

- Connection/broker handshake.
- Exchange routing và queue delivery.
- Listener container poll/dispatch.
- Message conversion và business handler.
- ACK/reject/DLX theo error policy.

Dùng `Thread.sleep(500)` rồi assert map thường flaky: máy dev nhanh thì pass, CI chậm thì fail. `CompletableFuture.get(10, TimeUnit.SECONDS)` **chờ tín hiệu thực sự** của handler, có timeout hữu hạn. Với failure path, `RabbitTemplate.receive(queue, timeout)` chờ message xuất hiện trong DLQ theo broker state.

**Cảnh báo:** `CompletableFuture.get` timeout không tự hủy consumer task. Nếu integration test đang dùng một shared broker và consumer xử lý sau timeout, có thể để lại message sang test khác. Dùng riêng container/test queues hoặc cleanup/reconciliation theo policy để đảm bảo isolation.

### Broker test này đã và chưa chứng minh gì?

**Đã chứng minh khi pass:** Testcontainers RabbitMQ khởi động; Boot kết nối; topology được khai báo; producer gửi payload String; exchange/routing/queue hoạt động; Spring @RabbitListener nhận; handler được gọi; invalid message bị reject và có thể quan sát ở DLQ theo config test.

**Chưa chứng minh:** producer confirm/publisher returns, durable persistence sau broker restart, exactly-once, end-to-end DB transaction, idempotency dưới redelivery thật, TLS/network production, cluster quorum queue, consumer crash/reconnect, mọi header/schema version hoặc multi-consumer throughput.

**Cũng chưa chứng minh ACK hoàn tất ở broker cho success path** chỉ vì `handler.watch(...).get(...)` đã hoàn thành: signal có thể được complete **trước khi container gửi ACK**. Nếu cần test ACK bền vững, hãy bổ sung một kịch bản kiểm tra queue delivery/unacked metrics hoặc redelivery/restart semantics có đồng bộ phù hợp.

## 13. Tại sao @ServiceConnection quan trọng?

Trong Spring Boot 3.5, `@ServiceConnection` trên `RabbitMQContainer` cung cấp **`RabbitConnectionDetails`** cho Spring AMQP auto-configuration. Vì vậy test không phải tự viết `spring.rabbitmq.host/port/username/password` từ một random mapped port.

Vai trò các annotation tách biệt:

| Cơ chế | Tác dụng |
| --- | --- |
| `@Testcontainers` | Đăng ký Testcontainers JUnit Jupiter extension |
| Static `@Container` | Start/stop RabbitMQ theo **test class** |
| `@ServiceConnection` | Boot tạo RabbitMQ connection details từ container |
| `@SpringBootTest(webEnvironment=NONE)` | Tải Spring context và listener/handler/topology |
| `@EnableRabbit` | Bật annotation-driven Rabbit listener infrastructure |
| `@RabbitListener` | Đăng ký listener endpoint cho queue |
| `RabbitTemplate` | Publish/receive messages qua AMQP |
| `spring.rabbitmq.listener.simple.default-requeue-rejected=false` | Khi listener fail, reject thay vì requeue mặc định |
| DLX/binding của `RabbitTopology` | Broker định tuyến rejected message đến DLQ |

Nếu dùng Spring Boot/Testcontainers version không hỗ trợ `@ServiceConnection`, có thể dùng `@DynamicPropertySource` để đăng ký host/port/credentials động. Chọn một cách nhất quán; đừng hardcode `localhost:5672` vì Testcontainers dùng mapped port.

**Đặc biệt:** trong Testcontainers 2.x, artifact/group package có thay đổi. Ví dụ này cố ý nhắm Boot 3.5/Testcontainers 1.x. Với một project mới trên Boot 4/Testcontainers 2.x, điều chỉnh dependency/import theo BOM version chứ không trộn hai nhánh.

## 14. @RabbitListenerException: requeue, retry và DLQ

Trong Spring AMQP, cần tách ba ý:

1. **Exception từ listener:** Java code không xử lý được message.
2. **Listener container policy:** có retry advice hay không, sau lỗi sẽ nack/reject/requeue như thế nào.
3. **Broker routing:** message bị reject mà không requeue có dead-letter exchange/queue hay không.

**Không phải cứ throw exception là tự vào DLQ.** Với listener container thông dụng khi retry disabled, thuộc tính default requeue rejected thường **true**: message lỗi có thể bị redeliver lặp lại. Nếu bật retry, chính sách retry/recoverer cũng ảnh hưởng kết quả. Trong bài, test đặt rõ:

```properties
spring.rabbitmq.listener.simple.default-requeue-rejected=false
spring.rabbitmq.listener.simple.concurrency=1
spring.rabbitmq.listener.simple.max-concurrency=1
```

và topology có `x-dead-letter-exchange`/`x-dead-letter-routing-key`. Nhờ cả hai phần, một message quantity 0 mới đi vào DLQ.

### Ack không đồng nghĩa handler có side effect bền vững

Với acknowledge mode AUTO:

- Listener trả thành công → listener container có thể ACK message.
- Listener ném exception → container xử lý theo retry/requeue/reject policy.
- Business handler có thể ghi DB rồi ném exception **sau một commit riêng**; redelivery có thể gây side effect lặp.
- RabbitMQ ACK và SQL COMMIT thông thường **không phải một distributed atomic transaction**.

Đây là lý do consumer **idempotent** cần khóa nghiệp vụ hoặc bảng processed-message, và production workflow quan trọng có thể cần transactional outbox/inbox, de-duplication, dead-letter monitoring và compensating actions.

### Một test retry cần kiểm tra những gì?

Nếu ứng dụng yêu cầu retry ba lần rồi DLQ:

- Cấu hình retry policy rõ số attempts/backoff/recoverer.
- Dùng handler test double có thể đếm attempts một cách thread-safe, không dùng counter không đồng bộ.
- Kiểm tra successful retry trước max và exhaustion → DLQ.
- Tránh timeout quá ngắn, `Thread.sleep` hoặc giả định scheduler luôn nhanh.
- Bảo đảm test không tạo infinite redelivery loop nếu default requeue vẫn true.
- Xác minh số lần chính xác **theo semantics maxAttempts** của framework version; không phỏng đoán off-by-one.
- Nếu retry nhắm database transient errors, test phải có đúng lỗi recoverable/unrecoverable; không retry validation poison message vô hạn.

Bộ runnable tập trung **reject một lần → DLQ**, để kịch bản ổn định. Không tuyên bố đã test retry/backoff khi cấu hình và tests chưa có chúng.

## 15. Publisher test khác consumer test

Unit test listener tập trung consumer method; integration test broker cần phân biệt:

- **Producer-side:** event được serialize đúng, exchange/routing key được chọn đúng, headers cần thiết, publisher confirms/returns nếu contract yêu cầu.
- **Broker topology:** exchange/queue/binding tồn tại, durability, DLX, permissions và routing behavior.
- **Consumer-side:** method được dispatch, payload convert đúng, validation, exception, ack/requeue/retry/DLQ, side effects.
- **End-to-end workflow:** HTTP command/DB transaction phát message, consumer xử lý và cập nhật read model/DB cuối cùng đúng.

Một producer unit test có thể mock `RabbitTemplate`:

```java
verify(template).convertAndSend(
        RabbitTopology.ORDER_EXCHANGE,
        RabbitTopology.ORDER_ROUTING,
        "ORD-7|2");
```

Đây là snippet minh họa bên trong test có `template` là Mockito mock và method production gọi nó; nó kiểm tra **đối số được truyền tới publisher**, nhưng không chứng minh RabbitMQ nhận hoặc route message.

Trong RabbitMQ, message bị publish tới exchange nhưng không route được có thể không tạo exception theo mọi cấu hình. Nếu bắt buộc phát hiện unroutable, cần publisher returns, mandatory flag và confirms theo Spring AMQP/RabbitMQ contract, kèm integration test. Đừng tự suy rằng `RabbitTemplate.convertAndSend(...)` return bình thường nghĩa là message đã được consumer xử lý.

## 16. Tránh “unit test” vô tình mở Spring context

Mục tiêu unit test listener là kiểm tra Java behavior nhỏ nhất. Với thiết kế của ví dụ:

```java
OrderEventHandler handler = mock(
        OrderEventHandler.class);
OrderQueueListener listener =
        new OrderQueueListener(handler);

listener.accept("ORD-7|2");
```

Không cần `@SpringBootTest`, `@MockBean`, `@MockitoBean` hoặc `@Testcontainers`. Nếu thêm full Spring context, test có thể fail vì RabbitMQ chưa có, mặc dù mục tiêu chỉ là parser/delegation.

**Khi nào cần Spring context nhưng chưa cần broker?**

- Muốn kiểm tra bean injection/configuration của listener, conversion logic ở Spring messaging adapter, `@RabbitListener` registration hoặc argument resolution.
- Có custom `MessageConverter` và muốn kiểm tra bean được chọn đúng.
- Có AOP advice/validation proxy cần hoạt động qua Spring.

Có thể dùng Spring-focused tests hoặc custom mock connection infrastructure để kiểm tra từng phần, nhưng **đừng gọi chúng là broker integration** nếu RabbitMQ server chưa hề chạy.

**Với Spring Kafka:** `@EmbeddedKafka` dùng broker test chạy trong quá trình test, không phải unit listener trực tiếp; Spring Cloud Stream test binder thường kiểm tra function/binding behavior nhưng **không thay thế một Kafka/RabbitMQ broker thực** khi contract liên quan protocol/delivery. Phải ghi rõ boundary.

## 17. Test JSON schema và header khi production không dùng text demo

Ví dụ payload `ORD-7|2` chủ yếu để học broker. Trong dự án thật, event có thể là JSON:

```json
{
  "eventId": "evt-7",
  "schemaVersion": 2,
  "type": "order.created",
  "orderId": "ORD-7",
  "quantity": 2,
  "occurredAt": "2026-11-08T00:00:00Z"
}
```

Khi chuyển sang JSON, cần test thêm:

1. Producer tạo đúng JSON schema (required/optional fields, enum, decimal/time formats).
2. Message converter/serializer gửi content-type/charset, correlation ID, event type/schema version đúng.
3. Consumer đọc đúng payload theo version mới và xử lý version cũ theo policy backward compatibility.
4. Invalid type, malformed JSON, field thiếu/null, Unicode có hướng xử lý rõ (reject/DLQ hay fallback).
5. Không log toàn bộ payload nếu chứa PII, token, financial data; mask và phân quyền logs.
6. Không dùng raw exception message trong DLQ reason hoặc public response gây lộ secrets.
7. Test rằng duplicate eventId **không** gây xử lý nghiệp vụ hai lần nếu contract at-least-once.

Nếu dùng `Jackson2JsonMessageConverter`/`JacksonJsonMessageConverter`, tên và supported API thay đổi theo Spring AMQP/Spring Boot major version. Kiểm tra dependency BOM và converters thực sự được cấu hình; không chỉ unit test một `ObjectMapper` rồi kết luận AMQP headers đúng.

**Một lớp lỗi điển hình:** message body là JSON hợp lệ nhưng content-type sai, converter của consumer không nhận hoặc mapping kiểu Java không đúng. Unit gọi `listener.accept("...")` không thể phát hiện lỗi ấy; integration qua broker cần kiểm tra delivery thực.

## 18. Test điều gì khi consumer có database?

Khi handler thực lưu dữ liệu:

```text
RabbitMQ delivery
    |
    v
@RabbitListener -> service transaction
    |
    +-- INSERT/UPDATE database
    |
    +-- ACK RabbitMQ (theo container policy)
```

Tại đây cần kiểm tra:

- **Hợp lệ:** message đã được consume, database row xuất hiện và giá trị đúng.
- **Vi phạm validation:** database không thay đổi, message được reject/DLQ hoặc bỏ qua theo contract.
- **Database transient failure:** retry/backoff và số attempts phù hợp.
- **Duplicate delivery:** không tạo record trùng hoặc double-charge.
- **Crash window:** DB có thể commit nhưng ACK chưa gửi; broker redeliver sau restart. Handler phải idempotent.
- **Outbox:** khi một DB transaction tạo event gửi ra broker, bảo đảm không mất sự kiện khi commit DB thành công nhưng publish thất bại.
- **Inbox/deduplication:** consumer có thể lưu eventId đã xử lý cùng transaction với side effect.
- **Poison message:** không retry vô hạn làm backlog/starvation; có DLQ và điều tra có kiểm soát.

**Đừng gắn `@Transactional` lên JUnit test rồi tin consumer thread được rollback**. Với RabbitMQ, `@RabbitListener` thường chạy trên thread của listener container, **không phải test thread**. Dữ liệu commit ở consumer có thể sống qua rollback của JUnit test. Test phải dùng dedicated DB/container và cleanup đúng transaction/lifecycle.

**Trong bộ runnable:** `InMemoryOrderHandler` chỉ cập nhật ConcurrentHashMap cho test synchronization. Nó kiểm tra broker-to-listener, **không kiểm tra persistence/DB transaction**. Muốn học thêm persistence, hãy thay port bằng handler ghi Postgres và thêm Testcontainers PostgreSQL/SQL assertions; không tuyên bố bài đã làm điều đó khi chưa có test.

## 19. Async assertions: cách đợi đúng và tránh flakiness

Một test messaging sai thường là:

```java
template.convertAndSend(...);
Thread.sleep(200);
assertEquals(1, results.size());
```

Đây là anti-pattern (không phải code hoàn chỉnh): sleep dựa trên thời gian đoán. Trên CI chậm, consumer có thể chưa start/kết nối; trên máy nhanh, sleep làm test vô ích.

Thay bằng:

- `CompletableFuture` được hoàn thành khi handler thực sự xử lý event.
- `BlockingQueue.poll(timeout, unit)` nếu chỉ cần lấy từng receipt (chú ý không phụ thuộc thứ tự).
- Awaitility với predicate được đồng bộ nếu project đã dùng dependency ấy.
- Kafka-specific consumer polling/record assertions theo thư viện test phù hợp.
- Đối với DLQ, dùng broker receive có timeout như `RabbitTemplate.receive(queue, timeout)`.

**Tín hiệu phải phản ánh đúng điều cần kết luận**. Nếu handler complete Future trước DB commit, Future pass không chứng minh DB đã commit. Nếu muốn kiểm tra consumer đã xử lý trọn transaction, hãy quan sát DB từ connection/transaction riêng hoặc event “committed” được phát sau transaction completion.

**Timeout là failure, không phải proof of absence:** một Future chưa complete trong 10 giây có thể do broker chưa sẵn sàng, routing sai, listener không đăng ký, converter lỗi hoặc resource thiếu. Test nên có logs/diagnostics để phân loại, không chỉ tăng timeout vô hạn.

## 20. Dữ liệu test độc lập và không kiểm thử theo thứ tự

Trong `RabbitBrokerIntegrationTest`, mỗi valid event dùng ID dạng `"ORD-" + UUID.randomUUID()`. Điều này giúp:

- Future chờ đúng event, không nhận tín hiệu của test khác.
- Counter `processedTimes(id)` được kiểm tra trên ID mới.
- Không dựa vào test A chạy trước để setup data của test B.
- Không chạm business records của người dùng/prod.

DLQ test là một exception: nó đọc từ **một queue dùng chung trong test class**. Với đúng ba tests trong ví dụ, chỉ một test cố ý gửi invalid payload; container được sở hữu riêng bởi class, nên expected dead message rõ. Trong suite lớn có nhiều producers khác, cần queue name riêng/suite, correlation ID hoặc inspect/requeue các messages ngoài scope; **đừng xóa toàn DLQ** chỉ để test pass.

**Không nên**:

- Publish tới queue production trong lúc chạy CI.
- Dùng một RabbitMQ shared giữa các tests có destructive purge ngoài lock/isolation.
- Giả định listener nhận messages theo publish order khi có nhiều consumers, priorities, retries hoặc requeue.
- Assert `processedTimes(id) == 1` là exactly-once guarantee dưới mọi failure.
- Dựa vào `@DirtiesContext` để purge broker: rebuild context không xóa queue messages.
- Dùng container static và cho rằng context cache luôn có lifecycle tương thích.

### Spring TestContext cache và static @Container

Nếu một Spring test class có `static @Container RabbitMQContainer`, JUnit extension dừng nó khi class kết thúc, nhưng Spring có thể cache context/DataSource/connection factory để dùng lại ở class khác có key giống nhau. Khi context tái sử dụng connection details của container đã stop, test suite có thể lỗi không ổn định.

Để share context qua nhiều classes, cân nhắc:

- Container là **Spring test bean** với `@TestConfiguration @Bean @ServiceConnection` để lifecycle sống theo context.
- Shared container owner của cả suite với startup/stop rõ.
- Cô lập contexts/configurations có chủ đích khi các classes dùng brokers khác nhau.
- `@DirtiesContext` có chọn lọc nếu cần đóng context thực sự, nhưng không thay broker data cleanup.

Mô hình nào đúng phụ thuộc Spring TestContext cache, runtime resource ownership và số classes. Với ví dụ **một integration class**, static `@Container` là cách đơn giản.

## 21. Kiểm thử retry, at-least-once và idempotency

Trong hệ messaging thực, test single success delivery là điểm bắt đầu. Các case quan trọng:

### 21.1. Duplicate event

Publish hai lần cùng `eventId` và kiểm tra DB chỉ ghi một business effect. Cần định nghĩa idempotency key và SQL unique constraint hoặc dedup store.

**Không đồng nhất với test hai order IDs khác nhau** của ví dụ. Test đó chỉ kiểm tra independent events, chưa test dedup.

### 21.2. Consumer handler lỗi trước commit

Inject một failure có kiểm soát (ví dụ repository ném transient exception lần đầu), xác minh broker retry/requeue theo config, số attempts và thành công cuối. Với Rabbit listener container, bật retry/nhận biết số attempts theo phiên bản; tránh dùng một infinite requeue loop để mô phỏng “retry”.

### 21.3. Consumer handler lỗi sau commit

Đây là **crash window**: một write DB đã commit nhưng ACK chưa đến broker. Redelivery cùng event phải không double-apply side effect. Đây là lý do idempotency quan trọng hơn mong muốn exactly-once.

### 21.4. Poison message

Payload có schema version không hỗ trợ hoặc dữ liệu không thể parse. Theo policy, message có thể chuyển DLQ một lần, có error metadata an toàn, không requeue vô hạn. Test DLQ ở mục 12 là phiên bản tối giản của case này.

### 21.5. Publisher failure

Khi DB transaction commit một order nhưng publish message không thành công, có nguy cơ event bị mất. Test transactional outbox/inbox và publisher confirm/retry là một boundary khác với test listener; không dùng listener unit test để khẳng định hệ thống có atomicity.

## 22. Khi nào dùng @RabbitListenerTest hoặc test binder?

Spring AMQP có hỗ trợ test infrastructure liên quan listener, bao gồm `@RabbitListenerTest`/listener test harness trong một số versions/configurations, hữu ích để spy/test method invocation và điều phối. Nhưng hãy phân biệt:

- **Method-level unit test:** gọi `new OrderQueueListener(mockHandler).accept(...)`, không broker.
- **Spring listener configuration test:** kiểm tra listener bean/registry, conversions/harness tùy cấu hình; có thể không cần broker thật nếu chỉ test một phần.
- **Broker integration test:** bắt buộc có RabbitMQ server thực (ví dụ Testcontainers) và publish/consume qua AMQP.
- **End-to-end system test:** producer thật, broker thật, consumer thật, database/API side effects thật; cần quản lý nhiều dependencies.

Một **Spring Cloud Stream test binder** kiểm tra binding/function wiring trong process nhưng không tái tạo đầy đủ broker. Nó rất có ích cho fast feedback, song không chứng minh Kafka partition assignment hoặc RabbitMQ DLX hoạt động. Với Kafka, `@EmbeddedKafka` chạy broker test nhưng không phải một listener unit test thuần; Kafka Testcontainers cung cấp môi trường broker trong container và còn yêu cầu kiểm tra topic/consumer-group/offset như hợp đồng.

**Đặt tên test đúng boundary** giúp người đọc không suy luận quá mức từ màu xanh của một test.

## 23. Java 17 demo độc lập: encoder/decoder không cần Docker

Tạo `src/main/java/example/messaging/OrderCodecDemo.java`:

```java
package example.messaging;

public class OrderCodecDemo {
    public static void main(String[] args) {
        OrderCreated event =
                new OrderCreated("ORD-7", 2);

        String encoded = OrderEventCodec.encode(event);
        OrderCreated decoded =
                OrderEventCodec.decode(encoded);

        System.out.println(encoded);
        System.out.println(decoded);

        try {
            OrderEventCodec.decode("ORD-7|0");
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "reject=" + error.getMessage());
        }
    }
}
```

Biên dịch từ root project có **JDK 17+** (không cần Spring/RabbitMQ/Gradle):

```bash
javac -encoding UTF-8 -d out src/main/java/example/messaging/OrderCreated.java src/main/java/example/messaging/OrderEventCodec.java src/main/java/example/messaging/OrderCodecDemo.java
java -cp out example.messaging.OrderCodecDemo
```

Stdout **chính xác**:

```text
ORD-7|2
OrderCreated[orderId=ORD-7, quantity=2]
reject=invalid quantity
```

Demo này thật sự có thể chạy bằng Java SE và giúp bạn phân biệt **logic codec** với **đường giao tiếp qua broker**. Nếu demo pass, không được kết luận exchange/queue/listener đã được tạo vì chương trình **không gọi RabbitTemplate và không mở RabbitMQ**.

## 24. Cách chạy bộ JUnit tests

Unit tests (không cần Docker):

```bash
./gradlew test --tests example.messaging.OrderQueueListenerUnitTest
./gradlew test --tests example.messaging.OrderEventCodecTest
```

Broker integration test (cần Docker chạy RabbitMQ image):

```bash
./gradlew test --tests example.messaging.RabbitBrokerIntegrationTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.messaging.OrderQueueListenerUnitTest"
.\gradlew.bat test --tests "example.messaging.OrderEventCodecTest"
.\gradlew.bat test --tests "example.messaging.RabbitBrokerIntegrationTest"
```

**Kỳ vọng nếu project, Docker image và dependencies khớp phiên bản đã nêu:**

| Test class | Method count | Broker |
| --- | ---: | --- |
| `OrderQueueListenerUnitTest` | 4 | Không |
| `OrderEventCodecTest` | 3 | Không |
| `RabbitBrokerIntegrationTest` | 3 | **RabbitMQ thật qua Testcontainers** |
| **Tổng** | **10** | Có cả hai mức |

Không gán stdout cố định cho Gradle/JUnit vì logs, Docker startup và test runners có thể khác. **Bộ mã được cung cấp để người học chạy; bài viết không tuyên bố đã thực thi Docker tests trong môi trường của người đọc.** Stdout chính xác chỉ áp dụng cho `OrderCodecDemo` chạy Java SE.

### Phân loại failure nhanh

- Unit codec fail → rule/parse format hoặc expected record.
- Unit listener fail → delegation, error propagation, Mockito setup.
- Docker không start → Docker daemon/image/resource, chưa thể kết luận Rabbit listener sai.
- Spring context fail → Boot dependency/autoconfiguration/connection details/topology.
- Message không tới handler → exchange/routing/binding, listener container, converter, consumer startup.
- Message lỗi liên tục requeue → `defaultRequeueRejected`/retry policy chưa đúng.
- Invalid payload không có ở DLQ → kiểm tra DLX/queue binding, requeue policy, listener exception và broker logs.
- Test chờ Future timeout → kiểm tra async delivery end-to-end; không tự tăng sleep.
- Chạy riêng pass nhưng suite fail → context caching, shared queues, test data contamination hoặc consumer concurrency.

## 25. Anti-patterns thường gặp

**1. Chỉ gọi listener method trực tiếp rồi khẳng định “broker integration đã pass”.** Không có network/queue/consumer container.

**2. Mock RabbitTemplate và khẳng định message đã deliver.** Verify invocation chỉ kiểm tra lời gọi producer, không kiểm tra broker routing.

**3. Mock business handler trong mọi test rồi quên test side effect thật.** Mockito không chứng minh DB commit/rollback hoặc persistence mapping.

**4. Catch mọi exception trong listener rồi return.** AUTO ack có thể báo success dù event không được xử lý, làm mất message.

**5. Nghĩ exception mặc định tự vào DLQ.** Còn phụ thuộc requeue, retry/recoverer và topology DLX. Không cấu hình rõ có thể gây vòng redelivery.

**6. Chỉ assert handler được gọi một lần rồi tuyên bố exactly-once.** At-least-once và crash window vẫn có thể gây duplicate.

**7. Sử dụng Thread.sleep để đợi consumer.** Flaky dưới CI load; dùng Future/BlockingQueue/broker receive có timeout.

**8. Tạo một consumer khác để “peek” main queue.** Nó có thể cướp message từ listener production test, khiến assertion không nhất quán; dùng quan sát side effect/signal phù hợp.

**9. Không kiểm tra routing key và exchange.** Publish có thể đi vào exchange sai, queue không nhận; unit không bắt được.

**10. Đọc DLQ nhưng quên message bị remove.** Test có thể vô tình tiêu thụ forensic data; chỉ làm trong queue test riêng.

**11. Dùng persistent queue cố định chung với integration tests chạy parallel.** Dữ liệu lỗi trộn nhau, test đọc nhầm DLQ message.

**12. Dùng test `@Transactional` và tin consumer thread rollback cùng test.** Consumer chạy thread/transaction riêng.

**13. Dùng @DirtiesContext để purge RabbitMQ queues.** Nó thay Spring context, không xóa broker committed state.

**14. Không chờ async task hoàn tất trước teardown container.** Message có thể đến sau cleanup hoặc container bị stop giữa lúc xử lý.

**15. Tưởng Testcontainers broker giống cluster production.** Cluster, TLS, auth, quorum queues, network latency và broker config có thể khác.

**16. Gửi malformed JSON nhưng chỉ kiểm tra listener parse raw String.** JSON converter/headers/schema handling chưa được test.

**17. Không test error path.** Message hợp lệ thành công không chứng minh retry/DLQ đúng, poison message có thể làm backlog.

**18. Không version event contract.** Consumer có thể vỡ khi producer thêm/bỏ fields hoặc đổi enum.

**19. Đặt timeout quá thấp rồi cho rằng code sai.** Container startup, queue declaration và async dispatch cần budget hợp lý; phân loại lỗi.

**20. Dùng production credentials/broker trong CI.** Test integration phải có môi trường biệt lập và data an toàn.

## 26. Checklist QA cho Messaging listener tests

**Unit test boundary:**

- Listener có constructor injection để test trực tiếp không?
- Có test valid payload, boundary invalid, malformed payload?
- Có verify collaborator được gọi với đúng argument không?
- Có `verifyNoInteractions` khi parse invalid không?
- Lỗi của business handler có được truyền ra thay vì swallow không?
- Unit test có chạy không cần Spring context hoặc Docker không?

**Broker integration boundary:**

- Có broker thật (RabbitMQContainer/Kafka) hay chỉ mock/test binder?
- Listener annotation đã được Spring phát hiện và queue/topic có đúng?
- Exchange, queue, binding/routing key hoặc topic/group/partition có được kiểm tra?
- Producer có gửi qua real client/template, không mock?
- Có chờ delivery bằng tín hiệu có timeout, không `Thread.sleep`?
- Có test invalid message → đúng retry/requeue/DLQ policy?
- DLQ test có kiểm tra đúng message body/headers và cô lập queue không?
- Có phân biệt handler signal với broker ACK/DB commit không?
- Có test data/eventId riêng và không phụ thuộc thứ tự chạy không?

**Reliability/production:**

- Consumer có idempotency/dedup policy với at-least-once delivery?
- Test duplicate, transient error, poison message, crash window nếu thuộc contract?
- Database side effects có commit/rollback test riêng nếu dùng DB?
- Schema/content-type/headers/versioning và Unicode có test tương ứng?
- Publisher confirms/returns nếu yêu cầu delivery guarantees?
- Có metrics, tracing, error logging an toàn và không để lộ PII/tokens?
- Container lifecycle có tương thích Spring context cache và parallel CI?
- CI có Docker/network/image, và thiếu Docker fail/skip theo policy?
- Test có chạy unit riêng, broker integration riêng và full suite để bắt state leakage?

**Kết luận:** **unit test listener** bảo vệ logic parse/validation/delegation và exception trên Java method; **integration test qua broker thật** bảo vệ publish, routing, listener container, delivery và error policy. Hai mức không thay thế nhau. Với Spring Boot, kết hợp JUnit/Mockito (nhanh, độc lập) với RabbitMQ Testcontainers (thực tế, bất đồng bộ); kiểm tra DLQ, idempotency, schema và database commit ở boundary tương ứng. Quan trọng nhất: **test xanh phải được diễn giải đúng những gì nó thực sự chạy**.

## 27. Tài liệu tham khảo

- [Spring Boot 3.5 — AMQP Messaging](https://docs.spring.io/spring-boot/3.5/reference/messaging/amqp.html): `@RabbitListener`, `RabbitTemplate`, listener factory và error/requeue config.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection` với `RabbitMQContainer`/connection details.
- [Spring AMQP — Exception Handling](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html): listener exception, requeue, reject, dead-letter behavior.
- [Spring AMQP — Listener Container Attributes](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): `defaultRequeueRejected` và listener container options.
- [Spring AMQP — RabbitListener API](https://docs.spring.io/spring-amqp/api/org/springframework/amqp/rabbit/annotation/RabbitListener.html): annotation setup, queue declarations và consumer config.
- [Testcontainers Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): static `@Container` và extension lifecycle.
- [Testcontainers Java — RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/): broker test dependencies và `RabbitMQContainer`; lưu ý docs hiện hành có thể dùng artifact Testcontainers 2.x trong khi bài nhắm 1.x.
- [Spring Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): broker integration/embedded Kafka và Kafka-specific test utilities.
