# Kiểm thử bất đồng bộ không dùng sleep tùy ý trong Spring Integration

## 1. Vì sao `Thread.sleep(...)` làm kiểm thử message flow thiếu tin cậy?

Spring Integration triển khai nhiều Enterprise Integration Patterns (EIP) thông qua channel và endpoint. Một message có thể đi qua `DirectChannel` đồng bộ, `ExecutorChannel` bất đồng bộ, `QueueChannel` có polling consumer, Delayer dùng scheduler, hoặc các nhánh Router/Splitter/Aggregator cần chờ đủ kết quả.

Trong các flow này, đoạn kiểm thử sau rất dễ gây sai lệch:

~~~java
input.send(MessageBuilder.withPayload("ORDER-501").build());
Thread.sleep(2_000);                 // Không đồng bộ theo sự kiện nào.
assertEquals("DONE", status.get());   // Máy CI bận có thể chưa xử lý xong.
~~~

Vấn đề:

- **Flaky:** trên máy nhanh xử lý xong sau 5 ms, nhưng máy CI bận mất hơn 2 giây; test lúc pass lúc fail.
- **Lãng phí:** nếu kết quả có sau 5 ms, test vẫn phải chờ đủ 2 giây.
- **Không có quan hệ nhân quả:** hết 2 giây không chứng minh consumer đã nhận message, error flow đã kết thúc hay Aggregator đã release.
- **Che lỗi:** test có thể chỉ kiểm tra một biến trong khi message bị drop, chuyển sang nhánh khác hoặc bị retry.
- **Khó bảo trì:** tăng sleep từ 2 lên 10 giây chỉ làm test chậm hơn, chưa làm giả định đúng hơn.

Phương pháp tốt hơn là **đợi một điều kiện quan sát được**, với **timeout tối đa rõ ràng**, rồi assert nội dung và ngữ nghĩa:

~~~text
Gửi message
    |
    v
Đợi sự kiện hoàn thành / nhận message / trạng thái cuối
    |
    +-- Hoàn thành trước hạn -> assert ngay
    |
    +-- Hết thời gian chờ -> fail với chẩn đoán cụ thể
~~~

Đối với module **SPRING_INTEGRATION_PATTERN**, đây là nền tảng kiểm thử các nhánh Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation. Mục tiêu không chỉ là “test hết đỏ”, mà còn chứng minh message **đi đúng nhánh, giữ đúng header nghiệp vụ, xử lý lỗi đúng chính sách và kết thúc đúng điều kiện**.

## 2. Nguyên tắc: đồng bộ bài test theo tín hiệu, không theo phỏng đoán thời gian

Mỗi kiểm thử bất đồng bộ nên trả lời bốn câu:

1. **Trigger:** hành động nào khởi động flow? Ví dụ `input.send(...)`.
2. **Observable:** có thể quan sát sự kiện nào? Message ở output channel, callback, DB row, `ErrorMessage`, completion signal hay metric?
3. **Completion condition:** điều gì đủ để coi kịch bản đã kết thúc? Ví dụ nhận được đúng `eventId` và trạng thái `COMPLETED`.
4. **Timeout budget:** nếu điều kiện không xảy ra, đợi tối đa bao lâu và thông báo lỗi như thế nào?

~~~mermaid
flowchart TD
    A[Test gửi message] --> B[Async channel / scheduler / poller]
    B --> C{Điều kiện hoàn tất đã đúng?}
    C -->|Có| D[Assert payload, header và side effect]
    C -->|Chưa| E{Đã hết timeout?}
    E -->|Chưa| C
    E -->|Rồi| F[Fail với eventId và trạng thái quan sát]
~~~

**Phân biệt timeout của bài test với timeout nghiệp vụ.** `receive(3_000)` có nghĩa bài test sẵn sàng đợi tối đa 3 giây để thấy message ở queue. Nó không khiến Delayer đổi delay, Gateway thay `replyTimeout` hay consumer bị hủy khi hết thời gian.

### Bảng chọn công cụ

| Mục tiêu test | Công cụ phù hợp | Điều cần chú ý |
| --- | --- | --- |
| Đợi message xuất hiện trên queue | `PollableChannel.receive(timeout)` | Kiểm tra payload/header và đúng channel |
| Đợi một callback/handler được gọi | `CountDownLatch.await(timeout)` | Latch nên được tạo mới cho mỗi test |
| Đợi trạng thái cuối trong DB hoặc in-memory state | Awaitility `untilAsserted(...)` | Điều kiện phải có tính quan sát được và kiểm tra an toàn |
| Đợi kết quả một tác vụ Java | `CompletableFuture.get(timeout)` | Kết quả có thể ném `ExecutionException` |
| Điều phối thứ tự giữa hai thread | Hai `CountDownLatch` hoặc `Phaser` | Dùng tín hiệu entered/release, không dùng sleep để “canh” |
| Kiểm tra logic deadline thuần túy | Inject `Clock`, dùng `Clock.fixed(...)` | Chỉ điều khiển clock của logic nghiệp vụ, không mặc nhiên điều khiển scheduler của Spring |
| Test retry và lỗi | Probe/spy + output/error channel | Assert số lần thử và kết quả cuối, tránh chỉ kiểm tra log |
| Bảo vệ cả bài test khỏi treo | JUnit `@Timeout` | Đây là guard, không thay thế assert điều kiện hoàn tất |

## 3. Ví dụ hoàn chỉnh: `ExecutorChannel` và `QueueChannel.receive(timeout)`

Flow dưới đây chuyển message sang executor, xử lý payload thành chữ in hoa rồi đưa vào queue. Bởi vì handler chạy trên thread khác, `send(...)` của producer **không chứng minh** message đã tới `async.out`.

Phụ thuộc cần thiết khi dùng Spring Boot:

- `spring-boot-starter-integration` cho Spring Integration DSL.
- `spring-boot-starter-test` cho JUnit 5/Spring Test.

### 3.1. Cấu hình flow

~~~java
import java.util.Locale;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class AsyncPatternTestConfig {

    @Bean(name = "asyncTestExecutor", destroyMethod = "shutdown")
    public ExecutorService asyncTestExecutor() {
        return Executors.newFixedThreadPool(2);
    }

    @Bean("async.in")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean("async.workers")
    public MessageChannel workers(
            @Qualifier("asyncTestExecutor") Executor executor) {
        return new ExecutorChannel(executor);
    }

    @Bean("async.out")
    public PollableChannel output() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow asyncFlow() {
        return IntegrationFlow.from("async.in")
                .channel("async.workers")
                .handle(String.class, (payload, headers) ->
                        payload.toUpperCase(Locale.ROOT))
                .channel("async.out")
                .get();
    }
}
~~~

Trong ví dụ này:

| Thành phần | Trách nhiệm |
| --- | --- |
| `DirectChannel` tại `async.in` | Producer gửi request vào flow |
| `ExecutorChannel` | Chuyển việc xử lý sang executor |
| Handler | Trả về payload kết quả |
| `QueueChannel` tại `async.out` | Giữ message kết quả để bài test nhận theo timeout |

Bean `ExecutorService` được Spring shutdown khi đóng context, tránh để lại thread chạy sau bài test. Trong production, có thể dùng `ThreadPoolTaskExecutor` và giới hạn concurrency/queue thay vì tạo executor mẫu này.

### 3.2. JUnit: đợi đúng message đầu ra

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(AsyncPatternTestConfig.class)
class AsyncPatternFlowTest {

    @Autowired
    @Qualifier("async.in")
    MessageChannel input;

    @Autowired
    @Qualifier("async.out")
    PollableChannel output;

    @Test
    @Timeout(10)
    void receivesResultWithoutArbitrarySleep() {
        assertTrue(input.send(
                MessageBuilder.withPayload("order-501")
                        .setHeader("eventId", "event-501")
                        .setHeader("correlationId", "order-501")
                        .build()));

        Message<?> result = output.receive(5_000);

        assertNotNull(result, "Không nhận được message trong 5 giây");
        assertEquals("ORDER-501", result.getPayload());
        assertEquals("event-501",
                result.getHeaders().get("eventId"));
        assertEquals("order-501",
                result.getHeaders().get("correlationId"));
    }
}
~~~

`receive(5_000)` **trả về ngay** khi message có trong queue; không bắt bài test chờ trọn 5 giây. Nếu timeout hết, nó trả `null` để bài test fail với lý do cụ thể.

**Tại sao cần assert headers?** Transformer/Service Activator có thể tạo message mới. Header `MessageHeaders.ID` có thể thay đổi, nhưng `eventId` và `correlationId` nghiệp vụ cần được giữ (trừ khi logic đã chủ động đổi chúng). Kiểm tra đúng event giúp tránh test nhận nhầm message của test khác.

### Vì sao không nên assert output rỗng ngay sau `send()`?

~~~java
assertTrue(input.send(message));
assertNull(output.receive(0)); // Có thể fail do executor đã xử lý quá nhanh.
~~~

Một task chạy rất nhanh có thể đã phát ra output trước khi dòng `receive(0)` thực thi. Đây là race giữa test thread và worker thread, không nhất thiết là lỗi flow. Chỉ dùng khẳng định “chưa có message” khi có **điều kiện đồng bộ đáng tin cậy** hoặc một deadline nghiệp vụ rõ ràng.

## 4. `CountDownLatch`: đợi một cột mốc đã được handler báo hiệu

Nếu muốn chứng minh handler thực sự đã bắt đầu và kiểm soát khi nào nó được hoàn thành, sử dụng **hai latch**:

- `entered`: worker báo “tôi đã đi vào handler”.
- `allowFinish`: bài test cho phép worker chạy tiếp.
- `completed`: worker báo “tôi đã xử lý xong”.

~~~mermaid
sequenceDiagram
    participant T as Test thread
    participant W as Worker thread
    T->>W: Gửi message
    W->>T: entered.countDown()
    T->>T: entered.await(timeout) == true
    Note over W: Chờ allowFinish
    T->>T: Assert chưa hoàn thành
    T->>W: allowFinish.countDown()
    W->>T: completed.countDown()
    T->>T: completed.await(timeout) == true
~~~

### 4.1. Probe dùng trong bài test

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class GatedHandlerProbe {
    private final CountDownLatch entered = new CountDownLatch(1);
    private final CountDownLatch allowFinish = new CountDownLatch(1);
    private final CountDownLatch completed = new CountDownLatch(1);
    private final AtomicReference<String> result = new AtomicReference<>();
    private final AtomicReference<Throwable> failure = new AtomicReference<>();

    public void handle(String payload) {
        entered.countDown();
        try {
            if (!allowFinish.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Test gate timed out");
            }
            result.set(payload.toUpperCase(java.util.Locale.ROOT));
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            failure.set(ex);
        } catch (RuntimeException ex) {
            failure.set(ex);
        } finally {
            completed.countDown();
        }
    }

    public boolean awaitEntered() throws InterruptedException {
        return entered.await(3, TimeUnit.SECONDS);
    }

    public void release() {
        allowFinish.countDown();
    }

    public boolean awaitCompleted() throws InterruptedException {
        return completed.await(3, TimeUnit.SECONDS);
    }

    public boolean isCompleted() {
        return completed.getCount() == 0;
    }

    public String result() {
        return result.get();
    }

    public Throwable failure() {
        return failure.get();
    }
}
~~~

Lưu ý: `CountDownLatch` **không reset được**. Mỗi test case nên tạo probe/context mới, hoặc dùng cơ chế quản lý lifecycle để tránh latch của test trước đã ở giá trị 0.

### 4.2. Gắn probe vào một flow bất đồng bộ

~~~java
// Các method bên dưới được đặt trong một class @Configuration
// có @EnableIntegration, và sử dụng một Executor đã khai báo.

@Bean
GatedHandlerProbe gateProbe() {
    return new GatedHandlerProbe();
}

@Bean("gate.in")
MessageChannel gateInput() {
    return new DirectChannel();
}

@Bean("gate.async")
MessageChannel gateExecutorChannel(
        @Qualifier("asyncTestExecutor") Executor executor) {
    return new ExecutorChannel(executor);
}

@Bean
IntegrationFlow gatedFlow(GatedHandlerProbe gateProbe) {
    return IntegrationFlow.from("gate.in")
            .channel("gate.async")
            .handle(gateProbe, "handle")
            .get();
}
~~~

Đoạn này **mở rộng** `AsyncPatternTestConfig` ở mục 3, tái sử dụng bean `asyncTestExecutor` và các import Spring/Executor đã khai báo. Không chép nguyên đoạn vào một class Java trống rồi coi là flow độc lập.

### 4.3. Kiểm thử thứ tự chính xác, không canh thời gian

~~~java
@Test
@Timeout(10)
void handlerWaitsForExplicitRelease() throws Exception {
    // Bean "gate.in" và GatedHandlerProbe được inject từ context.
    try {
        assertTrue(gateInput.send(
                MessageBuilder.withPayload("order-502").build()));

        assertTrue(gateProbe.awaitEntered(), "Worker chưa vào handler");
        assertFalse(gateProbe.isCompleted(),
                "Handler đã hoàn thành trước khi được test release");

        gateProbe.release();

        assertTrue(gateProbe.awaitCompleted(), "Handler chưa hoàn thành");
        assertNull(gateProbe.failure());
        assertEquals("ORDER-502", gateProbe.result());
    } finally {
        gateProbe.release(); // Bảo đảm không kẹt worker khi assertion fail.
    }
}
~~~

Đoạn JUnit trên giả định hai field `gateInput` (bean `gate.in`) và `gateProbe` đã được inject; đây là method bổ sung trong class test, không phải test class đầy đủ. Nó chứng minh **quan hệ xảy ra trước/sau** bằng tín hiệu đồng bộ thay vì giả định “sau 200 ms chắc handler đã vào”.

## 5. Awaitility: đợi trạng thái cuối và assert được nhiều lần

Khi kết quả nằm trong database, cache, hoặc một service status, có thể không có `PollableChannel` để `receive`. Awaitility hỗ trợ đợi một **điều kiện liên tục được kiểm tra** và trả về ngay khi điều kiện đúng.

Ví dụ thêm dependency chỉ trong test (Maven):

~~~xml
<dependency>
    <groupId>org.awaitility</groupId>
    <artifactId>awaitility</artifactId>
    <scope>test</scope>
</dependency>
~~~

Cần khai báo phiên bản tương thích trong dependency management, hoặc ghi version trực tiếp nếu project không quản lý dependency này.

~~~java
import java.time.Duration;
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;

// repository.findStatus(eventId) là API đọc trạng thái trong ví dụ.
await()
        .atMost(Duration.ofSeconds(5))
        .pollInterval(Duration.ofMillis(50))
        .untilAsserted(() ->
                assertEquals("COMPLETED",
                        repository.findStatus("event-501")));
~~~

**Khác với sleep:** nếu DB trả `COMPLETED` sau 120 ms, bài test có thể kết thúc sau vài lượt poll thay vì luôn đợi 5 giây. Nếu thất bại, Awaitility báo timeout điều kiện và assertion được mong đợi.

Để tránh test giả:

- Điều kiện cần phản ánh **trạng thái thực** của flow, không chỉ một biến được đặt trước khi xử lý xong.
- Nếu dùng DB, truy vấn phải thấy trạng thái đã commit, không chỉ dữ liệu chưa commit trong transaction của test.
- Một điều kiện nhiều lần đọc cần thread-safe; với mutable state trong RAM, dùng `AtomicReference` hoặc cấu trúc đồng bộ phù hợp.
- Tránh polling quá dày làm quá tải DB; `50 ms` chỉ là ví dụ cho test nhỏ.
- Không tự retry hành động nghiệp vụ trong predicate của Awaitility. Predicate nên **đọc/quan sát**, không tạo thêm side effect.

### Kiểm thử retry: đợi trạng thái cuối, không chờ số giây dự đoán

~~~java
await()
        .atMost(Duration.ofSeconds(8))
        .untilAsserted(() -> {
            assertEquals("DONE", statusStore.findStatus("event-retry-1"));
            assertEquals(3, attemptCounter.get());
        });
~~~

Ví dụ giả định test chủ động cấu hình handler thất bại hai lần đầu rồi thành công lần ba. Phải chắc rằng `attemptCounter` chỉ đếm đúng sự kiện này hoặc có map theo `eventId`; dùng một counter toàn cục khi nhiều message đang chạy song song dễ khiến assertion sai.

### Đừng dùng Awaitility để chứng minh không có sự kiện xảy ra mãi mãi

Khẳng định “không có message trong 100 ms” chỉ chứng minh **không quan sát được trong cửa sổ 100 ms**. Nếu muốn chứng minh Filter đã loại message, hãy đo output và **một dấu hiệu hoàn tất** (ví dụ Filter discard channel có message cùng `eventId`). Khi biết flow đã kết thúc tại nhánh discard, không cần chờ một khoảng tùy ý để đoán rằng không có output chính.

## 6. Kiểm thử Filter và Router: quan sát đúng nhánh

Với Filter, Router, Aggregator, một message có thể không xuất hiện ở channel mặc định vì **đúng logic phân nhánh**, không phải vì flow bị lỗi. Do đó không chỉ kiểm tra “output không có gì”.

### Ví dụ tiêu chí kiểm thử Filter

~~~text
Input: order.status = CANCELLED, eventId = order-503
Expected:
  - discard channel nhận đúng eventId = order-503
  - accepted channel không nhận eventId này
  - không phát sinh side effect gửi thông báo
~~~

Mẫu kiểm thử có hai `PollableChannel` đích:

~~~java
Message<?> discarded = discardChannel.receive(3_000);
assertNotNull(discarded, "Filter chưa hoàn thành nhánh discard");
assertEquals("order-503", discarded.getHeaders().get("eventId"));

// Dùng discard như tín hiệu kết thúc thay vì Thread.sleep(...).
// Việc xác nhận không có side effect cần một probe hoặc repository tương ứng.
assertEquals(0, sendProbe.countFor("order-503"));
~~~

Đoạn trên giả định Filter đã có `discardChannel`, `sendProbe` là một test double thread-safe và không có nhánh nào còn xử lý cùng `eventId` sau khi discard. Nếu một flow phức tạp có nhiều nhánh phát song song, cần đợi **tất cả nhánh liên quan kết thúc** trước khi khẳng định không có tác động.

### Với Router

- Đưa message có header `priority=HIGH` và `eventId` xác định.
- Đợi chính xác message ở `highPriorityChannel`.
- Assert payload, headers và đích xử lý.
- Kiểm thử nhánh default/unresolved có ý thức, thay vì chỉ nói “không thấy message”.

Để các test chạy song song độc lập, dùng context/channel riêng hoặc kịch bản có key đặc thù; nếu đọc cùng một `QueueChannel` có nhiều message, test phải lọc/correlate hoặc kiểm soát nguồn phát.

## 7. Splitter và Aggregator: đợi **đủ phần tử**, không ngủ chờ

Một Splitter có thể tạo N message; mỗi message có thể đi qua executor khác nhau. Aggregator release khi điều kiện nhóm thỏa mãn, thường dựa trên sequence metadata hoặc release strategy đã định nghĩa.

~~~mermaid
flowchart LR
    A[Input batch] --> S[Splitter]
    S --> B1[Item 1]
    S --> B2[Item 2]
    S --> B3[Item 3]
    B1 --> E[Async handlers]
    B2 --> E
    B3 --> E
    E --> G[Aggregator]
    G --> O[Aggregated output]
~~~

**Tiêu chí test tốt:**

1. Đợi **một aggregated result** bằng `output.receive(timeout)`.
2. Assert số phần tử và tập ID/payload, không mặc định thứ tự nếu flow không yêu cầu.
3. Assert `correlationId` hoặc group key phù hợp.
4. Kiểm tra trường hợp thiếu một phần tử, duplicate, timeout hoặc release strategy đặc biệt.

Ví dụ assert tập hợp kết quả (giả định aggregator trả `List` các String):

~~~java
Message<?> aggregate = aggregatedOutput.receive(5_000);
assertNotNull(aggregate, "Aggregator không release trong timeout");

@SuppressWarnings("unchecked")
java.util.List<String> payloads =
        (java.util.List<String>) aggregate.getPayload();

assertEquals(3, payloads.size());
assertEquals(
        java.util.Set.of("A", "B", "C"),
        new java.util.HashSet<>(payloads));
~~~

Nếu Aggregator của ứng dụng trả về một object hoặc `List<Message<?>>` thay vì `List<String>`, cần kiểm tra theo **hợp đồng output thực**. Khi thứ tự có ý nghĩa nghiệp vụ, phải có chiến lược resequencing/order rõ ràng và assert thứ tự; không tùy tiện so sánh `List` khi thứ tự không được bảo đảm.

### Tránh giả định các message chạy song song “chắc sẽ xong trong 500 ms”

Điều kiện release của Aggregator, retry ở từng nhánh và tốc độ scheduler mới quyết định khi nào có kết quả. Một sleep không phân biệt được “chưa đủ phần tử” với “có phần tử đã thất bại và đi sang error channel”. Test nên quan sát cả **result channel** và **error path**.

## 8. Kiểm thử Delayer: kết hợp deadline với tín hiệu release

Delayer chủ ý đợi một khoảng thời gian hoặc mốc tuyệt đối. Để kiểm thử “không phát quá sớm”, cần vừa đo thời gian **vừa đợi output có thật**, không chỉ `sleep` rồi so đồng hồ.

~~~java
import java.util.concurrent.TimeUnit;

long started = System.nanoTime();

assertTrue(input.send(
        MessageBuilder.withPayload("PAYMENT-REMINDER")
                .setHeader("delayMs", 700L)
                .build()));

Message<?> released = output.receive(3_000);
assertNotNull(released, "Message phải được phát trong timeout");

long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
        System.nanoTime() - started);
assertTrue(elapsedMs >= 700L, "Không được release trước hạn");
~~~

Ví dụ giả định Delayer dùng biểu thức `headers['delayMs']` và output queue. `System.nanoTime()` phù hợp đo **khoảng thời gian trong cùng tiến trình**; không dùng nó làm timestamp UTC để lưu vào database hoặc đối chiếu giữa nhiều máy.

**Giới hạn của timing test:** nếu thread test bị tạm dừng rất lâu ngay sau `send`, phép đo ở trên có thể không phát hiện được trường hợp message đã được release quá sớm. Với logic deadline yêu cầu độ chính xác cao, tốt hơn nên gắn một **probe tại điểm release** để ghi lại thời gian thực tế, hoặc kiểm thử logic tính deadline riêng bằng clock/scheduler có thể điều khiển.

### Fake `Clock` không tự làm Delayer chạy ngay

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixed = Clock.fixed(
        Instant.parse("2026-11-21T10:00:00Z"),
        ZoneOffset.UTC);

boolean expired = !Instant.parse("2026-11-21T09:59:00Z")
        .isAfter(fixed.instant());
assertTrue(expired);
~~~

Đoạn này kiểm tra **logic so sánh deadline của ứng dụng**. Nó không tác động tới `TaskScheduler` của Delayer trừ khi scheduler đã được thiết kế để sử dụng đồng hồ điều khiển đó. Đừng thay `Clock` trong một service rồi mặc định mọi tác vụ scheduled Spring Integration đều “tua nhanh” tương ứng.

Với scheduling phức tạp, một thiết kế dễ kiểm thử nên tách:

- **Tính due time:** hàm thuần hoặc service nhận `Clock` để kiểm tra bằng `Clock.fixed(...)`.
- **Đăng ký tác vụ:** một adapter quanh `TaskScheduler` có thể được mock/capture thời điểm `schedule(...)`.
- **Thực thi tác vụ:** kiểm thử rằng callback được gọi đúng và endpoint phát message theo hợp đồng.
- **Tích hợp thật:** một số ít test với scheduler thực, timeout có giới hạn và độ dư phù hợp.

## 9. Kiểm thử retry và error channel mà không dựa vào log

Khi handler có retry, các sự kiện cần quan sát:

~~~mermaid
sequenceDiagram
    participant T as Test
    participant F as Retry-enabled Flow
    participant C as Handler
    participant E as Error Channel
    T->>F: Message(eventId=evt-901)
    F->>C: Attempt 1
    C--xF: Temporary error
    F->>C: Attempt 2
    C--xF: Temporary error
    F->>C: Attempt 3
    alt Thành công
       C-->>F: Result
       F-->>T: Success output observable
    else Hết số lần thử
       F->>E: ErrorMessage
       E-->>T: Error observable
    end
~~~

Với `RequestHandlerRetryAdvice` hoặc retry tại Delayer, cách quan sát phụ thuộc nơi retry chạy. Một test nên có:

- Counter thread-safe theo **`eventId`**, không dùng một biến global nếu nhiều message đồng thời.
- Output channel cho thành công.
- Error channel hoặc durable DLQ/spy cho nhánh lỗi.
- Giới hạn thời gian tổng phù hợp với số attempt, backoff và timeout của handler.

Ví dụ khi **đã cấu hình** recovery phát `ErrorMessage` vào `PollableChannel errors`:

~~~java
Message<?> failed = errors.receive(5_000);
assertNotNull(failed, "Không thấy message lỗi sau retry");
assertInstanceOf(
        org.springframework.messaging.support.ErrorMessage.class, failed);
assertInstanceOf(Throwable.class, failed.getPayload());
assertEquals(3, attemptsByEvent.get("evt-901").get());
~~~

Đoạn này **không tự cấu hình retry/error channel**: cần có flow gửi lỗi vào `errors` (ví dụ `ErrorMessageSendingRecoverer` của `RequestHandlerRetryAdvice`), đồng thời message `evt-901` phải cố ý thất bại đúng ba lần. Với `DirectChannel` đồng bộ không có recoverer, exception có thể truyền về caller thay vì tự chạy tới global `errorChannel`.

### Kiểm thử nhánh không retryable

Một message có payload sai schema thường nên bị từ chối/route quarantine **ngay**, không cần retry vài lần. Kiểm thử:

1. Gửi message lỗi cố định có `eventId`.
2. Chờ observable ở nhánh quarantine/error.
3. Assert nguyên nhân, metadata và tổng số lần handler được gọi (ví dụ 1).
4. Xác minh không có side effect nghiệp vụ.

**Lưu ý:** nếu chỉ chờ `errors.receive(5_000)` mà không có message, kết quả timeout có thể do cấu hình error flow sai, handler chưa chạy hoặc bài test gửi nhầm channel. Cần đặt thông tin diagnostic như `eventId` và trạng thái executor/flow để phân biệt nguyên nhân.

## 10. Nhiều message đồng thời: phân biệt kết quả theo identity

Trong flow bất đồng bộ, thứ tự hoàn thành có thể khác thứ tự gửi. Ví dụ message B có handler nhanh có thể ra trước A dù được gửi sau.

~~~text
Send:     A -----> B -----> C
Complete:      B -----> C -----> A
~~~

Không assert FIFO nếu kiến trúc không đảm bảo FIFO. Hãy assert **tập kết quả và identity**:

~~~java
java.util.Set<String> expected =
        java.util.Set.of("event-A", "event-B", "event-C");
java.util.Set<String> actual = new java.util.HashSet<>();

for (int i = 0; i < expected.size(); i++) {
    Message<?> result = output.receive(5_000);
    assertNotNull(result, "Thiếu message ở output");
    actual.add((String) result.getHeaders().get("eventId"));
}

assertEquals(expected, actual);
~~~

Nếu muốn chứng minh **exactly one message cho mỗi `eventId`**, cần kiểm tra không có duplicate theo một observable đủ mạnh: counter ở consumer, unique constraint trong inbox, tổng số side effect, hoặc các tín hiệu hoàn tất đã đồng bộ. Một lần `receive(0) == null` sau khi lấy ba message chỉ là snapshot nhất thời, **không chứng minh sẽ không có duplicate trong tương lai**.

### Cô lập bài test

- Tạo context/channel riêng cho từng test khi có shared queue hoặc sử dụng `@DirtiesContext` nếu cần.
- Nếu context dùng chung, reset probe/counter theo event ID trước mỗi test và bảo đảm không còn worker từ test cũ.
- Dùng `eventId` duy nhất theo bài test; không dùng payload ngắn như `"hello"` làm tiêu chí nhận diện duy nhất.
- Dọn message trong queue/test DB có kiểm soát; không xóa nhầm dữ liệu của test khác.
- Đóng executor và context sau test để không có thread chạy lại sau khi assertion hoàn tất.

## 11. Kiểm thử Gateway và request/reply bất đồng bộ

Gateway có thể đợi reply trong một khoảng thời gian. Nếu flow đi qua Delayer hoặc executor và trả kết quả trễ, Gateway có thể timeout dù downstream tiếp tục chạy.

**Phân biệt:**

| Sự kiện | Chứng minh điều gì? |
| --- | --- |
| Producer/Gateway gửi request thành công | Flow đã nhận request ở mức contract đầu vào |
| Gateway `replyTimeout` hết | Caller không nhận reply trong hạn |
| Handler cuối xử lý xong | Tác động nghiệp vụ có thể đã hoàn tất |
| Reply đến sau timeout | Caller có thể không còn chờ kết quả |

Khi kiểm thử:

1. Định cấu hình `replyTimeout` cụ thể cho Gateway và delay cụ thể cho downstream.
2. Dùng `assertThrows` hoặc kết quả trả về phù hợp với `errorOnTimeout`/hợp đồng Gateway.
3. Chờ **một probe độc lập ở downstream** để xác nhận tác vụ tiếp tục hoặc bị hủy theo thiết kế, không chỉ dựa vào timeout của caller.
4. Dùng `eventId` để kiểm tra kết quả sau timeout nếu ứng dụng hỗ trợ tra cứu trạng thái.

Với nghiệp vụ dài, nên thiết kế request được **ACK đã tiếp nhận**, rồi cung cấp kết quả bằng message/callback hoặc truy vấn trạng thái; tránh giữ một Gateway đồng bộ chờ hàng phút.

## 12. Timeout budget, trạng thái lỗi và test flakiness trên CI

Một timeout quá ngắn làm test fail do máy bận; quá dài khiến phát hiện lỗi chậm. Chọn deadline dựa trên **cấu hình flow thực** và có độ dư có chủ đích.

Ví dụ:

~~~text
Delayer delay mặc định:           300 ms
Handler retry: 3 lần, backoff: 2 x 100 ms
Giới hạn mỗi lời gọi stub:        200 ms
Thời gian kỳ vọng tối đa logic:  300 + 600 + 200 = 1.100 ms
Timeout test đề xuất (ví dụ):   3.000 ms
~~~

Các con số trên là minh họa, không phải SLA của Spring Integration. Nếu CI chậm hoặc cần tích hợp network/database thật, chọn timeout phù hợp hơn; không điều chỉnh sleep ngẫu nhiên để “chữa” test.

### Giữ nguyên tính chẩn đoán khi fail

Một assert hữu ích nên chỉ ra:

- `eventId` nào không hoàn thành.
- Channel hoặc nhánh đang đợi.
- Số lần retry đã quan sát.
- Trạng thái hiện tại của hàng đợi/DB/consumer.
- Timeout cấu hình và kỳ vọng nghiệp vụ.

Ví dụ:

~~~java
Message<?> result = output.receive(3_000);
assertNotNull(result, "event-501: không có output sau 3s ở async.out");
~~~

JUnit `@Timeout(10)` là **hàng rào chống test treo**. Nó không thay thế `receive(timeout)` hoặc `latch.await(timeout)`, bởi vì điều kiện hoàn tất vẫn cần được khẳng định tường minh.

### Những lỗi thường làm test bất đồng bộ chập chờn

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Pass local, fail CI | Dựa vào sleep, timeout quá sát, máy CI bận | Đợi observable; nới timeout có căn cứ |
| Thỉnh thoảng nhận nhầm message | Shared `QueueChannel` giữa nhiều test | Cô lập context hoặc correlate theo `eventId` |
| Test fail vì counter sai | Dùng một counter chung cho nhiều message | Đếm theo eventId, reset/cô lập state |
| Assert “không có output” fail ngẫu nhiên | Không đồng bộ được thời điểm quan sát | Dùng gate/latch hoặc tín hiệu hoàn tất nhánh |
| Test Aggregator không release | Thiếu một phần tử, correlation ID sai, release strategy chưa thỏa | Kiểm tra đủ message, group và đường lỗi |
| Test cứ treo | Latch không release khi assertion fail, executor còn chạy | `try/finally` release gate, timeout và shutdown |
| Test Delayer trễ | TaskScheduler chịu tải hoặc host bị pause | Đo deadline/release bằng probe và timeout có dư |
| Test error channel không thấy gì | Lỗi sync truyền về caller hoặc recovery chưa được cấu hình | Kiểm tra ranh giới đồng bộ/bất đồng bộ |
| Test DB nhìn thấy dữ liệu nhưng consumer không | Test transaction chưa commit hoặc không cùng resource | Đặt đúng ranh giới transaction và quan sát sau commit |

## 13. Checklist thiết kế một bài test pattern bất đồng bộ

Trước khi chạy một test, kiểm tra:

1. **Mỗi test có một input xác định** với `eventId` rõ ràng.
2. **Điều kiện hoàn tất được định nghĩa** bằng message, callback, DB row hoặc probe.
3. Có **timeout tối đa**; không chờ vô hạn.
4. Có assertion về **payload, headers, routing và side effect**, không chỉ kiểm tra `send() == true`.
5. Xử lý riêng đường **success**, **discard** và **error**; không giả định errorChannel nhận mọi exception.
6. Dữ liệu giữa các test được **cô lập**; không có worker cũ ảnh hưởng.
7. Biết ranh giới thread giữa `DirectChannel`, `ExecutorChannel`, poller và broker.
8. Với Delayer/retry, phân biệt **logic thời gian** và **lịch thực thi thực tế**.
9. Với Splitter/Aggregator, kiểm tra correlation, sequence và release strategy; không mặc định thứ tự khi chạy concurrent.
10. Khi test fail, kết quả đủ thông tin để chẩn đoán **đã kẹt ở bước nào**.

## 14. Bài tập thực hành

1. Thay `Thread.sleep(2_000)` trong một test `ExecutorChannel` bằng `PollableChannel.receive(timeout)`. So sánh thời gian chạy trên máy nhanh và CI.
2. Dùng hai `CountDownLatch` để chứng minh handler đã vào nhưng chưa hoàn tất trước khi test phát tín hiệu cho phép chạy tiếp.
3. Dùng Awaitility đợi một DB row chuyển trạng thái `PENDING → COMPLETED` sau một IntegrationFlow chạy bất đồng bộ.
4. Tạo Filter route các order `CANCELLED` sang discard channel. Viết test kiểm tra discard signal và không có side effect gửi email.
5. Tạo Router ưu tiên và gửi ba message có `eventId` khác nhau. Assert tập message ở từng nhánh, không phụ thuộc thứ tự hoàn thành.
6. Splitter một danh sách ba item rồi Aggregator. Đợi kết quả aggregate thay vì sleep, kiểm tra tập item và correlation key.
7. Cho handler lỗi hai lần rồi thành công lần ba; đợi success channel, kiểm tra attempt counter theo `eventId`.
8. Cho handler lỗi vĩnh viễn và recovery gửi `ErrorMessage`; đợi error queue, kiểm tra exception và message gốc.
9. Kiểm thử Delayer chờ 700 ms. Đo release bằng probe tại output, phân tích giới hạn khi test thread bị scheduler tạm dừng.
10. Kiểm thử Gateway timeout trước khi downstream hoàn thành. Dùng một probe khác để xác minh downstream vẫn chạy theo chính sách.
11. Chạy các test bất đồng bộ song song và cố ý dùng chung queue. Phân tích lỗi nhiễu test và sửa bằng context isolation/event ID.
12. Đo thời gian các bài test trước/sau khi chuyển sang event-driven waiting; kiểm tra số lần flaky trong nhiều lần chạy CI.

### Câu hỏi tự kiểm tra

- Vì sao `Thread.sleep(...)` không tạo quan hệ nhân quả giữa producer và consumer?
- `PollableChannel.receive(timeout)` khác sleep ở điểm nào?
- Khi nào dùng `CountDownLatch` thay vì `Awaitility`?
- Vì sao phải có tín hiệu hoàn tất trước khi assert “không có side effect”?
- Vì sao test `Aggregator` không nên mặc định FIFO khi các nhánh chạy trên executor khác nhau?
- Dùng `Clock.fixed(...)` có làm `TaskScheduler` của Spring Integration chạy nhanh hơn không?
- Một `ErrorMessage` không xuất hiện có thể do lỗi sync hay do cấu hình sai ở đâu?
- Khi retry, cần kiểm tra số lần xử lý theo ID nào để không nhận nhầm message?
- Vì sao Gateway timeout chưa kết luận nghiệp vụ đã thất bại?

## Tài liệu tham khảo

- [Spring Integration Reference — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html): công cụ kiểm thử Spring Integration và thiết lập test context.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `DirectChannel`, `ExecutorChannel` và `QueueChannel`.
- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): scheduler, thời gian trì hoãn và release message.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): lỗi đồng bộ và bất đồng bộ, `ErrorMessage`, error channels.
- [JUnit 5 User Guide — Timeouts](https://junit.org/junit5/docs/current/user-guide/#writing-tests-declarative-timeouts): bảo vệ test không treo với `@Timeout`.
- [Awaitility Documentation](https://github.com/awaitility/awaitility/wiki/Usage): chờ điều kiện bằng `await()` và các dạng assertion.
- [Java SE API — CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html): phối hợp thread bằng tín hiệu `countDown`/`await`.
