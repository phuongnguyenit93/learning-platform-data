# Đối chiếu mô hình, chỉ mục, giao dịch và phạm vi nhất quán khi lựa chọn NoSQL

## 1. Vấn đề mở đầu: cùng một ứng dụng, bốn câu hỏi khác nhau

Giả sử đội phát triển Java cần chọn hệ lưu trữ cho một dịch vụ đặt chỗ có nhiều tenant. Dữ liệu gồm:

```text
Customer
  id, tenantId, name, contactPreferences

Property
  id, tenantId, city, amenities, geoLocation

Booking
  id, tenantId, customerId, propertyId
  startDate, endDate, status, totalAmount

Availability
  propertyId, date, remainingUnits

Payment
  id, tenantId, bookingId, status
```

Những truy vấn quan trọng:

1. Xem một booking theo ID.
2. Liệt kê booking của khách hàng theo thời gian mới nhất.
3. Tìm chỗ ở theo thành phố, ngày trống, mức giá và tiện nghi.
4. Xác nhận **không bán quá số lượng phòng còn trống** khi nhiều người đặt đồng thời.
5. Sau khi thanh toán thành công, người dùng đọc lại booking phải thấy trạng thái mới.
6. Tìm kiếm full-text và bản đồ với độ trễ chấp nhận được.
7. Chạy báo cáo tổng hợp theo khu vực, theo tháng.

Một người đề xuất document database vì dữ liệu có JSON lồng nhau. Một người đề xuất wide-column vì dự kiến có hàng tỷ bookings. Một người muốn graph vì Customer, Booking và Property có quan hệ. Một người chọn search engine vì giao diện tìm kiếm cần lọc và xếp hạng.

**Tất cả ý kiến đều có phần hợp lý, nhưng chưa đủ để ra quyết định.**

Việc lựa chọn NoSQL phải xem đồng thời bốn trục:

- **Mô hình dữ liệu:** đơn vị lưu, ownership, partition/shard key, quan hệ và mức denormalization.
- **Chỉ mục và truy vấn:** truy vấn nào được hỗ trợ hiệu quả, truy vấn nào phải quét, nhân bản hoặc xây read model.
- **Giao dịch và bất biến:** những thao tác nào cần atomicity/conditional write, phạm vi một document, partition hay nhiều shard.
- **Phạm vi nhất quán:** client, key, partition, transaction, session, replica, region và ứng dụng có được bảo đảm điều gì sau ACK.

Một engine xử lý rất tốt lookup theo khóa **không nhất thiết** cho phép tìm kiếm tùy ý với chi phí thấp. Một engine có transaction **không đồng nghĩa** toàn bộ truy vấn search/index của nó đều cập nhật tức thì. Một system có quorum **không mặc nhiên linearizable cho mọi operation**.

> **Chọn NoSQL bằng cách ghép từng yêu cầu truy vấn và bất biến nghiệp vụ với một cơ chế cụ thể, trong phạm vi được engine/version/deployment hỗ trợ và đã đo bằng workload đại diện.**

## 2. Mục tiêu học tập

Sau bài này, bạn cần:

1. Xác định access patterns, giới hạn latency/throughput và bất biến dữ liệu trước khi chọn mô hình.
2. Phân biệt key-value, document, wide-column, graph, search, time-series và vector store theo **khả năng truy vấn thực tế**.
3. Hiểu primary key, composite/clustering key, secondary index, inverted index, graph adjacency và ANN/vector index.
4. Đối chiếu chi phí index khi ghi, lưu trữ, cập nhật, bảo trì và phân bố dữ liệu giữa shards/regions.
5. Phân biệt **atomicity của một thao tác**, **giao dịch đa thao tác**, **conditional write**, **isolation** và **durability**.
6. Mô tả phạm vi consistency: single key/document, partition, multi-key, transaction, session, cluster và cross-region.
7. Đọc đúng cam kết read-after-write, linearizable, causal, eventual, bounded-staleness và quorum.
8. Xây bảng yêu cầu không thể đánh đổi (*hard gates*) và bảng chấm điểm có trọng số (*trade-off scorecard*).
9. Tạo mô hình thử nghiệm với Java 17, dataset tổng hợp và lịch sử operations có kiểm chứng.
10. Chọn giữa **một engine chính** và **kiến trúc polyglot** có read models/CDC, nhận biết chi phí nhất quán liên hệ thống.

## 3. Vì sao “NoSQL nào tốt nhất?” là câu hỏi chưa xác định đủ?

Một database không tồn tại tách khỏi workload. Câu hỏi có ý nghĩa hơn:

> “Với 50 triệu bookings, 95% truy vấn theo tenant và customer, 4% tìm kiếm theo địa điểm, 1% cập nhật tồn kho, điều kiện không oversell và p99 dưới 200 ms cho critical operations, mô hình nào giảm rủi ro tổng thể tốt nhất?”

Năm yếu tố có thể thay đổi kết quả:

| Yếu tố | Ví dụ ảnh hưởng |
|---|---|
| **Access patterns** | Lookup theo ID khác scan toàn thành phố |
| **Data shape** | JSON lồng nhau, graph rất nhiều cạnh, time series hay vector |
| **Update patterns** | Append-only khác cập nhật/xóa thường xuyên |
| **Invariants** | Không bán trùng phòng, không trừ tiền hai lần |
| **Deployment/SLO** | Single-region, multi-AZ, multi-region active-active, cost/latency |

Ngay cả hai phiên bản/deployment của cùng sản phẩm có thể có tính năng index, transaction, consistency, TTL hoặc quota khác. Tên thương mại là một **ứng viên**; capability thực tế là **điều kiện kiểm chứng**.

## 4. Thu thập danh sách access patterns

Một bảng đầu vào:

| ID | Thao tác | Bộ lọc/sắp xếp | Tải dự kiến | SLO | Tính đúng |
|---|---|---|---|---|---|
| Q1 | Get booking | `tenantId,bookingId` | 8.000/s | p99 ≤80 ms | Đúng tenant, dữ liệu hiện tại |
| Q2 | List bookings | `tenantId,customerId`, mới→cũ | 2.000/s | p99 ≤150 ms | Pagination ổn định |
| Q3 | Search properties | city, dates, price, amenities | 400/s | p99 ≤300 ms | Freshness ≤60s |
| Q4 | Reserve one unit | `propertyId,date` | 700/s | p99 ≤200 ms | Không oversell |
| Q5 | Payment status | `bookingId` | 900/s | p99 ≤120 ms | Không báo paid sai |
| Q6 | Monthly report | time range, region group | 1/giờ | vài phút | Snapshot/report semantics |

**Toàn bộ số liệu là giả định để học.** Dự án thật cần lấy tỷ lệ truy vấn, tần suất update, peak/cold workloads, kích thước dữ liệu và tăng trưởng từ đo đạc phù hợp.

### Đặt câu hỏi cho từng thao tác

- Bắt đầu từ **key** nào?
- Có thể giới hạn được partition không?
- Cần lấy một record, một range, top-K hay traversal?
- Có sort, filter, join, aggregate, geo/FTS/vector không?
- Kết quả cần đọc từ bản vừa ghi hay có thể stale?
- Cần cập nhật bao nhiêu records/partitions nguyên tử?
- Nếu network timeout sau write, làm thế nào tránh duplicate effect?
- Phạm vi tenant/security có bắt buộc lọc trong index/query không?

Một index có vẻ nhanh trên 10.000 records chưa chắc phù hợp với cardinality, hotspots và skew ở 100 triệu records.

## 5. Phân loại yêu cầu thành hard gates và preferences

Không phải mọi tiêu chí đều bù trừ được.

**Hard gate:** một ứng viên phải đáp ứng, nếu không sẽ bị loại hoặc cần thêm một authority/component khác.

```text
G1: Reserve capacity must not oversell.
G2: Every query must enforce tenant isolation.
G3: Committed payment status must survive agreed failures.
G4: Recovery/cutover must meet regulatory and RPO rules.
```

**Preferences/trade-offs:** có thể chấm theo kết quả thực nghiệm:

```text
P1: p99 list-booking read latency
P2: search relevance / geo filtering
P3: write throughput and index cost
P4: operation simplicity / team familiarity
P5: total cost and portability
```

Một ứng viên có p99 nhanh gấp đôi nhưng **không có cách đáng tin ngăn oversell** không nên thắng bằng cộng điểm tốc độ.

### Cấu trúc quyết định

```text
Business invariant / security / durability
                    |
                    v
            HARD-GATE FILTER
                    |
                    v
      Feasible candidate designs
                    |
                    v
    Benchmark + operational evidence
                    |
                    v
      Weighted trade-off analysis
                    |
                    v
       Design review and decision
```

Một “thiết kế ứng viên” có thể gồm database + outbox + search index + cache, không chỉ một engine đơn lẻ.

## 6. Mô hình dữ liệu không chỉ là định dạng JSON

Xét một booking:

```json
{
  "bookingId": "B1001",
  "tenantId": "T01",
  "customerId": "C007",
  "propertyId": "P003",
  "status": "CONFIRMED",
  "startDate": "2026-12-01",
  "endDate": "2026-12-03",
  "totalMinor": 450000
}
```

Đây là một JSON object, nhưng vẫn có thể được lưu dưới:

- Document `booking` trong document database.
- Item có partition key và sort key trong key-value/wide-column table.
- Nhiều relational rows với constraints.
- Node booking + edges customer/property trong graph database.
- Search document trong inverted-index engine.
- Event history trong append-only log.

**Hình dạng dữ liệu trên wire không quyết định mô hình lưu trữ phù hợp.** Quyết định đến từ truy vấn, ranh giới cập nhật, cách partition và tính đúng yêu cầu.

## 7. Key-value: tối ưu khi biết khóa

Một key-value model:

```text
Key:
  BOOKING#T01#B1001

Value:
  {status,customerId,propertyId,dates,totalMinor,...}
```

### Điểm mạnh

- Tra cứu trực tiếp theo khóa thường đơn giản.
- Tốt cho session state, configuration, hot entity lookup, cache, state machine theo key.
- Có thể phân tán theo hash/partitioning tương đối rõ.
- Một số hệ hỗ trợ atomic/conditional mutation trên một key/item.

### Giới hạn

- Truy vấn “tất cả bookings theo customer, sort ngày” cần thiết kế **index hoặc key space riêng**.
- Filter bất kỳ trên JSON value không tự có chỉ mục.
- Range scan và cross-key transactions phụ thuộc sản phẩm.
- Một hot key có thể giới hạn throughput bất kể tổng cụm có nhiều nodes.

### Khi chọn

Thích hợp khi phần lớn workload là `get/put/delete/CAS by known key` và các truy vấn phụ có mô hình rõ ràng.

### Khi không đủ

Nếu sản phẩm phải cho người dùng thay đổi tổ hợp filters tùy ý, key-value thuần có thể dẫn tới nhiều bảng/indices copy, khó đồng bộ và tăng chi phí cập nhật.

## 8. Document: aggregate và trường lồng nhau

Ví dụ:

```json
{
  "_id": "B1001",
  "tenantId": "T01",
  "customer": {
    "id": "C007",
    "nameSnapshot": "Synthetic User"
  },
  "property": {
    "id": "P003",
    "nameSnapshot": "Apartment Demo"
  },
  "items": [
    {"date": "2026-12-01", "units": 1},
    {"date": "2026-12-02", "units": 1}
  ],
  "status": "CONFIRMED"
}
```

### Điểm mạnh

- Đại diện aggregate tự nhiên cho một booking cùng các embedded items.
- Đọc lại toàn aggregate không cần nhiều joins.
- Một số hệ cho atomic update một document và indexes trên trường lồng nhau/arrays.
- Schema có thể tiến hóa linh hoạt hơn khi payload không đồng nhất.

### Giới hạn

- Embedded dữ liệu khách hàng có thể stale khi profile đổi.
- Arrays lớn có thể làm document lớn, cập nhật đắt hoặc chạm item-size limit.
- Cập nhật nhiều documents/shards cần transaction hoặc workflow khác.
- Secondary indexes có write amplification, cardinality và giới hạn multikey/array.

### Mô hình aggregate boundary

Nếu một booking đổi trạng thái cùng tất cả line items và rule yêu cầu atomicity, giữ trong cùng document có thể làm thiết kế đơn giản. Nhưng **tồn kho dùng chung giữa nhiều bookings** không thể nhét an toàn vào mỗi booking rồi giả định các cập nhật độc lập giữ invariant.

## 9. Wide-column: partition key và clustering order

Một bảng có partition theo tenant và customer:

```sql
CREATE TABLE bookings_by_customer (
    tenant_id text,
    customer_id text,
    created_at timestamp,
    booking_id text,
    status text,
    total_minor bigint,
    PRIMARY KEY (
        (tenant_id, customer_id),
        created_at, booking_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    booking_id DESC
);
```

Đây là mô hình CQL minh họa; support syntax/limits tùy phiên bản.

### Điểm mạnh

- Truy vấn Q2 theo partition key và clustering order có đường đọc rõ.
- Có thể thiết kế nhiều bảng theo truy vấn để tránh fan-out.
- Thích hợp dữ liệu lớn, access patterns biết trước và write-heavy workloads.

### Giới hạn

- Muốn `get booking by ID` có thể cần bảng `bookings_by_id` riêng.
- Một customer rất lớn có thể tạo oversized/hot partition; cần bucket/split.
- Các bản biểu diễn denormalized cần được duy trì khi update/delete.
- Arbitrary cross-partition filtering có thể đắt/không phù hợp.
- Atomicity/transaction semantics khác document hoặc SQL database, tùy engine.

### Quy tắc

Thiết kế **partition key từ truy vấn** và xác minh cardinality, skew, query latency, partition size; đừng chọn wide-column chỉ vì “nhiều dữ liệu”.

## 10. Graph: truy vấn theo quan hệ và đường đi

Mô hình:

```text
(Customer C007)
      |
      | MADE
      v
(Booking B1001) --FOR--> (Property P003)
      |
      +--PAID_BY--> (Payment M004)
```

### Điểm mạnh

- Traversal nhiều bước và mẫu quan hệ phức tạp.
- Fraud network, recommendation dựa đường đi, access graph, social relationships.
- Mô hình hóa edges có thuộc tính và identity rõ.
- Một số graph engines cung cấp ACID transactions trong phạm vi được hỗ trợ.

### Giới hạn

- Không phải graph DB nào cũng tối ưu cho timeseries aggregates hoặc full-text/vector search như engine chuyên dụng.
- High-degree nodes/long traversals có thể tạo fan-out rất lớn.
- Cross-partition graph traversals và distributed transactions phụ thuộc implementation.
- Denormalized query/report projections có thể vẫn cần.

### Không suy “có quan hệ” là phải dùng graph

Hầu hết ứng dụng đều có quan hệ giữa entities. Graph đem lại lợi thế khi **traversal theo chiều sâu/mẫu liên kết** là trọng tâm workload, không chỉ vì có foreign key.

## 11. Search engine: inverted index, relevance và geo

Một search document:

```json
{
  "propertyId": "P003",
  "tenantId": "T01",
  "city": "Da Nang",
  "title": "Synthetic Apartment",
  "amenities": ["wifi", "parking"],
  "priceMinor": 225000,
  "location": {"lat": 16.06, "lon": 108.22},
  "sourceRevision": 42
}
```

### Điểm mạnh

- Full-text, text analyzers, relevance scoring.
- Multi-field filter, facets/aggregations và geo queries.
- Search index thường được tối ưu cho retrieval/top-K, không chỉ key lookup.

### Giới hạn

- Index refresh/CDC lag khiến search có thể stale sau source write.
- Bulk index API thường có kết quả từng item, không đồng nghĩa giao dịch nguyên khối.
- Search index là **dữ liệu dẫn xuất** nếu nguồn khác mới là authority.
- Update/deletes, mapping changes và index rebuild có chi phí.

### Lựa chọn phổ biến

Nếu nguồn booking cần bảo đảm không oversell, search engine thường thích hợp làm **read model tìm kiếm**, chứ không mặc định là nơi quyết định duy nhất cho invariant tồn kho.

## 12. Time-series và vector: hai mô hình đặc thù

### Time-series

```text
key:   device/property/metric
time:  eventTime
value: temperature, requests, occupancy, price
```

Các yêu cầu chính: ingest theo thời gian, retention/TTL, downsampling, window aggregation, late events. **Phạm vi transaction và consistency cho updates lịch sử** cần kiểm tra; tối ưu append không đồng nghĩa hỗ trợ arbitrary relational update.

### Vector/ANN

```text
documentId -> embedding [0.12, -0.31, ...]
query vector -> approximate nearest neighbors
```

Các tiêu chí: embedding model/version, dimension, recall@k, latency, metadata filter, index build/refresh, delete propagation. **ANN recall** là một trục chất lượng riêng: kết quả approximate nearest neighbors không giống exact query cho mọi vector.

### Có thể kết hợp

Một sản phẩm có thể dùng document/SQL làm authority, search cho full-text/geo và vector index cho semantic discovery. Khi đó **pipeline đồng bộ và độ mới dữ liệu** trở thành một phần quyết định, không phải chi phí phụ nhỏ.

## 13. Bảng so sánh mô hình ở mức khái niệm

| Mô hình | Đường truy vấn đặc trưng | Điểm mạnh | Câu hỏi phải kiểm chứng |
|---|---|---|---|
| Key-value | By known key | Đơn giản, direct lookup | Secondary query và atomic scope? |
| Document | By ID, indexed fields, nested JSON | Aggregate, schema flexibility | Multikey index, multi-doc transaction? |
| Wide-column | Partition key + clustering range | Predictable high-scale queries | Hot partition, duplicate tables? |
| Graph | Path/traversal/relationship | Multi-hop relationship | Traversal partitioning, transaction scope? |
| Search | Full-text/filters/geo/top-K | Ranking và search facets | Refresh lag, source-of-truth? |
| Time-series | By entity + time window | Ingest, retention, rollups | Late corrections, cardinality? |
| Vector | Similarity + metadata filter | Semantic retrieval | Recall, filter correctness, freshness? |

Đây là **kiểu workload thường phù hợp**, không phải danh sách cấm/cho phép. Một engine hiện đại có thể hỗ trợ nhiều loại index và API; phải xem **độ trưởng thành, hạn chế, deployment và workload đo được**, không chọn chỉ theo nhãn “đa mô hình”.

## 14. Mô hình quyết định phải đi cùng đường truy cập vật lý

Một thao tác:

```text
List bookings for customer C007, newest first, page size 20.
```

Có nhiều cách thực hiện:

**Model A — Secondary index của document DB**

```text
Bookings collection
  index: (tenantId, customerId, createdAt DESC, bookingId DESC)
  |
  v
Fetch 20 matching documents
```

**Model B — Wide-column query table**

```text
bookings_by_customer partition (T01,C007)
  clustering key (createdAt DESC, bookingId DESC)
  |
  v
Read first 20 clustering rows
```

**Model C — Key-value read model**

```text
CUSTOMER_BOOKINGS#T01#C007
  -> list of booking IDs with sort metadata
  -> batch-get individual booking values
```

Cả ba có thể đáp ứng Q2, nhưng:

- A tăng chi phí duy trì index khi booking thay đổi.
- B có thể nhân đôi trạng thái giữa các bảng.
- C cần logic duy trì danh sách, giới hạn kích thước và ordering.

Đánh giá không dừng ở “có cách query”. Phải đo **chi phí reads, write amplification, failure windows, pagination stability và điều kiện nhất quán**.

## 15. Primary key: điều kiện bắt buộc để định danh chính xác

Một khóa đơn:

```text
bookingId = B1001
```

Trong hệ đa tenant, một khóa đầy đủ có thể là:

```text
tenantId + bookingId = (T01,B1001)
```

### Cần hỏi

- Uniqueness là global hay chỉ trong một tenant?
- ID có được sinh từ authority đáng tin không?
- Hash/partition key là gì?
- Key có hỗ trợ range scan/sort không?
- Entity delete/recreate có tái sử dụng ID và reset version không?

### Tenant isolation

Nếu lookup theo `bookingId` không chứa tenant scope trong route/query/authorization, có nguy cơ vô tình đọc booking của tenant khác. Một key thiết kế tốt **hỗ trợ** scoping nhưng không thay chính sách authz kiểm tra danh tính và quyền.

### Không mặc định một trường tên `id` là globally unique

Unique constraints và shard key có thể tương tác tùy engine. Nếu business đòi unique email/booking number toàn hệ, phải xem **phạm vi thực sự của constraint** và quy trình thay đổi key.

## 16. Composite index và quy tắc sort/filter

Giả sử Q2:

```sql
SELECT * FROM bookings
WHERE tenantId = ?
  AND customerId = ?
  AND status = ?
ORDER BY createdAt DESC, bookingId DESC
LIMIT 20;
```

Một index ứng viên:

```text
(tenantId, customerId, status, createdAt DESC, bookingId DESC)
```

Một index khác:

```text
(tenantId, customerId, createdAt DESC, bookingId DESC)
```

### Điểm đánh đổi

Index đầu giúp query có `status` equality predicate. Nhưng nếu phần lớn queries **không lọc status**, sort/range efficiency có thể thay đổi theo left-prefix/planner capabilities của engine.

Index thứ hai hỗ trợ mọi bookings theo customer, nhưng status filter có thể còn phải lọc sau khi scan các records liên quan.

**Thứ tự cột, sort direction, cardinality và loại predicate có tác động thực**, không chỉ có hay không một field trong index.

### Giới hạn portabilty

Quy tắc left-prefix, multikey, skip scan, covering và index intersection thay đổi giữa MongoDB, document DB khác, SQL, search engines. Không lấy nguyên một quy tắc planner của một hệ để suy cho tất cả NoSQL.

## 17. Index selectivity và cardinality

Giả sử:

```text
total bookings = 100,000,000
tenant T01     =  10,000,000
status PAID    =  60,000,000
customer C007  =         30
```

Một index chỉ trên `status` có selectivity thấp cho `PAID`. Một index có `tenantId+customerId` có thể thu hẹp còn vài chục records.

### Nhưng không chỉ nhìn trung bình

Một “super customer” có 500.000 bookings có thể làm index/partition nóng. Một city nổi tiếng có 70% properties tạo load skew.

Các thống kê cần:

- Distinct values/cardinality.
- Top-K hot keys và distribution tail.
- Records per tenant, customer và partition.
- Query selectivity ở peak.
- Sort/limit behavior.
- Rows scanned vs rows returned.
- Memory/disk cache hit rates.

### Predicate pushdown

Nếu query dùng filter sau khi lấy 1 triệu records, latency và cost khác hẳn index pushdown trả 20 rows. Cần xem execution plan/explain hoặc metrics scan/read units của engine.

## 18. Secondary index không phải “bảng miễn phí”

Một write thay đổi `status`, `price` và `city` có thể yêu cầu cập nhật nhiều indexes:

```text
Application write booking
   |
   +--> primary document/item
   +--> customer+date index
   +--> tenant+status index
   +--> search projection
   +--> analytics CDC event
```

Chi phí có thể bao gồm:

- Write amplification.
- Storage cho index entries.
- Index build/rebuild.
- Compaction/merge/refresh.
- Network và cross-AZ replication.
- CDC processing, retry và duplicate events.
- Thêm consistency boundary cần giám sát.

### Ước lượng đơn giản

Nếu mỗi logical write tạo \(I\) index mutations trung bình và \(P\) projection updates:

\[
W_{\mathrm{physical}}\approx
W_{\mathrm{logical}}\times(1+I+P)
\]

Đây chỉ là **mô hình khái niệm**; một index mutation có thể gồm nhiều physical writes/replicas, còn hệ thống có thể batch/compact. Không dùng công thức này làm dự báo IOPS chính xác nếu chưa benchmark.

## 19. Covering index, projection và đọc thêm record

Một query chỉ cần:

```text
bookingId, createdAt, status
```

Nếu index đã chứa đủ các trường cần trả, planner có thể tránh fetch document gốc trong những engine hỗ trợ **covering/index-only query**.

Nhưng:

- Included/stored fields tăng kích thước index.
- Index covering với field sensitive đòi access control tương ứng.
- Một số điều kiện update mới chưa visible trong index asynchronous.
- Query return đúng field nhưng stale version vẫn có thể vi phạm RYW.

### Benchmark

So sánh:

1. No secondary index.
2. Composite index với sort fields.
3. Covering index/primary-key read model.

Đo p50/p95/p99, entries scanned, bytes returned, storage footprint và update throughput. Chỉ tăng index khi lợi ích đối với **query thực và SLO** biện minh chi phí.

## 20. GSI, local secondary index và global index: chữ “index” chưa đủ

Hai indexes cùng hỗ trợ lookup theo email có thể khác:

- Cập nhật đồng bộ hay bất đồng bộ với source write?
- Index có nằm cùng partition/leader không?
- Read concern mạnh có áp được trên index không?
- Build index trong khi live writes thì quan sát thế nào?
- Có thể trả state cũ hoặc missing record sau ACK không?

### Ví dụ DynamoDB

Đọc strongly consistent trên base table/LSI trong phạm vi hỗ trợ không đồng nghĩa **GSI** hỗ trợ strongly consistent reads. GSI thường được cập nhật bất đồng bộ và không hỗ trợ tùy chọn strong read của base table.

### Ví dụ Elasticsearch

Index API có thể ACK nhưng search query chưa thấy update trước refresh. Đây là **search visibility semantics**, khác một lần GET document theo ID.

### Bài học

Chỉ mục là một **đường đọc có consistency contract riêng**. Khi đề xuất một index để đáp ứng truy vấn, hãy nêu luôn **freshness và rollback/repair behavior**.

## 21. Inverted index, analyzer và search quality

Đối với tìm chỗ ở:

```text
Query: "apartment near beach with parking"
```

Một index theo exact keyword và một inverted text index với analyzer/stemming/synonyms có semantics khác:

- Keyword filter trả match chính xác theo token/value.
- Full-text search phân tích từ, ranking/relevance.
- Geo filter và polygon search cần hỗ trợ geometry phù hợp.
- Synonyms/analyzer changes có thể đòi reindex.

### Không đánh đổi tính đúng âm thầm

Một search engine trả top 20 kết quả đúng text nhưng **không lọc tenant** là sai nghiêm trọng. Một vector search trả semantic-near kết quả nhưng bỏ sót bộ lọc phòng đã được đặt cũng sai nghiệp vụ.

### Tiêu chí cần đo

- Precision/recall/relevance với test queries.
- Filter correctness.
- Geo boundary correctness.
- p95/p99 với sort/facets thực.
- Indexing throughput và refresh lag.
- Cost of rebuild, alias cutover và rollback.

## 22. ANN vector index và điều kiện metadata filter

Giả sử:

```text
Find 10 semantically similar properties
WHERE tenantId = T01
  AND city = Da Nang
  AND price <= budget
```

Một ANN algorithm có thể trả top-K approximate gần đúng. Nếu engine lọc metadata **sau** ANN thay vì trong candidate selection, kết quả có thể ít hơn K hoặc recall kém với filter rất hẹp.

### Cần biết rõ

- Filter trước/sau/trong candidate search?
- Approximation error và recall@k?
- Các vectors vừa cập nhật có search-visible ngay không?
- Delete/TTL của source được áp vào vector index khi nào?
- Model version khác nhau có thể so similarity score trực tiếp không?

### Chọn engine

Không chỉ chấm “có vector search = 1”. Cần benchmark **hybrid filter + ANN recall + indexing freshness + operational cost** với dữ liệu synthetic/được phép.

## 23. Graph indexing và traversal fan-out

Graph query:

```cypher
MATCH (c:Customer {id: $customerId})-[:MADE]->(b:Booking)
      -[:FOR]->(p:Property)
WHERE p.city = $city
RETURN b, p
LIMIT 20
```

Index khởi điểm trên `Customer(id)` giúp định vị node, nhưng sau đó traversal còn phụ thuộc:

- Degree của customer.
- Số edges mỗi hop.
- Filter pushdown.
- Cross-partition/network hops.
- Graph engine planner và traversal depth.

### Anti-pattern

Một graph có 1 tỷ edges nhưng mỗi query chỉ là `get booking by ID` có thể không tận dụng lợi thế graph. Ngược lại relational/document joins 8 hops trên graph gian lận lớn có thể phức tạp hoặc tốn kém.

### Test

Benchmark traversal p95/p99 với **high-degree nodes và path distributions**. Không chỉ test một graph nhỏ, đều bậc.

## 24. Hot partition và shard key: index nhanh không đủ

Giả sử partition theo `tenantId`:

```text
Tenant small 1..1000:  100 requests/s total
Tenant giant T_BIG:  9000 requests/s
```

Một hot tenant có thể dồn toàn bộ tải vào một partition, dù cluster có 100 nodes.

### Lựa chọn

- Composite partition key thêm bucket/day/hash khi access pattern cho phép.
- Tách hot tenant hoặc hot entity.
- Đặt read replicas/caches đúng dữ liệu cho phép stale.
- Dùng write sharding/escrow quota nếu business invariant có thể chia.
- Điều chỉnh query/fan-out trade-off.

### Chi phí

Phân nhỏ partition giúp phân tán writes nhưng có thể làm:

```text
List all bookings for tenant
  -> query 32 buckets in parallel
  -> merge/sort/deduplicate
``

Vì thế shard key, indexes và transaction scope **phải xem cùng nhau**. Một lựa chọn giúp write throughput nhưng làm multi-bucket atomic update khó hơn có thể không chấp nhận.

## 25. Pagination và index là một phần mô hình

Một query:

```text
List newest bookings for customer, page size 20
```

Deep offset có thể đắt:

```text
OFFSET 5,000,000 LIMIT 20
```

Keyset/seek pagination cần sort key ổn định và unique tie-breaker:

```text
createdAt DESC, bookingId DESC
```

### Khi dữ liệu liên tục thay đổi

Keyset có thể vẫn không tạo **snapshot nhất quán** nếu source hoặc sort key bị thay đổi trong lúc đọc. Nếu business yêu cầu export/scan chính xác, cần snapshot/PIT hoặc change capture protocol.

### Khi index không đủ

Nếu sort theo một computed score thay đổi liên tục, page tokens hoặc keyset có thể không ổn định. Đánh giá snapshot search/pagination API và query plan thực sự.

## 26. Chi phí index lifecycle

Không phải chỉ cần tạo index một lần:

```text
Plan -> Build -> Backfill -> Validate
     -> Serve reads -> Maintain writes
     -> Alter schema -> Rebuild/Retire
```

### Cần hỏi

1. Build online hay downtime?
2. Cần bao nhiêu disk headroom và write capacity?
3. Index build có giữ consistency snapshot với concurrent writes không?
4. Version/mapping thay đổi thì rebuild có thể resume không?
5. Xóa dữ liệu/TTL có propagate tới index không?
6. KMS/IAM/index repository có phạm vi độc lập không?
7. Query planner có chọn index đúng hay cần hints/rewrite?
8. Nếu index corruption/rebuild, ứng dụng có fallback không?

“Có index” không đủ để coi operation Q3 hoàn thành SLO trong suốt rolling migration hoặc disaster recovery.

## 27. Chỉ mục cũng là bản sao dữ liệu nhạy cảm

Một source document chứa email, địa chỉ và vị trí địa lý. Search index có thể giữ:

- Plaintext field values trong stored source.
- Term/posting lists.
- Doc values.
- Tokenized fields.
- Vectors suy ra từ nội dung.
- Snapshots/repositories.

Việc API không hiển thị field email **không chứng minh index artifact không có email**.

### Yêu cầu đánh giá

- Tenant scoping ngay khi query/index.
- Least privilege cho index snapshot/export.
- Encryption at rest/in transit, backup retention.
- Delete/consent propagation.
- Không log raw query parameters/token hay vector payload nhạy cảm.

Security là một hard gate trước khi so sánh tốc độ.

## 28. Bảng đối chiếu chỉ mục

| Loại chỉ mục | Phù hợp | Chi phí/rủi ro |
|---|---|---|
| Primary key/hash | Point lookup | Hạn chế non-key filters |
| Composite ordered key | Equality prefix + range/sort | Cần query/key order phù hợp |
| Secondary index | Filter non-primary field | Write/storage amplification |
| Covering index | Projection không fetch base record | Index lớn, field security |
| GSI/asynchronous index | Lookup nhiều access patterns | Stale visibility, update lag |
| Inverted text index | Full-text/relevance | Analyzer/reindex, near-real-time |
| Geo index | Spatial filters/nearby | Geometry precision, query cost |
| Graph adjacency/index | Traversal/relationship | High-degree fan-out |
| Time-series index | Entity/time windows | Ingest hot buckets, retention |
| ANN/vector index | Similarity search | Approximate recall, build/update cost |

Không coi các tên trên là capability mặc định của mọi NoSQL. Ghi **engine/version/edition/config** cho từng phương án và đo bằng đúng API sẽ dùng.

## 29. Giao dịch: câu hỏi đầu tiên là bất biến nào phải giữ

Một Booking và một Availability liên hệ:

```text
Availability(property=P003,date=2026-12-01,remaining=1)

Client A: reserve 1 unit.
Client B: reserve 1 unit.
```

Nếu cả hai đọc `remaining=1` rồi cùng ghi `remaining=0` và tạo booking thành công, hệ có thể xác nhận **hai booking trong khi chỉ còn một phòng**.

Bất biến:

\[
\forall(p,d),\quad
\mathrm{confirmedUnits}(p,d)
\le \mathrm{availableCapacity}(p,d)
\]

Lựa chọn database phải trả lời:

- Có thể **atomic conditional decrement** trên authoritative key không?
- Một booking nhiều đêm cần khóa/trừ tồn kho nhiều days nguyên tử không?
- Nếu giữa các bước có timeout/partial failure, ứng dụng có giữ invariant hoặc compensation đúng?
- Một booking đã confirm có thể bị read từ stale replica rồi confirm lần nữa không?

Đây là lý do **giao dịch phải đối chiếu với mô hình/partition key**, không thể chấm độc lập “database hỗ trợ transaction = 5/5”.

## 30. Atomicity của một item khác giao dịch nhiều item

Ba cấp:

**A. Atomic single-key/item mutation**

```text
UPDATE inventory[P003,2026-12-01]
SET remaining = remaining - 1
IF remaining >= 1
```

Một conditional update được thực thi đúng ở authority có thể ngăn hai clients cùng trừ một đơn vị cuối của **một record**.

**B. Transaction nhiều records trong một scope**

```text
Atomically:
  decrement inventory(day1)
  decrement inventory(day2)
  create booking B1001
``

Cần xem engine có hỗ trợ transaction qua những keys/partitions/collections liên quan hay không.

**C. Workflow qua nhiều services**

```text
Reserve inventory -> Create booking -> Charge provider -> Email
```

Đây thường không còn là một database transaction. Payment provider và email ở **trust/system boundary khác**, cần idempotency, outbox, durable state machine, reconciliation và compensation.

### Từ “atomic” phải luôn kèm phạm vi

“Atomic update of one document” không đồng nghĩa “atomic across all bookings in a shard”; “ACID transaction” không tự bao gồm Kafka event hoặc third-party payment effect.

## 31. ACID là bốn thuộc tính, không phải một công tắc

| Thuộc tính | Câu hỏi kiểm thử |
|---|---|
| **Atomicity** | Mọi thay đổi thuộc cùng transaction được áp hoặc không áp trong scope nào? |
| **Consistency** | Transaction giữ các invariant đã được mô hình hóa ra sao? |
| **Isolation** | Các transaction concurrent quan sát/interleave thế nào? |
| **Durability** | Sau khi commit ACK, dữ liệu còn sau failures nào? |

### Cần tránh hai hiểu lầm

1. “Transaction ACID” không tự bảo vệ mọi **business invariant** nếu ứng dụng kiểm tra sai hoặc ràng buộc không được enforce.
2. “NoSQL không có transaction” là phát biểu sai ở mức toàn ngành: nhiều hệ NoSQL cung cấp transactions nhưng **giới hạn phạm vi, isolation, quota, latency và deployment** khác nhau.

## 32. Isolation: read committed, snapshot và serializable không giống nhau

Một giao dịch:

```text
T1 reads availability A and B.
T2 changes A.
T1 writes B based on old A.
``

Tùy isolation, T1 có thể quan sát một snapshot hợp lệ nhưng vẫn gây **write skew** nếu bất biến nằm trên nhiều records.

### Các hiện tượng

- **Dirty read:** đọc dữ liệu chưa commit rồi bị rollback.
- **Non-repeatable read:** cùng transaction đọc cùng item hai lần thấy thay đổi.
- **Phantom:** query cùng predicate trả thêm/bớt rows do concurrent transaction.
- **Lost update:** hai writers cập nhật dựa trên cùng state cũ, một ghi đè kết quả kia.
- **Write skew:** hai transactions đọc cùng trạng thái, ghi các records khác nhau và phá invariant chung.

Không có nghĩa tất cả engines cho phép mọi hiện tượng; phải đọc precise guarantee.

### Snapshot isolation không phải luôn serializable

Ví dụ:

```text
Constraint: at least one doctor on call.
T1 reads A=on,B=on; writes A=off.
T2 reads A=on,B=on; writes B=off.
Both commit under a weakly conflicting snapshot protocol.
Result A=off,B=off violates invariant.
```

Nếu business cần ràng buộc toàn cục, dùng cơ chế serialize/lock/conditional authority phù hợp, không chỉ “bật snapshot reads”.

## 33. Transactions và partition key gắn chặt với nhau

Nếu availability cho mỗi property-date là một key:

```text
PK = (propertyId, date)
```

Booking ba đêm đụng ba keys:

```text
(P003, 2026-12-01)
(P003, 2026-12-02)
(P003, 2026-12-03)
```

Với engine chỉ có atomicity per key/partition, thao tác trừ cả ba ngày **không tự atomic**.

### Những lựa chọn kiến trúc

1. **Chọn engine hỗ trợ transaction qua các keys** và đã chứng minh latency/conflict under load.
2. **Thiết kế aggregate inventory theo property/calendar** để một mutation authoritative kiểm đủ ngày, nếu size/hotspot cho phép.
3. **Reservation ledger/escrow quota** phân phối tokens và reconcile theo business invariants.
4. **Saga/hold-confirm** với trạng thái pending, idempotency, expiry và compensation được xác định.

### Đánh đổi

Gom mọi dates vào một aggregate có thể thuận tiện cho atomicity nhưng tạo **hot key**, giới hạn item size và contention. Chia ngày thành nhiều partitions giúp throughput nhưng làm invariant đa ngày phức tạp. **Mô hình và transaction scope quyết định lẫn nhau.**

## 34. Conditional write (CAS) thường đáng giá hơn một lock ngoài

Một optimistic concurrency flow:

```text
Read inventory version=8, remaining=1
Try update:
   remaining=0, version=9
   IF version=8 AND remaining>=1
``

Hai clients cùng đọc version=8:

- Một client update thành công.
- Client kia bị condition-failed, phải đọc lại/recompute hoặc trả sold-out.

### Điều kiện

Conditional update phải được thực thi **atomic tại authoritative storage** theo API. Nếu code:

```java
if (readRemaining() > 0) {
    writeRemaining(0);
}
```

thì **read-then-write riêng lẻ** có race; không phải CAS.

### Lock lease không tự là transaction

Distributed lock ở một hệ khác có thể hết hạn trong lúc worker bị pause, rồi worker cũ vẫn ghi vào DB. Nếu dựa vào lease, cần **fencing token** được kiểm tra ở sink; nếu không, conditional write có thể an toàn hơn.

## 35. Idempotency không giống atomicity

Một request:

```text
POST /bookings with Idempotency-Key=REQ-123
``

Server tạo booking B1001, nhưng response mất. Client retry.

Nếu server chỉ có atomic insert B1001 nhưng lần retry sinh B1002, **hai bookings** vẫn có thể được tạo.

### Thiết kế ledger

```text
Idempotency ledger key: (tenantId,REQ-123)
Value: bookingId, requestHash, state, result
``

Khi retry:

- Cùng key + cùng payload → trả lại outcome hoặc trạng thái pending.
- Cùng key + payload khác → reject conflict.
- Unknown commit → reconcile authority, không đoán failure.

### Ranh giới atomic

Để tránh vừa tạo booking vừa không lưu idempotency claim, ledger và business effect cần một **atomic boundary** hoặc protocol đã chứng minh an toàn. TTL idempotency phải dài đủ retry/reconciliation horizon.

### Không tuyên bố “exactly once” tùy ý

Network delivery có thể at-least-once. Mục tiêu thường là **một logical business effect** qua deterministic key, conditional mutation, inbox/outbox hoặc durable workflow.

## 36. Unique constraint theo tenant, shard và toàn cụm

Ví dụ yêu cầu:

```text
Within each tenant, bookingReference must be unique.
```

Một index unique trên `bookingReference` nếu chỉ enforce trong một partition/shard scope có thể **không bảo đảm unique toàn tenant** khi tenant nằm trên nhiều partitions.

### Cần hỏi

- Uniqueness áp trên keyset nào?
- Unique index có hỗ trợ sharded collection/table/region mode đó không?
- Null/missing/collation/case-insensitive semantics ra sao?
- Có thể đổi email hoặc bookingReference không?
- Nếu cross-region active-active, hai regions cùng claim một value thì conflict thế nào?

### Guard/registry pattern

Một authority có conditional key:

```text
UNIQUE#T01#normalized-reference-R123 -> bookingId B1001
``

Tạo claim trước khi confirm booking; giữ claim và booking state nhất quán qua transaction/workflow. Nhưng **registry và booking thuộc hai systems** vẫn có dual-write failure windows, cần outbox/saga/reconciliation.

### Index unique không tự thay schema normalization

`"ABC"`, `"abc"`, Unicode normalization và whitespace có thể tạo duplicates theo business nhưng khác binary key. Định nghĩa normalized business identity rõ và kiểm collision.

## 37. Giao dịch và secondary index có thể nhìn thấy khác thời điểm

Một transaction commit:

```text
Booking B1001 status=CONFIRMED
Index by customer updated async
Search index updated via CDC
```

Core transaction có thể atomic trên authoritative records, nhưng:

- Global secondary index ở một dịch vụ có thể có propagation lag.
- Search projection chưa refresh.
- Cache còn version cũ.
- Analytics chỉ có snapshot cuối ngày.

Đây là các **consistency boundaries riêng**. Không nói “transaction commit nên mọi query trên mọi index đều thấy ngay”.

### User-facing RYW

Nếu người dùng vừa xác nhận booking cần thấy nó trong `My bookings`, cần read path đủ mới: source query/causal context/versioned index hoặc pending UX. Một projection eventual vẫn có thể phục vụ public search nếu business cho phép.

## 38. Transaction đa shard và cái giá của phối hợp

Một multi-shard transaction có thể yêu cầu:

```text
Coordinator
   |
   +-- Prepare shard A
   +-- Prepare shard B
   +-- Commit decision
   +-- Apply and acknowledge
```

Các hệ có thể sử dụng biến thể consensus/2PC/transaction protocol khác nhau; sơ đồ chỉ minh họa ý tưởng **phối hợp nhiều nơi**.

### Cái giá

- Nhiều network round trips.
- Conflict/lock contention.
- Coordinator recovery, transaction timeout.
- Ảnh hưởng latency khi một shard/zone bị lỗi.
- Limits về số items/shards/bytes/duration.
- Index/CDC interactions và abort/retry overhead.

### Lưu ý

Không phải cứ có option "transactions" là chi phí giống SQL một node. Benchmark **p99 transaction commit under contention and AZ failure**, không chỉ một demo 2 records.

## 39. Saga không tạo atomic commit toàn bộ workflow

Với booking/payment:

```text
RESERVE_INVENTORY
      |
      v
CREATE_BOOKING_PENDING
      |
      v
PAYMENT_AUTHORIZE
      |
      v
CONFIRM_BOOKING
``

Nếu payment fail:

```text
RELEASE_RESERVATION
MARK_BOOKING_FAILED
``

### Điều phải kiểm chứng

- Mỗi bước có durable state và idempotency key.
- Compensation có thể fail; ai retry/reconcile?
- Một số hiệu ứng không thể “undo” thật (email, chuyển tiền đã settlement).
- Bên thứ ba có idempotency/unknown-outcome semantics.
- Holds có TTL/expiration protocol, không gây double release.

Saga là **eventual workflow consistency**, không phải transaction ACID của toàn hệ. Có thể phù hợp nếu business chấp nhận pending states và đã xử lý các rủi ro.

## 40. Outbox: transaction của dữ liệu và event

Ví dụ update booking và yêu cầu phát event:

```text
DB transaction:
  update Booking B1001 -> CONFIRMED
  append Outbox Event E777

Commit
  |
  v
Outbox relay -> broker -> search/notifications
``

Nếu DB hỗ trợ atomic boundary cho booking + outbox record, điều này tránh trạng thái booking commit nhưng không có durable event intent trong cùng boundary.

### Vẫn cần

- Relay replay idempotently sau crash.
- Consumers có dedup/conditional version.
- Publish outcome unknown và broker retries.
- Offset/checkpoint không vượt sink effect chưa bền.
- Event schema tối thiểu, tránh gửi PII không cần.

### Không gọi relay exactly-once end-to-end

Relay có thể gửi cùng event hai lần nếu ACK từ broker mất. Invariant cần **idempotent consumer effect**, không chỉ “outbox pattern có sẵn”.

## 41. Durability và consistency không cùng trục

Một write có thể:

- Được primary ACK và visible ngay ở primary nhưng chưa được replicated bền.
- Được majority ACK nhưng một eventual read trên replica khác vẫn chưa được thấy (tùy protocol/session).
- Được phục hồi bền sau failover nhưng search index còn lag.

**Durability:** có mất một write đã cam kết khi crash/failover không?

**Visibility/consistency:** read thấy version nào và theo thứ tự nào?

**Availability:** thao tác hoàn tất trong deadline nào?

Ba trục phải có criteria riêng.

## 42. Đừng chỉ đọc marketing “ACID support”

Checklist giao dịch:

1. Áp dụng trên **một key/document, một partition, một shard, nhiều shard, nhiều collections/tables** hay toàn region?
2. Có isolation level chính xác nào?
3. Có transaction retry/commit unknown outcome không?
4. Có conditional mutation/CAS được thực thi ở storage không?
5. Write ACK theo journal/replica/quorum nào?
6. Transaction duration, item, size, fan-out, throughput limits?
7. Khi leader/zone mất, commit decision được phục hồi thế nào?
8. Read index/cache/CDC có thấy cùng transaction atomic không?
9. Có multi-region transaction không, hay chỉ local region?
10. Latency/cost của transactions under concurrent contention thế nào?

Đối chiếu bằng **API và deployment version cụ thể**, không dựa vào một checkbox tính năng.

## 43. Transaction không thay kiểm thử business invariant

Một test cần minh họa:

```text
Initial remainingUnits=1

Run 100 concurrent reserve attempts for same
property/date, each with distinct request ID.

Expected:
  successful reservations <=1
  final remainingUnits>=0
  no duplicate reservation per idempotency key
  failure/timeout outcomes reconciled
```

Đây là một thử nghiệm trên **key nóng**, phù hợp để lộ races. Thử tiếp:

- Multiple nights (multi-key).
- Partial transaction failure.
- Primary failover giữa prepare và commit.
- Client timeout sau commit.
- Retry với same key.
- Cross-region route change.

Nếu test chỉ chạy tuần tự, có thể không phát hiện race của hai writers đọc cùng state.

## 44. Khi nào một entity-level transaction đủ?

Một ví dụ good fit:

```text
Atomic update inside Booking document:
  status=PENDING -> CONFIRMED
  confirmTime=...
  paymentReference=...
  revision=12
  IF previousStatus=PENDING
```

Nếu tất cả fields đều nằm trong **một aggregate** và invariant nội bộ, single-document/key conditional mutation có thể đủ mà không cần multi-shard transaction.

Nhưng nếu cùng transaction phải giảm Availability của nhiều dates và tạo Payment ledger, aggregate boundary chưa chắc đủ. Lúc đó xem lại model/authority/workflow.

### Không biến một document thành “toàn hệ trong một record”

Đưa hàng triệu bookings, calendar slots và financial ledger vào một document lớn để có atomicity có thể vượt size limit, tạo hot key và làm migration khó. Phải cân bằng **aggregate size, contention, query access và invariant scope**.

## 45. Bảng đối chiếu cơ chế giữ bất biến

| Bất biến | Scope hợp lý | Cơ chế ứng viên | Thử nghiệm |
|---|---|---|---|
| Status change hợp lệ | Single booking | CAS / conditional update | Concurrent double-confirm |
| Unique booking reference/tenant | Tenant scope | Unique index/registry authority | Concurrent same reference |
| Không oversell một date | Inventory key | Atomic conditional decrement | 100 concurrent reservations |
| Không oversell ba dates | Multi-key / aggregate | Multi-key transaction, escrow, saga | Partial reservation/failure |
| Payment exactly one logical charge | Workflow + provider | Idempotency ledger/provider key | Timeout after provider commit |
| Booking event không mất | Booking+outbox boundary | Atomic outbox intent | Crash after DB commit |
| Search không hồi sinh deleted booking | Source+projection | Revision/tombstone guard | CDC reorder and retry |
| Tenant không đọc chéo | End-to-end authorization | Tenant key/query scope + authz | Adversarial cross-tenant requests |

Chỉ khi thiết kế có cách giữ **từng invariant** thì mới chuyển sang chấm điểm hiệu năng/chi phí. Giao dịch “có” nhưng không phủ đúng invariant không phải giải pháp.

## 46. Phạm vi nhất quán: “strong” không đứng một mình

Một claim có ích phải ghi:

```text
Operation:
  Read booking B1001 by primary key

Scope:
  One item in region R1

Write:
  Conditional update ACK with specified write concern

Read:
  Strongly consistent mode supported by base table

Guarantee:
  Observes latest committed value under documented conditions
```

Không nên viết:

```text
Database X is strongly consistent everywhere.
```

Vì cùng sản phẩm có thể:

- Strong read trên primary key nhưng eventual read trên GSI.
- Atomic single item nhưng non-atomic bulk import.
- Causal session trong một region nhưng async replication giữa regions.
- Snapshot-consistent transaction read nhưng search index refresh sau commit.

### Các chiều scope

| Chiều | Ví dụ |
|---|---|
| Đơn vị dữ liệu | Key, document, partition, collection, multi-key |
| Loại thao tác | GetItem, Query, transaction, Scan, Search, CDC |
| Client | Một operation, một session, nhiều clients |
| Không gian | Node, AZ, region, cross-region |
| Thời gian | Sau ACK, sau refresh, sau replica catch-up |
| Lỗi | Node crash, network partition, failover, restore |

Một bảng đánh giá NoSQL thiếu các chiều này sẽ dễ so **hai thứ khác nhau dưới cùng từ “consistency”**.

## 47. Linearizable read/write theo một object

Với object có linearizable read/write, mỗi operation có thể được xem như xảy ra tại một thời điểm giữa invocation và response, tôn trọng real-time precedence.

```text
Client A:
  WRITE X=11 ----- ACK

Client B:
                        READ X -> 10
``

Nếu read bắt đầu sau write ACK và không có concurrent later write hợp lệ, đọc X=10 **vi phạm linearizability** của object này.

### Phạm vi cần chỉ rõ

- Một object hay nhiều objects?
- Single-region primary/leader hay distributed quorum?
- Transactional read hay ordinary read?
- Có stale transaction snapshot/PIT đã mở trước write không?
- Read có dùng replica/index đặc biệt không?

**Linearizable per-key** không tự cho một snapshot atomic của hai keys. Từng key có thứ tự đúng riêng nhưng việc lấy A và B ở hai thời điểm khác nhau vẫn có thể tạo một cặp giá trị không mong đợi.

## 48. Serializable transactions khác linearizability

**Serializability** của transactions hỏi liệu một lịch sử concurrent có tương đương một thứ tự tuần tự của các transactions không.

**Strict serializability** thêm ràng buộc real-time giữa các transactions không overlap (một khái niệm gần với linearizability của transaction object).

### Một ví dụ

```text
T1: transfer 100 from A to B.
T2: read A and B.
``

Một serializable outcome phải tương ứng T2 trước hoặc sau T1, không nhìn “A đã trừ nhưng B chưa cộng” theo transactional model.

### Vì sao khác read-your-writes?

RYW chỉ yêu cầu phiên thấy writes của chính mình (hoặc state newer). Nó không bảo đảm tính hợp lệ của một lịch sử concurrent transactions đa keys.

Do đó scorecard nên tách:

```text
single-key RYW
multi-key atomic visibility
serializable transaction histories
real-time read-after-commit
``

## 49. Monotonic reads và session consistency

Lịch sử:

```text
Session S:
  read booking rev11 from replica A
  reconnect / route to replica B
  read booking rev10
``

Vi phạm **monotonic reads** nếu hợp đồng áp qua reconnect trong cùng logical session, ngay cả khi S chưa ghi.

### RYW

```text
Session S:
  write booking rev12 -> ACK
  read booking rev11
``

Vi phạm **read-your-writes** nếu session guarantee yêu cầu.

### Causal consistency

Một causal session có thể mang operation time/bookmark/session token qua reads/writes để reader chờ hoặc route tới replica đủ mới. Nhưng:

- Driver session object khác web login session.
- Client/app pod mới không tự nhận context từ pod cũ.
- Token có lifecycle/scope cụ thể.
- Một read có thể timeout thay vì trả stale nếu không đủ replica freshness.

### Chọn trong ứng dụng

Nếu người dùng cập nhật profile rồi tải lại, RYW thường quan trọng. Nếu user đang lướt public catalog, eventual read có thể đủ. Không cần bắt mọi dashboard query đi qua strong-read path.

## 50. Causal consistency và thứ tự nhân quả

Một flow:

```text
Service A writes booking rev12.
Service A publishes BookingConfirmed event carrying rev12.
Service B receives event.
Service B reads booking from replica rev11.
Service B creates ShippingTask based on rev11.
``

Nếu Business B phải xử lý trạng thái dẫn đến event, B cần **causal read** ít nhất rev12, hoặc dùng event đã mang trạng thái đầy đủ được ủy quyền.

### Làm thế nào?

- Mang source revision/causal token trong event metadata.
- Dùng read mode/session/bookmark có guarantee phù hợp.
- Áp minimum revision gate và bounded wait/fallback.
- Idempotent event processing.

### Causal consistency không phải total order mọi writes

Hai writers độc lập không có quan hệ nhân quả có thể được nhìn theo thứ tự khác nhau trong phạm vi model cho phép. Đừng coi “causal” là “mọi thứ tuyến tính hóa toàn cầu”.

## 51. Eventual consistency và convergence

Trong hệ có async replicas:

```text
T0 leader has rev12, replica has rev11.
T1 leader write ACK.
T2 replica still rev11.
T3 replica catches up to rev12.
``

Nếu read API cho phép eventual data, T2 có thể là behavior hợp lệ. Nhưng ứng dụng cần hỏi:

- Freshness SLO bao nhiêu?
- Khi partition kéo dài, có stale bound không?
- Các bản xung đột được reconcile thế nào?
- Người dùng vừa ghi có được bypass cache/route mạnh hơn không?
- Nếu delete chứa security/privacy significance, stale read có được phép không?

### Eventual không bảo đảm ETA cố định

Không thể suy “eventual = chắc trong 1 giây” nếu service không cung cấp bound tương ứng. Khi lựa chọn, cần **đo distribution source-to-visible lag**, tách bình thường và fault windows.

## 52. Quorum: toán học cần nhưng chưa đủ

Với replication factor \(N\), read quorum \(R\), write quorum \(W\), điều kiện:

\[
R+W>N
\]

cho thấy giao nhau giữa read/write quorums trong một mô hình fixed replica set.

Ví dụ:

\[
N=3,\quad W=2,\quad R=2
\]

Một read quorum và một write quorum bất kỳ giao nhau tối thiểu một replica trong mô hình lý tưởng.

### Tại sao chưa đủ suy linearizability?

Còn phải xét:

- Replica được trả về có state mới nhất theo version rules?
- Concurrent conflicting writes và last-write-wins?
- Sloppy quorum/hinted handoff?
- Read repair, anti-entropy và stale tombstones?
- Topology changes/reconfiguration?
- Session routing, write timeout/unknown commit?
- Multi-DC `LOCAL_QUORUM` boundaries?

**Đọc tài liệu về exact consistency level của engine** thay vì dùng bất đẳng thức này làm bằng chứng duy nhất.

## 53. Network partition: availability theo operation

Một cụm leader-based majority:

```text
Zone A: one voter, reachable by client A
Network partition
Zones B+C: two voters, reachable by client B
```

Nếu strong write đòi majority, phía A **không thể tự cam kết majority write**. Có thể:

- Trả lỗi/timeout có kiểm soát.
- Cho phép stale read nếu API contract cho phép.
- Nhận durable pending intent nếu có authority/protocol khác được thiết kế.

### Lựa chọn cần ghi rõ

| Operation | Mong muốn khi minority | Bảo đảm |
|---|---|---|
| Catalog read | Có thể trả stale trong bound | Freshness policy |
| Confirm booking | Từ chối nếu không giữ invariant | Không oversell |
| Profile update | Tạm unavailable hoặc queue hợp lệ | RYW/durability contract |
| Payment capture | Không retry mù | Idempotency/reconciliation |

Không gọi database “CP” hoặc “AP” cho **toàn sản phẩm** rồi bỏ qua việc cùng cluster có read modes và operations khác nhau.

## 54. Scope một region khác multi-region

Một local strong read ở Region R2 chỉ nói về **state committed trong authority scope của R2**, không tự bảo đảm một write ở R1 đã replicate tới R2.

```text
R1: write rev11 -> ACK
  |
  +-- async replicate (lag) --> R2: rev10

Client failover to R2 -> local strong read rev10
``

### Các câu hỏi

- RPO khi R1 hỏng là bao nhiêu?
- R1 ACK có yêu cầu cross-region durable commit không?
- R2 có nhận causal/session context từ R1 không?
- Conflict resolution giữa hai writers active-active?
- Có regional read preference/session guarantee?
- Data sovereignty/egress và KMS keys có cho multi-region replication không?

### Không tự áp một consistency label cho mọi chế độ dịch vụ

Cùng một sản phẩm managed có thể có nhiều lựa chọn global table/multi-region consistency với semantics khác nhau. Mỗi chế độ phải được đánh giá riêng và ghi phiên bản/edition/deployment.

## 55. Chỉ mục và nhất quán có thể có ranh giới khác nhau

Một ứng dụng:

```text
Source booking write rev12 committed
  |
  +-- primary-key Get -> rev12
  +-- customer GSI Query -> rev11
  +-- search index -> rev10
  +-- cache -> rev9
``

Một kết luận tốt:

> “Core booking update đạt mức nhất quán đã cam kết trong authoritative path. Các read models qua GSI, search và cache có freshness riêng; user-facing endpoint Q2 hiện chưa giữ RYW xuyên routing.”

Không kết luận:

> “Database không nhất quán.”

Vì câu sau không chỉ rõ **lớp nào trả bản cũ, mode nào và scope nào**.

## 56. Read after write khác read from same transaction snapshot

Một transaction đọc snapshot bắt đầu ở T0; một writer ngoài transaction commit T1. Read tại T2 trong transaction cũ có thể vẫn trả value của T0 theo snapshot semantics.

```text
T0 Read transaction starts, pins snapshot rev10.
T1 Another session writes rev11 and commits.
T2 Snapshot transaction reads -> rev10.
``

Đây có thể **đúng snapshot contract**; không áp RYW assertion của một fresh read bên ngoài transaction vào đây.

### Khi thử

Ghi transaction start time/snapshot boundary/read concern. Nếu app giữ transaction mở quá lâu hoặc tái dùng snapshot không mong muốn, đó là vấn đề thiết kế connection/transaction lifecycle.

## 57. Consistency trên Graph, Search và Vector có thể khác core KV

Graph:

- Node/relationship updates có transaction semantics riêng.
- Causal bookmark có thể yêu cầu follower bắt kịp.
- Một traversal nhiều hops cần xem snapshot/transaction isolation.

Search:

- ACK ingest không tự bảo đảm query search-visible ngay.
- Refresh/PIT có thể quyết định observed version.
- Bulk operations có item-level failures.

Vector:

- Ingest document metadata và ANN index update có thể không đồng bộ.
- Có thể ANN không trả nearest exact even when fully indexed (approximation).
- Filter/tenant policy phải áp chính xác dù retrieval approximate.

**Tính đúng của query** gồm cả visibility, ranking/relevance hoặc traversal invariants, không chỉ “đã có record ở storage”.

## 58. Checkpoint và CDC là một lớp consistency riêng

Trong kiến trúc source + search projection:

```text
Source commit position C12
      |
      v
CDC connector checkpoint C10
      |
      v
Broker published C10
      |
      v
Sink applied C9
      |
      v
Search-visible C8
``

Các position có semantics khác nhau; không thể chỉ nhìn `broker_lag=0` rồi tuyên bố search đã nhìn thấy C12.

### Cần mô hình

1. Source snapshot + CDC boundary không có gap.
2. Duplicate-safe replay và ordering per entity.
3. Sink apply có revision/tombstone guard.
4. Query visibility checkpoint/freshness.
5. Recovery khi connector log token/retention hết hạn.

### Cost

Một second read model thêm một **consistency contract và runbook mới**. Nếu mục tiêu Q3 có freshness tối đa 30 giây, đội phải vận hành và đo được SLA đó.

## 59. Consistency vs availability vs latency: không chọn một chiều

Một strong read có thể **đợi quorum/follower catch-up**; data safety được giữ nhưng p99 tăng hoặc operation timeout.

```text
Weak read:
  p99 30ms, occasionally rev10

Strong/causal read:
  p99 150ms, no stale success observed
  during fault: 5% read timeouts
``

Các số chỉ minh họa; không phải benchmark của engine nào.

### Báo cáo ba kết quả riêng

| Trục | Đo thế nào |
|---|---|
| Correctness | Có stale/invalid/duplicate effect theo contract? |
| Availability | Tỷ lệ logical operations hoàn tất đúng deadline? |
| Latency/cost | p95/p99, throughput, resources và tiền vận hành |

Một thay đổi làm stale rate = 0 nhưng read timeout tăng vọt chưa phải giải pháp thành công nếu application cần phục vụ trong deadline.

## 60. Bảng đối chiếu mức nhất quán và phạm vi

| Guarantee | Điều thường đảm bảo | Điều không tự đảm bảo |
|---|---|---|
| Eventual read | Có thể trả version cũ rồi hội tụ | RYW tức thì |
| Bounded stale | Giới hạn lag theo contract | Atomic multi-key transaction |
| RYW/session | Session thấy writes của mình | Client khác thấy ngay |
| Monotonic reads | Không quay lùi trong session scope | Conflict-free concurrent writes |
| Causal | Tôn trọng causal order | Total order cho mọi independent writes |
| Linearizable key | Freshness real-time trên một object | Atomic snapshot nhiều objects |
| Snapshot transaction | Cùng snapshot cho scope giao dịch | Serializability mọi lịch sử |
| Serializable transactions | Lịch sử như một thứ tự tuần tự | Real-time order nếu không strict |
| Strict serializable | Serializable + real-time semantics | Global scope nếu transaction không phủ |

Không có hàng nào tự trả lời hết các nhu cầu. Gắn mỗi guarantee với **operations và scope thực tế** rồi mới so sánh sản phẩm.

## 61. Đường ghi ACK, read mode và failure model phải được đóng cặp

Một matrix:

| Write | Read | Kiểm chứng |
|---|---|---|
| Local ACK | Same primary read | Same-node visibility, chưa chứng minh durability |
| Majority ACK | Same causal session secondary read | Session RYW khi conditions đúng |
| Majority ACK | New session eventual replica | Có thể stale nếu không chuyển context |
| Conditional single-key write | Strong get by key | Check invariant và post-ACK visibility |
| Transaction commit | Read from async search index | Source commit khác index refresh |
| Cross-region async write | Other-region read | RPO/replication lag, no automatic global RYW |

### Crash windows

Nếu write timeout sau server commit, client có outcome unknown. Không dùng outcome ấy làm một **confirmed ACK** trong consistency checker; nhưng cũng không được retry non-idempotent command với new ID.

## 62. Tiêu chuẩn bảo mật là một phần của consistency contract

Một hệ đọc dữ liệu mới nhất nhưng trả cho **sai tenant** vẫn thất bại nghiêm trọng. Một cache trả permission “ADMIN” sau khi quyền đã bị thu hồi có thể là security violation ngay cả khi phần còn lại của app cho phép stale catalog.

### Hard gates

- Tenant isolation ở authorization, key/query/index boundaries.
- Không stale allow vượt revocation policy.
- Data deletion/TTL/consent phải propagate vào projections phù hợp.
- Audit of sensitive reads/exports.
- Encryption/KMS/backup/restore trong mọi region được phép.

**Chọn datastore và consistency mode phải dựa vào hậu quả của stale read**, không chỉ tần suất stale.

## 63. MongoDB: document aggregate, compound index và multi-document transaction

### Một model ứng viên

```javascript
db.bookings.insertOne({
  _id: "B1001",
  tenantId: "T01",
  customerId: "C007",
  propertyId: "P003",
  createdAt: ISODate("2026-11-14T09:00:00Z"),
  status: "PENDING",
  sourceRevision: 1
});

db.bookings.createIndex({
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  _id: -1
});
```

Đây là ví dụ thao tác MongoDB shell; deployment/sharding/index compatibility cần xác minh trước khi dùng thực tế.

### Đánh giá bốn trục

**Mô hình:** document phù hợp booking aggregate có nested line items nhỏ và bounded. Nếu inventory của mọi khách hàng nằm ở document khác, vẫn có cross-document invariant.

**Chỉ mục:** compound/multikey/partial/TTL/text/geo và các khả năng index khác tùy version/deployment. Index Q2 phải xem planner, sort và tenant scope.

**Giao dịch:** atomic update một document; có multi-document transactions trong topology/versions hỗ trợ, nhưng concurrency/conflicts/transaction time/commit cost cần đo.

**Nhất quán:** read preference, write concern, read concern và causal session là các cấu hình có tác động khác nhau. Majority write không tự làm arbitrary secondary eventual read thấy phiên bản mới.

### Test quyết định

- 100 concurrent inventory reservations với CAS hoặc transaction phù hợp.
- Q2 compound index explain dưới tenant lớn.
- Majority ACK rồi primary stepdown, kiểm RPO/RYW.
- Read qua secondary trong/ngoài causal session.
- Change Streams → search index freshness và replay.

### Khi chọn

Khi aggregate/document queries là chính, các index phù hợp và transactions đáp ứng invariant với chi phí chấp nhận.

### Khi phải cẩn trọng

Không biến mọi booking vào một giant tenant document; không coi transaction đa shard bằng chi phí single-document update; không dùng read replica eventual cho security-critical read chỉ vì giảm tải primary.

## 64. DynamoDB: access-pattern-first, primary key/GSI và condition writes

Một single-table concept:

```text
PK = TENANT#T01#CUSTOMER#C007
SK = BOOKING#2026-11-14T09:00:00Z#B1001

Secondary access:
  GSI_PK = BOOKING#B1001
  GSI_SK = TENANT#T01
``

Đây chỉ là **minh họa mô hình**, không phải khuyến nghị bỏ tenant authorization hoặc chọn GSI cho mọi lookup.

### Bốn trục

**Mô hình:** key-value/document items, query tốt nếu biết partition key/sort key; phải thiết kế access patterns và giới hạn hot partitions.

**Chỉ mục:** GSI/LSI có giới hạn và consistency semantics khác base table. GSI được cập nhật bất đồng bộ; strong read trên base table/LSI không làm GSI strong.

**Giao dịch:** conditional writes, transactional APIs cho tập items trong cùng account/region và phạm vi/giới hạn được hỗ trợ. `BatchWriteItem` **không phải transaction** và có thể trả unprocessed items.

**Nhất quán:** eventual/strong reads trong phạm vi hỗ trợ. Cross-region/global tables có mode replication/consistency cụ thể; không tự suy transaction/strong consistency toàn cầu.

### Test quyết định

- Tenant/customer query Q2 qua partition key.
- Conditional decrement inventory, xác minh không oversell.
- Transaction multi-day booking với contention/cost.
- GSI lag ngay sau write, giải pháp RYW của API.
- Throttling/hot partition khi một tenant rất lớn.
- Region failover với exact Global Tables mode.

### Khi chọn

Khi key/query patterns rõ, serverless/managed operations phù hợp và application sẵn sàng thiết kế secondary read models/idempotency.

### Khi phải cẩn trọng

Thay một query có filters tự do bằng `Scan` toàn bảng thường không bền về cost/performance. Không dựa vào GSI eventual lookup để enforce global uniqueness bằng read-then-insert.

## 65. Cassandra/ScyllaDB: wide-column và consistency per operation

Một query table:

```sql
CREATE TABLE bookings_by_customer (
  tenant_id text,
  customer_id text,
  created_at timestamp,
  booking_id text,
  status text,
  PRIMARY KEY (
    (tenant_id, customer_id),
    created_at, booking_id
  )
) WITH CLUSTERING ORDER BY (
  created_at DESC,
  booking_id DESC
);
```

### Bốn trục

**Mô hình:** query-specific denormalized tables, partition/clustering keys. Cần xác minh size/hotness, duplicate data maintenance và query ordering.

**Chỉ mục:** tùy engine/version có secondary index và kiểu storage-attached indexing khác nhau; không mặc định thay được partition-aware query model. Query explain/traces thực tế quan trọng.

**Giao dịch:** mutations/atomic batch semantics phụ thuộc partition scope và API; LWT/conditional operations dùng protocol riêng với chi phí contention. Không mặc định có arbitrary cross-partition serializable transaction giống SQL.

**Nhất quán:** read/write CL như `ONE`, `LOCAL_QUORUM` theo topology. Đồng thuận giao quorum không tự giải mọi concurrent-write/timestamp conflict.

### Test quyết định

- Q2 với 10, 10.000 và 1 triệu bookings/customer.
- Một hot partition và 99th percentile latency.
- Replica lag, one-AZ loss và CL theo DC.
- Conditional inventory update và multi-day reservation workflow.
- Schema evolution/delete/tombstones/repair khi CDC/index tables lệch.

### Khi chọn

Workload lớn, write-heavy, partition-aware query rõ, có khả năng vận hành nhiều read models và consistency policies theo từng operation.

### Khi phải cẩn trọng

Không dùng `ALLOW FILTERING` hay multi-partition batch tùy tiện để bù cho data model không khớp queries; không coi RF=3 là ba independent fault domains nếu placement sai.

## 66. Redis: state theo key, atomic command và giới hạn cross-slot

Một key:

```text
BOOKING:T01:B1001 -> serialized booking state
INVENTORY:P003:2026-12-01 -> integer remaining
``

### Bốn trục

**Mô hình:** rất tốt cho cache, short-lived state, counters, rate limits, sessions, streams theo workload.

**Chỉ mục:** key access trực tiếp; truy vấn field/search nâng cao phụ thuộc modules/products/capability, không mặc định từ Redis core.

**Giao dịch:** single commands atomic theo semantics server; `WATCH`/`MULTI`/`EXEC` optimistic transaction và scripts/Functions có constraints. Redis Cluster thường yêu cầu các keys trong một multi-key operation/script ở cùng hash slot khi được hỗ trợ; không tự có transaction cross-shard toàn cục.

**Nhất quán:** primary-replica replication thường async; failover/persistence có durability trade-offs. `WAIT` có thể đợi replica acknowledgment nhưng không biến topology thành global consensus transaction.

### Test quyết định

- Single-key atomic inventory CAS/script với 100 concurrent attempts.
- Session cache expiry, failover/RPO.
- Thao tác nhiều dates rơi vào different hash slots.
- Memory budget/eviction ảnh hưởng tính đúng.
- Cache stampede khi một AZ mất.

### Khi chọn

Phù hợp cho cache/ephemeral state hoặc authoritative key-level workloads có durability/HA constraints được hiểu rõ.

### Khi phải cẩn trọng

Nếu booking inventory là nguồn tài chính/nghiệp vụ quan trọng, cần xác minh Redis topology và persistence có đáp ứng RPO/invariants. Không dùng cache TTL/lock mơ hồ làm điều kiện duy nhất ngăn oversell.

## 67. Elasticsearch/OpenSearch: search index và freshness

Một projection:

```json
{
  "bookingId": "B1001",
  "tenantId": "T01",
  "propertyId": "P003",
  "city": "Da Nang",
  "status": "CONFIRMED",
  "sourceRevision": 12
}
```

### Bốn trục

**Mô hình:** search-oriented documents, shard/index/alias mappings.

**Chỉ mục:** inverted, term, numeric, geo, vector (capabilities tùy version) phục vụ search/filter/aggregation; refresh/reindex/merge cost.

**Giao dịch:** bulk API cho status từng item, optimistic concurrency/version checks; không coi một bulk request là arbitrary multi-document ACID transaction.

**Nhất quán:** index ACK, realtime document GET và search visibility có semantics khác nhau; PIT cố định search snapshot có thể chủ ý đọc trạng thái cũ.

### Test quyết định

- Search Q3 full-text+geo+facets, query relevance và p99.
- Refresh lag sau source update/delete.
- Source-to-visible CDC lag và replay khi connector crash.
- Search under shard relocation/AZ loss.
- Tenant filter/security, snapshot/index alias permissions.

### Khi chọn

Rất phù hợp làm search read model với source authority khác cho bookings/inventory/payment.

### Khi phải cẩn trọng

Không dùng search index query “còn phòng không?” làm **authority duy nhất** cho một reservation invariant nếu dữ liệu có thể stale.

## 68. Neo4j/property graph: traversal và transaction boundary

Một query:

```cypher
MATCH (c:Customer {id:$customerId})-[:MADE]->(b:Booking)
      -[:FOR]->(p:Property)
WHERE p.city = $city
RETURN b,p
LIMIT 20
```

### Bốn trục

**Mô hình:** nodes, relationships, properties; identity và graph topology rõ.

**Chỉ mục:** node/relationship property indexing có thể tăng khả năng tìm điểm bắt đầu, nhưng traversal cost phụ thuộc degree/path depth.

**Giao dịch:** engine hỗ trợ transaction trong phạm vi/version/deployment cụ thể; không suy những graph layers kết nối data stores khác nhau có cùng atomicity.

**Nhất quán:** clustered read routing và causal bookmarks/transaction snapshot cần xem theo driver/API. Một follower read không mang bookmark có thể không đạt causal boundary mong muốn.

### Test quyết định

- Traversal p99 với high-degree nodes.
- Relationship uniqueness/dedup.
- Transaction commit nhiều nodes/edges và failover.
- Bookmarks khi mở session mới.
- Graph export/anonymization và edge security.

### Khi chọn

Khi graph traversal/inference theo relationships là core product value.

### Khi phải cẩn trọng

Không đưa mọi booking lookup/analytics vào graph chỉ vì có Customer→Booking→Property edges nếu đường tra cứu đơn giản hơn bằng partition/index khác.

## 69. Azure Cosmos DB: API, partition và consistency choice

Một ứng viên managed multi-model/API:

### Bốn trục

**Mô hình:** tùy API như NoSQL document, MongoDB-compatible, Cassandra-compatible, Gremlin...; capabilities và constraints không nhất thiết giống nhau.

**Chỉ mục:** indexing policy và query features theo API/version; xác minh composite/geo/vector và chi phí RU/throughput theo đúng mode.

**Giao dịch:** nhiều transactional batch/stored procedure semantics được ràng buộc theo **logical partition key** trong API NoSQL; không tự suy arbitrary cross-partition ACID cho mọi API/mode.

**Nhất quán:** các consistency levels và session tokens với phạm vi được provider công bố. Session token cần được chuyển qua SDK clients/pods khi application contract yêu cầu RYW xuyên requests.

### Test quyết định

- Q1/Q2 theo partition key và query RU.
- Hot partition và multi-tenant fairness.
- Batch/reservation cần bao nhiêu logical partitions?
- SDK session-token propagation qua two app pods.
- Regional failover, RPO và chosen consistency mode.

### Khi chọn

Khi managed regional/global deployment và API capabilities đáp ứng queries/invariants với cost/throughput được đo.

### Khi phải cẩn trọng

Đừng coi tên “Cosmos DB” là một đơn nhất về giao dịch/chỉ mục trong tất cả APIs.

## 70. Couchbase: KV, SQL++ index và transactions

### Bốn trục

**Mô hình:** JSON documents và KV access, có SQL++ query cho truy vấn theo fields/join tùy deployment.

**Chỉ mục:** GSI/search/geo/vector capabilities thay đổi theo phiên bản/sản phẩm; index scanning có consistency semantics khác KV GET.

**Giao dịch:** SDK/server hỗ trợ distributed ACID transaction ở những phiên bản/phạm vi nhất định, nhưng không áp mọi thao tác ở search service hoặc external systems như một transaction duy nhất.

**Nhất quán:** KV reads, SQL++ scan consistency như request_plus/at_plus theo SDK, mutation token/causal context cần kiểm tra.

### Test quyết định

- KV Q1 và SQL++ Q2 performance.
- Secondary index freshness sau update.
- Multi-document transaction under conflicts/failover.
- Transaction impact lên read/write SLO.

### Khi phải cẩn trọng

Đừng dùng KV GET RYW PASS để chứng minh SQL++ query qua secondary index luôn thấy cùng write tức thì.

## 71. Bigtable/HBase và row-level atomicity

Các wide-column family stores khác có tối ưu theo row key/range scan.

### Cần phân biệt

- Single-row atomic mutation/check-and-mutate trong phạm vi API.
- Row key ordering/hotspot.
- Secondary query thông qua application-built tables/indexes hoặc extension.
- Cross-row transaction limitations.
- Multi-cluster replication consistency và failover semantics.

Ví dụ hai rows giữ inventory của hai ngày **không tự trở thành transaction** chỉ vì cả hai nằm trong cùng table. Chọn row key/aggregate boundary theo invariant.

### Quy trình thử

- Single-row conditional update.
- Cross-row partial failure.
- Row-key hotspot under peak.
- Read-after-write khi đổi cluster/region.
- Index table maintenance và recovery.

## 72. Không gộp mọi sản phẩm vào một bảng PASS/FAIL tuyệt đối

Một bảng như:

| Sản phẩm | ACID? | Strong? | Index? |
|---|---|---|---|
| X | Yes | Yes | Yes |

là quá thô. Với mỗi ô “Yes”, cần bổ sung:

```text
API:
  exact method/operation
Scope:
  key/partition/shard/region
Version:
  engine + edition + driver
Constraints:
  size/count/time/cross-region
Failure model:
  node/AZ/region partition
Evidence:
  official semantics + measured test
```

### Một capability card đầy đủ

```yaml
candidate:
  engine: "candidate-A"
  version: "pinned"
  deployment: "regional-3-zone"
  capability: "conditional decrement"
  scope: "one inventory key"
  isolation: "documented by engine"
  read_path: "authoritative API"
  consistency: "specified setting"
  guarantees:
    - "no negative count under concurrent test"
  limitations:
    - "multi-day booking crosses keys"
  evidence:
    - "load-test-run-17"
    - "failure-drill-04"
```

Không ghi “guarantees” như một sự thật chung nếu chỉ một bài test đã PASS; kết quả test là **bằng chứng hữu hạn** của cấu hình và phạm vi cụ thể.

## 73. Đánh giá engine kết hợp với thiết kế ứng dụng

Hai ứng viên:

**Candidate A**

```text
MongoDB document authority
  + change stream / outbox
  + Elasticsearch search projection
  + Redis cache
``

**Candidate B**

```text
DynamoDB key/value authority
  + DynamoDB Streams/event bridge
  + search service
  + optional DAX/cache
``

Cả hai là **hệ thống nhiều thành phần**, không phải một engine đơn giản.

### So theo cả hệ

- Source write atomicity/invariants.
- Search query quality và freshness.
- CDC/update/delete propagation.
- Cache RYW/version gating.
- Backups/restore/migration/rollback.
- Authz, KMS, tenant isolation.
- Total operational cost/on-call complexity.

### Một engine “đa mô hình” cũng không miễn phí consistency

Nếu search index nội bộ cập nhật async từ core storage, vẫn có read-after-write boundary. Nếu graph traversal và KV read dùng execution paths khác, vẫn cần test. “One vendor” không đồng nghĩa “one atomic operation across all capabilities”.

## 74. Từ access pattern đến một ma trận giải pháp

Quay lại dịch vụ đặt chỗ:

| Access pattern / invariant | Authority đề xuất để đánh giá | Read model/index có thể dùng | Cần kiểm thử |
|---|---|---|---|
| Q1 Get booking | Document/key-value/wide-column by ID | Primary key | Tenant scope, p99, RYW |
| Q2 List by customer | Document compound index hoặc query table | `(tenant,customer,date,id)` | Sort/paging, index freshness |
| Q3 Search property | Property authority | Full-text/geo/search projection | Relevance, filter, CDC lag |
| Q4 Reserve unit | Inventory authority theo key/aggregate | Không dựa vào search index | Concurrent CAS/transaction |
| Q5 Payment status | Durable payment workflow/ledger | Optional read projection | No duplicate capture, unknown outcome |
| Q6 Analytics | Immutable events/batch snapshots | OLAP/aggregates | Point-in-time reporting |
| RYW after payment | Booking/payment authoritative state | Causal/strong read hoặc version gate | Cross-session and failover |

### Đừng chọn model chỉ từ Q1

Nếu phần lớn request counts là catalog GET nhưng rủi ro pháp lý lớn nhất nằm ở payment, **critical invariants vẫn là hard gate**. Tần suất một thao tác thấp không có nghĩa độ quan trọng thấp.

## 75. Gắn mỗi yêu cầu với boundary cụ thể

Một bảng:

| Yêu cầu | Boundary cần bảo đảm | Bằng chứng |
|---|---|---|
| Booking status update | Single booking entity | Atomic conditional update |
| Two-night reservation | Two inventory keys + booking state | Transaction/workflow invariant test |
| Unique external reference | Tenant-wide identity | Unique claim/constraint under concurrency |
| Booking list RYW | Session/user + read model | After-ACK read across app pods |
| Search freshness 30s | Source → CDC → index → API | Source-to-visible lag histogram |
| No lost confirmed payment | DB + payment provider workflow | Crash/timeout/reconcile histories |
| Strong local read | Base table/API/region | Consistency mode test |
| Region DR RPO | Cross-region replication/restore | Failover/restore data verification |

### Nếu boundary trải nhiều systems

Không thể “mua thêm một transaction” trong engine authority mà tự làm payment provider và search engine cùng commit. Cần architecture-level protocol và test ở **workflow boundary**.

## 76. Chấm điểm không được phép bù điểm cho hard-gate failure

Một phương pháp:

1. Loại hoặc yêu cầu sửa thiết kế nếu **hard gate không đáp ứng**.
2. Với các ứng viên còn hợp lệ, đo preferences bằng thang 0–5.
3. Chấm mức độ chắc chắn của evidence.
4. Tổng hợp weighted score.
5. Review các giả định rủi ro, chi phí và operational readiness.

### Công thức minh họa

Với \(w_i\ge 0\), \(s_i\in[0,5]\):

\[
S=\frac{\sum_{i=1}^{n}w_i s_i}{\sum_{i=1}^{n}w_i}
\]

**Không tính điểm cho criterion chưa có evidence** rồi mặc định là đạt. Đánh dấu thiếu dữ liệu, lên kế hoạch benchmark.

### Ví dụ giả định

| Tiêu chí preference | Trọng số | A: Document+Search | B: KV+Search |
|---|---:|---:|---:|
| Q1/Q2 p99 (theo benchmark) | 30 | 4 | 5 |
| Q3 search relevance | 15 | 4 | 4 |
| Tốc độ write ở peak | 20 | 4 | 4 |
| Operational complexity | 20 | 3 | 4 |
| Total cost | 15 | 3 | 4 |

Tổng điểm:

\[
S_A=(30\cdot4+15\cdot4+20\cdot4+20\cdot3+15\cdot3)/100=3.65
\]
\[
S_B=(30\cdot5+15\cdot4+20\cdot4+20\cdot4+15\cdot4)/100=4.30
\]

Đây là số **giả định**, chỉ minh họa phép tính; không phải khuyến nghị rằng B tốt hơn trong thực tế. Nếu B không đáp ứng một hard gate như multi-day reservation invariant, **B không được chọn** trước khi có thiết kế khắc phục được chứng minh.

### Tránh “ngụy chính xác”

Điểm 4.30 không có nghĩa xác suất thành công 86%. Thang điểm là công cụ trao đổi, chịu ảnh hưởng chủ quan, quality của test và trọng số. Nên ghi confidence/evidence bên cạnh mỗi score.

## 77. Java 17: dựng catalog access patterns

Một cách cấu trúc hóa requirements:

```java
import java.time.Duration;
import java.util.List;

enum AccessKind {
    POINT_LOOKUP,
    ORDERED_RANGE,
    FILTER_SEARCH,
    GRAPH_TRAVERSAL,
    AGGREGATION,
    CONDITIONAL_UPDATE
}

enum RequiredConsistency {
    EVENTUAL_OK,
    BOUNDED_STALENESS,
    READ_YOUR_WRITES,
    LINEARIZABLE_KEY,
    TRANSACTIONAL_MULTI_KEY
}

record AccessPattern(
    String id,
    AccessKind kind,
    List<String> keyPredicates,
    List<String> sortFields,
    Duration p99Deadline,
    RequiredConsistency consistency,
    boolean hardGate
) {}

public final class AccessPatternCatalog {
    public static List<AccessPattern> example() {
        return List.of(
            new AccessPattern(
                "Q1", AccessKind.POINT_LOOKUP,
                List.of("tenantId", "bookingId"),
                List.of(),
                Duration.ofMillis(80),
                RequiredConsistency.READ_YOUR_WRITES,
                false
            ),
            new AccessPattern(
                "Q4", AccessKind.CONDITIONAL_UPDATE,
                List.of("propertyId", "date"),
                List.of(),
                Duration.ofMillis(200),
                RequiredConsistency.LINEARIZABLE_KEY,
                true
            )
        );
    }
}
```

### Ý nghĩa

Code không chọn được database thay con người. Nó buộc requirement viết ra **key predicates, sort, deadline và consistency scope** thay vì một câu “Q4 cần dữ liệu chuẩn”.

### Chưa đủ để chọn sản phẩm

Cần bổ sung workload distribution, bytes, tenant skew, topology, outage model, concurrency, cost, privacy và evidence thực nghiệm. Enum `LINEARIZABLE_KEY` chỉ là target contract; nó không tự khiến engine thật đáp ứng.

## 78. Java 17: hard-gate-first scorecard

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

record Criterion(
    String id,
    double weight,
    boolean hardGate
) {}

record Evidence(
    boolean passes,
    double score,
    String reference
) {}

record Candidate(
    String name,
    Map<String, Evidence> evidence
) {}

record Evaluation(
    String candidate,
    boolean eligible,
    double weightedScore,
    List<String> blockers
) {}

public final class CandidateEvaluator {
    public static Evaluation evaluate(
            Candidate candidate,
            List<Criterion> criteria) {
        var blockers = new ArrayList<String>();
        double weighted = 0;
        double totalWeight = 0;

        for (Criterion criterion : criteria) {
            Evidence e = candidate.evidence().get(criterion.id());
            if (e == null || e.reference() == null
                    || e.reference().isBlank()) {
                blockers.add("MISSING_EVIDENCE:" + criterion.id());
                continue;
            }

            if (criterion.hardGate()) {
                if (!e.passes()) {
                    blockers.add("HARD_GATE_FAILED:"
                        + criterion.id());
                }
            } else {
                if (!Double.isFinite(e.score())
                        || e.score() < 0 || e.score() > 5
                        || criterion.weight() < 0) {
                    blockers.add("INVALID_SCORE:"
                        + criterion.id());
                    continue;
                }
                weighted += criterion.weight() * e.score();
                totalWeight += criterion.weight();
            }
        }

        double score = totalWeight > 0
            ? weighted / totalWeight
            : Double.NaN;

        return new Evaluation(
            candidate.name(),
            blockers.isEmpty() && totalWeight > 0,
            score,
            List.copyOf(blockers)
        );
    }
}
```

### Hạn chế của ví dụ

- Evidence string chỉ là reference; production phải kiểm nguồn, tuổi dữ liệu, reproducibility và test coverage.
- Đoạn code không ngăn một người gán `passes=true` khi chưa kiểm thật.
- Nếu tiêu chí preference thiếu, candidate bị giữ lại để điều tra thay vì âm thầm cho điểm 0.
- Score vẫn có thể mang bias vì weights/scales chưa được chuẩn hóa qua hội đồng review.
- Một benchmark PASS không bảo đảm dưới tất cả future workloads/failures.

## 79. TCO: không chỉ giá lưu mỗi GB

Chi phí tổng thể:

```text
TCO =
  database compute / throughput
  + primary storage
  + index storage
  + replicas / multi-region
  + network egress
  + backups / PITR / restore drills
  + event brokers / CDC
  + cache / search / analytics systems
  + engineering operations / on-call
  + incident and migration risk
``

### Những khoản dễ bị bỏ sót

- GSI/index writes cùng data.
- Queries scan nhiều rows/read units.
- Geo/search/vector index rebuild.
- Replication traffic và storage ở region dự phòng.
- Repair/rebalance sau AZ outage.
- Backup snapshots và cross-account encryption keys.
- Data migration/dual run trong cutover.
- Multi-shard transaction conflicts/retries.

Một engine có giá requests thấp nhưng cần thêm ba pipelines để đáp ứng index/consistency có thể đắt hơn giải pháp ban đầu.

## 80. Operational readiness là một tiêu chí kiến trúc

Một lựa chọn phù hợp về query nhưng đội không thể vận hành an toàn thì chưa phù hợp.

### Đánh giá

- Provisioning/IaC và schema/index migration.
- Backup/PITR, restore test, key recovery.
- Replication lag/CDC visibility monitoring.
- AZ/region failover và RTO/RPO.
- Hot shard detection, compaction/index rebuild.
- Permission/IAM/KMS/tenant isolation.
- On-call runbooks và vendor support.
- Driver/SDK integration Java, observability, connection pooling.

### Managed không có nghĩa “không cần vận hành”

Provider có thể quản lý nodes và storage, nhưng ứng dụng vẫn chịu trách nhiệm **key design, throughput skew, query modes, invariants, idempotency, access policies và recovery validation**.

## 81. Data governance và compliance có thể loại một ứng viên

Hard gates bổ sung:

- Allowed region/data residency.
- Encryption and customer-managed keys nếu bắt buộc.
- Audit trails và least-privilege operations.
- Retention/deletion/backup policy.
- Export/import path bảo vệ PII.
- Data lineage của secondary indexes, CDC và search projections.
- DR capability và cross-region failover constraints.

### Ví dụ

Một search projection sao chép tên và địa chỉ của khách hàng sang region ngoài policy. Dù Q3 p99 rất tốt, thiết kế này không đạt hard gate. Giải pháp có thể là thay projection schema/region/permissions hoặc loại architecture.

### Không suy dữ liệu “đã hash” thì hết nhạy cảm

Pseudonymized IDs và embeddings có thể bị liên kết hoặc tái định danh. Privacy requirements phải áp lên **mọi bản sao**, không chỉ primary store.

## 82. Portability và exit strategy

Một engine có proprietary query DSL, index semantics và transaction API có thể giúp ra mắt nhanh nhưng tăng effort khi đổi provider.

### Tại bước đánh giá

- Export có bảo toàn types, null/missing, TTL, timestamps không?
- Có SDK Java ổn định và abstraction boundary không?
- Business invariants nằm trong application domain model hay bị chôn trong vendor script?
- Có thể dựng lại search/read models từ source events không?
- Change streams/PITR token có thể hỗ trợ migration online?
- Có kế hoạch rollback nếu cutover thất bại?

**Portability không nhất thiết quan trọng hơn correctness/performance**, nhưng phải được cân nhắc như chi phí và rủi ro dài hạn.

## 83. Đo benchmark theo access pattern, không theo một QPS tổng

Một benchmark cần các nhóm:

```text
Q1: get booking by primary key
Q2: list booking by customer, newest 20
Q3: search city/date/price/amenities
Q4: concurrent reserve, same inventory key
Q5: payment status read after ACK/failover
Q6: monthly aggregate
``

### Thu thập

| Metric | Vì sao quan trọng |
|---|---|
| Logical throughput/s | User workflow capacity |
| p50/p95/p99 latency | Tail latency |
| Error/throttle/timeout | Availability |
| Rows/index entries scanned | Query efficiency |
| Storage and index bytes | Cost |
| Write amplification | Cost under updates |
| Retry/transaction abort ratio | Contention |
| Hot key/partition load | Skew |
| Source-to-visible lag | Projection freshness |
| Correctness violations | Hard-gate failure |
| Resource saturation | N−1/peak headroom |

### Đừng benchmark chỉ trên cold empty database

Với realistic dataset:

- 100 tenants nhỏ và 1 tenant lớn.
- Document sizes p50/p99.
- Deletes/tombstones/TTL churn.
- Different query selectivity/cardinality.
- Concurrent readers/writers.
- Index build/compaction pressure.
- Cross-AZ latency/topology.

Data phải synthetic hoặc đã được phép sử dụng; không tải production PII sang laptop để benchmark.

## 84. Open-loop và closed-loop load generation

**Closed-loop:** mỗi virtual user gửi request mới sau khi request trước hoàn tất. Khi DB chậm, offered load tự giảm.

**Open-loop:** generator giữ arrival rate theo kế hoạch, dễ thấy queuing/capacity collapse nhưng cần safety cap.

### Báo cáo cả hai

```text
Offered requests/s
Completed correct requests/s
Rejected/throttled requests/s
Timeouts and retries
Queue wait and driver pool wait
Per-operation p95/p99
```

Một ứng viên báo throughput cao vì generator đã giảm tốc và bỏ qua long timeouts có thể tạo **coordinated omission** trong latency measurement. Benchmark phải minh bạch methodology.

## 85. Kiểm tra failure model trước khi chốt

Một candidate có thể pass healthy-state benchmark nhưng fail khi mất AZ:

```text
3 zones, each holds app + replica.
Zone A lost.
Primary elected in B.
Search index/CDC leader unavailable.
App C connection pool keeps stale route.
``

### Game-day questions

1. Majority/quorum còn theo placement?
2. Surviving zones có N−1 capacity?
3. Client reconnect/discovery trong bao lâu?
4. Write ACKs còn sau leader failover?
5. RYW/causal/strong reads từ new route có giữ không?
6. CDN/cache/index stale trong bao lâu?
7. CDC resume từ checkpoint có mất gap không?
8. Backup/KMS/restore path có dùng được ở region dự phòng?

Khi business hứa 99.9% availability cho critical writes, cần đo dưới **những fault scenarios liên quan**, không suy từ replica count.

## 86. Risk register: giả định nào có thể phá kết luận?

| Giả định | Rủi ro nếu sai | Cách kiểm chứng |
|---|---|---|
| GSI freshness đủ nhanh | User không thấy booking vừa tạo | Source-to-GSI latency test |
| Transaction support đúng phạm vi | Partial inventory updates | Multi-key failure experiment |
| Partition key phân bố đều | Hot partition overload | Synthetic skew benchmark |
| Quorum survives AZ loss | No writes under incident | Placement/fault drill |
| Token portable across pods | Lost RYW after reconnect | Session switch test |
| Event replay idempotent | Duplicate state/payments | Crash after sink commit |
| Index rebuild online | Availability degradation | Shadow rebuild rehearsal |
| Multi-region failover RPO acceptable | Lost ACKed writes | Recovery reconciliation |
| Backups decryptable | DR blocked | Restore with standby identity |
| Tenant index filter enforced | Cross-tenant data leak | Adversarial authz tests |

Mỗi risk nên có **owner, likelihood/impact, mitigation và evidence date**. Không ghi “vấn đề có thể có” mà không có người chịu trách nhiệm.

## 87. Java 17: concurrent reservation invariant probe

Một phép thử trọng tâm trước khi chọn database làm **inventory authority**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

interface InventoryAuthority {
    // Must atomically reject a reservation when no stock remains,
    // and apply a stable requestId with idempotent semantics.
    boolean tryReserve(
        String inventoryKey,
        String requestId
    ) throws Exception;

    // Authoritative reads, not an eventually consistent cache.
    int remaining(String inventoryKey) throws Exception;
    long confirmedReservations(String inventoryKey)
        throws Exception;
}

public final class InventoryInvariantProbe {
    public record Result(
        int acknowledgedSuccesses,
        int unknownOutcomes,
        int remainingUnits,
        long confirmedReservations
    ) {}

    public static Result run(
        InventoryAuthority authority,
        String dedicatedSyntheticKey
    ) throws Exception {
        // The test fixture must begin with exactly one available unit.
        var pool = Executors.newFixedThreadPool(16);
        var start = new CountDownLatch(1);
        List<Future<Boolean>> futures = new ArrayList<>();
        int successes = 0;
        int unknown = 0;

        try {
            for (int i = 0; i < 100; i++) {
                String requestId = UUID.randomUUID().toString();
                futures.add(pool.submit(() -> {
                    start.await();
                    return authority.tryReserve(
                        dedicatedSyntheticKey, requestId
                    );
                }));
            }
            start.countDown();

            for (Future<Boolean> future : futures) {
                try {
                    if (future.get(30, TimeUnit.SECONDS)) {
                        successes++;
                    }
                } catch (java.util.concurrent.ExecutionException
                         | java.util.concurrent.TimeoutException ex) {
                    // A write may have committed despite a timeout.
                    unknown++;
                }
            }
        } finally {
            pool.shutdownNow();
        }

        if (unknown != 0) {
            throw new IllegalStateException(
                "Inconclusive: reconcile unknown outcomes first"
            );
        }

        int remaining =
            authority.remaining(dedicatedSyntheticKey);
        long confirmed =
            authority.confirmedReservations(
                dedicatedSyntheticKey
            );

        if (successes > 1 || confirmed > 1
                || remaining < 0
                || remaining + confirmed != 1) {
            throw new AssertionError(
                "Reservation invariant violated"
            );
        }
        return new Result(
            successes, unknown, remaining, confirmed
        );
    }
}
```

### Ý nghĩa của ví dụ

- Tất cả writes bắt đầu gần nhau sau `CountDownLatch`, tăng khả năng lộ race.
- Stable request IDs giúp adapter xây idempotent calls.
- Kết quả cuối được đọc từ **authoritative state**, không phải cache.
- Unknown outcomes không bị gán thành definite failures.
- Nếu confirmedReservations phản ánh durable booking ledger, phép thử đối chiếu state với business effect.

### Giới hạn cần lưu ý

- Code là **minh họa**, không phải production-ready chaos runner.
- Cancellation hoặc `shutdownNow` không rollback remote writes; nếu có unknown outcome phải đợi in-flight calls ổn định/reconcile trước khi chạy lại.
- Test fixture phải được tạo và dọn riêng; không dùng inventory thật.
- Mô hình một đơn vị/một ngày không chứng minh transaction nhiều ngày.
- Một `PASS` không chứng minh mọi interleavings hoặc bảo đảm của mọi deployments.
- Timeout/interrupt cần error classification và evidence recorder phù hợp ở test harness thực.

## 88. Java: test read-after-write trên đường thực sự sử dụng

```java
record BookingWriteAck(
    String bookingId,
    long authoritativeRevision,
    String causalToken
) {}

record BookingRead(
    String bookingId,
    long observedRevision,
    String status
) {}

interface BookingServiceAdapter {
    BookingWriteAck confirm(
        String syntheticBookingId,
        String idempotencyKey
    ) throws Exception;

    // May route to another app pod/cache/replica.
    BookingRead readAfterSessionSwitch(
        String bookingId,
        String causalToken
    ) throws Exception;
}

public final class BookingReadYourWritesProbe {
    public static void assertReadYourWrites(
            BookingServiceAdapter service,
            String dedicatedSyntheticBookingId,
            String stableRequestId) throws Exception {

        BookingWriteAck ack = service.confirm(
            dedicatedSyntheticBookingId, stableRequestId
        );

        BookingRead read = service.readAfterSessionSwitch(
            dedicatedSyntheticBookingId,
            ack.causalToken()
        );

        if (read == null
                || read.observedRevision()
                    < ack.authoritativeRevision()) {
            throw new AssertionError(
                "Observed stale booking after acknowledged write"
            );
        }
    }
}
```

### Điều kiện đúng để dùng

- `authoritativeRevision` phải là một revision có thứ tự đáng tin.
- Adapter phải đợi write ACK trước khi gọi read.
- Nếu read session mới không hỗ trợ token portable, test cần dùng ứng dụng-level minimum revision protocol hoặc ghi “unsupported”.
- Nếu concurrent writer hợp lệ tạo revision cao hơn, oracle chỉ kiểm min revision, sau đó còn phải kiểm invariant của state.
- Read timeout phải báo availability failure/unknown theo contract, không được convert thành revision `-1` rồi kết luận stale mà không phân loại.

### Vì sao phải test qua app API?

Một MongoDB/DynamoDB direct read có thể PASS, nhưng cache/search ở dịch vụ đặt booking vẫn có thể trả phiên bản cũ. **User-facing guarantee cần end-to-end path**, không chỉ storage driver.

## 89. Java: giao diện kiểm chứng query không phụ thuộc engine

Một benchmark suite có thể tổ chức:

```java
import java.time.Duration;
import java.util.List;

record Page<T>(
    List<T> values,
    String nextPageToken
) {}

record BookingSummary(
    String bookingId,
    String tenantId,
    String customerId,
    long createdAtEpochMillis,
    String status,
    long sourceRevision
) {}

interface BookingQueryAdapter {
    BookingSummary getById(
        String verifiedTenantId,
        String bookingId
    ) throws Exception;

    Page<BookingSummary> listByCustomer(
        String verifiedTenantId,
        String customerId,
        int pageSize,
        String token
    ) throws Exception;

    // A real test also records which index/plan/partition was used.
}

public final class BookingQueryContract {
    public static void assertNewestFirst(
            Page<BookingSummary> page) {
        long previous = Long.MAX_VALUE;
        for (BookingSummary item : page.values()) {
            if (item.createdAtEpochMillis() > previous) {
                throw new AssertionError("Sort order violated");
            }
            previous = item.createdAtEpochMillis();
        }
    }
}
```

### Cần thêm oracle ngoài code

- Không có duplicate/missing khi duyệt toàn snapshot.
- Deterministic tie-breaker khi cùng timestamp.
- Tenant scope và authz.
- Read freshness sau write.
- Query p99, index entries scanned và cost.
- Page token expiry/route changes.

Đoạn code mới chỉ kiểm **thứ tự timestamp giảm**, chưa phân biệt records có timestamp bằng nhau; test đầy đủ cần tuple sort `(createdAt,bookingId)` và snapshot contract.

## 90. Case study A: document model nhanh nhưng tồn kho đa ngày khó

### Bối cảnh

Booking document rất tiện:

```text
Booking B1001 holds three nights.
One document update atomically moves status PENDING -> CONFIRMED.
``

Nhưng Availability của mỗi ngày là record riêng:

```text
Day 1 stock = 1
Day 2 stock = 1
Day 3 stock = 1
``

Hai clients cùng đặt ba đêm; một implementation dùng ba separate decrements rồi create booking.

### Vấn đề

Một worker crash sau decrement day1/day2 nhưng trước day3. Hai ngày bị hold, không có booking hợp lệ. Cùng lúc client khác có thể đặt ở day3. **Atomic update một booking document** không giúp giữ invariant toàn bộ calendar.

### Cần đánh giá

1. Multi-document transaction có đáp ứng latency/throughput/limits không?
2. Có thể mô hình inventory reservation per property-calendar aggregate không?
3. Có thể dùng reservation hold/escrow với compensation không?
4. Nếu source multi-shard, transaction failover behavior ra sao?

### Verdict

Document DB vẫn có thể phù hợp, nhưng **phải chứng minh inventory protocol**, không chọn chỉ vì Q1/Q2 dễ.

## 91. Case study B: wide-column mô hình chuẩn Q2 nhưng Q3 quá linh hoạt

### Bối cảnh

Đội có bảng:

```text
bookings_by_customer(tenantId, customerId, createdAt)
``

Q2 rất nhanh, nhưng product mới yêu cầu:

```text
Find properties within 5km,
including amenity X and excluding Y,
sorted by dynamic relevance and price.
``

### Vấn đề

Mô hình wide-column partition-aware cho bookings không tự hỗ trợ truy vấn geo/full-text/dynamic filters với cùng hiệu quả.

### Các hướng

- Dùng search projection chuyên dụng cho Property discovery.
- Phân rõ Property search freshness có thể eventual trong khi Booking authority không oversell.
- Dùng CDC/outbox với source revisions và delete replay.
- Đo chi phí search service thêm vào TCO.

### Verdict

Không nhất thiết bỏ wide-column authority. Có thể giữ nó cho workload chính và bổ sung **search read model** nếu chi phí vận hành chấp nhận.

## 92. Case study C: GSI giúp truy vấn nhưng chưa giữ uniqueness

### Bối cảnh

Đăng ký tenant có yêu cầu unique normalized email. Hai clients:

```text
Client A queries email GSI -> no item.
Client B queries email GSI -> no item.
Client A creates user U1.
Client B creates user U2.
``

### Vấn đề

GSI eventual query-then-insert không cung cấp một **atomic global uniqueness claim**. Ngay cả index rất nhanh, race vẫn xảy ra.

### Phương án

- Conditional Put trên authoritative email registry key.
- Transactionally coordinate registry + user creation nếu API/scope hỗ trợ.
- Hoặc workflow claim/pending/reconciliation, có release/expiry policy.

### Verdict

Đừng loại database vì “GSI eventual” nếu có một thiết kế uniqueness authority tốt, nhưng **đừng tuyên bố unique được bảo vệ** chỉ vì tạo secondary index.

## 93. Case study D: search rất nhanh nhưng booking status bị cũ

### Bối cảnh

Search Q3 trả top-K trong 80 ms. Khi user vừa thanh toán:

```text
Source booking: CONFIRMED rev12
Search index: PENDING rev11
``

### Vấn đề

Nếu My bookings API dùng search index mà business hứa RYW, user thấy sai sau thanh toán. Search throughput tốt không bù được violation.

### Phân tầng đúng

- Search property discovery có freshness SLO riêng.
- My booking/read-after-payment lấy dữ liệu từ authority hoặc version-gated projection.
- Khi trả results từ search, có thể hydrate authoritative status cho một số items khi cần.
- Tách mục tiêu p99 và cost.

### Verdict

Search engine có thể **PASS Q3**, nhưng **FAIL vai trò booking authority/read path Q5** nếu không có architecture guard.

## 94. Case study E: active-active nhiều region và unique inventory

### Bối cảnh

Hai regions đều writable để giảm latency:

```text
R1 sees last room = 1.
R2 sees last room = 1.
WAN partition.
R1 confirms booking B1.
R2 confirms booking B2.
``

### Vấn đề

Đôi bên có thể local ACK, sau đó conflict resolution không thể biến hai business confirmations thành một mà không vi phạm lời hứa với ít nhất một người dùng.

### Các lựa chọn

- Chia **ownership/quota** mỗi region và không oversell tổng quota.
- Một strong authority/quorum cho inventory writes, chấp nhận latency/availability trade-off.
- Holds/pending confirmations với reconciliation, không xác nhận sớm khi global uniqueness chưa chắc.
- Conflict semantics/compensation đã được business duyệt.

### Verdict

Không chọn active-active chỉ từ p99 regional reads. Đánh giá **global inventory invariant dưới network partition** là hard gate.

## 95. Case study F: graph tốt cho fraud nhưng không cần làm order ledger

### Bối cảnh

Một fraud service cần tìm:

```text
Customer -> Device -> AnotherCustomer -> Card -> Booking
``

Graph traversal cho những mô hình này có thể thuận lợi, nhưng order status API chỉ lookup by ID và append events.

### Thiết kế

```text
Booking/payment authority
     |
     +-- controlled events -> Fraud graph projection
``

Graph projection có thể phân tích network relationships với latency/freshness đã định; quyết định payment cuối cùng vẫn cần policy khi graph chưa bắt kịp.

### Verdict

Graph giải quyết **một access pattern chuyên biệt**, không nhất thiết thay toàn bộ data authority. TCO cần gồm CDC/graph consistency/privacy.

## 96. Case study G: hot partition khiến p99 phá SLO

### Bối cảnh

Candidate B có trung bình Q2 p99 = 50 ms trên 1 triệu synthetic records. Nhưng production estimate:

```text
Typical customer: 30 bookings
Large enterprise customer: 1,500,000 bookings
``

Một partition theo customer không bucket có thể rất lớn/hot.

### Điều chỉnh

- Bucket theo year/month hoặc shard suffix nếu access pattern cho phép.
- Pagination và merge-sort qua buckets.
- Bounded fan-out/maximum page size.
- Cân nhắc query table mới cho enterprise tenants.
- Test việc đổi key có ảnh hưởng transaction/uniqueness scope không.

### Verdict

Benchmark dữ liệu đều **không đủ bằng chứng** cho candidate. Phải chạy high-skew workload và test tail latency.

## 97. Case study H: transaction PASS nhưng restore không dùng được

### Bối cảnh

NoSQL candidate đáp ứng multi-key transaction và index SLO. DR drill khôi phục backup từ region khác thất bại vì:

```text
Backup encrypted with key unavailable in standby region.
``

### Vấn đề

Một database đạt correctness healthy-state nhưng **không đáp ứng RTO/RPO**. Encryption key lifecycle, backup access và restore automation là một phần lựa chọn.

### Đánh giá

- Restore trong isolated target bằng standby identity.
- KMS grants và key rotation.
- Snapshot/log compatibility.
- RPO data reconciliation.
- CDC/search read model rebuild.

### Verdict

Nếu DR là hard gate, candidate/architecture **chưa đủ điều kiện** cho tới khi recovery được sửa và diễn tập thành công.

## 98. Runbook lựa chọn NoSQL theo các giai đoạn

### Pha A — Requirements

1. Inventory entities/aggregate boundaries.
2. Liệt kê query/read/write patterns theo tần suất và peak.
3. Ghi business invariants và consequences nếu sai.
4. Định nghĩa freshness, RYW, consistency, RPO/RTO.
5. Phân loại dữ liệu/tenant region/compliance.

### Pha B — Candidate designs

1. Chọn một số engine/architecture phù hợp access patterns.
2. Mô hình primary/partition/shard keys và secondary indexes.
3. Gắn transaction/conditional-authority strategy cho từng invariant.
4. Gắn consistency mode/route cho từng read API.
5. Ghi những thành phần thêm như CDC/search/cache.

### Pha C — Evidence

1. Test CRUD/queries với realistic distributions.
2. Test concurrency and invariant preservation.
3. Test RYW/session/reconnect/failover.
4. Test index build/refresh and CDC replay.
5. Test N−1 zone capacity, backup/restore.
6. Đo TCO, latency, throughput, error and runbook readiness.

### Pha D — Decision

1. Loại hard-gate failures.
2. Chấm preferences với score/evidence/confidence.
3. Review risks/assumptions/chỗ chưa thử.
4. Chốt architecture với documented trade-offs.
5. Đặt migration/rollback, monitoring và reevaluation trigger.

## 99. Tiêu chí PASS, FAIL và INCONCLUSIVE

### PASS

Ứng viên đáp ứng **đúng contract trong fault/workload đã thử**, có bằng chứng đủ và kết quả lặp lại.

### FAIL

Có confirmed invariant violation, query không đạt hard SLO, unauthorized access, không restore được hoặc capability không hỗ trợ phạm vi bắt buộc.

### INCONCLUSIVE

- Driver/session/index setting chưa rõ.
- Fault không thực sự xảy ra.
- Test dataset thiếu hot skew.
- Monitoring mất dữ liệu.
- Write outcome unknown chưa reconcile.
- Không xác minh đúng source revision.
- Benchmark thiếu source/target cost hoặc production topology.

Không ghi “PASS” chỉ vì demo chạy được. Một kết quả **INCONCLUSIVE** có thể dẫn tới test bổ sung hoặc quyết định dựa trên risk acceptance công khai.

## 100. Mẫu Architecture Decision Record (ADR)

```markdown
# ADR: Choose storage for booking authority and search

## Context
- Q1/Q2 requirements: ...
- Q3 search requirements: ...
- Q4 inventory invariant: ...
- Required consistency and RPO/RTO: ...

## Options
- A: Document authority + search projection
- B: Key-value authority + search projection
- C: Wide-column authority + specialized reservation service

## Hard gates
- Global/tenant uniqueness: ...
- No overselling: ...
- Data isolation: ...
- Cross-region durability: ...

## Evidence
- Benchmark IDs and workload definitions: ...
- Transaction/condition tests: ...
- Session/failover histories: ...
- Search freshness and recovery: ...

## Decision
- Selected design: ...
- Accepted trade-offs: ...
- Known risks and mitigation owners: ...

## Migration and rollback
- Source-of-truth cutover protocol: ...
- CDC, reconciliation, compatibility: ...
- Monitoring and decommission criteria: ...

## Revisit triggers
- Traffic doubles / new query class appears
- New multi-region business requirement
- Index feature/version migration
```

**Một ADR tốt lưu lý do và bằng chứng, không chỉ tên sản phẩm được chọn.** Khi yêu cầu thay đổi, đội có thể biết điều kiện nào làm quyết định cũ không còn phù hợp.

## 101. Ba mươi bài tập thực hành

### Bài 1 — Từ tính năng đến access pattern

Ứng dụng cần “xem đơn đặt chỗ của tôi”. Chuyển mô tả này thành key predicates, sort, pagination, frequency, SLO và read-after-write contract. Giải thích vì sao `SELECT *` theo tất cả tenants không phải phương án hợp lý.

### Bài 2 — Primary key và tenant

Với booking ID có thể trùng giữa hai tenants, hãy thiết kế identity đầy đủ. API nhận booking ID nhưng không kiểm tenant scope có rủi ro gì? Chỉ đặt `tenantId` trong key đã đủ authz chưa?

### Bài 3 — Document aggregate

Mô hình booking có 20 line items, mỗi line item cập nhật cùng booking status. Trường hợp nào nên embed? Khi nào array lớn hoặc shared inventory khiến embed không phù hợp?

### Bài 4 — Wide-column query table

Thiết kế bảng cho Q2 `tenantId, customerId` sort `createdAt DESC, bookingId DESC`. Giải thích lý do chọn partition/clustering keys và cách xử lý customer có một triệu bookings.

### Bài 5 — Graph hay document?

Một tính năng cần tìm đường đi Customer→Device→Account→Payment→Booking tối đa 5 hops. Vì sao graph có thể hữu ích? Benchmark cần xem degree/path distribution gì?

### Bài 6 — Search index

Thiết kế query “chỗ ở trong bán kính 5 km, có wifi, giá tối đa 500.000, xếp theo relevance”. Vì sao một key-value lookup theo property ID không đủ? Độ mới dữ liệu nào có thể eventual?

### Bài 7 — ANN index

Khi vector search trả top-K approximate, cần kiểm thêm những gì ngoài p99? Nếu filters tenant/price bị áp sau retrieval, những kết quả sai nào có thể xuất hiện?

### Bài 8 — Composite index

So sánh hai index:

```text
(tenantId, customerId, status, createdAt DESC)
(tenantId, customerId, createdAt DESC)
```

Với query có/không có filter status, hãy dự đoán trade-off và nêu cách xác minh bằng query explain.

### Bài 9 — Covering index

List booking chỉ cần `id,createdAt,status`. Có nên thêm những fields này vào covering index? Đo storage/write cost và performance trước/sau như thế nào?

### Bài 10 — Low selectivity

80% bookings có `status=CONFIRMED`. Index chỉ trên status có giúp nhiều không? Vì sao tenant/customer key và cardinality có thể quan trọng hơn?

### Bài 11 — Hot partition

Tất cả inventory records cho property lớn nhất thuộc một partition, nhận 20.000 writes/s. Đề xuất split/bucketing/escrow, đồng thời nêu tác động lên transaction/oversell invariant.

### Bài 12 — Single-item CAS

Inventory remaining=1, hai clients cùng cố reserve. Viết pseudo conditional update ngăn remaining âm và giải thích tại sao client-side read-then-write không đủ.

### Bài 13 — Multi-day reservation

Đặt phòng ba đêm cần giảm inventory của ba ngày. Engine chỉ có atomic mutation một key. Thiết kế hai phương án khác nhau: aggregate key và durable reservation saga; so rủi ro của mỗi phương án.

### Bài 14 — ACID và isolation

Hai transactions cùng đọc hai nhân viên đang on-call, mỗi transaction tắt một người. Sau commit không còn ai. Đây là hiện tượng gì và vì sao snapshot isolation có thể chưa đủ?

### Bài 15 — Unique reference

Hai workers đăng ký cùng bookingReference ở hai shards. Nếu mỗi shard có local unique index, có bảo đảm unique tenant-wide không? Thiết kế registry/claim.

### Bài 16 — Idempotency

Một request CreateBooking commit nhưng response mất; client retry với new request ID. Mô tả duplicate effect và thiết kế idempotency ledger/collision policy.

### Bài 17 — Outbox

Booking status commit thành công nhưng process crash trước khi publish Kafka event. Làm thế nào outbox trong atomic source boundary giúp? Vì sao relay vẫn phải có consumer idempotency?

### Bài 18 — Saga vs transaction

Đặt chỗ, thu tiền, gửi email. Phần nào có thể nằm trong DB transaction? Phần nào cần workflow/reconciliation? Làm gì khi payment provider trả timeout sau khi capture?

### Bài 19 — RYW

User ghi revision 11, đọc qua một secondary trả revision 10. Khi nào là violation? Vì sao cùng user web cookie không nhất thiết tương ứng cùng database session?

### Bài 20 — Monotonic reads

Một session đọc rev15 rồi đổi region và đọc rev13. Phân biệt với RYW và chọn giải pháp source revision gate/causal token.

### Bài 21 — Quorum

RF=3, W=2, R=2. Tính điều kiện quorum giao nhau. Liệt kê ba lý do tại sao chưa được kết luận linearizability của mọi Cassandra write/read trong mọi topology.

### Bài 22 — DynamoDB GSI

Base table GetItem strong trả booking mới, query GSI không thấy. Đánh giá contract của mỗi đường và nêu cách đáp ứng RYW cho My bookings.

### Bài 23 — MongoDB transaction

Booking và inventory ở hai documents, sharded khác nhau. Phải kiểm tra transaction support/isolation/writes, contention và failover điều gì? Tại sao một demo transaction nhỏ chưa đủ?

### Bài 24 — Redis Cluster

Ba ngày inventory nằm trên ba hash slots. Một Lua script multi-key có thể chạy atomically cross-slot không? Đề xuất alternative authority/workflow và test.

### Bài 25 — Elasticsearch source-of-truth?

Search index ACK booking status CONFIRMED nhưng search query chưa thấy do refresh. Có nên dùng search query để quyết định charge payment không? Vì sao?

### Bài 26 — Causal chain

Service B nhận event BookingConfirmed rev12, nhưng follower DB mới ở rev11. Chọn strategy bảo vệ ShippingTask không dùng state cũ. Test timeout/lag thế nào?

### Bài 27 — Multi-region partition

R1 và R2 cùng bán phòng cuối trong WAN partition. Đề xuất phương án ownership/escrow/quorum và mô tả đánh đổi availability/latency.

### Bài 28 — Weighted score

Với bảng preferences và weights ở mục 76, tính điểm A và B. Nếu B fail hard gate unique reference, kết luận hợp lệ là gì? Thay weights có được bù điểm fail không?

### Bài 29 — Benchmark evidence

Ứng viên X p99=40 ms trên 100 nghìn records đều, ứng viên Y p99=70 ms trên 100 triệu records có skew. Có thể kết luận X tốt hơn không? Thiết kế benchmark công bằng.

### Bài 30 — Lựa chọn tổng hợp

Thiết kế architecture cho:

```text
Java Booking API (3 AZ)
  |
  +-- bookings (read-after-write needed)
  +-- inventory (no overselling)
  +-- payments (idempotent workflow)
  +-- property search (full-text + geo + vector)
  +-- analytics (monthly aggregates)
```

Bài làm cần có:

- Ít nhất hai candidate architectures.
- Access-pattern table và source-of-truth ownership.
- Primary/partition keys, indexes, and hot-key strategy.
- Single-key/multi-key/third-party invariant protocols.
- Consistency per read route, session, region.
- CDC/outbox/search freshness và delete propagation.
- p99/load/fault tests, security/DR gates.
- Hard-gate review, weighted score có evidence và ADR.

## 102. Checklist chọn mô hình dữ liệu

1. Có danh sách access patterns và owner nghiệp vụ cho mỗi operation?
2. Đã phân loại point lookup, range/sort, search, traversal, aggregate và vector?
3. Có đo tần suất, p95/p99, peak và distribution skew?
4. Có xác định aggregate/document/item/row boundary?
5. Partition/shard key có phân tải và phục vụ routing đúng?
6. Tenant identity có nằm trong key/authorization scope phù hợp?
7. Có hot key, large partition hoặc high-degree graph nodes?
8. Có mô hình hóa embedded và referenced data phù hợp update patterns?
9. Có các bản biểu diễn denormalized nào cần đồng bộ?
10. TTL/delete/recreation/version scope đã rõ?
11. Có yêu cầu unique global, unique per tenant hay local?
12. Có cần lookup đảo chiều từ child→parent hoặc theo các field ngoài key?
13. Có cần truy vấn nhiều partitions/joins/giao dịch?
14. Có xét schema evolution và data size limits?
15. Có giải pháp cho migration/resharding khi key design thay đổi?
16. Có giả định engine hỗ trợ query mà chưa được kiểm thực tế?

## 103. Checklist chọn và vận hành chỉ mục

1. Mỗi query có index/read model ứng viên và explain evidence?
2. Composite index column/key order phù hợp equality/range/sort?
3. Có unique stable tie-breaker cho pagination?
4. Query planner có scan quá nhiều rows/index entries?
5. Có phân tích low-selectivity fields và hot values?
6. Có index covering, included/stored fields và chi phí storage?
7. Index updates synchronous hay asynchronous?
8. Có RYW/freshness guarantee cho query từ index đó không?
9. Có build/rebuild/refresh/compaction budget?
10. Có test update/delete/TTL propagation và stale tombstones?
11. Có policy cho index snapshot/export và PII?
12. Có plan rollback nếu index migration/cutover fail?
13. Full-text analyzers và relevance có được kiểm theo business queries?
14. Geo boundaries/coordinate precision có đúng?
15. Vector ANN recall@k và filter correctness có đo?
16. Có alert source-to-index lag, missing events và query failure?
17. Nếu một index mất/đang rebuild, API có degraded mode đúng?

## 104. Checklist giao dịch và bất biến

1. Có viết bất biến bằng ngôn ngữ business hoặc biểu thức test được?
2. Mỗi invariant cần sửa/đọc bao nhiêu keys/partitions/shards?
3. Single-item conditional mutation có đủ không?
4. Nếu multi-key, engine hỗ trợ transaction đúng scope/version?
5. Isolation level và write skew/lost update/phantom đã được xét?
6. Có uniqueness claim đúng phạm vi tenant/global?
7. Có idempotency key với request hash và ledger?
8. Transaction timeout/commit unknown có reconciliation?
9. Có durable outbox cho events phải publish?
10. Nếu dùng saga, compensation có thể retry/timeout và được ghi bền?
11. Có rate/lock/transaction contention budget?
12. Concurrent invariant test dùng cùng hot key đã được chạy?
13. Failover giữa transaction phases có được diễn tập?
14. Có kiểm duplicate/out-of-order CDC effects?
15. Có phân biệt transaction success với index/search visibility?
16. Có hiểu durability sau ACK khi mất primary/AZ/region?
17. Có thể trình bày hard gate này cho security/business review không?

## 105. Checklist phạm vi nhất quán

1. “Strong”, “causal” hoặc “eventual” đã gắn với exact API/operation chưa?
2. Đã nêu unit: key, document, partition, transaction hay multi-region?
3. Write ACK concern và read concern/CL/read preference đã pin?
4. Có RYW/monotonic read qua driver session, app session, reconnect?
5. Token/bookmark/minimum revision có được truyền đúng?
6. Read từ GSI/search/cache có freshness contract riêng?
7. Transaction snapshot có thể cố ý đọc cũ không?
8. Quorum math có đi kèm protocol/version/topology assumptions?
9. Có strong read ở remote region thật sự không, và RPO gì?
10. Under network partition, minority read/write có behavior nào?
11. Có tối đa stale age và latency deadline?
12. Khi không đáp ứng được consistency, API fail/pending/timeout đúng?
13. Có test acknowledged write data loss sau failover?
14. Các events/projections có source revision/tombstone guards?
15. Cache có thể ghi lùi version do race hay không?
16. Có oracle với invocation/completion history và concurrent writers?
17. Đo stale success, timeout và cost như những chiều độc lập?

## 106. Checklist đánh giá tổng thể

1. Hard gates và preferences được tách?
2. Các ứng viên là **architecture** đầy đủ, không chỉ tên engine?
3. Có test dataset synthetic với workload distribution/scale đại diện?
4. Có đo correctness, p99, throughput và read/write cost cùng lúc?
5. Index build, schema migration và backfill có runbook?
6. CDC/search/cache thêm rủi ro consistency nào?
7. Có source identity, backup/PITR và DR restore test?
8. Có N−1 zone capacity và AZ/region failure plan?
9. Security/data residency/KMS/audit được đưa vào hard gates?
10. Team có kỹ năng vận hành, monitoring và incident ownership?
11. TCO tính cả indices, replicas, egress, projections, operations?
12. Vendor lock-in/data portability có được đánh giá?
13. Mọi điểm số đều có evidence reference và ngày?
14. Có ghi rõ điều kiện làm benchmark inconclusive?
15. Có ADR nêu lựa chọn, trade-off, risks và triggers để xét lại?
16. Có rollback/forward-fix plan khi migration thất bại?
17. Khi product thêm access pattern mới, model có đường tiến hóa?

## 107. Những hiểu lầm cần tránh

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “Dữ liệu JSON nên chọn document database” | Dạng JSON không quyết định query, partition và invariants |
| “Có quan hệ nên dùng graph database” | Chỉ traversal/path-heavy workload mới thường tận dụng ưu thế graph |
| “Có hàng tỷ records thì luôn chọn wide-column” | Access patterns, skew, indexes, transactions và vận hành mới quyết định |
| “Key-value không thể có transaction” | Có những hệ hỗ trợ conditional/transactional APIs trong scope cụ thể |
| “NoSQL không hỗ trợ ACID” | Có nhiều mức transaction, nhưng phạm vi/giới hạn khác nhau |
| “Một document atomic thì mọi booking business flow atomic” | Inventory/payment ở entities/services khác không tự nằm trong cùng boundary |
| “Index nào cũng đồng bộ với primary write” | GSI/search/read model có thể asynchronous |
| “Có secondary index là mọi filter/sort đều nhanh” | Query plan, selectivity, left-prefix, cardinality và fan-out quyết định |
| “Thêm index chỉ giúp nhanh hơn, không có chi phí” | Write amplification, storage, build/rebuild, privacy và lag |
| “Unique index ở shard tự unique toàn cụm” | Phải xác minh exact global/tenant/shard constraint scope |
| “Dùng query-then-insert là đủ enforce unique” | Concurrent reads có race; cần atomic authority/claim |
| “Bất kỳ ACID transaction đều serializable” | Isolation levels và anomalies khác nhau |
| “Snapshot isolation ngăn mọi write skew” | Có thể cần serializable hoặc invariant enforcement khác |
| “Transaction commit bao gồm gửi Kafka/email/payment” | External side effects nằm ngoài DB boundary nếu không có protocol |
| “Saga là transaction nguyên tử toàn bộ workflow” | Saga là durable steps/compensations, có intermediate states |
| “Outbox làm mọi consumer exactly-once” | Relay/replay có thể duplicate; consumer cần idempotency |
| “Retry write sau timeout luôn an toàn” | Commit có thể đã xảy ra; cần stable IDs và reconciliation |
| “Quorum intersection luôn chứng minh linearizability” | Còn phụ thuộc protocol, clocks/versioning, topology và read repair |
| “Strong read của region R2 thấy ngay write ACK ở R1” | Cross-region replication/authority mode quyết định |
| “Majority write làm mọi secondary eventual read tươi ngay” | Read session/concern và replica applied position vẫn quan trọng |
| “RYW và serializable là cùng một guarantee” | RYW chỉ theo phiên, serializable theo toàn transaction history |
| “Search query nhìn thấy ngay document index ACK” | Refresh/PIT/search visibility riêng |
| “Một index có field tenant nghĩa tenant isolation an toàn” | Authz/tenant enforcement cần end-to-end test |
| “Vector similarity chính xác như primary-key equality” | ANN có recall/approximation và filter semantics riêng |
| “Managed NoSQL loại bỏ operational risk” | App vẫn quản lý query model, costs, RPO/RTO, security |
| “Có ba replicas là chịu được mất một AZ bất kỳ” | Placement/voters/capacity và common dependencies quyết định |
| “p99 tốt nhất chắc chắn là database tốt nhất” | Hard invariants, durability, privacy và TCO có thể quan trọng hơn |
| “Mọi sản phẩm có transactions đều tương đương” | Scope, limits, isolation và distributed cost khác nhau |
| “Một số score 4.3/5 là bằng chứng khách quan” | Điểm phụ thuộc weights, evidence và scale; hard gates không bù được |
| “Chỉ cần chọn database, CDC/cache/search là phần phụ” | Mỗi thành phần thêm cost, data copy và consistency boundary |

## 108. Quy trình tư duy trong một trang

```text
Business workflows and invariants
                |
                v
Access-pattern inventory
 (key, range, filter, traversal, search, aggregate)
                |
                v
Data modeling candidates
 (aggregate, partition/shard key, denormalized views)
                |
                v
Index and query-path candidates
 (primary, composite, GSI, inverted, geo, graph, ANN)
                |
                v
Transactional authority
 (single-key CAS, multi-key transaction, saga, outbox)
                |
                v
Consistency boundary per operation
 (ACK, RYW, quorum, session, replica, region, CDC)
                |
                v
Hard-gate evaluation
 (correctness, security, durability, residency, DR)
                |
            +---+---+
            |       |
          FAIL     PASS
            |       |
            v       v
       Redesign   Benchmark and TCO
                    |
                    v
             ADR + migration plan
                    |
                    v
             Production monitoring
                    |
                    v
          Reevaluate when needs change
```

### Bốn câu hỏi nối nhau

1. **Mô hình:** Record/aggregate/partition nào là authority cho dữ liệu đang đọc hoặc ghi?
2. **Chỉ mục:** Query sẽ truy cập đường vật lý nào, với chi phí và độ mới nào?
3. **Giao dịch:** Bất biến nào cần atomic mutation/transaction/workflow và phạm vi nào?
4. **Nhất quán:** Sau khi write ACK, ai nhìn thấy gì, từ đâu, trong bao lâu và dưới lỗi nào?

Nếu không trả lời được một trong bốn câu, ứng viên chưa đủ được xác minh để chốt.

## 109. Một ví dụ quyết định đã được diễn đạt đúng

Giả sử đội chọn:

```text
Booking authority:
  Document database with conditional updates/transactions

Inventory authority:
  Dedicated reservation keys with verified no-oversell protocol

Search:
  Elasticsearch/OpenSearch projection
  from source changes, with freshness SLO

Cache:
  Redis for non-authoritative catalog reads

Analytics:
  Event/batch read model with explicit snapshot timestamp
```

Đây **không phải khuyến nghị tuyệt đối** cho mọi ứng dụng; chỉ minh họa cách viết lựa chọn có phạm vi.

### Giải thích theo bốn trục

- **Mô hình:** Booking là document aggregate; Inventory authority tách vì cùng một resource được nhiều bookings cạnh tranh.
- **Chỉ mục:** Compound index cho My bookings, search projection cho full-text/geo; không bắt một index làm mọi thứ.
- **Giao dịch:** Booking status dùng conditional update; inventory invariant qua protocol được test; payment xử lý bằng idempotency và durable workflow.
- **Nhất quán:** My bookings sau write đọc từ route đáp ứng RYW, search có freshness bound, catalog cache có stale allowance, payment status không được báo sai.

### Bằng chứng cần có trước production

1. Concurrent oversell tests không có confirmed violations.
2. Booking Q1/Q2 và search Q3 đạt p99 dưới tải đại diện.
3. Search CDC catch-up theo freshness SLO, bao gồm updates/deletes.
4. ACKed business writes còn sau leader/AZ failover theo RPO.
5. Client reconnect/session switch không phá RYW theo app contract.
6. Backups/restores/KMS/cutover rollback được diễn tập.
7. TCO và operational owners được phê duyệt.

Nếu thiếu một bằng chứng quan trọng, ghi **INCONCLUSIVE hoặc điều kiện triển khai**, không tô xanh bằng cách nói “công nghệ này hỗ trợ sẵn”.

## 110. Kết luận

Không có một nhãn **NoSQL tốt nhất** cho mọi workload. Quyết định phù hợp là quyết định minh bạch về **mô hình truy cập, đường chỉ mục, authority của giao dịch và phạm vi nhất quán**, cùng với giới hạn vận hành.

Những nguyên tắc cốt lõi:

1. **Bắt đầu từ truy vấn và bất biến**, không bắt đầu từ tên database.
2. **Chọn partition/aggregate boundary theo cả reads và atomic writes.** Một data model tốt cho Q2 có thể làm Q4 khó; phải cân bằng.
3. **Index có chi phí và freshness semantics.** GSI/search/ANN không phải cùng một loại index với cùng consistency.
4. **Transaction phải ghi đúng phạm vi.** Single-key, multi-document, multi-shard và multi-service workflows không đồng nhất.
5. **Conditional writes và idempotency rất quan trọng.** Chúng giúp tránh oversell, duplicate bookings và replay sai khi timeout.
6. **Phân biệt serializability, linearizability, RYW, causal và eventual.** Mỗi guarantee có phạm vi riêng.
7. **Quorum và số replicas không đủ thay proof.** Read modes, topology, version rules và failure model quyết định data được thấy.
8. **Đánh giá full architecture.** Thêm cache/search/CDC nghĩa là thêm consistency, privacy, cost và recovery boundaries.
9. **Hard-gate-first, benchmark-second.** Không để điểm latency đẹp bù cho vi phạm dữ liệu, quyền truy cập hoặc durability.
10. **Lưu bằng chứng và quyết định trong ADR.** Khi dữ liệu, tải hoặc yêu cầu thay đổi, bạn sẽ biết phải đánh giá lại điều gì.

Câu hỏi cuối cùng nên đặt ra khi lựa chọn:

> **“Với từng thao tác quan trọng, dữ liệu nằm ở đơn vị nào, query sử dụng index nào, bất biến được giữ bởi giao dịch hoặc authority nào, và những người đọc khác nhau có thể quan sát state nào sau một write thành công — kể cả khi có replica lag, reconnect hay mất một miền lỗi?”**

Khi câu trả lời có **model rõ, query plan có số liệu, invariant tests, consistency histories, failure drills và chi phí vận hành**, việc chọn NoSQL không còn là tranh luận dựa trên cảm tính. Nó trở thành một **quyết định kiến trúc có thể kiểm chứng, so sánh và bảo vệ bằng bằng chứng**.
