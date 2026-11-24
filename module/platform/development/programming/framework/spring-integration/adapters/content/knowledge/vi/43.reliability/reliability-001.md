# Retry advice cho request handler

**Chương:** Reliability  
**Bài học:** Retry advice cho request handler  
**Module:** Spring Integration Adapters  
**Phạm vi:** Thiết kế và vận hành cơ chế thử lại (retry) ở **message handler** trong Spring Integration, phối hợp với inbound/outbound adapter, gateway, poller và MessageChannel; phân biệt lỗi tạm thời với lỗi vĩnh viễn, xử lý backoff, recovery, tính lặp an toàn, transaction và bằng chứng giám sát.

## 1. Vì sao request handler cần retry?

Trong một hệ thống tích hợp, việc gửi hoặc nhận dữ liệu qua HTTP, SFTP, JMS, AMQP, Kafka, file hoặc cơ sở dữ liệu có thể thất bại vì nguyên nhân không cố định: kết nối bị ngắt trong chốc lát, remote service đang quá tải, broker chuyển leader, cơ sở dữ liệu xảy ra deadlock hoặc một session truyền file bị đóng giữa chừng. Nếu bỏ qua mọi lỗi, thông điệp có thể bị mất; nếu thử lại mọi lỗi, luồng có thể bị kẹt hoặc gây xử lý trùng.

**Retry advice cho request handler** là một cách đặt cơ chế thử lại sát **bước xử lý message**. Trong Spring Integration, lớp thường dùng là **`RequestHandlerRetryAdvice`**, kết hợp với **Spring Retry `RetryTemplate`** để quyết định:

- Lỗi nào có thể thử lại?
- Tối đa bao nhiêu lần gọi handler?
- Khoảng chờ giữa các lần thử là bao lâu?
- Nếu vẫn thất bại thì ném lỗi tiếp hay chuyển sang recovery?
- Retry này có tác động gì tới acknowledgement, transaction, thứ tự message và tính lặp an toàn?

**Trọng tâm:** Retry không phải thao tác “gọi lại bất kỳ chỗ nào lỗi”. Đó là **một chính sách xử lý lỗi có ranh giới rõ**, đặt vào đúng endpoint và có quy tắc khi thất bại cuối cùng.

### 1.1. Tình huống dẫn nhập

Một ứng dụng nhận lệnh tạo yêu cầu vận chuyển từ JMS, chuyển thành JSON và gọi dịch vụ HTTP của đối tác. Đối tác trả timeout vì mạng chập chờn.

~~~text
JMS inbound adapter
    -> transform payload
    -> DirectChannel
    -> HTTP outbound gateway
    -> kết quả / lỗi
~~~

Nếu HTTP handler bị timeout, retry có thể giúp gọi lại mà không yêu cầu producer gửi message mới. Tuy nhiên, nếu đối tác **đã tạo yêu cầu nhưng phản hồi bị mất**, gọi lại có thể tạo hai yêu cầu vận chuyển. Vì vậy retry phải đi cùng **idempotency key**, chính sách timeout và quy tắc xác minh kết quả không chắc chắn.

### 1.2. Mục tiêu học tập

Sau bài này, người học có thể:

1. Xác định chính xác vị trí `RequestHandlerRetryAdvice` trong một luồng Spring Integration.
2. Phân biệt retry trong handler với retry tại poller, listener container, broker hoặc ứng dụng gọi bên ngoài.
3. Cấu hình `RetryTemplate`, retry policy, exponential backoff và recovery cho một endpoint.
4. Phân loại lỗi transient, permanent và **ambiguous outcome** thay vì retry tất cả.
5. Giải thích mối quan hệ giữa retry, transaction, acknowledgement, error channel và dead-letter handling.
6. Chọn chiến lược phù hợp với file/SFTP, HTTP, JMS/AMQP, Kafka và JDBC.
7. Thiết kế metric, log, kiểm thử và runbook vận hành khi hết retry.

## 2. Ôn lại các thành phần Spring Integration liên quan

| Thành phần | Vai trò trong luồng | Liên quan tới retry |
| --- | --- | --- |
| **Message** | Payload và headers mang hợp đồng dữ liệu | Cùng một message có thể được xử lý lại; header không tự bảo đảm idempotency |
| **MessageChannel** | Kết nối các endpoint | `DirectChannel` thường đồng bộ; `ExecutorChannel` tạo ranh giới bất đồng bộ |
| **Inbound channel adapter** | Nhận dữ liệu/sự kiện từ hệ thống bên ngoài và tạo message | Có cơ chế poll/ack/redelivery riêng |
| **Outbound channel adapter** | Gửi message ra hệ thống ngoài, thông thường không có reply ứng dụng | Retry bao quanh thao tác gửi ở handler nếu được hỗ trợ |
| **Outbound gateway** | Gửi request và nhận reply | Retry có thể lặp lại toàn bộ request; chú ý tác động phía remote |
| **Service activator** | Xử lý message bằng phương thức nghiệp vụ | Có thể gắn advice ở endpoint tương ứng |
| **Poller** | Kích hoạt nguồn nhận theo lịch/trigger | Poller advice/transaction có ranh giới khác handler advice |
| **Error channel** | Nhận `ErrorMessage` khi lỗi được gửi tới luồng xử lý lỗi | Không tự thay thế policy thử lại |
| **`RequestHandlerRetryAdvice`** | Thử lại lời gọi xử lý của handler theo `RetryTemplate` | Không tự làm broker redelivery hoặc bền vững hóa message |

Một **gateway** khác **adapter** ở hợp đồng reply. Trong gateway, caller có thể đang chờ một response; trong outbound adapter một chiều, hệ thống thường chỉ quan tâm side effect gửi thành công. Cách chọn recovery ảnh hưởng trực tiếp tới hợp đồng này.

### 2.1. Lớp exception và nơi lỗi xuất hiện

Một HTTP handler có thể phát `ResourceAccessException` khi lỗi kết nối; một handler khác có thể bọc nguyên nhân trong `MessagingException`. Retry policy cần đánh giá **lỗi được ném tại ranh giới handler**, đôi khi gồm cả cause chain. Không nên chỉ xem nội dung message lỗi hoặc chuỗi mô tả như “timeout”.

### 2.2. Request handler là ranh giới xử lý, không phải mọi điểm trong flow

Giả sử:

~~~text
inbound adapter
  -> transform
  -> filter
  -> outbound HTTP handler [retry advice]
  -> output channel
~~~

Nếu đặt advice trên **outbound HTTP handler**, Spring Integration sẽ thử lại việc thực thi handler đó theo policy. Nó **không có nghĩa** toàn bộ chuỗi inbound–transform–filter được chạy lại trong mỗi attempt. Lỗi ở transformer phía trước hoặc ở một handler khác cần cơ chế riêng.

## 3. RequestHandlerRetryAdvice hoạt động theo mô hình nào?

`RequestHandlerRetryAdvice` thuộc nhóm **request-handler advice** của Spring Integration. Nó phối hợp với `RetryTemplate`: mỗi lần xử lý message đi qua advice, template quyết định có thực hiện thêm lần xử lý khi handler ném exception hay không.

~~~mermaid
flowchart TD
    IN["Message đến endpoint"] --> AD["RequestHandlerRetryAdvice"]
    AD --> POL["RetryTemplate<br/>RetryPolicy + BackOffPolicy"]
    POL --> H["Message handler thực thi"]
    H --> Q{"Thành công?"}
    Q -->|Có| OK["Trả reply / hoàn thành handler"]
    Q -->|Lỗi| C{"Retryable và còn attempts?"}
    C -->|Có| WAIT["Backoff theo policy"]
    WAIT --> H
    C -->|Không| REC{"Có recovery callback?"}
    REC -->|Có| RC["Thực thi recovery"]
    REC -->|Không| EX["Ném lỗi ra ranh giới caller"]
    RC --> END["Kết quả tùy callback"]
~~~

**Default hướng tới retry tại lời gọi handler hiện tại.** Trong chế độ retry thông thường (stateless), các lần thử diễn ra trong cùng hoạt động xử lý, thường trên cùng thread và cùng message. Khi cần giữ trạng thái giữa các lần redelivery của broker hoặc các transaction khác nhau, cần đánh giá **stateful retry** và kiến trúc nguồn nhận, không tự suy rằng RequestHandlerRetryAdvice mặc định có persistence.

### 3.1. Các thành phần cấu hình

| Thành phần | Trách nhiệm |
| --- | --- |
| `RequestHandlerRetryAdvice` | Gắn retry vào request handler của endpoint |
| `RetryTemplate` | Thực thi vòng lặp attempts và xử lý recovery |
| `RetryPolicy` | Quyết định exception có retry được, số attempts, điều kiện dừng |
| `BackOffPolicy` | Quyết định khoảng chờ giữa attempts |
| `RetryContext` | Theo dõi trạng thái của hoạt động retry |
| `RecoveryCallback` | Xử lý khi retry đã cạn hoặc chính sách dừng |
| `ErrorMessageSendingRecoverer` | Một lựa chọn gửi lỗi cuối cùng dưới dạng `ErrorMessage` tới channel |

**Số attempts bao gồm lần đầu.** Nếu cấu hình tối đa 4 attempts thì thông thường có **1 lần gọi đầu + tối đa 3 lần thử lại**, chứ không phải 4 lần retry bổ sung.

### 3.2. Advice không tạo ra retry bền vững

Nếu JVM chết giữa lần thử thứ hai, một stateless `RetryTemplate` không tự lưu lịch sử attempt vào database để khôi phục. Việc message có được đưa lại vào luồng sau khi khởi động tùy thuộc inbound adapter, transaction/ack, broker, file filter và thiết kế lưu trữ.

Vì thế cần phân biệt:

- **In-process retry:** Nhanh, gần lỗi, có backoff nhưng tiêu thụ thread và mất state khi process dừng.
- **Broker redelivery / durable retry:** Message được gửi lại qua broker/container hoặc retry topic/queue, có khả năng tồn tại qua restart nếu được cấu hình phù hợp.
- **Application-level recovery:** Lưu yêu cầu chưa thành công ở một kho bền vững để xử lý sau, có owner và idempotency.

## 4. Đặt advice ở đúng endpoint

Trong Java DSL, advice thường được gắn vào **endpoint configuration** của handler thông qua phương thức cấu hình advice trên endpoint. Ví dụ cấu trúc:

~~~java
// DSL minh họa: lời gọi handler được advice bao quanh.
return IntegrationFlow.from("outboundRequests")
    .handle(someOutboundHandlerSpec,
        endpoint -> endpoint.advice(requestHandlerRetryAdvice))
    .get();
~~~

Điều này khác với việc đặt advice trên poller hoặc sử dụng retry của HTTP client. Một luồng có nhiều handlers có thể cần những retry policies **khác nhau**:

~~~mermaid
flowchart LR
    SRC["Inbound Adapter"] --> T["Transformer"]
    T --> A["HTTP Gateway<br/>Retry: network transient"]
    A --> B["JDBC Handler<br/>Retry: DB transient"]
    B --> OUT["Result Channel"]
    E["Error/Recovery Channels"] -.-> A
    E -.-> B
~~~

Không dùng một policy “retry mọi lỗi 10 lần” chung cho tất cả endpoints: timeout HTTP, lỗi constraint trong JDBC và xác thực SFTP sai mật khẩu có cách xử lý khác nhau.

### 4.1. Bẫy ranh giới đồng bộ và bất đồng bộ

**`DirectChannel`** gọi subscriber theo đường đồng bộ; exception thường có thể lan tới caller trong cùng call stack. **`ExecutorChannel`** chuyển xử lý sang executor thread, tạo ranh giới bất đồng bộ: caller upstream có thể đã hoàn thành gửi message trước khi handler downstream lỗi.

Do đó:

- Retry advice ở handler downstream vẫn có thể thử lại tại handler đó.
- Exception sau ranh giới bất đồng bộ có thể đi tới error flow, không trở ngược theo cách caller đồng bộ kỳ vọng.
- Transaction/acknowledgement của adapter nguồn **không tự được kéo dài** qua mọi channel bất đồng bộ.
- Cần xác định rõ message được đánh dấu xử lý thành công tại ranh giới nào.

### 4.2. Handler advice khác poller advice

Poller kích hoạt việc lấy message từ nguồn; ví dụ file poller kiểm tra thư mục mỗi 5 giây. **Retry ở poller** liên quan thao tác poll/receive, còn **retry ở request handler** liên quan logic handler sau khi message đã được lấy.

Không nên coi retry một lời gọi HTTP outbound đồng nghĩa **đọc lại file/SFTP message**. Nếu cần nguồn đưa message trở lại sau crash, phải thiết kế accept-once filter, metadata store, transaction hoặc mechanism redelivery tương ứng.

## 5. Phân loại lỗi trước khi viết retry policy

Một policy tốt bắt đầu bằng **định nghĩa lỗi retryable**.

| Loại lỗi | Ví dụ | Quyết định thường phù hợp |
| --- | --- | --- |
| **Transient network** | Connection reset, connect timeout, mất kết nối ngắn | Retry có giới hạn, backoff và timeout |
| **Rate limiting / overloaded service** | HTTP 429; HTTP 503 theo hợp đồng remote | Chờ theo `Retry-After` khi phù hợp, giới hạn tốc độ |
| **Transient database** | Deadlock, serialization conflict, kết nối tạm gián đoạn | Retry tác vụ/transaction phù hợp nếu lặp an toàn |
| **Broker failover** | Mất session tạm thời, reconnect trong lúc đổi leader | Chính sách retry/reconnect đúng client/container |
| **Permanent client error** | Payload sai schema, sai tham số, resource không hợp lệ | Không retry lặp vô hạn; sửa dữ liệu hoặc code |
| **Authentication / authorization** | HTTP 401/403, token không đủ quyền | Thường không retry cùng credential; xử lý identity/permission |
| **Configuration error** | SFTP credentials sai, đường dẫn sai, exchange/queue chưa cấu hình đúng | Không retry dồn dập; báo vận hành |
| **Conflict / duplicate** | Unique constraint, entity đã tồn tại | Xác minh ý nghĩa nghiệp vụ; có thể coi là đã hoàn tất nếu idempotent |
| **Ambiguous outcome** | Remote đã xử lý nhưng response/ack bị mất | Cần idempotency hoặc truy vấn trạng thái trước khi gọi lại |
| **Poison message** | Dữ liệu khiến handler luôn ném exception | Dừng sau số lần hợp lý, cách ly DLQ/quarantine |

**Lỗi 5xx không mặc nhiên luôn an toàn để retry.** Một dịch vụ có thể xử lý xong yêu cầu rồi gặp lỗi khi trả response. **HTTP POST không tự bảo đảm idempotent**; chỉ retry khi hợp đồng API và cơ chế chống trùng đáp ứng.

### 5.1. Xử lý cause chain

Tầng Spring Integration có thể bọc nguyên nhân trong exception của messaging. Nếu retry policy chỉ so class exception ở tầng ngoài, nó có thể bỏ sót `ResourceAccessException` hoặc lỗi kết nối thực. Ngược lại, cấu hình retry theo **mọi `Exception`** có thể vô tình retry lỗi dữ liệu, lỗi code hoặc lỗi quyền.

Nên phân loại theo **exception type có căn cứ**, xét nested causes khi thích hợp, và bổ sung kiểm thử cho wrapped exceptions thật của adapter.

### 5.2. Một bảng quyết định trước khi retry

Trước mỗi nhóm lỗi, hỏi:

1. Lỗi có khả năng biến mất nếu chờ rồi thử lại không?
2. Lời gọi handler có side effect không?
3. Có biết remote chắc chắn **chưa xử lý** yêu cầu không?
4. Nếu không biết, có idempotency key hoặc cơ chế query trạng thái không?
5. Retry có vượt deadline của upstream không?
6. Khi hết retry, message sẽ được redeliver, vào DLQ hay được đánh dấu hoàn tất?

Nếu không trả lời được câu 2–4, **không áp retry mù quáng cho thao tác có thể tạo dữ liệu hoặc chuyển tiền**.

## 6. Cấu hình RetryTemplate và backoff

Spring Retry cung cấp `RetryTemplate` có thể kết hợp `RetryPolicy` và `BackOffPolicy`. Một cấu hình thường dùng cho lỗi kết nối transient:

- Tối đa **4 attempts**.
- Backoff ban đầu **250 ms**.
- Nhân đôi khoảng chờ sau mỗi lần lỗi.
- Giới hạn khoảng chờ mỗi lần tại **3 giây**.
- Chỉ retry nhóm exception đã xác định, gồm nested cause khi thực sự cần.

### 6.1. Mã Java cấu hình advice

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.web.client.ResourceAccessException;

@Configuration
public class RetryAdviceConfiguration {

    @Bean
    public RequestHandlerRetryAdvice httpNetworkRetryAdvice() {
        // 4 attempts TỔNG CỘNG, bao gồm lần gọi đầu tiên.
        var retryable = Map.<Class<? extends Throwable>, Boolean>of(
                ResourceAccessException.class, true);
        var retryPolicy = new SimpleRetryPolicy(
                4, retryable, true); // true: kiểm tra cả nested causes

        var backOff = new ExponentialBackOffPolicy();
        backOff.setInitialInterval(250L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(3_000L);

        var retryTemplate = new RetryTemplate();
        retryTemplate.setRetryPolicy(retryPolicy);
        retryTemplate.setBackOffPolicy(backOff);

        var advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(retryTemplate);
        return advice;
    }
}
~~~

**Giải thích:** Policy minh họa chỉ retry `ResourceAccessException` hoặc lớp nguyên nhân tương ứng trong cause chain. Nó không tự retry HTTP 5xx hoặc 429; nếu remote API yêu cầu xử lý chúng, phải **mở rộng policy có chọn lọc** và thiết kế phù hợp với `Retry-After`, idempotency cùng thời gian chờ tổng thể.

**Lưu ý tương thích:** Ví dụ dùng API của Spring Integration và Spring Retry phổ biến trong hệ sinh thái Spring hiện đại; import, builder DSL và overload có thể khác theo phiên bản dependency thực tế. Mọi cấu hình trước production cần được biên dịch và kiểm thử theo BOM/version của ứng dụng.

### 6.2. Exponential backoff có tác dụng gì?

Nếu timeout xảy ra vì remote đang quá tải, retry ngay lập tức có thể làm tình trạng tệ hơn. Backoff giúp giãn khoảng giữa lần thử, hạn chế tạo bão request.

~~~text
Attempt 1 -> lỗi
  chờ 250 ms
Attempt 2 -> lỗi
  chờ 500 ms
Attempt 3 -> lỗi
  chờ 1000 ms
Attempt 4 -> lỗi hoặc thành công
  hết quota retry, xử lý theo recovery/exception
~~~

Nên cân nhắc **jitter** trong backoff nếu nhiều instance đồng loạt retry: các khoảng chờ quá đồng bộ có thể tạo thác request. Có thể sử dụng backoff policy hỗ trợ randomization hoặc cơ chế tương đương đã được kiểm thử cho phiên bản Spring Retry đang dùng.

### 6.3. Retry budget và deadline

Giả sử `N` attempts, timeout tối đa mỗi lần `T` và các khoảng chờ `B₁ ... Bₙ₋₁`, thời gian trước khi trả kết quả xấp xỉ:

~~~text
Worst-case retry time ≈ N × T + sum(Bi) + overhead
~~~

Nên dùng deadline của caller, thời gian chờ ở gateway, consumer poll/ack và giới hạn thread pool để chọn N và backoff. Một HTTP gateway có caller timeout 3 giây **không nên** triển khai một vòng retry đồng bộ dự kiến mất nhiều chục giây mà không có hợp đồng bất đồng bộ hoặc cơ chế phản hồi thích hợp.

### 6.4. Retry không phải phép chữa mọi timeout

Nếu vấn đề là pool HTTP quá nhỏ, DNS sai, thông số socket timeout không hợp lý hoặc network policy chặn hoàn toàn, tăng attempts chỉ che nguyên nhân và tạo tải thêm. Retry policy phải đi kèm **timeout, connection pool, concurrency limit, health check và circuit breaker** ở những vị trí phù hợp.

## 7. Gắn RequestHandlerRetryAdvice vào HTTP outbound gateway

Ví dụ dưới đây tập trung vào **request handler** của HTTP outbound gateway. Một channel nhận message; gateway gọi HTTP POST; nếu gặp lỗi mạng phù hợp policy, lời gọi handler được thử lại. Khi thành công, kết quả được gửi tới channel tiếp theo.

### 7.1. Cấu hình Java DSL

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.integration.http.dsl.Http;

@Configuration
public class OutboundHttpFlowConfiguration {

    @Bean
    public IntegrationFlow partnerRequestFlow(
            RequestHandlerRetryAdvice httpNetworkRetryAdvice) {

        return IntegrationFlow.from("partnerRequests")
                .handle(
                        Http.outboundGateway(
                                        "https://partner.example.invalid/api/commands")
                                .httpMethod(HttpMethod.POST)
                                .expectedResponseType(String.class),
                        endpoint -> endpoint.advice(httpNetworkRetryAdvice))
                .channel("partnerResponses")
                .get();
    }
}
~~~

Đây là ví dụ về **cách gắn advice**, chưa phải ứng dụng production hoàn chỉnh. Địa chỉ `example.invalid` là placeholder không truy cập thực tế; hợp đồng JSON, authentication, timeout, HTTPS, header idempotency, xử lý lỗi HTTP và các channel cần được cấu hình tương ứng hệ thống đích.

### 7.2. Điều gì xảy ra khi timeout?

Giả sử response đầu tiên bị lỗi kết nối:

~~~mermaid
sequenceDiagram
    participant C as Caller / upstream channel
    participant A as Retry advice
    participant H as HTTP outbound gateway
    participant P as Partner API
    C->>A: Message chứa command
    A->>H: Attempt 1
    H->>P: HTTP POST
    P--xH: Connection/response thất bại
    H-->>A: Throw retryable exception
    A->>A: Backoff theo policy
    A->>H: Attempt 2
    H->>P: Gửi lại request
    P-->>H: 200 + response
    H-->>A: Reply payload
    A-->>C: Handler hoàn tất
~~~

**Rủi ro quan trọng:** Attempt 1 có thể đã được partner xử lý trước khi kết nối hỏng. Do đó sơ đồ không chứng minh POST thử lại luôn an toàn. Cần thiết kế idempotency ở §10.

### 7.3. Một retry policy cho nhiều flow?

Có thể tái sử dụng một advice bean nếu các endpoints dùng **cùng** chính sách lỗi, attempts và backoff. Nhưng production thường cần policy riêng cho HTTP GET, HTTP POST, gửi SFTP, truy vấn JDBC hoặc broker:

- GET tới dịch vụ chỉ đọc có thể chịu retry có giới hạn theo contract.
- POST tạo tài nguyên cần idempotency key hoặc trạng thái bền vững.
- JDBC ghi dữ liệu cần xem transaction isolation và duplicate constraint.
- File/SFTP có rủi ro partial output.

Tái sử dụng cấu hình không được che đi **mức rủi ro khác nhau của side effect**.

## 8. RecoveryCallback và ErrorMessageSendingRecoverer

Khi hết attempts, có hai hướng phổ biến:

1. **Không cấu hình recovery callback:** Exception được ném trở ra theo ranh giới đồng bộ/bất đồng bộ. Nguồn nhận, error flow hoặc caller xử lý tiếp.
2. **Có recovery callback:** Advice gọi logic recovery; ví dụ gửi `ErrorMessage` tới một channel xử lý thất bại. Kết quả và việc exception có tiếp tục được ném hay không phụ thuộc callback.

### 8.1. Cấu hình recovery gửi ErrorMessage

~~~java
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.messaging.MessageChannel;
import org.springframework.retry.support.RetryTemplate;

// Minh họa phần cấu hình advice; bean và channel được cung cấp bởi ứng dụng.
RequestHandlerRetryAdvice createAdvice(
        RetryTemplate template,
        MessageChannel exhaustedErrors) {
    var advice = new RequestHandlerRetryAdvice();
    advice.setRetryTemplate(template);
    advice.setRecoveryCallback(
            new ErrorMessageSendingRecoverer(exhaustedErrors));
    return advice;
}
~~~

`ErrorMessageSendingRecoverer` hữu ích để đưa **kết quả retry exhausted** tới channel riêng, nơi hệ thống có thể ghi audit, mở incident hoặc định tuyến một tác vụ sang retry queue/DLQ. **Nó không tự bảo đảm channel là durable hay message đã vào DLQ thành công theo giao dịch.**

### 8.2. Cẩn thận khi recovery trả kết quả bình thường

Đây là điểm đặc biệt quan trọng: nếu recovery callback **xử lý lỗi và trả về bình thường**, caller hoặc listener container có thể coi xử lý của handler là hoàn tất. Trong flow nhận từ JMS/AMQP/Kafka, điều này có thể dẫn tới **ack hoặc commit offset** theo cấu hình adapter, dù tác vụ nghiệp vụ chưa hoàn tất.

Vì thế trước khi dùng recovery:

- Xác định **hợp đồng success/failure** của handler.
- Xác định nơi thông điệp thất bại được lưu **bền vững**.
- Quyết định có muốn broker redelivery/rollback hay không.
- Xác minh thứ tự **ghi DLQ/quarantine → ack nguồn**.
- Không để channel error thiếu subscriber khiến lỗi tiếp tục bị bỏ qua hoặc xử lý sai.

### 8.3. Recovery trong gateway có reply

Với **outbound gateway** request/reply, recovery trả `null` hoặc chỉ gửi error sang channel khác có thể khiến caller **không nhận reply mong đợi** hoặc bị timeout theo flow/configuration. Không coi callback ghi log là một response nghiệp vụ hợp lệ.

Nếu muốn gateway trả lỗi theo hợp đồng, cần thiết kế **error reply hoặc exception** rõ ràng để caller phân biệt failure; không âm thầm biến một HTTP POST thất bại thành response thành công.

## 9. Error channel, retry và vòng đời exception

Spring Integration có cơ chế xử lý lỗi thông qua **error channel** và `ErrorMessage`; message có thể mang thông tin exception cùng message gốc theo trường hợp. Retry advice là một lớp khác: nó quyết định **thử lại tại handler trước khi lỗi được xử lý ở tầng ngoài**.

~~~mermaid
flowchart TD
    M["Message đến handler"] --> R["Handler + Retry advice"]
    R --> S{"Thành công?"}
    S -->|Có| OUT["Reply hoặc side effect hoàn tất"]
    S -->|Không, hết retry| Q{"Có recovery callback?"}
    Q -->|Không| PROP["Exception lan theo caller / endpoint boundary"]
    Q -->|Có| REC["Recovery nhận Throwable/RetryContext"]
    REC --> ERR["ErrorMessage hoặc durable failure record"]
    PROP --> EC["Error flow, transaction rollback hoặc caller"]
~~~

Tùy nguồn message và kiểu channel, exception có thể xuất hiện trong call stack, được gửi tới error channel, được listener container xử lý hoặc dẫn đến rollback. **Không thể suy ra một cấu hình errorChannel chung sẽ tự tạo retry, rollback và DLQ cho mọi adapter.**

### 9.1. Log lỗi như thế nào?

Một sự kiện retry nên có:

~~~json
{
  "flow": "partnerRequestFlow",
  "component": "http-outbound-gateway",
  "messageId": "msg-2107",
  "businessKey": "order-7642",
  "attempt": 3,
  "maxAttempts": 4,
  "errorClass": "ResourceAccessException",
  "retryDecision": "RETRY",
  "elapsedMs": 1850,
  "correlationId": "corr-5120"
}
~~~

Đây là **ví dụ định dạng telemetry**, không phải schema log tự sinh của Spring Integration. Không ghi token, mật khẩu, SFTP credential, toàn bộ payload có dữ liệu nhạy cảm hoặc chuỗi connection chứa secret.

### 9.2. RetryListener và observability

Spring Retry hỗ trợ cơ chế listener cho hoạt động retry; Spring Integration cũng có cơ chế quan sát/metrics tùy phiên bản. Có thể instrument:

- Số attempt và lý do retry.
- Thời gian backoff và thời gian handler.
- Retry success sau lần thứ mấy.
- Số lần exhausted và nguyên nhân cuối cùng.
- Số message đi vào durable recovery/DLQ.
- Mối liên hệ giữa message ID, business key và remote request ID.

**Không ghi một log ERROR cho mọi attempt** nếu số lượng lớn gây nhiễu; có thể dùng WARN/INFO/DEBUG theo chính sách, ghi ERROR khi exhausted hoặc gây tác động thực tế.

## 10. Idempotency: điều kiện then chốt khi có side effect

**Idempotency** nghĩa là cùng một thao tác với cùng khóa ngữ nghĩa được lặp lại mà không tạo thêm kết quả nghiệp vụ không mong muốn. Retry và redelivery làm tăng khả năng cùng message được xử lý nhiều lần, nên **at-least-once delivery + idempotent consumer/remote endpoint** thường là chiến lược thực tế.

### 10.1. Ba tình huống khi gọi remote

| Kết quả quan sát | Remote thật sự làm gì? | Retry có rủi ro không? |
| --- | --- | --- |
| Kết nối thất bại trước khi gửi request | Nhiều khả năng chưa xử lý | Có thể retry, nhưng vẫn phải hiểu điểm thất bại |
| Remote xác nhận lỗi transient trước xử lý | Chưa tạo side effect nếu contract cam kết | Có thể retry có kiểm soát |
| Remote xử lý xong nhưng response bị mất | Side effect **đã xảy ra** | Retry mù quáng có thể tạo duplicate |

Không thể chỉ dựa trên từ “timeout” để suy ra tác vụ chưa được thực thi.

### 10.2. Business key và idempotency key

Khi gọi API tạo yêu cầu vận chuyển, dùng **một idempotency key ổn định theo tác vụ nghiệp vụ**. Tất cả attempts của cùng message phải dùng cùng key; một tác vụ mới thực sự phải dùng key khác.

~~~text
Message business key: shipment-request-9281
Idempotency-Key gửi HTTP: shipment-request-9281

Attempt 1: remote tạo shipment, response bị mất.
Attempt 2: remote nhận cùng key, trả cùng kết quả hoặc trạng thái cũ.
Kết quả: 1 shipment, không phải 2 shipment.
~~~

Hiệu lực phụ thuộc **API đối tác có thực sự hỗ trợ idempotency key** và thời hạn lưu key. Tự thêm header `Idempotency-Key` không có tác dụng nếu remote bỏ qua header.

### 10.3. Chống trùng ở phía hệ thống nội bộ

Với JMS/AMQP/Kafka inbound, có thể dùng một **inbox/deduplication table** hoặc constraint duy nhất theo business key:

~~~sql
-- Minh họa schema; cách transaction/UPSERT phụ thuộc database.
CREATE TABLE processed_message (
    business_key VARCHAR(200) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Chỉ đánh dấu message đã xử lý khi các side effect tương ứng được bảo đảm theo transaction/consistency model. Nếu database transaction commit thành công nhưng remote API chưa được gọi, việc ghi dedup quá sớm có thể khiến tác vụ bị bỏ sót. Với luồng có hai hệ thống không chung transaction, cân nhắc **transactional outbox/inbox và state machine**.

### 10.4. Exactly-once cần phát biểu đúng phạm vi

Một broker hoặc connector có thể cung cấp đảm bảo giao hàng nhất định trong hệ sinh thái của nó, nhưng **không tự tạo exactly-once business effect trên HTTP + database + SFTP**. Muốn giảm duplicate phải xây dựng idempotency ở biên, transaction cục bộ, cơ chế đối soát và logic xử lý outcome chưa rõ.

## 11. Transaction, acknowledgement và commit

Retry ở handler phải được thiết kế cùng transaction/acknowledgement của nguồn. Nếu message được ack trước khi side effect hoàn tất, lỗi về sau có thể gây mất tác vụ. Nếu message được redeliver sau khi remote đã xử lý, có thể gây duplicate.

### 11.1. Stateless retry trong cùng lần xử lý

Trong retry thông thường:

~~~text
receive message
  -> handler attempt 1
  -> backoff
  -> handler attempt 2
  -> ... thành công hoặc exhausted
  -> trở về caller/container
~~~

Nếu source container đang giữ một transaction/ack cho toàn bộ lời gọi, tổng thời gian retry ảnh hưởng **consumer concurrency, lock duration, transaction timeout và khả năng redelivery**. Không giả định một lời gọi HTTP ra ngoài có thể rollback chỉ vì local database transaction rollback.

### 11.2. Stateful retry và redelivery

Một số kiến trúc cần **lưu thông tin retry theo khóa message** qua những lần broker redelivery hoặc transaction mới. Spring Retry có cơ chế retry state/context; Spring Integration hỗ trợ mô hình stateful retry trong cấu hình phù hợp.

Các điều kiện cần:

- **Retry key ổn định**, không thay đổi giữa redelivery của cùng công việc.
- Quản lý retry context cache/state phù hợp; hiểu phạm vi persistence và restart.
- Exception được truyền ra để transaction/consumer xử lý redelivery khi thiết kế yêu cầu.
- Có chính sách kết thúc: dead-letter, quarantine, trạng thái FAILED hoặc escalation.

**Stateful không tự đồng nghĩa durable qua JVM restart.** Context cache mặc định hay configuration cụ thể có thể không bền vững; nếu cần bảo đảm qua crash, phải dùng cơ chế broker hoặc state store bền vững có chủ đích.

### 11.3. Recovery có thể ảnh hưởng ack

Một minh họa với message broker:

~~~text
Message received
    -> handler retry 4 attempts
    -> exhausted
    -> recovery callback ghi log rồi trả bình thường
    -> listener coi handler đã hoàn thành
    -> có thể ack/commit theo cấu hình
~~~

Nếu không có durable failure record, message nghiệp vụ có thể mất. Phải định nghĩa rõ: **sau khi exhausted thì ném exception để broker redeliver, hay chuyển vào DLQ có bảo đảm rồi mới ack?** Hai chiến lược này không nên trộn bằng cấu hình ngầm.

## 12. Ba lớp retry và nguy cơ retry chồng nhau

Trong tích hợp thực tế có thể xuất hiện **ba hoặc nhiều lớp retry**:

1. HTTP/JMS/Kafka/SFTP client library retry hoặc reconnect nội bộ.
2. `RequestHandlerRetryAdvice` tại Spring Integration handler.
3. Broker/listener container redelivery, poller reprocessing hoặc caller retry từ bên ngoài.

~~~mermaid
flowchart TD
    BROKER["Broker / inbound adapter<br/>Có redelivery policy"] --> SI["Spring Integration Handler<br/>Retry advice"]
    SI --> CLIENT["HTTP/SFTP/JDBC client<br/>Có timeout/retry nội bộ"]
    CLIENT --> REM["Remote system"]
    SI -.-> DLQ["Durable recovery / DLQ"]
~~~

Nếu mỗi lớp tự cấu hình 3 attempts, tổng số lần chạm remote trong một trường hợp thất bại có thể tăng nhiều lần. Không cấu hình retry ở mọi tầng rồi nghĩ rằng hệ thống chỉ thử ba lần.

### 12.1. Chọn một tầng chịu trách nhiệm chính

| Nhu cầu | Tầng nên cân nhắc | Lưu ý |
| --- | --- | --- |
| Lỗi kết nối ngắn trong một request | Handler advice hoặc HTTP client, tránh lặp không kiểm soát | Deadline, idempotency |
| Retry sau vài phút hoặc qua restart | Broker retry queue/topic, durable scheduler, outbox | Không giữ thread chờ lâu |
| Lỗi khi lấy file/row từ source | Poller/source adapter hoặc source transaction | Không trộn với outbound handler retry |
| Broker consumer bị lỗi và cần redelivery | Listener/container/broker transaction/ack | Kiểm tra recovery có nuốt exception không |
| Tác vụ cần sửa tay | DLQ/quarantine, runbook và replay có idempotency | Không retry poison message vô tận |

**Nguyên tắc:** Một luồng có thể cần nhiều lớp, nhưng mỗi lớp phải có **vai trò, ngân sách retry, giới hạn thời gian và cách chuyển lỗi giữa các lớp** được ghi rõ.

## 13. File adapter: retry một handler không phải đọc lại file

File inbound adapter và file outbound adapter có các failure modes riêng: một file có thể chưa được ghi xong, bị khóa, bị đổi tên, đã được xử lý nhưng chưa được ghi nhận, hoặc bị ghi ra một phần khi lỗi.

### 13.1. Inbound file adapter

Một flow thông dụng:

~~~text
Directory
  -> FileReadingMessageSource + poller
  -> Message<File>
  -> transformer/validator
  -> handler [RequestHandlerRetryAdvice nếu gắn ở đây]
  -> downstream service
~~~

Nếu handler thất bại, advice thử lại **bước handler**; không nhất thiết poller sẽ phát lại cùng file trong lần quét kế tiếp. Cần hiểu **file filter, metadata store, trạng thái đã nhận và cách đánh dấu file đã xử lý**.

Một hệ thống dùng accept-once filter chỉ trong bộ nhớ có thể có hành vi khác sau restart so với hệ thống dùng persistent metadata store. Nếu muốn “xử lý ít nhất một lần”, phải thiết kế cách claim/move/đánh dấu file theo trạng thái kết quả, không chỉ tăng maxAttempts.

### 13.2. File outbound adapter và partial output

Giả sử handler ghi một file kết quả nhưng process bị ngắt sau khi ghi một phần. Retry cùng handler mà không kiểm soát tên file có thể:

- Ghi đè file đã hoàn tất.
- Ghi tiếp vào file hỏng.
- Tạo nhiều bản sao với tên khác.
- Khiến consumer downstream đọc file chưa hoàn chỉnh.

Thiết kế an toàn thường gồm:

1. Đặt **business key** hoặc message ID ổn định để suy ra tên file.
2. Ghi tới **đường dẫn tạm** không được consumer đọc.
3. Xác nhận đã ghi đủ và flush/sync theo mức độ cần thiết.
4. Chuyển file sang tên đích hoặc tạo marker hoàn tất theo semantics của filesystem.
5. Nếu retry, phát hiện file đích đã hoàn tất và xử lý idempotent.
6. Ghi audit trạng thái đã giao, không coi việc “có file với tên đó” là bằng chứng file hợp lệ.

**Atomic rename** phụ thuộc filesystem và việc di chuyển có nằm trong cùng filesystem hay không; không mặc định mọi môi trường lưu trữ có cùng đảm bảo.

### 13.3. Khi nào nên retry?

| Lỗi file | Quyết định |
| --- | --- |
| File còn đang được producer ghi và protocol có cơ chế hoàn tất | Chờ ổn định/ready marker trước khi xử lý; retry có thể phù hợp |
| File bị khóa tạm thời | Retry có giới hạn và backoff |
| Đường dẫn output chưa tồn tại do cấu hình sai | Báo cấu hình; không retry mù |
| Permission denied | Thường cần sửa quyền hoặc owner, không lặp vô hạn |
| Output partial hoặc checksum sai | Quarantine/cleanup có kiểm soát, ghi lại từ nguồn xác định |
| Retry sau crash | Dùng metadata bền vững, xử lý lại có idempotency |

## 14. SFTP adapter: retry kết nối và tính toàn vẹn chuyển file

SFTP inbound/outbound adapter dựa trên session tới máy chủ từ xa. Lỗi thường gặp gồm session disconnect, handshake timeout, file chưa hoàn tất, thư mục không tồn tại, authentication failure, quota hoặc lỗi permission ở remote.

### 14.1. Gắn advice vào phần xử lý có chủ đích

~~~text
SFTP inbound synchronization / polling
   -> local message channel
   -> validate file
   -> outbound SFTP handler [retry advice]
   -> publish completion event
~~~

Nếu advice gắn ở **outbound handler**, nó có thể retry thao tác gửi file. Nó **không tự sửa** lỗi của inbound synchronizer khi lấy danh sách file từ máy chủ, và cũng không tự đồng bộ lại những file đã tải về.

### 14.2. Tránh ghi file một phần

Các bước nên có khi remote consumer nhạy cảm với file chưa hoàn tất:

- Dùng tên tạm khi upload nếu adapter/server và hợp đồng với remote cho phép.
- Xác nhận nội dung truyền đủ, checksum/size khi cần.
- Chỉ rename hoặc phát completion marker sau khi upload thành công.
- Dùng filename hoặc idempotency key ổn định theo giao dịch.
- Khi retry sau timeout, kiểm tra remote có file hoàn tất chưa trước khi ghi lại.
- Xử lý file mồ côi, file tạm hoặc file hỏng bằng runbook.

**Một ACK hoặc response bị mất không chứng minh upload thất bại.** Nếu remote đã nhận toàn bộ file, retry có thể tạo duplicate hoặc ghi đè dữ liệu.

### 14.3. Phân loại SFTP errors

| Tình huống | Chính sách |
| --- | --- |
| Session reset/connection timeout tạm thời | Retry và tạo lại session theo client/session factory |
| Máy chủ bảo trì trong khoảng ngắn | Backoff, circuit breaker hoặc durable scheduling |
| Sai credential/host key | Không retry hàng trăm lần; cần sửa cấu hình và bảo mật |
| Không có quyền ghi remote directory | Gửi alert tới owner; không coi là transient |
| File tạm đã tồn tại sau attempt trước | Xác minh nội dung và trạng thái, không ghi đè tự động |
| Server quota/disk full | Có thể cần chờ vận hành; đừng làm nghẽn luồng vô hạn |

Host key verification là một kiểm soát bảo mật, **không được tự tắt chỉ để retry thành công**.

## 15. HTTP outbound gateway: timeout, status và idempotency

HTTP thường cho thấy rõ sự khác biệt giữa **lỗi transport**, **lỗi giao thức** và **lỗi nghiệp vụ**.

### 15.1. Phân loại HTTP

| Kết quả HTTP | Ý nghĩa thường gặp | Retry advice |
| --- | --- | --- |
| **Network timeout / connection reset** | Kết nối thất bại hoặc response không đến | Có thể thử lại nếu request lặp an toàn |
| **429 Too Many Requests** | Rate limit | Cân nhắc `Retry-After` và giới hạn tổng tải |
| **503 Service Unavailable** | Service tạm không sẵn sàng | Retry có giới hạn khi hợp đồng cho phép |
| **500 Internal Server Error** | Remote xử lý lỗi | Không mặc định retry POST không idempotent |
| **400 Bad Request** | Payload không đúng hợp đồng | Sửa validation/schema; thường không retry |
| **401 Unauthorized** | Credential thiếu/hết hạn | Dùng credential refresh đúng cơ chế, không retry mù |
| **403 Forbidden** | Principal thiếu quyền hoặc policy chặn | Khắc phục authorization, không dùng retry để bỏ qua |
| **404 Not Found** | Resource không tồn tại hoặc consistency delay | Tùy hợp đồng; có API cho phép chờ materialization |
| **409 Conflict** | Trạng thái hoặc duplicate | Có thể reconcile thay vì gọi lại |

Trong Spring, HTTP client có thể ném những exception khác nhau cho lỗi kết nối và status lỗi. Retry policy phải được điều chỉnh cho **client implementation và error handler** thực tế, không giả định mọi response 503 đều được chuyển thành cùng exception trên mọi adapter.

### 15.2. Khi HTTP POST không có idempotency

Không nên triển khai:

~~~text
POST /charge-card
  -> timeout
  -> POST /charge-card lần nữa
  -> timeout
  -> POST /charge-card lần nữa
~~~

nếu remote không có cơ chế chống duplicate hoặc xác minh giao dịch. Với thanh toán, vận chuyển, tạo booking và các side effect tương tự, việc xử lý outcome mơ hồ quan trọng hơn việc thêm số attempts.

### 15.3. Mẫu thiết kế an toàn

~~~text
Business command
  -> ghi durable command ID / idempotency key
  -> HTTP outbound gateway + retry lỗi transport có giới hạn
      -> thành công: cập nhật trạng thái
      -> chắc chắn bị từ chối: ghi lỗi nghiệp vụ
      -> outcome không rõ: tra cứu theo command ID hoặc reconcile
  -> chỉ phát completion event khi trạng thái được xác nhận
~~~

**Không đổi idempotency key mỗi attempt.** Nếu key thay đổi, remote có thể coi mỗi lần gọi là một request mới.

### 15.4. Gateway reply và timeout ngân sách

Nếu upstream đang chờ reply, tổng thời gian gồm **gửi request, thời gian remote xử lý, backoff và số attempts**. Một gateway có reply timeout ngắn hơn retry budget có thể tạo trải nghiệm “upstream timeout nhưng remote vẫn xử lý phía sau”. Khi luồng cần chờ lâu, cân nhắc chuyển thành **asynchronous command + completion event/status lookup**.

## 16. JMS: handler retry và broker redelivery

JMS hỗ trợ những mô hình nhận message có acknowledgement và transaction. Spring Integration có JMS inbound channel adapter/gateway và các thành phần outbound phù hợp. **Request-handler advice** không thay thế chính sách **session acknowledgement hoặc listener container**.

### 16.1. Ví dụ luồng

~~~text
JMS queue
  -> JMS message-driven inbound adapter
  -> DirectChannel
  -> business handler [retry advice]
  -> outbound HTTP/DB
~~~

Nếu handler ném exception sau khi retry exhausted, cách JMS message được redeliver phụ thuộc cấu hình **session transaction, acknowledgement, listener container và error handling**. Nếu recovery callback chỉ gửi log rồi trả bình thường, listener có thể coi message đã xử lý.

### 16.2. Mô hình cần quyết định

| Mục tiêu | Thiết kế tương ứng |
| --- | --- |
| Thử nhanh lỗi transient trong cùng lần nhận | Handler retry ngắn + backoff |
| Broker redelivery sau khi lỗi còn tồn tại | Để exception lan đến transaction/listener phù hợp; cấu hình redelivery |
| Cách ly poison message | DLQ/quarantine và giới hạn redelivery count |
| Không mất message khi recovery | Durable failure queue hoặc transaction/confirm phù hợp |
| Tránh duplicate downstream | Idempotent consumer và business key |

Khi dùng **transacted JMS session**, cần hiểu message source và database/HTTP side effects có chung transaction hay không. Một local JMS rollback **không tự rollback** HTTP call đã xảy ra.

### 16.3. Không kết hợp vô hạn

Nếu broker redeliver 20 lần và mỗi redelivery có 5 attempts ở handler, cùng một poison message có thể được xử lý rất nhiều lần, chiếm thread và đè remote service. Nên có:

- Quota attempts ở handler.
- Quota redelivery ở broker.
- Tổng thời gian/age của message.
- Đường DLQ có cảnh báo và replay được kiểm soát.
- Phân loại lỗi vĩnh viễn để đưa vào quarantine sớm.

## 17. AMQP/RabbitMQ: ack/nack, retry và DLQ

AMQP inbound adapter/gateway thường sử dụng listener container với các quy tắc ack, reject, requeue và dead-lettering của broker. Retry advice ở handler chỉ chi phối **bước message handler** tại Spring Integration; ack/nack và DLQ được cấu hình ở lớp nguồn/broker.

### 17.1. Hai hướng sau khi hết retry

**Hướng A — Ném exception:** Handler không thể xử lý, lỗi lan ra container theo cấu hình. Container/broker quyết định requeue, reject, rollback hoặc routing tới DLX/DLQ. Phải đảm bảo requeue không tạo vòng lặp vô hạn.

**Hướng B — Recovery:** Message được ghi vào một durable error path có xác nhận theo thiết kế, rồi luồng hoàn thành. Khi đó container có thể ack message đầu vào; đảm bảo việc ghi lỗi và ack không tạo khoảng trống mất dữ liệu.

### 17.2. Cấu hình kiểm soát cần review

| Thành phần | Câu hỏi |
| --- | --- |
| Inbound container | Auto/manual ack và transaction hoạt động thế nào? |
| Spring Integration advice | Retry đúng handler và exception type chưa? |
| Broker policy | Redelivery count/requeue có giới hạn không? |
| DLX/DLQ | Routing có bền vững, có owner và metric không? |
| Outbound publish | Có publisher confirm/return cần thiết không? |
| Idempotency | Message bị xử lý lại có tạo side effect trùng không? |

**Publisher confirm** giúp biết broker chấp nhận publish theo cơ chế hỗ trợ, nhưng **không chứng minh consumer phía sau đã xử lý nghiệp vụ thành công**. Không dùng confirm làm thay thế end-to-end status.

### 17.3. Khi message có thứ tự quan trọng

Một message bị retry lâu tại consumer có thể chặn các message tiếp theo, còn đẩy nó vào retry queue/DLQ có thể làm thay đổi thứ tự xử lý. Với nghiệp vụ cần ordering, định nghĩa **partitioning key, thứ tự theo aggregate, điều kiện bỏ qua hoặc reordering** rõ ràng thay vì thêm retry vô thời hạn.

## 18. Kafka: offset, consumer retry và DLQ

Spring Integration có các thành phần Kafka inbound/outbound, trong khi Spring Kafka cung cấp listener container, error handling và các mô hình retry riêng. Vì thế cần tách:

1. **Retry ở handler:** `RequestHandlerRetryAdvice` lặp lời gọi một handler trong flow.
2. **Consumer error handling:** Offset/seek/retry/record redelivery được quyết định bởi Kafka listener/container và cấu hình ứng dụng.
3. **Durable retry topic/DLT:** Message lỗi được xuất sang topic riêng để xử lý sau theo design.

### 18.1. Không đồng nhất handler success với offset commit

~~~text
Kafka record
  -> inbound adapter / listener
  -> channel
  -> handler [retry advice]
  -> business side effect
  -> return / error
  -> offset commit theo container/ack mode
~~~

Nếu handler exhausted nhưng recovery callback trả bình thường, container có thể coi record đã xử lý thành công và commit offset theo mode được cấu hình. Nếu chưa có durable recovery record, thao tác nghiệp vụ có thể bị bỏ sót.

### 18.2. Kafka không tự bảo đảm exactly-once cho HTTP

Kafka có những tính năng giao dịch/idempotent producer hỗ trợ bảo đảm trong phạm vi Kafka. Nhưng một handler đọc Kafka rồi gọi REST API bên ngoài **không tự có exactly-once end-to-end**. Vẫn cần idempotency key, outbox hoặc trạng thái nghiệp vụ có thể reconcile.

### 18.3. Retry và thứ tự record

Blocking retry tại handler có thể giữ consumer thread và ảnh hưởng throughput, heartbeat/poll schedule hoặc rebalance khi thời gian xử lý dài hơn cấu hình. Durable retry topic có thể giảm blocking nhưng thường đòi hỏi thiết kế lại **ordering semantics**.

Đối với record có cùng business aggregate ID, nên chọn rõ cách bảo toàn hoặc chấp nhận phá thứ tự; không suy rằng thêm một retry topic vẫn giữ mọi quan hệ trước/sau ban đầu.

### 18.4. Khi nào handler retry phù hợp?

Nó phù hợp cho **lỗi transient ngắn**, ít attempts, tổng thời gian nhỏ hơn budget của consumer. Với lỗi dài hoặc poison messages, nên dùng **cơ chế error handler/retry topic/DLT được hỗ trợ**, thay vì để một record chặn partition liên tục.

## 19. JDBC và cơ sở dữ liệu: retry phải hiểu transaction

Spring Integration có thể dùng JDBC inbound/outbound adapters hoặc các handlers thực hiện SQL. Một số lỗi database có thể transient, nhưng nhiều lỗi là **business/constraint error vĩnh viễn**.

### 19.1. Phân loại JDBC

| Lỗi | Cách xử lý |
| --- | --- |
| Deadlock / serialization conflict | Có thể retry **toàn bộ transaction phù hợp** sau backoff |
| Connection reset / failover | Retry khi kết nối được khôi phục và thao tác lặp an toàn |
| Unique constraint violation | Có thể là duplicate hoặc dữ liệu sai; kiểm tra idempotency |
| Foreign key violation | Thường cần sửa dữ liệu hoặc thứ tự nghiệp vụ |
| SQL syntax error | Sửa code/schema; không retry |
| Permission denied | Sửa quyền/chính sách kết nối; không retry mù |
| Statement timeout sau commit không rõ | Xác minh outcome trước khi ghi lại |

### 19.2. Transaction boundary quan trọng hơn số attempts

Nếu một handler chạy trong transaction:

~~~text
BEGIN
  cập nhật trạng thái đơn hàng
  ghi bản ghi audit
  gọi remote HTTP
COMMIT
~~~

Một lỗi ở remote có thể rollback local database, nhưng **không rollback** side effect của HTTP phía ngoài. Retry toàn handler/transaction có thể lặp lại remote call. Cần chia rõ bước nào transactional, dùng outbox khi giao dịch qua nhiều hệ thống và xác minh remote theo business key.

### 19.3. Polling dữ liệu SQL

Inbound JDBC polling thường đọc các row đủ điều kiện; việc đã “poll” không đồng nghĩa row được xử lý xong. Nếu muốn crash-safe processing, nên thiết kế trạng thái **NEW → CLAIMED → COMPLETED/FAILED**, điều kiện claim theo concurrency và cơ chế sửa trạng thái khi timeout. Handler retry không tự ngăn poller khác chọn lại row.

### 19.4. Idempotent write

Với câu lệnh INSERT/UPDATE, cân nhắc unique business key, conditional update hoặc UPSERT theo database và contract nghiệp vụ. Mục đích là kết quả của lần retry không tạo bản ghi kép hoặc ghi đè dữ liệu mới.

## 20. Message contract, headers và correlation

Retry ở handler nên dựa trên **Message** có hợp đồng rõ. Dữ liệu thường hữu ích:

| Trường/header | Ý nghĩa |
| --- | --- |
| `messageId` | Nhận diện message của framework trong một flow |
| `correlationId` | Liên kết các message của cùng giao dịch |
| `businessKey` | Khóa chống trùng theo nghiệp vụ |
| `sourceSystem` | Nguồn message để điều tra |
| `targetSystem` | Đích và loại adapter |
| `createdAt` / `deadline` | Phục vụ age và timeout budget |
| `schemaVersion` | Xác định contract để validation |
| `recoveryRoute` | Đường xử lý khi exhaustion, nếu thiết kế có |

Đừng giả định `MessageHeaders.ID` luôn ổn định giữa mọi lần redelivery/chuyển đổi message ở tất cả adapters. Với idempotency xuyên broker và restart, nên dùng **business key do hệ thống xác định** hoặc source event ID ổn định.

### 20.1. Bảo vệ message headers

Một header do hệ thống bên ngoài cung cấp **không tự đáng tin** khi nó quyết định đường đến privileged resource, retry budget hoặc idempotency. Cần validate/sanitize ở inbound boundary, giới hạn kích thước headers và tránh phản chiếu token/secret sang error channel.

### 20.2. Không tạo message mới mỗi retry nếu không cần

Retry handler thường lặp cùng message đã nhận. Nếu handler tự sinh ID mới hay timestamp nghiệp vụ mới trong mỗi attempt, remote có thể coi đó là giao dịch mới. Với side effect, idempotency key phải được xác định **trước vòng retry** và giữ nguyên qua các attempts.

## 21. Kiểm thử Retry advice theo các lớp

Một test tốt không chỉ xác nhận “đã gọi handler 4 lần”. Nó phải kiểm tra **lỗi nào được retry, side effect nào không bị lặp, recovery sau exhaustion và hành vi nguồn nhận**.

### 21.1. Ma trận unit/integration tests

| Kịch bản | Kỳ vọng |
| --- | --- |
| Handler thành công ngay | 1 attempt, không backoff |
| Hai lỗi mạng, attempt thứ ba thành công | 3 attempts, đúng reply và metric |
| Lỗi validation/payload schema | Không retry; error path nhận lỗi |
| Lỗi 401/403 | Không retry vô hạn bằng cùng credential |
| Lỗi transient kéo dài hơn maxAttempts | Recovery hoặc exception đúng thiết kế |
| Exception được bọc trong `MessagingException` | Policy phân loại nested cause đúng |
| Handler retry POST sau outcome mơ hồ | Remote idempotency không tạo duplicate |
| Recovery gửi error channel nhưng channel lỗi | Không đánh dấu source thành công khi chưa bảo toàn failure |
| JVM restart khi message đang xử lý | Message được phục hồi/redeliver theo source contract |
| Nhiều consumer nhận trùng business key | Dedup không tạo hai business effects |
| Timeout lớn hơn deadline caller | Không giữ request đồng bộ vô ích |
| Broker redelivery cộng handler retry | Tổng attempts trong giới hạn đã định |

### 21.2. Unit test ý tưởng cho RetryTemplate

Có thể kiểm thử retry policy riêng với một handler giả lập đếm lần gọi:

~~~java
// Ví dụ kiểm thử ý tưởng: cần bổ sung imports và @Test trong dự án.
AtomicInteger attempts = new AtomicInteger();

String result = retryTemplate.execute(context -> {
    int current = attempts.incrementAndGet();
    if (current < 3) {
        throw new ResourceAccessException("temporary disconnect");
    }
    return "ok";
});

assertEquals("ok", result);
assertEquals(3, attempts.get());
~~~

Test này xác minh **RetryTemplate** retry thành công sau hai lỗi; vẫn cần kiểm thử **advice thực sự gắn vào đúng endpoint DSL** và hành vi error channel/ack trong integration tests.

### 21.3. Integration test của HTTP

Sử dụng một HTTP stub server được kiểm soát để trả lỗi network/status theo kịch bản. Xác minh:

1. Lần đầu lỗi transient, các lần sau thành công.
2. Remote nhận cùng idempotency key ở các attempts.
3. POST không tạo nhiều business entities.
4. Retry policy từ chối lỗi không retryable.
5. Khi hết retry, `partnerResponses` không nhận success giả.

Đừng để bài test phụ thuộc dịch vụ đối tác production.

### 21.4. Integration test của broker

Với JMS/AMQP/Kafka, chạy test có listener và broker/container tương ứng:

- Xác minh ack/commit chỉ xảy ra theo chiến lược đã chọn.
- Nếu recovery hoàn tất bình thường, đảm bảo failure record durable trước khi ack.
- Nếu exception được ném để redeliver, kiểm tra redelivery count và DLQ.
- Cho process dừng giữa chừng, kiểm tra khả năng hồi phục.
- Kiểm tra ordering và concurrency với cùng business key.

### 21.5. Kiểm thử race conditions

Khi nhiều instance xử lý cùng một business key, một check kiểu “SELECT xem chưa tồn tại rồi INSERT” **không đủ** nếu không có constraint/lock hoặc transaction phù hợp. Test hai consumer chạy đồng thời và xác minh database/remote idempotency chỉ tạo một kết quả nghiệp vụ.

## 22. Observability: nhận biết retry đang giúp hay đang hại

Retry tốt có thể làm giảm lỗi ngắn hạn; retry sai có thể che sự cố, làm tăng độ trễ và khiến remote quá tải. Cần quan sát cả **tỷ lệ recovery** lẫn **tác động chi phí**.

### 22.1. Những metric nên có

| Metric | Ý nghĩa |
| --- | --- |
| `handler_attempts_total` | Số lần thực thi handler, phân loại theo component/result |
| `handler_retries_total` | Số lần thử lại ngoài attempt đầu |
| `retry_exhausted_total` | Số message không thành công sau quota |
| `retry_recovered_total` | Số lần thành công sau ít nhất một retry |
| `retry_backoff_duration` | Thời gian thread chờ giữa attempts |
| `handler_latency` | Tổng thời gian xử lý message gồm retry |
| `downstream_timeout_total` | Timeout theo hệ thống đích |
| `dlq_depth` / `quarantine_age` | Khối lượng và tuổi của tác vụ chưa xử lý |
| `duplicate_prevented_total` | Số yêu cầu lặp được dedup xác nhận |
| `consumer_lag` / `poller_delay` | Ảnh hưởng retry đến throughput nguồn |

Tên metric là **gợi ý đặt tên**, không mặc nhiên do Spring Integration tạo sẵn. Một số phiên bản tích hợp Micrometer/Observation có metrics khác; có thể bổ sung instrumentation có kiểm soát.

### 22.2. Cardinality và dữ liệu nhạy cảm

Không dùng `messageId`, `businessKey`, URL đầy đủ, username hoặc token làm **metric label** có cardinality cao. Có thể đưa vào trace/log có quyền xem phù hợp, còn metric labels nên dùng tên flow, endpoint, loại lỗi, adapter type và trạng thái kết quả.

### 22.3. Những tín hiệu cần cảnh báo

- Tỷ lệ retry tăng đột biến trên một outbound endpoint.
- Retry exhausted tăng đồng thời với lỗi timeout ở remote.
- Handler latency vượt deadline của gateway.
- Thread pool, JMS listener, Kafka consumer bị giữ quá lâu.
- DLQ tăng mà không có owner xử lý.
- Cùng business key liên tục được replay.
- Lỗi auth/permission bị retry vô hạn (dấu hiệu policy sai).
- Retry success cao nhưng duplicate business effect cũng tăng (dấu hiệu thiếu idempotency).

## 23. Runbook: khi retry exhausted

Một hệ thống đáng tin cậy cần kế hoạch **sau khi retry không còn hữu ích**.

### 23.1. Quy trình vận hành

1. **Xác định nguồn và đích:** Flow ID, adapter, source message key, target, correlation ID.
2. **Phân loại lỗi:** Transient, permanent, ambiguous hoặc upstream downstream outage.
3. **Xem retry policy đang áp:** N attempts, backoff, deadline, recovery callback và container redelivery.
4. **Kiểm tra trạng thái remote:** Nếu là thao tác có side effect, xác minh giao dịch đã thực hiện chưa.
5. **Kiểm tra durability:** Message nằm trong broker, DLQ, durable table, quarantine hay đã bị ack?
6. **Giảm tải:** Nếu remote đang quá tải, điều chỉnh concurrency/circuit breaker theo change policy thay vì tăng retry đồng loạt.
7. **Khắc phục căn nguyên:** Network, credential, schema, service state hoặc deadlock.
8. **Replay an toàn:** Dùng business key/idempotency, giới hạn đợt replay, lưu actor và approval.
9. **Xác minh:** Có kết quả nghiệp vụ đúng, không tạo duplicate và không còn message mắc kẹt.
10. **Đóng sự cố:** Ghi bằng chứng, thời gian và biện pháp tránh lặp.

### 23.2. Trạng thái xử lý lỗi

~~~text
RECEIVED       Source message đã được nhận
PROCESSING     Handler đang thực thi
RETRYING       Đang thử lại theo budget
EXHAUSTED      Không còn attempts hoặc lỗi không retryable
RECOVERY       Đang đưa vào durable recovery / error handling
QUARANTINED    Message đã được cách ly chờ xử lý
REPLAYING      Đang xử lý lại có kiểm soát
SUCCEEDED      Side effect/reply được xác nhận
FAILED         Không xử lý được, có owner và nguyên nhân
~~~

Các trạng thái là **đề xuất nghiệp vụ**, không phải enum Spring Integration mặc định. Với retry message có side effect, phải ghi nhận **xác thực kết quả tại remote** trước khi đặt trạng thái SUCCEEDED.

### 23.3. Replay không phải gửi lại vô điều kiện

Trước khi replay một lô message trong DLQ:

- Kiểm tra đã sửa nguyên nhân chưa.
- Xác định hệ thống đích có thực hiện một phần trước lỗi không.
- Đảm bảo business key/idempotency còn phù hợp sau thời gian dài.
- Chia batch nhỏ và giới hạn concurrency.
- Theo dõi downstream và có điểm dừng.
- Lưu người thực thi, thời gian, kết quả, những message được loại bỏ trùng.

## 24. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Retry mọi exception | Lỗi dữ liệu/permission bị lặp vô ích | Classify transient/permanent/ambiguous |
| MaxAttempts rất lớn trong gateway đồng bộ | Caller timeout, thread bị giữ | Giới hạn retry budget và deadline |
| Retry POST không idempotency | Tạo hai order, shipment hoặc charge | Business key/remote idempotency và reconciliation |
| Backoff bằng 0 khi remote quá tải | Retry storm làm lỗi trầm trọng hơn | Exponential backoff, jitter, rate limit |
| Bật retry ở client, handler và broker không có ngân sách | Số lần gọi nhân lên | Chỉ định tầng chịu trách nhiệm và tổng budget |
| Recovery chỉ log rồi return | Message có thể bị ack dù chưa xử lý | Durable recovery hoặc propagate exception |
| Gắn advice vào handler nhưng tưởng poller sẽ retry | Source file/record không được xử lý lại | Thiết kế source filter, transaction hoặc redelivery |
| Tin errorChannel tự có DLQ | Lỗi gửi sang channel nhưng không bền vững | Durable recovery, kiểm tra subscriber và ack |
| Dùng Message ID thay business key trong mọi hệ thống | ID thay sau redelivery, duplicate vẫn xảy ra | Khóa nghiệp vụ ổn định |
| Không giới hạn concurrency khi retry | Nhiều threads chờ, giảm throughput | Pool sizing, bulkhead, circuit breaker |
| Retry sai HTTP 401/403 | Làm ngập IdP/remote và che lỗi quyền | Refresh credential đúng cơ chế hoặc sửa authorization |
| Retry tất cả SQL errors | Lặp lỗi schema/constraint vô hạn | Retry lỗi transient, transaction/idempotency |
| SFTP retry ghi đè file đã hoàn tất | Hỏng dữ liệu hoặc duplicate | Temporary name, verify, atomic publish khi hỗ trợ |
| Consumer commit offset sau recovery chưa durable | Mất Kafka/JMS/AMQP message | Kiểm tra ack/commit và transactional failure routing |
| DLQ không có owner/metric | Lỗi bị tích tụ mà không ai xử lý | Runbook, alert, replay có audit |
| Chỉ test số attempts | Không phát hiện duplicate, ack sai hoặc lỗi sau restart | Integration test side effect và crash recovery |

## 25. Tình huống xuyên suốt: đơn hàng từ JMS đến HTTP và database

Một doanh nghiệp nhận các lệnh đặt hàng từ JMS, kiểm tra hợp đồng message, gọi hệ thống đối tác qua HTTP, sau đó lưu trạng thái ở JDBC. Luồng Spring Integration:

~~~mermaid
flowchart LR
    Q["JMS Queue"] --> IN["Inbound JMS Adapter"]
    IN --> VAL["Validate + business key"]
    VAL --> H["HTTP outbound gateway<br/>RequestHandlerRetryAdvice"]
    H --> DB["JDBC update / outbox"]
    H -.-> DLQ["Durable recovery"]
    DB --> DONE["Completion event"]
~~~

### 25.1. Hợp đồng message

~~~json
{
  "commandId": "cmd-order-8201",
  "orderId": "order-8201",
  "customerId": "customer-291",
  "operation": "CREATE_SHIPMENT",
  "schemaVersion": 2,
  "correlationId": "corr-9711"
}
~~~

**commandId** là khóa idempotency phải ổn định qua retry và redelivery. Không truyền payload nhạy cảm không cần thiết vào log và DLQ mở rộng quyền xem.

### 25.2. Thiết kế retry

| Bước | Retry? | Vì sao |
| --- | --- | --- |
| Validate schema | Không với lỗi schema cố định | Retry không làm payload đúng hơn |
| HTTP connect timeout | Có, giới hạn số attempts | Có thể transient; phải có idempotency ở remote |
| HTTP 401/403 | Không retry cùng credential | Cần sửa auth/permission |
| HTTP 503 | Có nếu contract cho phép, backoff | Remote có thể đang quá tải |
| JDBC deadlock | Có thể retry transaction phù hợp | Deadlock có tính transient |
| JDBC unique violation | Kiểm tra duplicate và trạng thái | Có thể là command đã xử lý |
| Remote outcome không xác định | Query trạng thái hoặc reconcile | Không gửi request mới vô điều kiện |

### 25.3. Chặng lỗi thực tế

Attempt 1 gửi HTTP POST; remote tạo shipment nhưng response bị mất. Attempt 2 gửi lại với cùng idempotency key `cmd-order-8201`; remote trả kết quả đã tạo. JDBC ghi trạng thái một lần theo unique key. Sau đó outbound completion event được tạo theo mô hình outbox hoặc cơ chế có bảo đảm tương ứng.

Nếu remote **không hỗ trợ idempotency**, hệ thống phải có quy trình truy vấn trạng thái theo `commandId`/tài nguyên nghiệp vụ hoặc chuyển kết quả chưa rõ sang reconciliation; không nên bật blind retry POST.

### 25.4. Khi tất cả attempts đều thất bại

Nếu `RetryTemplate` exhausted:

1. Handler ném lỗi cho JMS container theo transactional/redelivery design; **hoặc**
2. Recovery lưu command vào durable failure store/queue có bảo đảm rồi kết thúc xử lý nguồn.

Phải chọn một đường rõ ràng. Không vừa ack source vừa chỉ ghi error vào memory-only channel. Khi replay sau khi partner phục hồi, message vẫn mang **cùng commandId**, tránh tạo shipment mới.

### 25.5. Các trường hợp cần test

- HTTP thành công lần đầu.
- Timeout một lần rồi thành công.
- Remote đã tạo shipment, response bị mất, retry không tạo duplicate.
- Payload sai schema đi thẳng quarantine.
- JMS redelivery sau application crash.
- JDBC deadlock sau HTTP success: không tạo thêm shipment.
- Recovery channel hoặc DLQ tạm thời không dùng được.
- Nhiều consumer nhận cùng commandId.
- Replay lô DLQ sau sự cố partner và xác minh không mất/không trùng.

## 26. Checklist thiết kế Retry advice cho request handler

1. **Đúng vị trí:** Advice gắn vào handler/endpoint cần thử lại; không nhầm với poller hoặc broker retry.
2. **Đúng loại lỗi:** Có whitelist transient, phân biệt permanent và ambiguous outcome.
3. **Đúng attempts:** MaxAttempts bao gồm lần đầu; không nhân retry budget qua nhiều tầng.
4. **Đúng backoff:** Chọn exponential/fixed và jitter theo tải, không retry storm.
5. **Đúng timeout:** Tổng attempts và thời gian chờ nằm trong deadline/SLA hợp lý.
6. **Đúng message:** Có business key, correlation ID, schema và nguồn/tài nguyên rõ.
7. **Đúng idempotency:** Side effect lặp an toàn, đặc biệt HTTP POST, file upload, DB write.
8. **Đúng transaction:** Biết ranh giới database, broker, API ngoài và khả năng rollback.
9. **Đúng acknowledgement:** Recovery callback có thể làm source ack; cần kiểm tra thực tế.
10. **Đúng recovery:** Sau exhaustion có durable route, caller error hoặc DLQ có owner; không nuốt lỗi.
11. **Đúng adapter:** Hiểu file filter, SFTP partial file, HTTP status, JMS/AMQP redelivery, Kafka offset, JDBC transaction.
12. **Đúng channel:** Xác định đồng bộ/bất đồng bộ và nơi exception có thể lan tới.
13. **Đúng observability:** Theo dõi attempts, exhausted, recovered, latency, consumer lag và DLQ.
14. **Đúng bảo mật:** Không retry vô hạn lỗi auth; không log credential/payload nhạy cảm.
15. **Đúng kiểm thử:** Unit + integration + crash/restart + duplicate + negative cases.
16. **Đúng runbook:** Có cách xác minh outcome, replay, giới hạn tải và đóng sự cố.

## 27. Bài tập và câu hỏi tự kiểm tra

### Bài 1. MaxAttempts là bao nhiêu lần retry?

**Tình huống:** `SimpleRetryPolicy` được đặt tối đa 4 attempts. Một lập trình viên nói sẽ có 4 lần retry ngoài lần gọi đầu.

**Đáp án:** Không đúng. Thông thường có **4 lần gọi handler tổng cộng**, gồm 1 lần đầu và tối đa 3 lần thử lại.

### Bài 2. Advice nào xử lý lỗi file inbound polling?

**Tình huống:** File inbound poller không lấy được file từ remote vì lỗi session. Đội kỹ thuật chỉ gắn `RequestHandlerRetryAdvice` vào HTTP outbound handler ở phía cuối flow.

**Đáp án:** Advice ở HTTP handler **không giải quyết lỗi poll source**. Cần cấu hình/điều tra inbound poller, session reconnect, filter và nguồn redelivery tương ứng.

### Bài 3. Vì sao ErrorMessageSendingRecoverer có thể nguy hiểm?

**Tình huống:** Handler JMS exhausted; recoverer gửi lỗi tới một channel và trả về bình thường, nhưng channel không được lưu bền vững.

**Đáp án:** Listener có thể ack message nguồn theo cấu hình vì handler đã kết thúc bình thường, trong khi tác vụ nghiệp vụ chưa thành công và failure record có thể bị mất. Cần durable recovery và xác minh ack, hoặc để lỗi propagate nhằm redelivery theo policy.

### Bài 4. HTTP POST timeout có nên retry?

**Tình huống:** Một dịch vụ thanh toán trả connect/response timeout sau khi lệnh được gửi. Không có idempotency key hoặc API tra cứu trạng thái.

**Đáp án:** Không nên blind retry side effect. Phải xác minh hợp đồng API, trạng thái remote hoặc bổ sung idempotency trước khi thiết kế retry tự động.

### Bài 5. Kafka offset và handler retry

**Tình huống:** Handler dùng `RequestHandlerRetryAdvice`, hết 5 attempts rồi recovery return bình thường. Developer khẳng định Kafka chắc chắn sẽ redeliver record.

**Đáp án:** Không thể khẳng định. Commit/ack phụ thuộc listener/container và error handling. Nếu handler hoàn tất bình thường, offset có thể được commit theo cấu hình, khiến record không được phát lại. Cần integration test đúng mode.

### Bài 6. Duplicate do retry chồng nhau

**Tình huống:** HTTP client retry, handler retry và broker redelivery đều được bật, nhưng hệ thống chỉ ghi “max retries = 3” trong tài liệu.

**Đáp án:** Mô tả chưa đủ; tổng số lần chạm remote có thể tăng nhiều lần. Cần lập retry budget toàn luồng, chỉ định tầng chịu trách nhiệm, timeout và cơ chế dedup/recovery.

### Bài 7. JDBC deadlock và HTTP side effect

**Tình huống:** Handler gọi HTTP tạo đơn vận chuyển rồi ghi JDBC; JDBC deadlock nên retry toàn handler.

**Đáp án:** Nếu HTTP đã tạo đơn, retry toàn handler có thể tạo đơn thứ hai. Cần idempotency phía HTTP và transaction/reconciliation thích hợp; chỉ retry phần transaction thực sự an toàn hoặc dùng outbox/state machine.

### Bài 8. Retry chỉ còn lỗi 403

**Tình huống:** API từ chối 403 do thiếu permission; hệ thống đang exponential retry 20 lần.

**Đáp án:** Đây thường là lỗi authorization, tăng attempts không giải quyết. Chuyển sang error flow, kiểm tra principal/role/scope và cảnh báo IAM owner; không dùng retry như cách vượt quyền.

## 28. Tổng kết

**`RequestHandlerRetryAdvice`** cho phép Spring Integration thử lại **lời gọi message handler** theo chính sách của **`RetryTemplate`**, giúp xử lý những lỗi transient ngắn như mất kết nối hoặc remote tạm quá tải. Một cấu hình hữu ích phải xác định **exception có thể retry, số attempts, backoff, timeout và hành vi khi exhausted**, chứ không chỉ bật retry.

Trong module **Spring Integration Adapters**, mỗi giao thức có ranh giới riêng: **file/SFTP** cần chống partial output và duplicate; **HTTP** cần idempotency cho side effect; **JMS/AMQP/Kafka** cần phối hợp ack, redelivery và DLQ; **JDBC** cần hiểu transaction/constraint. Retry ở handler **không thay thế** poller retry, broker redelivery, source durability, error channel hay recovery có xác nhận.

Một luồng đáng tin cậy được đánh giá bằng **kết quả nghiệp vụ đúng**: message không bị mất, thao tác không bị nhân đôi ngoài dự kiến, tác vụ thất bại có nơi lưu/owner, retry không gây quá tải và có thể truy vết qua log, metric, test cùng runbook. Đó mới là mục tiêu của **retry advice cho request handler** trong hệ thống tích hợp thực tế.
