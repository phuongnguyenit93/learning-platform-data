# Chỉ số theo dõi phía ứng dụng, driver, máy chủ và hệ điều hành

Một API tra cứu đơn hàng dùng NoSQL có thể hoạt động bình thường trong nhiều tháng, rồi đột ngột tăng thời gian phản hồi từ 40 ms lên 900 ms ở phân vị 99 (p99). Database dashboard báo CPU 45%, ứng dụng báo timeout, còn log truy vấn tại server chỉ thấy phần lớn câu lệnh mất 12 ms. Nếu chỉ nhìn một chỉ số, team rất dễ kết luận sai: CPU chưa cao thì “database không có vấn đề”, hoặc API timeout thì “query quá chậm”. Trên thực tế, phần thời gian còn lại có thể nằm ở connection pool, hàng đợi driver, DNS/TLS handshake, retry, network, serialization hoặc thread bị kẹt.

Để chẩn đoán hệ thống **Database No SQL**, cần quan sát nhiều tầng và liên kết chúng theo **một request, một thao tác, một mốc thời gian và một nhóm tài nguyên**. Bài học này thuộc chương **Quan sát và chẩn đoán**, trình bày hệ thống chỉ số từ ứng dụng, NoSQL driver, database server đến hệ điều hành/container, cùng phương pháp tính latency, nhận diện contention, xử lý sự cố và xác minh kết quả.

Mục tiêu không phải thu thập càng nhiều metric càng tốt. Mục tiêu là trả lời được các câu hỏi có thể hành động:

1. Người dùng đang bị ảnh hưởng ở thao tác nào, mức nào?
2. Thời gian chờ phát sinh **trước, trong hay sau** khi truy vấn đến database?
3. Lỗi nằm ở một khóa/partition/tenant, một node hay toàn cụm?
4. Hệ đang thiếu CPU, bộ nhớ, I/O, network, connection hay capacity theo quota?
5. Các retry, timeouts hoặc background jobs có khuếch đại tải không?
6. Bước xử lý khẩn cấp nào an toàn và giải pháp dài hạn là gì?
7. Sau thay đổi, số liệu nào chứng minh p99 và tính đúng đắn được cải thiện?

**Lưu ý:** tên metrics, khả năng thu thập và những giới hạn về sampling khác nhau giữa MongoDB, Cassandra, ScyllaDB, DynamoDB, Redis, CouchDB, Elasticsearch/OpenSearch, JVM driver và các dịch vụ managed. Những ngưỡng, biểu đồ và tên chỉ số trong bài là ví dụ kiến trúc; khi triển khai phải đối chiếu tài liệu đúng phiên bản và hiện trạng hệ thống.

## 1. Bốn lớp quan sát và luồng thời gian của một request

Một read điển hình:

~~~mermaid
flowchart LR
    U["Client"] --> A["Ứng dụng/API"]
    A --> P["Driver + connection pool"]
    P --> N["Network / OS"]
    N --> S["NoSQL server/coordinator"]
    S --> D["Storage / replica / index"]
    D --> S
    S --> N
    N --> P
    P --> A
    A --> U
~~~

Mỗi tầng thấy một phần khác nhau:

| Lớp | Câu hỏi | Tín hiệu quan trọng |
|---|---|---|
| **Ứng dụng** | Người dùng mất bao lâu, request có thành công không? | Request rate, p50/p95/p99, errors, timeouts, queue, cache hit, business outcome |
| **Driver/client SDK** | Gọi DB chờ ở đâu trước và trong network round trip? | Pool wait, in-use/idle connections, retries, request latency, errors, timeouts, topology refresh |
| **Máy chủ NoSQL** | Node/shard/partition đang thực hiện bao nhiêu work? | Query latency, active ops, scan, cache miss, compaction, replication lag, disk queue, throttling |
| **Hệ điều hành/runtime** | Tài nguyên nền có giới hạn gì? | CPU/user/system/steal, memory pressure, GC, page faults, disk latency, network drops, file descriptors, cgroup limits |

**Một tầng khỏe không chứng minh tầng khác khỏe.** p99 server dưới 20 ms không loại trừ driver đợi pool 500 ms; CPU trung bình 40% không loại trừ một core hoặc một shard đã bão hòa.

## 2. SLI, SLO và alert: đo điều người dùng thật sự nhận

Một **Service Level Indicator (SLI)** là chỉ số định lượng chất lượng dịch vụ, ví dụ p99 latency của `GET /orders/{id}` hoặc tỷ lệ requests được trả thành công.

Một **Service Level Objective (SLO)** là mục tiêu cho SLI trong một cửa sổ xác định, ví dụ:

~~~text
Trong 30 ngày:
  99,9% GET /orders/{id} hoàn thành hợp lệ dưới 300 ms.

Trong giờ cao điểm:
  checkout accepted/committed theo business contract,
  không vì lỗi cache mà xác nhận đơn sai.
~~~

Ví dụ các SLI:

- **Availability:** tỷ lệ requests hợp lệ được phục vụ đúng hợp đồng, không chỉ HTTP 200.
- **Latency:** độ trễ tổng của user-facing operation, gồm cả pool/network/retries.
- **Correctness:** không ghi trùng do retry, không vượt tồn kho, không đọc sai tenant.
- **Freshness:** bản đọc/projection chậm so với nguồn bao lâu nếu ứng dụng có eventual reads.
- **Durability/replication:** dữ liệu đã ACK có còn sau failover theo hợp đồng không.

SLO nên **gắn với endpoint và tính chất nghiệp vụ**, không gộp một read cache nhanh với một checkout transaction chậm thành một đường “DB latency trung bình” khiến vấn đề biến mất.

### 2.1. Tại sao không dùng ngưỡng CPU cố định làm SLO?

“DB CPU dưới 70%” là một **resource guardrail**, không phải chất lượng người dùng. Một query bị khóa bởi hot partition có thể timeout khi CPU cluster còn thấp; ngược lại CPU 85% với throughput cao và p99 đạt mục tiêu có thể chưa là sự cố.

Alert tốt thường liên kết **burn rate của error budget**, sự suy giảm SLI và những resource signals hỗ trợ tìm nguyên nhân. CPU/disk/throttle alert vẫn hữu ích để phòng ngừa, nhưng nên có ngưỡng và hành động xác định.

## 3. Ba nhóm tín hiệu RED và bốn nhóm USE

**RED** cho các dịch vụ:

- **Rate:** requests/s, phân biệt operations chính.
- **Errors:** lỗi/s hoặc tỷ lệ lỗi, kể cả timeout/unknown outcome.
- **Duration:** phân phối latency p50/p95/p99 và request count.

**USE** cho các tài nguyên:

- **Utilization:** phần capacity đang sử dụng.
- **Saturation:** số work đang chờ hoặc bị từ chối vì thiếu capacity.
- **Errors:** lỗi ở tài nguyên.

Ví dụ:

| Tầng | RED/USE có thể theo dõi |
|---|---|
| API | `http_requests_total`, error rate, duration histogram |
| Driver | Calls/s, pool wait histogram, connection utilization, failed acquisitions |
| NoSQL server | Op latency, active operations, queue depth, rate limiting/throttling |
| CPU | Utilization, scheduler run queue, throttling |
| Disk | Utilization, await/latency, pending I/O, errors |
| Network | Bytes/s, retransmission, drops/errors, queue |
| Heap/cache | Used/max, GC pauses, cache hit/miss/evictions |

Không ép mọi thành phần vào một metric duy nhất. Một **counter timeout** chưa nói timeout do queue ở application hay server; đó là lúc cần trace và metrics theo lớp.

## 4. Chỉ số kiểu counter, gauge, histogram và timer

| Kiểu | Ý nghĩa | Ví dụ |
|---|---|---|
| **Counter** | Giá trị tích lũy, thường tăng đến khi reset process | Total requests, retries, errors |
| **Gauge** | Giá trị hiện thời, lên/xuống được | Queue length, active connections, memory used |
| **Histogram** | Phân phối quan sát theo buckets | Latency, request size, pool wait |
| **Summary** | Tóm tắt phân phối, tùy library có quantiles | Duration summary của process |
| **Timer** | Abstraction ghi duration/count, có thể xuất histogram | DB call duration |

Một counter `requests_total=500000` không có nghĩa hiện tại 500.000 requests/s. Muốn tính **tốc độ**, dùng thay đổi counter theo thời gian và xử lý reset đúng cách.

Gauge `db_pool_active=12` không có ý nghĩa nếu không biết `db_pool_max=12` hay `100`. Histogram mới cho phép nhìn phần đuôi của latency thay vì chỉ trung bình.

### 4.1. Không tính trung bình của p99 các instance

Giả sử hai pod:

~~~text
Pod A: 100.000 requests, p99 = 30 ms
Pod B:     100 requests, p99 = 2.000 ms
~~~

Trung bình p99 = 1.015 ms **không phải p99 toàn hệ**. Phân vị không có tính chất cộng trung bình; cần phân phối/buckets thô hoặc một cơ chế sketch/aggregation có hỗ trợ để tổng hợp theo traffic.

Tương tự, p99 của HTTP và p99 của DB không thể cộng thành p99 end-to-end theo toán học. Cần request tracing hoặc histogram end-to-end.

## 5. Các loại latency cần tách riêng

Thời gian request có thể được phân rã tương đối:

\[
T_{\mathrm{request}} \approx
T_{\mathrm{routing}}
+T_{\mathrm{app\ queue}}
+T_{\mathrm{pool\ wait}}
+T_{\mathrm{network}}
+T_{\mathrm{DB\ service}}
+T_{\mathrm{decode}}
+T_{\mathrm{response}}.
\]

Công thức là mô hình gợi ý, không phải tổng chính xác cho mọi implementation: một số giai đoạn overlap, retries lặp lại nhiều đoạn, connection establishment có thể nằm trong pool wait, và query gồm nhiều calls song song.

Một request có thể:

~~~text
Total HTTP duration:        850 ms
App routing/validation:      10 ms
Driver pool wait:           520 ms
One DB round trip:           24 ms
Retry/backoff wait:         270 ms
Decode + response:           26 ms
~~~

Nhìn server query = 24 ms rồi kết luận “database rất nhanh” là thiếu 826 ms của đường đi. Cần đo từ **góc nhìn người dùng**, đồng thời giữ các timer con để truy lỗi.

## 6. Latency percentiles: p50, p95, p99 và worst-case

- **p50:** một nửa requests có latency nhỏ hơn hoặc bằng mức này.
- **p95:** khoảng 5% requests chậm hơn mức này.
- **p99:** khoảng 1% requests chậm hơn mức này.
- **Max:** một sample chậm nhất, nhạy với outlier; có thể hữu ích nhưng không thay percentile.
- **Tail distribution:** các buckets/traces của requests chậm để tìm pattern.

Ví dụ một triệu GETs/ngày: 1% là khoảng **10.000 requests**. p99 xấu có thể ảnh hưởng đáng kể dù phần lớn requests vẫn nhanh.

### 6.1. Vì sao latency trung bình dễ đánh lừa?

~~~text
990 requests: 10 ms mỗi request
10 requests:  2.000 ms mỗi request
~~~

Trung bình gần 29,9 ms, nhưng 10 người dùng chờ khoảng 2 giây. Nếu ứng dụng bán hàng có SLA 300 ms, dùng latency mean sẽ bỏ qua nhóm bị ảnh hưởng nghiêm trọng.

Không chọn mỗi p99 nếu traffic quá ít: với 20 requests trong một cửa sổ, p99 dễ dao động vì sampling/statistical uncertainty. Có thể dùng event counts, phân phối, longer windows và error rate để đánh giá.

## 7. Request rate, concurrency và hàng đợi

Các chỉ số quan trọng:

- Arrivals/s: requests đến từ clients.
- Completed requests/s: số requests kết thúc.
- In-flight: số requests đang chạy.
- Queue length/age: requests đợi được xử lý.
- Rejected/429/503: số requests bị admission control từ chối.
- Per-operation mix: tỷ lệ key lookup, range query, scan, write.
- Client timeouts và cancellations.

Trong trạng thái ổn định, Little's Law:

\[
L=\lambda W,
\]

với `L` là số work trung bình trong hệ, `λ` là completed throughput và `W` là thời gian trung bình. Nếu hoàn thành 1.000 requests/s và mỗi request mất 50 ms, số requests in-flight trung bình có thể khoảng 50 theo phạm vi đo tương ứng.

Đây là trung bình; bursts, retries, queue và biến động arrival làm giá trị thực khác. Khi rate nhận > rate xử lý liên tục, **queue tăng**; thêm threads không chắc giải nếu điểm nghẽn nằm tại DB/capacity.

## 8. Chỉ số ứng dụng: request success phải có nghĩa nghiệp vụ

Một API `POST /reservations` trả HTTP 200 có thể không đồng nghĩa giữ hàng thành công nếu payload chứa trạng thái `REJECTED`. Ngược lại HTTP 504 sau khi source commit có thể là **unknown outcome**, không phải bằng chứng write thất bại.

Nên đo:

- `business_operation_total{operation,outcome}` với outcome thuộc tập nhỏ: accepted, rejected, unknown, failed.
- Idempotency-key duplicate attempts và replays.
- Conditional write conflicts hoặc optimistic concurrency failures.
- Invalid state transitions.
- Tenant authorization failures (không log raw identity trong metric label).
- Queue wait và backlog theo work type.
- Source write result reconciliations khi timeout.

**HTTP status và business outcome là hai trục khác nhau.** Giám sát NoSQL theo nghiệp vụ phải thể hiện cả hai, nếu không retry storm có thể làm requests trông thành công nhưng duplicate effects vẫn xảy ra.

## 9. Chỉ số ứng dụng: cache và read model

Một ứng dụng có cache trước NoSQL:

~~~mermaid
flowchart LR
    A["GET"] --> K{"Cache L1/L2"}
    K -->|Hit| R["Response"]
    K -->|Miss| DB["NoSQL"]
    DB --> K
~~~

Các metric:

- Cache hit/miss ratio **theo nhóm dữ liệu**.
- L1 hit, L2 hit, source miss tách riêng.
- Cache GET/SET/invalidate p95/p99.
- Cache pool connections và timeouts.
- Cache evictions, memory usage, hot key pressure.
- Số concurrent fills per key, stampede/coalescing effectiveness.
- Source read QPS phát sinh từ cache misses.
- Data age/version mismatch hoặc stale responses theo contract.
- Reporting projection lag/watermark nếu đọc dữ liệu dẫn xuất.

**Hit rate cao không đủ:** 99% cache hits có thể che 1% misses rất chậm, hoặc hit trả dữ liệu cũ trái nghiệp vụ. Phải theo dõi end-to-end p99 và correctness.

## 10. Chỉ số ứng dụng: thread pool, executor và event loop

Đối với Java/Spring hoặc runtime tương tự:

- Active threads, configured max, queued tasks.
- Queue wait duration và task execution duration.
- Rejected task count.
- Event loop lag/blocking duration trong runtime bất đồng bộ.
- HTTP connection/server thread pool saturation.
- JVM heap, allocation rate, GC pauses, safepoints.
- Async callback/coroutine backlog.
- CPU time/thread và blocked/waiting thread count.

Nếu API p99 tăng trong khi DB server nhanh, có thể worker bị chờ executor queue trước khi driver được gọi. Một event loop bị chặn bởi serialize JSON lớn có thể khiến nhiều requests chậm mà DB không thay đổi.

Dùng **trace span** để xác định đoạn delay nằm trước DB call, không suy tất cả từ CPU trung bình.

## 11. Phân nhóm metrics ứng dụng theo operation

Không đặt metric label bằng URL thô:

~~~text
Bad:
  path="/orders/O1001"
  path="/orders/O1002"
  path="/orders/O1003"

Better:
  route="/orders/{orderId}"
  operation="order-get"
  status_class="2xx"
~~~

Nên phân theo nhãn **cardinality thấp**:

- Operation: get-order, list-products, reserve-stock.
- Logical route/template.
- Response class hoặc error type đã chuẩn hóa.
- Service/environment/region/zone nếu cần.
- Database operation category (get, query, scan, insert, update).
- Tenant tier (free/business) nếu số tiers nhỏ, thay vì tenant ID không giới hạn.

Không đưa order ID, user ID, SQL/CQL query thô, raw filter, token, exception message hoặc stack trace vào metric labels. Những trường có cardinality cao thuộc **tracing/logs có kiểm soát và redaction**, không phải time-series tags.

## 12. Driver không chỉ là cầu nối network

NoSQL driver/SDK thường thực hiện:

- Connection pooling, keepalive và DNS/endpoint discovery.
- Load balancing, topology/leader/shard routing.
- Serialization/deserialization và request buffering.
- Timeouts, retry/backoff và error categorization.
- Server selection và failover.
- Batching, pipelining hoặc multiplexing.
- Consistency/read preference/transaction context theo API.
- TLS handshake và authentication refresh.

Vì thế cần tách **application timer** và **driver timer**. Một request có thể bị timeout khi **chưa gửi được lệnh tới server**, ví dụ pool exhausted. DB metrics không ghi nhận những requests chưa đến.

## 13. Chỉ số driver: connection pool và thời gian lấy connection

Một bộ metric cơ bản:

| Metric | Câu hỏi |
|---|---|
| Pool maximum/size | Pool có bao nhiêu connections khả dụng? |
| Active/in-use | Bao nhiêu connections đang làm việc? |
| Idle | Bao nhiêu connections không dùng? |
| Waiters/pending acquisition | Có request xếp hàng chờ pool? |
| Acquire latency histogram | Đợi connection mất bao lâu ở p95/p99? |
| Acquire timeout/rejections | Request bị loại khi pool cạn? |
| Connection created/closed | Có churn/reconnect bất thường? |
| TLS handshakes/auth failures | Có làm connection establishment chậm? |
| Connection max lifetime/idle expiry | Có nhiều connection đổi cùng lúc? |
| Per-endpoint pool distribution | Một node/endpoint bị dồn connection? |

Ví dụ:

~~~text
pool.max = 50
pool.active = 50
pool.waiting = 400
pool.acquire.p99 = 700 ms
server.query.p99 = 15 ms
~~~

Khả năng cao request chậm **do chờ lấy connection**. Nhưng nguyên nhân gốc vẫn có thể là queries kéo dài, nguồn chậm khiến connections giữ lâu, pool quá nhỏ hoặc ứng dụng rò connections. Không chỉ tăng pool lên 500: có thể đẩy quá nhiều requests tới DB và làm nghẽn server.

## 14. Driver: phân biệt timeout theo giai đoạn

Các timeout có thể phát sinh ở những nơi khác nhau:

| Loại timeout | Lúc nào xảy ra? | Điều phải kiểm tra |
|---|---|---|
| HTTP deadline | Client/gateway không đợi nữa | Total request budget |
| Application operation timeout | Toàn nghiệp vụ quá thời gian | App queue + các DB calls |
| Pool acquire timeout | Chưa mượn được connection/slot | Pool wait, active, max |
| Server selection timeout | Không tìm được host hợp lệ | Topology, DNS, failover |
| Connect/TLS timeout | Chưa lập được transport | Network/handshake/auth |
| Socket/read timeout | Chờ phản hồi sau khi gửi | Network/server/unknown write outcome |
| Driver command timeout | Thao tác DB vượt giới hạn SDK | Phạm vi timer cụ thể |
| Transaction timeout | Giao dịch vượt budget | State/commit outcome |

Không coi `socketTimeout=500ms` là deadline toàn request. Nếu SDK retry ba lần hoặc app phải đợi pool, tổng thời gian có thể lớn hơn nhiều.

Một write timeout sau khi đã gửi lệnh **có thể đã commit**, vì vậy lỗi phải được phân loại unknown outcome khi phù hợp và giải bằng idempotency key hoặc authoritative lookup thay vì gửi một write business mới vô điều kiện.

## 15. Driver: retries, backoff và load amplification

Một logical read có thể sinh nhiều physical attempts:

~~~text
API GET R1
  -> DB attempt 1: timeout 200 ms
  -> backoff: 100 ms
  -> DB attempt 2: transient unavailable
  -> backoff: 200 ms
  -> DB attempt 3: success 40 ms
~~~

Server query cuối chỉ mất 40 ms, nhưng user đã chờ lâu hơn 540 ms.

Theo dõi:

- Logical operations/s và physical attempts/s.
- Retry count per logical request, retry success/failure rate.
- Error class dẫn tới retry: timeout, throttle, leader switch, network.
- Backoff latency và tổng retry budget.
- Speculative/hedged requests nếu có.
- Retry amplification trên một cluster hoặc hot partition.
- Unknown write outcomes và kết quả đối soát.

Một tỷ lệ hữu ích:

\[
A=\frac{\mathrm{physical\ attempts}}{\mathrm{logical\ operations}}.
\]

Nếu có 1.000 logical operations/s nhưng 1.600 attempts/s, `A=1,6`. Khi source đã overload, retries không giới hạn có thể khiến nó quá tải nặng hơn.

~~~mermaid
flowchart TD
    A["Server chậm"] --> B["Driver timeout"]
    B --> C["Retry dồn dập"]
    C --> D["Tải server tăng"]
    D --> A
~~~

Cần exponential backoff có jitter, retry budgets, deadlines, circuit breaker/admission control và idempotency đúng semantics. Conditional business conflict không phải lỗi luôn nên retry.

## 16. Driver: topology, server selection và read routing

Driver có thể chọn primary, secondary, host trong local DC, leader, coordinator hoặc endpoint managed tùy hệ.

Metrics hữu ích:

- Server selection wait/error.
- Discovery/topology refresh time.
- Number of healthy/unhealthy hosts.
- Connection churn và reconnect rate sau failover.
- Client-selected region/DC/AZ, local-vs-remote calls.
- Read preference/consistency level theo operation.
- Load balancing skew theo host.
- Cross-region network latency/retries.
- DNS/TLS/auth refresh errors.

Nếu một thao tác bị route sang region khác, round trip có thể tăng mạnh trong khi **server execution time không đổi**. Nếu driver đang tìm node hợp lệ, request có thể chậm trước khi server nhận lệnh.

Đường đọc từ replica eventual không mặc nhiên có read-your-writes; metrics về topology phải được đối chiếu với contract consistency của API.

## 17. Driver: kích thước payload và serialization

Quan sát:

- Request/response bytes, item count.
- Encode/decode duration và CPU allocation.
- Compression ratio và CPU compression.
- Batch size/count, batch latency và partial failure.
- Page count và continuation token requests.
- Buffered bytes, streaming queue, backpressure.
- Network send/receive queue, pending responses.

Một truy vấn trả 20.000 documents có thể được server chuẩn bị tương đối nhanh, nhưng client vẫn mất nhiều thời gian truyền và decode hàng chục MiB. Nếu API chỉ dùng tên và trạng thái, **projection, limit và keyset pagination** thường hiệu quả hơn tăng pool size.

## 18. Driver: phân loại lỗi giúp biết đường sửa

| Error class | Tín hiệu | Hành động |
|---|---|---|
| Input/serialization | Invalid query/data shape | Sửa code/input |
| Authentication/authorization | Expired credential, denied | Kiểm tra secrets/roles |
| Pool exhausted | Acquire timeout | Pool waiting/active, slow holders |
| Topology/selection | No suitable endpoint | Failover/DNS/cluster health |
| Network/TLS | Reset/handshake/timeout | Network/OS/connectivity |
| Throttling | Capacity exceeded | Quota, hot partition, rate |
| Conditional conflict | Compare-and-set failed | Business concurrency |
| Storage/resource | Disk full, OOM, unavailable | Node/OS/storage |
| Unknown write outcome | Timeout sau gửi write | Reconcile/idempotency |

Một CAS thất bại vì hai requests tranh cùng entity có thể là kết quả nghiệp vụ bình thường, không phải outage. Ngược lại node down, pool reset hoặc DNS failures cần alert vận hành. Dùng metric labels theo **error category ổn định**, không theo raw error message.

## 19. Máy chủ NoSQL: throughput, service time và query work

Ở server, quan sát:

- Reads/writes/queries/scans per second.
- Service latency histogram theo operation.
- Active operations và pending queue.
- Rejections/throttled operations.
- Query plans, scanned records/bytes, returned records.
- Write amplification và index maintenance.
- Hot shard/partition throughput distribution.
- Compaction/repair/index rebuild impact.
- Long-running queries và cancellations.

**Server service time khác driver round-trip** vì driver tính cả network/queue/decode và có thể nhiều attempts. Cần đối chiếu cùng operation ID/time window khi điều tra.

### 19.1. Scan cost không bằng số rows trả

Một admin aggregation quét 10 triệu documents rồi trả 20 rows vẫn là truy vấn nặng.

Chỉ số định hướng:

\[
\mathrm{scan\ amplification}=
\frac{\mathrm{rows\ examined}}{\max(1,\mathrm{rows\ returned})}.
\]

Không phải mọi NoSQL engine có metric này, và cách tính scanned/index keys khác nhau. Dùng query plan, index selectivity, data scanned, per-partition fan-out tương ứng sản phẩm.

## 20. Máy chủ NoSQL: index và query planner

Theo dõi:

- Index hit/miss và kích thước/index residency.
- Documents/keys examined so với returned.
- Collection/table scan count.
- Query plan changes, plan cache churn.
- In-memory/disk sort, aggregation spill.
- Secondary index update lag nếu có.
- Index write amplification.
- Queries không target partition/shard key.
- Index build/rebuild background load.

Nếu API chậm sau khi thêm một filter mới, hãy xem query plan trước khi tăng tài nguyên. Có thể filter làm mất khả năng dùng index hoặc gây scatter-gather.

Không đưa raw query chứa email, tokens, giá trị người dùng vào metrics có nhãn. Dùng normalized query shape hoặc query hash, logs/traces được kiểm soát và redaction.

## 21. Máy chủ NoSQL: hot partition và phân phối tải

Một cluster có CPU trung bình 45% vẫn có một shard 98%:

~~~text
Shard A CPU:  18%
Shard B CPU:  27%
Shard C CPU:  98%   <-- hot owner
Shard D CPU:  37%
~~~

Theo dõi QPS, bytes, throttles, coordinator fan-out, partition sizes và replica placement **theo node/shard/range**. Một tenant hoặc một partition key hot có thể tạo p99 cao chỉ cho một nhóm người dùng.

Không tăng nodes một cách mù quáng nếu mọi traffic vẫn dồn vào một partition key. Cân nhắc key bucketing, đổi schema access pattern, cache hot read, giới hạn write bursts hoặc tách tải báo cáo.

Không xuất mọi userId/orderId thành nhãn metric: dễ nổ cardinality. Dùng top-K diagnostics hoặc sampled traces có bảo vệ dữ liệu.

## 22. Máy chủ NoSQL: replication và consistency

Những tín hiệu cần:

- Replication lag theo time/bytes/offset với semantics rõ.
- Replica apply backlog, catch-up rate.
- Leader election/failover count nếu áp dụng.
- Quorum availability và requests lỗi vì thiếu replicas.
- Repair/anti-entropy/pending mutations/hinted handoff nếu có.
- Cross-region traffic và network retry.
- Rebalance/reshard tiến độ.
- Stale read violations nếu có synthetic test.

Một lag 5 giây có thể chấp nhận với dashboard nhưng không phù hợp cho read-your-writes. **Lag=0 không tự bảo đảm API đọc đúng**: driver có thể route khác, index lag hoặc consumer bỏ event.

Liên kết replica lag với consistency/read preference của từng operation, thay vì chỉ nhìn một số lag trung bình.

## 23. Máy chủ NoSQL: compaction, flush, WAL và write amplification

Với storage engine dạng LSM tree, writes đi qua commitlog/WAL, memtable/SSTables rồi flush/compaction.

Theo dõi khi engine hỗ trợ:

- Memtable size/flush tasks pending.
- SSTable/segment count và kích thước.
- Compaction queue, bytes read/written và duration.
- Tombstone scan/drop counts.
- WAL/commitlog fsync latency và backlog.
- Storage read/write amplification.
- Disk free, indexing pressure và repair load.

Ví dụ:

~~~text
Writes stable at 2.000/s
Compaction backlog grows for hours
Disk write p99 increases
Read p99 increases due to SSTable/tombstone scans
CPU remains near 55%
~~~

Đó có thể là storage bottleneck, không phải CPU. Giải pháp phải dựa vào compaction/data layout/TTL/tombstone/indexing behavior cụ thể, không chỉ tăng thread count.

## 24. Máy chủ NoSQL: memory, page cache và internal caches

Theo dõi:

- Internal block/buffer/index cache hit/miss, evictions.
- Cache occupancy, read-through misses.
- Heap, off-heap/direct memory, RSS.
- GC pause và allocation rate nếu JVM.
- Page faults, dirty pages, writeback pressure.
- Process OOM/restarts.
- Memory fragmentation và limit headroom.

Cache vừa được warm thường làm read p99 tốt; sau restart/failover, cold cache khiến disk reads tăng. Không gộp OS page cache với internal DB block cache như thể cùng một bảng cân đối. Cần đo phạm vi mỗi cache.

## 25. Máy chủ NoSQL: queue và saturation

Một DB có nhiều hàng đợi:

- Pending requests/active commands.
- Coordinator/thread pool queues.
- Flush, compaction, repair queues.
- Indexing/bulk write queues.
- Network backlog.
- Admission control rejections/throttling.

Khi arrival vượt service capacity, queue tăng và latency tăng. Tăng queue capacity có thể chỉ trì hoãn lỗi; cần giảm nguồn work, tối ưu truy vấn, tăng năng lực thật hoặc đặt giới hạn.

**Latency tăng + throughput không tăng + queue kéo dài** là pattern saturation quan trọng, nhưng vẫn cần xác minh CPU, disk, contention và request mix.

## 26. Background work là nguồn contention dễ bị quên

Những hoạt động nền có thể ảnh hưởng request foreground:

- Snapshot/backup/export.
- Compaction/cleanup.
- Cluster rebalance/resharding.
- Index build/reindex.
- Repair/anti-entropy.
- CDC replay/backfill.
- Expiration/TTL cleanup.
- Search segment merge.
- Admin report scans.

Đánh dấu deployment, failover và maintenance windows trên dashboard. Nếu p99 tăng cùng thời điểm một job index build bắt đầu, đó là manh mối; phải đo shared I/O/CPU/queue để kiểm chứng.

Background jobs cần **quota, khả năng tạm dừng và stop condition theo OLTP SLO**, không chỉ “chạy lúc ít người dùng”.

## 27. Hệ điều hành: CPU utilization chưa nói hết

Những metric quan trọng:

- CPU user/system utilization theo core và process.
- Load average hoặc runnable thread queue, hiểu tương quan với core count.
- CPU saturation: run queue length, scheduler wait.
- CPU steal time trên VM nếu được công bố.
- Context switches và thread migration.
- Cgroup/container CPU quota throttling.
- CPU time của application, driver và DB process.
- IRQ/softIRQ load khi network/disk traffic cao.

Ví dụ:

~~~text
Host has 16 cores.
CPU average utilization: 48%.
DB process uses heavy CPU on 1 busy thread.
That core reaches 100%.
One shard/request queue becomes saturated.
~~~

CPU trung bình 48% **không loại trừ một thread/core bị khóa**. Một query coordinator hoặc event loop có thể là điểm nghẽn đơn luồng. Ngược lại CPU cao nhưng requests vẫn đạt SLO chưa chắc là sự cố.

Đối chiếu CPU với throughput, pending queues và p99 để xác định saturation; không dùng 70% làm ngưỡng tuyệt đối cho mọi nền tảng.

## 28. Hệ điều hành: memory pressure, RSS và swap

Cần theo dõi:

- RSS của process và memory được container cấp.
- Working set/anonymous/file-backed memory, OS page cache.
- Available memory và reclaim activity.
- Major/minor page faults.
- Swap in/out (nếu được bật).
- OOM kills và process/container restarts.
- Memory limit/cgroup OOM events.
- Direct/off-heap allocations và mapped files.
- Kernel slab/socket buffers khi liên quan.

Lý giải:

- **RSS tăng** chưa chắc memory leak; database có thể dùng mmap/page cache.
- **Page cache được dùng** không đồng nghĩa RAM “bị chiếm vô ích”; đây có thể là data path bình thường.
- **Major page faults/swap-in tăng cùng p99** gợi ý storage reads hoặc memory pressure.
- **OOMKilled** là tín hiệu hard failure, nhưng cần xác định OOM thuộc container nào.

Nếu một NoSQL JVM process heap dùng 4 GiB trong container limit 5 GiB, phải xét **off-heap, thread stacks, page cache và native buffers**. Không đặt heap = toàn bộ container memory rồi ngạc nhiên khi bị OOM.

## 29. JVM GC: đọc pause và allocation đúng phạm vi

Nếu application hoặc database chạy JVM, cần:

- Heap used/committed/max.
- GC count/time theo collector.
- Pause time histogram (p95/p99 nếu đo được).
- Allocation rate (bytes/s).
- Live set, old-gen pressure.
- Promotion failures/GC overhead.
- Safepoint pauses nếu runtime cung cấp.
- Thread count và direct buffer usage.
- OOM/heap dump events có kiểm soát.

Ví dụ:

~~~text
HTTP p99 spikes to 800 ms every 3 minutes.
DB server command time stays around 15 ms.
Application stop-the-world pauses reach 600 ms.
Request latency spikes align with GC pauses.
~~~

Tình huống này có thể do application GC, không phải DB. Nếu GC pause nằm trên database JVM, server p99 cũng có thể tăng. Cần phân biệt **process JVM nào** phát sinh pause và có cùng cửa sổ thời gian không.

Không suy từ GC count đơn thuần; nhiều collections ngắn có thể ít ảnh hưởng hơn một pause dài. Phần lớn thu thập cần overhead thấp, không tự bật logging cực chi tiết trên production vô thời hạn.

## 30. Disk: throughput, IOPS, await và queue

Các tín hiệu OS/storage:

- Reads/s và writes/s (IOPS).
- Bytes read/write per second.
- Read/write latency distribution và average await.
- Disk utilization/busy time, biết semantics với NVMe/parallel disks.
- Outstanding I/O/queue depth.
- Device errors và filesystem errors.
- Free capacity/inodes.
- Filesystem writeback, dirty pages.
- Fsync/write flush latency.
- Burst/credit limits trong cloud volumes nếu có.
- Storage throttling hoặc latency do shared tenancy.

Một disk có throughput chưa cao vẫn có I/O p99 xấu nếu requests nhỏ, random hoặc queue bị nghẽn. Disk utilization 100% trên một số thiết bị không tự nói hệ đã hết throughput theo mọi nghĩa; cần xem queue, latency và workload.

### 30.1. Tách read I/O, write I/O và compaction

Một NoSQL LSM store có thể tạo I/O nền:

~~~text
Foreground writes:  100 MiB/s
Compaction reads:   250 MiB/s
Compaction writes:  220 MiB/s
Total device work:  >500 MiB/s
~~~

Nếu chỉ nhìn application writes 100 MiB/s, khó hiểu vì sao disk bị bão hòa. Kết hợp OS disk metrics và server compaction/flush metrics sẽ giải thích **write amplification**.

## 31. Network: latency, retransmissions và kết nối

Theo dõi:

- Network receive/transmit bytes/s và packets/s.
- Packet drops, errors, retransmissions.
- TCP connect/reconnect/reset rate.
- RTT distribution theo vùng/endpoint.
- Socket send/receive queue, accept backlog.
- TLS handshakes và failures.
- DNS lookup duration/errors.
- MTU issues/fragmentation khi có dấu hiệu.
- Cross-zone/region traffic và egress cost.
- Connection counts, TIME_WAIT/CLOSE_WAIT nếu liên quan.

Ví dụ:

~~~text
DB command p99 at server:     12 ms
Driver round-trip p99:       320 ms
Pool acquire p99:             10 ms
TCP retransmissions:      elevated
Cross-region RTT:         elevated
~~~

Có thể cần điều tra network path, route, NAT/gateway, TLS hoặc cross-region traffic. Nhưng **TCP retransmissions tăng là dấu hiệu**, không luôn chứng minh chúng là nguyên nhân duy nhất. Đối chiếu các connections bị ảnh hưởng và các mốc thời gian.

## 32. Container/Kubernetes: metrics host và container có thể khác

Với containerized application/database, xem:

- Container CPU usage **và CPU throttled periods/time**.
- Requested vs limited CPU/memory.
- Pod restarts, OOMKilled, CrashLoopBackOff.
- Node allocatable vs pod resource requests.
- Ephemeral storage quota, volume capacity.
- Pod networking latency/drops/errors.
- HPA/VPA changes, autoscaling lag.
- Pod evictions và scheduling pending duration.
- Readiness/liveness probes và connection churn sau restart.
- Cgroup memory events và filesystem writeback.

Một pod bị giới hạn 1 CPU có thể bị **cgroup throttling** dù host có 32 cores và CPU toàn host chỉ 20%. Khi ứng dụng tăng p99, chỉ xem host CPU sẽ bỏ lỡ container quota.

### 32.1. Autoscaling có thể làm điểm nghẽn chuyển tầng

Thêm 20 application pods làm API xử lý nhiều requests hơn, nhưng mỗi pod tạo pool 50 connections:

\[
20\times 50=1.000\ \text{connections tiềm năng}.
\]

Nếu DB trước đó chỉ chịu 200 active calls hợp lý, scale app có thể tạo một retry/pool storm. Đo aggregate connections per database node, client concurrency và source QPS sau autoscale; không chỉ xem CPU mỗi pod giảm.

## 33. Hệ điều hành: file descriptors, ports và clock

Các giới hạn thường ít thấy trên dashboard:

- Open file descriptors vs ulimit.
- Socket count và ephemeral port exhaustion.
- DNS resolver cache/timeout.
- Clock synchronization và time jumps.
- TLS certificate expiry/rotation.
- Kernel OOM logs, disk filesystem errors.
- Process restarts và service manager events.

Clock skew làm log timestamps giữa application/driver/DB server khó so chính xác. Trong tracing, timestamps có thể bị lệch; nên dùng monotonic clock để đo duration trong cùng process, đồng thời theo dõi NTP/clock sync health để liên kết giữa nodes.

**Không dùng timestamp wall-clock làm cơ sở duy nhất xác định ordering giao dịch phân tán.** Nó phục vụ quan sát, không thay commit/causal order của database.

## 34. Dịch vụ NoSQL managed: những metric OS có thể không lộ

Trong một managed database, người dùng thường không có root trên DB host nên chỉ thấy metrics mà dịch vụ công bố:

- Request count/latency và errors.
- Provisioned/consumed capacity hoặc quota usage.
- Throttling, hot partition diagnostics (nếu có).
- Replication/index lag.
- Storage/backup usage.
- Network data transfer.
- Connection counts hoặc system load ở mức cung cấp.
- Service events/maintenance/failover.

Không được **bịa tên metric OS** như `db_disk_await_p99` nếu dịch vụ không xuất metric đó. Trong trường hợp thiếu server/OS telemetry, dùng:

1. Application + driver histograms.
2. Service/managed database metrics chính thức.
3. Controlled probe hoặc synthetic transaction.
4. Query profiling/logs được nhà cung cấp hỗ trợ.
5. Hỗ trợ vendor và service health events khi có incident.

Chỉ số có thể đổi tên, độ phân giải hoặc nghĩa theo phiên bản/tier/region. Ghi rõ data source và sampling granularity trên dashboard.

## 35. MongoDB: phối hợp operation, replication và host metrics

Một MongoDB deployment có các nhóm quan sát có thể lấy từ những giao diện/monitoring phù hợp:

- Command/operation counts và latency.
- Query profiler/slow query logs theo giới hạn và quyền.
- `docsExamined`/`keysExamined`, sort/spill và query plan.
- Current operations, connections, queued work.
- WiredTiger cache, dirty bytes, eviction activity.
- Replication lag/oplog window và election events.
- Shard targeting, scatter-gather, chunk migration.
- Disk I/O và memory/container host.
- Driver connection pool, command monitoring và server selection.

Ví dụ: API GET chậm nhưng profiler thấy execution 12 ms, driver acquire p99 500 ms và server connections cao. Hướng điều tra phù hợp là pool/connection churn/active slow holders trước khi tối ưu index.

Nếu một collection scan từ admin báo cáo làm WiredTiger cache bị đẩy ra, point reads có thể chậm do tăng disk reads; cần nhìn cache miss + read I/O + query plan cùng thời gian.

**Không bật full query profiling ở mức cao trên production vô hạn** mà không xét overhead và dữ liệu nhạy cảm trong log. Dùng sampling/scope hợp lý.

## 36. Cassandra/ScyllaDB: coordinator, partition và repair

Các nhóm tín hiệu phù hợp với kiến trúc wide-column:

- Read/write latency và throughput tại coordinator/replica theo khả năng.
- Client request timeouts/unavailables và consistency level.
- Pending tasks/thread pools, mutations queued.
- Compaction pending, SSTables, memtables, flush.
- Tombstones scanned per query và large partition warnings.
- Bloom filter/cache behavior và disk reads.
- Repair/streaming/hinted handoff backlog khi có.
- Speculative execution/retries tại driver.
- Hot partition/range và per-node skew.
- JVM GC đối với triển khai sử dụng JVM, hoặc runtime/allocator tương ứng với engine.

Ví dụ:

~~~text
CQL read p99 increases.
NoSQL coordinator pending tasks rise.
Tombstone scanned per query spikes.
Disk read latency also rises.
Application connection pool wait increases afterward.
~~~

Khả năng query phải đọc nhiều tombstones hoặc gặp compaction/read amplification. Root cause có thể là TTL/delete/data model, **không chỉ connection pool quá nhỏ**.

Driver consistency level và token-aware routing quyết định request đi đâu. Không lấy CPU trung bình cluster làm proxy cho một partition hot.

## 37. DynamoDB: capacity và throttling cần gắn với API

Khi dùng DynamoDB, các nhóm metrics chính:

- SuccessfulRequestLatency hoặc latency service theo operation, đúng tên/nguồn mà tài khoản cung cấp.
- Read/write request rates và consumed capacity.
- Provisioned capacity/utilization nếu dùng mode đó.
- Throttled requests/events và các nguyên nhân được dịch vụ cung cấp.
- Conditional check failures, phân biệt conflict bình thường với lỗi vận hành.
- System errors, user errors và retry attempts ở SDK.
- GSI update/query behavior và index usage/lag theo khả năng công bố.
- Scan/parallel scan consumed capacity.
- Hot partition/partition key diagnostics nếu công cụ hỗ trợ.
- Streams iterator age hoặc backlog cho CDC consumer khi sử dụng.

Một table có 90% tổng capacity chưa chắc mọi partition key đều đọc không throttle. Một hot key có thể chạm ràng buộc nội bộ; cần nhìn key distribution/access patterns và throttle reasons.

**SDK client latency có thể cao hơn service request latency** do local queue, network và retries. Với managed service, driver + API + provider metrics đặc biệt quan trọng vì OS của service không trực tiếp hiển thị.

## 38. Redis: event loop, hot keys và eviction

Redis thường có độ trễ thấp với operations đơn giản, nhưng cần theo dõi:

- Command rate và latency distribution.
- Slow log/latency diagnostics được hỗ trợ.
- Connected clients, blocked clients, rejected connections.
- Network in/out, output buffer usage.
- Used memory, fragmentation ratio.
- Evicted/expired keys và keyspace hit/miss.
- CPU per instance/core và event loop pressure.
- Persistence/replication lag hoặc AOF/RDB impact nếu được bật.
- Hot key/large value patterns và cluster slot skew.
- Failover/reconnection và client retry/load.

Một `GET` có p99 cao không luôn do Redis command execution: network, pool wait hoặc serialization bên app có thể chiếm thời gian. Ngược lại một command phức tạp chạy lâu có thể chặn các requests khác trên server process.

**Eviction và TTL expiration khác nhau.** Entry có thể bị đẩy khỏi cache vì RAM trước khi TTL hết, tạo miss storm lên NoSQL source.

## 39. Elasticsearch/OpenSearch: search fan-out và indexing pressure

Khi một NoSQL-adjacent search index phục vụ read model:

- Search requests/s và p95/p99.
- Shard-level search queue/rejections.
- Query vs fetch phase khi công cụ hỗ trợ.
- Indexing throughput, refresh, merge pressure.
- Heap/GC, fielddata/request cache, circuit breakers.
- Shard count, replica placement và hot shards.
- Disk watermarks, segment count và I/O.
- Bulk indexing partial errors.
- Snapshot/reindex/background tasks.
- Read model lag so với source-of-truth CDC.

Một search aggregation có thể trả 20 buckets nhưng quét nhiều shards và tăng heap. Nếu query dùng cùng cluster phục vụ người dùng, cần cô lập batch analytics hoặc giới hạn concurrency.

Search query latency không chứng minh index đã mới sau khi source ghi; freshness/CDC lag là một **chỉ số khác**.

## 40. Bản đồ dấu hiệu để định hướng nguyên nhân

| Quan sát kết hợp | Giả thuyết ban đầu | Kiểm tra tiếp |
|---|---|---|
| HTTP p99 cao, driver pool wait cao, server p99 thấp | Pool saturation/leak/slow holders | Active connections, thread dump, in-flight ops |
| HTTP p99 cao, app GC pause lớn, DB p99 thấp | Application GC | Heap allocation, pauses, request traces |
| Driver RTT cao, server execution thấp, TCP retransmits tăng | Network path | RTT, route, drops, DNS/TLS |
| Server p99 cao, disk queue và compaction backlog cao | Storage contention | I/O latency, SSTable/tombstones, background jobs |
| Cluster CPU trung bình thấp, một shard 100% | Hot partition | Key distribution, shard routing |
| Read p99 cao sau failover, cache misses cao | Cold cache | Disk reads, warm-up, failover events |
| API timeout tăng, retry amplification tăng | Retry storm | Physical attempts, backoff, throttle reasons |
| Driver server selection failures, elections tăng | Topology/availability | Node health, leader/DC routing |
| Source reports current, dashboard stale | CDC projection lag | Consumer offset, watermark, DLQ |
| HTTP 200 cao nhưng business rejects tăng | Domain-level failure | Conditional conflicts, invariants, outcome ledger |

Đây là **bảng giả thuyết**, không phải chẩn đoán chắc chắn. Hai sự cố có thể cùng xảy ra, hoặc một triệu chứng là hậu quả của nguyên nhân khác. Sử dụng traces và điều kiện thay đổi có kiểm soát để phân biệt.

## 41. Correlation: cùng thời gian, cùng thao tác, cùng phạm vi

Muốn suy luận nguyên nhân, các biểu đồ phải có **time window và scope tương thích**:

- Cùng khoảng thời gian, múi giờ và độ phân giải.
- Cùng environment/region/cluster.
- Cùng service, operation và nhóm status.
- Cùng node/shard/endpoint khi điều tra hotspot.
- Cùng read preference/consistency class nếu có.
- Cùng load mix hoặc traffic level.

Ví dụ:

~~~text
10:00-10:05 UTC:
  GET /orders/{id} p99 rises to 850 ms.
  Driver acquire p99 rises to 500 ms.
  Driver in-use equals configured max.
  MongoDB execution p99 remains at 18 ms.
  App pool waiting spikes.
~~~

Dữ liệu cùng thời gian ủng hộ giả thuyết pool saturation. Cần kiểm tra các requests đang giữ connections, liệu server có slow operations riêng và pool size/traffic có đổi hay không.

### 41.1. Correlation không phải causation

Một đường CPU tăng cùng lúc với p99 **chưa chứng minh CPU gây ra p99**. Có thể p99 tăng trước, làm requests giữ threads lâu, rồi CPU tăng vì retries; hoặc một compaction job gây I/O contention và CPU tăng như hậu quả.

Để phân biệt, tìm **thứ tự xuất hiện, traces có cùng lỗi, deployment annotations, nhóm không bị ảnh hưởng**, hoặc thí nghiệm thay đổi có kiểm soát trong môi trường được phép.

## 42. Distributed tracing: đi từ HTTP span tới DB attempt

Một trace minh họa:

~~~text
Trace: GET /orders/{orderId} [820 ms]
  AuthN/AuthZ [7 ms]
  OrderService.lookup [805 ms]
    Cache.GET [3 ms, MISS]
    DB.logicalOperation [786 ms]
      Driver.poolAcquire [490 ms]
      DB.attempt#1 [22 ms, TIMEOUT/NETWORK]
      Retry.backoff [250 ms]
      DB.attempt#2 [24 ms, SUCCESS]
  SerializeResponse [5 ms]
~~~

Từ một biểu đồ p99 của HTTP, ta tìm các **slow exemplars/traces** để biết giai đoạn gây trễ. Span cần ghi:

- Operation name đã chuẩn hóa.
- Service và logical database name.
- Peer host/region trong phạm vi an toàn và cần thiết.
- DB operation type và sanitized query shape nếu cho phép.
- Outcome/error category.
- Retry attempt count.
- Pool wait và query round trip nếu driver hỗ trợ.
- Sampling flag và trace/span IDs.

Không ghi raw credentials, token, payload khách hàng, email hoặc dữ liệu bí mật vào span attributes. **Tracing có sampling**: nếu có 1/1.000 traces, một lỗi hiếm có thể không được thấy; dùng metrics tổng làm sự thật về tần suất, traces cho minh chứng đường đi.

## 43. Structured logs: thông tin cần để ghép sự kiện

Một bản ghi log có cấu trúc, giả định đã được ẩn dữ liệu riêng tư:

~~~json
{
  "ts": "2026-11-14T10:00:12.320Z",
  "level": "WARN",
  "service": "order-api",
  "operation": "order-get",
  "traceId": "ab12cd34",
  "requestId": "req-1001",
  "dbOperation": "get",
  "dbErrorClass": "pool_acquire_timeout",
  "elapsedMs": 420,
  "attempts": 0,
  "environment": "production"
}
~~~

Tại đây `attempts=0` gợi ý chưa gửi physical attempt tới DB, nên server profiler không nhất thiết thấy request. Một log khác có `attempts=3` và throttling sẽ có hướng điều tra khác.

Các tiêu chí:

- Timestamp chuẩn, độ lệch clock được theo dõi.
- Trace/request correlation IDs.
- Error class chuẩn hóa; không lộ raw exception chứa data.
- Operation/route template, không ghi business IDs tùy ý.
- Actor/tenant context chỉ khi cần và có policy bảo vệ.
- Sampling/rate limiting logs để không làm I/O/chi phí log bùng nổ.
- Security log/audit trail tách khỏi debug log.

Log không thay metrics vì một sự cố throughput cao có thể sinh hàng triệu dòng; metrics giúp biết quy mô, logs/traces giúp xem ví dụ cụ thể.

## 44. OpenTelemetry/Micrometer: tư duy instrument theo logical operation

Với Java, có thể dùng instrumentation framework để thu histograms/counters, nhưng nguyên tắc quan trọng là **đo đúng ranh giới**. Một wrapper đơn giản dùng Java chuẩn để minh họa:

~~~java
import java.util.concurrent.TimeUnit;

public final class MeasuredOrderLookup {
    public interface OrderRepository {
        String readById(String id) throws Exception;
    }
    public interface MetricsSink {
        void recordDuration(
            String operation, String outcome, long nanos);
        void increment(String metric, String outcome);
    }

    private final OrderRepository repository;
    private final MetricsSink metrics;

    public MeasuredOrderLookup(
            OrderRepository repository, MetricsSink metrics) {
        this.repository = repository;
        this.metrics = metrics;
    }

    public String getOrder(String id) throws Exception {
        long start = System.nanoTime(); // monotonic duration
        String outcome = "success";
        try {
            return repository.readById(id);
        } catch (Exception e) {
            outcome = "failed";
            metrics.increment("order_lookup_error", "failed");
            throw e;
        } finally {
            metrics.recordDuration(
                "order-get", outcome, System.nanoTime() - start);
        }
    }
}
~~~

Điều đoạn mã **đo được** là thời gian của lời gọi repository, có thể bao gồm driver pool/network/DB/deserialize. Nó **không tự đo riêng DB server execution**. Muốn biết pool wait và physical attempts cần thêm hook/timer từ driver hoặc trace spans bên trong.

Một triển khai production sẽ chọn thư viện metric/tracing phù hợp, dùng histogram buckets đúng SLO, giới hạn nhãn và tránh ghi order ID thành label. Không tính duration bằng cách lấy hai `Instant.now()` và hy vọng wall-clock không nhảy.

### 44.1. Mẫu tên metrics và labels

Một schema logic:

~~~text
http.server.request.duration
  labels: service, route, method, status_class

db.client.operation.duration
  labels: service, db_system, operation, outcome

db.client.pool.acquire.duration
  labels: service, pool, outcome

db.client.retry.total
  labels: service, operation, reason

nosql.projection.lag.seconds
  labels: pipeline, source, region
~~~

Tên thực tế phụ thuộc Prometheus/OpenTelemetry/Micrometer exporter và quy ước đơn vị. **Chỉ là schema đề xuất, không khẳng định driver nào cũng phát ra các tên này.**

## 45. Prometheus: tính rate và phân vị từ histogram

Nếu hệ xuất Prometheus histogram `http_request_duration_seconds_bucket` với nhãn `route` và `le`, một truy vấn định hướng cho p99 theo route:

~~~promql
histogram_quantile(
  0.99,
  sum by (le, route) (
    rate(http_request_duration_seconds_bucket[5m])
  )
)
~~~

Một error ratio nếu counter có nhãn `outcome="error"`:

~~~promql
sum(rate(http_requests_total{outcome="error"}[5m]))
/
clamp_min(sum(rate(http_requests_total[5m])), 1)
~~~

**Đây là ví dụ cho classic histograms và các metric tự định nghĩa**. Tên nhãn/metric thực tế, native histograms và cách exporter biểu diễn cần điều chỉnh. `clamp_min` ở denominator có thể che trường hợp traffic gần 0; dashboard/alert phải xét sample count đủ lớn để không rút kết luận từ số liệu mỏng.

### 45.1. Không tính p99 từ trung bình của per-pod p99

Sai về nguyên tắc:

~~~text
avg(p99_of_pod_A, p99_of_pod_B, ...)
~~~

Phân vị toàn hệ phải tổng hợp phân phối hoặc histogram buckets trên cùng metric unit/boundaries, rồi mới ước lượng percentile. Kết quả `histogram_quantile` cũng là **ước lượng theo bucket resolution**; bucket quá thô quanh SLO làm cảnh báo sai hoặc không nhạy.

### 45.2. Rate, increase và reset counter

Một counter có thể reset sau restart. Dùng `rate()`/`increase()` theo đúng semantics Prometheus thay vì lấy hai sample trừ nhau trực tiếp, rồi coi giá trị âm là lỗi nghiệp vụ. Với một traffic spike rất ngắn, cửa sổ 5 phút có thể che burst; có thể dùng nhiều windows nhưng cần cân bằng noise.

## 46. Dashboard 4 tầng: một màn hình để khoanh vùng

Một dashboard hữu dụng có thể chia vùng rõ:

| Vùng | Biểu đồ | Câu hỏi |
|---|---|---|
| **Impact** | API SLO p95/p99, errors, business failures | Người dùng bị gì? |
| **Traffic** | Requests/s, operation mix, top tenants/tier | Tải có đổi? |
| **Client** | Driver pool wait, retries, timeouts, bytes | Chậm trước DB hay sau DB? |
| **Server** | Query p99, active ops, scan/index, shard skew | DB đang làm gì? |
| **Replicas** | Lag, elections, repair | Consistency/topology có đổi? |
| **Host** | CPU per core, disk latency, memory/GC, network drops | Resource bottleneck? |
| **Background** | Backup/compaction/replay/index jobs | Có work cạnh tranh? |
| **Data quality** | Cache stale/CDC watermark/unknown writes | Correctness có ảnh hưởng? |

Giữ panel phản ánh **đơn vị và phạm vi**: ms hay seconds, avg hay p99, process hay node, region nào. Đặt deployment/failover annotations cùng timeline.

Một dashboard có quá nhiều biểu đồ không được nhóm sẽ khiến người vận hành tìm chậm hơn; ưu tiên tuyến truy vết **user impact → client wait → DB work → OS pressure**.

## 47. Alert: từ ảnh hưởng người dùng tới nguyên nhân hỗ trợ

Những cảnh báo nên gắn hành động:

| Alert | Tiêu chí ví dụ | Hành động đầu tiên |
|---|---|---|
| API error-budget burn | Error/timeout cao trong windows xác định | Xác định impacted operations |
| Checkout p99 beyond SLO | Tail latency vượt ngưỡng và đủ samples | Mở trace và pool/DB overlays |
| Driver pool acquire p99 high | Pool wait tăng + waiters nhiều | Kiểm tra in-use/slow holders |
| Retry amplification high | Physical/logical attempts tăng | Kiểm tra throttle/errors/backoff |
| DB throttling sustained | Throttles tăng và source p99 tăng | Giảm load, hot partitions |
| Replication lag beyond contract | Replica lag vượt freshness budget | Route/lag/CDC source |
| Disk pressure | I/O queue/latency cao, free disk thấp | Storage/compaction/backup |
| JVM GC pause regression | Pause xấu cùng API/server p99 | Heap/alloc/GC tuning |
| CDC watermark stale | Oldest unprocessed age tăng | Consumer/backpressure/retention |
| OOM/restarts | Pod/process killed hoặc crash-loop | Memory/cgroup/limits |

Các ngưỡng chỉ là ví dụ: **không có ngưỡng ms/CPU chung** cho mọi NoSQL workload. Đặt alert dựa trên baseline, SLO, traffic volume và failure impact.

Tránh mỗi metric vượt ngưỡng là một page riêng: khi disk full có thể kích hoạt 20 alerts ở app/driver/server. Nên có correlation/grouping để một incident dẫn tới một runbook trung tâm.

## 48. Sampling, retention và chi phí observability

Thu thập chỉ số cũng tiêu CPU, memory, network và tiền. Cần phân lớp:

- **Metrics aggregated:** độ phân giải phù hợp, tags cardinality thấp, giữ đủ lâu cho trend.
- **Traces sampled:** giữ slow/error traces nhiều hơn nếu hệ hỗ trợ, cân nhắc bias khi thống kê.
- **Logs selective:** ghi lỗi, security events, slow queries với redaction và quota.
- **Profiling on-demand:** khi incident hoặc thử nghiệm, không bật overhead cao mãi.
- **Histograms:** chọn buckets quanh SLO cần kiểm tra.
- **Long-term trends:** downsample có kiểm soát khi cần giữ nhiều tháng.

Một endpoint tạo một metric series per orderId có thể tạo hàng triệu time series, làm observability backend tốn hơn NoSQL và gây cardinality exhaustion. Bài toán “tăng độ chi tiết” phải cân bằng **chi phí và khả năng trả lời câu hỏi**.

### 48.1. Biết cái gì không đo được

Một managed DB có thể không cho thấy per-core CPU hoặc raw disk await. Không tự điền bằng 0 hoặc suy từ request latency. Ghi rõ **data gap** trên dashboard và dùng telemetry phía driver, managed service metrics, synthetic probes để giới hạn giả thuyết.

## 49. Một quy trình chẩn đoán theo tầng

Khi người dùng báo “ứng dụng chậm”, làm theo thứ tự:

1. **Khoanh vùng ảnh hưởng:** endpoint, tenant tier, region, time window.
2. **Xác nhận SLI:** p50/p95/p99, error/outcome, traffic volume.
3. **Tách queue app:** request có chờ executor/event loop không?
4. **Tách driver:** pool acquire, server selection, retries, bytes sent/received.
5. **So server service time:** truy vấn nào chậm, node/shard nào, scan/index?
6. **Kiểm tra replicas/consistency:** election/lag/route/throttling.
7. **Kiểm tra OS:** CPU saturation, GC, disk I/O, memory pressure, TCP drops.
8. **Kiểm tra work nền:** compaction, reindex, backup, CDC replay.
9. **Tìm một trace đại diện và đối chứng** của request nhanh/chậm.
10. **Đưa giả thuyết có thể kiểm chứng**, không thay đổi nhiều thứ cùng lúc.
11. **Mitigate an toàn:** giảm report/replay, chặn retry storm, scale đúng bottleneck.
12. **Xác minh sau thay đổi:** cùng workload, p99/end-to-end outcome và không phát sinh data correctness issues.

Nếu vấn đề có tính đa nguyên nhân, có thể phải xử lý nhiều lớp. Ví dụ server disk chậm làm connection giữ lâu, khiến driver pool đầy; tăng pool chỉ giảm một triệu chứng trong ngắn hạn và có thể đẩy thêm tải vào disk.

## 50. Runbook A — API p99 cao nhưng database query nhanh

Tình huống:

~~~text
GET /orders/{id} p99:        780 ms
DB server command p99:       16 ms
Driver pool acquire p99:    510 ms
Driver waiters:              300
Pool active/max:           50/50
Driver retries:              low
~~~

Các bước:

1. Xác nhận là cùng API/region/time window.
2. Xem trace: thời gian chờ pool có chiếm phần lớn không?
3. Xem vì sao 50 connections bị giữ: slow queries hiếm, streams, leaks, long transactions, batch jobs, read preference/node routing.
4. Kiểm tra pool cap và application concurrency; đừng mở max connections không giới hạn.
5. Kiểm tra DB node saturation trước khi tăng pool.
6. Tách pool cho heavy report và giao dịch nếu chúng dùng chung.
7. Đặt bounded acquisition deadline/admission control, trả lỗi có kiểm soát khi quá tải.
8. Đo lại p99, pending acquisition và DB I/O sau thay đổi.

Điểm học: server trả command nhanh **không có nghĩa user không chờ database path**; driver có thể là nút cổ chai.

## 51. Runbook B — Server p99 cao cùng compaction và disk I/O

Tình huống:

~~~text
Read p99:                35 ms -> 450 ms
Write QPS:               không đổi
Disk read await:         tăng rõ rệt
Compaction pending:      tăng liên tục
SSTable count:           tăng
Driver retries:          tăng sau khi p99 xấu đi
Source CPU average:      55%
~~~

Các bước:

1. Xác định table/collection, node, partition bị ảnh hưởng.
2. Đối chiếu compaction/flush task bắt đầu từ lúc nào.
3. Xem tombstone scans, partition sizes và read amplification.
4. Kiểm tra disk queue, free space, filesystem errors và throughput.
5. Xem có backup, repair hoặc index rebuild cạnh tranh I/O không.
6. Giảm hoặc pause background work **nếu an toàn theo engine và runbook**.
7. Giới hạn retries, batch scan, report load để tránh overload ngược.
8. Xem lại TTL/data model/index cho giải pháp dài hạn.
9. Đo lại p99 và backlog sau mitigation.
10. Không chỉnh compaction hoặc xóa storage files thủ công khi không hiểu recovery semantics.

Đây là trường hợp **OS/disk và server storage metrics** có giá trị hơn CPU trung bình.

## 52. Runbook C — Tăng timeout do replication failover

Giả sử:

~~~text
Leader election count:     tăng
Driver server selection:   chậm
Connection created/s:      tăng đột biến
Replica lag:               tăng
API error:                 timeout/unknown write outcome
CPU:                       vẫn bình thường
~~~

Cách tiếp cận:

1. Đọc service/cluster events để xác định failover có thật.
2. Xác định driver có refresh topology đúng và chọn endpoint phù hợp không.
3. Xem pool reconnection/TLS/auth có tạo burst không.
4. Phân loại retry cho reads idempotent, writes có unknown outcome.
5. Kiểm tra quorum/consistency và availability theo business contract.
6. Giảm rate/retry storm, dùng deadline và jitter.
7. Không hạ consistency hoặc ép read stale cho bước xác nhận giao dịch để “cứu latency”.
8. Đối soát các write outcomes chưa rõ bằng stable operation/idempotency IDs.
9. Theo dõi replica catch-up và cache cold reads sau failover.
10. Ghi sự kiện, thời gian hồi phục và số requests ảnh hưởng.

Một timeout không phải lúc nào là lỗi “query quá phức tạp”; failover/topology có thể làm request chưa bao giờ đến server được chọn.

## 53. Runbook D — Hot key, throttling và retry amplification

Giả sử:

~~~text
Application requests:       4.000/s
SDK physical attempts:      9.000/s
DynamoDB/source throttles:  tăng
One partition or tenant:    chiếm phần lớn requests
Average cluster CPU:        không cao
~~~

Hướng chẩn đoán:

1. Phân loại operation/key access pattern, không log raw keys nếu nhạy cảm.
2. Tính amplification = attempts/logical operations.
3. Xem reason của throttle, service capacity và per-key skew.
4. Kiểm tra các clients có cùng retry policy, backoff/jitter không.
5. Giảm retry budget, thêm rate limit và backpressure.
6. Nếu hot read, cân nhắc cache phù hợp với freshness contract.
7. Nếu hot write, xem lại partitioning, bucketing, batching và invariant.
8. Tránh tăng concurrency để che throttling.
9. Đo business error/unknown outcomes và không làm mất write safety.
10. Xác nhận sau sửa: attempts/request, throttles, p99 và source capacity.

Nguyên nhân gốc có thể là **key distribution**, còn retry storm là yếu tố khuếch đại, nên cần giải cả hai.

## 54. Quy trình quan sát khi rollout thay đổi NoSQL

Trước khi đổi driver, index, schema, cache hoặc pool:

- Ghi baseline 24 giờ hoặc các cửa sổ tải đại diện (tùy traffic).
- Chọn operation/region/tenant tier và SLO cần bảo vệ.
- Xem p50/p95/p99, errors, retry amplification, pool wait.
- Đo query execution, index scan, hot partitions và OS.
- Đánh dấu deployment/version trên dashboard.
- Triển khai canary theo một tập traffic có khả năng đại diện.
- Theo dõi trong những khoảng warm-up, peak và background jobs phù hợp.
- Chuẩn bị rollback nếu business outcome hoặc performance xấu.
- So metrics trên **request mix và capacity tương đương**.
- Không kết luận cải thiện từ một median tốt hơn trong khi p99 xấu đi.

Có thể dùng trace exemplars trước/sau để biết thay đổi rút thời gian ở tầng nào. Nếu driver version mới làm connection churn tăng, chỉ nhìn DB server p99 có thể không phát hiện regression.

## 55. Bài thực hành A — Tách latency budget

Một API `GET /products/{id}` có trace:

~~~text
Total request:              620 ms
Application queue:           30 ms
Driver pool acquire:        380 ms
DB round trip:               28 ms
Retry backoff:              150 ms
Decode/serialize:            22 ms
Other routing/network:       10 ms
~~~

Hãy:

1. Kiểm tra các phần có cộng khớp tổng trong ví dụ không.
2. Giai đoạn nào chiếm phần lớn thời gian?
3. Chỉ số DB server service time 14 ms có làm thay đổi kết luận không?
4. Cần thu metric pool nào để xác minh?
5. Nếu pool active=max, nguyên nhân có thể là pool nhỏ hay DB request giữ lâu?
6. Tăng pool max gấp đôi có rủi ro gì?
7. Nếu retries do throttling, tăng pool có giúp không?
8. Vẽ một trace span tree cho request này.
9. Đề xuất hai mitigation không làm tăng DB overload.
10. Đặt SLI và một bài kiểm tra canary sau thay đổi.

## 56. Bài thực hành B — Phân biệt CPU, disk và GC

Có dữ liệu giả định:

| Tín hiệu | Giá trị khi bình thường | Khi sự cố |
|---|---:|---:|
| API GET p99 | 90 ms | 900 ms |
| DB CPU trung bình | 43% | 48% |
| DB disk await | 4 ms | 110 ms |
| Compaction pending | 2 | 850 |
| DB heap used | 65% | 68% |
| DB GC pause p99 | 12 ms | 14 ms |
| Server read latency p99 | 24 ms | 700 ms |

Yêu cầu:

1. Tầng nào có tín hiệu bất thường rõ nhất?
2. Vì sao CPU trung bình chưa đủ loại trừ bottleneck?
3. Trong bảng này, GC có phải giả thuyết chính không? Vì sao?
4. Compaction pending liên quan disk latency thế nào?
5. Các bảng/partitions nào cần điều tra trước?
6. Việc bật backup đồng thời có thể ảnh hưởng gì?
7. Có nên tăng mọi thread pools ngay không?
8. Đề xuất một thao tác giảm tải an toàn để kiểm chứng.
9. Chọn 5 metric cần theo dõi sau mitigation.
10. Nếu p99 hồi phục khi tạm ngưng report scan, điều đó chứng minh tới mức nào?

## 57. Bài thực hành C — Retry storm và unknown write outcomes

Dữ liệu:

~~~text
Business reservation rate:         400 intents/s
Driver physical write attempts:    950 attempts/s
Timeout after send:                 8% of intents
Conditional conflicts:             15% of intents
Success responses:                 70% of intents
Remaining outcomes:                unknown / other
~~~

Hãy:

1. Tính attempt amplification.
2. Tại sao physical attempts không thể được dùng để đếm số reservations được cấp?
3. Conditional conflict có phải outage không?
4. Timeout sau send có chắc chắn write thất bại không?
5. Idempotency key nên được gắn vào intent nào?
6. Khi client retry cùng key, server phải trả outcome thế nào?
7. Chọn metrics để phân loại accepted/rejected/unknown.
8. Nếu driver tự retry ba lần và app cũng retry ba lần, số attempts có thể tăng thế nào?
9. Cần cảnh báo nào khi retries tăng và throttling tăng đồng thời?
10. Một bài load test nào chứng minh p99 cải thiện mà không oversell?

## 58. Bài thực hành D — Thiết kế dashboard bốn tầng

Bạn phụ trách một API tra cứu NoSQL có cache và nhiều region. Hãy thiết kế dashboard gồm:

1. Request rate theo route template và region.
2. API p95/p99 và error-budget burn.
3. Business outcome (accepted/rejected/unknown).
4. Cache L1/L2 hit/miss và data-age.
5. Driver pool utilization/wait p99.
6. Driver retry amplification và error classes.
7. DB server query p99/scan amplification.
8. Node/shard QPS/CPU skew.
9. Replication lag/quorum health.
10. Disk I/O, memory/GC và network errors.
11. Background compaction/backfill annotations.
12. Traces/log examples cho requests chậm.

Với mỗi panel, ghi **đơn vị, metric type, aggregation window, allowed labels và hành động khi bất thường**. Chỉ ra ba nhãn có cardinality cao cần tránh và cách dùng trace/log thay thế.

## 59. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách làm đúng |
|---|---|---|
| “CPU thấp thì database không chậm” | I/O, lock, hot shard, queue có thể nghẽn | Quan sát USE và phân phối theo node |
| “DB command 10 ms nên API phải gần 10 ms” | App/driver/network/retries tạo thêm delay | Trace end-to-end |
| “Average latency thấp thì người dùng ổn” | Tail p95/p99 có thể rất cao | Histogram và SLO |
| “Lấy trung bình p99 từng pod là p99 tổng” | Quantiles không cộng trung bình | Merge histograms/sketches phù hợp |
| “HTTP 200 là giao dịch thành công” | Business outcome khác transport | Đo accepted/rejected/unknown |
| “Timeout là write thất bại” | Write có thể đã commit | Idempotency/outcome reconciliation |
| “Tăng pool luôn tăng throughput” | Có thể đẩy overload sang server | Đo active/wait + source capacity |
| “Driver retry giúp mọi lỗi” | Có thể khuếch đại overload/duplicate effect | Retry budgets, idempotency |
| “Server latency bằng round-trip của SDK” | Pool, network, decode khác nhau | Tách timers |
| “Mọi errors nên cộng chung” | CAS rejection khác node unavailable | Error taxonomy |
| “Result ít rows thì query rẻ” | Có thể quét rất nhiều rows | Plan/scan amplification |
| “CPU cluster trung bình mô tả hotspot” | Một shard có thể bão hòa | Per-node/partition metrics |
| “Replica lag thấp nghĩa luôn đúng consistency” | Route/read policy khác nhau | Consistency contract + validation |
| “Host CPU bình thường nên pod không bị throttle” | Container CPU quota riêng | Cgroup throttling |
| “Memory RSS cao luôn là leak” | Page cache/mmap/caches bình thường | Working set, reclaim, OOM |
| “GC count cao luôn gây p99 xấu” | Pause duration mới quan trọng | GC pause histogram |
| “Disk throughput thấp không thể nghẽn disk” | Latency/IOPS/queue có thể giới hạn | Disk await và pending I/O |
| “Một metric label cho mỗi order giúp debug” | Nổ cardinality và lộ dữ liệu | Template labels + trace IDs |
| “Traces đã sample đủ thay metrics tổng” | Lỗi hiếm có thể bị bỏ | Metrics cho rates, traces cho ví dụ |
| “Database managed lúc nào cũng có OS metrics” | Provider có giới hạn telemetry | Dùng SDK/provider metrics |
| “Một dashboard toàn biểu đồ là đủ” | Thiếu correlation và hành động | SLI → driver → server → OS |
| “Alert mọi metric vượt ngưỡng” | Page storm, thiếu ưu tiên | SLO/burn-rate + runbook |
| “Tăng timeout là cách khắc phục” | Chỉ kéo dài thời gian giữ tài nguyên | Tìm bottleneck và overload guard |
| “Thay đổi p99 sau deploy chắc do deploy” | Có thể traffic/background job khác | Đối chứng, scope, timeline |
| “Đọc replica luôn mới như source” | Có thể eventual/lag | Watermark/version/consistency |
| “Cache hit rate cao là hệ khỏe” | Miss tail/stale data có thể hỏng | End-to-end latency/correctness |

## 60. Câu hỏi tự kiểm tra

1. Vì sao cần đo từ ứng dụng tới OS thay vì chỉ xem DB CPU?
2. Bốn lớp quan sát trong bài gồm gì?
3. SLI khác SLO ở đâu?
4. RED và USE giải các loại câu hỏi gì?
5. Counter, gauge và histogram khác nhau thế nào?
6. Vì sao không lấy mean của per-pod p99?
7. Phân biệt server execution và driver round-trip.
8. Pool acquire timeout có thể xảy ra trước khi server nhận request không?
9. Retry amplification là gì?
10. Khi write timeout sau send, business outcome có thể là gì?
11. Một logical operation có thể tạo nhiều physical attempts ra sao?
12. Driver topology selection có ảnh hưởng latency thế nào?
13. Thế nào là hot partition?
14. Vì sao CPU trung bình cluster có thể che hot shard?
15. Index scan amplification cần đo gì?
16. Tại sao 20 returned rows không chứng minh query rẻ?
17. Replication lag có quan hệ gì với read-your-writes?
18. Compaction backlog có thể làm read p99 tăng ra sao?
19. Memory page cache và heap có cùng ý nghĩa không?
20. JVM GC pause có thể giải thích API p99 ra sao?
21. Disk IOPS, throughput và await khác nhau thế nào?
22. TCP retransmission nên được ghép với metric nào?
23. Vì sao container có thể throttle khi host CPU thấp?
24. Autoscaling app pods có thể làm DB quá tải bằng cách nào?
25. Managed service có thể thiếu telemetry gì?
26. MongoDB profiler và driver pool metrics bổ trợ nhau ra sao?
27. Cassandra tombstone scans có thể gây loại latency nào?
28. DynamoDB consumed capacity khác logical request count thế nào?
29. Redis eviction khác TTL expiration thế nào?
30. Search indexing/refresh ảnh hưởng read model freshness ra sao?
31. Metric label cardinality là gì và vì sao nguy hiểm?
32. Nên đưa orderId và access token vào metrics không?
33. Distributed tracing cung cấp thông tin nào mà metrics không có?
34. Vì sao không nên chỉ dựa vào sampled traces để đếm error rate?
35. Một trace slow request nên có những span nào?
36. Prometheus histogram buckets phục vụ p99 như thế nào?
37. Cần làm gì khi clock giữa server và app bị skew?
38. Alert SLO khác alert CPU threshold ở đâu?
39. Vì sao cần đánh dấu deploy/backup/replay trên dashboard?
40. Những điều kiện nào chứng minh sửa được vấn đề thay vì chỉ dời bottleneck?

## 61. Tổng kết: quan sát cùng một request qua bốn tầng

**Quan sát NoSQL hiệu quả là liên kết biểu hiện của người dùng với thời gian chờ ở ứng dụng, cách driver chọn và gửi lệnh, công việc thật ở máy chủ, và tài nguyên nền của hệ điều hành.** Không có một biểu đồ đơn lẻ nào giải thích mọi sự cố.

Quy trình nhận diện:

~~~text
1. Xác định affected operation, region, user-visible SLO.
2. Đo rate, errors, p50/p95/p99 và business outcomes.
3. Tách app queue, cache hit/miss và runtime pauses.
4. Tách driver pool wait, topology wait, retries và round-trip.
5. Xem server query service time, scan/index cost và hot shards.
6. Kiểm tra replication, consistency và background jobs.
7. Xem CPU per core/cgroup throttle, memory/GC, disk/network.
8. Tìm trace/log minh chứng theo cùng time window.
9. Đặt giả thuyết có thể kiểm chứng; tránh đổi nhiều thứ cùng lúc.
10. Mitigate an toàn cho business correctness và source capacity.
11. Đo lại với workload tương đương và kiểm tra p99/outcomes.
12. Cập nhật dashboards, alerts, metric taxonomy và runbook.
~~~

Điểm quan trọng nhất là **latency người dùng không đồng nhất với latency câu lệnh trên server**; đồng thời **CPU trung bình không thay thế tín hiệu saturation, queue, I/O hoặc phân phối hot partition**. Khi đo đúng các ranh giới, người vận hành có thể xác định sự cố thuộc application, driver, database hay OS — và chọn biện pháp sửa dựa trên bằng chứng thay vì phỏng đoán.








