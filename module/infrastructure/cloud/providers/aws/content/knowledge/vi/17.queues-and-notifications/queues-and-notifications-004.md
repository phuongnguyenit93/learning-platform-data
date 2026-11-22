# Message group, deduplication và thiết kế consumer idempotent

Trong một hệ thống bán hàng, service Java/Spring Boot có thể phát sự kiện `OrderCreated`, `OrderPaid`, `OrderCancelled` đến Amazon SQS/SNS để thanh toán, cập nhật tồn kho, tạo hóa đơn hoặc gửi thông báo. Cách làm bất đồng bộ giúp giảm phụ thuộc trực tiếp giữa các dịch vụ và xử lý tải tăng đột biến. Nhưng hệ thống phân tán phải đối mặt với hai loại lỗi khó: **message đến không đúng thứ tự nghiệp vụ** và **cùng một sự kiện gây side effect nhiều lần**.

**Amazon SQS FIFO** dùng `MessageGroupId` để sắp thứ tự trong từng nhóm, và `MessageDeduplicationId` để ngăn producer gửi lặp trong một cửa sổ ngắn. Tuy nhiên, **consumer vẫn có thể nhận lại message sau timeout hoặc crash**, cho nên application phải xử lý **idempotent**: chạy lại cùng business event không tạo thêm lần thanh toán, hóa đơn hoặc bản ghi trạng thái ngoài ý muốn.

Bài thuộc chương **Hàng đợi và thông báo** trong mô-đun **CLOUD_PROVIDERS_AWS**; kiến thức gắn với IAM, Region/AZ, SQS, SNS, Lambda, ECS/EC2, DynamoDB/RDS, VPC endpoints, CloudWatch và thiết kế ứng dụng an toàn, phục hồi được, có giám sát và kiểm soát chi phí.

> **Ba quy tắc khác nhau:** `MessageGroupId` xác định **phạm vi cần giữ thứ tự**; `MessageDeduplicationId` ngăn **producer gửi trùng trong 5 phút**; business `eventId` và idempotency store ngăn **side effect trùng dù message được giao lại sau vài phút, vài ngày hoặc qua DLQ redrive**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt SQS Standard, SQS FIFO và **SQS Standard fair queues**.
2. Chọn đúng `MessageGroupId` cho order, account, tenant, nhận biết giới hạn concurrency và hot group.
3. Phân biệt `MessageDeduplicationId` với SQS `messageId`, `receiptHandle` và `SequenceNumber`.
4. Giải thích deduplication window 5 phút, content-based SHA-256 và `DeduplicationScope` ở queue/group.
5. Phân tích vì sao FIFO không tự bảo đảm **exactly-once business processing**.
6. Thiết kế event envelope có `eventId`, `aggregateId`, `aggregateVersion` và correlation ID.
7. Tạo transactional inbox trên PostgreSQL, conditional writes trên DynamoDB và transactional outbox ở producer.
8. Dùng AWS SDK for Java 2.x để gửi FIFO messages và xử lý ack sau database commit.
9. Thiết kế SNS FIFO → nhiều SQS FIFO queues, xử lý subscriber filtering.
10. Dùng Lambda event source mapping với `ReportBatchItemFailures` mà không phá thứ tự FIFO.
11. Thiết kế retry, visibility timeout, DLQ/redrive và giới hạn concurrency.
12. Kiểm tra IAM, mã hóa, VPC endpoints, CloudWatch metrics, chi phí và bài lab chỉ đọc.

## 2. SQS Standard và FIFO: khác nhau ở đâu?

| Tiêu chí | SQS Standard | SQS FIFO |
|---|---|---|
| Thứ tự | Best effort; message có thể khác thứ tự gửi | Bảo đảm thứ tự **trong cùng group** |
| Duplicate delivery | At-least-once | Dedup khi enqueue trong 5 phút; consumer vẫn phải idempotent |
| `MessageGroupId` | Có thể dùng cho **fair queue** theo tenant | **Bắt buộc**, xác định luồng tuần tự |
| `MessageDeduplicationId` | Không dùng FIFO dedup mechanism | Bắt buộc cung cấp hoặc bật content-based dedup |
| Concurrency | Cao, không có khóa nhóm FIFO | Những groups độc lập có thể xử lý song song |
| Tên | Ví dụ `order-events` | Hậu tố bắt buộc `.fifo` |
| Phù hợp | Logs, telemetry, jobs độc lập, tenant fairness | Order state transitions, ledger/event streams theo key |

### 2.1. Điểm cập nhật về `MessageGroupId` trên Standard

AWS hiện có **SQS fair queues** cho Standard queues. Producer có thể gửi `MessageGroupId` như **tenant identifier**, giúp fair scheduling giảm ảnh hưởng của một tenant gây tải lớn (noisy neighbor).

**Không được nhầm:** Standard fair queue **không giữ thứ tự FIFO** trong group và không tuần tự hóa message của cùng tenant. Cùng field name nhưng semantics khác. Nếu ứng dụng yêu cầu `OrderCreated` phải được apply trước `OrderPaid`, dùng FIFO hoặc một protocol versioning đủ mạnh.

## 3. `MessageGroupId` và thứ tự trong FIFO

Với FIFO, mỗi message gắn với một group. Giả sử:

~~~text
Group order-101: A1 Created → A2 Paid → A3 Shipped
Group order-202: B1 Created → B2 Cancelled
Group order-303: C1 Created → C2 Paid
~~~

~~~mermaid
flowchart LR
  P["Producer: order service"] --> Q["SQS FIFO"]
  Q --> A["Group order-101: A1 → A2 → A3"]
  Q --> B["Group order-202: B1 → B2"]
  Q --> C["Group order-303: C1 → C2"]
  A --> W1["Worker 1"]
  B --> W2["Worker 2"]
  C --> W3["Worker 3"]
~~~

SQS giữ thứ tự **theo trình tự gửi được nó nhận thành công trong group**. Messages giữa các groups có thể được nhận/xử lý song song hoặc xen kẽ không xác định.

**Lưu ý về batch:** Một `ReceiveMessage` có thể trả **nhiều messages cùng group** theo thứ tự trong **một batch** (tối đa 10 messages mỗi lần receive). SQS không đưa thêm messages của group đó cho receive request khác trước khi batch đang in-flight được delete hoặc hết visibility timeout. Bên trong batch, application phải xử lý tuần tự nếu các events phụ thuộc nhau.

### 3.1. Chọn group theo aggregate

| Cách đặt | Ưu điểm | Rủi ro |
|---|---|---|
| `order-101`, `order-202` | Giữ thứ tự cho mỗi order, nhiều groups độc lập | Cần đồng nhất ID xuyên services |
| `account-456` | Giữ thứ tự giao dịch theo account | Account rất bận có thể là hot group |
| `tenant-789` | Dễ phân chia tenant | Tenant lớn làm một group nghẽn |
| `global` cho mọi message | Mọi message tuần tự theo broker | Concurrency thấp, một lỗi làm chặn toàn queue |
| UUID mới cho từng message | Nhiều groups, throughput cao | **Mất yêu cầu ordering theo cùng business entity** |

**Tư duy thiết kế:** Mỗi group phải tương ứng với ranh giới business cần giữ bất biến, thường là **aggregate root ID**. Không tự chia một aggregate thành nhiều groups để tăng tốc nếu order giữa các updates còn quan trọng.

### 3.2. Nhiều producer gửi đồng thời

Nếu Producer A gửi version 5 và Producer B gửi version 4 cùng group **đồng thời**, thứ tự SQS ghi nhận có thể là 5 rồi 4. FIFO không biết nghiệp vụ muốn 4 trước 5. Giữ **per-aggregate publication order** trong transactional outbox/relay; consumer dùng **business version** để phát hiện missing/stale/out-of-order transitions.

`SequenceNumber` do SQS cấp là số lớn, **không liên tục**; không dùng làm `aggregateVersion`. `MessageId` và `receiptHandle` cũng không thay business sequence.

## 4. Hot group, head-of-line blocking và high throughput

Nếu `A2` xử lý lỗi liên tục:

~~~text
order-101: A1 [done] → A2 [DB lỗi, retry] → A3 [waiting] → A4 [waiting]
order-202: B1 [processing] → B2 [processing later]
~~~

Group 101 bị **head-of-line blocking**, group 202 vẫn có thể tiến. Một queue chỉ có group `global` có thể bị một poison message chặn hết công việc.

Concurrency hữu dụng bị chặn bởi số groups đang đủ điều kiện:

\[
C_{\text{effective}} \le \min(G_{\text{ready}}, C_{\text{workers}}, Q_{\text{service}})
\]

Đây là công thức mô hình hóa, không phải service quota cụ thể.

SQS hỗ trợ **high-throughput FIFO** với:

~~~text
DeduplicationScope = messageGroup
FifoThroughputLimit = perMessageGroupId
~~~

Khi đó deduplication xảy ra **trong mỗi group**, throughput limit áp dụng theo group, hệ thống phân phối groups qua partitions. Với cấu hình `DeduplicationScope=queue` hoặc `FifoThroughputLimit=perQueue`, queue không vận hành ở mode high-throughput tương ứng.

**Giới hạn TPS thay đổi theo Region/quota và batching.** Đừng chốt kiến trúc dựa trên con số cố định cũ; xem [SQS message quotas](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/quotas-messages.html). Dùng nhiều groups độc lập và `SendMessageBatch` có thể tăng throughput, nhưng batch API cũng có **partial failures theo từng entry**.

## 5. `MessageDeduplicationId` và cửa sổ 5 phút

FIFO xử lý producer retries. Ví dụ:

~~~mermaid
sequenceDiagram
  participant P as Producer
  participant Q as SQS FIFO
  participant C as Consumer
  P->>Q: Send A, DedupId=evt-001
  Q--xP: ACK bị mất
  P->>Q: Retry A, DedupId=evt-001 (30 giây)
  Q-->>P: Success nhưng suppress duplicate
  Q->>C: Chỉ một A được đưa vào hàng đợi
  Note over Q: Cache dedup ID trong ~5 phút
  P->>Q: Retry A sau 6 phút
  Q->>C: Có thể có A mới
~~~

Nếu SQS đã chấp nhận một `MessageDeduplicationId`, lần send trùng trong **5 phút** có thể vẫn được ACK thành công nhưng **không được giao như message mới**. SQS vẫn nhớ ID này trong cửa sổ đó **sau khi message đã nhận và xóa**.

**Quan trọng:** Deduplication này chỉ áp dụng khi **producer gửi vào FIFO**, không tự ngăn consumer redelivery do **visibility timeout/crash** và không kéo dài vĩnh viễn. Consumer vẫn phải idempotent.

### 5.1. Queue-level vs message group-level dedup

| `DeduplicationScope` | Phạm vi loại duplicate | Lưu ý |
|---|---|---|
| `queue` | Toàn queue | Trùng dedup ID giữa hai groups có thể bị suppress |
| `messageGroup` | Trong một group | Cùng ID ở **khác groups** được xét độc lập |
| Kết hợp `perMessageGroupId` | High-throughput FIFO | Cần `DeduplicationScope=messageGroup` |

Ví dụ `order-101` và `order-202` đều gửi event type `Paid`. Nếu dedup ID chỉ là `Paid`, hai events hợp lệ có thể bị loại vì **không duy nhất**. Đặt dedup ID theo **event instance ổn định**, không theo event type.

## 6. Content-based deduplication

Nếu `ContentBasedDeduplication=true` và producer **không** truyền explicit dedup ID, SQS tính **SHA-256 của message body**, **không gồm message attributes**.

~~~json
{
  "eventId": "evt-8f20f9c7",
  "eventType": "OrderPaid",
  "aggregateId": "ord-101",
  "aggregateVersion": 5
}
~~~

Hai sends body giống nhau trong 5 phút sẽ bị coi là trùng theo dedup scope. Nhưng:

- Nếu body giống nhau còn **message attributes** khác, SQS vẫn có thể suppress event hợp lệ.
- Nếu cùng business event nhưng body đổi timestamp, whitespace hoặc thứ tự JSON fields, hash bytes có thể khác; không bị loại.
- **Explicit `MessageDeduplicationId`** được ưu tiên so với content hash khi đã cung cấp.

Với hệ thống đơn hàng, nên sinh **eventId** tại source transaction và dùng cả trong body lẫn explicit dedup ID, giữ nguyên qua retries. Nếu một event mới có nội dung tương tự, phải có **eventId mới**.

### 6.1. Những lựa chọn sai

| Dedup ID | Vì sao sai? |
|---|---|
| Timestamp hiện tại mỗi retry | Retry trở thành event mới |
| `OrderPaid` cho tất cả orders | Suppress nhiều events độc lập |
| UUID mới mỗi SendMessage attempt | Không chống retry |
| Customer ID cố định | Hai giao dịch khác nhau trong 5 phút có thể bị coi trùng |
| SQS `MessageId` làm dedup key phía gửi | MessageId chỉ sinh **sau khi send**, không xử lý tình huống mất ACK |

## 7. FIFO không tự cho exactly-once business processing

Có hai việc cần phân biệt:

- **Duplicate suppression at enqueue:** SQS FIFO cố ngăn cùng dedup ID vào queue hai lần trong cửa sổ 5 phút.
- **Business side effects exactly once:** database/payment/email của consumer phải không bị tác động lặp qua retries, timeouts và redrive.

Một timeline rất thường gặp:

~~~mermaid
sequenceDiagram
    participant Q as SQS FIFO
    participant C as Consumer
    participant D as PostgreSQL
    Q->>C: Deliver A (receiptHandle h1)
    C->>D: Update OrderPaid và COMMIT
    D-->>C: Commit thành công
    Note over C: Crash trước DeleteMessage
    Q->>Q: Visibility timeout kết thúc
    Q->>C: Redeliver A (receiptHandle h2)
    C->>D: Kiểm tra inbox eventId → đã xử lý
    D-->>C: No-op
    C->>Q: DeleteMessage bằng h2
~~~

SQS **không** có transaction chung với RDS. Nếu consumer commit database nhưng chết trước khi xóa message, message sẽ được nhận lại. Tương tự, Lambda event source mapping **at-least-once** có thể retry records. Vì vậy không dùng câu “SQS FIFO đảm bảo database update một lần” nếu chưa triển khai một **idempotency protocol**.

## 8. Event envelope và ba loại ID

Đề xuất payload:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-8f20f9c7",
  "eventType": "OrderPaid",
  "aggregateType": "Order",
  "aggregateId": "ord-101",
  "aggregateVersion": 5,
  "occurredAt": "2026-11-20T09:30:00Z",
  "correlationId": "req-2d5e78",
  "data": {
    "currency": "VND",
    "amountMinor": 250000
  }
}
~~~

| Key | Dùng để làm gì? |
|---|---|
| `eventId` | Business idempotency key, ổn định qua mọi retry/publish lại |
| `aggregateId` | Message group candidate, ví dụ `order-{aggregateId}` |
| `aggregateVersion` | Bảo toàn invariant và phát hiện gap/stale updates |
| `correlationId` | Tracing xuyên producer → queue → consumer |
| `schemaVersion` | Quản lý schema evolution |
| `eventType` | Phân nhánh consumer handler |
| `occurredAt` | Audit/latency, **không thay sequence number** |

**Không dùng mỗi SQS `messageId` làm idempotency key nghiệp vụ**: khi cùng business event bị re-publish sau dedup window, SQS có thể cấp **messageId mới**. Các consumers độc lập nên dùng key theo **(consumer_name, event_id)**, vì Billing và Notification đều phải xử lý cùng một eventId cho mục đích khác nhau.

Không đưa plaintext secrets/PII vào event body, group IDs hoặc logs. Dùng business ID nội bộ hoặc opaque IDs.

## 9. Idempotent consumer là gì?

Một phép xử lý event `e` được coi là idempotent trên trạng thái `S` nếu:

\[
f(f(S,e),e)=f(S,e)
\]

Chạy lại **cùng business event** không tạo thêm kết quả ngoài chủ định. Điều này **không có nghĩa consumer không bao giờ được invoke hai lần**.

| Pattern | Ví dụ | Hạn chế |
|---|---|---|
| Naturally idempotent | Gán status `PAID` thay vì tăng counter | Audit/email/ledger side effects có thể vẫn trùng |
| Unique business key | `UNIQUE(provider_payment_id)` | Cần transaction và xử lý unique violation |
| Transactional inbox | Ghi processed marker + state cùng DB transaction | Không atomic với external APIs |
| Conditional state change | Update nếu `version=expectedVersion` | Phải xử lý gaps/replays |
| DynamoDB TransactWriteItems | Put dedup key + Update business item atomic | Chỉ hiệu lực cho supported transaction scope |
| External idempotency key | Payment provider nhận `Idempotency-Key` | Phụ thuộc provider/time window |
| Transactional outbox | Commit domain state + event outbox cùng DB transaction | Relay có thể publish lặp; consumer vẫn idempotent |

### 9.1. Bẫy “check then act”

~~~text
if (NOT processed(eventId)) {
    charge_card();
    save_processed(eventId);
}
~~~

Không an toàn vì hai consumers có thể đồng thời thấy `processed=false` rồi cùng charge. Cần **unique constraint + transaction** để xử lý cạnh tranh, và với external payment API phải truyền provider-level stable idempotency key.

### 9.2. Thời hạn idempotency retention

Dedup marker phải giữ lâu theo **business replay horizon**, không chỉ 5 phút. Cân nhắc SQS retention, DLQ redrive sau nhiều ngày, producer outbox retries, regulatory/audit retention và payment provider window. Nếu DynamoDB TTL xóa marker, event cũ có thể được apply lại; với tài chính cần thêm **permanent business invariant** như ledger unique reference.

## 10. Transactional inbox với PostgreSQL

Để consumer `billing-projection` cập nhật read model sau `OrderPaid`, tạo bảng:

~~~sql
CREATE TABLE consumer_inbox (
  consumer_name VARCHAR(120) NOT NULL,
  event_id VARCHAR(160) NOT NULL,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (consumer_name,event_id)
);

CREATE TABLE order_projection (
  order_id VARCHAR(100) PRIMARY KEY,
  status VARCHAR(40) NOT NULL,
  aggregate_version BIGINT NOT NULL
);
~~~

Phương án xử lý trong **một database transaction**:

1. `INSERT INTO consumer_inbox ... ON CONFLICT DO NOTHING`.
2. Nếu insert **0 rows**, event đã xử lý; **không tạo business side effect** và commit/ACK.
3. Nếu insert **1 row**, validate event version và cập nhật business table.
4. **COMMIT** cả marker và state.
5. **Chỉ sau COMMIT** mới `DeleteMessage` trên SQS.

Một SQL minh họa:

~~~sql
BEGIN;

INSERT INTO consumer_inbox (consumer_name,event_id)
VALUES ('billing-projection','evt-8f20f9c7')
ON CONFLICT DO NOTHING;

-- Ứng dụng kiểm tra số rows vừa insert:
-- 0 => DUPLICATE, bỏ qua business update.
-- 1 => tiếp tục xử lý.

INSERT INTO order_projection(order_id,status,aggregate_version)
VALUES ('ord-101','PAID',5)
ON CONFLICT(order_id)
DO UPDATE SET
 status=EXCLUDED.status,
 aggregate_version=EXCLUDED.aggregate_version
WHERE order_projection.aggregate_version < EXCLUDED.aggregate_version;

COMMIT;
~~~

Đoạn SQL là **kịch bản mô tả**, không phải script transaction hoàn chỉnh vì việc chọn nhánh insert 0/1 phải do code/stored procedure thực hiện. Nếu business yêu cầu không được bỏ qua event version 4 khi nhận version 5, dùng **expected version +1** và xử lý gap thay vì chỉ dùng điều kiện `<`.

### 10.1. Phân tích cửa sổ lỗi

| Crash khi nào? | Tình trạng DB | Hành vi retry |
|---|---|---|
| Trước COMMIT | Transaction rollback | Apply lại bình thường |
| Sau COMMIT, trước `DeleteMessage` | State và inbox đã commit | Duplicate key → no-op, rồi delete |
| `DeleteMessage` thất bại | DB đã đúng | Retry → no-op, rồi delete |
| Delete **trước** DB commit | Message có thể mất nhưng state chưa commit | **Thiết kế sai** |

**Tuyệt đối không** ACK/delete trước business commit. Giữ marker và business update trong cùng transaction.

## 11. Java consumer với JDBC và AWS SDK v2

Đây là skeleton phần **xử lý một message** (chưa chứa JSON parser, network retry/backoff, scheduler và runbook). Dùng Java 21 records:

~~~java
public record OrderEvent(
        String eventId,
        String aggregateId,
        String status,
        long aggregateVersion
) {}
~~~

Code dưới đây đảm bảo inbox/state atomic rồi mới ACK SQS:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.DeleteMessageRequest;
import software.amazon.awssdk.services.sqs.model.Message;

public final class OrdersConsumer {
    private final DataSource db;
    private final SqsClient sqs;
    private final String queueUrl;

    public OrdersConsumer(DataSource db, SqsClient sqs, String queueUrl) {
        this.db = db;
        this.sqs = sqs;
        this.queueUrl = queueUrl;
    }

    public void process(Message message, OrderEvent event) throws SQLException {
        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new IllegalArgumentException("Missing event ID");
        }
        try (Connection conn = db.getConnection()) {
            conn.setAutoCommit(false);
            try {
                int inserted;
                try (PreparedStatement p = conn.prepareStatement(
                        "INSERT INTO consumer_inbox(consumer_name,event_id) "
                      + "VALUES(?,?) ON CONFLICT DO NOTHING")) {
                    p.setString(1, "billing-projection");
                    p.setString(2, event.eventId());
                    inserted = p.executeUpdate();
                }

                if (inserted == 1) {
                    try (PreparedStatement p = conn.prepareStatement(
                            "INSERT INTO order_projection(order_id,status,aggregate_version) "
                          + "VALUES(?,?,?) "
                          + "ON CONFLICT(order_id) DO UPDATE SET "
                          + "status=EXCLUDED.status, "
                          + "aggregate_version=EXCLUDED.aggregate_version "
                          + "WHERE order_projection.aggregate_version "
                          + "< EXCLUDED.aggregate_version")) {
                        p.setString(1, event.aggregateId());
                        p.setString(2, event.status());
                        p.setLong(3, event.aggregateVersion());
                        p.executeUpdate();
                    }
                }
                conn.commit();
            } catch (SQLException ex) {
                conn.rollback();
                throw ex;
            } catch (RuntimeException ex) {
                conn.rollback();
                throw ex;
            }
        }
        // Chỉ ACK sau khi transaction đã commit hoặc xác định duplicate.
        sqs.deleteMessage(DeleteMessageRequest.builder()
                .queueUrl(queueUrl)
                .receiptHandle(message.receiptHandle())
                .build());
    }
}
~~~

**Giới hạn của ví dụ:** Code minh họa read projection có thể bỏ qua old version khi `WHERE aggregate_version < ...` không match. Các nghiệp vụ strict state machine cần kiểm tra chính xác version trước/sau và xử lý gaps. Validate `status`, `aggregateId`, schema, authentication và business rules trước khi cập nhật DB. Thêm retries, metrics, input validation, monitoring, shutdown logic và transaction isolation theo DB. Nếu có external payment/notification API thì **không** thể atomic bằng riêng transaction PostgreSQL; dùng idempotency key của đối tác và outbox/reconciliation.

### 11.1. Long polling không phải “đọc vô hại”

~~~java
import java.util.List;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.Message;

public final class ReceiveLoopExample {
    public static void main(String[] args) {
        String url = System.getenv("ORDERS_FIFO_QUEUE_URL");
        try (SqsClient sqs = SqsClient.create()) {
            while (!Thread.currentThread().isInterrupted()) {
                List<Message> batch = sqs.receiveMessage(
                        ReceiveMessageRequest.builder()
                            .queueUrl(url)
                            .waitTimeSeconds(20)
                            .maxNumberOfMessages(10)
                            .build())
                    .messages();
                for (Message m : batch) {
                    // Parse event rồi gọi consumer idempotent.
                    // Khi lỗi: không ACK records chưa commit.
                    // Bảo đảm thứ tự trong mỗi FIFO group.
                }
            }
        }
    }
}
~~~

`ReceiveMessage` làm message **invisible**, tăng receive count và có thể khóa group. Skeleton không nên chạy trên production queue khi chưa có business processor/monitoring.

## 12. DynamoDB conditional writes và transaction

Nếu lưu processed marker trên DynamoDB:

~~~text
PK = CONSUMER#billing-projection#EVENT#evt-8f20f9c7
status = COMPLETED
processedAt = 2026-11-20T09:30:12Z
expiresAt = ...
~~~

Một `PutItem` với condition `attribute_not_exists(pk)` chặn nhiều workers cùng tạo marker. Nhưng nếu business update ở nơi khác thì marker **không đảm bảo atomic**.

Khi marker và state đều thuộc DynamoDB, dùng **`TransactWriteItems`**:

~~~text
Transaction:
  1. Put inbox key nếu attribute_not_exists(pk)
  2. Update order state nếu version đúng
Kết quả: cả hai thành công hoặc cả hai thất bại.
~~~

Nếu giao dịch fail vì marker đã tồn tại, có thể coi là duplicate sau khi kiểm tra đúng key/state. Nhưng **không** coi mọi conditional failure là duplicate: business version mismatch cũng có thể là dữ liệu không nhất quán.

**TTL cleanup không ngay lập tức** và sau khi marker bị xóa, replay event cũ có thể vượt dedup; với thanh toán/ledger cần unique reference dài hạn.

## 13. Transactional outbox cho producer

Consumer idempotent giải quyết **đầu nhận**, nhưng producer cũng có khoảng trống:

~~~text
UPDATE orders SET status='PAID';
COMMIT;
publish OrderPaid to SNS/SQS;   // Crash trước publish → mất event.
~~~

Đảo thứ tự (publish trước COMMIT) lại có thể phát sự kiện cho transaction đã rollback. Dùng **transactional outbox**:

1. Trong cùng DB transaction, cập nhật `orders`.
2. Insert `outbox_events(event_id, aggregate_id, version, payload, status)`.
3. Commit cả hai.
4. Relay/CDC đọc outbox, publish với `MessageGroupId=aggregateId` và `MessageDeduplicationId=eventId`.
5. Relay đánh dấu published; nếu crash trước khi đánh dấu, **có thể publish lại**.
6. Consumer inbox xử lý duplicate business event.

~~~mermaid
flowchart LR
    API["Order API"] --> TX["PostgreSQL transaction"]
    TX --> ORD["orders table"]
    TX --> OUT["outbox_events"]
    OUT --> REL["Relay / CDC"]
    REL --> SNS["SNS/SQS FIFO"]
    SNS --> CON["Idempotent consumer"]
    CON --> DB["Consumer business DB"]
~~~

**Outbox không có nghĩa publisher exactly-once.** Nó giảm rủi ro **DB đã commit nhưng event không publish**; relay vẫn có thể send hai lần, đặc biệt sau mất ACK. Cần per-aggregate publication order để không gửi version 5 trước version 4 khi relay có nhiều workers.

## 14. SNS FIFO fan-out tới các SQS FIFO queues

Một event cần tới Billing, Inventory và Notifications:

~~~mermaid
flowchart TD
    PUB["Order service + outbox"] --> TOPIC["SNS FIFO: order-events.fifo"]
    TOPIC --> BILL["SQS FIFO: billing.fifo"]
    TOPIC --> INV["SQS FIFO: inventory.fifo"]
    TOPIC --> NOT["SQS FIFO: notification.fifo"]
    BILL --> B["Billing consumer + inbox"]
    INV --> I["Inventory consumer + inbox"]
    NOT --> N["Notification consumer + inbox"]
~~~

SNS FIFO chuyển **MessageGroupId** tới SQS FIFO subscriptions để giữ thứ tự trong mỗi group theo các điều kiện dịch vụ. Mỗi subscriber có queue, retry và idempotency độc lập. Nếu subscription tới **SQS Standard**, không còn bảo đảm strict FIFO consumer order như FIFO queue.

### 14.1. `FifoThroughputScope` của SNS

SNS FIFO dùng attribute:

- `Topic`: deduplication ở topic scope; mặc định theo tài liệu.
- `MessageGroup`: deduplication theo group và hỗ trợ high throughput.

Theo tài liệu AWS hiện hành, sau khi đổi `FifoThroughputScope` sang `MessageGroup` thì **không đổi ngược sang `Topic`**. Phải quyết định trước khi sửa production. Với SNS FIFO high-throughput nên cân nhắc high-throughput SQS FIFO ở các queues subscribed.

### 14.2. Subscription filtering và delivery

SNS FIFO hỗ trợ filter theo message attributes hoặc body. Nếu có filtering, không hứa “mọi event tới mọi queue”: filter loại events không khớp và AWS lưu ý những điều kiện **at-most-once** với filtered subscriptions.

SNS FIFO không phát trực tiếp tới các endpoint email/SMS/HTTP(S) kiểu Standard mà vẫn bảo đảm strict FIFO. Muốn Lambda xử lý SNS FIFO, dùng **SNS FIFO → SQS FIFO → Lambda**; muốn gửi email, worker gọi SES/notification API có idempotency logic.

### 14.3. SQS queue policy cho SNS

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOneSnsFifoTopic",
      "Effect": "Allow",
      "Principal": { "Service": "sns.amazonaws.com" },
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:billing.fifo",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "arn:aws:sns:ap-southeast-1:111122223333:order-events.fifo"
        }
      }
    }
  ]
}
~~~

IDs/ARNs chỉ minh họa. Với SSE-KMS, kiểm tra thêm key policy. Không cho mọi SNS topics phát vào billing queue khi chỉ một topic được ủy quyền.

## 15. Lambda consumer của SQS FIFO và partial batch failures

Lambda event source mapping polls queue và invoke function với batches, **at least once**. Nếu batch xử lý A1/A2 thành công nhưng A3 lỗi, handler **throw exception** thì **toàn bộ batch** có thể được retry. A1/A2 đến lại là bình thường — consumer phải idempotent.

Bật cấu hình event source mapping:

~~~text
FunctionResponseTypes = ["ReportBatchItemFailures"]
~~~

Handler trả `batchItemFailures` chứa `messageId` của records cần retry. Với FIFO:

1. Xử lý batch **theo thứ tự**.
2. Khi một record lỗi, **dừng xử lý các record sau nó** (phương án an toàn nhất).
3. Trả **messageId của record lỗi và mọi record chưa xử lý**.
4. Chỉ những records đã xử lý thành công trước lỗi được Lambda xóa.
5. Không throw exception ra ngoài sau khi đã tạo partial response; nếu throw, **cả batch** bị coi là failed.

### 15.1. Java Lambda handler

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;
import java.util.ArrayList;
import java.util.List;

public final class OrderedFifoHandler
        implements RequestHandler<SQSEvent, SQSBatchResponse> {

    @Override
    public SQSBatchResponse handleRequest(SQSEvent event, Context context) {
        List<SQSBatchResponse.BatchItemFailure> failures = new ArrayList<>();
        List<SQSEvent.SQSMessage> batch = event.getRecords();
        for (int i = 0; i < batch.size(); i++) {
            SQSEvent.SQSMessage message = batch.get(i);
            try {
                processIdempotently(message);
            } catch (Exception ex) {
                context.getLogger().log(
                    "Batch failed at messageId=" + message.getMessageId());
                // FIFO: không xử lý records sau lỗi đầu tiên.
                for (int j = i; j < batch.size(); j++) {
                    failures.add(new SQSBatchResponse.BatchItemFailure(
                        batch.get(j).getMessageId()));
                }
                break;
            }
        }
        return new SQSBatchResponse(failures);
    }

    private void processIdempotently(SQSEvent.SQSMessage msg) {
        // TODO: Validate event + transactional inbox + business processing.
        throw new UnsupportedOperationException("Implement consumer");
    }
}
~~~

**Chú ý:** Đây là **skeleton**, method `processIdempotently` cố ý chưa triển khai và luôn fail; đừng deploy nguyên văn. Types `SQSEvent`/`SQSBatchResponse` thuộc `aws-lambda-java-events`. Nếu muốn tối ưu processing theo từng group trong một batch, phải bảo đảm group đã lỗi không xử lý record sau, và trả failure IDs đúng.

**Concurrency Lambda FIFO** bị giới hạn bởi số active groups, event source mapping maximum concurrency, reserved concurrency và các giới hạn dịch vụ. Đặt 100 workers không làm group `global` xử lý 100 messages đồng thời.

## 16. Visibility timeout, receipt handle và retry

Khi consumer `ReceiveMessage`, message **vẫn ở trong queue nhưng bị ẩn tạm thời**. `VisibilityTimeout` mặc định **30 giây**, cấu hình tối đa **12 giờ**.

- Nếu chưa `DeleteMessage` trước khi hết timeout, message có thể được giao lại.
- Dùng `ChangeMessageVisibility` để gia hạn khi xử lý dài; không kéo tổng thời gian vượt **12 giờ từ lần receive ban đầu**.
- Chọn timeout dựa trên P99 processing time + network jitter, không quá ngắn gây redelivery sớm, không quá dài khiến group bị chặn lâu.
- `ReceiptHandle` **thay đổi qua mỗi lần receive**; xóa bằng handle hiện tại, không lưu một handle cũ dùng mãi.
- `ReceiveRequestAttemptId` có thể giúp retry receive request đối với FIFO theo API semantics; **không** là business dedup key.

Với Lambda SQS mapping, AWS yêu cầu **Lambda timeout ≤ queue visibility timeout**, thường khuyến nghị queue visibility ít nhất **6 × function timeout**, cộng batching window nếu áp dụng, để chịu được throttling/retry. Đây là hướng dẫn vận hành, không bảo đảm consumer exactly-once.

## 17. Dead-letter queue và redrive mà không phá business order

Một poison message thất bại nhiều lần có thể bị chuyển tới **dead-letter queue (DLQ)** theo `maxReceiveCount`. Với FIFO source, dùng **FIFO DLQ** theo điều kiện AWS, thường cùng account/Region.

~~~mermaid
flowchart LR
    Q["SQS FIFO source"] --> C["Idempotent consumer"]
    C -->|"Commit + Delete"| DONE["Done"]
    C -->|"Fail, visibility expires"| Q
    Q -->|"maxReceiveCount exceeded"| DLQ["SQS FIFO DLQ"]
    DLQ --> REVIEW["Triage + approved redrive"]
    REVIEW --> Q
~~~

**Cảnh báo lớn:** Đẩy event version 3 của order-A sang DLQ rồi tiếp tục xử lý version 4 có thể phá **business ordering**, dù nguồn là FIFO. AWS cũng cảnh báo **DLQ không thích hợp cho các luồng nơi mọi bước bắt buộc phải được xử lý tuần tự** nếu không có reconciliation.

Khi redrive messages từ DLQ, chúng có thể **xen kẽ events mới** trong source queue. SQS có thể thay dedup ID khi chuyển FIFO → FIFO DLQ, vì thế giữ **stable eventId trong body**, business version và runbook replay.

Các bước xử lý phù hợp:

1. Phân loại lỗi tạm thời, poison payload hay lỗi quyền/network.
2. Giữ DLQ đủ lâu để phân tích; hạn chế truy cập body có PII.
3. Sửa consumer/schema/permission và test trên messages đại diện.
4. Với state machine strict, **tạm dừng hoặc điều phối** producer/consumer cho group liên quan khi replay nếu cần.
5. Dùng `aggregateVersion` để chống apply version cũ sau version mới.
6. Theo dõi DLQ backlog và business reconciliation sau redrive.

SQS retention có thể cấu hình **1 phút–14 ngày**, mặc định **4 ngày**. Đừng để messages hết retention trong lúc team chờ phân tích.

## 18. Producer Java AWS SDK v2

Ví dụ gửi một event có ID cố định qua retries:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

public final class OrderPublisher {
    public static void main(String[] args) {
        String queueUrl = System.getenv("ORDERS_FIFO_QUEUE_URL");
        String eventId = "evt-8f20f9c7";
        String orderId = "ord-101";
        String payload = """
          {"eventId":"evt-8f20f9c7","eventType":"OrderPaid",
           "aggregateId":"ord-101","aggregateVersion":5}
          """;

        try (SqsClient sqs = SqsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            var result = sqs.sendMessage(
                SendMessageRequest.builder()
                    .queueUrl(queueUrl)
                    .messageGroupId("order-" + orderId)
                    .messageDeduplicationId(eventId)
                    .messageBody(payload)
                    .build());
            System.out.println("Accepted SQS messageId=" + result.messageId());
        }
    }
}
~~~

**Đây là thao tác có tác động thật** nếu queue/IAM hợp lệ: có thể kích hoạt xử lý business và phí. Không chạy với queue production để “thử cú pháp”. Nên lấy eventId từ **outbox record**, không tạo UUID mới mỗi lần relay retry. SDK sử dụng default credentials chain, IAM role trên ECS/EC2/EKS hoặc profile dev, không hardcode AWS secret keys.

`SendMessageBatch` giúp giảm overhead nhưng mỗi response chứa **thành công và thất bại theo entry**; retry đúng failed entries với stable dedup IDs. Không coi HTTP 200 cho batch là mọi message đã publish thành công.

## 19. IAM, encryption, network và audit

| Role | IAM action quan trọng | Scope |
|---|---|---|
| Producer SQS | `sqs:SendMessage` | Đúng queue ARN |
| SNS publisher | `sns:Publish` | Đúng topic ARN |
| ECS/EC2 consumer | `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility`, `sqs:GetQueueAttributes` | Đúng queue ARN |
| Lambda SQS event source role | `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` | Queue nguồn; quyền KMS khi cần |
| SNS → SQS policy | `sqs:SendMessage` cho `sns.amazonaws.com` | Queue policy giới hạn `aws:SourceArn` topic |
| DLQ operator | `sqs:StartMessageMoveTask`/`sqs:CancelMessageMoveTask` và related rights | Quyền đặc biệt có approval |

**SSE-SQS/SSE-KMS** bảo vệ dữ liệu at rest nhưng không thay TLS, IAM, input validation và idempotency. Với customer-managed KMS key, xem `kms:GenerateDataKey`, `kms:Decrypt` cùng key policy cho producer/consumer/services theo đường xử lý.

Một worker trên ECS private subnet không NAT có thể gọi AWS APIs qua **Interface VPC Endpoints**, ví dụ:

~~~text
com.amazonaws.ap-southeast-1.sqs
com.amazonaws.ap-southeast-1.sns
~~~

Cần endpoint SG inbound TCP 443, Private DNS, route/NACL, IAM/endpoint policies phù hợp. **Lambda SQS event source mapping** được Lambda service poll; khác với function code chủ động gọi SQS API, nên không cần SQS VPC endpoint *chỉ để event source mapping poll*.

Giữ CloudTrail cho API control-plane audit, CloudWatch cho metrics/logs và business `eventId`/`correlationId` cho tracing. Không log full payload chứa PII/credentials.

## 20. AWS CLI chỉ đọc: queue/topic config

Các ví dụ dùng profile `dev`, Region `ap-southeast-1`, account `111122223333` **minh họa**. Thay URLs/ARNs bằng resources được cấp quyền trước khi chạy.

### 20.1. Identity và queue list

~~~bash
aws sts get-caller-identity \
  --profile dev \
  --query '{Account:Account,Arn:Arn}' \
  --output json

aws sqs list-queues \
  --queue-name-prefix orders- \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

### 20.2. Đọc các queue attributes

~~~bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders.fifo \
  --attribute-names \
    QueueArn FifoQueue ContentBasedDeduplication \
    DeduplicationScope FifoThroughputLimit \
    VisibilityTimeout MessageRetentionPeriod RedrivePolicy \
    ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

| Attribute | Cách hiểu |
|---|---|
| `FifoQueue` | Queue có thực sự là FIFO? |
| `ContentBasedDeduplication` | Dùng SHA-256 body tự động khi không có explicit dedup ID? |
| `DeduplicationScope` | `queue` hay `messageGroup`? |
| `FifoThroughputLimit` | `perQueue` hay `perMessageGroupId`? |
| `VisibilityTimeout` | Có đủ cho P99 worker/Lambda processing? |
| `MessageRetentionPeriod` | Có thời gian triage/recovery phù hợp? |
| `RedrivePolicy` | DLQ/maxReceiveCount và tác động tới ordering? |

`ApproximateNumberOfMessages` là **ước lượng**, không phải số lượng giao dịch kinh doanh.

### 20.3. SNS FIFO topic/subscription

~~~bash
aws sns get-topic-attributes \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events.fifo \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events.fifo \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Kiểm tra `FifoTopic`, `ContentBasedDeduplication`, `FifoThroughputScope` và filter policy. Khi cần filter chi tiết, dùng `get-subscription-attributes` với ARN đúng.

### 20.4. Lambda event source mapping

~~~bash
aws lambda list-event-source-mappings \
  --event-source-arn arn:aws:sqs:ap-southeast-1:111122223333/orders.fifo \
  --profile dev \
  --region ap-southeast-1 \
  --query 'EventSourceMappings[].{UUID:UUID,State:State,BatchSize:BatchSize,FunctionResponseTypes:FunctionResponseTypes,Scaling:ScalingConfig}' \
  --output json
~~~

### 20.5. Không dùng ReceiveMessage như một thao tác chỉ đọc

`ReceiveMessage` **làm message invisible** trong timeout và **tăng receive count**. Nếu queue có DLQ, một lần “xem thử” có thể đẩy message gần `maxReceiveCount`. Dùng GetQueueAttributes/CloudWatch để quan sát, hoặc chỉ receive trên queue lab có quyền/thỏa thuận.

## 21. Console và CLI tạo/gửi messages (có tác động)

### 21.1. Cấu hình FIFO queue qua Console

Trong SQS → Create queue:

1. Chọn **FIFO**, tên `orders.fifo`.
2. Chọn content-based dedup phù hợp hoặc chuẩn hóa explicit event ID.
3. Nếu cần high throughput, dùng `DeduplicationScope=messageGroup` và `FifoThroughputLimit=perMessageGroupId`.
4. Đặt visibility timeout/retention dựa trên SLA, không chỉ mặc định.
5. Chọn DLQ FIFO, maxReceiveCount và thủ tục redrive đảm bảo business ordering.
6. Cấu hình encryption, queue policy và CloudWatch alarms.
7. Test xử lý lỗi/trùng trong môi trường dev trước khi nhận traffic thật.

### 21.2. Ví dụ SendMessage (chỉ chạy trên queue lab)

~~~bash
# GỬI MESSAGE THẬT - có thể kích hoạt nghiệp vụ, không chạy production.
aws sqs send-message \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders.fifo \
  --message-body '{"eventId":"evt-8f20f9c7","eventType":"OrderPaid","aggregateId":"ord-101","aggregateVersion":5}' \
  --message-group-id order-ord-101 \
  --message-deduplication-id evt-8f20f9c7 \
  --profile dev \
  --region ap-southeast-1
~~~

### 21.3. Lambda partial batch flag (có tác động)

~~~bash
# Chỉ sau khi handler đã implement SQSBatchResponse đúng.
aws lambda update-event-source-mapping \
  --uuid 00000000-0000-0000-0000-000000000001 \
  --function-response-types ReportBatchItemFailures \
  --profile dev \
  --region ap-southeast-1
~~~

`UUID` là placeholder. Nếu handler vẫn throw exception ra ngoài, flag **không tự sửa** duplicate processing.

## 22. Monitoring, SLO và chi phí

### 22.1. Metrics quan trọng

| Nguồn | Metrics/gợi ý | Mục đích |
|---|---|---|
| SQS | `ApproximateNumberOfMessagesVisible` | Backlog |
| SQS | `ApproximateNumberOfMessagesNotVisible` | In-flight messages |
| SQS | `ApproximateAgeOfOldestMessage` | Độ trễ xử lý |
| SQS | `NumberOfMessagesSent`/`Received`/`Deleted` | Xu hướng API, không phải business unique count |
| DLQ | Message count/age và redrive failure | Poison events |
| Lambda | `Errors`, `Duration`, `Throttles`, concurrency | Failures/retry/concurrency |
| App | `inbox_duplicate`, `event_processing_lag_seconds`, per-group lag | Duplicates và ordering thực tế |
| DB | Transaction conflicts, unique violations, lock wait time | Idempotency storage health |
| SNS | Publish/delivery failure metrics | Fan-out reliability |

`SQS Approximate* metrics` không dùng để chứng minh thanh toán exactly-once. Dùng **ledger và business reconciliation** để xác minh.

### 22.2. Logging/Tracing

Log `eventId`, `aggregateId`, `aggregateVersion`, `correlationId`, SQS messageId/ApproximateReceiveCount (nếu có), consumer name và outcome:

~~~text
consumer=billing-projection
eventId=evt-8f20f9c7
aggregateId=ord-101
groupId=order-ord-101
outcome=APPLIED | DUPLICATE_SKIPPED | RETRY | DLQ
~~~

Đừng log thẻ thanh toán, token hoặc full event payload có PII.

### 22.3. Chi phí

| Thành phần | Phí có thể phát sinh |
|---|---|
| SQS Standard/FIFO | API calls, payload billing, data transfer |
| SNS FIFO | Publish/delivery, data transfer |
| Lambda | Invocations, duration, provisioned polling mode nếu dùng |
| RDS/DynamoDB | Inbox/outbox reads/writes, transactions, retention |
| KMS | SSE-KMS key và API usage |
| PrivateLink/NAT | Endpoint-hour/data processing, Internet egress |
| CloudWatch/CloudTrail | Logs, metrics, alarms, audit |
| DLQ/retention | Retry calls và lưu trữ messages chưa xử lý |

Một queue có 20 nhóm độc lập và 50 workers không nhất thiết xử lý nhanh hơn 20 workers. Tối ưu dựa trên **latency, retry rate, effective group cardinality**, không chỉ số threads.

## 23. Xử lý sự cố theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `SendMessage` FIFO báo missing group/dedup | Thiếu group hoặc không cung cấp dedup khi content-based off | Cấp stable IDs |
| Hai orders độc lập chỉ một event vào queue | Dedup ID trùng trong `queue` scope | Unique event IDs, xem queue attributes |
| Retry sau 6 phút tạo message mới | Cửa sổ dedup 5 phút đã hết | Consumer inbox/business key |
| Order version 5 nhận trước 4 | Nhiều producers publish không tuần tự | Per-aggregate relay ordering, version checks |
| Một group bị khóa | Poison event/visibility timeout | Triage, DLQ with order-aware runbook |
| Queue FIFO ít parallelism | Quá ít groups hoặc group `global` | Thiết kế aggregate group IDs |
| Standard fair queue không giữ thứ tự | `MessageGroupId` Standard chỉ có fairness semantics | Chọn FIFO nếu cần order |
| Cùng invoice được tạo hai lần | DB commit rồi SQS redelivery, thiếu inbox | Atomic unique marker + business transaction |
| Inbox có processed nhưng business thiếu | Marker commit riêng transaction | Commit cùng transaction |
| Duplicate charge dù inbox đúng | Charge external không thuộc DB transaction | Provider idempotency key, reconciliation |
| Lambda batch records thành công bị retry | Throw batch/thiếu partial failures | `ReportBatchItemFailures`, FIFO stop on failure |
| Messages vào DLQ và replay sai order | Redrive xen messages mới | Version-aware reconciliation |
| ReceiveMessage trong lab làm backlog thay đổi | Receive làm invisible và tăng receive count | Chỉ đọc attributes/metrics |
| SNS FIFO không tới queue | Subscription filter, queue policy, KMS | Xem SourceArn, filters, DLQ |
| SQS `AccessDenied` | IAM/queue policy/KMS/VPCE deny | Xác minh caller, ARN, endpoint policy |
| Consumer delete lỗi | Receipt handle cũ hoặc IAM `DeleteMessage` | Dùng handle hiện tại, role permissions |
| High throughput chưa bật | Attributes không đúng | `DeduplicationScope`/`FifoThroughputLimit` |
| Messages mất sau nhiều ngày | Retention hết, DLQ unmonitored | Retention/SLO, redrive/alarm |

### 23.1. Quy trình chẩn đoán

1. Xác nhận AWS account, Region, queue/topic ARN và FIFO/Standard type.
2. Đọc `MessageGroupId`, `MessageDeduplicationId`, `DeduplicationScope`, content-based setting.
3. Kiểm tra business `eventId/aggregateId/aggregateVersion` trong outbox/payload.
4. Kiểm tra consumer transaction, unique constraints, ack/delete timing.
5. Với Lambda, kiểm tra batch failure response, mapping, concurrency và visibility.
6. Với SNS, kiểm tra topic subscription filter, queue policy và KMS.
7. Đối chiếu CloudWatch + business DB + DLQ; replay qua runbook, không mở quyền wildcard.

## 24. Bài tập tình huống và câu hỏi tự đánh giá

### 24.1. Tình huống thực tế

Một Order API chạy ECS nhận đơn hàng. PostgreSQL lưu trạng thái và outbox. SNS FIFO phát events tới ba queues FIFO: Billing, Inventory, Notification. Yêu cầu:

- `OrderCreated` trước `OrderPaid` và `OrderShipped` **cho cùng order**.
- Các orders khác nhau xử lý song song.
- Producer/Lambda crash không được double-charge.
- DLQ replay không được apply version cũ sau version mới.

Thiết kế:

1. `MessageGroupId=order-{aggregateId}`.
2. `MessageDeduplicationId=eventId` ổn định qua retries.
3. Producer transactional outbox commit cùng business transaction; relay preserve per-aggregate order.
4. Mỗi consumer có unique inbox key `(consumerName,eventId)`.
5. Business updates và inbox marker atomic; với external charge thêm provider idempotency key.
6. Lambda partial batch response + FIFO stop after first error.
7. SQS visibility timeout/DLQ theo SLA, redrive version-aware.
8. Metrics backlog/lag/duplicate/DB transaction conflicts, least privilege IAM.

### 24.2. Bài tập

**A.** A1/A2/A3 trong `order-101`, B1/B2 trong `order-202`. A2 lỗi 90 giây. B2 phải chờ A2 không? **Không**, khác group. A3 phải chờ A2 không? **Có**.

**B.** Producer gửi `eventId=X`, response timeout, retry sau 30 giây; rồi retry lần nữa sau 6 phút. Bao nhiêu business effects hợp lệ? **Một**, nhờ consumer idempotent; broker có thể loại send 30 giây nhưng không bảo đảm loại send 6 phút.

**C.** Billing và Inventory đều nhận eventId X. Có nên dùng cùng bảng unique(eventId) không? **Không** nếu bảng chia sẻ; phải dùng key **(consumerName,eventId)**.

**D.** Lambda ghi DB xong nhưng chết trước delete. Có phải lỗi của SQS? **Không**; đó là redelivery dự kiến. Consumer xử lý lại bằng inbox no-op.

**E.** Dùng group `global` cho một triệu orders. Tăng Lambda concurrency có cải thiện throughput tương xứng không? **Không**; một group giữ thứ tự tuần tự.

**F.** Redrive version 3 từ DLQ sau khi version 4 đã commit. Có thể cập nhật state ngược lại version 3 không? **Không**; dùng version invariant và reconciliation.

### 24.3. Bài lab CLI chỉ đọc

Dùng các lệnh tại mục 20 để điền:

| Cấu hình | Giá trị quan sát | Kết luận |
|---|---|---|
| FIFO/Standard | `FifoQueue` | Có đảm bảo thứ tự theo group không? |
| Dedup scope | `queue/messageGroup` | Có nguy cơ suppress event khác group không? |
| Content dedup | `true/false` | Producer phải cấp explicit ID không? |
| Visibility | Số giây | Đủ cho P99 worker không? |
| DLQ | `RedrivePolicy` | Có giữ được invariants khi replay không? |
| Lambda mapping | `FunctionResponseTypes` | Có partial failure response không? |
| SNS topic | `FifoThroughputScope` | Dedup scope/topic throughput đúng không? |
| Authorization | IAM/queue policy/KMS | Có đúng least privilege không? |

**Không cần gửi, nhận, xóa hay redrive message thật** để hoàn thành lab.

### 24.4. Câu hỏi tự kiểm tra

1. SQS Standard có `MessageGroupId` không và nó dùng để làm gì?
2. FIFO giữ thứ tự trên toàn queue hay trên mỗi group?
3. Có thể receive chỉ một group bằng API parameter không?
4. `SequenceNumber` có dùng làm business aggregate version được không?
5. `MessageDeduplicationId` và `eventId` khác về mục đích thế nào?
6. Cửa sổ dedup của SQS FIFO là bao lâu?
7. Content-based dedup tính hash cả message attributes không?
8. Queue-level và message-group-level dedup khác ra sao?
9. Vì sao đã commit DB mà message vẫn được giao lại?
10. Tại sao một SELECT processed trước INSERT không đủ an toàn?
11. Transactional inbox có atomic với external payment gateway không?
12. Vì sao producer transactional outbox có thể publish trùng?
13. SNS FIFO tới SQS Standard có giữ FIFO processing không?
14. Với FIFO Lambda batch, sau lỗi đầu phải trả những IDs nào?
15. Visibility timeout có xóa message không?
16. Receipt handle có giữ nguyên sau mỗi lần receive không?
17. DLQ có thể phá business ordering như thế nào?
18. Vì sao không dùng SQS `messageId` làm business idempotency key?
19. SQS high-throughput FIFO cần hai attributes nào?
20. Những metrics nào phản ánh backlog và duplicate business effects?

### Định hướng đáp án

- **Group:** FIFO order theo aggregate; Standard fair queue group chỉ hỗ trợ fairness.
- **Dedup:** Cửa sổ **5 phút**, dựa trên explicit ID hoặc SHA-256 body không gồm attributes.
- **Consumer:** Có redelivery, nên giữ stable eventId, transactional inbox/business unique key, commit rồi ACK.
- **Producer:** Dùng outbox để giảm mất event; relay có thể publish trùng.
- **Vận hành:** Lambda partial batch failures cho FIFO, retry/visibility/DLQ version-aware, IAM/KMS, metrics và chi phí.

## 25. Tài liệu chính thức

1. [Amazon SQS overview](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html).
2. [FIFO queue delivery logic](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-understanding-logic.html).
3. [Exactly-once processing in Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html).
4. [MessageDeduplicationId behavior](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/using-messagededuplicationid-property.html).
5. [MessageGroupId with FIFO queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/using-messagegroupid-property.html).
6. [SQS Standard fair queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-fair-queues.html).
7. [SQS high-throughput FIFO](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/high-throughput-fifo.html).
8. [Enabling high-throughput FIFO](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/enable-high-throughput-fifo.html).
9. [Visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html).
10. [FIFO message IDs and receipt handles](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-fifo-queue-message-identifiers.html).
11. [Dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html).
12. [DLQ redrive](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue-redrive.html).
13. [Using Lambda with SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html).
14. [Handling Lambda SQS errors and partial batches](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html).
15. [Configuring Lambda SQS event source mappings](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html).
16. [Java SDK v2 SQS examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_sqs_code_examples.html).
17. [SNS FIFO message grouping](https://docs.aws.amazon.com/sns/latest/dg/fifo-message-grouping.html).
18. [SNS FIFO delivery](https://docs.aws.amazon.com/sns/latest/dg/fifo-message-delivery.html).
19. [SNS FIFO deduplication](https://docs.aws.amazon.com/sns/latest/dg/fifo-message-dedup.html).
20. [SNS high-throughput FIFO topics](https://docs.aws.amazon.com/sns/latest/dg/fifo-high-throughput.html).
21. [SNS FIFO subscription filtering](https://docs.aws.amazon.com/sns/latest/dg/fifo-message-filtering.html).
22. [SQS CloudWatch metrics](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html).
23. [SQS IAM access control](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-authentication-and-access-control.html).
24. [SQS VPC endpoints](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-internetwork-traffic-privacy.html).
25. [SQS pricing](https://aws.amazon.com/sqs/pricing/) và [SNS pricing](https://aws.amazon.com/sns/pricing/).

> **Ghi nhớ:** **FIFO không tự làm database, thanh toán hay email “exactly once”**. Chọn `MessageGroupId` theo aggregate; sinh `MessageDeduplicationId` ổn định cho từng business event; giữ `eventId` và `aggregateVersion` trong payload; consumer dùng **transactional inbox/unique constraint** và **chỉ ACK sau commit**; producer dùng outbox và xử lý retry. Kiểm soát visibility, DLQ, Lambda partial batch, network, IAM và monitoring để các retries không biến thành tác động nghiệp vụ lặp.

