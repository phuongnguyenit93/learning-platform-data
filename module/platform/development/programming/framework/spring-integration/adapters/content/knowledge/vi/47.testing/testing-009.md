# Test retry và recoverer trong Spring Integration Adapters

Giả sử một ứng dụng nhận đơn hàng từ Kafka, gọi HTTP API đối tác rồi cập nhật cơ sở dữ liệu. Khi HTTP trả `503 Service Unavailable`, có thể **retry** để thử lại; khi dịch vụ trả `400 Bad Request` do dữ liệu sai, retry nhiều lần thường không giúp gì; khi quá số lần thử, ứng dụng cần **recoverer** để ghi nhận thất bại, chuyển thông điệp sang nhánh xử lý có kiểm soát, thông báo vận hành hoặc đưa vào dead-letter/quarantine phù hợp.

Nhưng có một câu hỏi còn quan trọng hơn: nếu HTTP request đầu **đã tạo đơn thành công**, chỉ có response bị mất, việc retry có thể **tạo đơn trùng**. Vì thế test retry/recoverer không thể dừng ở `verify(handler, times(3))`; còn phải kiểm tra **phạm vi retry, loại lỗi được thử lại, khoảng chờ, điểm kết thúc, trạng thái dữ liệu, tính idempotent, bằng chứng hồi phục và tình huống recoverer tự thất bại**.

Bài **“Test retry và recoverer”** thuộc chương **Testing** của module `SPRING_INTEGRATION_ADAPTERS`. Trong module này, Spring Integration dùng **inbound/outbound adapter, gateway, poller và `MessageChannel`** để kết nối File, SFTP, HTTP, JMS, AMQP, Kafka và database. Bài tập trung vào kiểm thử **retry tại endpoint, Spring Retry và `RequestHandlerRetryAdvice`, recovery callback, error channel** cũng như mối quan hệ của chúng với **redelivery do transport**.

> **Nguyên tắc:** Retry là quyết định **thử lại một thao tác chưa đạt điều kiện thành công**. Recoverer là quyết định **xử lý khi thử lại không còn phù hợp hoặc đã cạn lượt**. Cả hai phải có ranh giới, owner, chính sách và điểm quan sát; không được tự động đồng nghĩa “business operation đã hoàn tất”.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **retry nội bộ**, **redelivery của broker**, **replay**, **recovery callback**, **error handler**, **dead-letter** và **compensation**.
2. Xác định lỗi **transient**, **permanent**, **unknown outcome** và chính sách retry phù hợp.
3. Cấu hình và kiểm thử `RetryTemplate`, `RetryPolicy`, `BackOffPolicy` và `RecoveryCallback` của Spring Retry.
4. Hiểu cách `RequestHandlerRetryAdvice` gắn vào endpoint Spring Integration, khi nào advice thấy exception.
5. Thiết kế test success sau N lần, hết số lần thử, recoverer chạy đúng một lần, lỗi không retry, sai cấu hình và recoverer lại lỗi.
6. Sử dụng `ErrorMessageSendingRecoverer`/error channel khi phù hợp với **one-way flow**, và tránh coi việc publish lỗi là nghiệp vụ thành công.
7. Kiểm tra **sync/async**, inbound poller, gateway request-reply và listener Kafka/JMS/AMQP theo đúng ranh giới acknowledgment.
8. Mô phỏng lỗi File, SFTP, HTTP, JDBC, JMS, AMQP, Kafka và xác minh **side effect tại đích** bằng test tích hợp.
9. Kiểm thử **idempotency, rollback, transaction, retry storm, backoff, recovery after restart** và bảo mật.
10. Tạo **test matrix và acceptance criteria** có thể vận hành trong CI/CD.

## 2. Từ vựng phải thống nhất trước khi viết test

| Khái niệm | Nghĩa trong bài | Lưu ý kiểm thử |
|---|---|---|
| **Attempt** | Một lần thực thi thao tác được bảo vệ. | Lần đầu thường được tính trong tổng `maxAttempts`. |
| **Retry** | Thực thi lại thao tác sau lỗi theo policy. | Phải chứng minh chính xác thao tác nào được chạy lại. |
| **Retry policy** | Quyết định lỗi nào được retry, bao nhiêu lần, điều kiện dừng. | Không retry mọi exception như nhau. |
| **Backoff** | Chờ giữa các attempt, có thể fixed/exponential/jitter. | Bounded, tránh retry storm và test flaky. |
| **Recovery callback** | Nhận quyền xử lý khi retry exhausted theo Spring Retry. | Không nhất thiết có nghĩa lỗi đã được khắc phục. |
| **Recoverer** | Thành phần ghi nhận/định tuyến thất bại hoặc xây kết quả recovery. | Có thể gửi error event, quarantine, DLQ hoặc trả fallback. |
| **Redelivery** | Broker/source phát lại cùng message logic. | Có thể xảy ra ngoài vòng retry trong process. |
| **Replay** | Chủ động phát lại event lịch sử. | Cần business key/version/idempotency. |
| **Dead-letter / quarantine** | Nơi giữ message không xử lý được để điều tra/redrive. | Chỉ đáng tin khi đã xác minh publish/persist. |
| **Compensation** | Thao tác nghiệp vụ xử lý hệ quả đã xảy ra. | Không phải rollback transaction tự động. |
| **Unknown outcome** | Không rõ thao tác ở đích đã thành công hay chưa. | Cần readback/idempotency trước retry nguy hiểm. |

Ví dụ khi broker đã giao message một lần, advice thử handler **ba attempt**; sau đó listener ném lỗi để broker redeliver lần hai. Khi ấy một business message có thể tạo **sáu lần thực thi handler**, chưa kể lần phát lại thủ công. Đếm retry nội bộ là chưa đủ để khẳng định tổng lượt xử lý.

## 3. Retry và recoverer nằm ở đâu trong flow?

~~~mermaid
flowchart TD
    SOURCE["Inbound source / listener"] --> CHANNEL["MessageChannel"]
    CHANNEL --> ADVICE["RequestHandlerRetryAdvice<br/>Retry policy + backoff"]
    ADVICE --> HANDLER["MessageHandler / outbound adapter"]
    HANDLER --> RESULT{"Kết quả attempt"}
    RESULT -- "Thành công" --> DONE["Downstream success path"]
    RESULT -- "Lỗi có thể retry" --> LIMIT{"Còn attempt?"}
    LIMIT -- "Có" --> BACK["Backoff rồi thử handler lại"]
    BACK --> HANDLER
    LIMIT -- "Hết" --> REC["RecoveryCallback / recoverer"]
    RESULT -- "Lỗi không retry" --> EXIT["Dừng retry theo policy<br/>Recovery hoặc propagate"]
    EXIT --> REC
    REC --> NEXT{"Recovery outcome"}
    NEXT -- "Ghi nhận/định tuyến" --> QUAR["Error channel / quarantine"]
    NEXT -- "Ném lỗi tiếp" --> UP["Caller / poller / broker container"]
    NEXT -- "Trả fallback" --> FALL["Fallback theo contract"]
~~~

Đây là **mô hình khái niệm**, không phải mọi Spring Integration endpoint đều tự có cùng đường xử lý. Đường lỗi đi đến error channel hay ném ngược, recoverer có được gọi với loại exception nào, và recovery return có trở thành reply hay không đều phụ thuộc **cấu hình advice, handler, channel và transaction/transport**.

### 3.1. Phạm vi protected operation quan trọng hơn số lần retry

~~~text
File inbound → parse CSV → gọi HTTP → lưu DB
~~~

Nếu retry advice chỉ bọc **HTTP outbound handler**, mỗi attempt có thể gọi HTTP lại nhưng **không parse CSV lại**. Nếu retry bọc **toàn chuỗi từ source**, một lần retry có thể tải/đọc file lại, tạo side effect khác. Cần ghi rõ ranh giới:

- Handler nào được retry?
- Có transaction nào bao quanh handler?
- Dữ liệu nguồn có bị consume/ack trước khi handler chạy không?
- Việc retry có tạo message ID mới hoặc dùng lại message cũ?
- Người nhận ở đích có hỗ trợ idempotency key không?

Test chỉ có ý nghĩa khi bao phủ **đúng đoạn được retry**.

## 4. Phân loại lỗi trước khi quyết định thử lại

| Nhóm lỗi | Ví dụ | Hành vi thông thường nên xem xét |
|---|---|---|
| **Transient transport** | HTTP 503, connection reset, broker tạm mất | Retry có giới hạn/backoff; quan sát recovery. |
| **Rate limiting** | HTTP 429, quota tạm đầy | Tôn trọng chỉ dẫn chờ hợp lệ; tránh flood. |
| **Potentially transient DB** | Deadlock, lock timeout | Retry **toàn transaction phù hợp** với giới hạn. |
| **Permanent validation** | CSV sai schema, JSON thiếu trường bắt buộc | Không retry y nguyên; quarantine/alert. |
| **Authorization** | HTTP 401/403, SFTP permission denied | Không retry vô hạn; điều tra credential/policy. |
| **Not found** | 404 đối với tài nguyên | Phụ thuộc contract: permanent, eventual-consistency hoặc chưa sẵn sàng. |
| **Unknown outcome** | Request ghi dữ liệu bị read timeout sau khi gửi | Readback/idempotency; không mặc định retry an toàn. |
| **Cancellation/shutdown** | Thread bị interrupt, endpoint stopping | Xử lý interruption/lifecycle đúng; tránh kéo dài shutdown. |
| **Resource exhaustion** | Queue đầy, pool hết connection | Backpressure, giảm tốc hoặc dừng intake; retry có kiểm soát. |
| **Poison message** | Payload làm consumer luôn throw | Không mắc kẹt vòng lặp; cách ly và nêu nguyên nhân. |

Không có một bảng **HTTP status → retry** áp dụng chính xác cho mọi API. Ví dụ 409 có thể nghĩa là conflict không thể sửa bằng retry, hoặc “đã tồn tại” có thể đọc lại kết quả idempotency. Hãy dựa vào **hợp đồng của ứng dụng và operation**.

### 4.1. Retryable khác với idempotent

Một lỗi có vẻ transient **không tự làm operation an toàn để retry**. Đặc biệt với phương thức tạo mới, thanh toán, cấp quyền, xóa tài nguyên hoặc gửi thông báo:

1. Lỗi ở client có thể xảy ra **sau side effect ở server**.
2. Retry có thể tạo tác dụng mới.
3. Cần idempotency key, dedupe tại đích, readback hoặc compensating workflow.
4. Test phải kiểm tra trạng thái thực ở đích, không chỉ số lần gọi phương thức.

## 5. Các khối chính trong Spring Retry

| Khối | Trách nhiệm | Test cần có |
|---|---|---|
| `RetryTemplate` | Chạy callback theo retry policy và backoff. | Attempts, kết quả, exhausted. |
| `RetryPolicy` | Quyết định retry khi nào, số lần tối đa, loại exception. | Transient/permanent, nested cause, giới hạn. |
| `BackOffPolicy` | Chờ giữa các attempt. | Bounded, schedule/tolerance, shutdown. |
| `RetryContext` | Trạng thái của vòng retry đang chạy. | Count/cause/attributes khi dùng. |
| `RetryCallback<T, E>` | Công việc thực thi mỗi attempt. | Phạm vi side effect chính xác. |
| `RecoveryCallback<T>` | Được gọi khi template kết thúc bằng recovery. | Một lần, nguyên nhân cuối, kết quả/throw. |
| `RequestHandlerRetryAdvice` | Gắn retry vào handler Spring Integration phù hợp. | Lỗi qua advice, endpoint được bọc đúng. |
| `ErrorMessageSendingRecoverer` | Recoverer gửi `ErrorMessage` vào channel được cấu hình. | Error channel nhận event; không nhầm với business reply. |

### 5.1. Tổng attempt và số retry

Giả sử `maxAttempts = 3`:

~~~text
Attempt #1: gọi handler lần đầu
  lỗi transient
Attempt #2: retry thứ nhất
  lỗi transient
Attempt #3: retry thứ hai
  lỗi transient
Exhausted → gọi RecoveryCallback (nếu được cấu hình)
~~~

Vậy tổng **3 lần gọi handler** nhưng chỉ **2 lần retry** sau lần đầu. `RetryContext.getRetryCount()` thường bắt đầu từ 0 trong lần đầu; khi test, đừng nhầm giá trị context với tổng số invocation nếu không đối chiếu semantics của thư viện.

### 5.2. Không cài đặt retry vô hạn tùy tiện

Một policy không giới hạn trong inbound adapter có thể:

- Giữ thread poller/consumer và ngăn message sau.
- Làm nghẽn Kafka partition hoặc hàng đợi JMS/AMQP.
- Tạo request storm tới API đang lỗi.
- Không bao giờ gọi recoverer, khiến poison message kẹt mãi.
- Chặn stop/shutdown hoặc kéo dài quá mức response của gateway.

Với nghiệp vụ cần **đợi lâu để nguồn phục hồi**, có thể dùng retry bất đồng bộ qua scheduler/queue bền vững hoặc redrive có quản trị, thay vì giữ một thread vô hạn.

## 6. Dependency và môi trường kiểm thử

Ví dụ Maven cho dự án đã được Spring Boot BOM/dependency management quản lý phiên bản tương thích:

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
        <groupId>org.springframework.retry</groupId>
        <artifactId>spring-retry</artifactId>
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
    implementation("org.springframework.retry:spring-retry")
    testImplementation("org.springframework.integration:spring-integration-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Nếu dự án không dùng Boot BOM, cần quản lý version Spring Framework, Spring Retry, Spring Integration và JUnit tương thích. Các API builder, Java DSL và cách đăng ký advice có thể khác theo phiên bản; khi áp dụng, kiểm tra API của đúng bản đang chạy.

`spring-integration-test` giúp cô lập endpoint nhưng **không cài sẵn broker, database, SFTP server hoặc HTTP stub**. Kiểm thử giao thức cần module adapter và tài nguyên test tương ứng.

## 7. Ví dụ đầu tiên: kiểm thử RetryTemplate độc lập

Nên bắt đầu bằng một **unit test cho retry semantics**, không cần Spring context hoặc broker. Test này chứng minh template gọi lại callback và recovery khi cạn attempts; tầng test sau mới chứng minh advice thực sự gắn vào endpoint.

### 7.1. Thành công sau hai lỗi transient

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.retry.support.RetryTemplate;

class RetryTemplatePolicyTest {

    @Test
    void retriesUntilThirdAttemptSucceeds() {
        RetryTemplate retry = RetryTemplate.builder()
                .maxAttempts(3)
                .fixedBackoff(1)
                .build();

        AtomicInteger attempts = new AtomicInteger();
        AtomicInteger recoveries = new AtomicInteger();

        String response = retry.execute(
                context -> {
                    int call = attempts.incrementAndGet();
                    if (call <= 2) {
                        throw new IllegalStateException("temporary");
                    }
                    return "CONFIRMED";
                },
                context -> {
                    recoveries.incrementAndGet();
                    return "RECOVERED";
                });

        assertEquals("CONFIRMED", response);
        assertEquals(3, attempts.get());
        assertEquals(0, recoveries.get());
    }
}
~~~

**Assertions quan trọng:** tổng số attempt đúng bằng 3 và **recoverer không chạy** khi một lần thử đã thành công. Đây là test của `RetryTemplate`, chưa phải test `RequestHandlerRetryAdvice` hoặc broker.

### 7.2. Cạn lượt thử rồi gọi recovery một lần

~~~java
@Test
void invokesRecoveryAfterAllAttemptsFail() {
    RetryTemplate retry = RetryTemplate.builder()
            .maxAttempts(3)
            .fixedBackoff(1)
            .build();

    AtomicInteger attempts = new AtomicInteger();
    AtomicInteger recoveries = new AtomicInteger();

    String result = retry.execute(
            context -> {
                attempts.incrementAndGet();
                throw new IllegalStateException("target unavailable");
            },
            context -> {
                recoveries.incrementAndGet();
                assertInstanceOf(IllegalStateException.class,
                        context.getLastThrowable());
                return "QUARANTINED";
            });

    assertEquals(3, attempts.get());
    assertEquals(1, recoveries.get());
    assertEquals("QUARANTINED", result);
}
~~~

Đây là ví dụ phương thức `@Test` nằm trong lớp test có import JUnit, `RetryTemplate` và `AtomicInteger` như ở phần trước. **`"QUARANTINED"` ở đây chỉ là giá trị giả do callback trả**. Muốn khẳng định message đã được quarantine phải có **side effect thực tế/đối tượng ghi nhận** và kiểm tra readback.

### 7.3. Không cấu hình recovery

Nếu không truyền `RecoveryCallback` hoặc không có recovery handler tương ứng, khi retry exhausted, template thường **ném ngoại lệ cuối/đại diện theo cơ chế của policy**. Test cần xác minh exception được propagate ra tầng caller, hoặc được xử lý bởi error handler của endpoint nếu có; không xem hết retry là một lần xử lý thành công.

## 8. Gắn RequestHandlerRetryAdvice vào endpoint

`RequestHandlerRetryAdvice` thực thi retry quanh lời gọi **`MessageHandler` của một endpoint Spring Integration**. Điều này khác với retry toàn bộ inbound polling source hoặc retry do broker listener.

Một cấu hình minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.messaging.MessageHandler;
import org.springframework.retry.support.RetryTemplate;

import java.util.concurrent.atomic.AtomicInteger;

@Configuration
@EnableIntegration
class RetryFlowTestConfig {

    @Bean
    DirectChannel requests() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel successes() {
        return new QueueChannel();
    }

    @Bean
    AtomicInteger handlerAttempts() {
        return new AtomicInteger();
    }

    @Bean
    RequestHandlerRetryAdvice retryAdvice() {
        RetryTemplate template = RetryTemplate.builder()
                .maxAttempts(3)
                .fixedBackoff(1)
                .build();
        RequestHandlerRetryAdvice advice =
                new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(template);
        return advice;
    }

    @Bean
    IntegrationFlow retryFlow(DirectChannel requests,
                              QueueChannel successes,
                              AtomicInteger handlerAttempts,
                              RequestHandlerRetryAdvice retryAdvice) {
        MessageHandler handler = message -> {
            int attempt = handlerAttempts.incrementAndGet();
            if (attempt <= 2) {
                throw new IllegalStateException("partner temporarily down");
            }
            successes.send(message);
        };

        return IntegrationFlow.from(requests)
                .handle(handler, endpoint -> endpoint
                        .id("retryProtectedEndpoint")
                        .advice(retryAdvice))
                .get();
    }
}
~~~

Trong ví dụ, `requests` là **channel đầu vào**, còn `retryProtectedEndpoint` là **endpoint ID**. Advice nằm quanh handler nên cùng một message được thử tối đa ba lần trong cùng vòng xử lý; ví dụ sử dụng `DirectChannel` để đơn giản hóa ranh giới đồng bộ.

### 8.1. Test wiring advice, không chỉ template

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(RetryFlowTestConfig.class)
class RequestHandlerRetryAdviceFlowTest {

    @Autowired
    @Qualifier("requests")
    DirectChannel input;

    @Autowired
    @Qualifier("successes")
    QueueChannel output;

    @Autowired
    AtomicInteger handlerAttempts;

    @Test
    void retriesHandlerAndEmitsSuccessOnce() {
        handlerAttempts.set(0);

        assertTrue(input.send(
                MessageBuilder.withPayload("order-9")
                        .setHeader("requestId", "req-9")
                        .build()));

        Message<?> observed = output.receive(1_000);
        assertNotNull(observed);
        assertEquals("order-9", observed.getPayload());
        assertEquals("req-9",
                observed.getHeaders().get("requestId"));
        assertEquals(3, handlerAttempts.get());
        assertNull(output.receive(0));
    }
}
~~~

Test này kiểm tra **advice thực sự bao quanh handler** của flow. `AtomicInteger` là state trong context, nên nếu nhiều test chia sẻ context phải reset rõ ràng hoặc cô lập fixture; bài test này giả định chỉ một ca chạy trên context đó.

**Điểm chưa được chứng minh:** side effect trên server/broker thật; handler giả chỉ phát message vào `QueueChannel`. Test integration của transport cần bao phủ phần còn lại.

## 9. Một recoverer thực sự cần làm gì?

Khi retry exhausted, recoverer phải có **hợp đồng rõ**. Một số kiểu recovery:

| Recovery outcome | Hành vi | Điểm quan sát test |
|---|---|---|
| **Propagate failure** | Ném lỗi về caller/listener/poller. | Exception/error path và redelivery semantics. |
| **Publish ErrorMessage** | Đẩy thông tin lỗi tới error channel. | Error message có cause/correlation. |
| **Quarantine/parking lot** | Lưu message và lý do để xử lý lại. | Record/queue/file thực sự tồn tại và có owner. |
| **Dead-letter broker message** | Dùng DLQ/DLT theo container/transport. | Broker target readback; không chỉ gọi method. |
| **Fallback response** | Trả một kết quả được contract cho phép. | Không gọi fallback là business success sai nghĩa. |
| **Compensation workflow** | Yêu cầu thao tác bù khi side effect đã xảy ra. | Trạng thái bù được theo dõi riêng. |
| **Escalation/alert** | Gửi cảnh báo/case cho vận hành. | Alert có correlation, retry khôi phục và dedup phù hợp. |

**“Đã gọi recoverer” chưa có nghĩa “đã phục hồi”.** Ví dụ recoverer đưa message vào `QueueChannel` chỉ chứng minh một message đã được gửi vào kênh test; muốn nói đã lưu bền vững vào DLQ phải quan sát được record ở broker.

### 9.1. Recovery phải có trạng thái dễ truy vấn

Một workflow có thể dùng:

~~~text
NEW → PROCESSING → RETRYING → SUCCEEDED
                          |
                          +→ EXHAUSTED → QUARANTINED → REDRIVE_PENDING
                                                 |
                                                 +→ RESOLVED
~~~

Không tự đặt `SUCCEEDED` khi chỉ chuyển qua `EXHAUSTED` hoặc `QUARANTINED`. Một request/reply gateway thậm chí có thể **timeout** sau recovery vì recoverer không tạo reply; điều đó cần được chủ động test.

## 10. ErrorMessageSendingRecoverer và error channel

Spring Integration cung cấp `ErrorMessageSendingRecoverer` để gửi một `ErrorMessage` tới channel được cấu hình khi retry advice đi vào recovery. Đây là cách phù hợp với **nhiều one-way message flows**, nơi xử lý lỗi cần chuyển sang một nhánh riêng.

Ví dụ cấu hình minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

@Bean
QueueChannel failedMessages() {
    return new QueueChannel();
}

@Bean
RequestHandlerRetryAdvice retryWithErrorChannel(
        QueueChannel failedMessages) {
    RequestHandlerRetryAdvice advice =
            new RequestHandlerRetryAdvice();
    advice.setRetryTemplate(RetryTemplate.builder()
            .maxAttempts(3)
            .fixedBackoff(1)
            .build());
    advice.setRecoveryCallback(
            new ErrorMessageSendingRecoverer(failedMessages));
    return advice;
}
~~~

Ở đây nên gắn bean `retryWithErrorChannel` vào **endpoint cần thử lại**, không tự giả định mọi endpoint dùng cùng global retry advice. Test phải xác minh message chứa `Throwable` đi tới `failedMessages` và **không có business success giả**.

### 10.1. Cẩn trọng khi dùng error channel

- `ErrorMessage` thường chứa throwable, nhưng dạng wrapper/cause và khả năng liên kết original message tùy nơi lỗi xảy ra.
- Việc gửi tới `QueueChannel` trong test không đồng nghĩa đã ghi bền vững; restart có thể mất message nếu channel không durable.
- Một recoverer trả kết quả hợp lệ có thể khiến tầng trên xem exception đã được xử lý; cần xem **ACK/commit** ở broker khi source là JMS/AMQP/Kafka.
- Nếu gateway request/reply cần một response, recoverer **gửi lỗi một chiều** chưa chắc tạo response cho caller; test có thể cần mapping lỗi sang reply riêng.
- Nếu error channel đầy hoặc consumer error flow throw, **recovery cũng có thể thất bại**; phải có test.

### 10.2. Kiểm thử thông điệp lỗi

Một assertion ở test flow dùng `failedMessages`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

Message<?> error = failedMessages.receive(1_000);
assertNotNull(error, "Recoverer phải gửi error message");
assertInstanceOf(ErrorMessage.class, error);
assertInstanceOf(Throwable.class, error.getPayload());

// Kiểm tra cause và correlation theo contract của flow thật.
// Không khẳng định original message luôn nằm cùng một header
// nếu error strategy / transport có thể cấu hình khác nhau.
~~~

Khi chưa thay handler để **luôn fail đủ số attempt**, test trên không chứng minh recovery được kích hoạt. Fixture phải có một handler thất bại xác định, bộ đếm attempt và output error riêng.

## 11. Các ca kiểm thử tối thiểu cho retry/recoverer

| Scenario | Input/fixture | Assertion |
|---|---|---|
| **Không lỗi** | Handler thành công ngay. | 1 attempt, 0 recovery. |
| **Một lỗi rồi thành công** | Fail lần 1, success lần 2. | 2 attempts, 0 recovery. |
| **Success đúng lần cuối** | Max=3, fail hai lần. | 3 attempts, 0 recovery. |
| **Thất bại toàn bộ** | Fail cả ba attempt. | 3 attempts, 1 recovery. |
| **Permanent failure** | Validation exception không retry theo policy. | Không thử lại nhiều lần vô ích. |
| **Recoverer cũng lỗi** | Recovery store không khả dụng. | Lỗi được escalate, không false success. |
| **Không cấu hình recoverer** | Handler luôn fail. | Error propagate theo advice/endpoint. |
| **Retry bị gián đoạn** | Shutdown/cancellation có chủ đích. | Không tiếp tục mãi và không nuốt interrupt. |
| **Message trùng** | Cùng `eventId` xuất hiện lại. | Không tạo side effect trùng ngoài contract. |
| **Restart trong retry** | Process dừng giữa attempt. | Semantics redelivery/checkpoint và idempotency đúng. |

Trong kiểm thử **unit** với `RetryTemplate`, đếm callback bằng `AtomicInteger`. Trong kiểm thử **Spring Integration flow**, phải thêm assertion endpoint advice đã được gắn đúng bean. Trong kiểm thử **transport**, phải xác minh side effect và ACK/redelivery ở nguồn/đích.

## 12. Test phân loại exception: lỗi nào được retry?

Một policy chỉ cần biết **số attempt** là chưa đủ. Nó còn phải phân biệt lỗi tạm thời với lỗi dữ liệu hoặc quyền truy cập.

### 12.1. Ví dụ dùng retryOn cho loại lỗi tạm thời

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.retry.support.RetryTemplate;

class ExceptionClassificationTest {

    static class TemporaryPartnerException extends RuntimeException {
        TemporaryPartnerException(String message) { super(message); }
    }

    static class InvalidOrderException extends RuntimeException {
        InvalidOrderException(String message) { super(message); }
    }

    @Test
    void onlyRetriesTheConfiguredTemporaryException() {
        RetryTemplate retry = RetryTemplate.builder()
                .maxAttempts(4)
                .retryOn(TemporaryPartnerException.class)
                .fixedBackoff(1)
                .build();

        AtomicInteger calls = new AtomicInteger();

        assertThrows(InvalidOrderException.class,
                () -> retry.execute(context -> {
                    calls.incrementAndGet();
                    throw new InvalidOrderException("missing orderId");
                }));

        assertEquals(1, calls.get(),
                "Dữ liệu sai không được thử lại bốn lần");
    }
}
~~~

Trong ví dụ, `InvalidOrderException` không thuộc nhóm được retry; template dừng thay vì lặp lại cùng lỗi. Với exception bị wrap (chẳng hạn HTTP client exception nằm trong `MessagingException`), policy phải xác định có xét **cause chain** hay không. Test phải cố ý tạo **wrapped exception** giống production, tránh chỉ dùng exception đã được unwrap lý tưởng.

### 12.2. Bộ ca kiểm thử classifier

| Input exception | Retry? | Điều cần assert |
|---|---|---|
| `TemporaryPartnerException` | Có, trong giới hạn. | Số attempt đúng; kết thúc nếu success. |
| `InvalidOrderException` | Không. | Một attempt; rejection/recovery đúng. |
| Exception được bọc trong `MessagingException` | Tùy policy `traverseCauses`/classifier. | Chính xác đường xử lý sau wrap. |
| HTTP 429 với hướng dẫn chờ | Tùy hợp đồng. | Không retry tức thì làm bão request. |
| HTTP 401/403 | Thường không lặp bằng credential cũ. | Có alert và không gửi lại vô ích. |
| `InterruptedException` hoặc thread interrupted | Không retry mù quáng. | Bảo toàn tín hiệu hủy/shutdown phù hợp. |
| Dữ liệu lỗi nhưng có thể sửa tự động | Chỉ khi transformation có căn cứ. | Không âm thầm đổi dữ liệu người dùng. |

### 12.3. Khi không retry, có gọi recoverer không?

Điều này phụ thuộc **RetryTemplate, classifier và cơ chế recovery đã cấu hình**. Một lỗi được phân loại “không retry” có thể đi thẳng vào xử lý exhausted/recovery, hoặc propagate theo chính sách. Test phải khẳng định **desired outcome** thay vì suy “không retry = không recover”. Điều chắc chắn cần kiểm tra là **không có chuỗi attempts vô ích** và **lỗi không bị báo thành thành công**.

## 13. Kiểm tra backoff mà không làm test chậm hoặc flaky

Backoff tránh việc một hệ thống lỗi bị hàng nghìn consumer gọi lại liên tục. Nhưng test `Thread.sleep(2_000)` rồi đo thời gian toàn bộ rất dễ bị ảnh hưởng bởi CPU/GC trên CI.

### 13.1. Kiểm tra số lần backoff bằng fake policy

Spring Retry cho phép cung cấp `BackOffPolicy` có thể thay trong unit test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.retry.RetryContext;
import org.springframework.retry.backoff.BackOffContext;
import org.springframework.retry.backoff.BackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

class BackoffBehaviorTest {

    @Test
    void invokesBackoffBetweenAttempts() {
        AtomicInteger waits = new AtomicInteger();
        AtomicInteger attempts = new AtomicInteger();

        BackOffPolicy fakeBackoff = new BackOffPolicy() {
            @Override
            public BackOffContext start(RetryContext context) {
                return new BackOffContext() {};
            }

            @Override
            public void backOff(BackOffContext context) {
                waits.incrementAndGet(); // Không ngủ thật.
            }
        };

        RetryTemplate retry = new RetryTemplate();
        retry.setRetryPolicy(new SimpleRetryPolicy(3));
        retry.setBackOffPolicy(fakeBackoff);

        String result = retry.execute(context -> {
            if (attempts.incrementAndGet() <= 2) {
                throw new IllegalStateException("temporary");
            }
            return "OK";
        });

        assertEquals("OK", result);
        assertEquals(3, attempts.get());
        assertEquals(2, waits.get(),
                "Ba attempts thành công cuối có hai khoảng backoff");
    }
}
~~~

Đây là **unit test hành vi backoff hook**, không chứng minh khoảng chờ thực đúng 100 ms hay exponential schedule. Nếu policy tự thiết kế giới hạn/tăng theo cấp số nhân, hãy test thuật toán tính delay riêng với clock/strategy giả, sau đó có một integration test nhỏ với tolerance hợp lý để xác nhận scheduling thực.

### 13.2. Retry storm và jitter

~~~mermaid
flowchart LR
    A["1000 consumer cùng gặp 503"] --> BAD["Retry tức thì cùng lúc<br/>thêm tải lên API"]
    A --> GOOD["Bounded exponential backoff<br/>+ jitter nếu phù hợp"]
    GOOD --> C["Giảm đồng bộ đợt retry"]
    BAD --> D["Tăng nguy cơ overload kéo dài"]
~~~

Jitter giúp tránh nhiều instance cùng thử lại tại một mốc, nhưng tạo biến động thời gian. Đừng viết assertion đòi delay ngẫu nhiên chính xác. Nên test **khoảng cho phép, độ lớn tối đa, số attempt, giới hạn thời gian tổng và không có delay âm**; nếu cần tái hiện, inject nguồn random có seed trong unit test.

### 13.3. Deadline tổng và timeout của gateway

Ví dụ gateway chỉ chờ reply tối đa 2 giây, nhưng retry policy cho phép năm attempt với mỗi backoff 1 giây. Kết quả có thể là caller timeout trước khi handler ngừng retry, tạo **in-flight work tiếp tục chạy sau khi caller đã bỏ cuộc**. Cần test:

1. Request/reply timeout và connect/read timeout theo từng attempt.
2. Ngân sách thời gian tổng (deadline) cho lời gọi.
3. Điều kiện hủy/stop khi không còn cần kết quả.
4. Side effect nếu retry tiếp tục sau caller timeout.
5. Hạn mức attempt/thời gian không khiến thread bị giữ vô hạn.

Không có quy tắc chung rằng số attempt nhân một delay sẽ bằng chính xác timeout tổng: thời gian **xử lý mỗi attempt**, backoff, scheduling và transport cần được cộng vào ngân sách.

## 14. Recoverer có thể thất bại: test second failure path

Giả sử handler lỗi ba lần, recoverer muốn ghi bản lỗi vào database hoặc publish dead-letter tới broker, nhưng **database/broker của recovery cũng không sẵn sàng**.

~~~text
Original request E
  → attempt #1 FAIL
  → attempt #2 FAIL
  → attempt #3 FAIL
  → recoverer publish DLT FAIL
  → ??? (không được mặc định là RESOLVED)
~~~

### 14.1. Test bằng callback throw

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.retry.support.RetryTemplate;

class RecoveryFailureTest {

    @Test
    void propagatesRecoveryFailureInsteadOfClaimingSuccess() {
        RetryTemplate retry = RetryTemplate.builder()
                .maxAttempts(2)
                .fixedBackoff(1)
                .build();

        AtomicInteger attempts = new AtomicInteger();
        AtomicInteger recovererCalls = new AtomicInteger();

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> retry.execute(
                        context -> {
                            attempts.incrementAndGet();
                            throw new IllegalArgumentException(
                                    "original failure");
                        },
                        context -> {
                            recovererCalls.incrementAndGet();
                            throw new IllegalStateException(
                                    "quarantine unavailable");
                        }));

        assertEquals("quarantine unavailable",
                error.getMessage());
        assertEquals(2, attempts.get());
        assertEquals(1, recovererCalls.get());
    }
}
~~~

Test minh họa nguyên lý **recovery failure phải được quan sát**. Trong ứng dụng thật, nên giữ cả **original exception** và **recovery exception** trong audit/tracing để không mất nguyên nhân ban đầu, đồng thời có chính sách escalation khi không thể lưu lỗi vào kênh phụ.

### 14.2. Cần thiết kế đường lỗi cấp hai

| Recoverer thất bại ở đâu? | Hành vi cần thiết kế và test |
|---|---|
| Error channel đầy | Có timeout/backpressure, không nuốt exception. |
| DLT publisher unavailable | Không ACK source một cách sai lầm; retry/redrive theo policy. |
| DB quarantine transaction fail | Rollback hoặc giữ trạng thái recoverable. |
| Alert service timeout | Không đánh dấu business message thành công chỉ vì đã thử gửi alert. |
| Payload không serialize được vào DLT | Lưu bản lỗi/metadata tối thiểu hoặc escalation an toàn. |
| Error flow tự throw exception | Hạn chế vòng lặp recovery và bảo toàn original cause. |

**Không lặp vô hạn “retry recoverer”** nếu chính hệ thống recovery đã mất; cần giới hạn riêng và cơ chế bảo toàn dữ liệu phù hợp.

## 15. Retry trong flow đồng bộ và bất đồng bộ

### 15.1. DirectChannel và service activator đồng bộ

Với `DirectChannel`, handler thường chạy trên thread người gửi. Khi advice không recover được:

- Exception có thể quay về lời gọi `send()`/gateway.
- Backoff có thể giữ chính thread caller.
- Test `assertThrows` phù hợp nếu error được propagate và không có tầng bọc/handler nuốt lỗi.
- Nếu recoverer xử lý lỗi và trả `null`, người gửi có thể **không nhận exception**, dù nghiệp vụ chưa thành công.

### 15.2. ExecutorChannel và xử lý asynchronous

Khi handler chạy trên thread khác:

- `send()` trả về không chứng minh handler đã chạy xong.
- Exception thường không đi ngược về caller thread một cách trực tiếp.
- Retry advice có thể chạy trong executor; cần quan sát attempt, error channel và completion signal.
- Test dùng `CountDownLatch`, output `QueueChannel` hoặc future có timeout.
- Teardown phải đợi/dọn in-flight retry trước khi reset mock.

### 15.3. Polling endpoint

Nếu source là File/SFTP/JDBC poller, `RequestHandlerRetryAdvice` gắn quanh handler không nhất thiết kiểm soát **thao tác `MessageSource.receive()`** hoặc bước remote fetch. Muốn test lỗi khi source poll thất bại, phải kiểm tra **poller advice/error handler** theo cách endpoint được thiết kế.

Một inbound source có thể phát lại cùng message ở tick sau tùy filter/metadata/transaction. Đừng suy rằng lỗi handler được retry nội bộ là đủ để bảo đảm file/row sẽ được đọc lại sau restart.

~~~mermaid
flowchart LR
    POLL["Poller"] --> SRC["MessageSource.receive()"]
    SRC --> CHANNEL["MessageChannel"]
    CHANNEL --> RETRY["Handler retry advice"]
    RETRY --> H["MessageHandler"]
    SRC -. "Source failure path riêng" .-> ERR["Poller error handling"]
    H -. "Handler failure" .-> REC["RecoveryCallback"]
~~~

## 16. Test retry với HTTP outbound gateway

HTTP là ví dụ phổ biến của **transient failure + unknown outcome**. Hãy tách **logic phân loại lỗi** và **test server trả response thật**.

### 16.1. Ma trận HTTP

| Server response | Test policy | Điểm quan sát |
|---|---|---|
| 200 + JSON hợp lệ | Không retry. | 1 HTTP request, reply đúng DTO. |
| 503 hai lần rồi 200 | Retry giới hạn. | 3 requests, 0 recovery, 1 business result. |
| 503 liên tục | Exhausted. | Đúng attempts, recoverer một lần, trạng thái lỗi. |
| 400 malformed request | Không retry cùng payload. | 1 request, lỗi validation. |
| 401/403 | Không spam credential sai. | 1 request và alert phù hợp. |
| 429 + Retry-After | Respect policy/client constraints. | Backoff và tổng thời gian bounded. |
| Connect timeout | Có thể an toàn hơn vì chưa gửi body, nhưng cần xem transport. | Lỗi được phân loại đúng. |
| Read timeout sau POST | Unknown outcome. | Readback/idempotency trước retry side effect. |
| 200 nhưng JSON sai schema | Contract error. | Không coi là business success. |
| Server nhận POST rồi trả muộn | Timeout tại client. | Partner có thể đã tạo dữ liệu; không tạo trùng. |

### 16.2. Một HTTP stub script minh họa

~~~text
Request #1 POST /orders → 503 Service Unavailable
Request #2 POST /orders → 503 Service Unavailable
Request #3 POST /orders → 200 {"orderId":"PO-9","status":"CONFIRMED"}

Assertions:
  - Tổng HTTP requests = 3
  - Header Idempotency-Key = req-order-9 ở cả ba requests
  - Gateway trả đúng OrderReply
  - Recoverer không chạy
  - Có correlation/log cho cả ba attempts
~~~

Để kiểm tra request thật, dùng **HTTP stub server/test server** hoặc công cụ mock HTTP client tương thích với client production. Một Mockito mock của `MessageHandler` chỉ chứng minh lời gọi ở boundary, không chứng minh HTTP method, TLS, timeout, response mapping hoặc network side effect.

### 16.3. Chỉ retry nếu operation có safety contract

Với `GET`/truy vấn read-only, retry thường ít nguy cơ duplicate side effect hơn. Với `POST` tạo giao dịch, cần idempotency key server xác thực, lookup operation status hoặc compensating workflow. Không dựa duy nhất vào HTTP verb: một số API thực tế có side effect kể cả ở endpoint tưởng chừng đọc dữ liệu.

## 17. Test retry với File và SFTP adapter

### 17.1. File inbound

Lỗi có thể xuất hiện khi:

- File chưa được ghi xong nhưng poller đã đọc.
- File bị lock, không có quyền đọc hoặc bị xóa giữa scan và open.
- Parser gặp CSV/JSON sai schema.
- Filter/metadata đã đánh dấu file rồi handler thất bại.
- Ứng dụng restart trước khi ghi kết quả hoặc cleanup.

**Không giải quyết file chưa hoàn chỉnh chỉ bằng retry vô hạn.** Thường cần ready-marker/atomic rename hoặc chính sách kiểm tra stability, cộng filter và error/quarantine.

| Ca test | Kỳ vọng |
|---|---|
| File `*.tmp` đang ghi | Không đọc trước ready. |
| File `*.ready` hợp lệ | Phát đúng bytes và metadata. |
| Lỗi I/O transient | Retry/recovery theo scope, file còn recoverable. |
| CSV sai schema | Không retry cùng file vô ích; quarantine có reason. |
| Handler xử lý thành công nhưng crash trước metadata update | Restart xử lý theo delivery policy, side effect idempotent. |
| Hai instance cùng file | Không side effect trùng ngoài chính sách. |

### 17.2. SFTP inbound/outbound

SFTP có thể thất bại ở **authentication, handshake, host key verification, session, remote list, download, upload, rename**; mỗi lỗi có khả năng retry khác nhau.

| Lỗi | Policy cần cân nhắc |
|---|---|
| Server chưa reachable | Retry có backoff/circuit breaker. |
| Session bị đóng giữa transfer | Reconnect; kiểm tra partial file và idempotency. |
| Wrong password/host key | Không retry hàng loạt; xử lý bảo mật. |
| Remote directory/permission denied | Thường cần sửa cấu hình, không spam attempts. |
| Upload xong nhưng ACK bị mất | Readback file đích, tránh upload trùng/ghi đè sai. |
| Hai bản cùng tên | Naming/versioning/rename policy rõ ràng. |

Với SFTP integration test, dùng **server thử nghiệm isolated**, host key và credential test, kiểm tra file ở remote/local đích. Không tắt host key verification chỉ để test dễ hơn. Mock message source/handler là phù hợp để kiểm tra downstream flow, nhưng **không chứng minh session/reconnect**.

## 18. Test retry với JDBC/database adapter

Trong JDBC polling hoặc outbound gateway, retry dễ tạo lỗi nếu **transaction boundary** không được hiểu đúng.

### 18.1. Transaction được retry ở đâu?

~~~text
BEGIN TRANSACTION
  UPDATE inbox_event SET status='PROCESSING'
  INSERT INTO orders ...
COMMIT
~~~

Khi deadlock/serialization failure, có thể cần **rollback toàn transaction** rồi thực thi lại từ đầu, chứ không chỉ retry một statement sau khi transaction đã vào trạng thái lỗi.

| Test | Kỳ vọng |
|---|---|
| Deadlock transient | Rollback và retry ở transaction boundary phù hợp. |
| Unique constraint violation do duplicate business key | Không retry vô ích; trả kết quả tồn tại/conflict theo policy. |
| DB unavailable giữa transaction | Trạng thái khôi phục đúng, không false commit. |
| Commit thành công nhưng client timeout | Readback theo business key; không insert duplicate. |
| Two pollers claim same row | Claim/lock phù hợp, side effect idempotent. |
| Exhausted sau nhiều deadlock | Quarantine/escalation nhưng row vẫn recoverable. |
| Recovery insert vào error table cũng fail | Không che original failure hoặc đánh dấu đã xử lý. |

### 18.2. H2 không thay thế DB thật khi test locking

H2/fake repository giúp kiểm thử service logic, nhưng **isolation, `SELECT FOR UPDATE`, `SKIP LOCKED`, timestamp precision và behavior sau deadlock** có thể khác PostgreSQL/MySQL/SQL Server. Khi kiểm thử cạnh tranh giữa nhiều poller, dùng DB engine tương đương production trong môi trường isolated.

### 18.3. Database + broker là hai transaction boundaries

Nếu handler cập nhật DB rồi publish Kafka/JMS, việc rollback DB không nhất thiết rollback message broker, và ngược lại. Cần kiểm thử **outbox/inbox, idempotency hoặc reconciliation** nếu hệ thống có yêu cầu delivery xuyên hai miền. RetryAdvice tự nó không tạo distributed transaction an toàn.

## 19. Test retry và redelivery với JMS

JMS có cơ chế **session acknowledgment/transaction và provider redelivery**. Nếu gắn Spring Retry vào business handler, bạn có thể có **retry trong process** kết hợp với **redelivery sau rollback**.

~~~mermaid
flowchart TD
    Q["JMS destination"] --> L["Listener nhận message"]
    L --> R["Retry advice<br/>maxAttempts = 3"]
    R --> H["Business handler"]
    H --> X{"Success?"}
    X -- "Có" --> ACK["ACK / commit theo session"]
    X -- "Không" --> REC["Recovery hoặc propagate"]
    REC --> D{"ACK/rollback policy?"}
    D -- "Rollback / recover" --> AGAIN["JMS provider redelivery"]
    AGAIN --> L
    D -- "Handled + commit" --> HANDLED["Chỉ an toàn nếu recovery durable"]
~~~

### 19.1. Các ca JMS cần có broker thử nghiệm

1. Handler fail hai lần rồi success: advice attempts đúng; session commit/ack một lần theo cấu hình.
2. Handler always fail: retry exhausted; kiểm tra rollback/redelivery hoặc DLT theo policy.
3. Recovery lưu DLT thành công: source message được ACK/commit khi contract cho phép.
4. DLT publish fail: source không mất im lặng.
5. Message có redelivery count/header do provider cung cấp: audit không trộn với retry count nội bộ.
6. Restart listener giữa attempt: message có thể redeliver; idempotency vẫn đúng.
7. Message poison: không khóa một queue vô thời hạn.

**Không tự khẳng định mỗi provider JMS dùng một header/behavior redelivery duy nhất.** Kiểm tra container, session mode và broker được triển khai.

## 20. Test retry và recoverer với AMQP

Với AMQP (ví dụ RabbitMQ), cần tách **application handler retry** khỏi **consumer ACK/NACK, requeue, DLX/DLQ** và **publisher confirm**.

| Cơ chế | Ý nghĩa | Test |
|---|---|---|
| Handler retry | Thử business handler lại trong process. | Attempts/recovery callback. |
| Consumer ACK | Consumer báo đã xử lý delivery theo policy. | Broker không redeliver ngoài mong muốn. |
| NACK/reject/requeue | Broker có thể giao lại message. | Không tạo vòng requeue nóng vô hạn. |
| DLX/DLQ | Định tuyến message không xử lý được. | Message thật có trong queue đúng, metadata/cause. |
| Publisher confirm | Broker xác nhận publish ở phạm vi tương ứng. | Không đồng nhất confirm với business completion. |

### 20.1. Bẫy phổ biến

~~~text
Handler fails
  → Spring Retry exhausted
  → Recoverer logs warning, returns normally
  → Listener container decides delivery handled
  → ACK message
  → Message không còn ở source, nhưng chưa được quarantine
~~~

Với hệ thống yêu cầu bảo toàn message, đây có thể là **mất dữ liệu nghiệp vụ**. Test phải chứng minh **quarantine/DLQ đã persist** trước khi cho phép source ACK theo thiết kế. Nếu không có bằng chứng, phải propagate/escalate chứ không coi việc log error là recovery đủ.

### 20.2. Redelivery không tự giải quyết poison message

NACK-requeue liên tục có thể tạo vòng lặp nóng và làm quá tải broker. Nên dùng retry bounded, delayed retry/DLX hoặc parking lot theo khả năng của broker/container; test số attempt, alert, backlog và khả năng redrive có kiểm soát.

## 21. Test retry với Kafka

Kafka có ngữ nghĩa **consumer group, partition, offset, commit**, nên retry nội bộ handler khác với redelivery/reprocessing của Kafka listener.

### 21.1. Retry ở đâu?

- `RequestHandlerRetryAdvice` có thể bọc handler trong một Spring Integration flow.
- Kafka listener container có error/retry/seek/DLT behavior riêng tùy Spring Kafka configuration.
- Kafka `MessageSource` trong polling flow có lifecycle khác message-driven consumer.
- Nhiều retry layers chồng lên nhau làm tổng số attempt lớn hơn dự kiến.

| Test | Điều cần xác minh |
|---|---|
| Retry nội bộ 3 attempts | Handler được gọi đúng ba lần trong một delivery logic. |
| Kafka redelivery/reprocessing | Offset và state consumer theo policy, có thể chạy handler thêm. |
| Poison event | DLT record đúng topic/key/header, không khóa partition vô hạn. |
| DLT publish thất bại | Không commit offset như thể đã xử lý xong nếu mất dữ liệu trái contract. |
| Consumer rebalance | Idempotency và in-flight work an toàn. |
| Duplicate event ID | Business side effect không tạo trùng. |
| Order theo partition | Không phát biểu bảo đảm thứ tự toàn topic. |
| Restart giữa DB write và offset commit | Readback/dedupe đúng. |

### 21.2. Kafka offset commit không phải business confirmation

Một consumer có thể commit offset sau khi recoverer gửi DLT. Điều đó là một **kết thúc xử lý nguồn theo policy**, không nghĩa side effect nghiệp vụ thành công. Dashboard nên phân biệt **processed, recovered-to-DLT, failed-without-durable-recovery**.

### 21.3. Cần test broker thật

Mockito mock `KafkaTemplate` chỉ kiểm tra rằng code đã gọi publish; không chứng minh Kafka đã lưu record, offset commit hoặc DLT tồn tại. Dùng broker isolated/ephemeral để kiểm tra schema, partition/key, retry, rebalance và thực thể DLT khi các đặc tính này là mục tiêu test.

## 22. Retry trên gateway request-reply: đặc biệt nguy hiểm

Một gateway đồng bộ như `OrderReply submit(OrderRequest)` làm caller **chờ reply**, trong khi handler có thể retry theo policy.

### 22.1. Ba trường hợp cần tách

1. **Success trước reply deadline:** gateway nhận reply đúng, 0 recovery.
2. **Handler exhausted và propagate:** caller nhận lỗi/timeout theo contract.
3. **Handler exhausted nhưng recoverer gửi error event rồi trả bình thường:** gateway có thể **không có reply**, dẫn tới timeout thay vì một error response tức thì.

Không dùng `ErrorMessageSendingRecoverer` một chiều rồi khẳng định gateway đã trả lỗi có cấu trúc cho caller. Nếu API cần trả `UPSTREAM_UNAVAILABLE`, phải có **mapping recovery/error sang reply** với kiểu và status rõ ràng, được test.

### 22.2. Tổng deadline

Một request có 1.5 giây reply timeout, nhưng handler retry 5 lần mỗi lần chờ 500 ms sẽ khó phù hợp với thời gian caller chấp nhận. Test cần:

- Có giới hạn attempt và **elapsed time** của toàn workflow.
- Deadline truyền qua các tầng nếu cần.
- Không tiếp tục tạo side effect nguy hiểm sau khi caller từ bỏ.
- Reply đến muộn được xử lý mà không ghép vào request mới.
- Unknown outcome có kênh tra cứu theo business key.

Không dùng `Thread.sleep` làm cơ chế đồng bộ chính; dùng fake reply có latch, bounded wait và observation points.

## 23. Circuit breaker, rate limiter và backpressure khác retry

Retry chỉ nên là **một** cơ chế resilience. Nếu HTTP partner bị lỗi toàn bộ, retry ở từng message có thể gây **thêm tải**, không giúp server phục hồi.

| Cơ chế | Câu hỏi | Test |
|---|---|---|
| **Retry** | Một operation có nên thử lại? | Attempt count, error classifier, backoff. |
| **Circuit breaker** | Có nên tạm ngừng gọi upstream đang lỗi? | Open/half-open/close, fallback/escalation. |
| **Rate limiter** | Có vượt quota/throughput cho phép không? | Từ chối/xếp hàng khi vượt ngưỡng. |
| **Bulkhead** | Một upstream lỗi có chiếm toàn bộ thread không? | Saturation, resource isolation. |
| **Backpressure** | Consumer có xử lý kịp tốc độ nguồn không? | Queue limits, stop/pause/reject. |
| **Timeout** | Một attempt/gateway được phép chờ bao lâu? | Deadline và cleanup. |
| **Recoverer** | Sau khi không xử lý được, bảo toàn lỗi và tiến trình thế nào? | Error event, DLQ, human review, redrive. |

Không phải mọi ứng dụng cần mọi cơ chế. Điều quan trọng là **không cấu hình retry trái với giới hạn của hệ thống ngoài** hoặc che lỗi bằng recoverer để dashboard trông “100% success”.

## 24. Redrive sau recoverer: xử lý lại có kiểm soát

Khi recoverer đưa message vào **parking lot/DLQ/quarantine**, chương trình cần trả lời: **ai** có quyền phát lại, **khi nào**, **điều kiện gì**, và **hệ thống có tránh side effect trùng hay không**.

~~~mermaid
flowchart TD
    A["Message bị lỗi"] --> R["Retry bounded"]
    R --> Q["Quarantine / DLT"]
    Q --> REVIEW["Review reason + payload schema<br/>owner được phân công"]
    REVIEW --> DECIDE{"Có thể redrive?"}
    DECIDE -- "Chưa" --> HOLD["Giữ trạng thái pending<br/>alert / remediation"]
    DECIDE -- "Có" --> VALID["Xác minh version, idempotency<br/>target state và scope"]
    VALID --> REPLAY["Redrive có audit ID"]
    REPLAY --> PROCESS["Business processing"]
    PROCESS --> VERIFY["Verify outcome"]
    VERIFY --> CLOSE["Resolve quarantine record"]
~~~

### 24.1. Những trường nên giữ trong quarantine

~~~json
{
  "quarantineId": "q-evt-order-2048",
  "eventId": "evt-order-2048",
  "tenantId": "VN",
  "sourceTransport": "KAFKA",
  "sourceReference": "orders-topic:partition-2:offset-991",
  "handler": "orderPartnerHttpHandler",
  "policyVersion": "retry-policy-v3",
  "attemptCount": 3,
  "failureCategory": "UPSTREAM_503",
  "firstFailedAt": "2026-11-23T09:00:00Z",
  "lastFailedAt": "2026-11-23T09:00:02Z",
  "status": "QUARANTINED",
  "redriveCount": 0,
  "owner": "integration-operations"
}
~~~

Đây là **schema minh họa do bài học đề xuất**, không phải output mặc định của Spring Integration. `sourceReference` có ý nghĩa tùy adapter; không giả định File/SFTP/HTTP có Kafka partition/offset.

Một record quarantine nên liên kết tới payload nguồn **bằng cách bảo vệ dữ liệu và phân quyền phù hợp**, không nhất thiết sao chép toàn bộ PII/secret vào bảng lỗi hoặc log công khai.

### 24.2. Test redrive

| Tình huống | Điều cần assert |
|---|---|
| Lỗi được sửa, phát lại | Event đi qua handler; record chuyển `RESOLVED` chỉ sau verified outcome. |
| Message chưa được xử lý do lỗi hệ thống | Không cấp trạng thái success chỉ vì đã chọn Redrive. |
| Redrive cùng event ID hai lần | Idempotency bảo vệ business side effect. |
| Payload vẫn sai schema | Quarantine lại có nguyên nhân, không retry storm. |
| Event version cũ bị thay thế | Không ghi đè trạng thái mới. |
| Redrive thất bại do broker unavailable | Không xóa record nguồn và không báo đã phát lại. |
| Người không có quyền redrive | Bị từ chối, có audit. |
| Payload chứa secret/PII | Không lộ qua UI/log của quy trình redrive. |

## 25. Retry stateful và stateless: chọn đúng tình huống

Một vòng **stateless retry** thực thi lại callback trong cùng ngữ cảnh gọi, thường phù hợp khi handler cần retry vài lần trước khi trả lỗi. **Stateful retry** có thể dùng ngữ cảnh/khóa để giữ trạng thái retry qua các lần invocation theo khả năng thư viện/cấu hình.

| Tiêu chí | Stateless | Stateful |
|---|---|---|
| Trạng thái attempt | Chủ yếu trong một lần execute. | Có thể liên kết qua nhiều lần gọi bằng key/context. |
| Cần identity của operation | Không nhất thiết để đếm retry trong một execute. | Rất quan trọng để không lẫn các operation. |
| Phù hợp | Một handler call có retry nhanh. | Workflow có transaction rollback/redelivery cần nhận diện retry history. |
| Nguy cơ | Backoff giữ thread; restart mất retry local. | Cache/key collision, state leak/expiry, concurrency. |
| Test bắt buộc | Attempts, exhaustion, recovery. | Key uniqueness, context retention/eviction, redelivery, restart. |

**Đừng mặc định stateful retry tự tạo persistence bền vững qua process restart.** Một retry context cache trong RAM có thể biến mất khi ứng dụng chết. Nếu yêu cầu còn trạng thái qua restart, cần lưu state có durability theo thiết kế, kèm test restart thực.

### 25.1. Business key cho state

Nên phân biệt:

- `MessageHeaders.ID`: ID message do framework sinh, không nhất thiết bền qua transform/replay.
- `eventId`: identity của event logic từ producer.
- `operationId`: identity của side effect nghiệp vụ.
- `tenantId`: namespace bảo vệ khỏi collision giữa tenant.

Một key như `tenantId + operationType + eventId` có thể phù hợp nếu contract quy định, nhưng cần xét version và các event hợp lệ có cùng entity ID. Không dùng filename/JMS message ID/Kafka offset như business key chung cho mọi adapter.

## 26. Failure injection: tái tạo lỗi mà không làm test flaky

Một retry test tốt phải **tạo lỗi có chủ đích ở đúng attempt**, không phụ thuộc server ngẫu nhiên không ổn định.

### 26.1. Handler fail N lần, sau đó thành công

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.messaging.MessageHandler;

AtomicInteger calls = new AtomicInteger();

MessageHandler failFirstTwo = message -> {
    int attempt = calls.incrementAndGet();
    if (attempt <= 2) {
        throw new IllegalStateException("temporary failure");
    }
    // Xác nhận side effect trong fixture khi attempt thứ ba chạy.
};
~~~

Nếu handler được thay qua `MockIntegrationContext`, cần chắc chắn advice vẫn **bao quanh đúng endpoint** theo cơ chế substitution của phiên bản. Một số cách mock thay toàn bộ endpoint có thể làm mất đoạn logic cần test; hãy đọc **kết quả attempt count** thay vì chỉ giả định advice được gọi.

### 26.2. Dùng latch cho concurrency và timeout

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

CountDownLatch started = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);

// Trong fake handler:
//   started.countDown()
//   if (!release.await(2, TimeUnit.SECONDS)) {
//       throw new IllegalStateException("test-controlled timeout");
//   }
//
// Trong test:
//   start handler trên executor
//   assertTrue(started.await(1, TimeUnit.SECONDS))
//   kiểm tra trạng thái pending rồi release.countDown()
//   đợi result/future với timeout hữu hạn
~~~

Đoạn này là **pseudocode Java cho fixture**: exception checked của `await` phải được xử lý trong code handler cụ thể. Mục tiêu là điều khiển thứ tự, không cần `Thread.sleep`. Với request-reply gateway, việc giữ reply sau timeout cần kiểm tra pending correlation cleanup.

### 26.3. Fault injection trên transport thật

| Transport | Fault injection | Cần xác minh |
|---|---|---|
| HTTP | Stub 503/429, server close, delayed response | Method/body/header, retry/backoff, unknown outcome. |
| SFTP | Server down, wrong host key, disconnect giữa upload | Reconnect, partial file, metadata/readback. |
| File | Permission denied, file biến mất, file chưa ready | Error path, filter, không đọc thiếu bytes. |
| JDBC | Kill connection, deadlock, transaction rollback | Claim/lock, retry đúng boundary, không duplicate. |
| JMS | Broker restart, session rollback | Provider redelivery, DLQ/ack. |
| AMQP | NACK/requeue, DLX failure, publisher confirm timeout | Recovery durable, không requeue storm. |
| Kafka | Broker unavailable, consumer rebalance, DLT publish lỗi | Offset/partition, idempotency, không mất message. |

Chỉ chạy fault injection trên **môi trường thử nghiệm cô lập**. Không vô tình kill broker hoặc thay quyền access của môi trường production.

## 27. Đếm attempts, retries, deliveries và business operations

Nếu một Kafka record được giao hai lần, mỗi delivery có ba handler attempts, nhưng business database chỉ ghi một lần:

~~~text
Deliveries = 2
Attempts per delivery = 3
Total handler invocations = 6
Successful business writes = 1
~~~

Các số này **không mâu thuẫn**. Chúng đo các tầng khác nhau.

### 27.1. Dữ liệu nên ghi trong audit/test evidence

| Trường | Mục đích |
|---|---|
| `eventId` / `operationId` | Nhận diện message logic, side effect. |
| `transportMessageId` | Gỡ lỗi tại broker/adapter cụ thể. |
| `deliveryAttempt` | Số lượt broker/source giao lại nếu có dữ liệu tin cậy. |
| `localRetryAttempt` | Attempt trong `RetryTemplate`. |
| `policyVersion` | Quy định đã chọn bao nhiêu attempts, loại lỗi gì. |
| `handlerName` / `endpointId` | Xác định đoạn được retry. |
| `failureCategory` | Lỗi transient/permanent/unknown. |
| `recoveryOutcome` | Propagated, quarantined, DLT persisted, fallback... |
| `targetEvidenceId` | Bằng chứng side effect ở đích. |
| `occurredAt` / `processedAt` | Đo thời gian đúng nghĩa. |

Không log toàn bộ token, password, private key hoặc payload nhạy cảm chỉ để tăng tiện ích debug. Với field nhạy cảm, dùng redaction hoặc tham chiếu tới evidence store có phân quyền.

## 28. Kiểm thử timeout, interruption và shutdown

### 28.1. Timeout per attempt khác total deadline

Một policy có thể cho mỗi HTTP call chờ 2 giây, tối đa 5 attempts, backoff tăng dần. Khi đó **thời gian tệ nhất** có thể vượt ngưỡng caller mong đợi. Test nên kiểm tra tổng ngân sách và điều kiện dừng, không chỉ attempt count.

### 28.2. Interrupted while backing off

Khi ứng dụng shutdown, thread đang chờ backoff có thể bị interrupt. Các việc cần test:

1. Retry không tiếp tục vô hạn sau khi endpoint bị dừng.
2. Tín hiệu interruption được xử lý đúng theo thư viện/runner.
3. In-flight side effect đã hoàn tất hay chưa được ghi nhận rõ.
4. Consumer/broker ACK không đánh dấu thành công giả.
5. Teardown của JUnit không để executor còn chạy sau test.

Không tự dùng `Thread.stop()` hoặc giết thread để dọn flaky test. Có thể dùng `Future` với timeout/cancel, lifecycle stop và resource cleanup phù hợp. **Cancel một future không undo side effect** ở HTTP, DB hay broker.

### 28.3. Clock cho nghiệp vụ, không giả định cho scheduler

`Clock.fixed` giúp kiểm tra expiry/deadline nghiệp vụ, nhưng **không tự điều khiển `Thread.sleep`, Spring Retry backoff hoặc `TaskScheduler`**. Để test backoff, dùng fake policy; để test cron, dùng trigger/calendar riêng; để test remote timeout, dùng server giả lập có điều khiển.

## 29. Bảo mật của retry và recoverer

Một hệ thống retry không an toàn có thể trở thành công cụ phát tán credential hoặc tấn công lặp lại hệ thống ngoài.

| Rủi ro | Test bảo mật |
|---|---|
| **Retry credential sai** | Không spam đăng nhập với password/token sai. |
| **SFTP host key mismatch** | Không bypass trust verification để retry. |
| **HTTP 401/403** | Không gửi lặp thông tin nhạy cảm vô ích. |
| **Quarantine payload chứa PII** | Không log thô; truy cập có authorization. |
| **DLQ cross-tenant** | Message của tenant A không lộ cho tenant B. |
| **Redrive không có authority** | Người không được cấp quyền bị từ chối. |
| **Replay request cấp quyền/chi tiền** | Idempotency và kiểm soát thẩm quyền vẫn có hiệu lực. |
| **Retry storm** | Giới hạn tốc độ, tài nguyên và alert. |
| **Error response** | Không tiết lộ stack trace/credential. |
| **Poison message** | Quarantine an toàn, tránh crash loop. |

### 29.1. ErrorMessage không nên là bản sao dữ liệu nhạy cảm

`ErrorMessage` có thể chứa nguyên nhân lỗi, failed message hoặc context. Khi đưa error flow vào log, monitoring hoặc DLQ cần **data minimization và access control**, đặc biệt nếu source là hóa đơn, hồ sơ nhân sự hoặc token tích hợp. Test bảo mật phải kiểm tra log/error payload sau masking, không chỉ production code.

## 30. Ma trận kiểm thử đầy đủ

| # | Kịch bản | Tầng | Assertion chính |
|---:|---|---|---|
| 1 | Handler thành công lần đầu | RetryTemplate unit | 1 attempt, 0 recoveries. |
| 2 | Fail một lần rồi success | Unit | 2 attempts, 0 recoveries. |
| 3 | Success lần cuối | Unit | `maxAttempts` đúng, không recovery. |
| 4 | Fail toàn bộ | Unit | `maxAttempts` và 1 recovery. |
| 5 | Không cấu hình recoverer | Unit/flow | Propagate error theo contract. |
| 6 | Permanent validation exception | Unit | Không retry vô ích. |
| 7 | Wrapped transient exception | Unit | Classifier theo cause chain đúng. |
| 8 | Wrapped permanent exception | Unit | Không mở retry loop do wrapper. |
| 9 | Recoverer trả fallback | Unit/gateway | Caller hiểu trạng thái fallback, không false success. |
| 10 | Recoverer throw | Unit | Original và recovery failure được quan sát. |
| 11 | Error channel đầy | Flow | Không nuốt lỗi hoặc ghi nhận thành công giả. |
| 12 | DLT publisher fail | Broker integration | Source không mất nếu contract yêu cầu durability. |
| 13 | Advice không gắn vào endpoint | Flow | Test phát hiện thiếu retry. |
| 14 | RetryAdvice gắn đúng endpoint ID | Flow | Handler attempt đúng. |
| 15 | Fake handler chỉ lỗi một lần | Flow | Message thành công sau retry. |
| 16 | Source poll lỗi | Poller | Source error path riêng. |
| 17 | Handler lỗi trong DirectChannel | Flow sync | Exception/Recovery theo config. |
| 18 | Handler lỗi trong ExecutorChannel | Flow async | Bằng chứng async/error channel; bounded wait. |
| 19 | Gateway cần reply nhưng recoverer chỉ gửi error | Gateway | No-reply/timeout được xử lý có chủ đích. |
| 20 | Gateway timeout trước khi retry hoàn tất | Gateway | Deadline và pending operation rõ. |
| 21 | Backoff fixed | Unit | Số lần backoff đúng. |
| 22 | Exponential backoff | Unit | Delay nằm trong policy bounds. |
| 23 | Jitter | Unit | Giá trị trong bounds, deterministic seed nếu cần. |
| 24 | Interrupted backoff | Lifecycle | Không retry vô hạn khi stop. |
| 25 | HTTP 503 → 503 → 200 | HTTP transport | Đúng requests, status/body và kết quả. |
| 26 | HTTP 400 | HTTP transport | Không retry cùng payload. |
| 27 | HTTP 429 | HTTP transport | Backoff theo hạn/contract. |
| 28 | HTTP read timeout sau POST | HTTP E2E | Readback/idempotency trước retry. |
| 29 | SFTP server down rồi recover | SFTP integration | Reconnect, file đúng, số uploads. |
| 30 | SFTP partial transfer | SFTP integration | Không đánh dấu hoàn tất sớm. |
| 31 | File chưa ready | File integration | Không xử lý file partial. |
| 32 | File CSV poison | File/flow | Quarantine, không lặp vô hạn. |
| 33 | JDBC deadlock | DB integration | Retry toàn transaction thích hợp. |
| 34 | JDBC unique constraint violation | DB integration | Không insert duplicate bằng retry. |
| 35 | Hai poller cạnh tranh row | DB concurrency | Side effect không trùng. |
| 36 | JMS rollback/redelivery | JMS broker | ACK/commit đúng policy. |
| 37 | JMS DLQ error | JMS broker | Message không mất im lặng. |
| 38 | AMQP nack/requeue | AMQP broker | Không nóng loop, message recoverable. |
| 39 | AMQP DLT/DLX publish lỗi | AMQP broker | Recovery failure được báo. |
| 40 | Kafka consumer rebalance | Kafka integration | Không sai offset/idempotency. |
| 41 | Kafka DLT persisted | Kafka integration | Target topic đúng record/key. |
| 42 | Kafka DLT publish fail | Kafka integration | Không false commit. |
| 43 | Duplicate event ID | Domain + DB | Một business side effect trong scope. |
| 44 | Replay message sau restart | E2E | Durable recovery/idempotency. |
| 45 | Redrive by unauthorized user | Security | Bị từ chối và audit. |
| 46 | Cross-tenant DLQ | Security | Không lộ payload tenant khác. |
| 47 | Error logging | Security | Không có secret trong log. |
| 48 | Retry storm 100 consumer | Resilience | Giới hạn attempts/concurrency/backoff. |
| 49 | Recovery alert rate | Operations | Không gửi lặp vô hạn một event. |
| 50 | Flow thành công nhưng target chưa xác nhận | E2E | Không báo business completed sai. |

### Cách đọc kết quả test

- **PASS ở unit:** retry policy/callback đúng trong điều kiện mô phỏng.
- **PASS ở flow:** advice và channel wiring thật được thực thi.
- **PASS ở transport:** protocol/ACK/recovery được xác minh với server/broker test.
- **PASS ở E2E:** business side effect cuối được quan sát và đúng hợp đồng.

Không dùng kết quả ở tầng thấp để tự khẳng định tầng cao hơn. Một test có thể đúng kỹ thuật nhưng **coverage chưa bao gồm network failure, crash hoặc tenant isolation**.

## 31. Ví dụ hoàn chỉnh: recoverer đưa ErrorMessage vào QueueChannel

Mục tiêu: test một **one-way flow** mà handler luôn fail, retry tối đa ba attempts và cuối cùng publish `ErrorMessage` tới channel chuyên biệt. Bài này kiểm tra **lifecycle của retry/recovery ở tầng Spring Integration**, không có broker thật.

### 31.1. Cấu hình Spring Integration

~~~java
package example.retry;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.messaging.MessageHandler;
import org.springframework.retry.support.RetryTemplate;

@Configuration
@EnableIntegration
public class ExhaustedRetryFlowConfig {

    @Bean
    DirectChannel workRequests() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel exhaustedFailures() {
        return new QueueChannel();
    }

    @Bean
    AtomicInteger failedAttempts() {
        return new AtomicInteger();
    }

    @Bean
    RequestHandlerRetryAdvice exhaustedRetryAdvice(
            QueueChannel exhaustedFailures) {
        RequestHandlerRetryAdvice advice =
                new RequestHandlerRetryAdvice();

        advice.setRetryTemplate(RetryTemplate.builder()
                .maxAttempts(3)
                .fixedBackoff(1)
                .build());

        advice.setRecoveryCallback(
                new ErrorMessageSendingRecoverer(exhaustedFailures));
        return advice;
    }

    @Bean
    IntegrationFlow exhaustedRetryFlow(
            DirectChannel workRequests,
            AtomicInteger failedAttempts,
            RequestHandlerRetryAdvice exhaustedRetryAdvice) {

        MessageHandler alwaysFail = message -> {
            failedAttempts.incrementAndGet();
            throw new IllegalStateException("external target unavailable");
        };

        return IntegrationFlow.from(workRequests)
                .handle(alwaysFail,
                        endpoint -> endpoint
                                .id("failingOutboundEndpoint")
                                .advice(exhaustedRetryAdvice))
                .get();
    }
}
~~~

**Hợp đồng của ví dụ:** giả định `RequestHandlerRetryAdvice` có thể xử lý lời gọi `MessageHandler` này và recoverer publish lỗi thành công vào `QueueChannel`. Không có HTTP/JMS/Kafka hoặc transaction nào được kiểm thử trong cấu hình này.

### 31.2. JUnit test

~~~java
package example.retry;

import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ExhaustedRetryFlowConfig.class)
class ExhaustedRetryFlowTest {

    @Autowired
    @Qualifier("workRequests")
    DirectChannel input;

    @Autowired
    @Qualifier("exhaustedFailures")
    QueueChannel failures;

    @Autowired
    AtomicInteger failedAttempts;

    @Test
    void retriesThreeTimesThenPublishesOneErrorMessage() {
        failedAttempts.set(0);

        boolean accepted = input.send(
                MessageBuilder.withPayload("order-2048")
                        .setHeader("eventId", "evt-2048")
                        .build());

        // Ở flow đồng bộ này, recoverer xử lý exception
        // và publish ErrorMessage qua channel.
        assertTrue(accepted);
        assertEquals(3, failedAttempts.get());

        Message<?> error = failures.receive(1_000);
        assertNotNull(error);
        assertInstanceOf(ErrorMessage.class, error);
        assertInstanceOf(Throwable.class, error.getPayload());
        assertNull(failures.receive(0));
    }
}
~~~

### 31.3. Kết luận chính xác của test

Test chứng minh:

1. Advice đã thực sự gắn với endpoint.
2. Handler lỗi được thử đúng ba attempts.
3. Recoverer phát một error event sau exhaustion.
4. Message error được nhận trong channel thử nghiệm.
5. Test không chờ vô hạn.

Test **không chứng minh** error event đã được lưu bền vững qua restart, không kiểm tra ACK broker, không khẳng định service ngoài đã hoạt động, và không biết original event có thể được retry/redeliver từ nguồn thật hay không.

Nếu triển khai code trên một dòng phiên bản có API khác, cần đối chiếu `ErrorMessageSendingRecoverer`, Java DSL `advice` và cách xây `RetryTemplate` theo đúng thư viện đã khóa trong dự án. Bài học ở đây là **cấu trúc kiểm thử retry và recovery**, không phải yêu cầu buộc dùng một phiên bản cụ thể.

## 32. Case study: SFTP inbound → HTTP outbound → kết quả Kafka

### 32.1. Bài toán

Đối tác tải file `orders-*.ready` qua SFTP. Hệ thống dùng inbound polling adapter lấy file, parse đơn hàng, gọi HTTP service để đăng ký đơn, rồi phát event kết quả lên Kafka. Có những nguy cơ:

- SFTP server không trả lời hoặc file chưa upload xong.
- CSV có row sai định dạng hoặc tenant không hợp lệ.
- HTTP trả 503 hoặc read timeout sau khi đã tạo đơn.
- Kafka broker tạm không khả dụng khi cần phát kết quả.
- Message được đọc lại sau restart hoặc redrive.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound<br/>ready files"] --> PARSE["Validate / Parse"]
    PARSE --> HTTP["HTTP outbound gateway<br/>retry policy"]
    HTTP --> KAFKA["Kafka result publisher"]
    PARSE --> BAD["Invalid file quarantine"]
    HTTP --> ERR["Retry exhausted<br/>recovery record"]
    KAFKA --> PUBERR["Publish recovery<br/>outbox / alert"]
~~~

### 32.2. Đặt policy cho từng đoạn, không dùng một retry cho toàn flow

| Boundary | Lỗi/condition | Policy cần thiết kế |
|---|---|---|
| SFTP list/download | Server mất kết nối | Retry/backoff ở source, partial file safety. |
| CSV validation | Thiếu cột bắt buộc | Reject/quarantine, không retry same bytes. |
| HTTP registration | 503 trước khi có response | Bounded retry, idempotency key trên request. |
| HTTP registration | Timeout sau khi gửi POST | Lookup/readback theo order ID, không retry mù quáng. |
| Kafka result publisher | Broker không khả dụng | Outbox/publish retry, không mất trạng thái đã đăng ký. |
| Source checkpoint | Crash trước khi ghi metadata | Redelivery/idempotent operation. |
| Recovery storage | DLQ/quarantine không ghi được | Alert/escalation, không đánh dấu handled giả. |

Nếu gắn một retry advice quanh **toàn bộ parser → HTTP → Kafka**, lần thử lại sau Kafka lỗi có thể **gọi HTTP đăng ký đơn lại**, dù HTTP đã thành công. Chính sách retry phải hạn chế **phạm vi side effect** và ghi nhận trạng thái trung gian đúng.

### 32.3. Trình tự kiểm thử theo tầng

**A — Unit tests:** CSV parser, validator, error classifier, idempotency key builder, mapper `OrderRegistrationResult`. Không dùng Spring context/broker.

**B — Flow isolation tests:** fake SFTP `MessageSource<File>`, HTTP handler fail hai lần rồi success, mock Kafka outbound boundary. Assert thứ tự, attempts, message contract và headers.

**C — SFTP integration:** server thử nghiệm, file ready, host key verification, remote disconnect và metadata restart.

**D — HTTP integration:** server stub trả 503/200, 400, 429, timeout, duplicate request ID và readback.

**E — Kafka integration:** broker thử nghiệm, result event theo key/topic/schema, publish failure, DLT/outbox, recovery.

**F — End-to-end:** một file sinh đúng một đơn hàng và một result event cuối; crash/restart sau HTTP success nhưng trước Kafka publish không làm tạo đơn trùng.

### 32.4. Một failure path quan trọng

~~~text
1. Nhận file orders-500.ready.
2. HTTP POST với Idempotency-Key=order-500 trả 503.
3. Retry lần 2: HTTP đã tạo đơn nhưng response bị mất.
4. Lần 3: server nhận cùng key, trả kết quả đơn đã tạo.
5. Kafka chưa sẵn sàng nên publish result thất bại.
6. Outbox giữ event result chưa publish.
7. Kafka phục hồi; publisher phát result event một lần logic.
8. Readback xác nhận order-500 tồn tại và outbox event đã được publish.
~~~

Test cần có **bằng chứng ở đích**, không chỉ bộ đếm 3 HTTP attempts. Nếu server không hỗ trợ idempotency key, phải thiết kế readback/operation status hoặc compensation phù hợp trước khi quyết định retry.

### 32.5. Điều kiện nghiệm thu của case study

- File chưa hoàn chỉnh không được xử lý.
- CSV sai không kích hoạt HTTP/Kafka.
- HTTP 503 transient được retry có giới hạn; 400 không retry.
- Timeout sau POST không tạo đơn trùng.
- Result event không mất khi Kafka lỗi.
- Recovery failure không được báo handled.
- Correlation từ file/event ID tới HTTP order và Kafka event có thể truy vết.
- Restart/redrive không tạo business side effect trùng.

## 33. Mẫu test plan YAML

~~~yaml
# Schema mô tả test do bài học đề xuất, không phải Spring Integration application.yml.
retryTestPlan:
  id: sftp-order-http-kafka
  ownerTeam: integration-platform
  language: vi

  flow:
    inbound: SFTP
    outbound:
      - HTTP
      - KAFKA
    businessKey:
      fields: [tenantId, operation, eventId]
    correlationHeader: traceId

  retry:
    protectedEndpointId: orderHttpEndpoint
    policyVersion: retry-policy-v3
    maxAttempts: 3
    backoffType: BOUNDED_EXPONENTIAL
    retryable:
      - TRANSIENT_CONNECTIVITY
      - HTTP_503
      - HTTP_429_WHEN_ALLOWED
    nonRetryable:
      - INVALID_PAYLOAD
      - UNAUTHORIZED
      - HOST_KEY_MISMATCH
    unknownOutcome:
      action: RECONCILE_BEFORE_UNSAFE_RETRY

  recovery:
    failureDestination: durable-quarantine
    preserve:
      - eventId
      - tenantId
      - policyVersion
      - failureCategory
      - lastThrowableType
    acknowledgeSourceOnlyAfterDurableRecovery: true
    redriveRequiresApproval: true

  scenarios:
    - success-first-attempt
    - success-last-attempt
    - exhausted-retry
    - non-retryable-validation
    - HTTP-read-timeout-after-side-effect
    - recovery-publisher-unavailable
    - duplicate-delivery
    - restart-before-checkpoint
    - cross-tenant-quarantine

  evidence:
    - businessEventId
    - retryAttempts
    - sourceDeliveryCount
    - recoveryOutcome
    - targetReadback

  cleanup:
    - stop-endpoints
    - reset-substitutions
    - close-test-clients
    - delete-test-files
    - delete-test-broker-resources
    - remove-test-db-records
~~~

**Đây là một cấu trúc kiểm thử minh họa.** Không đặt các key này vào `application.yml` rồi kỳ vọng framework tự nhận. Configuration thực tế của Spring Integration, Spring Retry, Kafka listener, AMQP container hoặc JDBC transaction phải được ánh xạ riêng từ policy đã duyệt.

## 34. Quan sát và đo chất lượng retry/recoverer

Chỉ báo một message “đã được xử lý” là không đủ nếu có nhiều attempts/recovery.

| Metric | Định nghĩa | Rủi ro diễn giải |
|---|---|---|
| **Local retry attempts** | Tổng lượt handler retry trong scope. | Không cộng thẳng thành số business events. |
| **Retry success rate** | Message thành công sau retry / message đã cần retry. | Phải nêu loại lỗi và cohort. |
| **Exhaustion rate** | Message cạn attempts / message có retry đã đánh giá. | Có thể tăng do upstream lỗi rộng, không do riêng app. |
| **Recovery publish success** | Recovery record được đích xác nhận / số lần yêu cầu durable recovery. | Chỉ gọi publisher chưa đủ. |
| **Recovery failure count** | Số lần recoverer tự thất bại. | Critical nếu source đã ACK sau đó. |
| **Unknown outcome backlog** | Request chưa rõ đã có side effect ở đích. | Không được tính như permanent failure hoặc success. |
| **Duplicate business side effect** | Side effects vượt số operation logic. | Cần business ID và target readback. |
| **Oldest quarantine age** | Tuổi record chưa được giải quyết. | Hữu ích để ưu tiên redrive. |
| **Redrive success rate** | Record được xác minh xử lý sau redrive / record được redrive. | Không chỉ đếm nút Redrive được nhấn. |
| **P95/P99 handling latency** | Latency của message đã xác nhận trong scope. | Cần đi kèm pending/overdue count. |

### 34.1. Nguyên tắc đặt label và cardinality

Metric label nên dùng **adapter type, endpoint ID, exception category, policy version, result** thay vì gắn `eventId`/`traceId` làm label cho từng time series vì cardinality rất cao. Correlation chi tiết lưu ở log/trace có phân quyền; dashboard tổng hợp cần có drill-down an toàn.

### 34.2. Alert có ý nghĩa

Không alert một lần cho mỗi retry attempt khi upstream lỗi toàn diện. Có thể gom theo **incident/risk/endpoint** và cảnh báo khi: exhaustion cao, recovery fail, quarantine aging, consumer backlog quá hạn, retry storm hoặc unknown outcome tồn đọng. Test alert logic và redrive policy theo contract, tránh phát hàng nghìn thông báo lặp.

## 35. Chạy test retry/recoverer trong CI/CD

### 35.1. Phân lớp test

| Suite | Chạy khi nào | Tài nguyên |
|---|---|---|
| **Unit tests** | Mọi PR | RetryTemplate, fake backoff, mapper, classifier. |
| **Flow tests** | Mọi PR | Spring context nhỏ, DirectChannel, QueueChannel, fake handler. |
| **Adapter integration** | Khi sửa adapter/contract, có thể mọi PR nếu CI đủ nhanh | HTTP stub, SFTP server, Kafka/JMS/AMQP broker, DB thử nghiệm. |
| **Recovery/fault injection** | Theo lịch hoặc trước release có rủi ro | Broker restart, network fault, crash/replay, concurrency. |
| **End-to-end** | Trước release quan trọng hoặc theo lịch | Nhiều hệ thống thử nghiệm, target readback. |

### 35.2. Nguyên tắc ổn định

1. **Không dùng `Thread.sleep` như cơ chế đồng bộ chính.** Dùng latch, queue hoặc trạng thái có thể đọc lại.
2. **Không dùng timeout vô hạn.** Mỗi test có ngân sách thời gian và cleanup.
3. **Không dùng production systems.** Mọi URL, queue, directory, DB và credential phải là fixture riêng.
4. **Không dùng chung retry context** giữa các test trừ khi chính đó là điều kiện cần kiểm tra.
5. **Không chạy parallel** trên cùng endpoint/mock/context mutable nếu chưa bảo đảm cô lập.
6. **Reset `MockIntegrationContext`** sau substitution và xử lý in-flight tasks.
7. **Dọn queue, file, DB, topic và quarantine fixture** kể cả khi assertion fail.
8. **Giữ event ID và correlation trong error report**, nhưng không để lộ payload/secret.
9. **Tách lỗi hạ tầng test khỏi lỗi business logic** khi thu thập report.
10. **Không đánh dấu pass** cho transport tests bị skip vì CI không có broker; report rõ coverage gap.

### 35.3. Tránh dữ liệu còn lại từ context cache

Spring Test có thể cache `ApplicationContext`. Một `AtomicInteger` đếm attempt, `QueueChannel` chứa error cũ hoặc mock handler chưa reset có thể làm test sau pass/fail sai. Mỗi test cần fixture riêng, reset counter và state, đồng thời stop endpoint trước khi làm sạch substitution khi có in-flight work.

`@DirtiesContext` chỉ nên dùng khi state không thể khôi phục an toàn; không dùng như cách che việc quên cleanup.

## 36. Anti-pattern phổ biến

| Anti-pattern | Hậu quả | Cách sửa |
|---|---|---|
| Retry mọi exception | CSV sai/401/403 bị gọi lại vô ích. | Exception classifier theo contract. |
| MaxAttempts rất lớn hoặc vô hạn | Giữ thread, retry storm. | Giới hạn attempts, deadline, backoff. |
| Retry toàn flow nhiều side effect | Gọi HTTP và publish Kafka trùng. | Retry đúng boundary, outbox/idempotency. |
| Chỉ assert số lần mock gọi | Không biết business side effect/trạng thái đích. | Transport test/readback. |
| Gọi recoverer = đánh dấu success | Lỗi còn tồn tại nhưng dashboard xanh. | Recovery status riêng, verified evidence. |
| Recoverer log rồi return, source ACK | Message có thể mất vĩnh viễn. | Durable recovery hoặc propagate. |
| DLQ publish failure bị nuốt | Mất dữ liệu không thể redrive. | Test secondary recovery failure. |
| Dùng `ErrorMessageSendingRecoverer` cho gateway mà không tạo reply | Gateway timeout, caller không nhận error contract. | Error-to-reply mapping rõ. |
| Không phân biệt local retry và broker redelivery | Tổng attempts lớn hơn dự kiến. | Đếm theo delivery và operation. |
| Tin HTTP read timeout = server chưa làm gì | Retry tạo duplicate. | Idempotency key và readback. |
| Dùng framework message ID để dedupe | Transform/replay tạo ID mới. | Business event/operation ID ổn định. |
| Dùng `Thread.sleep` cố định để test backoff | Flaky theo tải CI. | Fake BackOffPolicy, bounded observation. |
| Chỉ test success-first-attempt | Không bắt exhaustion, recovery failure. | Test matrix happy/negative/recovery. |
| Chạy SFTP với host-key check disabled | Che lỗi bảo mật. | Dùng server/key thử nghiệm đúng. |
| H2 để chứng minh deadlock/lock production | Kết quả không phản ánh DB thật. | Test engine tương đương. |
| Kafka DLT mock được gọi nghĩa là đã lưu | Offset có thể commit trước khi record tồn tại. | Verify broker DLT/transaction. |
| Không test restart | Mất state retry hoặc lặp side effect. | Restart/replay integration test. |
| Redrive không quản lý thẩm quyền | Người lạ tái thực thi thao tác nhạy cảm. | Approval/audit và tenant isolation. |
| Log toàn bộ payload khi lỗi | Lộ PII/token. | Redact, dữ liệu tối thiểu. |

## 37. Bài tập thực hành

### Bài tập 1 — RetryTemplate thành công sau lỗi

Tạo một callback lần một và hai throw `TemporaryPartnerException`, lần ba trả `"OK"`.

Yêu cầu:

1. Dùng `RetryTemplate` với tổng ba attempts.
2. Ghi số callback invocation và recovery invocation.
3. Assert result, attempts và recoveries.
4. Thêm ca lỗi không retry theo classifier.
5. Giải thích số attempt khác số retry và khác số broker delivery.

### Bài tập 2 — RequestHandlerRetryAdvice trong IntegrationFlow

Tạo `DirectChannel` đầu vào, `MessageHandler` giả và `QueueChannel` output.

Yêu cầu:

1. Gắn `RequestHandlerRetryAdvice` lên endpoint ID rõ.
2. Handler fail hai lần rồi success.
3. Assert payload/header, tổng attempts và một success output.
4. Thử bỏ advice để chứng minh test phát hiện cấu hình retry thiếu.
5. Tách test trực tiếp `RetryTemplate` và flow test; nêu coverage của từng tầng.

### Bài tập 3 — Recoverer, error channel và secondary failure

Tạo handler luôn fail, max attempts=3 và `ErrorMessageSendingRecoverer` gửi vào test `QueueChannel`.

Yêu cầu:

1. Assert recoverer chỉ chạy sau exhaustion.
2. Assert `ErrorMessage` có `Throwable`/cause phù hợp.
3. Chứng minh không có business success message.
4. Mô phỏng error channel/recoverer failure.
5. Định nghĩa source ACK/rollback policy để không mất message.

### Bài tập 4 — HTTP timeout sau khi server đã xử lý

Dùng HTTP test server có state:

1. Lần đầu nhận POST `requestId=R-20`, tạo record rồi **không trả response**.
2. Client timeout và đánh dấu outcome unknown.
3. Client retry với cùng idempotency key hoặc readback trạng thái.
4. Server trả record đã tạo, không tạo record mới.
5. Assert side effect đúng một lần và history attempts đầy đủ.

### Bài tập 5 — Kafka/JMS/AMQP redelivery

Chọn một broker thử nghiệm:

- Cấu hình handler retry nội bộ bounded.
- Cho handler luôn fail và kiểm tra DLQ/DLT hoặc rollback/redelivery thật.
- Mô phỏng recoverer publish fail, xác minh message nguồn vẫn recoverable.
- Khởi động lại consumer, kiểm tra idempotency.
- Phân biệt số delivery, attempts và business operations.

### Bài tập 6 — JDBC transaction và duplicate

Dùng database cùng engine với production trong môi trường test:

1. Tạo một inbox event `READY`.
2. Cho hai poller/worker cạnh tranh claim event.
3. Mô phỏng deadlock/rollback một worker.
4. Retry transaction thích hợp, không insert business record trùng.
5. Mô phỏng commit thành công nhưng caller mất response.
6. Đọc lại bằng business key để xác minh kết quả.

### Bài tập 7 — SFTP/File retry và restart

Dùng thư mục test và SFTP server isolated:

1. Tạo file `*.tmp` rồi rename thành `*.ready`.
2. Ngắt session giữa download/upload.
3. Kiểm tra partial file và retry/reconnect theo hợp đồng.
4. Stop/restart app, kiểm tra metadata store/duplicate.
5. Tạo file CSV lỗi vĩnh viễn, kiểm tra quarantine và alert.

### Bài tập 8 — Test matrix và policy design

Thiết kế retry policy cho luồng `SFTP → CSV → HTTP POST → Kafka`. Hãy nêu:

- Boundary nào được retry, boundary nào không.
- Exception classifier và policy version.
- Max attempts, backoff, deadline và circuit-breaker condition nếu cần.
- Recoverer output, owner, DLQ durability, redrive authority.
- Idempotency key và cách đọc lại trạng thái đích.
- Mười test âm tính, năm test happy/recovery, cách cleanup và evidence.
- Metric về recovery failure, pending, oldest quarantine và duplicate side effect.

## 38. Checklist nghiệm thu

- [ ] **Retry scope được xác định**: đúng handler, endpoint, transaction hay listener.
- [ ] **Error classifier rõ ràng**: transient/permanent/unknown outcome.
- [ ] **Max attempts gồm lần đầu** được hiểu và assert đúng.
- [ ] **Success-first, success-last và exhausted** có test riêng.
- [ ] **RecoveryCallback chỉ chạy khi đúng điều kiện**, không gọi khi đã success.
- [ ] **Permanent failure không retry vô ích**; wrapped exception cũng được kiểm tra.
- [ ] **Backoff bounded**, không tạo retry storm và không test bằng sleep tùy tiện.
- [ ] **RequestHandlerRetryAdvice gắn đúng endpoint**, có flow test thực sự.
- [ ] **Recoverer output được kiểm chứng**, không chỉ đếm method calls.
- [ ] **ErrorMessage được gửi đúng error channel** khi thiết kế yêu cầu.
- [ ] **Recoverer tự thất bại** có test escalation/propagation.
- [ ] **Không báo business success sau khi chỉ quarantine**.
- [ ] **Gateway reply/timeout rõ**, recovery một chiều không được giả làm reply.
- [ ] **Sync/async/poller được test đúng thread và lifecycle**.
- [ ] **Kafka/JMS/AMQP redelivery và ACK/offset** được phân biệt với local attempts.
- [ ] **File/SFTP partial transfer và JDBC transaction** được kiểm tra trên môi trường phù hợp.
- [ ] **HTTP POST timeout có idempotency/readback**, không retry mù quáng.
- [ ] **Restart/redrive/duplicate event** không gây side effect trùng.
- [ ] **Quarantine/DLQ có durability và access control** phù hợp.
- [ ] **Có timeout hữu hạn, fixture riêng, reset và cleanup** trong CI.
- [ ] **Không dùng hệ thống production hoặc lộ secret** trong test/log.
- [ ] **Kết quả QA phân tầng**: unit, flow, transport và E2E không bị đánh đồng.

## 39. Tổng kết

Kiểm thử **retry và recoverer** trong Spring Integration không chỉ là kiểm tra một exception khiến handler chạy lại bao nhiêu lần. Một bộ test đúng phải xác định **lỗi nào được thử lại, advice bảo vệ đoạn nào, lần thử cuối ra sao, recoverer làm gì với message và có bằng chứng nào xác nhận trạng thái kết thúc**. `RetryTemplate` và `RecoveryCallback` giúp unit test chính sách; `RequestHandlerRetryAdvice` và `ErrorMessageSendingRecoverer` hỗ trợ kiểm tra retry/recovery ở endpoint của message flow.

Tuy vậy, **File/SFTP, HTTP, JMS, AMQP, Kafka và JDBC có ranh giới xác nhận, transaction, retry và redelivery khác nhau**. Một retry có thể khiến side effect xảy ra thêm lần nữa nếu request đầu đã thành công nhưng response/ACK bị mất. Vì thế mọi chương trình tích hợp đáng tin cần **idempotency, durable recovery, error classification, bounded backoff, redrive có kiểm soát và test trên transport thật** khi rủi ro yêu cầu.

Khi hoàn thành, bạn phải trả lời được: **message logic nào được nhận, handler chạy bao nhiêu attempts trên bao nhiêu deliveries, lần nào đã gây side effect, lỗi nào khiến dừng thử lại, recoverer đã lưu ở đâu, ai có quyền xử lý lại và bằng chứng nào xác nhận kết quả cuối cùng**. Đó là nền tảng để adapter Spring Integration có thể phục hồi mà không che lỗi hoặc tạo dữ liệu trùng.
