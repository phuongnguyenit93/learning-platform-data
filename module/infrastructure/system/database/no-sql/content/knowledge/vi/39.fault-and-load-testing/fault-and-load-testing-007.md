# Kiểm tra retry budget, circuit breaker và giới hạn đồng thời

Trong hệ thống Java sử dụng NoSQL phân tán, một sự cố database hiếm khi chỉ gây ra vài request lỗi rồi tự kết thúc. Một replica chậm có thể làm **request nằm chờ lâu hơn**, hàng đợi ở ứng dụng tăng, thread và connection pool cạn, gateway bắt đầu timeout, rồi nhiều tầng đồng loạt **retry** khiến cluster chịu tải lớn hơn ngay khi nó đang yếu nhất. Sự cố cục bộ biến thành **cascading failure**.

Ba cơ chế thường phối hợp để ngăn vòng xoáy này:

1. **Retry budget** — giới hạn số lần thử lại trên mỗi logical request và trên toàn dịch vụ/cửa sổ thời gian, chỉ retry lỗi được phép, trong deadline còn lại.
2. **Circuit breaker** — phát hiện dependency đang không khỏe, tạm ngừng gửi request vào nó, rồi thăm dò hồi phục có kiểm soát.
3. **Giới hạn đồng thời (concurrency limit/bulkhead)** — giới hạn số tác vụ cùng chiếm connection, thread, bộ nhớ hay năng lực NoSQL; từ chối/chờ ngắn khi đầy thay vì để hàng đợi phình vô hạn.

Đây không phải ba nút bật để “mọi request luôn thành công”. Chúng **thay đổi cách hệ thống thất bại**: trả kết quả hoặc lỗi đúng trong thời hạn đã cam kết, tránh retry không kiểm soát và giữ cho các chức năng còn hoạt động không bị kéo sập.

Bài học thuộc chương **Kiểm thử lỗi và tải** của module **Database No SQL**, đặt trọng tâm vào **cách chứng minh các cơ chế hoạt động dưới thử nghiệm load/fault**, đọc các chỉ số, hiểu những đánh đổi về tính đúng dữ liệu và triển khai Java có guardrails. Các ngưỡng minh họa trong bài không phải cấu hình production khuyến nghị cho mọi ứng dụng.

> **Nguyên tắc:** Một request không được tạo thêm tải vượt budget, không được tiếp tục chờ sau deadline, không được vượt giới hạn tài nguyên và không được thay đổi tính đúng của thao tác dữ liệu chỉ để tăng tỷ lệ trả HTTP 200.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **logical request**, **attempt**, **retry**, **timeout**, **deadline**, **backoff**, **jitter**, **retry budget** và **error budget**.
2. Tính **retry amplification** khi gateway, Java service, SDK và proxy đều tự retry.
3. Phân loại các lỗi NoSQL **retryable / conditionally retryable / non-retryable**, đặc biệt khi write có **unknown outcome**.
4. Thiết kế retry có **per-request attempt cap**, **global token budget**, **deadline propagation**, backoff có jitter và tôn trọng throttling hints.
5. Giải thích **circuit breaker CLOSED–OPEN–HALF_OPEN**, thời điểm mở, điều kiện thăm dò và cách tránh mở sai vì 404/business validation.
6. Phân biệt **circuit breaker** với **rate limiter**, **semaphore bulkhead**, **connection pool limit**, **queue bound**, **load shedding** và **adaptive concurrency**.
7. Dùng **Little's Law** để liên hệ arrival rate, latency và in-flight concurrency; lý giải vì sao latency tăng khiến tài nguyên cạn dù QPS không đổi.
8. Kết hợp đúng thứ tự **admission → deadline → circuit breaker → attempt concurrency → SDK call → retry decision**, không tạo double retry hoặc giữ permit khi backoff.
9. Thiết kế fault injection cho replica failover, timeout, latency spike, throttling, network partition, hot partition và recovery.
10. Xây SLI/SLO, dashboard, runbook và tiêu chí nghiệm thu bảo vệ **throughput, p99, correctness và dữ liệu**.

## 2. Tình huống xuyên suốt: Order API và NoSQL chậm

Một Java Order Service đọc/ghi Orders:

~~~text
Client
  -> API Gateway (timeout/retry policy)
  -> Order Service Java (HTTP thread pool)
  -> NoSQL Java SDK (connection pools / retry policy)
  -> NoSQL cluster (shards/replicas)
~~~

Giả sử trạng thái bình thường:

~~~text
Logical requests: 1,000 / second
Backend success latency p50: 35 ms
Backend success latency p99: 120 ms
API latency SLO: p99 <= 300 ms
DB availability: healthy
~~~

Một shard bắt đầu timeout:

~~~text
t0: latency for hot partition rises from 40 ms to 1.5 s
t1: Java requests remain in flight longer
t2: connection slots and threads become saturated
t3: HTTP clients time out, re-send requests
t4: Java layer retries, SDK also retries
t5: DB receives a retry storm at the worst possible time
~~~

Nếu mỗi tầng được phép tự retry ba lần mà không phối hợp, backend có thể thấy **nhiều attempts cho một thao tác nghiệp vụ**. Một lỗi transient có thể được sửa bằng một retry đúng thời điểm; retry không giới hạn lại có thể làm hệ không bao giờ kịp phục hồi.

### 2.1. Đặt câu hỏi đúng trước khi “tăng retries”

- Lỗi do **chậm tạm thời** hay đang **quá tải kéo dài**?
- Request là **GET eventual**, **GET causal/strong**, **conditional write**, **counter increment** hay **transaction/payment**?
- Server có thể đã commit write trước khi client timeout không?
- Còn bao nhiêu milliseconds trong **deadline từ đầu request**?
- Bao nhiêu clients khác đang retry cùng shard?
- Có **phương án fail-fast** hoặc fallback **đúng về dữ liệu** không?
- Có thể giảm concurrency/queue để tránh chiếm toàn bộ tài nguyên không?

## 3. Logical request, attempt và các mốc thời gian

### 3.1. Một logical request có nhiều attempts

~~~text
Logical request R42: GET /orders/O900
  attempt #1: timeout after 80 ms
  wait:       25 ms backoff
  attempt #2: success after 40 ms
Result:      1 logical success, 2 backend attempts, 1 retry
~~~

Định nghĩa:

\[
\mathrm{attempts}=\mathrm{initialAttempts}+\mathrm{retryAttempts}
\]

Với một logical operation thực thi tuần tự thông thường:

\[
\mathrm{retryAttempts}=\max(0,\mathrm{attempts}-1)
\]

Đừng gọi `maxRetries=3` là `maxAttempts=3`: **3 retries** sau lần đầu có thể thành **4 attempts**. Các SDK khác nhau dùng tên và semantics riêng.

### 3.2. Timeout khác deadline

**Per-attempt timeout**: một lần gọi backend được chờ tối đa bao lâu.

**Overall deadline**: request nghiệp vụ được phép tiêu thụ tối đa bao lâu từ lúc bắt đầu, gồm xếp hàng, connect, attempt, backoff và chuyển vùng.

Nếu deadline là 250 ms:

~~~text
0 ms:    request arrives
20 ms:   admission/queue
20–100:  attempt #1
100–135: backoff
135–195: attempt #2
195–250: remaining budget for next action
~~~

Một retry bắt đầu ở 245 ms với timeout mới 200 ms có thể **vi phạm deadline**. Mỗi attempt cần min(per-attempt timeout, remaining deadline) và phải hủy/bỏ kết quả đúng khi hết hạn.

### 3.3. Timer wall-clock và monotonic clock

Đo timeout/deadline trong một process bằng **monotonic duration source**, như `System.nanoTime()` ở Java. Không lấy `System.currentTimeMillis()` để đo vài chục milliseconds khi wall clock có thể nhảy bởi NTP.

Khi truyền deadline xuyên services, dùng protocol có semantics rõ ràng cho propagated timeout, network transit và clock uncertainty; không trừ trực tiếp `nanoTime()` giữa hai JVM.

### 3.4. Deadline đã hết thì không retry

Một phép đo latency có thể thấy request #1 timeout sau 500 ms, nhưng API deadline chỉ 300 ms. Trong trường hợp đó, dù backend retry có thể thành công sau 100 ms nữa, **người dùng đã timeout** và request tiếp tục giữ tài nguyên, gây tải lãng phí.

## 4. Retry amplification: nhân tải khi nhiều tầng cùng retry

Giả sử các tầng dùng **max attempts**:

~~~text
Gateway:       3 attempts per incoming request
Java service:  3 attempts per gateway attempt
NoSQL SDK:     2 attempts per Java attempt
~~~

Trong tình huống xấu nhất mọi tầng đều retry tối đa:

\[
A_{\max}=3\times3\times2=18
\]

Với 1.000 logical requests/s từ khách:

\[
\lambda_{\mathrm{backend}} \le 18\,000 \ \mathrm{attempts/s}
\]

**Đây là upper bound lý thuyết** khi mọi retries được phát sinh và overlap trong khoảng quan sát; backoff/timeout có thể làm traffic dồn theo thời gian. Nhưng chỉ cần một phần amplification đã đủ làm database quá tải.

### 4.1. Sự khác biệt giữa `maxAttempts` và `maxRetries`

Nếu ba tầng cấu hình `maxRetries = 3, 3, 2` với lần thử đầu không tính, multiplier có thể là:

\[
(3+1)(3+1)(2+1)=48
\]

Việc đọc đúng tên tham số SDK quyết định risk profile.

### 4.2. Vì sao retry nhiều tầng phản tác dụng?

Gateway không biết Java service đang retry. Java service không biết SDK đang tự chuyển replica/retry. Cả ba đều muốn tăng success rate cục bộ nhưng **không tầng nào biết tổng workload và remaining deadline**.

### 4.3. Chỉ định một nơi điều phối retry

Một lựa chọn:

- SDK có những internal retry behaviors bắt buộc cho protocol/topology discovery, được **ghi nhận**.
- Java service kiểm soát **business-level logical operation retry** theo deadline và budget.
- Gateway **không tự retry unsafe writes** và chỉ retry requests được phép với idempotency.
- Toàn tuyến có maximum effort budget chung hoặc được phối hợp.

Không phải mọi ứng dụng đều nên tắt hoàn toàn retry SDK; với một số driver, retry đó là một phần hợp đồng xử lý failover. Cần audit và đặt **global bound** đủ nghiêm.

## 5. Retry budget: giới hạn attempts trên request và toàn hệ

Một **retry budget** giới hạn lượng công việc phát sinh do retry, thay vì chỉ nói “mỗi request thử tối đa ba lần”.

### 5.1. Tại sao per-request cap chưa đủ?

1.000 requests/s, mỗi request tối đa 3 attempts:

~~~text
Initial:  1,000 attempts/s
Retries:  up to 2,000 attempts/s
Total:    up to 3,000 attempts/s
~~~

Cap `maxAttempts=3` ngăn vòng lặp vô hạn từng request, nhưng khi toàn bộ cluster lỗi, **3.000 backend attempts/s vẫn có thể là overload**.

### 5.2. Global retry budget

Ví dụ policy:

~~~text
Allow retry attempts <= 10% of admitted initial attempts
measured over a rolling time window, with a bounded burst.
```

Với 1.000 original admitted requests/s:

\[
\lambda_{\mathrm{retry}}\le 100 \ \mathrm{attempts/s}
\]

Trong tình huống cùng cửa sổ ổn định:

\[
\lambda_{\mathrm{total}}\lesssim 1\,100 \ \mathrm{attempts/s}
\]

Đây là **mục tiêu thiết kế**; token-bucket refill/burst và phân tán clients có thể tạo spikes. Phải đo actual **backend attempts**, không chỉ số lần gọi retry của application.

### 5.3. Token bucket cho retries

~~~text
Initial request admitted:
  maybe credit retry tokens by defined policy

Before each retry:
  consume one available token
  if no token -> fail or return controlled fallback
```

Giới hạn:

- Có token capacity để cho phép một burst nhỏ.
- Refill gắn với legitimate original traffic hoặc clock rate theo chính sách.
- Tránh cấp retry tokens **theo chính retry attempts**, nếu không sẽ tự nuôi vòng lặp.
- Cấp budget theo service/dependency/operation/tenant khi cần, không cho một hot tenant dùng hết.

### 5.4. Local budget vs distributed budget

Nếu 20 Java pods, mỗi pod có local budget 10 retry/s, tổng có thể là **200 retry/s**, chưa kể autoscale lên 40 pods. Một local limiter không tự là global cap khi fleet size thay đổi.

Có thể dùng per-pod share có coordination/adjustment, distributed budget hoặc proxy/mesh controls; nhưng một distributed rate limiter cũng có latency/availability trade-offs. Thiết kế phải rõ scope:

~~~text
Budget scope: per API instance?
             per JVM?
             per service fleet?
             per NoSQL cluster?
             per region?
             per partition/tenant?
~~~

### 5.5. Retry budget không phải SLO error budget

**Error budget** là lượng request failures được phép theo reliability objective (ví dụ availability 99,9%). **Retry budget** là lượng extra attempts được phép tạo để cố khắc phục lỗi. Một hệ có thể dùng hết retry budget để bảo vệ database **dù error budget đã cạn**; không thể vì user-facing errors tăng mà vô hạn retry.

## 6. Điều kiện một retry được phép xảy ra

Một retry an toàn cần qua nhiều gates:

~~~text
Operation is retry-eligible?
Failure class is retryable?
Write outcome known or idempotency protected?
Deadline has remaining budget?
Attempts < maxAttempts?
Global retry token available?
Circuit permits an attempt?
Concurrency permit available?
Backoff + jitter fits deadline?
~~~

Một điều kiện sai là đủ để **không retry**.

### 6.1. Lỗi thường có thể retry có điều kiện

| Dấu hiệu | Cách xử lý thường phù hợp | Điều kiện |
| --- | --- | --- |
| Transient network reset trước khi gửi request | Có thể thử lại | Xác nhận request chưa tới server nếu transport chứng minh |
| Failover/leader changed | Driver discovery + retry có giới hạn | Đúng mode/consistency, còn deadline |
| Server throttling / 429 / overload | Backoff theo hint, hoặc load shed | Không retry tức thì khi server quá tải |
| Temporary unavailable replica | Retry route khác theo SDK policy | Phải giữ consistency/read-your-writes |
| Per-attempt timeout | Outcome có thể unknown | Idempotency/outcome lookup với write |
| Request validation error | Không retry cùng payload | Cần client fix |
| Authorization/permission denied | Không retry mù | Trừ khi có một documented transient credential refresh path |
| Conditional write conflict | Không retry same stale expected version | Đọc lại/đổi business decision |
| Missing key / expected 404 | Không tính là dependency failure | Trả domain result theo contract |
| Partition/quorum unavailable | Có thể fail-fast | Không hạ consistency để “đỡ lỗi” |

Không lấy một bảng generic HTTP status để thay thế error classifications của NoSQL SDK.

### 6.2. `Retry-After` và server hints

Một số HTTP APIs hoặc managed NoSQL services phát throttling delay hints. Khi được hỗ trợ, kiểm tra hint, cap theo deadline và jitter policy; không giả định mọi SDK exposes cùng một `Retry-After` header.

### 6.3. Backoff có jitter

Một công thức thường dùng:

\[
d_k=\operatorname{Uniform}\left(0,\min(d_{\max},d_{\mathrm{base}}2^k)\right)
\]

trong đó \(k=0,1,\ldots\) là lần retry đã thực hiện. Đây là **full jitter exponential backoff**. Cần giới hạn overflow khi tính \(2^k\) và không vượt deadline.

Ví dụ `base=20 ms`, `cap=200 ms`:

| Retry | Khoảng chờ random có thể chọn |
| ---: | --- |
| 1 | 0–20 ms |
| 2 | 0–40 ms |
| 3 | 0–80 ms |
| 4 | 0–160 ms |
| 5+ | 0–200 ms |

Không dùng một delay cố định giống nhau cho 10.000 clients sau sự cố; đó là **thundering herd**.

## 7. Tính đúng dữ liệu khi retry write

**Retry write timeout** nguy hiểm hơn retry một GET thuần, vì server có thể đã commit.

### 7.1. Unknown outcome

~~~text
Client -> reserveInventory(orderId=O100)
Database commits reservation.
Response ACK lost due to network reset.
Client receives timeout.
~~~

Nếu client tự gửi `reserveInventory` lần nữa như một mutation mới, có thể giữ hàng hai lần.

### 7.2. Idempotency key

Một lựa chọn:

~~~json
{
  "operationId": "reserve-O100-v1",
  "orderId": "O100",
  "sku": "SKU-7",
  "quantity": 1
}
~~~

Source of truth ghi kết quả theo `operationId` có uniqueness/conditional semantics phù hợp. Retry cùng operation ID sẽ trả cùng outcome hoặc tra kết quả đã tồn tại, không tự thực thi effect thêm lần nữa.

### 7.3. Idempotent CRUD không đồng nghĩa toàn operation an toàn

`PUT document with same value` có thể idempotent về target state, nhưng:

- Trigger/outbox/webhook có thể phát lại.
- TTL/updatedAt/version mới có thể thay đổi.
- Counter increment có thể tăng lần hai.
- Payment/charge side effect có thể bị gọi lại.
- Conditional write có thể conflict vì lần đầu đã commit.

Vì vậy idempotency là thuộc tính **end-to-end business operation**, không chỉ câu lệnh database.

### 7.4. Conditional mutations

Một optimistic lock:

~~~text
Update Order O100 from version 10 to 11
only if current version == 10.
~~~

Nếu timeout rồi retry, có thể nhận conflict vì lần đầu đã thành công. Application phải **tra trạng thái mới/operation outcome**, không coi conflict là thất bại chắc chắn của business operation và gửi mutation khác.

### 7.5. Strong consistency không được bỏ để đổi lấy success rate

Nếu payment ledger cần writes acknowledged theo majority/conditional transaction contract, fallback từ `QUORUM` sang `ONE` chỉ vì breaker mở có thể làm rủi ro correctness thay đổi. Trả `503` có thể tốt hơn trả `200` cho một write chưa đạt durability contract.

## 8. Circuit breaker: ngừng thêm tải vào dependency đang lỗi

Circuit breaker thường quản lý ba trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: failure/slow-call threshold crossed
    OPEN --> HALF_OPEN: probe delay elapsed
    HALF_OPEN --> CLOSED: enough successful probes
    HALF_OPEN --> OPEN: failed probe / threshold crossed
~~~

### 8.1. CLOSED

Calls được phép đi qua, breaker thu số liệu failure rate, slow-call rate hoặc consecutive failures trong window theo policy. **CLOSED không có nghĩa backend chắc khỏe**; nó chỉ là trạng thái đang cho thử.

### 8.2. OPEN

Requests mới bị chặn nhanh (short-circuit), trả controlled error hoặc fallback **nếu fallback hợp lệ về dữ liệu**. Breaker không tự sửa database. Mục tiêu giảm load và giữ ứng dụng không bị mắc kẹt ở dependency lỗi.

### 8.3. HALF_OPEN

Cho **một số ít probes/requests** đi qua. Nếu lành, trở về CLOSED; nếu tiếp tục lỗi, mở lại. Không cho tất cả 5.000 pending requests đồng loạt vào backend ngay khi thời gian OPEN kết thúc.

### 8.4. Failure classification là trọng tâm

Không đếm mọi kết quả không phải HTTP 200 thành DB failure:

- `OrderNotFound` có thể là response nghiệp vụ hợp lệ.
- ConditionalConflict có thể là optimistic concurrency, không phải database outage.
- ValidationError không chứng minh NoSQL hỏng.
- QuorumUnavailable/Timeout/Throttling có thể có trọng số khác.

Nếu breaker mở vì quá nhiều 404, nó tự chặn cả reads hợp lệ và tạo outage giả.

### 8.5. Scope breaker

Một breaker toàn cluster có thể chặn mọi tenants vì **một shard nóng**. Scope quá nhỏ theo từng key tạo hàng triệu breakers khó quản lý. Chọn theo khả năng hỏng độc lập:

~~~text
per dependency
per cluster/region
per operation class (read/write)
per shard/route where SDK exposes reliable identity
per remote integration
~~~

Lưu ý riêng cho `read` và `write`: một cluster mất write quorum vẫn có thể hỗ trợ một số reads theo contract, nên một breaker chung cho mọi operation có thể gây **fail-closed rộng hơn cần thiết**.

### 8.6. Circuit breaker không thay timeout

Breaker cần các attempts hoàn tất hoặc được xác định failed/slow để thống kê. Nếu không có timeout, hàng nghìn calls có thể bị treo trong khi breaker vẫn CLOSED, vì chưa có đủ observations. **Deadline và concurrency guard vẫn cần**.

### 8.7. Sampling và ngưỡng

Một tỷ lệ lỗi 50% trên 2 requests không đáng tin như 50% trên 1.000 requests. Window size, minimum calls, throughput, slow-call duration và threshold phải được chọn dựa trên workload và false-positive/false-negative costs.

Các giá trị như `failureRateThreshold=50%`, `minimumNumberOfCalls=20`, `openFor=5s` chỉ là **tham số ví dụ**; test phải cho thấy chúng phù hợp SLA và pattern lỗi thật.

## 9. Giới hạn đồng thời: bulkhead và admission control

**Concurrency limit** đặt trần lên số công việc đang phục vụ tại một nơi:

~~~text
Java Order Service
  ├── Read API: max 120 in-flight DB calls
  ├── Critical writes: max 40 in-flight DB calls
  └── Background reports: max 10 in-flight DB calls
~~~

Đây là ví dụ phân chia tài nguyên theo workload, không phải một con số tối ưu chung. Giới hạn phải có **scope**: mỗi JVM, toàn service fleet, mỗi DB client pool, per shard/tenant hoặc mỗi downstream operation.

### 9.1. Semaphore bulkhead

Semaphore cho tối đa \(C\) tác vụ giữ permit:

~~~text
if permit available:
    execute attempt
    release in finally
else:
    reject quickly or wait only within queue/deadline budget
~~~

Giới hạn này hữu ích cho synchronous Java code; phải đảm bảo **mọi exit path** release permit, kể cả timeout/exception/cancel.

### 9.2. Thread-pool isolation

Một executor pool riêng cho background queries tránh analytics chiếm mọi threads của critical checkout. Nhưng thread pool có queue vô hạn vẫn có thể **giấu overload** trong hàng đợi và làm requests hết deadline trước khi chạy.

### 9.3. Connection pool limit

NoSQL SDK có max connections/channels và max requests per connection riêng. Chỉ tăng connection count có thể **không tăng throughput** nếu shard/storage/CPU đã bão hòa; ngược lại còn tăng context switching/auth/TLS overhead.

### 9.4. Rate limit khác concurrency limit

**Rate limiter** khống chế requests/second, thường tính theo arrival rate.

**Concurrency limiter** khống chế số requests đang nằm trong hệ cùng lúc.

Một backend có thể chịu 1.000 req/s khi latency 20 ms nhưng chỉ 100 req/s khi mỗi request giữ lock/connection 1 giây. QPS cap đơn lẻ không bảo vệ được số in-flight.

### 9.5. Little's Law

Với hệ đủ ổn định và các assumptions liên quan:

\[
L=\lambda W
\]

trong đó:

- \(L\): số công việc trung bình trong hệ.
- \(\lambda\): throughput/arrival rate bền vững (requests/s).
- \(W\): thời gian trung bình một công việc ở trong hệ (s).

Ví dụ ở 1.000 requests/s:

| Mean time in system | Mean concurrent requests \(L\) |
| ---: | ---: |
| 20 ms | 20 |
| 50 ms | 50 |
| 200 ms | 200 |
| 1 s | 1.000 |
| 2 s | 2.000 |

Nếu latency tăng từ 50 ms lên 1 giây mà request rate giữ nguyên, in-flight demand tăng **20 lần**. Đây là lý do concurrency caps quan trọng trong một sự cố latency.

**Cẩn trọng:** Little's Law không cho biết p99, không mô hình toàn bộ queue dynamics khi hệ không ổn định và không chứng minh capacity backend từ một trung bình. Dùng load tests đo saturation/queueing.

### 9.6. Hàng đợi phải có giới hạn

Một limiter cho 100 active calls nhưng có **100.000 pending calls** vẫn gây memory/thread pressure. Policy nên chỉ rõ:

~~~text
maxConcurrent = 100
maxPending = 200
maxQueueWait = 30ms
overallDeadline = 250ms
overflowAction = REJECT / SHED
~~~

Phải định nghĩa điều gì xảy ra với requests bị từ chối: HTTP 429/503 hoặc domain error theo API contract, metrics và optional retry hint. Không giữ queue lâu hơn business deadline.

### 9.7. Bulkhead cho critical vs non-critical

Ví dụ:

~~~text
Checkout reserve inventory:
  dedicated DB attempt budget
  strict no-stale decision
  small bounded queue

Analytics dashboard:
  separate bulkhead
  can shed / return last known approved snapshot
~~~

Tách tài nguyên giúp analytics outage không ngăn checkout; nhưng reservation vẫn phải dùng atomic/conditional source correctness, không đọc từ stale search cache để “trả nhanh”.

### 9.8. Concurrency cap per instance chưa phải global cap

20 pods × 100 permits/pod có thể tạo **2.000 simultaneous DB attempts**. Autoscale lên 40 pods → 4.000. Nếu cluster chỉ chịu 1.500 in-flight, per-pod cap phải được phối hợp với fleet sizing, admission và SDK pool topology.

### 9.9. Adaptive concurrency

Một adaptive limiter điều chỉnh \(C\) theo latency/load/queueing feedback; ví dụ giảm permits khi latency tăng bất thường, tăng thận trọng khi hệ hồi phục. Đây là một **control loop**, dễ oscillate nếu dùng tín hiệu trễ hoặc nhiều tầng cùng tự tăng. Cần test behavior dưới burst và failure/recovery; không tin thuật toán tự điều chỉnh luôn chọn ngưỡng đúng.

## 10. Phối hợp retry budget, circuit breaker và concurrency limit

Một luồng request có thể như sau:

~~~mermaid
flowchart TD
    A["Incoming logical request"] --> B{"Overall deadline remaining?"}
    B -->|No| END["Deadline exceeded"]
    B -->|Yes| C{"Admission / route budget available?"}
    C -->|No| SHED["Controlled rejection"]
    C -->|Yes| D{"Circuit permits attempt?"}
    D -->|No| OPEN["Short-circuit / valid fallback"]
    D -->|Yes| E{"Concurrency permit acquired within wait budget?"}
    E -->|No| SAT["Saturation rejection"]
    E -->|Yes| F["Perform one NoSQL SDK attempt"]
    F --> G["Release attempt permit"]
    G --> H{"Success?"}
    H -->|Yes| OK["Return result"]
    H -->|No| I{"Retry eligibility, deadline, attempts, token?"}
    I -->|No| ERR["Return classified error"]
    I -->|Yes| J["Backoff with jitter"]
    J --> B
~~~

Một production implementation có thể đặt **outer breaker** bao quanh toàn logical operation hoặc **inner breaker** cho mỗi attempt; hai lựa chọn tạo số liệu và hiệu ứng khác nhau. Phải xác định rõ counts, concurrency permits và tầng nào retry. Sơ đồ mô tả khái niệm chứ không chuẩn hóa thứ tự decorator của mọi library.

### 10.1. Không giữ permit khi ngủ backoff

Sai:

~~~text
acquire DB permit
  attempt #1 fails
  sleep(200ms) while holding DB permit
  attempt #2
release permit
~~~

Trong 200 ms chờ, permit **không phục vụ bất kỳ DB attempt nào**, làm giảm throughput và đẩy request mới vào queue.

Tốt hơn trong mô hình per-attempt bulkhead:

~~~text
acquire
  attempt #1
release
backoff with jitter (without DB permit)
acquire
  attempt #2
release
~~~

Tuy nhiên một **outer logical-request admission permit** có thể cần được giữ xuyên toàn operation để giới hạn số request contexts tồn tại, nếu đó là thiết kế đã chọn. Phân biệt **logical in-flight cap** với **backend attempt cap**.

### 10.2. Breaker OPEN có tiêu tốn retry token không?

Policy thường **không retry ngay một breaker OPEN**. Một rejected attempt không đi tới backend không cần xem là backend retry attempt, nhưng vẫn là logical outcome đáng đo. Định nghĩa counts rõ:

~~~text
logical_request
backend_attempt_sent
retry_token_spent
circuit_short_circuit
bulkhead_rejected
timeout_before_send
```

Nếu “retries” tăng mà không có backend attempts, telemetry đang gộp sai các loại sự kiện.

### 10.3. Không để circuit breaker và limiter cùng tạo feedback loop sai

Ví dụ local bulkhead trả `BulkheadFull`; nếu breaker đếm đó là lỗi **NoSQL server**, breaker có thể mở dù DB vẫn khỏe. Nên tách dependency attempts thực, local rejections, user cancellations và business errors.

### 10.4. Không retry rejections do local saturation một cách đồng bộ

Khi 50.000 requests bị local semaphore từ chối, clients retry tức thì sẽ tạo vòng overload. Có thể trả 429/503 với backoff hints, admission throttling và client retry budget; không tự thử `while (!permit) retry`.

### 10.5. Propagate cancellation

Khi client ngắt hoặc API deadline hết, Java service cần hủy pending work nếu SDK/protocol hỗ trợ, không bắt đầu retry mới và release local permits. Hủy local future không nhất thiết ngăn database write đã gửi commit, nên **unknown outcome** vẫn cần idempotency.

### 10.6. Fail-fast không phải lỗi thiết kế

Một controlled `503` sau 20 ms có thể tốt hơn giữ 2 giây rồi trả timeout khi downstream đang sập, đặc biệt nếu có load shedding ở client/gateway và dữ liệu không cho phép stale fallback. Mục tiêu là **bounded resource consumption + truthful outcome**, không phải 100% HTTP 200 bằng mọi giá.

## 11. Ngân sách thời gian end-to-end

Ví dụ Order API có deadline 300 ms:

| Giai đoạn | Budget minh họa |
| --- | ---: |
| Authentication/routing | 20 ms |
| Request queue/admission | 15 ms |
| Attempt 1 | 100 ms |
| Backoff 1 | 20 ms |
| Attempt 2 | 100 ms |
| Response serialization/network reserve | 25 ms |
| **Tổng** | **280 ms** |

20 ms còn lại làm safety margin. Nếu attempt #1 thực tế dùng hết 150 ms, không còn đủ 100 ms cho attempt #2 với các bước còn lại; phải **skip retry**.

### 11.1. Timeout ngân sách không được tính bằng bình quân p50

Nếu p50=40 ms nhưng p99=500 ms, đặt per-attempt timeout 40 ms có thể tạo rất nhiều **unnecessary retries** trong trạng thái tải cao. Timeout cần cân bằng false timeouts, backend service latency SLO, network variation và deadline; thử nghiệm p95/p99 và tải peak mới cho bằng chứng.

### 11.2. Timeout không được vượt deadline của caller

Gateway timeout 300 ms, Java downstream timeout 2.000 ms sẽ khiến Java tiếp tục nắm connection/thread sau khi caller đã bỏ cuộc. Cần có **absolute/remaining request deadline** hoặc budget propagated.

### 11.3. Latency budget cho replication/read concern

Một strong read/write có thể cần quorum remote AZ; failover có election delay. Không ép các operations ấy vào timeout phi thực tế chỉ vì local eventual GET bình thường 15 ms. **SLO và consistency contract** là inputs để chọn deadline.

## 12. Một trường hợp retry storm có thể tính bằng số

Giả sử:

~~~text
Original logical throughput = 2,000 requests/s
Backend normal mean attempt time = 50ms
Backend degraded mean attempt time = 500ms
Gateway × service × SDK max attempt multiplier = 12
~~~

### 12.1. In-flight demand trước lỗi

\[
L_{\mathrm{normal}}
=2\,000\times0{,}05=100
\]

### 12.2. Nếu QPS không đổi, chỉ latency tăng

\[
L_{\mathrm{degraded}}
=2\,000\times0{,}5=1\,000
\]

Đã tăng 10 lần.

### 12.3. Nếu retry nhân thành 12 lần và đạt mức xấu nhất

\[
\lambda_{\mathrm{attempt}}=24\,000/s
\]

\[
L_{\mathrm{demand}}
\approx24\,000\times0{,}5=12\,000
\]

Đây là phép ước lượng steady-state demand có tính trực giác; khi deadline/retry/backoff đã giới hạn, hệ không thể duy trì đúng con số này và sẽ sinh queue/rejections/cancellations. Nhưng nó cho thấy **vì sao không thể “thêm threads” để giải quyết**.

### 12.4. Với retry budget 10%

Nếu toàn service giữ backend retries <=200/s:

~~~text
Initial attempts: 2,000/s
Extra attempts:   <=200/s
Total attempts:   <=2,200/s (steady-state budget target)
~~~

Vẫn cần concurrency cap vì 2.200×0,5s = **1.100 in-flight demand**, vượt rất nhiều giới hạn có thể cho DB. **Retry budget kiểm soát lượng attempts, concurrency limiter kiểm soát lượng in-flight, circuit breaker kiểm soát việc có gửi tiếp hay không.**

## 13. Fallback: luôn phải công bố dữ liệu và consistency

Một breaker OPEN thường dẫn tới câu hỏi “trả fallback gì?”. Không phải fallback nào cũng hợp lệ.

| Operation | Fallback có thể xem xét | Fallback nguy hiểm |
| --- | --- | --- |
| Public catalog eventual | Stale-while-revalidate với TTL/dataAsOf rõ | Coi stale data là tồn kho hiện tại |
| Analytics dashboard | Trả snapshot kèm watermark và warning | Gắn “realtime” vào số cũ |
| User's recently placed order | Session-aware cached version nếu đáp ứng minVersion | Trả order v17 sau ACK v18 như current |
| Inventory reservation | Có thể fail-fast; queue command có acknowledgment contract rõ | “Đặt hàng thành công” khi chưa reserve |
| Payment capture | Verify idempotent outcome/explicit pending status | Auto-capture lại vì write timeout |
| Audit/ledger | Source-of-truth policy, thường fail-closed | Cached ledger balance không có audit |

### 13.1. Stale fallback cần một SLO riêng

Một API có thể định nghĩa:

~~~json
{
  "status": "DEGRADED",
  "dataAsOf": "2026-11-14T08:00:00Z",
  "data": {"productCount": 120}
}
~~~

Chỉ dùng `dataAsOf` nếu đó là một **watermark có ý nghĩa từ nguồn**, không lấy giờ cache response sinh ra làm bằng chứng dữ liệu mới.

### 13.2. Fallback không chuyển 503 thành success giả

Nếu nghiệp vụ đòi read-your-writes sau PUT và cached version nhỏ hơn session token, trả `200` với dữ liệu cũ có thể vi phạm hợp đồng. Khi không đáp ứng, trả pending/unavailable minh bạch.

### 13.3. Queue-as-fallback cần phân biệt accept và commit

Một API có thể đưa command vào durable queue rồi trả `202 Accepted`, nhưng **không thể gọi đó là committed database write** cho đến khi processing và durability contract được đáp ứng. Unknown outcomes, dedup và consumer lag phải được xử lý.

## 14. Java 17: các building blocks của một resilience policy

Các đoạn mã sau dùng Java 17 standard library để giải thích cơ chế; **chúng không phải một production-ready NoSQL SDK wrapper**. Khi triển khai thật, ưu tiên library/SDK đã được kiểm chứng, tích hợp metrics/tracing/cancellation, điều phối retries với driver và test toàn bộ failure modes. Không dùng code này để thay engine consistency.

### 14.1. Deadline dùng monotonic duration

~~~java
import java.time.Duration;

public final class Deadline {
    private final long startedNanos = System.nanoTime();
    private final long budgetNanos;

    public Deadline(Duration budget) {
        if (budget.isZero() || budget.isNegative()) {
            throw new IllegalArgumentException("Deadline must be positive");
        }
        budgetNanos = budget.toNanos();
    }

    public long remainingNanos() {
        long elapsed = System.nanoTime() - startedNanos;
        return Math.max(0L, budgetNanos - elapsed);
    }

    public boolean expired() {
        return remainingNanos() <= 0L;
    }

    public Duration remainingDuration() {
        return Duration.ofNanos(remainingNanos());
    }
}
~~~

`Duration.toNanos()` có thể overflow nếu budget vô lý quá lớn; production code nên validate upper bound. Giá trị `startedNanos` chỉ có ý nghĩa trong JVM/process hiện tại và **không truyền sang service khác để trừ trực tiếp**.

### 14.2. Local retry token budget theo original operations

Ví dụ một bucket có capacity giới hạn, cấp **một token sau mỗi 10 original requests đã được admit**. Đây là policy fixed-ratio minh họa; không claim nó phù hợp workload thưa và không bảo đảm cap chính xác trong mọi rolling window.

~~~java
public final class RetryTokens {
    private final int capacity;
    private final int originalsPerToken;
    private int available;
    private int originalCredits;

    public RetryTokens(int capacity, int originalsPerToken) {
        if (capacity <= 0 || originalsPerToken <= 0) {
            throw new IllegalArgumentException("Invalid retry budget");
        }
        this.capacity = capacity;
        this.originalsPerToken = originalsPerToken;
    }

    public synchronized void onOriginalAdmitted() {
        originalCredits++;
        if (originalCredits >= originalsPerToken) {
            originalCredits = 0;
            available = Math.min(capacity, available + 1);
        }
    }

    public synchronized boolean trySpendForRetry() {
        if (available <= 0) {
            return false;
        }
        available--;
        return true;
    }

    public synchronized int available() {
        return available;
    }
}
~~~

Nếu 100 original requests được admit, policy cấp tổng cộng tối đa 10 tokens trước các lần tiêu, **trừ giới hạn capacity**. Một pod vừa khởi động với zero tokens sẽ không retry cho tới khi có đủ originals; điều này có thể là intentional. Nhưng nhiều pods cùng có bucket riêng tạo **per-pod budget**, không phải fleet-wide. Trong production cần metrics về original arrivals, retries allowed/denied và fleet size.

### 14.3. Không cấp token nhờ retry successes

Một lỗi thiết kế:

~~~text
After any successful attempt:
    add one retry token.
~~~

Nếu một retry thành công tạo thêm token, chính retry traffic có thể nuôi tiếp budget, làm policy khó kiểm soát. Hãy cấp tokens từ **legitimate original work hoặc một refill rate độc lập đã định**.

### 14.4. Phân biệt budget tiêu thụ và attempt thực sự gửi

Nếu đã tiêu token nhưng breaker chuyển OPEN ngay trước lúc gửi, có thể token mất mà chưa tạo backend attempt. Trong bài minh họa, điều này là một **conservative debit**; production design có thể hỗ trợ refund an toàn hoặc điều phối reservations để tính chính xác, nhưng không refund nhầm tạo oversubscription khi concurrency cao. Luôn đo **attempts thực gửi** và **tokens spent** riêng.

## 15. Java 17: circuit breaker có giới hạn half-open probes

Đây là breaker minh họa dùng sliding window theo số calls, minimum 10 samples, mở khi failure rate từ 50%, và chỉ cho **một probe** sau open delay. Nó không có slow-call policy, full cancellation, metrics, per-route isolation hoặc probes đủ lớn để chọn config production.

~~~java
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.Deque;

public final class TinyCircuitBreaker {
    public enum State { CLOSED, OPEN, HALF_OPEN }

    private final int windowSize;
    private final int minCalls;
    private final double failureThreshold;
    private final long openForNanos;
    private final Deque<Boolean> failures = new ArrayDeque<>();

    private State state = State.CLOSED;
    private long openedAtNanos = 0L;
    private boolean probeInFlight = false;

    public TinyCircuitBreaker(
        int windowSize, int minCalls,
        double failureThreshold, Duration openFor
    ) {
        if (windowSize <= 0 || minCalls <= 0
            || minCalls > windowSize
            || failureThreshold <= 0 || failureThreshold > 1.0
            || openFor.isZero() || openFor.isNegative()) {
            throw new IllegalArgumentException("Invalid breaker config");
        }
        this.windowSize = windowSize;
        this.minCalls = minCalls;
        this.failureThreshold = failureThreshold;
        this.openForNanos = openFor.toNanos();
    }

    public synchronized boolean tryAcquirePermission() {
        if (state == State.OPEN) {
            long elapsed = System.nanoTime() - openedAtNanos;
            if (elapsed < openForNanos) return false;
            state = State.HALF_OPEN;
            probeInFlight = false;
        }
        if (state == State.HALF_OPEN) {
            if (probeInFlight) return false;
            probeInFlight = true;
        }
        return true;
    }

    public synchronized void onResult(boolean serverFailure) {
        if (state == State.HALF_OPEN) {
            probeInFlight = false;
            if (serverFailure) {
                open();
            } else {
                failures.clear();
                state = State.CLOSED;
            }
            return;
        }
        if (state != State.CLOSED) {
            return;
        }
        failures.addLast(serverFailure);
        if (failures.size() > windowSize) failures.removeFirst();
        if (failures.size() < minCalls) return;

        long failed = failures.stream().filter(Boolean::booleanValue).count();
        if (((double) failed / failures.size()) >= failureThreshold) {
            open();
        }
    }

    private void open() {
        state = State.OPEN;
        openedAtNanos = System.nanoTime();
        probeInFlight = false;
    }

    public synchronized State state() {
        return state;
    }
}
~~~

### 15.1. Những giới hạn an toàn của code mẫu

- `onResult(false)` phải chỉ được gọi khi **một backend attempt được tính hợp lệ**. Không lấy local semaphore reject/validation error làm “server success”.
- Nếu một half-open probe đã được permit nhưng request bị hủy trước khi gửi và `onResult` không được gọi, breaker có thể **kẹt `probeInFlight=true`**. Production cần permission token có lifecycle/timeout/cancel/release rõ.
- Một successful probe đóng breaker ngay ở mẫu; production thường cần nhiều probes, slow-call thresholds và state metrics.
- Nếu breaker được chia theo nhiều JVM, mỗi JVM có state khác nhau; không có global breaker state trừ khi được thiết kế riêng.
- Window theo số calls khác window theo thời gian; test cần chọn kiểu phản ánh traffic.

### 15.2. Hành vi cần thử

~~~text
For 20 backend attempts: 12 are classified server failures.
State transitions CLOSED -> OPEN.

While OPEN:
  no backend call is sent by guarded path.

After open duration:
  exactly one probe is admitted.
  concurrent probes are rejected.

If probe fails:
  state returns OPEN.

If probe succeeds:
  state returns CLOSED in the illustrative policy.
~~~

Không chỉ assert `state=OPEN`; còn phải assert **backend attempts actually stop** và không có race cho nhiều half-open requests.

## 16. Java: per-attempt concurrency control

Với synchronous SDK, Java `Semaphore` là một công cụ cơ bản.

~~~java
import java.time.Duration;
import java.util.concurrent.Callable;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class DbAttemptBulkhead {
    private final Semaphore permits;

    public DbAttemptBulkhead(int maxConcurrent) {
        if (maxConcurrent <= 0) {
            throw new IllegalArgumentException("Invalid concurrency cap");
        }
        this.permits = new Semaphore(maxConcurrent);
    }

    public <T> T withPermit(
        Callable<T> operation,
        Duration maxWait,
        Deadline deadline
    ) throws Exception {
        long waitNanos = Math.min(
            maxWait.toNanos(),
            deadline.remainingNanos()
        );
        if (waitNanos <= 0L
            || !permits.tryAcquire(waitNanos, TimeUnit.NANOSECONDS)) {
            throw new BulkheadRejected("DB attempt capacity unavailable");
        }
        try {
            if (deadline.expired()) {
                throw new IllegalStateException("Deadline expired");
            }
            return operation.call();
        } finally {
            permits.release();
        }
    }

    public int currentlyAvailable() {
        return permits.availablePermits();
    }

    public static final class BulkheadRejected extends RuntimeException {
        public BulkheadRejected(String message) { super(message); }
    }
}
~~~

### 16.1. Semaphore không tự áp per-attempt timeout

`operation.call()` là synchronous. Nếu SDK call không có timeout/cancellation, thread giữ permit vô hạn. Muốn một attempt có deadline phải **cấu hình timeout trên SDK/network operation hoặc dùng cơ chế cancel an toàn**, không hy vọng semaphore tự ngắt backend.

### 16.2. InterruptedException

`tryAcquire` có thể bị interrupt. `withPermit` để caller xử lý ngoại lệ; caller nên propagate/hủy request và giữ interrupt status phù hợp framework. Không `catch InterruptedException` rồi bỏ qua để retry tiếp.

### 16.3. Global và per-shard limits

Một limiter chung max 100 có thể khiến một hot partition chiếm cả 100 slots. Nếu SDK cung cấp route/partition identity đáng tin, có thể tách:

~~~text
global cap=150
per critical-write cap=40
per expensive-query cap=10
per hot tenant cap=20
~~~

Khi dùng nhiều semaphores, lấy theo **thứ tự nhất quán** để giảm deadlocks và luôn release trong `finally`. Đừng tạo một limiter theo mọi key một cách vô hạn (cardinality/memory leak).

## 17. Java: một vòng retry có deadline và budget

Ví dụ dùng synchronous read operation **được xác nhận retryable/idempotent theo application contract**. `NoSqlRead.execute(timeout)` là adapter phải thực sự propagate timeout tới SDK; không gọi một API server timeout mặc định dài hơn rồi coi deadline đã được bảo vệ.

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;

public final class RetriedNoSqlRead {
    @FunctionalInterface
    public interface NoSqlRead<T> {
        T execute(Duration timeout) throws Exception;
    }

    @FunctionalInterface
    public interface FailureClassifier {
        boolean retryable(Exception failure);
    }

    private final RetryTokens retryTokens;
    private final DbAttemptBulkhead bulkhead;
    private final FailureClassifier classifier;

    public RetriedNoSqlRead(
        RetryTokens retryTokens,
        DbAttemptBulkhead bulkhead,
        FailureClassifier classifier
    ) {
        this.retryTokens = retryTokens;
        this.bulkhead = bulkhead;
        this.classifier = classifier;
    }

    public <T> T execute(
        NoSqlRead<T> read,
        Duration deadlineBudget,
        int maxAttempts
    ) throws Exception {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("No attempts configured");
        }
        Deadline deadline = new Deadline(deadlineBudget);
        retryTokens.onOriginalAdmitted();

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            if (deadline.expired()) {
                throw new IllegalStateException("Overall deadline expired");
            }

            if (attempt > 1 && !retryTokens.trySpendForRetry()) {
                throw new IllegalStateException("Retry budget exhausted");
            }

            try {
                return bulkhead.withPermit(
                    () -> {
                        Duration remaining = deadline.remainingDuration();
                        if (remaining.isZero()) {
                            throw new IllegalStateException(
                                "Overall deadline expired"
                            );
                        }
                        Duration perAttempt = min(
                            remaining, Duration.ofMillis(100)
                        );
                        return read.execute(perAttempt);
                    },
                    Duration.ofMillis(10),
                    deadline
                );
            } catch (DbAttemptBulkhead.BulkheadRejected e) {
                throw e; // Local overload: do not retry in this loop.
            } catch (Exception e) {
                if (attempt == maxAttempts || !classifier.retryable(e)) {
                    throw e;
                }
                long remainingNanos = deadline.remainingNanos();
                long maxBackoffNanos =
                    TimeUnit.MILLISECONDS.toNanos(50);
                long delayNanos = ThreadLocalRandom.current()
                    .nextLong(Math.min(
                        maxBackoffNanos, remainingNanos
                    ) + 1);

                if (deadline.expired()) throw e;
                if (delayNanos > 0) {
                    TimeUnit.NANOSECONDS.sleep(delayNanos);
                }
            }
        }
        throw new IllegalStateException("Unreachable attempt state");
    }

    private static Duration min(Duration a, Duration b) {
        return a.compareTo(b) <= 0 ? a : b;
    }
}
~~~

### 17.1. Những điểm cố ý chưa giải quyết trong mã mẫu

1. **Circuit breaker chưa được nối vào vòng lặp.** Tích hợp thực tế cần quyền half-open có lifecycle, failure classification và metrics; tránh tự ráp breaker API bất đồng bộ vào synchronous loop sai.
2. Retry budget là **per-JVM**; phải cân đối khi scale pods.
3. Backoff dùng capped random 50 ms thay vì exponential per-attempt chỉ để rút gọn; có thể thay bằng công thức ở mục 6.
4. Thread đang `sleep` vẫn chiếm một **request worker thread**; production reactive/async workloads nên dùng scheduler không chặn threads.
5. Khi deadline vừa hết trong sleep, code chỉ phát hiện ở vòng sau; không gửi backend attempt mới, nhưng response mapping cần phản ánh timeout chính xác.
6. Classifier chỉ nhận `Exception`; phải phân loại driver exceptions theo SDK version và write/read semantics, không retry `CancellationException` hay validation.
7. Không tính CPU/time dùng trước `execute` trong deadline; trong HTTP service, phải bắt đầu deadline tại request ingress và truyền **remaining budget** vào adapter.
8. Không có tracing, metrics, structured logging, graceful shutdown hay local work queue budget.
9. Nếu SDK tự retry 3 lần bên trong `read.execute`, **mỗi vòng ở đây có thể sinh nhiều attempts hơn một**; phải đo theo transport/driver.
10. `maxAttempts` được config theo operation type, không có một hằng số đúng cho tất cả GET/write.

Mục tiêu của mã là minh họa **một logical read có deadline, mỗi retry tiêu token và từng attempt phải lấy permit rồi release**; không được hiểu là thư viện resilience hoàn chỉnh.

## 18. Java: quy tắc cho write cần outcome lookup

Với write có side effect, hãy nghĩ bằng **operation state machine** thay vì dùng vòng retry read:

~~~text
NEW
  -> SENT
      -> ACKED_COMMITTED       -> return success
      -> DEFINITE_NOT_APPLIED  -> retry if safe and budget permits
      -> UNKNOWN_OUTCOME       -> query idempotency outcome
          -> COMMITTED         -> return previous success
          -> NOT_COMMITTED     -> retry if protocol permits
          -> STILL_UNKNOWN     -> return PENDING/UNAVAILABLE
~~~

Một số SDK cung cấp idempotency token/transaction ID semantics sẵn; các SDK khác đòi application table hoặc conditional write. Không dùng `time.sleep` + resend như giải pháp mặc định cho payment/reservation.

### 18.1. Bản ghi outcome

~~~json
{
  "operationId": "capture-O900-attempt-v1",
  "businessAggregateId": "O900",
  "state": "COMMITTED",
  "resultVersion": 22
}
~~~

ID cần ổn định xuyên retries; nên ràng buộc identity/payload để cùng `operationId` nhưng khác amount không bị diễn giải là cùng operation hợp lệ.

### 18.2. Idempotency retention

Nếu retry/outcome lookup có thể xảy ra nhiều ngày sau outage, dedup record phải sống đủ lâu theo **business retry and reconciliation window**. Không đặt TTL chỉ 30 giây vì API retry budget là 300 ms rồi bỏ qua webhook/broker redelivery sau đó.

### 18.3. Conditional conflict không đồng nghĩa failure

Sau write timeout, conditional retry thấy expectedVersion đã thay đổi. Điều đó có thể nghĩa lần đầu đã thành công; hoặc một concurrent actor đã ghi. Phải tra operation ID/domain history để phân biệt.

## 19. MongoDB: retryable reads/writes, elections và pool limits

MongoDB Java Driver và topology replica set/sharded cluster có những cơ chế retry, server selection và connection management theo phiên bản. Khi kiểm thử, phải biết **driver thực sự gửi bao nhiêu commands**, không chỉ nhìn số lần method Java được gọi.

### 19.1. Retryable reads/writes có điều kiện

MongoDB có các tính năng **retryable reads và retryable writes** cho những operations/topologies phù hợp; không phải mọi write, multi-document transaction hoặc user-defined side effect đều được bảo vệ giống nhau.

Ghi lại khi test:

~~~text
driver version and topology
retryReads / retryWrites settings
session/transaction usage
writeConcern / readConcern
readPreference / server selection
serverSelectionTimeout / socket/connect timeouts
max connection pool size and wait queue behavior
```

Đừng áp business retry quanh SDK mà không tính SDK retry đã bật.

### 19.2. Election failover

Khi primary mất:

- Driver có thể tạm không chọn được server phù hợp.
- Writes cần primary có thể fail/timeout cho tới election.
- Read preference có thể cho reads từ secondaries nếu consistency contract cho phép.
- SDK internal retries có thể thêm attempts trong election window.

Thử leader loss phải quan sát **command started/succeeded/failed events**, server selection time, logical request deadline và idempotency outcome.

### 19.3. `maxTimeMS` không phải toàn request deadline

Một server-side operation time limit không bao trùm tất cả client-side time như waiting for pool, server selection, network retries hoặc serialization. Cần phối hợp **client/network deadlines** đúng driver API, không coi `maxTimeMS=300` là đảm bảo Java request hoàn tất trong 300 ms.

### 19.4. Transaction commit unknown outcome

Đối với transactions, driver/transaction protocol có error labels và retry guidance theo version. Một commit timeout có thể có **unknown transaction commit result**. Không tự re-execute toàn business transaction và nhân side effects khi chỉ cần xử lý commit outcome theo documented pattern.

### 19.5. Không tăng pool vô giới hạn

Số Java pods × pool max connections × discovered MongoDB servers có thể tạo lượng connections lớn. Test scaling/failover với expected max pool usage; tăng pool có thể làm mongod CPU/memory/context-switching quá tải.

### 19.6. Breaker scope

Một shard của sharded MongoDB đang chậm không nhất thiết là toàn hệ chết. Nếu app biết routed shard/tenant class, chia bulkhead/metrics phù hợp; nhưng không cố suy shard từ application key khi mongos có routing metadata/migrations khác.

## 20. Cassandra/ScyllaDB: consistency level, timeouts và speculative execution

Cassandra/ScyllaDB có replica placement, coordinator, token awareness và consistency levels. Retry policy phải tôn trọng yêu cầu business.

### 20.1. `LOCAL_QUORUM` không được hạ tùy tiện

Giả sử RF=3 trong DC, một write cần `LOCAL_QUORUM`. Nếu một replica chậm, coordinator có thể timeout. Tự đổi sang `ONE` để trả thành công làm **consistency/durability expectation thay đổi**. Một số SDK có retry policy riêng cho lỗi đọc/ghi, không nên dùng broad retry cho mọi `WriteTimeout`.

### 20.2. Write timeout là outcome chưa chắc chắn

Coordinator timeout sau khi một số replicas đã apply write. Client không thể kết luận “chưa ghi gì”. Với counter/update không idempotent, retry mù có thể gây effects sai; cần operation ID/conditional logic theo domain.

### 20.3. Speculative execution khác sequential retry

Một số drivers hỗ trợ **speculative execution**: gửi một request song song tới coordinator khác khi lần đầu chậm. Điều này có thể giảm tail latency cho eligible **idempotent requests**, nhưng:

- Tăng attempts **đồng thời**, không chờ failure.
- Có thể nhân tải lên replicas/coordinators.
- Cần tính vào global retry/extra-attempt budget.
- Không phù hợp cho operations không idempotent.

Một dashboard chỉ đếm “retries after errors” có thể bỏ sót speculative attempts.

### 20.4. Hot partition

Throttling một tenant không giải quyết bằng thay coordinators nếu mọi request vẫn truy cập cùng hot partition replicas. Cần partition-key design, rate/admission per tenant hoặc workload shaping.

### 20.5. Thử nghiệm

~~~text
Fault: one replica becomes slow.
Read CL: LOCAL_QUORUM.
Verify: no silent downgrade, bounded attempts,
        p99/deadline, write outcome correctness.
```

## 21. DynamoDB: throttling, SDK retries và hot partitions

DynamoDB SDK có cơ chế retries theo mode/version. Khi kích hoạt resilience ở application, cần xem **SDK đã có retry quota/backoff/adaptive behavior** chưa để tránh chồng.

### 21.1. Throttling không phải chỉ là network timeout

Một write bị throttled có thể phản ánh capacity/hot partition. Retry tức thì với cùng key trong burst làm tình trạng xấu thêm. Nên:

- Tôn trọng throttling hints/exceptions.
- Backoff with jitter.
- Limit in-flight attempts.
- Điều tra partition-key skew, consumed capacity, throttled requests.
- Có per-tenant admission/rate budget khi cần.

### 21.2. Per-partition vs global

Một table có tổng throughput còn dư nhưng một partition key cực nóng. Breaker toàn table có thể chặn các keys khác không cần thiết. Nếu route metrics đủ tin cậy, tách per-tenant/key-class limits; tránh tạo million-key breakers.

### 21.3. Conditional writes

Một `ConditionalCheckFailed` thường là kết quả business concurrency/condition không đạt, **không phải transient availability failure** để retry same stale request. Đọc lại version/outcome và quyết định theo domain.

### 21.4. Transactions và idempotency

Nếu dùng transaction write APIs có client request tokens và retry semantics được hỗ trợ, dùng chúng theo contract; không tự assume mọi BatchWrite/Update request được dedup bởi service.

### 21.5. Phép thử nên có

~~~text
Inject throttling at hot partition / lower provisioned test capacity.
Measure:
  logical requests
  SDK-level attempts
  throttle responses
  backoff distribution
  retry budget denials
  in-flight attempts
  deadline failures and recovery
```

## 22. Redis: cluster topology, commands không idempotent và timeout

Redis có standalone, Sentinel và Cluster deployments; lỗi connection/topology có cách retry khác nhau.

### 22.1. Các tín hiệu topology

Với Redis Cluster, clients có thể gặp `MOVED`/`ASK` redirection khi slot ownership đang thay đổi; `TRYAGAIN` hoặc các lỗi cluster-state có retry guidance theo version. Một redirect/topology refresh không giống **business retry**. Theo dõi attempted commands sau driver rerouting.

### 22.2. Không retry `INCR` mù

~~~text
Client sends INCR stock_reserved.
Redis applies increment.
Network drops ACK.
Client sends INCR again.
```

Kết quả có thể increment hai lần. Cần idempotency/domain transaction model, không coi `INCR` là GET.

### 22.3. `SET` vs side effects

`SET key sameValue` về final value có thể idempotent, nhưng expiration, streams/pubsub events, scripts hoặc hooks có thể có semantics khác. Đánh giá **operation end-to-end**.

### 22.4. Redis failover và dữ liệu chưa replicate

Redis replication thông thường có tính bất đồng bộ; failover có thể gây mất một số writes acknowledged trước đó trong failure windows theo persistence/replication settings. Retry/returning HTTP 200 không sửa được durability gap. `WAIT` có acknowledgment semantics riêng nhưng không biến mọi write thành consensus transaction.

### 22.5. Dễ gặp saturation

Tăng số clients kết nối hoặc pipelining quá nhiều requests vào một hot primary có thể tăng queue/memory/network pressure. Concurrency/queue bounds và command timeouts cần theo dõi **per primary/hash-slot path** khi khả thi.

## 23. Elasticsearch/OpenSearch: bulk indexing, rejections và search queues

Search-oriented NoSQL có query/indexing thread pools, shard allocation và refresh behavior.

### 23.1. Bulk API có thể thành công một phần

Một bulk indexing request có thể trả HTTP-level success nhưng **có item-level failures**. Không replay mù toàn bulk vì một số items đã được apply.

Thiết kế:

- Kiểm tra từng item success/failure.
- Retry only eligible failed items.
- Dùng stable document IDs/versioning nếu appropriate.
- Bound bulk size, concurrency, retries.
- Theo dõi queue/rejections/429 và disk watermarks.

### 23.2. Search fallback

Một search endpoint có thể chấp nhận stale results trong thời hạn được công bố; nhưng một “inventory availability query” dùng search index không nên tự quyết định số lượng hàng được phép bán. Fallback phải giữ business correctness.

### 23.3. Retry không làm index refresh nhanh hơn

Một document đã index ACK nhưng chưa query-visible vì refresh/indexing lag. Retry search ngay với vòng tight loop có thể tăng tải mà không cải thiện freshness nhanh tương ứng. Cần versioned visibility SLI và backoff/wait policy phù hợp.

### 23.4. Hot shard

Một search query dùng wildcard trên nhiều shards có thể làm scatter-gather fanout, khiến attempt concurrency ở cluster cao hơn logical request count nhiều lần. Giới hạn query concurrency cần tính **fanout**, không chỉ số HTTP requests.

## 24. Cosmos DB for NoSQL: RU throttling và session correctness

Cosmos DB thường có request unit budgets và có thể trả throttling status, với SDK retry behavior theo version/mode.

### 24.1. 429 và per-partition workload

Khi RU/s hoặc partition limits bị chạm, SDK có thể tự retry theo backoff/throttling hints. Nếu app thêm retry bên ngoài mà không tính SDK, có thể làm QPS attempts tăng và kéo dài latency. Đo request charge, throttle rate, partition key distribution và deadline.

### 24.2. ETag conflicts

Optimistic concurrency check fail (ví dụ HTTP 412) thường là một domain concurrency condition; không nên retry blind stale ETag mãi. Đọc lại resource và quyết định business update.

### 24.3. Session tokens

Nếu user cần read-your-writes qua regions/replicas, fallback sang bất kỳ read region nào mà không giữ session semantics có thể trả bản cũ. Circuit breaker không tự đảm bảo causal/session consistency.

### 24.4. Bulk executor và concurrency

Batch/bulk mode có thể tạo nhiều concurrent operations bên trong SDK. Một application semaphore per bulk call không giới hạn số backend suboperations nếu library fanout; cần đo **actual in-flight requests/RU**.

## 25. Bảng NoSQL: nguyên nhân → thử nghiệm → guardrail

| Engine/đường truy cập | Sự cố điển hình | Guardrail cần thử |
| --- | --- | --- |
| MongoDB replica set | Primary election | Bounded driver selection/retries, unknown write outcome, breaker recovery |
| MongoDB sharded | Một shard chậm | Per-route/operation limits, không toàn cụm false-open |
| Cassandra/ScyllaDB | Replica timeout/hot partition | No CL downgrade, speculative attempts counted, quorum safety |
| DynamoDB | Hot-key throttling | SDK retry budget + backoff/jitter + per-key admission |
| Redis Sentinel/Cluster | Promotion/slot redirection | Topology refresh, no duplicate non-idempotent command |
| Elasticsearch/OpenSearch | Bulk 429/item failures | Item-level retries, bounded bulk concurrency |
| Cosmos DB | RU 429/partition hotness | Respect throttling, bound attempts, session consistency |

Tính đúng của retry phụ thuộc **SDK, topology, consistency mode và operation type**; các tên lỗi/behavior cụ thể phải kiểm tra trên phiên bản thực của ứng dụng.

## 26. Thiết kế bài kiểm thử: baseline và failure model

Không thể khẳng định retry budget hay breaker “đã hoạt động” chỉ bằng unit test một hàm.

### 26.1. Đặt workload đại diện

Ví dụ staging:

~~~yaml
workload:
  logicalRps: 1000
  durationMinutes: 20
  trafficMix:
    orderGet: "65%"
    orderUpdateConditional: "20%"
    inventoryReservation: "10%"
    analyticsQuery: "5%"
  partitionDistribution:
    normal: "realistic-skew"
    hotTenantShare: "20%"
  targets:
    apiP99Ms: 300
    successfulBusinessWritesPreserveInvariants: true
    allRequestsFinishOrFailWithinDeadline: true
~~~

Số liệu là **giả định thử nghiệm**, không phải benchmark của NoSQL nào. Chọn traffic mix/size/partition skew dựa trên production telemetry đã anonymize và workload business.

### 26.2. Có ba phase

~~~text
Phase A: Healthy baseline (5 min)
Phase B: Fault injection / overload (10 min)
Phase C: Recovery and traffic normalization (5 min)
~~~

Đo cả **sự phục hồi**, vì nhiều hệ có breaker đóng lại rồi tạo retry storm ngay khi backend vừa khỏe.

### 26.3. Cấp độ fault injection

1. **Unit:** Fake backend trả success/failure/timeouts có determinism.
2. **Integration:** SDK với local/staging NoSQL service và proxy delay.
3. **Cluster:** Một node/AZ/shard degraded, failover/rebalance.
4. **End-to-end:** Gateway → API → SDK → NoSQL với traffic mix và correct data outcomes.

Chỉ thực hiện destructive network partitions/kill operations ở **môi trường test hoặc được cấp phép rõ ràng**. Với managed NoSQL không thể inject node-level failures, dùng throttling/latency wrappers hoặc vendor-supported chaos exercises và kiểm tra SLO thực tế.

### 26.4. Baseline cần lưu

~~~text
appVersion, sdkVersion, retry config at every tier
NoSQL topology/replication and consistency
dataset size and partition skew
CPU, heap/GC, thread and connection pools
logical RPS, backend attempts RPS, p50/p95/p99
read/write error rate, throttling, queue wait
baseline business invariant verification
```

Không so một test 100k documents với production 100M và tuyên bố tính ổn định tương đương.

## 27. Test matrix cho retry budget

| Kịch bản | Fault được tạo | Điều phải kiểm tra |
| --- | --- | --- |
| Transient failure 1 attempt | Attempt đầu fail, attempt hai healthy | Retry đúng một lần nếu token/deadline cho phép |
| Persistent failure | Mọi attempts fail | Không vượt maxAttempts và global retry budget |
| SDK internal retry | Driver tự retry trước khi trả exception | Tổng backend attempts vẫn nằm trong budget thực |
| Nested retries | Gateway và app đều bật retry | Không nhân attempts quá target cap |
| Token exhaustion | Cố tình dùng hết retry budget | Requests mới fail/return đúng, không retry lén |
| No original traffic | Không có legitimate requests | Retry budget không tự được refill từ retries |
| High-QPS burst | 10× traffic trong 5 s | Bounded burst, metrics và backend attempts |
| Low-QPS | 1 original request / phút | Không starvation ngoài policy mong muốn |
| Hot tenant | Một tenant gây 80% errors | Không dùng hết budget của tenants khác |
| Network timeout write | ACK lost after commit | Không double-apply mutation |
| Conditional conflict | ExpectedVersion stale | Không retry blind |
| 429 throttling | Server capacity exceeded | Backoff, jitter, respect hint, admission |
| Deadline nearly expired | Retry would exceed remaining budget | Không gửi attempt mới |
| Cancellation | Client cancels mid-backoff | Không tiếp tục retry |
| App autoscale | 10 → 50 pods | Fleet-wide budget không phình vô kiểm soát |
| Rolling restart | Retry tokens reset | Behavior phù hợp, không burst ngay khi start |
| Breaker OPEN | Dependency short-circuited | No backend retry attempt |
| Half-open probe | Chỉ một probe allowed | Retry layer không tạo nhiều probes cùng lúc |

### 27.1. Một assertion quan trọng

Với **original requests** \(N\) và số **extra backend attempts** \(R\), có thể tính:

\[
\mathrm{retryAmplification}=\frac{N+R}{N}
=1+\frac{R}{N}
\]

Nếu budget đặt ở mức 10%:

\[
\frac{R}{N}\le0{,}10
\]

**Chỉ dùng phép đo này khi `N` là số logical operations có cùng scope và `R` tính tất cả extra attempts**, kể cả SDK proxy/hedging/speculative execution nếu chúng tạo tải tương đương. Nếu phân phối traffic vào nhiều partitions/regions, cần báo per-scope để không che burst ở một hot shard.

### 27.2. Phân biệt retry rate và retry success

Hai trường hợp:

~~~text
Case A:
  100 retries issued
  95 recover successfully

Case B:
  100 retries issued
  0 recover successfully
~~~

Cùng retry rate nhưng **giá trị khác hẳn**. Khi retry success thấp và backend đang quá tải, nên giảm attempts/fail faster thay vì tăng budget.

### 27.3. Đo overload, không chỉ successes

Một retry policy có thể tăng user success từ 96% lên 98% trong lab nhưng nhân backend attempts gấp 4 và làm p99 tăng từ 150→800 ms. Kết luận “tốt hơn” không đủ; phải xét **SLO latency, error budget, overload recovery và business correctness**.

## 28. Test matrix cho circuit breaker

### 28.1. Healthy traffic không được mở breaker

Inject 0–1% transient errors phù hợp baseline, kèm 404/validation/conditional conflicts hợp lệ. Assert breaker **không mở sai** chỉ vì domain outcomes.

### 28.2. Persistent downstream failure

Backend trả 503/timeout liên tiếp. Assert:

- CLOSED → OPEN theo window/min calls.
- Số real backend attempts giảm sau khi OPEN.
- Local short-circuit errors tăng với label rõ.
- API latency giảm về fail-fast range.
- Critical write không trả success giả.

### 28.3. HALF_OPEN

Sau open delay:

- Số concurrent probes tối đa theo config.
- Failed probes đưa về OPEN.
- Successful probes cho CLOSED theo policy.
- Không xả backlog queued vào backend ngay tức thì.

### 28.4. False-positive domain errors

Cho 1.000 GET keys không tồn tại; DB trả `NOT_FOUND` đúng contract. Breaker **không được mở** vì đó là business result, dù API có thể trả HTTP 404.

### 28.5. Partial failure

Chỉ một shard/region lỗi:

~~~text
Shard A: 95% failures
Shard B: healthy
Shard C: healthy
```

Test breaker scope: nếu gộp tất cả, A có thể làm block cả B/C. Cân nhắc route-level limits hoặc dedicated operation isolation mà không tạo quá nhiều per-key circuit states.

### 28.6. Breaker + concurrency cap

Khi bulkhead đầy do local traffic burst, `BulkheadRejected` phải được báo là **local saturation**; không được tăng `dependencyFailureCount` dẫn tới breaker OPEN sai, trừ khi policy cố ý coi saturation như signal nhưng phải định nghĩa rõ.

### 28.7. Flapping

Backend luân phiên khỏe/lỗi mỗi 2 giây. Nếu breaker đóng/mở liên tục, request success/latency có thể khó dự đoán. Test open window, minimum sample, half-open probes và jittered recovery để tránh **flapping**.

## 29. Test matrix cho concurrency, queue và bulkhead

### 29.1. Tăng tải từ từ

Một stepped load test:

~~~text
500 RPS for 3 min
1,000 RPS for 3 min
1,500 RPS for 3 min
2,000 RPS for 3 min
Reduce to 500 RPS for 3 min
~~~

Ở mỗi bước, ghi in-flight, queue length, queue wait, success, p99, DB saturation và retry amplification. **Tìm knee point**: ngưỡng QPS từ đó latency tăng rất nhanh vì queueing.

### 29.2. Concurrency limiter thực sự giữ trần

Nếu `maxConcurrentDbAttempts=80`, một test với 500 simultaneous callers phải xác nhận:

~~~text
max observed SDK attempts in flight <= 80
local rejection/queue bounded
all permits released on success/error/cancel/timeout
```

**SDK internal fan-out/retries** có thể khiến 80 outer permits bao quanh 80 logical calls nhưng hơn 80 transport attempts. Xác định thứ được giới hạn; nếu mục tiêu là backend attempt cap, phải instrument hoặc điều phối đúng tầng.

### 29.3. Thread-pool and heap pressure

Load spike tạo 10.000 waiting requests. Nếu pending queue unbounded, memory/GC/threads có thể tăng trước khi DB saturation rõ. Test giới hạn pending count và reject latency.

### 29.4. Isolating analytics

Cho expensive analytics queries chạy full concurrency limit trong khi critical writes vẫn đến. Assert writes có dedicated permits và business success/p99 trong SLO hoặc degrade đã định.

### 29.5. Permit leak

Inject exception ở:

- Connection acquisition.
- Backend timeout.
- Serialization/deserialization.
- User cancellation.
- Breaker-open short circuit.
- Unexpected runtime exception.

Sau mọi exception, eventual `availablePermits` phải trở lại expected state **khi không còn operations thực sự đang chạy**.

### 29.6. Queue timeout

Một request chỉ còn 10 ms deadline không được chờ semaphore 300 ms. Assert queue wait ≤ remaining deadline và không gửi backend request sau expiration.

### 29.7. Recovery

Sau 5 phút lỗi, backend trở lại healthy. Limiter/queue/breaker/retry policy không được khiến queue replay đồng loạt 100k operations. Đo time-to-stable normal p99 và post-recovery errors.

## 30. Fault injection matrix tích hợp

Các test sau chạy trên **lab/staging hoặc môi trường được phê duyệt**, dùng synthetic keys, bounded traffic và stop conditions.

| Fault | Cách mô phỏng an toàn | Kết quả quan sát kỳ vọng |
| --- | --- | --- |
| Network latency +250 ms | Proxy/test transport delay | Deadline phù hợp, no burst retries |
| 10% packet loss | Controlled proxy | Retry budget, breaker không false-open quá nhạy |
| 100% dependency timeout | Stub/proxy drop | Breaker OPEN, attempts giảm, fast failures |
| Primary election | Staging cluster failover | Driver discovery, idempotent outcomes |
| One shard slow | Key-selected delay | Per-route isolation hoặc graceful degradation |
| All replicas slow | Throttle staging resources | Concurrency/queue bound, load shedding |
| Throttling/429 | Stub or managed test capacity | Jitter, SDK hint, retry cap |
| Connection pool exhaustion | Low pool limit in lab | No infinite wait, local rejections classified |
| DNS/seed failure | Cold-start with one endpoint unavailable | Alternate discovery, bounded deadline |
| Read consistency unavailable | Simulated quorum failure | No unsafe downgrade |
| Write ACK lost | Commit then drop response in stub | No duplicate payment/reservation |
| CDC/index lag | Delay read model update | No stale fallback for critical reads |
| Client cancellation | Cancel after request sent | No new retry, permits released |
| Clock wall-time jump | Inject clock in monitoring | Monotonic deadline unaffected |
| Burst 10× traffic | Load generator with bound | Admission cap, no OOM |
| Gradual recovery | Restore backend health | Half-open probes, no herd |
| Frequent flaps | Alternate healthy/failing | Stable breaker hysteresis |
| One tenant attack/bug | Key-specific heavy workload | Tenant isolation, no full-cluster starvation |
| App autoscale | Increase pod count in lab | Fleet attempt budget still bounded |
| SDK retry mode switch | Enable built-in retries | No double amplification |

### 30.1. Fault injector phải có counter

Với network delay/packet drop, cần biết **bao nhiêu attempts thực sự chịu fault**. Một test báo “10% errors injected” nhưng chỉ 1% real DB requests đi qua proxy không chứng minh toàn tuyến.

### 30.2. Đừng phá tính đúng của fault injection

Không ngắt network production hoặc cố gây quorum loss trong môi trường người dùng thật chỉ để “thử breaker”, trừ khi có chương trình chaos được phê duyệt, guardrails và rollback. Staging test phải có synthetic records, giới hạn thời lượng và volume.

### 30.3. Recovery phases cần được đo

~~~text
T_fault_start
T_error_rate_detected
T_breaker_open
T_backend_attempts_drop
T_fault_removed
T_first_successful_probe
T_breaker_closed
T_api_slo_recovered
```

Nếu breaker đóng ở t=10s nhưng API p99 chỉ bình thường ở t=5 phút do long queue, “breaker recovered” chưa là end-to-end service recovery.

## 31. Open-loop và closed-loop load generators

### 31.1. Closed-loop

Mỗi virtual user gửi một request, đợi kết quả rồi gửi request mới. Khi backend chậm, **arrival rate giảm tự nhiên**, dễ che overload.

### 31.2. Open-loop

Load generator phát requests theo lịch/arrival rate mục tiêu độc lập với latency (trong giới hạn test harness). Khi backend chậm, requests có thể queue và phản ánh saturation rõ hơn.

### 31.3. Coordinated omission

Nếu công cụ chỉ đo latency của requests thực sự bắt đầu sau khi system có slot, những requests **đáng lẽ đã đến nhưng bị chặn vì generator đợi** không xuất hiện trong latency histogram. Đây là coordinated omission; p99 báo cáo có thể quá đẹp.

Để test retry/bulkhead, ghi:

- Scheduled arrival rate.
- Actual sent arrival rate.
- Logical user-visible latency, kể cả queueing.
- Dropped/rejected requests.
- Backend attempt latency.
- Test generator CPU/network saturation.

### 31.4. Load generator cũng có capacity limit

Nếu tool chạy trên một VM 1 vCPU không phát được 20.000 req/s, số liệu “DB bền ở 20k” không đáng tin. Chứng minh generator đạt target offered load và không là bottleneck.

## 32. Thử nghiệm A/B chính sách resilience

Một thiết kế:

~~~text
Policy A:
  3 retries at every layer
  no shared budget
  no bulkhead
  fixed backoff 100ms

Policy B:
  coordinated SDK/business retry
  total retry budget 10%
  jittered backoff
  per-route deadline and bulkhead
  circuit breaker with limited probes
~~~

Chạy **cùng dataset, fault type, offered load và traffic distribution**. So sánh:

- Logical success rate.
- Business correctness/duplicate effects.
- User-visible p95/p99.
- Backend attempts amplification.
- Time spent overloaded.
- Pool saturation/heap/GC.
- Recovery duration after fault removed.

Một policy B có thể trả nhiều fail-fast errors hơn trong fault nhưng bảo vệ khả năng hồi phục nhanh hơn. Đánh giá theo **business SLO/trade-offs**, không đơn giản “policy nào có nhiều HTTP 200 nhất”.

## 33. Chỉ số cần có để kiểm thử được các cơ chế

### 33.1. Tách ba tầng metrics

**User-facing logical requests**

- Logical request rate và endpoint/operation class.
- End-to-end latency p50/p95/p99, bao gồm chờ queue.
- Success, application errors, timeouts và cancellations.
- Business correctness: duplicates, stale reads, lost writes/unknown outcomes.

**Application protection controls**

- Retry attempts allowed/denied, tokens remaining.
- `attemptNumber`, total extra attempts, jitter/backoff duration.
- Breaker CLOSED/OPEN/HALF_OPEN, transition counts, probe outcomes.
- Bulkhead active permits, saturation, queued, rejected, wait duration.
- HTTP/gateway timeout, load shedding, fallback type và age.

**NoSQL/backend**

- Actual command/SDK transport attempts (không chỉ logical calls).
- Per-shard/region read/write QPS, latency, throttling.
- Connection pool active/idle/waiters.
- CPU, memory, disk I/O, compaction, replication/failover metrics.
- Server-selected route, consistency/write concern, failed quorum/leader changes.

### 33.2. Metrics có cùng scope

Tỷ lệ retries tính theo một window:

\[
\mathrm{retryRate}=
\frac{\mathrm{extraBackendAttempts}}
{\mathrm{initialBackendAttempts}}
\]

Nếu initial gồm tất cả incoming requests nhưng extra backend attempts chỉ gồm GET path, tỷ số bị sai. Cần cùng `service`, `route`, `operationKind`, `region` và window. Khi một request fan-out tới nhiều shards, nên tách **logical retry attempts** và **physical backend operations**.

### 33.3. Tỷ lệ breaker short-circuit

\[
\mathrm{shortCircuitRate}=
\frac{\mathrm{circuitDeniedCalls}}
{\mathrm{circuitDeniedCalls}+\mathrm{breakerPermittedCalls}}
\]

Đây là tỷ lệ trên số calls đi qua breaker, không phải user request failure rate. Một logical request có thể gọi breaker nhiều lần; cần báo logical success rate riêng.

### 33.4. Bulkhead saturation

\[
\mathrm{permitUtilization}=
\frac{\mathrm{activePermits}}
{\mathrm{configuredPermitLimit}}
\]

Tỷ lệ gần 100% là dấu hiệu có thể saturation, nhưng nếu queue=0 và errors=0 trong workload ổn định, chưa chắc có sự cố. Cần đọc chung queue wait, rejection rate và latency.

### 33.5. Error taxonomy

Một error classifier hữu ích:

~~~text
DB_TIMEOUT
DB_THROTTLED
DB_LEADER_CHANGED
DB_QUORUM_UNAVAILABLE
DB_CONNECTION_FAILURE
DB_CONDITIONAL_CONFLICT
DB_NOT_FOUND
DB_AUTHENTICATION
LOCAL_BULKHEAD_REJECTED
LOCAL_CIRCUIT_OPEN
LOCAL_DEADLINE_EXPIRED
CLIENT_CANCELLED
UNKNOWN_WRITE_OUTCOME
~~~

Không gộp tất cả thành `db_error=true`, nếu không sẽ khó chọn retryable exceptions và breaker statistics.

### 33.6. Histograms và percentiles

Nên dùng histogram/buckets phù hợp service SLO để tổng hợp p95/p99 trên nhiều pods; **không lấy trung bình p99 của các pods** rồi coi là p99 toàn dịch vụ.

### 33.7. Số liệu mẫu dashboard

| Chỉ số | Baseline | Trong fault | Sau recovery |
| --- | ---: | ---: | ---: |
| Logical RPS | 1.000 | 1.000 offered | 1.000 |
| Backend attempts/s | 1.015 | 1.085 | 1.012 |
| Retry attempts/initial | 1,5% | 8,5% | 1,2% |
| Breaker OPEN duration | 0 s | 40 s | 0 s |
| DB in-flight peak | 45 | 80 (cap 80) | 45 |
| Bulkhead rejected/s | 0 | 90 | 0 |
| API p99 | 145 ms | 290 ms successful* | 150 ms |
| API error rate | 0,05% | 14% | 0,07% |
| Duplicate business effects | 0 | 0 | 0 |

**Số liệu giả định**. `290 ms successful*` chỉ là p99 của **successful requests**, không thay cho full user-visible latency/outcome SLI. Nếu requests bị short-circuit rất nhanh, thành công p99 vẫn có thể trông đẹp trong khi availability giảm.

### 33.8. Censoring và timeout samples

Nếu 30% requests timeout 300 ms, chỉ tính p99 của 70% thành công sẽ tạo bias. Cần báo:

- Success-within-deadline rate.
- Timeout/error/short-circuit rate.
- Latency distributions theo outcome.
- Offered load vs accepted load.

Trong nhiều hệ không có latency thành công cho failed requests, timeout sample là **censored outcome**, không gán latency thực của backend bằng đúng timeout.

## 34. SLI/SLO và tiêu chí nghiệm thu cụ thể

Một test plan có thể nêu:

~~~yaml
resilienceTest:
  endpoint: "GET /orders/{id}"
  conditions:
    offeredRps: 1000
    fault: "backend timeouts for 60 seconds"
  targets:
    maxAttemptsPerLogicalRead: 3
    extraBackendAttemptsRatio: "<=0.10 per 1-minute window"
    maxDbAttemptsInFlightPerPod: 80
    maxPendingAttemptWaitMs: 20
    noNewAttemptAfterDeadline: true
    breakerHalfOpenMaxProbes: 2
    allOutcomesObservedWithinDeadlineMs: 300
    noStaleReadWhenSessionRequiresVersion: true
    noDuplicateWriteEffects: true
  observations:
    recordLogicalAndPhysicalAttempts: true
    runHealthyFaultRecoveryPhases: true
    monitorFleetAsPodsScale: true
~~~

Đây là **mẫu SLO** để đưa vào test, không phải config chính thức. `extraBackendAttemptsRatio` cần định nghĩa rõ mẫu số và rolling window; một bucket có burst allowance có thể khiến ratio vượt target ở một số cửa sổ ngắn nếu không phối hợp.

### 34.1. Vừa có availability vừa có safety

Hai assertions:

~~~text
Availability:
  user requests finish successfully or with controlled error
  under documented deadlines.

Safety:
  no acknowledged inventory/payment mutation is duplicated,
  and no read/write consistency contract is silently downgraded.
~~~

Một test có p99 cực thấp vì breaker trả `503` cho mọi request có thể đạt “fast response” nhưng **không đạt business availability target**.

### 34.2. Tiêu chí khi breaker OPEN

Ví dụ:

- Backend attempts trong 10s sau OPEN giảm ≥90% trên guarded path.
- Short-circuit error latency p99 ≤20 ms tại application (không tính upstream).
- Read-only fallback nếu có phải gắn freshness watermark.
- Không gửi critical writes qua unsafe fallback.

Con số ví dụ; chọn theo SLO/environment và overhead thực.

### 34.3. Tiêu chí khi hồi phục

- HALF_OPEN probe concurrency ≤ configured permits.
- Recovery không tạo burst vượt cluster safe capacity.
- Success rate trở về healthy SLO trong recovery target.
- Bulkhead/queue/pool không còn leak.
- Không còn pending requests sau deadline.

### 34.4. Error budget khi test

Fault injection có thể cố tình làm availability giảm; cần một **chaos budget** và test guard riêng để không ảnh hưởng live users. Không dùng production SLO error budget như quyền ngầm để phá cluster.

## 35. Phân tích một test giả định

Tình huống:

~~~text
Traffic: 800 original order reads/s
Fault: hot shard delayed 750 ms for 2 minutes
SDK retries: 2 attempts max
App retries: 3 attempts max
Gateway retries: 2 attempts max
API timeout: 300 ms
~~~

### 35.1. Giới hạn multiplier

Nếu `2,3,2` là **max attempts**:

\[
A_{\max}=2\times3\times2=12
\]

Tải attempts tiềm năng:

\[
800\times12=9\,600/s
\]

Do API deadline 300 ms và backend delay 750 ms, nhiều attempts sẽ không thể hoàn thành trong user deadline. Cho phép SDK/app/gateway retry nhiều tầng có thể **tạo tải nhưng không tạo thêm user success**.

### 35.2. Với budget 5% và per-pod bulkhead

Giả sử toàn fleet khống chế extra backend attempts 5%:

\[
800\times0{,}05=40\ \mathrm{extraAttempts/s}
\]

Trong steady period, tổng attempts kỳ vọng bị giới hạn khoảng 840/s trước khi áp breaker/admission. Concurrency cap giữ số in-flight ở mức có thể chịu; breaker mở khi fault đủ rõ. **Error rate có thể tăng** nhưng hệ tránh self-amplifying overload.

### 35.3. Điều cần đo để quyết định policy tốt

Nếu tăng global retry budget từ 5% lên 20%:

- Có tăng **successful responses within 300ms** không?
- Hay chỉ tăng attempts/queue và p99?
- Có làm shards khỏe chậm theo không?
- Breaker có phục hồi chậm hơn?
- Có thêm unknown outcomes/duplicate writes?

Không chọn retry budget lớn hơn chỉ vì percent failures giảm trong một lab test ở tải rất thấp.

## 36. Runbook khi NoSQL bắt đầu quá tải

### Bước 1 — Phân biệt nguồn lỗi

Kiểm tra:

~~~text
Logical RPS vs actual backend attempts RPS
Per-route/tenant hotness
DB latency and throttling
Client pool wait / queue wait
Breaker states
Retry tokens and denials
Failover/election/replication
Application CPU/heap/GC
~~~

Một API chậm do Java GC không được chữa bằng breaker mở vào database.

### Bước 2 — Xác định tính đúng dữ liệu

- Có unknown write outcomes không?
- Có counter/transaction/payment đang retry tự động không?
- Read paths có downgrade consistency không?
- User-visible fallback có stale vượt policy không?

Nếu dữ liệu bị nghi sai, ưu tiên **fence unsafe operations** và điều tra idempotency/authority.

### Bước 3 — Giảm tải có kiểm soát

Tùy nguyên nhân, áp:

- Rate/admission control với noncritical endpoints.
- Bounded retry budget, stop retrying overload.
- Lower concurrency for expensive queries.
- Disable nonessential batch/backfill.
- Keep per-request deadline short enough to prevent resource accumulation.
- Protect dedicated critical-write bulkhead.

Không tự tăng toàn bộ pools/threads mà không đo source saturation.

### Bước 4 — Breaker chính xác

- Phân biệt dependency failures với local rejects.
- Kiểm tra breaker đang OPEN vì đúng shard/region/operation.
- Không ép reset CLOSED hàng loạt khi backend vẫn lỗi.
- HALF_OPEN probes limited và có monitoring.

### Bước 5 — Khôi phục

- Theo dõi leader/topology recovery và replication.
- Cho traffic phục hồi từ từ; tránh thundering herd.
- Đánh giá queue drain, pool recovery, open breakers và tokens.
- Reconcile unknown write outcomes.
- Xác nhận endpoint success/p99/correctness.

### Bước 6 — Post-incident

Ghi:

~~~text
Root trigger: DB/partition/network/client/pool?
Amplification by gateway/service/SDK?
Time to circuit OPEN and recovery?
Max in-flight and queue depth?
Any consistency/duplicate effects?
Which limiter prevented cascade?
What fault/load test was missing?
~~~

## 37. Các lỗi cấu hình thường gặp

| Anti-pattern | Vì sao nguy hiểm | Cách cải thiện |
| --- | --- | --- |
| Mọi tầng retry 3 lần | Multiplicative attempts | Một policy phối hợp xuyên layers |
| Retry không deadline | Retry sau khi user đã bỏ | Overall deadline propagated |
| Retry non-idempotent write | Double effect | Operation ID/outcome lookup |
| Retry ngay khi 429 | Tăng overload | Backoff + jitter + server hints |
| Retry khi breaker OPEN | Không có ích | Fail fast hoặc valid fallback |
| Backoff giữ DB semaphore | Giảm useful capacity | Release per-attempt permit |
| Unbounded thread queue | Memory/GC và latency cao | Bounded queue/load shedding |
| Chỉ giới hạn request/s | Latency tăng làm in-flight tăng | Concurrency cap |
| Chỉ giới hạn per pod | Autoscale làm global cap phình | Fleet-level capacity budget |
| Circuit tính 404 là failure | False OPEN | Domain-aware classification |
| Circuit tính bulkhead rejection là DB outage | False OPEN | Tách local vs remote |
| HALF_OPEN mở mọi calls | Recovery storm | Probe permits |
| Một circuit toàn cluster | Hot shard chặn healthy shards | Scope phù hợp route/operation |
| Quá nhiều per-key breakers | Cardinality/memory leak | Group keys thành bounded classes |
| Fallback stale inventory | Vi phạm correctness | Fail closed/strong source |
| Quorum write tự hạ xuống ONE | Thay đổi durability | Giữ data contract |
| Tăng connection pools vô hạn | DB/server tài nguyên cạn | Measure saturation trước |
| Chỉ đo successful p99 | Bỏ timeout/rejection | Outcome SLI + percentiles |
| Không tính SDK internal attempts | Budget giả | Instrument real transport calls |
| Unit test mà không load test | Không thấy cascade | End-to-end fault + load |
| Test không có hot keys | Che partition bottleneck | Realistic skew |
| Closed-loop load test duy nhất | Coordinated omission | Open-loop offered-load test |
| Retry tất cả errors giống nhau | Auth/validation lỗi vô ích | Classifier theo operation |
| Breaker mở quá nhanh với 2 samples | Flapping | Min calls và window |
| Không test recovery | Mở lại gây herd | HALF_OPEN/ramp load test |
| One maxAttempts cho mọi endpoint | Không phù hợp risk/SLO | Per operation class |
| `sleep` trên event loop | Chặn async processing | Nonblocking scheduler |
| Không release permit khi cancel | Leak và starvation | Finally/cancel lifecycle |
| “HTTP 202” coi là write committed | Sai contract | Explicit accepted/pending state |

## 38. Case study A — Retry storm khi primary failover

### Bối cảnh

MongoDB replica set đổi primary. Gateway, Java Order Service và Java driver đều có retry policy riêng.

~~~text
Incoming requests: 1,500/s
Gateway maxAttempts: 2
Service maxAttempts: 3
SDK maxAttempts: 2 for eligible operation
~~~

### Triệu chứng

Thời gian election chỉ là một phần outage, nhưng sau đó DB vẫn nhận traffic gấp nhiều lần bình thường. CPU/connection pools bão hòa, breaker mở, RTO user-visible kéo dài.

### Nguyên nhân

Tổng multiplier tối đa \(2\times3\times2=12\) trong mô hình nested calls. Retry không phối hợp, không có global attempt budget; một số attempts tiếp tục sau khi gateway đã timeout.

### Khắc phục

- Ghi driver retry semantics/topology version.
- Bỏ retry dư thừa ở gateway với writes.
- Per-request deadline propagated tới SDK.
- Retry budget theo **actual backend attempts**.
- Cap in-flight/queue, half-open probes và gradual recovery.
- Reconcile unknown write outcomes.

**Kết luận:** Không thể chỉ “giảm election duration” để sửa retry storm; phải sửa behavior phía clients.

## 39. Case study B — Counter được tăng hai lần sau timeout

### Bối cảnh

Redis `INCR reservedQuantity` được áp nhưng ACK mất. Java service retry cùng command vì exception có tên `SocketTimeoutException`.

### Hậu quả

Counter tăng hai lần dù một Order được đặt một lần. Circuit breaker không bảo vệ correctness vì nó chỉ ngăn requests khi lỗi đủ nhiều.

### Biện pháp

Idempotency operation key, atomic reservation/domain transaction, kiểm tra outcome khi ACK unknown và phân biệt **retryable network event** với **retry-safe business mutation**. Test fault injection “commit then drop ACK”, không chỉ test “drop request before server”.

## 40. Case study C — HALF_OPEN tạo herd

### Bối cảnh

Breaker OPEN 10 giây; ngay khi hết thời gian, mọi waiting requests đều được phép đi vào backend.

### Hậu quả

Một shard vừa hồi phục lại nhận hàng nghìn in-flight calls, tăng queue, timeout và mở breaker trở lại. Hệ flapping.

### Biện pháp

Giới hạn HALF_OPEN probe permits, ramp up concurrency, không giữ unbounded waiting queue trước breaker, backoff jitter và đo recovery time. **Một successful probe** không phải bằng chứng có thể phục vụ full load ngay.

## 41. Case study D — Circuit breaker mở vì HTTP 404

### Bối cảnh

Một endpoint tìm Order cho 10.000 IDs không tồn tại. Java adapter map 404/NotFound thành generic exception, breaker đếm là dependency failure.

### Hậu quả

Breaker OPEN và chặn cả những GET/PUT hợp lệ dù DB khỏe.

### Biện pháp

Domain-aware classification: NotFound là valid business result, ConditionalConflict là concurrency outcome; chỉ system failures/throttling/timeouts phù hợp mới tác động breaker, tách latency/calls metrics. Test 404 storm **không mở breaker**.

## 42. Case study E — Một hot tenant chặn toàn cluster

### Bối cảnh

Tenant T1 chiếm 80% writes vào một partition key, throttle liên tục. Breaker đặt một instance cho toàn database.

### Hậu quả

T1 khiến breaker OPEN, healthy tenants T2..T100 cũng bị từ chối.

### Biện pháp

Tách per-tenant admission/rate budget và per-operation class; route-aware metrics, partition-key redesign nếu cần. Không tạo một breaker theo mỗi user/key vô hạn. Bảo vệ shared cluster capacity và fairness.

## 43. Case study F — Concurrency permit bị giữ khi backoff

### Bối cảnh

Developer lấy semaphore permit trước toàn bộ loop, rồi `Thread.sleep(500)` giữa attempts.

~~~text
maxConcurrentDbAttempts = 100
100 callers timeout once and sleep 500ms holding all permits
100 new callers are rejected even while no DB attempt is active
~~~

### Hậu quả

Hệ giảm useful capacity và tự tạo local overload. Breaker có thể lại đếm bulkhead rejection thành DB failure và mở sai.

### Biện pháp

Per-attempt permit trong `try/finally`, release trước backoff. Nếu cần outer logical admission cap, định nghĩa thành **hai limits riêng** và kiểm thử permit leaks/cancellation.

## 44. Case study G — API deadline 300 ms, SDK timeout 5 giây

### Bối cảnh

Gateway trả timeout sau 300 ms, nhưng Java worker vẫn đợi SDK 5 s rồi tiếp tục retry.

### Hậu quả

Người dùng đã nhận lỗi, nhưng hệ giữ threads/connections và gửi thêm attempts không có ích, tạo áp lực cục bộ kéo dài.

### Biện pháp

End-to-end budget propagation, cancellation/deadline checks trước mỗi attempt, driver-level per-operation timeouts phù hợp. Test bằng cách ghi **attemptStartedAt > callerDeadline** (phải bằng 0).

## 45. Case study H — Retry budget per pod tăng gấp bốn khi autoscale

### Bối cảnh

Mỗi Java pod được phép 20 retry attempts/s. Bình thường có 10 pods, trong sự cố autoscale lên 40.

### Kết quả

Budget lý thuyết tăng từ \(10\times20=200\) lên \(40\times20=800\) retries/s, đúng lúc DB quá tải.

### Biện pháp

Định nghĩa global/fleet attempt budget hoặc tính per-instance share có tái cân bằng; dashboard hiển thị fleet-wide actual attempts. Test autoscale trong fault; không chỉ benchmark fixed replica count.

## 46. Case study I — Throttling và fixed backoff

### Bối cảnh

5.000 DynamoDB requests cùng nhận throttling và tất cả retry đúng sau 100 ms.

### Hậu quả

Đỉnh retry mới lặp theo chu kỳ, tạo thundering herd; consumed capacity vẫn cao nhưng tỷ lệ thành công thấp.

### Biện pháp

Exponential backoff with jitter theo SDK/throttling hints, admission/partition-aware shaping và retry tokens. Đo phân phối retry start times, tránh đồng bộ spikes.

## 47. Case study J — Speculative executions không tính vào retry budget

### Bối cảnh

Cassandra driver dùng speculative execution cho reads. App metrics báo `retries=0` vì không có failure trước khi request thứ hai được gửi.

### Hậu quả

Backend attempts/s cao hơn logical requests/s dù retry metrics không tăng. Khi một replica chậm, speculative traffic gây thêm áp lực lên các replicas khác.

### Biện pháp

Đếm **mọi physical attempts**, kể cả hedge/speculative, phân loại chúng riêng. Chỉ speculative eligible idempotent reads, có concurrency/attempt budget và kiểm tra hiệu quả tail latency dưới load.

## 48. Case study K — Bulk indexing retry toàn bộ dù chỉ 2% items lỗi

### Bối cảnh

Elasticsearch/OpenSearch bulk request gồm 1.000 documents, 20 item failures/throttles; Java adapter không parse item results mà retry toàn bulk.

### Hậu quả

980 successful items bị gửi lại. Với operations có update scripts/increment counters, effects có thể sai; dù index by stable ID thì vẫn lãng phí I/O.

### Biện pháp

Parse item-level outcomes, retry **eligible failed items** với stable IDs/version semantics, bounded bulk concurrency và backoff. Test “partial success” khác “whole request failed”.

## 49. Case study L — Fallback stale sau write ACK

### Bối cảnh

User tạo Order v18, nhận DB ACK. Breaker cho follower read mở, API fallback sang cache v17 và trả 200 mà không cảnh báo.

### Hậu quả

Vi phạm read-your-writes/session contract (nếu đó là yêu cầu nghiệp vụ), user có thể đặt lại Order vì tưởng chưa tạo.

### Biện pháp

Giữ minVersion/session token, chọn read route mạnh/fallback có deadline hoặc trả pending/unavailable. Không dùng circuit breaker để **ẩn consistency gap**.

## 50. Case study M — Queue vô hạn làm instance OOM

### Bối cảnh

Java có `maxConcurrent=80`, nhưng executor queue unbounded. Khi DB chậm 2 giây, 20.000 HTTP requests bị xếp hàng.

### Hậu quả

Memory tăng, GC pauses, request timeouts ngay khi chưa thực hiện query; sau backend hồi phục, queue cũ gây tiếp overload.

### Biện pháp

Bound pending queue và max wait, admit/reject sớm, propagate cancellation, đo total user-visible latency không chỉ active DB call latency.

## 51. Case study N — Breaker bị mở bởi local pool exhaustion

### Bối cảnh

SDK connection pool max 10, Java backend call count 500 concurrent. Các callers hết hạn khi chờ pool, adapter đưa mọi timeout vào `dbServerUnavailable`.

### Hậu quả

Breaker OPEN dù server có thể còn khỏe; lỗi gốc nằm ở **client-side demand/pool sizing/configuration**, không nhất thiết ở DB.

### Biện pháp

Tách pool acquire timeout, server selection timeout, socket timeout và server response. Áp admission trước pool, xem active/in-use/pending và thử đo direct backend health riêng.

## 52. Case study O — Không có jitter khi cluster hồi phục

### Bối cảnh

Nhiều pods cùng mở breaker trong một network outage; sau `openFor=5s`, tất cả HALF_OPEN cùng thời điểm.

### Hậu quả

Mỗi pod chỉ cho một probe, nhưng 1.000 pods vẫn gửi **1.000 probes cùng lúc** vào shard mới khỏe. Per-instance probe cap không tự là fleet cap.

### Biện pháp

Jittered open duration/probe scheduling, fleet-aware budget và guarded ramp-up. Kiểm thử với số pods thực tế hoặc representative scale.

## 53. Case study P — Retry làm thay đổi quorum policy

### Bối cảnh

Write `LOCAL_QUORUM` thất bại; application tự “thử lại” bằng `ONE`, trả success nếu một replica đã ACK.

### Hậu quả

API trả thành công theo **durability/consistency policy yếu hơn** so với business contract ban đầu. Một failover sau đó có thể phát lộ data loss/inconsistency.

### Biện pháp

Retry giữ nguyên operation semantics, không thay CL/write concern trừ khi có **một API degraded mode được business phê duyệt rõ**. Với critical writes, fail-fast/pending reconciliation có thể an toàn hơn.

## 54. Bài tập thực hành

### Bài 1 — Retry amplification

Một API có ba tầng:

~~~text
Gateway maxAttempts = 2
Service maxAttempts = 4
SDK maxAttempts = 3
Original RPS = 600
~~~

1. Multiplier tối đa lý thuyết?
2. Backend attempts/s tối đa lý thuyết trong cùng steady window?
3. Vì sao thực tế có thể thấp hơn hoặc có burst cao hơn trong một cửa sổ nhỏ?
4. Metrics nào xác nhận số attempts thật?

### Bài 2 — `maxRetries` khác `maxAttempts`

Một SDK khai báo `maxRetries=3` trong khi Java policy `maxAttempts=2`.

1. Tối đa bao nhiêu attempts mỗi Java call của SDK?
2. Tổng multiplier khi nested Java→SDK?
3. Nếu docs nói `maxAttempts=3`, đáp án khác như thế nào?
4. Tại sao không nên tin tên `retryCount` nếu chưa đọc exact semantics?

### Bài 3 — Retry budget ratio

Service nhận 1.500 original requests/s, retry budget là 8% số originals.

1. Số retry attempts/s được phép theo mô hình steady state?
2. Total backend attempts/s mục tiêu nếu mỗi original có một backend call?
3. Nếu một logical request fan-out 4 shards, cần sửa mẫu số/thước đo thế nào?
4. Nếu 50 pods có local budget 10 retry/s/pod, liệu đã có global cap 8% chưa?

### Bài 4 — Per-request cap không đủ

1.000 requests/s, mỗi request maxAttempts=4, DB đang hoàn toàn unavailable.

1. Có thể phát tối đa bao nhiêu attempts/s khi không có backoff/budget khác?
2. Extra attempts ratio tối đa bao nhiêu?
3. Circuit breaker giúp gì?
4. Giới hạn đồng thời giúp gì?

### Bài 5 — Little's Law

Một service ổn định xử lý 800 requests/s, mean time in system tăng từ 50 ms lên 500 ms.

1. In-flight demand bình thường?
2. In-flight demand khi chậm?
3. Nếu limit là 100 active requests, điều gì xảy ra trong degraded mode?
4. Vì sao không lấy p99 latency thay mean vào công thức một cách máy móc?

### Bài 6 — Deadline budget

API deadline 250 ms. Đã dùng:

~~~text
Authentication/routing: 15ms
Queue wait:             20ms
Attempt 1:             100ms
Backoff:                40ms
Response reserve:       25ms
```

1. Còn bao nhiêu ms trước attempt #2?
2. Attempt #2 muốn timeout 100 ms có hợp lệ không?
3. Nếu chọn min(timeout, remaining), còn bao nhiêu sau reserve?
4. Tại sao phải giữ response reserve?

### Bài 7 — Backoff và jitter

Full jitter base=20 ms, cap=160 ms.

1. Miền delay cho retries #1..#5?
2. Vì sao 5.000 clients cùng delay 100 ms có nguy cơ herd?
3. Nếu deadline còn 30 ms nhưng backoff chọn 120 ms, làm gì?
4. Khi có server Retry-After hint, deadline ảnh hưởng thế nào?

### Bài 8 — Unknown write outcome

Một inventory reservation được commit nhưng ACK bị mất.

1. Vì sao timeout không chứng minh write fail?
2. Tại sao retry command như mới có thể oversell/double-reserve?
3. Thiết kế idempotency token/outcome lookup ra sao?
4. Nếu token cũ đã hết TTL, cần làm gì?

### Bài 9 — Conditional write conflict

Client cập nhật O900 v10→v11; nhận timeout. Retry điều kiện `version=10` nhận conflict.

1. Có thể kết luận lần đầu fail không?
2. Hai nguyên nhân khác nhau dẫn tới conflict là gì?
3. Dùng operationId và payload hash để xác minh ra sao?
4. Vì sao không đổi sang unconditional write?

### Bài 10 — Breaker window

Breaker có `windowSize=20`, `minimumCalls=20`, threshold failure 50%. Trong 20 backend calls có 11 failures thuộc loại được tính.

1. Failure rate?
2. Breaker có nên OPEN theo policy này?
3. Nếu 11 “errors” đều là expected NotFound, kết luận thay đổi ra sao?
4. Nếu chỉ có 5 calls với 4 failures, minimumCalls có tác dụng gì?

### Bài 11 — HALF_OPEN

Breaker OPEN 5s, half-open max probes=2. Khi hết 5s có 100 callers.

1. Tối đa bao nhiêu probes đi backend ngay trong half-open?
2. 98 callers còn lại nên nhận hành vi gì?
3. Nếu hai probes thành công, có nên xả cả backlog ngay không?
4. Nếu một probe timeout nhưng chưa report result, thiết kế permit lifecycle thế nào?

### Bài 12 — False-positive breaker

Một endpoint trả 70% NotFound hợp lệ và 30% success. Breaker coi mọi NotFound là server failure.

1. Lỗi classification ở đâu?
2. Hậu quả khi threshold 50%?
3. Nên đo domain NotFound và DB failures riêng thế nào?
4. Một test cụ thể để ngăn regression?

### Bài 13 — Bulkhead cap

Một Java instance có semaphore limit 80, concurrent arrivals 500, maxPending=100.

1. Tối đa bao nhiêu active calls?
2. Tối đa bao nhiêu requests có thể đợi theo budget?
3. Tối thiểu bao nhiêu requests phải được reject ngay nếu tất cả đến cùng lúc và chưa call nào xong?
4. Nếu SDK mỗi logical call fan-out 3 transport attempts, 80 outer permits có đồng nghĩa ≤80 transport attempts không?

### Bài 14 — Per pod vs fleet

20 pods × 60 concurrency permits, autoscale lên 45 pods.

1. Tổng attempt-capacity upper bound trước autoscale?
2. Sau autoscale?
3. Nếu DB chỉ chịu an toàn 1.500 in-flight attempts, có rủi ro gì?
4. Đề xuất fleet-level budget/admission.

### Bài 15 — Bulkhead giữ permit khi backoff

Có 100 permits; 100 callers đều fail đầu tiên và `sleep(500ms)` nhưng giữ permits.

1. DB attempts thực sự có thể bằng 0 trong lúc đó không?
2. Vì sao queue/rejections vẫn tăng?
3. Thiết kế release/reacquire thế nào?
4. Outer logical-request cap khác per-attempt cap ra sao?

### Bài 16 — Connection pool saturation

DB pool max 20, Java đồng thời có 500 callers. 480 callers chờ acquire rồi timeout.

1. Tất cả 480 có phải DB server failures không?
2. Nếu breaker đếm chúng, chuyện gì xảy ra?
3. Metrics nào chứng minh lỗi là local?
4. Có nên tăng pool lên 500 ngay không?

### Bài 17 — Throttling hot partition

DynamoDB table nhận tổng 5.000 RPS, nhưng 70% vào một key/partition và bị throttled, các keys khác vẫn khỏe.

1. Breaker toàn table có trade-off gì?
2. Jitter/backoff giải quyết điều gì và không giải quyết điều gì?
3. Per-tenant rate/admission giúp gì?
4. Khi nào cần sửa partition-key design?

### Bài 18 — Speculative execution

Cassandra driver gửi một request gốc rồi thêm một speculative request cho 20% logical reads.

1. Nếu có 1.000 logical reads/s, thêm bao nhiêu physical attempts/s trong mô hình?
2. Tỷ lệ extra attempts/initial?
3. Vì sao dashboard `retriesAfterFailure=0` đánh lừa?
4. Các operation nào không nên speculative?

### Bài 19 — Redis `INCR`

Java client gửi `INCR purchaseCount` rồi nhận timeout sau khi Redis đã thực thi.

1. Có thể retry `INCR` cùng request mù không?
2. Tính đúng count cần cơ chế gì?
3. Khi breaker OPEN, có nên cập nhật local memory rồi trả success không?
4. Nếu API trả 202, cần giải thích trạng thái nào?

### Bài 20 — MongoDB election

Trong replica set, primary mất 8 giây trước khi elected new primary; Java API deadline 300 ms.

1. Một request bị timeout lúc election có nên liên tục retry 8 giây không?
2. Retryable write support có thay thế business idempotency trong mọi trường hợp không?
3. Điều gì xảy ra nếu client chỉ hard-code old primary IP?
4. Cần test nào cho client cold-start sau failover?

### Bài 21 — Elasticsearch partial bulk success

Bulk có 1.000 index operations; 980 success, 20 thất bại do retryable throttling.

1. Có nên retry toàn 1.000 items?
2. Nếu retry chỉ 20 items, tiết kiệm bao nhiêu operations so với retry toàn bulk một lần?
3. Stable document IDs/version giúp gì?
4. Nếu một bulk item là script tăng counter, rủi ro gì?

### Bài 22 — Cosmos DB RU

Một container liên tục trả 429; SDK đã retry với backoff, application cũng có retry 4 attempts.

1. Cần kiểm tra điều gì trước khi tăng retries?
2. Per-partition RU/hotness có thể tạo lỗi cục bộ thế nào?
3. Vì sao 412 ETag conflict không được đối xử như 429?
4. User session token/causal consistency liên quan fallback thế nào?

### Bài 23 — Breaker một shard

Ba shard A/B/C, chỉ A lỗi 90%; B/C khỏe.

1. Circuit toàn cluster có thể gây availability loss thế nào?
2. Tách breaker theo từng key có vấn đề gì?
3. Chọn phạm vi trung gian nào?
4. Test routing/shard migration cần lưu ý gì?

### Bài 24 — Queue unbounded

10.000 requests/s đến, backend chỉ phục vụ 2.000/s và pending queue không giới hạn.

1. Trong 10 giây, nếu không có cancellation và số arrival/service không đổi, queue tăng khoảng bao nhiêu requests?
2. Vì sao queue backlog làm latency tăng?
3. Khi backend phục hồi, queue cũ có thể tạo tác động gì?
4. Bounded queue + reject policy nên chọn ra sao?

### Bài 25 — Successful p99 có bias

100 requests: 70 success dưới 200 ms, 30 timeout ở deadline 300 ms.

1. Tỷ lệ success-within-deadline?
2. Có thể báo user-facing p99 của mọi outcomes bằng 200 ms không?
3. Cần báo timeout/short-circuit và latency theo outcome thế nào?
4. Vì sao fail-fast có thể làm p99 success đẹp nhưng availability xấu?

### Bài 26 — Open-loop load test

Một closed-loop generator có 100 virtual users, mỗi user đợi response trước khi gửi request mới. DB chậm từ 50 ms lên 1 giây.

1. Vì sao offered load có thể giảm?
2. Little's Law giải thích số concurrent thế nào?
3. Mục tiêu open-loop generator khác gì?
4. Coordinated omission có thể che p99 ra sao?

### Bài 27 — Autoscale và budget

10 pods có 5 retries/s local cap mỗi pod; autoscale lên 40 pods trong sự cố.

1. Fleet cap lý thuyết trước và sau?
2. Tại sao retries tăng cùng autoscale làm lỗi nặng hơn?
3. Một global token budget có thể thiết kế thế nào?
4. Nếu coordination service lỗi, policy fail-open hay fail-closed theo risk nào?

### Bài 28 — Breaker count local rejects

DB khỏe, nhưng local bulkhead max 10 bị full; 100 callers nhận `BulkheadRejected`. Breaker đếm cả 100 là downstream failures.

1. Tại sao breaker OPEN là false positive?
2. Cần error taxonomy nào?
3. Làm sao đo backend success rate riêng?
4. Bộ thử regression nên inject overload local thế nào?

### Bài 29 — Bài tập tổng hợp

Order API có:

~~~text
Traffic: 2,000 logical RPS
API deadline: 350ms
NoSQL normal p99: 100ms
Fault: one partition 1.5s latency, 15% traffic
Fleet: 25 Java pods
Gateway retries: 2 attempts max
SDK retries: 3 attempts max
Current app retries: 4 attempts max
Business: no duplicate reservations
~~~

Thiết kế:

1. End-to-end attempts/deadline policy.
2. Fleet retry budget (mô tả scope và burst).
3. Breaker scope/failure classifier và half-open probes.
4. Concurrency limits cho critical writes vs analytics.
5. Idempotency/unknown outcome recovery.
6. Load test offered RPS và hot partition injection.
7. Dashboard SLI, metrics và stop conditions.
8. Recovery/failover drill và acceptance criteria.

### Bài 30 — Phản biện proposal

Một proposal:

> “Nếu NoSQL timeout, Java retry 10 lần trong khi SDK cũng retry. Tăng connection pool lên 1.000, không giới hạn queue vì muốn phục vụ mọi user. Circuit breaker mở khi có bất kỳ 5 exceptions nào, kể cả 404; sau 2 giây cho toàn bộ traffic qua lại. Nếu inventory write timeout, chuyển sang replica yếu hơn và ghi với consistency ONE. Dashboard chỉ đo p99 của successful requests.”

Hãy tìm **ít nhất mười lỗ hổng** và viết lại một test plan có retry budget, circuit breaker, concurrency cap, idempotency, consistency và đủ observability.

## 55. Gợi ý lời giải và cách suy luận

### 55.1. Bài 1 — Multiplier

\[
2\times4\times3=24\ \mathrm{attempts/logicalRequest}
\]

\[
600\times24=14\,400\ \mathrm{attempts/s}
\]

Đây là worst-case nested multiplier; actual throughput có thể giảm do timeouts, breaker và backoff, hoặc dồn thành bursts trong cửa sổ ngắn. Phải instrument **actual SDK/transport/backend attempts**.

### 55.2. Bài 2 — `maxRetries=3`

Nếu SDK thực hiện 3 retries sau một initial call thì mỗi Java attempt có **4 SDK attempts**, hai Java max attempts có thể tạo **8 backend attempts**. Nếu SDK `maxAttempts=3`, tổng là **6**. Đọc documentation và metrics thay vì đoán.

### 55.3. Bài 3 — Budget 8%

\[
1\,500\times0{,}08=120\ \mathrm{extraAttempts/s}
\]

Steady-state tổng khoảng **1.620 attempts/s** nếu mỗi original có một DB attempt và budget xét cùng scope. 50 pods × 10 retries/s có thể tạo tới 500 retries/s; **không** bảo đảm ratio 8% toàn fleet.

### 55.4. Bài 4 — Per-request cap

1.000 original RPS ×4 attempts = **4.000 attempts/s**, có thể có **3.000 retries/s** tức extra/initial ratio 300%. Circuit breaker chặn calls khi dependency lỗi, còn concurrency limiter khống chế số đang phục vụ; cần budget để giới hạn thêm attempts.

### 55.5. Bài 5 — Little's Law

\[
L_{\mathrm{normal}}=800\times0{,}05=40
\]

\[
L_{\mathrm{degraded}}=800\times0{,}5=400
\]

Limiter 100 active sẽ tạo queue/rejection/load shedding nếu demand vượt capacity; công thức dùng **mean time** trong hệ ổn định, không lấy p99 thế vào như dự báo chính xác.

### 55.6. Bài 6 — Deadline

Các bước ngoài attempt #2 chiếm:

\[
15+20+100+40+25=200\mathrm{ms}
\]

Thời gian tối đa còn dành cho attempt #2 **50 ms** nếu giữ 25 ms response reserve. Bắt đầu attempt #2 với 100 ms timeout rồi chờ toàn bộ sẽ vượt deadline. Nếu server/SDK không thể hoàn thành hữu ích trong 50 ms, skip retry hoặc trả controlled error.

### 55.7. Bài 7 — Full jitter

Với base=20 ms, cap=160 ms: các khoảng minh họa cho retries 1..5 lần lượt **[0,20], [0,40], [0,80], [0,160], [0,160] ms**. Nếu deadline còn 30 ms, không chọn delay 120 ms rồi tiếp tục; ràng buộc backoff/remaining time và reserved response budget.

### 55.8. Bài 8 — Commit then ACK lost

Timeout là **unknown outcome**. Giữ stable operation ID và payload identity; source of truth lưu committed result/idempotency state. Client lookup thay vì thực hiện reservation thứ hai như mới. TTL idempotency record phải phủ **business retry/redelivery window**, không chỉ HTTP deadline.

### 55.9. Bài 9 — Conditional conflict

Conflict có thể do **lần đầu đã commit v11** hoặc một actor khác cập nhật O900. Kiểm tra operationId, resultVersion và domain audit; không chuyển sang unconditional write vì sẽ ghi đè hợp lệ.

### 55.10. Bài 10 — Breaker threshold

\[
11/20=55\%
\]

Vượt 50% → breaker OPEN theo policy. Nếu đó là 11 NotFound hợp lệ thì **không được tính** là server failure. Với 5 calls chưa đủ `minimumCalls=20`, breaker thường chưa tính threshold để mở theo policy minh họa.

### 55.11. Bài 11 — HALF_OPEN

Với tối đa 2 probes, chỉ hai calls được vào backend tại một thời điểm half-open. 98 callers còn lại bị short-circuit/queue có giới hạn theo policy. Không xả toàn backlog ngay; cần ramp-up. Probe canceled/timed out phải giải phóng **half-open permission lifecycle**, tránh kẹt mãi.

### 55.12. Bài 13 — Bulkhead queue bound

80 active +100 waiting = **180 accepted/in-flight or pending** trong mô hình. Nếu 500 tới đồng thời và chưa cái nào xong, **ít nhất 320** phải bị reject (hoặc từ chối nhận) ngay. 80 outer permits **không** đảm bảo ≤80 transport attempts nếu SDK fan-out bên trong.

### 55.13. Bài 14 — Fleet concurrency

\[
20\times60=1\,200
\]

\[
45\times60=2\,700
\]

Nếu DB an toàn tới 1.500 in-flight, autoscale làm có thể vượt giới hạn. Cần fleet-level budget, per-route admission, phối hợp pod count và đo actual backend attempts.

### 55.14. Bài 15 — Permit held during backoff

100 calls cùng sleep giữ permit; actual backend attempts có thể tạm bằng **0** nhưng không client mới nào lấy được slot. Release per-attempt permit sau call; chỉ giữ outer request-context permit nếu chủ đích giới hạn toàn logical operation.

### 55.15. Bài 16 — Local pool contention

480 pool acquisition timeouts **không nhất thiết là DB server failures**. Tách poolWaitTimeout/connectionAcquire metrics khỏi socket/server failures; breaker đếm sai sẽ OPEN. Tăng pool lên 500 khi DB đã saturated có thể làm tình hình xấu thêm.

### 55.16. Bài 18 — Speculative attempts

\[
1\,000\times0{,}2=200
\]

Có thêm **200 physical attempts/s**, tương ứng extra ratio **20%** dù `retriesAfterFailure=0`. Đếm speculative/hedged attempts riêng; chỉ dùng cho operations được xem là idempotent/an toàn.

### 55.17. Bài 21 — Bulk partial success

Retry cả 1.000 thay vì 20 là gửi **980 operations thừa** trong một lượt. Stable IDs và versioning có thể giảm duplicate states nhưng không làm mọi script update idempotent; cần inspect item-level results.

### 55.18. Bài 24 — Unbounded queue

Trong 10 giây, theo dòng vào 10.000/s và phục vụ 2.000/s:

\[
Q(10s)\approx(10\,000-2\,000)\times10=80\,000
\]

requests đang chờ trong mô hình không cancellations. Latency/memory tăng; nên có bounded admission/rejection và cancellation để queue không tích lũy.

### 55.19. Bài 25 — Timeout outcomes

Success-within-deadline = **70%**, 30% timeout. P99 thành công ≤200 ms không phải p99 thực của toàn offered workload. Cần report timeout rate, reject rate và per-outcome latency, không gán censored backend latency bằng 300 ms như một giá trị exact.

### 55.20. Bài 27 — Per-pod budget autoscale

10 pods ×5 retries/s = **50/s**, 40 pods ×5 = **200/s**. Global budget hoặc coordinated per-pod shares tránh retry capacity tăng theo số pods. Nếu budget authority unavailable, chọn fail-closed/fail-limited theo product risk; không mở vô hạn retries.

### 55.21. Bài 28 — False breaker OPEN

Các `BulkheadRejected` là **local admission failures**; chúng không phải quan sát backend. Cần metrics `bulkheadRejected`, `circuitDenied` và `backendAttemptFailed` riêng. Test injected local overload với fake healthy DB phải cho thấy breaker CLOSED.

### 55.22. Bài 29 — Tổng thể

Khi maxAttempts là gateway=2, app=4, SDK=3:

\[
A_{\max}=2\times4\times3=24
\]

Potential all-traffic attempts tại 2.000 RPS:

\[
2\,000\times24=48\,000/s
\]

15% traffic vào hot partition tương đương **300 original requests/s**, có worst-case **7.200 attempts/s riêng hot path** nếu cả ba tầng đều nhân; cần phối hợp retry SDK/business/gateway và deadline 350 ms, không để retry chờ 1,5 giây. Một chương trình tốt giới hạn extra attempts fleet-wide, tách hot tenant/bulkhead, sử dụng idempotent reservations, per-route breaker và đo recovery.

### 55.23. Bài 30 — Ít nhất mười lỗi

1. Retry 10 lần ở app không xét SDK attempts.
2. Không có overall request deadline.
3. Không giới hạn retry budget toàn fleet.
4. Tăng pool lên 1.000 không chứng minh DB chịu được.
5. Queue vô hạn có thể OOM và coordinated omission.
6. 5 failures bất kỳ làm OPEN dù sample không đại diện.
7. 404 expected business response bị tính dependency failure.
8. Không có min calls/window/slow-call thresholds phù hợp.
9. HALF_OPEN cho mọi calls tạo herd.
10. Open duration không gắn recovery objective/probe cap.
11. Hạ consistency sang ONE làm thay đổi correctness.
12. Inventory write retry không có idempotency.
13. Fallback không công bố degraded/pending behavior.
14. Chỉ đo p99 success che timeouts/short circuits.
15. Không đo actual transport attempts và retry amplification.
16. Không có per-operation/tenant limits.
17. Không test auto-scaling/fault/recovery/cancellation.
18. Không tách client-side queue/pool failures với server failures.

Một kế hoạch thay thế: cấu hình **bounded retries với deadline**, token budget theo actual attempts, breaker có classifier/probe limits, separate critical bulkheads, no unsafe fallback, synthetic fault/load test ở offered rate ổn định, đo success/error/correctness và recovery.

## 56. Checklist 60 điểm trước khi bật policy resilience

### 56.1. Hiểu contract và deadline

1. Đã phân loại operations: read, conditional write, counter, transaction, batch, search không?
2. Có ghi consistency/read concern/write concern theo từng operation không?
3. Có biết API user-facing deadline, per-attempt timeout và queue wait budget không?
4. Có truyền remaining deadline từ gateway qua Java service đến SDK không?
5. Đo durations bằng monotonic clock trong một process chưa?
6. Có phân biệt maxAttempts và maxRetries của mọi tầng chưa?
7. Có lưu driver/SDK version và retry mode trong deployment config không?
8. Có xác định chính xác một backend attempt là gì, kể cả fanout/hedges không?
9. Có phân biệt write success, accepted/pending và unknown outcome không?
10. Có policy fail-closed khi không thể giữ strong consistency không?

### 56.2. Retry budget và idempotency

11. Mỗi operation có maxAttempts và retry classifier không?
12. Mọi retries đều kiểm tra remaining deadline không?
13. Có backoff with jitter và bounded burst không?
14. Có tôn trọng throttling hints của service/SDK khi có không?
15. Có retry budget theo legitimate originals thay vì cấp theo retries không?
16. Có global/fleet attempt budget hoặc per-pod share tương ứng autoscale không?
17. Có báo actual extra backend attempts ratio theo cùng scope không?
18. Có tính SDK/internal retries/speculative executions vào attempt budget không?
19. Có idempotency key/outcome lookup cho writes có unknown ACK không?
20. Có test commit-then-drop-ACK và duplicate-effect assertions không?

### 56.3. Circuit breaker

21. Breaker có window/minimum calls/threshold dựa trên workload thực không?
22. Có tách domain NotFound/validation/conflict khỏi backend failures không?
23. Có tách local bulkhead/pool rejections khỏi server failures không?
24. Có chọn breaker scope phù hợp cluster/region/operation/shard không?
25. Có bảo vệ healthy tenants/routes khi một partition lỗi không?
26. OPEN có thật sự ngừng backend attempts trên guarded path không?
27. HALF_OPEN có probe concurrency cap và lifecycle/cancel handling không?
28. Có test breaker flap và opening/closing hysteresis không?
29. Có phân biệt fallback hợp lệ với stale/unsafe fallback không?
30. Có giám sát state transitions, probes, short-circuit outcomes không?

### 56.4. Concurrency, queues và capacity

31. Có per-attempt in-flight limit rõ ràng không?
32. Có outer logical-request admission limit nếu cần không?
33. Có giới hạn pending queue và max wait không?
34. Có tránh giữ backend permit khi backoff không?
35. Có release permits trên success, exception, timeout và cancellation không?
36. Có tách critical writes/reads khỏi heavy analytics bulkhead không?
37. Có đo SDK connection pool wait/active/idle trước khi tăng pool không?
38. Có tính effective fleet concurrency khi autoscale/rollout không?
39. Có xem hot shards, fanout và per-tenant throughput khác với cluster mean không?
40. Có load shed trước khi queueing làm caller deadline hết không?

### 56.5. Fault/load testing và data correctness

41. Có baseline với representative dataset/partition skew/traffic mix không?
42. Có open-loop load test và ghi offered vs actual accepted RPS không?
43. Có tránh coordinated omission khi đo user-visible latency không?
44. Có fault timeout, throttle, leader election, hot partition, network delay không?
45. Có fault ở SDK transport và ở application local pool/bulkhead không?
46. Có test multi-layer retry amplification không?
47. Có test cancellation/deadline expiration và no-late-attempt không?
48. Có test HALF_OPEN/recovery ramp và post-recovery herd không?
49. Có test idempotency, no duplicate reservation/payment effects không?
50. Có test consistency không downgrade và session read-your-writes không?

### 56.6. Observability, runbook và rollout

51. Có tách logical request metrics với physical backend attempt metrics không?
52. Có SLI success-within-deadline và errors theo outcome không?
53. Có latency histograms per route, không lấy trung bình p99 của pods không?
54. Có metrics retry allowed/denied/tokens và breaker states không?
55. Có metrics active permits, pending queue, rejected requests, pool waits không?
56. Có correlated logs/traces mà không đưa PII/key values vào metric labels không?
57. Có rollback policy cho config mới nếu false-open/rejections tăng không?
58. Có stop conditions về API p99, error rate, DB attempts và correctness không?
59. Có documented runbook xử lý outage/unknown write outcomes/gradual recovery không?
60. Có owner và kết quả fault/load test được lưu cùng release/SDK config không?

## 57. Mẫu báo cáo kết quả bài kiểm thử

~~~yaml
testRun:
  id: "nosql-resilience-staging-20261114"
  environment: "staging"
  appVersion: "recorded-build-id"
  sdkVersion: "recorded-version"
  dependency: "orders-nosql-cluster"
  consistency:
    readPolicy: "recorded-mode"
    writePolicy: "recorded-mode"
  workload:
    offeredLogicalRps: 1000
    operationMix: "recorded-traffic-distribution"
    hotPartitionSharePercent: 20
  fault:
    type: "targeted-latency-and-timeout"
    startTime: "recorded"
    endTime: "recorded"
  protection:
    retryBudgetRatio: 0.10
    maxAttemptsPerRead: 3
    circuitWindow: 20
    circuitOpenForSeconds: 5
    maxHalfOpenProbes: 2
    maxDbAttemptsInFlightPerPod: 80
    maxQueueWaitMs: 20
  measurements:
    logicalSuccessWithinDeadlineRate: "measured"
    offeredVsAcceptedRps: "measured"
    backendAttemptAmplification: "measured"
    maxBackendInFlight: "measured"
    breakerOpenedAt: "measured"
    breakerClosedAt: "measured"
    rejectedByBulkhead: "measured"
    retryBudgetDenials: "measured"
    p99SuccessLatencyMs: "measured"
    timeoutRate: "measured"
    duplicateBusinessEffects: "measured"
    consistencyViolations: "measured"
  conclusion:
    objectivesMet: "true-or-false-after-evidence"
    blockers: []
    followUp: "recorded-action-items"
~~~

Các chuỗi `"measured"` là **placeholder**, không phải kết quả. Một report nghiệm thu phải liên kết tới test generator, traces, dashboard, sự kiện injected, dữ liệu expected/observed và config/commit/version; không lấy một screenshot duy nhất làm bằng chứng tổng thể.

### 57.1. Khi nào không được kết luận PASS?

- Thực tế offered RPS thấp hơn plan vì generator không phát đủ.
- Breaker mở nhưng không có đo **backend attempts đã ngừng**.
- Ratio retries “đạt 10%” nhưng không tính SDK speculative attempts.
- Concurrency cap “80” chỉ đo Java methods, trong khi SDK fanout >80.
- p99 success đẹp nhưng 30% requests timeout.
- Không có test commit-then-ACK-lost cho writes.
- Fallback giữ tỷ lệ HTTP 200 bằng data không đáp ứng session/consistency.
- Fault bị inject vào node không phục vụ shard/route đang test.
- Recovery chưa ổn định mà stop test ngay sau khi breaker CLOSED.

### 57.2. Đề xuất cách triển khai policy từ từ

Một rollout an toàn có thể:

1. **Observe-only:** Instrument SDK attempts, classifier, queue, breaker metrics; chưa short-circuit traffic.
2. **Staging fault/load:** Tìm ngưỡng và phân biệt saturation vs backend outage.
3. **Canary subset:** Bật limits trên ít instances/tenants noncritical theo approval.
4. **Compare:** User outcome SLI, backend attempts, false rejections, business invariants.
5. **Ramp:** Tăng dần traffic, giữ rollback switch và admission controls.
6. **Drill:** Chạy failover/overload recovery và xác minh breaker half-open.
7. **Operationalize:** Ghi runbook, alert thresholds, dashboard, owners.

Không chỉ “tăng retries để ổn định” mà không có evidence trước/sau.

## Kết luận

**Retry budget, circuit breaker và giới hạn đồng thời là ba cơ chế bổ sung**, không thay thế nhau:

- **Retry budget** ngăn lượng **attempts phát sinh thêm** vượt mức, đặc biệt khi nhiều tầng ứng dụng/SDK cùng retry.
- **Circuit breaker** ngăn tiếp tục đẩy công việc vào dependency có lỗi được chứng minh, và thăm dò hồi phục có giới hạn.
- **Concurrency limiter/bulkhead** ngăn số request đang chiếm threads, connection, memory và DB capacity vượt trần; queue phải được giới hạn tương ứng.
- **Timeout/deadline** là ranh giới thời gian chung, kiểm tra trước mỗi attempt và trong chờ permit/backoff.
- **Backoff với jitter** giúp tránh retry đồng loạt sau failover/throttling, nhưng không chữa được một hot partition cần redesign/admission.
- **Idempotency/outcome lookup** là yêu cầu của các writes có unknown result; “thử lại” không được gây duplicate business effect.
- **Consistency contract không thể tự nới lỏng khi lỗi.** Một write `QUORUM` không nên biến thành `ONE` mà API vẫn tuyên bố thành công như cũ.
- **Actual backend attempts** có thể lớn hơn số lần code Java gọi SDK do internal retries, redirects, fanout và speculative executions.
- **Breaker OPEN nhanh** không tự chứng minh hệ đạt availability; phải đo user success-within-deadline và errors, không chỉ p99 successes.
- **Fault/load tests phải có failure, saturation và recovery phases**, cùng representative data/skew và open-loop offered load.
- **Tính đúng dữ liệu là điều kiện nghiệm thu**, không phải metric phụ: no duplicated payment/reservation, no invalid stale fallback, no silent consistency downgrade.

Câu hỏi kiểm tra sau cùng:

> **“Khi NoSQL chậm hoặc không có quorum, một logical request có thể tạo tối đa bao nhiêu backend attempts, giữ bao nhiêu tài nguyên trong bao lâu, breaker có ngừng gửi tải và phục hồi đúng cách không, và điều gì chứng minh hệ không đánh đổi tính đúng dữ liệu lấy một HTTP 200?”**

Nếu có câu trả lời định lượng kèm fault/load test, traces và business invariant checks, một bộ resilience policy mới thực sự đáng tin cậy để bảo vệ hệ NoSQL trong sự cố.
