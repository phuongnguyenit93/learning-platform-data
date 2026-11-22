# Lập kế hoạch tách một năng lực khỏi hệ thống cũ

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Xác định lý do kinh doanh và kỹ thuật đủ mạnh để tách một năng lực khỏi hệ thống cũ (legacy system).
2. Khảo sát luồng nghiệp vụ, dependency, dữ liệu, transaction, traffic và ownership trước khi chọn boundary.
3. Phân biệt tách module trong code với tách service ở runtime, data ownership và deployment.
4. Chọn một capability có phạm vi phù hợp, có thể vận hành độc lập và có đường chuyển đổi từng bước.
5. Thiết kế target architecture, API/event contract và anti-corruption layer để legacy và service mới cùng tồn tại.
6. Lập kế hoạch backfill, CDC/outbox, cutover, reconciliation và xử lý dữ liệu phát sinh trong lúc migration.
7. Triển khai strangler pattern, branch by abstraction, shadow traffic, canary và expand–migrate–contract.
8. Xây dựng tiêu chí rollback có tính đến write đã phát sinh, event đã publish và schema đã thay đổi.
9. Phân công ownership giữa nhóm legacy, nhóm service mới, platform, SRE, QA và product.
10. Đo hiệu quả bằng lead time, latency, error rate, data correctness, operational load và tổng chi phí.
11. Xác định điều kiện dừng, điều kiện tiếp tục và thời điểm loại bỏ đường xử lý cũ.

Tách một năng lực khỏi hệ thống cũ không phải là thao tác chuyển một thư mục source sang repository khác. Đây là một thay đổi có ảnh hưởng tới **nghiệp vụ, dữ liệu, hợp đồng tích hợp, vận hành và trách nhiệm sở hữu**. Một kế hoạch tốt làm rõ vì sao cần tách, tách phần nào, chuyển theo thứ tự nào, làm sao biết dữ liệu đúng và cách quay lại khi một giai đoạn thất bại.

## 1. Bài toán: tách một capability khỏi legacy system

Giả sử một nền tảng bán lẻ đang chạy trên một ứng dụng Spring Boot lớn. Ứng dụng này quản lý sản phẩm, giá, đơn hàng, khách hàng, thanh toán và hỗ trợ. Các module cùng dùng một database; một số nhóm truy vấn trực tiếp bảng của nhau. Khi traffic storefront tăng, Catalog/Search làm tải database tăng và các lần phát hành thay đổi sản phẩm thường phải chờ lịch release của toàn ứng dụng.

Doanh nghiệp muốn tách năng lực **Product Catalog và Search** thành một service độc lập để:
- Xử lý lượng đọc lớn và scale riêng.
- Tối ưu search index/cache theo workload.
- Cho nhóm Catalog phát hành thay đổi độc lập.
- Có ownership rõ cho product query và search behavior.
- Giảm tải đọc lên database giao dịch của legacy app.

Nhưng Catalog data hiện nằm trong database của legacy app. Checkout vẫn cần giá và thông tin sản phẩm hợp lệ. Support có dashboard đọc product table. Một batch job cập nhật giá vào ban đêm. Nếu tạo Catalog Service rồi chuyển traffic ngay, hệ thống có thể trả dữ liệu cũ, bỏ sót cập nhật hoặc làm checkout dùng sai giá.

Bài toán cần giải là: **chuyển quyền sở hữu capability theo từng giai đoạn trong khi hệ thống hiện tại vẫn phục vụ nghiệp vụ**.

### Sơ đồ hiện trạng

~~~text
                    Storefront / Mobile
                            |
                            v
                 Legacy Commerce Application
                 +----------------------------+
                 | Catalog module             |
                 | Search query               |
                 | Order / Checkout           |
                 | Pricing                    |
                 | Support                    |
                 +-------------+--------------+
                               |
                               v
                      Shared Legacy DB
                      - products
                      - prices
                      - orders
                      - customers
                      - ...
                               ^
                               |
                    Batch jobs / Reports
~~~

### Sơ đồ đích dự kiến

~~~text
                 Storefront / Mobile
                         |
                         v
                    API Gateway
                         |
             +-----------+-----------+
             |                       |
             v                       v
       Catalog Service        Legacy Commerce App
       Catalog DB             Order / Checkout
       Search Index                 |
       Cache                        |
             ^                      |
             |                      |
       Product Events <--- Outbox / CDC
             ^
             |
       Legacy DB (giai đoạn chuyển đổi)
~~~

Trong giai đoạn đầu, legacy app vẫn là nguồn dữ liệu chuẩn; Catalog Service xây read model từ event/CDC. Sau khi quyền ghi được chuyển an toàn, Catalog Service có thể trở thành owner của product data. Không nên mặc định phải chuyển read và write cùng lúc.

## 2. Xác định lý do tách trước khi thiết kế service

Một đề xuất tách cần chỉ rõ vấn đề hiện tại và kết quả mong muốn. Các lý do hợp lệ có thể gồm:

- **Release coupling:** thay đổi Catalog phải chờ phát hành toàn bộ legacy app.
- **Scaling mismatch:** Catalog có tải đọc cao hơn nhiều so với các capability còn lại.
- **Reliability boundary:** search/index có thể degrade mà không làm giao dịch đặt hàng dừng.
- **Security/data ownership:** một nhóm cần kiểm soát dữ liệu hoặc quyền truy cập riêng.
- **Technology fit:** workload tìm kiếm cần engine/index khác với database giao dịch.
- **Team ownership:** nhóm Catalog có thể chịu trách nhiệm từ code tới production.
- **Product velocity:** thay đổi Catalog thường xuyên và có thể đo được chi phí chờ đợi.

Không nên tách chỉ vì:
- Một module có nhiều class hoặc nhiều dòng code.
- Muốn có thêm một service trong sơ đồ.
- Một framework mới đang được ưa chuộng.
- Tổ chức muốn mỗi nhóm có một repository nhưng chưa có ownership rõ.
- Database đang chậm nhưng chưa xác định query, index hay capacity là nguyên nhân.
- Muốn giải quyết code coupling bằng cách chuyển coupling thành network call.

### Viết problem statement

Một problem statement có thể theo mẫu:

~~~text
Hiện trạng:
  Catalog đọc dữ liệu trực tiếp từ shared database của legacy app.
  Traffic đọc sản phẩm tăng nhanh và gây contention với giao dịch.

Tác động:
  p95 product query vượt SLO vào giờ cao điểm.
  Release Catalog thường phải chờ release legacy.
  Tăng replica legacy làm tăng chi phí cho cả module ít tải.

Mục tiêu:
  Tách product query/search thành một capability có owner và
  runtime riêng, giữ checkout correctness và không mất cập nhật.

Phạm vi:
  Product read/search trước; quyền ghi product data chuyển sau
  khi backfill, event propagation và reconciliation đạt điều kiện.
~~~

Problem statement giúp phân biệt mục tiêu thật với giải pháp được chọn sẵn. Nếu vấn đề chỉ là một query thiếu index, tách service có thể không phải cách giải quyết tốt nhất.

## 3. Kiểm tra xem có thực sự cần tách

Trước khi bắt đầu, so sánh một số lựa chọn ít tốn kém hơn:

1. Tối ưu query, index, connection pool và database capacity.
2. Thêm cache hoặc read replica cho legacy application.
3. Tách worker hoặc process riêng nhưng giữ chung codebase/database.
4. Modularize Catalog trong legacy app và tạo public interface.
5. Tạo read model/search index trong cùng ứng dụng.
6. Tách Catalog Service thành runtime và data owner riêng.

Nếu một lựa chọn đơn giản hơn giải quyết được mục tiêu trong thời gian đủ dài, có thể trì hoãn service extraction. Nếu cần release autonomy, security isolation hoặc scaling độc lập thực sự, service boundary có thể đáng đầu tư.

### Câu hỏi ra quyết định

- Bao nhiêu phần trăm traffic thuộc capability này?
- Có số liệu chứng minh scaling hiện tại gây lãng phí hoặc ảnh hưởng SLO không?
- Các thay đổi của capability có thường xuyên bị chặn bởi release chung không?
- Những capability khác có cần transaction nguyên tử với nó không?
- Ai sẽ sở hữu dữ liệu sau khi tách?
- Những consumer nào đang đọc dữ liệu trực tiếp?
- Team mới có thể vận hành service và on-call không?
- TCO ba năm của migration, runtime và platform là bao nhiêu?
- Nếu không tách, có thể đạt kết quả bằng modularization/cache/read replica không?

## 4. Discovery: khảo sát hệ thống cũ trước khi thay đổi

Không thiết kế target boundary chỉ từ tên module. Cần khám phá cách nghiệp vụ đang chạy thực tế, bao gồm những dependency không được ghi trong tài liệu.

### 4.1 Kiểm kê luồng nghiệp vụ

Vẽ các use case liên quan:
- Tạo sản phẩm.
- Cập nhật tên, mô tả, thuộc tính và trạng thái kinh doanh.
- Thay đổi giá hoặc chương trình khuyến mãi.
- Publish/unpublish sản phẩm.
- Search, filter, sort và pagination.
- Checkout đọc snapshot sản phẩm/giá.
- Support tra cứu sản phẩm.
- Batch import/export.
- Đồng bộ với đối tác hoặc marketplace.

Với mỗi use case, ghi actor, entry point, service/module được gọi, bảng được đọc/ghi, event phát sinh và lỗi có thể xảy ra.

### 4.2 Lập dependency inventory

| Dependency | Câu hỏi cần trả lời | Bằng chứng |
| --- | --- | --- |
| API callers | Ai gọi Catalog endpoint? | Access logs, gateway routes |
| Direct DB readers | Ai đọc product tables? | SQL logs, code search, credentials |
| Writers | Ai cập nhật product/price? | Repository, job, admin tool |
| Batch jobs | Job nào import/export hoặc sửa dữ liệu? | Scheduler inventory |
| Event consumers | Ai đọc product events? | Broker consumer groups/catalog |
| Reports | Dashboard nào query trực tiếp? | BI lineage, query audit |
| External systems | Marketplace/PIM/vendor nào đồng bộ? | Integration registry |
| Cache/index | Những bản sao nào tồn tại? | Redis, search engine, CDN |
| Data retention | Product data có policy nào? | Data inventory/policy |
| Owners | Ai chịu trách nhiệm? | Service catalog/team mapping |

Đặc biệt tìm những caller không đi qua API chính thức: script, BI query, cron job, admin UI, export tool và service account dùng chung database credential.

### 4.3 Đo baseline

Thu thập số liệu trước migration:
- Request rate theo endpoint/use case.
- p50/p95/p99 latency và error rate.
- Query latency, lock wait, connection pool và DB CPU/IO.
- Cache hit ratio và search query distribution.
- Tần suất release và thời gian chờ release.
- Số consumer/writer và số thay đổi cần phối hợp.
- Incident, MTTR và số lỗi dữ liệu.
- Chi phí compute, database, cache và observability.
- Số giờ vận hành/on-call cho capability.

Không dùng một ngày tải thấp làm baseline cho sản phẩm có mùa vụ. Chọn cửa sổ đủ đại diện, bao gồm peak hoặc campaign nếu có.

## 5. Chọn boundary của capability

Một capability nên có business purpose và data ownership rõ. Với Catalog, có thể xác định:

**In scope**
- Product identity.
- Product description và attributes.
- Category/brand relationship.
- Publication status.
- Search document và query behavior.
- Product read API.
- Product change events.

**Có thể ngoài scope**
- Order line snapshot.
- Giá thanh toán cuối cùng nếu Pricing là domain riêng.
- Customer profile.
- Inventory reservation.
- Payment transaction.
- Search analytics nếu thuộc Data Platform.

### Phân biệt product data và order snapshot

Khi khách đặt hàng, Order cần lưu tên sản phẩm, SKU, đơn giá và currency tại thời điểm mua. Snapshot đó thuộc Order và không nên thay đổi khi Catalog sửa tên hoặc giá sau này.

Catalog Service có thể cung cấp dữ liệu hiện hành; Order vẫn sở hữu snapshot giao dịch của mình. Không để Order query Catalog mỗi lần hiển thị lịch sử rồi ghi đè dữ liệu snapshot.

### Dấu hiệu boundary phù hợp

- Business rules có thể được mô tả và kiểm thử riêng.
- Một nhóm có thể sở hữu thay đổi và vận hành.
- Dữ liệu có thể chuyển quyền ghi.
- Consumer có thể dùng API/event thay vì truy cập bảng nội bộ.
- Có thể xác định consistency requirement.
- Số lượng cross-boundary calls và transaction không quá dày.
- Có thể định nghĩa SLO và failure behavior riêng.

Nếu Catalog thường xuyên phải cập nhật đồng bộ một transaction với Order và Inventory, cần xem lại phạm vi hoặc cách phân chia invariant trước khi tách.

## 6. Xác định target ownership và source of truth

Trong quá trình migration, cần ghi rõ ai là nguồn chuẩn ở từng giai đoạn.

| Giai đoạn | Product write owner | Product read source | Ghi chú |
| --- | --- | --- | --- |
| Hiện trạng | Legacy app | Legacy DB | Catalog chưa tách |
| Read model build | Legacy app | Legacy DB và service shadow | Service mới chưa phục vụ traffic |
| Read cutover | Legacy app | Catalog Service projection | Projection có freshness SLA |
| Write transition | Một owner được chỉ định | Catalog Service/legacy adapter | Không để hai writer độc lập |
| Hoàn tất | Catalog Service | Catalog Service | Legacy tables/path được retire |

**Không để hai hệ thống cùng là source of truth lâu dài.** Nếu legacy và Catalog Service đều cho phép cập nhật product mà không có quy tắc conflict, dữ liệu sẽ lệch và không biết bên nào thắng.

Cần định nghĩa:
- Writer owner ở từng pha.
- Ai có quyền thay đổi record.
- Stable product ID và uniqueness.
- Version/sequence cho event.
- Cách xử lý update đồng thời.
- Cách chuyển quyền ghi.
- Cách khôi phục khi cutover thất bại.

## 7. Thiết kế target contract trước khi tách code

Catalog Service cần công bố API và event contract có version.

Ví dụ API:

~~~http
GET /catalog/products/{productId}
GET /catalog/products?query=keyboard&category=accessories
GET /catalog/categories/{categoryId}
~~~

Response minh họa:

~~~json
{
  "productId": "prd-1024",
  "sku": "KB-1024",
  "name": "Mechanical Keyboard",
  "status": "PUBLISHED",
  "attributes": {
    "layout": "ANSI",
    "switchType": "linear"
  },
  "catalogVersion": 18,
  "updatedAt": "2026-11-12T03:00:00Z"
}
~~~

Contract phải làm rõ:
- Field bắt buộc/tùy chọn và enum.
- Pagination, sort/filter semantics.
- Search freshness và eventual consistency.
- Authorization/tenant visibility.
- Error codes và retry behavior.
- Cache headers và freshness.
- Rate limit, timeout và SLO.
- Product version và cách phát hiện stale data.

### Event contract

Legacy app có thể phát ProductCreated, ProductUpdated, ProductPublished và ProductUnpublished qua outbox/CDC. Ví dụ:

~~~json
{
  "eventId": "evt-901",
  "eventType": "ProductUpdated",
  "schemaVersion": 1,
  "productId": "prd-1024",
  "aggregateVersion": 18,
  "occurredAt": "2026-11-12T03:00:00Z",
  "changedFields": ["name", "attributes"]
}
~~~

Payload có thể chứa snapshot cần thiết hoặc chỉ reference tùy yêu cầu consumer. Cần tránh phát dữ liệu nhạy cảm không cần thiết. Event có ID, aggregate version và semantics rõ để consumer xử lý duplicate/out-of-order.

## 8. Tách một interface trước khi tách runtime

Nếu legacy code truy cập trực tiếp ProductRepository từ nhiều nơi, bước đầu là tạo một interface do Catalog capability sở hữu.

~~~text
Before:
  Order ----> ProductRepository
  Support --> ProductRepository
  Web ------> ProductRepository
  Batch ----> ProductRepository

After:
  Order ----> CatalogQueryPort
  Support --> CatalogQueryPort
  Web ------> CatalogQueryPort
  Batch ----> CatalogAdminPort
                     |
                     v
             Legacy Catalog Module
~~~

Ví dụ Java:

~~~java
public interface CatalogQueryPort {
    ProductView findById(String productId);
    ProductPage search(ProductSearchCriteria criteria);
}
~~~

Các caller dùng interface và DTO công bố, không dùng JPA entity hoặc repository nội bộ. Implementation ban đầu vẫn đọc legacy database. Đây là **branch by abstraction**: tạo seam trước, sau đó thay implementation.

Khi Catalog Service sẵn sàng, có thể thêm RemoteCatalogAdapter và chuyển qua cấu hình/feature flag. Caller không cần thay toàn bộ domain logic cùng lúc, nhưng phải xử lý các semantics mới của network call như timeout, lỗi và stale response.

## 9. Strangler pattern: chuyển traffic theo lát nhỏ

Strangler pattern cho phép chuyển từng endpoint hoặc use case từ legacy sang service mới.

~~~text
Giai đoạn đầu:
  Client ---> Legacy App ---> Legacy Catalog

Giai đoạn chuyển:
  Client ---> Gateway/Facade
                  |                         |        --> Catalog Service
                  |
                  +----------> Legacy App (các capability khác)

Giai đoạn cuối:
  Client ---> Catalog Service
         --> Legacy App (Order, Customer, Support)
~~~

Các nguyên tắc:
- Chuyển một use case hoặc endpoint có thể quan sát rõ.
- Duy trì response semantics tương thích trong thời gian chuyển.
- Không chuyển write ownership khi chưa kiểm soát dữ liệu.
- Có feature flag hoặc routing rule để giới hạn traffic.
- Đo kết quả trước khi tăng tỷ lệ.
- Xóa đường cũ sau khi consumer và dữ liệu đã được đối soát.

Gateway có thể route traffic, nhưng không nên trở thành nơi chứa business logic Catalog. Nếu có adapter/facade, cần owner và thời hạn loại bỏ.

## 10. Chiến lược dữ liệu: backfill, CDC và outbox

Đây thường là phần rủi ro nhất của extraction. Catalog Service cần có dữ liệu ban đầu và nhận mọi thay đổi xảy ra trong lúc backfill.

### 10.1 Backfill snapshot

Một job đọc product records từ legacy DB và ghi vào Catalog DB/search index. Job cần:
- Stable key.
- Checkpoint để tiếp tục sau lỗi.
- Batch size và rate limit.
- Idempotent upsert.
- Version/timestamp để chống ghi đè dữ liệu mới.
- Metrics số record đọc/ghi/lỗi.
- Reconciliation số lượng và checksum phù hợp.

Không tải toàn bộ bảng vào memory hoặc chạy một transaction kéo dài nếu dữ liệu lớn.

### 10.2 Change Data Capture (CDC)

CDC đọc transaction log hoặc change stream của legacy DB để phát những thay đổi sau thời điểm snapshot. Cần xác định:
- Snapshot start position/LSN/binlog offset.
- Event ordering theo aggregate.
- Schema evolution.
- Duplicate delivery.
- Connector lag và retention của transaction log.
- Xử lý delete/tombstone.
- Khả năng replay khi consumer lỗi.

Một quy trình điển hình:
1. Chọn snapshot boundary T0 và lưu CDC offset tương ứng.
2. Bắt đầu CDC để không mất thay đổi sau T0.
3. Backfill dữ liệu snapshot tại T0.
4. Replay CDC từ offset đã ghi, áp dụng version-aware upsert.
5. Theo dõi lag cho tới khi projection gần realtime.
6. Reconcile dữ liệu và xử lý mismatch.

Nếu không có cách liên kết snapshot với CDC offset, có thể có khoảng trống hoặc cập nhật bị áp dụng sai thứ tự.

### 10.3 Transactional outbox

Nếu legacy application kiểm soát được write path, transactional outbox có thể ghi product update và outbox event trong cùng transaction:

~~~text
Legacy transaction:
  UPDATE product
  INSERT outbox_event
  COMMIT
       |
       v
Outbox relay / CDC
       |
       v
Message broker
       |
       v
Catalog projection consumer
~~~

Outbox giúp tránh tình trạng DB commit nhưng publish event thất bại. Relay vẫn có thể phát trùng nếu crash sau publish trước khi đánh dấu; consumer phải idempotent.

Nếu nhiều batch/script ghi trực tiếp database và không tạo outbox, CDC có thể bao phủ những đường ghi đó tốt hơn. Cần kiểm tra khả năng và semantics của CDC connector trước khi chọn.

## 11. Tránh dual-write không an toàn

Một anti-pattern phổ biến:

~~~text
Legacy App:
  1. Write Legacy DB
  2. Call Catalog API to write Catalog DB
~~~

Nếu bước 1 thành công nhưng bước 2 timeout, hai database lệch. Retry có thể tạo duplicate hoặc ghi đè update mới. Không có transaction ACID tự động bao trùm hai DB.

Các lựa chọn:
- Giữ legacy là writer duy nhất, Catalog chỉ nhận event/projection trong pha đầu.
- Chuyển write ownership rõ ràng sang Catalog; legacy gọi API mới.
- Dùng outbox/CDC để đồng bộ một chiều.
- Nếu bắt buộc dual-write tạm thời, có idempotency, version, reconciliation, conflict policy và deadline kết thúc.

**Không để dual-write hai chiều vô thời hạn.** Đây là trạng thái chuyển tiếp có chi phí và phải có điều kiện đóng.

## 12. Cutover read traffic an toàn

Sau khi backfill và CDC chạy ổn định, có thể chuyển read traffic theo giai đoạn:
1. Shadow read: legacy trả response, service mới đọc cùng request nhưng kết quả không trả về client.
2. Compare: so sánh các field/record quan trọng, ghi mismatch không chứa PII không cần thiết.
3. Canary: chuyển một tỷ lệ nhỏ traffic hoặc một nhóm tenant.
4. Ramp-up: tăng tỷ lệ khi latency/error/data correctness đạt ngưỡng.
5. Full read cutover: Catalog Service phục vụ query trong phạm vi.
6. Retire old reads: ngừng truy vấn product tables từ caller cũ.

Không nên shadow write thật hoặc gọi side effect ở service mới nếu chưa có idempotency và cô lập. Shadow traffic nên chỉ thực hiện read-only hoặc dùng môi trường dữ liệu riêng.

### So sánh kết quả

Các trường cần so:
- Product ID và SKU.
- Publication status.
- Category/attribute mapping.
- Search result ordering nếu có semantics ổn định.
- Visibility theo tenant/market.
- Giá hoặc reference giá nếu thuộc scope.
- Pagination/count.
- Deleted/unpublished product behavior.

Search ranking có thể khác do engine/index mới; cần định nghĩa tiêu chí tương đương theo nghiệp vụ thay vì yêu cầu byte-for-byte giống nhau khi behavior chủ ý thay đổi.

## 13. Chuyển write ownership

Read cutover và write cutover là hai quyết định riêng. Trước khi chuyển write:
- Catalog Service đã nhận đủ dữ liệu và xử lý CDC.
- Các admin UI, batch import và integration writers đã được kiểm kê.
- Có API/command contract cho create/update/publish.
- Authorization và audit được triển khai.
- Version/optimistic locking hoặc conflict policy rõ.
- Có migration/cutover window và rollback strategy.
- Legacy code không còn là writer độc lập sau thời điểm chuyển.

Một cách chuyển:
1. Đóng hoặc giới hạn write trong một cửa sổ ngắn nếu nghiệp vụ cho phép.
2. Chờ CDC lag về mức mục tiêu.
3. Reconcile dữ liệu cuối.
4. Chuyển writer endpoint/admin tool sang Catalog Service.
5. Ghi nhận write owner và generation/version.
6. Theo dõi write success, event lag và mismatch.
7. Ngăn legacy app tiếp tục ghi bảng cũ.
8. Mở lại luồng nghiệp vụ và kiểm tra các consumer.

Nếu không thể dừng write, cần một protocol chuyển quyền có sequence/epoch để bảo đảm chỉ một writer hợp lệ tại một thời điểm. Không chỉ dựa vào thời gian đồng hồ hoặc một feature flag chưa được đồng bộ.

## 14. Quản lý API consumer và direct database access

Trước khi retire bảng cũ, cần chuyển mọi caller:
- Storefront/mobile.
- Checkout/Order.
- Support dashboard.
- Admin portal.
- Batch import/export.
- Reporting/BI.
- Marketplace integration.
- Scheduled jobs.
- Data pipeline.

Với consumer nội bộ, có thể phát hành client library có version hoặc cập nhật trực tiếp contract. Với consumer bên ngoài/mobile, cần support window và deprecation notice.

Direct DB access là một trong những dependency khó phát hiện. Có thể:
- Kiểm tra DB query logs/audit.
- Tạo database role riêng cho từng application.
- Theo dõi connection identity.
- Chặn dần quyền đọc bảng cũ sau khi consumer chuyển.
- Giữ read-only compatibility view tạm thời nếu cần.
- Đặt owner và deadline cho mọi exception.

Không drop bảng chỉ dựa trên việc code search không còn reference; batch job hoặc query BI có thể nằm ngoài repository.

## 15. Tương thích schema và API qua nhiều phiên bản

Trong rolling deployment, legacy app và Catalog Service có thể chạy các phiên bản khác nhau. Cần expand–migrate–contract:

**Expand**
- Thêm endpoint/event/schema mới.
- Giữ field/route cũ.
- Consumer có thể đọc cả hai dạng.

**Migrate**
- Chuyển từng caller.
- Backfill dữ liệu.
- Theo dõi usage và compatibility.
- Giải quyết client/worker chậm.

**Contract**
- Chỉ bỏ đường cũ khi consumer inventory và telemetry đủ bằng chứng.
- Ngừng ghi và đọc cũ.
- Xóa schema/table/adapter sau khi không còn rollback dependency.

Không đổi nghĩa một field mà giữ tên/version. Nếu semantics thay đổi, cần contract version hoặc event type mới.

## 16. Định nghĩa consistency và freshness

Catalog Service có thể phục vụ read model được cập nhật qua CDC/event. Vì vậy, cần một freshness target rõ:
- Product update xuất hiện trong search index trong bao lâu?
- Unpublish có cần ẩn khỏi storefront gần như tức thời không?
- Checkout phải kiểm tra giá hiện hành ở nguồn nào?
- Support có thể thấy dữ liệu trễ vài giây không?
- Khi event lag vượt ngưỡng, query có fallback về legacy không?

Một policy minh họa:
- Product description/search: eventual consistency trong một cửa sổ ngắn.
- Product publication status: freshness chặt hơn vì sản phẩm bị gỡ phải ngừng bán.
- Checkout price: xác nhận từ Pricing/authoritative source, không dùng search index stale làm giá cuối.
- Order snapshot: giữ giá/tên tại thời điểm giao dịch.

Fallback về legacy có thể hữu ích nhưng không được làm shared DB quá tải khi service mới down. Cần rate limit, cache và degraded behavior rõ.

## 17. Xử lý lỗi và trạng thái không rõ kết quả

Các tình huống cần thiết kế:
- Catalog Service down trong lúc legacy vẫn hoạt động.
- Broker/CDC connector lag.
- Consumer nhận event trùng.
- Event version cũ tới sau version mới.
- Backfill job dừng giữa batch.
- Search index mất hoặc phải rebuild.
- Cutover xong nhưng phát hiện mismatch.
- Legacy app vẫn có writer chưa chuyển.
- Catalog DB restore từ snapshot cũ.

Mỗi tình huống cần owner, metric, runbook và recovery procedure.

### Idempotent projection consumer

Consumer có thể lưu aggregateVersion và chỉ áp dụng event mới hơn:

~~~text
if incoming.aggregateVersion <= stored.aggregateVersion:
    ignore as duplicate or stale
else:
    apply change
    store incoming.aggregateVersion
~~~

Thao tác update dữ liệu và version cần atomic trong Catalog DB. Với side effect bên ngoài DB, cần outbox/work item và idempotency riêng. Không dựa vào timestamp đồng hồ giữa các service nếu có thể dùng version/sequence do source owner cấp.

## 18. Rollback: phải xét dữ liệu đã ghi

Rollback không chỉ là đổi route về legacy. Cần xác định rollback có khả thi ở từng giai đoạn.

| Giai đoạn | Rollback có thể làm gì? | Rủi ro cần xử lý |
| --- | --- | --- |
| Interface refactor | Trả implementation về local adapter | Giữ behavior tương đương |
| Backfill | Dừng job, resume sau | Không xóa dữ liệu nguồn |
| Shadow read | Tắt shadow traffic | Không có write side effect |
| Canary read | Route lại legacy | Kiểm tra legacy còn đủ dữ liệu/capacity |
| Full read cutover | Route về legacy nếu source vẫn đồng bộ | Legacy có thể đã ngừng nhận update |
| Write ownership transfer | Cần chuyển writer hoặc đồng bộ ngược | Không được mất write mới |
| Legacy table retirement | Có thể không rollback đơn giản | Cần backup/restore và forward-fix plan |

Trước khi chuyển write owner, phải xác định:
- Có thể đồng bộ ngược thay đổi từ Catalog DB về legacy không?
- Có thể replay event để dựng lại dữ liệu không?
- Version/epoch nào đang có quyền ghi?
- Những update nào đã được xác nhận với người dùng?
- Khi nào phải chọn forward-fix thay vì rollback?

Nếu service mới đã nhận write và legacy không còn đồng bộ, route về legacy có thể trả dữ liệu cũ. Đừng đưa ra một nút rollback giả tạo không bảo toàn dữ liệu.

## 19. SLO và observability trong thời gian migration

Theo dõi cả service mới, legacy và hành trình end-to-end.

| Metric | Ý nghĩa |
| --- | --- |
| catalog_request_rate | Lưu lượng đọc/ghi |
| catalog_latency_p95/p99 | Độ trễ API |
| catalog_error_rate | Lỗi theo endpoint/status |
| cdc_lag_seconds | Độ trễ đồng bộ từ legacy |
| projection_events_processed | Throughput consumer |
| projection_failures_total | Lỗi apply event |
| projection_duplicate_total | Event trùng |
| product_reconciliation_mismatch | Record/field lệch |
| search_index_freshness | Độ mới của search index |
| legacy_product_reads | Caller còn đọc đường cũ |
| legacy_product_writes | Writer chưa chuyển |
| cutover_traffic_ratio | Tỷ lệ traffic đi service mới |
| fallback_rate | Tỷ lệ phải quay về legacy |
| migration_backfill_remaining | Số record chưa xử lý |

Không gắn product/customer ID có cardinality cao vào metric labels. Dùng logs/traces có kiểm soát để điều tra theo correlation ID và giữ payload tối thiểu.

### Business metrics

- Tỷ lệ search query thành công.
- Product detail conversion.
- Checkout price mismatch.
- Số đơn bị ảnh hưởng bởi product visibility sai.
- Tỷ lệ sản phẩm cập nhật xuất hiện trong index đúng hạn.
- Số thao tác admin thất bại.
- Customer support tickets do dữ liệu không đồng bộ.

SLO của Catalog không thay thế SLO checkout. Nếu Catalog p95 tốt nhưng checkout sử dụng giá stale, migration vẫn thất bại về nghiệp vụ.

## 20. Security, privacy và data governance

Tách service làm thay đổi phạm vi dữ liệu và quyền:
- Catalog Service cần service identity và quyền đọc/ghi đúng product data.
- Legacy app không nên giữ quyền admin rộng vô thời hạn.
- API cần authorization theo tenant/market/role.
- Event payload chỉ chứa trường consumer cần.
- Secret, certificate và database credential có vòng đời riêng.
- Audit ai tạo/sửa/publish product.
- Logs/traces không ghi payload nhạy cảm không cần thiết.
- Backup, retention và deletion policy phải bao phủ Catalog DB, search index, cache và event stream.
- Quy trình incident và access review phải cập nhật.

Nếu Catalog có dữ liệu do nhà cung cấp hoặc đối tác sở hữu, cần kiểm tra license, retention và quyền phân phối trước khi replicate sang hệ thống mới.

## 21. Build, test và deploy độc lập

Service mới cần có:
- Repository/module boundary và owner.
- Build tool/wrapper, Java toolchain và dependency version rõ.
- Unit/component/integration/contract tests.
- Docker image và artifact provenance.
- CI pipeline riêng.
- Configuration/secrets theo môi trường.
- Health/readiness probes.
- Resource requests/limits và autoscaling policy.
- Deployment/rollback pipeline.
- Dashboard, alerts, runbook và on-call.

Legacy app cũng cần được thay đổi để:
- Phát event/outbox hoặc CDC.
- Dùng interface/adapter mới.
- Ngừng truy cập trực tiếp data sau cutover.
- Có compatibility tests trong thời gian service mới và legacy cùng tồn tại.

Build độc lập không tự đảm bảo deploy độc lập. API/event contract phải tương thích qua nhiều phiên bản và thứ tự release.

## 22. Test plan theo từng giai đoạn

| Giai đoạn | Kiểm thử trọng tâm |
| --- | --- |
| Discovery | Trace use case, SQL/query inventory, writer inventory |
| Interface extraction | Unit/component tests giữ nguyên behavior |
| Contract design | Schema validation, provider/consumer tests |
| Backfill | Count, checksum, required fields, referential mapping |
| CDC | Ordering, duplicate, retry, lag, delete/tombstone |
| Shadow read | So sánh response và business fields |
| Canary | Latency, error, freshness, business outcome |
| Write cutover | Idempotency, optimistic locking, writer exclusivity |
| Rollback drill | Route, data sync, replay và consistency |
| Retirement | Không còn caller/writer, migration/backup verification |

Test cả dữ liệu biên:
- Product không có category.
- Product bị unpublish trong lúc search.
- Product đổi giá trong lúc checkout.
- Duplicate ProductUpdated.
- Event đến sai thứ tự.
- Record bị xóa trong lúc backfill.
- CDC lag tăng cao.
- Search index rebuild từ event lịch sử.
- Một consumer chưa chuyển sang API mới.

Không dùng một fixed sleep để kết luận projection đã đồng bộ. Poll postcondition có deadline và báo rõ record/partition nào chưa đạt.

## 23. Phân công trách nhiệm

| Vai trò | Trách nhiệm |
| --- | --- |
| Legacy team | Hiểu write paths, phát outbox/CDC, chuyển caller và retire code cũ |
| Capability team | Thiết kế Catalog contract, data model, service, migration consumer và vận hành |
| Platform team | CI/CD, secrets, service discovery, observability, broker và deployment templates |
| Data/Analytics | Kiểm kê BI/ETL consumer, lineage và migration read models |
| QA | Test plan, data comparison, contract, canary và regression |
| SRE | SLO, capacity, rollout, alert, incident và rollback drills |
| Product owner | Phạm vi, thứ tự use case, downtime window và business acceptance |
| Security/Data owner | Quyền truy cập, dữ liệu, audit, retention và policy |

Một activity cần có một owner cuối cùng. Các nhóm tham gia phải xác nhận deliverable và thời điểm; không dùng “đã thông báo” thay cho consumer readiness.

## 24. Roadmap mẫu cho extraction

Lịch sau chỉ minh họa. Mỗi giai đoạn chỉ chuyển tiếp khi exit criteria đã đạt.

~~~text
Phase 0 — Discovery and baseline
  - Map use cases, callers, writers, data and SLO
  - Confirm capability boundary and business case

Phase 1 — Modularize the seam
  - Create Catalog public interface
  - Move callers away from direct repository access
  - Add architecture and contract tests

Phase 2 — Build the new service
  - Catalog API, DB, search index, CI/CD and observability
  - Keep legacy as the only writer

Phase 3 — Backfill and synchronize
  - Snapshot + CDC/outbox
  - Version-aware projection and reconciliation

Phase 4 — Shadow and canary reads
  - Compare results
  - Ramp traffic with freshness/error gates

Phase 5 — Transfer write ownership
  - Move admin/batch writers
  - Enforce one writer owner
  - Reconcile and monitor

Phase 6 — Retire legacy path
  - Remove direct reads/writes
  - Drop old schema only after dependency and rollback review
  - Update runbooks and service catalog
~~~

Không nên đặt deadline cứng cho mọi phase trước khi biết kích thước dữ liệu, số consumer và khả năng của CDC. Hãy estimate sau discovery, thêm buffer cho partner/batch consumer và định nghĩa điều kiện dừng.

## 25. Exit criteria cho từng phase

**Discovery complete**
- Đã xác định tất cả writer/reader quan trọng.
- Có baseline và problem statement.
- Có target owner, boundary và risk register.
- Có phê duyệt scope và success metrics.

**Interface extraction complete**
- Caller dùng public interface.
- Không còn dependency mới vào persistence internal.
- Tests bảo toàn behavior hiện tại.
- Có adapter local và remote seam.

**Backfill complete**
- Tất cả record trong scope được xử lý.
- Count/checksum/field reconciliation đạt ngưỡng.
- CDC offset và lag được theo dõi.
- Delete/update trong thời gian backfill không bị mất.

**Read cutover complete**
- Canary và full traffic đạt SLO.
- Data freshness trong giới hạn.
- Business mismatch ở ngưỡng chấp nhận.
- Có fallback/rollback path đã thử.

**Write transfer complete**
- Một writer owner duy nhất.
- Các admin/batch/integration writers đã chuyển.
- Không còn dual-write vô kiểm soát.
- Reconciliation và audit hoạt động.

**Legacy retirement complete**
- Không còn reader/writer hợp lệ dùng đường cũ.
- Consumer inventory được xác nhận.
- Backup/restore và rollback dependencies được xử lý.
- Code, role và schema cũ được retire có kiểm soát.

## 26. Rủi ro thường gặp và cách giảm thiểu

| Rủi ro | Hậu quả | Giảm thiểu |
| --- | --- | --- |
| Bỏ sót direct DB reader | Caller lỗi sau khi drop table | Query audit, role inventory, deprecation |
| Snapshot/CDC gap | Mất cập nhật | Gắn snapshot boundary với CDC offset |
| Event duplicate | Projection hoặc side effect lặp | Idempotency và aggregate version |
| Event out-of-order | Dữ liệu cũ ghi đè mới | Version-aware consumer |
| Dual-write lệch | Hai source of truth | Một writer owner, outbox/CDC |
| Cutover quá sớm | Search/read trả dữ liệu stale | Shadow, canary, freshness gate |
| Legacy không còn dữ liệu mới | Rollback trả stale result | Data sync/forward-fix plan |
| Consumer ẩn | Lỗi BI/batch/partner | Inventory và telemetry |
| DB overload khi backfill | Ảnh hưởng giao dịch | Batch, rate limit, off-peak |
| Search ranking khác | UX/analytics thay đổi | Golden dataset và acceptance criteria |
| Team mới chưa vận hành được | Incident kéo dài | Runbook, on-call readiness |
| Scope phình to | Migration kéo dài | Giữ capability scope nhỏ, change control |

## 27. TCO và lợi ích cần đo

Extraction có chi phí:
- Phân tích domain và dependency.
- Build service mới và data store.
- Backfill, CDC/outbox, broker và schema registry.
- API client, contract tests và migration consumer.
- CI/CD, image registry, secrets và security.
- Logs, metrics, traces, dashboards và alert.
- On-call, runbook, incident và backup/restore.
- Dual-run, support legacy và cleanup.

Lợi ích có thể gồm:
- Giảm release wait của Catalog.
- Scale search/read mà không nhân bản toàn legacy app.
- Giảm DB contention và cải thiện p95.
- Ownership rõ hơn.
- Giảm blast radius cho search/index failure.
- Tăng tốc thay đổi và thử nghiệm.

Đo trước/sau:
- p95/p99 product query và checkout.
- DB CPU/IO/connection contention.
- Cost per product query hoặc successful checkout.
- Deployment lead time và coordinated release ratio.
- Error rate, incident count và MTTR.
- CDC lag, reconciliation mismatch và fallback rate.
- On-call hours và maintenance effort.

Không coi số ngày elapsed được rút ngắn là số ngày công tiết kiệm. Chỉ quy đổi thành tiền khi có tác động business hoặc labor được chứng minh.

## 28. Checklist trước khi bắt đầu extraction

- [ ] Problem statement nêu rõ tác động hiện tại và mục tiêu đo được.
- [ ] Đã xem xét tối ưu legacy/module/cache/read replica như phương án thay thế.
- [ ] Capability boundary dựa trên business rules và ownership.
- [ ] Đã kiểm kê API callers, direct DB readers/writers, batch, BI và partner.
- [ ] Có traffic, latency, error, cost và release baseline.
- [ ] Có data inventory, source of truth và stable identifiers.
- [ ] Có target architecture và contract version.
- [ ] Có consistency/freshness policy.
- [ ] Có snapshot/backfill/CDC/outbox strategy.
- [ ] Có idempotency, versioning, retry và reconciliation.
- [ ] Có plan chuyển read và write ownership riêng.
- [ ] Có canary, shadow comparison và cutover gates.
- [ ] Có rollback/forward-fix plan tính đến write mới.
- [ ] Có CI/CD, security, SLO, capacity, on-call và runbook.
- [ ] Có owner cho từng phase và consumer migration.
- [ ] Có TCO, success criteria và stop criteria.
- [ ] Có kế hoạch retire old path và quyền truy cập cũ.

## 29. Bài tập thực hành

Một legacy Spring Boot application đang quản lý sản phẩm, đơn hàng, khách hàng và thanh toán trong cùng database. Product search chiếm phần lớn read traffic. Storefront, Checkout, Support dashboard, batch import và BI report đều đọc product data; một số caller truy cập trực tiếp bảng. Nhóm muốn tách Product Catalog thành Catalog Service có database và search index riêng.

Hãy lập một kế hoạch extraction gồm:

1. Problem statement và lý do tách; nêu ít nhất hai phương án ít thay đổi hơn để so sánh.
2. Sơ đồ hiện trạng và target architecture qua từng giai đoạn.
3. Bounded context, in-scope/out-of-scope và owner.
4. Inventory của API callers, direct DB readers/writers, batch, BI và external systems.
5. Data model và source-of-truth matrix trước, trong và sau cutover.
6. OpenAPI/event contract cho ProductCreated, ProductUpdated và ProductUnpublished.
7. Cách tạo interface trong legacy app trước khi thay implementation bằng remote adapter.
8. Snapshot + CDC/outbox backfill strategy, offset boundary và version-aware consumer.
9. Shadow read, canary, reconciliation và tiêu chí tăng traffic.
10. Quy trình chuyển write ownership, ngăn dual-write và xử lý update đồng thời.
11. Kịch bản rollback khi Catalog Service đã nhận write.
12. SLO, metrics, alerts, security và on-call readiness.
13. Roadmap có owner, deliverable, exit criteria và risk register.
14. TCO và success metrics để quyết định có tiếp tục extraction hay dừng.

### Tình huống sự cố để phân tích

Trong lúc canary 20% traffic:
- CDC lag tăng lên 90 giây.
- Một batch import vẫn ghi trực tiếp legacy DB.
- Search index hiển thị một số sản phẩm đã unpublish.
- Catalog Service p95 tốt hơn legacy 35%, nhưng checkout phát hiện một số giá hiển thị đã cũ.
- Legacy team muốn rollback traffic về monolith.

Hãy giải thích:
- Có nên rollback ngay không? Điều kiện nào quyết định?
- Làm sao xác định batch import có phải nguồn update bị bỏ sót?
- Có thể dùng Catalog search result làm giá cuối cùng trong checkout không?
- Cần sửa event/CDC, freshness gate hoặc source of truth ra sao?
- Làm thế nào bảo đảm rollback không làm mất update đã phát sinh?
- Ai chịu trách nhiệm quyết định và thông báo cho product/business?

### Tiêu chí tự đánh giá

| Tiêu chí | Bằng chứng |
| --- | --- |
| Lý do tách | Baseline và problem statement |
| Boundary | Capability scope, owner, data ownership |
| Discovery | Caller/writer/dependency inventory |
| Data correctness | Snapshot/CDC/version/reconciliation |
| Compatibility | API/event contracts và consumer plan |
| Migration | Phases, canary, cutover và rollback |
| Operations | SLO, metrics, security, on-call |
| Economics | TCO, benefits và stop criteria |

## Kết luận

Tách một năng lực khỏi hệ thống cũ là một quá trình chuyển đổi ownership và luồng dữ liệu, không chỉ là tạo thêm một ứng dụng. Bắt đầu bằng problem statement, baseline và discovery; chọn capability có boundary đủ rõ; tạo interface và contract; xây service mới; backfill và đồng bộ dữ liệu; chuyển read rồi write theo các gate; cuối cùng mới retire đường cũ.

Một extraction an toàn luôn biết ai là source of truth ở từng giai đoạn, cách xử lý event trùng/sai thứ tự, cách đối soát dữ liệu và điều gì xảy ra khi rollback. Thành công được đo bằng kết quả nghiệp vụ, SLO, release autonomy và TCO. Nếu những chỉ số đó không cải thiện, cần xem lại boundary hoặc dừng mở rộng thay vì tiếp tục tách chỉ vì kế hoạch ban đầu đã được phê duyệt.
