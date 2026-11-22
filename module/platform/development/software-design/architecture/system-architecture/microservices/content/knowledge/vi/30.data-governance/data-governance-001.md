# Lập bản đồ dữ liệu và dịch vụ chịu trách nhiệm trong Microservices

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Quản trị dữ liệu.
>
> **Mục tiêu chính:** Xác định **dữ liệu nào tồn tại ở đâu, dịch vụ nào có quyền quyết định giá trị chuẩn của nó, hệ thống nào đang giữ bản sao, dữ liệu di chuyển qua các API/event/job nào và ai chịu trách nhiệm khi dữ liệu sai, thay đổi, bị rò rỉ hoặc cần xóa**. Bản đồ dữ liệu (data map/data ownership map) không chỉ là sơ đồ database; nó là công cụ quản trị kiến trúc, vận hành, bảo mật và vòng đời dữ liệu.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích các khái niệm **data owner, data steward, system of record, authoritative source, bounded context, data product, read model, data lineage** và data contract trong microservices.
2. Phân biệt **quyền sở hữu dữ liệu nghiệp vụ** với quyền quản trị cơ sở dữ liệu, quyền truy cập vật lý và trách nhiệm của đội vận hành hạ tầng.
3. Lập danh mục thực thể, thuộc tính quan trọng, nguồn dữ liệu chuẩn, nơi lưu bản sao, hệ thống tiêu thụ, cơ chế cập nhật và chính sách vòng đời.
4. Vẽ các luồng dữ liệu đồng bộ và bất đồng bộ qua REST/gRPC, event broker, CDC, ETL/ELT và dữ liệu phân tích.
5. Quyết định service nào **được phép thay đổi giá trị gốc** và service nào chỉ được lưu projection/cache hay gửi lệnh yêu cầu thay đổi.
6. Mô hình hóa ownership cho dữ liệu dùng chung như Customer, Order, Inventory, Payment, Address và Product mà không tạo database dùng chung khó kiểm soát.
7. Thiết lập metadata về phân loại nhạy cảm, consent, IAM, retention, deletion, encryption và quyền truy cập từng tập dữ liệu.
8. Thiết kế versioning và contract test để thay schema an toàn, không phá vỡ producer/consumer.
9. Xây dựng quy trình phát hiện dữ liệu không nhất quán, đối soát, khôi phục và truy vết nguyên nhân bằng correlation ID và audit log.
10. Tạo tài liệu, checklist và thực hành tổ chức để bản đồ dữ liệu **luôn phản ánh triển khai thực**, không trở thành sơ đồ lỗi thời.

Ví dụ trong bài dùng bối cảnh nền tảng bán hàng gồm Customer, Catalog, Inventory, Order, Payment, Fulfillment và Analytics. Tên bảng, schema và API là minh họa; áp dụng thực tế phải dựa trên mô hình nghiệp vụ, hợp đồng pháp lý và công nghệ của dự án.

## 2. Vì sao microservices cần bản đồ dữ liệu?

Trong kiến trúc monolith, nhiều module có thể đọc bảng Customer hoặc Order trong cùng database. Khi tách thành microservices, những giả định về “bảng nào cũng có thể JOIN” trở nên nguy hiểm:

- Nhiều service cùng viết một trường, gây **hai nguồn sự thật**.
- Service A đọc trực tiếp bảng của service B, khiến migration của B phá vỡ A.
- Customer đổi email nhưng Notification còn lưu email cũ.
- Payment đã ghi nhận giao dịch thành công nhưng Order chưa chuyển trạng thái do event bị chậm.
- Một yêu cầu xóa dữ liệu cá nhân hoàn tất tại Customer nhưng bản sao vẫn còn trong Analytics.
- Báo cáo doanh thu cộng dữ liệu từ nguồn không rõ trạng thái refund/cancel.
- Một incident không có đội đứng ra nhận trách nhiệm vì “dữ liệu này cũng ở service khác”.

Một bản đồ dữ liệu tốt trả lời được:

| Câu hỏi | Cần biết |
| --- | --- |
| Dữ liệu gốc được tạo ở đâu? | Service/domain quyết định giá trị chuẩn |
| Ai có quyền thay đổi? | Owner nghiệp vụ và write interface |
| Ai đang sử dụng? | Danh sách consumers, operation, mục đích |
| Giá trị đang lưu ở đâu? | DB, cache, search index, warehouse, backup, file |
| Bản sao được làm mới bằng gì? | API pull, event, CDC, ETL, batch |
| Dữ liệu có thể trễ bao lâu? | Freshness SLO, lag và eventual consistency |
| Nếu producer thay schema? | Contract versions, compatibility và consumer impact |
| Khi bị sai hoặc cần xóa? | Runbook correction, retention, deletion propagation |
| Ai xử lý incident? | Owner, steward, on-call, escalation |
| Ai được xem/ghi? | IAM, classification, audit, consent |

**Mục tiêu không phải vẽ thật nhiều mũi tên**, mà là làm rõ **trách nhiệm và ranh giới tin cậy** cho từng loại dữ liệu.

## 3. Thuật ngữ nền tảng

### 3.1. Data owner

**Data owner** là bên chịu trách nhiệm về ý nghĩa, chất lượng, chính sách và quyết định quan trọng của một tập dữ liệu. Trong tổ chức, owner có thể là người/đội nghiệp vụ được giao trách nhiệm, không nhất thiết là người trực tiếp chạy database.

Ví dụ: đội phụ trách Customer Domain quyết định quy tắc xác minh email và tính đúng đắn của hồ sơ khách hàng.

### 3.2. Service owner

**Service owner** là đội chịu trách nhiệm code, triển khai, uptime và vận hành một service. Service owner và data owner có thể cùng một đội nhưng không phải lúc nào cũng trùng nhau.

Ví dụ: Platform Team vận hành cluster PostgreSQL dùng chung nhưng **không phải owner của số dư thanh toán** lưu trong đó.

### 3.3. Data steward

**Data steward** là người/nhóm chăm sóc metadata, định nghĩa thuật ngữ, chất lượng, luồng yêu cầu sửa dữ liệu và tuân thủ chính sách. Steward phối hợp với owner, consumer và bộ phận bảo mật/tuân thủ khi cần.

### 3.4. System of Record (SoR)

**System of Record** là nguồn được công nhận có tính thẩm quyền cho một loại dữ liệu hoặc một thuộc tính trong phạm vi xác định. Ví dụ:

- Customer Service có quyền quyết định email đã xác minh của khách hàng.
- Order Service có quyền quyết định trạng thái nghiệp vụ của đơn hàng.
- Payment Service có quyền quyết định trạng thái thanh toán nội bộ đã đối soát.
- Inventory Service có quyền quyết định lượng hàng khả dụng và reservation ledger.

**Không nhất thiết có một SoR cho cả thực thể Customer theo mọi góc nhìn.** Địa chỉ giao hàng của một đơn đã đặt có thể là snapshot do Order sở hữu, trong khi địa chỉ mặc định hiện tại do Customer sở hữu.

### 3.5. Authoritative source và bản sao

**Authoritative source** trả lời câu hỏi: “Nếu có xung đột, hệ thống nào được phép xác nhận và sửa giá trị gốc?”. Bản sao có thể là:

- Cache để giảm latency.
- Materialized read model để phục vụ UI.
- Search index để tìm kiếm.
- Analytics warehouse phục vụ báo cáo.
- Snapshot lịch sử để giữ tính bất biến của một giao dịch.
- Backup phục hồi dữ liệu.

Có bản sao không đồng nghĩa consumer được phép **ghi ngược** vào nguồn gốc.

### 3.6. Bounded context

Trong Domain-Driven Design, **bounded context** là phạm vi mà một mô hình và từ vựng nghiệp vụ có nghĩa nhất quán. Một từ như “Customer” có thể mang nghĩa khác trong Sales, Billing và Support.

Ranh giới bounded context giúp xác định ownership; nhưng không phải mọi bounded context luôn bằng đúng một deployable microservice.

### 3.7. Data contract

**Data contract** mô tả giao diện, schema và semantics mà producer cung cấp cho consumer: field, type, nullability, constraints, version, freshness, chất lượng và quy trình thay đổi. Contract có thể áp dụng cho REST API, gRPC, event payload, CDC stream hoặc dataset phục vụ phân tích.

### 3.8. Data lineage

**Data lineage** theo dõi nguồn gốc và biến đổi: dữ liệu được lấy từ đâu, đi qua bước xử lý nào, vào bảng/report nào, và phụ thuộc vào hệ thống nào. Lineage trả lời cả tác động **xuôi dòng (impact)** lẫn truy nguyên **ngược nguồn (provenance)**.

## 4. Phân biệt các loại quyền sở hữu

Cần tránh câu hỏi mơ hồ “ai sở hữu bảng này?” nếu chưa phân biệt:

| Loại trách nhiệm | Điều quyết định | Ví dụ |
| --- | --- | --- |
| **Business ownership** | Ý nghĩa/định nghĩa, chính sách nghiệp vụ, mức chất lượng | Số dư khả dụng nghĩa là gì? |
| **Logical data ownership** | Dữ liệu authoritative, lệnh ghi hợp lệ, trạng thái lifecycle | Payment quyết định payment status |
| **Service ownership** | API, implementation, triển khai, SLO, runbook | Đội Payment xây dựng Payment Service |
| **Physical data custody** | Database/storage được vận hành ở đâu | DBA/Platform quản lý PostgreSQL |
| **Security ownership** | Quyền truy cập, phân loại, mã hóa, audit | Security + service/data owner |
| **Stewardship** | Data catalog, từ điển dữ liệu, quality issue | Data Governance Team |
| **Consumer responsibility** | Dùng dữ liệu đúng contract, xử lý stale/duplicate | Notification xử lý CustomerUpdated |

Một platform engineer có quyền admin DB để backup không vì thế được tự quyết định cập nhật payment state cho các nghiệp vụ. Ngược lại, data owner không nhất thiết có quyền root trên cluster.

### 4.1. Một trường dữ liệu có thể có nhiều đối tượng chịu trách nhiệm khác nhau

Ví dụ thuộc tính `shippingAddress`:

- **Customer** sở hữu address book hiện tại.
- **Order** sở hữu **snapshot địa chỉ trên đơn** tại lúc checkout.
- **Fulfillment** sở hữu thông tin fulfillment instruction và shipment tracking.
- **Analytics** giữ bản sao/pseudonymized projection cho báo cáo.

Nếu khách sửa địa chỉ mặc định sau khi đặt hàng, không thể tự động thay địa chỉ trên đơn đã bàn giao cho hãng vận chuyển nếu business contract không cho phép.

**Bản đồ phải nói rõ ý nghĩa và thời điểm của giá trị**, không chỉ đặt tên field giống nhau.

## 5. Mẫu kiến trúc sở hữu dữ liệu theo domain

Sơ đồ tham khảo:

~~~text
                    Client / API Gateway
                             │
             ┌───────────────┼─────────────────┐
             ▼               ▼                 ▼
       Customer Service   Order Service   Catalog Service
          │  SoR           │  SoR            │  SoR
          ▼                ▼                 ▼
       Customer DB       Order DB         Catalog DB
             │               │                 │
             │ Customer*     │ Order*          │ Product*
             ▼ events        ▼ events          ▼ events
          Event Broker / Schema Registry / Contract Catalog
             │               │                 │
             ├───────────────┼─────────────────┤
             ▼               ▼                 ▼
       Notification      Fulfillment       Search / Analytics
       read model        read model        projections/warehouse
~~~

Trong ví dụ:

- Mỗi domain có quyền ghi dữ liệu authoritative của mình.
- Các service khác nhận bản sao qua API hoặc event.
- Không cho consumer sửa DB của owner như thể là bảng dùng chung.
- Một service có thể lưu reference ID hoặc snapshot đúng mục đích mà không giành quyền sở hữu thực thể gốc.
- Event broker là phương tiện truyền thông tin, **không mặc định là SoR của business state**; điều này chỉ khác nếu kiến trúc đã chủ đích dùng event sourcing và event log được công nhận là nguồn authoritative.

## 6. Những thực thể cần đưa vào bản đồ

Không chỉ liệt kê table. Nên điều tra ở mức:

### 6.1. Thực thể nghiệp vụ

Customer, Account, Product, SKU, Warehouse, StockReservation, Order, OrderLine, Payment, Refund, Shipment, Invoice, Subscription, LoyaltyPoint.

### 6.2. Thuộc tính quan trọng

- Identifier/canonical key.
- Status và state transition.
- Amount, currency, tax, rounding.
- Ownership/tenant ID.
- Timestamp, effective date, expiration.
- Địa chỉ/email/phone.
- Consent/preferences.
- Idempotency key, event ID, correlation ID.

Một thực thể lớn đôi khi cần phân ownership ở **cấp thuộc tính hoặc phân khúc nghiệp vụ**, nhưng tránh tách quá chi li khiến một thao tác phải đi qua nhiều service không cần thiết.

### 6.3. Dataset kỹ thuật

- API responses.
- Topic/queue/event schemas.
- CDC streams và outbox.
- Search indexes/materialized views.
- Cache keys và TTL.
- Files/object storage.
- Warehouse tables, BI dashboards và feature datasets.
- Audit logs, backups và lưu trữ archive.

### 6.4. Dữ liệu không được thấy trong DB diagram

- Secrets và certificates trong config/secret manager.
- User identifiers trong logs/traces.
- Export CSV gửi cho đối tác.
- Dữ liệu trong dead-letter queue.
- Bản sao trong CDN và client cache.
- Dữ liệu tạm trong memory hoặc local filesystem của worker.

Một yêu cầu xóa hoặc điều tra rò rỉ dữ liệu sẽ thất bại nếu bản đồ chỉ ghi database chính.

## 7. Chọn SoR theo nghiệp vụ, không theo service gọi đầu tiên

Giả sử luồng checkout:

~~~text
Customer → Order → Payment → Fulfillment
          ↘ Inventory
~~~

Ai sở hữu “Order đã thanh toán”?

- **Payment** sở hữu kết quả thu tiền/authorization/refund của giao dịch thanh toán.
- **Order** sở hữu trạng thái đơn hàng theo business workflow.
- Order chỉ chuyển sang `PAID` khi nhận được sự kiện/kết quả đáng tin từ Payment theo contract, bao gồm idempotency và đối soát.

Điều này không tạo hai nguồn chân lý nếu semantics rõ:

| Giá trị | SoR | Các service khác có thể có |
| --- | --- | --- |
| Payment transaction status | Payment | Order lưu payment reference/trạng thái đã tổng hợp |
| Order lifecycle status | Order | Fulfillment/Customer UI có projection |
| Stock available/reserved | Inventory | Order nhận reservation result |
| Current default shipping address | Customer | UI cache, Order có snapshot |
| Shipment tracking status | Fulfillment | Order UI projection |

**Đừng định nghĩa SoR theo vị trí dữ liệu được copy nhiều nhất** hoặc nơi UI đọc nhanh nhất.

### 7.1. Một SoR có thể là hệ thống bên ngoài

Nếu ngân hàng hoặc đối tác thanh toán là nguồn thẩm quyền của kết quả settlement cuối cùng, Payment Service có thể là **SoR cho trạng thái payment nội bộ đã đối soát**, nhưng vẫn cần đối chiếu với provider statements. Nên ghi rõ cấp độ authoritative: internal view, provider-authoritative ledger, reconciled final state.

### 7.2. Dữ liệu phát sinh từ nhiều nguồn

“Customer 360” trong Analytics có thể kết hợp CRM, Support và Order. Analytics có quyền định nghĩa **dataset tổng hợp** và transformation logic, nhưng không tự trở thành SoR cho email đã xác minh, đơn hàng hoặc refund.

## 8. Ma trận data ownership thực tế

Bảng mẫu cho nền tảng bán hàng:

| Dữ liệu/ý nghĩa | SoR/service quyết định | Kho gốc | Consumers | Kênh cung cấp | Cập nhật/consistency |
| --- | --- | --- | --- | --- | --- |
| Customer profile hiện tại | Customer | Customer DB | Order, Support, Analytics | API + CustomerUpdated | Eventual cho projection |
| Email đã xác minh | Identity/Customer theo policy | Identity DB | Notification, Order | API/event có version | Theo authoritative verification |
| Product title/price catalogue | Catalog/Pricing tùy domain | Catalog/Pricing DB | Search, Order UI | API + ProductChanged | Projection có freshness policy |
| Stock reservation | Inventory | Inventory DB/ledger | Order, Fulfillment | Command API + ReservationChanged | Xác nhận tại owner |
| Order state | Order | Order DB | Customer UI, Analytics | Order API + OrderStatusChanged | Commit ở Order |
| Payment authorization | Payment | Payment DB/ledger | Order, Risk, Finance | API + PaymentAuthorized | Idempotent, đối soát |
| Refund state | Payment/Refund domain | Payment DB | Order, Support, Analytics | Refund API/event | Có trạng thái pending/final |
| Shipment tracking | Fulfillment | Fulfillment DB | Order UI, Support | API + ShipmentUpdated | Eventual |
| Search index | Search | Search storage | Client search | Query endpoint | Derived, rebuildable |
| Revenue report | Analytics/Finance data product | Warehouse | Finance/BI | Curated dataset | Theo reporting cut-off |

**Bảng này là khung ra quyết định.** Với một doanh nghiệp khác, Pricing có thể tách khỏi Catalog, Identity tách khỏi Customer, và Payment ledger có thể do Finance domain sở hữu. Nên ghi cả owner xác nhận và ngày rà soát.

## 9. Chọn mức hạt của bản đồ

Một bản đồ quá tổng quan như “Order phụ thuộc Customer” chưa đủ khi cần sửa bug. Nhưng ghi mọi cột của mọi bảng ngay từ đầu cũng gây chi phí quản trị lớn.

Gợi ý ba lớp:

### 9.1. Lớp domain/service

~~~text
Customer Domain ──► Order Domain ──► Payment Domain
                        │
                        └──────────► Fulfillment Domain
~~~

Dùng để hiểu ownership, user journeys và trách nhiệm giữa teams.

### 9.2. Lớp dataset/operation

~~~text
Order API:
  POST /orders             writes Order
  GET /orders/{id}         reads Order
  OrderCreated v2          publishes Order snapshot
  OrderPaymentConfirmed v1 consumes PaymentAuthorized v1
~~~

Dùng để đánh giá hợp đồng và tác động thay đổi.

### 9.3. Lớp field/lineage

~~~text
customer.email_verified
  → CustomerUpdated.emailVerified
  → Notification.customer_contact_projection.email_verified
  → send_email eligibility check
~~~

Dùng cho dữ liệu nhạy cảm, critical calculations, consent, deletion, chất lượng và điều tra sai lệch.

**Chọn field-level lineage có chọn lọc**: payment amount, consent, PII, tax và các trường business-critical cần sâu hơn thông tin hiển thị không trọng yếu.

## 10. Quy trình lập bản đồ từng bước

### Bước 1 — Xác định phạm vi và business journeys

Bắt đầu với một phạm vi rõ như **Checkout**, **Customer onboarding** hoặc **Refund**, thay vì cố map toàn bộ công ty trong một lần.

Ghi:

- User journey và kết quả đúng cần đạt.
- Những service trong critical path.
- Các sự kiện hoặc batch có thể hoàn thành sau request đầu.
- Các dữ liệu được tạo/đọc/sửa/xóa.
- Mục tiêu SLO, bảo mật và pháp lý.

### Bước 2 — Liệt kê entities và field nhạy cảm

Từ domain model, API schemas, DB DDL, event definitions và business documentation. Phân loại những field:

- Là khóa định danh/khóa ngoại logic.
- Tác động tiền, quyền, tồn kho hoặc trạng thái giao dịch.
- Chứa PII/sensitive data.
- Có yêu cầu retention/deletion riêng.
- Có nhiều nơi đọc hoặc sao chép.

### Bước 3 — Gán owner và nguồn gốc

Với mỗi thực thể/thuộc tính:

- Ai được phép tạo?
- Ai được phép cập nhật hoặc hủy?
- Ai quyết định field hợp lệ?
- Có hệ thống nguồn ngoài không?
- Khi xung đột, nơi nào có quyền xác nhận cuối cùng?
- Ai nhận escalation khi dữ liệu sai?

Nếu không thể trả lời, ghi **ownership gap** và owner cần xác minh, không tự gán một service chỉ vì nó đang giữ bản sao.

### Bước 4 — Tìm nơi lưu và consumers

Dùng:

- Service catalog và kiến trúc.
- Database schema và database accounts.
- API gateways/service discovery.
- Event broker topics/subscriptions.
- CDC pipeline, ETL jobs, data warehouse.
- Cache/search index và object storage.
- Logs, backups, exports và external partners.

Không chỉ đọc code để kết luận; những jobs theo lịch hoặc emergency tools có thể đọc dữ liệu mà runtime tracing bình thường không thấy.

### Bước 5 — Vẽ flows và transformation

Cho từng cạnh producer→consumer, ghi:

- Operation/giao thức (HTTP, gRPC, event, CDC, batch).
- Schema/version và hợp đồng.
- Idempotency, ordering, retry, timeout.
- Dữ liệu nào truyền qua và để làm gì.
- Freshness, latency và expected lag.
- Data classification và chính sách truy cập.
- Nơi lưu bản sao và thời hạn xóa.
- Dấu vết audit/correlation.

### Bước 6 — Phê duyệt và đưa vào repository/catalog

Owner và consumer xác nhận graph đúng; lưu metadata dưới dạng tài liệu có version hoặc data catalog có workflow cập nhật. Quy định một nơi authoritative cho metadata và quy trình thay đổi.

### Bước 7 — Kiểm chứng với runtime evidence

Đối chiếu:

- Tracing/network flows.
- SQL access và database audit nếu phù hợp.
- Broker subscriptions, consumer groups.
- Pipeline DAG, lineage reports.
- Logs/deploy config và secrets/IAM policies.

Runtime discovery có thể thiếu đường chỉ chạy theo quý; declared dependencies bổ sung phần chưa được quan sát.

### Bước 8 — Duy trì khi thay đổi

Mỗi change liên quan dataset, schema, service owner hoặc consumer nên cập nhật catalog/contract/lineage và qua review tương ứng. Một bản đồ đúng hôm nay nhưng lỗi thời sau ba releases có thể gây incident lớn hơn là không có map.

## 11. Cách biểu diễn bản đồ bằng bảng và đồ thị

### 11.1. Bảng ownership chuẩn

Gợi ý các cột:

~~~text
data_id
business_term
definition
domain
authoritative_service
physical_store
schema_or_contract_version
write_interface
consumer_services
replication_path
freshness_target
data_classification
retention_policy
deletion_procedure
business_owner
technical_owner
steward
last_verified_at
evidence
~~~

Không phải mọi dataset cần tất cả trường ngay ngày đầu; cần xác định **required metadata tối thiểu** cho từng classification/risk tier.

### 11.2. Directed graph

~~~text
    Customer SoR ─────────CustomerUpdated─────────► Notification
          │                       │                      │
          │                       ▼                      ▼
          └──Customer API──────► Order             Email Provider
                                   │
                           OrderCreated event
                                   │
                                   ▼
                               Analytics
~~~

Mũi tên nên ghi **ý nghĩa**. Phải thống nhất một quy ước: ví dụ producer→consumer đối với luồng dữ liệu và caller→callee đối với dependency. Nếu hai loại graph chung màn hình, dùng nhãn/cạnh khác nhau tránh hiểu nhầm.

### 11.3. Data flow diagram và trust boundary

Đối với PII/secret, có thể thể hiện thêm trust boundary:

~~~text
[Public Client]
      │ authenticated request
      ▼
[API Gateway] ───► [Customer Service / Private Network]
                           │ encrypted DB connection
                           ▼
                      [Customer DB]
                           │ approved pseudonymized export
                           ▼
                    [Analytics Zone]
~~~

Mỗi đoạn vượt trust boundary phải có mục đích, quyền truy cập, bảo vệ truyền dẫn và hạn chế dữ liệu.

### 11.4. Versioned metadata dạng YAML

~~~yaml
dataAsset:
  id: customer.email_verified
  version: 1
  definition: "Email đã được xác minh theo quy trình Identity"
  domain: customer-identity
  authoritativeService: identity-service
  classification: personal
  storage:
    type: postgresql
    logicalName: identity-db
  writeOperations:
    - verify-email
    - revoke-verification
  consumers:
    - service: notification-service
      contract: CustomerEmailVerified.v1
      purpose: transactional-notification
      refreshMode: event
      maxExpectedLagSeconds: 120
  governance:
    ownerTeam: identity-domain
    stewardTeam: data-governance
    retentionPolicyRef: identity-retention-policy
    deletionProcedureRef: erase-customer-contact
  evidence:
    lastVerifiedAt: "2026-11-12T02:00:00Z"
    sources:
      - api-schema
      - event-contract
      - production-observation
~~~

Trong ví dụ, `maxExpectedLagSeconds: 120` là mục tiêu minh họa, không khẳng định tất cả hệ thống event đều có lag tối đa 120 giây.

## 12. Database per service: ranh giới sở hữu logic và vật lý

Mô hình thường được khuyến khích:

~~~text
Customer Service → Customer-owned schema/database
Order Service    → Order-owned schema/database
Payment Service  → Payment-owned schema/database
~~~

Lợi ích:

- Một service kiểm soát schema migration và domain invariants của mình.
- Consumer không phụ thuộc trực tiếp bảng nội bộ.
- Quyền DB có thể giới hạn theo service identity.
- Có thể tách scale, backup và lifecycle phù hợp.
- Một lỗi query hoặc migration ít có nguy cơ phá các service khác qua bảng dùng chung.

**Không nhất thiết mỗi service phải có một máy database riêng.** Có thể dùng cùng PostgreSQL cluster nhưng database/schema/credentials và quyền sở hữu dữ liệu được tách logic, tùy yêu cầu isolation và vận hành.

### 12.1. Shared DB là anti-pattern khi nào?

Nếu Order chạy:

~~~sql
SELECT o.id, c.email
FROM order_schema.orders o
JOIN customer_schema.customers c
  ON c.id = o.customer_id;
~~~

và Order có quyền đọc trực tiếp schema nội bộ của Customer, hai team bị ràng buộc vào DDL, deployment và semantics của nhau. Customer đổi schema hoặc chuyển DB engine làm Order hỏng.

Đây là một loại coupling cần nhận diện trên bản đồ. Trong một giai đoạn migration có thể có legacy shared DB, nhưng phải ghi rõ technical debt, owner và lộ trình loại coupling.

### 12.2. Quyền truy cập DB

Chỉ service owner có quyền ghi bảng dữ liệu gốc của mình. Consumer nhận dữ liệu qua API/event/data product được quản lý thay vì dùng tài khoản DB admin. Các account backup/migration/audit cần quyền đặc thù, tách khỏi request runtime identity.

### 12.3. Foreign key liên service

Trong một database chia theo service, không thể giả định foreign key xuyên hai database vẫn được enforce như monolith. Order có thể giữ `customerId` làm reference logic, kiểm tra qua Customer API/event contract và định nghĩa xử lý khi Customer bị xóa.

Bản đồ cần ghi **referential integrity ownership**: ai xác minh ID và khi nào, idempotency/reconciliation ra sao.

## 13. Phân biệt “dữ liệu gốc”, “snapshot” và “projection”

Một nguồn dữ liệu thường có nhiều biểu diễn hợp lệ.

### 13.1. Data source of truth

Customer profile hiện tại nằm ở Customer DB; Customer Service có API xác minh và sửa email. Đây là dữ liệu hiện tại có thẩm quyền theo contract.

### 13.2. Snapshot nghiệp vụ

Order lưu địa chỉ giao hàng, giá bán và thuế **tại thời điểm đặt hàng**. Dù Catalog/Customer thay đổi sau đó, snapshot trên order có thể phải bất biến để đối soát, phục vụ fulfillment hoặc pháp lý.

**Không coi snapshot khác dữ liệu hiện tại là lỗi đồng bộ.** Nó có semantics thời gian khác nhau.

### 13.3. Read model/projection

Notification lưu `customer_email_projection` từ CustomerUpdated để gửi thông báo, Search lưu product index, Analytics tổng hợp doanh thu. Đây là bản sao/derived dataset; cần metadata về nguồn, thời gian cập nhật, lag, quyền truy cập và rebuild.

### 13.4. Cache

Cache có TTL/eviction và thường là dữ liệu tái tạo được. Nếu cache hỏng, hệ thống có thể đọc lại nguồn; nhưng cần kiểm soát cache stampede và bảo vệ dữ liệu nhạy cảm.

### 13.5. Historical ledger

Một sổ cái giao dịch có thể yêu cầu append-only/correction entries thay vì sửa record cũ. Data map cần ghi rõ “sửa lỗi bằng compensating entry” thay vì UPDATE trực tiếp.

## 14. Luồng đồng bộ: API hoặc gRPC

Khi Order cần xác thực một Customer đang tồn tại, có thể gọi Customer API:

~~~text
POST /orders
      │
      ├──► Customer GET /customers/{id} (lookup)
      ├──► Inventory POST /reservations
      └──► Order DB commit
~~~

Ưu điểm:

- Đọc dữ liệu gần thời điểm hiện tại.
- Không cần lưu bản sao cho mọi consumer.
- Owner kiểm soát response và authorization.
- Có thể định nghĩa contract rõ ràng.

Nhược điểm:

- Coupling runtime về latency và availability.
- Fan-out làm request chậm.
- Retry/timeout có thể gây tải amplification.
- Không thể bảo đảm giao dịch atomic qua nhiều service chỉ bằng API đồng bộ.

Trên bản đồ, cần ghi:

- API operation và version.
- Caller/callee, auth scope và purpose.
- Dữ liệu trả về/được gửi.
- Timeout/retry/idempotency.
- Fallback behavior.
- SLO và dependency criticality.

**Không dùng API response của owner rồi lưu vĩnh viễn như dữ liệu gốc mới**, trừ khi đó là snapshot có nghĩa nghiệp vụ rõ.

## 15. Luồng bất đồng bộ: domain events

Ví dụ Customer đổi email:

~~~text
Customer Service
  1. Verify business rule
  2. Commit Customer update + outbox
  3. Publish CustomerEmailChanged.v1
             │
             ▼
         Message Broker
             │
         ┌───┴──────────┐
         ▼              ▼
   Notification       Analytics
   projection         dataset
~~~

Một event nên biểu diễn **sự kiện nghiệp vụ đã xảy ra**: `CustomerEmailChanged`, không chỉ “hãy sửa cột email trong bảng X”.

### 15.1. Event contract minh họa

~~~json
{
  "eventId": "evt-10001",
  "eventType": "CustomerEmailChanged",
  "schemaVersion": 1,
  "aggregateId": "cust-123",
  "aggregateVersion": 8,
  "occurredAt": "2026-11-12T02:15:00Z",
  "traceId": "trace-example",
  "data": {
    "emailVerified": true,
    "contactReference": "contact-456"
  }
}
~~~

Không mặc định phát raw email cho mọi consumer. Event nên chứa tối thiểu dữ liệu mà consumers cần; một số consumer có thể nhận reference để truy vấn dữ liệu nhạy cảm qua API có kiểm soát.

### 15.2. Producer chịu trách nhiệm gì?

- Định nghĩa contract và semantics của event.
- Chỉ phát event sau khi business change thực sự durable.
- Có eventId, aggregateId và version/correlation thích hợp.
- Đảm bảo publish reliability bằng outbox/CDC hoặc cơ chế tương đương.
- Công bố thay đổi schema và compatibility rules.
- Xử lý provenance của dữ liệu trong payload.

### 15.3. Consumer chịu trách nhiệm gì?

- Xử lý idempotent vì broker có thể deliver lại.
- Chấp nhận event trễ/duplicate/out-of-order theo contract.
- Giữ version/offset/checkpoint hoặc dedup store phù hợp.
- Quan sát lag, DLQ và projection freshness.
- Không diễn giải một event cũ là trạng thái hiện tại khi có aggregateVersion mới hơn.
- Xóa hoặc sửa projection theo sự kiện và chính sách retention.

### 15.4. Event không tự đồng bộ mọi thứ tức thời

Order và Analytics có thể nhìn trạng thái Customer khác nhau trong vài giây. Đó có thể là eventual consistency được chấp nhận. Điều quan trọng là **định nghĩa freshness target và cách consumer biết bản sao stale**.

## 16. Transactional outbox và dữ liệu có thể phát lại

Nếu Customer ghi DB thành công nhưng gửi event vào broker thất bại:

~~~text
Customer DB commit = SUCCESS
Publish CustomerEmailChanged = FAILED
Notification projection vẫn cũ
~~~

Một thiết kế **transactional outbox** lưu record thay đổi và outbox event trong cùng transaction; publisher đọc outbox và gửi lại sau khi lỗi.

~~~text
BEGIN
  UPDATE customer ...
  INSERT INTO outbox(event_id, type, payload, ...)
COMMIT
   │
   ▼
Outbox Publisher → Broker → Consumer Projection
~~~

Outbox giảm nguy cơ “DB commit nhưng không có event”, nhưng không bảo đảm exactly-once end-to-end. Publisher có thể gửi cùng event nhiều lần khi crash sau send trước khi mark published. Consumer cần idempotent handling.

**Bản đồ dữ liệu nên ghi rõ** outbox nằm ở service nào, topic nào, dữ liệu nào đi qua, retry/DLQ policy và rebuild procedure.

## 17. Data contract cho API, event và dataset

Một data contract nên bao gồm ít nhất:

1. **Identity:** tên, version, owner và consumer liên quan.
2. **Schema:** field names, types, required/optional, nullability.
3. **Semantics:** ý nghĩa nghiệp vụ, đơn vị (VND, cents, UTC), enum values.
4. **Quality constraints:** uniqueness, non-negative amount, valid transitions.
5. **Operational properties:** latency, availability, freshness, retention.
6. **Privacy/security:** classification, purpose, data minimization.
7. **Change policy:** compatibility, deprecation period, migration path.
8. **Observability:** correlation, metrics, quality checks và incident owner.

### 17.1. Ví dụ schema contract đơn giản

~~~yaml
contract:
  name: OrderCreated
  version: 2
  producer: order-service
  ownerTeam: orders-domain
  fields:
    orderId:
      type: string
      required: true
      description: "Business identifier của Order"
    customerId:
      type: string
      required: true
      description: "Reference tới Customer authoritative"
    amountMinorUnits:
      type: integer
      required: true
      minimum: 0
    currency:
      type: string
      required: true
      example: VND
    occurredAt:
      type: instant
      required: true
  compatibility:
    mode: backward-compatible-for-existing-consumers
  classification: internal
  retentionPolicyRef: order-events-policy
~~~

Một số contract cần phân loại ở **cấp field**; `customerId` có thể là dữ liệu cá nhân gián tiếp tùy khả năng liên kết và chính sách của tổ chức.

### 17.2. Cẩn trọng với đơn vị và kiểu số

Gửi `totalAmount: 100.0` mà không ghi đơn vị hoặc cách làm tròn dễ tạo lỗi thanh toán. Dùng minor units hoặc decimal có precision/scale và định nghĩa currency/rounding rõ.

### 17.3. Thay schema

- Thêm field optional thường dễ tương thích, nhưng consumer strict parser có thể không chấp nhận.
- Đổi tên/xóa field đang được consumer dùng là breaking change trong nhiều hợp đồng.
- Đổi ý nghĩa field mà giữ tên cũ còn nguy hiểm vì hệ thống có thể chạy mà kết quả sai.
- Đổi enum cần kiểm tra cách consumer xử lý unknown values.
- Trong hệ event-driven, consumer có thể đọc lại sự kiện cũ từ nhiều tháng trước.

Không quyết định compatibility chỉ bằng cú pháp JSON; cần kiểm tra semantics.

## 18. Consumer-driven contract testing

Rủi ro thường gặp:

- Order tin Customer API trả `verifiedEmail`.
- Customer đã đổi field thành `emailStatus`.
- Unit test Order vẫn pass với stub cũ.
- Production Order không parse được.

Consumer-driven contract test như Pact/Spring Cloud Contract hoặc schema verification phù hợp có thể:

1. Cho consumer mô tả interaction cần dùng.
2. Provider verification kiểm tra provider thật đáp ứng interaction.
3. CI/deployment gate kiểm tra version tương thích.
4. Báo những consumers bị ảnh hưởng trước khi producer thay đổi.

Điều này không thay thế end-to-end test, security validation, performance test hoặc kiểm tra data quality. Đặc biệt với dữ liệu dùng trong tính tiền, contract phải kiểm tra cả semantics và data quality invariants.

## 19. Data lineage: truy nguyên nguồn và tác động thay đổi

Giả sử KPI `net_revenue` được tính:

~~~text
Payment Transactions
  → Settlement Reconciliation
  → Finance Curated Payments
  ─┐
   ├→ Daily Net Revenue Report
  ─┘
Refund Transactions
  → Refund Reconciliation
  → Finance Curated Refunds
~~~

Khi Payment đổi ý nghĩa `capturedAmount`, cần biết:

- Những pipelines nào dùng field đó.
- Report nào có thể sai.
- Hệ thống nào đang giữ dữ liệu lịch sử.
- Ai có quyền đổi transformation.
- Có cần backfill/recompute các kỳ trước không.

### 19.1. Lineage trực tiếp

`OrderCreated.amountMinorUnits → analytics.raw_orders.amount_minor → finance.order_gmv`.

### 19.2. Lineage biến đổi

Khi tính `netRevenue = successfulCaptures − settledRefunds`, ghi công thức, filter, timezone, exchange-rate policy và dữ liệu đầu vào. Không chỉ ghi cột nguồn vì công thức quyết định semantics.

### 19.3. Lineage theo dòng/record

Một số hệ thống cần truy nguyên record-level bằng eventId, transactionId hoặc lineage tokens. Điều này đòi hỏi data governance và bảo mật vì identifiers có thể nhạy cảm. Không đưa mọi record ID vào metrics có cardinality lớn.

### 19.4. Tác động ngược và xuôi

- **Backward lineage:** doanh thu hôm nay sai → dữ liệu raw/transform nào tạo ra số này?
- **Forward impact:** định sửa field `paymentStatus` → những dashboard, models và consumers nào sẽ bị ảnh hưởng?

## 20. Vòng đời dữ liệu và sự biến đổi ownership

Một dataset có lifecycle:

~~~text
Create → Validate → Persist → Publish/Share → Use/Transform
       → Archive/Retain → Correct/Delete/Expire
~~~

Cần xác định cho từng bước:

| Pha | Bên chịu trách nhiệm | Câu hỏi |
| --- | --- | --- |
| Tạo | Producer/SoR | Ai được tạo ID và giá trị? |
| Xác minh | Domain owner | Business constraints nào bắt buộc? |
| Lưu | Service owner + storage custodian | Giao dịch, backup và encryption nào? |
| Phát/chia sẻ | Producer và data governance | Consumer nào được nhận và dữ liệu nào? |
| Dùng | Consumer | Dùng đúng mục đích, version và freshness chưa? |
| Sửa | Authoritative owner | Sửa bằng API/compensation hay UPDATE? |
| Xóa | Domain/privacy owner và mọi custodians | Xóa đâu, xác nhận thế nào? |
| Lưu trữ | Records/Compliance owner | Retention, legal hold, backup lifecycle? |

**Một business event đã phát không thể đơn giản “xóa khỏi lịch sử” ở mọi broker/consumer** mà không có kiến trúc và chính sách xử lý phù hợp. Nếu có yêu cầu xóa dữ liệu cá nhân, cần thiết kế data minimization từ đầu để hạn chế payload nhạy cảm tồn tại dài hạn.

## 21. Phân loại dữ liệu và quyền truy cập

Ví dụ classification tiers:

- **Public:** thông tin được phép công bố.
- **Internal:** dữ liệu vận hành không công khai.
- **Confidential:** thông tin hợp đồng, giá đặc biệt, báo cáo chưa phát hành.
- **Personal/regulated:** dữ liệu định danh hoặc dữ liệu chịu chính sách pháp lý.
- **Secret:** token, private key, credential (thường nên lưu trong secret manager, không là business dataset).

Tổ chức có thể dùng hệ classification khác; điều quan trọng là owner thống nhất ý nghĩa và controls.

### 21.1. Metadata cấp field

~~~yaml
fields:
  customerId:
    classification: personal-pseudonymous
    permittedPurposes:
      - customer-support
      - order-linkage
  email:
    classification: personal
    permittedPurposes:
      - account-contact
      - transactional-email
    accessPolicyRef: customer-contact-policy
  passwordHash:
    classification: security-sensitive
    permittedPurposes:
      - authentication-verification
    sharing: prohibited
~~~

### 21.2. Data minimization

Notification cần gửi email xác nhận có thể nhận **contactReference** thay vì toàn bộ profile. Analytics có thể cần pseudonymous customer key nhưng không cần raw email/phone. Càng ít bản sao PII, bản đồ càng đơn giản và rủi ro rò rỉ càng thấp.

### 21.3. IAM và service-to-service access

Chỉ caller có scope/purpose được phép mới truy cập dataset. Với database per service, runtime identity của Notification không nên có quyền SELECT toàn bộ Customer DB. Access đi qua API/data product đã định nghĩa hoặc đường export được phê duyệt.

### 21.4. Audit

Theo dõi ai thay đổi permission, export dữ liệu, dùng API nhạy cảm hoặc thực hiện correction. Audit log cần bảo vệ toàn vẹn và tránh ghi raw secrets/PII không cần thiết. Retention và access log cũng cần nằm trong governance policy.

## 22. Quyền riêng tư, consent và yêu cầu xóa

Một yêu cầu xóa dữ liệu ở Customer có thể phải ảnh hưởng tới:

~~~text
Customer DB (SoR)
   ├──► Notification contact projection
   ├──► Analytics warehouse / BI extract
   ├──► Search index
   ├──► Cache
   ├──► Data export cho đối tác
   ├──► Object storage
   └──► Backups/logs theo chính sách retention
~~~

Bản đồ giúp liệt kê **mọi nơi lưu và mọi consumer** để phân loại cách thực hiện xóa, ẩn danh, hạn chế xử lý hoặc giữ theo nghĩa vụ pháp lý.

### 22.1. Không có một cơ chế xóa áp dụng cho mọi dữ liệu

- Dữ liệu account có thể cần xóa khi đủ điều kiện.
- Hóa đơn hoặc transaction records có thể phải lưu theo nghĩa vụ pháp lý.
- Snapshot order có thể cần giữ nhưng pseudonymize một số field.
- Log/backup có thể có retention và cơ chế expiration riêng.
- Derived datasets có thể cần rebuild hoặc emit tombstone event.

Cần xác định luật và hợp đồng áp dụng cho hệ thống cụ thể; không tự giả định một quy tắc retention phổ quát.

### 22.2. Truyền yêu cầu xóa

Một event hoặc workflow:

~~~text
Privacy Request
      │
      ▼
Customer/Privacy Orchestrator
      │
      ├──► Customer SoR
      ├──► Notification projection
      ├──► Search/Analytics
      ├──► External processors
      └──► Evidence / completion tracking
~~~

Mỗi consumer phản hồi trạng thái đã xử lý hoặc ngoại lệ hợp lệ. Orchestrator cần idempotency, retry, deadline, escalation và bằng chứng hoàn tất, không xem “đã publish event” là “mọi bản sao đã xóa”.

### 22.3. Consent thay đổi

Khi user thu hồi consent marketing, các service liên quan phải ngừng xử lý theo mục đích đó theo policy. Không được thay đổi interpretation chỉ bằng việc xóa một cột ở Customer DB nếu downstream vẫn giữ subscriber list cũ.

### 22.4. Data residency

Nếu dữ liệu bị giới hạn theo quốc gia/khu vực, graph cần metadata về region, replication và external processors. Cross-region failover hoặc analytics export có thể làm dữ liệu đi qua ranh giới pháp lý ngoài ý muốn. Quyết định cần dựa trên hợp đồng và hướng dẫn pháp lý của tổ chức.

## 23. Data quality: owner chịu trách nhiệm chất lượng gì?

Một bảng có dữ liệu nhưng không biết đúng hay sai không đủ cho quản trị. Có thể chọn:

| Dimension | Câu hỏi | Kiểm tra ví dụ |
| --- | --- | --- |
| Accuracy | Giá trị phản ánh thực tế? | Payment amount khớp reconciliation ledger |
| Completeness | Thiếu field/record nào? | Mọi Order PAID có payment reference |
| Uniqueness | Có bản ghi trùng? | Một idempotency key không tạo hai payment |
| Validity | Có tuân thủ rule? | Quantity > 0; currency thuộc danh sách hợp lệ |
| Consistency | Các nguồn có tương thích? | Order state phù hợp kết quả Payment |
| Timeliness/Freshness | Bản sao cập nhật đủ nhanh? | Search index lag dưới ngưỡng |
| Integrity | Quan hệ khóa và trạng thái hợp lệ? | OrderLine tham chiếu Order tồn tại |
| Traceability | Truy nguyên nguồn và biến đổi được? | Report có upstream lineage và version |

### 23.1. Quality SLO cho projection

Ví dụ Notification contact projection:

> Trong điều kiện broker và consumer hoạt động bình thường, 99% CustomerEmailChanged events được phản ánh trong projection trong vòng 60 giây.

Đo bằng `event.occurredAt` và thời gian applied, đồng thời xem clock skew, retry và out-of-order. Những ngưỡng này cần được chốt giữa producer/consumer theo use case.

### 23.2. Quality rule ở owner và consumer

Producer chịu trách nhiệm phát dữ liệu đúng contract và domain invariant. Consumer chịu trách nhiệm map/transform đúng, validate input được phép và xử lý stale/duplicate. Analytics steward chịu trách nhiệm chất lượng tập dữ liệu tổng hợp theo contract.

Một dataset có nhiều consumers không có nghĩa producer phải phục vụ mọi transformation riêng cho từng consumer.

### 23.3. Quality incident

Khi email trong Notification cũ, hãy xác định:

1. Customer SoR hiện đúng chưa?
2. CustomerUpdated event có được commit/publish?
3. Broker có tồn đọng hoặc DLQ?
4. Notification đã nhận event chưa?
5. Event có bị xử lý sai version hoặc out-of-order?
6. Projection được update nhưng API/UI cache vẫn cũ?
7. Ai chịu trách nhiệm từng đoạn?

Đồ thị và lineage giúp xác định đúng owner của **điểm hỏng**, không chỉ nơi người dùng thấy dữ liệu sai.

## 24. Data consistency và eventual consistency

Không phải tất cả service phải nhìn cùng một giá trị trong cùng một microsecond. Cần phân biệt:

- **Strong consistency trong boundary của SoR** đối với transaction/invariant yêu cầu.
- **Eventual consistency** của projections và read models.
- **Snapshot lịch sử** được cố ý giữ nguyên.
- **Unknown/pending state** của các operation cross-service chưa hoàn tất.
- **Reconciled state** khi đã đối soát với hệ thống ngoài.

### 24.1. Ví dụ payment authorization

~~~text
Order status: PAYMENT_PENDING
      │
      ├─ Request Payment.authorize
      ▼
Payment authoritative operation
      │
      ├─ Approved + event → Order marks PAID
      ├─ Declined + event → Order marks PAYMENT_FAILED
      └─ Timeout/unknown → Order keeps PENDING, reconciles
~~~

Order không được tự đặt `PAID` chỉ vì HTTP request đã được gửi. Payment không tự cập nhật Order DB. Quyền cập nhật state đi qua contract của owner.

### 24.2. Saga và compensating transactions

Khi nhiều SoR phải thay đổi cùng một business journey, có thể dùng saga orchestration/choreography và compensation:

~~~text
Order.createPending
   → Inventory.reserve
   → Payment.authorize
   → Order.confirm
~~~

Nếu Payment từ chối sau khi Inventory đã giữ hàng, có thể phát hành command release reservation. Mỗi domain thực hiện transaction riêng, có idempotency.

Compensation **không luôn đảo ngược được mọi tác động** (ví dụ email đã gửi hoặc hàng đã giao). Bản đồ cần ghi irreversible side effects và quy trình nghiệp vụ ngoại lệ.

### 24.3. Cross-service foreign key

Một Order có `customerId`, nhưng Customer đang ở database khác. Order phải định nghĩa tại điểm nào kiểm tra ID, xử lý khi Customer bị xóa, và có cần snapshot thông tin để giữ lịch sử hay không. Không giả định database tự enforce FK xuyên service.

## 25. Idempotency, ordering và duplicate delivery

Khi dữ liệu đi qua broker/API, có thể gặp:

- Producer publish trùng do retry.
- Consumer xử lý xong nhưng mất ack.
- Event đến sai thứ tự.
- Hai service cùng cố thay giá trị.
- Network timeout nhưng side effect phía downstream đã commit.
- CDC replay từ offset cũ.

Metadata hữu ích:

~~~json
{
  "eventId": "evt-789",
  "aggregateId": "order-123",
  "aggregateVersion": 12,
  "occurredAt": "2026-11-12T03:00:00Z",
  "correlationId": "checkout-456",
  "schemaVersion": 2
}
~~~

Consumer có thể lưu processed event IDs hoặc aggregate version để không apply phiên bản cũ. Khi dùng khóa version, phải hiểu guarantees về ordering theo aggregate/partition và concurrent changes. Với side effects ngoài DB, cần idempotency key ở provider hoặc outbox/inbox strategy phù hợp.

**Đừng nhầm** “đã nhận một event” với “đã xử lý đúng một lần”. Trong nhiều hệ thống, thiết kế practical là at-least-once delivery + idempotent processing.

## 26. Data correction: ai sửa, sửa ở đâu?

Giả sử Analytics báo doanh thu sai do một payment transaction bị ghi duplicate.

Một quy trình đúng:

1. **Xác định semantics:** duplicate business transaction hay duplicate event vào warehouse?
2. **Tìm SoR:** Payment ledger hay Warehouse transformation?
3. **Kiểm tra upstream:** nếu Payment SoR đúng, không sửa Payment chỉ để khớp report.
4. **Cô lập correction:** sửa ở tầng lỗi, theo API/correction workflow có audit.
5. **Đồng bộ lại consumers:** replay event, rebuild projection hoặc backfill dataset.
6. **Đối soát:** so sánh record counts, amounts, version và reporting periods.
7. **Ghi bằng chứng:** owner, approvals, correction event, timestamp, impacted datasets.

### 26.1. Không sửa bản sao để chữa triệu chứng

Nếu Order projection sai do thiếu event, một câu UPDATE trực tiếp vào Order DB theo “đúng dữ liệu Payment” có thể phá state machine hoặc bị event sau ghi đè. Cần đánh giá event replay/reconciliation hoặc domain command có kiểm soát.

### 26.2. Những ngoại lệ có chủ đích

Có thể có emergency break-glass correction cho dữ liệu production. Nhưng cần quyền phê duyệt, audit, backup/rollback, thỏa thuận với owner và kế hoạch sửa nguyên nhân. Break-glass không trở thành API ghi chuẩn.

## 27. Quản lý thay đổi schema và tác động consumer

Ví dụ Customer đổi trường email từ:

~~~json
{"email":"a@example.test"}
~~~

sang:

~~~json
{"primaryContact":{"type":"EMAIL","value":"a@example.test"}}
~~~

Nếu Order, Notification và Analytics đều đọc field cũ, đây là breaking change trừ khi contract hỗ trợ giai đoạn chuyển tiếp.

### 27.1. Expand–migrate–contract

1. **Expand:** producer hỗ trợ field cũ và field mới hoặc version mới.
2. **Migrate:** consumers được cập nhật, dữ liệu cần thiết backfill/reproject.
3. **Verify:** contract tests, telemetry, adoption metrics cho thấy consumer đã chuyển.
4. **Contract:** ngừng field/version cũ theo deprecation policy đã công bố.

Cần kiểm tra consumers chạy chậm, batch jobs theo tuần và mobile clients không nâng cấp ngay.

### 27.2. Change impact từ bản đồ

Khi thay `Customer.email`, truy các cạnh:

~~~text
Customer.email → Customer API
               → CustomerUpdated event
               → Notification projection
               → Support UI
               → Analytics warehouse
               → External CRM export
~~~

Mỗi cạnh có team, contract/version, data classification và SLA. Đây là lý do data map nên được version-control và đưa vào review của pull request/architecture decision.

### 27.3. Contract và ownership không đồng nghĩa consumer được veto mọi thay đổi

Owner có quyền quyết định semantics trong bounded context, nhưng phải cung cấp lộ trình tương thích đã thỏa thuận. Consumer cần tuân thủ contract và nâng cấp trong deprecation window; governance giải quyết xung đột về thời hạn và rủi ro.

## 28. Phối hợp RACI cho ownership và governance

RACI dùng:

- **R — Responsible:** trực tiếp thực hiện công việc.
- **A — Accountable:** chịu trách nhiệm cuối cùng và phê duyệt.
- **C — Consulted:** cần tham vấn.
- **I — Informed:** cần được thông báo.

Ví dụ cho Customer profile:

| Hoạt động | Customer Domain | Data Steward | Platform/DBA | Security/Privacy | Consumer Teams |
| --- | --- | --- | --- | --- | --- |
| Định nghĩa emailVerified | A/R | C | I | C | C |
| Thay API contract | A/R | C | I | C nếu nhạy cảm | C/I |
| Vận hành PostgreSQL | C | I | A/R | C | I |
| Phân loại PII | R | C | I | A | C |
| Chính sách retention | R | C | I | A cùng vai trò tuân thủ phù hợp | C |
| Sửa dữ liệu sai tại SoR | A/R | C | C | C khi cần | I |
| Backfill projection | C | C | C | C theo phân loại | A/R |
| Sự cố dữ liệu liên service | A theo root cause | C/R về định nghĩa chất lượng | R về hạ tầng nếu liên quan | C | R cho consumer impact |

Đây là mẫu minh họa; tổ chức cần quyết định chính xác một accountable owner cho từng quyết định cụ thể. **Tránh một hàng có nhiều “A” không rõ ai ký quyết định cuối**.

### 28.1. Ownership handoff

Khi service chuyển team, phải bàn giao:

- Data catalog/dictionary.
- API/event contracts và consumers.
- SLO, data quality checks, dashboards.
- Runbook correction/deletion/replay.
- Backups/restore và RTO/RPO.
- Secrets/IAM/access reviews.
- Những technical debts và ownership gaps chưa giải quyết.

### 28.2. Service owner nghỉ việc hoặc team giải thể

Không thể để critical dataset “orphaned”. Catalog nên có owner team và escalation contact ở cấp tổ chức, cùng quy trình chỉ định lại khi cơ cấu thay đổi.

## 29. Data catalog và metadata tự động

Một bản đồ quản trị có thể nằm trong một data catalog hoặc metadata repository, kết hợp:

- Danh mục domain và data assets.
- Owner/steward và contacts.
- API/event schema registry.
- Data lineage.
- Quality SLO và kiểm tra.
- Classification, policies và access requests.
- Change history và review timestamp.
- Links tới service catalog, runbooks, dashboards.

### 29.1. Nguồn metadata tự động

Có thể trích:

- OpenAPI/protobuf schemas.
- Kafka topic/schema registry.
- PostgreSQL information_schema và migrations.
- Warehouse table metadata.
- DAG từ Airflow/dbt hoặc công cụ ETL tương ứng.
- OpenTelemetry traces và client call metrics.
- IAM grants và service account usage.
- Git repository manifests/owners.

### 29.2. Không đồng nhất observed với authoritative

Tìm thấy Notification query trực tiếp Customer DB không chứng minh Notification **được phép sở hữu** Customer data. Nó có thể là coupling sai cần xử lý.

Tương tự, tracing không quan sát một cạnh có thể vì job chạy mỗi tháng hoặc sampling. Phải kết hợp **declared ownership**, **contract** và **runtime evidence**.

### 29.3. Metadata freshness

Một data asset được xác nhận lần cuối từ năm trước có thể không còn đúng. Cần review cadence theo mức rủi ro, tự cảnh báo khi schema/owner/consumers thay đổi và kiểm tra khi chuẩn bị migration.

## 30. Bản đồ dữ liệu cho analytics và BI

Microservices thường phát dữ liệu nghiệp vụ ra warehouse:

~~~text
Customer DB → CDC/Events ─┐
Order DB    → CDC/Events ─┼─► Data Ingestion → Raw → Curated → BI
Payment DB  → CDC/Events ─┤
Refund DB   → CDC/Events ─┘
~~~

Một số nguyên tắc:

1. Analytics có quyền sở hữu **transformation, quality và semantic layer** của tập dữ liệu curated.
2. Domain service vẫn là owner của dữ liệu nghiệp vụ gốc.
3. ETL phải ghi source table/topic, schema version, watermark và thời điểm dữ liệu.
4. Late-arriving events, duplicate, updates và deletes phải được xử lý theo contract.
5. Doanh thu cần rõ canceled/refunded/settled và cut-off timezone; không lấy mọi OrderCreated làm revenue.
6. Consumer có thể cần historical snapshots khác với profile hiện tại.
7. PII trong warehouse cần classification, purpose, access policy và retention riêng.
8. Dữ liệu ở BI report cũng phải có owner và lineage trở lại authoritative source.

### 30.1. Ví dụ data product

~~~yaml
dataProduct:
  id: finance.net_revenue_daily
  ownerTeam: finance-data
  inputs:
    - payments.captured_transactions.v2
    - refunds.settled_refunds.v1
  output:
    table: curated.net_revenue_daily
    grain: date_currency
  semantics:
    timezone: UTC
    revenueDefinitionRef: finance-net-revenue-policy
  quality:
    freshnessTargetHours: 4
    reconcileWithLedger: true
  classification: confidential
  documentationRef: finance-data-catalog
~~~

Đây là một **tập dữ liệu dẫn xuất có chủ sở hữu riêng**, không làm biến mất ownership của Payment/Refund dữ liệu gốc.

## 31. Bản đồ phục vụ migration và tách monolith

Khi tách Order từ monolith, một nguy cơ là hai hệ thống cùng ghi một bảng hoặc cùng được coi là nguồn sự thật.

### 31.1. Giai đoạn legacy shared DB

~~~text
Monolith ── writes ──► legacy.orders
Order Service ── reads/writes ? ──► legacy.orders
~~~

Dấu `?` là ownership gap cần giải quyết. Hai writers đồng thời thường gây lost updates, validation không thống nhất và khó rollback.

### 31.2. Chuyển trách nhiệm theo từng bước

Một lộ trình minh họa:

1. **Inventory:** liệt kê tất cả readers/writers và jobs với bảng orders.
2. **Define authority:** chọn điểm ghi chuẩn trong mỗi giai đoạn.
3. **Create owner API:** encapsulate thao tác ghi vào domain boundary.
4. **Shadow read/replication:** dựng projection từ nguồn cũ và so sánh kết quả.
5. **Cut over writes:** chỉ một authoritative writer tại một thời điểm, có kế hoạch rollback.
6. **Migrate reads:** consumers chuyển qua API/read model hoặc event.
7. **Retire direct DB access:** thu hồi grants, ngừng jobs phụ thuộc schema cũ.
8. **Reconcile:** kiểm tra counts, hashes, amounts, trạng thái nghiệp vụ.
9. **Update map:** source of truth, consumers, lineage, retention và runbook.

### 31.3. Dual-write nguy hiểm

Cho monolith và Order cùng ghi hai DB không có transaction chung có thể tạo divergence. Nếu cần dual-write tạm thời, phải có outbox/CDC, idempotency, reconciliation và cơ chế cutover có kiểm soát.

### 31.4. Strangler migration

Có thể chuyển từng operation sang Order Service theo route, giữ monolith xử lý phần còn lại. Data map cần ghi **operation ownership** ở từng giai đoạn, tránh trạng thái “service mới sở hữu Order” nhưng route update/refund vẫn ghi thẳng dữ liệu cũ.

## 32. Xử lý hệ thống nhiều tenant

Trong SaaS multi-tenant, một dataset có thể chứa tenantId, nhưng ownership còn bao gồm:

- Service nào xác minh tenant scope?
- Dữ liệu có bị trộn giữa tenants khi projection/ETL không?
- Tenant deletion/cancellation ảnh hưởng datasets nào?
- Encryption keys, retention và region có phân theo tenant?
- Analytics có được phép tổng hợp cross-tenant không?
- Backup/restore có thể khôi phục một tenant hay cả cluster?
- Ai có quyền hỗ trợ/impersonation và audit ra sao?

Một Customer Service có thể là SoR cho tất cả tenants về logic, nhưng data residency hoặc dedicated database per tenant tạo thêm phân chia vật lý. Bản đồ cần nêu cả hai.

### 32.1. ID không chứng minh quyền

Consumer có `customerId` không tự có quyền GET profile của customer đó. API owner phải thực hiện authorization theo caller/user/tenant và purpose, không dựa vào tính khó đoán của ID.

## 33. Data retention, backup và khả năng phục hồi

Bản đồ dữ liệu phải giúp trả lời:

- Bản gốc được backup theo lịch nào?
- Mục tiêu RPO/RTO?
- Snapshot hoặc event log có thể khôi phục tới mốc nào?
- Projection có thể rebuild từ event history không?
- Những events hoặc dữ liệu cần retention lâu hơn để replay?
- Kết quả restore có thể tạo duplicate side effect không?
- Có legal hold hoặc nghĩa vụ records không cho xóa?
- Khi xóa ở nguồn, backup hết hạn hoặc được xử lý theo policy nào?

### 33.1. Projection rebuild

Nếu Search index bị hỏng, có thể rebuild từ Catalog SoR hoặc event history được giữ đủ. Bản đồ nên ghi:

~~~text
Search index:
  authoritative source: Catalog Service
  rebuild method: Catalog bulk export + live events
  watermark: last-applied-catalog-version
  owner: search-team
  SLO: search-index-freshness
~~~

Không coi index là SoR chỉ vì rebuild đòi nhiều thời gian.

### 33.2. Restore làm dữ liệu lùi phiên bản

Nếu khôi phục Customer DB về snapshot cũ nhưng Notification projection đang ở version mới, hai nguồn có thể lệch. Cần quy trình reconcile từ source authoritative, không đơn giản phát lại mọi event mù quáng.

### 33.3. RPO/RTO phụ thuộc đường dữ liệu

Một Order API vẫn chạy sau AZ failure không đồng nghĩa Order data đã đạt RPO mong muốn. Nếu DB replication async, có thể mất giao dịch gần nhất. Data map cần gắn yêu cầu phục hồi với **từng authoritative dataset** và dependency.

## 34. Quan sát và phát hiện drift theo bản đồ

Các dashboard và cảnh báo có thể bao gồm:

| Nhóm | Metric / kiểm tra | Ý nghĩa |
| --- | --- | --- |
| SoR availability | Error ratio/latency cho write APIs | Owner có tiếp nhận thay đổi được không |
| Event delivery | Outbox age, publish failures | Dữ liệu đã commit có được phát không |
| Consumer processing | Lag, retry, DLQ, apply failures | Bản sao có bắt kịp không |
| Freshness | Last-applied version, update lag | Projection có stale quá mức không |
| Data quality | Validation violations, duplicates, missing records | Độ đúng của dữ liệu |
| Reconciliation | Mismatch counts/amounts | Hai tầng có sai lệch không |
| Contract | Schema registry errors, consumer parsing failures | Producer/consumer có không tương thích không |
| Privacy | Deletion completion, unauthorized access attempts | Chính sách bảo mật có thực thi không |
| Metadata | Assets không owner hoặc chưa review | Bản đồ quản trị có bị lỗi thời không |
| DR | Backup age, restore test status | Có bằng chứng phục hồi không |

### 34.1. Kiểm tra metadata orphan

Một data asset không có owner, không có retention hoặc không biết consumers là **governance risk**. Có thể đưa vào backlog với severity theo classification và criticality.

### 34.2. Kiểm tra runtime drift

Nếu system trace phát hiện Notification đang gọi trực tiếp Order DB ngoài contract, gắn cờ review: đó có thể là đường đọc mới chưa được khai báo hoặc truy cập trái chính sách.

### 34.3. Không lấy số metric làm bằng chứng nghiệp vụ

Outbox publish success=100% không chứng minh mọi consumer đã xử lý. Event consumed=100% không chứng minh projection đúng nếu consumer parse sai hoặc áp dụng stale data. Sử dụng kiểm tra end-to-end data correctness và reconciliation khi rủi ro cao.

## 35. Runbook: dữ liệu giữa hai service không khớp

Ví dụ Customer email hiện tại đã thay nhưng Notification vẫn dùng email cũ.

**Bước 1 — Xác nhận semantics:** hai giá trị có cùng ý nghĩa và cùng mốc thời gian không? Snapshot lịch sử có thể hợp lệ.

**Bước 2 — Tìm SoR:** Customer/Identity đang quyết định trường email nào? Business rule có yêu cầu verified email không?

**Bước 3 — Tìm lineage:** Customer DB → CustomerEmailChanged outbox → broker → Notification consumer → contact projection → Email Provider.

**Bước 4 — Kiểm tra nguồn:** record authoritative, aggregate version, occurredAt và audit trail.

**Bước 5 — Kiểm tra publish:** outbox chưa gửi, schema invalid, broker auth, topic không tồn tại, producer retries.

**Bước 6 — Kiểm tra consumer:** lag, DLQ, parse failure, idempotency/dedup, out-of-order, permission denied.

**Bước 7 — Kiểm tra projection:** update thành công chưa? Có cache stale hoặc query dùng nhầm key/tenant?

**Bước 8 — Chọn biện pháp:** replay event, rebuild projection, sửa mapping, rollback schema hoặc correction ở SoR theo bằng chứng.

**Bước 9 — Kiểm tra lại:** test cùng customer key đã được phép, projection version/freshness và user-facing behavior. Không in raw PII trong incident log.

**Bước 10 — Postmortem:** nguyên nhân, blast radius, khoảng lệch, những bản sao khác có nguy cơ, sửa contract/alert/runbook và owner thực hiện.

## 36. Runbook: yêu cầu xóa dữ liệu chưa hoàn tất

Một yêu cầu erasure có thể được phát từ privacy workflow và lan tới nhiều hệ thống.

1. **Xác thực phạm vi và căn cứ:** định danh, chính sách pháp lý/retention, ngoại lệ được cho phép.
2. **Liệt kê assets:** theo catalog/lineage, bao gồm search, analytics, cache, backup, exports và external processors.
3. **Phân tách dữ liệu:** trường phải xóa, phải ẩn danh, phải hạn chế xử lý và phải giữ theo nghĩa vụ.
4. **Thực hiện ở SoR:** domain APIs hoặc deletion workflow có audit.
5. **Phát yêu cầu downstream:** versioned event/command với idempotency key và deadline.
6. **Thu chứng cứ hoàn tất:** từng consumer phản hồi kết quả, exception, pending tasks.
7. **Xử lý DLQ/retry:** không bỏ qua consumer offline.
8. **Đối soát bản sao:** tránh raw PII còn trong search/cache/exports.
9. **Theo dõi backups:** áp dụng retention/expiry/restore controls đã được phê duyệt.
10. **Đóng yêu cầu:** chỉ khi policy điều kiện hoàn tất được đáp ứng hoặc ngoại lệ đã được phê duyệt.

**Không xem việc xóa một hàng trong Customer DB là đủ** nếu các bản sao downstream chưa xử lý, hoặc luật yêu cầu giữ một phần hồ sơ theo cách khác.

## 37. Runbook: contract thay đổi gây sự cố dữ liệu

Dấu hiệu:

- JSON deserialization errors tăng.
- DLQ và consumer lag tăng ngay sau deploy producer.
- Một field quan trọng bắt đầu null.
- BI report thiếu doanh thu dù nguồn có transactions.

Quy trình:

1. Xem producer/consumer contract versions và lịch deploy.
2. Tìm field semantics bị thay: type, nullability, enum, unit, timezone.
3. Khoanh những consumers dùng version bị ảnh hưởng.
4. Tạm dừng rollout/rollback hoặc chạy compatibility adapter theo chính sách.
5. Không replay event vô hạn vào consumer đang parse fail.
6. Triển khai fix contract và consumer với test xác nhận.
7. Reprocess event/DLQ với idempotency và version guards.
8. Backfill projections/reports bị sai hoặc thiếu.
9. Xác nhận record counts, business amounts và freshness SLO.
10. Cập nhật data map, schema registry rule và change-review checklist.

## 38. Ví dụ thiết kế một data map cho Checkout

### 38.1. Business flow

~~~text
CheckoutRequest
  │
  ▼
Order Service
  ├── Validate Customer reference
  ├── Reserve inventory in Inventory Service
  ├── Create Pending Order in Order DB
  ├── Authorize payment in Payment Service
  ├── Update Order state by domain policy
  └── Publish OrderStateChanged
            │
            ├──► Fulfillment read model
            ├──► Notification read model
            └──► Analytics warehouse
~~~

### 38.2. Bảng trách nhiệm chi tiết

| Thành phần dữ liệu | Authoritative owner | Trường bắt buộc | Contract | Consumer projection |
| --- | --- | --- | --- | --- |
| Order | Order | orderId, customerId, state, amount | Order API, OrderStateChanged | Fulfillment, Analytics |
| Reservation | Inventory | reservationId, sku, qty, expiry | Reserve API, ReservationUpdated | Order |
| Payment authorization | Payment | paymentId, amount, currency, status | Authorize API, PaymentAuthorized | Order, Finance |
| Customer identity | Customer/Identity | customerId, verified contact | Customer API/events | Notification |
| Product price at checkout | Order snapshot theo Pricing result | productId, price, tax | Pricing API → Order snapshot | Finance, Invoice |
| Shipment | Fulfillment | shipmentId, carrier, tracking, status | Shipment API/events | Order UI, Support |

### 38.3. Sai lệch có thể xảy ra

- Inventory đã reserve nhưng Order chưa ghi thành công.
- Payment đã authorize nhưng Order timeout trước response.
- Order tạo xong nhưng outbox publisher bị lỗi.
- Notification consumer nhận event trễ.
- Analytics tính doanh thu từ OrderCreated thay vì settled payment.
- Order snapshot và Catalog current price khác nhau đúng theo semantics.
- Customer xóa account nhưng Order phải giữ hồ sơ giao dịch ở mức được phép.

### 38.4. Cơ chế bảo vệ

- Domain owners kiểm soát write interfaces.
- Idempotency key xuyên retry.
- Saga/compensation cho quy trình nhiều service.
- Transactional outbox cho events.
- Contract tests cho API/event.
- Versioned projection + reconciliation.
- Audit trail cho correction và delete.
- Data catalog/lineage cập nhật khi schema hoặc owners thay đổi.

## 39. Ví dụ mã giả: chỉ owner được cập nhật dữ liệu gốc

Thiết kế Java/Spring Boot mức ứng dụng:

~~~java
public interface CustomerRepository {
    Customer findById(String customerId);
    void save(Customer customer);
}

public interface CustomerEventOutbox {
    void add(CustomerEvent event);
}

public final class ChangeCustomerContactService {
    private final CustomerRepository customers;
    private final CustomerEventOutbox outbox;

    public ChangeCustomerContactService(
            CustomerRepository customers,
            CustomerEventOutbox outbox) {
        this.customers = customers;
        this.outbox = outbox;
    }

    // Gọi trong một transaction do application adapter quản lý.
    public void changeEmail(
            String customerId,
            String verifiedEmail,
            String requestId) {
        Customer customer = customers.findById(customerId);
        customer.changeVerifiedEmail(verifiedEmail);
        customers.save(customer);
        outbox.add(new CustomerEmailChanged(
                customerId,
                customer.version(),
                requestId));
    }
}
~~~

`Customer` và `CustomerEmailChanged` là domain types minh họa. Đoạn code thể hiện **quyền sửa email gốc nằm trong Customer domain**. Muốn bảo đảm nguyên tử, repository save và outbox add phải nằm trong **cùng transaction thật** với persistence adapter phù hợp; một comment trong code không tự tạo transaction.

Notification Consumer có thể:

~~~java
public final class CustomerContactProjectionHandler {
    private final ContactProjectionRepository projection;

    public CustomerContactProjectionHandler(
            ContactProjectionRepository projection) {
        this.projection = projection;
    }

    public void on(CustomerEmailChanged event) {
        projection.applyIfNewer(
                event.customerId(),
                event.aggregateVersion(),
                event);
    }
}
~~~

`applyIfNewer` cần implementation atomic/idempotent với database thật để tránh race khi hai consumers xử lý các event cùng customer. Consumer chỉ cập nhật **projection của chính mình**, không sửa Customer authoritative record.

## 40. SQL dùng để nhận diện ownership kỹ thuật

Trong giai đoạn lập bản đồ, có thể xem DDL và DB grants để tìm ai có quyền trên schema. Ví dụ một hệ PostgreSQL có các truy vấn metadata phù hợp:

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
  AND table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name;
~~~

Truy vấn cột:

~~~sql
SELECT table_schema, table_name, column_name,
       data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'customer'
ORDER BY table_name, ordinal_position;
~~~

**Lưu ý:** PostgreSQL metadata phản ánh cấu trúc lưu trữ, không tự nói ai là business owner, ai đang sử dụng field hay retention policy nào. DB grants không bảo đảm ứng dụng thực sự dùng đúng quyền; phải đối chiếu code/config/runtime và owner xác nhận.

Khi quét metadata, tránh xuất dữ liệu production nhạy cảm hoặc sử dụng quyền vượt nhu cầu kiểm kê.

## 41. Testing của data ownership và data flow

### 41.1. Unit/domain tests

- Customer update email chỉ khi đã được xác minh.
- Order state transition hợp lệ.
- Payment amount/rounding policy đúng.
- Delete/correction theo lifecycle rules.

### 41.2. API contract tests

- Consumer gọi đúng endpoint, version, field.
- Provider đáp ứng contract.
- Authn/authz và tenant isolation.
- Validation và lỗi theo semantics.

### 41.3. Event schema tests

- Producer phát đúng version/payload.
- Consumer đọc event cũ và mới trong compatibility window.
- Unknown enum, nullable field và schema evolution.
- Duplicate/out-of-order, idempotency.

### 41.4. Integration tests

- DB transaction và outbox atomicity.
- Broker deliver/ack/retry/DLQ.
- CDC/ETL watermark và transform.
- Projection rebuild và reconciliation.

### 41.5. Data quality tests

- Unique keys, required fields, validity.
- Freshness/delay.
- Record counts và amount totals.
- Reference integrity và business invariants.
- Privacy deletion propagation.

### 41.6. Disaster recovery tests

- Restore SoR và rebuild projections.
- Reconcile event offsets sau restore.
- Không phát trùng side effects khi replay.
- RTO/RPO đạt mục tiêu.

**Không dùng mock để tuyên bố đã kiểm tra DB constraint/transaction thật.** Test phải chọn đúng boundary có khả năng phát hiện lỗi định kiểm tra.

## 42. Những anti-patterns thường gặp

**1. Nhiều service cùng ghi một trường authoritative.** Dễ lost update và không biết quyết định giá trị cuối thuộc ai.

**2. Database shared được xem là API nội bộ.** Consumer JOIN trực tiếp bảng service khác, làm deployment và migration phụ thuộc chéo.

**3. “Service nào giữ bản sao thì service đó sở hữu dữ liệu.”** Search, cache, Analytics thường là derived data.

**4. Không phân biệt snapshot lịch sử với giá trị hiện tại.** Order giá bán tại thời điểm giao dịch khác Catalog price hiện tại có thể là đúng.

**5. Data map chỉ có DB tables.** Bỏ qua API, event topics, cache, backups, logs, exports và external processors.

**6. Không có owner ở cấp field quan trọng.** Email verification, consent hoặc amount không có policy rõ.

**7. Consumer diễn giải enum/field theo suy đoán.** Schema hợp lệ nhưng semantics sai gây lỗi âm thầm.

**8. Phát raw PII trong mọi event.** Tăng số nơi lưu/khó xóa và rủi ro rò rỉ.

**9. Dùng event broker như database gốc mà không có quyết định event sourcing.** Không biết rebuild và retention.

**10. Xem publish success là mọi consumer đã cập nhật.** DLQ/lag có thể khiến projection stale.

**11. Không kiểm soát out-of-order/duplicate events.** Bản sao lùi về giá trị cũ hoặc side effects lặp.

**12. Dùng shared admin DB credential cho mọi service.** Không enforce ranh giới quyền ghi và khó audit.

**13. Không cập nhật map sau migration/deploy.** Sơ đồ đúng lúc thiết kế nhưng sai khi có incident.

**14. Không ghi transformation của báo cáo.** KPI sai nhưng không truy nguyên formula/nguồn.

**15. Xóa dữ liệu ở SoR và tuyên bố mọi nơi đã xóa.** Search/cache/warehouse/backup/processor còn bản sao.

**16. Tự sửa projection mà không sửa nguồn gây lệch.** Event tiếp theo có thể ghi đè, làm lỗi tái phát.

**17. Cho rằng một owner nghĩa là một team làm mọi việc.** Steward, service owner, custodians và consumers có trách nhiệm khác nhau.

**18. Chỉ nhìn service tracing để tìm data flow.** Batch/CDC/IdP/cache và cold paths có thể không hiện.

**19. Thay field trong một ngày không kiểm tra consumers cũ.** Batch jobs và mobile apps có thể vẫn dùng contract cũ.

**20. Không có quality/freshness SLO cho read model.** Projection sai/lỗi nhiều ngày mà HTTP API vẫn 200.

## 43. Bài tập thực hành

### Bài A — Chọn nguồn sự thật

Customer Service lưu địa chỉ mặc định hiện tại. Order Service lưu địa chỉ giao hàng của đơn đã đặt. User sửa địa chỉ mặc định sau khi đơn đã được giao cho đơn vị vận chuyển.

**Câu hỏi:** service nào được quyền thay đổi shipping address trên đơn?

**Gợi ý:** Customer sở hữu địa chỉ mặc định, Order/Fulfillment sở hữu địa chỉ theo workflow của đơn và shipment. Thay địa chỉ order phải qua contract nghiệp vụ của owner, không tự đồng bộ địa chỉ mặc định vào snapshot lịch sử.

### Bài B — Shared database coupling

Notification Service SELECT trực tiếp `customer_db.customers.email`, Customer đổi tên field và Notification lỗi ngay.

**Câu hỏi:** anti-pattern là gì và nên chuyển sang cơ chế nào?

**Gợi ý:** consumer đọc schema nội bộ không qua contract; chuyển sang API/ContactProjection qua event đã version, giới hạn quyền DB và dùng contract tests.

### Bài C — Projection bị chậm

Customer đã đổi email nhưng Notification vẫn dùng giá trị cũ. Outbox có event, broker consumer lag tăng.

**Câu hỏi:** owner nào cần xử lý ở bước đầu?

**Gợi ý:** dữ liệu gốc thuộc Customer; đường delivery/projection lag cần phối hợp Messaging/Notification owner. Điều tra chính xác điểm lỗi trước khi sửa trực tiếp SoR.

### Bài D — Schema thêm field

Catalog thêm field `manufacturerCountry` optional. Search consumer dùng parser strict và không chấp nhận unknown fields.

**Câu hỏi:** đây có thật sự là thay đổi backward-compatible không?

**Gợi ý:** không thể kết luận chỉ từ “field optional”; contract compatibility phụ thuộc cách consumer parse. Provider/consumer verification cần bao phủ trường hợp đó.

### Bài E — Số tiền bị lệch

Order phát `totalAmount: 100.50`, Finance diễn giải là VND còn Payment diễn giải là USD.

**Câu hỏi:** thiếu metadata gì?

**Gợi ý:** currency, unit, decimal precision/scale, rounding rules và semantics của amount. Contract phải xác định nhất quán và tests kiểm tra.

### Bài F — Quyền xóa

Privacy yêu cầu xóa customer; Customer DB đã xóa nhưng Search Index và Notification contact cache vẫn giữ PII.

**Câu hỏi:** cần sửa gì trong data map/workflow?

**Gợi ý:** khai báo mọi replica, retention và deletion consumers, có idempotent propagation, xác nhận completion, DLQ handling và policy cho backups.

### Bài G — Retry tạo bản ghi trùng

Order gọi Payment bị timeout; đã commit Payment nhưng client retry qua instance khác, tạo authorization thứ hai.

**Câu hỏi:** ownership giúp hiểu giải pháp như thế nào?

**Gợi ý:** Payment là owner của payment authorization; idempotency key/unique constraint phải được enforce tại Payment SoR. Order không tự sửa Payment DB mà reconcile qua Payment API.

### Bài H — Analytics khác dữ liệu sản xuất

Finance report ghi 1.200 doanh thu nhưng Payment ledger chỉ có 1.000 settled. Nguyên nhân có thể là report tính cả pending transactions.

**Câu hỏi:** phải truy ở đâu?

**Gợi ý:** dùng lineage từ report về curated dataset, transformation, Payment ledger và Refund/settlement semantics. Sửa definition/transform và backfill, không thay giao dịch thật để khớp report.

### Bài I — Ownership gap

Một topic `CustomerTierUpdated` được phát bởi legacy monolith và Customer Service trong giai đoạn migration.

**Câu hỏi:** cần quyết định gì?

**Gợi ý:** chọn authoritative writer theo thời kỳ, định nghĩa id/version/ordering, ngăn dual writers không kiểm soát, quy trình cutover và consumers biết nguồn đáng tin.

### Bài J — Data product

Marketing muốn dataset “khách có xu hướng mua lần hai” từ Orders, Catalog và Customer.

**Câu hỏi:** ai là owner?

**Gợi ý:** mỗi domain giữ quyền sở hữu dữ liệu gốc; team data product/Marketing Analytics sở hữu logic derived dataset, data quality, classification, purpose, privacy và lineage.

## 44. Checklist triển khai quản trị dữ liệu

### Ownership và kiến trúc

- [ ] Mỗi dữ liệu nghiệp vụ quan trọng có authoritative service/domain rõ ràng.
- [ ] Có business owner, technical owner và steward hoặc vai trò tương đương.
- [ ] Không có hai writers không được kiểm soát cho cùng authoritative state.
- [ ] Consumers được liệt kê và có purpose/contract.
- [ ] DB schema và quyền truy cập tuân thủ ranh giới sở hữu.
- [ ] Snapshot, projection, cache, warehouse được phân biệt với dữ liệu gốc.
- [ ] Bản đồ thể hiện region/AZ/tenant nếu ảnh hưởng tới quyền hoặc DR.

### Luồng và hợp đồng

- [ ] API/event/CDC/batch flows có hướng, version, owner và giao thức.
- [ ] Semantics field rõ về đơn vị, timezone, nullability, enum và state transitions.
- [ ] Producer/consumer contract verification cho thay đổi quan trọng.
- [ ] Outbox hoặc cơ chế publish reliability đã được thiết kế khi cần.
- [ ] Consumer idempotent và có policy out-of-order/duplicate.
- [ ] Freshness/lag target và runbook projection rebuild.
- [ ] Data lineage của critical KPIs và field nhạy cảm được ghi.

### Bảo mật và vòng đời

- [ ] Classification tại dataset và field nhạy cảm.
- [ ] IAM/least privilege, authn/authz và tenant isolation được kiểm tra.
- [ ] Event payload đáp ứng data minimization; không phát secret/PII tràn lan.
- [ ] Retention, delete/erase, pseudonymization và legal hold có policy.
- [ ] Logs, search indexes, caches, backups và exports nằm trong data map.
- [ ] Có audit trail cho correction, export và thay quyền.
- [ ] Data residency/external processors được ghi khi áp dụng.

### Chất lượng và vận hành

- [ ] Data quality rules cho accuracy/completeness/uniqueness/freshness.
- [ ] Reconciliation giữa SoR và derived datasets cho giá trị quan trọng.
- [ ] Dashboard outbox, consumer lag/DLQ, projection freshness.
- [ ] Runbook sửa dữ liệu không nhất quán và replay/backfill.
- [ ] Owner/escalation cho data incidents và ownership gaps.
- [ ] Backup/restore, RTO/RPO và projection rebuild được thử nghiệm.
- [ ] Metadata được review khi code/schema/ownership thay đổi.

## 45. Tóm tắt

Trong microservices, **dữ liệu có thể xuất hiện ở nhiều nơi nhưng quyền quyết định giá trị chuẩn phải rõ ràng**. Lập bản đồ dữ liệu và dịch vụ chịu trách nhiệm giúp tách ba điều thường bị nhầm:

1. **Ai sở hữu ý nghĩa và quyền ghi dữ liệu gốc?** — Data owner, bounded context, authoritative service.
2. **Dữ liệu được truyền, sao chép và biến đổi qua đâu?** — API/events/CDC/ETL, projections, caches và data lineage.
3. **Ai bảo vệ chất lượng, an toàn và vòng đời của dữ liệu?** — Service owner, steward, privacy/security, consumer responsibilities và data governance.

Một bản đồ hiệu quả có **thực thể/thuộc tính, SoR, readers/writers, contracts, storage locations, lineage, freshness, ownership và retention**. Nó được kiểm tra bằng code, runtime evidence và review khi thay đổi. Khi dữ liệu lệch, bản đồ giúp điều tra từ nguồn authoritative tới bản sao và chọn đúng vị trí correction; khi schema đổi hoặc có yêu cầu xóa, nó giúp tìm đầy đủ tác động xuôi dòng.

**Nguyên tắc ghi nhớ:** *một dữ liệu có thể có nhiều bản sao phục vụ nhiều nhu cầu; mỗi quyết định nghiệp vụ về giá trị chuẩn phải có trách nhiệm rõ ràng, và mọi bản sao phải biết nó đến từ đâu, cập nhật khi nào, được dùng vào việc gì và sẽ bị sửa/xóa ra sao.*
