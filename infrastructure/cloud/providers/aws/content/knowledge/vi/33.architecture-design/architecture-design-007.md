# Idempotency, outbox và tính nhất quán phân tán

## Mục tiêu bài học

Trong hệ sinh thái CLOUD_PROVIDERS_AWS, một nghiệp vụ thường đi qua nhiều thành phần: API nhận yêu cầu, dịch vụ ghi dữ liệu, hàng đợi truyền sự kiện và các dịch vụ khác tiếp tục xử lý. Mạng có thể timeout sau khi database đã commit; message broker có thể gửi lại thông điệp; Lambda có thể chạy lại một batch; client có thể retry vì không nhận được phản hồi. Nếu mỗi lần chạy lại đều tạo side effect mới, hệ thống có thể ghi trùng đơn hàng, trừ tiền hai lần, giữ tồn kho nhiều lần hoặc gửi thông báo sai.

Idempotency giúp một thao tác có thể được retry mà không tạo thêm kết quả nghiệp vụ ngoài dự kiến. Transactional outbox bảo đảm thay đổi dữ liệu và ý định phát sự kiện được ghi nhận nguyên tử trong cùng transaction của database. Inbox/deduplication giúp consumer xử lý an toàn khi nhận lại sự kiện. Khi nghiệp vụ đi qua nhiều dịch vụ và database, saga điều phối các local transaction cùng các hành động bù trừ để đưa hệ thống về trạng thái nghiệp vụ hợp lệ.

Sau bài học, người học có thể:

- Phân biệt idempotency, deduplication, retry, delivery semantics và exactly-once processing.
- Thiết kế idempotency key cho API và consumer, xử lý request đồng thời và lưu kết quả đã xử lý.
- Nhận diện lỗi dual-write giữa database và message broker.
- Triển khai transactional outbox bằng relational database hoặc DynamoDB Streams.
- Dùng inbox/processed-message table để bảo đảm side effect trong database chỉ được áp dụng một lần theo event ID.
- Chọn SQS Standard, SQS FIFO, EventBridge, DynamoDB Streams và Lambda theo yêu cầu thứ tự, độ bền và khả năng retry.
- Thiết kế versioning, ordering, retry, DLQ và reconciliation.
- Dùng saga orchestration hoặc choreography cho transaction trải qua nhiều microservice.
- Quan sát, kiểm thử và vận hành quy trình phân tán trong điều kiện duplicate, timeout, crash và mất kết nối.

## 1. Vì sao hệ thống phân tán khó giữ nhất quán?

Trong một ứng dụng đơn giản, một transaction database có thể cập nhật nhiều bảng nguyên tử: hoặc tất cả thay đổi commit, hoặc tất cả rollback. Khi nghiệp vụ mở rộng qua nhiều service, database và message broker, không còn một transaction ACID duy nhất bao phủ mọi thành phần.

Ví dụ, khi khách hàng đặt hàng:

1. Order service ghi đơn hàng vào RDS.
2. Order service gửi OrderPlaced tới SQS hoặc EventBridge.
3. Inventory service giữ hàng.
4. Payment service yêu cầu thanh toán.
5. Notification service gửi email xác nhận.

Một lỗi mạng có thể xuất hiện giữa bất kỳ hai bước nào. Giả sử database đã commit đơn hàng nhưng service timeout trước khi gửi sự kiện. Đơn hàng tồn tại nhưng Inventory service không biết để giữ hàng. Nếu service gửi sự kiện trước rồi transaction database rollback, Inventory service có thể giữ hàng cho một đơn hàng không tồn tại.

Đây là lỗi **dual write**: một thao tác nghiệp vụ phải ghi vào hai hệ thống độc lập, ví dụ database và message broker. Không có thứ tự gọi hai hệ thống nào loại bỏ được mọi cửa sổ lỗi:

| Thứ tự | Sự cố | Hậu quả |
|---|---|---|
| Ghi database rồi gửi message | Database commit thành công, gửi message thất bại | Dữ liệu đã lưu nhưng không có event |
| Gửi message rồi ghi database | Message được gửi, database transaction rollback | Consumer xử lý event cho dữ liệu chưa commit |
| Gửi message, nhận timeout | Broker có thể đã nhận message nhưng producer không nhận được ACK | Producer retry và có thể gửi trùng |
| Consumer xử lý xong nhưng không ACK | Message được giao lại | Consumer có thể lặp side effect |

Giải pháp cần xử lý ba vấn đề riêng:

- **Atomicity tại nguồn:** dữ liệu nghiệp vụ và event cần phát phải được lưu cùng nhau.
- **Delivery có thể lặp:** hệ thống phải chấp nhận event hoặc request được giao nhiều lần.
- **Consistency giữa dịch vụ:** các bước nghiệp vụ phải có cách retry, deduplicate, bù trừ và đối soát.

Transactional outbox giải quyết atomicity tại nguồn. Idempotency và inbox xử lý duplicate. Saga điều phối các bước phân tán và compensation khi một bước không thể hoàn tất.

## 2. Idempotency là gì?

Một thao tác idempotent có thể được thực hiện nhiều lần với cùng một ý định mà không làm tăng side effect ngoài mong muốn. Trong mô hình trạng thái, một phép biến đổi idempotent thỏa mãn:

\[
f(f(x)) = f(x)
\]

Ví dụ:

- Đặt trạng thái đơn hàng thành **SHIPPED** nhiều lần vẫn cho kết quả SHIPPED.
- Gán cấu hình desired capacity bằng 5 nhiều lần vẫn giữ capacity mục tiêu bằng 5.
- Ghi nhận một event ID đã xử lý nhiều lần không làm tăng số lần trừ tồn kho.

Ngược lại, các thao tác sau không tự idempotent:

- balance = balance - 100.
- inventory = inventory - 1.
- INSERT một đơn hàng mới mỗi lần nhận request.
- Gửi email hoặc thực hiện thanh toán mỗi lần handler được gọi.

Một API POST /orders thường tạo tài nguyên mới nên retry có thể tạo nhiều đơn hàng. API có thể hỗ trợ idempotency key để nhiều lần gửi cùng một yêu cầu logic trả về cùng một order/result.

Cần phân biệt:

| Khái niệm | Câu hỏi trả lời |
|---|---|
| Idempotency | Nếu cùng một thao tác được thực hiện lại, trạng thái nghiệp vụ có bị thay đổi thêm không? |
| Deduplication | Làm sao nhận biết hai request/message đại diện cùng một thao tác? |
| Retry | Khi lỗi tạm thời xảy ra, hệ thống thử lại như thế nào? |
| Delivery semantics | Producer/broker/consumer cam kết giao thông điệp theo cách nào? |
| Exactly-once effect | Làm sao bảo đảm side effect nghiệp vụ chỉ xảy ra một lần trong phạm vi được xác định? |

Idempotency không có nghĩa mọi lần gọi phải trả cùng một HTTP status hoặc cùng thời gian phản hồi. Một lần đầu có thể trả 201 Created, lần retry trả lại kết quả đã lưu với 200 OK; điều quan trọng là không tạo thêm đơn hàng hoặc thanh toán.

## 3. Vì sao không thể mặc định có exactly-once end-to-end?

Trong hệ thống phân tán, producer có thể gửi message thành công nhưng mất ACK. Consumer có thể xử lý thành công rồi crash trước khi xác nhận message. Broker phải quyết định có giao lại message hay không. Nếu không giao lại, có thể mất event; nếu giao lại, có thể tạo duplicate.

Vì vậy, nhiều dịch vụ AWS cung cấp at-least-once delivery ở một hoặc nhiều ranh giới:

- SQS Standard có thể giao một message nhiều lần và không bảo đảm thứ tự tuyệt đối.
- Lambda event source mappings xử lý record theo at-least-once; cùng một record có thể được xử lý lại.
- Lambda consumer của DynamoDB Streams cũng có thể xử lý cùng stream record nhiều lần khi invocation được retry.
- EventBridge có cơ chế retry delivery tới target; các dịch vụ nguồn có thể gửi event theo durable delivery at-least-once hoặc best-effort tùy loại event.

SQS FIFO có deduplication cho producer trong cửa sổ 5 phút và giữ thứ tự trong từng message group. Điều đó giúp giảm duplicate message được thêm vào queue, nhưng không biến mọi side effect của consumer, database và hệ thống bên ngoài thành exactly-once. Nếu consumer xử lý message nhưng không xóa được message trước khi visibility timeout hết hạn, message có thể được giao lại.

Một cách thiết kế thực tế là:

1. Chấp nhận message có thể được giao ít nhất một lần.
2. Mỗi sự kiện có một định danh ổn định.
3. Consumer ghi nhận event ID và cập nhật dữ liệu nghiệp vụ trong cùng transaction.
4. Side effect ngoài database cũng dùng idempotency key hoặc một workflow có thể retry an toàn.
5. Dùng DLQ và reconciliation để xử lý những trường hợp không thể tự phục hồi.

Mục tiêu không phải làm cho mọi thành phần chỉ chạy một lần. Mục tiêu là bảo đảm nhiều lần thực thi vẫn tạo ra một kết quả nghiệp vụ đúng.

## 4. Thiết kế idempotency key cho API

Idempotency key định danh một lần thực hiện nghiệp vụ logic. Client tạo key trước lần gửi đầu tiên và dùng lại key đó cho mọi retry của cùng yêu cầu.

Ví dụ, client tạo đơn hàng:

~~~http
POST /orders
Idempotency-Key: 5f2a2c7e-8a52-4f35-aef2-9e5d87f7d3b1
Content-Type: application/json

{
  "customerId": "customer-123",
  "items": [
    {"sku": "SKU-001", "quantity": 2}
  ]
}
~~~

Nếu client timeout sau khi server commit đơn hàng, client gửi lại cùng request với cùng Idempotency-Key. Server tra cứu record đã lưu và trả lại kết quả trước đó, không tạo order mới.

Một key nên có phạm vi rõ ràng, chẳng hạn:

- Tenant hoặc customer ID.
- Operation/API name.
- Idempotency key do client tạo.
- Hash của payload đã chuẩn hóa.

Ví dụ khóa logic:

~~~text
tenant-42#POST:/orders#5f2a2c7e-...
~~~

Không dùng riêng request body làm key nếu hai đơn hàng hợp lệ có cùng nội dung nhưng là hai ý định mua khác nhau. Ngược lại, không tạo key mới cho mỗi lần retry, vì như vậy server không thể nhận ra đó là cùng một thao tác.

### 4.1. Cùng key nhưng payload khác nhau

Nếu cùng một key được gửi với payload khác, server nên từ chối thay vì đoán ý định:

- Request đầu: key K1, thanh toán 100.000 đồng.
- Request sau: key K1, thanh toán 500.000 đồng.

Đây là xung đột sử dụng key. Server có thể trả 409 Conflict hoặc lỗi tương đương, đồng thời ghi log để điều tra. Không được trả kết quả của request đầu nhưng âm thầm thực hiện payload thứ hai.

### 4.2. Lưu trạng thái và kết quả

Một idempotency record thường có:

| Trường | Mục đích |
|---|---|
| idempotency_key | Khóa duy nhất trong phạm vi tenant/operation |
| request_hash | Phát hiện cùng key nhưng payload khác |
| status | IN_PROGRESS, SUCCEEDED hoặc trạng thái lỗi được quản lý |
| resource_id | ID order/payment/job đã tạo |
| response | Kết quả cần trả lại cho retry |
| created_at | Thời điểm nhận request đầu tiên |
| expires_at | Thời điểm hết thời hạn lưu record |
| lease_until | Hạn xử lý của worker đang giữ quyền thực thi |

Luồng xử lý:

~~~mermaid
flowchart TD
    A[Client gửi request với key K] --> B[Đọc hoặc claim idempotency record]
    B --> C{Record đã tồn tại?}
    C -- Chưa --> D[Conditional write IN_PROGRESS]
    D --> E[Thực hiện nghiệp vụ]
    E --> F[Commit kết quả và response]
    F --> G[Trả kết quả]
    C -- Có --> H{Request hash có giống?}
    H -- Không --> I[409 Conflict]
    H -- Có --> J{Status?}
    J -- SUCCEEDED --> K[Trả lại response đã lưu]
    J -- IN_PROGRESS --> L[Trả trạng thái đang xử lý hoặc retry sau]
    J -- Expired/Recoverable --> M[Claim lại theo lease và policy]
~~~

Việc claim key phải có tính atomic. Với DynamoDB, có thể dùng conditional PutItem hoặc UpdateItem; với relational database, dùng unique constraint và transaction. Nếu hai request đến đồng thời, chỉ một request được claim key thành công. Request còn lại đọc trạng thái hiện tại và không chạy side effect lần nữa.

Không nên giữ record IN_PROGRESS vô thời hạn. Nếu worker crash, lease hoặc in-progress expiry cho phép hệ thống xác định khi nào có thể thử lại. Tuy nhiên, lease hết hạn không chứng minh worker cũ đã dừng; nếu worker cũ có thể tiếp tục chạy, cần fencing token hoặc điều kiện version để ngăn worker cũ ghi đè kết quả mới.

### 4.3. Thời hạn idempotency

Thời gian lưu record phải dài hơn cửa sổ retry/replay mà hệ thống chấp nhận. Nếu xóa record quá sớm, một request cũ được gửi lại có thể tạo side effect mới.

Hãy xem xét:

- Thời gian client có thể retry.
- Thời gian API gateway, SDK hoặc proxy có thể retry.
- Thời gian message có thể nằm trong queue hoặc DLQ.
- Thời gian người vận hành có thể replay event.
- Yêu cầu kiểm toán và lưu lịch sử giao dịch.

TTL chỉ dùng để dọn record sau thời hạn. Không nên coi TTL là cơ chế khóa chính xác theo mili giây; cần kiểm tra expires_at trong logic ứng dụng trước khi nhận key là mới.

## 5. Idempotency cho consumer và side effect

Producer có thể gửi một event nhiều lần. Consumer phải dùng event ID hoặc một business key ổn định để nhận diện lần xử lý.

Ví dụ message:

~~~json
{
  "eventId": "evt-01J8QK9M4X",
  "eventType": "OrderPlaced",
  "aggregateId": "order-1001",
  "aggregateVersion": 1,
  "occurredAt": "2026-11-20T05:30:00Z",
  "payload": {
    "orderId": "order-1001",
    "customerId": "customer-123",
    "total": 250000
  }
}
~~~

Consumer cần lưu eventId đã xử lý. Nếu event đến lần thứ hai, consumer nhận ra duplicate và bỏ qua side effect. Việc ghi inbox record và cập nhật business table nên nằm trong cùng transaction:

~~~sql
BEGIN;

INSERT INTO processed_messages (consumer_name, event_id, processed_at)
VALUES ('inventory-service', 'evt-01J8QK9M4X', CURRENT_TIMESTAMP)
ON CONFLICT (consumer_name, event_id) DO NOTHING;

-- Chỉ áp dụng thay đổi tồn kho nếu INSERT thực sự tạo row mới.
-- Nếu event đã được xử lý, bỏ qua phần cập nhật.

COMMIT;
~~~

Đoạn SQL trên là pseudocode về thứ tự thao tác. Trong code thực tế, kiểm tra số row được insert; nếu bằng 0 thì event đã được xử lý. Nếu cập nhật tồn kho thất bại, transaction phải rollback cả inbox record để lần retry sau có thể xử lý lại.

Bảng inbox có thể dùng khóa chính (consumer_name, event_id). Nếu cùng event được xử lý bởi hai consumer khác nhau, mỗi consumer cần trạng thái riêng.

Không đặt inbox record trong một transaction rồi gọi external API sau đó mà không có cơ chế bảo vệ. Nếu consumer commit inbox trước khi gọi payment provider và crash, lần retry sẽ bị bỏ qua dù thanh toán chưa được thực hiện. Nếu gọi provider trước rồi commit inbox, crash giữa hai bước có thể tạo thanh toán lặp. Với side effect bên ngoài:

- Truyền cùng idempotency key tới provider nếu provider hỗ trợ.
- Hoặc ghi ý định gọi provider vào outbox riêng.
- Theo dõi trạng thái PENDING/CONFIRMED/UNKNOWN.
- Có bước query/reconciliation để xác định provider đã thực hiện thao tác hay chưa.

## 6. Transactional outbox giải quyết dual-write

Transactional outbox lưu event vào một bảng cùng database với dữ liệu nghiệp vụ. Ứng dụng ghi business data và outbox event trong cùng một transaction. Một relay riêng đọc các event đã commit rồi gửi chúng tới broker.

Luồng:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Order Service
    participant DB as RDS/Aurora
    participant R as Outbox Relay
    participant Q as SQS/EventBridge
    participant I as Consumer

    C->>S: POST /orders + Idempotency-Key
    S->>DB: BEGIN
    S->>DB: INSERT order
    S->>DB: INSERT outbox event
    S->>DB: COMMIT
    DB-->>S: Commit success
    S-->>C: Order created
    R->>DB: Read committed pending events
    DB-->>R: Event payload + event_id
    R->>Q: Publish event
    Q-->>R: Acknowledgement
    R->>DB: Mark event published
    Q->>I: Deliver event (possibly more than once)
    I->>I: Inbox dedup + business transaction
~~~

Nếu transaction database rollback, cả order và outbox row đều không tồn tại. Nếu transaction commit, event intent đã được lưu bền vững và relay có thể gửi sau, kể cả khi broker tạm thời unavailable.

Outbox không tạo transaction ACID xuyên database và broker. Nó tạo atomicity giữa business state và event intent trong database, sau đó dùng asynchronous delivery. Vì relay có thể gửi lại, consumer vẫn phải idempotent.

### 6.1. Cấu trúc bảng outbox

Ví dụ với PostgreSQL:

~~~sql
CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(150) NOT NULL,
    aggregate_sequence BIGINT NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    lease_owner VARCHAR(150),
    lease_until TIMESTAMPTZ,
    UNIQUE (aggregate_type, aggregate_id, aggregate_sequence)
);
~~~

Ý nghĩa:

- event_id: định danh ổn định để deduplicate.
- aggregate_id: entity phát sinh event, ví dụ order ID.
- aggregate_sequence: thứ tự event trong một aggregate.
- event_type: loại sự kiện.
- payload: dữ liệu cần cho consumer.
- published_at: thời điểm relay xác nhận broker đã nhận.
- attempts, next_attempt_at: quản lý retry và backoff.
- lease_owner, lease_until: phối hợp nhiều relay worker để tránh xử lý cùng row đồng thời.

Có thể thêm schema_version, correlation_id, causation_id, tenant ID và trace ID để hỗ trợ tương thích schema và điều tra.

### 6.2. Ghi business data và outbox trong cùng transaction

Ví dụ tạo order:

~~~sql
BEGIN;

INSERT INTO orders (
    order_id,
    customer_id,
    status,
    total_amount,
    version
) VALUES (
    'order-1001',
    'customer-123',
    'PENDING',
    250000,
    1
);

INSERT INTO outbox_events (
    event_id,
    aggregate_type,
    aggregate_id,
    aggregate_sequence,
    event_type,
    payload
) VALUES (
    '11111111-1111-4111-8111-111111111111',
    'Order',
    'order-1001',
    1,
    'OrderPlaced',
    '{"orderId":"order-1001","customerId":"customer-123","total":250000}'
);

COMMIT;
~~~

Nếu một trong hai INSERT thất bại, toàn transaction rollback. Event không thể được phát cho một order chưa commit. Trong ứng dụng thật, order ID và event ID được tạo theo cơ chế duy nhất; aggregate sequence được tăng có kiểm soát trong cùng transaction.

### 6.3. Relay và cửa sổ duplicate

Relay có thể dùng polling hoặc change data capture (CDC).

**Polling relay:**

1. Tìm các row chưa published và đến thời điểm retry.
2. Claim row bằng lock/lease.
3. Publish message tới SQS hoặc EventBridge.
4. Chỉ sau khi nhận ACK, đánh dấu published_at.
5. Nếu publish thất bại, tăng attempts và đặt next attempt theo exponential backoff có jitter.

Có một cửa sổ lỗi không thể loại bỏ chỉ bằng polling: broker đã nhận event nhưng relay crash trước khi đánh dấu published_at. Sau khi lease hết hạn, relay gửi lại event. Vì vậy event ID phải ổn định và consumer phải deduplicate.

Không đánh dấu published trước khi gửi, vì nếu relay crash sau khi đánh dấu mà trước khi publish, event sẽ bị mất. Gửi trước rồi đánh dấu sau chấp nhận khả năng duplicate để tránh mất event.

Khi có nhiều relay worker, dùng SELECT ... FOR UPDATE SKIP LOCKED hoặc cơ chế lease/claim tương đương. Không giữ database lock trong lúc gọi mạng lâu; claim row, commit lease, publish bên ngoài transaction rồi cập nhật kết quả.

**CDC relay:** dùng database change stream hoặc dịch vụ CDC để đọc thay đổi của outbox table. Với relational database, AWS DMS có thể đưa thay đổi tới các đích streaming như Amazon Kinesis Data Streams hoặc Amazon MSK; một consumer tiếp theo chuẩn hóa và publish event tới broker/target phù hợp. CDC giảm nhu cầu polling nhưng vẫn phải xử lý checkpoint, replay, schema evolution và duplicate.

## 7. Outbox với DynamoDB và DynamoDB Streams

Với DynamoDB, có thể dùng TransactWriteItems để ghi item nghiệp vụ và outbox item trong cùng transaction. DynamoDB Streams ghi nhận thay đổi của table theo trình tự thời gian; Lambda event source mapping đọc stream và phát event tới SQS/EventBridge.

Mô hình:

~~~mermaid
flowchart LR
    A[Order API Lambda] --> T[DynamoDB TransactWriteItems]
    T --> O[Order item]
    T --> X[Outbox item]
    X --> S[DynamoDB Streams]
    S --> L[Publisher Lambda]
    L --> Q[SQS or EventBridge]
    Q --> C[Consumer Lambda]
    C --> I[Inbox / processed event store]
~~~

Trong một transaction, ứng dụng có thể:

- Put order item với điều kiện item chưa tồn tại.
- Put outbox item với event ID duy nhất.
- Update idempotency record hoặc aggregate version nếu cần.
- Dùng condition expression để ngăn chuyển trạng thái không hợp lệ.

TransactWriteItems thực hiện atomic các action trong transaction. API hỗ trợ tối đa 100 action và tổng kích thước item trong transaction tối đa 4 MB; các action phải ở cùng account và Region. ClientRequestToken giúp cùng một request transaction có tính idempotent trong 10 phút kể từ khi request đầu hoàn tất. Sau 10 phút, cùng token được xem là request mới; vì vậy token này không thay thế business idempotency record có thời hạn dài hơn.

DynamoDB Streams record có thứ tự trong stream, nhưng Lambda consumer vẫn có thể xử lý lại record khi invocation retry. Hãy dùng event ID, sequence/version và inbox để chống side effect lặp. Với thiết kế single-table, publisher cần lọc đúng loại item hoặc event record, tránh phát mọi thay đổi của table như business event.

## 8. Chọn SQS Standard, SQS FIFO hay EventBridge?

Các dịch vụ truyền event có đặc tính khác nhau. Chọn theo yêu cầu ordering, fan-out, filtering, throughput và tích hợp.

| Dịch vụ | Đặc điểm | Khi phù hợp |
|---|---|---|
| SQS Standard | At-least-once, throughput cao, không bảo đảm thứ tự tuyệt đối | Queue công việc độc lập, consumer có thể deduplicate |
| SQS FIFO | Ordering trong từng MessageGroupId, producer deduplication window 5 phút | Cần thứ tự theo aggregate hoặc tránh duplicate gửi trong cửa sổ dedup |
| EventBridge | Event bus, content-based routing, nhiều target, retry và DLQ cho target | Phân phối event tới nhiều service, lọc theo event pattern |
| DynamoDB Streams | CDC theo thay đổi item, sequence theo shard | Phát event từ thay đổi DynamoDB |
| Amazon SNS | Pub/sub fan-out tới nhiều subscriber | Phát thông báo cùng lúc tới nhiều queue hoặc endpoint |

SQS Standard có thể giao trùng và không đảm bảo thứ tự tuyệt đối. SQS FIFO cho thứ tự trong cùng message group; các group khác nhau có thể được xử lý song song. Producer có thể dùng MessageDeduplicationId hoặc content-based deduplication. Cửa sổ deduplication là 5 phút; gửi lại sau cửa sổ có thể tạo message mới.

Với FIFO, chọn MessageGroupId theo aggregate, ví dụ order ID hoặc account ID, nếu các event của aggregate đó phải giữ thứ tự. Dùng MessageDeduplicationId là event ID ổn định. Không dùng một group ID duy nhất cho toàn bộ hệ thống nếu muốn xử lý song song, vì nó tuần tự hóa tất cả message.

EventBridge hỗ trợ routing theo nội dung event. Với target delivery lỗi tạm thời, EventBridge mặc định retry tối đa 24 giờ và 185 lần với exponential backoff và jitter; có thể cấu hình retry policy và dead-letter queue. Delivery semantics của từng AWS service source có thể là best-effort hoặc durable at-least-once. Không giả định mọi event source đều có cùng cam kết.

## 9. Consumer với SQS và Lambda

Khi Lambda đọc SQS qua event source mapping, Lambda poll queue và gửi một batch message tới function. Nếu function xử lý thành công cả batch, Lambda xóa message. Nếu invocation thất bại, message có thể xuất hiện lại sau visibility timeout.

Thiết kế consumer:

1. Parse và validate schema.
2. Xác định eventId, aggregateId, aggregateVersion.
3. Kiểm tra inbox hoặc processed-message store.
4. Nếu event mới, claim event ID bằng conditional write/unique constraint.
5. Cập nhật business state trong cùng transaction với inbox record.
6. Commit.
7. Chỉ sau đó mới xác nhận message đã xử lý.

Với batch có nhiều message, bật partial batch response (ReportBatchItemFailures) để chỉ trả lại message thất bại. Nếu một message lỗi mà function báo cả batch thất bại, những message đã xử lý thành công có thể bị giao lại. Powertools for AWS Lambda có Batch Processing utility giúp quản lý partial batch response.

Visibility timeout cần đủ dài cho thời gian xử lý batch. AWS khuyến nghị đặt visibility timeout của queue ít nhất sáu lần timeout của Lambda function để có thời gian xử lý các lần retry/throttling. Với xử lý kéo dài, có thể dùng ChangeMessageVisibility để gia hạn theo trạng thái thực tế.

Cấu hình DLQ/redrive policy với maxReceiveCount phù hợp. Message lỗi vĩnh viễn hoặc poison message không nên lặp vô hạn làm nghẽn queue. DLQ cần quy trình triage, sửa nguyên nhân và redrive có kiểm soát; redrive vẫn có thể tạo duplicate nên consumer phải idempotent.

## 10. Ordering và versioning của event

Idempotency xử lý duplicate, nhưng không tự xử lý event đến sai thứ tự.

Ví dụ, order phát hai event:

- Version 1: OrderPlaced.
- Version 2: OrderCancelled.

Nếu consumer nhận OrderCancelled trước rồi nhận OrderPlaced, một phép cập nhật đơn giản có thể đưa trạng thái từ CANCELLED trở lại PLACED.

Giải pháp:

- Gắn aggregateVersion hoặc sequence number vào mỗi event.
- Consumer chỉ áp dụng event có version kế tiếp theo quy tắc nghiệp vụ.
- Nếu version nhỏ hơn hoặc bằng version đã xử lý, coi là duplicate/stale và bỏ qua.
- Nếu version bị nhảy, tạm dừng, retry hoặc yêu cầu replay event còn thiếu.
- Dùng SQS FIFO MessageGroupId theo aggregate khi cần thứ tự vận chuyển.
- Không giả định timestamp đủ để sắp xếp tuyệt đối; clock skew và event creation time có thể khác thứ tự commit.

Một consumer có thể lưu last_applied_version cùng business state. Khi nhận event version v, kiểm tra v = last_applied_version + 1; nếu đúng thì cập nhật state và version trong cùng transaction. Nếu v nhỏ hơn hoặc bằng, event đã cũ; nếu v lớn hơn, cần chờ hoặc khôi phục event bị thiếu.

Ordering thường chỉ cần trong phạm vi một aggregate hoặc entity. Tránh yêu cầu global ordering cho toàn hệ thống vì nó làm giảm throughput và tăng coupling.

## 11. Retry, timeout, backoff và DLQ

Retry giúp phục hồi lỗi tạm thời như network timeout, throttling hoặc service unavailable. Nhưng retry không sửa được lỗi dữ liệu, permission hay logic nghiệp vụ.

Một policy nên có:

- **Timeout:** giới hạn thời gian gọi downstream.
- **Retryable errors:** danh sách lỗi có thể thử lại.
- **Exponential backoff:** tăng dần thời gian chờ.
- **Jitter:** thêm độ ngẫu nhiên để tránh nhiều client retry đồng thời.
- **Maximum attempts/age:** giới hạn số lần hoặc thời gian retry.
- **DLQ:** lưu message không thể xử lý sau các lần thử.
- **Idempotency:** bảo vệ side effect trong mọi lần retry.

Không retry ngay lập tức liên tục khi downstream đang quá tải. Điều đó có thể tạo retry storm. Dùng circuit breaker hoặc rate limit để giảm tải khi dịch vụ phụ thuộc suy giảm.

Với EventBridge target, cấu hình retry policy và DLQ. Với SQS, dùng redrive policy và DLQ. Với Lambda asynchronous invocation, cấu hình retry/destination phù hợp với loại trigger. Với DynamoDB Streams, theo dõi iterator age, retry behavior và cơ chế xử lý record lỗi.

Khi replay DLQ, giữ nguyên event ID và payload gốc nếu đó vẫn là cùng một sự kiện. Không sinh event ID mới chỉ vì muốn retry, vì consumer sẽ coi đó là một event khác và có thể lặp side effect.

## 12. Saga và tính nhất quán qua nhiều service

Outbox đảm bảo event intent được ghi cùng local transaction. Nhưng một workflow có thể cập nhật nhiều database độc lập, ví dụ Order, Inventory, Payment và Shipping. Không nên giữ transaction database mở trong suốt thời gian gọi các service từ xa.

**Saga** chia một business transaction dài thành chuỗi local transaction. Mỗi bước commit tại service sở hữu dữ liệu; khi một bước thất bại, workflow chạy forward recovery hoặc compensating transaction.

Ví dụ đặt hàng:

| Bước | Local transaction | Compensation |
|---|---|---|
| 1. Create order | Tạo order ở trạng thái PENDING | Cancel order |
| 2. Reserve inventory | Giữ hàng | Release inventory |
| 3. Authorize payment | Giữ hạn mức thanh toán | Void authorization |
| 4. Create shipment | Tạo yêu cầu giao hàng | Cancel shipment nếu còn khả năng |
| 5. Confirm order | Chuyển order sang CONFIRMED | Quy trình xử lý nghiệp vụ riêng nếu đã giao hàng |

Compensation không phải lúc nào cũng là rollback vật lý. Nếu payment đã capture hoặc shipment đã giao, hành động bù có thể là refund, return hoặc tạo case xử lý thủ công.

Hai cách tổ chức saga:

- **Choreography:** service phát event và service khác phản ứng. Phù hợp workflow ít bước và coupling thấp, nhưng luồng tổng thể khó quan sát khi có nhiều participant.
- **Orchestration:** một coordinator quản lý thứ tự, timeout, retry và compensation. AWS Step Functions có thể điều phối các bước và nhánh xử lý lỗi.

Mỗi local transaction và compensation cũng phải idempotent. Nếu saga orchestrator retry một bước, service participant không được giữ hàng hoặc trừ tiền hai lần. Lưu saga ID, step ID, attempt, status và correlation ID để điều tra.

## 13. Kết hợp idempotency, outbox và saga trong kiến trúc AWS

Một kiến trúc tham khảo cho đơn hàng:

~~~mermaid
flowchart TD
    C[Client with Idempotency-Key] --> A[API Gateway]
    A --> O[Order Service on Lambda or ECS]
    O --> D[(RDS or Aurora)]
    D --> I[Idempotency record]
    D --> B[Order business row]
    D --> X[Outbox event row]
    X --> R[Outbox relay or CDC]
    R --> Q[SQS FIFO or EventBridge]
    Q --> W[Workflow / Step Functions]
    W --> P[Payment service]
    W --> N[Inventory service]
    W --> S[Shipping service]
    P --> PI[(Payment inbox)]
    N --> NI[(Inventory inbox)]
    S --> SI[(Shipping inbox)]
    W --> DLQ[DLQ and operations queue]
~~~

Vai trò của từng thành phần:

- **API Gateway:** tiếp nhận request, xác thực và áp dụng throttling. Idempotency nghiệp vụ vẫn được xử lý ở ứng dụng/database.
- **Order Service:** kiểm tra key, tạo order và outbox event trong một local transaction.
- **RDS/Aurora:** lưu order, idempotency record và outbox row.
- **Outbox relay/CDC:** phát event đã commit tới broker.
- **SQS FIFO:** giữ thứ tự event theo order ID nếu cần; dedup producer trong 5 phút.
- **EventBridge:** định tuyến event tới nhiều workflow hoặc service theo nội dung.
- **Step Functions:** điều phối saga, timeout, retry và compensation.
- **Consumer inbox:** ghi nhận event ID đã xử lý cùng cập nhật nghiệp vụ.
- **DLQ:** giữ event không thể xử lý để điều tra và replay.

Nếu dùng DynamoDB thay RDS, có thể dùng TransactWriteItems ghi order và outbox item; DynamoDB Streams kích hoạt publisher Lambda. Nếu dùng Lambda, AWS Lambda Powertools Idempotency có thể lưu trạng thái idempotency vào DynamoDB; Java implementation hỗ trợ DynamoDB persistence layer. Cần kiểm tra phiên bản thư viện, cấu hình TTL và quyền IAM trước khi đưa vào production.

## 14. Ví dụ thiết kế: API tạo đơn hàng với idempotency và outbox

Giả sử API POST /orders nhận Idempotency-Key. Một request hợp lệ cần:

1. Chuẩn hóa payload và tính request hash.
2. Mở transaction database.
3. Tạo hoặc claim idempotency record theo unique key.
4. Nếu key đã tồn tại và hash khác, rollback và trả 409 Conflict.
5. Nếu key đã thành công, đọc response/resource ID đã lưu và trả lại.
6. Nếu key mới, tạo order.
7. Tạo OrderPlaced event trong outbox với event ID duy nhất và aggregate version.
8. Lưu response cùng trạng thái idempotency SUCCEEDED.
9. Commit.
10. Trả response cho client.

Pseudocode:

~~~text
handleCreateOrder(request, key):
    requestHash = hash(canonicalize(request))
    scope = (tenantId, "POST:/orders", key)

    begin transaction

    record = claimIdempotencyKey(scope, requestHash)

    if record exists and record.requestHash != requestHash:
        rollback
        return 409 Conflict

    if record.status == SUCCEEDED:
        commit
        return record.savedResponse

    if record is IN_PROGRESS and owned by another active worker:
        rollback
        return 202 Accepted or retryable response

    order = insertOrder(request)
    event = createOrderPlacedEvent(order)

    insertOutbox(event)
    saveIdempotencyResult(scope, order.id, response, SUCCEEDED)

    commit
    return response
~~~

Trong triển khai thật, claim key, order, outbox và response phải nằm trong cùng transaction hoặc một giao thức có lease/fencing được xác định rõ. Nếu record IN_PROGRESS được tạo ở transaction riêng, cần xử lý trường hợp worker crash giữa claim và business transaction.

### 14.1. Khi relay gửi event

Relay gửi OrderPlaced tới SQS FIFO:

- MessageGroupId = orderId.
- MessageDeduplicationId = eventId.
- Payload chứa aggregateVersion.

Sau khi nhận ACK, relay đánh dấu event published. Nếu relay crash trước khi đánh dấu, event có thể được gửi lại; consumer sẽ dùng eventId để deduplicate.

### 14.2. Khi Inventory consumer xử lý

Inventory service mở transaction:

1. Insert (consumer_name, event_id) vào inbox.
2. Nếu key đã tồn tại, bỏ qua event.
3. Nếu mới, kiểm tra aggregateVersion và trạng thái order.
4. Giữ tồn kho bằng conditional update.
5. Commit inbox và inventory cùng nhau.

Nếu inventory không đủ hàng, consumer phát một kết quả nghiệp vụ InventoryRejected qua outbox riêng. Saga coordinator nhận event và chạy compensation như cancel order hoặc void payment authorization nếu payment đã được thực hiện.

## 15. AWS Lambda Powertools Idempotency

AWS Lambda Powertools cung cấp utility idempotency để giảm lượng mã phải tự triển khai. Utility có thể tạo key từ toàn bộ event hoặc một tập trường được chọn, lưu trạng thái và response vào persistence layer, rồi trả lại kết quả trước đó khi cùng request được gọi lại trong thời hạn cấu hình.

Với Java, tài liệu Powertools mô tả DynamoDB là persistence layer được hỗ trợ. Bảng thường dùng partition key id và TTL attribute để dọn record hết hạn. Lambda execution role cần quyền đọc và ghi DynamoDB tương ứng, thường gồm:

- dynamodb:GetItem
- dynamodb:PutItem
- dynamodb:UpdateItem
- dynamodb:DeleteItem

Các điểm cần lưu ý:

- Chọn đúng trường nghiệp vụ làm idempotency key; không mặc định hash toàn payload nếu payload chứa timestamp hoặc trường thay đổi theo retry.
- Đặt expiration dài hơn cửa sổ retry thực tế.
- Xử lý concurrent request và trạng thái IN_PROGRESS.
- Không lưu response quá lớn vào DynamoDB; item size của DynamoDB có giới hạn 400 KB.
- Không dùng Powertools thay cho outbox hoặc inbox; utility bảo vệ handler invocation, còn outbox bảo vệ dual-write và inbox bảo vệ consumer side effect.
- Với external side effect, vẫn cần idempotency key ở provider hoặc quy trình reconciliation.

## 16. Consistency model và invariant nghiệp vụ

Không phải mọi dữ liệu cần strong consistency trên toàn hệ thống. Cần xác định invariant nào bắt buộc đúng ngay lập tức và dữ liệu nào có thể hội tụ theo thời gian.

| Dữ liệu hoặc invariant | Yêu cầu consistency |
|---|---|
| Không tạo hai order cho cùng một idempotency key | Atomic unique constraint/conditional write |
| Không trừ tồn kho vượt số lượng khả dụng | Conditional update hoặc transaction tại Inventory service |
| Payment không bị capture hai lần | Provider idempotency key và payment state machine |
| Email xác nhận có thể gửi trễ | Eventual consistency thường chấp nhận được |
| Search index cập nhật sau khi order commit | Eventual consistency, có lag monitoring |
| Event cùng order phải theo version | Ordering trong aggregate và version check |
| Báo cáo doanh thu cuối ngày | Eventual consistency và reconciliation |

Strong consistency cục bộ trong một database không tự tạo ra strong consistency xuyên nhiều service. Hãy xác định nơi sở hữu từng invariant. Service sở hữu dữ liệu phải thực thi invariant bằng transaction, conditional write hoặc state machine; service khác tương tác qua API/event.

Không để nhiều service cùng ghi trực tiếp vào một database table nếu không có ranh giới sở hữu và quy tắc concurrency rõ ràng. Sự phụ thuộc schema và transaction chung sẽ làm các service khó triển khai độc lập.

## 17. Observability: đo lường outbox, inbox và duplicate

Cần giám sát không chỉ trạng thái queue mà cả độ trễ và tuổi của event.

Các chỉ số hữu ích:

| Nhóm | Metric hoặc số liệu |
|---|---|
| API idempotency | Số request mới, replay, key conflict, in-progress conflict, record expiry |
| Outbox | Pending count, oldest pending age, publish attempts, publish failure, relay lag |
| Broker | Queue depth, age of oldest message, delivery count, DLQ depth |
| Consumer | Duplicate rate, processing latency, failure rate, retry count |
| Ordering | Version gap, stale event count, out-of-order event count |
| Saga | Running duration, failed step, compensation count, stuck workflow |
| Business | Duplicate order/payment prevented, inventory mismatch, reconciliation backlog |

Mỗi request/event nên có:

- correlationId: liên kết các bước trong một business flow.
- causationId: event/request đã kích hoạt event hiện tại.
- eventId: định danh duy nhất của event.
- aggregateId và aggregateVersion.
- idempotencyKey hoặc hash đã được bảo vệ.
- sagaId và step name nếu có orchestration.

Không ghi raw payment credentials, access token, session secret hoặc dữ liệu cá nhân không cần thiết vào log. Có thể log hash hoặc phần đã mask của idempotency key để hỗ trợ tìm kiếm.

Cảnh báo nên tập trung vào dấu hiệu vận hành có ý nghĩa: oldest outbox event vượt ngưỡng, DLQ tăng, event age tăng, saga bị treo, duplicate rate tăng bất thường hoặc reconciliation không hoàn tất.

## 18. Kiểm thử failure modes

Một bài kiểm thử tốt phải mô phỏng lỗi giữa các bước, không chỉ test happy path.

| Tình huống | Kết quả mong đợi |
|---|---|
| Client timeout sau DB commit và retry cùng key | Trả lại order/result cũ, không tạo order thứ hai |
| Cùng key nhưng payload khác | Từ chối bằng conflict |
| Hai request cùng key đến đồng thời | Chỉ một request claim và thực hiện side effect |
| DB transaction rollback | Không có business row và outbox event |
| Relay crash trước publish | Event còn pending và được retry |
| Relay crash sau publish nhưng trước mark published | Có thể gửi duplicate; consumer deduplicate |
| Consumer commit DB rồi crash trước ACK | Message được giao lại; inbox ngăn side effect lặp |
| Consumer lỗi một message trong batch | Partial batch response chỉ retry message lỗi |
| Message đến sai version | Consumer chờ, retry hoặc yêu cầu replay; không ghi đè state mới |
| Payment provider timeout sau khi đã charge | Retry cùng provider idempotency key hoặc query trạng thái trước khi charge lại |
| DLQ được redrive | Giữ event ID gốc và consumer tiếp tục idempotent |
| Saga thất bại ở bước cuối | Chạy compensation theo thứ tự và ghi lại kết quả |

Nên kiểm thử cả tải đồng thời, timeout kéo dài, service throttling, queue visibility timeout, network partition và database failover. Đối với retry, xác minh backoff/jitter để tránh retry storm.

## 19. Bảo mật và vận hành

Idempotency record và outbox có thể chứa thông tin khách hàng, order, payment reference và dữ liệu nghiệp vụ. Hãy bảo vệ chúng như dữ liệu ứng dụng quan trọng.

- Dùng IAM least privilege cho API, relay, Lambda consumer và Step Functions.
- Mã hóa dữ liệu at rest bằng KMS theo yêu cầu.
- Hạn chế ai có thể đọc payload outbox và inbox.
- Không đưa secret hoặc payment data nhạy cảm vào event payload nếu consumer không cần.
- Dùng schema version để thay đổi event có kiểm soát.
- Giới hạn thời gian lưu outbox/inbox theo yêu cầu audit và replay.
- Có runbook xử lý DLQ, stuck outbox, duplicate payment và saga compensation.
- Theo dõi thay đổi IAM, queue policy, event bus policy và database permissions bằng CloudTrail.

Outbox không nên giữ payload không giới hạn. Có thể chỉ lưu dữ liệu tối thiểu và reference tới resource; consumer truy xuất phần còn lại qua API có phân quyền. Tuy nhiên, nếu consumer phụ thuộc vào đọc trạng thái hiện tại thay vì event snapshot, cần hiểu rằng dữ liệu có thể đã thay đổi khi event được xử lý. Hãy chọn rõ event-carried state transfer hay event notification.

## 20. Thực hành: thiết kế luồng đặt hàng có thể retry an toàn

Một cửa hàng trực tuyến sử dụng API Gateway, Order Service trên Lambda, Aurora PostgreSQL, SQS FIFO và Step Functions. Yêu cầu:

- Client retry không tạo order trùng.
- Order và OrderPlaced event không bị lệch nhau.
- Inventory chỉ giữ hàng một lần cho cùng event.
- Payment không bị charge hai lần.
- Event theo cùng order được xử lý đúng thứ tự.
- Nếu payment thất bại, inventory được release và order chuyển sang trạng thái phù hợp.

Hãy triển khai theo thứ tự:

1. Thiết kế idempotency record với unique key theo tenant, operation và client key.
2. Tính request hash và từ chối cùng key nhưng payload khác.
3. Ghi order, idempotency result và outbox event trong một transaction.
4. Chọn polling relay hoặc CDC; lưu event ID và aggregate version.
5. Publish event tới SQS FIFO với group ID theo order ID.
6. Dùng inbox table tại Inventory service và Payment service.
7. Truyền idempotency key tới payment provider.
8. Dùng Step Functions điều phối các bước và compensation.
9. Cấu hình DLQ, retry/backoff và partial batch response.
10. Tạo dashboard cho outbox age, queue age, duplicate rate và saga failures.
11. Mô phỏng crash sau commit, crash sau publish và timeout từ payment provider.
12. Chứng minh bằng dữ liệu rằng mỗi order/payment chỉ có một kết quả nghiệp vụ hợp lệ.

Kết quả cần đạt không phải là mọi function chỉ được invoke một lần. Kết quả cần đạt là dù request, event hoặc function bị retry nhiều lần, hệ thống vẫn hội tụ về một trạng thái nghiệp vụ đúng và có thể điều tra.

## Kết luận

Idempotency giúp request và message có thể được retry mà không lặp side effect. Transactional outbox ghi business state và event intent trong cùng transaction để tránh lỗi dual-write. Inbox giúp consumer deduplicate trong cùng transaction với cập nhật nghiệp vụ. SQS FIFO, EventBridge, DynamoDB Streams và Lambda cung cấp các cơ chế truyền event khác nhau, nhưng không loại bỏ nhu cầu xử lý duplicate ở tầng ứng dụng.

Khi một nghiệp vụ trải qua nhiều service, saga điều phối local transaction và compensation. Thiết kế đáng tin cậy cần event ID ổn định, idempotency key có phạm vi rõ, ordering/versioning, retry có giới hạn, DLQ, observability và reconciliation. Hãy kiểm thử các cửa sổ crash giữa commit, publish, consume và ACK để chứng minh hệ thống có thể phục hồi mà không tạo giao dịch trùng.

## Tài liệu tham khảo

- [Transactional outbox pattern — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
- [Idempotency — Powertools for AWS Lambda Java](https://docs.aws.amazon.com/powertools/java/latest/utilities/idempotency/)
- [Idempotency — Powertools for AWS Lambda Python](https://docs.aws.amazon.com/powertools/python/latest/utilities/idempotency/)
- [DynamoDB TransactWriteItems API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html)
- [How DynamoDB transactions work](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)
- [Exactly-once processing in Amazon SQS FIFO queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html)
- [Outage recovery scenarios in Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/designing-for-outage-recovery-scenarios.html)
- [Using Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Configuring an SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html)
- [Handling errors for an SQS event source in Lambda](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- [Best practices for DynamoDB Streams with Lambda](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.Lambda.BestPracticesWithDynamoDB.html)
- [Delivery level for AWS service events — EventBridge](https://docs.aws.amazon.com/eventbridge/latest/ref/event-delivery-level.html)
- [EventBridge target retry policy](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rule-retry-policy.html)
- [Saga patterns — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-patterns.html)
- [Saga orchestration pattern — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-orchestration.html)

