# Testing inbound adapter theo thời gian trong Spring Integration

Trong hệ thống tích hợp, nhiều nguồn dữ liệu không chủ động gọi ứng dụng: file xuất hiện trong thư mục theo giờ, SFTP nhận tệp từ đối tác vài phút một lần, hoặc bảng cơ sở dữ liệu có các bản ghi đang chờ xử lý. Spring Integration thường dùng **inbound adapter kết hợp poller** để lấy dữ liệu, chuyển thành `Message<?>` rồi gửi vào `MessageChannel`. Flow hoạt động khi thử bằng tay vẫn có thể lỗi khi chạy thật: poller khởi động trước khi nguồn sẵn sàng, file được đọc hai lần, bản ghi DB bị bỏ sót, message đến trước giờ hiệu lực, hoặc gửi trùng sau khi kết nối thất bại.

**Testing inbound adapter theo thời gian** là thiết kế các bài kiểm thử có thể kiểm soát **thời điểm kích hoạt, tần suất poll, vòng đời endpoint, trạng thái nguồn, độ trễ, concurrency và phục hồi lỗi**. Điều quan trọng không chỉ là “cuối cùng đã nhận message” mà còn là **đúng dữ liệu, đúng lúc, không xử lý trùng ngoài hợp đồng và có bằng chứng khi thời gian hoặc kết nối thay đổi**.

Bài học thuộc chương **Testing** của module `SPRING_INTEGRATION_ADAPTERS`. Phạm vi module là kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`, bao gồm File, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Chủ đề này tập trung vào inbound có yếu tố thời gian, đặc biệt **polling adapter**; đồng thời phân biệt những adapter **message-driven** để tránh dùng sai kỹ thuật kiểm thử.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **polling inbound adapter**, **message-driven inbound adapter** và **inbound gateway** theo cơ chế kích hoạt.
2. Giải thích `MessageSource.receive()`, `SourcePollingChannelAdapter`, `PollerMetadata` và `TaskScheduler`.
3. Chọn đúng tầng test: **logic thời gian**, **flow không scheduler**, **poller lifecycle**, **transport integration** và **end-to-end**.
4. Dùng `@SpringIntegrationTest(noAutoStartup = "...")` và `MockIntegrationContext` để chuẩn bị fake `MessageSource` trước khi start endpoint.
5. Kiểm tra **fixedDelay, fixedRate, cron, maxMessagesPerPoll, nguồn rỗng, start/stop, restart và timeout**.
6. Kiểm thử **File/SFTP/JDBC polling**; phân biệt với Kafka/JMS/AMQP listener và HTTP inbound push.
7. Phân biệt **event time, effective time, poll time và processing time**, đo latency đúng ý nghĩa.
8. Thiết kế ca lỗi: duplicate, partial file, unavailable source, transaction rollback, concurrent poller, retry và backpressure.
9. Giảm flaky tests bằng fake clock, fake source hữu hạn, bounded wait, fixture cô lập và cleanup.

## 2. Inbound adapter được kích hoạt theo những cách nào?

Không phải mọi inbound adapter của Spring Integration đều chạy bằng một lịch poll:

| Nhóm | Cơ chế | Ví dụ | Trọng tâm kiểm thử thời gian |
|---|---|---|---|
| **Polling inbound adapter** | Scheduler định kỳ gọi `MessageSource.receive()` | File, SFTP synchronizer/file source, JDBC polling | Chu kỳ, lifecycle, số bản/tick, trạng thái nguồn, duplicate. |
| **Message-driven inbound adapter** | Listener/consumer được nguồn ngoài đánh thức | JMS, AMQP, Kafka message-driven adapter | Listener startup, ack/offset, redelivery, concurrency, reconnect. |
| **Inbound HTTP gateway** | HTTP request từ client kích hoạt flow | HTTP POST endpoint | Request/reply timeout, server lifecycle, deadline. |
| **Polling source từ broker** | Chủ động receive/poll từ một message source chuyên biệt | JMS polling source, Kafka `MessageSource` khi cấu hình | Trigger của Spring Integration cộng semantics broker. |

**Đừng dùng một bộ assertion cho tất cả nhóm.** `maxMessagesPerPoll` có ý nghĩa đối với polling endpoint của Spring Integration nhưng không tương đương `max.poll.records`, partition assignment hoặc offset commit trong một Kafka message-driven consumer.

~~~mermaid
flowchart LR
    CLOCK["TaskScheduler / Trigger<br/>fixedDelay, fixedRate, cron"] --> POLLER["Poller"]
    POLLER --> SOURCE["MessageSource.receive()"]
    EXT["Nguồn bên ngoài<br/>File / SFTP / JDBC"] --> SOURCE
    SOURCE --> CH["MessageChannel"]
    CH --> HANDLER["Filter / Transform / Route"]
    HANDLER --> TARGET["Business handler / outbound adapter"]
    SOURCE -. "Trả null nếu chưa có dữ liệu" .-> POLLER
    HANDLER --> ERR["Error / retry / recovery"]
~~~

Một tick chỉ tạo **cơ hội** để lấy dữ liệu. Khi nguồn rỗng, `receive()` có thể trả `null`; một tick cũng có thể xử lý nhiều message nếu giới hạn `maxMessagesPerPoll` và nguồn cho phép.

## 3. Các thành phần quyết định thời gian

| Thành phần | Vai trò | Câu hỏi test |
|---|---|---|
| `MessageSource<T>` | Lấy một message hoặc trả `null` | Hết dữ liệu có dừng phát? Lỗi được xử lý sao? |
| `SourcePollingChannelAdapter` | Đưa message từ source vào channel theo lịch | Start/stop có đúng? |
| `PollerMetadata` | Trigger, transaction, advice, `maxMessagesPerPoll` | Cấu hình đã gắn đúng endpoint chưa? |
| `TaskScheduler` | Chạy tác vụ theo lịch | Có thread và lifecycle phù hợp? |
| **Trigger** | Tính lần thực thi tiếp theo | Delay/rate/cron có đúng hợp đồng? |
| `MessageChannel` | Gửi message sang flow | Sync/async ảnh hưởng kết quả ra sao? |
| **Metadata/filter store** | Ghi nhận file/record đã được xem hoặc xử lý | State có bền qua restart? |
| **Error handler/advice** | Retry, transaction, recover | Lỗi có bị bỏ qua hoặc lặp vô hạn? |

**Poller chạy thành công không đồng nghĩa business handler đã thành công.** Cần tách điểm quan sát ở source, channel, handler và hệ thống đích.

## 4. Fixed delay, fixed rate và cron

### 4.1. Fixed delay

Với **fixed delay**, khoảng chờ được tính sau lần thực thi trước hoàn thành, theo semantics trigger/framework được cấu hình.

~~~text
Tick 1: 10:00:00.000 → xử lý xong 10:00:00.300
        chờ thêm 1.000 ms
Tick 2: khoảng 10:00:01.300
~~~

Nếu handler chậm, tần suất thực tế sẽ giảm. Không nên assert “mỗi giây chính xác một event”.

### 4.2. Fixed rate

**Fixed rate** xây dựng thời điểm mục tiêu theo lịch đều đặn. Thời điểm bắt đầu thực tế phụ thuộc scheduler, thread pool và thời gian chạy của tác vụ.

~~~text
Scheduled targets: 10:00:00, 10:00:01, 10:00:02, ...
Actual starts:     phụ thuộc tải và chiến lược TaskScheduler
~~~

**Không suy rằng fixed-rate task chắc chắn chạy song song.** Nếu việc chạy chồng lấp là rủi ro, phải kiểm tra semantics của scheduler được dùng và trạng thái truy cập nguồn khi concurrent.

### 4.3. Cron

Cron chọn những **mốc lịch** như “mỗi ngày lúc 02:30”. Các yếu tố cần kiểm tra:

- Time zone rõ ràng hay dựa vào mặc định của JVM?
- Tháng/năm nhuận, ngày cuối tháng và lịch kinh doanh.
- Daylight Saving Time (DST): một giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần.
- Khi ứng dụng ngừng hoạt động, có bỏ lỡ lịch hay phải xử lý backlog?

**Cron không tự bảo đảm catch-up** tất cả lần chạy bị mất khi ứng dụng tắt; việc xử lý backlog phải có trong thiết kế source/checkpoint/recovery.

| Trigger | Cần test | Không nên kết luận |
|---|---|---|
| Fixed delay | Khoảng nghỉ hợp lý sau xử lý, không busy-loop. | Luôn đúng N ms bất kể tải. |
| Fixed rate | Trễ khi handler chạy lâu, cách xử lý overlap. | Mỗi mốc chạy trên một thread mới. |
| Cron | Next execution theo zone, DST và lịch. | Tự bù mọi lần chạy lỡ. |

## 5. Các mốc thời gian của một message

Giả sử đối tác đưa file lên SFTP lúc 10:00:00, poller kiểm tra lúc 10:00:10, đọc được lúc 10:00:12 và handler hoàn tất lúc 10:00:14.

| Mốc | Tên tham khảo | Ý nghĩa |
|---|---|---|
| Dữ liệu sẵn sàng | `availableAt` | File/record đã hoàn chỉnh và được phép đọc. |
| Dữ liệu nghiệp vụ có hiệu lực | `effectiveAt` | Domain cho phép xử lý từ mốc này. |
| Tick poll | `pollAt` | Scheduler kích hoạt lượt nhận. |
| Adapter nhận message | `receivedAt` | Source trả một message. |
| Handler xử lý | `processedAt` | Business handler đã chạy theo nghĩa được định nghĩa. |
| Kết quả cuối được xác minh | `verifiedAt` | Target đã lưu/xử lý đúng, nếu workflow yêu cầu. |

~~~mermaid
flowchart LR
    A["availableAt<br/>Nguồn sẵn sàng"] --> B["pollAt<br/>Scheduler chạy"]
    B --> C["receivedAt<br/>Source trả message"]
    C --> D["processedAt<br/>Handler"]
    D --> E["verifiedAt<br/>Target xác nhận"]
~~~

**Poll latency** có thể đo bằng `receivedAt − availableAt` khi biết được lúc nguồn ready. **End-to-end latency** cần mốc cuối có bằng chứng; không dùng `send() == true` hoặc một ACK trung gian thay `verifiedAt`.

Một event có `effectiveAt` trong tương lai có thể đã được tải sớm nhưng chưa được phép tạo side effect. Vì thế phải phân biệt **nguồn đã nhận** với **nghiệp vụ đã có hiệu lực**.

## 6. Chiến lược test nhiều tầng

| Tầng | Kỹ thuật | Chứng minh được |
|---|---|---|
| **Clock/domain unit test** | `Clock.fixed` hoặc clock giả | Due date, expiry, time window. |
| **Source unit test** | Gọi `MessageSource.receive()` trực tiếp với fixture | Filter, mapping, no-data behavior. |
| **Flow test** | `DirectChannel` → transformer → `QueueChannel` | Payload/header và wiring downstream. |
| **Controlled poller test** | `noAutoStartup` + fake `MessageSource` + start/stop | Source–poller–channel wiring và lifecycle. |
| **Transport integration** | File thật, SFTP server, DB/broker thử nghiệm | I/O, transaction, filter, reconnect, ack. |
| **End-to-end/recovery** | Nguồn → các adapter → kết quả cuối | Đường đi nhiều hệ thống, restart, sai lệch thực tế. |

Nguyên tắc:

- **Mock source** để kiểm tra xử lý downstream mà không gọi nguồn ngoài.
- **Mock outbound handler** để quan sát message cuối flow mà không tạo side effect.
- **Không mock file source** khi mục tiêu là filter file, mtime hoặc metadata store thật.
- **Không mock database** khi cần kiểm chứng locking/isolation.
- **Không mock broker** khi cần kiểm chứng ack, offset, redelivery thực tế.

## 7. Dependency cần thiết

Ví dụ dự án dùng Spring Boot dependency management/BOM tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.integration:spring-integration-core")
    testImplementation("org.springframework.integration:spring-integration-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Nếu không dùng BOM, cần phiên bản tương thích của Spring Integration, Spring Framework, JUnit và Mockito. Khi test adapter File/SFTP/JDBC/Kafka/JMS/AMQP/HTTP thật, cần thêm **module adapter tương ứng** và môi trường test giao thức; `spring-integration-test` không tự cung cấp broker hoặc server SFTP.

Ví dụ tiếp theo dùng Java DSL thông dụng. Một số overload DSL/bean endpoint có thể khác theo phiên bản; khi triển khai hãy kiểm tra API của version trong dự án.

## 8. Ví dụ: inbound polling flow có thể điều khiển

Mục tiêu: source cung cấp chuỗi, transformer xóa khoảng trắng rồi gửi vào `QueueChannel`. Test phải **thay source trước khi start poller** để không phụ thuộc mạng hoặc dữ liệu ngoài.

### 8.1. Cấu hình flow

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Configuration
@EnableIntegration
class TimedInboundTestConfig {

    @Bean
    QueueChannel processedEvents() {
        return new QueueChannel();
    }

    @Bean
    MessageSource<String> idleSource() {
        return () -> null; // Không truy cập nguồn ngoài ở test context.
    }

    @Bean
    IntegrationFlow pollingFlow(MessageSource<String> idleSource,
                                QueueChannel processedEvents) {
        return IntegrationFlow
                .from(idleSource, endpoint -> endpoint
                        .id("timedInboundEndpoint")
                        .poller(Pollers
                                .fixedDelay(Duration.ofMillis(200))
                                .maxMessagesPerPoll(1)))
                .transform(String.class, String::trim)
                .channel(processedEvents)
                .get();
    }
}
~~~

Trong ví dụ:

- `idleSource`: bean `MessageSource<String>` mặc định trả `null`.
- `timedInboundEndpoint`: **endpoint ID** dùng thay source và điều khiển lifecycle.
- `processedEvents`: output `QueueChannel` để test chờ message với timeout.
- `maxMessagesPerPoll(1)`: giới hạn **mỗi lần poll**, không phải giới hạn suốt vòng đời endpoint.

### 8.2. Fake source phát hữu hạn

~~~java
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.Message;

final class FiniteSource<T> implements MessageSource<T> {

    private final Queue<Message<T>> pending =
            new ConcurrentLinkedQueue<>();
    private final AtomicInteger receiveCalls = new AtomicInteger();

    void enqueue(Message<T> message) {
        pending.add(message);
    }

    int receiveCount() {
        return receiveCalls.get();
    }

    @Override
    public Message<T> receive() {
        receiveCalls.incrementAndGet();
        return pending.poll(); // null khi hết dữ liệu
    }
}
~~~

Hàng đợi thread-safe phù hợp khi scheduler thread gọi `receive()` còn JUnit thread chuẩn bị hoặc quan sát fixture. Nếu muốn test race có chủ đích, dùng barrier/latch thay vì chia sẻ một `ArrayList` chưa đồng bộ.

### 8.3. JUnit test với start/stop chủ động

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.ApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TimedInboundTestConfig.class)
@SpringIntegrationTest(noAutoStartup = "timedInboundEndpoint")
class TimedInboundFlowTest {

    @Autowired
    MockIntegrationContext mockContext;

    @Autowired
    ApplicationContext context;

    @Autowired
    @Qualifier("processedEvents")
    QueueChannel output;

    private SmartLifecycle endpoint;

    @AfterEach
    void cleanup() {
        if (endpoint != null) {
            endpoint.stop();
        }
        mockContext.resetBeans();
        while (output.receive(0) != null) {
            // Dọn message còn lại trong QueueChannel.
        }
    }

    @Test
    void shouldPollMessageAfterExplicitStart() {
        FiniteSource<String> source = new FiniteSource<>();
        source.enqueue(MessageBuilder.withPayload("  invoice-2048  ")
                .setHeader("traceId", "test-2048")
                .build());

        mockContext.substituteMessageSourceFor(
                "timedInboundEndpoint", source);

        endpoint = context.getBean(
                "timedInboundEndpoint", SmartLifecycle.class);
        assertFalse(endpoint.isRunning());
        endpoint.start();

        Message<?> actual = output.receive(2_000);
        assertNotNull(actual, "Không nhận message trước timeout");
        assertEquals("invoice-2048", actual.getPayload());
        assertEquals("test-2048",
                actual.getHeaders().get("traceId"));
        assertTrue(source.receiveCount() >= 1);
    }
}
~~~

Test này chứng minh message đi từ **fake source** qua **polling endpoint** vào channel rồi transformer, sau khi start chủ động. Nó **không** chứng minh SFTP/DB thật được đọc, không chứng minh fixed delay luôn chính xác từng mili-giây và không kiểm chứng side effect của outbound adapter.

**Lưu ý endpoint bean:** cách Java DSL đăng ký tên endpoint/bean có thể khác theo phiên bản. Đoạn tra bean `timedInboundEndpoint` giả định ID được expose tương ứng; khi triển khai cần xác minh bean thực tế trong Spring context, không suy tên từ tên channel.

## 9. Kiểm thử source rỗng và không chạy trước start

### 9.1. Không poll trước khi setup

~~~java
@SpringIntegrationTest(noAutoStartup = "timedInboundEndpoint")
~~~

Ý nghĩa: endpoint tương ứng không tự start lúc context khởi tạo. Trình tự nên là:

1. Tạo fixture và fake `MessageSource`.
2. Đặt nguồn vào `MockIntegrationContext` bằng đúng endpoint ID.
3. Xác nhận endpoint chưa chạy.
4. Chủ động `start()`.
5. Chờ output hoặc error bằng điểm quan sát có timeout.

Nếu muốn chứng minh `receive()` **không bị gọi trước start**, dùng fake đếm invocation và quan sát giai đoạn setup; không chỉ gọi `QueueChannel.receive(0)` một lần.

### 9.2. Source rỗng là trạng thái bình thường

~~~java
MessageSource<String> emptySource = () -> null;
mockContext.substituteMessageSourceFor(
        "timedInboundEndpoint", emptySource);

// Sau khi start và bảo đảm channel đã rỗng:
Message<?> none = output.receive(400);
assertNull(none);
~~~

Assertion trên chỉ chứng minh **không có output trong 400 ms quan sát**. Để biết scheduler thực sự đã poll, dùng fake đếm `receive()` hoặc latch; nếu không, không nhận output có thể đơn giản là poller chưa chạy.

### 9.3. Fake phát vô hạn có thể tạo duplicate giả

~~~java
MessageSource<String> alwaysProduces = () ->
        MessageBuilder.withPayload("same-message").build();
~~~

Source này trả message ở **mỗi lần gọi**. Vì thế ngay cả `maxMessagesPerPoll(1)` vẫn có thể tạo một message ở **mỗi tick**. Với test chỉ muốn phát một message, dùng `FiniteSource` hoặc `AtomicReference<Message<T>>` để trả `null` sau lần đầu.

## 10. maxMessagesPerPoll là giới hạn theo lượt poll

Giả sử có ba message trong source:

~~~text
Source: [M1, M2, M3]
maxMessagesPerPoll = 1
Tick 1 → M1
Tick 2 → M2
Tick 3 → M3
Tick 4 → null
~~~

Mô hình trên mô tả trường hợp đơn giản; thực tế transaction, error handler và concurrency có thể ảnh hưởng kết quả. **Không nhầm `maxMessagesPerPoll=1` với “chỉ xử lý một message cho cả đời endpoint”**.

Một test mạnh nên kiểm tra:

- Số message mỗi tick không vượt cấu hình trong điều kiện đã kiểm soát.
- Các tick sau xử lý backlog còn lại.
- `receive() == null` dừng vòng lấy message trong tick thích hợp.
- Khi handler throw, message được retry/rollback theo chính sách.
- Với nhiều instance, giới hạn là của từng poller; không tự suy thành giới hạn toàn cụm.

Nếu chỉ thấy M1/M2 cách nhau 200 ms, chưa chắc đã chứng minh đúng **một message mỗi tick**, vì chưa biết tick boundary. Khi cần bảo đảm chính xác, hãy instrument scheduler/poller hoặc dùng scheduler được điều khiển.

## 11. Test business time bằng Clock, không ngủ chờ

Business rule “chỉ xử lý khi `effectiveAt` đến” nên tách thành Java class nhận `Clock`:

~~~java
import java.time.Clock;
import java.time.Instant;

final class DueTimePolicy {
    private final Clock clock;

    DueTimePolicy(Clock clock) {
        this.clock = clock;
    }

    boolean isDue(Instant effectiveAt) {
        return !clock.instant().isBefore(effectiveAt);
    }
}
~~~

Test ba ranh giới:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class DueTimePolicyTest {
    private final Instant deadline =
            Instant.parse("2026-11-24T00:00:00Z");

    @Test
    void rejectsBeforeDeadline() {
        Clock before = Clock.fixed(
                deadline.minusNanos(1), ZoneOffset.UTC);
        assertFalse(new DueTimePolicy(before).isDue(deadline));
    }

    @Test
    void acceptsExactlyAtDeadline() {
        Clock at = Clock.fixed(deadline, ZoneOffset.UTC);
        assertTrue(new DueTimePolicy(at).isDue(deadline));
    }

    @Test
    void acceptsAfterDeadline() {
        Clock after = Clock.fixed(
                deadline.plusSeconds(1), ZoneOffset.UTC);
        assertTrue(new DueTimePolicy(after).isDue(deadline));
    }
}
~~~

**`Clock.fixed` không tự thay clock của `TaskScheduler`**. Unit test này chứng minh logic nghiệp vụ, không chứng minh tick thực của cron/fixedDelay.

Các ca biên khác cần thử:

| Trường hợp | Câu hỏi |
|---|---|
| `now < effectiveAt` | Có xử lý quá sớm không? |
| `now == effectiveAt` | Có coi thời điểm đúng biên là hợp lệ? |
| Timestamp khác offset nhưng cùng instant | Có so sánh theo thời điểm tuyệt đối? |
| Event thay lịch từ version cũ sang mới | Có hủy lịch cũ để không xử lý hai lần? |
| Đồng hồ nguồn và máy xử lý lệch | Chính sách tolerance và cảnh báo là gì? |

## 12. Test nhiều tick bằng CountDownLatch

Để chứng minh poller **tiếp tục thức dậy** dù source rỗng, dùng fake đếm và latch thay vì ngủ ấn định:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger pollCount = new AtomicInteger();
CountDownLatch twoPolls = new CountDownLatch(2);

MessageSource<String> countingEmptySource = () -> {
    pollCount.incrementAndGet();
    twoPolls.countDown();
    return null;
};

mockContext.substituteMessageSourceFor(
        "timedInboundEndpoint", countingEmptySource);

endpoint.start();
assertTrue(twoPolls.await(3, TimeUnit.SECONDS));
assertTrue(pollCount.get() >= 2);
~~~

Test này chứng minh **ít nhất hai lần gọi source**, không chứng minh thời gian giữa hai tick chính xác 200 ms. Nếu kiểm tra latency thực, có thể ghi thời gian monotonic bằng `System.nanoTime()` trong cùng process, kèm tolerance hợp lý và điều kiện đã điều khiển.

### Vì sao assertion timing rất dễ flaky?

- JVM warmup, GC, CPU tranh chấp trên CI.
- Thread pool scheduler có task khác.
- Handler và I/O mất thời gian biến động.
- OS scheduler không cam kết chính xác từng mili-giây.
- Thời điểm test bắt đầu đếm khác thời điểm endpoint thật sự chạy.

Nên test **semantics và biên độ dung sai có ý nghĩa**, không `assertEquals(200, elapsedMs)` theo wall clock.

## 13. Cron, timezone và DST

Đối với lịch “02:30 mỗi ngày theo Europe/Berlin”, có ngày giờ địa phương **không tồn tại** khi bắt đầu DST, hoặc **xuất hiện hai lần** khi kết thúc DST. Test nên:

1. Parse biểu thức cron theo cú pháp Spring/phiên bản sử dụng.
2. Chỉ định zone rõ ràng.
3. Tính next execution quanh ngày cuối tháng/năm và ngày chuyển DST.
4. Xác nhận chính sách bỏ qua/chạy lại mốc bị mất.
5. Kiểm tra khả năng tạo backlog khi ứng dụng ngừng hoạt động lâu.

Không nên tự đoán kết quả cho mọi version của `CronTrigger`; kiểm tra logic trigger/calendar theo đúng phiên bản và hợp đồng đã thiết kế. UTC phù hợp lưu một **instant tuyệt đối**, nhưng lịch đối tác vẫn có thể cần theo **giờ địa phương**.

## 14. Kiểm thử stop, restart và in-flight work

~~~mermaid
stateDiagram-v2
    [*] --> STOPPED
    STOPPED --> RUNNING: start
    RUNNING --> STOPPING: stop
    STOPPING --> STOPPED: in-flight work settled
    STOPPED --> RUNNING: restart
~~~

| Kịch bản | Điều cần xác nhận |
|---|---|
| Auto-start bị tắt | Không poll trước setup. |
| Explicit start | Source bắt đầu được gọi. |
| Stop khi idle | Không có poll mới sau khi stop ổn định. |
| Stop giữa handler đang xử lý | In-flight work theo đúng lifecycle/transaction contract. |
| Restart có backlog | Lấy lại dữ liệu đang chờ theo metadata/checkpoint. |
| Restart sau lỗi | Connection/metadata được phục hồi hoặc báo lỗi rõ. |
| Nhiều instance cùng chạy | Không side effect trùng ngoài chính sách. |

**`stop()` không nhất thiết hủy tức thời mọi task đang chạy**. Một handler đang xử lý hoặc request I/O đang chờ có thể cần hoàn tất/timeout theo cấu hình. Dùng latch/barrier để tái hiện và quan sát kịch bản stop khi in-flight thay vì gọi stop rồi suy đoán không còn hoạt động.

## 15. Nguyên tắc teardown và cô lập test

Sau khi test, cần:

1. **Stop endpoint** đã start; đợi in-flight work theo contract nếu cần.
2. Gọi `MockIntegrationContext.resetBeans()` để khôi phục source/handler đã thay.
3. Drain output `QueueChannel` hoặc dùng fixture mới.
4. Xóa dữ liệu test trong filesystem, SFTP server, DB hoặc broker nếu có.
5. Đóng connection, scheduler/executor do test sở hữu.
6. Không dùng chung static mock, queue hoặc source mutable giữa test chạy song song.

`resetBeans()` **không tự xóa file, database row, Kafka topic hoặc JMS queue**, và cũng không thay thế việc chờ task async đã kết thúc. Context caching có thể khiến endpoint/mock của test trước còn ảnh hưởng test sau nếu cleanup không đúng.

## 16. File inbound: test thời điểm file đã sẵn sàng

Đối với File polling, **file tồn tại** chưa chắc đồng nghĩa **file đã ghi hoàn chỉnh**.

### 16.1. Những rủi ro cần có test

- Producer đang ghi file nhưng poller đã lấy file.
- File được đổi tên hoặc chuyển tới thư mục trong lúc poller scan.
- File tên giống bản trước nhưng nội dung được cập nhật.
- `AcceptOnce` hoặc metadata filter đánh dấu file là đã đọc trước khi xử lý nghiệp vụ thành công.
- Hai poller cùng quét một thư mục hoặc shared filesystem.
- File modification time có độ phân giải thấp hoặc khác clock nguồn.

### 16.2. Ready-marker hoặc atomic rename

~~~text
10:00:00 producer bắt đầu ghi orders-77.tmp
10:00:05 producer ghi xong, rename → orders-77.ready
10:00:06 poller quét *.ready
10:00:07 flow phát Message<File> cho orders-77.ready
~~~

Một chính sách thường gặp: producer chỉ đổi tên file hoặc tạo marker sau khi ghi xong; inbound adapter chỉ chấp nhận file `*.ready`. Test phải xác minh **file .tmp không được đưa vào flow** và file ready được xử lý đủ bytes. Tính nguyên tử của rename phụ thuộc filesystem/protocol; nếu là network share hoặc remote FS cần test trên môi trường phù hợp.

### 16.3. @TempDir tạo fixture

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class FileReadinessFixtureTest {

    @TempDir
    Path root;

    @Test
    void preparesFileWithReadyMarker() throws Exception {
        Path temp = root.resolve("orders-77.tmp");
        Files.writeString(temp, "id,total\n77,900\n");

        // File inbound adapter test chỉ chọn *.ready.
        // Poll tại đây: output vẫn rỗng.

        Path ready = root.resolve("orders-77.ready");
        Files.move(temp, ready);

        assertTrue(Files.exists(ready));
        assertEquals("id,total\n77,900\n",
                Files.readString(ready));

        // Poll và assert một Message<File> do adapter thực tạo.
    }
}
~~~

Ví dụ trên chỉ cho thấy **cách chuẩn bị fixture**, không tự chứng minh Spring Integration đã nhận file. Muốn kiểm tra File inbound thực, cần cấu hình `FileReadingMessageSource`, filter, directory, poller và output channel rồi assertion chính message được phát.

### 16.4. Filter/metadata và restart

| Loại state | Test cần có |
|---|---|
| In-memory AcceptOnce | Khi context còn chạy không đọc lại file theo rule. |
| Persistent metadata store | Sau khởi động lại có giữ được checkpoint không? |
| File sửa sau lần đọc | Đọc lại hay bỏ qua theo hợp đồng? |
| Lỗi sau khi file được đánh dấu | Có retry/requeue nếu business side effect chưa hoàn tất không? |
| Hai process cùng source | Dùng claim/locking theo thiết kế, không chỉ test trong một JVM. |

**Test chỉ stop/start endpoint trong cùng JVM không chứng minh metadata bền qua process restart** nếu store ở RAM. Với yêu cầu persistence, thử tạo lại context hoặc tiến trình trên metadata store đúng loại production.

## 17. SFTP inbound: thời điểm upload, đồng bộ và session

SFTP inbound có thể gồm bước **đồng bộ remote file về local** và bước **phát local file thành message**. Tùy adapter/mode, filter và metadata nằm ở hai vị trí khác nhau. Khi test phải chỉ rõ ranh giới nào thực sự được kiểm tra.

| Tình huống | Kết quả cần xác nhận |
|---|---|
| Remote file đang upload | Chưa phát file chưa hoàn chỉnh theo quy ước ready-marker/rename. |
| Không có file mới | Tick trả rỗng, không báo lỗi giả. |
| File xuất hiện ngay sau tick | Được lấy ở tick sau, trong phạm vi SLO. |
| SFTP không khả dụng | Error/retry có giới hạn, backlog không mất. |
| Session timeout | Reconnect và trạng thái metadata phù hợp. |
| Host key thay đổi bất ngờ | Bị từ chối theo trust policy, không tắt xác minh để test pass. |
| Duplicate filename/mtime | Filter và chính sách phát lại được kiểm tra. |
| Restart giữa download | File partial và metadata được xử lý an toàn. |

`MockIntegrationContext.substituteMessageSourceFor(...)` phù hợp để test **logic sau khi file đã được nhận**, nhưng không kiểm chứng authentication, host key, remote directory, transfer hoặc reconnect. Cần **SFTP server thử nghiệm isolated** để xác nhận chức năng giao thức và session lifecycle. Không kết nối SFTP production.

### 17.1. Tách hai test

**Flow isolation:** fake `MessageSource<File>` phát file test từ `@TempDir` vào flow; downstream validator/transformer xử lý; outbound mock nhận payload/header mong muốn.

**SFTP transport integration:** upload file lên server test, start inbound adapter thật, đợi output, kiểm tra local bytes/remote metadata, ngắt kết nối và thử recovery.

Đặt tên test đúng kết quả: `shouldBuildOrderEventFromSftpLikeMessage` khác `shouldDownloadReadyFileFromSftpServer`.

## 18. JDBC inbound: record đến hạn và transaction

JDBC polling kết hợp **thời gian, trạng thái xử lý, transaction và concurrency**. Giả sử bảng:

~~~sql
CREATE TABLE inbox_events (
    id            VARCHAR(64) PRIMARY KEY,
    event_type    VARCHAR(80) NOT NULL,
    payload_json  TEXT NOT NULL,
    due_at        TIMESTAMP NOT NULL,
    status        VARCHAR(20) NOT NULL,
    claimed_by    VARCHAR(80),
    created_at    TIMESTAMP NOT NULL
);
~~~

Điều kiện chọn record đến hạn có thể như sau:

~~~sql
SELECT id, event_type, payload_json, due_at
FROM inbox_events
WHERE status = 'READY'
  AND due_at <= :now
ORDER BY due_at, id;
~~~

Truy vấn trên **chỉ minh họa điều kiện thời gian**, chưa chống race khi hai instance cùng poll. Production có thể cần cơ chế claim/lock/lease hoặc update trạng thái nguyên tử theo SQL dialect và transaction isolation.

### 18.1. Test matrix JDBC

| Case | Điều kiện | Kỳ vọng |
|---|---|---|
| Chưa đến hạn | `dueAt > now` | Không phát trước hiệu lực. |
| Đúng hạn | `dueAt == now` | Được eligible nếu policy dùng biên inclusive. |
| Quá hạn | `dueAt < now` | Được xử lý; đo delay. |
| Đã processed | `status = COMPLETED` | Không chọn lại ngoài chính sách. |
| Handler throw | Chưa commit thành công | Rollback/retry, không mất bản ghi. |
| Hai instance cùng poll | Cùng bản ghi READY | Không side effect trùng trái hợp đồng. |
| DB mất kết nối | Nhiều tick lỗi | Cảnh báo, backoff, recovery. |
| Crash sau claim | Owner claim không còn | Lease/claim được recover theo chính sách. |
| Data được thêm giữa batch | Insert đồng thời | Không mất do pagination/watermark sai. |

### 18.2. H2 không thay thế hoàn toàn DB production

H2 hoặc fake repository phù hợp cho test logic nhanh, nhưng **locking, transaction isolation, timestamp precision, `SKIP LOCKED`, affected rows và SQL dialect** phụ thuộc engine. Để kiểm thử claim/concurrency thực, dùng DB cùng loại với production qua Testcontainers hoặc môi trường isolated.

Transaction DB cũng **không tự nguyên tử với HTTP/Kafka/SFTP**. Nếu flow cập nhật row rồi gửi message ra ngoài, cần test crash giữa hai side effect và cơ chế outbox/inbox hoặc idempotency đã thiết kế.

## 19. JMS, AMQP, Kafka và HTTP: không áp chung một poller

### JMS và AMQP message-driven

Inbound listener thường được broker gọi khi có message, thay vì một `SourcePollingChannelAdapter` có `PollerMetadata`. Bài test thời gian cần xem:

- Listener start/stop đúng lifecycle?
- Message gửi trước khi listener start có còn được broker lưu?
- Lỗi xử lý dẫn đến ack, reject, nack, rollback hoặc redelivery nào?
- Consumer concurrency, prefetch và ordering theo provider?
- Khi broker mất kết nối, listener tự recover bao lâu và có cảnh báo?

Nếu thực sự cấu hình **polling message source** cho JMS/AMQP, bổ sung test `MessageSource.receive()` và trigger tương ứng. Không suy các semantics ack của JMS/AMQP giống Kafka.

### Kafka inbound

Kafka **message-driven adapter** dùng listener/consumer container; Kafka consumer có phương thức `poll()` nội bộ nhưng đó **không phải cùng loại scheduler poller** của Spring Integration `MessageSource`.

Kiểm thử:

- Topic, partition, key, serializer và schema.
- Pause/resume/start/stop consumer.
- Offset commit theo mô hình container.
- Rebalance khi thay số consumer.
- Retry/DLT/idempotent side effect.
- Độ trễ giữa broker append, consume và business processing.

Nếu dùng `KafkaMessageSource` làm polling source, test trigger của Spring Integration cộng thêm hành vi offset/consumer của nguồn đó.

### HTTP inbound gateway

HTTP inbound thường do **request từ client** kích hoạt, không cần cron/fixedDelay. Test thời gian nên xem:

- Server ready trước request.
- Request/reply timeout và status theo contract.
- Correlation khi nhiều request đồng thời.
- Deadline/effectiveAt từ dữ liệu đáng tin cậy, không chỉ header client tự khai.
- Backpressure/429/overload khi lượng request tăng.

Nếu client có scheduler gửi HTTP request định kỳ, hãy kiểm thử scheduler **phía client** và HTTP gateway **phía server** như hai trách nhiệm độc lập.

## 20. Backpressure khi downstream chậm hơn inbound

Poller mỗi 100 ms nhưng handler cần 500 ms có thể gây backlog hoặc làm chậm tick tiếp theo, tùy channel:

| Thành phần | Hiệu ứng có thể xảy ra | Cần test |
|---|---|---|
| `DirectChannel` | Handler đồng bộ giữ poller cho đến khi xong | Thời gian handler, không mất message. |
| `ExecutorChannel` | Dispatch async, tăng in-flight tasks | Queue capacity, rejection, shutdown, lỗi thread khác. |
| `QueueChannel` | Message ở hàng chờ đến khi consumer lấy | Capacity, backlog, timeout, cleanup. |
| Broker outbound | Send chậm/timeout/buffer đầy | Retry, ack và trạng thái pending. |

Trước khi test overload, phải chốt **kết quả đúng**:

1. Poller có giới hạn số message/tick?
2. Có cần tạm dừng hoặc làm chậm nguồn?
3. Buffer tối đa bao nhiêu?
4. Khi hàng đợi đầy thì block, reject, retry hay DLQ?
5. Làm sao xử lý backlog mà không nhân bản side effect?
6. Có điểm quan sát queue length và tuổi event chưa xử lý không?

Test bằng handler có latch để cố ý chặn, sau đó quan sát backlog/recovery. Không lấy kết quả throughput của một máy CI làm SLO production.

## 21. Retry và idempotency khi lỗi giữa các tick

~~~text
T0: MessageSource lấy event E
T1: Handler ghi database thành công
T2: Ứng dụng crash hoặc mất ACK
T3: Lần poll/restart tiếp theo thấy lại E
~~~

Nếu không có idempotency, event E có thể tạo side effect trùng. **Message ID do Spring sinh không nhất thiết là business key ổn định qua transform/replay**, nên nên dùng khóa nghiệp vụ do producer/contract xác định.

~~~json
{
  "eventId": "evt-2026-00128",
  "eventType": "INVOICE_READY",
  "schemaVersion": 2,
  "availableAt": "2026-11-23T10:00:00Z",
  "effectiveAt": "2026-11-23T10:05:00Z",
  "invoiceId": "INV-128",
  "tenantId": "VN"
}
~~~

### Các ca lỗi phải thử

| Lỗi | Bằng chứng cần có |
|---|---|
| Source throw ở tick đầu | Lỗi được quan sát; tick sau có thể recover. |
| Handler throw trước side effect | Event chưa bị đánh dấu hoàn tất giả. |
| DB commit rồi mất ACK | Redelivery không tạo invoice trùng. |
| SFTP download một phần | Không coi file chưa hoàn chỉnh là ready. |
| JMS/Kafka redelivery sau restart | Business event ID được xử lý theo policy dedupe. |
| Error handler cũng thất bại | Có alert/quarantine, không làm mất dấu message. |
| Tick mới đến khi tick cũ chưa xong | Không overlap ngoài hợp đồng. |

Không mặc định **exactly-once end-to-end** chỉ vì broker hỗ trợ giao dịch trong một phạm vi; DB, HTTP và file transfer có các transaction boundary khác nhau.

## 22. Error channel và exception của poller

Inbound poller thường chạy trên scheduler thread, vì vậy lỗi có thể không truyền về JUnit test method:

~~~java
MessageSource<String> failingSource = () -> {
    throw new IllegalStateException("source unavailable");
};

mockContext.substituteMessageSourceFor(
        "timedInboundEndpoint", failingSource);
~~~

Để test:

1. Xác định endpoint có error handler, error channel hoặc retry advice nào.
2. Gắn điểm quan sát (ví dụ error `QueueChannel` nếu flow phù hợp).
3. Start endpoint và đợi **error event** bằng timeout hữu hạn.
4. Assert error/cause và correlation.
5. Kiểm tra số attempt/recovery theo cấu hình.
6. Stop endpoint và cleanup.

**Không đặt `assertThrows` quanh `endpoint.start()` rồi mong bắt exception của một tick chạy sau đó.** Ngoài ra không phải tất cả lỗi đều tự động đi vào một channel tên `errorChannel`; điều này phụ thuộc điểm phát lỗi và cách Spring Integration endpoint được cấu hình.

### Không đánh đồng các mức hoàn tất

- Poller gọi source thành công: **đã thử đọc nguồn**.
- Source trả message: **đã nhận message**.
- Handler xử lý: **đã qua một ranh giới xử lý**.
- Outbound trả ACK: **đã có phản hồi kỹ thuật**.
- Target readback xác nhận: **đã có bằng chứng trạng thái cuối**, nếu workflow cần.

Một test chỉ thấy `send() == true` không đủ chứng minh kết quả cuối của hệ thống tích hợp nhiều bước.

## 23. Hai poller đồng thời và race condition

Một hệ thống có thể chạy nhiều instance để tăng khả năng sẵn sàng. Với File/SFTP/JDBC phải trả lời: **một bản ghi/file có thể được xử lý nhiều lần không?**

Kịch bản kiểm thử:

1. Tạo một record `READY` trong DB thử nghiệm.
2. Khởi tạo hai poller cùng trỏ vào một nguồn chia sẻ.
3. Dùng barrier/latch để cả hai gần đồng thời claim record.
4. Giữ handler instance đầu trước commit.
5. Kiểm tra instance hai có claim cùng record không.
6. Thả barrier, kiểm tra side effect cuối.
7. Simulate crash instance đầu, kiểm tra recovery và ownership lease.

**Hai thread đọc một fake `ConcurrentLinkedQueue` không chứng minh JDBC row lock hoặc distributed metadata store an toàn.** Với yêu cầu distributed concurrency phải dùng transport/store phù hợp.

Ngữ nghĩa cần ghi trước khi test:

- **At-least-once delivery**: có thể giao lại message; side effect phải idempotent.
- **Single claim ownership**: cần lock/lease hoặc state transition nguyên tử theo thiết kế.
- **Ordering guarantee**: thường theo key, partition, batch hoặc nguồn cụ thể; không suy thứ tự toàn cục.

## 24. Dữ liệu xuất hiện giữa các tick

~~~text
10:00:00.000 — Tick 1 bắt đầu
10:00:00.050 — File mới xuất hiện
10:00:00.100 — Tick 1 kết thúc
10:00:01.000 — Tick 2 bắt đầu
~~~

Cần xác minh nếu Tick 1 chưa thấy file thì Tick 2 vẫn phát hiện được. Đây là vấn đề **watermark, file filter, query snapshot hoặc pagination**, không chỉ là thời gian scheduler.

### JDBC pagination

`LIMIT/OFFSET` trên bảng đang insert/delete có thể gây skip hoặc duplicate. Test cần có dữ liệu thay đổi đồng thời và đánh giá keyset pagination, claim hoặc watermark nếu được thiết kế.

### File/SFTP mtime

Không dựa duy nhất vào mtime để khẳng định file là mới: độ phân giải timestamp và clock nguồn khác nhau. Test tên file trùng, mtime bằng nhau, rename và update content theo contract.

## 25. Các chỉ số thời gian đáng đo

| Metric | Định nghĩa | Giới hạn |
|---|---|---|
| **Poll attempts** | Lượt source được gọi trong cửa sổ | Không phải số message nghiệp vụ. |
| **Empty poll ratio** | `receive() == null` / tổng receive attempts | Có thể cao bình thường nếu ít dữ liệu. |
| **Source-to-dispatch latency** | `dispatchedAt − availableAt` | Cần biết nguồn ready chính xác khi nào. |
| **Deadline lateness** | `processedAt − effectiveAt` với case xử lý sau hạn | Xử lý sớm cần chỉ số riêng. |
| **Oldest pending age** | Tuổi file/event chưa hoàn tất | Dễ thấy backlog hơn throughput thuần. |
| **Retry aging** | Tuổi và số attempt chưa recover | Không đếm retry thành business event mới. |
| **Duplicate side-effect count** | Side effect vượt expectation theo event ID | Cần business key và evidence. |
| **Recovery duration** | Từ khi nguồn phục hồi đến khi backlog được xử lý đủ | Không đồng nhất với thời gian reconnect. |

Nên xem **P50/P95/P99 latency của các việc đã xác nhận** cùng với **pending count, overdue count và oldest pending**. Chỉ báo latency những tác vụ thành công sẽ che các trường hợp bị kẹt lâu. Đừng biến performance trên máy CI thành SLA production khi chưa có baseline và đánh giá rủi ro.

## 26. Ma trận kiểm thử tổng hợp

| # | Kịch bản | Tầng kiểm thử | Kết quả mong đợi |
|---:|---|---|---|
| 1 | Endpoint `noAutoStartup` | Controlled flow | Không poll trước start. |
| 2 | Source rỗng | Controlled flow | Receive được gọi, không phát message. |
| 3 | Source một message | Controlled flow | Payload/header đúng, không phát vô hạn. |
| 4 | Ba message, `maxMessagesPerPoll=1` | Poller/scheduler | Giới hạn theo tick, backlog qua các tick. |
| 5 | Fixed delay với handler chậm | Scheduler | Delay theo semantics, tolerance phù hợp. |
| 6 | Fixed rate khi quá tải | Scheduler | Không overlap ngoài chính sách. |
| 7 | Cron qua cuối tháng | Trigger unit test | Next execution hợp lệ. |
| 8 | Cron qua DST | Trigger unit test | Mốc theo zone và chính sách. |
| 9 | `effectiveAt` tương lai | Clock unit test | Không xử lý sớm. |
| 10 | Đúng biên `effectiveAt` | Clock unit test | Kết quả theo quy tắc inclusive/exclusive. |
| 11 | Event đổi lịch/version | Domain + flow | Lịch cũ không gây side effect. |
| 12 | File `.tmp` đang ghi | File integration | Không phát trước ready. |
| 13 | File `.ready` | File integration | Được phát đúng nội dung. |
| 14 | File sửa sau poll | File integration | Filter/metadata theo contract. |
| 15 | SFTP mất kết nối | SFTP integration | Alert, reconnect, không mất backlog. |
| 16 | SFTP partial transfer | SFTP integration | Không xử lý file chưa hoàn tất. |
| 17 | JDBC row chưa đến hạn | DB integration | Không claim sớm. |
| 18 | Hai poller claim cùng row | DB concurrency | Không side effect trùng ngoài policy. |
| 19 | JDBC rollback | DB integration | Record recoverable, không mất dữ liệu. |
| 20 | Source throw exception | Controlled flow | Error path/recovery được quan sát. |
| 21 | Handler fail rồi success | Flow + transport | Retry/attempt/idempotency đúng. |
| 22 | Stop giữa in-flight | Lifecycle | Graceful semantics như hợp đồng. |
| 23 | Restart sau checkpoint | Transport/recovery | Không bỏ sót; duplicate được xử lý. |
| 24 | Kafka/JMS listener pause/restart | Broker integration | Ack/offset/redelivery đúng. |
| 25 | HTTP inbound timeout | HTTP integration | Status/correlation/timeout đúng. |
| 26 | Duplicate event ID | Flow + persistence | Không business side effect trùng. |
| 27 | Tenant trùng tên file | Flow + adapter | Không định tuyến chéo tenant. |
| 28 | CI chạy song song | Fixture isolation | Không tranh queue/file/DB/mock. |

Với mỗi test cần ghi **đầu vào, cấu hình trigger, initial state, điểm quan sát, timeout, cleanup và giới hạn bằng chứng**. Một test không nhận message chỉ trong 1 ms không chứng minh scheduler đã không xử lý sai.

## 27. Case study: SFTP inbound nhận báo cáo tài chính định kỳ

Đối tác upload CSV lên SFTP. Ứng dụng phải poll định kỳ, chỉ nhận file đã hoàn tất, kiểm tra tenant, chuyển thành event và gửi tới hệ thống nội bộ. File có thể đến trễ, mạng lỗi và cùng báo cáo có thể upload lại.

~~~mermaid
flowchart LR
    PARTNER["SFTP partner<br/>*.tmp → *.ready"] --> SYNC["SFTP sync / source"]
    CLOCK["Poller schedule"] --> SYNC
    SYNC --> CH["fileInput channel"]
    CH --> VALID["CSV/tenant validation"]
    VALID --> TRANSFORM["ReportEvent transform"]
    TRANSFORM --> OUT["Outbound adapter"]
    SYNC --> META["Metadata/filter"]
    VALID --> ERR["Reject/quarantine"]
~~~

### Bộ A — Clock và business contract

- File có `effectiveAt` chưa tới thì không tạo business side effect.
- Kiểm tra trước, đúng tại và sau deadline với `Clock.fixed`.
- Kiểm tra event đổi ngày hiệu lực, múi giờ và schema version.

### Bộ B — Flow isolation

- Dùng `MockIntegrationContext` thay inbound source bằng `Message<File>` từ `@TempDir`.
- Giữ parser/validator/transformer/channel thực.
- Mock outbound handler và xác minh `eventId`, `tenantId` và payload.
- File sai schema không được đến outbound boundary.

### Bộ C — SFTP integration

- Dùng server SFTP thử nghiệm có host key và account riêng.
- Upload file `*.tmp`, xác minh không được phát; rename `*.ready` và đọc đúng bytes.
- Test outage, reconnect, filter, duplicate filename và restart.
- Đọc metadata và local output để xác minh side effect.

### Bộ D — End-to-end

- Chạy SFTP, polling flow và hệ thống đích thử nghiệm.
- Xác nhận file tạo kết quả cuối đúng.
- Mô phỏng outbound nhận rồi timeout, kiểm tra idempotency.
- Khởi động lại ứng dụng, đối soát backlog và trạng thái pending.

**Điều kiện thành công:** không đọc file sớm, không bỏ sót file ready, không side effect trùng ngoài policy, có correlation/event ID, có recovery khi lỗi, và có bằng chứng tại đích.

## 28. Thiết kế CI để không flaky

1. **Tách suite nhanh và suite transport:** unit/flow mỗi PR; SFTP/DB/broker integration khi thay adapter hoặc theo lịch CI.
2. **Không dùng `Thread.sleep` làm cơ chế đồng bộ chính:** latch, channel và bounded wait tốt hơn.
3. **Timeout hữu hạn:** đủ cho môi trường test nhưng không treo vô hạn.
4. **Namespace riêng:** file, SFTP path, topic, queue, database row và correlation ID cho từng test.
5. **Clock rõ ràng:** inject `Clock` cho domain; cấu hình zone cho cron.
6. **Không hard-code thời điểm cron gần giờ thật:** kiểm tra next-execution bằng trigger test.
7. **Quản lý lifecycle:** start sau setup; stop và xử lý in-flight trong teardown.
8. **Reset mocks:** gọi `MockIntegrationContext.resetBeans()` nếu có substitution.
9. **Dọn metadata:** filter/checkpoint, queue, file, broker, DB.
10. **Không dùng production:** mọi transport test dùng tài nguyên isolated.
11. **Không lộ secret:** dùng fixture/credential thử nghiệm theo chính sách CI.
12. **Lưu evidence khi fail:** endpoint ID, test ID, timestamp, attempt, message/business ID và trạng thái quan sát.

### Context caching

Spring Test có thể tái sử dụng `ApplicationContext`. Một poller chưa dừng hoặc queue chưa drain làm test sau nhận dữ liệu cũ. Reset substitutions không đủ thay cleanup tài nguyên. `@DirtiesContext` có thể dùng nếu thay đổi context không thể khôi phục, nhưng tạo lại context tốn kém và không thay thế quản lý lifecycle tốt.

## 29. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách sửa |
|---|---|---|
| Sleep cố định rồi assert | Flaky theo CPU/GC | Dùng latch hoặc điểm quan sát có timeout. |
| Fake source luôn trả cùng message | Duplicate mỗi tick | Fake hữu hạn, trả `null` khi hết. |
| Auto-start trước setup | Đọc nguồn thật/file cũ | `noAutoStartup` và start chủ động. |
| Không stop poller | Side effect tiếp tục sau test | Stop và đợi in-flight đúng contract. |
| Quên `resetBeans()` | Mock test trước ảnh hưởng test sau | Reset trong teardown. |
| Assert chính xác từng ms | Không ổn định trên CI | Tolerance và trigger unit test. |
| `Clock.fixed` nghĩa là scheduler chạy nhanh | Nhầm domain clock và scheduler | Tách hai bài test. |
| `maxMessagesPerPoll=1` nghĩa là one-shot | Nhiều tick vẫn có nhiều message | Hiểu giới hạn theo lượt. |
| Coi Kafka listener là Spring poller | Dùng sai API/metrics | Test consumer container và offset. |
| Mock SFTP rồi tuyên bố upload/download thành công | Không có bằng chứng giao thức | Thử server SFTP thật. |
| Test restart chỉ cùng JVM | Không chứng minh checkpoint bền | Tái tạo context/process và store thật. |
| H2 được dùng chứng minh locking production | Dialect/isolation khác | Test engine DB phù hợp. |
| Chỉ đếm lệnh gửi thành công | Downstream vẫn có thể lỗi | Readback/trạng thái cuối. |
| Bỏ timezone/DST | Cron chạy sai hoặc lặp | Zone tường minh, test calendar. |
| Dùng filename làm business ID duy nhất | Upload lại/trùng tenant | Event key kèm scope. |
| Dùng chung queue/file khi test parallel | Race và dữ liệu trộn | Cô lập fixture và teardown. |

## 30. Bài tập thực hành

### Bài tập 1 — Controlled polling flow

Tạo `MessageSource<String>` phát ba message, `QueueChannel` nhận kết quả và poller fixed delay.

Yêu cầu:

1. Dùng `@SpringIntegrationTest(noAutoStartup = "...")`.
2. Đặt endpoint ID tường minh.
3. Thay source bằng `MockIntegrationContext` trước start.
4. Nhận đủ ba message bằng bounded wait.
5. Kiểm tra không phát dữ liệu vô hạn khi queue hết.
6. Stop, `resetBeans()` và dọn channel.

### Bài tập 2 — Kiểm thử thời gian nghiệp vụ

Viết `DueTimePolicy` nhận `Clock` và `effectiveAt`. Test trước, đúng tại và sau deadline, timestamp khác offset nhưng cùng instant, cùng với sự kiện hoãn lịch `v1 → v2`. Giải thích vì sao những bài unit test này không chứng minh cron/fixedDelay thật.

### Bài tập 3 — File readiness

Tạo File inbound adapter đọc thư mục `@TempDir` chỉ nhận `*.ready`. Producer ghi `*.tmp` rồi rename khi hoàn tất. Kiểm tra adapter không phát file tạm, phát đúng nội dung file ready, stop/restart và xử lý metadata. Thêm trường hợp file cùng tên được cập nhật theo chính sách.

### Bài tập 4 — SFTP hoặc JDBC

Chọn một:

- **SFTP:** server thử nghiệm, ready marker, host key, outage và restart.
- **JDBC:** DB thử nghiệm, `dueAt`, row claim, hai poller cạnh tranh và rollback.

Viết happy path cùng tối thiểu ba ca lỗi; ghi **đầu vào, mốc quan sát, timeout, expected outcome và evidence ở đích**.

### Bài tập 5 — Polling so với message-driven

Thiết kế hai flow nhận `ORDER_CREATED`: một JDBC inbound polling adapter đọc inbox, một Kafka message-driven adapter đọc topic. So sánh start/stop, số bản xử lý, retry, ordering, commit/offset, restart và backpressure. Chỉ ra nơi dùng `MockIntegrationContext` và nơi phải dùng DB/Kafka thật.

### Bài tập 6 — Test SLO và recovery

Đối tác gửi file SFTP mỗi 15 phút. Xác định `availableAt`, `receivedAt`, `verifiedAt` và công thức latency/pending. Thiết kế bài test outage 20 phút và upload duplicate; chọn ngưỡng SLO dựa trên risk/baseline thay vì tự coi số minh họa là chuẩn.

## 31. Checklist nghiệm thu

- [ ] **Phân loại inbound**: polling source, listener hay HTTP gateway.
- [ ] **Mô tả trigger**: fixed delay/rate/cron, zone và semantics.
- [ ] **Endpoint ID rõ** để thay source và điều khiển lifecycle.
- [ ] **noAutoStartup** nếu cần ngăn poll trước fixture.
- [ ] **Fake source hữu hạn**, trả `null` sau khi hết dữ liệu.
- [ ] **Business clock** được tách khỏi scheduler clock.
- [ ] **Timeout hữu hạn**, không dùng sleep làm đồng bộ chính.
- [ ] **maxMessagesPerPoll** được hiểu đúng giới hạn theo tick.
- [ ] **Startup/stop/restart và recovery** có test.
- [ ] **File/remote readiness, metadata, DB transaction** được kiểm tra trên nguồn phù hợp.
- [ ] **Duplicate/idempotency** được kiểm tra khi có redelivery.
- [ ] **Concurrency/locking** có test nền tảng thật khi cần.
- [ ] **Broker ack/offset** không bị nhầm với Spring poller.
- [ ] **Mock boundary** không được coi là side effect thật.
- [ ] **Cleanup endpoint/channel/mock/metadata** sau mỗi test.
- [ ] **Không gọi production hoặc để lộ credential** trong test.
- [ ] **Test matrix và điểm quan sát** thể hiện chính xác điều đã được chứng minh.

## 32. Tổng kết

Kiểm thử **inbound adapter theo thời gian** bắt đầu bằng việc xác định nguồn được đánh thức bởi **poller** hay bởi **sự kiện bên ngoài**. Với polling adapter, `@SpringIntegrationTest(noAutoStartup = "...")`, `MockIntegrationContext`, fake `MessageSource` hữu hạn, `QueueChannel` và lifecycle start/stop giúp kiểm tra flow nhanh, có tính quyết định. Với quy tắc deadline/expiry nghiệp vụ, `Clock` cho phép test ranh giới thời gian mà không phải ngủ chờ.

Những vấn đề **file chưa hoàn chỉnh, SFTP reconnect, JDBC locking/transaction, Kafka/JMS/AMQP acknowledgment-offset, HTTP gateway timeout, retry, idempotency và phục hồi sau restart** phải được kiểm tra bằng adapter và transport tương ứng. Một test đáng tin phải cho biết **nhận lúc nào, nguồn nào, dữ liệu gì, xử lý bao nhiêu lần, còn trạng thái nào chưa xác nhận và bằng chứng nào chứng minh kết quả ở đúng ranh giới**.

