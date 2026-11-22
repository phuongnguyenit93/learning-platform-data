# Tách quyền sở hữu dữ liệu và giảm truy cập cơ sở dữ liệu dùng chung trong Microservices

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Chuyển đổi kiến trúc.
>
> **Mục tiêu:** Chuyển từ mô hình nhiều service cùng đọc/ghi một database hoặc schema sang mô hình trong đó **mỗi bounded context có quyền sở hữu rõ ràng đối với dữ liệu authoritative của mình**. Việc chuyển đổi phải diễn ra an toàn qua các giai đoạn kiểm kê, xác định owner, tạo interface, sao chép dữ liệu, đồng bộ thay đổi, chuyển quyền ghi, chuyển consumers và loại bỏ quyền truy cập cũ. Đây là một quá trình thay đổi kiến trúc và vận hành, không chỉ là thao tác tách bảng sang database khác.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao nhiều microservices truy cập trực tiếp cùng database tạo ra coupling về schema, transaction, release, security và ownership.
2. Phân biệt **shared physical database cluster**, shared database, shared schema, shared tables và shared credentials; nhận diện mức độ coupling ở từng trường hợp.
3. Xác định authoritative owner theo domain, operation và field; phân biệt data owner với service owner, database custodian và consumer.
4. Kiểm kê đầy đủ readers, writers, jobs, reports, triggers, stored procedures, ETL/CDC và công cụ vận hành đang truy cập dữ liệu cũ.
5. Thiết kế mục tiêu database-per-service hoặc schema ownership riêng mà không mặc định mỗi service phải có một máy database độc lập.
6. Chọn API, domain event, CDC, outbox, read model hoặc data product để thay thế truy cập SQL xuyên ranh giới.
7. Lập kế hoạch migration có backfill, incremental sync, validation, shadow read, write cutover, reconciliation và rollback.
8. Tránh dual-write không nguyên tử, hai authoritative writers, event replay gây side effects và foreign keys xuyên database không còn được enforce.
9. Giảm quyền truy cập dần bằng least privilege, database roles, audit và kiểm thử runtime để phát hiện consumer còn phụ thuộc.
10. Quản lý consistency, freshness, data deletion, backup/restore, schema evolution và sự cố trong thời kỳ coexistence.
11. Xây dựng runbook và checklist để chuyển đổi theo từng domain với phạm vi ảnh hưởng có kiểm soát.

Các tên bảng, service, SQL và ngưỡng trong bài là ví dụ. Cần xác minh theo database engine, transaction model, traffic, yêu cầu pháp lý, RTO/RPO và năng lực của tổ chức.

## 2. Vấn đề của database dùng chung

Một hệ thống ban đầu có thể dùng một PostgreSQL database:

~~~text
                    Shared PostgreSQL
                 ┌───────────────────────┐
                 │ customers             │
                 │ orders                │
                 │ payments              │
                 │ inventory             │
                 │ products              │
                 └───────────────────────┘
                    ▲       ▲       ▲
                    │       │       │
                 Customer  Order  Payment
                  Service Service Service
~~~

Mô hình này có thể hợp lý trong monolith hoặc giai đoạn đầu. Khi tách service, vấn đề xuất hiện nếu mỗi service được cấp quyền truy cập trực tiếp vào bảng của domain khác:

- Order Service đọc và cập nhật `customers.email`.
- Payment Service sửa `orders.payment_status`.
- Reporting Worker chạy JOIN trực tiếp giữa orders, payments và inventory.
- Một batch job cập nhật giá trị tồn kho ngoài Inventory Service.
- DBA chạy script sửa dữ liệu mà không có domain owner xác nhận.
- Mọi service dùng chung một database account có quyền rộng.

Khi đó ranh giới service chỉ nằm ở process và repository. **Quyền quyết định dữ liệu vẫn dùng chung**, nên một thay đổi schema ở Customer có thể làm Order hoặc Reporting lỗi mà không cần thay code ở chính những service đó.

### 2.1. Hệ quả thường gặp

| Vấn đề | Cách nó xuất hiện | Hậu quả |
| --- | --- | --- |
| Schema coupling | Service khác đọc trực tiếp cột nội bộ | Migration cần phối hợp nhiều đội |
| Multiple writers | Nhiều service cập nhật cùng record | Lost update, invariant bị phá |
| Release coupling | Các service phải deploy cùng thời điểm | Giảm khả năng phát hành độc lập |
| Hidden dependencies | Job/BI query dùng bảng mà không ai khai báo | Migration gây lỗi bất ngờ |
| Security overreach | Runtime credential có quyền rộng | Blast radius và nguy cơ rò rỉ lớn |
| Transaction coupling | Một transaction bao nhiều domain tables | Khó tách process và ownership |
| Data semantics drift | Mỗi consumer tự diễn giải trạng thái | Dữ liệu không nhất quán |
| Operational contention | Query của service này ảnh hưởng service khác | Khó phân bổ capacity và tìm root cause |
| Unclear accountability | Không rõ ai được phép sửa dữ liệu | Incident kéo dài, correction rủi ro |

### 2.2. Shared database không tự động là sai

Dùng chung một **database cluster vật lý** có thể là lựa chọn vận hành hiệu quả nếu:

- Mỗi domain có database/schema và role riêng.
- Quyền ghi được giới hạn theo owner.
- Consumer dùng contract thay vì đọc bảng nội bộ.
- Migration và backup có owner rõ.
- Có capacity isolation phù hợp.
- Việc dùng chung cluster không làm vi phạm security hoặc availability requirements.

Điều cần giảm là **coupling dữ liệu và quyền ghi xuyên domain**, không nhất thiết là số máy database.

## 3. Phân biệt các mức “dùng chung database”

| Mô hình | Mô tả | Rủi ro coupling |
| --- | --- | --- |
| Shared cluster | Nhiều database/schema cùng chạy trên một cụm vật lý | Chung CPU, memory, I/O, maintenance và failure domain |
| Shared database, separate schemas | Các domain dùng schema riêng trong cùng database | Có thể tách quyền, nhưng vẫn chung transaction/connection/maintenance boundary |
| Shared schema, separate tables | Service có bảng riêng nhưng cùng schema | Dễ tạo quan hệ và grants chéo |
| Shared tables, separate services | Nhiều service đọc/ghi cùng bảng | Coupling ownership cao |
| Shared credentials | Nhiều service dùng một account | Khó giới hạn và audit quyền |
| Cross-domain SQL | Service query trực tiếp bảng domain khác | Phụ thuộc schema và semantics nội bộ |
| Shared read model | Một projection được thiết kế cho nhiều consumers | Có thể phù hợp nếu owner, contract và freshness rõ |
| Data warehouse shared | Các domain xuất dữ liệu cho analytics | Phù hợp cho phân tích nếu không biến thành write path nghiệp vụ |

### 3.1. Database-per-service là nguyên tắc ownership

Database-per-service thường được hiểu là mỗi service có **kho dữ liệu logic thuộc quyền kiểm soát của service/domain**, và những service khác không truy cập trực tiếp vào storage nội bộ đó.

Nó không bắt buộc:

- Mỗi service có một VM/database server riêng.
- Mỗi service phải dùng một database engine khác.
- Không bao giờ chia sẻ dữ liệu.
- Không được xây data warehouse chung.
- Mọi query cross-domain đều phải là synchronous HTTP call.

Điều bắt buộc cần làm rõ là **ai được ghi dữ liệu authoritative, ai kiểm soát schema và consumer nhận dữ liệu qua contract nào**.

### 3.2. Chọn mức isolation theo rủi ro

Một số domain có thể cùng dùng PostgreSQL cluster nhưng database riêng. Một số workload nhạy cảm cần cluster, account, encryption key hoặc region riêng. Quyết định dựa trên isolation, scale, security, compliance, recovery và chi phí.

## 4. Xác định ownership trước khi di chuyển bảng

Không bắt đầu bằng cách chọn một bảng rồi copy. Trước tiên phải hiểu semantics của dữ liệu.

Ví dụ thương mại điện tử:

| Dữ liệu | Owner authoritative | Vì sao |
| --- | --- | --- |
| Hồ sơ khách hàng hiện tại | Customer | Quy tắc xác minh, cập nhật profile |
| Trạng thái vòng đời đơn hàng | Order | State machine và invariants của Order |
| Payment authorization/refund | Payment | Ledger và giao dịch thanh toán |
| Số lượng tồn kho/reservation | Inventory | Reservation, release, reconciliation |
| Product catalogue | Catalog | Nội dung và thuộc tính sản phẩm |
| Giá bán theo chương trình | Pricing | Quy tắc giá, thời gian hiệu lực |
| Shipment/tracking | Fulfillment | Hãng vận chuyển và trạng thái giao hàng |

Một bảng có thể chứa nhiều loại dữ liệu với ownership khác nhau. Ví dụ `orders` có cột `customer_email`, nhưng không có nghĩa Order sở hữu email hiện tại của Customer. Cột đó có thể là **snapshot giao dịch**.

### 4.1. Ownership theo semantics và thời điểm

Phân biệt:

- `customer.email`: email hiện tại do Customer/Identity quản lý.
- `order.shipping_address_snapshot`: địa chỉ được chốt cho đơn tại thời điểm đặt hàng, do Order sở hữu.
- `shipment.delivery_address`: hướng dẫn giao hàng đang được Fulfillment quản lý theo workflow.
- `payment.status`: trạng thái payment authoritative.
- `order.payment_state`: trạng thái tổng hợp của Order dựa trên kết quả Payment theo contract.

Hai field cùng tên hoặc cùng chứa email có thể có ý nghĩa, owner và retention khác nhau.

### 4.2. Một domain có thể có nhiều data assets

Order domain có thể sở hữu:

- Operational order database.
- Outbox events.
- Read model phục vụ Order API.
- Snapshot phục vụ audit.
- Archive phục vụ đối soát.

Các asset đó có lifecycle khác nhau nhưng cùng cần owner rõ.

## 5. Lập inventory toàn bộ truy cập database cũ

Đây thường là bước tốn công nhất. Một lần grep code không đủ vì còn job, BI, stored procedures, ad-hoc scripts và consumer bên ngoài.

### 5.1. Tìm readers

Ghi lại mọi thành phần:

- SELECT trực tiếp từ bảng domain khác.
- JOIN qua nhiều domain.
- View/materialized view.
- Stored procedure/function.
- Trigger gọi logic liên domain.
- Search indexing.
- Cache warm-up.
- Reporting/BI query.
- CDC/ETL/ELT pipeline.
- Data science notebook hoặc export.
- Admin console và support scripts.
- Batch jobs theo ngày/tháng/quý.

### 5.2. Tìm writers

Đặc biệt quan trọng:

- INSERT/UPDATE/DELETE.
- Upsert và bulk load.
- Stored procedures có side effects.
- Trigger tự thay đổi bảng khác.
- ORM cascade qua relationship.
- Migration scripts.
- Scheduled jobs.
- Admin tools và manual SQL.
- Import từ hệ thống bên ngoài.
- CDC consumers có write-back.
- Một service dùng credential chung nhưng code path hiếm khi chạy.

### 5.3. Tìm quyền và account

Kiểm kê:

- Database users/roles.
- Grants theo schema/table/sequence/function.
- Connection strings và secret references.
- Service accounts trong Kubernetes/cloud.
- CI migration credentials.
- DBA/admin accounts.
- Read-only accounts dùng cho BI.
- Credential rotation và ownership.

Một account được cấp quyền không chứng minh service thực sự sử dụng; một truy vấn không xuất hiện trong tracing cũng không chứng minh service không đọc bảng. Kết hợp static code/config, audit logs, query statistics và runtime observation.

### 5.4. Ma trận reader/writer

Ví dụ:

| Consumer | Dataset/table | Read/Write | Operation | Tần suất | Owner hiện tại | Mục tiêu |
| --- | --- | --- | --- | --- | --- | --- |
| Order Service | customers | Read | Validate customer | Mỗi checkout | Customer | Customer API/projection |
| Order Service | orders | Write | Create/update order | Cao | Order | Giữ tại Order DB |
| Payment Service | orders | Read + Write | Update payment_status | Cao | Mơ hồ | Payment API/event; Order cập nhật state |
| Reporting Worker | orders/payments | Read | Revenue report | Theo giờ | Analytics | Curated data product |
| Support Script | customers | Write | Manual correction | Hiếm | Customer | Owner-controlled correction API |
| Legacy Batch | inventory | Write | Reconcile stock | Ban đêm | Inventory | Inventory import/reconcile interface |

Mọi dòng chưa biết owner hoặc semantics phải được ghi thành **ownership gap** để giải quyết trước khi cutover.

## 6. Đo mức độ phụ thuộc hiện tại

Có thể đánh giá rủi ro theo:

- Số readers/writers của từng bảng.
- Số domain có quyền ghi.
- Số JOIN xuyên schema.
- Số stored procedures/triggers có side effects.
- Tỷ lệ truy cập không có owner.
- Số deploy phải phối hợp khi schema thay đổi.
- Tần suất query trực tiếp ngoài API/event.
- Tỷ lệ consumer có contract/version rõ.
- Khả năng quan sát và audit access.
- Độ khó backfill/replay/restore.

Không có ngưỡng phổ quát như “từ 3 readers trở lên phải tách”. Một bảng có 20 readers read-only với contract stable có thể ít rủi ro hơn một bảng chỉ có 2 writers không rõ quyền.

### 6.1. Query coupling khác business coupling

Một JOIN giữa Order và Customer có thể phản ánh nhu cầu đọc dữ liệu; nhưng việc query trực tiếp schema Customer là **coupling triển khai**. Có thể thay bằng API hoặc read model mà vẫn giữ quan hệ nghiệp vụ.

### 6.2. Baseline trước chuyển đổi

Thu thập:

- Query volume/latency theo consumer nếu database hỗ trợ.
- Lock contention và transaction duration.
- Error rate và timeout.
- Connection count và pool usage.
- Data freshness/replication lag.
- Deploy incidents và thời gian xử lý.
- Cost của cluster và storage.
- Data quality/reconciliation mismatch.

Baseline giúp đánh giá migration có thực sự giảm coupling hoặc tạo thêm chi phí.

## 7. Kiến trúc đích: domain sở hữu dữ liệu

Mục tiêu tham khảo:

~~~text
                 API Gateway / Clients
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
       Customer API   Order API   Payment API
             │            │            │
             ▼            ▼            ▼
        Customer DB    Order DB    Payment DB
             │            │            │
             └─────── Event Broker ────┘
                         │
                 ┌───────┼───────────┐
                 ▼       ▼           ▼
            Notification Fulfillment Analytics
             Projection  Projection  Warehouse
~~~

Nguyên tắc:

1. Mỗi domain/service có quyền ghi authoritative state của mình.
2. Consumer không query trực tiếp storage nội bộ của producer.
3. Consumer dùng API, event, CDC contract hoặc read model phù hợp.
4. Snapshot và projection có semantics riêng, không giả làm SoR.
5. Cross-domain workflow dùng saga/compensation hoặc orchestration phù hợp.
6. Mọi data flow có owner, security, retention và observability.
7. Shared infrastructure có thể tiếp tục được dùng nếu quyền và failure boundaries phù hợp.

### 7.1. Physical separation có thể tiến hóa

Giai đoạn đầu:

~~~text
PostgreSQL Cluster
  ├── customer_db / customer_role
  ├── order_db / order_role
  └── payment_db / payment_role
~~~

Sau đó, nếu Payment cần isolation hoặc scale riêng, có thể chuyển `payment_db` sang cluster khác mà consumer contract không phải thay đổi. **Logical ownership trước, physical relocation sau** thường giảm rủi ro.

## 8. Thay truy cập SQL xuyên domain bằng cơ chế nào?

Không có một cơ chế phù hợp cho mọi truy cập.

| Nhu cầu | Cơ chế phù hợp | Đánh đổi |
| --- | --- | --- |
| Cần xác minh giá trị hiện tại trước quyết định | Owner API/gRPC | Runtime latency/availability coupling |
| Cần biết thay đổi đã xảy ra | Domain event | Eventual consistency, duplicate/order |
| Cần bản sao gần thời gian thực từ legacy | CDC có quản lý | Schema coupling và pipeline operations |
| Cần query nhiều domain cho UI | Read model/API composition | Projection lag và rebuild |
| Cần báo cáo lịch sử lớn | Warehouse/data product | Không dùng làm write path nghiệp vụ |
| Cần tra cứu dữ liệu ít thay đổi | Cache/projection | Staleness và invalidation |
| Cần transaction trong một domain | Domain-owned database transaction | Không bao phủ transaction xuyên service |
| Cần workflow nhiều domain | Saga/orchestration | Compensation và trạng thái trung gian |

### 8.1. Owner API

Order muốn kiểm tra Customer đang active có thể gọi Customer API:

~~~text
Order Service
   │ GET /customers/{customerId}/eligibility
   ▼
Customer Service
   │
   ▼
Customer DB
~~~

Ưu điểm: owner giữ business rules và quyền quyết định. Nhược điểm: Order phụ thuộc latency/availability của Customer trong critical path.

Cần quy định timeout, auth scope, rate limit, retry có giới hạn và fallback. Không retry mù nếu operation có side effects.

### 8.2. Domain events

Customer thay đổi địa chỉ và phát `CustomerAddressChanged`. Order hoặc Notification có thể cập nhật projection nếu mục đích hợp lệ. Event biểu diễn sự kiện nghiệp vụ đã xảy ra, không nên chỉ phơi bày tên bảng và cột nội bộ.

### 8.3. CDC

Change Data Capture có thể đọc log thay đổi từ legacy DB để đồng bộ dữ liệu trong giai đoạn chuyển đổi hoặc đưa dữ liệu vào analytics. CDC hữu ích cho replication/backfill, nhưng **không tự tạo ra ownership rõ ràng** và không nên biến log bảng thành public business API không kiểm soát.

### 8.4. Read model

Nếu màn hình cần Customer name, Order status và Payment summary, một projection có thể tổng hợp các dữ liệu này. Projection có owner, contract, freshness SLO và rebuild strategy riêng. Consumer đọc projection thay vì JOIN trực tiếp các DB nội bộ.

## 9. Quy trình chuyển đổi tổng thể

Một migration an toàn thường chia thành các giai đoạn:

~~~text
Discover
   ↓
Assign ownership
   ↓
Define target contract/schema
   ↓
Create new owner storage and write path
   ↓
Backfill historical data
   ↓
Replicate ongoing changes
   ↓
Validate / shadow read / reconcile
   ↓
Cut over authoritative writes
   ↓
Move consumers to APIs/events/read models
   ↓
Revoke legacy access
   ↓
Retire old schema and update documentation
~~~

Không nhất thiết mỗi bước chỉ diễn ra một lần. Có thể chia theo bảng, operation, tenant, region hoặc consumer group. Nhưng cần biết chính xác **ai là writer authoritative trong từng thời điểm**.

### 9.1. Một migration cần có trạng thái và owner

Ví dụ:

| Workstream | Owner | Exit condition |
| --- | --- | --- |
| Inventory readers/writers | Domain + DBA | Đủ danh sách truy cập và evidence |
| Target schema | Owning team | Schema/constraints approved |
| Backfill | Data/platform | Record counts/checksums reconciled |
| Change replication | Producer/DBA | Lag trong mục tiêu và replay test pass |
| Write cutover | Domain owner | Single authoritative writer |
| Consumer migration | Consumer teams | Không còn direct DB reads |
| Access removal | Security/DBA | Legacy grants thu hồi và kiểm tra |
| Legacy retirement | Architecture/owner | Không còn dependency, backup/retention rõ |

## 10. Bước 1: xác định ownership gap và phạm vi cutover

Trước khi tạo database mới, trả lời:

- Bảng nào thuộc domain nào?
- Mỗi operation create/update/delete thuộc owner nào?
- Field nào là snapshot, projection hay authoritative?
- Các transaction hiện tại có ghi nhiều domain cùng lúc không?
- Có triggers/stored procedures cross-domain không?
- Có batch jobs chạy theo lịch hiếm không?
- Có consumer ngoài tổ chức hoặc BI query không?
- Khi dữ liệu xung đột, nơi nào có quyền quyết định?
- Ai chịu trách nhiệm correction và deletion?

**Không chuyển bảng theo tên service một cách máy móc.** Có bảng legacy chứa nhiều bounded contexts; cần tách semantics và ownership trước khi quyết định schema mới.

### 10.1. Ví dụ ownership gap

Bảng `orders` có các trường:

~~~text
id
customer_id
customer_email
payment_status
inventory_reserved
order_status
shipment_tracking
~~~

Có thể phân định:

- `order_status`: Order.
- `payment_status`: Payment là nguồn payment truth; Order giữ trạng thái tổng hợp theo event/command.
- `inventory_reserved`: Inventory sở hữu reservation; Order giữ reference/snapshot kết quả.
- `shipment_tracking`: Fulfillment sở hữu tracking; Order có projection cho UI.
- `customer_email`: snapshot nếu chốt tại thời điểm đặt hàng, hoặc bỏ nếu chỉ là bản sao không có mục đích.

Một table có thể phải chia thành nhiều data assets. Không bắt buộc mọi cột chuyển nguyên vẹn sang cùng một database mới.

## 11. Bước 2: thiết kế schema mới và invariants

Mỗi owner service phải định nghĩa:

- Entities/aggregates và keys.
- Constraints và unique indexes.
- Transaction boundaries.
- State transitions.
- Retention/archival.
- Encryption/classification.
- Backup/restore và RTO/RPO.
- Migration/versioning strategy.
- Read/write API hoặc events.
- Idempotency/reconciliation.

Ví dụ Order DB:

~~~sql
CREATE TABLE orders (
    order_id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    order_status VARCHAR(32) NOT NULL,
    currency CHAR(3) NOT NULL,
    total_minor_units BIGINT NOT NULL,
    aggregate_version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (total_minor_units >= 0)
);
~~~

Schema này chỉ là ví dụ. Các business constraints như trạng thái hợp lệ, currency và uniqueness của idempotency cần được định nghĩa đầy đủ theo domain.

### 11.1. Chọn canonical ID

Khi tách database, không nên tạo lại ID theo cách làm consumer mất khả năng đối chiếu. Có thể giữ ID cũ hoặc tạo mapping rõ:

~~~text
legacy_customer_pk → customer_id
legacy_order_pk    → order_id
~~~

ID cần ổn định, có scope/tenant rõ và tránh dùng giá trị nhạy cảm làm identifier công khai.

### 11.2. Không copy mọi cột chỉ để giữ tương thích

Một số cột legacy:

- Không còn được dùng.
- Là derived value có thể tính lại.
- Là bản sao sai semantics.
- Chứa PII không cần thiết.
- Chỉ tồn tại vì JOIN thuận tiện.
- Là state do service khác sở hữu.

Migration là cơ hội phân biệt **business data cần giữ** với **technical artifacts có thể loại bỏ**, theo owner và retention policy.

## 12. Bước 3: tạo write path thuộc owner

Trước khi chuyển consumers, cần một interface có quyền cập nhật dữ liệu mới.

Ví dụ Inventory Service:

~~~text
POST /reservations
POST /reservations/{id}/release
GET  /reservations/{id}
~~~

Hoặc command/event contract phù hợp.

Owner service thực hiện:

- Validation và domain invariants.
- Authorization.
- Transaction nội bộ.
- Concurrency control.
- Idempotency.
- Audit.
- Emitting events/outbox.
- Metrics/logs/traces.

Consumer chỉ gửi command hoặc dùng read interface. Không cấp quyền ghi trực tiếp vào DB mới cho tất cả services cũ, vì như vậy chỉ di chuyển shared DB coupling sang vị trí mới.

### 12.1. Anti-corruption layer

Trong quá trình chuyển đổi, legacy schema có thể khác domain model mới. Một adapter/anti-corruption layer ánh xạ semantics:

~~~text
Legacy order_status = "P"
          │
          ▼
Legacy Adapter
          │
          ▼
New Order State = PAYMENT_PENDING
~~~

Adapter giúp cô lập tên cột, enum, null semantics và legacy quirks khỏi domain mới. Không để mọi consumer tự diễn giải legacy values theo cách riêng.

### 12.2. Định nghĩa contract trước khi migrate consumers

Contract cần nói rõ:

- Operation và version.
- Input/output, types, units, nullability.
- Authorization và tenant scope.
- Error semantics.
- Idempotency.
- Timeout/retry behavior.
- Data freshness.
- Compatibility/deprecation.
- Owner/on-call.

## 13. Bước 4: backfill dữ liệu lịch sử

Backfill copy dữ liệu hiện có từ legacy storage sang owner storage mới.

### 13.1. Phương án cơ bản

~~~text
Legacy DB
   │ consistent snapshot / bounded export
   ▼
Transform + validate
   │
   ▼
New domain DB
   │
   ▼
Counts / checksums / business reconciliation
~~~

Cần quyết định:

- Snapshot có transaction consistency không?
- Có ghi mới trong lúc export không?
- Dữ liệu có thể thay đổi trong khi copy không?
- Xử lý delete/soft delete thế nào?
- Có cần giữ historical version?
- Có partition/batch để giảm load không?
- Có dữ liệu trùng, orphan hoặc null bất thường không?
- Có thể chạy lại idempotently không?

### 13.2. Copy theo khóa ổn định

Có thể chia theo ID ranges hoặc thời gian tạo, nhưng cần kiểm soát record thay đổi trong lúc copy. Không giả định auto-increment ID phản ánh thứ tự commit đầy đủ trong mọi hệ thống.

### 13.3. Backfill có checkpoint

Ghi:

- Range/partition đã xử lý.
- Source watermark hoặc snapshot ID.
- Số record đọc/ghi.
- Số record reject/quarantine.
- Checksum/aggregate totals.
- Thời điểm bắt đầu/kết thúc.
- Error và retry count.

Checkpoint phải đủ để tiếp tục mà không tạo duplicate side effects hoặc bỏ sót record.

### 13.4. Transformation cần version

Nếu legacy status `P` chuyển thành `PAYMENT_PENDING`, ghi rõ mapping version và rule. Nếu transformation thay đổi giữa chừng, có thể phải biết record nào được xử lý bởi logic cũ/mới.

### 13.5. Không backfill bằng cách gọi API nghiệp vụ hàng triệu lần một cách tùy tiện

Bulk migration thường cần import path được thiết kế riêng với validation, rate limits, audit và idempotency. API nghiệp vụ có thể tạo email, payment hoặc side effects không mong muốn. Nếu dùng API, phải có chế độ import được owner phê duyệt.

## 14. Bước 5: đồng bộ thay đổi phát sinh trong khi backfill

Trong lúc copy lịch sử, dữ liệu mới vẫn được tạo/sửa/xóa. Nếu chỉ chụp snapshot một lần, database mới sẽ nhanh chóng stale.

Có một số cách:

### 14.1. CDC từ database log

~~~text
Legacy DB transaction log
       │
       ▼
CDC connector
       │ ordered changes + offsets
       ▼
Migration stream
       │ transform/dedupe
       ▼
New owner DB
~~~

CDC có thể chuyển INSERT/UPDATE/DELETE từ nguồn cũ. Cần hiểu semantics của engine, transaction boundaries, primary keys, snapshot phase, log retention, offsets và schema changes.

### 14.2. Outbox/domain events

Nếu legacy application có thể thay đổi, phát event từ transaction outbox để mô tả business change. Đây thường là contract tốt hơn việc consumer phải suy luận ý nghĩa từ row-level updates.

### 14.3. Timestamp polling

Có thể poll theo updated_at hoặc sequence watermark trong hệ thống đơn giản, nhưng dễ bỏ sót khi clock, precision, late commit hoặc record bị sửa mà timestamp không cập nhật đúng. Cần overlap window, stable cursor và reconciliation.

### 14.4. Dual-read và shadow read

Một số requests được đọc từ cả nguồn cũ và mới, nhưng chỉ một nguồn được trả kết quả cho user. So sánh:

- Record existence.
- Status/enum semantics.
- Amounts/units.
- Null handling.
- Version/timestamps.
- Ordering.
- Authorization/tenant scope.

Shadow read phải không tạo side effects. Tránh gọi hai lần một API có side effects hoặc làm tăng tải vượt budget.

### 14.5. CDC không đồng nghĩa business event

CDC có thể cho biết cột nào đổi nhưng không nhất thiết nói **vì sao**. Ví dụ `status` từ A sang B có thể do cancel, timeout reconciliation hoặc admin correction. Consumer business nên dùng domain event/contract nếu cần hiểu semantics.

## 15. Bước 6: kiểm chứng dữ liệu trước cutover

Không cutover chỉ vì backfill job báo “success”. Cần nhiều lớp kiểm chứng:

| Kiểm tra | Ví dụ | Phát hiện |
| --- | --- | --- |
| Record counts | Đếm theo tenant/status/date | Thiếu hoặc dư record |
| Key coverage | ID ở nguồn có tồn tại ở đích | Bỏ sót key |
| Checksums | Hash theo partition/record | Sai payload |
| Aggregates | Tổng amount, quantity, balances | Sai transformation |
| State distribution | Đếm theo enum/status | Mapping sai |
| Referential checks | Reference IDs tồn tại theo contract | Orphan references |
| Freshness | Lag từ source commit tới target apply | Đồng bộ chậm |
| Sample validation | Đối chiếu business records đại diện | Semantics sai |
| Concurrency test | Update đồng thời/retry | Lost update/race |
| Access test | Consumer dùng role mới | Permission thiếu/thừa |

### 15.1. Đếm số record không đủ

Hai bảng đều có 1 triệu rows nhưng amount hoặc status có thể sai hoàn toàn. Cần đối chiếu business invariants và aggregates theo partitions.

### 15.2. Checksum phải có semantics

Hash toàn bộ row có thể khác vì timezone, JSON key order, numeric representation hoặc generated columns. Cần canonicalization trước khi so sánh và ghi rõ fields được kiểm tra.

### 15.3. Kiểm tra consistency trong khi nguồn còn ghi

Nếu nguồn thay đổi trong lúc chạy đối soát, count/aggregate có thể lệch tạm thời. Dùng snapshot/watermark và xác định điểm đồng bộ để so sánh công bằng.

### 15.4. Mismatch cần có ngưỡng và owner

Mỗi loại mismatch cần severity, quarantine/retry/correction path và người quyết định. Không tự sửa nguồn authoritative để ép số liệu khớp.

## 16. Bước 7: chuyển quyền ghi (write cutover)

Đây là bước nhạy cảm nhất vì quyết định **ai có quyền thay đổi authoritative state**.

Một cutover đơn giản:

~~~text
Trước:
  Order Service ───────► Legacy shared orders table
  Payment Service ────► Legacy shared orders table

Sau:
  Order Service ───────► Order DB (authoritative)
  Payment Service ─────► Payment API/event
  Order state changes ─► Order-owned write path
~~~

### 16.1. Nguyên tắc single writer

Trong một thời điểm, một operation/state cần có một writer authoritative được xác định. Nếu legacy và new service cùng nhận writes không có coordination, có thể xảy ra:

- Lost updates.
- Last-write-wins ghi đè trạng thái mới.
- Sequence/version không nhất quán.
- Events phát sai thứ tự.
- Reconciliation không thể phân biệt bản nào đúng.

### 16.2. Chọn cutover strategy

- **Big bang:** chuyển toàn bộ traffic tại một thời điểm; đơn giản về trạng thái sau cutover nhưng blast radius lớn.
- **Canary by tenant/key/region:** chuyển một phần có thể định danh; cần partitioning và tránh một entity được ghi ở cả hai nơi.
- **Operation-by-operation:** chuyển từng command/route, ví dụ create trước, update sau; cần compatibility và state ownership rõ.
- **Strangler routing:** gateway/router điều phối operation giữa legacy và owner service trong giai đoạn coexistence.
- **Read cutover trước, write cutover sau:** hữu ích khi có thể shadow/compare reads; không giải quyết mọi race write.

Lựa chọn phụ thuộc khả năng partition, consistency và rollback. Không phải lúc nào canary theo % traffic cũng an toàn: cùng một order/customer có thể được ghi qua hai đường khác nhau.

### 16.3. Write freeze ngắn hạn

Một số hệ thống có thể dừng ghi trong một khoảng nhỏ để chốt delta và chuyển writer. Phù hợp nếu downtime được chấp nhận và dữ liệu có thể buffer. Cần đo thời gian, thông báo, queue/replay và runbook.

### 16.4. Fencing và version

Nếu legacy writer vẫn có thể chạy, cần ngăn nó ghi sau khi quyền đã chuyển:

- Revoke database grants.
- Disable old code path/feature flag.
- Credential rotation.
- Write version/fencing token.
- Routing policy enforce.
- Audit kiểm tra không còn writes.

Chỉ thay config ở một service mà quên batch job dùng credential riêng sẽ không đảm bảo single writer.

## 17. Vì sao dual-write thường nguy hiểm?

Một triển khai naïve:

~~~java
legacyRepository.save(order);
newRepository.save(order);
~~~

Nếu lệnh đầu thành công, lệnh thứ hai thất bại, dữ liệu hai nơi lệch. Nếu retry, có thể duplicate. Nếu mỗi DB commit độc lập, không có atomicity xuyên hai hệ thống.

### 17.1. Khi nào có thể chấp nhận dual-write?

Chỉ khi có cơ chế rõ ràng:

- Một authoritative write và một asynchronous replication.
- Transactional outbox/CDC.
- Idempotent consumer và reconciliation.
- Version/ordering.
- Monitoring lag và DLQ.
- Kế hoạch ngừng đường phụ.
- Không có hai bên cùng quyết định state.

### 17.2. Shadow writes

Có thể ghi thử vào database mới ở môi trường/canary nhưng kết quả không được dùng làm authoritative state. Cần bảo đảm không phát side effects (payment, email, event nghiệp vụ) và có thể dọn dữ liệu thử an toàn.

### 17.3. Không dùng “last write wins” như giải pháp mặc định

Nếu hai writers cập nhật Order state khác nhau, timestamp mới hơn không nhất thiết là quyết định nghiệp vụ đúng. Phải có domain owner, version/optimistic locking hoặc state transition rules.

## 18. Bước 8: chuyển consumers khỏi SQL trực tiếp

Khi write owner đã ổn định, tiếp tục chuyển readers.

### 18.1. Chuyển consumer sang owner API

Phù hợp khi cần giá trị hiện tại hoặc business validation. API phải có pagination, filter, auth, rate limit và latency budget nếu consumers cần truy vấn nhiều records.

Không dùng một endpoint trả cả database schema cho mọi consumer; hãy thiết kế operation theo nhu cầu nghiệp vụ.

### 18.2. Chuyển sang domain events

Phù hợp khi consumer cần phản ứng với thay đổi, xây projection hoặc xử lý workflow bất đồng bộ. Phải có schema version, ordering/idempotency và lag SLO.

### 18.3. Tạo read model phục vụ nhiều consumers

Một màn hình quản trị cần JOIN nhiều domain có thể dùng BFF/query service/materialized view. Owner của read model chịu trách nhiệm transformation, freshness và rebuild. Read model không được biến thành một database shared write path mới.

### 18.4. Analytics dùng warehouse/data product

BI cần query lớn, historical joins và aggregates. Không nên bắt API owner phục vụ mọi truy vấn ad-hoc bằng OLTP database. Export/CDC sang warehouse với lineage, classification và access controls.

### 18.5. Trường hợp truy cập legacy tạm thời

Có thể giữ một compatibility view hoặc read replica trong migration, nhưng phải có:

- Owner và danh sách consumers.
- Read-only grants.
- Mục đích và expiry date.
- Dashboard access.
- Kế hoạch thay thế.
- Tiêu chí thu hồi.

“Chỉ tạm thời” không có ngày kết thúc thường trở thành coupling vĩnh viễn.

## 19. Foreign keys và referential integrity sau khi tách

Trong shared DB, bảng Order có thể dùng FK trực tiếp tới Customer. Sau khi tách:

~~~text
Order DB                   Customer DB
---------                  -----------
orders.customer_id  ─────► customers.id
~~~

Hai database độc lập không còn enforce FK vật lý xuyên DB theo cách thông thường.

### 19.1. Reference ID

Order lưu `customer_id` như reference. Tại thời điểm tạo order, Order xác thực qua Customer API hoặc nhận một trusted command/event theo contract.

### 19.2. Deletion semantics

Nếu Customer bị xóa, Order lịch sử xử lý ra sao? Có thể cần:

- Pseudonymize snapshot.
- Giữ reference tombstone.
- Giữ dữ liệu cần thiết theo nghĩa vụ hợp pháp.
- Không cho tạo giao dịch mới.
- Duy trì integrity trong order history.

Quyết định thuộc business/privacy policy; không tự cascade delete qua nhiều database.

### 19.3. Reconciliation

Định kỳ kiểm tra reference IDs, orphan references và các trạng thái cần xử lý. Việc kiểm tra không đồng nghĩa mọi service phải gọi API cho mỗi row trong mọi read path.

## 20. Transaction xuyên domain và saga

Một transaction SQL duy nhất có thể trước đây:

~~~sql
BEGIN;
UPDATE inventory SET quantity = quantity - 1 WHERE sku = 'SKU-1';
INSERT INTO orders (...);
INSERT INTO payments (...);
COMMIT;
~~~

Khi tách thành Inventory, Order và Payment databases, không còn một local transaction bao phủ tất cả. Cần thiết kế workflow.

### 20.1. Saga minh họa

~~~text
1. Order tạo trạng thái PENDING
2. Inventory reserve stock
3. Payment authorize
4. Order xác nhận
5. Fulfillment tiếp nhận
~~~

Nếu bước Payment thất bại, Order có thể yêu cầu Inventory release reservation. Nếu timeout và kết quả payment chưa rõ, cần trạng thái UNKNOWN/PENDING và reconciliation, không tự kết luận thất bại.

### 20.2. Compensation

Compensation là hành động nghiệp vụ bù trừ:

- Release reservation.
- Void authorization.
- Cancel pending order.
- Tạo refund thay vì xóa một payment đã capture.

Không phải mọi side effect đều đảo ngược được. Email đã gửi, shipment đã xuất hoặc tiền đã settle có thể cần quy trình riêng.

### 20.3. Idempotency

Mỗi command cần khóa idempotency theo phạm vi nghiệp vụ, được lưu bền vững ở owner. Khi caller timeout và retry sang instance khác, owner nhận diện request đã thực hiện.

### 20.4. Outbox/inbox

Outbox bảo đảm state change và event record cùng commit trong một DB transaction. Inbox/dedup giúp consumer không áp dụng side effect trùng. Cả hai cần unique keys, retry và observability.

## 21. Thay đổi schema trong thời kỳ coexistence

Trong migration, legacy và new service có thể chạy đồng thời. Cần tránh một service đọc field cũ trong khi owner đã chuyển semantics.

### 21.1. Expand–migrate–contract

1. **Expand:** thêm schema/API/event mới mà vẫn hỗ trợ consumer cũ.
2. **Deploy compatibility:** adapter hoặc consumer hiểu cả hai dạng.
3. **Backfill:** chuyển historical data.
4. **Dual observe:** shadow read/compare và theo dõi mismatch.
5. **Cut over:** chuyển reads/writes theo plan.
6. **Deprecate:** thông báo và theo dõi direct accesses còn lại.
7. **Contract:** xóa schema cũ/field cũ khi không còn consumers.
8. **Revoke:** thu hồi credentials/grants và xác nhận.

### 21.2. Không đổi semantics mà giữ tên field

Ví dụ `status` trước đây có nghĩa “đã nhận yêu cầu”, sau migration lại có nghĩa “đã settle”. Schema vẫn parse được nhưng business data sai. Versioning cần semantics rõ, không chỉ tên và type.

### 21.3. Consumer cũ và replay

Event cũ có thể được replay sau nhiều tháng. Consumer mới phải biết xử lý schema versions và historical semantics, hoặc có migration/reprocessing plan riêng.

## 22. Security: giảm truy cập bằng quyền tối thiểu

Tách ownership mà vẫn để mọi service dùng credential admin không tạo ranh giới bảo mật.

### 22.1. Database roles theo service

Ví dụ PostgreSQL:

~~~sql
CREATE ROLE order_app LOGIN;
GRANT CONNECT ON DATABASE order_db TO order_app;
GRANT USAGE ON SCHEMA order TO order_app;
GRANT SELECT, INSERT, UPDATE ON TABLE order.orders TO order_app;
GRANT USAGE, SELECT ON SEQUENCE order.order_id_seq TO order_app;
~~~

Đây là ví dụ minh họa; quyền thật phải tối thiểu theo operations. Không cấp DELETE nếu app không cần, không cấp schema ownership cho runtime role, và xem xét quyền trên functions/views/sequences.

### 22.2. Read-only migration window

Một consumer có thể được cấp quyền đọc legacy trong thời gian chuyển đổi, nhưng:

- Role riêng, không chia sẻ.
- Scope theo schema/table.
- Expiry/owner rõ.
- Audit access.
- Không cho write.
- Theo dõi query để xác nhận đã ngừng.
- Thu hồi sau cutover.

### 22.3. Break-glass

DBA/admin có thể cần quyền khẩn cấp. Break-glass nên có approval/audit, thời hạn, justification và hậu kiểm. Không dùng account này trong application runtime.

### 22.4. Secret management

Mỗi service có identity/secret phù hợp. Khi chuyển DB endpoint, tránh hard-code password trong repository hoặc copy credential admin sang tất cả workloads. Có kế hoạch rotate/revoke credential cũ.

## 23. Observability cho quá trình migration

Migration có thể chạy nhiều tuần. Cần dashboard riêng:

| Nhóm | Metric | Ý nghĩa |
| --- | --- | --- |
| Backfill | Records scanned/copied/rejected | Tiến độ và chất lượng |
| CDC | Source offset, replication lag, errors | Đồng bộ delta |
| Validation | Count/checksum/aggregate mismatch | Tính đúng dữ liệu |
| Shadow read | Mismatch ratio theo field/operation | Khác biệt nguồn cũ/mới |
| Write path | Writes theo owner/legacy | Ai đang thực sự ghi |
| Consumer migration | Direct DB query count | Mức giảm coupling |
| Security | Grants, principals, denied attempts | Quyền truy cập còn lại |
| Application | Latency, errors, SLO burn | Tác động user |
| Database | CPU, IOPS, locks, connections | Tải do copy/dual observation |
| Recovery | Replay/DLQ/reconciliation backlog | Khả năng xử lý sai lệch |

### 23.1. Correlation

Mỗi migration record/operation cần có migration run ID, batch ID, source key, target key, source version/watermark và status. Tránh ghi raw PII vào log.

### 23.2. Alerting

Cảnh báo khi:

- CDC lag vượt giới hạn.
- Outbox age tăng.
- Backfill bị kẹt.
- Mismatch rate tăng.
- Legacy writes xuất hiện sau write cutover.
- Consumer còn truy cập bảng đã deprecated.
- New DB saturation/connection failures.
- Application SLO xấu đi sau route cutover.
- Data deletion/retention workflow bị kẹt.

### 23.3. Đo direct access còn lại

Query audit/statistics có thể giúp phát hiện table access, nhưng phải map connection identity về service/owner. Một shared account làm việc này khó hơn, nên cần tách roles sớm.

## 24. Kịch bản migration ví dụ: Order Service tách khỏi shared database

### 24.1. Hiện trạng

~~~text
Shared DB
  ├── customers
  ├── orders
  ├── order_lines
  ├── payments
  └── inventory

Order Service:
  - ghi orders/order_lines
  - đọc customers
  - đọc payments
  - cập nhật inventory.reserved
Reporting:
  - JOIN cả 5 bảng
Payment Service:
  - ghi payments
  - cập nhật orders.payment_status
~~~

Vấn đề: Payment đang ghi Order state; Order ghi Inventory; Reporting phụ thuộc DDL của tất cả domain.

### 24.2. Ownership đích

~~~text
Customer DB: customers
Order DB: orders, order_lines, order snapshots
Payment DB: payment transactions/refunds
Inventory DB: stock/reservations

Order Service owns order lifecycle
Payment Service owns payment lifecycle
Inventory Service owns stock/reservation lifecycle
Customer Service owns current customer profile
Analytics owns reporting projections
~~~

### 24.3. Luồng mới

~~~text
Checkout
   │
   ▼
Order Service ──► Inventory.reserve()
   │
   ├────────────► Payment.authorize()
   │
   ▼
Order DB + Outbox
   │
   ▼
Order events ──► Fulfillment / Notification / Analytics
~~~

Order không trực tiếp cập nhật inventory/payment tables. Payment phát kết quả theo contract; Order xử lý state transition của chính nó.

### 24.4. Migration phases

1. Inventory readers/writers và stored procedures.
2. Tạo Order DB/schema, roles và migrations.
3. Tạo Order-owned API/events.
4. Backfill orders/order_lines và snapshots.
5. CDC hoặc outbox sync cho thay đổi mới.
6. Shadow reads và reconciliation.
7. Chuyển Order writes sang Order DB.
8. Chuyển Payment khỏi direct UPDATE orders.payment_status sang API/event.
9. Chuyển Reporting sang curated warehouse datasets.
10. Revoke old grants và retire legacy tables sau thời gian quan sát.

### 24.5. Điều kiện hoàn tất

- Một authoritative writer cho Order state.
- Không còn consumer truy cập trực tiếp bảng Order.
- Các API/event contracts có owner/version.
- Reconciliation mismatch trong ngưỡng đã duyệt.
- Backup/restore và RTO/RPO được kiểm chứng.
- User SLO không suy giảm ngoài budget.
- Rollback window đóng theo quyết định có bằng chứng.
- Legacy schema/roles được thu hồi an toàn.

## 25. Các chiến lược cutover chi tiết

### 25.1. Cutover theo tenant

Chuyển một tenant sang owner DB mới trong khi tenant khác còn ở legacy. Cần routing nhất quán theo tenant, tenant migration state và bảo đảm một tenant không có writers ở cả hai nơi.

Phù hợp khi dữ liệu partition theo tenant và có thể cô lập traffic. Cần xem cross-tenant reports, shared entities và quota.

### 25.2. Cutover theo ID range

Chuyển một số customer/order ID ranges. Cần xác định mọi operation đều route theo cùng mapping; các references giữa ranges phải xử lý được. Không dựa vào ID range nếu business operations thường xuyên liên kết entity ở nhiều ranges.

### 25.3. Cutover theo operation

Ví dụ GET đọc mới trước, POST vẫn legacy; sau đó chuyển POST. Chỉ an toàn khi read/write semantics và replication đảm bảo không có stale read làm quyết định sai.

### 25.4. Cutover theo domain

Chuyển toàn bộ Inventory domain và mọi consumers liên quan. Đây là ranh giới rõ hơn nhưng có thể cần coordination lớn.

### 25.5. Chọn phương án

Đánh giá:

- Có thể partition nhất quán không?
- Có nhiều transactions cross-domain không?
- Có thể rollback route mà không tạo hai writers không?
- Mức downtime được phép?
- Data volume và CDC lag?
- Consumers nào không thể nâng cấp kịp?
- Có side effects không idempotent?
- Khả năng quan sát và điều phối?

## 26. Rollback: phải thiết kế trước cutover

Một lỗi phổ biến là “nếu có gì sai thì chuyển connection string về DB cũ”. Sau khi DB mới đã nhận writes, DB cũ có thể stale; rollback mù có thể mất dữ liệu.

### 26.1. Rollback trước write cutover

Nếu chưa chuyển quyền ghi, thường có thể dừng migration, giữ legacy authoritative và xử lý dữ liệu mới theo plan.

### 26.2. Rollback sau write cutover

Cần một trong các phương án đã được thiết kế:

- New DB có thể replay/replicate changes về legacy theo cơ chế kiểm soát.
- Có write freeze và delta reconciliation trước khi quay lại.
- Có reverse CDC với semantics rõ và một writer duy nhất.
- Có forward fix thay vì rollback data plane.
- Có compensation/reconciliation nếu đã tạo side effects.

**Không giả định reverse replication đơn giản đối xứng với forward migration.** Schema và semantics có thể khác nhau.

### 26.3. Rollback decision gate

Xác định trước:

- SLO/error thresholds.
- Mismatch threshold.
- Data loss tolerance/RPO.
- Người có quyền quyết định.
- Thời gian còn trong rollback window.
- Các writes đã xảy ra và hướng đồng bộ.
- Side effects đã gửi ra bên ngoài.
- Điều kiện dừng/tiếp tục migration.

### 26.4. Data recovery

Nếu có divergence, giữ snapshot/logs, xác định authoritative source theo từng record/operation và reconciliation. Không ghi đè toàn bộ một phía theo “database mới chắc đúng hơn”.

## 27. Những bẫy của CDC và replication

CDC là công cụ mạnh nhưng cần quản lý:

- Log retention không đủ khiến connector mất offset.
- Snapshot ban đầu và streaming phase có race.
- Schema changes làm connector fail.
- Transaction ordering và partitioning.
- Delete/tombstone semantics.
- Large transactions hoặc DDL.
- Duplicate delivery và consumer replay.
- PII bị copy sang hệ thống mới ngoài scope.
- CDC account có quyền quá rộng.
- Backpressure từ downstream.
- Recovery sau connector outage.

### 27.1. Exactly-once không nên được giả định

Nhiều pipeline cung cấp at-least-once hoặc semantics cụ thể theo engine. Consumer cần dedup/idempotency và offset management. Hãy ghi guarantees thật của connector và broker trong migration design.

### 27.2. CDC row-level không thay business event

Nếu consumer cần biết “Payment đã được capture”, không nên phụ thuộc vào việc đọc cột `payments.status` từ CDC mà không có contract semantics. Domain event có thể phù hợp hơn.

### 27.3. Không mở rộng CDC mãi mãi để giữ shared DB

CDC hữu ích cho migration và analytics, nhưng nếu mọi service đều subscribe trực tiếp table changes của nhau, coupling chỉ đổi từ SQL sang row-level event schema. Cần domain contracts và owners.

## 28. Giảm truy cập đọc xuyên service mà không làm UI chậm

Một câu hỏi thường gặp: nếu không JOIN trực tiếp, làm sao tạo màn hình hiển thị Order, Customer, Payment?

### 28.1. API composition

BFF/query service gọi các API owner và ghép kết quả. Phù hợp khi fan-out ít, latency budget đủ và dữ liệu cần khá mới.

Rủi ro: request phụ thuộc nhiều service, partial failures và N+1 queries. Cần parallelism, deadlines, caching và graceful degradation.

### 28.2. Materialized read model

Consumer nhận events và cập nhật projection:

~~~text
CustomerUpdated ──┐
OrderUpdated ─────┼──► CustomerOrderView
PaymentUpdated ───┘
~~~

Query UI đọc một model được tối ưu cho màn hình. Owner của projection chịu trách nhiệm lag/freshness, rebuild và correctness. Không được dùng nó để cập nhật authoritative Order/Payment state.

### 28.3. CQRS

Command path đi tới domain owner; query path có thể dùng read model. CQRS giúp tối ưu read workloads nhưng thêm eventual consistency và projection lifecycle. Chỉ dùng khi read/write needs khác biệt có ý nghĩa, không phải để tăng số components.

### 28.4. Cache

Cache giảm latency nhưng không là nguồn authoritative. Cần TTL, invalidation, version, tenant isolation và fallback. Khi cache miss, không tạo stampede làm DB owner quá tải.

## 29. Giảm truy cập database dùng chung qua security boundaries

Sau khi consumer chuyển sang contract, cần thu hồi quyền cũ. Nếu không, SQL path vẫn tồn tại và có thể được dùng lại.

### 29.1. Database principal riêng

Mỗi service dùng credential/role riêng. Tránh một `app_user` có quyền trên toàn bộ schema. Tách runtime role khỏi migration/admin role.

### 29.2. Audit quyền

- List roles/grants.
- Map credentials tới workloads.
- Kiểm tra active sessions/query history.
- Phân loại quyền cần giữ.
- Revoke grants đã hết mục đích.
- Theo dõi denied attempts sau cutover.

### 29.3. Revoke theo từng consumer

Không revoke tất cả cùng lúc nếu còn legacy paths hợp lệ. Dùng rollout theo owner/consumer, quan sát lỗi và có kế hoạch khôi phục quyền có thời hạn nếu phát hiện dependency ẩn.

### 29.4. Credential rotation

Khi bỏ shared credential, rotate secret và cập nhật workload. Xóa secret cũ khỏi runtime, CI, vault references và scripts sau khi xác nhận không còn dùng.

## 30. Stored procedures, triggers và views

Database logic thường ẩn dependency.

### 30.1. Stored procedures

Một procedure có thể đọc bảng nhiều domain, cập nhật trạng thái và gửi dữ liệu ra hệ khác. Cần:

- Kiểm kê dependencies.
- Xác định business owner.
- Xác định caller/service.
- Kiểm tra transaction boundary.
- Chuyển logic vào owner service nếu cần.
- Giữ procedure adapter tạm thời nếu migration yêu cầu.

### 30.2. Triggers

Trigger tự cập nhật bảng khác khi một row thay đổi có thể phá vỡ single-writer model dù app code không gọi trực tiếp. Phải kiểm tra trigger definitions và side effects trước cutover.

### 30.3. Views/materialized views

Views cross-schema có thể vẫn là direct schema coupling. Có thể thay bằng read model/data product hoặc giữ view có contract và owner trong giai đoạn chuyển đổi.

### 30.4. Không chuyển stored procedure sang service bằng cách copy từng dòng SQL

Cần xác định semantics, transaction, locking, isolation và error behavior. Một procedure có thể đang thực hiện business invariant cần được mô hình hóa ở domain layer.

## 31. Batch jobs, BI và consumers ngoài runtime

Một service map từ HTTP tracing không nhìn thấy tất cả readers.

Ví dụ:

~~~text
Legacy DB
  ├── Order API
  ├── Nightly Billing Job
  ├── Finance BI Dashboard
  ├── CSV export for partner
  ├── Data Science notebook
  └── Support repair script
~~~

Migration có thể khiến Order API chạy tốt nhưng Finance report lỗi vào ngày chốt sổ.

### 31.1. Job inventory

Ghi owner, schedule, query, dataset, purpose, output, failure alert và retention. Với job theo tháng/quý, phải có ít nhất một chu kỳ xác nhận hoặc bằng chứng source/config.

### 31.2. BI consumers

Đưa dữ liệu sang warehouse/curated datasets với semantic definitions. Không cấp quyền trực tiếp vào OLTP owner database cho hàng chục analyst.

### 31.3. External partners

API/file exports có thể là contract công khai hoặc thỏa thuận. Cần versioning, deprecation notice, security, data minimization và kiểm tra downstream trước khi đổi schema.

## 32. Quản lý dữ liệu nhạy cảm trong migration

Khi copy dữ liệu, phạm vi PII có thể tăng nếu schema mới gom thêm field không cần thiết.

Cần:

- Data classification theo dataset/field.
- Purpose và legal basis nếu áp dụng.
- Least privilege cho migration account.
- Encryption in transit/at rest.
- Secure temporary files/staging.
- Masking/pseudonymization cho non-production.
- Audit export và data movement.
- Retention cho temporary snapshots.
- Deletion/backup policy.
- Không ghi raw secrets/PII vào logs.

### 32.1. Copy không đồng nghĩa được phép dùng

Consumer có thể có quyền đọc Customer ID cho order linkage nhưng không có quyền nhận email/phone. Migration không nên mở rộng data access ngoài purpose đã được owner/security duyệt.

### 32.2. Data residency

Nếu domain mới đặt ở region khác, cần xác minh dữ liệu có được phép di chuyển, backup và replicate ở đó hay không. Physical migration có thể thay đổi ranh giới pháp lý.

## 33. Capacity, performance và cost

Tách database có thể giảm contention nhưng cũng tạo overhead:

- Nhiều connection pools.
- Nhiều backup/snapshot.
- Nhiều replication pipelines.
- Nhiều DB instances hoặc schema resources.
- Event broker throughput và storage.
- Read model/warehouse compute.
- Cross-zone/network traffic.
- Observability storage/cardinality.

### 33.1. Đo trước và sau

| Metric | Shared DB baseline | Target sau migration |
| --- | --- | --- |
| Query latency theo domain | Đo p50/p95/p99 | So sánh tương ứng |
| Lock contention | Theo table/transaction | Theo owner store |
| Connection usage | Theo principal/service | Theo DB/role |
| Schema deployment coupling | Số consumer cần phối hợp | Số contract migrations |
| Data lag | Hiện trạng nếu có replica | Event/CDC freshness |
| Incident blast radius | Số domain ảnh hưởng | Phân vùng mới |
| Cost | Cluster/storage/ops | Tổng DB + broker + projections |
| Operational toil | Manual jobs/grants | Migration/reconciliation toil |

### 33.2. Không scale vật lý quá sớm

Một shared cluster với database/schema/role riêng có thể đáp ứng isolation ban đầu. Tách ownership logic và giảm direct access trước, sau đó tách cluster khi có lý do scale, security hoặc failure-domain rõ.

### 33.3. Connection storm

Nếu mỗi microservice mở pool 50 connections và có 30 replicas, potential connections có thể lên 1.500. Cần pool budget theo tổng replica, proxy/pooling và capacity DB. Tách database không tự động giải quyết giới hạn connections.

## 34. Runbook: phát hiện consumer còn truy cập DB cũ

**Bước 1 — Xác định principal:** query/audit log cho biết user/role nào đang truy cập.

**Bước 2 — Map tới workload:** secret reference, deployment, CI job hoặc batch owner.

**Bước 3 — Xác định loại access:** read, write, stored procedure, view, trigger hoặc migration tool.

**Bước 4 — Xác nhận purpose:** business use, analytics, support, batch hay access không còn owner.

**Bước 5 — Tìm replacement:** API, event, projection, warehouse hoặc owner-operated correction tool.

**Bước 6 — Chuyển và quan sát:** shadow compare, contract tests, SLO và data correctness.

**Bước 7 — Thu hồi grant:** theo consumer cụ thể sau khi owner xác nhận.

**Bước 8 — Theo dõi denied attempts:** phân biệt dependency bị bỏ sót với credential misuse.

**Bước 9 — Cập nhật inventory:** consumer, owner, contract và expiry.

Không revoke một role dùng chung nếu chưa biết mọi workload phụ thuộc; trước tiên phải tách principal để thu hồi chính xác.

## 35. Runbook: dữ liệu nguồn mới và legacy bị lệch

1. Dừng/giới hạn cutover theo decision gate nếu mismatch ảnh hưởng correctness.
2. Xác định operation, record key, tenant và source watermark.
3. Xác định authoritative writer tại thời điểm record thay đổi.
4. Thu transaction/audit logs, CDC offsets, outbox IDs và version.
5. Phân loại mismatch: thiếu record, duplicate, stale, transform sai, concurrent update hoặc deletion.
6. Không overwrite mù; owner quyết định record đúng theo business semantics.
7. Reconcile bằng correction command, replay hoặc backfill đã kiểm thử.
8. Xác nhận downstream projections và business invariants.
9. Khôi phục traffic khi SLI và mismatch về ngưỡng chấp nhận.
10. Ghi root cause, phạm vi, action owners và cập nhật migration safeguards.

## 36. Runbook: cutover gây lỗi ứng dụng

**Triệu chứng:** error rate tăng sau khi chuyển Order sang DB mới.

1. Kiểm tra user-facing SLI và phạm vi theo region/tenant/version.
2. Kiểm tra DB connection/auth/permissions.
3. Kiểm tra schema migration và data mapping.
4. Xem latency, locks, indexes, pool saturation.
5. Kiểm tra API/event contract và serialization.
6. Xác nhận read-after-write và consistency behavior.
7. Kiểm tra routing có tạo mixed writers không.
8. Quyết định rollback hoặc forward fix theo data state.
9. Nếu rollback, đồng bộ/reconcile writes đã xảy ra.
10. Xác nhận duplicate/missing side effects, queue backlog và audit.

Không chuyển connection string về DB cũ trước khi biết dữ liệu mới đã nhận những writes nào.

## 37. Migration theo strangler pattern

Strangler pattern cho phép thay thế dần chức năng legacy:

~~~text
                    Router / Gateway
                     │           │
            legacy operations   migrated operations
                     │           │
                     ▼           ▼
                Legacy App   New Owner Service
                     │           │
                Legacy DB    New Domain DB
                     │           │
                     └─ controlled replication
~~~

### 37.1. Các giai đoạn

1. Đưa routing boundary vào trước legacy code.
2. Chọn một operation có phạm vi rõ.
3. Tạo owner service và target schema.
4. Backfill/sync data.
5. Shadow reads và kiểm chứng.
6. Chuyển operation sang service mới.
7. Giữ adapter cho clients cũ trong thời gian deprecation.
8. Chuyển consumers và retire legacy code/table.

### 37.2. Một operation tại một thời điểm

Ví dụ tách `GET /orders/{id}` trước để đọc từ Order DB, trong khi writes vẫn legacy. Điều này chỉ an toàn khi data sync và freshness được kiểm soát. Sau đó chuyển create/update với single-writer cutover.

### 37.3. Không để router trở thành business logic mới

Gateway/router nên định tuyến theo operation/tenant/version; domain validation và data ownership vẫn ở owner service. Nếu router bắt đầu tự sửa Order/Payment data, ownership lại bị phân tán.

## 38. Kiểm thử migration

### 38.1. Unit/domain tests

- Invariants của owner.
- State transitions.
- Mapping legacy-to-new.
- Idempotency/version handling.
- Authorization decisions.

### 38.2. Migration tests

- Snapshot consistency.
- Backfill resume/checkpoint.
- CDC offsets/replay.
- Deletes/tombstones.
- Schema evolution.
- Count/checksum/aggregate reconciliation.
- Large dataset and throttling.

### 38.3. Integration tests

- New service DB grants.
- API/event contracts.
- Outbox/inbox.
- Read model updates.
- Cross-service workflow and compensation.
- Legacy adapter.

### 38.4. Cutover rehearsal

Trong môi trường đại diện:

1. Chạy backfill.
2. Chạy incremental sync.
3. Giả lập traffic và writes liên tục.
4. Shadow compare.
5. Thực hiện cutover.
6. Kiểm tra user SLI và data invariants.
7. Thực hiện rollback rehearsal.
8. Đo thời gian và ghi sai lệch.

### 38.5. Production verification

- Canary/limited tenant.
- Error rate và p95/p99.
- CDC/outbox lag.
- Mismatch rate.
- Legacy writes.
- Permission denied.
- DB saturation.
- Reconciliation và business outcome.

Không coi việc test migration trên vài chục records là bằng chứng đủ cho hàng tỷ records hoặc các transaction concurrency cao.

## 39. Ví dụ SQL kiểm kê quyền và schema

Các truy vấn dưới đây là gợi ý cho PostgreSQL; catalog/permissions khác ở MySQL, SQL Server, Oracle và managed databases.

### 39.1. Liệt kê bảng nghiệp vụ

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
  AND table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name;
~~~

### 39.2. Liệt kê cột

~~~sql
SELECT table_schema, table_name, column_name,
       data_type, is_nullable
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;
~~~

### 39.3. Liệt kê table privileges

~~~sql
SELECT grantee, table_schema, table_name,
       privilege_type
FROM information_schema.role_table_grants
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, grantee, privilege_type;
~~~

### 39.4. Foreign key relationships

~~~sql
SELECT
    tc.table_schema,
    tc.table_name,
    kcu.column_name,
    ccu.table_schema AS foreign_table_schema,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
  ON ccu.constraint_name = tc.constraint_name
 AND ccu.constraint_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY';
~~~

Những truy vấn này hỗ trợ kiểm kê cấu trúc và quyền, nhưng **không xác định business owner hoặc consumer**. Cần đối chiếu source code, credentials, query logs, jobs và xác nhận của các domain owners.

## 40. Ví dụ Java: owner API thay cho direct repository access

### 40.1. Trước khi tách

~~~java
public final class OrderService {
    private final JdbcTemplate jdbc;

    public Customer loadCustomer(String customerId) {
        return jdbc.queryForObject(
            "select id, email, status from customers where id = ?",
            customerRowMapper,
            customerId
        );
    }
}
~~~

Order Service phụ thuộc trực tiếp bảng và semantics Customer.

### 40.2. Sau khi tách

~~~java
public interface CustomerEligibilityPort {
    CustomerEligibility getEligibility(String customerId);
}

public final class OrderService {
    private final CustomerEligibilityPort customers;

    public OrderService(CustomerEligibilityPort customers) {
        this.customers = customers;
    }

    public void validateCheckout(String customerId) {
        CustomerEligibility eligibility =
            customers.getEligibility(customerId);

        if (!eligibility.canPlaceOrder()) {
            throw new CheckoutNotAllowedException();
        }
    }
}
~~~

Adapter triển khai port bằng HTTP/gRPC client hoặc local projection phù hợp. Service không còn biết Customer DB schema.

### 40.3. Hợp đồng phải ổn định

`CustomerEligibility` nên chứa business capability mà Order cần, không trả toàn bộ Customer entity với mọi field. Cần timeout, authorization, versioning và tests cho adapter.

## 41. Ví dụ Java: consumer xử lý event idempotently

~~~java
public final class PaymentAuthorizedHandler {
    private final ProcessedEventRepository processed;
    private final OrderRepository orders;

    public void handle(PaymentAuthorized event) {
        if (processed.exists(event.eventId())) {
            return;
        }

        orders.markPaymentAuthorized(
            event.orderId(),
            event.paymentId(),
            event.aggregateVersion()
        );

        processed.record(event.eventId());
    }
}
~~~

Đoạn code là minh họa. Trong implementation thật, kiểm tra dedup, update Order và ghi processed-event phải nằm trong **một transaction local** hoặc một protocol có semantics tương đương. Nếu record processed trước khi update Order rồi crash, event có thể bị bỏ qua; nếu update xong trước khi record processed, duplicate có thể apply lại.

Cần unique constraint, optimistic version và retry policy để xử lý race giữa nhiều consumers.

## 42. Data ownership và analytics

Không phải mọi query cross-domain đều cần trở thành synchronous API.

~~~text
Customer SoR ──events/CDC──┐
Order SoR ─────events/CDC──┼──► Analytics Warehouse
Payment SoR ───events/CDC──┤
Inventory SoR ─events/CDC──┘
~~~

Analytics/Finance có thể sở hữu curated data products:

- Revenue by day/currency.
- Refund reconciliation.
- Inventory turnover.
- Customer cohort.
- Fulfillment SLA.

Domain services vẫn sở hữu operational truth. Data team chịu trách nhiệm transformation, lineage, freshness, quality và access của curated assets.

Không dùng warehouse như nguồn ghi lại Order hoặc Payment state cho operational request.

## 43. Retention, deletion và backup khi tách

Tách DB làm tăng số nơi phải quản lý:

- Backup/snapshot.
- WAL/binlog/archive.
- CDC topic.
- Outbox/inbox.
- Event retention.
- Read model/search index.
- Cache.
- Warehouse/export.
- Logs/traces.
- Temporary migration files.

Bản đồ dữ liệu phải ghi nơi nào chứa PII, ai có quyền truy cập, retention, deletion procedure và backup expiry. Khi có yêu cầu xóa, cần propagation workflow có audit và xử lý ngoại lệ pháp lý.

### 43.1. Restore sau cutover

Nếu Order DB restore về snapshot cũ, event consumers có thể đã tiến xa hơn. Cần xác định checkpoint, replay strategy, dedup và reconciliation để không làm lùi state hoặc phát side effect trùng.

### 43.2. RPO/RTO theo domain

Order, Payment và Inventory có thể có yêu cầu khác nhau. Tách ownership không tự bảo đảm từng DB đạt RPO/RTO. Cần kiểm thử restore và failover riêng cho từng data asset.

## 44. Bài tập tình huống

### Bài A — Nhiều writers

Order Service và Payment Service cùng UPDATE `orders.payment_status`.

**Hỏi:** chuyển bảng sang Order DB có đủ không?

**Gợi ý:** chưa. Phải xác định Payment sở hữu payment state, Order sở hữu order lifecycle. Payment phát kết quả theo contract; Order tự thực hiện transition của mình. Single authoritative writer cho Order state.

### Bài B — Backfill trong khi có writes

Copy 10 triệu rows sang DB mới mất 3 giờ; nguồn vẫn nhận update.

**Hỏi:** làm sao không bỏ lỡ thay đổi trong 3 giờ?

**Gợi ý:** snapshot/watermark nhất quán cộng CDC/outbox incremental, replay từ checkpoint và reconciliation trước cutover.

### Bài C — Dual-write divergence

Ứng dụng ghi legacy DB thành công nhưng new DB timeout.

**Hỏi:** có nên retry cả hai lệnh vô hạn?

**Gợi ý:** không. Cần một authoritative write path, outbox/CDC hoặc protocol idempotent; retry có giới hạn, theo dõi lag và reconcile.

### Bài D — Consumer cũ còn đọc bảng

Order đã chuyển DB nhưng Finance chạy query vào ngày cuối tháng và báo lỗi.

**Hỏi:** thiếu bước nào?

**Gợi ý:** inventory cả batch/BI consumers, chuyển sang curated data product và xác nhận qua ít nhất một chu kỳ phù hợp trước khi revoke/retire.

### Bài E — Foreign key bị mất

Order DB giữ customer_id nhưng Customer bị xóa.

**Hỏi:** có nên cascade delete Order?

**Gợi ý:** không tự động. Xác định snapshot, retention/legal policy và semantics lịch sử. Dùng owner APIs/tombstones/reconciliation nếu cần.

### Bài F — Shadow read mismatch

New DB trả amount 10000 minor units, legacy trả 100.00 decimal; hệ thống đánh dấu mismatch.

**Hỏi:** so sánh thế nào?

**Gợi ý:** canonicalize unit/currency/precision trước khi so sánh; semantics quan trọng hơn bytes thô.

### Bài G — CDC không thấy business meaning

CDC cho biết payment.status đổi từ PENDING sang SUCCESS.

**Hỏi:** consumer có thể tự phát PaymentCaptured event không?

**Gợi ý:** chỉ khi domain owner xác nhận mapping/transaction semantics. Row update có thể là trạng thái kỹ thuật hoặc được sửa bởi reconciliation; domain event phải phản ánh business fact.

### Bài H — Rollback sau cutover

New DB đã nhận 50.000 writes, legacy DB stale.

**Hỏi:** chỉ đổi connection string về legacy có an toàn không?

**Gợi ý:** không. Phải có reverse sync/replay hoặc forward fix và reconciliation; giữ single writer, xác định side effects.

### Bài I — Shared physical cluster

Customer và Order dùng hai database riêng trên cùng PostgreSQL cluster, roles tách biệt, không direct reads.

**Hỏi:** có vi phạm database-per-service không?

**Gợi ý:** không nhất thiết. Logical ownership và access boundary đã tách; physical cluster có thể dùng chung nếu capacity, security và failure isolation chấp nhận được.

### Bài J — API fan-out thay JOIN

Một UI cần Customer, Order và Payment; BFF gọi 3 APIs, p99 tăng gấp đôi.

**Hỏi:** có nên quay lại direct SQL cross-service?

**Gợi ý:** chưa. Xem API composition, parallel calls, deadline, cache hoặc materialized read model có owner. Tối ưu latency mà giữ data ownership.

## 45. Checklist trước khi chuyển đổi

### Discovery và ownership

- [ ] Xác định bounded context và authoritative owner cho từng data asset/operation.
- [ ] Liệt kê readers, writers, batch jobs, BI, views, procedures, triggers và exports.
- [ ] Map credentials/database roles tới service/workload cụ thể.
- [ ] Phân biệt current state, snapshot, projection và cache.
- [ ] Xác định data classification, retention, deletion và residency.
- [ ] Có baseline query, lock, latency, connection và incident.

### Target design

- [ ] Owner kiểm soát write path và domain invariants.
- [ ] Schema/keys/constraints và migration strategy được định nghĩa.
- [ ] API/event/data contract có version, owner và semantics.
- [ ] Consumer có read strategy phù hợp: API, event, projection hoặc warehouse.
- [ ] Cross-domain workflow có saga/compensation/idempotency khi cần.
- [ ] Backup/restore, RTO/RPO và access policy đã thiết kế.
- [ ] Physical isolation phù hợp rủi ro và cost.

### Data movement

- [ ] Backfill có snapshot/watermark và checkpoint.
- [ ] Incremental changes được capture qua CDC/outbox hoặc cơ chế tin cậy.
- [ ] Transformation versioned, delete/tombstone semantics rõ.
- [ ] Consumer xử lý duplicate/out-of-order.
- [ ] Count/checksum/aggregate/reference reconciliation.
- [ ] Shadow reads không tạo side effects và không quá tải.
- [ ] Có quarantine/correction cho mismatch.

### Cutover và rollback

- [ ] Có single-writer plan cho từng operation/entity.
- [ ] Route/tenant/partition mapping nhất quán.
- [ ] Mọi writers cũ (kể cả jobs/scripts) đã được kiểm soát.
- [ ] Cutover thresholds, owner và decision gates rõ.
- [ ] Rollback không trỏ về nguồn stale.
- [ ] Reverse sync/replay/forward fix strategy đã diễn tập.
- [ ] SLO, lag và mismatch dashboards hoạt động.

### Hoàn tất và retire

- [ ] Consumers đã chuyển sang contracts mới.
- [ ] Direct SQL access đã được xác minh ngừng.
- [ ] Credentials/grants cũ được thu hồi theo từng consumer.
- [ ] Không còn hidden batch/BI/partner dependencies.
- [ ] Legacy schema được archive/retire theo retention policy.
- [ ] Service catalog, data map, runbooks và owners cập nhật.
- [ ] Security/access audit hoàn tất.
- [ ] Reconciliation và production SLO đạt tiêu chí đóng migration.

## 46. Tổng kết

Tách quyền sở hữu dữ liệu không đơn giản là đưa bảng từ database A sang database B. Nó là việc **xác định lại ai có quyền quyết định trạng thái nghiệp vụ, ai được phép ghi, consumer nhận dữ liệu bằng contract nào và hệ thống bảo đảm tính đúng đắn trong suốt quá trình chuyển đổi ra sao**.

Một lộ trình thực dụng:

1. **Kiểm kê truy cập:** tìm mọi reader/writer, kể cả job, BI, procedure và công cụ thủ công.
2. **Chốt ownership:** chọn authoritative owner theo semantics và operation; phân biệt snapshot/projection.
3. **Xây write path mới:** schema, API/events, security và observability do owner kiểm soát.
4. **Di chuyển có đồng bộ:** backfill, CDC/outbox, shadow reads và reconciliation.
5. **Chuyển quyền ghi:** bảo đảm single writer, versioning, fencing và rollback có dữ liệu.
6. **Chuyển consumers:** API, events, read models hoặc data products phù hợp nhu cầu.
7. **Thu hồi coupling cũ:** revoke direct DB grants, loại bỏ jobs/schema phụ thuộc và cập nhật bản đồ.

Kết quả mong muốn là mỗi service có thể thay đổi và vận hành dữ liệu thuộc domain của mình với trách nhiệm rõ ràng; các consumer vẫn có dữ liệu cần thiết qua interface được quản lý. **Giảm truy cập database dùng chung thành công khi quyền ghi, schema và vòng đời dữ liệu thực sự có owner, các phụ thuộc cũ được loại bỏ bằng bằng chứng, và hệ thống vẫn bảo toàn correctness, SLO và khả năng phục hồi trong suốt migration.**
