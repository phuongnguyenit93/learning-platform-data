# Shard bị ghi tập trung, dữ liệu lệch và truy vấn scatter-gather trong MongoDB

## 1. Bối cảnh: đã sharding nhưng một shard vẫn quá tải

Một hệ thống MongoDB có ba shards. Dashboard cho thấy:

```text
                      Shard A   Shard B   Shard C
Dung lượng dữ liệu       34%       33%       33%
Insert/update mỗi giây   87%        8%        5%
CPU primary              94%       28%       23%
```

Trong khi đó, endpoint đọc báo cáo:

```text
GET /events?status=FAILED
p95 latency: 120 ms -> 1.8 s sau khi thêm shard thứ ba.
```

Hai vấn đề có thể xảy ra đồng thời:

- **Write hotspot:** phần lớn thao tác ghi nhắm vào những shard-key ranges nằm trên một shard dù bytes được phân bố đều.
- **Scatter-gather:** truy vấn thiếu shard key khiến `mongos` gửi yêu cầu tới nhiều hoặc toàn bộ shards, rồi chờ và ghép kết quả.

Cũng có thể có **data skew** độc lập với hai vấn đề trên: ví dụ shard A sở hữu 75% dữ liệu, B 20%, C 5%. Phân bố số documents/bytes/chunks và phân bố CPU/operations không nhất thiết giống nhau.

Bài này hướng dẫn **nhận diện, định lượng, chẩn đoán và xử lý có kiểm soát** ba nhóm sự cố trong MongoDB sharded cluster:

1. Shard bị ghi tập trung (hot shard/write hotspot).
2. Dữ liệu hoặc ranges/chunks bị lệch giữa shards.
3. Truy vấn scatter-gather và hậu quả với độ trễ, network, fan-out.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Đọc cấu trúc `mongos`, config server replica set, shards, shard key và data ranges.
- Phân biệt **data skew**, **write/read workload skew** và **query fan-out** bằng metric riêng.
- Biết vì sao shard key có cardinality thấp, giá trị quá phổ biến hoặc tăng đơn điệu tạo hotspot.
- Xem dữ liệu phân bố thực qua `sh.status(true)`, `sh.getShardedDataDistribution()` và `$shardedDataDistribution`.
- Xem trạng thái balancer, migrations, jumbo/indivisible ranges và zones.
- Dùng `explain("executionStats")` từ `mongos` để nhận diện targeted vs broadcast/scatter-gather.
- Dùng Shard Key Analyzer (`configureQueryAnalyzer`, `analyzeShardKey`) để đo candidate key bằng workload được lấy mẫu.
- Phân biệt range-based và hashed shard keys cùng đánh đổi về routing.
- Đề xuất xử lý từ **query rewrite/traffic throttling** đến **refine/reshard**, không thao tác production mù quáng.
- Kết nối sự cố sharding với Java Driver/Spring Data MongoDB và API latency.
- Viết runbook, checklist và thực hành trên sharded test cluster.

**Lưu ý:** Các số liệu trong bài là ví dụ minh họa. Các lệnh thay đổi balancer, shard key hoặc index phải được đánh giá trên môi trường test và thực hiện theo runbook production được phê duyệt.

---

## 2. Nhắc lại kiến trúc sharded cluster

```text
                        Applications
                   Java / Spring Data
                              |
                              v
                 +--------------------------+
                 |         mongos           |
                 | Query router / metadata  |
                 +--------------------------+
                    /         |         \
                   v          v          v
               Shard A     Shard B     Shard C
              Replica Set Replica Set Replica Set
              P  S  S     P  S  S     P  S  S

                 Config Server Replica Set
                 Metadata: chunks/ranges,
                 shard key, zones, placement
```

- **`mongos`:** route operations theo shard key và metadata; không sở hữu collection data như `mongod`.
- **Shard:** thường là một replica set; thành viên primary xử lý writes của shard đó.
- **Config server replica set (CSRS):** lưu metadata phân vùng/placement, balancer điều phối hoạt động theo kiến trúc/version.
- **Shard key:** field hoặc compound fields dùng để phân vùng một sharded collection.
- **Chunk/range:** khoảng shard-key values; mỗi range do một shard sở hữu ở một thời điểm.
- **Balancer:** quản lý migration các ranges để cải thiện phân bố dữ liệu theo thresholds và zones.
- **Unsharded collection:** có thể tập trung trên database primary shard; không tự phân bố chỉ vì database nằm trong sharded cluster.

### 2.1. Ranges và bounds

Một range chứa giá trị từ **lower inclusive** đến **upper exclusive**:

```text
[MinKey, 100) -> Shard A
[100, 200)    -> Shard B
[200, MaxKey) -> Shard C
```

Ví dụ chỉ minh họa shard key đơn `customerId`; ranges thật có thể dựa trên hashed values hoặc compound keys.

Một **giá trị shard key duy nhất** không thể tự tách thành nhiều ranges chứa cùng giá trị để phân tán tự do. Vì vậy shard key có một giá trị cực kỳ phổ biến là dấu hiệu cần điều tra.

### 2.2. Đường ghi và đường đọc

**Insert:** `mongos` tính shard key của document rồi route write tới shard sở hữu range.

**Read:** nếu filter cho phép `mongos` xác định shard-key range, truy vấn có thể **targeted**; nếu không, router phải gửi yêu cầu tới nhiều hoặc toàn bộ shards.

**Update/delete:** routing và các điều kiện dùng shard key, `_id`, upsert, multi-update có những khác biệt theo MongoDB version và dạng operation. Đừng viết quy tắc tuyệt đối cho mọi version; với workload quan trọng, **truyền đầy đủ shard key khi phù hợp** để target tốt và đọc docs đúng version.

### 2.3. Không nên kết nối thẳng shard node để chạy ứng dụng

Ứng dụng bình thường kết nối qua **`mongos`** (hoặc endpoint được Atlas cung cấp). Từ MongoDB 8.0, một số database commands khi truy cập trực tiếp shard bị chặn với thông báo kết nối improperly và cần dùng router, trừ maintenance-specific role/conditions.

Không bypass `mongos` để “giảm scatter-gather” trong production: bạn sẽ đánh mất routing/metadata semantics và có thể trả dữ liệu không đầy đủ.

---

## 3. Ba triệu chứng khác nhau và cách chứng minh

| Vấn đề | Định nghĩa | Dấu hiệu | Bằng chứng cần |
| --- | --- | --- | --- |
| **Write hotspot** | Writes tập trung vào một shard/range | Một shard CPU/write IOPS cao, latency tăng | Ops/s per shard, key frequency, key monotonicity |
| **Data skew** | Dung lượng/owned docs không đều | Một shard nhiều bytes/docs, ít free disk | `$shardedDataDistribution`, ranges, zones |
| **Scatter-gather** | Query gửi đến nhiều hoặc mọi shards | Query p95 cao, mongos merge/fan-out, nhiều shards cùng bận | `explain`, query shape, shard key predicates |
| **Read hotspot** | Nhiều reads vào một shard | CPU/network một shard cao dù writes đều | Read ops per shard, targeted query distribution |
| **Balancer lag** | Migration chưa đưa data về phân bố mong muốn | Data skew kéo dài, migrations đang chạy/failed | `balancerStatus`, logs, jumbo/zone metadata |

Ba triệu chứng **có thể cùng tồn tại** nhưng phải có chứng cứ riêng. Ví dụ 33/33/34% dung lượng không hề bác bỏ việc 90% ghi đang vào shard A.

### 3.1. Một số metric đơn giản

Tỷ lệ writes của shard i:

\[
p_i = \frac{\mathrm{writes}_i}{\sum_j \mathrm{writes}_j}
\]

Nếu phân bố 870/80/50 writes/s trên ba shards:

- A: 87%.
- B: 8%.
- C: 5%.

Chỉ số độ lệch dung lượng:

\[
\mathrm{max/min\ bytes}
=
\frac{\max_i(\mathrm{ownedBytes}_i)}
{\min_i(\mathrm{ownedBytes}_i)}
\]

Nếu có shard bằng 0 bytes, không chia cho 0; thay bằng bảng bytes và shard count, ghi rõ collection có thể còn đang phân bố ban đầu.

**Không đặt ngưỡng “trên 60% là lỗi” một cách phổ quát.** Tùy tenant size, zones, traffic, time-of-day và resource capacity.

---

## 4. Checklist phút đầu của incident

Nếu API p99 tăng hoặc một shard CPU 95%:

1. Ghi thời điểm UTC, environment, database/collection, cluster/tier/server version.
2. Xác định có shard nào **hot** và chỉ rõ CPU, writes/s, cache/disk/network.
3. Kiểm tra **sự kiện triển khai**, import/backfill, batch TTL, migrations, autoscaling.
4. Dùng `mongos` đọc shard key hiện tại và distribution.
5. Phân biệt **CPU hotspot** với **data skew** bằng per-shard metrics.
6. Xác định top query shapes và xem `explain` targeted/scatter.
7. Kiểm tra balancer status, zones, range migrations, jumbo.
8. Xác định write key distribution, heavy tenant/single-key values và monotonic key.
9. Đề xuất **giảm tải an toàn trước**, rồi thay đổi schema/shard key nếu có bằng chứng.
10. Đo kết quả sau xử lý và lưu rollback plan.

**Không ngay lập tức** di chuyển chunk thủ công, tắt balancer, drop shard key index hoặc chạy `reshardCollection` trên production.

---

## 5. Kết nối đúng mongos và xác minh topology

Từ `mongosh` kết nối vào endpoint `mongos` của **test cluster** hoặc URI Atlas sharded cluster:

```javascript
db.adminCommand({ hello: 1 });
```

Trên `mongos`, output của `hello` có:

```javascript
{
  msg: "isdbgrid",
  ok: 1
  // ... nhiều fields khác
}
```

Nếu không có `msg: "isdbgrid"`, kiểm tra có đang kết nối đến `mongod` trực tiếp hay không.

Một số lệnh chẩn đoán (cần quyền theo deployment):

```javascript
sh.status();
sh.status(true);
sh.getBalancerState();

db.adminCommand({ balancerStatus: 1 });
db.adminCommand({ listShards: 1 });
```

### 5.1. `sh.status(true)` dùng để làm gì?

Thông thường nó hiển thị:

- Shards có trong cluster.
- Thông tin databases và database primary shard.
- Shard key/index strategy của các sharded collections.
- Số ranges/chunks trên từng shard.
- Thông tin balancing, zones.
- Có thể có sharded data distribution.

Với collection có nhiều chunks, `sh.status(true)` cho phần verbose; output có thể rất dài. Trong production, ưu tiên lọc namespace hoặc dùng Atlas UI nếu chỉ cần một số chỉ báo.

### 5.2. Không nhầm primary shard và primary replica set

- **Database primary shard:** nơi unsharded collections của database thường cư trú.
- **Replica set primary:** thành viên primary trong từng shard replica set, phục vụ ghi.

Một database có primary shard là A **không có nghĩa** mọi sharded collections sẽ ghi vào A. Nhưng một unsharded collection cực lớn/nóng trên A có thể tạo imbalance bất kể shard key của các collections khác.

---

## 6. Đo data skew bằng `$shardedDataDistribution`

Trên MongoDB hỗ trợ stage này, kết nối tới `mongos` và dùng database `admin`:

```javascript
db.getSiblingDB("admin").aggregate([
  { $shardedDataDistribution: {} },
  { $match: { ns: "commerce.orders" } }
]).toArray();
```

Stage `$shardedDataDistribution` có từ MongoDB 6.0.3; cần privilege `shardedDataDistribution` và **chỉ chạy trên `mongos`**.

Một cách xem tương ứng trong `mongosh`:

```javascript
sh.getShardedDataDistribution()
  .filter(x => x.ns === "commerce.orders");
```

**Đây là ví dụ đọc;** thay `commerce.orders` bằng namespace đang điều tra.

### 6.1. Đọc output

```javascript
[
  {
    ns: "commerce.orders",
    shards: [
      {
        shardName: "shardA",
        numOwnedDocuments: 7000000,
        ownedSizeBytes: 7300000000,
        numOrphanedDocs: 0,
        orphanedSizeBytes: 0
      },
      {
        shardName: "shardB",
        numOwnedDocuments: 2000000,
        ownedSizeBytes: 2100000000,
        numOrphanedDocs: 0,
        orphanedSizeBytes: 0
      },
      {
        shardName: "shardC",
        numOwnedDocuments: 1000000,
        ownedSizeBytes: 1050000000,
        numOrphanedDocs: 0,
        orphanedSizeBytes: 0
      }
    ]
  }
]
```

**Các con số hoàn toàn minh họa.**

| Field | Ý nghĩa |
| --- | --- |
| `ns` | Database.collection |
| `shardName` | Tên shard |
| `numOwnedDocuments` | Documents thuộc quyền sở hữu hiện tại của shard |
| `ownedSizeBytes` | Estimated kích thước **uncompressed** của owned documents |
| `numOrphanedDocs` | Documents còn sót sau migration chưa được dọn |
| `orphanedSizeBytes` | Estimated kích thước orphaned documents |

Lưu ý `ownedSizeBytes` **không giống disk consumed** vì nén, indexes, fragmentation, oplog và những yếu tố storage khác. Muốn đánh giá disk capacity vẫn cần host/disk metrics.

### 6.2. Orphans không mặc định là data corruption

Khi range migration hoàn tất, dữ liệu ở donor có thể được xóa bất đồng bộ. Do vậy có thể thấy orphaned docs trong lúc cleanup. Không tự `deleteMany()` trực tiếp để “dọn orphan” vì làm hỏng cluster.

Nếu orphaned docs tăng không giảm, kiểm tra long-running reads, migration cleanup, balancer logs và server version; dùng hướng dẫn hỗ trợ được duyệt.

### 6.3. Metrics có thể là estimates

Sau unclean shutdown, thống kê counts/sizes có thể chênh lệch so với dữ liệu thật cho đến khi được cập nhật. Không dùng chênh 1–2% làm bằng chứng mất dữ liệu khi chưa so source/refresh semantics.

---

## 7. Chunk count khác số documents và bytes

Giả sử:

```text
Shard A: 100 chunks, 12 GB
Shard B: 110 chunks, 11 GB
Shard C:  95 chunks, 11 GB
```

Đây có thể là data distribution chấp nhận được.

Nhưng:

```text
Shard A: 60 chunks, 30 GB
Shard B: 60 chunks,  4 GB
Shard C: 60 chunks,  2 GB
```

Chunk count bằng nhau **không có nghĩa bytes cân bằng**. Ranges có thể khác nhau về mật độ document, kích thước BSON và shard key frequency.

Một chunk cũng có thể chứa rất nhiều writes tại thời điểm hiện tại dù dung lượng chưa lớn. Vì vậy quan sát độc lập:

- Chunks/ranges per shard.
- Owned docs/bytes per shard.
- Writes/reads per shard.
- CPU/IOPS/memory/network.
- Hot shard-key values.
- Balancer activity/errors.

### 7.1. Range size và migrations

MongoDB tài liệu hiện hành nêu default configured range size khoảng **128 MB**. Balancer migration decisions dựa trên **amount of data** và thresholds, không đơn giản so chunk counts.

Với default 128 MB, tài liệu nêu collection có thể được coi cân bằng khi chênh data giữa shard lớn nhất/nhỏ nhất nhỏ hơn khoảng **3 × range size** (ví dụ 384 MB). **Không tự điều chỉnh range size** chỉ để mọi shard trông có cùng số chunks.

### 7.2. Per-collection vs total bytes

Nếu shard A chứa nhiều unsharded collections còn shard B không, tổng dung lượng A cao không nhất thiết là imbalance của một sharded collection cụ thể. Đo **theo namespace** và phân biệt database primary shard/unsharded workloads.

---

## 8. Write hotspot do shard key tăng đơn điệu

Một thiết kế dễ gặp:

```javascript
sh.shardCollection(
  "commerce.events",
  { createdAt: 1 }
);
```

Mọi event mới có `createdAt` tăng theo thời gian.

### 8.1. Vì sao ghi dồn vào một range?

Ranged sharding chia dữ liệu theo thứ tự shard key:

```text
...older...                         ...newest...
[MinKey, T1)   -> Shard A
[T1, T2)       -> Shard B
[T2, MaxKey)   -> Shard C  <-- all new writes
```

Có một range chứa cận trên `MaxKey`. Nếu tất cả new key values tăng dần, chúng đi vào range cuối và tại một thời điểm **tập trung vào shard sở hữu range đó**.

Balancer có thể chia/move ranges theo dữ liệu, nhưng không đảm bảo phân tán **cùng lúc các writes mới nhất** khi key liên tục tăng.

### 8.2. Dấu hiệu

- Write ops/s trên một shard áp đảo.
- CPU/IOPS primary shard đó tăng theo traffic ingest.
- Other shards có free capacity.
- Data bytes có thể vẫn khá đều.
- Hot range theo thời gian dịch nhưng mỗi lúc chỉ một hoặc một số shards xử lý phần lớn ghi.

### 8.3. Hashed key có thể giảm hotspot monotonic

Thay `{createdAt:1}` bằng một field có giá trị phân tán như:

```javascript
{ eventId: "hashed" }
```

có thể phân tán inserts tốt hơn nếu `eventId` đủ đa dạng và mỗi event có một ID khác nhau.

**Đánh đổi:** truy vấn theo **khoảng thời gian** không còn route chỉ nhờ `createdAt` nếu shard key là `eventId`. Chúng có thể scatter-gather; cần đo tỷ lệ writes vs time-range reads.

**Không** kết luận cứ hash timestamp là tốt: hash giúp phân tán equality values, nhưng time-range pruning bị giảm mạnh và patterns có thể khác.

---

## 9. Write hotspot do low cardinality

Shard key chỉ có vài giá trị:

```javascript
{ status: 1 }
// NEW, PAID, FAILED, CANCELLED
```

Nếu phần lớn inserts bắt đầu bằng `status="NEW"`, mọi writes tới giá trị đó thuộc cùng shard-key range, tạo hotspot.

### 9.1. Cardinality là gì?

Cardinality = số giá trị shard key khác nhau trong dữ liệu.

| Candidate key | Cardinality giả định | Rủi ro |
| --- | ---: | --- |
| `status` | 4 | Rất thấp |
| `region` | 5 | Thấp, region có thể mất cân bằng |
| `tenantId` | 1.000 | Có thể ổn nhưng tenant lớn |
| `eventId` | 100 triệu | Cao |
| `createdAt` | Rất cao | Có thể monotonically increasing |

Cardinality cao là điều kiện tốt nhưng **không đủ**. `createdAt` có nhiều giá trị vẫn tạo hotspot do monotonicity.

### 9.2. Một giá trị duy nhất có thể không chia được

Chunk/range bao phủ một shard-key value có frequency quá cao có thể trở thành **indivisible/jumbo range**. Balancer không thể chia một single key value thành các ranges độc lập để di chuyển từng phần theo cùng shard key.

Muốn thay đổi, thường phải:

- **Refine** shard key để thêm suffix, tăng khả năng chia nhỏ các giá trị cũ.
- Hoặc **reshard** sang key khác.
- Hoặc thay mô hình dữ liệu/application để có key phân tán thực sự.

Không “force move” một jumbo range trên production mà chưa đánh giá downtime/write blocking.

---

## 10. Write hotspot do giá trị xuất hiện quá thường xuyên

Giả sử 1.000 tenants nhưng một tenant mang 80% traffic:

```text
Tenant A: 80% inserts
Other 999 tenants: 20% inserts
```

Shard key:

```javascript
{ tenantId: 1 }
```

có cardinality 1.000 nhưng một giá trị `tenantId="A"` có **frequency** rất lớn. Mọi writes của tenant A có thể bị tập trung tại shard sở hữu tenant đó.

### 10.1. Hash tenantId đơn thuần chưa giải quyết

```javascript
{ tenantId: "hashed" }
```

Hash giúp phân bố **các tenants khác nhau** lên shards. Nhưng **một tenant A duy nhất** vẫn hash ra **một giá trị**, thường được route tới cùng một shard. Nó không tự chia workload của heavy tenant.

Đây là sai lầm phổ biến: “Dùng hashed key là hết hot tenant”. Không đúng khi hotspot xuất phát từ một value có frequency cực cao.

### 10.2. Candidate compound key

Có thể cân nhắc:

```javascript
{ tenantId: 1, eventId: "hashed" }
```

Nhiều `eventId` của tenant A có hashed values khác nhau, giúp tạo các ranges phân tán **trong cùng tenant**, nếu cluster được sharding/phân bố tương ứng.

Đánh đổi:

- Truy vấn chỉ theo `tenantId` có thể phải hỏi **nhiều shards**.
- Truy vấn full equality trên `tenantId` và `eventId` có thể targeted.
- Khi filter theo time range nhưng thiếu `eventId`, fan-out tăng.
- Compound hashed shard key có constraints/unique/index implications cần xác minh theo version.

Không áp dụng candidate này chỉ bằng cảm giác; dùng Shard Key Analyzer và benchmark query workload.

---

## 11. Cardinality, frequency và monotonicity: bộ ba phải đo

| Thuộc tính | Tốt thường gặp | Nguy cơ |
| --- | --- | --- |
| **Cardinality** | Nhiều giá trị distinct | Không đủ ranges để chia |
| **Frequency** | Phân bố số documents/writes không quá lệch | Hot values tạo hotspot/jumbo |
| **Monotonicity** | Keys không luôn tăng/giảm liên tục | “Right-most”/“left-most” insertion hotspot |
| **Query locality** | Common filters có shard key/prefix | Scatter-gather thường xuyên |
| **Update behavior** | Shard key ổn định | Cross-shard movement/phức tạp |
| **Business constraints** | Hỗ trợ tenant/uniqueness | Index và transaction bất lợi |

### 11.1. Không chọn key chỉ theo dữ liệu hiện tại

Dataset có thể cân bằng theo tenant hôm nay nhưng campaign vừa ra mắt tạo 90% traffic vào một tenant mới. Cần phân tích **incoming writes** và expected growth, không chỉ documents hiện có.

### 11.2. Shard key là quyết định toàn workload

Một key tốt cho writes có thể tệ cho reads, và ngược lại:

- `{createdAt:1}` thuận time range reads nhưng có thể write hotspot.
- `{eventId:"hashed"}` thuận insert distribution và point lookup theo eventId, nhưng time range reads có thể scatter.
- `{tenantId:1,createdAt:1}` hỗ trợ per-tenant time queries nhưng một tenant hot + increasing time vẫn tạo hot tail.
- `{tenantId:1,eventId:"hashed"}` có thể phân chia writes trong tenant, nhưng per-tenant reports có thể fan-out.

---

## 12. Scatter-gather là gì?

Một query gửi qua `mongos` có hai hình thái chính:

### 12.1. Targeted query

```text
Client:
  find({tenantId:"A", eventId:"evt-42"})
          |
          v
        mongos
          |
          +------> Shard B (đúng range)
```

Router dùng shard key metadata để xác định shard hoặc subset shards chứa dữ liệu.

### 12.2. Scatter-gather query

```text
Client:
  find({status:"FAILED"})
          |
          v
        mongos
        /  |  \
       v   v   v
      A    B   C
       \   |  /
        v  v  v
       merge results
           |
           v
         Client
```

Nếu filter thiếu shard key (hoặc predicate không cho pruning), `mongos` broadcast tới tất cả shards liên quan, chờ responses và merge results.

### 12.3. Hậu quả khi thêm shards

Giả sử một query scatter tới 8 shards, mỗi shard thực hiện một phần công việc. 2.000 HTTP requests/s có thể tạo **nhiều nghìn shard-level query executions mỗi giây**. Đây là quan hệ fan-out khái niệm, không phải mỗi request luôn chính xác N server commands: optimizer, aggregation pipeline, caching và implementation có thể ảnh hưởng.

Tail latency của scatter query có thể bị chi phối bởi **shard chậm nhất** cộng với network và merge cost. Trong hệ thống có một shard hot, scatter-gather còn làm request bình thường phải đợi shard đang bận.

### 12.4. Scatter không phải luôn sai

Aggregation cần phân tích dữ liệu trên toàn cluster (analytics) có thể chủ ý chạy song song trên nhiều shards. Vấn đề là **OLTP query thường xuyên thiếu target**, không phải mọi aggregation broadcast đều đáng tránh.

---

## 13. Query nào thường targeted?

Giả sử current shard key:

```javascript
{ tenantId: 1, orderId: 1 }
```

Các query:

```javascript
// Có full equality shard key:
{ tenantId: "A", orderId: "O-101" }

// Có prefix:
{ tenantId: "A" }

// Không có prefix:
{ orderId: "O-101" }

// Hoàn toàn không liên quan shard key:
{ status: "PAID" }
```

Phân tích:

| Filter | Mongos có thể prune shards? | Lưu ý |
| --- | --- | --- |
| Full equality tenantId + orderId | Có, thường tới một shard | Khi key/ranges/metadata phù hợp |
| Chỉ tenantId (prefix) | Có thể tới subset shards | Không bảo đảm một shard nếu tenant trải nhiều ranges |
| Chỉ orderId | Thường broadcast | Thiếu leading prefix tenantId |
| Chỉ status | Thường broadcast | Index status trên từng shard không thay routing |
| tenantId + status | Có thể prune theo tenantId | Có thể vẫn nhiều shards |
| `$or` với một nhánh thiếu tenantId | Có thể broadcast | Xem toàn bộ query logic |

**Không dùng “có shard key trong filter” như cam kết tuyệt đối một-shard**; prefix/range/compound/hashing/zones và query shape quyết định số shards được target.

### 13.1. Hashed key

Với `{eventId:"hashed"}`:

```javascript
// Equality: mongos có thể hash value và target.
{ eventId: "evt-42" }

// Range: hashed order không giữ natural order của eventId.
{ eventId: { $gte: "evt-100", $lt: "evt-200" } }
```

Range query theo original values có thể scatter-gather. Đặc tính hashed distribution đối lập range locality.

### 13.2. `_id` không tự là shard key

Nếu collection sharded theo `{tenantId:1,eventId:"hashed"}`, query:

```javascript
{ _id: ObjectId("...") }
```

không tự có full shard key. `_id` index tồn tại trên các shards nhưng **không bảo đảm router target một shard**. Thiết kế API truy xuất ID nên mang context shard key khi có thể.

### 13.3. Index và routing là hai bước khác nhau

1. `mongos` quyết định shard(s) nào nhận query.
2. **Mỗi shard nhận query** chọn local index/query plan.

Tạo index `{status:1}` trên mỗi shard có thể giảm documents scanned **trong từng shard**, nhưng **không biến** `find({status:"FAILED"})` thành targeted nếu shard key là `eventId`.

---

## 14. Explain từ mongos: xác minh query fan-out

Kết nối với `mongosh` tới `mongos`, chạy trên collection được sharding thật:

```javascript
const dbLab = db.getSiblingDB("hotspot_lab");

const targetedPlan = dbLab.events_hashed
  .find({ eventId: "event-42" })
  .explain("executionStats");

printjson(targetedPlan);
```

Sau đó:

```javascript
const scatterPlan = dbLab.events_hashed
  .find({ status: "FAILED" })
  .limit(20)
  .explain("executionStats");

printjson(scatterPlan);
```

### 14.1. Cần tìm gì?

- Các shard IDs/names tham gia execution.
- Plan trong từng shard.
- `nReturned`, `totalDocsExamined`, `totalKeysExamined` từng shard khi có.
- Stages liên quan `SHARD_MERGE`, `SHARDING_FILTER`, `SORT`, `IXSCAN`, `COLLSCAN` tùy engine/version.
- Merge logic và sort/limit placement.
- Query time thực tế trên mỗi shard.

**Cấu trúc Explain JSON thay đổi theo server version và query engine**, không luôn có đúng một path `queryPlanner.winningPlan.shards`. Xem toàn bộ output, không chỉ grep một từ khóa rồi kết luận.

### 14.2. Aggregation có thể tách pipeline

Ví dụ:

```javascript
dbLab.events_hashed.explain("executionStats").aggregate([
  { $match: { status: "FAILED" } },
  { $group: { _id: "$tenantId", count: { $sum: 1 } } },
  { $sort: { count: -1 } }
]);
```

Explain có thể thể hiện `splitPipeline`, `shards`, `mergeType` hoặc cấu trúc khác theo version; `mongos`/shard nhận trách nhiệm merge khác nhau tùy stages.

### 14.3. Test đúng môi trường

Không dùng Explain trên **standalone** rồi kỳ vọng nhìn nhiều shards. Chỉ một sharded cluster với ít nhất hai shards mới cho bằng chứng thực về routing.

---

## 15. Atlas Sharding Insights và per-shard metrics

Với MongoDB Atlas đủ điều kiện, **Sharding Insights** tập hợp:

- Shards view: resource utilization, workload, data distribution.
- Collections view: distribution theo namespace/ranges.
- Mongos Instances view: query router behavior.
- Balancer activity và metadata theo tính năng hiện hành.

Theo tài liệu Atlas được tham chiếu, Sharding Insights yêu cầu **M10+ sharded cluster, MongoDB 8.0+**, commercial Atlas Core và các feature restrictions riêng. Nó không có trên replica set đơn thuần, một số cluster types hoặc các tiers thấp hơn.

### 15.1. Đọc theo hai trục

**Trục A — Dữ liệu:** ownedBytes, ownedDocs, ranges/chunks.

**Trục B — Workload:** writes/s, reads/s, CPU, disk IOPS, network, operation latency.

Một shard nhiều dữ liệu có thể không hot; một shard ít dữ liệu có thể cực hot.

### 15.2. Chọn khoảng thời gian đúng

Một batch import chạy từ 14:00–14:10 UTC có thể bị làm mượt trên biểu đồ 30 ngày. Thu hẹp khoảng thời gian, xem granularity nhỏ nhất được hỗ trợ, đối chiếu deployment marker và batch job logs.

### 15.3. Nếu không có Insights

Dùng `sh.status`, `$shardedDataDistribution`, Atlas per-node metrics, command/profiler logs hoặc monitoring phù hợp self-managed deployment. Không suy từ việc không thấy menu rằng dữ liệu đã cân bằng.

---

## 16. Shard Key Analyzer: đo thay vì đoán

MongoDB 7.0+ hỗ trợ **`analyzeShardKey`** để đánh giá candidate/current shard key dựa trên characteristics và workload samples.

### 16.1. Bắt đầu bằng ý tưởng workload

Candidate keys có thể là:

```javascript
{ createdAt: 1 }
{ eventId: "hashed" }
{ tenantId: 1, createdAt: 1 }
{ tenantId: 1, eventId: "hashed" }
```

Không chọn key chỉ vì cardinality cao; cần xem query distribution và writes.

### 16.2. Bật query sampling có kiểm soát

Trên môi trường test hoặc production được phê duyệt:

```javascript
const events = db.getSiblingDB("hotspot_lab").events_hashed;

events.configureQueryAnalyzer({
  mode: "full",
  samplesPerSecond: 1
});
```

`configureQueryAnalyzer` cần quyền phù hợp. `samplesPerSecond` là **sampling rate**, không phải cam kết có đúng một mẫu cho mọi giây khi không có đủ operations.

**Không bật sampling nhiều giờ trên production mà không có owner/retention/policy.**

### 16.3. Phân tích candidate key

```javascript
const report = events.analyzeShardKey({
  eventId: "hashed"
});

printjson(report);
```

Một số options tùy method/version hỗ trợ:

```javascript
events.analyzeShardKey(
  { eventId: "hashed" },
  {
    keyCharacteristics: true,
    readWriteDistribution: true,
    sampleSize: 10000
  }
);
```

`sampleSize` và `sampleRate` không được dùng cùng lúc. Các metrics distribution phụ thuộc **sampled queries thực sự**, nên nếu quá ít samples có thể thiếu hoặc không đại diện.

### 16.4. Tắt sampling sau điều tra

```javascript
events.configureQueryAnalyzer({
  mode: "off"
});
```

Giữ báo cáo anonymized, time range, traffic mix và tổng samples trong incident notes.

### 16.5. Các trường thông tin

| Nhóm | Ý nghĩa |
| --- | --- |
| `keyCharacteristics` | Cardinality, frequency, monotonicity |
| `numDocsSampled` | Kích thước sample |
| `mostCommonValues` | Những values xuất hiện nhiều và frequency |
| `readWriteDistribution` | Targeting/read/write workload distribution từ sampled queries |
| Routing-related metrics | Tỷ lệ targeted/multi-shard/scatter theo cấu trúc version |

Không coi sample trong giờ thấp điểm đại diện cho campaign/batch peak. Nên so nhiều time windows và cân nhắc seasonal workload.

---

## 17. Xác minh dữ liệu theo key trước khi cân nhắc reshard

Các truy vấn thống kê sau có thể tốn tài nguyên trên collection lớn; **chạy lab/staging hoặc query sampling được phê duyệt**.

### 17.1. Heavy tenants

```javascript
db.getSiblingDB("hotspot_lab").events_range.aggregate([
  { $group: { _id: "$tenantId", docs: { $sum: 1 } } },
  { $sort: { docs: -1 } },
  { $limit: 10 }
]).toArray();
```

Thống kê theo document **không bằng throughput theo thời gian**; một tenant có nhiều documents lịch sử chưa chắc là tenant đang tạo 80% writes hiện tại.

### 17.2. Key frequency

```javascript
db.getSiblingDB("hotspot_lab").events_range.aggregate([
  { $group: { _id: "$status", docs: { $sum: 1 } } },
  { $sort: { docs: -1 } }
]).toArray();
```

Nếu 90% events có `status="NEW"`, shard key `status` là candidate rất nguy hiểm về frequency.

### 17.3. Monotonicity

Kiểm tra key theo thời gian:

- Tại thời điểm T, các inserts mới có `createdAt` luôn tăng?
- `ObjectId`/incrementing sequences có tự tăng theo thời gian?
- Có batch imports lịch sử làm đảo xu hướng không?
- Có partitions/regions khác nhau gây nhiều tail ranges hay chỉ một?

`analyzeShardKey` là công cụ hữu ích, nhưng kết hợp application write traces và expected future patterns.

---

## 18. Balancer có trách nhiệm gì và không thể làm gì?

Balancer giám sát lượng dữ liệu theo sharded collection và có thể migrate ranges giữa shards nếu chênh phân bố đạt threshold, đồng thời **tôn trọng zone constraints**.

### 18.1. Migrations tốn chi phí

Di chuyển dữ liệu có thể tạo:

- Network copy giữa donor/recipient.
- Index synchronization.
- Increased disk/CPU.
- Replication overhead.
- Metadata changes/routing refresh.
- Asynchronous cleanup trên donor.

Không coi balancer là một scheduler sẽ tự dàn đều **CPU/writes per second** giữa shards.

### 18.2. Status và diagnostics

Trên `mongos`:

```javascript
sh.getBalancerState();

db.adminCommand({ balancerStatus: 1 });

sh.status(true);
```

Có thể xem trạng thái balancing theo collection (method và options tùy release):

```javascript
sh.balancerCollectionStatus("hotspot_lab.events_range");
```

Nếu balancer enabled nhưng data skew kéo dài, kiểm tra migrations, zones, range sizes, jumbo/indivisible ranges và migration failures.

### 18.3. Khi nào balancer không nên bị can thiệp?

Một số chênh lệch data **dưới migration threshold** là bình thường. Balancer có thể cân bằng theo amount of data chứ không chạy chỉ vì chunk counts khác nhau.

Tắt balancer dài hạn có thể khiến imbalance tăng theo thời gian; bật nó lại không bảo đảm giải quyết **hot key value** hoặc tập writes tập trung.

### 18.4. Không reset metadata thủ công

Tuyệt đối không sửa trực tiếp `config.chunks`, `config.collections`, `config.tags`, chunk ownership hoặc balancer state trong `config` database bằng những commands không được hỗ trợ. Metadata sai có thể làm cluster lỗi nghiêm trọng.

---

## 19. Jumbo/indivisible chunks và stuck migrations

Khi range lớn đến mức không thể split theo shard key, có thể thành **jumbo/indivisible range**. Thường gặp khi shard key có giá trị lặp rất nhiều hoặc cardinality không đủ.

### 19.1. Dấu hiệu

- `sh.status(true)`/balancer logs có `jumbo` hoặc cảnh báo oversized range.
- `balancerStatus` có migrations failed/retried.
- Một shard giữ quá nhiều bytes trong collection.
- Balancer vẫn enabled nhưng data distribution không cải thiện.
- Log có thông báo range migration conflicts, replication lag hoặc disk pressure.

### 19.2. Không tự forceJumbo trên production

Một số commands/options như `moveRange`, `moveChunk`, `forceJumbo`, clear jumbo flag có thể tồn tại theo MongoDB version. Tài liệu MongoDB cảnh báo **force migration jumbo range có thể block writes lâu**.

Vì vậy quy trình an toàn:

1. Xác nhận đây là oversized/indivisible range thật.
2. Kiểm tra migration logs, disk, replication health, ranges, zones.
3. Phân tích shard key cardinality/frequency.
4. Đánh giá **refine** hoặc **reshard** để giải quyết nguyên nhân.
5. Nếu cần manual migration, làm theo runbook có backup/change approval và tham vấn MongoDB Support khi phù hợp.
6. Không xóa dữ liệu hoặc sửa config metadata bằng tay.

### 19.3. Một hot key value không thể di chuyển chia đôi

Nếu 50 triệu documents cùng shard key `tenantId="A"`, moving range sang shard B chỉ **chuyển hotspot từ A sang B**, không chia writes đồng thời trên A/B. Cần có key có khả năng chia nhỏ nhiều giá trị khác nhau.

---

## 20. Zone sharding: lệch dữ liệu có thể là chủ đích

MongoDB cho phép định nghĩa **zones/tags** để gắn shard key ranges với shards phù hợp.

Ví dụ:

```text
EU region -> EU shards
APAC region -> APAC shards
```

Nếu APAC traffic lớn gấp 4 lần EU, một số shards APAC có thể nhiều data/CPU hơn. Đây có thể là **chính sách địa lý/tuân thủ**, không phải lỗi balancer.

Trước khi reshard/move:

- Xem zone ranges và shard assignments.
- Xem data residency/compliance requirements.
- Kiểm tra ranges có thể migrate tới những shards nào.
- Không di chuyển dữ liệu ra khỏi zone vì chỉ muốn dashboard cân bằng.

**Mục tiêu không phải mọi shard 33.3% bằng nhau**, mà là đáp ứng SLO, capacity và data-placement policy.

---

## 21. Refine shard key và reshard khác nhau

### 21.1. Refine: thêm suffix vào shard key cũ

Giả sử current shard key:

```javascript
{ tenantId: 1 }
```

Bạn có candidate mới:

```javascript
{ tenantId: 1, eventId: 1 }
```

`refineCollectionShardKey` thêm field(s) ở **phía sau** existing shard key, giữ existing prefix; có thể tăng cardinality và tạo khả năng split các hot values.

Ví dụ **chỉ để học API; không chạy ngoài lab/approval**:

```javascript
db.adminCommand({
  refineCollectionShardKey: "commerce.events",
  key: { tenantId: 1, eventId: 1 }
});
```

Điều kiện thực tế:

- Có index hỗ trợ refined shard key theo quy định.
- Tất cả documents phải có field phù hợp semantics (hoặc xử lý missing theo giới hạn phiên bản).
- Unique constraints/shard key rules hợp lệ.
- Existing prefix **không bị thay đổi**.
- Refine **không đồng nghĩa** lập tức phân bố lại dữ liệu/writes qua shards.
- Cần cho balancer/phân bổ lại ranges theo ngữ cảnh.

### 21.2. Reshard: chọn shard key mới

MongoDB 5.0+ hỗ trợ `reshardCollection` để đổi shard key của sharded collection.

Ví dụ **KHÔNG chạy production khi chưa có change approval**:

```javascript
db.adminCommand({
  reshardCollection: "commerce.events",
  key: { eventId: "hashed" }
});
```

Reshard có thể tái phân bố dữ liệu theo key mới và thay đổi routing semantics, nhưng tiêu thụ **tài nguyên lớn** và có những requirements/limitations về version, resources, concurrent changes và transactions.

### 21.3. MongoDB 8.0: redistribute với cùng shard key

Một số phiên bản 8.0 hỗ trợ **same-key resharding** với `forceRedistribution` khi điều kiện phù hợp:

```javascript
db.adminCommand({
  reshardCollection: "commerce.events",
  key: { eventId: "hashed" },
  forceRedistribution: true
});
```

Đây **không phải** giải pháp một giá trị shard key duy nhất nhận mọi writes. Nó chủ yếu giúp phân bố lại data trên shards mà **không đổi key**, ví dụ sau khi thêm shard, nhưng cần resource capacity và runbook.

MongoDB 8.0 cũng có `sh.shardAndDistributeCollection()` cho những deployment phù hợp. Không tự copy lệnh từ bài học vào production mà chưa kiểm tra current key, cluster version và prerequisites.

### 21.4. So sánh

| Giải pháp | Giải quyết gì? | Không tự giải quyết |
| --- | --- | --- |
| Bật lại balancer nếu đã tắt | Data migrations không diễn ra | Single hot shard-key value |
| Thêm index local | Giảm scan trong shard | Scatter routing |
| Refine key với suffix | Tăng cardinality/splittability | Existing hot tail ngay lập tức |
| Reshard sang key mới | Đổi routing, phân bố data và writes | Query patterns thiếu new shard key |
| Same-key redistribution | Đưa data lên thêm shards khi phù hợp | Wrong key cardinality/frequency |
| Thêm shard | Tăng tổng resources | Hot key cố định trên một shard |
| Throttle/hạn chế batch | Giảm áp lực ngắn hạn | Root cause key design |

---

## 22. Xử lý write hotspot ngắn hạn

Trước khi làm thay đổi shard key tốn kém, có thể áp dụng hành động giảm impact (tùy business requirements):

1. **Throttle batch import/backfill** gây 80% writes vào một key range.
2. Giới hạn per-tenant/per-producer write concurrency.
3. Phân bổ lại thời gian chạy jobs nếu business cho phép.
4. Giảm write amplification do quá nhiều indexes.
5. Tối ưu update predicates, batch sizes và network round trips.
6. Chọn admission control/load shedding cho traffic không quan trọng.
7. Tạm hoãn background job có tác động lớn.
8. Tăng capacity có cân nhắc để giảm CPU/IO bottleneck trong thời gian xử lý.
9. Kiểm tra migrations đang khiến hot shard vừa xử lý writes vừa copy data.
10. Ghi rollback và monitor p95/p99, error rate.

### 22.1. Không giảm write concern tùy tiện

Không đổi từ `majority` sang `w:1` chỉ để benchmark tốc độ hơn nếu business cần durability/consistency. Cũng không disable journaling/TLS/auth để tăng throughput.

### 22.2. Không kill operations theo duration duy nhất

Một aggregation/transaction/index build có thể chạy lâu hợp lệ. Nếu phải can thiệp, xác định owner và consequences trước.

---

## 23. Giải quyết scatter-gather bằng query patterns

Nếu shard key `{tenantId:1,eventId:"hashed"}`, một endpoint:

```javascript
db.events.find({ status: "FAILED" });
```

có thể broadcast toàn cluster.

### 23.1. Thêm context shard key vào API

Nếu business request luôn thuộc tenant A và một event ID:

```javascript
db.events.find({
  tenantId: "A",
  eventId: "event-42"
});
```

Có full equality shard key và phù hợp targeted routing.

### 23.2. Khi chỉ có tenantId

```javascript
db.events.find({
  tenantId: "A",
  status: "FAILED"
});
```

Filter theo **prefix** giúp router giới hạn phạm vi theo key, nhưng nếu tenant A được phân tán nhiều ranges/shards thì truy vấn vẫn có thể tới nhiều shards. Đây là đánh đổi giữa **phân tán writes trong tenant** và **truy vấn list toàn tenant**.

### 23.3. Không được thêm tenantId giả

Không lấy tenantId từ query parameter chưa xác thực rồi dùng làm shard key. Tenant scope phải đến từ authenticated principal/authorization context; nếu không bạn chỉ tối ưu được một lỗ hổng bảo mật.

### 23.4. Query không có shard key cần chiến lược khác

Các lựa chọn:

- Secondary index cho local query efficiency, dù scatter còn.
- Pre-aggregated/reporting collection theo key phục vụ analytics.
- Thay API để nhận partition key/tenant/time scope hợp lý.
- Chuyển global search sang công cụ tìm kiếm thích hợp nếu yêu cầu.
- Cân nhắc materialized views/OLAP pipeline tách khỏi OLTP cluster.
- Batching/async jobs và cache có invalidation đúng.
- Reshard với key dựa trên query patterns, nếu phù hợp toàn workload.

Không có phương án miễn phí: thêm field shard key vào mọi request có thể không khả thi cho global admin query; cần hỗ trợ workload scatter có chủ đích trong capacity planning.

---

## 24. Index tốt trên shards vẫn chưa đủ

Ví dụ sharded collection theo `{eventId:"hashed"}`:

```javascript
db.events.createIndex({ status: 1, createdAt: -1 });
```

Query:

```javascript
db.events.find({
  status: "FAILED"
}).sort({ createdAt: -1 }).limit(20);
```

`mongos` không tự suy từ local status index ra shard nào chứa status FAILED. Nó có thể phải hỏi **mọi shards**, mỗi shard dùng local index rồi merge/sort results.

### 24.1. Hai câu hỏi phải đặt

1. **Routing:** Query target bao nhiêu shards?
2. **Execution per shard:** Mỗi shard scan bao nhiêu index keys/documents, có sort stage không?

Tối ưu local index mà không tối ưu fan-out có thể cải thiện per-shard cost nhưng không giảm số shard-level operations.

### 24.2. Khi `limit`/`sort` scatter

Một distributed sort/limit có thể yêu cầu các shards tạo candidate results rồi `mongos`/merge shard tổng hợp. Không mặc định `limit(20)` đảm bảo chỉ có 20 documents được xét trên toàn cluster; hãy đọc Explain.

### 24.3. Index skew

Nếu một shard chứa nhiều docs của một hot tenant, index size và cache pressure trên shard đó có thể cao hơn; không chỉ đo collection data bytes. So index sizes, eviction, disk IOPS và memory per shard.

---

## 25. Java Driver: viết query có shard key đúng

Java Sync Driver ví dụ:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;

import org.bson.Document;

import static com.mongodb.client.model.Filters.*;

public class ShardingRoutingDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException("MONGODB_URI required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("hotspot_lab");
            MongoCollection<Document> events =
                db.getCollection("events_hashed");

            // Full equality trên shard key {eventId: "hashed"}.
            Document targeted = events
                .find(eq("eventId", "event-42"))
                .first();

            System.out.println(
                targeted == null ? "not found" : targeted.toJson()
            );

            // Thiếu shard key, có thể scatter-gather.
            events.find(eq("status", "FAILED"))
                .limit(20)
                .forEach(doc ->
                    System.out.println(doc.getString("eventId"))
                );
        }
    }
}
```

**Quan trọng:** `events_hashed` phải thực sự được sharding theo `{eventId:"hashed"}` trong lab; nếu là collection unsharded, hai queries không minh họa mongos fan-out.

### 25.1. Không tạo MongoClient mỗi request

Tái sử dụng singleton `MongoClient` trong service. Mỗi instance có connection pools và monitoring connections; tạo client liên tục làm tăng connection churn mà không sửa hotspot.

### 25.2. Read preference không thay routing shard key

Đổi `primary` sang `secondaryPreferred` thay member phục vụ **read** trong shard, nhưng không làm query thiếu shard key trở thành targeted hay giảm số shards logical được hỏi. Ngoài ra phải chấp nhận replication lag/read consistency semantics.

---

## 26. Spring Data MongoDB: derived query có thể vô tình scatter

Entity:

```java
@Document("events")
public class EventDoc {
    @Id
    private String id;
    private String tenantId;
    private String eventId;
    private String status;
    private Instant createdAt;
    // Constructors/getters/setters...
}
```

Repository:

```java
public interface EventRepository
        extends MongoRepository<EventDoc, String> {

    Optional<EventDoc> findByEventId(String eventId);

    List<EventDoc> findByStatus(String status);

    List<EventDoc> findByTenantIdAndStatus(
        String tenantId,
        String status
    );
}
```

Giả sử collection sharded theo `{eventId:"hashed"}`:

| Method | Routing kỳ vọng |
| --- | --- |
| `findByEventId` | Equality hashed key, thường targeted |
| `findByStatus` | Thiếu key, thường scatter |
| `findByTenantIdAndStatus` | Thiếu `eventId`, thường scatter |

Giả sử shard key khác: `{tenantId:1,eventId:"hashed"}`:

| Method | Routing kỳ vọng |
| --- | --- |
| `findByEventId` | Thiếu tenantId prefix, có thể scatter |
| `findByTenantIdAndStatus` | Có prefix tenantId, có thể prune subset, không chắc một shard |
| Query đủ tenantId+eventId | Thường targeted một shard |

**Điểm cốt lõi:** Spring Data repository method **không tự biết business intent “query này phải targeted”**; nó tạo MongoDB filter. Cần đọc sharding metadata và Explain của query cuối.

### 26.1. @Query và field mappings

```java
@Query("{ 'tenantId': ?0, 'eventId': ?1 }")
Optional<EventDoc> findScopedByEventId(
    String tenantId,
    String eventId
);
```

Nếu tenant scope hợp lệ theo auth context, method này có thể target compound key `{tenantId:1,eventId:"hashed"}`.

Với `@Field("tenant_id")` hoặc BSON field khác Java property, Spring Data mapping cần được xác minh; `mongos` route theo **BSON shard key fields**, không theo Java variable names.

### 26.2. N+1 query ở application có thể gây fan-out lớn

Nếu service duyệt 500 events rồi gọi `findByStatus(...)` 500 lần, mỗi call scatter 8 shards, application có thể gây fan-out rất lớn. Gom requests, dùng đúng access patterns, cache hoặc materialized read model khi thích hợp.

### 26.3. `@Aggregation` cần `$match` sớm

Với pipeline:

```javascript
[
  { $match: { tenantId: "A", eventId: "event-42" } },
  { $project: { _id: 0, status: 1 } }
]
```

Đưa filter shard key phù hợp ở đầu pipeline giúp mongos có cơ hội target tốt. Nhưng aggregation optimizer/merge stages có nhiều điều kiện; phải dùng Explain, không chỉ dựa vị trí `$match`.

---

## 27. Lab an toàn: chuẩn bị sharded test cluster

**Yêu cầu:** bạn đã có một **MongoDB sharded test cluster** với ít nhất hai shards và quyền quản trị cần thiết. Đây không phải bài hướng dẫn dựng production sharded topology từ đầu.

Không dùng database production. Trong `mongosh`, xác nhận đang đi qua `mongos`:

```javascript
db.adminCommand({ hello: 1 }).msg;
// "isdbgrid"
```

Dùng database lab:

```javascript
const lab = db.getSiblingDB("hotspot_lab");

lab.events_range.drop();
lab.events_hashed.drop();
```

**Cảnh báo:** hai lệnh `drop` xóa data/indexes của collections lab. Chỉ thực hiện nếu bạn chắc chắn đang ở cluster/test database được phép.

### 27.1. Sharding collections trên empty collections

```javascript
sh.enableSharding("hotspot_lab");

sh.shardCollection(
  "hotspot_lab.events_range",
  { createdAt: 1 }
);

sh.shardCollection(
  "hotspot_lab.events_hashed",
  { eventId: "hashed" }
);
```

Trong một số MongoDB versions, `sh.enableSharding` không cần thực hiện riêng hoặc có behavior khác; kiểm tra response và sharding state theo version.

- Range collection: shard key `createdAt`, tăng theo thời gian.
- Hashed collection: shard key `eventId`, phân tán hơn nếu IDs đủ đa dạng.

**Lưu ý quan trọng về initial layout:** empty range-sharded collection có thể bắt đầu với một range lớn; hashed sharding có thể có pre-split/initial distribution theo shard count/zone conditions. Sau khi insert vài nghìn documents, dữ liệu có thể chưa lớn đủ để kích hoạt balancer. Kết quả shard distribution trong lab không nhất thiết phân bố đều ngay.

### 27.2. Không đưa toàn bộ ví dụ vào shell production

Dù collection tên `hotspot_lab`, người dùng vẫn phải xác minh cluster URI và quyền. Thao tác tạo/shard/drop collection có ảnh hưởng metadata và tài nguyên.

---

## 28. Lab: seed dữ liệu và quan sát write hotspot

Trong `mongosh` kết nối `mongos`:

```javascript
const lab = db.getSiblingDB("hotspot_lab");
const startMs = Date.parse("2026-11-14T00:00:00Z");

for (let base = 0; base < 4000; base += 200) {
  const docs = [];

  for (let i = base; i < base + 200; i++) {
    docs.push({
      _id: "id-" + i,
      eventId: "event-" + i,
      tenantId: i % 10 === 0 ? "B" : "A",
      status: i % 20 === 0 ? "FAILED" : "OK",
      createdAt: new Date(startMs + i * 1000),
      value: i % 100
    });
  }

  lab.events_range.insertMany(docs);

  lab.events_hashed.insertMany(
    docs.map(x => ({ ...x }))
  );
}
```

Đây là **4.000 documents mỗi collection**, có `createdAt` tăng, `eventId` đa dạng, tenant A nhận khoảng 90% documents và status FAILED khoảng 5%.

### 28.1. So counts

```javascript
lab.events_range.countDocuments({});
lab.events_hashed.countDocuments({});
// Cùng khoảng 4000 documents nếu insert thành công.
```

### 28.2. Xem shard key metadata

```javascript
sh.status(true);
```

Xác định `hotspot_lab.events_range` có key `{createdAt:1}` và `events_hashed` có `{eventId:"hashed"}`.

### 28.3. Xem data distribution

```javascript
sh.getShardedDataDistribution()
  .filter(x =>
    x.ns === "hotspot_lab.events_range" ||
    x.ns === "hotspot_lab.events_hashed"
  );
```

Không mặc định kết quả phải 33/33/34 hoặc 50/50: dung lượng lab nhỏ hơn threshold balancing, initial placement có thể khác; đây là **lab học quan sát** chứ không phải benchmark hotspot chính xác.

### 28.4. Vì sao không tăng lên hàng triệu writes trong bài?

Sinh tải lớn trên shared cluster có thể gây resource contention, chi phí, replication lag và làm phiền team khác. Muốn benchmark thực, tạo performance environment, load generator được phê duyệt, plan cleanup và giới hạn budget.

---

## 29. Lab: targeted và scatter-gather trên hashed collection

### 29.1. Query equality có shard key

```javascript
const lab = db.getSiblingDB("hotspot_lab");

lab.events_hashed
  .find({ eventId: "event-42" })
  .explain("executionStats");
```

Với `{eventId:"hashed"}`, equality trên field này thường cho phép targeted một shard.

### 29.2. Query thiếu shard key

```javascript
lab.events_hashed
  .find({ status: "FAILED" })
  .limit(20)
  .explain("executionStats");
```

Filter `status` không cho `mongos` suy ra `eventId` hash; thường phải broadcast. Kể cả khi có index status, vẫn cần xem fan-out.

### 29.3. Range query trên original hashed field

```javascript
lab.events_hashed
  .find({
    eventId: {
      $gte: "event-100",
      $lt: "event-200"
    }
  })
  .explain("executionStats");
```

Hashed key không bảo toàn lexicographic/range order của giá trị gốc. Truy vấn range này thường khó prune shards hiệu quả.

### 29.4. Query time range trên range-sharded collection

```javascript
lab.events_range
  .find({
    createdAt: {
      $gte: ISODate("2026-11-14T00:10:00Z"),
      $lt: ISODate("2026-11-14T00:20:00Z")
    }
  })
  .explain("executionStats");
```

Range key có thể prune một subset ranges/shards, nhưng với layout nhỏ hoặc nhiều ranges trải shards vẫn có thể tới nhiều shards.

### 29.5. Bảng báo cáo thực nghiệm

| Query | Shard key | Dự đoán | Quan sát thật |
| --- | --- | --- | --- |
| `eventId = event-42` | Hashed eventId | Targeted | Điền từ Explain |
| `status = FAILED` | Hashed eventId | Scatter | Điền từ Explain |
| `eventId range` | Hashed eventId | Scatter/ít pruning | Điền từ Explain |
| `createdAt range` | Ranged createdAt | Có thể prune | Điền từ Explain |
| `tenantId = A` | Ranged createdAt | Scatter | Điền từ Explain |

Không dựa vào một dòng latency; so shards targeted, docs examined, keys examined, sort/merge và traffic.

---

## 30. Lab: đánh giá candidate shard keys bằng Analyzer

Trong **test cluster 7.0+ có quyền cần thiết**, bật query sampling trên một collection:

```javascript
const events = db.getSiblingDB("hotspot_lab").events_hashed;

events.configureQueryAnalyzer({
  mode: "full",
  samplesPerSecond: 1
});
```

Tạo workload nhỏ (lab):

```javascript
for (let i = 0; i < 100; i++) {
  events.findOne({ eventId: "event-" + (i % 80) });
  events.find({ tenantId: "A", status: "FAILED" })
    .limit(5).toArray();
}
```

Sau đó xem report:

```javascript
printjson(
  events.analyzeShardKey({ eventId: "hashed" })
);
```

Khi đủ samples/đúng version, report có thể chứa key characteristics và read/write distribution. Nếu thiếu distribution, xem sampling config, số queries, privilege, topology và sampling limitations.

**Dừng sampling sau bài:**

```javascript
events.configureQueryAnalyzer({ mode: "off" });
```

### 30.1. Candidate key khác

Đánh giá thêm trên test collection và điều kiện tương thích:

```javascript
events.analyzeShardKey({ tenantId: 1 });
```

Kết quả có thể cho thấy heavy tenant A có frequency rất cao.

Đừng lấy một sample nhỏ làm quyết định cuối cho production: cần workloads peak, batch imports, long-running reports và future growth projections.

---

## 31. Lab: đo sự khác nhau giữa data skew và workload skew

Một mô phỏng minh họa:

```text
Data distribution:
  Shard A: 2.0 GB
  Shard B: 2.1 GB
  Shard C: 1.9 GB

Write throughput:
  Shard A: 800 ops/s
  Shard B: 120 ops/s
  Shard C: 80 ops/s
```

### Câu hỏi

1. Data bytes có mất cân bằng đáng kể không?
2. Write distribution có lệch không?
3. Balancer có chắc giải quyết write skew không?
4. Cần kiểm tra key characteristics và query shapes nào?

**Đáp án định hướng:** bytes gần cân bằng, writes tập trung A. Balancer quản lý data ranges theo thresholds; không thể chia được một single hot shard-key value chỉ bằng cách chuyển ranges. Cần phân tích frequency/monotonicity và candidate key.

### 31.1. Không quy lỗi sharding chỉ vì CPU cao

CPU cao trên A còn có thể do:

- Một aggregation độc lập.
- Index build/checkpoint.
- Secondary replication hoặc recovery.
- TTL cleanup.
- Orphan range deletion.
- Stuck transaction hoặc application retry.
- Các unsharded collections có primary shard A.

Đối chiếu ops/s, namespace activity, logs, migrations và query profiler trước khi kết luận shard key là thủ phạm.

---

## 32. Trường hợp scatter-gather và shard chậm nhất

Giả sử một request scatter tới ba shards:

```text
Shard A: 15ms
Shard B: 210ms  <-- đang hot vì writes
Shard C: 18ms
Merge/network overhead: ...
```

Client latency có thể chịu ảnh hưởng lớn bởi shard B (khoảng lớn nhất trong fan-out) cộng thêm merge/network. Không thể ước lượng đơn giản bằng trung bình `(15+210+18)/3`.

### 32.1. Tăng shard count có thể tăng fan-out

Nếu query vẫn broadcast toàn cluster, thêm shards tăng số participants dù mỗi shard có thể chứa ít dữ liệu hơn. Hiệu năng cuối có thể tốt hơn hoặc tệ hơn tùy parallelism, network, merge, index, skew và load. **Không tuyên bố số shards tăng thì query scatter luôn chậm hơn**; phải đo.

### 32.2. Per-shard index quan trọng

Khi scatter là business requirement (global analytics), tối ưu local filters/projections, aggregation pipeline và merge cost. Nên đo:
- `docsExamined` per shard.
- `keysExamined` per shard.
- Returned candidates per shard.
- Sort/merge stages.
- CPU/cache/network.
- p95/p99 và error rate.

### 32.3. Không dùng lệnh count thiếu giới hạn trên production

Một global `countDocuments({})` hoặc aggregation không filter có thể hỏi nhiều shards và tiêu thụ tài nguyên. Với dashboard định kỳ, cân nhắc precomputed counters hoặc analytics system theo use case.

---

## 33. Runbook remediation theo nguyên nhân

| Bằng chứng | Nguyên nhân có khả năng | Hành động ngắn hạn | Hành động dài hạn |
| --- | --- | --- | --- |
| 90% inserts tới newest range | Monotonic ranged key | Throttle import, giảm burst | Reshard/compound hashed candidate |
| 80% writes một tenantId | Heavy hitter | Per-tenant rate limit | Phân vùng within-tenant bằng key mới |
| Chunk count đều nhưng bytes lệch | Different range density | Xem migration thresholds/zone | Refine/reshard nếu cần |
| Balancer off, skew tăng | Balancer bị tắt | Xem maintenance/change owner | Bật theo policy, monitor |
| Balancer on, jumbo warnings | Indivisible range | Điều tra logs/size | Refine/reshard; Support |
| Zone APAC hot | Residency + traffic skew | Cân bằng capacity trong zone | Thiết kế zone/key/capacity |
| API query thiếu shard key | Scatter-gather | Index/local optimization, cache | Query rewrite/read model |
| Per-shard IXSCAN nhưng vẫn p99 cao | Fan-out + slowest shard | Throttle + isolate workloads | Targeting/data model |
| Added shard nhưng data chưa dịch | Threshold/placement | Theo dõi balancer | Same-key redistribute nếu phù hợp 8.0 |
| Unsharded collection hot ở primary shard | Unsharded data | Kiểm tra job/resources | Shard collection với key phù hợp |
| Sudden lag trong migration | Data copy/replication pressure | Giảm competing batch | Migration scheduling/capacity |

**Không phải hành động nào trong bảng cũng được làm trực tiếp khi incident đang xảy ra.** Nếu ảnh hưởng tới metadata, shard key hoặc data placement, phải có change approval, backup/restore strategy, canary/benchmark và owner.

---

## 34. Chọn candidate shard key: scorecard

Giả sử ứng dụng event ingestion:

```text
80% operations: insert events
15% operations: find event by eventId
 5% operations: tenant time range analytics
```

Ba candidates:

| Candidate | Writes distribution | Point lookup | Tenant time range | Rủi ro |
| --- | --- | --- | --- | --- |
| `{createdAt:1}` | Monotonic hotspot | Thường scatter | Có thể target theo time | Hot tail |
| `{eventId:"hashed"}` | Thường phân bố tốt | Targeted equality | Thường scatter | Analytics fan-out |
| `{tenantId:1,eventId:"hashed"}` | Có thể chia hot tenant | Targeted full key | Fan-out trong tenant | Key complexity |

Không quyết định chỉ từ tỷ lệ operations; cần xem bytes/IO per operation, SLOs và business consistency.

### 34.1. Bài toán heavy tenant

Nếu tenant A có 80% traffic, hashed `tenantId` đơn lẻ vẫn không chia một tenant. Compound key có suffix phân tán có thể giúp nhưng làm per-tenant queries phải target nhiều shards. Cần đo real workload.

### 34.2. Các ràng buộc cần giữ

- Index/unique constraints: MongoDB sharded collections có quy tắc riêng về unique indexes và shard key prefix.
- Transactions và shard key updates có restrictions và overhead.
- Shard key values có thể không có ở legacy docs.
- Query patterns và pagination phải có sort/filter phù hợp.
- Zone ranges có business/compliance constraint.
- Resharding cần đủ storage, compute, network và oplog/replication health.

---

## 35. Khi nào nên reshard, khi nào không?

**Nên cân nhắc** khi:

- Hot key/range đã được chứng minh gây p95/p99 regression.
- Balancer không giải quyết được vì cardinality/frequency.
- Workload query thường xuyên scatter do key không phù hợp.
- Có candidate key được phân tích bằng samples và benchmark.
- Có nguồn lực thực hiện migration, monitor và rollback.

**Chưa nên** chỉ vì:

- Số chunks không bằng nhau.
- Một biểu đồ CPU lên cao trong 30 giây.
- Một collection nhỏ chưa phân bố đều ngay sau shardCollection.
- Có một query analytics scatter chạy vài lần mỗi ngày nhưng đáp ứng SLO.
- Zone compliance cố ý khiến bytes lệch.
- Chưa có baseline, sampling, load tests hoặc migration plan.

### 35.1. Độ rủi ro của reshardCollection

Resharding thay data placement/shard key, tạo nhiều công việc đọc/ghi và có giai đoạn commit. Một số giai đoạn không thể abort sau khi commit bắt đầu theo MongoDB docs.

Plan phải có:

1. MongoDB version/prerequisites.
2. Current key, candidate key, indexes.
3. Data size và bandwidth/storage headroom.
4. Business SLO/maintenance window.
5. Migration observability và progress.
6. Cơ chế xử lý concurrent writes.
7. Rollback/backout strategy theo giai đoạn.
8. Phương án khi commit/migration fail.
9. Benchmark trước/sau.
10. Owner/on-call/approval.

Không trình bày `reshardCollection` như thao tác an toàn “copy một lệnh là xong”.

---

## 36. Dashboard tối thiểu cho sharded cluster

### 36.1. Workload per shard

| Metric | Tại sao? |
| --- | --- |
| Insert/update/delete ops/s | Tìm write hotspot |
| Read ops/s | Tìm read hotspot |
| CPU per primary | Bão hòa compute |
| Disk read/write IOPS, latency | Storage bottleneck |
| WiredTiger cache used/dirty/evictions | Working-set và eviction pressure |
| Network in/out | Scatter results, replication, migrations |
| Connection count | Driver/pool fan-out |
| Replication lag | Write/migration pressure |

### 36.2. Sharding metadata

| Metric | Tại sao? |
| --- | --- |
| Owned docs/bytes per collection per shard | Data skew |
| Number of ranges/chunks | Placement granularity |
| Orphaned docs | Migration cleanup |
| Balancer status/migrations | Data movement |
| Jumbo/indivisible ranges | Không thể split/move bình thường |
| Zone assignments | Data residency/allowed placement |
| Scatter/targeted query proportions | Query routing efficiency |
| Shard Key Analyzer read/write distribution | Key design |

### 36.3. Application metrics

| Metric | Tại sao? |
| --- | --- |
| API p50/p95/p99 | User SLO |
| Throughput/RPS | Load |
| Errors/timeouts/retries | Availability |
| Driver pool checkout waits | Client-side bottleneck |
| Query shapes/command durations | Tìm top costly queries |
| Tenant/region/endpoint breakdown | Hot tenant, regional skew |
| Deployment/batch markers | Correlate changes |

### 36.4. Giữ timestamps đồng nhất

Ghi sự kiện theo UTC, đồng bộ clock/NTP, chú ý granularity/sampling. Một spike 1 phút có thể biến mất trên biểu đồ theo giờ.

---

## 37. Bảo mật và ổn định khi chẩn đoán

- Chỉ dùng monitoring account với quyền tối thiểu; các lệnh admin/Analyzer có roles riêng.
- Không in raw query literals chứa tenant IDs/PII lên shared dashboard.
- Không chia sẻ full Atlas URI có credentials.
- Không kết nối trực tiếp shard để bypass routing.
- Không sửa `config` metadata thủ công.
- Không bật profiler/sampling mức lớn tùy tiện.
- Không ép `moveChunk`/`forceJumbo` khi chưa có runbook vì có nguy cơ block writes.
- Không xóa orphan documents bằng application queries.
- Không dùng `drop()` hoặc `sh.shardCollection()` trên production database do nhầm tên.
- Giới hạn thời gian, sample rate và query volume khi benchmark.
- Đặt timeouts/rollback policies và owner cho mọi change.

**Nguyên tắc:** điều tra bắt đầu bằng **read-only metrics**, thay đổi configuration sau khi đã có bằng chứng và phê duyệt.

---

## 38. Những kết luận sai thường gặp

| Nhận định sai | Thực tế |
| --- | --- |
| “Sharding rồi thì writes tự cân bằng” | Shard key có thể tạo hotspot |
| “Data bytes đều nghĩa không có hot shard” | Workload skew khác data skew |
| “Một shard CPU cao chắc do shard key” | Có thể index build, job, TTL, migration |
| “Chunk count đều nghĩa dữ liệu đều” | Chunk sizes/densities khác |
| “Balancer chia đều writes/s” | Balancer chủ yếu di chuyển data ranges |
| “Balancer enabled thì không thể data skew” | Threshold, zones, jumbo, failures |
| “Hash tenantId giúp một tenant hot phân tán” | Một value hash thường vào một shard |
| “Cardinality cao chắc chắn good shard key” | Có thể monotonic |
| “Refine key ngay lập tức phân bố toàn data” | Không tự bảo đảm redistribution |
| “Thêm shard là sửa mọi hot key” | Một key vẫn có thể về một shard |
| “Same-key redistribution sửa key có frequency cao” | Không thay key cardinality |
| “Có status index thì query status targeted” | mongos route theo shard key |
| “Index tốt trên shards sẽ bỏ scatter-gather” | Hai bước routing/index khác |
| “_id lookup luôn targeted” | Không nếu _id không là shard key đủ điều kiện |
| “Filter có prefix chắc một shard” | Prefix có thể map nhiều shards |
| “Hashed shard key hỗ trợ tốt mọi range query” | Range locality giảm |
| “Scatter query luôn sai” | Analytics có thể chủ ý broadcast |
| “Scatter query latency bằng trung bình các shards” | Shard chậm nhất/merge đáng kể |
| “Tăng shards luôn giảm p99” | Fan-out/overhead và skew có thể tăng |
| “One Explain chứng minh p99 production” | Cần workload metrics |
| “Index hint là cách sửa vấn đề routing” | Hint tác động local plan, không tạo shard key |
| “Jumbo thì forceJumbo ngay” | Có thể block writes lâu |
| “Zone imbalance luôn là bug” | Có thể compliance policy |
| “mongosh standalone chứng minh routing” | Cần mongos trên sharded cluster |
| “MongoDB 8.0 cho chạy mọi command trực tiếp shard” | Một số direct shard commands bị chặn |
| “Shard key change không tác động app” | Query predicates/index/transaction semantics thay đổi |
| “Reshard command luôn rollback được” | Có commit phase constraints |
| “Orphan documents là corruption” | Có thể cleanup chưa xong |
| “Query sampling luôn đại diện” | Cần đủ samples và đúng time window |

---

## 39. Bài tập thực hành

### Bài 1 — Phân loại triệu chứng

Data bytes 34/33/33 nhưng writes 87/8/5. Đây là data skew hay workload skew?

**Đáp án:** Write workload skew; data tương đối đều.

### Bài 2 — Kết nối mongos

Lệnh nào giúp xác nhận client đang nối tới mongos? Giá trị `msg` nào cần nhìn?

**Đáp án:** `db.adminCommand({hello:1})`, `msg: "isdbgrid"`.

### Bài 3 — Chunk vs data

Vì sao 100 chunks trên mỗi shard không bảo đảm bytes bằng nhau?

### Bài 4 — Owned vs orphaned

Phân biệt `numOwnedDocuments` và `numOrphanedDocs`. Vì sao không xóa orphan thủ công?

### Bài 5 — Sharded Data Distribution

Viết lệnh `$shardedDataDistribution` trên admin DB, lọc namespace `commerce.orders`.

### Bài 6 — Write hotspot

Một shard key `{createdAt:1}` với thời gian tăng liên tục có rủi ro nào?

**Đáp án:** Ghi vào hot tail range, thường tập trung một shard tại một thời điểm.

### Bài 7 — Cardinality

Vì sao shard key chỉ có bốn status values là ứng viên kém?

### Bài 8 — Frequency

1.000 tenants nhưng một tenant tạo 80% writes. Vì sao cardinality 1.000 chưa đủ?

### Bài 9 — Hashed tenant

Hash `{tenantId:"hashed"}` có làm một tenant A được chia writes sang mọi shard không?

**Đáp án:** Không, một tenantId chỉ hash thành một giá trị.

### Bài 10 — Hashed eventId

Nếu eventId unique đa dạng, hashed key có ưu điểm và nhược điểm gì với time range reports?

### Bài 11 — Scatter-gather

Với key `{eventId:"hashed"}`, query `{status:"FAILED"}` thường route thế nào?

**Đáp án:** Broadcast/scatter nếu thiếu shard key.

### Bài 12 — Index chưa đủ

Thêm index `{status:1}` trên shards có biến query status thành targeted không?

**Đáp án:** Không; chỉ giúp execution tại mỗi shard.

### Bài 13 — Compound prefix

Với key `{tenantId:1,orderId:1}`, filter chỉ theo `orderId` có target được không?

### Bài 14 — Full equality

Với key `{tenantId:1,orderId:1}`, filter đủ hai field thường giúp gì?

### Bài 15 — Prefix

Query chỉ theo tenantId có chắc chỉ tới một shard không?

**Đáp án:** Không; có thể target subset shards.

### Bài 16 — Hashed range

Vì sao `{eventId:{$gte:"evt-10",$lt:"evt-50"}}` trên hashed shard key có thể scatter?

### Bài 17 — Explain

Trong Explain từ mongos, cần xem thông tin gì để biết query targeted hay broadcast?

### Bài 18 — Aggregation

Khi nào scatter-gather là lựa chọn có chủ đích và hợp lý?

### Bài 19 — Slowest shard

Scatter tới A=12ms, B=220ms, C=15ms. Vì sao client latency không bằng trung bình?

### Bài 20 — Balancer

Balancer cân bằng data hay CPU/writes per second?

**Đáp án:** Cân bằng data ranges theo policy/threshold, không trực tiếp cân bằng ops/s.

### Bài 21 — Balancer threshold

Với range size default 128 MB và ngưỡng chênh khoảng 3×, hãy giải thích vì sao chênh 100 MB có thể chưa trigger migration.

### Bài 22 — Jumbo

Một hot tenant có hàng triệu docs cùng một shard-key value. Vì sao chunk có thể indivisible?

### Bài 23 — ForceJumbo

Rủi ro chính khi cố move oversized/jumbo range là gì?

### Bài 24 — Zones

Vì sao data nằm 70% ở khu vực APAC không nhất thiết là lỗi balancer?

### Bài 25 — Refine

Khác nhau giữa `{tenantId:1}` và refined `{tenantId:1,eventId:1}` là gì? Điều gì không tự động xảy ra?

### Bài 26 — Reshard

Khi nào reshardCollection phù hợp hơn refineCollectionShardKey?

### Bài 27 — Same-key redistribution

MongoDB 8.0 `forceRedistribution:true` giải quyết trường hợp gì và **không** giải quyết gì?

### Bài 28 — Query Analyzer

Viết lệnh bật sampling 1 sample/s, analyze shard key và tắt sampling.

### Bài 29 — Sampling bias

Vì sao 200 samples trong giờ thấp điểm không chứng minh key tốt cho campaign peak?

### Bài 30 — Data vs workload

Một shard có bytes nhiều nhất nhưng CPU thấp, shard khác bytes ít hơn nhưng CPU cao. Bạn đo gì tiếp?

### Bài 31 — MongoDB Java Driver

Viết Java query equality trên `eventId` và một query chỉ filter status; so routing khi key hashed eventId.

### Bài 32 — Spring Data

Với key `{tenantId:1,eventId:"hashed"}`, viết repository method có đủ hai fields và giải thích sự khác nhau với `findByStatus`.

### Bài 33 — Security

Vì sao không cho client tự truyền tenantId bất kỳ chỉ để query được targeted?

### Bài 34 — Unsharded collection

Một database thuộc sharded cluster nhưng collection chưa sharded; nó có tự phân tán lên mọi shard không?

### Bài 35 — Migration logging

Các dấu hiệu stuck range migrations là gì? Nên xem logs và metrics nào?

### Bài 36 — Capacity

Thêm shard giúp điều gì và có thể không giúp gì khi single key hotspot?

### Bài 37 — P99 regression

Sau thêm shard, p99 global status query tăng. Hãy kiểm tra fan-out, per-shard indexes, merge và slowest shard.

### Bài 38 — Runbook ngắn hạn

Batch import gây 90% writes vào hot tail. Chọn hai cách giảm tải có thể triển khai mà không đổi shard key và mô tả rủi ro.

### Bài 39 — Index trade-off

Thêm nhiều indexes cho scatter query có thể tác động write hotspot thế nào?

### Bài 40 — Bài tổng hợp

Một collection events lớn đang sharded theo `{createdAt:1}`. App có:
- 80% writes theo timestamp mới.
- 15% point lookups theo eventId.
- 5% tenant time-range reports.
- Data size gần đều nhưng CPU 90/30/25.
- Một số global status reports scatter.

Hãy xây báo cáo:
1. Chứng cứ về hotspot, data distribution và fan-out.
2. Candidate keys và trade-offs.
3. Kế hoạch sampling/benchmark.
4. Hành động giảm tải ngắn hạn.
5. Phương án refine/reshard dài hạn nếu cần.
6. Migration/rollback constraints.
7. Metrics đánh giá sau triển khai.

---

## 40. Checklist production

### Chẩn đoán

- [ ] Đã xác định kết nối qua mongos, không truy cập thẳng shard để suy routing.
- [ ] Ghi namespace, shard key, number of shards, server version.
- [ ] Tách data skew khỏi write/read workload skew.
- [ ] Có per-shard ops/s, CPU, disk, cache, network.
- [ ] Có owned bytes/docs theo namespace.
- [ ] Có chunk/range count, zones, balancer status, orphan cleanup.
- [ ] Xác định monotonicity/cardinality/frequency của current key.
- [ ] Có query shapes và Explain số shards target.
- [ ] Đã xem application read/write request mix và tenant distribution.
- [ ] Có baseline p95/p99/errors/retries.

### Chọn giải pháp

- [ ] Không trông chờ balancer tự dàn writes/s.
- [ ] Không chọn hash tenantId khi một tenant chiếm phần lớn traffic mà chưa đo.
- [ ] Đánh giá hashed/ranged/compound shard keys theo cả read và write.
- [ ] Có Shard Key Analyzer samples ở thời gian đủ đại diện.
- [ ] Không dùng index hint để cố “sửa” query thiếu shard key.
- [ ] Có chiến lược targeted queries hoặc deliberate scatter cho analytics.
- [ ] Xem unique indexes, transactions, zones và data residency.
- [ ] Xem jumbo/indivisible ranges trước khi định manual migration.
- [ ] Thực hiện refine/reshard chỉ khi có benchmark và change approval.

### Rollout và vận hành

- [ ] Có MongoDB/Atlas version compatibility và feature requirements.
- [ ] Có backups và rollback/backout plan theo từng giai đoạn.
- [ ] Có resource headroom cho migrations/resharding.
- [ ] Có migration progress/replication lag/disk space monitoring.
- [ ] Có owner, on-call, incident timeline và change ticket.
- [ ] Không sửa config metadata trực tiếp.
- [ ] Không forceJumbo/chuyển zones khi chưa có runbook.
- [ ] Không bật sampling/profiler vô thời hạn.
- [ ] Có per-shard before/after metrics và API p95/p99.
- [ ] Đã đo tác động tới writes, reads, query routing, cache và network.

---

## 41. Tổng kết

Khi MongoDB đã sharding nhưng vẫn chậm, đừng mặc định “cần thêm shards”. Hãy phân biệt:

1. **Write hotspot:** một shard-key value/range nhận phần lớn writes. Nguyên nhân phổ biến là cardinality thấp, key frequency cao hoặc giá trị tăng đơn điệu.
2. **Data skew:** lượng owned data/ranges giữa shards lệch; dùng `$shardedDataDistribution`, `sh.status(true)` và quan sát balancer/zones/jumbo.
3. **Scatter-gather:** filter không đủ shard key để mongos route target; local indexes có thể làm từng shard nhanh hơn nhưng không đổi fan-out.
4. **Balancer cân bằng dữ liệu theo thresholds**, không phải hệ thống tự phân phối writes/s.
5. **Hashed sharding** có thể giảm monotonic hotspot, nhưng time-range queries thường khó prune; hash tenantId **không chia một heavy tenant duy nhất**.
6. **Refine/reshard** có thể sửa thiết kế shard key, nhưng cần phân tích sampled workload, index constraints, migration resources và rollback.
7. **Java/Spring Data** phải đưa shard-key predicates đúng theo business/authorization khi có thể; tên repository method không tự bảo đảm targeted routing.
8. **Kết luận dựa trên ba chứng cứ:** distribution per shard, query routing/Explain và end-to-end workload metrics.
9. **Chẩn đoán trước, giảm tải an toàn, thay đổi cấu trúc sau** là trình tự tốt cho incident production.

Câu hỏi cốt lõi luôn là:

> **“Vấn đề nằm ở phân bố dữ liệu, phân bố operations hay số shards mỗi truy vấn phải đi qua — và shard key có phục vụ đúng workload không?”**

### Tài liệu MongoDB chính thức

- [Sharding Introduction and Architecture](https://www.mongodb.com/docs/manual/sharding/) — mongos, shards, config servers, ranged/hashed sharding.
- [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/) — cardinality, frequency, monotonicity, query patterns.
- [Troubleshoot Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-troubleshooting-shard-keys/) — hot keys, jumbo, poor distribution.
- [Routing with mongos](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/) — targeted queries, broadcast/scatter-gather, aggregation merge.
- [Data Partitioning with Chunks](https://www.mongodb.com/docs/manual/core/sharding-data-partitioning/) — ranges, migrations, indivisible chunks.
- [Sharded Cluster Balancer](https://www.mongodb.com/docs/manual/core/sharding-balancer-administration/) — migration thresholds, balancing policies.
- [Manage Balancer](https://www.mongodb.com/docs/manual/tutorial/manage-sharded-cluster-balancer/) — supported administration options.
- [Troubleshoot Stuck Chunk Migrations](https://www.mongodb.com/docs/manual/troubleshooting/chunk-migrations-stuck/) — balancer and jumbo diagnostics.
- [sh.status()](https://www.mongodb.com/docs/manual/reference/method/sh.status/) — cluster metadata, chunk placement.
- [sh.getShardedDataDistribution()](https://www.mongodb.com/docs/manual/reference/method/sh.getshardeddatadistribution/) — owned/orphaned documents and bytes.
- [$shardedDataDistribution](https://www.mongodb.com/docs/manual/reference/operator/aggregation/shardeddatadistribution/) — distribution output from mongos admin.
- [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/) — hashed keys and range query trade-offs.
- [analyzeShardKey](https://www.mongodb.com/docs/manual/reference/command/analyzeshardkey/) — shard key characteristics and read/write distribution.
- [configureQueryAnalyzer](https://www.mongodb.com/docs/manual/reference/command/configurequeryanalyzer/) — query sampling.
- [refineCollectionShardKey](https://www.mongodb.com/docs/manual/reference/command/refineCollectionShardKey/) — extend shard key prefix.
- [reshardCollection](https://www.mongodb.com/docs/manual/reference/command/reshardcollection/) — change/redistribute shard key ranges.
- [Atlas Sharding Insights](https://www.mongodb.com/docs/atlas/sharding-advisor/) — per-shard metrics, distribution and balancer.
- [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — execution statistics.
- [Spring Data MongoDB Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — derived queries, @Query.
