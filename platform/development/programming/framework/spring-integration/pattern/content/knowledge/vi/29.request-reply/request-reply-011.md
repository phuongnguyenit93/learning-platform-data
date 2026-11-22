# Request-reply qua hệ thống bất đồng bộ

> **Chương:** Request reply  
> **Module:** `SPRING_INTEGRATION_PATTERN` — học triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng. Thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử, theo dõi các nhánh xử lý. Bài này tập trung vào **thiết kế request–reply khi request và kết quả đi qua queue, topic, executor hoặc hệ thống phân tán**, nơi bên gửi, bên xử lý và bên nhận reply có thể hoạt động ở thời điểm khác nhau.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao **request–reply là một hợp đồng giao tiếp**, không đòi hỏi transport phải đồng bộ.
2. Phân biệt **xử lý bất đồng bộ bên trong nhưng caller vẫn đợi reply** với **giao thức bất đồng bộ từ đầu đến cuối** (accepted → later result).
3. Thiết kế request envelope gồm `requestId`, `operationId`, `correlationId`, `replyTo`, `deadline`, `schemaVersion` và source identity, đồng thời xác định **trường nào do bên tin cậy cấp**.
4. Xây đường request queue → worker → reply queue/topic → caller/registry; xử lý nhiều requests đang chờ cùng lúc mà không trộn replies.
5. Chọn Gateway, Service Activator, channel, message adapter và reply correlation thích hợp trong Spring Integration; hiểu giới hạn của local temporary `replyChannel` so với remote broker.
6. Tách **ACK**, **đã tiếp nhận**, **đã xử lý**, **đã commit** và **đã giao reply** thành các sự kiện khác nhau.
7. Đặt timeout/deadline, pending state, late/duplicate replies, backpressure, retry, DLQ và reconciliation mà không tạo side effect trùng.
8. Viết Java 17 và Spring Integration Java DSL minh họa async handler, reply result có kiểu, cùng các unit/integration tests và test matrix production.
9. Kết hợp correlation của request–reply với Splitter/Aggregator, Router, Filter, error channel và idempotent receiver khi workflow phức tạp.

## 2. Tình huống: lệnh giữ hàng đi qua queue, reply đến sau

Ứng dụng Order Service gửi lệnh:

~~~json
{
  "tenantId": "shop-a",
  "operationId": "RSV-901",
  "requestId": "req-7f31",
  "orderId": "ORD-901",
  "sku": "BOOK-42",
  "quantity": 2
}
~~~

Inventory Worker xử lý request, có thể cần gọi database/warehouse hoặc đợi hàng trăm milliseconds đến vài giây. Sau khi có kết quả nghiệp vụ, Worker gửi:

~~~json
{
  "requestId": "req-7f31",
  "operationId": "RSV-901",
  "orderId": "ORD-901",
  "status": "RESERVED",
  "reasonCode": null
}
~~~

Nếu request và reply đi qua một broker, **không có stack frame Java chạy xuyên suốt hai services**. Order Service phải biết reply `req-7f31` thuộc **lượt yêu cầu nào**, có đang còn chờ hay không, và kết quả `RESERVED` có tương ứng với **operation** đã yêu cầu hay không.

~~~mermaid
sequenceDiagram
    participant C as Order Service
    participant RQ as Request queue
    participant W as Inventory Worker
    participant DB as Inventory DB
    participant RP as Reply queue
    C->>C: Register pending(req-7f31)
    C->>RQ: ReserveCommand + correlation/replyTo
    RQ-->>C: Broker accepted (not business success)
    RQ->>W: Deliver request
    W->>DB: Reserve with operationId=RSV-901
    DB-->>W: Committed result
    W->>RP: ReserveReply(req-7f31, RESERVED)
    RP->>C: Deliver reply
    C->>C: Match pending + validate + complete
~~~

### 2.1. Tại sao reply không tự quay về nơi đã gửi?

Một HTTP call cùng TCP connection thường có response path rõ. Nhưng queue/topic chỉ biết **message được publish vào destination nào**. Nó không tự biết JVM/process nào đang giữ lời gọi Java chờ.

Cần một trong những cách sau:

- `replyTo` hoặc reply destination có kiểm soát để biết **gửi response đi đâu**.
- `requestId`/correlation key để biết **reply thuộc request nào**.
- Pending registry hoặc một workflow state store để nối reply tới caller/trạng thái đã lưu.
- Timeout/expiration policy nếu reply không đến hoặc đến muộn.

### 2.2. Nhận request vào queue không đồng nghĩa giữ hàng thành công

~~~text
Publisher send success
    != Consumer received
    != Handler completed
    != DB transaction committed
    != Reply published
    != Caller received reply
~~~

Không có bước nào mặc nhiên suy ra tất cả bước sau đã xảy ra. Đây là lý do một kết quả `ACCEPTED` có thể hợp lý hơn `RESERVED` khi hệ thống mới chỉ enqueue yêu cầu.

## 3. Hai mô hình “bất đồng bộ” cần phân biệt

### 3.1. Async bên trong, caller vẫn gọi request–reply

~~~text
Java caller: ReserveReply reply = gateway.reserve(command);
        | blocks/waits
        v
Messaging Gateway -> ExecutorChannel / broker
                              |
                              v
                         Worker handles
                              |
                              v
                         Reply to Gateway
        |
        v
Java caller receives ReserveReply
~~~

Worker có thể chạy thread/process khác, nhưng caller vẫn chờ đến khi nhận reply hoặc hết timeout. Một `@MessagingGateway` trả POJO là ví dụ dễ hiểu.

**Ưu điểm:** API đơn giản cho caller, tương thích với logic đồng bộ.  
**Đổi lại:** caller chiếm tài nguyên trong lúc chờ; timeout, late reply và concurrency giới hạn khả năng mở rộng.

### 3.2. Async end-to-end: nhận việc trước, kết quả sau

~~~text
POST /reservations
  -> validate/auth + enqueue
  <- HTTP 202 Accepted + operationId

Later:
  Worker commits / rejects reservation
  -> publishes ReservationOutcome

Caller:
  GET /reservations/{operationId}
  or receives webhook / subscription result
~~~

Ở đây không cần giữ thread HTTP/Gateway chờ toàn bộ tác vụ. Kết quả được truy xuất qua **status API**, subscription, webhook hoặc event topic.

**Ưu điểm:** hợp với tác vụ lâu, cần bền qua restart, giảm số request chờ.  
**Đổi lại:** phải quản lý lifecycle của operation, version, retry của callback/status, auth và reconciliation.

### 3.3. Không gọi cả hai là “fire-and-forget”

| Mô hình | Có reply nghiệp vụ? | Caller chờ? | Điều cần thiết |
| --- | --- | --- | --- |
| Request–reply trực tiếp | Có | Thường có | Reply destination và timeout |
| Async worker, sync Gateway | Có | Có, tối đa deadline | Correlation, bounded waiting |
| Async end-to-end | Có, tới sau | Không cần block | Operation status / callback / event |
| One-way event/command | Không theo contract của tương tác đó | Không | Không suy thành công nghiệp vụ từ send |
| Scatter-Gather | Có thể reply tổng | Tùy interface | Group correlation, release policy |

“Async” là đặc tính **lịch thực thi**; “reply” là đặc tính **giao thức**. Một request–reply có thể hoàn toàn dựa trên messaging bất đồng bộ.

## 4. Anatomy của request và reply envelopes

Bên cạnh payload nghiệp vụ, một hệ phân tán thường cần envelope rõ ràng.

~~~text
RequestEnvelope
  requestId                req-7f31
  operationId              RSV-901
  businessCorrelationId    ORD-901
  tenantId                 shop-a
  producerId               order-service
  schemaVersion            reserve-command-v1
  replyTo                  inventory.replies.order-service
  deadlineAt               2026-11-21T08:00:15Z
  payload                  ReserveCommand(...)

ReplyEnvelope
  correlationId            req-7f31
  operationId              RSV-901
  tenantId                 shop-a
  producerId               inventory-service
  schemaVersion            reserve-reply-v1
  status                   RESERVED / REJECTED / UNKNOWN
  payload                  ReserveReply(...)
~~~

### 4.1. Ý nghĩa từng key

| Field | Dùng để | Lưu ý |
| --- | --- | --- |
| `requestId` | Nhận diện **một lần trao đổi request–reply** | Có thể mới cho lần gọi API mới |
| Reply `correlationId` | Liên kết reply về đúng request | Ở ví dụ bằng `requestId` |
| `operationId` | Idempotency của **một mutation nghiệp vụ** | Phải bền qua retry cùng command |
| `businessCorrelationId` | Trace nhiều bước cùng một order/case | Có thể bao trùm nhiều operations |
| `executionId` | Gom child replies của một workflow run | Quan trọng với Aggregator |
| `tenantId` | Namespace và authorization scope | Phải xác minh, không tin string tự khai |
| `producerId` | Nguồn phát có xác thực | Từ transport identity/registry đáng tin |
| `replyTo` | Reply destination | Không nhận queue/topic tùy ý từ bên ngoài |
| `deadlineAt` | Hạn của exchange | Không tự là transactional cancellation |
| `schemaVersion` | Chọn decoder/contract | Tách request và reply versions |
| Transport message ID/offset | Thông tin delivery | Không phải operation idempotency key |

### 4.2. RequestId có được đổi khi retry không?

Phụ thuộc retry đang xảy ra ở mức nào:

- **Broker redelivery cùng request**: thường giữ `requestId` và `operationId`, còn delivery metadata/offset có thể thay đổi.
- **Caller mở một exchange mới sau timeout**: có thể tạo `requestId` mới cho pending wait mới, **nhưng phải giữ `operationId`** nếu vẫn là cùng business command.
- **Một lệnh nghiệp vụ hoàn toàn mới**: cần `operationId` mới và phải có intent rõ.

Không gộp cả ba thành một `UUID.randomUUID()` tạo trong mỗi lần Handler được invoke.

### 4.3. Header và payload phải thống nhất

Nếu `payload.operationId=RSV-901` nhưng `header.operationId=RSV-902`, không tùy tiện chọn một để xử lý. Định nghĩa authority của field, verify nguồn, rồi reject `OPERATION_ID_CONFLICT` hoặc áp chính sách đã kiểm.

Một reply chỉ cần `correlationId` trùng **chưa đủ** để được chấp nhận. Phải so tenant, expected operation, producer identity, schema/status hợp lệ và quyền đọc kết quả.

## 5. Các trạng thái: không nhầm lệnh đã nhận với lệnh đã hoàn tất

Một state machine rõ tránh trường hợp caller timeout rồi suy “chắc chưa xử lý”.

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> PENDING: validate + register/persist
    PENDING --> DISPATCHED: publish request
    DISPATCHED --> PROCESSING: worker accepted
    PROCESSING --> COMPLETED: business commit + outcome
    PROCESSING --> REJECTED: terminal business decision
    DISPATCHED --> TIMED_OUT: wait deadline exceeded
    PROCESSING --> TIMED_OUT: wait deadline exceeded
    TIMED_OUT --> COMPLETED: late successful outcome
    TIMED_OUT --> REJECTED: late business rejection
    PENDING --> FAILED_DISPATCH: publish failed
    COMPLETED --> [*]
    REJECTED --> [*]
    FAILED_DISPATCH --> [*]
~~~

**Sơ đồ mang tính khái niệm:** `TIMED_OUT` có thể chỉ là trạng thái **exchange đang chờ**, không phải trạng thái cuối của operation. Trong production thường nên tách rõ:

- **Exchange/wait state:** `WAITING`, `TIMED_OUT`, `DELIVERED`.
- **Business operation state:** `RECEIVED`, `PROCESSING`, `COMPLETED`, `REJECTED`, `UNKNOWN`.

Một reply đến muộn có thể cập nhật **business operation** thành `COMPLETED` dù HTTP request ban đầu đã timeout. Nếu gom cả hai state vào một enum và khóa `TIMED_OUT` như “business FAILED”, sẽ gây sai reconciliation.

### 5.1. Trạng thái nghiệp vụ UNKNOWN

`UNKNOWN` hữu ích khi request có thể đã commit nhưng caller/broker chưa nhận được bằng chứng. Không tự biến mọi timeout thành `REJECTED` hoặc tự retry bằng operation ID mới.

### 5.2. Terminal rejection khác retryable technical error

| Trạng thái/lỗi | Có retry cùng business command? | Hành động |
| --- | --- | --- |
| `REJECTED: INVALID_QUANTITY` | Không với cùng dữ liệu | Sửa input hoặc trả lỗi người dùng |
| `REJECTED: UNAUTHORIZED` | Không để bypass security | Xác minh quyền |
| `COMPLETED: RESERVED` | Không thực hiện effect thêm | Return persisted outcome |
| `UNKNOWN after timeout` | Có thể tra status/retry cùng key | Reconcile trước side effect |
| Broker unavailable | Retry bounded khi bảo đảm publish status | Backoff + monitoring |
| Worker crash after commit | Redelivery cùng operation key | Idempotent receiver |
| Reply queue unavailable | Retry publish result, không reserve lại | Outbox/reply repair |

## 6. Correlation: ghép reply đúng với request

Khi có 10.000 requests đang chờ, replies có thể đến **khác thứ tự**:

~~~text
Request order:  A, B, C, D
Reply order:    D, B, A, C
~~~

Nếu listener chỉ dùng một QueueChannel chung rồi đưa “reply đầu tiên” cho “caller đầu tiên”, sẽ trả nhầm dữ liệu. Correlation phải là ánh xạ rõ:

~~~text
pending[req-A] -> waiting caller A
pending[req-B] -> waiting caller B
pending[req-C] -> waiting caller C
pending[req-D] -> waiting caller D

reply(correlationId=req-D) -> complete only pending[req-D]
~~~

### 6.1. Correlation ID duy nhất trong phạm vi nào?

Một `requestId` dạng UUID đủ entropy có thể gần như unique trong toàn hệ thống, nhưng logic an toàn vẫn phải ràng buộc:

~~~text
(tenantId, requester/service namespace, requestId)
~~~

Không cho một tenant đọc reply của tenant khác chỉ vì biết `requestId`. Nếu có nhiều app instances cùng nghe reply topic, phải bảo đảm **reply đi đến instance đang giữ waiter** hoặc dùng **shared state** để complete exchange chính xác.

### 6.2. Khi nào cần reply-to?

Qua broker, Worker thường không biết caller hiện đang chạy ở đâu. `replyTo` có thể là:

- Queue được cấp/allowlist cho caller service.
- Topic chung với một partition/routing key theo tenant/service.
- Temporary reply queue do adapter quản lý với lifecycle rõ.
- Không có replyTo nếu protocol dùng **một result topic mặc định** được cả hai phía biết.

**Cảnh báo security:** không lấy `replyTo` từ untrusted JSON/HTTP header rồi gửi sensitive results đến một địa chỉ tùy ý. Nên có producer identity → allowed reply destinations registry, IAM/ACL và validation.

### 6.3. Request correlation qua JMS/AMQP/Kafka

| Transport | Công cụ giao thức | Không nên nhầm |
| --- | --- | --- |
| JMS | `JMSReplyTo`, `JMSCorrelationID`, `JMSMessageID` | Message ID không tự là business operation ID |
| AMQP | reply-to/correlationId properties, reply queues, broker acks | ACK không phải business outcome |
| Kafka | request/reply topics, record headers/key, partition/offset | Offset không ổn định qua retry topic |
| HTTP async | operation resource, webhook/polling | HTTP 202 không phải hoàn tất |
| Spring in-JVM | `replyChannel` header/temporary channel | Java channel object không serialize qua broker |

Không có ánh xạ 1:1 tự động giữa mọi protocol. Khi dùng outbound/inbound Gateway hoặc adapter của Spring Integration, phải xác định **header mapper**, serializer, response channel và version tương ứng.

## 7. Timeout, deadline và late replies

Một request–reply qua async worker nên có ít nhất ba giới hạn:

1. **Send/publish timeout:** không thể gửi request vào channel/broker đúng hạn.
2. **Reply wait timeout:** caller/Gateway không nhận reply trong khoảng chờ.
3. **Business operation deadline:** sau thời điểm này, nghiệp vụ có thể không còn muốn thực hiện **nếu chưa commit**.

Các giới hạn này **không giống nhau**. Một Gateway có `defaultReplyTimeout=3s` không tự gửi cancel tới worker sau 3 giây.

### 7.1. Timeline có reply đến muộn

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant W as Worker
    participant DB as DB
    C->>G: reserve(RSV-901)
    G->>W: request(req-7f31)
    Note over G: Wait up to 3s
    G-->>C: Timeout at 3s
    W->>DB: Commit at 5s
    DB-->>W: RESERVED
    W-->>G: Reply at 6s
    Note over G: Original waiter gone
~~~

**Không được tự kết luận:** timeout của caller nghĩa là worker đã dừng, request đã bị hủy hoặc stock chưa bị trừ.

### 7.2. Deadline propagation

Một envelope có `deadlineAt` giúp Worker quyết định có **được phép bắt đầu** hay cần từ chối khi đã quá hạn. Nhưng giữa check deadline và commit luôn có race; nếu yêu cầu hủy chắc chắn, phải có cơ chế transaction/state machine/cancellation rõ tại business owner.

Không dựa vào wall clock của một máy khi services có clock skew đáng kể. Định nghĩa UTC instant, đồng bộ đồng hồ, và margin/authority cho deadline ở các boundary.

### 7.3. Bốn chính sách xử lý late reply

| Chính sách | Khi dùng | Cảnh báo |
| --- | --- | --- |
| **Ignore for expired waiter** | Caller cũ đã đóng, không cần unblock | Vẫn cập nhật status operation nếu có commit |
| **Persist outcome** | Hỗ trợ polling/reconciliation | Auth và retention phù hợp |
| **Notify via callback/event** | Async end-to-end | Delivery/retry/duplicate callback |
| **Compensate** | Business cho phép đảo ngược effect | Không phải mọi effect có thể hoàn tác |

Không phản hồi late reply cho **request mới** chỉ vì hai message có cùng `orderId`. Phải so `requestId`/operation identity và quyền.


## 8. Spring Integration: async worker nhưng Gateway vẫn trả kết quả

Đây là ví dụ **bất đồng bộ ở bên trong một JVM**, nhằm học rõ cách Message Gateway tiếp tục request–reply khi handler chạy trên executor thread. Nó **không** thay thế broker queue durable và không bảo vệ trạng thái pending qua process restart.

### 8.1. DTO request và reply bằng Java 17

~~~java
import java.util.Objects;

record ReserveCommand(
    String tenantId,
    String requestId,
    String operationId,
    String orderId,
    String sku,
    int quantity
) {
    ReserveCommand {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(operationId, "operationId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(sku, "sku");
    }
}

record ReserveReply(
    String tenantId,
    String requestId,
    String operationId,
    String orderId,
    String status,
    String reasonCode,
    String workerThread
) {
    ReserveReply {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(operationId, "operationId");
        Objects.requireNonNull(status, "status");
    }
}
~~~

`requestId` ở đây giúp minh họa exchange identity. Trong cùng-JVM Gateway, framework cũng quản lý reply routing/correlation nội bộ; khi chuyển sang **broker remote**, ta cần thiết kế correlation/idempotency contract độc lập với Java object.

### 8.2. Service Activator giả lập một worker

~~~java
final class ReservationWorker {

    public ReserveReply reserve(ReserveCommand cmd) {
        String worker = Thread.currentThread().getName();

        // Demo chỉ tính result; không thực thi DB mutation.
        if (cmd.tenantId().isBlank()
                || cmd.requestId().isBlank()
                || cmd.operationId().isBlank()
                || cmd.orderId().isBlank()
                || cmd.sku().isBlank()) {
            return new ReserveReply(
                cmd.tenantId(), cmd.requestId(),
                cmd.operationId(), cmd.orderId(),
                "REJECTED", "MISSING_FIELD", worker);
        }

        if (cmd.quantity() < 1 || cmd.quantity() > 500) {
            return new ReserveReply(
                cmd.tenantId(), cmd.requestId(),
                cmd.operationId(), cmd.orderId(),
                "REJECTED",
                "INVALID_QUANTITY", worker);
        }

        return new ReserveReply(
            cmd.tenantId(), cmd.requestId(),
            cmd.operationId(), cmd.orderId(),
            "RESERVED", null, worker);
    }
}
~~~

**Lưu ý:** `RESERVED` ở demo không chứng minh stock đã bị giữ trong DB. Khi thay bằng service thật, cần transaction + idempotency ở business owner, không đặt logic “trừ kho lần nữa” vào một handler có thể được retry.

### 8.3. Gateway interface

~~~java
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
    defaultRequestChannel = "reservations.async.requests",
    defaultRequestTimeout = "500",
    defaultReplyTimeout = "3000")
interface ReservationGateway {

    ReserveReply reserve(ReserveCommand command);
}
~~~

Trong ví dụ này, method trả `ReserveReply`: **caller sẽ chờ**. Worker được chạy trên thread khác, nhưng API Java của caller vẫn synchronous. `defaultReplyTimeout` là demo; với DirectChannel hoặc I/O block, hiệu lực deadline có thể khác. Cần kiểm trên topology thực.

### 8.4. Java DSL và ExecutorChannel

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableIntegration
@IntegrationComponentScan
class AsyncReservationFlowConfiguration {

    @Bean
    ThreadPoolTaskExecutor reservationExecutor() {
        ThreadPoolTaskExecutor pool =
            new ThreadPoolTaskExecutor();
        pool.setThreadNamePrefix("reserve-worker-");
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(32);
        return pool;
    }

    @Bean("reservations.async.requests")
    ExecutorChannel asyncRequestChannel(
            ThreadPoolTaskExecutor reservationExecutor) {
        return new ExecutorChannel(reservationExecutor);
    }

    @Bean
    ReservationWorker reservationWorker() {
        return new ReservationWorker();
    }

    @Bean
    IntegrationFlow processReservations(
            ReservationWorker worker) {
        return IntegrationFlow
            .from("reservations.async.requests")
            .handle(worker, "reserve")
            // Không gắn output channel tĩnh cản reply
            // của Gateway đã đặt vào request metadata.
            .get();
    }
}
~~~

**Ý nghĩa luồng:**

1. Gateway biến `reserve(command)` thành request message có reply route nội bộ.
2. ExecutorChannel dispatch đến thread thuộc `reservationExecutor`.
3. `ReservationWorker.reserve` được gọi như Service Activator, trả `ReserveReply`.
4. Handler/flow gửi reply về route mà Gateway đang chờ theo endpoint semantics.
5. Gateway nhận reply và chuyển payload về `ReserveReply` cho caller.

### 8.5. Vì sao không chỉ dùng `DirectChannel`?

`DirectChannel` thường gọi handler trong thread người gửi: hành vi có thể vẫn request–reply, nhưng **không minh họa worker được tách thread**. `ExecutorChannel` giúp thấy rõ ranh giới async, nhu cầu capacity, thread context và deadline.

**Không** chọn executor unbounded. Nếu queue/pool đầy, request send có thể bị reject; cần bounded capacity, metrics, backpressure và chính sách trả lỗi/HTTP 429/503 thích hợp. Mã này chỉ là demo và chưa cấu hình broker durability.

### 8.6. Nếu handler trả `null` thì sao?

Một handler trả `null` thường **không tạo ordinary reply**. Gateway đang chờ có thể timeout hoặc flow phát lỗi nếu handler cấu hình `requiresReply`. Nếu business từ chối, nên trả `ReserveReply(status="REJECTED")` có reason thay vì `null`.

## 9. JUnit 5: chứng minh async xử lý nhưng request–reply đúng

### 9.1. Unit tests cho worker

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ReservationWorkerTest {

    private final ReservationWorker worker =
        new ReservationWorker();

    private static ReserveCommand command(int quantity) {
        return new ReserveCommand(
            "shop-a", "req-101", "RSV-101",
            "ORD-101", "BOOK-42", quantity);
    }

    @Test
    void acceptsValidCommand() {
        ReserveReply reply = worker.reserve(command(2));

        assertEquals("req-101", reply.requestId());
        assertEquals("RSV-101", reply.operationId());
        assertEquals("RESERVED", reply.status());
        assertNull(reply.reasonCode());
    }

    @Test
    void rejectsQuantityWithTypedReply() {
        ReserveReply reply = worker.reserve(command(0));

        assertEquals("REJECTED", reply.status());
        assertEquals("INVALID_QUANTITY", reply.reasonCode());
    }
}
~~~

### 9.2. Integration tests với Spring context

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(AsyncReservationFlowConfiguration.class)
class AsyncReservationGatewayIntegrationTest {

    @Autowired
    ReservationGateway gateway;

    private static ReserveCommand command(
            String requestId, String operationId,
            int quantity) {
        return new ReserveCommand(
            "shop-a", requestId, operationId,
            "ORD-901", "BOOK-42", quantity);
    }

    @Test
    void receivesTypedReplyFromExecutorThread() {
        ReserveReply reply = gateway.reserve(
            command("req-a", "RSV-901", 2));

        assertNotNull(reply);
        assertEquals("req-a", reply.requestId());
        assertEquals("RSV-901", reply.operationId());
        assertEquals("RESERVED", reply.status());

        // Thread name cho thấy dispatch qua ExecutorChannel.
        assertTrue(
            reply.workerThread().startsWith("reserve-worker-"));
    }

    @Test
    void businessRejectionStillReturnsReply() {
        ReserveReply reply = gateway.reserve(
            command("req-b", "RSV-902", -3));

        assertEquals("req-b", reply.requestId());
        assertEquals("REJECTED", reply.status());
        assertEquals(
            "INVALID_QUANTITY", reply.reasonCode());
    }
}
~~~

### 9.3. Hạn chế của integration test

- Đây là **test trong một JVM**; Spring Gateway và ExecutorChannel quản lý reply nội bộ.
- Nó chưa chứng minh request/reply survives process crash, Kafka/JMS/AMQP serialization, ACL, DLQ và database commit.
- Tên worker thread chỉ xác nhận có dispatch qua executor, không chứng minh mọi message đều chạy trên một thread cố định hoặc processing đúng thứ tự.
- Test này không tạo timeout có kiểm soát; cần thêm một **latch-controlled worker** và reply timeout riêng để test late reply, tránh dùng `Thread.sleep(...)` ngẫu nhiên khiến CI không ổn định.

### 9.4. Kiểm tra concurrency/correlation

Một bài integration test nâng cao nên thực hiện nhiều lời gọi đồng thời:

~~~text
Given:
  100 requests with distinct requestId and operationId
  20 concurrent callers
  worker reply times intentionally reordered

Assert:
  for each caller:
    reply.requestId == its own request.requestId
    reply.operationId == its own operationId
  no reply delivered to another caller
  timeout/rejection handled independently
~~~

Khi dùng một shared reply queue/topic hoặc nhiều service instances, việc kiểm correlation cần diễn ra **sau serialization và receive**, không chỉ trong một Gateway proxy.

## 10. Thiết kế request–reply qua một broker thật

Ví dụ sau áp dụng với các hệ thống messaging có request destination, reply destination và delivery at-least-once. Cách gắn header cụ thể tùy AMQP/JMS/Kafka adapter; đây là **giao thức logic**, không giả định một provider thực hiện hộ mọi bước.

~~~mermaid
flowchart TD
    API["Order API / Gateway"] --> STATE[("Operation + pending state")]
    API --> OUT[("Outbox request")]
    OUT --> PUB["Request publisher"]
    PUB --> REQQ[("inventory.requests queue/topic")]
    REQQ --> WORK["Inventory worker + inbox/idempotency"]
    WORK --> DB[("Inventory DB")]
    WORK --> OREPLY[("Outbox reply")]
    OREPLY --> REPLYQ[("order-service.replies")]
    REPLYQ --> LIST["Reply listener"]
    LIST --> VALID["Validate producer/correlation/schema/tenant"]
    VALID --> STATE
    STATE --> STATUS["Status API / webhook / pending waiter"]
~~~

### 10.1. Bên gửi (Requester) chịu trách nhiệm gì?

1. Xác thực caller và tạo/kiểm `operationId` (stable business identity).
2. Tạo `requestId` cho exchange và record mapping tới operation.
3. **Persist operation/pending metadata** nếu cần sống qua restart.
4. Ghi request vào **outbox cùng transaction** với record operation nếu cần atomic state+publish intent.
5. Publish request envelope có schema version, correlation, deadline, reply destination được allowlist.
6. Có reply listener đọc kết quả, xác thực nguồn và match correlation.
7. Trả status cho caller/hoàn thành pending future nếu vẫn đang chờ.
8. Dọn pending theo TTL nhưng **không xóa business operation status** chỉ vì caller đã timeout.

### 10.2. Bên xử lý (Responder) chịu trách nhiệm gì?

1. Consume request, validate schema/version và nguồn đã xác thực.
2. Kiểm deadline/policy/authorization; không tin tenant/replyTo tùy ý.
3. Dedupe business operation theo `(tenantId,operationId)` và request fingerprint.
4. Thực hiện effect một lần trong consistency boundary có thể bảo đảm.
5. Persist outcome, rồi publish reply có `correlationId=requestId`.
6. Nếu publish reply thất bại sau commit, retry **việc phát reply**, không chạy effect lại.
7. Nếu request được giao lại, trả stored outcome cho exchange hợp lệ hiện tại.
8. Kiểm soát retry, DLQ, poison messages và reconciliation.

### 10.3. RequestId mới có thể nhận cùng persisted business result

~~~text
First exchange:
  requestId = req-a
  operationId = RSV-901
  outcome committed but reply lost

Second exchange:
  requestId = req-b
  operationId = RSV-901  (SAME mutation)
  worker returns persisted RESERVED
  reply correlationId = req-b
~~~

Ở đây bên xử lý **không tạo effect mới**, nhưng vẫn có thể phát **reply mới** cho một exchange mới. Điều này tránh việc trả reply của `req-a` vào waiter `req-b` một cách nhầm lẫn.

### 10.4. Reply publish không nên nằm trong cùng bước “reserve lại”

Một đoạn xử lý sai:

~~~java
// Sai khi retry publisher bằng cách gọi lại toàn handler
void onRetry(ReserveCommand command) {
    warehouse.reserveStock(command); // may repeat effect
    broker.sendReply(buildReply(command));
}
~~~

Một thiết kế tốt phải tách **business operation result** khỏi **reply delivery attempt**, ví dụ persist outcome và outbox event, để publisher có thể retry nhiều lần mà không gọi kho thêm.

## 11. Java 17: registry in-memory để hiểu correlation

Để thấy rõ cách nhiều pending requests được nối với replies khác thứ tự, có thể viết một registry nhỏ dùng `CompletableFuture`. Ví dụ này **chỉ dành cho một JVM**, không thay durable registry, authentication hoặc distributed correlation routing.

### 11.1. Khóa pending đủ scope

~~~java
record PendingKey(
    String tenantId,
    String requesterId,
    String requestId
) {}

record ExpectedReply(
    String operationId,
    java.util.concurrent.CompletableFuture<ReserveReply> future
) {}
~~~

### 11.2. Registry với register-before-publish

~~~java
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.TimeUnit;

final class PendingReplyRegistry {

    private final ConcurrentMap<PendingKey, ExpectedReply> pending =
        new ConcurrentHashMap<>();

    CompletableFuture<ReserveReply> register(
            PendingKey key, String operationId,
            Duration timeout) {
        CompletableFuture<ReserveReply> future =
            new CompletableFuture<>();
        ExpectedReply expected =
            new ExpectedReply(operationId, future);

        if (pending.putIfAbsent(key, expected) != null) {
            throw new IllegalStateException(
                "DUPLICATE_REQUEST_ID");
        }

        // Timeout chỉ đóng waiter, KHÔNG hủy worker từ xa.
        future.orTimeout(
                timeout.toMillis(), TimeUnit.MILLISECONDS)
            .whenComplete((reply, error) ->
                pending.remove(key, expected));

        return future;
    }

    boolean onReply(
            PendingKey key, ReserveReply reply) {
        ExpectedReply expected = pending.get(key);
        if (expected == null) {
            // Late reply hoặc không còn waiter.
            return false;
        }

        if (!key.tenantId().equals(reply.tenantId())
                || !key.requestId().equals(reply.requestId())
                || !expected.operationId().equals(
                    reply.operationId())) {
            // Không hoàn thành sai waiter.
            return false;
        }

        // Chỉ một complete thắng; duplicate -> false.
        return expected.future().complete(reply);
    }

    void failBeforePublish(
            PendingKey key, Throwable cause) {
        ExpectedReply expected = pending.get(key);
        if (expected != null) {
            expected.future().completeExceptionally(cause);
        }
    }
}
~~~

**Quy tắc bắt buộc:** `register(...)` **trước khi** publish, vì một reply rất nhanh có thể đến ngay sau publish. Nếu đăng ký waiter sau publish, reply listener có thể nhận kết quả nhưng không thấy pending entry rồi bỏ qua.

### 11.3. Hạn chế thiết kế in-memory

- Registry biến mất khi JVM chết, không cho phép bất kỳ instance nào complete một waiter của JVM khác.
- `CompletableFuture.orTimeout` kết thúc **future đang chờ**, không huỷ remote operation hoặc broker delivery.
- `onReply` so các trường identity nhưng không tự xác thực **producer**. Listener phải kiểm nguồn qua broker identity, schema và ACL trước khi gọi nó.
- Vì pending entry có TTL, late reply phải được đưa sang **business status persistence/reconciliation**, không chỉ bị discard.
- `failBeforePublish` chỉ nên gọi khi chắc chắn message **chưa được publish**. Một publisher timeout sau khi broker có thể đã nhận request là trạng thái **UNKNOWN**, không được giả là chưa gửi.
- Dùng `Duration` hợp lệ, không để timeout âm hoặc quá lớn; production cần bounds, resource limits và metrics để chống memory exhaustion.
- Dùng `CompletableFuture.completeExceptionally` để báo lỗi waiter không đồng nghĩa cập nhật operation business thành FAILED.

### 11.4. Một ví dụ sử dụng

~~~java
PendingKey key = new PendingKey(
    "shop-a", "order-service", "req-7f31");

// Register first:
var awaiting = registry.register(
    key, "RSV-901", java.time.Duration.ofSeconds(3));

// Publish request envelope with requestId=req-7f31.
// Reply listener receives and authenticates producer.
// Then:
registry.onReply(key, new ReserveReply(
    "shop-a", "req-7f31", "RSV-901",
    "ORD-901", "RESERVED", null, "inventory-worker"));

// The waiting caller can now get the typed reply.
ReserveReply reply = awaiting.join();
~~~

Đoạn trên minh họa **thứ tự thao tác** và API registry; biến `registry` giả định đã được tạo trong fixture. Không copy nó làm code xử lý broker production mà thiếu persistence, auth, scheduler và chính sách late reply.


## 12. Test correlation registry khi replies về sai thứ tự

Một registry in-memory cũng cần test races. JUnit 5 dưới đây kiểm hai requests độc lập, không dùng `Thread.sleep` để “giả concurrency”.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.Test;

class PendingReplyRegistryTest {

    private final PendingReplyRegistry registry =
        new PendingReplyRegistry();

    private static ReserveReply reply(
            String requestId, String operationId) {
        return new ReserveReply(
            "shop-a", requestId, operationId,
            "ORD-901", "RESERVED", null, "worker");
    }

    @Test
    void outOfOrderRepliesCompleteCorrectWaiters() {
        PendingKey keyA =
            new PendingKey("shop-a", "order-service", "req-a");
        PendingKey keyB =
            new PendingKey("shop-a", "order-service", "req-b");

        CompletableFuture<ReserveReply> pendingA =
            registry.register(
                keyA, "RSV-A", Duration.ofSeconds(5));
        CompletableFuture<ReserveReply> pendingB =
            registry.register(
                keyB, "RSV-B", Duration.ofSeconds(5));

        // B trả trước A: không được trao reply B cho A.
        assertTrue(registry.onReply(
            keyB, reply("req-b", "RSV-B")));
        assertTrue(registry.onReply(
            keyA, reply("req-a", "RSV-A")));

        assertEquals("RSV-A",
            pendingA.join().operationId());
        assertEquals("RSV-B",
            pendingB.join().operationId());
    }

    @Test
    void wrongOperationMustNotCompleteWaiter() {
        PendingKey key =
            new PendingKey("shop-a", "order-service", "req-a");
        CompletableFuture<ReserveReply> awaiting =
            registry.register(
                key, "RSV-A", Duration.ofSeconds(5));

        assertFalse(registry.onReply(
            key, reply("req-a", "RSV-OTHER")));
        assertFalse(awaiting.isDone());

        assertTrue(registry.onReply(
            key, reply("req-a", "RSV-A")));
        assertEquals("RSV-A",
            awaiting.join().operationId());
    }

    @Test
    void duplicateReplyIsNotDeliveredTwice() {
        PendingKey key =
            new PendingKey("shop-a", "order-service", "req-a");
        CompletableFuture<ReserveReply> awaiting =
            registry.register(
                key, "RSV-A", Duration.ofSeconds(5));

        assertTrue(registry.onReply(
            key, reply("req-a", "RSV-A")));
        assertFalse(registry.onReply(
            key, reply("req-a", "RSV-A")));

        assertEquals("RESERVED",
            awaiting.join().status());
    }
}
~~~

Test thứ ba không khẳng định **business effect** chỉ được commit một lần; nó chỉ cho thấy local pending waiter chỉ được hoàn tất một lần. Cần test idempotency tại DB/business owner riêng.

### 12.1. Test timeout mà không tạo flaky sleep

Một negative test có thể đăng ký với timeout ngắn và chờ `CompletableFuture` kết thúc exceptional:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.concurrent.CompletionException;
import org.junit.jupiter.api.Test;

@Test
void timeoutClosesWaiterButNotRemoteOperation() {
    PendingReplyRegistry registry =
        new PendingReplyRegistry();
    PendingKey key =
        new PendingKey("shop-a", "order-service", "req-timeout");

    var future = registry.register(
        key, "RSV-901", Duration.ofMillis(50));

    assertThrows(
        CompletionException.class, future::join);

    // Một late reply không thể complete waiter cũ.
    assertFalse(registry.onReply(
        key, new ReserveReply(
            "shop-a", "req-timeout", "RSV-901",
            "ORD-901", "RESERVED", null, "worker")));
}
~~~

Đoạn này chỉ là test future timeout ở mức Java, **không** phát message hoặc cancel worker. Với CI lớn, chọn timeout/clock abstraction và scheduler injection phù hợp để tránh timing test không ổn định.

### 12.2. Test bảo mật: sai tenant hoặc request ID

Thêm fixtures reply có `tenantId=shop-b` dù `PendingKey` thuộc `shop-a`, hoặc reply có `requestId=req-other`. `onReply` phải trả false và không complete pending của shop-a.

Nhưng vẫn phải kiểm **authenticated producer** ở listener; bất cứ ai publish reply giả có IDs đúng đều có thể làm sai kết quả nếu không có ACL, producer authentication hoặc validation chữ ký/kênh phù hợp.

## 13. Durable request submission: đừng gửi broker rồi mới ghi operation

Trong hệ thống có yêu cầu không mất việc sau crash, thứ tự thao tác rất quan trọng.

### 13.1. Cách dễ mất message

~~~text
1. HTTP handler inserts operation=PENDING into DB.
2. It commits DB transaction.
3. Process crashes BEFORE publishing broker request.
4. Operation remains PENDING forever.
~~~

Hoặc đảo thứ tự:

~~~text
1. Publish broker request successfully.
2. Process crashes BEFORE persisting operation.
3. Worker processes; reply returns but no state exists.
~~~

Hai hệ độc lập (DB và broker) không tự có atomic commit. Khi cần reliability, dùng **transactional outbox** hoặc cơ chế nhất quán khác được kiểm chứng.

### 13.2. Outbox ở requester

~~~text
BEGIN DATABASE TRANSACTION
  insert/get operation(tenantId, operationId, status=RECEIVED)
  reject mismatched request fingerprint for reused operationId
  insert outbox message(
    requestId, operationId,
    destination=inventory.requests,
    payload, schemaVersion
  )
COMMIT

Outbox publisher:
  read unpublished rows
  send request to broker
  mark published / retry safely
~~~

Điều này giúp lưu bền **ý định publish** với operation state. Nhưng publisher vẫn có thể phát duplicate nếu gửi thành công rồi crash trước khi mark published. Do đó Worker cần **idempotent receiver**.

### 13.3. `HTTP 202 Accepted` nên được hiểu thế nào?

Có thể trả:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /api/reservations/RSV-901
~~~

~~~json
{
  "operationId": "RSV-901",
  "status": "RECEIVED",
  "statusUrl": "/api/reservations/RSV-901"
}
~~~

Nếu API hứa **durable acceptance**, hãy chỉ phát 202 sau khi request intent/operation được commit bền vững theo cơ chế tương ứng. 202 không chứng minh `RESERVED`; business result có thể là `REJECTED` ở bước sau.

Không trả 201/200 “đã giữ hàng thành công” chỉ vì request mới được đẩy vào queue.

### 13.4. Operation status endpoint

~~~text
GET /api/reservations/RSV-901

Possible responses:
  RECEIVED
  PROCESSING
  COMPLETED { status: RESERVED, ... }
  REJECTED  { reasonCode: ... }
  UNKNOWN   { guidance: retry/reconcile }
~~~

API tra trạng thái phải xác thực caller, so tenant/ownership, giới hạn rate, tránh lộ operation ID của người khác. Một `operationId` có entropy cao **không thay thế authorization**.

### 13.5. Webhook/callback thay polling

Nếu business muốn push kết quả, có thể gửi webhook khi operation hoàn tất. Nhưng webhook delivery có thể retry và duplicate:

- Endpoint callback phải được đăng ký và **xác thực/allowlist**, tránh SSRF/open-redirect style replyTo.
- Ký/authenticate callback theo phương án được chấp thuận; ngăn replay.
- Gắn stable `operationId` và `eventId`.
- Receiver xử lý idempotent theo event/operation semantics.
- Tách trạng thái “business completed” khỏi “webhook delivered”.

## 14. Idempotency ở Worker: chống double reserve

Một request có thể được giao lại do broker at-least-once; handler chạy nhiều lần nhưng **không được commit cùng mutation nhiều lần**.

### 14.1. Khóa nghiệp vụ đúng phạm vi

~~~text
UNIQUE (tenant_id, operation_id)
Stored record:
  request_fingerprint
  state = IN_PROGRESS / COMPLETED / REJECTED
  stored_reply
  updated_at
~~~

Không dùng riêng `orderId` nếu một order có lệnh RESERVE, RELEASE và ADJUST hợp lệ khác nhau. Cũng không dùng transport message ID hoặc Kafka offset: những giá trị ấy có thể khác khi redelivery/replay.

### 14.2. Luồng xử lý logic

~~~mermaid
flowchart TD
    REQ["Delivered ReserveCommand"] --> AUTH["Validate auth/schema/deadline"]
    AUTH --> CLAIM{"Atomically claim operation key"}
    CLAIM -->|"New"| EXEC["Execute mutation once"]
    CLAIM -->|"Completed same fingerprint"| STORED["Load stored outcome"]
    CLAIM -->|"In-progress"| WAIT["Wait/defer/reconcile"]
    CLAIM -->|"Same key, different request"| CONFLICT["IDEMPOTENCY_CONFLICT"]
    EXEC --> COMMIT["Commit mutation + persist outcome"]
    COMMIT --> OUT["Reply outbox"]
    STORED --> OUT
    OUT --> PUB["Publish reply for current requestId"]
    CONFLICT --> ERR["Typed rejection"]
~~~

**Quan trọng:** `request_fingerprint` nên được tính từ business command được chuẩn hóa đúng, gồm tenant, operation type, resource và parameters ảnh hưởng side effect. Nếu fingerprint chỉ là raw JSON bytes, khác thứ tự key/format có thể tạo conflict giả; nếu fingerprint quá nghèo, hai intents khác nhau có thể dùng chung key mà không bị phát hiện.

### 14.3. Race giữa hai Worker instances

Một `ConcurrentHashMap` chỉ bảo vệ một JVM. Khi A và B cùng đọc operation chưa có, cả hai có thể chạy effect nếu check-then-insert không nguyên tử.

Cần shared DB unique constraint, atomic claim/locking hoặc một backend cung cấp idempotency. Nếu effect là **remote HTTP call**, DB claim riêng vẫn chưa đủ để đảm bảo exactly-once effect ở hệ thống đích; cần idempotency token được remote API chấp nhận hoặc reconciliation khi response mất.

### 14.4. Sau commit nhưng publish reply thất bại

~~~text
Worker commits RESERVE
    |
Process crashes before reply publish
    |
Broker redelivers request
    |
Worker finds COMPLETED and stored result
    |
Worker publishes ReserveReply again
~~~

Không thực hiện `reserveStock` lần hai. Tách **business state** và **reply delivery** có thể dùng outbox để gửi reply sau commit một cách bền vững.

### 14.5. Reply duplication bình thường trong at-least-once

Nếu Worker đã publish reply thành công nhưng chưa ACK request trước khi crash, request có thể được giao lại và reply được publish lần hai. Reply listener cần:

- Dedupe theo reply event ID hoặc `(tenantId,requestId,replyVersion)` theo contract.
- Không complete cùng pending exchange nhiều lần.
- Không update operation sang trạng thái không hợp lệ do reply cũ đến sau.
- Có sequence/version guard khi outcome có thể chuyển trạng thái nhiều lần.

Một request–reply đáng tin **không hứa mỗi reply chỉ xuất hiện một lần**; nó hứa caller/state machine xử lý được duplicate và retry.

## 15. Retry và error channel: hai nơi thất bại khác nhau

### 15.1. Request-side errors

| Điểm lỗi | Ví dụ | Hành động |
| --- | --- | --- |
| Validate ingress | Missing tenant/operation ID | Reject có mã, không publish |
| Persist request/outbox | DB unavailable | Trả lỗi chấp nhận chưa bền, retry có kiểm soát |
| Publish request | Broker timeout | Có thể đã publish; reconcile outbox state |
| Wait reply | Reply timeout | Trạng thái exchange timeout; operation UNKNOWN/PROCESSING |
| Reply parsing | Unsupported reply schema | Quarantine raw có bảo vệ, không complete waiter |
| Reply identity | Wrong tenant/operation/requestId | Drop/quarantine + security alert |
| Reply destination | Reply queue không còn | Retry publish hoặc lưu persisted outcome |

### 15.2. Responder-side errors

| Điểm lỗi | Ví dụ | Hành động |
| --- | --- | --- |
| Deserialize | Malformed payload | Terminal rejection/DLQ, tránh poison loop |
| Authorization | Tenant không được phép | Deny, không retry để bypass |
| Business validation | Quantity không hợp lệ | Typed `REJECTED` reply |
| DB temporary outage | Timeout/deadlock | Bounded retry + backoff |
| External API timeout | Không biết remote có commit | Status lookup + same idempotency key |
| Outbox publish | Reply broker unavailable | Retry reply delivery, không re-run effect |
| Callback send | Client endpoint unavailable | Retry callback theo policy, operation vẫn hoàn tất |

### 15.3. Spring Integration errorChannel không đồng nghĩa business reply

`errorChannel`, `ErrorMessage` và `MessagingException` dùng cho **error flow**. Một message lỗi kỹ thuật không tự thành `ReserveReply(status=REJECTED)`.

- Với `DirectChannel` đồng bộ, handler exception có thể propagate về caller.
- Với `ExecutorChannel`, poller và broker adapters, lỗi có thể đi vào error handling/error channels theo endpoint configuration.
- Với remote request–reply, listener nên chuyển lỗi thành **protocol-level reply/terminal status** khi được phép và có thông tin correlation hợp lệ; nếu không, dùng DLQ/reconciliation thay vì im lặng drop.

**Không** catch mọi `Exception` rồi trả `RESERVED` hoặc `INVALID_QUANTITY`; điều đó che lỗi hạ tầng và làm sai retry policy.

### 15.4. Đừng retry một terminal business rejection

Nếu `quantity=-2`, gửi lại cùng bytes 10 lần không tự làm quantity hợp lệ. Phát `ReserveReply(status=REJECTED, reasonCode=INVALID_QUANTITY)`, chốt outcome tương ứng, trả về caller hoặc status API.

Ngược lại, broker timeout không chứng minh quantity sai. Cần **retry hạ tầng** với bounded attempts, backoff/jitter, circuit breaker và idempotency.

## 16. Security: correlation và replyTo đều là điểm cần xác thực

Một request ngoài có thể cố gửi:

~~~json
{
  "tenantId": "victim-tenant",
  "operationId": "RSV-901",
  "replyTo": "attacker-controlled-queue",
  "quantity": 2
}
~~~

Nếu Worker chỉ tin các field này, có thể vừa xử lý nhầm tenant vừa phát dữ liệu cho đối tượng không có quyền.

### 16.1. Trust boundary đúng

~~~text
External request
  -> AuthN producer/principal
  -> AuthZ tenant/resource/action
  -> Size/schema/version validation
  -> Assign/verify operationId, requestId
  -> Resolve reply destination from allowed registry
  -> Safe internal request envelope
  -> Queue / Worker
~~~

Tên header `trustedTenant` tự nó không tạo uy tín. Adapter phải chứng minh provenance. Trong multi-tenant system, Worker vẫn cần authorization tại nơi commit, không chỉ vì caller từng được kiểm ở edge.

### 16.2. Reply listener không tin mỗi correlation ID

Nếu reply có `correlationId=req-7f31` nhưng từ một producer không thuộc inventory service, hoặc ghi tenant khác, phải từ chối. Một guessed/captured request ID không được quyền complete pending của người khác.

Kiểm tra ít nhất:

- Broker authentication/ACL hoặc chữ ký/event provenance thích hợp.
- Request/operation/tenant match.
- Reply schema version và status hợp lệ.
- Producer đúng loại service được mong đợi.
- Payload size và fields có allowlist.
- Không log secrets/PII khi reply bị reject.

### 16.3. ReplyTo không là URL tùy ý

Một `replyTo` chứa HTTP URL có thể tạo rủi ro SSRF/data exfiltration; một queue name bất kỳ có thể gửi dữ liệu qua tenant khác. Hãy suy reply destination từ **identity đã xác thực và cấu hình** hoặc áp allowlist/ACL chặt. Không forward Authorization/JWT thô hay Java `MessageChannel` object qua broker.

### 16.4. Encryption, retention và data minimization

Request/reply có thể chứa PII, số tiền, địa chỉ, order IDs. Cần mã hóa dữ liệu khi truyền và khi lưu theo threat model, quyền truy xuất per tenant, thời hạn giữ inbox/outbox/DLQ/status và chính sách xóa. Không đưa `tenantId`/`operationId` tùy ý vào metric tags gây high cardinality.


## 17. Request–reply qua JMS, AMQP và Kafka

Mỗi công nghệ messaging có primitives khác nhau. Pattern EIP giống nhau, nhưng không thể copy cùng một config/header mapper và cho rằng nó có semantics giống hệt.

| Hạ tầng | Cách gửi request | Reply path thường gặp | Rủi ro trọng tâm |
| --- | --- | --- | --- |
| **JMS** | Request destination qua JMS producer | `JMSReplyTo` + `JMSCorrelationID`/adapter | Temporary queue lifecycle, sessions/ACK, provider semantics |
| **AMQP/RabbitMQ** | Exchange + routing key đến queue | Reply queue, reply-to, correlation properties | Connection loss, manual ack, duplicate, direct reply-to |
| **Kafka** | Request topic với key/headers | Reply topic + key/correlation header | Reply partitions, consumer groups, rebalance, retention |
| **Spring in-JVM** | Direct/Executor/QueueChannel | `replyChannel` header do Gateway quản lý | Không có durability sau process crash |
| **HTTP 202 + status** | POST và lưu durable operation | GET status, webhook hoặc event | Callback auth, eventual consistency, retention |

### 17.1. JMS: replyTo và correlation cần đồng thuận

JMS message có `JMSMessageID`, `JMSCorrelationID` và `JMSReplyTo`. Một requester có thể cung cấp reply destination và một correlation key; responder gửi reply tới destination thích hợp, listener dùng correlation để match.

Nhưng:

- Không tự dùng `JMSMessageID` của request như `operationId` của business mutation.
- Không giả định mọi provider/adapter map `JMSCorrelationID` từ `requestId` theo cùng một default.
- Temporary reply queue có thể không tồn tại khi requester restart; muốn durable reply cần destination/lifecycle khác.
- Session transaction/ACK chỉ bảo vệ đúng transport boundary, không tự tạo atomic DB+JMS+HTTP transaction.

Khi dùng Spring Integration JMS Gateway/Adapters, cấu hình reply listener, converter, correlation strategy, consumer concurrency và error handling theo **version cụ thể**, rồi test với broker thật.

### 17.2. AMQP/RabbitMQ: ACK và direct reply-to

AMQP reply patterns có thể dùng reply queue hoặc **direct reply-to**. Direct reply-to thuận tiện/nhẹ trong một số RPC flows nhưng có những giới hạn về tính bền của reply và lifecycle; không nên coi nó như một kết quả workflow có thể truy xuất vô hạn.

Cần xác định:

- Responder có quyền publish đến reply destination nào.
- Correlation property được gắn và đọc ra đúng byte/type.
- Consumer ACK request trước hay sau khi persist outcome/outbox.
- Publisher confirm nói gì về broker accept và điều gì **chưa** chứng minh.
- Nếu reply bị mất, operation status/retry sẽ được phục hồi ở đâu.

Đừng dựa vào một in-memory reply queue như nguồn sự thật của business outcome.

### 17.3. Kafka: reply topic phải có consumer topology phù hợp

Kafka không phải RPC transport mặc định. Một implementation có thể chọn:

~~~text
inventory.requests topic:
  key = tenantId + ":" + orderId (for partition affinity)
  headers: requestId, operationId, replyTopic, schemaVersion
  value = ReserveCommand

inventory.replies topic:
  key = requestId or partition key per protocol
  headers: correlationId=requestId, schemaVersion
  value = ReserveReply
~~~

Đây là **giao thức ví dụ**. Cần định nghĩa encoding của key, tránh collision do nối chuỗi; nếu sử dụng partition ordering cần chọn partition key nhất quán.

Vấn đề khác với JMS:

- Topic reply có thể được đọc bởi consumer group; **một reply có thể đến một instance không giữ local waiter**.
- Nếu mỗi instance có registry in-memory và chung consumer group, reply được phân phối sang instance bất kỳ là rủi ro.
- Cần **instance-specific reply routing**, partition assignment phù hợp hoặc **shared persistent workflow state** thay vì hy vọng consumer group “tự biết” caller nào chờ.
- Offset không phải business operation identity. Reply topic retention không thay cho durable operation ledger.
- Rebalance/retry topic có thể thay đổi nơi processing; phải hỗ trợ duplicate, out-of-order và concurrency.

### 17.4. Exactly-once trong broker không bằng exactly-once external side effect

Broker transaction có thể hỗ trợ bảo đảm trong **phạm vi broker** nhưng không tự rollback một lệnh HTTP tới warehouse hoặc database khác khi network response mất.

Để bảo vệ nghiệp vụ, cần idempotency ở owner, unique operation key, outcome persistence và reconciliation. Đừng viết tài liệu “Kafka exactly-once nên không thể giữ hàng hai lần” nếu còn remote side effect không có transaction chung.

### 17.5. Message headers có thể mất khi serialization

Spring `MessageHeaders` cho phép các kiểu object, trong khi transport hỗ trợ tập kiểu/encoding riêng. Khi đi qua adapter, phải kiểm:

- ID và correlation là String/UUID/binary theo contract.
- `replyChannel`/`errorChannel` nội bộ không bị serialize vào broker.
- Content type phản ánh bytes đã serialize, không phải Java record trong JVM.
- Schema versions được consumer hiểu và unknown fields có policy.
- Không copy JWT/secret, stack traces hoặc object exceptions qua reply.
- Header mapper có allowlist và test **on-the-wire** thực sự.

## 18. Request–reply kết hợp Router, Filter và Transformer

Một async flow nhiều nguồn thường có:

~~~mermaid
flowchart TD
    IN["Request topic/queue"] --> AUTH["Authenticate + validate envelope"]
    AUTH --> ROUTE["Router by trusted source / command type"]
    ROUTE --> T1["Translator A to canonical"]
    ROUTE --> T2["Translator B to canonical"]
    T1 --> FILTER{"Business validation"}
    T2 --> FILTER
    FILTER -->|"Valid"| SVC["Service Activator / handler"]
    FILTER -->|"Invalid"| REJ["Typed REJECTED reply"]
    SVC --> RES["Persist outcome + reply outbox"]
    REJ --> RES
    RES --> PUB["Publish reply with original requestId"]
~~~

### 18.1. Filter drop là nguy cơ trong request–reply

Nếu Filter **âm thầm loại** một request do validation, caller chỉ thấy timeout dù input thực sự bị từ chối. Với request–reply mà caller cần biết outcome, hãy:

- Tạo typed rejection reply `INVALID_QUANTITY`, hoặc
- Ghi terminal operation status + reason nếu là async end-to-end, hoặc
- Có error/rejection channel mà API có thể đọc.

Một Filter chỉ drop phù hợp khi contract cho phép **không phát reply**; không nên dùng nó như một cách báo lỗi mặc định.

### 18.2. Transformer không được mất correlation

Nếu Service A gửi `requestId=req-7f31` rồi Transformer đổi schema trước Worker, phải giữ correlation/operation identity cần thiết. Không tạo random requestId mới trong Transformer nếu chỉ đang dịch **cùng một request exchange**.

Nếu target broker có header name khác, cần explicit mapping. Reply Translator chiều về cũng phải giữ request ID để listener ghép đúng pending entry.

### 18.3. Router phải có đường lỗi cho unknown command type

Một `commandType=CANCEL` mới đến trước khi Worker hỗ trợ: không nên route sang RESERVE chỉ vì default branch, cũng không silent drop. Có thể trả `UNSUPPORTED_COMMAND` hoặc quarantine cùng operation status, tùy protocol và security.

## 19. Async request–reply với Splitter, Aggregator và Scatter-Gather

Một request có thể được chia thành nhiều child work items. Caller vẫn cần **một reply tổng** hoặc một status tổng.

~~~mermaid
flowchart TD
    REQ["ReserveBatch(requestId=req-700)"] --> SPLIT["Splitter: 3 lines"]
    SPLIT --> A["Worker LINE-1"]
    SPLIT --> B["Worker LINE-2"]
    SPLIT --> C["Worker LINE-3"]
    A --> OUT1["LineOutcome RESERVED"]
    B --> OUT2["LineOutcome REJECTED"]
    C --> OUT3["LineOutcome RESERVED"]
    OUT1 --> AGG["Aggregator by executionId"]
    OUT2 --> AGG
    OUT3 --> AGG
    AGG --> BR["BatchReply(correlationId=req-700)"]
~~~

### 19.1. Ba loại correlation có vai trò riêng

| Identity | Phạm vi | Ví dụ |
| --- | --- | --- |
| `requestId` | Exchange caller ↔ batch reply | `req-700` |
| `executionId` | Group của một workflow run | `RUN-700-A` |
| `childId` | Phần việc duy nhất trong group | `LINE-2` |
| `operationId` | Side effect duy nhất của child | `RSV-700-LINE-2` |
| `businessCorrelationId` | Trace order/case rộng hơn | `ORD-700` |

**Đủ child replies khác với toàn bộ child thành công.**

~~~text
Expected: LINE-1, LINE-2, LINE-3
Received: 3/3 unique outcomes
Business result: 2 RESERVED, 1 REJECTED
Batch outcome: PARTIAL / FAILED (policy-dependent)
~~~

### 19.2. Đừng đếm duplicate reply là một child mới

Nếu LINE-1 bị redelivery hai lần và Aggregator dùng `group.size()==3`, nó có thể release sớm khi mới nhận LINE-1, LINE-1 duplicate và LINE-3, còn LINE-2 chưa đến.

Cần release dựa trên **expected unique child set**, dedupe `(executionId,childId)`, và policy khi outcome của cùng child mâu thuẫn.

### 19.3. Zero replies không tạo group timeout

Nếu cả ba workers đều không gửi reply, Aggregator có thể chưa có message nào để tạo group; `groupTimeout` của một group chưa tồn tại không giải quyết được. Cần một **execution-level deadline watcher**, durable expected child registry hoặc workflow timeout độc lập.

### 19.4. Partial, cancellation và compensation

Một batch hết deadline trong khi LINE-1 đã reserve thành công và LINE-3 còn xử lý. Có các lựa chọn:

- **Return PARTIAL** cùng danh sách outcomes rõ, để consumer quyết định.
- **Await later completion** qua status/callback.
- **Compensate** các side effects đã commit nếu business contract all-or-nothing và compensation khả thi.
- **Mark UNKNOWN** cho những children chưa biết, không khai gian thành REJECTED.

Timeout Gateway chỉ dừng một waiter, không tự rollback các child mutations.

### 19.5. Finalize một lần

Một batch reply đến muộn có thể kích hoạt lại Aggregator sau khi group được xóa. Cần closed-execution registry/tombstone, result version và idempotent finalizer để tránh publish hai final decisions khi contract không cho phép.

## 20. Ordering, concurrency và backpressure

### 20.1. Replies không có thứ tự chung

Async Worker/Executor/broker có thể trả reply sai thứ tự gửi. Request–reply correlation phải theo ID, **không** theo thứ tự FIFO của một shared reply queue.

Ngay cả nếu request partition giữ ordering trong Kafka, outbound Worker concurrency hoặc retry topic vẫn có thể đảo thứ tự replies. Nếu business cần xử lý theo sequence, cần version/sequence và reorder policy riêng.

### 20.2. Không xử lý status cũ đè status mới

Giả sử:

~~~text
t1: Reserve operation completes (RESERVED)
t2: Caller starts separate CANCEL operation
t3: CANCEL commits (CANCELLED)
t4: Late RESERVE reply arrives
~~~

Nếu listener chỉ update order status theo thời điểm **nhận reply**, nó có thể đổi `CANCELLED` thành `RESERVED` sai. Cần event version/aggregate revision/operation sequencing theo domain và state transition validation.

### 20.3. Pending registry phải có giới hạn

Nếu 100.000 callers đều mở pending futures cho tác vụ mất 5 phút, memory/threads/connection pools có thể bị quá tải. Cần:

- Max pending requests và per-tenant quotas.
- Bounded executor queues và consumer concurrency.
- Deadline/TTL cleanup, metrics pending age.
- Rate limiting/load shedding và backpressure trả lỗi rõ.
- Chuyển sang **202 + polling/webhook** cho tác vụ dài.
- Size/TTL cho DLQ, outbox, reply topic và operation status.

### 20.4. Không bỏ qua consumer lag

Nếu request queue backlog 10.000 messages nhưng Gateway reply timeout 2 giây, đa số callers sẽ timeout trước khi worker bắt đầu. Đừng sửa bằng cách đặt timeout vô hạn; đánh giá capacity, service time, queueing delay và mô hình async end-to-end phù hợp hơn.

## 21. Observability: đo từng giai đoạn request–reply

Một log `request_published=true` chỉ chứng minh publisher đã quan sát một sự kiện gửi, không phải operation thành công.

| Signal/metric gợi ý | Câu hỏi |
| --- | --- |
| `requests_received_total` | Bao nhiêu yêu cầu vào? |
| `outbox_pending_total` | Bao nhiêu publish intents chưa chuyển? |
| `request_publish_failures_total` | Broker publish có lỗi? |
| `request_queue_depth/lag` | Worker có theo kịp không? |
| `worker_processing_duration` | Business service mất bao lâu? |
| `operation_completed_total` | Bao nhiêu operations commit? |
| `operation_rejected_total` theo reason | Bao nhiêu terminal rejections? |
| `reply_publish_failures_total` | Result đã có nhưng reply gửi lỗi? |
| `pending_replies_active` | Bao nhiêu waiters đang giữ? |
| `reply_received_total` | Bao nhiêu reply messages nhận được? |
| `reply_correlation_miss_total` | Reply không tìm thấy pending key? |
| `reply_identity_mismatch_total` | Wrong tenant/operation/request ID? |
| `reply_duplicates_total` | Bao nhiêu duplicate replies? |
| `reply_timeout_total` | Bao nhiêu exchanges hết hạn? |
| `late_reply_total` | Bao nhiêu kết quả đến sau wait deadline? |
| `idempotency_reused_total` | Bao nhiêu stored results được trả lại? |
| `dlq_backlog/oldest_age` | Có poison messages bị bỏ quên không? |
| `status_reconciliation_backlog` | Bao nhiêu UNKNOWN cần xử lý? |

Tên metric ở đây là **đề xuất instrumentation**, không khẳng định Spring Integration tự cấp tất cả các counters. Có thể kết hợp Micrometer/observation, broker metrics và business ledger.

### 21.1. Structured log không lộ data

~~~json
{
  "event": "reply_correlated",
  "sourceService": "inventory-service",
  "requestSchema": "reserve-command-v1",
  "replySchema": "reserve-reply-v1",
  "outcome": "RESERVED",
  "correlationResult": "MATCHED",
  "late": false,
  "duplicate": false
}
~~~

Khi debug một exchange cụ thể có thể cần `requestId`/`operationId` trong restricted logs/traces. Không đưa những IDs cardinality cao hay PII thô vào metric labels. Logs phải masking, access control và retention theo policy.

### 21.2. Trace span qua broker

Các spans có thể là:

~~~text
order.api.accept
  -> outbox.persist
  -> broker.publish.request
      -> inventory.consumer.receive
          -> reservation.commit
          -> broker.publish.reply
              -> order.reply.listener
                  -> pending.complete / status.persist
~~~

Trace/span IDs có thể được propagate bằng tiêu chuẩn phù hợp, nhưng tracing không phải cơ chế authorization hoặc business idempotency. Đừng tin traceparent do client tự đưa để xác định tenant.

### 21.3. Những cảnh báo quan trọng

Alert khi:

- Reply correlation miss tăng đột ngột.
- Lượng late replies tăng sau thay đổi timeout.
- Outbox publisher backlog tăng và request queue không nhận.
- Worker commit rate ổn định nhưng reply publish failures tăng.
- Pending registry gần capacity.
- Reply identity mismatch (có thể là bug mapping hoặc injection).
- UNKNOWN operations quá SLA, không có reconciliation.
- Retry storm/DLQ oldest age vượt ngưỡng.
- Batch executions không đủ child outcomes trước deadline.


## 22. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Coi async request–reply là fire-and-forget | Caller không biết operation outcome | Protocol reply/status rõ ràng |
| Broker ACK được coi là business success | Trả RESERVED dù worker chưa chạy | Phân biệt accepted, processed, committed |
| Reply đầu tiên được gán cho caller đầu tiên | Trộn data giữa requests | Correlation theo requestId |
| Correlation chỉ dựa trên orderId | Hai exchanges cùng order nhận nhầm | Scope requestId/tenant/requester |
| Dùng `MessageHeaders.ID` hoặc Kafka offset làm operation ID | Redelivery tạo ID mới | Stable business operation ID |
| Sinh `UUID` mới trong Worker retry | Double reserve/charge | Preserve operation ID qua attempts |
| Đăng ký pending sau publish | Fast reply đến trước registry | Register-before-publish |
| Pending registry in-memory được coi là durable | Crash mất waiter/state | Persistent operation/ledger, shared routing |
| Shared reply consumer group nhưng mỗi instance giữ private pending | Reply tới sai instance | Reply routing theo instance hoặc shared state |
| Không xác thực reply producer | Forged reply hoàn thành request | Broker auth/ACL, schema, identity matching |
| Chỉ so requestId, bỏ tenant/operation | Cross-tenant leak, status sai | Validate expected tenant, operation, producer |
| Chấp nhận `replyTo` tùy ý từ client | Data exfiltration/SSRF | Allowlists + trusted identity |
| Timeout được hiểu là business rollback | Operation có thể đã commit | UNKNOWN + reconciliation |
| Gateway replyTimeout là cancellation | Worker vẫn chạy sau timeout | Explicit cancellation/state policy |
| Call remote effect lại khi publish reply thất bại | Side effect trùng | Persist result + reply outbox |
| Chỉ check Redis/HashMap rồi mutate DB không atomic | Race giữa Worker instances | Atomic claim + consistency boundary |
| Outbox publisher được coi là exactly-once | Duplicate publish sau crash | Idempotent consumer |
| Retry terminal invalid input vô hạn | Poison loop/DLQ storm | Typed rejection và terminal handling |
| Convert technical error thành `REJECTED INVALID_QUANTITY` | Không retry đúng | Tách technical và business errors |
| One global timeout vô hạn | Memory/thread exhaustion | Bounded waits + 202/status API |
| Reply cũ ghi đè operation status mới | Hồi sinh trạng thái đã hủy | Version/state transition checks |
| Filter drop child lỗi | Aggregator thiếu outcomes | Typed rejected child result |
| `group.size()` coi duplicate là phần mới | Release sớm/batch sai | Unique child IDs + expected set |
| Chỉ dùng group timeout | Zero-reply execution bị bỏ quên | Execution-level deadline watcher |
| Test Gateway in-JVM rồi khẳng định broker durable | Bỏ qua crash, header mapping | Transport/broker contract tests |
| Copy raw payload/PII vào headers/logs | Rò rỉ dữ liệu | Minimal metadata, protected logs |
| Dùng requestId làm metric label | Cardinality cao | Metric tags hữu hạn, trace có ACL |

## 23. Checklist trước production

### 23.1. Hợp đồng giao thức

- [ ] Xác định caller có **chờ reply** hay dùng **accepted + later status**.
- [ ] Có request/reply schemas versioned; enum outcome và mã lỗi rõ.
- [ ] Phân biệt `requestId`, `operationId`, `businessCorrelationId`, `executionId` và transport IDs.
- [ ] Reply chứa correlation key, operation ID, tenant scope đủ để match.
- [ ] Định nghĩa idempotency contract cho mọi business mutation.
- [ ] Có protocol rõ cho missing reply, terminal rejection, transient failure và UNKNOWN.
- [ ] Không hiểu broker ACK/HTTP 202 là business COMMITTED.

### 23.2. Routing và consistency

- [ ] Reply destination được suy từ trusted registry/identity hoặc allowlist.
- [ ] Requester đăng ký pending **trước khi publish**.
- [ ] Pending cleanup có TTL/resource limit, không làm mất business outcome.
- [ ] Với multi-instance, reply listener có shared state hoặc instance affinity hợp lệ.
- [ ] Requester ghi durable operation/outbox nếu promise durable acceptance.
- [ ] Responder dùng atomic claim/idempotent receiver tại business owner.
- [ ] Stored outcome được tái sử dụng khi redelivery cùng operation key.
- [ ] Reply outbox cho phép retry publish mà không lặp side effect.
- [ ] Header mapping qua broker/HTTP không làm mất correlation hay gửi Java channel objects.
- [ ] Schema evolution/replay có mapping policy/version và reconciliation.

### 23.3. Deadline, security và vận hành

- [ ] Send timeout, reply wait timeout và business deadline được định nghĩa riêng.
- [ ] Gateway/HTTP có bounded waits; tác vụ dài chuyển sang status API/callback.
- [ ] Late reply cập nhật operation state hoặc được reconcile theo policy.
- [ ] Duplicate/out-of-order replies không complete sai waiter hay ghi đè state mới.
- [ ] AuthN/AuthZ/tenant/producer validation được thực thi ở cả hai phía.
- [ ] Callback/replyTo không cho phép chỉ định endpoint tùy ý.
- [ ] Pending registry/executor/broker queues có capacity, rate limiting và backpressure.
- [ ] Error channel và terminal business rejection được xử lý riêng.
- [ ] DLQ, outbox, inbox và operation status retention tương thích với replay window.
- [ ] PII/secrets được mã hóa, giới hạn logs/metric tags và quyền truy xuất.
- [ ] Có metrics cho publish, commit, reply, timeout, duplicate, late và UNKNOWN.
- [ ] Có runbook cho request stuck, replies orphaned, consumer lag và broker outage.

### 23.4. Kiểm thử

- [ ] Unit test Worker business outcome, không nhầm test với DB commit thật.
- [ ] Spring Integration test ExecutorChannel + typed Gateway reply.
- [ ] Test replies **đảo thứ tự** và correlation nhiều callers cùng lúc.
- [ ] Test duplicate reply chỉ hoàn tất pending một lần.
- [ ] Test wrong tenant/requestId/operationId không complete pending.
- [ ] Test timeout tạo exchange timeout nhưng **không** tự mark operation FAILED.
- [ ] Test register-before-publish bằng reply đến rất nhanh.
- [ ] Test process crash sau DB commit, trước reply publish; không double effect.
- [ ] Test outbox publisher duplicate và idempotent Worker/Consumer.
- [ ] Test reply consumer sau rebalance/restart, shared registry hoặc instance routing.
- [ ] Test missing reply, unknown schema, poison message và DLQ.
- [ ] Test zero-reply batch và duplicate/late child outcomes.
- [ ] Test authorization: requester không thể chọn reply destination ngoài quyền.
- [ ] Test status endpoint/webhook chặn cross-tenant reads.
- [ ] Test bounded resource usage khi pending/queue gần capacity.

## 24. Bài tập thực hành: tạo phiếu giao hàng bất đồng bộ

Một hệ thống thương mại điện tử nhận yêu cầu `CreateShipment`. Shipping Worker có thể tạo nhãn vận chuyển mất 30 giây, đôi khi carrier API timeout sau khi đã tạo shipment thật.

**Đầu vào:**

~~~json
{
  "tenantId": "shop-a",
  "operationId": "SHIP-CREATE-901",
  "requestId": "request-sh-901-a",
  "orderId": "ORD-901",
  "carrierCode": "CARRIER_A",
  "weightGrams": 1250
}
~~~

**Kết quả hợp đồng:**

~~~json
{
  "correlationId": "request-sh-901-a",
  "operationId": "SHIP-CREATE-901",
  "status": "CREATED",
  "shipmentId": "SHP-901",
  "reasonCode": null
}
~~~

### 24.1. Nhiệm vụ thiết kế

1. Chọn **Gateway chờ reply** hay **HTTP 202 + status API**, giải thích lựa chọn cho tác vụ 30 giây.
2. Thiết kế request/reply envelopes có schema version, authenticated tenant/producer, `requestId`, `operationId`, `replyTo` và deadline.
3. Vẽ sequence request queue → Worker → Carrier API → reply outbox → reply listener.
4. Giải thích vì sao HTTP 202 không có nghĩa shipment đã được tạo.
5. Thiết kế operation table và outbox trong cùng transaction cho requester.
6. Thiết kế idempotent Worker để carrier API timeout không sinh shipment thứ hai khi retry.
7. Nếu Carrier A không hỗ trợ idempotency token, đề xuất status lookup/reconciliation thay vì retry mù.
8. Quy định `requestId` thế nào khi retry cùng operation và khi mở một exchange mới.
9. Viết Java records `CreateShipmentCommand`, `ShipmentReply` và `PendingKey` có kiểu rõ.
10. Viết một `PendingReplyRegistry` dùng `CompletableFuture` chỉ để demo correlation.
11. Test replies của A và B đến đảo thứ tự, không trộn tenants/operations.
12. Test late reply sau deadline không complete HTTP caller cũ nhưng vẫn cập nhật durable shipment status.
13. Thiết kế callback/webhook an toàn, không chấp nhận URL tùy ý do client gửi.
14. Thiết kế Reply Listener validation: đúng schema, producer, tenant, operation và correlation.
15. Thêm một field mới trong `shipment-reply-v2`; nêu migration/unknown-field policy cho consumer v1.
16. Với 50 shipments, dùng Splitter/Aggregator và typed child outcomes; mô tả zero-reply deadline.
17. Mô tả vì sao Kafka consumer group có thể đưa reply tới instance không giữ in-memory waiter.
18. Thiết kế một topology reply topic/partition/instance routing hoặc shared status store phù hợp.
19. Chọn metrics cho accepted, pending, processing, committed, reply published, timeout, late, duplicate và UNKNOWN.
20. Tạo một runbook xử lý các operations `PROCESSING` quá SLA, không assume failed.
21. Viết broker integration tests cho publisher retry và consumer redelivery sau commit.
22. Kiểm tra không log PII/raw payload, không dùng request ID làm metric tag cardinality cao.

### 24.2. Tiêu chí nghiệm thu

Bài làm đạt khi chứng minh được **bốn tính chất độc lập**:

1. **Correlation correctness:** reply đúng tenant, request và operation, kể cả khi sai thứ tự.
2. **Outcome correctness:** caller phân biệt `ACCEPTED/PROCESSING/CREATED/REJECTED/UNKNOWN`, không lấy timeout làm FAILED.
3. **Idempotency correctness:** retry/redelivery/crash không tự tạo hai shipments cho một business operation.
4. **Recovery correctness:** process restart, mất reply, outbox retry và late result đều có đường tiếp tục/reconcile rõ.

Chỉ test “Gateway trả về một DTO hợp lệ” là chưa đủ cho một distributed request–reply protocol.

## 25. Tổng kết

**Request-reply qua hệ thống bất đồng bộ** cho phép bên gửi và bên xử lý giao tiếp qua queue, topic, executor hoặc broker mà vẫn có một hợp đồng trả kết quả. Bên gọi có thể **chờ** như với Messaging Gateway, hoặc **nhận 202 và theo dõi outcome sau** qua status API/webhook. Hai cách khác nhau về trải nghiệm và vòng đời tài nguyên, nhưng đều cần correlation và xác định rõ trạng thái xử lý.

Phần khó không phải gọi một method hay publish hai messages, mà là quản lý **reply đến khác thứ tự, duplicate, timeout, late reply, process crash, broker redelivery và cross-instance routing**. Giữ `requestId` cho exchange và `operationId` cho idempotent business mutation; không đồng nhất broker ACK, Java return hay Gateway timeout với DB commit. Với yêu cầu reliability, cần durable operation/outbox, atomic idempotency ở business owner, stored outcomes và reply listener xác thực người phát trước khi hoàn thành pending.

Trong Spring Integration, `@MessagingGateway`, `ExecutorChannel`, Service Activator, Router, Filter, Transformer, error channel và Splitter/Aggregator giúp hiện thực những đoạn của flow, nhưng không tự bảo đảm exactly-once external side effects. Hãy kết hợp **contract rõ, boundary security, bounded waiting, reconciliation và unit/integration/broker tests** để request–reply **đúng người, đúng nghiệp vụ, có khả năng phục hồi và không tạo side effect trùng**.

**Tài liệu tham khảo:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Request-Reply, Correlation Identifier, Messaging Gateway, Return Address, Service Activator, Idempotent Receiver, Aggregator, Dead Letter Channel); Spring Integration Reference về Messaging Gateways, Message Channels, ExecutorChannel, Service Activators, Routers, Error Handling và Testing; Spring Framework/Java SE về TaskExecutor, records, `CompletableFuture` và concurrency; tài liệu giao thức JMS, RabbitMQ/AMQP, Apache Kafka và mẫu transactional outbox/inbox theo hệ thống thực tế.









