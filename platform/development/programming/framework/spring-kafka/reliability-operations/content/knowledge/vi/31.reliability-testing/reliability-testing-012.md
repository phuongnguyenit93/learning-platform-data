# Test consumer idle event trong Spring Kafka

## 1. Bài toán: làm sao biết consumer không nhận được bản ghi mới?

Một ứng dụng Spring Kafka có consumer xử lý đơn hàng, thanh toán hoặc sự kiện đồng bộ dữ liệu. Có những thời điểm topic thực sự không có message mới: buổi đêm, cuối kỳ xử lý, hoặc khi upstream tạm ngừng phát dữ liệu. Nhưng cũng có trường hợp consumer không nhận message vì cấu hình sai, mất kết nối, partition chưa được gán, consumer bị pause hoặc luồng `poll()` có vấn đề.

Trong vận hành, ta cần một tín hiệu cho biết **listener container đã không nhận bản ghi trong một khoảng thời gian**, đồng thời kiểm thử được tín hiệu đó. Spring for Apache Kafka cung cấp `ListenerContainerIdleEvent` cho mục đích này.

```text
Kafka topic / partitions
          |
          v
KafkaConsumer.poll(...)
          |
          +---- Có records ----> @KafkaListener xử lý records
          |                         |
          |                         +--> Nếu trước đó idle:
          |                              ListenerContainerNoLongerIdleEvent
          |
          +---- Không có records liên tục
                    |
                    +---- Qua ngưỡng idleEventInterval
                              |
                              v
                    ListenerContainerIdleEvent
                    (có thể phát lặp khi tiếp tục idle)
```

**Test consumer idle event** là kiểm tra rằng Spring Kafka thực sự phát `ListenerContainerIdleEvent` trong điều kiện không có record được phân phối tới container, và có thể phát `ListenerContainerNoLongerIdleEvent` khi nhận lại dữ liệu. Test cũng cần phân biệt idle hợp lệ với lỗi vận hành, không giả định mọi lần thiếu message đều là consumer hỏng.

Kết quả mong muốn:

- Có cấu hình ngưỡng idle rõ ràng và có thể rút ngắn riêng trong test.
- Event được bắt bằng Spring `@EventListener` hoặc `ApplicationListener`.
- Test xác minh đúng **listener/container**, thời gian idle và hành vi sau khi message xuất hiện trở lại.
- Test không phụ thuộc vào `Thread.sleep(...)` và giả định thời điểm scheduler/poll chính xác tuyệt đối.
- Các ca bất thường như poll không trả về, pause, partition rỗng và concurrent consumers được xét riêng.

## 2. `ListenerContainerIdleEvent` là gì?

`ListenerContainerIdleEvent` thuộc package:

```java
org.springframework.kafka.event.ListenerContainerIdleEvent
```

Khi cấu hình `idleEventInterval`, listener container có thể phát event sau một khoảng thời gian không nhận bản ghi. Nếu vẫn idle, event tiếp tục được phát theo khoảng này, **không phải một sự kiện chỉ xảy ra một lần**.

| Thuộc tính / API | Ý nghĩa |
|---|---|
| `getListenerId()` | ID của listener, hoặc tên container nếu không khai báo listener ID. |
| `getIdleTime()` | Khoảng thời gian container đã idle tính bằng **millisecond** khi event được phát. |
| `getTopicPartitions()` | Các topic-partitions đang được gán cho consumer khi event được tạo. |
| `getConsumer()` | Tham chiếu Kafka `Consumer` nếu có; có ràng buộc thread-safety nghiêm ngặt. |
| `isPaused()` | Consumer có đang ở trạng thái pause khi phát event không. |
| `getContainer()` | Container liên quan tới event; khi concurrency có thể là parent container. |
| `getSource()` | Đối tượng container trực tiếp phát event. |

**Giới hạn:** `getIdleTime()` phản ánh thời gian idle mà container ghi nhận, không phải đồng hồ đảm bảo chính xác tới từng millisecond. Event phụ thuộc vòng lặp poll, scheduling, assignment và trạng thái container. Do đó, assertion nên dùng **điều kiện khoảng thời gian hợp lý và timeout hữu hạn**, thay vì yêu cầu event xuất hiện đúng tại mốc 1.000 ms.

### 2.1. `idleEventInterval` và `idleBeforeDataMultiplier`

`ContainerProperties` có các cấu hình quan trọng:

| Property | Ý nghĩa | Giá trị mặc định thường gặp trong Spring Kafka 3.x |
|---|---|---|
| `idleEventInterval` | Ngưỡng/khoảng thời gian giữa các `ListenerContainerIdleEvent`. | `null`: không phát sự kiện idle container. |
| `idleBeforeDataMultiplier` | Nhân ngưỡng idle **trước khi consumer nhận bản ghi đầu tiên**. | `5.0`. |
| `idlePartitionEventInterval` | Bật sự kiện idle cho **từng partition**. | `null`. |
| `pollTimeout` | Timeout khi `KafkaConsumer.poll(...)`; có thể ảnh hưởng độ trễ phát hiện event. | Tùy phiên bản/cấu hình container. |
| `monitorInterval` | Chu kỳ monitor phát hiện poll không phản hồi, tính bằng giây. | Thường 30 giây. |
| `noPollThreshold` | Hệ số ngưỡng để coi poll không phản hồi so với `pollTimeout`. | Thường `3.0`. |

Ví dụ, nếu `idleEventInterval = 1.000 ms` và `idleBeforeDataMultiplier = 5.0`, một consumer **chưa từng nhận dữ liệu** có thể cần khoảng 5 giây idle trước khi có event đầu tiên. Sau khi đã nhận record, ngưỡng quay về khoảng 1 giây. Đây là nguyên nhân phổ biến khiến test chờ 2 giây rồi thất bại dù cấu hình `idleEventInterval=1s` là đúng.

Trong integration test, ta có thể đặt `idleBeforeDataMultiplier=1.0` để đo hành vi ngay sau startup, hoặc **gửi một record, xác minh listener đã nhận**, rồi mới chờ trạng thái idle. Cách thứ hai gần với vòng đời thực tế hơn khi muốn test chuyển trạng thái active → idle → active.

### 2.2. `idleBetweenPolls` không phải idle event interval

`idleBetweenPolls` dùng để chủ động cho consumer thread nghỉ giữa các lần poll nhằm hạn chế tốc độ phân phối. Nó **không phải cấu hình phát `ListenerContainerIdleEvent`**. Tương tự, Kafka property `max.poll.interval.ms` kiểm soát khoảng thời gian tối đa giữa các lần poll trước khi consumer bị coi là không đáp ứng yêu cầu group, không phải ngưỡng idle message của Spring Kafka.

### 2.3. Event do Spring công bố, không phải message trong Kafka topic

`ListenerContainerIdleEvent` là **Spring `ApplicationEvent` trong cùng ứng dụng**, không phải record được broker tự gửi vào một topic. Nếu muốn gửi cảnh báo ra hệ thống khác, ứng dụng phải chủ động chuyển đổi event thành metric/log/notification qua một service phù hợp.

Vì vậy, không thể test bằng cách đợi Kafka producer gửi một record tên `ListenerContainerIdleEvent`. Cần quan sát **Spring ApplicationContext event bus** hoặc một side effect của handler đã đăng ký.

## 3. Phân biệt idle với những hiện tượng khác

Các event liên quan thường bị nhầm:

| Event / trạng thái | Trigger | Ý nghĩa khi vận hành |
|---|---|---|
| `ListenerContainerIdleEvent` | Container không nhận records quá khoảng idle cấu hình. | Consumer không có bản ghi được phân phối; **không tự chứng minh lỗi**. |
| `ListenerContainerNoLongerIdleEvent` | Một record được nhận sau khi container đã phát idle event. | Consumer đã nhận dữ liệu trở lại. |
| `ListenerContainerPartitionIdleEvent` | Một partition được gán không có records trong khoảng riêng. | Một partition idle dù partition khác vẫn hoạt động. |
| `ListenerContainerPartitionNoLongerIdleEvent` | Partition đã idle bắt đầu nhận record trở lại. | Theo dõi phục hồi ở phạm vi partition. |
| `NonResponsiveConsumerEvent` | Consumer `poll()` không quay lại trong ngưỡng giám sát. | Cần điều tra poll bị block/chậm, khác với poll đều đặn nhưng trả rỗng. |
| Consumer paused | Listener container hoặc consumer đang được pause. | Có thể là trạng thái có chủ đích (backpressure, retry, vận hành). |
| Consumer lag cao | Offset end của broker vượt offset đã commit/tiến độ xử lý. | Consumer có backlog chưa xử lý; không được suy ra chỉ từ event idle. |
| Container stopped | Listener container không chạy. | Không kỳ vọng phát idle events bình thường khi đã dừng. |

Một consumer idle có thể **khỏe mạnh** khi broker không có message. Ngược lại, một consumer có lag cao cũng có thể không nhận record vì assignment, pause, lỗi auth, cấu hình poll hoặc topology. Alert đáng tin cậy cần kết hợp idle event với lag, trạng thái assignment, liveness của container, tốc độ producer và kỳ vọng dữ liệu nghiệp vụ.

## 4. Cấu hình idle event trong Spring Boot

Các ví dụ dưới đây nhắm tới **Java 17+, Spring Boot 3.x và Spring Kafka 3.x**. Dự án dùng Spring Boot 4.x / Spring Kafka 4.x cần đối chiếu API và tên property theo phiên bản tương ứng.

### 4.1. Dùng `application.yml`

Spring Boot hỗ trợ cấu hình listener idle interval bằng property:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-worker
      auto-offset-reset: earliest
    listener:
      idle-event-interval: 60s
      idle-partition-event-interval: 120s
```

Khi cấu hình này được Boot áp dụng cho `ConcurrentKafkaListenerContainerFactory` do Boot quản lý, container có thể phát `ListenerContainerIdleEvent` nếu không nhận dữ liệu trong 60 giây, và phát idle partition event theo ngưỡng 120 giây khi được hỗ trợ.

Trong production, nên chọn ngưỡng theo **nhịp dữ liệu thật**. Một topic chỉ có message vào cuối ngày không nên bị gắn nhãn incident mỗi phút. Có thể không cấu hình partition idle nếu chỉ cần phát hiện container idle, nhằm giảm event không cần thiết.

### 4.2. Cấu hình trực tiếp `ConcurrentKafkaListenerContainerFactory`

Khi muốn kiểm soát một nhóm listener riêng, có thể cấu hình container factory:

```java
import org.springframework.boot.autoconfigure.kafka.ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
class OrderKafkaListenerConfig {

    @Bean("ordersListenerFactory")
    ConcurrentKafkaListenerContainerFactory<String, String> ordersListenerFactory(
            ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
            ConsumerFactory<String, String> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        configurer.configure(factory, consumerFactory);

        factory.getContainerProperties().setIdleEventInterval(60_000L);
        factory.getContainerProperties().setIdlePartitionEventInterval(120_000L);
        return factory;
    }
}
```

`ConcurrentKafkaListenerContainerFactoryConfigurer` giúp giữ các cấu hình cơ bản mà Spring Boot đã chuẩn bị (deserializers, error handling và nhiều thuộc tính listener) trước khi override các property cụ thể. Với factory hoàn toàn tự tạo, cần tự đảm bảo có `ConsumerFactory` và các thiết lập liên quan.

Khai báo listener:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderMessageListener {

    @KafkaListener(
            id = "ordersConsumer",
            topics = "orders.events",
            groupId = "orders-worker",
            containerFactory = "ordersListenerFactory")
    public void handle(String payload) {
        // Xử lý nghiệp vụ; không dùng message payload làm dữ liệu log vô hạn.
    }
}
```

`id` của listener là khóa tiện để lọc idle events. Trong container concurrency, các child listener IDs có thể mang hậu tố như `ordersConsumer-0`, `ordersConsumer-1`; không nên phụ thuộc tên child chính xác khi chỉ cần kiểm tra cả nhóm listener.

## 5. Bắt idle event với `@EventListener`

Một Spring bean có thể quan sát `ListenerContainerIdleEvent`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
class KafkaIdleObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaIdleObserver.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        if (!event.getListenerId().startsWith("ordersConsumer")) {
            return;
        }

        log.info("kafka.consumer.idle listenerId={} idleMs={} "
                        + "partitions={} paused={}",
                event.getListenerId(),
                event.getIdleTime(),
                event.getTopicPartitions(),
                event.isPaused());
    }
}
```

Spring `ApplicationEvent` được công bố trong cùng `ApplicationContext`. Handler `@EventListener` **có thể nhận event của mọi listener containers** trong context, nên cần lọc theo listener ID, container hoặc điều kiện phù hợp. Nếu không lọc, một test có nhiều listeners có thể pass vì idle event phát từ listener không liên quan.

Cũng có thể viết:

```java
@EventListener(condition = "#event.listenerId.startsWith('ordersConsumer')")
public void onIdle(ListenerContainerIdleEvent event) {
    // Chỉ theo dõi nhóm listener ordersConsumer.
}
```

Khi dùng SpEL trong `condition`, cần phù hợp cú pháp hỗ trợ của Spring Framework và tên tham số; nếu dự án biên dịch không giữ metadata tên tham số, hãy cân nhắc điều kiện đã được tài liệu xác nhận hoặc lọc bằng Java trong thân method như ví dụ đầu để dễ kiểm thử.

### 5.1. Không làm việc nặng trên consumer thread

Theo cơ chế mặc định, event listener thường được gọi trên **thread đang phát event**, tức consumer thread. Nếu handler idle thực hiện HTTP request dài, truy vấn database nặng hoặc `Thread.sleep`, nó có thể trì hoãn vòng lặp `poll()` và gây vấn đề với Kafka consumer group.

Mẫu an toàn hơn:

```text
Consumer thread
   |
   +-- @EventListener -> cập nhật counter / đưa event nhẹ vào queue
                           |
                           v
                      Worker/monitor riêng
                           |
                           +-- Alert / metrics / policy quyết định
```

Khi chỉ cần ghi metric/counter, hãy giữ handler ngắn và không block. Khi phải gửi cảnh báo mạng, bàn giao **metadata đã copy** (listener ID, idle time, partitions) cho executor/queue, không chuyển nguyên `Consumer` sang thread khác để gọi API Kafka tùy tiện.

### 5.2. Không tự stop child container trên callback thread

Nếu policy muốn dừng listener container khi idle, **không gọi `container.stop()` trực tiếp trên consumer thread trong idle handler**. Điều đó có thể gây trì hoãn và log không cần thiết. Với concurrent container, phải điều khiển **parent concurrent listener container** bằng một thread điều phối khác thay vì stop riêng một child container.

Để quản lý, có thể tìm container theo ID qua `KafkaListenerEndpointRegistry`, rồi yêu cầu thao tác từ task executor chuyên dụng sau khi đã xác định rõ cần stop hay không. Idle bình thường không phải lý do đủ để tự stop/restart.

## 6. Phần kiểm thử quan trọng: có record, chuyển sang idle, rồi hoạt động lại

Một integration test đáng tin cậy cần chứng minh cả ba sự kiện logic:

```text
[A] Consumer nhận message -> chứng minh consumer đã được gán partition
               |
               v
[B] Không gửi thêm message -> nhận ListenerContainerIdleEvent
               |
               v
[C] Gửi message mới -> consumer nhận +
    ListenerContainerNoLongerIdleEvent
```

Trình tự này tốt hơn việc chỉ chạy ứng dụng với topic rỗng rồi chờ vài trăm ms, vì test còn xác minh consumer thực sự có thể nhận dữ liệu. Nó cũng tránh hiểu nhầm **startup idle multiplier mặc định 5x** khi chưa có bất kỳ record nào.

### 6.1. Dependencies trong Gradle

Ví dụ `build.gradle` dạng Groovy với plugin/BOM Spring Boot quản lý phiên bản:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-kafka-test` cung cấp `@EmbeddedKafka` và các tiện ích test. Nếu ứng dụng đã dùng Spring Kafka thông qua starter/dependency khác thì giữ cấu trúc dependency của dự án; không thêm trùng nhiều phiên bản Kafka clients không tương thích. Bài này **không yêu cầu chạy Gradle để triển khai lý thuyết**, nhưng trong dự án thật, integration test phải được thực thi trên môi trường có Kafka embedded hoặc container theo cấu hình build.

### 6.2. Một integration test hoàn chỉnh với `@EmbeddedKafka`

Ví dụ sau dành cho **Spring Boot 3.x / Spring Kafka 3.x / JUnit 5**, sử dụng broker embedded với một topic riêng. Trong test, cấu hình `idleEventInterval=500ms`, `idleBeforeDataMultiplier=1.0` và `pollTimeout=100ms` để giảm thời gian chờ. Những giá trị ngắn này **chỉ phục vụ test**, không nên dùng mặc định trong production.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.kafka.ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.kafka.test.context.EmbeddedKafka;

@SpringBootTest(
        classes = ConsumerIdleEventIT.TestApplication.class,
        properties = {
                "spring.kafka.consumer.auto-offset-reset=earliest",
                "spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
                "spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
                "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
                "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer"
        })
@EmbeddedKafka(
        partitions = 1,
        topics = "orders-idle-it",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class ConsumerIdleEventIT {

    @org.springframework.beans.factory.annotation.Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @org.springframework.beans.factory.annotation.Autowired
    IdleOrdersConsumer consumer;

    @org.springframework.beans.factory.annotation.Autowired
    IdleEventProbe events;

    @Test
    void emitsIdleAndNoLongerIdleAfterNewRecord() throws Exception {
        kafkaTemplate.send("orders-idle-it", "first").get(10, TimeUnit.SECONDS);

        // Xác nhận listener thực sự đang consume trên broker test.
        assertEquals("first", consumer.messages.poll(15, TimeUnit.SECONDS));

        // Bỏ các sự kiện idle có thể đã phát trước record đầu tiên.
        events.idle.clear();

        ListenerContainerIdleEvent idle =
                events.idle.poll(15, TimeUnit.SECONDS);

        assertNotNull(idle, "Consumer should become idle");
        assertTrue(idle.getListenerId().startsWith("ordersIdleListener"));
        assertTrue(idle.getIdleTime() >= 500L);

        // Chỉ kiểm tra event phục hồi được phát SAU idle đã xác nhận.
        events.noLongerIdle.clear();
        kafkaTemplate.send("orders-idle-it", "second")
                .get(10, TimeUnit.SECONDS);

        assertEquals("second", consumer.messages.poll(15, TimeUnit.SECONDS));

        ListenerContainerNoLongerIdleEvent resumed =
                events.noLongerIdle.poll(15, TimeUnit.SECONDS);

        assertNotNull(resumed, "Consumer should leave idle state");
        assertTrue(resumed.getListenerId().startsWith("ordersIdleListener"));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableKafka
    @Import({IdleKafkaTestConfig.class, IdleOrdersConsumer.class, IdleEventProbe.class})
    static class TestApplication {
    }

    @TestConfiguration
    static class IdleKafkaTestConfig {

        @Bean("idleListenerFactory")
        ConcurrentKafkaListenerContainerFactory<String, String> idleListenerFactory(
                ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
                ConsumerFactory<String, String> consumerFactory) {

            var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
            configurer.configure(factory, consumerFactory);
            factory.getContainerProperties().setIdleEventInterval(500L);
            factory.getContainerProperties().setIdleBeforeDataMultiplier(1.0);
            factory.getContainerProperties().setPollTimeout(100L);
            return factory;
        }
    }

    static class IdleOrdersConsumer {

        final BlockingQueue<String> messages = new LinkedBlockingQueue<>();

        @KafkaListener(
                id = "ordersIdleListener",
                topics = "orders-idle-it",
                groupId = "orders-idle-it-group",
                containerFactory = "idleListenerFactory")
        public void consume(String payload) {
            messages.offer(payload);
        }
    }

    static class IdleEventProbe {

        final BlockingQueue<ListenerContainerIdleEvent> idle =
                new LinkedBlockingQueue<>();
        final BlockingQueue<ListenerContainerNoLongerIdleEvent> noLongerIdle =
                new LinkedBlockingQueue<>();

        @EventListener
        public void onIdle(ListenerContainerIdleEvent event) {
            if (event.getListenerId().startsWith("ordersIdleListener")) {
                idle.offer(event);
            }
        }

        @EventListener
        public void onNoLongerIdle(ListenerContainerNoLongerIdleEvent event) {
            if (event.getListenerId().startsWith("ordersIdleListener")) {
                noLongerIdle.offer(event);
            }
        }
    }
}
```

Các nested classes `IdleOrdersConsumer` và `IdleEventProbe` được đăng ký vào Spring context thông qua `@Import`, nên `@KafkaListener` và `@EventListener` có hiệu lực. `ConcurrentKafkaListenerContainerFactoryConfigurer` lấy cấu hình cơ sở từ Spring Boot và gắn `ConsumerFactory`; sau đó test override ba thông số liên quan idle.

**Giải thích lựa chọn trong test:**

1. `@EmbeddedKafka` tạo broker thử nghiệm, không kết nối Kafka production. `bootstrapServersProperty` chuyển địa chỉ embedded broker vào `spring.kafka.bootstrap-servers`.
2. `KafkaTemplate.send(...).get(timeout)` xác nhận phía producer gửi được message tới broker, **không thay cho assertion consumer đã xử lý**.
3. `consumer.messages.poll(timeout)` chờ dữ liệu được listener thực sự nhận. Không dùng sleep cố định để đoán consumer đã được assign partition.
4. Sau record đầu tiên, test chờ `ListenerContainerIdleEvent` và kiểm tra `listenerId`/`idleTime`.
5. Sau khi xác nhận idle, test gửi record thứ hai và chờ event `ListenerContainerNoLongerIdleEvent`.
6. Handler event chỉ `offer` vào queue, **không block consumer thread**. Test method mới thực hiện chờ bằng `poll(timeout)`.
7. Các assertion có timeout hữu hạn giúp test không treo vô hạn nếu Kafka hoặc container không khởi động được.

Đây là ví dụ dành cho một integration-test context riêng. Khi project đã có `@SpringBootApplication` và cấu hình listener thật, có thể dùng `@SpringBootTest` với cấu hình production thay vì tự định nghĩa `TestApplication`; cần tránh vô tình khởi động thêm những listener khác cũng đọc topic test. Trong một test suite chạy song song, mỗi test nên dùng topic/group ID riêng hoặc bảo đảm fixture/offset và `ApplicationContext` được cô lập.

### 6.3. Chống flaky test do thời gian và điều phối

Một test timer-based không thể đảm bảo Kafka poll và thread scheduling đúng một mốc millisecond. Vì vậy:

- **Không** assert rằng idle event phải đến chính xác tại 500 ms.
- **Không** dùng `Thread.sleep(500)` rồi yêu cầu đã có event.
- **Không** dùng một `CountDownLatch` cũ của test khác mà không reset.
- **Có** dùng `BlockingQueue.poll(15, TimeUnit.SECONDS)` hoặc Awaitility để đợi điều kiện trong thời gian giới hạn.
- **Có** lọc đúng listener ID, nhất là khi Spring context có nhiều containers.
- **Có** đảm bảo consumer đã nhận record nếu đang test active → idle.
- **Có** xem đến `idleBeforeDataMultiplier` khi test startup idle trước record đầu.
- **Có** dành timeout đủ rộng cho broker embedded khởi động, partition assignment và CI chậm.

Một kiểm tra “không có idle event trong 500 ms đầu tiên” thường dễ nhiễu do thời điểm container bắt đầu poll trước khi test bắt đầu đếm. Nếu cần kiểm tra ranh giới thời gian, dùng cơ chế clock/test seam ở logic ứng dụng hoặc điều kiện kiểm thử có dung sai rõ, thay vì giả định đồng hồ test và consumer bắt đầu cùng một lúc.

## 7. Unit test cho handler, không cần Kafka broker

Integration test xác nhận framework thực sự phát event. Unit test tập trung vào code **xử lý** event: lọc theo listener ID, tạo metric, tăng counter, đưa cảnh báo vào hàng đợi.

Ví dụ handler thuần, không dùng `@EventListener` để unit test trực tiếp:

```java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.kafka.event.ListenerContainerIdleEvent;

public final class IdleEventCounter {

    private final AtomicInteger idleEvents = new AtomicInteger();

    public void onIdle(ListenerContainerIdleEvent event) {
        if (event.getListenerId().startsWith("ordersIdleListener")) {
            idleEvents.incrementAndGet();
        }
    }

    public int count() {
        return idleEvents.get();
    }
}
```

Một unit test có thể dựng `ListenerContainerIdleEvent` bằng constructor tương ứng Spring Kafka 3.x:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.kafka.event.ListenerContainerIdleEvent;

class IdleEventCounterTest {

    @Test
    void countsOnlyEventsForExpectedListener() {
        IdleEventCounter handler = new IdleEventCounter();

        ListenerContainerIdleEvent target = new ListenerContainerIdleEvent(
                this, this, 2_000L, "ordersIdleListener-0",
                List.of(), null, false);

        ListenerContainerIdleEvent other = new ListenerContainerIdleEvent(
                this, this, 2_000L, "billingListener-0",
                List.of(), null, false);

        handler.onIdle(target);
        handler.onIdle(other);

        assertEquals(1, handler.count());
    }
}
```

Constructor cụ thể của event có thể khác giữa các phiên bản, nên dùng Javadoc khớp với dependency của dự án. Unit test này **không** khởi động consumer, không xác minh `idleEventInterval`, và không chứng minh framework có phát event; nó chỉ kiểm tra logic lọc và đếm.

Khi handler gửi alert qua service, mock service đó và kiểm tra `onIdle` được gọi đúng cho listener mục tiêu, không gọi cho event của listener khác. Có thể giữ handler mỏng và chuyển quyết định business/alert threshold sang service riêng để test nhanh.

## 8. Test consumer idle ngay từ lúc khởi động

Có hệ thống cần phát hiện consumer không hề nhận record nào từ lúc start, ví dụ một topic lẽ ra có dữ liệu mỗi phút. Trong Spring Kafka 3.x, `idleBeforeDataMultiplier` mặc định `5.0` làm thời gian chờ event đầu tiên dài hơn nếu chưa có record.

Để test startup idle một cách chủ động:

```java
factory.getContainerProperties().setIdleEventInterval(1_000L);
factory.getContainerProperties().setIdleBeforeDataMultiplier(1.0);
```

Sau đó giữ topic test không có record mới và chờ event từ đúng listener, với timeout đủ lớn. **Không cần gửi message** trong bài test này. Tuy nhiên cần đảm bảo test group mới không có backlog cũ, container thật sự được khởi động và có partition assignment; nếu topic/group dùng lại với offset cũ, consumer có thể nhận record và phá giả định “idle từ startup”.

Một checklist cho ca startup idle:

1. Dùng topic rỗng và group ID độc lập với test khác.
2. Bật `idleEventInterval` và xác định rõ multiplier trước record đầu.
3. Chờ container ở trạng thái đang chạy/đã được assign nếu muốn diễn giải event ở một assignment thật.
4. Chờ `ListenerContainerIdleEvent` bằng queue/latch/Awaitility, không sleep cứng.
5. Kiểm tra listener ID; nếu yêu cầu partition assignment, kiểm tra `getTopicPartitions()` sau khi assignment hoàn tất.
6. Không coi việc có event đầu tiên là đủ chứng minh broker lành mạnh hoặc không còn lag.

Nếu chỉ muốn kiểm tra business behavior khi thiếu dữ liệu, có thể viết unit test cho policy độc lập với broker thay vì phụ thuộc timing của idle event trong mọi ca kiểm thử.

## 9. Test idle lặp lại và phục hồi

Event idle có thể được phát nhiều lần khi tiếp tục không nhận record. Điều này hữu ích để giám sát, nhưng handler thiếu rate limiting có thể gửi cảnh báo lặp vô hạn.

### 9.1. Kiểm tra event thứ hai khi vẫn idle

Kịch bản integration test:

```text
1. Container đã nhận một record và chuyển sang idle.
2. Thu được idleEvent #1.
3. Không publish thêm record.
4. Thu được idleEvent #2 trong timeout hợp lý.
5. Cùng listener/container; idleTime mới thường không nhỏ hơn thời gian cũ.
```

Nếu đang test event lặp, dùng một `BlockingQueue` chứa các event thay vì một latch chỉ đếm một lần. Đừng áp assertion rằng khoảng cách timestamp giữa hai event luôn đúng 500 ms; độ trễ poll và scheduling có thể thay đổi. Với consumer thực tế có partitions được assign, event còn phụ thuộc trạng thái pause và các record mới đi tới container.

### 9.2. Kiểm tra `NoLongerIdleEvent`

`ListenerContainerNoLongerIdleEvent` chỉ có ý nghĩa **sau khi container đã phát một idle event** và sau đó nhận record mới. Nếu gửi record quá sớm, container chưa từng idle theo định nghĩa framework, nên không kỳ vọng event phục hồi.

Trình tự phù hợp:

```text
    record #1 consumed
            |
            v
   ListenerContainerIdleEvent
            |
            v
       record #2 consumed
            |
            v
 ListenerContainerNoLongerIdleEvent
```

Khi kiểm thử, nên loại bỏ các event cũ khỏi test probe sau khi đã xác nhận idle và trước khi gửi record phục hồi. Nếu nhiều listener cùng dùng một probe, phải lọc theo listener ID thay vì chỉ lấy phần tử đầu queue.

## 10. Test idle ở mức partition khi container vẫn có traffic

Với topic nhiều partitions, một consumer có thể vẫn nhận dữ liệu từ partition 0 trong khi partition 1 không có record. Container-level idle event có thể **không xuất hiện**, vì container vẫn nhận record; nhưng partition-level idle event có thể xuất hiện.

Để bật:

```java
factory.getContainerProperties().setIdlePartitionEventInterval(2_000L);
```

Theo dõi bằng:

```java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerPartitionIdleEvent;

@EventListener
public void onPartitionIdle(ListenerContainerPartitionIdleEvent event) {
    if (event.getListenerId().startsWith("ordersIdleListener")) {
        log.info("kafka.partition.idle listenerId={} partition={} idleMs={}",
                event.getListenerId(),
                event.getTopicPartition(),
                event.getIdleTime());
    }
}
```

Kịch bản test với **2 partitions và một listener container concurrency=1**:

1. Tạo topic test có hai partitions và dùng một consumer group độc lập.
2. Chờ cả hai partitions được assign cho cùng listener nếu bài test yêu cầu như vậy.
3. Gửi messages liên tục tới partition 0 trong khoảng lớn hơn `idlePartitionEventInterval`.
4. Không gửi message tới partition 1.
5. Chờ event có `getTopicPartition().partition() == 1`; không yêu cầu container-wide idle event.
6. Gửi message tới partition 1 rồi xác minh `ListenerContainerPartitionNoLongerIdleEvent` nếu muốn test hồi phục.

Nếu concurrency lớn hơn số partitions, hoặc group có thêm consumer khác, assignment có thể thay đổi. Test cần kiểm tra assignment trước khi khẳng định một partition thuộc consumer đang quan sát. Hạn chế dùng topic test chia sẻ giữa các integration tests chạy song song.

## 11. Event có thể không xuất hiện dù không thấy message

Một test `assertNotNull(idleEvent)` bị timeout chưa đủ kết luận implementation Spring Kafka sai. Những nguyên nhân thường gặp:

| Hiện tượng | Khả năng nguyên nhân | Cách chẩn đoán |
|---|---|---|
| Không có idle event nào | Chưa cấu hình `idleEventInterval`, hoặc factory không được listener sử dụng. | Kiểm tra `containerFactory` trên `@KafkaListener` và giá trị container properties lúc runtime. |
| Không có event trong 1 giây khi topic rỗng từ đầu | `idleBeforeDataMultiplier` mặc định 5.0. | Đặt multiplier 1.0 trong test hoặc tăng timeout/nhận record trước. |
| Event đến trễ | `pollTimeout`, scheduling, broker startup, CI chậm. | Dùng wait có timeout lớn hơn, giảm poll timeout trong test. |
| Container chưa chạy | Listener `autoStartup=false`, cấu hình lỗi hoặc container stopped. | Xác minh registry/container running và startup events. |
| Không có partitions được assign | Topic/group/rebalance chưa sẵn sàng. | Đợi assignment; kiểm tra group/partition và topic creation. |
| Chỉ thấy `NonResponsiveConsumerEvent` | `poll()` bị kẹt, không trả về. | Điều tra poll, connectivity, Kafka client và monitor settings. |
| Không có container idle nhưng một partition rỗng | Partition khác vẫn có message. | Dùng `ListenerContainerPartitionIdleEvent`. |
| Event có nhưng test không bắt được | `@EventListener` bean chưa đăng ký, lọc sai listener ID, khác ApplicationContext. | Kiểm tra Spring bean/import và ID thực tế. |
| Event thuộc listener khác | Event listener nhận sự kiện từ nhiều containers. | Lọc theo `getListenerId()` hoặc source/container. |
| Event handler làm chậm consumer | Handler gọi HTTP/blocking I/O trên consumer thread. | Chuyển công việc nặng sang executor, giữ callback ngắn. |
| Consumer paused | Container/partition chủ động pause; event không nói rõ backlog. | Kiểm tra `isPaused`, pause/resume và consumer lag. |
| Kafka data được gửi nhưng consumer không nhận | Group offset, serializer/deserializer, rebalance hoặc chưa assignment. | Xác minh producer send future, test topic/group, error logs. |

Một yếu tố dễ bị bỏ qua: `getListenerId()` của child container có thể có **hậu tố theo concurrency**, chẳng hạn `ordersIdleListener-0`. So sánh bằng `equals("ordersIdleListener")` trong handler có thể làm mất event. Khi cần chọn toàn bộ nhóm child, dùng `startsWith` với prefix được thiết kế để không đụng ID của listener khác; nếu nhiều ID cùng prefix, lọc theo parent container hoặc quy ước ID rõ ràng.

## 12. `NonResponsiveConsumerEvent` là bài toán khác

`ListenerContainerIdleEvent` chỉ có thể được tạo khi consumer poll loop đủ cơ hội quan sát rằng không có records. Nếu `KafkaConsumer.poll()` không quay về (do network/client hoặc một vấn đề blocking), việc không thấy idle event **không chứng minh consumer vẫn khỏe**.

Spring Kafka còn có `NonResponsiveConsumerEvent` để báo consumer có vẻ đang bị kẹt trong `poll()`. Các thông số liên quan:

```java
factory.getContainerProperties().setPollTimeout(1_000L);
factory.getContainerProperties().setMonitorInterval(5);
factory.getContainerProperties().setNoPollThreshold(3.0f);
```

`monitorInterval` tính bằng giây; `noPollThreshold` cần lớn hơn 1 để tránh false positives do race/timing. Với các phiên bản API khác nhau, kiểu tham số của setter cần đối chiếu Javadoc. Mẫu trên minh họa rằng poll timeout và monitor threshold **khác** idle interval.

Trong production, không nên tự kết luận poll bị kẹt chỉ vì topic không có message. Ngược lại, cũng không được xem `ListenerContainerIdleEvent` là tín hiệu đủ để restart consumer. Cần đánh giá container health, consumer lag, broker connectivity, heartbeat, pause/rebalance và trạng thái upstream.

### 12.1. Có nên viết test bằng cách cố làm `poll()` treo?

Test idle nên dùng topic rỗng, không cần giả lập network failure hoặc cố chặn Kafka client. Nếu muốn test `NonResponsiveConsumerEvent`, đó là một bài test riêng, thường cần kiểm soát Kafka client/poll mock và monitor cadence. Không nên làm hỏng broker embedded ngẫu nhiên rồi chờ idle event, vì lỗi chính cần được phát hiện có thể là **non-responsive** chứ không phải idle.

## 13. Cách viết alerting policy từ idle event

Khi production cần cảnh báo, có thể chuyển event thành metric hoặc một tín hiệu được đánh giá theo cửa sổ thời gian. Ví dụ:

```text
Idle event -> ghi lastIdleAt, listenerId, idleMs
           -> metric/counter giới hạn cardinality
           -> policy:
                - topic có kỳ vọng traffic không?
                - lag và broker health ra sao?
                - có pause/maintenance/rebalance không?
                - idle kéo dài bao lâu qua nhiều chu kỳ?
           -> cảnh báo khi hội đủ điều kiện
```

**Không gửi một alert cho mỗi idle event**. Container có thể phát lặp lại mỗi `idleEventInterval`; với hàng trăm consumers, cơ chế gửi cảnh báo không rate limit sẽ gây alert storm dù topic rỗng là bình thường.

Một chính sách có thể báo sau 5 phút idle liên tục **và** producer đang được kỳ vọng phát records. Khi event `NoLongerIdle` xuất hiện, reset trạng thái/khép cảnh báo. Nếu metrics có high cardinality, tránh dùng message key, event payload hoặc partition ID không cần thiết làm tag; nhóm theo service, listener và topic nếu tập giá trị hữu hạn và phù hợp.

### 13.1. Idle không chứng minh lag bằng 0

Consumer có thể không nhận record vì đang pause, thiếu assignment, lỗi deserializer, hoặc metadata/group chưa ổn định, trong khi broker vẫn có backlog. **Consumer lag** cần tính từ vị trí broker/end offset và offset đã commit/tiến độ consume, tùy công cụ giám sát. `getIdleTime()` không phải phép đo lag và không cho biết lần commit cuối thành công.

### 13.2. Không điều khiển offset tùy tiện trong idle handler

`ListenerContainerIdleEvent.getConsumer()` có thể cung cấp Kafka consumer reference. Mặc định event handler chạy trên consumer thread, nhưng nếu cấu hình Spring application event multicaster chạy bất đồng bộ, handler có thể ở thread khác. **KafkaConsumer không thread-safe**; không được gọi `seek`, `pause`, `resume`, `commit` hoặc các method consumer từ thread không sở hữu nó khi không có cơ chế được framework hỗ trợ.

Nếu cần thực hiện hành động theo vị trí consumer khi idle, Spring Kafka có `ConsumerSeekAware.onIdleContainer(...)` để tương tác với callback/seek strategy phù hợp. Đây là lựa chọn chuyên biệt, không cần dùng cho bài test chỉ quan sát event.

## 14. Test trong CI: Embedded Kafka hay Testcontainers?

| Lựa chọn | Phù hợp khi | Ưu điểm | Điều cần lưu ý |
|---|---|---|---|
| `@EmbeddedKafka` | Integration test nhanh cho listener/event trong cùng JVM test. | Không cần Kafka broker ngoài trong tình huống phổ biến. | Cần quản lý topic/group, broker startup, port, context và test isolation. |
| Kafka Testcontainers | Muốn thử broker/container gần môi trường triển khai thực tế. | Có thể kiểm tra network/container behavior và broker image cụ thể. | Cần Docker/container runtime; startup chậm hơn. |
| `MockConsumer` / mock events | Unit test xử lý event hoặc logic policy. | Nhanh, deterministic, không cần broker. | Không chứng minh listener container phát idle event thật. |
| Kafka staging/test cluster | End-to-end với security, ACL, partition/rebalance thực. | Sát vận hành. | Khó cô lập dữ liệu/tải; không nên dùng cho mỗi unit test. |

Ví dụ Testcontainers có thể dùng `KafkaContainer` hoặc `ConfluentKafkaContainer` tùy phiên bản Testcontainers/Kafka được chọn. Test cần truyền bootstrap servers qua `@DynamicPropertySource` hoặc `@ServiceConnection` (khi Spring Boot hỗ trợ); vẫn dùng cách bắt event và assertion như trên.

Không nên chạy tất cả unit tests phụ thuộc vào broker thật nếu logic chỉ là lọc listener ID, đếm idle events hoặc rate limiting. Những logic đó thuộc unit tests; để lại một số integration tests đủ đại diện để xác nhận wiring và hành vi framework.

### 14.1. Cô lập consumer group và test topic

Các test có thể ảnh hưởng nhau khi dùng cùng topic/group:

- Test trước để lại offset khiến test sau không đọc record như mong đợi.
- Hai test chạy song song trong cùng group chia partitions, mỗi test nhận tập records khác.
- Event cũ trong `BlockingQueue` làm assertion của test sau pass giả.
- Spring Test context caching giữ container và observer bean từ class khác.

Phương án đơn giản là test topic riêng theo class, group ID riêng và reset queues/latches trước mỗi case. Với integration test chạy theo nhiều class trong cùng JVM, `@DirtiesContext` có thể giúp dừng context/containers sau khi test; chỉ dùng khi cần, vì làm tăng thời gian suite. Khi dùng embedded broker chia sẻ toàn test suite, phải quản lý lifecycle và resource isolation rõ ràng.

## 15. Chiến lược kiểm thử không dựa vào sleep

Một bài test sự kiện bất đồng bộ cần **đồng bộ bằng sự kiện** chứ không bằng may rủi timing:

```text
Producer send future -> get(timeout)        [broker nhận được record]
Consumer queue.poll(timeout)                 [listener đã nhận record]
Idle probe queue.poll(timeout)               [Spring phát idle event]
Producer send future -> get(timeout)         [broker nhận record phục hồi]
Consumer queue.poll(timeout)                 [listener nhận record phục hồi]
Resume probe queue.poll(timeout)             [Spring phát no-longer-idle]
```

Hai điểm dễ nhầm:

1. **Producer ACK không đồng nghĩa consumer đã consume.** `KafkaTemplate.send(...).get(...)` chỉ xác nhận producer operation theo Kafka producer ACK policy. Cần assertion riêng ở listener.
2. **Không thấy record không phải điều kiện tạo event duy nhất.** Nếu container chưa chạy, `poll()` không trả về hoặc đã bị stop, test không thể chỉ sleep rồi mong nhận idle event.

Với Awaitility, test có thể đợi điều kiện thay vì `BlockingQueue`; tuy nhiên cần bảo đảm điều kiện đọc state thread-safe. Dùng `AtomicInteger`, `ConcurrentLinkedQueue` hoặc synchronized state; đừng đọc một `ArrayList` bị consumer thread sửa mà không đồng bộ.

### 15.1. Timeout nào phù hợp?

Ngưỡng idle của test có thể là 500 ms, nhưng timeout chờ event nên rộng hơn nhiều, ví dụ 10–20 giây tùy CI. Không rút thời gian đợi xuống 600 ms chỉ để test “nhanh”: scheduling/rebalance có thể gây flaky. Khi test timeout, thông báo lỗi nên ghi rõ đã đợi loại event gì, listener ID nào và trạng thái container nếu có.

### 15.2. Tránh kiểm tra thời gian bằng hiệu `System.currentTimeMillis()` chính xác

Kafka listener sử dụng poll loop/timer logic riêng, còn JUnit thread dùng lịch trình khác. Thay vì `assertEquals(500, idle.getIdleTime())`, dùng điều kiện tương đối (`idleTime >= threshold` với một dung sai phù hợp), và đặt upper bound timeout chờ tổng thể. Nếu cần kiểm tra thuật toán rate limiting riêng, tách thuật toán ra service có `Clock` giả lập để unit test deterministic.

## 16. Ma trận test cần có cho consumer idle event

| Ca kiểm thử | Setup | Kỳ vọng |
|---|---|---|
| Có record rồi rỗng | Gửi record, xác nhận consume, dừng publish | Có `ListenerContainerIdleEvent` đúng ID. |
| Idle rồi hoạt động lại | Sau idle, gửi record mới | Có `ListenerContainerNoLongerIdleEvent`. |
| Topic rỗng từ startup | Không gửi record, multiplier test = 1.0 | Có idle event trong timeout. |
| Chưa bật idle interval | Không đặt `idleEventInterval` | Không **cấu hình** tính năng; tránh test âm tính bằng timing quá ngắn. |
| Hai listener trong một context | Một listener rỗng, một listener nhận message | Handler/test chỉ tính event đúng listener ID. |
| Nhiều partitions | Traffic ở một partition, partition còn lại rỗng | Có partition idle event tương ứng nếu bật interval riêng. |
| Listener paused | Chủ động pause theo API phù hợp | Kiểm tra event paused/không suy diễn healthy từ idle. |
| Poll không phản hồi | Một test riêng điều khiển/mô phỏng poll bị block | Quan sát `NonResponsiveConsumerEvent`, không ép idle event. |
| Idle lặp | Không gửi records trong nhiều interval | Nhận nhiều events, handler không alert storm. |
| Concurrency > 1 | Có nhiều child containers | Listener ID có suffix, test lọc đúng group/child. |
| Consumer được stop | Dừng container theo cách được hỗ trợ | Không kỳ vọng idle event tiếp tục như khi running. |

Không nhất thiết mỗi ca phải là một integration test nặng. Có thể giữ vài ca tích hợp để chứng minh event lifecycle, còn filtering, alert rate limit, counter và policy là unit tests.

## 17. Những lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Test chờ 1 giây nhưng không có idle event | Multipler trước data mặc định 5; poll startup chưa hoàn tất. | Đặt `setIdleBeforeDataMultiplier(1.0)` trong test, hoặc nhận record trước khi chờ. |
| `@EventListener` không được gọi | Handler không nằm trong Spring context. | Đăng ký bằng `@Component`, `@Bean` hoặc `@Import`; kiểm tra đúng context. |
| Event bị lọc hết | Listener ID có suffix `-0`, `-1`. | Dùng `startsWith` có scope, hoặc kiểm tra source/container. |
| Event xuất hiện từ consumer khác | Một application context có nhiều listeners. | Lọc theo listener ID; tách test fixtures. |
| Test pass dù listener không nhận message | Chỉ assert idle event, không test consumer callback. | Gửi record đầu và chờ queue/latch xác nhận listener hoạt động. |
| `NoLongerIdleEvent` không xuất hiện | Chưa từng có idle event trước khi gửi record. | Đợi idle event thật rồi mới gửi dữ liệu phục hồi. |
| Không có idle event nhưng client bị kẹt | `poll()` không trả về để phát hiện idle. | Giám sát `NonResponsiveConsumerEvent`, poll/network/client. |
| Container đã dừng | `autoStartup=false` hoặc stop được gọi trước test. | Kiểm tra registry, running state và startup lỗi. |
| Topic rỗng nhưng consumer group có backlog | Assignment sai/paused/deserialization failure/lag. | Đối chiếu lag, assignment, pause, logs và broker metrics. |
| Test bị flaky trên CI | Timeout quá sát idle interval, nhiều test tranh topic/group. | Dùng queue poll timeout rộng, cô lập topic/group, tránh sleep cứng. |
| Event handler làm chậm consume | Gọi network API trong consumer thread. | Chuyển sang executor/queue, chỉ truyền metadata an toàn. |
| Alert bị spam | Event idle lặp mỗi interval. | Rate limit và trạng thái alert, khép khi NoLongerIdle. |
| Partition idle bị xem nhầm là container idle | Partition khác vẫn có traffic. | Dùng listener partition-level và kiểm tra đúng phạm vi. |
| Consumer API báo lỗi thread safety | Gọi `getConsumer()` từ event listener bất đồng bộ. | Không thao tác Consumer ngoài owning thread; dùng callback/registry API phù hợp. |

## 18. Quy trình áp dụng vào dự án

1. **Xác định kỳ vọng nghiệp vụ:** topic nhận dữ liệu liên tục hay theo lịch? Khoảng thiếu dữ liệu bao lâu là bình thường?
2. **Chọn phạm vi giám sát:** idle toàn container hay từng partition? Có cần theo dõi consumer lag riêng không?
3. **Bật interval phù hợp:** `idleEventInterval` và, nếu cần, `idlePartitionEventInterval`; hiểu multiplier trước record đầu.
4. **Đặt ID listener rõ ràng:** thuận tiện lọc event, logs và metrics.
5. **Viết handler nhẹ:** không block consumer thread; ghi metadata tối thiểu và giao việc alerting cho service riêng.
6. **Xây dựng integration test:** tạo broker/topic/group test, consume một record, đợi idle event, gửi record tiếp và xác nhận recovery event.
7. **Dùng timeout hữu hạn:** không dựa vào `Thread.sleep` cố định; cô lập probe giữa các tests.
8. **Thêm unit tests:** logic lọc listener ID, dedupe/rate limiting và business policy.
9. **Thử thêm failure modes:** pause, rebalance, partition rỗng, non-responsive poll và container stopped.
10. **Đối chiếu production telemetry:** lag, consumer health, throughput producer và maintenance windows trước khi tạo alert nghiêm trọng.

### Bài tập 1 — Test consumer trở nên idle

Tạo listener `paymentsConsumer` đọc topic `payments-test`, bật `idleEventInterval=1s`. Dùng `@EmbeddedKafka` gửi một record, xác minh listener đã nhận, sau đó chờ `ListenerContainerIdleEvent` trong 15 giây. Kiểm tra `getListenerId()` và `getIdleTime()` mà không dùng `Thread.sleep(1000)`.

### Bài tập 2 — Test idle → active

Sau khi nhận idle event, gửi một record mới và chờ `ListenerContainerNoLongerIdleEvent`. Giải thích tại sao gửi record trước idle event không đảm bảo sự kiện no-longer-idle xuất hiện.

### Bài tập 3 — Kiểm tra multiplier trước record đầu

Để topic trống từ startup. So sánh test cấu hình `idleEventInterval=1000L, idleBeforeDataMultiplier=5.0` với `idleBeforeDataMultiplier=1.0`. Không assert mốc thời gian chính xác, chỉ quan sát sự khác nhau về thời gian kỳ vọng và cấu hình timeout.

### Bài tập 4 — Nhiều listeners và partitions

Tạo hai listeners với IDs khác nhau, một topic có hai partitions. Gửi dữ liệu vào một partition và giữ partition còn lại rỗng. Viết probe không nhầm idle event của listener khác và tìm đúng `ListenerContainerPartitionIdleEvent` theo partition ID. Kiểm tra behavior khi concurrency thay đổi.

### Bài tập 5 — Alert không bị spam

Một consumer idle 10 phút có thể phát hàng chục events. Viết `IdleAlertPolicy` giữ trạng thái và chỉ gửi một alert ban đầu, có escalation theo ngưỡng nếu cần, rồi clear khi `ListenerContainerNoLongerIdleEvent` được phát. Unit test chính sách bằng clock điều khiển được, không cần Kafka broker.

### Bài tập 6 — Phân biệt idle và consumer hỏng

Thiết kế bảng tín hiệu gồm idle event, lag, partition assignment, paused state, nonresponsive event, upstream producer rate và broker connectivity. Đưa ra quyết định cho ba trường hợp: topic rỗng hợp lệ, topic có backlog nhưng consumer paused, và consumer poll không phản hồi.

## 19. Nguyên tắc ghi nhớ

- `ListenerContainerIdleEvent` báo **không nhận record trong một khoảng thời gian**, không tự chứng minh consumer hoặc broker đang lỗi.
- `idleEventInterval` phải được bật; mặc định `null` thường không phát event. `idleBeforeDataMultiplier` mặc định **5.0** trước khi có record đầu tiên trong Spring Kafka 3.x.
- Event có thể **phát lặp lại** khi vẫn idle; dùng rate limiting trong observability/alerting.
- `ListenerContainerNoLongerIdleEvent` cho biết consumer nhận record sau trạng thái idle đã được framework ghi nhận.
- Test tốt nhất sử dụng **Kafka broker test + `@EventListener` + queue/latch/Awaitility**, với timeout rộng và không `sleep` cứng.
- Luôn xác minh listener thực sự đã consume, không chỉ producer send thành công.
- Với concurrency, listener ID có thể mang hậu tố child; event handler cần lọc đúng phạm vi.
- `ListenerContainerPartitionIdleEvent` và `NonResponsiveConsumerEvent` giải quyết **những câu hỏi khác**; đừng suy luận lag, health hoặc poll responsiveness từ một idle event.
- Event handler mặc định có thể chạy trên consumer thread; **không block** và không thao tác Kafka `Consumer` từ thread không sở hữu nó.
- Trong production, kết hợp idle, lag, assignment, producer rate và business expectations trước khi alert hoặc restart container.

## 20. Tài liệu tham khảo chính thức

- [Spring for Apache Kafka Reference — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html): `ListenerContainerIdleEvent`, `ListenerContainerNoLongerIdleEvent`, partition idle events, nonresponsive consumer và cách xử lý event.
- [Spring for Apache Kafka Reference — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html): `idleEventInterval`, `idleBeforeDataMultiplier`, `idlePartitionEventInterval`, `pollTimeout` và monitor settings.
- [Spring Kafka 3.3 API — `ListenerContainerIdleEvent`](https://docs.spring.io/spring-kafka/docs/3.3.11/api/org/springframework/kafka/event/ListenerContainerIdleEvent.html): constructor và getter của idle event.
- [Spring Kafka 3.3 API — `ListenerContainerNoLongerIdleEvent`](https://docs.spring.io/spring-kafka/docs/3.3.11/api/org/springframework/kafka/event/ListenerContainerNoLongerIdleEvent.html): event được phát khi listener có dữ liệu trở lại.
- [Spring Boot Reference — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): cấu hình Kafka trong Boot và kiểm thử với `@EmbeddedKafka`.
- [Spring Boot 3.5 — Common Kafka Listener Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.kafka.listener.idle-event-interval` và các Kafka properties khác.
- [Spring Kafka Reference — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): embedded brokers, `@EmbeddedKafka`, Kafka test utilities và cách tổ chức tests.

