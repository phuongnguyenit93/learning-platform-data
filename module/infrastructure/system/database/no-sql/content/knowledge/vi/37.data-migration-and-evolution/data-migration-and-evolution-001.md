# Kiểm kê dữ liệu, truy vấn, schema và hợp đồng ứng dụng trước di chuyển

## 1. Tình huống mở đầu: chuyển dữ liệu xong nhưng ứng dụng vẫn lỗi

Một hệ thống Java lưu đơn hàng trong MongoDB. Đội phát triển muốn chuyển một phần dữ liệu sang DynamoDB để đơn giản hóa vận hành. Sau khi sao chép 50 triệu documents, họ kiểm tra:

~~~text
Source order count:       50.000.000
Target item count:        50.000.000
Copy job status:          SUCCESS
```

Nhưng khi chuyển một số requests sang hệ mới, xuất hiện nhiều vấn đề:

- Trang quản trị tìm đơn theo `customerId + createdAt` chậm vì target chưa có access path tương ứng.
- Endpoint `GET /orders` dựa vào sắp xếp mặc định không còn trả cùng thứ tự.
- Một số đơn cũ lưu `totalAmount` dưới dạng chuỗi, một số là số; quy tắc mapping trước đây vô tình che sự không nhất quán.
- Ứng dụng dùng update có điều kiện theo `version`, nhưng lệnh ghi mới được triển khai thành `put` vô điều kiện, gây lost update.
- Một worker cũ vẫn kết nối MongoDB và tiếp tục tạo dữ liệu mới sau snapshot.
- TTL của dữ liệu tạm bị hiểu thành xóa vật lý đúng thời điểm; session hết hạn vẫn xuất hiện trong một số read paths.
- Quy trình đối soát payment dùng một aggregation query không được đưa vào danh sách chuyển đổi.
- Một job batch viết thẳng vào collection, không đi qua Java repository; nó đã bị bỏ sót.
- Search index, CDC consumer và backup job vẫn trỏ về nguồn cũ.

**Sao chép cùng số bản ghi chưa có nghĩa là di chuyển thành công.** Database không chỉ chứa dữ liệu. Nó còn là một tập các **schema thực tế, access patterns, side effects, consistency expectations, quyền truy cập và thỏa thuận ngầm** giữa nhiều thành phần.

Bài học **“Kiểm kê dữ liệu, truy vấn, schema và hợp đồng ứng dụng trước di chuyển”** thuộc chương **“Di chuyển và thay đổi”** trong module **Database No SQL**. Trọng tâm là lập hồ sơ hiện trạng đủ chi tiết và kiểm chứng được để một nhóm khác có thể thiết kế, thử nghiệm, triển khai và rollback migration mà không đoán hành vi ứng dụng.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định rõ **phạm vi di chuyển** và hệ thống nào là nguồn có thẩm quyền.
2. Lập inventory dữ liệu theo collection/table/keyspace/index/tenant/region và theo phụ thuộc nghiệp vụ.
3. Phân biệt **schema được khai báo** với schema thực tế đang tồn tại trong dữ liệu.
4. Liệt kê các truy vấn/ghi phát sinh từ API, batch, CDC, admin tools và tích hợp bên ngoài.
5. Mô tả query patterns bằng key, filter, sort, projection, pagination, cardinality, tần suất và SLO.
6. Ghi nhận hợp đồng ứng dụng về kiểu dữ liệu, absent/null, IDs, errors, consistency, giao dịch, TTL và idempotency.
7. Xác định tác động của key design, partition distribution, hot keys và secondary indexes khi đổi NoSQL engine.
8. Lập mapping schema và kiểm soát lỗi chuyển kiểu, dữ liệu trùng, quan hệ thiếu và schema drift.
9. Xác định các consumer của events/CDC, read models và những thành phần đọc/ghi trực tiếp ngoài API chính.
10. Xây inventory có owner, bằng chứng và mức độ chắc chắn; chuyển những chỗ chưa rõ thành blocker/test.
11. Đặt acceptance criteria cho backfill, dual write, shadow reads, cutover và rollback.
12. Viết ví dụ Java để đo/query catalog và kiểm thử những hợp đồng quan trọng.

---

## 2. Tư duy đúng: kiểm kê là tìm các “hợp đồng đang tồn tại”

Một **hợp đồng ứng dụng** là tập điều kiện mà consumer dựa vào khi sử dụng dữ liệu, dù điều kiện đó có được viết thành tài liệu chính thức hay không.

Ví dụ:

~~~text
API GET /orders/{id}
  Input:
    orderId luôn là UUID canonical string
  Output:
    404 nếu không thấy
    status thuộc CREATED | PAID | CANCELLED
  Time:
    p99 dưới 100 ms với kích thước tải chuẩn
  Consistency:
    sau khi PUT trả 200, người dùng đọc lại phải thấy phiên bản mới
  Security:
    chỉ xem đơn thuộc tenant hiện tại
~~~

Nếu ở database mới việc đọc ngay sau ghi trả dữ liệu cũ, response thiếu field, thứ tự sort khác hoặc query bỏ kiểm tenant, hợp đồng có thể bị phá **dù số records hoàn toàn khớp**.

### 2.1. Bốn lớp phải kiểm kê

| Lớp | Phải trả lời |
|---|---|
| **Data** | Dữ liệu nào có, ở đâu, ai sở hữu, nguồn có thẩm quyền là gì? |
| **Queries/mutations** | Các thành phần đang đọc/ghi thế nào, với tải và SLO nào? |
| **Schema/semantics** | Kiểu, cấu trúc, ràng buộc, version và vòng đời thực tế là gì? |
| **Application contract** | Consumer giả định gì về kết quả, thứ tự, lỗi, consistency, transaction và security? |

### 2.2. Cần cả trạng thái hiện tại lẫn mục tiêu

Đánh dấu rõ từng điều:

- **Observed current behavior:** đã quan sát được.
- **Declared existing contract:** yêu cầu đã được phê duyệt.
- **Target behavior:** muốn có sau di chuyển.
- **Intentional behavior change:** thay đổi có chủ đích cần người chịu trách nhiệm chấp thuận.
- **Unknown:** chưa đủ bằng chứng, không được tự điền giá trị.

### 2.3. Kiểm kê trước khi thiết kế target schema

Một mô hình `orders_by_customer` trong Cassandra hoặc GSI trong DynamoDB nên xuất phát từ access patterns đã kiểm chứng. Tạo schema dựa chỉ vào bản JSON mẫu thường khiến query path không khả thi hoặc quá đắt.

---

## 3. Xác định chính xác loại migration

Không phải mọi thay đổi đều giống nhau.

| Loại thay đổi | Ví dụ | Điều kiểm kê cần ưu tiên |
|---|---|---|
| Đổi engine | MongoDB → DynamoDB | Query/consistency/index/transaction semantics |
| Đổi mô hình dữ liệu | Embedded document → multiple tables | Relations, duplicate data, atomic updates |
| Đổi partition/shard key | `tenantId` → `tenantId#bucket` | Routing, hot partitions, query fan-out |
| Tách collection/table | `orders` → order header + items | Invariants và read consistency |
| Hợp nhất nguồn | Nhiều regional stores → một global service | ID collisions, conflicts, residency |
| Đổi vùng/nhà cung cấp | Self-hosted → managed region | Latency, encryption, IAM, backup |
| Nâng phiên bản engine | Driver/schema/protocol change | Compatibility, feature defaults |
| Thay access path | Scan → query theo GSI/index | Filter/sort/pagination semantics |
| Thay CDC/stream | Oplog/change stream → new events | Ordering, resume tokens, payload format |
| Backfill một trường | `currency`/`schemaVersion` | Missing/null, default và concurrent writes |

### 3.1. Phạm vi phải là danh sách cụ thể

Ghi:

~~~text
In scope:
  orders: primary collection
  orders_by_customer: read model
  order outbox and CDC
  Java Order API + nightly reconciliation job

Out of scope:
  accounting ledger (external authority)
  historical invoice archive (read-only)
  search ranking model

Dependencies:
  payment provider, IAM, KMS, Kafka
```

“Out of scope” không có nghĩa bỏ qua phụ thuộc của chúng. Ví dụ accounting ledger không chuyển nhưng vẫn là nguồn đối soát sau cutover.

### 3.2. Khóa phạm vi theo một thời điểm

Inventory cần có `capturedAt`, code revision/driver version, source topology và traffic window. Dữ liệu/truy vấn thay đổi mỗi ngày; một báo cáo từ 3 tháng trước không thể coi là current mà không refresh.

---

## 4. Bắt đầu bằng sơ đồ luồng dữ liệu, không bằng danh sách collections

Một luồng nghiệp vụ minh họa:

~~~mermaid
flowchart LR
    UI["Web/Mobile"] --> API["Java Order API"]
    API --> SRC["Order source NoSQL"]
    API --> CACHE["Redis cache"]
    API --> PAY["Payment service"]
    JOB["Nightly reconciliation"] --> SRC
    ADMIN["Support/admin tools"] --> SRC
    SRC --> CDC["Outbox / CDC"]
    CDC --> SEARCH["Search index"]
    CDC --> REPORT["Analytics sink"]
    CDC --> NOTIFY["Email worker"]
    ARCHIVE["Object archive"] <-->|"Invoice references"| SRC
~~~

### 4.1. Ghi mọi loại writer

- API synchronous writes.
- Scheduled batch jobs.
- Data import/backfill scripts.
- Admin/operations consoles.
- Event consumers và CDC replay jobs.
- Mobile/offline synchronization.
- External partners qua integrations.
- Scheduled TTL/cleanup jobs.
- Manual support corrections.
- Old app versions đang chạy trong lúc rolling deployment.

### 4.2. Ghi mọi loại reader

- Point lookup API.
- List/search/filter endpoints.
- Dashboard/reporting.
- Export/ETL.
- Fraud checks.
- Customer support tooling.
- Cache warm-up.
- Monitoring/health probes.
- Audit/compliance retrieval.
- Backup/restore verification.

### 4.3. Không bỏ quên workload ít chạy

Query chạy mỗi quý để lập báo cáo thuế có thể không xuất hiện trong 7 ngày telemetry. Cần kết hợp **code search, owners, scheduled jobs, access logs và runbooks** thay vì chỉ xem top queries hiện tại.

### 4.4. Đường đọc gián tiếp

Một endpoint có thể đọc Redis trước, miss rồi query MongoDB. Nếu chỉ xem APM của cache hit, database access pattern dưới peak cache-miss không được ghi nhận đúng.

---

## 5. Data inventory: đơn vị và thuộc tính tối thiểu

Một bảng kiểm kê có thể gồm:

| Field | Ví dụ | Ý nghĩa |
|---|---|---|
| `assetId` | `orders-main` | ID ổn định cho migration plan |
| `businessOwner` | Order domain | Ai duyệt invariant/RPO |
| `technicalOwner` | Order platform team | Ai triển khai và vận hành |
| `systemOfRecord` | MongoDB orders | Nguồn có thẩm quyền |
| `storageScope` | cluster, db, collection | Ranh giới sao chép |
| `tenantScope` | Multi-tenant | Tách/kiểm tenant |
| `region` | Primary + DR region | Residency và failure domain |
| `approxCount` | 50M docs | Dự báo backfill |
| `avg/p99DocumentSize` | 1.2/24 KiB | Dự báo memory/network |
| `growthRate` | 120 GB/day | Catch-up window |
| `update/deleteRate` | 10k/2k ops/s | CDC và tombstone pressure |
| `retention/TTL` | 365 ngày | Lifecycle/physical cleanup |
| `dataSensitivity` | PII / financial | Access/encryption/masking |
| `indexes` | tenant+createdAt | Query dependencies |
| `schemaVersions` | v1/v2/v3 | Mapping rules |
| `readers/writers` | API, batch, CDC | Contract owners |
| `backup/RPO/RTO` | Theo asset | Recovery/cutover safety |
| `evidence` | Telemetry snapshot + owner | Độ tin cậy của inventory |

### 5.1. Số lượng record không đủ để sizing

Một collection 10 triệu documents có thể chứa 2 KiB/doc hoặc 2 MiB/doc. Đo size distribution (p50/p95/p99/max), không nhân count với một bản mẫu.

### 5.2. Cần hiểu dữ liệu trùng

Nếu cùng một `order` được lưu trong `orders`, `orders_by_user` và `orders_by_day`, đây có thể là **ba bản thể hiện của cùng một fact**, không được xem là ba giao dịch khác nhau khi đối soát.

### 5.3. Ghi thuộc tính mở rộng

Các fields như `isArchived`, `deletedAt`, `sourceVersion`, `etag`, `lastUpdatedAt` có thể mang semantics quan trọng cho retention, conflict resolution và CDC.

---

## 6. System of record, derived data và nguồn có thể tái dựng

### 6.1. Authoritative records

Đây là nơi một quyết định nghiệp vụ được commit theo hợp đồng. Ví dụ `orders` có thể là nguồn chính cho trạng thái đơn.

### 6.2. Materialized projections

`orders_by_customer` hoặc Elasticsearch index có thể được dựng lại từ source và change history, **nhưng chỉ khi** history/mapper/schema/permissions còn đủ.

### 6.3. Cache và state hữu hạn

Redis có thể giữ cache products, nhưng cũng có thể giữ idempotency keys, one-time tokens hoặc quota. Không đánh dấu tất cả Redis keys là disposable.

### 6.4. External source of authority

Payment provider có thể xác thực một khoản tiền đã thu; một backup NoSQL không tự đảo ngược charge ở provider.

### 6.5. Quy tắc đánh dấu `rebuildable`

Chỉ đánh dấu `true` khi có:

1. Source dữ liệu còn tồn tại.
2. Query/access tới source.
3. Đầy đủ historical changes/CDC hoặc baseline phù hợp.
4. Mapping code/version.
5. Thời gian và capacity rebuild đạt RTO.
6. Validation oracle độc lập.
7. Quy trình retry/replay không nhân side effects.

---

## 7. Lập inventory schema khai báo và schema thực tế

Document NoSQL có thể linh hoạt về cấu trúc nhưng **ứng dụng không hề schema-less**: code vẫn giả định những trường, kiểu và ràng buộc cụ thể.

### 7.1. Schema khai báo

Có thể tồn tại dưới dạng:

- JSON Schema validation.
- Cassandra CQL table definitions.
- DynamoDB key schema + attribute conventions.
- MongoDB collection validators.
- Java DTO/POJO, Jackson annotations.
- Avro/Protobuf/JSON Schema của events.
- Database index definitions.
- Application-level constraints và migration scripts.

### 7.2. Schema thực tế

Trong dữ liệu có thể tồn tại:

~~~json
{"_id":"o-101","totalAmount":120000,"currency":"VND","status":"PAID"}
{"_id":"o-102","totalAmount":"120000","status":"PAID"}
{"_id":"o-103","totalAmount":null,"currency":"VND"}
{"_id":"o-104","items":[],"status":"CREATED"}
{"_id":"o-105","status":"REFUNDED","schemaVersion":1}
```

Khi client cũ đã từng ghi nhiều biến thể, DTO mới có thể deserialize được một phần nhưng **backfill nghiêm ngặt** sẽ fail hoặc silently coerce sai.

### 7.3. Cần ghi type distribution theo field

Ví dụ:

| Field | Observed variants | Ý nghĩa khi chuyển |
|---|---|---|
| `_id` | String/UUID/BSON ObjectId | Canonical ID mapping |
| `totalAmount` | Number/String/Null/Missing | Validation và chuẩn hóa tiền |
| `createdAt` | ISO string/BSON Date/epoch | Timezone và precision |
| `status` | PAID/CANCELLED/REFUNDED/legacy values | Enum compatibility |
| `items` | Array/Null/Missing | List semantics |
| `tenantId` | String/Missing trong legacy | Isolation/backfill policy |
| `metadata` | Object/string | Nested map/serializer |
| `version` | Number/Missing | Optimistic locking |

### 7.4. Dùng sampling có ý thức

Sample ngẫu nhiên có thể bỏ qua long-tail. Nên kết hợp:

- Random sampling có tỷ lệ phù hợp.
- Stratified by tenant/time/schemaVersion.
- Top largest documents.
- Oldest/newest records.
- Known exceptional IDs (dùng mã giả hoặc secure references).
- Dead-letter/parse-error cohorts.
- Data written by legacy app versions.

Không xuất raw PII vào báo cáo kiểm kê.

---

## 8. Missing, null, empty và zero là bốn nghĩa khác nhau

Ví dụ:

~~~json
{}
{"discount":null}
{"discount":0}
{"discount":""}
```

Tùy domain:

- **Missing:** không được ghi/không có thông tin.
- **Null:** chủ đích chưa biết/không áp dụng.
- **Zero:** giá trị số bằng 0.
- **Empty string:** chuỗi rỗng, có thể bị coi invalid.
- **Empty array:** mảng hợp lệ nhưng không có phần tử.
- **Expired/deleted marker:** có thể không còn xuất hiện ở read path.

### 8.1. Vì sao migration hay phá nghĩa?

Một mapper có thể gọi `getOrDefault("discount", 0)`, biến mọi missing/null thành 0 và khiến logic tính giá coi khách đã có thông tin giảm giá hợp lệ.

### 8.2. DynamoDB/MongoDB/Cassandra khác nhau

DynamoDB có các attribute types và tồn tại/không tồn tại attribute; MongoDB phân biệt field presence với BSON Null; Cassandra có row/cell/tombstone semantics riêng. Không áp null/missing equality và filter behavior của engine cũ sang engine mới.

### 8.3. Cách lập mapping

Mỗi trường cần:

~~~text
sourceType
sourcePresenceRule
targetType
targetPresenceRule
defaultRule
invalidValueRule
precisionRule
lossyTransformationAllowed?
ownerApproval
validationOracle
```

### 8.4. Không tự thêm default lúc copy

Nếu default làm thay đổi nghiệp vụ, phải có owner chấp thuận và audit được danh sách records đã được normalize.

---

## 9. Kiểu dữ liệu, độ chính xác và đơn vị đo

### 9.1. Số tiền

Không chuyển `BigDecimal` sang IEEE 754 `double` chỉ để dễ serialize khi cần độ chính xác tài chính. Nếu source dùng decimal/long minor units, định nghĩa scale, rounding và currency rõ ràng.

### 9.2. Timestamps

Ghi:

- UTC instant hay local business time.
- Precision: seconds/milliseconds/microseconds.
- Timezone offset có được giữ không.
- DST ambiguity.
- Nếu input cũ là epoch seconds, tránh hiểu nhầm milliseconds.
- Thứ tự events có dựa vào timestamp không.

### 9.3. IDs

MongoDB ObjectId/Binary UUID, UUID string, DynamoDB partition key và Cassandra UUID/TIMEUUID không tương đương về thứ tự hoặc representation. Cần canonical mapping và test uniqueness.

### 9.4. Binary/blob

Một document có binary attachment lớn có thể phải chuyển sang object storage và lưu reference. Việc này thay đổi atomicity, retry, cleanup và authorization.

### 9.5. Strings

Unicode normalization, collation, case-insensitive comparison, locale sort và whitespace handling có thể khác giữa engine/index/client.

### 9.6. Booleans/enums

Legacy `"Y"`, `1`, `true` và missing phải có conversion rules. Unknown enum values phải được xử lý an toàn; không âm thầm map mọi thứ thành trạng thái có quyền cao.

---

## 10. Identity và key design: logic, vật lý và định tuyến

Một ứng dụng có thể coi `orderId` là khóa logic duy nhất, nhưng target database có thể cần **partition key + sort key** để hỗ trợ queries.

Ví dụ access patterns:

~~~text
Get order by ID
List orders for tenant + customer, newest first
Find pending orders by merchant + day
Update one order using version predicate
```

Một thiết kế DynamoDB minh họa có thể dùng:

~~~text
Table PK: ORDER#<orderId>
Table SK: METADATA
GSI1PK: CUSTOMER#<tenantId>#<customerId>
GSI1SK: <createdAt>#<orderId>
```

Đây là một phương án ví dụ, không phải lựa chọn tối ưu cho mọi dataset.

### 10.1. Ghi key invariants

- ID unique toàn cầu hay chỉ trong tenant?
- ID có thể đổi không?
- Partition key immutable?
- Có composite key?
- Có thể một tenant gây hot key không?
- Có cần query theo time range?
- Có legacy records thiếu tenantId?
- Sort order cần tie-breaker không?

### 10.2. Key collision

Nếu hai nguồn đều có `_id="123"` nhưng thuộc tenants khác, hợp nhất sang một bảng dùng ID đơn sẽ overwrite. Phải có namespace/tenant-aware composite identity.

### 10.3. Key skew

Một `merchantId` cực lớn được chọn làm partition key cho tất cả writes có thể nóng. Inventory cần top-N key distributions và peak writes/s theo key/partition cohort.

### 10.4. Những key được generated bởi server

Nếu app dựa vào server-generated ID, target key generation strategy thay đổi có thể ảnh hưởng idempotency và workflow tạo nhiều records; cần contract cho lúc ID được tạo và được trả lại.

---

## 11. Inventory query: danh sách operation chứ không chỉ vài câu lệnh mẫu

Mẫu hồ sơ một query:

~~~yaml
queryId: Q-ORDERS-002
owner: order-api
sourceEndpoint: GET /v1/customers/{id}/orders
sourceStore: orders-main
operation: LIST
filters:
  - tenantId = currentTenant
  - customerId = inputCustomer
sort:
  - createdAt DESC
  - orderId DESC
projection:
  - id
  - status
  - totalAmount
  - createdAt
pagination:
  type: keyset
  pageSizeP99: 100
consistencyRequirement: "fresh enough for account history"
traffic:
  steadyQps: 120
  peakQps: 1400
latencyTarget:
  p99Millis: 180
evidence:
  - "APM trace group"
  - "Owner-reviewed API contract"
status: OBSERVED_AND_REVIEWED
```

YAML này chỉ minh họa một bản kiểm kê, không phải file info của bài học.

### 11.1. Phân nhóm query

- Point GET by primary key.
- Bounded range query.
- Secondary-index lookup.
- Filter + sort + pagination.
- Aggregation/group-by.
- Full-text/geospatial search.
- Batch scan/export.
- Conditional update.
- Multi-record transaction.
- Delete/TTL/soft-delete.
- CDC/outbox polling.
- Administrative/repair queries.

### 11.2. Ghi workload trọng số

Một query chạy 10.000 lần/giây cần ưu tiên khác query chạy 5 lần/ngày, nhưng query báo cáo thuế hiếm chạy có thể là **functional blocker** lớn hơn một query phổ biến.

### 11.3. Ghi kết quả và thứ tự

Không chỉ `WHERE` mà còn default sort, projection, pagination token semantics, limit behavior, NULL matching, duplicate rows và total count policy.

---

## 12. Phát hiện query từ những nguồn nào?

### 12.1. Code static inventory

Tìm repository/DAO/query builder, raw query strings, Criteria API, CQL statements, SDK calls, aggregation pipelines và Redis commands.

### 12.2. Telemetry/runtime inventory

APM traces, database profiler/slow logs, driver metrics, index usage stats, query shapes, request throughput, p95/p99, retries.

### 12.3. Jobs và tích hợp bên ngoài

Cron, Airflow/ETL, Spark jobs, BI dashboards, support scripts, import tools, migration workers, serverless functions.

### 12.4. Unknown clients

Nếu database logs có một account/connection nhưng không có owner, đừng bỏ qua. Ghi `UNKNOWN_OWNER` và điều tra trước cutover.

### 12.5. Không suy “không có trace” là “không có query”

Sampling có thể bỏ qua low-volume operations; slow logs không ghi những query nhanh; những job cuối tháng chưa chạy trong cửa sổ quan sát.

### 12.6. Sampling theo thời gian

Ghi phạm vi:

~~~text
7 ngày: daily API
30 ngày: weekly/monthly workloads
90 ngày hoặc owner-confirmed: quarter-end processes
Peak campaign: burst access patterns
```

Không có cửa sổ nào đảm bảo đầy đủ 100%; kết hợp bằng chứng.

---

## 13. Query shape và tham số: đừng lưu PII trong profiler catalog

Hai queries có thể cùng shape nhưng tham số khác:

~~~javascript
db.orders.find({
  tenantId: "<tenant>",
  customerId: "<customer>"
}).sort({ createdAt: -1 }).limit(50);
~~~

Không đưa `tenantId` thật, email, địa chỉ hoặc số thẻ vào báo cáo rộng rãi.

### 13.1. Dùng fingerprint

Có thể chuẩn hóa query thành:

~~~text
collection=orders
filters=[tenantId:eq,customerId:eq]
sort=[createdAt:desc]
projection=[id,status,totalAmount]
pagination=limit
```

### 13.2. Nhưng shape không bao trùm skew

Cùng query shape với customer có 2 orders khác customer có 3 triệu orders. Cần đo **cardinality distribution và heavy cohorts** mà không lộ danh tính.

### 13.3. Kích thước kết quả

Ghi p50/p95/p99 rows và bytes returned. Một query trả 10.000 rows có thể tiêu tốn network/memory hơn 100 point reads nhỏ.

### 13.4. Frequency không là latency

Một query hiếm nhưng gây full collection scan trong lúc batch có thể chiếm I/O và ảnh hưởng p99 của toàn cụm.

---

## 14. Inventory index: index nào đang phục vụ hợp đồng nào?

Một index có thể tồn tại vì:

- Point lookup.
- Query filter.
- Sort.
- Uniqueness.
- TTL cleanup.
- Full-text search.
- Sparse/partial conditions.
- Geospatial lookup.
- Covering/projection.
- Optimistic concurrency access.

### 14.1. Mối quan hệ nhiều-nhiều

Một query có thể dùng nhiều indexes khác nhau theo parameter/selectivity; một index phục vụ nhiều query shapes.

### 14.2. Ghi trạng thái index

- Definition: field order, sort direction, type.
- Partial/sparse/filter conditions.
- Collation/case rules.
- Uniqueness scope.
- Usage metrics theo quan sát.
- Build cost, size và maintenance write overhead.
- Target access path/GSI/materialized view.
- Backfill/cutover readiness.

### 14.3. Không chọn target index từ tên source index

Một MongoDB compound B-tree index có thể hỗ trợ filter/sort theo prefix; DynamoDB GSI yêu cầu key access và có eventual consistency semantics riêng; Cassandra CQL không thể tùy ý lọc/sort như MongoDB; Redis key access khác hẳn. Cần map **truy vấn thực**.

### 14.4. Drop index là thay đổi contract

Một index ít dùng nhưng phục vụ emergency investigation hoặc quarter-end export vẫn có thể quan trọng. Cần owner đánh dấu chấp nhận drop hoặc có replacement.

---

## 15. Inventory truy vấn phân trang và thứ tự

### 15.1. Offset pagination

Một API dùng `skip/limit` có thể có semantics khác ở hệ mới; large offsets có thể rất đắt và nếu dữ liệu thêm/xóa đồng thời, trang có thể trùng/thiếu records.

### 15.2. Keyset/cursor pagination

Cần một sort key ổn định và tie-breaker, ví dụ `(createdAt, orderId)`; nếu chỉ sort `createdAt`, nhiều records cùng timestamp sẽ có thứ tự không ổn định.

### 15.3. Cursor opaque

MongoDB cursor, Cassandra paging state và DynamoDB `LastEvaluatedKey` **không thay thế nhau**. Không tiếp tục sử dụng opaque paging token của engine cũ sau cutover trừ khi API có translation/version mechanism hợp lệ.

### 15.4. API contract về `nextPageToken`

Nếu clients có thể lưu token vài giờ/ngày, cần lifecycle plan cho tokens được phát trước cutover:

- Có chấp nhận tokens cũ tới hết hạn?
- Token version/issuer?
- Có cần routing request trở lại nguồn cũ?
- Trả mã lỗi nào nếu token không còn hợp lệ?
- Có đảm bảo không lặp/thiếu record khi chuyển giữa các trang?

### 15.5. Count semantics

`totalCount` có cần exact theo snapshot nhất quán hay chỉ approximate? Một engine mới có thể không hỗ trợ exact count rẻ cho cùng query.

---

## 16. Inventory read consistency và freshness

Hợp đồng cần mô tả không chỉ “read eventually consistent”, mà **operation nào cần thấy cái gì sau khi nào**.

### 16.1. Read-your-writes

Sau khi cập nhật địa chỉ giao hàng và nhận 200, người dùng đọc lại có cần thấy ngay giá trị mới không?

### 16.2. Monotonic reads

Một người đã thấy order `PAID` không nên thấy nó lùi về `PENDING` do chuyển đọc sang replica khác, trừ khi nghiệp vụ cho phép rollback trạng thái có kiểm soát.

### 16.3. Strong/linearizable operations

Một inventory decrement hoặc one-time token redemption có thể yêu cầu atomic conditional check/update; một cache eventual read không đủ bảo vệ bất biến.

### 16.4. Stale-tolerant reads

Recommendations/analytics có thể chấp nhận trễ theo một SLO rõ (ví dụ 5 phút), thay vì ghi chung chung “eventual”.

### 16.5. Đặc điểm engine

- MongoDB có read concerns, read preferences và session semantics theo deployment.
- Cassandra có consistency levels cho mỗi operation; không suy từ `R+W>N` một mình rằng mọi truy vấn đều linearizable.
- DynamoDB base-table reads có lựa chọn consistent read trong phạm vi hỗ trợ, trong khi GSI reads có eventual consistency.
- Redis Cluster failover với replication async không mặc định bảo toàn mọi write đã ACK trên primary cũ.
- Elasticsearch search/index refresh tạo near-real-time visibility riêng.

### 16.6. Một record mới thấy ở target không chứng minh consistency

Kiểm xuyên nhiều clients, concurrent writes, failover và các reads từ replicas khác nhau.

---

## 17. Inventory các lệnh ghi: hợp đồng về atomicity

Một bảng:

| Operation | Điều kiện trước khi ghi | Tác động | Atomicity cần |
|---|---|---|---|
| Create order | Request ID chưa tồn tại | Tạo order và outbox | Không tạo trùng |
| Reserve inventory | Available >= quantity | Giảm available, tăng reserved | Atomic per product/partition theo design |
| Update order status | Version = expected | Chuyển state, tăng version | Compare-and-set |
| Cancel order | Order not shipped | Đổi status + release reservation | Transaction/saga/reconciliation |
| Delete personal data | Authorized deletion | Tombstone/delete + downstream | Không hồi sinh sau restore |
| Batch import | Source event ID mới | Upsert many records | Idempotent replay |

### 17.1. `upsert` có thể nguy hiểm

Ở source, một `updateOne` chỉ sửa field A; ở target, một `PutItem` thay toàn item có thể vô tình xóa các fields không có trong payload.

### 17.2. Atomic update operators khác nhau

MongoDB `$inc` và `$set`, Cassandra conditional/LWT và DynamoDB `UpdateExpression`/`ConditionExpression` có semantics khác. Không chuyển các lệnh bằng cách map tên mà bỏ logic read-modify-write.

### 17.3. Idempotency

Retry sau timeout có thể gửi lại một write đã commit. Cần stable operation/request IDs và quy tắc duplicate detection.

### 17.4. Optimistic locking

Nếu source kiểm `version=7` trước khi đổi thành 8, target phải giữ điều kiện tương đương. Ghi đè không điều kiện làm lost updates.

### 17.5. Batch atomicity

“Batch write” có thể chỉ là nhiều writes gửi trong một request, không đảm bảo all-or-nothing. Cần ghi contract giao dịch và xử lý partial failure riêng.

---

## 18. Giao dịch đa record và bất biến nghiệp vụ

Ví dụ bất biến:

\[
\text{available}+\text{reserved}+\text{sold}=\text{totalStock}
\]

Nếu chuyển từ một transaction đa document sang nhiều writes độc lập, có thể tạm hoặc vĩnh viễn phá bất biến khi process crash.

### 18.1. Kiểm đúng transaction boundary

- Một item/document?
- Một partition?
- Nhiều items cùng partition?
- Nhiều collections/tables?
- Cross-service với payment?
- Client-side saga/outbox?

### 18.2. Target không cần mô phỏng mọi thứ y hệt nếu thay đổi được phê duyệt

Có thể chuyển sang reservation ledger, conditional writes, transactional API, saga và idempotent compensation. Nhưng đây là **design change**, không chỉ data copy; cần owner và contract tests.

### 18.3. Không cho phép “tạm sai vô hạn”

Nếu eventual reconciliation được chọn, phải có bound lag, conflict strategy và cơ chế phát hiện bất biến sai.

### 18.4. Ghi failover behavior

Nếu write outcome unknown khi primary failover, application sẽ query request ledger, retry idempotent hay gửi bù? Những quyết định này cần làm rõ trước migration.

---

## 19. Schema version, backward compatibility và rolling deployment

Trong nhiều hệ, app version cũ/mới chạy đồng thời:

~~~text
App v1 reads:
  status, total

App v2 reads:
  status, totalAmount, currency

Writer v2 begins writing:
  schemaVersion=2
```

Nếu app v1 không hiểu `totalAmount`, trong rolling rollout nó có thể crash.

### 19.1. Expand–migrate–contract

Một hướng tổng quát:

1. **Expand:** reader tương thích cả cũ/mới, writer có version nếu cần.
2. **Migrate:** backfill dữ liệu, metrics cảnh báo parse/mapping failures.
3. **Switch:** cutover reads/writes khi safety gates đạt.
4. **Contract:** chỉ bỏ old schema/code/index khi không còn consumers phụ thuộc.

### 19.2. Forward/backward compatibility

- **Backward compatible reader:** code mới đọc được dữ liệu cũ.
- **Forward compatible reader:** code cũ không phá khi gặp trường mới trong phạm vi được thiết kế.
- **Writer compatibility:** writer mới không làm consumers cũ sai.

### 19.3. Unknown enums

Nếu client cũ gặp `REFUNDED_PARTIALLY`, không được âm thầm coi là `PAID` nếu thay đổi quyền/hậu quả tài chính. Cần explicit unknown state policy.

### 19.4. Rollback window

Nếu writer mới bắt đầu tạo dữ liệu không thể đọc bởi binary cũ, rollback code mà không có downgrade migration sẽ thất bại. Inventory phải ghi **khả năng đọc hai chiều** hoặc đánh dấu điểm không thể rollback trực tiếp.

---

## 20. TTL, soft delete, hard delete và retention

### 20.1. TTL không có nghĩa delete đúng giây

Nhiều engine cleanup bất đồng bộ. Nếu business yêu cầu token hết hạn lúc 10:00, application phải kiểm expiry field khi sử dụng, không chỉ trông chờ physical cleanup.

### 20.2. Soft delete

Một record `deletedAt != null` có thể vẫn tồn tại trong database; query cũ có thể mặc định lọc đi. Nếu target query quên filter, người dùng thấy lại dữ liệu đã xóa.

### 20.3. Tombstones

Cassandra dùng tombstones với repair/GC semantics; MongoDB soft delete hay DynamoDB TTL không tự giống Cassandra tombstones. Không map thuật ngữ “delete” mà bỏ lifecycle.

### 20.4. GDPR/privacy/retention

Dữ liệu đã được xóa khỏi primary có thể còn trong backup, CDC, archive hoặc search index theo chính sách. Migration cần bảo vệ deletion correctness và scope tuân thủ, không tự nhân bản dữ liệu đã quá retention.

### 20.5. Legal hold

Một dataset có retention exception phải được đánh dấu; không áp TTL mới cho tất cả records nếu có legal hold hoặc financial recordkeeping.

### 20.6. Restore cũ

Migration thường có rollback/restore; một backup cũ có thể hồi sinh revoked permissions hoặc deleted PII. Cần deletion ledger/reconciliation policy.

---

## 21. CDC, outbox và sự kiện: đây cũng là application contract

Một số consumers không đọc database trực tiếp mà nhận events.

~~~text
Order write
  -> source NoSQL
  -> CDC/outbox
  -> Kafka/event stream
  -> search projector
  -> notification worker
  -> audit sink
```

### 21.1. Kiểm kê event schema

- Topic/stream/collection name.
- Event key/partitioning.
- Payload schema/version.
- Change type: insert/update/delete.
- Before/after images.
- Stable event ID và source version.
- Ordering guarantees.
- Retry/duplicate/redelivery behavior.
- Dead-letter queue.
- Retention/compaction/tombstone behavior.
- Consumer checkpoint/resume token.
- Data sensitivity.
- Consumer owner.

### 21.2. Ordering không tự chuyển hệ

MongoDB Change Streams, DynamoDB Streams, Kafka partitions và Cassandra CDC có các thứ tự/phạm vi riêng. Không lấy commit timestamp làm thứ tự toàn cục nếu protocol không bảo đảm.

### 21.3. Exactly-once không thể suy từ connector

Nếu consumer nhận event trùng sau retry, phải idempotent theo event ID/source version. Transactional outbox có thể bảo vệ atomicity giữa business record và intent phát sự kiện trong một storage boundary được hỗ trợ.

### 21.4. Delete events

Trong một số hệ, delete có tombstone/null payload hoặc TTL-generated stream event. Downstream phải hiểu và không resurrect record bằng event đến muộn.

### 21.5. Rebootstrap

Nếu consumer vượt log retention hoặc resume token hết hạn, cần resnapshot + tail changes với watermark/cutover phù hợp. Không skip changes rồi báo đồng bộ thành công.

---

## 22. Hợp đồng bảo mật là một phần của migration

Danh sách cần kiểm:

- Authentication: password/token/mTLS/IAM.
- Roles và quyền read/write theo collection/table/index.
- Tenant isolation.
- Field-level access/redaction.
- Data residency/region.
- Encryption at rest và TLS in transit.
- KMS keys, truststores, secrets rotation.
- Audit trail và privileged operations.
- Data masking trong staging.
- Retention và deletion requests.
- Backup/restore access boundaries.
- Log/trace data exposure.

### 22.1. Truy vấn thiếu tenant filter

Nếu source dùng một database riêng cho mỗi tenant, nhưng target gộp tenant vào một table, một point lookup theo `orderId` không kèm tenant authorization có thể tạo cross-tenant data exposure.

### 22.2. Security không chỉ là database ACL

Một app account có quyền đọc table nhưng tầng API phải kiểm chủ sở hữu bản ghi theo tenant. Đổi key/index có thể làm bug filter xuất hiện.

### 22.3. Không đưa production PII vào test environment tùy tiện

Dùng synthetic data hoặc masking được phê duyệt. Một migration test thành công không đáng đánh đổi rò dữ liệu.

### 22.4. Security rollback

Nếu chuyển sang role model mới, rollback có thể làm old app nắm quyền rộng hơn hoặc thiếu quyền cần thiết. Ghi mappings và test cả chiều rollback.

---

## 23. Hợp đồng về lỗi, retry và timeout

Ví dụ một API trả:

~~~text
404: Order không tồn tại
409: Conflict/version mismatch
429: Rate limited
503: Dependency temporarily unavailable
504: Timeout, write outcome may be unknown
```

### 23.1. Engine errors không tương đương API errors

Một `ConditionalCheckFailed` trong target có thể map sang 409, không phải 500. Một `ProvisionedThroughputExceeded` có thể cần bounded retries/backoff và báo 429/503 tùy contract.

### 23.2. Timeout không chứng minh write thất bại

Server có thể commit nhưng response bị mất. Migration cần giữ operation IDs, idempotency và cách tra cứu kết quả.

### 23.3. Retry budget

Nếu target throttles, retries không giới hạn sẽ tạo thác tải. Ghi max attempts, deadline, jitter/backoff và khi nào không retry.

### 23.4. Pagination/partial results

Một scan có thể trả kết quả từng trang; timeout ở giữa không đồng nghĩa toàn bộ query atomic. API cần quy định resume token và failure handling.

### 23.5. Exception types

Nếu code Java ở nhiều nơi bắt các exception của driver cũ, thay driver có thể làm logic retry/breaker bị bỏ qua. Inventory phải liệt kê exception mapping trong repository adapter và handlers.

---

## 24. Hợp đồng về latency, throughput và cost

Trước di chuyển, ghi baseline theo operation:

| Operation | Peak QPS | p99 target | Typical/result size | Criticality |
|---|---:|---:|---|---|
| Get order by ID | 10k/s | 80 ms | 2 KiB | Critical |
| List customer orders | 2k/s | 180 ms | 50 rows | High |
| Reserve inventory | 5k/s | 100 ms | Conditional write | Critical |
| Export daily settlement | 2/day | 30 min batch | Millions rows | High |
| Search orders | 700/s | 400 ms | 20 hits | Medium |
| Reconcile payment | 1/day | 1 hour | Aggregations | Critical completeness |

Số trong bảng là giả định minh họa, không phải benchmark.

### 24.1. Tách peak khỏi average

Một endpoint trung bình 100 QPS nhưng 20k QPS trong sự kiện promotion có thể gây hot-key throttling ở target.

### 24.2. Read/write amplification

Một API trước đây cần 1 DB request, sau khi denormalize có thể cần 5 writes đồng thời. Đo target operation count và chi phí read/write capacity, không chỉ latency của từng call.

### 24.3. Data egress và backfill

Cross-region migration có network egress cost và giới hạn throughput, chưa tính dual-write, CDC và index backfill.

### 24.4. p99 không là server execution time

Client pool wait, retries, TLS, network, serialization và fanout đều ảnh hưởng. Instrument ở request logical và driver attempts.

### 24.5. Đặt acceptance gates có thể đo

Không ghi “performance tốt”. Ghi rõ p95/p99, error rate, throttling, saturation, TTL/index lag, consistency tests và chi phí tối đa được duyệt.

---

## 25. Chọn phạm vi inventory theo thời gian và tổ chức

### 25.1. Theo hệ thống

Source database, app repositories, stream processors, jobs, admin tools, runtime telemetry.

### 25.2. Theo thời gian

- Peak.
- Giờ thấp tải.
- Cuối ngày/tuần/tháng.
- Promotion campaigns.
- Retention/TTL expiry cycles.
- Replication/failover/backup windows.
- Quarterly compliance/export tasks.

### 25.3. Theo data cohorts

- Active/historical.
- Soft-deleted.
- Expired/near-expiry.
- Legacy schema versions.
- Hot and cold tenants.
- Large documents/partitions.
- Known outliers.
- Security-sensitive entities.

### 25.4. Theo actor

- API clients.
- Internal background workers.
- Support operators.
- External partners.
- Unknown service accounts.
- Disaster recovery/backup tooling.

### 25.5. Mỗi inventory entry cần bằng chứng và confidence

Ví dụ:

~~~text
Q-042:
  source=APM+code-review
  observed=2026-11-01..2026-11-14
  ownerReviewed=yes
  confidence=HIGH

Q-043:
  source=quarterly-report-owner
  runtimeObserved=no
  confidence=MEDIUM
  action=run controlled replay before cutover
```

Không coi MEDIUM/UNKNOWN là “đã xong” nếu contract critical.

---

## 26. Template Data Contract Catalog

Có thể biểu diễn mỗi asset bằng YAML đã quản trị phiên bản:

~~~yaml
assetId: orders-main
owner:
  business: order-domain
  engineering: order-platform
source:
  engine: MongoDB
  clusterAlias: prod-orders
  database: commerce
  collection: orders
  region: region-a
authority: PRIMARY_SOURCE_OF_TRUTH
scope:
  tenants: all
  excludedCohorts:
    - legal-hold-reviewed-separately
schema:
  currentVersions: [1, 2, 3]
  idRule: tenantId + orderId
  nullableFields:
    - couponCode
  schemaDriftObserved: true
workload:
  peakReadsPerSecond: 12000
  peakWritesPerSecond: 7000
  targetMaxLagSeconds: 5
retention:
  defaultDays: 365
  deletePropagationRequired: true
security:
  sensitivity: RESTRICTED
  tenantIsolationRequired: true
migration:
  targetAssetId: orders-v2
  backfillSourceVersion: pending
  cutover: not-approved
  rollbackWindowHours: 48
  unknowns:
    - "legacy records without tenantId"
  ownersApproved: false
~~~

### 26.1. Template không thay dữ liệu đo

Một người điền `peakWritesPerSecond: 7000` phải ghi nguồn và khoảng thời gian. Nếu thiếu evidence, đánh dấu assumed estimate.

### 26.2. Giữ catalog là artifact có version

Đổi query/schema/feature flag phải cập nhật catalog hoặc tạo migration delta. Một file tĩnh được duyệt một lần rồi bỏ quên không đủ để bảo vệ cutover.

### 26.3. Không lưu secrets/raw PII

Catalog chỉ lưu references/metadata. Secret values, token và personal data không nên vào Git hoặc reports.

---

## 27. Template Query Contract Catalog

~~~yaml
queryId: Q-CUSTOMER-ORDER-LIST
consumer: order-web-api
operation: LIST
logicalEntity: Order
source:
  engine: MongoDB
  collection: orders
parameters:
  - name: tenantId
    type: string
    required: true
  - name: customerId
    type: string
    required: true
filter:
  - tenantId EQ
  - customerId EQ
sort:
  - createdAt DESC
  - orderId DESC
pageSizeMax: 100
resultContract:
  stableOrdering: true
  noCrossTenantRecords: true
  nullHandling: preserve
  paginationTokenCompatibility: "versioned"
consistency:
  readYourWritesRequired: true
failureSemantics:
  notFoundStatus: 404
  timeoutHandling: bounded-retry
observability:
  metricName: nosql.client.operation
  peakQpsObserved: 1400
  resultBytesP99: 102400
target:
  tableOrIndex: orders_by_customer
  gap: "GSI freshness and read-your-writes"
validation:
  owner: order-platform
  contractTests: pending
~~~

Một query entry nên nói rõ **những gì chắc chắn chưa giải quyết**, không chỉ target mapping. Nếu `readYourWritesRequired` mà target GSI eventual, đó là design blocker cần phương án, không phải một field tùy chọn được bỏ qua.

---

## 28. Ma trận Source → Target cho từng operation

Ví dụ MongoDB → DynamoDB:

| Operation | Source behavior | Target candidate | Gap cần quyết định |
|---|---|---|---|
| GET by ID | `_id` lookup | `GetItem` PK | ID+tenant key mapping |
| List by customer/date | Compound index filter/sort | Query GSI | GSI eventual, tie-breaker |
| Increment counter | `$inc` atomic | UpdateExpression ADD/SET | Bounds/conditions |
| CAS version | Filter `{id,version}` + `$inc` | ConditionExpression | Missing version cases |
| Multi-document update | Transaction | Transaction API hoặc redesign | Transaction limits/cost |
| Aggregation by month | Aggregation pipeline | Materialized report / analytics | Not a direct Query equivalent |
| Delete expired sessions | TTL index | DynamoDB TTL + app expiry check | Physical cleanup asynchronous |
| Stream changes | Change Streams | DynamoDB Streams/outbox | Payload, order, retention |
| Scan export | Bounded cursor | Parallel Scan/export | Consistency, throttle, resumability |

Đây là **bảng điều tra**, không phải hướng dẫn chuyển đổi tự động.

### 28.1. Không gán `1 source query = 1 target query`

Một query aggregation có thể cần precomputed view, event stream hoặc external analytics. Ngược lại, vài queries source có thể được gộp target bằng một access pattern mới.

### 28.2. Chênh lệch nhất quán là blocker thiết kế

Nếu source có một transaction multi-doc còn target candidate không thể bảo đảm invariant trong giới hạn API/partition đã chọn, phải **thiết kế lại workflow**, không chỉ thay driver.

### 28.3. Đo thêm writes cho indexes/read models

Một API tạo order có thể cần update multiple materialized views. Chi phí và failure-handling thay đổi; inventory mutation phải bao phủ tất cả derived writes.

---

## 29. Cassandra: keyspace, partition/clustering keys và truy vấn

Cassandra dùng data model rất phụ thuộc access patterns.

Ví dụ:

~~~sql
CREATE TABLE orders_by_customer (
    tenant_id text,
    customer_id text,
    created_at timestamp,
    order_id uuid,
    status text,
    amount_minor bigint,
    PRIMARY KEY (
        (tenant_id, customer_id),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

### 29.1. Điều cần kiểm kê

- Keyspace/table và replication strategy per DC.
- Partition key/clustering columns.
- Partition size p50/p99/top outliers.
- Query shapes và `ALLOW FILTERING`/secondary index usage.
- TTL/default TTL và tombstones.
- Consistency levels per read/write.
- LWT/conditional updates.
- Batch semantics.
- Materialized views/indexes/SAI theo bản cài.
- Repair/compaction strategy.
- CQL schema/migrations và Java driver mapping.

### 29.2. Không suy Cassandra là relational SQL

Query `WHERE status='PAID' ORDER BY created_at DESC` trên toàn dataset có thể không phù hợp một base table hiện tại. Thường cần table/read model định hướng truy vấn hoặc external search/analytics.

### 29.3. Tính partition growth

Nếu dùng `(tenantId,customerId)` và một customer có hàng triệu orders, partition size có thể gây vấn đề. Migration inventory cần distribution và buckets, không chỉ trung bình.

### 29.4. Consistency không “giữ nguyên” bằng tên gọi

`LOCAL_QUORUM`, `ONE`, LWT và counters có semantics riêng; cần map business contract cụ thể.

---

## 30. MongoDB: document shape, aggregation và index semantics

Một nguồn MongoDB có thể dùng:

~~~javascript
db.orders.find(
  {
    tenantId: "<tenant>",
    customerId: "<customer>",
    deletedAt: { $exists: false }
  },
  {
    _id: 1,
    status: 1,
    totalAmount: 1,
    createdAt: 1
  }
).sort({ createdAt: -1, _id: -1 }).limit(100);
~~~

### 30.1. Kiểm toàn bộ pipeline

Một aggregation có `$lookup`, `$group`, `$unwind`, `$facet`, `$sort`, `$merge` hay computed fields không nhất thiết chuyển sang target NoSQL một cách trực tiếp. Ghi source query shape và output contract.

### 30.2. Index definitions

Compound, partial, TTL, collation, unique, text/geospatial indexes có thể là phụ thuộc vô hình của application. Ghi index sizes/usage và target replacement.

### 30.3. BSON types

ObjectId, Decimal128, Date, Binary và null/missing cần mapping. Không serialize BSON ObjectId thành string rồi ngầm suy order/time semantics giữ nguyên.

### 30.4. Write concerns và sessions

Chú ý transactions, read concern, retryable writes, read preferences và causal/session semantics đã được ứng dụng sử dụng.

### 30.5. Change Streams

Resume tokens và event payloads cần version/discovery/retention plan. Không thể cứ copy token MongoDB sang stream target.

---

## 31. DynamoDB: keys, GSIs và item constraints

Một migration tới/từ DynamoDB phải kiểm kê:

- Table key schema và item attributes.
- GSIs/LSIs, projected attributes và access patterns.
- ConditionExpressions/transaction APIs.
- Per-item/transaction/operation size limits theo service version.
- Read consistency (base table vs GSIs).
- RCU/WCU hoặc on-demand traffic behavior.
- Hot partition/key distribution.
- TTL attribute semantics.
- Streams, event views, retention.
- PITR/backup/restore behavior.
- IAM policies, encryption keys và region/account.
- SDK retries/throttling.

### 31.1. Không biến filter expression thành primary access path

Nếu target query lấy rất nhiều items từ một partition rồi mới filter `status='PAID'`, consumed capacity có thể tăng dù output chỉ vài records.

### 31.2. GSI không tự giữ cùng read freshness

Một GSI có asynchronous propagation; nếu hợp đồng đòi người dùng đọc lại ngay sau ghi, cần giải pháp alternate read path, session cache, read-through authority hoặc sửa contract có chủ đích.

### 31.3. Data model theo item size

Một MongoDB document lớn chuyển nguyên thành một DynamoDB item có thể vượt giới hạn kích thước item được hỗ trợ. Cần inventory p99/max item sizes và thiết kế split/object storage.

### 31.4. Target-specific cost

Queries và writes có chi phí theo throughput/items/indexes; kiểm kê phải đủ để mô hình chi phí và thử peak.

---

## 32. Redis: key patterns, TTL và atomic scripts

Nếu nguồn/đích có Redis, đừng chỉ đếm keys.

### 32.1. Key namespace

~~~text
session:<user>
cart:<tenant>:<user>
idempotency:<operationId>
ratelimit:<tenant>:<window>
catalog:<sku>
~~~

### 32.2. Data structures

String, hash, list, set, sorted set, stream, probabilistic structures hoặc modules có APIs và semantics khác nhau.

### 32.3. TTL

Đo TTL distribution và tỷ lệ keys không có TTL. Một key đã expired có thể bị cleanup bất đồng bộ. Migration cần preserve *logical expiration time*, không chỉ copy TTL remaining rồi tạo expiry mới sai.

### 32.4. Atomicity

Lua scripts/transactions/SET NX, locks, counters và compare logic có thể là contract critical. Không thay `SET NX` bằng hai lệnh GET rồi SET.

### 32.5. Redis Cluster

Hash slots, key tags, multi-key command constraints, MOVED/ASK redirect và replication/failover ảnh hưởng correctness khi đổi topology.

### 32.6. Role của Redis

Nếu chỉ derived cache, có thể chọn rebuild thay vì data transfer. Nếu có idempotency/queue authority, không được áp cùng chiến lược.

---

## 33. Elasticsearch/OpenSearch: mapping và search semantics

Một index search không chỉ có documents:

- Analyzer/tokenizer/normalizer.
- Mapping: text vs keyword, numeric/date.
- Nested vs object fields.
- Collation/fuzzy scoring.
- Sorting/missing values.
- Synonyms và language rules.
- Ingest pipelines.
- Aliases/data streams/rollover/ILM.
- Refresh visibility và index lag.
- Search query DSL.
- Pagination (`search_after`, PIT context hoặc other).
- Replicas/shard placement.
- Security/document-level restrictions.

### 33.1. Thứ tự search có thể khác

Nếu relevance scoring/analyzers đổi, cùng keyword có thể trả thứ tự khác. “Dữ liệu bằng nhau” chưa có nghĩa search API contract đạt.

### 33.2. Count và deleted docs

Segment cleanup là bất đồng bộ; số bytes/index docs và query results cần được kiểm theo semantics, không dùng filesystem size làm oracle duy nhất.

### 33.3. Aliases và zero-downtime cutover

Cần inventory alias consumers và query endpoints, không chỉ concrete index names. Chuyển alias có thể là cutover point nhưng phải bảo đảm ingest CDC và read consistency tương ứng.

---

## 34. Kiểm kê quan hệ và denormalization

NoSQL thường lưu dữ liệu trùng để tối ưu truy vấn:

~~~text
orders/{orderId}
orders_by_customer/{customerId}/{createdAt}/{orderId}
orders_by_merchant/{merchantId}/{createdAt}/{orderId}
```

### 34.1. Quan hệ phụ thuộc

- Entity chính có những children nào?
- Một-nhiều hay nhiều-nhiều?
- Dữ liệu embedded hay referenced?
- Có orphan records?
- Cascading deletes được ứng dụng triển khai như thế nào?
- Update parent có fan-out tới bao nhiêu projections?
- Có event sourcing/ledger đứng sau không?

### 34.2. Đừng sao chép cùng record nhiều lần rồi đếm nhầm

Một fact có thể được denormalize trong 3 tables; kiểm kê cần lineage và dedup identifiers.

### 34.3. Referential integrity nằm ở đâu?

Không thể giả định database target có foreign keys tương đương. Nếu invariant đang được application/consumer bảo vệ, phải ghi và test.

### 34.4. Split/merge model

Tách một document thành nhiều items có thể thay đổi atomicity và partial read behavior. Hợp đồng API có cần trả đủ children cùng version không?

---

## 35. Dữ liệu lịch sử: không được đo mỗi active data

Những cohort dễ bị bỏ sót:

- Orders 5 năm trước.
- Records chưa có `schemaVersion`.
- IDs được tạo bởi hệ cũ.
- Soft-deleted/archived.
- Legal hold.
- Documents quá lớn.
- Null/missing tenantId.
- Unicode/emoji/language-specific text.
- Timezones lạ hoặc DST.
- Retry duplicates.
- Out-of-order CDC events.
- Tombstones đã chưa cleanup.
- Manually corrected records.

### 35.1. Chọn sample theo tuổi

Kết quả mapping của records viết hôm qua có thể tốt nhưng dữ liệu tạo từ ba phiên bản ứng dụng trước khác hẳn.

### 35.2. Quarantine thay vì silently drop

Nếu gặp malformed record, ghi immutable reference, error code và owner xử lý. Không bỏ qua rồi báo backfill hoàn tất vì count job processing đạt 100%.

### 35.3. Có thể cần remediation trước backfill

Đôi khi sửa schema drift ở source theo quy trình có kiểm soát tốt hơn viết hàng chục conversion branches không rõ. Nhưng phải cân nhắc audit/rollback và không đổi business facts thiếu phê duyệt.

---

## 36. Lập profile chất lượng dữ liệu

Đối với mỗi asset:

| Kiểu kiểm | Ví dụ | Oracle |
|---|---|---|
| Completeness | `tenantId` missing | Tỷ lệ và danh sách an toàn |
| Type conformity | `totalAmount` numeric/decimal | Mapping không mất precision |
| Uniqueness | `(tenantId,orderId)` | Không collision |
| Valid values | `status` trong enum set | Legacy values có policy |
| Referential integrity | Order → customer/invoice | Không orphan không được chấp nhận |
| Temporal consistency | `updatedAt >= createdAt` | Exceptions được giải thích |
| Business invariant | `paidAmount <= authorizedAmount` | Finance owner duyệt |
| Freshness | CDC lag | SLA cho target |
| Delete correctness | `deletedAt`/tombstone | Không resurrect |
| Security | Cross-tenant references | Không rò dữ liệu |
| Size constraints | Max item/document size | Không bỏ record vì giới hạn |
| Encoding | UTF-8, binary, timezone | Reversible/approved loss |

### 36.1. Định nghĩa `0 lỗi` khi nào?

Với payment/idempotency/tenant isolation, có thể cần zero unreviewed violations. Với dữ liệu cache có thể rebuild, business có thể chấp nhận một error budget. Quyết định phải theo hợp đồng, không do migration script tự đặt.

### 36.2. Checksum cần canonicalization

Nếu source BSON và target JSON có representation khác, hash raw bytes sẽ không khớp dù nghĩa tương đương. Dùng canonical logical representation có định nghĩa trường/kiểu/sort/number/time rõ.

### 36.3. Counts chưa đủ

Hai tập đều 50 triệu records nhưng khác một triệu IDs vẫn có count bằng nhau. Cần ID coverage, content canonical checks, stratified samples và business invariants.

---

## 37. Hợp đồng Java: DTO, repository và driver behavior

Một ứng dụng Spring/Java có thể có những lớp:

~~~text
HTTP Controller
     |
Service / Domain
     |
Repository interface
     |
MongoDB-specific adapter
```

Migration tốt có thể bổ sung target adapter nhưng không tự động giữ contract nếu adapter mới trả giá trị khác.

### 37.1. Inventory DTO assumptions

- Required fields.
- Jackson serialization aliases.
- Default values.
- Enum unknown handling.
- BigDecimal/Instant mapping.
- Bean validation rules.
- Null and missing semantics.
- Immutable records/builders.
- UUID and binary encodings.

### 37.2. Inventory repository semantics

- Not found: `Optional.empty`, null hay exception.
- Writes: ack/conditional conflict/error mapping.
- Read consistency.
- Pagination behavior.
- Timeout and retry.
- Transaction boundaries.
- Soft-delete filtering.
- Tenant isolation.

### 37.3. Test bằng cùng interface contract

Một cách phát triển là chạy **một bộ contract tests** lên source adapter và target adapter. Kết quả khác nhau phải được phân loại intentional change hoặc blocker.

### 37.4. Không phụ thuộc vào driver exception ở tầng business

Nên map lỗi driver vào domain errors có nghĩa rõ, nếu không controller có thể trả 500 thay vì 409 sau migration.

---

## 38. Java: mô hình `QueryContract` cho việc kiểm kê

Ví dụ Java 17 sau **định nghĩa metadata về access pattern**. Nó không chạy truy vấn và không chứng minh target đáp ứng contract; mục đích là tạo cấu trúc để review.

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public record QueryContract(
    String queryId,
    String consumer,
    Operation operation,
    String assetId,
    List<String> filterFields,
    List<String> sortFields,
    Set<String> projectedFields,
    boolean tenantBound,
    boolean readYourWritesRequired,
    Duration p99Target,
    int maxPageSize
) {
    public enum Operation {
        POINT_READ, LIST, SEARCH,
        CONDITIONAL_WRITE, DELETE, AGGREGATE
    }

    public QueryContract {
        Objects.requireNonNull(queryId);
        Objects.requireNonNull(consumer);
        Objects.requireNonNull(operation);
        Objects.requireNonNull(assetId);
        filterFields = List.copyOf(filterFields);
        sortFields = List.copyOf(sortFields);
        projectedFields = Set.copyOf(projectedFields);
        Objects.requireNonNull(p99Target);

        if (queryId.isBlank() || assetId.isBlank()) {
            throw new IllegalArgumentException(
                "Query ID and asset must be nonblank"
            );
        }
        if (p99Target.isNegative() || p99Target.isZero()) {
            throw new IllegalArgumentException(
                "Latency objective must be positive"
            );
        }
        if (maxPageSize < 0) {
            throw new IllegalArgumentException(
                "Page size cannot be negative"
            );
        }
    }
}
~~~

### 38.1. Không lấy record này làm hoàn chỉnh

Contract thực còn bao gồm correctness, pagination token, errors, durability, consistency, filters operators, SLO measurement window và dependencies. Cấu trúc trên có thể mở rộng hoặc dùng YAML schema thực tế.

### 38.2. `tenantBound=true` là lời khai, cần test

Từ code/config mà owner khai rằng endpoint tenant-bound chưa chứng minh no cross-tenant leaks; cần negative security tests.

### 38.3. Tên query ổn định

Một `queryId` ổn định giúp nối telemetry, owner approval, migration design và validation report, ngay cả khi implementation chuyển driver.

---

## 39. Java Micrometer: đo query shapes không lộ dữ liệu

Đo từ repository boundary có thể giúp kiểm kê workload.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.Objects;
import java.util.function.Supplier;

public final class RepositoryQueryMetrics {

    private final MeterRegistry registry;

    public RepositoryQueryMetrics(MeterRegistry registry) {
        this.registry = Objects.requireNonNull(registry);
    }

    public <T> T observe(
            String boundedQueryId,
            String engine,
            Supplier<T> action) {

        String id = boundedId(boundedQueryId);
        String store = boundedEngine(engine);

        Timer timer = Timer.builder(
                "nosql.repository.query.latency")
            .tag("query_id", id)
            .tag("engine", store)
            .register(registry);

        return timer.record(action);
    }

    private String boundedId(String id) {
        return switch (id) {
            case "Q-GET-ORDER" -> "Q-GET-ORDER";
            case "Q-LIST-ORDERS" -> "Q-LIST-ORDERS";
            case "Q-RESERVE" -> "Q-RESERVE";
            default -> "OTHER";
        };
    }

    private String boundedEngine(String engine) {
        return switch (engine) {
            case "mongo" -> "mongo";
            case "dynamo" -> "dynamo";
            case "cassandra" -> "cassandra";
            default -> "other";
        };
    }
}
~~~

### 39.1. Chỉ dùng bounded labels

Không gắn `customerId`, `orderId`, raw query string hoặc arbitrary tenant IDs làm tag. High-cardinality metrics có thể làm hệ giám sát quá tải và lộ thông tin nhạy cảm.

### 39.2. Đo synchronous đúng scope

`Timer.record(action)` đo hàm synchronous. Với async SDK trả `CompletionStage`, cần đo **tới khi stage completed**, không chỉ lúc trả future.

### 39.3. Bổ sung attempts và result

Production nên đo success/conflict/not-found/throttle/timeout, retry attempts, result bytes, pool wait và client/server latency. Chỉ p99 một metric không đủ chỉ ra migration regressions.

### 39.4. APM sampling bias

Nếu tracing sampling thấp, đừng dùng trace count làm tổng query frequency. Dùng metrics counters đáng tin hơn cho throughput, tracing cho root cause.

---

## 40. Java: contract tests cho null/missing và versioned write

Ví dụ định nghĩa interface có semantics rõ:

~~~java
import java.math.BigDecimal;
import java.util.Optional;

public interface OrderRepository {
    Optional<Order> findByTenantAndId(
        String tenantId,
        String orderId
    );

    boolean updateAmountIfVersionMatches(
        String tenantId,
        String orderId,
        long expectedVersion,
        BigDecimal newAmount
    );

    record Order(
        String tenantId,
        String orderId,
        BigDecimal amount,
        long version
    ) {}
}
~~~

Một bộ tests dùng chung cho source và target adapters:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.util.function.Supplier;
import org.junit.jupiter.api.Test;

public abstract class OrderRepositoryContractTest {

    protected abstract OrderRepository repository();
    protected abstract void seed(
        OrderRepository.Order order
    );

    @Test
    void wrongTenantCannotReadAnotherTenantsOrder() {
        seed(new OrderRepository.Order(
            "tenant-A", "o-1",
            new BigDecimal("100.00"), 2
        ));

        assertTrue(
            repository().findByTenantAndId(
                "tenant-B", "o-1"
            ).isEmpty()
        );
    }

    @Test
    void updateRejectsStaleVersion() {
        seed(new OrderRepository.Order(
            "tenant-A", "o-2",
            new BigDecimal("100.00"), 2
        ));

        boolean updated =
            repository().updateAmountIfVersionMatches(
                "tenant-A",
                "o-2",
                1,
                new BigDecimal("200.00")
            );

        assertFalse(updated);
        assertEquals(
            new BigDecimal("100.00"),
            repository().findByTenantAndId(
                "tenant-A", "o-2"
            ).orElseThrow().amount()
        );
    }
}
~~~

### 40.1. Test fixtures phải cô lập

Các tests cần database test container/namespace riêng và reset state. Không dùng order thật từ production để seed.

### 40.2. Contracts quan trọng nhưng chưa đủ

Unit/integration tests này không bao phủ concurrent races, network partition, failover hoặc consistency. Cần chaos/integration scenarios theo yêu cầu.

### 40.3. Không so `BigDecimal` thiếu scale policy

`new BigDecimal("100.00")` và `new BigDecimal("100.0")` có thể cùng giá trị số nhưng `equals` khác do scale. Domain contract cần định nghĩa canonical scale trước khi đối soát source/target.

### 40.4. Unknown/timeout

Adapter cần phân biệt conflict xác định với **outcome unknown** để tránh retry làm nhân transaction.

---

## 41. Java: so sánh canonical record thay vì raw JSON

Một migration có thể chuyển BSON Decimal128 sang Java BigDecimal, thay thứ tự fields và type encoding.

Một hàm canonicalization minh họa:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

public record CanonicalOrder(
    String tenantId,
    String orderId,
    long amountMinor,
    String currency,
    String status,
    Instant updatedAt,
    boolean deleted
) {
    public CanonicalOrder {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(currency);
        Objects.requireNonNull(status);
        Objects.requireNonNull(updatedAt);
    }

    public static long toMinorUnits(
            BigDecimal amount,
            int fractionalDigits) {
        return amount.movePointRight(
                fractionalDigits)
            .longValueExact();
    }
}
~~~

### 41.1. Chỉ canonicalize theo domain contract

Nếu currency có scale khác nhau, dùng ISO currency/minor unit mapping được phê duyệt; không mặc định mọi currency có hai chữ số thập phân.

### 41.2. Bảo vệ overflow

`longValueExact()` phát hiện giá trị vượt kiểu hoặc có phần thập phân không hợp lệ sau scaling. Tốt hơn âm thầm truncate.

### 41.3. Không bỏ qua fields không có trong canonical view

Một canonical projection cho endpoint đơn hàng không chứng minh bản archive/audit đã được chuyển. Mỗi asset/query cần oracle riêng.

### 41.4. Full comparison có thể tốn tài nguyên

Với hàng tỷ records, thiết kế snapshot-consistent sampling, keyed hashes, partition-based reconciliation và escalation khi mismatch; không buộc tất cả dữ liệu vào Java heap.

---

## 42. Kiểm kê theo schema versions và mapping rules

Một bảng migration mapping:

| Source version | Source field | Target field | Rule | Lossless? |
|---|---|---|---|---|
| v1 | `amount` String | `amountMinor` Number | Parse + scale per currency | Có điều kiện |
| v2 | `totalAmount` Decimal | `amountMinor` Number | Multiply exact | Có điều kiện |
| v3 | `amountMinor` Long | `amountMinor` Number | Exact copy | Thường có |
| v1 | missing `tenantId` | `tenantId` | Resolve from validated legacy owner mapping | Chỉ khi đủ bằng chứng |
| all | `updatedAt` Date | `updatedAt` ISO instant | Normalize to UTC | Nếu precision được giữ |
| all | `deletedAt` optional | `deleted` Bool + timestamp | Preserve deletion semantics | Cần policy |

### 42.1. Làm rõ source/version rules

Nếu `schemaVersion` absent có thể là v1 hoặc bad data, không tự giả định. Ghi cách nhận diện cohort bằng fields/time/source application.

### 42.2. Trường không thể map phải có trạng thái

- `QUARANTINED`.
- `REQUIRES_OWNER_DECISION`.
- `SKIPPED_WITH_APPROVAL`.
- `REBUILT_FROM_AUTHORITY`.
- `LOSSY_MAPPING_APPROVED`.

### 42.3. Ghi version của mapper

Backfill lúc đầu chạy mapper v4; CDC consumer rollout dùng mapper v5 có thể tạo outputs khác. Version mapper/contract phải được pin và ghi trong checkpoint.

---

## 43. Backfill, dual-write và CDC đòi inventory nhiều hơn dữ liệu

Một migration online thường cần sao chép dữ liệu lịch sử **và** bắt kịp thay đổi mới.

~~~mermaid
flowchart TD
    SRC["Source of truth"] --> SNAP["Snapshot/backfill"]
    SRC --> CDC["CDC/transactional outbox"]
    SNAP --> TGT["Target store"]
    CDC --> MAPPER["Idempotent mapper"]
    MAPPER --> TGT
    TGT --> DIFF["Shadow read / reconciliation"]
    DIFF --> GATE["Cutover decision"]
~~~

### 43.1. Backfill watermark

Cần record snapshot position/time theo cơ chế engine hỗ trợ. Chỉ ghi “job bắt đầu lúc 10:00” chưa đủ để xác định events nào cần replay sau snapshot.

### 43.2. Ordering

Nếu CDC update version 7 đến target trước khi backfill version 5, backfill không được overwrite version 7. Dùng version-guarded conditional writes hoặc protocol tương ứng.

### 43.3. Duplicate delivery

CDC có thể redeliver. Mapping/target writes cần idempotency bằng stable event ID/source position và version.

### 43.4. Deletes

Backfill từ snapshot cũ có thể viết lại record đã delete. Delete/tombstone propagation và version ordering phải được kiểm.

### 43.5. Dual-write

Ứng dụng ghi cả source và target có thể thành công một bên, thất bại một bên. Đây là distributed partial failure; cần retry/reconciliation/outbox theo design, không giả định hai writes là transaction toàn cục.

### 43.6. Shadow reads

Read cả source và target để so logic results có thể hữu ích, nhưng cần chú ý source lag, consistency, permission, chi phí và tránh dùng shadow result phục vụ khách trước validation.

---

## 44. Hợp đồng về client version và feature flags

Một trạng thái rollout có thể:

~~~text
v1 applications: 70% traffic
v2 applications: 30% traffic
Migration worker: backfilling
CDC: tailing source writes
Source remains authoritative
Target reads: shadow only
```

### 44.1. Có bao nhiêu writers thực sự?

Nếu app v1 vẫn ghi MongoDB nhưng v2 chuyển thẳng target, hai nguồn có thể diverge. Đếm service versions, CronJobs, regional deployments và mobile SDK cũ.

### 44.2. Feature flags phải có owner

Các cờ:

- `read_source`.
- `shadow_read_target`.
- `dual_write`.
- `read_target`.
- `write_target`.
- `fallback_read_source`.

Cần semantics rõ, trạng thái theo tenant/cohort, khả năng rollback và audit.

### 44.3. Rollback không là flip flag đơn giản

Sau khi target trở thành nguồn ghi chính, source có thể đã lag. Quay lại source mà không reverse synchronization sẽ mất dữ liệu mới.

### 44.4. Điểm không thể quay lại

Ghi `pointOfNoReturn`: lúc source bị decommission, schema cũ bị xóa, target ghi data không backward-compatible hoặc replay history không còn đủ. Phải có phê duyệt trước khi vượt mốc này.

---

## 45. Validation: phân ba lớp

### 45.1. Structural validation

- Count by entity/cohort.
- ID coverage/uniqueness.
- Required fields/types.
- Index definitions.
- Schema version distribution.
- Retention/TTL/deleted markers.
- Shard/key distribution.

### 45.2. Behavioral/contract validation

- Same expected API results.
- Filter/sort/pagination.
- Not found vs conflict vs timeout.
- CAS/conditional writes.
- Read-your-writes/freshness.
- Security/tenant isolation.
- Idempotency after retries.
- Transaction invariants.
- CDC/event payload semantics.

### 45.3. Operational validation

- p95/p99 latency/goodput.
- Throttling/driver attempts.
- Capacity/partition skew.
- Disk/compaction/GSI maintenance.
- Backup/PITR/restore.
- Runbook/restart/failover.
- Monitoring/alerts.
- Cost controls.

### 45.4. Count equality chỉ là một test

Hai datasets bằng count nhưng IDs khác, amounts bị làm tròn hoặc delete flags bị đảo vẫn có thể phá nghiệp vụ.

### 45.5. Acceptance phải có error budget và owner

Ví dụ:

~~~text
Order amounts mismatch: 0 unreviewed
Cross-tenant result: 0
Stale version accepted: 0
Missing business-critical ID: 0
Shadow-read mismatch allowed: only approved eventual-lag window
p99 regression: <= agreed percentage under representative load
```

Các ngưỡng phải do owner phê duyệt, không do script tự đặt.

---

## 46. Đối chiếu số lượng khi có writes đồng thời

Nếu source và target luôn đang ghi, so counts tại “now” có thể lệch do replication/backfill lag chứ chưa chắc data loss.

### 46.1. Dùng consistent watermark

Chọn một snapshot position và source-change checkpoint đã có contract. So source và target **cùng logical cut**, hoặc reconcile after catch-up.

### 46.2. Partition-aware reconciliation

Đối chiếu theo tenant/date/range để tìm khu vực lệch thay vì chỉ một count toàn cluster.

### 46.3. Phân loại mismatch

- Target behind: chưa catch up.
- Mapping bug: type/field sai.
- Duplicate ID.
- Delete not propagated.
- Source record changed during sampling.
- Inconsistent read preference.
- Failed upsert/condition.
- Wrong key/tenant mapping.
- Event gap beyond retention.

### 46.4. Đừng tự sửa mismatch bằng overwrite mù

Nếu target version mới hơn và source snapshot cũ, overwrite có thể làm mất dữ liệu đúng. Cần version/tombstone logic và forensic trace.

---

## 47. Checklist chuyển đổi queries theo nhóm

### 47.1. Point reads

- Key mapping, uniqueness.
- Tenant authorization.
- Missing/not-found.
- Read consistency.
- Payload type/size.
- Response cache/ETag.

### 47.2. List/range

- Filter/index.
- Sort/tie-breaker.
- Pagination token.
- Timezone/collation.
- Maximum result size.
- Query cost and throttling.

### 47.3. Search/aggregation

- Full-text/analyzer.
- Facets/group-by.
- Exact/approx counts.
- Cross-entity joins.
- Materialized projections.
- Lag/rebuild RTO.

### 47.4. Writes

- Create/upsert semantics.
- Conditional/version checks.
- TTL/soft-delete.
- Partial mutation.
- Multi-record atomicity.
- Idempotency/unknown outcome.

### 47.5. System integrations

- CDC resume.
- Outbox.
- Batch export.
- Backup/restore.
- Admin tools.
- Monitoring and audit.

Một nhóm chưa có migration mapping/validation owner phải được ghi là **uncovered**, không tự cho là “không quan trọng”.

---

## 48. Một hồ sơ kiểm kê hoàn chỉnh cho một API

Ví dụ: `PATCH /orders/{id}/shipping-address`.

### 48.1. Business invariant

- Chỉ chủ đơn hoặc nhân viên có quyền được sửa.
- Chỉ sửa trước `SHIPPED`.
- `order.version` tăng đúng một sau successful mutation.
- Không làm mất `paymentInfo` hoặc `items` khi partial update.
- Event `OrderAddressChanged` được phát một cách idempotent.
- Một request timeout không được tạo hai lần event gây external side effects.

### 48.2. Source behavior

~~~text
Lookup by tenantId + orderId
Check status != SHIPPED
Atomic conditional update version
Write outbox in transaction if supported
Return new version and updated shipping address
```

### 48.3. Target requirements

- Key lookup theo tenant.
- Atomic condition cho status/version.
- Partial update giữ các attributes khác.
- Outbox/stream reliability.
- RYW hoặc authoritative subsequent read.
- Same response fields/error mappings.
- Concurrency race handling.

### 48.4. Thử nghiệm bắt buộc

- Sửa đúng version thành công.
- Sửa sai version trả conflict.
- Đơn đã shipped bị từ chối.
- Tenant khác không đọc/sửa.
- Concurrent updates chỉ một operation thỏa precondition.
- Timeout sau commit + retry không nhân effect.
- CDC event redelivery không phát side effect trùng.
- Target failover không làm state lùi trái contract.
- Rollback app version vẫn đọc được schema mới trong window được tuyên bố.

---

## 49. Risk register: ưu tiên những khoảng trống nào?

| Risk | Dấu hiệu | Impact | Ưu tiên |
|---|---|---|---|
| Unknown direct writer | Service account không có owner | Bỏ mất mutations | Critical |
| Missing tenant key | Legacy records không định danh tenant | Cross-tenant exposure | Critical |
| Broken CAS | Target dùng unconditional PUT | Lost update/oversell | Critical |
| Incompatible read consistency | GSI lag vs RYW contract | Stale state | High |
| Snapshot/CDC gap | Backfill và stream không cùng cut | Missing/duplicate data | Critical |
| Index query not supported | Aggregation không có target design | Feature outage | High |
| Wrong null mapping | Missing = 0 | Business calculation sai | High |
| Duplicate IDs | Namespace gộp | Overwrite records | Critical |
| Cold search index | Rebuild quá lâu | RTO violation | High |
| Incompatible pagination token | Long-lived clients giữ token | API errors | Medium/High |
| Unknown stale client | Old app vẫn dùng source | Divergence | High |
| Missing rollback path | Target trở thành authority | Prolonged outage | High |
| Backup not portable | KMS/schema incompatible | Cannot restore | Critical |
| Privacy deletion lost | Tombstone not migrated | Deleted PII exposed | Critical |
| HOT partition | One merchant write heavy | Throttle/p99 regression | High |
| Unsupported large item | One document vượt item cap | Data loss/quarantine | High |

### 49.1. Ưu tiên không chỉ theo xác suất

Rủi ro ít gặp nhưng gây mất dữ liệu, lộ tenant hoặc double charge có thể cần **block cutover**.

### 49.2. Mỗi risk cần owner và exit criterion

Không chấp nhận “sẽ xử lý sau” nếu impact critical mà chưa có mitigation, test và người phê duyệt.

### 49.3. Dùng `UNKNOWN` như trạng thái chính thức

Thiếu bằng chứng không phải `PASS`; điều này quan trọng khi migration lớn hơn khả năng quan sát hiện tại.

---

## 50. Điều kiện kết thúc giai đoạn kiểm kê (inventory exit gates)

Có thể yêu cầu:

1. Các business-critical assets có owner/source of truth.
2. Readers/writers hiện hành được kiểm kê bằng code + telemetry + owner review.
3. Các batch/quarterly/admin accesses đã được xác nhận hoặc đánh dấu blocker.
4. Schema versions/field types được profile theo cohorts.
5. IDs, time/money types, null/missing và TTL semantics có mapping rõ.
6. Query shapes có target access path hoặc design gap được mở.
7. Index/projection dependencies được ghi.
8. Concurrency, CAS, transactions, idempotency và failure semantics được test/design.
9. Read consistency/freshness contract được duyệt.
10. Security/tenant/data residency policy được giữ.
11. CDC/events/consumer checkpoints và replay horizons được kiểm.
12. Dataset size/growth/throughput và backfill duration có estimates.
13. Rollout/coexistence/backward compatibility/rollback được mô tả.
14. Acceptance tests và observation metrics có owner.
15. Unknowns critical không bị bỏ qua; có quyết định điều tra hoặc risk acceptance chính thức.

### 50.1. Exit gate không phải QA code cuối cùng

Nó nói **đã hiểu đủ hiện trạng để thiết kế và đánh giá kế hoạch di chuyển**, không phải target implementation đã đạt mọi test.

### 50.2. Không yêu cầu kiểm kê 100% dữ liệu bằng tay

Tự động hóa sampling/profiling; tập trung vào những invariant và long-tail có rủi ro cao. Nhưng không bỏ những nhóm critical chưa có bằng chứng.

---

## 51. Runbook thực hành: từ phạm vi đến bản kiểm kê được phê duyệt

### Pha A — Scope và ownership

1. Ghi source/target, dạng migration, business workflows trong phạm vi.
2. Liệt kê failure domains, data residency, tenant scope.
3. Chỉ định business owner và engineering owner từng asset.
4. Xác định source authority và những hệ dẫn xuất.
5. Liệt kê dependencies: auth/KMS/backup/CDC/search/payment.

### Pha B — Data profiling

6. Chụp logical/physical size, count và growth.
7. Profile field type/presence, schemaVersion và outliers.
8. Profile IDs, uniqueness, tenant isolation.
9. Kiểm TTL/soft-delete/archival/legal hold.
10. Kiểm các bản ghi lỗi/legacy và remediation owners.

### Pha C — Query/mutation discovery

11. Kiểm API code, repositories, query builders.
12. Xem APM/driver/database query shape metrics.
13. Tìm batch, admin, ETL và external clients.
14. Ghi filters/sorts/projection/pagination/aggregations.
15. Đo QPS, p99, result sizes, scan/index usage.
16. Ghi write CAS/transaction/idempotency/error semantics.

### Pha D — Compatibility mapping

17. Map source queries sang target access paths.
18. Ghi schema conversions và data loss risks.
19. Kiểm event/CDC downstream contracts.
20. Kiểm app version coexistence.
21. Kiểm target limitations, capacity và expected cost.
22. Ghi blocker/test/owner của từng gap.

### Pha E — Review và freeze baseline

23. Review với domain owners/SRE/security/data teams.
24. Xác định contract tests và metrics dùng nghiệm thu.
25. Chụp inventory artifact version + timestamp.
26. Chốt rules cho refresh inventory trước cutover.
27. Phê duyệt tiến hành pilot nếu critical unknowns được giải quyết.

---

## 52. Ma trận 36 tình huống kiểm thử trước cutover

| ID | Tình huống | Điều cần chứng minh |
|---|---|---|
| M01 | Legacy record thiếu `schemaVersion` | Mapping nhận diện và xử lý có kiểm soát |
| M02 | `totalAmount` String/Decimal/Null | Không mất precision/không tự đổi nghĩa |
| M03 | Duplicate `_id` giữa tenants | Không overwrite/cross-tenant |
| M04 | Missing `tenantId` ở legacy data | Không lộ dữ liệu; quarantine/resolve |
| M05 | Null vs absent attribute | API/filter giữ nghĩa |
| M06 | Empty array vs absent children | Response/invariant đúng |
| M07 | Timestamp timezone/DST | Sort/range đúng |
| M08 | Source ObjectId → target key | Uniqueness/canonical mapping |
| M09 | Max document/item size | Oversize được xử lý, không silent drop |
| M10 | Hot tenant 20× peak | Partition distribution và throttle |
| M11 | Compound-index sort query | Target access path + stable order |
| M12 | Pagination token qua cutover | Contract rõ: translate/expire/route |
| M13 | Full-text search query | Analyzer/relevance/filters được review |
| M14 | Monthly aggregation hiếm | Không bỏ query vì telemetry thiếu |
| M15 | Conditional update stale version | Conflict, không lost update |
| M16 | Two concurrent reservations | Không oversell |
| M17 | Partial update nested object | Không mất fields ngoài phạm vi |
| M18 | Multi-record transaction failure | Business invariant/saga hợp lệ |
| M19 | Client timeout after commit | Retry idempotent/unknown outcome |
| M20 | CDC redelivery duplicate | Target state không nhân side effect |
| M21 | Backfill old version after new CDC | Version guard ngăn overwrite |
| M22 | Delete arrives before old insert | Tombstone/version protects delete |
| M23 | CDC source log retention exceeded | Rebootstrap thay vì skip |
| M24 | Dual-write partial failure | Reconciliation và alert |
| M25 | Shadow read under eventual lag | Mismatch được phân loại theo lag |
| M26 | Tenant filter accidentally omitted | Security test chặn cross-tenant |
| M27 | Permissions/roles migrate | Least privilege còn đúng |
| M28 | GDPR delete during backfill | Không resurrect ở target |
| M29 | Old app version reads new schema | Compatibility trong rollback window |
| M30 | New app version writes new-only field | Point-of-no-return được xác định |
| M31 | Source continues writes after cutover | Không tạo divergent authority |
| M32 | Target hot partition during burst | SLO và cost guard |
| M33 | Backup of target missing KMS key | Restore drill phát hiện |
| M34 | Failover/region loss while dual-write | Recovery consistency đạt contract |
| M35 | Batch/admin unknown direct writer | Inventory gate chặn cutover |
| M36 | Counts equal but IDs differ | Reconciliation phát hiện mismatch |

Chỉ tạo failure modes trong staging/isolated environments được phê duyệt hoặc theo production-safe rollout program; không cố ý phá dữ liệu/ngắt cụm production để kiểm thử kiểm kê.

---

## 53. Bài tập 1 — Lập inventory dữ liệu cho ứng dụng bán hàng

Một hệ có:

~~~text
MongoDB:
  orders, customers, products
Redis:
  cart_cache, session_state, idempotency
Kafka:
  order_events, payment_events
Elasticsearch:
  orders_search
Object storage:
  invoices
```

Hãy:

1. Xác định source of truth của mỗi business fact.
2. Phân loại authoritative/derived/ephemeral và unknown.
3. Liệt kê read/write owners.
4. Lập inventory kích thước/growth/retention.
5. Đánh dấu PII/security/tenant constraints.
6. Liệt kê indexes, schema versions, CDC/backup dependencies.
7. Chọn 5 critical unknowns phải xử lý trước migration.

---

## 54. Bài tập 2 — Tạo catalog query từ source code và telemetry

Một API có endpoints:

~~~text
GET  /orders/{id}
GET  /customers/{id}/orders?from=&to=&page=
PATCH /orders/{id}/status
POST /orders/{id}/refund
GET  /reports/monthly
```

Yêu cầu:

1. Liệt kê query/mutation shapes.
2. Ghi input/filter/sort/projection/page/expected errors.
3. Đặt required consistency, transaction và idempotency.
4. Đo QPS/p99/result size theo từng operation.
5. Liệt kê source indexes và target access paths cần có.
6. Phân biệt query hàng ngày với monthly report ít chạy.
7. Thiết kế owner review/evidence fields.
8. Nêu ít nhất một query không có mapping trực tiếp.

---

## 55. Bài tập 3 — Mapping schema drift

Dữ liệu mẫu:

~~~json
{"_id":"1","amount":"100.20","currency":"USD","schemaVersion":1}
{"_id":"2","totalAmount":100.2,"currency":"USD","schemaVersion":2}
{"_id":"3","amountMinor":10020,"currency":"USD","schemaVersion":3}
{"_id":"4","totalAmount":null,"currency":"USD"}
```

1. Tạo mapping sang `amountMinor`.
2. Record nào có thể map losslessly theo rules được phê duyệt?
3. Record nào phải quarantine?
4. Vì sao không dùng binary floating-point để tính tiền?
5. Viết các test cho missing/null/string/overflow.
6. Quy định `schemaVersion` absent ra sao?
7. Ghi audit trail của data remediation.

---

## 56. Bài tập 4 — Chuyển MongoDB list query sang DynamoDB

Source:

~~~javascript
db.orders.find(
  { tenantId: "t", customerId: "c" }
).sort({ createdAt: -1, _id: -1 }).limit(50);
~~~

1. Đề xuất partition/sort key hoặc GSI.
2. Xử lý nhiều orders cùng `createdAt`.
3. Query target có đáp ứng read-your-writes không?
4. Pagination token cũ chuyển đổi thế nào?
5. Một customer rất lớn có hot partition không?
6. Consumed capacity khi filter thêm `status` là gì?
7. Tạo contract tests cho sort, tenant isolation và lag.
8. Nêu khi nào cần materialized view riêng.

---

## 57. Bài tập 5 — Concurrent writes và migration

Một order được cập nhật liên tục:

~~~text
Backfill reads version 7
CDC reads update version 9
CDC writes v9 to target
Backfill later writes v7 to target
```

Hãy:

1. Giải thích lost update xảy ra thế nào nếu upsert vô điều kiện.
2. Thiết kế version-guarded write.
3. Xử lý duplicate CDC delivery.
4. Xử lý delete event v10 rồi insert backfill v7.
5. Khi nào tombstone retention là quan trọng?
6. Nếu version không có ở source, cần xác định ordering source nào?
7. Đặt reconciliation oracle với latest source version.

---

## 58. Bài tập 6 — Phát hiện unknown writers

Telemetry phát hiện account `legacy-reporting` đang ghi source collection 10 lần mỗi tháng, nhưng không có source repository nào ghi như vậy.

1. Tại sao không thể bỏ qua vì write rate nhỏ?
2. Cách dùng database access logs/audit an toàn?
3. Cách tìm owner và schedule?
4. Nếu job chỉ chạy cuối tháng, có cần delay cutover?
5. Cách bảo vệ target khỏi write gap?
6. Policy khi không tìm được owner?
7. Checklist xác nhận đã retire hoặc migrate writer.

---

## 59. Bài tập 7 — So sánh hai adapters Java

Bạn có `OrderRepository` với MongoDB adapter và target NoSQL adapter.

Yêu cầu thiết kế tests:

1. `findByTenantAndId` not-found semantics.
2. Tenant isolation.
3. Conditional version update.
4. Monetary precision.
5. Null/missing handling.
6. Pagination stable sort.
7. Timeout/retry/idempotency.
8. Multi-record invariant.
9. Consistency after write.
10. Failure when target is throttled.
11. Backup/recovery consistency.
12. Metrics kết quả để quyết định go/no-go.

---

## 60. Bài tập 8 — Migration readiness review

Một hệ có 300 triệu records, 12 Java services, 5 batch jobs và 18 CDC consumers. Đã inventory:

~~~text
Collections inventoried:         100%
Query shapes observed:            82%
Schema versions sampled:          v2, v3 only
Direct writers identified:        10/12
Target conditional writes:        untested
CDC deletion handling:           not implemented
Shadow-read mismatch:             0.1%
Rollback plan:                    not documented
```

1. Có đủ điều kiện go-live chưa? Vì sao?
2. Nêu critical blockers.
3. Chọn thứ tự điều tra những khoảng trống.
4. Khi nào 0.1% mismatch có thể được phép?
5. Những missing contract tests nào cần thêm?
6. Viết go/no-go decision có owner.
7. Lập kế hoạch refresh inventory sau khi sửa.
8. Xác định point-of-no-return và rollback window.

---

## 61. Những hiểu lầm thường gặp

| Ngộ nhận | Điều đúng hơn |
|---|---|
| “Copy đủ count là xong.” | Cần ID/content/contract/correctness |
| “Document NoSQL không có schema.” | Schema nằm trong data, code và validation |
| “Mẫu 100 records đủ đại diện.” | Cần cohorts/long-tail/types/outliers |
| “Chỉ API chính mới ghi dữ liệu.” | Batch/admin/CDC/legacy clients có thể ghi trực tiếp |
| “Query chạy ít thì bỏ được.” | Có thể là critical monthly/compliance flow |
| “Index cũ chuyển nguyên tên sang target.” | Query/access pattern quyết định |
| “DynamoDB GSI như MongoDB secondary index.” | Consistency/key model/cost khác |
| “Cassandra dùng WHERE/ORDER BY tùy ý.” | Partition/clustering/access pattern quyết định |
| “Missing và null như nhau.” | Có thể mang nghĩa nghiệp vụ khác |
| “Money dùng double là đủ.” | Cần exact precision/scale |
| “UUID/ObjectId/String tự chuyển lossless mọi thứ.” | Cần representation/uniqueness contract |
| “TTL xóa ngay thời điểm hết hạn.” | Physical cleanup thường bất đồng bộ |
| “Soft delete chỉ là field bình thường.” | Query/privacy/recovery semantics quan trọng |
| “Một collection là một authoritative entity.” | Có thể có nhiều denormalized projections |
| “Có replica nên không cần backup trong migration.” | Logical corruption/cutover cần recovery |
| “Shadow read khác 0 nghĩa luôn bug.” | Có thể do lag/consistency; phải phân loại |
| “Backfill và CDC có thể upsert bất kỳ thứ tự.” | Có thể overwrite version mới bằng cũ |
| “Dual write là atomic transaction.” | Hai stores có partial failure |
| “Event stream là backup vô hạn.” | Retention/order/gaps có giới hạn |
| “Source write đã dừng vì flag mới bật.” | Old writers/jobs vẫn có thể tồn tại |
| “Read-your-writes tự có trên mọi secondary index.” | Phải kiểm engine/consistency |
| “Một query failover pass chứng minh mọi partitions.” | Cần key/replica/zone coverage |
| “Pagination token dùng lại giữa database drivers.” | Thường opaque và không tương thích |
| “Timeout nghĩa ghi không thành công.” | Write outcome có thể unknown |
| “Retry càng nhiều càng an toàn.” | Retry storm và side effects |
| “Một CAS bằng GET rồi SET.” | Không atomic khi concurrent writes |
| “Schema mới đọc được thì app cũ cũng đọc được.” | Rolling rollback compatibility khác |
| “Rollback là đổi feature flag.” | Target writes mới có thể chưa sync về source |
| “Một search index rebuildable nên không cần RTO.” | Rebuild có thể rất lâu |
| “Không thấy query trong APM là không tồn tại.” | Sampling/schedule/low frequency |
| “Bỏ field PII ở target là đủ privacy.” | CDC, backups, indexes và logs cũng liên quan |
| “Benchmark short test là đại diện.” | Hot keys, steady state và maintenance xuất hiện muộn |
| “Managed NoSQL không cần capacity model.” | Quota/partition/GSI/cost vẫn cần |
| “Unknown owner không ảnh hưởng cutover.” | Là một migration blocker cần xử lý |
| “Thêm default cho missing field luôn an toàn.” | Có thể đổi nghĩa dữ liệu |
| “Có test Java tức đã kiểm cluster semantics.” | Cần integration/failover/chaos tests phù hợp |

---

## 62. Checklist kiểm kê trước di chuyển

- [ ] Ghi source/target và lý do migration.
- [ ] Xác định phạm vi, những thành phần out-of-scope nhưng có phụ thuộc.
- [ ] Có sơ đồ luồng dữ liệu và business workflow.
- [ ] Xác định authoritative source cho từng business fact.
- [ ] Phân loại derived/cache/event/audit/recovery dependencies.
- [ ] Có owner cho từng dataset, query và consumer.
- [ ] Inventory đủ table/collection/index/keyspace/topic/bucket cần thiết.
- [ ] Ghi region/DC/tenant/failure domain và data sensitivity.
- [ ] Profile count, logical/physical bytes, growth, size distribution.
- [ ] Profile schema versions và missing/null/type distributions.
- [ ] Xử lý trường tiền/giờ/ID/Unicode/binary bằng contract rõ.
- [ ] Có kế hoạch cho malformed/legacy/oversized records.
- [ ] Kiểm unique keys và duplicate/collision risk.
- [ ] Đo hot keys/partition skew và expected peak throughput.
- [ ] Liệt kê mọi readers và writers kể cả batch/admin/legacy clients.
- [ ] Query catalog có filter/sort/projection/pagination và result contract.
- [ ] Aggregation/search/geospatial/reporting queries được xét riêng.
- [ ] Ghi index definitions/usage, target replacement và build plan.
- [ ] Read freshness/read-your-writes/consistency yêu cầu đã được duyệt.
- [ ] Mutations có CAS/version/transaction/idempotency policy.
- [ ] Not-found/conflict/throttle/timeout và retry contract được ghi.
- [ ] TTL/soft-delete/tombstone/legal hold có lifecycle mapping.
- [ ] Event/CDC stream schemas, ordering, checkpoints và retention được ghi.
- [ ] Tenant security/ACL/PII/deletion policy có tests.
- [ ] Source→target query/mutation matrix không bỏ sót critical operation.
- [ ] Target item size/partition/index/transaction limits đã được đối chiếu.
- [ ] Có target throughput/cost/headroom model.
- [ ] Có dữ liệu và monitoring cho peak/seasonal jobs.
- [ ] App version compatibility/feature flags được kiểm.
- [ ] Backfill snapshot position và CDC catch-up ordering được thiết kế.
- [ ] Shadow reads có comparison oracle/allowed lag.
- [ ] Dual-write partial failure có reconciliation.
- [ ] Acceptance metrics có owner và clear thresholds.
- [ ] Backups/PITR và rollback window đã xác minh.
- [ ] Điểm không thể quay lại được mô tả và phê duyệt.
- [ ] Unknowns và risks critical chưa được đánh dấu PASS giả.
- [ ] Inventory được version hóa, có timestamp/evidence và review owners.
- [ ] Có go/no-go meeting khi chưa đủ bằng chứng.
- [ ] Không copy raw production PII vào catalog hoặc test logs.
- [ ] Không đổi quyền truy cập/consistency/durability ngầm chỉ để dễ migrate.

---

## 63. Tổng kết

**Kiểm kê trước khi di chuyển NoSQL là hoạt động tìm những điều ứng dụng đang dựa vào, không phải chỉ thống kê collections và bản ghi.** Hệ mới có thể chứa chính xác số lượng documents nhưng vẫn thất bại vì index/query shape khác, null/missing bị gộp, các mutation mất atomicity, dữ liệu đến muộn ghi đè bản mới hoặc consumer cũ vẫn ghi vào nguồn cũ.

Những điểm quan trọng nhất:

1. **Bắt đầu từ business workflows và data authority**, rồi mới chốt danh sách collections/tables/indexes.
2. **Schema thực tế phải được đo**, bao gồm legacy versions, kiểu dữ liệu, trường thiếu/null, kích thước và dữ liệu lỗi.
3. **Mọi query và mutation cần hợp đồng rõ** về filter, sort, pagination, SLO, consistency, transaction và errors.
4. **Đừng bỏ quên các clients không đi qua API chính**, như batch, admin, CDC và integrations.
5. **Chọn target access paths từ query catalog**, không sao chép nguyên tên index hoặc query syntax của source.
6. **Bảo vệ invariants của writes** với CAS, conditional updates, idempotency và reconciliation; dual-write không tự atomic.
7. **Backfill và CDC phải phối hợp bằng snapshot position/version ordering**, kể cả với deletes và duplicate delivery.
8. **Phân biệt source-of-truth data và derived projections**; rebuildable phải có đủ source, history và thời gian.
9. **Giữ nguyên hoặc thay đổi có chủ đích application contracts**, đặc biệt tenant isolation, privacy deletion và read freshness.
10. **Go/no-go phải dựa trên evidence và owner-approved exit gates**, không phải một `COPY SUCCESS` hay `COUNT MATCHED` đơn lẻ.

**Câu cần nhớ: “Trước khi chuyển một document, hãy biết ai tạo ra nó, ai đọc nó, ai sửa nó, schema và index nào giúp nó hoạt động, điều gì phải luôn đúng sau mỗi thao tác, và ai có quyền xác nhận rằng hành vi ấy vẫn đúng trên hệ mới.”**
