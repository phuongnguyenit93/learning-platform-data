# RequestHandlerRetryAdvice trong Spring Integration Adapters

> **Chương:** Reliability  
> **Chủ đề:** RequestHandlerRetryAdvice  
> **Phạm vi module:** Kết nối hệ thống bên ngoài bằng **Spring Integration** thông qua inbound/outbound adapter, gateway, poller và MessageChannel; thực hành File, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Bài tập trung vào retry đúng ranh giới handler, hợp đồng message, xử lý lỗi, tính nhất quán và vòng đời kết nối.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **RequestHandlerRetryAdvice** là cơ chế bọc lời gọi message handler của Spring Integration bằng Spring Retry.
2. Phân biệt **RetryTemplate, RetryPolicy, BackOffPolicy, RetryContext, RetryCallback và RecoveryCallback** theo đúng trách nhiệm.
3. Gắn advice vào **message-handling endpoint** bằng Java DSL, hiểu điểm nào được thực thi lại và điểm nào không.
4. Chọn số attempts, loại exception được retry, khoảng nghỉ, timeout và deadline; tránh retry vô hạn hoặc nhân tải lên hệ thống ngoài.
5. Thiết kế **recovery** không mất message hoặc âm thầm ack/commit message chưa được bảo toàn.
6. Phân biệt retry trong handler, **broker redelivery**, **Kafka offset/seek**, poller schedule và replay từ durable queue.
7. Áp dụng tới File/SFTP, HTTP, JMS, AMQP, Kafka và JDBC, gắn với **idempotency, transaction và acknowledgement**.
8. Viết test kiểm tra số invocations, exception classification, recovery, negative cases, side effects, crash/restart và observability.

## 2. Bài toán: một handler gọi đối tác tạm thời bị lỗi

Xét một luồng nhận file SFTP, chuyển thành thông điệp rồi đồng bộ đơn hàng tới hệ thống ERP:

~~~text
SFTP inbound adapter + poller
    -> rawFileChannel
    -> parse / validate records
    -> orderChannel
    -> HTTP outbound gateway (ERP)
    -> database status update
    -> AMQP outbound adapter
~~~

HTTP outbound gateway có thể gặp:

- **Connection reset:** kết nối tạm thời hỏng.
- **HTTP 503:** đối tác đang bảo trì hoặc quá tải.
- **HTTP 429:** đối tác giới hạn tốc độ.
- **Read timeout sau POST:** đích có thể đã tạo đơn hàng nhưng response bị mất.
- **HTTP 400/403:** payload hoặc quyền không hợp lệ, thường không sửa bằng cách thử lại.
- **Lỗi sau khi ERP thành công:** database hoặc broker có thể hỏng, dù không nên gửi lại đơn hàng ERP.

Một thiết kế kém gắn retry quanh toàn flow: nếu bước cuối lỗi, file bị đọc lại và HTTP POST bị gửi lần nữa. Thiết kế đúng hơn xác định **mỗi thao tác nào được retry**, kết quả nào đã commit và làm sao chống tác dụng phụ trùng.

**RequestHandlerRetryAdvice** phù hợp khi đơn vị cần thử lại chính là **invocation của một message handler**. Nó không tự khôi phục toàn bộ giao dịch xuyên qua nhiều hệ thống.

## 3. RequestHandlerRetryAdvice là gì?

Trong Spring Integration, **message-handling endpoint** kết nối message channel với logic của handler: transformer, service activator, router, outbound adapter/gateway hoặc handler chuyên dụng tùy thành phần.

**RequestHandlerRetryAdvice** là một message handler advice cho phép dùng Spring Retry ở endpoint phù hợp. Mỗi khi handler ném exception, **RetryTemplate** phối hợp RetryPolicy và BackOffPolicy để quyết định có gọi handler thêm một lần nữa không.

| Thành phần | Nhiệm vụ | Không tự bảo đảm |
|---|---|---|
| Inbound adapter / MessageSource | Nhận hoặc tạo message từ hệ thống nguồn | Message chắc chắn được nhận lại sau mọi lỗi |
| MessageChannel | Truyền message tới subscriber/handler | Durable delivery trong mọi loại channel |
| MessageHandler | Xử lý message hoặc thực hiện I/O ngoài | Thao tác lặp lại sẽ an toàn |
| **RequestHandlerRetryAdvice** | Bọc invocation của handler được gắn advice | Retry cả IntegrationFlow hoặc quản lý broker offset |
| RetryTemplate | Điều phối attempts, callback và recovery | Idempotency, distributed transaction |
| RetryPolicy | Quyết định exception và attempts còn được retry | Thời gian chờ, business recovery |
| BackOffPolicy | Đợi giữa các attempts | Kết nối timeout hay retryability |
| RetryContext | Trạng thái chuỗi retry hiện tại | Lưu bền qua app restart |
| RecoveryCallback | Xử lý khi retry exhausted | Tự động DLQ bền và ack đúng |
| Error channel/container | Tuyến xử lý lỗi hoặc nguồn redelivery | Mọi lỗi đều có thể replay an toàn |

Cần phân biệt advice này với **@Retryable** ở method/service, retry của HTTP client, Kafka listener error handler, JMS/AMQP broker redelivery và lần poll sau. Các cơ chế có thể cùng xuất hiện nhưng có **phạm vi và bộ đếm riêng**.

### Câu hỏi trước khi gắn advice

- Handler có **một** side effect có thể nhận diện được không?
- Nếu lời gọi trả timeout, có thể biết remote đã làm gì chưa?
- Message có **business ID ổn định** để chống trùng không?
- Có tầng nào bên dưới handler tự retry không?
- Lỗi cuối cùng nên ném ra, gửi DLQ hay đưa vào delayed retry?
- Caller/container sẽ ack/commit vào lúc nào?
- Khi app restart giữa retry, nguồn có thể giao lại an toàn không?

## 4. Phạm vi retry: handler chứ không phải toàn flow

~~~mermaid
flowchart LR
    S["SFTP inbound"] --> C["MessageChannel"]
    C --> P["Parse + validate"]
    P --> H["HTTP outbound handler"]
    H --> R["RequestHandlerRetryAdvice"]
    R --> E["ERP API"]
    H --> D["Database update"]
    D --> A["AMQP send"]
    X["Poller / SFTP state"] -.->|"Không nằm trong advice"| S
    R -.->|"Chỉ thực hiện lại handler được bọc"| H
~~~

Nếu advice gắn ở **HTTP outbound handler**:

- Transformer trước đó không tự chạy lại do handler retry.
- Handler HTTP có thể được gọi nhiều lần.
- Khi HTTP cuối cùng thành công, flow tiếp tục.
- Nếu database hoặc AMQP phía sau thất bại, advice ở HTTP handler **không** giải quyết lỗi đó.
- Lần poll SFTP tiếp theo không tự đảm bảo file được tải lại.
- Nếu retry exhausted và exception propagate, caller hoặc consumer/container thực hiện cơ chế lỗi đã cấu hình.

### Vì sao không bọc toàn orchestration?

Giả sử handler tổng hợp thực hiện:

~~~text
handler.process():
    createOrderAtERP()
    updateLocalDatabase()
    publishNotification()
~~~

Nếu ERP thành công, DB thành công nhưng publishNotification lỗi, chạy lại **cả handler** có thể tạo thêm đơn hàng và thêm database update. Chỉ sử dụng retry bao toàn khối khi từng bước idempotent và trạng thái kết quả được quản lý chặt.

Giải pháp thường tốt hơn: **state machine + retry riêng ở từng bước + outbox/inbox + reconciliation**.

## 5. Vòng đời một lời gọi có RequestHandlerRetryAdvice

~~~mermaid
flowchart TD
    A["Message đến endpoint"] --> B["Mở RetryContext"]
    B --> C{"RetryPolicy còn cho phép?"}
    C -->|"Có"| D["Thực thi handler invocation"]
    D -->|"Thành công"| S["Kết thúc và trả kết quả"]
    D -->|"Ném lỗi"| E["Phân loại exception và cập nhật context"]
    E --> F{"Retryable và còn attempts?"}
    F -->|"Có"| W["BackOffPolicy chờ có giới hạn"]
    W --> C
    F -->|"Không"| R{"Có RecoveryCallback?"}
    R -->|"Có"| G["Recovery theo contract"]
    R -->|"Không"| X["Exception nổi lên caller/container"]
    G --> Z["Kết thúc"]
    X --> Z
~~~

Sơ đồ biểu diễn logic. Backoff chỉ quyết định **thời điểm thử tiếp**, không bảo đảm lỗi có thể phục hồi hoặc thao tác lặp lại an toàn.

### Attempt khác retry

Với maxAttempts = 4:

| Lần thực thi | Tên gọi | Backoff trước lần đó? |
|---|---|---|
| 1 | Initial attempt | Không |
| 2 | Retry thứ nhất | Có nếu lần 1 lỗi và retryable |
| 3 | Retry thứ hai | Có nếu lần 2 lỗi và retryable |
| 4 | Retry thứ ba | Có nếu lần 3 lỗi và retryable |
| Sau lần 4 lỗi | Exhausted/recovery | Không có attempt thứ năm |

**4 attempts tổng = 1 lần đầu + tối đa 3 lần thử lại**, không phải 4 retries bổ sung.

## 6. RetryPolicy: chỉ lỗi hợp lệ mới được retry

Không nên retry mọi exception vì có nhiều lỗi không thay đổi dù chờ bao lâu.

| Lỗi hoặc triệu chứng | Retry? | Điều kiện |
|---|---|---|
| Connection reset / temporary unreachable | Có thể | Có timeout và backoff |
| HTTP 503 / 429 | Có thể | Deadline, jitter, rate limit và Retry-After nếu có |
| HTTP 502 / 504 | Tùy operation | Response có thể mất sau khi remote đã commit |
| Connect timeout | Có thể | Kiểm tra khả năng operation được gửi tới đích |
| Read timeout sau POST | Không retry mù | Idempotency key hoặc query trạng thái |
| HTTP 400 / validation | Thường không | Sửa schema/payload |
| HTTP 401 / 403 | Thường không retry cùng credential | Khôi phục token/quyền theo luồng riêng |
| HTTP 404 / 409 | Tùy nghiệp vụ | Có thể eventual consistency hoặc đã xử lý |
| JDBC deadlock / serialization conflict | Có thể | Retry transaction mới phù hợp |
| SFTP auth / host key error | Không retry mù | Cần sửa trust/credential |
| File permission denied | Thường không | Cần sửa ACL hoặc quyền hệ thống |
| Poison message | Không với payload không đổi | Quarantine/manual review |

**Retryability là thuộc tính của cả loại lỗi và operation.** Một IOException có thể tạm thời nhưng nếu HTTP POST không idempotent, retry vẫn nguy hiểm.

### Exception wrapper

Spring Integration có thể ném **MessagingException/MessageHandlingException**, bao bọc lỗi client như ResourceAccessException hoặc SocketTimeoutException. Cần kiểm tra **cause chain** theo ngữ nghĩa của RetryPolicy.

~~~text
MessageHandlingException
  caused by ResourceAccessException
    caused by SocketTimeoutException
~~~

Không nên retry toàn bộ MessagingException vì nó có thể bọc cả lỗi validation hoặc quyền. Bộ test phải xác nhận loại exception **thực tế phát sinh trong version/adapter đang dùng**.

## 7. BackOffPolicy: lựa chọn thời gian chờ

Backoff giúp tránh gửi request liên tục tới hệ thống đang không khỏe.

| Chính sách | Ý tưởng | Lưu ý |
|---|---|---|
| NoBackOffPolicy | Thử lại gần như ngay | Dễ gây retry storm nếu dùng trên mạng |
| FixedBackOffPolicy | Đợi khoảng cố định | Nhiều client dễ thức dậy cùng nhịp |
| ExponentialBackOffPolicy | Khoảng nghỉ tăng theo multiplier đến maxInterval | Không tự thêm jitter thông thường |
| ExponentialRandomBackOffPolicy | Exponential có ngẫu nhiên hóa theo implementation | Phù hợp phân tán tải từ nhiều instance |
| UniformRandomBackOffPolicy | Khoảng nghỉ chọn ngẫu nhiên trong miền quy định | Cần min/max và deadline phù hợp |

Giả sử initialInterval=250 ms, multiplier=2, maxAttempts=4 và không jitter:

~~~text
Attempt 1 --fail--> 250 ms
Attempt 2 --fail--> 500 ms
Attempt 3 --fail--> 1000 ms
Attempt 4 --fail--> exhausted
~~~

Tổng nghỉ = **1.750 ms**. Nếu mỗi HTTP attempt có timeout tối đa 2 giây thì độ trễ xấu nhất gần đúng **4 × 2.000 + 1.750 = 9.750 ms**, chưa gồm overhead.

**BackOffPolicy không đặt timeout cho HTTP connect/read**, không thay deadline tổng, và trạng thái của nó không tự tồn tại qua restart.

### Jitter và retry storm

Nếu 500 worker cùng gặp HTTP 503 lúc 10:00, fixed backoff 1 giây có thể khiến cả 500 worker retry gần như cùng lúc 10:00:01. Exponential có jitter, kết hợp **rate limit** và **concurrency cap**, giúp rải tải.

Không có jitter nào thay thế **idempotency, maxAttempts, deadline, circuit breaker hoặc durable recovery** khi hệ thống ngoài down lâu.

## 8. Mẫu Java: RetryTemplate với lỗi được phân loại

Mẫu sau dùng Spring Retry và ví dụ exception từ Spring Web. Đây là cấu hình tham khảo; phải đối chiếu dependency version và exception thực tế của HTTP adapter.

~~~java
import java.util.HashMap;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;

@Configuration
public class PartnerRetryConfig {

    @Bean
    public RetryTemplate partnerRetryTemplate() {
        Map<Class<? extends Throwable>, Boolean> retryable =
                new HashMap<>();

        // Danh sách ví dụ, không tự áp dụng cho mọi HTTP operation.
        retryable.put(ResourceAccessException.class, true);
        retryable.put(
                HttpClientErrorException.TooManyRequests.class, true);
        retryable.put(
                HttpServerErrorException.ServiceUnavailable.class, true);

        // 4 attempts tổng; xét cause chain; các lỗi khác mặc định false.
        SimpleRetryPolicy retryPolicy =
                new SimpleRetryPolicy(4, retryable, true, false);

        ExponentialBackOffPolicy backoff =
                new ExponentialBackOffPolicy();
        backoff.setInitialInterval(250L);
        backoff.setMultiplier(2.0);
        backoff.setMaxInterval(2_000L);

        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(retryPolicy);
        template.setBackOffPolicy(backoff);
        return template;
    }
}
~~~

### Giới hạn của ví dụ

- ResourceAccessException có thể đại diện nhiều lỗi I/O. Retryable về mặt kỹ thuật **không chứng minh** POST tạo order an toàn khi gửi lại.
- HTTP client có thể sử dụng exception khác; wrapper/cause chain cần được kiểm tra.
- Ví dụ chưa có jitter, retry budget tổng, connect/read timeout, Retry-After parsing, circuit breaker hoặc idempotency key.
- Không giả định danh sách status retryable ở trên là tiêu chuẩn cho mọi đối tác.
- Một exception phân loại sai có thể biến lỗi vĩnh viễn thành nhiều lời gọi vô ích; hãy thử từng status và operation.

### Khi cần randomization

Có thể thay ExponentialBackOffPolicy bằng **ExponentialRandomBackOffPolicy** theo version hỗ trợ, giữ initialInterval, multiplier và maxInterval phù hợp. Đo actual backoff, vì dãy delay sẽ không có giá trị xác định chính xác như ví dụ không jitter.

## 9. Tạo RequestHandlerRetryAdvice bean

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class IntegrationRetryAdviceConfig {

    @Bean
    public RequestHandlerRetryAdvice partnerRetryAdvice(
            RetryTemplate partnerRetryTemplate) {
        RequestHandlerRetryAdvice advice =
                new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(partnerRetryTemplate);

        // Không chỉ định RecoveryCallback trong ví dụ cơ bản;
        // hết retries, lỗi được propagate theo đường endpoint/caller.
        return advice;
    }
}
~~~

Để một retry advice có ý nghĩa, nó phải được **gắn vào endpoint**. Chỉ tạo bean mà không dùng trong endpoint không làm flow tự retry.

### Khi chọn RecoveryCallback

Mặc định lỗi có thể propagate theo xử lý của endpoint; muốn custom recovery sau exhausted có thể đặt RecoveryCallback. Nhưng phải hiểu **kết quả callback được tầng trên diễn giải thế nào**. Nếu callback trả bình thường, source/container có thể đánh dấu message đã xử lý. Không dùng recovery chỉ để ghi log rồi nuốt lỗi khi chưa có lưu trữ bền.

## 10. Gắn advice vào IntegrationFlow Java DSL

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.integration.http.dsl.Http;

@Configuration
public class PartnerStatusFlow {

    @Bean
    IntegrationFlow partnerStatusFlow(
            RequestHandlerRetryAdvice partnerRetryAdvice) {
        return IntegrationFlow.from("partnerStatusRequests")
            .handle(
                Http.outboundGateway(
                        "https://partner.example.invalid/api/status")
                    .httpMethod(HttpMethod.GET)
                    .expectedResponseType(String.class),
                endpoint -> endpoint.advice(partnerRetryAdvice)
            )
            .channel("partnerStatusResponses")
            .get();
    }
}
~~~

Trong flow:

1. Input channel nhận message.
2. HTTP outbound gateway gọi partner.
3. Advice bọc **HTTP message handler** của endpoint này.
4. Khi handler lỗi retryable, RetryTemplate chờ/backoff rồi gọi lại handler.
5. Nếu thành công, response đi tới channel tiếp.
6. Nếu exhausted và exception được propagate, caller hoặc error handling xử lý theo cấu hình.

Tên miền **example.invalid** là placeholder. Ví dụ dùng GET để tập trung vào wiring; khi dùng POST tạo side effect cần thêm idempotency, outcome reconciliation, deadline và auth.

### Vì sao không gắn một advice chung cho toàn flow?

Vì một handler bị lỗi sau khi bước trước thành công không cho phép tự động lặp lại bước trước. Mỗi điểm kết nối ngoài thường có **retry policy và recovery strategy riêng**.

## 11. Handler nào nên gắn retry advice?

| Handler | Có thể retry? | Điều kiện |
|---|---|---|
| HTTP outbound GET | Thường phù hợp với transient network error | Timeout, maxAttempts và rate limit |
| HTTP outbound POST | Chỉ nếu replay-safe | Idempotency key hoặc query/reconcile |
| SFTP outbound upload | Có thể với lỗi transient | Temp file, checksum và remote state |
| File outbound write | Có thể khi I/O tạm lỗi | Stable name và publish atomic khi hỗ trợ |
| JDBC outbound update | Tùy transaction | Rollback đúng scope, unique constraint |
| Service activator gọi remote | Có thể | Handler đủ nhỏ, một operation rõ |
| JMS/AMQP outbound send | Cần hiểu publish outcome | Confirm, dedupe và broker retry |
| Kafka outbound send | Cần hiểu producer semantics | Broker ack, client retry và idempotency |
| Validator thuần dữ liệu | Không retry input invalid | Quarantine |
| Email/webhook sender | Rất cẩn trọng | Có thể đã gửi trước timeout |
| Handler phối hợp nhiều side effects | Không bọc mù | State machine và retry từng bước |

**Một policy giống nhau cho mọi handler là anti-pattern**: parser invalid và HTTP 503 không nên được xử lý như nhau.

## 12. Advice chain và transaction boundary

Một endpoint có thể được gắn nhiều advice, như retry, transaction và metrics/tracing. Thứ tự bao quanh handler có thể làm khác số transaction được mở.

~~~text
A. Retry là lớp ngoài:
   attempt 1 -> BEGIN tx1 -> handler -> ROLLBACK
   backoff
   attempt 2 -> BEGIN tx2 -> handler -> COMMIT

B. Transaction là lớp ngoài:
   BEGIN tx1
     attempt 1 -> handler -> exception, có thể rollback-only
     attempt 2 -> handler -> vẫn trong tx1
   COMMIT có thể lỗi
~~~

Trong nhiều trường hợp deadlock, muốn retry **transaction mới**, không phải lặp SQL bên trong transaction đã rollback-only. Nhưng transaction mới không làm một HTTP POST trước đó tự rollback: side effect giữa các hệ thống cần cơ chế riêng.

### Những câu hỏi phải trả lời

1. Retry đang bao ngoài hay bên trong transaction?
2. Khi attempt lỗi, transaction đã bị đánh dấu rollback-only chưa?
3. Một lời gọi ngoài DB đã thành công trước lỗi chưa?
4. Handler có gửi AMQP/Kafka trước commit DB không?
5. Source ack/commit phụ thuộc vào việc exception được propagate không?
6. Có outbox/inbox để chống mất/nhân message khi crash không?
7. Có integration test với deadlock/rollback thực và advice chain thật không?

**Không có thứ tự advice universal**. Chỉ thay đổi thứ tự mà không kiểm thử có thể làm khác semantics transaction và lần gửi.

## 13. So sánh RequestHandlerRetryAdvice và @Retryable

Cả hai có thể dùng ý tưởng Spring Retry nhưng ranh giới khác nhau.

| Tiêu chí | RequestHandlerRetryAdvice | @Retryable cho method |
|---|---|---|
| Đơn vị | Invocation của message-handling endpoint | Invocation của method qua proxy phù hợp |
| Gắn ở đâu | Endpoint advice chain / Integration DSL | Service method/AOP configuration |
| Mục tiêu | Điều chỉnh handler trong message flow | Retry service method ở nhiều ngữ cảnh |
| Lỗi cần chú ý | Channel/source ack, retry cả handler | Proxy/self-invocation và method scope |
| Khả năng dùng cùng nhau | Có thể, nhưng dễ nhân attempts | Có thể, nhưng cần ngân sách tổng |
| Recovery | Callback/error flow theo cấu hình | Recovery theo method-level retry |

Nếu endpoint retry tối đa 4 attempts và method bên trong cũng retry 3 attempts thì có thể xảy ra **12 method invocations** cho một message, chưa tính HTTP client/broker redelivery.

Chỉ chọn hai lớp cùng lúc khi có **lý do rõ, deadline tổng, idempotency và metric phân biệt từng tầng**.

## 14. MessageChannel và cách exception truyền đi

### DirectChannel

**DirectChannel** thường dispatch đồng bộ trong thread gửi. Nếu handler lỗi và exception propagate, caller có thể nhận lỗi cùng call stack. RetryAdvice giữ thread qua các attempts và backoff.

~~~text
HTTP inbound gateway
  -> DirectChannel
  -> HTTP outbound handler + RetryAdvice (nhiều attempts)
  -> response / error
~~~

Nếu tổng thời gian thử lại vượt timeout của HTTP caller, caller có thể gửi lại request. Vì vậy cần budget end-to-end.

### ExecutorChannel

**ExecutorChannel** chuyển xử lý sang executor, tạo ranh giới bất đồng bộ. Exception không nhất thiết quay về thread sender như DirectChannel; error channel và task/rejection handling cần được thiết kế.

ExecutorChannel **không tự là durable queue**. Process restart có thể khiến message in-memory chưa xử lý biến mất nếu không có cơ chế nguồn redelivery hoặc lưu bền.

### QueueChannel

QueueChannel có cơ chế giữ message theo cách được cấu hình; durability tùy MessageStore/transaction và cách poller lấy/ack message. Không mặc định mọi QueueChannel bảo đảm at-least-once qua crash.

### Bảng câu hỏi cho topology

| Câu hỏi | Vì sao quan trọng |
|---|---|
| Thread nào đang chờ backoff? | Đo nghẽn và timeout |
| Caller đang đợi reply không? | Deadline và retry từ caller |
| Nếu handler exhausted, exception đi đâu? | Error channel/container |
| Source đã ack hoặc commit chưa? | Tránh silent message loss |
| Có message store/durable queue chưa? | Khôi phục qua restart |
| Ai giữ business event ID? | Idempotent redelivery |

## 15. Poller schedule khác handler retry

Poller kiểm tra nguồn theo trigger như fixedDelay/fixedRate/cron. **RequestHandlerRetryAdvice** không biến poller thành retry scheduler bền vững.

~~~text
SFTP poller:
  kiểm tra remote directory mỗi 5 giây.

HTTP handler:
  attempt 1 -> lỗi
  đợi 250 ms
  attempt 2 -> lỗi
  đợi 500 ms
  attempt 3 -> thành công
~~~

Các sự kiện này khác nhau về **đơn vị công việc và thời gian**.

- Khi poller không thấy message, thường đó là trạng thái bình thường, không phải exception cần retry.
- Nếu file đã được accept-once filter ghi nhận, lần poll sau **không chắc** đọc lại file ấy.
- Handler retry downstream không tự tái tạo message upstream.
- Với nguồn đang down lâu, có thể cần điều chỉnh polling schedule/tạm dừng adapter và đưa message lỗi vào durable retry.
- Backoff dài có thể giữ poller thread, làm giảm throughput.
- Retry advice ở handler khác với advice của polling endpoint; cần kiểm tra topology thực.

## 16. RecoveryCallback: hết attempts không được làm mất message

Đây là rủi ro quan trọng của RequestHandlerRetryAdvice.

### Đường thứ nhất: propagate lỗi

Nếu không custom recovery hoặc recovery ném lỗi, caller/container nhìn thấy terminal exception và có thể xử lý theo hợp đồng nguồn: HTTP error, JMS rollback, AMQP nack, Kafka error handler hoặc error channel.

### Đường thứ hai: recovery trả về bình thường

Nếu callback gửi log rồi return null, tầng trên có thể xem handler đã kết thúc, dẫn đến ack/commit **dù nghiệp vụ chưa được xử lý và message chưa được lưu lại**.

~~~java
// Anti-pattern: cẩn trọng với việc nuốt exception.
advice.setRecoveryCallback(context -> {
    logger.error("Partner unavailable", context.getLastThrowable());
    return null; // Container có thể xem message đã xử lý.
});
~~~

### Một ví dụ propagate terminal failure

~~~java
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

RequestHandlerRetryAdvice advice =
        new RequestHandlerRetryAdvice();
advice.setRetryTemplate(retryTemplate);

advice.setRecoveryCallback(context -> {
    throw new IllegalStateException(
            "Partner handler exhausted retry policy",
            context.getLastThrowable());
});
~~~

Đây là đoạn cấu hình minh họa, không phải một file Java độc lập hoàn chỉnh. Khi chọn **durable parking/DLQ** thay vì rethrow, phải xác nhận ghi thành công và thiết kế nguồn ack/commit tương ứng.

### ErrorMessage và error channel

Spring Integration có ErrorMessage và các cơ chế recovery gửi lỗi tới error channel, chẳng hạn sử dụng **ErrorMessageSendingRecoverer** theo cấu hình phù hợp. Nhưng **error channel không tự là durable storage**:

- Channel in-memory có thể mất message khi restart.
- Chưa có subscriber hoặc error flow lỗi có thể khiến recovery không đạt yêu cầu.
- Phải bảo vệ payload/headers chứa secret.
- Cần lưu business event ID, exception category, attempt count và trạng thái recovery.
- Nếu recoverer trả về bình thường, phải xác định nguồn có được ack không và message đã thực sự được bảo toàn chưa.

## 17. Hợp đồng terminal recovery

Bảng trạng thái giúp vận hành sau khi retry exhausted:

| Trạng thái | Ý nghĩa | Bằng chứng cần có |
|---|---|---|
| SUCCESS | Handler tạo kết quả hợp lệ | Kết quả, side effect đã xác nhận |
| RETRY_EXHAUSTED | Hết budget in-process | Last exception và bước tiếp |
| PARKED | Message được lưu để điều tra | Storage bền, owner, retention, event ID |
| DELAYED_RETRY | Message chờ thử lại theo lịch | NextAttemptAt, attempt count, deadline |
| DEAD_LETTERED | Message chuyển DLQ/DLT | Xác nhận lưu và replay policy |
| OUTCOME_UNKNOWN | Không rõ remote đã commit chưa | Query/reconciliation |
| INVALID | Payload không hợp lệ | Reason code, quarantine |
| CANCELLED | Nghiệp vụ hết hiệu lực | Lý do và audit |

Ví dụ schema lỗi:

~~~json
{
  "eventId": "order-312-v2",
  "correlationId": "corr-e92c",
  "flowId": "sftp-to-erp",
  "endpointId": "erpOutboundGateway",
  "operation": "order.upsert",
  "attemptsCurrentInvocation": 4,
  "errorCategory": "REMOTE_UNAVAILABLE",
  "lastErrorType": "ServiceUnavailable",
  "outcome": "PARKED",
  "payloadReference": "secure-message-store/order-312",
  "nextReviewAt": "2026-11-23T12:00:00Z"
}
~~~

Đây là schema nghiệp vụ minh họa, không phải format mặc định của framework. **Không ghi token, private key, mật khẩu hoặc toàn bộ dữ liệu khách hàng trong log lỗi.**


## 18. Idempotency: retry an toàn cần khóa nghiệp vụ ổn định

**Idempotent** nghĩa là thực hiện lại cùng một thao tác với cùng ngữ nghĩa không gây thêm hiệu ứng nghiệp vụ ngoài dự kiến. Điều này quan trọng với HTTP POST, ghi database, upload file, gửi email hoặc publish event.

### Stable business event ID

Không dùng MessageHeaders.ID có thể được tạo mới sau transform/redelivery làm khóa nghiệp vụ. Nên dùng ID ổn định do nguồn hoặc nghiệp vụ xác định.

~~~text
businessEventId = partner-X:order-312:v2
operation = ERP.order.upsert

Attempt 1:
    Idempotency-Key = partner-X:order-312:v2
    ERP đã commit nhưng response bị mất.

Attempt 2:
    Idempotency-Key = partner-X:order-312:v2
    ERP trả kết quả trước, không tạo order thứ hai.
~~~

Ví dụ chỉ đúng nếu **ERP thực sự hỗ trợ idempotency key**, có quy tắc TTL, phạm vi và xử lý payload khác nhau với cùng key. Nếu không có, cần tra cứu trạng thái theo orderId hoặc chuyển sang **OUTCOME_UNKNOWN** để đối soát.

### Inbox/dedupe

Bảng kiểm soát sự kiện được xử lý có thể dùng unique constraint:

~~~sql
-- Minh họa khóa nghiệp vụ của consumer.
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    business_event_id VARCHAR(160) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, business_event_id)
);
~~~

Khi việc đánh dấu đã xử lý và cập nhật dữ liệu nghiệp vụ nằm **trong một DB transaction**, có thể giảm duplicate side effect tại DB đó. Nhưng nếu handler gọi HTTP remote trước rồi local DB mới ghi processed_events, crash giữa hai bước vẫn làm remote có thể đã xử lý mà local không biết.

### Transactional outbox

Một flow cập nhật DB và gửi AMQP/Kafka có thể:

1. Ghi dữ liệu nghiệp vụ;
2. Ghi một outbox event vào **cùng DB transaction**;
3. Commit;
4. Outbox publisher thử gửi broker, có thể gửi lại sau lỗi;
5. Consumer đích dedupe theo stable event ID.

Outbox bảo toàn **ý định gửi**, không tự đảm bảo publish exactly-once trên mọi hệ thống. Consumer vẫn phải idempotent.

### Vì sao không retry một callback dài?

~~~text
RetryCallback:
    createERPOrder();       // đã thành công
    updateLocalDatabase();  // đã thành công
    sendNotification();     // lỗi

Retry lại callback:
    createERPOrder();       // có thể tạo trùng
    updateLocalDatabase();
    sendNotification();
~~~

Nên chia thành các trạng thái ERP_PENDING, ERP_CONFIRMED, DB_UPDATED, NOTIFICATION_PENDING, DONE với OUTCOME_UNKNOWN và PARKED để mỗi bước có phạm vi retry riêng.

## 19. Transaction, acknowledgement và redelivery

Trong một integration flow, cần phân biệt:

1. **Handler attempt:** một lần chạy code handler;
2. **Transaction:** các cập nhật nào cùng commit/rollback;
3. **Source acknowledgement/checkpoint:** khi nào nguồn tin rằng message đã xử lý.

RetryAdvice không tự đồng nhất ba ranh giới trên.

| Nguồn | Khi thành công | Khi exhausted | Câu hỏi cần xác minh |
|---|---|---|---|
| HTTP inbound gateway | Response theo request–reply | Trả lỗi phù hợp | Client có gửi lại request không? |
| File inbound | File được xử lý/đánh dấu theo flow | Không có broker ack mặc định | Accept-once, metadata, archive? |
| SFTP inbound | Download/filter theo config | Không tự download lại | Transfer/remote state bền? |
| JMS listener | Ack/commit theo container | Rollback/redelivery/DLQ | Recovery có nuốt exception? |
| AMQP listener | Ack/commit theo mode | Nack/reject/requeue/DLX | Có hot loop không? |
| Kafka | Offset/ack theo container | Seek/retry topic/DLT | Partition ordering và side effects? |
| JDBC poller | Claim/update theo transaction | Row cần retry/lease | Có thể nhận lại row an toàn? |

**Không suy từ việc handler ném exception rằng mọi nguồn đều tự redeliver.** Phải kiểm tra cấu hình cụ thể và thực hiện test khi lỗi/restart.

### Transaction DB và retry

Deadlock hoặc serialization conflict có thể làm transaction rollback-only. Retry thêm statement trong transaction ấy có thể không commit; cần **rollback và mở transaction mới** theo ranh giới phù hợp. Nhưng một side effect HTTP ngoài DB không được tự rollback, nên không đưa nó vào callback lớn chỉ để retry transaction.

### Nguồn ack và durable recovery

Khi chuyển message vào parking/DLQ rồi cho source ack, cần:

1. Ghi bản lưu có stable eventId, payload reference và metadata đủ redrive;
2. Xác nhận ghi bền thành công;
3. Ack nguồn theo hợp đồng;
4. Có idempotency nếu crash sau ghi parking nhưng trước ack nguồn.

**Ghi vào broker khác rồi ack nguồn không tự atomic** nếu không có transaction/hợp đồng bảo đảm tương ứng.

## 20. HTTP outbound gateway: trường hợp áp dụng điển hình

HTTP gateway xử lý request–reply và phù hợp với advice ở message handler, miễn là thao tác có thể retry an toàn.

| Lỗi | Cách xử lý tham chiếu | Bảo vệ bổ sung |
|---|---|---|
| 429 | Retry có delay khi phù hợp | Retry-After/rate limit/deadline |
| 503 | Exponential backoff và jitter | Tránh khuếch đại quá tải |
| 502/504 | Tùy operation | Outcome có thể không rõ |
| Connect timeout | Có thể retry | Kiểm tra tầng mạng/client |
| Read timeout sau POST | Không gửi lại mù | Idempotency/reconciliation |
| 400 / invalid schema | Không retry | Sửa dữ liệu |
| 401/403 | Không retry cùng credential | Sửa authentication/permission |
| 404/409 | Theo hợp đồng nghiệp vụ | Không tự coi transient |
| 500 | Không tự mặc định retry mọi POST | Server có thể commit trước lỗi |

### Retry-After và deadline

Nếu partner trả 429 với Retry-After 30 giây, còn HTTP inbound caller chỉ đợi 4 giây, không nên giữ request đồng bộ thêm 30 giây. Có thể trả lỗi cho caller hoặc lưu message vào delayed retry bền vững theo contract.

**ExponentialBackOffPolicy không tự đọc header Retry-After.** Muốn theo chỉ thị của server cần logic response-specific và giới hạn tổng deadline.

### POST timeout sau commit

~~~mermaid
sequenceDiagram
    participant C as HTTP Handler
    participant P as Partner ERP
    participant D as ERP Database
    C->>P: POST order eventId=order-312-v2
    P->>D: Commit order
    D-->>P: Success
    Note over C,P: Response bị mất, read timeout
    C->>C: RetryAdvice đánh giá lỗi
    C->>P: POST cùng idempotency key nếu hỗ trợ
    P-->>C: Trả kết quả trước
~~~

Sơ đồ giả định partner thực sự hỗ trợ idempotency. Nếu không có, chuyển message thành OUTCOME_UNKNOWN để query/đối soát trước khi gửi lại.

## 21. File inbound/outbound: retry handler không phải retry poller

### Inbound File

- File có thể đang ghi dở: dùng temporary name/ready marker hoặc manifest.
- File invalid JSON/CSV: quarantine, không retry cùng payload vô hạn.
- Nếu downstream handler HTTP lỗi, advice ở HTTP **không tự làm file được poll lại**.
- Accept-once filter có thể đã ghi trạng thái file trước downstream failure.
- Metadata in-memory có thể thay đổi hành vi sau restart; cần stable business event ID và persistence.
- Archive/delete file chỉ theo trạng thái xử lý được phê duyệt, không quá sớm.

### Outbound File

Nếu ghi file lỗi nửa chừng, retry cùng tên có thể tạo file partial/ghi đè. Có thể ghi ra temporary output rồi publish bằng rename khi filesystem hỗ trợ semantics phù hợp. Tên file gắn event ID giúp đối soát.

**Backoff có thể giúp I/O transient, nhưng không biến file write thành atomic transaction**, và không sửa được nội dung file không hợp lệ.

## 22. SFTP: session, transfer dở và remote state

Spring Integration SFTP adapters có thể mở session, list/download/upload, rename/move/delete. Không phải mọi lỗi đều nên retry giống nhau.

| Hoạt động | Lỗi tạm thời | Rủi ro |
|---|---|---|
| Mở session | Connect timeout/reset | Credential và host key sai là lỗi khác |
| List remote | Server busy | Poller tăng tải hoặc lặp file |
| Download | Mất kết nối giữa transfer | Local partial file |
| Upload | Timeout khi đã gửi gần xong | Remote partial/duplicate |
| Rename | Response mất | Lệnh có thể đã thực hiện |
| Delete/move | Timeout | File có thể đã được chuyển/xóa |

### Upload có thể khôi phục

~~~text
eventId=invoice-882-v3
    -> temp filename theo eventId
    -> upload
    -> kiểm tra size/hash/manifest nếu phù hợp
    -> publish thành final filename
    -> mark CONFIRMED
~~~

Nếu mất response ở bước rename, cần xem **remote file đã ở trạng thái nào** trước khi retry. Không bỏ SSH host-key verification để giúp reconnect; sai khóa/credential đòi hỏi sửa trust/config.

### Giới hạn của advice

RequestHandlerRetryAdvice ở một downstream handler **không tự bọc toàn bộ hoạt động SFTP inbound source**. Nếu lỗi trước khi source tạo message, phải xử lý tại **SFTP session/adapter/poller**. Nếu file đã tải nhưng handler sau lỗi, cần lưu message và replay riêng.

## 23. JMS: in-process attempts nhân với broker deliveries

~~~text
JMS delivery 1:
    handler attempt 1 -> timeout
    handler attempt 2 -> timeout
    handler attempt 3 -> exhausted
    exception propagate

Container:
    nếu có transaction/rollback phù hợp:
        message có thể được redeliver

JMS delivery 2:
    handler có thể tiếp tục 3 attempts mới
~~~

Nếu một delivery có 3 handler attempts và broker tổng 5 deliveries, handler có thể chạy **15 lần**. Lời gọi HTTP/DB bên trong cần idempotency.

Cần xác định:

- Session transacted hay không và acknowledgement mode;
- Container sẽ làm gì khi handler ném exception;
- RecoveryCallback có return bình thường khiến ack không;
- Broker giới hạn redelivery và chuyển DLQ thế nào;
- Có poison message block consumer hay không;
- Message ID của broker khác business event ID ra sao.

**Handler retry và JMS broker redelivery là hai vòng lặp khác nhau**, cần giới hạn tổng số lần xử lý.

## 24. AMQP/RabbitMQ: nack/requeue và publisher confirm

### Inbound

- Handler retry ngắn với RequestHandlerRetryAdvice.
- Khi exhausted, container quyết định ack/nack/reject/requeue dựa trên cấu hình và exception.
- **Requeue ngay vô hạn** có thể tạo hot loop.
- TTL/DLX, delayed queue hoặc cơ chế retry thích hợp giúp dãn lỗi kéo dài.
- Prefetch/concurrency quyết định bao nhiêu messages đang giữ worker slot.
- Nếu RecoveryCallback return success trước khi message được lưu bền, nguồn có thể ack nhầm.

### Outbound

Publish có thể đã tới broker nhưng confirm không về, tạo **unknown outcome**. Retry publish có thể tạo message trùng. Publisher confirms không chứng minh consumer đã xử lý nghiệp vụ.

Giải pháp: outbox khi xuất phát từ DB transaction, stable event ID và consumer dedupe; xử lý timeout/confirm theo contract.

**Không giả định ghi DLQ trên broker khác và ack nguồn là một transaction nguyên tử**.

## 25. Kafka: advice không thay container error handler

Spring Integration Kafka adapters kết hợp với Spring for Apache Kafka. RequestHandlerRetryAdvice **chỉ retry handler invocation**, không tự seek, commit offset, tạo retry topics hoặc DLT.

| Tầng | Trách nhiệm |
|---|---|
| Kafka consumer/client | Poll records, heartbeat, group, offset |
| Listener container/error handler | Retry/seek/backoff/recovery/DLT theo cấu hình |
| Spring Integration inbound adapter/channel | Đưa record vào message flow |
| RequestHandlerRetryAdvice | Retry handler được bọc |
| Business handler | DB/HTTP side effect và idempotency |
| Kafka producer/outbound | Gửi/ack record theo producer policy |

### Thứ tự trong partition

~~~text
offset 100: order-created
offset 101: order-updated
offset 102: order-cancelled
~~~

Nếu offset 100 lỗi:

- Retry tại chỗ có thể giữ thứ tự nhưng block partition.
- Chuyển retry topic có thể cho offset 101 chạy trước 100 nếu không có ordering guard.
- Commit offset sớm gây nguy cơ mất tác vụ.
- Không commit và replay gây duplicate nếu DB/HTTP đã thành công.

Đặc tính exactly-once trong một phạm vi Kafka không tự bảo đảm exactly-once trên HTTP partner và database ngoài phạm vi transaction đó.

## 26. JDBC: retry ở transaction boundary đúng

Các lỗi có thể xảy ra:

- Connection pool hết connection tạm thời;
- DB failover;
- Deadlock/serialization conflict;
- Lock timeout;
- Unique constraint violation;
- SQL schema/syntax error;
- Timeout sau commit với outcome không rõ.

**Deadlock** thường có thể retry sau rollback, nhưng cần transaction mới nếu trước đó rollback-only.

~~~text
Retry outer:
    attempt 1 -> BEGIN tx1 -> UPDATE -> deadlock -> ROLLBACK
    backoff
    attempt 2 -> BEGIN tx2 -> UPDATE -> COMMIT
~~~

Không đưa HTTP POST và DB update vào cùng callback mù, vì retry do DB deadlock có thể gửi lại HTTP đã thành công.

### JDBC inbound polling

~~~text
NEW -> CLAIMED -> PROCESSING -> DONE
                  |
                  +-> RETRY_WAIT -> PROCESSING
                  |
                  +-> PARKED
~~~

Row cần stable ID, attempt_count, next_attempt_at, lease_owner, lease_until và atomic claim phù hợp. RetryContext in-memory không tự khôi phục một row khi worker chết giữa PROCESSING.

## 27. Retry lồng nhau và hệ số nhân số lần gọi

Ví dụ:

~~~text
Client HTTP: 3 attempts
  -> API Gateway: 4 attempts
      -> Handler advice: 4 attempts
          -> HTTP client: 2 attempts
~~~

Partner có thể nhận tối đa **3 × 4 × 4 × 2 = 96 calls** cho một business event trong tình huống xấu nhất, nếu mọi tầng thử hết budget và không có giới hạn khác.

### Cách phối hợp

1. Chỉ định owner retry ở từng ranh giới.
2. Công bố maxAttempts tính cả lần đầu.
3. Đặt per-attempt timeout và total deadline.
4. Giảm retries ở tầng khác nếu không có lý do.
5. Dùng idempotency key chung.
6. Dùng backoff/jitter, rate limiter và circuit breaker.
7. Giới hạn concurrency bằng bulkhead.
8. Đo attempts của handler, broker deliveries, durable redrives riêng.
9. Nếu sự cố kéo dài, chuyển durable delayed retry.

| Cơ chế | Giải quyết | Không thay thế |
|---|---|---|
| Retry | Lỗi transient | Idempotency |
| Backoff/jitter | Dãn tải | Exception classification |
| Circuit breaker | Không tiếp tục gọi dependency đang lỗi | Message persistence |
| Rate limiter | Quota và burst | Business correctness |
| Bulkhead | Cô lập worker/thread | Outcome reconciliation |
| Delayed retry | Chờ lâu qua storage | Transaction/ack |
| DLQ/parking | Giữ message lỗi | Tự sửa invalid payload |
| Inbox/outbox | Bảo toàn ý định gửi/dedupe | Exactly-once xuyên mọi hệ thống |


## 28. Khi nào chuyển từ handler retry sang durable delayed retry?

RetryAdvice với BackOffPolicy thông thường vận hành **trong một chuỗi call in-process**. Khi process restart, RetryContext của chuỗi đang chạy không tự được lưu lại; trách nhiệm khôi phục thuộc nguồn và storage của hệ thống.

### Short in-process retry phù hợp khi

- Lỗi transient thường hết sau vài trăm mili giây hoặc vài giây.
- Có ít attempts, timeout rõ và tổng deadline đủ.
- Worker pool có capacity.
- Operation idempotent/replay-safe.
- Caller đang chờ response và deadline chưa hết.
- Không có broker retry khác nhân attempts vô ý.

### Durable delayed retry phù hợp khi

- Partner có thể down phút hoặc giờ.
- Hàng nghìn messages đang đợi, không nên giữ mọi consumer threads.
- Cần survive restart/redeploy.
- Retry-After dài hơn deadline của synchronous caller.
- Cần inspect, pause, schedule, redrive, retention và owner.
- Message có business expiry, trạng thái OUTCOME_UNKNOWN hoặc cần manual review.

| Tiêu chí | RequestHandlerRetryAdvice | Durable delayed retry |
|---|---|---|
| Đơn vị | Handler invocation | Message/job/event lưu bền |
| State | RetryContext trong process | DB/queue/topic/message store |
| Khoảng thời gian | Thường ngắn | Có thể dài |
| Worker thread | Có thể chờ trong backoff | Không cần giữ call stack |
| Restart | Không tự khôi phục state | Có khi lưu/ack đúng |
| Attempt count | Theo invocation hiện tại | Persist qua nhiều executions |
| Terminal outcome | Exception/recovery callback | PARKED/DLQ/CANCELLED rõ |
| Ordering | Phụ thuộc handler/container | Phải thiết kế riêng |
| Idempotency | Cần | Vẫn cần |

**Mô hình kết hợp:** retry ngắn 2–4 attempts có giới hạn tại handler; nếu lỗi transient kéo dài, ghi message bền vào delayed retry với nextAttemptAt; một worker khác xử lý sau. Nếu lỗi permanent, chuyển quarantine thay vì redrive không điều kiện.

### Ví dụ record durable retry

~~~json
{
  "eventId": "invoice-882-v3",
  "target": "erp-http",
  "operation": "invoice.upsert",
  "state": "RETRY_WAIT",
  "attemptCountPersisted": 6,
  "nextAttemptAt": "2026-11-23T10:30:00Z",
  "deadlineAt": "2026-11-24T00:00:00Z",
  "lastErrorCategory": "SERVICE_UNAVAILABLE",
  "payloadRef": "secure-store/invoice-882",
  "idempotencyKeyRef": "invoice-882-v3"
}
~~~

Đây là schema minh họa. Không lưu bearer token, khóa SSH hoặc nội dung nhạy cảm nguyên văn vào record retry.

## 29. Logging, tracing và metrics

Chỉ log “retrying...” từng lần không đủ để giải thích tổng số calls hoặc xác nhận nghiệp vụ không bị nhân đôi.

### Hợp đồng log

| Trường | Mục đích |
|---|---|
| businessEventId | Theo dõi cùng nghiệp vụ qua retry, redelivery, replay |
| correlationId/traceId | Nối inbound, handler, outbound, recovery |
| flowId/endpointId | Xác định handler được gắn advice |
| source/targetAlias | Nhóm hệ thống, không ghi secret host |
| attemptIndex/maxAttempts | Số lần handler chạy |
| exceptionType/errorCategory | Transient/permanent/unknown outcome |
| backoffRequestedMs/elapsedMs | Kiểm soát latency |
| retryPolicyVersion | Biết policy nào đang có hiệu lực |
| recoveryOutcome | SUCCESS, EXHAUSTED, PARKED, DEAD_LETTERED, CANCELLED |
| sourceAckOrCommitOutcome | Message/offset đã xác nhận chưa |
| idempotencyKeyRef | Liên kết các attempts cùng event |

**Không log** password, private key SFTP, bearer token, session cookie hoặc toàn bộ payload khách hàng. Các header của message có thể chứa dữ liệu nhạy cảm; không serialize tất cả headers vào log lỗi.

### Các metrics cần tách riêng

| Metric | Ý nghĩa |
|---|---|
| handler_attempts_total | Tổng handler invocations theo endpoint và error category |
| retry_success_after_failure_total | Chuỗi handler retry thành công sau ít nhất một lỗi |
| retry_exhausted_total | Chuỗi retry hết ngân sách |
| retry_backoff_seconds | Phân phối khoảng nghỉ của policy |
| handler_latency_seconds | Tổng thời gian handler gồm attempts/backoff |
| first_attempt_success_rate | Tỷ lệ thành công không cần retry |
| broker_redelivery_total | Số lần nguồn/broker giao lại message |
| durable_redrive_total | Số lần replay từ DLQ/parking/job store |
| parked_backlog_age_seconds | Tuổi message đang chờ xử lý |
| duplicate_business_effect_total | Số side effects trùng đã xác minh |
| dedupe_hits_total | Số event trùng được ngăn theo business key |
| pool_blocked_threads | Threads bị giữ do timeout/backoff |
| partner_error_rate | 429/503/timeout theo dependency |

**Không dùng businessEventId, orderId hoặc traceId làm metric label** vì high-cardinality. ID phù hợp log/tracing; metric label nên dùng endpoint, target alias, errorCategory và finalOutcome thuộc tập có giới hạn.

Nếu first-attempt success giảm mạnh nhưng cuối cùng retry success vẫn cao, hệ thống có thể đang **che giấu lỗi phụ thuộc**. Đọc metric cùng latency, queue depth và duplicate effects.

### RetryListener và tracing

Có thể dùng RetryListener/instrumentation để ghi open/onError/close của RetryTemplate. Cần kiểm tra version API, thread safety và bảo mật payload. Một trace cho business event có thể chứa nhiều spans cho attempts; business counter vẫn chỉ đếm **một sự kiện nghiệp vụ**, không tính mỗi attempt thành một đơn hàng mới.

## 30. Kiểm thử RequestHandlerRetryAdvice

Kiểm thử đúng nghĩa không chỉ assert mock được gọi N lần; cần chứng minh **kết quả, phạm vi và side effect**.

### 30.1. Unit test RetryTemplate

~~~java
import java.io.IOException;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.retry.backoff.NoBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

// Ví dụ đặt trong test method; Java cần hỗ trợ Map.of.
RetryTemplate template = new RetryTemplate();
template.setRetryPolicy(new SimpleRetryPolicy(
        3, Map.of(IOException.class, true), true, false));
template.setBackOffPolicy(new NoBackOffPolicy());

AtomicInteger calls = new AtomicInteger();
String result = template.execute(ctx -> {
    if (calls.incrementAndGet() < 3) {
        throw new IOException("Temporary connection failure");
    }
    return "OK";
});

// Mong đợi: result = "OK", calls = 3.
~~~

NoBackOffPolicy chỉ để unit test nhanh; **không phải cấu hình nên dùng cho network failure production**. Khi cần test khoảng nghỉ exponential, dùng Sleeper/test double hoặc cơ chế đo của version Spring Retry phù hợp, tránh assert thời gian wall-clock quá chặt gây flaky tests.

### 30.2. Test endpoint advice thực

~~~text
testInputChannel
    -> upstreamTransformer
    -> handlerWithRetryAdvice (fake lỗi 2 lần)
    -> successChannel
~~~

Xác minh:

1. Một message eventId ổn định được gửi.
2. Handler được gọi **3 lần**.
3. Upstream transformer chỉ chạy **1 lần** trong topology đang kiểm thử.
4. Downstream nhận **1 kết quả**.
5. Correlation ID được bảo toàn đúng.
6. Error flow không có terminal failure do attempt cuối thành công.

### 30.3. Test exhausted

Cho handler luôn lỗi retryable:

- Với maxAttempts=4 phải có **đúng bốn invocations**.
- Nếu recovery rethrow, caller/container nhìn thấy terminal exception.
- Nếu recovery parking, bản ghi phải thực sự bền trước khi ack nguồn.
- Nếu lưu parking lỗi, không coi message đã xử lý thành công.
- Nếu sau đó broker redeliver, idempotency phải vẫn đúng.

### 30.4. Test wrapped exceptions

Dùng MessageHandlingException chứa cause là IOException và một trường hợp chứa InvalidPayloadException. Xác minh classifier:

- Retry transient cause được duyệt.
- Không retry invalid payload.
- Không tự retry mọi MessagingException.

Tên wrapper/exception cụ thể tùy adapter/version; test phải dùng exception thật từ integration flow của dự án.

## 31. Ma trận kiểm thử end-to-end

| ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| A1 | Handler thành công attempt đầu | Một invocation, không backoff |
| A2 | Hai lỗi transient rồi thành công | Ba attempts, downstream một kết quả |
| A3 | Lỗi liên tục maxAttempts=4 | Bốn attempts, đúng recovery |
| A4 | Invalid payload | Không retry, quarantine |
| A5 | HTTP 401/403 | Không retry cùng credential |
| A6 | HTTP 429 + Retry-After | Rate/deadline được tôn trọng |
| A7 | HTTP 503 ở nhiều instance | Jitter/rate limit không tạo burst bất thường |
| A8 | POST đã commit nhưng response mất | Không tạo duplicate nhờ idempotency/reconciliation |
| A9 | RetryAdvice chỉ ở HTTP handler | Transformer upstream không chạy lại |
| A10 | JDBC phía sau lỗi sau ERP thành công | Không lặp HTTP POST |
| A11 | RecoveryCallback rethrow | Caller/container nhận terminal error |
| A12 | RecoveryCallback trả bình thường | Chỉ ack khi message được bảo toàn |
| A13 | Error channel in-memory không subscriber | Không đánh dấu DLQ bền thành công |
| A14 | Ghi DLQ thất bại | Không mất message nguồn |
| A15 | SFTP outbound upload đã xong nhưng timeout | Remote state được đối soát |
| A16 | SFTP inbound accept-once filter | Handler retry không bị nhầm thành re-download |
| A17 | File chưa publish hoàn chỉnh | Không parse partial file |
| A18 | JMS transacted listener lỗi | Rollback/redelivery theo contract |
| A19 | AMQP nack/requeue liên tục | Không hot loop; DLQ/delayed retry |
| A20 | Kafka record lỗi | Offset/retry topic/DLT đúng |
| A21 | Kafka retry topic ảnh hưởng ordering | Test phát hiện khi business đòi thứ tự |
| A22 | JDBC deadlock | Transaction mới và một commit |
| A23 | Transaction đã rollback-only | Không dùng lại transaction hỏng |
| A24 | ExecutorChannel downstream lỗi | Error flow xử lý đúng |
| A25 | DirectChannel với backoff dài | Không vượt caller deadline |
| A26 | Process restart giữa retry | Source/durable state phục hồi |
| A27 | Circuit breaker open | Không phát sinh remote calls trái policy |
| A28 | Nested retries ở nhiều tầng | Tổng calls đúng budget |
| A29 | Broker duplicate delivery | Dedupe ngăn business effect trùng |
| A30 | Error logs có token | Secret được redact |
| A31 | Business event đã hết deadline | Không tiếp tục redrive |
| A32 | Partner down nhiều giờ | Dùng delayed retry, không giữ mọi threads |
| A33 | Client timeout nhưng handler còn chạy | Cancellation/side-effect policy rõ |
| A34 | DLQ replay sau sửa dữ liệu | Replay có audit và idempotent |
| A35 | Thay đổi RetryPolicy sau rollout | Contract tests phát hiện lệch attempts/latency |
| A36 | Hai flow dùng chung advice | Policy/metrics phân biệt endpoint |

### Crash-point testing

Chủ động dừng ứng dụng giữa:

1. Nhận message nhưng chưa ghi inbox;
2. HTTP partner commit nhưng client chưa nhận response;
3. DB commit nhưng chưa publish AMQP;
4. DLQ đã ghi nhưng nguồn chưa ack;
5. Nguồn đã ack nhưng audit chưa hoàn tất.

Mỗi điểm cần nêu rõ cách hệ thống khôi phục, cách dedupe và bằng chứng **không mất hoặc tạo hai tác dụng phụ**. Không chỉ assert số lần mock được gọi.

## 32. Bài tập tình huống: SFTP → HTTP ERP → JDBC → AMQP

### Bối cảnh

Một doanh nghiệp nhận file đơn hàng từ SFTP rồi đồng bộ từng record tới ERP.

~~~text
SFTP inbound adapter + poller
   -> staging
   -> parse + validate
   -> orderMessagesChannel
   -> HTTP outbound gateway (ERP)
   -> JDBC update status
   -> AMQP notification
   -> archive file
~~~

Yêu cầu:

- Không tạo order trùng ở ERP.
- Không mất record khi partner down.
- Record invalid phải quarantine.
- Replay có thể được kích hoạt theo business event ID.
- Process restart không làm mất các tác vụ pending.

### Diễn biến

| Thời điểm | Sự kiện |
|---|---|
| 08:00 | Đối tác đang upload orders-312.part |
| 08:02 | File được publish thành orders-312.ready |
| 08:03 | Poller nhận record A hợp lệ, B thiếu customerId |
| 08:04 | HTTP POST A: ERP commit nhưng response mất |
| 08:05 | Retry lần hai có nguy cơ tạo order trùng |
| 08:06 | ERP trả 503, nhiều worker retry đồng loạt |
| 08:07 | JDBC update status A deadlock |
| 08:08 | RabbitMQ mất kết nối |
| 08:09 | App restart giữa lúc một số handler đang backoff |
| 08:12 | File được replay từ staging |
| 08:15 | Ops chỉ thấy error channel, chưa biết message đã lưu bền chưa |

### Nhiệm vụ

1. Advice nên gắn ở endpoint nào, vì sao?
2. Lỗi nào cần retry, lỗi nào không?
3. Đề xuất maxAttempts, backoff và total deadline cho ERP.
4. Giải thích timeout sau remote commit khác connect failure thế nào.
5. Đề xuất stable event ID/idempotency key và state machine.
6. Hết retry thì làm gì để không mất message?
7. Vì sao JDBC deadlock và AMQP down không nên kích hoạt retry toàn flow?
8. Poller SFTP, retry advice và delayed replay khác nhau ra sao?
9. Nếu broker redeliver nhiều lần, tính tổng handler calls thế nào?
10. Chọn ít nhất năm metrics và tám test cases để xác minh.

### Hướng giải tham khảo

**1. Vị trí:** gắn RequestHandlerRetryAdvice ở **ERP HTTP outbound gateway** với điều kiện operation retry-safe. JDBC transaction retry riêng; AMQP publication qua outbox có retry/recovery riêng. Không bọc toàn chuỗi.

**2. Phân loại:** 503 có thể retry ngắn; HTTP timeout sau POST commit là OUTCOME_UNKNOWN; B invalid không retry; SFTP host-key/credential sai phải sửa auth; JDBC deadlock có thể retry transaction mới; AMQP outage cần durable retry.

**3. Ví dụ chính sách:** maxAttempts=4 tổng, exponential 250/500/1.000 ms có jitter, connect/read timeout và deadline theo hợp đồng. Đây là số **minh họa**, không phải chuẩn. Đối tác down lâu thì durable delayed retry.

**4. Không tạo duplicate:** Idempotency-Key = partnerId + orderId + businessVersion; dùng cùng key xuyên qua mọi attempt và redrive nếu ERP hỗ trợ contract đó. Nếu không, query/reconcile trạng thái trước khi gửi lại.

**5. State:** RECEIVED → VALIDATED → ERP_PENDING → ERP_CONFIRMED → NOTIFICATION_PENDING → DONE; trạng thái phụ OUTCOME_UNKNOWN, RETRY_WAIT, INVALID, PARKED. Inbox theo unique business key, outbox cho AMQP.

**6. Recovery:** message lỗi có eventId, payload reference, reason, attempts, owner/expiry và terminal state; chỉ ack nguồn nếu đã bảo toàn hoặc xử lý theo hợp đồng. Nếu parking fail, propagate error hoặc dùng cơ chế bảo đảm khác.

**7. Tách transaction:** DB deadlock retry DB transaction đúng phạm vi; AMQP down outbox publisher gửi lại sau commit. Không gọi ERP lại chỉ vì notification fail.

**8. Ba chu kỳ:** SFTP poller chạy theo lịch lấy file; RetryTemplate/backoff retry HTTP handler ngắn; durable replay lưu message qua restart và chạy lại khi đến lịch.

**9. Tổng calls:** ví dụ 4 attempts/delivery × 5 deliveries = **20 handler invocations**, chưa tính HTTP client retry.

**10. Quan sát/test:** handler_attempts_total, retry_exhausted_total, first-attempt success, duplicate_business_effect_total, parked backlog age, broker redelivery, handler latency và AMQP publish result. Test B invalid, 503 recovery, timeout sau commit, JDBC rollback, AMQP down, restart, parking fail, SFTP accept-once, broker redelivery và retry storm.

### Kiến trúc mục tiêu

~~~mermaid
flowchart TD
    S["SFTP ready file"] --> V["Stage + validate"]
    V -->|"Invalid"| Q["Quarantine reason"]
    V -->|"Valid"| I["Inbox stable eventId"]
    I --> E["ERP operation state"]
    E --> R{"Transient và retry-safe?"}
    R -->|"Có"| H["HTTP Handler + RetryAdvice"]
    R -->|"Outcome unknown"| C["Query ERP / reconcile"]
    H -->|"Success"| D["ERP_CONFIRMED"]
    C -->|"Confirmed"| D
    H -->|"Exhausted"| P["Durable RETRY_WAIT / PARKED"]
    P -->|"Đến lịch và còn deadline"| E
    D --> T["DB transaction: update + outbox"]
    T --> A["AMQP outbox publisher"]
    A -->|"Broker down"| W["Delayed publish"]
    W --> A
    A --> Z["DONE + archive"]
    Q --> O["Audit / triage"]
    P --> O
~~~

Sơ đồ chỉ mô tả trách nhiệm; vòng delayed retry phải có deadline, max attempts, concurrency/rate control và terminal state. Không triển khai busy loop vô hạn.

## 33. Anti-pattern cần tránh

| Anti-pattern | Tác hại | Cách sửa |
|---|---|---|
| Retry mọi Exception | Validation/auth lỗi vẫn lặp | Classifier theo exception và operation |
| Advice quanh workflow dài | Lặp side effect đã thành công | Retry từng handler |
| Nhầm maxAttempts với số retries thêm | Vượt calls | Tính cả attempt đầu |
| Không backoff/timeout | Storm hoặc treo thread | Timeout + backoff + deadline |
| POST không idempotency | Order/payment trùng | Stable key/reconciliation |
| RecoveryCallback nuốt lỗi | Broker ack message chưa bảo toàn | Durable recovery hoặc rethrow |
| Error channel được xem như DLQ bền | Mất message khi restart | Message store/broker DLQ |
| Nhầm retry handler với broker delivery | Tổng attempts nhân lên | Retry budget tổng |
| Nhầm retry với poller | Không lấy lại cùng file | Durable message state |
| JDBC retry trong rollback-only tx | Commit vẫn lỗi | Retry transaction mới |
| Dùng message UUID làm business key | Dedupe thất bại | Stable eventId |
| Kafka commit offset sớm | Mất business event | Ack/error handler đúng |
| AMQP requeue vô hạn | Broker hot loop | Delayed retry/DLQ |
| SFTP upload lại không kiểm remote | File trùng/partial | Temp file/checksum/reconcile |
| Giữ thread chờ hàng giờ | Cạn concurrency | Durable delayed retry |
| Không test crash | Silent message loss | Fault injection/crash tests |
| Log token/secret | Rò rỉ thông tin | Redaction/secure logging |
| Không test cause chain | Retry nhầm loại lỗi | Wrapped-exception tests |
| Chỉ đo retry success | Che lỗi đối tác | First-attempt success và latency |

## 34. Checklist triển khai

- [ ] Có sơ đồ inbound/source, channel, handler, adapter, gateway và đường lỗi.
- [ ] Gắn advice đúng endpoint, không bọc toàn orchestration mù.
- [ ] RetryTemplate/RetryPolicy/BackOffPolicy có cấu hình được kiểm thử.
- [ ] Phân loại transient/permanent/unknown outcome.
- [ ] Test wrapper exception và cause chain thực tế.
- [ ] MaxAttempts **tính cả lần đầu**, có timeout và deadline.
- [ ] Backoff/jitter, Retry-After/rate limit/circuit breaker phù hợp.
- [ ] Đã kiểm soát @Retryable, HTTP client retry, broker redelivery.
- [ ] Handler có stable eventId và idempotency/reconciliation.
- [ ] Retry/transaction advice order được kiểm tra với commit/rollback.
- [ ] DirectChannel/ExecutorChannel/QueueChannel có error path phù hợp.
- [ ] Poller File/SFTP không bị nhầm với durable replay.
- [ ] JMS/AMQP container ack/nack/DLQ không nuốt terminal error.
- [ ] Kafka offset/retry/DLT và ordering đúng hợp đồng.
- [ ] JDBC retry transaction mới khi cần, DB có unique key/outbox.
- [ ] RecoveryCallback không báo success khi message chưa được bảo toàn.
- [ ] Parking/DLQ có owner, retention, alert, controlled redrive.
- [ ] Lỗi kéo dài được chuyển durable retry thay vì giữ mọi threads.
- [ ] Metrics tách attempts, broker deliveries, redrives và business effects.
- [ ] Không ghi secret hoặc payload nhạy cảm không cần thiết vào log.
- [ ] Test invalid data, auth errors, timeout sau commit, recovery failure.
- [ ] Test restart/crash, duplicate effect, concurrency và SLA.

## 35. Thuật ngữ, tài liệu và câu hỏi ôn tập

### Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| **RequestHandlerRetryAdvice** | Advice retry invocation của message handler trong Spring Integration |
| **RetryTemplate** | Điều phối RetryCallback, RetryPolicy, BackOffPolicy và recovery |
| **RetryPolicy** | Quyết định exception/số attempts |
| **BackOffPolicy** | Khoảng chờ giữa attempts |
| **RetryContext** | Trạng thái chuỗi retry |
| **RecoveryCallback** | Xử lý sau khi exhausted |
| **ErrorMessage / error channel** | Tuyến lỗi, không mặc định durable |
| **Idempotency key** | Khóa nhận diện cùng business event qua retries |
| **Unknown outcome** | Không biết remote đã commit chưa |
| **DLQ/DLT/PARKED** | Đích giữ message lỗi để triage/replay |
| **Redelivery** | Broker/source giao lại message |
| **Ack/offset commit** | Nguồn ghi nhận tiến độ xử lý |
| **DirectChannel** | Channel thường dispatch đồng bộ trong thread sender |
| **ExecutorChannel** | Channel dùng executor, làm thay đổi đường exception |
| **Poller** | Lấy message theo trigger/lịch |
| **Inbox/outbox** | Pattern dedupe và bảo toàn ý định publish |
| **Circuit breaker/retry budget** | Giới hạn gọi dependency lỗi / tổng retries |
| **Poison message** | Message không thể xử lý nếu dữ liệu/chính sách không đổi |

### Tài liệu tham khảo khái niệm

- **Spring Integration Reference — Message Handler Advice / Retry and More:** RequestHandlerRetryAdvice và advice chain.
- **Spring Retry Reference:** RetryTemplate, RetryPolicy, BackOffPolicy, RetryContext, RecoveryCallback.
- **Spring Integration Reference — Polling Consumer, Message Channels, Error Handling:** đồng bộ/bất đồng bộ và error channel.
- **Spring Integration Reference — File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC adapters/gateways:** semantics của từng nguồn/đích.
- **Spring for Apache Kafka Reference:** listener error handling, offset, retry topic và DLT.
- **Spring AMQP Reference:** nack/requeue, DLQ và publisher confirm.
- **Spring Framework Transaction Management:** propagation, rollback và advice ordering.
- **Enterprise Integration Patterns:** Idempotent Receiver, Dead Letter Channel, Message Store, Transactional Client.

### Câu hỏi ôn tập

1. Vì sao advice trên HTTP handler không làm SFTP inbound đọc lại file?
2. maxAttempts=4 tương đương tối đa mấy retries bổ sung?
3. RecoveryCallback trả null có thể ảnh hưởng ack thế nào?
4. Vì sao HTTP POST timeout sau remote commit khác connect failure?
5. Hai tầng retry 3 và 4 attempts có thể tạo bao nhiêu invocations?
6. DirectChannel với backoff dài ảnh hưởng HTTP caller ra sao?
7. ExecutorChannel thay đổi cách nhận lỗi như thế nào?
8. JDBC rollback-only transaction cần retry ở đâu?
9. RequestHandlerRetryAdvice và Kafka consumer error handler khác gì?
10. Khi nào chuyển từ in-process retry sang durable delayed retry?

### Đáp án ngắn

1. Advice chỉ bọc handler; poller/filter có vòng đời riêng.
2. **3 lần retry** sau attempt ban đầu.
3. Container có thể coi message đã xử lý và ack khi chưa có durable recovery.
4. Remote có thể đã tạo side effect; cần idempotency/reconcile.
5. **3 × 4 = 12** khi các tầng lồng nhau đều chạy đủ.
6. Có thể giữ sender thread lâu hơn caller deadline.
7. Lỗi async cần error flow, không tự propagate về caller đồng bộ.
8. Retry transaction mới đúng scope, không lặp side effect ngoài DB.
9. Advice không tự seek/commit offset hoặc tạo retry topic/DLT.
10. Khi lỗi kéo dài, tải lớn hoặc yêu cầu khôi phục sau restart.

**Điểm cần ghi nhớ:** **RequestHandlerRetryAdvice** giúp thử lại **đúng invocation của message handler được gắn advice** trong Spring Integration. Độ tin cậy không đến từ tăng maxAttempts đơn thuần mà phụ thuộc vào **phân loại lỗi, ranh giới handler, idempotency, transaction/ack, recovery bền vững và kiểm thử side effects thực**. Khi kết nối ngoài thất bại, cần chứng minh được **message không bị mất, không tạo tác dụng phụ trùng và lỗi được xử lý đúng tầng**.
