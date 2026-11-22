# Mô hình đọc riêng và bản chiếu dữ liệu từ sự kiện

## 1. Bài toán: một màn hình cần dữ liệu của nhiều dịch vụ

Trong một hệ thống bán hàng sử dụng Microservices, khách mở màn hình **Chi tiết đơn hàng**. Màn hình cần hiển thị:

- Mã đơn, ngày đặt, danh sách dòng hàng và giá đã chốt.
- Tên sản phẩm và ảnh đại diện.
- Trạng thái thanh toán và hoàn tiền.
- Số lượng đã giữ, tình trạng xử lý tại kho.
- Mã vận đơn, đơn vị giao hàng, tiến trình giao nhận.
- Tình trạng thông báo xác nhận tới khách hàng.

Những dữ liệu này có thể thuộc nhiều Bounded Context: Ordering, Catalog, Payments, Inventory, Fulfillment và Notifications. Mỗi context có quyền sở hữu dữ liệu, schema và chu kỳ triển khai riêng. Nếu màn hình gọi lần lượt sáu service cho từng lần truy vấn, thời gian phản hồi và khả năng sẵn sàng có thể phụ thuộc quá nhiều vào các lời gọi đồng bộ.

Một cách giải quyết là xây **mô hình đọc riêng** (read model) hoặc **bản chiếu dữ liệu** (projection): cấu trúc dữ liệu được tổ chức theo nhu cầu đọc của một màn hình, truy vấn hoặc báo cáo cụ thể. Read model có thể được cập nhật từ **các sự kiện** mà các context nguồn công bố.

Ý tưởng chính:

> **Write model** giữ tính đúng đắn và bất biến của nghiệp vụ trong context sở hữu; **read model** lưu biểu diễn phục vụ tra cứu, có thể chấp nhận một độ trễ có kiểm soát so với nguồn.

Bài học này thuộc phần **Truy vấn liên dịch vụ**. Mục tiêu không phải bắt mọi hệ thống phải triển khai Event Sourcing hoặc CQRS phức tạp, mà là hiểu khi nào nên dùng dữ liệu đọc tách biệt để giảm fan-out, giảm phụ thuộc đồng bộ và cung cấp API truy vấn ổn định.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt domain/write model, read model, projection, materialized view, cache và event log.
2. Giải thích vì sao đọc dữ liệu từ nhiều Microservices bằng synchronous aggregation có thể gặp vấn đề.
3. Thiết kế projection từ các domain events được công bố có hợp đồng rõ.
4. Hiểu CQRS là tách mô hình/trách nhiệm đọc–ghi, không mặc định tương đương Event Sourcing.
5. Thiết kế xử lý event idempotent, out-of-order, duplicate, retry và replay.
6. Xác định phạm vi nhất quán mạnh và **eventual consistency** giữa các context.
7. Lập kế hoạch bootstrap, backfill, rebuild, chuyển phiên bản projection không dừng dịch vụ.
8. Viết ví dụ SQL/Java về cập nhật projection và API đọc.
9. Quan sát độ trễ projection, xử lý lỗi và bảo vệ quyền truy cập dữ liệu tổng hợp.
10. Phân tích đánh đổi giữa query trực tiếp, API composition, cache, CQRS projection và kho tìm kiếm.

## 2. Những khái niệm dễ bị dùng lẫn

### 2.1. Write model

**Write model** (mô hình ghi) là phần mô hình nghiệp vụ xử lý command, thực thi invariant và thay đổi trạng thái thuộc quyền sở hữu của context.

Ví dụ Ordering sở hữu:

- Order được tạo bởi khách có quyền hợp lệ.
- Giá dòng hàng được chốt ở thời điểm đặt.
- Một đơn chỉ được chuyển trạng thái theo quy tắc cho phép.
- Hủy đơn có thể bị giới hạn khi đã giao hàng.
- Việc chuyển trạng thái cần kiểm soát concurrent updates.

Ordering có thể lưu Order aggregate vào database giao dịch. Payments lại sở hữu Payment Attempt và kết quả giao dịch; Inventory sở hữu Stock Reservation. Không nên lấy read model của màn hình chi tiết đơn làm nguồn quyết định có thu tiền hoặc giảm tồn hay không.

### 2.2. Read model

**Read model** là dữ liệu được tối ưu theo một use case đọc: chi tiết đơn, danh sách đơn của một khách, bảng điều hành giao vận, dashboard hoặc tìm kiếm.

Ví dụ một bản ghi đọc:

~~~json
{
  "orderId": "ORD-1001",
  "customerId": "CUS-17",
  "orderStatus": "FULFILLING",
  "paymentStatus": "SUCCEEDED",
  "shipmentStatus": "IN_TRANSIT",
  "items": [
    {"sku": "BOOK-01", "name": "Sách A", "quantity": 2}
  ],
  "totalAmountMinor": 500000,
  "currency": "VND",
  "lastProjectedAt": "2026-11-11T10:03:00Z"
}
~~~

Một số field được lấy từ Ordering, một số từ Payments hoặc Shipping. Read model có thể lưu ở PostgreSQL, Elasticsearch/OpenSearch, một database document, key–value store hoặc một kho phân tích tùy truy vấn.

Read model được phép **trùng một phần dữ liệu** nguồn vì mục đích truy vấn, nhưng cần phân biệt rõ:

- Bản ghi nào là **authoritative source of truth**?
- Bản đọc này đã cập nhật đến sự kiện nào?
- Chậm hơn nguồn bao lâu là chấp nhận được?
- Khi mất/bị lệch dữ liệu thì sửa từ đâu?
- Ai được đọc từng thuộc tính tổng hợp?

### 2.3. Projection

**Projection** là quá trình áp các thay đổi, thường là events, để tạo hoặc cập nhật một read model. Ví dụ:

~~~text
OrderPlaced          -> tạo bản ghi chi tiết đơn
PaymentSucceeded     -> cập nhật paymentStatus
ShipmentCreated      -> thêm vận đơn
ShipmentDelivered    -> cập nhật shipmentStatus
OrderCancelled       -> cập nhật trạng thái tổng hợp
~~~

Từ projection cũng được dùng cho một biểu diễn kết quả của việc chiếu dữ liệu. Trong bài này, ta phân biệt **projection handler** (chương trình cập nhật) và **projection store/read model** (dữ liệu đầu ra).

### 2.4. Materialized view

**Materialized view** là kết quả truy vấn được lưu sẵn thay vì tính lại mọi lần. Một projection từ events có thể được xem là một dạng materialized view ở mức ứng dụng. Nhưng materialized view trong database có thể được refresh bằng truy vấn SQL, không cần message broker. Đừng đồng nhất hai cơ chế.

### 2.5. Cache

**Cache** lưu tạm kết quả hoặc dữ liệu để tăng tốc đọc; có thể áp TTL/eviction. Read model cũng có thể được truy vấn rất nhanh, nhưng thường có **lifecycle và trách nhiệm xây dựng rõ**: nhận event, checkpoint, theo dõi đồng bộ và rebuild. Một cache bị xóa thường được điền lại khi đọc; một projection có thể được dựng lại từ luồng lịch sử hoặc snapshot/backfill.

Không phải mọi read model đều có durability mạnh và không phải mọi cache đều dễ mất; phân biệt dựa vào **vai trò kiến trúc**, không chỉ công nghệ lưu.

### 2.6. Event Sourcing

Trong **Event Sourcing**, chuỗi domain events là nguồn sự thật được lưu theo thiết kế, và trạng thái write model có thể dựng từ chuỗi đó. **Không cần Event Sourcing** để tạo projection: hệ thống thông thường lưu Order trong PostgreSQL và phát OrderPlaced/OrderStatusChanged qua Transactional Outbox vẫn có thể xây read model bằng events.

### 2.7. CQRS

**Command Query Responsibility Segregation (CQRS)** phân tách mô hình/luồng xử lý lệnh ghi với mô hình/luồng xử lý truy vấn đọc. CQRS có nhiều mức độ:

- Tách handler command/query trong cùng ứng dụng, vẫn chung database.
- Tách schema bảng đọc và schema domain trong cùng database.
- Tách database đọc riêng và cập nhật bằng events hoặc CDC.
- Tách hẳn các dịch vụ write/read với khả năng mở rộng và vận hành độc lập.

Không cần tự động thêm Kafka, Elasticsearch, nhiều database và Event Sourcing chỉ vì sử dụng CQRS.

## 3. Vì sao không luôn truy vấn trực tiếp nhiều Microservices?

Có ba phương án điển hình cho màn hình Chi tiết đơn.

### Phương án A: API Composition đồng bộ

~~~mermaid
flowchart LR
    U[Client] --> B[BFF / Query API]
    B --> O[Ordering]
    B --> P[Payments]
    B --> S[Shipping]
    B --> C[Catalog]
    B --> I[Inventory]
~~~

BFF gọi nhiều service, hợp nhất response rồi trả client. Cách này dễ bắt đầu, không cần thêm pipeline projection và có thể cung cấp thông tin tương đối mới.

Nhưng nó có thể tạo:

- **Fan-out:** một request phải gọi nhiều dependency.
- **Latency:** nếu gọi tuần tự, thời gian cộng dồn; nếu song song, phải xử lý partial failures.
- **Availability:** một service chậm/lỗi có thể làm cả trang chậm hoặc không hiển thị.
- **Over-fetching/N+1:** màn hình danh sách 100 đơn có thể tạo hàng trăm RPC.
- **Contract coupling:** BFF phải biết nhiều API nội bộ, thay đổi của các context có thể lan tới truy vấn.
- **Peak load:** lượng đọc trên dashboard gây tải lớn lên database nghiệp vụ.

API Composition vẫn thích hợp khi số dependency ít, dữ liệu cần mới, khối lượng đọc thấp và độ phức tạp bổ sung của projection chưa đáng.

### Phương án B: query trực tiếp database của các service

~~~text
Read API -> JOIN order_db + payment_db + shipping_db
~~~

Thoạt nhìn cách này giảm số HTTP request, nhưng thường phá ranh giới sở hữu dữ liệu:

- Consumer phụ thuộc bảng và schema nội bộ của context khác.
- Một team có thể đổi database không thông báo API consumer.
- Quyền đọc database dễ bị mở quá rộng.
- Transaction và consistency giữa nhiều database không tự được bảo đảm.
- Truy vấn phân tán có thể rất đắt, khó tối ưu và không theo hợp đồng nghiệp vụ.

Một data warehouse hoặc pipeline phân tích được thiết kế chính thức có thể đọc bản sao dữ liệu với governance riêng. Điều cần tránh là **dịch vụ nghiệp vụ tùy ý JOIN trực tiếp những bảng private mà đội khác sở hữu** để đáp ứng API runtime.

### Phương án C: read model riêng cập nhật từ events

~~~mermaid
flowchart TB
    O[Ordering] --> E[(Event Broker)]
    P[Payments] --> E
    S[Shipping] --> E
    C[Catalog] --> E
    E --> W[Order Read Projector]
    W --> R[(Order Read Store)]
    U[Client] --> A[Order Query API]
    A --> R
~~~

Đường đọc của client chỉ cần query read store đã chuẩn bị sẵn. Dịch vụ nguồn có thể độc lập hơn với tải truy vấn. Đổi lại, hệ thống phải xử lý **độ trễ projection, event delivery, schema evolution, recovery và security**.

### So sánh lựa chọn

| Tiêu chí | API Composition | Read Model từ events | Query trực tiếp DB private |
| --- | --- | --- | --- |
| Thời gian xây ban đầu | Thường thấp hơn | Thường cao hơn | Có vẻ nhanh nhưng coupling lớn |
| Dữ liệu mới nhất | Có thể gần hiện tại của từng nguồn | Có độ trễ theo pipeline | Phụ thuộc transaction/snapshot và thiết kế |
| Fan-out mỗi request | Có | Thường không | Không qua API nhưng có coupling dữ liệu |
| Phụ thuộc service nguồn lúc đọc | Cao | Thấp hơn | Phụ thuộc schema/database nguồn |
| Tải lên DB nghiệp vụ | Có thể tăng | Có thể tách riêng | Có thể rất cao |
| Xử lý nguồn lỗi | Partial response/fallback | Trả snapshot cũ với freshness policy | Query fail/phân mảnh |
| Độ phức tạp vận hành | Hợp nhất API/dependency | Event pipeline, replay, lag, DLQ | Schema coupling và quyền dữ liệu |
| Bảo đảm nhất quán đa context | Không tự bảo đảm | Eventual consistency | Không tự bảo đảm |
| Khả năng tìm kiếm/tổng hợp | Tùy API | Có thể tối ưu theo use case | Dễ phát sinh query phức tạp |

**Chọn theo SLO và use case**, không phải vì “Microservices phải có CQRS”.

## 4. Thiết kế read model theo câu hỏi người dùng

Bắt đầu từ truy vấn thực tế, không bắt đầu từ database hoặc tên broker topic.

Ví dụ API cần phục vụ:

1. GET /orders/ORD-1001: chi tiết một đơn.
2. GET /customers/CUS-17/orders?page=...: danh sách đơn theo khách.
3. GET /shipments/late: các shipment quá hạn.
4. GET /operations/dashboard: tổng hợp trạng thái.
5. GET /orders/search?keyword=...: tìm kiếm theo SKU hoặc mã vận đơn.

Mỗi truy vấn có kiểu sắp xếp, bộ lọc, mức dữ liệu cần mới và quyền truy cập khác nhau. Có thể dùng **nhiều projection** từ cùng event stream:

~~~text
OrderDetailProjection  -> by orderId
CustomerOrdersView     -> by customerId + createdAt
ShipmentTrackingView   -> by shipmentId
OperationsDashboard    -> aggregate counters
OrderSearchIndex       -> full-text search
~~~

Không cần dồn mọi mục đích đọc vào một bảng khổng lồ. Projection phục vụ danh sách đơn thường cần index theo customerId và createdAt; projection tìm kiếm văn bản có thể cần search engine; dashboard có thể cần bảng tổng hợp.

### Ví dụ schema read model

~~~sql
CREATE TABLE order_read_model (
    order_id              VARCHAR(64) PRIMARY KEY,
    customer_id           VARCHAR(64) NOT NULL,
    order_status          VARCHAR(32) NOT NULL,
    payment_status        VARCHAR(32),
    shipment_status       VARCHAR(32),
    total_amount_minor    BIGINT NOT NULL,
    currency              CHAR(3) NOT NULL,
    line_items_json       JSONB NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL,
    last_projected_at     TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_order_read_customer_time
ON order_read_model (customer_id, created_at DESC);
~~~

Đây là ví dụ PostgreSQL. Trong hệ thống thật cần thiết kế nullability, retention, data types và indexes theo query thật. Read model chứa dữ liệu tổng hợp; không sử dụng nó để kết luận “đã thu tiền” cho thao tác tài chính nếu nguồn thanh toán chưa được xác minh.

## 5. Bản đồ nguồn sự thật cho từng trường dữ liệu

Trước khi làm projection, lập bảng ownership:

| Thuộc tính read model | Context có thẩm quyền | Event/nguồn dữ liệu | Lưu ý |
| --- | --- | --- | --- |
| orderId, customerId, createdAt | Ordering | OrderPlaced | Không lấy customerId từ client chưa xác thực |
| items, quantity, giá chốt | Ordering | OrderPlaced/OrderRepriced theo chính sách | Snapshot giá của đơn, không tự cập nhật theo Catalog |
| tên sản phẩm và thumbnail | Catalog hoặc snapshot ở Ordering | ProductUpdated hoặc OrderPlaced | Quy định hiển thị tên lúc mua hay tên hiện tại |
| paymentStatus | Payments | PaymentSucceeded/Failed/Refunded | Payments là nguồn sự thật tài chính |
| reservationStatus | Inventory | StockReserved/Released/Rejected | Inventory sở hữu reservation |
| shipmentStatus, tracking | Fulfillment/Shipping | ShipmentCreated/Delivered | Một Order có thể có nhiều shipments |
| notificationStatus | Notifications | NotificationDispatched/Failed | Không dùng trạng thái gửi email để kết luận đơn thành công |

Hai điều cần làm rõ:

- **Snapshot hay current value?** Tên sản phẩm trên hóa đơn có thể phải giữ nguyên theo thời điểm đặt, trong khi trang chi tiết sản phẩm có thể hiển thị tên hiện tại.
- **Độ tươi dữ liệu:** trạng thái vận chuyển chậm cập nhật 30 giây có thể chấp nhận; thông tin để quyết định một khoản hoàn tiền có thể cần kiểm tra trực tiếp nguồn có thẩm quyền.

Read model không có quyền viết ngược sang database các context chỉ vì có dữ liệu tổng hợp.

## 6. Hợp đồng sự kiện làm đầu vào

Một projection phụ thuộc vào những message mà các context nguồn công bố. Thay vì lắng nghe mọi thay đổi bảng bằng bất kỳ field nào, nên có contract event ổn định về cấu trúc và ngữ nghĩa.

Ví dụ:

~~~json
{
  "eventId": "evt-order-100",
  "eventType": "OrderPlaced",
  "eventVersion": 1,
  "aggregateId": "ORD-1001",
  "aggregateVersion": 1,
  "occurredAt": "2026-11-11T10:00:00Z",
  "correlationId": "checkout-1001",
  "data": {
    "orderId": "ORD-1001",
    "customerId": "CUS-17",
    "totalAmountMinor": 500000,
    "currency": "VND",
    "items": [
      {"sku": "BOOK-01", "nameAtPurchase": "Sách A", "quantity": 2}
    ]
  }
}
~~~

Một event khác:

~~~json
{
  "eventId": "evt-payment-200",
  "eventType": "PaymentSucceeded",
  "eventVersion": 1,
  "aggregateId": "PAY-101",
  "aggregateVersion": 3,
  "occurredAt": "2026-11-11T10:00:08Z",
  "correlationId": "checkout-1001",
  "data": {
    "orderId": "ORD-1001",
    "paymentId": "PAY-101",
    "capturedAmountMinor": 500000,
    "currency": "VND"
  }
}
~~~

Các field và giá trị là ví dụ; hệ thống thật phải định nghĩa chính xác paymentSucceeded phản ánh authorization, capture hay settlement và áp dụng chúng nhất quán.

### Metadata tối thiểu đáng cân nhắc

- eventId: nhận diện delivery trùng của cùng một event.
- eventType và eventVersion: xác định cách đọc theo contract.
- aggregateId: đối tượng nghiệp vụ nguồn.
- aggregateVersion hoặc sequence: giúp xử lý thứ tự của **một nguồn/aggregate**.
- occurredAt: thời điểm nghiệp vụ ghi nhận; không đủ để xác lập thứ tự nhân quả toàn hệ thống.
- correlationId: liên kết nhiều sự kiện của một workflow.
- schema ID nếu sử dụng serializer/schema registry phù hợp.
- producer/context identity nếu hệ thống cần kiểm soát nguồn phát.

Không yêu cầu mọi event phải chứa mọi field kể trên. Điều quan trọng là projection có đủ thông tin để quản lý idempotency, semantics và consistency theo yêu cầu.

## 7. Luồng cập nhật read model

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Ordering
    participant OB as Outbox
    participant B as Event Broker
    participant P as Order Read Projector
    participant R as Read Database
    participant Q as Query API

    O->>O: Transaction tạo Order
    O->>OB: Ghi OrderPlaced trong cùng transaction
    OB-->>B: Publisher gửi event
    B-->>P: Deliver OrderPlaced
    P->>R: Upsert Order row + processed event
    P-->>B: Ack/commit offset sau DB commit
    Q->>R: GET order details
    R-->>Q: Snapshot đã được chiếu
~~~

Ở mỗi bước có failure modes:

1. Order đã commit nhưng event chưa phát: Outbox publisher còn có thể phát về sau.
2. Event đã được publish nhưng producer chưa ghi nhận checkpoint: event có thể được gửi lại.
3. Projector đã commit DB nhưng crash trước khi ack: cùng event có thể được giao lại.
4. Projector gặp schema mới không giải mã được: consumer có thể dừng, retry hoặc chuyển vào luồng xử lý ngoại lệ.
5. Query đến khi event chưa được áp: read model vẫn là trạng thái cũ.
6. Một context nguồn lỗi: projection có thể tiếp tục phục vụ snapshot cuối với cảnh báo freshness nếu chính sách cho phép.

Vì vậy, **không dựa vào giả định mỗi event chỉ đến đúng một lần** để xây hệ thống an toàn.

## 8. Vì sao Transactional Outbox thường được dùng?

Giả sử Ordering xử lý CreateOrder bằng transaction database rồi phát OrderPlaced lên broker:

~~~text
BEGIN
INSERT INTO orders ...
COMMIT

publish OrderPlaced to broker
~~~

Nếu process chết giữa COMMIT và publish, DB có Order nhưng broker thiếu sự kiện. Nếu đảo thứ tự publish rồi COMMIT, consumer có thể nhận OrderPlaced trong khi transaction Order bị rollback.

**Transactional Outbox** lưu ý định phát sự kiện trong **cùng transaction cục bộ** với thay đổi trạng thái:

~~~sql
BEGIN;

INSERT INTO orders (order_id, customer_id, status, total_amount_minor)
VALUES ('ORD-1001', 'CUS-17', 'PENDING', 500000);

INSERT INTO outbox_events
    (event_id, aggregate_id, event_type, payload_json, created_at)
VALUES
    ('evt-order-100', 'ORD-1001', 'OrderPlaced',
     '{"orderId":"ORD-1001"}', CURRENT_TIMESTAMP);

COMMIT;
~~~

Outbox publisher hoặc CDC adapter đưa dữ liệu từ bảng outbox ra broker. Đây là ví dụ tối giản; cần metadata đủ dùng, schema, transaction boundaries, retry, cleanup và monitoring.

**Outbox không tự đảm bảo exactly-once processing ở consumer.** Sự kiện có thể được publish hoặc deliver lại. Consumer/projector vẫn cần xử lý trùng an toàn và quản lý checkpoint.

## 9. Idempotency: một event giao lại không được nhân tác dụng

Giả sử PaymentSucceeded(evt-payment-200) được deliver hai lần vì consumer restart.

**Không đúng:**

~~~text
on PaymentSucceeded:
    totalPaid += capturedAmount
~~~

Nếu không kiểm soát trùng, hai delivery có thể làm totalPaid tăng hai lần. Cách làm phù hợp là ghi eventId đã xử lý, hoặc sử dụng phép gán/upsert idempotent theo nguồn và version.

Một bảng hỗ trợ:

~~~sql
CREATE TABLE projection_inbox (
    projector_name VARCHAR(64) NOT NULL,
    event_id       VARCHAR(128) NOT NULL,
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (projector_name, event_id)
);
~~~

Ý tưởng xử lý trong một transaction:

~~~text
BEGIN
  INSERT (projector, eventId) vào projection_inbox
  nếu duplicate key:
      xác nhận event đã áp trước đó, không thực hiện side effect thêm
  nếu insert thành công:
      APPLY projection update
COMMIT
ACK broker
~~~

**Inbox insert và projection update phải có transaction phù hợp**, nếu không có thể ghi “đã xử lý event” nhưng projection chưa cập nhật. Khi dùng nhiều kho không có transaction chung, cần thiết kế cơ chế idempotency/compensation khác.

### Một mẫu SQL upsert theo version

~~~sql
INSERT INTO order_payment_projection
    (order_id, payment_id, payment_status, source_version)
VALUES
    ('ORD-1001', 'PAY-101', 'SUCCEEDED', 3)
ON CONFLICT (order_id) DO UPDATE
SET payment_id = EXCLUDED.payment_id,
    payment_status = EXCLUDED.payment_status,
    source_version = EXCLUDED.source_version
WHERE order_payment_projection.source_version < EXCLUDED.source_version;
~~~

Ví dụ này **chỉ đúng nếu** thực sự có một version tăng đơn điệu cho trạng thái payment liên quan đến order. Nếu một Order có nhiều Payment Attempt hoặc refunds, dùng một source_version duy nhất có thể không hợp lệ. Khi đó cần mô hình theo paymentId/attemptId, aggregateVersion hoặc timeline rõ ràng.

## 10. Thứ tự sự kiện: không có thứ tự toàn cục mặc định

Một projection nhận sự kiện từ Ordering, Payments, Inventory và Shipping. Dù mỗi nguồn giữ thứ tự theo aggregate, **không có bảo đảm mặc định rằng các sự kiện từ các nguồn này đến theo thứ tự nghiệp vụ toàn hệ thống**.

Ví dụ:

~~~text
Thời điểm nghiệp vụ:
  OrderPlaced        10:00:00
  PaymentSucceeded   10:00:08
  ShipmentCreated    10:00:10

Thứ tự đến projector:
  PaymentSucceeded
  OrderPlaced
  ShipmentCreated
~~~

PaymentSucceeded có thể đến trước OrderPlaced vì producer/broker/consumer thuộc các luồng khác nhau. Nếu projector chỉ UPDATE bản ghi Order vốn chưa tồn tại rồi bỏ qua, dữ liệu thanh toán có thể mất khỏi read model.

### Các chiến lược xử lý

**A. Partial projection/upsert:** cho phép bản ghi đọc bắt đầu ở trạng thái chưa đủ field, cập nhật dần khi từng sự kiện đến.

**B. Pending events:** lưu sự kiện chưa có aggregate tham chiếu vào inbox/pending queue, thử lại khi đủ điều kiện.

**C. Split source projections:** duy trì PaymentProjection, OrderProjection, ShipmentProjection riêng rồi hợp nhất ở query hoặc bằng một job bổ sung. Điều này giảm phụ thuộc order of arrival giữa context.

**D. Sequence/version per aggregate:** dùng version từ từng nguồn để bỏ cập nhật cũ, không suy ra một global version chung.

**E. Reconciliation:** định kỳ so sánh những bản ghi kẹt/thành phần thiếu với nguồn có thẩm quyền.

**F. Deterministic reducers:** thiết kế phép cập nhật lặp lại cho ra kết quả như nhau theo tập sự kiện hợp lệ, khi có thể.

### Vì sao timestamp không đủ?

Đồng hồ của các hệ thống có thể lệch, event có thể được tạo trước khi publish, và nguồn khác nhau không có total order chung. So sánh occurredAt giữa Payments và Shipping để xác định một sự kiện “mới hơn” không nhất thiết đúng với semantics. Version/sequence theo aggregate và state machine domain thường đáng tin hơn cho từng loại trạng thái.

## 11. Kafka partition và message key

Nếu dùng Kafka, một partition cung cấp thứ tự log **trong partition đó**. Có thể chọn orderId làm message key để các sự kiện của **cùng một order từ một producer/topic tương ứng** được phân phối ổn định theo mapping key–partition ở thời điểm cấu hình.

~~~text
orders.events:
  key=ORD-1001 OrderPlaced(v1)
  key=ORD-1001 OrderConfirmed(v2)
  key=ORD-1001 OrderCancelled(v3)

payments.events:
  key=PAY-101 PaymentInitiated(v1)
  key=PAY-101 PaymentSucceeded(v2)
~~~

Hai topic/partition khác nhau **không có thứ tự toàn cục**. Hơn nữa, thay partition count, key strategy, producer concurrency và chính sách retry có thể ảnh hưởng giả định ordering. Consumer cũng có thể xử lý song song làm thứ tự commit vào read store khác với thứ tự nhận.

### Chọn key theo đối tượng nào?

- Order lifecycle events: thường là orderId.
- Payment lifecycle events: có thể là paymentId.
- Shipment events: có thể là shipmentId.
- Customer profile events: có thể là customerId.

Projection tổng hợp theo orderId phải hiểu các key gốc khác nhau và quan hệ cross-context. **Đừng ép mọi sự kiện dùng orderId** nếu điều đó làm sai ownership/mô hình của context nguồn; thay vào đó thiết kế mapping và xử lý thứ tự phù hợp.

### Consumer group và partition assignment

Trong một consumer group, mỗi partition thường do một member xử lý tại một thời điểm theo cơ chế giao thức được dùng. Khi rebalance hoặc restart, message có thể được giao lại; việc commit offset quá sớm có thể làm mất update, còn commit sau DB commit có thể dẫn đến redelivery. Idempotency là biện pháp cốt lõi để xử lý giao lại.

## 12. Eventual consistency: dữ liệu đọc có thể chậm hơn nguồn

Khi Payments đã ghi PaymentSucceeded nhưng projector chưa áp, GET /orders/ORD-1001 có thể trả paymentStatus=PENDING. Đó là một biểu hiện của **eventual consistency**.

**Eventual consistency không có nghĩa “không cần cam kết thời gian”**. Cần xác định:

- Độ trễ cập nhật điển hình và mục tiêu p95/p99.
- Với dữ liệu nào cho phép chậm, dữ liệu nào phải xác minh trước hành động.
- Client cần nhìn thấy trạng thái pending/loading nào.
- Có cung cấp trường lastUpdatedAt hoặc freshness indicator không.
- Khi lag vượt ngưỡng, API nên trả snapshot cũ kèm cảnh báo hay từ chối một số operation.
- Có cơ chế read-your-writes hoặc tra cứu nguồn khi khách vừa thực hiện thao tác quan trọng không.

### Read-your-writes

Khách vừa đặt đơn có thể được trả ngay orderId và trạng thái PENDING từ write API, nhưng query projection ở giây tiếp theo chưa có bản ghi. Có các lựa chọn:

1. **UI hiển thị response của command** trong lúc chờ projection.
2. **Đọc nguồn tạm thời cho luồng vừa ghi** ở một số endpoint nhạy cảm.
3. **Chờ checkpoint/version** của projection đạt một watermark nhất định với timeout giới hạn.
4. **Trả 202/đang đồng bộ** hoặc “đơn đang được xử lý”, kèm endpoint để poll.
5. **Cập nhật giao diện theo event/push** nếu cần, nhưng vẫn dựa trên nguồn trạng thái hợp lệ.

Không nên tự động coi “query chưa thấy đơn” là bằng chứng command trước đã thất bại. Có thể message chưa đến hoặc projector đang lag.

### Mẫu response có metadata

~~~json
{
  "orderId": "ORD-1001",
  "status": "PAYMENT_PENDING",
  "readModelVersion": 17,
  "lastProjectedAt": "2026-11-11T10:00:03Z",
  "synchronizationStatus": "UPDATING"
}
~~~

Các field là ví dụ; API phải định nghĩa cụ thể readModelVersion tính theo cái gì. Nếu data được tổng hợp từ nhiều nguồn, một con số version đơn lẻ không tự thể hiện mọi source đã cập nhật đến đâu.

## 13. Tránh quyết định nghiệp vụ từ projection đã trễ

Một lỗi nguy hiểm:

~~~text
Order Read Model cho biết paymentStatus = PENDING
=> Payment Service quyết định thu tiền thêm lần nữa.
~~~

Payment Service phải đối chiếu payment attempt và provider transaction trong nguồn có thẩm quyền của chính mình. Read model phục vụ màn hình có thể chậm hoặc thiếu event; dùng nó làm căn cứ cuối cho thao tác tài chính gây double charge.

Tương tự:

- Inventory không quyết định available stock dựa vào dashboard projection.
- Ordering không hủy đơn chỉ vì search index chưa có ShipmentCreated.
- Refund logic không tự dùng số dư hiển thị tại read model để quyết định nghĩa vụ.
- Authorization không được bỏ qua vì projection thiếu tenantId hoặc customerId.

Một projection có thể cung cấp thông tin hỗ trợ quyết định, nhưng những bất biến đòi hỏi trạng thái mới và nhất quán phải được thực thi ở context nguồn hoặc qua một giao thức xác minh phù hợp.

## 14. Các mô hình triển khai projection phổ biến

### Mô hình A: consumer chuyên trách

~~~text
Kafka topic -> order-read-projector -> PostgreSQL read schema
                                      -> Query API
~~~

Projector có deployment, consumer group, monitoring và cadence riêng. Có thể scale theo partitions, nhưng số worker nhiều hơn partition không tự tăng throughput của cùng một consumer group/topic.

### Mô hình B: read service tích hợp consumer

~~~text
Order Read Service:
  - event listener
  - read repository
  - query endpoints
~~~

Phù hợp use case đơn giản; cần bảo đảm lifecycle consumer không làm quá tải API query khi traffic tăng. Khi consumer lag, có thể tách deployment hoặc cấu hình tài nguyên.

### Mô hình C: CDC và materialized view

Có thể lấy các thay đổi từ Outbox hoặc database change data capture. CDC hữu ích để tích hợp hệ thống cũ và giảm rủi ro mất event sau commit. Tuy nhiên, **CDC raw row changes không tự tạo domain event có ngữ nghĩa tốt**. Một event kiểu “row order updated column status=PAID” có thể rò schema nội bộ và buộc consumer biết trạng thái domain mà producer chưa công bố chính thức.

### Mô hình D: managed stream processing

Kafka Streams, Flink, ksqlDB hoặc các stream processors khác có thể thực hiện map, filter, join, window, aggregate và quản lý state store/checkpoint. Đây là lựa chọn khi khối lượng, event-time semantics hoặc join stream phức tạp. Nó không xóa nhu cầu hiểu exactly-once scope, version, side effects ngoài hệ thống và quyền dữ liệu.

### Mô hình E: database materialized view cục bộ

Nếu read và write vẫn thuộc cùng context/database, đôi khi một SQL materialized view, index hoặc bảng summary được cập nhật trong cùng transaction đủ đáp ứng nhu cầu. Không nhất thiết thêm broker chỉ để hiển thị một danh sách đơn.

## 15. Các lựa chọn lưu projection

| Nơi lưu | Tình huống | Lưu ý |
| --- | --- | --- |
| PostgreSQL/MySQL | Query filter, join nhỏ, pagination, transaction inbox | Index, concurrency, upsert, schema migration |
| Document DB | Dữ liệu đọc tổng hợp dạng document | Update partial fields, phân vùng, consistency |
| Elasticsearch/OpenSearch | Full-text search, filter nhiều trường | Refresh lag, mapping, reindex, source-of-truth |
| Redis | Tra cứu key nhanh, materialized cache | Persistence/eviction/TTL không phù hợp mọi read model |
| Columnar warehouse | Analytics tổng hợp lớn | Không thay thế API transactional latency thấp |
| Stream state store | Join/aggregate trong stream processing | Checkpoint, changelog, state restore, scaling |
| Multiple stores | Chi tiết đơn trong RDBMS + tìm kiếm trong index | Đồng bộ, ownership và chi phí vận hành |

Không chọn Elasticsearch cho mọi read model chỉ vì có event. Cần benchmark workload, độ trễ, consistency và khả năng vận hành của đội.

## 16. Mô hình projections nhiều phần để tránh mất cập nhật

Nếu Ordering, Payments và Shipping cùng cập nhật **một hàng order_read_model**, cần tránh việc xử lý một event ghi đè các field thuộc context khác.

Ví dụ sai:

~~~text
Payment handler:
  đọc toàn bộ order_read_model
  paymentStatus = SUCCEEDED
  ghi lại toàn row

Shipping handler:
  đọc toàn bộ row cũ chưa thấy payment update
  shipmentStatus = IN_TRANSIT
  ghi lại toàn row

Kết quả: paymentStatus bị ghi đè về PENDING.
~~~

Có thể giải quyết bằng:

- Partial UPDATE chỉ tác động cột thuộc event đó.
- Optimistic lock/version khi update theo document.
- Tách bảng order_core_projection, payment_projection, shipment_projection và join ở query.
- Thiết kế event-specific reducers đảm bảo trạng thái hợp lệ.
- Tận dụng transaction/atomic update của database.

### Ví dụ tách bảng

~~~sql
CREATE TABLE order_core_projection (
    order_id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    order_status VARCHAR(32) NOT NULL,
    source_version BIGINT NOT NULL
);

CREATE TABLE payment_projection (
    payment_id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL,
    payment_status VARCHAR(32) NOT NULL,
    source_version BIGINT NOT NULL
);

CREATE TABLE shipment_projection (
    shipment_id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL,
    shipment_status VARCHAR(32) NOT NULL,
    source_version BIGINT NOT NULL
);
~~~

Query API có thể join các bảng đọc trong chính read database theo khóa orderId. Đây là **read store của projection**, không phải trực tiếp join database private của Ordering, Payments và Shipping. Nếu một đơn có nhiều payment attempts hoặc shipments, thiết kế schema phải phản ánh quan hệ đó thay vì chỉ lưu một status.

## 17. Java/Spring: kiến trúc projector đơn giản

Một ứng dụng Java có thể tách các lớp:

~~~text
Broker Listener
    -> Deserialize + validate event schema
    -> Projection Application Service
    -> Idempotency / ordering checks
    -> Transaction update read DB + inbox
    -> Commit/ack after durable update

Query Controller
    -> Authorization
    -> Read Repository
    -> DTO / pagination / freshness response
~~~

Ví dụ domain event record:

~~~java
public record OrderPlacedEvent(
    String eventId,
    String orderId,
    long aggregateVersion,
    String customerId,
    long totalAmountMinor,
    String currency
) {}

public record PaymentSucceededEvent(
    String eventId,
    String orderId,
    String paymentId,
    long paymentVersion
) {}
~~~

Các record chỉ minh họa phần dữ liệu cần thiết; trong dự án thật sẽ dùng schema serializer có version, metadata và validation phù hợp.

### Mẫu projector với transaction

~~~java
@Service
public final class OrderReadProjector {
    private final ProcessedEventRepository processed;
    private final OrderReadRepository readRepository;

    public OrderReadProjector(
        ProcessedEventRepository processed,
        OrderReadRepository readRepository
    ) {
        this.processed = processed;
        this.readRepository = readRepository;
    }

    @Transactional
    public void onOrderPlaced(OrderPlacedEvent event) {
        // insertIfAbsent phải được bảo vệ bằng unique constraint
        // trong cùng transaction với cập nhật read model.
        if (!processed.insertIfAbsent("order-detail", event.eventId())) {
            return;
        }

        readRepository.applyOrderPlaced(
            event.orderId(),
            event.customerId(),
            event.totalAmountMinor(),
            event.currency(),
            event.aggregateVersion()
        );
    }

    @Transactional
    public void onPaymentSucceeded(PaymentSucceededEvent event) {
        if (!processed.insertIfAbsent("order-detail", event.eventId())) {
            return;
        }

        readRepository.applyPaymentSucceeded(
            event.orderId(),
            event.paymentId(),
            event.paymentVersion()
        );
    }
}
~~~

Các repository/interface và phần xử lý race chưa được trình bày đầy đủ. Đặc biệt, nếu event PaymentSucceeded đến trước OrderPlaced, phương thức applyPaymentSucceeded phải lưu được dữ liệu tạm, upsert riêng hoặc chuyển vào pending events; không được âm thầm bỏ qua.

### Listener Kafka minh họa

~~~java
@Component
class OrderEventListener {
    private final OrderReadProjector projector;

    OrderEventListener(OrderReadProjector projector) {
        this.projector = projector;
    }

    @KafkaListener(
        topics = "orders.events",
        groupId = "order-read-projector"
    )
    public void onOrderPlaced(OrderPlacedEvent event) {
        projector.onOrderPlaced(event);
        // Ack/offset commit phụ thuộc container configuration.
        // Không xác nhận offset trước transaction đã hoàn tất.
    }
}
~~~

Ví dụ mang tính cấu trúc. Trong hệ thống thật cần cấu hình deserializer/consumer theo topic event type, retry, offset commit, error handler, DLQ và transaction boundaries. Khi dùng Spring Kafka, lựa chọn auto/manual ack và error handler quyết định hành vi giao lại; không copy một class mẫu và mặc định đạt exactly-once.

## 18. Chiến lược chống event cũ ghi đè event mới

Đối với sự kiện của cùng Order, có thể dùng aggregateVersion:

~~~text
OrderPlaced(orderId=ORD-1001, version=1)
OrderConfirmed(orderId=ORD-1001, version=2)
OrderCancelled(orderId=ORD-1001, version=3)
~~~

Projector lưu source_version đã áp. Event version=2 đến lại sau version=3 không được đưa trạng thái về CONFIRMED.

SQL upsert ý tưởng:

~~~sql
INSERT INTO order_core_projection (
    order_id, customer_id, order_status, source_version
)
VALUES ('ORD-1001', 'CUS-17', 'CONFIRMED', 2)
ON CONFLICT (order_id) DO UPDATE
SET order_status = EXCLUDED.order_status,
    source_version = EXCLUDED.source_version
WHERE order_core_projection.source_version < EXCLUDED.source_version;
~~~

Lưu ý: cách này chỉ bảo vệ khỏi **stale overwrite** khi source_version đúng và trạng thái sau có đủ để xây projection. Nếu event version=1 chứa customerId nhưng version=2 thiếu dữ liệu này, việc bỏ version=1 do version=2 đã đến trước có thể khiến projection thiếu field mãi. Có thể cần lưu pending events, xử lý theo sequence hoặc định nghĩa event mới có đủ snapshot.

Không nhầm source version của Ordering với version của Payments; hai context không có bộ đếm chung. Với paymentId, cần version theo payment aggregate; với shipmentId, version theo shipment aggregate. Read model tổng hợp phải xử lý sự độc lập đó.

## 19. Rebuild projection: nếu bị lỗi hoặc muốn đổi schema đọc

Read model là biểu diễn được **tái tạo**, nhưng tái tạo được hay không còn phụ thuộc việc có đủ dữ liệu nguồn hợp lệ. Khi phát hiện logic projection sai, muốn bổ sung field hay đổi index, có thể cần rebuild.

### Các nguồn rebuild

1. **Event log bền vững đầy đủ:** replay từ đầu nếu tất cả event cần thiết còn trong retention/archive và schema cũ giải mã được.
2. **Snapshot và event sau snapshot:** khởi tạo từ snapshot có version/watermark rồi áp các event mới.
3. **Backfill API/export từ source:** lấy ảnh chụp dữ liệu nguồn có thẩm quyền, sau đó bắt kịp event phát sinh trong lúc backfill.
4. **CDC snapshot + stream:** dùng cơ chế snapshot đồng bộ với position/changelog khi nền tảng hỗ trợ.

Không được kết luận “có Kafka là luôn replay được tất cả lịch sử”. Topic có retention, compaction và schema evolution; event có thể đã hết hạn hoặc không chứa dữ liệu cần cho projection mới.

### Rebuild bằng projection v2

Một chiến lược giảm gián đoạn:

~~~text
Production Query API -> Read Model v1 (đang phục vụ)
                              |
                              v
Event source / snapshots -> Projector v2 -> Read Model v2
                              |
                              v
                     Validate + catch up
                              |
                              v
                    Switch Query API to v2
                              |
                              v
                    Retire v1 after rollback window
~~~

Các bước:

1. Tạo schema/storage v2 tách khỏi v1.
2. Xác định điểm bắt đầu replay hoặc snapshot watermark hợp lệ.
3. Chạy projector v2 đọc dữ liệu cũ và đồng thời bắt kịp event mới.
4. Đối chiếu số bản ghi, các tổng hợp quan trọng và mẫu dữ liệu với nguồn.
5. Xác định độ trễ khi v2 đã catch up đến watermark yêu cầu.
6. Dùng feature flag, alias hoặc route để chuyển query sang v2 có kiểm soát.
7. Theo dõi kết quả sau chuyển, giữ khả năng quay lại v1 trong thời hạn hợp lý.
8. Chỉ xóa v1 khi đã kiểm chứng và hoàn tất quy trình deprecation.

**Không sửa read model v1 đang phục vụ bằng một rebuild phá cấu trúc** nếu có thể gây downtime hoặc trả dữ liệu thiếu cho người dùng.

## 20. Vấn đề snapshot và backfill khi nguồn đang tiếp tục ghi

Giả sử lấy snapshot Order lúc 10:00 rồi bắt đầu nghe event lúc 10:05. Trong năm phút đó có những đơn mới hoặc trạng thái đổi. Nếu không có checkpoint/offset phù hợp, projection sẽ bị thiếu dữ liệu.

Một cách tiếp cận hợp lệ phải định nghĩa **điểm nối** giữa snapshot và event stream:

- Capture broker/CDC position trước hoặc trong snapshot theo thuật toán được hỗ trợ.
- Chụp dữ liệu tại một snapshot nhất quán hoặc lưu record version.
- Áp event từ một vị trí đủ sớm và loại trùng bằng eventId/version.
- Bảo đảm event xảy ra trong lúc quét snapshot không bị bỏ sót.
- Có kiểm tra reconciliation cho bản ghi còn khác biệt.

Chi tiết tùy database, CDC và broker. **Không có một công thức “đọc bảng rồi bắt đầu Kafka từ latest” áp dụng an toàn cho mọi hệ thống**.

### Backfill qua API

Nếu source không cho quyền trực tiếp vào database, có thể tạo API export theo cursor/snapshot token và version. Đối với dataset lớn, cần rate limit/backpressure để backfill không làm suy giảm traffic nghiệp vụ. Hợp đồng export phải mô tả tính nhất quán trang dữ liệu và cách bắt kịp thay đổi.

## 21. Schema evolution của events và read model

Một Event OrderPlaced ban đầu có totalAmountMinor; sau này thêm discountBreakdown hoặc shippingAddressRef. Những thay đổi này ảnh hưởng:

- Producer schema.
- Serializer/deserializer, Schema Registry nếu có.
- Projector v1/v2.
- Data migration/backfill.
- Query API DTO và consumers.
- Chính sách dữ liệu nhạy cảm.

Một hướng tương thích:

1. Thêm field tùy chọn hoặc event type mới theo định nghĩa business.
2. Cho projector hiểu cả event schema cũ và mới.
3. Kiểm tra fixture của lịch sử event.
4. Cập nhật read schema/index bằng migration có kiểm soát.
5. Rebuild khi field mới cần có mặt trên dữ liệu lịch sử.
6. Thay Query API một cách tương thích với client nếu cần.

**Một event có cùng kiểu JSON nhưng đổi ý nghĩa** vẫn có thể phá semantic compatibility. Ví dụ amountMinor đổi đơn vị từ đồng nguyên sang phần trăm không thể xem là thay đổi an toàn vì type vẫn là long.

### Version của projection và version của event

- Event schema version: producer công bố format/semantics.
- Aggregate version: thứ tự thay đổi của một aggregate nguồn.
- Projection schema version: cấu trúc bảng đọc.
- Projector implementation version: thuật toán reducer/handler.
- Query API version: hợp đồng mà consumer đọc.
- Broker offset: vị trí message trong một partition.
- Read model freshness watermark: vị trí tiến độ đã áp từ các nguồn.

Không gộp tất cả thành một biến version duy nhất.

## 22. Độ trễ và watermark: thế nào là đã đồng bộ?

Một read model nhận events từ nhiều topics và partitions. Có thể đo:

- **Consumer lag:** số record chưa được tiêu thụ theo offset; thấp không đảm bảo xử lý nghiệp vụ đúng.
- **Processing latency:** thời gian từ lúc consumer nhận đến lúc DB commit projection.
- **End-to-end event latency:** từ khi event xảy ra hoặc được publish đến lúc projection phản ánh.
- **Watermark/checkpoint:** tiến độ đã áp đối với partition/source cụ thể.
- **Pending events:** các event chưa thể áp vì thiếu dữ liệu liên quan.
- **Reconciliation gap:** số trường hợp dữ liệu projection lệch nguồn sau kiểm tra.

Một độ trễ trung bình 1 giây có thể che giấu một partition bị kẹt 2 giờ. Theo dõi p95/p99, max age, lag theo partition và lỗi theo event type. Với một read model kết hợp nhiều nguồn, “đã đồng bộ tới 10:00” cần có định nghĩa chính xác hơn một timestamp chung.

### Quan sát gắn với trải nghiệm người dùng

Nếu người dùng vừa thanh toán và màn hình vẫn PENDING hơn ngưỡng cho phép, hệ thống có thể hiển thị “Đang cập nhật trạng thái thanh toán” cùng cơ chế refresh/notify. Nếu UI báo thất bại và khuyến khích thanh toán lại khi nguồn thực tế đã thành công, đó có thể là lỗi nghiệp vụ nghiêm trọng.

## 23. Retry, DLQ và poison messages

Projector có thể gặp các lỗi khác nhau:

| Loại lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Tạm thời ở DB | PostgreSQL unavailable | Retry bounded/backoff; không ack trước commit |
| Tạm thời ở broker | Broker/network reset | Consumer reconnect theo policy |
| Schema không hiểu | Event version mới chưa được hỗ trợ | Quarantine/alert, deploy compatible consumer |
| Dữ liệu nghiệp vụ thiếu | Payment event chưa có Order | Partial state/pending event, retry có điều kiện |
| Bất biến projection vi phạm | Hai order cùng key sai | Ghi sự cố và đối soát nguồn |
| Duplicate | Cùng eventId được deliver lại | Idempotent no-op |
| Out-of-order | Event version cũ tới sau | Version check/buffer theo semantics |
| Poison message | Event liên tục làm consumer crash | DLQ/quarantine và điều tra chủ sở hữu producer |

Một **DLQ (dead-letter queue)** không làm message trở nên đúng. Cần lưu đủ metadata an toàn để tái xử lý: eventId, source topic/partition/offset, schemaId, error class và thời điểm. Phải kiểm soát PII, retention và quyền truy cập DLQ.

### Tránh ack khi cập nhật projection thất bại

Nếu consumer ack/commit offset trước khi transaction cập nhật read store hoàn tất, crash có thể làm message bị bỏ qua và projection thiếu dữ liệu. Thông thường phải bảo đảm durable update trước checkpoint/ack tương ứng. Nếu hệ thống cung cấp transactional integration tốt hơn, vẫn cần hiểu phạm vi chính xác của guarantee.

### Đừng retry vô hạn một event lỗi dữ liệu

Một message sai schema sẽ không tự sửa sau 10.000 lần retry. Retry nóng có thể chặn toàn partition, tăng lag và tốn CPU. Hãy phân loại lỗi transient/permanent, áp retry bounded và chuyển sang luồng xử lý ngoại lệ có tracking.

## 24. Partial data: màn hình hiển thị khi thiếu một nguồn

Read model không nhất thiết phải chờ đủ tất cả context mới tạo được record:

~~~json
{
  "orderId": "ORD-1001",
  "orderStatus": "ACCEPTED",
  "paymentStatus": "PENDING",
  "shipmentStatus": null,
  "dataCompleteness": {
    "ordering": "CURRENT",
    "payments": "UPDATING",
    "shipping": "NOT_APPLICABLE"
  }
}
~~~

Những trạng thái trên là biểu diễn minh họa. Cần phân biệt:

- **UNKNOWN:** chưa biết hoặc chưa đồng bộ.
- **NOT_APPLICABLE:** không áp dụng cho đơn này.
- **PENDING:** nghiệp vụ đang chờ một bước xác định.
- **FAILED:** nguồn có thẩm quyền xác nhận thất bại.
- **STALE:** có dữ liệu nhưng quá giới hạn freshness.

Không đặt mặc định paymentStatus=FAILED chỉ vì chưa nhận PaymentSucceeded. Không đặt shipmentStatus=DELIVERED vì không có shipment event. **Thiếu sự kiện không phải bằng chứng sự kiện chưa từng xảy ra**.

## 25. Privacy và authorization trong read model tổng hợp

Khi một projection ghép dữ liệu từ nhiều context, nó có nguy cơ trở thành nơi tập trung PII và dữ liệu có quyền truy cập khác nhau.

Ví dụ:

- Ordering cần customerId.
- Notifications có thể cần email hoặc địa chỉ giao hàng.
- Payments lưu thông tin giao dịch và tham chiếu provider.
- Shipping có địa chỉ người nhận, số điện thoại và tracking.
- Analytics có thể chỉ cần dữ liệu đã ẩn danh/tổng hợp.

Nếu OrderReadModel tập hợp tất cả field đó và mở endpoint GET /orders/{id}, hậu quả khi kiểm tra quyền sai có thể rất lớn.

### Các nguyên tắc

1. **Data minimization:** chỉ sao chép field phục vụ query có quyền rõ.
2. **Resource authorization:** user/tenant chỉ đọc đơn được phép; đừng chỉ kiểm tra login thành công.
3. **Role-based views:** nhân viên hỗ trợ có thể thấy trường khác khách hàng; tách DTO/endpoint nếu cần.
4. **Không log secrets:** token, địa chỉ đầy đủ, payment credentials hoặc PII nhạy cảm không được ghi vào log tùy tiện.
5. **Encryption:** bảo vệ dữ liệu in transit/at rest theo threat model.
6. **Retention và deletion:** projection phải phản ánh quy tắc xóa/ẩn danh hoặc hết hạn dữ liệu từ nguồn.
7. **Audit:** ai đọc, dùng mục đích gì, với dữ liệu nào theo chính sách.
8. **Broker ACL:** ai được tiêu thụ event; quyền đọc schema không đồng nghĩa quyền đọc payload.
9. **Rebuild và backup:** dữ liệu đã xóa cần không bị phục hồi trái phép khi replay lịch sử.
10. **Projection ownership:** team sở hữu read model chịu trách nhiệm quyền truy cập và phản ứng khi nguồn phát sinh field mới.

**Truy vấn nhanh không phải lý do bỏ phân quyền.** Một projection read-only vẫn có thể làm lộ dữ liệu nhạy cảm.

## 26. Dữ liệu đã xóa hoặc thay đổi quyền: bài toán đặc biệt

Giả sử người dùng yêu cầu xóa dữ liệu theo chính sách hoặc nhân viên bị thu hồi quyền xem một nhóm đơn. Nếu projection giữ bản ghi cũ mà không cập nhật, UI có thể tiếp tục lộ dữ liệu.

Cần thiết kế:

- Domain events như CustomerAnonymized, AccountClosed, AccessRevoked khi phù hợp.
- Projection handler xóa/ẩn danh field, không chỉ đổi status.
- Chính sách cho event history đã phát và backup/replay.
- Authorization tra nguồn quyền mới nếu read model có thể chậm quá mức chấp nhận.
- Audit của việc xóa, tái dựng và ranh giới dữ liệu.

Thao tác xóa bản ghi khỏi read database **không tự xóa** dữ liệu trong broker, logs, snapshots hoặc backup. Cần phối hợp với chính sách retention và data governance.

## 27. Khi read model chưa đủ mới cho một command

Giả sử nhân viên nhấn “Hoàn tiền” từ màn hình OrderDetail. Read model hiển thị PaymentSucceeded. Có thể dùng read model để **gợi ý UI** rằng nút Refund nên xuất hiện, nhưng command cuối cùng phải gửi đến Payments/Refund context để kiểm tra:

- Payment còn hợp lệ và chưa hoàn toàn refunded.
- Số tiền refund không vượt nghĩa vụ còn lại.
- Actor có quyền refund theo tenant/role.
- Provider reference tồn tại và phản hồi an toàn.
- Các thao tác concurrent không tạo hai khoản hoàn.
- Có idempotency key và reconciliation cho timeout.

Read model hiển thị có thể đã cũ. Domain source chịu trách nhiệm kết quả cuối, trả lỗi hợp lệ nếu điều kiện đã đổi. UI cần xử lý conflict thay vì tự ghi đè trạng thái.

## 28. Tối ưu read model theo truy vấn

### Pagination và sắp xếp

Danh sách đơn thường cần phân trang theo thời gian. Offset pagination có thể kém hiệu quả hoặc không ổn định khi thêm bản ghi mới; cursor/keyset pagination dựa trên createdAt + orderId có thể phù hợp hơn với dataset lớn.

~~~sql
SELECT order_id, customer_id, order_status,
       payment_status, created_at
FROM order_read_model
WHERE customer_id = 'CUS-17'
  AND (created_at, order_id) < ('2026-11-11T10:00:00Z', 'ORD-1001')
ORDER BY created_at DESC, order_id DESC
LIMIT 30;
~~~

Cần index phù hợp và xử lý cùng timestamp bằng tie-breaker. SQL minh họa giả định PostgreSQL và định dạng timestamp được parse đúng.

### Search index

Nếu tìm theo tên sản phẩm hoặc mã vận đơn, có thể tạo projection vào search engine với document riêng. Chú ý search index refresh lag và cơ chế reindex; không dùng kết quả tìm kiếm để xác nhận một transaction đã commit.

### Aggregation

Dashboard “số đơn đang chờ thanh toán” có thể duy trì counter từ events. Nhưng đếm cộng/trừ rất nhạy với duplicate và event đến thiếu. Có thể cần eventId ledger hoặc tái tính từ read store có nguồn kiểm chứng.

### Snapshot và document

Một document OrderDetail chứa dòng hàng, payment summary, shipments giúp API đọc một lần. Tuy nhiên update concurrent vào các phần document cần atomic partial update/optimistic locking, tránh ghi đè stale state.

## 29. Những anti-pattern phổ biến

### Anti-pattern 1: project từ những bảng private không có hợp đồng

BFF đọc trực tiếp order_db, payment_db và shipping_db. Khi team nguồn đổi schema, query vỡ. Khắc phục bằng event/CDC contract hoặc API chính thức.

### Anti-pattern 2: coi read model là nguồn sự thật

Payment Service dựa vào paymentStatus trong OrderDetailProjection để quyết định charge/refund. Projection có thể lag nên không được dùng làm authority cho bất biến tài chính.

### Anti-pattern 3: không có idempotency

Redelivery PaymentSucceeded khiến paidAmount tăng hai lần. Dùng inbox/unique eventId và transaction hoặc reducer idempotent phù hợp.

### Anti-pattern 4: ack trước DB commit

Consumer crash sau ack nhưng trước write; sự kiện bị bỏ qua. Thiết kế commit order chính xác.

### Anti-pattern 5: chỉ xử lý sự kiện theo thứ tự lý tưởng

PaymentSucceeded đến trước OrderPlaced và bị bỏ. Dùng partial projection/pending events hoặc split source views.

### Anti-pattern 6: dùng timestamp làm total order

So sánh thời gian từ nhiều service rồi bỏ event có timestamp nhỏ hơn. Clocks và network không bảo đảm causal ordering; dùng per-aggregate version và semantics.

### Anti-pattern 7: giữ toàn bộ PII trong một view cho tiện

Projection trở thành một kho dữ liệu nhạy cảm không được phân quyền. Áp data minimization và resource authorization.

### Anti-pattern 8: giả định Kafka retention là vô hạn

Cần rebuild nhưng event đầu đã bị xóa. Có snapshot, archive/backfill hoặc retention policy được xác minh.

### Anti-pattern 9: nâng cấp projector và schema đọc ngay trên bản đang phục vụ

Rebuild nửa chừng tạo kết quả thiếu. Dùng blue/green read model hoặc migration an toàn.

### Anti-pattern 10: không có chỉ số freshness

Dashboard vẫn hoạt động nhưng đã ngừng nhận sự kiện hai giờ. Theo dõi lag/max event age/checkpoint, không chỉ HTTP 200.

### Anti-pattern 11: dùng cùng version cho nhiều context

Payment version=5 và Order version=5 không thể so sánh trực tiếp để quyết định trạng thái “mới hơn”. Cần version riêng theo nguồn.

### Anti-pattern 12: replay với side effects ngoài ý muốn

Chạy lại event để rebuild search index nhưng consumer vô tình gửi email hoặc thu tiền lần nữa. Rebuild projector phải tách khỏi command/side-effect consumer hoặc có chế độ replay an toàn.

## 30. Quy trình thiết kế read model từ đầu

### Bước 1: Chọn query cụ thể

Ví dụ trang chi tiết đơn cần phản hồi trong một giới hạn latency đã thỏa thuận, chấp nhận shipmentStatus chậm cập nhật trong một khoảng xác định. Ghi rõ các truy vấn, filter, sorting, pagination và quyền người dùng.

### Bước 2: Liệt kê field và nguồn authority

Đánh dấu mỗi field thuộc Ordering, Payments, Inventory, Shipping hay Catalog; phân biệt snapshot lúc đặt với thông tin hiện tại.

### Bước 3: Quyết định có cần projection không

Nếu màn hình chỉ cần hai API và QPS thấp, API Composition có thể đơn giản hơn. Nếu cần fan-out lớn, nhiều query lặp, full-text search hoặc read scaling, projection có thể có lợi.

### Bước 4: Thiết kế event contracts

Mỗi event cần ý nghĩa business, producer, payload, identity, version, privacy và ordering assumptions. Nêu cách source publish đáng tin cậy: Outbox/CDC hoặc phương án tương đương.

### Bước 5: Thiết kế read store

Chọn schema theo access patterns, indexes và TTL/retention. Không chỉ copy các bảng domain sang database khác rồi gọi đó là mô hình đọc tối ưu.

### Bước 6: Thiết kế projector

Xác định:
- idempotency và inbox;
- transaction boundary;
- xử lý event đến trước/đến trễ;
- per-source aggregate version;
- offset/ack sau durable commit;
- retry, DLQ và monitoring;
- schema evolution và unknown event types.

### Bước 7: Thiết kế bootstrap và recovery

Nguồn replay nào đủ? Nếu không, có snapshot/backfill API nào? Cần watermark/catch-up strategy trước khi mở API production.

### Bước 8: Thiết kế API và UX cho eventual consistency

Các trạng thái PENDING, UNKNOWN, STALE, NOT_APPLICABLE cần có semantics rõ. Các thao tác nhạy cảm phải gọi source authority để xác minh.

### Bước 9: Thêm bảo mật và governance

Kiểm tra quyền theo user/tenant/resource; tránh PII không cần; ghi ownership và privacy policy của projection.

### Bước 10: Vận hành và đo lường

Theo dõi event age, consumer lag, projection errors, DB latency, DLQ và reconciliation discrepancies. Định nghĩa SLO riêng cho freshness và query latency.

## 31. Một checklist thực tế

| Hạng mục | Câu hỏi cần trả lời |
| --- | --- |
| Query consumer | Màn hình/ứng dụng nào sử dụng projection? |
| Read contract | API/DTO và pagination/filter/sort là gì? |
| Owner | Team nào chịu trách nhiệm projector, DB và sự cố? |
| Source facts | Context nào sở hữu từng field? |
| Event contract | Event nào cập nhật field nào, schema version nào? |
| Durability | Event còn đủ để replay hay cần snapshot/backfill? |
| Idempotency | Event trùng được bỏ qua an toàn ra sao? |
| Ordering | Có version/sequence theo aggregate hay không? |
| Partial updates | Event đến trước nguồn liên quan xử lý thế nào? |
| Concurrency | Nhiều handler ghi cùng document có race không? |
| Transaction | Read model và inbox commit cùng nhau ra sao? |
| Consumer offset | Khi nào ack/commit? |
| Retry/DLQ | Lỗi tạm và permanent phân biệt bằng gì? |
| Freshness | Chậm bao lâu được phép, alert ở ngưỡng nào? |
| Read-your-writes | Khách vừa ghi có nhìn thấy kết quả thế nào? |
| Authorization | Ai xem được record và từng field? |
| PII/Retention | Dữ liệu nào cần ẩn, xóa hoặc hết hạn? |
| Schema evolution | Producer, projector, read schema thay đổi ra sao? |
| Rebuild | Có chạy projection v2 song song và cutover được không? |
| Observability | Lag, watermark, errors, query latency và reconciliation? |

## 32. Bài tập thực hành

### Bài A: chọn API Composition hay Projection

Một trang quản trị hiển thị 200 đơn, mỗi đơn cần trạng thái thanh toán và giao hàng. Cách hiện tại gọi Order Service một lần rồi gọi Payments và Shipping cho từng đơn, tạo hàng trăm request nội bộ.

Hãy đề xuất một read model hỗ trợ truy vấn theo customerId, trạng thái và createdAt; phân tích đánh đổi latency, độ tươi dữ liệu, chi phí vận hành và API contracts.

### Bài B: xử lý duplicate

Một event PaymentSucceeded có eventId=evt-200 được gửi hai lần. Read model đang cộng tổng tiền mỗi lần nhận event. Hãy thiết kế bảng inbox và transaction bảo đảm không tăng tiền lần thứ hai.

### Bài C: out-of-order

Projector nhận PaymentSucceeded cho ORD-1001 trước OrderPlaced. Hãy giải thích vì sao UPDATE không thấy row có thể gây mất dữ liệu và thiết kế một trong các giải pháp partial projection, pending event hoặc split payment view.

### Bài D: replay từ lịch sử

Read model v1 có lỗi làm thiếu các shipment được tạo tuần trước. Kafka topic chỉ giữ message trong 3 ngày. Hãy xây phương án backfill hoặc snapshot, nêu cách xử lý sự kiện mới phát trong lúc backfill.

### Bài E: quyền truy cập

OrderDetailProjection chứa địa chỉ giao hàng. API chỉ kiểm tra user đã login. Vì sao user CUS-99 có thể xem đơn CUS-17 nếu biết orderId? Hãy thêm kiểm tra authorization theo customer/tenant và policy hiển thị field.

### Bài F: đổi event schema

OrderPlaced thêm field currency trong khi lịch sử có message không chứa field đó. Những giả định nào phải được xác minh trước khi đặt default VND? Projector mới phải đọc old/new events ra sao?

### Bài G: projector v2

Tạo projection mới tối ưu cho full-text search nhưng không muốn ngừng API chi tiết đơn hiện tại. Hãy trình bày kiến trúc dual read model, backfill, catch-up, cutover và rollback window.

### Bài H: tăng số consumer

Một Kafka topic có 4 partitions, consumer group của projection hiện có 8 instances nhưng throughput không tăng như dự tính. Hãy giải thích giới hạn partition assignment và cách đánh giá bottleneck ở DB, batch size, serialization và consumer processing.

### Bài I: state machine

OrderCancelled(version=5) được xử lý trước OrderConfirmed(version=4). Hãy thiết kế condition để projection không lùi trạng thái, đồng thời giải thích nguy cơ bỏ mất dữ liệu nền nếu chỉ nhìn version.

### Bài J: UX khi lag

Khách thanh toán thành công nhưng read model còn paymentStatus=PENDING trong 20 giây. Thiết kế UX “đang xác nhận” và endpoint tra cứu/notify an toàn, tránh yêu cầu khách thanh toán lại.

## 33. Câu hỏi tự kiểm tra

1. Read model khác write model về trách nhiệm và tổ chức dữ liệu thế nào?
2. Projection từ events có bắt buộc Event Sourcing không?
3. CQRS có luôn cần database và service tách biệt không?
4. API Composition phù hợp trong trường hợp nào?
5. Vì sao việc JOIN trực tiếp database private của nhiều services thường nguy hiểm?
6. Khi producer commit DB rồi crash trước khi phát event, Outbox giải quyết gì?
7. Vì sao Outbox không thay thế idempotent consumer?
8. Nên ack offset Kafka trước hay sau khi commit projection?
9. Một event PaymentSucceeded đến hai lần có được cộng tiền hai lần không?
10. Tại sao không có global order mặc định giữa Ordering và Payments topics?
11. Per-aggregate version có thể bảo vệ điều gì và còn giới hạn gì?
12. Có thể dùng occurredAt từ hai service làm causal ordering tuyệt đối không?
13. Một read model query 200 OK có chứng minh nó đã đồng bộ mới nhất không?
14. Consumer lag bằng 0 có đồng nghĩa projection không có dữ liệu sai không?
15. Khi rebuild, tại sao phải biết event retention và schema lịch sử?
16. Khi xóa PII khỏi nguồn, tại sao cần xem cả projection và event archive?
17. Khi user vừa tạo đơn nhưng read model chưa thấy, UI nên làm gì?
18. Có nên dùng paymentStatus trong projection để quyết định refund hay không?
19. Vì sao một projection phải có ownership và monitoring riêng?
20. Khi nào một SQL materialized view cục bộ là đủ, không cần event broker?

## 34. Kết luận

**Read model riêng** cho phép ứng dụng truy vấn dữ liệu đã được tổ chức theo nhu cầu đọc, thay vì luôn fan-out qua nhiều Microservices hoặc đọc thẳng các database private. **Projection từ events** giúp cập nhật read model bằng những sự thật nghiệp vụ mà các context nguồn công bố, trong khi mỗi context vẫn sở hữu dữ liệu và invariant của mình.

Đổi lại, hệ thống phải thiết kế rõ **eventual consistency, idempotency, out-of-order handling, source version, replay, bootstrap, rebuild, freshness SLO, bảo mật và phân quyền**. Read model là một bản sao phục vụ đọc; không phải nguồn sự thật để quyết định thanh toán, tồn kho hay quyền thay đổi nghiệp vụ.

Lựa chọn phù hợp không phải “mọi truy vấn đều cần CQRS”, mà là: xác định trải nghiệm người dùng và độ tươi dữ liệu cần thiết, đánh giá fan-out/dependency, rồi chọn mức tách đọc–ghi đủ đáp ứng yêu cầu. Khi được xây dựng đúng, projection giúp giảm coupling lúc đọc, cải thiện khả năng mở rộng và tạo đường truy vấn ổn định mà vẫn giữ trách nhiệm nghiệp vụ ở đúng dịch vụ.
