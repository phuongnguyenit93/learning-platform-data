# Danh mục giới hạn cần kiểm tra theo phiên bản và môi trường triển khai MongoDB

## Mục tiêu bài học

MongoDB có nhiều nhóm giới hạn: giới hạn cứng của định dạng BSON, điều kiện hỗ trợ tính năng theo **server version và Feature Compatibility Version (FCV)**, giới hạn bộ nhớ của aggregation, topology của replica set/sharded cluster, hạn chế của index/transaction/change stream và quota theo **môi trường Atlas hoặc self-managed**. Một số giá trị là hằng số tương đối ổn định; nhiều giá trị khác thay đổi theo bản phát hành, cấu hình, dịch vụ quản lý, driver, hệ điều hành và workload.

Ví dụ, câu “MongoDB giới hạn 16 MB” không đủ rõ: **16 MiB áp dụng cho mỗi BSON document**, không áp dụng cho tổng collection hoặc toàn bộ cursor. Câu “aggregation giới hạn 100 MB” cũng không đủ: đây có thể là ngưỡng bộ nhớ của một số stages, trong khi `$facet` có ngưỡng riêng và output cuối vẫn không được vượt BSON document limit. Còn “Atlas chỉ cho tối đa N connections” không thể tra theo tên MongoDB chung chung; phải biết **tier, region, service type và chính sách quota tại thời điểm triển khai**.

Bài thuộc **Database Engine Document MongoDB → Tổng kết và tra cứu → Danh mục giới hạn cần kiểm tra theo phiên bản và môi trường triển khai**.

Bài này là một **sổ tra cứu và quy trình kiểm tra**. Mục đích không phải học thuộc một bảng số dễ lỗi thời, mà biết **phải tra điều gì, ở đâu, trên cluster nào, khi nào và bằng phép kiểm chứng nào**.

Sau khi học, bạn có thể:

1. Phân loại giới hạn thành **hard limit**, **configurable limit**, **service quota**, **performance/operational limit** và **application policy**.
2. Ghi chính xác bộ nhận diện deployment: server build, FCV, topology, Atlas tier, driver, edition và region.
3. Xác minh giá trị tại server bằng `hello`, `buildInfo`, `getParameter`, `collStats`, `listIndexes`, `serverStatus` và cấu hình quản trị được cấp quyền.
4. Xây ma trận tra cứu giới hạn BSON, names, nesting, indexing, aggregation, writes, transactions, sessions, cursors, replication, sharding, change streams, TTL, time-series và GridFS.
5. Phân biệt các giới hạn kỹ thuật của MongoDB với quota Atlas Search/Vector Search, managed tiers và hệ điều hành.
6. Áp dụng bảng kiểm tra trước **upgrade, migration, production rollout, load test và xử lý sự cố**.
7. Ưu tiên biện pháp đúng: giảm kích thước document, chỉnh schema/index, phân trang, chia batch, bổ sung capacity hoặc đổi topology — thay vì tăng một tham số không liên quan.
8. Lưu lại bằng chứng và ngày kiểm tra, không truyền miệng một con số thiếu ngữ cảnh.

> **Quy tắc tổng quát:** Bất kỳ giới hạn nào dùng để quyết định kiến trúc/triển khai phải được ghi kèm **server version + FCV + topology + tier/edition + driver + cấu hình + nguồn tài liệu và ngày xác nhận**. Không chỉ ghi một giá trị N.

---

## 1. Năm loại giới hạn cần phân biệt

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| **Hard format/protocol limit** | Không tăng tùy tiện bằng cấu hình | BSON document tối đa 16 MiB |
| **Feature/version limit** | Tính năng hoặc hành vi thay theo server/FCV | Khả năng dùng một aggregation operator |
| **Configurable resource limit** | Có tham số hoặc tùy chọn trong phạm vi hỗ trợ | Connection pool, `maxTimeMS`, một số memory/disk policies |
| **Managed-service quota** | Do nhà cung cấp/plan/tier/region quyết định | Atlas connections, backup retention, Search nodes |
| **Operational/application limit** | Do SLO, tải, nguồn lực hoặc contract tự đặt | Batch 200–500 writes, p99 latency, max event payload |

### 1.1. Hard limit không có nghĩa toàn hệ thống bị giới hạn như vậy

Ví dụ 16 MiB là kích thước **mỗi document**. Collection có thể chứa hàng triệu documents. Với dữ liệu file lớn, chọn GridFS/object storage, không cố biến một document thành 50 MiB.

### 1.2. Configurable không có nghĩa nên tăng

Một mức bộ nhớ sort, số connections hay transaction timeout có thể liên quan cấu hình, nhưng tăng quá cao làm node OOM, cạn file descriptors hoặc khiến workload khác chậm. Phải đánh giá resource budget và các ràng buộc của managed service.

### 1.3. Quota khác khả năng engine

Một lệnh hợp lệ trên MongoDB Enterprise self-managed chưa chắc dùng được trên Atlas tier thấp vì policy/capacity/tính năng. Ngược lại, Atlas Search có quota riêng không được suy từ giới hạn aggregation của mongod.

### 1.4. Performance limit không phải một con số chung

Một cluster có thể xử lý hàng nghìn thao tác/giây ở workload nhỏ nhưng không đáp ứng nổi cùng QPS nếu documents lớn, indexes nhiều, hot shard, query không chọn lọc, disk chậm hoặc yêu cầu write concern cao.

### 1.5. Application policy nên thấp hơn hard limit

Nếu một entity dự kiến mở rộng, đặt max BSON size cảnh báo thấp hơn 16 MiB, giới hạn số array elements và kích thước payload. Đừng thiết kế nghiệp vụ sống sát trần rồi chờ error.

---

## 2. “Chữ ký môi trường” cần chụp trước khi tra limit

Trước khi quyết định một con số có áp dụng không, ghi lại:

| Thuộc tính | Cần biết cụ thể |
|---|---|
| Server version | Build version và patch level trên các nodes liên quan |
| FCV | Feature Compatibility Version thực tế |
| Deployment | Standalone, replica set hay sharded cluster |
| Edition | Community, Enterprise, managed Atlas hoặc sản phẩm tương thích khác |
| Provider/tier | Atlas shared/Flex/dedicated và cấu hình thực tế khi thích hợp |
| Region/cloud | AWS/Azure/GCP, region và network topology |
| Storage | WiredTiger, disk/IOPS, storage quota, filesystem |
| Driver | Java Sync/Reactive, Spring Data MongoDB, Node.js, Python… và versions |
| Auth/role | Quyền đọc server parameters/metrics, direct DB access |
| Workload | Document size, indexes, read/write mix, transaction rate, hot keys |
| Data placement | Shard key, replica members, zones, Search nodes |
| Versioned docs | Đường dẫn tài liệu đúng release, ngày truy cập |
| Governance | Ai phê duyệt thay đổi/capacity/backup và rollback |

### 2.1. Vì sao phải ghi FCV?

Server binary có thể đã được nâng nhưng FCV vẫn ở giá trị cũ trong một giai đoạn upgrade. Một số feature hoặc behavior phụ thuộc FCV. `db.version()` **không thay thế** việc xác định FCV.

### 2.2. Vì sao phải ghi driver?

Client có connection pool, timeout, codec, retry policies, cursor settings và compatibility matrix riêng. Cùng server version nhưng hai ứng dụng dùng driver khác nhau có thể gặp giới hạn từ phía client trước.

### 2.3. Vì sao phải ghi tier?

Đối với managed deployments, quotas của tier và backup/network/scale policies có thể thay đổi theo sản phẩm và thời điểm; không dùng giới hạn self-managed làm cam kết Atlas.

---

## 3. Những lệnh nhận diện môi trường trong mongosh

Chỉ chạy trên cluster bạn được phép truy cập; một số lệnh yêu cầu quyền quản trị.

~~~javascript
// Server version của kết nối hiện tại.
db.version();

// Build metadata (đừng log nguyên output nhạy cảm ra nơi công khai).
db.adminCommand({ buildInfo: 1 });

// Topology / primary / khả năng của server đang kết nối.
db.adminCommand({ hello: 1 });

// FCV nếu quyền và deployment cho phép.
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});

// Replication status trên member nếu có quyền.
db.adminCommand({ replSetGetStatus: 1 });
~~~

### 3.1. Trường quan trọng trong `hello`

Tùy server/route, response có thể bao gồm:

- `maxBsonObjectSize`: kích thước BSON document tối đa được quảng bá.
- `maxMessageSizeBytes`: giới hạn network protocol message.
- `maxWriteBatchSize`: số write operations tối đa theo protocol batch.
- `setName`, `hosts`, `isWritablePrimary`: thông tin replica set.
- `msg: "isdbgrid"`: dấu hiệu mongos.
- `logicalSessionTimeoutMinutes` khi khả dụng.

Không suy “maxWriteBatchSize đủ lớn” nghĩa app có thể gửi từng operation payload lớn tùy ý; giới hạn BSON, message size, driver splitting và memory vẫn áp dụng.

### 3.2. Không xem một mongos là toàn bộ cluster

Trong sharded cluster, mongos có thể trả metadata về route; server versions, parameter settings và capacity của shards/config servers cũng quan trọng. Atlas GUI/API hoặc cluster inventory có thể là nguồn thẩm quyền tốt hơn khi quyền truy cập shell hạn chế.

### 3.3. Permission denied không phải không có giới hạn

Trên Atlas managed tier, nhiều `getParameter`, `serverStatus`, filesystem commands bị hạn chế. Khi lệnh không được phép, dùng Atlas UI/API, metrics, release docs và operator runbook thay vì tìm cách tăng quyền tùy tiện.

### 3.4. Lưu output có kiểm soát

Không gửi toàn bộ `buildInfo`, connection string, user/host/IP/cluster details và secrets vào tài liệu công khai. Lưu metadata cần thiết trong hệ thống quản trị được phân quyền.

---

## 4. Danh mục nhanh: giới hạn nào có mốc số ổn định?

| Nhóm | Mốc hay gặp | Khi sử dụng phải lưu ý |
|---|---|---|
| BSON document | **16 MiB = 16.777.216 bytes** | Áp cho một BSON document, không phải toàn collection |
| BSON nesting depth | **100 levels** | Dữ liệu quá lồng nhau có thể lỗi |
| Aggregation pipeline stages | **1.000 stages** | Quy tắc tính trước/sau parse/optimizer theo docs |
| Nhiều blocking aggregation stages | Ngưỡng bộ nhớ thường **100 MB** | Không phải ngưỡng chung cho mọi stage/operation; spill tùy điều kiện |
| `$facet` document | **100 MB** nội bộ | Facet không spill; output cuối vẫn ≤16 MiB |
| Chỉ mục/collection | Tài liệu nêu mức giới hạn **64 indexes** ở nhiều server versions | Kiểm tra tài liệu version, hidden/wildcard/search indexes |
| Compound index keys | Tài liệu nêu tối đa **32 indexed fields** trong compound index ở nhiều versions | Kiểm tra index loại gì/version và key design |
| Default transaction lifetime | Thường khoảng **60 giây** ở nhiều server versions | Kiểm tra `transactionLifetimeLimitSeconds`, Atlas restrictions và workload |

**Bảng trên không phải giấy phép mặc định cho mọi deployment.** Các mốc ở hai dòng index và transaction phải tra trong **MongoDB Limits**, **Transactions** và cấu hình của version đang vận hành trước khi đưa vào deployment gate. Một số limits khác không nên đóng đinh trong tài liệu vì phụ thuộc topology/tier/driver.

### 4.1. Thông điệp về đơn vị

**MiB** = 1.048.576 bytes. **MB** = 1.000.000 bytes trong cách dùng SI, nhưng tài liệu/log có thể dùng đơn vị theo ngữ cảnh. Khi kiểm tra size, dùng trường `bytes` từ server hoặc nêu rõ đơn vị; đừng nhầm 16 MiB với 16.000.000 bytes.

### 4.2. Tránh đem mốc cũ áp lên server mới

Một số giới hạn index key size, transaction oplog behavior, aggregation spilling hoặc naming từng thay đổi theo MongoDB major releases. Không dùng slide/blog 5 năm trước để quyết định an toàn nâng cấp.

---

## 5. BSON: giới hạn của document, trường và nesting

### 5.1. Document ≤16 MiB

Ví dụ một document order lưu mọi audit event:

~~~javascript
{
  _id: "ORD-101",
  status: "PAID",
  audit_events: [
    // Tăng mãi qua nhiều năm.
  ]
}
~~~

Một lần `$push` có thể khiến kết quả vượt 16 MiB dù những năm trước vẫn ghi thành công.

### 5.2. Không có “một max elements” áp cho mọi array

Kích thước array phụ thuộc kích thước từng element, tên/index keys, nested documents và fields khác. Mảng 100.000 số nguyên nhỏ có thể nhẹ hơn 1.000 objects chứa strings dài.

### 5.3. Kiểm tra BSON bytes bằng `$bsonSize`

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      tenant_id: 1,
      bson_bytes: {
        $bsonSize: "$$ROOT"
      }
    }
  },
  { $sort: { bson_bytes: -1 } },
  { $limit: 20 }
], {
  allowDiskUse: true
});
~~~

Cần đọc toàn document để tính size; đây là scan có thể nặng trên collection lớn. Chạy theo tenant/cohort/sampling hoặc ngoài giờ cao điểm.

### 5.4. Đếm số phần tử mảng an toàn

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      audit_count: {
        $cond: [
          { $isArray: "$audit_events" },
          { $size: "$audit_events" },
          0
        ]
      },
      bson_bytes: { $bsonSize: "$$ROOT" }
    }
  },
  { $sort: { audit_count: -1 } },
  { $limit: 20 }
]);
~~~

`$size` yêu cầu array. Dùng `$isArray`/validation nếu dữ liệu có thể missing/null/incorrect type.

### 5.5. Collection lớn hơn 16 MiB là bình thường

Một collection có thể chứa nhiều BSON documents, được truy vấn qua cursor. **16 MiB áp cho từng document**, không phải tổng các documents mà cursor trả qua nhiều batches.

### 5.6. Binary/file lớn

Dữ liệu một file vượt 16 MiB nên dùng **GridFS** hoặc object storage theo yêu cầu query/retention, không cố encode base64 vào document. GridFS chia file thành chunks và metadata; nó không nới giới hạn một BSON document.

### 5.7. Những giới hạn liên quan cần tra

- Độ dài field name và restrictions về ký tự (`$`, `.`) theo server/driver/version.
- Độ sâu lồng documents.
- BSON type/value sizes, encoding UTF-8, BSON numeric types.
- Kích thước document sau `update`, không chỉ input trước.
- Schema validator và giới hạn indexed paths trên nested arrays.

**Không suy kích thước từ `JSON.stringify().length`**, vì JSON text và BSON khác encoding/overhead.

---

## 6. Namespace, collection, field name và identifier

### 6.1. Những thứ phải tra theo version/topology

- Maximum namespace length gồm database và collection name.
- Restrictions của collection/system names, ký tự `$` hoặc `.`.
- Giới hạn index name / namespace khi sharding.
- Database/collection name constraints trên Windows/Linux.
- Hành vi case-sensitive và restrictions của filesystem/tooling.
- Giới hạn BSON document nesting.

### 6.2. Vì sao không đặt tên sát trần?

Một collection có tên rất dài có thể tương tác với internal namespace, index tools và compatibility với version cũ. Dùng naming convention ngắn, ổn định và không dựa vào mức giới hạn cũ.

### 6.3. Không nhầm tên Java và tên BSON

Spring Data `@Field("tenant_id")` map property `tenantId` sang field khác. Giới hạn/restrictions áp cho **BSON path thực**, không phải chỉ tên Java trong entity.

### 6.4. Unicode/collation

Không dùng suy luận “hai tên nhìn giống nhau thì unique index chắc coi giống nhau”. Collation và normalization tác động equality/sorting/uniqueness; phải định nghĩa explicit.

---

## 7. Chỉ mục: số lượng, số fields và kích thước key

MongoDB có index limits khác nhau theo phiên bản và loại index.

### 7.1. Những mục phải xác minh

1. Số indexes tối đa cho một collection.
2. Số fields tối đa trong compound index.
3. Giới hạn key/index entry nếu tồn tại ở version cụ thể.
4. Multikey restrictions, đặc biệt compound indexes với nhiều array paths.
5. Unique index semantics của missing/null và collation.
6. Partial index filter capabilities.
7. Wildcard index restrictions.
8. Text, geo, hashed, TTL và clustered index rules.
9. Hidden indexes, index build concurrency và resource budgets.
10. Sharded unique index restrictions theo shard key và topology.

### 7.2. Tra indexes hiện có

~~~javascript
db.orders.getIndexes();
~~~

Đếm chúng:

~~~javascript
db.orders.getIndexes().length;
~~~

Kết quả gồm `_id` index. Khi tính quota theo index type/version, đối chiếu docs thay vì chỉ cộng tất cả UI Search indexes vào B-tree count.

### 7.3. Index nhiều chưa chắc tốt

Mỗi insert/update/delete có thể phải duy trì nhiều index entries. Với inventory counter hoặc array thường đổi, thừa index gây write amplification và tăng storage.

### 7.4. Compound multikey với nhiều arrays

Một document chứa hai arrays được index cùng lúc trong một compound multikey index có restrictions (parallel arrays). Không tự nghĩ “chỉ cần index hai mảng là query nhanh”. Kiểm tra restrictions và thay schema/query nếu cần.

### 7.5. Index size/performance khác limit số indexes

Tạo index hợp lệ không chứng minh bộ nhớ/disk/IOPS đủ. Dùng `db.collection.stats()`, execution stats, index sizes, workload benchmark và capacity model.

### 7.6. Index key limit thay theo đời MongoDB

Đã có những thay đổi lịch sử về index key limitations. Không copy một con số 1024-byte từ tài liệu phiên bản cũ áp cho server mới; tham chiếu versioned documentation.

---

## 8. Unique index, null/missing và migration

### 8.1. Single-field unique index

Nếu nhiều documents thiếu field hoặc có null, việc tạo unique index có thể thất bại tùy shape/index rules. Trước migration cần đếm duplicates và xác định requirement thực sự.

### 8.2. Partial unique index

Khi chỉ muốn enforce uniqueness cho documents đã chuẩn hóa:

~~~javascript
db.customers.createIndex(
  {
    tenant_id: 1,
    normalized_email: 1
  },
  {
    unique: true,
    partialFilterExpression: {
      normalized_email: { $type: "string" }
    },
    name: "uq_tenant_normalized_email"
  }
);
~~~

Documents ngoài partial filter **không được** index này bảo vệ; không nhầm với universal uniqueness.

### 8.3. Collation

Unique equality phụ thuộc collation. Nếu business email/username cần case-insensitive uniqueness, thiết kế normalization hoặc collation phù hợp, không chỉ tạo unique index binary.

### 8.4. Sharded uniqueness

Với sharded collections, unique index/constraint phải theo supported combinations của shard key và phiên bản. Không cam kết global uniqueness khi index không đáp ứng sharding rules.

### 8.5. Migration gate

Trước khi tạo/drop unique index: kiểm tra existing duplicates, null/missing, write paths, backup, rollout mixed versions và phương án rollback.

---

## 9. Aggregation: 16 MiB output khác 100 MB memory

Một pipeline có thể thất bại vì:

- Một resulting BSON document vượt 16 MiB.
- Một blocking stage cần memory quá mức và không thể/don't spill.
- Một `$group` accumulator như `$push` chứa quá nhiều values.
- Một `$facet` output vượt ngưỡng riêng.
- Pipeline có trên 1.000 stages.
- Quá tải CPU/disk/network hoặc timeout, dù không chạm hard limit.

### 9.1. Dùng cursor không có nghĩa được tạo một document khổng lồ

Query trả 1 triệu documents nhỏ qua cursor có thể hợp lệ. Nhưng `$group: {items: {$push:"$$ROOT"}}` gom chúng thành **một** result document có thể vượt giới hạn BSON.

### 9.2. `$lookup` fan-out

Một parent join 500.000 child documents tạo array lớn. Dùng foreign pipeline với `$match`, `$sort`, `$limit` và `$project` nếu business chỉ cần top-N; hoặc query children trực tiếp theo pages.

### 9.3. `$unwind` làm tăng cardinality

Mỗi array element thành một pipeline row. Nếu sau đó `$lookup` và `$group` thêm, số rows/state có thể tăng rất mạnh. Đo cardinality ở từng stage.

### 9.4. `$facet`

Facet trả một document với arrays cho sub-pipelines, có ngưỡng nội bộ khoảng 100 MB và **không spill ra disk**. Result cuối vẫn chịu BSON document 16 MiB. `allowDiskUse:true` không biến facet thành nơi chứa unlimited history.

### 9.5. Stage count

Một pipeline động sinh trên 1.000 `$addFields`/`$project` có thể lỗi dù từng stage đơn giản. Hợp nhất operations, dùng `$map`/`$reduce` đúng semantics hoặc materialize pipeline thành bước hữu hạn.

---

## 10. Giới hạn bộ nhớ của aggregation và `allowDiskUse`

### 10.1. Những stages thường có áp lực memory

- `$sort` (blocking).
- `$group`.
- `$bucket`/`$bucketAuto`.
- `$sortByCount`.
- `$setWindowFields`.
- Một số `$lookup` và accumulators.

Một số stages có thể spill ra disk trong điều kiện server cho phép. Không khẳng định mọi stage hoặc mọi accumulator đều spill được.

### 10.2. Server version và default

Từ MongoDB 6.0, `allowDiskUseByDefault` liên quan việc các stages có thể dùng disk theo default. Per-command `allowDiskUse` override phù hợp với supported semantics. MongoDB versions mới hơn có thể bổ sung giới hạn bộ nhớ **theo operation**; kiểm tra release docs.

### 10.3. Ví dụ

~~~javascript
db.sales.aggregate([
  {
    $match: {
      tenant_id: "tenant-a",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$customer_id",
      total_minor: { $sum: "$amount_minor" },
      count: { $sum: 1 }
    }
  },
  { $sort: { total_minor: -1 } },
  { $limit: 100 }
], {
  allowDiskUse: true,
  maxTimeMS: 30000
});
~~~

### 10.4. Khi nào `allowDiskUse` không giúp?

- BSON output >16 MiB.
- `$facet` internal cap.
- Một accumulator array quá lớn không thể spill.
- Pipeline >1.000 stages.
- Client OOM do gom toàn cursor vào List.
- Một join fan-out không được giới hạn.
- Hardware disk I/O không đủ.

### 10.5. Spill có giá

Tăng temp disk I/O, latency và cạnh tranh tài nguyên. Theo dõi profiler/log `usedDisk` khi hỗ trợ; cân nhắc query plan/index/limit thay vì bật spill vô điều kiện.

### 10.6. Không sửa internal parameters bừa

Tăng memory limit có thể khiến một operation chiếm quá nhiều RAM dưới concurrency. Managed Atlas có thể không cho thay. Ghi approval, benchmark và rollback plan trước khi thay cấu hình được hỗ trợ.

---

## 11. `$sort`: index, limit và memory

### 11.1. Query không giới hạn

~~~javascript
db.events.aggregate([
  { $sort: { created_at: -1 } }
], {
  allowDiskUse: false
});
~~~

Với dữ liệu lớn và không có index phục vụ sort, có thể gặp memory error.

### 11.2. Query có scope và top-k

~~~javascript
db.events.createIndex({
  tenant_id: 1,
  created_at: -1,
  _id: -1
});

db.events.aggregate([
  { $match: { tenant_id: "tenant-a" } },
  { $sort: { created_at: -1, _id: -1 } },
  { $limit: 50 },
  { $project: { _id: 1, type: 1, created_at: 1 } }
]);
~~~

`$sort` rồi `$limit` khác `$limit` rồi `$sort`. Không di chuyển limit bừa khiến kết quả sai nghiệp vụ.

### 11.3. Explain

~~~javascript
db.events.explain("executionStats").aggregate([
  { $match: { tenant_id: "tenant-a" } },
  { $sort: { created_at: -1, _id: -1 } },
  { $limit: 50 }
]);
~~~

Xác nhận `IXSCAN`/sort behavior bằng plan thực tế. Index có tồn tại không có nghĩa query chắc sử dụng nó.

---

## 12. `$group` và accumulator memory

### 12.1. Pipeline nguy hiểm

~~~javascript
db.order_events.aggregate([
  {
    $group: {
      _id: "$order_id",
      events: { $push: "$$ROOT" }
    }
  }
], {
  allowDiskUse: true
});
~~~

Một order nhiều sự kiện có thể làm `events` array vượt accumulator memory hoặc output 16 MiB. Spill của group state không làm một accumulator unlimited.

### 12.2. Nếu chỉ cần tổng

~~~javascript
db.order_events.aggregate([
  {
    $group: {
      _id: "$order_id",
      event_count: { $sum: 1 }
    }
  }
]);
~~~

### 12.3. Nếu cần lịch sử

Trả events bằng cursor/pagination theo `order_id` thay vì gom tất cả vào một result document.

### 12.4. Nếu cần top N per group

Kiểm tra version hỗ trợ các accumulator top-N hoặc dùng window functions/queries thích hợp; vẫn phải giới hạn N và test memory. Không coi top-N là miễn mọi giới hạn.

---

## 13. Write batches, network protocol và driver splitting

### 13.1. Ba giới hạn khác nhau

- `maxBsonObjectSize`: per-document.
- `maxMessageSizeBytes`: kích thước message ở protocol.
- `maxWriteBatchSize`: số write operations tối đa trong batch theo server capability.

Tra thực tế:

~~~javascript
const hello = db.adminCommand({ hello: 1 });

printjson({
  maxBsonObjectSize: hello.maxBsonObjectSize,
  maxMessageSizeBytes: hello.maxMessageSizeBytes,
  maxWriteBatchSize: hello.maxWriteBatchSize
});
~~~

### 13.2. Driver tự chia batch vẫn có giới hạn ứng dụng

Java Driver có thể chia bulk writes theo giới hạn server. Nhưng application không nên tích lũy 10 triệu write models trong heap rồi mới `execute`. Tự chia input chunks hữu hạn, checkpoint và kiểm soát throughput.

### 13.3. Ordered vs unordered

`ORDERED` dừng theo semantics khi operation lỗi, `UNORDERED` có thể tiếp tục các operations độc lập. **Cả hai không tự all-or-nothing transaction**.

### 13.4. Không chọn batch size chỉ theo protocol max

Batch 100.000 operations có thể hợp lệ theo một capability nhưng quá lớn cho SLO, heap, retry/reconciliation hoặc MongoDB transaction budget. Dùng benchmark thực tế và quota của môi trường.

### 13.5. Unknown write outcome

Network timeout không chứng minh write fail. Với `$inc`/`$push`, retry application-level không có stable idempotency key có thể lặp effect; yêu cầu unique operation ID/ledger.

---

## 14. Cursor, batchSize, pagination và client memory

### 14.1. Cursor trả nhiều documents, từng document chịu 16 MiB

`batchSize` ảnh hưởng number/size của batches theo driver/server rules, không cho phép một BSON document 20 MiB. `limit` là limit tổng kết quả, không tự set max server memory.

### 14.2. Không collect vô hạn trong JVM

~~~java
// Nguy hiểm trên collection lớn:
List<Document> all =
    collection.find().into(new ArrayList<>());
~~~

Duyệt cursor theo batch và xử lý streaming:

~~~java
try (MongoCursor<Document> cursor =
         collection.find()
             .batchSize(200)
             .iterator()) {

    while (cursor.hasNext()) {
        Document doc = cursor.next();
        processOne(doc);
    }
}
~~~

Đoạn Java minh họa; `processOne` là application function. Client memory, GC, max heap, timeout và downstream backpressure là giới hạn ngoài MongoDB Server.

### 14.3. Pagination bằng keyset

Với collection rất lớn, `skip(1000000)` có thể đắt. Dùng stable sort key và cursor token, ví dụ `created_at DESC, _id DESC` có index tương ứng, truyền last value cùng tenant/filter scope.

### 14.4. Cursor lifetime

Có `noCursorTimeout`, logical session timeout và server resource policies. Không giả định một cursor mở nhiều giờ luôn sống. Đóng cursor khi xong và checkpoint đủ để restart/re-query.

### 14.5. Change streams cũng là cursor-like stream

Batch/await/resume token không thay yêu cầu backpressure, retention và checkpoint durable.

---

## 15. Transactions: điều kiện hỗ trợ và giới hạn thực tế

Multi-document transaction phải được xem theo:

1. Replica set hay sharded cluster.
2. Server version và FCV.
3. Driver version và session support.
4. Default/custom `transactionLifetimeLimitSeconds`.
5. Write concern/read concern, retryable transaction errors.
6. Tổng data/read/write set, số documents/collections tham gia.
7. Lock contention và WiredTiger cache pressure.
8. Transaction oplog representation theo server version.
9. Cross-shard coordination cost.
10. Managed-tier restrictions và timeouts.

### 15.1. Default lifetime không phải budget muốn bao nhiêu cũng được

Nhiều MongoDB versions có default transaction lifetime khoảng **60 giây**; giá trị cấu hình và restrictions theo environment phải xác nhận. Thiết kế transaction ngắn, không giữ mở khi chờ payment provider/email.

### 15.2. Kiểm tra tham số khi được quyền

~~~javascript
db.adminCommand({
  getParameter: 1,
  transactionLifetimeLimitSeconds: 1
});
~~~

Nếu Atlas tier không cho đọc/sửa parameter, tra UI/API/support docs và xác nhận với platform owner.

### 15.3. Không nói “transaction tối đa 16 MiB tổng”

MongoDB từng thay đổi cách ghi oplog của transactions. Không áp một giới hạn legacy về tổng transaction size cho mọi server mới. **Mỗi persisted BSON document** vẫn phải phù hợp hard limit, còn transaction chịu những resource constraints khác.

### 15.4. Unknown commit result

Một commit có thể thành công nhưng client mất ACK. Retry commit hoặc reconcile bằng stable business ID. Không tự charge payment/gửi message trong transaction callback có thể retry.

### 15.5. Transactions không atomic với external systems

MongoDB transaction không bao gồm Kafka, email, payment gateway hoặc HTTP service bên ngoài. Dùng transactional outbox, idempotent consumers và saga/compensation theo nghiệp vụ.

---

## 16. Sessions, retryable writes và connection pools

### 16.1. Sessions

Logical sessions có lifetime và cleanup rules; không cache `ClientSession` vô thời hạn hoặc dùng session đồng thời không phù hợp driver contract. Kiểm tra `logicalSessionTimeoutMinutes` khi được trả về qua `hello`.

### 16.2. Retryable writes

Cần topology/version/driver hỗ trợ, retry policy và wire protocol tương ứng. Một HTTP replay mới không nhất thiết dùng lại database operation identity; business idempotency vẫn cần.

### 16.3. Connection pool là giới hạn client và server

Java Driver có `maxSize`, `minSize`, `maxConnecting`, `maxWaitTime`, socket/connect/server selection timeouts. Tên và default cụ thể tùy driver version.

### 16.4. Server connections và Atlas quota

Server có limits từ config, system file descriptors và managed tier; Atlas quota có thể nhỏ hơn capacity lý thuyết. Đừng tính số connections bằng “số users”; tính số app instances × pool max × số server addresses/nodes có thể kết nối cộng monitoring/jobs.

### 16.5. Triệu chứng pool exhaustion

Threads chờ connection, `MongoWaitQueueTimeoutException` hoặc timeout tương tự, p99 tăng. Tăng pool size khi server đã cạn sockets có thể làm sự cố nặng hơn.

### 16.6. Verify

Đối chiếu driver configuration, `db.serverStatus().connections` (nếu được quyền), Atlas connection metrics, OS file descriptors, `ulimit`/Windows limits và process count. Không suy một giới hạn cứng chung.

---

## 17. Replica set: giới hạn topology và replication

Cần xác minh theo server release:

- Maximum replica set members.
- Số voting members được hỗ trợ và election rules.
- Oplog size/retention window.
- Read/write concern defaults.
- Majority availability và failover behavior.
- Member priority, hidden/delayed/arbiter restrictions.
- Sync sources và network bandwidth.
- Logical sessions support.
- Transaction/change stream support.
- Upgrade compatibility giữa các members.

### 17.1. Members và voters không cùng một con số

MongoDB docs nhiều đời phân biệt số members tối đa và số voting members; không lấy mức max members làm mức max voters. Nếu thiết kế replica set nhiều nodes, tra [Replica Set Limits](https://www.mongodb.com/docs/manual/reference/limits/#replica-set-limits) đúng version.

### 17.2. Oplog là resource hữu hạn

Change stream resume và replication phụ thuộc lịch sử oplog còn được giữ. Oplog size, throughput, oplog retention policy và disk capacity quyết định khoảng thời gian thực tế; không có “resume được đúng 7 ngày” phổ quát.

### 17.3. Lag là một giới hạn vận hành

Replica secondary lag làm read stale, ảnh hưởng failover/RPO, backup và change stream. Đo lag/optime/health, không chỉ CPU của primary.

### 17.4. Failover chưa chắc nhanh tùy ý

Election timeout, topology/network và driver server selection timeout ảnh hưởng latency khi primary thay đổi. Test stepdown trên staging; không cam kết 0 downtime cho mọi deployment.

---

## 18. Sharded cluster: shard key, chunks và quotas

Các mục phải kiểm tra:

- Server/FCV của mongos, config server và shards.
- Shard key restrictions, hashed vs ranged keys.
- Unique indexes trên sharded collections.
- Chunk size/balancer behavior theo version.
- Jumbo chunks, hot shards, zone sharding.
- Max number of shards/namespaces theo release và managed tier.
- Cross-shard transactions/aggregations.
- Chunk migrations, disk/IO pressure và backup consistency.
- Shard key updates/resharding support.
- Query targeting vs scatter-gather.
- Limits của Atlas auto-scaling/shard scaling.

### 18.1. Sharding không tăng 16 MiB per document

Một document 20 MiB vẫn không hợp lệ dù có 100 shards. Cần split một document thành nhiều referenced documents/buckets.

### 18.2. Một hot key vẫn là hotspot

Nếu tất cả requests giảm stock của SKU-01 trong một document, sharding không tự biến atomic counter đó thành nhiều independent counters.

### 18.3. Shard key và transaction

Thiết kế tenant+key giúp target queries có thể giảm scatter-gather, nhưng cần kiểm tra shard key thực tế, unique index rules và read/write workloads.

### 18.4. Chunk size không phải document size

Chunk là đơn vị dữ liệu phân vùng/chuyển giữa shards, không phải một BSON object. Không dùng chunk size để suy một document có thể lớn bằng chunk.

---

## 19. Change Streams: retention, pre-images và resume

### 19.1. Deployment support

Change Streams được dùng trên replica sets/sharded clusters với server version phù hợp. Standalone không phải deployment thông thường cho change streams. Driver API và permissions cần được xác nhận.

### 19.2. Không có “resume token hiệu lực mãi mãi”

Resume token là opaque marker. Nếu oplog history chứa vị trí đó không còn, consumer có thể gặp lỗi không resume được và cần re-bootstrap/reconciliation.

### 19.3. Dung lượng event

Change event có thể lớn khi dùng `fullDocument` update lookup và especially pre/post-images. Kích thước event, pipeline transformations và message transport đều có giới hạn. Không coi full document change events luôn nhỏ vì update chỉ thay một field.

### 19.4. Pre/post images

Có lifecycle/retention/storage policies theo server/version và cấu hình collection. Pre/post-images không phải backup vô hạn; phải xác nhận retention và quota.

### 19.5. Backpressure

`batchSize` và `maxAwaitTimeMS` thay cách đợi/đọc batches, không tăng oplog history. Khi arrival rate > processing rate, lag tăng; thêm concurrency phải giữ ordering/checkpoint correctness.

### 19.6. Checkpoint và idempotency

Lưu resume token bền vững sau xử lý đúng; consumer có thể nhận duplicate sau crash. Dùng stable event ID/version và idempotent side effects.

### 19.7. Theo dõi

Oplog time window, consumer lag, resume failures, pre-image storage, throughput và error rate. Nếu history lost, không restart từ “now” rồi tuyên bố không mất sự kiện.

---

## 20. TTL indexes và retention không chính xác từng giây

### 20.1. TTL có giới hạn/rules riêng

Kiểm tra:

- Field phải thuộc kiểu thời gian hợp lệ.
- `expireAfterSeconds` semantics.
- Restrictions theo single-field/compound/partial/time-series versions.
- TTL monitor cadence và deletion lag.
- Impact lên writes/replication/CPU.
- Managed backup/retention requirements.

### 20.2. TTL không làm nghiệp vụ bù trừ

Xóa reservation ACTIVE bằng TTL không tự trả lại inventory. Cần expiration worker thực hiện state transition và conditional inventory adjustment trước khi cleanup marker.

### 20.3. TTL không phải scheduling SLA chính xác

TTL deletion chạy background; document có thể tồn tại một khoảng sau deadline. Không dùng sự vắng mặt của document làm bằng chứng rằng job đã đúng giờ.

### 20.4. Retention vs idempotency

Nếu xóa processed-event marker trước khi delayed queue replay, duplicate effect có thể xảy ra. Thiết kế TTL theo replay window và audit/legal obligations.

### 20.5. Đừng nhầm TTL với backup

Dữ liệu bị TTL delete không mặc nhiên còn phục hồi được theo mức retention mong muốn. RPO/RTO dựa vào backup policy riêng.

---

## 21. Time-series collections: giới hạn khác collection thường

Time-series có cơ chế bucketing và restrictions theo MongoDB release.

Danh mục cần kiểm tra:

1. Server version/FCV hỗ trợ feature đang dùng.
2. `timeField` và optional `metaField` shape.
3. `granularity` và bucket span/rounding rules.
4. Retention/TTL.
5. Allowed updates/deletes.
6. Indexes và secondary indexes hỗ trợ.
7. Sharding support/restrictions.
8. Limits/behavior của bucketing và bucket size.
9. Query optimization với metadata/time bounds.
10. Downsampling, late-arriving measurements và backfill.

### 21.1. Không dùng time-series như arbitrary mutable document collection

Một số update/delete/transaction/sharding behaviors khác collections thường, và tính năng hỗ trợ thay đổi giữa releases. Xem versioned time-series docs trước khi dùng cho inventory/reservation state.

### 21.2. Measurements quá lớn

BSON document limit vẫn liên quan; time-series không tự biến một payload measurement cực lớn thành hợp lệ. Mô hình measurements nhỏ, time-bound và metadata phù hợp.

### 21.3. Bucket size khác TTL retention

Bucket size là storage/layout; retention là lifecycle. Không chọn granularity chỉ vì cần xóa sau 30 ngày mà không xét query/workload.

---

## 22. GridFS: giới hạn file khác BSON document

GridFS tách file thành file metadata và các chunks. Phù hợp với file-like binary lớn hơn 16 MiB khi muốn lưu trong MongoDB; không phải cách chữa mọi unbounded array.

### 22.1. Điều phải kiểm tra

- Driver/GridFS API và version.
- Chunk size/collection indexes.
- Storage/backup/restore quota.
- File metadata và tenant ACLs.
- Incomplete uploads và cleanup.
- Retention/lifecycle.
- Read range/streaming performance.
- Atlas tier disk/storage limits.

### 22.2. Khi nào không nên GridFS?

Nếu dữ liệu là hàng triệu events cần filter, sort, dedup theo `event_id`, collection events riêng với indexes tốt hơn một file blob chứa JSON khổng lồ.

### 22.3. External object storage

Có thể chọn S3/GCS/Azure Blob cho files, lưu metadata/pointer trong MongoDB. Khi đó cần consistency/retention/ACL giữa hai systems, không giả định MongoDB transaction atomic với object storage.

---

## 23. Atlas: quotas phải tra theo sản phẩm/tier

MongoDB Atlas có nhiều loại triển khai, mỗi loại với availability, performance, backup/network và feature constraints khác nhau.

### 23.1. Không hard-code giới hạn một tier mãi mãi

Quotas có thể thay đổi khi Atlas cập nhật sản phẩm/tên plan. Một tài liệu cũ về M0/M2/M5 có thể không còn mô tả đầy đủ Flex/dedicated hoặc phiên bản mới. Ghi **tên tier hiện tại từ Atlas UI/API**.

### 23.2. Những mục kiểm tra bắt buộc

| Nhóm | Câu hỏi cần trả lời |
|---|---|
| Storage | Max allocated storage? Auto-scaling? Disk IOPS/throughput? |
| Connections | Max concurrent connections/tier và connection spikes? |
| Compute | CPU/RAM, class, Search nodes? |
| Backup | Snapshot frequency, retention, PITR, restore RPO/RTO? |
| Networking | Private endpoint/peering, public IP allowlist, egress policies? |
| Features | Transactions, sharding, Search, Vector Search, encryption, time series? |
| Operations | Index build/resource limits, maintenance/upgrade windows? |
| Quotas | Số clusters/projects, API limits, alerts? |
| Region/cloud | Regions supported, zones, instance size availability? |
| Scaling | Min/max tier, auto-scaling guardrails, storage scale policies? |
| Security | Auditing/advanced auth/encryption tiers? |
| Support | Service level và escalation path? |

### 23.3. Atlas Search/Vector Search khác mongod aggregation

Search index quotas, analyzers, vector dimension ceilings, query syntax, field mappings, Search nodes, index size và concurrent query limits có bảng riêng. Không lấy limits của MongoDB B-tree indexes để suy Search index capacity.

### 23.4. Atlas serverless/managed feature names thay đổi

Dùng [Atlas documentation](https://www.mongodb.com/docs/atlas/) hiện hành theo đúng cluster type và plan, không copy bảng limitations từ một blog không có ngày phát hành.

### 23.5. Tài khoản của bạn có thể không thấy mọi parameter

Cần dùng Atlas metrics/UI/API và platform team. Không tìm cách đọc những server internal parameters bằng bypass quyền.

---

## 24. Self-managed: limits từ hệ điều hành và hardware

MongoDB Server hỗ trợ một workload không có nghĩa host có tài nguyên.

### 24.1. Linux/Windows

Kiểm tra file descriptors/handles, max processes/threads, memory limits, disk space, filesystem, DNS, network sockets, TCP behavior, service supervisor và container limits.

### 24.2. Container/Kubernetes

- CPU limits/throttling.
- Memory limit và OOMKills.
- Ephemeral storage.
- Persistent volume IOPS/throughput/capacity.
- Pod eviction và node failure.
- Resource requests/limits.
- Probes và rolling upgrade.
- Multi-availability-zone networking.

### 24.3. WiredTiger cache

WiredTiger dùng cache và memory ngoài cache. Kích thước default/tuning phụ thuộc build/environment; không tính “MongoDB RAM = cache size” rồi bỏ qua OS page cache, connections, aggregation hoặc concurrent queries.

### 24.4. Disk capacity

Không chỉ data size: cộng indexes, journal, oplog, temporary aggregation/index build space, snapshots và headroom. Storage engine compression làm `logical data size` khác `allocated disk usage`.

### 24.5. Virtualization/cloud

IOPS/throughput/network bandwidth và burst credits có thể là nút thắt trước CPU. Bảng limit của MongoDB không thay benchmark host thực tế.

---

## 25. Backup, restore và data retention

Những thứ cần xác minh:

- Backup/PITR availability theo tier.
- Snapshot interval và retention.
- RPO/RTO kỳ vọng.
- Backup consistency trong sharded/replica topology.
- Disk/network capacity để restore.
- Encryption key management.
- Version compatibility restore.
- Backup của Search indexes/derived projections.
- TTL deletion và legal hold.
- Restore rehearsal và xác nhận ứng dụng đọc được schema cũ.

### 25.1. Backup không thay idempotency

Restore có thể tạo lại trạng thái từ thời điểm trước transaction nhưng làm mất những writes hợp lệ sau đó. Khi khôi phục cần kế hoạch replay/reconcile từ source of truth/outbox.

### 25.2. Version compatibility

Không giả định một backup snapshot từ server version mới có thể restore trực tiếp bằng binary rất cũ. Kiểm tra supported upgrade/downgrade paths và FCV.

### 25.3. Restore time là giới hạn thực tế

Một cluster rất lớn có snapshot backup nhưng mất nhiều giờ restore có thể không đạt RTO. Test restore với data size và network thực.

---

## 26. Bảo mật và encryption có giới hạn riêng

### 26.1. TLS/authentication

Kiểm tra driver support, TLS versions, cert chain, auth mechanism, identity provider/session settings và Atlas security policies. Không hạ bảo mật chỉ để “kết nối được” sau upgrade.

### 26.2. Client-Side Field Level Encryption

CSFLE và Queryable Encryption có requirements/restrictions về supported types, operators, encrypted indexes, driver versions, key management và payload expansion. Không mặc định encrypted field có thể dùng trong mọi `$regex`, `$sort` hoặc `$lookup` như plaintext.

### 26.3. Encrypted data expansion

Encryption metadata có thể tăng BSON size. Một document plaintext sát 16 MiB có thể vượt giới hạn khi mã hóa. Đặt headroom và kiểm tra data thật.

### 26.4. Search và encryption

Search trên dữ liệu encrypted có restrictions/chế độ hỗ trợ riêng; không suy Atlas Search có thể index mọi field client-side encrypted.

### 26.5. Key lifecycle

Key rotation/availability và restore là operational constraints. Một backup có dữ liệu encrypted nhưng không có keys cần thiết không giúp khôi phục đầy đủ.

---

## 27. Driver, Spring Data và API compatibility

### 27.1. MongoDB Java Sync Driver

Tra matrix của driver version so với MongoDB Server versions, Java runtime requirements, retryable writes, transactions, compression, authentication mechanisms và codec behavior.

### 27.2. Spring Data MongoDB

Spring Data/BOM/Boot version quyết định API mapping, `MongoTemplate`, `BulkOperations`, session/transaction integration, reactive features và feature flags. Không dùng code snippet phiên bản mới với dependency cũ mà không kiểm tra.

### 27.3. Không trộn blocking và reactive mà không đo

Reactive driver có connection/backpressure semantics khác synchronous driver. Cùng server quota nhưng client concurrency/memory patterns khác.

### 27.4. Driver socket và timeout

Các nhóm cần tra:

- `serverSelectionTimeout`.
- `connectTimeout`.
- `socketTimeout` hoặc read timeout.
- `maxPoolSize`, `minPoolSize`.
- `maxConnecting`, `maxWaitTime`.
- `retryReads`/`retryWrites`.
- Heartbeat and topology discovery.

Default thay theo driver version. Ghi effective runtime config, không suy từ sample code.

### 27.5. Client-side BSON codec

Client có thể không serialize được object lớn/unsupported type, hoặc Java heap OOM trước khi server nhận request. Phân biệt driver error với server limit.

---

## 28. Cách đọc `stats` đúng

~~~javascript
db.orders.stats();
~~~

Thường thấy `count`, `size`, `avgObjSize`, `storageSize` và index sizes, tùy version/engine/topology.

### 28.1. `avgObjSize` che tail

Một collection có average document size 3 KiB vẫn có thể có vài documents 15 MiB. Phải đo top-N/p95/p99 với `$bsonSize` hoặc telemetry.

### 28.2. Logical size khác disk size

`size` và `storageSize` khác nhau do compression/fragmentation/allocation. Không tính max document từ `storageSize/count`.

### 28.3. Index stats

`$indexStats` hoặc server metrics giúp hiểu index usage, nhưng “usage=0 trong 24 giờ” không đủ để drop index phục vụ job cuối tuần. Có workload inventory.

### 28.4. Sharded collection

Stats có thể tổng hợp/hiển thị theo shard, không chứng minh distribution đều. Cần xem hot shards/zone placement và query routing.

---

## 29. Mẫu bảng đăng ký giới hạn (Limit Register)

Một team nên duy trì bảng có tính truy xuất:

| ID | Thành phần | Limit/constraint | Nguồn giá trị | Evidence | Owner | Checked at |
|---|---|---|---|---|---|---|
| LIM-001 | BSON | maxBsonObjectSize | `hello` + manual | command output | DBA | Ngày kiểm tra |
| LIM-002 | Aggregation | Spill/`allowDiskUse` | server settings + docs | profiler/explain | Data team | Ngày kiểm tra |
| LIM-003 | Transaction | Lifetime/config | `getParameter`/Atlas docs | config snapshot | Platform | Ngày kiểm tra |
| LIM-004 | Connections | Client pool + Atlas tier | driver config + Atlas | dashboard | Backend/SRE | Ngày kiểm tra |
| LIM-005 | Change Stream | Oplog retention | replica metrics | lag chart | SRE | Ngày kiểm tra |
| LIM-006 | Search | Search index/vector restrictions | Atlas docs/tier | UI/API | Search team | Ngày kiểm tra |
| LIM-007 | Disk | IOPS/storage headroom | Cloud/OS metrics | dashboard | SRE | Ngày kiểm tra |

### 29.1. Trường nên lưu cho từng limit

~~~yaml
id: LIM-003
component: mongodb-transaction
environment: staging
server_version: "<captured-version>"
fcv: "<captured-fcv>"
topology: replica-set
tier: "<atlas-tier-or-self-managed>"
client: "<driver-and-version>"
property: transactionLifetimeLimitSeconds
effective_value: "<observed-value>"
unit: seconds
classification: configurable
reference: "<versioned-document-url>"
observed_at: "<ISO-8601 timestamp>"
verified_by: "<owner-or-team>"
action_threshold: "<application-policy>"
notes: "<what-to-watch>"
~~~

Đây là **template ghi nhận**, không phải dữ liệu thật của một cluster. Đừng điền version/tier giả rồi coi đó là evidence.

### 29.2. Bản ghi hết hạn

Với các limits thay đổi theo tier và service docs, đặt review date. Khi upgrade driver, thay tier, resharding hoặc nâng FCV, phải cập nhật limit register.

### 29.3. Có nguồn chứng cứ thực

Một dòng “limit=500” thiếu version, cluster, docs và thời điểm sẽ khó dùng trong incident. Gắn screenshot/command output đã redact hoặc link tới dashboard có quyền.

---

## 30. Quy trình kiểm tra limit trước production rollout

### Bước 1 — Nhận diện thay đổi

Ví dụ ứng dụng chuyển từ order embedded items sang 100.000 events, thêm aggregation `$lookup` và tăng pool connections.

### Bước 2 — Mapping sang nhóm limit

- Document 16 MiB/array growth.
- Index multikey restrictions.
- Aggregation output/memory.
- Client heap/cursor.
- Connection pool + Atlas quota.
- Change stream lag nếu có CDC.

### Bước 3 — Chụp môi trường

Server versions, FCV, topology, tier, driver, deployment config và workload size.

### Bước 4 — Tra versioned docs

Dùng manual của đúng server release, Atlas tier docs, driver compatibility matrix. Ghi URL/ngày.

### Bước 5 — Đo trên cluster

`hello`, stats, index list, explain, profiler/metrics, resource quotas. Nếu thiếu quyền, yêu cầu platform owner cung cấp evidence.

### Bước 6 — Tính headroom

Không deploy khi document trung bình 15.9 MiB chỉ vì hard cap là 16 MiB. Tính tốc độ tăng, high-percentile, peak concurrency và safety margin.

### Bước 7 — Staging load/fault tests

Dữ liệu/cardinality tương đương production, test top tenants, hot SKU, network failures, primary stepdown, disk pressure và timeout.

### Bước 8 — Set guardrails

Max event payload, max array count, batch size, maxTimeMS, pool settings, concurrency limit, alerts, rate limiting và retry policies.

### Bước 9 — Rollout có canary

Theo dõi latency/errors/memory/spill/replica lag, dừng hoặc rollback nếu vượt ngưỡng nội bộ.

### Bước 10 — Cập nhật register

Ghi effective values và bài học sau rollout. Tài liệu phải đủ để đội on-call xác định limit nào đã kiểm chứng.

---

## 31. Runbook: `BSONObjectTooLarge` hoặc document vượt 16 MiB

1. Xác nhận error class/message; phân biệt insert/update và aggregation output.
2. Ghi server/driver versions và `hello.maxBsonObjectSize` nếu được phép.
3. Xác định document ID/tenant; không dump raw PII vào log.
4. Đo `$bsonSize:"$$ROOT"` và array counts trên dữ liệu nghi ngờ.
5. Xác định field/unbounded array lớn: events, comments, attachments, snapshots.
6. Dừng retry storm/`$push` tiếp tục làm document tăng.
7. Chọn bounded recent array, referenced collection, bucket hoặc GridFS theo business.
8. Backfill có stable IDs/checkpoint/idempotency.
9. Drain old writers và reconcile trước khi xóa embedded history.
10. Đặt cảnh báo kích thước thấp hơn trần và cập nhật data model.

**Không** tăng `batchSize`/`allowDiskUse` để chữa một document vượt 16 MiB; những tùy chọn này không sửa hard document limit.

---

## 32. Runbook: aggregation vượt memory hoặc output

### 32.1. Phân loại

- Một result document >16 MiB?
- Stage `$sort` hoặc `$group` vượt memory?
- `$group` accumulator `$push` quá lớn?
- `$facet` intermediate >100 MB?
- `$lookup` fan-out?
- Pipeline >1.000 stages?
- Driver/client OOM thay vì mongod error?
- Timeout do index/IOPS thiếu?

### 32.2. Dùng explain và profiler có kiểm soát

Không bật profiler full-time mức cao trên production mà không xét overhead/PII. Thu evidence theo request/pipeline IDs và query shapes.

### 32.3. Sửa phù hợp

- `$match` sớm.
- Index filter/sort/join.
- `$project` nhỏ trước stage nặng khi đúng semantics.
- `$sort` + `$limit` đúng thứ tự.
- Tránh `$push:"$$ROOT"` nếu chỉ cần count/sum.
- Giới hạn `$lookup` foreign pipeline.
- Phân trang raw history.
- Dùng materialized summary/`$merge` với documents nhỏ.
- Bật spill khi stage hỗ trợ và disk budget đủ.

### 32.4. Không tăng memory mù

Nếu chỉ chuyển một query từ RAM sang disk, nhiều concurrent queries có thể làm disk cạn và đẩy cluster vào sự cố khác. Benchmark và đo usedDisk/IOPS/p99.

---

## 33. Runbook: quá tải connections hoặc timeout

1. Phân biệt server selection timeout, connect timeout, pool wait timeout, socket timeout và maxTimeMS.
2. Chụp driver version/pool config/instance count.
3. Đọc Atlas connection metrics hoặc `serverStatus.connections` nếu được phép.
4. Kiểm tra sockets/file descriptors/OS/container resource.
5. Đếm service replicas × connections per node và background workers.
6. Xác định connection leaks, unclosed cursors/sessions, retry storms.
7. Giảm concurrency/resolve slow queries; không chỉ tăng pool size.
8. Nếu capacity thật thiếu, scale tier/nodes theo quota được phép.
9. Test failover và reconnect behavior; theo dõi p99, connection count, errors.
10. Cập nhật register với observed limit/threshold.

### 33.1. Một con số pool max không là số connections toàn cluster

Mỗi service instance có thể kết nối đến nhiều server addresses, driver có monitoring connections và topology-dependent behavior. Đo actual connections thay vì ước lượng sơ sài.

---

## 34. Runbook: Change Stream không resume được

1. Ghi server version/FCV/topology, driver và exception.
2. Kiểm tra resume token validity/retention theo oplog history.
3. Đo lag của consumer, write/arrival rate và backlog.
4. Phân loại transient error hay history lost.
5. Không bỏ token và watch từ “now” khi chưa đánh giá mất dữ liệu.
6. Nếu history lost, bootstrap/reconcile từ source snapshot và xác định cutover point.
7. Dùng idempotent processing và durable checkpoint sau successful effect.
8. Điều chỉnh concurrency/backpressure/oplog budget nếu cần.
9. Kiểm tra pre/post-images retention nếu pipeline dựa vào chúng.
10. Lập alert khi lag tiến gần oplog window.

---

## 35. Runbook: transaction timeout hoặc write conflicts

1. Phân loại transaction lifetime limit, lock/write conflict, unknown commit, network error.
2. Kiểm tra `transactionLifetimeLimitSeconds`/Atlas tier/quota.
3. Đo transaction duration, number of documents/collections, retry count.
4. Kiểm tra có HTTP/external I/O bên trong transaction không.
5. Thu hẹp read/write set và transaction duration.
6. Sắp thứ tự touched stock buckets ổn định khi phù hợp.
7. Chỉ retry theo driver contract, cùng business operation ID.
8. Unknown commit → retry commit/reconcile durable marker.
9. Không chạy retry callback với external non-idempotent side effects.
10. Đo p95/p99, conflicts và primary resource headroom.

---

## 36. Kiểm tra giới hạn bằng lệnh và đối chiếu

Bảng thao tác mongosh:

| Mục | Lệnh/hướng kiểm tra | Điều cần ghi |
|---|---|---|
| Server version | `db.version()`, `buildInfo` | Major/minor/patch, edition |
| FCV | `getParameter featureCompatibilityVersion` | Effective FCV |
| Protocol BSON/message/batch | `hello` | maxBsonObjectSize, maxMessageSizeBytes, maxWriteBatchSize |
| Topology | `hello`, `replSetGetStatus`, Atlas UI | Members/shards, primary, lag |
| Index count | `db.coll.getIndexes()` | Count/types/index definitions |
| Collection sizes | `db.coll.stats()` | count, avgObjSize, indexes, storage |
| Large documents | `$bsonSize:"$$ROOT"` | Top/p95/max size |
| Query/index plan | `explain("executionStats")` | IXSCAN/COLLSCAN, examined counts |
| Memory spill | Profiler/log `usedDisk` | Spill frequency/latency |
| Transactions | `getParameter transactionLifetimeLimitSeconds` | Effective limit, restrictions |
| Connections | `serverStatus().connections`, Atlas Metrics | Active/available/total |
| Oplog | Replica metrics/oplog status | Retention window, consumer lag |
| TTL | `getIndexes` + deletion monitoring | Expiry config, actual lag |
| Search/Vector | Atlas UI/API/Search docs | Index quota, dimension/query limits |
| Backup | Atlas/self-managed backup admin | RPO/RTO/retention |
| Storage/IO | OS/Atlas/storage metrics | Disk headroom, IOPS, throughput |

### 36.1. Không mọi lệnh đều chạy được trên Atlas

Permission và product tier khác nhau. Khi bị từ chối quyền, ghi “not observable with current role”, không đoán giá trị.

### 36.2. Một giá trị ở staging không là production

Mọi nhận định phải gắn environment. Atlas M10 staging, M40 production, sharded production và local standalone có constraints khác nhau.

---

## 37. Ma trận rủi ro theo workload

| Workload | Giới hạn hay va chạm | Cách phòng ngừa |
|---|---|---|
| User profile với audit events | BSON 16 MiB, unbounded arrays | Reference events, bounded recent preview |
| Order report tất cả invoices | `$group` accumulator, result 16 MiB | Scalar summary/pagination |
| Search faceted navigation | `$facet` 100 MB, result 16 MiB | Limit arrays, selective match |
| Bulk sync ERP | Write batch, heap, partial errors | Chunks, checkpoint, idempotency |
| Inventory hot SKU | Single-document contention, transaction retries | Atomic conditional, quotas, benchmark |
| Feed/social timeline | Array growth, pagination | Separate posts/events, indexed keyset |
| Time-series telemetry | Bucket/index/TTL/version restrictions | Metadata/time modeling và retention |
| CDC to Kafka | Oplog retention, resume lag | Backpressure, durable checkpoints |
| Vector similarity search | Atlas Search/vector index quota | Tier/version/dimension/index planning |
| Multi-SKU checkout | Transaction lifetime/contention | Short transactions, stable IDs |
| Large attachments | BSON 16 MiB | GridFS/object storage |
| Many microservices | Connection/server quota | Pool sizing, per-service budgeting |
| Multi-region reads | Lag, network latency | Read preference/consistency policy |
| Regulatory audit | TTL/backup/retention | Legal hold, immutable event log |

### 37.1. Giới hạn chạm sớm nhất mới là nút thắt thực

Một hệ thống có thể bị hạn chế bởi gateway HTTP response size hoặc JVM heap trước khi chạm MongoDB 16 MiB. Luôn xác định **tầng phát lỗi**.

---

## 38. Những hiểu lầm cần loại bỏ

**Hiểu lầm 1:** “MongoDB chỉ lưu tối đa 16 MiB tổng dữ liệu.”  
Không. 16 MiB áp cho một BSON document.

**Hiểu lầm 2:** “Một cursor trả tối đa 16 MiB tất cả documents.”  
Không; cursor có nhiều batches, mỗi document vẫn có limit.

**Hiểu lầm 3:** “Bật allowDiskUse cho phép result document 50 MiB.”  
Không; result BSON limit vẫn áp dụng.

**Hiểu lầm 4:** “`$facet` có thể spill như `$sort`.”  
Không; facet có giới hạn riêng.

**Hiểu lầm 5:** “`$group` có thể spill nên `$push` một triệu records là an toàn.”  
Không; accumulator array và final BSON size vẫn hạn chế.

**Hiểu lầm 6:** “Max write batch size là số nên dùng cho mọi batch.”  
Không; là protocol maximum, không phải application recommendation.

**Hiểu lầm 7:** “BSON 16 MiB tính bằng số ký tự JSON.”  
Không; dùng bytes BSON.

**Hiểu lầm 8:** “Một câu lệnh MongoDB đúng cú pháp sẽ chạy trên mọi Atlas tier.”  
Không; product/tier/version restrictions khác nhau.

**Hiểu lầm 9:** “Server binary mới đã chắc có feature vì `db.version` cao.”  
Cần xét FCV/feature gates.

**Hiểu lầm 10:** “Standalone test chứng minh transactions/Change Streams production.”  
Không; phải test topology hỗ trợ.

**Hiểu lầm 11:** “Index càng nhiều càng nhanh.”  
Write amplification, storage và index limits có giá.

**Hiểu lầm 12:** “Unique index cùng quy tắc trên mọi sharded collection.”  
Có restrictions với shard key và release.

**Hiểu lầm 13:** “TTL xóa đúng giây deadline.”  
TTL background có thể trễ.

**Hiểu lầm 14:** “Oplog giữ lịch sử change stream 7 ngày mặc định ở mọi cluster.”  
Retention phụ thuộc cấu hình/write volume/topology.

**Hiểu lầm 15:** “Replication lag chỉ ảnh hưởng dashboard.”  
Nó liên quan failover, stale reads, backups và CDC.

**Hiểu lầm 16:** “Transaction lifetime 60s có thể cứ tăng cho mọi workflow.”  
Phải xét restrictions và resource budget; không gọi external API trong transaction.

**Hiểu lầm 17:** “Driver retryable write thay business idempotency.”  
HTTP/message replay vẫn có thể áp effect hai lần.

**Hiểu lầm 18:** “Có backup thì không cần diễn tập restore.”  
RTO/keys/compatibility có thể làm restore thất bại.

**Hiểu lầm 19:** “Storage size/collStats average cho biết document lớn nhất.”  
Average che tail; dùng `$bsonSize`.

**Hiểu lầm 20:** “Search index và B-tree index có cùng quota.”  
Atlas Search/Vector có rules khác.

**Hiểu lầm 21:** “Sharding làm một BSON document lớn hơn 16 MiB hợp lệ.”  
Không.

**Hiểu lầm 22:** “Tăng maxConnections giải quyết pool leak.”  
Có thể làm server cạn sockets nhanh hơn.

**Hiểu lầm 23:** “MongoDB server error và JVM OOM là một.”  
Khác tầng; cần chẩn đoán riêng.

**Hiểu lầm 24:** “Con số trên tài liệu cũ là chuẩn cho release hiện tại.”  
Phải tra versioned docs và effective runtime config.

**Hiểu lầm 25:** “Thay một parameter là không ảnh hưởng các workloads khác.”  
Memory/disk/network là tài nguyên chia sẻ; phải benchmark và có rollback.

---

## 39. Checklist khi nâng cấp MongoDB Server/FCV

- [ ] Ghi server versions của tất cả relevant nodes.
- [ ] Ghi FCV và supported upgrade/downgrade path.
- [ ] Kiểm tra driver/Spring Data compatibility matrix.
- [ ] Kiểm tra feature restrictions thay đổi.
- [ ] Kiểm tra index key/compound/multikey/unique rules.
- [ ] Kiểm tra aggregation spill/memory/stage behavior.
- [ ] Kiểm tra transaction lifetime/retry/commit semantics.
- [ ] Kiểm tra oplog/Change Streams/pre-image support.
- [ ] Kiểm tra sharding/balancer/resharding restrictions.
- [ ] Kiểm tra time-series/TTL/backup/restore support.
- [ ] Kiểm tra Atlas plan/tier-specific constraints.
- [ ] Chụp query plans, p95/p99 latency và error baseline.
- [ ] Test rolling upgrade với mixed versions nếu supported.
- [ ] Không bật feature mới khi FCV chưa phù hợp.
- [ ] Có backup và restore rehearsal.
- [ ] Ghi release notes, risk owner và rollback boundary.

---

## 40. Checklist khi đổi Atlas tier hoặc cloud region

- [ ] Tier/product name hiện hành đã xác nhận.
- [ ] Connection/storage/compute quotas được kiểm tra.
- [ ] Backup/PITR retention và restore path được xác nhận.
- [ ] Search/Vector Search nodes/index limits được kiểm tra.
- [ ] Region/cloud support và network private endpoints hợp lệ.
- [ ] Auto-scaling upper/lower bounds được cấu hình.
- [ ] Throughput/IOPS/headroom được đo.
- [ ] DNS/TLS/allowlists/roles kiểm tra.
- [ ] Application pool và retry policies phù hợp.
- [ ] Shard/replica topology và data placement được kiểm tra.
- [ ] Monitoring, alerts và on-call runbook được cập nhật.
- [ ] Cost impact và rollback/scale-down được phê duyệt.

---

## 41. Checklist cho code review liên quan giới hạn

- [ ] Không có unbounded embedded array hoặc raw event log trong một document.
- [ ] Có max bytes/count policy cho client input.
- [ ] Không gom full history vào `$push:"$$ROOT"`.
- [ ] `$lookup` có foreign index và bounded fan-out khi cần.
- [ ] `$facet` không chứa unlimited result arrays.
- [ ] `$sort` có index/top-k hoặc spill policy rõ.
- [ ] Cursor được đóng và không eagerly materialize toàn bộ data.
- [ ] Bulk input được chia chunks hữu hạn, có partial error handling.
- [ ] Transactions ngắn, không gọi external API trong retry callback.
- [ ] Requests replay có idempotency key.
- [ ] Dynamic aggregation builder giới hạn stage count.
- [ ] Time-series/Search/Vector capabilities có version/tier proof.
- [ ] Query `maxTimeMS` được đặt theo budget; không dùng như tối ưu thay index.
- [ ] Driver pool sizing được tính theo replicas và server capacity.
- [ ] Schema/index/TTL migrations có kế hoạch multi-version compatibility.
- [ ] Metrics và alerts thấp hơn hard limit để phòng sự cố.

---

## 42. Bài tập thực hành

### Bài 1 — Nhận diện môi trường

Chạy `db.version()`, `hello`, `buildInfo` và FCV query trong một lab replica set. Lập bảng server/FCV/topology.

### Bài 2 — BSON limit

Tạo documents từ vài KiB đến vài MiB trong lab, dùng `$bsonSize`. Giải thích vì sao bytes BSON khác độ dài JSON string.

### Bài 3 — Array growth

Tạo một document có `audit_events`; tăng theo batches và đo size/count. Thiết kế referenced collection khi growth vô hạn.

### Bài 4 — Nesting

Tạo nested BSON documents ở mức nhỏ; nghiên cứu giới hạn độ sâu và thiết kế schema nông hơn cho query.

### Bài 5 — Index inventory

Liệt kê `getIndexes()`; phân loại indexes hữu ích/trùng lặp, không drop index trước khi có workload evidence.

### Bài 6 — Compound multikey

Thử thiết kế compound index có hai array fields; xác định restriction theo version lab.

### Bài 7 — Unique index

Tạo partial unique index cho normalized_email; kiểm tra documents ngoài filter có được bảo vệ không.

### Bài 8 — Aggregation output

Thay `$group + $push all events` bằng `$sum` và query history theo pagination.

### Bài 9 — Sort và index

Dùng `explain("executionStats")` so sánh sort không index và sort theo indexed tenant/time.

### Bài 10 — Facet

Tạo facet page 20 + count; giải thích giới hạn 100MB nội bộ và 16 MiB output.

### Bài 11 — Dynamic stages

Sinh 1.001 `$set` stages trong test, đếm và refactor thành ít stages hơn.

### Bài 12 — allowDiskUse

So sánh behavior `$sort`/`$group` trên dataset staging với `allowDiskUse` true/false và theo dõi spill.

### Bài 13 — Batch capabilities

Đọc `hello.maxWriteBatchSize`, `maxMessageSizeBytes`, `maxBsonObjectSize` và giải thích ba con số khác nhau.

### Bài 14 — Bulk retry

Thiết kế batch 500 writes với checkpoint/idempotent upserts; xử lý partial success và unknown outcome.

### Bài 15 — Cursor memory

Trong Java, thay `into(new ArrayList<>())` bằng streaming cursor và batchSize hữu hạn.

### Bài 16 — Transaction

Trên replica set lab, tạo transaction update inventory + insert reservation; mô phỏng không đủ hàng/timeout.

### Bài 17 — Lifetime

Tra `transactionLifetimeLimitSeconds` từ server/Atlas docs; xác định vì sao payment HTTP call không đặt trong transaction.

### Bài 18 — Oplog window

Đo change stream lag và oplog retention của lab; thiết kế cảnh báo khi lag gần window.

### Bài 19 — TTL

Thử TTL xóa terminal logs, phân biệt business expiry và background deletion.

### Bài 20 — Time-series

Tạo collection time-series trong version lab, tra restrictions về update, TTL/index và sharding.

### Bài 21 — Atlas tier

Chọn một Atlas tier đang có quyền xem và lập register về storage/connections/backup/Search; trích docs hiện hành.

### Bài 22 — Driver pool

Tính connection budget của 10 service instances với pool size X; đo actual connections và so với quota.

### Bài 23 — Restore drill

Restore snapshot vào staging; kiểm tra server/schema compatibility, keys, timing và RTO.

### Bài 24 — Search quota

Tra Atlas Search/Vector Search documentation đúng tier; phân biệt vector dimension limit và MongoDB BSON limit.

### Bài 25 — Limit register

Điền template với ít nhất 10 entries có effective value, owner, nguồn, ngày và trigger re-check.

### Bài 26 — Large document incident

Viết runbook cho `BSONObjectTooLarge` do unbounded audit array; chọn bounded preview và event collection.

### Bài 27 — Aggregation incident

Một pipeline `$lookup→$unwind→$group→$facet` lỗi memory. Đo fan-out từng bước và đề xuất shape nhỏ hơn.

### Bài 28 — Connection incident

Ứng dụng bị pool wait timeout sau scale lên 20 pods. Đối chiếu pool config, server quota, connections metric và slow queries.

### Bài 29 — Upgrade gate

Lập checklist nâng server/FCV khi Java Driver/Spring Data còn cũ. Đề xuất thứ tự test/upgrade theo supported matrix.

### Bài 30 — Architecture review

Thiết kế hệ thống dùng documents, transactions, Search, Change Streams và TTL trên Atlas. Ghi limits cứng, limits theo tier, ngưỡng nội bộ, test evidence và rollback plan.

---

## 43. Câu hỏi ôn tập

1. Hard limit, configurable limit, quota và operational limit khác nhau thế nào?
2. Vì sao phải ghi server version và FCV riêng?
3. Vì sao Atlas tier và driver version là một phần của “chữ ký môi trường”?
4. MongoDB BSON document tối đa bao nhiêu MiB?
5. Tại sao 16 MiB không phải kích thước toàn collection?
6. BSON bytes khác JSON characters như thế nào?
7. `$bsonSize` và `$size` đo hai thứ khác nhau ra sao?
8. Vì sao avgObjSize không đủ phát hiện outlier?
9. Một array có số phần tử tối đa chung không?
10. GridFS giải quyết loại dữ liệu nào?
11. Có thể dùng sharding để lưu một document 20 MiB không?
12. Vì sao phải tra namespace/naming restrictions theo version?
13. Tại sao maximum index count chưa đủ để quyết định index strategy?
14. Compound multikey indexes có restrictions gì?
15. Unique partial index có bảo vệ documents ngoài filter không?
16. Sharded unique index cần lưu ý gì?
17. Aggregation result limit khác stage memory như thế nào?
18. Stage count giới hạn thường là bao nhiêu?
19. `$facet` có những giới hạn nào và có spill không?
20. Vì sao `$group` với `$push:"$$ROOT"` nguy hiểm?
21. `allowDiskUse` có làm document 20 MiB hợp lệ không?
22. Tại sao bật spill có thể làm disk I/O tăng?
23. `$sort + $limit` khác `$limit + $sort` thế nào?
24. Vì sao `$lookup` dễ tạo fan-out?
25. Vì sao `$unwind` có thể tạo số rows khổng lồ?
26. `maxBsonObjectSize`, `maxMessageSizeBytes` và `maxWriteBatchSize` khác nhau thế nào?
27. Tại sao không lấy protocol maximum làm default app batch size?
28. Ordered bulk có atomic all-or-nothing không?
29. Cursor nhiều batches có vượt tổng 16 MiB không?
30. Tại sao Java `into(new ArrayList<>())` có thể gây OOM?
31. Vì sao `maxTimeMS` không thay query optimization?
32. MongoDB transaction hỗ trợ trên topology nào?
33. Transaction lifetime có cố định cho mọi environment không?
34. Tại sao không gọi payment API bên trong transaction callback?
35. Unknown commit outcome nên được xử lý thế nào?
36. Driver retryable writes có thay business idempotency không?
37. Vì sao cần tính connection budget theo instance và server?
38. Pool timeout và server BSON error khác nhau thế nào?
39. Oplog retention ảnh hưởng Change Streams thế nào?
40. Vì sao resume token không tồn tại mãi?
41. TTL có xóa đúng thời điểm expire không?
42. TTL có tự release inventory reservation không?
43. Time-series collections có thể cập nhật như normal collection trên mọi version không?
44. GridFS có làm arbitrary BSON document vượt 16 MiB hợp lệ không?
45. Atlas Search/Vector Search quotas có giống B-tree index limits không?
46. Vì sao backup retention không bảo đảm RTO?
47. Tại sao tăng memory/pool size có thể làm sự cố nặng hơn?
48. Giới hạn nào chịu ảnh hưởng OS/container/IOPS?
49. Khi nâng FCV cần test những nhóm feature nào?
50. Một Limit Register hữu ích phải lưu những trường nào?
51. Khi permission denied với serverStatus, nên làm gì?
52. Vì sao staging tier khác production khiến kết luận dễ sai?
53. Loại workload nào dễ tạo unbounded document?
54. Những metrics nào báo trước sắp chạm giới hạn?
55. Làm sao phân biệt MongoDB error và HTTP gateway 413?
56. Khi nào cần kiểm tra driver compatibility matrix?
57. Khi nào nên chọn referenced collection thay embedded array?
58. Tại sao không xóa legacy field trước migration reconciliation?
59. Khi nào một limit đã kiểm tra trước đây cần kiểm tra lại?
60. Tại sao “con số N” thiếu version/nguồn/ngày không đủ làm deployment gate?

---

## 44. Tổng kết

**Danh mục giới hạn MongoDB là một công cụ ra quyết định theo môi trường, không phải bảng số học thuộc lòng.**

- **BSON:** 16 MiB per document, nesting và naming restrictions; đo bằng BSON bytes, không suy từ JSON text.
- **Index:** số lượng, compound/multikey/unique/sharded rules; tra theo server version và workload.
- **Aggregation:** phân biệt result 16 MiB, stage memory/spill, `$facet` không spill, accumulator growth và 1.000 stages.
- **Writes/clients:** `hello` quảng bá BSON/message/batch capabilities; driver pool, memory, retries và operational batch size vẫn là giới hạn riêng.
- **Transactions:** topology, FCV, lifetime, resource budget, commit uncertainty và external idempotency.
- **Replication/CDC:** oplog retention, lag, resume history và pre/post images; không có retention window cố định cho mọi cluster.
- **Sharding/time-series/TTL:** có compatibility rules theo version, không suy chỉ từ tên MongoDB.
- **Atlas/Search/Vector:** quotas theo tier/plan/region/feature, phải tra tài liệu hiện hành.
- **Self-managed:** OS, memory, file descriptors, disk IOPS, network và container limits có thể là bottleneck trước engine.
- **Vận hành:** ghi Limit Register kèm evidence, threshold, owner và ngày; re-check trước upgrade/cutover/incident.

Một kiến trúc đúng không hỏi riêng “MongoDB cho tối đa bao nhiêu?”, mà hỏi: **Giới hạn nào áp cho workload này, ở server/FCV/tier/driver cụ thể, đã đo bằng gì, có headroom bao nhiêu, và khi vượt thì hệ thống xử lý/khôi phục thế nào?**

## Tài liệu tham khảo chính thức

- [MongoDB — Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB — BSON Documents](https://www.mongodb.com/docs/manual/core/document/)
- [MongoDB — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB — `$bsonSize`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bsonsize/)
- [MongoDB — Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB — Aggregation Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/)
- [MongoDB — `$facet`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/)
- [MongoDB — `$group`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/)
- [MongoDB — `$lookup`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB — `$sort`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/)
- [MongoDB — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB — Index Limits](https://www.mongodb.com/docs/manual/reference/limits/#index-limitations)
- [MongoDB — Compound Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [MongoDB — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB — Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/)
- [MongoDB — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB — Replica Sets](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB — Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/)
- [MongoDB — GridFS](https://www.mongodb.com/docs/manual/core/gridfs/)
- [MongoDB — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB — Queryable Encryption](https://www.mongodb.com/docs/manual/core/queryable-encryption/)
- [MongoDB — Feature Compatibility Version](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/)
- [MongoDB Atlas Documentation](https://www.mongodb.com/docs/atlas/)
- [MongoDB Atlas — Limits](https://www.mongodb.com/docs/atlas/reference/atlas-limits/)
- [MongoDB Atlas Search](https://www.mongodb.com/docs/atlas/atlas-search/)
- [MongoDB Atlas Vector Search](https://www.mongodb.com/docs/atlas/atlas-vector-search/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/)
