# Delay kết hợp retry hoặc scheduler trong Spring Integration

## 1. Vì sao cần kết hợp Delayer với retry và scheduler?

Một hệ thống đặt hàng có thể yêu cầu **chờ 3 giây** trước khi gọi dịch vụ đối tác. Nếu đối tác trả HTTP 503, hệ thống **thử lại tối đa 3 lần**, mỗi lần cách nhau một khoảng ngắn. Đây là hai quyết định riêng:

1. **Delay trước lần xử lý đầu tiên:** message chưa được phép đi tới consumer trước một thời điểm.
2. **Retry sau khi xử lý thất bại:** chỉ có lý do thử lại **sau khi** một lần thực hiện đã lỗi.

Trong Spring Integration, Delayer triển khai Enterprise Integration Pattern *Delayer*. `TaskScheduler` lên lịch các tác vụ phát message; còn retry có thể được cấu hình trên cơ chế phát lại của `DelayHandler` hoặc tại chính service handler bằng `RequestHandlerRetryAdvice`.

Trong module **SPRING_INTEGRATION_PATTERN**, lựa chọn này giúp kết hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation thành luồng ít phụ thuộc, dễ mở rộng và có thể quan sát từng nhánh. Bài học tập trung vào **khi nào dùng Delayer, retry, TaskScheduler hoặc scheduler nghiệp vụ**, cách phối hợp chúng và cách tránh xử lý trùng.

### Ví dụ timeline

| Thời điểm (tương đối) | Sự kiện |
| --- | --- |
| `t = 0 ms` | Producer gửi message vào Delayer |
| `t ≈ 3.000 ms` | Delayer release lần đầu, downstream trả lỗi |
| `t ≈ 3.500 ms` | Thử phát lần hai, tiếp tục lỗi |
| `t ≈ 4.000 ms` | Thử phát lần ba, downstream thành công |

Các mốc ở trên giả định `defaultDelay(3000L)`, `retryDelay(500L)`, `maxAttempts(3)` và thời gian chạy handler không đáng kể. Trên thực tế, thời gian xử lý, scheduler và độ trễ hệ thống có thể khiến kết quả muộn hơn.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant D as Delayer
    participant T as TaskScheduler
    participant C as Consumer
    P->>D: Message(eventId=evt-101)
    D->>T: Lên lịch sau 3 giây
    D-->>P: Trả quyền điều khiển
    T->>D: Đến hạn
    D->>C: Lần phát 1
    C--xD: Lỗi tạm thời
    Note over D,T: retryDelay = 500 ms
    D->>C: Lần phát 2
    C--xD: Lỗi tạm thời
    Note over D,T: retryDelay = 500 ms
    D->>C: Lần phát 3
    C-->>D: Thành công
~~~

> **Phân biệt:** *Delay* dời thời điểm một message được đưa tới downstream. *Retry* phản ứng với lỗi xảy ra khi xử lý. `TaskScheduler` là cơ chế chạy tác vụ đúng hạn, không phải một chính sách retry hay lịch kinh doanh theo cron.

## 2. Bốn cơ chế khác nhau và quan hệ giữa chúng

| Cơ chế | Điều kiện kích hoạt | Mục tiêu | Cấu hình tiêu biểu |
| --- | --- | --- | --- |
| **Delayer** | Message đến endpoint | Phát sau một khoảng/mốc xác định | `defaultDelay`, `delayExpression`, `messageGroupId` |
| **Retry của Delayer** | Phát message đã đến hạn bị lỗi | Thử lại việc chuyển message xuống downstream | `maxAttempts`, `retryDelay` |
| **Retry Advice của handler** | Endpoint được advice xử lý thất bại | Thử lại lời gọi service handler cụ thể | `RequestHandlerRetryAdvice` và `RetryTemplate` |
| **Scheduler nghiệp vụ** | Cron, chu kỳ, lịch ngày giờ hoặc workflow state | Tạo công việc theo một lịch nghiệp vụ | `@Scheduled`, Quartz hoặc workflow engine |

`TaskScheduler` của Spring là thành phần nền tảng được Delayer dùng để lên lịch thực thi. Nó không tự quyết định “thử lại tối đa bao nhiêu lần” hoặc “thứ Hai gửi hóa đơn cho ai”.

### Điều gì xảy ra khi một thông báo cần chờ 2 phút và có thể retry?

~~~mermaid
flowchart LR
    P[Producer] --> V[Validate payload và deadline]
    V --> D["Delayer<br/>chờ 2 phút"]
    D --> H{Service handler}
    H -->|Thành công| OK[Hoàn tất]
    H -->|Lỗi có thể thử lại| R[Retry có giới hạn]
    R --> H
    H -->|Lỗi vĩnh viễn/hết retry| E[Error flow / Dead letter]
~~~

Không áp dụng retry chỉ vì message còn đang chờ: chưa có lỗi nghiệp vụ để thử lại. Ngược lại, nếu một adapter vừa xử lý thành công rồi bị mất phản hồi, retry có thể tạo tác động trùng; lựa chọn `eventId` và idempotency trở nên bắt buộc.

## 3. Delayer tính thời gian chờ ban đầu

### 3.1. Delay tương đối

~~~java
.delay(delayer -> delayer
        .messageGroupId("orders.initial-delay.v1")
        .defaultDelay(3_000L))
~~~

Mọi message đi qua endpoint này chờ khoảng 3 giây kể từ lúc Delayer nhận nó, rồi đủ điều kiện phát. Tác vụ phát thực tế có thể chạy muộn hơn do scheduler hoặc máy chủ bận.

### 3.2. Delay động theo message

~~~java
.delay(delayer -> delayer
        .messageGroupId("orders.dynamic-delay.v1")
        .defaultDelay(3_000L)
        .delayExpression("headers['delayMs']"))
~~~

Producer có thể cung cấp `delayMs = 250L` cho đơn ưu tiên hoặc `delayMs = 10_000L` cho đơn thường. Nếu biểu thức trả về `null` vì không có header, Delayer dùng mặc định.

### 3.3. Delay tới thời điểm tuyệt đối

Delayer cũng có thể nhận giá trị `java.util.Date` từ biểu thức:

~~~java
MessageBuilder.withPayload("REMINDER-101")
        .setHeader("deliverAt",
                java.util.Date.from(java.time.Instant.now().plusSeconds(30)))
        .build();
~~~

Kết hợp với:

~~~java
.delay(delayer -> delayer
        .messageGroupId("reminders.absolute-delay.v1")
        .defaultDelay(1_000L)
        .delayExpression("headers['deliverAt']"))
~~~

**Số `Long` nghĩa là số mili giây chờ tương đối; `Date` nghĩa là mốc tuyệt đối.** Đừng gửi epoch milliseconds dưới dạng `Long` mà mong framework tự hiểu đó là thời gian trên đồng hồ. Nếu mốc `Date` đã ở quá khứ, message đã đến hạn và có thể được chuyển tiếp ngay.

## 4. Retry thuộc giai đoạn release của Delayer

Với độ trễ dương, Delayer lưu message đang chờ và giao scheduler tác vụ phát về sau. Khi đến hạn, Delayer gửi message tới output channel. Nếu thao tác **phát tới downstream** thất bại, có thể cấu hình:

~~~java
.delay(delayer -> delayer
        .messageGroupId("orders.delivery.delayer.v1")
        .defaultDelay(800L)
        .maxAttempts(3)
        .retryDelay(250L))
~~~

| Thuộc tính | Vai trò |
| --- | --- |
| `defaultDelay(800L)` | Chờ trước **lần phát đầu** |
| `maxAttempts(3)` | Giới hạn **tổng số lần thử phát** theo chính sách Delayer |
| `retryDelay(250L)` | Khoảng chờ giữa các lần thử sau lỗi |
| `messageGroupId(...)` | Nhóm lưu các message đang chờ của Delayer |

Ở ví dụ này, Delayer có thể phát lần đầu sau khoảng 800 ms; nếu lỗi, nó thử lại tối đa theo cấu hình. **`retryDelay` không thay thế `defaultDelay`**, và không cộng vào mỗi message mới nếu chưa có lần phát thất bại.

### Cần biết exception có truyền về Delayer hay không

Với luồng đồng bộ sau Delayer, ví dụ `DirectChannel → Service Activator`, exception do handler ném có thể truyền ngược vào thao tác release. Delayer sẽ biết lần phát đó thất bại và có thể áp dụng retry của nó.

Nếu Delayer phát thành công vào một `QueueChannel`, `ExecutorChannel` hoặc broker rồi consumer **xử lý lỗi về sau**, thao tác bàn giao message có thể đã được coi là thành công. Khi đó Delayer **không tự nhận biết** toàn bộ lỗi bất đồng bộ ở consumer.

| Cấu trúc phía sau Delayer | Retry của Delayer có thể bao phủ |
| --- | --- |
| `DirectChannel → handler` đồng bộ | Exception của handler truyền trực tiếp qua lần phát |
| `QueueChannel → poller → handler` | Thường chỉ bao phủ thao tác gửi vào queue; lỗi ở poller cần chính sách riêng |
| `ExecutorChannel → handler` | Thao tác bàn giao vào executor; lỗi ở thread khác cần error flow/retry khác |
| Adapter gửi tới broker | Bảo đảm của bước gửi/ack vào broker theo adapter; không bao phủ xử lý của consumer ngoài broker |

**Lựa chọn vị trí retry phụ thuộc ranh giới xác nhận.** Hệ thống cần quyết định “thành công” nghĩa là đã đưa vào channel, broker nhận, hay dịch vụ bên ngoài đã hoàn thành.

## 5. Ví dụ Java DSL hoàn chỉnh: retry khi phát sau delay

Flow sau dùng một `DirectChannel` đầu vào, Delayer với retry giới hạn và một handler mô phỏng lỗi tạm thời trong hai lần đầu. Vì handler nằm đồng bộ sau Delayer, lỗi được truyền về lần phát; lần thứ ba thành công và message đi đến `QueueChannel`.

**Phụ thuộc:** `spring-boot-starter-integration` cho Java DSL; `spring-boot-starter-test` cho bài kiểm thử ở mục tiếp theo.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class DelayRetryFlowConfig {

    @Bean("delivery.in")
    public MessageChannel deliveryInput() {
        return new DirectChannel();
    }

    @Bean("delivery.out")
    public PollableChannel deliveryOutput() {
        return new QueueChannel();
    }

    @Bean
    public AtomicInteger deliveryAttempts() {
        return new AtomicInteger();
    }

    @Bean
    public IntegrationFlow delayedDeliveryFlow(AtomicInteger deliveryAttempts) {
        return IntegrationFlow.from("delivery.in")
                .delay(d -> d
                        .messageGroupId("orders.delayed-delivery.v1")
                        .defaultDelay(800L)
                        .maxAttempts(3)
                        .retryDelay(250L))
                .handle(String.class, (payload, headers) -> {
                    int attempt = deliveryAttempts.incrementAndGet();
                    if (attempt < 3) {
                        throw new IllegalStateException(
                                "Temporary partner failure: attempt=" + attempt);
                    }
                    return payload;
                })
                .channel("delivery.out")
                .get();
    }
}
~~~

Trong ví dụ học tập này, bộ đếm `AtomicInteger` đếm tổng số lần handler được gọi **trong một application context**. Nó không phải cơ chế lưu số lần thử bền vững cho nhiều message hay nhiều instance. Với chương trình thật, việc retry phải được thiết kế theo từng message và từng lỗi.

Producer:

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public boolean publish(MessageChannel deliveryInput) {
    return deliveryInput.send(
            MessageBuilder.withPayload("ORDER-101")
                    .setHeader("eventId", "notify:order-101:v1")
                    .setHeader("correlationId", "order-101")
                    .build());
}
~~~

Tham số `deliveryInput` cần là bean `delivery.in` của Spring. `send(...)` trả về trước khi bước handler thành công nếu delay dương đã được lên lịch; đó không phải xác nhận nghiệp vụ hoàn tất.

## 6. Kiểm thử delay ban đầu và retry

Kiểm thử cần xác nhận:

1. Message **không ra output trước hạn**.
2. Handler bị gọi đúng ba lần trong kịch bản lỗi tạm thời.
3. Chỉ có message được phát thành công mới đến `delivery.out`.
4. Thời gian được đo tương đối bằng `System.nanoTime()`, không so khớp mili giây tuyệt đối.

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(DelayRetryFlowConfig.class)
class DelayRetryFlowTest {

    @Autowired
    @Qualifier("delivery.in")
    MessageChannel input;

    @Autowired
    @Qualifier("delivery.out")
    PollableChannel output;

    @Autowired
    AtomicInteger deliveryAttempts;

    @Test
    void retriesAfterInitialDelayAndEventuallyReleases() {
        long started = System.nanoTime();
        assertTrue(input.send(MessageBuilder.withPayload("ORDER-101")
                .setHeader("eventId", "notify:order-101:v1")
                .build()));

        assertNull(output.receive(100), "Không được phát trước hạn");

        Message<?> released = output.receive(5_000);
        assertNotNull(released, "Retry cuối cùng cần thành công");
        assertEquals("ORDER-101", released.getPayload());
        assertEquals("notify:order-101:v1",
                released.getHeaders().get("eventId"));
        assertEquals(3, deliveryAttempts.get());

        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started);
        assertTrue(elapsedMs >= 800L);
    }
}
~~~

Đây là bài kiểm thử chức năng tại endpoint. Nó không chứng minh lời gọi API bên ngoài có bảo đảm exactly-once. Trong CI, cần tách application context cho các test dùng `AtomicInteger` và `QueueChannel` chung, đồng thời cho timeout đủ rộng khi scheduler chịu tải.

### Những trường hợp nên kiểm thử bổ sung

- Handler thành công ngay lần đầu: không xuất hiện retry vô ích.
- Handler luôn lỗi: kiểm tra behavior sau khi hết `maxAttempts`, error flow và dữ liệu còn trong store.
- Delay bằng `0L`: downstream có thể chạy đồng bộ, exception có thể ảnh hưởng trực tiếp đến producer.
- Một message đi qua `QueueChannel` rồi lỗi ở consumer: retry của Delayer không tự bắt được lỗi downstream đó.
- Nhiều message đồng thời chờ: kiểm tra số lần retry **theo từng eventId**, không dùng bộ đếm chung như demo.
- Restart khi message đang chờ hoặc khi retry chưa hoàn tất: kiểm tra khôi phục từ persistent store.

## 7. Khi nào dùng `RequestHandlerRetryAdvice` thay vì retry của Delayer?

Nếu yêu cầu là “khi service gọi đối tác thất bại thì thử gọi service đó lại”, có thể gắn `RequestHandlerRetryAdvice` tại **handler cụ thể**. Cách này tách chính sách thử lại khỏi việc message có từng đi qua Delayer hay không.

Ví dụ khai báo advice dùng Spring Retry:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.backoff.FixedBackOffPolicy;
import org.springframework.retry.support.RetryTemplate;

@Bean
public RequestHandlerRetryAdvice outboundRetryAdvice() {
    RetryTemplate retry = new RetryTemplate();
    retry.setRetryPolicy(new SimpleRetryPolicy(3));

    FixedBackOffPolicy backOff = new FixedBackOffPolicy();
    backOff.setBackOffPeriod(300L);
    retry.setBackOffPolicy(backOff);

    RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
    advice.setRetryTemplate(retry);
    return advice;
}
~~~

Đoạn trên là **method `@Bean` đặt trong class `@Configuration`**, cần thêm dependency Spring Retry tương thích với dự án. Để gắn advice vào một endpoint cụ thể:

~~~java
// Minh họa đoạn DSL đặt trong một IntegrationFlow:
.handle(String.class, (payload, headers) -> {
    deliveryService.deliver(payload);
    return payload;
}, endpoint -> endpoint.advice(outboundRetryAdvice))
~~~

Đoạn DSL giả định đã có một bean/service `deliveryService` và biến `outboundRetryAdvice` được inject, nên không phải flow chạy độc lập. Mục đích là minh họa: retry được áp dụng **trực tiếp lên thao tác handler**, kể cả khi trước đó không có Delayer.

### Vì sao không nên chồng retry tùy tiện?

Nếu Delayer retry 3 lần mà mỗi lần lại gọi một service handler có `RequestHandlerRetryAdvice` retry tối đa 3 lần, cùng một sự kiện có thể bị gọi tới đối tác **tối đa 9 lần** trong một số tổ hợp lỗi. Con số thực tế phụ thuộc error flow và kiểu exception, nhưng rủi ro nhân số lần thử là có thật.

Đặc biệt:

- **Delayer retry** giúp xử lý lỗi *phát message đã đến hạn*.
- **Retry advice** giúp giới hạn lỗi *ở handler* và có thể có recovery callback riêng.
- Một **message broker consumer** có thể có policy retry/redelivery độc lập.
- HTTP client có thể tự retry ở lớp mạng.

Hãy chỉ định một tầng **chịu trách nhiệm chính** cho mỗi loại lỗi. Ghi rõ tổng số lần thử tối đa, khả năng backoff và khóa idempotency dùng xuyên các tầng.

## 8. TaskScheduler: lên lịch không đồng nghĩa xử lý nghiệp vụ

Delayer sử dụng `TaskScheduler` để gọi tác vụ phát khi đến hạn. Cần phân biệt:

| Thành phần | Chức năng | Không tự bảo đảm |
| --- | --- | --- |
| `TaskScheduler` | Thực thi một `Runnable` tại thời điểm hoặc sau delay | Message bền vững qua restart; retry HTTP; exactly-once |
| `MessageGroupStore` | Giữ message đang chờ theo group | Tự chạy tác vụ đúng hạn |
| `DelayHandler` | Kết nối chính sách delay, store và scheduler | Mọi side effect downstream thành công |
| `QueueChannel` | Buffer message đã được gửi vào channel | Deadline nghiệp vụ hoặc retry của consumer |
| `RequestHandlerRetryAdvice` | Retry tại handler được bọc advice | Hẹn giờ một sự kiện lần đầu trong tương lai |

### Ví dụ cấu hình một pool scheduler

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Bean(name = "taskScheduler")
public ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(6);
    scheduler.setThreadNamePrefix("integration-delay-");
    return scheduler;
}
~~~

Đây là **bean cấu hình thay thế cho scheduler được quản lý bởi framework** khi ứng dụng sử dụng tên bean này. Nên rà soát scheduler hiện có của Spring Boot/Spring Integration để tránh tạo bean xung đột hoặc thay đổi scheduler của các endpoint khác ngoài dự kiến. Spring quản lý vòng đời và khởi tạo `ThreadPoolTaskScheduler` khi nó là một bean.

**Tăng kích thước pool không làm đảm bảo xử lý nhanh hơn tuyến tính.** Với `DirectChannel` downstream, scheduler thread có thể bị chiếm trong thời gian handler gọi REST API hoặc retry/backoff. Nếu 6 thread đều bị chiếm, những delayed message khác đã đến hạn có thể được phát **muộn**.

### Scheduler và retry có thể cạnh tranh tài nguyên

~~~mermaid
flowchart TB
    S["TaskScheduler: 6 threads"] --> A["Message A: release + retry"]
    S --> B["Message B: release + retry"]
    S --> C["Message C: release + handler chậm"]
    S --> D["Các message đến hạn khác"]
    A --> E[(External service)]
    B --> E
    C --> E
    D --> E
~~~

Để giảm nghẽn:

1. Đặt timeout cho outbound HTTP/DB call, tránh block vô hạn.
2. Thiết kế retry có giới hạn và phân loại lỗi retryable.
3. Đo thời gian scheduler bị chiếm, release lag và hàng đợi đang chờ.
4. Tách giai đoạn release khỏi xử lý nghiệp vụ dài nếu cần, **đồng thời** thêm retry/error handling ở tầng consumer mới, vì exception không còn tự truyền tới Delayer.
5. Xem xét bulkhead, rate limiter hoặc broker để bảo vệ đối tác; Delayer không thay thế kiểm soát throughput.

## 9. Khi nào dùng scheduler nghiệp vụ hoặc `@Scheduled`?

Delayer đặc biệt phù hợp khi **một message đã tồn tại** và phải được đưa tới bước sau vào một thời điểm tương lai. Scheduler nghiệp vụ hoặc cron thích hợp khi hệ thống cần **tạo tác vụ mới theo lịch**.

| Yêu cầu | Phương án phù hợp hơn |
| --- | --- |
| Mỗi đơn hàng nhận message, chờ 5 giây rồi kiểm tra thanh toán | Delayer |
| Một message có header `deliverAt` cho thời điểm cụ thể | Delayer với `Date`, nếu việc lưu/lập lịch đáp ứng yêu cầu |
| Mỗi ngày 08:00 quét các hóa đơn chưa trả | Scheduler nghiệp vụ, `@Scheduled` hoặc job scheduler |
| Hàng triệu lịch hẹn cần sửa/xóa và truy vấn trạng thái | Scheduler/workflow engine hoặc store lịch chuyên dụng |
| Khi REST API trả HTTP 503 thì retry có backoff | Retry advice, consumer retry hoặc Delayer retry tùy ranh giới lỗi |
| Giới hạn tối đa 50 request/giây tới đối tác | Rate limiter, không phải một delay cố định cho mọi message |

Ví dụ `@Scheduled` tạo một batch request định kỳ:

~~~java
import org.springframework.scheduling.annotation.Scheduled;

// Minh họa method đặt trong một Spring bean đã bật @EnableScheduling.
@Scheduled(cron = "0 0 8 * * *", zone = "Asia/Ho_Chi_Minh")
public void createMorningReminderRequests() {
    reminderRequestService.enqueueEligibleReminders();
}
~~~

Đoạn này cần một bean `reminderRequestService` trong ứng dụng và cơ chế tránh chạy job trùng khi deploy nhiều instance. `@Scheduled` **không mặc nhiên lưu công việc đang chờ qua restart**, không làm thay persistence của Delayer, và không tự có cơ chế retry/error channel của từng request.

Nếu job tạo ra từng reminder message, có thể thiết kế:

~~~mermaid
flowchart LR
    C["Cron job 08:00"] --> P["Producer / Outbox"]
    P --> D["Delayer: deadline riêng từng message"]
    D --> F[Filter trạng thái hiện tại]
    F --> H[Consumer + retry có giới hạn]
    H --> A[Audit / result store]
~~~

## 10. Retry, error channel và quyết định dừng

Khi Delayer phát message bị lỗi, có thể định tuyến một `ErrorMessage` sang kênh chuyên xử lý:

~~~java
.delay(d -> d
        .messageGroupId("orders.delayed-delivery.v1")
        .defaultDelay(800L)
        .maxAttempts(3)
        .retryDelay(250L)
        .delayedMessageErrorChannel("orders.delay.errors"))
~~~

Đây là đoạn cấu hình **thay thế phần `.delay(...)`**, không phải flow đầy đủ. Cần khai báo channel `orders.delay.errors` và flow xử lý `ErrorMessage`.

Đặc biệt, **hành vi của error flow ảnh hưởng đến retry**:

- Nếu error handler xử lý lỗi và **kết thúc bình thường**, Delayer có thể xem lần phát đã được xử lý; không nên mặc định nó sẽ tiếp tục thử lại cho đủ `maxAttempts`.
- Nếu error handler **ném exception trở lại**, Delayer có thể tiếp tục cơ chế retry theo cấu hình cho đến giới hạn.
- Nếu lỗi không thể phục hồi, error flow nên ghi vào kho lỗi bền vững, phát cảnh báo hoặc chuyển đến nhánh xử lý thủ công theo chính sách.

Một minh họa handler lỗi:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.support.ErrorMessage;

public class DelayedErrorHandler {

    @ServiceActivator(inputChannel = "orders.delay.errors")
    public void handle(ErrorMessage error) {
        Throwable cause = error.getPayload();
        Object original = error.getOriginalMessage();

        // TODO: persist vào dead-letter/quarantine store có độ tin cậy phù hợp.
        // TODO: liên kết eventId/correlationId với hệ thống giám sát.
        System.err.println("Failed release: " + cause);
        System.err.println("Original: " + original);

        // Return bình thường = chính sách đã xử lý lỗi, không chủ động retry.
    }
}
~~~

Để chạy đoạn handler, đăng ký lớp làm bean Spring và khai báo channel tương ứng. `System.err` chỉ để mô tả và không phải dead-letter store; production cần lưu thông tin lỗi bền vững và chính sách replay có kiểm soát.

### Không retry vô hạn

Các nguyên nhân như payload không hợp lệ, quyền truy cập bị từ chối hoặc đơn hàng đã bị hủy thường không cải thiện khi gửi lại y nguyên. Với lỗi mạng tạm thời hoặc dịch vụ 503, retry giới hạn là hợp lý hơn. Sau khi hết lần thử:

1. Đánh dấu message cần điều tra hoặc chuyển vào dead-letter store.
2. Lưu `eventId`, `correlationId`, kiểu lỗi và số lần thử.
3. Có cảnh báo theo SLA và quy trình replay chỉ khi nguyên nhân đã được khắc phục.
4. Kiểm tra trạng thái nghiệp vụ trước khi thử lại để tránh side effect lỗi thời.

## 11. Persistence, transaction và restart giữa lúc retry

Với store trong bộ nhớ, message chưa đến hạn có thể mất khi JVM dừng. Nếu message quan trọng, sử dụng `MessageGroupStore` bền vững như `JdbcMessageStore` và giữ `messageGroupId` ổn định:

~~~java
.delay(d -> d
        .messageGroupId("orders.delayed-delivery.v1")
        .messageStore(jdbcMessageStore)
        .defaultDelay(3_000L)
        .maxAttempts(3)
        .retryDelay(500L))
~~~

Đoạn DSL giả định `jdbcMessageStore` đã có bean, `DataSource`, schema và transaction thích hợp.

**Phân biệt ba trạng thái**:

- Message đang chờ trong Delayer: persistence có thể giúp khôi phục lịch sau restart.
- Delayer đã gửi message vào hàng đợi/adapter phía sau: việc giữ message từ thời điểm này phụ thuộc **đích nhận** và contract handoff, không chỉ vào Delayer store.
- Consumer đã tạo side effect nhưng chưa xác nhận: retry/restart có nguy cơ xử lý trùng.

Trong transaction JDBC, khi lỗi release dẫn đến rollback, message có thể vẫn còn trong store sau khi retry đã hết **nhưng không còn tác vụ được lên lịch tự động**. Cần test trực tiếp cơ chế recovery/rescheduling của phiên bản đang dùng. **Một row còn trong database không đồng nghĩa đang có lịch phát hợp lệ**.

### Tại sao cần `eventId` ổn định?

Một sự kiện có thể được gửi lại bằng một `Message` mới với UUID khác. `MessageHeaders.ID` không đủ để bảo vệ side effect. Nên dùng khóa nghiệp vụ như `eventId = notify:order-101:v1` ở producer, giữ nó qua Router/Transformer/Delayer và xử lý idempotent tại consumer.

~~~java
// Pseudocode minh họa: claim phải là thao tác atomic trong durable store.
if (idempotencyStore.tryClaim(eventId)) {
    partnerService.deliverWithIdempotencyKey(eventId, payload);
    idempotencyStore.markCompleted(eventId);
}
~~~

Pseudocode trên chưa xử lý toàn bộ cửa sổ lỗi khi crash giữa `tryClaim` và `markCompleted`. Trong production, cân nhắc trạng thái claim có lease, transaction, inbox/outbox và idempotency key phía đối tác nếu có hỗ trợ.

Không dùng `messageGroupId` làm khóa chống trùng: tất cả message trong cùng Delayer có thể dùng chung group ID.

## 12. Timeout, backpressure và vận hành khi nhiều message đến hạn

Một Delayer có delay cố định 10 giây **không phải rate limiter**. Nếu 10.000 message đến gần như đồng thời, chúng có thể cùng đủ điều kiện phát sau 10 giây, gây tải cho scheduler, message store, downstream hoặc dịch vụ bên ngoài.

Đặt các timeout khác nhau theo tầng:

| Timeout / khoảng chờ | Tác động |
| --- | --- |
| Delayer delay | Dời thời điểm message bắt đầu được phát |
| `retryDelay` | Chờ giữa các lần thử sau lỗi release |
| HTTP connect/read timeout | Không để một lời gọi mạng chiếm thread vô hạn |
| Gateway `replyTimeout` | Giới hạn thời gian caller chờ reply; không tự hủy delayed message |
| Poller `receiveTimeout` | Giới hạn thời gian poll chờ message |
| Business expiry | Deadline sau đó hành động không còn hợp lệ, phải được kiểm tra ở tầng nghiệp vụ |

Đừng chỉ dựa vào `Thread.sleep(...)` trong handler để tạo retry: cách này giữ thread trong khi đợi và dễ làm nghẽn pool. Dùng chính sách retry có giới hạn, đặt timeout cho lời gọi I/O, bảo vệ downstream bằng rate limiter/bulkhead khi cần.

**Đối với message quá hạn sau restart:** trước khi retry, Filter hoặc handler nên kiểm tra lại trạng thái hiện tại của đơn hàng. Một reminder không còn cần thiết không nên bị gửi chỉ vì nó vẫn nằm trong store.

## 13. Observability: đo lịch phát, retry và kết quả riêng

Mỗi message nên có `eventId`, `correlationId` và các mốc thời gian:

~~~text
eventId=notify:order-101:v1
correlationId=order-101
delayGroup=orders.delayed-delivery.v1
receivedAt=2026-11-21T10:00:00Z
dueAt=2026-11-21T10:00:03Z
releasedAt=2026-11-21T10:00:03.140Z
releaseLagMs=140
deliveryAttempts=3
retryDelayMs=500
businessCompletedAt=2026-11-21T10:00:04.510Z
outcome=SUCCESS_AFTER_RETRY
~~~

Các trường trên là **một log do ứng dụng chủ động xây dựng**, không phải Spring Integration tự cung cấp toàn bộ.

Nên theo dõi:

- `pendingCount`, `oldestPendingAge`: số lượng/tuổi message đang chờ.
- `releaseLagMs`: thời gian phát thực tế trừ mốc đến hạn.
- `retryAttempts`, `retryExhaustedCount`: áp lực và hiệu quả retry.
- `deadLetterCount`: số sự kiện chuyển sang nhánh lỗi.
- `handlerDurationMs`, `schedulerActiveThreads`: phát hiện pool bị block.
- `duplicateSuppressedCount`: số lần consumer ngăn side effect trùng theo `eventId`.
- `businessCompletionLagMs`: mốc hoàn thành nghiệp vụ trừ deadline của Delayer.

| Triệu chứng | Điều cần kiểm tra |
| --- | --- |
| Producer gửi thành công nhưng consumer chưa chạy | Message vẫn đang chờ? Scheduler có hoạt động? |
| Retry Delayer không xảy ra | Exception có truyền ngược qua output channel không, hay bị tách async? |
| Retry xảy ra nhiều hơn dự kiến | Có chồng Delayer retry, Retry Advice, HTTP client retry và broker redelivery? |
| Có message trong store nhưng không phát | Recovery, transaction rollback, retry exhausted, group ID |
| Nhiều message đến hạn nhưng phát muộn | Pool scheduler, blocking handler, DB và concurrency |
| Gateway timeout dù task cuối cùng thành công | Hợp đồng async, replyTimeout và kết quả xử lý theo eventId |
| Cùng notification được gửi hai lần | Idempotency, side effect sau timeout, nhiều instance và replay |

## 14. Bài tập thực hành và câu hỏi tự kiểm tra

1. Cấu hình Delayer delay 1 giây với `maxAttempts(3)` và `retryDelay(200L)`. Tạo handler lỗi trong hai lần đầu rồi thành công; ghi thời điểm và số lần gọi.
2. Đổi handler sang luôn ném exception. Quan sát khi retry hết lần, rồi bổ sung error channel và dead-letter store.
3. Thêm `RequestHandlerRetryAdvice` vào handler đang đứng sau Delayer retry. Đếm tổng số lần gọi nếu mỗi tầng retry 3 lần; giải thích vì sao cần tránh chồng policy.
4. Thay `DirectChannel` giữa Delayer và consumer bằng `ExecutorChannel`. Xác định lỗi của consumer được xử lý ở đâu, và vì sao Delayer có thể không biết.
5. Tạo 100 message cùng delay 2 giây, dùng một handler giả lập xử lý 500 ms. Đo `releaseLagMs` theo kích thước scheduler pool.
6. Dùng `JdbcMessageStore`, restart khi một message chưa đến hạn. Xác minh message còn chờ được lên lịch lại với group ID ổn định.
7. Mô phỏng HTTP timeout sau khi dịch vụ đích đã xử lý thành công. Sử dụng `eventId` để xây dựng consumer idempotent.
8. Tạo cron job mỗi ngày sinh message theo lịch của khách. Giải thích trách nhiệm của cron job so với trách nhiệm của Delayer.
9. Cho Gateway chờ 500 ms trong khi Delayer đợi 2 giây. Thiết kế một ACK bất đồng bộ và cách tra cứu kết quả sau này.
10. Thêm Filter sau Delayer để bỏ qua thông báo đã hết hiệu lực khi message được khôi phục sau downtime.

**Câu hỏi tự kiểm tra:** Delay ban đầu khác retryDelay ở đâu? TaskScheduler có thay thế persistence không? Khi nào Delayer thấy lỗi của handler? Tại sao `ExecutorChannel` thay đổi ranh giới retry? Retry Advice nên đặt ở đâu? Chồng hai bộ retry gây rủi ro gì? Vì sao một message còn trong store có thể không có tác vụ phát? Khi một API đã thành công nhưng mất phản hồi, cần dựa vào khóa gì để ngăn side effect trùng?

## Tài liệu tham khảo

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): Delayer, `TaskScheduler`, `maxAttempts`, `retryDelay`, error channel và lưu trữ.
- [Spring Integration Reference — Retry Advice](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html): advice trên message handler, gồm chính sách retry.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, error channel và lỗi bất đồng bộ.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): `MessageGroupStore`, persistence và khôi phục message chờ.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskScheduler`, `ThreadPoolTaskScheduler` và `@Scheduled`.
- [Spring Retry Reference](https://docs.spring.io/spring-retry/reference/): `RetryTemplate`, retry policy và backoff.
