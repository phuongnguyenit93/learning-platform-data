# Lựa chọn loại lưu trữ theo nhu cầu và chi phí vận hành

## 1. Vì sao lựa chọn nơi lưu dữ liệu là quyết định kiến trúc?

Trong kiến trúc microservices, mỗi dịch vụ sở hữu một phần dữ liệu và các quy tắc nghiệp vụ liên quan. Dữ liệu của Order Service, Catalog Service, Inventory Service hay Payment Service không chỉ có cấu trúc khác nhau; chúng còn có yêu cầu khác nhau về giao dịch, truy vấn, mở rộng, tính sẵn sàng, bảo mật, thời hạn lưu giữ và phục hồi sau sự cố.

Một quyết định lưu trữ sai có thể gây ra hai loại chi phí:

1. **Chi phí kỹ thuật và nghiệp vụ:** khó bảo đảm tính đúng đắn, truy vấn chậm, dữ liệu lệch, migration rủi ro, không đáp ứng yêu cầu phục hồi hoặc compliance.
2. **Chi phí vận hành toàn vòng đời:** hạ tầng, bản sao, backup, mạng, license, giám sát, nâng cấp, nhân sự trực sự cố, kiểm thử và thời gian phát triển.

Ví dụ, một nhóm nhỏ chọn một hệ cơ sở dữ liệu phân tán phức tạp chỉ vì có thể phục vụ hàng triệu request mỗi giây, trong khi sản phẩm mới chỉ có vài trăm người dùng và các transaction liên quan đơn hàng cần ràng buộc nhất quán. Nhóm có thể phải bỏ nhiều thời gian vận hành cluster, xử lý consistency và viết logic thay cho những khả năng sẵn có của một relational database.

Ngược lại, một hệ thống lưu lượng rất lớn lưu toàn bộ sự kiện telemetry vào một bảng OLTP có nhiều index và retention vô hạn có thể gặp bottleneck chi phí và ghi dữ liệu. Khi đó, time-series hoặc analytical storage với thiết kế retention và ingestion phù hợp có thể hiệu quả hơn.

**Nguyên tắc trung tâm:** bắt đầu từ dữ liệu, hành vi truy cập, bất biến nghiệp vụ và năng lực vận hành. Chỉ sau đó mới chọn hệ lưu trữ, dịch vụ managed và chiến lược mở rộng. Không có loại database duy nhất tốt nhất cho mọi workload.

Bài này trình bày:

- Cách xác định quyền sở hữu dữ liệu ở ranh giới microservices.
- Cách đọc đặc điểm workload và chọn relational, document, key-value, wide-column, graph, search, time-series, object storage hoặc analytical storage.
- Cách đánh giá consistency, transaction, availability, backup, bảo mật và mở rộng.
- Cách tính tổng chi phí sở hữu và chi phí vận hành thực tế.
- Cách đưa ra quyết định qua ma trận, thử nghiệm, case study và ADR.
- Cách thay đổi loại lưu trữ mà vẫn bảo vệ hợp đồng dữ liệu và tránh dual-write.

## 2. Quyền sở hữu dữ liệu phải được xác định trước công nghệ

**Data ownership** nghĩa là một service hoặc một bounded context có quyền quyết định mô hình nghiệp vụ, bất biến, vòng đời và cách thay đổi dữ liệu thuộc phạm vi của mình.

Ví dụ trong thương mại điện tử:

| Dịch vụ | Dữ liệu sở hữu | Bất biến điển hình |
| --- | --- | --- |
| Identity | Người dùng, thông tin đăng nhập hoặc identity references | Quyền truy cập và danh tính hợp lệ |
| Catalog | Thông tin sản phẩm, mô tả, danh mục | SKU hợp lệ và quy tắc xuất bản |
| Inventory | Số lượng sẵn có, reservation, movement | Không giữ vượt giới hạn theo chính sách |
| Order | Đơn hàng, trạng thái, lịch sử thay đổi | Transition hợp lệ, số tiền đơn được ghi đúng |
| Payment | Payment intent, transaction status, reconciliation | Không thực hiện tác dụng thu tiền trùng |
| Notification | Template, delivery attempt, trạng thái gửi | Retry không tạo tác dụng ngoài ý muốn nếu contract yêu cầu |
| Analytics | Read model, báo cáo, số liệu tổng hợp | Có độ trễ cập nhật và nguồn dữ liệu rõ ràng |

**Database per service** là một nguyên tắc về **quyền sở hữu logic**, không bắt buộc mỗi service phải có một server vật lý hoặc cloud account riêng từ ngày đầu. Một tổ chức nhỏ có thể sử dụng một PostgreSQL cluster với database/schema, tài khoản truy cập và migration tách biệt cho từng service nếu vẫn bảo đảm không truy cập trực tiếp dữ liệu của service khác.

Điều cần tránh là service A và B cùng sửa một bảng, cùng tự đặt business rules, hoặc dùng join xuyên database để né API contract. Khi ranh giới quyền sở hữu mờ, đổi database của một service sẽ kéo theo sửa hàng loạt service khác.

### 2.1. Một service có thể dùng nhiều loại lưu trữ không?

Có. Một service có thể sở hữu:

- **Primary transactional store** cho trạng thái nghiệp vụ.
- **Cache** cho dữ liệu đọc nhiều, tái tạo được.
- **Search index** cho full-text search hoặc faceted search.
- **Object storage** cho ảnh và file nhị phân lớn.
- **Event log hoặc outbox** phục vụ tích hợp.
- **Read model** để phục vụ truy vấn chuyên biệt.

Tuy nhiên, cần xác định **nguồn sự thật có thẩm quyền (source of truth)**. Search index và cache thường là biểu diễn dẫn xuất, không phải nơi duy nhất ghi nhận số tiền đã thanh toán. Nếu dữ liệu giữa các hệ lưu trữ tạm thời khác nhau, phải có quy tắc cập nhật, độ trễ chấp nhận và khả năng xây dựng lại.

### 2.2. Shared infrastructure khác shared ownership

Hai service dùng chung một máy chủ database chưa chắc vi phạm data ownership nếu chúng được phân quyền và quản lý schema riêng. Ngược lại, mỗi service có database riêng nhưng vẫn gọi SQL trực tiếp vào database của service khác qua quyền admin thì ownership vẫn bị phá vỡ.

Một ranh giới lành mạnh cần:

1. Một nhóm hoặc service có quyền thay đổi schema/logic nghiệp vụ.
2. Chỉ owner được ghi dữ liệu chính.
3. Các service khác sử dụng API, command hoặc event theo hợp đồng.
4. Migrations có trách nhiệm và quy trình triển khai rõ.
5. Quyền truy cập kỹ thuật thực thi ownership, không chỉ dựa vào quy ước.

## 3. Bắt đầu từ yêu cầu, không bắt đầu từ tên database

Trước khi liệt kê công nghệ, hãy mô tả dữ liệu và cách sử dụng.

### 3.1. Những câu hỏi bắt buộc

| Khía cạnh | Câu hỏi |
| --- | --- |
| Business invariants | Những điều kiện nào không bao giờ được sai? |
| Consistency | Sau ghi, người dùng hoặc service khác cần thấy dữ liệu mới ngay hay có thể trễ? |
| Transactions | Có cần cập nhật nhiều bản ghi atomically? |
| Access patterns | Chủ yếu truy vấn theo ID, join, range, aggregation, full-text hay graph traversal? |
| Read/write ratio | Số đọc/ghi và độ biến động theo ngày/giờ thế nào? |
| Data shape | Dữ liệu có cấu trúc bảng, JSON thay đổi nhanh, chuỗi thời gian, binary hay vector? |
| Size/growth | Tổng dung lượng hiện tại, tốc độ tăng và retention dự kiến? |
| Latency | p95/p99 mục tiêu trong điều kiện tải xác định? |
| Availability | Chấp nhận downtime, RPO và RTO bao nhiêu? |
| Durability | Mất bản ghi có chấp nhận được không? |
| Security | Dữ liệu nhạy cảm, mã hóa, phân quyền, audit, data residency? |
| Team skills | Nhóm có khả năng vận hành, backup, tuning và khôi phục hệ thống không? |
| Budget | Giá cloud/license, egress, nhân sự và tổng chi phí theo thời gian? |
| Migration | Có kế hoạch đổi schema/công nghệ và xây dựng lại read models không? |

Không nên chỉ ghi “cần scale cao”. Cần định nghĩa **cao bao nhiêu, ở truy vấn nào, vào khi nào, theo mô hình tăng trưởng nào và dữ liệu nào có thể phân vùng**.

### 3.2. Ví dụ profile workload

Giả định Order Service có:

- 400 yêu cầu tạo đơn/phút ở giờ cao điểm.
- 90% truy vấn đọc đơn theo orderId hoặc customerId.
- Mỗi đơn gồm header, dòng sản phẩm, tiền và trạng thái.
- Cần transaction để tạo đơn cùng dòng đơn.
- Cần index theo người dùng, ngày tạo và trạng thái.
- Không được ghi nhận một đơn hai lần khi client retry cùng operationId.
- Có retention theo chính sách kế toán và nghiệp vụ.
- Team có ba backend developers, ít kinh nghiệm vận hành hệ thống phân tán lớn.

Đây là profile định hướng tốt hơn nhiều so với yêu cầu “chọn NoSQL để scale”. Với workload như trên, relational database có transaction và index thường là ứng viên rất đáng thử đầu tiên. Việc lựa chọn cuối cần kiểm tra tải, ngân sách, managed service và ràng buộc thực tế.

## 4. Phân loại nhu cầu theo dữ liệu và truy vấn

Một hệ thống có thể có cùng lúc nhiều dạng dữ liệu:

- **Transactional entities:** order, payment, inventory movement.
- **Document aggregates:** hồ sơ, catalog attributes, cấu hình có cấu trúc linh hoạt.
- **Key lookups:** session, feature flag, token metadata, cache.
- **High-throughput append:** telemetry, clickstream, sensor events.
- **Text retrieval:** tìm kiếm tên/mô tả, lọc nhiều facet, ranking.
- **Relationship traversal:** đồ thị mạng xã hội hoặc phát hiện liên kết gian lận.
- **Time-series:** chỉ số đo liên tục kèm timestamp và retention.
- **Analytical queries:** tổng hợp lớn theo nhiều chiều, nhiều tháng/năm.
- **Binary objects:** ảnh, tài liệu, video, bản sao dữ liệu.
- **Vector similarity:** tìm embedding gần nhất theo ngữ nghĩa.

Một số sản phẩm có thể đáp ứng nhiều loại workload. Ví dụ PostgreSQL hỗ trợ JSON, full-text search và extension vector; một cloud database managed có thể hỗ trợ key-value và document patterns. **Phân loại workload không đồng nghĩa bắt buộc chọn một engine mới cho mỗi dòng.**

## 5. Relational database: lựa chọn mặc định hợp lý khi cần transaction

Đại diện: PostgreSQL, MySQL và các hệ RDBMS khác.

### 5.1. Điểm mạnh

- Schema rõ và quan hệ giữa các thực thể được biểu diễn bằng bảng/khóa.
- Transaction ACID trong phạm vi engine và cấu hình hỗ trợ.
- Ràng buộc UNIQUE, FOREIGN KEY, CHECK giúp bảo vệ bất biến.
- SQL hỗ trợ join, range query, filter, aggregation, index.
- Hệ sinh thái tooling, migration, backup, observability trưởng thành.
- Có thể dùng read replica, partitioning, connection pooling và các hình thức mở rộng khác.

Ví dụ tạo đơn gồm order header và order lines trong một transaction để tránh lưu đơn không có dòng hàng:

~~~sql
BEGIN;

INSERT INTO orders(order_id, customer_id, status, total_minor)
VALUES ('O-8421', 'C-17', 'PENDING', 250000);

INSERT INTO order_items(order_id, sku, quantity, unit_price_minor)
VALUES ('O-8421', 'SKU-1', 2, 125000);

COMMIT;
~~~

Đây là ví dụ đơn giản; production còn cần validate, ràng buộc idempotency, tính lại tổng tiền ở phía server và bảo vệ concurrency.

### 5.2. Những giới hạn và chi phí

- Join và query không đúng index có thể rất tốn kém khi dữ liệu lớn.
- Ghi tập trung có thể thành bottleneck; scaling write ngang cần chiến lược phù hợp.
- Cross-region consistency thường tăng latency và độ phức tạp.
- Schema migration cần quản lý version và deploy an toàn.
- Pool kết nối, locks, vacuum/compaction, replication lag, index bloat và backups cần vận hành đúng.
- SQL không tự làm transaction xuyên tất cả microservices hay external payment provider thành atomic.

**Ngộ nhận:** “SQL không scale được.” Thực tế nhiều workload lớn có thể phục vụ tốt bằng index, cache, read replica, partitioning, thay đổi mô hình truy vấn hoặc kiến trúc distributed SQL. Cần đo bottleneck trước khi rời relational model.

### 5.3. Khi nên ưu tiên

- Order, payment intent, inventory ledger hoặc các aggregate có transaction mạnh.
- Dữ liệu quan hệ rõ, cần uniqueness và join.
- Team nhỏ cần thời gian phát triển nhanh và nền tảng quen thuộc.
- Workload chưa chứng minh cần một mô hình truy cập chuyên biệt khác.

## 6. Document database: dữ liệu dạng aggregate linh hoạt

Đại diện: MongoDB hoặc các hệ document database khác, với hành vi và tính năng transaction phụ thuộc sản phẩm.

Document database lưu một thực thể hoặc aggregate dưới dạng document, thường là JSON/BSON hoặc biểu diễn tương tự.

Ví dụ Catalog product:

~~~json
{
  "productId": "P100",
  "name": "Bàn phím",
  "brand": "Example",
  "attributes": {
    "layout": "75%",
    "switchType": "linear",
    "connectivity": ["usb", "bluetooth"]
  },
  "variants": [
    {"sku": "P100-BLK", "color": "black"},
    {"sku": "P100-WHT", "color": "white"}
  ]
}
~~~

### 6.1. Khi document model phù hợp

- Một aggregate được đọc/ghi cùng nhau.
- Thuộc tính có nhiều biến thể hoặc phát triển nhanh.
- Truy vấn chủ yếu xoay quanh khóa và fields bên trong document.
- Có thể thiết kế indexes đúng theo access patterns.
- Team hiểu giới hạn kích thước document và cập nhật đồng thời.

### 6.2. Trade-offs

- Embedding quá nhiều dữ liệu dẫn tới document phình to hoặc khó cập nhật.
- Duplication có thể tăng, cần chiến lược đồng bộ và invalidation.
- Quan hệ nhiều-nhiều, join phức tạp và reporting có thể bất tiện hơn theo từng engine.
- Tính năng transaction/multi-document consistency **khác nhau theo sản phẩm**, không thể tuyên bố mọi document DB không hỗ trợ ACID.
- Index và query patterns vẫn cần quản trị; schema linh hoạt không nghĩa là không cần schema validation/version.

Không nên chọn document database chỉ vì “không cần migration”. Mỗi client, API và event vẫn kỳ vọng một hợp đồng dữ liệu; document không có cấu trúc thống nhất sẽ gây lỗi khi phiên bản phát triển.

## 7. Key-value storage: rất tốt cho truy cập theo khóa

Đại diện: Redis với các chế độ lưu trữ/cấu hình tương ứng, hoặc những dịch vụ managed key-value/database hỗ trợ key-based access.

Mô hình:

~~~text
key                       value
session:abc123             session metadata
rate:tenant-17:2026-11-11  counter/state
feature:tenant-17          feature flags
product:P100:summary       cached product summary
~~~

### 7.1. Phù hợp

- Cache dữ liệu tính lại được.
- Session/state có TTL khi phù hợp bảo mật và durability.
- Rate-limit counters.
- Các phép tra cứu theo khóa với latency thấp.
- Một số workflow dùng atomic operation có phạm vi được hỗ trợ.

### 7.2. Cần phân biệt cache và primary database

Redis thường được dùng làm cache, nhưng độ bền dữ liệu phụ thuộc cấu hình persistence, replication, failover và product/managed service. **Không nên mặc định mọi Redis deployment là nơi lưu dữ liệu bền vững** cũng không nên mặc định mọi Redis deployment mất dữ liệu ngay khi restart.

Một cache miss không phải thất bại của nghiệp vụ nếu có thể truy xuất lại primary store. Một payment state chỉ lưu trong cache dễ trở thành rủi ro nếu bị eviction hoặc TTL trước khi đối soát.

### 7.3. Chi phí và rủi ro

- Dữ liệu in-memory có thể tốn chi phí theo RAM; cấu hình eviction cần hiểu rõ.
- Hot keys làm tải không phân bố đều.
- Cache stampede xảy ra khi nhiều request đồng thời tái tải dữ liệu.
- Invalidation sai tạo dữ liệu cũ, có thể làm sai quyết định nếu dùng trong bước cần strong consistency.
- Replication và failover có semantics riêng; không tự bảo đảm every write đã được ghi bền ở mọi node.

**Quy tắc:** cache là giải pháp giảm chi phí đọc hoặc latency cho workload đo được, không phải cách mặc định loại bỏ consistency requirements.

## 8. Wide-column / distributed key-based database

Đại diện: Apache Cassandra, Google Bigtable và các hệ phân tán tổ chức dữ liệu dựa trên partition/row key, với tính năng khác nhau theo sản phẩm.

### 8.1. Điểm mạnh

- Thiết kế cho tập dữ liệu lớn, write throughput cao và horizontal scaling.
- Truy cập nhanh khi query bám sát partition key đã thiết kế.
- Có thể phù hợp với telemetry hoặc event-like workloads rất lớn.
- Một số engine có replication đa vùng và cơ chế availability đặc thù.

### 8.2. Trade-offs

- Thiết kế partition key là quyết định cốt lõi. Chọn sai dẫn tới hot partition, query khó hoặc cần scan lớn.
- Không thuận tiện cho ad-hoc joins và truy vấn không biết trước.
- Consistency levels, transaction/counter/conditional writes có semantics khác RDBMS và khác giữa các engine.
- Compaction, tombstones, repair, hotspot, capacity planning và restore có thể làm vận hành phức tạp.
- Team cần kinh nghiệm mô hình hóa **theo query** thay vì chỉ theo quan hệ thực thể.

Ví dụ ghi hàng tỷ metrics theo deviceId và time bucket có thể phù hợp với partition-oriented storage, nhưng nếu sản phẩm mới chỉ vài triệu bản ghi cần join và transaction phức tạp, chọn hệ này sớm có thể làm tăng chi phí không cần thiết.

## 9. Search engine và full-text index

Đại diện: Elasticsearch/OpenSearch, Lucene-based systems và khả năng full-text search trong relational database.

### 9.1. Vì sao cần search storage?

Các nhu cầu:

- Tìm kiếm văn bản theo nhiều trường.
- Tokenization, stemming, synonym và language analyzer.
- Fuzzy search, relevance scoring.
- Faceted filters: giá, danh mục, thương hiệu.
- Autocomplete, ranking, kết hợp từ khóa.

Catalog có thể lưu product source trong database chính và đồng bộ search document sang search index.

~~~mermaid
flowchart LR
    C["Catalog Service"] --> DB[("Catalog primary DB")]
    DB --> O[("Outbox / CDC")]
    O --> S[("Search Index")]
    U["Search API"] --> S
~~~

### 9.2. Search index thường là dữ liệu dẫn xuất

Nếu primary DB đã commit giá sản phẩm mới nhưng index cập nhật chậm, người dùng có thể thấy kết quả search cũ trong một khoảng thời gian. Hệ thống phải định nghĩa độ trễ chấp nhận được và cách xử lý các field cần chính xác tuyệt đối.

Ví dụ giá cuối khi checkout nên xác minh từ service sở hữu giá và nghiệp vụ, không chỉ từ search index được lập trước đó.

### 9.3. Chi phí vận hành

- Ingestion pipeline, index mappings và reindexing.
- Shards, replicas, cluster topology, memory và storage.
- Duplicate data từ primary database.
- Query tuning và chi phí relevance.
- Rebuild index sau lỗi hoặc thay đổi analyzer.
- Quản lý consistency và schema evolution.

Trước khi triển khai một search cluster riêng, hãy thử khả năng full-text search sẵn có trong database đang dùng; nếu yêu cầu ít phức tạp, cách này có thể đủ và giảm chi phí.

## 10. Time-series database: tối ưu dữ liệu theo thời gian

Đại diện: InfluxDB, TimescaleDB hoặc các sản phẩm tối ưu time-series theo cấu hình phù hợp.

Workload điển hình:

~~~text
timestamp             metric          tags                  value
2026-11-11T10:00Z     cpu_usage       service=orders        61.2
2026-11-11T10:01Z     cpu_usage       service=orders        64.8
2026-11-11T10:02Z     request_count   service=orders        940
~~~

### 10.1. Phù hợp khi

- Việc ghi dữ liệu theo timestamp liên tục.
- Truy vấn theo time range và aggregation/window.
- Có retention policy, downsampling và nén dữ liệu.
- Cần tổng hợp metrics/telemetry/sensor theo thời gian.

### 10.2. Những bẫy

- High cardinality của tags/labels có thể làm index và RAM tăng mạnh.
- Retention vô hạn gây chi phí tăng nhanh; cần định nghĩa chu kỳ sống của raw data.
- Query xuyên business entities nhiều quan hệ có thể không thuận tiện.
- Với metrics có tính tiền, phải xác định tính chính xác, late arrivals và aggregation semantics.
- Không nên tự biến time-series store thành source of truth cho giao dịch thanh toán chỉ vì dữ liệu có timestamp.

Một relational database có partitioning/time-series extension có thể phù hợp nếu đội muốn giảm số công nghệ cần vận hành.

## 11. Object storage: nơi phù hợp cho file và binary lớn

Đại diện: các dịch vụ cloud object storage và hệ tương đương.

Nhu cầu:

- Ảnh sản phẩm, video, hóa đơn PDF, tài liệu.
- Backup và archival.
- Data lake, log thô, kết quả export.
- Static assets dùng với CDN.

Một object thường có **key/path**, nội dung binary, metadata và chính sách truy cập. Các ứng dụng thường lưu bản ghi business metadata trong database chính, còn bytes nằm ở object storage.

Ví dụ:

~~~text
Document Service DB:
  documentId
  ownerId
  objectKey
  contentType
  checksum
  status
  retentionPolicy

Object storage:
  tenant-17/documents/7d2a/invoice.pdf
~~~

### 11.1. Không đưa binary lớn vào RDBMS theo thói quen

Lưu ảnh/video trực tiếp trong một bảng transaction có thể làm backup, replication, memory và I/O tốn kém. Object storage thường phù hợp hơn với large immutable-ish blobs, nhưng vẫn cần quản lý metadata, permissions, versioning và lifecycle.

Không phải mọi blob đều phải ở object storage: với file nhỏ cần transaction atomic cùng một bản ghi, lựa chọn có thể khác. Hãy cân nhắc size, lưu lượng và semantics.

### 11.2. Chi phí ẩn

- Storage class và dung lượng.
- Request PUT/GET/LIST.
- Data retrieval từ archival tier.
- Egress/CDN và inter-region transfer.
- Replication và versioning.
- Lifecycle rules, retention locks và delete policies.
- Quét malware, xử lý metadata và quyền truy cập presigned URL.

Giá mỗi GB thấp không nghĩa tổng chi phí thấp khi đối tượng được đọc rất nhiều qua mạng hoặc cần khôi phục khẩn cấp.

### 11.3. Bảo mật

Không dùng object key khó đoán thay cho authorization. Presigned URL cần TTL và phạm vi tối thiểu; tránh ghi URL có token vào logs. Nếu lưu dữ liệu nhạy cảm, cần encryption, access audit, retention và quyền xóa phù hợp pháp lý.

## 12. Graph database: truy vấn quan hệ nhiều bước

Đại diện: Neo4j và graph-oriented systems.

Các use case:

- Đường quan hệ giữa tài khoản, thiết bị, giao dịch để phát hiện gian lận.
- Hệ thống gợi ý dựa trên mạng liên kết.
- Knowledge graph, dependency graph.
- Tìm đường đi hoặc liên kết nhiều bước.

**Lợi ích:** khi truy vấn chủ yếu là traversal phức tạp qua các quan hệ, một graph model có thể tự nhiên và hiệu quả hơn việc viết nhiều join lặp lại theo từng use case.

**Trade-offs:** thêm hệ công nghệ, ngôn ngữ truy vấn, quản trị dữ liệu, điều kiện partitioning và chi phí vận hành. Nếu quan hệ chỉ gồm vài bảng với join đơn giản, relational DB thường đủ.

Không nên chọn graph chỉ vì có foreign keys; hãy dựa trên độ sâu traversal, query latency và nhu cầu mô hình hóa quan hệ thật.

## 13. Analytical / OLAP storage và data warehouse

Đại diện: ClickHouse, BigQuery, Snowflake và các engine columnar/analytics phù hợp.

### 13.1. OLTP khác OLAP

| Khía cạnh | OLTP | OLAP |
| --- | --- | --- |
| Mục đích | Giao dịch ngắn, cập nhật từng entity | Phân tích, tổng hợp tập dữ liệu lớn |
| Query | Lookup, write, transaction | Scan, group by, join dữ liệu lớn, historical analysis |
| Tính đúng đắn | Transaction và ràng buộc nghiệp vụ | Snapshot, data freshness và transformation correctness |
| Latency | Thường nhắm tới request tương tác | Có thể chấp nhận query dài hơn tùy báo cáo |
| Mô hình | Normalized/aggregate theo use case | Star schema, wide table, columnar, materialized views |

Một hệ giao dịch có thể cung cấp báo cáo đơn giản; một warehouse có thể ghi dữ liệu, nhưng không nên tự động coi hai mục đích là giống nhau.

### 13.2. Tách analytics để bảo vệ transactional path

Nếu đội báo cáo chạy truy vấn toàn bộ lịch sử đơn liên tục trên database phục vụ checkout, CPU và I/O có thể ảnh hưởng luồng người dùng. Có thể dùng replication/ETL/CDC sang analytical store.

Cần xác định:

- Độ trễ dữ liệu báo cáo chấp nhận được.
- Cách replay và xử lý late/out-of-order events.
- Quy tắc định nghĩa số liệu (gross/net/refund).
- Chất lượng dữ liệu, dedup và schema evolution.
- Chi phí ingest, storage và query scanning.
- Chính sách bảo mật vì warehouse thường tổng hợp nhiều dữ liệu nhạy cảm.

Dữ liệu warehouse là nền tảng ra quyết định, nhưng kết quả thanh toán lúc checkout vẫn phải xác nhận ở owner của payment/order.

## 14. Vector search và embeddings: nhu cầu chuyên biệt

Khi cần semantic search hoặc retrieval-augmented generation, có thể lưu embedding và tìm nearest neighbors bằng:

- Extension vector trong relational database.
- Vector capability của search engine hiện có.
- Một vector database/service riêng nếu workload, quy mô hoặc tính năng thực sự đòi hỏi.

Chi phí không chỉ là nơi lưu vectors mà còn gồm tạo embeddings, cập nhật mô hình, reindexing, metadata filtering, latency, memory/index size và quyền truy cập dữ liệu.

**Đừng triển khai thêm vector DB chỉ vì dự án có AI.** Với bộ dữ liệu vừa phải và team đã vận hành PostgreSQL, thử extension trước có thể đơn giản hơn. Ngược lại, nếu phải quản lý số lượng embedding rất lớn với SLA truy vấn đặc biệt, công nghệ chuyên biệt có thể hợp lý sau khi benchmark.

## 15. Event log và message broker có phải database không?

Kafka hoặc message log có thể lưu sự kiện với retention và replay theo cấu hình, đôi khi phục vụ event sourcing. Nhưng **message broker không mặc nhiên thay thế cơ sở dữ liệu truy vấn nghiệp vụ**.

Một broker được tối ưu cho append, phân phối và consumption theo partition/offset. Để hỏi “trạng thái đơn hàng 8421 hiện tại là gì?”, thường cần:

- Materialized view/read model.
- Event-sourced aggregate được tái dựng và có snapshot.
- Một service state store có contract riêng.

Nếu dùng event sourcing, dữ liệu sự kiện trở thành source of truth theo mô hình đó và đòi hỏi:

- Event schema/version ổn định.
- Thứ tự theo aggregate.
- Replay/snapshot.
- Invariant và concurrency.
- Retention/khả năng xóa dữ liệu theo pháp lý.
- Khả năng đối chiếu external effects.

Đừng gọi mọi hệ dùng Kafka là event-sourced hay hứa broker tự bảo đảm exactly-once end-to-end.

## 16. Một ma trận chọn loại lưu trữ theo workload

| Nhu cầu trội | Ứng viên nên đánh giá | Điểm cần xác minh |
| --- | --- | --- |
| Transaction nhiều bảng, ràng buộc mạnh | Relational DB | ACID, indexes, locking, scaling write |
| Aggregate JSON linh hoạt | Document DB hoặc JSON trong relational | Size, query, index, consistency |
| Lookup key/TTL, cache | Key-value store | Persistence, eviction, hot keys |
| Ghi cực lớn theo partition | Wide-column/distributed key-based | Partition design, consistency, ops |
| Full-text, fuzzy, ranking | Search index hoặc DB full-text | Reindex, freshness, search relevance |
| Metrics/timestamp + retention | Time-series store | Cardinality, downsampling, compression |
| File/ảnh/video/archive | Object storage | Metadata, IAM, egress, retrieval |
| Quan hệ nhiều bước | Graph DB hoặc SQL | Traversal cost, model complexity |
| Báo cáo/scan lớn | OLAP/warehouse | Freshness, query cost, governance |
| Vector similarity | Vector extension/search/vector DB | Index/update cost, metadata security |
| Replay sự kiện | Log/broker + state model | Retention, ordering, business source of truth |

Ma trận là danh sách **ứng viên**, không phải chỉ định chắc chắn. Một hệ RDBMS có thể xử lý nhiều use case trong bảng; tránh “polyglot persistence” khi chưa có bằng chứng cần thêm công nghệ.

## 17. Các thuộc tính chất lượng phải định lượng

### 17.1. Consistency và transactions

Cần hỏi dữ liệu nào phải thống nhất ngay trong một transaction, dữ liệu nào có thể eventual consistency.

Ví dụ:

- Order lines và order total có thể cần được lưu nhất quán trong một transaction Order.
- Search index có thể trễ vài giây sau khi Catalog cập nhật nếu sản phẩm cho phép.
- Payment trạng thái cuối cần xác minh theo owner; không thể dùng cached status cũ để kết luận tiền chưa thu.
- Analytics dashboard có thể có freshness target vài phút/giờ tùy quyết định nghiệp vụ.

Không nên chia nhỏ một invariant chặt thành nhiều service chỉ để mỗi service dùng database khác nhau. Khi một bất biến cần giao dịch chung thường xuyên, hãy đánh giá lại **bounded context và ranh giới service**.

### 17.2. Latency p95/p99 và access patterns

Một database thường được quảng bá “rất nhanh” với một loại query cụ thể. Nhưng ứng dụng có thể cần:

- Lookup theo một partition key.
- Tìm 100 đơn mới nhất theo customerId.
- Lọc theo nhiều trường và sort.
- Thực hiện transaction cập nhật cùng lúc nhiều bản ghi.
- Báo cáo tổng hợp 100 triệu dòng.
- Tìm kiếm ngữ nghĩa hoặc full-text.

Chỉ benchmark đúng query, distribution, index và hardware/managed tier mới có ý nghĩa. Đo cả p95/p99 ở mức concurrency và dữ liệu dự kiến, không chỉ thời gian một query trong môi trường trống.

### 17.3. Durability, RPO và RTO

**RPO (Recovery Point Objective)** mô tả mức mất dữ liệu tối đa chấp nhận sau sự cố. **RTO (Recovery Time Objective)** mô tả thời gian mong muốn để khôi phục khả năng vận hành.

Một dịch vụ payment có thể đòi hỏi mức mất dữ liệu cực thấp và audit rõ, trong khi cache có thể tái tạo từ primary store. Chi phí replication, backup frequency, WAL/PITR, snapshot và restore drills phải gắn với RPO/RTO từng loại dữ liệu.

“Có backup” chưa đủ. Phải kiểm tra **khôi phục được, trong bao lâu, đến thời điểm nào**, và ai có quyền thực hiện.

### 17.4. Availability và distributed trade-offs

Multi-AZ, multi-region replication, failover và quorum có thể cải thiện availability nhưng cũng tăng chi phí và độ phức tạp. Lựa chọn strong consistency có thể phải đánh đổi latency hoặc availability khi network partition tùy hệ thống và cấu hình.

Không nên giản lược rằng “SQL luôn consistent, NoSQL luôn eventually consistent”. Mỗi sản phẩm có contract riêng và nhiều lựa chọn consistency/transaction. Cần đọc tài liệu đúng phiên bản và kiểm chứng trong failure conditions.

## 18. Chi phí: đừng chỉ so sánh giá một GB

**TCO (Total Cost of Ownership)** gồm chi phí tài nguyên trực tiếp và tổng công sức để hệ thống hoạt động đáng tin cậy suốt vòng đời.

Một mô hình tính chi phí hàng tháng:

~~~text
Monthly TCO ≈
  Compute / provisioned capacity
+ Data storage + indexes + replicas
+ Backup + PITR + archival + restore
+ Read/write/query/request charges
+ Network and cross-region egress
+ Monitoring, logging and security
+ License/support
+ Engineering/on-call time
+ Migration and incident costs (ước lượng phân bổ)
~~~

Công thức chỉ là khung để so sánh, không phải báo giá của nhà cung cấp. Đơn giá thay đổi theo khu vực, mức dịch vụ, gói commit, workload và chính sách.

### 18.1. Chi phí hạ tầng trực tiếp

Cần xem:

- Node/instance size hoặc serverless capacity units.
- Provisioned IOPS, throughput và storage tiers.
- Read/write request hoặc consumed units.
- Index storage, materialized views và replicas.
- Backup snapshot, transaction log retention, cross-region copies.
- Data transfer giữa AZ, region và ra internet.
- Restore/recovery operations và data retrieval từ cold storage.
- Peak capacity: cần trả cho 24/7 hay trả theo tiêu thụ?

Ví dụ một hệ được tính phí theo request có thể có chi phí thấp khi traffic biến động ít, nhưng cao khi truy vấn phát sinh hàng tỷ reads nhỏ. Một hệ provisioned có thể ổn định khi tải cao nhưng tốn phí khi thường xuyên nhàn rỗi.

### 18.2. Chi phí nhân sự vận hành

Self-hosted cluster có thể tiết kiệm một phần phí dịch vụ nhưng tiêu tốn:

- Setup, nâng cấp, kiểm thử compatibility.
- Replication, failover, backup, restore.
- Patch bảo mật, rotation secrets, encryption keys.
- Tuning query/index, memory, compaction.
- Capacity planning, monitoring, alerting.
- Trực sự cố, điều tra data corruption và khôi phục.
- Runbook, disaster recovery drills, audit.

Đội 4 người với một database quen thuộc có thể triển khai tính năng nhanh hơn nhiều so với 4 hệ lưu trữ độc lập, dù giá cloud trên giấy của một hệ mới thấp hơn.

### 18.3. Chi phí độ phức tạp và rủi ro

Một nền tảng mới tạo thêm dependency cho release, security review, compliance, training và tuyển dụng. Mỗi hệ thêm một vòng đời schema, backup, monitoring và incident response.

Nếu search index hoặc cache chỉ giảm latency 10 ms nhưng cần cả một cluster mới cùng nhiều giờ on-call mỗi tuần, phải chứng minh lợi ích nghiệp vụ đủ lớn.

### 18.4. Công thức so sánh chi phí theo đơn vị nghiệp vụ

Bên cạnh tổng hóa đơn cloud, có thể dùng:

~~~text
Cost per 1,000 successful orders =
    monthly storage-related total cost
    / monthly successful orders
    × 1,000
~~~

Hoặc cost per million events ingested, cost per TB retained/month, cost per report completed. Những chỉ số này giúp so sánh khi sản phẩm mở rộng, nhưng phải tính **đúng phần chi phí được phân bổ** và không dùng tỷ lệ để che giấu sự cố reliability.

## 19. Ví dụ TCO minh họa: chọn hệ nào không chỉ vì giá trên bảng

Giả định ba phương án quản lý dữ liệu đơn hàng trong một sản phẩm mới:

- **A:** Managed PostgreSQL.
- **B:** Self-hosted distributed database.
- **C:** Managed document database.

Mọi con số dưới đây là **đơn vị điểm chi phí minh họa**, không phải giá dịch vụ thực tế:

| Hạng mục (điểm/tháng) | A | B | C |
| --- | ---: | ---: | ---: |
| Compute và storage | 30 | 20 | 40 |
| Backup/monitoring/network | 10 | 20 | 15 |
| Công sức vận hành quy đổi | 10 | 45 | 20 |
| Chi phí phát triển/migration quy đổi | 5 | 25 | 15 |
| **Tổng giả định** | **55** | **110** | **90** |

Nếu chỉ so compute, B trông rẻ nhất. Khi tính thêm khôi phục, trực sự cố, training và migration, A lại có tổng chi phí thấp hơn trong giả định này.

Điều này không có nghĩa managed PostgreSQL luôn rẻ nhất. Nếu workload thay đổi thành ghi dữ liệu cực lớn, thiếu join và phân vùng tốt, một distributed database có thể thắng ở một quy mô cụ thể. Bài học là **cần cùng cách tính và cùng giả định** trước khi so.

### 19.1. Tính trên ba kịch bản

Nên dựng các kịch bản:

- **Base:** traffic và data growth thực tế có khả năng cao.
- **Peak:** tải cao điểm, marketing campaign, batch import hoặc sự cố cache.
- **Growth:** 12–24 tháng khi số tenant, dữ liệu và query tăng.

Đối với mỗi kịch bản, đo cost, p95/p99, error rate, quota, nhu cầu người vận hành và phương án scaling. Không tự coi dự báo tăng trưởng là chắc chắn; đánh dấu giả định và ngưỡng cần xem lại.

## 20. Managed service hay tự vận hành?

### 20.1. Khi managed service thường hợp lý

- Team nhỏ, muốn tập trung business features.
- Cần backup, patching, replication, monitoring hoặc failover được quản lý.
- Chưa có người chuyên DBA/SRE cho hệ dữ liệu phức tạp.
- Ưu tiên thời gian ra mắt và kiểm soát rủi ro vận hành.

Managed không có nghĩa nhà cung cấp chịu mọi trách nhiệm. Team vẫn phải thiết kế schema, indexes, query, IAM, backup policies, DR runbook, chọn tier và kiểm soát chi phí.

### 20.2. Khi self-host có thể hợp lý

- Có chuyên môn vận hành đủ sâu.
- Yêu cầu triển khai on-premises/air-gapped hoặc kiểm soát đặc biệt.
- Workload ổn định, lớn và economics chứng minh lợi ích.
- Có tooling, automation, hỗ trợ, on-call và diễn tập khôi phục.
- Chi phí migration/lock-in và compliance đã được cân nhắc.

Không nên chỉ so giá instance raw với giá managed rồi kết luận self-host rẻ hơn. Phải tính cả nhân sự, SLA, backup, thời gian khôi phục, nâng cấp và chi phí cơ hội.

### 20.3. Vendor lock-in có phải luôn xấu?

Vendor lock-in là một chi phí/chấp nhận rủi ro, không tự động là sai. Một dịch vụ cloud chuyên biệt có thể giúp ra mắt nhanh, giảm vận hành và đáp ứng tốt yêu cầu. Nên xác định mức phụ thuộc:

- API/query language riêng.
- Format export/import và tốc độ chuyển dữ liệu.
- Tính năng consistency, index, backup và IAM độc quyền.
- Kịch bản nhà cung cấp thay đổi giá, quota hoặc region.
- Khả năng kiểm thử một phương án thay thế.

Không cần xây abstraction quá lớn “database agnostic” ngay từ đầu nếu nó làm mất tính năng cốt lõi. Thay vào đó, giữ **domain/API contract độc lập** với chi tiết lưu trữ, tài liệu hóa quyết định và đường migration có thể thực thi.

## 21. Ma trận quyết định có trọng số

Khi có nhiều ứng viên, ma trận giúp thảo luận minh bạch. Chọn tiêu chí theo ngữ cảnh; ví dụ một Order Service:

| Tiêu chí | Trọng số |
| --- | ---: |
| Transaction và data correctness | 30% |
| Phù hợp query/access patterns | 25% |
| Năng lực team và chi phí vận hành | 20% |
| Khả năng mở rộng trong dự báo | 15% |
| Chi phí trực tiếp | 10% |
| **Tổng** | **100%** |

Giả định chấm 1 = kém phù hợp, 5 = rất phù hợp:

| Ứng viên | Correctness | Query fit | Operations | Scale fit | Direct cost | Điểm quy đổi |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Managed relational | 5 | 5 | 4 | 4 | 4 | 4,55 |
| Managed document | 3 | 4 | 3 | 4 | 3 | 3,40 |
| Managed key-value | 2 | 2 | 4 | 5 | 4 | 3,05 |

Điểm tính theo tổng (trọng số × điểm) / 100. Các điểm số là **ví dụ giả định**, không phải benchmark hoặc đánh giá chung cho mọi sản phẩm.

Cách dùng đúng:

1. Chốt các tiêu chí **hard constraints** trước. Một ứng viên không đáp ứng data residency hoặc business transaction bắt buộc phải bị loại dù điểm tổng cao.
2. Có bằng chứng benchmark/POC cho điểm số quan trọng.
3. Ghi người đưa ra giả định và mức bất định.
4. Kiểm tra độ nhạy: nếu tăng trọng số scaling, kết quả có đổi không?
5. Không để điểm số thay thế quyết định kỹ thuật trong bối cảnh thật.

### 21.1. Hard constraints và soft preferences

**Hard constraints**: phải đáp ứng, ví dụ vùng lưu dữ liệu bắt buộc, encryption, thời gian khôi phục tối đa, unique transaction/invariant không thể bỏ.

**Soft preferences**: mong muốn như truy vấn thuận tiện hơn, service managed, ecosystem nhiều công cụ, chi phí cloud dự báo thấp.

Một database điểm cao nhưng không đáp ứng hard constraint thì không thể chọn chỉ vì có nhiều tính năng hấp dẫn.

## 22. Case study 1: thương mại điện tử quy mô nhỏ

**Bối cảnh giả định:**

- 6 kỹ sư backend.
- Dự kiến ra mắt trong 3 tháng.
- Catalog khoảng 20.000 sản phẩm, đơn hàng tăng dần.
- Checkout cần transaction đúng, idempotency và đối soát.
- Search có thể bắt đầu từ lọc cơ bản.
- Ảnh sản phẩm được đọc nhiều nhưng ít thay đổi.
- Chi phí on-call và thời gian ra mắt là yếu tố quan trọng.

### 22.1. Phương án ban đầu

| Nhu cầu | Lựa chọn ban đầu gợi ý | Lý do |
| --- | --- | --- |
| Order, payment intent, inventory ledger | Managed PostgreSQL hoặc relational tương đương | Transaction, constraints, team quen |
| Catalog metadata | Relational tables/JSON khi hợp lý | Chưa chứng minh cần document cluster riêng |
| Ảnh sản phẩm | Object storage + CDN | Tránh nhồi binary vào OLTP |
| Tìm kiếm cơ bản | Index/full-text trong DB | Tránh search cluster quá sớm |
| Session/cache | Chưa cần nếu DB đủ đáp ứng; thêm key-value khi có số liệu | Giảm một hệ vận hành |
| Analytics | Báo cáo nhẹ/read replica hoặc pipeline đơn giản | Chỉ tách warehouse khi query ảnh hưởng OLTP |

Ưu tiên một số ít hệ lưu trữ đội hiểu sâu, dữ liệu thuộc đúng owner, quyền truy cập tách biệt và backup/restore được kiểm thử.

### 22.2. Khi nào xem xét thay đổi?

- Query search cần fuzzy relevance/phân tích facet phức tạp mà DB không đáp ứng SLO.
- Cache miss/hot read gây tải DB vượt ngưỡng, đã tối ưu index và query.
- Analytics scan làm giảm p95 checkout dù đã tách/giới hạn.
- Khối lượng telemetry tăng mạnh và retention policy không còn hiệu quả.
- Dữ liệu hoặc số lượng tenant tăng khiến partition strategy hiện tại trở thành bottleneck.
- RTO/RPO hoặc region requirements thay đổi.

**Không nên đổi kiến trúc chỉ vì số lượng người dùng tăng một ngưỡng tùy tiện.** Hãy đo bottleneck và xây thử phương án thay thế trước.

## 23. Case study 2: nền tảng thu thập sự kiện khối lượng lớn

**Bối cảnh giả định:**

- Hàng triệu sự kiện/ngày từ thiết bị.
- Mỗi sự kiện có timestamp, deviceId và metrics.
- Write-heavy, ít cập nhật bản ghi cũ.
- Nhiều truy vấn time-range và aggregation.
- Raw data có thời hạn giữ, dữ liệu tổng hợp giữ lâu hơn.
- Một phần dữ liệu cần đưa về warehouse để phân tích.

### 23.1. Thiết kế ứng viên

~~~mermaid
flowchart LR
    D["Devices"] --> I["Ingestion API"]
    I --> Q[("Event Stream")]
    Q --> T[("Time-Series Store")]
    Q --> O[("Object Archive")]
    O --> A[("Analytics Engine")]
    M["Metadata Service"] --> R[("Relational DB")]
~~~

Lựa chọn này phân tách:

- Device metadata cần identity, policy và transaction.
- Telemetry cần ingestion throughput và time-window queries.
- Archive cần lưu trữ lâu, nén/lifecycle.
- Analytics cần scan và aggregation quy mô lớn.

Không nhất thiết dùng đúng bốn engine; có thể chọn hệ hỗ trợ nhiều workload hoặc đơn giản hóa theo quy mô. Cần chứng minh hiệu quả qua benchmark và TCO.

### 23.2. Các quyết định không được bỏ qua

- Partition theo device/time bucket để tránh hot partition.
- Retention và downsampling, tránh lưu raw vô hạn.
- Backpressure khi consumer chậm, tránh queue không giới hạn.
- Dedup eventId nếu producer retry.
- Xử lý event tới muộn hoặc out-of-order.
- Schema registry/evolution.
- Quyền truy cập dữ liệu của từng tenant.
- Recovery từ event log/archive khi read store cần dựng lại.

Nếu số lượng sự kiện cực lớn nhưng dùng nhiều index không cần thiết trong một OLTP DB, chi phí có thể tăng không tỷ lệ với giá trị dữ liệu.

## 24. Case study 3: B2B SaaS nhiều tenant

**Bối cảnh giả định:** một sản phẩm SaaS có vài trăm doanh nghiệp, mỗi tenant có dữ liệu riêng, một số khách yêu cầu region cụ thể hoặc xóa dữ liệu theo hợp đồng.

### 24.1. Mô hình tenancy

Các mô hình thường gặp:

- Shared database, shared schema, có tenant_id và row-level access controls.
- Shared database, schema tách theo tenant.
- Database tách theo tenant trên hạ tầng shared.
- Infrastructure tách biệt cho tenant cần isolation cao.

Không có mô hình nào thắng tuyệt đối. So sánh:

| Tiêu chí | Shared schema | Separate schema/DB | Dedicated infrastructure |
| --- | --- | --- | --- |
| Chi phí cho nhiều tenant nhỏ | Có thể thấp | Tăng theo lượng phân tách | Thường cao |
| Isolation | Phụ thuộc RLS/app controls | Phân tách mạnh hơn ở một số mặt | Mạnh hơn nếu cấu hình đúng |
| Migration | Một schema nhưng phải tính tenant logic | Nhiều schema/DB cần orchestration | Nhiều deployment |
| Backup/restore từng tenant | Có thể phức tạp | Dễ hơn tùy topology | Tách biệt hơn |
| Data residency | Phụ thuộc phân vùng triển khai | Có thể gán DB/region | Tùy khu vực dedicated |
| Noisy neighbor | Cần quota/limiter | Có thể cô lập tốt hơn | Có thể cô lập mạnh nhất |

RLS hoặc tenant filter phải được test chống lộ dữ liệu xuyên tenant, không chỉ tin tưởng rằng developer nhớ WHERE tenant_id. Kế hoạch restore/xóa dữ liệu của một tenant cần xem cả backup, cache, search index và warehouse.

### 24.2. Quyền sở hữu không bị xóa bởi tenancy

Tenant isolation là một chiều khác với service data ownership. Order Service vẫn sở hữu đơn của mọi tenant, còn các chính sách phân tách tenant quyết định mức isolation trong store.

## 25. Khi thêm cache hoặc search index: chiến lược đồng bộ

Một câu hỏi lớn trong polyglot storage là **làm sao giữ dữ liệu dẫn xuất đủ mới và có thể phục hồi?**

Ví dụ Catalog lưu primary data trong PostgreSQL, tạo search index và Redis cache. Nếu cập nhật primary DB thành công nhưng cập nhật search thất bại, dữ liệu sẽ lệch.

### 25.1. Tránh dual-write không an toàn

~~~text
UPDATE products trong DB -> COMMIT
Gọi Search API để reindex
Process crash ở giữa
~~~

Nếu không có cơ chế retry bền vững, index có thể không bao giờ cập nhật. Giải pháp thường dùng:

- Transactional Outbox ghi business change + event trong một DB transaction.
- Publisher/CDC phát event.
- Consumer cập nhật search index idempotent.
- Theo dõi lag và có rebuild process.

### 25.2. Cache invalidation

Cache có thể dùng TTL, explicit invalidation, versioned keys hoặc write-through/write-behind tùy semantics. Cần chọn dựa trên:

- Độ trễ dữ liệu chấp nhận.
- Hệ quả nếu cache trả dữ liệu cũ.
- Mức tải và cache hit ratio.
- Khả năng cache stampede/hot keys.
- Chi phí rebuild và memory.

Nếu giữ số lượng hàng có thể bán trong cache mà không xác minh ràng buộc tại owner của Inventory, client có thể thấy sai kết quả. Cache nên hỗ trợ hiển thị/giảm tải, còn quyết định giữ hàng phải thuộc service bảo vệ invariant.

## 26. Thiết kế data access không bị trói vào hệ lưu trữ

Mô hình domain không nhất thiết phải phản ánh trực tiếp schema database.

Một tổ chức có thể dùng phân tách:

~~~text
Application / Domain
    -> Repository interface / Port
        -> PostgreSQL adapter
        -> Search/read-model adapter
        -> Object storage adapter
~~~

Mục đích là **đặt business rules ở đúng service**, hạn chế SQL/SDK lan vào mọi nơi. Tuy nhiên, không cần dựng abstraction giả định mọi database giống nhau. Transaction, query semantics, consistency và indexing của từng hệ rất khác.

**Thực tế tốt:** interface phản ánh use cases và invariants của domain. Ví dụ loadOrderForUpdate(orderId), reserveInventory(operationId, lines) có nghĩa hơn một abstraction CRUD chung cố che giấu transaction boundary.

### 26.1. Đừng thiết kế một transaction giả xuyên nhiều adapter

Nếu service cập nhật PostgreSQL rồi Search Index, gọi hai repository liên tiếp không làm chúng atomic. Cần ghi outbox, xử lý projection bất đồng bộ hoặc một cơ chế cụ thể khác. Lớp interface không tự tạo distributed transaction.

## 27. Di chuyển dữ liệu và thay đổi loại lưu trữ

Migrating storage là một dự án kiến trúc, không chỉ là dump/import dữ liệu.

### 27.1. Kế hoạch theo các giai đoạn

1. **Xác định mục tiêu:** query nào không đáp ứng, chi phí nào cần giảm, SLA nào phải đạt?
2. **Khảo sát dữ liệu:** schema, constraints, row counts, size, PII, retention, duplicate/dirty records.
3. **Thiết kế target model:** partition/index/primary key, consistency, backup, access patterns.
4. **Xây phương án migration:** snapshot/backfill, incremental CDC/event sync hoặc maintenance window.
5. **Shadow reads/dual observations:** so kết quả target và source trong môi trường kiểm soát.
6. **Consistency verification:** row counts, checksums, sample queries, business invariants.
7. **Cutover plan:** routing, feature flags, freeze window, handling writes đang diễn ra.
8. **Rollback plan:** quay lại nguồn cũ nếu target lỗi, tránh conflict dữ liệu phát sinh sau cutover.
9. **Monitoring:** latency, errors, mismatch, replication lag, cost.
10. **Decommission:** chỉ xóa nguồn cũ sau khi đã xử lý retention, audit, backup và recovery.

### 27.2. Dual-write có rủi ro

Nếu ứng dụng ghi đồng thời vào cả database cũ và mới mà không có transaction chung, một lần ghi có thể thành công ở một bên, thất bại ở bên kia. Cần chọn cách đồng bộ có recovery rõ: outbox/CDC hoặc một cơ chế giao dịch đáng tin, không dựa vào việc “hai call thường đều trả 200”.

### 27.3. Expand-contract cho schema migration

Với thay đổi schema trong một database:

- Expand: thêm field/table/index mới tương thích với code cũ.
- Deploy code có thể đọc/ghi theo giai đoạn.
- Backfill dữ liệu có kiểm soát.
- Chuyển các reader và writer sang cấu trúc mới.
- Contract: bỏ field/cấu trúc cũ sau khi không còn phụ thuộc.

Phải tính phiên bản dịch vụ chạy song song, queue có event cũ, rollback và migration dài. Một schema có thể được nâng cấp trong phút, nhưng dữ liệu hàng tỷ record có thể cần nhiều giờ hoặc ngày để backfill.

## 28. Backup, restore và disaster recovery là phần của quyết định

Một database dễ deploy nhưng không khôi phục được dữ liệu khi lỗi không phải lựa chọn hợp lý cho nghiệp vụ quan trọng.

### 28.1. Checklist về khôi phục

- [ ] Backup tự động theo RPO yêu cầu.
- [ ] Có khả năng point-in-time recovery khi cần và sản phẩm hỗ trợ.
- [ ] Backup được mã hóa và phân quyền riêng.
- [ ] Có retention, legal hold và quy tắc xóa phù hợp.
- [ ] Đã diễn tập restore trên môi trường kiểm soát.
- [ ] Biết thời gian khôi phục thực tế để so với RTO.
- [ ] Có kế hoạch failover, DNS/application reconnect và data consistency sau failover.
- [ ] Đã kiểm tra restore cả object storage, search index và metadata liên quan.
- [ ] Có runbook và người chịu trách nhiệm.

### 28.2. Replication không thay thế backup

Replication có thể sao chép cả một lệnh xóa nhầm hoặc dữ liệu bị ghi sai sang replicas. Backup/versioning và restore test giải quyết loại rủi ro khác. Replication tăng khả năng sẵn sàng trong một số sự cố; backup hỗ trợ phục hồi dữ liệu bị hỏng/xóa theo thời điểm.

### 28.3. RPO/RTO cần phù hợp loại dữ liệu

Cache có thể tái tạo. Search index có thể reindex, nhưng mất nhiều giờ. Payment ledger cần độ bền, audit và đối soát rất nghiêm ngặt. Một chính sách backup duy nhất cho mọi store có thể vừa tốn chi phí, vừa không đáp ứng yêu cầu quan trọng.

## 29. Security, privacy và governance

Storage decision còn liên quan:

- Encryption at rest và in transit.
- IAM, service identities, least privilege.
- Audit logs và data access monitoring.
- Data residency và cross-border transfer.
- Tenant isolation và row-level security.
- Key management/rotation.
- Data retention, archival và deletion policy.
- Masking/tokenization/pseudonymization cho dữ liệu nhạy cảm.
- Access review, incident response và forensics.

### 29.1. Quyền sở hữu dữ liệu phải tương ứng quyền kỹ thuật

Nếu chỉ Payment Service có quyền ghi bảng payment, các service khác không được dùng chung tài khoản admin. Khi chia sẻ cluster, nên dùng database users/roles/schema privileges rõ, không cho mỗi service đọc/sửa mọi bảng.

### 29.2. Dữ liệu dẫn xuất cũng là dữ liệu cần bảo vệ

Search index, logs, cache, analytics và backups có thể chứa PII. Chuyển source data sang warehouse hoặc index không làm mất trách nhiệm xóa/hạn chế quyền theo pháp lý.

Ví dụ khi xóa dữ liệu cá nhân, cần có cơ chế xóa hoặc ẩn ở primary store, các bản sao/read models và chính sách xử lý backup theo luật/contract.

### 29.3. Chống rò thông tin giữa tenant

Trong multi-tenant system, cache key phải có tenant scope khi cần; search queries phải lọc authorization; object keys và signed URLs không được thay auth. Một ràng buộc dữ liệu sai có thể lộ dữ liệu ngay cả khi hệ database được chọn đúng loại.

## 30. Những anti-pattern thường gặp

**1. Chọn database theo xu hướng.**  
“Dùng NoSQL vì microservices” hoặc “dùng vector DB vì có AI” không phải yêu cầu kỹ thuật. Phải bắt đầu từ workload và bằng chứng.

**2. Một microservice bắt buộc có một database server riêng.**  
Ownership logic có thể tách trên hạ tầng dùng chung với quyền và schema rõ. Tách vật lý khi có yêu cầu về isolation, scaling hoặc reliability.

**3. Mọi service đọc thẳng DB của nhau.**  
Tạo coupling schema và phá vỡ khả năng thay đổi owner. Dùng public/internal API hoặc event contract.

**4. Coi cache là source of truth của tiền hoặc tồn kho.**  
Cache có TTL/eviction/staleness; invariant nghiệp vụ cần cơ chế đúng ở owner.

**5. Dùng search index để xác nhận checkout.**  
Search projection có thể trễ. Phải xác minh dữ liệu quan trọng từ source of truth.

**6. Chọn store vì giá GB rẻ.**  
Tổng chi phí còn có requests, replication, egress, nhân sự, backup và query.

**7. Dùng distributed database chỉ để “scale sau này”.**  
Trước khi workload cần, chi phí complexity và cơ chế consistency có thể vượt lợi ích.

**8. Cố dùng relational cho mọi workload bất chấp số liệu.**  
Một OLTP DB có thể trở thành điểm nghẽn khi dùng làm warehouse, object storage và telemetry raw vô hạn.

**9. Không thiết kế partition key.**  
Wide-column/key-based store có thể hot spot, query scan rất tốn.

**10. Không quan tâm index và query plan.**  
Database mạnh không thể cứu các truy vấn thiếu index, N+1 hoặc tải không giới hạn.

**11. Dùng nhiều store nhưng không có ownership.**  
Không biết nơi nào có dữ liệu đúng, ai cập nhật index, ai xử lý stale cache.

**12. Dual-write không có recovery.**  
Business DB commit thành công nhưng index/broker lỗi dẫn tới dữ liệu lệch mãi mãi.

**13. Không thử restore.**  
Backup tồn tại nhưng không biết restore mất bao lâu, có đủ dữ liệu hay không.

**14. Không tính data retention.**  
Storage, index, backup tăng mãi; query chậm và hóa đơn cloud tăng.

**15. Bỏ qua quyền truy cập khi chuyển dữ liệu.**  
Read model/search/cache có thể lộ PII hoặc cross-tenant.

**16. Không tính cost of people.**  
Giải pháp tự vận hành có cloud bill thấp nhưng on-call và downtime rất đắt.

**17. Benchmark không đại diện.**  
Test 1.000 bản ghi, một client, không concurrency, không background load rồi suy ra sẽ đáp ứng 100 triệu record.

**18. Dựng abstraction database-agnostic phức tạp.**  
Lớp trừu tượng quá chung làm mất transaction, query semantics và performance lợi thế của engine.

**19. Không có plan rời công nghệ.**  
Vendor đổi giá hoặc workload đổi, migration thiếu dữ kiện và đường rollback.

**20. Tin rằng polyglot persistence luôn tốt.**  
Thêm engine chỉ nên khi lợi ích rõ hơn chi phí vận hành và đồng bộ dữ liệu.

## 31. Quy trình lựa chọn từng bước

### Bước 1 — Viết business invariants

Ví dụ: mỗi paymentId có tác dụng thu tiền không trùng; tổng số item của đơn hợp lệ; không giữ hàng vượt giới hạn.

Nếu một ứng viên không bảo vệ được các invariant bằng cơ chế phù hợp với năng lực nhóm, loại hoặc thiết kế bổ sung phải được chứng minh trước.

### Bước 2 — Liệt kê top access patterns

Ghi cụ thể:

- Query theo key nào?
- Có join/aggregation không?
- Tần suất và độ trễ mục tiêu?
- Dữ liệu cần nhất quán ngay không?
- Query ad hoc thường xuyên hay truy vấn định hình trước?

### Bước 3 — Ước lượng data volume và growth

Số record, kích thước trung bình, index overhead, retention, replication, peak writes và hot partitions.

### Bước 4 — Xác định hard constraints

Compliance, regions, encryption, RPO/RTO, consistency, SLA, data residency, ngân sách không thể vượt.

### Bước 5 — Chọn ít ứng viên

Thường đánh giá hệ đang vận hành trước, rồi 1–2 ứng viên chuyên biệt nếu có lý do. Không cần đưa mọi engine vào cuộc thi.

### Bước 6 — POC/benchmark đúng workload

Dựng data distribution, indexes, query patterns, concurrency, failures, backup/restore và cost measurement.

### Bước 7 — Tính TCO theo kịch bản

Base/peak/growth, cộng infrastructure + operator time + migration/incident risk.

### Bước 8 — Quyết định có thể giải thích

Ghi trade-offs, giả định, hard constraints, số liệu và vì sao không chọn các phương án khác.

### Bước 9 — Xây runbook trước production

Migrations, backups, restore, alerts, capacity, on-call, tenant security và recovery.

### Bước 10 — Đặt trigger xem lại

Ví dụ: p99 vượt SLO liên tiếp, chi phí mỗi triệu events tăng, backup restore vượt RTO, index growth quá dự tính hoặc đội không đủ vận hành.

## 32. Mẫu ADR cho quyết định lưu trữ

~~~markdown
# ADR-012: Chọn primary storage cho Order Service

Trạng thái: Accepted
Người sở hữu: Order Team
Ngày: YYYY-MM-DD

## Bối cảnh
- Mỗi order có header và nhiều line items.
- Cần transaction khi tạo đơn và cập nhật trạng thái.
- Query chính: theo orderId, customerId, ngày tạo.
- 6 engineers, yêu cầu ra mắt trong 3 tháng.
- RPO/RTO và data residency theo hợp đồng đã định.

## Các lựa chọn
1. Managed relational database
2. Managed document database
3. Distributed key-based database

## Quyết định
Dùng managed relational database làm primary store của Order.
Mỗi service sở hữu schema và quyền ghi riêng.
Object storage dành cho file lớn; search/cache chỉ thêm khi có số liệu.

## Lý do
- Transaction và uniqueness phù hợp invariants.
- SQL/index phục vụ access patterns.
- Team đã có kỹ năng và runbook.
- TCO base/growth đáp ứng giới hạn giả định.

## Hệ quả
- Cần index review và query performance monitoring.
- Cần backup/PITR/restore drills.
- Dùng outbox cho các event cần publish sau commit.
- Không cho service khác truy cập trực tiếp bảng Order.

## Không lựa chọn
- Document DB: chưa có lợi ích đủ lớn so với transaction/query hiện tại.
- Distributed key-based: chi phí model/ops chưa được bù bởi workload.

## Triggers xem lại
- p99 vượt SLO do bottleneck đã đo.
- Data growth phá vỡ partitioning/capacity.
- TCO tăng ngoài dự báo.
- Yêu cầu region/compliance thay đổi.
~~~

ADR nên ghi các giả định thật và kết quả benchmark; ví dụ chỉ minh họa cấu trúc.

## 33. Bài tập thực hành

### Bài tập 1 — Order Service

Một service ghi đơn hàng với nhiều dòng sản phẩm, cần transaction và tra cứu theo customerId. Đội có bốn kỹ sư, dữ liệu hiện 100.000 đơn, tăng khoảng 10% mỗi tháng.

Hãy chọn 2–3 ứng viên lưu trữ, nêu hard constraints và thiết kế thử nghiệm để chọn. Không sử dụng “NoSQL dễ scale” làm lập luận duy nhất.

### Bài tập 2 — Catalog nhiều thuộc tính

Catalog có nhiều loại sản phẩm với thuộc tính khác nhau. Hệ thống cần filter theo category, price và color, full-text search và cập nhật giá nhanh.

Hãy so sánh relational + JSON/full-text với document DB và search index riêng. Xác định nơi nào là source of truth và cách giữ giá checkout chính xác.

### Bài tập 3 — Log/telemetry

Một triệu thiết bị gửi metrics có timestamp. Dữ liệu raw chỉ cần 30 ngày, báo cáo tổng hợp giữ 2 năm. Truy vấn phổ biến là aggregation theo device group, time bucket.

Thiết kế partitioning, retention, downsampling, object archive và analytics path. Nêu cách tránh high cardinality và cost vượt dự tính.

### Bài tập 4 — Ước lượng TCO

Cho ba lựa chọn managed relational, managed document và self-hosted distributed. Dựng mô hình tính monthly cost gồm compute, storage, backup, egress, on-call, incident và migration. Tính ba scenario base/peak/growth bằng dữ liệu giả định do bạn tự định nghĩa.

Giải thích vì sao giá mỗi GB không đủ kết luận.

### Bài tập 5 — Thêm Redis cache

API GET /products/{id} bị read-heavy nhưng Catalog cần cập nhật tồn kho nhanh. Hãy thiết kế cache keys, TTL, invalidation, fallback khi cache unavailable và cách không dùng cached stock để quyết định reserve.

### Bài tập 6 — Chuyển sang search engine

Một catalog cần fuzzy search, autosuggest và facet. Hãy thiết kế outbox/CDC, idempotent consumer, full rebuild, lag SLO và việc xử lý search data stale khi cập nhật giá.

### Bài tập 7 — Multi-tenant SaaS

Chọn shared schema, separate schema/DB hoặc dedicated instances cho khách hàng có yêu cầu data residency, isolation và backup từng tenant. Ghi trade-offs về chi phí, migrations và cross-tenant security.

### Bài tập 8 — Migration rủi ro

Order DB chuyển engine trong khi không được phép mất đơn. Hãy thiết kế snapshot, backfill, CDC, validation, cutover, rollback, dual-write risk và ngày xác nhận có thể tắt nguồn cũ.

## 34. Câu hỏi tự kiểm tra kiến thức

1. Vì sao quyền sở hữu dữ liệu phải xác định trước việc chọn PostgreSQL, MongoDB hoặc Redis?
2. Database per service có bắt buộc mỗi service phải có server riêng không?
3. Access pattern nào khiến relational DB thường phù hợp với Order Service?
4. Document model giúp gì cho aggregate linh hoạt và trade-off của embedding là gì?
5. Khi nào key-value store phù hợp hơn relational queries?
6. Redis cache có thể thay payment ledger không? Vì sao?
7. Hot partition phát sinh khi nào trong wide-column/distributed store?
8. Vì sao search index thường không phải source of truth của giá thanh toán?
9. Time-series storage được lợi từ retention/downsampling ra sao?
10. Khi nào object storage phù hợp cho ảnh, tài liệu và archive?
11. Graph database có lợi ở workload nào?
12. OLTP khác OLAP ở mục tiêu và query patterns ra sao?
13. Vector search có buộc phải có một vector database riêng không?
14. Kafka log có tự trả trạng thái đơn hàng hiện tại không?
15. RPO khác RTO thế nào và làm sao chứng minh restore đạt mục tiêu?
16. Replication có thay thế backup không?
17. Những thành phần nào làm tổng TCO khác giá compute/storage?
18. Managed service có xóa hết trách nhiệm vận hành của team không?
19. Tại sao dữ liệu dẫn xuất cần cơ chế đồng bộ/outbox và rebuild?
20. Schema migration an toàn cần lưu ý những phiên bản dịch vụ chạy đồng thời nào?
21. Có thể dùng scoring matrix để bỏ qua hard constraints không?
22. Một workload đã có relational DB nên thêm search/cache ở điều kiện gì?
23. Tenant isolation ảnh hưởng lựa chọn storage và data governance thế nào?
24. Trong data migration, vì sao dual-write hai hệ độc lập có rủi ro?
25. Quyết định storage cần ghi các điều kiện xem lại nào?

## 35. Checklist trước khi chốt giải pháp

- [ ] Đã xác định service/bounded context sở hữu dữ liệu.
- [ ] Có danh sách business invariants và transaction boundaries.
- [ ] Đã mô tả top queries, read/write ratio, burst, dữ liệu và retention.
- [ ] Có SLO latency/throughput, RPO/RTO và consistency requirements.
- [ ] Có hard constraints về bảo mật, region, compliance và tenancy.
- [ ] Đã đánh giá relational store đang có trước khi thêm công nghệ mới.
- [ ] Đã xem transaction/index/partition limitations của từng ứng viên.
- [ ] Đã benchmark đúng data size và concurrency mục tiêu.
- [ ] Đã tính TCO bao gồm compute, requests, backup, network và nhân sự.
- [ ] Có kế hoạch managed/self-hosted, ownership on-call và runbook.
- [ ] Có backup policy và restore drill, không chỉ checkbox backup enabled.
- [ ] Đã phân biệt primary source of truth với cache/search/read models.
- [ ] Có outbox/CDC hoặc đồng bộ bền vững khi ghi dữ liệu dẫn xuất.
- [ ] Có thiết kế chống event trùng, sai thứ tự và replay khi cần.
- [ ] Có migration/cutover/rollback và schema evolution plan.
- [ ] Đã kiểm soát IAM, secret, encryption, audit, PII và tenant isolation.
- [ ] Có metrics cost per unit và resource saturation.
- [ ] Có trigger xem lại khi workload, compliance hoặc cost thay đổi.
- [ ] Đã ghi ADR giải thích lựa chọn, trade-offs và giới hạn.
- [ ] Không chọn polyglot persistence chỉ để theo xu hướng.

## 36. Kết luận

**Lựa chọn loại lưu trữ là quyết định về quyền sở hữu dữ liệu, mô hình truy cập, tính đúng đắn và chi phí vận hành; không chỉ là chọn một sản phẩm database.** Relational database có thể là nền tảng tốt cho transaction; document phù hợp với aggregate linh hoạt; key-value hỗ trợ lookup/cache; wide-column hữu ích cho một số workload phân tán lớn; search, time-series, graph, object và OLAP phục vụ những nhu cầu chuyên biệt. Nhưng mỗi hệ đều tạo thêm giới hạn, công việc đồng bộ dữ liệu và trách nhiệm vận hành.

Trong microservices, hãy bảo vệ source of truth và business invariants trước, đo workload thật và chọn **số lượng hệ lưu trữ tối thiểu đáp ứng yêu cầu**. Sau đó tính tổng chi phí bao gồm đội ngũ, backup, replication, query, network, incident và migration. Thêm công nghệ mới chỉ khi lợi ích được chứng minh vượt chi phí và có chiến lược khôi phục.

Một quyết định tốt không nhất thiết tồn tại mãi mãi. Nó có **lý do theo bối cảnh, bằng chứng, kế hoạch vận hành và ngưỡng xem lại**, giúp hệ thống tiến hóa theo nhu cầu và ngân sách thực tế thay vì chạy theo xu hướng.