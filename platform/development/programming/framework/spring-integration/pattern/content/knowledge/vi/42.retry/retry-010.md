# Retry kết hợp error channel trong Spring Integration

## 1. Bài toán: retry ở đâu và lỗi cuối cùng đi đâu?

Một hệ thống nhận sự kiện `OrderPaid` và phải gọi API xuất hóa đơn. API đối tác đôi khi trả lỗi HTTP 503, nhưng cũng có thể từ chối vĩnh viễn nếu dữ liệu đơn hàng không hợp lệ. Nếu ứng dụng chỉ bắt exception rồi bỏ qua, giao dịch có thể bị mất. Nếu thử lại vô hạn, luồng bị kẹt và có thể làm quá tải đối tác.

Thiết kế mong muốn là:

1. **Thử lại có giới hạn** khi một lỗi có khả năng phục hồi xảy ra.
2. Có **backoff** để không gửi liên tục vào dịch vụ đang lỗi.
3. Sau khi hết số lần thử, tạo **ErrorMessage** để chuyển sang kênh lỗi có thể theo dõi.
4. Ở kênh lỗi, ghi nhận `eventId`, nguyên nhân, số lần thử và đưa vào quy trình khắc phục hoặc dead-letter/quarantine.
5. Khi thử lại hoặc replay, hạn chế **tác động nghiệp vụ trùng**.

Trong module **SPRING_INTEGRATION_PATTERN**, bài này kết hợp Enterprise Integration Patterns với các flow Router, Filter, Transformer, Splitter, Aggregator, Gateway và correlation. Mục tiêu không chỉ là “thử lại cho đến khi chạy được”, mà là tạo luồng message ít phụ thuộc, có đường thành công/đường lỗi minh bạch, kiểm thử được từng nhánh và không âm thầm làm mất dữ liệu.

~~~mermaid
flowchart LR
    P[Producer] --> F[Validation / Filter]
    F --> H["Service handler<br/>Retry Advice"]
    H -->|Thành công| S[Success channel]
    H -->|Lỗi thử lại được| H
    H -->|Hết retry| R[Recovery callback]
    R --> E["ErrorMessage<br/>Error channel"]
    E --> D["Dead letter / Audit"]
    D --> O[Điều tra và replay có kiểm soát]
~~~

> **Quy tắc quan trọng:** retry và error channel không thay thế nhau. Retry là **chính sách phản ứng với lỗi**. Error channel là **đường chuyển thông tin lỗi** để endpoint khác xử lý, ghi nhận hoặc quyết định hướng khắc phục.

## 2. Những khái niệm cần phân biệt

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Retry attempt** | Một lần thực thi lại thao tác lỗi | Gọi API xuất hóa đơn lần 2 |
| **Retry policy** | Quyết định lỗi nào được thử lại và tối đa bao nhiêu lần | 3 lần với lỗi kết nối tạm thời |
| **Backoff policy** | Khoảng nghỉ giữa các lần thử | 200 ms rồi tăng dần |
| **Recovery callback** | Hành động khi retry không thể tiếp tục | Chuyển lỗi sang kênh xử lý |
| **ErrorMessage** | Message chứa `Throwable` trong payload | Exception + thông tin message thất bại |
| **Error channel** | `MessageChannel` nhận `ErrorMessage` | `orders.retry.exhausted` |
| **Dead-letter/quarantine** | Nơi giữ dữ liệu lỗi có thể điều tra/replay | Bảng DB hoặc topic lỗi |
| **Idempotency key** | ID ổn định của thao tác nghiệp vụ | `invoice:order-501:v1` |

### Số lần thử bao gồm cả lần đầu

Với `SimpleRetryPolicy(3)`, tối đa **3 lần thực thi handler tổng cộng**, không phải một lần đầu cộng ba lần retry.

~~~text
Attempt 1: exception -> backoff
Attempt 2: exception -> backoff
Attempt 3: exception -> recovery callback
~~~

Nếu lần thứ hai thành công thì không còn lần thứ ba. Nếu lỗi được phân loại là không thể retry, policy có thể đưa thẳng sang recovery/đường lỗi mà không thử lại.

### Retry không phải là phát lại vô hạn

Một hệ thống xử lý message lâu dài cần **điểm kết thúc rõ ràng** khi không thể xử lý. Ví dụ:

- HTTP 503 hoặc timeout tạm thời: có thể retry có giới hạn, tùy tính idempotent của thao tác.
- HTTP 400 do dữ liệu sai: thường không nên retry y nguyên dữ liệu.
- HTTP timeout sau khi đối tác **đã xử lý thành công**: trạng thái không chắc chắn; nên tra cứu hoặc retry bằng idempotency key để tránh xuất hai hóa đơn.

## 3. Lỗi đồng bộ và bất đồng bộ đi vào error channel khác nhau ra sao?

### 3.1. Handler đồng bộ trên `DirectChannel`

`DirectChannel` gọi subscriber trên thread đang gửi message. Nếu handler ném exception và không có retry/recovery bao quanh, exception thường truyền ngược về caller:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as DirectChannel
    participant H as Handler
    P->>C: send(message)
    C->>H: invoke(message)
    H--xC: throw exception
    C--xP: exception tới caller
~~~

Trong đường **đồng bộ**, không nên cho rằng exception sẽ tự động đi tới global `errorChannel`. Muốn gom lỗi vào kênh xử lý, cần **chủ động cấu hình** một cơ chế như `RequestHandlerRetryAdvice` với `ErrorMessageSendingRecoverer`, hoặc bắt/định tuyến lỗi tại ranh giới gọi phù hợp.

### 3.2. Executor, poller và các điểm bất đồng bộ

Với `ExecutorChannel` hoặc các endpoint do poller chạy, code của producer có thể đã trả về khi handler phía sau mới gặp lỗi. Một số thành phần bất đồng bộ của Spring Integration sử dụng `ErrorMessagePublisher`/`MessagePublishingErrorHandler` để chuyển exception thành `ErrorMessage` gửi qua error channel được chỉ định, hoặc fallback sang `errorChannel` chung.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant E as ExecutorChannel
    participant H as Handler
    participant X as ErrorChannel
    P->>E: send(message)
    E-->>P: Accepted
    E->>H: chạy ở thread khác
    H--xE: exception
    E->>X: ErrorMessage theo error handler được cấu hình
~~~

**Đừng suy ra mọi lỗi bất đồng bộ đều luôn đi tới một kênh cụ thể.** Hành vi còn phụ thuộc endpoint, error handler, header `errorChannel`, loại channel và cấu hình integration. Với các adapter hay consumer ngoài broker, phải xem contract xác nhận và retry/redelivery của chính adapter/broker.

### 3.3. Ba tên dễ gây nhầm lẫn

| Cơ chế | Vị trí sử dụng |
| --- | --- |
| `errorChannel` toàn cục | Kênh lỗi mặc định của Spring Integration khi một publisher/handler bất đồng bộ sử dụng nó |
| Header `errorChannel` | Message có thể chỉ định kênh lỗi, nếu thành phần phát lỗi tôn trọng header đó |
| `orders.retry.exhausted` riêng | Kênh **recovery** do ứng dụng chỉ định, ví dụ với `ErrorMessageSendingRecoverer` |

Một kênh được đặt tên `orders.retry.exhausted` không tự nhận lỗi nếu không có thành phần nào gửi `ErrorMessage` vào đó. Ngược lại, global `errorChannel` không tự động đóng vai trò kho dead-letter bền vững.

## 4. Hai cách tổ chức retry phổ biến

### Cách A — Retry tại chính handler

Đặt `RequestHandlerRetryAdvice` ở Service Activator hoặc outbound handler. Retry chạy quanh lời gọi handler đó, và có thể dùng `ErrorMessageSendingRecoverer` làm recovery callback.

~~~mermaid
flowchart LR
    A[Inbound channel] --> B["Handler + RetryAdvice"]
    B -->|Success| C[Output channel]
    B -->|Exhausted| D[ErrorMessageSendingRecoverer]
    D --> E[Recovery channel]
~~~

Thích hợp khi exception xuất hiện **trong lời gọi handler đồng bộ** và muốn tách xử lý lỗi cuối cùng khỏi producer. Lưu ý: tùy backoff, các lần retry có thể giữ thread của bên đang thực thi handler.

### Cách B — Retry ở consumer hoặc nguồn bất đồng bộ

Nếu một message đã được chuyển vào `QueueChannel`/broker, người nhận ở phía sau cần retry và error flow **của chính nó**:

~~~mermaid
flowchart LR
    A[Producer] --> Q[Queue / Broker]
    Q --> P[Poller / Consumer]
    P --> H[Handler + retry]
    H -->|Success| S[ACK / Complete]
    H -->|Failure exhausted| E[Error channel / DLQ]
~~~

Không nên đặt một Retry Advice ở phía **trước queue** và mong nó xử lý exception phát sinh **sau** khi một consumer khác lấy message ra.

## 5. Ví dụ hoàn chỉnh: `RequestHandlerRetryAdvice` + `ErrorMessageSendingRecoverer`

Ví dụ học tập này minh họa một flow có hai đầu ra:

- `orders.success`: handler thành công sau tối đa ba lần thử.
- `orders.retry.exhausted`: recovery callback phát một `ErrorMessage` sau khi retry hết lần.

Các phần của ví dụ đặt trong một `@Configuration` để có thể chạy trong Spring context. Phụ thuộc chính: `spring-boot-starter-integration`, Spring Retry (module `spring-retry`) và `spring-boot-starter-test` cho JUnit.

### 5.1. Khai báo channel và retry policy

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.retry.backoff.FixedBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
@EnableIntegration
public class RetryErrorChannelConfig {

    @Bean("orders.in")
    public MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean("orders.success")
    public PollableChannel ordersSuccess() {
        return new QueueChannel();
    }

    @Bean("orders.retry.exhausted")
    public PollableChannel ordersRetryExhausted() {
        return new QueueChannel();
    }

    @Bean
    public ConcurrentMap<String, AtomicInteger> attemptsByEvent() {
        return new ConcurrentHashMap<>();
    }

    @Bean
    public RequestHandlerRetryAdvice orderRetryAdvice(
            @Qualifier("orders.retry.exhausted") PollableChannel errors) {

        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(new SimpleRetryPolicy(3));

        FixedBackOffPolicy backOff = new FixedBackOffPolicy();
        backOff.setBackOffPeriod(100L);
        template.setBackOffPolicy(backOff);

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(template);
        advice.setRecoveryCallback(
                new ErrorMessageSendingRecoverer(errors));
        return advice;
    }

    @Bean
    public IntegrationFlow orderFlow(
            RequestHandlerRetryAdvice orderRetryAdvice,
            ConcurrentMap<String, AtomicInteger> attemptsByEvent) {

        return IntegrationFlow.from("orders.in")
                .handle(String.class, (payload, headers) -> {
                    String eventId = (String) headers.get("eventId");
                    int attempt = attemptsByEvent
                            .computeIfAbsent(eventId, key -> new AtomicInteger())
                            .incrementAndGet();

                    if (payload.equals("FAIL_ALWAYS") || attempt < 3) {
                        throw new IllegalStateException(
                                "Simulated temporary failure, attempt=" + attempt);
                    }

                    return "INVOICED:" + payload;
                }, endpoint -> endpoint.advice(orderRetryAdvice))
                .channel("orders.success")
                .get();
    }
}
~~~

**Điểm cần hiểu trong đoạn cấu hình:**

1. `SimpleRetryPolicy(3)` cho phép tối đa ba lời gọi handler theo policy demo.
2. `FixedBackOffPolicy(100 ms)` tạo khoảng nghỉ cố định giữa các lần thử.
3. `RequestHandlerRetryAdvice` bọc riêng handler được gắn `endpoint.advice(...)`.
4. `ErrorMessageSendingRecoverer` gửi lỗi cuối cùng sang channel `orders.retry.exhausted`.
5. `QueueChannel` đầu ra thành công và đầu ra lỗi giúp bài test gọi `receive(timeout)`; **chúng không phải DLQ bền vững**.

Đoạn mô phỏng cố ý lỗi với một message, sử dụng map bộ đếm cho mục đích kiểm thử. Trong production, không dùng map RAM này để lưu retry state khi có nhiều instance hoặc restart, và không trả lỗi giả từ logic nghiệp vụ như trên.

### 5.2. Producer tạo identity nghiệp vụ

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public boolean submitInvoice(MessageChannel ordersInput,
                             String eventId, String payload) {
    return ordersInput.send(
            MessageBuilder.withPayload(payload)
                    .setHeader("eventId", eventId)
                    .setHeader("correlationId", "order-501")
                    .build());
}
~~~

`ordersInput` cần là bean `orders.in`. Trong hệ thống thực, producer có thể nhận yêu cầu qua Gateway, HTTP inbound adapter hoặc broker. `eventId` phải **ổn định qua các lần replay**, không tạo ngẫu nhiên mỗi lần handler chạy.

### 5.3. Recovery callback thay đổi hợp đồng thành công của caller

Nếu retry hết lần và `ErrorMessageSendingRecoverer` **gửi thành công** đến channel `orders.retry.exhausted`, lỗi đã được xử lý ở mức **retry interceptor**: bên gửi có thể không còn thấy exception, mặc dù nghiệp vụ **chưa thành công**. Việc message đi vào error queue **không** tương đương xuất hóa đơn thành công.

Vì thế API gọi flow cần phân biệt các kết quả:

- Xử lý nghiệp vụ thành công.
- Đã nhận để xử lý bất đồng bộ.
- Không xử lý được, đã đưa vào hàng đợi lỗi hoặc chờ khắc phục.

Khi thiết kế request/reply Gateway đồng bộ, phải xác định điều gì xảy ra nếu recovery callback trả về `null` và không có reply: caller có thể tiếp tục chờ đến `replyTimeout`. Không trả “thành công” chỉ vì lời gọi `send(...)` ban đầu không ném exception.

## 6. ErrorMessage chứa gì?

`ErrorMessage` là một message có payload kiểu `Throwable`. Trong bối cảnh Retry Advice đã kiệt sức, lỗi có thể được bọc trong `MessagingException` hoặc exception liên quan. Tùy cách tạo message, có thể truy cập message gốc từ `ErrorMessage.getOriginalMessage()` hoặc từ `MessagingException.getFailedMessage()`.

Ví dụ một handler xử lý lỗi:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

public class ExhaustedRetryHandler {

    @ServiceActivator(inputChannel = "orders.retry.exhausted")
    public void handle(ErrorMessage error) {
        Throwable failure = error.getPayload();
        Message<?> original = error.getOriginalMessage();

        if (original == null && failure instanceof MessagingException ex) {
            original = ex.getFailedMessage();
        }

        Object eventId = original == null
                ? "UNKNOWN"
                : original.getHeaders().get("eventId");

        // Trong production: ghi lỗi và message vào durable DLQ/inbox.
        // Một log không thay cho bước lưu bền vững.
        System.err.println("eventId=" + eventId);
        System.err.println("cause=" + failure);
    }
}
~~~

**Lưu ý:** code trên là minh họa cách đọc lỗi. Để dùng nó, đăng ký lớp làm bean Spring và gắn vào một **subscribable channel** như `DirectChannel`, hoặc xây một poller/flow đọc `QueueChannel`. Trong cấu hình demo ở mục 5, `orders.retry.exhausted` là **QueueChannel cho test poll**, nên không thể chỉ thêm `@ServiceActivator` trực tiếp mà không thiết kế bước polling phù hợp.

Với flow production, một lựa chọn là dùng `DirectChannel` cho `orders.retry.exhausted`, một Service Activator lưu lỗi vào database/topic lỗi, và thiết kế xử lý khi chính kho lỗi không sẵn sàng. Một lựa chọn khác là giữ `QueueChannel` và cấu hình poller có error handling riêng.

### Đừng coi mọi exception đều là message đã hỏng vĩnh viễn

Khi phân loại lỗi, hãy lấy **nguyên nhân gốc** (root cause) và ngữ cảnh:

| Lỗi | Khuyến nghị |
| --- | --- |
| `ConnectException`, HTTP 503, lỗi tạm của DB | Retry có giới hạn và backoff phù hợp |
| Payload/schema sai, dữ liệu bắt buộc thiếu | Dừng retry, quarantine để sửa dữ liệu |
| Unauthorized/forbidden | Có thể cần sửa cấu hình/secret trước khi replay |
| Timeout HTTP sau khi gửi request | Kiểm tra idempotency/đối soát vì side effect có thể đã xảy ra |
| Lỗi lập trình không xác định | Log/alert, hạn chế retry gây lặp lỗi hệ thống |

`SimpleRetryPolicy(3)` trong ví dụ mặc định cho nhiều loại exception được thử lại. Production nên thiết kế policy phân loại rõ các exception được retry, thay vì thử lại mọi lỗi như nhau.

## 7. Kiểm thử đường thành công và đường kiệt sức retry

Kiểm thử bên dưới dùng **hai message với `eventId` khác nhau** để bộ đếm không giao nhau:

- `success-001`: handler lỗi hai lần và thành công ở lần thứ ba.
- `exhausted-001`: handler luôn lỗi; recoverer gửi `ErrorMessage` vào kênh lỗi sau ba lần.

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(RetryErrorChannelConfig.class)
class RetryErrorChannelTest {

    @Autowired
    @Qualifier("orders.in")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.success")
    PollableChannel success;

    @Autowired
    @Qualifier("orders.retry.exhausted")
    PollableChannel exhausted;

    @Autowired
    ConcurrentMap<String, AtomicInteger> attemptsByEvent;

    @Test
    void succeedsAfterTwoFailures() {
        assertTrue(input.send(
                MessageBuilder.withPayload("ORDER-501")
                        .setHeader("eventId", "success-001")
                        .build()));

        Message<?> result = success.receive(1_000);
        assertNotNull(result);
        assertEquals("INVOICED:ORDER-501", result.getPayload());
        assertEquals(3, attemptsByEvent.get("success-001").get());
        assertNull(exhausted.receive(0));
    }

    @Test
    void sendsErrorMessageAfterRetryExhausted() {
        assertTrue(input.send(
                MessageBuilder.withPayload("FAIL_ALWAYS")
                        .setHeader("eventId", "exhausted-001")
                        .build()));

        Message<?> failed = exhausted.receive(1_000);
        assertNotNull(failed);
        assertInstanceOf(ErrorMessage.class, failed);
        assertInstanceOf(Throwable.class, failed.getPayload());
        assertEquals(3, attemptsByEvent.get("exhausted-001").get());
        assertNull(success.receive(0));
    }
}
~~~

Các ca test nên chạy độc lập hoặc có context/queue riêng khi chạy song song để tránh message từ test khác chen vào. Test ở đây kiểm tra hành vi của flow với một `DirectChannel` và recovery queue; nó không chứng minh durability qua restart.

**Điều cần đọc ở kết quả:** nếu test `exhausted` chạy thành công nhưng `input.send(...)` không ném exception, đó là do recovery đã chuyển message lỗi sang kênh khác, **không có nghĩa lần xử lý nghiệp vụ đã thành công**.

## 8. Khi không có recovery callback hoặc khi recovery cũng lỗi

Với `RequestHandlerRetryAdvice` không có recovery callback, exception sau khi retry kiệt sức có thể truyền ngược tới caller ở luồng đồng bộ; khi chạy trên poller/executor, tầng error publisher thích hợp có thể đưa nó vào error channel.

Khi có `ErrorMessageSendingRecoverer`, nhưng kênh lỗi không tồn tại, không có subscriber, bị nghẽn hoặc việc lưu vào kho lỗi thất bại, recovery cũng có thể lỗi. Không giả định rằng message đã được lưu bền vững chỉ vì mã đã gọi `send(...)` tới một channel.

~~~mermaid
flowchart TB
    H["Handler + Retry Advice"] --> Q{Thành công?}
    Q -->|Có| S[Output thành công]
    Q -->|Không, hết retry| C[Recovery callback]
    C --> R{Gửi lỗi thành công?}
    R -->|Có| E[Error channel / durable error workflow]
    R -->|Không| X[Recovery failure cần xử lý ở ranh giới caller/thread]
~~~

Một thiết kế sản xuất phải quyết định **ai chịu trách nhiệm** khi error channel hoặc DLQ cũng lỗi:

- Ném exception để nguồn nhận không ACK và có cơ chế redelivery phù hợp.
- Dùng outbox hoặc transaction nếu nguồn và kho lỗi có thể tham gia một giao dịch.
- Chuyển sang một fallback có kiểm soát hoặc cảnh báo vận hành ngay.
- Không chấp nhận chỉ log lỗi và “bỏ qua” một sự kiện quan trọng.

**Không gọi handler lỗi rồi im lặng kết thúc nếu chưa bảo đảm lưu lại được thông tin cần replay.**

## 9. Phân biệt Retry Advice, Delayer retry và broker redelivery

Trong một flow lớn, có thể cùng tồn tại nhiều cơ chế thử lại:

| Vị trí | Cơ chế | Lỗi mà nó nhìn thấy |
| --- | --- | --- |
| Service Activator/outbound handler | `RequestHandlerRetryAdvice` | Exception trong lời gọi handler được advice bao quanh |
| Delayer phát message đã đến hạn | `maxAttempts`, `retryDelay` | Lỗi truyền về khi phát message từ Delayer xuống downstream |
| Poller | Advice chain của poller, error handler | Lỗi khi poll/dispatch/handle theo cách endpoint được cấu hình |
| Kafka/RabbitMQ/JMS consumer | Redelivery/retry/DLQ của adapter/broker | Lỗi và ACK/NACK theo contract của consumer |
| HTTP client | Client-level retry | Lỗi mạng/request do client kiểm soát |

Ví dụ Delayer retry tối đa 3 lần nhưng handler bên trong cũng có Retry Advice tối đa 3 lần: nếu mọi thao tác đều thất bại và exception vẫn truyền qua cả hai tầng, đối tác có thể bị gọi **tối đa 9 lần** trong kịch bản đơn giản. Khi có recovery callback xử lý lỗi, kết quả còn phụ thuộc việc callback có ném exception hay không.

**Nguyên tắc:** chọn một tầng chịu trách nhiệm retry chính cho từng loại lỗi, tính **ngân sách retry tổng** và tránh nhân số lần thử ngoài dự kiến. Đối với HTTP timeout không rõ request đã thành công hay chưa, phải dùng idempotency key trước khi quyết định retry.

## 10. Error channel và idempotency

`MessageHeaders.ID` định danh một đối tượng `Message` của Spring, nhưng một sự kiện được producer gửi lại có thể được xây dựng thành message mới mang UUID khác. Vì thế:

- `eventId`: khóa ổn định cho **sự kiện nghiệp vụ**.
- `correlationId`: nối các message cùng đơn hàng/workflow.
- `retryAttempt`: thông tin lần thử để vận hành và cảnh báo; không tự làm khóa chống trùng.
- `messageGroupId`: nếu có Delayer, đây là khóa group message đang chờ, **không phải** khóa dedupe.

~~~java
MessageBuilder.withPayload("ORDER-501")
        .setHeader("eventId", "invoice:order-501:v1")
        .setHeader("correlationId", "order-501")
        .build();
~~~

Retry một lời gọi có thể khiến side effect xảy ra nhiều lần. Ví dụ API đối tác xử lý xuất hóa đơn thành công nhưng phản hồi bị timeout; nếu caller thử lại mà đối tác không nhận diện idempotency key, hai hóa đơn có thể được tạo.

Pseudocode kiến trúc:

~~~java
// Minh họa ý tưởng, không phải implementation atomic production.
void processInvoice(String eventId, String orderId) {
    if (idempotencyStore.alreadyCompleted(eventId)) {
        return;
    }

    partnerApi.createInvoiceWithIdempotencyKey(eventId, orderId);
    idempotencyStore.markCompleted(eventId);
}
~~~

Kiểm tra rồi đánh dấu tách rời có race. Khi chạy thật cần claim/unique constraint atomic, trạng thái `PROCESSING`/`COMPLETED`, transaction, lease/retry cho trạng thái kẹt và idempotency phía đối tác. **Error channel là nơi nhận lỗi; nó không tự bảo đảm chống trùng.**

## 11. Error flow cho các EIP khác trong module

Một đường lỗi tốt cần mang đủ ngữ cảnh khi message đi qua nhiều pattern:

~~~mermaid
flowchart LR
    A[Inbound] --> T[Transformer]
    T --> R{Router}
    R --> S[Service Activator + Retry]
    R --> Q[Other route]
    S -->|Thành công| O[Success]
    S -->|Hết retry| E[Error channel]
    E --> P[Audit / Quarantine]
~~~

| EIP | Lưu ý khi kết hợp retry và error channel |
| --- | --- |
| **Transformer** | Nếu lỗi do dữ liệu không hợp lệ, sửa dữ liệu hoặc route quarantine thay vì retry vô ích |
| **Router** | Định tuyến dựa trên mã lỗi/loại message; không làm mất `eventId` và `correlationId` |
| **Filter** | Lọc sự kiện không còn hợp lệ sau thời gian chờ, tránh thực hiện hành động lỗi thời |
| **Splitter** | Mỗi phần tử có thể được retry riêng; cần định danh `eventId + partId` để tránh trùng một phần |
| **Aggregator** | Retry một phần tử có thể gây lặp trong group; cần chiến lược correlation và duplicate control |
| **Gateway** | Caller có thể timeout dù recovery đã nhận lỗi; API cần hợp đồng ACK/trạng thái rõ ràng |
| **Delayer** | Lỗi khi phát lại có retry/error channel riêng, không đồng nhất với Retry Advice của handler |

Một flow có Splitter → nhiều handler → Aggregator cần xác định đường lỗi cho **mỗi phần tử** và điều kiện hoàn thành group. Nếu một phần tử được chuyển sang DLQ, Aggregator có thể chờ mãi nếu không có timeout/release strategy xử lý trường hợp thiếu phần tử.

## 12. Backoff, timeout và nguy cơ nghẽn thread

`FixedBackOffPolicy` trong ví dụ là chính sách đơn giản. Với đối tác có lỗi tạm thời trên diện rộng, nhiều request đồng loạt retry sau 100 ms có thể tạo đợt tải lặp. Có thể cân nhắc **exponential backoff và jitter** ở tầng retry phù hợp, với trần thời gian và số lần thử.

| Thành phần | Tác động thời gian |
| --- | --- |
| `RetryTemplate` với backoff đồng bộ | Có thể giữ thread của handler trong lúc chờ lần thử tiếp theo |
| `ExecutorChannel` | Tách thread producer khỏi handler; lỗi downstream cần error flow tại tầng bất đồng bộ |
| `Gateway.replyTimeout` | Caller có thể ngừng chờ trước khi toàn bộ retry kết thúc |
| Delayer | Trì hoãn **trước khi phát message**; không tự là rate limiter hay cron |
| Scheduler/broker | Có thể phù hợp với các lần retry dài, backlog lớn hoặc yêu cầu persistence cao hơn |

### Bài toán thời gian tổng

Giả sử mỗi lời gọi API có timeout 2 giây, số lần thử tối đa 3 và backoff 500 ms giữa lần:

\[
\text{thời gian tối đa xấp xỉ} = 3 \times 2s + 2 \times 0.5s = 7s
\]

Đây là ước lượng khi mỗi lần thử chạm timeout đầy đủ; thời gian thực còn phụ thuộc overhead, scheduler, kết nối và tải. Nếu Gateway chỉ đợi 3 giây, caller có thể timeout dù retry vẫn tiếp diễn. Hãy thống nhất deadline của request và **retry budget** với hợp đồng ứng dụng.

Đối với retry kéo dài phút/giờ, không nên giữ một thread trong suốt quá trình. Có thể đưa message vào hàng đợi lỗi/đợi retry bền vững hoặc dùng một flow Delayer/worker chuyên reschedule, tùy kiến trúc.

## 13. Quan sát, cảnh báo và replay có kiểm soát

Một bản ghi lỗi nên có thể trả lời “message nào?”, “lỗi gì?”, “đã thử mấy lần?”, “tác động ngoài đã xảy ra chưa?”:

~~~text
flow=invoiceCreation
eventId=invoice:order-501:v1
correlationId=order-501
handler=invoicePartnerAdapter
exceptionType=java.net.SocketTimeoutException
attempts=3
recoveryChannel=orders.retry.exhausted
firstAttemptAt=2026-11-21T10:00:00Z
lastAttemptAt=2026-11-21T10:00:05Z
outcome=QUARANTINED
~~~

Đây là **log do ứng dụng thiết kế**, không phải tất cả trường được Spring Integration tự sinh. Không ghi token, password hoặc dữ liệu thanh toán nhạy cảm vào payload log.

Các metric quan trọng:

| Chỉ số | Ý nghĩa |
| --- | --- |
| `handlerSuccessCount` | Số message xử lý thành công |
| `retryAttemptCount` | Tổng số lần thử lại |
| `retryExhaustedCount` | Số message hết số lần thử |
| `errorChannelPublishFailures` | Số lần ngay cả recovery cũng không gửi/lưu được lỗi |
| `deadLetterBacklog` | Số message chưa được giải quyết trong kho lỗi |
| `retryLatencyMs` | Thời gian từ lần thử đầu đến kết quả cuối |
| `duplicateSuppressedCount` | Số tác động trùng được idempotent consumer ngăn |

### Trình tự replay an toàn

1. Đọc thông tin lỗi và phân loại nguyên nhân: dữ liệu sai, cấu hình sai, đối tác quá tải hay kết quả không rõ.
2. Kiểm tra kết quả ở dịch vụ đích theo `eventId`; đừng mặc định lần trước thất bại chỉ vì caller timeout.
3. Sửa dữ liệu hoặc cấu hình; xác định chính sách retry mới.
4. Phát lại bằng cùng **idempotency key** nếu đây là cùng thao tác nghiệp vụ.
5. Cập nhật trạng thái kho lỗi theo transaction/đối soát thích hợp; theo dõi hậu quả sau replay.

Không tự chạy replay vô hạn, không xóa message lỗi trước khi có dấu vết xử lý, và không tạo event ID mới chỉ để vượt qua kiểm tra trùng.

## 14. Ma trận quyết định và xử lý sự cố

| Triệu chứng | Khả năng | Hướng xử lý |
| --- | --- | --- |
| `send()` ném exception ngay | Handler đồng bộ lỗi, không có recovery hoặc recovery lỗi | Kiểm tra Retry Advice, exception và channel |
| `send()` thành công nhưng không thấy kết quả nghiệp vụ | Recovery đã chuyển lỗi sang error channel; output không có reply | Kiểm tra cả kênh success và error, hợp đồng ACK |
| Global `errorChannel` không có gì | Lỗi đi theo đường đồng bộ, hoặc recoverer dùng channel riêng | Kiểm tra vị trí ErrorMessage publisher |
| Retry không chạy | Advice chưa gắn vào endpoint; lỗi ở consumer async phía sau | Gắn advice đúng handler hoặc đặt retry ở consumer |
| Handler bị gọi 9 lần thay vì 3 | Hai tầng retry cùng cấu hình 3 lần | Định nghĩa retry owner và ngân sách tổng |
| Error queue tăng liên tục | Đối tác lỗi lâu dài, dữ liệu không hợp lệ hoặc DLQ không được tiêu thụ | Cảnh báo, phân loại lỗi và xử lý backlog |
| Retry HTTP gây tạo hai hóa đơn | Timeout sau side effect, thiếu idempotency | Sử dụng khóa sự kiện ở dịch vụ đích/đối soát |
| Error handler chỉ log rồi mất message | Kênh lỗi hoặc logging không bền vững | Durable dead letter và quy trình replay |
| Gateway timeout trước khi retry hoàn tất | `replyTimeout` quá ngắn so với retry budget | Chuyển sang ACK async hoặc điều chỉnh hợp đồng |

## 15. Bài tập thực hành và câu hỏi tự kiểm tra

1. Cấu hình `RequestHandlerRetryAdvice` tối đa 3 lần. Cho handler thất bại hai lần đầu rồi thành công, khẳng định `orders.success` có một kết quả và error queue trống.
2. Cho handler luôn lỗi, xác minh một `ErrorMessage` xuất hiện ở `orders.retry.exhausted` sau ba lần thử.
3. Bỏ recovery callback. So sánh exception tới caller trong luồng `DirectChannel` với hành vi khi có callback.
4. Thay error queue bằng `DirectChannel` và một `ServiceActivator` thực sự lưu lỗi bền vững; cho kho lỗi ném exception rồi xác định hậu quả với nguồn message.
5. Thay handler bằng consumer chạy sau `ExecutorChannel`, giải thích vì sao error channel/error publisher ở ranh giới async là quan trọng.
6. Cho hai tầng retry cùng tối đa 3 lần, đo số lần gọi dịch vụ, rồi thiết kế lại để chỉ một tầng chịu trách nhiệm.
7. Tạo lỗi HTTP timeout sau khi đối tác đã xử lý thành công. Sử dụng `eventId`/idempotency key để tránh tạo hai hóa đơn.
8. Thiết kế lỗi không retryable như payload thiếu mã đơn và route sang quarantine ngay, không chờ 3 lần thử.
9. Thêm `correlationId` và `partId` sau Splitter; thử replay một phần tử và xem Aggregator có nhận duplicate hay không.
10. Đặt Gateway `replyTimeout` nhỏ hơn tổng retry budget; xây một API ACK bất đồng bộ và kênh truy vấn trạng thái để client không nhầm timeout với thất bại nghiệp vụ.

**Câu hỏi tự kiểm tra:** Vì sao global `errorChannel` không tự nhận mọi exception của `DirectChannel`? `RetryTemplate` và `ErrorMessageSendingRecoverer` có vai trò khác nhau thế nào? Nếu recoverer gửi lỗi thành công thì caller có thể nhìn thấy gì? Vì sao `QueueChannel` trong bài test không phải durable dead-letter store? Retry có thể tạo side effect trùng ở giai đoạn nào? Khi sử dụng Gateway, làm sao phân biệt hết thời gian chờ với một nghiệp vụ đã thất bại?

## Tài liệu tham khảo

- [Spring Integration Reference — Retry Advice](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html): `RequestHandlerRetryAdvice` và `ErrorMessageSendingRecoverer`.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, error channel và ranh giới đồng bộ/bất đồng bộ.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): gắn advice vào handler trong `IntegrationFlow`.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): reply timeout và luồng request/reply.
- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): khác biệt giữa retry lúc release Delayer và retry trên handler.
- [Spring Retry Reference](https://docs.spring.io/spring-retry/reference/): `RetryTemplate`, retry policy, backoff và recovery.
