# Xây dựng pipeline sự kiện với hàm serverless và xử lý lỗi

## Mục tiêu dự án

Trong dự án này, bạn xây dựng một pipeline xử lý sự kiện bất đồng bộ bằng hàm serverless. Pipeline nhận sự kiện nghiệp vụ, kiểm tra hợp đồng dữ liệu, đưa sự kiện vào hàng đợi, gọi function để xử lý, lưu kết quả và phát sự kiện tiếp theo. Khi xử lý thất bại, hệ thống retry có giới hạn, cách ly message lỗi vào dead-letter queue (DLQ), phát cảnh báo và cho phép phục hồi bằng redrive có kiểm soát.

Bài toán mẫu là xử lý đơn hàng trực tuyến. Dịch vụ Order API phát sự kiện OrderPlaced sau khi đơn hàng được tạo. Một function xử lý sự kiện kiểm tra dữ liệu, xác nhận tồn kho và cập nhật trạng thái đơn. Khi dependency tạm thời lỗi, message được thử lại. Khi message không thể xử lý sau chính sách retry, queue chuyển nó sang DLQ để điều tra. Sau khi nguyên nhân được sửa, operator có thể phát lại các message hợp lệ mà không tạo đơn hoặc giữ hàng trùng lặp.

Dự án giúp kết hợp các năng lực compute cloud đã học: queue, event bus, serverless functions, storage, identity, autoscaling, monitoring, retry, idempotency và tối ưu chi phí.

Sau khi hoàn thành, bạn có thể:

- Thiết kế luồng sự kiện bất đồng bộ có queue làm bộ đệm.
- Xác định event contract, schema version và idempotency key.
- Viết producer và serverless consumer có trách nhiệm rõ ràng.
- Xử lý duplicate, retry, timeout, poison message và partial batch failure.
- Cấu hình DLQ, retention, redrive và cảnh báo.
- Giới hạn concurrency và backpressure để bảo vệ dependency.
- Quan sát toàn bộ vòng đời sự kiện từ publish tới kết quả cuối.
- Bảo vệ payload, credential và quyền truy cập.
- Kiểm thử lỗi có chủ đích và chứng minh khả năng phục hồi.
- Đánh giá chi phí theo số sự kiện xử lý thành công.

## 1. Bối cảnh và yêu cầu nghiệp vụ

Một cửa hàng trực tuyến tiếp nhận nhiều đơn hàng. Sau khi Order API tạo đơn, các công việc sau có thể chạy độc lập:

- Kiểm tra và giữ hàng trong kho.
- Tính toán thông tin giao nhận.
- Gửi thông báo xác nhận.
- Cập nhật dữ liệu phân tích.
- Phát event cho hệ thống downstream.

Nếu Order API gọi trực tiếp tất cả dịch vụ theo chuỗi đồng bộ, thời gian phản hồi sẽ phụ thuộc vào mọi dependency. Một dịch vụ chậm có thể làm request tạo đơn bị timeout dù dữ liệu đơn hàng đã được ghi. Khi lượng đơn tăng, các dịch vụ phụ thuộc cũng có thể bị quá tải cùng lúc.

Pipeline sự kiện tách việc tiếp nhận đơn hàng khỏi các bước xử lý sau đó. Producer ghi nhận đơn và phát event bền vững; consumer xử lý độc lập theo capacity của nó. Queue hấp thụ burst, retry xử lý lỗi tạm thời và DLQ cách ly message lỗi kéo dài.

### 1.1. Phạm vi chức năng

Pipeline cần thực hiện:

1. Producer tạo OrderPlaced với event ID ổn định.
2. Event được xác thực theo schema trước khi publish.
3. Event được ghi vào nguồn bền vững.
4. Serverless function nhận một message hoặc batch.
5. Consumer kiểm tra idempotency trước side effect.
6. Consumer xác minh đơn hàng và thực hiện bước giữ hàng.
7. Kết quả được commit bền vững.
8. Consumer chỉ acknowledge sau khi commit.
9. Lỗi transient được retry theo policy.
10. Message vượt ngưỡng retry được chuyển vào DLQ.
11. DLQ có metric, cảnh báo, retention và owner.
12. Operator có thể điều tra, sửa lỗi và redrive message hợp lệ.
13. Hệ thống không tạo side effect trùng khi message được gửi lại.

### 1.2. Yêu cầu phi chức năng

| Yêu cầu | Mục tiêu thiết kế |
|---|---|
| Durability | Event đã được xác nhận publish phải tồn tại theo durability contract của queue |
| Reliability | Duplicate delivery không tạo đơn hoặc giữ hàng trùng |
| Availability | Producer tiếp tục nhận đơn khi consumer chậm, trong giới hạn queue và storage |
| Scalability | Function scale theo backlog nhưng không vượt khả năng dependency |
| Recoverability | Message lỗi có thể điều tra và phục hồi |
| Observability | Theo dõi publish, processing, retry, DLQ và end-to-end latency |
| Security | Quyền tối thiểu, mã hóa, kiểm soát dữ liệu nhạy cảm |
| Cost control | Giới hạn concurrency, retry storm, log volume và retention |

Các mục tiêu định lượng như throughput, latency, retention và recovery time cần được xác định theo môi trường triển khai. Không giả định một con số phù hợp cho mọi workload.

## 2. Kiến trúc tổng thể

Một kiến trúc tham chiếu:

~~~mermaid
flowchart LR
    API["Order API"] --> OB["Transactional outbox"]
    OB --> PUB["Outbox publisher"]
    PUB --> Q["Orders queue"]
    Q --> FN["Serverless consumer"]
    FN --> DB["Orders / inventory database"]
    FN --> OUT["OrderAccepted event"]
    Q -->|Retry exhausted| DLQ["Orders DLQ"]
    DLQ --> OBS["Alert and investigation"]
    OBS --> RD["Controlled redrive"]
    RD --> Q
    FN --> MET["Logs / metrics / traces"]
    Q --> MET
    DLQ --> MET
~~~

Các thành phần:

- **Order API:** xác thực request và ghi đơn hàng.
- **Transactional outbox:** lưu event cần phát cùng transaction với đơn hàng.
- **Outbox publisher:** đọc outbox và gửi event tới queue.
- **Orders queue:** lưu event và tách producer khỏi consumer.
- **Serverless consumer:** xử lý event theo batch hoặc từng message.
- **Database:** lưu trạng thái đơn hàng, reservation và idempotency record.
- **OrderAccepted event:** thông báo kết quả cho hệ thống downstream.
- **Orders DLQ:** cách ly message đã vượt retry policy.
- **Observability backend:** thu thập metric, log, trace và cảnh báo.
- **Redrive worker/tool:** đưa message đã được xác minh trở lại luồng xử lý.

Có thể thay queue bằng event bus hoặc stream nếu yêu cầu routing, fan-out, ordering hay replay khác nhau. Tuy nhiên, cần chọn semantics cụ thể trước khi viết consumer vì cách acknowledge và retry khác nhau giữa các event source.

### 2.1. Vì sao dùng queue giữa producer và function?

Queue tạo ranh giới bất đồng bộ:

- Producer không cần chờ function hoàn thành.
- Consumer có thể scale độc lập.
- Burst được lưu trong queue thay vì đẩy thẳng vào database.
- Retry không cần producer gửi lại request tạo đơn.
- DLQ tách message lỗi khỏi luồng bình thường.
- Queue depth và message age giúp đo áp lực xử lý.

Queue không loại bỏ giới hạn capacity. Nếu tốc độ publish dài hạn cao hơn tốc độ xử lý, backlog sẽ tăng. Cần theo dõi oldest message age và đặt giới hạn concurrency theo khả năng dependency.

### 2.2. Luồng thành công và thất bại

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant Q as Orders queue
    participant F as Serverless function
    participant DB as Database
    participant D as DLQ
    API->>Q: Publish OrderPlaced
    Q->>F: Deliver message
    F->>DB: Check idempotency and reserve stock
    alt Commit succeeds
        DB-->>F: Reservation committed
        F-->>Q: Acknowledge
        F->>Q: Publish OrderAccepted
    else Transient error
        DB-->>F: Timeout / temporary failure
        F-->>Q: Do not acknowledge
        Q->>F: Retry after visibility/delay
    else Attempts exhausted
        Q->>D: Move message to DLQ
    end
~~~

Thứ tự publish event tiếp theo và acknowledge cần được thiết kế cẩn thận. Nếu database commit thành công nhưng publish OrderAccepted thất bại, hệ thống có thể thiếu event downstream. Có thể dùng transactional outbox cho event đầu ra hoặc ghi kết quả và outbox record trong cùng transaction.

## 3. Event contract và schema

Event contract xác định cấu trúc, ý nghĩa và quy tắc tương thích của message. Producer và consumer cần dùng cùng một schema version đã được quản lý.

Ví dụ OrderPlaced:

~~~json
{
  "eventId": "evt-01J9A6M7Q2",
  "eventType": "com.example.orders.order-placed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-22T09:30:00Z",
  "producer": "order-api",
  "correlationId": "req-7f31a2",
  "data": {
    "orderId": "ord-10482",
    "customerId": "cus-918",
    "currency": "VND",
    "items": [
      {
        "sku": "SKU-RED-01",
        "quantity": 2
      }
    ]
  }
}
~~~

Ví dụ dùng ID minh họa. Trong hệ thống thật, event ID phải duy nhất và ổn định qua mọi lần retry/redrive.

### 3.1. Các trường quan trọng

| Trường | Mục đích |
|---|---|
| eventId | Idempotency key và định danh event |
| eventType | Chọn handler và routing rule |
| schemaVersion | Chọn parser/validator tương thích |
| occurredAt | Thời điểm nghiệp vụ phát sinh |
| producer | Nguồn tạo event |
| correlationId | Liên kết request và trace |
| data | Payload nghiệp vụ |

Có thể bổ sung tenant, partition key, trace context, event expiry và sequence number nếu cần. Tránh đưa token, password hoặc dữ liệu nhạy cảm không cần thiết vào event.

### 3.2. Quy tắc schema evolution

- Thêm field optional có default thường dễ tương thích hơn đổi kiểu field hiện có.
- Không đổi ý nghĩa của field mà giữ nguyên schema version.
- Consumer nên bỏ qua field chưa biết nếu contract cho phép.
- Thay đổi breaking cần version mới hoặc migration có kế hoạch.
- Producer không phát event trước khi consumer đã hỗ trợ schema mới.
- Giữ mẫu event đại diện trong contract tests.

Không dùng timestamp làm event ID. Hai event có thể cùng thời điểm và đồng hồ của producer có thể lệch. Dùng ID ổn định hoặc khóa nghiệp vụ được xác định rõ.

### 3.3. Xác thực payload

Consumer cần kiểm tra:

- Event ID tồn tại và đúng định dạng.
- Event type được hỗ trợ.
- Schema version được chấp nhận.
- Required fields có mặt.
- Quantity và giá trị số nằm trong range hợp lệ.
- Kích thước payload không vượt giới hạn.
- Tenant/customer có quyền phát sinh event nếu có xác thực nguồn.

Lỗi schema hoặc payload không hợp lệ thường là permanent failure. Không retry nhiều lần nếu không có thay đổi dữ liệu hoặc code.

## 4. Thiết kế producer và transactional outbox

Producer cần tránh tình huống database ghi đơn thành công nhưng publish event thất bại. Nếu hai thao tác không nằm trong cùng một transaction phân tán, có thể xảy ra trạng thái đơn đã tồn tại nhưng consumer không bao giờ nhận được event.

Transactional outbox giải quyết bằng cách ghi đơn và outbox record trong cùng transaction database.

Quy trình:

1. Nhận request tạo đơn.
2. Tạo order ID và event ID.
3. Ghi order record.
4. Ghi outbox record chứa event envelope.
5. Commit transaction.
6. Publisher đọc các outbox record chưa gửi.
7. Publish event tới queue.
8. Đánh dấu outbox record đã publish sau khi nhận xác nhận.
9. Nếu publisher timeout, gửi lại event với cùng event ID.

Ví dụ bảng logic:

~~~sql
CREATE TABLE outbox_events (
    event_id        VARCHAR(80) PRIMARY KEY,
    aggregate_id    VARCHAR(80) NOT NULL,
    event_type      VARCHAR(160) NOT NULL,
    schema_version  INTEGER NOT NULL,
    payload         JSON NOT NULL,
    created_at      TIMESTAMP NOT NULL,
    published_at    TIMESTAMP NULL
);
~~~

Schema SQL cần điều chỉnh theo database thực tế. Publisher nên xử lý lease/locking để nhiều instance không cùng claim một record. Nếu publish thành công nhưng cập nhật published_at thất bại, event có thể được gửi lại; consumer vẫn phải idempotent.

### 4.1. Outbox publisher

Publisher có thể là một worker serverless chạy theo lịch, database change stream hoặc process poll liên tục. Cần giới hạn batch và số lần retry.

Các trạng thái thường dùng:

- pending: chưa được gửi.
- publishing/leased: đang được một publisher xử lý.
- published: queue đã xác nhận nhận event.
- failed/review: lỗi kéo dài cần điều tra.

Không xóa outbox record ngay sau publish nếu cần audit hoặc reconciliation. Đặt retention và archive policy phù hợp.

## 5. Thiết kế serverless consumer

Consumer nhận message từ queue, xác thực, kiểm tra idempotency, thực hiện nghiệp vụ và chỉ acknowledge sau khi kết quả bền vững.

Trách nhiệm của handler nên rõ ràng:

- Parse event envelope.
- Validate schema và business invariants.
- Kiểm tra event đã xử lý chưa.
- Thực hiện side effect theo transaction/idempotency.
- Phân loại lỗi transient và permanent.
- Trả kết quả đúng semantics của event source.
- Ghi log có correlation ID mà không lộ payload nhạy cảm.

### 5.1. Luồng xử lý một message

~~~mermaid
flowchart TD
    A["Receive event"] --> B["Parse and validate"]
    B -->|Invalid| X["Permanent failure / quarantine"]
    B -->|Valid| C["Check idempotency"]
    C -->|Already completed| OK["Acknowledge safely"]
    C -->|New event| D["Apply business transaction"]
    D -->|Commit| E["Write result / outbox"]
    E --> OK
    D -->|Transient error| R["Retry"]
    D -->|Permanent business error| X
~~~

### 5.2. Ví dụ handler TypeScript

Mã dưới đây minh họa cấu trúc xử lý một message. Các interface database, queue và logger cần được triển khai bằng SDK của nền tảng đã chọn.

~~~typescript
type OrderPlaced = {
  eventId: string;
  eventType: "com.example.orders.order-placed";
  schemaVersion: number;
  occurredAt: string;
  correlationId: string;
  data: {
    orderId: string;
    customerId: string;
    currency: string;
    items: Array<{ sku: string; quantity: number }>;
  };
};

class TransientError extends Error {}
class PermanentError extends Error {}

async function handleOrderPlaced(
  event: OrderPlaced,
  deps: Dependencies
): Promise<void> {
  validateOrderPlaced(event);

  await deps.database.transaction(async (tx) => {
    const alreadyDone = await tx.inbox.isCompleted(event.eventId);
    if (alreadyDone) return;

    await reserveInventory(tx, event.data.items);

    await tx.orders.markAccepted(event.data.orderId);
    await tx.inbox.markCompleted(event.eventId);

    await tx.outbox.add({
      eventId: createStableResultEventId(event.eventId),
      eventType: "com.example.orders.order-accepted",
      correlationId: event.correlationId,
      data: { orderId: event.data.orderId }
    });
  });
}
~~~

Ví dụ giả định các thao tác inbox, order, inventory và outbox cùng tham gia một transaction database. Nếu reservation nằm ở dịch vụ ngoài database, cần saga hoặc protocol idempotent riêng; không thể giả định một transaction SQL bao trùm mọi dịch vụ.

### 5.3. Phân loại lỗi trong handler

~~~typescript
async function processMessage(
  message: QueueMessage,
  deps: Dependencies
): Promise<"success" | "retry" | "permanent"> {
  try {
    const event = parseAndValidateEnvelope(message.body);
    await handleOrderPlaced(event, deps);
    return "success";
  } catch (error) {
    if (error instanceof PermanentError) {
      await deps.quarantine.record(message, safeErrorCode(error));
      return "permanent";
    }

    if (isTransient(error)) {
      return "retry";
    }

    deps.logger.error("unclassified_processing_failure", {
      messageId: message.id,
      errorClass: classify(error)
    });
    return "retry";
  }
}
~~~

Đây là pseudo-code định hướng. Từng event source có cách biểu diễn permanent failure khác nhau. Một số queue consumer chỉ có lựa chọn ack hoặc không ack; khi đó permanent failure cần được ghi vào quarantine/DLQ an toàn trước khi ack. Không ack một message đã ghi quarantine thất bại.

## 6. Idempotency và side effect

Queue thường cung cấp at-least-once delivery. Cùng một message có thể đến nhiều lần. Consumer phải đảm bảo duplicate không tạo thêm reservation, charge hoặc notification ngoài ý muốn.

### 6.1. Inbox/deduplication store

Bảng inbox có thể lưu:

~~~sql
CREATE TABLE processed_events (
    event_id       VARCHAR(80) PRIMARY KEY,
    event_type     VARCHAR(160) NOT NULL,
    status         VARCHAR(20) NOT NULL,
    processed_at   TIMESTAMP NULL,
    result_ref     VARCHAR(100) NULL
);
~~~

Khóa chính trên event_id giúp ngăn hai consumer cùng đánh dấu một event như mới nếu thao tác được thực hiện trong transaction phù hợp.

Trạng thái có thể gồm processing, completed và failed, nhưng cần lease/timeout nếu consumer chết giữa lúc ghi processing. Không để record processing tồn tại vĩnh viễn khiến event không thể được xử lý lại.

### 6.2. External side effect

Nếu consumer gọi payment provider hoặc dịch vụ ngoài, transaction database không thể tự rollback side effect đã xảy ra ở bên ngoài.

Dùng:

- Idempotency key mà downstream provider hỗ trợ.
- Request ID ổn định theo event và operation.
- Saga với trạng thái từng bước.
- Compensation nếu nghiệp vụ cho phép.
- Reconciliation để phát hiện kết quả không xác định.
- Timeout và retry theo contract của dependency.

Nếu request tới downstream timeout, không thể luôn kết luận operation thất bại. Có thể provider đã xử lý nhưng response bị mất. Truy vấn trạng thái bằng idempotency key trước khi gửi lại.

### 6.3. Không nhầm event ID với attempt ID

Event ID giữ nguyên qua retry và redrive. Attempt ID có thể thay đổi mỗi lần xử lý. Ghi cả hai để điều tra, nhưng deduplication dùng event ID hoặc operation key ổn định.

## 7. Retry, visibility timeout và DLQ

Retry policy cần được phối hợp với thời gian xử lý, timeout của function và semantics queue.

### 7.1. Visibility timeout

Với queue polling, message thường bị ẩn trong một khoảng visibility timeout sau khi consumer nhận. Nếu consumer không ack/delete trước khi hết timeout, message có thể được giao lại.

Visibility timeout cần đủ lớn cho:

- Thời gian xử lý p99.
- Thời gian ghi database và output.
- Thời gian shutdown/retry nội bộ nếu có.
- Buffer cho cold start hoặc network delay.

Nếu visibility quá ngắn, hai worker có thể cùng xử lý một message. Nếu quá dài, message lỗi cần chờ lâu mới được giao lại. Chọn theo thời gian xử lý đo được và retry semantics của provider.

### 7.2. Backoff và jitter

Exponential backoff giảm tốc độ retry khi dependency lỗi:

~~~text
delay = min(maxDelay, initialDelay * 2^attempt)
~~~

Jitter phân tán thời điểm retry:

~~~text
actualDelay = random(0, delay)
~~~

Một policy minh họa:

~~~yaml
retry:
  maxAttempts: 5
  initialDelay: 2s
  maxDelay: 2m
  jitter: full
  maxEventAge: 6h
~~~

Đây là cấu hình khái niệm, không phải schema dùng chung. Queue có thể retry theo visibility timeout và receive count thay vì delay riêng từng attempt.

### 7.3. Redrive policy và DLQ

Ví dụ cấu hình logic:

~~~yaml
sourceQueue:
  name: orders-events
  visibilityTimeout: 120s
  retention: 4d
  redrive:
    deadLetterQueue: orders-events-dlq
    maxReceiveCount: 5

deadLetterQueue:
  name: orders-events-dlq
  retention: 14d
  encryption: enabled
  alertOnVisibleMessage: true
~~~

Các giá trị chỉ minh họa. Cần kiểm tra giới hạn dịch vụ, retention tối đa, semantics receive count và quyền queue nguồn gửi sang DLQ.

DLQ cần có owner, cảnh báo, retention, quyền truy cập và runbook. Nếu không, message lỗi có thể hết hạn mà không ai biết.

### 7.4. Poison event

Một payload sai schema hoặc một giá trị luôn gây exception có thể trở thành poison event. Không retry vô hạn.

Phân loại:

- transient: retry có backoff.
- permanent/schema: quarantine hoặc DLQ sớm.
- unknown: retry có giới hạn, log error class và giữ context.
- dependency outage: giảm concurrency, backpressure hoặc tạm dừng consumer theo runbook.

Không log toàn bộ payload nếu chứa thông tin khách hàng hoặc dữ liệu thanh toán.

## 8. Batch và partial failure

Một function có thể nhận nhiều message trong một invocation để tăng throughput và giảm overhead. Tuy nhiên, nếu một record lỗi và handler đánh dấu cả batch thất bại, những record đã xử lý thành công có thể bị chạy lại.

Có hai mô hình:

- Batch-level retry: cả batch được giao lại khi một record lỗi.
- Partial batch response: function chỉ trả các record thất bại nếu event source hỗ trợ.

Ví dụ phản hồi khái niệm:

~~~json
{
  "batchItemFailures": [
    { "itemIdentifier": "msg-17" },
    { "itemIdentifier": "msg-22" }
  ]
}
~~~

Schema thực tế phụ thuộc nền tảng và loại event source. Cần dùng đúng identifier mà mapping yêu cầu.

### 8.1. Giới hạn batch size

Batch lớn tăng throughput nhưng cũng:

- Kéo dài thời gian invocation.
- Tăng lượng dữ liệu trong memory.
- Tăng số record bị retry khi partial response không có.
- Làm khó xác định poison record.
- Tăng thời gian giữ message invisible.

Chọn batch size bằng thử nghiệm với payload lớn nhất, p99 processing time và function memory limit.

### 8.2. Batch bisect

Một số stream integration hỗ trợ chia batch thất bại thành hai phần để tìm record gây lỗi. Cơ chế này hữu ích nhưng làm tăng invocation và không thay thế idempotency.

Với stream có ordering, record lỗi có thể giữ checkpoint và làm chậm record sau trong cùng partition. Phải hiểu semantics checkpoint trước khi bật batch bisect hoặc partial failure.

## 9. Concurrency, backpressure và capacity

Serverless có thể tự scale nhanh, nhưng dependency phía sau không nhất thiết scale cùng tốc độ. Nếu function tạo quá nhiều kết nối database hoặc request tới inventory service, hệ thống có thể chuyển một queue backlog thành dependency outage.

### 9.1. Giới hạn concurrency

Đặt giới hạn concurrency dựa trên capacity của dependency:

~~~text
maxFunctionConcurrency <=
  safeDatabaseConnections / connectionsPerInvocation
~~~

Công thức là ước lượng ban đầu. Cần trừ kết nối dành cho API, admin và các workload khác; tính cả connection pool, retry và số region/instance.

Có thể dùng:

- Reserved/provisioned concurrency hoặc giới hạn tương đương của provider.
- Queue consumer batch size.
- Poller concurrency.
- Rate limit theo tenant hoặc event type.
- Semaphore cho downstream call.
- Circuit breaker khi dependency lỗi.

### 9.2. Backpressure

Khi consumer không theo kịp producer:

- Queue depth tăng.
- Oldest message age tăng.
- Event latency tăng.
- Storage/retention có nguy cơ bị chạm.
- Retry có thể làm tải tăng thêm.

Backpressure có thể gồm giảm producer rate, giới hạn consumer concurrency, trì hoãn low-priority event hoặc trả trạng thái retryable cho producer. Không scale function vô hạn nếu database là bottleneck.

### 9.3. Ước lượng capacity

Nếu mỗi invocation xử lý trung bình B message trong thời gian S giây và có C invocation đồng thời, throughput lý thuyết gần đúng:

~~~text
throughput ≈ (B * C) / S
~~~

Ví dụ B=10, C=20, S=2 giây thì throughput lý thuyết khoảng 100 message/giây. Throughput thực tế còn phụ thuộc cold start, throttling, database, network, batch failures và thời gian retry.

Đo throughput thành công và oldest message age trong tải thực tế. Không dùng throughput lý thuyết làm cam kết capacity.

## 10. Ordering và partitioning

Không phải mọi pipeline cần xử lý đúng thứ tự. Nếu OrderPlaced và OrderCancelled cho cùng một đơn phải theo thứ tự, queue không đảm bảo ordering có thể tạo trạng thái sai.

Các lựa chọn:

- Dùng FIFO hoặc partition key theo order ID nếu provider hỗ trợ.
- Lưu aggregate version/sequence trong event.
- Consumer kiểm tra version trước khi áp dụng thay đổi.
- Chấp nhận event đến trễ và xử lý theo state machine.
- Chia partition để tăng parallelism mà vẫn giữ thứ tự trong từng nhóm.

Ordering toàn cục thường làm giảm throughput và tăng coupling. Chỉ yêu cầu ordering ở phạm vi cần thiết, ví dụ theo order ID hoặc customer ID.

### 10.1. Event đến muộn

Nếu OrderCancelled đến trước OrderPlaced do retry hoặc replay, consumer cần quyết định:

- Giữ event chờ predecessor.
- Ghi trạng thái pending.
- Từ chối với lỗi retryable.
- Áp dụng state transition có version.
- Cách ly event để điều tra.

Không dựa hoàn toàn vào timestamp để xác định thứ tự vì clock drift và delivery delay.

## 11. Bảo mật pipeline

Mỗi thành phần chỉ nên có quyền cần thiết:

- Producer chỉ được publish vào queue nguồn.
- Consumer chỉ được đọc queue, ghi database cần thiết và publish event đầu ra.
- Redrive operator có quyền đọc DLQ và chạy redrive theo phạm vi được phê duyệt.
- Monitoring agent chỉ được đọc metric/log cần thiết.
- Không cấp quyền purge DLQ cho function nghiệp vụ.

Các biện pháp:

- Mã hóa queue, DLQ và database khi lưu.
- TLS cho giao tiếp.
- Workload identity hoặc credential ngắn hạn.
- Secret manager cho token/credential.
- Kiểm tra chữ ký hoặc nguồn phát khi event đi qua ranh giới tin cậy.
- Validate schema và giới hạn payload size.
- Mask PII trong logs.
- Audit publish, receive, redrive, purge và policy changes.
- Retention và deletion policy cho event có dữ liệu nhạy cảm.

### 11.1. Event không phải command tùy ý

Không thực thi shell command, SQL tùy ý hoặc URL do payload cung cấp mà không validate. Event nên biểu diễn dữ liệu nghiệp vụ có schema rõ, không trở thành một kênh thực thi lệnh.

Nếu event chứa object key hoặc URL, xác thực namespace, tenant và quyền truy cập trước khi tải dữ liệu.

## 12. Observability và correlation

Pipeline cần theo dõi event từ producer tới kết quả cuối. Dùng event ID và correlation ID xuyên suốt.

Các metric:

| Metric | Ý nghĩa |
|---|---|
| events_published_total | Số event publish |
| publish_failures_total | Số lần publish thất bại |
| queue_visible_messages | Backlog hiện tại |
| queue_oldest_message_age_seconds | Tuổi message lâu nhất |
| function_invocations_total | Số invocation |
| function_errors_total | Số invocation lỗi |
| function_duration_seconds | Thời gian xử lý |
| function_throttles_total | Số lần bị throttle |
| event_success_total | Số event hoàn tất nghiệp vụ |
| retry_attempts_total | Số lần retry |
| dlq_visible_messages | Số message trong DLQ |
| dlq_oldest_message_age_seconds | Tuổi message lâu nhất trong DLQ |
| redrive_success_total | Số message redrive thành công |
| duplicate_events_total | Số event bị idempotency loại bỏ |
| downstream_latency_seconds | Độ trễ dependency |

### 12.1. Structured logging

Log nên chứa:

- eventId.
- correlationId/traceId.
- eventType và schemaVersion.
- messageId của queue.
- attempt count nếu có.
- function version.
- error class/code.
- duration và result.
- redriveRunId nếu replay.

Không ghi toàn bộ payload mặc định. Dùng allowlist field, masking và log level phù hợp.

### 12.2. Distributed tracing

Tạo span cho:

- Publish event.
- Queue wait time nếu có timestamp/metadata.
- Function invocation.
- Database transaction.
- Downstream API.
- Publish result event.
- Redrive/replay.

Queue tạo ranh giới bất đồng bộ nên trace context cần được truyền trong message envelope hoặc message attributes. Không dùng trace ID làm idempotency key; hai khái niệm có mục đích khác nhau.

### 12.3. Cảnh báo

Các cảnh báo nên bao gồm:

- Source queue oldest age vượt SLO.
- Queue depth tăng liên tục.
- Function error/throttle rate tăng.
- DLQ có message mới hoặc oldest age tiến gần retention.
- Outbox pending age tăng.
- Database connection/latency vượt ngưỡng.
- Redrive làm message quay lại DLQ.
- Publish failure hoặc permission denied.
- Event success rate giảm dù invocation rate tăng.

Cảnh báo cần gắn owner và runbook. Với event quan trọng, cảnh báo khi DLQ có message đầu tiên; với luồng ít quan trọng có thể dùng ngưỡng count/age.

## 13. Chiến lược redrive và phục hồi

Redrive đưa message từ DLQ về queue nguồn hoặc một queue phục hồi. Không redrive toàn bộ ngay sau khi sửa code mà chưa thử một message.

Quy trình:

1. Xác định nguyên nhân thất bại.
2. Xác nhận code/config/dependency đã được sửa.
3. Kiểm tra schema version và event expiry.
4. Xác minh idempotency và downstream state.
5. Chọn một message đại diện.
6. Redrive thử và kiểm tra side effect.
7. Chạy batch nhỏ với rate limit.
8. Theo dõi queue, DLQ, dependency và SLO.
9. Dừng nếu message tiếp tục thất bại.
10. Ghi audit về phạm vi và kết quả redrive.

### 13.1. Giữ nguyên event identity

Khi replay, giữ event ID gốc để deduplication hoạt động. Có thể bổ sung replayRunId, replayedAt và replaySource. Không đổi event ID để né idempotency vì điều đó có thể tạo side effect trùng.

### 13.2. Event đã hết hạn

Một event có thể không còn hợp lệ về nghiệp vụ sau một thời gian. Ví dụ đơn đã bị hủy hoặc payment window đã đóng. Trước khi redrive, kiểm tra trạng thái hiện tại và event expiry. Một số message nên được đóng theo quyết định nghiệp vụ thay vì replay.

### 13.3. Không tạo vòng lặp retry-DLQ

Không cấu hình consumer DLQ tự động gửi lại message về source vô hạn. Redrive cần là hành động có kiểm soát, có batch limit, rate limit và điều kiện dừng.

## 14. Triển khai và cấu hình tham chiếu

Dự án nên quản lý queue, DLQ, function, permission, database và alarms bằng Infrastructure as Code. Tên resource và schema phụ thuộc provider; cấu hình dưới đây là mô hình khái niệm để mô tả quan hệ.

~~~yaml
pipeline:
  name: order-event-pipeline

  sourceQueue:
    name: orders-events
    encryption: enabled
    retention: 4d
    visibilityTimeout: 120s
    redrive:
      target: orders-events-dlq
      maxReceiveCount: 5

  deadLetterQueue:
    name: orders-events-dlq
    encryption: enabled
    retention: 14d
    alertThreshold: 1

  consumer:
    function: process-order-event
    runtime: nodejs
    timeout: 30s
    memory: 1024MiB
    batchSize: 5
    maximumConcurrency: 20
    partialBatchResponse: enabled

  idempotency:
    store: processed-events
    key: eventId
    retention: 30d

  observability:
    structuredLogs: enabled
    tracing: enabled
    metrics: enabled
    alarms:
      - sourceQueueOldestAge
      - functionErrorRate
      - dlqVisibleMessages
~~~

Đây không phải manifest triển khai trực tiếp. Khi chuyển sang Terraform, CloudFormation, Bicep hoặc công cụ provider khác, thay field theo schema thực và kiểm tra quota, timeout, retention, permission và encryption policy.

### 14.1. Cấu hình timeout nhất quán

Nếu function timeout 30 giây, visibility timeout không nên thấp hơn thời gian xử lý tối đa cộng buffer. Với batch, cần tính thời gian cả batch và cơ chế retry. Một số provider yêu cầu visibility timeout theo công thức hoặc giới hạn cụ thể; kiểm tra tài liệu dịch vụ.

### 14.2. Quyền của function

Consumer cần quyền:

- Receive/read message từ source queue.
- Delete/ack message theo integration.
- Ghi database/table cần thiết.
- Publish output event nếu có.
- Ghi logs/metrics/traces.
- Đọc secret cụ thể nếu thật sự cần.

Consumer không cần quyền purge queue hoặc thay đổi redrive policy. Tách role triển khai, runtime và redrive operator.

## 15. Kiểm thử pipeline

Kiểm thử phải chứng minh cả luồng thành công và khả năng phục hồi.

### 15.1. Unit tests

Kiểm thử:

- Schema hợp lệ và không hợp lệ.
- Event type không được hỗ trợ.
- Quantity hoặc business invariant sai.
- Event đã xử lý.
- Dependency timeout.
- Lỗi throttling.
- Permanent business error.
- Retry classification.
- Idempotency key ổn định.

### 15.2. Integration tests

Kiểm thử:

1. Producer ghi order và outbox trong một transaction.
2. Publisher gửi event thành công.
3. Consumer nhận và xử lý event.
4. Database cập nhật đúng.
5. Output event được tạo.
6. Duplicate event không tạo side effect trùng.
7. Consumer lỗi và message được retry.
8. Message vượt ngưỡng được đưa vào DLQ.
9. Redrive sau khi sửa lỗi xử lý thành công.

### 15.3. Failure injection

Mô phỏng các tình huống:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Database timeout một lần | Message retry và cuối cùng thành công |
| Database outage kéo dài | Concurrency được giới hạn, backlog tăng có kiểm soát |
| Payload sai schema | Quarantine/DLQ, không retry vô hạn |
| Consumer crash sau commit trước ack | Redelivery không tạo duplicate |
| Visibility timeout quá ngắn | Test phát hiện duplicate concurrency |
| Function timeout | Message được retry theo policy |
| DLQ permission sai | Cảnh báo và phát hiện message không được chuyển |
| Outbox publish timeout | Publisher retry cùng event ID |
| Redrive batch quá lớn | Rate limit bảo vệ downstream |
| Event hết hạn | Consumer từ chối hoặc route theo business policy |

Không chỉ xác nhận function trả HTTP 200 hoặc invocation success. Cần kiểm tra trạng thái đơn, reservation, inbox/outbox, queue và DLQ.

### 15.4. Load và resilience tests

Tạo tải tăng dần, burst và sustained load. Đo:

- Publish throughput.
- Queue depth và oldest age.
- Function concurrency và duration.
- Database connections và latency.
- Success/error/retry rate.
- DLQ arrival rate.
- Cost per completed order.

Kiểm tra hệ thống khi consumer bị pause, database chậm và cloud dependency mất kết nối. Xác minh producer có thể tiếp tục trong giới hạn durability và retention.

## 16. Runbook vận hành

### 16.1. Khi source queue backlog tăng

1. Kiểm tra producer rate và consumer invocation rate.
2. Kiểm tra function errors, throttles và duration.
3. Kiểm tra database connection, latency và quota.
4. Xác định bottleneck là compute, queue poller hay dependency.
5. Giảm concurrency nếu downstream quá tải.
6. Tăng concurrency chỉ khi dependency còn headroom.
7. Kiểm tra oldest message age so với SLO.
8. Theo dõi backlog drain sau điều chỉnh.

### 16.2. Khi DLQ xuất hiện message

1. Xác định event type, consumer version và error class.
2. Kiểm tra có phải poison event hay dependency outage.
3. Chọn một message đại diện để điều tra.
4. Xác nhận payload và schema.
5. Sửa producer/consumer/config.
6. Kiểm thử lại với bản sao message.
7. Redrive một message, sau đó batch nhỏ.
8. Theo dõi message có quay lại DLQ không.
9. Ghi audit và đóng incident.

### 16.3. Khi event bị xử lý trùng

1. Xác định event ID và các attempt.
2. Kiểm tra idempotency record và transaction boundary.
3. Xác định side effect đã xảy ra ở downstream chưa.
4. Dùng reconciliation hoặc compensation theo nghiệp vụ.
5. Sửa unique constraint/locking/idempotency key.
6. Replay một mẫu duplicate trong staging.
7. Xác nhận event được acknowledge mà không lặp side effect.

### 16.4. Khi outbox backlog tăng

Kiểm tra publisher health, permission, queue availability, lease timeout và số record bị lock. Không xóa outbox record để làm backlog về 0. Khi publish timeout không rõ kết quả, retry với event ID gốc và dựa vào idempotency downstream.

## 17. Tối ưu chi phí

Serverless không đồng nghĩa chi phí luôn thấp. Retry storm, batch quá nhỏ, log quá chi tiết, function memory không phù hợp và queue retention dài có thể làm chi phí tăng.

Các yếu tố:

- Số invocation và thời gian thực thi.
- Memory/CPU allocation.
- Batch size và concurrency.
- Queue request/polling.
- Database reads/writes và connection overhead.
- Log/trace ingestion và retention.
- DLQ storage và redrive.
- Network transfer.
- Cold start và provisioned capacity nếu dùng.

### 17.1. Cost per successful event

Đo chi phí trên kết quả nghiệp vụ:

~~~text
Cost per successful event =
  (function + queue + database + network + logs + retry + operations cost)
  / successful events
~~~

So sánh các cấu hình batch size, memory, concurrency và retry bằng workload tương đương. Không giảm log hoặc retry đến mức làm mất khả năng phục hồi chỉ để giảm chi phí.

### 17.2. Giảm chi phí an toàn

- Chọn memory/CPU theo benchmark.
- Dùng batch size phù hợp.
- Giới hạn retry và event age.
- Giảm duplicate bằng idempotency.
- Sampling trace và log debug.
- Retention DLQ theo thời gian điều tra.
- Dọn outbox đã publish theo policy.
- Dùng queue buffering để tránh overprovision consumer.
- Tối ưu query và connection reuse.
- Cảnh báo khi DLQ hoặc retry rate tăng.

## 18. Tiêu chí nghiệm thu dự án

Pipeline được xem là hoàn thành khi chứng minh được các điều kiện:

| Nhóm | Tiêu chí nghiệm thu |
|---|---|
| Producer | Event có ID ổn định; outbox tránh mất event sau commit |
| Contract | Schema có version và validation |
| Consumer | Function xử lý thành công và ghi kết quả bền vững |
| Idempotency | Gửi lại cùng event không tạo side effect trùng |
| Retry | Lỗi transient được retry có giới hạn và backoff |
| DLQ | Poison/permanent failure được cách ly và cảnh báo |
| Redrive | Có thể replay batch nhỏ sau khi sửa lỗi |
| Capacity | Concurrency không vượt khả năng downstream |
| Observability | Có queue age, error rate, DLQ, trace và correlation |
| Security | Quyền tối thiểu, encryption và audit |
| Recovery | Đã thử crash sau commit trước ack và chứng minh không duplicate |
| Cost | Có báo cáo cost per successful event hoặc proxy metric |

### 18.1. Deliverables

Bộ bàn giao dự án gồm:

- Sơ đồ kiến trúc và sequence diagram.
- Event schema và ví dụ payload.
- Producer/outbox publisher.
- Serverless consumer và unit tests.
- Queue, DLQ và permission configuration.
- Idempotency store/schema.
- Infrastructure as Code.
- Dashboard, alarms và runbook.
- Báo cáo failure injection và load test.
- Hướng dẫn redrive và rollback.

## 19. Lỗi thường gặp và cách tránh

**Publish sau khi commit nhưng không có outbox:** order có thể tồn tại mà event bị mất. Dùng transactional outbox hoặc cơ chế tương đương.

**Ack trước khi commit kết quả:** function crash có thể làm mất event. Chỉ ack sau khi side effect bền vững.

**Không có idempotency:** at-least-once delivery tạo duplicate. Dùng event ID ổn định và transaction/unique constraint.

**Retry mọi lỗi:** payload sai schema lặp vô hạn. Phân loại transient và permanent.

**Retry không có jitter:** nhiều function cùng retry tạo thundering herd. Dùng backoff, jitter và concurrency limit.

**Visibility timeout quá ngắn:** message được giao lại khi invocation cũ còn chạy. Đặt theo thời gian xử lý và buffer.

**Scale function không giới hạn:** database bị quá tải. Đặt maximum concurrency và backpressure.

**DLQ không có owner:** message nằm lâu tới hết retention. Gắn owner, alert và runbook.

**Redrive toàn bộ cùng lúc:** dependency bị quá tải lần nữa. Thử một message, sau đó batch nhỏ có rate limit.

**Thay event ID khi replay:** idempotency không nhận ra duplicate. Giữ event ID gốc và thêm replay metadata.

**Không kiểm tra event expiry:** sự kiện cũ làm thay đổi trạng thái nghiệp vụ không còn hợp lệ. Validate business state trước khi apply.

**Log toàn bộ payload:** rò rỉ PII/secret và tăng chi phí. Dùng structured logs, masking và allowlist.

**Không kiểm thử crash sau commit:** duplicate side effect chỉ xuất hiện ở failure window này. Có test riêng cho commit-before-ack.

## 20. Checklist triển khai pipeline

- [ ] Kiến trúc xác định producer, queue, function, database, DLQ và downstream event.
- [ ] Event contract có eventId, eventType, schemaVersion và correlationId.
- [ ] Schema validation được thực hiện trước side effect.
- [ ] Producer dùng transactional outbox hoặc bảo đảm publish tương đương.
- [ ] Consumer xử lý idempotent theo event ID ổn định.
- [ ] Side effect và inbox state được commit nhất quán.
- [ ] Acknowledge chỉ sau khi kết quả bền vững.
- [ ] Retry có maximum attempts, event age, backoff và jitter.
- [ ] Visibility timeout phù hợp function timeout và p99 processing.
- [ ] DLQ có redrive policy, encryption, retention và alert.
- [ ] Permanent failure được quarantine phù hợp.
- [ ] Partial batch response được dùng khi event source hỗ trợ.
- [ ] Maximum concurrency bảo vệ database và downstream.
- [ ] Ordering/partition key được xác định theo nghiệp vụ.
- [ ] IAM/workload identity tuân theo least privilege.
- [ ] Logs mask dữ liệu nhạy cảm và có correlation ID.
- [ ] Dashboard theo dõi queue age, function errors, retry và DLQ.
- [ ] Redrive có batch limit, rate limit, audit và stop condition.
- [ ] Đã kiểm thử duplicate, timeout, poison event và DLQ.
- [ ] Đã chạy load/resilience test và tính cost per successful event.
- [ ] Có runbook cho backlog, DLQ, duplicate và outbox backlog.
- [ ] Có tiêu chí nghiệm thu và deliverables được lưu trữ.

Dự án này tạo một pipeline sự kiện serverless có khả năng tiếp nhận tải bất đồng bộ, xử lý độc lập và phục hồi khi function hoặc dependency gặp lỗi. Chất lượng của pipeline phụ thuộc vào event contract ổn định, idempotency, retry có giới hạn, DLQ có người chịu trách nhiệm và observability xuyên suốt. Khi kiểm thử cả tình huống commit-before-ack, poison event, backlog và redrive có kiểm soát, bạn có thể chứng minh hệ thống xử lý sự kiện đúng đắn và mở rộng được mà không làm quá tải các dịch vụ phía sau.
