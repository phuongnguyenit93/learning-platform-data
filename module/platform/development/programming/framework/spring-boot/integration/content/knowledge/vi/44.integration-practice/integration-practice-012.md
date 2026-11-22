# Mô phỏng lỗi từng phần và xác minh quy trình phục hồi dữ liệu

Một hệ thống Spring Boot có thể nhận HTTP request thành công, ghi dữ liệu vào database, phát sự kiện qua broker và cập nhật dữ liệu ở một service khác. Mỗi bước đều có thể thất bại ở một thời điểm khác nhau. Khi một pod chết ngay sau khi commit DB nhưng trước khi gửi message, hoặc broker đã nhận message nhưng producer bị timeout, **chỉ kiểm tra mã HTTP hoặc số message đã nhận sẽ không chứng minh dữ liệu đã được phục hồi đúng**.

Bài thực hành tổng hợp này xây dựng kịch bản **fault injection có kiểm soát**, theo dõi trạng thái ở từng ranh giới DB/HTTP/cache/broker và đối soát kết quả sau khi hệ thống khôi phục. Trọng tâm là mô phỏng lỗi từng phần, xác định cửa sổ mất hoặc trùng dữ liệu, bảo vệ transaction và idempotency, kiểm tra retry/DLQ, rồi đo lường khả năng phục hồi bằng bằng chứng có thể lặp lại.

Ví dụ sử dụng Spring Boot với PostgreSQL, một message broker (Kafka, Pulsar hoặc RabbitMQ), một consumer và một dịch vụ HTTP bên ngoài. Các cơ chế kiểm thử có thể áp dụng cho Spring Integration adapters khi luồng sử dụng channel, gateway hay inbound/outbound adapter. Ví dụ SQL dùng PostgreSQL; API broker, acknowledgment và chính sách retry phải được điều chỉnh theo hệ thống thực tế.

## 1. Xác định hệ thống và kết quả được xem là đúng

Giả sử một nền tảng bán hàng có luồng:

1. Client gửi `POST /orders` kèm `Idempotency-Key` và mã tenant.
2. `Order API` xác thực, ghi `orders` và một bản ghi `outbox` trong **cùng transaction**.
3. `Outbox publisher` đọc record chưa gửi, publish `OrderCreated` lên broker và đánh dấu đã gửi sau khi broker xác nhận.
4. `Order projection consumer` nhận event, dùng `eventId` chống trùng trong `inbox`, cập nhật một database đọc (read model), rồi ack **sau commit**.
5. Một thành phần tích hợp có thể gọi HTTP sang đối tác giao hàng; cache sản phẩm giúp đọc nhanh nhưng không phải nguồn sự thật.

~~~mermaid
flowchart LR
    H[HTTP client] --> A[Order API]
    A --> T[(Order DB: orders + outbox)]
    T --> P[Outbox publisher]
    P --> B[(Message broker)]
    B --> C[Projection consumer]
    C --> R[(Read DB: inbox + projection)]
    C -. qua workflow/outbox .-> X[HTTP partner]
    A -. đọc dữ liệu .-> K[(Cache)]
~~~

### 1.1. Định nghĩa các bất biến nghiệp vụ

Trước khi làm hỏng hệ thống, phải biết thế nào là **phục hồi thành công**. Các bất biến kiểm thử:

| Mã | Bất biến phải giữ | Cách xác minh |
| --- | --- | --- |
| I1 | Một `tenantId + clientOperationId` chỉ tạo **một** đơn hàng logic | Unique key tại DB nguồn, đếm `orders` |
| I2 | Mỗi đơn hàng đã commit đều có một ý định phát event bền vững | Đếm `outbox` cùng transaction, tra theo order ID |
| I3 | Một event có thể gửi/nhận nhiều lần nhưng chỉ gây **một** tác động trên projection theo handler và tenant | Unique `inbox(tenant_id, handler_name, event_id)`, kiểm tra số effect đã commit |
| I4 | Projection không bị event cũ ghi đè dữ liệu mới | So sánh `aggregateVersion` tại DB đích |
| I5 | Khi dependency hồi phục, backlog có thể về 0 hoặc đúng ngưỡng SLA | Đo outbox pending age, broker lag, retry queue |
| I6 | Thông điệp độc hại không làm mất message hợp lệ | DLQ/quarantine, replay có kiểm soát |
| I7 | Không tạo side effect HTTP hai lần cho cùng business operation | Idempotency key và log kết quả ở đối tác |
| I8 | Cache hỏng không làm phát sinh trạng thái giao dịch sai | So sánh kết quả với DB có thẩm quyền |

“Chỉ một lần” ở I1/I3/I7 phải được hiểu **theo định danh và ranh giới đã nêu**. Không khẳng định toàn bộ hệ thống đạt exactly-once; thông thường broker dùng at-least-once và handler phải chịu được duplicate.

### 1.2. Phân loại mức độ phục hồi

- **Consistency:** dữ liệu tuân thủ các ràng buộc và phiên bản; không tạo đơn, trừ tiền hoặc phát hóa đơn trùng.
- **Durability:** thay đổi đã commit không mất khi pod/broker gặp lỗi; outbox giữ được ý định gửi.
- **Availability:** API còn có thể tiếp nhận yêu cầu hay phải trả `503` khi DB không sẵn sàng.
- **Convergence:** projection và hệ thống ngoài bắt kịp trạng thái nguồn trong khoảng thời gian cho phép.
- **Recovery point objective (RPO):** lượng dữ liệu được phép mất theo yêu cầu hệ thống; với đơn hàng đã được API xác nhận commit, thông thường RPO mục tiêu là **0** đối với bản ghi nguồn.
- **Recovery time objective (RTO):** khoảng thời gian chấp nhận để chức năng trở về trạng thái phục vụ sau lỗi. Phải đo trên môi trường và tải được xác định, không chỉ ghi con số dự kiến.

## 2. Thiết kế điểm chèn lỗi thay vì tắt ngẫu nhiên dịch vụ

Để truy ra nguyên nhân, đặt điểm lỗi theo ranh giới mà ứng dụng có thể quan sát:

~~~text
F1  Trước khi commit orders + outbox
F2  Sau DB commit, trước khi publisher đọc outbox
F3  Sau broker chấp nhận event, trước khi producer nhận ack/mark SENT
F4  Sau consumer commit inbox + projection, trước broker ack
F5  Trong transaction consumer (trước commit)
F6  Trong kết nối broker / lúc reconnect hoặc rebalance
F7  Khi gọi HTTP đối tác; remote đã xử lý nhưng response bị mất
F8  Cache GET, PUT hoặc invalidate thất bại
F9  Message sai schema hoặc vi phạm hợp đồng nghiệp vụ
F10 Hai replica/publisher cạnh tranh cùng công việc khi một worker chết
~~~

Có thể gắn hook thử nghiệm ở ranh giới transaction/outbox trong **test profile**, dùng proxy mạng để cắt connection và dùng container stop/restart để giả lập crash. Hook không được tùy tiện xuất hiện trong request production.

Một lỗi được mô phỏng chỉ có giá trị nếu kiểm soát được **lúc xảy ra**. Ví dụ “tắt broker 30 giây rồi thấy hệ thống chạy lại” không kiểm chứng được tình huống broker đã lưu message nhưng acknowledgment chưa tới producer. Ca F3 cần ép lỗi ngay khoảng publish acknowledgment (hoặc dùng stub/fault hook tái hiện trạng thái không chắc chắn).

## 3. Chuẩn bị môi trường thực hành có thể lặp lại

Nên dựng một **môi trường integration test cô lập**:

| Thành phần | Vai trò | Cách mô phỏng |
| --- | --- | --- |
| PostgreSQL nguồn | Lưu `orders` và `outbox` | Testcontainers PostgreSQL; stop/restart, khóa hoặc rollback |
| Broker | Chuyển `OrderCreated` | Testcontainers Kafka/RabbitMQ/Pulsar phù hợp dự án; network fault |
| PostgreSQL projection | Lưu `inbox` và read model | Có thể dùng cùng instance DB nhưng **schema/transaction khác** để kiểm thử ranh giới |
| HTTP đối tác | Nhận yêu cầu tạo vận đơn | WireMock/MockWebServer, giả lập `429`/`500`/timeout và response loss |
| Proxy mạng | Cắt kết nối, tăng latency, giới hạn băng thông | Toxiproxy hoặc network emulator |
| Ứng dụng | Order API, publisher, consumer, scheduler | Chạy ít nhất 2 replica cho ca cạnh tranh |
| Quan sát | Log, metric, trace, DB queries | Correlation ID và event ID ổn định |

Testcontainers đơn thuần không tự đảm bảo toàn bộ cấu hình giống production. Cần ghi rõ phiên bản broker/driver, transaction isolation, cấu hình retry, ack mode, retention và số replica. Khi kiểm thử tải, cố định kích thước payload, số partition, tốc độ request và thời gian inject.

### 3.1. Dữ liệu thử và key ổn định

Dùng một bộ input riêng cho từng lần chạy thử:

~~~json
{
  "tenantId": "shop-a",
  "clientOperationId": "create-order-test-001",
  "orderId": "00000000-0000-4000-8000-000000000042",
  "eventId": "10000000-0000-4000-8000-000000000042",
  "aggregateVersion": 1,
  "amount": 125000
}
~~~

`clientOperationId` được giữ nguyên khi client retry HTTP. `eventId` được tạo một lần khi ghi outbox và **không thay bằng UUID mới ở mỗi lần publish retry**. Nếu test được chạy lại trên cùng DB mà không reset fixture hoặc đổi namespace thử nghiệm, receipt của lần trước có thể làm test thành công giả. Chỉ reset dữ liệu **trong môi trường test cô lập**; không tự xóa dữ liệu production.

### 3.2. Dụng cụ kiểm soát thời gian và concurrency

Dùng barrier/`CountDownLatch` hoặc hook điểm kiểm thử để tạo race tại đúng ranh giới; dùng đồng hồ có thể điều khiển nếu logic dựa vào lease/TTL. Tránh phụ thuộc vào `Thread.sleep(...)` dài và các mốc thời gian ngẫu nhiên, vì test có thể pass trên laptop nhưng fail trên CI.

Đối với test phục hồi bất đồng bộ, dùng `Awaitility` hoặc polling có deadline để chờ **điều kiện nghiệp vụ**, chẳng hạn “projection có đúng một row version 1”, thay vì “đợi 5 giây rồi hy vọng đủ”.

## 4. Dữ liệu và transaction làm nền cho phục hồi

Một schema rút gọn minh họa:

~~~sql
CREATE TABLE orders (
    order_id            uuid         PRIMARY KEY,
    tenant_id           varchar(80)  NOT NULL,
    client_operation_id varchar(100) NOT NULL,
    amount              bigint       NOT NULL,
    state               varchar(40)  NOT NULL,
    created_at          timestamptz  NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, client_operation_id)
);

CREATE TABLE order_outbox (
    event_id        uuid         PRIMARY KEY,
    tenant_id       varchar(80)  NOT NULL,
    aggregate_id    uuid         NOT NULL,
    aggregate_ver   bigint       NOT NULL,
    event_type      varchar(80)  NOT NULL,
    payload         jsonb        NOT NULL,
    status          varchar(20)  NOT NULL DEFAULT 'NEW',
    attempts        integer      NOT NULL DEFAULT 0,
    next_attempt_at timestamptz  NOT NULL DEFAULT now(),
    created_at      timestamptz  NOT NULL DEFAULT now(),
    sent_at         timestamptz
);

CREATE TABLE consumer_inbox (
    tenant_id    varchar(80)  NOT NULL,
    handler_name varchar(100) NOT NULL,
    event_id     uuid         NOT NULL,
    processed_at timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, handler_name, event_id)
);

CREATE TABLE order_read_model (
    tenant_id         varchar(80)  NOT NULL,
    order_id          uuid         NOT NULL,
    state             varchar(40)  NOT NULL,
    source_version    bigint       NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);
~~~

Các bảng nguồn và đích có thể ở **hai database khác nhau**. Chúng được đặt trong một khối DDL để minh họa tên cột; không suy diễn có transaction xuyên hai database. `consumer_inbox` được lưu **cùng transaction với read model**, còn `orders` và `order_outbox` được lưu **cùng transaction DB nguồn**.

Các unique constraints có vai trò riêng:

- `(tenant_id, client_operation_id)`: chống tạo nhiều đơn do client retry cùng lệnh.
- `order_outbox.event_id`: giữ một định danh message logic qua lần publish retry.
- `(tenant_id, handler_name, event_id)`: một handler chỉ thực hiện DB effect của event một lần trong đúng phạm vi tenant.
- `(tenant_id, order_id)` và `source_version`: bảo vệ dữ liệu projection, chống event cũ ghi đè.

Bảng outbox thực tế cần thêm fields phục vụ claim/lease hoặc cơ chế khóa hàng, lỗi cuối, số lần retry và cách phân biệt record poison. Chỉ có cột `status` là **chưa đủ** để nhiều publisher đồng thời claim an toàn.

### 4.1. Transaction tại Order API

Trong một transaction tại DB nguồn:

~~~text
BEGIN
  INSERT orders(tenant_id, client_operation_id, order_id, ...)
  INSERT order_outbox(event_id, aggregate_id, aggregate_ver, payload, ...)
COMMIT
HTTP response 201/200 phù hợp với hợp đồng idempotency
~~~

Nếu insert `orders` bị conflict do cùng client operation ID, API phải đọc lại kết quả cũ và đối chiếu **request payload/amount/tenant** để tránh trả kết quả của một request khác vô tình tái sử dụng key. Không tự tạo đơn mới bằng key khác vì một client timeout. Không publish trực tiếp giữa hai lệnh DB rồi nghĩ rằng broker có cùng transaction với PostgreSQL.

### 4.2. Transaction tại consumer

Ở database projection, xử lý event theo thứ tự:

~~~text
BEGIN
  INSERT consumer_inbox(handler_name, event_id)
    ON CONFLICT DO NOTHING
  nếu đã có receipt:
      không ghi business effect
  nếu claim mới:
      INSERT/UPDATE order_read_model có điều kiện aggregateVersion
COMMIT
ACK broker
~~~

Nếu consumer crash trước commit, receipt và read model cùng rollback; broker có thể redeliver. Nếu crash sau commit nhưng trước ack, duplicate có receipt và được bỏ qua an toàn. Nếu message có cùng event ID nhưng payload khác, cần kiểm tra hợp đồng hoặc hash trước khi coi là duplicate; không âm thầm bỏ qua dữ liệu khác nghĩa.

### 4.3. Một lệnh SQL kiểm chứng phiên bản

Với PostgreSQL, projection giữ bản mới nhất có thể dùng:

~~~sql
INSERT INTO order_read_model
    (tenant_id, order_id, state, source_version)
VALUES (:tenant_id, :order_id, :state, :version)
ON CONFLICT (tenant_id, order_id)
DO UPDATE SET
    state = EXCLUDED.state,
    source_version = EXCLUDED.source_version
WHERE order_read_model.source_version < EXCLUDED.source_version;
~~~

Đây là mẫu **latest-state projection**, chấp nhận bỏ qua event cũ. Nếu nghiệp vụ cần xử lý đầy đủ từng transition hoặc cộng/trừ biến động, phải kiểm tra `expectedVersion = currentVersion + 1` và lưu event đến sớm để xử lý lại theo thứ tự. Không dùng `max(version)` để che mất một event bắt buộc.

## 5. Baseline: chạy luồng bình thường trước khi gây lỗi

Không inject ngay. Đầu tiên chạy một yêu cầu sạch để có đường chuẩn:

1. Gửi `POST /orders` một lần với `Idempotency-Key: create-order-test-001`.
2. Xác minh `orders` có một row; `order_outbox` có một row cùng aggregate/event key.
3. Chờ publisher gửi event, broker nhận; record outbox chuyển sang `SENT` **sau acknowledgment**.
4. Chờ consumer commit `consumer_inbox` và `order_read_model` rồi ack.
5. Nếu có HTTP đối tác, xác minh đúng một operation tại hệ thống giả lập, sử dụng một idempotency key đã ghi bền vững.
6. Ghi baseline: p95/p99 publish latency, thời gian hội tụ projection, số retry, outbox pending age, broker lag và memory.

Một baseline không có unique constraints, không có idempotency và không biết bao nhiêu event được phát **chưa đủ điều kiện** để dùng làm chuẩn test recovery. Cần phát hiện và sửa những sai sót này trước khi chèn lỗi.

## 6. Ma trận lỗi từng phần và kỳ vọng phục hồi

| Lỗi | Điểm inject | Trạng thái mong muốn ngay sau lỗi | Tiêu chí phục hồi |
| --- | --- | --- | --- |
| F1 | Order API trước DB commit | Không có order và outbox đã commit | Retry cùng key tạo đúng một order + outbox |
| F2 | Sau commit, trước publish | Order + outbox `NEW` vẫn còn | Publisher restart gửi event, projection hội tụ |
| F3 | Broker đã nhận, producer mất ack | Outbox có thể chưa `SENT` | Retry có thể gửi trùng nhưng consumer chỉ ghi một effect |
| F4 | Consumer commit, ack thất lạc | Inbox + projection đã commit | Redelivery bị skip, ack lại; không ghi trùng |
| F5 | Consumer DB unavailable giữa transaction | Transaction rollback, message chưa ack | Sau phục hồi DB, retry và commit một lần |
| F6 | Broker unavailable/rebalance | Outbox còn pending, backlog tồn tại | Reconnect, backlog giảm có giới hạn, không mất event |
| F7 | HTTP đối tác xử lý nhưng response bị mất | Trạng thái outbound còn không chắc chắn | Retry cùng operation ID, không tạo effect thứ hai |
| F8 | Cache GET/evict thất bại | Cache suy giảm hoặc stale có giới hạn | Source of truth đúng, cache được làm mới/invalidate |
| F9 | Payload sai schema hoặc poison message | Message bị retry/quarantine theo chính sách | DLQ có thông tin điều tra, message tốt vẫn tiến triển |
| F10 | Hai publisher/consumer tranh chấp; một pod chết | Có thể nhận/lặp gửi vật lý | Unique DB, claim/lease và idempotency giữ đúng số effect |

**Không phải mọi ca đều kỳ vọng 0 message trùng.** Với F3 và F4, một số lần publish hoặc receive bị lặp là hành vi có thể chấp nhận trong at-least-once; điều cần chứng minh là **không trùng kết quả nghiệp vụ** và hệ thống cuối cùng hội tụ.

## 7. Ca F1: lỗi trước commit DB nguồn

**Mục tiêu:** chứng minh không có trạng thái “đơn hàng đã commit nhưng outbox chưa được ghi” khi hai bảng phải thay đổi nguyên tử.

**Dàn dựng:** tạo order qua một service method có `@Transactional`. Trong test profile, chèn exception **sau khi insert `orders` và `order_outbox`, nhưng trước commit**. Có thể dùng hook test trên service transaction, thay vì chỉ kill process ngẫu nhiên.

~~~java
// Pseudocode của test hook, chỉ bật trong test profile.
// Phương thức nghiệp vụ thực vẫn dùng một transaction DB.
@Transactional
public UUID createOrder(CreateOrderCommand command) {
    UUID orderId = saveOrderWithUniqueOperationKey(command);
    saveOutboxEvent(orderId, command);
    faultHook.failIfEnabled("BEFORE_ORDER_COMMIT");
    return orderId;
}
~~~

Các method `saveOrderWithUniqueOperationKey`, `saveOutboxEvent` và `faultHook` là abstraction minh họa, không phải API có sẵn của Spring Boot. Lỗi phải được ném trước transaction commit và được transaction manager đánh dấu rollback; nếu test hook bắt exception rồi tiếp tục, ca test không còn phản ánh tình huống cần kiểm tra.

**Kiểm chứng:**

- HTTP trả lỗi có kiểm soát; database **không còn row** `orders` và `outbox` thuộc lệnh vừa thất bại.
- Gửi lại cùng `Idempotency-Key` sau khi tắt hook, hai row được tạo đúng một lần.
- Nếu hai HTTP request cùng key đến đồng thời, unique constraint chọn một order; client còn lại nhận kết quả idempotent theo hợp đồng hoặc lỗi trùng có thể xử lý.
- Không có event `OrderCreated` được phát từ transaction thất bại.

Nếu test phát hiện chỉ có `orders` nhưng thiếu `outbox`, cần kiểm tra xem hai insert có dùng cùng datasource/transaction manager không, hoặc có `REQUIRES_NEW`/gọi HTTP trong transaction làm thay đổi hành vi hay không.

## 8. Ca F2: DB đã commit nhưng publisher chưa kịp gửi

**Mục tiêu:** chứng minh một lỗi độc lập của pod/worker sau DB commit không làm mất event cần phát.

**Dàn dựng:**

1. Gọi API tạo đơn, xác minh `orders` và `order_outbox` đã commit.
2. Tạm dừng outbox publisher hoặc kill riêng worker **trước khi nó lấy record**; không dừng DB.
3. Ghi nhận `outbox.status=NEW`, `sent_at IS NULL` và projection chưa có event.
4. Khôi phục publisher, quan sát nó lấy lại record, gửi tới broker và đánh dấu `SENT` sau ack.
5. Đợi consumer commit inbox và projection.

~~~mermaid
sequenceDiagram
    participant A as Order API
    participant D as Order DB
    participant P as Publisher
    participant B as Broker
    participant C as Consumer
    A->>D: COMMIT order + outbox(E42)
    Note over P: Pod publisher chết trước khi đọc E42
    D-->>A: Transaction đã commit
    Note over P: Restart
    P->>D: Poll outbox NEW
    P->>B: Publish E42
    B-->>P: ACK
    P->>D: Mark outbox SENT
    B-->>C: Deliver E42
    C->>C: Inbox + projection COMMIT
~~~

**Tiêu chí pass:** có đúng một order logic, một outbox record cho event ID, projection hội tụ và không có row bị kẹt vĩnh viễn ở `NEW`. Số lần gửi vật lý có thể lớn hơn một nếu có lỗi khác xen vào; không kiểm tra “đúng một network send” như một bất biến.

**Dấu hiệu lỗi thiết kế:** publish được gọi ngay trong HTTP controller và crash sau commit làm mất ý định gửi; outbox lưu trong database khác không cùng transaction; scheduler chỉ quét một lần ở startup; query pending bỏ sót record vì trạng thái/lease kẹt.

## 9. Ca F3: broker đã nhận nhưng producer không biết

**Mục tiêu:** kiểm chứng tình trạng **kết quả publish không chắc chắn**. Có thể broker đã lưu message dù producer ném timeout do ack thất lạc.

Có hai mức test cần phân biệt:

- **Deterministic recovery test:** broker gửi thành công và trả ack, nhưng hook làm publisher chết **sau ack, trước khi update outbox SENT**. Lần restart chắc chắn gửi lại cùng event ID. Test này chứng minh downstream chịu được duplicate.
- **Network fault test:** đặt Toxiproxy/network emulator giữa publisher và broker rồi cắt hoặc gây latency ở thời điểm publish; quan sát timeout/reconnect. Chỉ từ một timeout **không thể chứng minh** broker đã ghi message. Cần log/metric hoặc truy vấn được hỗ trợ để xác nhận trạng thái phía broker khi cần.

~~~text
Outbox E42 = NEW/SENDING
  -> producer gửi E42
  -> broker có thể đã ghi E42
  -> ack không đến publisher hoặc pod chết
  -> outbox chưa được đánh dấu SENT
  -> recovery gửi lại E42
  -> consumer nhận E42 lần 1 và/hoặc lần 2
  -> unique inbox(eventId, handler) chỉ cho một DB effect
~~~

**Tiêu chí pass:** cuối cùng outbox được giải phóng, inbox nhận diện E42, projection có đúng một effect, event ID của bản gửi lại **không đổi**. Nếu publisher mỗi lần retry tạo UUID mới, inbox theo event ID không thể chống trùng này; cần sửa ngay tại nguồn tạo outbox.

**Điều cần tránh:** coi mọi lỗi `sendAsync()` là “broker chắc chắn chưa lưu”; đánh dấu `SENT` trước ack; xử lý duplicate bằng cách drop cả message theo tên pod hoặc offset; lưu trạng thái “đã gửi” chỉ trong RAM.

## 10. Ca F4 và F5: consumer mất ack hoặc DB lỗi giữa transaction

### 10.1. F4 — commit projection xong nhưng mất ack

1. Consumer nhận event E42.
2. Transaction DB đích insert `consumer_inbox(E42)` và update `order_read_model`; commit.
3. Hook cắt kết nối hoặc kill consumer **trước ack**.
4. Broker giao lại E42 cho consumer khác.
5. Worker mới thử insert inbox với cùng key; phát hiện duplicate đã commit, không cập nhật projection thêm lần nữa; ack sau khi xác minh.

~~~mermaid
sequenceDiagram
    participant M as Broker
    participant A as Consumer A
    participant D as Projection DB
    participant B as Consumer B
    M-->>A: Event E42
    A->>D: BEGIN; INSERT inbox; UPDATE read model
    A->>D: COMMIT
    Note over A: Chết trước ACK
    M-->>B: Redeliver E42
    B->>D: INSERT inbox E42 → conflict
    B-->>M: ACK duplicate đã được ghi nhận
~~~

**Tiêu chí pass:** có một receipt `(tenant,handler,E42)` và một projection đúng phiên bản; broker không redeliver vô hạn; số lần callback có thể ≥ 2 nhưng business side effect vẫn bằng một.

### 10.2. F5 — mất DB đích trước commit

Giả lập database đích không sẵn sàng hoặc ném exception **trước commit**. Transaction phải rollback cả inbox và business update. Consumer không được ack như thành công; error handler/backoff/Retry topic hoặc DLQ phải tuân thủ chính sách.

**Tiêu chí pass:** khi DB còn lỗi, không xuất hiện marker “đã xử lý” giả; sau khi khôi phục DB, redelivery commit được inbox và projection. Kiểm tra cả tình huống lỗi kết nối ở **thời điểm commit**: client có thể không biết commit đã thành công hay chưa. Lần retry phải dựa vào unique inbox và trạng thái DB thực tế, không suy diễn từ exception.

### 10.3. Quy tắc transaction và ack cho các framework

| Consumer framework | Ranh giới cần kiểm tra | Sai lầm thường gặp |
| --- | --- | --- |
| Spring Kafka | Container ack/offset commit, DB transaction, error handler | Ack offset trước khi DB commit; retry và DLT cấu hình không thống nhất |
| Spring for Apache Pulsar | Ack/nack và redelivery, listener transaction DB | Coi broker ack là một phần transaction JDBC |
| Spring AMQP/RabbitMQ | Manual/auto ack, requeue/DLX, consumer concurrency | Ack sớm; requeue poison message vô hạn |
| Spring Integration | Inbound adapter, error channel, advice/retry, transaction boundary | Tưởng error channel tự rollback cả DB và broker |
| Spring Batch xử lý message theo lô | Job checkpoint và reader/ack mode theo triển khai | Restart job bằng identity mới gây xử lý trùng |

Không ghép một generic `@Transactional` lên handler rồi kết luận có distributed transaction. Kiểm tra transaction manager nào tham gia bước nào; nếu DB và broker không cùng một transaction có bảo đảm thích hợp, hãy thiết kế hành vi retry/idempotency để chịu được lỗi ở giữa.

## 11. Ca F6: broker chậm, ngắt mạng và phục hồi có giới hạn

Khi broker không sẵn sàng, nguồn dữ liệu đã commit vẫn ở outbox. Mục tiêu của recovery là **không mất event và không làm sập DB/HTTP khi broker hồi phục**.

Kế hoạch:

1. Tạo N order có `eventId` riêng, trong đó N đủ để quan sát backlog nhưng vẫn phù hợp tài nguyên test.
2. Chặn kết nối broker bằng proxy hoặc dừng container. Xác minh HTTP API hoặc publisher xử lý theo SLA riêng: không block vô hạn, không drop outbox.
3. Quan sát outbox tăng, publisher timeout/retry nhưng có `backoff + jitter` và bounded concurrency.
4. Khôi phục broker, đo tốc độ publisher lấy backlog, connection pool, pending send queue và tỉ lệ lỗi.
5. Đợi backlog hạ dưới ngưỡng, đối chiếu mỗi order có event tương ứng tại projection.

**Bộ giới hạn nên có:** connect/operation timeout, max in-flight, bulkhead, số retry hoặc deadline, circuit breaker (khi phù hợp), outbox claim/lease, worker concurrency. Đừng cho một pod bắn vô hạn `sendAsync()` hoặc một HTTP request giữ transaction DB mở chờ broker.

Khi có nhiều publisher:

- Claim một record bằng khóa hàng/điều kiện nguyên tử trong DB; `SELECT ... FOR UPDATE SKIP LOCKED` có thể hỗ trợ phân việc ngắn trong PostgreSQL.
- Nếu gửi cần thời gian lâu, dùng trạng thái `SENDING` kèm `ownerToken`/`leaseUntil` được ghi bền vững, thay vì giữ một DB transaction mở suốt network send.
- Khi lease hết, publisher khác có thể gửi lại cùng event. **Không dùng lease như cơ chế exactly-once**; downstream vẫn phải idempotent.
- Đối với báo cáo test, đếm `eventId` duy nhất trong nguồn và số business effect đã commit tại đích, không so số lần `sendAsync()` thuần.

**Tiêu chí pass:** broker hồi phục, outbox không còn record pending quá deadline, projection hội tụ, số side effect không tăng theo số publish attempts và tài nguyên (heap, thread, DB pool, queue) không vượt ngân sách thử nghiệm.

## 12. Ca F7: đối tác HTTP đã xử lý nhưng phản hồi thất lạc

Một dịch vụ tích hợp có thể gọi API vận đơn, thanh toán hoặc hóa đơn. Đây là nơi dễ hiểu nhầm “timeout là thao tác thất bại”.

Ví dụ workflow phát hành vận đơn:

~~~http
POST /shipments HTTP/1.1
Idempotency-Key: shop-a:shipment:create:order-42
Content-Type: application/json

{"orderId":"00000000-0000-4000-8000-000000000042"}
~~~

Trên WireMock hoặc fake partner được thiết kế riêng cho test, mô phỏng:

1. Đích **ghi nhận và commit** operation với key `shop-a:shipment:create:order-42`.
2. Đích cố tình đóng connection hoặc trả response quá trễ để caller thấy timeout.
3. Worker lưu trạng thái **UNKNOWN/RETRYABLE** thay vì khẳng định request chưa thực thi.
4. Sau backoff, worker tra cứu trạng thái nếu API hỗ trợ hoặc gửi lại **cùng idempotency key**.
5. Đích trả lại cùng kết quả và không tạo thêm shipment.

**Tiêu chí pass:** fake partner lưu một shipment logic, dù application gọi hai lần. Mọi lần retry có cùng operation ID và payload tương thích. Nếu đích không hỗ trợ idempotency hoặc tra cứu, phải dùng reconciliation/compensation; một distributed lock bên ứng dụng không thể đảm bảo exactly-once cho API đối tác.

Không đặt HTTP call cần retry bền vững trong transaction inbox rồi coi commit DB là bằng chứng HTTP call thành công. Lưu một workflow/outbox record, điều phối worker sau commit và ghi kết quả remote theo trạng thái có thể phục hồi.

## 13. Ca F8: lỗi cache và invalidation sau cập nhật

Cache là bản sao dữ liệu dùng để giảm độ trễ, không phải nguồn sự thật để xác nhận “đã tạo đơn” hoặc “đã thanh toán”.

Tách ít nhất ba lỗi:

| Lỗi | Điều cần kiểm chứng | Phương án nghiệp vụ |
| --- | --- | --- |
| Cache GET timeout | HTTP có thể truy vấn DB có thẩm quyền trong ngân sách cho phép? | Fail-open có bounded fallback nếu dữ liệu cho phép |
| Cache PUT thất bại | Dữ liệu mới đã commit có trả đúng không? | Trả kết quả từ nguồn; tăng cảnh báo/hit-miss |
| Cache eviction thất bại sau DB update | Entry stale có bị dùng ngoài giới hạn freshness? | TTL/version key, invalidation retry hoặc đọc nguồn khi quyết định nhạy cảm |

Khi API cập nhật đơn hàng commit DB rồi Redis bị ngắt trước `evict`, **không thể tự suy ra transaction DB đã rollback** từ exception cache. Cần quy trình khôi phục invalidation: event bền vững, outbox, TTL có giới hạn, key theo version hoặc cơ chế đọc lại nguồn. Với quyền truy cập, tồn kho, hạn mức hoặc trạng thái thanh toán, không trả stale chỉ vì cache còn giữ một entry.

**Tiêu chí pass:** DB nguồn giữ đúng trạng thái; khi cache hồi phục, entry được invalidation/refresh; cache miss hàng loạt không làm DB bị quá tải do không có giới hạn fallback.

## 14. Ca F9: schema lỗi, poison message và DLQ

Gửi một event có JSON sai schema hoặc vi phạm business contract, xen giữa các event hợp lệ.

~~~json
{
  "eventId": "20000000-0000-4000-8000-000000000042",
  "eventType": "OrderCreated",
  "schemaVersion": 999,
  "payload": {"orderId": null}
}
~~~

**Mục tiêu:** lỗi vĩnh viễn không tạo vòng retry bất tận, không làm mất event tốt và không bị giả mạo thành event đã xử lý thành công.

- Validate envelope trước business handler; phân loại deserialize error, schema mismatch, invalid business data và lỗi nguồn tạm thời.
- Retry lỗi tạm thời theo ngân sách; lỗi không thể sửa bằng retry thì đưa DLQ/quarantine với lý do được kiểm soát và correlation ID.
- Không log toàn bộ payload nhạy cảm. DLQ cần quyền truy cập, retention và quy trình re-drive riêng.
- Khi sửa schema hoặc dữ liệu, re-drive **cùng business key/event ID** nếu vẫn là cùng event; nếu là một revision mới, cần quy định rõ.
- Không tự động ack poison message như success nếu chưa có quyết định nghiệp vụ về discard/quarantine. Hợp đồng ack khi DLQ publish thất bại cũng phải được kiểm thử.

**Tiêu chí pass:** event hợp lệ phía sau vẫn xử lý được theo cam kết ordering, event lỗi xuất hiện tại quarantine/DLQ một cách quan sát được, không phát sinh trùng business effect khi re-drive. Với workflow bắt buộc xử lý version tuần tự, event version sau không được vượt qua một version bị lỗi mà không có quy trình đối soát.

## 15. Ca F10: nhiều replica cùng claim hoặc xử lý lại

Chạy hai instance publisher hoặc consumer cùng đọc một hàng đợi/DB, rồi kill một instance ở thời điểm nguy hiểm.

### 15.1. Hai publisher cùng outbox record

Nếu hai publisher làm `SELECT status=NEW` trước khi update, cả hai có thể gửi E42. Cần claim nguyên tử bằng row lock hoặc conditional update để giảm cạnh tranh. Dù có claim/lease, **vẫn có thể gửi trùng** khi lease hết, worker pause lâu hoặc producer mất ack. Do đó kiểm chứng cả số lần publish và idempotency của downstream.

### 15.2. Hai consumer cùng event

Dùng cùng `eventId` và chạy hai transaction độc lập. Worker A insert `consumer_inbox(tenant,handler,E42)` nhưng giữ transaction mở; worker B cũng insert cùng unique key. Database chọn một đường commit thành công; nếu A rollback, B có thể claim. Kết quả cuối phải là **một inbox receipt và một business effect** dù hai callback cùng chạy.

### 15.3. Lease hết nhưng worker cũ còn sống

Đặt lease ngắn để mô phỏng A bị pause, B takeover, sau đó A tiếp tục. `ownerToken` giúp ngăn A ghi đè trạng thái claim, nhưng **không tự ngăn** A gọi HTTP. Cần fencing token đơn điệu được hệ thống đích kiểm tra, hoặc idempotency key do đích hỗ trợ. Nếu không có hai cơ chế đó, test phải thể hiện giới hạn bảo đảm và có bước reconciliation, không gắn nhãn ca này là “exactly-once”.

### 15.4. Khôi phục sau restart hoặc deploy

Lặp các ca trên khi:

- Publisher pod được rolling restart lúc đang publish.
- Consumer mất assignment/rebalance giữa xử lý và ack.
- Outbox worker bị kill, record còn `SENDING` cho tới khi lease hết.
- Cấu hình retry/backoff thay đổi giữa hai lần deploy.

Kiểm chứng worker mới tiếp tục từ trạng thái **bền vững**, không phụ thuộc một queue, map hoặc cache chỉ tồn tại trong RAM của pod cũ.

## 16. Tự động hóa bài thực hành bằng kiểm thử tích hợp

Một bộ test có thể tổ chức theo lớp để giảm thời gian phản hồi và giữ được bằng chứng kỹ thuật:

| Cấp kiểm thử | Nội dung | Công cụ tham khảo |
| --- | --- | --- |
| Unit | Phân loại exception, tính backoff, dedup key, chính sách version | JUnit 5, Mockito |
| Integration DB | Unique constraint, transaction rollback, outbox/inbox, concurrency | `@SpringBootTest`, Testcontainers PostgreSQL |
| Integration broker | Publish/consume, redelivery, ack mode, retry/DLQ | Testcontainers broker phù hợp |
| Fault injection | Cắt network, timeout, restart pod/worker | Toxiproxy, WireMock, test hook |
| End-to-end phục hồi | Đối soát DB nguồn và DB đích sau fault | Awaitility, SQL probes, metrics/log/traces |
| Staging chaos test | Scale-out, rolling restart, hạ tầng gần production | Tool điều phối container/Kubernetes, observability |

### 16.1. Tách điểm quan sát khỏi điểm chèn lỗi

Một lỗi chỉ nên được bật **tại một ranh giới xác định**. Ví dụ test hook có thể hỗ trợ:

~~~text
BEFORE_ORDER_COMMIT
AFTER_ORDER_COMMIT_BEFORE_PUBLISH
AFTER_BROKER_ACK_BEFORE_MARK_SENT
AFTER_CONSUMER_DB_COMMIT_BEFORE_ACK
BEFORE_CONSUMER_DB_COMMIT
BEFORE_PARTNER_RESPONSE
AFTER_LEASE_EXPIRED_BEFORE_WORKER_RESUMES
~~~

Các tên này là **giao diện fault hook do bài thực hành tự thiết kế**, không phải API sẵn có của Spring Boot. Hook ở `AFTER_ORDER_COMMIT_BEFORE_PUBLISH` thuộc worker/publisher hoặc lớp điều phối sau commit, **không** được mô phỏng bằng cách ném exception *bên trong* transaction rồi nhầm là đã commit.

Các điểm fault có thể được hiện thực bằng latch, spy, test bean `@Primary`, fault proxy hoặc kênh điều khiển của test harness. Khi test tác động tới network, cần quan sát được kết nối thật và chứng minh lỗi đã kích hoạt; không đơn thuần giả định `container.stop()` xảy ra đúng microsecond mong muốn.

### 16.2. Skeleton kiểm thử một cửa sổ mất ack

Đoạn Java sau minh họa **ý tưởng orchestration**. `IntegrationScenario` là facade của test harness cần tự xây dựng, không phải class có sẵn trong thư viện Spring.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class OutboxRecoveryIT {
    private IntegrationScenario scenario; // @Autowired hoặc test fixture.

    @Test
    void publisherCrashAfterBrokerAckMustNotDuplicateProjection() {
        var input = scenario.uniqueOrderCommand();

        // Mô phỏng broker đã nhận nhưng outbox chưa được mark SENT.
        scenario.failOnceAt("AFTER_BROKER_ACK_BEFORE_MARK_SENT");
        var result = scenario.createOrder(input);

        // Đợi publisher recover và projection bắt kịp.
        scenario.restartFailedPublisher();
        await().atMost(Duration.ofSeconds(60)).untilAsserted(() -> {
            assertThat(scenario.outboxSent(result.eventId())).isTrue();
            assertThat(scenario.inboxReceiptCount(result.eventId()))
                    .isEqualTo(1);
            assertThat(scenario.projectedOrderCount(result.orderId()))
                    .isEqualTo(1);
            assertThat(scenario.projectedVersion(result.orderId()))
                    .isEqualTo(1);
        });

        assertThat(scenario.orderCount(input.operationId())).isEqualTo(1);
    }
}
~~~

`Duration.ofSeconds(60)` ở đây là **deadline minh họa của test**, không phải RTO đã được bảo đảm. Cần chọn ngưỡng theo SLA và môi trường CI. Test phải chứng minh `failOnceAt` thật sự xảy ra (ví dụ bộ đếm fault hit bằng một), tránh tình trạng test pass vì hệ thống chưa đi qua cửa sổ lỗi.

### 16.3. Race test với hai transaction

Để kiểm chứng chống trùng giữa replica, dùng **hai connection và hai transaction độc lập**, đồng bộ khởi động bằng `CountDownLatch`/barrier. Cho worker A insert `consumer_inbox(E42)` rồi giữ transaction chưa commit; worker B cố insert cùng key.

Chạy hai nhánh:

- **A commit:** B không được commit business effect lần hai; marker và read model đúng một.
- **A rollback:** B có thể được quyền xử lý; sau cùng vẫn đúng một business effect.

Kiểm tra cùng một database thực như PostgreSQL; H2 in-memory không nhất thiết tái hiện lock, isolation và lỗi unique giống production. Đếm **row đã commit** và sự kiện outbound từ outbox, ngoài số lần callback handler được gọi.

### 16.4. Phân biệt test infrastructure với test nghiệp vụ

Một test xanh vì proxy đã cắt connection chưa chứng minh dữ liệu phục hồi. Mỗi test nên có hai nhóm assertion:

1. **Fault assertions:** lỗi đã kích hoạt ở điểm định trước; request hoặc worker đã quan sát timeout/crash/rebalance đúng tình huống.
2. **Data assertions:** bất biến I1–I8 được giữ, cuối cùng không còn dữ liệu pending quá SLA và phiên bản projection đúng nguồn.

Không coi “không có exception cuối test” là một chỉ số phục hồi đầy đủ.

## 17. Đối soát dữ liệu bằng SQL và business key

Công việc chính sau fault là **so sánh nguồn sự thật với các bản sao hoặc tác động bên ngoài**, không chỉ đếm message.

### 17.1. Tìm order đã commit nhưng thiếu outbox event

Trên **database nguồn**:

~~~sql
SELECT o.tenant_id, o.order_id, o.client_operation_id
FROM orders o
LEFT JOIN order_outbox b
    ON b.tenant_id = o.tenant_id
   AND b.aggregate_id = o.order_id
   AND b.event_type = 'OrderCreated'
WHERE b.event_id IS NULL;
~~~

Nếu luồng thiết kế “mỗi order tạo đúng một OrderCreated trong cùng transaction”, kết quả của query phải rỗng. Chỉ dùng query khi bảng outbox còn giữ record của kỳ cần kiểm tra; nếu outbox có chính sách purge, phải tra archive/audit thay thế trước khi kết luận thiếu.

Để phát hiện **outbox trùng event logic** dù `event_id` khác nhau:

~~~sql
SELECT tenant_id, aggregate_id, aggregate_ver, event_type,
       COUNT(*) AS n
FROM order_outbox
GROUP BY tenant_id, aggregate_id, aggregate_ver, event_type
HAVING COUNT(*) > 1;
~~~

Query này có ý nghĩa nếu hợp đồng là **một event type trên mỗi aggregate version**. Với nghiệp vụ có chủ đích phát nhiều event cùng loại trên một version, cần bổ sung operation ID hoặc sequence trong điều kiện đối soát.

### 17.2. Tìm outbox pending hoặc retry quá hạn

~~~sql
SELECT status,
       COUNT(*) AS event_count,
       MIN(created_at) AS oldest_created_at,
       MAX(attempts) AS max_attempts
FROM order_outbox
GROUP BY status
ORDER BY status;
~~~

Với outbox có `next_attempt_at`, kiểm tra record đến hạn chưa xử lý:

~~~sql
SELECT event_id, aggregate_id, attempts, next_attempt_at
FROM order_outbox
WHERE status IN ('NEW', 'RETRYABLE')
  AND next_attempt_at <= now()
ORDER BY next_attempt_at, created_at
LIMIT 100;
~~~

Schema minh họa mục 4 chỉ dùng `NEW` và `SENT`; `RETRYABLE` là một trạng thái **tùy chọn của state machine** khi triển khai lỗi chi tiết. Nếu dùng trạng thái khác, phải sửa query cho đúng. Một record `SENDING` không có khả năng thu hồi khi worker chết là dấu hiệu thiếu lease/reaper, không nên tự set hàng loạt thành `SENT` bằng SQL.

### 17.3. Kiểm tra receipt tại DB đích

Trên **database projection**:

~~~sql
SELECT tenant_id, handler_name, event_id, COUNT(*) AS n
FROM consumer_inbox
GROUP BY tenant_id, handler_name, event_id
HAVING COUNT(*) > 1;
~~~

Với primary key của `consumer_inbox`, query này phải luôn rỗng; nó kiểm tra tính toàn vẹn của receipt, nhưng **không chứng minh** business effect bên ngoài không bị lặp. Cần thêm kiểm tra dữ liệu nghiệp vụ và remote system, đặc biệt khi handler gọi HTTP.

Kiểm tra phiên bản và trạng thái của một order:

~~~sql
SELECT tenant_id, order_id, state, source_version
FROM order_read_model
WHERE tenant_id = 'shop-a'
  AND order_id = '00000000-0000-4000-8000-000000000042';
~~~

### 17.4. Đối soát giữa hai database

Nếu nguồn và projection ở **hai database tách biệt**, đừng viết `JOIN` SQL như thể có transaction chung hoặc cùng datasource. Viết reconciliation worker/job:

1. Đọc danh sách `order_id` và version mục tiêu từ DB nguồn theo một watermark/snapshot rõ ràng.
2. Đọc dữ liệu projection theo cùng tenant/order ID.
3. So sánh phiên bản, state và các trường hợp đồng có ý nghĩa nghiệp vụ.
4. Phân nhóm `MISSING`, `STALE`, `CONFLICT` và `OK`.
5. Đối với `MISSING/STALE` sau khi đã hết cửa sổ xử lý bình thường, lên lịch phát lại từ outbox/nguồn với **event ID hoặc business operation ID ổn định**.
6. Không tự động ghi đè `CONFLICT` hoặc chạy lại tác động thanh toán; đẩy qua quy trình điều tra.

Một `Spring Batch` job có thể dùng cho reconciliation định kỳ khi dữ liệu nhiều: reader có checkpoint, identifying parameters theo khoảng thời gian/tenant, writer lưu kết quả đối soát, lỗi có retry giới hạn. Nếu job restart sau lỗi, cần giữ identity của lần đối soát và chống trùng action repair. Nếu dùng Spring Integration, có thể định tuyến mismatch vào error channel hoặc integration flow phục hồi bền vững; không biến error channel thành nơi retry vô hạn trong RAM.

**Tiêu chí cuối cùng:** với một business key cụ thể, chứng minh được nguồn đã commit, event được giữ/gửi, consumer đã xử lý hoặc đã quarantine có lý do, và projection/đích khớp với chính sách dữ liệu.

## 18. Đo RPO, RTO và khoảng hội tụ sau lỗi

Cần gắn mốc đo một cách nhất quán:

~~~text
T0 = fault bắt đầu
T1 = dependency hoặc worker có thể phục vụ lại
T2 = backlog bắt đầu giảm ổn định
T3 = bất biến dữ liệu được xác minh và backlog trong SLA

Thời gian khôi phục chức năng ≈ T1 - T0
Thời gian hội tụ sau phục hồi ≈ T3 - T1
Tổng thời gian đến trạng thái dữ liệu đúng ≈ T3 - T0
~~~

Đây là các mốc phân tích; **RTO chính thức** của dịch vụ có thể được định nghĩa theo chức năng quan trọng khác với `T3`, vì vậy phải thống nhất với SLO/SLA. Đừng báo “RTO 5 giây” chỉ vì broker đã accept connection ở T1 trong khi projection vẫn trễ hàng phút.

Các chỉ số cần thu:

| Tín hiệu | Cách dùng |
| --- | --- |
| `outbox_pending_total`, oldest pending age | Biết ý định phát chưa tới broker và độ tuổi backlog |
| Publish success/error/timeout, queue depth | Phân biệt broker chậm với publisher bị nghẽn |
| Broker lag/backlog, redelivery, DLQ | Biết message chưa tới consumer hoặc đang lặp |
| Consumer DB transaction latency, unique conflicts | Biết độ trễ xử lý và dedupe hoạt động |
| Projection version gap, reconciliation mismatch | Xác định đúng/sai về dữ liệu |
| HTTP downstream idempotency hit/timeout | Kiểm chứng external effects |
| Retry attempts, circuit/bulkhead, connection pool | Tránh recovery gây quá tải dây chuyền |
| Correlation ID, event ID, order ID trong log/trace | Truy vết từ HTTP tới DB và broker có kiểm soát |

Metric tags nên có cardinality giới hạn như service, component, outcome, fault scenario, broker topic (khi số lượng topic được kiểm soát). Không đưa raw `eventId`, `orderId`, token hoặc payload nhạy cảm vào metric tags; event ID có thể xuất hiện ở log/trace với chính sách truy cập và retention phù hợp.

### 18.1. Mẫu báo cáo kết quả một ca thực hành

| Trường | Ví dụ cần điền từ phép đo thực |
| --- | --- |
| Scenario | `F4: consumer commit rồi mất ack` |
| Version/config | Spring Boot, DB, broker, ack mode, isolation, số replica |
| Input | `tenant, operationId, orderId, eventId, aggregateVersion` |
| Fault activated | Thời điểm inject, log/hook hit/trace chứng minh |
| Trạng thái ngay sau fault | DB nguồn, outbox, inbox, projection, broker lag |
| Recovery action | Restart consumer, reconnect, retry hoặc re-drive |
| Trạng thái sau recovery | Counts, version, idempotency result, pending age |
| RPO/RTO/convergence | Giá trị đo và tiêu chuẩn pass/fail |
| Finding | Vi phạm bất biến nào, nguyên nhân và thay đổi cần làm |

**Không tự điền con số pass:** kết quả phải lấy từ test execution và số liệu môi trường. Một lesson có thiết kế ca kiểm thử đầy đủ chưa đồng nghĩa các ca đã được chạy.

## 19. Runbook phục hồi dữ liệu sau sự cố thật

Khi xảy ra lỗi production, không nên phản ứng bằng cách xóa metadata, đổi event ID hoặc replay toàn bộ ngay lập tức. Một quy trình kiểm soát:

1. **Khoanh vùng ảnh hưởng:** xác định service, tenant, khoảng thời gian, topic/subscription, order/event IDs; thu thập alert và trace.
2. **Ổn định nguyên nhân:** phục hồi DB/broker/network/credential, bảo đảm connection pool và retry không tạo bão tải; nếu cần tạm dừng publisher hoặc consumer có kiểm soát.
3. **Chụp bằng chứng:** lưu truy vấn số row nguồn/outbox/inbox/projection, watermark, backlog, DLQ và lỗi cuối. Không thay đổi data trước khi hiểu trạng thái.
4. **Phân loại theo trạng thái thực:** order chưa commit, outbox pending, publish không rõ kết quả, inbox đã commit nhưng chưa ack, projection stale, HTTP đích không rõ kết quả.
5. **Phục hồi theo thứ tự an toàn:** cho publisher đọc outbox bền vững; consumer idempotent xử lý redelivery; replay DLQ chỉ sau sửa schema/config; nếu cần tái tạo projection, dùng source snapshot/aggregate version.
6. **Đối soát nguồn và đích:** chạy reconciliation theo tenant/time window, xác minh I1–I8, kiểm tra các hệ thống HTTP ngoài qua operation ID.
7. **Khôi phục lưu lượng:** tăng concurrency có giới hạn, theo dõi DB pool, broker lag, retry, DLQ và cache invalidation.
8. **Đóng sự cố:** ghi mốc lỗi, thời gian hội tụ, số event bị retry, số duplicate đã chặn và các mismatch còn tồn tại.

**Các thao tác không nên tự động hóa thiếu điều kiện:** ép hàng loạt `outbox.status='SENT'` khi không có ack; xóa `consumer_inbox` để bắt consumer chạy lại; tạo event ID mới cho cùng business operation; ack poison message không lưu quarantine; tăng concurrency vô hạn cho đến khi backlog về 0. Những thao tác này có thể che giấu hoặc nhân dữ liệu sai.

### 19.1. Khi nào cần can thiệp thủ công?

- Cùng idempotency key nhưng payload khác: phải xác định yêu cầu nào có hiệu lực.
- Hai hệ thống đã commit trạng thái mâu thuẫn và không có quy tắc giải quyết tự động.
- Remote payment/invoice API không hỗ trợ tra cứu hoặc idempotency; cần reconciliation có chứng cứ.
- DLQ chứa message sai schema/version không thể chuyển đổi tự động.
- Event cũ bị replay sau thời hạn retention dedupe, có nguy cơ tạo lại side effect.
- Cần reprocess thay đổi nghiệp vụ, không chỉ retry một fault tạm thời.

Những trường hợp này cần bản ghi quyết định và người chịu trách nhiệm nghiệp vụ; việc “worker chạy xong” không có nghĩa hệ thống đã đúng.

## 20. Những sai lầm thường khiến bài thực hành cho kết quả giả

- **Chỉ kill ngẫu nhiên container:** không biết crash xảy ra trước hay sau commit/ack; kết quả thiếu khả năng chứng minh.
- **So số message gửi/nhận rồi kết luận đúng một lần:** broker at-least-once có thể lặp; hãy đếm business effect đã commit.
- **Dùng khóa Redis thay cho transaction/unique constraint:** lease hết hoặc worker chết có thể tạo race và duplicate.
- **Đánh dấu outbox SENT trước broker ack:** tạo cửa sổ mất event khi publish lỗi.
- **Ack trước DB commit:** tạo cửa sổ mất việc khi consumer crash.
- **HTTP timeout được coi chắc chắn không thành công:** bỏ qua kết quả không chắc chắn tại hệ thống đích.
- **Retry tự tạo event ID hoặc idempotency key mới:** làm dedupe không nhận ra cùng business operation.
- **Sửa metadata bằng SQL để ép chạy lại:** phá lịch sử và cơ chế recovery; cần runbook theo state machine.
- **Dùng H2 thay PostgreSQL rồi coi race test tương đương:** hành vi khóa/upsert/isolation có thể khác.
- **Chỉ kiểm tra cuối test, bỏ qua fault activation:** test có thể pass dù điểm chèn lỗi chưa từng chạy.
- **Cache được coi là nguồn sự thật:** entry stale có thể khiến API trả trạng thái sai sau DB update.
- **Không đo backlog và dữ liệu sau hồi phục:** broker đã connect nhưng dữ liệu đích còn thiếu.

## 21. Checklist hoàn thành bài thực hành

- [ ] Đã xác định nguồn sự thật, các bước HTTP/DB/broker/cache và ranh giới transaction.
- [ ] Có các bất biến dữ liệu cụ thể, bao gồm ID nghiệp vụ, event ID, version và remote side effect.
- [ ] Test profile có thể inject lỗi trước/sau commit, publish, ack và HTTP response.
- [ ] Baseline không fault chứng minh dữ liệu nguồn/outbox/inbox/projection đúng.
- [ ] F1–F10 có ít nhất một test hoặc kịch bản lặp lại được, ghi rõ cách chứng minh fault đã kích hoạt.
- [ ] Transactional inbox/outbox và unique constraints đã được kiểm chứng trên DB tương thích production.
- [ ] Consumer ack sau commit, có retry/DLQ với giới hạn; publisher có bounded queue/lease/recovery.
- [ ] Remote HTTP dùng idempotency key bền vững hoặc quy trình reconciliation/compensation.
- [ ] Cache failure không làm thay đổi nguồn dữ liệu có thẩm quyền, invalidation có giới hạn stale.
- [ ] Có SQL probes và phương pháp so sánh dữ liệu xuyên các database bằng business key/version.
- [ ] Báo cáo ghi fault point, trạng thái ngay sau lỗi, hành động phục hồi, số liệu sau phục hồi và RPO/RTO đo được.
- [ ] Có runbook cho các trạng thái không thể tự phục hồi; không replay mù quáng hoặc xóa receipt tùy tiện.

**Nguyên tắc cốt lõi:** mô phỏng lỗi từng phần chỉ có giá trị khi kiểm tra được **đúng điểm đã lỗi**, **dữ liệu còn lại ngay sau lỗi** và **kết quả bền vững sau phục hồi**. Trong Spring Boot, transaction và unique constraint giữ nguyên tử ở từng database; outbox/inbox, ack đúng thời điểm, idempotency và reconciliation nối các ranh giới HTTP, cache và broker. Hệ thống được xem là phục hồi khi các bất biến nghiệp vụ đã được xác minh, không chỉ khi service trở lại trạng thái `UP`.

### Tài liệu tham khảo

- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundary, rollback, propagation và transaction manager.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): `@SpringBootTest`, test slices và integration testing.
- [Spring Integration — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html): test flow, channel và integration endpoints.
- [Spring for Apache Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): phạm vi broker transaction và giới hạn với hệ thống ngoài.
- [Testcontainers for Java — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): PostgreSQL test container.
- [Testcontainers for Java — Toxiproxy](https://java.testcontainers.org/modules/toxiproxy/): fault injection ở tầng mạng.
- [WireMock Documentation](https://wiremock.org/docs/): HTTP stubbing, fault simulation, request verification.
- [PostgreSQL — INSERT and ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): upsert và unique constraints.

Các ví dụ dùng API/DSL minh họa để giải thích bài thực hành; `faultHook` và `IntegrationScenario` cần được hiện thực trong test harness của ứng dụng. Cần đối chiếu phiên bản Spring Boot, broker, thư viện kiểm thử và hợp đồng dữ liệu trước khi triển khai. Việc viết bài hoàn tất STEP 4; kiểm chứng thực nghiệm và vòng QA học thuật sẽ được thực hiện trong các bước riêng.



