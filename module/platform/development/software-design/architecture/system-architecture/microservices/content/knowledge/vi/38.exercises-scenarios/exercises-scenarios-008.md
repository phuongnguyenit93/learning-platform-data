# Thiết kế bản chiếu phục vụ màn hình tổng hợp nhiều dịch vụ

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Bài tập và tình huống.
>
> **Bài toán:** Một màn hình cần hiển thị thông tin tổng hợp từ nhiều domain như Customer, Order, Payment, Inventory và Fulfillment. Làm sao cung cấp dữ liệu nhanh, dễ truy vấn và đủ mới mà vẫn giữ quyền sở hữu nghiệp vụ ở các service nguồn?
>
> **Ý tưởng cốt lõi:** Thiết kế một **read model / projection** theo nhu cầu đọc của màn hình. Các service nguồn tiếp tục sở hữu trạng thái authoritative; projection nhận dữ liệu qua API, domain events hoặc pipeline được quản lý, biến đổi thành mô hình đọc phù hợp và cung cấp cho UI qua một query interface. Projection là dữ liệu dẫn xuất có freshness, lineage, version, owner và quy trình rebuild rõ ràng.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Chuyển yêu cầu màn hình tổng hợp thành use cases, fields, filters, sorting, pagination và freshness expectations.
2. Xác định authoritative source cho từng trường dữ liệu và phân biệt dữ liệu gốc, snapshot, projection, cache và dữ liệu suy diễn.
3. So sánh API composition/BFF với materialized read model, CQRS và hybrid design.
4. Chọn grain và key của projection sao cho một record phản ánh đúng một đối tượng nghiệp vụ ở một thời điểm xác định.
5. Thiết kế data contract và event ingestion từ nhiều service mà không cho query service ghi ngược vào domain databases.
6. Xử lý event duplicate, out-of-order, partial updates, version gaps, tombstones và replay.
7. Xác định consistency model, freshness SLO, read-your-writes và cách hiển thị dữ liệu stale hoặc chưa đầy đủ.
8. Thiết kế schema, index, query API, pagination và cache theo workload thực tế của màn hình.
9. Bảo vệ tenant isolation, authorization, PII, purpose limitation và audit trong read model tổng hợp.
10. Backfill, rebuild, reconcile và vận hành projection khi nguồn thay schema, broker lag hoặc consumer bị lỗi.
11. Kiểm thử tính đúng đắn, performance, failure modes và data quality của mô hình đọc.
12. Triển khai theo từng bước, đo hiệu quả và lựa chọn phương án phù hợp với quy mô hệ thống.

Các service, fields, SQL, JSON và số liệu trong bài là ví dụ minh họa. Cần xác định semantics, SLA, classification và technology theo hệ thống thực tế.

## 2. Bối cảnh: một màn hình phải ghép nhiều domain

Giả sử trang quản trị đơn hàng cần hiển thị:

- Mã đơn, thời điểm tạo, trạng thái đơn và tổng tiền.
- Tên khách hàng và thông tin liên hệ được phép hiển thị.
- Trạng thái thanh toán, số tiền đã thu và refund.
- Tình trạng giữ hàng và số lượng sản phẩm.
- Trạng thái giao hàng, đơn vị vận chuyển và tracking.
- Các bộ lọc theo ngày, trạng thái, khách hàng, tenant và khu vực.
- Sắp xếp theo thời gian, tổng tiền hoặc trạng thái cập nhật.
- Phân trang cho hàng nghìn hoặc hàng triệu đơn.

Dữ liệu thuộc nhiều service:

~~~text
                   Admin UI
                      │
                      ▼
               Order Summary API
                      │
        ┌─────────────┼──────────────┐
        ▼             ▼              ▼
   Customer       Payment        Fulfillment
    Service        Service         Service
        │             │              │
   Customer DB    Payment DB     Shipment DB
        ▲             ▲              ▲
        └─────────────┼──────────────┘
                      │
                 Order Service
                      │
                   Order DB
~~~

Nếu UI gọi cả năm service cho từng hàng trong bảng, màn hình có thể chậm, tạo nhiều network requests và phụ thuộc availability của tất cả upstream services. Nếu query service tự JOIN trực tiếp các database, nó lại phá vỡ data ownership và phụ thuộc schema nội bộ.

Một read model chuyên dụng có thể tổng hợp dữ liệu theo nhu cầu hiển thị:

~~~text
Customer Events ─────┐
Order Events ────────┤
Payment Events ──────┼──► Projection Processor
Inventory Events ────┤            │
Fulfillment Events ──┘            ▼
                              Read Model DB
                                   │
                                   ▼
                              Summary API
                                   │
                                   ▼
                                 Admin UI
~~~

UI đọc một contract được tối ưu cho màn hình. Mỗi service nguồn vẫn là nơi quyết định dữ liệu thuộc domain của mình.

## 3. Xác định đúng bài toán trước khi chọn công nghệ

Không bắt đầu bằng câu hỏi “dùng Kafka hay Redis?” Hãy mô tả chính xác nhu cầu đọc.

### 3.1. Use cases của màn hình

| Use case | Dữ liệu cần | Hành vi |
| --- | --- | --- |
| Danh sách đơn | order ID, createdAt, order status, total | Sort, filter, pagination |
| Chi tiết đơn | order lines, customer summary, payment, shipment | Mở một đơn |
| Bộ lọc thanh toán | payment state, captured amount, refund state | Filter theo trạng thái |
| Theo dõi giao hàng | carrier, tracking state, last update | Hiển thị tiến trình |
| Báo cáo nhanh | totals theo ngày/trạng thái | Aggregate |
| Hỗ trợ khách hàng | contact được phép xem, lịch sử trạng thái | Authorization theo vai trò |

Một màn hình danh sách và màn hình chi tiết có thể cần hai read models khác nhau. Đừng ép một bảng projection khổng lồ phục vụ mọi query nếu access patterns khác nhau rõ rệt.

### 3.2. Viết data requirements

Với mỗi field, ghi:

- Tên hiển thị và ý nghĩa nghiệp vụ.
- Authoritative source/service.
- Đơn vị, timezone, enum semantics.
- Có bắt buộc hay có thể null?
- Có phải snapshot tại thời điểm tạo không?
- Cập nhật theo event hay API pull?
- Freshness mong muốn.
- Ai được phép xem?
- Có cần filter/sort/index?
- Khi source xóa hoặc không còn quyền truy cập, xử lý ra sao?

### 3.3. Phân biệt màn hình operational và analytical

Operational screen thường cần truy vấn theo ID/tenant/status, dữ liệu tương đối mới, pagination, drill-down, latency thấp và authorization theo user/role.

Analytical dashboard thường cần aggregates lớn, historical joins, time windows, transformation phức tạp và reporting cut-off. Một OLTP read model không nhất thiết phù hợp làm warehouse; ngược lại, BI warehouse không nên làm query path cho thao tác cần current operational state nếu freshness không đáp ứng.

## 4. Chọn grain của projection

**Grain** trả lời: một hàng trong read model đại diện cho điều gì?

Ví dụ:

- Một row cho mỗi Order.
- Một row cho mỗi OrderLine.
- Một row cho mỗi Shipment.
- Một row cho mỗi Order và một trạng thái workflow.
- Một row cho mỗi Order theo từng ngày báo cáo.

Đối với danh sách đơn, grain có thể là **một summary row cho mỗi orderId trong tenant**.

~~~text
order_summary
  tenant_id
  order_id
  created_at
  order_status
  customer_summary
  payment_summary
  fulfillment_summary
  total_amount
  currency
  projection_version
  updated_at
~~~

Không chọn grain chỉ vì dễ JOIN. Hãy xét:

- UI có cần một dòng cho mỗi Order hay mỗi Shipment?
- Một Order có nhiều payments/refunds hoặc nhiều shipments không?
- Aggregate nhiều dòng có thể làm duplicate order rows không?
- Có cần lịch sử trạng thái hay chỉ trạng thái mới nhất?
- Có thể query theo tenant, ngày và status hiệu quả không?

### 4.1. Một đối tượng có nhiều bản ghi con

Nếu một Order có 3 shipments, JOIN thẳng Order với Shipment sẽ tạo 3 rows. Khi đó COUNT(order_id) có thể sai và pagination dễ lặp/mất đơn.

Có thể giữ một summary row/order với shipment count và latest shipment status; dùng child table riêng cho shipment details; query chi tiết qua endpoint khác; hoặc tạo read model khác nếu màn hình theo dõi shipment có workload riêng.

### 4.2. Grain phải đi cùng semantics thời gian

Một order summary có thể hiển thị trạng thái hiện tại. Một invoice report có thể cần trạng thái tại thời điểm chốt sổ. Một order snapshot cần giữ giá tại thời điểm checkout. Không trộn current state với historical snapshot trong cùng field mà không ghi rõ.

## 5. Xác định authoritative source cho từng field

Projection không có quyền tự định nghĩa lại domain truth.

| Field trong màn hình | Nguồn authoritative | Projection lưu |
| --- | --- | --- |
| orderId | Order | ID và tenant key |
| orderStatus | Order | Trạng thái đơn mới nhất đã áp dụng |
| createdAt | Order | Timestamp gốc, chuẩn timezone |
| customerDisplayName | Customer/Profile | Snapshot hiển thị hoặc projection |
| customerContact | Customer/Identity | Chỉ field được phép, có classification |
| paymentStatus | Payment | Trạng thái payment theo contract |
| capturedAmount | Payment | Amount/currency theo semantics |
| refundSummary | Payment/Refund | Aggregate theo policy |
| reservationStatus | Inventory | Trạng thái reservation |
| shipmentStatus | Fulfillment | Latest state/version |
| trackingReference | Fulfillment | Reference được phép hiển thị |
| orderTotal | Order/Pricing snapshot | Giá trị đã chốt tại thời điểm order |

### 5.1. Một field tổng hợp có thể có owner dẫn xuất

Ví dụ paymentSummaryStatus trên màn hình có thể được tính từ nhiều payment attempts. Payment Service vẫn sở hữu từng payment transaction; projection processor sở hữu cách tổng hợp cho màn hình theo một contract được công bố.

### 5.2. Không tự suy luận business status từ nhiều booleans

Nếu UI tự suy ra “Đã hoàn tất” khi payment=success, inventory=reserved và shipment=created, có thể sai khi order bị canceled hoặc refund pending. Domain owner nên cung cấp state có semantics rõ, hoặc quy tắc tổng hợp phải được phê duyệt và kiểm thử.

### 5.3. Ghi provenance

Với field quan trọng, giữ metadata như source version, source event time hoặc applied version để điều tra và đối soát. Không nhất thiết phải lưu mọi metadata vào response công khai.

## 6. Hai cách tiếp cận chính: API composition và materialized read model

### 6.1. API composition / BFF

Một BFF hoặc query API gọi nhiều owner APIs rồi tổng hợp response:

~~~text
UI
 │
 ▼
Order Summary BFF
 ├──► Order API
 ├──► Customer API
 ├──► Payment API
 └──► Fulfillment API
 │
 ▼
Combined Response
~~~

Ưu điểm:

- Không cần duy trì bản sao dữ liệu tổng hợp.
- Có thể lấy dữ liệu mới trực tiếp từ owner.
- Logic presentation nằm gần UI/API.
- Ít pipeline projection và rebuild.

Nhược điểm:

- Mỗi request phụ thuộc nhiều upstream.
- Latency và tail latency có thể cộng dồn.
- Fan-out có thể tạo nhiều requests.
- Partial failures cần xử lý.
- Pagination/filter/sort xuyên nhiều nguồn rất khó.
- Upstream rate limits và availability ảnh hưởng UI.

Phù hợp khi số nguồn ít, traffic vừa phải, dữ liệu cần mới và query pattern đơn giản.

### 6.2. Materialized read model / projection

Một processor cập nhật bảng đọc từ events hoặc pipeline:

~~~text
Owner Services
    │ events / CDC / snapshots
    ▼
Projection Processor
    │ transform + deduplicate + version
    ▼
Read Model Store
    │ indexed query
    ▼
Summary API
    │
    ▼
UI
~~~

Ưu điểm:

- Query một nơi, response nhanh và ổn định.
- Tối ưu theo screen-specific access patterns.
- Ít phụ thuộc runtime vào tất cả upstream services.
- Có thể hỗ trợ filter/sort/pagination hiệu quả.
- Tạo được partial availability với freshness contract.

Nhược điểm:

- Eventual consistency.
- Phải quản lý duplication, ordering và replay.
- Thêm storage/pipeline/observability.
- Cần backfill/rebuild và reconciliation.
- Dữ liệu nhạy cảm có thêm bản sao cần bảo vệ.

Phù hợp khi màn hình đọc nhiều, tổng hợp nhiều nguồn, cần query linh hoạt và chấp nhận freshness được định nghĩa.

### 6.3. Hybrid

Có thể dùng projection cho danh sách và gọi owner API khi mở chi tiết:

~~~text
Order List UI ──► Order Summary Read Model
Order Detail UI ──► Order Detail BFF
                       ├──► Order API
                       ├──► Payment API
                       └──► Fulfillment API
~~~

Danh sách có thể chấp nhận dữ liệu trễ vài giây; thao tác nhạy cảm hoặc kiểm tra trạng thái cuối có thể truy vấn owner. Đây thường là lựa chọn cân bằng.

## 7. Ma trận quyết định

| Tiêu chí | API composition | Materialized projection | Hybrid |
| --- | --- | --- | --- |
| Freshness | Gần nguồn tại thời điểm gọi | Có lag theo pipeline | Theo từng use case |
| Runtime dependencies | Nhiều upstream | Chủ yếu read store | Kết hợp |
| Latency danh sách lớn | Có thể khó tối ưu | Dễ tối ưu index/query | Tốt nếu phân chia hợp lý |
| Filter/sort nhiều domain | Phức tạp | Có thể thiết kế trước | Một phần |
| Operational overhead | BFF + upstream clients | Processor + store + replay | Cả hai |
| Failure behavior | Partial upstream failure | Stale/lagged projection | Có fallback theo màn hình |
| Rebuild | Không có projection | Phải có | Phần projection |
| Data copies | Ít hơn | Nhiều hơn | Chọn lọc |
| Phù hợp | Ít nguồn, query đơn giản | Read-heavy, nhiều nguồn | Sản phẩm đa dạng use cases |

Không có lựa chọn luôn tốt nhất. Quyết định phải gắn với traffic, latency budget, freshness, data classification và năng lực vận hành.

## 8. Thiết kế kiến trúc projection

Một kiến trúc tham khảo:

~~~text
       Customer Service          Payment Service
              │                         │
        CustomerUpdated            PaymentUpdated
              │                         │
              └──────────┬──────────────┘
                         │
       Order Service     │      Fulfillment Service
              │         │              │
        OrderUpdated    │        ShipmentUpdated
              │         │              │
              └─────────┴──────────────┘
                         │
                    Event Broker
                         │
                  Projection Consumer
                         │
               ┌─────────┴─────────┐
               │                   │
          Inbox/Dedup          Projection Logic
                                   │
                                   ▼
                            Read Model DB
                                   │
                              Summary API
                                   │
                                   ▼
                                   UI
~~~

Các trách nhiệm:

- **Producer/domain owner:** phát event đúng semantics sau khi state change durable.
- **Broker:** chuyển message theo delivery/retention guarantees.
- **Projection consumer:** validate schema, deduplicate, kiểm version, transform.
- **Read model store:** giữ dữ liệu tối ưu cho query.
- **Summary API:** authorization, filter, pagination, response contract.
- **UI:** thể hiện freshness/partial data và dùng query contract đúng.

Projection processor không được trở thành writer của Order DB, Payment DB hoặc Customer DB.

## 9. Chọn event hay CDC làm nguồn projection

### 9.1. Domain events

Ví dụ OrderConfirmed, PaymentCaptured, ShipmentDispatched. Ưu điểm là semantics nghiệp vụ rõ và ít phụ thuộc schema vật lý.

Owner công bố event type/version, aggregate ID/version, event ID, occurred time, correlation/causation IDs, payload fields/units, compatibility policy và retention/replay policy.

### 9.2. CDC

CDC có thể stream row changes từ database log. Hữu ích khi legacy service chưa có domain events hoặc cần backfill/incremental replication.

Nhược điểm:

- Row-level changes không luôn phản ánh business fact.
- Coupling với schema/table.
- DDL và connector upgrades cần quản lý.
- Delete/tombstone và transaction ordering phải rõ.
- Dễ phát tán internal fields hoặc PII không cần thiết.

CDC có thể là cầu nối migration; đừng mặc định biến mọi table change thành public domain contract lâu dài.

### 9.3. Snapshot API và batch

Có thể tải snapshot từ owner API hoặc export job rồi cập nhật incremental bằng events. Cần snapshot watermark để biết delta nào đã xảy ra sau snapshot. Không chụp snapshot và stream độc lập mà không có điểm nối, nếu không sẽ có race và bỏ sót/thêm trùng thay đổi.

### 9.4. Chọn nguồn theo ownership

Không đọc thẳng DB chỉ vì dễ hơn. Nếu một service không có API/event phù hợp, phối hợp với owner để tạo contract/export có kiểm soát, hoặc ghi rõ một compatibility path có expiry.

## 10. Thiết kế event contract cho projection

Ví dụ event:

~~~json
{
  "eventId": "evt-10001",
  "eventType": "PaymentStatusChanged",
  "schemaVersion": 2,
  "aggregateType": "Payment",
  "aggregateId": "pay-123",
  "aggregateVersion": 7,
  "occurredAt": "2026-11-12T03:15:00Z",
  "correlationId": "checkout-456",
  "data": {
    "orderId": "ord-789",
    "status": "CAPTURED",
    "amountMinorUnits": 250000,
    "currency": "VND"
  }
}
~~~

### 10.1. Event ID

Nhận diện một event cụ thể, dùng để deduplicate delivery. Không dùng orderId làm event ID vì một order có nhiều event.

### 10.2. Aggregate ID và version

Giúp nhận diện entity và ngăn projection bị lùi khi event cũ tới sau. Version cần tăng theo contract owner; không tự tạo sequence ở projection consumer nếu cần biết thứ tự nguồn.

### 10.3. Occurred time và applied time

occurredAt là thời điểm event xảy ra theo nguồn. appliedAt là thời điểm projection lưu thành công. Chênh lệch hỗ trợ đo freshness; cần lưu ý clock skew.

### 10.4. Snapshot event và delta event

- **Snapshot/full-state event:** chứa đủ dữ liệu cần để thay thế projection phần tương ứng. Dễ xử lý version và rebuild, nhưng payload lớn hơn và có thể mang dữ liệu không cần thiết.
- **Delta event:** chỉ mô tả thay đổi. Phải xử lý ordering/gaps và áp dụng đúng transition.

Đừng áp dụng logic snapshot cho delta. Ví dụ event PaymentAmountAdjusted(+1000) không thể bỏ qua chỉ vì event sau có version cao hơn nếu projection cần tính tổng từ mọi delta.

### 10.5. Payload tối thiểu

Projection chỉ cần tên hiển thị, có thể không cần toàn bộ Customer profile. Hạn chế raw email, phone, address và các field nhạy cảm. Dùng reference hoặc projection đã được cấp quyền khi phù hợp.

## 11. Thiết kế schema read model

Một bảng summary cho danh sách đơn có thể là:

~~~sql
CREATE TABLE order_summary (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    order_status VARCHAR(32) NOT NULL,
    customer_id UUID,
    customer_display_name TEXT,
    payment_status VARCHAR(32),
    captured_minor_units BIGINT,
    currency CHAR(3),
    fulfillment_status VARCHAR(32),
    latest_tracking_reference TEXT,
    item_count INTEGER,
    total_minor_units BIGINT NOT NULL,
    order_version BIGINT,
    customer_version BIGINT,
    payment_version BIGINT,
    fulfillment_version BIGINT,
    projection_updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);
~~~

Đây là ví dụ schema; chọn types và fields theo database, privacy policy và query workload.

### 11.1. Tại sao có version riêng cho từng source?

Order version 12 không thể so sánh trực tiếp với Customer version 8. Mỗi source có sequence riêng. Projection có thể lưu order_version, customer_version, payment_version và fulfillment_version.

### 11.2. Projection metadata

Có thể lưu thêm:

- last_order_event_at.
- last_payment_event_at.
- last_fulfillment_event_at.
- projection_updated_at.
- projection_schema_version.
- source_watermark hoặc offset theo pipeline.

Không nhất thiết trả tất cả metadata cho UI; giữ đủ để vận hành và điều tra.

### 11.3. Tách bảng con khi cardinality khác nhau

Nếu một order có nhiều shipments hoặc payment attempts, có thể tạo:

- order_summary: một row/order.
- order_payment_summary: một row/order hoặc payment aggregate.
- order_shipments: một row/shipment.
- order_lines: một row/order line.

Không nhét danh sách không giới hạn vào JSON column nếu UI cần filter/sort trên từng phần tử hoặc dữ liệu tăng lớn. Có thể dùng JSON cho snapshot nhỏ, bounded và chỉ hiển thị.

## 12. Index và tối ưu truy vấn

Màn hình danh sách thường filter theo tenant, ngày, status và sort theo createdAt.

Ví dụ:

~~~sql
CREATE INDEX idx_order_summary_tenant_created
ON order_summary (tenant_id, created_at DESC, order_id);

CREATE INDEX idx_order_summary_tenant_status_created
ON order_summary (tenant_id, order_status, created_at DESC, order_id);

CREATE INDEX idx_order_summary_tenant_payment_created
ON order_summary (tenant_id, payment_status, created_at DESC, order_id);
~~~

### 12.1. Index theo access pattern

Không tạo index cho mọi field. Mỗi index tăng chi phí writes/storage và có thể làm projection updates chậm hơn. Dùng query plans và production-like workload để quyết định.

### 12.2. Pagination ổn định

Offset pagination đơn giản nhưng offset lớn có thể chậm và dữ liệu thay đổi giữa các pages có thể gây duplicate/missing rows.

Keyset pagination có thể dùng (created_at, order_id) làm cursor:

~~~sql
SELECT order_id, created_at, order_status, total_minor_units
FROM order_summary
WHERE tenant_id = :tenant_id
  AND (created_at, order_id) < (:cursor_time, :cursor_id)
ORDER BY created_at DESC, order_id DESC
LIMIT :page_size;
~~~

Cần index phù hợp và cursor opaque/signed nếu không muốn client tự sửa.

### 12.3. Sort theo field thay đổi nhanh

Nếu sort theo paymentStatus hoặc fulfillmentStatus, cần index phù hợp hoặc query model chuyên dụng. Đừng sort toàn bộ rows trong application memory.

### 12.4. Filter semantics

Xác định createdAt dùng UTC hay timezone tenant; amount dùng minor units hay decimal; status filter bao gồm trạng thái trung gian nào. Query nhanh nhưng semantics sai vẫn là lỗi.

## 13. API contract cho màn hình

Ví dụ query:

~~~http
GET /admin/order-summaries?status=PAYMENT_PENDING&from=2026-11-01T00:00:00Z&limit=50
Authorization: Bearer <token>
~~~

Response minh họa:

~~~json
{
  "items": [
    {
      "orderId": "ord-789",
      "createdAt": "2026-11-12T03:15:00Z",
      "orderStatus": "PENDING",
      "customer": {
        "id": "cus-123",
        "displayName": "Nguyen Van A"
      },
      "payment": {
        "status": "AUTHORIZED",
        "capturedMinorUnits": 250000,
        "currency": "VND"
      },
      "fulfillment": {
        "status": "NOT_STARTED"
      },
      "freshness": {
        "updatedAt": "2026-11-12T03:15:04Z",
        "state": "CURRENT_WITHIN_TARGET"
      }
    }
  ],
  "nextCursor": "opaque-cursor",
  "generatedAt": "2026-11-12T03:15:05Z"
}
~~~

Đây là response minh họa; tên trạng thái và semantics cần được định nghĩa trong API contract.

### 13.1. API phải thể hiện nguồn dữ liệu

Không cần công khai tên database/topic, nhưng cần công bố fields và semantics, freshness expectation, null/unknown behavior, pagination/filter/sort, authorization, error/partial result behavior và version/deprecation.

### 13.2. Không trả raw event payload

UI cần view model có ổn định. Event schema phục vụ integration; query API phục vụ consumer. Hai contract có thể khác nhau.

### 13.3. Version API độc lập với projection schema

Có thể đổi storage schema mà giữ response contract. API version chỉ cần thay khi semantics/compatibility của public response thay đổi.

## 14. Cập nhật projection: full replacement hay partial merge?

### 14.1. Full snapshot

Event chứa đủ dữ liệu thuộc source:

~~~text
OrderSnapshot v12:
  status = CONFIRMED
  total = 250000
  currency = VND
  createdAt = ...
~~~

Consumer cập nhật phần Order fields của projection. Dễ xử lý version và rebuild, nhưng payload lớn hơn và có thể mang dữ liệu không cần thiết.

### 14.2. Partial/delta event

Event chỉ chứa thay đổi:

~~~text
OrderStatusChanged v13:
  previous = PENDING
  current = CONFIRMED
~~~

Payload nhỏ nhưng consumer phải hiểu transition, giữ state đúng và phát hiện gap.

### 14.3. Partial merge phải theo source ownership

Payment event chỉ được cập nhật cột payment-related; không ghi đè order_status hoặc customer_display_name bằng null do payload không chứa các fields đó.

Tránh ORM save toàn bộ entity từ một event thiếu field, vì có thể ghi null đè dữ liệu của source khác.

### 14.4. Upsert có điều kiện theo version

Ví dụ ý tưởng:

~~~sql
UPDATE order_summary
SET payment_status = :status,
    captured_minor_units = :captured_minor_units,
    payment_version = :incoming_version,
    projection_updated_at = now()
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND COALESCE(payment_version, 0) < :incoming_version;
~~~

Nếu không có row, cần phân biệt row chưa tồn tại, event duplicate/cũ hay key sai. Có thể cần upsert/transaction và xử lý concurrency đầy đủ.

## 15. Idempotency và duplicate events

Broker có thể redeliver event khi consumer crash sau khi commit read model nhưng trước acknowledgement.

Projection update nên idempotent:

- Full snapshot với version có thể apply nếu incoming version lớn hơn version đã lưu.
- Delta event cần inbox/dedup theo event ID và transaction với projection update.
- Aggregate operations như cộng amount cần unique event record hoặc idempotency key.
- External side effects không nên được thực hiện trong projection handler nếu không cần.

Bảng inbox minh họa:

~~~sql
CREATE TABLE projection_inbox (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong một transaction local:

1. Insert inbox key.
2. Nếu duplicate thì kết thúc an toàn.
3. Validate source version.
4. Update projection.
5. Commit.
6. Ack message.

Nếu insert inbox và update projection không atomic, crash có thể làm mất event hoặc áp dụng lặp.

## 16. Out-of-order events và version gaps

Ví dụ Customer phát version 15 rồi version 14 tới sau do retry. Nếu projection áp dụng v14, tên khách có thể quay về giá trị cũ.

### 16.1. Latest-state snapshot

Nếu event là full snapshot, consumer có thể chỉ áp dụng version cao hơn current version.

### 16.2. Delta event

Nếu event là delta, version 15 có thể phụ thuộc vào version 14. Khi thiếu sequence:

- Buffer/retry trong giới hạn.
- Fetch snapshot từ owner.
- Rebuild projection phần bị thiếu.
- Đưa vào reconciliation queue.
- Alert nếu gap tồn tại quá lâu.

### 16.3. Version theo từng aggregate

Không so sánh order version với payment version. Mỗi source có version namespace riêng. Projection lưu version theo từng source/aggregate.

### 16.4. Ordering theo key

Nếu broker hỗ trợ partition key, dùng aggregate ID để event của cùng entity có cơ hội được xử lý theo thứ tự trong partition. Vẫn cần version checks vì producer retries, multiple publishers hoặc consumer concurrency có thể gây tình huống phức tạp.

## 17. Ghép dữ liệu khi events đến không đồng thời

Order event có thể tới trước Customer event. Projection cần quyết định có tạo row ngay hay đợi đủ nguồn.

### 17.1. Tạo partial row

Có thể tạo Order summary với Customer section chưa có:

~~~text
Order: present
Customer: PENDING_ENRICHMENT
Payment: UNKNOWN
Fulfillment: NOT_STARTED
~~~

UI hiển thị trạng thái phù hợp và projection bổ sung sau.

### 17.2. Buffer prerequisite

Nếu một field bắt buộc cho business query, có thể lưu event tạm hoặc chờ snapshot. Nhưng không để message bị block vô hạn vì một event khác không tới.

### 17.3. Fetch on miss

Projection processor có thể gọi owner API để lấy snapshot khi nhận reference chưa có. Cần rate limit, retry, circuit breaker và tránh fan-out storm khi nhiều events cùng thiếu prerequisite.

### 17.4. Không giả định arrival order giữa topics

Order, Customer và Payment topics không có một global order. Dùng correlation ID giúp nối workflow nhưng không tạo thứ tự giữa các topics.

## 18. Trạng thái tổng hợp và semantics

Màn hình có thể cần một nhãn “Tình trạng xử lý” tổng hợp. Hãy định nghĩa rõ:

| Order | Payment | Inventory | Fulfillment | Display summary |
| --- | --- | --- | --- | --- |
| PENDING | UNKNOWN | UNKNOWN | NOT_STARTED | Đang tiếp nhận |
| PENDING | AUTHORIZED | RESERVED | NOT_STARTED | Đang xác nhận đơn |
| CONFIRMED | CAPTURED | RESERVED | READY | Sẵn sàng giao |
| CONFIRMED | CAPTURED | RESERVED | DISPATCHED | Đang vận chuyển |
| CANCELLED | REFUNDED | RELEASED | NOT_STARTED | Đã hủy |
| CONFIRMED | CAPTURED | RESERVED | DELIVERED | Đã giao |

Bảng này chỉ là ví dụ. Trạng thái thực tế cần dựa vào business state machine. Có thể có ngoại lệ như payment captured nhưng order cancel pending, partial shipment hoặc partial refund.

### 18.1. Đừng tạo enum tổng hợp quá lớn

Nếu kết hợp 5 status dimensions thành một enum với hàng trăm tổ hợp, schema và UI khó duy trì. Có thể trả các trạng thái độc lập cùng một attentionState hoặc workflowSummary có quy tắc rõ.

### 18.2. Phân biệt unknown, pending và failed

- **Unknown:** projection chưa biết trạng thái hoặc source chưa trả kết quả.
- **Pending:** nghiệp vụ đang xử lý theo workflow.
- **Failed:** owner xác nhận thao tác thất bại.
- **Stale:** projection chưa nhận cập nhật đủ mới.
- **Unavailable:** không lấy được nguồn/đang lỗi.

Không gộp tất cả thành null hoặc “Không rõ”.

### 18.3. Summary phải có owner của rule

Nếu Summary API tự tổng hợp state, cần một nhóm sở hữu semantics và versioning của rule. Không để frontend, report và API tự tính ba cách khác nhau.

## 19. Freshness và consistency contract

Một projection không thể nói “real-time” nếu không đo.

Ví dụ mục tiêu minh họa:

- 99% Order events được áp dụng trong 5 giây.
- 99% Payment events trong 10 giây.
- 99% Shipment updates trong 30 giây.
- Mismatch critical được phát hiện trong 2 phút.
- Projection có thể stale tối đa 5 phút trước khi UI hiển thị cảnh báo.

Chọn ngưỡng theo use case, broker throughput, owner SLO và business risk.

### 19.1. Đo source-to-projection lag

Có thể tính:

`projectionAppliedAt - sourceOccurredAt`

hoặc dùng committed timestamp/watermark đáng tin cậy hơn. Cần tính clock skew, event buffering và batch processing.

### 19.2. Freshness theo source

Một row có thể có Order data mới nhưng Shipment data cũ. Có thể hiển thị freshness theo từng section/source hoặc một overall state theo policy.

### 19.3. Read-your-writes

Sau khi người dùng vừa cập nhật một field, projection có thể chưa kịp cập nhật. Các lựa chọn:

- Response trả authoritative result.
- UI optimistic update và sau đó reconcile.
- Query API chấp nhận minimumVersion/consistency token.
- Đọc owner API trong khoảng ngắn.
- Hiển thị “đang cập nhật” tới khi projection đạt version.

### 19.4. Không hứa strong consistency từ projection async

Nếu user cần xác nhận thanh toán cuối cùng, query Payment owner hoặc một operation có consistency guarantee phù hợp. Không dựa vào projection trễ để thực hiện hành động không thể đảo ngược.

## 20. Partial failure và degraded UI

Màn hình tổng hợp có thể hoạt động khi một upstream service lỗi nếu projection đã có dữ liệu trước đó. Nhưng UI phải biết dữ liệu nào stale.

Ví dụ:

~~~json
{
  "orderStatus": {
    "value": "CONFIRMED",
    "freshness": "CURRENT"
  },
  "paymentStatus": {
    "value": "CAPTURED",
    "freshness": "CURRENT"
  },
  "fulfillmentStatus": {
    "value": "DISPATCHED",
    "freshness": "STALE",
    "lastUpdatedAt": "2026-11-12T02:50:00Z"
  }
}
~~~

### 20.1. Degraded states

- Projection store hoạt động, event pipeline lag: trả dữ liệu với freshness metadata.
- Một source chưa từng gửi data: hiển thị NOT_AVAILABLE hoặc PENDING_ENRICHMENT.
- Source bị xóa theo policy: hiển thị dữ liệu đã ẩn danh hoặc không còn khả dụng.
- Projection API không truy cập được: báo lỗi phù hợp, không trả cache không rõ tuổi như dữ liệu mới.

### 20.2. Không che giấu partial data

Nếu Payment chưa cập nhật, không suy luận NOT_PAID chỉ vì field null. UI cần phân biệt “chưa nhận dữ liệu” với “Payment owner xác nhận chưa thanh toán”.

### 20.3. Stale-while-revalidate

Có thể trả bản sao gần nhất và làm mới sau nếu business chấp nhận. Response phải cho biết thời điểm cập nhật và trạng thái stale. Không dùng cho quyết định tài chính/inventory nếu freshness không đủ.

## 21. API composition khi vẫn cần gọi nhiều nguồn

Nếu chọn BFF, tránh gọi tuần tự tất cả upstream APIs.

### 21.1. Parallel fan-out

Gọi độc lập song song trong cùng deadline có thể giảm latency so với gọi tuần tự. Nhưng cần giới hạn concurrency và tổng số requests.

### 21.2. Deadline budget

Nếu màn hình có latency budget 500 ms, không thể để mỗi upstream timeout 500 ms rồi cộng lại. Chia ngân sách theo criticality và giữ thời gian serialize/response.

### 21.3. Partial result

Xác định nguồn nào critical và nguồn nào optional. Ví dụ Order core cần có; Customer display name có thể hiển thị fallback; shipment tracking có thể stale.

### 21.4. N+1 requests

Không gọi Payment API một lần cho mỗi order row. Dùng batch endpoint, bulk query hoặc projection. API owner có thể cung cấp operation batch có authorization/quotas rõ.

### 21.5. Circuit breaker và caching

BFF cần timeout, retry bounded, circuit breaker và cache phù hợp. Cache không thay owner truth; TTL và invalidation cần semantics.

## 22. Security, tenant isolation và privacy

Một read model tổng hợp thường chứa dữ liệu nhạy cảm từ nhiều domain, nên có thể tạo blast radius lớn hơn từng projection riêng lẻ.

### 22.1. Authorization ở query boundary

Summary API phải kiểm tra user identity và role, tenant scope, quyền xem Order/Payment/Customer, region hoặc organizational scope, field-level restrictions và purpose of use nếu policy yêu cầu.

Không dựa vào việc UI ẩn cột để bảo vệ dữ liệu. Authorization phải được enforce server-side.

### 22.2. Tenant key trong mọi query

Nếu multi-tenant, primary key/index/query cần bao gồm tenant scope phù hợp. Mọi lookup, cursor, cache key và projection update phải giữ tenant boundary. Tránh chỉ query theo orderId nếu ID có thể đoán hoặc trùng giữa tenants.

### 22.3. Field-level data minimization

Màn hình hỗ trợ có thể cần display name và masked contact; không nhất thiết cần raw address, full card data hoặc identity documents. Chỉ ingest field có purpose rõ.

### 22.4. Retention và deletion propagation

Nếu Customer contact bị xóa/ẩn danh, projection phải nhận tombstone hoặc deletion workflow và xử lý cache/export liên quan. Projection là một bản sao dữ liệu, nên nằm trong data map và retention policy.

### 22.5. Audit

Ghi audit cho truy cập nhạy cảm, export lớn và administrative searches theo policy. Không log raw PII/token hoặc đưa customerId/orderId vào metric labels cardinality cao.

## 23. Cache và invalidation

Có thể có nhiều tầng:

~~~text
UI cache
   ↓
API/CDN cache
   ↓
Read Model DB
   ↓
Projection pipeline
   ↓
Domain sources
~~~

Cần phân biệt cache response API, cache query result, cache object trong application, materialized projection và browser state.

### 23.1. TTL theo semantics

Order status và Payment status có thể cần TTL ngắn hơn static product metadata. Không dùng một TTL cho mọi fields.

### 23.2. Invalidation theo event

Có thể invalidate cache khi projection version tăng. Event invalidation phải idempotent và xử lý event đến trễ; version token có thể an toàn hơn delete key mù.

### 23.3. Cache key

Bao gồm tenant, user/role scope nếu response khác theo quyền, filters, sort và cursor. Không cache response chứa PII chung giữa các principals.

### 23.4. Cache stampede

Khi key hết hạn đồng loạt, nhiều requests có thể cùng query DB. Dùng request coalescing, jittered TTL hoặc stale-while-revalidate nếu policy cho phép.

## 24. Rebuild và backfill projection

Projection cần có cách tạo lại khi schema thay đổi, consumer bug đã ghi sai dữ liệu, read model mất dữ liệu, cần thêm field, cần reprocess events hoặc source gửi correction lịch sử.

### 24.1. Nguồn rebuild

Có thể dùng domain event history, owner API bulk snapshot, CDC snapshot + log stream, data warehouse/curated snapshot nếu semantics phù hợp, hoặc combination snapshot + incremental events.

Không giả định broker retention đủ dài cho mọi rebuild. Phải biết nguồn lịch sử nào có authoritative data.

### 24.2. Snapshot + watermark

Quy trình ví dụ:

1. Chọn source snapshot tại watermark W.
2. Load snapshot vào projection generation mới.
3. Đọc các events sau W.
4. Apply theo version/order/idempotency.
5. Reconcile counts và aggregates.
6. Đưa read traffic sang generation mới.
7. Retire generation cũ sau thời gian quan sát.

Nếu snapshot không nhất quán với watermark, có thể bỏ sót hoặc áp dụng hai lần thay đổi. Phải hiểu connector/owner guarantees.

### 24.3. Blue-green projection

Dùng hai generations:

~~~text
Projection v1 (active) ──► Summary API
Projection v2 (building)
          │
          ├── snapshot + replay
          ├── validate
          └── cutover
~~~

Giảm downtime khi schema rebuild lớn. Cần kiểm soát storage cost, dual processing và atomic routing switch.

### 24.4. Replay không tạo side effects

Projection consumer chỉ nên cập nhật read model. Nếu replay cũng gửi email, charge payment hoặc kích hoạt workflow, rebuild có thể gây tác động ngoài ý muốn. Tách projection processing khỏi business side-effect handlers.

## 25. Reconciliation và data quality

Một projection có thể sai dù consumer không báo lỗi. Ví dụ mapping REFUNDED thành CAPTURED, hoặc một source event bị bỏ qua.

### 25.1. Kiểm tra theo domain

- Order counts/status totals khớp với Order source.
- Payment amounts/currency totals khớp Payment source theo semantics.
- Latest shipment state/version khớp Fulfillment.
- Customer projection chỉ chứa records được phép.
- References có tenant scope đúng.
- Không có projection row orphan ngoài policy.

### 25.2. Không so sánh byte một cách máy móc

Timezone normalization, decimal scale, enum mapping và snapshot semantics có thể làm giá trị khác dạng nhưng đúng nghĩa. Reconciliation cần canonicalize theo contract.

### 25.3. Mismatch workflow

1. Phát hiện mismatch và ghi source keys/version.
2. Phân loại missing, duplicate, stale, mapping bug hoặc legitimate snapshot.
3. Xác định authoritative owner.
4. Rebuild/correction projection theo owner-approved path.
5. Xác nhận downstream query và user-visible behavior.
6. Lưu audit, metric và root cause.

### 25.4. Reconciliation không ghi ngược vào source

Projection team không được sửa Order/Payment DB để khớp bảng đọc. Nếu source sai, owner xử lý; nếu projection sai, projection được rebuild/correct.

## 26. Observability và SLO cho read model

Các metric nên có:

| Nhóm | Metric | Mục đích |
| --- | --- | --- |
| Ingestion | Event received/second | Throughput |
| Delivery | Broker lag, oldest event age | Độ trễ |
| Processing | Processing duration, error rate | Consumer health |
| Dedup | Duplicate count | Delivery behavior |
| Ordering | Version gap/stale event dropped | Event sequence |
| Projection | Applied source version/time | Freshness |
| Quality | Reconciliation mismatch count/age | Correctness |
| Query | p50/p95/p99 latency | UI performance |
| Query | Error/timeout rate | Availability |
| Database | Connections, CPU, locks, I/O | Capacity |
| Security | Denied access, tenant mismatch | Protection |
| Lifecycle | Rebuild duration, backlog | Recovery |

### 26.1. Freshness SLO end-to-end

Đo từ thời điểm source commit/event occurrence đến khi field được áp dụng trong projection. Chỉ đo broker lag chưa đủ vì consumer processing hoặc DB write có thể chậm.

### 26.2. Query SLO

Ví dụ p95 dưới 300 ms cho danh sách có filter phổ biến; con số phải đo bằng production-like traffic, dataset size và authorization checks.

### 26.3. Business SLI

Đo tỷ lệ màn hình hiển thị đúng summary cho những order đủ điều kiện, tỷ lệ records có đủ required fields và thời gian cập nhật status sau source change.

### 26.4. Traceability

Propagate trace/correlation metadata từ source event tới projection apply. Ghi source service, event type/version và projection generation. Không dùng IDs có cardinality lớn làm metric dimensions.

## 27. Kiểm thử projection

### 27.1. Contract tests

- Producer event schema đúng.
- Consumer đọc các versions được hỗ trợ.
- Unknown enum/null/optional fields.
- Unit/currency/timezone semantics.
- Event type và ownership.

### 27.2. Projection unit tests

- Mapping từng source field.
- Full snapshot vs delta behavior.
- Aggregate summary rules.
- Null vs unknown vs stale.
- Duplicate/version handling.
- Tombstone/deletion.
- Multi-tenant isolation.

### 27.3. Integration tests

- Inbox + projection update trong một transaction.
- Outbox/event ingestion.
- Broker redelivery.
- DB upsert/concurrent update.
- Replay/backfill.
- Rebuild generation/cutover.
- Query pagination/filter/sort.

### 27.4. Performance tests

- Dataset realistic.
- Cardinality và skew.
- Concurrent UI users.
- Filter combinations.
- Large tenant/noisy neighbor.
- Query plan/index selectivity.
- Event burst và backlog recovery.
- DB connection limits.

### 27.5. Failure tests

- Customer event tới trễ.
- Payment event duplicate.
- Shipment event out-of-order.
- Source unavailable.
- Projection DB unavailable.
- Consumer crash giữa commit và ack.
- Schema incompatibility.
- Tenant deletion.
- Rebuild giữa lúc traffic tăng.

Một test chỉ kiểm tra API trả 200 không chứng minh projection đúng.

## 28. Thiết kế BFF và projection cùng nhau

Một kiến trúc hybrid có thể chia:

- Order Summary Projection: danh sách và filters.
- Order Detail BFF: lấy thông tin chi tiết mới từ owners khi mở một order.
- Owner APIs: thao tác nghiệp vụ nhạy cảm.
- Analytics Warehouse: báo cáo lịch sử.

~~~text
                         Admin UI
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
      Order Summary API             Order Detail BFF
              │                    ┌──────┼───────┐
              ▼                    ▼      ▼       ▼
       Summary Read DB           Order  Payment Fulfillment
              ▲
              │
       Projection Processor
              ▲
              │
      Domain Events / CDC
~~~

Danh sách không cần gọi năm APIs cho mỗi row. Khi mở chi tiết, BFF có thể truy vấn owner APIs song song theo deadline và hiển thị partial sections nếu một upstream lỗi.

### 28.1. Quyền sở hữu BFF

BFF sở hữu presentation composition và response shape cho frontend. Nó không sở hữu authoritative payment/order rules. Những rule nghiệp vụ phải ở domain owner hoặc một service có ownership rõ.

### 28.2. Tránh BFF thành distributed monolith

Nếu BFF chứa logic state transitions, cập nhật DB domain và phải deploy cùng mọi upstream, nó đã vượt vai trò composition. Giữ BFF mỏng về business authority và có contract tests.

## 29. Tránh các lỗi thiết kế thường gặp

**1. Gọi tất cả services theo từng row.** Tạo N+1 requests, latency và rate-limit pressure.

**2. JOIN trực tiếp các service databases.** Phá schema/data ownership và khiến query phụ thuộc internal implementation.

**3. Dùng một projection cho mọi màn hình.** Grain và query patterns khác nhau làm schema phình to, khó index và khó hiểu.

**4. Không xác định grain.** Join one-to-many làm duplicate rows, pagination và aggregates sai.

**5. Dùng projection như nguồn authoritative.** Một bản sao trễ không được quyết định payment, inventory hoặc order transition.

**6. Không lưu source versions.** Event cũ có thể ghi đè dữ liệu mới.

**7. Xử lý partial event bằng full-row overwrite.** Field không có trong payload bị ghi null hoặc mất dữ liệu.

**8. Không deduplicate.** Event redelivery làm amount/count hoặc state bị cập nhật lặp.

**9. Không định nghĩa freshness.** UI không biết dữ liệu stale bao lâu và người dùng hiểu sai.

**10. Null có nhiều nghĩa.** Không phân biệt chưa có dữ liệu, không áp dụng, bị ẩn, unknown và lỗi nguồn.

**11. Summary status tự suy đoán.** Các team tính trạng thái tổng hợp khác nhau và tạo mâu thuẫn.

**12. Không có rebuild path.** Một bug projection buộc phải sửa từng row bằng tay.

**13. Rebuild gây side effects.** Replay event làm gửi email hoặc kích hoạt workflow lần nữa.

**14. Bỏ qua tenant scope trong cache/index.** Có thể lộ dữ liệu tenant khác.

**15. Copy PII không cần thiết.** Mỗi projection trở thành một nơi phải bảo vệ, audit và xóa.

**16. Không tính query/index cost.** Read model cập nhật nhanh nhưng query chậm hoặc ngược lại.

**17. Chỉ đo broker lag.** Consumer DB write hoặc projection apply có thể vẫn chậm.

**18. Không có reconciliation.** Projection sai âm thầm trong thời gian dài.

**19. Bắt frontend ghép dữ liệu nghiệp vụ.** Business rules bị lặp ở nhiều clients.

**20. Gọi projection là real-time mà không có SLO.** Không có deadline/freshness evidence để chứng minh.

## 30. Runbook: màn hình hiển thị trạng thái cũ

1. Xác định orderId, tenant và field đang stale.
2. Kiểm tra authoritative source state/version tại owner.
3. Xác định source event tương ứng và occurred/committed time.
4. Kiểm tra outbox/publisher hoặc CDC offset.
5. Kiểm tra broker lag, partition và message retention.
6. Kiểm tra projection consumer error/retry/DLQ.
7. Kiểm tra inbox/dedup và applied source version.
8. Kiểm tra projection DB commit, cache và API response cache.
9. Phân loại stale do event chưa tới, event bị bỏ qua, version gap, mapping bug hay cache.
10. Replay/rebuild/correct projection theo runbook, không sửa owner data.
11. Xác nhận UI và freshness SLO.
12. Ghi incident evidence, owner và corrective action.

## 31. Runbook: projection thiếu một phần dữ liệu

Ví dụ Order có nhưng Customer summary trống.

1. Xác nhận Customer ID và tenant reference hợp lệ.
2. Kiểm tra Customer source có record và quyền chia sẻ field.
3. Kiểm tra Customer event có được phát/publish.
4. Kiểm tra consumer nhận event và schema version.
5. Kiểm tra projection row có được tạo/update theo đúng source version.
6. Xác định đây là missing, intentionally hidden, deleted hay not yet enriched.
7. Nếu cần fetch snapshot, gọi owner API theo rate limit.
8. Nếu event bị mất, backfill/replay có idempotency.
9. Kiểm tra privacy/authorization trước khi hiển thị.
10. Cập nhật partial status và freshness metadata.
11. Reconcile các records cùng loại để tìm blast radius.
12. Cập nhật alert/test để phát hiện sớm.

## 32. Runbook: projection rebuild

1. Xác định nguyên nhân rebuild và generation/schema version mới.
2. Chọn authoritative sources và snapshot/watermark.
3. Ước lượng data volume, throughput, storage và load budget.
4. Tạo read model generation mới với index phù hợp.
5. Backfill snapshot có checkpoint.
6. Replay incremental events sau watermark.
7. Validate counts, aggregates, versions và samples.
8. Chạy shadow queries và so sánh response semantics.
9. Chuyển API routing sang generation mới theo plan.
10. Theo dõi latency, freshness, error và mismatch.
11. Giữ generation cũ trong rollback window.
12. Retire generation cũ theo retention/security policy.

Không chạy rebuild đồng thời với full traffic nếu DB không đủ capacity; có thể throttle hoặc dùng replica/snapshot phù hợp.

## 33. Ví dụ code: projection handler

Mã giả Java minh họa handler cho event Order snapshot:

~~~java
public final class OrderSnapshotHandler {
    private final InboxRepository inbox;
    private final OrderSummaryRepository summaries;

    public void handle(OrderSnapshotChanged event) {
        if (!inbox.tryRecord("order-summary", event.eventId())) {
            return;
        }

        summaries.applyOrderSnapshotIfNewer(
            event.tenantId(),
            event.orderId(),
            event.aggregateVersion(),
            event.orderStatus(),
            event.totalMinorUnits(),
            event.currency(),
            event.createdAt()
        );
    }
}
~~~

Trong implementation thật, tryRecord và applyOrderSnapshotIfNewer phải nằm trong cùng transaction local để inbox và projection update atomic. Nếu handler crash trước commit, message có thể redeliver; nếu crash sau commit trước ack, dedup xử lý lần lặp.

### 33.1. Không cho event Order ghi field Payment

Order handler chỉ cập nhật phần Order-owned fields. Payment handler cập nhật Payment-owned fields. Cùng một projection row có thể được cập nhật từ nhiều handlers, nên cần transaction/concurrency control để tránh lost updates.

### 33.2. Partial update an toàn

Repository nên có operation theo source section, ví dụ applyPaymentSnapshotIfNewer, thay vì save một entity đầy đủ được dựng từ event thiếu field.

### 33.3. Version guard

Version guard phải atomic tại database. Đọc version trong application rồi update không điều kiện vẫn có race giữa hai workers.

## 34. Ví dụ SQL: cập nhật phần Payment có version

Một cách triển khai PostgreSQL minh họa:

~~~sql
UPDATE order_summary
SET payment_status = :payment_status,
    captured_minor_units = :captured_minor_units,
    payment_version = :incoming_version,
    projection_updated_at = now()
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND COALESCE(payment_version, 0) < :incoming_version;
~~~

Nếu chưa có row Order summary, consumer cần lưu event pending hoặc tạo skeleton row với trạng thái nguồn chưa có. Cần xử lý concurrent upsert và foreign references theo policy.

Không dùng COALESCE(version, 0) nếu version có thể âm hoặc semantics version khác; ví dụ giả định version bắt đầu từ số dương.

## 35. Ví dụ schema cho source freshness

Có thể lưu trạng thái cập nhật theo từng source:

~~~sql
CREATE TABLE projection_source_state (
    tenant_id UUID NOT NULL,
    entity_id UUID NOT NULL,
    source_name VARCHAR(50) NOT NULL,
    source_version BIGINT,
    source_event_at TIMESTAMPTZ,
    applied_at TIMESTAMPTZ NOT NULL,
    freshness_state VARCHAR(24) NOT NULL,
    PRIMARY KEY (tenant_id, entity_id, source_name)
);
~~~

Bảng này giúp xác định section nào stale. Có thể thay bằng metadata columns trên main table hoặc pipeline watermarks tùy quy mô. Không tạo quá nhiều tables nếu không có nhu cầu query/operations tương ứng.

## 36. Data deletion và tombstones

Nếu Order bị xóa/hủy hoặc Customer bị yêu cầu xóa dữ liệu, projection phải xử lý đúng semantics.

- Event OrderCancelled không nhất thiết có nghĩa xóa order summary.
- Event OrderDeleted có thể yêu cầu xóa row hoặc giữ tombstone.
- Customer profile deletion có thể yêu cầu pseudonymize display fields nhưng giữ order history theo policy.
- Search/cache/export có thể cần xóa hoặc expire.
- Backups và event history có retention riêng.

### 36.1. Tombstone

Tombstone giúp consumer biết entity đã bị xóa/ẩn danh, tránh event cũ tạo lại projection. Cần giữ version để một stale snapshot không resurrect record.

### 36.2. Privacy workflow

Một deletion request nên theo dõi từng downstream consumer và xác nhận completion/exception. “Đã xóa ở Customer DB” chưa chứng minh summary projection và cache đã xử lý.

## 37. Security trong query API

### 37.1. Filter theo tenant server-side

Không tin tenantId do client tự truyền nếu user không có quyền. Server lấy tenant scope từ identity/authorization context hoặc kiểm tra quyền explicit.

### 37.2. Field-level visibility

Có thể cùng một projection lưu field nhưng response serializer quyết định field nào user được xem; tuy nhiên lưu dữ liệu vẫn cần purpose/access controls. Với field rất nhạy cảm, cân nhắc không ingest vào projection.

### 37.3. Export

Export nhiều rows có nguy cơ lớn hơn query một trang. Cần authorization, audit, rate limit, masking và retention của file export.

### 37.4. Query abuse

Giới hạn page size, sort/filter combinations và expensive wildcard searches. Dùng prepared statements/parameter binding; không ghép SQL từ input.

### 37.5. Cache privacy

Cache key và cache policy phải phản ánh tenant/role/field scope. Không dùng shared cache response nếu hai users có quyền xem khác nhau.

## 38. Tổ chức ownership và vận hành

Một read model cần owner dù dữ liệu gốc thuộc nhiều services.

| Vai trò | Trách nhiệm |
| --- | --- |
| Domain producer owner | Semantics, event/API contract, authoritative state |
| Projection owner | Transformation, schema, freshness, rebuild, data quality |
| Platform team | Broker, runtime, database platform, secrets/observability tooling |
| API/BFF owner | Query contract, auth, pagination, response performance |
| Security/privacy | Classification, access policies, deletion/retention guidance |
| UI team | Render states, partial data, user interactions |
| On-call | Alert triage, runbooks, escalation |

Một người/đội cần accountable cho projection outcome và SLO. Việc các source teams sở hữu dữ liệu gốc không có nghĩa không ai chịu trách nhiệm cho bản tổng hợp.

### 38.1. Service catalog

Ghi projection purpose và consumers, grain/key, sources/contracts, owner/on-call, freshness SLO, data classification/retention, rebuild procedure, dashboards/runbooks và API version/deprecation.

### 38.2. Change management

Khi producer đổi schema, cần biết projection consumer có bị ảnh hưởng không. Contract tests và dependency catalog hỗ trợ phát hiện trước deploy.

## 39. Kế hoạch triển khai theo giai đoạn

### Giai đoạn 1 — Discovery

- Liệt kê màn hình/use cases.
- Xác định fields, filters, sort và pagination.
- Ghi source owner và semantics.
- Đo traffic/latency/freshness needs.
- Phân loại dữ liệu nhạy cảm.

### Giai đoạn 2 — Design

- Chọn API composition, projection hoặc hybrid.
- Chốt grain, keys và schema.
- Định nghĩa contracts/events.
- Chọn consistency/freshness SLO.
- Thiết kế authorization và retention.
- Lập ADR và ownership.

### Giai đoạn 3 — Build

- Tạo processor, inbox/dedup và version guards.
- Tạo read model schema/indexes.
- Xây query API và pagination.
- Thêm observability/reconciliation.
- Viết tests.

### Giai đoạn 4 — Backfill và shadow

- Lấy snapshot/watermark.
- Backfill lịch sử.
- Stream incremental events.
- So sánh query output với nguồn hoặc API composition.
- Kiểm tra performance và data quality.
- Không dùng shadow results làm authoritative writes.

### Giai đoạn 5 — Cutover

- Canary users/tenants hoặc route.
- Theo dõi SLO/freshness/mismatch.
- Bật UI theo feature flag.
- Có fallback rõ nếu projection chưa đáp ứng.
- Mở rộng traffic sau khi đạt exit criteria.

### Giai đoạn 6 — Operate

- Theo dõi lag và quality.
- Reconcile định kỳ.
- Thử rebuild/restore.
- Review privacy/retention.
- Cập nhật catalog và contracts.

## 40. Ví dụ tiêu chí nghiệm thu

Các ngưỡng dưới đây chỉ minh họa; đội dự án phải chốt baseline và mục tiêu thật:

| Tiêu chí | Ví dụ điều kiện |
| --- | --- |
| Query latency | p95 dưới 300 ms cho filter phổ biến |
| API availability | Theo SLO của admin screen |
| Order freshness | 99% updates dưới 5 giây |
| Payment freshness | 99% updates dưới 10 giây |
| Missing required fields | Dưới ngưỡng được owner phê duyệt |
| Tenant isolation | Không có cross-tenant result trong security tests |
| Duplicate events | Không làm thay đổi kết quả nghiệp vụ |
| Out-of-order | Không làm projection lùi version |
| Rebuild | Hoàn tất trong RTO đã định |
| Reconciliation | Critical mismatch được phát hiện và xử lý trong deadline |
| Privacy | Deletion/retention tests pass |
| Pagination | Không duplicate/missing rows trong cursor contract |

Không chỉ nghiệm thu bằng “màn hình hiển thị dữ liệu”. Cần chứng minh data correctness, security, freshness, recovery và performance.

## 41. Bài tập tình huống

### Bài A — Chọn API composition hay projection

Admin list hiển thị 100 orders/page từ Order, Customer, Payment, Shipment. Mỗi lần load hiện tại tạo 401 requests.

**Câu hỏi:** lựa chọn nào phù hợp?

**Gợi ý:** projection cho danh sách hoặc batch APIs có thể giảm N+1. Nếu read-heavy và chấp nhận freshness, materialized view là lựa chọn tốt. Detail screen có thể dùng BFF gọi owners.

### Bài B — Một Order có nhiều shipments

JOIN order với shipment tạo 3 rows cho một order và pagination bị lặp.

**Câu hỏi:** sửa grain thế nào?

**Gợi ý:** một summary row/order với latest shipment/count; child table hoặc detail endpoint cho từng shipment. Không paginate trên join one-to-many mà không định nghĩa grouping.

### Bài C — Payment event tới trễ

Order projection mới nhưng paymentStatus cũ 20 phút.

**Câu hỏi:** có nên hiển thị FAILED?

**Gợi ý:** không. Hiển thị stale/unknown và timestamp; điều tra lag/consumer/DLQ. Không suy diễn trạng thái từ việc thiếu event.

### Bài D — Event version lùi

Projection đã apply Payment version 12, sau đó nhận version 11.

**Câu hỏi:** xử lý ra sao?

**Gợi ý:** nếu snapshot, bỏ version cũ; nếu delta, xử lý sequence gap/replay theo contract. Version phải theo Payment aggregate, không so với Order version.

### Bài E — Customer bị xóa

Customer source phát deletion event; order history cần giữ theo policy.

**Câu hỏi:** projection nên xóa toàn bộ order summary?

**Gợi ý:** không tự động. Xử lý customer fields theo privacy/retention policy, giữ order state nếu có căn cứ, tombstone và audit downstream.

### Bài F — Read model sai amount

Payment source lưu amount minor units, projection hiểu là decimal major units.

**Câu hỏi:** kiểm tra nào phát hiện?

**Gợi ý:** contract ghi currency/unit/precision, data quality aggregates và reconciliation. Không so sánh số raw thiếu semantics.

### Bài G — Projection rebuild gửi email

Consumer dùng chung handler với notification workflow. Replay 2 tháng events gửi email lại.

**Câu hỏi:** sai ở đâu?

**Gợi ý:** tách pure projection processing khỏi side-effect handlers. Rebuild phải idempotent và không phát business actions.

### Bài H — Cache lộ dữ liệu tenant

Hai tenant có cùng filter/query key, response cache không có tenant scope.

**Câu hỏi:** sửa thế nào?

**Gợi ý:** tenant authorization trong API, cache key chứa scope phù hợp, test cross-tenant và audit.

### Bài I — API projection quá stale

UI cần xác nhận Payment captured trước khi cho phép phát hành shipment.

**Câu hỏi:** có dùng summary projection không?

**Gợi ý:** không dùng stale projection làm quyết định authoritative. Gọi Payment/Order owner theo contract hoặc dùng workflow command xác nhận trạng thái.

### Bài J — Source không có events

Legacy Customer Service chỉ có DB và nightly export.

**Câu hỏi:** có thể tạo projection không?

**Gợi ý:** có thể dùng snapshot/batch/CDC có owner và watermark; xác định freshness phù hợp, migration path và tránh query trực tiếp schema không kiểm soát.

### Bài K — Một summary enum phình lớn

UI muốn một field status kết hợp Order, Payment, Inventory, Shipment.

**Câu hỏi:** có nên tạo mọi tổ hợp thành enum?

**Gợi ý:** thường không. Giữ trạng thái từng domain và một summary rule có owner; biểu diễn unknown/stale/pending rõ ràng.

### Bài L — Projection và source cùng ghi

Projection service sửa trực tiếp Order DB khi phát hiện mismatch.

**Câu hỏi:** vì sao nguy hiểm?

**Gợi ý:** phá ownership và có thể bypass state machine/audit. Projection owner sửa projection; source owner sửa authoritative data qua command/API.

## 42. Checklist thiết kế read model

### Nhu cầu màn hình

- [ ] Use cases, fields, filters, sorting và pagination được liệt kê.
- [ ] Grain của mỗi row rõ ràng.
- [ ] One-to-many relationships được xử lý có chủ đích.
- [ ] Operational và analytical needs được phân biệt.
- [ ] Freshness và latency expectations được chốt.

### Ownership và data contracts

- [ ] Authoritative source cho từng field.
- [ ] Current state, snapshot và projection phân biệt.
- [ ] Event/API contracts có version và semantics.
- [ ] Amount, currency, timezone, null và enum được định nghĩa.
- [ ] Source versions/watermarks được lưu đủ.
- [ ] Projection có owner và data lineage.

### Ingestion và correctness

- [ ] Outbox/CDC/batch guarantees được hiểu.
- [ ] Inbox/dedup và idempotency.
- [ ] Ordering/version gap handling.
- [ ] Partial updates không ghi đè field của source khác.
- [ ] Tombstone/deletion handling.
- [ ] Reconciliation và correction workflow.
- [ ] Rebuild/backfill có checkpoint và watermark.

### Query và UI

- [ ] Index theo query access patterns.
- [ ] Pagination ổn định.
- [ ] API có auth, tenant scope và limits.
- [ ] Partial/stale/unknown states thể hiện rõ.
- [ ] Cache key và TTL phù hợp.
- [ ] Sensitive fields được tối thiểu hóa.

### Vận hành

- [ ] Freshness, query SLO và business SLI.
- [ ] Broker lag, retries, DLQ và applied versions.
- [ ] Database capacity/locks/connections.
- [ ] Trace/correlation qua projection.
- [ ] Runbooks cho stale/missing/rebuild.
- [ ] Backup/restore và retention.
- [ ] Security/access review và deletion propagation.

## 43. Câu hỏi cho architecture review

1. Màn hình phục vụ quyết định nào và ai sử dụng?
2. Một row đại diện cho entity/grain nào?
3. Nguồn authoritative của mỗi field là đâu?
4. Có field nào là snapshot lịch sử thay vì current state?
5. API composition có gây fan-out/N+1 không?
6. Projection có thật sự cần thiết và lợi ích query là gì?
7. Source events có đủ semantics và version không?
8. Snapshot/backfill được nối với incremental stream bằng watermark nào?
9. Duplicate/out-of-order/partial updates được xử lý ra sao?
10. Freshness SLO theo source và overall là gì?
11. User có cần read-your-writes hoặc current Payment state không?
12. Partial failure được biểu diễn như thế nào?
13. Query API enforce tenant/role/field authorization ở đâu?
14. PII nào được copy, retention và deletion thế nào?
15. Projection có thể rebuild mà không gây side effects không?
16. Reconciliation kiểm tra những business invariants nào?
17. Ai on-call và ai chịu trách nhiệm data quality?
18. Query performance và pipeline lag được đo ở production ra sao?

## 44. Tổng kết

Màn hình tổng hợp nhiều dịch vụ cần một mô hình đọc phù hợp với **câu hỏi mà người dùng muốn trả lời**, không phải bản sao nguyên trạng của mọi database nguồn. API composition phù hợp khi số nguồn ít, cần dữ liệu mới và query đơn giản. Materialized projection phù hợp khi màn hình đọc nhiều, tổng hợp nhiều domain và cần query nhanh, filter/sort/pagination ổn định. Hybrid kết hợp projection cho danh sách với owner APIs cho chi tiết hoặc quyết định nhạy cảm.

Một read model đáng tin cậy cần:

1. **Grain và semantics rõ:** biết một row đại diện cho gì và từng field đến từ đâu.
2. **Ownership đúng:** domain service giữ authoritative state; projection chỉ sở hữu dữ liệu dẫn xuất và quy tắc trình bày được công bố.
3. **Ingestion an toàn:** contracts, version, idempotency, ordering và snapshot/watermark.
4. **Consistency có giới hạn:** freshness SLO, stale/unknown states, read-your-writes và reconciliation.
5. **Query được tối ưu:** schema/index, pagination, cache và authorization theo tenant.
6. **Vận hành được:** observability, rebuild, backfill, deletion, runbooks và owner rõ ràng.

Đừng để frontend tự JOIN các service hoặc để projection trở thành nguồn sự thật thứ hai. Hãy tạo một contract đọc ổn định, tối ưu cho use case, minh bạch về freshness và có thể tái tạo từ các nguồn authoritative. Khi đó màn hình có thể cung cấp trải nghiệm nhanh và nhất quán theo đúng mức cam kết mà nghiệp vụ yêu cầu, trong khi các microservices vẫn giữ được quyền sở hữu dữ liệu của mình.
