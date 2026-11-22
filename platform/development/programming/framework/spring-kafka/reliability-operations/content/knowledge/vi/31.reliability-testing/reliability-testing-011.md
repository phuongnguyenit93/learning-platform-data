# Test pause và resume trong Spring Kafka

Khi hệ thống downstream chậm, database quá tải hoặc một dịch vụ phụ thuộc đang bảo trì, ứng dụng tiêu thụ Kafka có thể cần **tạm ngừng nhận thêm bản ghi** mà không muốn rời consumer group. Trong Spring Kafka, `pause()` và `resume()` trên **listener container** là công cụ hữu ích để kiểm soát luồng xử lý. Tuy nhiên, gọi `pause()` không có nghĩa consumer dừng tức thì; còn `resume()` không bảo đảm toàn bộ backlog đã được xử lý thành công.

Chủ đề **Test pause và resume** thuộc **Spring Kafka Reliability Operations → Kiểm thử tin cậy**. Mục tiêu là thiết kế bài kiểm thử chứng minh được ba điều: **consumer đã thực sự pause**, **message gửi trong thời gian pause không bị xử lý sớm**, và **sau resume, backlog được xử lý theo đúng hợp đồng offset/acknowledgment**.

```text
                      Kafka topic
                  partition 0: A B C D E
                               |
                               v
                    Spring Kafka container
                      (poll vẫn diễn ra)
                               |
              +----------------+----------------+
              |                                 |
          RUNNING                            PAUSED
         nhận record                     không chuyển thêm
         vào listener                    record mới tới listener
              |                                 |
              +----------- resume() ------------+
                               |
                               v
                       xử lý backlog
                               |
                       commit offset
                    theo AckMode đang dùng
```

**Phân biệt:** pause không xóa message khỏi Kafka, không tự commit offset và không thay thế retry/DLT. Nó chỉ tạm dừng việc tiếp tục đưa record tới listener theo phạm vi pause. Hành vi xử lý record đã được poll, giao lại sau crash và commit offset vẫn phải được kiểm thử riêng.

## 1. Mục tiêu kiểm thử và tiêu chí thành công

Một bộ test có giá trị cần quan sát **trạng thái thực** của listener container và **kết quả xử lý record**, không chỉ xác nhận method `pause()` được gọi.

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Listener đang chạy | Consumer đã được assign partition và xử lý được message thử nghiệm |
| Gọi `pause()` | Container ghi nhận pause request, sau đó thực sự đi vào trạng thái paused |
| Producer gửi sau khi pause đã có hiệu lực | Producer nhận ack nhưng listener không xử lý message trong cửa sổ quan sát |
| Gọi `resume()` | Container rời trạng thái paused và xử lý message đang chờ |
| Pause khi listener đang xử lý record | Record in-flight có thể hoàn tất; không đòi pause ngắt thread đang chạy |
| Pause lâu | Container vẫn poll để duy trì membership, tùy tình trạng broker/network và thời gian xử lý |
| Restart/rebalance | Trạng thái pause và việc giao lại record phải được hiểu theo lifecycle thực, không suy đoán |
| Offset/side effect | Không mất dữ liệu; việc chống ghi trùng phụ thuộc ack và idempotency |

Ví dụ một kết quả kiểm thử mong muốn:

```text
T0    Listener đã nhận partition 0
T1    container.pause()
T2    isContainerPaused() == true
T3    Producer gửi order-001, Kafka ack thành công
T4    Không có callback xử lý order-001 trong khoảng quan sát
T5    container.resume()
T6    isContainerPaused() == false
T7    Listener nhận order-001 và ghi kết quả
```

**T2 là mốc bắt buộc trước T3.** Nếu gửi ở T1, record có thể đã được fetch hoặc đưa tới listener trước khi lệnh pause có hiệu lực. Test như vậy dễ bị flaky dù thư viện hoạt động đúng.

## 2. `pause()` của container khác gì `pause()` của `KafkaConsumer`?

Apache Kafka có API `KafkaConsumer.pause(Collection<TopicPartition>)` và `resume(...)`. Spring Kafka bao bọc consumer bằng các listener container như `KafkaMessageListenerContainer` và `ConcurrentMessageListenerContainer`.

Ở ứng dụng dùng `@KafkaListener`, nên ưu tiên **API của container**:

```java
MessageListenerContainer container =
    registry.getListenerContainer("ordersListener");

container.pause();   // Yêu cầu container tạm ngừng nhận thêm record.
container.resume();  // Yêu cầu container tiếp tục.
```

Lý do:

- `KafkaConsumer` **không thread-safe**; gọi trực tiếp các method của consumer từ một HTTP controller hay thread khác có thể vi phạm hợp đồng của Kafka client.
- Container quản lý consumer thread, poll loop, partition assignment, acknowledgment, error handler và lifecycle.
- `pause()` ở container là một **request được áp dụng tại điểm an toàn của consumer loop**, không nhất thiết là trạng thái đã có hiệu lực ngay sau lời gọi.
- Với container đồng thời (*concurrency > 1*), pause ở container cấp cha cần phối hợp các consumer con; vì thế nên quan sát trạng thái đã pause thay vì giả định tất cả đã dừng cùng lúc.

Các API quan trọng (Spring Kafka 3.x):

| API | Vai trò |
| --- | --- |
| `pause()` | Yêu cầu pause các partition của listener container |
| `resume()` | Yêu cầu khôi phục nhận record |
| `isPauseRequested()` | Cho biết đã yêu cầu pause hay chưa |
| `isContainerPaused()` | Cho biết container thực sự ở trạng thái paused theo phạm vi của nó |
| `pausePartition(TopicPartition)` | Yêu cầu pause một partition cụ thể nếu API/phiên bản hỗ trợ |
| `resumePartition(TopicPartition)` | Cho phép tiếp tục partition cụ thể |
| `isPartitionPaused(TopicPartition)` | Quan sát trạng thái pause thực tế của partition |

`pause()` **không tương đương** `stop()`. Trong cơ chế pause của listener container, consumer vẫn được poll theo nhịp thích hợp để duy trì membership/heartbeat; còn `stop()` dừng container và thường kéo theo việc consumer rời nhóm hoặc partition được giao lại. Dùng stop khi muốn dừng hẳn workload; dùng pause khi muốn tạm ngừng delivery nhưng giữ consumer lifecycle.

### 2.1. Pause là trạng thái cục bộ của consumer

Nếu có hai consumer groups cùng đọc một topic, pause group A **không pause topic trên broker** và không ngăn group B đọc. Nếu có ba instance ứng dụng trong cùng group, chỉ pause container của một instance không đồng nghĩa tất cả instance còn lại đều pause.

```text
                      orders-topic
                       /        \
                      v          v
                 Group billing   Group reporting
                      |              |
                instance A        instance X
                PAUSED            RUNNING
                      |
                instance B
                RUNNING
```

Muốn ngừng xử lý của **cả group**, cần điều phối trạng thái trên mọi instance hoặc thiết kế cơ chế control plane tập trung. Một lời gọi REST tới một Pod ngẫu nhiên không đủ để bảo đảm toàn bộ group dừng.

## 3. Điều gì xảy ra trong poll loop khi pause?

Một consumer bình thường liên tục gọi `poll()` để nhận record và duy trì trạng thái nhóm. Khi Spring Kafka container được yêu cầu pause, container thực hiện pause trên các partition được assign ở thời điểm phù hợp, sau đó vẫn tiếp tục poll để phục vụ giao thức consumer group.

```text
Consumer thread:

poll()  -> records [A, B, C]
   |
   +--> listener xử lý A
   +--> thread điều khiển gọi container.pause()
   +--> listener có thể vẫn xử lý B và C đã poll
   +--> kết thúc phần đang xử lý
   +--> áp dụng consumer.pause(assigned partitions)
   +--> poll() khi paused: không fetch thêm record từ partition paused
   |
   +--> thread điều khiển gọi container.resume()
   +--> tiếp tục poll/delivery
```

**Không kỳ vọng pause cắt ngang một callback listener đang chạy.** Với một poll đã trả nhiều record, container có thể tiếp tục giao các record còn lại trước khi trạng thái paused có hiệu lực, phụ thuộc phiên bản/cấu hình. Spring Kafka có tùy chọn `pauseImmediate` cho một số loại container: khi được bật, việc pause có thể xảy ra ngay sau record hiện tại thay vì phải xử lý hết record trong poll, còn các record chưa giao sẽ được giữ lại để xử lý sau resume. Điều này không hủy transaction hoặc callback đang thực thi.

Nếu listener đang bị block lâu hơn `max.poll.interval.ms`, consumer vẫn có thể bị coi là không còn đáp ứng yêu cầu poll và dẫn tới rebalance. **Pause không chữa được listener đã bị kẹt bên trong callback**, vì container phải quay lại poll loop để duy trì nhịp hoạt động.

### 3.1. Pause không đổi offset

Giả sử partition có offset từ `0` đến `9`. Consumer đã commit offset kế tiếp là `4` (nghĩa là xử lý qua offset `3` theo hợp đồng ack của ứng dụng). Pause không tự commit tới `10` và cũng không xóa các record `4..9`.

```text
Kafka log:
offset        0 1 2 3 | 4 5 6 7 8 9
                      ^
                committed next offset = 4

Consumer PAUSED:
  record 4..9 còn ở Kafka, hoặc một phần đã được fetch trước pause

Consumer RESUMED:
  việc delivery tiếp tục theo consumer position/buffer và commit policy
```

Kafka consumer có **position hiện tại**, **committed offset** và có thể có **record đã fetch**. Ba khái niệm không nhất thiết trùng nhau. Sau crash/rebalance, việc replay thông thường dựa trên committed offsets, không dựa vào một log `pause()` đã được gọi.

Nếu pause kéo dài vượt thời gian retention của topic, một phần dữ liệu cũ có thể không còn trong Kafka khi resume; đó là rủi ro **retention**, không phải thao tác pause tự xóa record. Cần có monitoring backlog và chính sách giới hạn thời gian pause.

## 4. Cách điều khiển listener container theo `id`

Ví dụ listener:

```java
package com.example.kafka;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "orders-service"
    )
    public void onMessage(String payload) {
        // Validate, xử lý nghiệp vụ, ghi trạng thái idempotent.
        System.out.println("Received: " + payload);
    }
}
```

`id="ordersListener"` là **container ID** để `KafkaListenerEndpointRegistry` tra đúng listener. Không nhầm container ID với topic hoặc `groupId`. Trong hệ thống có nhiều `@KafkaListener`, controller phải biết listener nào được phép pause, không nên lấy ID không tin cậy rồi điều khiển tùy ý tất cả listener.

Một service điều khiển:

```java
package com.example.kafka;

import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class ListenerFlowControl {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerFlowControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    private MessageListenerContainer requireOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");
        if (container == null) {
            throw new IllegalStateException("ordersListener is not registered");
        }
        return container;
    }

    public void requestPause() {
        requireOrdersListener().pause();
    }

    public void requestResume() {
        requireOrdersListener().resume();
    }

    public boolean pauseRequested() {
        return requireOrdersListener().isPauseRequested();
    }

    public boolean actuallyPaused() {
        return requireOrdersListener().isContainerPaused();
    }
}
```

`requestPause()` trả về nhanh không có nghĩa mọi partition đã pause. Vì vậy vận hành nên phân biệt:

```text
pauseRequested = true
isContainerPaused = false
  → lệnh đã được nhận nhưng consumer có thể đang xử lý poll hiện tại

pauseRequested = true
isContainerPaused = true
  → container đã xác nhận trạng thái paused
```

Tương tự, sau `resume()`, cần chờ trạng thái pause thực sự được gỡ trước khi khẳng định consumer đã resume. Dù trạng thái đã resume, không có message mới cũng không đồng nghĩa có lỗi.

## 5. Kế hoạch test có thể lặp lại, tránh timing flaky

Trình tự kiểm thử nên dùng **barrier và trạng thái thật**:

```text
1. Tạo topic riêng, consumer group riêng và một listener.
2. Chờ container được assign partition.
3. Gọi pause().
4. Chờ isContainerPaused() == true.
5. Gửi message X, chờ producer Future trả về thành công.
6. Xác nhận X chưa được listener ghi nhận trong cửa sổ quan sát.
7. Gọi resume().
8. Chờ isContainerPaused() == false.
9. Xác nhận listener nhận X, output đúng.
```

Test nên có **một partition và một consumer thread trước**, để loại bỏ nhiễu do nhiều partition hoặc rebalance. Sau khi baseline ổn định mới mở rộng sang concurrency > 1.

**Không nên làm:**

```java
container.pause();
kafkaTemplate.send(topic, value);
Thread.sleep(100);
assertThat(received).isEmpty();
```

Lỗi ở đây là chưa chờ pause có hiệu lực và chưa chờ producer gửi thành công. `Thread.sleep(100)` còn phụ thuộc tốc độ CPU, broker, CI runner và scheduling, nên có thể cho kết quả ngẫu nhiên.

### 5.1. Nguồn quan sát đáng tin

| Nguồn | Dùng để kiểm chứng | Giới hạn |
| --- | --- | --- |
| `isContainerPaused()` | Container đã áp dụng trạng thái pause | Không mô tả mọi sự kiện in-flight trước pause |
| `ConsumerPausedEvent` | Nhận thông báo trạng thái paused từ container | Cần lọc đúng container/partition và đợi event |
| `BlockingQueue`/latch trong listener test | Có callback xử lý record hay chưa | Không tự chứng minh transaction DB/offset đã commit |
| Producer `Future.get()` | Broker đã nhận/ack theo cấu hình producer | Không chứng minh listener đã xử lý |
| Output DB/idempotency key | Side effect nghiệp vụ có được ghi hay không | Cần transaction và fixture rõ ràng |
| Consumer group offsets/lag | Backlog và tiến độ commit | Lag không nhất thiết về 0 tức thì sau resume |

Với negative assertion “không có callback trong lúc paused”, luôn xác nhận **pause đã active trước khi gửi message**. Sau đó kiểm tra bằng một khoảng quan sát hữu hạn, đủ để phát hiện callback bất thường nhưng không kéo dài suite vô ích.

## 6. Project test với Spring Boot 3.x và Spring Kafka 3.x

Ví dụ dưới đây dùng **Java 17+, Spring Boot 3.x, Spring Kafka 3.x, JUnit Jupiter**, `@EmbeddedKafka` và Awaitility. Đây là kịch bản kiểm thử ở môi trường test; khi chạy production thường kết nối một Kafka cluster thật qua cấu hình hạ tầng.

### 6.1. Dependency Gradle

Với một project Spring Boot đã quản lý version qua BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.awaitility:awaitility'
}
```

Spring Kafka và test module nên theo **version tương thích do Spring Boot BOM quản lý**. Không trộn tùy tiện Spring Kafka 2.x, 3.x và Boot 4.x vì một số API, package, thuộc tính container và hành vi embedded broker có thể thay đổi.

### 6.2. Integration test `@EmbeddedKafka`

Ví dụ test tạo một listener trong cấu hình test, gửi record **sau khi container thật sự paused**, rồi xác nhận resume giao lại record đó:

```java
package com.example.kafka;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;
import org.springframework.test.annotation.DirtiesContext;

@SpringBootTest(
    classes = PauseResumeIntegrationTest.TestApplication.class,
    properties = {
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.key-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.producer.key-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.listener.missing-topics-fatal=true"
    }
)
@EmbeddedKafka(
    partitions = 1,
    topics = "orders.pause.test",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class PauseResumeIntegrationTest {

    static final String TOPIC = "orders.pause.test";

    @Autowired KafkaListenerEndpointRegistry registry;
    @Autowired KafkaTemplate<String, String> kafkaTemplate;
    @Autowired ReceivedProbe probe;

    @Test
    void pausingStopsDeliveryAndResumingProcessesBacklog()
            throws Exception {

        MessageListenerContainer container =
            Objects.requireNonNull(
                registry.getListenerContainer("ordersListener"));

        // Không gọi pause trước khi consumer được assign partition.
        ContainerTestUtils.waitForAssignment(container, 1);

        container.pause();
        await().atMost(Duration.ofSeconds(10))
            .until(container::isContainerPaused);

        assertThat(container.isPauseRequested()).isTrue();

        String payload = "order-pause-001";
        kafkaTemplate.send(TOPIC, payload)
            .get(10, TimeUnit.SECONDS); // Producer đã được Kafka ack.

        // Record được gửi SAU khi paused phải chưa đến listener.
        assertThat(probe.received.poll(700, TimeUnit.MILLISECONDS))
            .isNull();

        container.resume();
        await().atMost(Duration.ofSeconds(10))
            .until(() -> !container.isContainerPaused());

        // Message vẫn ở Kafka và được listener xử lý sau resume.
        assertThat(probe.received.poll(10, TimeUnit.SECONDS))
            .isEqualTo(payload);
        assertThat(probe.received.poll(300, TimeUnit.MILLISECONDS))
            .isNull();
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableKafka
    static class TestApplication {
        @Bean
        ReceivedProbe receivedProbe() {
            return new ReceivedProbe();
        }
    }

    static class ReceivedProbe {
        final BlockingQueue<String> received =
            new LinkedBlockingQueue<>();

        @KafkaListener(
            id = "ordersListener",
            topics = TOPIC,
            groupId = "pause-resume-integration-test"
        )
        void onMessage(String payload) {
            received.add(payload);
        }
    }
}
```

Test sử dụng cấu hình ứng dụng con để tập trung vào hành vi pause/resume, không yêu cầu tạo HTTP controller. Các điểm đáng chú ý:

1. `@EmbeddedKafka` tạo broker cho phạm vi test và đưa địa chỉ broker vào `spring.kafka.bootstrap-servers`.
2. `@EnableKafka` bật đăng ký listener; Spring Boot tạo `KafkaTemplate` và listener container factory theo dependency/config đã cung cấp.
3. `ContainerTestUtils.waitForAssignment(...)` đợi partition được assign thay vì đoán thời điểm container khởi động.
4. `container.pause()` là yêu cầu, `await(...).until(container::isContainerPaused)` mới là barrier xác nhận pause.
5. `KafkaTemplate.send(...).get(...)` chờ producer hoàn tất để test không nhầm “message chưa gửi” với “listener đã bị pause”.
6. Hàng đợi `BlockingQueue` ghi nhận **callback thật**, thay vì test chỉ mock `MessageListenerContainer.pause()`.
7. `@DirtiesContext` giúp đóng context/broker và hạn chế trạng thái listener còn sót khi chạy suite khác.

Trong một bộ test lớn, mỗi test nên có **topic/group ID riêng hoặc cleanup và isolation rõ ràng**, tránh message/committed offsets từ test trước làm nhiễu kết quả. Nếu test dùng broker chung, một group ID cố định và topic cũ có thể khiến listener nhận record không thuộc fixture hiện tại.

**Giới hạn của test:** test chứng minh pause/resume delivery trong một lần chạy ổn định. Nó **không chứng minh exactly-once sau crash**, không chứng minh state pause sống qua restart, và không thay thế test với Kafka broker thật/consumer rebalance.

## 7. Kiểm thử record đang xử lý (*in-flight*) khi pause

Một negative test dễ viết sai là yêu cầu **không còn bất kỳ callback nào ngay sau khi gọi `pause()`**. Hành vi đúng có thể là callback đang chạy hoặc record từ poll trước đó tiếp tục xử lý.

Mô phỏng listener dùng hai latch:

```java
final CountDownLatch entered = new CountDownLatch(1);
final CountDownLatch release = new CountDownLatch(1);

@KafkaListener(id = "slowListener", topics = "slow.orders")
public void onMessage(String payload) throws InterruptedException {
    entered.countDown();
    if (!release.await(10, TimeUnit.SECONDS)) {
        throw new IllegalStateException("Timed out in test listener");
    }
    processed.add(payload);
}
```

Đây là **fixture minh họa**, không phải một class test hoàn chỉnh; `processed` là queue hoặc list thread-safe do test chuẩn bị. Các bước kiểm thử:

1. Gửi `A`; đợi `entered.await(...)` để xác nhận listener đang xử lý `A`.
2. Gọi `container.pause()` trong thread test.
3. Kiểm tra `isPauseRequested()` có thể đã `true`, **nhưng chưa được đòi `isContainerPaused()==true`** vì callback `A` còn block.
4. Thả latch `release` để callback `A` hoàn tất.
5. Chờ `isContainerPaused()==true`; sau đó mới gửi `B`.
6. Xác nhận `B` không được xử lý trong khoảng paused; gọi `resume()` và xác nhận `B` được xử lý.

Nếu `pauseImmediate` được bật (phiên bản/cấu hình hỗ trợ), hãy kiểm tra thêm cách container giữ các record còn lại của poll. Nếu không bật, đừng áp đặt rằng một poll đã fetch 100 record chỉ được xử lý đúng một record sau khi pause request.

### 7.1. `max.poll.records` không phải số record bảo đảm xử lý

`max.poll.records` giới hạn số record trả về trong một lần `poll()` ở mức Kafka client; nó **không giới hạn số record trong backlog** hoặc tạo transaction business tự động. Khi test pause với nhiều record đã poll, thay đổi `max.poll.records` có thể ảnh hưởng số record tiếp tục được xử lý trước khi pause thật sự có hiệu lực. Dùng giá trị nhỏ khi muốn test dễ quan sát, nhưng test vẫn phải dựa vào trạng thái container và callback thực tế.

## 8. Dùng `ConsumerPausedEvent` và `ConsumerResumedEvent`

Spring Kafka phát các **application events** liên quan trạng thái listener container, trong đó có `ConsumerPausedEvent` và `ConsumerResumedEvent`. Chúng hữu ích cho logging, metrics và test chờ trạng thái mà không phải đọc log text.

Ví dụ một observer minh họa (Spring Kafka 3.x):

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPausedEvent;
import org.springframework.kafka.event.ConsumerResumedEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaPauseEventLogger {
    private static final Logger log =
        LoggerFactory.getLogger(KafkaPauseEventLogger.class);

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info("event=kafka.consumer.paused source={} partitions={}",
            event.getSource(), event.getPartitions());
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info("event=kafka.consumer.resumed source={} partitions={}",
            event.getSource(), event.getPartitions());
    }
}
```

Event có thông tin container/consumer và các partition liên quan. Với nhiều listener hoặc nhiều test context, cần **lọc đúng container ID/topic-partition** trước khi tính một event là bằng chứng của listener đang kiểm tra. Đồng thời tránh viết logic điều khiển consumer theo cách gọi trực tiếp `KafkaConsumer` từ một listener xử lý event chạy ở thread không phù hợp.

Để kiểm thử luồng pause/resume mà không phụ thuộc chi tiết event dispatcher, có thể ưu tiên `isContainerPaused()` làm điều kiện và dùng event như bằng chứng bổ sung. Khi cấu hình ứng dụng xử lý event bất đồng bộ, việc chờ event cũng cần latch/queue và timeout rõ ràng.

## 9. Test pause/resume theo từng partition

Không phải lúc nào cũng cần pause toàn bộ listener. Ví dụ topic có hai partition: partition 0 gặp dữ liệu đầu vào cần điều tra, partition 1 vẫn có thể xử lý bình thường.

```text
                  orders-topic
                  /          \
                 v            v
            partition 0   partition 1
              PAUSED        RUNNING
                 |            |
              backlog      tiếp tục
              tăng         xử lý
```

Với Spring Kafka version hỗ trợ partition-level pause:

```java
TopicPartition partition0 =
    new TopicPartition("orders-topic", 0);

MessageListenerContainer container =
    registry.getListenerContainer("ordersListener");

container.pausePartition(partition0);

await().atMost(Duration.ofSeconds(10))
    .until(() -> container.isPartitionPaused(partition0));

// Gửi record vào partition 0 và 1 để kiểm thử:
// template.send("orders-topic", 0, "k0", "A").get(...);
// template.send("orders-topic", 1, "k1", "B").get(...);
// B có thể được xử lý; A phải chờ tới khi resume partition 0.

container.resumePartition(partition0);
await().atMost(Duration.ofSeconds(10))
    .until(() -> !container.isPartitionPaused(partition0));
```

Đoạn này là **khung kiểm thử**, giả định topic có ít nhất hai partition, partition 0 được assign cho consumer/container đang điều khiển, cùng một consumer group và producer đã được cấu hình. Test hoàn chỉnh cần tạo topic hai partition, chờ assignment, gửi với **explicit partition** rồi quan sát queue theo partition (thay vì chỉ theo payload).

Với `concurrency > 1`, các partition có thể được phân cho các consumer con khác nhau; kiểm thử phải xác minh assignment và phạm vi container. `isContainerPaused()` là tín hiệu pause **toàn container**, không thể thay thế điều kiện `isPartitionPaused(partition0)` khi chỉ một partition bị pause.

### 9.1. Rebalance và partition reassignment

Khi consumer group rebalance, partition có thể bị revoke và gán sang consumer khác. Một yêu cầu pause cho partition ở container cũ không tự là chính sách ngăn xử lý trên **mọi instance**. Nếu hệ thống muốn giữ trạng thái “partition này phải tạm dừng” qua rebalance, phải thiết kế nơi lưu **desired state** và cơ chế áp dụng lại khi partition được assign, đồng thời kiểm tra tính nhất quán sau rebalance.

Test reliability mở rộng nên cố ý thêm/bớt consumer hoặc restart một instance, rồi kiểm tra partition đã được reassigned và trạng thái pause mong muốn. Đừng kết luận một lần pause thành công trên một consumer tương đương khóa topic trên broker.

## 10. Offset, acknowledgment và lỗi sau resume

Pause/resume **không thay đổi chính sách ack** đã cấu hình. Nếu dùng `AckMode.RECORD`, `AckMode.BATCH`, `MANUAL` hoặc `MANUAL_IMMEDIATE`, thời điểm commit và hành vi replay khi crash khác nhau.

| Tình huống | Điều phải hiểu |
| --- | --- |
| Pause trước khi message được fetch | Message còn ở Kafka; consumer sẽ fetch khi được resume và có quyền đọc |
| Pause sau khi message đã poll | Container có thể cần xử lý record đã fetch tùy cấu hình, rồi mới pause thật sự |
| Listener xử lý thành công nhưng process chết trước offset commit | Record có thể được giao lại sau restart/rebalance |
| Listener xử lý lỗi trong lúc resume | Error handler, retry/backoff, DLT và ack policy quyết định kết quả; pause không tự sửa lỗi |
| Commit offset xảy ra trước khi side effect business bền vững | Có rủi ro mất tác động nghiệp vụ dù record không còn được giao lại như mong đợi |
| Pause kéo dài khi retention hết hạn | Backlog có thể bị Kafka xóa theo retention; cần giám sát và recovery |

Một listener dùng manual acknowledgment (mẫu minh họa):

```java
@KafkaListener(
    id = "paymentsListener",
    topics = "payments.events",
    groupId = "payments-service"
)
public void handle(
        ConsumerRecord<String, String> record,
        Acknowledgment acknowledgment) {

    paymentService.applyIdempotently(
        record.key(), record.value());

    acknowledgment.acknowledge();
}
```

Trong đoạn trên, container factory phải được cấu hình **manual ack mode**, chẳng hạn `ContainerProperties.AckMode.MANUAL` hoặc `MANUAL_IMMEDIATE`, và `paymentService` là service ứng dụng. Không gọi `acknowledge()` trước khi side effect cần thiết được commit thành công nếu hợp đồng nghiệp vụ cần at-least-once processing.

Ngay cả nếu pause/resume hoạt động hoàn hảo, một crash sau khi database commit nhưng trước Kafka offset commit có thể dẫn đến **delivery lặp**. Vì vậy consumer idempotency (unique business key, deduplication, transactional outbox, v.v.) vẫn là yêu cầu độc lập với pause/resume.

### 10.1. Đừng dùng pause thay cho retry/DLT

Khi một record lỗi parse hoặc vi phạm quy tắc nghiệp vụ, **pause cả container vô thời hạn** có thể khiến các record khác bị chặn. Spring Kafka có các cơ chế `DefaultErrorHandler`, backoff, `DeadLetterPublishingRecoverer` và retry-topic phù hợp cho lỗi cụ thể.

Pause phù hợp hơn cho **vấn đề lưu lượng/capacity hoặc phụ thuộc tạm thời**, ví dụ database đang được bảo trì. Việc phân biệt hai chính sách nên được test:

- Lỗi dữ liệu một record: xử lý theo retry/skip/DLT đã thiết kế.
- Downstream quá tải diện rộng: pause toàn container hoặc partition được kiểm soát, rồi resume khi điều kiện phục hồi thỏa mãn.

## 11. Test backpressure: tự động pause và resume theo ngưỡng

Một ứng dụng có thể pause khi hàng đợi nội bộ, connection pool hoặc dịch vụ đích vượt ngưỡng; resume sau khi áp lực giảm. Mô hình nên dùng **hysteresis** để tránh bật/tắt quá nhanh:

```text
Độ sâu queue
   ^
  900 |                x       pause
  800 |---------- PAUSE_THRESHOLD ----------
  600 |               / \___
  400 |                      \__
  200 |---------- RESUME_THRESHOLD ---------
  100 |                            \___ resume
      +------------------------------------> time
```

Ví dụ `pauseThreshold=800` và `resumeThreshold=200`. Nếu chỉ dùng một ngưỡng, queue dao động quanh mốc sẽ khiến container liên tục pause/resume (*flapping*), có thể làm latency khó đoán và tăng chi phí vận hành.

Một control service minh họa:

```java
public void adjustFlow(int pendingWork) {
    MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");
    if (container == null) {
        throw new IllegalStateException("Listener not found");
    }

    if (pendingWork >= 800 && !container.isPauseRequested()) {
        container.pause();
    } else if (pendingWork <= 200 && container.isPauseRequested()) {
        container.resume();
    }
}
```

Đây chỉ là **logic ngưỡng đơn giản**. Production nên bổ sung cooldown, giới hạn pause tối đa, metric và alert khi controller không thể đưa container về desired state. Nếu hệ thống có nhiều node, mỗi node có queue depth riêng và các instance có thể cần pause độc lập hoặc theo điều phối tập trung.

### 11.1. Kịch bản integration test cho backpressure

1. Thiết lập một fake capacity gauge có thể điều khiển.
2. Cho container chạy, xác nhận đã assign partition.
3. Đặt gauge `900`, gọi `adjustFlow()`, chờ `isContainerPaused()`.
4. Gửi message `X` sau khi paused; xác nhận chưa vào business handler.
5. Hạ gauge xuống `500`; container **vẫn paused** vì chưa tới resume threshold.
6. Hạ gauge xuống `100`; controller gọi resume, chờ trạng thái resumed.
7. Xác nhận `X` được xử lý và không bị bỏ sót.
8. Dao động gauge quanh `800` và `200`; bảo đảm không phát nhiều control commands ngoài ý muốn.

Test này xác nhận logic control và hành vi Kafka cùng lúc. Unit test riêng có thể mock `MessageListenerContainer` để kiểm tra decision threshold nhanh hơn, nhưng mock không chứng minh consumer thật đã pause/resume.

## 12. Test restart ứng dụng khi đang paused

Pause là trạng thái runtime của listener container, **không phải một thuộc tính của Kafka topic được lưu trên broker**. Khi process chết, container cũ không tồn tại nữa. Một process mới có thể tự start listener theo cấu hình và tiếp tục nhận record, dù process trước đó đã được operator pause.

Vì vậy cần xác định yêu cầu nghiệp vụ:

### Trường hợp A: pause chỉ dùng để giảm tải tạm thời

Sau restart, listener có thể hoạt động lại bình thường. Kiểm thử tập trung vào committed offsets và dữ liệu backlog; không kỳ vọng container mới biết trạng thái pause cũ.

### Trường hợp B: pause là quyết định vận hành phải giữ qua restart

Ví dụ một nguồn dữ liệu được tạm ngừng vì compliance hoặc downstream maintenance. Khi ấy:

1. Lưu **desired state** (`PAUSED`/`RUNNING`) vào database/config store bền vững được phân quyền.
2. Khi ứng dụng start, tải desired state trước khi cho phép nhận message nghiệp vụ.
3. Điều phối lifecycle/assignment để áp dụng pause đúng thời điểm; không để listener tự nhận message rồi mới kiểm tra desired state quá muộn.
4. Kiểm tra trạng thái pause thực tế và phát cảnh báo nếu không đồng bộ.
5. Khi operator resume, lưu state mới và resume trên các instance liên quan.

`autoStartup=false` có thể hữu ích để không khởi động listener trước khi control plane sẵn sàng, nhưng cần thiết kế rõ thao tác start/assign/pause. Chỉ gọi `pause()` sau khi listener đã nhận record không đủ cho một yêu cầu **không được xử lý bất kỳ message nào trong chế độ PAUSED**.

### Kịch bản kiểm thử hai process

```text
Process A:
  consumer active → pause confirmed → gửi X → X chưa xử lý
  kill/stop process A

Process B:
  tải desired state = PAUSED từ DB (nếu policy yêu cầu)
  đảm bảo không phát side effect cho X khi chưa được resume
  operator đổi desired state = RUNNING
  resume/start xử lý → X được commit đúng một lần theo policy
```

Tương tự các bài kiểm thử phục hồi khác, phải đo **output nghiệp vụ**, không chỉ một boolean trạng thái trong control service. Với hard kill, record đã xử lý trước khi commit offset có thể được replay; kiểm thử phải chấp nhận at-least-once và xác minh idempotency.

## 13. Test rebalance và hoạt động nhiều consumer

Test một listener có một partition là bước đầu, chưa chứng minh ứng dụng chịu được scale-out. Với Kafka consumer group, assignment thay đổi khi một thành viên join/leave hoặc broker/coordinator thay đổi trạng thái.

Các test mở rộng nên có:

| Test | Cách gây tình huống | Điều cần quan sát |
| --- | --- | --- |
| Hai listener instances trong một group | Khởi động thêm một consumer | Phân phối partition và desired pause state theo từng instance |
| Pause một instance | Pause container A, giữ B chạy | B tiếp tục partition của mình, A không xử lý thêm sau khi paused |
| Rebalance khi paused | Stop/restart một instance | Partition có thể chuyển owner; không dựa vào pause của owner cũ |
| Container concurrency > 1 | Cấu hình nhiều consumer con | Chờ pause hoàn tất trên toàn container, không nhìn một thread |
| Nhiều partitions | Gửi explicit partition | Không lẫn pause toàn container với pause một partition |
| Mất broker kết nối ngắn | Thử trong Kafka Testcontainers/cluster test | Consumer recover, trạng thái desired/actual được giám sát |

Trong các test này, **message key**, partition, consumer group ID, assignment event và output correlation ID nên được ghi rõ để phân biệt message bị xử lý muộn với message bị một consumer khác trong group xử lý.

## 14. `@EmbeddedKafka` hay Testcontainers?

| Công cụ | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| Mock `MessageListenerContainer` | Kiểm tra decision logic của service điều khiển nhanh | Không có poll, assignment, broker hay offset thật |
| `@EmbeddedKafka` | Test container, listener, topic, pause/resume và producer/consumer trong CI | Không mô phỏng đầy đủ môi trường mạng, auth, topology production |
| Kafka Testcontainers | Chạy Kafka broker trong container thật, gần setup triển khai hơn | Tốn thời gian/tài nguyên, cần Docker |
| Environment/staging cluster | Kiểm tra security, rebalances, retention, metrics và scale thực | Đắt hơn, cần isolation và quản lý dữ liệu test nghiêm ngặt |

Khuyến nghị thực tế là **unit test control policy**, **integration test `@EmbeddedKafka` cho hành vi cơ bản**, sau đó dùng **Testcontainers hoặc staging** cho các tình huống rebalance, broker failure và đồng thời nhiều consumer. Đừng yêu cầu mỗi unit test tự start Kafka broker; cũng đừng coi mock `pause()` là đủ để chứng minh reliability.

Trong một môi trường test có consumer thực, ưu tiên:

- Topic và consumer group riêng theo test suite.
- Chờ assignment trước khi điều khiển pause.
- Đợi producer ack và trạng thái container thực.
- Poll queue/latch có timeout; không dựa vào sleep cố định.
- Có teardown cho listener/consumer/broker.
- Bảo đảm output/side effect và offset phù hợp với ack policy.

## 15. Các lỗi kiểm thử thường gặp

| Hiện tượng | Nguyên nhân phổ biến | Hướng sửa |
| --- | --- | --- |
| `pause()` được gọi nhưng listener vẫn nhận một vài record | Record đã nằm trong poll/in-flight; pause là request | Chờ `isContainerPaused()` rồi mới gửi message cần kiểm thử |
| Test lúc pass lúc fail | Sleep ngắn, chưa chờ assignment hoặc producer ack | Dùng assignment barrier, Awaitility, `Future.get()` |
| Không tìm thấy container | `id` của `@KafkaListener` sai hoặc chưa được đăng ký | Kiểm tra registry và cấu hình `@EnableKafka` |
| Chờ `isContainerPaused()` mãi | Consumer chưa start/assign, listener bị block hoặc phiên bản/cấu hình khác | Xem thread, assignment, listener và timeout |
| Resume xong chưa nhận message | Chưa thật sự resumed, topic/group sai, record đã được xử lý trước đó | Kiểm tra state, offsets, logs và output |
| Resume nhận duplicate | Crash/rebalance trước commit offset hoặc writer không idempotent | Xem ack/transaction, business key và retry |
| Pause một Pod nhưng vẫn có output | Pod/consumer khác còn chạy cùng group | Điều phối toàn bộ nhóm hoặc hiểu đúng partition ownership |
| Partition-level pause không có hiệu lực | Partition không được assign cho container được gọi | Kiểm tra assignment và owner hiện tại |
| `pause()` làm tụt throughput nhưng lag tăng | Đây là hệ quả tự nhiên khi ngừng xử lý | Theo dõi backlog, retention và SLA pause |
| Pause kéo dài khiến data cũ mất | Retention đã xóa log segment trước resume | Đặt pause TTL, alert và recovery/backfill |
| App restart tự consume dù trước đó đã pause | Pause state chỉ nằm trong memory | Persist desired state và quản lý startup nếu nghiệp vụ yêu cầu |
| `stop()` được dùng thay `pause()` | Container rời group/rebalance ngoài dự kiến | Phân biệt lifecycle và flow control |
| Test kiểm tra `isPauseRequested()` rồi kết luận không delivery | Chỉ mới có request, chưa paused thật | Quan sát `isContainerPaused()`/event có hiệu lực |
| Producer send không đợi ack | Có thể message chưa tới broker khi kiểm tra | Chờ future hoàn tất trước assertion |

## 16. Monitoring và vận hành pause/resume

Để giải thích vì sao một consumer đang không xử lý message, không nên chỉ log `pause called`. Một bản ghi điều khiển có cấu trúc nên có:

```text
event=kafka.consumer.pause.requested
containerId=ordersListener
groupId=orders-service
reason=DOWNSTREAM_OVERLOADED
requestedBy=flow-controller
requestedAt=2026-11-16T09:00:00Z

event=kafka.consumer.paused
containerId=ordersListener
topic=orders.events
partitions=[0,1]
observedAt=2026-11-16T09:00:01Z

event=kafka.consumer.resumed
containerId=ordersListener
reason=DOWNSTREAM_RECOVERED
observedAt=2026-11-16T09:04:23Z
```

Những metric có ích:

| Metric | Ý nghĩa |
| --- | --- |
| `consumer_pause_requested` | Desired/requested state của container |
| `consumer_paused` | Actual state đã áp dụng |
| `consumer_pause_duration_seconds` | Tổng thời gian paused |
| `kafka_consumer_lag` | Backlog theo group/partition |
| `records_processed_total` | Số record callback đã xử lý thành công theo hợp đồng ứng dụng |
| `processing_failures_total` | Lỗi listener/downstream sau resume |
| `rebalances_total` | Phát hiện assignment thay đổi |
| `downstream_queue_depth` | Nguồn tín hiệu backpressure |

Các tên metric trên là **gợi ý cho instrumentation của ứng dụng**, không khẳng định tất cả có sẵn mặc định trong Spring Kafka/Micrometer. Tùy hệ thống, metrics từ Kafka client và Spring Kafka có thể có tên/nhãn khác. Tránh đưa message key, order ID hoặc correlation ID riêng từng record vào metric labels vì cardinality cao; dùng log/audit có phân quyền cho các định danh chi tiết.

Một dashboard nên thể hiện **requested pause** và **actual pause**, lý do và thời điểm, consumer lag, số partition đang assign và sức khỏe downstream. Nếu `pauseRequested=true` nhưng actual vẫn `false` lâu bất thường, đó là tín hiệu listener kẹt hoặc poll loop chưa đạt tới điểm pause, cần cảnh báo.

### 16.1. Quyền điều khiển và an toàn

Nếu cung cấp REST/Actuator operation để pause/resume:

1. Phân quyền người/công cụ được phép gọi.
2. Ghi audit `requestedBy`, reason và trạng thái sau thao tác.
3. Không để client tùy ý chọn container ID/group/topic ngoài phạm vi được cấp.
4. Có giới hạn thời gian pause và cảnh báo khi backlog tiến sát retention/SLA.
5. Với nhiều node, triển khai cơ chế điều phối thay vì chỉ tác động một Pod ngẫu nhiên.
6. Không dùng resume để bỏ qua yêu cầu bảo trì hoặc cảnh báo bảo mật chưa được xử lý.

## 17. Checklist trước khi chấp nhận bài test

| Điều cần xác nhận | Lý do |
| --- | --- |
| Consumer đã có assignment | Pause trước assignment không cho bằng chứng cùng ý nghĩa |
| Có barrier `isContainerPaused()` | Tránh gửi message trước khi pause hiệu lực |
| Producer đã được broker ack | Không nhầm send chưa xong với consumer paused |
| Có assertion “không callback khi paused” | Chứng minh không delivery sau mốc pause |
| Có assertion nhận message sau resume | Chứng minh backlog vẫn được xử lý |
| Có timeout rõ ràng, không chờ vô hạn | Test CI không treo khi lỗi |
| Có test in-flight riêng | Không áp đặt hành vi ngắt callback đang chạy |
| Có test offset/side effect khi crash nếu nghiệp vụ cần | Pause không thay thế idempotency |
| Có test rebalance/partition khi chạy nhiều consumer | Pause state cục bộ không phải group-wide lock |
| Có kiểm thử startup desired state nếu cần pause bền vững | Process restart có thể tự consume |
| Có teardown và isolation | Tránh message/offset/test context nhiễu |

## 18. Kết luận

**Test pause và resume trong Spring Kafka** không chỉ là gọi `container.pause()` rồi `container.resume()`. Một bài kiểm thử đáng tin phải phân biệt **pause request** với **pause thực sự có hiệu lực**, chờ consumer được assign partition, gửi message **sau thời điểm đã paused**, xác nhận listener không xử lý trong cửa sổ quan sát và kiểm tra message được xử lý sau resume.

Pause giữ consumer trong lifecycle poll/group thay vì chủ động stop, nhưng **không hủy callback đang chạy, không commit/seek offset, không bảo đảm exactly-once và không tự tồn tại qua process restart**. Những yêu cầu về idempotency, error handling, consumer group rebalance, retention và desired state xuyên node cần có test riêng. Khi kết hợp `@EmbeddedKafka`, barrier đúng, output assertions và kịch bản failure path, ta có một bộ kiểm thử flow control có thể vận hành tin cậy hơn trong production.

## Tài liệu tham khảo

- [Spring for Apache Kafka Reference — Pausing and Resuming Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/pause-resume.html): API pause/resume, trạng thái và thời điểm áp dụng.
- [Spring for Apache Kafka Reference — Pausing and Resuming Partitions](https://docs.spring.io/spring-kafka/reference/kafka/pause-resume-partitions.html): pause/resume theo `TopicPartition`.
- [Spring for Apache Kafka Reference — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html): sự kiện consumer/container, trong đó có paused/resumed.
- [Spring for Apache Kafka Reference — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka`, `ContainerTestUtils` và kiểm thử listener.
- [Spring for Apache Kafka Reference — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): poll, acknowledgment và vòng đời container.
- [Spring for Apache Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): retry, backoff, recoverer và DLT.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): consumer groups, pause/resume, offset, retention và client behavior.
