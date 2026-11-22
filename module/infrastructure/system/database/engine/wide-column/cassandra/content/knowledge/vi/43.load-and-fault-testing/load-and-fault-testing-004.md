# Độ trễ p50/p95/p99, thông lượng và lượng tài nguyên khi đo tải Apache Cassandra

## 1. Mục tiêu và bối cảnh

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**: ứng dụng truy cập dữ liệu thông qua partition key, token, coordinator, replica và **consistency level (CL)**. Một truy vấn CQL có thể bị chi phối bởi CPU/GC của coordinator, network giữa các datacenter, disk I/O của replica, số lượng SSTable/tombstone, compaction, repair và số request từ Java Driver.

Trong chương **Đo tải và lỗi phân tán** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, bài này tập trung trả lời câu hỏi: **“Hệ thống xử lý được bao nhiêu công việc, mất bao lâu ở phần đuôi phân bố và tiêu thụ bao nhiêu tài nguyên để đạt kết quả ấy?”**

Sau bài học, người học có thể:

1. Định nghĩa và đọc **p50, p95, p99** của độ trễ thay vì chỉ xem trung bình.
2. Phân biệt **offered load, completed throughput, successful throughput, attempts và logical operations**.
3. Hiểu tương quan giữa **arrival rate, service rate, concurrency, queueing và tài nguyên**.
4. Giải thích **coordinated omission**, response-time histogram, thời gian warm-up và sai lệch do cache.
5. Xây dựng kế hoạch đo tải với query patterns thực tế: read/write/mixed, partition key, RF/CL và token distribution.
6. Đo và đối chiếu **client/driver latency** với coordinator/replica metrics, disk I/O, CPU, GC, network, compaction và storage.
7. Phân tích hiệu ứng **hot partition, wide partition, tombstone, page size, LWT, repair và node outage**.
8. Thiết lập **pass/fail criteria** theo SLO và khuyến nghị giới hạn tải với headroom.
9. Viết Java Driver 4.x instrumentation và hiểu cách dùng histogram/Prometheus.
10. Thực hành các runbook điều tra khi p99 cao, throughput giảm hoặc tài nguyên bị bão hòa.

**Phạm vi:** Các con số trong bài chỉ là **ví dụ tính toán/thiết kế thí nghiệm**, không phải benchmark chuẩn của Cassandra. Không có một giá trị “Cassandra đạt X QPS” đúng cho mọi schema, phần cứng, RF, CL và workload. Những lệnh tạo tải chỉ được chạy trên **cluster lab/staging được ủy quyền**, không trên production hoặc hệ thống có dữ liệu không thể mất.

## 2. Một request đi qua những đâu?

~~~mermaid
flowchart LR
    A["Client / Load generator"] --> B["Java Driver pool"]
    B --> C["Coordinator"]
    C --> D["Replica 1"]
    C --> E["Replica 2"]
    C --> F["Replica 3"]
    D --> C
    E --> C
    F --> C
    C --> B
    B --> A
    G["Compaction / repair / streaming"] -. "I/O + CPU" .-> D
    G -. "I/O + CPU" .-> E
    G -. "I/O + CPU" .-> F
~~~

Độ trễ mà **người gọi** nhìn thấy có thể bao gồm:

- Chờ trong gateway/API service và admission control.
- Chờ driver có connection/in-flight capacity.
- Gửi request qua network đến coordinator.
- Coordinator chọn replica và thực hiện read/write theo CL.
- Replica đọc memtable/SSTable, xử lý tombstone, commit log, cache hoặc compaction contention.
- Replica gửi phản hồi; coordinator hoàn tất, trả về driver.
- Driver decode/mapping và ứng dụng xây dựng response.

Nếu đo chỉ một phần đường đi, phải **đặt tên phạm vi**. Ví dụ `driver.executeAsync` latency không bao gồm thời gian HTTP request đã xếp hàng trước khi ứng dụng gọi driver; server-side read latency không bao gồm thời gian mapping Java ở API.

### 2.1. Bốn lớp thời gian cần tách

| Loại thời gian | Đo từ đâu đến đâu? | Người sử dụng chỉ số |
|---|---|---|
| **End-to-end API latency** | Caller gửi đến khi nhận response/stream complete | Product SLO, người dùng |
| **Java/Driver request latency** | Submit statement đến success/error ở client | Application/DB team |
| **Coordinator operation latency** | Node điều phối xử lý request theo metrics server | Cassandra operator |
| **Replica/storage/queue latency** | Read/write/flush/commitlog/compaction ở từng node | Tìm bottleneck |

**Không được cộng trực tiếp p99 của từng lớp** để suy p99 end-to-end: các percentile có thể đến từ **những request khác nhau**, và các tầng có concurrency/overlap. Cần distributed tracing hoặc histogram đúng từng lớp nếu muốn phân tích chi tiết.

## 3. Độ trễ p50, p95, p99 là gì?

### 3.1. Định nghĩa

Một **percentile** là ngưỡng trên phân bố giá trị:

- **p50**: khoảng 50% mẫu có độ trễ **nhỏ hơn hoặc bằng** giá trị này.
- **p95**: khoảng 95% mẫu nhỏ hơn hoặc bằng; 5% còn lại có thể chậm hơn.
- **p99**: khoảng 99% mẫu nhỏ hơn hoặc bằng; 1% còn lại có thể chậm hơn.
- **p99.9**: phản ánh phần đuôi sâu hơn; cần số lượng mẫu lớn hơn để ổn định.

Percentile phụ thuộc **cách tính**: nearest-rank, interpolation, histogram bucket approximation hoặc t-digest/HDR histogram. Các công cụ có thể cho kết quả gần nhưng không hoàn toàn trùng, đặc biệt khi số mẫu ít. Ghi rõ phương pháp/khoảng đo.

### 3.2. Phân bố minh họa 1.000 request

Giả sử phân bố thời gian phản hồi đã sắp tăng dần:

| Nhóm độ trễ | Số request | Vị trí trong dãy 1.000 |
|---|---:|---|
| 10 ms | 900 | 1–900 |
| 40 ms | 50 | 901–950 |
| 180 ms | 40 | 951–990 |
| 900 ms | 9 | 991–999 |
| 4.000 ms | 1 | 1.000 |

Dùng **nearest-rank** (vị trí `ceil(p × N)`, đánh số từ 1):

- p50 = vị trí 500 → **10 ms**.
- p95 = vị trí 950 → **40 ms**.
- p99 = vị trí 990 → **180 ms**.
- p99.9 = vị trí 999 → **900 ms**.
- Max = **4.000 ms**.

Trung bình ở ví dụ này:

\[
\overline{t}=\frac{900(10)+50(40)+40(180)+9(900)+1(4000)}{1000}=30.3\text{ ms}.
\]

**Trung bình 30,3 ms có thể trông tốt**, nhưng 10 request trong 1.000 mất 900 ms trở lên. Với một dịch vụ gọi Cassandra nhiều lần trên đường xử lý, ảnh hưởng của tail latency càng dễ xuất hiện ở API p99.

### 3.3. Percentile không phải tỷ lệ thành công

Một hệ thống có p99 = 80 ms **trên các request thành công** nhưng 8% request timeout có thể tệ hơn hệ thống có p99 = 150 ms và 0,01% lỗi.

Khi báo cáo p99, phải ghi rõ:

- Tính trên **tất cả attempts hay chỉ success**?
- Request timeout có được đưa vào histogram không, hay tách ở counter khác?
- Bao nhiêu request và khoảng thời gian nào?
- Số liệu ở client, API hay coordinator?
- Đang đo theo **logical request**, theo **driver attempt** hay theo **một page**?
- Có loại trừ giai đoạn warm-up hoặc failover không, và vì sao?

**Cấm kết luận “p99 đạt SLO” chỉ từ histogram success trong khi error rate tăng**.

### 3.4. Cửa sổ đo và tính đại diện

Nếu window có 50 request thì 1% là **nửa request**, nên p99 có thể nhảy thất thường gần max. Với N=10.000, phần 1% đuôi chứa khoảng 100 quan sát; đáng tin hơn nhưng vẫn phải xem biến động, phân bố traffic và chế độ lỗi.

Không gộp p99 tuần qua với p99 một phút bằng trung bình. Cần lưu **histogram hoặc raw samples** để tổng hợp chính xác trên window mới.

## 4. p50 “đẹp” nhưng p99 xấu: điều này đang nói gì?

Hãy hình dung độ trễ theo tải:

| Offered load (ops/s) | p50 (ms) | p95 (ms) | p99 (ms) |
|---:|---:|---:|---:|
| 500 | 8 | 15 | 24 |
| 1.000 | 9 | 20 | 35 |
| 1.500 | 10 | 40 | 120 |
| 2.000 | 12 | 100 | 600 |
| 2.500 | 15 | 300 | 1.900 |

Số liệu biểu đồ là **giả định** để thể hiện hiện tượng queueing. Khi workload tiến gần bão hòa, phần lớn request vẫn nhanh nhưng một phần nhỏ kẹt trong queue, chờ disk hoặc bị GC pause.

Các khả năng thường gặp ở Cassandra:

- **Hot partition:** một nhóm replica phải phục vụ phần lớn truy vấn.
- **Wide partition/nhiều tombstone:** một số key đọc đắt hơn phần còn lại.
- **Disk hoặc compaction:** một node có tail latency lớn trong lúc flush/compaction.
- **GC pause/CPU saturation:** một số request chờ theo đợt.
- **Network retransmission/cross-DC:** chỉ một tập request đi đường chậm.
- **Retry/speculative executions:** tail latency có thể được che cho một số request, nhưng tải backend tăng.
- **Driver pool saturation:** request xếp hàng, không nhất thiết server read latency cao.
- **Unbalanced token distribution hoặc RF/CL:** một số coordinator/replica được dùng quá mức.

**p99 tăng là tín hiệu điều tra, không tự chỉ ra nguyên nhân.** Muốn biết nguyên nhân cần đối chiếu thời điểm với per-node latency, pending queues, disk, GC, token/partition distribution và driver telemetry.

## 5. Histogram và cách tính p99 cho dashboard

### 5.1. Vì sao histogram hữu ích hơn chỉ lưu percentile?

Nếu mỗi node xuất riêng “p99=150 ms”, “p99=400 ms”, ta **không thể lấy trung bình** hai số để ra p99 toàn cluster. Số lượng request, phân bố và overlap khác nhau.

Một histogram giữ **số mẫu trong các khoảng độ trễ**; các bucket counts có thể cộng qua node/instance cùng định nghĩa để tính percentile gần đúng cho nhiều khoảng thời gian.

Ví dụ buckets cộng dồn của một query:

| Upper bound | Số mẫu ≤ ngưỡng | Ý nghĩa |
|---|---:|---|
| 10 ms | 700 | 70% request ≤ 10 ms |
| 25 ms | 900 | 90% request ≤ 25 ms |
| 50 ms | 950 | 95% request ≤ 50 ms |
| 100 ms | 970 | 97% request ≤ 100 ms |
| 250 ms | 992 | 99,2% request ≤ 250 ms |
| +Inf | 1.000 | Tổng số mẫu |

Ở ví dụ này, p99 nằm trong khoảng **100–250 ms**, nhưng histogram chỉ biết bucket nên ước lượng có sai số phụ thuộc độ rộng bucket và phương pháp interpolation. Không tuyên bố p99 chính xác tới 1 ms nếu bucket quanh p99 rộng 150 ms.

### 5.2. PromQL minh họa với histogram cổ điển

Giả sử ứng dụng export histogram `cassandra_client_request_duration_seconds_bucket` với nhãn `query_template` và `outcome`:

~~~promql
histogram_quantile(
  0.99,
  sum by (le, query_template) (
    rate(
      cassandra_client_request_duration_seconds_bucket{
        outcome="success"
      }[5m]
    )
  )
)
~~~

Điều cần nhớ:

- Đơn vị `_seconds` là **giây**, không phải milliseconds.
- `le` phải được giữ khi tổng hợp classic histogram.
- Đây là p99 **của success**, phải đi cùng tỷ lệ error/timeout.
- Sử dụng `rate(...[5m])` trên **counter buckets** chứ không lấy trung bình p99 exported từ mỗi instance.
- Metric name/labels là **ví dụ do ứng dụng tự định nghĩa**, không khẳng định driver xuất sẵn với tên này.
- Nếu dùng **Prometheus native histograms**, cú pháp và cách aggregate khác; đối chiếu phiên bản collector/Prometheus thực tế.
- Query template ID có cardinality hữu hạn; **không** dùng raw CQL/bind values/partition key làm label.

### 5.3. Chọn buckets dựa trên SLO

Nếu SLO yêu cầu p99 ≤ 200 ms, buckets nên đủ dày xung quanh **0,1–0,3 giây** để phân biệt 180 và 260 ms. Một histogram chỉ có buckets 0,1 s và 1 s không phù hợp đo chính xác ngưỡng 200 ms.

Histogram lưu gần đúng; raw observations/HDRHistogram có thể giúp phân tích nội bộ nếu cấu hình sampling và retention phù hợp. Không lưu log một dòng cho mọi request high-QPS để tính percentiles nếu log pipeline không chịu nổi.

### 5.4. SLO latency phải đi cùng availability

Ví dụ tiêu chí:

- **≥ 99,9%** logical reads thành công trong window, tùy business requirement.
- **p99 latency ≤ 200 ms** trên logical reads thành công.
- **Timeout ≤ 0,1%** và không có data correctness violation.
- **CPU/disk headroom** đủ cho node down hoặc traffic burst theo capacity plan.

Con số trên là **mẫu acceptance criteria**, không phải baseline được Cassandra bảo đảm. Một hệ thống có thể đạt p99 nếu bỏ/timeout mọi request chậm; cần giới hạn cả error rate để tránh “tối ưu số liệu” sai.

## 6. Thông lượng: offered load và achieved throughput khác nhau

### 6.1. Các đơn vị cần ghi rõ

| Chỉ số | Đơn vị | Cách hiểu |
|---|---|---|
| Offered request rate | logical requests/s | Số yêu cầu load generator muốn khởi phát |
| Started attempts | attempts/s | Số lần client/driver thực sự bắt đầu |
| Completed throughput | completed requests/s | Kể cả success và error đã kết thúc |
| Successful throughput | successful logical ops/s | Số thao tác thành công theo tiêu chí client |
| Failed/timeout rate | errors/s và % | Số thao tác không hoàn tất đúng |
| Read/write requests | operations/s | Phải phân biệt read, write, LWT và batches |
| Rows returned | rows/s | Một SELECT có thể trả nhiều rows/pages |
| Bytes in/out | MiB/s hoặc MB/s | Dung lượng network/serialization |
| SSTable read/write bytes | MiB/s | I/O thực tại node, không bằng payload client |
| Background throughput | compaction/streaming/repair MiB/s | Tải tranh tài nguyên với CQL |

**QPS không phải ops/s theo nghĩa duy nhất:** một query đọc 1 row khác rất xa một query đọc 10.000 row hoặc một range scan chạm nhiều SSTable. Khi so sánh benchmark, phải ghi **query mix, rows/query, bytes/query, partition distribution và CL**.

### 6.2. Offered > completed: queue có đang tăng?

Giả sử load generator muốn gửi **3.000 logical requests/s**, Cassandra chỉ hoàn thành **2.300/s**:

~~~text
Offered load:           3000 requests/s
Completed throughput:   2300 requests/s
Difference:              700 requests/s

Nếu arrival rate giữ nguyên và không có drop/load shedding,
backlog có thể tăng khoảng 700 request mỗi giây.
~~~

Nếu hệ thống có admission control/drop, chênh lệch không nhất thiết trở thành queue trong Cassandra; một số request có thể bị từ chối ở tầng trước. Hãy xác định **điểm xếp hàng hoặc rơi request**, không chỉ tính một hiệu số.

Khi tăng offered load mà achieved throughput gần như không tăng, nhưng latency/p99 và errors tiếp tục tăng, đó là dấu hiệu **đã đến hoặc vượt knee of the curve**.

### 6.3. Logical requests khác driver attempts

Một logical read từ HTTP có thể được thử nhiều lần do driver retry policy, speculative execution hoặc application/gateway retry:

~~~text
1000 HTTP logical reads
  - 900 thành công ngay attempt đầu
  - 100 cần thêm một attempt

Logical reads:      1000
Driver attempts:    1100 (minh họa)
Extra backend load: 10% attempts
~~~

Với một trường hợp có retry theo nhiều tầng, số attempts có thể lớn hơn nhiều. Nếu chỉ xem **throughput logical success**, cluster load tăng vì retry có thể bị bỏ qua trong báo cáo.

**Đối với write timeout, không retry mù**: kết quả mutation có thể không chắc chắn, đặc biệt counter, LWT, TTL hoặc side effect ngoài Cassandra.

## 7. RF, CL và throughput vật lý của replica

### 7.1. Viết một logical row có thể gây nhiều replica writes

Với `NetworkTopologyStrategy`, RF=3 ở một DC, một mutation logical thường được replicate đến ba bản sao theo placement:

~~~text
Client write: 1 logical mutation
Coordinator: điều phối request
Replica set: A, B, C

Bản sao được cập nhật hướng tới RF=3.
CL=ONE: có thể trả success khi một ACK phù hợp.
CL=LOCAL_QUORUM: quorum 2/3 ACK.
CL=ALL: phải đáp ứng các điều kiện của mọi replica liên quan.
~~~

**CL không bằng số bản sao cuối cùng tồn tại** và số ACK cũng không chính xác bằng số I/O. Replica có commit log/memtable/flush/compaction; coordinator/network có chi phí riêng. Một write RF=3 có thể tạo chi phí storage **nhiều hơn một bản ghi logical** trước khi tính compaction, hints và repairs.

### 7.2. Ước lượng tải bản sao phải ghi giả định

Nếu 2.000 writes/s được replicate RF=3, số **replica mutation deliveries mục tiêu** xấp xỉ 6.000/s trong điều kiện ổn định, **không phải** tuyên bố mỗi node đều nhận 6.000/s hay IOPS = 6.000. Phân bố token, DC/rack, coordinator, batches, compaction và mạng quyết định chi phí thật.

Một phép tính capacity sơ bộ:

\[
\text{Replica write target rate}
\approx \text{logical writes/s}\times RF.
\]

Cần bổ sung:

- Per-node token ownership và key distribution.
- RF theo **từng DC** với multi-DC.
- Băng thông cross-DC, hints và repair.
- Số bytes/cell, commit-log sync, compaction/write amplification.
- CL, consistency availability và số node có thể hỏng.
- Độ trễ p95/p99 của **node xấu nhất**, không chỉ trung bình cluster.

### 7.3. RF/CL khác nhau là hai bài benchmark khác nhau

Không so trực tiếp “CL=ONE đạt 50k ops/s” với “LOCAL_QUORUM đạt 30k ops/s” rồi kết luận chỉ cần hạ CL để được nhanh hơn. CL là **đòi hỏi tính nhất quán và khả dụng** của nghiệp vụ.

Báo cáo nên ghi một bảng:

| Biến | Ví dụ cấu hình |
|---|---|
| Keyspace RF | `dc1:3`, `dc2:3` (nếu có) |
| Read CL | `LOCAL_QUORUM` |
| Write CL | `LOCAL_QUORUM` |
| Serial CL | Chỉ cho LWT khi dùng, theo thiết kế |
| Driver local DC | `dc1` |
| Request timeout | Giá trị có hiệu lực, ghi rõ driver/profile |
| Retry/speculative policy | Tên, số attempts, điều kiện idempotent |
| Partition distribution | Uniform, Zipfian hoặc hotspot profile |
| Read/write ratio | Ví dụ 80/20, đo trên logical requests |
| Payload | Rows/partition, bytes/row, TTL/tombstone mix |

Nếu không mô tả những biến này, hai biểu đồ QPS khó so sánh về mặt kỹ thuật.

## 8. Little's Law, concurrency và queueing

### 8.1. Quan hệ cơ bản

Ở trạng thái ổn định, trong phạm vi một hệ thống/queue có dòng việc được xác định rõ, **Little's Law**:

\[
L = \lambda W.
\]

Trong đó:

- `L`: số công việc trung bình **đang ở trong hệ thống**.
- `λ`: tốc độ hoàn thành/arrival ổn định (`requests/s`).
- `W`: thời gian **trung bình** một công việc ở trong hệ thống (`seconds`).

Ví dụ 2.500 completed requests/s với **latency trung bình** 40 ms:

\[
L=2500\times 0.040=100\text{ in-flight requests trung bình}.
\]

**Không thay `W` bằng p99** trong công thức này để suy một concurrency trung bình chính xác; Little's Law liên hệ các **giá trị trung bình**.

### 8.2. Tại sao concurrency cao không bảo đảm throughput cao?

Ở mức tải thấp, tăng concurrency có thể giúp tận dụng server. Nhưng khi CPU/disk hoặc hot replica chạm giới hạn, request mới chỉ xếp hàng lâu hơn. Khi đó:

- Offered load tăng.
- Completed throughput đi ngang.
- Mean/p95/p99 latency tăng.
- Timeout/retry và queue length tăng.
- Throughput **thành công** có thể giảm dù attempts/s tăng.

Đây là đường cong bão hòa; cần đo điểm bắt đầu cong mạnh (**knee**), không chọn mức tải cao nhất từng thấy trong một đợt burst ngắn.

### 8.3. Phân biệt service time và queue wait

~~~text
End-to-end duration =
    queue wait
  + work/service duration
  + network/client overhead
  + retry/backoff overhead (nếu có)
~~~

Khi queue wait là phần lớn latency, tăng timeout có thể chỉ giữ thêm request trong hàng đợi. Giải pháp có thể là giảm tải, rate limit, partition rebucketing, tối ưu read path hoặc tăng capacity theo bottleneck thật.

## 9. Phương pháp phát tải: open-loop và closed-loop

### 9.1. Closed-loop

Một worker gửi request, **chờ xong** rồi mới gửi request kế:

~~~text
worker_1: send -> wait -> response -> send -> wait
worker_2: send -> wait -> response -> send -> wait
...
~~~

Ưu điểm: dễ giới hạn concurrent requests, hữu ích đo behavior của một pool cố định.

Rủi ro: khi Cassandra chậm, workers gửi ít request hơn, **offered load tự giảm**. Benchmark có thể báo throughput thấp và p99 trông “không quá xấu” vì không tạo đúng arrival rate lúc hệ thống bão hòa.

### 9.2. Open-loop

Generator lên lịch arrival theo tốc độ mục tiêu, **không đợi request trước hoàn thành**:

~~~text
Scheduled arrivals at:
0 ms, 1 ms, 2 ms, 3 ms, ...

Các request đã gửi có thể còn đang xử lý,
trong khi arrival mới vẫn được đưa vào theo lịch.
~~~

Ưu điểm: có thể kiểm tra service khi **nguồn traffic cố định** bất chấp latency tăng, gần mô hình một số hệ thống thực.

Rủi ro: nếu không có cap/abort, số in-flight/queue tăng rất nhanh và có thể làm cluster lab sập. Cần giới hạn **max outstanding requests**, generator memory và stop conditions.

### 9.3. Coordinated omission

**Coordinated omission** xảy ra khi hệ đo **không ghi nhận hoặc không tạo các request lẽ ra đến** trong lúc hệ thống đang chậm. Ví dụ:

~~~text
Target arrival: 1000 requests/s
Server pause: 2 seconds

Closed-loop worker:
  request A kẹt 2 giây
  không phát nhiều request đáng lẽ đến trong 2 giây ấy
  histogram chỉ thấy một số ít request chậm

Người dùng ngoài thực tế:
  nhiều request mới vẫn đến, xếp hàng/timeout
  p99 trải nghiệm có thể tệ hơn histogram benchmark.
~~~

Cách ứng phó:

- Dùng generator có hỗ trợ **scheduled arrival timestamps**.
- Ghi cả **expected schedule lag, queue wait và end-to-end latency**.
- Nếu có histogram correction cho coordinated omission, mô tả rõ cách dùng/các giả định.
- Báo cáo generator achieved/offered rate và missed/delayed arrivals.
- Không so open-loop với closed-loop như hai số liệu trực tiếp tương đương.

### 9.4. Chọn phương pháp theo production traffic

- HTTP frontend có nhiều client độc lập → cần xem arrival rate ngoài hệ thống.
- Batch job tự đợi reply trước khi đọc tiếp → closed-loop có thể gần một phần workload.
- Kafka consumer có backlog → arrival rate producer và consumption rate là hai đại lượng; queue có thể dồn ngoài Cassandra.
- Scheduled jobs/bursts → test thêm synchronized bursts, không chỉ steady load.

**Nên mô tả mô hình nguồn traffic trong báo cáo**, thay vì chỉ ghi “100 threads”.

## 10. Chuẩn bị workload đại diện trước khi benchmark

### 10.1. Dữ liệu mẫu phải giống thực tế

Cassandra performance phụ thuộc mạnh vào **data model và distribution**:

| Biến workload | Hãy mô tả và kiểm tra |
|---|---|
| Partition key | Đầy đủ key hay token-range scan? |
| Partition width | Rows/partition, bytes/partition, p50/p95/p99 kích thước |
| Clustering order | Latest-first, range, số row per query |
| Read/write mix | Tỷ lệ logical requests, theo thời gian |
| TTL/DELETE | Phần trăm cells hết hạn và tombstone density |
| Compaction | Strategy, backlog, SSTables/read, disk headroom |
| Cache | Cold/warm, key cache, OS page cache |
| RF/CL | Replicas/ack requirements và DC topology |
| Consistency/failure | Node down, slow replica, retries, hints |
| Payload | Bytes/row, collection/UDT/blob, serialization |
| Concurrency | Offered RPS, threads, in-flight, per-client connections |
| Hotspot | Uniform vs Zipfian/skew, tenant/device hot keys |

Nếu chỉ test `SELECT` theo một key đã nằm trong cache, kết quả không đại diện cho production với hàng triệu partition và read/write TTL mix.

### 10.2. Query-specific schema

Ví dụ bảng đọc theo thiết bị và ngày:

~~~cql
-- Lab với datacenter dc1, số node đủ RF=3.
CREATE KEYSPACE telemetry_bench
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry_bench.readings_by_device_day (
  device_id uuid,
  event_day date,
  event_time timestamp,
  reading_value double,
  status text,
  PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Read pattern:

~~~cql
SELECT event_time, reading_value, status
FROM telemetry_bench.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT 20;
~~~

Partition key `(device_id, event_day)` cho phép định tuyến theo token khi driver suy ra đủ key. Nhưng query một partition quá rộng hoặc nhiều tombstone vẫn có thể có p99 cao.

### 10.3. Test matrix

| Kịch bản | Read/write | Data distribution | Mục đích |
|---|---|---|---|
| Baseline | 100% simple read | Uniform keys | Đo p50/p95/p99 ban đầu |
| Read/write mix | 80/20 | Uniform | Xem tranh resource |
| Hot keys | 80/20 | Zipfian/tập key nóng | Phát hiện lệch replica load |
| Wide partition | Read ranges | Partition rộng | SSTables/tombstones/page cost |
| High TTL | Mixed | TTL và expired cells | Tombstone/compaction effect |
| Write burst | 10/90 | Nhiều partitions | Commit log, memtable flush |
| LWT | Conditional | Một số hot keys | Paxos contention/tail |
| Repair/streaming | Same baseline | Background I/O | Headroom khi maintenance |
| Failure | Same baseline | Một replica/node bị loại trong lab | Latency/error/CL dưới outage |

Đối với mỗi kịch bản, phải giữ **cấu hình còn lại** gần như cố định hoặc ghi rõ thay đổi. Không so “baseline cold cache” với “after tuning warm cache” rồi gán mọi khác biệt cho tuning.

## 11. Công cụ phát tải và phạm vi an toàn

### 11.1. `cassandra-stress` không thay workload ứng dụng

`cassandra-stress` giúp thử tải bằng các phép đọc/ghi tổng hợp, thường hữu ích để khảo sát baseline. Nhưng **default schema, phân bố key và request shape** có thể rất khác Java API đang vận hành: partition widths, TTL/tombstone, clustering, RF/CL và payload.

Ví dụ **chỉ trên cluster lab được phép ghi dữ liệu**:

~~~bash
# Cú pháp minh họa phổ biến; xác minh help theo version.
# Không trỏ generator này vào production.
cassandra-stress write n=200000 -rate threads=32 -node 127.0.0.1
~~~

Công cụ có thể tự tạo hoặc ghi keyspace/table dành cho stress; không dùng nhầm một keyspace đang phục vụ dữ liệu thật. Tùy release, cách truyền auth/TLS, CL, profile hoặc duration thay đổi. **Không chạy load test trong bước viết bài này**.

Nếu mục tiêu là throughput của `SELECT` theo `(device_id, event_day)`, hãy dùng custom profile hoặc generator Java thực thi **prepared CQL thật**, đúng payload, partition distribution, read/write ratio và consistency.

### 11.2. Guardrails bắt buộc trước khi phát tải

~~~text
[ ] Đã xác nhận cluster LAB/STAGING, địa chỉ node và chủ sở hữu.
[ ] Dùng data/keyspace test và quyền RBAC giới hạn.
[ ] Có start/stop window, người giám sát và rollback plan.
[ ] Snapshot/backup nếu test có tác động thay dữ liệu cần giữ.
[ ] Có max offered QPS, max outstanding, max bytes/s.
[ ] Có ngưỡng dừng theo p99, errors, disk, heap, queues.
[ ] Có thể dừng load generator và xác minh không còn requests.
[ ] Có metrics từ generator, Java driver và mọi Cassandra node.
[ ] Không làm fault injection trên production.
~~~

**Một benchmark không đáng giá nếu nó gây sự cố ở hệ thống khác.** Không tăng tải đến khi disk full chỉ vì muốn thấy con số “max throughput”.

### 11.3. Khi cần custom profile?

| Yêu cầu | Vì sao generic stress chưa đủ? |
|---|---|
| Prepared query và codec của ứng dụng | Default CQL không khớp |
| Partition distribution Zipfian/hot keys | Uniform keys có thể che hotspot |
| TTL/tombstone, wide partitions | Chí phí read path khác |
| CL/RF và multi-DC routing | Inter-node traffic/ACK khác |
| Java retry, timeout, pooling | Generic tool không phản ánh stack |
| API end-to-end p99 | Cassandra stress không đo HTTP/business mapping |
| Open-loop arrival và coordinated omission | Phải biết scheduler/mode của generator |

Dùng custom generator phải đo **CPU, GC, NIC và heap của chính generator**. Nếu generator bị bão hòa trước cluster, kết quả “Cassandra chỉ đạt X ops/s” không đáng tin.

## 12. Quy trình benchmark có thể lặp lại

### 12.1. Năm pha

~~~mermaid
flowchart LR
    A["Preflight + seed"] --> B["Warm-up"]
    B --> C["Ramp offered load"]
    C --> D["Steady-state windows"]
    D --> E["Cool-down + recovery"]
    E --> F["Report + decision"]
~~~

**Preflight:** ghi server/driver/JDK versions, node count, instance type, RF/CL, topology, compaction strategy, storage, schema, dataset, read/write mix, profile generator và timeout/retry.

**Seed:** nạp dữ liệu đủ lớn, giống partition/row/TTL thực tế. Đo disk growth, SSTables, compaction, network để tránh seed trở thành nguồn biến động không rõ.

**Warm-up:** JIT, connection pools, OS page cache và key cache có thời gian ổn định. Nếu test **cold cache**, phải thiết kế cold-start riêng, không ngầm gộp warm-up vào kết quả.

**Ramp:** tăng offered load theo các mức có giới hạn; giữ đủ lâu để thấy sự thay đổi p99/compaction/queue, không tăng đột ngột đến disk saturation.

**Steady-state:** ghi nhiều measurement windows, xác minh backlog không tăng liên tục; không chỉ trích ra một con số đẹp nhất.

**Cool-down:** dừng generator, quan sát pending queues, compaction backlog, disk/GC và lỗi có trở về baseline không. Recovery time cũng là một kết quả quan trọng.

### 12.2. Một lịch minh họa — không phải khuyến nghị chung

| Pha | Khoảng thời gian | Offered load minh họa | Điều kiện quan sát |
|---|---|---:|---|
| Seed | Phụ thuộc dataset | Giới hạn writes | Data/disk/compaction |
| Warm-up | 5 phút | 200 ops/s | Cache/pools/JIT |
| Ramp A | 10 phút | 500 ops/s | p50/p95/p99 |
| Ramp B | 10 phút | 1.000 ops/s | Node worst-case |
| Ramp C | 10 phút | 1.500 ops/s | Queue/retries |
| Ramp D | 10 phút | 2.000 ops/s | Dừng nếu vượt guardrails |
| Recovery | Đến ổn định | 0 traffic test | Pending/disk/error |

Các số chỉ nhằm minh họa phương pháp. Cluster nhỏ có thể cần rất thấp, cluster lớn cao hơn. **Không suy năng lực sản phẩm từ ví dụ**.

### 12.3. Làm sao biết đã steady?

- Offered và completed rates ít biến động qua nhiều windows.
- In-flight và queue depth **không tăng dài hạn**.
- Compaction/flush/streaming backlog không tiếp tục tích lũy ngoài dự kiến.
- Error/timeout/retry rate ổn định và trong budget.
- Disk latency, GC, CPU không còn drift do seed/startup.
- Generator không tự queue/drop request vượt max outstanding.
- Không có repair, node restart hoặc batch job không báo trước.

Một đợt benchmark dài 30 giây **không đủ** xác nhận cluster chịu được cùng tải suốt nhiều giờ khi write amplification/compaction bắt đầu tác động.

## 13. Đo request latency trong Java Driver 4.x

### 13.1. `System.nanoTime()` và asynchronous completion

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public final class DriverLatencyProbe {
    private final CqlSession session;
    private final LongAdder success = new LongAdder();
    private final LongAdder failed = new LongAdder();

    public DriverLatencyProbe(CqlSession session) {
        this.session = session;
    }

    public CompletionStage<AsyncResultSet> execute(
            BoundStatement statement) {
        long started = System.nanoTime();

        try {
            CompletionStage<AsyncResultSet> stage =
                session.executeAsync(statement);

            return stage.whenComplete((result, error) -> {
                long elapsed = System.nanoTime() - started;
                observe(elapsed, TimeUnit.NANOSECONDS);

                if (error == null) {
                    success.increment();
                } else {
                    failed.increment();
                    recordError(error);
                }
            });
        } catch (RuntimeException error) {
            observe(System.nanoTime() - started,
                    TimeUnit.NANOSECONDS);
            failed.increment();
            recordError(error);
            throw error;
        }
    }

    private void observe(long value, TimeUnit unit) {
        // Đưa duration vào histogram của Micrometer/HDRHistogram.
        // Không log stdout cho từng request.
    }

    private void recordError(Throwable error) {
        // Gom theo loại lỗi/query template hữu hạn.
    }
}
~~~

`System.nanoTime()` là đồng hồ đơn điệu để đo **elapsed duration trong cùng process**. Không lấy `System.currentTimeMillis()` hoặc timestamps trên **hai máy khác nhau** trừ nhau rồi cho đó là latency chuẩn khi clock chưa được đồng bộ.

Mẫu trên đo thời gian **`executeAsync` hoàn tất response đầu tiên**, không nhất thiết đo thời gian tiêu thụ **mọi page** của một truy vấn dài. Nếu ứng dụng trả 10.000 row nhiều page, cần thêm chỉ số `time_to_last_row` và `bytes_processed`.

### 13.2. Metric tags và histogram

Với Micrometer:

~~~java
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

public final class LatencyRecorder {
    private final Timer timer;

    public LatencyRecorder(Timer timer) {
        this.timer = timer;
    }

    public void recordNanos(long nanos) {
        timer.record(nanos, TimeUnit.NANOSECONDS);
    }
}
~~~

Tạo timer/histogram với tags **low cardinality**: `query_template`, `operation`, `outcome`, `dc`. Không dùng `tenant_id`, device UUID, raw CQL, routing key/token hoặc exception message làm metric labels.

Tên metric/exporter và bucket configuration phụ thuộc Micrometer/Prometheus registry/driver version; phải **xác minh cấu hình thực tế**, không giả định driver tự phát một histogram có tên do ví dụ đặt.

### 13.3. Một logical call có thể chứa nhiều attempts

Driver có thể retry hoặc dùng speculative execution tùy policy. Wrapper đo một lần gọi `executeAsync` từ ứng dụng, **không cho biết** đã thử bao nhiêu coordinator, replica hay network attempts.

Nên thu thêm:

- Driver retry/speculative execution count nếu metric có hỗ trợ.
- `AllNodesFailedException.getAllErrors()` theo candidate coordinator khi lỗi.
- Query template, CL, request timeout và local DC.
- Logical success/failed/timeout và achieved attempts rate tách biệt.

**Không log mọi stack trace vào hot path của benchmark**: logging synchronous có thể làm p99 xấu do chính instrumentation.

## 14. Asynchronous ≠ unlimited concurrency

### 14.1. Anti-pattern tạo vô hạn requests

~~~java
// ANTI-PATTERN: không giữ futures hoặc kiểm soát outstanding.
for (UUID id : millionsOfIds) {
    session.executeAsync(buildStatement(id));
}
~~~

`executeAsync` không chặn thread gọi nhưng vẫn tạo CQL traffic, driver buffers, connection pool pressure và in-flight requests. Nếu generator tạo nhanh hơn server hoàn tất, memory/queue có thể tăng.

### 14.2. Bounded in-flight là yêu cầu tối thiểu

Một load generator đúng phải:

1. Đặt **max outstanding** theo generator/cluster.
2. Dùng arrival scheduler rõ (open-loop hoặc closed-loop).
3. Ghi thời điểm **scheduled, submitted, completed** cho mỗi operation.
4. Ghi failures/timeouts/rejections, không chỉ success.
5. Đếm số attempts do application/gateway/driver sinh thêm.
6. Dừng/giảm tải khi chạm error/disk/GC guardrails.
7. Bảo đảm generator không tự bão hòa trước Cassandra.

Ví dụ một permit trong **pseudocode**:

~~~java
Semaphore inFlight = new Semaphore(100);

if (!inFlight.tryAcquire()) {
    generatorRejected.increment();
    return; // Ghi nhận offered-but-not-submitted.
}

long submittedAt = System.nanoTime();

try {
    session.executeAsync(statement)
        .whenComplete((result, error) -> {
            try {
                observeCompletion(
                    submittedAt, System.nanoTime(), error);
            } finally {
                inFlight.release();
            }
        });
} catch (RuntimeException error) {
    inFlight.release();
    observeSubmissionFailure(error);
}
~~~

Các biến như `generatorRejected` và `observeCompletion` là thành phần instrumentation giả định. Nếu xây open-loop generator, phải lưu **intended/scheduled arrival timestamp** riêng để phát hiện schedule lag/coordinated omission.

**Generator rejection không phải Cassandra `UnavailableException`.** Một phép đo có ý nghĩa phải phân biệt “yêu cầu bị chặn ở máy phát” với “Cassandra đã nhận nhưng thất bại”.

### 14.3. Generator cũng cần metrics

- CPU, CPU throttling/steal, GC pause và heap của generator.
- Network Rx/Tx, RTT đến contact points.
- Scheduler lag, rate đã lên lịch và thực gửi.
- Outstanding requests, local queue length, client rejection.
- Retry amplification, load test operation mix.
- Số client connections và số lỗi pool/transport.

Nếu p99 tăng khi **chỉ generator** đạt 100% CPU nhưng Cassandra nodes vẫn rảnh, không nên quy lỗi đó cho replica/disk của Cassandra.

## 15. Bảng tài nguyên cần thu theo node

### 15.1. CPU, GC, heap và native memory

| Tài nguyên | Chỉ số quan sát | Vì sao ảnh hưởng tail latency |
|---|---|---|
| CPU % theo core | Busy/core saturation | Một core coordinator nóng dù average CPU vừa |
| CPU throttling/steal | Cgroup quota/VM contention | Queue và p99 tăng đột ngột |
| JVM GC pauses | Count, p95/max pause, allocation rate | Một nhóm requests chờ GC |
| Heap occupancy | Used %, promotion/old gen, allocations | GC pressure, OOM |
| Off-heap/native/direct buffers | Resident memory, direct buffers | Process có thể thiếu RAM dù heap thấp |
| OS page cache | Cache hit/miss, eviction | Read path đụng disk nhiều hơn |
| File descriptors/connections | Limits và failures | Pool/socket errors |

Không kết luận “cluster còn 60% CPU headroom” từ CPU trung bình 40%: **một core hoặc replica nóng** có thể đã bão hòa.

### 15.2. Disk và compaction

| Chỉ số | Vì sao cần |
|---|---|
| Read/write IOPS | Số I/O operations, phụ thuộc request size |
| Disk MiB/s | Byte throughput, khác IOPS |
| Device await/latency | Chỉ báo read/write tail |
| Queue depth/utilization | Backlog ở thiết bị |
| Disk free GB và % | Flush, compaction, snapshots cần headroom |
| Commitlog fsync latency | Write durability path |
| SSTables per read | Read amplification |
| Compaction pending/bytes/s | Background SSTable rewrite |
| Tombstone warnings | Nhiều expired/deleted cells phải scan |

Disk utilization cao chưa đủ kết luận bottleneck; phải xem đồng thời **latency, queue, throughput, node hotness và compaction**. HDD/SSD/NVMe và I/O size có khả năng phục vụ khác nhau.

### 15.3. Network và replica load

Đo:

- Client↔coordinator Rx/Tx bytes, RTT, retries, connection failures.
- Coordinator↔replica traffic; cross-DC bandwidth nếu có.
- TCP retransmits/packet loss, NIC utilization.
- Hints, streaming, repair traffic làm nền.
- Token ownership, per-node read/write load, hot partition.
- TLS/auth overhead khi connection churn.

Một write logical RF=3 có nhiều replica deliveries; **client payload bytes không bằng inter-node traffic**. Nhiều background jobs vẫn dùng disk/network dù `cassandra-stress` stopped.

## 16. `nodetool`, JMX và bẫy quan sát

### 16.1. Lệnh quan sát theo Cassandra version

~~~bash
# Trạng thái node, DC/rack và ownership.
nodetool status

# Stage active/pending/completed và dropped messages.
nodetool tpstats

# Running/pending compactions.
nodetool compactionstats

# Table-level storage/read/write/SSTable metrics.
nodetool tablestats telemetry_bench.readings_by_device_day

# Histograms theo table, nếu phiên bản hỗ trợ.
nodetool tablehistograms telemetry_bench readings_by_device_day

# SSTable streaming khi bootstrap/repair/rebuild.
nodetool netstats
~~~

Output, stage/metric names và options của `nodetool` có thể khác giữa Cassandra versions; kiểm tra `nodetool help` và JMX exporter mapping của hệ đang chạy. Những lệnh quan sát không thay thế thời gian chạy benchmark/delta metrics.

### 16.2. Counter tích lũy khác QPS

~~~text
Time    ReadStage Pending   Completed     READ Dropped
10:00                  80      500000                5
10:01                 980      512000               65

Delta Completed/60s = 12000/60 = 200 tasks/s
Pending +900; Dropped +60.
~~~

`Completed` là **stage task count** trên node, **không** phải số logical HTTP GET/s hay số SELECT/s toàn cluster. Nếu node restart, counter reset; không trừ hai snapshot xuyên restart.

### 16.3. `netstats` trống không chứng minh network idle

`nodetool netstats` chủ yếu báo **SSTable streaming**, không phải mọi native CQL request. Để đo CQL/load, dùng driver metrics, native transport counters, network interface bytes/s và per-node request latency.

### 16.4. Node `UN` có thể vẫn vi phạm p99

`nodetool status` báo node Up/Normal không có nghĩa:

- Disk await thấp.
- CPU/GC khỏe.
- Pending queue nhỏ.
- Request CQL đáp ứng CL đúng hạn.
- Java client ở region khác kết nối được.
- No hot partitions/tombstones.

**Availability và performance là hai chiều riêng**. Cần biết cluster có bao nhiêu replica usable theo RF/CL và các replica ấy có latency/tải ra sao.

## 17. Đọc latency, throughput và resource trên cùng một bảng

Giả sử cùng schema, cùng RF/CL, cùng dataset, cùng load generator; số liệu sau là **giả định**:

| Offered ops/s | Success ops/s | p50 | p95 | p99 | CPU node nóng nhất | Disk read await | Error % |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 500 | 498 | 8 ms | 15 ms | 24 ms | 25% | 2 ms | 0,0% |
| 1.000 | 995 | 9 ms | 20 ms | 35 ms | 41% | 4 ms | 0,1% |
| 1.500 | 1.490 | 10 ms | 40 ms | 120 ms | 62% | 9 ms | 0,2% |
| 2.000 | 1.920 | 12 ms | 100 ms | 600 ms | 83% | 24 ms | 3,0% |
| 2.500 | 1.870 | 15 ms | 300 ms | 1.900 ms | 92% | 51 ms | 14,0% |

**Giải thích:** error % được tính trên các logical requests đã hoàn tất hoặc timeout trong window quan sát; chênh giữa offered và success còn chứa backlog, in-flight lúc ranh giới window, lỗi ở generator hoặc rejections, nên **không được suy từ một cột số học duy nhất**.

Nếu SLO yêu cầu **p99 ≤ 200 ms** và error ≤ 0,5%, mức 1.500 offered ops/s có thể đáp ứng trong bài thử này. Nhưng không được tuyên bố capacity production bằng đúng 1.500:

- Cần nhiều lần chạy lặp lại.
- Cần steady-state đủ dài, không chỉ trước khi compaction tích lũy.
- Cần kiểm tra node failure, repair, traffic burst và headroom.
- Cần thử data distribution thật, không chỉ uniform random keys.
- Cần đối chiếu client/generator limits, không chỉ server metrics.

### 17.1. “Knee of the curve” quan trọng hơn throughput đỉnh

Từ 2.000 lên 2.500 offered ops/s, successful throughput ở ví dụ giảm, nhưng p99 và disk await tăng rất mạnh. Đây là dấu hiệu tải đã vượt phạm vi phục vụ bền vững.

Một capacity target tốt thường nằm **trước điểm cong mạnh**, để còn dự phòng khi:

- Một node down hoặc được rolling upgrade.
- Compaction/repair/streaming diễn ra.
- Retry và client burst làm attempts/s cao hơn logical requests/s.
- Data/tombstone volume tăng theo tháng.
- Network/GC tạo tail latency không đều.

**Không chọn “max observed QPS” làm mức giới hạn production** nếu error budget và p99 không đạt.

## 18. Phân tầng kết quả theo query, partition và node

### 18.1. Không gộp tất cả workload rồi đọc một p99

Giả sử API có:

- Query A: đọc 1 row theo full primary key.
- Query B: đọc 20 row mới nhất trong một partition.
- Query C: đọc range nhiều page.
- Query D: LWT conditional write.

Nếu gộp hết vào một histogram duy nhất, một query A chiếm 90% requests có thể che p99 rất xấu của query C/D.

Nên phân nhóm theo:

| Nhãn nên có | Mục đích | Giới hạn cardinality |
|---|---|---|
| `query_template` | So cùng CQL shape | Tên template cố định |
| `operation` | Read, write, LWT, batch | Tập nhỏ |
| `outcome` | Success/timeout/unavailable/error | Tập nhỏ |
| `consistency` | ONE, LOCAL_QUORUM, ... | Tập nhỏ |
| `datacenter` | Local/remote DC | Tập nhỏ |
| `client_region` | Nhận diện mạng caller | Tập nhỏ |
| `payload_band` | Small/medium/large | Bins hữu hạn |
| `partition_size_band` | Phát hiện wide partition | Bins hữu hạn |

**Không đưa raw primary key, tenant UUID hoặc token làm metric label**. Nếu cần điều tra hot partition, dùng tracing/log được giới hạn quyền và **sampling**; metric labels theo từng key có thể tăng không giới hạn và tiết lộ dữ liệu.

### 18.2. Simpson's paradox và traffic mix

Ví dụ khi trước deploy, query A (rẻ) chiếm 90%; sau deploy, query B (đắt) chiếm 40%. Cluster p99 tăng có thể phản ánh **thay đổi traffic mix**, dù mỗi query riêng không chậm hơn.

Cần so:

1. Percentile cho **cùng query template**.
2. Tỷ lệ mix và payload/rows/query.
3. Kích thước partition/token distribution.
4. Offered/achieved rate của từng nhóm.
5. RF/CL/driver settings và client region.
6. Background compaction/repair.

Không gọi “tuning regressions” khi tập workload bị thay đổi đáng kể và chưa được chuẩn hóa so sánh.

### 18.3. Per-node latency quan trọng ở cluster phân tán

Một node có p99 read latency xấu do disk/GC hoặc hotspot có thể ảnh hưởng requests mà nó làm coordinator hoặc replica. Nếu chỉ nhìn cluster average:

~~~text
Node A  p99=40 ms,  read QPS=1000
Node B  p99=45 ms,  read QPS=1000
Node C  p99=800 ms, read QPS=4000  <-- hotspot
~~~

Bảng này là giả định. Không tính cluster p99 bằng trung bình (40+45+800)/3; không trọng số cũng không thể phục dựng percentile từ ba số p99. Cần histogram raw/bucket theo node, cộng counts thích hợp và phân tích **partition/token distribution**.

## 19. Fault testing: đo phản ứng khi một replica hoặc node lỗi

### 19.1. Ba giai đoạn có thể so sánh

~~~mermaid
flowchart TD
    A["Baseline: mọi node khỏe"] --> B["Fault window: một failure được phép trong LAB"]
    B --> C["Recovery: phục hồi node/network"]
    C --> D["So p99, success, throughput, retries, backlog, data correctness"]
~~~

Chỉ làm fault injection với **cluster cô lập** và owner/rollback. Mục tiêu không phải gây lỗi nhiều nhất, mà là đo mức **degradation có giới hạn** và khả năng phục hồi.

Trong fault window, thu:

- Offered vs successful logical ops/s.
- p50/p95/p99 và timeout/error %.
- Driver retry/speculative attempts/s.
- Coordinator/replica CPU/GC/disk/network.
- Pending/dropped messages, hints, compaction/streaming.
- Node status, CL, RF và DC/rack.
- Recovery time từ lúc fault kết thúc tới khi SLO ổn định trở lại.

### 19.2. RF=3, CL=LOCAL_QUORUM trong một DC

Giả sử keyspace RF=3 ở dc1. Quorum là **2 phản hồi phù hợp** cho thao tác thông thường theo CL. Khi một replica down:

- Một số requests vẫn có thể thành công nếu đủ replica còn lại phục vụ.
- Latency có thể tăng vì route/retry, replica còn lại nóng hơn hoặc queue khác.
- Nếu replica thứ hai không đáp ứng kịp, có thể xuất hiện `ReadTimeoutException`, `WriteTimeoutException` hoặc `UnavailableException` tùy trạng thái.
- Hints/repair/recovery tạo thêm background work sau khi node quay lại.

**Không đồng nhất “CL cho phép một node down” với “p99 sẽ không đổi”**. Availability logic và capacity headroom là hai điều kiện riêng.

### 19.3. Multi-DC và network partition

Với `NetworkTopologyStrategy` và một app ưu tiên local DC:

- `LOCAL_QUORUM` đọc/ghi theo điều kiện local DC liên quan.
- Traffic cross-DC có thể vẫn tồn tại từ replication/hints/repair.
- Lỗi app→coordinator local DC có thể gây `AllNodesFailedException` dù DC khác vẫn khỏe.
- `EACH_QUORUM` chỉ dùng ở những thao tác được server hỗ trợ và cần hiểu chính xác DC quorum semantics.
- Failover sang DC khác phải có kế hoạch CL, topology, latency và correctness.

Test fault cross-DC chỉ nên chạy ở cluster mô phỏng multi-DC có network isolation được kiểm soát. **Không chặn network giữa các datacenter production** để tạo p99 samples.

### 19.4. Success p99 giảm khi fault không nhất thiết là tốt

Giả sử trước fault:

~~~text
success rate: 99.9%
success p99: 150 ms
timeout rate: 0.1%
~~~

Trong fault:

~~~text
success rate: 80%
success p99: 100 ms
timeout rate: 20%
~~~

p99 của **surviving successes** giảm nhưng dịch vụ tệ hơn nhiều; một lượng lớn slow requests bị loại bằng timeout. Báo cáo phải đặt **latency và availability cạnh nhau**; không chỉ p99 success.

### 19.5. Recovery không chỉ là node `UN`

Khi node về trạng thái UP/NORMAL, vẫn cần theo dõi:

- Pending hints và delivery.
- Repair/rebuild/streaming nếu có.
- Compaction backlog và disk free.
- Replica read/write latency.
- Error/timeout rate và client pools reconnecting.
- API SLO p99, not just Cassandra node status.

**Recovery time của hệ thống phục vụ** có thể dài hơn thời điểm node trở lại `UN`.

## 20. Đặt điều kiện pass/fail và stop conditions trước khi chạy

### 20.1. Một bản acceptance criteria minh họa

Giả sử hệ thống đặt các yêu cầu sau cho query template `latest20_by_device_day`:

| Tiêu chí | Ví dụ acceptance | Cách đo |
|---|---|---|
| Successful logical read | ≥ 99,9% | Lỗi/timeout trên logical request |
| p99 success latency | ≤ 200 ms | Client histogram window |
| Sustained offered load | 1.000 requests/s | Open-loop generator schedule |
| Completed success rate | Gần offered, ổn định | Client outcomes và backlog |
| p99 under one-node fault | ≤ 400 ms | Fault window lab có chủ đích |
| CPU headroom | Không có node nóng liên tục quá giới hạn nội bộ | Per-node CPU/core |
| Disk p95 read latency | Dưới ngưỡng device/SLO đã định | Per-device |
| Compaction backlog | Không tăng không kiểm soát | Compaction metrics theo thời gian |
| Data correctness | Không sai primary key/CL/side effects | Read-back/checksum/invariants |
| Recovery | SLO được khôi phục trong cửa sổ định nghĩa | API + node metrics |

Các ngưỡng là **ví dụ giả định**. Mỗi hệ thống phải định nghĩa theo business SLO, hardware và capacity budget; không coi chúng là SLA mặc định của Cassandra.

### 20.2. Stop conditions

Dù chạy trên lab, nên dừng hoặc giảm tải khi xuất hiện:

- Generator memory/in-flight vượt cap.
- Error/timeout rate vượt budget trong nhiều windows.
- Disk free rơi dưới mức headroom an toàn.
- Compaction/flush pending tăng không có dấu hiệu hồi phục.
- CPU throttling/GC pause hoặc disk await tăng bất thường.
- Một node không còn reachable mà fault plan không dự kiến.
- Dữ liệu test tăng vượt quota/retention.
- Test ảnh hưởng dịch vụ dùng chung ngoài phạm vi được phép.

**Dừng do guardrail vẫn là một kết quả đo có giá trị**, không phải thất bại cần che giấu. Báo cáo mốc tải và nguyên nhân dừng.

### 20.3. Xác định capacity bền vững, không chỉ peak

Một câu trả lời dạng:

> “Cluster chịu được 1.500 read ops/s trong workload A tại RF=3/LOCAL_QUORUM, payload median 1 KiB, 4 giờ sustained test, với p99=120 ms và error=0,2%; khi mô phỏng mất một node, p99=250 ms và error=0,3%.”

có ích hơn “Cluster đạt 2.000 QPS” vì có **bối cảnh, thời gian, CL và failure headroom**. Các số ở đây vẫn chỉ là **mẫu báo cáo**, không phải một kết quả thử thực tế.

## 21. Runbook A — p99 tăng nhưng p50 gần như giữ nguyên

**Tình huống:** p50 tăng từ 9 lên 11 ms; p99 tăng từ 45 lên 600 ms; successful throughput chưa giảm nhiều.

1. **Xác minh phạm vi:** p99 đo tại client hay server, success only hay all outcomes, window có đủ mẫu chưa?
2. **Phân nhóm query:** query template, CL, payload band, local DC, read/write mix; tìm một query/tenant nhóm làm đuôi xấu.
3. **Xem arrival rate:** offered QPS có tăng nhanh? Closed-loop có che coordinated omission?
4. **So per-node:** disk await, GC pauses, CPU throttling, `tpstats` Pending, dropped messages.
5. **Kiểm tra data:** hot/wide partitions, tombstone scanned, SSTables per read, index/query shape.
6. **Kiểm tra background:** compaction, repair, bootstrap/streaming, hints và flush.
7. **Giảm load tạm thời:** throttle backfill/job nếu node gần saturation; không retry ồ ạt.
8. **Lặp test có kiểm soát:** cùng dataset/CL, với một thay đổi một lần; so p99 + successful throughput + errors + resource.
9. **Đóng incident:** ghi root cause/hypothesis, regression test, threshold và rollback.

**Tránh kết luận** “tăng driver timeout là sửa p99”. Nó có thể chỉ làm các request chậm giữ tài nguyên lâu hơn.

## 22. Runbook B — Throughput bão hòa, queue và disk latency tăng

**Tình huống:** offered QPS từ 1.500 lên 2.500, success ops/s chỉ tăng ít rồi giảm, `tpstats` Pending và disk await tăng.

1. **Đo bottleneck thật:** device read/write IOPS, throughput, latency, disk queue; CPU/GC và network cũng cần kiểm tra.
2. **Tách logical writes khỏi replica cost:** RF, CL, mutation bytes, commitlog, flush và compaction overhead.
3. **Xem hot node:** một replica có chịu nhiều token/hot keys hơn không; cluster average không đủ.
4. **Kiểm tra compaction:** pending, bytes read/rewrite, số SSTable, disk free/temporary headroom.
5. **Không tăng client concurrency mù quáng:** nó có thể tăng queue chứ không tăng successful throughput.
6. **Thử giảm offered load:** tìm mức queue trở về ổn định và p99 đạt SLO; ghi knee of curve.
7. **Đánh giá tuning:** query modeling, bucketing, TTL/tombstone, page size, compression/compaction strategy, disk capacity, scale-out phù hợp.
8. **Xác minh sustained:** sau điều chỉnh, chạy đủ lâu để compaction/flush ổn định; kiểm tra phục hồi khi dừng generator.

**Đừng chạy major compaction/repair tự phát trên production** để “giải quyết benchmark”; chúng có thể tạo thêm I/O/CPU và cần SOP riêng.

## 23. Runbook C — p99 xấu do load generator, không phải Cassandra

**Tình huống:** benchmark báo p99 tăng mạnh, nhưng Cassandra CPU/disk thấp, query latency server ổn; load generator đạt CPU 100% và GC pause cao.

1. **Đo generator:** CPU/core, heap, GC, network, scheduling lag, outstanding/rejections.
2. **Phân biệt timestamps:** scheduled arrival, submitted, completed; nếu submit bị trễ, latency theo lịch có thể cao dù driver response nhanh.
3. **Kiểm tra instrumentation:** log/metrics từng request có block callback, lock contention hoặc allocation quá mức?
4. **Kiểm tra pooling:** driver session có được tái sử dụng? Tạo session mỗi request là anti-pattern.
5. **Giới hạn work ngoài Cassandra:** JSON serialization, protobuf, TLS handshake mới mỗi call, HTTP response mapping.
6. **Kiểm tra source scheduler:** closed-loop có tự giảm offered load lúc chậm; open-loop có bỏ arrivals khi hết permits mà không ghi không?
7. **Phân bố generator hosts nếu cần:** vẫn có total rate/accounting đúng và clock policy rõ.
8. **So baseline lại:** giữ nguyên query/data/CL, chỉ sửa generator; kiểm tra p99 ở driver/server và achieved rate.

**Generator khỏe là điều kiện để kết luận server có bottleneck.** Đừng dựa vào một con số p99 mà không rõ nó đo từ đâu.

## 24. Runbook D — Failover đạt quorum nhưng latency/error budget không đạt

**Tình huống:** Cluster RF=3, LOCAL_QUORUM, thử mất một replica trên lab; phần lớn write thành công nhưng p99 tăng 6 lần, retry attempts tăng và compaction backlog xuất hiện sau phục hồi.

1. **So baseline vs fault vs recovery:** cùng offered QPS, query mix và dataset.
2. **Xem loại lỗi:** DriverTimeout, Read/WriteTimeout, Unavailable, AllNodesFailed và connection pool errors.
3. **Đối chiếu RF/CL:** còn bao nhiêu replica available, DC/rack nào bị ảnh hưởng?
4. **Xem node còn lại:** CPU/GC, disk, commitlog, network, pending queues.
5. **Xem retry/speculative execution:** có khuếch đại tải trong fault window không?
6. **Xem recovery:** hints/streaming/repair, compaction và disk headroom có làm tail kéo dài?
7. **Giảm offered load nếu vượt guardrails**; có thể capacity cho một-node-fault phải thấp hơn steady healthy capacity.
8. **Xác minh correctness:** không mất/nhân mutation do retry không an toàn, LWT/counter/write outcome được xử lý.
9. **Báo cáo recovery time:** không chỉ thời điểm `nodetool status` đổi `UN`, mà khi API success/p99 trở lại SLO.

**Hệ có thể đạt logical availability nhưng không đạt performance SLO**. Cần headroom và traffic policies cho điều kiện suy giảm, không chỉ quorum arithmetic.

## 25. Mẫu báo cáo benchmark có thể so sánh

Một báo cáo hữu ích phải đủ thông tin để người khác **tái tạo cùng workload**, thay vì chỉ có ảnh chụp p99 và con số QPS.

### 25.1. Metadata bắt buộc

~~~yaml
# Ví dụ báo cáo, KHÔNG phải file cấu hình cần tạo ở bước này.
experiment_id: cassandra-bench-read-001
environment: isolated-staging
date_utc: "2026-11-21"
cassandra_release: "<version tested>"
java_driver_release: "<version tested>"
generator:
  model: open-loop
  offered_rps: 1200
  max_outstanding: 500
  host_count: 2
cluster:
  nodes_per_dc: 3
  datacenters: [dc1]
  replication_factor_dc1: 3
  read_consistency: LOCAL_QUORUM
  write_consistency: LOCAL_QUORUM
workload:
  query_template: latest20_by_device_day
  read_percent: 100
  write_percent: 0
  partition_distribution: "uniform on preseeded data"
  rows_per_read_limit: 20
  paging_size: 20
phases:
  warmup_minutes: 5
  steady_minutes: 30
  recovery_until_stable: true
acceptance:
  p99_success_ms_max: 200
  logical_error_rate_pct_max: 0.5
  required_recovery: "API and Cassandra metrics stable"
~~~

**Các giá trị là ví dụ**. Trường release/version phải điền bằng thông tin cluster thật khi test; không sao chép `<version tested>` vào một báo cáo cuối cùng.

### 25.2. Bảng kết quả nên điền

| Nhóm | Chỉ số | Healthy baseline | Under fault | Recovered |
|---|---|---:|---:|---:|
| Client | Offered logical RPS | 1.200 | 1.200 | 1.200 |
| Client | Successful RPS | 1.195 | 1.160 | 1.193 |
| Client | p50 success | 9 ms | 12 ms | 10 ms |
| Client | p95 success | 35 ms | 180 ms | 40 ms |
| Client | p99 success | 140 ms | 520 ms | 155 ms |
| Client | Timeout/error % | 0,2% | 2,7% | 0,3% |
| Driver | Retry attempts / logical request | 1,01 | 1,22 | 1,02 |
| Server | Worst-node CPU | 58% | 83% | 61% |
| Server | Worst-node disk await | 7 ms | 26 ms | 9 ms |
| Server | Pending compaction | Low/stable | Rising | Declining |
| Recovery | Time to SLO | N/A | N/A | 8 phút |

Đây là **bảng số liệu giả định**, không phải measurement. Một vài số offered, success và errors được làm tròn theo cửa sổ và có thể chênh vì in-flight ở biên; khi báo cáo thật phải nêu **denominator**, time window, sample count và rejections.

### 25.3. Kết luận của báo cáo minh họa

- Healthy đạt ví dụ **p99 ≤ 200 ms** và **error ≤ 0,5%**.
- Khi fault, p99 520 ms, error 2,7% → **FAIL** nếu acceptance under-fault yêu cầu p99 ≤ 400 ms và error ≤ 1%.
- Phục hồi sau khoảng 8 phút, nhưng cần xác minh **hints/compaction/disk**, không chỉ API response.
- Capacity target production nên giữ headroom cho failover; cần điều chỉnh concurrency/rate, khám phá node hotness và lặp lại test.
- Không chọn mức offered cao nhất một lần chạy làm capacity chuẩn.

### 25.4. Đính kèm evidence thay vì chỉ số tổng hợp

Nên lưu ở repository báo cáo hoặc hệ thống kết quả được phê duyệt:

- Query templates/CQL, schema và seed data distribution.
- Driver/generator/server versions và config profile.
- Time-series offered/achieved/errors, p50/p95/p99 histogram buckets.
- Per-node CPU/GC/disk/network, `tpstats`/compaction/streaming.
- Timeline lỗi/fault injection và recovery.
- Trạng thái đúng/sai của business invariants và data consistency tests.
- Mục tiêu, quyết định PASS/FAIL, caveats, chủ sở hữu và action items.

Đảm bảo logs/metrics không chứa mật khẩu, tokens, raw tenant/device IDs hay bind values nhạy cảm. Không đưa cả production dataset vào báo cáo benchmark.

## 26. Các anti-pattern đo tải cần nhận diện

| Anti-pattern | Vì sao nguy hiểm? | Cách khắc phục |
|---|---|---|
| Chỉ báo trung bình latency | Che phần 1% chậm nhất | Luôn xem p50/p95/p99 + error |
| Lấy trung bình p99 của từng node | Percentile không cộng tuyến tính | Aggregate histogram cùng bucket/method |
| Chỉ tính p99 success | Timeout rơi khỏi biểu đồ | Đếm success/errors/timeouts cùng window |
| Chạy closed-loop và gọi đó là fixed RPS | Slow responses làm giảm offered rate | Ghi offered schedule hoặc dùng open-loop có cap |
| Không đo generator saturation | Có thể benchmark chính generator | Đo CPU/GC/network/schedule lag |
| Dùng 1 hot key đã cache làm đại diện | Không phản ánh token/data distribution | Seed nhiều partitions, profile thực |
| `cassandra-stress` default schema được coi là app benchmark | CQL/payload khác production | Custom profile/driver generator |
| Bỏ warm-up nhưng so với run có warm-up | Cache/JIT/pool khác | Ghi rõ cold vs warm conditions |
| Run vài chục giây rồi chốt max QPS | Không thấy compaction/recovery | Sustained windows và cool-down |
| Thêm retry để tăng success mà không đo attempts | Amplification che chi phí backend | Attempts/logical request, retries/s |
| Đổi CL xuống ONE để tăng QPS | Thay đổi correctness/availability | Giữ CL nghiệp vụ, báo cáo riêng |
| Không đo bytes/row hoặc rows/query | 1 QPS không đồng nhất work | Payload/rows/bytes per op |
| Gộp LWT, reads, writes vào một p99 | Mix khác làm lệch kết quả | Query template/operation breakdown |
| Chỉ xem cluster CPU trung bình | Một replica/core có thể nóng | Per-node/worst-node metrics |
| Chỉ nhìn `nodetool status` = UN | UP không bảo đảm SLO | Latency/queue/disk/GC/network |
| Tăng client concurrency khi disk đã bão hòa | Queue và timeout tăng | Giảm tải, tối ưu read path/capacity |
| Chạy repair/compact mù quáng khi p99 xấu | Tạo thêm I/O | SOP và resource headroom |
| Gọi retry/error bằng logical success | Sai mẫu số và rates | Tách attempts, outcomes, rejections |
| Sử dụng raw partition key làm metric label | Cardinality/security issue | Low-cardinality bands và sampling |
| Report một run duy nhất | Noise/CI/cache/clock khác nhau | Lặp lại và báo confidence/window |
| Không có stop conditions | Có thể phá lab hoặc ảnh hưởng hệ khác | Guardrails/owner/rollback |
| Tuyên bố p99 tốt hơn sau fault dù errors tăng | Survivorship bias | Gắn latency với availability |
| Bỏ qua data correctness | Throughput cao nhưng mutation sai | Verify read-back/invariants |
| Không xét multi-DC network | Thực tế replication tốn băng thông | DC topology/CL/cross-DC metrics |

## 27. Bài tập có đáp án

### Câu 1 — p50, p95, p99

Một tập 1.000 request có 900 request 10 ms, 50 request 40 ms, 40 request 180 ms, 9 request 900 ms và 1 request 4.000 ms. Theo nearest-rank, p95 và p99 là bao nhiêu?

**Đáp án:** p95 ở vị trí 950 = **40 ms**; p99 ở vị trí 990 = **180 ms**. Không lấy trung bình hay max thay p99.

### Câu 2 — Trung bình che tail

Tập dữ liệu Câu 1 có mean bao nhiêu?

**Đáp án:** `(900×10+50×40+40×180+9×900+1×4000)/1000 = 30,3 ms`. Mean thấp không làm các request 900–4.000 ms biến mất.

### Câu 3 — p99.9

Với cùng 1.000 request, nearest-rank p99.9 bằng?

**Đáp án:** `ceil(0,999×1000)=999`, vị trí 999 có **900 ms**. Phần tử 1.000 có 4.000 ms là max.

### Câu 4 — Không đủ mẫu

Một cửa sổ chỉ có 40 requests. p99 có đáng tin như cửa sổ 100.000 request không?

**Đáp án:** Không. 1% của 40 là 0,4 request nên ước lượng p99 rất nhạy với outlier/phương pháp; cần đủ sample count và window rõ.

### Câu 5 — Độ trễ và tỷ lệ lỗi

Test A có success p99=70 ms nhưng 10% request timeout. Test B có success p99=150 ms và 0,05% timeout. Có thể tuyên bố A tốt hơn chỉ vì p99 thấp?

**Đáp án:** Không. Latency success và availability phải báo cùng nhau; A có thể đã loại mọi request chậm thành timeout.

### Câu 6 — Offered và achieved

Generator muốn phát 3.000 requests/s; server chỉ hoàn tất 2.300/s. Nếu không có rejection/drop và arrival tiếp tục, backlog biến động ra sao?

**Đáp án:** Trong mô hình đơn giản tăng khoảng **700 request mỗi giây**. Thực tế phải đo nơi queue/rejection và in-flight; không tự suy toàn bộ queue nằm ở Cassandra.

### Câu 7 — Little's Law

Ở trạng thái ổn định 2.500 completed ops/s, latency trung bình 40 ms, số request trung bình trong hệ khoảng bao nhiêu?

**Đáp án:** `L = 2500 × 0,040 = 100`. Không dùng p99 để thay mean trong cùng công thức.

### Câu 8 — RF và replica cost

Có 2.000 logical writes/s, RF=3 một DC. Số replica mutation deliveries mục tiêu khoảng bao nhiêu trong trạng thái ổn định?

**Đáp án:** Khoảng **6.000/s** trước khi xét retries, hints, batching, compaction và phân bố node. **Không** đồng nghĩa 6.000 disk IOPS hoặc mỗi node nhận 6.000.

### Câu 9 — CL

Hạ `LOCAL_QUORUM` xuống `ONE` giúp benchmark nhanh hơn. Có nên chọn luôn vì throughput tăng?

**Đáp án:** Không mặc định. CL là quyết định consistency/availability/correctness; không hạ chỉ để đạt KPI.

### Câu 10 — Percentile across nodes

Ba node báo p99 lần lượt 40, 45, 800 ms. Có được lấy trung bình ba số rồi gọi p99 cluster không?

**Đáp án:** Không. Percentiles không aggregate theo trung bình; cần histograms/raw samples với trọng số và bucket tương thích.

### Câu 11 — Histogram

Histogram cổ điển muốn tính p99 nhiều instances bằng PromQL. Nên giữ label nào trong `sum by`?

**Đáp án:** Giữ `le` và nhóm mong muốn (ví dụ query_template) khi cộng bucket rates. Sau đó dùng `histogram_quantile(0.99, ...)`.

### Câu 12 — Coordinated omission

Worker synchronous đợi response xong mới gửi request mới. Khi server pause hai giây, benchmark bỏ lỡ nhiều arrivals định kỳ. Đây là vấn đề gì?

**Đáp án:** **Coordinated omission**: lịch arrival thực tế không được giữ/ghi; histogram có thể đánh giá tail latency thấp hơn trải nghiệm nguồn traffic cố định.

### Câu 13 — Open-loop không giới hạn

Generator open-loop gửi 10.000/s vào cluster chỉ xử lý 1.000/s, không giới hạn outstanding. Điều gì có thể xảy ra?

**Đáp án:** Queue/in-flight/heap tăng nhanh, có thể làm generator/cluster quá tải. Phải có max outstanding, rejections được đếm và stop conditions.

### Câu 14 — Driver async timing

Đo thời gian `session.executeAsync(stmt)` hoàn tất lần đầu trên một SELECT 10.000 rows. Có chắc đã đo toàn bộ thời gian tiêu thụ 10.000 rows?

**Đáp án:** Không. Có thể mới nhận page đầu; cần đo full paging/processing nếu SLO đòi kết quả hoàn chỉnh.

### Câu 15 — Generator bottleneck

Cassandra nodes CPU/disk thấp nhưng generator CPU 100%, GC pause lớn. Nên kết luận Cassandra disk chậm không?

**Đáp án:** Không. Kiểm tra generator saturation, callback/instrumentation, schedule lag và network trước.

### Câu 16 — Hot partition

Uniform key test có p99 tốt, production một số device cực nóng có p99 cao. Cần thay đổi profile thế nào?

**Đáp án:** Bổ sung skew/Zipfian/hot-key distribution, per-node/token metrics, partition sizes và đo worst-node; xem bucketing/data modeling.

### Câu 17 — Compaction

p99 tăng khi `compactionstats` pending và disk await tăng. Có nên chạy thêm major compaction trên production ngay?

**Đáp án:** Không. Cần xác minh nghẽn I/O, strategy, headroom, background job và runbook; major compaction có thể tăng tải.

### Câu 18 — One-node fault

RF=3, `LOCAL_QUORUM`, một replica down trong cluster lab. Có chắc p99 giữ nguyên vì vẫn đủ quorum không?

**Đáp án:** Không. Replica còn lại gánh tải, route/retry/hints và network có thể làm p99/error tăng; cần đo degraded capacity.

### Câu 19 — Recovery

`nodetool status` cho node vừa restart báo `UN`. Có thể kết luận cluster đã phục hồi hoàn toàn không?

**Đáp án:** Không. Cần xem hints, repair/streaming, compaction, per-node latency, client connections và API SLO.

### Câu 20 — Resource headroom

Hai run có cùng successful throughput. Run A CPU node nóng nhất 55%, disk await 5 ms; run B CPU 90%, disk await 30 ms. Có thể coi năng lực dự phòng như nhau không?

**Đáp án:** Không. B gần bão hòa và kém an toàn với node fault/burst; phải xét resource headroom và p99.

### Câu 21 — Error denominator

Driver retry ba lần cho một logical HTTP request. Có thể coi 3 driver attempts là 3 logical requests thành công khi tính SLO API không?

**Đáp án:** Không. SLO logical request dùng một outcome cuối; attempts/s riêng để đo tải Cassandra và retry amplification.

### Câu 22 — Kết luận capacity

Một test 30 giây đạt 20k QPS trước khi compaction bắt đầu; test một giờ ở cùng offered QPS có pending queues tăng và p99 vượt SLO. Mức capacity bền vững là bao nhiêu?

**Đáp án:** Không thể khẳng định 20k chỉ dựa trên burst. Cần xác định mức tải **steady-state** trước điểm bão hòa với p99/error/resource và failure headroom đạt yêu cầu, rồi lặp lại đo.

## 28. Checklist nghiệm thu đo tải và thử lỗi phân tán

### 28.1. Thiết kế benchmark

~~~text
[ ] Workload có schema, partition key, query template và CQL rõ.
[ ] Read/write/LWT mix, payload bytes, rows/query được ghi nhận.
[ ] RF, CL, local DC, topology và driver version cố định.
[ ] Có data volume lớn/nhỏ, TTL/tombstone, hot-key phân bố phù hợp.
[ ] Xác định open-loop/closed-loop và coordinated omission.
[ ] Generator có max QPS/in-flight, báo rejected/missed arrivals.
[ ] Dataset/warm-up/cache conditions được mô tả.
[ ] Có nhiều ramp levels, steady windows và cool-down.
[ ] Thí nghiệm chạy trên cluster được phép, data test riêng.
[ ] Owner, guardrails, stop conditions, recovery/rollback rõ.
~~~

### 28.2. Số đo client/driver

~~~text
[ ] p50/p95/p99 theo query template và window có sample count.
[ ] Mean/max và histograms có bucket/đơn vị được mô tả.
[ ] Percentiles không bị average qua node hoặc thời gian.
[ ] Success latency đo cùng failure/timeout/unavailable rates.
[ ] Offered, submitted, completed, successful throughput tách biệt.
[ ] Logical operations và attempts/retries/s không bị lẫn.
[ ] Row/s và bytes/s được đo khi query trả nhiều row/page.
[ ] API end-to-end và driver first-page/full-consume tách biệt.
[ ] Generator CPU/GC/network/schedule lag không bão hòa.
[ ] Metrics không chứa raw primary key/tenant/token/secret.
~~~

### 28.3. Số đo Cassandra và interpretation

~~~text
[ ] Worst-node CPU, CPU throttle, GC, heap/off-heap được quan sát.
[ ] Disk free GB/%, IOPS, MiB/s, await/queue theo device.
[ ] Commitlog fsync, memtable flush và compaction pending.
[ ] Read amplification: SSTables/read, tombstone/row sizes.
[ ] nodetool tpstats, compactionstats, tablestats theo thời gian.
[ ] Native transport và inter-DC network/Rx-Tx được đo.
[ ] nodetool netstats không bị dùng thay CQL network metric.
[ ] Per-node RF/CL/replica availability/hints/repair được so.
[ ] Node UN không bị hiểu là phục hồi API SLO hoàn toàn.
[ ] Error/drift tăng thì test dừng theo guardrail, không che giấu.
~~~

### 28.4. Phân tích và bàn giao

~~~text
[ ] PASS/FAIL theo p99, successful throughput và error budget.
[ ] Có bảng baseline/fault/recovery nếu bài test fault.
[ ] So workload cùng schema/dataset/CL, không cherry-pick runs.
[ ] Báo cáo knee-of-curve và headroom, không chỉ peak QPS.
[ ] Có time-series chứng minh steady state, không backlog drift.
[ ] Có sample sizes, window lengths, units, histograms và caveats.
[ ] Có test correctness, không chỉ hiệu suất.
[ ] Có runbook xử lý p99 tail, saturation, generator, node fault.
[ ] Chỉ ra các bottleneck chưa kết luận rõ và dữ liệu cần đo thêm.
[ ] Không tự chạy Gradle/benchmark/fault injection trong STEP 4.
~~~

## 29. Tổng kết

Để **đo tải và lỗi phân tán** cho Apache Cassandra đúng, phải xem latency, throughput và resource như **một bộ chỉ số liên kết**:

1. **p50/p95/p99** mô tả phân bố độ trễ; p99 giúp phát hiện tail latency mà mean hoặc p50 có thể che.
2. **Không average percentiles** giữa node/instance/window; muốn p99 tổng hợp phải dùng histogram hoặc raw observations với phương pháp nhất quán.
3. **Độ trễ của success phải đi cùng error/timeout rate**; p99 giảm vì request chậm chết trước không phải tối ưu thành công.
4. **Offered load ≠ completed/success throughput**. Khi throughput bão hòa mà queue, p99, errors tăng, đã đi qua điểm tải an toàn.
5. **Logical operations ≠ driver attempts**. Retry/speculative execution có thể tăng tải backend và làm benchmark sai nếu chỉ đếm HTTP outcomes.
6. **Little's Law liên hệ các giá trị trung bình** của concurrency, throughput và latency ở trạng thái ổn định; không thay mean bằng p99.
7. **Open-loop vs closed-loop và coordinated omission** có thể thay cách nhìn về latency/throughput; chọn generator theo nguồn traffic thật, ghi nhận misses/rejections.
8. **RF/CL, partition key và data distribution** quyết định replica work. Hot/wide partitions và tombstones có thể làm một vài node chậm dù average cluster tốt.
9. **CPU/GC/heap, disk IOPS/await, network, compaction, repair, hints và pending queues** giải thích vì sao p99 tăng; không chỉ xem node `UN`.
10. **Benchmark phải có warm-up, sustained windows, guardrails và recovery**. Một peak QPS ngắn không phải capacity bền vững.
11. **Fault test trong lab** phải đo trước/trong/sau failure theo SLO, resource headroom và data correctness; quorum availability không bảo đảm p99 giữ nguyên.
12. **Báo cáo có thể tái tạo** cần schema/CQL, versions, RF/CL, workload mix, sample count, histograms, outcomes, server resources và những giới hạn kết luận.

Câu hỏi quan trọng nhất không phải **“Cassandra đạt bao nhiêu QPS?”**, mà là: **“Ở workload, RF/CL và phân bố dữ liệu xác định, hệ thống hoàn tất bao nhiêu logical operations với p99 và error budget nào, tiêu thụ những tài nguyên nào trên node nóng nhất, và còn đủ headroom để phục vụ đúng khi một phần cluster lỗi hay không?”**. Đó mới là cơ sở cho quyết định tối ưu truy vấn, điều chỉnh capacity và bảo vệ SLO.



