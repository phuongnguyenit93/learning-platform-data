# Test non-responsive consumer trong Spring Kafka Reliability Operations

Khi một ứng dụng Spring Kafka đang tiêu thụ message, consumer cần liên tục quay lại vòng `poll()` để nhận bản ghi mới và duy trì khả năng phối hợp với consumer group. Trong điều kiện lỗi, khoảng cách giữa các lần `poll()` có thể kéo dài bất thường: listener xử lý quá lâu, thread bị block, remote API không trả kết quả, hệ thống quá tải hoặc một sự cố liên quan tới Kafka client/network làm quá trình polling không tiến triển.

Nếu chỉ kiểm tra “ứng dụng còn chạy” hoặc “Kafka broker vẫn hoạt động”, hệ thống có thể bỏ sót một consumer **không còn tiến triển**. Spring Kafka cung cấp sự kiện `NonResponsiveConsumerEvent` để hỗ trợ phát hiện tình trạng không có hoạt động poll trong một khoảng thời gian vượt ngưỡng được cấu hình.

Bài thực hành **Test non-responsive consumer** thuộc nhóm **Kiểm thử tin cậy** của **Spring Kafka Reliability Operations**. Mục tiêu là xây dựng phép thử có thể tái lập, chứng minh consumer monitor phát hiện được việc polling bị gián đoạn, biết cách phân biệt với consumer nhàn rỗi và hiểu các giới hạn của cơ chế phát hiện.

> **Điểm quan trọng:** `NonResponsiveConsumerEvent` chỉ báo rằng khoảng thời gian không có hoạt động poll vượt ngưỡng giám sát. Nó **không tự chẩn đoán nguyên nhân** là Kafka broker bị lỗi, network bị treo hay listener xử lý lâu. Muốn kết luận nguyên nhân, phải kết hợp thread dump, metrics, log và kiểm thử lỗi theo từng tầng.

Các ví dụ chủ yếu dành cho Java 17, Spring Boot 3.x và dòng Spring Kafka 3.x. Khi dùng Spring Kafka 4.x hoặc phiên bản khác, hãy đối chiếu package, API và cấu hình thực tế của dependency trong dự án. Các ngưỡng thời gian của test được đặt nhỏ có chủ đích, không phải cấu hình production được khuyến nghị.

## 1. Non-responsive consumer là gì?

Một Kafka consumer bình thường liên tục lặp:

```text
Consumer container thread
        |
        v
    consumer.poll(...)
        |
        +-- Có record --> gọi message listener
        |                    |
        |                    v
        |                 xử lý xong
        |                    |
        +<-------------------+
        |
        v
    consumer.poll(...) lần tiếp theo
```

Khi listener block trong nhiều giây, phút hoặc lâu hơn, thread có thể chưa gọi `poll()` tiếp theo. Spring Kafka monitor quan sát khoảng thời gian liên quan tới hoạt động polling và phát event nếu vượt ngưỡng.

Ví dụ:

```text
Thời gian      00:00     00:01     00:02     00:03     00:04
               |---------|---------|---------|---------|
poll()         ^
record handler [----------------------------- blocked ...
monitor                  ^             ^
                      check          check
                                      |
                                      v
                        NonResponsiveConsumerEvent
```

Event là một tín hiệu giám sát **trong ứng dụng**, khác với việc Kafka tự loại consumer khỏi group do vượt `max.poll.interval.ms`. Hai cơ chế hoạt động ở những tầng khác nhau và có thể xuất hiện ở các thời điểm khác nhau.

### Những nguyên nhân thường gặp

- Listener gọi HTTP/gRPC và bị chờ vô hạn hoặc timeout quá dài.
- Listener chờ database lock, connection pool hoặc transaction kéo dài.
- Deadlock, lock contention hoặc `CountDownLatch.await()` không bao giờ được mở.
- CPU starvation, GC pause lớn hoặc executor quá tải.
- Kafka client gặp sự cố liên quan tới `poll()` hoặc network/broker.
- Một record cần xử lý quá lâu, khiến consumer không quay lại `poll()`.
- Cấu hình xử lý batch quá lớn so với thời gian được phép giữa các lần poll.

Event báo “không poll đúng nhịp mong đợi”, chứ không nói “consumer chắc chắn đã chết”.

## 2. Phân biệt non-responsive, idle và lag

Ba tình trạng sau rất dễ bị nhầm:

| Tình trạng | Biểu hiện | Ý nghĩa |
| --- | --- | --- |
| **Idle consumer** | `poll()` vẫn diễn ra, nhưng không có record mới. | Consumer có thể hoàn toàn khỏe mạnh; topic đang không có dữ liệu. |
| **Non-responsive consumer** | Không thấy hoạt động poll trong khoảng thời gian dài hơn ngưỡng. | Có thể thread đang block, xử lý quá lâu hoặc polling gặp vấn đề. |
| **Consumer lag cao** | Consumer group còn nhiều record chưa xử lý so với log end offset. | Tiến độ tiêu thụ không theo kịp producer; consumer vẫn có thể đang poll. |

Trong Spring Kafka, sự kiện `ListenerContainerIdleEvent` và `NonResponsiveConsumerEvent` có ý nghĩa **khác nhau**.

```text
Không có message, consumer vẫn poll:
  poll(empty) -> poll(empty) -> poll(empty)
  => Có thể là IDLE, không nhất thiết NON-RESPONSIVE.

Listener nhận một message rồi block:
  poll(records) -> listener bị chặn -> không trở lại poll
  => Có thể phát NonResponsiveConsumerEvent.

Producer gửi rất nhanh, consumer vẫn poll đều:
  poll -> xử lý -> poll -> xử lý
  lag tăng vì throughput thấp
  => Có lag cao, nhưng chưa chắc có NonResponsiveConsumerEvent.
```

Vì vậy, không sử dụng `NonResponsiveConsumerEvent` làm chỉ số duy nhất cho sức khỏe consumer. Nó là một tín hiệu trong hệ thống giám sát tiến độ.

## 3. Cơ chế `NonResponsiveConsumerEvent`

Spring Kafka listener container có một monitor định kỳ. Với cấu hình phù hợp, monitor kiểm tra khoảng thời gian kể từ lần poll gần nhất; khi khoảng thời gian vượt ngưỡng, container có thể phát `NonResponsiveConsumerEvent`.

Các thuộc tính quan trọng trên `ContainerProperties`:

| Thuộc tính | Mục đích |
| --- | --- |
| `pollTimeout` | Timeout cho một lời gọi `KafkaConsumer.poll(Duration)` của container, tính bằng millisecond. |
| `noPollThreshold` | Hệ số nhân với `pollTimeout` để xác định ngưỡng không có poll trước khi phát cảnh báo. |
| `monitorInterval` | Chu kỳ kiểm tra của monitor, thường được cấu hình bằng số giây trên `ContainerProperties`. |

Ngưỡng khái niệm:

\[
T_{\mathrm{nonresponsive}} \approx
\mathrm{noPollThreshold}\times\mathrm{pollTimeout}
\]

Ví dụ:

```text
pollTimeout      = 1.000 ms
noPollThreshold  = 3.0
monitorInterval  = 1 giây

Ngưỡng cơ sở     = 3.000 ms
Monitor kiểm tra mỗi 1 giây
=> Event có thể xuất hiện sau khi vượt ngưỡng,
   không nhất thiết đúng tại mốc 3.000 ms.
```

Các thuộc tính, giá trị mặc định và API có thể phụ thuộc phiên bản Spring Kafka. Trong nhiều bản Spring Kafka, `noPollThreshold` mặc định là `3.0` và `monitorInterval` mặc định vào khoảng 30 giây. Không nên dùng những mặc định đó làm cơ sở cho một test chỉ chờ vài giây; test cần **cấu hình tường minh**.

`noPollThreshold` nên lớn hơn `1.0` để giảm nguy cơ cảnh báo sai do chênh lệch thời điểm thread poll và monitor kiểm tra.

### Khi monitor kiểm tra thì event được phát khi nào?

Giả sử ngưỡng 1,5 giây, monitor mỗi 1 giây:

```text
t = 0.0s: poll cuối
t = 1.0s: monitor check, chưa vượt 1.5s
t = 2.0s: monitor check, đã vượt ngưỡng
           -> NonResponsiveConsumerEvent
```

Không viết test kiểm tra event **phải xuất hiện chính xác ở 1,5 giây**. Thời điểm thực tế bị ảnh hưởng bởi lịch chạy thread, khởi động Spring context và độ trễ scheduler. Test tin cậy nên chờ theo điều kiện với timeout đủ rộng.

## 4. Mối quan hệ với các tham số Kafka consumer

`NonResponsiveConsumerEvent` là chức năng Spring Kafka; Kafka client có những timeout riêng.

| Tham số/cơ chế | Điều khiển | Dễ nhầm lẫn |
| --- | --- | --- |
| `pollTimeout` của Spring container | Thời gian chờ mỗi lời gọi poll ở container. | Không phải tổng thời gian listener được phép xử lý một record. |
| `noPollThreshold` | Ngưỡng Spring Kafka monitor xác định khoảng không poll đáng ngờ. | Không phải timeout của group membership. |
| `monitorInterval` | Tần suất monitor kiểm tra consumer. | Không phải thời gian consumer gửi heartbeat. |
| `max.poll.interval.ms` | Khoảng tối đa giữa các lời gọi poll theo cơ chế Kafka consumer group. | Có thể gây rebalance khi xử lý quá lâu, nhưng không phải event của Spring monitor. |
| `session.timeout.ms` | Thời hạn phát hiện consumer mất session với group coordinator theo cơ chế group protocol tương ứng. | Không phản ánh trực tiếp tốc độ callback xử lý record. |
| `heartbeat.interval.ms` | Chu kỳ heartbeat trong những chế độ group protocol dùng cấu hình này. | Có heartbeat không bảo đảm listener đã xử lý xong record. |
| `max.poll.records` | Số record tối đa được trả về mỗi lần poll. | Batch quá lớn có thể kéo dài vòng xử lý và tăng rủi ro vượt poll interval. |

Ví dụ listener xử lý một batch 500 bản ghi, mỗi bản ghi cần 2 giây:

```text
500 record × 2 giây ≈ 1.000 giây xử lý tuần tự
```

Dù `consumer.poll()` trả kết quả bình thường, listener có thể cần rất lâu mới gọi poll tiếp. Điều này có thể phát `NonResponsiveConsumerEvent` và còn có thể vi phạm `max.poll.interval.ms`.

**Tăng `max.poll.interval.ms` không giải quyết listener bị treo vô hạn.** Tương tự, giảm `noPollThreshold` không làm consumer tự hoạt động trở lại; nó chỉ thay đổi độ nhạy của cảnh báo.

### Phân biệt pause và stop

Một consumer được **pause** theo cách Spring Kafka hỗ trợ có thể vẫn thực hiện polling để duy trì group membership, tùy trạng thái và cách container vận hành. Vì vậy trạng thái pause hợp lệ không nhất thiết tạo event non-responsive.

`stop()` container là thao tác vòng đời; sau khi container dừng hoàn toàn không còn yêu cầu nó phải poll. Khi kiểm tra sự kiện, cần xác nhận container đang ở trạng thái được kỳ vọng là running.

## 5. Mục tiêu của một test non-responsive consumer

Một bài test đầy đủ tối thiểu nên chứng minh:

1. Container được khởi tạo, đăng ký listener và tham gia Kafka consumer group.
2. Listener nhận được một message test.
3. Listener bị giữ ở trạng thái không hoàn tất để container không quay lại poll.
4. Monitor phát một hoặc nhiều `NonResponsiveConsumerEvent` trong giới hạn thời gian xác định.
5. Event được ghi nhận bởi listener quan sát và có đúng container/listener ID.
6. Khi gỡ chặn, callback có thể hoàn tất và container tiếp tục hoạt động theo hợp đồng.
7. Test luôn giải phóng latch/worker trong `finally` để không làm treo suite.

Ngoài test tích cực, cần có **test âm**: khi consumer xử lý nhanh và poll bình thường, không được báo non-responsive vì một cách tính timeout sai hoặc do setup không ổn định.

Không phải mọi kiểm thử đều phải mô phỏng broker chết. Một test dùng latch là cách hiệu quả để kiểm tra **cơ chế phát hiện thời gian không poll**. Một test fault injection riêng mới chứng minh ứng dụng ứng xử ra sao với mạng/broker lỗi thật.

## 6. Các lớp kiểm thử: unit, integration và fault injection

| Lớp kiểm thử | Mục đích | Kỹ thuật |
| --- | --- | --- |
| **Unit test của event handler** | Đảm bảo event được phân loại, log và đưa vào metric/alert đúng cách. | Tạo event/probe giả hoặc gọi logic xử lý với dữ liệu đã ánh xạ. |
| **Integration test với Embedded Kafka** | Chứng minh container monitor phát event khi listener không quay lại poll. | `@EmbeddedKafka`, `CountDownLatch`, `@EventListener`, timeout. |
| **Integration test lifecycle recovery** | Thử chính sách cảnh báo, giải phóng listener, tiếp tục nhận message, không tạo loop restart. | Embedded Kafka/Testcontainers, await trạng thái và record. |
| **Network fault injection** | Thử lỗi broker/network ảnh hưởng tới polling, coordinator hoặc metadata. | Proxy có kiểm soát, Testcontainers/Toxiproxy, môi trường Kafka test riêng. |
| **Soak/performance test** | Kiểm tra phát hiện và khôi phục ổn định dưới tải lớn, GC, DB/HTTP latency. | Thời gian dài, nhiều partition, metrics, chaos scenario. |

Test bằng latch nên là **bài test nền tảng**, vì dễ tái lập và không phụ thuộc một lỗi mạng vốn có thể tạo ra hành vi khác giữa các phiên bản Kafka client.

## 7. Dependency và cấu hình cho integration test

Ví dụ Gradle dùng Spring Boot quản lý phiên bản phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

`spring-kafka-test` hỗ trợ `@EmbeddedKafka` và các utility để chờ consumer partition assignment.

Khi dùng Spring Boot test, nên cấu hình serializer và deserializer dạng String để fixture đơn giản:

```properties
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.consumer.auto-offset-reset=earliest
```

Những property này là ví dụ cho **test profile**. Trong production, serializer/deserializer phải phù hợp message contract và có chính sách xử lý lỗi deserialize riêng.

Không dùng topic production hoặc consumer group production cho test. Consumer group test nên được cô lập để không ảnh hưởng các ứng dụng đang chạy.

## 8. Cấu hình monitor với ngưỡng nhỏ trong test

Trong ví dụ, ta chọn:

```text
pollTimeout      = 500 ms
noPollThreshold  = 3.0
monitorInterval  = 1 giây
ngưỡng cơ sở     = 1,5 giây
```

Cấu hình bean `ConcurrentKafkaListenerContainerFactory`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class NonResponsiveTestKafkaConfig {

    @Bean("nonResponsiveTestFactory")
    ConcurrentKafkaListenerContainerFactory<String, String>
    nonResponsiveTestFactory(
            ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory
                        <String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(1);

        factory.getContainerProperties().setPollTimeout(500L);
        factory.getContainerProperties().setNoPollThreshold(3.0f);
        factory.getContainerProperties().setMonitorInterval(1);

        return factory;
    }
}
```

Ở đây:

- `setPollTimeout(500L)` giúp threshold dự kiến nhỏ.
- `setNoPollThreshold(3.0f)` cho biết event được kỳ vọng sau một khoảng không poll dài hơn `3 × 500ms`.
- `setMonitorInterval(1)` khiến monitor kiểm tra thường xuyên đủ cho integration test.
- `setConcurrency(1)` giúp kiểm soát chỉ một consumer thread cho một partition.

**Không sao chép ngưỡng cực thấp này sang production** nếu listener xử lý record bình thường lâu hơn vài giây. Ngưỡng quá nhạy gây nhiều cảnh báo không có giá trị, thậm chí kích hoạt một chính sách tự phục hồi nguy hiểm nếu ứng dụng tự động restart.

Trong ứng dụng có nhiều listener factories, hãy xác nhận `@KafkaListener` test sử dụng đúng `containerFactory`. Chỉnh một factory không có tác dụng với listener đang chạy trên factory khác.

## 9. Tạo listener test cố ý không phản hồi

Dùng `CountDownLatch` thay vì `Thread.sleep(10000)` để test chủ động quyết định khi nào callback được phép kết thúc.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.kafka.annotation.KafkaListener;

public final class BlockingOrderListener {

    final CountDownLatch entered = new CountDownLatch(1);
    final CountDownLatch release = new CountDownLatch(1);
    final CountDownLatch completed = new CountDownLatch(1);
    final AtomicInteger deliveryCount = new AtomicInteger();

    @KafkaListener(
            id = "blocked-order-consumer",
            topics = "nonresponsive-consumer-it",
            containerFactory = "nonResponsiveTestFactory")
    public void onOrder(String message) throws InterruptedException {

        deliveryCount.incrementAndGet();
        entered.countDown();

        try {
            // Test chủ động giữ listener đang xử lý record.
            // Có timeout để CI không bị treo vô hạn.
            if (!release.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Test fixture timed out");
            }
        } finally {
            completed.countDown();
        }
    }
}
```

Khi listener đã chạy vào `onOrder(...)`, consumer thread sẽ không quay lại vòng poll cho đến khi method kết thúc.

Ưu điểm của fixture:

- Có `entered` để xác nhận message đã được nhận; không suy đoán bằng cách ngủ một khoảng tùy ý.
- Có `release` để gỡ chặn một cách xác định.
- Có `completed` để test chờ callback thoát.
- Có timeout phòng trường hợp test fail sớm hoặc teardown bất thường.
- Có `deliveryCount` để hỗ trợ kiểm tra nhận message.

**Đây là mô phỏng listener bị block**, không phải mô phỏng `KafkaConsumer.poll()` bị treo trong Kafka client. Sự khác biệt này phải được ghi rõ trong kết luận của bài test.

## 10. Thu thập `NonResponsiveConsumerEvent`

Spring Kafka có thể công bố những sự kiện container qua cơ chế application events của Spring. Tạo một probe để lưu event vào một hàng đợi thread-safe:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;

public final class NonResponsiveEventProbe {

    final BlockingQueue<NonResponsiveConsumerEvent> events =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onEvent(NonResponsiveConsumerEvent event) {
        String listenerId = event.getListenerId();

        if (listenerId != null
                && listenerId.startsWith("blocked-order-consumer")) {
            events.offer(event);
        }
    }
}
```

Với concurrent listener container, ID trong event có thể mang hậu tố xác định child consumer, tùy cấu trúc container. Vì vậy test không nên mặc định so sánh chuỗi ID một cách quá cứng nhắc nếu cấu hình concurrency thay đổi.

`LinkedBlockingQueue` phù hợp để chuyển event từ monitor thread sang test thread. Trong một app giám sát thật, không nên giữ mọi event vô hạn trong memory; chọn queue có giới hạn, tổng hợp metric theo container và có chính sách chống lặp cảnh báo.

### Ý nghĩa của event

`NonResponsiveConsumerEvent` cung cấp thông tin như listener/container identity và khoảng thời gian từ poll liên quan tới cảnh báo. Ví dụ:

```java
long elapsedMs = event.getTimeSinceLastPoll();
String listenerId = event.getListenerId();
```

Các giá trị này giúp log/metric được gắn đúng container.

Không mặc nhiên gọi các method của `KafkaConsumer` từ monitor/event thread. `KafkaConsumer` không phải một API thread-safe tổng quát; ngoại lệ liên quan tới `wakeup()` có điều kiện sử dụng riêng và phải được xử lý cẩn thận. Một event handler chỉ ghi nhận cảnh báo thường an toàn hơn một handler tự ý seek, commit hoặc poll từ thread khác.

## 11. Integration test với `@EmbeddedKafka`

Ta kết hợp:

1. Embedded Kafka broker có một topic và một partition.
2. Spring Boot application context có `KafkaTemplate`.
3. `BlockingOrderListener` đăng ký qua `@KafkaListener`.
4. `NonResponsiveEventProbe` nhận event.
5. Một test gửi message, chờ callback vào trạng thái block, rồi đợi event.

Ví dụ một lớp integration test hoàn chỉnh về cấu trúc:

```java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "spring.kafka.consumer.auto-offset-reset=earliest",
    "spring.kafka.consumer.key-deserializer="
        + "org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.consumer.value-deserializer="
        + "org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.producer.key-serializer="
        + "org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.producer.value-serializer="
        + "org.apache.kafka.common.serialization.StringSerializer"
})
@EmbeddedKafka(
        partitions = 1,
        topics = "nonresponsive-consumer-it",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
@Import(NonResponsiveConsumerIT.FixtureConfiguration.class)
class NonResponsiveConsumerIT {

    @Autowired
    KafkaTemplate<String, String> template;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Autowired
    BlockingOrderListener blockingListener;

    @Autowired
    NonResponsiveEventProbe eventProbe;

    @Test
    void emitsEventWhenListenerDoesNotReturnToPoll()
            throws Exception {

        try {
            var container =
                    registry.getListenerContainer("blocked-order-consumer");

            assertThat(container).isNotNull();

            // Chờ consumer thực sự được gán partition.
            ContainerTestUtils.waitForAssignment(container, 1);

            template.send(
                    "nonresponsive-consumer-it",
                    "order-1",
                    "payload").get(10, TimeUnit.SECONDS);

            assertThat(
                    blockingListener.entered.await(
                            10, TimeUnit.SECONDS))
                    .as("Listener should receive the test message")
                    .isTrue();

            NonResponsiveConsumerEvent event =
                    eventProbe.events.poll(8, TimeUnit.SECONDS);

            assertThat(event)
                    .as("Monitor should detect lack of polling")
                    .isNotNull();

            assertThat(event.getListenerId())
                    .startsWith("blocked-order-consumer");

            assertThat(event.getTimeSinceLastPoll())
                    .isGreaterThan(0L);

        } finally {
            // Luôn giải phóng thread consumer,
            // kể cả khi assertion ở trên thất bại.
            blockingListener.release.countDown();
        }

        assertThat(
                blockingListener.completed.await(
                        5, TimeUnit.SECONDS))
                .as("Listener should be released after the test")
                .isTrue();
    }

    @TestConfiguration(proxyBeanMethods = false)
    @EnableKafka
    static class FixtureConfiguration {

        @Bean("nonResponsiveTestFactory")
        ConcurrentKafkaListenerContainerFactory<String, String>
        nonResponsiveTestFactory(
                ConsumerFactory<String, String> consumerFactory) {

            var factory =
                    new ConcurrentKafkaListenerContainerFactory
                            <String, String>();

            factory.setConsumerFactory(consumerFactory);
            factory.setConcurrency(1);
            factory.getContainerProperties().setPollTimeout(500L);
            factory.getContainerProperties().setNoPollThreshold(3.0f);
            factory.getContainerProperties().setMonitorInterval(1);

            return factory;
        }

        @Bean
        BlockingOrderListener blockingListener() {
            return new BlockingOrderListener();
        }

        @Bean
        NonResponsiveEventProbe eventProbe() {
            return new NonResponsiveEventProbe();
        }
    }
}
```

### Các giả định của ví dụ

- Ứng dụng có `@SpringBootApplication` hoặc một cấu hình Spring Boot phù hợp để `@SpringBootTest` tìm được context.
- `BlockingOrderListener` và `NonResponsiveEventProbe` là hai lớp ở mục trước, đã được thêm vào test source.
- Test dùng `spring-kafka-test` tương thích với phiên bản Spring Kafka của ứng dụng.
- KafkaTemplate và ConsumerFactory được Spring Boot cấu hình với String serializer/deserializer như property minh họa.
- Chỉ có một instance `blocked-order-consumer` trong test context; topic và group không bị các test khác dùng chung gây nhiễu.
- `@EmbeddedKafka` tạo broker riêng cho test và kết nối qua property `spring.kafka.bootstrap-servers`.
- Consumer đang chạy thật, không chỉ có một object listener được gọi trực tiếp bằng unit test.

Một vài phiên bản hỗ trợ các overload utility và cấu hình Embedded Kafka khác nhau. Điểm kiểm thử bất biến là **chờ partition assignment, gửi record, chờ listener block, rồi nhận event**, không cần cố ép chính xác mọi dòng import theo phiên bản mới nhất.

### Vì sao cần chờ partition assignment?

Nếu gửi ngay khi test context khởi động, consumer có thể chưa nhận partition. Với `auto.offset.reset=latest`, một consumer mới đôi khi bỏ qua record đã được gửi trước khi có vị trí bắt đầu. Dùng `earliest` trong test và chờ assignment giúp giảm race condition; việc chờ assignment còn xác nhận container đã tham gia Kafka group trước khi kiểm thử.

### Vì sao không chỉ dùng `Thread.sleep(3000)`?

Một test kiểu:

```java
Thread.sleep(3000);
assertThat(events).isNotEmpty();
```

không chứng minh listener đã nhận message và bị block. Trong CI chậm, ba giây có thể trôi qua trước khi consumer tham gia group. Test có latch và queue nhận event chắc chắn hơn vì dựa trên **điều kiện**, không dựa trên một con số thời gian ước lượng.

### Vì sao test có thể nhận nhiều event?

Monitor có thể tiếp tục phát `NonResponsiveConsumerEvent` theo những lần kiểm tra định kỳ nếu consumer vẫn chưa quay lại poll. Test chỉ cần xác nhận **ít nhất một event phù hợp**. Trong ứng dụng thật, nếu cảnh báo lặp, nên có cooldown hoặc coalescing theo listener/container ID.

## 12. Test consumer phục hồi sau khi được gỡ chặn

Phát hiện event là một nửa câu chuyện. Kiểm thử tin cậy cần chứng minh khi điều kiện block biến mất, consumer có thể quay lại xử lý.

Mở rộng fixture để đánh dấu lần xử lý tiếp theo:

```java
final CountDownLatch secondDelivered = new CountDownLatch(1);

@KafkaListener(
        id = "blocked-order-consumer",
        topics = "nonresponsive-consumer-it",
        containerFactory = "nonResponsiveTestFactory")
public void onOrder(String message) throws InterruptedException {
    int count = deliveryCount.incrementAndGet();

    if (count == 1) {
        entered.countDown();
        if (!release.await(15, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Fixture timed out");
        }
        completed.countDown();
    } else {
        secondDelivered.countDown();
    }
}
```

Sau khi test nhận event:

```java
blockingListener.release.countDown();

assertThat(
        blockingListener.completed.await(
                5, TimeUnit.SECONDS))
        .isTrue();

template.send(
        "nonresponsive-consumer-it",
        "order-2",
        "second-payload").get(10, TimeUnit.SECONDS);

assertThat(
        blockingListener.secondDelivered.await(
                10, TimeUnit.SECONDS))
        .as("Consumer should process another record after release")
        .isTrue();
```

Đây là **phần mở rộng thay thế method listener** trong fixture, không chạy đồng thời hai method `@KafkaListener` có cùng ID trong cùng test context.

Cần chú ý: nếu callback đầu tiên block **quá lâu**, consumer có thể vượt `max.poll.interval.ms` và bị rebalance. Khi đó test có thể vẫn hồi phục sau assignment lại, nhưng độ trễ và thứ tự record khác với một bài test monitor ngắn. Để kiểm tra riêng sự kiện monitor, giữ khoảng block ngắn hơn giới hạn poll interval phù hợp và không cố ý trộn vào kịch bản rebalance.

### Không dựa vào “event biến mất ngay” làm tín hiệu hồi phục duy nhất

Event là một thông báo thời điểm. Sau khi listener được gỡ chặn, một event đã nằm trong queue không tự bị xóa. Ngoài ra monitor có thể đã phát thêm event trước khi consumer thực sự quay lại poll.

Đo phục hồi bằng **poll/receive tiến triển**, xử lý message mới và metrics phù hợp; không chỉ bằng việc `events.isEmpty()`.

## 13. Test âm: consumer khỏe mạnh không bị báo lỗi

Một test âm giúp phát hiện cấu hình threshold quá nhạy hoặc probe thu nhầm event.

Kịch bản:

1. Dùng listener đơn giản không block và trả về ngay.
2. Chờ partition assignment.
3. Gửi một số record và xác nhận tất cả đã được xử lý.
4. Trong một cửa sổ quan sát có độ dài hợp lý, xác nhận không có `NonResponsiveConsumerEvent` cho listener đó.
5. Phân biệt event do các listener khác trong cùng context.

Một listener bình thường:

```java
public final class FastListener {
    private final CountDownLatch received = new CountDownLatch(3);

    @KafkaListener(
            id = "fast-consumer",
            topics = "fast-consumer-test",
            containerFactory = "nonResponsiveTestFactory")
    public void onMessage(String payload) {
        received.countDown();
    }
}
```

Để kiểm tra “không có event”, hãy dùng một probe lọc theo `fast-consumer` và một khoảng quan sát hữu hạn, **không suy luận vĩnh viễn rằng sẽ không bao giờ có event**. Một kết quả âm chỉ được đảm bảo trong thời gian và môi trường test đã đo.

Test âm có thể bị nhiễu khi máy CI tạm dừng JVM quá lâu, GC pause bất thường hoặc hệ thống quá tải. Điều này chính là lý do không cấu hình ngưỡng quá nhỏ và không đặt assertion thời gian quá chặt.

## 14. Giới hạn của test bằng latch

Fixture dùng `CountDownLatch` chứng minh một trường hợp **consumer không quay lại poll vì message handler đang chờ**. Nó không nhất thiết mô phỏng:

- TCP connection bị half-open giữa Kafka client và broker.
- Kafka client thread bị kẹt sâu bên trong `poll()`.
- DNS hoặc TLS handshake bất thường.
- Broker metadata/coordinator response chậm.
- Consumer group rebalance kéo dài.
- Một ứng dụng bị CPU starvation thực tế.

Vì vậy, kết luận đúng là:

> “Với cấu hình monitor được kiểm thử, khi listener không hoàn tất và polling không tiến triển quá ngưỡng, Spring Kafka phát `NonResponsiveConsumerEvent` như mong đợi.”

**Không kết luận:** “Test này chứng minh ứng dụng tự khôi phục mọi lỗi mạng Kafka.” Điều đó đòi hỏi kiểm thử lỗi mạng và chiến lược recovery riêng.

## 15. Fault injection: giả lập vấn đề network/broker

Để kiểm thử độ tin cậy sâu hơn, dùng một môi trường Kafka test độc lập, ví dụ Testcontainers Kafka kết hợp một network proxy như Toxiproxy.

Mục tiêu có thể là:

- Chèn latency hoặc cắt kết nối giữa consumer và broker.
- Tạo lỗi mạng từng khoảng ngắn rồi khôi phục.
- Tắt hoặc restart một broker trong cụm test.
- Mô phỏng network partition giữa consumer và broker.
- Quan sát listener container, sự kiện lỗi, consumer group assignment và khả năng tiêu thụ sau recovery.

Sơ đồ:

```text
Spring Kafka Consumer
        |
        v
  Network proxy (Toxiproxy)
        |
        v
    Kafka Broker
        |
        v
  Topic/Partitions
```

**Lưu ý quan trọng khi Kafka qua proxy:** Kafka client không chỉ sử dụng địa chỉ bootstrap. Sau khi lấy metadata, client kết nối tới các broker theo `advertised.listeners`. Nếu các advertised endpoints không đi qua proxy, test “đã cắt bootstrap connection” nhưng traffic thực tế vẫn đi thẳng tới broker và không mô phỏng đúng sự cố. Mọi broker endpoint cần được route qua mạng test như thiết kế.

Không nên dùng lỗi mạng để ép một Kafka client vào trạng thái treo vô hạn theo kỳ vọng cứng nhắc. Kafka client có timeout/reconnect và có thể tiếp tục poll trả về rỗng, ném exception, rebalance hoặc retry mà **không phát `NonResponsiveConsumerEvent`**. Đó vẫn có thể là hành vi đúng tùy loại lỗi.

Một fault-injection test tốt cần ghi nhận:

1. Fault được kích hoạt ở đúng endpoint.
2. Consumer còn polling hay không.
3. Những event nào xuất hiện (`NonResponsiveConsumerEvent`, các event lỗi, rebalance, stopped, v.v.).
4. Consumer group bị ảnh hưởng ra sao.
5. Sau khi hết fault, các record đã được xử lý đủ chưa.
6. Có duplicate do retry/offset commit không.
7. Ứng dụng có phải restart container hoặc process không.

## 16. Event handler production: quan sát trước, phản ứng có kiểm soát

Khi nhận `NonResponsiveConsumerEvent`, hành động đầu tiên thường nên là **ghi log có cấu trúc và tăng metric**, không tự động kill consumer.

Ví dụ:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
public final class ConsumerResponsivenessObserver {

    private static final Logger log =
            LoggerFactory.getLogger(ConsumerResponsivenessObserver.class);

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.warn(
                "kafka.consumer.nonresponsive listenerId={} "
                    + "timeSinceLastPollMs={}",
                event.getListenerId(),
                event.getTimeSinceLastPoll()
        );

        // Có thể tăng metric hoặc gửi tín hiệu cho monitor.
        // Không gọi trực tiếp các thao tác KafkaConsumer
        // không thread-safe từ event thread.
    }
}
```

Event handler nên xử lý nhanh. Nếu handler gửi HTTP đến hệ thống alert và chờ lâu, bản thân nó có thể làm nghẽn thread công bố event hoặc tăng áp lực lên hệ thống monitor.

### Những thông tin nên bổ sung vào cảnh báo

- `listenerId` và container ID.
- Application instance/pod/host.
- Consumer group ID.
- Topic/partition liên quan nếu xác định được.
- `timeSinceLastPollMs`.
- Thời gian bắt đầu sự kiện và số lần lặp.
- Kafka consumer lag theo partition.
- Last successfully processed offset và thời điểm xử lý cuối.
- `max.poll.interval.ms`, `pollTimeout`, `noPollThreshold`, `monitorInterval`.
- CPU, GC pause, active thread, blocked thread, DB/HTTP latency.

Không cố đưa hàng loạt object `ConsumerRecord` hoặc payload chưa được lọc vào cảnh báo. Dữ liệu message có thể chứa PII hoặc thông tin nội bộ.

## 17. Có nên tự động restart container khi nhận event?

**Không nên mặc định restart ngay mỗi lần có event.** Có thể xảy ra:

- Listener đang xử lý một record hợp lệ nhưng mất nhiều thời gian.
- Một external API đang đợi trả kết quả; restart container không làm side effect bên ngoài biến mất.
- Một message “độc” khiến listener liên tục block; restart chỉ tạo loop.
- `max.poll.interval.ms` hoặc rebalancing đã làm consumer mất assignment; restart chồng thêm biến động.
- Nếu listener xử lý với transaction hoặc manual acknowledgments, restart có thể dẫn đến redelivery.
- Event được phát lặp, khiến nhiều lệnh restart cạnh tranh nhau.

Một chính sách remediation nên xét:

| Điều kiện | Hành động đề xuất |
| --- | --- |
| Một event ngắn, lag thấp, consumer sau đó tiến triển | Ghi metric/log, theo dõi. |
| Nhiều event liên tiếp, không có offset tiến triển | Cảnh báo và thu thread dump trước khi can thiệp. |
| Thread bị kẹt ở remote call | Kiểm tra timeout, circuit breaker, dependency health. |
| Thread thật sự kẹt trong Kafka poll/network | Cân nhắc cơ chế wakeup/stop/restart được hỗ trợ, với kiểm soát lifecycle. |
| Repeated crash/restart cùng record | Điều tra poison record, retry/DLT và idempotency. |
| Consumer group liên tục rebalance | Kiểm tra poll interval, xử lý batch, static membership và tài nguyên. |

Nếu cần tự động khôi phục:

1. Dùng **cooldown** để không restart liên tục.
2. Chỉ cho phép một remediation cùng lúc cho một container.
3. Kiểm tra trạng thái container và assignment hiện tại.
4. Lưu sự kiện nguyên nhân trước khi restart.
5. Dùng API lifecycle của container đúng theo phiên bản và thread contract.
6. Chờ container dừng hẳn trước khi khởi động lại nếu chính sách đòi hỏi.
7. Giới hạn số lần restart và escalates to operator khi không tiến triển.
8. Kiểm tra idempotency của xử lý message khi có redelivery.

**Không gọi `consumer.poll()`, `commitSync()` hoặc `seek()` tùy tiện từ event thread.** `KafkaConsumer` có quy tắc sử dụng theo thread, và sửa offset khi worker đang xử lý record có thể phá thứ tự và tính đúng đắn.

## 18. `wakeup()` không phải nút “sửa mọi consumer”

Kafka consumer API có `wakeup()` là thao tác có thể được gọi từ thread khác theo hợp đồng Kafka client, nhằm đánh thức consumer khỏi các thao tác có thể bị ngắt. Tuy nhiên:

- Nó không làm một callback listener đang chờ database/HTTP tự kết thúc.
- Nó không thay thế timeout mạng hoặc transaction.
- Nó có thể tạo exception được Kafka client/container xử lý theo lifecycle riêng.
- Nó không xác nhận record hiện tại đã được commit hoặc hoàn tất.
- Gọi lặp vô tội vạ có thể làm tình trạng vận hành khó chẩn đoán hơn.

Vì vậy, nếu ứng dụng sử dụng wakeup như một phần quy trình khôi phục, cần kiểm thử cả trường hợp đang poll thật và trường hợp đang block **trong listener**. Không tự ý gọi `wakeup()` khi chưa hiểu container xử lý exception và offset theo phiên bản đang dùng.

## 19. Tác động tới at-least-once và offset commit

Một consumer không poll lâu có thể kéo theo timeout group hoặc rebalance. Khi partition được giao lại cho consumer khác, message chưa commit có thể được phân phối lại.

Giả sử:

```text
Consumer A poll record offset=100
        |
        v
Listener A gọi remote API, xử lý lâu
        |
        v
max.poll.interval.ms bị vượt
        |
        v
Group thay đổi assignment
        |
        v
Consumer B nhận partition, có thể đọc lại offset=100
        |
        v
Remote operation có nguy cơ thực hiện hai lần
```

Mức độ redelivery phụ thuộc commit mode, transaction và offset đã commit. Nhưng nguyên tắc chung với xử lý at-least-once là **cùng record có thể được xử lý hơn một lần** trong lỗi/rebalance.

Vì vậy, bài test reliability không nên chỉ assert “event đã phát”. Với nghiệp vụ quan trọng cần thêm:

- Một business key/idempotency key ổn định trong message.
- Ghi nhận những offset đã xử lý thành công.
- Kiểm tra không có side effect trùng hoặc có dedup đúng.
- Phân biệt record đang xử lý với record đã ack/commit.
- Kiểm tra retry và DLT khi gặp poison record.
- Khi consumer phục hồi, xác nhận tiến độ offset tiếp tục từ vị trí hợp lệ.

Không dùng event để tự động commit offset của record đang xử lý dở chỉ nhằm “làm lag giảm”. Điều đó có thể làm mất dữ liệu.

## 20. Test khác nhau theo ack mode và xử lý batch

Spring Kafka hỗ trợ các chế độ ack/commit khác nhau qua container. Test cần phản ánh chính sách thực tế:

| Kiểu xử lý | Điểm cần kiểm tra khi consumer không poll |
| --- | --- |
| Record listener, ack mặc định của container | Message đang xử lý có được commit chưa; có redelivery khi restart không. |
| Manual ack | Listener đã ack trước hay sau side effect; nếu block trước ack thì xử lý lại ra sao. |
| Batch listener | Một batch lớn có kéo dài khoảng giữa hai poll không; các record lỗi có ảnh hưởng cả batch không. |
| Transactional Kafka processing | Transaction timeout, abort/retry và offset commit trong transaction được xử lý thế nào. |
| Concurrent listener containers | Event thuộc child nào; chỉ một partition hay nhiều partition bị ảnh hưởng. |
| Retry/DLT | Poison record được retry có giới hạn hay block mãi một worker. |

Nếu bài test chỉ chạy một partition và một consumer, nó giúp chứng minh logic monitor nhưng **chưa đại diện cho nhiều partition/concurrency**. Khi mở rộng, nên gắn probe theo listener/container ID và kiểm tra đủ assignment.

### Không che khuất vấn đề bằng concurrency cao

Tăng concurrency có thể làm tổng throughput tốt hơn trong lúc một child bị block, nhưng child đó vẫn giữ partition được giao và có thể không xử lý record mới. Tổng lag có thể trông bình thường trong khi một partition bị tụt lại. Theo dõi lag/last processed offset **theo partition** khi có yêu cầu tiến độ chặt.

## 21. Tránh flakiness trong CI

Kiểm thử thời gian thực và thread có các nguồn biến thiên: khởi động Embedded Kafka, JVM warmup, CI scheduler, GC, rebalancing và thời gian ghi log.

Các biện pháp:

1. **Chờ partition assignment** trước khi gửi record.
2. **Chờ latch listener entered** trước khi chờ event.
3. **Cấu hình threshold test đủ nhỏ nhưng không sát 0**: `pollTimeout=500ms`, `noPollThreshold=3.0`, `monitorInterval=1s` chỉ là một ví dụ.
4. **Dùng bounded wait** cho event, không dùng sleep rồi kiểm tra ngay.
5. **Không assert thời điểm event chính xác**; chỉ assert event xuất hiện trong cửa sổ đủ rộng.
6. **Lọc event theo listener ID**; Spring context có thể có nhiều KafkaListener.
7. **Luôn release latch trong `finally`**.
8. **Không chạy nhiều test dùng chung group/topic/fixture** nếu có thể tranh record.
9. **Không phụ thuộc message delivery order giữa nhiều partition** nếu ứng dụng không yêu cầu.
10. **Làm sạch/restart context hợp lý**, không dừng consumer đang còn chạy khi test kết thúc đột ngột.
11. **Không dùng production thresholds** trong test ngắn nếu monitor mặc định 30 giây.
12. **Thu log/topic/group diagnostic khi fail** để phân biệt lỗi setup với lỗi feature.

### Kiểm soát test teardown

Nếu một assertion fail trước khi gọi `release.countDown()`, consumer thread có thể vẫn block. Vì vậy `try/finally` là bắt buộc. Ngoài ra, listener fixture nên có timeout nội bộ để tự thoát nếu test runner chết bất thường.

Nếu dùng `@DirtiesContext` để cô lập thử nghiệm, cân nhắc chi phí khởi tạo Embedded Kafka khi có nhiều test. Đừng gọi `context.close()` tùy tiện giữa test nếu những bean khác còn đang dùng consumer/container.

## 22. Debug khi không nhận được `NonResponsiveConsumerEvent`

Giả sử test chờ 10 giây nhưng không có event. Kiểm tra theo thứ tự:

### 22.1. Listener có nhận message chưa?

Nếu `entered.await(...)` không thành công, vấn đề có thể là:

- Container chưa được gán partition.
- Producer gửi sai topic.
- Group hoặc deserializer sai.
- Embedded Kafka bootstrap servers không được trỏ đúng.
- Container factory hoặc bean KafkaListener không được đăng ký.
- Topic/partition không tồn tại hoặc test dùng sai profile.

**Không điều tra monitor trước khi chứng minh listener đã bắt đầu xử lý.**

### 22.2. Đúng factory chưa?

`@KafkaListener` phải dùng `containerFactory="nonResponsiveTestFactory"` nếu threshold được đặt trên factory này. Nếu quên, listener có thể dùng `kafkaListenerContainerFactory` mặc định với ngưỡng monitor lớn hơn thời gian test.

### 22.3. Monitor có đang kiểm tra theo chu kỳ mong đợi?

Xác minh giá trị `pollTimeout`, `noPollThreshold`, `monitorInterval` thật của container đang chạy. Nếu threshold bằng vài giây nhưng monitor kiểm tra 30 giây một lần, test chờ 8 giây có thể không đủ.

### 22.4. Callback có thật sự block không?

Một phương thức listener test có thể thoát sớm do:

- Latch đã bị count down từ test trước.
- Mã thử chỉ block một loại payload nhưng message gửi không trùng.
- Exception làm callback kết thúc.
- Test gửi record vào listener khác.

Dùng `entered`, `completed` và số lần xử lý để xác nhận trạng thái.

### 22.5. Probe có đăng ký vào Spring context không?

`@EventListener` chỉ hoạt động khi đối tượng được Spring quản lý. Nếu test tự tạo `new NonResponsiveEventProbe()` nhưng không đăng ký bean, event publisher không biết probe đó.

### 22.6. Event có bị lọc sai ID không?

Concurrent containers có thể phát event với ID mang hậu tố. Nếu dùng so sánh exact string, probe có thể bỏ qua event hợp lệ.

### 22.7. Thread ứng dụng có bị đình trệ chung không?

Nếu cả JVM bị pause dài hoặc hệ thống CI thiếu tài nguyên, monitor cũng không có cơ hội chạy đúng chu kỳ. Kết quả test thời gian có thể lệch và cần phân tích CPU/GC/scheduling.

## 23. Debug khi event xuất hiện dù consumer vẫn “khỏe”

Một cảnh báo non-responsive không đồng nghĩa chắc chắn có lỗi Kafka client.

Các câu hỏi cần kiểm tra:

- Listener đang xử lý một record hợp lệ nhưng mất nhiều thời gian?
- Có retry/backoff đồng bộ giữ thread listener?
- Database đang có lock wait?
- Một remote API call không có timeout?
- Có quá nhiều record mỗi poll do `max.poll.records`?
- Thread pool/CPU/GC có bị quá tải?
- Threshold monitor có được đặt thấp hơn thời gian xử lý P99 bình thường?
- Container có đang trong quá trình start/stop/rebalance?
- Event có đến từ child container khác không?

Nếu thường xuyên xử lý lâu nhưng đúng nghiệp vụ, có thể cần tối ưu xử lý, giảm batch/poll size, tách tác vụ chậm khỏi consumer thread hoặc điều chỉnh cấu hình. Chỉ tăng threshold để không còn cảnh báo có thể che giấu một bottleneck thực.

## 24. Điều tra consumer bị kẹt thực sự

Một quy trình vận hành có thể:

1. Xác định `listenerId`, group, topic/partition, instance và thời điểm event.
2. Kiểm tra `timeSinceLastPollMs` và số lần event lặp.
3. Kiểm tra consumer lag/offset progression theo partition.
4. Thu **thread dump** để xem consumer thread đang ở `poll()`, listener callback, JDBC, HTTP hay lock wait.
5. Kiểm tra CPU, GC pause, thread pool và connection pool.
6. Kiểm tra broker health, network latency, coordinator/rebalance log.
7. Đối chiếu `max.poll.interval.ms` với thời gian xử lý P99.
8. Chỉ khi đã phân loại nguyên nhân mới chọn giải pháp: timeout, retry, DLT, tăng parallelism, sửa deadlock hoặc restart có kiểm soát.
9. Sau khôi phục, xác minh xử lý message đúng, không mất và không trùng side effect.

Không dùng duy nhất giá trị `timeSinceLastPollMs` để kết luận thread deadlocked. Nó là dấu hiệu để bắt đầu điều tra.

## 25. Observability: metric, logging và alert

Những tín hiệu hữu ích:

| Tín hiệu | Nội dung | Cách dùng |
| --- | --- | --- |
| `nonresponsive_event_total` | Số event theo listener/group và môi trường. | Phát hiện tần suất cảnh báo tăng. |
| `time_since_last_poll_ms` | Khoảng không poll được monitor ghi nhận. | Phân biệt event nhẹ với tình trạng kéo dài. |
| Consumer lag theo partition | Record chưa tiêu thụ so với end offset. | Nhận biết mất tiến độ và backlog. |
| Last processed offset/time | Offset/thời điểm xử lý thành công gần nhất. | Phát hiện không tiến triển dù ứng dụng còn chạy. |
| Listener processing duration | P50/P95/P99 thời gian xử lý record/batch. | Điều chỉnh batch size và poll interval. |
| Retry/DLT count | Lỗi nghiệp vụ đang lặp lại. | Phân biệt poison record với lỗi infrastructure. |
| Rebalance count/duration | Tần suất group thay đổi assignment. | Xem liên hệ với poll interval. |
| JVM thread/GC/CPU | Áp lực tài nguyên. | Chẩn đoán thread đình trệ. |
| DB/HTTP latency | Độ trễ dependency ngoài Kafka. | Xác định listener bị block ở đâu. |

Các tên metric ở trên là **đề xuất thiết kế**, không phải tất cả đều được Spring Kafka/Micrometer xuất sẵn với đúng tên đó. Đối với metric tự định nghĩa, dùng tag cardinality thấp như `listenerId`, `groupId` và môi trường; không đưa mỗi message key hay offset riêng làm tag.

### Khi nào nên cảnh báo?

Ví dụ chính sách:

```text
Nếu có một NonResponsiveConsumerEvent:
  -> log WARN, tăng counter, ghi lastPollGap

Nếu event lặp và không có offset progression:
  -> alert operator + thread dump

Nếu lag tăng vượt SLA hoặc consumer mất group:
  -> incident severity cao hơn

Nếu consumer hồi phục, xử lý record mới thành công:
  -> ghi trạng thái recovered, đóng cảnh báo sau cooldown
```

Đây là **gợi ý vận hành**, không phải ngưỡng mặc định của Spring Kafka. Chọn threshold theo thời gian xử lý dữ liệu và nhu cầu nghiệp vụ.

## 26. Bài tập thực hành

Xây dựng `orderEventsListener` nhận sự kiện đơn hàng trên topic `orders-events` và gọi một remote service để kiểm tra tình trạng sản phẩm. Có lúc remote service phản hồi sau 20 giây.

### Phần A – Phát hiện

1. Tạo `ConcurrentKafkaListenerContainerFactory` có `pollTimeout`, `noPollThreshold` và `monitorInterval` phù hợp test.
2. Tạo một listener test dùng `CountDownLatch` để block sau khi nhận record.
3. Tạo event probe nhận `NonResponsiveConsumerEvent` và lọc theo listener ID.
4. Dùng `@EmbeddedKafka` gửi record và chờ partition assignment.
5. Assert có event sau khi listener bị block, với timeout có giới hạn.
6. Dùng `finally` giải phóng latch.

### Phần B – Phục hồi

1. Cho listener hoàn tất, gửi một record tiếp theo.
2. Xác nhận consumer thực sự tiếp tục nhận và xử lý message.
3. Kiểm tra không có side effect trùng khi callback hoàn tất/retry.
4. Thử kéo dài block để quan sát ảnh hưởng của `max.poll.interval.ms` và rebalance.

### Phần C – Lỗi thật

1. Dùng Kafka test cluster + proxy để thử network latency và disconnect.
2. Ghi nhận liệu `NonResponsiveConsumerEvent` có xuất hiện hay không trong từng loại fault.
3. Theo dõi group assignment và lag.
4. Khôi phục network và kiểm tra consumer tiêu thụ tiếp.
5. Không coi việc “không có non-responsive event” là lỗi test nếu client vẫn poll được bình thường dưới fault đó.

### Phần D – Vận hành

1. Thêm structured logging với listener ID, thời gian không poll và host.
2. Thêm cảnh báo chỉ khi không có offset tiến triển qua nhiều chu kỳ.
3. Ghi lại thread dump khi event lặp.
4. Thử một listener bị block ở HTTP, một listener xử lý bình thường.
5. Thảo luận tác động của restart container với at-least-once delivery và idempotency.

### Câu hỏi tự đánh giá

- Sự khác nhau giữa `ListenerContainerIdleEvent` và `NonResponsiveConsumerEvent` là gì?
- Vì sao event non-responsive không chứng minh Kafka broker đang down?
- Vai trò riêng của `monitorInterval`, `pollTimeout` và `noPollThreshold`?
- Vì sao không nên assert event xuất hiện đúng ở thời điểm `noPollThreshold × pollTimeout`?
- Nếu listener block trong HTTP call, `wakeup()` có chắc chắn khôi phục listener không?
- `max.poll.interval.ms` liên quan gì tới xử lý một batch quá lâu?
- Sau khi Kafka rebalance, tại sao một record có thể bị xử lý lại?
- Làm thế nào phân biệt một consumer đang idle, một consumer bị block và một consumer chỉ có lag cao?

## Tài liệu tham khảo

- [Spring for Apache Kafka Reference – Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html): các sự kiện listener container, bao gồm `NonResponsiveConsumerEvent`.
- [Spring for Apache Kafka Reference – Non-Responsive Consumer](https://docs.spring.io/spring-kafka/reference/kafka/non-responsive-consumer.html): cấu hình monitor và cách phát hiện consumer không polling.
- [Spring for Apache Kafka Reference – Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html): `pollTimeout`, `noPollThreshold`, `monitorInterval` và cấu hình container.
- [Spring for Apache Kafka Reference – Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka`, `spring-kafka-test`, kiểm thử listener.
- [Apache Kafka – Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs): `max.poll.interval.ms` và các cấu hình Kafka consumer.
- [Apache Kafka – KafkaConsumer API](https://kafka.apache.org/documentation/#consumerapi): nguyên tắc poll, timeout, wakeup và thread safety.
- [Testcontainers – Kafka Module](https://java.testcontainers.org/modules/kafka/): Kafka test trong container, phù hợp integration/fault injection.

