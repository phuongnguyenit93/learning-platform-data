# mongostat, mongotop, Compass và công cụ giám sát Atlas trong MongoDB

## 1. Mục tiêu và bức tranh quan sát hệ thống

Một hệ thống MongoDB có thể vẫn nhận kết nối bình thường nhưng ứng dụng trả về rất chậm. Nguyên nhân có thể là truy vấn quét toàn collection, quá nhiều connections, disk bão hòa, cache bị áp lực, một collection có quá nhiều writes, secondary replication lag hoặc shard key gây phân bố tải không đều.

Câu hỏi đầu tiên khi điều tra không chỉ là “MongoDB còn sống không?” mà là:

- Tải tăng **ở node nào**, vào lúc nào và kéo dài bao lâu?
- Số insert/query/update/delete và network traffic thay đổi thế nào?
- **Collection nào** đang tiêu tốn nhiều thời gian đọc/ghi?
- **Query shape nào** chậm hoặc quét nhiều document?
- Hệ thống nghẽn CPU, memory, disk, network, queue hay connection pool?
- Replica set có secondary lag, election hoặc mất majority không?
- Có phải một thay đổi vừa triển khai đã gây ra sự cố?
- Monitoring có đưa ra cảnh báo trước khi ảnh hưởng người dùng không?

MongoDB có bốn công cụ thường được sử dụng cùng nhau:

1. **`mongostat`:** quan sát nhanh tình trạng một tiến trình `mongod` hoặc `mongos` theo khoảng lấy mẫu.
2. **`mongotop`:** đo tổng thời gian read/write theo collection/namespace trên một `mongod`.
3. **MongoDB Compass:** giao diện đồ họa có Performance và Explain Plan, giúp đọc các thống kê và truy vấn.
4. **MongoDB Atlas Monitoring:** biểu đồ lịch sử, Real-Time Performance Panel, Query Insights/Profiler, Performance Advisor, Sharding Insights, logs và alerts tùy cluster tier.

Bài học tập trung vào **chọn đúng công cụ, diễn giải đúng số liệu và thiết kế quy trình chẩn đoán**. Một metric đơn lẻ hiếm khi xác định được nguyên nhân.

### Kết quả đạt được

Sau bài này, bạn có thể:

- Chạy `mongostat`, `mongotop` từ terminal với interval và row count.
- Đọc throughput, WiredTiger cache, memory, active/queued clients, network và connections.
- Không nhầm **tổng thời gian read/write** ở `mongotop` với độ trễ của một query.
- Dùng Compass Performance và Explain Plan tìm nút thắt truy vấn.
- Phân biệt Atlas Metrics, RTPP, Query Profiler, Query Insights và Performance Advisor.
- Lập alert có điều kiện, owner, notification và runbook.
- Kết hợp `serverStatus`, `$currentOp`, `rs.status()` và `explain("executionStats")`.
- Điều tra sự cố chậm theo timestamp, node, collection, query shape và metrics trước/sau.

---

## 2. Nên dùng công cụ nào trước?

| Câu hỏi | Công cụ nên mở trước | Điều cần nhớ |
| --- | --- | --- |
| Hoạt động database tăng bất thường? | `mongostat`, Atlas Metrics | Có đơn vị và khoảng lấy mẫu |
| Connections/queue đang tăng? | `mongostat`, Atlas Metrics | Cần so với traffic và app connection pools |
| Collection nào nóng? | `mongotop`, Compass Performance, Atlas RTPP | Thời gian tích lũy khác latency |
| Query có dùng index không? | Compass Explain, `explain()` | Đọc cả keys/docs examined |
| Query nào chạy lâu ngay lúc này? | `$currentOp`, Compass Slowest Operations, RTPP | Phản ánh operations đang hoạt động |
| Query shape nào chậm trong vài ngày qua? | Atlas Query Insights/Profiler | Có sampling và retention |
| Có nên tạo index? | Performance Advisor + Explain + benchmark | Index cũng làm writes/storage tốn hơn |
| Replica set có vấn đề? | Atlas per-node metrics, `rs.status()` | Kiểm tra secondary và oplog |
| Shards phân bố tải ra sao? | Sharding Insights và per-shard metrics | Tùy Atlas tier và server version |
| Muốn được gọi khi disk sắp đầy? | Atlas Alerts | Cần threshold, owner, runbook |
| API p99 tăng dù MongoDB metrics bình thường? | App APM/tracing + DB metrics | DB chỉ là một phần request |

### 2.1. Metric, log, trace và explain không giống nhau

- **Metric:** số đo qua thời gian, ví dụ ops/s, CPU, connections, replication lag; tốt cho dashboard và alerts.
- **Log:** bản ghi sự kiện, ví dụ failover, authentication failure, slow operation; tốt cho timeline và điều tra.
- **Trace:** đường đi của một HTTP request qua application, driver, MongoDB và dịch vụ khác; tốt để tìm phần latency.
- **Profiler:** quan sát operation/query sample, giúp nhận diện query shape chậm.
- **Explain:** phân tích query plan và các thống kê thực thi khi chạy một truy vấn kiểm tra.

Một biểu đồ CPU cao không chứng minh thiếu index. Một query có `IXSCAN` cũng không chứng minh nó đã tối ưu.

---

## 3. Chuẩn bị MongoDB Database Tools

`mongostat` và `mongotop` thuộc **MongoDB Database Tools**. Đây là chương trình dòng lệnh hệ điều hành, không phải biểu thức JavaScript trong `mongosh`.

Kiểm tra:

```bash
mongostat --version
mongotop --version
mongosh --version
```

MongoDB Database Tools có chuỗi phiên bản riêng, thường là `100.x`. Version Database Tools không cần trùng MongoDB Server nhưng phải thuộc tập tương thích của deployment.

### 3.1. Chạy ở đâu?

- Trên máy quản trị hoặc bastion được phép kết nối đến `mongod`/`mongos`.
- Trong môi trường lab self-managed để học cú pháp.
- Với Atlas, có thể dùng tools qua network endpoint/TLS/credentials khi tính năng và quyền cho phép.
- Compass là ứng dụng GUI riêng; Atlas Monitoring có sẵn trong Atlas UI theo project.

**Không** tự mở MongoDB public network access chỉ để giám sát. Network segmentation, TLS và database roles vẫn phải được áp dụng.

### 3.2. Quyền hạn tối thiểu

`mongostat` dùng các thông tin như `serverStatus`; `mongotop` cần các quyền liên quan đến `serverStatus` và `top`. Role built-in **`clusterMonitor`** thường phù hợp cho giám sát self-managed nhưng cần kiểm tra deployment policy.

Xem operations của người khác qua `$currentOp` có thể cần privilege `inprog`; dừng operations cần quyền riêng như `killop`. Không cấp quyền đó cho mọi người chỉ xem dashboard.

**Atlas Project roles** và **MongoDB database roles** là hai tầng khác nhau. Project viewer có thể xem một số biểu đồ nhưng không tự có quyền tạo index hay chạy mọi lệnh admin.

### 3.3. Kết nối không lộ credentials

Môi trường lab không authentication:

```bash
mongostat --host=127.0.0.1:27017 --rowcount=5 1
mongotop --host=127.0.0.1:27017 --rowcount=5 1
```

Deployment yêu cầu authentication, nhập password qua prompt:

```bash
mongostat \
  --host=mongo1.example.net:27017 \
  --username=monitorUser \
  --authenticationDatabase=admin \
  --rowcount=10 2
```

Database Tools hỗ trợ các cơ chế TLS/CA và `--config` theo phiên bản. **Không ghi plaintext password vào URI trong log, repository hoặc shell history**, không tự tắt xác minh TLS để “sửa nhanh”.

---

## 4. mongostat: cái nhìn nhanh theo node

`mongostat` là công cụ theo dõi `mongod`/`mongos` định kỳ, gần với ý tưởng `vmstat` trên Linux.

Cú pháp:

```bash
mongostat [options] [polling-interval-seconds]
```

Ví dụ:

```bash
# Local MongoDB, mỗi giây một mẫu, chạy cho tới Ctrl+C.
mongostat

# Thu 12 mẫu, interval hai giây.
mongostat --host=127.0.0.1:27017 --rowcount=12 2

# Thu 10 mẫu, mỗi năm giây.
mongostat --rowcount=10 5
```

`--rowcount` xác định số mẫu hiển thị; số cuối là **khoảng lấy mẫu tính bằng giây**. Nếu bỏ row count, công cụ có thể tiếp tục đến khi người dùng dừng.

### 4.1. Mẫu output minh họa

```text
insert query update delete getmore command dirty used flushes vsize res qrw arw net_in net_out conn time
    15    46     12      1       4     3|0  1.2%  36%      0   2.7G 400M 0|0 4|1  100k   250k   40 10:00:00
    80   210     75      4       7     5|0  3.8%  59%      0   2.8G 445M 2|5 9|8  950k   1.2m   90 10:00:01
```

**Các số trên là ví dụ tưởng tượng**, không phải kết quả benchmark. Tên cột và format thay đổi tùy Database Tools/server version.

### 4.2. Operation counters

| Field | Ý nghĩa | Diễn giải |
| --- | --- | --- |
| `insert` | Số objects/documents inserted mỗi giây | Ingest burst hoặc batch import |
| `query` | Query operations mỗi giây | Không nhất thiết bằng số HTTP GET |
| `update` | Update operations mỗi giây | Batch updates hoặc ứng dụng ghi |
| `delete` | Delete operations mỗi giây | Cleanup, purge, TTL activity |
| `getmore` | Cursor getMore operations mỗi giây | Các lần fetch thêm batches |
| `command` | Command operations mỗi giây | Trên secondary có thể là `local|replicated` |
| `set` | Tên replica set nếu có | Nhận diện group |
| `repl` | Vai trò thành viên | PRI, SEC, REC, RTR... |

Trên một số giá trị, dấu `*` cho biết **replicated operation**. Ví dụ `*0` trên secondary không phải lỗi hoặc wildcard.

Một HTTP request có thể tạo nhiều database commands; còn một database query có thể được tái thử. Vì vậy **ops/s không bằng requests/s của ứng dụng**.

### 4.3. Cache và memory

| Field | Chính xác là gì? | Không phải là gì? |
| --- | --- | --- |
| `dirty` | % WiredTiger cache maximum gồm dirty bytes | % toàn bộ RAM máy |
| `used` | % WiredTiger cache maximum đang dùng | % tổng disk hoặc RAM hệ điều hành |
| `vsize` | Virtual memory size của process | RAM resident thực |
| `res` | Resident memory của process | Tổng memory của cả host/Search Nodes |
| `flushes` | Checkpoint events theo interval đối với WiredTiger | Số lần ghi document xuống disk |

Ví dụ `used=94%` **chưa đủ** để kết luận memory leak. WiredTiger cache được thiết kế để sử dụng bộ nhớ; phải kết hợp eviction behavior, disk I/O, query latency và OS free memory.

`dirty` tăng kéo dài cùng write latency và disk utilization có thể gợi ý áp lực checkpoint/disk, nhưng cũng cần thêm metrics trước khi kết luận.

### 4.4. Queues và active requests

Một số bản output dùng:

- `qr` / `qw`: read/write clients đang **chờ**.
- `ar` / `aw`: read/write clients đang **active**.
- `qrw` / `arw`: định dạng ghép `read|write`.

Ví dụ:

```text
qrw  arw
0|6  8|12
```

Đây là 0 readers đang chờ, 6 writers đang chờ; 8 active readers, 12 active writers theo format ví dụ. Queue tăng có thể là saturation, contention hoặc load burst. Cần so CPU/disk/latency để biết bottleneck thật.

### 4.5. Network và connections

| Field | Nghĩa |
| --- | --- |
| `net_in` / `netIn` | Bytes nhận, thường biểu diễn theo interval/format của utility |
| `net_out` / `netOut` | Bytes gửi |
| `conn` | Số open connections |

Nếu `conn` từ 200 tăng lên 3.000 sau deploy, những giả thuyết gồm: application tạo nhiều clients không tái sử dụng pool, số pod tăng, connection pool misconfiguration, retry storm, hoặc connection leak.

Không nên nâng tier ngay khi chưa xem app driver pool telemetry, connection limits và traffic.

### 4.6. Interval ảnh hưởng cách hiểu

Các chỉ số throughput trong `mongostat` được chuẩn hóa thành tốc độ **per second**, kể cả khi interval >1 giây. Với interval 5 giây, một burst 0,2 giây có thể bị làm mượt thành một giá trị trung bình.

- Khoảng 1s: tốt khi đang xem incident ngắn, output nhiều.
- Khoảng 5–10s: phù hợp nhìn xu hướng trong terminal.
- Atlas Metrics: tốt hơn cho dữ liệu lịch sử, nhưng có granularity và retention riêng.

---

## 5. mongostat nâng cao

### 5.1. Lấy nhiều members của replica set

```bash
mongostat \
  --host=mongo1.example.net:27017,mongo2.example.net:27017,mongo3.example.net:27017 \
  --rowcount=15 2
```

Dữ liệu các nodes phải được đọc theo vai trò PRI/SEC, network path và thời điểm lấy mẫu.

### 5.2. Khám phá topology với --discover

```bash
mongostat \
  --host=mongo1.example.net:27017 \
  --discover \
  --rowcount=15 2
```

`--discover` có thể khám phá **non-hidden replica set members**. Khi kết nối tới `mongos`, công cụ có thể thu statistics từ shards và members phù hợp.

**Không** cho rằng discovery đã bao phủ mọi hidden member hoặc host mà tài khoản không có quyền/truy cập mạng.

### 5.3. JSON output

```bash
mongostat --host=127.0.0.1:27017 --json --rowcount=5 1
```

JSON tiện cho lưu một trace giám sát lab, nhưng đừng tự coi field names là API bất biến qua mọi Database Tools versions.

### 5.4. Chọn thêm serverStatus fields

`-O` bổ sung field vào output mặc định:

```bash
mongostat \
  --host=127.0.0.1:27017 \
  -O='host,version,network.numRequests=Requests' \
  --rowcount=5 2
```

`-o` chỉ xuất những fields được chọn:

```bash
mongostat \
  --host=127.0.0.1:27017 \
  -o='host=Node,time=Time,network.numRequests=Requests' \
  --rowcount=5 2
```

Theo tài liệu, `-o` còn hỗ trợ `.rate()` và `.diff()` với `serverStatus` fields phù hợp. **Không sử dụng đồng thời `-o` và `-O`**.

```bash
mongostat --all --rowcount=5 2
mongostat --interactive
```

`--interactive` không dùng chung với `--json`.

### 5.5. Điều mongostat chưa trả lời

- Query nào làm counter tăng?
- Collection nào đang nóng?
- Một query cụ thể chạy bao lâu?
- p95/p99 latency của app?
- Historical trend của hôm qua?

Muốn trả lời, chuyển tiếp sang `mongotop`, Compass/Atlas Profiler hoặc app observability.

---

## 6. mongotop: collection nào tiêu thụ read/write time?

`mongotop` báo **thời gian thực hiện read/write theo namespace**, là góc nhìn collection-level của một `mongod`.

```bash
mongotop

mongotop --host=127.0.0.1:27017 --rowcount=10 2
```

Mặc định công cụ lấy mẫu mỗi giây. Quyền cần có gồm `serverStatus` và `top` theo tài liệu Database Tools.

### 6.1. Mẫu output

```text
ns                       total    read    write    timestamp
shop.orders              850ms   700ms   150ms    10:10:00
shop.sessions            430ms    30ms   400ms    10:10:00
shop.products             70ms    70ms     0ms    10:10:00
```

Số liệu **giả định**.

| Cột | Ý nghĩa |
| --- | --- |
| `ns` | Namespace `database.collection` |
| `total` | Tổng operation time được ghi nhận cho namespace |
| `read` | Tổng thời gian read operations |
| `write` | Tổng thời gian write operations |
| Timestamp | Thời điểm báo cáo |

### 6.2. Đừng nhầm tổng thời gian với latency

Một collection có 100 reads chạy cùng lúc, mỗi read khoảng 10 ms:

```text
100 × 10 ms = 1.000 ms tổng operation time
```

Vì các operations có thể chồng nhau, `mongotop.total` **có thể lớn hơn 1.000ms trong một khoảng 1s**. Nó không có nghĩa một query chạy hơn một giây, cũng không phải %CPU.

Muốn biết operation count hoặc latency của từng query, dùng JSON mode, Query Profiler và APM.

### 6.3. Namespace không xuất hiện

`mongotop` thường chỉ hiển thị namespace có activity trong sample. Nếu một collection không xuất hiện:

- Có thể không hoạt động trong khoảng đó.
- Có thể traffic phục vụ ở node khác.
- Có thể query đã hoàn thành giữa các mẫu.
- Có thể collection bị che bởi hạn chế tính năng/quyền trong công cụ GUI tương ứng.

Không kết luận collection đó chưa từng được dùng cả ngày.

### 6.4. JSON và --locks legacy

```bash
mongotop --host=127.0.0.1:27017 --json --rowcount=5 1
```

Tài liệu MongoDB mô tả JSON output còn có **số operations trong polling interval** bên cạnh read/write timings.

Tùy chọn `mongotop --locks` là tính năng **legacy** cho per-database lock usage trước MongoDB 3.0; trên các server mới nó có thể lỗi. **Không dùng `--locks` để suy lock contention trên MongoDB 8.x/9.x.**

### 6.5. mongotop trong sharded cluster

`mongotop` tập trung vào statistics của **một mongod**. Với sharded cluster, cần xem **nhiều shard members** hoặc Atlas per-shard charts/Sharding Insights. Một kết nối `mongos` không phải góc nhìn timing đầy đủ của mọi physical shard node.

---

## 7. Lab: tạo dữ liệu và tạo một query chưa có index phù hợp

Mở `mongosh` trên **database thử nghiệm**, không chạy `drop()` hoặc sinh tải nhân tạo trên production.

```javascript
const lab = db.getSiblingDB("observability_lab");
lab.events.drop();

const records = Array.from({ length: 2000 }, (_, i) => ({
  tenantId: i % 2 === 0 ? "A" : "B",
  eventId: "event-" + i,
  status: i % 10 === 0 ? "FAILED" : "OK",
  category: ["auth", "order", "payment", "search"][i % 4],
  createdAt: new Date(Date.UTC(2026, 10, 14, 0, 0, i % 3600)),
  durationMs: (i * 7) % 300,
  payload: { source: "demo", id: i }
}));

lab.events.insertMany(records);

lab.events.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "ix_tenant_createdAt" }
);

lab.events.countDocuments({});
// 2000
```

### 7.1. Query có index phù hợp

```javascript
lab.events.find({
  tenantId: "A",
  createdAt: {
    $gte: ISODate("2026-11-14T00:10:00Z")
  }
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
```

Index `(tenantId, createdAt)` có thể đáp ứng equality theo tenant, range và sort theo thời gian. Nhưng với 2.000 docs, optimizer đôi khi chọn plan khác; **phải xem actual explain**.

### 7.2. Query thiếu index theo status

```javascript
lab.events.find({ status: "FAILED" })
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
```

Ở thời điểm này chưa có index hỗ trợ tốt `status + sort(createdAt)`. Có thể phát sinh `COLLSCAN` và sort tốn chi phí.

### 7.3. Sinh một workload rất nhỏ để quan sát

Mở hai terminals:

```bash
# Terminal A
mongostat --rowcount=30 1

# Terminal B
mongotop --rowcount=30 1
```

Rồi chạy trong `mongosh` của **lab**:

```javascript
for (let i = 0; i < 100; i++) {
  lab.events.find({ status: "FAILED" })
    .sort({ createdAt: -1 })
    .limit(10)
    .toArray();
}

for (let i = 0; i < 50; i++) {
  lab.events.updateOne(
    { eventId: "event-" + i },
    { $inc: { durationMs: 1 } }
  );
}
```

`mongostat` có thể cho thấy tăng query/update operations; `mongotop` có thể cho thấy `observability_lab.events` có read/write time.

**Lưu ý:** Với data nhỏ, toàn bộ vòng lặp có thể hoàn thành rất nhanh và rơi giữa các lần polling. Không thấy spike không đồng nghĩa tool sai. Không tăng workload tới hàng triệu queries trên production để “cho biểu đồ có dữ liệu”.

### 7.4. Thêm index thử nghiệm, so lại Explain

```javascript
lab.events.createIndex(
  { status: 1, createdAt: -1 },
  { name: "ix_status_createdAt" }
);

lab.events.find({ status: "FAILED" })
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
```

So các mục:

- `winningPlan`.
- `totalKeysExamined`.
- `totalDocsExamined`.
- `nReturned`.
- Sort stage.
- `executionTimeMillis`.
- Ảnh hưởng tới write workload nếu thử nghiệm ở quy mô lớn hơn.

Index mới có thể tăng storage và write amplification. Không tạo trực tiếp trong production mà chưa kiểm chứng các query patterns khác.

---

## 8. Các lệnh bổ sung trong mongosh

### 8.1. serverStatus: counters theo node

```javascript
const admin = db.getSiblingDB("admin");
const s = admin.serverStatus();

printjson({
  uptime: s.uptime,
  connections: s.connections,
  opcounters: s.opcounters,
  network: s.network,
  opLatencies: s.opLatencies
});
```

Nhiều field trong `serverStatus` là **counters tích lũy từ khi process khởi động**, không phải tốc độ mỗi giây.

Muốn tính rate:

\[
\mathrm{rate}=\frac{\mathrm{counter}_2-\mathrm{counter}_1}{t_2-t_1}
\]

Nếu counter tăng 600 trong 10 giây thì tốc độ trung bình là 60/s. Không tính chênh lệch qua restart hoặc hai nodes khác nhau mà không ghi chú.

`opLatencies` có count/latency statistics theo operation type; không được coi một average là HTTP p95/p99.

### 8.2. top: operation time theo namespace

```javascript
db.getSiblingDB("admin").runCommand({ top: 1 });
```

Dữ liệu `top` là cơ sở của `mongotop`. Trên `mongod`, output thể hiện timing theo namespaces. Không gọi vào một node rồi suy ra kết quả tổng hợp toàn sharded cluster.

### 8.3. currentOp: những operations đang chạy

```javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      localOps: true
    }
  },
  {
    $match: {
      active: true,
      secs_running: { $gte: 2 }
    }
  },
  {
    $project: {
      opid: 1,
      ns: 1,
      op: 1,
      secs_running: 1,
      client: 1,
      waitingForLock: 1
    }
  }
]).toArray();
```

Ví dụ cần privilege phù hợp và được chạy ở deployment/role hỗ trợ. Các options/field names khác nhau theo MongoDB version và process role.

**Không tự kill một operation** chỉ vì `secs_running` cao: đó có thể là reporting job, backup, index build hoặc transaction hợp lệ.

### 8.4. rs.status và db.hello

```javascript
db.hello();

// Chỉ trên replica set với quyền phù hợp:
rs.status();
```

Dùng để xác định primary/secondary, member health, replication state và optimes. Một secondary phục vụ reads nhiều có profile khác primary.

### 8.5. explain

```javascript
lab.events.find({ status: "FAILED" })
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
```

Không nhầm `executionTimeMillis` của **một lần explain** với p99 lịch sử của ứng dụng.

---

## 9. MongoDB Compass: Performance qua GUI

MongoDB Compass là ứng dụng desktop chính thức để duyệt documents, indexes, schema, aggregations và query explain.

### 9.1. Mở Performance

Theo tài liệu Compass hiện hành:

1. Mở Compass và kết nối tới một deployment với credentials phù hợp.
2. Trong **Connections Sidebar**, mở menu cạnh tên connection.
3. Chọn **Performance**.
4. Quan sát charts và bảng, ghi lại timestamp/node.
5. Tìm Hottest Collections/Slowest Operations để tiếp tục điều tra.

Tên hoặc vị trí menu có thể thay đổi tùy Compass version; ưu tiên hướng dẫn theo phiên bản đang cài.

### 9.2. Các khu vực của Performance

| Khu vực | Nội dung | Nguồn so sánh |
| --- | --- | --- |
| Operations | Tốc độ database operations | `mongostat` |
| Read & Write | Active/queued reads và writes | `mongostat` |
| Network | Network/connections | `mongostat` |
| Memory | Cache/process memory metrics | `mongostat` |
| Hottest Collections | Collections có nhiều hoạt động | `mongotop` |
| Slowest Operations | Operations đang chạy chậm | `db.currentOp()` / `$currentOp` |

Compass có **Pause** để dừng cập nhật trên giao diện; nó **không pause MongoDB database**. Không dùng GUI Pause như một thao tác đóng băng dữ liệu hay backup.

### 9.3. Giới hạn

- Compass có **thông tin Performance hạn chế** khi kết nối tới `mongos`.
- Compass không thể lấy performance data cho collections dùng **Queryable Encryption** theo tài liệu hiện hành.
- Real-time Performance không tự giữ toàn bộ lịch sử tháng trước.
- Xem hoặc dừng operations đòi database privileges phù hợp; `killop` không nên cấp rộng.

---

## 10. Compass Explain Plan: xem query plan cụ thể

`mongostat` cho biết node đang có tải; `mongotop` cho biết collection nóng; **Explain** giúp tìm query cụ thể.

### 10.1. Quy trình thao tác

1. Mở collection `observability_lab.events` trong Compass.
2. Ở query bar, nhập Filter:

```javascript
{ status: "FAILED" }
```

3. Nhập Sort:

```javascript
{ createdAt: -1 }
```

4. Chọn **Explain**.
5. Xem **Visual Tree**.
6. Chuyển sang **Raw Output** để đọc execution details.
7. So sánh trước và sau khi có index `ix_status_createdAt`.

### 10.2. Đọc các chỉ số quan trọng

| Field/Stage | Nghĩa |
| --- | --- |
| `COLLSCAN` | Quét collection |
| `IXSCAN` | Quét B-tree index |
| `FETCH` | Đọc document sau index |
| `SORT` | Stage sort; có thể tốn memory |
| `totalDocsExamined` | Số documents được kiểm tra |
| `totalKeysExamined` | Số index keys được kiểm tra |
| `nReturned` | Số kết quả |
| `executionTimeMillis` | Thời gian của lần chạy explain, không phải p95 |
| `winningPlan` | Query execution plan được chọn |

### 10.3. Query targeting ratio

\[
\mathrm{DocsExaminedPerReturned} =
\frac{\mathrm{docsExamined}}{\mathrm{docsReturned}}
\]

Nếu scan 100.000 docs để trả 100 docs, ratio là **1.000 docs/result**.

Nếu `docsReturned=0`, không thể tính tỷ số thông thường; đừng báo ratio = vô hạn hay zero một cách máy móc.

**Ratio cao không luôn là lỗi:** analytics full-scan đôi khi là chủ đích. Cần xem request semantics và traffic.

### 10.4. IXSCAN không tự chứng minh tốt

```text
IXSCAN keysExamined=400,000
FETCH docsExamined=250,000
nReturned=5
```

Có index nhưng vẫn quét rất nhiều keys/docs. Kiểm tra compound index prefix, filter selectivity, collation, sort và phân bố dữ liệu.

### 10.5. Giới hạn Visual Tree

MongoDB Compass hiện **không hiển thị vector search queries dưới dạng Visual Tree** trong Explain. Với `$vectorSearch`, dùng output/methods được phiên bản hỗ trợ và Search metrics chuyên biệt.

---

## 11. Atlas Monitoring: nhìn hệ thống qua thời gian

Atlas cung cấp monitoring theo cluster, node, project và tính năng được hỗ trợ.

Nhóm công cụ chính:

- **Deployment Metrics:** charts lịch sử throughput, CPU, disk, memory, network, connections...
- **Real-Time Performance Panel (RTPP):** hoạt động gần realtime, slowest operations/hottest collections.
- **Query Insights:** query shapes và namespaces có slow-running queries.
- **Query Profiler:** chi tiết các sampled slow operations.
- **Performance Advisor:** gợi ý indexes từ workload.
- **Sharding Insights:** quan sát phân bố tải trên sharded cluster theo điều kiện.
- **Alerts:** conditions/thresholds và notification.
- **Logs, Administration API, Integrations:** phục vụ điều tra và pipeline giám sát ngoài Atlas.

### 11.1. Kiểm tra tier và quyền trước

Không phải feature nào cũng có trên mọi cluster:

- **RTPP**: tài liệu Atlas mô tả trên **M10+**.
- **Performance Advisor**: nhóm tính năng **M10+**.
- **Query Profiler/Query Insights**: phụ thuộc tier, role, feature/threshold và dữ liệu đang thu.
- **Sharding Insights**: tài liệu hiện hành nêu cho **M10+ sharded clusters, MongoDB 8.0+**.
- **Free/Flex**: metrics, retention và alerts có giới hạn riêng.

Nếu không tìm thấy menu, kiểm tra Atlas tier, project roles, server version và feature settings.

---

## 12. Atlas Deployment Metrics

Trong Atlas, chọn organization/project, mở cluster/deployment và phần **Metrics** theo UI đang dùng. Chọn khoảng thời gian tương ứng sự cố.

### 12.1. Nhóm metrics nên đọc

| Nhóm | Dấu hiệu đáng chú ý |
| --- | --- |
| Operations/s | Load tăng ngay sau deploy/batch job |
| CPU | Sustained saturation |
| Disk IOPS/latency | Read/write bottleneck |
| Cache & resident memory | Cache pressure, evictions |
| Connections | Connection storm/pool growth |
| Network In/Out | Payload lớn, read traffic, replication |
| Query Targeting | Quét quá nhiều docs so với results |
| Replication Lag | Secondary tụt khỏi primary |
| Oplog Window | Secondary recovery risk |
| Data/Index Size | Capacity và write amplification |
| Search Nodes nếu dùng | Search index RAM/disk/latency |

Các metric cụ thể khác theo cluster tier và MongoDB version.

### 12.2. Baseline quan trọng hơn một giá trị đơn

Giả sử CPU=75%:

- Cluster A thường 15–25%, vừa tăng lên 75% sau deployment: cần điều tra.
- Cluster B thường 60–80% lúc cao điểm, không có latency/error increase: chưa chắc sự cố.

Nên so với cùng giờ hôm trước, cùng thứ tuần trước và các sự kiện triển khai gần nhất.

### 12.3. Sampling và granularity

Một burst chỉ kéo dài 20 giây có thể biến mất trên chart được aggregate theo giờ. Khi điều tra:

- Dùng time range hẹp.
- Chọn granularity nhỏ nhất môi trường hỗ trợ.
- So với timestamp logs/profiler.
- Ghi rõ timezone (ưu tiên UTC).
- Không trộn dữ liệu 1 giây và giá trị trung bình 5 phút mà không ghi chú.

---

## 13. Atlas Real-Time Performance Panel

RTPP hiển thị performance gần thời gian thực trên Atlas deployments đủ điều kiện.

Thông tin có thể gồm:

- Connections, Network In/Out.
- CPU, Disk IOPS, System Memory.
- Operations.
- Query Execution Times.
- Query Targeting.
- Hottest Collections.
- Slowest Operations.
- Active/queued readers/writers.
- Replication lag tùy member/role.

### 13.1. Dùng RTPP khi ứng dụng đang chậm

1. Mở cluster RTPP trong Atlas.
2. Chọn node/shard hoặc phạm vi phù hợp.
3. Nhìn trend operations/CPU/IOPS/Network.
4. Mở **Hottest Collections** để tìm namespace có nhiều activity.
5. Mở **Slowest Operations** để xem operations đang lâu.
6. Đánh giá Query Targeting.
7. Ghi query shape/host/time, chuyển sang Profiler/Explain để phân tích sâu.

### 13.2. Giới hạn phạm vi

Theo Atlas Docs, RTPP lấy dữ liệu từ **primary replica set members**; với sharded clusters, từ primary của từng shard. Nó không thay thế việc quan sát secondary khi ứng dụng đọc bằng `secondaryPreferred`.

Một số dữ liệu có thể bị che/redact khi dùng Queryable Encryption. Quyền xem và quyền **Kill Op** khác nhau.

### 13.3. Kill Op cần quy trình

Nếu giao diện cho phép dừng operation, hãy xác định:

- Có phải operation business critical?
- Nó có liên quan backup/index build/transaction không?
- App có retry được không?
- Ai đang chịu trách nhiệm incident?
- Có phương án rollback/recovery?

**Không** kill operation chỉ vì thấy duration >1 giây.

---

## 14. Atlas Query Insights: query shape và namespace

Query Insights giúp phân tích **patterns của truy vấn chậm** thay vì chỉ các operations đang diễn ra.

### 14.1. Query shape

Hai lệnh:

```javascript
db.orders.find({ status: "NEW", tenantId: "A" });
db.orders.find({ status: "PAID", tenantId: "B" });
```

có thể được nhóm theo cùng một shape khi cấu trúc filter giống nhau. MongoDB/Atlas xác định query shape theo phiên bản/operation type; không tự giả định mọi thay đổi literal đều cho cùng shape.

### 14.2. Query Shape Insights

Có thể giúp:

- Xác định query shape nào có latency cao.
- Xem trend theo host/shard và time range.
- So một số shapes để nhận diện regression.
- Phân biệt query bất thường và truy vấn phổ biến.

### 14.3. Namespace Insights

Nhìn performance theo collection:

```text
shop.orders
shop.products
shop.sessions
```

Nếu `shop.orders` có latency tăng, mở query shapes tương ứng; một collection có thể chứa nhiều queries có cấu trúc và index needs khác nhau.

### 14.4. P95 sampled latency không phải HTTP p95

Atlas có thể cung cấp sampled P95 latency của slow query shapes trong Query Insights. Con số này **không nhất thiết bằng** p95 end-to-end API, vì app latency còn có:

- Network và serialization.
- Driver pool wait.
- Application CPU.
- Retries.
- External dependencies.
- Aggregation/LLM/reranking bên ngoài DB.

Phải có app APM/tracing để đánh giá user-facing SLO.

---

## 15. Atlas Query Profiler

Query Profiler tập trung vào những operations chậm được thu bởi Atlas. Trong UI hiện hành thường nằm ở cluster → **Query Insights** → **Query Profiler**.

### 15.1. Các field quan trọng

| Metric | Ý nghĩa |
| --- | --- |
| `millis` | Thời gian thực thi operation |
| `docsExamined` | Documents đã đọc để xử lý query |
| `nreturned` / Docs Returned | Kết quả trả |
| `keysExamined` | Index keys đã xem |
| `planSummary` | Tóm tắt plan như COLLSCAN hoặc IXSCAN |
| `numYields` | Số lần operation nhường quyền |
| Response Length | Payload kết quả |
| Docs/Keys Examined : Returned | Query targeting efficiency |

Ví dụ sample log **minh họa**:

```javascript
{
  ns: "shop.orders",
  millis: 270,
  planSummary: "COLLSCAN",
  docsExamined: 250000,
  keysExamined: 0,
  nreturned: 12
}
```

Ratio docsExamined/nreturned ≈ **20.833**. Đây là dấu hiệu cần xem query filters/indexes, không phải đủ bằng chứng để tạo index trực tiếp.

### 15.2. Sampling và retention

Profiler lưu **samples/history** tùy tier/feature; tài liệu Atlas hiện hành mô tả khả năng xem một số lịch sử query chậm trong khoảng gần đây, ví dụ tối đa **7 ngày** theo cơ chế hiện hành.

Không coi profiler là nơi lưu vĩnh viễn tất cả queries. Trong audit hoặc long-term trend, dùng logging/metrics pipeline theo retention policy.

### 15.3. Slow threshold có thể động

Atlas-managed slow query threshold có thể được điều chỉnh theo workload khi tính năng được bật. Vì vậy “slow” trên cluster A và B không nhất thiết có cùng giới hạn ms. Không so số lượng slow queries giữa hai clusters mà bỏ qua threshold và sampling.

### 15.4. Profiler khác Explain

- Profiler: **operation đã xảy ra** trong workload thật.
- Explain: **plan và execution stats** khi chạy truy vấn kiểm tra.

Quy trình tốt: Profiler → query shape/parameters → Explain trên môi trường thích hợp → index/query rewrite → đối chiếu production telemetry.

---

## 16. Atlas Performance Advisor

Performance Advisor dựa trên slow query workload để đề xuất indexes có khả năng cải thiện hiệu suất.

Có thể thấy:

- Index key pattern được đề xuất.
- Sample query shapes.
- Execution count.
- Average execution time.
- Query targeting.
- Docs scanned/returned.
- In-memory sort.
- Index ranking/drop recommendations tùy giao diện.

### 16.1. Tại sao không tạo mọi index?

Một index mới:

- Tăng disk/storage và cache usage.
- Tăng chi phí insert/update/delete.
- Tốn tài nguyên khi index build.
- Có thể trùng với index khác.
- Có thể không phù hợp collation/partial filter/multikey constraints.
- Có thể chỉ cải thiện một query hiếm gặp mà gây overhead thường xuyên.

**Advisor là gợi ý**, cần xem `explain`, workload và impact.

### 16.2. Không có đề xuất không nghĩa DB không có vấn đề

Performance Advisor phụ thuộc threshold, sampling và loại query. Một Query Targeting alert có thể xảy ra mà không có suggestion phù hợp. Ngoài thiếu index, bottleneck còn có CPU/disk, connection pool, network và application retries.

---

## 17. Atlas Alerts: từ biểu đồ thành hành động

Atlas Alerts cho phép tạo điều kiện theo metrics/events và gửi notification tới các kênh đã cấu hình. Khả năng và alert conditions phụ thuộc tier.

### 17.1. Một alert hữu ích cần đủ thành phần

```text
Name: Production MongoDB disk capacity risk
Target: production cluster
Condition: ngưỡng disk theo metric Atlas đang hỗ trợ
Duration: kéo dài Y phút
Severity: Warning / Critical
Owner: Platform On-call
Notifications: Email + PagerDuty
Runbook: link hướng dẫn đo time-to-full và xử lý capacity
```

`Y`, mức disk và severity phải dựa vào workload cụ thể. Các trường trong ví dụ là **mô tả thiết kế**, không phải cấu hình API để copy nguyên.

### 17.2. Nhóm alerts quan trọng

| Nhóm | Điều cần phát hiện | Bước đầu |
| --- | --- | --- |
| Disk space | Time-to-full ngắn | Xem data/index growth |
| CPU sustained high | Saturation | So load, query plans, background jobs |
| Connections | Pool gần giới hạn | Kiểm tra app pool/client count |
| Replica lag | Secondary tụt | Disk, network, writes, oplog window |
| Node unavailable | Mất member | Kiểm tra quorum/failover |
| Slow query targeting | Scan không hiệu quả | Profiler và Explain |
| Backup failure | Mất recovery coverage | Backup pipeline/retention |
| Network spike | Payload/traffic bất thường | App traffic/replication |
| Search capacity | Search index lag/resource pressure | Search metrics và version |

Không phải mọi dòng trong bảng là tên điều kiện tồn tại sẵn trên tất cả Atlas tiers; đối chiếu điều kiện thực tế trước khi tạo.

### 17.3. Giảm alert flapping và fatigue

- Dùng duration khi điều kiện hỗ trợ.
- Áp ngưỡng theo baseline.
- Tách warning/critical.
- Dùng maintenance window.
- Có on-call owner.
- Gộp những alerts cùng nguyên nhân.
- Có escalation và runbook.
- Kiểm tra notification channel thực sự nhận được.

Atlas có những tùy chọn “send if condition lasts at least” và resend cho **host alerts**, nhưng không phải mọi event-based alert đều hỗ trợ chúng.

### 17.4. Quyền và notifications

Atlas có các tích hợp như email, SMS, PagerDuty, Microsoft Teams và webhooks theo cấu hình. Quản lý project alerts cần role như **Project Owner** hoặc **Project Alerts Manager** khi được hỗ trợ.

Đừng gửi query literals có dữ liệu cá nhân qua webhook hoặc channel công khai.

---

## 18. Replica set: quan sát primary và secondary riêng

### 18.1. Những metrics quan trọng

- Primary/secondary health.
- Replication lag từng secondary.
- Optimes và oplog window.
- Elections và role changes.
- Read preference của ứng dụng.
- Disk IOPS/cache pressure từng member.
- Network giữa members.
- Hidden/delayed members nếu có.

Ví dụ **giả định**:

```text
Primary P:     query=100/s, update=600/s
Secondary S1:  query=1500/s, update=*600/s
Secondary S2:  query=0/s, update=*600/s
```

S1 có thể phục vụ lượng read lớn do ứng dụng dùng secondary read preference. Nếu chỉ xem primary, bạn có thể bỏ qua node gây chậm.

### 18.2. Replication lag có nhiều nguyên nhân

- Primary write burst.
- Secondary disk chậm.
- Network gián đoạn.
- Secondary đang phục vụ query nặng.
- Cache pressure.
- Index build/maintenance.
- Member restart/recovery.

Không tăng oplog size rồi nghĩ lag sẽ biến mất; tăng retention window có thể giúp recover nhưng không sửa throughput bottleneck.

### 18.3. Monitor majority và failover

Với 3 voting members, majority là 2. Nếu hai members down, có thể mất write availability. Khi alerts báo node unavailable, phải xem `rs.status()` và election logs, không chỉ xem `mongostat conn`.

---

## 19. Sharded cluster: nhìn tải theo shard

Sharding có thể phân bố data đều nhưng workload không đều.

```text
Sharded cluster:
  Shard A: 80% operations
  Shard B: 15% operations
  Shard C:  5% operations
```

Các số chỉ minh họa.

Có thể do hot shard key, range hotspot, scatter-gather queries, balancer/migration hoặc ứng dụng tập trung vào một tenant.

Theo Atlas Docs, **Sharding Insights** có mặt trên M10+ sharded clusters chạy MongoDB 8.0+ theo điều kiện của tính năng.

Nên xem:

- Ops/s, CPU/disk, network theo shard.
- Query targeting và số shards tham gia.
- Chunk distribution/migration.
- Shard key cardinality.
- Routing và mongos health.
- Replication lag của từng shard replica set.

`mongostat --discover` cho nhiều số liệu theo member nhưng không thay đầy đủ sharding metadata analysis.

---

## 20. Phân tích theo triệu chứng, không suy luận một bước

| Triệu chứng | Những giả thuyết hợp lý | Bằng chứng tiếp theo |
| --- | --- | --- |
| CPU cao, docs examined cao | Query scan nhiều | Profiler, Explain |
| CPU cao, docs examined thấp | Aggregation, compression, index build | Logs, stages, host metrics |
| WiredTiger dirty tăng | Write/checkpoint pressure | Disk IOPS, cache metrics |
| Cache used cao | Working set lớn hoặc cache bình thường | Evictions, disk read latency |
| Connections tăng | App scale-out, pool leak, retry | Driver pool stats |
| Network out tăng | Response lớn, getMore, replication | Response Length, app trace |
| Read queue tăng | Contention hoặc saturation | Active ops, CPU/disk |
| Secondary lag | Disk/network/write burst | Rs status/Atlas per-node |
| Một shard nóng | Shard-key/workload skew | Sharding Insights |
| COLLSCAN + high targeting | Thiếu index/shape không chọn lọc | Index inventory, Explain |
| App p99 cao, DB bình thường | Pool wait, network, app CPU | Distributed tracing |

Đây là **giả thuyết** chứ không phải quan hệ nhân quả chắc chắn.

---

## 21. Quy trình điều tra một sự cố cụ thể

Giả sử sau deployment, endpoint `/api/orders?status=FAILED` tăng p95 từ 70ms lên 650ms lúc **14:05 UTC**. Đây là ví dụ tưởng tượng.

### Bước 1 — Đóng khung timeline

```text
Incident: 14:05 UTC
Environment: production
Endpoint: /api/orders
Release: build-2026-11-14
Cluster: production-cluster
Symptom: p95 70ms -> 650ms
```

Ghi user impact, error rate, tenant/region và những thay đổi gần đây.

### Bước 2 — Atlas Metrics

So CPU, disk IOPS, connections, ops/s và query targeting trước/sau deploy. Tách theo node/replica set nếu có thể.

### Bước 3 — mongostat

```bash
mongostat --host=mongo1.example.net:27017 --rowcount=15 1
```

Xác định read/write mix, queue, conn, cache. Nếu incident đã kết thúc, `mongostat` hiện tại có thể không còn cho bằng chứng; dùng Atlas history.

### Bước 4 — mongotop hoặc Compass Performance

```bash
mongotop --host=mongo1.example.net:27017 --rowcount=15 1
```

Xem `shop.orders` có phải namespace đang nóng không. Nếu không, kiểm tra đúng node/secondary hoặc khoảng thời gian.

### Bước 5 — Query Profiler

Lọc namespace `shop.orders`, khoảng 14:00–14:20 UTC, query shape có `status` và sort. Xem `millis`, `docsExamined`, `keysExamined`, `planSummary`.

### Bước 6 — Compass Explain

```javascript
db.orders.find({ status: "FAILED" })
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
```

Nếu `COLLSCAN`, thử candidate index **trên staging**. Nếu đã có `IXSCAN` mà keys examined lớn, cần xem index prefix/selectivity.

### Bước 7 — Đánh giá candidate change

```javascript
// Chỉ là ví dụ staging, không mặc định chạy trên production.
db.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "ix_status_createdAt" }
);
```

Kiểm tra index size, write overhead, query mix, build impact và rollback plan.

### Bước 8 — Đo trước và sau

- HTTP p50/p95/p99.
- Query profiler latency.
- Keys/docs examined.
- CPU/disk/memory.
- Write latency.
- Connection pool wait.
- Error/retry rate.
- Replica lag và shard skew.

### Bước 9 — Incident report

Ghi nguyên nhân được chứng minh, impact, phương án khắc phục, rollback, metrics trước/sau và alert cần bổ sung.

---

## 22. Các kịch bản thường gặp

### 22.1. Connection storm sau release

Atlas Connections tăng từ 400 lên 4.000. Điều tra:

1. Số app instances.
2. MongoDB driver `MongoClient` có bị tạo mới mỗi HTTP request không.
3. Connection pool `maxPoolSize`/`minPoolSize`.
4. Retry loops.
5. Active vs queued clients.
6. Host CPU/network và auth failures.

Đừng kết luận cần scale MongoDB trước khi kiểm tra connection lifecycle phía app.

### 22.2. Collection write-heavy sau batch job

`mongotop` cho `analytics.events` write time lớn; `mongostat` update/s tăng.

Xem batch size, update filter index, document growth, số indexes, dirty cache, disk IOPS và replication lag. Cách sửa có thể là batching/throttle, tối ưu query hoặc chuyển lịch chạy job.

### 22.3. Secondary lag nhưng primary khỏe

RTPP primary bình thường, một secondary lag 90 giây. Cần xem per-secondary CPU/disk/network, read preference, oplog window và logs. Không lấy panel primary làm bằng chứng mọi member đã khỏe.

### 22.4. Query có index nhưng vẫn chậm

Profiler báo `IXSCAN` nhưng `keysExamined` cao và response lớn. Có thể cần compound index khác, projection, sort optimization hoặc giảm kết quả. Không xem tên stage là kết luận cuối.

---

## 23. Ba loại latency phải phân biệt

1. `mongotop.read=500ms` là **tổng read operation time** trên namespace trong sample.
2. Query Profiler `millis=500` là **thời gian một operation** được ghi nhận.
3. HTTP p95=500ms là **percentile của nhiều requests** gồm network, app, driver và database.

Chúng không được thay thế lẫn nhau.

### 23.1. Mean khác p95/p99

Nếu 99% queries trả dưới 60ms nhưng 1% còn lại tốn 2 giây, mean có thể nhìn chấp nhận được trong khi tail latency ảnh hưởng người dùng.

Cần đo:

- API requests/s và errors.
- HTTP p50/p95/p99.
- Database operation latency.
- Driver connection-pool wait.
- Timeouts/retries.
- External calls và serialization.

**Không ước lượng p99 từ năm dòng mongostat**.

### 23.2. Throughput giảm chưa chắc hiệu năng cải thiện

Nếu API lỗi sớm trước khi gửi DB queries, `mongostat query/s` có thể giảm. Không được báo database đã cải thiện khi user-facing error rate lại tăng.

---

## 24. Dashboard giám sát tối thiểu

### 24.1. Hạ tầng

| Chart | Mục đích |
| --- | --- |
| CPU per node | Saturation |
| Disk free, IOPS, latency | Capacity và I/O |
| WiredTiger cache used/dirty | Cache pressure |
| Resident memory, swap | Memory |
| Connections, queued operations | Pool/queue pressure |
| Network in/out | Traffic/replication |

### 24.2. Database

| Chart | Mục đích |
| --- | --- |
| Ops/s theo loại | Workload mix |
| Query targeting | Scan efficiency |
| Namespace latency/slow query shapes | Định vị bottleneck |
| Replication lag/elections | Availability |
| Oplog window | Recoverability |
| Data/index size | Capacity |
| Sharding/Searching metrics nếu có | Skew/index health |

### 24.3. Ứng dụng

| Chart | Mục đích |
| --- | --- |
| Endpoint p50/p95/p99 | User SLO |
| Error/timeout rate | Kết quả thất bại |
| Driver pool wait | App-side queue |
| Queries/retries | Hidden load |
| Deployment markers | Correlate changes |
| Region/tenant breakdown | Tránh trung bình che hotspot |

Dashboard tốt cho phép truy ngược **symptom → node → namespace → query shape → request trace**.

---

## 25. Bảo mật, chi phí và giới hạn giám sát

### 25.1. Query logs có thể chứa dữ liệu nhạy cảm

Profiler/currentOp/explain có thể lộ:

- Collection/field names.
- Query literal values, user IDs, email.
- Internal topology.
- Application metadata.
- Tên tenant hoặc business identifiers.

Cần redact trước khi đưa vào ticket và chỉ cho vai trò phù hợp truy cập.

### 25.2. Không bật profiling mọi operations tùy tiện

MongoDB self-managed có database profiler. Ví dụ:

```javascript
// Không thực hiện trên production nếu chưa có runbook/approval.
db.setProfilingLevel(2);
```

Profiling level cao có thể gây overhead CPU/disk và ghi query values vào `system.profile`. Hãy đặt mức và threshold theo yêu cầu, dùng Atlas tools/sampling nếu thích hợp.

### 25.3. Queryable Encryption

Compass Performance không hiển thị performance data cho collections dùng Queryable Encryption theo hạn chế hiện hành. Atlas RTPP có thể ẩn/redact một số encrypted query details. Không vô hiệu hóa encryption để nhìn query plaintext.

### 25.4. Quyền dừng operation

Kill Op có thể làm giao dịch/report/index work thất bại và kích hoạt retry. Đội vận hành phải có incident runbook và change approval; không cấp kill privileges cho chỉ số giám sát read-only.

---

## 26. Sai lầm thường gặp

| Nhận định sai | Thực tế |
| --- | --- |
| “`mongostat query=100` nghĩa 100 HTTP requests/s” | Request có thể sinh nhiều DB commands |
| “`mongotop total=900ms` là query chậm 900ms” | Là tổng operation time namespace |
| “`mongotop` cho % CPU từng collection” | Nó báo read/write time |
| “`dirty=80%` nghĩa disk đã đầy” | Là tỷ lệ WiredTiger cache dirty |
| “`used=95%` là memory leak” | Cache có thể dùng gần hết dung lượng |
| “`vsize` là RAM vật lý” | Virtual memory khác resident memory |
| “Connections tăng nghĩa DB có lỗi” | Có thể app pool hoặc deploy |
| “`IXSCAN` đồng nghĩa index tốt” | Có thể scan rất nhiều keys |
| “`COLLSCAN` luôn sai” | Một số full-scan queries là hợp lệ |
| “Compass Performance lưu historical metrics vô hạn” | Chủ yếu realtime |
| “Compass kết nối mongos thấy đầy đủ node metrics” | Có giới hạn |
| “RTPP primary đại diện mọi secondary” | Secondary có workload riêng |
| “Performance Advisor gợi ý thì tạo index ngay” | Phải đo write/storage/plan impact |
| “Không có Advisor suggestion nghĩa không có slow query” | Có sampling và threshold |
| “Atlas Free có mọi feature như M10+” | Tier có giới hạn |
| “`mongostat --discover` luôn thấy hidden nodes” | Discovery có giới hạn |
| “`mongotop --locks` chuẩn trên MongoDB hiện đại” | Legacy 2.6 trở xuống |
| “Profiler không có overhead hay dữ liệu nhạy cảm” | Có overhead/privacy risk |
| “Pause Compass tạm dừng database” | Chỉ pause GUI update |
| “Atlas P95 giống HTTP P95” | Phạm vi/sampling khác |
| “Kill Op là fix query chậm” | Chỉ dừng operation, có thể gây lỗi |
| “Một snapshot một giây đủ xác định nguyên nhân” | Cần timeline và đối chiếu signals |

---

## 27. Bài tập thực hành

### Bài 1 — Chọn đúng công cụ

Với các yêu cầu: xem ops/s, tìm collection nóng, giải thích query plan, tạo cảnh báo disk, chọn giữa `mongostat`, `mongotop`, Compass Explain và Atlas Alerts.

**Đáp án:** Lần lượt mongostat, mongotop, Compass Explain, Atlas Alerts.

### Bài 2 — Terminal hay mongosh?

Tại sao `mongostat --rowcount=10 1` là lệnh terminal chứ không phải JavaScript trong `mongosh`?

### Bài 3 — Polling

`mongostat --rowcount=12 5` có bao nhiêu samples và interval bao nhiêu giây? Query field là rate hay tổng của 5 giây?

**Đáp án:** 12 samples, interval 5s; operations rate thường được chuẩn hóa per second.

### Bài 4 — Cache

`dirty=8%` và `used=94%` có chứng minh disk đầy 94% không?

**Đáp án:** Không; cả hai tính theo WiredTiger cache maximum.

### Bài 5 — Connections

`conn` tăng đột ngột sau deploy. Kể ba khả năng liên quan app connection pool.

### Bài 6 — Replica mark

Dấu `*` trong trường operation và `command=3|120` trên secondary có thể biểu thị điều gì?

### Bài 7 — Discovery

Tại sao `mongostat --discover` có thể bỏ qua hidden member?

### Bài 8 — -o và -O

Phân biệt `mongostat -o` và `-O`. Có dùng cùng lúc được không?

**Đáp án:** Chọn riêng fields và thêm fields vào default; không dùng chung.

### Bài 9 — Mongotop 2500ms

Một interval 1s có `read=2500ms`. Có chắc đã có một query mất 2,5 giây không?

**Đáp án:** Không, có thể nhiều operations đồng thời.

### Bài 10 — --locks

Vì sao `mongotop --locks` không phù hợp MongoDB 8.x?

### Bài 11 — Namespace không thấy

`mongotop` không hiện `shop.products` trong một mẫu. Có thể nói collection đó chưa được truy vấn cả ngày không?

**Đáp án:** Không.

### Bài 12 — Lab Explain

Chạy query lab theo `status` trước và sau index `(status,createdAt)`. Ghi keys examined, docs examined, nReturned và sort stage.

### Bài 13 — Ratio

`docsExamined=200000`, `nReturned=50`. Docs examined per returned?

**Đáp án:** 4.000.

### Bài 14 — IXSCAN rộng

`keysExamined=500000` và `nReturned=5` dù có IXSCAN. Tại sao cần xem compound index/selectivity?

### Bài 15 — Compass Performance

Kể sáu nhóm thông tin mà Compass Performance cung cấp. Nhóm nào liên quan `mongotop`?

### Bài 16 — Compass mongos

Giao diện Performance có giới hạn gì khi kết nối tới `mongos`?

### Bài 17 — Vector Search Explain

Compass có hiển thị mọi `$vectorSearch` queries dưới dạng Visual Tree không?

**Đáp án:** Không.

### Bài 18 — RTPP và secondary

RTPP chủ yếu báo từ member nào? Cần làm gì nếu app đọc nhiều từ secondary?

### Bài 19 — Metrics granularity

Một spike kéo dài 20 giây bị chìm trong chart 30 ngày. Bạn thu hẹp time range thế nào?

### Bài 20 — Query shape

Hai query chỉ khác literal nhưng cùng cấu trúc có thể được nhóm ra sao? Khi nào grouping không đủ?

### Bài 21 — Advisor

Performance Advisor gợi ý ba indexes. Vì sao phải đo write latency và index size trước khi tạo?

### Bài 22 — Query Insights p95

Atlas query p95 thấp nhưng HTTP p95 cao. Kể bốn nguyên nhân ngoài DB operation execution.

### Bài 23 — Alert

Thiết kế disk capacity alert có threshold, duration, owner, notification và runbook.

### Bài 24 — Replica lag

Một secondary lag 90s nhưng primary bình thường. Bạn kiểm tra network, disk, read load và oplog ra sao?

### Bài 25 — Shard skew

Ba shards có tải 80/15/5%. Kể những nguyên nhân có thể và cách kiểm tra.

### Bài 26 — Incident

CPU cao, `mongotop` nóng ở `orders`, profiler có COLLSCAN, API p95 tăng. Lập thứ tự điều tra và chọn bước tối ưu an toàn.

### Bài 27 — ServerStatus rate

Counter tăng 600 trong 10s; rate trung bình bằng bao nhiêu?

**Đáp án:** 60 operations/s nếu cùng process và không có restart.

### Bài 28 — Profiling security

Vì sao không chạy `db.setProfilingLevel(2)` ngay trên production rồi đăng toàn bộ query samples lên ticket công khai?

### Bài 29 — Alert fatigue

Một team có 200 alerts nhưng không có owner/runbook. Đề xuất cách giảm nhiễu và gắn với SLO.

### Bài 30 — Runbook tổng hợp

Thiết kế quy trình kết hợp app tracing, Atlas Metrics, `mongostat`, `mongotop`, Query Profiler, Performance Advisor và Compass Explain để xử lý lỗi latency sau deployment. Nêu rollback plan và metrics trước/sau.

---

## 28. Checklist production

### Phân quyền và bảo mật

- [ ] Database Tools/Compass versions tương thích server.
- [ ] Có monitoring roles tối thiểu cho serverStatus/top/currentOp.
- [ ] Atlas Project viewers không bị cấp quyền admin không cần thiết.
- [ ] Kết nối dùng TLS, credentials không nằm trong logs/URI công khai.
- [ ] Query samples/PII được redact.
- [ ] Không kill op/profiling mức cao ngoài quy trình.

### Metrics và dashboard

- [ ] Có CPU/disk/cache/connections theo node.
- [ ] Có ops/s, query targeting và slow query shapes.
- [ ] Có replication lag, oplog window và election logs.
- [ ] Có p95/p99 app latency, errors và driver pool wait.
- [ ] Có deployment/maintenance markers.
- [ ] Có timestamp UTC thống nhất.
- [ ] Hiểu tier-specific sampling/retention và feature limits.

### Alerts và điều tra

- [ ] Có capacity/availability/backup/replication alerts đúng policy.
- [ ] Mỗi alert có owner, severity, notification, runbook.
- [ ] Test alert delivery và escalation.
- [ ] Có quy trình tối ưu query bằng Profiler → Explain → benchmark.
- [ ] Có review index changes và rollback.
- [ ] Đo write/index overhead khi sửa read bottleneck.
- [ ] Có incident postmortem với dữ liệu trước/sau.

---

## 29. Tổng kết

**`mongostat`**, **`mongotop`**, **Compass** và **Atlas Monitoring** phục vụ các góc nhìn khác nhau:

1. **`mongostat`:** quan sát nhanh mỗi node về operations/s, cache, queue, memory, network và connections.
2. **`mongotop`:** biết collection nào có nhiều read/write operation time; **không nhầm** tổng này với latency một query.
3. **Compass:** Performance GUI và Explain Plan để tìm `COLLSCAN`/`IXSCAN`, keys/docs examined và tác động của index.
4. **Atlas:** cung cấp lịch sử, RTPP, Query Insights, Query Profiler, Performance Advisor, Sharding Insights và alerts theo tier/role/version.
5. **Không có công cụ duy nhất cho root cause:** cần nối bằng chứng từ user-facing latency → cluster → node → namespace → query shape → Explain.
6. **Vận hành tốt đòi monitoring an toàn, alerts có hành động và đo lường trước/sau thay đổi.**

Hãy luôn hỏi: **“Số liệu này đang đo đơn vị gì, ở node nào, trong khoảng thời gian nào và còn thiếu bằng chứng gì?”**. Đó là nền tảng của observability MongoDB.

### Tài liệu MongoDB chính thức

- [mongostat — Database Tools](https://www.mongodb.com/docs/database-tools/mongostat/) — options, polling, fields, discovery và JSON.
- [mongostat Examples](https://www.mongodb.com/docs/database-tools/mongostat/mongostat-examples/) — `-o`, `-O`, interval và rowcount.
- [mongotop — Database Tools](https://www.mongodb.com/docs/database-tools/mongotop/) — namespace read/write times, JSON và quyền.
- [mongotop Examples](https://www.mongodb.com/docs/database-tools/mongotop/mongotop-examples/) — output và frequency.
- [Compass: View Real-Time Performance](https://www.mongodb.com/docs/compass/performance/) — Operations, Hottest Collections, Slowest Operations.
- [Compass: View Query Performance](https://www.mongodb.com/docs/compass/query-plan/) — Explain Visual Tree/Raw Output.
- [Atlas: Monitor Clusters](https://www.mongodb.com/docs/atlas/monitoring-alerts/) — metrics, alerts, logs, integrations.
- [Atlas: Real-Time Performance Panel](https://www.mongodb.com/docs/atlas/real-time-performance-panel/) — per-node realtime view.
- [Atlas: Analyze Slow Queries](https://www.mongodb.com/docs/atlas/analyze-slow-queries/) — Query Insights, Query Profiler, Advisor, Sharding Insights.
- [Atlas: Query Profiler](https://www.mongodb.com/docs/atlas/tutorial/query-profiler/) — slow operations và targeting.
- [Atlas: Performance Advisor](https://www.mongodb.com/docs/atlas/performance-advisor/) — index recommendations.
- [Atlas: Configure Alerts](https://www.mongodb.com/docs/atlas/configure-alerts/) — conditions, notifications, permissions.
- [Atlas: Alert Basics](https://www.mongodb.com/docs/atlas/alert-basics/) — alert lifecycle.
- [Analyze Query Performance](https://www.mongodb.com/docs/manual/tutorial/evaluate-operation-performance/) — methods và profiling.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — execution plans và statistics.
- [serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — node counters.
- [top](https://www.mongodb.com/docs/manual/reference/command/top/) — collection time.
- [$currentOp Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/currentOp/) — current operations.
- [Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/) — profiling considerations.
- [Replica Set Status](https://www.mongodb.com/docs/manual/reference/command/replSetGetStatus/) — replication health.
