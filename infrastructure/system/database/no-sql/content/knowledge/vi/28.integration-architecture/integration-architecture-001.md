# Xác định hệ giữ dữ liệu chuẩn và các kho dữ liệu dẫn xuất

## 1. Khi một khách hàng xuất hiện trong năm nơi, nơi nào nói sự thật?

Một nền tảng thương mại điện tử có:

- **MongoDB:** lưu hồ sơ khách hàng và đơn hàng.
- **Redis:** cache thông tin khách hàng để API trả nhanh.
- **Elasticsearch/OpenSearch:** tìm kiếm sản phẩm và đơn hàng.
- **DynamoDB:** trạng thái một số workflow và idempotency ledger.
- **Data warehouse:** báo cáo doanh thu theo ngày.
- **Ứng dụng di động:** giữ bản sao cục bộ khi mạng yếu.

Khách hàng đổi số điện thoại từ số cũ sang số mới. Ngay sau đó:

~~~text
MongoDB customer document:      NEW
Redis cached profile:           OLD
Search customer index:          OLD
Warehouse daily snapshot:       OLD
Mobile offline copy:            OLD
~~~

Vậy hệ nào đúng? Có nên xem nơi trả kết quả nhanh nhất là đúng? Có nên sửa Redis và search index trực tiếp để “đồng bộ” lại không? Nếu báo cáo hôm qua và MongoDB hôm nay khác nhau, đó là lỗi hay hệ quả hợp lệ của độ trễ?

Để tránh kiến trúc mất kiểm soát, cần xác định:

> **Hệ giữ dữ liệu chuẩn (authoritative system of record) có quyền quyết định trạng thái nào; những nơi còn lại chỉ là các biểu diễn dẫn xuất phục vụ truy vấn, tìm kiếm, cache, phân tích hoặc tích hợp.**

Đây là bài thuộc module **Database No SQL**, chương **Tích hợp và kiến trúc**. Không phải mọi dữ liệu phải nằm trong một database duy nhất; trọng tâm là **quyền sở hữu, nguồn phát sinh thay đổi, hợp đồng nhất quán và khả năng tái tạo dữ liệu dẫn xuất**.

### Mục tiêu học tập

1. Phân biệt **system of record**, **source of truth**, **authoritative owner**, **read model**, **materialized view**, **cache**, **index**, **projection** và **replica**.
2. Xác định dữ liệu chuẩn theo **thực thể, trường, command và bất biến nghiệp vụ** thay vì theo tên database.
3. Vẽ luồng nguồn chuẩn → thay đổi/sự kiện → các kho dẫn xuất, ngăn luồng ghi ngược vô chủ.
4. Chọn CQRS, CDC, transactional outbox, event sourcing hoặc batch ETL đúng mục đích.
5. Thiết kế version, ordering, idempotency và hội tụ khi sự kiện đến muộn/bị phát lại.
6. Xử lý rebuild, reconciliation, schema evolution, xóa dữ liệu và bảo mật.
7. Lập hợp đồng freshness, latency, durability và monitoring cho từng consumer.
8. Chuyển nguồn chuẩn mà không tạo hai nguồn ghi độc lập.
9. Liên hệ MongoDB, DynamoDB, Cassandra, Redis và Elasticsearch/OpenSearch.

## 2. Định nghĩa “dữ liệu chuẩn” một cách chính xác

### 2.1. System of record (SoR)

**System of record** là nơi hoặc hệ thống được giao trách nhiệm lưu giữ và quyết định bản ghi nghiệp vụ có thẩm quyền trong một phạm vi cụ thể.

~~~text
Customer Service / Customer DB
  authoritative for customer.profile

Order Service / Order DB
  authoritative for order state

Payment Service / Payment Ledger
  authoritative for payment settlement state
~~~

Đây là **ranh giới sở hữu**. Chúng có thể dùng những database khác nhau hoặc cùng nền tảng vật lý, nhưng cùng database không có nghĩa mọi service đều có quyền chỉnh mọi collection.

### 2.2. Source of truth

**Source of truth** thường được dùng rộng để chỉ nơi có giá trị đáng tin cậy cho một câu hỏi. Tuy nhiên, thuật ngữ này dễ mơ hồ.

Ví dụ:

- Giá sản phẩm niêm yết hiện hành có thể do **Pricing Service** quyết định.
- Tổng tiền đã cam kết của **một đơn hàng** có thể là **price snapshot** do Order Service giữ sau checkout.
- Số tiền đã capture thực tế có thể do **Payment Service/ledger** quyết định.

Không nên nói chung “Catalog là source of truth cho mọi giá” nếu đơn hàng lịch sử phải giữ giá đã chốt ở thời điểm mua.

### 2.3. Authoritative owner

**Owner** không chỉ là nơi chứa bản ghi. Owner chịu trách nhiệm:

- Kiểm tra ràng buộc nghiệp vụ.
- Phê duyệt hoặc từ chối commands thay đổi.
- Quy định giao thức ghi/transaction.
- Định nghĩa state, version, lịch sử.
- Phát hành sự kiện/CDC cho downstream.
- Phục hồi, retention và kiểm soát truy cập.

Redis cache chứa cùng dữ liệu profile không mặc nhiên là owner của profile.

### 2.4. Derived data store

**Kho dữ liệu dẫn xuất** chứa dữ liệu được tính, sao chép, biến đổi, tổng hợp hoặc lập chỉ mục từ nguồn có thẩm quyền.

~~~text
Customer DB
   |
   +--> Redis customer cache
   +--> Search customer index
   +--> Warehouse customer dimension
   +--> Mobile profile snapshot
~~~

Các kho này có thể cực kỳ quan trọng trong production, nhưng không vì thế được tùy ý ra quyết định sửa trạng thái gốc.

### 2.5. Canonical representation

**Biểu diễn chuẩn (canonical representation)** là schema và ý nghĩa do owner xác định: ID, đơn vị, thời gian, trạng thái, version, null/missing semantics.

Một API hoặc event contract có thể là **giao diện chuẩn** để consumer dùng, trong khi dữ liệu nằm ở nhiều tables hoặc shards bên dưới.

Không đánh đồng canonical schema với một bảng duy nhất chứa tất cả dữ liệu.

## 3. Ba điều thường bị nhầm là “nguồn dữ liệu chuẩn”

### 3.1. Replica không nhất thiết là nguồn độc lập

MongoDB secondary hoặc replica trong Cassandra có thể chứa cùng dữ liệu nguồn theo protocol replication. Đó là **bản sao trong cùng hệ sở hữu**, khác với một search index được tạo từ CDC để phục vụ truy vấn mới.

Replication có semantics write concern, consistency và failover; derived projection có thể có mapping, mất chi tiết, độ mới và rebuild contract riêng.

### 3.2. Cache trả nhanh không quyết định sự thật

Redis hiển thị stockAvailable=1 nhưng Inventory Service đã xác nhận chiếc cuối được đặt. Checkout không được tự dựa vào cache để bán thêm. Cache giúp **đọc nhanh**, không tự enforce ràng buộc bán hàng.

### 3.3. Warehouse có số liệu đúng nhưng không là kho lệnh

Kho phân tích có thể báo Revenue(day)=2,5 tỷ VND, đúng theo định nghĩa “chỉ tính giao dịch settled đến cuối ngày”. Điều đó không khiến warehouse trở thành nơi sửa trạng thái order hoặc hoàn tiền.

**Đúng theo định nghĩa phép đo** khác với **có quyền ra lệnh nghiệp vụ**.

## 4. Sở hữu dữ liệu phải được xác định theo phạm vi

Một hệ thường **không có một nguồn duy nhất cho mọi trường**. Ví dụ:

| Thực thể / dữ kiện | Owner có thẩm quyền | Nơi dẫn xuất | Ai được gửi lệnh thay đổi? |
|---|---|---|---|
| Customer.profile | Customer Service | Redis, search, warehouse | Customer Service qua API |
| Customer.emailVerified | Identity Service | Customer read model | Identity Service |
| Product.description | Catalog Service | Search, CDN, warehouse | Catalog Service |
| Product.currentPrice | Pricing Service | Catalog read model, Redis | Pricing Service |
| Order.totalAtCheckout | Order Service | Reporting, search | Order Service khi tạo đơn |
| Inventory.reservableQty | Inventory Service | Availability cache | Inventory Service |
| Payment.settlement | Payment/Ledger Service | Order projection, analytics | Payment Service |
| Search relevance score | Search subsystem | Search index | Search/ranking pipeline |
| Daily revenue KPI | Analytics pipeline theo định nghĩa KPI | Dashboard cache | Metric owner |

### 4.1. Một field có thể có hai ngữ nghĩa

Price có thể chỉ giá hiện tại, giá hội viên, giá đã chốt trong Order Line hay số tiền đã thanh toán sau khuyến mãi. Nếu lưu tất cả dưới tên price mà không quy định owner và thời điểm hiệu lực, tích hợp rất dễ sai.

### 4.2. Một thực thể có nhiều owner theo lát cắt

~~~text
Identity owns credentials and verification.
CRM owns marketing preferences.
Customer Service owns contact profile.
Compliance owns legal hold/deletion status.
~~~

Tuy nhiên, **mỗi business fact/invariant phải có authority rõ**. “Nhiều services cùng được quyền sửa một field theo ý mình” là anti-pattern.

### 4.3. Không dùng database name để thay định nghĩa

Mô tả mơ hồ:

> “DynamoDB là dữ liệu chuẩn, Redis là cache.”

Mô tả hữu ích hơn:

> “Order Service là authority cho vòng đời đơn hàng, lưu state trong bảng DynamoDB Orders. Redis chỉ cache OrderSummary với TTL minh họa 30 giây, có thể tái tạo từ Order API.”

Mô tả thứ hai nói rõ **ai quyết định, dữ liệu nào, API nào, độ mới và khả năng rebuild**.

### 4.4. Owner theo command

~~~text
ChangeCustomerContact -> Customer Service
VerifyEmail           -> Identity Service
ReserveStock          -> Inventory Service
SettlePayment         -> Payment Service
CreateSearchDocument  -> Search projection worker (derived only)
~~~

Consumer muốn thay đổi dữ liệu chuẩn phải gọi command của owner hoặc một protocol ủy quyền, không ghi thẳng vào projection rồi mong dữ liệu tự chạy ngược.

## 5. Sơ đồ kiến trúc một chiều: owner → projections

~~~mermaid
flowchart TD
    UI["Web / Mobile / Partners"] --> API["Business APIs / Commands"]
    API --> O["Authoritative Order Store"]
    O --> OUT["Outbox / CDC"]
    OUT --> BUS["Event transport"]
    BUS --> S["Search projection"]
    BUS --> C["Redis cache / invalidation"]
    BUS --> W["Warehouse / Analytics"]
    S --> Q["Search API"]
    C --> R["Fast read API"]
    W --> B["BI Dashboard"]
~~~

### 5.1. Luồng cập nhật chuẩn

~~~text
1. Client gửi ConfirmOrder(O101).
2. Order Service kiểm tra invariant và commit.
3. Change event được xuất bản an toàn.
4. Search index cập nhật document.
5. Redis cache bị invalidated/refreshed.
6. Analytics cập nhật projection doanh thu.
~~~

### 5.2. Luồng đọc tối ưu

~~~text
Search products -> Search index
View popular profile -> Redis cache
Order status requiring newest commit -> Order owner/strong read
Daily sales chart -> Warehouse projection
~~~

Không ép mọi GET đọc nguồn chuẩn nếu query có thể phục vụ từ projection với freshness contract phù hợp.

### 5.3. Luồng sai: projection ghi ngược tùy ý

~~~text
Search worker updates search document.
Another worker reads search document.
Worker writes inferred status directly into Order DB.
Order Service publishes another change.
Search worker updates search document again.
~~~

Vòng feedback có thể tạo **update loop**, overwrite field có thẩm quyền và lệch version. Nếu downstream phát hiện dữ liệu sai, gửi **correction request/command đến owner** với reason/evidence, không tự thay authority.

## 6. Các nhóm dữ liệu cần mô hình hóa riêng

### 6.1. Transactional canonical state

~~~text
Order status
Inventory reservation
Payment ledger
Username claim
~~~

Cần xác định command authority, transaction scope, concurrency control và durability.

### 6.2. Operational read model

Ví dụ OrderSummary:

~~~json
{
  "orderId": "O101",
  "customerName": "An",
  "itemCount": 3,
  "paymentStatus": "PAID",
  "shippingStatus": "PACKING"
}
~~~

Nó có thể tổng hợp từ Order, Customer, Payment và Fulfillment owners để API đọc một lần. Các trường có thể cập nhật vào những thời điểm khác nhau; read model cần mô tả freshness và tính nhất quán của tổ hợp.

### 6.3. Search index

Search chứa tokens, analyzers, denormalized fields và relevance score cho full-text/filter/sort. Không coi ranking score là nguồn chuẩn cho giá hoặc số lượng hàng hóa.

### 6.4. Analytics/warehouse

ETL/ELT có thể tổng hợp nhiều nguồn theo ngày, giữ lịch sử, snapshots, dimensions và facts. Warehouse phục vụ **định nghĩa KPI**, không trực tiếp enforce reservation.

## 7. Phân biệt nguồn chuẩn với replica, index và projection

| Loại | Được ghi bởi ai? | Chứa gì? | Rebuild? | Công dụng |
|---|---|---|---|---|
| Authoritative store | Owner command path | Business facts/invariants | Backup/event log nếu có | Transaction |
| Internal DB replica | Replication protocol | Bản sao cùng hệ | Catch-up/snapshot | HA/đọc |
| Cache | Cache writer | Bản sao ngắn hạn | Thường được | Đọc nhanh |
| Search index | Indexer/CDC | Tokens/denormalized docs | Thường được | Tìm kiếm |
| CQRS read model | Projector | View tối ưu query | Nên có kế hoạch | API đọc |
| Warehouse | ETL/stream analytics | Facts/dimensions/KPI | Tùy retention | BI |
| Authoritative event log | Domain command handler | Domain events bền vững | State có thể replay | Event sourcing |
| Mobile local copy | Client sync | Snapshot và pending changes | Tái đồng bộ | Offline |

### 7.1. Rebuildable không có nghĩa không quan trọng

Search index có thể xây lại nhưng nếu mất hai giờ rebuild, tìm kiếm cũng có thể gián đoạn hai giờ. Derived stores vẫn cần HA, SLO và runbook.

### 7.2. TTL không phải quyền sở hữu

TTL 60 giây chỉ nói cache có thể giữ bản sao bao lâu, không quy định ai được phép thay trạng thái chuẩn.

### 7.3. Index nội bộ khác external search

Index MongoDB thuộc cùng engine với collection; search index ngoài cập nhật qua CDC có propagation delay và rebuild contract khác. Cùng gọi “index” không có nghĩa cùng consistency.

## 8. Một dữ kiện có thể là snapshot chuẩn theo thời điểm

~~~text
Current product list price at Pricing: 120.000 VND
Order line price at checkout:         110.000 VND
Payment captured amount:             110.000 VND
~~~

Ba con số không mâu thuẫn nếu order áp dụng voucher và giá hiện tại đã đổi.

### 8.1. Snapshot nghiệp vụ khác stale cache

OrderLine.unitPriceAtCheckout là **business fact đã chốt**, không phải cache lỗi thời của Product.currentPrice.

### 8.2. Giữ provenance

~~~json
{
  "orderId": "O101",
  "productId": "P501",
  "unitPriceMinor": 110000,
  "currency": "VND",
  "pricingRuleVersion": "PR-23",
  "pricedAt": "2026-11-14T03:20:00Z"
}
~~~

Giữ currency, rule version và thời điểm giúp giải thích lịch sử giao dịch khi giá hiện tại đổi.

### 8.3. Tránh đồng bộ ngược snapshot

Giá Catalog tăng lên 120.000 không có nghĩa cập nhật mọi order lịch sử thành 120.000. Làm vậy có thể phá hóa đơn, hoàn tiền và đối soát.

## 9. Quyền ra quyết định phải gắn với bất biến

### 9.1. Username duy nhất

~~~text
Trong mỗi tenant, usernameCanonical chỉ được có một owner.
~~~

Search index eventual có thể trả not found cho username vừa tạo. Không dùng nó tự cấp username; dùng authority với atomic conditional claim.

### 9.2. Tồn kho

~~~text
Không xác nhận nhiều reservations hơn số stock được phép bán.
~~~

Cache và search có thể hiển thị số lượng ước lượng; ReserveStock phải đi qua Inventory owner.

### 9.3. Thanh toán

~~~text
Một payment intent không bị capture lặp ngoài chính sách.
~~~

Phải định nghĩa rõ Payment ledger, provider và Order status phụ thuộc nhau thế nào. Order projection không có quyền tự kết luận settled từ webhook chưa xác minh.

### 9.4. Dữ liệu hiển thị khác quyết định

UI hiển thị stock≈10 từ cache để duyệt nhanh, nhưng checkout cần xác nhận reservation tại nguồn chuẩn. Giá trị cached có thể cũ mà không khiến business rule sai nếu command path đúng.

## 10. Quy trình xác định hệ giữ dữ liệu chuẩn

1. **Liệt kê business facts:** ContactEmail, MarketingConsent, OrderStatus, OrderPriceSnapshot, ReservationOwner, CaptureStatus, SearchKeywords.
2. **Liệt kê commands:** ChangeContactEmail, ConfirmOrder, ReserveStock, CapturePayment.
3. **Chọn authority cho mỗi command/invariant:** Ai kiểm tra và commit?
4. **Liệt kê consumer và access pattern:** point lookup, full-text, dashboard, offline, batch.
5. **Gán representation dẫn xuất:** Redis, search index, CQRS view, warehouse, client snapshot.
6. **Định nghĩa propagation:** CDC, outbox, domain events, stream processing hoặc batch.
7. **Đặt hợp đồng freshness:** người dùng thấy bản cũ bao lâu, cách báo khi lag.
8. **Lập cách rebuild/reconcile:** snapshot, event log, cursor/checkpoint và tombstones.
9. **Kiểm soát access:** ai có quyền ghi source, ai chỉ có quyền ghi projection.
10. **Test failure modes:** duplicate events, out-of-order, delayed updates, partial outage.

Một ownership contract minh họa:

~~~text
Owner: Order Service
Canonical read API: GET /orders/{orderId}
Canonical write API: POST /orders/{orderId}/confirm
Derived index: order-search-v2
Target projection freshness: p99 under 10 seconds (example)
Rebuild source: Order snapshots + durable outbox/CDC
On lag: show delayed-data indicator, never infer order absence
~~~

Mốc 10 giây chỉ là ví dụ; hãy chọn và đo theo yêu cầu nghiệp vụ.

## 11. Vòng đời ghi đúng: command → commit → publish → project

### 11.1. Client gửi command

Ví dụ:

~~~json
{
  "operationId": "CONFIRM-O101",
  "orderId": "O101",
  "expectedVersion": 7,
  "action": "CONFIRM"
}
~~~

Client không ghi trực tiếp OrderSearchDocument. Nó yêu cầu Order Service thực hiện hành động có nghĩa nghiệp vụ.

### 11.2. Owner bảo vệ invariant

Order Service xác nhận:

- Người gửi có quyền.
- State hiện hành cho phép confirm.
- Expected version không stale.
- OperationId chưa được apply trước đó hoặc có thể replay kết quả.
- Transaction có thể commit trong phạm vi đúng.

Sau đó owner cập nhật canonical state và ghi một thay đổi có thể phát đi bền vững.

### 11.3. Derived consumers xử lý thay đổi

~~~text
Order version 8 committed
    |
    +--> SearchOrderProjector: update O101 to v8
    +--> Redis invalidator: invalidate OrderSummary O101
    +--> Warehouse consumer: update facts / aggregate
~~~

### 11.4. Publish success khác projection success

Order API có thể trả CONFIRMED sau source commit dù search index chưa nhận version 8. Nếu API hứa chỉ cần source commit, điều này hợp lệ.

Nếu API hứa “search visible immediately”, đó là hợp đồng khác, cần thiết kế đồng bộ hoặc đợi watermark.

### 11.5. Không để projection phát lại command tùy ý

Search projector không nên gửi ConfirmOrder lần nữa chỉ vì thấy version 7. Nó cần replay **event/projection update**, không replay business command.

## 12. Vì sao dual write từ ứng dụng dễ làm mất dữ liệu?

Một cách viết ngây thơ:

~~~text
1. Update Order DB.
2. Update Search Index.
~~~

Nếu bước 1 thành công, bước 2 thất bại:

~~~text
Order DB: v8 CONFIRMED
Search:   v7 DRAFT
~~~

Nếu đảo thứ tự rồi bước 2 thất bại:

~~~text
Search:   v8 CONFIRMED
Order DB: v7 DRAFT
~~~

### 12.1. Hai lời gọi không tạo một transaction

Hai API writes tới hai hệ khác nhau không có atomicity chỉ vì được gọi liên tiếp trong một method Java.

### 12.2. Retry có thể làm lệch thứ tự

~~~text
t1 Search update v8 bị timeout nhưng thực ra commit.
t2 Search update v9 thành công.
t3 Retry v8 đến muộn, overwrite v9.
~~~

Nếu indexer không kiểm tra version, projection có thể **đi lùi** dù source chỉ tiến lên.

### 12.3. Hợp đồng tốt hơn

Commit ở owner trước, rồi truyền changes qua kênh có thể retry/replay và idempotent consumer. Không cần giả vờ có transaction xuyên mọi kho khi chỉ yêu cầu eventual projection.

### 12.4. Ngoại lệ cần protocol rõ

Trong migration hoặc những hệ hỗ trợ distributed transaction thật, dual-write pattern có thể xuất hiện, nhưng phải có nguồn thẩm quyền, ordering, idempotency và reconciliation. Không xem nó là lựa chọn mặc định.

## 13. Transactional outbox: gắn state và ý định phát sự kiện

### 13.1. Vấn đề khi publish sau commit

~~~text
1. Commit Order v8 thành công.
2. Process crash trước khi publish OrderConfirmed.
~~~

Nếu không có bản ghi bền vững để phát lại, search/warehouse có thể không bao giờ nhận v8.

### 13.2. Transactional outbox

Trong cùng transaction được database hỗ trợ:

~~~text
TRANSACTION:
    update Order O101 from v7 to v8
    insert OutboxEvent EVT-O101-8
COMMIT
~~~

Publisher đọc outbox rồi chuyển event đến broker. Nếu publisher chết trước ACK, nó có thể phát lại; consumers cần idempotency.

~~~mermaid
flowchart TD
    A["Order command"] --> T["Atomic source transaction"]
    T --> O["Order v8"]
    T --> X["Outbox EVT-O101-8"]
    X --> P["Outbox publisher"]
    P --> B["Broker / Stream"]
    B --> S["Search projector"]
    B --> W["Warehouse projector"]
    B --> C["Cache invalidator"]
~~~

### 13.3. Atomicity là điều kiện quan trọng

Nếu Order lưu Database A và outbox lưu Database B với hai calls độc lập, ta **không có transactional outbox nguyên tử**. Phải lưu trong transaction boundary phù hợp hoặc capture commit log/CDC đúng protocol.

### 13.4. Publisher có thể gửi trùng

~~~text
Publish EVT-O101-8 thành công.
Process crash trước published checkpoint.
Restart -> publish EVT-O101-8 lần nữa.
~~~

Consumer cần xử lý duplicate eventId hoặc entityVersion, không increment bừa mỗi lần nhận.

### 13.5. Outbox không thay business authority

Outbox ghi nhận **thay đổi đã commit**, không trở thành hệ quyết định Order. Consumer search lỗi không được sửa source Order chỉ để điều chỉnh index.

## 14. CDC: quan sát commit log thay vì hai lần ghi

**Change Data Capture (CDC)** đọc các thay đổi từ source database qua log/change stream/cơ chế hỗ trợ và chuyển tới consumers.

~~~text
Canonical source
   |
   v
Committed changes / change log
   |
   v
CDC connector
   |
   v
Event stream
   |
   +--> Search
   +--> Cache
   +--> Analytics
~~~

### 14.1. Lợi ích

- Tránh application dual write.
- Thu thập insert/update/delete.
- Có resume checkpoint/token theo engine.
- Tích hợp source legacy chưa có domain events.

### 14.2. CDC khác domain event

CDC có thể nói:

~~~text
Orders.status changed from DRAFT to CONFIRMED.
~~~

Domain event có thể nói:

~~~text
OrderConfirmed(orderId=O101, businessVersion=8).
~~~

Thay đổi cấp storage khác với **sự thật nghiệp vụ**. Không mặc định mọi sửa field status do admin maintenance đều là nghiệp vụ xác nhận đơn.

### 14.3. Delete/tombstone quan trọng

Nếu CDC bỏ qua delete, search có thể giữ item đã xóa mãi. Delete phải được truyền và apply ngay cả khi source record không còn.

### 14.4. Snapshot rồi stream

Khi tạo projection mới với hàng triệu records:

~~~text
1. Lấy snapshot source ở watermark W.
2. Build projection từ snapshot.
3. Replay changes sau W.
4. Khi consumer bắt kịp, chuyển traffic.
~~~

Nếu snapshot và stream không có watermark/handshake rõ, sẽ có nguy cơ bỏ sót thay đổi xảy ra trong lúc scan.

### 14.5. Retention cần đủ cho recovery

Source giữ change stream chỉ 24 giờ nhưng projector offline 3 ngày có thể không resume từ checkpoint. Cần backfill/resnapshot hoặc log retention phù hợp.

## 15. Event schema là contract

Một event mẫu:

~~~json
{
  "eventId": "EVT-O101-8",
  "eventType": "OrderConfirmed",
  "schemaVersion": 2,
  "aggregateType": "Order",
  "aggregateId": "O101",
  "aggregateVersion": 8,
  "occurredAt": "2026-11-14T03:20:00Z",
  "tenantId": "T17",
  "data": {
    "customerId": "U17",
    "status": "CONFIRMED",
    "totalMinor": 110000,
    "currency": "VND"
  }
}
~~~

### 15.1. Các ID/version

| Trường | Ý nghĩa |
|---|---|
| eventId | Dedupe bản tin bị phát nhiều lần |
| aggregateId | Định danh thực thể và routing key |
| aggregateVersion | Thứ tự thay đổi của thực thể |
| schemaVersion | Phiên bản cấu trúc event |
| occurredAt | Thời gian theo contract |
| tenantId | Phạm vi sở hữu và quyền |
| data | Payload đã được chuẩn hóa |

**Schema version không thay aggregate version.** Một event có schemaVersion=2 vẫn có thể là version 9 của Order.

### 15.2. Đơn vị và chuẩn hóa

Tiền dùng đơn vị nhỏ nhất có currency; thời gian có UTC/timezone; số lượng có unit. Tránh amount=100 không rõ là đồng, cent hay đơn vị khác.

### 15.3. Data minimization

Events nội bộ cũng có thể chứa field nhạy cảm. Không chuyển toàn bộ customer document vào broker dùng chung nếu consumer chỉ cần customerId và displayName.

### 15.4. Schema evolution

Thêm optional field thường dễ hơn xóa/đổi nghĩa một field. Đổi tên, thay type, đổi null/missing hoặc đơn vị tiền cần migration/versioning và compatibility plan.

### 15.5. Các dạng event

- **Event notification:** Có ID/version, consumer đọc source khi cần.
- **Event-carried state:** Mang snapshot fields đủ để projection.
- **Domain fact:** Có ý nghĩa nghiệp vụ, như PaymentCaptured.

Chọn theo độ trễ, coupling, retention, volume và privacy.

## 16. Ordering: projection không được quay ngược

Source xử lý:

~~~text
Order O101 v7 = DRAFT
Order O101 v8 = CONFIRMED
Order O101 v9 = CANCELLED
~~~

Do network/parallel consumers, search nhận v9 trước v8. Nếu projector overwrite theo thứ tự nhận:

~~~text
Search after v9: CANCELLED
Search after v8: CONFIRMED   <-- sai
~~~

### 16.1. Version-aware apply

~~~text
onEvent(event):
    current = projection.get(event.aggregateId)

    if event.aggregateVersion <= current.aggregateVersion:
        skip duplicate/stale event

    if event is full state snapshot:
        apply with atomic version condition
    else if event requires exact sequence:
        require event.aggregateVersion == current.aggregateVersion + 1
        otherwise wait for missing events or rebuild
~~~

Nếu event là delta “increase quantity by 3”, bỏ version 8 rồi apply version 9 có thể thiếu một phần. Không coi mọi event mới nhất là đủ để phục hồi.

### 16.2. Partition key ổn định

Stream partition theo aggregateId có thể giữ thứ tự cho cùng aggregate trong phạm vi broker/producer contract. Vẫn cần xử lý replay, generation và late events.

### 16.3. Timestamp không là version tổng quát

Clock skew giữa producers khiến event đến sau có timestamp nhỏ hơn. Không dùng last-write-wins chỉ theo wall clock để quyết định business state cần thứ tự có thẩm quyền.

### 16.4. Multi-entity projection

OrderSummary ghép Order v8, Payment v5, Shipping v3. Không có một aggregateVersion chung nếu nguồn độc lập.

~~~json
{
  "orderId": "O101",
  "sourceVersions": {
    "order": 8,
    "payment": 5,
    "shipping": 3
  }
}
~~~

Lưu vector giúp minh bạch version, nhưng **không tự tạo atomic snapshot xuyên ba nguồn**.

## 17. Idempotency: xử lý at-least-once delivery

Một broker/CDC có thể giao lại:

~~~text
EVT-O101-8
EVT-O101-8
EVT-O101-8
~~~

### 17.1. Idempotent upsert

Với event mang toàn bộ trạng thái version 8, projector có thể conditional upsert nếu incomingVersion lớn hơn storedVersion. Replay version 8 không đổi kết quả.

### 17.2. Delta cần dedup

Nếu event là RevenueIncreasedBy(110000), áp dụng ba lần sẽ cộng ba lần. Cần inbox/dedupe eventId, transaction giữa marker và aggregate update, hoặc tính lại từ facts.

### 17.3. Check rồi ghi không nguyên tử

~~~text
A checks eventId absent
B checks eventId absent
A updates revenue
B updates revenue
~~~

Hai workers có thể tạo duplicate effect. Dedupe marker và effect cần transaction/conditional scope thực.

### 17.4. Timeout sau commit

Projector ghi search thành công nhưng response mất. Khi retry, version/eventId phải ngăn việc tạo nhiều records hoặc ghi đè bản mới.

### 17.5. Exactly once phải có phạm vi

Broker có tính năng exactly-once không tự làm payment gateway hoặc email provider trở thành exactly-once end-to-end. Mỗi ranh giới side effect cần idempotency/reconciliation.

## 18. CQRS: tách command model khỏi query model

**CQRS (Command Query Responsibility Segregation)** tách đường command có quyền quyết định khỏi query model tối ưu đọc.

~~~mermaid
flowchart TD
    Client --> CommandAPI["Command API"]
    CommandAPI --> WriteDB["Authoritative write model"]
    WriteDB --> Stream["Outbox / Change stream"]
    Stream --> Projector
    Projector --> ReadDB["Denormalized read model"]
    Client --> QueryAPI["Query API"]
    QueryAPI --> ReadDB
~~~

### 18.1. Lợi ích

- Write model ưu tiên invariant/transaction.
- Read model ưu tiên query, sort/filter/search.
- Chọn storage phù hợp từng đường.
- Scale read khác write.

### 18.2. Đánh đổi

- Eventual lag giữa write và read.
- Phải rebuild/catch up.
- Event contract/versioning phức tạp hơn.
- Thêm vận hành broker/indexer.
- Test end-to-end khó hơn một database.

### 18.3. Không phải dự án nào cũng cần CQRS vật lý

Ứng dụng nhỏ có thể dùng một MongoDB collection và index cho cả đọc/ghi. Tách write store/search store chỉ vì xu hướng kiến trúc có thể tạo chi phí lớn hơn giá trị.

### 18.4. Query không được sửa source tùy ý

Nếu Query API cần chỉnh sửa, nó chuyển thành command tới owner. Không chỉnh search document rồi mong source cập nhật.

## 19. Event sourcing: khi sự kiện là nguồn chuẩn

Trong **event sourcing**, nguồn có thẩm quyền cho một aggregate có thể là dãy domain events bất biến có thứ tự:

~~~text
OrderCreated(O101)
ItemAdded(O101,P501,2)
OrderConfirmed(O101)
OrderCancelled(O101)
~~~

State hiện hành được dựng bằng apply events theo thứ tự và logic aggregate.

### 19.1. Event log chuẩn khác CDC log

- **Authoritative event store:** Domain events là mô hình persistence chính.
- **CDC log:** Ghi nhận thay đổi đã commit trong source khác.
- **Message broker:** Vận chuyển events; không tự là log lưu đủ lâu để rebuild.

Nếu event store là canonical, phải bảo đảm retention, ordering, version, snapshot và disaster recovery.

### 19.2. Snapshot là dẫn xuất, nhưng phục vụ nhanh

~~~text
Authoritative Event Log -> CurrentOrderState snapshot
~~~

Snapshot giúp không replay hàng triệu events cho mỗi GET. Không xóa events mà bỏ qua retention, regulatory needs và khả năng khôi phục.

### 19.3. Command khác event

~~~text
Command: CancelOrder(O101)    (có thể bị từ chối)
Event:   OrderCancelled(O101) (sự thật đã xảy ra)
~~~

Không phát OrderCancelled trước khi owner quyết định hủy; nếu commit command thất bại, event phát sớm đã nói sai.

### 19.4. Replay không được kích hoạt external effects

Replay events để rebuild search không được tự động gửi lại email, capture payment hay gọi hệ ngoài. Phải phân biệt **pure projection handler** và process manager có side effects.

## 20. MongoDB là nguồn chuẩn, Elasticsearch là search projection

Giả sử Product Service sở hữu collection Products:

~~~json
{
  "_id": "P501",
  "tenantId": "T17",
  "title": "Bàn phím cơ",
  "description": "Bàn phím với switch ...",
  "priceMinor": 1200000,
  "currency": "VND",
  "version": 18,
  "deleted": false
}
~~~

### 20.1. Lệnh sửa sản phẩm

Mọi sửa title, description và giá thuộc quyền sở hữu của các domain owners tương ứng. Nếu giả định Product Service là owner của cả ba trường trong ví dụ đơn giản, đường ghi:

~~~text
Admin -> Product Service -> MongoDB Product
                                  |
                                  v
                              Change stream
                                  |
                                  v
                         Search indexer -> Search document
~~~

### 20.2. Source và projection có schema khác

Source document chứa các fields phục vụ domain invariants. Search index có thể chứa:

~~~json
{
  "productId": "P501",
  "title": "Bàn phím cơ",
  "searchTokens": ["ban", "phim", "co"],
  "priceMinor": 1200000,
  "isSearchable": true,
  "sourceVersion": 18
}
~~~

Search tokens, analyzers hoặc ranking fields là sản phẩm của search pipeline, không bắt buộc lưu trong Product canonical document.

### 20.3. MongoDB change stream

Một application có thể subscribe changes ở collection/database/cluster tùy scope được hỗ trợ, dùng resume token và quy tắc resume của MongoDB.

Nhưng:

- Resume token chỉ có ích khi lịch sử thay đổi vẫn được giữ/khả dụng.
- Delete phải được xử lý.
- Update event có thể không mang đủ full document tùy cấu hình.
- Một source snapshot/backfill cần liên kết chính xác với stream nếu muốn không mất thay đổi.

### 20.4. Không để search index là nơi sửa giá

Nếu admin chỉnh giá qua Search API mà Product Service không nhận command, hai nơi có thể lệch. Search document chỉ là dẫn xuất; sửa giá phải qua authority, sau đó indexing pipeline cập nhật lại index.

### 20.5. Query tìm kiếm khác xác nhận tồn kho

Search có thể trả sản phẩm P501 đang khả dụng dựa trên snapshot. Khi checkout, Inventory owner vẫn phải xác nhận stock/reservation. Search result không là quyết định đặt hàng.

### 20.6. Reindex với alias

Khi thay analyzer/schema index:

~~~text
products-v1 (serving)
products-v2 (building)
~~~

Tạo v2 từ source snapshot và replay changes đến watermark đủ mới; đối soát count/version/sample queries; sau đó chuyển read alias theo cơ chế search engine.

Không xóa v1 ngay trước khi xác minh v2 đã đủ dữ liệu và rollback window.

## 21. DynamoDB là authoritative store, Redis là cache

Một service quản lý workflow:

~~~text
PK = ORDER#O101
status = CONFIRMED
version = 8
~~~

### 21.1. Ghi qua conditional update

Pseudocode của Order Service:

~~~text
Update order O101
SET status=CONFIRMED, version=8
IF version=7 AND status=DRAFT
~~~

Ứng dụng không sửa Redis trước rồi coi thay đổi đã được xác nhận. Command phải commit tại DynamoDB theo semantics đã chọn.

### 21.2. DynamoDB Streams

Stream có thể cung cấp dữ liệu thay đổi cho consumers theo cấu hình phù hợp, dùng để invalidation/update projection.

### 21.3. Cache-aside

~~~text
GET order summary:
    try Redis
    if miss:
        query Order owner via API
        cache result with appropriate version/TTL
~~~

Đường đọc này thích hợp nếu API cho phép stale theo policy.

### 21.4. Race invalidate và repopulate

~~~text
t1 Reader miss cache, đọc source v7.
t2 Writer commit source v8, invalidate cache.
t3 Reader set cache v7 sau invalidate.
~~~

TTL không ngăn cache bị đặt lại phiên bản cũ. Giải pháp có thể dùng version-aware cache CAS, token/generation, write-through protocol có thứ tự hoặc chấp nhận stale tối đa rõ ràng.

### 21.5. Strong read chỉ ở nơi được hỗ trợ

Không tự suy query GSI của DynamoDB sẽ thấy write mới nhất. GSI có eventual read semantics; nếu cần xác nhận order phiên bản mới nhất, đọc nguồn/đường API bảo đảm phù hợp.

### 21.6. Multi-Region

Nếu dùng Global Tables chế độ eventual, concurrent writes các Region có conflict semantics riêng. Phải xác định **authority cho business fact toàn cầu**, không tự xem bản nào đến sau là đúng nếu inventory/username cần một winner.

## 22. Cassandra/ScyllaDB và bảng truy vấn dẫn xuất

Trong wide-column NoSQL, một dữ kiện thường được biểu diễn ở nhiều bảng để phục vụ access patterns:

~~~text
orders_by_id
orders_by_customer
orders_by_day
~~~

### 22.1. Không phải mỗi bảng đều là owner

Giả sử Order Service có quyền quyết định Order O101. Bảng orders_by_customer và orders_by_day có thể là query tables/projections, dù cùng nằm trong Cassandra cluster.

**Cùng engine vật lý không làm mọi bản sao thành nguồn độc lập.**

### 22.2. Ví dụ schema giản lược

~~~sql
CREATE TABLE orders_by_id (
  tenant_id text,
  order_id text,
  customer_id text,
  status text,
  total_minor bigint,
  version bigint,
  PRIMARY KEY ((tenant_id, order_id))
);

CREATE TABLE orders_by_customer (
  tenant_id text,
  customer_id text,
  created_at timestamp,
  order_id text,
  status text,
  total_minor bigint,
  source_version bigint,
  PRIMARY KEY ((tenant_id, customer_id), created_at, order_id)
);
~~~

### 22.3. Hai writes thường không tự atomic

Nếu ứng dụng ghi orders_by_id thành công rồi bị lỗi trước khi ghi orders_by_customer, read model sẽ trễ/lệch.

Không suy từ việc cùng Cassandra cluster rằng một batch nhiều partitions tạo transaction ACID giống một relational database. Cần phân biệt batch atomicity, logged batch, isolation và LWT semantics trong phạm vi phù hợp.

### 22.4. Một nguồn quyết định và repair

Chọn authoritative state hoặc event store/command layer, rồi có cơ chế phát thay đổi/rebuild query tables. Nếu projection bị hỏng có thể đối soát lại từ nguồn có thẩm quyền.

### 22.5. Cassandra LWT không biến mọi projection thành serializable

Một conditional mutation cho unique claim trong một partition không tự đồng bộ orders_by_customer hay analytics table. Ranh giới transaction và idempotency vẫn quan trọng.

## 23. Redis: cache, queue, counter hay nguồn chuẩn?

Redis thường dùng làm cache, nhưng không phải mọi dữ liệu trong Redis luôn là derived.

### 23.1. Redis như cache

~~~text
Customer DB authoritative -> Redis customer:U101
~~~

Giá trị có thể hết TTL rồi tái tạo từ source.

### 23.2. Redis như nguồn của trạng thái tạm thời

Một application có thể quyết định rằng Redis giữ một state có thẩm quyền trong phạm vi cụ thể, ví dụ admission-control bucket hoặc session tạm thời, **nếu durability, failover, eviction và consistency contract thực sự đáp ứng yêu cầu**.

Không mặc định Redis là cache hoặc source; hãy phân loại từng key/namespace.

### 23.3. Counter trong Redis

Nếu Redis lưu viewCount nhưng event log mới là nguồn dữ liệu có thể replay, Redis counter là projection.

Nếu không có nguồn nào khác có thể tái tạo count sau mất Redis, nó trên thực tế đang là một loại authoritative state, bất kể tài liệu gọi nó là cache. Kiến trúc phải nhìn nhận rủi ro durability.

### 23.4. Redis Streams

Một stream có thể là bộ đệm/vận chuyển events, nhưng không tự đủ điều kiện làm authoritative event store cho lịch sử nhiều năm nếu retention, persistence, replication, consumer state và recovery không được đảm bảo.

### 23.5. Cấm cache quyết định nghiệp vụ mà không có source

Nếu API Checkout đọc Inventory từ Redis và ghi thành công ngay mà không kiểm tra nguồn có thẩm quyền, outage/cache stale có thể khiến oversell. Điều đó là lỗi thiết kế authority, không đơn thuần lỗi TTL.

## 24. Elasticsearch/OpenSearch là read model cho search, không là database tổng quát mặc định

### 24.1. Tối ưu search

Index có thể flatten/denormalize:

~~~json
{
  "orderId": "O101",
  "customerName": "An",
  "productTitles": ["Bàn phím cơ"],
  "status": "CONFIRMED",
  "sourceVersion": 8
}
~~~

Nó giúp search nhanh theo text và filter, nhưng customerName cũng có thể là snapshot của Customer owner chứ không phải field Order trực tiếp sở hữu.

### 24.2. Refresh latency

Write source vừa commit không có nghĩa search document được nhìn thấy ngay; indexing/refresh/replica và CDC đều có độ trễ.

### 24.3. Quy tắc version update

Nếu v9 đến trước v8, indexer phải bảo đảm v8 không overwrite v9. Có thể dùng conditional version control hoặc logic project state phù hợp với cách lập chỉ mục.

### 24.4. Index aliases và rebuild

Giữ index v1 cho người dùng, xây v2 ở nền; catch up stream, đối soát, đổi alias; sau đó cleanup v1 theo kế hoạch. Tránh downtime hoặc index nửa chừng.

### 24.5. Search là source of truth cho relevance score?

Search engine có thể là hệ có thẩm quyền cho **ranking output** theo index/analyzer/model version tại thời điểm truy vấn, nhưng không là source cho giá sản phẩm hay payment settlement.

**Quyền sở hữu phải xét theo loại sự thật**, không gán nhãn “toàn bộ Elasticsearch là dẫn xuất” cho mọi use case một cách máy móc.

## 25. Cross-service read model: một document, nhiều nguồn

Một API Dashboard muốn trả:

~~~json
{
  "orderId": "O101",
  "status": "CONFIRMED",
  "paymentStatus": "CAPTURED",
  "shippingStatus": "IN_TRANSIT",
  "customerName": "An"
}
~~~

Nguồn:

~~~text
Order Service       -> status
Payment Service     -> paymentStatus
Shipping Service    -> shippingStatus
Customer Service    -> customerName
~~~

### 25.1. Read model tổng hợp không trở thành owner của tất cả field

Document có thể chứa nhiều field được ghép, nhưng các commands thay đổi payment, shipping, profile vẫn thuộc từng owner.

### 25.2. Một view có thể tạm không đồng bộ

~~~text
Order version 8: CONFIRMED
Payment version 5: CAPTURED
Shipping version 2: LABEL_CREATED
~~~

Ngay lúc PaymentCaptured event đến, Shipping projection chưa chắc đã bắt kịp. Đây có thể là trạng thái trung gian hợp lệ nếu UI trình bày đúng.

### 25.3. Không suy một field khác từ field đã đến

Search projector không nên tự chuyển shippingStatus sang SHIPPED khi thấy paymentStatus=CAPTURED, trừ khi business rule có thẩm quyền và event/command protocol cho phép.

### 25.4. Version vector và provenance

Lưu:

~~~json
{
  "orderId": "O101",
  "sourceVersions": {
    "order": 8,
    "payment": 5,
    "shipping": 2,
    "customer": 12
  },
  "projectedAt": "2026-11-14T03:25:00Z"
}
~~~

Giúp xác định consumer nào bị lag; không tự cung cấp atomic snapshot xuyên các services.

### 25.5. Thời gian và version cần ngữ nghĩa rõ

projectedAt là thời gian worker cập nhật, không phải thời gian dữ liệu được business owner commit. Dùng source commit position/version để đo **freshness của dữ liệu có thẩm quyền**.

## 26. Client offline là một kho dẫn xuất đặc biệt

### 26.1. Mobile cache

Ứng dụng di động có thể lưu:

~~~text
Customer profile v12
Order history snapshot
Pending edits
~~~

Khi offline, người dùng sửa địa chỉ:

~~~text
LOCAL pending command ChangeAddress(...)
~~~

**Pending command không phải canonical change** cho tới khi owner xác nhận.

### 26.2. Sync khi reconnect

~~~text
Client reconnects
 -> sends operationId + expectedVersion
 -> owner accepts/rejects/returns conflict
 -> client updates local projection
~~~

### 26.3. Conflict resolution

Nếu server profile đã v13 còn client sửa dựa trên v12, cần rule merge/optimistic concurrency. Last-write-wins theo điện thoại đặt giờ sai có thể mất thay đổi.

### 26.4. Local-first ngoại lệ

Một số ứng dụng cộng tác có thể dùng CRDT/multi-writer model, cho phép nhiều thiết bị đóng góp sự thật qua merge protocol. Khi đó authority là **protocol và tập các actors được phép**, không phải một DB primary duy nhất.

Không ép mô hình single-writer vào mọi ứng dụng; hãy ghi rõ consistency, conflict resolution và owner permissions.

## 27. Java: mô hình source command và event projectors

Một cấu trúc Java khái niệm:

~~~java
import java.time.Instant;

public record OrderConfirmedEvent(
        String eventId,
        String tenantId,
        String orderId,
        long aggregateVersion,
        Instant occurredAt,
        long totalMinor,
        String currency
) {}

public record ConfirmOrderCommand(
        String operationId,
        String tenantId,
        String orderId,
        long expectedVersion
) {}
~~~

### 27.1. Owner thực hiện command

~~~java
public interface OrderCommandService {
    // Implementation phải kiểm tra invariant và lưu event
    // cùng canonical change trong transaction thích hợp.
    void confirm(ConfirmOrderCommand command);
}
~~~

### 27.2. Projector chỉ ghi kho dẫn xuất

~~~java
public interface OrderSearchProjection {
    void upsertIfNewer(OrderConfirmedEvent event);
}
~~~

Một implementation ví dụ:

~~~java
public final class OrderSearchProjector {
    private final OrderSearchProjection index;

    public OrderSearchProjector(OrderSearchProjection index) {
        this.index = index;
    }

    public void onEvent(OrderConfirmedEvent event) {
        index.upsertIfNewer(event);
    }
}
~~~

### 27.3. Điều kiện upsert phải nguyên tử

Pseudocode:

~~~text
upsertIfNewer(event):
    ATOMICALLY:
        storedVersion = index.getVersion(event.orderId)
        if event.aggregateVersion <= storedVersion:
            return ALREADY_APPLIED
        index.replace(event.orderId, toSearchDocument(event))
    return APPLIED
~~~

Nếu getVersion và replace là hai requests tách biệt, workers A và B có thể race. Phải dùng API version control/atomic update của destination hoặc một cơ chế serialize theo aggregate phù hợp.

### 27.4. Với delta event

Nếu event chỉ nói ItemAdded(quantity=2), việc upsert từ event đơn lẻ không đủ dựng toàn bộ Order document; projector phải áp dụng đúng thứ tự hoặc fetch canonical snapshot.

### 27.5. Không đặt business command trong projector

Projection handler không gọi payment capture hay CancelOrder khi replay, trừ khi nó là một process manager được thiết kế riêng với idempotency và trách nhiệm nghiệp vụ rõ.

## 28. Rebuild projection: dữ liệu dẫn xuất phải có đường phục hồi

### 28.1. Vì sao rebuild là một tính năng kiến trúc?

Search index bị xóa nhầm, đổi analyzer, cache schema thay đổi hoặc warehouse job có bug. Nếu projection thực sự là dẫn xuất, hệ cần trả lời:

> Từ dữ liệu chuẩn và lịch sử thay đổi nào, bằng quy trình gì, ta dựng lại projection đầy đủ và đưa nó vào phục vụ mà không mất những cập nhật trong lúc rebuild?

Nếu không có câu trả lời, projection có thể đã trở thành **nguồn duy nhất của một phần dữ liệu**, trái với sơ đồ kiến trúc mong muốn.

### 28.2. Rebuild bằng snapshot + change stream

Một quy trình:

~~~text
t0 Capture consistent source snapshot at watermark W.
t1 Start/retain CDC consumption from W.
t2 Build products-index-v2 from snapshot.
t3 Apply events after W to v2.
t4 Wait until v2 caught up to required watermark.
t5 Validate coverage, versions and representative queries.
t6 Atomically switch read alias to v2.
t7 Keep v1 for rollback window.
t8 Cleanup v1 after verification.
~~~

Một số engines không hỗ trợ snapshot toàn hệ tại một instant; cần protocol phối hợp watermark, per-partition offsets hoặc cách quét/catch-up phù hợp.

### 28.3. Đánh số generation

~~~text
Projection generation=7 (old)
Projection generation=8 (building)
~~~

Thêm generation giúp tách dữ liệu v1/v2 và tránh một worker dùng schema cũ ghi vào index mới.

### 28.4. Rebuild không được kích hoạt side effects

Event replay để dựng lại search/warehouse không được gửi lại SMS, email hoặc charge. Các handlers cần phân loại:

- Pure projections có thể replay.
- Process manager có side effect cần workflow riêng.

### 28.5. Nếu source thiếu lịch sử?

Nếu source chỉ giữ **state hiện tại** và không giữ lịch sử giá cũ, warehouse không thể tự tái tạo mọi historical revenue/snapshot chỉ bằng cách quét current state.

Muốn rebuild lịch sử phải có authoritative historical facts, event log, backups hoặc retention hợp lý. Không quảng bá “mọi projection có thể rebuild” khi thông tin gốc đã mất.

### 28.6. Dữ liệu tombstone

Nếu snapshot cũ có record P101, sau đó record bị xóa, projector v2 phải nhận delete/tombstone. Nếu chỉ replay upserts, P101 có thể hồi sinh trong index.

## 29. Reconciliation: so sánh nguồn chuẩn với các projection

### 29.1. Event pipeline không miễn lỗi

Ngay cả khi publisher/consumer có retries, vẫn có thể gặp:

- Bug mapper bỏ qua field.
- Event bị drop do retention.
- Worker skip một message lỗi.
- Indexer dùng schema sai.
- Consumer áp dụng out-of-order.
- Dữ liệu cũ tồn tại trong projection sau khi source đã xóa.

Do đó cần **đối soát độc lập** chứ không chỉ tin consumer lag=0.

### 29.2. Đối soát theo key/version

Một batch kiểm tra:

~~~text
For each canonical key K:
    canonical = owner.get(K)
    projected = search.get(K)
    compare business fields and sourceVersion
~~~

Không so sánh các search-only fields như analyzer tokens với source fields không tồn tại.

### 29.3. Checksum

Một hệ lớn có thể tính checksum theo bucket/range từ canonical representation:

~~~text
Bucket 0:
    source count=10,000
    projection count=10,000
    source hash=H1
    projection hash=H1
~~~

Count bằng nhau **chưa đủ**; hai tập khác nhau có thể có cùng count. Hash/checksum nên dùng quy tắc canonicalization, ordering và field selection nhất quán.

### 29.4. Reconciliation phải có watermark

Nếu source ở version mới hơn projection theo freshness contract, so sánh tức thời có thể thấy mismatch hợp lệ.

Ví dụ:

~~~text
Source committed watermark: W105
Search applied watermark:   W100
~~~

Không kết luận mọi entry từ W101..W105 là lỗi dữ liệu trước khi hết cửa sổ cho phép. Nhưng nếu W100 không tiến trong 30 phút, đó là dấu hiệu lag.

### 29.5. Repair có thẩm quyền

Nếu search document lỗi:

~~~text
Read canonical state -> reproject -> upsert search
~~~

Nếu canonical state lỗi, không lấy search document eventual làm bằng chứng duy nhất rồi viết ngược source. Cần domain correction command/audit.

### 29.6. Tự động hóa repair có giới hạn

Repair hàng loạt không được tạo retry storm hoặc xóa đúng dữ liệu vì comparator sai. Nên có dry run, sampling, rate limits và audit trail.

## 30. Freshness: biểu diễn “đúng nhưng trễ” một cách đo được

### 30.1. Các loại độ trễ

~~~text
Source commit time
   |
   v
CDC captured
   |
   v
Event published
   |
   v
Consumer applied
   |
   v
Search refreshed / data visible to user
~~~

Đừng chỉ đo consumer ACK time nếu search vẫn chưa refresh và người dùng chưa đọc được document.

### 30.2. Freshness lag

Một thước đo:

\[
\text{ProjectionLagSeconds}
=\text{observed visible time}-\text{source commit time}.
\]

Khi consumer không có dữ liệu mới, cần dùng watermark/heartbeat phù hợp để đo lag; chỉ đo thời gian từ event cuối cùng có thể cho số liệu lạc quan.

### 30.3. SLO ví dụ

~~~text
Search product updates:
  99% visible within 15 seconds under normal conditions.

Order confirmation:
  canonical write ACK after source commit.

Payment settlement:
  status endpoint reads authoritative Payment state.

Warehouse:
  previous UTC day's report ready by 06:00 UTC.
~~~

Các SLO minh họa khác nhau bởi **business impact**, không dùng chung một mốc cho mọi projection.

### 30.4. Trả kèm data as-of

Một dashboard có thể hiển thị:

~~~json
{
  "revenueMinor": 250000000,
  "currency": "VND",
  "dataAsOf": "2026-11-14T02:00:00Z",
  "isPartial": false
}
~~~

Thời điểm dataAsOf phải có ý nghĩa thực: event-time watermark, snapshot cutoff hoặc thời điểm nguồn đã được xử lý đủ; không đơn thuần là lúc UI render.

### 30.5. User-facing stale indicators

Nếu index lag:

~~~text
Kết quả tìm kiếm có thể chưa gồm các thay đổi vài phút gần đây.
~~~

Minh bạch hơn việc âm thầm hiển thị một order không tồn tại rồi kết luận chưa thanh toán.

## 31. Đọc nhiều nguồn: đồng bộ gọi API hay precompute?

### 31.1. API composition đồng bộ

Một OrderSummary endpoint gọi bốn services:

~~~text
Order
Payment
Shipping
Customer
~~~

Ưu điểm:

- Gần trạng thái nguồn nếu mỗi API đủ mới.
- Không cần projection bền vững.

Nhược điểm:

- Fan-out network.
- Latency đuôi phụ thuộc slowest dependency.
- Partial failure phức tạp.
- Không tự có snapshot nguyên tử giữa các cuộc gọi.

### 31.2. Materialized read model

Projector cập nhật một document từ events của bốn services. Read path rất nhanh và chịu lỗi nguồn tạm thời tốt hơn, nhưng dữ liệu có thể trễ và cần rebuild.

### 31.3. Chọn theo yêu cầu

| Yêu cầu | Hướng cân nhắc |
|---|---|
| Bảng danh sách 100 orders nhanh | Materialized OrderSummary |
| Xác nhận thanh toán vừa xảy ra | Authoritative Payment API |
| Trang danh mục sản phẩm | Search/cache |
| Báo cáo cuối ngày | Warehouse |
| Xem hồ sơ vừa sửa | Session/strong source read hoặc version-aware cache |
| Dashboard nhiều domains | Projection có source versions và lag |

### 31.4. Hybrid

Một API có thể phục vụ đa số từ read model, nhưng với vài trường business-critical (ví dụ payment status) truy vấn authoritative owner khi người dùng thực hiện hành động nhạy cảm.

### 31.5. Không gọi tất cả nguồn vô hạn

API composition cần deadlines, bounded concurrency, timeouts và partial result semantics. Chỉ vì đó là read path không nghĩa có thể fan-out 100 services trong mỗi request.

## 32. Quyền sở hữu trong Saga và workflows nhiều bước

Một order workflow:

~~~text
OrderCreated
 -> ReserveInventory
 -> CapturePayment
 -> ArrangeShipment
~~~

Không một service nhất thiết sở hữu toàn bộ trạng thái nghiệp vụ của những service khác.

### 32.1. Saga orchestrator là owner của workflow state

Orchestrator có thể giữ:

~~~text
OrderCheckoutWorkflow O101:
  inventoryReservationId=R501
  paymentIntentId=P901
  workflowStatus=PAYMENT_PENDING
~~~

Nó là source of truth cho **tiến độ workflow/orchestration**, nhưng không tự thay Inventory owner cho số lượng hàng hoặc Payment owner cho settlement.

### 32.2. Commands và events

~~~text
Orchestrator -> ReserveStock command
Inventory -> StockReserved event
Orchestrator -> CapturePayment command
Payment -> PaymentCaptured event
~~~

Phải có correlation/causation IDs, operation IDs, retry và terminal failure handling.

### 32.3. Compensation không là rollback ACID

Nếu PaymentCaptured nhưng giao hàng thất bại, một refund có thể là **command bù trừ mới**, có audit/latency/side effects riêng. Không xóa record PaymentCaptured rồi nói chưa từng thanh toán.

### 32.4. Read model của Saga

OrderSummary có thể hiển thị:

~~~text
checkoutStatus=PROCESSING
paymentStatus=CAPTURED
shippingStatus=PENDING
~~~

Nó phải phản ánh những domain facts đã có, không tự đoán mọi bước hoàn tất vì một cờ boolean tổng hợp.

## 33. Xóa, ẩn danh và dữ liệu nhạy cảm trong nhiều kho

### 33.1. Xóa ở source chưa xóa ở projection

~~~text
Customer Service deletes/erases profile.
Search still holds customerName.
Redis cache still holds old profile.
Warehouse dimension still holds email.
Mobile offline copy remains.
~~~

Một lệnh xóa đúng ở nguồn có thể chưa đáp ứng yêu cầu xóa dữ liệu trên toàn hệ.

### 33.2. Delete propagation

Lập danh sách recipients của dữ liệu nhạy cảm:

- Source canonical store.
- Read replicas/backups theo policy.
- Redis/CDN caches.
- Search indexes.
- Warehouse/lake.
- Event logs/queues.
- Exports và mobile/offline copies nếu kiểm soát được.

Mỗi nơi cần retention, deletion/anonymization và audit contract.

### 33.3. Tombstones và generation

Một delete event có thể mang:

~~~json
{
  "eventType": "CustomerErased",
  "customerId": "U101",
  "aggregateVersion": 37,
  "eraseGeneration": 5
}
~~~

Nếu consumer sau đó nhận một update cũ version 36, nó không được hồi sinh dữ liệu đã xóa.

### 33.4. Rebuild có thể hồi sinh dữ liệu cũ

Nếu rebuild search từ snapshot trước delete mà không replay tombstone hoặc áp dụng erasure manifest, dữ liệu đã xóa có thể xuất hiện lại.

Không thiết kế erase như chỉ một DELETE rồi bỏ qua rebuild/replay.

### 33.5. Legal hold và policy ngoại lệ

Một số hệ có nghĩa vụ retention pháp lý đối với transactions, trong khi dữ liệu cá nhân phải được giảm thiểu hoặc ẩn danh theo chính sách. Không tự xóa toàn bộ payment ledger chỉ vì một yêu cầu chung; cần policy và owner pháp lý rõ.

### 33.6. Data minimization

Projection chỉ nên chứa những fields cần dùng; giảm số kho lưu PII giúp giảm bề mặt xóa, rủi ro truy cập và chi phí compliance.

### 33.7. Authorization của read models

Search index có thể gom dữ liệu nhiều tenant. Query API vẫn phải áp tenant scope/authorization; một client không được truyền tenantId bất kỳ rồi đọc document của tenant khác.

## 34. Data lineage và catalog sở hữu

Một bảng metadata nội bộ:

| Data product | Owner | Upstream | Downstream | Contract | Rebuild |
|---|---|---|---|---|---|
| Orders canonical | Order Service | Commands | Order events | Order schema v3 | Backups + recovery |
| Orders search | Search team | Orders/outbox | Search API | Projection v2 | Snapshot + events |
| Orders cache | API team | Order API | GET endpoints | TTL/version | Cache refill |
| Revenue facts | Analytics | Orders + Payments | BI | KPI definition | Historical events |
| Customer profile | Customer Service | Customer commands | Cache/search | Customer v4 | Backup/event history |

### 34.1. Cần nhiều thông tin hơn tên nguồn

Catalog có thể ghi:

- Data owner và on-call team.
- Canonical identifier.
- Event/API schema version.
- Freshness SLO.
- Allowed consumers, PII classification.
- Retention và delete propagation.
- Backfill/rebuild instructions.
- Recovery point/watermark.
- Những business invariants được bảo vệ ở đâu.

### 34.2. Tránh “shadow integration”

Một nhóm đọc thẳng bảng của service khác rồi tự duy trì bản sao không được tài liệu hóa sẽ tạo coupling và rủi ro khi source schema đổi.

Ưu tiên public API/data contract/event đã được owner công bố; nếu buộc phải đọc trực tiếp, cần contract, permission và trách nhiệm rõ.

### 34.3. Schema registry không là data authority

Registry quản lý schema/compatibility; nó không quyết định business fact nào đúng. Schema hợp lệ không chứng minh một PaymentCaptured event là sự thật nếu producer chưa được xác minh.

### 34.4. Data contract có thể kiểm thử

Những ràng buộc:

~~~text
aggregateId not null
aggregateVersion monotonically increases per aggregate
currency always provided with amountMinor
eventId globally unique within producer namespace
delete events contain enough key/version metadata
~~~

Consumer có thể validate để tránh âm thầm đưa dữ liệu sai vào projection.

## 35. Chuyển hệ giữ dữ liệu chuẩn: migration authority

Giả sử Customer Service muốn chuyển source từ MongoDB sang DynamoDB.

### 35.1. Nguy cơ hai nguồn cùng nhận write

~~~text
Old MongoDB accepts update email=A.
New DynamoDB accepts update email=B.
Both report success.
~~~

Nếu không có cùng một quyền quyết định hoặc conflict protocol, ta tạo **split authority**. Đồng bộ eventual không bảo đảm business fact nào thắng đúng.

### 35.2. Lộ trình expand–migrate–cutover

Một phương án:

~~~text
1. Define canonical API and data contract.
2. Prepare DynamoDB schema and projection.
3. Snapshot/backfill from MongoDB at watermark W.
4. Stream/replay MongoDB changes after W into DynamoDB.
5. Shadow reads / compare results, do not change authority yet.
6. Fence old writers and cut over one authoritative write path.
7. Route new commands to new owner/backend.
8. Keep reconciliation and rollback protocol for an agreed window.
9. Retire old source write permissions after validation.
~~~

### 35.3. Shadow reads

Đọc mới và cũ song song để so kết quả:

~~~text
Production response: Old source result.
Shadow response: New candidate result.
Compare versions/fields/latency.
~~~

Shadow read không được gây mutation. Nếu hai kết quả khác nhau do replication lag trong cửa sổ cho phép, đối soát theo watermark trước khi báo mismatch.

### 35.4. Cutover cần fencing

Nếu process cũ còn giữ connection tới MongoDB, sau cutover nó không được tiếp tục commit các commands đã chuyển authority sang DynamoDB. Có thể dùng owner epoch, permission revocation, routing switch và giao thức đảm bảo không còn old writer hợp lệ.

### 35.5. Rollback khó hơn đổi route

Nếu sau cutover DynamoDB nhận writes mới, rollback về MongoDB cần replay thay đổi mới hoặc cơ chế authoritative recovery; không chỉ sửa DNS/API route về backend cũ.

### 35.6. Migration schema khác migration owner

Có thể đổi internal database nhưng **Customer Service vẫn là authority**; đó là chuyển backend lưu trữ. Cũng có thể chuyển quyền sở hữu email verification từ Customer Service sang Identity Service; đây là **thay bounded context/domain ownership** và cần cập nhật commands/events/ACL khác.

## 36. Failure modes của kiến trúc nguồn chuẩn và dẫn xuất

### 36.1. Source commit thành công, publisher thất bại

~~~text
Order canonical state = v8
Outbox event still pending
Search = v7
~~~

Đây là tình huống cần retry publisher/backlog; không rollback source chỉ vì search chưa nhận nếu contract không yêu cầu đồng bộ.

### 36.2. Publisher gửi trùng

~~~text
EVT-O101-8 delivered twice
~~~

Consumer cần idempotent update. Hai lần giao không có nghĩa hai lần xác nhận Order.

### 36.3. Event đến sai thứ tự

~~~text
Index receives v9 then v8
~~~

Version-aware apply ngăn v8 ghi đè v9; delta events cần phát hiện khoảng trống.

### 36.4. Search mất toàn bộ index

Nếu source và history đủ, chạy rebuild v2 từ snapshot/events rồi cutover alias. Trong thời gian rebuild, có thể dùng fallback source query cho một số chức năng nhưng không hứa full-text như cũ nếu source không hỗ trợ.

### 36.5. Source outage, cache còn hoạt động

Read cache có thể phục vụ stale theo contract; commands cần authoritative quyết định có thể tạm unavailable. Không cho cache tự cấp inventory chỉ để giữ tỷ lệ HTTP success.

### 36.6. Projection có bug nhưng event lag=0

Consumer vẫn báo đã xử lý mọi messages, song mapper bỏ field totalMinor hoặc hiểu currency sai. Cần reconciliation nội dung và contract tests, không chỉ đo lag.

### 36.7. Consumer bị mất retention window

Nếu CDC token quá cũ, resume thất bại. Không nhảy thẳng tới latest để báo healthy khi mất hàng nghìn mutations. Chuyển sang repair/resnapshot với checkpoint mới có căn cứ.

### 36.8. Delete sau snapshot nhưng trước cutover

Nếu rebuild bỏ tombstone của user đã xóa, search index mới sẽ hồi sinh user. Cutover phải xác nhận erase propagation và event watermark.

### 36.9. Multi-owner field race

CRM và Customer Service cùng sửa phone trong hai stores khác nhau. Một sync job last-write-wins có thể ghi đè thay đổi hợp lệ. Giải pháp gốc là phân quyền owner hoặc conflict resolution có hợp đồng, không tăng tần suất sync.

### 36.10. Schema evolution làm sai projection

Producer đổi totalMinor thành totalDecimal trong event mới; consumer cũ vẫn đọc totalMinor mặc định 0. Pipeline có thể báo success nhưng warehouse giảm doanh thu sai. Cần compatibility tests, versioned consumers và cảnh báo dữ liệu bất thường.

## 37. Metric cho từng thành phần

| Thành phần | Metric / tín hiệu | Ý nghĩa |
|---|---|---|
| Source command | Success/reject/timeout, p99, conditional conflicts | Nguồn có thẩm quyền còn xử lý đúng không |
| Source storage | Durability, replica/quorum health, capacity | Rủi ro mất dữ liệu/availability |
| Outbox | Pending count, oldest pending age, publish retries | Event đã commit nhưng chưa phát |
| CDC | Capture lag, expired token, checkpoint age | Có bị trễ/mất cửa sổ replay không |
| Broker | Consumer lag per partition, DLQ count | Downstream đã bắt kịp chưa |
| Search projector | Applied version, failures, indexing lag, refresh lag | Dữ liệu có thể tìm thấy chưa |
| Cache | Hit rate, stale hit, invalidation lag, eviction | Đọc cũ bao lâu |
| Warehouse | Event-time watermark, load completion, correction count | KPI đã đủ dữ liệu tới mốc nào |
| Reconciliation | Mismatch count/percentage, repair backlog | Dữ liệu dẫn xuất có đúng không |
| Rebuild | Snapshot completion, replay lag, coverage | Index mới có sẵn sàng cutover không |
| Privacy | Erasure pending, last deletion age, failed deletes | Dữ liệu nhạy cảm còn ở đâu |
| User journey | Incorrect status reports, missing search results, stale-visible duration | Tác động thực lên người dùng |

### 37.1. Tách độ trễ theo tầng

~~~text
Source commit -> outbox publish
Outbox publish -> consumer receive
Consumer receive -> index commit
Index commit -> search visible
~~~

Nếu search chậm, biết chính xác tầng nào gây lag tốt hơn nhìn một metric end-to-end duy nhất.

### 37.2. Watermark theo partition

Một consumer có 16 stream partitions. 15 partitions đã tới W1000 nhưng partition 7 mới tới W500. Một metric trung bình có thể che shard lag lớn.

Watermark toàn projection phải được định nghĩa cẩn thận, ví dụ minimum progress theo những partitions liên quan, không tự lấy max checkpoint rồi nói mọi data đã cập nhật.

### 37.3. SLO theo business criticality

Search gợi ý có thể cho phép trễ vài giây, Payment status cần chặt hơn. Không dùng một freshness SLO chung cho toàn hệ chỉ vì dễ cấu hình dashboard.

### 37.4. Alert theo data correctness

Thêm alert:

~~~text
source/projection mismatch over threshold
delete not propagated by policy deadline
unrecoverable event gap
rebuild v2 behind cutoff watermark
payment projection showing terminal state inconsistent with ledger
~~~

### 37.5. Không lộ PII trong telemetry

Không đưa email/raw phone/credentials vào high-cardinality labels hoặc log tự do. Dùng identifiers đã được phân quyền, hashing/anonymization phù hợp và retention hợp lý.

## 38. Câu hỏi cần hỏi khi hai hệ báo dữ liệu khác nhau

Một cuộc điều tra tốt không bắt đầu bằng “đồng bộ cả hai theo bản mới nhất”. Hãy hỏi:

1. Hai hệ đang mô tả **cùng business fact** hay hai snapshots theo thời điểm khác nhau?
2. Authority cho fact đó là service và command nào?
3. Source commit ở version/watermark bao nhiêu?
4. Projection applied tới mốc nào?
5. Độ trễ có nằm trong SLO cho phép không?
6. Có event thiếu, trùng, đến muộn hoặc đảo thứ tự không?
7. Projection có transform fields đúng contract không?
8. Có delete/tombstone hoặc policy erasure không?
9. Có một service ngoài quyền đã ghi trực tiếp vào projection/source không?
10. Repair phải đi từ source sang projection, hay cần domain correction command?

Ví dụ:

~~~text
Canonical Order v10: REFUNDED
Search Order v9:    PAID
Payment Ledger v7: REFUNDED
~~~

Nếu Search applied watermark còn thiếu event Order v10 và trong lag budget, đó là **stale projection**. Nếu Search báo v10 nhưng vẫn PAID, khả năng **bug mapping hoặc field ownership**; cần điều tra và reproject.

## 39. Ma trận quyết định chọn kho dẫn xuất

| Nhu cầu | Kho có thể phù hợp | Đánh đổi / yêu cầu |
|---|---|---|
| Cache hồ sơ phổ biến | Redis hoặc in-process cache | TTL/invalidation, stale read |
| Full-text search | Elasticsearch/OpenSearch | Async indexing, rebuild |
| Query theo customer/createdAt | Denormalized NoSQL table | Extra writes, ordering, fan-out |
| Dashboard doanh thu lịch sử | Warehouse/lake | ETL delay, KPI definition |
| Top products cập nhật thường xuyên | Streaming aggregate/read model | Dedup, watermark |
| Offline mobile | Local store + sync queue | Conflicts, pending commands |
| Một quyết định unique | Authoritative conditional store | Không dựa vào search/cache |
| Ledger thanh toán | Source có invariant/durability phù hợp | Audit, reconciliation |
| Multi-service summary | CQRS projection/API composition | Freshness vs network fan-out |
| Lưu sự kiện domain bất biến | Event store có contract | Retention, replay, schema evolution |

### 39.1. Có thể có nhiều read models cho một source

~~~text
Order source
  -> orders_by_customer
  -> orders_by_status
  -> order_search_index
  -> revenue_warehouse
  -> customer_order_cache
~~~

Mỗi projection tối ưu một loại query; không nên ép nó trở thành owner chỉ vì API dùng nó nhiều.

### 39.2. Tránh tạo thêm kho khi chưa cần

Một hệ ít dữ liệu, ít query có thể dùng một database có index đủ tốt. Phải tính chi phí event bus, indexer, backfill, on-call, data governance trước khi chọn thêm NoSQL systems.

## 40. Trường hợp authority là giao thức chứ không một máy

### 40.1. Leader/quorum trong database

Một hệ NoSQL có nhiều replicas nhưng authority có thể được xác định qua leader/quorum, không đồng nghĩa một physical node luôn nắm sự thật.

~~~text
Business owner = Order Service
Canonical state = replicated database group
Write authority = leader/quorum protocol
~~~

Khi leader failover, Service owner và canonical dataset vẫn tồn tại; chỉ quyền điều phối vật lý chuyển node.

### 40.2. Hai nguồn sự thật có chủ ý?

Một số kiến trúc multi-master/CRDT cho nhiều replicas ghi đồng thời rồi merge theo protocol. Khi đó không đơn giản “chọn một DB làm source”; cần xác định:

- Các actors được phép tạo thay đổi.
- Quy tắc merge/causal ordering.
- Conflict resolution.
- Bất biến có thể bảo vệ hay phải coord.
- Quyền xem/ghi và giới hạn phân vùng.

### 40.3. Không suy CRDT giải mọi business constraint

Hai người cùng tạo claim username hoặc đặt chiếc ghế cuối cùng không thể chỉ merge tùy ý rồi xem cả hai xác nhận là đúng. Một số invariants vẫn cần coordination hoặc quota/escrow.

### 40.4. Authority theo thời điểm chuyển giao

Trong migration:

~~~text
Before cutover epoch 41: old write path authoritative.
After cutover epoch 42:  new write path authoritative.
~~~

Epoch/fencing và routing policy phải giúp tránh cả hai cùng nhận ghi có thẩm quyền.

## 41. Data correctness vs operational availability

### 41.1. Projection còn chạy khi source lỗi

Search có thể tiếp tục phục vụ dữ liệu cũ để người dùng duyệt sản phẩm. Đây là **graceful degradation** nếu API có thể chấp nhận stale.

### 41.2. Command không được suy từ dữ liệu cache

Nếu source Inventory mất quorum, checkout có thể phải tạm từ chối reservation mới để tránh oversell, dù Search/Redis vẫn trả dữ liệu nhanh.

### 41.3. Fail-open hay fail-closed?

| Tình huống | Lựa chọn thường đáng cân nhắc |
|---|---|
| Đọc mô tả sản phẩm | Cho phép stale có đánh dấu |
| Gợi ý tìm kiếm | Có thể dùng index cũ |
| Đặt chiếc vé cuối | Fail-closed nếu không xác minh owner |
| Chuyển tiền | Không xác nhận nếu outcome chưa rõ |
| Warehouse chưa bắt kịp | Mark report partial/as-of |
| Xóa dữ liệu cá nhân | Không coi completed nếu projection erasure còn pending |

Đây là định hướng; hợp đồng cụ thể cần business/risk owner phê duyệt.

### 41.4. Không chấp nhận HTTP 200 như tín hiệu đúng

Một API Search trả 200 với dữ liệu lỗi thời là thành công HTTP nhưng có thể vi phạm freshness SLO. Một Payment API trả 200 nhưng dựa trên cache sai là lỗi business nghiêm trọng.

## 42. Anti-patterns cần tránh

| Anti-pattern | Hệ quả | Hướng sửa |
|---|---|---|
| Hai services cùng tự ghi một field chuẩn | Split authority | Một owner/command contract |
| Search index được dùng cấp unique username | Race do eventual index | Conditional claim source |
| Redis stock quyết định checkout | Oversell vì stale cache | Inventory reservation authority |
| Update source rồi search bằng hai calls | Partial failure | Outbox/CDC |
| Publish event trước khi commit source | Event nói sai sự thật | Transactional outbox/domain transaction |
| Broker event được xem là domain fact dù chưa commit | Consumer thực hiện side effect sai | Emit after authoritative decision |
| Consumer replay side effects khi rebuild | Gửi email/charge trùng | Pure projection handlers |
| Projection ghi đè theo arrival order | State quay ngược | Version-aware apply |
| Dedupe bằng SELECT rồi UPDATE rời | Duplicate effect khi race | Atomic claim/transaction |
| Bỏ tombstone | Dữ liệu xóa hồi sinh | Delete propagation/generation |
| Cache invalidate trước commit source | Cache có thể tải lại state cũ | Invalidate after commit + version |
| Consumer lag=0 được xem là data correctness | Mapper bug không bị phát hiện | Reconciliation |
| Chuyển read alias khi index chưa catch up | Missing search results | Watermark/cutover |
| Query search NOT_FOUND sau POST để kết luận chưa tạo | Double create | Query authoritative operation status |
| Coi warehouse là nơi sửa order | Mất authority | Domain correction command |
| Chuyển MongoDB → DynamoDB bằng dual writes không có cutover | Split writes | Snapshot + CDC + fencing |
| Event log retention ngắn nhưng hứa rebuild mọi lịch sử | Không đủ dữ liệu lịch sử | Historical source/retention |
| Không ghi owner trong catalog | Shadow integration | Ownership matrix/lineage |
| Đưa toàn bộ PII vào search/analytics | Phạm vi rò rỉ/xóa tăng | Data minimization/access control |
| Nhiều DB nhưng không có on-call/rebuild owner | Sự cố kéo dài | Phân công vận hành rõ |
| Read model ghép bốn nguồn nhưng nói snapshot atomic | Hiểu sai nhất quán | Source versions/watermarks |
| Sử dụng LWW timestamp cho mọi conflict | Lost update/đúng nghiệp vụ bị phá | Version/merge protocol |
| Chỉ dùng TTL để kiểm soát stale | Không chặn mọi race invalidation | Versioned cache contract |
| Cho consumer ghi trực tiếp source theo document khác | Feedback loop | Owner API/command, ACL |
| Một “Data Lake” được tuyên bố là mọi source of truth | Không rõ fact/time/authority | Mô tả ownership từng dữ kiện |

## 43. Checklist thiết kế ở mức kiến trúc

### 43.1. Ownership

- Có owner cho mỗi business fact/command không?
- Có thực thể nào nhiều services cùng được quyền sửa một field không?
- Invariants được enforce ở đâu?
- Có xác định provenance và thời điểm hiệu lực không?

### 43.2. Read models

- Mỗi kho dẫn xuất dùng cho query nào?
- Có thể build lại từ nguồn/historical log không?
- Freshness và stale behavior được mô tả không?
- Đã giới hạn dữ liệu nhạy cảm đến mức cần thiết chưa?

### 43.3. Change propagation

- Có outbox/CDC với durability đúng không?
- Có checkpoint, eventId và aggregateVersion không?
- Delete/tombstone có truyền qua không?
- Có xử lý duplicate, out-of-order và gap không?
- Có replay/backfill khi vượt retention window không?

### 43.4. Operations

- Có dashboards lag và mismatches không?
- Có runbook rebuild/cutover/rollback không?
- Có trách nhiệm on-call cho projection không?
- Có fault injection để thử partial failure không?

### 43.5. Governance

- Data lineage/catalog cập nhật khi thêm consumer không?
- ACL ngăn direct write trái quyền không?
- PII retention, legal hold, erasure được kiểm soát không?
- Contract schema/version có test backward compatibility không?

## 44. Bài tập 1 — xác định nguồn chuẩn của một shop

Một shop dùng:

~~~text
MongoDB: Product, Order
Redis: cached stock, cached product detail
Elasticsearch: product search
DynamoDB: payment workflow state
Warehouse: revenue by day
~~~

Yêu cầu:

1. Chỉ định owner cho tên sản phẩm, giá hiện tại, tồn kho có thể bán, số tiền đã capture và KPI doanh thu.
2. Đánh dấu mỗi kho là source, replica, projection hoặc có thể chứa cả nhiều loại tùy namespace.
3. Đường ghi nào được phép sửa stock khi khách mua hàng?
4. Nếu Redis stock=1 nhưng Inventory source=0, checkout phải làm gì?
5. Có nên cho nhân viên sửa giá trực tiếp từ Elasticsearch? Vì sao?

## 45. Bài tập 2 — cùng một giá trị nhưng khác thời điểm

Ngày 10/11, khách mua sản phẩm giá 110.000 VND. Ngày 14/11, giá niêm yết là 120.000 VND. Search index vẫn hiển thị 115.000 VND do pipeline lỗi.

1. Giá nào đúng cho hóa đơn ngày 10/11?
2. Giá nào đúng cho catalog hiện tại?
3. Search index đang sai trong phạm vi nào?
4. Nếu Order Service đọc lại current price rồi sửa OrderLine lịch sử, hậu quả gì?
5. Đề xuất các field price snapshot, currency, pricingRuleVersion và effectiveAt.

## 46. Bài tập 3 — dual write failure

Service có code:

~~~text
saveOrderToMongoDB(order)
saveOrderToElasticsearch(order)
return success
~~~

Giả sử bước MongoDB commit thành công, search index timeout.

1. Có được coi Order chưa tồn tại không?
2. Có nên rollback MongoDB theo lỗi search không nếu contract chỉ yêu cầu source commit?
3. Điều gì xảy ra nếu process crash trước bước search?
4. Đề xuất transactional outbox hoặc CDC.
5. Nếu outbox publisher phát một event hai lần, consumer xử lý thế nào?
6. Vẽ trạng thái user-visible khi search bị chậm.

## 47. Bài tập 4 — thiết kế transactional outbox

Order Service cần:

~~~text
Order O101: DRAFT -> CONFIRMED
Publish OrderConfirmed
~~~

1. Mô tả transaction gồm canonical mutation và outbox entry.
2. Chọn các trường cho outbox: eventId, aggregateId, version, eventType, createdAt.
3. Publisher checkpoint sau khi broker ACK; crash giữa publish và checkpoint gây gì?
4. Consumer cần idempotency theo eventId/version ra sao?
5. Nếu Order nằm ở Database A nhưng outbox ở Database B, tính atomic có còn tự động không?

## 48. Bài tập 5 — event đến sai thứ tự

~~~text
Source:
  Order O101 v7 DRAFT
  Order O101 v8 CONFIRMED
  Order O101 v9 CANCELLED

Search receives:
  v9, v8, v9 duplicate
~~~

1. Nếu projector overwrite theo arrival order, trạng thái cuối có thể sai gì?
2. Đề xuất conditional upsert theo aggregateVersion.
3. Với event mang snapshot đầy đủ, có thể xử lý v9 trước v8 ra sao?
4. Nếu các events là delta, nhận v9 thiếu v8 phải làm gì?
5. Giải thích vì sao schemaVersion không là aggregateVersion.

## 49. Bài tập 6 — rebuild index không mất cập nhật

Một search index có 10 triệu documents. Bạn cần đổi analyzer, mất ba giờ để backfill. Trong ba giờ đó, sản phẩm vẫn được thêm/sửa/xóa.

1. Dùng snapshot và watermark W như thế nào?
2. Trong lúc quét snapshot, event nào phải được giữ lại?
3. Làm sao tránh mất DELETE sau snapshot?
4. Khi nào index mới đủ điều kiện nhận traffic?
5. Cách chuyển alias và rollback?
6. Vì sao không chạy replay handler có side effect gửi email?

## 50. Bài tập 7 — xác định tính rebuildable

Ba kho:

~~~text
A. Redis customer cache; source Customer DB còn đủ.
B. Search orders index; source Orders còn state hiện tại.
C. Revenue warehouse giữ giá lịch sử; source Orders đã xóa
   các giá chốt cũ và không có event log/backup.
~~~

1. Kho nào có khả năng rebuild đầy đủ dễ nhất?
2. Kho nào có thể rebuild state hiện tại nhưng không chắc lịch sử?
3. Kho nào có nguy cơ là nguồn duy nhất cho historical facts?
4. Nếu C bị xóa, có thể suy giá lịch sử từ Product.currentPrice không?
5. Nêu yêu cầu retention/history để tránh tình huống này.

## 51. Bài tập 8 — reconciliation

Một job đối soát báo:

~~~text
Source count:           1.000.000
Search count:           1.000.000
Source checksum:        A1
Search checksum:        B7
Consumer applied W1000
Source committed W1000
~~~

1. Count bằng nhau chứng minh dữ liệu giống nhau không?
2. Checksum khác nhau gợi ý gì?
3. Có phải nên overwrite source bằng search để hai hash giống nhau không?
4. Thiết kế cách tìm bucket/key lệch.
5. Nếu mismatch do mapper đổi currency, repair ra sao?

## 52. Bài tập 9 — source commit và projection lag

Order được confirm lúc 09:00:00, outbox publish 09:00:01, indexer apply 09:00:05 và search có thể thấy lúc 09:00:08.

1. Source commit → search visible mất bao lâu?
2. Nếu SLO p99 visibility dưới 10 giây, ví dụ này có đạt không?
3. Tại sao chỉ đo indexer apply lúc 09:00:05 chưa đủ?
4. Nếu user hỏi ngay lúc 09:00:02 liệu order đã confirm chưa, nên gọi nguồn nào?
5. Dashboard cần hiển thị dataAsOf thế nào để người dùng hiểu độ trễ?

## 53. Bài tập 10 — multi-service read model

OrderSummary lấy:

~~~text
Order Service:    O101 v8 CONFIRMED
Payment Service:  P901 v5 CAPTURED
Shipping Service: S801 v2 LABEL_CREATED
Customer Service: U101 v12 displayName=An
~~~

1. Ai sở hữu từng field của OrderSummary?
2. Projector có được tự cập nhật Payment source để sửa lỗi ghép dữ liệu không?
3. Thiết kế sourceVersions.
4. Nếu Payment v6 REFUNDED đến nhưng Order vẫn v8 CONFIRMED, có được tự chuyển Order sang CANCELLED không?
5. So sánh API composition đồng bộ và materialized read model cho dashboard.

## 54. Bài tập 11 — Cassandra query tables

Một ứng dụng có:

~~~text
orders_by_id
orders_by_customer
orders_by_day
~~~

1. Tại sao ba bảng cùng nằm trong Cassandra không tự có cùng quyền sở hữu?
2. Chọn một canonical operation owner.
3. Nếu ghi orders_by_id thành công nhưng orders_by_customer thất bại, hệ nên phục hồi ra sao?
4. Vì sao logged batch nhiều partitions không tự tương đương transaction ACID tổng quát?
5. Đề xuất cách rebuild orders_by_customer khi mapper/schema thay đổi.

## 55. Bài tập 12 — DynamoDB và Redis

Order v7 đang được cache. Reader miss cache và bắt đầu tải từ source. Writer chuyển Order sang v8 rồi invalidate cache. Reader kết thúc muộn và set lại v7.

1. Vẽ timeline race.
2. TTL 30 giây ngăn lỗi này hoàn toàn không?
3. Đề xuất version-aware cache update.
4. Nếu API cần read-your-writes, nên dùng đường đọc nào?
5. Nếu DynamoDB GSI vẫn chưa phản ánh v8, có thể dùng GSI để xác nhận commit không?

## 56. Bài tập 13 — privacy và dữ liệu đã xóa

Customer U101 yêu cầu xóa profile. Source đã xóa, nhưng search index, warehouse, Redis và một backup cũ còn bản ghi.

1. Tạo data lineage cho U101.
2. Những downstream stores nào cần erasure/anonymization theo policy?
3. Thiết kế tombstone có aggregateVersion và eraseGeneration.
4. Tại sao rebuild search từ snapshot cũ có thể làm dữ liệu xuất hiện lại?
5. Nêu vai trò legal hold và retention exemptions cần được xử lý theo policy.
6. Những metric nào cho biết yêu cầu xóa đã hoàn tất?

## 57. Bài tập 14 — migration MongoDB sang DynamoDB

Customer Service giữ hồ sơ MongoDB và muốn chuyển backend sang DynamoDB mà vẫn phục vụ writes.

1. Chọn thời điểm snapshot/capture W.
2. Cách replay CDC từ W sang DynamoDB.
3. Cách shadow read và đối soát dữ liệu.
4. Thời điểm nào chuyển quyền ghi mới?
5. Cần ngăn writers cũ bằng fencing/permissions ra sao?
6. Nếu DynamoDB nhận thêm writes sau cutover, rollback về MongoDB cần làm gì?
7. Nêu khác biệt giữa chuyển backend và chuyển domain ownership sang một service khác.

## 58. Bài tập 15 — event sourcing và CQRS

Một Order aggregate lưu:

~~~text
OrderCreated
ItemAdded
OrderConfirmed
OrderCancelled
~~~

1. Nếu event store là authoritative, current state được dựng thế nào?
2. Snapshot phục vụ read có phải source chuẩn không?
3. CDC event và domain event khác gì?
4. Khi replay 1 triệu events để rebuild, vì sao không gửi lại email cho các OrderConfirmed?
5. Nếu một event schema bị đổi nghĩa, backward compatibility cần gì?
6. Có cần CQRS vật lý cho một ứng dụng nhỏ ít truy vấn không?

## 59. Bài tập 16 — kiến trúc Saga

Một checkout workflow gồm:

~~~text
Order -> Inventory -> Payment -> Shipping
~~~

1. Service nào sở hữu trạng thái Order?
2. Ai sở hữu reservation quantity?
3. Ai sở hữu capture/refund ledger?
4. Saga orchestrator sở hữu điều gì?
5. Khi PaymentCaptured nhưng ShippingFailed, xử lý compensation như thế nào?
6. OrderSummary có thể ghép các states mà không trở thành owner của Payment không?

## 60. Bài tập 17 — lập data ownership catalog

Với một sản phẩm SaaS multi-tenant có Customer, Invoice, Subscription, AccessControl, Search và Analytics:

1. Liệt kê ít nhất 12 business facts.
2. Chỉ định owner/command cho mỗi fact.
3. Liệt kê derived consumers và mục đích query.
4. Ghi nguồn rebuild, retention và freshness SLO.
5. Ghi trường PII và quy trình erasure propagation.
6. Thiết kế access-control policy ngăn projection ghi source.
7. Đề xuất metric drift/mismatch và một runbook reconciliation.

## 61. Bài tập 18 — phân tích sự cố end-to-end

Ngày thứ Hai, người dùng báo các vấn đề:

~~~text
A. Order API trả CONFIRMED, search không thấy order.
B. Search có order CANCELLED nhưng Order API trả CONFIRMED.
C. Warehouse ghi doanh thu nhiều hơn payment ledger.
D. Redis hiển thị tồn kho 3 trong khi Inventory hết hàng.
E. Người dùng đã xóa nhưng còn trong index mới vừa rebuild.
~~~

Hãy xây bảng:

1. Sự thật nào được quyết định ở owner nào?
2. Có thể là stale hợp lệ hay lỗi correctness?
3. Đọc source version/watermark nào để điều tra?
4. Tầng nào cần repair, replay hay code fix?
5. Có cần thông báo partial/stale cho người dùng không?
6. Có business side effect nào cần chặn ngay?
7. Những regression/fault-injection tests nào nên bổ sung?

## 62. Tổng kết

Một hệ NoSQL thực tế có thể sở hữu **nhiều biểu diễn của cùng một dữ kiện**, nhưng không được vì thế mà có nhiều quyết định nghiệp vụ tùy tiện.

Những nguyên tắc cốt lõi:

1. **Xác định authority theo business fact/command/invariant**, không chỉ theo tên database. Customer profile, payment settlement, order snapshot và warehouse KPI có thể do những owners khác nhau chịu trách nhiệm.
2. **Source of truth không nhất thiết là một máy hay một collection.** Nó có thể là service API, replicated group có quorum, ledger hoặc domain event log được định nghĩa rõ.
3. **Kho dẫn xuất phục vụ một access pattern.** Redis cho cache, Elasticsearch cho tìm kiếm, NoSQL query table cho đọc theo khóa, warehouse cho analytics và client store cho offline.
4. **Replica khác projection.** Bản sao nội bộ theo replication protocol không giống một denormalized read model chạy qua CDC/outbox.
5. **Ghi qua owner, đọc qua đường thích hợp.** Search/cache không được tự quyết định inventory, username hoặc payment chỉ vì query nhanh.
6. **Dual write ngây thơ gây partial failure.** Transactional outbox hoặc CDC giúp truyền thay đổi đã commit mà không phải giả vờ có atomic transaction xuyên các kho.
7. **Consumers phải chịu được duplicate, out-of-order và delete.** EventId, aggregateVersion, conditional apply, tombstone và checkpoint/watermark là những thành phần thường cần.
8. **CQRS không đòi event sourcing; event sourcing không đồng nghĩa broker.** CQRS phân biệt command/read; event sourcing lưu domain events như nguồn chuẩn; CDC theo dõi commit của một nguồn khác.
9. **Projection phải có kế hoạch rebuild.** Snapshot + replay với watermark và chuyển read alias có kiểm soát giúp tránh index nửa vời hay mất cập nhật.
10. **Reconciliation kiểm chứng dữ liệu, không chỉ pipeline lag.** Count, checksum, source versions, business-field comparison và repair từ nguồn giúp tìm lỗi mapper/retention.
11. **Freshness là một contract.** Nguồn đã commit nhưng search còn trễ có thể chấp nhận được; một lệnh thanh toán không được quyết định bằng kết quả search eventual.
12. **Privacy/deletion phải lan truyền tới toàn bộ downstream.** Erasure, tombstone, retention và rebuild là một bài toán liên hệ nhiều kho.
13. **Migration owner cần cutover rõ.** Snapshot, CDC, shadow reads, epoch/fencing và rollback strategy ngăn old/new stores cùng trở thành nguồn ghi độc lập.
14. **Đầu tư vào ownership catalog.** Ghi rõ owner, contract, downstream, SLO, rebuild, retention và on-call để tránh shadow integration.

Câu hỏi kiểm tra kiến trúc cuối cùng là:

> **“Với một dữ kiện cụ thể, hệ nào được quyền quyết định và bảo vệ bất biến; nếu mọi cache, search index và read model đều bị xóa, chúng ta có thể tái tạo chúng từ dữ liệu có thẩm quyền với đủ lịch sử, thứ tự và quyền truy cập hay không?”**





