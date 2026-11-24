# Test error flow và dead-letter

**Chương:** Testing  
**Bài học:** Test error flow và dead-letter  
**Module:** Spring Integration Adapters (`SPRING_INTEGRATION_ADAPTERS`)  
**Phạm vi:** Kiểm thử cách inbound/outbound adapter, gateway, poller và `MessageChannel` xử lý lỗi; xác nhận retry, error channel, recoverer, dead-letter, acknowledgment, transaction và replay qua File/SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu.

> **Thông điệp chính:** Một bài test chỉ xác nhận exception xuất hiện là **chưa đủ**. Khi integration flow lỗi, cần chứng minh bản tin **không bị mất**, **không bị xử lý trùng ngoài hợp đồng**, đã đi tới đúng **error/recovery destination**, trạng thái **ack/commit** nhất quán, và có đường **đối soát hoặc replay an toàn**.

## 1. Vì sao phải test error flow và dead-letter?

Luồng tích hợp bình thường dễ kiểm thử: tạo message, gửi qua channel, gọi adapter, assert kết quả. Nhưng lỗi thực tế thường xảy ra ở những thời điểm khó quan sát:

- HTTP outbound gateway gửi request thành công nhưng response bị mất.
- Kafka consumer xử lý và ghi DB xong nhưng crash trước khi commit offset.
- JMS/AMQP consumer rollback rồi nhận lại cùng message.
- SFTP poller tải file nhưng một record bị lỗi schema.
- JDBC poller claim hàng, gọi API ngoài timeout rồi không rõ transaction đã commit chưa.
- Handler retry hết lượt; recoverer gửi `ErrorMessage` nhưng error flow không có subscriber.
- DLQ publisher lỗi, dù application đã tưởng rằng failure được lưu an toàn.
- Người vận hành replay một message mà downstream đã xử lý từ trước.

Các trường hợp này có thể làm **mất tác vụ**, **nhân đôi side effect**, **kẹt poison message**, **tăng độ trễ**, hoặc tạo **silent failure**: log có lỗi nhưng luồng vẫn bị báo thành công.

Ví dụ xuyên suốt: hệ thống lấy file đơn hàng từ SFTP, tách thành các message, gọi HTTP API để tạo vận đơn, sau đó ghi kết quả vào DB hoặc phát event Kafka. Nếu HTTP timeout sau ba lần thử, hệ thống phải có trạng thái rõ ràng và bằng chứng:

~~~text
SFTP file/record
    -> parse + validate
    -> MessageChannel
    -> HTTP outbound handler (+ retry)
          -> success: persist result
          -> exhausted: error/recovery flow
                -> durable failure record / DLQ / quarantine
                -> alert + reconciliation/replay
~~~

**Câu hỏi kiểm thử không chỉ là "có error không?"** mà là "bản ghi đơn hàng cuối cùng đang ở đâu, ai chịu trách nhiệm xử lý nó, và làm sao biết chưa có duplicate?".

### 1.1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích `ErrorMessage`, `errorChannel`, header `errorChannel`, `MessagingException` và `MessagePublishingErrorHandler`.
2. Phân biệt lỗi **đồng bộ**, **bất đồng bộ**, lỗi trong **poller**, và lỗi **sau retry exhaustion**.
3. Thiết kế test ở các cấp **unit**, **flow component**, **integration với broker/server thật**, và **failure-injection end-to-end**.
4. Dùng JUnit 5, Spring Test, `@SpringIntegrationTest`, `MockIntegrationContext`, `MockIntegration` hoặc `QueueChannel` đúng phạm vi.
5. Xác nhận recoverer tạo `ErrorMessage`, error flow phân loại lỗi, và DLQ/quarantine **được ghi bền**.
6. Kiểm thử ACK/NACK, offset commit, transaction rollback, idempotency và retry budget cho các adapter.
7. Kiểm tra replay sau lỗi, phục hồi khi error handler cũng lỗi, metrics và tiêu chí đóng incident.

## 2. Những khái niệm cần phân biệt

| Thuật ngữ | Ý nghĩa | Điều cần chứng minh khi test |
| --- | --- | --- |
| **Error flow** | Luồng nhận thông tin lỗi rồi quyết định xử lý | Error đến đúng flow, không bị bỏ qua |
| **`ErrorMessage`** | Spring Message có payload là `Throwable` | Đúng exception/cause, đủ context cần thiết |
| **`errorChannel`** | Channel lỗi theo header hoặc global name | Lỗi được route đúng trong loại endpoint đang dùng |
| **Retry** | Gọi lại một thao tác khi lỗi thuộc nhóm được phép | Số attempts, backoff, giới hạn thời gian |
| **Retry exhaustion** | Retry policy không cho thử thêm | Recovery được thực hiện đúng một lần theo thiết kế |
| **Recoverer / `RecoveryCallback`** | Quyết định sau khi retry cạn | Propagate, archive, DLQ hoặc fallback đúng contract |
| **Dead-letter queue/topic (DLQ/DLT)** | Destination giữ message không xử lý được | Đã publish thành công, có thể đọc/replay |
| **Quarantine store** | Kho riêng giữ dữ liệu lỗi chờ điều tra/sửa | Có retention, owner, reference và audit |
| **Acknowledgment** | Nguồn xác nhận đã nhận/xử lý theo cơ chế | Không ACK khi còn nguy cơ mất operation |
| **Transaction** | Ranh giới commit/rollback | Failure không để lại trạng thái sai |
| **Idempotency** | Xử lý cùng business operation nhiều lần không sinh tác động thừa | Redelivery/replay không nhân đôi side effect |
| **Reconciliation** | Xác định outcome thật ở downstream | Không đoán FAILED khi response mất |

### 2.1. Error channel không mặc nhiên là DLQ

Một `ErrorMessage` được gửi đến `DirectChannel`, `PublishSubscribeChannel` hay `QueueChannel` trong bộ nhớ **không có nghĩa** nó được lưu bền như broker DLQ. Để bảo đảm failure còn sau restart, error flow phải publish vào destination bền hoặc lưu failure record vào kho an toàn và **kiểm chứng việc lưu đó**.

### 2.2. Retry exhaustion không đồng nghĩa xử lý chưa xảy ra

Với thao tác có side effect, timeout có thể xảy ra **sau khi remote service commit**. Hệ thống không nhận response nên không biết kết quả. Nếu tự replay một POST tạo đơn, có thể tạo trùng. Bài test phải mô phỏng **outcome unknown**, buộc luồng dùng operation ID/idempotency key hoặc truy vấn trạng thái đối tác trước replay.

### 2.3. DLQ không phải trạng thái cuối nghiệp vụ

Message vào DLQ có thể là:

- Lỗi schema cần sửa dữ liệu.
- Lỗi cấu hình auth/permission cần xử lý vận hành.
- Lỗi hạ tầng đã hết retry.
- Outcome chưa rõ, cần reconciliation.
- Poison message luôn làm consumer lỗi.

Vì vậy "đã vào DLQ" chỉ nghĩa là **đã được bàn giao sang nơi xử lý failure**, không chứng minh nghiệp vụ đã thành công hoặc đã được xử lý triệt để.

## 3. Bản đồ đường đi của exception

~~~mermaid
flowchart TD
    SRC["Inbound adapter / gateway / poller"] --> CH["MessageChannel"]
    CH --> H["MessageHandler / outbound adapter"]
    H --> Q{"Handler throws?"}
    Q -->|Không| OK["Normal reply / next channel"]
    Q -->|Có| MODE{"Đồng bộ hay async/poller?"}
    MODE -->|Caller thread / DirectChannel| CALL["Exception tới caller<br/>trừ khi có cơ chế catch/route riêng"]
    MODE -->|Executor/TaskExecutor hoặc poller| PUB["MessagePublishingErrorHandler"]
    PUB --> EC["Header errorChannel hoặc global errorChannel"]
    EC --> ROUTE["Error router / service activator"]
    H -.-> RETRY["RequestHandlerRetryAdvice"]
    RETRY --> EXH{"Retry exhausted?"}
    EXH -->|Có, recovery callback| REC["ErrorMessageSendingRecoverer hoặc custom recoverer"]
    REC --> RCH["Dedicated recovery channel"]
    ROUTE --> STORE["Durable failure store / broker DLQ / quarantine"]
    RCH --> STORE
    CALL --> SOURCE["Caller / source transaction / gateway error contract"]
    STORE --> TEST["Verify evidence + ack + replay policy"]
    SOURCE --> TEST
~~~

Sơ đồ thể hiện **những đường khả dĩ**, không phải một exception sẽ đi qua tất cả nhánh. Vị trí advice, threading, loại inbound endpoint và handler quyết định đường đi thật.

### 3.1. `DirectChannel`: lỗi đồng bộ

Một `DirectChannel` thường gọi subscriber trên thread gửi message. Khi handler ném exception:

~~~text
JUnit thread -> channel.send(message) -> handler -> exception
                                  <- exception propagates
~~~

Vì thế test dùng `assertThrows(...)` hoặc kiểm tra root cause thường đúng hơn việc chờ một ErrorMessage ở global `errorChannel`. **Không giả định mọi synchronous exception được framework tự publish vào errorChannel.**

### 3.2. `ExecutorChannel`/poller: lỗi bất đồng bộ

Khi message được xử lý bởi một `TaskExecutor`, nguồn gửi có thể đã trả về trước khi handler ném exception. Spring Integration hỗ trợ publish lỗi thành `ErrorMessage` theo cơ chế error handler phù hợp. Poller task có thể dùng `MessagePublishingErrorHandler` để đưa lỗi vào error channel.

Do đó test cần **quan sát kênh lỗi/condition bất đồng bộ**, không chỉ assert exception ở thread gọi `send`.

### 3.3. Nguồn định tuyến lỗi

Với đường dùng `MessagePublishingErrorHandler`, thứ tự tìm nơi nhận lỗi thường là:

1. `MessageHeaders.ERROR_CHANNEL` trên message đang xử lý nếu có.
2. Global channel tên `errorChannel`.

Một recoverer được gắn **explicit recovery channel** có thể gửi lỗi tới đó thay vì global `errorChannel`. Bài test phải nêu rõ đường nào được kỳ vọng và không nhập nhằng.

## 4. ErrorMessage gồm những gì?

`ErrorMessage` là message có **payload là `Throwable`**. Với lỗi do Spring Integration xử lý, payload có thể là `MessagingException` chứa message gây lỗi, hoặc exception được bọc tùy adapter/đường thực thi.

Các thông tin hữu ích khi test:

- **Exception class và root cause:** Timeout, validation, auth, broker failure, DB conflict...
- **Failed message:** `MessagingException.getFailedMessage()` khi có.
- **Original message:** `ErrorMessage.getOriginalMessage()` nếu `ErrorMessageStrategy` cung cấp.
- **Headers:** Correlation ID, source adapter ID, business operation ID, message ID, tenant ID khi policy cho phép.
- **Flow/endpoint identity:** Xác định handler nào lỗi.
- **Attempt history:** Bao nhiêu lần thử đã xảy ra theo retry policy thực.
- **Destination decision:** Error flow chọn quarantine, DLQ, rethrow hay fallback.

### 4.1. Original message có luôn hiện diện không?

**Không.** Tùy exception và `ErrorMessageStrategy`, `originalMessage` hoặc `getFailedMessage()` có thể không có hoặc không phản ánh cùng một điểm trong flow. Đặc biệt sau transform/split, message gần lỗi có thể không giống raw input ban đầu.

Một extractor để phục vụ failure record nên có chính sách:

~~~text
if ErrorMessage.originalMessage exists:
    use safely selected fields from originalMessage
else if throwable is MessagingException and failedMessage exists:
    use safely selected fields from failedMessage
else:
    use correlation in logging/trace/input metadata;
    record MISSING_ORIGINAL_CONTEXT, do not fabricate payload
~~~

### 4.2. Không so chuỗi stack trace nguyên văn

Stack trace thay đổi theo runtime, wrapper và version. Test ổn định nên assert:

- Loại/nhóm exception hoặc root cause.
- Nội dung nghiệp vụ có ý nghĩa, nếu là contract.
- Message correlation và metadata.
- Hành vi retry/recovery/DLQ.

Không nên assert số dòng stack trace hay toàn bộ `Throwable.toString()`.

## 5. Mặc định `errorChannel` và hậu quả khi không có subscriber

Spring Integration có global `errorChannel` phục vụ những đường xử lý lỗi cần message-based error handling. Trong nhiều phiên bản, channel mặc định là **`PublishSubscribeChannel`**, có logging subscriber; cơ chế yêu cầu subscriber có thể làm lỗi dispatch rõ ràng hơn thay vì silently dropping.

Điều cần test:

1. Global channel có tồn tại trong application context.
2. Custom `errorChannel` có đúng loại channel và consumer không.
3. Header `errorChannel` có ưu tiên trong đường publish hỗ trợ không.
4. Nếu channel không có subscriber, thất bại có bị bỏ qua hay được ném/cảnh báo.
5. Error handler consumer ném exception thì upstream có được retry/nack theo thiết kế không.
6. Lúc app shutdown, lỗi trong inflight tasks có gây mất message không.

**Không sửa cấu hình global error channel trong test mà vô tình thay toàn bộ semantics production.** Có thể tạo test context riêng hoặc dedicated channel cho flow cần test.

### 5.1. Tại sao test một log `ERROR` chưa đủ?

Logging subscriber ghi exception chỉ là **tín hiệu**. Nếu message nguồn đã ack mà chưa được lưu failure ở nơi bền vững, không có đường replay; do đó luồng vẫn sai về reliability dù log có đầy đủ stack trace.

## 6. Test pyramid cho error flow và dead-letter

| Cấp test | Kiểm tra chính | Công cụ gợi ý | Không nên suy ra |
| --- | --- | --- | --- |
| **Unit** | Phân loại lỗi, build failure envelope, redaction, retry decision | JUnit 5, Mockito, AssertJ | Đã publish broker DLQ thật |
| **Flow/component** | Handler advice, channel routing, `ErrorMessage`, discard/recovery handler | Spring Integration test, `QueueChannel`, `MockIntegrationContext` | Broker ack/offset thật |
| **Adapter integration** | Protocol, connection, transaction, redelivery, DLQ/DTL | Testcontainers/embedded brokers, fake SFTP/HTTP | Toàn bộ end-to-end được đảm bảo |
| **End-to-end failure injection** | Crash windows, store outage, replay, idempotency, reconciliation | Container restart, network fault, observability | Mọi lỗi production đã được bao phủ |
| **Operational drill** | Runbook và người chịu trách nhiệm xử lý backlog | Môi trường staging được phép | Có thể bỏ qua audit hoặc bảo mật payload |

### 6.1. Vì sao cần nhiều lớp?

Unit test nhanh và xác định logic của bạn, nhưng không thấy ack của RabbitMQ hoặc Kafka offset. Integration test với broker thật có thể xác minh redelivery nhưng chậm hơn. Drill có thể chứng minh failure record vẫn sống sau restart nhưng cần kiểm soát tài nguyên test.

### 6.2. Quy tắc test không phụ thuộc thời gian ngẫu nhiên

- Ưu tiên `QueueChannel.receive(timeout)`, latch, Awaitility hoặc signal có thời hạn.
- Dùng timeout hữu hạn và hợp lý, không dùng `Thread.sleep` tùy tiện để "đợi hệ thống".
- Với retry có backoff, dùng test policy không delay hoặc thời hạn ngắn riêng cho test.
- Không assert thời gian chính xác từng mili giây nếu scheduler/broker có jitter.
- Reset metadata store, queue, database, mock và test fixtures sau mỗi ca.

## 7. Dụng cụ test trong Spring Integration

Spring Integration cung cấp:

- **`spring-integration-test-support`:** Những helper dùng trong unit/component tests.
- **`spring-integration-test`:** Testing framework với `@SpringIntegrationTest`, `MockIntegrationContext`, integration mocks và cấu hình Spring test context.
- **Spring Test + JUnit 5:** `@SpringJUnitConfig`, `@SpringBootTest` khi thích hợp, `@DirtiesContext` nếu thực sự cần cô lập context.
- **`MockIntegration`:** Mock `MessageSource`, `MessageProducer`, `MessageHandler`, `MessageChannel` để kiểm thử phần flow mục tiêu.
- **`QueueChannel`:** Thu message tại một điểm cho assertion.
- **`OnlyOnceTrigger`:** Hạn chế poller phát đúng một sự kiện trong unit/integration test phù hợp.
- **`MockIntegrationContext`:** Thay message source/handler, ngăn auto-start endpoint và reset sau test.

### 7.1. Khống chế poller trong test

Nếu test load application context thật mà SFTP/JDBC/AMQP inbound adapter tự khởi động, test có thể gọi ra hệ thống thật, race hoặc nhận dữ liệu ngoài test.

~~~java
@SpringJUnitConfig(MyIntegrationConfig.class)
@SpringIntegrationTest(noAutoStartup = {"sftpInbound", "jdbcPoller", "*Source*"})
class ErrorFlowTests {
    @Autowired
    MockIntegrationContext mockIntegrationContext;

    @AfterEach
    void restore() {
        mockIntegrationContext.resetBeans();
    }
}
~~~

Tên pattern trong `noAutoStartup` phải khớp **endpoint bean names**. Không giả định method Java config name luôn trùng endpoint internal ID trong mọi DSL. Test nên xác minh endpoint nào được chặn auto-start.

### 7.2. Thay MessageSource trong test

~~~java
MessageSource<String> fakeSource =
        () -> new GenericMessage<>("one-test-message");

mockIntegrationContext.substituteMessageSourceFor(
        "myPollingEndpoint", fakeSource);
~~~

Đây là đoạn minh họa API; để chạy cần đúng imports và bean `myPollingEndpoint` thực sự là `SourcePollingChannelAdapter` phù hợp. Khi test chỉ cần một lần poll, `OnlyOnceTrigger` hoặc trigger thay thế được hỗ trợ có thể giúp tránh message phát lặp.

**Chú ý:** Một **mock source** chứng minh flow error routing nhưng không chứng minh SFTP remote file filter, JMS acknowledgment hoặc Kafka offset commit. Những điều đó cần integration test protocol-specific.

## 8. Phân loại lỗi để xây test matrix

| Lỗi | Retry theo mặc định nên cân nhắc | Kết quả kiểm thử |
| --- | --- | --- |
| HTTP timeout/network reset | Retry hữu hạn nếu operation idempotent | Attempts, backoff, recovery và outcome unknown |
| HTTP 429 / transient 503 | Retry theo contract và rate limit | Tôn trọng Retry-After nếu hệ thống hỗ trợ |
| JSON/schema không hợp lệ | Thường không retry | Quarantine ngay, giữ raw input/reference có kiểm soát |
| HTTP 401/403 | Thường cần sửa auth/permission | Không tạo retry storm, alert owner |
| JMS/AMQP deserialization | Có thể là poison message | Đúng DLQ sau policy, không chặn vô hạn cả queue |
| Kafka deserialization | Có thể xảy ra **trước** business handler | Container/deserializer error path, DLT, offset |
| JDBC unique conflict | Có thể là duplicate hợp lệ hoặc lỗi contract | Business decision, không retry mù |
| SFTP file transfer interrupted | Retry transfer/chốt file theo source policy | Không tạo file local nửa chừng được xử lý |
| Downstream commit rồi mất response | Outcome unknown | Reconcile/idempotency trước replay |
| Recovery archive/DLQ publish lỗi | Lỗi của chính error flow | Không ack nguồn nếu sẽ mất message |

Đừng bao toàn bộ exception thành `RuntimeException` rồi test chung một đường: việc **phân loại retryable/non-retryable** và **đúng tầng phát sinh lỗi** quyết định behavior thật.

## 9. Test luồng đồng bộ: exception tới caller

Một test đơn giản không cần broker để chứng minh handler đồng bộ ném lỗi:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class SynchronousErrorFlowTest {

    @Test
    void handlerFailurePropagatesToSender() {
        DirectChannel input = new DirectChannel();
        input.subscribe((MessageHandler) message -> {
            throw new IllegalStateException("simulated downstream outage");
        });

        Message<String> request = MessageBuilder
                .withPayload("order-971")
                .build();

        RuntimeException failure = assertThrows(
                RuntimeException.class, () -> input.send(request));

        // Framework có thể bọc exception; tìm root cause thay vì
        // ép kiểu top-level exception.
        Throwable root = failure;
        while (root.getCause() != null) {
            root = root.getCause();
        }
        assertInstanceOf(IllegalStateException.class, root);
        assertEquals("simulated downstream outage", root.getMessage());
    }
}
~~~

**Bài test này chứng minh điều gì?** `DirectChannel` hoạt động đồng bộ và lỗi lan tới caller khi không có cơ chế catch/route khác. Nó **không** chứng minh một `ErrorMessage` đã được gửi global `errorChannel`.

### 9.1. Cần test thêm ở một gateway

Khi flow bắt đầu bằng inbound HTTP gateway, exception có thể được ánh xạ thành HTTP status/body theo error handling của gateway/app. Test phải assert:

- Status code phù hợp với lỗi nghiệp vụ/hạ tầng.
- Không trả `200 OK` khi chưa xử lý thành công.
- Có correlation ID và mã lỗi không lộ secret.
- Thời hạn chờ của caller phù hợp tổng retry time.

## 10. Test `ErrorMessage` và failure envelope ở cấp unit

Ta có thể tạo một `ErrorMessage` rồi gọi một **application error handler** để test phân loại lỗi và lưu failure record, không cần khởi động broker.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class FailureEnvelopeTest {

    @Test
    void preservesBusinessCorrelationAndRootCause() {
        Message<String> request = MessageBuilder
                .withPayload("sensitive-payload-reference")
                .setHeader("operationId", "order:create:T42:971")
                .setHeader("correlationId", "trace-84021")
                .build();

        Exception cause = new IllegalStateException("partner unavailable");
        MessagingException wrapped =
                new MessagingException(request, "handler failed", cause);

        ErrorMessage error = new ErrorMessage(wrapped, request);

        assertSame(request, error.getOriginalMessage());
        assertSame(request, wrapped.getFailedMessage());
        assertSame(cause, wrapped.getCause());
        assertEquals("trace-84021",
                error.getOriginalMessage().getHeaders()
                        .get("correlationId"));
    }
}
~~~

Đây là **unit test về object contract**; vì ta chủ động tạo `ErrorMessage`, nó **không chứng minh framework tự route lỗi từ một adapter**. Bài test route cần gửi message qua flow thật, quan sát channel và assert số attempts.

### 10.1. Business failure envelope

~~~json
{
  "failureId": "fail-20261123-001",
  "sourceAdapter": "sftp-orders",
  "destinationAdapter": "partner-http",
  "businessOperationId": "order:create:T42:971",
  "sourceMessageId": "msg-84021",
  "correlationId": "trace-84021",
  "errorCategory": "PARTNER_TIMEOUT",
  "terminalRetryState": "RETRY_EXHAUSTED",
  "attemptsObserved": 3,
  "outcome": "UNKNOWN_REQUIRES_RECONCILIATION",
  "payloadReference": "encrypted-store:orders/msg-84021",
  "owner": "integration-platform",
  "occurredAt": "2026-11-23T08:05:00Z"
}
~~~

Đây là **schema do ứng dụng định nghĩa**, không phải cấu trúc `ErrorMessage` do Spring tự sinh toàn bộ. **Không log raw payload, Authorization header, access token, mật khẩu SFTP hoặc session secret**.

## 11. Test error routing đồng bộ và bất đồng bộ

Một test đáng tin cần phân biệt hai cơ chế:

| Điều kiện | Assertion đúng |
| --- | --- |
| `DirectChannel` handler throws | Caller bắt exception nếu không có catch/route khác |
| Async handler qua `TaskExecutor`/poller error handler | Có `ErrorMessage` trên dedicated/global errorChannel theo cấu hình |
| Header `errorChannel` trỏ tới test channel | Test channel nhận lỗi trong đường hỗ trợ |
| Error publish thất bại | Lỗi được ghi/propagate theo chính sách, không báo fake-success |
| Error không có context gốc | Failure handler báo thiếu context có kiểm toán, không bịa dữ liệu |

### 11.1. Pseudocode test với QueueChannel

~~~text
Given:
    dedicatedErrorChannel = QueueChannel
    inbound message có header errorChannel = dedicatedErrorChannel
    handler chạy trong môi trường async được cấu hình ErrorMessage publisher
    handler ném SimulatedBusinessException

When:
    send message vào input channel

Then:
    error = dedicatedErrorChannel.receive(timeout)
    assert error is ErrorMessage
    assert rootCause(error.payload) is SimulatedBusinessException
    assert correlationId được giữ hoặc có mapping rõ
    assert không có business success result
~~~

Mấu chốt ở test này là **phải chạy qua đúng async error-handling boundary**. Nếu chỉ gửi message tới một `DirectChannel` rồi chờ queue, test có thể thất bại do kỳ vọng sai, không phải framework lỗi.

### 11.2. Poller và error handler

Khi test scheduled polling:

1. Ngăn poller production tự chạy khi context khởi động.
2. Dùng fake source/trigger giới hạn số lần poll.
3. Cấu hình hoặc xác nhận `MessagePublishingErrorHandler`.
4. Cho handler ném exception có thể nhận diện.
5. Assert `ErrorMessage` đến channel đã chỉ định.
6. Kiểm tra source state: file/JDBC row/broker record còn xử lý lại được hay không.

Không đánh đồng việc poller publish `ErrorMessage` với việc nguồn tự động rollback hoặc có DLQ.

## 12. Test retry exhaustion và recoverer

`RequestHandlerRetryAdvice` giúp thử lại một **message handler**. Có thể cấu hình `RecoveryCallback` để quyết định hậu quả sau khi retry hết lượt; `ErrorMessageSendingRecoverer` là một lựa chọn gửi ErrorMessage vào channel.

### 12.1. Những assertion phải có

1. Handler được gọi đúng **số attempts đã cấu hình và quan sát**.
2. Handler thành công trước khi hết lượt → **recoverer không chạy**.
3. Handler lỗi retryable tới giới hạn → **recoverer chạy** và nhận lỗi cuối.
4. Handler lỗi non-retryable → không retry vô ích; đi đúng nhánh theo policy.
5. Recoverer publish ErrorMessage tới **đúng channel**.
6. Recoverer failure → không nuốt lỗi để upstream ack sai.
7. Không gọi lại downstream lần thứ N+1 trong `RecoveryCallback` mà không kiểm soát.
8. Tổng attempts tính cả retry ở SDK, handler, container và broker.

### 12.2. Cảnh báo về version Spring Retry

Đừng chép một con số "retry mặc định" giữa các phiên bản Spring Integration/Spring Retry rồi kết luận số attempts từ cấu hình. Các API cấu hình mới có thể dùng `RetryPolicy.maxRetries`, trong khi ví dụ `RetryTemplate`/ `SimpleRetryPolicy` của Spring Retry 2.x dùng `maxAttempts`.

**Cách kiểm thử bền vững:** Cấu hình policy **rõ ràng**, đưa một `AtomicInteger` vào fake handler, quan sát `invokeCount` và terminal recovery. Khi viết tài liệu/hướng dẫn vận hành, ghi rõ thư viện và ý nghĩa "initial attempt" so với "retries".

### 12.3. Test matrix

| Case | Handler behavior | Expected |
| --- | --- | --- |
| Thành công ngay | Lần đầu trả thành công | 1 call, không recovery |
| Hai lần fail rồi thành công | Transient exceptions, sau đó OK | Chỉ đủ attempts cần thiết, không DLQ |
| Luôn fail | Retryable exception | Hết lượt, một terminal recovery theo flow |
| Non-retryable | Invalid payload/auth | Không retry nhiều lần, chuyển quarantine/propagate |
| Recoverer archive thành công | Error flow lưu bền | Terminal failure record, ack theo thiết kế |
| Recoverer archive lỗi | DB/broker recovery down | Failure propagate/giữ nguồn, không fake-success |
| Retry vẫn vượt timeout gateway | Caller hết hạn trước recovery | Thiết kế lại timeout budget |
| Broker redelivery sau handler retry | Source ném lại lỗi | Tổng attempts và DLQ đúng giới hạn |

## 13. Test error handler lỗi lần thứ hai

Đây là ca thường bị bỏ quên: **handler chính lỗi**, error flow cũng lỗi.

~~~mermaid
flowchart TD
    IN["Message nguồn"] --> MAIN["Business handler"]
    MAIN -->|Exception| RET["Retry / error publisher"]
    RET --> REC["Recovery handler"]
    REC -->|Persist succeeds| STORE["Durable failure record / DLQ"]
    REC -->|Persist fails| FAIL["Throw / NACK / rollback hoặc pause theo policy"]
    STORE --> ACK["Ack/commit chỉ sau khi đạt điều kiện"]
    FAIL --> HOLD["Source still owns message / recovery incident"]
~~~

Những trường hợp phải test:

- DB archive mất kết nối.
- DLQ broker không còn available.
- Serialization failure envelope lỗi.
- Quarantine store đầy.
- Error channel không có subscriber.
- Subscriber của error channel ném exception.
- App restart trước khi xác nhận lưu failure.

**Acceptance criterion:** Không xuất hiện trạng thái "source đã ack, main business chưa xử lý và failure record cũng không tồn tại", trừ khi hợp đồng cho phép mất dữ liệu có chủ đích và được ghi nhận.

## 14. Test dead-letter thực sự khác test ErrorMessage

Một test chỉ quan sát `ErrorMessage` trong `QueueChannel` mới chứng minh **error routing**, chưa chứng minh **dead-letter persistence**.

Dead-letter test cần có:

1. **Nguồn thật** hoặc broker test có behavior tương đương production.
2. **Failure được kích hoạt** theo cách adapter/container thật nhìn thấy.
3. **Retry/redelivery** xảy ra theo chính sách cấu hình.
4. **Terminal failure** được publish vào DLQ/DLT/quarantine.
5. **Record đọc lại được** với payload/reference và headers được giữ theo contract.
6. **Nguyên bản không bị mất** trong cửa sổ publish/ack.
7. **Replay** được kiểm thử với business key cố định.
8. Không để poison message vào DLQ rồi lại được tự động replay vô hạn.

### 14.1. Chọn thông tin để assert trong DLQ

| Trường | Mục đích |
| --- | --- |
| Source topic/queue/file | Truy vết từ đâu |
| Message ID / operation ID | Liên hệ với delivery và nghiệp vụ |
| Correlation ID | Gắn trace, transaction, failure |
| Error classification | Biết vì sao thất bại |
| Attempt lineage | Biết đã retry bao nhiêu lớp |
| Failure timestamp | Quản lý SLA, retention |
| Original payload/reference | Có thể replay và điều tra |
| Schema/version | Đọc lại đúng dữ liệu |
| Target destination | Biết đã fail ở adapter nào |
| Re-drive status/owner | Quản trị vòng đời DLQ |

Chỉ assert những headers/fields **được sản phẩm và contract hỗ trợ**. Không suy đoán mọi broker tự lưu cùng metadata.

### 14.2. Kiểm tra poison message

Lỗi permanent như schema không hợp lệ không nên bị retry vô hạn và làm nghẽn partition/queue. Test cần assert message chuyển đúng quarantine hoặc DLT sau policy, đồng thời những message lành mạnh phía sau tiếp tục được xử lý theo **ordering và error-handler semantics** của nguồn.

## 15. JMS: test rollback, redelivery và DLQ

Với JMS inbound adapter, behavior phụ thuộc listener container, `Session`, acknowledgment mode, transaction và broker dead-letter policy.

### 15.1. Case thành công

~~~text
Produce message K
 -> JMS consumer receives
 -> Spring Integration handler commits business result
 -> JMS transaction/ack succeeds

Assert:
  business output đúng
  source queue không còn bản ghi cần xử lý
  DLQ không có K
~~~

### 15.2. Case handler thất bại

~~~text
Produce K
 -> handler throws
 -> session rollback / consumer redelivery theo cấu hình
 -> số delivery đạt giới hạn của broker
 -> broker DLQ nhận K
~~~

**Không giả định** chỉ cần `ErrorMessageSendingRecoverer` là JMS broker DLQ sẽ nhận message. Nếu recoverer publish error rồi return bình thường, container có thể coi delivery thành công và commit theo cấu hình. Khi muốn broker tự DLQ, phải xác minh có **exception/rollback/nack** tương ứng.

### 15.3. Test checklist JMS

- Redelivery count/flag quan sát được trong broker dùng ở test.
- Rollback thực sự xảy ra khi handler hoặc recovery persistence lỗi.
- DLQ nhận đúng message sau terminal failure.
- Nếu failure archive thành công rồi listener ack, message không bị xử lý trùng.
- Connection restart giữa commit nghiệp vụ và JMS ack → idempotency vẫn đúng.
- Lỗi non-retryable được xử lý theo policy, không loop vô hạn.

## 16. AMQP/RabbitMQ: DLX, ack và requeue

RabbitMQ có acknowledgment, `basic.nack`/reject, requeue và dead-letter exchange (DLX) theo cấu hình. Spring AMQP listener container có behavior riêng đối với exception, retry advice và message conversion.

### 16.1. Test thiết kế broker DLQ

~~~text
orders.queue
   |
   | failed delivery, rejected/nacked without requeue
   v
orders.dead-letter-exchange
   |
   v
orders.dlq
~~~

Kiểm thử cần tạo exchange/queue/routing-key như test fixture **thực sự**, thay vì chỉ assert một string `deadLetterChannel` trong application.

### 16.2. Các trường hợp test

| Tình huống | Điều cần assert |
| --- | --- |
| Lỗi transient rồi success | Không có DLQ; message xử lý một lần về nghiệp vụ |
| Lỗi permanent | DLQ nhận đúng payload/reference sau policy |
| `requeue=true` không giới hạn | Phát hiện poison-message loop, không chấp nhận như terminal |
| DLX route sai | Message không biến mất âm thầm; test thất bại rõ |
| Consumer ack trước failure persistence | Test phát hiện nguy cơ mất operation |
| Broker restart | Durable queue/message còn theo cấu hình |
| Hai consumers | Duplicate/out-of-order và idempotency được kiểm tra |

### 16.3. Không suy DLQ chỉ từ log

Một `AmqpRejectAndDontRequeueException` hoặc cơ chế reject tương đương có thể dẫn đến DLX nếu broker queue được cấu hình phù hợp, nhưng **phải kiểm tra cả broker route**. Một log ghi "dead letter" không chứng minh DLQ thực sự có record.

## 17. Kafka: DLT, offset và container error handling

Với Kafka, **Spring Integration Kafka adapters** và **Spring for Apache Kafka listener container/error handler** có các ranh giới riêng. Khi dùng `DefaultErrorHandler` với `DeadLetterPublishingRecoverer` trong một cấu hình phù hợp, recovery có thể publish record lỗi tới **dead-letter topic (DLT)**.

**Không đồng nhất:**

- `ErrorMessageSendingRecoverer` của Spring Integration: gửi `ErrorMessage` vào một channel.
- `DeadLetterPublishingRecoverer` của Spring Kafka: publish một Kafka record lỗi sang topic theo cấu hình.
- Một `errorChannel` trong flow: đường thông điệp lỗi, không tự thay đổi consumer offset commit.

### 17.1. Luồng cần test

~~~mermaid
flowchart TD
    T["orders topic"] --> C["Consumer / SI inbound adapter"]
    C --> H["Business handler"]
    H -->|Success| COM["Commit/ack offset theo cấu hình"]
    H -->|Failure| EH["Listener/container error handler"]
    EH --> RET{"Còn retry?"}
    RET -->|Có| H
    RET -->|Không| DLT["DeadLetterPublishingRecoverer -> orders.DLT"]
    DLT --> VERIFY["Verify published DLT record"]
    VERIFY --> OFFSET["Offset/transaction result theo cấu hình"]
~~~

Sơ đồ tổng quát; chi tiết seek, retry, batch/record listener, transactional recovery và offset phụ thuộc phiên bản/config. Không được tự giả định một message chỉ đi qua đúng một tầng retry.

### 17.2. Test với Kafka broker cách ly

1. Tạo input topic và DLT với số partitions phù hợp policy.
2. Dùng consumer group riêng cho mỗi test, reset state giữa các ca.
3. Produce record mang `businessOperationId`.
4. Cho handler ném một exception được đánh dấu permanent hoặc retryable.
5. Quan sát retries và container callback đúng mức.
6. Dùng consumer riêng đọc record ở DLT.
7. Assert key, value/reference, origin topic/partition/offset headers nếu publisher cung cấp.
8. Assert trạng thái offset và không bỏ sót các record sau record lỗi.
9. Thử publisher DLT lỗi: không tự coi record đã recovered.

### 17.3. DLT publish failure quan trọng thế nào?

Nếu DLT producer fail, quy trình không được thông báo recovered như thể record đã lưu. Spring Kafka có những option để kiểm tra kết quả publish và xử lý recovery failure theo phiên bản. Test phải quan sát **publisher result và hành vi container** thay vì chỉ verify recoverer method đã được gọi.

### 17.4. Trường hợp lỗi deserialization

Lỗi key/value deserialization có thể xảy ra **trước khi business handler được gọi**. Với `ErrorHandlingDeserializer` hoặc cơ chế được hỗ trợ, container có thể nhận thông tin lỗi và đưa bản gốc vào DLT. Test cần:

- Produce bytes lỗi mà serializer/deserializer dự kiến từ chối.
- Confirm business handler không chạy.
- Confirm error path không chặn partition vô hạn.
- Confirm DLT chứa dữ liệu/references cần thiết theo security policy.

## 18. File/SFTP: quarantine và checkpoint

File/SFTP không có broker DLQ/ack tương tự JMS/AMQP/Kafka. Kiểm thử cần xem **file lifecycle**, filter metadata và per-record state.

### 18.1. Các điểm lỗi cần mô phỏng

| Điểm lỗi | Bằng chứng cần kiểm tra |
| --- | --- |
| SFTP connection/login failure | Adapter retry/error log; không tạo file local hỏng |
| Download giữa chừng | File staging không được xử lý như complete |
| File schema invalid | Đưa vào quarantine với reason/reference |
| Split record lỗi | Per-record recovery, file không được coi hoàn tất mù |
| File bị upload lại | Persistent filter và idempotency key hoạt động |
| App restart | Local/remote file state, filter metadata, replay chính xác |
| SFTP session leak | Session/stream được đóng sau success và failure |
| Quarantine store lỗi | Không move file sang DONE nếu chưa có bản sao bền |

### 18.2. Lỗi file-level khác record-level

~~~text
orders.csv
  row 1 -> COMPLETED
  row 2 -> INVALID_SCHEMA -> quarantine
  row 3 -> COMPLETED

File downloaded = true
File fully processed = phụ thuộc policy (all rows handled?)
~~~

Nếu file accept-once filter ghi nhận file đã tải, nhưng row 2 không có failure record, sau restart hệ thống có thể bỏ qua tác vụ. Test phải xác minh **file filter không được dùng thay bằng chứng per-record business outcome**.

### 18.3. Integration test SFTP

Có thể dùng một SFTP server test cô lập (Apache MINA SSHD hoặc container tương thích), upload một file fixture, khởi động inbound adapter với poller được kiểm soát, quan sát local staging và failure store. Test không nên kết nối SFTP production hoặc dùng credential thật.

## 19. HTTP inbound/outbound: mapping lỗi và outcome unknown

### 19.1. HTTP outbound gateway

Sử dụng HTTP mock server để mô phỏng:

- `503` hoặc timeout hai lần, sau đó `200` → thành công, không dead-letter.
- `400` invalid payload → lỗi permanent, quarantine theo policy.
- `401/403` → alert cấu hình/auth, không retry storm.
- `429` có rate limit → retry theo contract.
- Server **đã commit**, response bị ngắt → outcome unknown, không tự POST lại như thao tác mới.

Test tools gợi ý: MockRestServiceServer, WireMock, mock HTTP server/container, chọn theo HTTP client thật mà outbound adapter dùng.

### 19.2. HTTP inbound gateway

Với lỗi ở flow đồng bộ, verify:

- HTTP status/body tương ứng, không trả `200 OK` khi business chưa thành công.
- Correlation ID, error code và security redaction đúng.
- Caller retry giữ cùng Idempotency-Key.
- Duplicate của request đã hoàn tất nhận cached result/response hợp lệ.
- Khi lỗi sau khi đã lưu job bền, API có thể trả trạng thái `ACCEPTED/PENDING` theo contract thay vì giả DELIVERED.

Không dùng một test `QueueChannel` one-way để chứng minh request-reply gateway đã trả lỗi đúng cho client.

## 20. JDBC: failure table, row claim và rollback

Với JDBC inbound polling, lỗi thường liên quan transaction, row claim, concurrency và trạng thái xử lý.

### 20.1. Failure injection

~~~text
T0: poller SELECT row status=NEW
T1: claim row status=PROCESSING
T2: outbound handler lỗi
T3: retry exhausted
T4: ghi failure table/quarantine
T5: commit transaction / hoặc rollback theo policy
~~~

Các điểm phải kiểm tra:

- Nếu T4 persist lỗi, row không bị đánh dấu COMPLETED.
- Nếu transaction rollback, record còn khả năng poll lại.
- Nếu error flow persist thành công và row được đưa vào `RECOVERY_PENDING`, không còn bị poll thành duplicate mỗi vài giây.
- Hai pollers không cùng claim một row ngoài dự kiến.
- Có unique operation key và kiểm tra idempotency nếu upstream chèn hai hàng cho cùng operation.

### 20.2. Bảng trạng thái gợi ý

~~~sql
CREATE TABLE inbound_jobs (
    job_id           VARCHAR(100) PRIMARY KEY,
    operation_id     VARCHAR(200) NOT NULL,
    status           VARCHAR(40) NOT NULL,
    attempt_count    INT NOT NULL,
    failure_ref      VARCHAR(200),
    updated_at       TIMESTAMP NOT NULL
);
~~~

Schema này minh họa. Transaction/locking và upsert syntax cần chọn theo database thực tế; không coi `failure_ref != null` là bằng chứng failure store đã lưu bền nếu không có cơ chế xác minh tương ứng.

## 21. Ví dụ integration test: retry exhaustion tới dedicated recovery channel

Ví dụ dưới đây sử dụng **Spring Integration Java DSL**, một fake handler luôn lỗi, `RequestHandlerRetryAdvice` và `ErrorMessageSendingRecoverer`. Test gửi message tới `DirectChannel` rồi kiểm tra `QueueChannel` phục vụ recovery.

**Phạm vi phiên bản:** Ví dụ dùng API `RetryTemplate`/`SimpleRetryPolicy` theo phong cách **Spring Integration 6.x và Spring Retry 2.x**. Spring Integration/Spring Retry mới hơn có API policy khác; cần đối chiếu dependencies của dự án khi dùng nguyên mã. Mục tiêu test không đổi: **đếm attempts thực tế và xác nhận message terminal ở recovery channel**.

### 21.1. Test configuration

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.retry.backoff.NoBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
@EnableIntegration
class RecoveryFlowTestConfig {

    @Bean
    MessageChannel testRequests() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel testRecoveryChannel() {
        return new QueueChannel();
    }

    @Bean
    AtomicInteger handlerAttempts() {
        return new AtomicInteger();
    }

    @Bean
    RequestHandlerRetryAdvice testRetryAdvice(
            QueueChannel testRecoveryChannel) {

        RetryTemplate retryTemplate = new RetryTemplate();
        retryTemplate.setRetryPolicy(new SimpleRetryPolicy(3));
        retryTemplate.setBackOffPolicy(new NoBackOffPolicy());

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(retryTemplate);
        advice.setRecoveryCallback(
                new ErrorMessageSendingRecoverer(testRecoveryChannel));
        return advice;
    }

    @Bean
    IntegrationFlow testFailureFlow(
            AtomicInteger handlerAttempts,
            RequestHandlerRetryAdvice testRetryAdvice) {

        MessageHandler alwaysFail = message -> {
            handlerAttempts.incrementAndGet();
            throw new IllegalStateException("simulated partner outage");
        };

        return IntegrationFlow.from("testRequests")
                .handle(alwaysFail, endpoint -> endpoint.advice(testRetryAdvice))
                .get();
    }
}
~~~

`NoBackOffPolicy` giúp test nhanh và ít phụ thuộc clock. Trong production, backoff/rate limiting phải thiết kế theo downstream SLA; **không lấy cấu hình test zero backoff để triển khai thật**.

### 21.2. JUnit test

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(RecoveryFlowTestConfig.class)
class RecoveryFlowIntegrationTest {

    @Autowired
    MessageChannel testRequests;

    @Autowired
    QueueChannel testRecoveryChannel;

    @Autowired
    AtomicInteger handlerAttempts;

    @Test
    void publishesOneTerminalErrorAfterThreeAttempts() {
        Message<String> input = MessageBuilder
                .withPayload("order-971")
                .setHeader("businessOperationId", "order:create:T42:971")
                .build();

        // Bắt đầu bằng một message mới; bean counter có phạm vi test context.
        assertTrue(testRequests.send(input));

        Message<?> terminal = testRecoveryChannel.receive(1_000);
        assertNotNull(terminal);
        assertInstanceOf(ErrorMessage.class, terminal);
        assertEquals(3, handlerAttempts.get());

        Throwable error = ((ErrorMessage) terminal).getPayload();
        assertNotNull(error);

        Throwable root = error;
        while (root.getCause() != null) {
            root = root.getCause();
        }
        assertInstanceOf(IllegalStateException.class, root);
        assertEquals("simulated partner outage", root.getMessage());

        // Không có error message terminal thứ hai.
        assertNull(testRecoveryChannel.receive(0));
    }
}
~~~

**Điều mà test chứng minh:** Handler đã được advice gọi ba lần theo policy thử nghiệm; terminal error đi tới dedicated recovery channel. **Điều test chưa chứng minh:** Recovery được lưu bền, broker ACK an toàn hay remote operation chưa được thực hiện.

### 21.3. Cách mở rộng test

Thêm các trường hợp:

- Fake handler fail hai lần rồi success: recoverer **không** được publish error.
- Fake handler luôn ném exception được phân loại non-retryable: số attempts đúng policy.
- Recovery handler lưu vào fake archive và có thể nhận diện source operation ID.
- Archive ném exception: test không báo message như đã xử lý an toàn.
- Với một gateway cần reply, test contract của caller thay vì chỉ test `send`.

Nếu mỗi test chia sẻ `AtomicInteger` và `QueueChannel` trong cùng context, phải **reset/drain** có kiểm soát trong `@BeforeEach` hoặc dùng context isolation phù hợp. Không để test chạy phụ thuộc thứ tự.

## 22. Test recovery handler và durable archive

Một `ErrorMessageSendingRecoverer` gửi lỗi đi, còn **application recovery handler** mới có nhiệm vụ ghi bền failure. Test cần tách hai cấp:

- **Unit:** Handler chuyển ErrorMessage thành failure record đúng, không làm lộ secret.
- **Integration:** Record tồn tại trong DB/DLQ sau restart và việc publish được xác nhận.

### 22.1. Giao diện ứng dụng

~~~java
// Đây là giao diện nghiệp vụ tự định nghĩa, không phải API của Spring.
interface FailureArchive {
    void save(FailureRecord record);
}

record FailureRecord(
        String businessOperationId,
        String errorType,
        String state,
        String payloadReference) {}
~~~

Một recovery handler có thể chuyển từ ErrorMessage sang record như sau:

~~~java
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

final class RecoveryArchiveHandler {
    private final FailureArchive archive;

    RecoveryArchiveHandler(FailureArchive archive) {
        this.archive = archive;
    }

    void handle(ErrorMessage error) {
        Throwable failure = error.getPayload();
        Message<?> original = error.getOriginalMessage();

        if (original == null && failure instanceof MessagingException m) {
            original = m.getFailedMessage();
        }
        if (original == null) {
            throw new IllegalStateException(
                    "Cannot archive failure: original context is missing",
                    failure);
        }

        String operationId =
                String.valueOf(original.getHeaders().get("businessOperationId"));
        if ("null".equals(operationId) || operationId.isBlank()) {
            throw new IllegalArgumentException(
                    "Cannot archive failure without businessOperationId");
        }

        // Chỉ lưu payloadReference an toàn, không lưu raw payload nhạy cảm.
        FailureRecord record = new FailureRecord(
                operationId,
                failure.getClass().getName(),
                "RETRY_EXHAUSTED",
                "encrypted-ref:example"
        );
        archive.save(record);
    }
}
~~~

Code là ví dụ học tập để thể hiện **fail closed** nếu context tối thiểu không có. Trong sản phẩm thật, có thể dùng **correlation ID hoặc nguồn metadata bền vững** để khôi phục context hợp lệ thay vì ném lỗi ngay; nhưng không nên tự bịa `businessOperationId`.

### 22.2. Test khi archive hoạt động

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

import static org.mockito.Mockito.*;

class RecoveryArchiveHandlerTest {

    @Test
    void archivesFailedOperation() {
        FailureArchive archive = mock(FailureArchive.class);
        RecoveryArchiveHandler handler = new RecoveryArchiveHandler(archive);

        Message<String> original = MessageBuilder.withPayload("redacted")
                .setHeader("businessOperationId", "create:T42:971")
                .build();
        ErrorMessage error = new ErrorMessage(
                new MessagingException(original, "handler failed"),
                original);

        handler.handle(error);

        verify(archive).save(argThat(record ->
                "create:T42:971".equals(record.businessOperationId())
                && "RETRY_EXHAUSTED".equals(record.state())));
        verifyNoMoreInteractions(archive);
    }
}
~~~

**Giới hạn:** Mockito `verify(save)` chỉ chứng minh **gọi method** chứ không chứng minh DB/broker commit. Test lưu bền phải đọc lại record qua storage thực.

### 22.3. Test khi archive lỗi

~~~java
// Minh họa assertion chính trong test, dùng original/error như test ở trên.
doThrow(new IllegalStateException("failure DB unavailable"))
        .when(archive).save(any(FailureRecord.class));

assertThrows(IllegalStateException.class, () -> handler.handle(error));
~~~

Sau đó dùng adapter integration test để chứng minh **exception khi archive lỗi** khiến broker/poller xử lý theo retry/rollback hoặc cơ chế giữ nguồn đã thiết kế. Không dừng ở unit assertion.

## 23. Kiểm tra acknowledgment, offset và transaction

Đây là nhóm test **quan trọng hơn việc đếm stack traces**. Việc recoverer xử lý thành công theo mã ứng dụng có thể làm nguồn xem message hoàn tất.

### 23.1. Ma trận trạng thái

| Business outcome | Failure archived | Source ACK/commit | Đánh giá |
| --- | --- | --- | --- |
| Thành công, có bằng chứng | Không cần | Có | Thường phù hợp |
| Thất bại, archive bền và có replay owner | Có | Có theo contract | Có thể phù hợp nếu đã bàn giao trách nhiệm |
| Thất bại, archive bền | Có | Không, broker redeliver | Có thể tạo duplicate failure; cần idempotent archive |
| Thất bại, archive cũng lỗi | Không | Có | **Nguy cơ mất message** |
| Thất bại, archive cũng lỗi | Không | Không, nguồn giữ message | Phù hợp với fail-safe được thiết kế |
| Outcome unknown sau remote timeout | Có metadata đối soát | Tùy contract | Cần reconciliation/idempotency trước replay |

### 23.2. Crash windows phải test

~~~text
F1  Trước khi nhận message.
F2  Sau khi nhận nhưng trước business handler.
F3  Sau khi downstream commit nhưng trước response.
F4  Sau khi business result commit nhưng trước source ACK.
F5  Sau retry exhaustion nhưng trước archive.
F6  Sau archive persist nhưng trước source ACK.
F7  Trong lúc publish DLT/DLQ.
F8  Sau khi đã publish DLT nhưng trước commit source offset.
F9  Sau khi bắt đầu replay nhưng trước khi lưu replay result.
~~~

Với mỗi điểm lỗi, cần biết **source có redeliver không, failure record có tồn tại không, business effect có bị lặp không**. Không cần giả lập crash bằng cách kill JVM ở mọi unit test; có thể dùng targeted integration tests và một số restart tests có kiểm soát.

### 23.3. Test redelivery sau commit

Giả sử service đã ghi DB cho operation `K`, nhưng broker ACK thất bại và redeliver. Receiver phải kiểm tra `K` đã `COMPLETED` và **không tạo side effect thứ hai**. Phần này được thực thi bởi **idempotent receiver/unique constraint/inbox**, không phải `ErrorMessage` tự bảo đảm.

## 24. Kiểm thử số lần retry qua nhiều tầng

Một inbound adapter có thể chịu:

- SDK HTTP client tự retry.
- `RequestHandlerRetryAdvice` của Spring Integration.
- Spring Kafka hoặc Spring AMQP container retry.
- Broker redelivery sau rollback.
- Replay job hoặc consumer restart.

Ví dụ cấu hình giả định:

~~~text
HTTP client:           2 attempts / handler invocation
SI handler advice:     3 attempts / broker delivery
Broker redeliveries:   4 delivery attempts

Tổng số downstream HTTP requests tối đa trong kịch bản xấu:
    2 x 3 x 4 = 24
~~~

Con số là **ví dụ về phép nhân tầng retry**, không phải giá trị mặc định. Test nên đưa counter/mock server tại **ranh giới external request** để đo số lần thật, không chỉ counter của message handler.

### 24.1. Timeout budget

Nếu một request HTTP có timeout 2 giây và handler cho phép ba attempts, cộng backoff 0,5 giây và 1 giây, worst-case xấp xỉ **7,5 giây** (chưa gồm overhead). Nếu inbound gateway chỉ chờ 5 giây, caller có thể timeout **trước khi retry exhaustion được xử lý**.

Test:

- Gateway timeout và end-to-end latency.
- Thread pool không bị bão hòa bởi retries.
- Backoff/rate limit của upstream và downstream.
- Error flow vẫn xử lý sau khi client đã disconnect.
- Không tiếp tục tạo side effect khi request đã bị hủy nếu contract quy định cancel.

## 25. Kiểm thử replay từ DLQ/quarantine

Đưa message vào DLQ chỉ là **điểm bắt đầu** của vòng đời lỗi. Replay có thể phải:

1. Xác minh lỗi đã được khắc phục.
2. Phân loại message permanent vs transient vs outcome unknown.
3. Kiểm tra business state tại downstream.
4. Giữ **operation ID gốc** và payload fingerprint.
5. Ghi `replayAttempt`/`replayId` riêng để kiểm toán.
6. Giới hạn số replay, rate và concurrency.
7. Xác nhận kết quả ở downstream.
8. Đánh dấu failure record `REPLAYED`, `RESOLVED` hoặc `ESCALATED` theo contract.

### 25.1. Replay test matrix

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Transient outage đã hết | Replay thành công và đóng failure |
| Invalid payload chưa sửa | Không replay vô hạn; giữ quarantine |
| Outcome đã commit từ lần trước | Không tạo duplicate; reconcile thành công |
| DLQ message thiếu schema/version | Phát hiện lỗi đọc và escalation |
| Replay publish thất bại | Không đánh dấu resolved |
| Hai operator replay cùng operation | Atomic claim, không nhân đôi side effect |
| Replay vượt rate limit | Backoff/backpressure, không đánh sập downstream |
| Payload nhạy cảm | Không log raw body, chỉ lấy qua quyền hạn tương ứng |
| Failure đã bị xóa theo retention | Chứng minh lifecycle/retention hợp lệ, không bịa dữ liệu |

### 25.2. Không thay idempotency key khi replay

~~~text
original operation key: order:create:T42:971
first delivery id:      msg-100
DLQ message id:         dlq-308
replay delivery id:     replay-22

Idempotency key dùng gọi downstream:
    vẫn là order:create:T42:971
~~~

Nếu tạo một operation key mới mỗi replay, downstream có thể coi đó là một lệnh nghiệp vụ mới và tạo side effect trùng.

## 26. Correlation, observability và bảo mật failure data

### 26.1. Các chỉ số cần quan sát

| Metric gợi ý | Vì sao cần? |
| --- | --- |
| `integration_error_total` | Tổng errors theo adapter/flow/category |
| `integration_retry_attempt_total` | Attempts theo cấp retry |
| `integration_retry_exhausted_total` | Terminal retry failures |
| `integration_error_message_published_total` | Số ErrorMessage được publish |
| `integration_error_message_delivery_failed_total` | Lỗi route tới error channel |
| `integration_failure_archive_success_total` | Failure record ghi thành công |
| `integration_failure_archive_failed_total` | Lỗi của recovery sink |
| `integration_dlq_publish_total` | Bản tin được publish vào DLQ/DLT |
| `integration_dlq_backlog` | Số failure chờ xử lý |
| `integration_dlq_oldest_age` | Tuổi message lâu nhất chưa giải quyết |
| `integration_replay_total` | Replay attempts, success/fail |
| `integration_outcome_unknown_total` | Giao dịch cần reconciliation |
| `integration_source_lag` | Backlog của source/file/poller/broker |
| `integration_ack_after_archive_fail_total` | Phát hiện nguy cơ mất message |

Đây là **metric names ứng dụng có thể thiết kế**, không phải toàn bộ metric mặc định được framework tự tạo. Tránh dùng business ID, message ID hoặc tenant ID làm metric label có cardinality cao.

### 26.2. Log failure an toàn

~~~json
{
  "event": "integration.dead_letter.recorded",
  "flow": "sftp-orders-to-partner-http",
  "sourceAdapter": "sftp",
  "destination": "partner-http",
  "correlationId": "trace-84021",
  "operationKeyRef": "hash:example",
  "exceptionCategory": "RETRYABLE_TIMEOUT",
  "recoveryAction": "STORE_FOR_RECONCILIATION",
  "failureRecordId": "fail-20261123-001",
  "status": "PERSISTED",
  "occurredAt": "2026-11-23T08:05:00Z"
}
~~~

**Không ghi raw secrets**, access key, password SFTP, Authorization header, cookie, PII hoặc payload khách hàng vào log/metric. Có thể dùng encrypted payload reference, correlation và schema version để điều tra.

### 26.3. Test log và audit

- Exception category được map đúng.
- Correlation liên kết được original message → retry → DLQ → replay.
- Attempts là giá trị quan sát, không hardcode.
- Log không chứa credential hoặc thông tin nhạy cảm.
- Failure record có owner, deadline/review SLA.
- Thời điểm failure, persist và replay có timezone/định dạng chuẩn.
- Những trạng thái `PERSISTED`, `REPLAY_PENDING` và `DELIVERED` không bị đồng nhất.

## 27. Kiến trúc test environment an toàn

Một test environment tốt có các ranh giới tách biệt:

~~~mermaid
flowchart LR
    JUNIT["JUnit 5 / Spring Test"] --> CTX["Spring Integration test context"]
    CTX --> SRC["Mock source / Testcontainers broker / SFTP fixture"]
    SRC --> FLOW["Flow under test"]
    FLOW --> HTTP["HTTP stub server"]
    FLOW --> DB["Disposable DB / failure archive"]
    FLOW --> DLT["Test DLQ/DLT"]
    DLT --> ASSERT["DLQ consumer + assertions"]
    DB --> ASSERT
    CTX --> ASSERT
~~~

### 27.1. Bảo đảm cách ly

- Dùng topic/queue/schema/test directory riêng; ưu tiên random test identifier.
- Không dùng production credentials hoặc endpoints.
- Clean messages, failure store, offsets, metadata sau test.
- Đóng connection, listener container, task executor và SFTP server fixture.
- Không để poller chạy nền sau test.
- Dùng cấu hình hạn chế retry/backoff cho test nhưng vẫn giữ **semantics** cần kiểm chứng.
- Với tests chạy parallel, tránh shared state hoặc dùng namespace riêng.
- Không phụ thuộc vào clock và scheduler theo cách làm test flakey.

### 27.2. Những thứ không nên mock

Muốn chứng minh một đặc tính, **phải giữ thành phần thực sự sở hữu đặc tính đó**:

| Cần chứng minh | Không nên chỉ mock |
| --- | --- |
| Kafka offset commit / DLT routing | `MessageChannel` hoặc `KafkaTemplate.send` |
| JMS session rollback | Listener method |
| RabbitMQ DLX / requeue | Error flow handler |
| File accept-once sau restart | `FileMessageSource` đơn giản |
| SFTP stream cleanup | Parser với String payload |
| JDBC transaction atomicity | Repository mock |
| HTTP status/timeout | DirectChannel thay cho HTTP gateway |
| Failure persistence | Mock `FailureArchive.save()` |

Mock có giá trị cho **logic nhỏ và wiring**, nhưng **không thay thế system boundary** mà test đang hứa kiểm chứng.

## 28. Golden test plan cho một flow SFTP → HTTP → DB

Giả sử mỗi record từ file SFTP được chuyển thành HTTP request tạo vận đơn; kết quả lưu DB.

### 28.1. Danh sách test bắt buộc

| ID | Case | Điều kiện | Acceptance |
| --- | --- | --- | --- |
| T01 | Happy path | File hợp lệ, partner OK | Delivered; không DLQ |
| T02 | Transient recover | Hai timeout rồi OK | Retry đúng, không terminal error |
| T03 | Retry exhausted | Partner luôn timeout | Failure record bền + correlation |
| T04 | Permanent invalid | Record thiếu field | Quarantine, không retry HTTP |
| T05 | Remote outcome unknown | Partner commit rồi response mất | Không tạo vận đơn trùng |
| T06 | Failure archive down | DB failure store lỗi | Nguồn không bị mất trách nhiệm xử lý |
| T07 | Restart after download | App restart trước xử lý xong | File/record còn khả năng phục hồi |
| T08 | Duplicate file | SFTP gửi lại file | Không tạo duplicate business effect |
| T09 | Re-drive | Partner phục hồi | Replay đúng operation key và đóng record |
| T10 | Poison message | Một record vĩnh viễn lỗi | Không chặn toàn luồng theo policy |
| T11 | Concurrent consumers | Hai instance nhận cùng record | Idempotency/claim đúng |
| T12 | Security | Failure payload chứa credential giả | Không rò log/metrics/DLQ không được bảo vệ |
| T13 | DLQ full/down | Recovery destination không thể lưu | Fail-safe và alert |
| T14 | Connection recovery | SFTP/HTTP bị cắt kết nối | Không leak session/thread |
| T15 | Late response | Response đến sau caller timeout | Outcome được đối soát, không báo fake-fail |

### 28.2. Vì sao test T06 quan trọng?

T06 phát hiện một lỗi thiết kế phổ biến: recoverer nhận `ErrorMessage`, archive `save` thất bại, code bắt exception rồi chỉ log. Inbound flow trả thành công khiến nguồn được ack, nhưng cả business result lẫn failure record đều không có. Một hệ thống có mọi "happy path" test xanh vẫn có thể mất message vì thiếu ca này.

### 28.3. Vì sao test T05 quan trọng?

HTTP timeout không cho biết server đã commit hay chưa. Nếu test chỉ mô phỏng server trả `500` trước khi xử lý, nó không đo được nguy cơ duplicate. Cần mock server có khả năng:

1. Lưu side effect ứng dụng.
2. Cố tình không trả hoặc ngắt response.
3. Ghi số lần cùng Idempotency-Key được xử lý.
4. Cho phép query trạng thái bằng business reference.

Kết quả kỳ vọng: Application đối soát và không tạo vận đơn lần hai.

## 29. Khi test lỗi: phân biệt lỗi test với lỗi sản phẩm

Một test bất đồng bộ thất bại vì `receive(1000)` trả null có thể do:

- Error channel không được route đúng.
- Endpoint không chạy hoặc autoStartup bị tắt.
- TaskExecutor chưa dispatch.
- Error message được gửi global errorChannel khác.
- Subscriber đã tiêu thụ message trước khi test đọc.
- Retry/backoff dài hơn test timeout.
- Handler error bị nuốt bởi callback khác.
- Broker không phát redelivery vì transaction/ack mode khác dự kiến.

### 29.1. Quy trình debug có hệ thống

1. Xác nhận test input được nhận và endpoint tồn tại.
2. Xác nhận handler thực sự chạy: counter hoặc spy.
3. Xác nhận exception được ném trong thread/rành giới dự kiến.
4. Tìm error channel được resolve từ header hay global.
5. Đếm retries và kiểm tra `RecoveryCallback` có được gọi không.
6. Kiểm tra channel subscriber/dispatcher hoặc consumer nào đã đọc message.
7. Kiểm tra transaction/ack/offset của source.
8. Kiểm tra DLQ publish result và tiêu thụ từ test consumer.
9. Tăng test timeout hợp lý **chỉ khi** căn cứ chứng minh hệ thống đúng nhưng môi trường chậm.

**Đừng chữa test đỏ bằng cách thêm `Thread.sleep(5000)` vô điều kiện.** Nó che giấu race và làm test suite chậm/flaky.

## 30. Anti-pattern phổ biến

| Anti-pattern | Hậu quả | Cách test đúng |
| --- | --- | --- |
| Chỉ test happy path | Không biết dữ liệu có mất khi lỗi không | Failure injection + recovery assertions |
| Coi mọi exception đều publish global errorChannel | Test sai với DirectChannel | Phân biệt synchronous/async/poller |
| Chỉ verify log ERROR | Lỗi có thể bị bỏ, không có replay | Assert durable failure record |
| Coi QueueChannel là broker DLQ | Qua restart message có thể mất | Integration test broker/file/DB thật |
| Count retry chỉ ở handler | Bỏ qua SDK/broker retries | Đo downstream boundary requests |
| Recoverer return null được coi thành công | Upstream có thể ack sai | Assert business outcome và ack |
| Nuốt lỗi trong recovery handler | Silent loss | Test archive failure, propagate/fail-safe |
| Đếm đúng DLQ nhưng không test offset | Có thể mất hoặc lặp message | Broker ack/commit assertions |
| Assert stack trace nguyên văn | Flaky theo version | Root cause, category, correlation |
| Mock KafkaTemplate rồi tuyên bố DLT an toàn | Không kiểm chứng broker publish | Testcontainers/embedded Kafka |
| Auto-start SFTP poller trong unit test | Gọi hệ thống ngoài hoặc race | `noAutoStartup`, fake source/trigger |
| Retry invalid schema nhiều lần | Poison message làm nghẽn | Non-retryable/quarantine test |
| Replay tạo ID nghiệp vụ mới | Duplicate side effect | Giữ stable operation key |
| Không phân biệt FAILED và OUTCOME_UNKNOWN | Replay mù khi server đã commit | Test remote commit + lost response |
| Không test parallel consumers | Duplicates khi scale-out | Shared store/DB unique constraint tests |
| Ghi raw payload/secret vào DLQ | Rò dữ liệu | Redaction, encrypted reference, ACL |
| Test phụ thuộc `Thread.sleep` | Flaky và chậm | Bounded waits/latch/Awaitility |
| Không test shutdown/restart | Inflight messages bị bỏ quên | Crash/restart drill |

## 31. Bài tập tự kiểm tra

### Bài 1. DirectChannel và errorChannel

**Tình huống:** Test gửi message tới `DirectChannel`; handler ném exception; test chờ global `errorChannel` nhưng không nhận gì.

**Đáp án:** Có thể test giả định sai. Với flow đồng bộ, lỗi thường lan về caller. Hãy assert exception hoặc cấu hình cơ chế catch/route rõ, không mặc định global errorChannel.

### Bài 2. ErrorMessage đã xuất hiện

**Tình huống:** Test nhận ErrorMessage từ dedicated QueueChannel và đánh dấu DLQ thành công.

**Đáp án:** Chưa đủ. QueueChannel trong bộ nhớ không phải durable broker DLQ; cần test error flow đã publish/lưu bền và đọc lại failure.

### Bài 3. Retry 3 lần

**Tình huống:** Nhóm phát triển cấu hình `maxRetries=3` và giả định có đúng ba lần gọi tính cả lần đầu.

**Đáp án:** Phải kiểm tra API/version: `maxRetries` thường đếm số lần **retry**, khác `maxAttempts` có thể tính cả lần đầu. Cấu hình rõ và assert counter thực tế.

### Bài 4. JMS đã ack

**Tình huống:** Recovery handler ghi log rồi return bình thường; JMS queue không còn message, DLQ trống.

**Đáp án:** Nguy cơ silent loss. Cần failure persistence có kiểm chứng hoặc ném lỗi để rollback/redelivery theo container/broker policy.

### Bài 5. Kafka DLT

**Tình huống:** Mockito xác nhận `DeadLetterPublishingRecoverer.accept()` được gọi nhưng DLT topic rỗng.

**Đáp án:** Test mock không chứng minh publish. Cần test với broker thật và kiểm tra publish result, DLT record và offset.

### Bài 6. HTTP timeout

**Tình huống:** Client gọi tạo đơn, timeout, message vào recovery store. Sau đó operator replay ngay.

**Đáp án:** Có thể tạo trùng nếu remote đã commit trước timeout. Phải đối soát bằng operation ID/idempotency key hoặc query status trước replay.

### Bài 7. SFTP file đã tải

**Tình huống:** File có 100 dòng; 99 dòng thành công, một dòng lỗi; persistent file filter đánh dấu file đã nhận.

**Đáp án:** File accept-once không chứng minh mọi dòng đã xử lý. Cần per-record outcome, quarantine/replay và file lifecycle test.

### Bài 8. Recovery archive lỗi

**Tình huống:** DLQ publisher không kết nối được; recovery handler bắt exception rồi trả bình thường.

**Đáp án:** Nếu nguồn ack/commit, có thể mất operation. Bắt buộc test fail-safe: không báo recovered, nguồn còn trách nhiệm hoặc có kênh lưu bền dự phòng được xác minh.

### Bài 9. Backoff và gateway timeout

**Tình huống:** Retry budget vượt thời hạn caller chờ.

**Đáp án:** Test gateway timeout, latency budget và error contract. Cân nhắc asynchronous accepted workflow hoặc giảm attempts/backoff; đừng chỉ tăng timeout tùy tiện.

### Bài 10. Redelivery sau business commit

**Tình huống:** JDBC commit xong, RabbitMQ ACK mất; record được redeliver.

**Đáp án:** Dedupe theo stable operation ID và inbox/unique constraint; test không có side effect thứ hai, đồng thời broker ack theo policy sau khi nhận diện outcome.

## 32. Checklist triển khai test error flow và dead-letter

1. **Phân loại lỗi:** Có transient, permanent, auth, schema và outcome unknown.
2. **Xác định boundary:** Handler trên DirectChannel, executor, poller hay broker listener?
3. **Đúng channel:** Header errorChannel, global errorChannel hoặc recovery channel explicit.
4. **ErrorMessage đủ ngữ cảnh:** Root cause, failed/original message, correlation khi có.
5. **Không dựa vào stack trace:** Assert hành vi và contract.
6. **Retry rõ ràng:** Attempts, backoff, non-retryable, timeout budget.
7. **Recovery rõ ràng:** Propagate, durable archive, DLQ, quarantine hoặc fallback hợp lệ.
8. **Archive failure:** Test lỗi ở chính recovery path và fail-safe.
9. **DLQ bền:** Có record đọc lại từ broker/store thật.
10. **Ack/commit đúng:** Không xác nhận nguồn trước khi có business result hoặc handoff bền phù hợp.
11. **Kafka offset/JMS/AMQP:** Test với container/broker có semantics thực.
12. **File/SFTP:** Test source filter, staging, per-record failure và session cleanup.
13. **HTTP:** Test status/reply, retry timing, idempotency và lost response.
14. **JDBC:** Test transaction, row claim, unique constraint và recover state.
15. **Poison message:** Không gây redelivery vô hạn hoặc nghẽn toàn luồng.
16. **Replay:** Stable operation key, owner, audit, reconciliation và rate limit.
17. **Parallel/restart:** Có test concurrency, crash và redelivery sau commit.
18. **Observability:** Errors, DLQ backlog, recovery failure, oldest age và unknown outcomes.
19. **Bảo mật:** Không leak token/PII trong error message, log và DLT.
20. **Cách ly test:** Mock nguồn phù hợp, noAutoStartup, cleanup và resource disposal.
21. **Đúng version:** Kiểm tra Spring Integration, Spring Retry, Spring Kafka/AMQP, broker API của dự án.
22. **Chỉ công bố điều đã kiểm chứng:** Unit routing không thay thế broker DLQ end-to-end.

## 33. Tài liệu tham khảo chính thức

Để đối chiếu APIs và behavior theo version dự án:

1. **Spring Integration — Error Handling:** https://docs.spring.io/spring-integration/reference/error-handling.html
2. **Spring Integration — Testing Support:** https://docs.spring.io/spring-integration/reference/testing.html
3. **Spring Integration — Provided Advice Classes / RequestHandlerRetryAdvice:** https://docs.spring.io/spring-integration/reference/handler-advice/classes.html
4. **Spring Integration — Message Channels:** https://docs.spring.io/spring-integration/reference/channel.html
5. **Spring Kafka — Handling Exceptions / DeadLetterPublishingRecoverer:** https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
6. **Spring AMQP — Exception Handling:** https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html
7. **Spring Integration — SFTP Support:** https://docs.spring.io/spring-integration/reference/sftp.html

Ví dụ sử dụng **JUnit 5**, Spring Test, Java DSL và APIs thường gặp. Những module Spring Integration/Spring Retry phiên bản mới có thể đổi method cấu hình retry hoặc cách kết hợp API; vì vậy mọi đoạn mã phải được đối chiếu, biên dịch và chạy test trong **version BOM** của dự án trước khi đưa vào production. Trong bước viết học liệu này, các đoạn mã là ví dụ để người học áp dụng; chúng **không được xác nhận đã chạy build tại repository**.

## 34. Tổng kết

**Test error flow và dead-letter** phải kiểm tra toàn bộ hành trình thất bại của message, không chỉ kiểm tra một exception hoặc một dòng log. Spring Integration cung cấp `ErrorMessage`, `errorChannel`, `MessagePublishingErrorHandler`, `RequestHandlerRetryAdvice`, `RecoveryCallback` và `ErrorMessageSendingRecoverer` để xây các đường xử lý lỗi; JMS/AMQP/Kafka và từng inbound adapter bổ sung **transaction, acknowledgment, offset, redelivery và dead-letter semantics** của riêng mình.

Một bộ test đáng tin cần kết hợp **unit test về error contract**, **flow test về routing/retry**, **adapter integration test với broker/server thật**, và **failure-injection test về crash, archive failure, lost response và replay**. Chỉ coi message đã được bàn giao an toàn khi **business outcome có bằng chứng, hoặc failure đã được lưu bền và nguồn được ACK theo chính sách được xác minh**. Cùng với idempotency, reconciliation, observability và runbook, cách kiểm thử này giúp luồng tích hợp không chỉ phát hiện lỗi mà còn **không làm mất hoặc nhân đôi tác vụ nghiệp vụ khi xảy ra sự cố**.
