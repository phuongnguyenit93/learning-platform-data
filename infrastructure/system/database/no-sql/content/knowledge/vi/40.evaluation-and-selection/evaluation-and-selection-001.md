# Xây dựng bảng tiêu chí từ truy vấn, dữ liệu và mức phục vụ mục tiêu

Khi lựa chọn một cơ sở dữ liệu NoSQL cho ứng dụng Java, nhóm kỹ thuật thường nhận được những lời đề xuất khác nhau: “Redis rất nhanh”, “MongoDB linh hoạt”, “Cassandra chịu nhiều ghi”, “DynamoDB giảm vận hành”, “Graph database giải quyết quan hệ”, hoặc “Giữ SQL vì giao dịch quan trọng”. Những nhận xét này chỉ có giá trị khi gắn với **truy vấn thực, phân bố dữ liệu, mục tiêu chất lượng dịch vụ và bất biến nghiệp vụ**. Cùng một sản phẩm có thể rất phù hợp chức năng tra cứu theo khóa nhưng không phù hợp màn hình cần nhiều filter; phù hợp một projection được phép trễ nhưng không đủ điều kiện làm nguồn sự thật của giao dịch thanh toán.

Bài thuộc **Database No SQL → Đánh giá và lựa chọn** hướng dẫn xây dựng một **bảng tiêu chí có thể kiểm chứng** thay cho danh sách ưu/nhược điểm chung. Phương pháp bắt đầu từ ba nhóm yêu cầu:

1. **Truy vấn và thao tác:** cần đọc/ghi những gì, theo khóa nào, phân trang/sắp xếp ra sao, có nhiều JOIN/traversal hay không, bao nhiêu thao tác đồng thời, truy vấn nào quan trọng nhất.
2. **Dữ liệu:** bao nhiêu bản ghi, kích thước phân bố như thế nào, quan hệ và vòng đời ra sao, bao nhiêu tenant, tỷ lệ tenant lớn, cập nhật/xóa/TTL, schema versions và độ nhạy thông tin.
3. **Mức phục vụ mục tiêu:** latency p95/p99, throughput, tính đúng, nhất quán, độ mới của dữ liệu dẫn xuất, availability, RPO/RTO, bảo mật, chi phí và khả năng vận hành.

Từ đó nhóm xây **điều kiện bắt buộc (hard gates)**, xác định mô hình lưu trữ khả thi, lập thí nghiệm/PoC và mới chấm **các tiêu chí có thể đánh đổi bằng trọng số**. Bài có ví dụ bảng tiêu chí, công thức điểm, Java 21, cách so SQL và các họ key–value/document/wide-column/graph/search, phương pháp benchmark, thí nghiệm lỗi và cấu trúc Architecture Decision Record (ADR).

> **Nguyên tắc:** **Đừng chọn công nghệ rồi mới tìm workload phù hợp.** Bắt đầu từ hợp đồng nghiệp vụ và dữ liệu, cho từng ứng viên một cơ hội thiết kế mô hình truy cập tối ưu của nó, đo bằng cùng yêu cầu end-to-end, và loại phương án không đạt điều kiện bắt buộc. Điểm tổng cao **không thể bù** lỗi double-book, lộ dữ liệu tenant khác hoặc không khôi phục được trong mục tiêu.

> **Phạm vi:** Số QPS, latency, kích thước, trọng số, điểm đánh giá và giới hạn trong bài đều là ví dụ giáo dục, **không phải benchmark của bất kỳ hãng nào**. Cơ chế transaction, index, backup, consistency, quota và region của một sản phẩm phụ thuộc phiên bản, cấu hình, tier, topology và SDK; khi áp dụng phải kiểm chứng tài liệu và đo tại môi trường được phép.

## 1. Kết quả đầu ra mong đợi

Một hoạt động đánh giá đúng phải tạo được:

- **Danh mục truy vấn** với ID, filters, sorts, keys, output, tần suất và SLO.
- **Hồ sơ dữ liệu** có cardinality, kích thước, skew, tăng trưởng và retention.
- **Bản đồ bất biến**: ai sở hữu sự thật, ranh giới atomic, uniqueness, authorization, idempotency.
- **Danh sách hard gates** và phép thử đạt/trượt.
- **Danh sách candidate architectures** không giới hạn vào một DB duy nhất.
- **Ma trận tiêu chí có trọng số**, rubric có neo và evidence IDs.
- **Kết quả PoC** có correctness, p99, timeout, resource usage và chi phí.
- **Phân tích độ nhạy** khi workload/requirements thay đổi.
- **ADR** ghi lựa chọn, phương án bị loại, rủi ro, migration, rollback và ngưỡng xem lại.

Tài liệu cuối phải trả lời: **Vì sao phương án này phù hợp hơn trong phạm vi nào, bằng chứng ở đâu và khi nào nhận định có thể không còn đúng?**

### 1.1. Không đánh giá một engine cho mọi vai trò

Một hệ đặt chỗ có thể giữ:
- SQL làm write authority của booking/inventory/payment.
- Document projection cho màn hình booking detail.
- KV cache cho point reads.
- Wide-column cho timeline dài theo customer.
- Search index cho tìm property theo từ khóa.
- Graph projection cho recommendation nhiều hop.

Đó là những **vai trò khác nhau**. Việc một cache nhanh hơn một nguồn giao dịch không chứng minh nó có thể thay nguồn giao dịch.

### 1.2. “Đúng” phải đứng trước “nhanh”

Một query trả trong 3 ms nhưng thiếu tenant predicate là lỗi nghiêm trọng. Một write báo thành công trong 15 ms nhưng retry tạo hai booking cho cùng operationId cũng không thể chấp nhận. Performance chỉ có nghĩa khi **kết quả, phạm vi quyền và độ bền đã được định nghĩa**.

## 2. Bản đồ quy trình

~~~~mermaid
flowchart TD
    Q["Inventory queries and commands"] --> C["Query catalog"]
    D["Data profile, growth and skew"] --> P["Data constraints"]
    S["SLI/SLO, invariants, RPO/RTO"] --> H["Hard gates and measurable rubrics"]
    C --> A["Candidate data models"]
    P --> A
    A --> E["Representative PoC and tests"]
    H --> E
    E --> F{"Mandatory gates pass?"}
    F -->|No| R["Reject or require redesign"]
    F -->|Yes| W["Weighted matrix and uncertainty"]
    W --> T["Sensitivity, cost and operations review"]
    T --> ADR["Architecture Decision Record"]
~~~~

Quy trình có thể quay lại bước model nếu một PoC cho thấy shard key hoặc read pattern sai; **không cố giữ phương án ban đầu chỉ vì đã đầu tư thời gian**.

## 3. Tình huống xuyên suốt: nền tảng booking đa tenant

Giả sử hệ có:
- 30 triệu booking; ba năm sau dự kiến 300 triệu.
- 10.000 tenants; một tenant chiếm khoảng 35% traffic.
- Booking trung bình 1 KB, có một số records lớn hàng chục KB.
- Customer có thể có từ 0 đến hàng triệu bookings.
- Booking có nhiều line items, phần lớn vài item.
- Property title, city, amenities được dùng trong màn hình tìm kiếm.
- Inventory slot không được double-book.
- Payment callback có thể đến trùng/lệch thứ tự.
- Search được phép trễ 5 giây.
- Dữ liệu cá nhân cần tenant isolation, retention và erasure.
- Java 21 services đang dùng relational DB cho giao dịch chính.

Đây là **giả định cho bài tập đánh giá**. Không suy ra kết quả lựa chọn nếu chưa đo tải/chi phí và xác minh hạn mức.

### 3.1. Các chức năng có yêu cầu không giống nhau

| Chức năng | Truy cập chính | Bất biến/độ mới |
| --- | --- | --- |
| Lấy booking by ID | Tenant + bookingId | Đúng scope; có thể cần read-your-writes |
| Danh sách booking | Tenant + customer + sort time | Pagination ổn định, freshness có bound |
| Tạo booking | Insert + reserve inventory | Không duplicate slot; durable commit |
| Xác nhận/cancel | Compare version, state transition | Không lost update |
| Payment callback | Lookup operationId + update | Idempotency, audit |
| Search property | Text + filters + ranking | Eventual freshness được chấp nhận |
| Recommendation | Traversal customer–tag–property | Bounded graph query; privacy |
| Financial report | Aggregate by date/tenant | Exactness/reconciliation |
| Privacy deletion | Remove/tombstone nhiều nguồn | Không hồi sinh PII |
| Restore | Snapshot/PITR + kiểm chứng | RPO/RTO đúng hợp đồng |

Đánh giá một “database chung” bằng điểm trung bình có thể che chức năng tạo booking quan trọng hơn recommendation.

## 4. Lập danh mục query trước khi thiết kế storage

Một query inventory đủ dùng không chỉ ghi tên endpoint. Nó ghi:
- ID thao tác.
- Source endpoint / caller.
- Lookup keys.
- Filters và toán tử.
- Sort và pagination.
- Số records/bytes đọc và trả.
- Read/write proportion.
- RPS giờ bình thường/đỉnh.
- Deadline và latency target.
- Consistency/freshness contract.
- Tenant/field authorization.
- Transaction/invariant nếu có.
- Query owner.

Ví dụ:

| ID | Thao tác | Khóa/điều kiện | Hình dạng | Tải minh họa |
| --- | --- | --- | --- | --- |
| Q1 | bookingById | tenantId + bookingId | Point read | 1.500 RPS |
| Q2 | bookingsByCustomer | tenantId + customerId; createdAt DESC | Ordered range, cursor | 600 RPS |
| Q3 | calendarByProperty | tenantId + propertyId + date range | Range | 400 RPS |
| Q4 | searchProperties | city + tags + text | Compound/filter/search | 250 RPS |
| Q5 | recommendProperties | Customer, tags, relation depth | Graph traversal | 50 RPS |
| W1 | createBooking | tenant, slot, operationId | Conditional multi-entity workflow | 200 RPS |
| W2 | changeStatus | bookingId + expectedVersion | Versioned update | 100 RPS |
| W3 | reconcilePayment | providerOperationId | Idempotent mutation | 50 RPS |
| E1 | publishEvent | sourceVersion/eventId | CDC/outbox | Theo writes |

### 4.1. Đừng quên query ẩn

Các operation thường bị bỏ quên:
- Admin export.
- Compliance erasure.
- Backfill và reindex.
- Repair/backups.
- List entities for background jobs.
- CDC snapshot.
- Analytics.
- Incident reconciliation.
- Cache warm-up.
- Periodic cleanup.

Một store phục vụ Q1/Q2 tốt nhưng không hỗ trợ recovery/backfill trong RTO có thể là quyết định sai.

## 5. Phân tích một query đủ sâu

Q2: lấy 30 booking mới nhất của C-9 trong tenant T-7.

~~~~yaml
queryId: Q2
name: listBookingsByCustomer
requiredKeys: [tenantId, customerId]
filters:
  status: optional
sort:
  - createdAt DESC
  - bookingId ASC
pageSize: 30
maxDateRangeDays: 365
consistency: eventual-with-session-fallback
target:
  p99Milliseconds: 120
  searchProjectionLagSeconds: 5
workload:
  peakRps: 600
  topTenantTrafficShare: 0.35
~~~~

Bảng cần ghi các câu hỏi:
- customer có bao nhiêu bookings ở p99?
- Queries thường trong 30 ngày hay 5 năm?
- Có filter status đáng kể?
- Cần trả propertyTitle hiện tại hay snapshot lúc booking?
- createdAt có các giá trị bằng nhau không?
- Khi insert giữa hai pages, API hứa snapshot hay live pagination?
- Có thể đọc từ replica/index trễ không?
- Có paging token gắn tenant/filter/version không?
- Index nào hoặc partition nào cung cấp thứ tự?

### 5.1. Query shape gợi ý mô hình nhưng không định sẵn sản phẩm

Q2 có thể:
- Được đáp ứng bởi SQL compound index.
- Được đáp ứng bởi document store compound index.
- Được đáp ứng bởi wide-column partition theo customer/time bucket.
- Được đáp ứng bởi KV + một ordered index có đồng bộ riêng.

Cần đo cả read path lẫn write/maintenance cost của mô hình được đề xuất.

## 6. Phân loại hình dạng truy vấn

| Hình dạng truy cập | Ví dụ | Hướng thường cân nhắc |
| --- | --- | --- |
| Point key | GET bookingId | KV, document key, row key, SQL PK |
| Ordered range trong partition | Timeline customer/day | Wide-column, compound index |
| Query nhiều thuộc tính | City + amenities + price | Document indexes, SQL, search |
| Full-text/ranking | Property description | Search index |
| Multi-hop relationship | Customer → tag → property | Graph hoặc precompute |
| Append/event history | Per-entity event stream | Wide-column/event store |
| Counter/conditional write | Inventory | DB hỗ trợ atomic/conditional semantics |
| Multi-record business transaction | Booking + reservation | SQL/transaction-capable NoSQL + protocol |
| Analytical aggregation | Finance/BI | Analytical store/warehouse |
| Cache/session | Key with TTL | KV/cache |

Bảng chỉ giúp tạo shortlist. Một tính năng được quảng cáo “có index” chưa chứng minh Query Q4 hiệu quả với tổ hợp filter thực tế.

## 7. Inventory dữ liệu: số lượng và phân phối

Một data profile nên ghi:

| Dimension | Câu hỏi | Tác động lựa chọn |
| --- | --- | --- |
| Total count | Current/future records? | Capacity/index/storage |
| Item size | p50/p99/max bytes? | Document/item limits, IO |
| Tenant count | Bao nhiêu tenants? | Partition/isolation |
| Skew | Top tenant % writes/reads? | Noisy neighbor |
| Cardinality | Unique customers/properties/tags? | Key/index selectivity |
| Relationship | One-to-many hay many-to-many? | Embed/reference/graph |
| Update frequency | Field nào thay đổi thường xuyên? | Denormalization fan-out |
| Retention | Năm, TTL, legal hold? | Storage/compaction/backup |
| Delete patterns | Soft/hard/erasure? | Tombstone/replay |
| Schema versions | Bao nhiêu versions cùng tồn tại? | Codec/migration |
| Geographic | Region/residency? | Multi-region topology |
| Sensitivity | PII/finance/audit? | Security compliance |

### 7.1. “Có 1 TB dữ liệu” là chưa đủ

Một TB chứa vài triệu documents rất lớn có hành vi khác một TB chứa hàng tỷ tiny events. Query performance/backup/index/compaction phụ thuộc shape và access pattern.

### 7.2. Đo phân phối, không dùng mỗi trung bình

Ghi p50/p95/p99/max của:
- Rows/customer.
- Items/booking.
- Writes/tenant.
- Document/row bytes.
- Update frequency.
- Query result cardinality.
- Partition size.

Một tenant chiếm 35% writes có thể khiến partition key chỉ tenantId thành điểm nóng dù có rất nhiều tenants khác.

### 7.3. Quan hệ và vòng đời quan trọng

Booking items thường được đọc và cập nhật cùng booking, có thể nhúng nếu bounded. Customer profile được dùng bởi nhiều bookings nên có thể nên tham chiếu thay vì lặp nguyên object. Property title có thể là historical snapshot hoặc current value; hai semantics khác nhau dẫn tới chiến lược đồng bộ khác.

## 8. Dữ liệu tăng trưởng và khả năng thay đổi mô hình

Không chỉ hỏi có scale lên 300 triệu bookings không, mà còn:
- Partition/shard key đã chọn có cần đổi không?
- Có hỗ trợ repartition/reshard online không?
- Tạm cần gấp đôi storage không?
- Thời gian copy/rebuild index?
- Khả năng rollback?
- Những clients route theo key cũ có còn hoạt động không?
- Một hot tenant lớn có tách riêng được không?
- Query cross-bucket sẽ fan-out như thế nào?

### 8.1. Cardinality cao vẫn có thể hotspot

Có 10.000 tenants nhưng một tenant chiếm phần lớn traffic. Partition theo tenantId có cardinality 10.000 nhưng skew rất cao.

### 8.2. Hash vs range

- Hash có thể phân phối keys tốt hơn nhưng range scans trở nên khó và nhiều fan-out.
- Range giúp locality nhưng writes theo khóa thời gian tăng dần có thể hot.
- Time bucket giảm wide partition nhưng tăng việc gộp nhiều partitions khi query lịch sử dài.

Chọn theo truy vấn, distribution và thí nghiệm chứ không theo nguyên tắc “hash luôn tốt”.

## 9. Chuyển yêu cầu thành SLI và SLO có thể đo

Một phát biểu “phải nhanh” thiếu nghĩa. Ví dụ tốt hơn:

- 99,9% GET booking hợp lệ phải hoàn thành đúng dữ liệu trong 120 ms theo end-to-end latency, cửa sổ 30 ngày.
- Timeline query Q2 p99 dưới 150 ms tại 600 requests/s, page size 30, skew đại diện.
- 99% booking changes nhìn thấy ở search trong 5 giây theo sourceVersion.
- Booking write không tạo duplicate logical operationId trong các tình huống retry/lost ACK.
- Availability mục tiêu được định nghĩa theo từng endpoint, tính cả timeout/correctness.
- Restore đạt RPO 5 phút và RTO 60 phút cho kịch bản được xác định.

Các số trên là **chỉ tiêu ví dụ**, không phải SLA của sản phẩm nào.

### 9.1. Latency phải có điểm bắt đầu và kết thúc

Đo:
- HTTP end-to-end hay driver-only?
- Có TLS/auth/serialization?
- Có queue/connection-pool wait?
- Có retries và timeouts?
- Mức tải nào?
- Tenant nào?
- Region nào?
- Read consistency nào?

Không so p99 driver-only của candidate A với p99 HTTP của B.

### 9.2. Availability cần kết quả đúng

Một HTTP 200 trả bản ghi tenant khác không thể được coi là request thành công. SLI cần đo **correct successful requests in deadline**, kèm error type.

### 9.3. Freshness khác response latency

Search trả sau 20 ms nhưng dữ liệu trễ 10 phút không đạt SLO freshness 5 giây. Tách:
- Query response latency.
- Source-to-projection lag.
- Read-your-writes behavior.
- Time to convergence after recovery.

### 9.4. RPO khác RTO

- RPO: mức dữ liệu tối đa có thể mất theo recovery point.
- RTO: thời gian để hệ trở lại mức phục vụ chấp nhận được.
- Replication/failover có thể cải thiện availability nhưng không thay backup chống logical deletion/corruption.
- Backup job SUCCESS chưa đủ: phải thử restore/decrypt/verify.

## 10. Bất biến nghiệp vụ là hard gates

Trước khi chấm điểm, viết rõ những điều **không được vi phạm**:

1. Không tạo hai booking CONFIRMED cho một slot chỉ được cấp một.
2. Không double-charge cho cùng payment operationId.
3. Conditional update với expectedVersion cũ không được overwrite version mới.
4. Tenant A không thể đọc/ghi tenant B.
5. Privacy deletion không bị stale backfill/CDC event hồi sinh.
6. Field nội bộ không bị xuất qua projection/sort/filter trái phép.
7. Một write đã ACK có durability theo hợp đồng cụ thể.
8. Có thể reconcile trường hợp client timeout nhưng server commit UNKNOWN.
9. RPO/RTO thực tế đạt mức đã phê duyệt hoặc có ngoại lệ được chấp thuận.
10. Data residency/encryption/retention đạt chính sách.

### 10.1. Hard gates không thể được bù bằng tốc độ

Một engine có p99 5 ms nhưng workflow tạo booking có thể double-book dưới network partition phải **FAIL** cho vai trò booking source, dù tổng điểm về performance/cost cao.

### 10.2. “Có transaction” chưa chứng minh invariant

Phải hỏi:
- Atomicity ở một key/document/partition hay nhiều records?
- Isolation level?
- Conditional conflict?
- Retry after timeout?
- Transactions xuyên shards/regions?
- Hành động ở payment provider nằm ngoài database transaction ra sao?

### 10.3. Mọi read không nhất thiết linearizable

Search/recommendation có thể eventual, nhưng booking detail ngay sau confirm có thể cần read-your-writes. Bảng tiêu chí cần phân biệt theo operation, không gắn một nhãn consistency chung cho cả hệ.

## 11. Điều kiện bắt buộc so với tiêu chí đánh đổi

Phân thành ba nhóm:

**A. Hard gates:** Nếu không đạt, loại hoặc yêu cầu redesign. Ví dụ tenant isolation, inventory invariant, legal residency, restore ability.

**B. Scored preferences:** Có thể đánh đổi sau khi qua gates. Ví dụ chi phí, latency headroom, simplicity, developer productivity.

**C. Unknowns/assumptions:** Chưa có bằng chứng, cần PoC hoặc sensitivity test. Ví dụ hot tenant growth, vendor regional quotas, rebuild speed ở 300M records.

Đừng biến **UNKNOWN** thành điểm 3/5 để lấp ô trống; đó là một cách che rủi ro bằng sự chính xác giả.

### 11.1. Bảng hard gate minh họa

| ID | Gate | Phép kiểm chứng | Trạng thái trước PoC |
| --- | --- | --- | --- |
| G-01 | Cross-tenant isolation | Auth read/write/export tests | UNKNOWN |
| G-02 | No double-book | Two-writer, retry/lost ACK | UNKNOWN |
| G-03 | Payment idempotency | Duplicate callback + ledger | UNKNOWN |
| G-04 | Stable pagination | Same-time keys, cursor test | UNKNOWN |
| G-05 | Durability semantics | Failover after ACK | UNKNOWN |
| G-06 | Restore RPO/RTO | Full restore drill | UNKNOWN |
| G-07 | Residency/encryption | Security review | UNKNOWN |
| G-08 | Data erasure | Tombstone + rebuild test | UNKNOWN |
| G-09 | Critical query capacity | Peak/skew benchmark | UNKNOWN |

Có thể ghi PASS, FAIL, UNKNOWN hoặc CONDITIONAL, nhưng CONDITIONAL phải có thiết kế giảm thiểu rủi ro, người chịu trách nhiệm và thí nghiệm còn thiếu.

### 11.2. Gate áp cho đúng vai trò

Một recommendation graph projection không cần trực tiếp xử lý payment idempotency nếu payment authority nằm ở nơi khác. Nhưng **toàn kiến trúc** vẫn phải qua gate đó. Không chấm công nghệ ngoài phạm vi rồi dùng điểm chung để kết luận sai.

## 12. Mẫu bảng tiêu chí đo lường

| ID | Nhóm | Nội dung đo | Đơn vị / oracle | Minh chứng |
| --- | --- | --- | --- | --- |
| Q-1 | Query | Lookup tenant+bookingId | p99, exact ID, RPS | Benchmark + integration |
| Q-2 | Query | Customer timeline | Ordered IDs/cursor, p99 | Query test |
| Q-3 | Query | Compound filters/search | Selectivity, latency, relevance | Search PoC |
| D-1 | Data | Hot partition | Max saturation/latency | Skew test |
| D-2 | Data | Large items/partitions | Max bytes, read amp | Size tests |
| W-1 | Writes | Conditional booking | Duplicate violations | Concurrency fault |
| W-2 | Writes | Idempotent retries | Effects per operationId | Lost ACK test |
| C-1 | Consistency | Session read | Min version seen | RYW test |
| C-2 | Consistency | Derived freshness | Source-to-index lag | CDC measurement |
| R-1 | Reliability | Failover correctness | Recovery time + data | Chaos test |
| R-2 | Reliability | Backup/restore | Actual RPO/RTO | DR drill |
| S-1 | Security | Authorization | Violations | Security integration |
| O-1 | Operations | Monitoring/repair readiness | Rehearsed runbook | Ops drill |
| T-1 | Cost | Three-year TCO | Currency/time | Cost scenarios |
| M-1 | Migration | Reversible cutover | Time/data drift | Pilot |

Đây là điểm biến ý kiến thành **câu hỏi có phép thử**.

## 13. Thiết kế shortlist candidate architectures

Tránh đặt Redis, MongoDB, Cassandra và SQL vào một bảng rồi hỏi “ai thắng tất cả”. Thay vào đó chọn phương án kiến trúc:

- A. SQL hiện tại với indexing/partitioning.
- B. SQL source + Redis cache Q1.
- C. SQL source + document booking summary Q1/Q2.
- D. SQL source + wide-column timeline Q2/Q3.
- E. SQL source + search index Q4.
- F. SQL source + graph projection Q5.
- G. Di chuyển source writes sang NoSQL transaction-capable candidate, kèm workflow idempotency/conditional invariants đã thiết kế.

### 13.1. Mỗi candidate phải có boundary rõ

Ghi:
- Chức năng nào chuyển?
- Source of truth ở đâu?
- Ở đâu duplicate dữ liệu?
- Cập nhật qua CDC/outbox hay synchronous writes?
- Staleness được phép?
- Query API nào gọi vào store?
- Backup/rebuild/DR ai sở hữu?

### 13.2. Mô hình đa store cũng phải tính chi phí

Một phương án có 5 services/DBs phải tính cả:
- Broker/CDC.
- Auth/IAM.
- Backfill và replay.
- Monitoring.
- Operational complexity.
- Schema compatibility.
- Incident response.
- Cross-store consistency.

Không tối ưu cục bộ một GET rồi bỏ qua tác động toàn hệ.

## 14. Bảng định tính cho các họ mô hình

| Họ lưu trữ | Access pattern khởi đầu | Vấn đề bắt buộc kiểm tra |
| --- | --- | --- |
| SQL/relational | Transactions, flexible JOINs, indexes | Scaling, cost, connection limits |
| KV/cache | Point key, TTL, session, simple counters | Multi-key consistency, hot key, index maintenance |
| Document | Aggregates, nested fields, compound indexes | Document size, embedding, shard/index costs |
| Wide-column | Partition-local ranges, ordered timeline | Hot/wide partitions, bucketing, tombstones |
| Graph | Multi-hop traversal, relationships | Supernodes, depth/fan-out, auth per edge |
| Search | Text/ranking/compound discovery | Index freshness, rebuild, query cost |
| Analytical | Cross-domain reports, columnar scans | ETL freshness, not write authority |

Đây là **bản đồ giả thuyết**, không phải bảng điểm 1–5. Những engine cùng họ cũng khác nhau ở transaction, consistency, index, regional replication và pricing.

## 15. So khả năng phục vụ truy vấn bằng đường truy cập vật lý

Đối với mỗi Q, yêu cầu nhóm trả lời:

1. Input keys và schema type?
2. Partition/shard/row/document khởi đầu?
3. Index nào được dùng?
4. Bao nhiêu partitions bị truy cập?
5. Có scan trước filter không?
6. Sort ở index hay trong bộ nhớ?
7. Keyset cursor dùng những fields nào?
8. Query có thể chạm hot tenant/partition không?
9. Read từ primary/follower/index nào và consistency gì?
10. Nếu data 10×, cost tăng ra sao?

### 15.1. Q1 point lookup

Key tenantId+bookingId giúp định tuyến trực tiếp trong nhiều mô hình. Nếu chỉ index by customerId+date, lookup by bookingId có thể phải thêm index hoặc scan. Bảng score cần phản ánh đường thực, không chỉ tên database.

### 15.2. Q2 timeline

Partition theo tenant/customer/day làm query từng ngày dễ, nhưng 5 năm lịch sử phải hợp nhất nhiều buckets. Compound index trên tenant/customer/createdAt có tính chất khác. Cần đo sorting, pagination, fan-out, hotspot và cost.

### 15.3. Q4 search

Query city+amenities+keyword có thể cần inverted index/ranking, không đơn giản là GET theo key. Một database có secondary indexes không bảo đảm mọi tổ hợp filter đều hiệu quả.

### 15.4. Q5 graph

Nếu recommendation chỉ dựa trên 5 tags cố định, một precomputed KV list có thể đủ. Nếu truy vấn nhiều hop và đổi đường traversal linh hoạt, graph đáng thử. Đo thực tế degree distribution và supernodes.

## 16. Phân quyền và dữ liệu nhạy cảm

Bảng tiêu chí phải bao gồm:
- IAM, authn/authz.
- Multi-tenant isolation.
- Field-level visibility.
- Encryption in transit/at rest.
- KMS/key recovery.
- Audit logs.
- Private networking.
- Data residency.
- Backup access.
- Retention/erasure.
- Query DSL/operator allowlist.
- Resource quotas chống abusive queries.

### 16.1. Auth không được bỏ ra khỏi benchmark khi đo end-to-end

Một PoC không TLS/auth/tenant checks có thể nhanh hơn production. Nếu chọn dựa trên trải nghiệm người dùng, test tương đương đường đi production.

### 16.2. Một field không hiển thị vẫn có thể bị lộ

Sort/filter/aggregation trên internalScore có thể rò thông tin qua thứ tự/count. Đánh giá response projection và quyền truy vấn, không chỉ output JSON.

### 16.3. Privacy deletion là một test kiến trúc

Nếu xóa customer ở source, các copies:
- Document projection.
- KV cache.
- Wide-column read table.
- Search index.
- Graph edges.
- Backup/staging theo policy.

phải được xử lý. Tombstone/version-aware apply ngăn stale event hoặc backfill hồi sinh dữ liệu đã xóa.

## 17. Chọn tiêu chí hiệu năng và tính đúng riêng

Ví dụ:

| Tiêu chí | Cách đo | Có là gate? |
| --- | --- | --- |
| Booking unique | Double booking violations | Có |
| Tenant isolation | Cross-tenant accesses | Có |
| Q1 p99 ≤ 120 ms ở peak | Latency distribution + timeout | Có hoặc threshold |
| Q2 p99 càng thấp càng tốt | Headroom so target | Scored nếu đã đạt gate |
| Search freshness ≤ 5 s | SourceVersion age lag | Có nếu contract bắt buộc |
| Compression ratio | Storage saved | Scored |
| Cost per 1M operations | Billing estimate/test | Scored |
| Deployment simplicity | Rehearsed time/runbook | Scored |
| RPO/RTO | Actual restore drill | Có |

Một mục tiêu có thể có cả **ngưỡng gate** và **điểm headroom** sau gate. Không cho 5/5 về p99 để bù cho việc 10% requests timeout.

## 18. Weighted matrix sau hard gates

Một bộ trọng số cho read projection:

| Nhóm | Trọng số |
| --- | ---: |
| Query fit + p99 | 25 |
| Growth/skew scalability | 20 |
| Freshness/consistency | 15 |
| Recovery/reliability | 15 |
| Security/governance | 10 |
| Three-year TCO | 10 |
| Team/operational fit | 5 |
| **Tổng** | **100** |

Đây là **ví dụ cho read projection**, không áp nguyên cho payment source. Với payment, tính đúng/durability thường là hard gates và ưu tiên rủi ro có thể khác.

### 18.1. Chốt trọng số trước khi xem score

Nếu chỉnh trọng số sau khi biết candidate yêu thích thắng/thua, bảng dễ trở thành công cụ hợp thức hóa quyết định có sẵn.

### 18.2. Có sự tham gia của stakeholders

Nên có product, engineering, SRE, security, finance và data team. Số 25 cho query là một **ưu tiên chính sách**, không phải thông số kỹ thuật được đo.

### 18.3. Tránh double-counting

Latency, throughput và scalability liên quan nhau. Nếu đặt ba mục độc lập, cần định nghĩa rõ:
- Latency tại tải mục tiêu.
- Max sustainable throughput.
- Khả năng tăng scale và skew tolerance.

## 19. Thang điểm có neo thay vì cảm tính

Một rubric 1–5:

| Điểm | Ý nghĩa minh họa |
| --- | --- |
| 1 | Không đạt, chênh xa mục tiêu |
| 2 | Đạt một phần với workaround/rủi ro lớn |
| 3 | Đạt ngưỡng tối thiểu, headroom thấp |
| 4 | Đạt có headroom rõ và bằng chứng phù hợp |
| 5 | Đạt tốt với headroom, recoverability và vận hành đã chứng minh |

Một điểm cần có evidence, workload, config và owner, ví dụ:

> Q2: 600 req/s, top tenant 35%, pageSize=30, compound index đã dựng; p99=95 ms, timeout=0,02%, exact sorted IDs; RUN-Q2-007. Điểm 4/5 theo rubric.

Đây là một **mẫu số liệu giả định**, không phải test vừa chạy.

### 19.1. UNKNOWN không được cho trung bình 3

Thiếu thí nghiệm về hot partition? Ghi UNKNOWN, confidence LOW và action item. Điền 3 làm thiếu bằng chứng trở thành một điểm trung bình giả.

### 19.2. N/A khác UNKNOWN

Graph projection không thực hiện payment write theo scope thì tiêu chí payment source có thể N/A cho component đó, nhưng hard gate của **kiến trúc tổng** vẫn cần nguồn payment đáp ứng.

### 19.3. Điểm có thời hạn

PoC từ schema/driver phiên bản cũ hoặc traffic distribution trước khi một tenant tăng trưởng mạnh có thể không còn đại diện. Cần evidence date và revisit trigger.

## 20. Công thức tính điểm

Với các criteria có trọng số \(w_i\), điểm \(s_i\) trên 1–5 và tổng trọng số 100:

\[
S = \sum_{i=1}^{n} w_i \frac{s_i}{5}
\]

Ví dụ một tiêu chí Q-fit có trọng số 25, điểm 4, đóng góp \(25\times4/5=20\) trên thang 100.

**Chỉ so điểm tổng giữa các ứng viên đã đạt hard gates và có dữ liệu đầy đủ trên cùng phạm vi.** S=84 không phải “84% xác suất thành công” và không thay thế quyền phê duyệt.

### 20.1. Chấm điểm theo kiến trúc, không một DB cô lập

Nếu candidate là SQL+Redis:
- Q1 cache hit path phải tính cả hit rate và miss fallback.
- TCO phải gồm SQL, Redis và invalidation.
- Recovery phải gồm cold-cache behavior.
- Correctness phải kiểm tra stale fill/tenant namespace.

### 20.2. Chênh điểm nhỏ có thể không đáng kể

A=82 và B=80 có thể đảo khi cost model hoặc skew thay đổi. Không suy chiến thắng chắc chắn nếu các thí nghiệm có uncertainty lớn.

## 21. Bảng chấm điểm minh họa với evidence status

Phạm vi: **customer timeline read projection**. SQL vẫn là write authority.

| Tiêu chí | Trọng số | SQL indexed | Document projection | Wide-column timeline | KV ordered index |
| --- | ---: | --- | --- | --- | --- |
| Q2 sort/cursor | 25 | PoC cần đo | PoC cần đo | PoC cần đo | PoC cần đo |
| Hot tenant scaling | 20 | Cần skew test | Cần shard test | Cần partition test | Cần hot-index test |
| Freshness | 15 | Source read tùy contract | CDC lag cần đo | CDC lag cần đo | Multi-key view lag |
| Recovery | 15 | Restore drill | Rebuild/restore | Rebuild/repair | Cache/index rebuild |
| Security | 10 | Authz tests | Authz tests | Authz tests | Key namespace tests |
| Cost | 10 | Index/query cost | Cluster+CDC+indexes | Partitions+repair | Source+ordered index |
| Operations | 5 | Team readiness | Team readiness | Team readiness | Team readiness |
| **Decision** | **100** | **UNKNOWN** | **UNKNOWN** | **UNKNOWN** | **UNKNOWN** |

Bảng này cố ý **không điền điểm chưa đo**. Để chọn, phải chạy PoC theo cùng contract.

### 21.1. Có thể không cần NoSQL

Nếu SQL query Q2 đã đạt p99, mở rộng theo mục tiêu, có backup/DR và chi phí hợp lý, thêm một NoSQL store chỉ để đổi công nghệ có thể không đáng. “Giữ SQL” là một candidate hợp lệ.

## 22. PoC phải bắt đầu bằng giả thuyết bác bỏ được

Ví dụ:

> Với dữ liệu 100 triệu bookings, top tenant 35% traffic, pageSize 30 và 600 Q2 req/s, kiến trúc X có p99 ≤120 ms, timeout rate trong error budget, exact tenant/order và không vượt quota ở hot partition.

Một PoC khác:

> Khi hai booking requests tranh cùng slot, có lỗi lost ACK sau commit và client retry cùng operationId, một source-write workflow vẫn chỉ tạo một logical booking, inventory không âm và payment không double-charge.

### 22.1. Mẫu PoC plan

- Hypothesis ID.
- Candidate data model.
- Query/command contract.
- Synthetic data generator và seed.
- Data size/shape/skew.
- Driver/engine version.
- Index/partition definition.
- Workload arrival rate.
- Timeout/retry/consistency settings.
- Correctness oracle.
- Metric collection.
- Pass/fail threshold.
- Fault cases.
- Cleanup/repro instructions.

### 22.2. Ưu tiên hard-gate experiments sớm

Nếu architecture có khả năng vi phạm uniqueness hoặc residency, hãy kiểm tra trước khi tối ưu p99. Một thí nghiệm phát hiện bất khả thi sớm tiết kiệm nhiều công.

### 22.3. Không giả định PoC đơn giản hóa vẫn công bằng

Bỏ auth, encryption, replication hoặc business payload để benchmark cho một candidate sẽ khiến so sánh sai. Phải ghi các khác biệt và đo lại end-to-end khi quyết định.

## 23. Synthetic dataset đại diện cho distribution

Một cấu hình minh họa:

~~~~yaml
dataset: booking-evaluation
generatorVersion: 1
seed: 565001
recordCount: 10000000
bookingBytes:
  p50: 1200
  p99: 8000
tenantDistribution:
  tenantCount: 2000
  largestTenantRequestShare: 0.35
queryMix:
  bookingPointRead: 0.50
  timelineRead: 0.20
  propertyCalendar: 0.10
  conditionalWrite: 0.10
  search: 0.10
specialCases:
  - sameBookingIdAcrossTenants
  - sameCreatedAtSortTie
  - tombstoneAfterUpsert
  - legacySchema
  - hotCustomer
  - largeDocument
~~~~

Đây là mẫu dữ liệu, không phải chuẩn yêu cầu. Nên tạo **data synthetic** để tránh đưa PII thật vào PoC.

### 23.1. Dữ liệu lớn chưa đủ nếu thiếu skew

Một generator random uniform cho mỗi tenant số writes gần như bằng nhau sẽ không tái tạo hot tenant có 35% traffic.

### 23.2. Hai mức fixture

- **Logic fixture nhỏ:** kiểm tra đúng key/tenant/sort/versions/deletes.
- **Scale fixture lớn:** kiểm tra index/partition/compaction/hotspot/throughput.

Không dùng 10 triệu records để thay test 3 records có tie-breaker rõ; cũng không dùng 3 records để kết luận về scale.

### 23.3. Có thể kiểm tra mức giới hạn

Thêm:
- Max document/item size theo policy.
- Long/numeric overflow.
- Null/missing.
- TTL expiry.
- Large IN/filter.
- Deep pagination.
- High-degree graph node.
- Very wide partition.

## 24. Benchmark công bằng giữa các mô hình

Điều kiện chung cần giữ:
- Cùng business query semantics.
- Cùng dữ liệu logical và skew.
- Cùng offered load.
- Cùng payload response.
- Cùng availability/consistency contract nếu có thể.
- Cùng scope TLS/auth.
- Cùng test window và success definitions.
- Cùng fault cases.
- Có index/schema readiness.
- Warm-up và compaction/GC được quan sát.

### 24.1. Không bắt ép physical schema giống nhau

Một SQL compound index, document compound index và Cassandra table theo query có cấu trúc khác nhau. So sánh công bằng là **cùng chức năng end-to-end**, cho mỗi store thiết kế đường truy cập phù hợp.

### 24.2. Tính mọi extra components

Nếu Cassandra cần ba materialized tables và CDC, tính storage, writes, lag, repair/rebuild của cả ba. Nếu Redis dựa vào SQL fallback, tính source QPS trong cache misses và network outage.

### 24.3. Kết quả đúng quan trọng như latency

Báo:
- Exact IDs/order.
- Tenant scope.
- Stale/duplicate/missing.
- Write invariants.
- Error/timeout fraction.
- p50/p95/p99.
- Achieved throughput.
- CPU/IO/memory.
- Retry amplification.

## 25. Đừng mắc lỗi coordinated omission

Trong load generator closed-loop, request sau chỉ phát khi request trước hoàn thành. Khi database chậm, arrival rate giảm tự động; completed requests có thể có p99 “đẹp” vì phần tải lẽ ra tới đã không được phát.

Để kiểm tra fixed arrival workload:
- Planned arrivals.
- Actual sent.
- Completed.
- Dropped/queued.
- Timeout.
- Scheduler lag.
- End-to-end latency kể cả queue theo contract.

### 25.1. Không ghi “đạt 2.000 RPS” khi chỉ thực hiện 1.000

Cần chứng minh generator đã phát đủ và database hoàn thành đúng số thao tác trong deadline. Nếu chậm, đánh giá cả overload behavior.

### 25.2. Phải báo timeouts bên cạnh p99

Nếu 10% requests timeout và chỉ tính p99 của 90% successes, số đo che vấn đề. Đặt timeout budget và đo tất cả outcomes.

### 25.3. Thử burst và skew

Average RPS ổn không có nghĩa chịu được:
- Tenant burst.
- Cache stampede.
- Reindex/catch-up.
- Compaction spike.
- Node failover.
- Cross-region reconnect.

## 26. Benchmark theo chi phí truy vấn và storage

Một access pattern có thể trả kết quả đúng nhưng đọc quá nhiều:
- Full scan rồi filter.
- Scatter-gather qua nhiều shards.
- Secondary index với selectivity thấp.
- Graph traversal qua supernode.
- KV phải fetch N+1.
- Wide-column query quá nhiều buckets.
- Aggregation phức tạp.

Đo:
- Database items/bytes scanned.
- Items returned.
- Network round trips.
- Index read cost.
- CPU per query.
- Hot partition utilization.
- Number of fan-out branches.
- Compaction/write amplification.
- Memory allocations.

### 26.1. Read amplification

Nếu trả 30 records nhưng quét hàng trăm nghìn records, đây là tín hiệu query model có vấn đề, dù một lần thử trên dataset nhỏ chưa thấy chậm.

### 26.2. Write amplification

Nếu một booking xuất hiện trong source + customer timeline + property calendar + search + cache, một write có thể phát nhiều updates và retry. Phải tính chi phí maintain các copies.

### 26.3. Query plan có thể đổi khi data tăng

Một index tối ưu ở 100.000 records có thể khác với 300 triệu records. Cần thử mức tăng trưởng và xem explain plan/metrics theo engine.

## 27. Kiểm thử consistency, failover và network faults

Một candidate đạt performance ở network bình thường chưa chứng minh:
- Lost ACK sau commit không tạo duplicate.
- Leader failover không mất writes vượt durability contract.
- Old leader bị fenced.
- Reads qua replica/index không vi phạm freshness requirement.
- Stale CDC events không ghi đè sourceVersion mới.
- Delete tombstone không bị hồi sinh.
- Partition không tạo double-book.
- Recovery lag không kéo dài quá mục tiêu.

### 27.1. Quorum theo operation

Đánh giá consistency level, read/write concern và quorum theo topology thực. Không gọi một database “CP” hoặc “AP” rồi tự suy mọi reads/writes có cùng behavior.

### 27.2. UNKNOWN commit

Client timeout có thể xảy ra sau server commit. Phải có logical operationId và reconciliation, không retry tạo ID mới rồi cho rằng write cũ rollback.

### 27.3. CDC/index recovery

Nếu source write thành công nhưng search không cập nhật vì network partition:
- Source vẫn authoritative.
- Search freshness có thể vi phạm.
- Consumer cần replay idempotently.
- Backfill cũ không được ghi đè version mới.
- Cần đo catch-up time và cost.

## 28. RPO/RTO và backup phục hồi là một tiêu chí đo được

Một DR drill gồm:
1. Xác định incident và recovery boundary.
2. Chọn snapshot/PITR/log chain.
3. Dựng môi trường nhận cách ly.
4. Restore và replay theo supported procedure.
5. Verify schema/index/ACL.
6. So key membership/version/canonical digest.
7. Kiểm tra business invariants.
8. Cutover/routing/fencing.
9. Đo actual RPO/RTO.
10. Post-recovery cleanup và evidence.

### 28.1. Replication không phải backup

Một lệnh DELETE sai có thể replicate tới mọi replicas. Sao lưu phải có retention/restore độc lập theo threat model và được kiểm chứng.

### 28.2. RTO gồm nhiều phase

\[
RTO_{\mathrm{actual}}=
T_{\mathrm{detect}}+T_{\mathrm{decide}}+
T_{\mathrm{provision}}+T_{\mathrm{restore}}+
T_{\mathrm{verify}}+T_{\mathrm{cutover}}
\]

Chỉ đo thời gian chạy restore command là thiếu.

### 28.3. Chọn lọc restore

Nếu chỉ một collection hoặc 100 records bị hỏng, khả năng staging restore, selective export và conditional patch có thể giúp tránh roll back toàn cụm về snapshot cũ.

## 29. Team/operational readiness

Bảng cần có:
- Monitoring cho p99, hot partitions và replication lag.
- Alerts và per-tenant diagnostics.
- Backup age và last verified restore.
- Runbooks failover/repair/reindex.
- Trách nhiệm on-call.
- Thời gian đào tạo.
- Kỹ năng schema/partition tuning.
- Chi phí incident response.
- Vendor support/escalation.
- Khả năng tự động hóa upgrade/migration.

### 29.1. Managed service vẫn cần vận hành

Nhà cung cấp có thể quản lý nodes nhưng ứng dụng vẫn phải quản lý:
- Data model.
- Queries/indexes.
- IAM.
- Retry/idempotency.
- Quotas/cost.
- CDC.
- Security.
- Backups/restore policy.
- Business reconciliation.

### 29.2. Chấm “team fit” bằng bằng chứng

Ví dụ có runbook đã diễn tập, dashboard hữu ích và incident drill thành công là bằng chứng tốt hơn nhận xét “team thích công nghệ này”.

## 30. Three-year TCO

Một mô hình:

\[
TCO =
C_{\mathrm{compute}} + C_{\mathrm{storage}} +
C_{\mathrm{read/write}} + C_{\mathrm{network}} +
C_{\mathrm{replication}} + C_{\mathrm{backup}} +
C_{\mathrm{observability}} + C_{\mathrm{people}} +
C_{\mathrm{migration}} + C_{\mathrm{risk}}
\]

Các thành phần có đơn vị và uncertainty khác nhau; không tự cộng “risk points” thành tiền nếu không có giả định và phương pháp rõ.

### 30.1. Đừng chỉ nhìn giá instance

Tính:
- Index storage.
- Replication copies.
- CDC broker throughput.
- Cross-zone/region egress.
- PITR/backup.
- Restore drill/rebuild.
- Request charges.
- Headroom cho peak/failover.
- Operations/staff.
- Observability/log retention.
- Migration and decommissioning.
- Vendor exit cost.

### 30.2. Mô hình nhiều kịch bản

Ít nhất:
- Current baseline.
- Traffic 3×, data 3×.
- Data 10×, traffic 5×.
- Top tenant 70% writes.
- Region loss/rebuild.
- Compliance retention tăng.

Một lựa chọn rẻ ở steady state nhưng không đủ capacity để reindex/restore trong RTO có rủi ro vận hành cao.

### 30.3. Cần ghi giá theo region/tier hiện tại

Không sử dụng bảng giá cũ hoặc giá quảng cáo như cost đã xác nhận; ghi ngày lấy báo giá, region, tier và quota.

## 31. Sensitivity analysis trước khi chốt

Thử thay các giả định:

| Thay đổi | Thử lại điều gì? |
| --- | --- |
| Top tenant 35% → 70% | Hot partition, fairness, throttling |
| Q2 p99 target 120 → 60 ms | Latency headroom |
| Search freshness 5 → 1 s | CDC/index throughput |
| Data 30M → 300M | Index, backup, partition, cost |
| RTO 60 → 10 phút | Restore capacity/quorum strategy |
| More dynamic filters | Index flexibility vs query cost |
| Region outage | Failover, conflict, RPO |
| Security retention chặt hơn | Erasure/backup lifecycle |
| Team size giảm một nửa | Operational burden |

### 31.1. Chênh score 2 điểm không đủ nếu uncertainty lớn

Candidate A=82 và B=80 có thể đảo khi growth hoặc cost assumption thay đổi. Ghi kết quả phân tích theo scenarios, không biến 82 thành “82% cơ hội thành công”.

### 31.2. UNKNOWN quan trọng thành action item

Nếu chưa biết rebalancing time ở 300M records:
- Ghi UNKNOWN.
- Chọn experiment.
- Owner.
- Deadline.
- Gate dependency.
- Không kết luận chắc chắn trước khi có evidence.

## 32. Java 21: cấu trúc biểu diễn scorecard

Một tập record typed tránh nhầm lẫn giữa metric, điểm và evidence:

~~~~java
import java.util.List;
import java.util.Map;

public record Criterion(
        String id,
        String description,
        int weight,
        boolean mandatory
) {
    public Criterion {
        if (id == null || id.isBlank()
                || description == null || description.isBlank()
                || weight < 0 || weight > 100) {
            throw new IllegalArgumentException("invalid criterion");
        }
    }
}

public record Assessment(
        int score,
        boolean demonstrated,
        String evidenceId,
        String explanation
) {
    public Assessment {
        if (score < 1 || score > 5) {
            throw new IllegalArgumentException("score");
        }
        if (evidenceId == null) {
            evidenceId = "";
        }
    }
}

public record Candidate(
        String name,
        Map<String, Assessment> assessments
) {
    public Candidate {
        if (name == null || name.isBlank()
                || assessments == null) {
            throw new IllegalArgumentException("candidate");
        }
        assessments = Map.copyOf(assessments);
    }
}

public record Evaluation(
        String candidateName,
        boolean eligible,
        double weightedScore,
        List<String> blockers
) {}
~~~~

### 32.1. Một evaluator chỉ để minh họa

~~~~java
import java.util.ArrayList;
import java.util.List;

public final class MatrixEvaluator {
    private MatrixEvaluator() {}

    public static Evaluation evaluate(
            List<Criterion> criteria,
            Candidate candidate
    ) {
        int totalWeight = criteria.stream()
                .mapToInt(Criterion::weight)
                .sum();

        if (totalWeight != 100) {
            throw new IllegalArgumentException(
                    "weights must sum to 100"
            );
        }

        double points = 0.0;
        List<String> blockers = new ArrayList<>();

        for (Criterion criterion : criteria) {
            Assessment a = candidate.assessments()
                    .get(criterion.id());

            if (a == null || !a.demonstrated()
                    || a.evidenceId().isBlank()) {
                blockers.add(
                        criterion.id() + ": missing evidence"
                );
                continue;
            }

            if (criterion.mandatory() && a.score() < 4) {
                blockers.add(
                        criterion.id() + ": hard gate not met"
                );
            }

            points += criterion.weight() *
                    (a.score() / 5.0);
        }

        return new Evaluation(
                candidate.name(),
                blockers.isEmpty(),
                points,
                List.copyOf(blockers)
        );
    }
}
~~~~

**Giới hạn quan trọng:** Đây là một thang chấm ví dụ; dùng điểm 4 làm gate chỉ là policy minh họa. Trong hệ thực, một hard gate nên có **assertion pass/fail độc lập**, không được chỉ dựa vào subjective score. Nếu một criterion thiếu evidence, weightedScore chỉ là partial và không dùng xếp hạng.

### 32.2. Điểm là metadata của bằng chứng, không tự sinh bằng chứng

Có thể thêm:
- Measurement run ID.
- Engine/driver/config version.
- Dataset seed.
- Test date.
- Reviewer.
- Confidence.
- Pass/fail.
- Link artifact.
- Known limitations.

Code scorecard không chạy benchmark; nó chỉ quản lý quyết định dựa trên kết quả đã thu.

## 33. Java 21: ví dụ tạo candidate

~~~~java
import java.util.List;
import java.util.Map;

public final class ExampleScorecard {
    public static void main(String[] args) {
        List<Criterion> criteria = List.of(
                new Criterion("QUERY", "Query fit", 25, true),
                new Criterion("SCALE", "Skew scaling", 20, false),
                new Criterion("FRESH", "Freshness", 15, true),
                new Criterion("RECOVER", "Recovery", 15, true),
                new Criterion("SEC", "Security", 10, true),
                new Criterion("COST", "TCO", 10, false),
                new Criterion("OPS", "Operations", 5, false)
        );

        Candidate option = new Candidate(
                "Document-timeline-projection",
                Map.of(
                        "QUERY", new Assessment(
                                4, true, "RUN-Q2-007", "Measured p99"),
                        "SCALE", new Assessment(
                                3, true, "RUN-SKEW-011", "Moderate headroom"),
                        "FRESH", new Assessment(
                                4, true, "RUN-CDC-004", "Bounded lag"),
                        "RECOVER", new Assessment(
                                4, true, "RUN-DR-002", "Rebuild drill"),
                        "SEC", new Assessment(
                                5, true, "RUN-AUTH-006", "Tenant checks"),
                        "COST", new Assessment(
                                3, true, "COST-003", "Forecast scenario"),
                        "OPS", new Assessment(
                                4, true, "OPS-005", "Runbook practiced")
                )
        );

        Evaluation result =
                MatrixEvaluator.evaluate(criteria, option);

        System.out.println(result);
    }
}
~~~~

**RUN-Q2-007** và các evidence IDs ở đây hoàn toàn **giả định**; không được tuyên bố phương án đã PASS khi chưa có thí nghiệm. Một đánh giá thật cần lưu artifacts, log phiên bản và review độc lập.

## 34. Từ scorecard tới Architecture Decision Record

Một ADR nên có:

1. **Bối cảnh:** chức năng, workload, dữ liệu và giới hạn.
2. **Phạm vi:** source, projection, cache hay search.
3. **Các điều kiện bắt buộc:** business/security/recovery.
4. **Các phương án:** cả giữ SQL và các candidate architectures.
5. **Thiết kế mỗi phương án:** key/index/partition, consistency.
6. **Bằng chứng:** PoC run IDs, pass/fail, dataset/config.
7. **Ma trận điểm:** trọng số và rubric chốt trước.
8. **Độ bất định:** UNKNOWN và rủi ro còn lại.
9. **Đánh đổi/chi phí:** scale, TCO, team.
10. **Quyết định:** lựa chọn, phạm vi, tại sao.
11. **Migration:** backfill/CDC/shadow/canary.
12. **Rollback/failback:** khi nào có thể, khi nào không.
13. **Theo dõi:** SLO, drift, backup, cost.
14. **Revisit triggers:** load, data, compliance, tech change.

### 34.1. Ví dụ quyết định có điều kiện

> Giữ relational DB làm source cho booking/payment vì hiện đáp ứng inventory/uniqueness và có runbook đã thử. Đánh giá một read projection theo customer/time bucket cho Q2. Chỉ chuyển traffic đọc khi tenant isolation, exact pagination, p99, freshness, rebuild và hot-tenant tests đạt. Search tiếp tục là derived index. Không tự chuyển payment authority trong cùng đợt.

Đây là **ví dụ trình bày lập luận**, không phải lựa chọn bắt buộc cho mọi hệ.

### 34.2. Quyết định tốt ghi cả lý do không chọn

Nếu KV projection cần một ordered index phức tạp hơn document projection, ghi lý do cost/maintenance. Nếu wide-column chưa đạt hot tenant latency, ghi test và điều kiện cải thiện. Đừng xóa dữ liệu về các phương án thua khỏi ADR.

## 35. Migration/rollback là một tiêu chí riêng

### 35.1. Read projection

Một lộ trình:
1. SQL source còn authoritative.
2. Capture snapshot H.
3. Backfill projection.
4. CDC/outbox events có sourceVersion/eventId.
5. Version-aware apply; tombstones.
6. Shadow reads và canonical diff.
7. Canary traffic 1%→100% theo gates.
8. Rollback reads về SQL nếu drift/p99 vi phạm.
9. Rebuild/repair khi cần.

### 35.2. Source-of-truth migration

Khó hơn:
- Phải chuyển uniqueness/transaction.
- Single writer authority và fencing.
- Idempotency keys.
- UNKNOWN commit reconciliation.
- External payment side effects.
- Reverse sync/failback.
- SQL có thể stale sau khi NoSQL nhận writes.

Không thể “tắt feature flag quay lại SQL” an toàn nếu source cũ đã thiếu writes sau cutover.

### 35.3. Đánh giá khối lượng backfill thật

Tính:
- Dữ liệu cần copy.
- Source read capacity.
- Destination write capacity.
- Index build time.
- CDC rate/chasing lag.
- Retries.
- Error/quarantine handling.
- Compatibility.
- Validation time.
- Cutover window.
- Temporary doubled storage.

## 36. Quan sát hệ thống sau quyết định

Một scorecard chỉ có giá trị nếu các giả định được đo sau rollout:
- p99 theo query/tenant.
- Hot partitions.
- Index/CDC lag.
- Stale projection counts.
- Unknown commits.
- Retry amplification.
- Quorum/failover events.
- Backups/last verified restore.
- Costs and growth.
- Error budget burn.
- Privacy erasure reconciliation.
- Query mix drift.

### 36.1. Triggers xem lại

Ví dụ:
- Q2 p99 vượt 120 ms liên tiếp theo SLO.
- Top tenant > 60% traffic.
- CDC freshness p99 > 5 giây.
- Số wide partitions vượt policy.
- RTO drill không đạt.
- Chi phí per million operations tăng vượt budget.
- Xuất hiện query pattern không được thiết kế trước.

### 36.2. Không hiểu một lựa chọn là vĩnh viễn

Ngay cả khi quyết định hôm nay đúng, workload và quy định có thể đổi. Lưu evidence/version để có thể tái đánh giá thay vì bắt đầu từ số không.

## 37. Ví dụ ma trận quyết định cho ba chức năng

### 37.1. Booking source

Ưu tiên:
- Durable writes.
- Inventory uniqueness.
- Idempotent operation IDs.
- Transaction/conditional scope.
- Tenant security.
- RPO/RTO.
- Data lineage/audit.

Một ứng viên cực nhanh nhưng không bảo vệ những điều này không pass.

### 37.2. Customer timeline

Ưu tiên:
- Tenant+customer partition routing.
- Stable sort/cursor.
- Bounded range.
- High-cardinality/skew handling.
- Projection freshness.
- Rebuild from source.
- TCO theo long history.

Có thể chọn SQL indexed query, document hoặc wide-column theo kết quả đo.

### 37.3. Property recommendation

Ưu tiên:
- Multi-hop query fit.
- Graph degree distribution.
- Bounded depth.
- Privacy/tenant scope.
- Versioned freshness.
- Rebuild cost.

Nếu nhu cầu chỉ là “top 20 similar properties” theo batch, có thể dùng precomputed list thay graph engine.

## 38. Một buổi đánh giá kỹ thuật thường diễn ra ra sao?

### Bước 1 — Định nghĩa quyết định

Đang chọn:
- Store mới thay source?
- Read model?
- Cache?
- Search?
- Graph recommendation?

Không dùng một ma trận cho scope chưa rõ.

### Bước 2 — Chốt query/data/service contracts

Product + engineering + SRE + security xác nhận query inventory, data distribution, SLO, invariant.

### Bước 3 — Tạo shortlist

Gồm phương án giữ hệ hiện tại và phương án thay thế. Mỗi kiến trúc có data model cụ thể.

### Bước 4 — Hard gate review

Bắt đầu bằng security, correctness, durability, recoverability và operational feasibility. Fail hoặc Unknown quan trọng phải tạo action.

### Bước 5 — PoC ưu tiên rủi ro lớn

Chạy:
- Key/index query correctness.
- Concurrency/idempotency.
- Hot tenant benchmark.
- CDC/backfill.
- Lost ACK/leader failure.
- Restore drill.

### Bước 6 — Chấm điểm từ evidence

Áp rubric chốt trước, ghi run IDs/confidence. Không chấm tên sản phẩm.

### Bước 7 — TCO/sensitivity

Thử growth, traffic skew, region loss, tightened freshness/retention, team capacity.

### Bước 8 — ADR và migration plan

Lựa chọn, hệ quả, rollback/failback, review triggers.

## 39. Những ngộ nhận thường gặp

1. **“NoSQL luôn tốt hơn SQL khi dữ liệu lớn.”** Phụ thuộc workload và scaling strategy.
2. **“Cơ sở dữ liệu có index thì query nào cũng hiệu quả.”** Selectivity và access path quan trọng.
3. **“Point GET benchmark đủ chọn nơi lưu booking.”** Không kiểm tra write invariant.
4. **“Data count đại diện data distribution.”** Skew, size, cardinality khác.
5. **“Trung bình latency quan trọng hơn p99.”** Tail có thể phá SLO.
6. **“p99 chỉ successes phản ánh toàn user traffic.”** Che timeouts.
7. **“Closed-loop benchmark chứng minh offered RPS cố định.”** Có coordinated omission.
8. **“Tất cả tenant phân bố đều.”** Hot tenant có thể thống trị.
9. **“Thêm node xử lý mọi hot key.”** Không chắc.
10. **“Hash partition tốt nhất cho mọi range query.”** Có fan-out.
11. **“Range key tốt nhất cho mọi write workload.”** Có hotspot.
12. **“Một database phải phục vụ mọi use case.”** Có thể polyglot.
13. **“Thêm càng nhiều NoSQL càng tốt.”** Tăng CDC/operations.
14. **“Cứ chấm Redis 5 vì rất nhanh.”** Phải đúng query/role.
15. **“Graph luôn tốt hơn JOIN.”** Chỉ khi traversal phù hợp.
16. **“Wide-column có throughput cao nên query nhiều filter dễ.”** Access pattern giới hạn.
17. **“Nhúng nhiều dữ liệu giúp bỏ mọi JOIN.”** Unbounded document/fan-out.
18. **“Denormalization miễn phí.”** Write amplification/lag.
19. **“Có transaction nghĩa hỗ trợ mọi nghiệp vụ atomic.”** Cần xét scope.
20. **“Có replicas nghĩa RPO=0.”** Không mặc định.
21. **“Backup job succeeded nghĩa RTO đạt.”** Cần restore drill.
22. **“Timeout write chắc rollback.”** Có UNKNOWN outcome.
23. **“Driver retries đảm bảo idempotent payment.”** Không.
24. **“GSI/search index luôn thấy write ngay.”** Có eventual lag.
25. **“Freshness là latency.”** Hai chỉ số khác.
26. **“HTTP 200 nhanh nghĩa đúng.”** Có thể sai tenant/version.
27. **“SLO p99 không cần định nghĩa tính errors.”** Thiếu mẫu.
28. **“Hard gate có thể bù bằng cost score.”** Không.
29. **“Chưa đo cho score 3.”** Tạo bằng chứng giả.
30. **“N/A và UNKNOWN giống nhau.”** Khác.
31. **“Cùng trọng số cho source và cache.”** Không đúng phạm vi.
32. **“Điểm tổng là xác suất thành công.”** Không.
33. **“Chênh 1–2 điểm đã chắc chắn.”** Cần sensitivity.
34. **“Chi phí là phí instance.”** Thiếu nhiều thành phần.
35. **“Managed DB không cần vận hành.”** Application vẫn cần.
36. **“Nhóm biết driver tức sẵn sàng on-call.”** Cần drills.
37. **“Data residency xử lý sau.”** Có thể là blocker.
38. **“Backup data không cần bảo mật.”** Có thể chứa PII.
39. **“Không cần erasure tests cho projection.”** Có resurrection.
40. **“Projection nhanh dù rebuild chậm vẫn tốt.”** DR có thể fail.
41. **“Chỉ benchmark current scale.”** Không có future headroom.
42. **“Load uniform đủ test tenant skew.”** Không.
43. **“Một proxy fault bằng chứng toàn cluster fault tolerant.”** Không.
44. **“Cutover read và write có rollback giống nhau.”** Khác.
45. **“SQL fallback luôn còn mới.”** Có thể stale sau source switch.
46. **“Có thể đổi trọng số sau khi thấy winner.”** Selection bias.
47. **“Tài liệu tính năng là PoC.”** Chưa đo workload.
48. **“Một quyết định không cần ADR/evidence.”** Khó bảo trì.
49. **“Một scorecard xanh là xong QA dữ liệu.”** Cần verify.
50. **“Quyết định đúng mãi mãi.”** Revisit khi giả định đổi.

## 40. Bài tập tổng hợp

Một hệ Booking API có 30M bookings, 10.000 tenants, top tenant 35% traffic, dự báo 300M bookings trong ba năm. Java 21 ứng dụng hiện ghi SQL; nhiều request Q1/Q2 đọc booking. Search có thể stale 5 giây; inventory/payment cần chính xác, RPO mục tiêu 5 phút và RTO 60 phút.

### A. Query catalog

Thiết kế tối thiểu 8 entries cho:
- Booking by ID.
- Customer timeline.
- Property calendar.
- Property text search.
- Recommendation.
- Create booking.
- Confirm/cancel.
- Payment callback.

Mỗi entry nêu keys, filter, sort, page, RPS, p99, consistency, owner.

### B. Data profile

Lập bảng:
- Cardinality customer/property/tenant.
- Booking size p50/p99/max.
- Tenant skew.
- Booking items bounded/unbounded.
- Retention và deletes.
- Schema versions.
- Query-selectivity.

Giải thích vì sao tổng 30M records chưa đủ chọn partition key.

### C. Hard gates

Thiết kế ít nhất tám gates với expected test:
- Tenant isolation.
- Inventory uniqueness.
- Payment idempotency.
- Pagination correctness.
- Search freshness.
- Durability.
- RPO/RTO.
- Privacy erasure.

Gate nào thuộc source, projection và toàn kiến trúc?

### D. Shortlist

So sánh SQL indexed, SQL+KV cache, SQL+document summary, SQL+wide-column timeline, SQL+search, SQL+graph. Đừng yêu cầu mọi component tự đảm nhận payment transaction.

### E. Trọng số và rubric

Thiết kế trọng số tổng 100 cho read timeline. Phân biệt:
- Hard gates.
- Scored preferences.
- Unknown assumptions.
- N/A.

Chấm một candidate dựa vào evidence giả định, ghi rõ trạng thái chưa được thực nghiệm.

### F. PoC Q2

Đặt workload:
- 600 requests/s.
- Page size 30.
- Top tenant 35%.
- Sort createdAt DESC, bookingId ASC.
- Data 100M bookings.

Nêu test exact ordered IDs, p99/timeout, per-partition load và cost.

### G. Fault test

Khi một booking đã commit nhưng ACK mất:
1. Client outcome gì?
2. Retry cùng operationId thế nào?
3. Làm sao phát hiện duplicate?
4. Ảnh hưởng tới điểm chọn source?
5. Khi nào phải loại candidate vì gate FAIL?

### H. TCO

Lập công thức chi phí trong ba năm gồm compute, storage/index, network, CDC, replica, backup, monitoring, staff, migration và rebuild.

### I. Sensitivity

Thay top tenant share thành 70%, data tăng 10×, RTO giảm còn 10 phút, search freshness còn 1 giây. Candidate nào có rủi ro mới và PoC nào cần chạy lại?

### J. ADR

Viết ADR theo:
- Context.
- Scope.
- Hard gates.
- Candidates.
- Evidence.
- Scores/confidence.
- Choice.
- Consequences.
- Migration.
- Rollback/failback.
- Revisit triggers.

### K. Phản biện

Một đồng nghiệp nói:

> “Redis được 96 điểm vì GET nhanh 1 ms, SQL chỉ 78 điểm vì JOIN chậm 20 ms. Chuyển cả booking và payment sang Redis. Mỗi tiêu chí cho trọng số bằng nhau để khách quan. Không cần thử network partition; có replica là RPO=0. Nếu lỗi chỉ việc tắt feature flag về SQL.”

Phản biện về **phạm vi, hard gates, consistency/durability, idempotency, replica vs backup, write-authority cutover và điểm số dựa trên evidence**.

### Hướng giải

Một cách giải đúng:
1. Chọn **đúng role** cho từng database.
2. Lấy query/data/SLO làm nguồn tiêu chí.
3. Viết hard gates cho correctness/security/recovery.
4. Dựng access path/key/index/partition cho từng candidate.
5. Chạy PoC với data skew/peak/fault.
6. Ghi p99, errors, accuracy, retries, cost và recovery evidence.
7. Chỉ chấm ứng viên pass gates; Unknown cần thí nghiệm thêm.
8. Thử kịch bản tăng trưởng và thay đổi SLO.
9. Ghi ADR, migration/canary/rollback có trách nhiệm rõ.

## 41. Checklist ra quyết định

1. **Scope là source, projection, cache, search hay graph đã rõ?**
2. **Danh mục query có key/filter/sort/page/owner?**
3. **Write commands và invariants được liệt kê?**
4. **RPS/peak/latency/error rates có nguồn đo?**
5. **Data size p50/p99/max được biết?**
6. **Tenant/key skew đã được đo?**
7. **Relationship lifecycle/denormalization rõ?**
8. **Retention/TTL/delete/privacy requirements có?**
9. **Schema version/codec constraints có?**
10. **p99 SLO định nghĩa end-to-end và timeouts?**
11. **Freshness SLO riêng cho projection?**
12. **Availability theo kết quả đúng?**
13. **Durability/ACK contract rõ?**
14. **RPO/RTO có business owner phê duyệt?**
15. **Hard gates được ghi và có test?**
16. **Tenant isolation/field auth là gate?**
17. **Inventory/payment idempotency là gate?**
18. **Mỗi query có access path vật lý?**
19. **Index/partition key đã được thiết kế?**
20. **Hot partition/fan-out được đo?**
21. **Shortlist gồm cả giữ SQL khi hợp lý?**
22. **Candidates đại diện kiến trúc đầy đủ?**
23. **PoC dùng data synthetic/skew/scale?**
24. **Benchmark đo offered/sent/completed?**
25. **p99 đi kèm errors/timeouts?**
26. **Có fault/retry/UNKNOWN commit tests?**
27. **Có CDC/tombstone/backfill tests nếu là projection?**
28. **Backup/restore drill đo actual RPO/RTO?**
29. **Security/regional/tier limitations được xác minh?**
30. **TCO gồm data movement, ops và migration?**
31. **Trọng số chốt trước khi biết scores?**
32. **Rubric có anchors?**
33. **Unknown không tự thành điểm?**
34. **Evidence IDs và confidence được ghi?**
35. **Không bù hard gate FAIL bằng score?**
36. **Sensitivity với skew/growth/failover được làm?**
37. **Migration/canary/rollback/failback đã thiết kế?**
38. **ADR ghi lý do chọn và không chọn?**
39. **Có monitoring/revisit triggers sau rollout?**
40. **Quyết định có thể được kiểm chứng lại từ artifacts?**

**Kết luận:** Bảng tiêu chí lựa chọn NoSQL tốt không xuất phát từ tên sản phẩm hoặc tính năng quảng cáo. Nó xuất phát từ **query catalog, data profile và mức phục vụ mục tiêu**, sau đó biến các yêu cầu đó thành **bất biến bắt buộc, đường truy cập có thể thiết kế và phép đo rõ ràng**. Trước tiên loại các phương án không bảo vệ được tính đúng, tenant isolation, durability hoặc RPO/RTO; tiếp theo mới so hiệu năng, khả năng scale, tính linh hoạt, chi phí và vận hành bằng **trọng số có bằng chứng**. Đánh giá phải dùng workload có skew/growth đại diện, có fault/restore tests và không che timeouts hoặc unknowns. Kết quả có thể là giữ SQL, chọn một NoSQL theo vai trò, hoặc kết hợp nhiều stores với CDC/reconciliation và rollback phù hợp. Một quyết định đáng tin là quyết định **giải thích được, tái đo được, vận hành được và có điều kiện xem lại khi giả định đổi**.
