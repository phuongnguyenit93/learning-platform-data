# Correlation qua retry và redelivery

> **Chương:** Content-based correlation  
> **Module:** `SPRING_INTEGRATION_PATTERN` — học triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng. Thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và theo dõi các nhánh xử lý. Bài này tập trung vào **giữ đúng danh tính nghiệp vụ và mối liên hệ giữa các thông điệp khi cùng một công việc được thử lại hoặc giao lại**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **content-based correlation**: tìm khóa liên hệ từ dữ liệu nghiệp vụ đã chuẩn hóa thay vì phụ thuộc hoàn toàn vào ID của envelope hoặc ID lần giao.
2. Phân biệt **correlation group**, **business operation identity**, **idempotency key**, **message ID**, **trace ID** và **attempt/delivery count**.
3. Mô tả **retry trong cùng lần xử lý**, **redelivery từ broker**, **dead-letter replay** và **reprocessing có chủ đích**; hiểu vì sao chúng không nhất thiết có cùng danh tính thực thi.
4. Thiết kế một khóa ổn định, không va chạm logic giữa tenant/đơn/dòng/thao tác và không thay đổi khi broker giao lại message.
5. Sử dụng Spring Integration **Java DSL + RequestHandlerRetryAdvice** để minh họa retry, rồi kiểm thử việc một business operation chỉ được commit một lần trong mô hình thử nghiệm.
6. Xử lý duplicate/reordered replies ở **Aggregator/Scatter-Gather**, tránh đếm nhiều lần một kết quả hay tạo group mới từ reply đến muộn.
7. Thiết kế idempotent consumer, inbox/outbox, durable state, header propagation, timeout/reconciliation và observability qua HTTP, AMQP/JMS/Kafka.

## 2. Bài toán: một yêu cầu giữ hàng được thực thi bao nhiêu lần?

Giả sử hệ thống nhận lệnh giữ hàng:

~~~json
{
  "tenantId": "shop-a",
  "commandId": "CMD-2026-901",
  "orderId": "ORD-901",
  "lineId": "LINE-2",
  "sku": "BOOK-42",
  "quantity": 2,
  "executionId": "RUN-901-A"
}
~~~

Dịch vụ gửi yêu cầu tới hệ thống kho. Hệ thống kho **đã lưu thành công việc giữ hàng** nhưng response bị mất do mạng. Caller không biết điều đó nên retry. Sau đó worker bị restart và broker giao lại message; cuối tuần một nhân viên còn thực hiện replay từ dead-letter queue (DLQ).

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as Broker
    participant C as Spring Integration consumer
    participant W as Inventory
    P->>B: ReserveCommand(commandId=CMD-901)
    B->>C: Delivery #1
    C->>W: Reserve with stable business key
    W-->>W: Commit reservation
    W--xC: ACK lost / timeout
    C->>W: Local retry, same business key
    W-->>C: Existing reservation result
    C--xB: Consumer crashes before broker ACK
    B->>C: Redelivery #2, new attempt
    C->>W: Same operation, same business key
    W-->>C: Existing reservation result
    C-->>B: ACK after durable handling
~~~

**Yêu cầu cốt lõi:** Không để một đơn hàng bị giữ thêm hai lần chỉ vì **một business command** được thực thi qua nhiều attempts.

Đồng thời, nếu chính sách cho phép đặt thêm một lần giữ hàng **mới**, hệ thống phải phân biệt nó với replay của lệnh cũ. Một khóa quá rộng như chỉ `orderId` có thể làm mất các thao tác mới hợp lệ.

## 3. Retry khác redelivery, và cả hai khác business reprocessing

| Cơ chế | Ai kích hoạt? | Cái gì thường được thực hiện lại? | Danh tính nào cần giữ ổn định? |
| --- | --- | --- | --- |
| **Local retry** | `RetryTemplate`/`RequestHandlerRetryAdvice` hoặc caller trong cùng process | Lời gọi handler có lỗi | Business command/operation ID |
| **Broker redelivery** | Kafka/JMS/AMQP consumer/container/broker theo chính sách | Message chưa ACK/commit theo transport | Business operation ID; correlation liên quan |
| **Retry topic / delayed queue** | Hệ thống retry bất đồng bộ | Bản message/record ở một kênh khác | Stable business ID, metadata liên kết gốc |
| **DLQ replay** | Công cụ/nhân viên hoặc workflow khôi phục | Message đã bị đưa vào dead-letter | Phân biệt phát lại *cùng thao tác* với thao tác mới |
| **Business reprocessing** | Nghiệp vụ yêu cầu xử lý lại toàn bộ luồng | Một execution mới trên dữ liệu cũ hoặc đã sửa | Business intent và execution policy phải explicit |

**Không giả định** local retry nhất thiết tạo một Spring `Message<?>` mới. Một advice có thể gọi lại handler với cùng message trong cùng lần dispatch. Ngược lại, redelivery qua transport có thể tạo **envelope, header hoặc delivery tag mới** trong khi nội dung nghiệp vụ vẫn chỉ là **một** lệnh.

### 3.1. At-least-once không đồng nghĩa exactly-once side effect

Một broker hoặc client có thể bảo đảm giao/đọc lại theo một số semantics nhất định, nhưng **tác dụng phụ** ở DB, API kho hoặc dịch vụ thanh toán nằm ngoài transaction của broker trừ khi có cơ chế phối hợp được thiết kế cụ thể.

~~~text
Broker delivery attempt    !=  Business operation
MessageHeaders.id          !=  Business command ID
Successful send            !=  Business commit
Retry count                !=  Duplicate detection key
Correlation ID             !=  Idempotency key (nếu chưa có contract)
~~~

Để đạt **một business effect duy nhất** khi message có thể giao lại, cần idempotency/dedup ở **nơi commit nghiệp vụ** và một khóa ổn định có ý nghĩa.

## 4. Sáu loại ID thường bị nhầm

| ID/header | Nó trả lời câu hỏi nào? | Có ổn định khi retry/redelivery? | Có nên dùng để chống trùng nghiệp vụ? |
| --- | --- | --- | --- |
| `MessageHeaders.ID` | Envelope message này được tạo với ID nào? | Có thể đổi khi dựng message mới | **Không**, trừ contract đặc biệt đã kiểm chứng |
| `businessCorrelationId` | Những hoạt động nào liên quan cùng business request? | Nên ổn định theo request | Hữu ích cho tracing, **chưa đủ** để chống trùng mọi thao tác |
| `executionId` | Các replies thuộc *lần thực thi workflow nào*? | Giữ trong một execution; **có thể đổi** ở lần chạy mới | Thường là khóa group, không thay operation key |
| `commandId` / `operationId` | Đây là cùng một ý định thay đổi trạng thái hay lệnh mới? | **Phải giữ** khi retry/replay cùng lệnh | Có, khi namespace và operation scope đủ rõ |
| `traceId` / `spanId` | Một đường thực thi phân tán có những spans nào? | Tùy cơ chế tracing; span thường thay | **Không**, tracing không phải dedup |
| Delivery ID / broker offset / attempt | Broker đã giao record/attempt nào? | Tùy transport và lần giao | **Không**, chỉ phục vụ transport/diagnostic |

Đối với **Split → xử lý từng dòng → Aggregate**, một `commandId` có thể tạo **nhiều child operations**. Mỗi child cần `lineId` hoặc `taskId` để không coi mọi dòng hàng cùng command là một thao tác.

### 4.1. Một ví dụ đầy đủ

~~~text
tenantId                shop-a
orderId                 ORD-901
commandId               CMD-2026-901
lineId                  LINE-2
operationType           RESERVE_STOCK

businessCorrelationId   ORD-901
executionId             RUN-901-A
idempotencyKey fields   shop-a/CMD-2026-901/LINE-2/RESERVE_STOCK

attempt #1              transient timeout after commit
attempt #2              local retry
delivery #2             broker redelivery
DLQ replay              manually re-published same command
~~~

Bốn lần xử lý có thể tương ứng **một operation identity duy nhất**. Nhưng một lệnh `RELEASE_STOCK` hoặc một `RESERVE_STOCK` mới được nghiệp vụ cấp `commandId` mới **không** nên bị dedup sai.

## 5. Content-based correlation là gì?

**Content-based correlation** lấy mối liên hệ từ **nội dung nghiệp vụ** hoặc metadata đã được kiểm chứng, ví dụ:

- `tenantId` + `orderId` để trace các message liên quan một đơn.
- `executionId` để gom các replies thuộc một đợt Scatter-Gather.
- `commandId` + `lineId` + `operationType` để nhận diện một side effect duy nhất.
- `invoiceId` + `invoiceVersion` để xử lý event theo phiên bản có thứ tự.

Thay vì tin rằng hai message có cùng `MessageHeaders.ID`, content-based correlation phát biểu quy tắc tường minh:

~~~text
sameOperation(a, b) :=
  a.tenantId     == b.tenantId
  AND a.commandId == b.commandId
  AND a.lineId    == b.lineId
  AND a.operation == b.operation

sameAggregationGroup(a, b) :=
  a.executionId == b.executionId
~~~

**Hai định nghĩa cố ý khác nhau.** Cùng một business operation có thể bị retry trong một execution hoặc được replay ở một execution mới. Ngược lại, một execution có thể chứa **nhiều operations** tương ứng nhiều `lineId`.

### 5.1. Chọn khóa từ phần dữ liệu có tính bất biến

Khóa correlation/dedup không nên bao gồm:

- `retryCount`, `JMSXDeliveryCount` hay số attempt.
- Timestamp **của lần xử lý hiện tại**.
- Random UUID mới sinh ở mỗi lần retry.
- ID của mỗi Spring message envelope.
- Giá trị mutable như mô tả đơn hoặc giá tính lại mỗi lần.

Nên dùng định danh đã được tạo **khi nghiệp vụ phát sinh thao tác**, lưu bền rồi giữ qua mọi ranh giới.

### 5.2. Khóa cần có namespace

`orderId=123` của tenant A và tenant B có thể trùng nhau. Vì vậy khóa dedup chỉ theo `orderId` là nguy hiểm trong hệ thống multi-tenant.

Một khóa nghiệp vụ nên gồm những phần cần thiết theo contract:

~~~text
ReservationIdentity(
    tenantId = shop-a,
    commandId = CMD-2026-901,
    lineId = LINE-2,
    operation = RESERVE_STOCK
)
~~~

Trong DB, có thể lưu **các cột riêng có UNIQUE constraint** thay vì ghép chuỗi bằng dấu phân tách dễ va chạm. Nếu phải truyền một chuỗi ra hệ thống ngoài, hãy định nghĩa canonical encoding/escaping rõ hoặc dùng một UUID/opaque operation ID đã được tạo **một lần**, có mapping bền tới business identity.

### 5.3. Không hash tùy tiện nội dung mutable để làm identity

`SHA-256(payload JSON)` có vẻ thuận tiện nhưng có thể tạo **hai khóa khác nhau** cho cùng một thao tác khi JSON đổi thứ tự field, thêm metadata, timestamp hoặc serializer. Ngược lại, hai tác vụ hợp lệ có payload giống hệt nhau có thể bị coi nhầm là duplicate.

Nếu hợp đồng thật sự yêu cầu content hash, phải xác định **canonicalization, version, scope và collision handling**. Thông thường một **operation ID ổn định do producer phát hành** có ý nghĩa rõ hơn raw payload hash.

## 6. Luồng thiết kế: correlation không bị mất sau nhiều lần xử lý

~~~mermaid
flowchart TD
    IN["Trusted inbound: Validate command and IDs"] --> D["Compute/restore stable operation identity"]
    D --> I{"Inbox / idempotency state"}
    I -->|"New"| H["Business handler"]
    I -->|"Already completed"| OLD["Reuse persisted outcome"]
    I -->|"In progress"| WAIT["Wait / retry later / reconcile"]
    H --> O["Commit business result + outbox where possible"]
    O --> R["Reply with executionId + lineId"]
    OLD --> R
    R --> A["Aggregator: group by executionId"]
    A --> F["Finalization once per execution"]
    WAIT --> E["Controlled error / delayed retry"]
~~~

**Một redelivered message có thể đi vào Inbox và được nhận diện là đã xử lý**, rồi trả lại **kết quả đã ghi**. Tuy nhiên, nếu reply cũ bị gửi lại cho một Aggregator đã hoàn thành, bản thân Aggregator cũng cần dedup/closed-group policy. Chống trùng ở **business handler** và chống trùng ở **group/finalization** là hai lớp khác nhau.

### 6.1. Correlation đúng nhưng vẫn nhân đôi side effect

Ví dụ hai message cùng `businessCorrelationId=ORD-901` vẫn có thể đều gọi `reserveStock()`. Correlation chỉ cho phép biết chúng liên quan nhau; nó **không chặn** hai lần commit.

Cần phân biệt:

~~~text
Correlation: tìm mối liên hệ
Deduplication: nhận diện bản lặp
Idempotency: xử lý lặp mà không tạo thêm effect
Ordering: quyết định message nào đi trước
Exactly-once business outcome: kết quả cần đạt bằng state/transaction
~~~

## 7. Java 17: định nghĩa business identity ổn định

Ta dùng một ví dụ đơn giản cho bài học. Các DTO là Java 17 `record`, phù hợp với một contract bất biến. Những class có thể đặt trong các file Java riêng trong cùng package.

### 7.1. Command và reservation key

~~~java
import java.util.Objects;

record ReserveCommand(
    String tenantId,
    String commandId,
    String executionId,
    String orderId,
    String lineId,
    String sku,
    int quantity
) {
    ReserveCommand {
        requireNonBlank(tenantId, "tenantId");
        requireNonBlank(commandId, "commandId");
        requireNonBlank(executionId, "executionId");
        requireNonBlank(orderId, "orderId");
        requireNonBlank(lineId, "lineId");
        requireNonBlank(sku, "sku");
        if (quantity <= 0) {
            throw new IllegalArgumentException("INVALID_QUANTITY");
        }
    }

    private static void requireNonBlank(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + "_MISSING");
        }
    }
}

record ReservationKey(
    String tenantId,
    String commandId,
    String lineId,
    String operationType
) {
    static ReservationKey from(ReserveCommand command) {
        return new ReservationKey(
            command.tenantId(),
            command.commandId(),
            command.lineId(),
            "RESERVE_STOCK");
    }
}
~~~

`executionId` **không** nằm trong `ReservationKey`. Đó là quyết định theo contract ví dụ: một replay trong execution mới của **cùng command** vẫn phải dùng lại kết quả giữ hàng cũ. Nhưng `executionId` vẫn nằm trong request/reply để biết **lượt xử lý nào đang chờ**.

Nếu nghiệp vụ cho phép **thực hiện hai lệnh giữ hàng riêng biệt** cho cùng dòng hàng, producer phải phát hành `commandId` mới có ý nghĩa; không “lách” idempotency bằng cách thay `executionId`.

### 7.2. Receipt và reply cho Aggregator

~~~java
record ReserveReceipt(
    ReservationKey reservationKey,
    String executionId,
    String lineId,
    String outcome
) {}

record ItemReply(
    String executionId,
    String lineId,
    String outcome
) {
    ItemReply {
        if (executionId == null || executionId.isBlank()
                || lineId == null || lineId.isBlank()
                || outcome == null || outcome.isBlank()) {
            throw new IllegalArgumentException("INVALID_ITEM_REPLY");
        }
    }
}
~~~

`ReserveReceipt` gồm **business identity** và **execution identity** nhưng chúng phục vụ mục đích khác nhau. Một consumer có thể lấy lại business result đã được lưu từ lần xử lý trước và xây **reply mới** với `executionId` hiện tại; không lấy một `executionId` cũ từ receipt đã persist rồi gắn nhầm vào group mới.

## 8. Demo Java: giả lập “commit rồi mất ACK”

Một lỗi rất hay xảy ra: backend đã commit thành công, caller chỉ thấy timeout nên retry. Mô hình Java sau cố ý **nếm thử lỗi ấy** bằng việc lưu kết quả trước rồi ném exception trong lần gọi đầu.

> Đoạn này là **fake trong JVM phục vụ minh họa/test**. `ConcurrentHashMap` không thay thế DB transaction, unique index hoặc idempotency ở external inventory service. Không dùng làm cơ chế durability production.

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

final class SimulatedInventoryHandler {
    private final ConcurrentMap<ReservationKey, String> committed =
        new ConcurrentHashMap<>();
    private final AtomicInteger attempts = new AtomicInteger();
    private final AtomicInteger commits = new AtomicInteger();
    private final AtomicBoolean loseFirstAck = new AtomicBoolean(true);

    public ReserveReceipt reserve(ReserveCommand command) {
        attempts.incrementAndGet();

        ReservationKey key = ReservationKey.from(command);
        String outcome = committed.computeIfAbsent(key, ignored -> {
            commits.incrementAndGet();
            return "RESERVED";
        });

        // Giả lập: side effect đã commit nhưng response bị mất.
        if (loseFirstAck.compareAndSet(true, false)) {
            throw new IllegalStateException("SIMULATED_ACK_LOSS");
        }

        return new ReserveReceipt(
            key, command.executionId(), command.lineId(), outcome);
    }

    int attempts() {
        return attempts.get();
    }

    int committedOperations() {
        return commits.get();
    }
}
~~~

Lời gọi đầu:

~~~text
attempt #1:
  computeIfAbsent(key) -> store "RESERVED", commits = 1
  throw SIMULATED_ACK_LOSS

attempt #2:
  same key -> return stored "RESERVED", commits still = 1
  return ReserveReceipt
~~~

Nếu request được giao lại lần nữa, `attempts` tăng nhưng `committedOperations` vẫn là **1** trong phạm vi đời sống fake store.

### 8.1. Không dùng fake này để suy ra production “exactly once”

- Khi process restart, `ConcurrentHashMap` mất trạng thái.
- Hai service instances có hai map riêng, không có unique constraint chung.
- Nếu việc giữ hàng ở một hệ thống ngoài diễn ra **sau** khi kiểm tra map, vẫn có race giữa “kiểm tra chưa xử lý” và “gửi lệnh”.
- Một external API có thể đã commit khi caller thấy timeout; local map chưa ghi gì.

Production cần **idempotency ở nơi side effect được thực thi** (hoặc giao thức reconciliation/chốt trạng thái với external service).

## 9. Spring Integration Java DSL: retry lời gọi handler

Spring Integration có `RequestHandlerRetryAdvice`, tích hợp với cơ chế retry của Spring Retry để gọi lại một handler khi gặp exception phù hợp. Cấu hình minh họa dưới đây chạy trong một JVM, sử dụng `DirectChannel` và `QueueChannel` để dễ quan sát.

### 9.1. Bean configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.backoff.FixedBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
@EnableIntegration
class ReservationRetryFlowConfiguration {

    @Bean("reservations.in")
    DirectChannel reservationInput() {
        return new DirectChannel();
    }

    @Bean("reservations.out")
    QueueChannel reservationOutput() {
        return new QueueChannel();
    }

    @Bean
    SimulatedInventoryHandler inventoryHandler() {
        return new SimulatedInventoryHandler();
    }

    @Bean
    RequestHandlerRetryAdvice reserveRetryAdvice() {
        RetryTemplate retry = new RetryTemplate();
        retry.setRetryPolicy(new SimpleRetryPolicy(3));

        FixedBackOffPolicy backoff = new FixedBackOffPolicy();
        backoff.setBackOffPeriod(10L);
        retry.setBackOffPolicy(backoff);

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(retry);
        return advice;
    }

    @Bean
    IntegrationFlow reserveWithRetry(
            SimulatedInventoryHandler handler,
            RequestHandlerRetryAdvice retryAdvice) {
        return IntegrationFlow.from("reservations.in")
            .handle(handler, "reserve", e -> e.advice(retryAdvice))
            .channel("reservations.out")
            .get();
    }
}
~~~

**Phụ thuộc:** ví dụ sử dụng Spring Integration Java DSL, Spring Messaging, Spring Retry và Spring Test/JUnit cho tests phía sau. Nếu ứng dụng chưa có Spring Retry, phải bổ sung dependency tương thích với stack của dự án.

`SimpleRetryPolicy(3)` có nghĩa ví dụ cho phép **tối đa ba attempts**, không phải “một lần ban đầu và ba lần thử lại”. Backoff 10 ms **chỉ để test nhanh**, không phù hợp cho một dịch vụ ngoài có nguy cơ quá tải.

### 9.2. Điều gì được giữ qua local retry?

Khi advice gọi lại handler trong cùng execution:

- `ReserveCommand.commandId`, `tenantId`, `lineId` và `operationType` phải giữ nguyên.
- `ReserveCommand.executionId` vẫn biểu thị cùng đợt xử lý.
- Không sinh `commandId` mới trong handler ở mỗi attempt.
- Trace có thể có span/attempt metadata khác, nhưng không đổi business operation identity.

Nếu retry chạy ở handler có side effect, **phải** có cơ chế idempotent ở backend. Chỉ cấu hình `RetryAdvice` không đảm bảo một tác vụ không bị nhân đôi.

### 9.3. Lỗi retryable và lỗi không retryable

Code ví dụ dùng `SimpleRetryPolicy` tổng quát cho demonstration. Trong production phải phân loại:

| Lỗi | Có nên retry cùng command? | Lý do |
| --- | --- | --- |
| Network timeout, HTTP 503 | Có điều kiện, backoff hữu hạn | Có thể transient; kết quả side effect có thể UNKNOWN |
| Throttling/rate limit | Có điều kiện, theo backoff/Retry-After | Tránh tạo bão retry |
| Payload sai schema | Không | Cùng payload sẽ sai mãi |
| Invalid tenant/forbidden | Không | Retry không sửa được quyền |
| Business rejection cuối cùng | Không | Đã có outcome nghiệp vụ terminal |
| Duplicate đã commit | Không thực hiện side effect thêm | Trả cached/recorded outcome |
| Conflict do hai payload cùng operation ID | Quarantine/reconcile | Không tự chọn bản ghi cuối |

Một **timeout sau commit** là trường hợp đặc biệt: chỉ có thể retry **an toàn** nếu bên nhận hỗ trợ idempotency/reconciliation. Không được chỉ coi timeout là bằng chứng giao dịch chưa diễn ra.

## 10. Correlation header trong Spring Messaging

Message headers có thể mang thông tin correlation để downstream theo dõi hoặc Aggregator ghép reply. Ví dụ:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

ReserveCommand command = new ReserveCommand(
    "shop-a", "CMD-2026-901", "RUN-901-A",
    "ORD-901", "LINE-2", "BOOK-42", 2);

Message<ReserveCommand> request = MessageBuilder.withPayload(command)
    .setHeader("businessCorrelationId", command.orderId())
    .setHeader("commandId", command.commandId())
    .setHeader(
        IntegrationMessageHeaderAccessor.CORRELATION_ID,
        command.executionId())
    .build();

// inputChannel.send(request);
~~~

**Ba lớp thông tin:**

- Payload `commandId` và `lineId` xác định operation.
- Header `businessCorrelationId` giúp log/trace theo đơn.
- Header `correlationId` do Spring Integration dùng cho **message-group semantics** khi cần.

**Đừng coi một header do client tự gửi là nguồn tin cậy tuyệt đối.** Ở ingress, kiểm tra chữ ký/xác thực, tenant, schema/version và đối chiếu với payload hoặc workflow registry. Nếu payload và header mâu thuẫn, từ chối/quarantine thay vì tùy tiện chọn một bên.

### 10.1. Header propagation có giới hạn

Một Transformer có thể tạo envelope mới; một HTTP/Kafka/AMQP adapter có header mapper riêng, đôi khi không chuyển một số header hoặc đổi kiểu. Khi qua boundary:

1. Định nghĩa **header contract** cần gửi.
2. Serialize correlation/command/execution IDs thành kiểu ổn định.
3. Kiểm tra identity đã xác thực ở phía nhận.
4. Test message round-trip, kể cả khi retry và DLQ replay.
5. Không serialize trực tiếp object `replyChannel` chỉ có nghĩa trong một JVM.

### 10.2. Đừng gán lại business ID từ `MessageHeaders.ID`

~~~java
// Không nên: envelope ID không đại diện cho business command
String unstableOperationId = message.getHeaders().getId().toString();

// Nên: stable business command identity từ payload/registry
ReservationKey stableKey =
    ReservationKey.from((ReserveCommand) message.getPayload());
~~~

Dòng thứ hai chỉ an toàn khi command đã được validate và nguồn được xác thực. Kẻ gửi không đáng tin có thể **mạo danh cùng operation ID** để chiếm kết quả cũ hoặc gây từ chối xử lý; store phải scope theo tenant/principal và kiểm tra content consistency.

## 11. JUnit: retry tại handler không nhân đôi commit trong fake

Ví dụ tích hợp với Spring Test. Test kiểm tra rằng handler được gọi lại sau lỗi mất ACK giả lập nhưng số business commit trong fake vẫn bằng một.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.annotation.DirtiesContext;

@SpringJUnitConfig(ReservationRetryFlowConfiguration.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ReservationRetryFlowTest {

    @Autowired @Qualifier("reservations.in")
    MessageChannel input;

    @Autowired @Qualifier("reservations.out")
    PollableChannel output;

    @Autowired
    SimulatedInventoryHandler handler;

    private static ReserveCommand command(String executionId) {
        return new ReserveCommand(
            "shop-a", "CMD-2026-901", executionId,
            "ORD-901", "LINE-2", "BOOK-42", 2);
    }

    @Test
    void localRetryKeepsBusinessOperationStable() {
        ReserveCommand c = command("RUN-901-A");

        assertTrue(input.send(
            MessageBuilder.withPayload(c).build()));

        Message<?> reply = output.receive(1000);
        assertNotNull(reply);
        assertInstanceOf(ReserveReceipt.class, reply.getPayload());

        ReserveReceipt result = (ReserveReceipt) reply.getPayload();
        assertEquals("RUN-901-A", result.executionId());
        assertEquals("LINE-2", result.lineId());
        assertEquals("RESERVED", result.outcome());

        assertEquals(2, handler.attempts());
        assertEquals(1, handler.committedOperations());
        assertNull(output.receive(0));
    }

    @Test
    void redeliveryCanCreateAnotherReplyButNotAnotherCommit() {
        ReserveCommand c = command("RUN-901-A");

        Message<ReserveCommand> delivery1 =
            MessageBuilder.withPayload(c).build();
        Message<ReserveCommand> delivery2 =
            MessageBuilder.withPayload(c).build();

        // Hai envelopes mới có thể khác ID,
        // nhưng vẫn mang cùng business operation.
        assertNotEquals(
            delivery1.getHeaders().getId(),
            delivery2.getHeaders().getId());

        assertTrue(input.send(delivery1));
        assertNotNull(output.receive(1000));

        assertTrue(input.send(delivery2));
        assertNotNull(output.receive(1000));

        assertEquals(3, handler.attempts());
        assertEquals(1, handler.committedOperations());
    }

    @Test
    void newExecutionOfSameCommandStillReusesBusinessEffect() {
        assertTrue(input.send(MessageBuilder
            .withPayload(command("RUN-901-A")).build()));
        ReserveReceipt first =
            (ReserveReceipt) output.receive(1000).getPayload();

        assertTrue(input.send(MessageBuilder
            .withPayload(command("RUN-901-B")).build()));
        ReserveReceipt replay =
            (ReserveReceipt) output.receive(1000).getPayload();

        assertEquals(first.reservationKey(), replay.reservationKey());
        assertNotEquals(first.executionId(), replay.executionId());
        assertEquals(1, handler.committedOperations());
    }
}
~~~

**Điều test chứng minh và không chứng minh:**

- Chứng minh: trong một JVM với fake idempotent map, **số attempts có thể lớn hơn số commits**.
- Chứng minh: redelivery có thể tạo **nhiều replies** dù side effect chỉ một.
- Chứng minh: một execution mới có thể dùng lại business result cũ mà vẫn phát reply có `executionId` mới.
- **Không chứng minh:** durable dedup qua restart, transaction với kho ngoài, broker acknowledgment, hoặc exactly-once output của Aggregator.

**Hệ quả quan trọng:** chống trùng business operation **không tự chặn** phản hồi trùng ở những bước sau. Aggregator và finalization còn phải có policy riêng.

## 12. Redelivery thật trên JMS, AMQP, Kafka: không có một counter chung

Khi triển khai với broker, phải xem semantics cụ thể của transport và connector.

| Transport | Cơ chế thường liên quan redelivery | Điều cần kiểm chứng |
| --- | --- | --- |
| **JMS** | Session transaction/acknowledgment và provider redelivery; một số provider cung cấp `JMSRedelivered`/`JMSXDeliveryCount` | Provider hỗ trợ counter nào; commit/rollback và DLQ semantics |
| **AMQP/RabbitMQ** | Consumer ACK/NACK/reject, requeue, dead-letter, retry queue | `redelivered` flag, DLX/x-death headers và chính sách requeue; không suy delivery count tùy tiện |
| **Kafka** | Consumer offsets, retry ở container hoặc retry topics, rebalances/reprocess | Offset commit, partition/order, record key, retry-topic headers nếu dùng |
| **HTTP webhook** | Sender retry theo chính sách riêng, có thể gửi request mới | Event ID, signature, timestamp validity window, idempotency contract |
| **Internal queue** | Poller/executor/redelivery tùy channel/store | Queue có durable không, retry/ack ở endpoint nào |

### 12.1. `deliveryCount` không phải khóa correlation

Counter tăng theo attempt, có thể reset hoặc không có khi message được republish sang retry topic/DLQ. Nó tốt cho metrics và quyết định **giới hạn retry**, nhưng không ổn định để nhận diện operation.

### 12.2. Kafka offset không phải business ID

Một record Kafka có topic, partition và offset, nhưng **business operation có thể được republish sang topic khác hoặc offset mới**. Nếu dedup theo offset, một replay thủ công của cùng `ReserveCommand` sẽ đi qua.

Chọn Kafka record key theo phân vùng/ordering khi cần, nhưng business idempotency vẫn phải dựa vào **command/operation identity**. Nếu dùng Kafka transactions, nhớ rằng chúng không tự mở rộng tính nguyên tử sang một API kho hoặc database tùy ý bên ngoài transaction.

### 12.3. AMQP và JMS: ACK sau khi có độ bền phù hợp

Nếu worker ACK broker trước khi kết quả nghiệp vụ được commit hoặc lưu an toàn, crash giữa hai bước có thể mất công việc. Nếu commit xong rồi ACK thất bại, broker sẽ có thể redeliver. Thiết kế chịu được **cả hai cửa sổ lỗi** bằng durable state và idempotency.

Không mặc định ACK tại channel nội bộ đồng nghĩa external provider đã hoàn tất.

## 13. DLQ replay: cùng operation hay một workflow mới?

Một message bị dead-letter do vượt số lần retry. Khi quyết định phát lại, cần đặt câu hỏi:

1. Dữ liệu gốc vẫn đúng contract không?
2. Đây là **re-delivery cùng command** hay một yêu cầu nghiệp vụ mới?
3. Hệ thống đích có thể đã commit thao tác cũ không?
4. Correlation group cũ còn mở hay đã `EXPIRED/COMPLETE`?
5. Bên nhận đang dùng schema/policy version nào khi replay?

### 13.1. Replay cùng command

Giữ nguyên `tenantId`, `commandId`, `lineId`, `operationType`. Có thể dùng một `executionId` mới nếu bắt đầu một workflow được phép reprocess, nhưng phải lập mapping và policy rõ để không trộn replies của đợt cũ.

~~~text
Original:
  operation key = (shop-a, CMD-901, LINE-2, RESERVE_STOCK)
  execution = RUN-901-A

DLQ replay:
  same operation key
  execution = RUN-901-B (new processing run)
  replayOf = RUN-901-A
~~~

Kết quả từ inventory phải được dedup bởi **operation key**, còn reply của lần chạy mới có thể được đưa vào group `RUN-901-B`.

### 13.2. Thao tác nghiệp vụ mới

Nếu nhân viên chủ đích tạo một lệnh bổ sung **khác** với lệnh cũ, phải phát hành `commandId` mới và lưu lý do/authorization phù hợp. Không thay `commandId` chỉ để “retry cho chạy lại” một thao tác đã có thể commit.

### 13.3. Không bỏ qua schema version

DLQ có thể giữ message nhiều ngày. Khi replay, serializer/mapper hiện tại có thể chỉ hỗ trợ schema mới. Cần versioned decoder và migration policy; không tự hiểu message `v1` theo `v2` nếu trường/đơn vị tiền đã thay đổi.

## 14. Aggregator và Scatter-Gather: correlation qua reply lặp

Một lệnh batch giữ hàng có ba dòng:

~~~text
execution RUN-901-A
expected LINE-1, LINE-2, LINE-3

Incoming:
  LINE-1 -> RESERVED
  LINE-2 -> RESERVED
  LINE-2 -> RESERVED (duplicate due to redelivery)
  LINE-3 -> not arrived
~~~

Nếu release strategy chỉ kiểm tra `group.size() >= 3`, nhóm có thể **bị release sai** dù LINE-3 chưa có.

### 14.1. Group theo execution, release theo item ID duy nhất

~~~text
Group key      = executionId
Unique item key = lineId
Release when   = all expected line IDs have terminal valid results
~~~

`executionId` phải được lấy từ **payload/metadata đã xác minh**. `lineId` phải nằm trong expected set, không được do một reply bên ngoài tự thay đổi.

### 14.2. Pure Java release policy minh họa

~~~java
import java.util.Collection;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

final class ReplyCompletionPolicy {
    private ReplyCompletionPolicy() {}

    static boolean allExpectedReceived(
            String executionId,
            Set<String> expectedLineIds,
            Collection<ItemReply> replies) {

        Map<String, ItemReply> unique = new HashMap<>();

        for (ItemReply reply : replies) {
            if (reply == null
                    || !executionId.equals(reply.executionId())
                    || !expectedLineIds.contains(reply.lineId())) {
                throw new IllegalArgumentException("UNEXPECTED_REPLY");
            }

            ItemReply previous =
                unique.putIfAbsent(reply.lineId(), reply);
            if (previous != null && !previous.equals(reply)) {
                throw new IllegalArgumentException(
                    "CONFLICTING_DUPLICATE_REPLY");
            }
        }

        return unique.keySet().equals(expectedLineIds);
    }
}
~~~

**Điều kiện:** `expectedLineIds` được lấy từ nguồn tin cậy, không rỗng nếu workflow cần ít nhất một phần; caller chịu trách nhiệm kiểm tra group key và policy trước hàm này. Đây là một **pure policy**, không phải một custom Aggregator hoàn chỉnh với store, timeout và side effects.

### 14.3. Test duplicate trước release

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class ReplyCompletionPolicyTest {

    @Test
    void duplicateDoesNotReplaceMissingLine() {
        Set<String> expected =
            Set.of("LINE-1", "LINE-2", "LINE-3");

        List<ItemReply> received = List.of(
            new ItemReply("RUN-901-A", "LINE-1", "RESERVED"),
            new ItemReply("RUN-901-A", "LINE-2", "RESERVED"),
            new ItemReply("RUN-901-A", "LINE-2", "RESERVED"));

        assertFalse(ReplyCompletionPolicy.allExpectedReceived(
            "RUN-901-A", expected, received));
    }

    @Test
    void receivesAllUniqueLinesOutOfOrder() {
        Set<String> expected =
            Set.of("LINE-1", "LINE-2", "LINE-3");

        List<ItemReply> received = List.of(
            new ItemReply("RUN-901-A", "LINE-3", "RESERVED"),
            new ItemReply("RUN-901-A", "LINE-1", "RESERVED"),
            new ItemReply("RUN-901-A", "LINE-2", "RESERVED"));

        assertTrue(ReplyCompletionPolicy.allExpectedReceived(
            "RUN-901-A", expected, received));
    }

    @Test
    void rejectsConflictingDuplicate() {
        Set<String> expected = Set.of("LINE-1");

        List<ItemReply> conflicting = List.of(
            new ItemReply("RUN-901-A", "LINE-1", "RESERVED"),
            new ItemReply("RUN-901-A", "LINE-1", "FAILED"));

        assertThrows(IllegalArgumentException.class, () ->
            ReplyCompletionPolicy.allExpectedReceived(
                "RUN-901-A", expected, conflicting));
    }
}
~~~

### 14.4. Khi nào nên dedup reply trước Aggregator?

Một cách vững chắc là dedup/validate replies tại **inbox trước Gatherer**. Nếu các replies đã được thêm vào group, release strategy và output processor vẫn phải đối phó với duplicate và conflicting result. Nếu một duplicate có thể đến **sau khi group đã đóng**, cần closed-group registry/tombstone hoặc duplicate detector để không tạo group mới.

## 15. Group đã hoàn thành nhưng reply vẫn đến

Giả sử Aggregator đã tạo `BatchOutcome(COMPLETE)` cho `RUN-901-A` và xóa group khỏi store. Broker sau đó giao lại reply của `LINE-2`:

~~~text
RUN-901-A, LINE-2, RESERVED (redelivery)
    |
    v
Aggregator group no longer exists
    |
    v
Could create a new incomplete group with same key
~~~

Một **closed-execution registry** giúp phân biệt:

~~~text
Incoming ItemReply
    |
    +--> execution OPEN
    |        -> validate + dedup + group
    |
    +--> execution COMPLETE
    |        -> duplicate audit / idempotent no-op
    |
    +--> execution EXPIRED
    |        -> late reply / reconcile
    |
    +--> execution UNKNOWN
             -> reject / quarantine
~~~

**Không chọn `expireGroupsUponCompletion(true)` rồi cho rằng late replies tự biến mất.** Khi group đã bị xóa, state mới có thể được tạo nếu không có chính sách ngăn.

### 15.1. Race giữa reply cuối và timeout

Hai thread có thể cùng quan sát trạng thái:

~~~text
Thread A: final reply arrives, should COMPLETE
Thread B: deadline sees one missing, should EXPIRE
~~~

Cần một transition **nguyên tử** trên execution như `OPEN → COMPLETE` **hoặc** `OPEN → EXPIRED`. Dù một outcome thắng theo thứ tự commit, chỉ **một kết quả cuối** được phát; dùng database CAS/transaction hoặc state machine + outbox thích hợp.

### 15.2. Zero replies không tự có group

Nếu không có reply nào tới, Aggregator có thể chưa có group để `groupTimeout` kích hoạt. Deadline watcher ở **request/execution registry** phải tạo outcome `NO_REPLIES`, không chỉ dựa vào timeout của một group không tồn tại.

### 15.3. Replay sau timeout

Nếu một execution đã `EXPIRED` nhưng operator cần chạy lại, tạo **execution ID mới** theo chính sách (ví dụ `RUN-901-B`), giữ business operation keys cũ nếu vẫn là **cùng command**. Replies mới phải được map vào group mới, nhưng không được lặp side effects ở backend.

## 16. Durable idempotency: chỉ nhớ trong RAM là chưa đủ

Production cần xử lý các trường hợp process restart, nhiều consumer nodes, broker redelivery và recovery sau khi đã gọi external API.

### 16.1. Unique constraint trên operation key

Một bảng minh họa:

~~~sql
CREATE TABLE reservation_operation (
    tenant_id       VARCHAR(80) NOT NULL,
    command_id      VARCHAR(120) NOT NULL,
    line_id         VARCHAR(120) NOT NULL,
    operation_type  VARCHAR(40) NOT NULL,
    request_hash    VARCHAR(64) NOT NULL,
    state           VARCHAR(30) NOT NULL,
    result_json     TEXT,
    updated_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, command_id, line_id, operation_type)
);
~~~

**Ý nghĩa `request_hash`:** có thể giúp phát hiện **cùng identity nhưng hai payload xung đột**. Tuy nhiên phải định nghĩa canonicalization/version của những field ảnh hưởng nghiệp vụ; không hash tùy tiện toàn bộ JSON bao gồm retry metadata. Nếu hai requests cùng operation key nhưng khác SKU/quantity, **đừng** trả cached success mà không so sánh contract — điều đó có thể che lỗi hoặc bị lợi dụng để nhận nhầm kết quả.

### 16.2. State machine minh họa

~~~mermaid
flowchart LR
    N["NEW"] --> P["PROCESSING (claimed)"]
    P --> C["COMPLETED (durable result)"]
    P --> R["RETRYABLE / UNKNOWN"]
    R --> P
    P --> F["FAILED_FINAL"]
    C --> DUP["Duplicate -> same result, no new effect"]
    F --> DUPF["Duplicate -> same terminal error"]
~~~

Cần một **unique insert/CAS** để chỉ một worker sở hữu operation hợp lệ. Nếu worker chết ở `PROCESSING`, phải có lease/timeout/recovery; đừng để operation kẹt mãi. Nếu backend external không cung cấp idempotency, state local **không thể tự phân giải** trường hợp “external đã commit nhưng local chưa ghi result”; cần status lookup/reconciliation hoặc giao thức có idempotency token ở backend.

### 16.3. Inbox và outbox xử lý hai vấn đề khác nhau

- **Inbox/processed-message ledger:** nhận diện message/operation đã nhận và đã commit, chặn xử lý trùng.
- **Outbox:** lưu event cần phát ra **cùng transaction** với dữ liệu nghiệp vụ trong hệ thống sở hữu DB, để publisher retry mà không mất thông báo.
- **Idempotent external API:** backend chấp nhận stable operation key và trả cùng outcome cho nhiều lần gọi.
- **Aggregator closed-state:** bảo đảm một execution không phát hai final outcomes.

Một hệ thống có thể cần **cả bốn**. Không có một flag duy nhất `retry=true` hoặc `exactlyOnce=true` thay thế các lớp này.

## 17. Ranh giới DB và external API: không thể transaction bằng ý muốn

Ví dụ handler:

~~~text
1. Begin DB transaction
2. Check command operation key
3. Call external Inventory API
4. Persist local result
5. Commit DB transaction
6. ACK broker
~~~

Nếu bước 3 đã commit ở hệ thống kho nhưng bước 4 thất bại, DB local **không biết kết quả**. Một DB transaction không tự rollback hệ thống kho. Nếu broker redeliver, handler phải:

1. Tra cứu operation theo stable key ở backend (nếu hỗ trợ).
2. Hoặc gọi lại API idempotent với cùng key.
3. Hoặc chuyển `UNKNOWN` sang reconciliation/manual review.

**Không** mặc định có thể “thử lại an toàn” một charge/payment/reservation chỉ vì DB local chưa có row `COMPLETED`.

### 17.1. Tại nơi side effect xảy ra

Một thiết kế lý tưởng là business owner lưu operation key **cùng transaction với mutation**:

~~~text
BEGIN
  INSERT operation_key IF ABSENT
  IF already committed: RETURN stored outcome
  ELSE apply business mutation
       SAVE outcome
COMMIT
~~~

Với nhiều transactions hoặc external systems, chi tiết thay đổi nhưng nguyên tắc là: kiểm tra idempotency phải ở **cùng ranh giới nhất quán** với side effect, hoặc có cách reconcile khi ranh giới không thể atomic.

## 18. Header propagation, tracing và security

### 18.1. Header qua nhiều lần xử lý

~~~text
Inbound:
  payload.commandId = CMD-901
  payload.executionId = RUN-901-A
  headers.businessCorrelationId = ORD-901

Retry within handler:
  same business identity, perhaps same envelope

Broker redelivery:
  new delivery metadata, business identity unchanged

DLQ replay:
  new envelope/transport headers may appear,
  stable operation identity must survive
~~~

Không bảo đảm `traceId` hay `spanId` giữ cùng giá trị qua manual replay. Nếu cần liên kết traces, lưu `originalEventId` hoặc `replayOf` dưới metadata có kiểm soát, song vẫn phân biệt trace mới với transaction nghiệp vụ cũ.

### 18.2. Không tin `commandId` tự khai là quyền

Một client có thể đặt `commandId` trùng operation của tenant khác nhằm dò/chiếm kết quả. Scope idempotency phải bao gồm tenant/principal đáng tin; không tiết lộ cached result nếu caller không có quyền xem operation đó.

Với HTTP webhook, kiểm tra chữ ký/timestamp/replay window và identity source. Với broker, kiểm tra ACL/producer identity, schema/version và tenant mapping. Nếu header business correlation và payload mâu thuẫn, cần lỗi có lý do thay vì silently accepting.

### 18.3. Tránh PII trong khóa và metrics

Đừng dùng địa chỉ email, số điện thoại hay mã căn cước thô làm dedup key nếu không cần. Ưu tiên opaque IDs ổn định và scope rõ. `commandId`, `orderId` và `executionId` có cardinality cao; nên ở logs/traces có phân quyền thay vì metric labels.

## 19. Retry policy và retry budget

Retry không nên vô hạn. Một lỗi tạm thời khi downstream quá tải có thể khiến cả hệ thống đồng loạt retry và làm sự cố nặng thêm.

| Chính sách | Mục đích | Cách áp dụng |
| --- | --- | --- |
| Max attempts | Chặn loop vô hạn | Cấu hình theo loại lỗi và SLA |
| Backoff + jitter | Tránh retry storm | Delay tăng dần, phân tán |
| Timeout mỗi attempt | Giới hạn thời gian gọi ngoài | Không để thread giữ vô hạn |
| End-to-end deadline | Giới hạn tổng thời gian của command/execution | Đếm cả queue wait + retries |
| Circuit breaker / rate limit | Bảo vệ downstream | Từ chối/defer khi quá tải |
| Retryable exception set | Không retry dữ liệu sai/permanent rejection | Classify errors |
| DLQ + reconciliation | Giữ bằng chứng cho lỗi khó sửa tự động | Không tự xác nhận side effect chưa xảy ra |

### 19.1. Retry budget khác delivery count

Một worker có thể thử local 3 lần, broker redelivery 2 lần và một DLQ replay lại thử local 3 lần:

~~~text
3 local attempts × 2 broker deliveries + 3 replay attempts
= up to 9 handler attempts
~~~

Đây chỉ là ví dụ tính tổng attempts, không phải mặc định của Spring Integration. **Cần tổng hợp ngân sách retry ở nhiều tầng** để tránh retry vô hạn vì mỗi tầng tự đặt max attempts nhưng liên tục đẩy sang tầng khác.

### 19.2. Giữ business key qua từng tầng

Dù 9 attempts, `ReservationKey(shop-a, CMD-901, LINE-2, RESERVE_STOCK)` vẫn là **một operation**. Attempt count là metadata chẩn đoán, không tham gia idempotency key.

## 20. Ma trận kiểm thử

| Kịch bản | Input/diễn biến | Điều cần assert |
| --- | --- | --- |
| Happy path | Một command lần đầu | Một commit và một reply đúng |
| Local retry | Commit xong nhưng lost ACK | Attempt tăng; business commit chỉ một |
| Broker redelivery | Cùng command, envelope mới | Stable operation key; không commit thêm |
| New execution of same command | RUN-A → RUN-B | New reply group, old business result |
| New command for same order/line | Command ID mới | Không dedup nhầm nếu nghiệp vụ cho phép |
| Different tenant, same command ID | shop-a và shop-b | Hai namespaces riêng, không leak kết quả |
| Duplicate reply | LINE-2 hai lần | Unique count không tăng |
| Conflicting duplicate | LINE-2 RESERVED và FAILED | Reject/reconcile, không tùy tiện chọn |
| Out-of-order replies | LINE-3, LINE-1, LINE-2 | Group đúng, complete theo unique IDs |
| Missing one reply | 2/3 trước deadline | Chờ/partial/timeout đúng policy |
| Zero replies | Chưa có group | Request deadline watcher phát timeout |
| Late reply after completion | Group đã đóng | Không tạo final outcome thứ hai |
| Reaper/group removed | Metadata group bị xóa | Tombstone chặn mở lại trái phép |
| Process restart | Inbox state trước/sau crash | Durable dedup/recovery |
| Two instances race | Cùng key đến hai workers | DB constraint/CAS ngăn double commit |
| Retry count reset | Republish từ DLQ | Operation key không đổi |
| Request payload conflict | Cùng key, quantity khác | Không trả cached result của command khác |
| Header mapping | Qua JMS/AMQP/Kafka | IDs quan trọng còn nguyên kiểu/ý nghĩa |
| AuthZ spoofing | Client dùng key của tenant khác | Deny, không trả cached data |
| Tracing | Retry/replay span mới | Liên kết điều tra mà không dùng span ID để dedup |
| Outbox republish | Event publish lặp | Idempotent consumer/finalizer |
| External system UNKNOWN | Timeout sau có thể commit | Reconciliation; không tự tạo command mới |

**Thực hành tốt:** ngoài test kết quả **được tạo**, phải assert các side effects **không được lặp**. Không chỉ assert số messages đầu ra nếu mục tiêu là “giữ hàng đúng một lần”.

## 21. Observability: nhìn được correlation qua các attempts

Nếu hệ thống chỉ log `message processed`, rất khó biết hai lần xử lý là hai lệnh hợp lệ hay một redelivery.

| Điểm đo | Signal | Mục đích |
| --- | --- | --- |
| Ingress | Command accepted/rejected, source, schema version | Phát hiện dữ liệu sai |
| Retry advice | Attempts, exception class, retry exhausted | Thấy local retries |
| Broker consumer | Redelivery/rebalance/retry-topic volume | Thấy transport retries |
| Idempotency layer | New, hit, conflict, in-progress | Đo duplicate và contention |
| Business backend | Operation committed/reused, latency | Biết effect thực sự |
| Aggregator | Open groups, unique replies, duplicates, late | Phát hiện group sai |
| DLQ/replay | Backlog, replay reason, operator actions | Theo dõi reprocessing |
| Outbox | Pending age, publication retries | Bảo đảm kết quả được phát |
| Finalization | COMPLETE/EXPIRED and final emit count | Chặn phát final hai lần |

Một log minh họa:

~~~json
{
  "event": "reservation_retry_completed",
  "tenant": "shop-a",
  "commandId": "CMD-2026-901",
  "lineId": "LINE-2",
  "executionId": "RUN-901-A",
  "businessResult": "RESERVED",
  "idempotency": "REUSED",
  "attempt": 2,
  "cause": "REMOTE_ACK_TIMEOUT"
}
~~~

Đây là **schema log ứng dụng minh họa**, không phải field Spring Integration tự sinh. Với dữ liệu nhạy cảm, cần masking/tokenization và quyền truy cập phù hợp. Tránh tag metrics theo command/line/execution ID vì cardinality cao.

## 22. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Dùng `MessageHeaders.id` làm idempotency key | Envelope mới tạo side effect trùng | Stable command/operation identity |
| Dùng `retryCount` làm correlation ID | Mỗi attempt thành group khác nhau | Để attempt count chỉ là metadata |
| Dùng chỉ `orderId` cho mọi thao tác | Các dòng/operation mới bị bỏ nhầm | Thêm commandId, lineId, operationType |
| Sinh commandId mới trong mỗi attempt | Không còn idempotency | Sinh một lần ở producer, persist |
| Hash toàn bộ JSON thô để dedup | Metadata/field order gây false negatives | Operation ID hoặc canonicalized contract rõ |
| Đếm `group.size()` là đủ replies | Duplicate thay item bị thiếu | Unique business item IDs |
| Xóa group xong quên late reply | Group mới/final thứ hai | Tombstone/closed-state |
| Retry tất cả lỗi | Validation/permanent error không được sửa | Classify retryable vs terminal |
| Tin HTTP timeout nghĩa là chưa commit | Side effect có thể đã xảy ra | Backend idempotency + status lookup |
| Check idempotency ngoài DB transaction rồi commit | Race giữa hai workers | Unique index/CAS cùng consistency boundary |
| Dùng map in-memory cho durable dedup | Restart/multi-node mất trạng thái | Durable store, locks, conflict policy |
| DLQ replay với commandId mới tùy tiện | Lặp business operation | Giữ key khi replay cùng command |
| Dùng executionId như operation key duy nhất | Reprocess hợp lệ có thể gây commit trùng | Group key và business key tách biệt |
| Dùng correlationId do client tự khai làm quyền | Spoof/IDOR/cross-tenant | AuthN/AuthZ và trusted validation |
| Coi broker ACK = business success | Kết luận sai khi handler chưa commit | Theo dõi committed outcome |
| Chỉ test retry happy path | Không phát hiện ACK-loss window | Inject failure after commit |
| Log PII hoặc token trong key | Rò rỉ dữ liệu | Opaque stable IDs và secure logging |

## 23. Checklist trước khi triển khai

- [ ] Định nghĩa rõ business command/operation identity cho từng side effect.
- [ ] Operation key có tenant/source namespace, commandId, itemId và operationType nếu cần.
- [ ] Định nghĩa **group correlation key** riêng cho Aggregator/Scatter-Gather execution.
- [ ] Không dùng envelope ID, retry count, delivery tag hoặc trace span làm business idempotency key.
- [ ] Producer sinh commandId ổn định một lần và giữ qua local retry/broker redelivery/DLQ replay.
- [ ] Mọi incoming identity được validate với authentication/tenant/schema contract.
- [ ] Có chính sách **cùng key nhưng payload khác**: reject/quarantine/compare request hash.
- [ ] Backend có durable idempotency hoặc reconciliation khi external API không hỗ trợ.
- [ ] Inbox/outbox và ACK order được thiết kế chống crash windows.
- [ ] RequestHandlerRetryAdvice có retryable exception policy, max attempts, backoff và timeout.
- [ ] Retry budget ở nhiều tầng không tạo storm hoặc vòng lặp vô hạn.
- [ ] Reply duplicate/late/out-of-order không làm Aggregator release sai hoặc finalization hai lần.
- [ ] Group store, closed-execution registry và deadline watcher có retention tương ứng replay window.
- [ ] Header mapping được test qua JMS/AMQP/Kafka/HTTP nếu sử dụng.
- [ ] Có unit/integration tests injecting failure **sau commit trước ACK**.
- [ ] Có monitoring cho retries, duplicate hits, conflicts, in-progress stuck và DLQ.
- [ ] Logs/traces có correlation nhưng không tạo metric tags cardinality cao hoặc rò thông tin nhạy cảm.

## 24. Bài tập vận dụng

Một ứng dụng thanh toán nhận các event `PaymentRequested` mang `tenantId`, `paymentId`, `commandId`, `executionId`, `amountMinor`, `currency`. Events được gửi đến một **Payment Gateway** và sau đó kết quả được gom vào một **Aggregator** cùng các bước fraud check và invoice creation.

**Điều kiện:**

- Cùng một `commandId` được broker redeliver tối đa nhiều lần theo transport.
- Gateway có thể charge thành công rồi timeout, khiến worker không nhận reply.
- Một người vận hành có thể replay DLQ sau một ngày.
- Nếu khách hàng cố ý thanh toán một khoản mới hợp lệ, phải có `commandId` mới.
- Có thể có hai `executionId` khác nhau cùng xử lý lại một business command cũ.

**Yêu cầu:**

1. Định nghĩa `PaymentOperationIdentity`. Giải thích vì sao không dùng `MessageHeaders.id`, Kafka offset hoặc retry count để chống charge trùng.
2. Vẽ sơ đồ retry/redelivery và chỉ ra cửa sổ lỗi **charge committed → ACK lost**.
3. Viết Java record cho `PaymentRequested`, `PaymentOutcome` và `PaymentOperationKey`.
4. Thiết kế Spring Integration `RequestHandlerRetryAdvice` có retryable/error-exhaustion policy.
5. Thiết kế durable idempotency ở Payment Gateway hoặc DB chịu trách nhiệm payment mutation, có unique constraint và request fingerprint.
6. Viết test: local retry sau ACK loss, broker redelivery, DLQ replay, conflicting amount cùng command ID, new command hợp lệ.
7. Định nghĩa correlation group cho replies từ fraud/payment/invoice theo executionId; tránh duplicate payment reply bị đếm là một component thứ tư.
8. Với late reply sau Aggregator complete, mô tả tombstone/reconciliation và cơ chế không phát final outcome lần hai.
9. Nếu Payment Gateway không có API idempotency nhưng có API tra cứu transaction, thiết kế reconciliation trước retry để giảm nguy cơ double charge.
10. Đề xuất logging/metrics an toàn: retries, unique business operations, dedup hits, conflicts, timeout, DLQ và late replies; không log thông tin thanh toán nhạy cảm.

**Gợi ý:** Sử dụng **một business operation key bất biến** cho charge, **execution ID riêng** cho group, và **transport metadata riêng** cho diagnostic. Đảm bảo mọi tầng thử lại không sinh lại ý định nghiệp vụ mới khi chỉ đang giao lại cùng message.

## 25. Tổng kết

**Correlation qua retry và redelivery** yêu cầu phân biệt **“cùng công việc”** với **“cùng lần giao message”**. Message envelope, broker delivery tag và attempt count có thể thay đổi; **business operation identity** phải ổn định khi một command được thử lại hoặc phát lại. Trong khi đó, **correlation group của Aggregator** có thể thay đổi khi một workflow được reprocess, còn **idempotency key** phải tiếp tục bảo vệ side effect của cùng command.

Với Spring Integration, có thể dùng Java DSL và `RequestHandlerRetryAdvice` cho retry tại handler, nhưng phải kết hợp **dedup/inbox, idempotent backend, durable transaction/outbox, error channel, DLQ replay policy và closed-group registry**. Khi một phần được giao lại, Aggregator đếm **unique item results** chứ không đếm raw message count; khi reply đến muộn, không tạo một kết quả cuối thứ hai. Kết quả mong muốn không chỉ là message được chuyển tới đúng nhánh, mà là **đúng business operation, đúng correlation group, đúng số lần tạo side effect và có thể truy vết qua mọi lần thử**.

**Tài liệu tham khảo:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Correlation Identifier, Message Sequence, Idempotent Receiver, Aggregator, Request-Reply, Guaranteed Delivery); tài liệu Spring Integration về Request Handler Advice/Retry, Aggregators, Message Channels, Error Handling, Message Stores, Java DSL và Testing; tài liệu Spring Retry về RetryTemplate, RetryPolicy và BackOffPolicy; tài liệu Java SE về record, ConcurrentHashMap và concurrency primitives.

