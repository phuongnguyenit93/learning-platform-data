# Xây dựng SQS listener với retry và idempotency

> **Chương:** Ứng dụng Java và Spring Boot  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hệ sinh thái AWS qua hạ tầng Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless. Người học rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Amazon Simple Queue Service (Amazon SQS) giúp tách producer khỏi consumer, hấp thụ traffic burst và xử lý công việc bất đồng bộ. Tuy nhiên, SQS có thể giao một message nhiều lần; consumer có thể crash sau khi đã commit database nhưng trước khi xóa message. Vì vậy, **retry phải đi cùng idempotency**.

Bài học xây dựng luồng xử lý `OrderCreated` bằng Java/Spring Boot, Spring Cloud AWS 3.x và AWS SDK for Java 2.x. Ta sẽ thiết kế queue, visibility timeout, retry/DLQ, listener acknowledgement, durable idempotency, database transaction, outbox, FIFO ordering, graceful shutdown và observability.

Sau bài học, bạn có thể:

1. Giải thích at-least-once delivery của SQS Standard và semantics của FIFO.
2. Thiết kế visibility timeout, long polling, redrive policy và dead-letter queue.
3. Phân biệt message retry, visibility extension, delayed retry và redrive.
4. Cấu hình Spring Cloud AWS listener và acknowledgement mode.
5. Xử lý message trùng bằng idempotency key bền vững.
6. Kết hợp idempotency record với business database transaction.
7. Dùng outbox/idempotent external APIs cho side effects bên ngoài database.
8. Hiểu `MessageGroupId`, `MessageDeduplicationId` và giới hạn FIFO.
9. Cấu hình IAM least privilege, SSE-KMS và network access.
10. Thiết kế graceful shutdown, bounded concurrency, metrics, tracing và runbook.

## 1. Vì sao ứng dụng cần SQS listener?

### 1.1. Tách request khỏi công việc tốn thời gian

Giả sử một API nhận yêu cầu thanh toán/đăng ký khóa học. Trong cùng request, hệ thống có thể phải cập nhật database, gửi email, cập nhật search index, tạo hóa đơn và ghi analytics. Nếu gọi tất cả tuần tự, API phụ thuộc uptime và latency của từng hệ thống downstream.

SQS cho phép API ghi event vào queue rồi trả kết quả nhanh; consumer xử lý độc lập:

~~~mermaid
flowchart LR
    C[Client] --> API[Spring Boot API]
    API --> DB[(Orders DB)]
    API --> Q[(SQS Orders Queue)]
    Q --> W[Spring Boot Worker]
    W --> DB2[(Business DB)]
    W --> MAIL[Email provider]
    W --> SEARCH[Search index]
    Q -. redrive .-> DLQ[(Dead-letter queue)]
~~~

Producer và consumer có thể scale độc lập. Queue lưu message trong khi consumer tạm thời không sẵn sàng, trong giới hạn retention và queue configuration.

### 1.2. SQS không phải distributed transaction coordinator

Việc `SendMessage` thành công không tự commit cùng transaction database của producer. Có thể xảy ra:

- Database commit nhưng process crash trước khi gửi SQS;
- Gửi SQS thành công nhưng response bị timeout, producer không biết message đã được gửi chưa;
- Consumer commit DB nhưng crash trước khi DeleteMessage;
- Consumer gọi payment/email thành công nhưng crash trước khi đánh dấu xử lý xong.

Các tình huống này tạo ra **duplicate hoặc missing side effects** nếu không thiết kế thêm. Bài học sẽ dùng idempotency và outbox/inbox để xử lý.

### 1.3. Delivery guarantee và mục tiêu thực tế

Với SQS Standard, hệ thống được thiết kế theo **at-least-once delivery**: một message có thể được giao lại, kể cả khi consumer đã xử lý trong một số failure scenarios. Thứ tự không được đảm bảo tuyệt đối.

SQS FIFO cung cấp ordering theo `MessageGroupId` và deduplication ở phía gửi trong cửa sổ deduplication của queue. Điều này **không biến toàn bộ nghiệp vụ end-to-end thành exactly-once**. Consumer vẫn phải an toàn khi nhận lại message.

Mục tiêu kiến trúc thực tế:

- Message có thể giao lại;
- Consumer có thể chạy lại;
- Database side effect được bảo vệ bằng transaction/unique constraint;
- External side effect có idempotency key hoặc outbox workflow;
- Message chỉ được acknowledge/delete sau khi kết quả xử lý đã bền vững.

### 1.4. Ba lớp cần tách bạch

| Lớp | Cơ chế | Giải quyết vấn đề |
|---|---|---|
| Transport retry | SQS visibility timeout/redrive | Giao lại message khi consumer chưa hoàn tất |
| Processing idempotency | Event ID + durable inbox/unique key | Không áp dụng cùng business event hai lần |
| Side-effect consistency | DB transaction, outbox, external idempotency | Tránh trạng thái nửa hoàn thành giữa các hệ thống |

Không lớp nào thay thế hoàn toàn hai lớp còn lại.

## 2. SQS Standard và FIFO

### 2.1. So sánh

| Thuộc tính | Standard queue | FIFO queue |
|---|---|---|
| Throughput | Cao, scale rộng | Có giới hạn theo chế độ throughput/Region; hỗ trợ high-throughput FIFO |
| Ordering | Không đảm bảo thứ tự | Đảm bảo thứ tự trong cùng message group |
| Duplicate delivery | Có thể | Vẫn cần consumer idempotency |
| Send deduplication | Không có queue-level FIFO dedupe | Có deduplication ID/content-based dedupe trong cửa sổ 5 phút |
| Parallelism | Consumer có thể xử lý song song nhiều messages | Parallel theo nhiều message groups; trong một group phải giữ thứ tự |
| Queue name | Tên thường | Tên kết thúc bằng `.fifo` |
| Use case | Event/workload độc lập, throughput lớn | Ordering theo order/account/aggregate |

Chọn FIFO khi thứ tự là invariant nghiệp vụ, ví dụ cập nhật số dư theo từng account hoặc trạng thái order theo sequence. Nếu messages độc lập và có thể xử lý song song, Standard thường đơn giản và linh hoạt hơn.

### 2.2. FIFO không tự bảo đảm exactly-once business processing

FIFO deduplication giúp SQS nhận biết cùng `MessageDeduplicationId` trong **5 phút** để tránh enqueue trùng trong cửa sổ đó. Nhưng:

- Consumer có thể nhận lại message khi visibility timeout hết;
- Consumer có thể commit business transaction nhưng chưa delete message;
- Một retry được gửi sau cửa sổ deduplication có thể được enqueue lại;
- Email/payment/search side effect có thể bị gọi lại nếu không có idempotency.

Vì vậy, producer dùng deterministic deduplication ID và consumer vẫn lưu `eventId` đã xử lý trong durable store.

### 2.3. MessageGroupId là ranh giới ordering

Ví dụ FIFO:

~~~text
MessageGroupId = ORDER#order-123
  Event 1: OrderCreated
  Event 2: PaymentAuthorized
  Event 3: OrderShipped

MessageGroupId = ORDER#order-456
  Event 1: OrderCreated
  Event 2: PaymentAuthorized
~~~

Các messages trong cùng group được xử lý theo thứ tự; nhiều groups có thể được xử lý đồng thời. Nếu đặt cùng một group ID cho toàn queue, bạn có thể vô tình tuần tự hóa gần như toàn bộ workload.

Ở phía ứng dụng, đừng dispatch messages cùng group vào các threads xử lý song song rồi commit out of order. Nếu dùng batch listener hoặc custom executor, cần giữ serial processing theo `MessageGroupId` hoặc chứng minh framework/container version đang dùng bảo toàn thứ tự end-to-end.

Chọn group theo aggregate cần giữ thứ tự, như `ORDER#<orderId>` hoặc `ACCOUNT#<accountId>`. Không dùng tenant ID chung làm group nếu mọi đơn hàng trong tenant không cần thứ tự toàn cục.

### 2.4. Event envelope có schema version

Message body nên có envelope ổn định:

~~~json
{
  "eventId": "evt-8b1f4d",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-20T03:00:00Z",
  "tenantId": "tenant-17",
  "aggregateId": "order-123",
  "correlationId": "req-456",
  "payload": {
    "orderId": "order-123",
    "customerId": "customer-42",
    "currency": "VND",
    "totalMinorUnits": 12500000
  }
}
~~~

`eventId` là identity của business event, ổn định qua retries. `MessageId` do SQS cấp là identity của một message được gửi vào queue; không nên coi nó luôn tương đương event ID khi producer retry bằng hai SendMessage calls khác nhau.

`schemaVersion` giúp consumer biết cách deserialize/migrate event. Không đưa access token, password, card data hoặc PII không cần thiết vào body/attributes.

### 2.5. Chọn queue topology

Một queue nên đại diện cho một luồng công việc/consumer contract có retention, retry, concurrency và security tương thích. Tách queue khi:

- Consumer có SLA hoặc throughput khác nhau;
- Một loại event cần FIFO còn loại khác không;
- Quyền IAM/retention/KMS/ownership khác nhau;
- Một consumer chậm không được phép gây backlog cho consumer khác.

Không tạo một queue cho từng message nếu không có nhu cầu isolation rõ.

## 3. Visibility timeout, long polling và redrive

### 3.1. Message lifecycle

Khi consumer nhận một message, SQS không xóa message ngay. Message chuyển sang trạng thái **in flight** và tạm ẩn khỏi các lần receive khác trong thời gian `VisibilityTimeout`.

~~~mermaid
sequenceDiagram
    participant Q as SQS
    participant W as Worker
    participant DB as Database
    W->>Q: ReceiveMessage
    Q-->>W: Message (in flight)
    W->>DB: Process + commit
    alt xử lý thành công
        W->>Q: DeleteMessage / acknowledge
        Q-->>W: Deleted
    else worker lỗi/crash hoặc không delete
        Note over Q: Visibility timeout hết hạn
        Q-->>W: Message có thể được giao lại
    end
~~~

Nếu consumer hoàn tất nghiệp vụ nhưng không xóa message, SQS có thể giao lại. Đây là lý do consumer phải idempotent **ngay cả khi acknowledgement mode được cấu hình đúng**.

### 3.2. Chọn VisibilityTimeout

`VisibilityTimeout` bắt đầu khi message được nhận. Trong thời gian này, consumer có trách nhiệm xử lý và acknowledge/delete.

Chọn timeout dựa trên:

- Thời gian xử lý p95/p99 thực tế;
- Batch size và số lượng messages xử lý đồng thời;
- Thời gian chờ database/downstream;
- Retry nội bộ của SDK/HTTP client;
- Khoảng thời gian shutdown/drain;
- Margin cho GC pause, scheduler delay và network jitter.

Timeout quá ngắn làm message xuất hiện lại khi consumer cũ vẫn đang chạy, dẫn đến **hai workers xử lý cùng message đồng thời**. Timeout quá dài làm message lỗi phải chờ lâu mới được retry và kéo dài thời gian phát hiện worker chết.

Không dùng một timeout tùy tiện cho mọi loại workload. Đo processing duration và đặt timeout lớn hơn thời gian xử lý tối đa dự kiến với margin phù hợp.

### 3.3. Visibility extension cho tác vụ dài

Nếu công việc có thời gian xử lý biến động, consumer có thể gọi `ChangeMessageVisibility` để gia hạn visibility khi còn xử lý. Cần:

- Gia hạn trước khi timeout hiện tại hết;
- Dùng heartbeat có giới hạn và dừng khi xử lý xong;
- Xử lý lỗi khi gia hạn thất bại;
- Đảm bảo chỉ worker đang sở hữu message tiếp tục side effect;
- Có deadline tổng thể để tránh giữ message vô hạn.

Ví dụ với consumer tự gọi AWS SDK for Java 2.x (không phải listener đã giao receipt handle cho Spring container): Giả sử `sqs` là `SqsClient` đã được cấu hình với đúng Region và credentials:

~~~java
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.ChangeMessageVisibilityRequest;

ChangeMessageVisibilityRequest request = ChangeMessageVisibilityRequest.builder()
    .queueUrl(queueUrl)
    .receiptHandle(receiptHandle)
    .visibilityTimeout(120)
    .build();

sqs.changeMessageVisibility(request);
~~~

`receiptHandle` phải là handle từ lần receive hiện tại; không dùng `MessageId`. Nếu Spring Cloud AWS đang quản lý message lifecycle, dùng cơ chế/framework API tương ứng thay vì tự delete/extend bằng một SqsClient khác.

SQS có giới hạn visibility tối đa **12 giờ tính từ lúc receive ban đầu**. Gia hạn không thể tạo một lease không giới hạn. Nếu job có thể chạy hàng giờ hoặc cần workflow dài, cân nhắc tách thành các bước nhỏ hoặc dùng workflow orchestration.

### 3.4. Long polling

SQS long polling giảm empty responses bằng cách đợi message đến trong một khoảng thời gian. `WaitTimeSeconds` tối đa là **20 giây**.

Queue attribute `ReceiveMessageWaitTimeSeconds` có thể cấu hình long polling mặc định; request `ReceiveMessage` cũng có thể chỉ định riêng. Với Spring Cloud AWS listener container, `pollTimeout` là cấu hình polling tương ứng trong version được chọn.

Long polling thường giảm API calls và chi phí so với short polling. Đảm bảo HTTP response timeout của client đủ dài hơn poll wait time cộng network margin; nếu client timeout trước khi SQS trả response, bạn có thể tạo retry không cần thiết.

### 3.5. Queue retention

SQS giữ message tối đa theo `MessageRetentionPeriod`:

- Default thường là **4 ngày**;
- Maximum là **14 ngày**;
- Queue retention phải phù hợp khả năng xử lý backlog và replay.

Retention không phải backup dài hạn. Nếu cần lưu audit/event history lâu hơn, ghi event vào durable event store/S3/data platform theo yêu cầu retention riêng.

### 3.6. Dead-letter queue

**Dead-letter queue (DLQ)** nhận những messages đã được giao quá số lần cho phép theo redrive policy.

~~~mermaid
flowchart TD
    Q[(Source queue)] --> W[Listener]
    W -->|success + delete| DONE[Processed]
    W -->|failure / no delete| RETRY[Visible after timeout]
    RETRY --> Q
    RETRY -->|receive count reaches maxReceiveCount| DLQ[(DLQ)]
    DLQ --> TRIAGE[Inspect, fix, redrive]
    TRIAGE --> Q
~~~

Redrive policy có các thông tin chính:

- `deadLetterTargetArn`: ARN của DLQ;
- `maxReceiveCount`: ngưỡng số lần receive; khi message đạt ngưỡng theo redrive policy, SQS chuyển message sang DLQ.

Ví dụ khái niệm:

~~~json
{
  "deadLetterTargetArn": "arn:aws:sqs:ap-southeast-1:111122223333:orders-dlq",
  "maxReceiveCount": 5
}
~~~

Đây là cấu hình mẫu, không phải lệnh áp dụng vào account. Chọn `maxReceiveCount` theo retry budget, thời gian visibility và mức độ transient của lỗi.

### 3.7. Quy tắc thiết kế DLQ

- DLQ phải cùng loại queue với source: Standard ↔ Standard, FIFO ↔ FIFO;
- DLQ cần retention đủ dài để điều tra; thường đặt dài hơn source queue;
- Bật alarm khi DLQ có message;
- Ghi nhận event ID, source queue, receive count, failure category và correlation ID;
- Không tự động redrive liên tục khi chưa sửa nguyên nhân;
- Có quy trình xác minh data/business state trước khi replay;
- Dùng redrive allow policy phù hợp để giới hạn source queues được phép gửi vào DLQ.

Với Standard queue, message expiration timestamp giữ quan hệ với enqueue time ban đầu khi chuyển sang DLQ; FIFO reset enqueue timestamp khi chuyển. Vì vậy, đặt DLQ retention dài hơn source và hiểu cách AWS tính retention cho loại queue của bạn.

**Lưu ý riêng cho FIFO:** khi message đầu của một group bị chuyển sang DLQ, các messages sau trong group có thể tiếp tục được xử lý. Điều đó giúp queue không bị chặn mãi nhưng có thể tạo khoảng trống trong business sequence. Nếu nghiệp vụ yêu cầu strict ordering tuyệt đối, hãy đánh giá việc dùng DLQ có phù hợp hay cần quy trình pause/reconcile theo aggregate.

### 3.8. Poison messages và phân loại lỗi

Một message **poison** luôn thất bại do payload/schema/business constraint, ví dụ thiếu `eventId`, version không hỗ trợ hoặc currency sai. Retry vô hạn không sửa được poison message.

| Loại lỗi | Hướng xử lý |
|---|---|
| Network timeout, throttling, database unavailable | Retry có backoff, giới hạn attempts |
| Temporary dependency outage | Không acknowledge; để SQS retry hoặc đổi visibility có kiểm soát |
| Invalid schema/unsupported event version | Lưu failure record/đưa DLQ; không retry vô hạn |
| Business rule rejected | Ghi trạng thái rejection có audit; quyết định ack/DLQ theo contract |
| Duplicate event đã commit | Xem là xử lý thành công; acknowledge |
| IAM/configuration error | Alert/stop rollout; retry hàng loạt thường không có ích |

Không nuốt mọi exception rồi return bình thường: listener container có thể acknowledge message dù business operation chưa hoàn tất.

### 3.9. Retry delay và backoff

SQS redelivery thường xảy ra sau visibility timeout nếu message chưa bị xóa. Muốn backoff tăng dần, có thể:

- Dùng `ChangeMessageVisibility` để đặt thời gian ẩn tiếp theo;
- Dùng retry queues với `DelaySeconds`/message timers trong giới hạn SQS;
- Dùng orchestration/workflow cho retry có lịch phức tạp.

Không dùng `Thread.sleep()` trong listener để chờ retry. Cách đó giữ thread/concurrency slot, làm giảm throughput và có thể khiến visibility timeout hết ngay khi worker đang ngủ.

### 3.10. Receive count không thay idempotency key

SQS cung cấp system attribute `ApproximateReceiveCount`. Có thể dùng để log/metric và phân loại retry, nhưng đây là **số lần receive gần đúng**, không phải event identity. Đừng dùng receive count làm idempotency key; một event có thể được gửi thành hai messages khác nhau, mỗi message có receive count bắt đầu riêng.

## 4. Idempotency: cùng event xử lý nhiều lần nhưng chỉ áp dụng một lần

### 4.1. Idempotency là gì?

Một operation là **idempotent** khi thực hiện lặp lại với cùng business input không làm thay đổi kết quả cuối nhiều lần. Ví dụ:

- Đặt trạng thái order thành PAID theo event ID có thể idempotent;
- Trừ tồn kho thêm 1 mỗi lần nhận message là **không idempotent**;
- Gửi email mỗi lần listener chạy là **không idempotent**;
- Ghi nhận event ID vào bảng có unique constraint giúp phát hiện lần xử lý đã hoàn tất.

Mục tiêu không phải ngăn SQS giao message trùng; mục tiêu là làm consumer **an toàn khi message trùng được giao**.

### 4.2. Dùng business event ID ổn định

Ví dụ:

~~~json
{
  "eventId": "evt-8b1f4d",
  "eventType": "OrderCreated",
  "aggregateId": "order-123",
  "schemaVersion": 1
}
~~~

`eventId` được tạo một lần khi business event được tạo và giữ nguyên qua các lần producer retry. Không tạo UUID mới cho mỗi lần gửi lại cùng một event, vì consumer sẽ coi đó là event mới.

`MessageId` của SQS phù hợp để correlation/debug một message, nhưng không thay thế business event ID xuyên producer retries, queue redrive và replay.

### 4.3. Inbox/processed-message table

Một bảng relational đơn giản:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

`consumer_name` cho phép cùng một event được xử lý bởi các consumer độc lập. Ví dụ `billing-projection` và `email-notifier` có idempotency namespaces riêng.

Có thể lưu thêm payload hash, schema version, correlation ID hoặc result reference để audit. Không lưu toàn bộ PII nếu không cần.

Nếu cùng `(consumer_name, event_id)` xuất hiện với payload hash khác lần đầu, coi đó là integrity/schema violation cần điều tra; không âm thầm xem là duplicate hợp lệ rồi bỏ qua.

### 4.4. Ghi inbox và business update trong cùng DB transaction

Với PostgreSQL, dùng `INSERT ... ON CONFLICT DO NOTHING` để claim event một cách atomic:

~~~sql
INSERT INTO processed_message (consumer_name, event_id)
VALUES (?, ?)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

Nếu số rows inserted là `1`, transaction này là lần đầu consumer nhận event và được phép áp dụng business update. Nếu là `0`, event đã được xử lý/claim trong một transaction đã commit; listener có thể xem đó là duplicate thành công.

**Ví dụ sau là PostgreSQL-specific SQL**, không phải cú pháp portable cho mọi RDBMS.

~~~mermaid
flowchart TD
    M[Receive eventId] --> TX[Begin DB transaction]
    TX --> I[Insert inbox row with unique key]
    I --> D{Inserted one row?}
    D -->|No| DUP[Already processed]
    DUP --> COMMIT1[Commit / return duplicate]
    D -->|Yes| B[Apply business database changes]
    B --> O[Insert outbox event if needed]
    O --> COMMIT2[Commit all DB changes]
    COMMIT1 --> ACK[Acknowledge SQS]
    COMMIT2 --> ACK
~~~

Điều quan trọng là **inbox insert, business state changes và outbox insert nằm trong cùng transaction**. Nếu business update lỗi, transaction rollback cả inbox row, để SQS retry có thể thử lại.

### 4.5. Java/Spring service với transaction

Ví dụ dùng `JdbcTemplate` và PostgreSQL:

~~~java
@Service
public class OrderEventProcessor {

    private final JdbcTemplate jdbc;

    public OrderEventProcessor(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public ProcessingResult process(OrderCreatedEvent event) {
        int inserted = jdbc.update("""
            INSERT INTO processed_message (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """,
            "order-projection",
            event.eventId().toString()
        );

        if (inserted == 0) {
            return ProcessingResult.DUPLICATE;
        }

        // Cùng transaction: business update phải rollback
        // nếu có bất kỳ bước nào bên dưới thất bại.
        jdbc.update("""
            UPDATE orders
               SET event_status = ?, updated_at = CURRENT_TIMESTAMP
             WHERE order_id = ?
            """,
            "CREATED",
            event.orderId().toString()
        );

        // Nếu cần external side effect, ghi outbox row ở đây.
        return ProcessingResult.APPLIED;
    }
}
~~~

Đây là ví dụ minh họa; production cần kiểm tra UPDATE row count, schema/constraints, event ordering và xử lý trường hợp order chưa tồn tại. Đảm bảo method được gọi qua Spring transactional proxy để transaction thực sự hoạt động.

Với synchronous listener, khi method process trả về qua proxy, transaction commit đã hoàn tất. Sau đó listener mới return thành công và acknowledgement mode ON_SUCCESS mới acknowledge message.

### 4.6. Vì sao không insert idempotency record trước rồi xử lý sau?

Mẫu sai:

~~~text
1. INSERT processed_message and COMMIT
2. Update order
3. Crash before order update
4. SQS redelivers
5. Consumer sees processed_message and skips
~~~

Event bị đánh dấu đã xử lý dù business update chưa xảy ra. Đặt **inbox claim + business writes trong một transaction** nếu cùng một database có thể tham gia transaction đó.

### 4.7. Race condition khi hai consumers nhận cùng event

Unique constraint trên `(consumer_name, event_id)` là hàng rào cuối cùng. Nếu hai workers cùng xử lý:

- Một transaction insert thành công;
- Transaction còn lại chờ/nhận conflict theo database semantics;
- Chỉ transaction insert thành công tiếp tục business updates;
- Transaction còn lại kết luận duplicate sau khi xác định conflict đã commit.

Không chỉ làm SELECT trước rồi INSERT sau: hai workers có thể cùng SELECT thấy “chưa tồn tại” và cùng thực hiện side effect. Cần **atomic unique constraint/conditional write**.

### 4.8. Idempotency record retention

Giữ processed IDs ít nhất bằng thời gian tối đa message có thể được retry, lưu trong DLQ, redrive hoặc replay. Nếu xóa record quá sớm, một message cũ được replay sẽ bị xử lý lại.

Nếu dùng TTL để dọn inbox rows:

- TTL thường xóa bất đồng bộ, không đúng giây;
- Thời gian TTL phải dài hơn retry/redrive/replay horizon;
- Không coi TTL là khóa business expiration chính xác;
- Với tài chính/ledger/audit, có thể cần giữ idempotency key lâu hơn nhiều hoặc theo retention policy.

### 4.9. Idempotency key phải phản ánh business operation

Không phải lúc nào eventId cũng đủ. Một API có thể tạo hai events khác nhau nhưng cùng đại diện một thao tác thanh toán. Khi đó, cần business key như paymentAttemptId, orderId + actionVersion hoặc idempotency key do client cấp và được lưu bền vững.

Tránh dùng chỉ orderId nếu một order có nhiều hợp lệ state transitions. Key phải phân biệt **mỗi business operation** nhưng giữ nguyên qua retry của chính operation đó.

## 5. Database transaction và side effects bên ngoài

### 5.1. Transaction chỉ bao phủ resource tham gia transaction

`@Transactional` với JDBC/JPA thường quản lý transaction trong **một relational database transaction manager**. Nó không tự atomic với:

- `DeleteMessage` của SQS;
- HTTP request tới payment provider;
- Email/SMS provider;
- Search index;
- Object storage;
- Một database khác không cùng transaction coordinator.

Không đặt kỳ vọng một annotation transaction sẽ commit cả SQS và DB.

### 5.2. Crash window giữa commit và acknowledgement

~~~text
Receive SQS message
  -> DB transaction commit
  -> Process crashes
  -> SQS message not deleted
  -> Visibility timeout expires
  -> Message delivered again
~~~

Lần xử lý thứ hai thấy inbox record đã commit, không lặp business update, return thành công và acknowledge. Đây là **at-least-once transport + idempotent consumer**.

Nếu consumer acknowledge trước khi commit DB, crash sau ack có thể làm mất công việc. Vì vậy, ack phải theo sau durable commit.

### 5.3. Transactional outbox

Khi business update cần phát event/email/search update, ghi một **outbox row** trong cùng database transaction:

~~~sql
CREATE TABLE outbox_event (
    outbox_id UUID PRIMARY KEY,
    event_type VARCHAR(120) NOT NULL,
    aggregate_id VARCHAR(160) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ
);
~~~

Transaction:

~~~text
BEGIN
  insert processed_message
  update orders
  insert outbox_event
COMMIT
~~~

Publisher/relay đọc các outbox rows chưa publish, gửi SQS/email/search event rồi đánh dấu published. Nếu relay gửi thành công nhưng crash trước khi đánh dấu, event có thể gửi lại; downstream consumer vẫn cần idempotency.

Outbox giải quyết **dual-write gap giữa database và broker** bằng cách làm thay đổi business state và ghi ý định phát event trong cùng transaction. Nó không biến external delivery thành exactly-once.

### 5.4. External API idempotency key

Nếu payment provider hỗ trợ idempotency key, gửi cùng key cho mọi lần retry của cùng operation:

~~~http
Idempotency-Key: payment-attempt-7a9...
~~~

Nếu timeout sau khi gửi request, hãy query/reconcile kết quả bằng cùng key trước khi tạo operation mới. Không tạo key mới chỉ vì response bị mất.

Email provider có thể không hỗ trợ idempotency thực sự. Trong trường hợp đó, outbox có thể đảm bảo event được phát bền vững nhưng không thể tuyệt đối ngăn email trùng sau một timeout không xác định; thiết kế business notification để chịu duplicate hoặc dùng provider có dedupe support.

### 5.5. Không giữ DB transaction mở trong lúc gọi HTTP lâu

Mẫu kém:

~~~text
BEGIN DB transaction
  insert inbox
  update order
  call payment/email HTTP API (seconds)
COMMIT
ack SQS
~~~

Giữ DB locks/connection trong lúc chờ network làm tăng contention và nguy cơ timeout. Tốt hơn:

1. Transactional DB update + inbox + outbox;
2. Commit;
3. Listener acknowledge;
4. Outbox relay gọi external service;
5. Relay ghi trạng thái/retry;
6. Consumer bên ngoài idempotent.

### 5.6. DynamoDB làm inbox store

Nếu business state cũng nằm trong DynamoDB, có thể dùng `TransactWriteItems` để ghi idempotency item và business item atomically trong cùng Region/account transaction limits. Dùng condition expression `attribute_not_exists(PK)` cho inbox key.

Nếu business state nằm ở RDS nhưng idempotency item ở DynamoDB, hai writes không tự atomic. Dùng RDS inbox table cùng RDS business transaction hoặc outbox/saga/reconciliation.

## 6. Retry policy theo failure type

### 6.1. Retry không phải phản ứng giống nhau cho mọi exception

Một consumer cần phân loại failure:

- **Transient:** network timeout, throttling, dependency tạm unavailable;
- **Permanent/poison:** payload invalid, schema version không hỗ trợ, thiếu field bắt buộc;
- **Business rejection:** order đã hủy, hạn mức không đủ, trạng thái không cho phép;
- **Duplicate:** event đã được commit;
- **Configuration/security:** IAM deny, endpoint sai, secret hết hạn.

Retry transient có thể thành công sau một khoảng thời gian. Retry permanent thường chỉ làm tăng backlog và chi phí. Duplicate là **success outcome**, không phải retry failure.

### 6.2. Error policy mẫu

| Kết quả xử lý | Listener behavior | SQS outcome |
|---|---|---|
| Applied successfully | Return success | Acknowledge/delete |
| Duplicate already committed | Return success | Acknowledge/delete |
| Temporary DB/network outage | Throw retryable exception | Không ack; redelivery theo visibility/redrive |
| Invalid schema | Lưu diagnostic bền vững rồi route DLQ/ack theo policy | Không retry vô hạn |
| Business rejection có chủ đích | Lưu rejection/audit rồi return success nếu contract xác định terminal | Acknowledge/delete |
| IAM/endpoint misconfiguration | Fail fast/alert, pause rollout | Tránh retry vô hạn và che lỗi |

Đối với permanent errors, một thiết kế có thể chủ động lưu failure record/DLQ bằng workflow riêng. Không vừa manually send vào DLQ vừa để source message tự redrive mà không có dedupe, vì có thể tạo hai bản failure.

### 6.3. Backoff và jitter

Nếu dependency đang quá tải, retry đồng loạt ngay lập tức tạo **thundering herd**. Dùng exponential backoff có jitter, bounded attempts và retry budget. Với SQS, cách thực thi có thể là:

- Đặt visibility delay phù hợp qua `ChangeMessageVisibility`;
- Dùng retry queue/delay queue;
- Giới hạn consumer concurrency khi downstream quá tải;
- Dùng circuit breaker để tránh tiếp tục gọi dependency đang lỗi.

Không giữ thread listener bằng sleep. Retry phải có metrics, maximum delay và dead-letter path.

### 6.4. Poison message và DLQ triage

DLQ là vùng cách ly để điều tra:

1. Kiểm tra source queue, event ID, schema version, approximate receive count;
2. Phân loại permanent/transient/configuration error;
3. Xác minh event có side effect nào đã xảy ra không;
4. Sửa consumer hoặc data issue;
5. Chọn replay/redrive có kiểm soát;
6. Theo dõi duplicate/idempotency metrics;
7. Lưu audit ai đã redrive, lúc nào và vì sao.

Không chỉnh payload DLQ bằng cách thủ công rồi replay mà không có audit/change control. Nếu cần sửa schema, ưu tiên migration/compatibility handler có kiểm thử.

## 7. Spring Boot và Spring Cloud AWS SQS listener

### 7.1. Chọn version tương thích

Với Spring Boot 3 và Java 17, có thể dùng Spring Cloud AWS 3.x cùng AWS SDK for Java 2.x. Quản lý version bằng BOM của Spring Cloud AWS và chọn phiên bản tương thích với Spring Boot release train của dự án.

Ví dụ Maven dependency:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>io.awspring.cloud</groupId>
      <artifactId>spring-cloud-aws-dependencies</artifactId>
      <version>${spring-cloud-aws.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-sqs</artifactId>
  </dependency>
</dependencies>
~~~

`spring-cloud-aws.version` là property do dự án quản lý, không phải version phát hành. Không trộn Spring Cloud AWS 2.x và 3.x imports/configuration; API packages và behavior khác nhau.

### 7.2. Cấu hình Region và queue name

Ví dụ application.yml:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  sqs:
    orders-queue: orders-events
~~~

Tên property cụ thể cần khớp với version Spring Cloud AWS được chọn. Trong production, Region có thể được cấp từ deployment configuration; tránh cho user request tùy ý điều khiển Region.

Credentials nên lấy từ provider chain của AWS SDK (ECS task role, EKS Pod Identity/IRSA, EC2 instance profile hoặc local SSO profile). Không thêm access key/secret vào application.yml.

### 7.3. SqsAsyncClient và listener container factory

Starter có thể auto-configure SQS client/container infrastructure. Khi cần cấu hình tường minh, ví dụ:

~~~java
import java.time.Duration;

import io.awspring.cloud.sqs.config.SqsMessageListenerContainerFactory;
import io.awspring.cloud.sqs.listener.acknowledgement.handler.AcknowledgementMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;

@Configuration
public class SqsListenerConfiguration {

    @Bean
    SqsAsyncClient sqsAsyncClient() {
        return SqsAsyncClient.builder()
            .region(Region.AP_SOUTHEAST_1)
            .build();
    }

    @Bean
    SqsMessageListenerContainerFactory<Object>
    defaultSqsListenerContainerFactory(SqsAsyncClient sqsAsyncClient) {
        return SqsMessageListenerContainerFactory.builder()
            .sqsAsyncClient(sqsAsyncClient)
            .configure(options -> options
                .acknowledgementMode(AcknowledgementMode.ON_SUCCESS)
                .maxConcurrentMessages(20)
                .maxMessagesPerPoll(10)
                .pollTimeout(Duration.ofSeconds(20)))
            .build();
    }
}
~~~

Đây là mẫu API cho Spring Cloud AWS 3.x; hãy pin một minor version và đối chiếu imports/options với version thực tế của dự án. Nếu starter đã cung cấp SqsAsyncClient, không khai báo bean trùng tên/loại ngoài ý muốn.

`maxConcurrentMessages` giới hạn số messages đang được container xử lý đồng thời; `maxMessagesPerPoll` không vượt quá giới hạn 10 messages của một SQS ReceiveMessage call. `pollTimeout` hỗ trợ long polling; HTTP client response timeout cần lớn hơn thời gian poll và margin mạng.

### 7.4. Listener với ON_SUCCESS acknowledgement

~~~java
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersListener {

    private final OrderEventProcessor processor;

    public OrdersListener(OrderEventProcessor processor) {
        this.processor = processor;
    }

    @SqsListener("${app.sqs.orders-queue}")
    public void onOrderCreated(OrderCreatedEvent event) {
        processor.process(event);
    }
}
~~~

Với `AcknowledgementMode.ON_SUCCESS`, container acknowledge message sau khi listener hoàn tất thành công. Nếu `processor.process(...)` ném exception, listener không được xem là success và message có thể được giao lại theo visibility timeout/redrive policy.

**Không bắt exception rồi chỉ log và return** nếu business transaction chưa hoàn tất. Return bình thường thường được container hiểu là thành công và message có thể bị acknowledge.

### 7.5. Manual acknowledgement

Manual ack phù hợp khi ứng dụng phải quyết định rõ thời điểm acknowledge sau khi commit hoặc sau khi ghi durable failure record. Ví dụ khái niệm cho Spring Cloud AWS 3.x:

~~~java
import io.awspring.cloud.sqs.annotation.SqsListener;
import io.awspring.cloud.sqs.listener.acknowledgement.Acknowledgement;
import org.springframework.stereotype.Component;

@Component
public class ManualOrdersListener {

    private final OrderEventProcessor processor;

    public ManualOrdersListener(OrderEventProcessor processor) {
        this.processor = processor;
    }

    @SqsListener(value = "${app.sqs.orders-queue}", acknowledgementMode = "MANUAL")
    public void onMessage(
            OrderCreatedEvent event,
            Acknowledgement acknowledgement) {

        processor.process(event); // transaction commit khi method trả về
        acknowledgement.acknowledgeAsync().join();
    }
}
~~~

Tên enum/annotation attributes có thể thay đổi giữa các minor versions. Trong cấu hình production, ưu tiên đặt manual mode trên listener container options bằng enum tương ứng nếu version hỗ trợ. Không bật manual mode mà quên gọi acknowledge: message sẽ được giao lại khi visibility timeout hết.

### 7.6. Vì sao listener nên mỏng?

Listener chỉ nên:

1. Nhận message và deserialize;
2. Validate envelope cơ bản;
3. Gọi application service;
4. Để exception được propagate theo retry policy;
5. Acknowledge theo mode đã chọn.

Business transaction/idempotency nên nằm trong service/repository để có thể test độc lập, reuse từ API hoặc replay job. Không nhồi DB, payment, retry sleeps và logging payload vào listener method.

### 7.7. Deserialization và schema compatibility

Khi queue chứa events nhiều version, không giả định mọi message có cùng schema. Có thể dùng envelope chung rồi dispatch theo eventType/schemaVersion.

- Validate event ID, event type và required fields;
- Reject version chưa hỗ trợ theo DLQ policy;
- Giữ compatibility khi thêm optional fields;
- Tránh đổi meaning của field cũ;
- Không log raw body chứa PII/secrets khi deserialize thất bại;
- Có thể lưu raw payload vào restricted failure store nếu incident process yêu cầu.

## 8. Java SDK v2 producer: gửi message ổn định

### 8.1. Standard queue

Ví dụ producer dùng AWS SDK for Java 2.x:

~~~java
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

public final class OrderEventPublisher {

    private final SqsClient sqs;
    private final String queueUrl;

    public OrderEventPublisher(SqsClient sqs, String queueUrl) {
        this.sqs = sqs;
        this.queueUrl = queueUrl;
    }

    public void publish(String jsonBody) {
        SendMessageRequest request = SendMessageRequest.builder()
            .queueUrl(queueUrl)
            .messageBody(jsonBody)
            .build();

        sqs.sendMessage(request);
    }
}
~~~

Queue URL nên được resolve/cấu hình từ trusted environment. Không nhận queue URL tùy ý từ API caller; điều đó có thể tạo confused-deputy/SSRF-like routing và gửi dữ liệu tới queue ngoài ownership.

### 8.2. FIFO queue

Với FIFO, producer cần `MessageGroupId`; có thể cung cấp `MessageDeduplicationId` hoặc bật content-based deduplication theo queue configuration:

~~~java
SendMessageRequest request = SendMessageRequest.builder()
    .queueUrl(fifoQueueUrl)
    .messageBody(jsonBody)
    .messageGroupId("ORDER#" + orderId)
    .messageDeduplicationId(eventId)
    .build();

sqs.sendMessage(request);
~~~

`MessageDeduplicationId` nên ổn định cho cùng event. Deduplication window là **5 phút**; đây không phải durable idempotency store cho toàn bộ lifetime của event.

Nếu queue bật content-based deduplication, SQS tạo deduplication ID dựa trên message body; message attributes không được dùng trong hash content-based deduplication. Nếu body khác do timestamp/random metadata, cùng business event có thể không dedupe như mong muốn.

### 8.3. Producer retry và ambiguous timeout

Nếu `SendMessage` timeout, producer không biết SQS đã nhận message hay chưa. Retry với cùng event ID và payload:

- FIFO: dùng cùng `MessageDeduplicationId` trong cửa sổ dedupe;
- Standard: consumer phải chịu duplicate;
- Cả hai: business event ID vẫn giữ nguyên;
- Nếu event được tạo từ DB transaction, dùng outbox để publisher có thể retry bền vững.

Không tạo event ID mới khi retry chỉ vì request timeout.

### 8.4. Outbox relay không nên giữ transaction lâu

Một relay có thể claim một nhóm outbox rows, commit claim/lease, publish messages rồi đánh dấu sent. Nếu crash sau publish trước mark-sent, relay có thể gửi lại. Consumer idempotency xử lý duplicate.

Có thể dùng CDC/Debezium hoặc polling relay; chọn theo throughput/latency/operational capability. Đảm bảo lease có timeout và stale claims được phục hồi sau crash.

## 9. Acknowledgement và delete semantics

### 9.1. Acknowledge là DeleteMessage

Trong SQS, acknowledgement cuối cùng tương ứng xóa message bằng receipt handle nhận được trong lần receive hiện tại. `MessageId` không phải receipt handle. Nếu receipt handle cũ hoặc không hợp lệ, delete có thể không đạt kết quả mong đợi.

Spring Cloud AWS container quản lý receipt handle và acknowledgement flow; không tự gọi `DeleteMessage` bằng ID nếu framework đã sở hữu message lifecycle.

### 9.2. Khi nào ack?

| Thời điểm ack | Hậu quả |
|---|---|
| Trước DB commit | Crash sau ack có thể làm mất event |
| Sau DB commit + inbox/idempotency | An toàn hơn; duplicate có thể được bỏ qua |
| Sau external API nhưng không có idempotency | Timeout/crash có thể tạo duplicate side effect |
| Sau durable rejection record | Có thể ack nếu policy xác định terminal |
| Không ack khi transient error | SQS redelivers sau visibility timeout |

**Ack sau durable outcome** là nguyên tắc. Durable outcome có thể là business transaction thành công, duplicate đã xử lý, hoặc permanent failure được lưu theo policy để không retry nữa.

### 9.3. Acknowledgement batching

Spring Cloud AWS có thể batch acknowledgements để giảm API calls. Khi bật batching, message có thể đã xử lý xong nhưng DeleteMessageBatch chưa gửi ngay. Consumer phải vẫn idempotent trong khoảng này.

Nếu batch delete thất bại một phần, container/framework cần xử lý các failed entries. Kiểm tra behavior và metrics của version Spring Cloud AWS đang dùng; đừng tự giả định mọi messages trong batch đều đã xóa.

### 9.4. Batch listener và partial failure

Một batch có nhiều messages; nếu một item fail, semantics acknowledgement phụ thuộc listener mode và framework version. Nếu xử lý batch, thiết kế rõ:

- Message nào đã commit business transaction?
- Message nào có thể ack?
- Có hỗ trợ partial acknowledgement/failed-message handling không?
- Một exception có làm cả batch redeliver không?
- Các side effects đã commit có idempotent khi batch chạy lại không?

Đừng nhầm partial batch response của **AWS Lambda SQS event source mapping** với Spring Cloud AWS listener container; hai integration có cấu hình riêng.

## 10. Queue configuration as infrastructure

### 10.1. Queue attributes cần quyết định

| Attribute | Mục đích | Gợi ý thiết kế |
|---|---|---|
| `VisibilityTimeout` | Thời gian ẩn message sau receive | Dựa trên processing p99 + margin |
| `ReceiveMessageWaitTimeSeconds` | Long polling | Thường dùng 20 giây nếu phù hợp |
| `MessageRetentionPeriod` | Thời gian giữ message | Dựa vào backlog/recovery window |
| `RedrivePolicy` | Chuyển message sang DLQ | Đặt max receive count có chủ đích |
| `KmsMasterKeyId` | SSE-KMS encryption key | Chọn key/policy theo compliance |
| `FifoQueue` | Bật FIFO semantics | Cả source và DLQ cùng loại |
| `ContentBasedDeduplication` | Tạo dedupe ID từ body | Chỉ bật khi body ổn định phù hợp |

Đặt queue attributes bằng IaC (CloudFormation/CDK/Terraform) để review, version control và tái tạo môi trường. Không cấu hình thủ công khác nhau giữa dev/staging/prod mà không có source of truth.

### 10.2. CloudFormation ví dụ cho Standard queue + DLQ

~~~yaml
Resources:
  OrdersDlq:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: orders-events-dlq
      MessageRetentionPeriod: 1209600

  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: orders-events
      VisibilityTimeout: 120
      ReceiveMessageWaitTimeSeconds: 20
      MessageRetentionPeriod: 345600
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt OrdersDlq.Arn
        maxReceiveCount: 5
~~~

Các giá trị 120 giây, 20 giây, 4 ngày và 5 receives là **ví dụ minh họa**; cần sizing theo measured processing time, retry budget và retention. DLQ trong ví dụ có retention dài hơn source queue.

### 10.3. FIFO queue + FIFO DLQ

Với FIFO, cả hai queue cần cấu hình FIFO và tên kết thúc bằng `.fifo`:

~~~yaml
Resources:
  OrdersFifoDlq:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: orders-events-dlq.fifo
      FifoQueue: true
      MessageRetentionPeriod: 1209600

  OrdersFifoQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: orders-events.fifo
      FifoQueue: true
      ContentBasedDeduplication: false
      VisibilityTimeout: 120
      ReceiveMessageWaitTimeSeconds: 20
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt OrdersFifoDlq.Arn
        maxReceiveCount: 5
~~~

Nếu dùng explicit `MessageDeduplicationId`, `ContentBasedDeduplication` có thể để false. Chọn một cách rõ ràng; không dựa vào content hash nếu message body có timestamp/random fields thay đổi mỗi lần gửi.

### 10.4. Visibility timeout của queue và listener

Container có concurrency/batch behavior riêng, nhưng SQS queue vẫn sở hữu visibility timeout. Cần kiểm tra:

- Processing time của một message;
- Batch processing duration nếu listener xử lý batch;
- Có gọi external API lâu không;
- Có extend visibility hay không;
- Có graceful shutdown/drain không;
- Retry policy và redrive count.

Nếu một batch 10 messages chạy tuần tự mất 90 giây, timeout 60 giây có thể làm các messages đầu tiên visible lại trước khi batch hoàn tất. Cấu hình concurrency và timeout dựa trên **thời gian message thực sự được giữ in-flight**.

### 10.5. Queue policy và DLQ redrive allow policy

Queue policy có thể giới hạn principals/services được phép gửi hoặc nhận message. Redrive allow policy có thể giới hạn source queues được phép sử dụng DLQ. Không để DLQ nhận message từ bất kỳ queue nào trong account nếu ownership không cho phép.

Nếu SQS trigger đến từ SNS/EventBridge/Lambda, policy cần allow đúng service principal/source ARN theo hướng dẫn integration tương ứng.

### 10.6. Quan sát queue bằng AWS CLI (chỉ đọc)

Trong sandbox account/Region được cấp, có thể kiểm tra URL và attributes mà không thay đổi queue:

~~~bash
REGION=ap-southeast-1
QUEUE_URL=$(aws sqs get-queue-url --queue-name orders-events --region "$REGION" --query QueueUrl --output text)

aws sqs get-queue-attributes --queue-url "$QUEUE_URL" --attribute-names All --region "$REGION" --output json
~~~

Đọc `VisibilityTimeout`, `ReceiveMessageWaitTimeSeconds`, `MessageRetentionPeriod`, `RedrivePolicy`, `KmsMasterKeyId` và queue type. Lệnh `get-queue-attributes` chỉ đọc; không copy queue URL/ARN hoặc payload nhạy cảm vào log công khai.

## 11. IAM, KMS và private networking

### 11.1. Least privilege cho consumer

Consumer thường cần các actions trên source queue:

- `sqs:ReceiveMessage`;
- `sqs:DeleteMessage`;
- `sqs:ChangeMessageVisibility` nếu extend visibility;
- `sqs:GetQueueAttributes`;
- `sqs:GetQueueUrl` nếu framework resolve queue URL từ name.

Không cấp `sqs:*` trên mọi queue nếu worker chỉ xử lý orders queue.

### 11.2. Producer permissions

Producer thường chỉ cần `sqs:SendMessage` trên queue đích. Nếu producer gửi FIFO, quyền action vẫn là SendMessage; các FIFO parameters nằm trong request.

Nếu app cần đọc attributes hoặc resolve URL, thêm quyền đúng nhu cầu. Tách producer role khỏi consumer role khi hai workload có ownership/security khác nhau.

### 11.3. KMS permissions với SSE-KMS

Nếu queue dùng customer-managed KMS key, producer/consumer cần các KMS permissions phù hợp với encryption workflow và key policy. Thường cần xem `kms:GenerateDataKey`/`kms:Decrypt` cho producer và `kms:Decrypt` cho consumer, tùy integration và key usage.

KMS key policy và IAM policy đều phải cho phép. SQS queue policy không thay thế KMS key policy. Không cấp `kms:*` trên mọi key.

### 11.4. Encryption in transit và at rest

SQS API sử dụng HTTPS/TLS để bảo vệ request khi truyền. Server-side encryption bảo vệ message body ở trạng thái lưu trữ. Chọn SSE-SQS hoặc SSE-KMS theo compliance, key ownership, audit và cross-account needs.

Không đưa secrets vào message body chỉ vì queue được mã hóa; consumer, DLQ readers, logs và exports vẫn có thể đọc payload.

### 11.5. VPC endpoint cho SQS

Trong môi trường private, có thể dùng **Interface VPC Endpoint** cho SQS:

- Enable Private DNS nếu kiến trúc yêu cầu;
- Endpoint security group cho phép HTTPS/443 từ worker;
- Endpoint policy giới hạn queues/actions;
- Queue/resource policy cho phép đúng principal;
- DNS và route hoạt động từ subnet của ECS/EKS/EC2;
- Kiểm tra endpoint và queue cùng partition/Region phù hợp.

PrivateLink không tự giải quyết IAM authorization. Cần cả network path và policy.

### 11.6. Queue URL và Region

SQS client Region phải phù hợp queue Region. Không dùng queue URL từ account/Region khác chỉ vì string URL hợp lệ. Resolve queue URL từ deployment config/trusted resource discovery, validate account/Region và không cho client bên ngoài cung cấp URL tùy ý.

### 11.7. Ví dụ policy consumer giới hạn vào một queue

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConsumeOrdersQueue",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueAttributes",
        "sqs:GetQueueUrl"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-events"
    }
  ]
}
~~~

Đây là policy minh họa cho consumer cần receive/delete/visibility extension. Nếu listener chỉ dùng fixed queue URL, có thể không cần `GetQueueUrl`; nếu không extend visibility, bỏ `ChangeMessageVisibility`. Producer nên có policy riêng chỉ cho `sqs:SendMessage`. Thêm KMS permissions riêng khi dùng SSE-KMS và kiểm tra queue/key resource policies.

## 12. Concurrency, backpressure và throughput

### 12.1. Bounded concurrency

Nếu mỗi listener xử lý message trong 2 giây và container cho 100 concurrent messages, downstream database có thể nhận đến 100 operations đồng thời từ một instance. Với 10 ECS tasks, concurrency lý thuyết có thể lên tới 1.000.

~~~text
Total in-flight work
  = number of worker instances
    x maxConcurrentMessages per instance
~~~

Sizing phải tính:

- Database connection pool;
- Downstream API rate limits;
- CPU/memory;
- SQS in-flight message quotas;
- FIFO message group concurrency;
- Retry/visibility behavior.

Không đặt concurrency bằng số lớn tùy ý với kỳ vọng queue luôn drain nhanh hơn.

### 12.2. Backpressure

Khi database quá tải:

- Giảm `maxConcurrentMessages`;
- Scale worker chậm lại hoặc tạm pause listener;
- Dùng circuit breaker/rate limiter;
- Đặt visibility/retry policy có kiểm soát;
- Theo dõi oldest message age và backlog;
- Không tiếp tục nhận nhiều message hơn khả năng xử lý bền vững.

Backpressure giúp bảo vệ downstream, nhưng backlog sẽ tăng. Cần alert theo SLO và capacity plan để xử lý backlog trước khi message retention hết hạn.

### 12.3. FIFO concurrency

FIFO có thể xử lý song song giữa các `MessageGroupId`, nhưng ordering trong cùng group cần giữ nguyên. Một group có message đầu tiên bị retry lâu có thể chặn các message sau trong cùng group (head-of-line blocking).

Chọn group ID đủ chi tiết để cho phép parallelism nhưng vẫn giữ invariant. Không chia một order thành nhiều groups nếu các transitions của order cần strict ordering.

### 12.4. Batch size

SQS ReceiveMessage trả tối đa **10 messages mỗi lần gọi**. Batch lớn giảm API calls nhưng có thể:

- Tăng thời gian một batch hoàn tất;
- Tăng memory;
- Kéo dài visibility needs;
- Làm retry một batch gây nhiều duplicate work;
- Làm failure isolation khó hơn.

Với Spring Cloud AWS, `maxMessagesPerPoll` và `maxConcurrentMessages` là hai knobs khác nhau; hiểu version semantics và đo trước khi tăng.

### 12.5. Scale theo queue metrics

Có thể scale worker theo backlog/oldest message age, nhưng không chỉ dựa vào visible message count. Nếu messages đang in-flight hoặc dependency đang throttle, tăng worker có thể làm tình trạng xấu hơn.

Dùng autoscaling có cooldown, maximum capacity và alarm downstream. Với FIFO, số message groups có thể giới hạn parallelism thực tế dù worker count cao.

## 13. Graceful shutdown và message ownership

### 13.1. Vì sao shutdown có thể gây duplicate?

Container có thể đang xử lý một message khi ECS task/Kubernetes pod nhận tín hiệu terminate. Nếu process dừng trước khi transaction hoàn tất:

- Không ack message;
- Visibility timeout hết;
- SQS giao lại message cho worker khác.

Nếu transaction đã commit nhưng process dừng trước ack, message được giao lại và inbox idempotency phải nhận ra duplicate.

Đây là failure mode bình thường của distributed consumer, không phải lý do để ack sớm.

### 13.2. Shutdown sequence đề xuất

~~~mermaid
sequenceDiagram
    participant P as Platform (ECS/K8s)
    participant C as SQS container
    participant W as Worker
    participant DB as Database
    P->>C: SIGTERM / stop lifecycle
    C->>C: Stop new polling
    C->>W: Allow in-flight work to finish
    W->>DB: Commit transaction
    W->>C: Listener success
    C->>P: Drain/close within grace period
    Note over P,C: Work not completed must remain unacknowledged
~~~

Khi shutdown:

1. Ngừng nhận thêm messages;
2. Chờ in-flight processing trong grace period;
3. Commit transaction và ack các messages hoàn tất;
4. Messages chưa hoàn tất không được ack;
5. Đóng SQS/HTTP clients sau khi listener container dừng.

### 13.3. Spring Boot graceful shutdown

`server.shutdown=graceful` chủ yếu điều khiển graceful shutdown của embedded web server; không tự chứng minh mọi SQS listener đã drain. Spring lifecycle timeout có thể cấu hình:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
~~~

Giá trị 45 giây là ví dụ. Kiểm tra listener container lifecycle của Spring Cloud AWS version đang dùng, đặt application termination grace period đủ dài và test SIGTERM khi message đang xử lý.

### 13.4. ECS và Kubernetes

- ECS `stopTimeout`/task shutdown window cần lớn hơn thời gian drain dự kiến và nằm trong giới hạn platform;
- Kubernetes `terminationGracePeriodSeconds` phải phù hợp với thời gian xử lý tối đa;
- Không để readiness/liveness probes gây restart liên tục khi queue/service có transient outage;
- Nếu shutdown timeout hết, process có thể bị kill; inbox/idempotency vẫn phải bảo vệ duplicate;
- Đừng phụ thuộc `preStop` sleep để thay cho listener lifecycle đúng.

### 13.5. In-flight work và visibility timeout

Nếu container dừng polling nhưng một message chưa xử lý xong, cần đảm bảo visibility vẫn đủ để worker drain. Nếu không thể drain trước deadline, để message không được ack và chấp nhận redelivery. Không kéo dài visibility vô hạn chỉ để tránh duplicate; idempotency là hàng rào đúng.

## 14. Observability: metrics, logs và tracing

### 14.1. SQS CloudWatch metrics

Các queue metrics quan trọng:

| Metric | Ý nghĩa | Cảnh báo khi |
|---|---|---|
| `ApproximateNumberOfMessagesVisible` | Messages đang chờ nhận | Backlog tăng kéo dài |
| `ApproximateNumberOfMessagesNotVisible` | Messages đang in-flight | Tăng cao bất thường hoặc stuck |
| `ApproximateNumberOfMessagesDelayed` | Messages đang delayed | Retry delay tăng ngoài dự kiến |
| `ApproximateAgeOfOldestMessage` | Tuổi message cũ nhất | Vượt processing SLO/retention budget |
| `NumberOfMessagesSent` | Messages gửi vào queue | Traffic spike/producer loop |
| `NumberOfMessagesReceived` | Messages được receive | Retry/duplicate tăng |
| `NumberOfMessagesDeleted` | Messages bị xóa | So sánh với receive/success |
| `NumberOfEmptyReceives` | Poll không có message | Polling inefficiency/configuration |

Các số liệu queue có semantics/aggregation riêng và một số là approximate. Đừng coi `NumberOfMessagesReceived - NumberOfMessagesDeleted` là số message chưa xử lý chính xác trong mọi tình huống.

### 14.2. Application metrics

Nên phát custom metrics theo queue/consumer:

- `messages_processed_total`;
- `messages_duplicate_total`;
- `messages_retryable_failure_total`;
- `messages_permanent_failure_total`;
- `message_processing_duration`;
- `message_receive_count`;
- `idempotency_conflict_total`;
- `outbox_publish_lag`;
- `dlq_message_count`;
- `downstream_dependency_error_total`.

Dùng dimensions có cardinality kiểm soát như queue, event type, result. Không đưa event ID, order ID hoặc user ID thành metric dimension vì cardinality tăng rất lớn và có thể lộ dữ liệu.

### 14.3. Structured logs

Ví dụ log an toàn:

~~~json
{
  "level": "INFO",
  "message": "SQS event processed",
  "queue": "orders-events",
  "eventType": "OrderCreated",
  "eventId": "evt-8b1f4d",
  "sqsMessageId": "sqs-message-id",
  "receiveCount": 2,
  "result": "DUPLICATE",
  "correlationId": "req-456",
  "durationMs": 14
}
~~~

Chỉ log identifiers cần cho vận hành theo policy. Không log raw message body, credentials, session tokens, payment details hoặc full customer PII. `eventId` và `MessageId` cần được bảo vệ theo data classification nếu có thể liên kết người dùng.

### 14.4. Distributed tracing

Propagate trace context qua message attributes hoặc event envelope theo convention đã chọn (ví dụ W3C Trace Context). Producer tạo span publish; consumer tạo span receive/process; outbox relay và downstream calls nối trace context.

SQS là asynchronous boundary nên trace có thể tách thành producer/consumer spans. Đừng giả định HTTP request span còn sống khi consumer chạy vài phút sau đó.

### 14.5. Alert theo SLO

Alert hữu ích:

- Oldest message age vượt ngưỡng;
- Visible backlog tăng liên tục;
- DLQ có message;
- Retry/duplicate ratio tăng đột biến;
- Processing p95/p99 vượt budget;
- In-flight messages stuck;
- Consumer count = 0 khi queue cần được xử lý;
- Downstream DB/API throttling hoặc error rate cao.

Alert cần kèm runbook/owner và tránh paging vì một spike ngắn không ảnh hưởng SLO.

## 15. Kiểm thử listener, retry và idempotency

### 15.1. Unit test business processor

Test các trường hợp:

1. Event mới: business state được cập nhật, inbox row được tạo;
2. Cùng event ID gửi lại: không áp dụng business update lần hai;
3. Business update fail: transaction rollback cả inbox row;
4. Hai workers đồng thời: unique constraint chỉ cho một transaction áp dụng;
5. External side effect: outbox record được tạo cùng transaction;
6. Event schema version không hỗ trợ: permanent failure theo policy.

Không chỉ mock repository để khẳng định idempotency; cần integration test với database/unique constraint thật (ví dụ Testcontainers PostgreSQL).

### 15.2. Integration test với SQS emulator

LocalStack hoặc Testcontainers có thể giúp test queue integration:

- Tạo queue Standard và FIFO;
- Gửi message và nhận qua listener;
- Kiểm tra acknowledgement/delete;
- Ném retryable exception để xác nhận redelivery;
- Kiểm tra DLQ redrive với receive count;
- Kiểm tra duplicate event ID;
- Kiểm tra FIFO ordering theo group;
- Gửi SIGTERM khi processing để kiểm tra shutdown.

Emulator không mô phỏng hoàn hảo IAM, KMS, quotas, eventual delivery, endpoint policies hoặc mọi behavior của AWS. Giữ một số smoke tests trong AWS sandbox được kiểm soát.

### 15.3. Test crash window commit-before-ack

Đây là test quan trọng:

~~~text
1. Worker nhận event E.
2. Inbox + business update commit.
3. Test giả lập crash trước acknowledgement.
4. Visibility timeout hết, E được giao lại.
5. Worker xử lý E lần hai.
6. Inbox unique constraint nhận ra duplicate.
7. Business update không chạy lần nữa.
8. Listener return success và ack.
~~~

Test này chứng minh idempotency ở business database, thay vì chỉ kiểm tra listener method chạy một lần.

### 15.4. Test retry và DLQ

- Dùng visibility timeout ngắn trong test sandbox;
- Cố ý ném exception có kiểm soát;
- Quan sát receive count tăng;
- Xác nhận message được chuyển DLQ sau `maxReceiveCount`;
- Redrive sau khi sửa consumer;
- Kiểm tra idempotency vẫn hoạt động khi message quay lại source queue.

Không giảm visibility timeout của production để test. Queue/DLQ test phải có tên, tags và owner riêng.

### 15.5. Test load và backpressure

Tăng dần producer rate, quan sát:

- Queue age/backlog;
- Worker concurrency và memory;
- DB connection pool saturation;
- Downstream throttling;
- Visibility expirations/duplicate processing;
- Retry/DLQ rate;
- p95/p99 end-to-end latency.

Load test phải dùng data giả và có budget. Không chạy flood test vào production queue.

## 16. Kịch bản thiết kế: OrderCreated worker

### 16.1. Yêu cầu

Một nền tảng bán khóa học có các yêu cầu:

- API tạo order và ghi OrderCreated event;
- Consumer cập nhật projection và phát yêu cầu gửi email;
- Một order không được áp dụng trạng thái hai lần do message duplicate;
- Payment/email provider có thể timeout;
- Worker chạy nhiều ECS tasks;
- Queue có thể backlog khi downstream database bảo trì;
- Message lỗi vĩnh viễn phải vào DLQ để điều tra;
- Hệ thống cần theo dõi age/backlog và shutdown an toàn.

### 16.2. Kiến trúc đề xuất

~~~mermaid
flowchart TD
    API[Spring Boot Order API] --> DB[(Orders DB)]
    DB --> OB[Transactional outbox]
    OB --> RELAY[Outbox relay]
    RELAY --> Q[(SQS Standard)]
    Q --> W1[Spring Boot worker task 1]
    Q --> W2[Spring Boot worker task 2]
    Q --> W3[Spring Boot worker task N]
    W1 --> TX[Inbox + projection transaction]
    W2 --> TX
    W3 --> TX
    TX --> OUT[Notification outbox]
    OUT --> NP[Notification publisher]
    NP --> EMAIL[Email provider]
    Q -->|redrive| DLQ[(Orders DLQ)]
~~~

### 16.3. Luồng xử lý

1. API tạo order và outbox event trong cùng transaction RDS.
2. Relay publish event với event ID ổn định.
3. SQS giao message cho một worker.
4. Listener deserialize envelope và gọi OrderEventProcessor.
5. Processor insert inbox record bằng unique key.
6. Nếu duplicate, return DUPLICATE và không update projection.
7. Nếu mới, update projection và insert notification outbox trong cùng DB transaction.
8. Transaction commit; listener return success.
9. Spring Cloud AWS ON_SUCCESS acknowledge message.
10. Notification publisher gửi email bằng idempotency key nếu provider hỗ trợ; cập nhật trạng thái outbox.
11. Lỗi transient không ack; SQS redeliver theo visibility/redrive.
12. Lỗi poison được chuyển DLQ; alert và triage trước redrive.

### 16.4. Những quyết định cần ghi vào ADR

- Standard hay FIFO; nếu FIFO, aggregate nào cần ordering?
- eventId được tạo ở đâu và giữ ổn định qua retries thế nào?
- Database inbox unique key/retention bao lâu?
- Business writes và inbox/outbox cùng transaction manager nào?
- Visibility timeout và maximum processing duration?
- maxReceiveCount, DLQ retention và redrive owner?
- Listener concurrency so với database pool?
- External API idempotency/reconciliation?
- Shutdown grace period?
- SLO/alarms và replay audit?

## 17. Chẩn đoán lỗi và runbook

### 17.1. Bảng sự cố thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra và xử lý |
|---|---|---|
| Message xuất hiện nhiều lần | Visibility timeout quá ngắn, worker crash, delete lỗi | So processing duration, visibility và delete/ack errors |
| DB update lặp | Thiếu durable idempotency hoặc event ID thay đổi | Inbox unique key, producer event identity |
| Listener thành công nhưng business chưa xong | Exception bị catch rồi return | Propagate exception hoặc ghi terminal outcome trước ack |
| Message không bao giờ retry | Listener ack sớm hoặc manual ack sai | Xem acknowledgement mode và ack call |
| Message vào DLQ quá sớm | maxReceiveCount thấp hoặc lỗi transient kéo dài | Xem receive count, retry budget và dependency health |
| DLQ tăng liên tục | Poison payload, schema incompatibility, IAM/config error | Phân loại lỗi và dừng redrive tự động |
| FIFO group bị nghẽn | Message đầu group retry lâu hoặc poison | Kiểm tra group ID, visibility và DLQ; đánh giá ordering contract |
| Consumer không nhận message | Sai Region/queue URL, IAM deny, listener không start | Kiểm tra effective Region, queue name, ReceiveMessage permission |
| SQS AccessDenied | IAM role, queue policy, endpoint policy | Kiểm tra principal/resource/condition |
| KMS AccessDenied | Thiếu KMS permissions hoặc key policy | Xem key policy và producer/consumer grants |
| UnknownHost/timeout | DNS/VPC endpoint/routes/SG | Test DNS, HTTPS/443 và endpoint policy |
| Deserialization error | JSON/schema/content type không khớp | Kiểm tra schemaVersion, converter và payload shape |
| Oldest message age tăng | Consumer capacity thấp hoặc downstream chậm | Backpressure, concurrency, dependency latency |
| In-flight messages tăng mãi | Worker bị kẹt, visibility extension loop hoặc ack không chạy | Thread dump, processing spans, visibility lifecycle |
| Redrive không thành công | DLQ type/policy/permissions sai | Kiểm tra source/DLQ type, redrive allow policy và IAM |

### 17.2. Runbook 10 bước

~~~text
1. Xác định source queue, DLQ, Region, account và consumer deployment.
2. Kiểm tra ApproximateAgeOfOldestMessage và visible/not-visible backlog.
3. Xem DLQ count, receive count và event type/schemaVersion.
4. Đối chiếu eventId với inbox/idempotency record.
5. Xác định transaction đã commit hay external side effect đã chạy chưa.
6. Phân loại transient, poison, business rejection hay IAM/configuration.
7. Kiểm tra visibility timeout, maxReceiveCount và listener acknowledgement mode.
8. Kiểm tra worker concurrency, DB pool, downstream throttling và network.
9. Sửa nguyên nhân, chạy test/sandbox và xác minh duplicate safety.
10. Redrive có kiểm soát, theo dõi metrics và ghi audit.
~~~

Không redrive DLQ chỉ để làm queue count về zero. Nếu nguyên nhân chưa được sửa, message sẽ quay lại DLQ và tăng tải.

### 17.3. Redrive an toàn

Trước khi redrive:

- Xác nhận consumer version đã fix và deploy;
- Kiểm tra event có side effect trước đó chưa;
- Đảm bảo inbox/idempotency retention vẫn còn;
- Chọn tốc độ redrive phù hợp capacity;
- Giới hạn số messages trong đợt đầu và quan sát;
- Có owner, ticket/change record và rollback/stop criteria.

Khi replay lịch sử vượt idempotency retention, cần tạo quy trình reconcile hoặc business-specific replay key. Không xóa processed IDs để “cho chạy lại” khi chưa đánh giá side effects.

## 18. Câu hỏi tự kiểm tra và đáp án

### 18.1. Câu hỏi

1. Vì sao SQS Standard được thiết kế theo at-least-once delivery?
2. SQS FIFO bảo đảm ordering trong phạm vi nào?
3. MessageDeduplicationId của FIFO có cửa sổ dedupe bao lâu?
4. Vì sao FIFO vẫn cần consumer idempotency?
5. Visibility timeout bắt đầu khi nào?
6. Điều gì xảy ra khi consumer không delete message?
7. Khi nào cần ChangeMessageVisibility?
8. Long polling tối đa bao nhiêu giây?
9. maxReceiveCount dùng để làm gì?
10. Source queue và DLQ cần cùng loại queue không?
11. Vì sao DLQ retention nên dài hơn source queue?
12. MessageId của SQS có thay thế business eventId không?
13. Vì sao không dùng ApproximateReceiveCount làm idempotency key?
14. AcknowledgementMode.ON_SUCCESS có ý nghĩa gì?
15. Vì sao không swallow exception rồi return từ listener?
16. Inbox record và business update nên nằm trong transaction nào?
17. Vì sao SELECT trước rồi INSERT không đủ chống duplicate race?
18. Transactional outbox giải quyết dual-write gap như thế nào?
19. @Transactional có atomic với DeleteMessage hay external HTTP API không?
20. Vì sao ack phải sau durable commit?
21. maxConcurrentMessages ảnh hưởng downstream capacity thế nào?
22. Vì sao FIFO message group có thể gây head-of-line blocking?
23. Những CloudWatch metrics nào giúp phát hiện backlog và DLQ?
24. Graceful shutdown nên làm gì với in-flight messages?
25. Vì sao LocalStack test không thay thế AWS sandbox smoke tests?

### 18.2. Đáp án gợi ý

1. SQS có thể giao lại message trong một số failure scenarios; consumer cần chịu duplicate.
2. Theo thứ tự trong cùng MessageGroupId; các groups khác có thể chạy song song.
3. 5 phút.
4. Consumer vẫn có thể commit rồi crash trước delete; message sẽ redeliver.
5. Khi SQS giao message cho consumer qua receive.
6. Message visible lại sau khi visibility timeout hết.
7. Khi processing dài hơn timeout dự kiến và cần giữ message in-flight có kiểm soát.
8. 20 giây.
9. Giới hạn số lần receive trước khi redrive sang DLQ.
10. Có; Standard source dùng Standard DLQ, FIFO source dùng FIFO DLQ.
11. Để có thời gian điều tra/replay; semantics expiration khác nhau theo queue type.
12. Không; MessageId là transport identity, eventId là business identity ổn định qua retries.
13. Receive count chỉ đếm lần giao gần đúng, không định danh business operation.
14. Acknowledge khi listener hoàn tất thành công.
15. Framework có thể coi return là success và delete message dù business chưa hoàn tất.
16. Cùng transaction với business database writes, inbox unique insert và outbox insert nếu cần.
17. Hai workers có thể cùng thấy chưa tồn tại trước khi insert; unique constraint/conditional write mới atomic.
18. Business update và ý định phát event được ghi cùng database transaction; relay có thể publish lại nên consumer vẫn idempotent.
19. Không; transaction chỉ bao phủ resource transaction manager quản lý.
20. Ack trước commit có thể làm mất event nếu process crash.
21. Tổng concurrency nhân số instances; cần nằm trong DB pool/downstream capacity.
22. Message đầu group bị retry có thể chặn các messages sau trong group.
23. ApproximateAgeOfOldestMessage, ApproximateNumberOfMessagesVisible/NotVisible, DLQ visible count và custom failure metrics.
24. Stop polling, drain/commit/ack completed messages; incomplete messages không ack để redeliver.
25. Emulator không mô phỏng đầy đủ IAM/KMS/quotas/network/production delivery behavior.

## 19. Checklist triển khai production

### Queue và delivery

- [ ] Đã chọn Standard/FIFO theo ordering và throughput requirement.
- [ ] Event envelope có eventId ổn định, eventType, schemaVersion, occurredAt và correlation ID.
- [ ] Visibility timeout dựa trên processing p99 + margin.
- [ ] Long polling/HTTP response timeout được cấu hình tương thích.
- [ ] Queue retention đáp ứng backlog/recovery window.
- [ ] DLQ cùng loại với source queue, có redrive policy và retention phù hợp.
- [ ] maxReceiveCount được chọn theo retry budget.
- [ ] Redrive allow policy, replay owner và audit workflow rõ ràng.
- [ ] FIFO MessageGroupId phân chia theo aggregate cần ordering.
- [ ] FIFO MessageDeduplicationId ổn định; không coi là durable idempotency.

### Consumer và correctness

- [ ] Spring Cloud AWS/Spring Boot versions được quản lý bằng BOM tương thích.
- [ ] Acknowledgement mode được cấu hình rõ, test đúng version.
- [ ] Listener không swallow exception khi processing chưa hoàn tất.
- [ ] Inbox/processed-message có unique key theo consumer + business event ID.
- [ ] Inbox insert và business DB changes nằm cùng transaction.
- [ ] Duplicate được xem là success và ack sau khi xác nhận durable state.
- [ ] External side effects dùng outbox/provider idempotency/reconciliation.
- [ ] Không giữ DB transaction mở trong lúc gọi HTTP lâu.
- [ ] Retry phân loại transient/permanent/business/configuration.
- [ ] Không dùng Thread.sleep trong listener để backoff.
- [ ] Idempotency retention dài hơn retry/DLQ/replay horizon.

### Security và operations

- [ ] Consumer/producer IAM roles least privilege theo queue ARN.
- [ ] KMS key policy/permissions được kiểm thử nếu dùng SSE-KMS.
- [ ] VPC endpoint/DNS/SG/queue policy được kiểm tra từ runtime.
- [ ] Không log raw payload, PII, credentials hoặc presigned URLs.
- [ ] Metrics backlog, oldest age, in-flight, retry, duplicate và DLQ có alarms.
- [ ] Trace context/correlation ID được truyền qua asynchronous boundary.
- [ ] Listener concurrency phù hợp DB pool và downstream rate limits.
- [ ] Graceful shutdown dừng polling và drain in-flight work trong grace period.
- [ ] Có test crash-after-commit-before-ack, retry, DLQ và duplicate race.
- [ ] Có AWS sandbox smoke tests ngoài emulator.
- [ ] Có runbook, redrive audit, capacity plan và budget.

**Kết quả mong đợi:** bạn có thể xây dựng SQS listener bằng Spring Boot với retry có giới hạn, idempotency bền vững, acknowledgement sau durable outcome, DLQ/replay có kiểm soát và observability đủ để vận hành khi consumer hoặc downstream gặp sự cố.

## Tài liệu AWS và Spring chính thức

- [Amazon SQS at-least-once delivery](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/standard-queues-at-least-once-delivery.html)
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Amazon SQS long polling](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-short-and-long-polling.html)
- [Amazon SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [Amazon SQS redrive allow policy](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [Amazon SQS FIFO queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues.html)
- [Amazon SQS message deduplication](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html)
- [Amazon SQS message attributes and system attributes](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-message-metadata.html)
- [Amazon SQS CloudWatch metrics](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html)
- [Amazon SQS server-side encryption](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-server-side-encryption.html)
- [Amazon SQS IAM policy examples](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-basic-examples-of-sqs-policies.html)
- [AWS SDK for Java 2.x SQS examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-sqs.html)
- [Spring Cloud AWS reference documentation](https://docs.awspring.io/spring-cloud-aws/docs/current/reference/html/index.html)
- [Spring Cloud AWS SQS integration](https://docs.awspring.io/spring-cloud-aws/docs/current/reference/html/index.html#sqs-integration)
- [Spring Framework transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)

> **Lưu ý áp dụng:** Queue names, ARNs, event IDs, order IDs, account IDs, timeouts và code trong bài là ví dụ đào tạo. Không chạy lệnh/configuration mẫu trực tiếp trên production khi chưa review. SQS/Spring Cloud AWS APIs, quotas và behavior có thể thay đổi theo Region/version; hãy pin dependency version, kiểm tra tài liệu tương ứng, test trên sandbox và bảo vệ dữ liệu nhạy cảm.
