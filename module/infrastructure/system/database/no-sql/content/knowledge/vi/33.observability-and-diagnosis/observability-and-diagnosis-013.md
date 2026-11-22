# Thu thập thời điểm, cấu hình, truy vấn và dữ liệu để tái hiện lỗi

Một hệ thống Java sử dụng NoSQL nhận báo cáo rằng một số đơn đặt chỗ đã được xác nhận nhưng trang tìm kiếm vẫn hiển thị trạng thái cũ. Người trực vận hành tìm thấy log **“Query succeeded”** và một ảnh chụp màn hình, nhưng không biết yêu cầu xảy ra chính xác lúc nào, replica nào phục vụ truy vấn, consistency level nào được chọn, bản ứng dụng nào xử lý, truy vấn đầy đủ gồm những điều kiện gì, hay dữ liệu nguồn có phiên bản nào. Lỗi không tái hiện được trên máy cá nhân dù mã nguồn dường như giống hệt.

Nguyên nhân có thể rất khác nhau: ứng dụng đọc secondary replica chậm, tìm kiếm dùng một index cập nhật bất đồng bộ, bộ nhớ đệm đang giữ bản cũ, hai request cập nhật đồng thời, dữ liệu có kiểu BSON/JSON khác kỳ vọng, TTL xóa record ngay trước truy vấn, connection timeout sau một write đã commit, hoặc một thay đổi cấu hình chỉ áp dụng ở một nhóm pods. **Không có đủ chứng cứ, kỹ sư dễ sửa sai thành phần hoặc vô tình che lỗi.**

Bài học thuộc **Database No SQL → Quan sát và chẩn đoán**, tập trung vào cách thu thập bằng chứng có cấu trúc để **tái hiện một lỗi một cách kiểm soát được**. Trọng tâm gồm bốn nhóm: **thời điểm**, **cấu hình và môi trường**, **truy vấn/tác vụ**, **dữ liệu và trạng thái**. Chúng phải được gắn với request ID/trace ID, phiên bản thay đổi, điều kiện cạnh tranh và những dấu vết đáng tin cậy từ client đến server.

> **Nguyên tắc:** Một câu báo lỗi “NoSQL chậm”, “đọc sai dữ liệu” hay “đôi lúc timeout” chưa phải một kịch bản tái hiện. Muốn tái hiện, hãy ghi được **làm gì, vào lúc nào, trên phiên bản/cấu hình nào, với input và trạng thái tối thiểu nào, kỳ vọng gì, thực tế gì và chứng cứ nào xác nhận sự khác biệt**. Thu thập phải an toàn: bí mật xác thực, dữ liệu cá nhân, payload thô và thông tin nội bộ chỉ được lưu khi thật sự cần, có phân quyền và thời hạn lưu rõ ràng.

> **Phạm vi:** Các ví dụ sử dụng Java 21 và một số hệ NoSQL phổ biến. Tên collection/table, địa chỉ, IDs, version và timestamps đều là giả lập. API, option truy vấn, read/write consistency và công cụ chẩn đoán phụ thuộc phiên bản engine/driver; cần đối chiếu với cấu hình triển khai thực tế.

## 1. “Tái hiện được lỗi” nghĩa là gì?

Một lỗi được coi là có kịch bản tái hiện khi có thể mô tả:

1. **Preconditions:** dữ liệu, schema/index, môi trường và quyền truy cập trước thử nghiệm.
2. **Actions:** chuỗi request/query/write/timeout/failover xảy ra theo thứ tự hoặc lịch concurrency cụ thể.
3. **Timing:** thời điểm, cửa sổ, độ trễ, event/commit boundaries và quan hệ trước–sau.
4. **Observations:** kết quả trả về, lỗi, trạng thái database/cache/index, metrics và traces.
5. **Expected behavior:** invariant hoặc hợp đồng API đáng lẽ được giữ.
6. **Actual behavior:** chứng cứ cho thấy kết quả khác kỳ vọng.
7. **Repeatability:** số lần thử, tỷ lệ xuất hiện, seed và những điều kiện khiến lỗi tái hiện hoặc biến mất.

Tái hiện không nhất thiết là “100% chạy lại thấy lỗi”. Với race hiếm, một test có thể chứng minh lỗi xuất hiện **trong điều kiện faults hoặc interleaving được kiểm soát**, rồi dùng bất biến để xác nhận.

### 1.1. Tối thiểu để bắt đầu điều tra

Một bản ghi sự cố hữu ích phải trả lời được:

| Câu hỏi | Dữ liệu cần thu thập |
| --- | --- |
| **Khi nào?** | UTC timestamp có độ chính xác rõ, khoảng thời gian, duration, clock source |
| **Ở đâu?** | Service, pod/instance, region, cluster/replica/shard |
| **Phiên bản nào?** | Commit/build, JDK, driver, engine, schema/index/config revision |
| **Lệnh gì?** | API operation, loại query/write, filter/sort/projection/consistency |
| **Với dữ liệu nào?** | Key/tenant scope, kiểu trường, version, payload mẫu đã xử lý an toàn |
| **Kỳ vọng gì?** | Đầu ra/bất biến theo contract |
| **Thực tế gì?** | Error code, response, version, duration, retries |
| **Có concurrency không?** | Interleaving, operation IDs, transaction/session, competing writes |
| **Từ nguồn nào?** | Log/trace/metric, DB audit, CDC event, snapshot, query plan |
| **Có thể chạy lại không?** | Script/harness, seed, dataset và tiêu chí pass/fail |

### 1.2. Tái hiện khác việc chụp lại một biểu hiện

Một screenshot “booking vẫn CONFIRMED” có thể chứng minh **UI đã hiển thị** dữ liệu đó. Nó không cho biết:
- Source đã commit CANCELLED chưa.
- UI lấy qua search index, cache hay database trực tiếp.
- Response được tạo trước hay sau source commit.
- Có read-your-writes contract không.
- Cache key có tenant đúng không.
- Request nào và phiên bản nào phục vụ.

Không nên suy nguyên nhân từ một biểu hiện đơn lẻ.

## 2. Chuỗi chứng cứ từ đầu đến cuối

~~~~mermaid
flowchart LR
    USER["User action / API request"] --> EDGE["Gateway / LB"]
    EDGE --> JAVA["Java service"]
    JAVA --> CACHE[("Cache")]
    JAVA --> DRIVER["NoSQL driver"]
    DRIVER --> DB[("NoSQL source/replica")]
    DB --> CDC["CDC / event"]
    CDC --> INDEX[("Read model / search")]
    INDEX --> JAVA
    JAVA --> RESP["Response"]
    EVIDENCE["Evidence pack"] -.-> EDGE
    EVIDENCE -.-> JAVA
    EVIDENCE -.-> DRIVER
    EVIDENCE -.-> DB
    EVIDENCE -.-> CDC
    EVIDENCE -.-> INDEX
~~~~

Không cần thu mọi byte ở mọi thành phần, nhưng cần một **đường nối nhân quả**:
- RequestId/traceId của user request.
- OperationId nếu có write.
- Dependency span/request ID phía NoSQL.
- Dấu mốc source commit/version.
- Dấu mốc cache/CDC/index visibility khi liên quan.
- Deployment/config revisions có hiệu lực.
- Kết quả thật của từng bước.

### 2.1. Quan sát và kết luận phải được tách

**Quan sát:** “Source document có version 21 lúc 10:03:05 UTC; search document version 19 lúc 10:03:08 UTC.”

**Giả thuyết:** “CDC event version 20–21 chưa được xử lý.”

**Chưa chứng minh:** Vì có thể search query trỏ nhầm index alias, cache giữ bản cũ, source/target được đọc ở boundary khác nhau, hoặc transformer đã bỏ qua version.

Một report tốt đánh dấu:
- FACT / Observed.
- HYPOTHESIS.
- INFERENCE.
- UNKNOWN.
- ACTION TAKEN.
- VERIFIED RESULT.

Không viết một giả thuyết như thể đã được xác nhận.

## 3. Thu thập thời điểm: nhiều loại “time” khác nhau

Một hệ NoSQL phân tán có thể có:
- **Client request arrival time:** gateway nhận yêu cầu.
- **Application handler start:** Java bắt đầu xử lý.
- **Driver send time:** gửi tác vụ tới database.
- **Server receive/execute time:** database nhận/xử lý.
- **Commit/ack time:** write được commit và client nhận ACK, có thể khác nhau.
- **Replica apply time:** secondary bắt kịp.
- **Cache populate/invalidate time:** entry được ghi/xóa.
- **CDC event time và ingest time:** nguồn commit so với consumer nhận.
- **Search index visibility time:** write vào index so với được tìm thấy.
- **User observation time:** UI hiển thị.

Chúng không phải cùng một mốc.

### 3.1. Lưu UTC để ghép sự kiện

Ưu tiên timestamp có offset rõ theo ISO 8601/RFC 3339:

~~~~text
2026-11-14T10:03:05.230Z
2026-11-14T17:03:05.230+07:00
~~~~

Hai timestamps có thể chỉ cùng một instant nếu tính offset đúng.

Không chỉ ghi:

~~~~text
14/11/2026 17:03:05
~~~~

vì thiếu timezone/offset và format có thể mơ hồ.

### 3.2. Monotonic clock để đo duration

Trong cùng JVM, dùng System.nanoTime để đo elapsed time:

~~~~java
long start = System.nanoTime();
// NoSQL operation.
long elapsedNanos = System.nanoTime() - start;
~~~~

Ưu điểm: tránh những bước điều chỉnh đồng hồ hệ thống làm wall-clock nhảy khi tính duration.

**Không so sánh raw System.nanoTime giữa hai JVM, máy chủ hoặc lần restart.** Epoch của monotonic clock không được coi là global.

### 3.3. UTC wall-clock để tương quan giữa services

Mỗi process có thể ghi:
- Instant.now tại thời điểm event.
- Duration đo bằng monotonic clock.
- Trace context/request ID.
- Clock sync status khi cần độ chính xác cao.

Nếu clocks lệch 300 ms, thứ tự trong logs có thể đảo so với nhân quả thực. Trace parent/child, source versions, commit sequence hoặc event IDs giúp xác định thứ tự tốt hơn timestamp đơn lẻ.

### 3.4. Đồng hồ không chứng minh commit order

Hai writes có timestamps:

~~~~text
App A logs write attempt: 10:00:00.100Z
App B logs write attempt: 10:00:00.105Z
~~~~

không đủ chứng minh A commit trước B. Network queueing, retries, NTP skew và replica arbitration có thể làm thứ tự khác.

Muốn xác định thứ tự commit, tìm:
- Database-provided revision/version.
- Transaction/commit sequence khi hệ hỗ trợ.
- Conditional write outcome.
- Cluster logical time/token theo semantics nhà cung cấp.
- Authoritative read sau commit với consistency phù hợp.

### 3.5. Cửa sổ thay vì một instant giả chính xác

Nếu user chỉ nhớ “khoảng 10 giờ”:
- Ghi khoảng 09:55–10:10 theo timezone đã xác minh.
- Tra deployment, slow query, failover, GC và CDC events cùng cửa sổ.
- Thu hẹp bằng requestId/source version.
- Giữ mức độ bất định, không tự điền mili giây không có bằng chứng.

## 4. Timeline tái hiện mẫu

~~~~text
T0 10:03:04.920Z request R-901 nhận POST /booking/B-901/cancel
T1 10:03:05.011Z Java gửi conditional update expectedVersion=20
T2 10:03:05.037Z Source ACK, version mới=21
T3 10:03:05.050Z CDC event v21 được publish
T4 10:03:05.061Z API trả 200, operationId=OP-901
T5 10:03:05.200Z Request R-902 đọc search index -> v19
T6 10:03:05.350Z CDC consumer xử lý v21
T7 10:03:06.000Z Search index refresh làm v21 searchable
~~~~

Nếu API contract của search là eventual với cho phép lệch vài giây, quan sát T5 **có thể phù hợp**. Nếu API hứa read-your-writes ngay sau T3, cần kiểm tra cơ chế đảm bảo ấy.

### 4.1. Ghi time boundary từ nguồn nào?

Mỗi dòng timeline nên chỉ rõ nguồn:
- Gateway access log.
- Application structured log.
- Driver span.
- Database audit/metrics.
- CDC broker record.
- Search index status.
- User screenshot.

Đừng viết các mốc “T2 source committed” chỉ vì client vừa gửi write; cần ACK/transaction evidence hoặc reconcile.

### 4.2. Khi response mất

Timeline có thể:

~~~~text
T1 client gửi WRITE operationId=OP-901
T2 source có thể đã commit
T3 kết nối mất; client TIMEOUT
T4 client retry
~~~~

Không biết T2 đã xảy ra hay chưa chỉ từ T3. Kết quả là **UNKNOWN**, không phải tự động FAILED. Evidence pack cần:
- OperationId/idempotency key.
- Request payload fingerprint.
- Source version/ledger state.
- Retry attempt IDs.
- Read-after-timeout/reconciliation results.

## 5. Bốn nhóm chứng cứ cốt lõi

| Nhóm | Tối thiểu | Khi nào đào sâu |
| --- | --- | --- |
| **Thời điểm** | UTC/offset, duration, time window | Clock skew, overlap, commit order, TTL boundaries |
| **Cấu hình** | App build, driver, engine version, effective config | Pool, consistency, TLS, index, replication, feature flags |
| **Truy vấn** | Operation shape, filter, projection, sort, limit, parameters type | Explain plan, partition, retries, session/transaction |
| **Dữ liệu** | Key, type, version, expected/actual fields, tombstone | Synthetic dataset, snapshot, skew/cardinality, competing writes |

Mỗi nhóm cần **provenance**: ai/đâu/điều kiện nào tạo chứng cứ, có thể tin và tái sử dụng thế nào.

## 6. Cấu hình: file khai báo không đủ

Một ứng dụng có thể đọc application.yml nhưng:
- Environment variable ghi đè.
- Secret manager cấp token khác.
- Remote feature flag đổi behavior.
- ConfigMap chưa reload ở một số pods.
- Driver có default bị thay giữa phiên bản.
- Service discovery trỏ tới region khác.
- Runtime index chưa được tạo thành công.
- Database settings khác với IaC file.

Do đó cần ghi **effective configuration** được runtime thực sự dùng, đã redacted, kèm nguồn/version.

### 6.1. Checklist cấu hình ứng dụng Java

- Service name và build/commit SHA.
- Java runtime vendor/version/flags có ảnh hưởng.
- Dependency versions (MongoDB Java Driver, DataStax/Apache Cassandra, Lettuce, AWS SDK...).
- Spring Boot/framework version.
- Container image digest.
- Pod/instance ID, region, availability zone/cell.
- Feature flag snapshot/revision.
- NoSQL endpoint alias, database/keyspace/table/collection.
- Connection pool sizes/timeouts.
- Retry/backoff policy.
- Read/write concern, consistency, session/transaction settings.
- Codec/serialization settings.
- Cache TTL/invalidation policy.
- Query batching/pagination policy.
- Request deadlines.
- Tenant routing.
- Auth principal alias/role (không ghi secret).
- TLS mode và certificate/trust bundle identifier (không ghi private key).

### 6.2. Checklist cấu hình database

- Engine và version.
- Cluster topology: shards/partitions/replica sets, quorum.
- Region, zone, leader/primary/replica serving read.
- Collection/table schema/validation.
- Index definitions và trạng thái build.
- Secondary-index consistency.
- TTL configuration.
- Compaction/GC/retention policies liên quan.
- Storage and memory pressure.
- Replication lag.
- Access control / role permissions.
- Capacity autoscaling/throttle/quotas.
- Backup/restore/snapshot metadata.
- Deployment/maintenance events.
- Query planner/statistics state nếu engine có.

### 6.3. Đừng chỉ ghi tên version

Nếu lỗi bắt đầu sau bản 2.7.4, cần biết:
- Artifact digest đúng.
- Số pods đã rollout version mới.
- Có pod version cũ cùng phục vụ không.
- Config revision có đổi độc lập build không.
- Feature flag đã bật cho tenant nào.
- Connection pool cũ có còn sống sau secret/cert rotation không.

Lỗi chỉ xảy ra ở **một pod cũ** có thể biến mất khi redeploy mà không phải code fix.

## 7. Bản ghi cấu hình an toàn để tái hiện

Một ví dụ manifest:

~~~~yaml
incidentId: INC-2026-474
capturedAtUtc: "2026-11-14T10:05:00Z"
service:
  name: booking-api
  buildCommit: a1b2c3d4
  javaRuntime: "21"
  imageDigestRef: "sha256:example-redacted"
  region: ap-southeast-1
  cell: booking-cell-2
  instanceAlias: pod-17
  featureFlagRevision: config-v42
database:
  engine: document-nosql
  version: "major.minor.patch"
  endpointAlias: booking-source-primary
  database: booking
  collection: reservations
  consistency: "configured-mode"
  topologyRevision: cluster-revision-18
  indexRevision: index-spec-9
client:
  driverVersion: "record-exact-at-runtime"
  connectionPoolMax: 40
  connectTimeoutMs: 3000
  readTimeoutMs: 2000
  retryMode: "bounded"
  serializerRevision: booking-codec-v5
security:
  principalAlias: booking-writer
  tlsRequired: true
  credentialMaterial: "[NOT_COLLECTED]"
  trustBundleVersion: ca-bundle-v4
evidence:
  requestId: R-901
  traceId: trace-opaque-redacted
  timeWindowStartUtc: "2026-11-14T10:02:00Z"
  timeWindowEndUtc: "2026-11-14T10:06:00Z"
~~~~

Các giá trị chỉ là mẫu. Một file manifest hữu ích nên bao gồm link/ID tới evidence artifacts được quản lý bảo mật, không dán dữ liệu cá nhân vào YAML.

### 7.1. Config drift

So effective config của:
- Pod gặp lỗi.
- Pod không gặp lỗi.
- Trước và sau deploy.
- Production và staging.
- Region A và B.

Một diff có thể bộc lộ:
- Pool max 10 thay vì 50.
- Retry disabled chỉ ở một cell.
- Read preference chuyển sang secondary.
- Cache TTL tăng 10 phút lên một giờ.
- Index mới chưa build ở region B.

### 7.2. Cấu hình có secret thì xử lý thế nào?

Không lưu:
- Password, API token, bearer token.
- Private key.
- Full URI chứa username/password.
- Connection strings có ký tự userinfo.
- Auth header.
- Unredacted environment dump.
- Secret-provider response.

Chỉ ghi:
- Credential reference alias đã được phép lưu.
- Secret version identifier nếu policy cho phép.
- Principal/role alias.
- TLS/certificate expiry metadata cần thiết, không private key.

## 8. Truy vấn: “SELECT booking” không đủ để tái hiện

Một cùng bảng dữ liệu có thể có hàng chục query paths khác nhau:
- Point read theo primary key.
- Query secondary index.
- Range scan.
- Filter có tenantId.
- Sort theo createdAt.
- Pagination bằng cursor.
- Projection lấy một tập fields.
- Read từ replica khác.
- Cache hit/miss.
- Transactional vs non-transactional read.

Một bug pagination có thể chỉ xảy ra khi **sort fields không tạo thứ tự toàn phần** và có concurrent inserts.

### 8.1. Ghi hình dạng truy vấn

Một query descriptor nên có:
- Operation: find/query/update/delete/aggregate/transaction.
- Namespace/table/collection.
- Filter/predicate structure.
- Parameter names và **data types**.
- Index hint hoặc access path.
- Projection fields.
- Sort keys/directions.
- Limit/page size.
- Cursor/page token alias (bảo vệ token nếu nhạy cảm).
- Read/write consistency.
- Transaction/session.
- Collation/timezone.
- Retry attempts.
- Request deadline.
- Row count, result count và error code.

### 8.2. Giá trị tham số: quyền riêng tư vs độ chính xác

Không thể tái hiện nhiều lỗi chỉ từ tên field. Ví dụ:
- amount là integer hay decimal?
- tenantId chứa ký tự Unicode chuẩn hóa khác?
- createdAt là ISO date hay chuỗi?
- array 10 hay 10.000 items?
- partition key có hot skew không?

Nên thu thập **shape và đặc tính**, dùng synthetic values hoặc pseudonymization có kiểm soát. Nếu cần giá trị thật để pháp y, phải có quyền và kênh bảo mật riêng, không ghi vào log mặc định.

### 8.3. Query fingerprint

Một normalized query shape giúp nhóm lỗi:

~~~~text
FIND reservations
WHERE tenantId = <string>
  AND status IN <array-of-string:length-3>
  AND createdAt >= <instant>
SORT createdAt DESC, bookingId ASC
LIMIT 50
READ_PREFERENCE secondary
~~~~

Dùng fingerprint ổn định của shape để correlate slow queries mà không log PII.

### 8.4. Ngay cả query fingerprint giống nhau vẫn có latency khác

Vì:
- Bind value selectivity khác.
- Partition key hot/cold.
- Cardinality/working-set size khác.
- Cache residency khác.
- Index mới cũ.
- Replica lag.
- Disk compaction/background work.

Cần thu thêm **distribution và source state**, không suy một shape đủ cho mọi lỗi.

## 9. MongoDB: thu thập thông tin truy vấn và execution plan

Một truy vấn minh họa:

~~~~javascript
db.reservations.find(
  {
    tenantId: "T-42",
    status: { $in: ["PENDING", "CONFIRMED"] },
    createdAt: { $gte: ISODate("2026-11-01T00:00:00Z") }
  },
  {
    bookingId: 1,
    status: 1,
    createdAt: 1
  }
)
.sort({ createdAt: -1, bookingId: 1 })
.limit(50)
~~~~

Khi có lỗi:
- Xác nhận filter được ứng dụng **thực sự gửi**, không chỉ query code muốn gửi.
- Ghi kiểu BSON của trường và tham số.
- Ghi index definitions/visibility.
- Ghi sort, collation, projection, limit, skip/page token.
- Ghi session, readPreference, readConcern và writeConcern nếu liên quan.
- Ghi server/replica đã phục vụ.
- Ghi plan summary/keys examined/docs examined/returned khi thu được an toàn.

### 9.1. Explain đúng mục tiêu

Execution plan có thể giúp phát hiện:
- Collection scan.
- Index scan không phù hợp.
- Sort trong memory.
- Số keys/docs examined cao.
- Plan switch sau statistics/index change.

Nhưng:
- Explain mode có thể thực thi/tiêu nhiều tài nguyên tùy engine/options.
- Không chạy một truy vấn full scan nặng trên production chỉ để debug mà không có budget.
- Explain có thể làm khác execution path thông thường.
- Plan thay đổi theo phiên bản, index stats và parameter selectivity.

### 9.2. MongoDB command monitoring

Driver có command events giúp theo dõi operation, duration và failure category. Không log nguyên command document bừa bãi: filters, aggregation pipelines và update documents có thể chứa PII hoặc secret-like values.

Nên xuất:
- Command name.
- Database/collection alias.
- Request/operation ID.
- Duration.
- Error category.
- Sanitized query shape.
- Server endpoint alias.

### 9.3. Null, missing và BSON type

Một lỗi chỉ xảy ra với:

~~~~json
{"amountMinor":"1250000"}
~~~~

thay vì:

~~~~json
{"amountMinor":1250000}
~~~~

Một field kiểu string có thể không tham gia filter/sort như numeric. Tương tự:
- null vs absent.
- array vs scalar.
- Date vs string.
- Decimal128 vs double/long.
- ObjectId vs string.
- Collation/Unicode.
- Nested fields.

**Loại dữ liệu là một phần của đầu vào tái hiện.**

## 10. Cassandra/HBase: partition, consistency và tombstones

Với wide-column NoSQL, lỗi có thể phụ thuộc trực tiếp vào data model và distribution:
- Partition key.
- Clustering key.
- Partition width.
- Read/write consistency.
- Replica locations.
- Tombstone count.
- TTL.
- Compaction strategy.
- Paging.
- Repair/replication lag.

### 10.1. Một CQL query

~~~~sql
SELECT booking_id, status, updated_at
FROM booking_by_tenant
WHERE tenant_id = ?
  AND bucket_day = ?
  AND created_at >= ?;
~~~~

Để tái hiện cần:
- Partition key và clustering schema.
- Kiểu và dải giá trị bind parameters.
- Consistency level.
- Page size.
- Partition cardinality.
- Tombstones/expired rows.
- Server/driver versions.
- Pool connections and request timeout.
- Trạng thái replica repair/compaction.

### 10.2. Một môi trường staging nhỏ có thể không tái hiện

Production partition có 2 triệu rows, nhiều tombstones; staging chỉ có 20 rows. Query shape giống nhưng không tái hiện slow read. Dataset thử nghiệm phải giữ **phân phối/kích thước tương đối**, không chỉ field names.

### 10.3. Clock và TTL

Một record có TTL/expiry khác nhau giữa nodes hoặc gần ranh giới có thể:
- Có ở một read.
- Biến mất ở read sau.
- Xuất hiện tombstone khi đọc.

Phải ghi:
- Write timestamp/TTL policy theo semantics engine.
- Thời điểm đọc.
- Replication consistency.
- Clock sync.
- Compaction/repair state.

Không coi TTL “đến giờ xóa chính xác tức thì” nếu storage engine dọn vật lý bất đồng bộ.

### 10.4. HBase

Với HBase cần xem:
- Row key encoding.
- Column family.
- Timestamp/version selection.
- Scan start/stop rows.
- Filter conditions.
- Region assignment.
- Memstore/flush/compaction.
- Tombstone/delete markers.
- RPC timeout và retries.

Một scan có cùng start/stop key nhưng khác maxVersions hoặc filter sẽ cho kết quả khác.

## 11. DynamoDB: key condition, GSI và capacity

Một Query trên bảng khác với Query qua GSI.

Để tái hiện lỗi:
- Region/account/table alias.
- Partition/sort key schema.
- KeyConditionExpression.
- FilterExpression.
- ProjectionExpression.
- ExpressionAttributeNames/Values **theo type**.
- Limit, ExclusiveStartKey và LastEvaluatedKey.
- IndexName, consistency mode.
- ConsumedCapacity nếu được bật trong phạm vi phù hợp.
- Throttling/conditional-check error.
- SDK retries/timeout/credential provider version.

### 11.1. GSI freshness

Dữ liệu ở base table có thể đã commit nhưng GSI chưa phản ánh ngay. Một query qua GSI khác một read base table ở consistency contract. Khi tái hiện:
- Ghi rõ query dùng table hay index.
- Ghi source item version.
- Ghi thời điểm GSI trở nên thấy được nếu đo được.
- Không suy GSI miss là source rollback.

### 11.2. FilterExpression không phải key pruning

Một Query có key condition rộng và filter nhiều rows:
- Có thể đọc nhiều items trước filter.
- Tốn capacity/latency khác hẳn query thu hẹp partition/sort key.
- Chỉ lưu filter mà bỏ key condition dẫn đến chẩn đoán sai.

### 11.3. Pagination

Page token thường chứa thông tin cursor và có thể nhạy cảm; không log toàn bộ theo mặc định. Nếu cần replay, dùng token được lưu ở vault/evidence store có quyền, hoặc tái tạo bằng synthetic data.

### 11.4. Conditional writes

Khi điều tra concurrency:
- Ghi expected version/condition.
- Ghi whether condition succeeded/failed.
- Ghi operationId.
- Ghi SDK attempt counts và timeout outcomes.

Không biến ConditionalCheckFailed thành lỗi network cần retry vô hạn.

## 12. Redis: cache, eviction, TTL và command semantics

Một lỗi “key biến mất” có thể do:
- TTL đã hết.
- Eviction do memory pressure.
- Explicit DEL/UNLINK.
- Key bị ghi đè.
- Redis failover.
- Prefix/DB index khác.
- Cache invalidation event.
- Wrong serialization.
- ACL permission.

Cần ghi:
- Key class/prefix/tenant scope đã bảo vệ.
- Command shape (GET/SET/EXPIRE/HGETALL/Lua...).
- TTL/expiration mode.
- Eviction policy và memory pressure.
- Replica/cluster routing.
- Connection/read timeout.
- Serializer/compression format/version.
- Cache fill/invalidation generation.
- Cache hit/miss và source version.

### 12.1. Không chụp cả Redis production để “debug”

Một dump có thể chứa tokens, PII, session data, secrets. Chỉ export phạm vi tối thiểu đã phê duyệt, encrypt và gắn retention. Trong đa số bài tái hiện, có thể dùng synthetic records với TTL/type tương đương.

### 12.2. Cache stampede

Một hot key vừa hết TTL, 10.000 requests cùng miss:
- Đo key TTL/counter, miss spike, origin requests.
- Ghi singleflight/distributed refill configuration.
- Đo source p99 và pool waits.
- Kiểm tra versioned fill tránh stale overwrite.

Nếu staging không có hot traffic, lỗi không xuất hiện dù dữ liệu giống nhau.

### 12.3. Distributed lock/lease

Khi điều tra lease:
- Ghi token *alias/fingerprint* không làm lộ secret.
- Lease acquisition/release timestamps.
- TTL và clock assumptions.
- Holder pause/restart.
- Fencing/source version behavior.
- Redis failover events.

Đừng chỉ đưa log “lock acquired” rồi suy serializability cho booking.

## 13. OpenSearch/Elasticsearch và read models

Khi dữ liệu nguồn đúng nhưng search trả sai:
- Xác định index/alias thực tế.
- Mapping revision.
- Analyzer/normalizer.
- Query DSL shape, sort, page search_after/cursor.
- Indexing response per item.
- Refresh/visibility.
- CDC/ingestion lag.
- Source version embedded trong indexed document.
- Reindex/cutover events.
- Shard health/routing.

### 13.1. Indexed không đồng nghĩa searchable ngay

Một write vào index có thể thành công nhưng query chưa nhìn thấy cho đến refresh/visibility boundary. Cần ghi đúng thời điểm:
- Target accepted update.
- Search result bắt đầu thấy document.
- Query đã vào alias/index nào.

### 13.2. Alias và version

Một deploy chuyển alias search-v7 → search-v8. Một pod tiếp tục query index v7 có thể thấy kết quả khác. Bản ghi môi trường phải có **alias resolution tại thời điểm lỗi**, không chỉ tên alias.

### 13.3. Full content có thể chứa PII

Query text, analyzers và document source có thể chứa từ khóa nhạy cảm. Thu query shape/field names; chỉ lấy payload thật trong evidence store có quyền, hoặc tạo từ khóa synthetic tương tự.

## 14. Dữ liệu: tái hiện bằng đặc tính chứ không sao chép tùy tiện

Một bộ dữ liệu mẫu nên bảo tồn những tính chất gây lỗi:

- **Kiểu dữ liệu:** integer, string, decimal, date, binary, null/missing.
- **Giá trị biên:** empty, maximum, negative, Unicode, timestamp edge.
- **Phân phối:** hot key, skew, cardinality, item size.
- **Quan hệ:** cùng tenant, same partition, foreign/business references.
- **Thứ tự:** version, update sequence, deletion, re-creation.
- **TTL:** tuổi record và thời điểm hết hạn.
- **Index:** field selectivity và query plan.
- **Tải:** số concurrent readers/writers, request rate.
- **Topology:** replica lag, shard placement.
- **Schema evolution:** records được viết bằng serializer v2/v3.
- **Permissions:** user/tenant scope.

### 14.1. Một record dễ, một record gây lỗi

Dataset “đẹp”:

~~~~json
{
  "bookingId": "B-1",
  "tenantId": "T-1",
  "amountMinor": 120000,
  "createdAt": "2026-11-14T10:00:00Z"
}
~~~~

Record thực tế có thể có:

~~~~json
{
  "bookingId": "B-000001",
  "tenantId": "T-1",
  "amountMinor": "120000",
  "createdAt": null,
  "metadata": {"specialNote": ""},
  "schemaVersion": 1
}
~~~~

Nếu code giả định amountMinor là long và createdAt không null, chỉ dataset thứ hai tái hiện lỗi. Không biến dữ liệu mẫu thành kiểu mới trước khi ghi nhận **vì chính kiểu cũ có thể là trigger**.

### 14.2. Null và missing

Trong document databases, field không tồn tại khác field tồn tại với null ở một số query/serialization semantics. Một repro dataset nên chứa cả:
- Field absent.
- Field present null.
- Field present empty string.
- Field present empty array/object.
- Field present wrong type.

### 14.3. Decimal và tiền

Không chuyển Decimal128 hoặc integer cents sang double tùy tiện nếu đang điều tra rounding/precision. Cần lưu type và scale. Đôi khi một test chỉ tái hiện khi amount gần giới hạn integer hoặc vừa qua boundary làm tròn.

### 14.4. Timestamp biên

Các trường hợp:
- Ngày cuối tháng.
- Leap day.
- UTC midnight.
- Offset +07:00 vs Z.
- DST khi dùng timezone có DST.
- TTL expire near second boundary.
- Unix milliseconds vs seconds.
- Clock skew giữa nodes.

## 15. Một bộ dữ liệu tái hiện tối thiểu

Giả sử lỗi là “sau một update, cache đã invalidate nhưng một reader cũ ghi cache v7 đè v8”.

Không cần sao chép cả production. Cần ba thành phần:

~~~~json
{
  "sourceDocument": {
    "tenantId": "T-test",
    "bookingId": "B-repro",
    "version": 7,
    "status": "PENDING"
  },
  "cacheDocument": null,
  "invalidationGeneration": 7
}
~~~~

Và hai request có thứ tự kiểm soát:

~~~~text
A: read source v7 but pause before cache SET
B: update source to v8, invalidate cache/advance generation
A: resume and attempt cache SET v7
ASSERT: cache must not expose v7 as fresh
~~~~

### 15.1. Vì sao là minimal?

Chỉ cần:
- Một entity.
- Một cache key.
- Hai actors.
- Hai versions.
- Một điểm tạm dừng xác định.
- Một invariant.

Không cần 100.000 bookings. Sau khi chứng minh race, có thể mở rộng stress test để đo xác suất.

### 15.2. Reproduction seed

Với dữ liệu ngẫu nhiên:
- Lưu random seed.
- Số entities.
- Key distribution policy.
- Schema mix.
- Time offsets.
- Concurrent operation schedule.

Không dùng Math.random không lưu seed rồi kỳ vọng tái hiện chính xác.

### 15.3. MRE vs production-scale repro

Có hai cấp:

1. **Minimal Reproducible Example (MRE):** tìm bug logic, race hoặc type boundary.
2. **Scale/Topology Reproduction:** cần data volume, shard skew, compaction, pool pressure, replica lag.

Một lỗi p99 chỉ xuất hiện khi partition có 2 triệu rows không thể tái hiện chỉ bằng 2 records; MRE phải giữ yếu tố kích hoạt.

## 16. Thu dữ liệu an toàn: masking, tokenization và synthetic data

### 16.1. Thu thập tối thiểu

Không thu:
- Password/API key.
- Private key/client cert private material.
- Full bearer token.
- Họ tên/địa chỉ/số điện thoại/email thật nếu không cần.
- Payment card information.
- Raw multi-tenant dataset vô cớ.
- Tất cả HTTP headers.
- Full connection URI có userinfo.

Thu:
- Pseudonymous entity ID.
- Data type/shape.
- Aggregate version.
- Field cardinality/range.
- Sanitized query shape.
- Timing/topology metadata.
- Thông tin phân loại lỗi.

### 16.2. Hash không tự là ẩn danh

Hash của email, số điện thoại, userId liên tục hoặc giá trị ít entropy có thể bị đoán/ngược qua dictionary. Khi cần đối chiếu nhiều events theo cùng một subject, cân nhắc tokenization/HMAC trong miền bảo vệ phù hợp và chính sách quản lý key/retention; không in raw ID song song.

### 16.3. Synthetic data bảo toàn invariant

Khi thay tenant T-42 bằng T-test:
- Các records liên quan phải cùng tenant tương ứng.
- Referential integrity không đổi.
- Hot partition skew được giữ khi performance là trigger.
- UTC/offets/type/length patterns được giữ khi parser là trigger.
- TTL/version lifecycle được giữ.

Không tạo một dataset sạch và đồng nhất nếu lỗi do dữ liệu legacy không đồng nhất.

### 16.4. Tách bằng chứng nhạy cảm và kịch bản tái hiện

Một incident có thể có:
- **Secure evidence store:** raw evidence tối thiểu đã phê duyệt, encrypted, audit access, expiry.
- **Repro fixtures repository:** synthetic/sanitized data không chứa secrets/PII.
- **Incident report:** IDs/fingerprints/timing/summary, không raw sensitive payload.

Đừng commit production dumps vào repository thử nghiệm.

### 16.5. Quyền và retention

Xác định:
- Ai được xem evidence.
- Mục đích.
- Retention deadline.
- Quy trình xóa.
- Đường chia sẻ với vendor/support.
- Nghĩa vụ pháp lý/bảo mật nội bộ.

Chỉ gửi đủ phần cần thiết; tránh upload không kiểm soát.

## 17. Bất biến nghiệp vụ giúp xác định lỗi

Một query trả dữ liệu “khác mong đợi” chỉ là lỗi nếu có một expectation rõ.

Ví dụ:
- Booking slot chỉ có tối đa một CONFIRMED reservation.
- Một operationId chỉ tạo tối đa một logical payment/order.
- API read-your-writes phải nhìn version tối thiểu vừa commit.
- Dữ liệu tenant A không được trả cho B.
- Cache entry không được ghi xuống version nhỏ hơn watermark đã biết.
- CDC projection phải bắt kịp trong freshness bound đã công bố.
- Delete/privacy revoke phải phản ánh trong thời hạn đã định.

### 17.1. Công bố consistency contract

Các câu hỏi:
- Read có thể stale không?
- Tối đa stale bao lâu?
- Có session token/minVersion không?
- Query qua GSI/search/index eventual hay authoritative primary?
- Write ACK nghĩa gì (accepted, durable, quorum)?
- Có transaction scope nào?
- Timeout sau commit có được coi UNKNOWN không?

Không thể tái hiện một “lỗi stale read” đúng nghĩa khi chưa xác định hệ hứa consistency gì.

### 17.2. Dữ liệu chỉ là một trạng thái của timeline

Một snapshot B-901 v7 không đủ để hiểu vì sao API trả v7 sau khi source v8:
- Snapshot chụp trước hay sau commit?
- Replica nào phục vụ?
- Session nào đọc?
- Invalidation đã đến chưa?

Phải gắn snapshot với boundary và provenance.

## 18. Tái hiện lỗi đồng thời: điều khiển interleaving

Nhiều bugs mất đi khi thêm logging vì timing thay đổi. Với race, dùng test hooks/barriers có kiểm soát trong môi trường thử nghiệm.

~~~~mermaid
sequenceDiagram
    participant A as Reader A
    participant B as Writer B
    participant D as NoSQL source
    participant K as Cache
    A->>D: Read v7
    D-->>A: v7
    Note over A: Pause before cache fill
    B->>D: Conditional update v7 -> v8
    D-->>B: Commit v8
    B->>K: Invalidate / watermark v8
    Note over A: Resume
    A->>K: Attempt cache fill v7
    Note over K: Reject if watermark >= v8
~~~~

### 18.1. Latch/barrier là chứng cứ tốt hơn sleep ngẫu nhiên

Thay vì:

~~~~java
Thread.sleep(100);
~~~~

và hy vọng race xuất hiện, dùng:
- CountDownLatch.
- CyclicBarrier.
- Phaser.
- Test-specific hooks.
- Fault injection tại điểm I/O cụ thể.

Nhưng đừng đưa cơ chế pause không được kiểm soát vào production.

### 18.2. Java 21: ví dụ barrier cho hai actors

~~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class RaceHarness {
    private final CountDownLatch readerLoaded =
            new CountDownLatch(1);
    private final CountDownLatch writerCommitted =
            new CountDownLatch(1);

    public void reader() throws Exception {
        // Simulate source read of v7.
        long observedVersion = 7L;
        readerLoaded.countDown();

        if (!writerCommitted.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("writer did not commit");
        }

        // Reproduction assertion: a version-aware cache fill
        // must reject observedVersion=7 after watermark=8.
        boolean accepted = fakeCacheCompareAndSet(observedVersion);
        if (accepted) {
            throw new AssertionError("stale fill was accepted");
        }
    }

    public void writer() throws Exception {
        if (!readerLoaded.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("reader did not load");
        }

        // Simulate an authoritative source commit to v8,
        // followed by publication of a version watermark.
        writerCommitted.countDown();
    }

    private boolean fakeCacheCompareAndSet(long version) {
        long watermark = 8L;
        return version >= watermark;
    }
}
~~~~

Đây là **mô hình sự kiện giả lập** để giải thích interleaving, không phải test tích hợp đã kết nối NoSQL/Redis. Trong test thật:
- Thay fakeCacheCompareAndSet bằng atomic update tại cache.
- Source write phải có conditional version guard.
- Ghi trace IDs và versions.
- Dọn trạng thái thử nghiệm.
- Không coi một test giả lập là bằng chứng engine thực tế đã đúng.

### 18.3. Tránh observer effect

Logging đồng bộ trong vùng tranh chấp có thể:
- Thêm lock.
- Làm đổi CPU scheduling.
- Che race.
- Giảm QPS, khiến lỗi biến mất.

Đặt instrumentation nhẹ, dùng trace sampling có kiểm soát, và khi cần tách test deterministic khỏi load-stress test.

## 19. Java: ghi thời gian và dữ liệu chẩn đoán có cấu trúc

Một bộ đo tối thiểu nên:
- Ghi Instant start/end cho tương quan.
- Đo duration bằng monotonic clock.
- Gắn request/trace/operation IDs.
- Log operation shape chứ không raw payload.
- Phân loại outcome.
- Tách retry attempt.
- Không ghi secret.

Ví dụ thuần Java 21:

~~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.TimeUnit;

public final class ObservedNoSqlCall {

    public enum Outcome {
        SUCCESS,
        TIMEOUT,
        CONDITIONAL_CONFLICT,
        PERMISSION_DENIED,
        RETRYABLE_FAILURE,
        UNKNOWN_WRITE_RESULT,
        OTHER_FAILURE
    }

    public record QueryShape(
            String operation,
            String namespaceAlias,
            String filterFingerprint,
            String consistencyMode
    ) {}

    public record CallEvidence(
            String requestId,
            String operationId,
            int attemptNumber,
            Instant startedUtc,
            Instant finishedUtc,
            long durationMicros,
            QueryShape queryShape,
            Outcome outcome,
            String sanitizedErrorCategory
    ) {}

    @FunctionalInterface
    public interface EvidenceSink {
        void record(CallEvidence evidence);
    }

    public static <T> T observe(
            String requestId,
            String operationId,
            int attemptNumber,
            QueryShape queryShape,
            Callable<T> operation,
            EvidenceSink sink
    ) throws Exception {
        Objects.requireNonNull(queryShape);
        Objects.requireNonNull(operation);
        Objects.requireNonNull(sink);

        Instant startedUtc = Instant.now();
        long startNanos = System.nanoTime();
        Outcome outcome = Outcome.SUCCESS;
        String category = null;

        try {
            return operation.call();
        } catch (Exception error) {
            // Application classifier must use driver-specific
            // exception types, labels and operation semantics.
            outcome = classifySafely(error);
            category = error.getClass().getSimpleName();
            throw error;
        } finally {
            Instant finishedUtc = Instant.now();
            long elapsedMicros = TimeUnit.NANOSECONDS.toMicros(
                    Math.max(0, System.nanoTime() - startNanos)
            );

            CallEvidence e = new CallEvidence(
                    requestId,
                    operationId,
                    attemptNumber,
                    startedUtc,
                    finishedUtc,
                    elapsedMicros,
                    queryShape,
                    outcome,
                    category
            );

            // Sink should be bounded, asynchronous and
            // non-throwing from the request's perspective.
            try {
                sink.record(e);
            } catch (RuntimeException ignored) {
                // Count metric-export failures via independent
                // channel; never replace original DB outcome.
            }
        }
    }

    private static Outcome classifySafely(Exception error) {
        // Placeholder: determine real categories via
        // driver-specific, operation-specific contracts.
        return Outcome.OTHER_FAILURE;
    }
}
~~~~

### 19.1. Những gì đoạn mã có thể làm

- Giữ các request/operation IDs.
- Đo elapsed trong cùng JVM bằng nanoTime.
- Lưu UTC anchors.
- Không tự serialize query parameters hoặc exception message.
- Tách outcome và class lỗi.
- Không để sink lỗi ghi đè kết quả NoSQL ban đầu.

### 19.2. Giới hạn cần bổ sung trong production

- Asynchronous CompletionStage/Future callbacks thay cho Callable nếu driver async.
- Driver-specific error categories.
- Tracing propagation và correlation ID source-side.
- Deadline/timeout/retry budget.
- Client pool wait riêng.
- Database server timings khi có.
- Structured bounded log queue.
- Sampling và retention.
- Data privacy policy.
- Sink failure metric có cơ chế không gây recursion.
- Kiểm tra class name/error code có thực sự không nhạy cảm.

**Không log error.getMessage() hoặc command payload một cách mặc định.** Exception messages đôi lúc chứa endpoint, command, parameter hoặc user data.

### 19.3. Async API: đo tới callback completion

Với CompletionStage:
- Capture startNanos trước khi submit.
- Khi completion callback chạy, tính duration.
- Ghi exception category.
- Phân biệt synchronous submission failure với async failure.
- Nếu callback scheduler bị GC pause, client-visible latency tăng; dùng server metrics để tách nguyên nhân.

## 20. Trace context: nối sự kiện thay vì chỉ nhìn log rời

Một request có thể đi qua:
- Gateway.
- Java API.
- MongoDB driver.
- Redis cache.
- Kafka publisher.
- Search consumer.

Trace context giúp nối spans. Một span có thể có:

~~~~json
{
  "traceId": "opaque-trace-id",
  "spanId": "opaque-span-id",
  "parentSpanId": "opaque-parent-id",
  "service": "booking-api",
  "operation": "nosql.find",
  "db.system": "document-db",
  "db.namespace.alias": "booking.reservations",
  "db.query.shape": "shape-fingerprint-12",
  "db.consistency": "secondary-read",
  "durationMs": 43.5,
  "outcome": "SUCCESS",
  "requestId": "R-901",
  "operationId": "OP-901"
}
~~~~

Các field names ngoài chuẩn có thể là custom attributes, phải xác minh theo semantic conventions của OpenTelemetry/SDK đang dùng. Không sao chép snippet này như chuẩn telemetry chính thức.

### 20.1. Không ghi raw DB statement khi chứa PII

Một số instrumentation có thể thu full database statements. Trước khi bật:
- Kiểm tra có values được bind inline không.
- Có secrets trong URI/headers không.
- Có UPDATE documents chứa PII không.
- Sampling/retention/export destination.

Có thể lưu normalized fingerprint và tham số kiểu/range, không phải raw values.

### 20.2. Trace sampling có thể bỏ đúng lỗi hiếm

Nếu sampling 1%, một lỗi 1/100.000 requests có thể không có trace. Kết hợp:
- Errors/slow requests adaptive sampling theo policy.
- RequestId lookup.
- Structured event logs với low-cardinality metadata.
- Metrics counters không sampling mất.
- On-demand diagnostic mode có expiry.

### 20.3. Không dựa vào trace để quyết định commit đã xảy ra

Một span “db.write timeout” không chứng minh source rollback. Phải có authoritative operation state/version/idempotency ledger.

## 21. Query plan và thống kê truy vấn

Khi lỗi là p99 tăng, chỉ có raw latency chưa đủ. Cần đánh giá:
- Số rows/items examined.
- Số keys scanned.
- Index selected.
- In-memory sort hoặc spill.
- Partition/shard fanout.
- Read repair/replica wait.
- Queuing time.
- Locks/contention.
- Background compaction/GC.
- Throttling/capacity.
- Payload/network bytes.

### 21.1. Đừng chỉ lưu explain output sau sự cố

Query plan có thể thay đổi:
- Index vừa tạo.
- Statistics refresh.
- Engine upgrade.
- Data distribution đổi.
- Cache warmed.

Nếu không có plan tại thời điểm lỗi, phải ghi rõ plan sau incident **chỉ là bằng chứng tham khảo**.

### 21.2. Query explain và quyền vận hành

Một số explain/trace modes có overhead đáng kể, có thể chạy query hoặc quét nhiều dữ liệu. Chỉ chạy:
- Với budget.
- Trên môi trường hợp lệ.
- Theo runbook.
- Với result redaction.
- Không làm production p99 xấu hơn incident.

### 21.3. Plan fingerprint

Nếu một index hint/plan change chỉ xảy ra cho partition lớn:
- So plan ở query cùng shape nhưng bind values khác.
- So selectivity/hotness.
- So query stats theo tenant/partition.
- Đừng suy một truy vấn chạy nhanh trên key nhỏ sẽ chạy nhanh trên hot key.

## 22. Lỗi thoáng qua và lỗi chỉ xuất hiện khi tải cao

Một “intermittent bug” có thể do:
- GC pause.
- Compaction.
- Memory pressure.
- CPU throttling.
- Leader election.
- Replica lag.
- Network packet loss.
- Connection churn.
- Cache stampede.
- Expiration batch.
- Noisy neighbor.
- Throttling.
- Query mix.
- Data skew.

### 22.1. Thu cả system state

Ghi trong cùng time window:
- Application CPU, heap, GC.
- Thread pool queues.
- NoSQL client pool active/waiting.
- DB CPU/IO/disk/network.
- Connections.
- Partition hotspots.
- Replica/consistency lag.
- Compaction/flush.
- Cache miss/eviction.
- CDC lag.
- Error/retry rates.
- Deployment/failover events.

### 22.2. Không chỉ đo p99 thành công

Khi load generator/client chậm:
- RPS thực có thể giảm.
- Timeout requests không được tính.
- p99 chỉ của successes có thể đẹp giả.

Ghi planned/sent/completed/rejected/timeout và operation mix nếu đang tái hiện performance issue bằng load test.

### 22.3. Cửa sổ mẫu hẹp

Một dashboard aggregation 5 phút có thể che spike 300 ms. Cần raw/short-window metrics đủ retention để xác định burst và correlation.

### 22.4. Thread dumps/heap dumps

Có thể hữu ích nhưng chứa:
- Memory buffers.
- Password/token fragments.
- PII.
- Internal topology.
- Business objects.

Chỉ thu khi có phê duyệt, encrypt, hạn chế quyền và retention; tránh đính kèm tự do.

## 23. Lỗi TTL và vòng đời dữ liệu

Một record biến mất lúc 10:00 có thể liên quan:
- TTL được gán khi write.
- Expiry evaluation tại read.
- Logical tombstone.
- Background compaction/garbage collection.
- Replica repair.
- Snapshot pinning.
- Cache expiry khác source TTL.

### 23.1. Thu đủ thời điểm

Ví dụ:

~~~~yaml
entityAlias: booking-test-1
createdAtUtc: "2026-11-14T09:40:00Z"
ttlSeconds: 1200
expectedLogicalExpiryUtc: "2026-11-14T10:00:00Z"
observedRead1Utc: "2026-11-14T09:59:59.800Z"
observedRead2Utc: "2026-11-14T10:00:00.250Z"
readConsistency: "record-real-value"
replicaAlias: "replica-2"
~~~~

**Không kết luận đã bị xóa vật lý** chỉ vì read sau expiry trả NOT_FOUND. Logical expiration và background reclaim khác nhau.

### 23.2. Clock skew

Nếu server clock lệch, TTL boundary có thể khác kỳ vọng. Cần xem clock sync, server time semantics và timestamp origin.

### 23.3. Tombstones và snapshot

Một backup/restore có thể đưa bản cũ trở lại hoặc giữ data đã bị xóa tùy policy. Tái hiện deletion bug cần:
- Source version/deletion marker.
- Snapshot boundary.
- Restore time.
- Invalidation/replay event.
- Target projection state.

## 24. CDC và projection lag trong bộ chứng cứ

Một event-driven read model cần dấu mốc:
1. Source commit.
2. CDC event emitted.
3. Connector published.
4. Broker stored.
5. Consumer processed.
6. Target write durable.
7. Query visibility.

### 24.1. Đừng gọi mọi mismatch là lost event

Nếu source version=30, target version=28:
- Consumer có thể chỉ lag.
- Event v29–30 có thể vẫn trong broker.
- Search refresh có thể chưa chạy.
- Target update có thể fail mapping.
- Consumer có thể đã skip v29.
- Reconciliation reads có thể ở hai boundary khác nhau.

Thu:
- Source version.
- Consumer checkpoint/lag.
- Event IDs.
- DLQ.
- Index version/alias.
- UTC timeline.

### 24.2. CDC cursor và opaque token

Không log/replay token tùy tiện trong hệ khác. Token có thể nhạy cảm hoặc phụ thuộc provider/source identity. Evidence store có quyền và alias giúp tái hiện mà không đưa token vào logs công khai.

### 24.3. Source snapshot không luôn khôi phục lịch sử

Nếu thiếu event transition trong cửa sổ, current source record có thể đủ để repair current-state search nhưng không đủ reconstruct audit, billing hay notifications. Incident report phải ghi limitation.

## 25. Retry, idempotency và UNKNOWN outcome

Một timeout có thể là:
- Request chưa tới DB.
- DB chưa commit.
- DB đã commit nhưng ACK mất.
- DB đang retry/partially applied theo engine contract.

Muốn tái hiện phải thu:
- Logical operation ID.
- Attempt IDs.
- Query shape/payload fingerprint.
- Conditional version.
- Transaction/session IDs nếu có.
- Driver retry labels/error category.
- Last known source state.
- Result reconciliation.

### 25.1. Không retry write không idempotent chỉ vì socket timeout

Nếu một increment +1 được gửi hai lần sau timeout, có thể cộng hai lần. Cần:
- Operation ledger.
- Idempotency key.
- Conditional update.
- Transaction/memoization theo semantics.
- State verification.

### 25.2. Timeline UNKNOWN

~~~~text
OP-901 attempt-1 -> source
TCP connection breaks
client sees timeout
OP-901 attempt-2 with same operationId
source ledger says already committed
API returns canonical result
~~~~

Không ghi “attempt-1 failed to commit” khi chưa xác minh.

### 25.3. Error code có thể phân loại không đủ

Một generic timeout cần thêm:
- Phase: pool acquire/connect/TLS/send/read/commit ACK.
- Request timeout/deadline.
- Attempts.
- Server-side trace.
- Operation type.
- Authoritative result.

## 26. Mẫu evidence packet cho một lỗi

~~~~yaml
incident:
  id: INC-2026-474
  summary: "Search stale after booking update"
  status: INVESTIGATING
  expected: "Read-your-writes for booking detail endpoint"
  observed: "Response returned version 19 after source ACK v21"
  timeWindow:
    fromUtc: "2026-11-14T10:02:00Z"
    toUtc: "2026-11-14T10:06:00Z"
  uncertainty:
    clockSkewEstimateMs: 15
    exactSourceCommitTimestampKnown: false

environment:
  service: booking-api
  build: commit-a1b2c3
  java: "21"
  driver: "record-runtime-version"
  region: ap-southeast-1
  podAlias: pod-17
  configRevision: config-v42
  databaseEngine: document-db
  clusterAlias: booking-prod
  readPreference: secondaryPreferred
  indexRevision: index-v9

request:
  requestId: R-902
  traceId: opaque-trace-alias
  logicalOperationId: OP-901
  operation: GET_BOOKING_DETAIL
  tenantScope: "pseudonymous-T-42"
  queryFingerprint: shape-booking-detail-v3
  parameterTypes:
    tenantId: string
    bookingId: string
  retryAttempts: 1
  deadlineMs: 1000

state:
  sourceVersionAtVerifiedRead: 21
  projectionVersionAtObservedRead: 19
  cacheVersion: unknown
  sourceReadBoundary: "documented-verification-time"
  projectionReadBoundary: "observed-request-time"

evidenceRefs:
  - "secure://incident/INC-2026-474/trace"
  - "secure://incident/INC-2026-474/config-redacted"
  - "secure://incident/INC-2026-474/versioned-state"

reproduction:
  fixtureId: repro-booking-v3
  runSeed: 445474
  status: NOT_YET_REPRODUCED
  successCondition: "No stale result under stated contract"
  failureCondition: "Returned version < required session version"
~~~~

Đây là schema mô tả để học, không phải cấu hình kết nối hoặc dữ liệu production. Thuộc tính “expected” phải dựa trên hợp đồng thật: nếu endpoint chỉ có eventual consistency thì cần điều chỉnh kỳ vọng.

### 26.1. EvidenceRefs phải có quyền

Một chuỗi secure:// trong ví dụ chỉ minh họa logical reference. Hệ thực có thể dùng evidence store/incident system với:
- Access control.
- Audit logging.
- Encryption.
- Retention.
- Download review.

Không in signed URLs sống lâu trong bug ticket rộng quyền.

## 27. Provenance và integrity của bằng chứng

Một artifact hữu ích nên có:
- Collection method/version.
- Collector identity/service account.
- UTC capture timestamp.
- Source endpoint/namespace alias.
- File size/type.
- Content digest.
- Redaction applied.
- Sensitivity classification.
- Chain of custody/owner.
- Retention expiry.
- Correlation to incident/runId.

### 27.1. Hash để phát hiện thay đổi

Có thể lưu SHA-256 digest của file evidence đã được phép thu:

~~~~text
artifact: sanitized-trace.jsonl
bytes: 123456
sha256: <computed-at-collection>
redactionPolicy: incident-safe-v2
~~~~

Đừng tự coi một digest là bằng chứng file đúng, thật hay không bị giả trước khi hash; nó hỗ trợ **kiểm tra integrity sau khi thu**.

### 27.2. Không giữ bí mật trong manifest

Tên file, paths và content hashes cũng có thể tiết lộ metadata nội bộ. Manifest cần access controls tương ứng. Không để secret nằm trong filename hoặc query string.

### 27.3. Evidence reproducibility

Nếu một kỹ sư khác lấy cùng:
- Sanitized config.
- Fixture seed.
- Query shape/bind types.
- Versioned runner.
- Interleaving schedule.

thì họ phải chạy được cùng protocol; khác biệt kết quả phải có logs để giải thích.

## 28. Tái hiện có hệ thống: từ production evidence đến test

Một quy trình:

~~~~mermaid
flowchart TD
    INCIDENT["Production symptom"] --> SCOPE["Bound time/tenant/operation"]
    SCOPE --> COLLECT["Collect sanitized evidence"]
    COLLECT --> HYP["Write hypotheses"]
    HYP --> FIXTURE["Construct minimal fixture"]
    FIXTURE --> REPLAY["Replay queries/interleavings"]
    REPLAY --> CHECK{"Reproduced?"}
    CHECK -->|No| DIFFERENCE["Compare environment/data/timing gaps"]
    DIFFERENCE --> FIXTURE
    CHECK -->|Yes| ASSERT["Add invariant-based regression test"]
    ASSERT --> CHANGE["Fix underlying cause"]
    CHANGE --> VERIFY["Run replay + stress/fault tests"]
    VERIFY --> DOCUMENT["Document outcome/remaining risk"]
~~~~

### 28.1. Bắt đầu từ phạm vi nhỏ

Xác định:
- Một request/operationId.
- Một tenant bị ảnh hưởng.
- Một key hoặc một partition.
- Một time window.
- Một app revision.
- Một query shape.

Tránh “export cả database rồi xem” như bước mặc định.

### 28.2. Xây fixture

Chọn:
- Minimal records.
- Types tương đương.
- Version relationships.
- TTL/expiry conditions.
- Index definitions.
- Read/write consistency.
- Concurrency schedule.
- Pseudonymous IDs.

### 28.3. Đặt assertions trước khi sửa

Ví dụ:
- Không có booking double-confirm.
- Returned sourceVersion >= sessionMinVersion.
- Query kết quả sắp xếp ổn định khi dùng cursor.
- Null/absent fields được xử lý đúng.
- Cache không nhận fill version cũ.
- Conditional conflict trả đúng error.

Nếu sửa code trước khi có assertion, có thể vô tình che lỗi thay vì chứng minh root cause.

### 28.4. Thay một biến mỗi lần

So sánh:
- Same data, different driver.
- Same driver, different readConcern.
- Same query, different index.
- Same topology, different pool max.
- Same interleaving, feature flag on/off.

Thay đồng thời 5 biến sẽ khó biết yếu tố nào thật sự gây lỗi.

## 29. Java: lưu một fixture có version

Một fixture có thể tách:
- Environment assumptions.
- Input records.
- Operation schedule.
- Expected outputs.
- Invariant assertions.

~~~~yaml
fixtureId: booking-cache-race-v1
dataSchemaVersion: 3
seed: 47401
startingState:
  booking:
    tenant: T-test
    bookingId: B-repro
    sourceVersion: 7
    status: PENDING
  cache:
    present: false
events:
  - actor: reader-A
    action: source-read
    expectVersion: 7
  - actor: reader-A
    action: pause-before-cache-write
  - actor: writer-B
    action: conditional-update
    expectedVersion: 7
    newVersion: 8
  - actor: writer-B
    action: invalidate-cache
    watermark: 8
  - actor: reader-A
    action: resume-cache-write
assertions:
  - cacheVersionMustNotBeBelow: 8
  - noBusinessSideEffectsFromReproduction: true
~~~~

Đây là một test specification giả lập; một harness thật cần mapper từ actions tới driver/cache calls cùng exception handling.

### 29.1. Determinism có giới hạn

Một concurrent system không luôn deterministic dù có seed. Cần:
- Controlled barriers.
- Traces/attempt ordering.
- Fault injection vị trí cụ thể.
- Repeated trials.
- Distinguish reproduced vs not reproduced.

### 29.2. Fake clock cho TTL

Một test cần tái hiện expiry không nên dùng sleep 20 phút. Nếu application tạo Clock dependency:
- Inject fixed/offset clock ở domain logic.
- Advance clock trong test.
- Nhưng expiration thực trong Redis/NoSQL engine có clock riêng; fake app Clock không tự điều khiển server TTL.

Khi cần integration test TTL, dùng deployment/test engine có kiểm soát với TTL ngắn và wait bounds, ghi latency/tolerance.

## 30. Query pagination và duplicate/missing rows

Một lỗi phổ biến: phân trang dùng:

~~~~text
SORT createdAt DESC
LIMIT 50
~~~~

Nếu nhiều documents có cùng createdAt, thứ tự giữa chúng không ổn định. Khi dùng offset/skip hoặc concurrent writes:
- Một document xuất hiện ở cả hai pages.
- Một document bị bỏ qua.
- Không tái hiện trên dataset quá ít records.

### 30.1. Dữ liệu để tái hiện

- Ít nhất 100 records.
- Nhiều records có createdAt giống nhau.
- Stable bookingId khác nhau.
- Một concurrent insert/update giữa page 1 và page 2.
- Cùng sort, collation, index và page token behavior.

### 30.2. Kỳ vọng

Nếu contract yêu cầu pagination ổn định:
- Dùng sort tie-breaker unique phù hợp.
- Có snapshot/seek cursor semantics thích hợp.
- Không hứa snapshot nhất quán nếu pages đọc ở times khác nhau và source không hỗ trợ.

### 30.3. Chứng cứ cần

- Full normalized sort.
- Last sort-key values (đã bảo vệ).
- Page token/cursor.
- Source version/snapshot boundary.
- Query times.
- Returned key lists đã pseudonymized.
- Database index plan.

## 31. Serialization/schema bugs

Một lỗi chỉ xảy ra với record legacy:
- Field amountMinor từng là string, nay là long.
- Timestamp lưu dạng epoch seconds thay vì millis.
- Java enum đổi tên.
- Json property null bị bỏ.
- UUID được serialize khác binary/string.
- Decimal precision mất khi dùng double.

### 31.1. Thu version của cả hai phía

- Data schema version.
- Serializer version.
- Java model/Jackson configuration.
- NoSQL driver codec registry.
- Existing record types.
- Migration history.
- API request content type.

### 31.2. Cẩn thận với redaction

Nếu thay mọi giá trị bằng "REDACTED", mất:
- Type.
- Length.
- Null/missing.
- Encoding.
- Unicode normalization.

Có thể thay bằng typed placeholders:

~~~~json
{
  "amountMinor": {"type":"string","length":7},
  "createdAt": {"type":"null"},
  "customerName": {"type":"string","length":12,"value":"[REDACTED]"}
}
~~~~

Đây là **shape metadata**, không phải JSON document để đưa trực tiếp vào NoSQL. Repro fixture nên dựng synthetic values theo đúng type.

### 31.3. Schema drift theo vùng

Một region/pod chưa rollout decoder mới có thể đọc records v3 sai, trong khi vùng khác đúng. Thu rollout distribution và source record schema version.

## 32. Lỗi đọc sau ghi và replica lag

Nếu Java vừa PUT v21 rồi GET trả v20:
- GET có đi qua secondary không?
- Write concern xác nhận mức nào?
- Read concern/consistency yêu cầu gì?
- Session có được truyền theo request không?
- Có minVersion/causal token không?
- Replica lag lúc ấy bao nhiêu?
- Cache/index có ở read path không?

### 32.1. Một test chuẩn

~~~~text
1. Create test entity version=1.
2. Write conditional update to version=2.
3. Record successful ACK and operationId.
4. Immediately issue read with known consistency/session.
5. Compare returned version with stated contract.
6. Repeat via primary/secondary/cache/search paths separately.
~~~~

### 32.2. Một read path có thể không cho strong consistency

Không kết luận “database bug” chỉ vì GSI/search/cached projection trả v1 khi API chỉ hứa eventual. Nếu product requirement cần immediate state, thiết kế read-after-write path phải đáp ứng; evidence packet giúp chỉ ra thiếu sót.

### 32.3. Timestamp của request không tự là version

Hai requests cùng millisecond có thể thấy hai versions khác nhau. SourceVersion/session token thường phù hợp hơn wall-clock để khẳng định freshness.

## 33. Performance bug do index và phân phối dữ liệu

Một query nhanh trên staging nhưng chậm production có thể do:
- Khối dữ liệu lớn hơn.
- Một tenant có partition quá rộng.
- Index thiếu ở một môi trường.
- Data types khác.
- Skew/hot keys.
- Compaction/TTL tombstone.
- Memory cache miss.
- Aggregation fan-out.
- Cross-region reads.
- Rate limiting.

### 33.1. Tạo dataset có tính đại diện

Nếu production:
- 1 triệu items.
- 5% tenants chiếm 90% writes.
- Một hot partition rộng gấp 100 lần median.
- 20% records có field legacy.

Repro cần giữ **tỷ lệ đặc tính** hoặc tạo targeted stress, không nhất thiết sao chép records thật.

### 33.2. Metrics liên quan

- Rows examined vs returned.
- Index hit/miss.
- Partition size.
- Query plan.
- CPU/IO.
- Disk queue.
- Compaction time.
- GC pause.
- Pool waits.
- Retries.
- NoSQL latency p50/p95/p99.
- Offered vs completed RPS.
- Cache hit/miss.

### 33.3. Giảm tác động benchmark

Không chạy load test phá năng lực production trong lúc incident. Sử dụng isolated staging/performance cluster, rate budget và kill switch.

## 34. Phân biệt sự cố ở Java client và NoSQL server

Một request “mất 2 giây” có thể gồm:

~~~~text
Caller -> 100 ms app queue
       -> 300 ms acquire pool connection
       -> 10 ms network send
       -> 40 ms database execute
       -> 50 ms network response
       -> 1500 ms callback/event-loop wait
       = 2000 ms client-visible elapsed
~~~~

Nếu chỉ nhìn DB execute=40 ms thì không giải thích client p99=2 giây.

### 34.1. Chọn spans

- API queue.
- Validation/auth.
- Cache lookup.
- Driver pool acquisition.
- Network request/response.
- Database server processing.
- Serialization.
- Callback scheduling.
- Response send.

### 34.2. Không suy từ “database normal” rằng client luôn bình thường

DB CPU thấp vẫn có thể:
- Client event loop blocked.
- Pool max quá nhỏ.
- DNS/TLS reconnect.
- Network partition.
- Timeout config sai.

### 34.3. Ngược lại, client slow không chứng minh server issue

Một GC pause 2 giây trên một pod có thể trùng thời điểm query. Cần server-side evidence và peer pods làm đối chứng.

## 35. Sự cố phụ thuộc cấu hình đặc biệt

Một số trường hợp chỉ xuất hiện khi:
- TLS cert rotation.
- IAM token hết hạn.
- Secret version đổi.
- Driver có default timeout mới.
- Replica read preference thay đổi.
- Feature flag bật cho tenant.
- Index build đang chạy.
- Redis eviction policy đổi.
- JVM GC mode đổi.
- Cgroup CPU/memory limits đổi.

### 35.1. Ghi config có hiệu lực theo thời điểm

Nếu feature flag bật lúc 10:02 rồi tắt lúc 10:05:
- Screenshot config lúc 10:10 không chứng minh flag bật tại 10:03.
- Cần versioned config/flag change audit, deployment events và effective runtime log.

### 35.2. Source of configuration

Một giá trị có thể đến từ:
- File.
- Environment variable.
- JVM system property.
- Remote config.
- Service discovery.
- Secret manager.
- Driver default.

Thu giá trị **sau resolution** đã redacted, provenance/source và revision. Không ghi secret payload.

## 36. Fault injection có mục tiêu

Để tái hiện lỗi hiếm, có thể gây lỗi trong môi trường được kiểm soát:

| Fault | Thiết lập | Chứng cứ cần |
| --- | --- | --- |
| Network delay | Tăng latency giữa app–DB | Timeouts, retry, duration |
| Connection drop sau write | Mất ACK | OperationId, source commit reconciliation |
| Replica lag | Trì hoãn apply | Returned version vs consistency |
| Primary election/failover | Chuyển owner | Errors, topology, retry labels |
| Cache invalidate delay | Giữ cache stale | Cache/source versions |
| Redis eviction | Evict hot key | Miss spike, origin reads |
| CDC pause | Dừng consumer | Source/target lag, event IDs |
| GC pause | Pause Java test process | Scheduler/callback lag |
| Pool exhaustion | Giảm max connections | Acquire wait, throughput |
| Index absent | Bỏ index trên test cluster | Explain, scanned records |
| Tombstone-heavy partition | Dựng TTL/delete churn | Read p99, tombstone counts |
| Schema mismatch | Inject legacy typed record | Decoder exception, field types |
| Pagination race | Insert giữa pages | Duplicate/missing IDs |
| Concurrent conditional writes | Hai writers cùng expectedVersion | One success, one conflict |
| Clock skew | Inject app-clock offset theo test | Expiry/session logic boundaries |
| Load generator slowdown | CPU throttle tester | Planned vs actual requests |

### 36.1. Không fault inject nguy hiểm lên production tùy tiện

Faults có thể làm mất khả năng phục vụ hoặc ảnh hưởng dữ liệu. Phải dùng:
- Isolated test cluster.
- Synthetic tenants.
- Permission/approval.
- Guardrails và rollback.
- Time-bound fault.
- Defined blast radius.

### 36.2. Fault phải đo được

Không chỉ “restart Redis rồi lỗi xuất hiện”. Ghi:
- Fault start/end UTC.
- Region/node.
- Fault intensity.
- Recovery timing.
- Result distribution.
- Target invariant.
- Metrics before/during/after.

### 36.3. Mỗi test nên có control run

Chạy cùng workload không fault để so:
- Error rate.
- p99.
- Replica lag.
- Cache/version state.
- Invariant results.

Nếu dataset hoặc code thay đổi đồng thời, khó quy nguyên nhân cho fault.

## 37. Các tiêu chí xác nhận đã tái hiện

Một repro tốt có thể có:

~~~~yaml
reproduction:
  scenario: stale-cache-fill-race
  fixtureVersion: v3
  setup: passed
  environmentalMatch:
    driverVersion: matched
    consistencyPolicy: matched
    schemaVersion: matched
    concurrencyPreconditions: matched
  trials: 100
  observedFailureTrials: 98
  expectedInvariant: "cachedVersion >= knownWatermark"
  failureSignature: "stale version accepted"
  evidence:
    - sanitizedTraceRef
    - sourceVersionTimelineRef
    - testResultRef
~~~~

Số liệu minh họa, không phải kết quả chạy thật.

### 37.1. Nếu không tái hiện

Ghi:
- Đã thử bao nhiêu lần.
- Những điều kiện đã mô phỏng.
- Những khác biệt còn tồn tại giữa test và production.
- Evidence nào thiếu.
- Giả thuyết nào đã loại trừ.
- Điều gì làm khả năng tái hiện tăng.

Không viết “Cannot reproduce → not a bug” khi production evidence rõ ràng.

### 37.2. Negative result cũng hữu ích

Nếu lỗi chỉ xuất hiện với:
- Driver v5 nhưng không v4.
- Read preference secondary nhưng không primary.
- Schema v1 nhưng không v2.
- Hot partition 1 triệu rows nhưng không 1.000 rows.

Đó là manh mối quan trọng để tìm root cause.

## 38. Biến repro thành regression test

Sau khi đã có reproduction:
1. Viết test thất bại trước khi sửa.
2. Ghi expected invariant.
3. Đặt fixture deterministic.
4. Sửa root cause.
5. Test pass với cùng fixture.
6. Chạy thêm stress/interleavings.
7. Kiểm tra error/timeout paths.
8. Đo side effects/correctness.
9. Ghi phạm vi chưa được bao phủ.

### 38.1. Không biến test thành tình cờ pass

Nếu race chỉ được test bằng:

~~~~java
Thread.sleep(100);
~~~~

test có thể pass 100 lần vì scheduler may mắn. Nên dùng barriers/hook ở đúng critical boundaries và lặp trial có logging.

### 38.2. Không dùng shared production keys

Regression test phải dùng:
- Synthetic tenant.
- Isolated namespace.
- Predictable operation IDs.
- Cleanup.
- No external payment/notification side effects.
- No production credentials.

### 38.3. Test một invariant sau failure

Với timeout-after-commit:
- Source có tối đa một logical order.
- Retry với same operationId trả cùng canonical result.
- Không có duplicate charges.
- Operation ledger cho biết committed/unknown/failure rõ.

Không chỉ assert HTTP 200.

## 39. Runbook thu thập evidence khi đang có incident

### Bước 1 — Xác định mức độ ảnh hưởng

- Service/endpoint nào?
- Tenants/regions nào?
- Số request lỗi, dữ liệu sai, timeout?
- Có risk privacy/security/financial không?
- Có cần tạm vô hiệu hóa chức năng nguy hiểm?

### Bước 2 — Đặt time window

- UTC start/end có độ bất định rõ.
- RequestId/traceId/operationId.
- Ghi clock sync status.
- Ghi deployment/failover/config changes trong cùng cửa sổ.

### Bước 3 — Thu cấu hình hiệu lực

- App/driver/JDK versions.
- Container image/config revision.
- Region, cluster, read/write consistency.
- Pool, retry, timeouts.
- Index/schema/TTL.
- Feature flags.
- Redact credentials.

### Bước 4 — Thu query/operation shape

- Namespace.
- Filters/keys/parameter types.
- Projection/sort/limit/pagination.
- Read preference/consistency.
- Transaction/session.
- Retry attempts.
- Error categories.
- Query plan khi an toàn.

### Bước 5 — Thu trạng thái dữ liệu tối thiểu

- Key/tenant scope pseudonymized.
- Source version/status.
- Cache/target version.
- Tombstone/TTL.
- Expected vs actual.
- Snapshot boundary.
- Relevant competing operations.

### Bước 6 — Ghép timeline

- Mỗi event có nguồn.
- Tách fact/hypothesis.
- Đánh dấu UNKNOWN commit outcomes.
- Đối chiếu clocks, causal IDs và versions.

### Bước 7 — Bảo vệ chứng cứ

- Encrypt evidence store.
- Retention và access.
- Hash/integrity metadata.
- Không paste raw secrets/PII vào ticket.
- Ghi redaction policy.

### Bước 8 — Tạo fixture synthetic

- Giữ các type/size/versions/ordering gây lỗi.
- Phân phối khi performance issue.
- Concurrency/fault triggers.
- Deterministic seed.

### Bước 9 — Chạy reproduction

- Ghi trial IDs và outcomes.
- So control vs fault.
- Đo source/client metrics.
- Không ảnh hưởng production dữ liệu thật.

### Bước 10 — Xác nhận root cause

- Evidence tương quan với failure.
- Một thay đổi nguyên nhân làm lỗi biến mất.
- Regression test thất bại trước, pass sau.
- Không có invariant/side-effect regression.

## 40. Một incident narrative hoàn chỉnh

**Tình huống:** Trong 15 phút, API GET booking đôi lúc trả trạng thái CONFIRMED sau khi POST cancel trả 200. Chỉ xuất hiện với tenant lớn vào giờ cao điểm.

### 40.1. Chứng cứ ban đầu

- UTC window 10:00–10:15.
- POST cancel operationId OP-901 trả success.
- Source document v21 status CANCELLED.
- GET request R-902 trả v19 status CONFIRMED.
- GET path đi qua Redis L1/L2 và search projection.
- App version v5 chỉ ở cell-2.
- L2 cache TTL 10 phút.
- CDC lag p99 tăng trong window.
- Một hot key vừa bị invalidate.

### 40.2. Các giả thuyết có thể

1. Read preference/replica lag.
2. Cache stale entry chưa invalidate.
3. In-flight cache loader v19 ghi đè sau invalidate.
4. Search projection chưa thấy CDC event.
5. Wrong tenant cache key.
6. App v5 dùng read path khác.

### 40.3. Cần thêm chứng cứ để phân biệt

- GET response cho biết source/cache/index route nào?
- Cache entry version tại thời điểm R-902?
- Invalidation watermark/eventId?
- Search document version?
- CDC checkpoint/lag?
- App config và feature flag ở cell-2?
- Query fingerprint/tenant scope?
- Có in-flight loader start trước POST cancel không?

### 40.4. Một reproduction tối thiểu

Cho:
- Source v19.
- Reader bắt đầu load v19.
- Pause trước cache fill.
- Writer update v20/v21 và invalidate.
- Reader cũ resume.
- Assert cache không được chứa v19 như fresh.

Nếu phiên bản code cũ nhận stale fill, phiên bản mới có version fence từ chối, đó là một regression test mạnh cho một root cause cụ thể.

### 40.5. Những gì không nên kết luận vội

- “Database rollback” vì GET trả cũ.
- “Cache bug” chỉ vì cache có mặt.
- “CDC lost event” chỉ vì search chậm.
- “API fixed” chỉ vì restart pod làm lỗi biến mất.
- “Data corruption” trước khi so boundaries và versions.

## 41. Những nhầm lẫn hay gặp

1. **“Có screenshot lỗi là đủ tái hiện.”** Thiếu environment/timing/query/data.
2. **“Timestamp không cần timezone.”** Dễ ghép sai sự kiện.
3. **“Java nanoTime là global timestamp.”** Chỉ dùng đo durations trong process.
4. **“Log A xuất hiện trước B nghĩa A commit trước.”** Clock skew/log flush.
5. **“Client đã gửi write nghĩa source đã commit.”** Không đủ.
6. **“Socket timeout nghĩa rollback.”** Có UNKNOWN outcome.
7. **“Log success nghĩa user đã thấy dữ liệu.”** Có cache/index/UI.
8. **“File cấu hình trong Git là runtime config thật.”** Có overrides/flags.
9. **“Một version name đủ.”** Cần build digest/revisions.
10. **“Driver default giống nhau giữa mọi versions.”** Phải xác minh.
11. **“Query name giống nhau nghĩa input giống.”** Bind types/values khác.
12. **“Filter giống nhau nghĩa access path giống.”** Index/stats khác.
13. **“Explain sau incident là plan lúc incident.”** Có thể đã đổi.
14. **“Explain luôn không tốn tài nguyên.”** Có thể đắt.
15. **“Không cần sort khi tái hiện pagination.”** Thứ tự là trigger.
16. **“Query limit không ảnh hưởng lỗi.”** Có thể ảnh hưởng plan/paging.
17. **“Chỉ log raw query cho nhanh.”** Có PII/secrets.
18. **“Redact tất cả thành string REDACTED là đủ.”** Mất type/shape.
19. **“Dùng data sạch hơn vẫn tái hiện lỗi legacy.”** Có thể không.
20. **“Null và missing giống nhau.”** Tùy engine/codec khác.
21. **“Decimal và double luôn tương đương.”** Precision/rounding.
22. **“Một row trên staging đủ cho performance bug.”** Skew/size là trigger.
23. **“Mọi replica đọc cùng state tức thời.”** Consistency/lag.
24. **“GSI miss nghĩa source không có item.”** Eventual index.
25. **“Cache hit nghĩa source còn cùng version.”** Có stale.
26. **“TTL logical expiry nghĩa đã reclaim vật lý.”** Khác nhau.
27. **“Event lag nghĩa event đã mất.”** Có thể backlog.
28. **“Current snapshot tái dựng mọi historical events.”** Không.
29. **“Một query timeout chứng minh DB chậm.”** Pool/GC/network.
30. **“Server latency nhỏ nghĩa API latency nhỏ.”** Queue/callback delays.
31. **“Không reproduce thì không có bug.”** Thiếu đúng conditions.
32. **“Thêm sleep làm race deterministic.”** Không.
33. **“Tăng logging luôn giúp.”** Có observer effect.
34. **“Trace sampling 1% chắc bắt lỗi hiếm.”** Có thể miss.
35. **“Raw stack trace luôn an toàn lưu.”** Có thể lộ internals/payload.
36. **“Hash email là anonymous.”** Có thể bị đoán.
37. **“Kubernetes Secret base64 là encryption.”** Không.
38. **“Heap dump không chứa credential.”** Có thể chứa.
39. **“Một SQL-like query là đủ để chẩn đoán NoSQL.”** Partition/index/consistency khác.
40. **“Repro data có thể lấy từ production tùy tiện.”** Phải phân quyền/retention.
41. **“Một test pass sau fix chứng minh root cause.”** Cần failing baseline/causal evidence.
42. **“Restart làm biến mất lỗi tức là đã sửa.”** Có thể xóa dấu vết timing/cache.
43. **“Một p99 đẹp nghĩa workload đúng.”** Generator có thể tự giảm tải.
44. **“Không cần ghi retries.”** Physical attempts ảnh hưởng state/latency.
45. **“DB read cũ là luôn bug.”** Phụ thuộc consistency contract.
46. **“NoSQL write success nghĩa search visible ngay.”** Projection có lag.
47. **“Tài liệu incident nên chứa mọi secret để tiện tra.”** Không.
48. **“Hash evidence chứng minh nguồn đã đúng.”** Chỉ hỗ trợ integrity sau capture.
49. **“Full scan production là bước debug mặc định.”** Có thể quá tải và lộ dữ liệu.
50. **“Chỉ cần fix code, không cần fixture regression.”** Dễ tái phát.

## 42. Bài tập thực hành: dựng bộ chứng cứ và tái hiện lỗi NoSQL

Một ứng dụng Java 21 dùng:
- MongoDB làm source lưu Bookings.
- Redis L2 cache và Caffeine L1.
- DynamoDB cho bảng nghiệp vụ phụ.
- OpenSearch làm read model tìm kiếm.
- CDC relay giữa source và search.
- Ba regions và nhiều pods mỗi region.
- Có TTL, schema evolution v1→v3, secondary reads.
- Một vài requests báo stale; một số writes timeout nhưng source có thể đã commit.
- Production data có PII và nhiều tenants.

### Phần A — Thu time window

Người dùng báo “khoảng 17:00 giờ Việt Nam ngày 14/11/2026”.

1. Viết UTC tương ứng khi biết offset +07:00.
2. Nếu uncertainty ±10 phút, ghi interval thế nào?
3. Dùng System.nanoTime để tính gì?
4. Vì sao không trừ raw nanoTime giữa hai pods?
5. Sự kiện source commit và replica apply cần mốc gì?

**Gợi ý:** 17:00 +07:00 tương ứng 10:00Z cùng ngày.

### Phần B — Chụp effective configuration

Thiết kế manifest gồm:
- Build, container image, JDK, driver.
- Replica/region/cluster.
- Read/write consistency.
- Pool timeout/max.
- Cache TTL.
- Index revision.
- Feature flags.
- Auth principal alias.
- Không có password/token.

Giải thích vì sao application.yml trong Git chưa đủ.

### Phần C — Query descriptor

Một request trả thiếu một booking ở page 2. Thu:
- Filter/predicate.
- Parameter types.
- Sort/collation.
- Limit/page token.
- Index/plan.
- Read preference.
- Source snapshot/createdAt tie cases.

Thiết kế synthetic dataset để tái hiện duplicate/missing rows.

### Phần D — Dữ liệu legacy

Records có:
- amountMinor là string ở v1, long ở v3.
- createdAt có thể null.
- bookingId có Unicode.
- Một số fields missing.

1. Viết typed shapes.
2. Tạo fixtures không dùng PII.
3. Vì sao không chuyển tất cả thành JSON string mới?
4. Kiểm tra deserialization/roundtrip.
5. Ghi schema policy version.

### Phần E — Race cache

- A đọc source v7 nhưng bị pause.
- B update v8 và invalidate.
- A ghi cache v7.

Thiết kế timeline, barriers và version watermark assertion.

### Phần F — UNKNOWN commit

- POST booking timeout sau 2 giây.
- Retry cùng user.
- Source có thể đã tạo booking ở attempt đầu.

1. Những IDs nào cần thu?
2. Có được kết luận rollback không?
3. Idempotency ledger dùng làm gì?
4. Thiết kế test drop ACK.
5. Bất biến nào xác nhận không double-booking?

### Phần G — Source vs search

- MongoDB v21.
- Search v19.
- CDC lag 3 giây.
- GET sau write tại 500 ms.

1. Có chắc bug không?
2. Hợp đồng read-your-writes và eventual khác nhau ra sao?
3. Thu những timestamps/versions nào?
4. Khi nào nói CDC lost event?
5. Kiểm tra search refresh/alias thế nào?

### Phần H — Performance

Một tenant có partition 100 lần lớn hơn median; p99 tăng lúc compaction.

1. Vì sao staging 1.000 records không đủ?
2. Cần ghi partition cardinality và tombstones gì?
3. Client pool waits vs server processing time khác nhau?
4. Thử nghiệm source load thế nào để không quá tải?
5. Nếu generator tự chậm, phải ghi planned/sent/completed ra sao?

### Phần I — Security

Một kỹ sư định upload full MongoDB dump và JVM heap dump vào public issue.

1. Rủi ro nào?
2. Có thể thu dữ liệu tối thiểu nào?
3. Synthetic/pseudonymous fixture tạo thế nào?
4. Ai có quyền xem raw artifacts nếu thật sự cần?
5. Retention/audit/secret redaction?

### Phần J — Fault injection

Lập kịch bản cho:
1. Network delay.
2. Lost ACK after source commit.
3. MongoDB replica lag.
4. Redis eviction.
5. CDC pause.
6. Search index refresh delay.
7. GC pause.
8. Connection pool exhaustion.
9. TTL expiry boundary.
10. Index missing.
11. Schema legacy record.
12. Clock skew.
13. Concurrent conditional writes.
14. Pagination with duplicate sort keys.
15. Region failover.

Với mỗi fault, ghi:
- Setup.
- Captured timestamps.
- Config version.
- Query fingerprint.
- Data fixture.
- Expected/actual.
- Assertion.
- Recovery/reset.

### Phần K — Incident evidence packet

Viết một YAML/JSON gồm:
- IncidentId.
- Time window UTC.
- Request/trace/operation IDs.
- Effective environment.
- Sanitized query shape.
- Source/cache/search versions.
- Evidence references.
- Known/unknown facts.
- Hypotheses.
- Repro fixture ID và seed.
- Reproduction attempts/results.
- Privacy classification.

### Phần L — Phản biện

Một đồng nghiệp nói:

> “Bug chỉ xảy ra vài lần nên ghi log nguyên query và response, dump cả database rồi thử lại. Chụp config file trên Git là đủ. Nếu không tái hiện trên staging thì chắc do người dùng nhầm. Restart pods rồi xóa Redis để hết lỗi. Timeout nghĩa database không ghi gì nên retry write thoải mái.”

Hãy chỉ ra:
- PII/secret exposure.
- Runtime config drift.
- Data shape/skew.
- Replica/read consistency.
- Race và observer effect.
- UNKNOWN commit.
- Idempotency.
- Evidence loss sau restart/cache flush.
- Repro fixture/clock/trace requirements.
- Regression tests và production safety.

### Hướng giải

Một phương án đầy đủ:
- Thu **time window UTC + monotonic durations** với request/operation/trace IDs.
- Ghi **effective config** và deployment/driver/index/schema revisions đã redacted.
- Lưu **query shape, bind types, consistency, pagination, retry** và explain khi an toàn.
- Dựng **synthetic fixture** giữ type/size/version/TTL/concurrency trigger.
- Ghép timeline từ source/cache/index/CDC, tách fact và hypothesis.
- Chạy controlled repro bằng barriers/fault injection trên môi trường được phép.
- Tạo failing regression assertion về invariant trước khi sửa.
- Lưu artifacts vào evidence store có quyền, hash/retention và không chứa secret.
- Ghi rõ khi chưa tái hiện được và những điều kiện còn thiếu.

## 43. Checklist sẵn sàng chẩn đoán NoSQL

1. **Có requestId/traceId/operationId cho đường lỗi?**
2. **Có UTC timestamps với offset và time window?**
3. **Có duration đo bằng monotonic clock trong process?**
4. **Có xác định clock skew/uncertainty khi ghép nodes?**
5. **Có phân biệt attempt/ACK/commit/visibility times?**
6. **Có biết source of truth và read model/cache path?**
7. **Có build/container/Java/driver versions thực tế?**
8. **Có effective config revision, không chỉ Git file?**
9. **Có feature flags và rollout distribution theo thời điểm?**
10. **Có cluster/region/shard/replica alias?**
11. **Có consistency, read/write concern và session settings?**
12. **Có pool, retry, deadlines, timeouts?**
13. **Có schema/serializer/index revisions?**
14. **Có TTL, cache, compaction/repair state khi liên quan?**
15. **Query shape đã gồm filter/key condition, projection, sort, limit?**
16. **Bind parameter types và boundary values đã mô tả?**
17. **Có pagination token/cursor semantics khi cần?**
18. **Có query plan/explain với thời điểm và budget?**
19. **Có sourceVersion/ETag/conditional values?**
20. **Có expected/actual values và bất biến rõ ràng?**
21. **Có tách source/cache/index versions?**
22. **Có dữ liệu tối thiểu giữ null/missing/legacy types?**
23. **Có giữ partition skew/size/cardinality cho performance?**
24. **Có tái hiện TTL/timezone/clock boundaries?**
25. **Có ghi concurrency actors/interleaving/transactions?**
26. **Có xử lý timeout-after-commit như UNKNOWN khi phù hợp?**
27. **Có idempotency key và retry attempt IDs?**
28. **Có quan sát CDC lag/index visibility khi projection sai?**
29. **Có phân biệt client pool/GC/network và DB service time?**
30. **Có lưu metrics p99, errors, retries, pool waits theo window?**
31. **Có dùng controlled fault injection với guardrails?**
32. **Có fixture seed và deterministic barriers khi phù hợp?**
33. **Không copy raw production secrets/PII vào logs/repo?**
34. **Evidence có access control, encryption, hash, retention?**
35. **Có ghi evidence provenance và phương pháp redaction?**
36. **Có tách FACT/HYPOTHESIS/UNKNOWN?**
37. **Có bảng điều kiện đã thử và chưa thử?**
38. **Có regression invariant trước khi sửa?**
39. **Không tuyên bố root cause chỉ vì restart làm lỗi biến mất?**
40. **Có kết quả tái hiện/không tái hiện với mức độ chắc chắn đúng?**

**Kết luận:** Một lỗi NoSQL khó tái hiện thường không thiếu mã nguồn mà thiếu **ngữ cảnh chạy thực tế**. Muốn chẩn đoán đáng tin, hãy thu đồng thời **thời điểm có timezone và duration đúng**, **cấu hình/phiên bản thực sự có hiệu lực**, **truy vấn cùng kiểu tham số, access path và consistency**, và **dữ liệu tối thiểu giữ được schema, version, TTL, phân phối và các interleavings quan trọng**. Gắn chúng bằng **requestId, traceId, operationId và source version** để dựng timeline dựa trên chứng cứ, phân biệt quan sát với giả thuyết và lỗi nguồn với độ trễ của cache/CDC/index. Dùng synthetic fixtures, controlled fault injection và regression assertions để tái hiện mà không sao chép dữ liệu khách hàng hoặc bí mật. Cuối cùng, một báo cáo đáng tin phải nói rõ **đã chứng minh điều gì, chưa biết điều gì, cách chạy lại và kết quả sau sửa**, thay vì chỉ có dòng log lỗi và một lần restart làm triệu chứng biến mất.
