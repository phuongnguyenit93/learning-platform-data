# Chỉ số cần theo dõi: độ trễ, lưu lượng, lỗi và kết nối

Một hệ thống dùng **MongoDB** có thể vận hành bình thường hàng tháng, sau đó bất ngờ xuất hiện hiện tượng API chậm, tăng số request thất bại, worker bị timeout hoặc mất kết nối tới primary. Khi đó, câu hỏi quan trọng không chỉ là “MongoDB có còn chạy không?” mà còn là:

- Người dùng phải chờ bao lâu để một yêu cầu được hoàn tất?
- Mỗi giây database đang nhận và xử lý bao nhiêu thao tác?
- Bao nhiêu thao tác thất bại, lỗi do thành phần nào và tỉ lệ lỗi đang tăng hay giảm?
- Số kết nối đang mở, đang hoạt động, đang chờ trong connection pool có bình thường không?
- Tài nguyên hoặc topology nào đang gây ra biến động đó?
- Có thể phát hiện vấn đề **trước** khi hệ thống quá tải và có bằng chứng để xử lý không?

Đây là các câu hỏi thuộc **observability** — khả năng quan sát hệ thống từ metrics, logs và traces — chứ không chỉ là hoạt động nhìn vào CPU hay thử chạy `db.collection.findOne()`.

Trong các mô hình giám sát hệ thống, **độ trễ (latency)**, **lưu lượng (traffic)**, **lỗi (errors)** và **độ bão hòa (saturation)** thường được gọi là *four golden signals*. Với một ứng dụng MongoDB, **kết nối (connections)** là một chỉ số đặc biệt quan trọng vì nó phản ánh cả nguồn tải, connection pooling, khả năng truy cập server và tình trạng nghẽn.

Bài học **“Chỉ số cần theo dõi: độ trễ, lưu lượng, lỗi và kết nối”** trong chương **Quan sát hệ thống** giải thích cách định nghĩa bốn nhóm tín hiệu này, thu thập số liệu từ ứng dụng, driver và MongoDB, đọc các bộ đếm đúng cách, thiết kế dashboard/alerts, xác định nguyên nhân sự cố và thực hành các phép đo an toàn.

> **Nguyên tắc đầu tiên:** Một metric chỉ có ý nghĩa khi biết **nó đo ở lớp nào, đơn vị gì, lấy mẫu trong khoảng nào, áp dụng cho node/tenant/operation nào, và có bao gồm phần chờ đợi/retry hay không**. Không coi một con số “latency 10 ms” là toàn bộ thời gian người dùng phải chờ nếu chưa xác định điểm bắt đầu và kết thúc phép đo.

## 1. Bức tranh tổng thể của một request MongoDB

Một request HTTP từ người dùng có thể đi qua nhiều thành phần:

```text
Người dùng
    │
    ▼
Load balancer / API Gateway
    │
    ▼
Application server
    │
    ├── AuthN/AuthZ, validation
    ├── Business logic
    │
    ▼
MongoDB Driver
    │
    ├── Server selection
    ├── Connection pool checkout
    ├── Serialization BSON
    ├── Network / TLS
    │
    ▼
mongos hoặc mongod
    │
    ├── Query planning / index access
    ├── WiredTiger cache / disk I/O
    ├── Locks / tickets / scheduling
    ├── Replication / write concern
    │
    ▼
MongoDB Driver
    │
    ▼
Application transformation
    │
    ▼
HTTP response
```

Ví dụ một API `/orders/search` trả sau **850 ms** nhưng MongoDB xử lý phần query tương ứng trong **35 ms**. Phần thời gian còn lại có thể đến từ:

- Đợi một connection rảnh trong pool;
- Đợi server selection sau failover;
- Nhiều câu query nhỏ chạy tuần tự;
- Network round trips;
- BSON decoding;
- Logic mapping/authorization;
- Gọi service khác;
- Retry hoặc timeout;
- Application thread pool bị nghẽn.

Ngược lại, nếu API chậm 850 ms và MongoDB operation kéo dài 800 ms, cần kiểm tra query plan, index, CPU, disk, locks và số concurrent operations.

**Chỉ số ở từng lớp phải được đối chiếu, không thay thế cho nhau.**

### 1.1. Ba lớp quan sát tối thiểu

| Lớp | Nhìn thấy gì? | Công cụ |
|---|---|---|
| Application/API | Thời gian người dùng chờ, HTTP errors, business traffic | Metrics, APM, OpenTelemetry, structured logs |
| MongoDB Driver | Command timing, failures, pool checkout, server selection, retries | Driver listeners, tracing, pool metrics |
| MongoDB Server/Atlas | Operations, network traffic, connections, cache, replication, query activity | Atlas Monitoring, `serverStatus`, `mongostat`, profiler, logs |

Một dashboard chỉ nhìn server metrics không tự giải thích mọi lỗi HTTP. Một dashboard chỉ nhìn HTTP không chỉ ra root cause trong MongoDB.

## 2. Định nghĩa độ trễ đúng trước khi đo

**Latency** là thời gian từ một điểm bắt đầu tới một điểm kết thúc của một hoạt động.

Trong ứng dụng MongoDB có nhiều định nghĩa khác nhau:

- **End-to-end request latency:** từ khi API nhận request đến khi response hoàn tất.
- **Database logical operation latency:** toàn bộ thời gian ứng dụng cần để hoàn thành một tác vụ database, có thể gồm nhiều commands và retries.
- **Driver command elapsed time:** thời gian driver đo cho một command đã gửi/tương tác với server theo cơ chế monitoring.
- **Server operation latency:** thời gian xử lý operation trong MongoDB server theo thống kê server.
- **Connection checkout wait:** thời gian chờ lấy connection từ pool.
- **Server-selection wait:** thời gian driver tìm được một server phù hợp với read preference/topology.
- **Replication/write concern wait:** thời gian cần để đạt yêu cầu xác nhận ghi.
- **Network latency:** thời gian truyền dữ liệu và round trips.

Không đặt tất cả chúng dưới một metric tên `mongodb_latency_ms` nếu cách đo khác nhau.

### 2.1. Một request có thể tạo nhiều MongoDB commands

Ví dụ:

```text
HTTP GET /orders
    │
    ├── Query orders           40 ms
    ├── Query customer         20 ms
    ├── Query permissions      15 ms
    └── Business processing    25 ms
```

Nếu các thao tác chạy tuần tự và không có các chờ khác, latency tối thiểu đã khoảng 100 ms. Server có thể báo các reads riêng lẻ nhanh hơn nhiều so với toàn bộ API.

Vì vậy, khi theo dõi hiệu năng phải phân biệt **latency per command** và **latency per business request**.

### 2.2. Đơn vị

| Đại lượng | Đơn vị nên thể hiện |
|---|---|
| HTTP latency | ms hoặc s |
| Driver command duration | ms |
| MongoDB `opLatencies.*.latency` | Tổng microseconds tích lũy theo loại operation |
| Connection checkout wait | ms |
| Replication lag | s |
| Network bytes/sec | B/s, KiB/s, MiB/s |
| Throughput | requests/s hoặc operations/s |
| Error rate | errors/s hoặc % |
| Connection counts | Số kết nối, không phải requests/s |

Không lấy microseconds chia thành milliseconds rồi quên hệ số **1.000**. Một báo cáo sai đơn vị có thể khiến nhận định “MongoDB chậm gấp nghìn lần” xuất hiện dù hệ thống bình thường.

## 3. Trung bình khác p95, p99

Một metric trung bình có thể che trải nghiệm xấu của một nhóm người dùng.

Ví dụ có 100 requests:

```text
95 requests:  50 ms
4 requests:  500 ms
1 request:   5000 ms
```

Trung bình:

\[
\text{mean} = \frac{95 \times 50+4 \times 500+5000}{100}=117.5\text{ ms}
\]

Trong khi đó, request chậm nhất mất **5 giây**.

Các percentile phổ biến:

- **p50:** khoảng 50% quan sát không vượt giá trị này.
- **p95:** khoảng 95% quan sát không vượt giá trị này.
- **p99:** khoảng 99% quan sát không vượt giá trị này.
- **max:** thời gian lớn nhất trong cửa sổ đo.

### 3.1. Vì sao nên xem p95/p99?

Với API trả hàng triệu requests mỗi ngày, 1% requests chậm vẫn có thể ảnh hưởng tới hàng nghìn người dùng. Mean thấp không chứng minh tail latency tốt.

Một dashboard latency nên có tối thiểu:

```text
api_request_latency_ms
  p50
  p95
  p99

mongodb_command_latency_ms
  p50
  p95
  p99

mongodb_pool_checkout_wait_ms
  p95
  p99
```

Không nên chỉ lấy một percentile duy nhất. p99 rất nhạy với số lượng mẫu và noise nếu lượng traffic thấp.

### 3.2. Percentile phải được tính từ phân phối, không từ trung bình

Sai:

```text
Server A p95 = 100 ms
Server B p95 = 500 ms
Global p95 = (100+500)/2 = 300 ms
```

Global p95 **không phải trung bình của p95 các server**. Cần tổng hợp histogram hoặc tập samples theo cách thống kê phù hợp, có trọng số theo lượng request.

Nếu hệ thống xuất histogram, dùng hàm aggregation/histogram quantile đúng theo telemetry backend; đừng tính trung bình của các p95 theo node.

### 3.3. Histogram buckets và cận

Histogram có thể dùng buckets:

```text
<= 10 ms
<= 25 ms
<= 50 ms
<= 100 ms
<= 250 ms
<= 500 ms
<= 1000 ms
> 1000 ms
```

Histogram hỗ trợ ước lượng percentile và tỷ lệ request đạt SLO. Nhưng bucket quá thô làm sai số ước lượng lớn. Chọn buckets phù hợp với SLO, không phải mặc định mọi hệ thống đều cần cùng boundaries.

## 4. MongoDB `opLatencies`: hiểu đúng bộ đếm trên server

MongoDB có thông tin thống kê operation latency trong `serverStatus()`.

Ví dụ đọc một số trường:

```javascript
const s = db.serverStatus();

printjson({
  serverTime: s.localTime,
  uptimeSeconds: s.uptime,
  opLatencies: s.opLatencies
});
```

Ở những phiên bản hỗ trợ, `opLatencies` chứa các nhóm như:

```javascript
{
  reads: {
    latency: NumberLong("..."),
    ops: NumberLong("...")
  },
  writes: {
    latency: NumberLong("..."),
    ops: NumberLong("...")
  },
  commands: {
    latency: NumberLong("..."),
    ops: NumberLong("...")
  }
}
```

**Đây là biểu diễn rút gọn**, output thực tế có thể có các trường khác/histogram tùy phiên bản.

- `ops`: số operations tích lũy thuộc nhóm.
- `latency`: tổng thời gian microseconds tích lũy thuộc nhóm.
- `reads`/`writes`/`commands`: các nhóm operation theo phân loại của MongoDB, không đồng nghĩa ba endpoint nghiệp vụ.

### 4.1. Cách tính trung bình từ hai mẫu

Giả sử tại \(t_1\):

```text
reads.ops = 1.000.000
reads.latency = 40.000.000 μs
```

Tại \(t_2\), sau 60 giây:

```text
reads.ops = 1.006.000
reads.latency = 41.500.000 μs
```

Khi đó:

\[
\Delta ops=6000
\]

\[
\Delta latency=1.500.000\ \mu s
\]

\[
\text{trung bình}=\frac{1.500.000}{6000}=250\ \mu s=0.25\text{ ms}
\]

\[
\text{read throughput}=\frac{6000}{60}=100\text{ ops/s}
\]

Các con số chỉ là ví dụ. Điều quan trọng là **lấy chênh lệch cùng cửa sổ**, không chia tổng tích lũy từ khi server khởi động rồi gọi đó là latency trong một phút gần nhất.

### 4.2. `opLatencies` không phải p95 ứng dụng

Ngay cả khi có mean reads là 0.25 ms:

- Không suy được p95 của HTTP API;
- Không suy được driver pool wait;
- Không suy được percentile nếu chỉ có `ops` và tổng `latency`;
- Không phân tách được thao tác thuộc endpoint nào nếu không có nhãn/correlation;
- Không cho biết network RTT.

Với percentile, dùng histogram/tracing/driver instrumentation hoặc Atlas metrics phù hợp.

### 4.3. Counter reset khi restart

`serverStatus()` có nhiều bộ đếm **tích lũy từ thời điểm khởi động process**. Khi `mongod` restart, counter có thể về nhỏ hơn.

Nếu tính:

```text
delta = counter_now - counter_previous
```

và delta âm, cần coi đây là **counter reset/series change**, không ghi throughput âm.

Cũng phải tránh ghép số liệu từ hai nodes khác nhau thành một chuỗi duy nhất. Một primary stepdown có thể làm exporter đi từ node A sang node B với counters khác.

## 5. Cách lấy mẫu latency bằng `mongosh` an toàn

Ví dụ đọc hai lần `serverStatus()` cách nhau mười giây:

```javascript
const first = db.serverStatus();
sleep(10000);
const second = db.serverStatus();

const seconds =
  (second.localTime.getTime() - first.localTime.getTime()) / 1000;

function readRate(groupName) {
  const before = first.opLatencies[groupName];
  const after = second.opLatencies[groupName];

  const opsDelta = Number(after.ops) - Number(before.ops);
  const latencyDeltaUs =
    Number(after.latency) - Number(before.latency);

  if (seconds <= 0 || opsDelta < 0 || latencyDeltaUs < 0) {
    return { valid: false, reason: "invalid-window-or-counter-reset" };
  }

  return {
    valid: true,
    operationsPerSecond: opsDelta / seconds,
    meanLatencyMs:
      opsDelta > 0 ? latencyDeltaUs / opsDelta / 1000 : null
  };
}

printjson({
  windowSeconds: seconds,
  reads: readRate("reads"),
  writes: readRate("writes"),
  commands: readRate("commands")
});
```

**Mục đích của ví dụ là minh họa delta counters**, không phải một monitoring exporter production. Với counters rất lớn, việc ép BSON `Long` thành JavaScript `Number` có thể mất độ chính xác; exporter thật nên dùng numeric handling/telemetry library phù hợp.

`db.serverStatus()` có thể cần quyền `serverStatus`/`clusterMonitor`. Lệnh chỉ đọc số liệu, nhưng output đầy đủ chứa metadata hạ tầng; không đưa raw output lên một trang công khai.

### 5.1. Không sampling quá dày

Lấy `serverStatus` mỗi vài milliseconds trên mọi node không bảo đảm quan sát tốt hơn. Nó tăng overhead, noise và storage. Chọn interval theo SLO/monitoring system, thường là vài giây đến vài chục giây, kết hợp event traces khi cần chi tiết.

### 5.2. Cửa sổ đo phải được ghi rõ

Một biểu đồ nên ghi:

```text
read_ops_per_second over 60s
read_mean_latency_ms over 60s
api_p95_latency_ms over 5m
```

Nếu không biết window, việc so sánh hai hệ thống có thể sai.

## 6. Lưu lượng: đo đúng “bao nhiêu việc đang được xử lý”

**Traffic** có thể được mô tả ở nhiều mức:

- HTTP requests/second;
- Business operations/second: checkout, search, purchase;
- MongoDB commands/second;
- Reads/writes/second trên `mongod`;
- Query/document throughput;
- Network bytes in/out;
- Change stream events/second;
- Search queries/second.

Những con số này **không tương đương**.

Ví dụ:

```text
100 HTTP requests/s
   │
   ├── mỗi request gọi 3 MongoDB commands
   └── một phần có retry
             │
             ▼
Có thể >300 MongoDB commands/s
```

Ngược lại, một MongoDB command có thể trả hàng nghìn documents. Không lấy số documents returned làm QPS.

### 6.1. `opcounters`

Dùng:

```javascript
const s = db.serverStatus();

printjson({
  opcounters: s.opcounters
});
```

Output thường có các nhóm như:

```text
insert
query
update
delete
getmore
command
```

Đây là những counters theo cách MongoDB phân loại operations. Trên các phiên bản/protocol khác nhau, không phải tất cả hoạt động logic do ứng dụng gọi đều ánh xạ một-một với nhóm counter mà người mới đoán từ tên.

### 6.2. Phân biệt `opcounters` và `opLatencies`

`opcounters` giúp theo dõi **loại operations và số lần**; `opLatencies` giúp theo dõi tổng thời gian xử lý và số operations trong các nhóm latency.

Không so sánh số `opcounters.query` trực tiếp với `opLatencies.reads.ops` rồi mặc định chúng phải bằng nhau. Định nghĩa và phân loại không nhất thiết trùng.

### 6.3. Theo dõi lưu lượng replication riêng

Khi xem metrics node replica set, cần phân biệt:

- Operations do client gửi;
- Hoạt động apply từ replication;
- Internal commands;
- Network giữa các members.

`serverStatus()` có các nhóm thống kê replication-related tùy phiên bản, chẳng hạn `opcountersRepl` trong output hỗ trợ. Nếu cộng mọi counter của các nodes và coi đó là số request người dùng, dễ **đếm lặp**.

Một write của ứng dụng có thể xuất hiện trên primary và được replicate tới secondaries, nhưng đó không phải nhiều business writes độc lập.

## 7. Network throughput: `bytesIn`, `bytesOut`, `numRequests`

Một nhóm thông tin từ `serverStatus()`:

```javascript
const s = db.serverStatus();

printjson({
  network: {
    bytesIn: s.network && s.network.bytesIn,
    bytesOut: s.network && s.network.bytesOut,
    numRequests: s.network && s.network.numRequests
  }
});
```

Các trường phổ biến:

- `bytesIn`: bytes mà server đã nhận theo cơ chế đếm của MongoDB.
- `bytesOut`: bytes server đã gửi.
- `numRequests`: số requests được server ghi nhận.
- Có thể có những trường network khác tùy phiên bản.

Đây thường là **counters tích lũy**, không phải bytes/s sẵn có.

### 7.1. Tính bytes/s

Giả sử:

```text
T1 bytesOut = 1.000.000.000
T2 bytesOut = 1.120.000.000
Khoảng đo = 60 giây
```

\[
\text{outbound throughput}=
\frac{120.000.000}{60}=
2.000.000\text{ bytes/s}
\]

Có thể quy đổi sang MiB/s nếu dashboard muốn. Cần nhất quán giữa **MB (10^6 bytes)** và **MiB (2^20 bytes)**.

### 7.2. Vì sao network throughput tăng?

Những nguyên nhân:

- Search endpoint trả nhiều documents;
- API bỏ projection và truyền field lớn/array;
- Aggregation xuất dataset lớn;
- Backup/export job;
- Change stream consumer;
- Client retry;
- Shard scatter-gather;
- Internal replication;
- Query result batching/getMore.

Không kết luận “có tấn công” chỉ vì bytesOut tăng. Đối chiếu thời điểm, nguồn kết nối, app traffic, authentication và business releases.

### 7.3. Network traffic không phải số request HTTP

Server `network.numRequests` đếm requests đến MongoDB theo semantics của server, không phải HTTP requests đến application. Để tính request error rate của API, phải dùng **HTTP counters** từ ứng dụng/gateway.

## 8. Đo error rate: định nghĩa “lỗi” trước khi đặt alert

Không có một chỉ số lỗi MongoDB duy nhất phù hợp cho mọi nghiệp vụ.

Các loại cần tách:

1. **Application errors:** HTTP 5xx, lỗi nghiệp vụ không mong đợi.
2. **Driver errors:** server selection timeout, pool checkout timeout, network/socket errors.
3. **MongoDB command errors:** duplicate key, unauthorized, validation error, interrupted operation, exceeded time limit.
4. **Write concern failures:** thao tác ghi đã thực hiện nhưng chưa đạt mức xác nhận mong muốn.
5. **Replication/topology events:** primary election, connectivity loss, replication lag.
6. **Search/index errors:** index not ready, query timeout, stale results.
7. **Business rejections:** input sai, conflict hợp lệ, 404 “không có đơn hàng”.

### 8.1. Không coi mọi 4xx là hệ thống hỏng

Một user nhập mã giảm giá sai là business rejection được thiết kế. Nếu API trả HTTP 400 đúng hợp đồng, nó có thể là lỗi ở góc nhìn người dùng nhưng **không phải database availability failure**.

Cần metric theo nhóm:

```text
http_requests_total{status_class="2xx"}
http_requests_total{status_class="4xx"}
http_requests_total{status_class="5xx"}

mongodb_command_failures_total{category="timeout"}
mongodb_command_failures_total{category="auth"}
mongodb_command_failures_total{category="duplicate_key"}
mongodb_command_failures_total{category="network"}
```

Các tên và labels chỉ là quy ước minh họa. Không đưa raw exception text làm label vì dễ tăng cardinality và rò dữ liệu.

### 8.2. Công thức error rate

Nếu trong năm phút có 50.000 requests và 500 requests lỗi thuộc lớp đã định nghĩa:

\[
\text{error rate}=\frac{500}{50.000}=1\%
\]

Không chia số lỗi từ database cho tổng HTTP requests nếu một request có thể gọi nhiều MongoDB commands; mẫu số phải khớp **đơn vị sự kiện đang đo**.

### 8.3. Error count và error percentage đều cần

Một service có 10 requests trong năm phút và 1 lỗi: error rate **10%**, nhưng sample ít. Một service có 100.000 requests và 1.000 lỗi: error rate **1%**, nhưng ảnh hưởng lớn.

Alert tốt có thể kết hợp:

- Tỷ lệ lỗi;
- Số lượng lỗi tối thiểu;
- Thời gian duy trì;
- Error budget burn;
- Business criticality.

### 8.4. Retry có thể che lỗi

Driver có thể tự retry một số thao tác theo cấu hình và semantics MongoDB. Khi đó:

```text
Command attempt #1: network error
Command attempt #2: successful
HTTP request: 200 OK
```

User không thấy lỗi, nhưng database command retries tăng. Nếu chỉ đo HTTP error rate, ta có thể bỏ lỡ tín hiệu trước sự cố.

Nên có metric:

```text
mongodb_command_attempts
mongodb_command_failures
mongodb_retryable_failures
api_requests_failed
```

Không mặc định “command failed” luôn có nghĩa business operation cuối cùng thất bại. Với write concern/network errors, trạng thái cuối có thể cần đối soát để tránh ghi trùng.

## 9. Những mã lỗi/nhóm lỗi cần phân biệt

| Nhóm | Dấu hiệu | Cách kiểm tra |
|---|---|---|
| Duplicate key | `E11000` / code 11000 | Unique index, retry/business conflict |
| Unauthorized | Authentication/authorization failure | Credentials, role, authSource, audit |
| Time limit exceeded | Query/operation bị giới hạn thời gian | Query plan, maxTimeMS, resource |
| Server selection timeout | Driver không tìm được server phù hợp | DNS, TLS, topology, election |
| Connection checkout timeout | Không lấy được connection từ pool | Pool sizing, wait queue, slow ops |
| Network/socket error | Kết nối bị reset hoặc mất | Network path, LB, TLS, restarts |
| WriteConcernError | Không đạt confirmation theo write concern | Replication health, write concern |
| TransientTransactionError | Transaction có điều kiện retry | Retry policy, topology |
| Cache/disk pressure | Latency tăng, có thể chạm tài nguyên | WiredTiger, disk metrics |
| Cursor timeout | Cursor idle/closed | Cursor lifecycle, getMore, sessions |

Từng loại có **chiến lược retry khác nhau**. Không viết một vòng `catch(Exception) -> retry forever`; điều đó có thể biến sự cố nhỏ thành retry storm.

### 9.1. Duplicate key có phải lúc nào cũng alert?

Không. Nếu một endpoint đăng ký tài khoản báo username đã tồn tại, duplicate key có thể là một business conflict mong đợi. Nhưng số lỗi `E11000` tăng đột biến ở một batch import vốn phải idempotent lại có thể báo hiệu bug.

Phân loại theo **operation và expectation** trước khi đặt alert.

### 9.2. Mức quan sát nào cho command failed?

Application logs có stack trace/correlation ID; driver listener có command name, elapsed time và failure; server logs có sự kiện tại server. Tập hợp chúng bằng một trace ID khi có thể, không ép MongoDB phải ghi toàn bộ request body chứa PII.

## 10. Kết nối: đếm gì và vì sao nó quan trọng?

MongoDB sử dụng các TCP connections giữa clients/drivers và các server. Các MongoDB drivers phổ biến có **connection pools** để tái sử dụng kết nối thay vì tạo TCP/TLS connection cho từng request.

Các trạng thái dễ nhầm:

- **Open/current connections:** socket/connections hiện đang được server duy trì.
- **Active connections:** kết nối đang thực hiện hoạt động theo semantics metric cụ thể.
- **Available capacity:** số kết nối server còn có thể nhận theo giới hạn.
- **Connections created:** tổng số kết nối đã được tạo trong một khoảng hoặc từ khi process khởi động.
- **Pool size:** số kết nối mỗi driver pool đang quản lý.
- **Checked-out connections:** những kết nối client đã lấy từ pool để dùng.
- **Pool wait queue:** requests đang chờ pool cấp connection.
- **Pool checkout wait:** thời gian chờ lấy connection.
- **Server selection time:** thời gian driver chọn server có thể phục vụ thao tác.

**Server connections không đồng nghĩa driver pool connections của một process**. Một MongoDB server nhận kết nối từ nhiều application instances, admin tools, monitoring và replication-related components.

## 11. `serverStatus().connections`

Ví dụ:

```javascript
const s = db.serverStatus();

printjson({
  connections: s.connections
});
```

Các trường phổ biến:

```javascript
{
  current: NumberInt(150),
  available: NumberInt(10000),
  totalCreated: NumberLong("125000"),
  active: NumberInt(85)
}
```

Output chỉ là ví dụ; MongoDB versions có thể thêm các trường khác.

- `current`: số connections hiện đang mở theo server.
- `available`: khả năng nhận thêm connections theo server capacity.
- `totalCreated`: số kết nối được tạo tích lũy.
- `active`: số connections active theo semantics server.
- Những chi tiết như `threaded` có thể tồn tại ở phiên bản khác.

### 11.1. `current` cao có phải luôn xấu?

Không. Một hệ thống có nhiều app pods, mỗi pod dùng connection pool riêng, có thể duy trì hàng trăm connections ngay cả khi QPS bình thường.

Điều đáng chú ý hơn:

- `current` tăng không tương xứng với số app instances;
- `totalCreated` tăng rất nhanh;
- `available` giảm gần mức giới hạn;
- Checkout wait time tăng;
- Pool timeouts tăng;
- Tạo MongoClient mới trên mỗi HTTP request;
- Connection count spike sau deployment/failover;
- Số lượng connections không giảm khi instances được thu hồi.

Một con số `current=500` tự nó không chứng minh có connection leak.

### 11.2. `totalCreated` là counter, không phải số kết nối đang mở

Nếu:

```text
totalCreated = 500.000
current = 250
```

không có nghĩa server đang mở 500.000 connections. `totalCreated` là số lượng tạo tích lũy. Để đo churn:

\[
\text{new connections/s}=
\frac{\Delta totalCreated}{\Delta t}
\]

Khi deploy rolling hoặc autoscale, rate này có thể tăng tạm thời. Cần theo dõi cùng timeline pod count và retries.

### 11.3. Connection leaks và churn khác nhau

- **Leak/pool growth:** connections giữ lâu ngoài dự kiến, số lượng tăng dần.
- **Churn:** connections liên tục tạo/đóng, current có thể không quá cao nhưng totalCreated rate rất lớn.

Churn gây thêm TLS handshake, authentication và CPU; leak làm cạn connection capacity. Cách xử lý khác nhau.

## 12. Driver connection pools: nơi latency có thể bị ẩn

Giả sử có:

```text
10 application instances
Mỗi instance duy trì pool tối đa 50 connections/server
```

Về mặt cấu hình, có thể có tới hàng trăm connections cho mỗi server từ ứng dụng, chưa kể monitoring và background connections. Số thực tế phụ thuộc driver, topology, workload và pool lifecycle; **không nhân số instances với maxPoolSize rồi coi đó là số socket luôn mở**.

### 12.1. `maxPoolSize` và `minPoolSize`

Các options thường gặp trong MongoDB drivers:

- `maxPoolSize`: giới hạn tối đa pool connections tới một server.
- `minPoolSize`: mức kết nối tối thiểu pool cố gắng duy trì.
- `maxConnecting`: giới hạn số kết nối đang được thiết lập đồng thời trong pool, nếu driver/version hỗ trợ.
- `maxIdleTimeMS`: kiểm soát thời gian nhàn rỗi của pooled connection.
- Pool checkout timeout hoặc max wait time theo tên API/driver tương ứng.
- Server selection timeout, connect timeout, socket timeout có semantics khác nhau.

Không có một `maxPoolSize=100` tối ưu cho mọi ứng dụng. Pool quá nhỏ có thể tạo hàng chờ; pool quá lớn có thể gây connection storms, cạnh tranh tài nguyên hoặc làm quá tải database.

### 12.2. Pool checkout wait khác server query latency

Timeline:

```text
API begins
    │
    ├── Wait for pool connection      400 ms
    ├── MongoDB command                15 ms
    ├── Decode / business logic        25 ms
    └── Return response
```

Nếu chỉ xem `opLatencies` trên server, có thể thấy MongoDB nhanh, còn API p99 rất chậm. Đây không phải mâu thuẫn; **pool wait xảy ra trước khi command được xử lý**.

### 12.3. Tạo một `MongoClient` cho mỗi request là anti-pattern

Không nên:

```java
void handleRequest() {
    try (var client = MongoClients.create(System.getenv("MONGODB_URI"))) {
        // Một request -> một MongoClient/pool mới.
    }
}
```

Trong phần lớn ứng dụng web, nên tạo **MongoClient được dùng chung theo application lifecycle**, vì MongoClient quản lý connection pools và background monitoring.

Mở/đóng client liên tục có thể tạo network/TLS/authentication overhead và connection churn.

### 12.4. Cần theo dõi pool ở đâu?

Driver-specific monitoring APIs thường có các event:

```text
ConnectionPoolCreated
ConnectionCreated
ConnectionCheckedOut
ConnectionCheckedIn
ConnectionCheckOutFailed
ConnectionClosed
```

Tên lớp/event cụ thể phụ thuộc driver. Tập metrics hữu ích:

```text
pool_in_use
pool_idle
pool_waiting
pool_checkout_duration
pool_checkout_failures_total
pool_created_total
pool_closed_total
```

Không coi `connections.current` trên server là đủ để suy ra thời gian chờ lấy connection trong từng Java service.

## 13. Đặt bốn nhóm tín hiệu cạnh nhau

Một bảng đọc theo hiện tượng:

| Latency | Traffic | Errors | Connections | Gợi ý |
|---|---|---|---|---|
| Tăng | Tăng | Chưa tăng | Active tăng | Tải tăng, query/resource cần kiểm tra |
| Tăng | Không đổi | Tăng timeout | Wait queue tăng | Pool bão hòa hoặc database chậm |
| Tăng đột biến | Giảm | Server selection errors | Churn tăng | Failover/network/TLS |
| Ổn | Tăng | Ổn | Current tăng hợp lý | Scale hoạt động bình thường |
| Ổn | Ổn | Auth errors tăng | New connections tăng | Credentials/rotation/bất thường |
| Tăng | Ổn | Ít lỗi | Current ổn | Query plan/I/O/cache/lock |
| Tăng từng đợt | Ổn | Retry tăng | Created rate tăng | Connection storms/restarts |
| Thấp | Gần 0 | Gần 0 | 0 hoặc còn idle | Có thể hết traffic, cũng có thể app mất kết nối |

Bảng là **giả thuyết chẩn đoán**, không phải công thức suy ra nguyên nhân chắc chắn. Phải đối chiếu logs, traces, topology và thay đổi gần đây.

## 14. Saturation: bối cảnh không thể thiếu

Bốn nhóm latency/traffic/errors/connections phản ánh hiện tượng. Để hiểu nguyên nhân, phải xem **saturation** — một tài nguyên đang tiến gần hoặc vượt khả năng phục vụ.

Các nguồn bão hòa MongoDB thường gặp:

- CPU;
- WiredTiger cache;
- RAM pressure/swapping;
- Disk IOPS/throughput/latency;
- Disk space;
- Read/write concurrency và scheduling;
- Connection limits;
- Driver pool wait queues;
- Network bandwidth;
- Replication lag;
- Query planner/index inefficiency;
- Search nodes nếu dùng MongoDB Search/Vector Search.

### 14.1. CPU cao không đủ chẩn đoán

CPU cao khi traffic tăng có thể bình thường. Nhưng CPU cao với QPS không đổi, p99 tăng và query plan mới có COLLSCAN là tín hiệu khác.

Cần so:

```text
CPU utilization
QPS / reads / writes
p95/p99 latency
Docs examined / returned
Index usage
```

### 14.2. Disk I/O và latency

Nếu disk read latency tăng, WiredTiger cache miss nhiều hoặc workload scan documents lớn, MongoDB queries có thể chậm dù CPU chưa đạt 100%.

Các chỉ số nên xem:

- Disk read/write IOPS;
- Throughput;
- Queue depth/await trên OS/cloud;
- Available disk capacity;
- WiredTiger cache read/write activity;
- Pages read into cache;
- Replication/checkpoint/backup I/O.

Không tự kết luận “RAM càng nhiều luôn sửa được mọi truy vấn chậm”. Một query không có index vẫn có thể quá đắt.

## 15. WiredTiger cache và chẩn đoán

Với WiredTiger storage engine, cache là thành phần quan trọng ảnh hưởng read/write latency.

Ví dụ xem phần liên quan:

```javascript
const s = db.serverStatus();

if (s.wiredTiger && s.wiredTiger.cache) {
  printjson({
    cache: s.wiredTiger.cache
  });
}
```

Output có nhiều counters, một số tên mô tả như:

```text
maximum bytes configured
bytes currently in the cache
bytes read into cache
bytes written from cache
tracked dirty bytes in the cache
```

Tên field và nội dung có thể thay đổi theo MongoDB version. Không cố hardcode toàn bộ metrics WiredTiger của một phiên bản vào script mọi phiên bản.

### 15.1. Cache utilization

Một phép tính trực quan:

\[
\text{cache usage ratio} =
\frac{\text{bytes currently in cache}}
     {\text{maximum bytes configured}}
\]

Tuy nhiên, **cache gần đầy không tự nghĩa có lỗi**: cache được thiết kế để sử dụng memory nhằm tăng hiệu quả. Cần xem thêm eviction pressure, dirty bytes, disk I/O, query latency và CPU.

### 15.2. Write latency và dirty cache

Nếu dữ liệu dirty tăng, eviction/checkpoint không theo kịp hoặc disk write latency tăng, writes có thể chậm. Kết hợp:

```text
write ops/s
write latency
dirty cache metrics
disk write latency
checkpoint activity
replication lag
```

Không chỉ giảm write concern hoặc tắt journaling để “sửa” latency; những thay đổi đó có thể gây rủi ro dữ liệu.

## 16. Query hiệu năng kém: số lượng thao tác không phải tất cả

Hai workload có cùng 100 reads/s:

```text
Workload A:
  100 findOne theo _id

Workload B:
  100 aggregation quét một triệu documents mỗi lần
```

Số operations/s giống nhau nhưng chi phí CPU/I/O hoàn toàn khác.

Để phân tích cần:

- Docs examined;
- Keys examined;
- Docs returned;
- Query plan (`IXSCAN`, `COLLSCAN` hoặc những stages tương ứng);
- Query shape;
- Slow query logs;
- Query Profiler/Atlas Query Insights nếu có;
- Số result batches/getMore;
- Sort memory/disk spill.

### 16.1. `explain("executionStats")`

Trên collection đã có index và quyền phù hợp:

```javascript
db.getSiblingDB("shop").orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.limit(20)
.explain("executionStats");
```

Các trường thường quan trọng:

```text
winningPlan
nReturned
totalKeysExamined
totalDocsExamined
executionTimeMillis
```

Tùy MongoDB version/query engine, tên stages và cấu trúc có thể khác.

### 16.2. Query targeting ratio

Một metric tương đối:

\[
\text{documents examined per returned} =
\frac{\text{totalDocsExamined}}{\max(1,\text{nReturned})}
\]

Nếu cần trả 10 documents mà phải examine 500.000, nên xem index/query shape. Tuy nhiên, ratio cao không phải lúc nào sai: một truy vấn tìm “không có record nào” có thể phải kiểm tra nhiều candidates theo thiết kế.

Quan sát ratio kết hợp latency, traffic và use case; không đặt một threshold máy móc cho mọi truy vấn.

### 16.3. Explain không giống production latency

`explain("executionStats")` là công cụ phân tích execution của một câu query cụ thể. Nó không mô phỏng đầy đủ:

- Connection pool contention;
- Traffic concurrency;
- End-to-end API;
- Network RTT từ client;
- Application retries;
- Tác động của mọi workload đang chạy.

Đừng lấy `executionTimeMillis` từ một lần explain rồi dùng thay SLO của API.

## 17. Logs, slow operations và profiler

Khi latency tăng, metrics chỉ ra *khi nào* và *bao nhiêu*, còn logs/profiler giúp thấy *truy vấn nào và điều gì xảy ra*.

Nguồn phổ biến:

- MongoDB diagnostic logs;
- Slow operation messages;
- Atlas Query Profiler/Performance Advisor theo tier;
- Database profiler (`system.profile`) khi được bật;
- Application structured logs;
- Driver command monitoring;
- Distributed tracing.

### 17.1. Slow operation threshold

MongoDB có cấu hình liên quan `slowms` và cơ chế logging/profiling. Tuy nhiên, **thay threshold là một thay đổi vận hành**, không phải lệnh chỉ đọc.

Không tự bật profiling toàn bộ mọi operation ở production khi chưa đánh giá overhead và retention. Profile data có thể chứa query shapes, field values hoặc metadata nhạy cảm.

### 17.2. Đọc trạng thái profiler

Trong `mongosh`, nếu được phép:

```javascript
db.getSiblingDB("shop").getProfilingStatus();
```

Nếu profiler đã bật và user có quyền, có thể đọc giới hạn:

```javascript
db.getSiblingDB("shop").system.profile.find(
  {},
  {
    ts: 1,
    millis: 1,
    op: 1,
    ns: 1
  }
)
.sort({ ts: -1 })
.limit(10);
```

Ngay cả field metadata có thể tiết lộ collection names và activity. Không paste raw profiler documents vào ticket public.

### 17.3. Slow query không chỉ do query không có index

Các nguyên nhân khác:

- Query dùng index nhưng trả quá nhiều dữ liệu;
- Sort phức tạp;
- Aggregation memory pressure;
- Transaction giữ tài nguyên lâu;
- Network throughput;
- Disk contention;
- Plan cache/shape thay đổi;
- Data skew;
- Chunk migration/shard balancing;
- Concurrent operations.

Phải đối chiếu performance metrics cùng timestamp chậm.

## 18. `currentOp`: xem các hoạt động đang chạy

Khi muốn biết điều gì đang chiếm thời gian, có thể dùng `currentOp` theo quyền và phiên bản:

```javascript
db.adminCommand({
  currentOp: 1,
  active: true
});
```

Kết quả có thể chứa:

```text
operation type
namespace
secs_running
waitingForLock
client metadata
command details
```

Không phải mọi field xuất hiện ở mọi version/operation. `currentOp` chỉ là **ảnh tại thời điểm lấy mẫu**, có thể bỏ lỡ các operations ngắn.

### 18.1. Cần cẩn thận với thông tin nhạy cảm

Kết quả có thể chứa command details hoặc client info. Không lưu nguyên output vào nơi công khai.

### 18.2. Không tự kill operations trong bài quan sát

Lệnh `killOp` và các cách terminate session/transaction là thao tác can thiệp vận hành, có thể ảnh hưởng người dùng. Chúng cần runbook và thẩm quyền riêng. Việc quan sát không đồng nghĩa được phép tự dừng mọi query chạy lâu.

### 18.3. Long-running query và index build

Một long-running aggregation có thể là sự cố, nhưng một job batch có kế hoạch, index build hoặc backup có thể hợp lệ. Phải biết maintenance window và business workload trước khi alert hoặc can thiệp.

## 19. Replica set: độ trễ replication và elections

Trong replica set:

- Primary nhận writes theo topology;
- Secondaries replicate/apply changes;
- Elections thay primary khi cần;
- Read preference có thể định tuyến reads tới các nodes khác nhau;
- Write concern ảnh hưởng điều kiện xác nhận ghi.

Vì vậy, khi theo dõi latency/traffic/errors/connections, phải đặt chúng trong bối cảnh replication.

### 19.1. Replication lag

Một metric cơ bản:

```text
Primary oplog time:   T
Secondary applied:    T - 12 seconds
Replication lag:      ~12 seconds
```

Lag ảnh hưởng tính mới của reads từ secondaries và có thể liên quan majority write confirmation tùy topology/sự cố.

### 19.2. Xem trạng thái

Trên replica set với quyền phù hợp:

```javascript
rs.status();
```

Cần xác nhận:

- Members up/down;
- Primary hiện hành;
- Secondary states;
- Health;
- Optime/lag;
- Elections/restarts;
- Network problems.

Không lấy `rs.status()` của một node rồi suy ra mọi vấn đề mạng đã được giải quyết. Đối chiếu server metrics và monitoring đa node.

### 19.3. Election tác động connection và lỗi

Khi primary thay đổi:

```text
Primary stepdown
     │
     ├── Server selection thay đổi
     ├── Một số commands bị interrupted/retried
     ├── Connections/pools có thể tái thiết lập
     └── API latency/error tăng tạm thời
```

Nếu dashboard chỉ có QPS mà không có topology events, có thể chẩn đoán nhầm thành query regression.

### 19.4. Không “sửa latency” bằng cách hạ độ bền ghi vô tội vạ

Giảm write concern để ACK sớm hơn có thể tác động bảo đảm dữ liệu. Chỉ thay khi hiểu yêu cầu nhất quán và độ bền của nghiệp vụ, được phê duyệt và đo bằng workload.

## 20. Sharded cluster: metrics theo router, shard và namespace

Với sharded cluster:

```text
Application
    │
    ▼
  mongos
    │
    ├── Shard A replica set
    ├── Shard B replica set
    └── Shard C replica set
```

Một query có thể:

- Target một shard;
- Target một số shards;
- Scatter-gather mọi shards;
- Chờ merge kết quả;
- Bị ảnh hưởng bởi chunk migrations/balancer.

### 20.1. Không nhìn một shard rồi kết luận toàn cluster

Ví dụ:

```text
Shard A CPU = 95%, p99 cao
Shard B CPU = 20%, p99 ổn
Shard C CPU = 15%, p99 ổn
```

Trung bình CPU toàn cluster có thể không quá cao, nhưng shard A là hotspot.

Nên phân tách metrics theo:

- Shard;
- Replica set member;
- Primary/secondary;
- Namespace;
- Query shape;
- Tenant hoặc partition key khi có telemetry phù hợp.

### 20.2. Scatter-gather có thể tăng traffic

Một endpoint không cung cấp shard key có thể làm `mongos` gửi query tới nhiều shards. HTTP QPS không đổi nhưng tổng MongoDB query activity và network tăng.

Khi xem traffic, cần tránh đếm lặp giữa router và shards như thể đó là những request nghiệp vụ độc lập.

### 20.3. Balancing/resharding và latency spikes

Chunk migrations, balancing hoặc resharding có thể ảnh hưởng disk/network/CPU. Đối chiếu metrics với maintenance events trước khi quy lỗi cho traffic tăng.

## 21. Atlas Monitoring: dùng dashboard có sẵn nhưng hiểu ngữ nghĩa

MongoDB Atlas có các dashboard/metrics và tính năng phân tích performance tùy deployment tier và phiên bản, chẳng hạn:

- Operations và throughput;
- Connections;
- Query/command latency;
- CPU, memory, disk;
- Network ingress/egress;
- Replication lag;
- Cache/utilization;
- Query targeting;
- Alerts;
- Query Profiler/Performance Advisor hoặc các tính năng tương ứng;
- Search Nodes metrics nếu sử dụng.

**Tên metric và mức chi tiết tùy tier/version**, nên xem tooltip/definition của chính dashboard thay vì tin rằng mọi tên giống với `serverStatus()`.

### 21.1. Metric phạm vi node hay cluster?

Một biểu đồ “Connections” có thể trình bày theo một node hoặc toàn cluster tùy màn hình. Khi so sánh:

- Chọn đúng cluster/project;
- Chọn node role;
- Chọn thời gian và timezone;
- Xem biểu đồ aggregated hay per-node;
- Đối chiếu rolling upgrades và elections.

### 21.2. Atlas Free/Flex có giới hạn monitoring

Không nên giả định Atlas Free, Flex và Dedicated đều có cùng độ phân giải metrics, retention, profiler, alert options hay khả năng export. Khi SLO production yêu cầu p99 trace chi tiết, cần xem tier đang dùng có đủ dữ liệu không.

### 21.3. Alert gắn với người trực

Atlas alert không đủ nếu:

- Không ai nhận notification;
- Threshold không liên quan SLO;
- Alert spam quá mức dẫn tới bỏ qua;
- Không có runbook;
- Không có escalation;
- Không có quy trình tránh thao tác phá hoại.

Thiết kế monitoring là một phần của vận hành, không chỉ bật một thông báo.

## 22. `mongostat` và `mongotop`: hai công cụ khác nhau

MongoDB Database Tools/diagnostic tools có các lệnh quan sát như `mongostat` và `mongotop` trong môi trường được hỗ trợ.

### 22.1. `mongostat`

Ví dụ chạy tại shell được phép:

```bash
mongostat --uri "$MONGODB_URI" 5
```

Ví dụ trên theo cú pháp shell Unix; trên Windows PowerShell, cách tham chiếu biến môi trường khác. Không gắn username/password thật vào command hoặc log terminal.

`mongostat` cho cái nhìn mẫu theo chu kỳ về:

- Insert/query/update/delete;
- Connections;
- Cache/memory;
- Network;
- Replication metrics;
- Các cột tùy server/tool version.

Nó phù hợp chẩn đoán nhanh, **không thay hệ thống time-series monitoring dài hạn**.

### 22.2. `mongotop`

Ví dụ:

```bash
mongotop --uri "$MONGODB_URI" 5
```

`mongotop` cung cấp thời gian đọc/ghi theo namespaces theo cơ chế sampling của công cụ. Nó có thể giúp tìm collection có activity đáng chú ý.

Không coi những cột milliseconds của `mongotop` là HTTP p95 latency. Chúng đo **thời gian hoạt động MongoDB** ở scope khác.

### 22.3. Không chạy công cụ với tài khoản root chỉ vì muốn xem metrics

Dùng một account monitoring có đủ privileges, theo least privilege, với TLS và private connectivity. Các công cụ chẩn đoán cũng là clients cần kiểm soát credentials.

## 23. Java Driver: thu thập command latency và errors

Với MongoDB Java Sync Driver, có thể dùng **CommandListener** để quan sát command started/succeeded/failed.

Ví dụ tối giản:

```java
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import com.mongodb.event.CommandFailedEvent;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public final class SafeMongoCommandListener implements CommandListener {

    private final LongAdder successCount = new LongAdder();
    private final LongAdder failureCount = new LongAdder();
    private final LongAdder elapsedNanos = new LongAdder();

    @Override
    public void commandStarted(CommandStartedEvent event) {
        // Không log event.getCommand() một cách tùy tiện:
        // command body có thể chứa PII hoặc token.
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        successCount.increment();
        elapsedNanos.add(
            event.getElapsedTime(TimeUnit.NANOSECONDS)
        );
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        failureCount.increment();
        elapsedNanos.add(
            event.getElapsedTime(TimeUnit.NANOSECONDS)
        );
    }

    public long successes() {
        return successCount.sum();
    }

    public long failures() {
        return failureCount.sum();
    }

    public long totalElapsedNanos() {
        return elapsedNanos.sum();
    }
}
```

Đăng ký listener khi tạo `MongoClientSettings`:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

String uri = System.getenv("MONGODB_URI");

SafeMongoCommandListener listener =
    new SafeMongoCommandListener();

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .addCommandListener(listener)
    .build();

MongoClient client = MongoClients.create(settings);
```

Đây là ví dụ để hiểu **điểm cắm của monitoring**, không phải metrics exporter production hoàn chỉnh. Các counters là tổng từ lúc listener được tạo. Một hệ thực tế cần:

- Histogram cho durations;
- Command name làm label hữu ích;
- Error category thấp cardinality;
- Context về application instance;
- Export ra metrics backend;
- Correlation với API spans;
- Tránh log command parameters;
- Đóng MongoClient theo lifecycle ứng dụng.

### 23.1. Command elapsed không bao gồm mọi khoảng chờ ở ứng dụng

Driver command listener tập trung vào lifecycle của database command. Nó **không tự đo toàn bộ** pool checkout wait, server selection, serialization trong business code hoặc HTTP response time.

Nên đặt một timer ở application service boundary để có góc nhìn end-to-end.

### 23.2. Khi command fail nhưng request retry thành công

Nếu monitor tăng `failureCount` cho lần thử đầu, sau đó retry thành công, application vẫn trả 200. Đây là hai metric ở hai scope khác nhau:

```text
Driver command attempt: failed
Driver later attempt:  success
HTTP request:          success
```

Không “sửa” số liệu bằng cách xóa driver failure; cần phân biệt rõ *attempt failure* với *logical request failure*.

## 24. Java ConnectionPoolListener: nhìn thấy wait queue

MongoDB Java Driver có connection pool monitoring events. Một instrumentation production thường cần:

- Pool created/cleared/closed;
- Connection created/ready/closed;
- Checkout started;
- Checkout succeeded;
- Checkout failed;
- Checked in;
- Checkout duration.

Một cách cấu hình khung:

```java
import com.mongodb.MongoClientSettings;
import com.mongodb.ConnectionString;
import com.mongodb.event.ConnectionPoolListener;

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(
        new ConnectionString(System.getenv("MONGODB_URI"))
    )
    .applyToConnectionPoolSettings(builder -> {
        builder.addConnectionPoolListener(
            new MyConnectionPoolMetricsListener()
        );
    })
    .build();
```

`MyConnectionPoolMetricsListener` là **class ứng dụng cần tự hiện thực** từ `ConnectionPoolListener` theo API driver version. Không phải class có sẵn trong MongoDB Driver.

### 24.1. Những sự kiện cần correlate

```text
ConnectionCheckOutStarted
        │
        ├── Succeeded → checkout duration
        │
        └── Failed    → reason / timeout
```

Nếu checkout duration p99 tăng trong lúc `mongod` operation latency bình thường, có thể là:

- Pool quá nhỏ so với concurrency;
- Connections bị giữ lâu bởi operations khác;
- Pool đang establish connections quá chậm;
- Ứng dụng có quá nhiều threads tranh pool;
- Một client instance tạo quá nhiều concurrent requests;
- Network/TLS establishment chậm.

Tăng `maxPoolSize` có thể giúp một số tình huống nhưng cũng có thể dồn tải xuống MongoDB, khiến server quá tải hơn. Phải benchmark và kiểm soát concurrency.

## 25. OpenTelemetry: traces ghép các lớp lại với nhau

Một trace end-to-end có thể như sau:

```text
Trace: GET /orders/search 900 ms
   │
   ├── API middleware                   10 ms
   ├── Business rule                    20 ms
   ├── DB pool / server selection      450 ms
   ├── MongoDB aggregate              120 ms
   ├── External service call          200 ms
   └── Response serialization         100 ms
```

Một trace có các spans giúp chỉ ra thời gian tiêu tốn ở đâu. Tuy nhiên, **độ chính xác của phân chia** phụ thuộc cách instrumentation: không phải mọi library tự tạo span cho pool wait.

### 25.1. Correlation IDs

Nên truyền một request/trace ID xuyên các lớp:

```text
HTTP traceId
    ↕
Application log
    ↕
Driver span/command event
    ↕
Operational timeline
```

Không đưa user raw data, secrets, MongoDB URIs hoặc PII vào span attributes. Một trace ID hữu ích ngay cả khi không lưu command body.

### 25.2. Sampling

Full tracing cho mọi request có thể đắt. Các lựa chọn:

- Head-based sampling;
- Tail-based sampling;
- Sampling tăng cho errors/slow requests;
- Giữ aggregate metrics cho toàn bộ traffic;
- Có policy retention và privacy.

Không lấy mẫu vài trace thành công rồi tuyên bố đó là toàn bộ phân phối latency.

## 26. Định nghĩa SLI, SLO và SLA

Một dashboard tốt cần trả lời **“người dùng đang nhận dịch vụ đúng cam kết không?”**

- **SLI (Service Level Indicator):** chỉ số đo chất lượng thực.
- **SLO (Service Level Objective):** mục tiêu nội bộ cho SLI trong một khoảng.
- **SLA (Service Level Agreement):** cam kết dịch vụ có ý nghĩa hợp đồng nếu có.

### 26.1. Ví dụ SLI cho API dùng MongoDB

```text
SLI availability:
  successful HTTP requests / eligible HTTP requests

SLI latency:
  proportion of eligible requests completing <= 250 ms

SLO:
  99% eligible requests complete <= 250 ms over 30 days
```

Đây là ví dụ, không phải ngưỡng khuyến nghị cho mọi MongoDB ứng dụng.

Quan trọng là định nghĩa **eligible requests**:

- Có loại bỏ health checks không?
- 4xx do client sai input có tính lỗi availability không?
- HTTP request bị client cancel tính thế nào?
- Timeout ở gateway có được ghi nhận không?

Nếu không thống nhất định nghĩa, hai dashboard có thể báo SLO khác nhau cho cùng traffic.

### 26.2. Error budget

Nếu SLO success là 99.9% trong một tháng:

\[
\text{error budget fraction}=1-0.999=0.001=0.1\%
\]

Mục tiêu giúp cân bằng phát hành tính năng và độ ổn định. Khi burn rate cao, có thể tạm hoãn thay đổi rủi ro cao và tập trung khắc phục.

### 26.3. Database SLO và API SLO khác nhau

Một database metric:

```text
MongoDB command success rate >= 99.99%
```

không bảo đảm:

```text
User checkout success rate >= 99.9%
```

vì API còn phụ thuộc service khác, business logic và các bước hậu xử lý.

Nên có cả business-level và DB-level SLIs để chẩn đoán.

## 27. Thiết kế dashboard tối thiểu

Một dashboard MongoDB/app hữu ích nên có các panels:

### 27.1. Hàng 1 — Sức khỏe người dùng

| Panel | Mục tiêu |
|---|---|
| API request rate | Lưu lượng người dùng |
| API error rate theo endpoint/status | Khả năng phục vụ |
| API latency p50/p95/p99 | Trải nghiệm |
| Key business success rate | Tác động nghiệp vụ |

### 27.2. Hàng 2 — MongoDB operations

| Panel | Mục tiêu |
|---|---|
| Reads/writes/commands per second | Tải database |
| Server operation mean latency | Tốc độ xử lý |
| Driver command latency p95/p99 | Thời gian command |
| Driver error categories | Lỗi DB |
| Slow query volume | Queries đáng chú ý |
| Query targeting | Hiệu quả query/index |

### 27.3. Hàng 3 — Connections/pools

| Panel | Mục tiêu |
|---|---|
| Server `connections.current` | Kết nối đang mở |
| Server `connections.active` | Hoạt động hiện thời |
| Server `connections.available` | Headroom |
| Connection creation rate | Churn |
| Driver checked-out/idle/waiting | Pool pressure |
| Pool checkout duration p95 | Thời gian chờ |
| Pool checkout failures | Tín hiệu nghẽn |

### 27.4. Hàng 4 — Capacity/topology

| Panel | Mục tiêu |
|---|---|
| CPU, memory, disk IOPS/latency | Saturation |
| WiredTiger cache/dirty bytes | Storage pressure |
| Replication lag/elections | Replica set |
| Shard-specific hotspots | Sharding |
| Network ingress/egress | Traffic dữ liệu |
| Search index sync lag | Derived indexing nếu dùng |

### 27.5. Hàng 5 — Thay đổi

Đặt các deployment/change annotations:

```text
09:30 deploy API v2.13
10:05 index build started
10:12 autoscale +4 pods
10:35 primary stepdown
11:00 backup job started
```

Có timeline thay đổi giúp phân biệt lỗi do release và lỗi do traffic tự nhiên.

## 28. Đặt alert sao cho có thể hành động

Alert nên dựa trên **ngưỡng có ý nghĩa và thời gian duy trì**, không chỉ một giá trị chớp nhoáng.

Ví dụ khởi đầu, phải điều chỉnh theo workload:

| Alert | Điều kiện minh họa | Tại sao |
|---|---|---|
| API p95 cao | p95 > 300 ms trong 10 phút | User chờ lâu |
| API error rate | > 1% trong 5 phút với đủ traffic | Nhiều requests lỗi |
| Pool checkout failures | Có failures liên tục trong 5 phút | Requests không lấy được connection |
| Connection headroom thấp | Available giảm gần giới hạn | Nguy cơ từ chối kết nối |
| Connection churn | Created rate cao bất thường | Client lifecycle/TLS overhead |
| Replication lag | Vượt ngưỡng RPO/SLO | Stale reads, availability |
| Disk free thấp | Dưới capacity margin | Rủi ro write failure |
| CPU sustained high | CPU cao kèm latency và queues | Resource saturation |
| Backup failed | Một kỳ backup quan trọng thất bại | Mất khả năng phục hồi |
| Primary flapping | Elections lặp lại | Availability risk |

Các ngưỡng chỉ là ví dụ. Với workload tải thấp, percentage cần **minimum sample count**. Với workload theo mùa, dùng baseline theo thời gian hoặc phân tầng nghiệp vụ.

### 28.1. Không alert chỉ vì connection count tuyệt đối

Một pool duy trì 500 connections có thể bình thường. Alert tốt hơn là **thay đổi bất thường**, tiến gần server limit, checkout wait tăng hoặc connection failures.

### 28.2. Multi-window alerts

Một tín hiệu error-budget burn nên có khả năng phát hiện cả:

- Sự cố lớn ngắn hạn;
- Suy giảm nhỏ nhưng kéo dài.

Kết hợp cửa sổ ngắn/dài tùy telemetry backend và SLO. Không dùng một threshold duy nhất cho mọi cảnh báo.

### 28.3. Không biến alert thành vòng tự động phá hoại

Tăng latency không có nghĩa tự động `killOp` toàn bộ active operations, restart replica set hay giảm write concern. Một remediation tự động cần điều kiện an toàn, ownership, idempotency, rollback và kiểm thử riêng.

## 29. Runbook: khi p99 latency tăng

Một quy trình điều tra:

```text
1. Xác nhận phạm vi sự cố
      │
      ▼
2. API p95/p99 và traffic/errors
      │
      ▼
3. Driver command / pool waits
      │
      ▼
4. Server opLatencies, opcounters, connections
      │
      ▼
5. CPU, disk, cache, replication, sharding
      │
      ▼
6. Query profiler / explain / recent changes
      │
      ▼
7. Mitigation có kiểm soát
      │
      ▼
8. Verify SLO recovery
```

### 29.1. Bước 1 — Phạm vi

- Một endpoint hay toàn API?
- Một tenant hay toàn bộ tenants?
- Một region hay tất cả?
- Chỉ writes hay cả reads?
- Chỉ secondary reads hay primary?
- Chỉ Search/Vector Search hay query thông thường?

### 29.2. Bước 2 — Người dùng thực sự có bị ảnh hưởng?

Kiểm tra HTTP p95/p99, error rate, business success rate. Nếu chỉ một `mongostat` cột tăng nhưng API SLO vẫn tốt, chưa chắc là incident.

### 29.3. Bước 3 — Driver và connection pool

Nếu pool wait tăng:

- Số app instances có thay đổi?
- Có connection leak?
- Queries giữ connection lâu?
- Có server selection delays?
- Pool config/timeout thay đổi?
- Có nhiều retries?

### 29.4. Bước 4 — Server/query

Nếu operation latency tăng:

- Xem query shapes vừa deploy;
- `explain("executionStats")`;
- Docs examined/returned;
- Index changes;
- Cache/disk;
- Oplog/replication activity;
- Lock/ticket waits;
- Search index build.

### 29.5. Bước 5 — Mitigation

Có thể rollback code gây query xấu, tạm giảm traffic có chủ đích hoặc tối ưu index theo quy trình. Không thực hiện thao tác thay đổi production khi chưa hiểu blast radius.

## 30. Runbook: khi kết nối tăng bất thường

Tình huống:

```text
connections.current tăng từ 300 lên 3000
totalCreated/sec tăng mạnh
API p99 tăng
pool checkout failures xuất hiện
```

Hướng điều tra:

1. Có deployment/autoscale vừa diễn ra không?
2. `MongoClient` có được tạo một lần cho cả process không?
3. `maxPoolSize`, `minPoolSize` hoặc idle timeout vừa đổi?
4. Load balancer/network có reset connections?
5. Primary stepdown đã xảy ra?
6. TLS cert/credentials vừa rotate?
7. Có clients/monitoring jobs mới?
8. Có long-running operations giữ connections?
9. Có tấn công/brute force hoặc traffic ngoài dự kiến?
10. Database connection limit và host resource đang ở đâu?

### 30.1. Ví dụ về connection storm

```text
200 app pods cùng restart
   │
   ▼
Mỗi pod đồng loạt mở nhiều connections
   │
   ▼
TLS + authentication overhead tăng
   │
   ▼
Server bị áp lực và timeouts tăng
```

Một biện pháp có thể là **staggered rollout, connection warm-up có giới hạn, backoff/jitter**, không phải chỉ tăng max connections vô hạn.

## 31. Runbook: khi lỗi tăng nhưng latency không tăng

Tình huống:

```text
Latency p95 vẫn 80 ms
HTTP 5xx tăng đột biến
MongoDB command failures tăng
```

Có thể vì:

- Authentication credentials hết hạn/sai sau rotation;
- User role bị thu hồi;
- Database name/authSource sai;
- Schema validation rejects;
- Duplicate key tăng do regression;
- Query timeout quá ngắn;
- Network errors trước khi command bắt đầu;
- Application bug fail fast.

Đừng chỉ đi tìm slow query. Hãy phân loại exception codes và xem change timeline.

### 31.1. Lỗi do quyền không nên được “sửa” bằng root

Nếu app mất quyền sau thay đổi role, điều tra đúng privilege yêu cầu. Không cấp `root` chỉ để giảm lỗi; làm vậy giải quyết triệu chứng bằng cách mở rộng blast radius.

### 31.2. Lỗi do timeout có thể là upstream

Một ứng dụng đặt deadline 100 ms trong khi p95 service call tới provider khác 150 ms có thể trả timeout mà MongoDB vẫn bình thường. Tracing giúp xác định nơi thời gian bị tiêu tốn.

## 32. Khi traffic tăng nhưng lỗi/latency ổn định

Không phải mọi traffic spike là sự cố.

Nếu:

```text
Throughput tăng 2 lần
p95/p99 vẫn trong SLO
Error rate ổn định
Connections/CPU tăng tương xứng
Disk/network còn headroom
```

hệ thống có thể đang scale tốt.

Tuy nhiên, cần xem:

- Tăng trưởng traffic có bền vững không?
- Connection headroom còn bao nhiêu?
- Cache hiệu quả không?
- Search index lag có tăng?
- Replication lag có tăng?
- Load test trước đó đạt đến mức nào?

Sự kiện traffic tăng có thể là **tín hiệu capacity planning**, không phải lập tức incident.

## 33. Capacity planning từ các tín hiệu

Giả sử workload dự kiến tăng:

```text
Hiện tại:          200 HTTP req/s
Mỗi request:       2 MongoDB commands trung bình
Dự báo 6 tháng:    500 HTTP req/s
```

Một ước lượng lý thuyết:

```text
Hiện tại: ~400 DB commands/s
Tương lai: ~1000 DB commands/s
```

Nhưng hệ số này thay đổi nếu:

- Endpoint mix đổi;
- Batch reads/writes được tối ưu;
- Cache hit rate tăng;
- Retry rate tăng;
- Một request sinh fan-out;
- Shard routing thay đổi.

Cần load test trên dữ liệu, indexes và cấu hình gần production.

### 33.1. Công thức Little's Law

Một quan hệ cơ bản giữa concurrency, throughput và response time:

\[
L \approx \lambda W
\]

Trong đó:

- \(L\): số operations đang ở trong hệ thống trung bình;
- \(\lambda\): throughput trung bình (operations/s);
- \(W\): thời gian mỗi operation trong hệ thống (s).

Ví dụ 200 operations/s, latency trung bình 0.05 s, concurrency trung bình xấp xỉ 10 operations.

Đây là **quan hệ trung bình ở trạng thái ổn định**, không suy được p99 hoặc pool max size chỉ từ một phép nhân. Cần tính thêm burstiness, blocking, connection lifecycle và capacity margin.

### 33.2. Cảnh báo gần saturation

Latency thường tăng nhanh khi tài nguyên tiến gần giới hạn. Đừng sizing sao cho load bình thường đã ở 99% capacity rồi kỳ vọng mọi request đều có p99 tốt.

## 34. Các lỗi quan sát thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Xem mean thay p95/p99 | Che tail latency | Histogram/percentiles |
| So API latency với server opLatency như cùng scope | Đo khác đường đi | Phân tách layers |
| Dùng counter tích lũy làm QPS | Không chia theo thời gian | Tính delta/rate |
| Không xử lý counter reset | QPS âm sau restart | Reset-aware telemetry |
| Cộng counters mọi replica members thành user requests | Replication làm đếm lặp | Phân loại node/traffic |
| `network.numRequests` là HTTP RPS | Khác protocol/layer | Dùng API metric |
| 500 connections là leak | Pool idle có thể hợp lệ | Xem trend/churn/wait |
| `totalCreated` là open connections | Đây là counter | Dùng `current` |
| MongoDB mean thấp nghĩa API nhanh | Pool/network/app có thể chậm | End-to-end tracing |
| Pool lớn hơn luôn tốt | Có thể tăng server contention | Benchmark/limits |
| Lỗi `E11000` luôn là incident | Có thể là conflict hợp lệ | Phân loại business |
| Chỉ đếm HTTP 5xx | Retry có thể che DB errors | Theo dõi driver failures |
| Error % cao trên 2 requests là outage | Sample quá ít | Minimum volume/window |
| p95 toàn hệ thống = mean p95 của nodes | Sai toán percentile | Tổng hợp histograms |
| CPU cao chắc chắn là nguyên nhân | Có thể là hệ quả tải | Correlate query/I/O |
| Một query explain đủ định nghĩa SLO | Không gồm pool/API | APM + metrics |
| Bật profiler toàn bộ không tính overhead | Tốn tài nguyên, lộ dữ liệu | Sampling/approval |
| Log nguyên query/request | Có thể chứa PII/secrets | Redaction |
| Alert không có owner | Không ai hành động | Runbook/on-call |
| Dùng `killOp` như bước quan sát | Thay đổi state | Tách approval |
| Mỗi HTTP request tạo MongoClient | Connection churn | Singleton/shared lifecycle |
| Bỏ theo dõi election/replication | Chẩn đoán nhầm timeout | Topology timeline |
| Search sync lag bị coi là API query latency | Khác loại freshness | Theo dõi riêng |
| Một số liệu toàn cluster che shard hotspot | Data skew | Phân tách per shard |
| Dashboard chỉ có CPU và RAM | Không thấy tác động user | Golden signals |
| Thay threshold bằng phỏng đoán | Alert fatigue | SLO, baseline, load test |

## 35. Bài tập thực hành

### Bài 1 — Phân biệt lớp latency

Một request có:

```text
HTTP duration:          900 ms
MongoDB command time:    30 ms
Pool checkout wait:     500 ms
External API:           200 ms
Other processing:       170 ms
```

1. MongoDB server có nhất thiết là nguyên nhân chính không?
2. Cần theo dõi metric nào của driver?
3. Có nên thêm index trước khi xem pool không?
4. Tại sao chỉ nhìn `opLatencies` không đủ?

### Bài 2 — Tính read throughput từ counters

Dữ liệu:

```text
T1 at 10:00:00:
  reads.ops = 100000

T2 at 10:01:00:
  reads.ops = 112000
```

1. Tính reads/s.
2. Nếu có 5 retries, metrics nào phân biệt logical requests?
3. Nếu process restart giữa T1/T2 thì cách xử lý?
4. Nếu T1 và T2 thuộc hai nodes khác nhau thì có so được không?

### Bài 3 — Tính mean operation latency

```text
T1:
  reads.ops = 10000
  reads.latency = 5000000 μs

T2:
  reads.ops = 11000
  reads.latency = 7500000 μs
```

1. Tính delta operations.
2. Tính delta microseconds.
3. Đổi sang mean milliseconds.
4. Có suy ra p95 từ hai counters này không?

### Bài 4 — p99 và mean

Một API có 99% requests 50 ms và 1% requests 4 giây.

1. Mean có phản ánh trải nghiệm nhóm chậm không?
2. p95 và p99 phản ánh điều gì?
3. Vì sao p99 dễ nhiễu với số mẫu thấp?
4. Thiết kế histogram buckets theo SLO.

### Bài 5 — Network counter

Từ hai mẫu `network.bytesOut`:

```text
T1: 400000000 bytes
T2: 550000000 bytes
Interval: 30 seconds
```

1. Tính bytes/s.
2. Đổi sang MiB/s.
3. Kể ba nguyên nhân traffic tăng.
4. Vì sao không gọi đó là HTTP request rate?

### Bài 6 — Connections và churn

```text
T1 current=400, totalCreated=100000
T2 current=420, totalCreated=160000
Interval=5 minutes
```

1. Connection creation rate bao nhiêu?
2. `current` có tăng mạnh không?
3. Rủi ro churn là gì?
4. Nên kiểm tra MongoClient lifecycle và triển khai gần đây thế nào?

### Bài 7 — Pool bão hòa

API p99 1.2 giây, server operations chỉ 15 ms, pool checkout p99 1 giây.

1. Bottleneck có khả năng ở đâu?
2. Cần đo in-use/idle/waiting gì?
3. Tăng `maxPoolSize` vô hạn có an toàn không?
4. Đề xuất load test và concurrency controls.

### Bài 8 — Error rate có mẫu nhỏ

Trong cửa sổ 5 phút:

```text
Service A: 1 lỗi / 10 requests
Service B: 1000 lỗi / 100000 requests
```

1. Error percentage mỗi service?
2. Dịch vụ nào gây tác động lớn hơn tính theo số requests?
3. Có nên alert chỉ dựa vào percentage?
4. Đề xuất kết hợp ngưỡng và thời gian duy trì.

### Bài 9 — E11000

Một service tạo username mới thường nhận duplicate key khi username đã tồn tại.

1. Đây có phải lỗi hạ tầng không?
2. Cần log/categorize ra sao?
3. Nếu duplicate key tăng gấp 100 lần sau deployment thì làm gì?
4. Vì sao không loại bỏ unique index để giảm lỗi?

### Bài 10 — Election

Sau primary stepdown, application thấy server selection timeouts và connection creation rate tăng.

1. Giải thích mối liên hệ topology và driver.
2. Metric nào giúp xác nhận election?
3. Khi nào retry hợp lệ?
4. Vì sao không nên restart tất cả nodes để “ổn định”?

### Bài 11 — Query thiếu index

Một endpoint trả 10 documents nhưng `totalDocsExamined=800000`.

1. Documents examined/returned ratio?
2. Cần xem `winningPlan` gì?
3. Metrics I/O/cache nào có thể bị ảnh hưởng?
4. Có thể kết luận chỉ cần thêm index mà không thử query không?

### Bài 12 — Shard hotspot

Một sharded cluster có Shard A CPU 95%, B 20%, C 15%.

1. Vì sao CPU mean dễ che hotspot?
2. Kiểm tra shard key/query targeting như thế nào?
3. Traffic scatter-gather có thể ảnh hưởng metrics ra sao?
4. Nên đặt dashboard theo node/shard thế nào?

### Bài 13 — Java monitoring

Dùng `CommandListener`:

1. Đếm succeeded/failed commands.
2. Thu elapsed duration.
3. Thêm tags command name nhưng không chứa `_id`/raw query.
4. Phân biệt command error và HTTP error.
5. Thêm connection pool metrics qua `ConnectionPoolListener`.

### Bài 14 — Thiết kế SLO

Một dịch vụ yêu cầu:

```text
99% eligible requests <= 250 ms
30-day window
```

1. Chọn SLI phù hợp.
2. Có tính HTTP 400 validation errors không?
3. Đo bằng histogram thế nào?
4. Khi error budget burn nhanh, team nên làm gì?

### Bài 15 — Dashboard golden signals

Thiết kế dashboard có:

- API p50/p95/p99;
- Reads/writes/commands/s;
- Error rates theo loại;
- Connections current/available/created;
- Pool checkout wait;
- CPU/disk/cache;
- Replication lag;
- Deployment annotations.

Giải thích thứ tự các panels theo mục đích incident response.

### Bài 16 — Runbook hoàn chỉnh

Mô phỏng:

```text
11:00 p99 API tăng từ 250ms lên 2s
11:02 traffic tăng 30%
11:03 pool checkout timeout xuất hiện
11:04 replica lag tăng
11:05 connection creation rate tăng
```

1. Xếp các giả thuyết nguyên nhân.
2. Liệt kê lệnh read-only và dashboard cần xem.
3. Tìm correlation giữa từng mốc.
4. Đề xuất mitigation có rollback.
5. Viết tiêu chí xác nhận recovery.

## 36. Checklist production cho observability MongoDB

### Metrics và tracing

- [ ] API p50/p95/p99 được đo theo endpoint/service.
- [ ] MongoDB command duration được đo bằng driver instrumentation.
- [ ] Pool checkout wait và checkout failures có metrics.
- [ ] Server opLatencies được thu đúng node/window/đơn vị.
- [ ] Throughput được tính từ counter deltas/rates.
- [ ] HTTP requests/s được tách khỏi MongoDB operations/s.
- [ ] Network bytes/s được đo theo node/role.
- [ ] Error rate có phân loại timeout/auth/duplicate/network.
- [ ] Retry counts được quan sát độc lập với HTTP success.
- [ ] Connections current/active/available/created có dashboard.
- [ ] Counter resets được xử lý khi server restart.
- [ ] Trace/correlation ID có chính sách privacy.

### Capacity và topology

- [ ] CPU, RAM, disk IOPS/latency/free space được theo dõi.
- [ ] WiredTiger cache/eviction/dirty bytes có baseline.
- [ ] Slow query/query plan monitoring được bật theo quyền/overhead.
- [ ] Replica status/elections/replication lag có alerts.
- [ ] Sharded deployment được xem per shard, không chỉ mean cluster.
- [ ] Search/Vector indexing lag được theo dõi nếu có.
- [ ] Backup và restore monitoring có owner.
- [ ] Có capacity/load test đại diện production.

### Alerts và vận hành

- [ ] Mỗi alert quan trọng có on-call owner và runbook.
- [ ] Threshold gắn với SLO/baseline, không chọn tùy tiện.
- [ ] Có minimum sample volume cho percentage alerts.
- [ ] Có deployment/maintenance annotations.
- [ ] Alerts được thử trên staging hoặc bài diễn tập phù hợp.
- [ ] Không tự thực hiện destructive actions từ monitoring.
- [ ] Logs/metrics không chứa secrets/PII không cần thiết.
- [ ] Có chính sách retention và access control cho telemetry.
- [ ] Có quy trình post-incident review và điều chỉnh alerts.

## 37. Tài liệu MongoDB tham khảo

Các trang dưới đây cung cấp mô tả chi tiết theo server version và deployment; trước khi triển khai cần đối chiếu field/semantics trên phiên bản đang dùng:

- [MongoDB Monitoring](https://www.mongodb.com/docs/manual/administration/monitoring/)
- [MongoDB `serverStatus`](https://www.mongodb.com/docs/manual/reference/command/serverStatus/)
- [MongoDB `db.serverStatus()`](https://www.mongodb.com/docs/manual/reference/method/db.serverStatus/)
- [MongoDB `currentOp`](https://www.mongodb.com/docs/manual/reference/command/currentOp/)
- [MongoDB `explain`](https://www.mongodb.com/docs/manual/reference/method/cursor.explain/)
- [MongoDB Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB `mongostat`](https://www.mongodb.com/docs/database-tools/mongostat/)
- [MongoDB `mongotop`](https://www.mongodb.com/docs/database-tools/mongotop/)
- [MongoDB Atlas Monitoring](https://www.mongodb.com/docs/atlas/monitoring-alerts/)
- [MongoDB Atlas Alerts](https://www.mongodb.com/docs/atlas/configure-alerts/)
- [MongoDB Replica Set Monitoring](https://www.mongodb.com/docs/manual/administration/monitor-replica-sets/)
- [MongoDB Connection Pooling](https://www.mongodb.com/docs/manual/administration/connection-pool-overview/)
- [MongoDB Java Sync Driver Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/)
- [MongoDB Performance Best Practices](https://www.mongodb.com/docs/manual/administration/analyzing-mongodb-performance/)

## Kết luận

**Độ trễ, lưu lượng, lỗi và kết nối** là bốn nhóm tín hiệu trung tâm để quan sát một hệ thống MongoDB hoạt động trong môi trường thật. Nhưng phải đo chúng **ở đúng lớp**:

- **Độ trễ:** không chỉ nhìn trung bình server; cần p95/p99 API, command timing, pool wait và tracing.
- **Lưu lượng:** phân biệt HTTP requests/s, MongoDB operations/s, network bytes/s và hoạt động replication; nhiều counters MongoDB là số **tích lũy** cần lấy delta theo thời gian.
- **Lỗi:** phân loại business rejection, driver/server failures, retries, timeout, authentication và write concern; đừng trộn mọi lỗi thành một tỷ lệ không có ý nghĩa.
- **Kết nối:** theo dõi current/active/available, creation rate, pool in-use/waiting, checkout latency và churn; số lượng connections cao **không tự chứng minh** có leak.
- **Bối cảnh:** CPU, disk, WiredTiger cache, query plans, replication, sharding, Search indexing và deployment changes giúp giải thích nguyên nhân thật.

Một hệ thống quan sát tốt phải có **định nghĩa metric, đơn vị, cửa sổ đo, histogram, dashboards, alerts có owner, runbooks, privacy controls và cơ chế thử phục hồi**. Thước đo cuối cùng không phải số biểu đồ đã tạo, mà là việc đội vận hành có thể **phát hiện sớm, khoanh vùng, giảm tác động và xác nhận hệ thống đã trở lại SLO** hay không.

**MongoDB không “chậm” hay “nhanh” chỉ từ một con số; hãy quan sát toàn bộ hành trình của request và dùng bốn nhóm tín hiệu để tìm đúng nguyên nhân trước khi thay đổi hệ thống.**

