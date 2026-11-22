# Thiết lập ngưỡng cảnh báo, dữ liệu nền và quy trình điều tra sự cố trong MongoDB

## 1. Tại sao giám sát MongoDB cần nhiều hơn một biểu đồ CPU?

Giả sử hệ thống MongoDB vẫn trả lời lệnh `ping` nhưng người dùng liên tục gặp lỗi timeout khi mở danh sách đơn hàng. Nguyên nhân có thể là một query mới không sử dụng index, Java driver cạn pool kết nối, replication lag làm majority writes chậm hoặc một shard nóng hơn những shards còn lại.

Một CPU spike ngắn có thể vô hại; ngược lại CPU thấp không chứng minh database đang phục vụ ứng dụng tốt. Giám sát hiệu quả phải dựa trên **ảnh hưởng tới người dùng**, **baseline bình thường**, **ngưỡng có thể hành động** và **quy trình điều tra sự cố có bằng chứng**.

Bài học thuộc chương **Quan sát hệ thống** của module **Database Engine Document MongoDB**, với đề bài **Thiết lập ngưỡng cảnh báo, dữ liệu nền và quy trình điều tra sự cố**.

Sau bài này, bạn có thể:

1. Phân biệt monitoring, observability, alerting và incident management.
2. Chọn các nhóm tín hiệu quan trọng: latency, traffic, errors, saturation, replication và backup readiness.
3. Xây baseline theo ngày/giờ, release, workload và từng MongoDB member/shard.
4. Thiết kế ngưỡng static, dynamic, relative, forecast, SLO/error-budget và no-data.
5. Thiết lập duration, hysteresis, deduplication và routes tới đúng người trực.
6. Dùng Atlas Alerts, metrics, Query Profiler, Performance Advisor và Real-Time Performance Panel phù hợp.
7. Đọc `serverStatus`, `rs.status`, `rs.printSecondaryReplicationInfo`, `$currentOp`, profiler và `explain`.
8. Phân tích query regression, connection storm, replication lag, disk pressure, elections và authentication failures.
9. Lập incident timeline, thử giả thuyết, khắc phục, xác minh phục hồi và viết postmortem.
10. Thiết kế metrics Java driver, bảo vệ dữ liệu nhạy cảm trong logs/traces và chạy diễn tập.

**Nguyên tắc cốt lõi:** Một cảnh báo tốt cho biết vấn đề cần xử lý, mức độ ưu tiên, người chịu trách nhiệm và đường dẫn tới runbook. Nó không đơn thuần là phép so sánh một metric với con số tùy ý.

## 2. Bốn lớp của một hệ thống quan sát

~~~text
Ứng dụng / trải nghiệm người dùng
       |
       v
Application metrics + traces + driver metrics
       |
       v
MongoDB node / replica set / shard metrics + logs
       |
       v
Baseline + SLO + Alert rules
       |
       v
On-call / Incident response
       |
       v
Root cause + Action items + Threshold review
~~~

- **Monitoring:** theo dõi các tín hiệu đã định nghĩa và trạng thái hiện tại.
- **Observability:** khả năng giải thích điều đang xảy ra qua metrics, logs, traces và query plans.
- **Alerting:** quyết định lúc nào một điều kiện cần sự chú ý.
- **Incident response:** giảm tác động, giữ bằng chứng, xác minh phục hồi và cải tiến hệ thống.

Không có công cụ nào thay thế hoàn toàn công cụ khác. Atlas metrics có thể cho thấy disk I/O cao nhưng chưa cho biết endpoint nào bị tác động; Java tracing có thể chỉ rõ endpoint nhưng không giải thích node đang mất primary.

### 2.1. Triệu chứng khác nguyên nhân

~~~text
Người dùng thấy API chậm
   |
   +--> Java pool checkout wait cao
   |        |
   |        +--> Connections tăng
   |                 |
   |                 +--> Retry storm hoặc app scale
   |
   +--> Query plan đổi sang COLLSCAN
   |
   +--> Secondary lag, majority write chậm
   |
   +--> Disk latency cao
~~~

Một đường CPU và một đường latency tăng cùng lúc chỉ là tương quan. Cần timeline, cơ chế kỹ thuật và một phép kiểm tra có thể bác bỏ giả thuyết.

## 3. Golden signals và những đặc trưng riêng của MongoDB

Bốn golden signals:

| Nhóm | Chỉ số gợi ý | Câu hỏi điều tra |
|---|---|---|
| Latency | p50/p95/p99 query và API response | Request có chậm hơn mức chấp nhận? |
| Traffic | Requests/s, database operations/s | Workload tăng hay giảm bất thường? |
| Errors | Command failures, timeouts, 5xx, auth errors | Những yêu cầu nào đang thất bại? |
| Saturation | CPU, RAM/cache, IOPS, queues, tickets, connections | Thành phần nào hết khả năng phục vụ? |

MongoDB cần giám sát thêm:

- Primary availability và elections.
- Replication lag giữa các members.
- Oplog window và khả năng secondary bắt kịp.
- WiredTiger cache/eviction/checkpoints.
- Disk free bytes và latency/throughput.
- Query plan/scan ratio/index usage.
- Các shards mất cân bằng.
- Backup freshness và PIT restore window.
- TLS/authentication failures.
- Change streams consumer lag nếu ứng dụng dùng.

### 3.1. Quan sát theo nhiều cấp

~~~text
Business SLO
    |
    v
Service/Endpoint SLI
    |
    v
MongoClient / connection pools
    |
    v
Cluster / Replica Set
    |
    +--> Member A - PRIMARY
    +--> Member B - SECONDARY
    +--> Member C - SECONDARY
    |
    v
Per-namespace / query shape
~~~

Đừng chỉ dùng average toàn cluster; một secondary hoặc shard bị lỗi có thể bị các nodes khỏe che đi.

### 3.2. Số liệu từ client và server không luôn giống

Thời gian API nhận được bao gồm network, DNS/TLS, connection selection, queue/pool checkout, retries, BSON serialization và business logic. Server execution time chỉ là một phần. Một MongoDB server khỏe không loại trừ lỗi ở Java driver hoặc network.

## 4. Đọc đúng kiểu dữ liệu metrics

| Kiểu metric | Ví dụ | Cách dùng |
|---|---|---|
| Gauge | `connections.current`, disk free, CPU % | Giá trị tại thời điểm |
| Counter | `connections.totalCreated`, `opcounters` | Chuyển thành rate/increase theo thời gian |
| Histogram | Duration buckets | Tính p95/p99 |
| State/Event | Primary election, node down | Detect transition/duration |
| Derived ratio | Docs examined/returned, error rate | Có điều kiện mẫu số và volume |

### 4.1. Counter bị reset

Counter thường tăng từ khi MongoDB process chạy; khi restart, nó có thể quay về 0. Không tính delta âm thành throughput âm. Hệ thống telemetry phải xử lý counter reset; trong Prometheus thường dùng `rate()` hoặc `increase()`.

### 4.2. `connections.totalCreated` không phải số kết nối hiện tại

- `current`: incoming connections đang mở.
- `available`: số incoming connections còn có thể nhận.
- `totalCreated`: tổng số đã tạo từ khi process chạy.

Số `totalCreated` lớn có thể chỉ là uptime dài. Tốc độ `rate(totalCreated)` tăng bất thường mới gợi ý churn.

### 4.3. p95/p99 quan trọng hơn average

Average có thể đẹp dù một nhóm users đợi rất lâu. Với endpoint quan trọng, theo dõi p50, p95, p99, error rate, số requests và concurrency.

### 4.4. Percentile cần đủ số mẫu

Một request rất chậm trong ba requests không đủ kết luận p99 có xu hướng tăng bền vững. Alert nên có minimum sample count hoặc cửa sổ dài hơn.

### 4.5. Tỷ lệ khi mẫu số bằng 0

`docsExamined / nReturned` không xác định nếu không có document trả về. Khi giám sát, có thể dùng tỷ lệ có điều kiện hoặc metric examined tuyệt đối kèm số lượng returned. Không biến phép chia 0 thành vô hạn rồi page mọi lúc.

## 5. Baseline là gì?

**Dữ liệu nền (baseline)** ghi lại trạng thái bình thường của workload theo những điều kiện xác định, dùng làm cơ sở so sánh.

Ví dụ:

~~~text
Thứ hai, 09:00: 1.200 queries/min
Thứ hai, 02:00:    50 queries/min
Chủ nhật, 09:00:  150 queries/min
~~~

Nếu đặt alert một giá trị 500 queries/min, nó sẽ hiểu sai traffic ban ngày là bất thường và bỏ qua sự cố “traffic sụt còn 0” vào ban đêm.

### 5.1. Thu baseline bao lâu?

Có thể bắt đầu bằng 7–28 ngày lịch sử hoạt động bình thường, kéo dài nếu workload có chu kỳ cuối tháng/cuối quý. Không có một số ngày chung cho mọi hệ thống. Thời gian phải đủ bao phủ chu kỳ nghiệp vụ.

### 5.2. Baseline nên phân nhóm

- Giờ trong ngày, ngày trong tuần.
- Peak và off-peak.
- Region và cluster tier.
- Application/endpoint.
- Query shape.
- Primary và secondary.
- Trước/sau deploy.
- Batch/backfill có lịch.
- Loại tenant hoặc phân lớp workload, tránh cardinality quá cao.

### 5.3. Dữ liệu sự cố không trở thành bình thường

Một tuần có incident query chậm 10 lần không nên tự đẩy dynamic baseline cao thêm và che sự cố. Ghi nhãn incident windows và bảo vệ baseline khỏi drift trong khi đang điều tra.

### 5.4. Sự kiện làm baseline đổi

Cần review khi:

- MongoDB major version upgrade.
- Thêm/xóa index hoặc thay schema.
- Đổi tier/hardware/storage.
- Shard hoặc reshard.
- Thay ứng dụng/query shape.
- Tăng gấp nhiều lần traffic/dữ liệu.
- Chuyển region/network.
- Batch workload mới.

## 6. Bảng baseline mẫu

Tất cả số liệu dưới đây **giả định cho bài tập**, không phải giá trị mặc định của MongoDB.

| Chỉ số | Segment | p50 | p95 | p99 | Window |
|---|---|---:|---:|---:|---|
| API read latency | Orders peak | 30 ms | 90 ms | 160 ms | 4 tuần |
| API read latency | Orders off-peak | 20 ms | 60 ms | 110 ms | 4 tuần |
| Pool checkout wait | Orders API | 3 ms | 20 ms | 45 ms | 4 tuần |
| Secondary lag | rs0 node B | 0.2 s | 1.1 s | 2.5 s | 4 tuần |
| Query duration | get-open-orders | 8 ms | 30 ms | 60 ms | 4 tuần |

Metadata baseline ví dụ:

~~~yaml
baselineId: mongo-orders-prod-2026w46
windowStartUtc: 2026-10-17T00:00:00Z
windowEndUtc: 2026-11-14T00:00:00Z
cluster: orders-prod
releaseRange: orders-2026.10
excludedIncidents:
  - INC-2026-041
owner: platform
~~~

Đây là YAML quản trị tự định nghĩa, **không** phải cấu hình trực tiếp của MongoDB.

### 6.1. Không chỉ giữ average

Lưu quantiles, distribution, QPS, tỷ lệ error, thời gian đo và phiên bản hệ thống. Nếu chỉ giữ một con số “CPU trung bình 55%”, bạn khó phân biệt CPU 90% vào peak có bình thường không.

## 7. Ngưỡng tĩnh (static thresholds)

Ngưỡng tĩnh phù hợp khi có giới hạn kỹ thuật/kinh doanh rõ:

~~~text
Warning: disk used > 80% trong 10 phút
Critical: disk used > 92% trong 5 phút
~~~

Ưu điểm: dễ hiểu, dễ audit.

Nhược điểm: có thể tạo false positives khi workload khác nhau; disk 82% ổn định không khẩn cấp bằng disk 76% tăng 5% mỗi giờ.

### 7.1. Nên kết hợp thời gian đến khi cạn

~~~text
Estimated time to full =
    disk_free_bytes / estimated_growth_bytes_per_second
~~~

Đây là công thức dự báo đơn giản; nếu growth rate=0 hoặc âm thì không dùng phép chia trực tiếp. Forecast nên có độ tin cậy, seasonal behavior và điều kiện tối thiểu.

### 7.2. Không áp một CPU threshold cho mọi node

Node phục vụ heavy analytics có CPU cao theo thiết kế; node primary của transactional API có thể bị ảnh hưởng ngay cả khi CPU thấp vì I/O hoặc lock/tickets. Chọn severity dựa trên tác động nghiệp vụ.

## 8. Ngưỡng động (dynamic / baseline-relative)

Một rule ví dụ:

~~~text
observed_p95_ms > max(200, 2 * baseline_p95_ms)
for 10 minutes
AND request_count_5m >= 100
~~~

Nếu baseline là 80ms, ngưỡng ở đây là 200ms; nếu baseline 300ms thì ngưỡng là 600ms.

Đây chỉ là **logic minh họa**. Các giá trị 200ms, 2× và 10 phút cần được xác nhận qua SLO và dữ liệu thực.

### 8.1. Kết hợp absolute floor và relative multiplier

Nếu baseline p95 là 2ms, tăng 2× thành 4ms thường không đáng page. Absolute floor tránh noise. Nếu baseline là 500ms, một ngưỡng 200ms sẽ luôn báo động; relative multiplier tránh rule vô nghĩa.

### 8.2. Baseline theo time-of-week

So observed query latency vào thứ hai 09:00 với baseline của các khoảng tương tự; tránh so với đêm khuya không cùng QPS.

### 8.3. Đừng để baseline tự học incident

Nếu dynamic baseline liên tục học từ dữ liệu 30 phút vừa qua khi sự cố chưa được xử lý, nó có thể nâng chuẩn “bình thường” tới mức alert tự tắt. Cần freeze/exclude incident samples.

## 9. Duration, hysteresis và anti-flapping

Một cảnh báo bật/tắt liên tục sẽ làm mất niềm tin của on-call.

### 9.1. Minimum duration

~~~text
Alert ON:
  CPU > 85% liên tục 10 phút

Không page vì spike 5 giây.
~~~

Tuy nhiên các sự kiện như mất primary và data corruption có thể cần thông báo gần như tức thì; duration phải theo loại impact.

### 9.2. Hysteresis

~~~text
Alert ON:
  disk used > 90% trong 5 phút

Alert OFF:
  disk used < 82% trong 15 phút
~~~

Trigger và resolve khác ngưỡng giảm tình trạng flapping.

### 9.3. Deduplication và alert grouping

Một primary election có thể kích hoạt nhiều metrics: no primary, driver timeout, replication error, API 5xx. Group theo incident/cluster thay vì page on-call 20 lần.

### 9.4. Maintenance window

Planned maintenance nên được gắn nhãn để giảm false alarms; vẫn cần phát hiện những lỗi quan trọng như data loss, mất availability kéo dài hoặc backup bị phá.

### 9.5. No-data là một trạng thái cần theo dõi

Nếu exporter/Atlas integration ngừng gửi dữ liệu, dashboard im lặng **không** có nghĩa dịch vụ khỏe. Cần alert last-sample-age, exporter down và failure của alert delivery pipeline.

## 10. SLO, SLI và error budget

Resource metrics không trực tiếp đo trải nghiệm khách hàng. Một SLO ví dụ:

~~~text
Trong 30 ngày, ít nhất 99.9% request xem đơn hàng:
- thành công
- và hoàn tất trong 200ms
~~~

- **SLI:** tỷ lệ request đạt tiêu chí.
- **SLO:** mục tiêu của SLI.
- **Error budget:** phần requests có thể không đạt.
- **Burn rate:** tốc độ tiêu thụ ngân sách so với mức cho phép.

### 10.1. Ví dụ burn rate

Nếu SLO cho phép 0.1% requests không đạt, nhưng 5 phút gần nhất có 1% requests không đạt, burn rate tương ứng khoảng 10×.

Một page dựa duy nhất vào 1 phút có thể nhiễu; một alert chỉ dựa vào 24 giờ lại chậm. **Multi-window burn rate** kết hợp cửa sổ ngắn và dài để quyết định severity.

### 10.2. Liên kết DB metrics với SLO

Ví dụ:

~~~text
API p99 vượt SLO
    |
    +--> MongoDB query duration tăng
    +--> Docs examined per returned tăng
    +--> Disk/CPU cũng tăng
~~~

Đây là chuỗi bằng chứng mạnh hơn “CPU >80%”. Dù vậy cần kiểm tra trace và deploy events để xác nhận nguyên nhân.

## 11. Các nhóm metric MongoDB nên thu thập

| Nhóm | Metrics | Rủi ro |
|---|---|---|
| Availability | Node state, primary availability, elections | Read/write unavailable |
| Replication | Secondary lag, applied optime, oplog window | Stale reads, resync |
| Throughput | Opcounters rates, operation rates | Traffic spike/drop |
| Query | Duration p95/p99, docs/keys examined, nReturned | Query regression |
| Connections | Current, available, totalCreated rate, rejected | Connection exhaustion |
| Memory | WiredTiger cache, eviction, OS swap | Cache pressure |
| CPU | Process CPU, host CPU | Saturation |
| Disk | Capacity, IOPS, latency, disk queue | Full disk, slow I/O |
| Tickets/queues | Available tickets, queued operations | Backpressure |
| Sharding | Per-shard load, chunk distribution | Hot shard |
| Reliability | Backup freshness, PIT window, restore drill | Recovery risk |
| Security | Authentication failures, TLS errors | Credential/network issue |

Tên fields và khả năng thu thập phụ thuộc MongoDB version, Atlas tier, exporter và storage engine. Không giả định cùng một metric hiện hữu ở mọi deployment.

### 11.1. Cần cả góc nhìn per-node

Một cluster trung bình CPU 50% vẫn có thể có shard A CPU 95% và shard B CPU 5%. Một secondary lag lớn có thể bị average replication lag che giấu. Xem từng host/member/shard.

## 12. Ma trận ngưỡng mẫu

**Tất cả con số là ví dụ đề xuất điểm bắt đầu, không phải ngưỡng MongoDB bắt buộc.**

| Sự kiện | Warning ví dụ | Critical ví dụ |
|---|---|---|
| Primary unavailable | Có thay đổi trạng thái không theo lịch | Mất write availability vượt SLO |
| Secondary lag | >5s trong 5 phút | >30s trong 3 phút |
| Oplog window | <24h | Thấp hơn downtime recovery dự kiến |
| Disk used | >80% và tăng nhanh | >90% hoặc time-to-full rất ngắn |
| CPU | >85% trong 10 phút | >95% trong 5 phút kèm latency |
| Query p95 | >2× baseline và vượt floor | Vi phạm SLO kéo dài |
| Connections | Available giảm mạnh | Rejected/checkout timeouts tăng |
| Queues | Vượt baseline kéo dài | Queue tăng kèm p99 xấu |
| Errors | Tăng trên baseline | Burn rate vượt ngưỡng P1/P2 |
| Backup | Quá lịch backup đã verify | Không còn recovery point đạt RPO |

### 12.1. Severity nên dựa trên impact

P1 có thể là không ghi được dữ liệu, khả năng mất dữ liệu hoặc phần lớn người dùng ảnh hưởng. P2 là suy giảm đáng kể nhưng còn workaround. P3 là cảnh báo capacity cần xử lý trong giờ làm việc. Định nghĩa cụ thể nên được tổ chức phê duyệt.

### 12.2. Kết hợp nguyên nhân và triệu chứng

Disk 92% chưa chắc phải page nếu ổn định và có headroom được dự báo; disk 78% tăng rất nhanh có thể cần ưu tiên cao. SLO, growth rate, runbook và khả năng can thiệp mới quyết định severity.

## 13. Atlas Alerts và Notifications

MongoDB Atlas hỗ trợ alert conditions, thresholds, notification methods và các alerts mặc định ở cấp project. Người vận hành có thể cấu hình alerts theo project/organization tương ứng với quyền được cấp.

Quy trình:

1. Chọn project và cluster.
2. Xem baseline trong Metrics/Monitoring.
3. Mở Alerts/Alert Settings.
4. Chọn condition/metric đúng loại cluster.
5. Đặt ngưỡng, duration và routing.
6. Gắn owner/runbook theo hệ thống incident nội bộ.
7. Kiểm tra notification channel.
8. Review false positives/missed incidents sau thời gian vận hành.

### 13.1. Free/Flex và Dedicated có mức observability khác nhau

Atlas Free/Flex chỉ hỗ trợ metric/alert conditions dành cho tier của nó. Real-Time Performance Panel có điều kiện M10+. Query Profiler/Performance Advisor cũng có các giới hạn theo deployment và product configuration.

Không hứa rằng mọi screenshot hoặc menu Atlas của một tier sẽ giống một tier khác.

### 13.2. Tickets/queues alert từ tài liệu Atlas

Atlas Alert Basics đưa ra gợi ý cảnh báo khi **available tickets giảm** hoặc **queues tăng** trong vài phút, với mục tiêu tránh false positives do spike thoáng qua. Các con số mẫu của Atlas phải được hiệu chỉnh theo workload, server version và metric definition của deployment.

### 13.3. Notifications chỉ là lớp phân phối

Có thể chuyển cảnh báo qua email, webhook và các integrations được Atlas hỗ trợ. Incident vẫn cần ACK, escalation, owner, status update và runbook.

## 14. Atlas Query Profiler, RTPP và Performance Advisor

Các công cụ Atlas bổ sung nhau:

- **Query Profiler:** tìm queries chậm theo thời gian, namespace, duration, docs examined/returned và hiệu quả index.
- **Real-Time Performance Panel:** xem operations/network/hardware gần thời gian thực, có điều kiện M10+.
- **Performance Advisor:** phân tích slow queries và đề xuất indexes/query improvements.
- **Sharding Insights:** quan sát phân phối workload/chunks trên sharded clusters được hỗ trợ.

### 14.1. Performance Advisor không thay review index

Một index mới có thể làm tăng storage/write amplification, làm trùng index hiện có hoặc tạo thay đổi query planner. Cần đối chiếu workload, cardinality và rollout trước khi apply vào production.

### 14.2. Query Profiler có thể có thông tin nhạy cảm

Profiler/logs chứa query shape/metadata và có thể làm lộ thông tin nghiệp vụ. Giới hạn quyền, retention và redaction trước khi chia sẻ bên ngoài team.

### 14.3. Correlate với change events

Đặt biểu đồ p99/query shape cạnh releases, index builds, scaling và backups. Có sự kiện trước incident là manh mối, không phải bằng chứng nguyên nhân độc lập.

## 15. Self-managed MongoDB: serverStatus

Với tài khoản monitoring có quyền phù hợp:

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });

printjson({
  host: s.host,
  uptime: s.uptime,
  connections: s.connections,
  opcounters: s.opcounters,
  network: s.network
});
~~~

Output và fields thay đổi theo MongoDB version, node type và storage engine.

### 15.1. Connections

~~~javascript
s.connections.current;
s.connections.available;
s.connections.totalCreated;
~~~

MongoDB 6.3 bổ sung `connections.rejected`. Các versions mới có thể có thêm queue/connection establishment metrics. Khi viết collector, kiểm tra tồn tại của field và version.

### 15.2. Network và opcounters

~~~javascript
s.network.bytesIn;
s.network.bytesOut;
s.network.numRequests;

s.opcounters;
~~~

Đây thường là counters. Chuyển thành rates, so với throughput ứng dụng; không coi tổng bytesIn là số bytes/s.

### 15.3. Uptime reset là dấu hiệu quan trọng

Nếu uptime về thấp, node có thể vừa restart. Khi nhiều counters reset cùng lúc, check restart/election/host logs trước khi kết luận traffic sụt.

## 16. WiredTiger cache, eviction và disk I/O

WiredTiger thường tận dụng RAM làm cache. Cache usage cao **không tự chứng minh thiếu bộ nhớ**.

Ví dụ đọc một vài fields tùy phiên bản:

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });
const cache = s.wiredTiger && s.wiredTiger.cache;

if (cache) {
  printjson({
    bytesInCache: cache["bytes currently in the cache"],
    maximumBytes: cache["maximum bytes configured"],
    dirtyBytes: cache["tracked dirty bytes in the cache"]
  });
}
~~~

Cần xác minh tên field với output MongoDB/WiredTiger thực tế của version đang chạy.

### 16.1. Những dấu hiệu hữu ích hơn “cache used 90%”

- Eviction activity và application threads tham gia eviction.
- Dirty pages, checkpoints.
- Disk read/write latency.
- OS swap/memory pressure.
- p95/p99 queries.
- Working set thay đổi.
- Read/write ticket availability.

### 16.2. Disk full vs disk slow

Disk used là **capacity**; disk latency/IOPS là **performance**. Có thể gặp disk latency cao dù free space còn nhiều.

### 16.3. Đừng xóa WiredTiger files để giải phóng ổ

Các file dữ liệu/journal của MongoDB phải được quản lý qua MongoDB commands/runbook. Xóa trực tiếp trên filesystem có thể gây mất dữ liệu/corruption.

## 17. Tickets, queues và flow control

Các phiên bản MongoDB/WiredTiger có metrics về available read/write tickets, queue depth và flow control. Cần dùng tên metric tương ứng với server/Atlas tier thực tế.

Cảnh báo tốt kết hợp:

~~~text
Available tickets thấp
AND queue depth tăng
AND p99 latency tăng
trong 5 phút
~~~

Không chỉ page vì 1 mẫu tickets giảm thoáng qua.

### 17.1. Flow control có liên quan replication

Flow control có thể giới hạn tốc độ writes trên primary khi majority commit lag cao, nhằm tránh secondaries tụt quá xa. Nếu write latency tăng đồng thời lag lớn, xem secondary disks/network/flow control thay vì mặc định tăng pool.

### 17.2. Connection pool quá lớn có thể làm tình hình tệ hơn

Tăng pool từ 100 lên 500 trên mỗi application instance có thể khuếch đại hàng đợi khi database đã quá tải. Phải xác định bottleneck và dùng backpressure/concurrency limits.

## 18. Replica set và replication lag

Các tín hiệu quan trọng:

- Có PRIMARY hay không?
- Members có healthy/majority không?
- Secondaries bị lag bao lâu?
- Oplog window đủ cho downtime dự kiến không?
- Có elections liên tục không?
- Majority write latency tăng không?

### 18.1. Kiểm tra bằng mongosh

~~~javascript
rs.status();
rs.printSecondaryReplicationInfo();
rs.printReplicationInfo();
~~~

- `rs.status()`: topology, member states, optimes, heartbeat/election context.
- `rs.printSecondaryReplicationInfo()`: thông tin về secondary replication lag.
- `rs.printReplicationInfo()`: oplog size và khoảng thời gian được giữ.

Trong scripts có thể dùng `db.getReplicationInfo()` cho thông tin có cấu trúc.

### 18.2. Oplog window là thời gian, không chỉ kích thước GB

Oplog window chịu ảnh hưởng write rate. Khi writes tăng, cùng một dung lượng oplog có thể chỉ giữ lịch sử ngắn hơn.

~~~text
Oplog window: 8 giờ
Secondary offline: 12 giờ
=> Có rủi ro secondary không bắt kịp bằng oplog.
~~~

Tài liệu MongoDB khuyến nghị oplog đủ cho thời gian secondary có thể unavailable; thường ít nhất khoảng 24 giờ, và nhiều hệ thống chọn 72 giờ hoặc lâu hơn theo khả năng recovery.

### 18.3. Cần monitor từng member

Một secondary lag 30 giây và một secondary lag 0.5 giây không nên được gộp thành “cluster replication lag bình thường” nếu ứng dụng đọc từ member bị chậm.

### 18.4. Không đổi writeConcern chỉ để che triệu chứng

Nếu majority writes chậm vì secondary lag, tùy tiện giảm write concern có thể thay đổi durability guarantees. Đánh giá impact và remediation theo runbook được phê duyệt.

## 19. Primary elections

Election có thể do maintenance, node failure, network, resource stall hoặc unexpected restart.

Dấu hiệu điều tra:

- Primary changes theo timestamp.
- Heartbeat failures.
- `rs.status()` member states.
- Node uptime/restarts.
- Driver `NotPrimary` hoặc server selection timeouts.
- Replication health và quorum.
- TLS/DNS/network errors.
- Atlas events/maintenance calendar.

### 19.1. Planned vs unplanned

Một planned failover ngắn mà clients retry thành công có thể là sự kiện quan sát. Một replica set mất primary kéo dài hoặc elections lặp gây write failures là incident.

### 19.2. Tránh thay topology tùy tiện

`rs.stepDown()`, `rs.reconfig()` và restart đồng thời nhiều members đều có thể tăng outage. Cần bảo toàn quorum và có approval/runbook.

## 20. Sharded clusters và hot shard

Một cluster có thể:

~~~text
Shard A: CPU 90%, p99=1200ms
Shard B: CPU 30%, p99=100ms
Cluster average CPU: 60%
~~~

Average che giấu shard A bị saturation.

Điều tra:

- Load theo từng shard và member.
- Shard key predicate có xuất hiện trong query không?
- Query có scatter-gather không?
- Chunk distribution và jumbo chunks.
- Balancer/migration events.
- Indexes có nhất quán không?
- Hot tenant/partition?
- Query explain qua `mongos`.

Không quyết định resharding trong incident khi chưa đánh giá resource cost, side effects và rollback.

## 21. Query plan và explain

Truy vấn mẫu:

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "OPEN"
}).sort({
  createdAt: -1
}).explain("executionStats");
~~~

Quan sát:

- Winning plan/stages.
- `totalDocsExamined`.
- `totalKeysExamined`.
- `nReturned`.
- `executionTimeMillis`.
- `COLLSCAN` hay `IXSCAN`.
- Có blocking sort không.
- Index name và bounds.

### 21.1. IXSCAN không đồng nghĩa tối ưu

Một index có thể được dùng nhưng quét hàng trăm nghìn keys để trả vài documents. Cần xem scanned-to-returned ratio và latency.

### 21.2. COLLSCAN không phải lúc nào xấu

Một collection có bốn documents có thể được quét nhanh hơn dùng index. Với endpoint realtime trên collection lớn, COLLSCAN có thể là vấn đề.

### 21.3. Explain trên lab không thay performance test

Execution statistics phụ thuộc data size, cache, concurrency và plan. Không lấy `executionTimeMillis` từ một lần explain để tuyên bố production p99.

## 22. $currentOp để quan sát operations đang chạy

Với quyền monitoring phù hợp:

~~~javascript
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
      secs_running: { $gte: 5 }
    }
  },
  {
    $project: {
      opid: 1,
      ns: 1,
      desc: 1,
      secs_running: 1,
      waitingForLock: 1
    }
  },
  { $limit: 30 }
]);
~~~

`$currentOp` phải đứng đầu pipeline. `allUsers:true` yêu cầu privileges như `inprog` khi xác thực được bật. Chỉ dùng tài khoản được cấp quyền monitoring phù hợp.

### 22.1. $currentOp không phải lịch sử đầy đủ

Operations đã kết thúc không còn trong current operations. Dùng slow logs/Query Profiler/database profiler nếu cần điều tra lịch sử.

### 22.2. Đừng kill operation ngay

`db.killOp()` có thể ảnh hưởng transactions, migrations và tác vụ admin. Trước khi hủy, xác minh owner, phạm vi, tác động và approval.

## 23. Database profiler của MongoDB

Profiler ghi operations vào capped collection `system.profile` theo database.

| Mức | Ý nghĩa |
|---|---|
| 0 | Không ghi profiler entries |
| 1 | Ghi slow operations hoặc theo filter |
| 2 | Ghi mọi operations |

MongoDB cảnh báo profiler có thể ảnh hưởng performance và disk usage, đặc biệt level 2 hoặc threshold quá thấp.

### 23.1. Bật thử trên self-managed lab

~~~javascript
use observability_lab

db.getProfilingStatus();

db.setProfilingLevel(1, {
  slowms: 200,
  sampleRate: 0.1
});
~~~

Lệnh là một cấu hình có tác động. `slowms` và `sampleRate` có thể ảnh hưởng toàn process/diagnostic logs, không chỉ database hiện tại theo version. Ghi lại cấu hình ban đầu trước khi thay.

### 23.2. Xem mẫu slow operations

~~~javascript
db.system.profile.find(
  { millis: { $gte: 200 } },
  {
    ts: 1,
    ns: 1,
    millis: 1,
    planSummary: 1,
    keysExamined: 1,
    docsExamined: 1
  }
).sort({ ts: -1 }).limit(20);
~~~

Đọc dữ liệu profile có quyền và retention phù hợp; tránh xuất raw command nếu nó có PII.

### 23.3. Tắt khi hết giai đoạn điều tra

~~~javascript
db.setProfilingLevel(0);
~~~

Nhớ khôi phục các giá trị slowms/sampleRate cũ nếu đã thay đổi. Không coi `setProfilingLevel(0)` tự phục hồi mọi setting ban đầu.

### 23.4. mongos không có database profiler như mongod

MongoDB không hỗ trợ bật profiler trên `mongos`. Có thể điều chỉnh slow operation log theo tài liệu, nhưng không mong có `system.profile` của mongos.

## 24. $queryStats: hữu ích nhưng cần cẩn trọng

Trên môi trường và phiên bản hỗ trợ:

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $queryStats: {} },
  { $limit: 10 }
]);
~~~

Lưu ý:

- `$queryStats` chạy trên `admin`, là stage đầu pipeline.
- Trang MongoDB Manual hiện cảnh báo tính năng **unsupported**, output format không được bảo đảm ổn định qua releases.
- Với Atlas, tài liệu mô tả yêu cầu tier ít nhất M10.
- Cần `queryStatsRead` privilege, có trong `clusterMonitor`.
- Thống kê theo query shape lưu trong memory, có sampling/giới hạn theo phiên bản.
- Không dùng output làm nguồn sự thật duy nhất của incident.

### 24.1. Khi nào nên cân nhắc?

Để nhóm những query shapes hay chạy, so sánh execution behavior và tìm workloads có chi phí cao. Đối chiếu thêm application metrics, logs và Query Profiler.

### 24.2. Vì sao không làm alert dựa trên field path cố định?

Schema `$queryStats` thay đổi theo MongoDB release. Nếu collector giả định một field nhất định luôn tồn tại, sau upgrade alert có thể lỗi hoặc im lặng. Dùng integration được hỗ trợ và version tests.

## 25. Java driver monitoring

Application Java cần instrument:

- Connection checkout wait.
- Connection creation/close.
- Server selection time.
- Command duration và failure.
- Retry count.
- Pool utilization.
- Query shape/operation name, không log values nhạy cảm.
- API latency và error rate.

### 25.1. Ví dụ CommandListener an toàn

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;

import java.util.concurrent.TimeUnit;

class SafeMongoListener implements CommandListener {
    @Override
    public void commandStarted(CommandStartedEvent e) {
        // Chỉ ghi tên command, không ghi e.getCommand().
        System.out.println("Mongo started: " + e.getCommandName());
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent e) {
        System.out.println("Mongo succeeded: "
            + e.getCommandName() + " in "
            + e.getElapsedTime(TimeUnit.MILLISECONDS) + "ms");
    }

    @Override
    public void commandFailed(CommandFailedEvent e) {
        System.out.println("Mongo failed: "
            + e.getCommandName() + " in "
            + e.getElapsedTime(TimeUnit.MILLISECONDS) + "ms");
    }
}

// Đặt trong phương thức khởi tạo và cung cấp URI qua secret manager.
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(mongoUri))
    .addCommandListener(new SafeMongoListener())
    .build();

MongoClient client = MongoClients.create(settings);
~~~

`mongoUri` là biến của ứng dụng lấy từ cấu hình bảo mật. Không in URI (có thể chứa password) vào logs. Ví dụ dùng `System.out` để đơn giản hóa; production nên export metrics có sampling/cardinality control.

### 25.2. Server nhanh nhưng app vẫn chậm

Nếu server query execution p95 20ms nhưng API p95 800ms, kiểm tra pool checkout, network, DNS, TLS, retries và application logic trước khi thêm index.

## 26. Query shapes và bảo mật telemetry

Logs/traces/profiler có thể chứa:

- Full query values.
- Email, phone, tên hoặc user identifiers.
- MongoDB connection URI chứa credentials.
- Document content.
- Internal database/collection names.
- Network topology.

Các nguyên tắc:

1. Không log passwords/tokens/private keys.
2. Redact hoặc hash sensitive values.
3. Gắn metric labels theo query shape, không theo mỗi user/document.
4. Dùng TLS cho telemetry pipeline.
5. Giới hạn retention và quyền truy cập logs/profiler.
6. Có audit khi truy xuất incident evidence.
7. Tránh full collection export chỉ để debug.
8. Có policy cho dữ liệu gửi tới bên thứ ba.

Ví dụ thông báo không nên gồm:

~~~text
Slow query: email=customer@example.test, token=secret
~~~

Nên:

~~~text
Query shape: customers-by-email
Namespace: appdata.customers
p99 duration: 1.4s
Docs examined: high
Trace ID: abcd...
~~~

## 27. Một rule biểu diễn dưới dạng pseudo config

~~~yaml
id: mongo-orders-p95-query
service: orders-api
cluster: orders-prod
severity: warning
window: 5m
minimumRequests: 100
condition: "p95 > max(200ms, 2 x baseline_p95)"
duration: 10m
resolutionCondition: "p95 < max(160ms, 1.5 x baseline_p95)"
resolutionDuration: 15m
notify:
  - orders-oncall
  - db-platform
runbook: "https://internal.example.test/runbooks/query-regression"
~~~

Đây là mô tả logic tự định nghĩa, **không phải cấu hình YAML trực tiếp của MongoDB Atlas**.

### 27.1. Ví dụ PromQL minh họa

Nếu ứng dụng tự instrument histogram `app_mongodb_command_duration_seconds_bucket`:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(app_mongodb_command_duration_seconds_bucket[5m])
  )
)
~~~

Metric trong ví dụ không phải metric MongoDB tự động xuất. Cần code/instrumentation đúng để nó tồn tại.

## 28. Sơ đồ điều tra incident

~~~text
DETECT / ALERT
       |
       v
ACK + ASSIGN OWNER
       |
       v
MEASURE USER IMPACT
       |
       v
PRESERVE EVIDENCE
       |
       v
BUILD HYPOTHESES
       |
       v
MITIGATE SAFELY
       |
       v
VERIFY RECOVERY
       |
       v
POSTMORTEM + ACTIONS
~~~

### 28.1. Ưu tiên impact trước nguyên nhân

Hỏi:

- Bao nhiêu người/requests bị ảnh hưởng?
- Những endpoints, regions, tenants nào?
- Có data loss, stale reads hoặc writes thất bại không?
- Sự cố bắt đầu lúc nào?
- Có workaround hoặc rollback an toàn không?
- Cần nâng severity/escalate không?

Không cần biết root cause mới bắt đầu mitigation hợp lý.

### 28.2. Ghi timestamp UTC

~~~text
10:02:13Z  Deploy orders-api v3
10:04:00Z  API p95 tăng
10:04:20Z  Docs examined tăng
10:06:00Z  Alert fired
10:07:10Z  On-call ACK
10:12:00Z  Canary rollback
10:14:00Z  p95 về baseline
~~~

### 28.3. Evidence và hypothesis khác nhau

- **Observation:** query p95 tăng 5×.
- **Hypothesis:** deploy mới gây thiếu index.
- **Evidence:** query shape mới, explain có COLLSCAN, canary rollback phục hồi.
- **Conclusion:** có cơ sở liên kết thay đổi query với regression.

Không viết “MongoDB hỏng vì release” chỉ từ một đường biểu đồ.

## 29. Incident roles và giao tiếp

| Vai trò | Trách nhiệm |
|---|---|
| Incident Commander | Điều phối và ưu tiên |
| DB/Platform Operator | Điều tra MongoDB, thực hiện mitigation được phê duyệt |
| Application Owner | Xác định user impact, đổi release/traffic |
| Communications | Cập nhật stakeholders |
| Scribe | Ghi timeline và evidence |
| Security | Tham gia khi có dấu hiệu tấn công/dữ liệu bị lộ |

Một sự cố nhỏ có thể gộp vai trò. Quan trọng là biết ai chịu trách nhiệm và người khác không chạy các lệnh mâu thuẫn.

### 29.1. Status update tốt

Nêu phạm vi ảnh hưởng, triệu chứng xác nhận, mitigation đang làm, những gì chưa rõ và owner bước tiếp theo. Không đưa password/PII vào incident chat.

### 29.2. Production changes trong incident cần trace

Ghi command/action, identity, approval, mốc giờ và kết quả. Những lệnh như `rs.reconfig()`, `rs.stepDown()`, `killOp` hoặc drop index phải được đánh giá rủi ro trước.

## 30. Runbook A — Query regression sau release

**Triệu chứng:** Query p95/p99 tăng, docs examined/returned tăng, API timeouts.

1. Đo impact theo endpoint và tenant.
2. Xem release/change calendar.
3. So query shapes ở Query Profiler/slow logs.
4. Chạy `explain("executionStats")` trên query tương đương.
5. Kiểm tra `COLLSCAN`, indexName, examined/returned, blocking sort.
6. Đánh giá những workload khác có bị ảnh hưởng không.
7. Nếu có bằng chứng, rollback canary/release hoặc giảm tải batch.
8. Xem xét index mới theo change control, không tạo vội trên cluster đang rất tải.
9. Verify p95/p99 và errors về baseline.
10. Thêm performance regression test và alert theo shape.

**Không** kết luận chỉ từ `IXSCAN` hoặc `COLLSCAN` mà bỏ qua data volume/latency.

## 31. Runbook B — Connection storm

**Triệu chứng:** connection checkout timeouts, `connections.current` tăng, `available` giảm, `totalCreated` rate tăng.

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });
printjson(s.connections);
~~~

Kiểm tra:

- Số application instances và pool max size.
- App vừa autoscale/deploy không?
- Driver connection creation rate.
- Rejected connections (khi field được hỗ trợ).
- TLS handshake/DNS/network failures.
- CPU, memory và queue.
- Có retry storm không?

Ví dụ 20 pods cấu hình max pool 100 có giới hạn lý thuyết 2.000 connections từ các pools đó, **không** có nghĩa chúng luôn mở đủ 2.000.

Mitigation: kiểm soát autoscaling, connection churn, pool sizes, retries/backoff và DB capacity; tránh restart tất cả app pods cùng lúc.

## 32. Runbook C — Secondary replication lag

~~~javascript
rs.status();
rs.printSecondaryReplicationInfo();
rs.printReplicationInfo();
~~~

Thu thập:

- Lag tăng trên member nào?
- Primary write rate có tăng đột biến?
- Secondary CPU/disk/network có bị nghẽn?
- Oplog window còn bao lâu?
- Có index build, backup, restart hoặc initial sync không?
- Flow control và majority write latency thay đổi thế nào?

Mitigation: giảm bulk writes không thiết yếu, khắc phục bottleneck ở secondary/network, scale khi cần, bảo đảm member hồi phục trước khi làm node khác.

Không tùy tiện giảm writeConcern để che lag; đó là thay đổi durability semantics.

## 33. Runbook D — Disk pressure

Theo dõi:

- Disk free bytes và time-to-full.
- Disk latency/IOPS/throughput.
- Growth theo database/collection.
- WiredTiger cache/dirty bytes/checkpoints.
- Backups/index builds/batches đang chạy.
- Host/system errors.

Mitigation: scale storage có kế hoạch, giảm workload bất thường, kiểm tra temporary files/logs và cleanup qua công cụ an toàn. Không xóa trực tiếp file WiredTiger/journal.

Verify disk headroom và query latency ổn định; không có corruption/replication lag mới.

## 34. Runbook E — Primary elections bất thường

Kiểm tra:

- `rs.status()` và members.
- Heartbeat/election logs.
- Host restarts/OOM/disk stalls.
- DNS/TLS/network paths.
- Majority quorum.
- Driver retry/server selection errors.
- Maintenance/change events.

Một election có kế hoạch không tương đương incident P1 nếu app retry thành công. Nhưng repeated elections và mất primary kéo dài cần phản ứng nghiêm trọng.

Không tự chạy `rs.stepDown()`/`rs.reconfig()` khi chưa biết quorum và rollback.

## 35. Runbook F — Authentication/TLS failures

Dấu hiệu: MongoDB `AuthenticationFailed`, auth code 18, TLS handshake exceptions.

Điều tra:

- Password/secret rotation gần đây.
- Pods có secret version mới chưa?
- `authSource` và auth mechanism.
- URI encoding các ký tự đặc biệt.
- TLS certificate expiry/SAN/CA.
- IP access/network endpoint.
- Dấu hiệu brute-force/credential compromise.
- Driver/client pool có cần recreate không?

TLS handshake failure xảy ra ở lớp khác SCRAM; authorization failure là đã auth nhưng thiếu quyền. Không quy mọi lỗi kết nối thành password sai.

## 36. Lab nhỏ: quan sát index và query

Tạo database thử nghiệm:

~~~javascript
use observability_lab

db.orders.insertMany([
  {
    _id: 1,
    tenantId: "tenant-A",
    status: "OPEN",
    amount: 120,
    createdAt: ISODate("2026-11-01T08:00:00Z")
  },
  {
    _id: 2,
    tenantId: "tenant-A",
    status: "CLOSED",
    amount: 400,
    createdAt: ISODate("2026-11-02T08:00:00Z")
  },
  {
    _id: 3,
    tenantId: "tenant-B",
    status: "OPEN",
    amount: 90,
    createdAt: ISODate("2026-11-03T08:00:00Z")
  },
  {
    _id: 4,
    tenantId: "tenant-A",
    status: "OPEN",
    amount: 250,
    createdAt: ISODate("2026-11-04T08:00:00Z")
  }
]);
~~~

### 36.1. Explain trước khi thêm index

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "OPEN"
}).sort({ createdAt: -1 })
  .explain("executionStats");
~~~

### 36.2. Tạo index và so lại

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1
  },
  {
    name: "idx_tenant_status_createdAt"
  }
);
~~~

Chạy lại explain. Với bốn documents, query planner có thể chọn COLLSCAN do dataset quá nhỏ. Đây là bài tập cú pháp, không phải benchmark.

### 36.3. Trạng thái profiler trước/sau

~~~javascript
db.getProfilingStatus();
~~~

Chỉ bật level 1 trên lab với quyền phù hợp, lưu cấu hình ban đầu và khôi phục sau bài tập.

## 37. Chẩn đoán end-to-end với Java client

Một health check ngắn:

~~~java
import com.mongodb.client.MongoClient;
import org.bson.Document;

public class MongoReachability {
    public static boolean canReachServer(MongoClient client) {
        try {
            Document result = client.getDatabase("admin")
                .runCommand(new Document("ping", 1));
            return ((Number) result.get("ok")).doubleValue() == 1.0;
        } catch (RuntimeException ex) {
            // Ghi metric/traces đã redacted ở tầng gọi.
            return false;
        }
    }
}
~~~

**Ping không thay readiness nghiệp vụ**. Nó không chứng minh query có index, transactions hoạt động hoặc p99 nằm trong SLO. Health checks phải nhẹ, không truy vấn dữ liệu lớn chỉ để kiểm tra trạng thái.

### 37.1. Retries cần giới hạn

Exponential backoff, jitter, deadline và circuit breaker giúp tránh retry storm. Unlimited retries khi MongoDB đã quá tải có thể làm sự cố nặng hơn.

## 38. Case study: một release gây tăng tài liệu phải quét

Baseline giả định:

~~~text
API p95: 80ms
MongoDB query p95: 25ms
Docs examined / returned: 4
CPU: 45%
Secondary lag: <1s
~~~

Sau deploy:

~~~text
API p95: 700ms
MongoDB query p95: 500ms
Docs examined / returned: 20.000
CPU: 85%
Secondary lag: ~1s
~~~

Chuỗi điều tra:

1. API SLO alert được kích hoạt.
2. Query duration và examined ratio tăng.
3. Replication lag vẫn ổn định, giảm ưu tiên giả thuyết replication.
4. Query Profiler cho thấy shape mới.
5. Explain trên shape mới có plan không phù hợp.
6. Release diff xác nhận filter/sort thay đổi.
7. Rollback có kiểm soát làm p95 về baseline.
8. Thêm index/query review trong pipeline deployment.

Điều này có cơ sở gọi là **query regression do release**, mạnh hơn kết luận “MongoDB CPU cao”.

## 39. Postmortem và root-cause analysis

Một postmortem có các mục:

| Mục | Nội dung |
|---|---|
| Impact | Users, endpoints, thời lượng, dữ liệu |
| Timeline | Sự kiện theo UTC |
| Trigger | Điều kích hoạt chuỗi |
| Contributing factors | Những điều kiện khiến impact lớn |
| Detection | Alert nào bắn, nhanh/chậm thế nào |
| Mitigation | Hành động nào giảm impact |
| Recovery verification | Khi nào SLO ổn định |
| Prevention | Action items có owner và hạn |

### 39.1. Trigger không phải toàn bộ root cause

Trigger là release query mới; contributing factors có thể là staging data không đại diện, thiếu index review, thiếu load test và alert chỉ xem CPU.

### 39.2. Action item cần đo được

Không nên ghi “monitor tốt hơn”. Nên viết:

- Thêm load test cho query shape `list-open-orders` trước release.
- Alert p95 theo endpoint và DB query shape.
- Review indexes cho query mới.
- Thêm runbook query regression.
- Diễn tập rollback canary hằng quý.

### 39.3. Review chất lượng cảnh báo

- Alert có đến trước khách hàng báo lỗi không?
- Có false positive liên tục không?
- Có missed incident không?
- Dashboard có đủ evidence không?
- Người nhận có action được không?
- Có thiếu metrics vì exporter down không?

## 40. Governance cho thay đổi thresholds

Nâng ngưỡng CPU từ 90% lên 99% chỉ để alert hết bắn là **che triệu chứng**, không phải tự động giải quyết vấn đề.

Thay threshold cần:

1. Baseline và số liệu thực.
2. SLO liên quan.
3. Các lần alert/incident gần đây.
4. Threshold cũ/mới.
5. Duration/hysteresis.
6. Owner phê duyệt.
7. Review date và rollback.

Ví dụ registry:

~~~yaml
alertId: mongo-orders-disk-growth
version: 3
owner: platform-oncall
signal: disk-time-to-full
window: 7d-trend
threshold: less-than-14-days
baselineRef: orders-2026w46
approvedAtUtc: 2026-11-14T00:00:00Z
~~~

Đây là metadata quản lý alert tự định nghĩa, không phải MongoDB config.

## 41. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Chỉ alert CPU | Bỏ qua disk, network, pool, replication | Golden signals + DB metrics |
| CPU cao luôn P1 | False positive | Xem user impact |
| CPU thấp nghĩa ổn | Bỏ qua query/pool bottleneck | Multi-signal monitoring |
| Một ngưỡng mọi workload | Cảnh báo sai mùa vụ | Baseline theo segment |
| Dùng average latency | Che tail p99 | Theo dõi percentiles |
| Dùng counter nguyên giá trị | Alert vì uptime dài | Rate + reset handling |
| No data = OK | Mất observability | No-data alert |
| Trigger/resolve cùng ngưỡng | Flapping | Hysteresis |
| Bật profiler level 2 trên prod liên tục | Overhead/PII | Sampling, có giới hạn |
| Mongos có system.profile | Không đúng | Dùng log/Atlas tools |
| $currentOp lưu lịch sử | Mất dữ liệu của operations đã xong | Slow logs/profiler |
| $queryStats schema ổn định | Break collector khi upgrade | Version-aware design |
| COLLSCAN luôn xấu | Điều tra sai trên data nhỏ | So performance thực |
| IXSCAN luôn tốt | Quét nhiều keys | Examine/return ratio |
| Replica set thay backup | Xóa nhầm replicate | Backup/PIT |
| Replication lag một member bằng cluster lag | Bỏ sót secondary lỗi | Per-member |
| Oplog window cố định khi write volume tăng | Mất khả năng catch up | Monitor time window |
| Tăng pool khi DB quá tải | Tăng saturation | Backpressure/tune |
| Tất cả errors là bad password | Bỏ qua TLS/network/authSource | Phân loại |
| Full query trong alerts | Lộ PII/secrets | Query shape/redaction |
| Trigger là root cause | Kết luận thiếu chứng cứ | RCA và thí nghiệm |
| Một email đủ điều hành incident | Không ACK/escalate | Runbook/on-call |
| KillOp bừa bãi | Hủy tác vụ quan trọng | Approval |
| Sửa alert để hết page | Che impact | Threshold governance |

## 42. Bài tập thực hành

Chạy lệnh có tác động trong **lab**, không tùy tiện bật profiler, tạo index, hủy operation hoặc reconfigure production.

### Bài 1 — Golden signals

Phân loại API p99, opcounters rate, authentication errors, disk latency và connection checkout wait.

### Bài 2 — Baseline theo ngày/giờ

Peak traffic 10 lần off-peak. Vì sao không dùng average QPS toàn ngày làm dynamic baseline?

### Bài 3 — Gauge và counter

Phân biệt `connections.current` và `connections.totalCreated`; metric nào cần `rate()`?

### Bài 4 — Counter reset

Vì sao counter giảm sau restart không có nghĩa throughput âm?

### Bài 5 — Tail latency

Average 30ms, p99 1500ms. Cần theo dõi thêm tín hiệu gì?

### Bài 6 — Ngưỡng động

Baseline p95 80ms; floor=200ms, multiplier=2. Threshold nào được chọn và vì sao?

### Bài 7 — Hysteresis

Đề xuất trigger/resolve cho disk used, kèm duration.

### Bài 8 — No-data

Một monitoring agent tắt và không có mẫu mới. Thiết kế alert phát hiện.

### Bài 9 — SLO burn rate

SLO 99.9%, bad request ratio 1%. Burn rate xấp xỉ bao nhiêu?

### Bài 10 — Severity

Khi nào primary election là event bình thường, và khi nào P1?

### Bài 11 — Atlas tier

Vì sao Free/Flex không nên được giả định có mọi alert/Real-Time Panel như M10+?

### Bài 12 — serverStatus

Chạy lệnh lấy `connections` trên lab và giải thích current/available/totalCreated.

### Bài 13 — Cache

Cache usage 90% nhưng p99/eviction/disk latency bình thường. Có đủ dữ liệu scale không?

### Bài 14 — Disk forecast

Disk used 78%, tăng 4% mỗi ngày. Hãy tạo cảnh báo time-to-full.

### Bài 15 — Query explain

Vì sao `IXSCAN` không bảo đảm query hiệu quả?

### Bài 16 — Current operations

Dùng `$currentOp` lọc `secs_running>=5`. Tại sao không tự động killOp?

### Bài 17 — Profiler

Bật profiling level 1 với sample trên lab, đọc `system.profile` rồi hoàn nguyên cấu hình.

### Bài 18 — $queryStats

Vì sao cần kiểm tra version/support và không phụ thuộc output fields cố định?

### Bài 19 — Replication lag

Một secondary lag 20s. Những metrics nào giúp phân biệt CPU/disk/network/oplog?

### Bài 20 — Oplog window

Secondary mất kết nối 12 giờ, oplog window 8 giờ. Có rủi ro gì?

### Bài 21 — Election timeline

Viết timeline từ heartbeat failure đến app retries, recovery.

### Bài 22 — Hot shard

Một shard CPU 90%, shard khác 20%. Tại sao average không đủ?

### Bài 23 — Connection storm

20 app pods max pool=100. Vì sao không kết luận luôn có 2000 active connections?

### Bài 24 — Java metrics

Gắn CommandListener không log raw commands. Cần thêm pool checkout metric nào?

### Bài 25 — Query regression

Sau deploy, examined/returned tăng 100×. Lập bốn giả thuyết/kiểm chứng.

### Bài 26 — Auth failures

Sau rotation, chỉ 20% pods lỗi. Kiểm tra secret versions, authSource, TLS và pools.

### Bài 27 — Incident evidence

Viết timeline UTC và phân biệt observation, hypothesis, test result.

### Bài 28 — Alert routing

Thiết kế rules P1 primary unavailable, P2 replication lag và P3 disk growth.

### Bài 29 — Privacy

Một profiler entry chứa email. Những fields nào nên redacted khi chia sẻ?

### Bài 30 — Postmortem

Viết RCA có impact, timeline, trigger, contributing factors, mitigation và action owners.

### Bài 31 — Lab query/index

Chạy explain trước/sau compound index trên `observability_lab.orders`. Vì sao với bốn documents MongoDB vẫn có thể chọn COLLSCAN?

### Bài 32 — Thiết kế hệ thống hoàn chỉnh

Thiết kế observability cho Atlas sharded cluster với Java API:

- API SLI/SLO.
- Query latency/shape baselines.
- Connections/pool metrics.
- Per-shard CPU/disk/cache.
- Replication lag/elections/oplog window.
- Atlas Alerts/Profiler.
- No-data detection và alert routing.
- Runbook P1.
- Privacy controls.
- Postmortem và threshold review.

## 43. Checklist production

### Dữ liệu nền và metrics

- [ ] Có SLI/SLO ở mức ứng dụng.
- [ ] Golden signals được instrument.
- [ ] Có query shape/namespace metrics.
- [ ] Có per-node/per-shard views.
- [ ] Baseline theo workload, time-of-week.
- [ ] Exclude hoặc đánh dấu incidents/maintenance.
- [ ] Cập nhật baseline sau release/tier changes.
- [ ] Counters được chuyển thành rates đúng.
- [ ] Percentile có minimum sample count.
- [ ] Metric labels không chứa PII/cardinality quá cao.

### Cảnh báo

- [ ] Static/dynamic thresholds có justification.
- [ ] Có duration/hysteresis.
- [ ] Có no-data/exporter-health alerts.
- [ ] Có user-facing SLO burn-rate alerts.
- [ ] Alert có owner/severity/escalation.
- [ ] Có runbook/dashboard link.
- [ ] Có ACK và deduplication.
- [ ] Có test route và review false positives.
- [ ] Không suppress critical alerts vô thời hạn.
- [ ] Changes về threshold có approval.

### MongoDB

- [ ] Theo dõi PRIMARY availability/elections.
- [ ] Secondary lag và oplog window.
- [ ] Connections và pool behavior.
- [ ] WiredTiger cache, eviction, disk latency.
- [ ] Query plans và scanned/returned ratio.
- [ ] Atlas tier/feature support được xác minh.
- [ ] Database profiler bật có kiểm soát.
- [ ] $queryStats được dùng với version caveats.
- [ ] Có sharded imbalance insights khi cần.
- [ ] Có backup freshness/data safety alerts.

### Incident response

- [ ] Có incident command/roles.
- [ ] Ghi timeline UTC.
- [ ] Evidence được redacted.
- [ ] Mitigate trước khi chờ full RCA.
- [ ] Có rollback/approval cho production changes.
- [ ] Không tự động killOp/reconfig bừa bãi.
- [ ] Có recovery acceptance criteria.
- [ ] Có postmortem không đổ lỗi.
- [ ] Action items có owner và hạn.
- [ ] Có diễn tập query, disk, replication và network incidents.

## 44. Tổng kết

Một quy trình MongoDB observability đáng tin cậy gồm ba vòng lặp:

1. **Biết bình thường là gì:** lưu baseline theo service, query shape, thời gian, node và workload; đo latency, traffic, errors, saturation, replication và recovery readiness.
2. **Cảnh báo đúng:** chọn static/dynamic thresholds, SLO/error-budget, duration/hysteresis, no-data detection và severity dựa trên user impact; mỗi alert có owner và runbook.
3. **Điều tra và cải tiến:** xác định ảnh hưởng, ghi timeline, đối chiếu Atlas metrics, `serverStatus`, `rs.status`, `$currentOp`, Query Profiler, `explain` và driver metrics. Sau mitigation, xác minh SLO rồi viết RCA/action items.

Mục tiêu không phải có nhiều alerts nhất, mà là **phát hiện đúng sự cố trước khi thiệt hại lớn, tránh báo động giả và cho người trực đủ dữ kiện để hành động an toàn**.

## Tài liệu tham khảo chính thức

- [MongoDB Atlas — Configure and Resolve Alerts](https://www.mongodb.com/docs/atlas/alerts/)
- [MongoDB Atlas — Alert Basics](https://www.mongodb.com/docs/atlas/alert-basics/)
- [MongoDB Atlas Architecture — Monitoring and Alerts](https://www.mongodb.com/docs/atlas/architecture/current/monitoring-alerts/)
- [MongoDB Atlas — Monitor Real-Time Performance](https://www.mongodb.com/docs/atlas/real-time-performance-panel/)
- [MongoDB Atlas — Query Profiler](https://www.mongodb.com/docs/atlas/tutorial/query-profiler/)
- [MongoDB Atlas — Analyze Slow Queries](https://www.mongodb.com/docs/atlas/analyze-slow-queries/)
- [MongoDB Manual — serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverstatus/)
- [MongoDB Manual — Monitor Slow Queries with $currentOp](https://www.mongodb.com/docs/manual/tutorial/monitor-slow-queries/)
- [MongoDB Manual — Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB Manual — $queryStats](https://www.mongodb.com/docs/manual/reference/operator/aggregation/querystats/)
- [MongoDB Manual — Troubleshoot Replication Lag](https://www.mongodb.com/docs/manual/troubleshooting/replication-lag/)
- [MongoDB Manual — rs.printReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/rs.printreplicationinfo/)
- [MongoDB Manual — Replication Fundamentals](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/)
