# Lựa chọn MongoDB độc lập hoặc phối hợp với hệ quản trị khác

> **Module:** Database Engine Document MongoDB  
> **Chương:** Thiết kế ứng dụng  
> **Bài học:** Lựa chọn MongoDB độc lập hoặc phối hợp với hệ quản trị khác

## 1. Tình huống mở đầu: một database có nên làm tất cả?

Một nền tảng thương mại điện tử cần lưu:

- Danh mục sản phẩm có cấu trúc thuộc tính không đồng nhất theo ngành hàng.
- Đơn hàng và thanh toán phải tránh ghi trùng, kiểm soát chuyển trạng thái.
- Giỏ hàng và session có lưu lượng đọc/ghi cao, thời gian sống ngắn.
- Tìm kiếm sản phẩm theo tiếng Việt, lọc thuộc tính, xếp hạng và gợi ý.
- Dashboard doanh thu và phân tích lịch sử nhiều năm.
- Ảnh sản phẩm, file đính kèm và tài liệu dung lượng lớn.
- Dữ liệu cần xuất sang hệ thống kế toán đã dùng PostgreSQL.

Một đề xuất là: **“Dùng MongoDB cho mọi thứ vì document database linh hoạt.”** Đề xuất khác: **“Dùng mỗi loại database tốt nhất cho một bài toán.”**

Cả hai có thể đúng trong một bối cảnh và sai trong bối cảnh khác. Một hệ thống quá nhiều kho dữ liệu có thể khó vận hành hơn chính yêu cầu sản phẩm; ngược lại, ép một database làm những truy vấn và hợp đồng mà nó không phù hợp có thể làm tăng chi phí, độ trễ và rủi ro mất nhất quán.

**Câu hỏi cần giải:** Khi nào MongoDB nên là **nền tảng lưu trữ độc lập**, và khi nào nên là **một thành phần trong kiến trúc polyglot persistence** — kết hợp nhiều hệ quản trị dữ liệu theo nhu cầu?

### 1.1. Kết quả học tập

Sau bài học, bạn có thể:

1. Đánh giá MongoDB dựa trên **access patterns, invariants, SLO, chi phí và năng lực vận hành**, không dựa vào nhãn NoSQL/SQL.
2. Biết những trường hợp MongoDB một mình đã đủ: dữ liệu document, aggregation, indexes, transactions, change streams, TTL và tìm kiếm khi dịch vụ hỗ trợ.
3. Biết những trường hợp cơ sở dữ liệu quan hệ, cache, search engine, message broker, object storage hay data warehouse có lợi thế.
4. Phân biệt **source of truth**, cache, search index, read model, event log và analytical copy.
5. Thiết kế ranh giới dữ liệu rõ trong một hệ thống dùng MongoDB cùng PostgreSQL, Redis, OpenSearch, Kafka hoặc storage khác.
6. Phân tích dual-write problem, event ordering, retry, at-least-once delivery, idempotency và reconciliation.
7. Áp dụng transactional outbox, change streams, CQRS, cache-aside và backfill theo khả năng.
8. Xác định consistency cần thiết trên từng đường nghiệp vụ.
9. Lập bảng quyết định với tiêu chí đo được, mô phỏng các kịch bản sự cố và kế hoạch rollback.
10. Tạo prototype trên MongoDB test, có test dữ liệu và giới hạn cleanup rõ ràng.
11. Giải thích trade-off về tổng chi phí, backup, quyền truy cập, schema evolution, năng lực đội ngũ và khả năng thay đổi kiến trúc trong tương lai.

## 2. Trước hết phải chọn bài toán, không chọn tên sản phẩm

Một thiết kế database nên bắt đầu từ câu hỏi:

- **Dữ liệu nào được đọc và ghi cùng nhau?**
- Những truy vấn nào tạo ra phần lớn tải?
- Quy tắc đúng sai nào không được vi phạm kể cả khi failover?
- Tần suất thay đổi cấu trúc document và truy vấn là bao nhiêu?
- Dữ liệu là nguồn sự thật hay bản sao phục vụ tìm kiếm/hiển thị?
- Tác vụ có yêu cầu giao dịch nhiều bảng/collections hay không?
- Có thể chấp nhận kết quả tìm kiếm và báo cáo chậm vài giây không?
- Khi một hệ thống phụ ngừng, nghiệp vụ chính có cần tiếp tục hoạt động không?
- Đội ngũ có khả năng vận hành thêm cache, broker và search cluster không?

### 2.1. Bảng câu hỏi về workload

| Chiều đánh giá | Cần biết | Vì sao quan trọng |
| --- | --- | --- |
| Write patterns | Insert/update/delete, batch, write amplification | Index, contention, durability |
| Read patterns | Theo ID, list theo filter, full-text, aggregation, graph traversal | Quyết định index, engine và projection |
| Data shape | Document lồng nhau, quan hệ nhiều-nhiều, dữ liệu bán cấu trúc | Chiến lược embedding/referencing |
| Atomic boundary | Một document, nhiều documents, nhiều hệ thống | Transaction và consistency |
| SLO | p95/p99 latency, uptime, RPO/RTO | Capacity và replication |
| Growth | Records, bytes, hot keys, tenants, retention | Sharding, partitioning, storage |
| Security | PII, tenancy, residency, audit | Access control, encryption, compliance |
| Operations | Backup, upgrades, observability, runbooks | Tổng chi phí sở hữu |
| Analytics | OLTP queries hay scan nhiều năm | Tách analytical workloads |
| Team | Kỹ năng MongoDB, SQL, Redis, Kafka, search | Độ phức tạp vận hành |
| Integration | Hệ thống kế toán, CRM, API, data lake | Ownership và đồng bộ |

### 2.2. Không thể quyết định chỉ bằng lượng dữ liệu

Một collection 10 triệu records có thể chạy tốt với MongoDB nếu queries được phục vụ bằng indexes thích hợp. Một collection 20.000 records vẫn có thể chậm nếu mỗi request yêu cầu join phức tạp, sort không có index, dùng `$lookup` lặp lại hoặc tạo document không kiểm soát.

**Data volume không thay thế workload analysis.** Cần biết cấu trúc truy vấn, cardinality, read/write ratio, skew, caching, query planner và business invariants.

## 3. MongoDB độc lập nghĩa là gì?

Trong bài, “MongoDB độc lập” nghĩa là MongoDB là **hệ quản trị dữ liệu chính đủ phục vụ những nhu cầu lưu trữ và truy vấn của ứng dụng**; nó không có nghĩa chỉ có một server `mongod` duy nhất.

Production thường cần:

- Replica set để high availability, durability và change streams.
- Sharding khi workload/capacity đòi hỏi.
- Indexes, validators, TTL, aggregation.
- Backup, PITR khi dịch vụ hỗ trợ, monitoring và access control.
- Tùy nền tảng: Search/Vector Search tích hợp hoặc dịch vụ kèm MongoDB.

Một kiến trúc “MongoDB-only” vẫn có load balancer, object storage cho asset lớn, application workers và monitoring; câu hỏi ở đây là **có thêm một kho dữ liệu có trạng thái cần đồng bộ không**.

### 3.1. Một kiến trúc đơn giản

```text
              Browser / Mobile
                    |
                 API layer
                    |
              Application services
                    |
          +---------+---------+
          |                   |
     Reads & writes      Background jobs
          |                   |
          +---------+---------+
                    |
              MongoDB cluster
         +----------+-----------+
         |          |           |
       Indexes   Aggregation  Change streams
         |          |           |
       Fast API    Reports   Internal workflows
```

Nếu các requirements được phục vụ đầy đủ trong một cluster và cách tổ chức collections hợp lý, đây có thể là phương án rẻ và dễ kiểm soát hơn việc thêm 3–5 hệ thống phụ.

### 3.2. MongoDB có gì ngoài CRUD?

Không nên dựa vào định kiến “document database chỉ tìm theo `_id`”.

MongoDB cung cấp, tùy phiên bản/triển khai:

- Secondary/compound/multikey/partial/unique/TTL indexes.
- Aggregation pipelines gồm `$match`, `$group`, `$lookup`, `$facet`, `$setWindowFields`, `$unionWith`.
- Document-level atomicity.
- Multi-document transactions trên deployment hỗ trợ.
- Schema validation với `$jsonSchema`.
- Change streams trên replica set/sharded cluster.
- Geospatial indexes và truy vấn địa lý.
- Time-series collections.
- Full-text index cơ bản; **MongoDB Search/Atlas Search** là khả năng search phong phú hơn nhưng phụ thuộc sản phẩm/triển khai.
- Vector Search trên nền tảng/phiên bản hỗ trợ, không mặc định có ở mọi `mongod`.

Tuy nhiên, có các khả năng này **không có nghĩa mọi workload chạy tối ưu**. Một phép `$lookup` được MongoDB hỗ trợ vẫn phải kiểm CPU, index, cardinality, network và p99.

## 4. Khi nào MongoDB một mình là lựa chọn hợp lý?

### 4.1. Document là đơn vị đọc/ghi tự nhiên

Ví dụ sản phẩm có thuộc tính thay đổi theo ngành:

```javascript
{
  _id: "SKU-CHAIR-100",
  tenantId: "store-A",
  type: "furniture",
  title: "Ghế làm việc",
  priceCents: NumberLong("24500000"),
  attributes: {
    color: "black",
    material: "mesh",
    adjustableHeight: true
  },
  images: [
    {
      fileKey: "products/SKU-CHAIR-100/main.webp",
      role: "main"
    }
  ],
  updatedAt: ISODate("2026-11-14T04:00:00Z")
}
```

Một category khác có attributes khác. Nếu phần lớn API đọc cùng một product document và updates có phạm vi product, MongoDB document model giúp:

- Đọc một product với ít round trips.
- Lưu thuộc tính lồng nhau mà không cần nhiều bảng phụ.
- Áp dụng validation theo type/version phù hợp.
- Dùng index trên các fields thường truy vấn.
- Thay đổi schema với quy trình tiến hóa dữ liệu có kiểm soát.

Đây **không** phải khuyến nghị đưa tất cả data liên quan tới product vào một document không giới hạn.

### 4.2. Các dữ liệu con có vòng đời gắn với document cha

Một order snapshot:

```javascript
{
  _id: "order-123",
  customerId: "customer-9",
  status: "CREATED",
  lines: [
    {
      productId: "SKU-1",
      titleAtPurchase: "Sổ tay",
      unitPriceCents: NumberLong("300000"),
      quantity: NumberInt(2)
    }
  ],
  totalCents: NumberLong("600000"),
  createdAt: ISODate("2026-11-14T04:00:00Z")
}
```

Một snapshot tên sản phẩm/giá tại thời điểm mua thường nên nằm trong order vì:

- Order cần được đọc như một đơn vị.
- Giá hiện tại của sản phẩm không được thay đổi order lịch sử.
- Đơn hàng có bounded line items trong phần lớn mô hình.
- Cập nhật trạng thái order có thể là atomic single-document update.

Nhưng nếu một “order” có hàng triệu lines hoặc liên tục tăng event history, embedding có thể tạo document rất lớn, hotspot và chi phí update. Phải kiểm **BSON document size limit (16 MiB)** và growth patterns.

### 4.3. Những truy vấn được đáp ứng bằng index rõ ràng

Ví dụ:

```javascript
db.orders.find({
  tenantId: "store-A",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(30);
```

Một compound index ứng viên:

```javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1
  },
  {
    name: "orders_tenant_status_created"
  }
);
```

Nếu đây là workload chính, MongoDB có thể đáp ứng rất tốt khi index phù hợp, dataset và read/write SLO được đo trên thực tế.

Đừng thêm Elasticsearch chỉ để thực hiện filter theo tenant/status và sort timestamp khi index MongoDB đã giải quyết.

### 4.4. Cần transaction đa document nhưng tỷ lệ vừa phải

MongoDB hỗ trợ multi-document transactions. Nếu ứng dụng thỉnh thoảng cần cập nhật order và command ledger atomically, không nhất thiết phải chuyển toàn bộ hệ thống sang RDBMS.

Tuy nhiên:

- Transactions có chi phí, đặc biệt khi chạy dài hoặc cross-shard.
- Không đưa external HTTP/email/payment vào MongoDB transaction.
- Cần session, write concern và retry labels.
- Transaction không làm dữ liệu được tự động normalize như schema quan hệ.

### 4.5. Dùng aggregation vừa đủ thay data warehouse

Một dashboard vận hành nhỏ theo thời gian gần:

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "store-A",
      status: "PAID",
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        day: {
          $dateTrunc: {
            date: "$createdAt",
            unit: "day",
            timezone: "Asia/Ho_Chi_Minh"
          }
        }
      },
      count: { $sum: 1 },
      revenueCents: { $sum: "$totalCents" }
    }
  },
  { $sort: { "_id.day": 1 } }
]);
```

Đối với một khoảng dữ liệu và tần suất giới hạn, aggregation có thể đủ. Nếu hàng trăm analysts liên tục quét nhiều năm và join với finance/marketing datasets, một analytical store chuyên biệt có thể hợp lý hơn.

## 5. Khi nào nên cân nhắc hệ quản trị quan hệ?

### 5.1. Quan hệ là trung tâm nghiệp vụ

Một hệ quản trị có nhiều thực thể liên kết:

```text
Customers --< Orders --< OrderItems >-- Products
    |           |
    |           +--< Payments
    |
    +--< Addresses
```

Nếu nghiệp vụ thường xuyên cần:

- Join nhiều bảng một cách tự nhiên.
- Foreign keys và referential integrity ở tầng database.
- Constraints phức tạp liên quan nhiều tables.
- Truy vấn ad hoc SQL của nhóm phân tích/vận hành.
- Transactional schema theo nhiều entity.
- Hệ sinh thái ERP/accounting đang dùng SQL.

thì PostgreSQL, MySQL hoặc một RDBMS thích hợp có thể là **primary database tốt hơn**.

MongoDB có `$lookup` và transactions, nhưng nó **không tự cung cấp foreign-key constraints giữa collections giống RDBMS**. Chọn theo bất biến cần enforce và dạng truy vấn, không chỉ theo khả năng giả lập joins.

### 5.2. Một ví dụ kiểm soát tham chiếu

Trong PostgreSQL:

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES customers(customer_id),
    amount_cents BIGINT NOT NULL
        CHECK (amount_cents >= 0)
);
```

`REFERENCES` ràng buộc orders không tham chiếu customer không tồn tại, trong phạm vi semantics và transaction của RDBMS.

Trong MongoDB, có thể lưu `customerId` trong order, nhưng việc ngăn orphan reference cần application logic và/hoặc transaction/reconciliation phù hợp. Nếu đây là invariant trọng yếu và quan hệ thay đổi liên tục, RDBMS có thể đơn giản hơn.

### 5.3. Đừng kết luận SQL luôn nhanh hơn mọi join

SQL query planners, indexes và relational constraints rất mạnh, nhưng một RDBMS cũng có thể chậm khi query/index/schema được thiết kế kém. Tương tự, `$lookup` MongoDB có thể hợp lý trên bounded datasets với index tốt.

Đánh giá bằng **representative queries + data shape + p95/p99 + vận hành**, không bằng một benchmark đơn lẻ hoặc khẩu hiệu “SQL vs NoSQL”.

### 5.4. Nếu RDBMS đã là source of truth

Không đồng bộ toàn bộ dữ liệu từ PostgreSQL sang MongoDB chỉ vì team mới thích document model. Hãy trả lời:

- Use case nào không thể phục vụ hợp lý bằng PostgreSQL?
- Có thể tạo view/materialized view, JSONB column hoặc index trước không?
- MongoDB có là primary cho một bounded context mới, hay chỉ là read projection?
- Ai chịu trách nhiệm consistency và gap recovery?
- Chi phí thêm cluster/outbox/CDC có được lợi ích bù đắp không?

**Một hệ thống hiện hữu vận hành tốt không cần thêm database chỉ để dùng công nghệ mới.**

## 6. Khi nào MongoDB kết hợp PostgreSQL/MySQL là hợp lý?

### 6.1. Tách bounded contexts theo nguồn sở hữu

Ví dụ:

```text
                 API Gateway
                     |
           +---------+---------+
           |                   |
      Catalog Service      Billing Service
           |                   |
       MongoDB             PostgreSQL
     products / offers    invoices / ledger
           |                   |
           +------ Events -----+
                     |
              Read projections
```

Catalog có attributes phong phú và đổi nhanh; Billing cần transactional ledger, constraints và SQL integration. Mỗi service sở hữu writes của database mình.

**Nguyên tắc:** database ownership theo bounded context tốt hơn để mọi service cùng ghi vào mọi database.

### 6.2. Tránh transaction xuyên hai database khi chưa thật cần

Một nghiệp vụ:

```text
1. Insert product into MongoDB
2. Insert billing record into PostgreSQL
```

Nếu bước 1 thành công, bước 2 thất bại, dữ liệu tạm thời không nhất quán. MongoDB transaction chỉ bao trùm MongoDB; PostgreSQL transaction chỉ bao trùm PostgreSQL. Hai transaction riêng không tạo atomicity toàn hệ.

Các hướng xử lý:

- Chọn **một source of truth** cho một sự kiện nghiệp vụ.
- Dùng outbox/event-driven projection để hệ còn lại nhận bản sao.
- Với một workflow thực sự chạm hai owners, dùng saga/compensation với trạng thái trung gian.
- Nếu cần invariant synchronous không thể chia, cân nhắc đưa bước ghi vào một hệ quản trị cùng transaction boundary.

### 6.3. Có thể dùng MongoDB làm projection của RDBMS

Ví dụ accounting/PostgreSQL là nguồn sự thật cho invoices, MongoDB lưu read model:

```javascript
{
  _id: "invoice-123",
  customerId: "customer-9",
  invoiceNumber: "INV-123",
  amountCents: NumberLong("450000"),
  status: "PAID",
  searchTokens: ["INV-123", "customer-9"],
  sourceVersion: NumberLong("18"),
  projectedAt: ISODate("2026-11-14T04:30:00Z")
}
```

Khi nhận event:

- Chỉ writer thuộc Billing cập nhật PostgreSQL.
- MongoDB projector upsert theo invoice ID.
- `sourceVersion` ngăn event cũ ghi đè event mới.
- Projection có thể rebuild khi missing events.
- Không cho API ghi trực tiếp vào projection và coi đó là thay đổi invoice thật.

### 6.4. Có thể dùng RDBMS làm projection của MongoDB

Ngược lại, MongoDB có thể là source of truth cho catalog/orders, PostgreSQL chứa reporting tables phục vụ SQL BI.

Hai chiều đều hợp lệ khi **ownership rõ**, nhưng không nên thiết kế hai database “đều là primary” cho cùng một field mà không có conflict-resolution protocol.

## 7. MongoDB và Redis: cache không phải bản sao giao dịch tự nhiên

### 7.1. Khi Redis có ích

Redis thường được cân nhắc cho:

- Cache các kết quả đọc nóng, TTL ngắn.
- Session/cache state nếu yêu cầu phù hợp.
- Rate limiting và lightweight counters với tính đúng đắn được thiết kế riêng.
- Queues/streams khi workload và durability semantics tương thích.
- Đọc với độ trễ rất thấp, giảm load primary database.

Không cần Redis ngay lập tức nếu MongoDB index đã đủ SLO và cluster chưa chịu read pressure đáng kể.

### 7.2. Cache-aside

```text
            Application
                |
        GET product by ID
                |
           Redis cache?
             /       \
          HIT        MISS
           |           |
         return     MongoDB read
                       |
                    cache set
                       |
                     return
```

Một flow:

1. Read từ cache theo key có tenant/version.
2. Miss thì read MongoDB.
3. Cache result với TTL.
4. Khi update MongoDB thành công, invalidate cache.
5. Khi cache outage, fallback về MongoDB có backpressure.

### 7.3. Race khó nhận ra

```text
T1 Reader misses cache, reads old product from MongoDB
T2 Writer updates product in MongoDB
T3 Writer invalidates Redis key
T4 Reader caches old product
```

Tại T4, cache lại chứa dữ liệu cũ **sau** khi invalidate. Xử lý có thể bao gồm:

- Versioned cache keys.
- CAS/version khi set cache.
- TTL ngắn + stale-data budget.
- Invalidation event với version.
- Single-flight/cache locking khi phù hợp.
- Tránh cache những fields cần strong consistency.

Không chỉ nói “update database rồi DEL Redis là luôn nhất quán”.

### 7.4. Không đặt tiền/số lượng tồn kho quan trọng chỉ trong cache

Nếu Redis là nguồn duy nhất của một số dư mà persistence/recovery không đáp ứng hợp đồng kinh doanh, việc restart/eviction/failover có thể phá invariant.

Nếu chỉ cache balance từ MongoDB, phải xác định stale read có được phép khi ra quyết định giao dịch không. Với charge/settlement, thường cần xác nhận trên authoritative store bằng atomic operation/transaction.

### 7.5. Redis làm tăng vận hành

Thêm Redis là thêm:

- Cache keys và versioning.
- Eviction/TTL policy.
- Memory sizing.
- Warm-up và cache stampede.
- Backup/failover theo mục đích.
- Security/credentials.
- Consistency/correctness tests.
- Fallback behavior khi Redis unavailable.

**Chỉ thêm nếu lợi ích latency/cost rõ hơn chi phí này.**

## 8. MongoDB và Elasticsearch/OpenSearch: tìm kiếm chuyên sâu

### 8.1. Khi search engine chuyên dụng hữu ích

Nếu cần:

- Full-text search nhiều trường.
- Analyzer/tokenization tiếng Việt.
- Relevance ranking, fuzzy, synonym, autocomplete.
- Facets/phân tích nhiều chiều phục vụ search UI.
- Highlighting và complex scoring.
- Search workload độc lập lớn so với OLTP.
- Tính năng search/vector/hybrid đặc thù theo engine.

một công cụ như OpenSearch hoặc Elasticsearch có thể phù hợp.

### 8.2. Nhưng MongoDB cũng có search

Trước khi thêm search cluster, kiểm:

- Compound/text indexes MongoDB cơ bản có đáp ứng không?
- MongoDB Search/Atlas Search có sẵn trên tier/region/phiên bản không?
- Search features có đủ cho product team không?
- Khi dùng search tích hợp, liệu vẫn đáp ứng SLO và khả năng mở rộng độc lập không?

Không viết “MongoDB không hỗ trợ full-text” hoặc “muốn vector search bắt buộc dùng engine khác” mà không xét sản phẩm/triển khai cụ thể.

### 8.3. Search index nên là **derived state**

```text
MongoDB (products authoritative)
               |
          Change stream / Outbox
               |
               v
        Search indexer
               |
       OpenSearch index
               |
        Search API / UI
```

Một search hit không tự chứng minh product còn tồn tại/được bán. Các thao tác mua hàng cần kiểm tra trạng thái trên source of truth.

### 8.4. Sự kiện đến trễ và thứ tự cập nhật

```text
Product P version 12 -> price 100
Product P version 13 -> price 120
Events arrive search indexer as: 13, then 12
```

Nếu indexer ghi tùy ý, giá search bị lùi về 100. Hướng xử lý:

- Phát `sourceVersion` hoặc monotonic event sequence theo document.
- Index/update với kiểm soát version.
- Deduplicate events bằng event ID.
- Ghi tombstone/version cho deletes.
- Có backfill/reindex và kiểm index lag.
- Xử lý out-of-order và duplicate deliveries trong consumer.

### 8.5. Indexing không nên nằm trong transaction của đơn hàng

Không đưa HTTP call tới OpenSearch vào MongoDB transaction rồi mong cả hai atomic. Nên commit authoritative product và outbox trong MongoDB, sau đó indexer cập nhật search index.

Nếu search engine lỗi, product write có thể vẫn thành công; search UI hiển thị dữ liệu cũ trong một khoảng có kiểm soát. Nếu nghiệp vụ không chấp nhận độ trễ đó, xem lại ranh giới dữ liệu hoặc thiết kế synchronous verification.

## 9. MongoDB và Kafka/message broker: sự kiện khác dữ liệu hiện tại

### 9.1. Vai trò khác nhau

MongoDB lưu trạng thái hiện tại và lịch sử document theo mô hình thiết kế. Broker như Kafka phục vụ event log/stream distribution, retention và consumer offsets/partitioning theo đặc trưng sản phẩm.

```text
                  MongoDB
              Order source of truth
                      |
             Outbox / CDC relay
                      |
                      v
                 Kafka topic
                 /    |    \
                v     v     v
          Search   Billing  Analytics
```

Đây là kiến trúc có ích khi nhiều subscribers độc lập, cần buffer và scale event processing. Nhưng một ứng dụng nhỏ với một background worker có thể dùng change stream trực tiếp, không cần broker.

### 9.2. Change streams không tương đương Kafka consumer groups

MongoDB change streams:

- Đọc các thay đổi từ oplog history.
- Sử dụng resume token.
- History hữu hạn theo oplog.
- Mỗi watcher có thể nhận cùng event.
- Không tự cung cấp phân phối workload consumer group như Kafka.

Kafka:

- Lưu records theo topic/partition và retention policy.
- Consumer groups quản lý partition assignment/offset.
- Cần thiết kế key/ordering và retry/DLQ.
- Có chi phí broker, topics, schema evolution và operations.

Hai hệ thống không tự thay thế lẫn nhau. Một CDC pipeline có thể kết hợp cả hai.

### 9.3. Domain event khác database change

Một change event:

```javascript
{
  operationType: "update",
  documentKey: { _id: "order-123" },
  updateDescription: {
    updatedFields: { status: "PAID" }
  }
}
```

chỉ cho biết document thay đổi. Một domain event:

```javascript
{
  eventId: "order-123:paid:version-7",
  eventType: "OrderPaid",
  orderId: "order-123",
  paymentId: "payment-1",
  occurredAt: ISODate("2026-11-14T04:00:00Z"),
  schemaVersion: NumberInt(1)
}
```

mô tả **ý định nghiệp vụ**. Không phải mọi update status đều là thanh toán thực tế; logic chuyển đổi change event thành domain event phải dựa vào invariant và source fields thích hợp.

### 9.4. Khi không có broker vẫn phải quan tâm reliability

Một consumer đọc trực tiếp change stream vẫn cần:

- Resume token checkpoint bền vững.
- Xử lý idempotent.
- Kiểm thời gian oplog còn lịch sử.
- Phục hồi khi `ChangeStreamHistoryLost`.
- Graceful shutdown.
- Ownership nếu nhiều pods.
- Cơ chế re-bootstrap nếu token không còn.

Không lấy “không thêm Kafka” làm lý do bỏ qua các quy tắc delivery.

## 10. MongoDB và data warehouse/lakehouse: OLTP khác OLAP

### 10.1. Phân biệt mục tiêu

**OLTP (online transaction processing)** tập trung vào:

- Point reads/writes.
- Truy vấn theo key/tenant.
- Latency thấp và concurrency cao.
- Tính đúng đắn của business operations.
- Working set nóng và indexes.

**OLAP (online analytical processing)** tập trung vào:

- Quét khối lượng lớn theo cột/partition.
- Aggregations, joins nhiều dataset.
- Dữ liệu lịch sử dài hạn.
- Analysts/BI/report scheduling.
- Cost tối ưu cho batch/scan.

MongoDB aggregation phù hợp nhiều báo cáo; không có quy tắc “cứ `$group` là phải chuyển warehouse”. Nhưng nếu analytical queries thường xuyên scan dữ liệu giao dịch khổng lồ và gây tăng p99 API, tách OLAP có thể cần thiết.

### 10.2. Kiến trúc tách analytical copy

```text
Operational APIs
      |
      v
   MongoDB
      |
      +------ CDC / export / ETL ------+
                                      |
                                      v
                                 Data Lake /
                                Data Warehouse
                                      |
                            BI / SQL / ML / Reports
```

Dữ liệu phân tích là **bản sao có độ trễ và phiên bản schema**, không phải authoritative write path cho order.

### 10.3. Chọn refresh model

| Cách đồng bộ | Phù hợp | Rủi ro |
| --- | --- | --- |
| Nightly batch export | Báo cáo theo ngày | Data stale, job fail |
| Incremental CDC | Near-real-time analytics | Event replay, ordering, schema drift |
| Snapshot + CDC | Bootstrap dataset lớn | Gap giữa snapshot và stream |
| Scheduled aggregates | Dashboard giới hạn | Chênh lệch do late events |
| Recompute từ source | Đối soát định kỳ | Chi phí scan |

Phải định nghĩa rõ **freshness SLO**: “báo cáo doanh thu cập nhật sau tối đa 5 phút” khác với “số dư tài khoản luôn chính xác trước khi thanh toán”.

### 10.4. Đối soát analytical numbers

Số liệu có thể khác bởi:

- Timezone và cách xác định ngày.
- Cửa sổ dữ liệu/watermark.
- Late-arriving events.
- Deletes/updates và event retraction.
- Duplicates do CDC retry.
- Different exchange rates/tax rules.
- Aggregation semantics của trạng thái canceled/refunded.

Không so hai dashboard rồi tự kết luận database nào “sai” trước khi thống nhất định nghĩa metric.

## 11. MongoDB và object storage: không phải mọi byte đều là document

### 11.1. Ảnh và file dung lượng lớn

MongoDB document có **giới hạn 16 MiB**. Dù MongoDB có GridFS cho files vượt giới hạn này, trong nhiều ứng dụng web, object storage (S3-compatible, Google Cloud Storage, Azure Blob, v.v.) là lựa chọn phù hợp cho ảnh/video/tệp và CDN.

Ví dụ MongoDB giữ metadata:

```javascript
{
  _id: "product-SKU-1",
  title: "Ghế làm việc",
  assets: [
    {
      assetId: "asset-100",
      objectKey: "products/SKU-1/main.webp",
      contentType: "image/webp",
      sizeBytes: NumberLong("310000"),
      checksumSha256: "hash-of-file",
      status: "READY"
    }
  ]
}
```

Nội dung binary nằm ở object storage, MongoDB giữ key/reference và metadata.

### 11.2. Hai hệ thống không có transaction chung

Flow upload:

```text
Client uploads object
          |
          v
Object storage write
          |
          v
MongoDB metadata write
```

Nếu object upload thành công nhưng MongoDB insert thất bại, có orphan file. Nếu metadata ghi trước nhưng upload thất bại, API có reference tới file chưa tồn tại.

Cần state machine:

```text
INITIATED -> UPLOADING -> READY
                 |
                 +------> FAILED / CLEANUP_PENDING
```

Đưa cleanup/orphan reconciliation vào runbook, không giả định commit hai hệ thống atomic.

### 11.3. Kiểm quyền đối với objectKey

Object key không tự là authorization token. API cần xác minh tenant/ownership khi tạo signed URL, upload/download và thay metadata.

Không lưu signed URLs lâu dài nếu có thời hạn; lưu object key/asset ID và tạo URL khi được phép.

## 12. MongoDB kết hợp graph database hoặc vector store

### 12.1. Graph: khi traversal nhiều bậc là workload chính

Một nền tảng social/network fraud phải truy vấn:

- Bạn của bạn của bạn.
- Đường đi ngắn nhất.
- Subgraph/phát hiện vòng.
- Các kết nối nhiều bậc thay đổi liên tục.

MongoDB có `$graphLookup` và document references, có thể đáp ứng một số use case. Nhưng nếu graph traversals sâu, biến đổi, với số lượng cạnh lớn là workload chủ đạo, graph database chuyên dụng có thể đáng thử.

Không chọn graph database chỉ vì ứng dụng có `userId` tham chiếu từ order.

### 12.2. Vector search

Nếu ứng dụng cần semantic search/RAG:

- MongoDB Vector Search khả dụng ở một số deployment/tier và có các yêu cầu indexes/config riêng.
- Vector database chuyên dụng có thể được đánh giá nếu cần scale, filtering, model operations hoặc recall/latency đặc thù.
- OpenSearch/Elasticsearch và một số RDBMS cũng có vector capabilities theo extension/product.
- Kết quả phụ thuộc embedding model, chunking, filter selectivity, recall target, p95/p99, costs và data privacy.

Không tuyên bố một engine “luôn tốt nhất” cho vector search. Làm prototype với dữ liệu đại diện, ground-truth relevance và load test.

### 12.3. Vector/index là derived state

Nếu content được sửa/xóa trong MongoDB nhưng vector index chưa cập nhật, RAG có thể trả lời dựa trên tài liệu cũ hoặc đã bị revoke. Cần event version, delete propagation, ACL filter, freshness SLO và reindex/reconciliation.

## 13. Bảng tổng quan: vai trò phù hợp của từng hệ thống

| Thành phần | Vai trò thường hợp lý | Dữ liệu gốc? | Cần đặc biệt chú ý |
| --- | --- | --- | --- |
| MongoDB | Document OLTP, nested entities, aggregation, change stream | Có thể là nguồn gốc | Index, data model, transactions |
| PostgreSQL/MySQL | Relational transactions, FK, SQL workload | Có thể là nguồn gốc | Joins, constraints, migrations |
| Redis | Cache, ephemeral state, rate limits | Thường không cho dữ liệu quan trọng | Staleness, eviction, persistence |
| OpenSearch/Elasticsearch | Full-text/relevance/facets | Thường là projection | Reindex, ordering, lag |
| Kafka/broker | Event distribution/retention/buffering | Event log có thể là source theo kiến trúc | Offsets, schema, partitions |
| Warehouse/lakehouse | BI/OLAP, long-history analytics | Thường analytical copy | Freshness, late data, cost |
| Object storage | Large files/media, archival blobs | Là source cho binary content | Orphan cleanup, ACL, checksum |
| Graph database | Relationship traversal workload | Tùy bounded context | Sync edges, identifiers |
| Vector store | Semantic similarity retrieval | Thường derived index | Recall, ACL, stale embeddings |

Bảng mô tả **vai trò**, không phải danh sách bắt buộc phải mua. Một sản phẩm có thể không cần Redis, Kafka, warehouse hay search cluster nếu MongoDB/đường ứng dụng đã đáp ứng.

## 14. Nguồn sự thật và bản sao: nguyên tắc quan trọng nhất khi dùng nhiều database

### 14.1. Mỗi trường dữ liệu nên có một nơi sở hữu writes

Giả sử product `priceCents` xuất hiện ở:

- MongoDB product document.
- Redis cache.
- OpenSearch search index.
- Warehouse reporting table.

Ai được phép quyết định giá mới? Nếu mọi thành phần đều cập nhật và đẩy ngược nhau, sẽ xảy ra conflict khó kiểm soát.

Một lựa chọn rõ:

```text
Catalog Service owns price
             |
             v
MongoDB authoritative product
             |
             +----> Redis cache (derived)
             +----> OpenSearch (derived)
             +----> Warehouse (derived)
```

Không cho web admin sửa trực tiếp OpenSearch price rồi kỳ vọng MongoDB tự đồng bộ ngược.

### 14.2. Authority không nhất thiết là một database cho toàn doanh nghiệp

Có thể:

- Catalog sở hữu product attributes trong MongoDB.
- Billing sở hữu invoices/payments trong PostgreSQL.
- Identity service sở hữu user credentials ở identity provider.
- Media service sở hữu file bytes trong object storage.
- Search phục vụ indexed copy.

**Một chủ sở hữu cho từng aggregate/business fact**, không phải “một database làm source of truth cho mọi hệ thống”.

### 14.3. Quy định chiều dữ liệu và contract

Trong tài liệu thiết kế:

```yaml
dataProduct: ProductCatalog
owner: CatalogService
authoritativeStore: MongoDB/products
eventContract: ProductChanged/v2
derivedStores:
  - Redis/product-cache
  - OpenSearch/product-index
  - Warehouse/dim_products
freshnessSlo:
  redis: "seconds"
  search: "under 1 minute"
  analytics: "under 30 minutes"
rebuildSource: MongoDB/products + versioned events
conflictResolution: authoritative source version wins
```

Đây là YAML thiết kế ứng dụng, **không phải cấu hình MongoDB tự nhận**. Các SLO chỉ minh họa, phải đo/thống nhất theo sản phẩm.

## 15. Cần loại consistency nào?

Không phải mọi API cần cùng consistency.

### 15.1. Phân loại theo hậu quả

| Use case | Ví dụ | Consistency thường cần |
| --- | --- | --- |
| Financial decision | Charge payment, withdraw, settle | Cực kỳ chặt chẽ, invariant tại source |
| Inventory reservation | Đặt số lượng còn lại | Atomic conditional update/transaction |
| Product detail | Tên, mô tả, ảnh | Có thể chấp nhận cache stale ngắn |
| Search results | Index sản phẩm | Eventual consistency có freshness SLO |
| Dashboard | Doanh thu theo giờ | Batch/near-real-time tùy business |
| User authentication | Session/permissions | Không được stale theo cách cấp quyền sai |
| Audit/retention | Lịch sử nghiệp vụ | Durability, immutability policy, backup |
| Recommendations | Gợi ý sản phẩm | Có thể chấp nhận dữ liệu trễ |

### 15.2. Strong consistency thường nằm ở authoritative write path

Nếu quyết định giao dịch dựa trên số lượng tồn kho, không lấy một Redis cache stale rồi tự trừ với giả định nguồn chính sẽ đồng ý.

Trong MongoDB, có thể dùng:

```javascript
db.inventory.updateOne(
  {
    _id: "SKU-1",
    available: { $gte: 2 }
  },
  {
    $inc: {
      available: -2,
      reserved: 2
    }
  }
);
```

Đây là single-document atomic conditional update. Nhưng nếu order/stock/ledger ở các collections khác nhau và phải đồng bộ, cần transaction/compensation theo business boundary. Nếu tồn kho ở PostgreSQL, hãy thực hiện invariant tại PostgreSQL, không trong Redis.

### 15.3. Read-your-writes và secondary lag

MongoDB replica set cung cấp read concern/write concern/read preference và causal consistency theo session khi đủ điều kiện.

Một `w:"majority"` acknowledgment không đồng nghĩa **mọi secondary query sẽ đọc ngay version mới**, đặc biệt nếu secondary apply còn lag. Với MongoDB 8.0, majority acknowledgment semantics có thay đổi liên quan secondary oplog durability và việc apply vào collection.

Nếu API vừa cập nhật status rồi đọc ngay để trả response, thiết kế đường đọc bảo đảm visibility cần thiết; không mặc định readPreference secondary là read-your-writes.

### 15.4. Consistency xuyên DB không miễn phí

```text
MongoDB product price=120
Redis cache price=100
Search index price=100
Warehouse price=80
```

Đây có thể là tình trạng tạm thời phù hợp freshness SLO, hoặc là incident nếu ràng buộc yêu cầu mọi nơi phản ánh ngay.

Cần phân biệt **inconsistency được phép trong window** và **vi phạm correctness** trước khi thiết kế đồng bộ.

## 16. Dual-write problem: rủi ro lớn nhất của polyglot persistence

### 16.1. Hai writes rời nhau có nhiều trạng thái lỗi

Sai kiểu:

```java
mongoProducts.replaceOne(...);
searchClient.index(...);
```

Có thể xảy ra:

1. MongoDB success, search failure.
2. MongoDB timeout nhưng thực tế success, search được/không được gọi.
3. Search success, MongoDB failure nếu thứ tự đảo.
4. Cả hai success nhưng response API bị mất.
5. Events/new updates đến không đúng thứ tự.
6. Process crash giữa hai writes.

Không có một transaction chung giữa MongoDB và OpenSearch/Redis/Kafka trong cách gọi thông thường.

### 16.2. Không sửa bằng cách đảo thứ tự

Đổi:

```text
MongoDB -> Redis
```

thành:

```text
Redis -> MongoDB
```

không giải quyết atomicity, chỉ thay vị trí crash window.

### 16.3. Chọn hệ gốc rồi đồng bộ derived stores

```text
                 Business request
                        |
                        v
             Authoritative DB commit
                        |
                        v
                Durable change/event
                        |
                   Async delivery
                 /      |       \
                v       v        v
             Cache    Search    Analytics
```

Nếu derived store lỗi, primary business write không bị biến thành “không rõ đã thành công chưa” chỉ vì search indexing thất bại, trừ khi business contract cố ý buộc điều đó.

## 17. Transactional outbox khi MongoDB làm nguồn gốc

### 17.1. Mẫu outbox

Trong **cùng MongoDB transaction**, ghi business document và outbox:

```text
begin transaction
    |
    +--> update products
    |
    +--> insert outbox event
    |
commit
    |
relay watches/polls outbox
    |
publish to broker/search/cache worker
```

Nếu commit thành công, business state và outbox cùng tồn tại; nếu abort, cả hai rollback. Nó tránh khoảng trống “business committed nhưng không có record nào biết cần sync”.

### 17.2. Một event document

```javascript
{
  _id: "product-SKU-1:version-8",
  aggregateType: "Product",
  aggregateId: "SKU-1",
  aggregateVersion: NumberLong("8"),
  eventType: "ProductChanged",
  eventSchemaVersion: NumberInt(1),
  payload: {
    title: "Ghế làm việc",
    priceCents: NumberLong("24500000")
  },
  state: "NEW",
  createdAt: ISODate("2026-11-14T04:00:00Z")
}
```

Lưu ý:

- `_id` là event identity ổn định và unique.
- `aggregateVersion` dùng để ngăn replay cũ ghi đè mới.
- Payload chỉ chứa dữ liệu consumers cần; tránh phát PII quá mức.
- Có cơ chế upgrade event schema và retention/replay.
- Không coi `state:"SENT"` là exactly-once external delivery nếu ACK mất.

### 17.3. Relay có thể giao event nhiều lần

```text
Read outbox E8
      |
Publish E8 to broker
      |
ACK lost
      |
Relay retries E8
      |
Broker/consumer may see duplicate
```

Cần consumer **idempotent**:

- Dedup theo event ID.
- Unique inbox key.
- Upsert projection bằng aggregate ID.
- Compare incoming version với version đã xử lý.
- Retry/backoff và DLQ.
- Theo dõi backlog/lag.

Transactional outbox giúp không mất **ý định phát event** sau business commit, nhưng tự nó không loại bỏ duplicates trong delivery.

### 17.4. Có thể dùng change streams làm relay

MongoDB change streams có thể theo dõi outbox inserts và checkpoint resume token. Nhưng:

- Cần replica set/sharded cluster.
- Oplog history có thời hạn.
- Resume token phải lưu sau khi side effects đã xử lý thành công.
- Khi mất history phải backfill/reconcile.
- Có nhiều pods cần ownership/fencing hoặc partitioning.
- Nếu outbox còn records `NEW`, một polling/recovery path có thể giúp phục hồi những events bị bỏ do history loss.

Thiết kế outbox với durable state/retry là **một workflow**; không coi change stream một mình là broker có retention vô hạn.

## 18. CQRS: read model khác write model khi có lợi ích rõ

### 18.1. Khái niệm

**CQRS (Command Query Responsibility Segregation)** tách mô hình ghi theo invariants khỏi mô hình đọc tối ưu cho truy vấn.

```text
       Commands                        Queries
           |                              |
           v                              v
      Write Model                    Read Model
       MongoDB                        MongoDB /
           |                         Search / SQL
           |
        Outbox events
           |
           +----------------------------->+
```

Không nhất thiết phải dùng hai công nghệ. CQRS có thể dùng **hai collections MongoDB** với schemas khác nhau.

### 18.2. Khi tách read model có ích

Một API cần hiển thị dashboard đơn hàng gồm:

- Tên khách hàng.
- Tên các sản phẩm tại thời điểm mua.
- Trạng thái thanh toán.
- Tổng tiền.
- Kết quả vận chuyển.
- Sorting/filtering theo nhiều trường.

Thay vì mỗi request `$lookup` qua 4 collections, có thể xây projection:

```javascript
{
  _id: "order-123",
  tenantId: "store-A",
  customerName: "Khách hàng demo",
  productNames: ["Sổ tay", "Bút"],
  orderTotalCents: NumberLong("600000"),
  paymentStatus: "PAID",
  fulfillmentStatus: "PACKED",
  sourceVersion: NumberLong("12"),
  projectedAt: ISODate("2026-11-14T04:00:00Z")
}
```

Read model có thể lag. Giao diện phải biết freshness SLO và có thể xác nhận lại tại source khi ra quyết định không được stale.

### 18.3. CQRS có chi phí

- Event schemas/versioning.
- Backfill.
- Rebuild khi projection sai.
- Event delivery, idempotency, ordering.
- Metrics lag và reconciliation.
- Consistency contract ở API.
- Dữ liệu trùng làm tăng storage.

Nếu một index trên source collection đã giải quyết query, tách projection có thể quá phức tạp.

## 19. Identity và version: hai điều kiện để đồng bộ an toàn

### 19.1. IDs phải ổn định

Một record product có thể xuất hiện ở nhiều stores. Cần một ID chung:

```text
MongoDB _id:      SKU-1
Redis key:        product:SKU-1:v8
Search document:  SKU-1
Warehouse key:    SKU-1
```

Không chuyển sang ID khác ở mỗi tầng nếu không có mapping rõ, vì sẽ khó deduplicate, delete và reconcile.

### 19.2. Version chống ghi lùi

Ví dụ projection hiện tại:

```javascript
{
  _id: "SKU-1",
  sourceVersion: NumberLong("11"),
  title: "Ghế A"
}
```

Indexer nhận event version 12 trước version 10. Nếu có conditional update:

```javascript
db.product_projection.updateOne(
  {
    _id: "SKU-1",
    sourceVersion: { $lt: NumberLong("12") }
  },
  {
    $set: {
      sourceVersion: NumberLong("12"),
      title: "Ghế B"
    }
  }
);
```

vẫn cần xử lý **document chưa tồn tại** và race khi upsert đồng thời. Một phương án là phân phối events theo aggregate ID cho một ordered consumer, hoặc dùng transaction/CAS và unique `_id` với retry phân loại duplicate. Không dùng một `upsert:true` ngây thơ với filter chứa `sourceVersion:$lt` mà không xét khả năng insert duplicate `_id`.

### 19.3. Delete cần tombstone hoặc version

Nếu delete chỉ xóa search document ngay, event cũ đến muộn có thể tạo lại sản phẩm đã xóa. Lưu tombstone:

```javascript
{
  _id: "SKU-1",
  sourceVersion: NumberLong("13"),
  deleted: true,
  deletedAt: ISODate("2026-11-14T05:00:00Z")
}
```

Consumer bỏ qua event version thấp hơn 13. Tombstone retention phải đủ cho retry/replay window và data governance. Nếu xóa dữ liệu vì yêu cầu privacy, retention của tombstone/payload cần được thiết kế để không giữ PII không cần thiết.

### 19.4. Version phải có semantics rõ

- `updatedAt` không luôn là version an toàn vì clock skew/precision.
- `ObjectId` có timestamp nhưng không phải global ordering guarantee.
- `clusterTime` không tự là business version của từng aggregate.
- Sequence theo aggregate do authoritative writer quản lý thường dễ hiểu hơn.
- Trong multi-region/multi-writer, conflict resolution phức tạp hơn một số nguyên.

Không tự dùng `Date.now()` làm global version cho mọi database.

## 20. Bảo đảm atomicity tại source trước khi phát sự kiện

### 20.1. Single-document atomicity

Một command đổi giá và tăng version:

```javascript
db.products.updateOne(
  {
    _id: "SKU-1",
    tenantId: "store-A",
    version: NumberLong("7")
  },
  {
    $set: {
      priceCents: NumberLong("25000000"),
      updatedAt: new Date()
    },
    $inc: {
      version: 1
    }
  }
);
```

Nếu cùng product document chứa đủ state, update atomic là cơ sở tốt. Nhưng nếu outbox event nằm ở collection khác, muốn bảo đảm cả product update và outbox insert cùng commit thường cần transaction.

### 20.2. Transaction trong MongoDB

```javascript
const session = db.getMongo().startSession();
const sdb = session.getDatabase("commerce");

try {
  session.withTransaction(() => {
    // Update product and insert outbox event.
    // Mọi operation phải dùng cùng session.
    // Không gọi external services trong callback.
  });
} finally {
  session.endSession();
}
```

Đây là skeleton; triển khai thật phải xử lý version, transaction retries, write concern, session lifecycle, lệnh được hỗ trợ và namespace. Callback có thể retry; external side effects trong callback có thể bị lặp.

### 20.3. Không dùng transaction bao toàn business workflow

Một quy trình order → payment gateway → shipping provider có thể kéo dài phút/giờ. Không giữ MongoDB transaction mở trong suốt khoảng đó.

Dùng **saga/state machine**:

```text
OrderCreated
    |
ReserveInventory
    |
RequestPayment
    |
PaymentConfirmed/Failed
    |
CreateShipment / ReleaseInventory
```

Mỗi bước có transaction local, idempotency key, retry, timeout và compensation. Sự chuyển tiếp trạng thái phải có audit/recovery.

## 21. Quy tắc chọn định dạng dữ liệu và schema giữa các hệ thống

### 21.1. BSON không giống JSON hay SQL types

MongoDB có:

- Int32, Int64, Double, Decimal128.
- Date, Timestamp.
- ObjectId.
- Binary UUID với subtype.
- Embedded documents/arrays.
- Null/missing phân biệt.

Khi chuyển sang SQL, Redis JSON, Kafka JSON hoặc search index:

- `NumberLong("9007199254740993")` có thể mất chính xác nếu đi qua JavaScript Number.
- Decimal128 không nên bị chuyển thành Double cho tiền tệ.
- ObjectId không tự bằng String ID.
- BSON Date là instant UTC, không giữ timezone gốc.
- Missing khác explicit null.
- Mảng object có semantics khác SQL normalized rows.

### 21.2. Hợp đồng mapping nên có bảng

| MongoDB field | Source type | Projection type | Quy tắc |
| --- | --- | --- | --- |
| `_id` | String hoặc ObjectId | String key | Canonical mapping ổn định |
| `amountCents` | Int64 | BIGINT/long | Không qua floating point |
| `priceDecimal` | Decimal128 | DECIMAL(p,s) | Kiểm precision/scale |
| `createdAt` | BSON Date | TIMESTAMP WITH TIME ZONE | Giữ instant UTC |
| `tags` | Array String | Array/child rows | Quyết định order/duplicates |
| `optionalField` | Missing/null/String | Nullable + presence marker | Không gộp nếu nghiệp vụ cần phân biệt |
| `schemaVersion` | Int32 | Integer | Versioned evolution |

### 21.3. Event schema thay đổi như thế nào?

Event v1:

```javascript
{
  eventType: "ProductChanged",
  schemaVersion: 1,
  payload: { price: "120.00" }
}
```

Event v2:

```javascript
{
  eventType: "ProductChanged",
  schemaVersion: 2,
  payload: { priceCents: NumberLong("12000") }
}
```

Consumer cần:

1. Có thể đọc v1 và v2 trong giai đoạn chuyển.
2. Có mapping chính xác đơn vị và decimal.
3. Không viết code chỉ nhìn field mới rồi bỏ event cũ trong backlog.
4. Có backfill/replay tests cho retained events.
5. Xác định khi nào ngừng hỗ trợ v1.

Một stream contract có thể khó migrate hơn một collection vì consumers deploy độc lập.

## 22. Backfill khi thêm derived store lần đầu

### 22.1. Sai lầm: scan xong rồi mới bắt CDC

```text
T0 Snapshot MongoDB products starts
T1 Product SKU-1 updated
T2 Snapshot finishes
T3 Search indexer starts watching changes
```

Thay đổi ở T1 có thể bị bỏ qua. Đây là **snapshot-to-stream gap**.

### 22.2. Một quy trình có checkpoint

```text
Establish CDC start boundary
           |
Start capturing/buffering changes
           |
Scan authoritative snapshot in batches
           |
Build derived projection with version checks
           |
Replay buffered/new events
           |
Reconcile counts, checksums, versions
           |
Cut over read traffic when lag acceptable
```

Chi tiết phụ thuộc MongoDB version, oplog window, topology, tool CDC, transaction/snapshot strategy và hệ đích. Không giả định mở change stream là đủ nếu backfill nhiều ngày và oplog chỉ giữ vài giờ.

### 22.3. Nếu mất oplog history

Khi resume token không còn trong history, không được âm thầm “watch từ hiện tại” rồi tuyên bố search/warehouse đã nhất quán.

Cần:

- Phát alarm.
- Tạm dừng cutover nếu projection chưa đáng tin.
- Chọn rebootstrap hoặc reconcile theo source data.
- Thiết lập boundary mới không có gap.
- Lưu quyết định/audit.
- Theo dõi recovery progress.

### 22.4. Backfill nên có version/CAS

Nếu snapshot đọc version 5 nhưng CDC đã áp version 6, backfill không được ghi đè trở lại version 5. Cần ordered commit, conditional version compare hoặc reconcile after backfill.

## 23. Migration từ MongoDB-only sang polyglot theo nhiều giai đoạn

### 23.1. Giai đoạn 0 — Xác định nguyên nhân thật

Đừng thêm Redis vì có vài request chậm do index thiếu; đừng thêm search cluster vì query sử dụng `$regex` không tối ưu trên collection nhỏ.

Lấy:

- Top queries/slow queries.
- Explain `totalKeysExamined`/`totalDocsExamined`.
- p50/p95/p99 và throughput.
- CPU, memory, WiredTiger cache, disk latency.
- Query semantics cần thêm (relevance, fuzzy, facets...).
- Chi phí hiện tại và chi phí dự báo.
- Team support burden.

### 23.2. Giai đoạn 1 — Tối ưu MongoDB trước

Thử:

- Thiết kế compound indexes đúng query patterns.
- Projection để giảm payload.
- Bounded pagination/keyset.
- Rà soát embedding vs references.
- Tách hot/cold data hợp lý.
- Aggregation pipeline hợp lý.
- Materialized view trong MongoDB nếu phù hợp.
- Search capabilities của MongoDB trên deployment hiện có.
- Read/write concerns theo nghiệp vụ.

Không phải tối ưu bằng mọi giá; mục tiêu là biết **giới hạn nào thực sự buộc phải tách**.

### 23.3. Giai đoạn 2 — Thêm derived store ở chế độ shadow

```text
Production reads -> MongoDB
        |
     CDC/outbox
        |
        v
New Search/Cache/Read model (not serving users yet)
```

Dùng shadow store để:

- Build data.
- Reconcile versions/IDs.
- Đo lag và cost.
- Kiểm correctness.
- Thử rollback khi target unavailable.
- Đánh giá ACL/PII.

### 23.4. Giai đoạn 3 — Canary read traffic

Chỉ khi shadow đạt điều kiện:

- Chọn read-only cohort nhỏ.
- So kết quả và freshness.
- Giữ fallback sang authoritative read nếu policy cho phép.
- Đặt SLO và error budget.
- Bật feature flag để rollback routing.

Với search UI, khác biệt ranking có thể là expected; cần metric relevance/recall và product acceptance, không chỉ so JSON equality.

### 23.5. Giai đoạn 4 — Tăng tỷ lệ và vận hành

Sau canary:

- Scale target store.
- Mở metrics lag/backlog/version mismatches.
- Huấn luyện runbook cho on-call.
- Kiểm backup/reindex/recovery.
- Cập nhật security/retention.
- Kiểm chi phí thực tế vs dự kiến.
- Chỉ bỏ code path cũ khi có bằng chứng và rollback window.

## 24. Nếu muốn chuyển primary ownership sang hệ khác?

Đây là bài toán khó hơn thêm cache/search projection.

Ví dụ chuyển Orders authoritative từ MongoDB sang PostgreSQL:

```text
Old ownership: MongoDB orders
New ownership: PostgreSQL orders
```

Có các vấn đề:

- Schema mapping BSON → relational.
- Business constraints và ID mapping.
- Historical data/backfill.
- Concurrent writes và conflict.
- Cutover atomicity.
- API/client compatibility.
- Transactions/session semantics.
- Rollback sau khi có writes ở primary mới.

Một quy trình thường cần:

1. Mô tả ownership tại từng giai đoạn.
2. Dual-read/shadow compare nhưng không cho hai hệ cùng nhận authoritative writes tùy tiện.
3. Đồng bộ có checkpoint/version.
4. Quiesce/cutover hoặc protocol phân quyền writers.
5. Read-after-write validation.
6. Reconciliation/rollback plan đã thử.
7. Đánh dấu hệ cũ read-only cho giai đoạn chuyển.
8. Chỉ retire khi dữ liệu và consumers được xác nhận.

Không dùng “dual-write vĩnh viễn sang hai primary” làm giải pháp đơn giản cho bài toán ownership.

## 25. Một ví dụ đầy đủ: ứng dụng quản lý cho thuê

Giả sử ứng dụng có:

- `properties`: thuộc tính bất động sản đa dạng.
- `availability`: lịch còn trống/đặt chỗ.
- `bookings`: hợp đồng đặt thuê.
- `payments`: giao dịch và đối soát.
- `search`: tìm theo vị trí, tiện ích, giá, từ khóa.
- `analytics`: doanh thu theo khu vực/tháng.
- `photos`: ảnh/video bất động sản.

### 25.1. Phương án A — MongoDB là primary và chỉ dùng ít thành phần

```text
Web / Mobile
     |
API services
     |
MongoDB
  properties
  bookings
  availability
  payment references
  query indexes / aggregation
     |
Object storage for images
```

Khả thi khi:

- Đọc property theo document là workload chính.
- Booking invariants thực thi được bằng atomic conditional updates/transactions.
- Search/aggregation hiện có đáp ứng.
- Volume và SLO phù hợp.
- Đội muốn tối giản operations.

Không đặt toàn bộ payment gateway state vào document property; payment là bounded context khác với security/transaction contract riêng.

### 25.2. Phương án B — Polyglot theo vai trò

```text
                  API Gateway
                       |
             +---------+---------+
             |                   |
       Listing Service       Booking Service
             |                   |
          MongoDB           PostgreSQL
             |                   |
        Catalog events       Booking events
             |                   |
             +--------+----------+
                      |
             Event relay / broker
              /       |       \
             v        v        v
        Search idx   Redis    Warehouse
             |
        Search API
             
   Object storage <- Media Service
```

Phương án này có thể hợp lý khi:

- Listing attributes thay đổi mạnh.
- Booking cần relational constraints/integration.
- Search relevance/facets cần engine riêng.
- Analytics quét lịch sử lớn.
- Số lượng requests và team ownership đủ lớn để biện minh vận hành.

### 25.3. Booking không được quyết định chỉ từ search/cache

Search có thể báo phòng “còn trống” do projection chậm. Tại lúc đặt:

1. API gọi Booking authoritative service.
2. Service kiểm availability/invariant và giữ chỗ bằng atomic write/transaction.
3. Commit với durability phù hợp.
4. Phát event cập nhật search/cache.
5. Nếu event chậm, UI có thể hiển thị availability cũ, nhưng booking service **không oversell**.

Một chênh lệch hiển thị tạm thời có thể chấp nhận được; hai booking cùng chiếm một phòng/khung giờ có thể không.

### 25.4. Đừng chuyển dữ liệu người thuê qua mọi hệ

PII của người thuê không nên tự xuất hiện trong search index, cache và warehouse chỉ vì sync toàn bộ MongoDB document. Thiết kế projection tối thiểu:

```javascript
{
  propertyId: "property-123",
  city: "HCM",
  amenityTags: ["wifi", "parking"],
  nightlyPriceCents: NumberLong("750000"),
  availableFrom: ISODate("2026-12-01T00:00:00Z"),
  sourceVersion: NumberLong("30")
}
```

Không gửi customer phone, ID document, payment details vào search nếu không cần.

## 26. Một ví dụ thứ hai: IoT và time-series

Một hệ thống thu cảm biến:

```javascript
{
  sensorId: "sensor-100",
  observedAt: ISODate("2026-11-14T04:10:00Z"),
  temperatureC: 28.3,
  humidityPct: 70.0,
  siteId: "site-A"
}
```

### 26.1. MongoDB-only có thể đủ

- Time-series collections phù hợp nếu version/deployment hỗ trợ.
- Query theo sensor/time window.
- TTL retention phù hợp.
- Alerts/aggregates có tần suất vừa phải.
- Không cần SQL BI toàn lịch sử ngay.

### 26.2. Khi cần thêm hệ khác

- Kafka/broker khi ingest burst rất lớn, cần buffer phân vùng và nhiều subscribers.
- Warehouse/data lake khi analytics trên nhiều năm.
- Search cho log text nếu cần full-text.
- Redis cho dashboard nóng cần cache.
- Object storage cho raw payloads/files.

### 26.3. Thiết kế lưu trữ nhiều tầng

```text
Sensors -> Ingest API / Broker
                 |
          MongoDB hot operational window
                 |
          Scheduled/CDC export
                 |
          Object storage / Warehouse
                 |
          Long-term analytics
```

Phải xác định retention/archival/replay và ai giữ source truth của raw events. Nếu TTL xóa MongoDB hot data trước khi export hoàn tất, có thể mất dữ liệu lịch sử.

## 27. Tổng chi phí sở hữu: database thứ hai không chỉ là tiền máy

### 27.1. Cách tính

Một khung đánh giá:

```text
TCO =
  Infrastructure cost
+ Data transfer/network cost
+ Storage/replication/backups
+ Engineering development
+ Operations/on-call
+ Security/compliance
+ Failure recovery/reconciliation
+ Migration and future change cost
```

Khi thêm một database phụ, cần tính chi phí:

- Storage dữ liệu trùng.
- Indexes và replication của cả hai.
- CDC pipelines/brokers.
- SLO monitoring và alerts.
- Reindex/replay/backfill.
- Schema migration/versioning.
- Credentials/key rotation và access reviews.
- Disaster recovery khi các systems restore ở snapshots khác thời điểm.
- Nhân sự trực vận hành/đào tạo.

### 27.2. Tối ưu tài nguyên vs chi phí đồng bộ

Ví dụ Redis giúp giảm read load MongoDB 40%, nhưng:

- Cache invalidation race tạo incidents.
- Redis memory và on-call thêm chi phí.
- Product price stale làm giảm trải nghiệm.
- Data contracts khó kiểm thử hơn.

Nếu MongoDB chỉ cần thêm index/scale nhỏ để đáp ứng SLO, Redis có thể không còn lợi ích ròng.

### 27.3. Tách khi cần scale độc lập

Một lý do tốt cho polyglot: search/analytics cần scale độc lập với OLTP. Nếu việc chạy báo cáo lớn trên MongoDB liên tục gây p99 API tăng, tách warehouse có thể cho:

- API SLO ổn định hơn.
- Batching/compute chuyên dụng.
- Cost attribution theo workload.
- Tránh query analyst chiếm tài nguyên primary.

Nhưng phải trả giá bằng data freshness và vận hành pipeline.

## 28. Security và governance trong nhiều kho dữ liệu

### 28.1. Dữ liệu nhân bản làm tăng blast radius

MongoDB có RBAC, encryption/network controls. Khi copy sang Redis/Search/Warehouse, cùng PII có thể tồn tại ở 3–4 nơi, mỗi nơi có:

- Credentials.
- Backup/snapshots.
- Logs/profiling.
- Retention.
- Access policies.
- Audit trails.
- Deletion obligations.

“MongoDB đã mã hóa rồi” không có nghĩa bản sao trong search cũng được bảo vệ.

### 28.2. Tenant isolation không chỉ ở MongoDB

Nếu source query luôn lọc `tenantId` nhưng OpenSearch query không lọc, hệ thống có thể lộ dữ liệu giữa tenants.

Mỗi projection phải:

- Mang đủ tenant scope hoặc ACL metadata.
- Enforce authorization tại API.
- Không coi frontend filter là security boundary.
- Kiểm index/search permissions.
- Thử negative test truy cập chéo tenant.
- Tách dữ liệu nhạy cảm ra khỏi public search.

### 28.3. Quyền xóa và data retention

Khi người dùng yêu cầu xóa hoặc policy hết hạn:

```text
Delete from authoritative store
             |
        Deletion event
          /   |    \
         v    v     v
      Cache Search Analytics
```

Nếu một target offline, delete event phải được retry; không thể coi source delete là hoàn tất mọi compliance obligation. Cần trạng thái completion, alerts và audits. Với backups, áp dụng retention/legal hold phù hợp.

### 28.4. Disaster recovery đa hệ

Một lỗi restore:

```text
MongoDB restore to 10:05
Search restore to 10:15
Warehouse snapshot at 09:00
```

Search có thể chứa product events mà MongoDB source đã rollback/không còn. Không chỉ restore từng hệ mà cần **rebuild/reconcile derived stores từ authoritative state** sau DR.

Nếu một hệ khác cũng có source truth riêng, phải có kế hoạch khôi phục từng bounded context, không “chạy lại mọi event” vô điều kiện.

## 29. Observability: đo độ lệch chứ không chỉ uptime

### 29.1. Metrics của MongoDB authoritative path

- Read/write p50/p95/p99.
- QPS và error rate.
- CPU, WiredTiger cache, disk IOPS/latency.
- Replication lag/elections.
- Connections/pool wait.
- Slow queries và examined/returned.
- Transactions retry/commit errors.
- Oplog history window.

### 29.2. Metrics của derived stores

- CDC/outbox backlog.
- Last processed event/version per partition.
- Projection lag/freshness age.
- Failed/retried events.
- Duplicate/event out-of-order counts.
- Reindex/backfill progress.
- Source-target mismatches.
- Redis hit ratio, evictions, stale hits.
- Search latency/relevance.
- Warehouse data completeness.

### 29.3. Dashboard gợi ý

```text
+-----------------------------+----------------------------+
| MongoDB OLTP p95/p99        | Primary write errors       |
+-----------------------------+----------------------------+
| CDC / outbox backlog        | Resume/history lost        |
+-----------------------------+----------------------------+
| Search index freshness      | Search API relevance/lat.  |
+-----------------------------+----------------------------+
| Cache hit ratio/evictions   | Cache stale-version count  |
+-----------------------------+----------------------------+
| Warehouse watermark        | Reconciliation mismatches  |
+-----------------------------+----------------------------+
| Source/target event version | End-to-end cost per query  |
+-----------------------------+----------------------------+
```

Một cluster search “healthy” nhưng lệch dữ liệu 3 ngày vẫn có thể là sự cố nghiệp vụ. **Operational health và data correctness phải cùng được quan sát.**

## 30. Sự cố điển hình và cách thiết kế để chịu lỗi

### 30.1. Redis chết

**Kỳ vọng nếu Redis chỉ là cache:**

1. Reads fallback MongoDB.
2. Rate limit/backpressure bảo vệ MongoDB khỏi cache stampede.
3. Business writes không bị mất do cache unavailable.
4. Khi Redis trở lại, cache warm-up và version check.
5. Không dùng cached authorization decision đã hết hiệu lực.

Nếu Redis outage làm ứng dụng mất hoàn toàn khả năng đặt đơn, cần xem lại việc cache có vô tình trở thành source of truth hay không.

### 30.2. OpenSearch/indexer ngừng

1. MongoDB authoritative writes vẫn được xác nhận.
2. Outbox/CDC có thể giữ backlog trong retention budget.
3. Search UI hiển thị trạng thái degraded/stale.
4. Relay retry với idempotent events.
5. Nếu history không còn, reindex/reconcile.
6. Không sửa product giá trên search trực tiếp để “đỡ chậm” mà bỏ qua source.

### 30.3. Kafka broker chậm hoặc outage

- Business write + outbox có thể vẫn commit nếu architecture cho phép.
- Relay backlog tăng.
- Không xóa outbox chưa acknowledged.
- Kiểm storage/retention và retry storm.
- Consumers dùng dedup/inbox.
- Khi broker phục hồi, replay theo event IDs/version.

Nếu yêu cầu business đòi publish đồng bộ trước khi xác nhận command, hãy xác định rõ failure semantics, thay vì vừa dùng outbox vừa bắt cả API timeout vì broker trong đường nóng.

### 30.4. Warehouse lạc hậu

- Báo cáo cần gắn watermark/data-as-of timestamp.
- Kiểm ingestion jobs và late events.
- Cho phép rebuild partitions.
- Không dùng số liệu warehouse trễ để xác nhận balance tức thời.
- Có đối soát totals theo authoritative source.

### 30.5. PostgreSQL billing lỗi

Nếu Billing sở hữu ledger, Catalog có thể tiếp tục phục vụ sản phẩm, nhưng booking/payment workflows phải chuyển sang trạng thái chờ hoặc từ chối có kiểm soát. Không lấy bản sao invoice trong MongoDB để tự ghi “đã thanh toán” khi Billing source unavailable.

## 31. Bảng quyết định: tính điểm thay vì tranh luận sở thích

Một mẫu chấm điểm minh họa (không phải benchmark phổ quát):

| Tiêu chí | Trọng số ví dụ | MongoDB-only | MongoDB + hệ khác |
| --- | ---: | --- | --- |
| Query fits indexes/aggregation | 20% | Có lợi nếu đáp ứng đủ | Có lợi khi engine chuyên dụng giải quyết được gap |
| Consistency/invariants | 20% | Ít boundary và dễ quản lý | Tăng rủi ro sync nếu business spans systems |
| p95/p99 & throughput | 20% | Cần benchmark thật | Scale độc lập có thể tốt hơn |
| Team operational skill | 15% | Ít hệ thống hơn | Yêu cầu kỹ năng bổ sung |
| Cost/TCO | 15% | Thường đơn giản hơn | Có thể hiệu quả ở workload lớn |
| Security/compliance | 10% | Ít data copies | Nhiều nơi phải áp policy |

### 31.1. Cách dùng bảng đúng

1. Đặt tiêu chí do sản phẩm/đội ngũ xác nhận.
2. Cho weight theo mục tiêu quan trọng.
3. Đo số liệu thay vì cho điểm cảm tính.
4. Có **hard constraints**: không đạt invariant/security thì loại phương án, dù tổng điểm cao.
5. Ghi giả định và khoảng bất định.
6. Benchmark POC workload thực.
7. Lập kế hoạch review lại khi quy mô thay đổi.

Không chọn database bằng “MongoDB thắng 87 điểm, PostgreSQL 82” nếu điểm chỉ là ý kiến cá nhân.

### 31.2. Một decision tree thực dụng

```text
Do reads/writes naturally fit bounded documents?
       |
     +-- No --> Consider relational/graph/other primary
     |
     +-- Yes
          |
          v
Can MongoDB meet invariants with atomic ops,
transactions, indexes and validation?
          |
        +-- No --> Redesign model or choose another primary
        |
        +-- Yes
              |
              v
Can MongoDB meet measured SLO/cost for key queries?
              |
            +-- Yes --> Prefer simpler MongoDB-first solution
            |
            +-- No
                  |
                  v
Is problem a specialist workload?
   - caching -> Redis?
   - text relevance -> Search?
   - event fan-out -> Broker?
   - large analytics -> Warehouse?
   - file bytes -> Object Storage?
                  |
                  v
Add a derived store with ownership,
event delivery, idempotency and recovery
```

## 32. POC: định nghĩa những gì phải đo

### 32.1. Dataset đại diện

Một POC có ý nghĩa cần:

- Document sizes/payload phân phối như production.
- Tenant skew và hot products.
- Số lượng children trong arrays.
- Index cardinality.
- Read/write ratio.
- Các query shapes thực tế.
- Burst workload và peak traffic.
- Dữ liệu cũ/invalid/missing nếu vẫn có.
- Backfill/incremental sync volume.

Không kết luận một engine tối ưu hơn qua 1.000 documents trong localhost.

### 32.2. Performance experiments

Ví dụ câu hỏi:

- MongoDB compound index có phục vụ list API dưới p95 50 ms không?
- Tìm kiếm fuzzy tiếng Việt đạt relevance target hay chưa?
- Search index lag sau 10.000 product updates/s là bao nhiêu?
- Khi Redis cache cold, MongoDB có chịu được thác lũ misses không?
- Khi broker mất 10 phút, outbox có giữ đủ dữ liệu và đuổi kịp không?
- Warehouse ETL scan có ảnh hưởng OLTP không?
- Chi phí storage/indexes/network khi scale 10 lần?

### 32.3. Correctness experiments

Không chỉ đo tốc độ:

- Hai writers cập nhật cùng product version.
- Event v12 đến trước v11.
- Delete event đến trước delayed update.
- Indexer chết sau khi apply nhưng trước ack.
- Oplog history mất.
- HTTP gateway timeout sau source commit.
- Redis invalidation race.
- Source restore từ backup trong khi projection mới hơn.
- Tenant A query vào data tenant B.
- Field price từ Decimal128 chuyển sang floating point.
- GDPR/retention delete khi target offline.

## 33. Lab an toàn: MongoDB làm authoritative + projection nội bộ

Mục tiêu lab là **mô phỏng lựa chọn MongoDB-only trước khi cần external database**. Sử dụng hai collections MongoDB: một source và một read projection. Bài không yêu cầu cài Redis/Kafka/OpenSearch, không can thiệp server config.

### 33.1. Điều kiện

- Chỉ MongoDB test được cấp quyền CRUD và tạo collection.
- Không sử dụng dữ liệu thật, credentials production.
- Tạo collection **riêng theo runId**.
- Không drop database hoặc xóa collections của người khác.
- Không cố gây failover/network partition.
- Dọn dữ liệu bằng `_id + runId`.
- Ví dụ demo **không** tự cung cấp full CDC production guarantee; các hạn chế được giải thích ở phần sau.

### 33.2. Khởi tạo namespace

```javascript
const lab = db.getSiblingDB("mongo_polyglot_row453_lab");
const runId = "row453_" + new ObjectId().toHexString();
const sourceName = "products_" + runId;
const projectionName = "product_read_" + runId;

for (const name of [sourceName, projectionName]) {
  if (lab.getCollectionNames().includes(name)) {
    throw new Error("Lab namespace already exists");
  }
}

lab.createCollection(sourceName);
lab.createCollection(projectionName);

const products = lab.getCollection(sourceName);
const readModel = lab.getCollection(projectionName);

printjson({
  database: lab.getName(),
  sourceName,
  projectionName,
  runId
});
```

### 33.3. Tạo sản phẩm giả

```javascript
const productId = "SKU_" + runId;

products.insertOne({
  _id: productId,
  runId,
  tenantId: "tenant_" + runId,
  title: "Ghế demo",
  priceCents: NumberLong("1250000"),
  status: "ACTIVE",
  tags: ["furniture", "office"],
  version: NumberLong("1"),
  updatedAt: new Date()
});

printjson(products.findOne({ _id: productId, runId }));
```

### 33.4. Tạo index cho source query trước khi thêm hệ khác

```javascript
products.createIndex(
  {
    tenantId: 1,
    status: 1,
    updatedAt: -1
  },
  { name: "tenant_status_updated" }
);

printjson(
  products.find({
    tenantId: "tenant_" + runId,
    status: "ACTIVE"
  }).sort({ updatedAt: -1 })
    .limit(10)
    .explain("executionStats")
);
```

Collection một document có thể được planner quét toàn bộ thay vì dùng index vì quá nhỏ. Mục tiêu là hiểu **thiết kế và đo query**, không chứng minh tốc độ từ lab siêu nhỏ.

### 33.5. Xây read projection đơn giản

```javascript
const product = products.findOne({
  _id: productId,
  runId
});

if (!product) {
  throw new Error("Source product not found");
}

readModel.updateOne(
  { _id: product._id, runId },
  {
    $set: {
      tenantId: product.tenantId,
      title: product.title,
      priceCents: product.priceCents,
      status: product.status,
      tags: product.tags,
      sourceVersion: product.version,
      projectedAt: new Date()
    },
    $setOnInsert: { runId }
  },
  { upsert: true }
);

printjson(readModel.findOne({ _id: productId, runId }));
```

Ở đây projection được build đồng bộ bằng script cho mục đích học. Trong production, việc chạy lại script với sourceVersion cũ có thể overwrite data mới; cần version/CAS, ordering và source-to-projection pipeline đúng.

### 33.6. Thay đổi source với CAS

```javascript
const changed = products.updateOne(
  {
    _id: productId,
    runId,
    version: NumberLong("1")
  },
  {
    $set: {
      priceCents: NumberLong("1350000"),
      updatedAt: new Date()
    },
    $inc: { version: NumberLong("1") }
  }
);

if (changed.matchedCount !== 1) {
  throw new Error("Version mismatch; stop");
}

printjson(products.findOne({ _id: productId, runId }));
```

Bây giờ readModel chưa được đồng bộ, minh họa **eventual consistency**:

```javascript
printjson({
  authoritative: products.findOne({
    _id: productId, runId
  }).priceCents,
  projected: readModel.findOne({
    _id: productId, runId
  }).priceCents
});
```

### 33.7. Đồng bộ một event giả định

```javascript
const latest = products.findOne({
  _id: productId,
  runId
});

const currentProjection = readModel.findOne({
  _id: productId,
  runId
});

if (!latest || !currentProjection) {
  throw new Error("Lab expected source and projection");
}

if (latest.version > currentProjection.sourceVersion) {
  readModel.updateOne(
    {
      _id: productId,
      runId,
      sourceVersion: currentProjection.sourceVersion
    },
    {
      $set: {
        tenantId: latest.tenantId,
        title: latest.title,
        priceCents: latest.priceCents,
        status: latest.status,
        tags: latest.tags,
        sourceVersion: latest.version,
        projectedAt: new Date()
      }
    }
  );
}

printjson(readModel.findOne({ _id: productId, runId }));
```

Đây là demo **single-worker sequential**. Với multiple consumers, cần implement CAS retry/ordering và xử lý missing projection. Ví dụ không tự claim exactly-once hoặc rebootstrap gap-free.

### 33.8. Mô phỏng event cũ

```javascript
const staleEvent = {
  productId,
  sourceVersion: NumberLong("1"),
  title: "Tên cũ"
};

const projection = readModel.findOne({
  _id: productId,
  runId
});

if (staleEvent.sourceVersion < projection.sourceVersion) {
  print("Ignore stale event; projection remains newer");
} else {
  throw new Error("Unexpected version ordering");
}
```

Trong demo, business versions tăng tuần tự. Với production consumer cần version-aware conditional writes tại database hoặc single-owner ordered delivery, không chỉ kiểm version trong RAM khi có concurrent writers.

### 33.9. So sánh source và projection

```javascript
const src = products.findOne({
  _id: productId, runId
});
const dst = readModel.findOne({
  _id: productId, runId
});

printjson({
  sourceVersion: src.version,
  projectionVersion: dst.sourceVersion,
  sameTitle: src.title === dst.title,
  samePrice: src.priceCents.toString()
          === dst.priceCents.toString()
});
```

Đây là một reconciliation check đơn giản cho một product. Trên production cần scan có phân vùng, reconciliation metrics, business-specific comparisons và giới hạn tải.

### 33.10. Cleanup chỉ dữ liệu của lượt thử

Trước khi xóa, kiểm:

```javascript
printjson({
  db: lab.getName(),
  sourceName,
  projectionName,
  runId
});

const sourceDocs = products.find(
  { runId }, { _id: 1, runId: 1 }
).toArray();

const projectionDocs = readModel.find(
  { runId }, { _id: 1, runId: 1 }
).toArray();

printjson({
  sourceOwned: sourceDocs.length,
  projectionOwned: projectionDocs.length
});
```

Sau khi xác nhận đúng namespace/runId:

```javascript
for (const item of sourceDocs) {
  products.deleteOne({
    _id: item._id, runId
  });
}

for (const item of projectionDocs) {
  readModel.deleteOne({
    _id: item._id, runId
  });
}

printjson({
  sourceRemaining: products.countDocuments({ runId }),
  projectionRemaining: readModel.countDocuments({ runId })
});
```

Không `dropDatabase()` hoặc `deleteMany({})` trên môi trường chia sẻ. Collection/index lab còn lại sau khi xóa records; việc dọn namespace ngẫu nhiên là nhiệm vụ quản trị test environment với xác minh ownership.

## 34. Thiết kế service Java: gateway và repository theo bounded context

### 34.1. Không để ứng dụng phụ trực tiếp ghi vào hai databases

Một service sở hữu product state nên dùng interface:

```java
public interface ProductRepository {
    Product findById(String tenantId, String productId);
    boolean updatePriceIfVersion(
        String tenantId,
        String productId,
        long expectedVersion,
        long priceCents
    );
}
```

Implementation MongoDB chịu trách nhiệm atomic source updates và, khi cần, outbox trong transaction.

Search indexer nên có interface khác:

```java
public interface ProductSearchProjection {
    void upsert(
        String productId,
        long sourceVersion,
        ProductSearchDocument document
    );
    void delete(String productId, long sourceVersion);
}
```

Không đặt logic ghi MongoDB và search trong một method đơn giản rồi trả “thành công” nếu chỉ một bên đã ghi.

### 34.2. Ví dụ atomic conditional update bằng Java Sync Driver

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

static boolean updatePrice(
        MongoCollection<Document> products,
        String tenantId,
        String productId,
        long expectedVersion,
        long newPriceCents) {

    if (newPriceCents < 0) {
        throw new IllegalArgumentException(
            "Price cannot be negative"
        );
    }

    UpdateResult result = products.updateOne(
        and(
            eq("_id", productId),
            eq("tenantId", tenantId),
            eq("version", expectedVersion)
        ),
        combine(
            set("priceCents", newPriceCents),
            currentDate("updatedAt"),
            inc("version", 1L)
        )
    );

    return result.getMatchedCount() == 1;
}
```

Với monetary values, kiểm business units và conversion. Đối với update product và outbox cùng transaction, thêm `ClientSession` cùng write concern và retry semantics. Đây là code minh họa một update source, **chưa phải full outbox implementation**.

### 34.3. Query-side fallback

Pseudo-code:

```java
ProductSearchResult searchProducts(Query q) {
    try {
        return searchProjection.search(q);
    } catch (SearchUnavailableException e) {
        // Fallback chỉ khi MongoDB source có query
        // tương đương và đủ SLO/budget.
        return mongoSearchFallback.search(q);
    }
}
```

Không thể fallback một full-text relevance query cực phức tạp bằng `find({})` rồi lọc trong RAM nếu thiếu index/SLO. Fallback có thể trả degraded response hoặc báo search unavailable; phải thiết kế rõ.

## 35. Ma trận anti-pattern và hướng thay thế

| Anti-pattern | Vì sao có vấn đề | Phương án |
| --- | --- | --- |
| “MongoDB luôn tốt nhất vì schema linh hoạt” | Bỏ qua FK/join/SQL workload | Đánh giá invariants và query patterns |
| “SQL luôn tốt hơn vì có ACID” | MongoDB có atomic documents/transactions | Benchmark và ranh giới giao dịch |
| “Document DB không thể join” | MongoDB có `$lookup` | Đo join frequency/cost |
| “Mỗi microservice phải dùng DB khác loại” | Tăng operations vô ích | Chọn theo bounded context |
| “Dữ liệu có quan hệ là phải chuyển SQL” | Embedded bounded aggregates có thể hợp lý | Chọn theo lifecycle/access patterns |
| “MongoDB-only nghĩa một server” | Bỏ HA/durability | Replica set/sharding khi cần |
| “Chậm thì thêm Redis trước” | Có thể chỉ thiếu index | Explain/optimize source |
| “Redis invalidation luôn đồng bộ” | Có race giữa read/fill/invalidate | Version/TTL/consistency budget |
| “Search index là nguồn giá” | Projection có thể stale | Checkout verify source |
| “Search engine luôn cần cho text” | MongoDB có text/Search tùy deployment | Đánh giá features hiện có |
| “Kafka là database giao dịch” | Broker offset khác business invariant | Source owner + events |
| “MongoDB change stream là consumer group” | Mỗi watcher có thể nhận mọi events | Ownership/partitioning |
| “Outbox nghĩa exactly once” | Publish ACK có thể mất | Idempotent consumers |
| “Dual-write Mongo + SQL là atomic” | Không transaction chung mặc định | Single owner, outbox/saga |
| “Hai DB đều có thể sửa price” | Conflict authority | One source of truth |
| “Event đến luôn đúng thứ tự” | Multi-consumer retries/partitioning | Aggregate version/CAS |
| “Snapshot xong mới CDC là ổn” | Có gap | Coordinated bootstrap |
| “Resume token giữ lịch sử mãi” | Oplog window hữu hạn | Monitor/rebootstrap |
| “Warehouse số nào cũng realtime” | Batch/lag/late events | Watermark/freshness SLO |
| “Object storage file + Mongo metadata atomic” | Hai hệ thống riêng | State machine/reconciliation |
| “Vector DB là bắt buộc cho RAG” | Nhiều lựa chọn tùy workload | POC recall/latency/cost |
| “Data copy không tăng rủi ro bảo mật” | Thêm nơi có PII | Minimize/ACL/audit/delete |
| “Delete source là xóa mọi bản sao” | Derived stores có thể offline | Deletion propagation audit |
| “DR chỉ restore từng database là đủ” | Snapshots khác thời điểm | Rebuild/reconcile |
| “Không thấy lỗi tức dữ liệu sync đúng” | Silent lag/mismatch | Metrics + reconciliation |
| “Đổi database khi vừa gặp một slow query” | Che thiết kế truy vấn sai | Profile, index, explain |
| “Schema-less nghĩa không cần data contract” | Consumer/mapping errors | Validator/schema versioning |
| “Một benchmark localhost chọn được kiến trúc” | Không đại diện load/failure | Representative POC |
| “Thêm nhiều công nghệ giúp future-proof” | TCO/on-call tăng | Start simple, evolve deliberately |

## 36. Các câu hỏi phỏng vấn và bài tập thiết kế

### Bài A — MongoDB một mình có đủ không?

Một ứng dụng lưu 200.000 hồ sơ sản phẩm, phần lớn truy vấn bằng `productId` và filter `category`, chỉ 3 developers vận hành.

1. Những phép đo nào cần trước khi thêm Redis?
2. MongoDB indexes/aggregation có thể giải quyết gì?
3. Khi nào mới cần search engine?
4. TCO có ảnh hưởng gì đến quyết định?

### Bài B — Chọn SQL hay document model

Hệ thống quản lý kế toán cần journal entries, constraints và nhiều báo cáo join. So với catalog sản phẩm có attributes thay đổi, đâu nên dùng MongoDB và đâu nên cân nhắc RDBMS? Nêu access patterns, invariants và transaction boundary.

### Bài C — Dual writes

```text
write MongoDB -> write OpenSearch
```

1. Kể ít nhất 4 failure windows.
2. Vì sao đảo thứ tự không giải quyết?
3. Thiết kế outbox/CDC.
4. Khi search lỗi, API catalog nên phản hồi thế nào?

### Bài D — Cache invalidation race

```text
T1 cache miss
T2 MongoDB update
T3 cache DEL
T4 old reader cache SET
```

Hãy đề xuất versioned cache key hoặc CAS logic. Chỉ rõ stale-data budget cho product title và payment status khác nhau ra sao.

### Bài E — Event ordering

Product version 13 đến indexer trước version 12.

1. Vì sao search có thể bị ghi lùi?
2. Version lấy từ đâu?
3. Khi nhận delete event trước delayed update thì sao?
4. Tombstone retention giúp gì?

### Bài F — CQRS

Một dashboard cần 8 fields từ 5 collections. So sánh `$lookup` trực tiếp với read projection. Nêu query frequency, index/plan, data freshness, rebuild và cost.

### Bài G — Analytical workloads

Một nhóm BI chạy queries quét 3 năm đơn hàng mỗi 2 phút, làm API p99 tăng.

1. Có thể tối ưu MongoDB bằng cách nào trước?
2. Khi nào warehouse là hợp lý?
3. Làm sao export/CDC mà không mất updates?
4. Dùng watermark nào để giải thích báo cáo trễ?

### Bài H — Object storage metadata

Upload file thành công nhưng insert MongoDB metadata thất bại.

1. File sẽ ở trạng thái gì?
2. Thiết kế state machine.
3. Làm sao dọn orphan an toàn?
4. Có thể gọi hai writes là atomic không?

### Bài I — Booking availability

Search hiển thị còn phòng nhưng Booking service authoritative báo hết.

1. Nơi nào quyết định?
2. Kịch bản nào chấp nhận eventual consistency?
3. Inventory reservation phải atomic như thế nào?
4. Nếu search lag vượt SLO thì UI nên làm gì?

### Bài J — Outbox retries

Relay publish event E10 thành công nhưng mất ACK rồi publish lại.

1. Vì sao không thể gọi exactly once?
2. Consumer dedup bằng key nào?
3. Nếu event E11 đến trước E10 xử lý thế nào?
4. Cần DLQ/retry/reconciliation gì?

### Bài K — MongoDB + PostgreSQL ownership

Catalog dùng MongoDB; Billing dùng PostgreSQL. Một API checkout cần thông tin product và tạo invoice.

1. Hai systems nên phối hợp qua API/events thế nào?
2. Giá snapshot ở thời điểm checkout nằm ở đâu?
3. Nếu Catalog unavailable thì tạo invoice được không?
4. Không dùng transaction xuyên MongoDB/PostgreSQL mà vẫn đúng nghiệp vụ bằng cách nào?

### Bài L — Security đa hệ

Customer data có ở MongoDB, Redis, Search và Warehouse. Một tenant yêu cầu xóa.

1. Liệt kê places cần xử lý.
2. Nếu search offline, xóa thế nào?
3. Backups và retention cần policy gì?
4. Chứng minh deletion đã propagated bằng evidence nào?

### Bài M — Recovery

MongoDB source restore về snapshot 10:00, search restore về 10:15.

1. Loại dữ liệu lệch nào có thể xuất hiện?
2. Làm sao rebuild từ source?
3. Có cần tombstones/version không?
4. Có thể cứ tin search vì nó “mới hơn” không?

### Bài N — Transaction boundary

Một service cần cập nhật order, ledger, outbox. Thiết kế transaction trong MongoDB và phân biệt với gọi payment gateway. Vì sao external call không được nằm trong retry callback?

### Bài O — Graph/vector

Ứng dụng social có relationships 5 hops; ứng dụng hỗ trợ khách hàng cần semantic search. Hãy đặt benchmark và tiêu chí để lựa chọn MongoDB `$graphLookup`/Vector Search so với specialized graph/vector engines.

### Bài P — Decision record

Viết một ADR cho quyết định thêm OpenSearch vào hệ thống MongoDB:

- Context.
- Current pain.
- Alternatives (indexes/MongoDB Search/OpenSearch).
- Data owner.
- Read/write path.
- Consistency SLO.
- Failure modes.
- Backfill/CDC.
- Security.
- Cost and operations.
- Rollout/rollback criteria.

### Bài Q — Không thêm database

Một team đề xuất Kafka + Redis + OpenSearch + PostgreSQL cho một app nội bộ 300 người dùng. Hãy lập luận một kiến trúc MongoDB-first đơn giản, những giới hạn phải đo và các điều kiện cụ thể khiến bạn đổi quyết định.

## 37. Mẫu Architecture Decision Record (ADR)

```markdown
# ADR: MongoDB-only hay MongoDB + Search

## Context
- Source data: products
- Access patterns: read by ID + faceted full-text search
- Current latency: p95...
- Expected growth: ...
- Team/on-call capacity: ...

## Decision drivers
- Search relevance and latency
- OLTP SLO isolation
- Security/tenant filtering
- Freshness allowed
- Cost/TCO

## Options
1. MongoDB indexes + aggregation
2. MongoDB Search on available deployment
3. MongoDB + OpenSearch projection

## Decision
- Chọn ... vì ...
- MongoDB remains source of truth
- Search target is derived and rebuildable

## Synchronization
- Outbox/change stream + stable event IDs
- Source version and tombstones
- Retry/backoff/idempotency
- Rebootstrap procedure

## Failure behavior
- Search unavailable -> ...
- CDC history lost -> ...
- Source restore -> ...

## Validation
- P95/p99 load test
- Relevance tests
- Version mismatch count
- Security negative tests
- Recovery drill

## Rollout
- Shadow index
- Reconcile
- Canary reads
- Gradual cutover
- Feature-flag rollback

## Ownership
- Catalog writes MongoDB only
- Search team owns projection and on-call
```

ADR nên ghi **quyết định và các điều kiện thay đổi quyết định**, không chỉ liệt kê tên công nghệ. Khi workload/khả năng sản phẩm thay đổi, nhóm có thể xem lại với dữ liệu mới.

## 38. Tài liệu tham khảo

Đọc theo đúng MongoDB server version, FCV, driver, topology và khả năng của managed service; không mặc định mọi tính năng có ở mọi deployment:

### MongoDB chính thức

- [Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/) — embedding, references, access patterns.
- [Indexes](https://www.mongodb.com/docs/manual/indexes/) — compound/multikey/partial/TTL/unique indexes.
- [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) — `$match`, `$group`, `$lookup` và transformations.
- [`$lookup`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/) — kết hợp collections trong aggregation.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — multi-document atomicity và trade-offs.
- [Change Streams](https://www.mongodb.com/docs/manual/changestreams/) — CDC, resume tokens, oplog history.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — durability/replication guarantees.
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — visibility/consistency.
- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — document contracts.
- [Sharding](https://www.mongodb.com/docs/manual/sharding/) — scale-out và shard key design.
- [Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/) — time-series storage.
- [GridFS](https://www.mongodb.com/docs/manual/core/gridfs/) — lưu files lớn khi phù hợp.
- [MongoDB Search](https://www.mongodb.com/docs/atlas/atlas-search/) — khả năng full-text/search tích hợp theo tier.
- [MongoDB Vector Search](https://www.mongodb.com/docs/atlas/atlas-vector-search/) — semantic/vector capabilities theo deployment.
- [`$graphLookup`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/graphLookup/) — recursive graph traversal.
- [MongoDB Atlas Monitoring](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/) — metrics cluster.

### Công nghệ bổ sung (tài liệu nhà cung cấp)

- [PostgreSQL Documentation](https://www.postgresql.org/docs/) — relational schema, constraints, transactions, SQL.
- [Redis Documentation](https://redis.io/docs/latest/) — caching, persistence, eviction, streams.
- [OpenSearch Documentation](https://docs.opensearch.org/latest/) — search indexes, ingestion, relevance.
- [Elasticsearch Documentation](https://www.elastic.co/guide/) — full-text/search engine features.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/) — topics, partitions, offsets, consumers.
- [Debezium Documentation](https://debezium.io/documentation/) — change data capture patterns.
- [AWS S3 Documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html) — object storage semantics.

Không chọn công nghệ chỉ vì tài liệu nói “hỗ trợ” một feature. Với performance/correctness/security, phải thử trên dataset và quy trình phục hồi đại diện cho chính ứng dụng.

## 39. Kết luận

**Lựa chọn MongoDB độc lập hay phối hợp với hệ quản trị khác là quyết định về ranh giới dữ liệu và năng lực vận hành, không phải cuộc thi số tính năng.**

- **Ưu tiên MongoDB-first** nếu dữ liệu document phù hợp, các query chính có thể được phục vụ bởi indexes/aggregation/search khả dụng, invariants bảo vệ được và SLO/chi phí đạt mục tiêu.
- **Cân nhắc RDBMS** khi dữ liệu quan hệ, referential constraints, SQL joins và transactional workflows là trọng tâm.
- **Thêm Redis** khi cache thật sự giúp latency/cost và ứng dụng chịu được staleness cùng fallback.
- **Thêm search engine** khi cần relevance/facets/fuzzy/scoring mà lựa chọn search hiện có không đáp ứng.
- **Thêm broker** khi cần fan-out/buffering/retention/consumer groups vượt nhu cầu change stream trực tiếp.
- **Thêm warehouse/lakehouse** khi OLAP lịch sử ảnh hưởng OLTP hoặc cần phân tích nhiều nguồn dữ liệu.
- **Dùng object storage** cho files/binary lớn và quản lý metadata/ownership rõ.
- **Đánh giá graph/vector engines** khi traversal/semantic retrieval là workload chủ đạo, dựa trên benchmark và tính năng deployment thực tế.

Khi sử dụng nhiều hệ thống, các quyết định quan trọng hơn tên database là:

1. **Ai sở hữu nguồn dữ liệu gốc và được phép ghi?**
2. **Bản sao nào có thể stale trong bao lâu?**
3. **Dữ liệu được đồng bộ bằng event/outbox/CDC nào, với ID/version ra sao?**
4. **Nếu event lặp, đến trễ, mất lịch sử hoặc target ngừng, recovery thế nào?**
5. **Invariants nào không được đặt trên cache/search projection?**
6. **Hệ thống có đủ observability, backup, reconciliation, bảo mật và người vận hành không?**

**Nguyên tắc cốt lõi:** bắt đầu từ mô hình đơn giản nhất **đáp ứng đúng workload và hợp đồng nghiệp vụ**. Chỉ thêm một hệ quản trị dữ liệu khi giá trị kỹ thuật/kinh doanh đo được vượt chi phí của đồng bộ và vận hành. Khi đã thêm, hãy thiết kế nó như một **thành phần có ownership, consistency, failure behavior và đường khôi phục rõ ràng**, không chỉ là nơi lưu thêm một bản sao.
