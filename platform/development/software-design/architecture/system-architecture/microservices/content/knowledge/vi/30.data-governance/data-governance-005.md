# Tách luồng phân tích và nền tảng dữ liệu khỏi cơ sở dữ liệu giao dịch

## 1. Mục tiêu

Một ứng dụng thương mại điện tử sử dụng cơ sở dữ liệu giao dịch để tạo đơn hàng, cập nhật tồn kho, thanh toán và truy vấn trạng thái hiện tại. Đồng thời, doanh nghiệp muốn lập báo cáo doanh thu theo năm, phân tích hành vi mua hàng, so sánh chiến dịch marketing và huấn luyện mô hình dự báo.

Nếu cả truy vấn giao dịch lẫn truy vấn phân tích đều chạy trên cùng database production, hệ thống rất dễ gặp xung đột tài nguyên: truy vấn tổng hợp quét hàng triệu dòng có thể làm tăng I/O, CPU, bộ nhớ, thời gian giữ transaction và độ trễ của những request quan trọng đối với người dùng.

**Tách luồng phân tích và nền tảng dữ liệu khỏi cơ sở dữ liệu giao dịch** là thiết kế duy trì một hệ thống **OLTP** phục vụ giao dịch, sau đó chuyển dữ liệu cần thiết sang các thành phần **OLAP** để phân tích mà không bắt truy vấn phân tích nặng cạnh tranh trực tiếp với giao dịch.

Mục tiêu không chỉ là tăng tốc báo cáo. Kiến trúc đúng phải bảo vệ **tính toàn vẹn dữ liệu, quyền sở hữu nghiệp vụ, độ tin cậy của giao dịch, độ mới dữ liệu, bảo mật và khả năng vận hành**.

Sau bài này, người đọc có thể:

- Phân biệt yêu cầu OLTP và OLAP về truy vấn, dữ liệu, độ trễ, consistency và workload.
- Giải thích vì sao chạy báo cáo nặng trực tiếp trên transactional database gây nguy cơ.
- So sánh read replica, ETL theo lô, CDC, transactional outbox và event streaming.
- Thiết kế pipeline đưa dữ liệu từ hệ thống giao dịch đến warehouse/lakehouse/analytics serving.
- Hiểu delivery semantics: at-least-once, deduplication, idempotency, ordering, snapshot và replay.
- Lựa chọn freshness, data quality SLI/SLO và reconciliation thay vì giả định luôn nhất quán tức thời.
- Thiết kế data contracts, schema evolution, lineage, access control và chính sách dữ liệu cá nhân.
- Đặt ranh giới service ownership để không biến kho phân tích thành đường truy cập tắt vào logic nghiệp vụ.
- Xây dựng quy trình kiểm thử, theo dõi, khôi phục và backfill an toàn.

## 2. Ví dụ: Checkout bị chậm vì báo cáo doanh thu

Giả sử hệ thống có các bảng orders, order_items, payments, refunds và inventory trong PostgreSQL phục vụ ứng dụng Checkout.

Ban ngày các request:

~~~text
POST /orders               -> INSERT orders, order_items
POST /payments/authorize   -> UPDATE payment state
GET /orders/{id}           -> SELECT theo khóa và tenant
POST /inventory/reserve    -> UPDATE tồn kho trong transaction
~~~

Một báo cáo phân tích chạy cùng lúc:

~~~sql
SELECT date_trunc('month', o.created_at) AS month,
       SUM(oi.quantity * oi.unit_price) AS gross_sales
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.created_at >= TIMESTAMP '2025-01-01'
GROUP BY date_trunc('month', o.created_at)
ORDER BY month;
~~~

Khi dữ liệu lớn, báo cáo có thể quét nhiều trang dữ liệu, tiêu tốn CPU, memory, I/O và cache của database. Nó còn có thể cạnh tranh với các transaction quan trọng, đặc biệt nếu có thêm joins, temp files, lock hoặc các truy vấn dài.

Tác động không phải lúc nào cũng là SQL báo cáo khóa trực tiếp INSERT. Dù một MVCC database cho phép nhiều SELECT và WRITE cùng tồn tại, **cạnh tranh tài nguyên** vẫn có thể làm p95/p99 checkout tăng; transaction dài cũng có thể ảnh hưởng cơ chế vacuum/cleanup hoặc replication lag tùy hệ quản trị.

Giải pháp khái quát:

~~~text
Checkout / Payment / Inventory
          |
          v
Transactional Database (OLTP) -----> Change stream / ETL
         nguồn sự thật                        |
                                              v
                                     Data platform (OLAP)
                                              |
                                   +----------+----------+
                                   |          |          |
                               Dashboard    BI/SQL    ML/Forecast
~~~

Báo cáo không còn quét database giao dịch trực tiếp. Dữ liệu phân tích có thể trễ vài giây/phút theo hợp đồng đã công bố; hành động cần kết quả tài chính tức thời vẫn sử dụng nguồn sự thật có quyền sở hữu phù hợp.

## 3. Phân biệt OLTP và OLAP

| Thuộc tính | OLTP — giao dịch | OLAP — phân tích |
|---|---|---|
| Mục đích | Ghi/đọc trạng thái nghiệp vụ hiện tại | Tìm xu hướng, tổng hợp, lịch sử |
| Đơn vị truy vấn | Một order, một payment, một user | Hàng triệu event/order theo khoảng thời gian |
| Kiểu thao tác | CRUD ngắn, transaction ACID | Scan, join, aggregation, window function |
| Độ trễ mong muốn | Thường mili giây đến thấp giây | Tùy BI, giây đến phút hoặc batch |
| Consistency | Quy tắc nghiệp vụ cần chính xác | Có thể chấp nhận eventual consistency có kiểm soát |
| Tối ưu lưu trữ | Index phục vụ lookup/update | Columnar, partition, aggregate, lịch sử |
| Thay đổi schema | Gắn với contract của service | Gắn với data model và backward compatibility |
| Quyền sở hữu | Service sở hữu dữ liệu và hành vi | Data platform quản lý bản sao phục vụ phân tích |
| Failure handling | Transaction commit/rollback | Replay, dedup, backfill, reconciliation |
| Tải | Request tương tác, số lượng lớn, ngắn | Truy vấn ad hoc, đọc rộng, tài nguyên lớn |

Không có quy tắc "OLTP không bao giờ được aggregate" hay "OLAP không bao giờ cập nhật". Vấn đề là **tách các workload có đặc tính và SLO khác nhau**, để chúng không làm hỏng nhau.

Một số dữ liệu tổng hợp nhỏ, yêu cầu nhất quán tức thì, vẫn có thể được duy trì trong service giao dịch bằng materialized counter hoặc một read model riêng có hợp đồng rõ ràng. Không nhất thiết đưa mọi câu hỏi nghiệp vụ qua warehouse.

## 4. Ranh giới quan trọng: nguồn sự thật và bản sao phân tích

Một thiết kế cần chỉ rõ **system of record** cho từng thực thể nghiệp vụ:

- Order Service sở hữu vòng đời đơn hàng.
- Payment Service sở hữu trạng thái thanh toán.
- Inventory Service sở hữu logic giữ và trừ tồn kho.
- Customer Service sở hữu hồ sơ khách hàng và các quy tắc truy cập.
- Analytics Platform tạo bản sao/diễn giải phục vụ câu hỏi phân tích.

Các bản sao phân tích **không được coi là nguồn ra quyết định nghiệp vụ có tính ràng buộc mạnh** nếu chưa có contract cho phép. Ví dụ một Payment Service không nên hỏi warehouse "đơn hàng đã thanh toán chưa?" khi đang quyết định hoàn tiền theo thời gian thực. Dữ liệu warehouse có thể đang trễ, bị lọc hoặc đang backfill.

Điều này tạo một ranh giới kiến trúc:

~~~text
Command: "Hủy đơn hàng 123" 
    -> Order Service API/command
    -> Kiểm tra trạng thái, quyền, invariant
    -> Transactional DB của Order Service

Query: "Doanh thu tháng này theo khu vực?"
    -> Analytics API / BI dataset
    -> Warehouse/lakehouse
    -> Báo cáo có data freshness rõ ràng
~~~

Trong một số hệ thống CQRS, read model dùng cho ứng dụng cũng có thể được xây từ event stream. Nhưng **command side** vẫn cần kiểm tra các invariant quan trọng theo mô hình consistency đã thiết kế, không dựa bừa trên một projection trễ.

## 5. Sơ đồ kiến trúc mục tiêu

Một kiến trúc điển hình:

~~~text
       +-------------------------+
       |  API / Business Service |
       +------------+------------+
                    |
                    v
       +-------------------------+
       |  OLTP Database          |
       |  orders / payments      |
       +------------+------------+
                    |
            transaction log
                    |
                    v
       +-------------------------+
       | CDC Connector / Outbox  |
       +------------+------------+
                    |
                    v
       +-------------------------+
       | Event Broker / Stream   |
       | topic, partition, retry |
       +------------+------------+
                    |
          +---------+------------+
          |                      |
          v                      v
 +-----------------+    +------------------------+
 | Raw/Landing     |    | Operational Read Model |
 | Object Storage  |    | Search/near-real-time  |
 +--------+--------+    +------------------------+
          |
          v
 +------------------------------+
 | Data Processing / Validation |
 | Dedup, normalize, enrich     |
 +---------------+--------------+
                 |
                 v
 +------------------------------+
 | Warehouse / Lakehouse / OLAP |
 | Facts, dimensions, snapshots |
 +---------------+--------------+
                 |
          +------+-------+-----------------+
          |              |                 |
          v              v                 v
      BI Reports     Analytics API      ML/Forecast
~~~

Không phải hệ thống nào cũng cần đủ mọi thành phần. Một dự án nhỏ có thể bắt đầu bằng batch ETL sang warehouse. Một hệ thống cần near-real-time analytics và nhiều consumers có thể cần CDC + broker + streaming processor.

Quan trọng là **cách dữ liệu rời OLTP không đe dọa giao dịch**, và cách bản sao được kiểm chứng/khôi phục phải rõ ràng.

## 6. Lựa chọn cách lấy dữ liệu ra khỏi OLTP

Có nhiều cách; không có công thức duy nhất.

| Cách tiếp cận | Độ mới điển hình | Ưu điểm | Hạn chế/rủi ro |
|---|---|---|---|
| Query trực tiếp OLTP | Gần thời gian thực | Đơn giản lúc đầu | Cạnh tranh tải và coupling |
| Read replica | Trễ replication | Cô lập phần read | Lag, cùng schema, truy vấn OLAP vẫn có thể nặng |
| Batch ETL/ELT | Phút/giờ/ngày | Dễ kiểm soát và phục hồi | Tính mới thấp, query trích xuất có thể nặng |
| CDC từ transaction log | Giây tới phút tùy pipeline | Bắt thay đổi ít cần polling bảng | Quản lý snapshot, WAL/binlog, schema, retention |
| Transactional outbox + relay | Giây tới phút tùy relay | Gắn sự kiện nghiệp vụ với transaction | Outbox cleanup, retry, idempotency |
| Domain event trực tiếp | Tùy thiết kế | Nhiều consumers, semantics rõ | Dual-write nếu không phối hợp transaction |
| Streaming + materialized views | Gần thời gian thực có kiểm soát | Tổng hợp nhanh, incremental | Vận hành state, ordering, reprocessing |

Trễ nói trên chỉ là phạm vi thường gặp, **không phải cam kết**. CDC cũng có thể trễ hàng giờ khi broker/connector nghẽn hoặc snapshot lớn; batch có thể chạy nhiều lần mỗi phút nếu chi phí cho phép.

### 6.1. Bắt đầu từ SLO, không bắt đầu từ công cụ

Câu hỏi "báo cáo phải cập nhật sau bao lâu?" quyết định khá nhiều kiến trúc:

- Báo cáo tài chính chốt theo ngày: batch có thể đủ.
- Dashboard vận hành doanh số cập nhật trong 5 phút: micro-batch hoặc CDC phù hợp.
- Phát hiện gian lận trong vài trăm mili giây: cần pipeline/decision system chuyên biệt; không nên giả định warehouse đáp ứng đúng latency/consistency.
- Tìm kiếm sản phẩm với indexing trễ vài giây: projection/search index từ event có thể phù hợp.
- Kiểm tra số dư hay tồn kho khi commit giao dịch: nên hỏi service nguồn theo hợp đồng consistency, không dùng BI store.

## 7. Read replica: giải pháp hữu ích nhưng chưa phải nền tảng phân tích

Read replica sao chép dữ liệu từ primary database đến một instance khác để phục vụ truy vấn đọc.

~~~text
OLTP Primary (writes)
       |
       +----> Replica A (application reads)
       |
       +----> Replica B (report queries)
~~~

Lợi ích:

- Tách một phần CPU/I/O của SELECT khỏi primary.
- Có thể giảm tác động của reporting workload lên request ghi.
- Ít thay đổi application data model lúc đầu.
- Đôi khi là giai đoạn trung gian trước khi xây data platform.

Giới hạn:

- Replica vẫn dùng cấu trúc bảng giao dịch, chưa tối ưu cho scans/aggregates.
- Replication lag khiến dữ liệu không nhất quán tức thời.
- Long-running queries có thể cạnh tranh trên replica hoặc gây tác động tùy replication mechanism.
- Replication/network/storage vẫn tiêu tài nguyên và chi phí.
- Một số truy vấn report yêu cầu reshape nhiều bảng, cần data model phân tích.
- Sự cố cấu hình, failover hoặc replica catch-up có thể khiến báo cáo mất ổn định.
- Nếu report dùng chung replica với critical application reads, xung đột workload vẫn tồn tại.

Nếu dùng replica làm nguồn extraction, cần kiểm tra cách đọc snapshot nhất quán, replication delay, retention và tác động lên primary. **Read replica phù hợp để giảm tải đọc trong phạm vi nhất định, nhưng không tự thay thế warehouse/lakehouse và quản trị dữ liệu.**

## 8. ETL và ELT theo lô

### 8.1. ETL

Extract dữ liệu từ nguồn, Transform trước khi nạp, Load vào kho đích.

~~~text
OLTP -> Extract -> Clean/Transform -> Warehouse
~~~

Phù hợp khi:

- Batch chạy theo giờ/ngày được chấp nhận.
- Có yêu cầu làm sạch và kiểm tra trước khi dữ liệu xuất hiện trong đích.
- Khối lượng và nguồn dữ liệu có thể kiểm soát.
- Không cần sự kiện từng thay đổi gần thời gian thực.

### 8.2. ELT

Extract, Load dữ liệu thô có quản trị vào nền tảng phân tích, rồi Transform tại đó.

~~~text
OLTP -> Extract -> Raw/Staging -> Transform in Warehouse
~~~

Lợi ích là giữ raw records phục vụ replay, nhiều kiểu phân tích và sử dụng engine OLAP cho phép biến đổi dữ liệu. Nhưng raw zone phải kiểm soát phân quyền, PII, retention và lineage; "đưa tất cả dữ liệu thô vào data lake" không mặc định an toàn.

### 8.3. Incremental batch extraction

Tránh quét toàn bảng mỗi đêm nếu chỉ có một phần dữ liệu thay đổi. Một cách đơn giản là incremental theo updated_at hoặc ID.

Ví dụ:

~~~sql
SELECT id, customer_id, status, total_amount, updated_at
FROM orders
WHERE updated_at >= :last_watermark
  AND updated_at < :this_watermark;
~~~

Cần biết rủi ro:

- updated_at phải được cập nhật chính xác với mọi thay đổi có ý nghĩa.
- Hai transaction có cùng timestamp, lệch đồng hồ hoặc commit trễ có thể khiến watermark bỏ sót.
- Deletes không hiện trong truy vấn trừ khi có soft delete hoặc cơ chế riêng.
- Late-arriving changes cần overlap window và dedup.
- Query trích xuất vẫn có thể làm tăng tải OLTP nếu thiếu index hoặc chạy quá thường xuyên.

Khi cần độ chính xác và khả năng replay cao, CDC thường đáng cân nhắc hơn polling updated_at.

### 8.4. Snapshot nhất quán

Nếu extract orders và order_items trong hai query độc lập ở hai thời điểm khác nhau, dữ liệu có thể mô tả một trạng thái chưa từng tồn tại. Ví dụ đơn đã được thêm nhưng order_items chưa được đọc hoặc bị cập nhật trong lúc batch chạy.

Có thể dùng transaction isolation/snapshot phù hợp, export snapshot được hỗ trợ hoặc pipeline incremental hợp nhất tại một mốc nhất quán. Không giữ transaction snapshot quá lâu trên OLTP nếu cơ chế đó gây ảnh hưởng tới cleanup hoặc tài nguyên.

## 9. Change Data Capture (CDC)

**CDC** là kỹ thuật thu nhận các thay đổi INSERT/UPDATE/DELETE từ nguồn, thường bằng database transaction log như WAL hoặc binlog, thay vì liên tục SELECT toàn bảng.

Một luồng khái niệm:

~~~text
Order Service transaction
       |
       v
OLTP commit
       |
       v
WAL / binlog
       |
       v
CDC connector
       |
       v
Change records -> Broker -> Consumers -> Analytics
~~~

Bản ghi change có thể gồm operation type, before/after fields, source table, transaction metadata và vị trí log tùy công cụ.

Ví dụ minh họa:

~~~json
{
  "source": "order-db",
  "table": "orders",
  "operation": "UPDATE",
  "primary_key": 90021,
  "before": {
    "status": "CREATED"
  },
  "after": {
    "status": "PAID"
  },
  "commit_timestamp": "2026-11-12T07:20:05Z",
  "source_position": "example-log-position"
}
~~~

Các trường trên là dữ liệu mẫu, không phải một schema CDC chuẩn áp dụng cho mọi connector. Một số hệ thống không cung cấp đầy đủ before image hoặc timestamp; cần đọc hợp đồng connector đang dùng.

### 9.1. Điểm mạnh

- Theo dõi thay đổi có tính incremental.
- Tránh phải liên tục quét bảng lớn.
- Bắt deletes và updates tốt hơn một số mô hình polling.
- Có thể cấp dữ liệu cho nhiều consumers.
- Dữ liệu raw có thể lưu để replay/backfill hoặc auditing phù hợp.

### 9.2. Rủi ro vận hành

- Connector bị dừng lâu có thể mất vị trí đọc nếu transaction log đã bị xóa.
- Giữ WAL/binlog quá lâu có thể làm đầy storage primary.
- Schema changes có thể làm connector/sink lỗi.
- Snapshot ban đầu và stream tiếp theo phải ghép đúng để không mất/trùng record.
- Transaction có nhiều table changes cần hiểu ordering và commit boundaries.
- Thay đổi physical schema không tự mang nghĩa nghiệp vụ.
- Delete events và dữ liệu cá nhân cần được xử lý tại sinks.

Đo connector lag, log retention, queue backlog, số records processed/dropped và tốc độ recover, không chỉ xem trạng thái process "RUNNING".

## 10. CDC không đồng nghĩa domain events

Một database change cho biết cột orders.status đổi từ CREATED sang PAID. Nó không nhất thiết cho biết **vì sao** đổi, hợp đồng nghiệp vụ nào vừa hoàn tất, đã có idempotency hay transaction nào liên quan.

So sánh:

~~~text
CDC row change:
  orders.status: CREATED -> PAID

Domain event:
  PaymentCaptured
  orderId=90021
  paymentId=50771
  amount=125000
  currency=VND
  occurredAt=...
  schemaVersion=2
~~~

Domain event có ngữ nghĩa nghiệp vụ được service sở hữu công bố, thuận lợi để consumers lập mô hình. Nhưng phát event trực tiếp cùng một transaction tạo bài toán **dual-write**.

Nếu service commit DB thành công rồi publish event thất bại, warehouse có thể không bao giờ nhận thay đổi. Nếu publish trước commit rồi transaction rollback, consumer nhận sự kiện không tương ứng với trạng thái đã commit.

Đây là lý do cần phân biệt hai việc:

- Thu data changes từ CDC theo schema vật lý.
- Công bố business events một cách đáng tin cậy, thường thông qua outbox hoặc một cơ chế phối hợp tương đương.

## 11. Transactional Outbox: tránh dual-write

**Transactional outbox** lưu business state và event cần phát trong **cùng một database transaction**.

~~~text
Order Service
  |
  | DB transaction:
  |   UPDATE orders
  |   INSERT outbox_events
  |
  v
COMMIT
  |
  v
Outbox relay / CDC
  |
  v
Broker topic
  |
  v
Analytics consumer
~~~

Khi transaction commit, cả order state và outbox event cùng tồn tại. Nếu rollback, cả hai cùng rollback. Relay có thể đọc outbox bằng CDC hoặc polling và phát event ra broker.

Điều này giải quyết vấn đề **mất event do hai lần ghi không nguyên tử** ở phía producer. Tuy nhiên nó **không tự bảo đảm exactly-once end-to-end**: relay có thể phát event rồi crash trước khi ghi nhận đã phát, khiến event được gửi lại. Consumer vẫn phải idempotent.

### 11.1. Ví dụ schema outbox

~~~sql
CREATE TABLE outbox_events (
    event_id          UUID PRIMARY KEY,
    aggregate_type    VARCHAR(100) NOT NULL,
    aggregate_id      VARCHAR(100) NOT NULL,
    event_type        VARCHAR(100) NOT NULL,
    schema_version    INTEGER NOT NULL,
    payload_json      JSONB NOT NULL,
    occurred_at       TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_outbox_aggregate
    ON outbox_events (aggregate_type, aggregate_id, occurred_at);
~~~

DDL trên là ví dụ PostgreSQL. Trong production, cần tính chiến lược retention/cleanup, indexing, partitioning, PII, kích thước payload, rate và schema của relay. Không tạo index trên mọi cột chỉ để tiện truy vấn; outbox table có thể phát sinh write volume cao.

### 11.2. Ghi business state và event cùng transaction

Pseudocode Java/Spring:

~~~java
@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void markPaid(UUID orderId, UUID paymentId) {
        Order order = orders.findByIdForUpdate(orderId);
        order.markPaid(paymentId);
        orders.save(order);

        OutboxEvent event = OutboxEvent.of(
            UUID.randomUUID(),
            "Order",
            orderId.toString(),
            "OrderPaid",
            1,
            OrderPaidPayload.from(order, paymentId)
        );
        outbox.save(event);
    }
}
~~~

Các type và method trong ví dụ là domain-specific placeholders, cần được implement đúng theo Spring/JPA đang dùng. Điều quan trọng là **hai thao tác database được thực hiện trong cùng transaction**. Relay không nằm trong transaction HTTP này: nó sẽ phát sau commit.

Nếu payment có trạng thái phức tạp, method markPaid phải xử lý idempotency và invariant theo domain; không chỉ dựa vào outbox để ngăn thanh toán trùng.

### 11.3. Polling relay và CDC relay

**Polling relay** thường SELECT event chưa gửi theo batch, lock/claim row, publish rồi đánh dấu trạng thái. Cần xử lý crash, multiple workers, retry và tránh giữ DB transaction mở trong lúc đợi network quá lâu.

**CDC relay** đọc INSERT outbox từ transaction log rồi phát ra broker. Nó giảm nhu cầu polling bảng nhưng đòi hỏi vận hành CDC connector và log retention.

Dù chọn cách nào, event_id phải ổn định qua retry để consumer nhận biết duplicate. Cleanup outbox chỉ diễn ra khi xác định dữ liệu đã được bảo toàn/retained theo chính sách pipeline, không xóa mù ngay sau một lần publish thành công.

## 12. At-least-once, duplicate và idempotency

Trong pipeline phân tán, consumer có thể thấy cùng một event nhiều lần:

~~~text
Consumer nhận event E1
    |
    v
Ghi analytics table thành công
    |
    v
Crash trước khi commit offset/ack
    |
    v
Broker gửi lại E1
~~~

Nếu consumer thực hiện INSERT cộng doanh thu mỗi lần, một đơn hàng có thể bị tính hai lần.

**At-least-once** là mô hình thực tế phổ biến: event không bị bỏ qua khi retry phù hợp, nhưng có thể bị giao lặp. Vì thế cần một trong các chiến lược:

- Upsert theo business primary key và source version.
- Dedupe theo event_id đã ghi nhận.
- Merge theo CDC log position hoặc sequence number.
- Tính aggregate từ trạng thái bảng đã hợp nhất, không cộng một event tuỳ tiện.
- Checkpoint/commit offset phối hợp với transactional sink nếu nền tảng hỗ trợ.

### 12.1. Ví dụ bảng đã xử lý event

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Một consumer ghi marker và kết quả trong cùng transaction của database đích có thể kiểm tra trùng trước khi áp side effect. Nếu sink là warehouse không hỗ trợ transaction theo cùng nghĩa, dùng MERGE/append+dedup hoặc khả năng exactly-once/sink transactions đã được xác minh của platform.

**Không tuyên bố exactly-once end-to-end** chỉ vì broker hoặc stream processor quảng bá exactly-once processing. Cần xem cả source, broker, state store, sink, external calls và semantics reprocessing.

### 12.2. Idempotent upsert

Ví dụ trong bảng analytics_current_orders, mỗi order có một source version tăng đơn điệu. Consumer chỉ cập nhật khi event đến có version mới hơn:

~~~sql
INSERT INTO analytics_current_orders
    (order_id, status, total_amount, source_version, updated_at)
VALUES
    (:order_id, :status, :amount, :version, :updated_at)
ON CONFLICT (order_id) DO UPDATE
SET status = EXCLUDED.status,
    total_amount = EXCLUDED.total_amount,
    source_version = EXCLUDED.source_version,
    updated_at = EXCLUDED.updated_at
WHERE analytics_current_orders.source_version
    < EXCLUDED.source_version;
~~~

Cú pháp minh họa cho PostgreSQL làm read model; mỗi warehouse có cú pháp MERGE/upsert khác. Dùng source version có tính **đơn điệu trên từng aggregate** và được quản lý đúng. Một timestamp đồng hồ không luôn thay thế được sequence/version do event có thể đến muộn hoặc clock lệch.

## 13. Ordering, partition và sự kiện đến muộn

Một đơn hàng có thể phát các event:

~~~text
OrderCreated  -> OrderPaid -> OrderCancelled -> RefundIssued
       v1            v2            v3              v4
~~~

Nếu các event tới consumer theo thứ tự v1, v3, v2, v4, áp dụng trạng thái theo thứ tự nhận có thể đưa order trở lại PAID sau khi đã CANCELLED.

Cách xử lý:

- Dùng aggregate_id làm partition key để giữ thứ tự trong phạm vi một partition khi broker/producer semantics cho phép.
- Gắn source version hoặc sequence number cho từng aggregate.
- Chỉ chấp nhận event mới hơn version hiện tại.
- Có cơ chế xử lý gap (nhận v4 khi thiếu v3) nếu invariant cần đủ chuỗi.
- Tách event-time và processing-time cho analytical windows.
- Cho phép late arrival/retractions ở các phép tính thống kê.
- Thiết kế backfill/replay không phá dữ liệu đã cập nhật.

Thứ tự trong cùng một Kafka partition không tự tạo thứ tự toàn cục giữa nhiều partition, database hay service. Nếu một báo cáo phụ thuộc vào thứ tự giữa Payment và Order từ hai service, cần mô hình join/correlation và semantics rõ, không dựa vào timestamp đơn thuần.

## 14. Initial snapshot và chuyển sang CDC liên tục

Khi lần đầu xây data warehouse, cần chuyển dữ liệu lịch sử hàng triệu record rồi tiếp tục nhận thay đổi mới. Đây là chỗ dễ tạo khoảng trống hoặc trùng:

~~~text
T0: bắt đầu snapshot 100 triệu orders
T1: user cập nhật order A
T2: snapshot đọc order A
T3: CDC stream phát thay đổi của order A
~~~

Nếu không có thuật toán phối hợp snapshot với log position, sink có thể áp bản cũ sau bản mới, tính trùng hoặc bỏ sót cập nhật.

Một quy trình có kiểm soát:

1. Xác định snapshot consistent point hoặc low/high watermark theo connector.
2. Ghi lại log position/tokens cần thiết để tiếp tục stream.
3. Copy dữ liệu ban đầu theo batch có giới hạn tải.
4. Duy trì capture changes trong lúc snapshot.
5. Merge snapshot và CDC events bằng primary key/version/position.
6. Kiểm tra counts, checksums và một số invariant.
7. Chỉ chuyển báo cáo chính thức sang pipeline mới khi reconciliation đạt tiêu chí.
8. Theo dõi freshness và gaps sau cutover.

Thứ tự thực hiện phụ thuộc CDC tool và database; nhiều connector đã cung cấp initial snapshot semantics. Không tự viết một thuật toán snapshot đơn giản dựa vào updated_at rồi mặc định không mất dữ liệu.

## 15. Backfill và replay an toàn

**Backfill** lấp dữ liệu lịch sử chưa có hoặc tính lại một dataset sau khi sửa logic.

**Replay** chạy lại chuỗi change/events từ một vị trí hoặc một khoảng thời gian.

Cả hai đều quan trọng trong data platform. Khi sửa quy tắc tính doanh thu, chỉ sửa pipeline từ hôm nay trở đi sẽ khiến dữ liệu năm trước mang định nghĩa cũ.

Một kế hoạch backfill tốt cần:

- Chỉ rõ phạm vi thời gian, bảng, key và business semantics.
- Dữ liệu nguồn có còn đầy đủ theo retention không?
- Có partition đích riêng hoặc dataset tạm để tính lại?
- Có version của transformation logic và schema đích?
- Có giới hạn tài nguyên/cost và khả năng pause/resume?
- Dedupe/idempotency khi chạy lại?
- So sánh số dòng, tổng tiền, sample records và invariants trước cutover?
- Có kế hoạch rollback của **data projection**, khác với rollback service code?
- Có cách gắn nhãn dataset "đang backfill" để tránh người dùng hiểu sai?
- Có audit về ai khởi chạy, khi nào, logic nào và bằng chứng hoàn tất?

Đừng xóa bảng analytics production rồi tính lại toàn bộ ngay tại chỗ nếu dashboard đang dùng nó. Có thể xây dataset phiên bản mới, kiểm thử rồi **atomic swap/alias switch** nếu engine hỗ trợ và cách làm an toàn.

## 16. Chọn nền tảng đích: warehouse, lake, lakehouse và specialized stores

### 16.1. Data warehouse

Thường tối ưu cho SQL analytical queries, reporting, aggregates và BI. Có thể có lưu trữ dạng cột, engine thực thi song song và quản lý workload/query isolation.

Phù hợp cho: doanh thu theo tháng, cohort analysis, funnel, tài chính, dashboard và data marts. Cần tính query cost, partition/clustering, schema/data model và quyền truy cập.

### 16.2. Data lake

Lưu dữ liệu thô hoặc bán cấu trúc trên object storage, thuận tiện giữ lịch sử, nhiều định dạng và nhiều nhóm processing. Nhưng "một bucket lưu JSON" chưa tự thành data platform quản trị tốt. Cần catalog, schema, partitioning, access policy, retention, chất lượng và khả năng quản lý versions.

### 16.3. Lakehouse

Kết hợp object storage với table format/metadata layer hỗ trợ các thao tác bảng có quản trị, thường gồm snapshot, schema evolution hoặc transaction semantics tùy platform. Hữu ích khi vừa cần phân tích SQL vừa cần dữ liệu cho ML/data science.

### 16.4. Columnar/real-time OLAP stores

Các hệ thống chuyên cho truy vấn tổng hợp nhanh trên luồng dữ liệu mới có thể phù hợp dashboard gần thời gian thực. Chi phí đổi lại là vận hành ingestion, indexing, aggregation rollup và giới hạn truy vấn tùy engine.

### 16.5. Search index là mục tiêu khác

Một search engine có thể nhận projection để full-text search hoặc filtering phục vụ sản phẩm, nhưng không tự phù hợp cho phân tích tài chính đa chiều/phức tạp. Search index thường là **read model** và có freshness/rebuild semantics riêng.

Một tổ chức có thể dùng nhiều đích, nhưng cần tránh gửi mỗi service tới 10 storage engines mà không có ownership, lineage và contract rõ.

## 17. Data modeling cho phân tích

Schema giao dịch thường chuẩn hóa để tránh bất nhất khi cập nhật, ví dụ orders, order_items, payments, refunds tách bảng. Schema phân tích có thể thiết kế thành **facts và dimensions** để phục vụ truy vấn.

Ví dụ star schema:

~~~text
             dim_customer
                  |
                  v
dim_date ---- fact_order_items ---- dim_product
                  |
                  v
             dim_channel
~~~

**Fact** giữ các số đo và foreign keys như quantity, unit_price, discount, net_amount. **Dimension** cung cấp thuộc tính mô tả như sản phẩm, kênh, thời gian, nhóm khách hàng.

Điều cốt lõi là xác định **grain**: một dòng fact biểu diễn cái gì?

- Một đơn hàng?
- Một dòng hàng trong đơn?
- Một payment attempt?
- Một sự kiện refund?
- Một lần xem sản phẩm?

Nếu fact_order_items có grain là từng dòng hàng, cộng SUM(order_total) được join từ order có thể nhân doanh thu theo số item. Phải đo tại đúng grain và có business definition nhất quán.

### 17.1. Doanh thu không chỉ là tổng order.total

Có nhiều khái niệm:

- Gross merchandise value.
- Net sales sau discount/refund.
- Revenue recognized theo chính sách kế toán.
- Payment captured và settlement.
- Tax, shipping fee và currency conversion.
- Order created, paid, fulfilled, cancelled.
- Phân bổ doanh thu theo thời gian event hay ngày hạch toán.

Một bảng analytics có truy vấn chạy rất nhanh nhưng dùng sai định nghĩa doanh thu vẫn là hệ thống dữ liệu kém chất lượng. Data contracts cần định nghĩa metric và owner chịu trách nhiệm.

### 17.2. Slowly Changing Dimensions (SCD)

Nếu khách hàng chuyển vùng hoặc sản phẩm đổi danh mục, báo cáo lịch sử cần biết dùng thuộc tính **hiện tại** hay thuộc tính **tại thời điểm giao dịch**.

SCD Type 1 thường ghi đè giá trị mới; Type 2 lưu lịch sử các phiên bản dimension với valid_from/valid_to và surrogate key. Chọn model dựa trên câu hỏi nghiệp vụ, không phải mặc định Type 2 cho mọi cột.

## 18. Quản trị dữ liệu theo ownership của Microservices

Trong microservice architecture, data ownership tránh việc các service cùng ghi một database hoặc tự đọc bảng nội bộ của nhau. Nền tảng phân tích là bên **nhận dữ liệu có hợp đồng**, không phải một service có quyền ghi ngược vào transaction của đơn hàng.

Ví dụ:

~~~text
Order Service owns:
  orders state transitions
  order totals and invariants
  OrderCreated/OrderPaid/OrderCancelled events

Payment Service owns:
  authorization, capture, refund transitions
  PaymentAuthorized/PaymentCaptured/RefundIssued events

Analytics owns:
  normalized facts, historical snapshots, reports
  data lineage, data quality rules, marts
~~~

Có thể thu dữ liệu qua CDC từ database nội bộ, nhưng nếu schema vật lý thường xuyên đổi, data platform bị coupled rất chặt với service. Lúc đó cân nhắc domain events hoặc versioned CDC contracts để định nghĩa rõ dữ liệu nào được phép xuất.

**Không cấp direct write access vào OLTP cho analytics job.** Mọi thay đổi nghiệp vụ phải đi qua service owner hoặc một cơ chế quản lý được thiết kế rõ.

### 18.1. Data product và data contract

Một nguồn dữ liệu có thể được xem như data product với:

- Tên, domain, owner và contact.
- Schema, version và compatibility rules.
- Semantics của từng field, key và unit.
- Grain, primary key, event type và dedup key.
- Dữ liệu có thể null, late hoặc delete.
- Freshness/availability/quality SLO.
- Tần suất update và backfill/replay behavior.
- PII classification, permissions, retention và usage restrictions.
- Changelog và deprecation policy.

Thay đổi nhỏ trong physical database có thể phá pipeline dù ứng dụng vẫn chạy tốt. Data contracts giúp service producer và data consumers phối hợp trước deploy.

## 19. Schema evolution mà không làm hỏng consumers

Ví dụ event version 1:

~~~json
{
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "orderId": "90021",
  "amount": 125000,
  "currency": "VND"
}
~~~

Version 2 thêm một field optional:

~~~json
{
  "eventType": "OrderPaid",
  "schemaVersion": 2,
  "orderId": "90021",
  "amount": 125000,
  "currency": "VND",
  "paymentMethod": "CARD"
}
~~~

Nếu consumer cũ chấp nhận field thêm và có default hợp lệ, thay đổi có thể backward-compatible. Nhưng đổi amount từ đơn vị đồng sang đơn vị xu hoặc đổi ý nghĩa event là breaking change ngay cả khi type vẫn numeric.

Các nguyên tắc:

1. Version schemas và cập nhật changelog.
2. Thêm field optional trước khi consumer cần nó.
3. Không xóa/đổi nghĩa field khi consumer cũ còn chạy.
4. Tách event mới nếu semantics thay đổi đáng kể.
5. Contract-test producer và consumers.
6. Theo dõi schema compatibility trong pipeline.
7. Xác định cách đọc lịch sử khi backfill qua nhiều versions.
8. Tránh phụ thuộc vào thứ tự field hoặc raw SQL column positions.

Schema registry có thể giúp kiểm tra một số dạng compatibility, nhưng **không tự phát hiện lỗi semantics** như đổi currency scale hay ý nghĩa trạng thái.

## 20. Freshness: dữ liệu có trễ bao lâu?

Một bản phân tích có thể hợp lệ nhưng không mới như người xem nghĩ. Phải công bố độ trễ:

~~~text
T0: Order được commit ở OLTP
T1: CDC đọc transaction log
T2: Event tới broker
T3: Transformation hoàn tất
T4: Warehouse table được cập nhật
T5: Dashboard refresh
~~~

Các thành phần trễ:

- Source capture delay = T1 - T0.
- Transport/queue delay = T2 - T1.
- Processing delay = T3 - T2.
- Load/commit delay = T4 - T3.
- Presentation delay = T5 - T4.
- End-to-end freshness = T5 - T0 theo định nghĩa dữ liệu hiển thị.

Không nhầm **event time**, **commit time**, **ingestion time**, **processing time** và **dashboard refresh time**. Các loại timestamp này có semantics khác nhau; lệch đồng hồ có thể làm timestamp chênh bất hợp lý.

### 20.1. Freshness SLO

Ví dụ SLO tham khảo:

~~~text
99% OrderPaid events xuất hiện trong dataset analytics
trong vòng 5 phút sau commit, đo trên cửa sổ 7 ngày.
~~~

Một SLO phù hợp cần định nghĩa:

- Tập events hợp lệ.
- Thời điểm nguồn để tính.
- Sink nào và thời điểm xem là "đã xuất hiện".
- Cách xử lý duplicate, late arrival và replay.
- Cách đo khi mất telemetry/source event.
- Error budget hoặc số lượng events quá hạn.

Một dashboard đặt nhãn "Realtime" nhưng thực tế dữ liệu cập nhật mỗi 30 phút là gây hiểu nhầm. Nên hiển thị **last successful sync**, **data as-of time** và trạng thái pipeline.

### 20.2. Tươi nhưng chưa đủ

Một stream có thể cập nhật nhanh nhưng bỏ sót deletes hoặc duplicates. Freshness phải đi cùng completeness và correctness. Dữ liệu cập nhật trong 10 giây nhưng thiếu 5% order không đáng tin hơn dữ liệu cập nhật trong 5 phút nhưng đầy đủ, nếu bài toán yêu cầu số liệu tài chính chính xác.

## 21. Data quality: kiểm tra bằng bất biến và đối soát

**Data quality** cần có các chiều:

| Chiều | Câu hỏi |
|---|---|
| Completeness | Đã nhận đủ records/events trong phạm vi định nghĩa? |
| Uniqueness | Có order hoặc event được tính trùng? |
| Validity | Status, currency, amount có hợp lệ? |
| Consistency | Order/payment/refund có khớp logic nghiệp vụ? |
| Timeliness | Độ mới có đạt SLO? |
| Referential integrity | Fact có dimension/key liên quan? |
| Accuracy | Kết quả phản ánh sự thật nghiệp vụ? |
| Lineage | Có biết dữ liệu đến từ đâu và transform nào? |

Ví dụ các kiểm tra:

~~~sql
-- Kiểm tra event_id có bị lặp trong staging
SELECT event_id, COUNT(*) AS cnt
FROM staging_order_events
GROUP BY event_id
HAVING COUNT(*) > 1;

-- Kiểm tra số tiền âm ngoài trạng thái được phép
SELECT order_id, total_amount
FROM analytics_current_orders
WHERE total_amount < 0;

-- Kiểm tra fact trùng business key nếu grain là một dòng/order item
SELECT order_id, item_id, COUNT(*) AS cnt
FROM fact_order_items
GROUP BY order_id, item_id
HAVING COUNT(*) > 1;
~~~

Đây là các truy vấn minh họa; với refund/credit, số âm có thể hợp lệ nếu data model định nghĩa như vậy. Không biến một quy tắc chung thành cảnh báo sai cho mọi domain.

### 21.1. Reconciliation với nguồn giao dịch

Đối soát có thể dùng:

- Count theo khoảng commit time.
- Tổng tiền theo currency và trạng thái.
- Checksums theo partition.
- Số record theo primary key và version.
- Các bất biến nghiệp vụ qua Order/Payment/Refund.
- Sampling các record, cả trường hợp null/late/delete.
- Chênh lệch trong tolerance đã được phê duyệt.

Ví dụ: nếu analytics dùng eventual consistency tối đa 5 phút, so sánh hai bên tại thời điểm hiện tại có thể báo sai lệch bình thường. Phải chọn **watermark/cutoff thống nhất** và chỉ đối chiếu dữ liệu đã qua hạn freshness.

Đừng tự động sửa dữ liệu OLTP từ warehouse khi thấy mismatch. Điều tra source of truth và pipeline, rồi xử lý bằng quy trình có quyền thích hợp.

## 22. Deletes, corrections và quyền xóa dữ liệu

Các pipeline phân tích thường rất giỏi thêm dữ liệu, nhưng dễ quên việc **xóa hoặc sửa** dữ liệu gốc.

Các trường hợp:

- Order bị cancel hoặc refund sau nhiều ngày.
- Giá trị bị sửa theo quy trình correction.
- Customer thay đổi thông tin.
- Data retention hết hạn.
- Yêu cầu xóa dữ liệu cá nhân theo chính sách/pháp luật áp dụng.
- Dữ liệu trước đây được lưu sai cần được redaction.

Nếu dùng append-only raw events, việc xóa một row trong OLTP không có nghĩa tất cả raw files, downstream tables, caches, extracts và backups tự xóa. Cần quản lý deletion propagation hoặc một cơ chế kiểm soát truy cập/phục hồi phù hợp theo chính sách dữ liệu.

Một giải pháp có thể dùng tombstone/delete event, deletion ledger, processing jobs và verification records. Cần xem cả backups, immutable retention và nghĩa vụ pháp lý trước khi hứa xóa tuyệt đối trong một khoảng thời gian.

### 22.1. Auditability và data correction

Khi dữ liệu tài chính bị điều chỉnh, nhiều hệ thống không nên ghi đè lịch sử tùy tiện. Có thể giữ correction/adjustment events và xây metric theo định nghĩa kế toán. Những gì hiển thị trong báo cáo phải có khả năng truy ngược tới giao dịch nguồn và quy tắc biến đổi.

## 23. Data security và quyền truy cập

Tách OLAP khỏi OLTP **không tự làm dữ liệu an toàn hơn**. Warehouse có thể tập trung nhiều dữ liệu nhạy cảm của nhiều service, làm tăng blast radius nếu lộ quyền.

Các lớp kiểm soát cần xem xét:

- Least-privilege service accounts cho CDC, ETL, brokers và sinks.
- Encryption in transit và at rest theo nền tảng.
- Network segmentation, private connectivity và secret management.
- Row/column-level security hoặc phân quyền theo dataset/tenant.
- Tách quyền người phân tích, BI, ML và vận hành pipeline.
- Masking/tokenization/pseudonymization dữ liệu nhạy cảm khi phù hợp.
- Không sao chép mật khẩu, access tokens hoặc full payment card data sang analytics.
- Data classification, retention và quyền xóa.
- Audit quyền đọc/export dữ liệu.
- Kiểm soát dữ liệu khách hàng khi dùng notebooks và exports.
- Quản lý quyền của external data sharing/BI dashboards.
- Chính sách đưa dữ liệu qua biên giới/region nếu áp dụng.

### 23.1. Multi-tenant analytics

Nếu warehouse chứa dữ liệu của nhiều tenant, cần có tenant scoping có thể kiểm chứng tại ingestion, transformation và query/API. Không chỉ tin vào client gửi tenant_id.

Với BI nội bộ, row-level policies có thể thực thi ranh giới truy cập. Với analytics API cho khách hàng, phải có authorization tại service sở hữu hành vi và kiểm thử BOLA/tenant isolation, không dùng tên bảng hoặc SQL query parameter làm lớp bảo vệ duy nhất.

### 23.2. Không chuyển dữ liệu thừa

Phần lớn báo cáo không cần ngày sinh, địa chỉ nhà đầy đủ, token hay toàn bộ lịch sử thay đổi nhạy cảm. Thu dữ liệu tối thiểu theo mục tiêu được phép, thiết kế contract cho những field cần, và tránh đưa cột PII vào raw zone chỉ vì "sau này biết đâu cần".

## 24. Data lineage, catalog và khả năng kiểm toán

Khi dashboard "doanh thu thuần" thay đổi bất thường, cần trả lời:

- Dữ liệu từ những service/table/event nào?
- CDC connector nào đã capture?
- Topic/queue và pipeline nào vận chuyển?
- Transformation version nào tạo bảng fact?
- Data quality tests nào đã chạy?
- Dashboard hiện xem partition nào và as-of timestamp nào?
- Schema nào đã đổi trước khi số liệu biến động?
- Có backfill/replay làm thay đổi lịch sử không?

Một lineage graph:

~~~text
Payment DB / PaymentCaptured
             |
             v
outbox / CDC -> payment-events-v2
             |
             v
raw_payment_events
             |
             v
stg_payments_deduped
             |
             v
fact_payments ---------> mart_daily_revenue
                                 |
                                 v
                        BI Revenue Dashboard
~~~

Lineage giúp xác định phạm vi tác động của lỗi nguồn hoặc biến đổi: nếu field payment.currency đổi nghĩa, có thể liệt kê datasets/reports downstream cần kiểm tra.

Catalog nên ghi owner, description, schema, sample queries, classification, freshness, SLO và documentation links. Không cần triển khai hệ thống data catalog khổng lồ ngay từ đầu; điều quan trọng là metadata có thể tìm và duy trì.

## 25. Cô lập workload và resource governance

Ngay cả trong warehouse, dashboard quan trọng và một truy vấn ad hoc không giới hạn cũng có thể cạnh tranh tài nguyên.

Các biện pháp:

- Tách compute/workload groups khi platform hỗ trợ.
- Query timeout, concurrency limit và admission control.
- Query quotas/cost budgets cho từng nhóm.
- Partition pruning, clustering, materialized aggregates.
- Caching phù hợp với freshness yêu cầu.
- Tách dataset production và thử nghiệm.
- Cấp quyền tạo bảng và chạy truy vấn nặng theo vai trò.
- Monitoring top expensive queries và scan volume.
- Schedule backfill ở khung giờ phù hợp.
- Thực thi schema/quality checks trước khi cho BI dùng dataset mới.

Mục tiêu là **cô lập cả transactional workload khỏi analytics và analytical workloads khỏi nhau**. Tách database không có nghĩa bỏ qua capacity planning và governance.

### 25.1. Partition và clustering

Bảng event lớn có thể partition theo event_date hoặc commit_date; chọn theo các query phổ biến và độ phân bố dữ liệu. Nếu query thường lọc tenant_id, order_id, region hoặc event time, clustering/indexing có thể giúp engine bỏ qua phần dữ liệu không liên quan.

Nhưng partition quá nhỏ hoặc quá nhiều partition cũng tạo overhead metadata và quản lý. Tối ưu theo query profile thực, không tự đặt partition theo mọi cột.

## 26. Dữ liệu streaming và tính toán cửa sổ

Một dashboard cần cập nhật doanh số mỗi phút có thể dùng stream processing:

~~~text
OrderPaid events
       |
       v
Validate + dedupe
       |
       v
Window aggregate (1 phút / 5 phút)
       |
       v
Realtime OLAP / dashboard
~~~

Cần phân biệt:

- **Event time:** thời điểm nghiệp vụ thật sự xảy ra.
- **Processing time:** lúc processor nhận/xử lý event.
- **Watermark:** tín hiệu giới hạn mức độ dữ liệu đến muộn được chờ theo cơ chế engine.
- **Late events:** event đến sau cửa sổ kỳ vọng.
- **Retractions/updates:** điều chỉnh aggregate khi dữ liệu mới/correction xuất hiện.
- **Window type:** tumbling, sliding, session.

Nếu một payment bị hoàn tiền hôm sau, doanh số ngày hôm trước có thể cần điều chỉnh theo business definition. Stream aggregate không tự giải quyết revenue recognition hay cách phân bổ refund.

Với workload lớn, state size, checkpoint duration, backpressure và processing lag là chỉ số vận hành bắt buộc.

## 27. Data pipeline observability

Một pipeline chỉ có trạng thái process "RUNNING" chưa đủ để biết dữ liệu đáng tin.

Các metrics quan trọng:

| Nhóm | Chỉ số |
|---|---|
| Source | CDC source position, log/WAL lag, snapshot progress |
| Transport | Broker throughput, queue depth, consumer lag, retries |
| Processing | Records/sec, duration, exceptions, restart, checkpoint |
| Sink | Batch write latency, failed writes, insert/merge counts |
| Freshness | Source commit to sink visible lag, data as-of time |
| Quality | Duplicate keys, missing required fields, mismatched sums |
| Completeness | Expected/received record counts by watermark |
| Schema | Deserialization failures, incompatible schema events |
| Recovery | Replay duration, backlog drain rate, DLQ age |
| Resource | CPU/memory, I/O, storage, cost per TB/partition |
| Security | Access violations, unexpected exports, PII scan failures |

### 27.1. Alert theo người sử dụng dữ liệu

Ví dụ:

~~~text
Critical:
  99% OrderPaid events phải xuất hiện trong dataset
  trong 5 phút; SLI đang vi phạm nhiều cửa sổ.

Warning:
  CDC connector lag > 2 phút trong 10 phút.
  Broker consumer lag đang tăng.

Data quality:
  Reconciliation giữa Order DB và fact_orders
  tại cutoff đã ổn định lệch quá tolerance.
~~~

Ngưỡng cụ thể phải dựa trên SLO, đặc tính pipeline và số liệu nền. Một connector lag 2 phút chưa chắc là sự cố với báo cáo hằng ngày, nhưng là nghiêm trọng với dashboard yêu cầu 1 phút.

### 27.2. Tracing xuyên pipeline

Có thể truyền correlation ID từ source event qua processing stages, lưu event_id và source position trong logs, dùng trace/span links khi xử lý batch. Không nên giữ một root span mở nhiều ngày cho pipeline batch; có thể dùng traces ngắn theo stage và liên kết qua job ID, run ID và lineage.

## 28. Failure mode: khi tách dữ liệu nhưng hệ thống vẫn lỗi

### 28.1. CDC connector ngừng đọc

Hệ quả: warehouse stale, WAL/binlog retention có nguy cơ tăng, eventual log truncation khiến cần resnapshot.

Ứng phó: alert lag/storage, khôi phục connector theo vị trí đã lưu nếu còn hợp lệ, không tự xóa replication slot hoặc reset offset mù, đối soát sau phục hồi.

### 28.2. Broker có backlog lớn

Hệ quả: thời gian từ commit tới báo cáo tăng; consumers có thể tụt xa retention.

Ứng phó: xem arrival/processing rate, partition skew, consumer saturation, hot keys và sink throughput. Không tăng consumer vượt partition/quota một cách mù quáng.

### 28.3. Schema thay đổi không tương thích

Hệ quả: records vào DLQ, transformation fail, một số partitions ngừng cập nhật.

Ứng phó: tạm dừng rollout, phân loại version, khôi phục contract compatibility hoặc hotfix processor; replay từ vị trí phù hợp sau khi test.

### 28.4. Duplicate events làm doanh thu tăng 2 lần

Hệ quả: dashboard sai dù pipeline không báo lỗi kỹ thuật.

Ứng phó: xác định grain/key, replay logic idempotent, xây dataset correction ở staging, kiểm tra reconciliation rồi publish. Không cộng trừ thủ công trên báo cáo production khi chưa hiểu nguyên nhân.

### 28.5. Late refunds không được áp vào dữ liệu lịch sử

Hệ quả: doanh thu tháng cũ sai sau khi refund phát sinh.

Ứng phó: sửa model event-time và correction semantics, xác định window/retention, backfill có kiểm thử và versioned metrics.

### 28.6. Data warehouse bị outage

Nếu ứng dụng giao dịch không phụ thuộc đồng bộ vào warehouse, Checkout vẫn có thể hoạt động. Đây là lợi ích quan trọng của kiến trúc tách biệt. Pipeline có thể backlog/retry trong giới hạn retention, còn dashboard hiển thị dữ liệu cũ và thông báo sự cố.

Nếu Checkout vẫn gọi warehouse để tính tồn kho tức thời, kiến trúc đã vô tình tạo phụ thuộc đồng bộ và đánh mất tính cô lập.

### 28.7. Backfill làm cạn chi phí hoặc tài nguyên

Một truy vấn backfill quét toàn bộ dataset trong giờ cao điểm có thể làm BI dashboard chậm hoặc vượt ngân sách. Cần resource quotas, concurrency, checkpoint, cost estimation và khả năng pause.

### 28.8. Dữ liệu nhạy cảm bị đưa vào raw zone

Sự cố privacy không thể giải quyết bằng cách chỉ sửa dashboard. Cần xác định mọi downstream copies, dừng ingest field, điều tra truy cập, kiểm soát retention/deletion và phối hợp nhóm bảo mật/pháp lý theo quy trình.

## 29. Kết nối pipeline với quản lý incident và SLO

Khi báo cáo analytics sai hoặc stale, cần incident process tương tự ứng dụng:

1. Xác định ảnh hưởng người dùng dữ liệu: báo cáo nào, quyết định nào, khu vực nào.
2. Khoanh vùng nguồn, connector, stream, transformation và sink.
3. Tìm timestamp bắt đầu lệch freshness/completeness.
4. So deployment/config/schema/backfill events.
5. Chọn giảm tác động: dừng publish dataset sai, hiển thị stale banner hoặc chuyển sang dataset ổn định.
6. Khôi phục pipeline theo checkpoint/offset hợp lệ.
7. Đối soát dữ liệu và xác minh freshness/quality.
8. Reprocess lịch sử nếu necessary, lưu evidence và timeline.
9. Thực hiện postmortem và corrective actions nếu sự cố đáng kể.

Không "đánh dấu xanh" pipeline chỉ vì consumer đã chạy lại. Phải xác minh tất cả các partitions cần thiết đã catch up và số liệu đã đúng. **Data SLO là phần của độ tin cậy sản phẩm**, đặc biệt với báo cáo dùng để ra quyết định.

## 30. Ví dụ end-to-end: Order Service sang Revenue Dashboard

Một yêu cầu thực tế:

- Checkout phải tiếp tục ghi Order trong khoảng thời gian SLO của API.
- Dashboard doanh thu có dữ liệu mới trong 5 phút.
- Doanh thu không được nhân đôi khi event được gửi lại.
- Cancellation/refund phải được phản ánh theo business rule đã thống nhất.
- Phân tích không được tạo thêm tải nặng lên primary DB.
- Team Analytics không có quyền sửa orders transaction data.

### 30.1. Thiết kế luồng

~~~text
Client -> Checkout -> Order Service
                          |
                   OLTP transaction
                     |          |
                     v          v
                    orders    outbox_events
                                  |
                               CDC/relay
                                  |
                                  v
                              Event Broker
                                  |
                           +------+------+
                           |             |
                           v             v
                       Raw events   Revenue processor
                                         |
                                  Validate + dedupe
                                         |
                                  Fact order/payment
                                         |
                                  Revenue mart
                                         |
                                        BI
~~~

### 30.2. Event contract

Ví dụ event OrderPaid:

~~~json
{
  "eventId": "e3b0-example",
  "eventType": "OrderPaid",
  "eventVersion": 1,
  "aggregateId": "order-90021",
  "aggregateVersion": 3,
  "occurredAt": "2026-11-12T07:10:00Z",
  "tenantId": "tenant-example",
  "payload": {
    "orderId": "order-90021",
    "currency": "VND",
    "paidAmountMinor": 125000,
    "paymentId": "payment-50771"
  }
}
~~~

Đây là dữ liệu minh họa; amount representation phải có hợp đồng rõ về minor units/currency, không đoán rằng mọi currency có cùng số chữ số thập phân. Data contracts cần nêu event được phát khi nào và có nghĩa "authorized", "captured" hay "settled".

### 30.3. Xử lý dedup và state

Consumer:

1. Nhận event có eventId và aggregateVersion.
2. Kiểm tra schema và authorization/nguồn phát.
3. Dedupe eventId trong phạm vi consumer.
4. Đảm bảo không áp version cũ hơn trạng thái đã biết.
5. Ghi raw event theo chính sách, tránh lộ PII.
6. Cập nhật staged state hoặc fact bằng MERGE/upsert.
7. Ghi checkpoint/ack sau khi sink ghi thành công theo semantics.
8. Cập nhật freshness/completeness metrics.
9. Khi event lỗi không phục hồi được, gửi DLQ hoặc quarantine và alert.

### 30.4. Xây doanh thu

Không đơn giản cộng mọi OrderPaid vào revenue nếu refund/cancellation và quy định ghi nhận có thể thay đổi số tiền. Xây một mô hình fact có events hoặc trạng thái payment/settlement/refund, định nghĩa metric nhất quán với chủ sở hữu tài chính.

Ví dụ dashboard có thể trình bày:

~~~text
Dataset: mart_net_sales_daily
Business definition: captured_amount - refunded_amount
Currency handling: per currency; conversion theo policy riêng
Timezone: báo cáo theo Asia/Ho_Chi_Minh
Data as of: 2026-11-12 14:15 ICT
Freshness SLO: 99% source events visible trong 5 phút
Quality status: last reconciliation PASS
~~~

Timezone và ngày trên chỉ minh họa cách truyền đạt. Việc đổi từ UTC sang timezone báo cáo phải được thực hiện nhất quán, nhất là gần ranh giới ngày/tháng và khi giao dịch có nhiều múi giờ.

### 30.5. Xác minh sau cutover

- Chạy song song query OLTP tổng hợp trong một khoảng hẹp và warehouse query tại cùng cutoff, có giới hạn tải an toàn.
- Đối chiếu counts và totals theo currency/status.
- Thử tạo/cancel/refund trong môi trường test.
- Thử relay phát trùng, consumer restart và events đến đảo thứ tự.
- Thử warehouse outage rồi khôi phục/catch-up.
- Xác nhận Checkout không tăng p95 trong lúc backfill.
- Xác nhận dashboard hiển thị freshness và không trả số liệu âm thầm sai.
- Sau khi đạt tiêu chí, chuyển BI sang dataset mới và ngừng báo cáo nặng trên OLTP.

## 31. Kế hoạch chuyển đổi từng giai đoạn

Không nhất thiết "big bang" chuyển mọi báo cáo trong một lần. Có thể đi theo các giai đoạn:

### Giai đoạn 0 — Khảo sát

- Lập danh sách báo cáo/query chạy trực tiếp trên OLTP.
- Đo top resource-heavy queries và ảnh hưởng p95/p99 của giao dịch.
- Xác định business definition, owner, freshness và data classification.
- Ưu tiên workload có tác động lớn nhưng dễ tách.
- Chọn đường dữ liệu theo yêu cầu thực, không khóa vào công cụ trước.

### Giai đoạn 1 — Chọn một luồng nhỏ có thể đo

Ví dụ doanh thu theo ngày từ OrderPaid/RefundIssued, với SLO 15 phút và reconciliation theo ngày. Thiết kế source contract, raw/staging, transform, mart, monitoring.

### Giai đoạn 2 — Dựng pipeline và backfill

- Cấp quyền source tối thiểu.
- Chọn CDC/outbox/batch.
- Snapshot dữ liệu có cutoff.
- Xây idempotent transformation.
- Thiết lập quality tests và lineage.
- Ghi markers và dashboards.

### Giai đoạn 3 — Shadow run

Chạy báo cáo OLTP cũ và pipeline mới song song có kiểm soát. Đối soát theo cutoff, đánh giá latency/chi phí/freshness. Không cắt ngay khi số lượng row trùng một lần.

### Giai đoạn 4 — Cutover BI

Đổi dataset hoặc analytics API sang nền tảng mới; gắn data as-of và phương án quay về trong giới hạn an toàn. Loại bỏ read access/reporting jobs trực tiếp trên primary theo kế hoạch.

### Giai đoạn 5 — Mở rộng theo domain

Thêm Payment, Inventory, Customer, Product từng phần theo data contracts, không lấy raw schemas của mọi service mà thiếu ownership. Chuẩn hóa replay, alert, data catalog và governance.

### Giai đoạn 6 — Kiểm soát chi phí và vòng đời

Xem query profile, retention, cold storage, partition, materialization, resource quotas và cleanup. Tránh biến một data lake thành nơi lưu mọi dữ liệu không giới hạn.

## 32. Những câu hỏi kiến trúc trước khi chọn công cụ

- Báo cáo nào cần latency bao nhiêu và chịu stale bao lâu?
- Giao dịch nào không được ảnh hưởng bởi workload analytics?
- Source of truth và data owner là ai?
- Dữ liệu có cần before image, delete và historical corrections?
- Khối lượng dữ liệu/giây, số tables và schema churn bao nhiêu?
- Có transaction log/CDC connector ổn định với database hiện tại không?
- Cần domain event semantics hay row-level CDC đã đủ?
- Có thể lưu outbox trong cùng transaction với nghiệp vụ không?
- Tần suất replay/backfill và retention cần bao lâu?
- Warehouse/lakehouse cần SQL, ML, realtime hay archive?
- Có thể kiểm thử at-least-once, idempotency, ordering và missing events không?
- Business definitions của doanh thu/đơn hàng/refund đã rõ chưa?
- Cần cross-region/data residency hoặc row-level security?
- Có cách đo freshness, completeness và data correctness không?
- Nếu warehouse hỏng, giao dịch còn hoạt động không?
- Team nào trực pipeline, nhận alert, xử lý schema change và on-call?
- Chi phí compute, storage, egress và backfill được kiểm soát ra sao?

Không có câu trả lời cho những câu hỏi này, một sơ đồ dùng nhiều công nghệ mới vẫn có thể trở thành nguồn phát sinh sự cố.

## 33. Bài tập thực hành

### Bài 1 — Đề xuất kiến trúc tối thiểu

Một ứng dụng có 50.000 orders/ngày, BI cần dashboard theo giờ và báo cáo tổng kết ngày. Báo cáo đang chạy JOIN trên primary khiến checkout p95 tăng.

**Câu hỏi:** Có nhất thiết phải triển khai Kafka, CDC, stream processing và lakehouse ngay không?

**Gợi ý:** Không. Có thể bắt đầu bằng batch ETL incremental/replica phù hợp sang warehouse, giới hạn tải source, dữ liệu đủ mới theo SLO và reconciliation. Chỉ tăng kiến trúc khi yêu cầu near-real-time, khối lượng hoặc consumers thực sự cần.

### Bài 2 — Dual-write failure

Order Service commit orders nhưng request publish OrderPaid tới broker timeout. Một thiết kế publish event trực tiếp sau commit sẽ ra sao?

**Đáp án:** Dữ liệu giao dịch đã có nhưng event có thể mất hoặc trạng thái publish không biết chắc; báo cáo có nguy cơ thiếu order. Transactional outbox đưa order state và outbox event vào cùng DB transaction, relay phát lại sau commit; consumer cần idempotency vì duplicate vẫn có thể xảy ra.

### Bài 3 — Duplicate events

Một OrderPaid eventId E100 được consumer xử lý, nhưng consumer crash trước ack nên broker phát lại E100. Nếu mỗi lần nhận đều cộng thêm 250.000 VND vào revenue, điều gì xảy ra?

**Đáp án:** Doanh thu bị tính trùng 250.000 VND. Cần dedupe/idempotent update, ví dụ ghi event_id và kết quả atomically khi sink hỗ trợ hoặc xây aggregate từ bảng order/payment state đã MERGE.

### Bài 4 — Out-of-order events

Consumer nhận OrderCancelled version=5 trước OrderPaid version=4. Nếu cứ áp event cuối cùng nhận được, trạng thái sẽ ra sao?

**Đáp án:** Có thể bị đưa về PAID sai. Cần aggregate version/ordering và policy xử lý late hoặc missing event theo business invariant.

### Bài 5 — Freshness

Order commit lúc 14:00, CDC đọc 14:01, broker nhận 14:02, transformation xong 14:03, warehouse commit 14:05, dashboard refresh 14:10.

**Câu hỏi:** Freshness từ commit tới dữ liệu hiển thị là bao lâu?

**Đáp án:** 10 phút; nếu chỉ tính tới warehouse visible thì 5 phút. Phải định nghĩa rõ SLO đang đo tại sink hay UI.

### Bài 6 — Reconciliation

Warehouse count orders ngày hôm qua thấp hơn OLTP 200 dòng. Có nên ngay lập tức nạp lại cả bảng orders không?

**Đáp án:** Chưa. Kiểm tra cutoff/watermark, timezone, status filter, late commits, soft deletes, CDC lag, duplicates, schema errors và mức sai khác đã chấp nhận. Xác minh nguyên nhân rồi backfill đúng phạm vi với idempotency.

### Bài 7 — Privacy

Data team cần phân tích conversion theo region, nhưng source customer table chứa email, số điện thoại, địa chỉ nhà và ngày sinh.

**Câu hỏi:** Có nên dump toàn bộ bảng vào raw zone vì tiện không?

**Đáp án:** Không mặc định. Cần data minimization, classification và kiểm soát quyền; chỉ xuất các field thật sự cần, hoặc dùng pseudonymous IDs và dimension phù hợp. Nếu giữ PII vì mục đích hợp lệ, phải có retention/deletion/access policies rõ.

### Bài 8 — Kho phân tích bị outage

Warehouse không nhận dữ liệu trong 2 giờ, nhưng Checkout vẫn khỏe. Đây có phải kết quả kiến trúc tốt không?

**Đáp án:** Việc Checkout không bị kéo xuống là ưu điểm của isolation; tuy nhiên data freshness SLO có thể bị vi phạm, dashboard phải báo stale, pipeline cần catch-up và reconciliation. Cần quản lý backlog, log retention và thời gian recovery.

## 34. Checklist triển khai production

### Nguồn và hợp đồng

- [ ] Mỗi dữ liệu nghiệp vụ có service owner/system of record rõ.
- [ ] Analytics không được ghi ngược vào OLTP ngoài API/contract cho phép.
- [ ] Truy vấn phân tích nặng không chạy trực tiếp trên primary critical path.
- [ ] Đã định nghĩa freshness SLO theo từng data product.
- [ ] Đã chọn batch/CDC/outbox theo nhu cầu và khả năng vận hành.
- [ ] Event/data contract có schema, version, semantics, keys và owner.
- [ ] Có chiến lược xử lý updates, deletes, corrections và late events.
- [ ] Có quy tắc compatibility khi schema nguồn thay đổi.

### Độ tin cậy dữ liệu

- [ ] Initial snapshot và CDC stream có phối hợp log position/cutoff.
- [ ] Consumers có dedup/idempotency và xử lý ordering.
- [ ] Có replay/backfill plan và test trên dataset tạm.
- [ ] Có retention đủ cho recovery của CDC/broker/raw events.
- [ ] Có DLQ/quarantine và quy trình sửa lỗi event.
- [ ] Có data quality tests: completeness, uniqueness, validity, consistency.
- [ ] Có reconciliation với source tại cutoff phù hợp.
- [ ] Có dòng lineage từ source tới báo cáo.
- [ ] Có cảnh báo dữ liệu stale và hiển thị last successful refresh.

### Bảo mật và vận hành

- [ ] CDC/ETL chỉ có quyền tối thiểu cần thiết.
- [ ] PII/secret không bị xuất thừa, dữ liệu được phân loại.
- [ ] Có encryption, row/column access controls và audit.
- [ ] Có deletion/retention propagation theo quy định áp dụng.
- [ ] Query và backfill có limits/cost controls.
- [ ] Pipeline metrics theo dõi lag, errors, retries, throughput, storage.
- [ ] Có người trực và runbook cho source/broker/sink outage.
- [ ] Warehouse outage không kéo hỏng giao dịch production.
- [ ] Đã thử connector restart, duplicate, schema change, late events, backlog.
- [ ] Đã đo ảnh hưởng tới p95/p99 OLTP sau khi tách workload.

## 35. Sai lầm phổ biến

1. **Dùng OLTP production làm data warehouse:** báo cáo cạnh tranh CPU/I/O và có thể ảnh hưởng người dùng.
2. **Cho rằng read replica giải quyết mọi nhu cầu OLAP:** replica vẫn gắn schema OLTP và có lag.
3. **Dual-write DB và broker không có cơ chế bảo đảm:** event có thể mất hoặc thừa.
4. **Nhầm CDC record với business event:** thiếu semantics và contract nghiệp vụ.
5. **Không xử lý duplicate:** doanh thu hoặc số đơn bị nhân đôi khi replay.
6. **Không xử lý out-of-order:** trạng thái cũ ghi đè trạng thái mới.
7. **Không phối hợp snapshot và log stream:** dữ liệu thiếu hoặc sai sau initial load.
8. **Không thiết kế backfill:** logic mới chỉ đúng cho dữ liệu phát sinh từ hôm nay.
9. **Xem timestamp là ordering tuyệt đối:** clock skew và commit timing có thể phá giả định.
10. **Không có freshness SLO:** dashboard dữ liệu cũ nhưng người dùng tưởng realtime.
11. **Chỉ đo pipeline RUNNING:** bỏ sót missing records và sai dữ liệu.
12. **Không đối soát dữ liệu nguồn:** lỗi âm thầm tồn tại nhiều tháng.
13. **Schema change không có contract:** downstream fail sau một deploy bình thường.
14. **Khai thác raw PII không kiểm soát:** tăng rủi ro privacy và compliance.
15. **Không có data catalog/lineage:** không biết báo cáo sai do field hoặc job nào.
16. **Model fact sai grain:** JOIN làm tính doanh thu nhiều lần.
17. **Bỏ qua refund/cancellation:** báo cáo doanh số đúng tại ngày tạo đơn nhưng sai sau đó.
18. **Warehouse outage kéo hỏng Checkout:** hệ thống vẫn còn phụ thuộc đồng bộ không cần thiết.
19. **Không có resource governance ở OLAP:** một truy vấn ad hoc làm chậm mọi dashboard.
20. **Chọn công cụ trước khi có SLO và owner:** kiến trúc phức tạp mà không giải quyết nhu cầu thật.

## 36. Ghi nhớ

**OLTP** là nơi thực hiện giao dịch, bảo vệ invariant và trạng thái nghiệp vụ do từng service sở hữu. **OLAP** là môi trường phục vụ scans, aggregates, báo cáo, lịch sử, BI và các phân tích phức tạp. Tách hai workload giúp bảo vệ độ trễ và độ tin cậy của ứng dụng, đồng thời cho phép nền tảng phân tích tối ưu độc lập.

Cách chuyển dữ liệu có thể từ batch ETL/ELT, read replica, CDC hoặc transactional outbox kết hợp broker/stream processing. Lựa chọn theo freshness, consistency, dữ liệu thay đổi, chi phí, vận hành và business semantics. CDC không tự tạo domain events; outbox giúp tránh dual-write nhưng consumers vẫn phải chịu được duplicate và replay.

Dữ liệu phân tích thường có eventual consistency. Vì vậy phải có **freshness SLO, data quality checks, reconciliation, dedup/idempotency, schema contracts, lineage, bảo mật và backfill**. Một dashboard nhanh nhưng thiếu order hoặc tính trùng doanh thu không phải thành công.

**Nguyên tắc cốt lõi: giữ cơ sở dữ liệu giao dịch tập trung phục vụ nghiệp vụ và tính đúng đắn; xuất dữ liệu ra một luồng có hợp đồng và khả năng khôi phục; để phân tích chạy trên nền tảng riêng; đo rõ độ mới, đầy đủ, chính xác và tác động lên hệ thống nguồn.**