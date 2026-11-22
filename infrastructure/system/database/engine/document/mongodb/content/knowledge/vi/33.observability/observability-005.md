# Log có cấu trúc, slow query log và mức chi tiết phù hợp trong MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Quan sát hệ thống  
> **Bài học:** Log có cấu trúc, slow query log và mức chi tiết phù hợp

## 1. Bài toán: ứng dụng chậm, MongoDB đang nói gì?

Một dịch vụ đặt hàng dùng MongoDB báo lỗi tăng độ trễ: API liệt kê đơn hàng từ 50 ms lên 2 giây, nhưng CPU của ứng dụng không tăng tương ứng. Nhóm vận hành cần trả lời:

- MongoDB có phát sinh truy vấn chậm không?
- Lệnh nào chậm, chạy trên collection nào?
- MongoDB đã quét bao nhiêu document và index key?
- Có xảy ra `COLLSCAN`, sort lớn, chờ lock hoặc replication lag không?
- Slow query bắt đầu khi nào, trên instance nào và thuộc request nào?
- Có thể tăng độ chi tiết log để điều tra mà không làm đầy ổ đĩa hoặc lộ dữ liệu khách hàng không?
- Nên bật database profiler hay chỉ cần server diagnostic log?
- Khi sự cố kết thúc, phải hạ mức log/khôi phục sampling như thế nào?

Câu trả lời không phải “bật mọi thứ lên verbosity 5”. MongoDB cung cấp những nguồn dữ liệu quan sát có **mức chi tiết, phạm vi và chi phí khác nhau**.

```text
Ứng dụng / Java Driver
    │
    │ request, command, latency, opaque traceId
    ▼
MongoDB mongos / mongod
    │
    ├─ Diagnostic log dạng JSON:
    │    INFO / WARNING / ERROR / DEBUG
    │    component, message id, context, attributes
    │
    ├─ Slow-operation log:
    │    command + namespace + duration + plan summary
    │    keysExamined, docsExamined, nreturned ...
    │
    ├─ Database profiler (mongod):
    │    system.profile capped collection theo database
    │
    └─ Metrics / diagnostics khác:
         serverStatus, explain, currentOp,
         FTDC, managed monitoring
    │
    ▼
Log collector / Monitoring / Alerting
    │
    └─ Phân tích: thời gian, host, namespace,
       query shape, component, latency, error
```

**Thông điệp chính:** Sử dụng **structured diagnostic logs** cho quan sát rộng, **slow-operation logging** cho phát hiện lệnh chậm, **profiler** khi cần chi tiết có kiểm soát, và **explain/metrics** để kiểm chứng nguyên nhân. Chọn verbosity, threshold và sampling có chủ đích, rồi thu hồi cấu hình debug sau điều tra.

### 1.1. Kết quả học tập

Sau bài học, bạn có thể:

1. Nhận diện cấu trúc JSON logging của MongoDB: `t`, `s`, `c`, `id`, `ctx`, `msg`, `attr`.
2. Phân biệt warning/error log với slow-operation log và profiler.
3. Đọc một slow query entry: namespace, command, duration, plan, keys/documents examined.
4. Hiểu các tùy chọn `slowOpThresholdMs`, `slowOpSampleRate` và profiler levels 0/1/2.
5. Chọn mức component verbosity phù hợp thay vì bật debug trên toàn server.
6. Dùng `getProfilingStatus()`, `setProfilingLevel()`, `system.profile` và `explain("executionStats")` trong lab.
7. Tương quan Java Driver command monitoring với server-side logs mà không log password hoặc dữ liệu nhạy cảm.
8. Phân biệt logs của `mongod`, `mongos`, replica set và sharded cluster.
9. Thiết kế retention, rotation, parsing, sampling, access controls và cảnh báo.
10. Viết runbook khi latency tăng và biết lúc nào phải hạ verbosity.

---

## 2. Ba loại thông tin thường bị gọi chung là “MongoDB log”

| Nguồn | Mục tiêu | Nằm ở đâu | Phạm vi | Chi phí cần chú ý |
|---|---|---|---|---|
| **Diagnostic log** | Trạng thái server, warnings, errors, debug, slow operations | stdout/stderr hoặc file, tùy cấu hình | Theo từng tiến trình `mongod`/`mongos` | Dung lượng, I/O, độ nhạy cảm dữ liệu |
| **Slow-operation log** | Chỉ ra các thao tác bị coi là chậm | Thường là một loại message trong diagnostic log | Theo server process/threshold/filter | Volume lớn khi threshold thấp |
| **Database profiler** | Ghi record chi tiết các thao tác được profiler chọn | Collection `system.profile` trong một database | Theo database trên `mongod` | CPU/ghi đĩa/capped storage |
| **Metrics/FTDC** | Xu hướng CPU, memory, cache, operation counters, locks, queues | Monitoring hoặc diagnostic data | Process/host/cluster | Sampling, data collection, retention |
| **Driver/application log** | Request/trace, network + driver latency, retries | Service log/tracing | Client/service | Sensitive info, cardinality, volume |

**Slow query log không mặc định là một file riêng.** MongoDB thường ghi thông báo về thao tác chậm vào **server diagnostic log**. Tùy log destination, người vận hành có thể nhìn thấy nó trong file `mongod.log`, container log hoặc hệ thống quan sát do nhà cung cấp quản lý.

### 2.1. Diagnostic log

Thông điệp về:

- Startup/shutdown.
- Kết nối network/TLS.
- Authentication/authorization.
- Replication, election và sharding.
- Storage/checkpoint.
- Query/command execution.
- Warning khi hệ thống gần chạm giới hạn.
- Errors và thông tin xử lý sự cố.

Không phải tất cả messages đều là query; một số rất hữu ích để giải thích query chậm do cơ sở hạ tầng hoặc trạng thái cluster.

### 2.2. Slow-operation log

Một thông điệp về lệnh có latency vượt ngưỡng hoặc phù hợp filter/sampling đã cấu hình.

Ví dụ có thể nói:

- `ns`: `shop.orders`.
- `command`: `find`.
- `planSummary`: `COLLSCAN`.
- `docsExamined`: 250.000.
- `nreturned`: 20.
- `durationMillis`: 863.

Nó cung cấp manh mối tốt để mở `explain` và kiểm tra index/query shape; nhưng **không tự chứng minh mọi nguyên nhân** của độ trễ.

### 2.3. Database profiler

MongoDB profiler có thể ghi các bản ghi vào `system.profile`. Nó là **dữ liệu trong MongoDB**, không phải file text `mongod.log`. Collection này có tính chất capped và ghi nhận các thông tin theo cơ chế version-specific.

Profiler hữu ích cho điều tra có chủ đích nhưng không nên bật mức 2 trên một workload lớn không có giới hạn.

### 2.4. Tắt profiler có còn slow query log không?

**Có thể có.** Profiling level `0` nghĩa là **không ghi hồ sơ thao tác vào `system.profile`**, nhưng slow operations vẫn có thể được ghi vào diagnostic log theo cấu hình threshold/sample/filter.

Đây là khác biệt phải nhớ:

```text
Profiling level = 0
    ├─ system.profile: không ghi operation profile
    └─ diagnostic log: vẫn có thể ghi slow-operation messages
```

---

## 3. Structured logging: MongoDB ghi log dạng JSON như thế nào?

Các phiên bản MongoDB hiện đại hỗ trợ **structured logging** theo từng dòng JSON. MongoDB 4.4 đưa structured JSON diagnostic logging vào server.

Ví dụ **minh họa đã rút gọn** (các fields khác nhau giữa phiên bản, command type và execution engine):

```json
{
  "t": {
    "$date": "2026-11-14T08:20:12.483+00:00"
  },
  "s": "I",
  "c": "COMMAND",
  "id": 51803,
  "ctx": "conn241",
  "msg": "Slow query",
  "attr": {
    "type": "command",
    "ns": "shop.orders",
    "command": {
      "find": "orders",
      "filter": {
        "status": "PENDING"
      },
      "$db": "shop"
    },
    "planSummary": "COLLSCAN",
    "keysExamined": 0,
    "docsExamined": 250000,
    "nreturned": 20,
    "durationMillis": 863
  }
}
```

**Không giả định mọi bản MongoDB trả đúng những fields này.** Đây là mẫu để hiểu ý nghĩa cấu trúc, không phải schema bắt buộc của mọi log event.

### 3.1. Các top-level fields

| Field | Ý nghĩa | Ví dụ |
|---|---|---|
| `t` | Timestamp của log event, thường ở dạng Extended JSON Date | `{"$date":"..."}` |
| `s` | Severity | `I`, `W`, `E`, `D1` |
| `c` | Component/subsystem | `COMMAND`, `NETWORK`, `REPL` |
| `id` | Numeric message identifier cho loại message | `51803` |
| `ctx` | Execution context/connection/thread | `conn241` |
| `msg` | Nội dung message có thể đọc được | `Slow query` |
| `attr` | Thuộc tính có cấu trúc, phụ thuộc từng message | `ns`, `durationMillis`... |
| `tags` | Tags tùy loại message, không phải event nào cũng có | Danh sách classification tags |

### 3.2. t: timestamp

Timestamp dùng để:

- So sánh thời điểm lỗi.
- Ghép với metrics CPU/I/O/replication.
- Xác định trước/sau deploy.
- Lập timeline của incident.

Cần chuẩn hóa timezone trong log pipeline, thường dùng UTC ở hệ thống tập trung. Không trộn thời gian của server, client và dashboard mà không quy đổi timezone.

### 3.3. s: severity

Các ký hiệu thường gặp:

| Severity | Cách đọc |
|---|---|
| `F` | Fatal |
| `E` | Error |
| `W` | Warning |
| `I` | Informational |
| `D1` tới `D5` | Các mức debug tùy verbosity |

Một message `I` tên `Slow query` vẫn có thể đại diện vấn đề hiệu năng quan trọng. Không chỉ lọc `E/W` rồi nghĩ không có slow queries.

### 3.4. c: component

Log component cho biết subsystem phát sinh message. Ví dụ:

- `COMMAND`: thao tác command và thông tin slow operations.
- `NETWORK`: kết nối, socket, TLS.
- `ACCESS` hoặc các nhánh access control tùy bản: authentication/authorization.
- `REPL`: replication.
- `STORAGE`: storage engine.
- `SHARDING`: sharded cluster.
- `QUERY`: query execution/planning trong những tình huống cụ thể.
- `INDEX`: index build/operations.

Danh mục component cụ thể thay đổi theo MongoDB version. Dùng documentation của phiên bản đang chạy thay vì hardcode mọi thành phần.

### 3.5. id là message identifier, không phải request ID

Ví dụ `id: 51803` có thể được dùng cho **nhiều** slow query entries.

Nó định danh **loại message**; không đại diện duy nhất cho một request như trace ID trong ứng dụng.

Muốn nhận diện các sự kiện riêng, dùng timestamp, host/process, context, namespace và những correlation fields có sẵn.

### 3.6. ctx là execution context

`ctx` có thể biểu diễn connection hoặc thread context, ví dụ `conn241`. Nó giúp đối chiếu các messages trên cùng connection trong một khoảng thời gian.

Nhưng:

- Connection pool có thể tái sử dụng cùng connection cho nhiều requests.
- Một request application có thể gây nhiều MongoDB commands.
- Retries/getMore có thể làm sequence phức tạp.
- Giá trị `ctx` không phải end-to-end trace ID toàn hệ thống.

Không coi `conn241` là transaction ID hoặc business request ID.

### 3.7. msg và attr

`msg` là câu mô tả được chuẩn hóa ở mức nhất định; `attr` chứa details để phân tích bằng máy.

Ví dụ:

```json
{
  "msg": "Slow query",
  "attr": {
    "ns": "shop.orders",
    "planSummary": "IXSCAN { customerId: 1, createdAt: -1 }",
    "keysExamined": 84500,
    "docsExamined": 84500,
    "nreturned": 10,
    "durationMillis": 377
  }
}
```

Đừng dựa vào string matching toàn bộ dòng log khi một parser có thể lấy JSON fields theo cấu trúc.

---

## 4. Vì sao structured logs có lợi cho quan sát hệ thống?

Trước structured logs, việc tìm thông tin có thể phụ thuộc regex trên một dòng text dài, dễ vỡ khi format thay đổi.

Với JSON logs, ta có thể truy vấn:

- `s="E"` trong 5 phút vừa qua.
- `c="REPL"` và một số message IDs.
- `msg="Slow query"` kèm `attr.ns="shop.orders"`.
- Histogram của `attr.durationMillis`.
- Top namespaces có `docsExamined / max(nreturned,1)` cao.
- Số errors theo component/host/replica set member.

### 4.1. Một log event có thể không có attr

Không phải mọi message đều chứa `attr` hoặc đủ mọi nested fields. Log pipeline nên xử lý optional fields.

### 4.2. Dấu hiệu truncated log

Một số giá trị lớn, đặc biệt command/query documents, có thể bị **truncate** do giới hạn log message size và cơ chế redaction. Đừng giả định `attr.command` là bản sao đầy đủ và nguyên vẹn của query.

Không dùng slow log để tái chạy query một cách máy móc khi:

- Command đã bị truncate.
- Có fields chứa dữ liệu nhạy cảm.
- Có thông tin không đủ như read concern/transaction context.
- Tham số log đã được redacted.
- Query có tác dụng ghi/xóa dữ liệu.

### 4.3. Schema log không phải một hợp đồng bất biến

Các phiên bản MongoDB có thể:

- Thêm/bỏ fields.
- Đổi cách thể hiện query identifiers.
- Có field khác giữa classic engine và Slot-Based Execution.
- Thay message text/ID.
- Thay đổi chi tiết cho read/write/getMore.

Dùng parsing robust: schema có optional fields, giữ raw message theo chính sách, và test parser khi upgrade MongoDB.

### 4.4. Message id ổn định hơn text nhưng vẫn phải quản lý version

Numeric log IDs hữu ích để phân loại, nhưng không nên tạo một parser giả định mọi phiên bản cùng có một event với cấu trúc giống hệt. Dùng `id` cùng `msg`, `c` và version để phân loại.

---

## 5. Slow query log là gì?

Tên gọi thông dụng là **slow query log**, nhưng MongoDB thực tế có thể ghi những **slow operations** không chỉ gồm `find`.

Các operation có thể bao gồm:

- `find`.
- `aggregate`.
- `update`.
- `delete`.
- `findAndModify`.
- `getMore` cho cursor.
- Một số commands và hoạt động khác tùy phiên bản.

Một operation vượt ngưỡng theo cơ chế logging/profiling có thể tạo message trong diagnostic log.

### 5.1. Slow không nhất thiết là lỗi

Ví dụ query phân tích báo cáo được dự kiến chạy 5 giây, còn API transactional có SLO 100 ms.

Cùng một ngưỡng 100 ms có thể:

- Quá nhạy cho analytic batch.
- Quá lỏng cho API latency nhạy cảm.
- Gây quá nhiều log với workload lớn.
- Bỏ sót nhiều query 80 ms nhưng request tổng 300 ms.

Ngưỡng phải đi cùng **SLO của từng workload**, không chỉ mặc định của server.

### 5.2. Ngưỡng phổ biến

MongoDB có tùy chọn:

```yaml
operationProfiling:
  slowOpThresholdMs: 100
```

100 ms là ngưỡng mặc định phổ biến cho các thao tác chậm trong nhiều phiên bản, nhưng **phải kiểm tra cấu hình thực tế** của server/managed provider.

### 5.3. Sampling

Một hệ thống có 100.000 slow operations/giờ có thể tạo lượng log khổng lồ.

```yaml
operationProfiling:
  slowOpSampleRate: 0.1
```

Giá trị 0.1 nghĩa là sampling khoảng 10% theo cơ chế áp dụng trong phiên bản hỗ trợ, **không phải đảm bảo chính xác 10 trên 100 operation cho mỗi collection**.

Sampling giúp giảm volume/overhead, nhưng:

- Có thể bỏ sót một sự kiện hiếm.
- Không đủ để chứng minh “không có slow query”.
- Không thích hợp nếu cần audit chính xác từng thao tác.
- Alerting phải tính đến sampling factor.
- Thống kê percentiles dựa trên logs sampled có thể lệch nếu sample không đại diện.

### 5.4. Ngưỡng và sample không phải debugger miễn phí

Nếu hạ threshold từ 100 ms xuống 0 ms trên một hệ thống có 100.000 ops/s, bạn có thể biến server log thành một luồng sự kiện khổng lồ.

Không chỉnh threshold cực thấp trên production trong thời gian dài mà không tính lượng log, collector throughput và dung lượng disk.

---

## 6. Profiler levels: 0, 1 và 2

MongoDB có **database profiler** với các mức thường gặp:

| Level | Ý nghĩa | Khi dùng |
|---|---|---|
| `0` | Tắt thu thập profile records vào `system.profile` | Mặc định/hoạt động bình thường, vẫn có slow-operation log |
| `1` | Ghi profile cho thao tác chậm theo threshold/sample hoặc filter phù hợp | Điều tra có kiểm soát |
| `2` | Ghi profile cho tất cả operations được profiler theo dõi | Lab hoặc điều tra rất ngắn, cân nhắc overhead |

**Cực kỳ quan trọng:** Mức 0 không bảo đảm diagnostic log ngừng ghi slow operations.

### 6.1. Profiling mode trong file config

Ví dụ self-managed `mongod.conf`:

```yaml
operationProfiling:
  mode: off
  slowOpThresholdMs: 100
  slowOpSampleRate: 1.0
```

Các giá trị mode trong config thường gồm:

- `off`: profiler không thu thập vào `system.profile`.
- `slowOp`: profile slow operations.
- `all`: profile all operations.

Cách diễn đạt của CLI/mongosh là numeric levels 0/1/2.

### 6.2. Thay đổi profiling level trong mongosh

Giả sử lab được phép quản trị:

```javascript
const lab = db.getSiblingDB("observability_lab");

// Xem trước trạng thái hiện tại.
printjson(lab.getProfilingStatus());

// Bật profiler cho slow operations trong lab.
lab.setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 1.0
});
```

Để tắt profiler sau thí nghiệm:

```javascript
lab.setProfilingLevel(0);
```

**Không nên chỉ nhớ rằng ban đầu là level 0.** Hãy ghi lại cấu hình trước khi thay đổi và khôi phục đúng các values threshold/sample/filter theo runbook.

### 6.3. Mức 2 rất tốn tài nguyên

```javascript
// Chỉ trong môi trường lab nhỏ và được phép.
lab.setProfilingLevel(2);
```

Profiling level 2 có thể tạo lượng profile records lớn và thêm write load. Không bật toàn bộ trên production trong thời gian dài vì mục đích “thu thập thêm cho chắc”.

### 6.4. Cơ chế filter

Một số phiên bản MongoDB hỗ trợ cấu hình profiler filter để chọn operations theo điều kiện cụ thể.

Khi dùng `filter`, quan hệ với `slowms`/`sampleRate` có thể **khác logic threshold thông thường**; documentation chỉ ra filter có thể được ưu tiên thay cho các ngưỡng này trong một số cấu hình.

Vì vậy, đừng vừa đặt filter vừa mặc định slowms/sampleRate còn giới hạn lượng profile/slow log như trước. Đọc version-specific docs rồi thử trong lab.

### 6.5. Profiler ở mongos?

Database profiler ở `mongod` sử dụng `system.profile`. **Không bật database profiling trên `mongos` như trên mongod**: `mongos` không có `system.profile` tương đương để ghi profile records của một database.

Trong sharded cluster, cần thu thập diagnostic logs và các thông tin trên mongos/shards theo topology.

---

## 7. Tạo lab quan sát không gây tải nguy hiểm

Bài tập sau chỉ dùng collection nhỏ. Không cố tình tạo query độc hại để ép MongoDB chậm.

### 7.1. Dữ liệu lab

Trong `mongosh` kết nối MongoDB lab:

```javascript
const lab = db.getSiblingDB("observability_lab");
const orders = lab.getCollection("orders");

orders.insertMany([
  {
    _id: 1, tenantId: "t1", customerId: "C001",
    status: "PENDING", amount: 120000,
    createdAt: ISODate("2026-11-01T08:00:00Z")
  },
  {
    _id: 2, tenantId: "t1", customerId: "C002",
    status: "PAID", amount: 560000,
    createdAt: ISODate("2026-11-01T09:00:00Z")
  },
  {
    _id: 3, tenantId: "t1", customerId: "C001",
    status: "PENDING", amount: 80000,
    createdAt: ISODate("2026-11-02T08:00:00Z")
  },
  {
    _id: 4, tenantId: "t1", customerId: "C003",
    status: "CANCELLED", amount: 140000,
    createdAt: ISODate("2026-11-02T09:00:00Z")
  },
  {
    _id: 5, tenantId: "t2", customerId: "C090",
    status: "PAID", amount: 250000,
    createdAt: ISODate("2026-11-03T08:00:00Z")
  },
  {
    _id: 6, tenantId: "t2", customerId: "C091",
    status: "PENDING", amount: 175000,
    createdAt: ISODate("2026-11-03T09:00:00Z")
  },
  {
    _id: 7, tenantId: "t1", customerId: "C001",
    status: "PAID", amount: 310000,
    createdAt: ISODate("2026-11-04T08:00:00Z")
  },
  {
    _id: 8, tenantId: "t1", customerId: "C002",
    status: "PENDING", amount: 220000,
    createdAt: ISODate("2026-11-04T09:00:00Z")
  },
  {
    _id: 9, tenantId: "t2", customerId: "C090",
    status: "PAID", amount: 199000,
    createdAt: ISODate("2026-11-05T08:00:00Z")
  },
  {
    _id: 10, tenantId: "t1", customerId: "C004",
    status: "PENDING", amount: 275000,
    createdAt: ISODate("2026-11-05T09:00:00Z")
  }
]);

print("Orders:", orders.countDocuments({}));
```

Bộ mẫu có **10 documents**. Chạy `insertMany` một lần trên database lab trống; nếu lặp lại sẽ có duplicate `_id`. Không dùng `dropDatabase()` trên database có dữ liệu cần giữ.

### 7.2. Thử các query

```javascript
printjson(orders.find({
  tenantId: "t1",
  status: "PENDING"
}).toArray());

printjson(orders.find({
  customerId: "C001"
}).sort({ createdAt: -1 }).toArray());
```

### 7.3. Tạo index ứng viên

```javascript
orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);

orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "idx_customer_created" }
);

printjson(orders.getIndexes());
```

Hai index là ví dụ cho query patterns trong lab, không phải khuyến nghị tạo cả hai ở mọi production collection.

---

## 8. Đọc log hiện có trước khi chỉnh cấu hình

### 8.1. Server tự quản lý trên Linux

Nếu MongoDB ghi diagnostic log ra file, ví dụ:

```text
/var/log/mongodb/mongod.log
```

có thể xem log bằng công cụ OS theo quyền cho phép:

```bash
tail -n 100 /var/log/mongodb/mongod.log
```

Nếu service ghi stdout/stderr qua systemd/container, cần dùng journal/container logging tương ứng.

### 8.2. systemLog.destination

Một cấu hình self-managed tham khảo:

```yaml
systemLog:
  destination: file
  path: /var/log/mongodb/mongod.log
  logAppend: true
  verbosity: 0
  timeStampFormat: iso8601-utc
```

Ý nghĩa:

- `destination: file`: server ghi vào file log.
- `path`: vị trí file.
- `logAppend`: xử lý append theo cấu hình khi server startup.
- `verbosity: 0`: mức logging bình thường, không phải debug tối đa.
- `timeStampFormat`: format timestamp cho logging theo những chế độ được hỗ trợ.

Tùy deployment, logs có thể đi ra stdout/container collector thay vì file, và options có thể do managed service kiểm soát.

### 8.3. getLog không thay cho persistent log file

Nếu tài khoản đủ quyền:

```javascript
db.getSiblingDB("admin").runCommand({
  getLog: "global"
});
```

Lệnh `getLog` trả về thông tin trong **in-memory log buffer** theo cơ chế server, không phải toàn bộ lịch sử log vĩnh viễn.

Dùng nó để kiểm tra nhanh messages gần đây, không thay thế persistent log storage hoặc tập trung log.

### 8.4. Atlas/managed MongoDB

Với MongoDB Atlas, log access, Profiler UI, Real-Time Performance Panel và metrics phụ thuộc cluster tier/service. Không có quyền shell sửa `mongod.conf` chỉ vì bạn có database user.

Sử dụng các công cụ log/metrics/API được nhà cung cấp hỗ trợ. Không giả định mọi MongoDB Atlas tier cho phép bật profiler level 2 hoặc tải mọi log file.

---

## 9. Cấu hình slow-operation threshold và sampling

Ví dụ file config cho **self-managed lab server**:

```yaml
systemLog:
  destination: file
  path: /var/log/mongodb/mongod.log
  logAppend: true
  verbosity: 0

operationProfiling:
  mode: off
  slowOpThresholdMs: 100
  slowOpSampleRate: 1.0
```

Đây là một cấu hình mang tính minh họa: profiler tắt nhưng MongoDB vẫn có thể ghi các thao tác chậm vào diagnostic log theo threshold.

### 9.1. Ngưỡng 100 ms dùng khi nào?

Phù hợp như một mốc khởi đầu để quan sát nhưng chưa chắc là ngưỡng tốt cho ứng dụng:

- API đặt hàng SLO 100 ms: query 70 ms đã chiếm nhiều budget.
- Batch analytics SLO 1 phút: query 500 ms có thể bình thường.
- Client ở xa: network latency lớn không được phản ánh đầy đủ trong server operation duration.

Cần kết hợp metrics/traces và mục tiêu dịch vụ.

### 9.2. Giảm sampling

```yaml
operationProfiling:
  mode: off
  slowOpThresholdMs: 100
  slowOpSampleRate: 0.25
```

Giá trị 0.25 giúp giảm số event được log/profile theo cách sampling được hỗ trợ. Có thể hợp lý khi traffic lớn, nhưng có nguy cơ mất các event hiếm.

### 9.3. Ngưỡng quá thấp

Ví dụ cấu hình sai trong giờ cao điểm:

```yaml
operationProfiling:
  slowOpThresholdMs: 0
  slowOpSampleRate: 1.0
```

Nó có thể biến một lượng rất lớn operations thành events đủ điều kiện slow logging, khiến:

- Log volume tăng mạnh.
- Disk/collector bandwidth tăng.
- Chi phí ingest/storage tăng.
- Alert noise lớn.
- CPU/logging overhead đáng kể.

Chỉ dùng ngưỡng cực thấp trong isolated lab hoặc thời gian debug được kiểm soát.

### 9.4. Threshold là process-level concern

Mức độ tác động của thay đổi threshold/sample có thể vượt phạm vi một query hoặc database. Các phương thức runtime và server config có semantics/phạm vi theo version.

Vì vậy trước khi thay đổi:

1. Đọc trạng thái hiện tại.
2. Xác định tác động lên database khác trên cùng process.
3. Thông báo change window.
4. Chọn thời gian kết thúc tự động/runbook rollback.
5. Quan sát log volume ngay sau khi bật.

Không thay đổi threshold trên production chỉ để một người dùng “có thêm mẫu truy vấn” mà chưa đánh giá ảnh hưởng đến workloads khác.

---

## 10. Dùng mongosh điều chỉnh profiler trong lab

### 10.1. Xem cấu hình

```javascript
const lab = db.getSiblingDB("observability_lab");

printjson(lab.getProfilingStatus());
print("Level:", lab.getProfilingLevel());
```

Một kết quả minh họa:

```json
{
  "was": 0,
  "slowms": 100,
  "sampleRate": 1,
  "ok": 1
}
```

Tên fields và lựa chọn có thể khác khi phiên bản hỗ trợ thêm filter.

### 10.2. Bật profiling slow operations

```javascript
lab.setProfilingLevel(1, {
  slowms: 50,
  sampleRate: 1.0
});
```

Đọc lại:

```javascript
printjson(lab.getProfilingStatus());
```

### 10.3. Query lấy bản ghi profile

```javascript
lab.system.profile
  .find({
    ns: "observability_lab.orders"
  })
  .sort({ ts: -1 })
  .limit(10)
  .pretty();
```

Nếu không có bản ghi, **không có nghĩa hệ thống không có query**. Có thể:

- Không query nào đủ chậm.
- Sampling bỏ qua.
- Profiler chưa được bật.
- Query xảy ra tại process khác.
- User không có quyền đọc `system.profile`.
- Collection capped đã overwrite các records cũ.
- Profiling filter không chọn những thao tác đó.

### 10.4. Tắt profiling sau lab

```javascript
lab.setProfilingLevel(0);
```

Nếu trước đó có threshold/sample/filter khác, phải khôi phục theo snapshot cấu hình đã ghi lại, không chỉ giảm level. Tắt profiler không ngăn slow logging hoàn toàn.

### 10.5. Không dùng mức 2 trên môi trường bận rộn

```javascript
// Cân nhắc chỉ trong lab cô lập.
lab.setProfilingLevel(2);
```

Mức 2 có thể tạo nhiều writes vào `system.profile`; hệ thống cần theo dõi CPU/storage và tránh kéo dài thời gian thu thập.

### 10.6. Môi trường lab có thể không tạo slow record

10 documents được truy vấn trong vài ms nên không đạt 50/100 ms. Đừng cố tạo artificial lock hoặc câu truy vấn ReDoS trên môi trường dùng chung chỉ để nhìn thấy slow query.

Có thể:

- Đọc một mẫu log đã được lưu an toàn.
- Dùng `explain("executionStats")` để học performance counters.
- Trong **isolated local lab** và được phép, tạm hạ slowms trong thời gian rất ngắn, sau đó hoàn nguyên cẩn thận.
- Dùng một dataset representative được cấp phép thay vì dữ liệu production thật.

---

## 11. Những field quan trọng trong slow query entry

Đối với một event slow operation, các thuộc tính thường hữu ích:

| Field | Cách diễn giải | Cảnh báo |
|---|---|---|
| `ns` | Namespace, ví dụ `shop.orders` | Chỉ ra collection/context |
| `type` | Command/op type | Không phải field nào cũng xuất hiện |
| `command` | Phần command/query được ghi | Có thể truncate/redact/chứa dữ liệu nhạy cảm |
| `planSummary` | Tóm tắt plan | Không thay cho full explain |
| `keysExamined` | Index keys đã xét | Lớn chưa chắc sai; cần so với nreturned |
| `docsExamined` | Documents đã xét | Cao có thể là scan rộng |
| `nreturned` | Số kết quả | Với write/getMore semantics có thể khác |
| `durationMillis` | Thời gian theo server | Không đồng nhất client end-to-end latency |
| `numYields` | Số lần operation yield | Không thể kết luận lock contention chỉ từ một số |
| `reslen` | Kích thước response (nếu có) | Dữ liệu lớn làm tăng network cost |
| `locks` | Thông tin lock operations | Interpret theo event/version |
| `storage` | Storage statistics (nếu có) | Không phải mọi log event đều có |
| `planningTimeMicros` | Thời gian lập kế hoạch (nếu có) | Có thể vắng mặt |
| Query/plan shape identifiers | Gom những truy vấn cùng shape | Tên/kiểu field thay đổi theo version |

**Không xem `durationMillis` là thời gian duy nhất mà người dùng đợi**. Application latency còn gồm connection checkout, server selection, network, serialization, retries, pagination và business logic.

### 11.1. Docs examined lớn, nreturned nhỏ

Ví dụ:

```text
planSummary     = COLLSCAN
docsExamined    = 600000
keysExamined    = 0
nreturned       = 8
durationMillis  = 985
```

Đây là dấu hiệu đáng nghi vì MongoDB xem rất nhiều documents nhưng chỉ trả 8.

Hướng điều tra:

1. Xem query filter và sort.
2. Xem `explain("executionStats")`.
3. Đánh giá index phù hợp với equality/sort/range.
4. Kiểm tra query thật có bị thiếu tenant predicate không.
5. Đo trên dữ liệu representative.
6. Chỉ tạo index sau khi xét chi phí ghi/dung lượng.

### 11.2. IXSCAN vẫn có thể chậm

Ví dụ:

```text
planSummary     = IXSCAN { status: 1 }
keysExamined    = 400000
docsExamined    = 400000
nreturned       = 150000
durationMillis  = 1300
```

Ở đây MongoDB dùng index nhưng vẫn đọc/return lượng dữ liệu lớn. Nguyên nhân có thể là filter kém chọn lọc hoặc API không phân trang.

**Có index không đồng nghĩa query nhanh.**

### 11.3. DocsExamined = 0 cũng chưa chắc không chậm

Một query có thể đọc chủ yếu index entries và nhiều keys hoặc chờ locks/replication/network, nên `docsExamined=0` không đảm bảo latency thấp.

Đọc các counters kết hợp, không đánh giá bằng một số riêng.

### 11.4. Sort và giới hạn kết quả

Một slow query có thể có:

- PlanSummary thể hiện scan phù hợp nhưng vẫn phải sort.
- `nreturned` lớn.
- Response document kích thước lớn.
- Pagination dùng `skip` cao.
- Index không khớp sort order.

Cần xem query shape và explain, không chỉ thêm một index trên filter field.

---

## 12. getMore: tại sao API chậm nhưng find ban đầu không chậm?

MongoDB sử dụng cursor cho nhiều truy vấn. Một application gọi `find()`, sau đó driver gọi `getMore` để lấy batch tiếp theo.

```text
Application find()
   │
   ├─ find command  ──> firstBatch
   │
   ├─ getMore       ──> secondBatch
   │
   ├─ getMore       ──> thirdBatch
   │
   └─ cursor exhausted
```

Một `getMore` có thể chậm do:

- Batch lớn.
- Query tiếp tục scan/compute.
- Network traffic.
- Cursor/aggregation workload.
- Server load và concurrent operations.

Nếu chỉ tìm log message chứa `find`, bạn có thể bỏ qua các `getMore` entries ảnh hưởng latency tổng.

### 12.1. Cursor batch size

Ví dụ:

```javascript
const docs = db.getSiblingDB("observability_lab")
  .orders
  .find({ tenantId: "t1" })
  .batchSize(2)
  .toArray();

print("Fetched:", docs.length);
```

Batch size ảnh hưởng các lần trao đổi với server, nhưng không phải mọi batch chắc chắn tạo slow log. Truy vấn lab nhỏ thường quá nhanh.

### 12.2. Aggregation cũng có getMore

`aggregate` với cursor trả dữ liệu theo batch. Một pipeline xử lý lâu có thể xuất hiện ở command hoặc getMore entries khác nhau.

Khi phân tích latency tổng của một API, ghép các batches cùng operation context theo dữ liệu sẵn có; không coi mỗi log line là một API request độc lập.

---

## 13. Dùng explain để kiểm chứng manh mối từ log

Slow log cho biết **triệu chứng đã xảy ra**. `explain` giúp xem cách planner dự định và thực thi một query tương ứng.

### 13.1. Ví dụ find

```javascript
const lab = db.getSiblingDB("observability_lab");

const explainResult = lab.orders
  .find({
    tenantId: "t1",
    status: "PENDING"
  })
  .sort({ createdAt: -1 })
  .explain("executionStats");

printjson(explainResult.queryPlanner);
printjson(explainResult.executionStats);
```

### 13.2. Các số liệu cần so sánh

| Slow log | Explain | Ý nghĩa |
|---|---|---|
| `planSummary` | `winningPlan` | Có thể giúp xác định scan type |
| `docsExamined` | `totalDocsExamined` | Documents scan |
| `keysExamined` | `totalKeysExamined` | Index keys scan |
| `nreturned` | `nReturned` | Số kết quả |
| `durationMillis` | `executionTimeMillis` | Không phải cùng một phép đo tuyệt đối |
| Query command | Query filter/sort/projection | Phải tái tạo shape tương đương |

### 13.3. Vì sao log và explain có thể khác nhau?

- Dữ liệu đã thay đổi sau khi log được ghi.
- Index mới được tạo.
- Query plan cache thay đổi.
- Parameters/selectivity khác.
- Host, shard, primary/secondary khác.
- Client network latency không có trong server explain.
- Một execution là cursor/getMore, còn explain chỉ khảo sát query shape.
- Runtime load thay đổi.
- Server version hoặc optimizer engine thay đổi.

Không dùng explain ở thời điểm sau sự cố rồi nói đó **chắc chắn** là kế hoạch đã chạy trong sự cố.

### 13.4. Cẩn trọng với explain của lệnh ghi

Đừng tái chạy một `deleteMany`, `updateMany` hoặc script migration từ slow log trực tiếp trên production.

Để điều tra, dùng phương thức explain đúng với API và môi trường hỗ trợ, hoặc một bản sao dữ liệu, tránh thực thi operation có tác dụng thay đổi dữ liệu.

### 13.5. Query shape khác literal parameters

Hai query:

```javascript
{ tenantId: "t1", status: "PENDING" }
{ tenantId: "t2", status: "PAID" }
```

có thể thuộc một shape giống nhau nhưng độ chọn lọc khác đáng kể. Khi tổng hợp slow logs, cần phân biệt:

- Shape ổn định cho nhóm vấn đề.
- Distribution của giá trị đầu vào.
- Index selectivity.
- Workload theo tenant.

Nếu log pipeline nhóm mọi trường hợp vào một shape mà không xét selectivity, có thể bỏ qua một tenant có dữ liệu bất thường.

---

## 14. Phân biệt server latency và application latency

Giả sử metrics cho thấy:

```text
HTTP request latency:       1400 ms
MongoDB command duration:    320 ms
Other application work:      900 ms
Network/queue/retry:         180 ms
```

Các số trên chỉ minh họa, nhưng cho thấy `slow log durationMillis` **không nhất thiết bằng HTTP latency**.

Ngược lại:

```text
HTTP request latency:       2000 ms
MongoDB command duration:   1780 ms
Application work:            220 ms
```

cho thấy MongoDB có thể chiếm phần lớn budget.

### 14.1. Server-side slow logs quan sát gì?

Server nhìn thao tác phía database với các counters và timing mà MongoDB ghi.

### 14.2. Driver command monitoring quan sát gì?

Driver thấy thời gian command theo client-side measurement, bao gồm một số overhead mạng/driver; nó không đại diện toàn bộ HTTP request hoặc server internal execution.

### 14.3. APM traces quan sát gì?

Application Performance Monitoring/tracing theo request có thể theo dõi:

- HTTP inbound span.
- Business logic.
- Connection pool wait.
- MongoDB command spans.
- Retry.
- External API calls.

Kết hợp ba nguồn sẽ tốt hơn dùng một con số.

### 14.4. Slow query xuất hiện ít không loại trừ performance problem

Các lý do:

- Threshold quá cao.
- Sample rate thấp.
- Vấn đề nằm ở connection checkout/network.
- Query đã bị timeout trước khi được log theo cách mong đợi.
- Sự cố nằm ở application.
- Bạn đang nhìn log sai process/shard/timezone.
- Managed provider giới hạn log view.
- Vấn đề chỉ xảy ra trong getMore/commit/write concern.

---

## 15. Đọc log trong Linux và container

### 15.1. File diagnostic log

Nếu file đã được cấu hình và bạn có quyền:

```bash
tail -n 200 /var/log/mongodb/mongod.log
```

Có thể tìm text một cách đơn giản:

```bash
grep -F '"msg":"Slow query"' /var/log/mongodb/mongod.log
```

Nhưng raw grep phụ thuộc JSON serialization và một số version/message có thể khác. Dùng structured parser/log platform khi phân tích nhiều phiên bản.

### 15.2. jq trên JSON lines

Một command minh họa:

```bash
jq -c 'select(.msg == "Slow query") | {
  timestamp: .t["$date"],
  component: .c,
  context: .ctx,
  namespace: .attr.ns,
  durationMillis: .attr.durationMillis,
  docsExamined: .attr.docsExamined,
  keysExamined: .attr.keysExamined,
  nreturned: .attr.nreturned,
  planSummary: .attr.planSummary
}' /var/log/mongodb/mongod.log
```

Cú pháp trên giả định mỗi dòng là JSON log object hợp lệ. Với log files chứa nhiều định dạng, parser cần xử lý các lines không hợp lệ và giữ raw logs.

### 15.3. Filter theo ngưỡng

```bash
jq -c 'select(.msg == "Slow query")
  | select((.attr.durationMillis // 0) >= 500)
  | {
      namespace: .attr.ns,
      durationMs: .attr.durationMillis,
      plan: .attr.planSummary
    }' /var/log/mongodb/mongod.log
```

Không hiểu result rỗng là không có slow queries nếu:

- Log không ở file đó.
- Fields khác trong version đang chạy.
- Sampling loại event.
- Log file đã rotate.
- Threshold ban đầu loại operation.

### 15.4. systemd

Trong self-managed Linux dùng systemd, tùy cấu hình:

```bash
journalctl -u mongod --since "2026-11-14 08:00:00"
```

Cần kiểm tra timezone của journal/system và đảm bảo permissions. MongoDB có thể ghi riêng ra file thay vì journal, nên journal không nhất thiết chứa slow query entries.

### 15.5. Container/Kubernetes

Khi container ghi stdout/stderr:

- Tập trung log từ pod/container theo nhãn cluster/member.
- Đánh dấu namespace, host, deployment, replica set.
- Quản lý log rotation của runtime/collector.
- Không log mỗi query document có dữ liệu nhạy cảm.
- Phân biệt restart pod làm mất local logs nếu không có collector.

Ví dụ thao tác khám phá chung:

```bash
kubectl logs <mongodb-pod-name> --since=15m
```

Chỉ dùng khi có quyền và đúng namespace/context. Không assume log output container chứa mọi MongoDB diagnostic messages nếu server đang ghi vào file nội bộ.

### 15.6. Windows PowerShell

Nếu file log là JSON lines và chỉ cần đọc một phần trong lab:

```powershell
Get-Content -LiteralPath "C:\MongoDB\logs\mongod.log" -Tail 100 |
  ForEach-Object {
    try { $_ | ConvertFrom-Json } catch { $null }
  } |
  Where-Object { $_ -and $_.msg -eq "Slow query" } |
  Select-Object t, c, ctx, attr
```

Không áp dụng nguyên lệnh `Get-Content` đọc toàn bộ file log hàng GB trong giờ cao điểm; dùng collector, streaming và giới hạn phạm vi.

---

## 16. Chọn mức chi tiết: verbosity 0 đến debug theo component

MongoDB cho phép cấu hình log verbosity ở mức server và cho từng component.

### 16.1. Mức bình thường

Thông thường nên bắt đầu với:

```yaml
systemLog:
  verbosity: 0
```

Mức 0 không có nghĩa “không log gì”; server vẫn ghi nhiều information/warning/error/slow-operation messages cần thiết.

### 16.2. Debug verbosity

Các debug levels cao hơn như `1` đến `5` có thể tạo thêm messages, tùy component/version.

Không cần hiểu 5 là “tốt nhất”. Nó là **chi tiết hơn**, đồng thời có thể gây:

- Lượng log tăng mạnh.
- Tăng CPU/IO.
- Phát sinh sensitive metadata trong logs.
- Chi phí ingest lớn.
- Khó tìm signal vì noise.
- Ảnh hưởng p95/p99 latency khi logging quá mức.

### 16.3. Component-specific verbosity

Ví dụ cấu hình self-managed:

```yaml
systemLog:
  verbosity: 0
  component:
    command:
      verbosity: 0
    query:
      verbosity: 0
    network:
      verbosity: 0
```

Trong một ca điều tra query planner, có thể tăng tạm component `query` hoặc `command` theo chỉ dẫn phiên bản thay vì tăng global verbosity.

### 16.4. Cơ chế kế thừa

Component log level có thể có giá trị **kế thừa** từ parent/global theo quy tắc configuration. Trong nhiều giao diện, `-1` có nghĩa dùng mức parent.

Nếu trước khi sửa component đã kế thừa global, đặt `0` để “rollback” **không phải luôn giống** khôi phục chế độ kế thừa.

Hãy ghi **giá trị ban đầu**, không chỉ ghi “debug đang ở 1”.

### 16.5. Runtime thay đổi bằng mongosh

MongoDB cung cấp helper:

```javascript
const admin = db.getSiblingDB("admin");

// Đọc cấu hình trước khi đổi.
printjson(admin.runCommand({
  getParameter: 1,
  logComponentVerbosity: 1
}));
```

Trong môi trường lab có quyền:

```javascript
// Thử tăng chi tiết cho component query.
admin.setLogLevel(1, "query");
```

Khi kết thúc, khôi phục mức cũ được ghi nhận, ví dụ nếu ban đầu là 0:

```javascript
admin.setLogLevel(0, "query");
```

**Không đặt về 0 một cách máy móc** nếu trước đó là inherited `-1` hoặc mức tùy chỉnh khác. Các helper/available components và quyền quản trị cần được đối chiếu với MongoDB version.

### 16.6. Thay đổi global verbosity

Có thể dùng `setParameter`/log verbosity APIs theo phiên bản, nhưng thay đổi toàn server có phạm vi ảnh hưởng rộng. Trong môi trường production, ưu tiên targeted component/sampling cùng maintenance/change ticket.

### 16.7. Khi nào verbosity lớn có ích?

Một số tình huống:

- Debug TLS/network handshake.
- Điều tra authentication failures.
- Theo dõi quá trình election/replication.
- Điều tra index build.
- Phân tích planner bất thường.
- Hỗ trợ theo chỉ dẫn của MongoDB Support.

Đối với các tình huống này, phải xác định **component + thời gian + mục tiêu quan sát**. Đừng bật global debug level cao để giải quyết một query chậm đã có đủ `explain`.

---

## 17. Bảng đề xuất mức chi tiết theo môi trường

| Tình huống | Cấu hình khởi đầu | Hành động thêm | Giới hạn |
|---|---|---|---|
| Production bình thường | Global verbosity 0; slow threshold theo SLO; sampling hợp lý | Metrics/traces, alerting | Giữ log volume trong budget |
| API query latency tăng | Slow log + explain + profiler chọn lọc | Tạm giảm slowms ở window nhỏ nếu được phép | Có rollback và monitor |
| Sự cố network/TLS | Global 0; targeted network component debug | Theo host/endpoint/context | Tránh lộ thông tin kết nối |
| Replica set election liên tục | Global 0; replication component logging cần thiết | So election metrics/heartbeats | Nhiều members, đồng bộ thời gian |
| Index build chậm | Index/storage components theo hướng dẫn | serverStatus/currentOp/metrics | Đừng log all query commands |
| Lab nhỏ | Có thể profiler level 1/2 tạm thời | Explain, system.profile | Khôi phục config sau thí nghiệm |
| Benchmark tải cao | Default diagnostic log; profiling chỉ khi cần | APM và metrics sampling | Profiling level 2 có thể làm lệch benchmark |
| Incident có dữ liệu nhạy cảm | Minimize command detail, redaction và RBAC | Chỉ cho nhóm phản ứng sự cố truy cập | Không tải raw logs công khai |
| Sharded cluster | Thu log mongos + shards, gắn topology labels | Slow query ở router và execution nodes | Đừng gộp events thành một query sai |

**Không có một con số verbosity tối ưu cho mọi ứng dụng**. Hãy bắt đầu bằng câu hỏi điều tra, chọn signal đủ để trả lời, và tính chi phí quan sát.

---

## 18. Vì sao log phải được quản lý như dữ liệu nhạy cảm?

Slow-operation logs có thể chứa:

- Query filters với email, số điện thoại, mã khách hàng.
- Fields dùng cho authorization hoặc tenant isolation.
- Update documents với giá trị nhạy cảm.
- Collection/database names tiết lộ kiến trúc nội bộ.
- Truy vấn tài chính.
- Identifiers dùng trong business workflows.
- Dữ liệu liên quan authentication hoặc lỗi certificate.

**Một dòng log có thể chứa data người dùng**, không chỉ thông số hệ thống.

### 18.1. Không copy raw slow query vào ticket public

Ví dụ query:

```javascript
db.customers.find({
  email: "customer@example.com"
});
```

Nếu log ghi `command.filter.email`, chia sẻ nguyên dòng có thể tiết lộ PII.

Thay bằng bản sanitized:

```json
{
  "ns": "shop.customers",
  "queryShape": {
    "email": "<redacted>"
  },
  "planSummary": "COLLSCAN",
  "docsExamined": 250000,
  "nreturned": 1,
  "durationMillis": 450
}
```

Sanitization phải được áp dụng ở nơi phù hợp, có kiểm tra chất lượng và không làm mất thông tin cần thiết phục vụ điều tra.

### 18.2. Server-side log redaction

MongoDB có những khả năng **redact client log data** trong edition/version hỗ trợ, ví dụ cấu hình `security.redactClientLogData` theo tài liệu tương ứng.

Không assume redaction luôn có trong mọi deployment/tier; cũng không assume nó che toàn bộ metadata nhạy cảm hoặc dữ liệu business. Phải xem khả năng, giới hạn và tác động đến giá trị debug.

### 18.3. Quản lý quyền truy cập

- Log file owner và mode/ACL phù hợp.
- Collector có service identity riêng.
- Chỉ team cần thiết đọc raw logs.
- Có audit truy cập logs.
- Encrypt logs at rest và in transit.
- Retention theo policy, không giữ vô hạn.
- Không log credentials trong ứng dụng Java.
- Không gửi logs chứa customer data vào môi trường không được phép.

### 18.4. Debug không được phá vỡ data privacy

Tăng verbosity có thể vô tình ghi thêm command arguments. Vì vậy:

1. Xác định phạm vi dữ liệu có thể xuất hiện.
2. Kiểm tra redaction trước khi bật.
3. Đặt thời gian tự tắt.
4. Không đưa log production vào repo.
5. Xóa/hạn chế truy cập tập log tạm theo retention policy.

---

## 19. Log volume, retention và rotation

### 19.1. Ước lượng dung lượng

Giả sử:

```text
Slow operations:   5000 events/phút
Trung bình:        1.5 KB/event
Trong 60 phút:     5000 × 60 × 1.5 KB
                 = 450000 KB ≈ 439 MiB/giờ
```

Nếu bật toàn bộ debug, lưu lượng có thể cao hơn rất nhiều.

Lưu ý đây là ước tính, cần đo trên log thực tế vì JSON events có kích thước thay đổi mạnh.

### 19.2. Ảnh hưởng khi disk đầy

Nếu `mongod.log` tăng không giới hạn:

- Disk filesystem có thể đầy.
- Server/host services có thể bị ảnh hưởng.
- Log collector có thể backpressure.
- Có thể mất events do rate/ingest limits.
- Tăng chi phí và khó điều tra.

Do đó logging là một phần của capacity planning.

### 19.3. Rotation

MongoDB hỗ trợ log rotation theo cơ chế server. Ví dụ với quyền admin trên deployment tương thích:

```javascript
db.getSiblingDB("admin").runCommand({
  logRotate: 1
});
```

Tùy cấu hình, rotation có thể dùng chế độ rename hoặc reopen. Một số hệ thống phối hợp với OS logrotate/container runtime.

Không đơn giản xóa file đang được `mongod` giữ open rồi nghĩ server lập tức tạo file mới an toàn.

### 19.4. Chọn retention

Xác định:

- Phục vụ điều tra operational: bao nhiêu ngày?
- Yêu cầu bảo mật/compliance: bao lâu?
- Có cần giữ slow queries dạng aggregate metrics lâu hơn raw PII?
- Lưu online hot hay object storage cold?
- Ai có quyền truy cập?
- Có chính sách xóa/tẩy dữ liệu nhạy cảm?

Nhiều hệ thống giữ raw logs ngắn, metrics đã tổng hợp lâu hơn. Quyết định theo nhu cầu và quy định tổ chức.

### 19.5. Compression và export

Nén log files giúp giảm chi phí lưu trữ, nhưng:

- Compression không phải encryption.
- Logs bị truncate trước khi nén không thể phục hồi phần mất.
- Pipeline phải giữ đúng timestamp/host/source metadata.
- Không upload raw logs có PII vào storage public.

---

## 20. Tương quan log từ nhiều node

### 20.1. Replica set

Replica set có nhiều `mongod` processes:

```text
rs0
├── mongo-a (PRIMARY)
├── mongo-b (SECONDARY)
└── mongo-c (SECONDARY)
```

Một slow query log được ghi trên node **thực thi operation**. Nếu application có read preference tới secondary, không nên chỉ xem primary logs.

### 20.2. Sharded cluster

Sharded cluster có:

- `mongos` routers.
- Config server replica set.
- Các shard replica sets.

Logs trên mongos có góc nhìn router; shard mongod logs có thông tin execution tương ứng. Một request có thể sinh events ở nhiều processes.

```text
App
 │
 ▼
mongos router
 ├── shardA mongod
 ├── shardB mongod
 └── shardC mongod
```

Không cộng bừa `durationMillis` của từng shard để ra application latency; nhiều shards có thể chạy song song và router còn có merge/network overhead.

### 20.3. Labels cần có trong log collector

- Environment: production/staging/lab.
- Cluster ID.
- Replica set/shard ID.
- Host/pod name.
- Process type: `mongod` hay `mongos`.
- Server version.
- Region/zone nếu phù hợp.
- Timestamp chuẩn UTC.
- Event severity/component/message ID.

Không lấy `ctx=conn123` ở node A làm cùng connection với `ctx=conn123` ở node B.

### 20.4. Đồng bộ thời gian

Nếu các nodes lệch clock, phân tích chuỗi sự kiện sẽ sai.

Cần:

- NTP/time synchronization.
- Timezone normalization.
- Giữ timestamp gốc.
- Phân biệt log ingestion time với event time.

### 20.5. Query chậm do shard targeting

Khi logs cho thấy cùng một query xuất hiện trên nhiều shards, cần xem:

- Query có đủ shard key predicate không?
- Mongos có broadcast/scatter-gather không?
- Các shard có indexes giống nhau không?
- Một shard bị skew/hotspot không?
- Merge sort hoặc aggregation ở router có tốn tài nguyên không?

Một slow log riêng lẻ trên shard không đủ để kết luận nguyên nhân toàn cluster.

---

## 21. Correlation từ Java application xuống MongoDB

Trong ứng dụng Java, driver có thể cung cấp **command monitoring** qua `CommandListener`.

Cách tiếp cận an toàn là log metadata tối thiểu:

- Command name.
- Database name.
- Request ID trong driver.
- Elapsed time.
- Success/failure.
- Một opaque application trace ID ở context, nếu đã được hệ thống tracing quản lý.

**Không log toàn bộ `event.getCommand()`** trong production một cách mặc định: query chứa dữ liệu khách hàng và update payload có thể nhạy cảm.

### 21.1. Ví dụ Java Sync Driver command listener

Ví dụ dùng Java Sync Driver hiện đại và SLF4J:

```java
import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.TimeUnit;

public final class SafeMongoCommandListener implements CommandListener {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeMongoCommandListener.class);

    @Override
    public void commandStarted(CommandStartedEvent event) {
        LOG.debug(
                "mongo.command.started command={} database={} requestId={}",
                event.getCommandName(),
                event.getDatabaseName(),
                event.getRequestId()
        );
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        LOG.info(
                "mongo.command.succeeded command={} requestId={} elapsedMs={}",
                event.getCommandName(),
                event.getRequestId(),
                event.getElapsedTime(TimeUnit.MILLISECONDS)
        );
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        LOG.warn(
                "mongo.command.failed command={} requestId={} elapsedMs={} errorType={}",
                event.getCommandName(),
                event.getRequestId(),
                event.getElapsedTime(TimeUnit.MILLISECONDS),
                event.getThrowable().getClass().getSimpleName()
        );
    }
}
```

Giải thích:

- Log chỉ metadata, không log command document hay password.
- `requestId` có phạm vi driver/connection; không phải trace ID toàn cluster.
- `elapsedMs` là phép đo client-side, không hoàn toàn giống server `durationMillis`.
- Số lượng INFO events có thể rất lớn. Trong production nên sampling/metrics thay vì INFO từng command không giới hạn.
- Không log exception full stack cho mọi failed command nếu exception có thể chứa dữ liệu nhạy cảm; dùng cơ chế structured error sanitization phù hợp.

### 21.2. Đăng ký listener

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class MongoClientFactory {
    public static MongoClient create() {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                    "MONGODB_URI is missing");
        }

        MongoClientSettings settings = MongoClientSettings.builder()
                .applyConnectionString(new ConnectionString(uri))
                .addCommandListener(new SafeMongoCommandListener())
                .build();

        return MongoClients.create(settings);
    }
}
```

Không hardcode password trong source. MONGODB_URI từ environment vẫn phải được bảo vệ khỏi logging và truy cập trái phép.

### 21.3. Hạn chế của command monitoring

Một command có thể:

- Là retry attempt.
- Tương ứng một batch getMore.
- Có duration khác thời gian mà HTTP request đợi.
- Được trả về thành công dù business operation sau đó thất bại.
- Trả success về protocol nhưng không đạt SLO của API.

Dùng cùng tracing/metrics để hiểu toàn bộ request.

### 21.4. Gắn comment có kiểm soát

MongoDB hỗ trợ `comment` trên nhiều query commands. Một comment ngắn, không chứa dữ liệu nhạy cảm, có thể giúp nhận diện operation trong profiler/diagnostic logs khi được ghi.

Ví dụ trong mongosh:

```javascript
const lab = db.getSiblingDB("observability_lab");

lab.orders.find({
  status: "PENDING"
}).comment("service=checkout;operation=listPending").toArray();
```

Trong Java Driver, một số iterable cung cấp `comment(...)` theo phiên bản API:

```java
import static com.mongodb.client.model.Filters.eq;

orders.find(eq("status", "PENDING"))
      .comment("service=checkout;operation=listPending")
      .limit(20)
      .into(new java.util.ArrayList<>());
```

Các nguyên tắc:

- Comment ngắn, an toàn, không chứa email, token hoặc password.
- Không tạo cardinality cực cao nếu không cần.
- Không mặc định comment xuất hiện trong **mọi** log event.
- Tính năng comment và khả năng ghi nhận phụ thuộc command/driver/server version.
- Comment không thay thế distributed tracing.

### 21.5. Giảm log volume ở Java

Một listener INFO mỗi command có thể biến ứng dụng thành nguồn log lớn. Một cấu hình tốt có thể là:

- Application metrics tổng hợp theo command/namespace/latency.
- Sampling các commands thành công.
- Log failures có throttling/aggregation.
- Log chi tiết tạm thời cho một canary service.
- Server slow log cho operations vượt ngưỡng.
- Alert theo p95/p99 thay vì raw lines count.

---

## 22. Vì sao server-side log và driver log không khớp hoàn toàn?

Giả sử:

```text
Driver event:
  command=find
  elapsedMs=900

Server slow log:
  command=find
  durationMillis=380
```

Các nguyên nhân có thể:

- Network latency.
- TLS overhead.
- Driver scheduling hoặc runtime pauses.
- Server selection/connection pool timing mà listener đo/không đo khác nhau.
- Retries.
- Batches/getMore.
- Differences trong điểm bắt đầu/kết thúc timing.
- Request context không thực sự cùng một command.

Hãy xác minh trước rằng hai events cùng một operation. Không lấy phép trừ 900 - 380 = 520 ms rồi kết luận “network chậm chính xác 520 ms” khi không có trace nhất quán.

### 22.1. Dùng OpenTelemetry/APM

Nếu ứng dụng đã có tracing:

```text
HTTP GET /orders
  ├── validate tenant
  ├── MongoDB find orders
  │   ├── server selection
  │   ├── connection checkout
  │   ├── command
  │   └── cursor batches
  ├── call payment API
  └── serialize JSON
```

Việc theo dõi từng span sẽ cho biết nguồn latency chính, trong khi MongoDB logs cho biết plan và server internals.

### 22.2. Không sao chép raw query documents vào traces

Telemetry là một nơi có thể rò PII. Tốt hơn gắn:

- Namespace đã sanitize.
- Operation type.
- Query shape identifier khi có.
- Document counts.
- Latency.
- Error category.

Không gắn tất cả giá trị `filter` của khách hàng vào span attributes.

---

## 23. Chọn alerting signals thay vì đếm mọi log line

Một dashboard hữu ích có thể hiển thị:

- Slow operations count theo phút.
- Slow log rate theo namespace.
- p50/p95/p99 command duration.
- Query shape có tỷ lệ `docsExamined / nReturned` cao.
- Tỷ lệ error/warning theo component.
- Connection count/pool wait.
- Replication lag/elections.
- Cache/disk utilization.
- Bytes của log ingest theo node.
- Tỷ lệ log bị drop/truncated.
- Tỷ lệ query `COLLSCAN` trong các queries trọng yếu.

### 23.1. Đếm log line có thể đánh lừa

Ví dụ slow event count giảm từ 1000 xuống 100 khi giảm sample rate từ 1.0 xuống 0.1. Đó không phải bằng chứng hệ thống nhanh lên.

Dashboard phải biết sampling policy hoặc dùng metrics độc lập để phân tích.

### 23.2. Threshold thay đổi thì alert thay đổi

Nếu giảm `slowOpThresholdMs` từ 100 xuống 20, số slow logs tăng là điều dễ hiểu. Alerting cần annotation của config changes để tránh báo động nhầm.

### 23.3. Cardinality cao là rủi ro

Đừng đưa nguyên `userId`, `email`, `traceId` của từng request thành labels trong metrics time series. Điều đó gây cardinality explosion và tăng memory/cost.

Có thể giữ opaque trace IDs trong trace/log event dưới policy, nhưng dùng labels/tags với tập giá trị có giới hạn cho aggregation.

### 23.4. Tỷ lệ docsExamined/nReturned

Một heuristic:

```text
scan_ratio = docsExamined / max(nReturned, 1)
```

Tỷ lệ lớn có thể chỉ ra lọc kém hiệu quả.

Nhưng không phải cứ tỷ lệ lớn là index sai:

- Aggregation tạo kết quả tổng hợp có thể trả 1 row từ nhiều docs.
- Analytics cố ý quét nhiều records.
- TTL/maintenance và read workloads khác nhau.
- Query cần count toàn tập.

Dùng theo **query shape và mục tiêu nghiệp vụ**, không xếp hạng tất cả queries bằng một tỷ lệ đơn giản.

---

## 24. Phân tích từng nhóm slow operation

### 24.1. Read chậm vì collection scan

Log minh họa:

```json
{
  "msg": "Slow query",
  "attr": {
    "ns": "shop.orders",
    "planSummary": "COLLSCAN",
    "keysExamined": 0,
    "docsExamined": 450000,
    "nreturned": 10,
    "durationMillis": 820
  }
}
```

Hướng điều tra:

1. Xác định filter/sort/projection.
2. Lấy explain trong môi trường an toàn.
3. Xem missing index và selectivity.
4. Kiểm tra application có bỏ `tenantId` không.
5. Đánh giá index chi phí đọc/ghi.
6. Quan sát sau triển khai index.

### 24.2. Read chậm dù IXSCAN

```json
{
  "msg": "Slow query",
  "attr": {
    "ns": "shop.orders",
    "planSummary": "IXSCAN { status: 1 }",
    "keysExamined": 180000,
    "docsExamined": 170000,
    "nreturned": 90000,
    "durationMillis": 1300
  }
}
```

Có index nhưng phải trả nhiều kết quả. Cân nhắc pagination, projection, index cho filter/sort và business contract.

### 24.3. Write chậm

Slow operation là `update` hoặc `insert` có thể bị ảnh hưởng bởi:

- Nhiều indexes.
- Write concern.
- Replication lag.
- Lock contention.
- Document lớn.
- Storage I/O.
- Large batch.

Không giải quyết write chậm bằng cách tạo thêm indexes một cách máy móc; có thể khiến write nặng hơn.

### 24.4. Aggregation chậm

Aggregation có thể chậm do:

- `$lookup` fan-out.
- `$group` với cardinality cao.
- `$sort` trên dữ liệu lớn.
- `$unwind` làm nở số rows.
- Index không được tận dụng ở đầu pipeline.
- Spill to disk khi được phép.
- Cross-shard merge.

Dùng `explain` của aggregation, pipeline design và metrics tương ứng.

### 24.5. Locks/yields/storage

Một số slow log entries có thông tin về locks, yields, storage và flow control.

Các counters này phải đọc trong ngữ cảnh operation/server version. Ví dụ `numYields` lớn không tự chứng minh đã xảy ra lock bottleneck; MongoDB có thể yield theo cơ chế quản lý concurrency bình thường.

### 24.6. Slow getMore

Một find trả batch đầu nhanh, nhưng một getMore tốn 2 giây. Nếu chỉ nhìn `find` slow events, dashboard sẽ bỏ qua phần chậm nhất.

Gom logs theo cursor/connection context khi khả thi, và so với driver spans.

---

## 25. Quy trình điều tra: từ triệu chứng đến kết luận có kiểm chứng

Giả sử một incident: API `GET /orders?status=PENDING` có p95 tăng 60 → 900 ms sau khi deploy.

### Bước 1 — Ghi rõ cửa sổ và scope

- Từ mấy giờ tới mấy giờ?
- Service/API nào?
- Cluster, region và tenant nào?
- Có deploy/index migration gần đó không?
- Read preference tới node nào?
- Dữ liệu/traffic có tăng đột ngột không?

### Bước 2 — So application metrics với server metrics

Kiểm tra:

- HTTP p95/p99.
- MongoDB command durations.
- Connection pool wait.
- CPU/IO/cache.
- Replication lag.
- Network errors.
- MongoDB error rate.

### Bước 3 — Lọc slow operation logs

Lọc theo:

```text
Time window
Cluster / process
msg = Slow query (hoặc loại tương ứng)
ns = shop.orders
command = find / aggregate / getMore
durationMillis >= ngưỡng điều tra
```

Không bỏ qua entries có component khác mà liên quan storage/replication.

### Bước 4 — Xem query shape và kế hoạch

So:

- PlanSummary.
- KeysExamined.
- DocsExamined.
- NReturned.
- Sort.
- Changed plan/cache.
- Query parameters/selectivity.

### Bước 5 — Dùng explain an toàn

Lấy query shape và kiểm tra trên dữ liệu phù hợp:

```javascript
db.getSiblingDB("observability_lab")
  .orders.find({
    tenantId: "t1",
    status: "PENDING"
  })
  .sort({ createdAt: -1 })
  .explain("executionStats");
```

Không tái chạy lệnh ghi từ raw logs trên production.

### Bước 6 — Chọn can thiệp

Có thể:

- Tạo/sửa compound index sau khi đánh giá.
- Bổ sung tenant predicate.
- Đổi query hoặc projection.
- Phân trang/giới hạn batch size.
- Tách analytics khỏi operational workload.
- Sửa data model.
- Xử lý hotspot/shard targeting.
- Điều chỉnh query timeout.

### Bước 7 — Xác minh

So trước/sau:

- API p95/p99.
- Server command durations.
- Query plan/scan counts.
- Disk/CPU/cache.
- Write overhead do index mới.
- Error rate.

### Bước 8 — Khôi phục log config

Nếu đã tăng verbosity hoặc giảm slowms:

- Trả về cấu hình gốc.
- Đóng temporary debug sink.
- Giữ evidence đã sanitize.
- Ghi timeline incident.
- Đưa bài học vào runbook.
- Không để debug mức cao chạy vô thời hạn.

---

## 26. Một runbook an toàn khi phải tăng log verbosity

### 26.1. Trước khi bật

Ghi:

```text
Incident ID:
Owner:
Environment/cluster:
Target process:
Component:
Current verbosity:
Proposed verbosity:
Current slowOpThresholdMs:
Proposed threshold:
Current sampleRate:
Proposed sampleRate:
Duration of diagnostic window:
Estimated log rate:
Storage/collector headroom:
Rollback owner:
Approval:
```

### 26.2. Trong cửa sổ thu thập

- Giữ global verbosity ở mức bình thường nếu có thể.
- Chỉ tăng component cần thiết.
- Chọn slowms/sample hợp lý.
- Giới hạn target/replica member nếu chính sách cho phép.
- Theo dõi log bytes/s và dropped events.
- Giữ raw sensitive logs trong vùng được phép.
- Không sao chép query values ra các kênh public.

### 26.3. Khi kết thúc

- Khôi phục verbosity **đúng giá trị gốc**, kể cả inherited settings.
- Khôi phục slowms/sample/filter.
- Tắt profiler nếu chỉ bật để điều tra.
- Xác nhận log volume trở lại nền.
- Kiểm tra storage/disk và rotation.
- Lưu bài học cùng sanitized evidence.

### 26.4. Không dùng debug để che lỗi

Một lỗi phổ biến là bật verbosity 5 rồi bỏ quên. Vài giờ sau log disk đầy, ảnh hưởng chính database.

Đặt thời gian kết thúc rõ ngay khi mở debug window. Nếu không đủ thông tin để xác định nguồn slow query, thu thập thêm metrics/tracing thay vì vô hạn tăng logs.

---

## 27. Phân biệt hoạt động truy vấn thường và profiler

Giả sử:

```javascript
const lab = db.getSiblingDB("observability_lab");
lab.setProfilingLevel(0, { slowms: 100, sampleRate: 1.0 });
```

Ý nghĩa:

- Level 0: không lưu operation profiles vào `system.profile`.
- Slow operation threshold: 100 ms theo cấu hình đang áp dụng.
- Sample rate: 1.0 cho các operations đủ điều kiện theo version.
- Diagnostic log vẫn có thể có slow operation events.

Nếu đổi:

```javascript
lab.setProfilingLevel(1, { slowms: 100, sampleRate: 1.0 });
```

thì profiler bắt đầu lưu các slow operations đủ điều kiện vào `system.profile` trên node/database tương ứng.

Nếu đổi:

```javascript
lab.setProfilingLevel(2);
```

profiler ghi rộng hơn; không nên chạy trên production trừ khi có lý do và kiểm soát chặt chẽ.

### 27.1. system.profile có index/retention gì?

Profiler data nằm trong một **capped collection**, có giới hạn dung lượng và có thể overwrite records cũ.

Không coi `system.profile` là kho lưu truy vấn lịch sử vô hạn. Nếu cần lưu dài hạn, thiết kế export/collection pipeline với RBAC và redaction đúng, và kiểm soát chi phí.

### 27.2. Profiler không thay cho audit log

Database profiler ghi dữ liệu để phân tích performance, không bảo đảm đầy đủ mọi security/audit action theo tiêu chuẩn compliance.

Nếu cần audit:

- Dùng database auditing feature hỗ trợ theo edition/deployment.
- Chọn audit events/policy phù hợp.
- Bảo vệ audit logs và retention.
- Không dùng slow logs thay bằng chứng audit.

---

## 28. Structured log schema và parsing robust

Một hệ thống thu log tốt phải:

1. Parse JSON theo từng event.
2. Gắn source metadata.
3. Giữ timestamp gốc.
4. Xử lý optional fields.
5. Tránh lưu toàn command payload nếu không cần.
6. Tương thích thay đổi log schema.
7. Phân loại cả warnings/errors và slow operations.
8. Có giới hạn ingest rate.
9. Có dead-letter handling cho invalid/truncated messages.
10. Kiểm tra pipeline sau MongoDB version upgrades.

### 28.1. Gợi ý schema chuẩn hóa

```json
{
  "eventTime": "2026-11-14T08:20:12.483Z",
  "environment": "production",
  "cluster": "orders-rs",
  "process": "mongo-a",
  "severity": "I",
  "component": "COMMAND",
  "messageId": 51803,
  "messageType": "slow_operation",
  "namespace": "shop.orders",
  "commandType": "find",
  "planSummary": "COLLSCAN",
  "durationMs": 863,
  "keysExamined": 0,
  "docsExamined": 250000,
  "nReturned": 20
}
```

Đây là **schema do hệ thống log pipeline thiết kế**, không phải raw MongoDB schema được bảo đảm tồn tại như vậy.

### 28.2. Không dùng một field bắt buộc cho mọi event

Một slow `getMore` hoặc command error có thể thiếu `nreturned` hoặc dùng field khác. Log parser phải cho phép `null`/missing.

### 28.3. Đừng lưu sensitive filters thành labels

Một filter chứa `customerEmail` có thể là PII. Nếu cần nhóm theo shape, chuẩn hóa tên field/operator và redaction giá trị.

### 28.4. Chênh lệch query identifiers theo version

Các trường liên quan query hash/query shape/plan cache có thể thay đổi giữa MongoDB releases. Kiểm tra docs tương ứng và không xây dashboard phụ thuộc duy nhất vào tên một field cũ.

---

## 29. Bài tập thực hành

### Bài A — Đọc structured JSON log

Cho event:

```json
{
  "t": {
    "$date": "2026-11-14T08:20:12.483Z"
  },
  "s": "I",
  "c": "COMMAND",
  "id": 51803,
  "ctx": "conn42",
  "msg": "Slow query",
  "attr": {
    "ns": "shop.orders",
    "planSummary": "COLLSCAN",
    "keysExamined": 0,
    "docsExamined": 100000,
    "nreturned": 5,
    "durationMillis": 420
  }
}
```

Trả lời:

1. Severity là gì?
2. Component là gì?
3. `id` có phải request ID không?
4. Namespace nào liên quan?
5. Vì sao docsExamined lớn so với nreturned đáng điều tra?
6. Có thể khẳng định nguyên nhân là thiếu index chưa? Vì sao?

### Bài B — Slow logging và profiler

Giải thích khác nhau giữa:

- Profiler level 0 với slowms 100.
- Profiler level 1 với slowms 100.
- Profiler level 2.
- Diagnostic log verbosity 0.
- Component query verbosity 1.

Khi level 0, MongoDB có thể vẫn ghi slow operations ở đâu?

### Bài C — Tạo lab

1. Tạo `observability_lab.orders`.
2. Chạy một query theo status.
3. Xem explain.
4. Tạo compound index.
5. Chạy lại explain.
6. So docsExamined/keysExamined.
7. Giải thích vì sao 10 documents quá ít để benchmark latency.

### Bài D — Query chậm không có trong slow log

Một API p95 là 500 ms nhưng không có slow messages.

Hãy liệt kê tối thiểu sáu giả thuyết, gồm threshold, sampling, process sai, network/client, connection pool, getMore và server/application timing.

### Bài E — Log sampling

Giả sử 10.000 slow operations/giờ ở sample rate 1.0. Sau đó giảm sample rate còn 0.1, log dashboard chỉ có khoảng 1.000 events.

Có thể kết luận MongoDB nhanh lên 10 lần không? Phải chuẩn hóa như thế nào khi so trends?

### Bài F — Chọn verbosity

Một cluster production có lỗi authentication thất thường. Bạn đang định bật global verbosity 5.

Hãy đề xuất cách:

1. Chọn component chính xác.
2. Đặt verbosity thấp nhất đủ điều tra.
3. Giới hạn cửa sổ.
4. Bảo vệ secrets.
5. Quan sát log volume.
6. Rollback đúng mức ban đầu.

### Bài G — Parsing bằng jq

Cho file JSON lines:

- Lọc `msg="Slow query"`.
- Lấy `attr.ns`, `durationMillis`, `planSummary`.
- Chọn duration trên 500 ms.
- Cho phép field thiếu.
- Tránh xuất raw sensitive command.

### Bài H — Correlation Java/MongoDB

Một Java Driver commandSucceeded event có 800 ms, trong khi slow log MongoDB ghi 300 ms.

Giải thích những lý do có thể khiến hai giá trị khác nhau; đề xuất cách dùng tracing và không log `getCommand()`.

### Bài I — Sharded cluster

Một query scatter-gather chạy qua ba shards. Router log ghi tổng 900 ms, từng shard ghi 300/400/600 ms.

Có thể cộng 300 + 400 + 600 thành 1300 ms rồi coi là request latency không? Vì sao? Cần thêm dữ liệu gì về merge và shard targeting?

### Bài J — Redaction và privacy

Log có query:

```javascript
db.customers.find({
  email: "alice@example.com",
  phone: "0900000000"
});
```

Thiết kế một schema normalized để dashboard vẫn thấy namespace, query shape, scan counts, duration nhưng không lộ email/phone.

### Bài K — Alerting

Một dashboard alert theo số `Slow query` messages vượt 100/phút.

Sau một deploy, `slowOpThresholdMs` giảm 100 xuống 20 và sample rate từ 1.0 xuống 0.5.

Làm sao phân biệt tăng log do thay đổi cấu hình với tăng query latency thật? Cần chú thích config changes và theo dõi metrics nào?

### Bài L — Incident runbook

Viết quy trình phản ứng khi API latency tăng:

- Scope/time window.
- Application metrics.
- Server logs.
- Profiler có kiểm soát.
- Explain.
- Index/plan/locking/sharding.
- Mitigation.
- Verification.
- Config rollback.
- Sanitized incident report.

---

## 30. Checklist production logging

### 30.1. Cấu hình nền

- [ ] Biết rõ logs của `mongod`/`mongos` đang được ghi ở đâu.
- [ ] Dùng structured JSON parsing trên phiên bản hỗ trợ.
- [ ] Gắn đúng host/process/cluster labels.
- [ ] Timestamp và timezone nhất quán.
- [ ] Global verbosity ở mức phù hợp, thường là 0.
- [ ] Slow threshold phù hợp performance SLO.
- [ ] Sampling được ghi nhận và phản ánh trong metrics.

### 30.2. Điều tra chậm

- [ ] Không lẫn server slow log với profiler.
- [ ] Biết profiler level hiện tại.
- [ ] Xác nhận có `system.profile` và quyền đọc trên database cần kiểm tra.
- [ ] Đọc `ns`, `command`, `durationMillis`, `planSummary`.
- [ ] So `keysExamined`/`docsExamined`/`nreturned`.
- [ ] Không suy ra IXSCAN luôn là tối ưu.
- [ ] Không bỏ qua `aggregate`/`getMore`/write operations.
- [ ] Dùng explain với query shape tương ứng.
- [ ] Tách client, network, driver và server latency.
- [ ] Kiểm tra workload/tenant/shard distribution.

### 30.3. Mức chi tiết

- [ ] Tăng theo component khi cần.
- [ ] Không bật global debug quá cao một cách mặc định.
- [ ] Có change owner và thời gian kết thúc.
- [ ] Ghi cấu hình gốc để rollback chính xác.
- [ ] Theo dõi bytes/s, disk, collector queues.
- [ ] Tắt profiling level 2 sau điều tra.
- [ ] Không để slowms 0/sampleRate 1.0 trên production lâu dài.
- [ ] Đã xem version-specific log component options.

### 30.4. Bảo mật và lưu trữ

- [ ] Không log password, token hoặc raw PII.
- [ ] Raw command payload được redacted/sanitized khi cần.
- [ ] Log collector có RBAC.
- [ ] Logs được mã hóa khi truyền và lưu.
- [ ] Có rotation và retention.
- [ ] Tránh metric label cardinality quá cao.
- [ ] Có xử lý parser errors/truncation.
- [ ] Có audit truy cập log.
- [ ] Không coi profiler là security audit log.

### 30.5. Sau sự cố

- [ ] Đã xác minh mitigation bằng performance metrics.
- [ ] Đã khôi phục verbosity/threshold/sample/filter.
- [ ] Đã kiểm tra log volume trở lại mức bình thường.
- [ ] Có report đã loại thông tin nhạy cảm.
- [ ] Cập nhật runbook và alerting.

---

## 31. Những nhầm lẫn cần tránh

| Nhầm lẫn | Sự thật |
|---|---|
| Slow query log là file riêng cố định | Thường là event trong diagnostic log |
| Profiler level 0 nghĩa là không có slow logs | Server diagnostic log vẫn có thể ghi slow operations |
| Profiler level 2 miễn phí | Có CPU/write/storage overhead lớn |
| Verbosity 5 là mức “chuẩn production” | Mức debug cao thường tạo log volume rất lớn |
| Cứ giảm slowms xuống 0 là tốt | Có thể gây log storm |
| Sampling 0.1 làm database nhanh hơn 10 lần | Nó chỉ giảm event được thu thập theo cơ chế sampling |
| severity I nghĩa là không quan trọng | Slow query có thể được log ở mức informational |
| id là ID duy nhất của query | Message ID mô tả loại sự kiện |
| ctx giống trace ID xuyên suốt | Context thường là connection/thread, có thể tái sử dụng |
| Log command luôn đầy đủ | Có thể truncate/redact/thiếu fields |
| COLLSCAN luôn là bug | Trên tập nhỏ hay query chọn phần lớn data, nó có thể hợp lý |
| IXSCAN luôn nhanh | Có thể quét hàng triệu keys |
| docsExamined/nReturned cao luôn sai | Analytics/aggregation có mục đích scan lớn |
| durationMillis bằng HTTP latency | Client/network/business logic còn thêm thời gian |
| Không thấy slow log là không có query chậm | Có threshold/sample/tier/process/timezone |
| find nhanh nghĩa là API đọc nhanh | getMore/cursor batches có thể chậm |
| Tăng global debug giải quyết root cause | Logs chỉ cung cấp bằng chứng |
| Cứ log toàn query document là dễ debug | Rủi ro PII/secrets |
| Dùng `system.profile` thay audit log | Mục tiêu khác nhau |
| Logs của mongos bao gồm mọi chi tiết shard | Phải kết hợp router và shard logs |
| Nhìn logs trên primary là đủ | Read preference có thể dùng secondary |
| Drop/delete log file đang mở là cách rotate an toàn | Phải dùng cơ chế rotation phù hợp |
| Trả verbosity về 0 luôn khôi phục ban đầu | Component có thể kế thừa mức khác |
| Bật debug xong có thể để đó | Cần thời gian kết thúc và rollback |

---

## 32. Tài liệu MongoDB chính thức

- [MongoDB Manual – Log Messages](https://www.mongodb.com/docs/manual/reference/log-messages/)
- [MongoDB Manual – Log Message Verbosity Levels](https://www.mongodb.com/docs/manual/reference/log-messages/#verbosity-levels)
- [MongoDB Manual – Log Components](https://www.mongodb.com/docs/manual/reference/log-messages/#log-components)
- [MongoDB Manual – Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB Manual – db.setProfilingLevel()](https://www.mongodb.com/docs/manual/reference/method/db.setProfilingLevel/)
- [MongoDB Manual – db.getProfilingStatus()](https://www.mongodb.com/docs/manual/reference/method/db.getProfilingStatus/)
- [MongoDB Manual – db.setLogLevel()](https://www.mongodb.com/docs/manual/reference/method/db.setLogLevel/)
- [MongoDB Manual – systemLog Configuration](https://www.mongodb.com/docs/manual/reference/configuration-options/#systemlog-options)
- [MongoDB Manual – operationProfiling Configuration](https://www.mongodb.com/docs/manual/reference/configuration-options/#operationprofiling-options)
- [MongoDB Manual – Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual – Database Commands / getLog](https://www.mongodb.com/docs/manual/reference/command/getLog/)
- [MongoDB Manual – logRotate Command](https://www.mongodb.com/docs/manual/reference/command/logRotate/)
- [MongoDB Java Sync Driver – Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/monitoring-and-logging/monitoring/)
- [MongoDB Java Sync Driver – Logging](https://www.mongodb.com/docs/drivers/java/sync/current/monitoring-and-logging/logging/)
- [MongoDB Atlas – Query Profiler](https://www.mongodb.com/docs/atlas/tutorial/profile-database/)
- [MongoDB Atlas – Monitoring](https://www.mongodb.com/docs/atlas/monitoring-alerts/)

> **Lưu ý phiên bản:** Trường JSON logs, tên components, khả năng filter/profile, các runtime parameters và tính năng managed deployment có thể thay đổi. Trước khi áp dụng lệnh thay đổi cấu hình, kiểm tra documentation của **đúng MongoDB Server version, MongoDB Atlas tier (nếu có), và MongoDB Java Driver version** đang triển khai.

## 33. Kết luận

MongoDB có nhiều nguồn dữ liệu quan sát, nhưng mỗi nguồn trả lời một câu hỏi khác nhau:

1. **Structured diagnostic logs** giúp theo dõi tình trạng hệ thống bằng những events có timestamp, severity, component, message ID, context và structured attributes.
2. **Slow-operation logs** giúp tìm các `find`, `aggregate`, `getMore` hoặc write commands bị coi là chậm theo threshold/sample/filter.
3. **Database profiler** lưu profile records vào `system.profile` trên `mongod` khi được bật; **level 0 không có nghĩa diagnostic slow logging cũng dừng**.
4. **Explain và metrics/tracing** là bước xác minh nguyên nhân: COLLSCAN, IXSCAN, scan ratio, sort, locking, sharding, network và application overhead.
5. **Verbosity phù hợp** là mức thấp nhất đủ trả lời câu hỏi điều tra. Hãy ưu tiên debug theo component và trong cửa sổ thời gian xác định.
6. **Log là dữ liệu có thể nhạy cảm**: cần redaction, RBAC, encryption, retention, rotation và tránh ghi raw query/password.
7. **Đóng incident phải bao gồm rollback cấu hình logging**. Không để slowms cực thấp, profiler level 2 hoặc verbosity cao tiếp tục chạy trên production chỉ vì quên khôi phục.

Một hệ thống quan sát tốt không cố ghi **mọi thao tác**, mà thu thập **đúng tín hiệu**, đủ độ chi tiết để điều tra, đủ an toàn để vận hành lâu dài và đủ ít tác động để việc đo lường không trở thành nguyên nhân làm MongoDB chậm thêm.
