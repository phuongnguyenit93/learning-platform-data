# Chọn kết hợp nhiều hệ khi lợi ích vượt chi phí phối hợp

## 1. Vấn đề đặt ra: một hệ không làm tốt mọi thứ, nhưng nhiều hệ không miễn phí

Một nền tảng thương mại điện tử ban đầu lưu toàn bộ dữ liệu trong MongoDB. Ứng dụng Java hỗ trợ:

- Ghi và cập nhật đơn hàng với điều kiện về trạng thái và phiên bản.
- Đọc đơn hàng theo khách, ngày và trạng thái.
- Tìm kiếm sản phẩm bằng từ khóa, gợi ý và xếp hạng.
- Hiển thị catalog có lượng truy cập rất cao.
- Lập báo cáo tổng hợp nhiều năm.
- Ghi sự kiện để đồng bộ các dịch vụ khác.

Ở quy mô nhỏ, một database có thể phục vụ khá tốt. Khi dữ liệu tăng, nhóm phát triển đề xuất:

~~~text
MongoDB       : đơn hàng có thẩm quyền
Redis         : cache catalog và kiểm soát truy cập tạm thời
Elasticsearch : tìm kiếm sản phẩm
Kafka         : phân phối thay đổi dữ liệu
Analytics DB  : tổng hợp báo cáo
~~~

Nhìn từ từng chức năng, sự phân công có vẻ hợp lý. Nhưng hệ thống mới đặt ra các câu hỏi khó:

- Nếu cập nhật giá trong MongoDB thành công nhưng Elasticsearch chưa cập nhật thì người dùng thấy giá nào?
- Khi Redis trả một bản ghi đã bị xóa hoặc thu hồi quyền, tầng nào chịu trách nhiệm ngăn lộ dữ liệu?
- Nếu Kafka consumer nhận cùng một sự kiện ba lần, có tạo ba lần hóa đơn không?
- Nếu cần restore MongoDB về hôm qua, offset Kafka và chỉ mục tìm kiếm phải xử lý thế nào?
- Một tính năng cần ba hệ cùng hoạt động: vậy availability thực tế có thấp hơn hệ trước không?
- Đội có đủ người vận hành, giám sát, nâng cấp, backup, quản lý schema và điều tra lỗi của cả năm hệ?
- Lợi ích về độ trễ, chi phí truy vấn và năng lực kinh doanh có **lớn hơn** chi phí phối hợp hay không?

Đó là bài toán **polyglot persistence**: chọn nhiều công nghệ lưu trữ cho các nhu cầu khác nhau, nhưng chỉ khi giá trị thu được lớn hơn độ phức tạp mới phát sinh.

Bài học **“Chọn kết hợp nhiều hệ khi lợi ích vượt chi phí phối hợp”** thuộc chương **“Đánh giá và lựa chọn”** của module **Database No SQL**. Trọng tâm không phải xếp hạng sản phẩm nào “tốt nhất”, mà là xây **phương pháp ra quyết định có bằng chứng, khả năng kiểm tra và kế hoạch rút lui**.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nhận diện nhu cầu thực sự đòi hỏi nhiều hệ lưu trữ, thay vì thêm công nghệ theo xu hướng.
2. Phân biệt **nguồn dữ liệu có thẩm quyền** với cache, search index, materialized view và kho phân tích.
3. Lập bản đồ workload, invariants, consistency, security, retention và SLO để đánh giá kiến trúc.
4. So sánh một engine đa năng, tính năng tích hợp, read model bổ sung và nhiều database chuyên dụng.
5. Lượng hóa lợi ích kinh doanh, độ trễ, throughput, chi phí tài nguyên và thời gian phát triển.
6. Tính **coordination tax**: CDC, event schema, replay, idempotency, reconciliation, vận hành, phục hồi và kiểm thử.
7. Thiết kế luồng ghi/đọc an toàn, tránh dual-write không nguyên tử.
8. Xác định semantics về freshness, thứ tự sự kiện, lỗi từng phần và degraded mode.
9. Xây kiến trúc Java có ranh giới domain, adapter và outbox rõ.
10. Đặt acceptance gates để quyết định thử nghiệm, mở rộng hay loại bỏ hệ mới.
11. Tránh các anti-pattern như “distributed join” đồng bộ trên đường nóng hoặc cache trở thành source of truth ngoài ý muốn.
12. Lập decision record, ma trận bằng chứng, test plan và lộ trình migration/rollback.

---

## 2. Polyglot persistence là gì?

**Polyglot persistence** là việc dùng nhiều hệ thống lưu trữ/đọc dữ liệu với đặc tính khác nhau để đáp ứng một hoặc nhiều nhu cầu nghiệp vụ.

Ví dụ:

~~~mermaid
flowchart LR
    APP["Java application"] --> O["Orders authority: MongoDB"]
    APP --> C["Catalog cache: Redis"]
    APP --> S["Product search: Elasticsearch"]
    O --> E["Transactional outbox / CDC"]
    E --> B["Event stream"]
    B --> S
    B --> A["Analytics read model"]
~~~

Ở đây có nhiều bản thể hiện dữ liệu, nhưng **không nên có nhiều nguồn sự thật không được điều phối cho cùng một business fact**.

### 2.1. Không đồng nghĩa microservices

Một monolith vẫn có thể dùng PostgreSQL, Redis và Elasticsearch. Ngược lại, mười microservices có thể cùng dùng một engine nhưng tách database theo domain.

### 2.2. Không đồng nghĩa “cứ thêm database là tốt”

Mỗi hệ mới tạo thêm failure modes, network hops, credentials, backups, upgrade paths và data synchronization requirements.

### 2.3. Không đồng nghĩa mỗi bản dữ liệu đều authoritative

Một search index chứa thông tin sản phẩm không có nghĩa nó được phép quyết định giá cuối cùng khi thanh toán.

### 2.4. Hệ chuyên dụng chỉ hữu ích khi đúng workload

Graph database không tự nhanh hơn document database cho mọi truy vấn có quan hệ; time-series store không tự thay được transactional inventory; search engine không nên làm payment ledger chỉ vì hỗ trợ JSON.

---

## 3. Quy tắc mặc định: ưu tiên ít hệ hơn cho tới khi có bằng chứng

**Mặc định khởi đầu hợp lý thường là một hệ dữ liệu chính có mô hình, chỉ mục và truy vấn phù hợp, bổ sung hệ khác khi xuất hiện nhu cầu đo được.**

Trước khi thêm một hệ, thử:

- Tối ưu data model và query shape.
- Tạo chỉ mục/compound index phù hợp.
- Thêm read replicas hoặc thay read concern có chủ đích.
- Dùng materialized view hoặc aggregation được engine hiện tại hỗ trợ.
- Caching ở ứng dụng khi rủi ro freshness chấp nhận được.
- Partitioning/sharding hoặc archival.
- Truy vấn async/batch cho báo cáo không cần thời gian thực.
- Tính năng search/vector/time-series tích hợp của sản phẩm đang dùng nếu đáp ứng hợp đồng.
- Tách hot/cold data trong cùng engine.
- Đổi request contract để giảm fan-out và dữ liệu trả về.

### 3.1. Khi nào tối ưu một hệ là đủ?

Nếu p99 và throughput còn đạt mục tiêu với headroom, access patterns ổn định, consistency dễ kiểm và chi phí vận hành nhỏ, việc thêm nhiều hệ có thể tạo âm lợi ích.

### 3.2. Khi nào cần xem xét hệ khác?

Khi một workload vẫn vi phạm SLO hoặc có chi phí quá cao sau khi đã thử những lựa chọn hợp lý, **và** một hệ khác có lợi thế rõ ràng được kiểm chứng bằng prototype, benchmark hoặc tính năng không thể đáp ứng tốt ở hệ hiện tại.

### 3.3. Không cần “một hệ mãi mãi”

Quy tắc ưu tiên đơn giản là điểm bắt đầu có thể đảo ngược, không phải tín điều chống lại kiến trúc nhiều hệ.

---

## 4. Phân biệt nhu cầu dữ liệu bằng access pattern

Cùng một thực thể `Product` có thể bị truy cập theo nhiều cách:

| Tác vụ | Dữ liệu cần | Tính chất quan trọng |
|---|---|---|
| Cập nhật giá chính thức | Product ID, version, price | Conditional update, audit |
| Xem trang sản phẩm | Product ID, fields hiển thị | Đọc nhanh, cache được |
| Tìm từ khóa | Text, filters, ranking | Full-text, analyzer, relevance |
| Gợi ý sản phẩm tương tự | Features/vectors | Approximate similarity và reranking |
| Báo cáo doanh thu | Order facts qua nhiều năm | Scans, aggregations, column-oriented |
| Tính tồn kho | Stock/reservations | Atomicity, concurrency safety |
| Phân tích mạng lưới nhà cung cấp | Node-edge relationships | Traversal nhiều bước |

### 4.1. Một hệ có thể đáp ứng nhiều hàng

Không nên ánh xạ máy móc “mỗi hàng = một sản phẩm”. Một hệ hiện tại có thể đã có full-text index, analytical secondary engine hoặc materialized views đủ dùng.

### 4.2. Khác biệt lớn nhất thường nằm ở đường truy cập

Một transactional source tối ưu point read/write khác một hệ phục vụ aggregation trên hàng tỷ records. Sự khác biệt này có thể tạo lợi ích đủ lớn để bù thêm độ phức tạp.

### 4.3. Chọn từ yêu cầu, không từ tên sản phẩm

Mô tả workload trước:

~~~text
Query: SearchProduct(keyword, filters)
Peak QPS: 3,000
p99 objective: 250 ms
Corpus: 80 million records
Freshness tolerance: 10 seconds
Ordering: relevance + explicit tie-breaker
Tenant isolation: mandatory
~~~

Sau đó mới thử công nghệ và cách dữ liệu được đồng bộ.

---

## 5. Phân loại các thành phần: authority, projection, cache, log

| Vai trò | Ví dụ | Được phép quyết định nghiệp vụ? |
|---|---|---|
| **System of record** | Orders database, inventory ledger | Có, trong ranh giới đã định |
| **Derived read model** | `orders_by_customer`, search index | Không nếu nguồn authoritative khác |
| **Cache** | Redis product detail | Chỉ theo freshness/authorization policy |
| **Event/change log** | Outbox, CDC stream, Kafka | Có thể là authority nếu hệ thiết kế event sourcing thực sự |
| **Analytical store** | OLAP/reporting DB | Thường phục vụ phân tích, không duyệt giao dịch |
| **Archive/backup** | Object storage snapshots | Nguồn phục hồi theo recovery contract |
| **External authority** | Payment provider | Có đối với kết quả charge theo hợp đồng tích hợp |

### 5.1. Authority phải được chỉ ra theo từng fact

Một hệ có thể coi Orders là nguồn authoritative cho `order.status`, Payment Provider là nguồn authoritative cho `capture result`, Inventory là nguồn authoritative cho `available units`.

### 5.2. Không gộp hai authority vô tình

Nếu app vừa ghi giá vào MongoDB vừa cho nhân viên sửa trực tiếp Elasticsearch, không có quy tắc giải quyết mâu thuẫn thì hệ có hai writers không phối hợp.

### 5.3. Source of truth là một cam kết vận hành

Phải ghi ai được ghi, thao tác nào được ghi, version nào thắng, tiến trình nào rebuild được projections, và làm gì khi dữ liệu diverge.

---

## 6. Khi một database đáp ứng được thì kiến trúc trông như thế nào?

~~~mermaid
flowchart TD
    API["Java API"] --> DB["Primary NoSQL engine"]
    DB --> ID["Indexes / internal projections"]
    DB --> BK["Native backup / PITR"]
    API --> REP["Async report jobs"]
    REP --> DB
~~~

Ưu điểm:

- Ít operational surface.
- Ít nhất quán chéo hệ.
- Một vòng backup/restore, một IAM/RBAC model chủ đạo.
- Dễ tìm nguồn sai lệch.
- Gọn hơn cho nhóm nhỏ.
- Dễ thực hiện transactional data changes trong phạm vi engine.

Giới hạn:

- Một loại query có thể ảnh hưởng các query khác.
- Heavy analytics có thể tranh CPU/I/O với critical writes.
- Một workload cần search/vector/graph traversal chuyên sâu có thể kém phù hợp.
- Indexing và duplication trong một engine vẫn có chi phí.
- Failure domain tập trung hơn nếu không phân vùng kiến trúc.

### 6.1. Tách workload trong cùng sản phẩm

Read replica, dedicated analytics nodes, online archival hoặc native search service có thể là phương án giữa “một cụm duy nhất” và “năm công nghệ độc lập”.

### 6.2. Khi workload đủ nhẹ

Nếu báo cáo chạy mỗi đêm 20 phút và không làm suy giảm giao dịch, dựng một hệ analytics mới 24/7 có thể không đáng.

---

## 7. Khi nào một hệ chuyên dụng tạo giá trị khác biệt?

Các dấu hiệu thường gặp:

1. Một tính năng rất quan trọng có yêu cầu mà engine hiện tại thiếu hoặc xử lý không hiệu quả.
2. Tải đọc/ghi có hình dạng trái ngược, làm nghẽn tài nguyên chung.
3. Indexes để phục vụ một truy vấn tạo write amplification hoặc storage cost quá lớn.
4. Bài toán có tính chuyên biệt: relevance search, graph multi-hop, large-scale analytics, time-series ingestion, key/value latency rất thấp.
5. Có thể tách dữ liệu dẫn xuất khỏi đường ghi chính bằng một hợp đồng eventual consistency được chấp nhận.
6. Đội có khả năng vận hành, kiểm thử và khôi phục hệ mới.
7. Có tiêu chí đo lợi ích sau khi thêm hệ mới và phương án quay lại.

### 7.1. Không đánh giá theo benchmark marketing

Một hệ đạt 1 triệu ops/s trên workload khác không chứng minh nó nhanh với query/user traffic của bạn.

### 7.2. Tránh chọn vì “đang phổ biến”

Tính phổ biến có thể giúp tìm nhân lực/tài liệu nhưng không thay yêu cầu cụ thể hoặc phép thử trên dữ liệu đại diện.

### 7.3. Không chỉ đo latency trung bình

p95/p99, error rate, resource saturation, hot partitions, consistency và vận hành trong giờ peak mới quyết định trải nghiệm.

---

## 8. Những lựa chọn NoSQL thường xuất hiện trong polyglot architecture

| Hệ/loại | Điểm mạnh thường xét | Điều không nên tự suy ra |
|---|---|---|
| **MongoDB/document** | Mô hình document, rich queries, indexes, transactional use cases tùy topology | Tất cả cross-system effects atomic |
| **DynamoDB/key-value/document** | Managed key access, conditional writes, predictable access patterns | GSI strong reads, scan tùy ý rẻ |
| **Cassandra/Scylla-like wide-column** | Writes quy mô lớn, phân phối theo partition, nhiều DC theo thiết kế | SQL joins/transactions tổng quát |
| **Redis** | Key-value latency thấp, cache, counters/data structures | Mọi ACK durable qua async failover |
| **Elasticsearch/OpenSearch** | Full-text, analyzer, relevance, aggregations/search | Transaction ledger với linearizable writes |
| **Graph DB** | Traversals, nhiều bước quan hệ theo query model | Luôn tối ưu mọi join bất kể kích thước |
| **Time-series DB** | Ingestion, compression, time-window queries | Bảo đảm tài chính/uniqueness tùy ý |
| **OLAP/columnar** | Scan/aggregation lớn, column compression | Thay một transactional source cho đơn hàng |
| **Object storage/data lake** | Chi phí lưu khối lượng lớn, immutable artifacts, batch | Low-latency transactional lookups tự nhiên |
| **Event broker/log** | Fan-out, buffering, replay trong retention | Database backup hoàn chỉnh mặc định |

Đặc tính chi tiết phụ thuộc phiên bản, cấu hình, mô hình dữ liệu và managed deployment. Một bảng so sánh không thay proof-of-concept.

---

## 9. Mô hình quyết định: lợi ích ròng phải dương

Để thêm hệ \(H\) vào kiến trúc, có thể dùng một mô hình sơ bộ:

\[
V_{\mathrm{net}}(H)
=
V_{\mathrm{business}}
+S_{\mathrm{resource}}
+V_{\mathrm{riskReduced}}
-C_{\mathrm{coordination}}
-C_{\mathrm{operations}}
-C_{\mathrm{migration}}
-C_{\mathrm{residualRisk}}.
\]

Trong đó:

- \(V_{\mathrm{business}}\): thêm doanh thu, giảm thời gian xử lý, cải thiện trải nghiệm và khả năng ra sản phẩm.
- \(S_{\mathrm{resource}}\): tiết kiệm CPU/IOPS/storage/compute vì chuyển workload khỏi nguồn.
- \(V_{\mathrm{riskReduced}}\): giảm sự cố do cách ly workload hoặc tăng khả năng phục hồi.
- \(C_{\mathrm{coordination}}\): CDC, schema, sync, reconciliation, duplicate delivery, multi-store failure handling.
- \(C_{\mathrm{operations}}\): on-call, bảo mật, backup, nâng cấp, monitoring, đào tạo.
- \(C_{\mathrm{migration}}\): backfill, dual running, cutover và rollback.
- \(C_{\mathrm{residualRisk}}\): rủi ro dữ liệu stale, vi phạm hợp đồng hoặc phải sửa sai.

### 9.1. Đây là mô hình quyết định, không phải công thức chuẩn

Có thể rất khó gắn tiền chính xác cho risk/privacy. Với những yêu cầu không thể vi phạm, dùng **hard gates** trước, rồi mới so giá trị tiền.

### 9.2. Hãy so với phương án tốt nhất chỉ dùng một hệ

So “một database chưa tối ưu” với “nhiều database được tối ưu” là thiên lệch. Cần đặt baseline sau những tối ưu hợp lý.

### 9.3. Lợi ích cần được chứng minh sau triển khai

Mỗi mục tiêu nên có metric owner, time horizon và review date. Nếu giá trị ròng thực tế không đạt, kiến trúc phải có phương án đơn giản hóa.

---

## 10. Ví dụ định lượng lợi ích và coordination tax

Một công ty dự báo cho năm đầu nếu thêm search engine riêng:

| Khoản | Giá trị minh họa |
|---|---:|
| Giảm chi phí compute/IO của nguồn | +360 triệu VND |
| Giá trị tăng từ search conversion | +1.200 triệu VND |
| Giảm thời gian triển khai tính năng search | +240 triệu VND |
| Hạ tầng search engine | -300 triệu VND |
| CDC/broker/network/storage | -180 triệu VND |
| Kỹ sư vận hành/on-call | -480 triệu VND |
| Migration/backfill/QA | -420 triệu VND |
| Rủi ro/reconciliation budget | -180 triệu VND |

Tổng lợi ích minh họa = **1.800 triệu VND**. Tổng chi phí minh họa = **1.560 triệu VND**. Giá trị ròng ước tính = **+240 triệu VND trong năm đầu**.

### 10.1. Nhưng chưa đủ để quyết định ngay

Nếu business bắt buộc giá hiển thị phải luôn đúng 100% khi thanh toán mà hệ mới chỉ cho eventual search freshness, kiến trúc phải phân biệt **giá dùng để search** với **giá chốt từ source**. Một lỗi correctness critical không thể chỉ “trừ vào budget” rồi bỏ qua.

### 10.2. Nhạy cảm với giả định

Nếu conversion uplift chỉ bằng 50% dự báo, lợi ích giảm 600 triệu VND; giá trị ròng đổi thành **-360 triệu VND**.

### 10.3. Không dùng số chi phí tưởng tượng làm bằng chứng

Các số trên chỉ để học cách phân tích. Quyết định thật cần cloud bills, load tests, thời gian kỹ sư, backlog và phân tích business.

### 10.4. Chi phí năm hai có thể khác năm đầu

Migration cost giảm, nhưng vận hành 24/7, version upgrades, security patches và data growth vẫn tồn tại.

---

## 11. Tính TCO thay vì chỉ tiền thuê database

Một mô hình tổng chi phí sở hữu:

\[
TCO =
C_{\mathrm{infra}}
+C_{\mathrm{network}}
+C_{\mathrm{storage}}
+C_{\mathrm{personnel}}
+C_{\mathrm{tooling}}
+C_{\mathrm{backupDR}}
+C_{\mathrm{security}}
+C_{\mathrm{migration}}
+C_{\mathrm{incident}}.
\]

### 11.1. Infrastructure

Compute, memory, provisioned/on-demand capacity, disk throughput, backups, replication, shard overhead.

### 11.2. Network

Cross-AZ/cross-region data transfer, CDC streaming, analytics extracts, client connections và egress.

### 11.3. Storage duplication

Một document 2 KiB có thể xuất hiện ở authoritative store, cache, search index, CDC log và data lake. Tổng bytes/cost lớn hơn một bản ghi.

### 11.4. Operations

Số quy trình cần hiểu và trực on-call tăng: scaling, dashboards, alert tuning, credentials, patching, incident response, schema upgrades.

### 11.5. Security/compliance

Tenant isolation trên nhiều read paths, KMS/IAM, audit, privacy deletes, retention, legal hold và incident forensics.

### 11.6. DR

Restore một hệ nhanh nhưng năm hệ không cùng checkpoint có thể khiến service RTO dài hơn. Cần test end-to-end DR chứ không chỉ backup từng store.

### 11.7. Chi phí cơ hội

Đội engineering duy trì Kafka connectors, search mappings và sync lỗi có thể làm chậm những tính năng thực sự tạo doanh thu.

---

## 12. Một dạng ma trận đánh giá có trọng số

Ví dụ chấm từ 1 (kém) đến 5 (tốt):

| Tiêu chí | Trọng số | Một hệ tối ưu | Thêm search riêng |
|---|---:|---:|---:|
| Truy vấn search đạt SLO | 25% | 3 | 5 |
| Tính đúng nghiệp vụ dễ giữ | 20% | 5 | 4 |
| Chi phí vận hành thấp | 15% | 5 | 2 |
| Khả năng mở rộng workload | 15% | 3 | 5 |
| Tính sẵn sàng/degraded mode | 10% | 4 | 4 |
| Dễ restore/migrate | 10% | 5 | 2 |
| Năng lực đội phù hợp | 5% | 5 | 3 |

Tổng điểm ví dụ:

- Một hệ: \(3(0.25)+5(0.20)+5(0.15)+3(0.15)+4(0.10)+5(0.10)+5(0.05)=4.10/5\).
- Thêm search: \(5(0.25)+4(0.20)+2(0.15)+5(0.15)+4(0.10)+2(0.10)+3(0.05)=3.85/5\).

Dù phương án nhiều hệ đạt search SLO tốt hơn, trọng số hiện tại ưu tiên simplicity/correctness nên chưa thắng.

### 12.1. Điểm tổng không thay hard constraints

Nếu một engine không thể đáp ứng SLO search bắt buộc dù đã tối ưu, kết quả điểm cao của một hệ không làm nó khả thi. Đặt hard gates trước scoring.

### 12.2. Trọng số do stakeholders quyết định

Product, SRE, data, security và finance có ưu tiên khác. Ghi rõ owner và lý do trọng số.

### 12.3. Scoring giúp hội thoại, không là “phép đo khách quan tuyệt đối”

Kèm bằng chứng và confidence từng hàng: benchmark, observed cost, prototype hoặc giả định chưa thử.

---

## 13. Kiểm thử một hệ trước khi bổ sung hệ khác

Một evaluation phải có baseline:

~~~yaml
baseline:
  workload: product-search
  corpusRecords: 80000000
  peakQps: 3000
  resultP99Bytes: 18000
  latencyP99TargetMillis: 250
  freshnessTargetSeconds: 10
  sourceCpuHeadroomPercent: 15
  queries:
    - keyword-ranking
    - filtered-facets
    - prefix-suggest
  evidence:
    - production-query-fingerprints
    - representative-load-test
~~~

### 13.1. Chạy fair comparison

Cùng query semantics, data distribution, load, consistency/freshness và result payload. Không so source full scan với target index tốt rồi kết luận riêng engine quyết định tất cả.

### 13.2. Tính sync/reindex vào benchmark

Không chỉ đo latency search trên index đã sẵn, còn đo thời gian từ source write đến search visibility và cost build/update.

### 13.3. Đo cold và warm paths

Cache warm có thể che lỗi. Khi index/search cluster vừa restart, p99 và throughput có thể thấp hơn nhiều.

### 13.4. Đo peak/skew

Hot tenant/merchant, từ khóa phổ biến, large documents và bursts cần có trong workload.

---

## 14. Thiết kế một bản đồ dữ liệu và quyền sở hữu

Mỗi entity/fact cần một owner và hợp đồng:

| Fact | Authority | Bản sao | Quy tắc thay đổi |
|---|---|---|---|
| Giá chốt đơn | Pricing/Orders authority | Search/cached catalog | Chốt lại tại checkout từ authority |
| Trạng thái thanh toán | Provider + payment ledger | Orders summary | Reconcile theo provider receipt |
| Tồn kho khả dụng | Inventory authority | Catalog display cache | Reservation CAS tại authority |
| Mô tả sản phẩm | Catalog authority | Search index, CDN cache | Event-driven update |
| Session | Session authority theo policy | Edge cache | Expiry/revocation rule rõ |
| Search relevance score | Search model | API response | Không thành authoritative price |
| Event delivery state | Broker/consumer checkpoint | Monitoring projections | Replay/idempotency |

### 14.1. Người đọc không nhất thiết viết

Search service thường không sửa catalog source. Nếu admin muốn cập nhật product name, họ phải gọi catalog command path thay vì sửa index.

### 14.2. Version và timeline

Bản sao nên có source version/updatedAt, event ID hoặc watermark đủ để phát hiện stale state và replay.

### 14.3. Ownership là hợp đồng xã hội lẫn kỹ thuật

Ai sửa bug mapper? Ai rebuild index? Ai quyết định khi dữ liệu mâu thuẫn? Ai phê duyệt compatibility change? Không có owner, chi phí phối hợp tăng mạnh.

---

## 15. Một kiến trúc nhiều hệ có thể chấp nhận được

~~~mermaid
flowchart TD
    CLIENT["Client"] --> API["Java Order API"]
    API --> WRITE["Order command service"]
    WRITE --> DB["Authoritative Orders DB"]
    DB --> OUT["Transactional outbox"]
    OUT --> CDC["Outbox relay / CDC"]
    CDC --> BUS["Event broker"]
    BUS --> SEARCH["Search projector"]
    BUS --> ANALYTICS["Analytics projector"]
    SEARCH --> ES["Search index"]
    ANALYTICS --> WH["Analytical store"]
    API --> CACHE["Redis cache-aside"]
    API --> ES
    API --> DB
    API --> PAY["Payment provider"]
~~~

### 15.1. Viết qua một authority

Đối với một business fact, route commands tới service/authority chịu trách nhiệm commit. Không cho nhiều stores tự quyết cùng một fact.

### 15.2. Bản sao chỉ là projection

Search index, analytics và cache phục vụ các truy vấn theo freshness contract; nếu source thay đổi, projections cần catch-up hoặc rebuild.

### 15.3. Business invariant nằm ở chỗ phù hợp

Không dựa vào search index eventual để xác nhận còn vé. Phải reserve tại inventory authority.

### 15.4. Event broker là đường phân phối, không tự là transaction

Nếu business write và event publish thực hiện thành hai lời gọi không phối hợp, một lời gọi có thể thành công và lời kia thất bại.

---

## 16. Anti-pattern: dual-write đồng bộ không có giao dịch chung

Một service làm:

~~~java
ordersDb.save(order);
searchClient.index(order);
return SUCCESS;
~~~

Các trường hợp:

| Bước 1 — DB | Bước 2 — Search | Hậu quả |
|---|---|---|
| Thành công | Thành công | Có vẻ đúng |
| Thành công | Timeout | Source và search có thể lệch |
| Thành công | Lỗi chắc chắn | Search thiếu record |
| Timeout nhưng đã commit | Thành công | Client thấy lỗi nhưng hai stores đã đổi |
| Thất bại | Không chạy | Không có bản mới |
| Thành công | Thành công rồi client timeout | Retry có thể nhân side effects |

### 16.1. Try/catch không tạo atomicity

Viết `try { db.save; search.save; } catch { rollback; }` không chắc rollback được cả hai hệ, đặc biệt khi timeout không rõ kết quả.

### 16.2. Distributed transaction không phải mặc định

Không phải mọi engine/managed service tham gia chung transaction coordinator; ngay cả khi hỗ trợ, chi phí latency, lock và failure semantics có thể lớn.

### 16.3. Tránh dùng search như một phần commit bắt buộc nếu không cần

Một order write không nhất thiết thất bại chỉ vì search unavailable, miễn hợp đồng cho phép index bắt kịp sau đó và có cơ chế tránh mất event.

---

## 17. Outbox: phát event intent cùng business commit

Transactional outbox là một cách phổ biến để tránh mất ý định phát sự kiện sau khi business write đã commit.

~~~mermaid
sequenceDiagram
    participant API as Java API
    participant DB as Authoritative DB
    participant REL as Outbox relay
    participant BUS as Broker
    participant IDX as Search projector
    API->>DB: Begin supported transaction
    API->>DB: Update order + append outbox intent
    DB-->>API: Commit / authoritative receipt
    REL->>DB: Read pending outbox
    REL->>BUS: Publish event (may retry)
    BUS->>IDX: Deliver (possibly duplicate)
    IDX->>IDX: Idempotent/versioned upsert
~~~

### 17.1. Điều kiện quan trọng

Business write và outbox intent phải được commit nguyên tử **trong một transaction boundary thực sự được engine hỗ trợ** hoặc trong một data model/protocol tương đương.

### 17.2. At-least-once delivery

Relay có thể publish thành công rồi crash trước khi ghi nhận đã publish, dẫn tới publish trùng khi restart. Consumer cần idempotent.

### 17.3. Không hứa thứ tự toàn cục

Event ordering thường có scope theo partition/entity key; nếu hai orders khác nhau ở partitions khác nhau, không mặc định có total order.

### 17.4. Outbox không thay reconciliation

Nếu event history bị thiếu, transformer lỗi hoặc downstream mất checkpoint, cần phát hiện và resnapshot/replay.

---

## 18. CDC từ source: tiện lợi nhưng không miễn phí

Change Data Capture có thể chuyển thay đổi của source sang event stream mà không bắt API trực tiếp ghi nhiều hệ.

### 18.1. Điểm mạnh

- Tách producer business logic khỏi nhiều consumers.
- Dễ mở thêm projection mới.
- Có thể bắt kịp updates và deletes.
- Dễ xây audit/freshness metrics với source positions.

### 18.2. Giới hạn

- Retention có hạn.
- Connector có thể bị pause hoặc crash.
- Một source update không luôn tương đương một business event giàu semantics.
- Snapshot+tail cần logical cut/checkpoint đúng.
- Schema evolution và delete events cần mapping.
- Per-partition order, duplicates, resubscription.
- Backpressure khi target chậm.

### 18.3. Không suy CDC là backup

Nếu nguồn đã hỏng và logs chỉ giữ thời gian ngắn, CDC stream có thể không đủ để reconstruct toàn bộ source. Backup/PITR vẫn là bài toán riêng.

### 18.4. Chi phí vận hành

Connector upgrades, permission scopes, queue backlogs, dead letters, rebalances và lag alerts cần owner.

---

## 19. Bản sao dữ liệu làm tăng chi phí consistency

Nếu một product được ghi vào source lúc 10:00:00:

~~~text
10:00:00 Source commit version 8
10:00:00.1 CDC captures update
10:00:01 Broker delivers
10:00:02 Search index receives
10:00:03 Search refresh exposes version 8
10:00:05 Redis cache entry expires
~~~

Một người dùng đọc từ search lúc 10:00:02 có thể thấy version 7. Cache đến 10:00:05 vẫn có thể trả giá cũ.

### 19.1. Tách các mức bảo đảm

- Strong/current source reads cho quyết định giao dịch.
- Read-your-writes trong một session nếu cần.
- Bounded staleness cho search/catalog.
- Eventual convergence cho analytics.
- Security revocation có thể cần fail-closed, không cho stale permission.

### 19.2. Cần một freshness budget rõ

Ví dụ search `99.9% updates visible within 10s` dưới điều kiện hoạt động đã định nghĩa. Đây là mục tiêu giả định, không là bảo đảm tự nhiên của Elasticsearch hay Kafka.

### 19.3. Không gọi eventual là “sai” một cách chung chung

Nếu hợp đồng cho phép kết quả trễ 5 giây, một read cũ trong khoảng đó có thể hợp lệ. Nhưng nếu giá checkout phải chính xác tại commit, phải đọc/chốt qua authority.

---

## 20. Backpressure và khi consumer không theo kịp

Giả sử source tạo \(\lambda=20{,}000\) events/s và search projector xử lý \(\mu=18{,}000\) events/s.

Backlog tăng khoảng:

\[
\Delta Q\approx(\lambda-\mu)t.
\]

Sau 1 giờ, backlog tăng lý tưởng:

\[
(20{,}000-18{,}000)\times3600=7{,}200{,}000\text{ events}.
\]

### 20.1. Không thể gọi “đang đồng bộ” nếu backlog tăng vô hạn

Cần nâng capacity, giảm event volume, batch/coalesce hợp lý hoặc hạ business freshness target có chủ đích.

### 20.2. Catch-up capacity

Nếu backlog là \(Q\) và \(\mu>\lambda\):

\[
T_{\text{catchup}}\approx\frac{Q}{\mu-\lambda}.
\]

Đây là mô hình đơn giản; skew, broker quotas, retries, index refresh và hot partitions làm thực tế khác.

### 20.3. Bounded queues

Queue không giới hạn có thể làm OOM hoặc retention hết hạn. Cần giới hạn in-flight, batching, retry budget và dead-letter policy.

### 20.4. Không để search outage làm sập payment path

Nếu search chỉ là derived projection, application nên có degraded mode rõ thay vì retries đồng bộ hàng loạt khiến transaction source quá tải.

---

## 21. Duplicate delivery, reorder và version guards

Một consumer có thể nhận:

~~~text
OrderUpdated(id=7, version=12)
OrderUpdated(id=7, version=12)   duplicate
OrderUpdated(id=7, version=11)   late event
OrderDeleted(id=7, version=13)
OrderCreated(id=7, version=10)   old backfill
~~~

Nếu target dùng unconditional upsert, event version 11 hoặc old backfill v10 có thể ghi đè version 12 hoặc hồi sinh deleted record.

### 21.1. Quy tắc tối thiểu

Lưu `sourceVersion`/epoch và chỉ áp event mới hơn state target hiện có, với per-entity ordering contract rõ.

### 21.2. Duplicate phải idempotent

Hai events cùng eventId/version không tạo hai external effects.

### 21.3. Tombstone/delete marker

Sau delete v13, event v10 không được tạo lại record. Cần giữ tombstone/version guard đủ lâu so với replay horizon.

### 21.4. Version không luôn chỉ là số tăng

Nếu entity được tạo lại, schema reset, multi-region branches hoặc source không có monotonic version, cần epoch/causal metadata hoặc một ordering protocol khác. Không tự so timestamp wall-clock mà tuyên bố chính xác.

---

## 22. Quyền riêng tư và tenant isolation trên nhiều hệ

Sao chép sang Redis, search index, broker và analytical warehouse **mở rộng diện tích dữ liệu nhạy cảm**.

### 22.1. Tenant filter phải có ở mọi read path

Một query search thiếu `tenantId` vẫn có thể lộ dữ liệu của tenant B dù Orders API kiểm tenant đúng.

### 22.2. Redis key có thể bị collision

Key `order:123` không đủ nếu order IDs chỉ unique trong tenant. Dùng namespace có tenant theo policy và bảo đảm auth context đến cache key path.

### 22.3. Xóa dữ liệu phải lan đúng

Sau user deletion, source xóa không có nghĩa search/index/cache đã xóa; cần sự kiện delete, reconciliation, TTL/retention và audit.

### 22.4. Key và vùng dữ liệu

Cross-region replication/analytics có thể vi phạm data residency. Mỗi store cần encryption, KMS/IAM, RBAC, retention policy và backup boundary phù hợp.

### 22.5. Cache authorization không thể chỉ dựa TTL

Nếu một permission vừa bị revoke, cache entry còn hiệu lực vật lý 10 phút không được phép tiếp tục authorize nếu hợp đồng security cấm. Có thể cần version token, central verification hoặc fail-closed design.

---

## 23. Availability: phụ thuộc nhiều hệ có thể làm yếu đường nóng

Giả sử một request **bắt buộc đồng thời** thành công tại ba dependencies, mỗi dependency có availability 99.9% trong mô hình độc lập rất đơn giản.

Availability request xấp xỉ:

\[
0.999^3\approx 0.997003,
\]

tức khoảng **99.7003%**, thấp hơn 99.9% của từng dependency.

### 23.1. Đây chỉ là mô hình minh họa

Failures có thể tương quan, retries/circuit breakers/caches có thể thay đổi xác suất; không dùng tích số này như SLA dự báo chính xác.

### 23.2. Giảm phụ thuộc đồng bộ

Nếu checkout chỉ cần Inventory authority và Payment provider, việc search index down không nên làm checkout fail.

### 23.3. Thiết kế degraded modes

| Dependency mất | Phản ứng có thể hợp lệ | Điều tuyệt đối tránh |
|---|---|---|
| Redis derived cache | Đọc source với rate limit | Stampede làm source quá tải |
| Search | Ẩn tìm kiếm, vẫn cho GET by ID | Cho search stale quyết định quyền/giá |
| Analytics | Hoãn báo cáo | Chặn checkout không cần thiết |
| Broker | Durable outbox tích lũy rồi replay | Mất intent phát sự kiện |
| Inventory authority | Từ chối giữ chỗ an toàn | Bán dựa trên cache cũ |
| Payment provider | Dùng pending/unknown outcome flow | Retry charge với ID mới vô hạn |

### 23.4. Không giả định fallback luôn an toàn

Fallback sang source khi cache mất có thể làm nguồn quá tải; fallback từ strong read sang stale replica có thể phá invariant. Mỗi fallback cần contract và load test.

---

## 24. Phân tách đường nóng, đường dẫn xuất và đường phân tích

~~~text
HOT TRANSACTION:
  API -> Authoritative DB -> durable result

DERIVED READ:
  API -> Search/Cache
            ^ asynchronous events from authority

ANALYTICS:
  Data pipeline -> Analytical store -> Reports
~~~

### 24.1. Đường nóng

Tối thiểu hóa synchronous dependencies; những dependency còn lại phải cần thiết cho tính đúng nghiệp vụ.

### 24.2. Đường dẫn xuất

Chấp nhận delay có giới hạn, có version/watermark và khả năng rebuild.

### 24.3. Đường phân tích

Có thể chạy batch/stream, tách resource khỏi write-heavy primary và có SLA riêng.

### 24.4. Transactional reporting khác analytics offline

Nếu báo cáo được dùng để quyết định chuyển tiền ngay, nó có thể cần consistency mạnh hơn dashboard phân tích xu hướng.

---

## 25. Khi nào nên thêm Redis?

Một use case hợp lý:

- Hot key/value reads chiếm phần lớn load.
- Dữ liệu chủ yếu dẫn xuất, có authority khác.
- Cache hit rate đủ cao để bù network hop và chi phí.
- Có TTL/invalidation rõ và cơ chế chống stampede.
- Lỗi cache không gây correctness violation.
- Đã đo backend load khi cache mất.

### 25.1. Cache-aside

~~~text
GET product:
  Redis hit -> return if freshness/security valid
  Redis miss -> authoritative DB
               -> put into Redis with TTL
               -> return
~~~

### 25.2. Hệ dễ mắc lỗi

Một value có giá/permission đã đổi nhưng cache chưa invalidated. Phải chọn update/invalidate policy, versioning và final authoritative check nếu có hậu quả tài chính/bảo mật.

### 25.3. Redis không phải mặc định chỉ là cache

Nếu sử dụng Redis queues, sessions, counters hoặc idempotency ledger như nguồn duy nhất, kiến trúc đã có thêm **authoritative state**. Cần durability/backup/failover riêng.

### 25.4. Đo lợi ích đúng

So p99, hit rate, cache bytes, invalidation lag, Redis cost, source read reduction và source peak load khi cache down.

---

## 26. Khi nào nên thêm Elasticsearch/OpenSearch hoặc search service?

Cân nhắc khi:

- Cần full-text relevance, analyzers, synonyms, filtering, facets, highlighting hoặc vector retrieval mà giải pháp hiện tại không đáp ứng tốt.
- Index update latency có budget rõ.
- Query/search load ảnh hưởng transactional source.
- Có khả năng rebuild index từ authority.
- Search failure có degraded mode.
- Đội chấp nhận cluster/index/alias/refresh/backup operations.

### 26.1. Không dùng search làm giá thanh toán

Search trả giá để hiển thị, nhưng checkout phải xác nhận/chốt giá theo contract từ Pricing/Orders authority.

### 26.2. Không quên thứ tự và pagination

Search score, analyzer và `search_after`/PIT semantics có thể khác query của source. Contract test cần kiểm logical results chứ không chỉ document count.

### 26.3. Versioned index / alias cutover

Có thể dựng index mới, replay CDC đến checkpoint, chạy shadow comparisons rồi chuyển alias có kiểm soát.

### 26.4. Cost cần bao gồm writes

Index mới cần storage/shards và CPU để ingest/refresh/reindex; không chỉ chi phí truy vấn.

---

## 27. Khi nào cần graph database?

Các quan hệ kiểu:

~~~text
Customer -> Account -> Device -> IP -> Merchant -> FraudRing
~~~

có thể cần multi-hop traversal, path finding hoặc graph pattern matching.

### 27.1. Dấu hiệu phù hợp

- Traversal nhiều bước là lõi chức năng.
- Quan hệ thay đổi thường xuyên.
- Query yêu cầu khám phá paths và neighborhoods phức tạp.
- Denormalized joins trong hệ hiện tại quá tốn hoặc quá khó duy trì.

### 27.2. Không thêm graph chỉ vì có foreign keys

Một join một-nhiều đơn giản có thể được biểu diễn bằng document embedding/reference, materialized view hoặc relational query đủ hiệu quả.

### 27.3. Graph projection thường không nên là payment authority

Graph có thể phục vụ fraud detection/risk scores, nhưng quyết định nghiệp vụ nào cần strong current source phải tách rõ.

### 27.4. Đồng bộ node-edge

Nếu entity source bị delete và graph thiếu tombstone, kết quả có thể liên quan đến chủ thể đã bị xóa. Cần lineage, version, cleanup và data privacy policy.

---

## 28. Khi nào thêm time-series hoặc analytical store?

### 28.1. Time-series

Các workload như metrics, telemetry, IoT events và time-window aggregations có thể cần ingest cao, retention/time partitioning, downsampling và compression.

### 28.2. Analytical store

Báo cáo quét hàng tỷ events, group-by/histogram/joins theo nhiều năm có thể hưởng lợi từ columnar/OLAP.

### 28.3. Phân biệt raw facts và aggregates

Một dashboard doanh thu cập nhật mỗi 15 phút khác sổ cái dùng để chuyển tiền. Không chuyển business authority sang OLAP chỉ để aggregate nhanh.

### 28.4. Retention và late events

Late-arriving events, corrections và deletes phải được xử lý: append-only analytics có thể cần retractions/upserts, backfill và partition rebuild.

### 28.5. Batch thay real-time khi business cho phép

Nếu người dùng chỉ xem báo cáo cuối ngày, cron export có thể đơn giản hơn streaming pipeline chạy liên tục.

---

## 29. Khi nào nhiều NoSQL authorities là lựa chọn đúng?

Có thể có nhiều domain khác nhau:

~~~text
Identity service -> Identity database
Order service    -> Orders database
Inventory        -> Inventory ledger
Search service   -> Search projection
~~~

Đây không nhất thiết là sai, bởi mỗi dịch vụ sở hữu **business facts khác nhau**.

### 29.1. Domain ownership

Một team sở hữu schema/commands cho dữ liệu của mình. Consumer khác gọi API hoặc nhận events, không sửa trực tiếp table của owner.

### 29.2. Cross-domain consistency

Order và Inventory có thể không nằm trong một transaction chung. Cần reservation protocol, saga/compensation và idempotency.

### 29.3. Khi nào nên gộp?

Nếu hai services liên tục cần transaction chéo với strong invariant, nhiều hệ có thể khiến workflow quá phức tạp. Cân nhắc chuyển invariant về một authority hoặc đổi boundaries.

### 29.4. Không phân chia chỉ theo kỹ thuật

Một database cho “read service”, một database cho “write service” mà cả hai đều authoritative cùng fact dễ tạo ownership rối. CQRS read model nên giữ authority rõ.

---

## 30. Distributed transactions, saga và compensation

Với Order, Inventory và Payment ở ba domain:

~~~mermaid
flowchart TD
    START["PlaceOrder"] --> RES["Reserve inventory"]
    RES --> PAY["Capture payment"]
    PAY --> CONF["Confirm order"]
    RES -->|Rejected| REJ["Reject order"]
    PAY -->|Failed definite| RELEASE["Release reservation"]
    PAY -->|Unknown| RECON["Check provider receipt / reconcile"]
    CONF --> DONE["Fulfilled state"]
~~~

### 30.1. Không có transaction chung tự động

Một MongoDB transaction không bao phủ API payment provider và Redis Search cache. Cross-service atomicity phải được thiết kế riêng.

### 30.2. Saga là chuỗi trạng thái nghiệp vụ

Mỗi bước có idempotent command, state, retries, timeouts, compensation và exception handling.

### 30.3. Compensation không luôn đảo ngược vật lý

Email đã gửi không thể “unsend”; payment đã capture có thể cần refund thay vì rollback giả định.

### 30.4. Unknown outcomes

Nếu provider timeout, không lập tức charge lại với operation ID mới. Truy vấn provider/reference ledger theo request ID trước khi quyết định.

### 30.5. Chi phí phối hợp phải tính

Workflow status store, reconciliation jobs, dead letters, observability, on-call runbooks và tests đều là chi phí bổ sung.

---

## 31. Java: ranh giới rõ giữa command authority và read projections

Một cách tổ chức Java 17:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Optional;

public interface OrderCommandPort {

    // Ghi authoritative order + durable outbox intent
    // trong cùng boundary được adapter bảo đảm.
    WriteReceipt commitOrder(
        String tenantId,
        String requestId,
        BigDecimal total,
        String currency
    );

    record WriteReceipt(
        String orderId,
        long sourceVersion,
        String requestId
    ) {}
}

public interface OrderQueryPort {
    Optional<OrderView> getOrder(
        String tenantId, String orderId
    );

    record OrderView(
        String orderId,
        String status,
        BigDecimal total,
        String currency,
        Instant updatedAt,
        long sourceVersion
    ) {}
}

public interface ProductSearchPort {
    SearchPage search(
        String tenantId,
        String query,
        String continuationToken
    );

    record SearchHit(
        String productId,
        String title,
        long sourceVersion
    ) {}

    record SearchPage(
        java.util.List<SearchHit> hits,
        String nextToken
    ) {}
}
~~~

### 31.1. Ý nghĩa của phân tách

- `OrderCommandPort`: duy nhất chịu trách nhiệm thay đổi authoritative state.
- `OrderQueryPort`: đọc đơn hàng theo consistency contract.
- `ProductSearchPort`: read model chuyên dụng với freshness riêng.

### 31.2. Interface không tự tạo atomicity

Một adapter `commitOrder` phải thực hiện protocol đúng, ví dụ MongoDB transaction cho order + outbox hoặc DynamoDB transaction trong giới hạn hỗ trợ. Tên method không thay database guarantees.

### 31.3. Không leak driver semantics ra domain

Map `ConditionalCheckFailed`, duplicate key, timeout/unknown outcome thành domain results rõ, đừng làm business layer dựa trên exception string.

---

## 32. Java: mẫu service không chặn transaction vì search

Một ví dụ service:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public final class PlaceOrderService {

    private final OrderCommandPort commands;

    public PlaceOrderService(OrderCommandPort commands) {
        this.commands = Objects.requireNonNull(commands);
    }

    public OrderCommandPort.WriteReceipt place(
            String tenantId,
            String requestId,
            BigDecimal total,
            String currency) {

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Invalid tenant");
        }
        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException("Invalid request");
        }
        if (total == null || total.signum() < 0) {
            throw new IllegalArgumentException("Invalid total");
        }

        return commands.commitOrder(
            tenantId, requestId, total, currency
        );
    }
}
~~~

Điểm quan trọng: method này **không gọi Elasticsearch**. Commit authoritative state và durable event intent thuộc adapter; search projection tự cập nhật qua event pipeline.

### 32.1. Phải có idempotency bên trong authority

`requestId` được truyền vào không đủ. Adapter/ledger phải từ chối hoặc trả lại kết quả cũ khi nhận duplicate theo contract.

### 32.2. Không phát event bằng fire-and-forget thread trong API

Một process crash có thể làm mất intent. Outbox/event source bền vững giúp recovery, nhưng vẫn cần duplicate handling.

### 32.3. Có thể cần synchronous dependency thật

Nếu payment authorization là điều kiện để chấp nhận order, nó có workflow riêng. Không phải mọi thứ đều có thể eventual; kiến trúc phải nêu rõ invariant cần đồng bộ.

---

## 33. Java: consumer áp sự kiện có version guard

Sơ đồ:

~~~text
Broker receives OrderChanged(id=o-7, version=12)
  -> Projector
  -> Target conditional upsert if sourceVersion < 12
  -> ACK/checkpoint after durable target result
~~~

Hợp đồng Java:

~~~java
import java.util.Objects;

public record OrderChanged(
    String eventId,
    String tenantId,
    String orderId,
    long sourceVersion,
    String status,
    long amountMinor,
    boolean deleted
) {
    public OrderChanged {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(status);
    }
}

public interface VersionedOrderProjection {
    enum ApplyResult {
        APPLIED,
        DUPLICATE_OR_OLD,
        RETRYABLE_FAILURE
    }

    // Adapter phải so version và update atomically
    // theo semantics engine target được chọn.
    ApplyResult applyIfNewer(OrderChanged event);
}
~~~

### 33.1. Consumer không nên so version bằng GET rồi PUT không điều kiện

Hai projector instances có thể race. Dùng conditional write/CAS/atomic script/version protocol phù hợp target.

### 33.2. `deleted=true` cần tombstone/retention

Nếu delete v13 đã áp, event create v10 tới muộn không được hồi sinh. Đặt version guard kể cả khi object không còn được trả trong query.

### 33.3. ACK/checkpoint sau write

Checkpoint broker trước khi target commit có thể làm mất event trên crash. Checkpoint sau commit có thể làm redelivery; phải idempotent.

### 33.4. Source version phải có semantics đủ

Nếu source có branching writes hoặc reset version sau recreation, bổ sung epoch/stream position. Không giả định một `long` tăng toàn cầu trong mọi architecture.

---

## 34. Java JUnit 5: kiểm consumer bị redelivery và reorder

Một contract test giả định projection adapter thật:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

public abstract class ProjectionContractTest {

    protected abstract VersionedOrderProjection projection();

    protected abstract long currentVersion(
        String tenantId, String orderId);

    protected abstract boolean isVisible(
        String tenantId, String orderId);

    @Test
    void oldEventCannotOverwriteNewerVersion() {
        String tenant = "test-t";
        String order = "o-7";

        OrderChanged v12 = new OrderChanged(
            "e12", tenant, order, 12,
            "PAID", 10020, false);

        OrderChanged v11 = new OrderChanged(
            "e11", tenant, order, 11,
            "PENDING", 10020, false);

        projection().applyIfNewer(v12);
        projection().applyIfNewer(v11);
        projection().applyIfNewer(v12); // duplicate

        assertEquals(12, currentVersion(tenant, order));
    }

    @Test
    void oldInsertCannotResurrectDelete() {
        String tenant = "test-t";
        String order = "o-8";

        projection().applyIfNewer(new OrderChanged(
            "e13", tenant, order, 13,
            "DELETED", 0, true));

        projection().applyIfNewer(new OrderChanged(
            "e10", tenant, order, 10,
            "CREATED", 10020, false));

        assertFalse(isVisible(tenant, order));
        assertEquals(13, currentVersion(tenant, order));
    }
}
~~~

### 34.1. Dùng adapter thực

Chạy cùng suite trên MongoDB read model, DynamoDB GSI-backed model hoặc Elasticsearch projector tùy target; nhưng method `currentVersion` cần oracle độc lập và consistency phù hợp.

### 34.2. Test này không chứng minh broker delivery

Nó kiểm behavior khi đưa commands theo thứ tự đã chọn. Cần integration test với broker/CDC thật cho retention, checkpoint và restart.

### 34.3. Tạo namespace riêng

Cần ID/test tenant/collection độc lập để tests chạy song song không nhiễu nhau.

---

## 35. Java: cache-aside mà không coi cache là authority

~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.Optional;

public final class ProductReader {

    public interface ProductStore {
        Optional<Product> findByTenantAndId(
            String tenantId, String productId);
    }

    public interface ProductCache {
        Optional<Product> get(
            String tenantId, String productId);

        void put(
            String tenantId,
            Product product,
            Duration ttl);
    }

    public record Product(
        String id,
        String title,
        long priceMinor,
        long version
    ) {}

    private final ProductStore authority;
    private final ProductCache cache;

    public ProductReader(
            ProductStore authority,
            ProductCache cache) {
        this.authority = Objects.requireNonNull(authority);
        this.cache = Objects.requireNonNull(cache);
    }

    public Optional<Product> find(
            String tenantId, String productId) {

        Optional<Product> cached =
            cache.get(tenantId, productId);

        if (cached.isPresent()) {
            return cached;
        }

        Optional<Product> source =
            authority.findByTenantAndId(
                tenantId, productId);

        source.ifPresent(product ->
            cache.put(
                tenantId,
                product,
                Duration.ofSeconds(30)));

        return source;
    }
}
~~~

### 35.1. Đây là code minh họa, không là mẫu dùng để chốt giá

Giá trong cache có thể stale. Checkout cần kiểm lại giá/phiên bản qua authority theo business contract.

### 35.2. Cần xử lý cache failure

Trong production có thể bắt các lỗi cache xác định và fallback có **rate limit/circuit breaker**. Không catch mọi exception rồi tự coi authorization đúng.

### 35.3. Stampede protection

Nhiều misses cùng key có thể flood source. Dùng single-flight/locking có giới hạn và bounded concurrency, không giả định TTL nhỏ luôn an toàn.

### 35.4. Tenant authorization

Cache key phải được partition theo tenant; `ProductStore` và API phải xác minh quyền đọc. Cache hit không tự thay authorization.

---

## 36. MongoDB + Redis + Elasticsearch: ví dụ đánh giá thực tế

### 36.1. Ban đầu

MongoDB chứa catalog và orders. Các truy vấn text đơn giản được hỗ trợ nhưng search nâng cao bị chậm; các request đọc catalog gây tải cao lên primary.

### 36.2. Giải pháp đề xuất

- MongoDB authority cho product price, status và order state.
- Redis cache-aside cho product display.
- Elasticsearch search index cho keyword/ranking/facets.
- Outbox/CDC giữ projections bắt kịp.

### 36.3. Acceptance contracts

- Checkout đọc/chốt giá và inventory từ authorities.
- Search freshness có giới hạn đo được.
- Không trả products deleted/hidden trái policy.
- Nếu Redis mất, source không bị stampede.
- Nếu Elasticsearch mất, GET product by ID vẫn hoạt động.
- Nếu CDC gap quá retention, hệ hỗ trợ resnapshot/rebuild.

### 36.4. Khi nào không nên triển khai?

Nếu search engine tích hợp trong MongoDB hiện tại đã đạt p99, quality và TCO; nếu đội chưa có on-call/restore capability; hoặc nếu chi phí dữ liệu nhân bản vượt lợi ích dự kiến.

### 36.5. Thử nghiệm pilot

Chọn subset products/tenants, shadow compare queries và tỷ lệ click/conversion theo chính sách experiment. Không để search index pilot quyết định giá chốt đơn.

---

## 37. DynamoDB + OpenSearch + S3: kiến trúc managed có phối hợp

Một ứng dụng có thể dùng:

~~~text
DynamoDB: authoritative catalog records
Streams / outbox: change delivery
OpenSearch: text search
S3/object storage: media, exports, backups
~~~

### 37.1. Giá trị

Các writes/read-by-key có thể phù hợp DynamoDB; search queries được xử lý bởi search service; media lớn chuyển sang object storage.

### 37.2. Chi phí phối hợp

DynamoDB Streams có retention, ordering scope và event-format semantics riêng. GSI và OpenSearch không tự strong-consistent với nguồn. Phải có replay/resnapshot và reconciliation.

### 37.3. IAM và service quotas

Hệ managed vẫn cần IAM policies, encryption, VPC/network, cost quotas, throttling, backup/PITR, hot key analysis và DR.

### 37.4. Không biến OpenSearch thành “GSI không giới hạn”

Search index có mapping/analyzer/sharding/reindex và availability semantics riêng. Mỗi khi source đổi schema, cần xét impact trên projector/index template.

### 37.5. Pilot phải đo AWS thật khi cần

DynamoDB Local/LocalStack hữu ích kiểm một số SDK/API flows, nhưng không thay managed IAM/throttling/region behavior. Ghi rõ giới hạn thử nghiệm.

---

## 38. Cassandra + analytics: cách ly hai loại tải

Một hệ telemetry ghi hàng trăm nghìn events/s vào Cassandra hoặc wide-column store.

### 38.1. Nhu cầu

- Ingest dựa vào partition keys và retention.
- Truy vấn online theo device + time window.
- Analytics theo toàn quốc, 90 ngày, group-by nhiều dimensions.

### 38.2. Không biến truy vấn phân tích thành scan tùy tiện trên OLTP source

Các truy vấn cross-partition ad hoc có thể gây fan-out/I/O lớn. Một analytical store/data lake có thể cách ly workload đó.

### 38.3. Dữ liệu đến muộn

Event timestamps khác ingest timestamps. Analytics pipeline cần dedup, watermark và late-event policy.

### 38.4. Backfill cost

Nếu data lake mất, có thể rebuild từ source chỉ khi retention đủ và throughput chấp nhận được. Nếu source đã TTL xóa data cũ, lake có thể là **archive authority** cho historical fact; cần RPO/backup riêng.

### 38.5. Quyết định

Nếu reports ít và có thể batch export, một scheduled job có thể rẻ hơn streaming OLAP system.

---

## 39. Redis và relational/NoSQL chính: khi cache “lớn thành domain”

Một Redis ban đầu chỉ chứa:

~~~text
product-cache:{tenant}:{sku}
~~~

Sau hai năm thêm:

~~~text
idempotency:{paymentRequest}
queue:{fulfillment}
lease:{warehouseJob}
session:{user}
ratelimit:{tenant}
~~~

### 39.1. Tính chất đã thay đổi

Redis không còn là cache hoàn toàn disposable. Một số namespaces chứa state có side effects, authorization hoặc job ownership.

### 39.2. Cần inventory theo namespace

| Namespace | Authority? | Có thể rebuild? | Rủi ro mất |
|---|---|---|---|
| `product-cache` | Không | Có từ catalog | Backend load |
| `session` | Tùy contract | Có thể yêu cầu login lại | UX/security |
| `idempotency` | Có thể có | Chỉ nếu ledger nguồn tồn tại | Double charge |
| `queue` | Có thể có | Chỉ nếu outbox/source jobs đủ | Lost jobs |
| `lease` | Trạng thái phối hợp | Cần fencing protocol | Duplicate workers |
| `ratelimit` | Security-sensitive | Có thể có fallback | Abuse-control gap |

### 39.3. Tránh quên chi phí tăng dần

Mỗi “chỉ thêm một key” có thể chuyển cache thành cơ sở dữ liệu quan trọng mà chưa có backup/restore, DR và owner tương ứng.

---

## 40. Chọn multi-store không được phá transaction invariants

Giả sử bán 1.000 vé. Tồn kho cần:

\[
available + held + sold = capacity
\]

và:

\[
available\ge0.
\]

Nếu `available` ở Redis còn reservations ở MongoDB, hai bước riêng không tạo một transaction chung.

### 40.1. Đưa invariant về một authority

Có thể lưu state đủ để reserve atomically trong MongoDB/DynamoDB/partition owner, còn Redis chỉ cache available count.

### 40.2. Hoặc dùng reservation protocol rõ

Một service giữ quyền tài nguyên bằng durable ledger, unique token, expiry, idempotency và reconciliation; không chỉ gọi hai `save` và hy vọng cùng thành công.

### 40.3. Không dùng search result để kiểm stock

Read model eventual có thể cho số lượng đã cũ. Checkout xác nhận từ inventory authority.

### 40.4. Kiểm concurrency

Hai clients tranh last unit, failover sau commit trước ACK, retry trùng request ID, cancel/confirm race, TTL expiry và restore cũ.

---

## 41. Hai kiểu “đồng bộ dữ liệu” cần phân biệt

### 41.1. Replication cùng một database

Replicas của một cluster thường giữ cùng logical data theo protocol, phục vụ availability/read scaling và có consistency contract của engine.

### 41.2. Đồng bộ giữa hai hệ khác sản phẩm

MongoDB → Elasticsearch không phải replication tương đương về transaction, schema hay query. Nó là **transformation pipeline**:

~~~text
source version -> event serialization -> broker
-> mapper -> target index -> search visibility
~~~

### 41.3. Khi target đổi schema

Một `Decimal128` có thể được chuyển thành string/long minor units; một nested document có thể tách thành index fields. Cần mapping contract chứ không chỉ CDC bytes.

### 41.4. Rebuildability có điều kiện

Khi target mất, source + log history + mapping version + capacity phải tồn tại thì mới rebuild đúng.

---

## 42. Multi-store làm backup/restore khó hơn thế nào?

Một sự cố lúc 10:00:

~~~text
Orders DB snapshot:       09:55
Kafka processed offset:   through 09:59
Search index snapshot:    09:58
Redis keys:               current at 10:00
Payment provider:         transactions through 10:00
~~~

Nếu restore Orders về 09:55 nhưng giữ Kafka consumer offset 09:59, một số events liên quan dữ liệu chưa có sau restore có thể bị bỏ qua.

### 42.1. Cần recovery plan cho authority trước

Xác định recoverable point, dữ liệu có thể mất và external transactions cần đối soát.

### 42.2. Rebuild projections

Search/cache/analytics có thể được rebuild từ authority hoặc source snapshot + CDC nếu history đầy đủ và consistency boundary rõ.

### 42.3. Deletion/revocation

Restore cũ có thể hồi sinh PII hoặc permissions đã bị xóa/revoke. Cần deletion ledger và safety checks trước khi mở traffic.

### 42.4. Service RTO

RTO phải tính restore DB, replay backlog, reindex, cache warm-up, permissions, SDK cutover và user-visible SLO; không chỉ thời gian một backup job.

### 42.5. Thực hiện drill

Không chỉ kiểm backup của từng store. Diễn tập toàn bộ workflow quan trọng, đặc biệt order/payment/inventory/search dependencies.

---

## 43. Security coordination tax và phạm vi tấn công

Thêm mỗi hệ thường cần:

- Network segment/endpoints.
- Service identities, passwords hoặc IAM roles.
- Encryption/KMS lifecycle.
- RBAC/ACL và tenant authorization.
- Audit logs.
- Vulnerability patching.
- Secrets rotation.
- Backup access.
- Data residency policy.
- Privacy deletion/retention.
- Incident response và credential revocation.

### 43.1. Quyền tối thiểu cho projector

Search projector chỉ cần đọc events và ghi index được cấp phép, không nên có quyền xóa toàn bộ authoritative Orders DB.

### 43.2. Không sao chép PII theo kiểu “có gì sync hết”

Search index thường chỉ cần fields cho search. Giới hạn projection và mask những dữ liệu không cần.

### 43.3. Cache key phải giữ tenant boundary

`productId=123` có thể trùng giữa tenants; key phải theo scope và API authorization phải hoạt động cả khi cache hit.

### 43.4. Xóa có cascade nhưng không phải transaction toàn cục

Delete events có thể trễ, thất bại hoặc bị bỏ sót. Đối với quyền riêng tư nghiêm ngặt, cần cơ chế ngăn đọc stale record và reconciliation.

---

## 44. Observability: một request đi qua nhiều hệ

Khi người dùng báo “giá sai”, cần lần theo:

~~~text
Request trace
  -> Cache hit: product version 7
  -> Source authority: product version 8
  -> CDC captured: version 8
  -> Broker publish: event E8
  -> Search projector: processing version 8
  -> Search index visible: version 7
~~~

### 44.1. Correlation identifiers

Một `traceId`/`operationId` có thể đi qua service, outbox, broker, consumer và index document metadata theo quy định bảo mật.

### 44.2. Metrics cần thiết

- Source commit rate.
- CDC capture lag.
- Broker backlog.
- Consumer attempts/retries/dead letters.
- Projection freshness watermark.
- Search visibility lag.
- Cache hit/miss/invalidation delay.
- Reconciliation mismatch count.
- Cross-tenant/permission violation count.
- End-to-end p99 theo operation.
- Recovery point và restore drill age.

### 44.3. Không gắn user ID vào high-cardinality metrics

Dùng bounded labels theo service, operation, environment, status; chi tiết PII được ghi trong secure traces/audit theo retention phù hợp.

### 44.4. “Không thấy lỗi” có thể do monitor bị hỏng

Theo dõi cả last successful reconciliation, checker coverage và missing-event conditions.

---

## 45. Một contract cho projection có thể đo

~~~yaml
projection: product-search-v2
owner: search-platform
sourceAuthority: catalog-db
input:
  channel: catalog-events
  key: product-id
  schemaVersion: 3
target:
  engine: Elasticsearch
  indexAlias: products-current
semantics:
  ordering: per-product-version
  dedup: event-id-and-source-version
  deletes: tombstone-and-remove-visible-record
  rebuild: snapshot-plus-tail-events
  sourceOfTruthForPrice: false
freshness:
  targetP99Seconds: 10
  maxAcceptedLagSeconds: 60
security:
  tenantFilterRequired: true
  piiFieldsAllowed: []
validation:
  - shadow-search-compare
  - cross-tenant-negative-test
  - out-of-order-delete-test
  - full-index-rebuild-drill
rollback:
  - route-search-to-old-alias
  - disable-projector-writes-after-approval
~~~

### 45.1. Tài liệu này không tạo bảo đảm tự động

Cần code, tests, metrics và runbook kiểm chứng hợp đồng.

### 45.2. Freshness theo loại data

Giá hiển thị và quảng cáo có thể có budget khác permission revocation hay payment status.

### 45.3. Rollback phải gồm data authority

Rollback alias search dễ hơn rollback authoritative writes. Không áp một nút “rollback” chung cho mọi thành phần.

---

## 46. Thiết kế pilot ít rủi ro

Một lộ trình:

~~~mermaid
flowchart TD
    BASE["Baseline one-store metrics"] --> POC["Isolated proof-of-concept"]
    POC --> SHADOW["Shadow writes / reads"]
    SHADOW --> COMPARE["Correctness + latency + cost comparison"]
    COMPARE --> GATE{"Benefits exceed coordination cost?"}
    GATE -->|No| STOP["Keep one-store / simplify"]
    GATE -->|Yes| CANARY["Small tenant/cohort canary"]
    CANARY --> EXPAND["Gradual rollout"]
    EXPAND --> OPERATE["Operate + audit realized value"]
~~~

### 46.1. POC

Kiểm engine feature phù hợp, không chỉ chạy một hello-world query.

### 46.2. Shadow

Đọc source và target song song để so kết quả nhưng **không** phục vụ target result cho giao dịch quan trọng khi chưa qua gate.

### 46.3. Dual write phải phân biệt

Nếu chọn dual write, cần hiểu partial failure và reverse sync. Cách thường ít rủi ro hơn cho read projection là authoritative write + outbox/CDC.

### 46.4. Canary theo cohort

Thử một tập tenants/sản phẩm/regions có thể cô lập; đo lag, mismatch, p99 và chi phí.

### 46.5. Expand

Tăng traffic từng bước, có rollback routes và observation windows. Không xóa source/index cũ ngay khi vừa switch.

### 46.6. Realized-value review

Sau 30/90 ngày (mốc minh họa), so chi phí thực và business outcome với dự báo; nếu không đạt, xem xét giảm kiến trúc.

---

## 47. Chọn thử nghiệm nào để chứng minh lợi ích?

Một bộ POC phải chứng minh:

1. Query correctness trên data distribution đại diện.
2. p95/p99 latency dưới peak và normal traffic.
3. Throughput/compute cost.
4. Index/update/write amplification.
5. Source-to-target freshness.
6. Backlog recovery sau consumer downtime.
7. Duplicate/out-of-order CDC handling.
8. Security/tenant isolation.
9. Delete/TTL and schema evolution.
10. Failure/degraded mode.
11. Restore/rebuild duration.
12. Operation cost và on-call overhead.
13. Compatibility với Java driver/SDK.
14. Độ dễ của migration/rollback.
15. Chi phí nhân lực và đào tạo.

### 47.1. Test trên dữ liệu nhỏ không đủ

Một query chạy 20 ms trên 10.000 records không chứng minh 250 ms p99 trên 80 triệu records.

### 47.2. Có giới hạn đo mà không cần phá production

Dùng staging/isolated replicas và synthetic load được cấp phép; tránh tạo destructive chaos trên production ngoài chương trình đã duyệt.

---

## 48. Decision gates: khi nào chấp nhận thêm hệ?

Có thể dùng những **hard gates**:

| Gate | Ví dụ yêu cầu |
|---|---|
| Correctness | Không phá inventory/payment/tenant invariants |
| Authority | Mỗi fact có owner/source of truth |
| Query | Target đáp ứng required access patterns |
| Freshness | Lag trong budget của feature |
| Reliability | Degraded mode và retry bounded |
| Recoverability | Rebuild/restore trong RTO |
| Security | IAM/TLS/PII/deletion policy đạt |
| Operability | Có owner, runbook, alerts và SLO |
| Cost | TCO năm 1–3 và giới hạn budget hợp lý |
| Reversibility | Canaries/rollback/point-of-no-return rõ |

Chỉ khi hard gates đạt mới xét điểm số lợi ích.

### 48.1. Một hard gate chưa đủ bằng chứng = UNKNOWN

Không cho `PASS` giả vì deadline hoặc kết quả emulator không đại diện.

### 48.2. `PASS` cần scope

Ví dụ “Search freshness p99 < 10 s trên 5 triệu records, một region, không failover” là kết luận giới hạn, chưa chứng minh under 100 triệu và region loss.

---

## 49. Anti-pattern: truy vấn đồng bộ xuyên ba nguồn trên đường nóng

Một endpoint:

~~~text
GET /order-page
  -> Orders DB
  -> Payment DB
  -> Inventory DB
  -> Search service
  -> Recommendations
  -> merge response
~~~

### 49.1. Fan-out tăng latency và rủi ro

p99 của response bị chi phối bởi các dependency chậm nhất; retries/cancellation có thể làm tải tăng.

### 49.2. Có thể dùng read model riêng

Nếu cùng một trang cần dữ liệu tổng hợp rất thường xuyên, dựng projection được version hóa cho page view, chấp nhận freshness contract rõ và đối chiếu authority khi thực hiện hành động quan trọng.

### 49.3. Không gộp tùy tiện

Một dashboard có thể cho phép stale, còn “xác nhận tồn kho” phải kiểm tại authority. Tách GET display với POST commit.

### 49.4. Circuit breaker và partial response

Có thể trả trang thiếu recommendations nếu hệ đó lỗi, không nhất thiết làm GET order trả 500. Nhưng không được ẩn việc payment trạng thái `UNKNOWN` thành `PAID`.

---

## 50. Anti-pattern: event-driven nghĩa là không còn consistency problem

Events giúp giảm synchronous coupling nhưng tạo **temporal coupling**:

- Producer đổi schema.
- Consumer lag.
- Out-of-order events.
- Dead letters.
- Backfill race.
- Duplicate side effects.
- Replay after restore.
- Misconfigured retention.
- Broken watermark.
- Permission/deletion propagation delay.

### 50.1. Cần schema contract

Avro/Protobuf/JSON schema với version policy và consumer compatibility tests; không thay tên field phá read model không có migration plan.

### 50.2. Dedupe và ordering

At-least-once delivery là thường gặp; consumer phải xử lý repeat/old versions.

### 50.3. Reconciliation là tuyến phòng thủ

Một job có thể so source authoritative records với target theo shard/tenant/time/version để phát hiện missing hoặc corrupt projections. Không nên chỉ dựa vào metric `consumer_connected=1`.

---

## 51. Anti-pattern: mọi data được copy sang mọi hệ

Copy toàn bộ user profile, payment details, token và audit documents vào cache/search/analytics “cho tiện” có thể:

- Tăng data transfer và storage.
- Tăng PII exposure.
- Làm privacy delete khó.
- Tạo schema evolution burden.
- Làm quyền truy cập khó kiểm soát.
- Tăng chi phí encryption/backup.
- Tăng sự cố stale authorization.

### 51.1. Projection theo nhu cầu

Search index chỉ giữ fields cần tìm kiếm/hiển thị; analytics giữ aggregate/pseudonymized data khi phù hợp; Redis chỉ giữ cache fields tối thiểu.

### 51.2. Có lineage

Để xóa/update một record từ source, phải biết bản sao nằm đâu và propagation behavior ra sao.

### 51.3. Mỗi bản sao cần retention policy

Không để cache TTL 90 ngày cho dữ liệu mà source đã xóa theo policy sau 7 ngày.

---

## 52. Anti-pattern: nhiều hệ nhưng không có đường rút lui

Một hệ mới có thể bị đánh giá lại sau khi chi phí tăng hoặc hiệu quả không đạt. Nếu mọi service đã phụ thuộc trực tiếp vào query DSL riêng và không có owner/schema contract, việc gỡ bỏ rất khó.

### 52.1. Adapter boundaries

Ẩn engine-specific queries ở repository/ports thay vì rải raw query expressions khắp service code.

### 52.2. Versioned data contract

Giữ event schema và migration mapping có version, tránh để consumers tự parse tùy tiện.

### 52.3. Rebuild path

Có script/quy trình tạo lại projections từ authority, với time/cost estimate đã diễn tập.

### 52.4. Feature flags và canary

Cho phép giảm traffic tới read model mới, quay về read path cũ nếu vẫn đáp ứng SLO.

### 52.5. Point of no return

Khi hệ mới bắt đầu ghi authoritative state duy nhất, rollback khó hơn nhiều. Ghi thời điểm và approval cụ thể trước khi vượt mốc.

---

## 53. Chọn cách phối hợp: sync call, event hay batch?

| Cách phối hợp | Phù hợp khi | Đánh đổi |
|---|---|---|
| Synchronous API call | Phải quyết định nghiệp vụ ngay | Latency/availability coupling |
| Async event/outbox | Cập nhật read model, downstream reactions | Lag, duplicates, ordering, replay |
| CDC | Bắt thay đổi source để tạo projection | Change-log semantics và retention |
| Scheduled batch export | Báo cáo ít yêu cầu freshness | Dữ liệu theo lô, rebuild window |
| Cache-aside | Đọc lặp lại, có authority | Invalidation/staleness/stampede |
| Dual write | Giai đoạn migration cần kiểm soát | Partial failure, reconciliation |
| Global transaction | Invariant cần nhiều records trong supported boundary | Cost/limits/coordination |
| Saga | Cross-service workflow dài | Compensation/idempotency/UNKNOWN |
| Query federation | Ad hoc/reporting, không phải hot path mặc định | Fan-out/network/cost |

### 53.1. Chọn mức phối hợp thấp nhất đáp ứng nghiệp vụ

Nếu analytics cho phép trễ 1 giờ, dùng batch có thể an toàn và rẻ hơn streaming tức thời.

### 53.2. Không xem “real-time” là miễn phí

Freshness gần 0 có thể đòi synchronous coordination hoặc replication có semantics cao hơn; chi phí/durability/failure model tăng.

---

## 54. Risk register cho polyglot persistence

| Rủi ro | Dấu hiệu | Biện pháp |
|---|---|---|
| Two authorities for same fact | Source/search đều nhận writes | Domain ownership, single command path |
| Lost event on dual-write | DB commit nhưng publish fail | Transactional outbox |
| Duplicate consumer effect | Same event redelivered | Idempotent inbox/receipt |
| Out-of-order overwrite | v7 đến sau v8 | Version guard |
| Tombstone lost | Delete v9 bị backfill v6 ghi đè | Tombstone/version retention |
| CDC gap | Consumer offline vượt retention | Resnapshot/reconcile |
| Search stale price | Checkout lấy giá từ index | Verify/chốt tại authority |
| Cache stampede | Redis fail, source QPS spike | Bounded fallback/single-flight |
| Availability multiplication | Hot path cần 5 dependencies | Degraded mode, async boundaries |
| Global uniqueness break | Multi-region independent accepts | Ownership/coordination |
| Cross-tenant leak | Search filter/cache key thiếu tenant | Auth negative tests |
| Privacy deletion gap | Search/analytics giữ PII | Deletion propagation, audit |
| DR inconsistent cut | DB rewind, offsets mới hơn | Recovery orchestration |
| Version mismatch | Producer đổi event schema | Schema registry/contract tests |
| Unexpected cost | Egress/index/ops tăng | TCO monitoring and budgets |
| Vendor lock-in | Raw SDK everywhere | Ports/adapters, exit plan |
| On-call overload | Không owner chuyên môn | Training, runbooks, managed service |
| Overengineered analytics | Stream real-time dù báo cáo hàng ngày | Batch alternative |
| Unknown side effects | Payment timeout retried | Request ledger/reconciliation |
| Insufficient load headroom | Catch-up luôn chậm hơn ingress | Capacity modeling |

Rủi ro critical chưa có owner/mitigation/test phải được đánh dấu blocker trong decision record.

---

## 55. Ma trận 36 bài kiểm thử trước khi quyết định triển khai

| ID | Tình huống | Điều phải chứng minh |
|---|---|---|
| P01 | Workload tối ưu trên một hệ | Baseline khách quan |
| P02 | Search POC trên corpus đại diện | p99/quality/cost đạt |
| P03 | Cache hits under peak | Giảm source QPS đo được |
| P04 | Cache mất hoàn toàn | Source không bị stampede |
| P05 | Search down | Checkout/GET by ID vẫn theo degraded contract |
| P06 | Broker down | Outbox giữ intent, source writes an toàn |
| P07 | Relay crash sau publish | Redelivery không nhân effect |
| P08 | CDC event duplicate | Target idempotent |
| P09 | CDC event version cũ | Version guard không overwrite |
| P10 | Delete v9 rồi backfill v6 | Không resurrect |
| P11 | Consumer offline vượt retention | Rebootstrap chứ không skip |
| P12 | Target throttling | Queue/backoff bounded |
| P13 | Lag vượt freshness SLO | Alert/degraded behavior |
| P14 | Hot tenant tạo skew | Capacity và isolation |
| P15 | Transactional order + outbox | Không có business commit thiếu intent |
| P16 | Timeout sau source commit | Request ID/reconcile đúng |
| P17 | Concurrent inventory reserve | Không oversell |
| P18 | Payment provider retry | Không double charge |
| P19 | Cross-domain saga failure | Compensation đúng |
| P20 | Search trả giá stale | Checkout xác nhận authority |
| P21 | Tenant A search record B | Denied/no leakage |
| P22 | Tenant ID cache collision | Không cross-tenant |
| P23 | Revoked permission và cached token | Fail closed theo contract |
| P24 | Delete PII trong source | Propagated to projections |
| P25 | Key rotation | Projector/DR credentials vẫn đúng |
| P26 | Schema v2 producer, v1 consumer | Compatibility policy |
| P27 | MongoDB → search index rebuild | Full index đúng, thời gian đạt RTO |
| P28 | DynamoDB Stream lost horizon | Reconciliation/reseed |
| P29 | Cassandra analytics lag | Batch/CDC capacity đủ |
| P30 | Redis primary failover | Durable expectations được đo đúng |
| P31 | Search shard relocation | SLO/degraded mode phù hợp |
| P32 | Primary region recovery | Authority/cutover không split-brain |
| P33 | Restore DB về quá khứ | Offset/deletion/payment reconcile |
| P34 | Source count = target count nhưng IDs khác | Diff checker tìm mismatch |
| P35 | Data grows 5×, throughput steady | TCO và rebuild headroom |
| P36 | Migrate back to one-store option | Exit/rollback path khả thi |

Phân phối tests theo PR/nightly/release/DR lanes. Không tạo destructive faults ở production ngoài chương trình có phê duyệt.

---

## 56. Runbook ra quyết định trong 12 bước

### Bước 1 — Chốt vấn đề nghiệp vụ

Ví dụ: “Search product p99 đang 900 ms, mục tiêu 250 ms, gây giảm conversion.” Không dùng vấn đề mơ hồ như “MongoDB không hiện đại”.

### Bước 2 — Ghi hợp đồng

Workload, data size, hot keys, freshness, security, correctness, SLO, RPO/RTO.

### Bước 3 — Kiểm tối ưu một hệ

Index, query, caching/local enhancements, batching và native features.

### Bước 4 — Chọn phương án

Một hệ; một hệ với read replicas; một hệ với search native; một authority + derived specialized store; nhiều domain authorities; hoặc full multi-store.

### Bước 5 — Đặt hard constraints

Security/privacy, business invariants, data authority, latency/throughput, DR.

### Bước 6 — Lập TCO/coordination budget

Hạ tầng, egress, replication, operations, engineering, incident, migrations.

### Bước 7 — POC với dữ liệu đại diện

Đo cả query và update/index costs, peak/normal và cold/warm.

### Bước 8 — Thiết kế data flow

Command authority, outbox/CDC/batch, dedupe/version, retention, deletes và reconciliation.

### Bước 9 — Test failure paths

Cache/search down, broker lag, partial writes, retry, restore, tenant isolation và unknown outcomes.

### Bước 10 — Canary

Shadow/canary theo cohort, so business outcomes, p99, freshness và costs.

### Bước 11 — Go/no-go

Owner review với bằng chứng và những limitations còn lại.

### Bước 12 — Hậu triển khai

Audit realized value, SLA/cost drift, training/runbooks và trigger để đơn giản hóa hoặc mở rộng.

---

## 57. Một mẫu Architecture Decision Record

~~~markdown
# ADR: Tách tìm kiếm sản phẩm khỏi authoritative catalog

## Vấn đề
Search p99 vượt SLO trên workload peak hiện tại;
đã thử tối ưu native index theo danh sách kèm bằng chứng.

## Quyết định đề xuất
Giữ Catalog DB authoritative;
dùng Search Engine làm read projection qua outbox/CDC.

## Phạm vi
Trong scope: keyword search, facets, autocomplete.
Ngoài scope: checkout pricing, inventory reservation.

## Hợp đồng
Source version theo productId, at-least-once events.
Target applies only newer version.
Deletes propagate; tenant filter enforced.
Search freshness <= business-approved target.

## Phương án so sánh
A: một engine hiện tại, tối ưu.
B: native search feature.
C: dedicated search service.

## Lợi ích định lượng
p99, conversion, source CPU, feature velocity.

## Chi phí/rủi ro
Infrastructure, CDC, ops, security, DR, reindex.

## Validation
Shadow reads, full rebuild, replay, failure tests.

## Rollback
Feature flag, old read path nếu còn đủ capability;
không đổi source authority.

## Owners
Business, engineering, SRE, security, finance.

## Review
Pilot gate, 30/90-day realized-value review.
~~~

### 57.1. ADR không phải một quyết định không thể đổi

Khi dữ liệu, giá cloud, đội ngũ hoặc business thay đổi, ghi ADR mới để đánh giá lại.

### 57.2. Quyết định phải có người ký

Kỹ thuật không tự quyết risk acceptance về privacy, thanh toán hay ngân sách nếu không có owner phù hợp.

---

## 58. Bài tập 1 — Chọn một hay nhiều hệ?

Một Java application có:

~~~text
2 million product records
10 million order records
Peak 800 reads/s
Peak 150 writes/s
Full-text search p99: 200 ms
Business search SLO: 300 ms
Nightly analytics job: 12 minutes
Operational team: 2 engineers
~~~

1. Đã có bằng chứng cần Elasticsearch/OLAP chưa?
2. Những tối ưu một hệ nào nên xem trước?
3. Ưu tiên correctness/DR/on-call ra sao?
4. Khi nào cần thử thêm Redis?
5. Thiết kế baseline metrics và decision gates.
6. Nêu một thay đổi workload khiến quyết định phải xem lại.

---

## 59. Bài tập 2 — Tính lợi ích ròng và sensitivity

Giả sử:

~~~text
Expected conversion/business gain:    900 triệu VND/năm
Source compute savings:               300 triệu VND/năm
New infrastructure:                   250 triệu VND/năm
CDC/network:                          170 triệu VND/năm
Operations/personnel:                 400 triệu VND/năm
One-time migration:                   300 triệu VND
Risk/incident reserve:                150 triệu VND/năm
~~~

1. Tính lợi ích ròng năm đầu.
2. Tính recurring benefit/cost các năm sau nếu giả định khác không đổi.
3. Nếu business gain thấp hơn dự báo 40%, quyết định có đổi không?
4. Nêu các mục chưa thể định lượng dễ.
5. Liệt kê hard constraints có thể làm phương án không hợp lệ dù lợi ích ròng dương.
6. Đề xuất mốc review sau pilot.

---

## 60. Bài tập 3 — Thiết kế order authority với search projection

Một hệ:

~~~text
Orders DB: orders, payments summary
Search: orders_search
Broker: order events
~~~

Hãy:

1. Chọn authority cho `order.status`.
2. Xác định `OrderCreated`, `OrderPaid`, `OrderDeleted` event schema.
3. Thiết kế transactional outbox boundary.
4. Dùng `sourceVersion` để chống reorder.
5. Thiết kế dedupe khi event redelivered.
6. Thiết kế deletion propagation.
7. Đặt search freshness SLO.
8. Thiết kế reindex/rebuild và restore drill.
9. Không cho search ảnh hưởng transaction safety thế nào?

---

## 61. Bài tập 4 — Phân tích cache correctness

Redis cache giá hàng hóa:

~~~text
TTL = 15 minutes
Catalog price changes every 10 minutes during promotion
Checkout must never charge stale/unapproved price
~~~

1. Cache TTL này có thể phục vụ product display không?
2. Vì sao checkout không thể tin giá cached?
3. Đặt version/ETag/invalidation policy.
4. Phân biệt display freshness và charge correctness.
5. Thiết kế test Redis unavailable.
6. Thiết kế test stampede và tenant isolation.
7. Xác định khi nào cache có lợi ròng.

---

## 62. Bài tập 5 — Tính backlog và recovery

Nguồn phát 15.000 events/s. Consumer search xử lý 18.000 events/s. Sau outage backlog 21.600.000 events.

1. Tính thời gian bắt kịp lý tưởng.
2. Nếu consumer chỉ xử lý 12.000 events/s sau failover thì sao?
3. Nếu broker retention chỉ đủ 1 giờ ở peak volume, cần cảnh báo gì?
4. Thiết kế giải pháp replay/resnapshot.
5. Nếu data có hot partitions, global average đủ đánh giá không?
6. Đặt cutover/recovery gates dựa trên watermark.

---

## 63. Bài tập 6 — Chọn graph hay denormalization?

Một hệ chống gian lận cần truy vấn:

~~~text
Find users connected by 3+ hops
through accounts, devices, phones, merchants, addresses.
~~~

1. Thiết kế POC trên engine hiện tại và graph engine.
2. Xác định nodes, edges, update frequency.
3. Đặt query latency/correctness objectives.
4. Tính chi phí đồng bộ graph projection.
5. Chọn source authority cho user/device facts.
6. Kiểm delete/PII/tenant boundaries.
7. Thiết kế fallback khi graph service down.
8. Khi nào không nên thêm graph database?

---

## 64. Bài tập 7 — Chẩn đoán lỗi phối hợp nhiều hệ

Sau deploy:

~~~text
MongoDB order version: 12
Kafka broker backlog: growing
Search index version: 10
Redis cached version: 9
Payment provider: captured
Java checkout API: returning SUCCESS
~~~

Yêu cầu:

1. Fact nào authoritative?
2. Trạng thái nào chấp nhận stale và trong bao lâu?
3. Nếu client đọc search rồi cancel order, đường ghi phải làm gì?
4. Nếu idempotency ledger chỉ ở Redis, rủi ro là gì?
5. Đề xuất alerts và reconciliation.
6. Thiết kế incident playbook và degraded mode.
7. Khi nào tạm dừng writes?
8. Cần những bằng chứng nào để tuyên bố restored?

---

## 65. Bài tập 8 — Decision review cho kiến trúc năm hệ

Hệ hiện có:

~~~text
MongoDB + Redis + Kafka + Elasticsearch + OLAP
~~~

Data platform có 3 kỹ sư trực on-call. Search traffic giảm 70%; analytics báo cáo mỗi ngày, cache hit rate chỉ 12%; CDC vận hành mất 30% thời gian kỹ sư.

Hãy:

1. Lập danh sách workload và operational cost hiện tại.
2. Xác định hệ nào vẫn tạo giá trị lớn.
3. Tính thử đơn giản hóa cache, analytics hoặc event pipeline.
4. Kiểm điều gì sẽ mất khi bỏ mỗi hệ.
5. Xây phương án migration ngược và rollback.
6. Chọn một pilot giảm độ phức tạp.
7. Kiểm data ownership, deletion, security và DR.
8. Soạn ADR mới với hard gates và metrics.

---

## 66. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Mỗi tính năng nên có database riêng.” | Mỗi database mới cần bằng chứng lợi ích ròng |
| “Một database luôn kém hơn polyglot.” | Đơn giản giúp correctness/vận hành nếu đủ đáp ứng |
| “NoSQL engine A nhanh hơn B trong mọi workload.” | Phải đo access pattern và topology cụ thể |
| “Tách search khiến mọi writes nhanh hơn.” | Còn CDC/outbox/index cost và load |
| “Có Kafka là đồng bộ exactly-once.” | Delivery, effects, ordering là hợp đồng riêng |
| “CDC là backup thay PITR.” | Retention/gaps/scope khác backup |
| “Dual-write trong try/catch là atomic.” | Partial failure và unknown outcome |
| “Search index có thể dùng quyết định giá.” | Checkout cần authoritative state |
| “Cache hit đồng nghĩa dữ liệu hợp lệ.” | TTL/permission/version có thể stale |
| “Redis chỉ là cache.” | Một số namespace giữ state critical |
| “Eventual consistency là không cần kiểm.” | Cần freshness/version/reconciliation |
| “Mọi event có tổng thứ tự.” | Thường chỉ theo partition/entity |
| “Dedupe dùng mỗi eventId là đủ mọi tình huống.” | Cần ordering/recreation/epoch semantics |
| “Version số lớn hơn luôn mới hơn.” | Cần source monotonic version contract |
| “Một backend phụ thuộc thêm không ảnh hưởng availability.” | Hot-path coupling có cost |
| “Fallback sang stale replica luôn tốt hơn lỗi.” | Có thể phá safety contract |
| “Bản sao dẫn xuất không cần backup.” | Có thể cần backup để đáp RTO |
| “Full-text feature tự chứng minh cần Elasticsearch.” | Có thể dùng native search |
| “Có graph edge là phải có graph database.” | Query cost/volume quyết định |
| “OLAP luôn phải stream real-time.” | Batch đủ nếu freshness cho phép |
| “Managed DB nghĩa không cần SRE.” | IAM/quota/DR/schema/metrics vẫn cần |
| “TCO chỉ là hóa đơn cloud.” | Người, incidents, migration, egress cũng tính |
| “Có benchmark p50 đủ quyết định.” | p99, skew, scale, recovery cần đo |
| “Count target bằng source nghĩa sync đúng.” | IDs/versions/deletes có thể lệch |
| “Quorum của một engine đảm bảo cross-engine transaction.” | Mỗi boundary khác nhau |
| “One application method tương đương one global commit.” | Không tự atomic qua nhiều systems |
| “Privacy deletion ở source là xong.” | Cache/search/analytics/backup cần policy |
| “Một lần POC pass cho production scale.” | Cần tests đại diện và limitations |
| “Một ADR là vĩnh viễn.” | Phải review theo dữ liệu/chi phí/rủi ro mới |
| “Rollback chỉ cần đổi feature flag.” | Authority và reverse sync có thể khác |
| “Không có lỗi khi replay là dữ liệu đã hội tụ.” | Cần watermark/independent oracle |
| “Thêm database vì đội thích học” | Giá trị học tập không thay ROI/risk |
| “Dùng 5 hệ là hiện đại hơn dùng 2 hệ.” | Số hệ không đo chất lượng kiến trúc |
| “Search down thì checkout phải down.” | Đường nóng nên tránh phụ thuộc không cần |
| “Security là việc của source DB.” | Mỗi read path là surface riêng |
| “RPO/RTO của từng store là RTO toàn ứng dụng.” | Cần diễn tập end-to-end |
| “Metrics không có mismatches chứng minh mọi thứ đúng.” | Checker coverage/gaps cần theo dõi |
| “Cắt một hệ là luôn giảm rủi ro.” | Có thể mất tính năng/availability isolation |

---

## 67. Checklist trước khi lựa chọn kết hợp nhiều hệ

- [ ] Có business problem và access pattern được đo rõ.
- [ ] Đã thử hoặc đánh giá tối ưu hợp lý trên một engine.
- [ ] Đã xem khả năng native index/search/analytics/replicas.
- [ ] Có baseline p95/p99, throughput, error rate, headroom.
- [ ] Có dataset size/growth/peak/hot key distribution.
- [ ] Có danh sách hard correctness/security constraints.
- [ ] Mỗi business fact có source authority/owner rõ.
- [ ] Derived stores không được viết authoritative state tùy tiện.
- [ ] Có map read/write paths và synchronous dependencies.
- [ ] Có freshness budget per feature/query.
- [ ] Có versioning, deduplication và out-of-order handling.
- [ ] Có transactional outbox hoặc giải pháp tránh dual-write gap.
- [ ] Có source snapshot + CDC replay/rebootstrap plan.
- [ ] Có reconciliation oracle độc lập và alert.
- [ ] Có handling cho deletes, TTL, revocations và PII.
- [ ] Có tenant isolation trong cache/search/analytics.
- [ ] Có KMS/IAM/RBAC/TLS và least privilege per system.
- [ ] Có managed quotas/cost and scaling assumptions.
- [ ] Có failure and degraded mode per dependency.
- [ ] Có bounded retries/backpressure/admission controls.
- [ ] Không để search/cache quyết định inventory/payment safety.
- [ ] Có schema evolution/contract tests.
- [ ] Có backup/recovery runbook cho authority và projections.
- [ ] Có end-to-end restore/cutover/failback practice.
- [ ] Có projectors/reindex rebuild time trong RTO.
- [ ] Có TCO infra+people+network+DR+incident budget.
- [ ] Có risk register và owner cho critical gaps.
- [ ] Có POC trên dữ liệu và workload đại diện.
- [ ] Có shadow read/comparison, canary và rollback.
- [ ] Có metric để xác minh realized value sau deploy.
- [ ] Có điểm đánh giá lại và cơ chế bỏ hệ không còn giá trị.
- [ ] Có kiến trúc ports/adapters tránh driver leak khắp code.
- [ ] Có quyết định ADR được phê duyệt với những giả định rõ.
- [ ] Không coi test chưa chạy hoặc service không đại diện là PASS.
- [ ] Không dùng dữ liệu PII/production credentials trái chính sách khi benchmark.
- [ ] Nếu lợi ích chưa vượt coordination tax, giữ phương án đơn giản hơn.

---

## 68. Tổng kết

**Kết hợp nhiều NoSQL systems có thể giải quyết những workload rất khác nhau, nhưng mỗi hệ mới cũng mang vào kiến trúc thêm độ trễ, quyền truy cập, data contracts, synchronization, failure modes, backup/restore và gánh nặng vận hành.** Quyết định đúng không phải là chọn nhiều công nghệ nhất, mà là chọn **số hệ tối thiểu đáp ứng các yêu cầu bắt buộc với tổng chi phí và rủi ro được chấp nhận**.

Những nguyên tắc chính:

1. **Bắt đầu từ nhu cầu và benchmark, không từ tên database.** Chỉ bổ sung công nghệ khi một vấn đề đo được chưa có giải pháp đơn giản đủ tốt.
2. **Giữ ranh giới authoritative rõ.** Một fact không nên được ghi độc lập vào nhiều stores khi không có conflict protocol.
3. **Dùng projections/cache cho những reads thích hợp.** Search, analytics và catalog cache có thể stale trong một budget; inventory và payment decisions phải đi theo authority.
4. **Tính coordination tax đầy đủ.** Outbox, CDC, schema evolution, dedup, reorder, reconciliation, security và DR là chi phí thực.
5. **Tránh synchronous coupling không cần thiết.** Một lỗi search không nên mặc nhiên chặn checkout.
6. **Thiết kế cho lỗi, không chỉ happy path.** Timeout sau commit, consumer backlog, duplicate event, delete resurrection và restore sai checkpoint thường là rủi ro quyết định.
7. **Đánh giá cả TCO và hiệu quả kinh doanh.** Hạ tầng rẻ hơn chưa chắc tổng hệ rẻ hơn nếu nhiều kỹ sư phải trực vận hành.
8. **Giữ khả năng đảo ngược.** Ports/adapters, source-of-truth separation, shadow/canary và rebuild path giúp thay đổi khi giả định không còn đúng.
9. **Test trước khi mở rộng.** Dùng workload thật, p99, consistency, recovery và security gates để quyết định.
10. **Tái đánh giá theo thời gian.** Công nghệ, traffic, SLO, nhân lực và chi phí đều thay đổi; một hệ chuyên dụng hôm nay có thể không còn đáng vào năm sau.

**Câu cần nhớ: “Mỗi database thêm vào phải chứng minh giá trị của chính nó — không chỉ chạy một truy vấn nhanh hơn, mà còn bù được mọi chi phí giữ dữ liệu đúng, đồng bộ được, bảo mật được, khôi phục được và vận hành được khi có sự cố.”**
