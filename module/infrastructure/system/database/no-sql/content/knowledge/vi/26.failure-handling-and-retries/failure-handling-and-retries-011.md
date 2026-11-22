# Giới hạn đồng thời, hàng đợi có giới hạn và chống khuếch đại tải

## 1. Mở đầu: khi retry biến một sự cố nhỏ thành sập cả cụm NoSQL

Một ứng dụng Java nhận khoảng 4.000 request/giây. Mỗi request có thể đọc document, cập nhật counter hoặc ghi transaction vào cụm NoSQL. Hệ chạy ổn định cho tới khi một shard bị chậm do compaction, một replica bị mất kết nối hoặc cluster đang failover.

Kịch bản có thể diễn ra:

~~~text
Bình thường:
  API -> NoSQL: 4.000 requests/s
  DB p99:        60 ms
  Error rate:    thấp

Sau khi một số replica chậm:
  DB p99:        900 ms
  Client timeout: 500 ms
  API tự retry 3 lần
  Gateway cũng retry
  Queue phía API tăng
  Connection pool bị giữ kín
  Retry mới tiếp tục làm DB chậm hơn
~~~

Nhiều đội chỉ nhìn thấy một “lỗi database” và tăng thời gian timeout, số thread, số connection hoặc số lần retry. Nhưng nếu **tải phát sinh đã vượt năng lực xử lý**, các thay đổi ấy có thể khiến hệ tệ hơn.

Một thiết kế chống quá tải phải trả lời đồng thời:

1. **Bao nhiêu request được phép vào hệ?** Đây là *admission control*.
2. **Bao nhiêu request được phép thực thi cùng lúc?** Đây là *concurrency limit*.
3. **Bao nhiêu request được phép chờ và chờ bao lâu?** Đây là *bounded queue*.
4. **Khi hết chỗ thì điều gì xảy ra?** Đây là *load shedding/backpressure*.
5. **Retry có thể tạo thêm bao nhiêu request?** Đây là *retry amplification*.
6. **Tài nguyên được chia cho tenant, shard, endpoint ra sao?** Đây là *bulkhead/fairness*.
7. **Làm sao phát hiện giới hạn đang quá thấp hoặc quá cao?** Đây là *metrics và điều khiển*.

Bài học **“Giới hạn đồng thời, hàng đợi có giới hạn và chống khuếch đại tải”** thuộc chương **“Lỗi phân tán và retry”** của module Database No SQL. Trọng tâm là bảo vệ database, API và người dùng khi một phần hệ thống chậm hoặc không khả dụng; không phải làm mọi request thành công bằng mọi giá.

### Mục tiêu học tập

Sau bài, bạn có thể:

- Phân biệt *rate limit*, *concurrency limit*, *connection pool* và *queue capacity*.
- Sử dụng định luật Little và mô hình hàng đợi để ước lượng tải đang xử lý.
- Hiểu vì sao hàng đợi vô hạn làm tăng latency, memory và retry storm.
- Tính tác động của retry nhiều tầng và fan-out trên NoSQL phân tán.
- Thiết kế bounded executor, semaphore, timeout, deadline và retry budget trong Java.
- Áp dụng bulkhead, token bucket, circuit breaker và backpressure theo đúng vai trò.
- Phân tích hot partition, quorum reads/writes, scatter-gather và multi-region timeout.
- Thiết kế phản hồi 429/503, idempotency và xử lý unknown commit outcome.
- Lập dashboard, canary, stress test, runbook cho overload.
- Chọn chính sách khác nhau cho read, write, background job và giao dịch quan trọng.

---

## 2. Bốn tài nguyên khác nhau: tốc độ, đồng thời, hàng đợi và kết nối

Các giới hạn sau liên quan nhưng **không thể thay thế nhau**:

| Khái niệm | Đại lượng | Giải quyết | Không tự giải quyết |
|---|---|---|---|
| Rate limit | Request/s hoặc token/s | Kiểm soát tốc độ đến trong cửa sổ | Tác vụ kéo dài đột ngột |
| Concurrency limit | Số request đang chạy | Giới hạn công việc đồng thời và tài nguyên | Bursts đến quá nhanh nếu không có admission |
| Queue capacity | Số request được chờ | Hấp thụ burst ngắn có kiểm soát | Tải trung bình vượt năng lực kéo dài |
| Connection pool limit | Số connection sử dụng | Giới hạn/ tái sử dụng kết nối tới DB | Số thao tác logical khi multiplexing hoặc ngoài pool |
| Deadline | Thời gian tối đa cho request | Chặn công việc quá hạn | Tải vào quá lớn nếu không reject |
| Retry budget | Số/ tỷ lệ retry hợp lệ | Ngăn retry khuếch đại tải | Workload gốc vượt capacity |
| Bulkhead | Giới hạn riêng theo nhóm | Tránh một nhóm chiếm hết tài nguyên | Overload toàn cục nếu tổng capacity sai |

Ví dụ một request update kéo dài 2 giây trong khi bình thường chỉ mất 20 ms. Dù request/s giữ nguyên, số thao tác đang thực thi có thể tăng khoảng 100 lần. Rate limit cố định không nhất thiết cứu được connection pool.

### 2.1. Rate limit là “vào nhanh bao nhiêu”

Token bucket có thể cho trung bình 500 requests/s và một burst 100 token. Nó kiểm soát **nhịp nhận request**, nhưng request chạy lâu hơn vẫn có thể tích tụ.

### 2.2. Concurrency limit là “đang làm bao nhiêu”

Semaphore 40 permits cho DB operation nghĩa nhiều nhất 40 thao tác cùng vượt qua điểm bảo vệ. Điều này thích hợp khi mỗi in-flight operation giữ connection, memory, DB CPU hoặc remote slot.

### 2.3. Bounded queue là “có bao nhiêu việc được phép đứng chờ”

Một queue tối đa 80 request có thể giúp chịu burst ngắn. Nhưng nếu DB phục vụ 100 request/s còn đầu vào 300 request/s liên tục, queue sẽ đầy; **không có queue hữu hạn nào xử lý được tải không cân bằng vô hạn thời gian**.

### 2.4. Giới hạn connection khác concurrency trong một số driver

Một connection có thể xử lý nhiều in-flight requests trong driver hỗ trợ multiplexing; một request cũng có thể chiếm nhiều connection khi fan-out/quorum. Do đó không dùng số connection như cách duy nhất đo concurrency; hãy quan sát actual in-flight operations và driver semantics.

---

## 3. Định luật Little: ước lượng số request đang nằm trong hệ

Với hệ ổn định trong điều kiện đo phù hợp, định luật Little:

\[
L=\lambda W
\]

trong đó:

- \(L\): số công việc trung bình đang ở **phạm vi hệ được xét**, bao gồm xử lý và chờ nếu phạm vi có queue.
- \(\lambda\): throughput hoàn thành/đến trung bình của hệ ổn định, tính bằng công việc mỗi giây.
- \(W\): thời gian một công việc ở trong phạm vi đó, tính bằng giây.

Ví dụ:

\[
\lambda=500\text{ req/s},\quad W=0.04\text{ s}.
\]

Khi đó:

\[
L=500\times0.04=20.
\]

Khoảng 20 request ở trong hệ theo trung bình nếu những giả định của định luật thỏa mãn.

### 3.1. Khi latency tăng, concurrency có thể tăng vọt

Giữ throughput đến 500 request/s, nhưng thời gian trong hệ tăng từ 40 ms lên 800 ms:

\[
L=500\times0.8=400.
\]

Nếu chỉ cấu hình 50 DB connections và không có admission control, phần còn lại sẽ chờ ở queue, connection pool hoặc tầng khác. Các queue chồng lên nhau có thể làm tổng latency tăng rất mạnh.

### 3.2. Không lấy công thức làm một SLA p99

Định luật Little nói về **giá trị trung bình trong hệ ổn định**. Nó không tự dự đoán p95/p99, thời gian phục vụ có đuôi dài, sự cố correlated failures, hoặc khả năng phản hồi trước deadline.

Không lấy kết quả \(L=20\) để kết luận “20 permits đảm bảo p99 dưới 40 ms”. Nên đo thực tế và chừa headroom.

### 3.3. Xác định đúng phạm vi của L và W

Nếu đang phân tích DB executor:

~~~text
Queue wait:    30 ms
DB execution:  50 ms
Total:         80 ms
~~~

Khi tính request **trong cả queue + executor**, \(W=80\) ms. Khi tính chỉ số request **đang chạy trên DB**, nên dùng 50 ms và throughput thực tế tương ứng.

Trộn latency end-to-end với concurrency một thành phần sẽ cho kết quả sai.

### 3.4. Queue stability

Gọi:

- \(\lambda\): tốc độ công việc đến.
- \(\mu\): năng lực phục vụ bền vững của nhóm workers/DB path.

Nếu trung bình lâu dài:

\[
\lambda\ge\mu,
\]

backlog không thể tự giảm về 0 bằng cách tăng chiều dài queue. Queue chỉ làm **trễ thời điểm từ chối**.

Khi \(\lambda<\mu\), queue vẫn có thể tăng tạm thời do bursts, variance và slow tasks. Vì thế cần cả **headroom, bounded queue và deadline**.

---

## 4. Phân biệt offered load, accepted load và completed load

Một hệ lúc quá tải có thể báo “throughput thành công ổn định”, khiến đội vận hành tưởng không có vấn đề.

Ví dụ:

~~~text
Offered requests:      9.000/s
Accepted into API:     6.000/s
Completed successfully:4.500/s
Rejected promptly:     3.000/s
Timed out after wait:  1.500/s
~~~

Nếu dashboard chỉ hiển thị 4.500 completed/s, nó che mất **9.000 offered/s**.

### 4.1. Các biến nên đo

- `offered_requests_total`: request tới admission boundary.
- `accepted_requests_total`: request được nhận để xử lý.
- `rejected_overload_total`: từ chối do capacity/budget.
- `inflight_requests`: đang làm việc trong phạm vi được bảo vệ.
- `queue_depth` và `queue_wait_ms`.
- `completed_requests_total`, `failed_requests_total`.
- `deadline_exceeded_total`.
- `client_canceled_total`.
- `retry_attempts_total`.
- `attempts_per_logical_request`.

Tên metric ở đây mang tính minh họa, không phải tên mặc định của một công cụ.

### 4.2. Thành công ít hơn không luôn nghĩa admission tệ

Khi cluster chỉ còn phục vụ được 4.500/s, từ chối nhanh 4.500 request dư thừa có thể bảo vệ p99 của request đã nhận. Nhận tất cả rồi để chúng timeout thường tạo thêm công việc lãng phí.

### 4.3. Một logical request có nhiều physical attempts

Một user nhấn **Đặt vé** một lần. Gateway gọi service, service gọi DB, mỗi tầng có retry. Đừng đếm các lần retry như nhu cầu nghiệp vụ mới.

Nên có:

~~~text
logicalRequestId = checkout-9001
attemptId        = attempt-1, attempt-2, ...
~~~

Để phân biệt demand gốc và khuếch đại do hệ tự tạo.

---

## 5. Bản chất của hàng đợi vô hạn: hoãn lỗi thay vì chữa lỗi

Một `LinkedBlockingQueue` mặc định không giới hạn hợp lý hoặc một queue tự xây bằng list vô hạn có thể khiến request tích tụ.

~~~mermaid
flowchart LR
    C["Clients"] --> A["API"]
    A --> Q["Unbounded queue"]
    Q --> W["Workers"]
    W --> D["NoSQL"]
    D -. "Chậm / timeout" .- W
    Q --> M["Memory tăng"]
    Q --> T["Queue wait vượt deadline"]
    T --> R["Clients retry"]
    R --> A
~~~

### 5.1. Memory có thể bị ăn hết

Nếu mỗi queued job giữ 32 KiB state, 100.000 job có thể giữ khoảng:

\[
100000\times32\text{ KiB}=3\,200\,000\text{ KiB}
\approx3.05\text{ GiB}.
\]

Đây là mô hình minh họa; request thực có thể giữ object graph, closure, trace context, body buffer và cả connection/response state nên footprint phức tạp hơn.

### 5.2. Request đã hết hạn vẫn tiêu tốn tài nguyên

Ví dụ client deadline 500 ms, nhưng queue wait 1,5 giây. Khi worker bắt đầu, người dùng đã bỏ cuộc. Nếu server vẫn truy vấn DB và ghi kết quả vào response không còn người nhận, hệ tiêu tốn capacity vô ích.

### 5.3. Queue càng lớn có thể càng làm p99 tệ

Giả sử throughput phục vụ ổn định 200/s và queue đang có 1.000 request, thời gian xả queue theo mô hình trung bình lý tưởng ít nhất gần:

\[
T_{\text{drain}}\approx\frac{1000}{200}=5\text{ s}
\]

khi không có thêm arrivals, bỏ qua thời gian các request đang chạy và biến thiên service time.

Một API có SLO 200 ms **không được lợi** từ việc “chịu được” queue 1.000 request nếu chúng đã chờ hàng giây.

### 5.4. Garbage collection và retry còn khuếch đại

Queue lớn tăng heap pressure/GC. GC làm worker chậm, worker chậm khiến queue tăng, client timeout làm retry tăng. Đây là **vòng phản hồi dương**.

### 5.5. Giới hạn queue cần dựa trên thời gian chờ

Không chọn queue capacity chỉ vì bộ nhớ còn dư. Nếu hệ phục vụ 200/s và queue budget chỉ 100 ms, queue chứa 1.000 request là phi lý cho đường interactive. Nên dựa vào observed service rate, deadline và tail latency.

---

## 6. Bounded queue: từ chối sớm để bảo vệ hệ

Một bounded queue đặt số request được phép chờ:

~~~text
Active workers: 20
Waiting queue: 40
Additional request:
  if active+waiting capacity available -> accept
  else -> reject as overloaded
~~~

Điểm quan trọng: **hàng đợi đầy không phải lỗi logic bất thường; đó là một kết quả admission có chủ đích**.

### 6.1. Những chính sách khi queue đầy

| Chính sách | Hành vi | Khi nào phù hợp |
|---|---|---|
| Reject immediately | Trả 429/503 hoặc lỗi typed | Interactive requests, deadline ngắn |
| Wait for a bounded time | Chờ permit/chỗ trống tối đa X ms | Work có deadline đủ dài |
| Drop oldest | Loại công việc cũ để nhận mới | Telemetry/coalescing có thể mất dữ liệu |
| Drop newest | Bỏ việc mới | Một số streams best-effort |
| Persist to durable queue | Nhận intent, xử lý async | Business workflow có trạng thái `PENDING` |
| Coalesce/deduplicate | Gộp nhiều yêu cầu giống nhau | Cache refresh, metrics, same-key reads |
| Synchronous fallback | Xử lý ở nguồn khác | Chỉ khi fallback thật sự có capacity |
| Caller-runs | Thread gọi tự chạy job | Chỉ khi được thiết kế backpressure cẩn thận |

Không sử dụng drop policy cho giao dịch tiền hoặc cấp phát tài nguyên nếu chưa có business contract cho phép.

### 6.2. `CallerRunsPolicy` có bẫy

Trong Java executor, `CallerRunsPolicy` có thể khiến thread HTTP request phải tự thực thi tác vụ DB khi queue đầy. Điều này tạo backpressure nhưng cũng có thể:

- Giữ event loop/request thread lâu.
- Làm nghẽn acceptor.
- Lan nghẽn từ DB lên gateway.
- Vượt deadline nhưng vẫn thực thi.

Cần hiểu execution model trước khi dùng; **không mặc định caller-runs an toàn hơn reject**.

### 6.3. Queue có thể bounded nhưng vẫn chờ quá lâu

Có 100 chỗ chờ không nghĩa tất cả request trong queue còn hữu ích. Cần kiểm tra deadline **trước khi xếp hàng, khi được dequeue và trước lúc bắt đầu side effect**.

### 6.4. Bounded queue in-memory không phải durable message queue

Nếu process crash, những job chỉ nằm trong RAM có thể mất. Với workflow async cần cam kết xử lý sau ACK, phải dùng durable queue, transaction/outbox hoặc cơ chế persistence phù hợp.

**HTTP 202 Accepted chỉ có ý nghĩa nếu ứng dụng mô tả rõ intent đã được lưu bền tới đâu và chưa hoàn thành business action.**

---

## 7. Concurrency limit nên đặt ở đâu?

Một request xuyên các tầng:

~~~text
Client
  -> Gateway
    -> Checkout API
      -> Inventory Service
        -> NoSQL router
          -> Shard A/B/C
~~~

Có thể cần giới hạn ở nhiều vị trí, nhưng phải biết mỗi giới hạn bảo vệ tài nguyên gì.

### 7.1. Gateway/global admission

Bảo vệ toàn hệ khỏi tốc độ request bên ngoài quá lớn, abuse hoặc traffic spike. Có thể áp rate limit theo token, người dùng, IP, tenant hoặc operation.

Nhưng global rate limit không nhận biết tốt tình huống chỉ một shard đang nóng.

### 7.2. Service-level concurrency

Ví dụ tối đa 100 checkout operations đang chờ/đang xử lý. Bảo vệ service thread, memory, connection pool và downstream call volume.

### 7.3. Dependency-level bulkhead

Nếu service gọi Inventory DB và Search Engine, mỗi dependency nên có vùng hạn mức riêng:

~~~text
Inventory:
  max in-flight = 40

Search:
  max in-flight = 80

Analytics:
  max in-flight = 10
~~~

Nếu Search quá tải, nó không chiếm hết permits của Inventory.

### 7.4. Per-shard/per-key limits

Một tenant hot hoặc một partition quá tải không nên chiếm hết concurrency dành cho toàn cụm.

Ví dụ:

~~~text
Global DB in-flight <= 200
Per-shard in-flight <= 30
Per-tenant in-flight <= 15
Admin report in-flight <= 5
~~~

Các con số minh họa; phải chọn từ benchmark và capacity thật.

### 7.5. Không nhân mọi giới hạn một cách ngây thơ

Nếu 10 API instances mỗi instance cho phép 100 DB calls, hệ có thể tạo **1.000 in-flight calls**. Một limit local không phải cluster-wide limit.

Muốn giới hạn toàn cục cần cách phối hợp/admission theo capacity toàn hệ, hoặc phân ngân sách theo instance cùng kế hoạch autoscaling.

---

## 8. Rate limiter: token bucket và leaky bucket

**Rate limiting** và **concurrency limiting** thường được dùng cùng nhau.

### 8.1. Token bucket

Một bucket có:

- Sức chứa \(B\) tokens.
- Tốc độ bổ sung \(r\) tokens/giây.
- Mỗi request tiêu thụ số token theo cost policy.

Ví dụ:

~~~text
Refill rate: 100 tokens/s
Burst capacity: 200 tokens
1 simple read: 1 token
1 admin query: 20 tokens
~~~

Có thể xử lý burst ngắn tới ngân sách, rồi tốc độ bị điều tiết.

### 8.2. Leaky bucket

Leaky bucket cho phép giữ một lượng công việc có giới hạn và phát ra theo tốc độ tương đối ổn định, tùy implementation. Nó hữu ích khi downstream cần nhịp ổn định, nhưng nếu giữ request quá lâu vẫn vi phạm deadline.

### 8.3. Concurrency và rate không tương đương

Giả sử cùng 100 request/s:

- Request loại A mất 10 ms -> số in-flight trung bình khoảng 1.
- Request loại B mất 1 s -> số in-flight trung bình khoảng 100.

Một rate limit 100/s cho cả hai **không bảo vệ giống nhau** trước tài nguyên bị giữ lâu. Cần concurrency limit.

### 8.4. Weighted cost

Một point lookup và global scatter-gather query có chi phí khác nhau. Có thể tính token/capacity theo:

- Số shard bị chạm.
- Số record/index keys dự kiến.
- Độ phức tạp aggregate.
- Read/write units của dịch vụ managed.
- Tenant tier hoặc priority.

Cost estimate cần được hiệu chỉnh bằng telemetry; query planner có thể chọn plan khác dự đoán.

---

## 9. Chống khuếch đại tải: tại sao nhiều tầng retry nguy hiểm?

Giả sử request đi qua ba tầng A → B → C. Mỗi tầng được cấu hình **tối đa 3 attempts**, kể cả lần đầu.

Nếu tất cả đều retry hết và mỗi attempt tới C thực sự xảy ra:

\[
3\times3\times3=27
\]

lần gọi tới C cho **một ý định ban đầu** trong trường hợp xấu nhất.

~~~mermaid
flowchart TD
    U["1 logical client request"] --> A["A: up to 3 attempts"]
    A --> B["B: up to 3 attempts per A attempt"]
    B --> C["C: up to 3 attempts per B attempt"]
    C --> R["Up to 27 deepest attempts"]
~~~

Khi cả hệ thống đang lỗi, khả năng nhiều tầng cùng retry hết là cao hơn, nên tải có thể bị khuếch đại đúng lúc backend yếu nhất.

### 9.1. Công thức giới hạn

Nếu có k tầng retry độc lập về cơ chế, tầng i cho tối đa \(a_i\) attempts, cận trên số call tới tầng sâu trong mô hình nested retries:

\[
A_{\max}=\prod_{i=1}^{k}a_i.
\]

Đây là **cận trên**, không có nghĩa mọi request thực tế đều sinh đủ số ấy.

### 9.2. Kỳ vọng attempt cho một tầng

Nếu mỗi attempt thất bại độc lập với xác suất \(p\), dừng khi thành công hoặc đạt tối đa \(m\) attempts:

\[
E[A]=1+p+p^2+\cdots+p^{m-1}.
\]

Với \(m=3,p=0.1\):

\[
E[A]=1+0.1+0.01=1.11.
\]

Với \(p=0.8\):

\[
E[A]=1+0.8+0.64=2.44.
\]

**Giả định độc lập thường không đúng khi cluster overload:** lỗi có tương quan theo thời gian, node, partition và network. Vì thế retry có thể làm tình hình nghiêm trọng hơn mô hình đơn giản.

### 9.3. Tải retry phụ thuộc lỗi

Giả sử bình thường có 2.000 logical requests/s, khi sự cố mỗi request phát trung bình 2,5 attempts tới DB:

\[
\lambda_{\text{physical}}
=2000\times2.5
=5000\text{ attempts/s}.
\]

Backend vốn giảm năng lực từ 2.500/s xuống 1.500/s giờ phải đối diện 5.000 attempts/s. Retry làm **lệch cán cân xa hơn**.

### 9.4. Retry storm là vòng phản hồi dương

~~~text
DB chậm -> Timeout -> Retry
  -> In-flight tăng -> Queue dài
  -> DB/connection pool chậm hơn -> Thêm Timeout
  -> Thêm Retry -> ...
~~~

Muốn dừng vòng lặp cần **giảm tải phát sinh**, không chỉ tăng số connection hoặc timeout.

---

## 10. Retry đúng tầng và retry budget chung

Một nguyên tắc thường hữu ích: **chỉ một tầng chịu trách nhiệm retry cho một loại lỗi và một thao tác cụ thể**, thay vì gateway, SDK, service và driver cùng tự retry không biết nhau.

### 10.1. Vì sao retry một nơi dễ quản hơn?

Tầng chủ động retry có thể biết:

- Thời hạn request còn bao nhiêu.
- Operation có idempotent không.
- Có thể kiểm tra outcome không.
- Backend đang overload không.
- Attempt trước chạm shard nào.
- Tổng số attempt đã tiêu tốn.
- Retry có được phép khi lỗi là `429/503` không.

### 10.2. Không tắt mọi retry một cách máy móc

Một số driver tự xử lý topology refresh hoặc retryable reads/writes theo semantics đã công bố. Không nên vô hiệu hóa bừa nếu nó giải quyết các transient failures một cách đúng đắn.

Điều cần làm là **kiểm kê các tầng retry**, giới hạn tổng attempt/deadline, tránh cùng lỗi bị replay không kiểm soát.

### 10.3. Retry budget theo tỷ lệ

Thay vì cho mọi request retry ba lần, có thể đặt giới hạn aggregate:

~~~text
100 requests gốc thành công/được nhận
Cho phép tối đa 5 hoặc 10 retry attempts
trong cùng cửa sổ và workload class.
~~~

Đây là ví dụ chính sách, không phải tỷ lệ chuẩn. Retry budget giúp backend không nhận vô hạn secondary traffic khi success rate giảm.

### 10.4. Retry budget theo request

Một request có thể có:

~~~text
Total deadline: 600 ms
Max attempts:  2
Maximum retry wait: 100 ms
Remaining time before attempt 2: 250 ms
~~~

Nếu còn 15 ms trong khi DB p50 là 40 ms, một retry mới có thể không có giá trị. Dừng và trả kết quả phù hợp tốt hơn.

### 10.5. Không retry business rejection

`ConditionalCheckFailed`, duplicate request với payload khác, out-of-stock hoặc validation error không phải transient failure để retry vô hạn. Phân loại lỗi trước khi quyết định.

---

## 11. Exponential backoff và jitter

Một chính sách backoff cơ bản:

\[
b_n=\min(b_{\max},b_0 2^{n-1})
\]

với \(n\) là số lần retry (không tính lần đầu), \(b_0\) là thời gian chờ cơ sở.

### 11.1. Vì sao cần jitter?

Nếu 10.000 clients timeout cùng một lúc và đều chờ đúng 100, 200, 400 ms, họ sẽ tiếp tục **đập vào backend theo từng làn sóng đồng bộ**.

Full jitter chọn thời gian chờ ngẫu nhiên:

\[
wait_n\sim U(0,b_n).
\]

Nhờ vậy request trải đều hơn theo thời gian, giảm khả năng retry đồng pha.

### 11.2. Ví dụ

~~~text
Initial attempt: immediate
Retry 1 cap:     100 ms -> wait random [0,100]
Retry 2 cap:     200 ms -> wait random [0,200]
Retry 3 cap:     400 ms -> wait random [0,400]
Total request deadline: 800 ms
~~~

Đây là ví dụ cơ chế, không phải cấu hình phù hợp cho mọi operation. Thời gian chờ phải nằm trong **deadline tổng**, tránh request đã hết hạn vẫn cố retry.

### 11.3. Dùng Retry-After khi hợp lý

Một response `429 Too Many Requests` hoặc `503 Service Unavailable` có thể mang hướng dẫn `Retry-After`. Client có thể tôn trọng nếu thời hạn nghiệp vụ cho phép và không tạo synchronized stampede.

`Retry-After` không đảm bảo backend sẽ khỏe đúng lúc đó; cần thêm jitter hoặc retry budget theo thiết kế.

### 11.4. Retry chậm vẫn có thể sai

Backoff làm giảm tốc độ nhưng **không sửa tính không idempotent**. Retry một `chargeCreditCard()` với request ID mới vẫn có thể double-charge dù chờ 30 giây.

---

## 12. Deadline, timeout và queue age

Phân biệt:

- **Connect timeout:** thời gian thiết lập connection.
- **Acquire timeout:** thời gian chờ connection/permit.
- **Queue timeout:** thời gian được phép chờ trong queue.
- **Operation timeout:** thời gian chờ DB execution.
- **End-to-end deadline:** mốc toàn request phải hoàn thành hoặc dừng.

### 12.1. Deadline tổng quan trọng hơn các timeout rời

Nếu API có SLO 500 ms nhưng các bước:

~~~text
Queue wait:         400 ms
Connection acquire: 300 ms
DB operation:       500 ms
Retry wait:         200 ms
DB retry:           500 ms
~~~

tổng có thể vượt xa kỳ vọng. Không nên cấp cho mỗi tầng một timeout 500 ms mà không tính tổng.

### 12.2. Deadline propagation

API nhận deadline, rồi truyền budget còn lại xuống các dependency:

~~~text
HTTP budget = 500 ms
Auth takes 30 ms
Queue wait takes 20 ms
Remaining = 450 ms

Inventory DB timeout <= remaining minus response reserve
~~~

Các ví dụ dùng số minh họa. Thực tế cần chừa thời gian mạng, serialization và trả response.

### 12.3. Dùng đồng hồ monotonic cho duration

Trong Java, `System.nanoTime()` thích hợp để tính thời gian trôi qua. Không dựa hoàn toàn vào `System.currentTimeMillis()` cho elapsed-time deadline vì đồng hồ hệ thống có thể được điều chỉnh.

### 12.4. Hủy request không chắc hủy DB write

Client cancel `CompletableFuture` hoặc mất kết nối HTTP **không chắc** DB operation đã dừng hay chưa commit. Đặc biệt sau write timeout, outcome có thể là `UNKNOWN`; cần idempotency và đối soát.

### 12.5. Queue nên loại công việc hết hạn trước khi chạy

Nếu một job đến lượt sau deadline, tránh gọi DB chỉ để tạo thêm tải. Với side effect ghi, phải kiểm tra xem nó **đã được bắt đầu** chưa để tránh nhầm cancellation với rollback.

---

## 13. Admission control: quyết định trước khi dùng tài nguyên đắt

Một đường xử lý bảo vệ:

~~~mermaid
flowchart TD
    R["Incoming request"] --> V["Authenticate, validate, classify"]
    V --> B{"Remaining deadline sufficient?"}
    B -- "No" --> E["Reject expired request"]
    B -- "Yes" --> T{"Tenant / rate budget?"}
    T -- "No" --> Q["429 / policy rejection"]
    T -- "Yes" --> P{"Concurrency permit available?"}
    P -- "No" --> O["503/429, retry hint"]
    P -- "Yes" --> D["Execute bounded DB operation"]
    D --> F["Release permit in finally"]
~~~

Luồng minh họa không yêu cầu mọi request phải chờ blocking. Admission sớm giúp từ chối trước khi cấp connection, transaction state hoặc quét dữ liệu.

### 13.1. Đặt giới hạn càng gần tài nguyên càng tốt

Một global gateway limit có thể không biết DB đang có hot shard. Một per-shard limiter tại service hoặc driver adapter có thể phản ứng trực tiếp hơn.

Tuy nhiên, nếu chỉ hạn chế ở DB server sau khi API đã tạo 20.000 request objects, application vẫn có thể quá tải memory. **Bảo vệ nhiều tầng với phạm vi rõ**, không duplicate retries.

### 13.2. Fail fast có thể tốt hơn fail slow

Khi queue/permit không còn, trả 503 nhanh với trạng thái overload minh bạch giúp client:

- Không chờ timeout rồi retry không đúng lúc.
- Có thể fallback/hiển thị thử lại sau.
- Giữ connection và thread cho request còn khả năng hoàn thành.

### 13.3. Trả 429 hay 503?

Thông thường:

- `429` phù hợp giới hạn tốc độ/quota theo client/tenant, có thể kèm `Retry-After`.
- `503` phù hợp hệ/dependency tạm không đáp ứng capacity.

Đó là **hướng diễn đạt API**, không phải luật cứng thay cho hợp đồng hiện tại. Cần trả message rõ, thống kê retryable vs permanent, và tránh rò rỉ thông tin nội bộ.

### 13.4. Đừng báo đã hoàn tất nghiệp vụ khi chỉ queue được request

Nếu API nhận request vào durable queue, có thể trả `202 Accepted` với request ID và status endpoint. Không được trả `CONFIRMED` nếu transaction authoritative chưa xảy ra.

---

## 14. Bulkhead: ngăn một lỗi lan sang chức năng khác

**Bulkhead** vay mượn ý tưởng các khoang chống ngập của tàu: mỗi workload có vùng tài nguyên riêng.

Ví dụ ứng dụng có:

~~~text
DB point reads:            80 permits
DB inventory transactions: 30 permits
Search queries:           40 permits
Admin analytics:           5 permits
Background reindex:        5 permits
~~~

Nếu Search chậm 10 giây, nó không chiếm toàn bộ worker permits dành cho Inventory.

### 14.1. Bulkhead theo dependency

Tách:

- Connection pool cho DB transactional nếu cần và được hỗ trợ.
- Executor hoặc semaphore cho search.
- Worker pool riêng cho batch.
- Queues riêng cho user-facing và background tasks.

### 14.2. Bulkhead theo tenant

Một tenant lớn có thể gửi 90% traffic. Nếu mọi tenant dùng một queue FIFO chung, tenant nóng có thể chiếm phần lớn chỗ chờ.

Giải pháp:

- Per-tenant concurrency budgets.
- Weighted fair queueing.
- Giới hạn queue riêng hoặc quota.
- Priority lanes cho traffic critical.
- Global cap bổ sung để bảo vệ toàn cụm.

### 14.3. Bulkhead có thể làm lãng phí tài nguyên nếu quá cứng

Nếu nhóm A rảnh nhưng nhóm B quá tải, quota cứng có thể khiến capacity ở A bỏ trống. Một thiết kế linh hoạt có thể cho mượn một phần permits dưới global cap, với ngưỡng và ưu tiên rõ.

Không cần tự triển khai thuật toán fairness phức tạp nếu workload nhỏ; bắt đầu bằng giới hạn quan sát được rồi điều chỉnh.

### 14.4. Bulkhead không chữa shard nóng

Hai API instances có bulkhead tốt nhưng cùng query vào một partition hot vẫn có thể overload partition. Cần per-key/per-partition limits hoặc thay data model.

---

## 15. Circuit breaker khác concurrency limiter

Một **circuit breaker** quan sát lỗi/độ trễ và có thể tạm ngăn gọi dependency khi nó có vẻ không đáp ứng.

Các trạng thái thường được minh họa:

~~~text
CLOSED -> gọi bình thường, đo lỗi
OPEN -> từ chối nhanh trong khoảng
HALF_OPEN -> cho một số probe có kiểm soát
~~~

### 15.1. Hai cơ chế giải quyết câu hỏi khác nhau

- **Concurrency limiter:** “Có bao nhiêu việc được phép chạy ngay lúc này?”
- **Circuit breaker:** “Dependency có đang trong trạng thái nên tạm dừng gọi không?”

Một dependency có thể vẫn trả thành công nhưng quá chậm; concurrency limit bảo vệ in-flight resources. Ngược lại, lỗi 100% ngay lập tức có thể không làm in-flight tăng cao; circuit breaker giảm lưu lượng vô ích.

### 15.2. Không mở circuit chỉ vì business rejection

Out-of-stock, CAS conflict hoặc request validation thất bại là kết quả nghiệp vụ hợp lệ, không nên được tính như dependency outage.

### 15.3. Half-open cần probe budget

Nếu circuit mở xong cùng lúc cho 10.000 request đi qua, nó có thể gây retry storm mới. Half-open thường cần giới hạn số request thử và điều kiện đóng/mở phù hợp.

### 15.4. Fallback cũng dùng tài nguyên

Chuyển toàn bộ traffic từ DB A sang DB B khi A lỗi có thể khiến B bị overload. Bulkhead và admission phải bao gồm cả nhánh fallback, tránh “chuyển bệnh” sang hệ dự phòng.

---

## 16. Adaptive concurrency: giảm in-flight khi latency xấu

Một concurrency limit cố định có thể phù hợp khi capacity ổn định. Nhưng NoSQL thường biến động vì:

- Compaction/repair.
- Failover và leader election.
- Autoscaling hoặc resharding.
- Network latency.
- Hot partitions.
- Tăng tải theo giờ.
- Backup/index build.
- Shared cloud resources.

Một **adaptive concurrency limiter** dùng tín hiệu như latency, queue wait, errors và outstanding requests để thay đổi giới hạn trong khoảng an toàn.

### 16.1. Ý tưởng AIMD

Một bộ điều khiển đơn giản có thể:

- Tăng giới hạn chậm khi latency khỏe và resource còn dư.
- Giảm giới hạn mạnh khi phát hiện congestion.
- Giữ cooldown/hysteresis để tránh dao động.
- Có min/max và safety thresholds.

Ví dụ minh họa:

~~~text
Limit 40, latency ổn -> 41 -> 42
P99 tăng mạnh -> giảm còn 30
Sau recovery ổn định -> tăng lại từ từ
~~~

Đây không phải công thức chuẩn; phải đánh giá bằng load test và telemetry thực.

### 16.2. Bẫy dùng p99 làm tín hiệu tức thời

p99 có thể nhiễu và phụ thuộc volume. Giảm concurrency quá nhanh khi có vài sample hoặc tăng quá nhanh sau một khoảng rảnh có thể gây oscillation.

Cần:

- Measurement window đủ mẫu.
- Hysteresis/cooldown.
- Phân biệt lỗi upstream/downstream.
- Quan sát throughput và queue delay.
- Chặn thay đổi đột ngột.
- Đảm bảo giới hạn không vượt ngân sách cluster.

### 16.3. Độ trễ thấp không tự nghĩa còn capacity

Khi đang reject 80% request, p99 của những request đã được nhận có thể rất tốt. Adaptive controller không nên nhìn duy nhất latency thành công mà bỏ qua offered load và rejection rate.

### 16.4. Không dùng autoscaling như phản ứng duy nhất

HPA hoặc auto-scale database cần thời gian khởi tạo node, chuyển shard, làm nóng cache và ổn định. Khi tốc độ đến vượt năng lực hiện tại, admission/bounded queues vẫn cần bảo vệ **trong cửa sổ chờ scale**.

---

## 17. Fan-out có thể khuếch đại tải ngay cả khi không retry

Một request search có thể chạm 16 shard:

~~~text
1 user query
  -> 16 shard queries
  -> mỗi shard đọc 2 replica tùy consistency
~~~

Số thao tác mạng có thể lớn hơn 16. Nếu user query retry 2 lần, fan-out lặp lại.

### 17.1. Công thức tải downstream đơn giản

Nếu:

- \(Q\): logical requests/s.
- \(F\): số nhánh downstream trung bình.
- \(A\): số attempts trung bình mỗi nhánh.

Một ước lượng:

\[
C_{\text{downstream}} \approx QFA.
\]

Ví dụ:

\[
Q=300,\quad F=12,\quad A=1.5
\]

thì:

\[
C\approx300\times12\times1.5=5400
\]

downstream branch attempts/s.

Mô hình giả định cấu trúc đồng nhất và không tính RPC nội bộ quorum/redirect; hãy đo thực tế.

### 17.2. Fan-out bounded theo shard

Không phát 100 shard tasks song song nếu DB/client chỉ chịu được 10 active. Có thể dùng một semaphore global + per-shard limits để giảm peak, đồng thời kiểm tra deadline trước khi gửi nhánh mới.

### 17.3. Timeout một nhánh có thể làm cả kết quả thất bại

Nếu cần báo cáo đầy đủ từ 20 shard, một shard chậm kéo dài query. Retry toàn bộ 20 shard sau một timeout của một nhánh có thể lặp lại 19 nhánh đã thành công.

Tùy engine/API, có thể retry riêng nhánh lỗi theo protocol; phải đảm bảo **đúng snapshot/completeness**, không tự ghép dữ liệu nhiều mốc cho báo cáo đòi nhất quán.

### 17.4. Partial results có hợp đồng riêng

Search UI có thể hiển thị partial result có nhãn, nhưng financial aggregate không được im lặng bỏ shard lỗi rồi coi là tổng đúng. Load shedding không cho phép vi phạm tính đầy đủ mà không thông báo.

---

## 18. Hedged requests: giảm tail latency nhưng dễ nhân tải

**Hedging** gửi một request thứ hai tới replica/đường khác khi request đầu chậm bất thường. Nó có thể giảm tail latency cho idempotent read nếu được thiết kế cẩn thận.

Ví dụ:

~~~text
t=0ms: read -> Replica A
t=80ms: A chưa phản hồi
        hedge read -> Replica B
t=100ms: B trả kết quả
        cancel A nếu có thể
~~~

### 18.1. Hedging không phải miễn phí

Mỗi hedge là một request thêm. Nếu cả cluster đều chậm do saturation, hedging làm tải tăng ngay lúc xấu nhất.

### 18.2. Chỉ hedge khi có ngân sách

Một chính sách có thể đặt:

- Chỉ cho read idempotent.
- Chỉ hedge khi latency vượt ngưỡng quan sát.
- Chỉ khi có alternative replica với capacity.
- Giới hạn tỷ lệ hedge toàn hệ.
- Chỉ một hedge/request.
- Hủy request thừa nếu engine hỗ trợ.
- Tôn trọng deadline tổng và consistency requirement.

### 18.3. Hedging write là nguy hiểm nếu không có semantics đặc biệt

Hai write cùng ý định có thể tạo hai side effects nếu backend không dedup. Đừng tự “hedge payment” hoặc “hedge decrement” với ID mới.

### 18.4. Driver speculative execution

Một số database drivers hỗ trợ speculative execution cho query trong điều kiện nhất định. Cần xem cấu hình idempotency và consistency; không bật tùy tiện cho non-idempotent operations.

---

## 19. Retry ghi NoSQL: outcome có thể không xác định

Điểm khó là **write timeout không chứng minh write đã rollback**.

~~~text
Client -> DB write K
DB commits K
DB response lost
Client timeout
~~~

Nếu retry với key hoặc request ID mới, người dùng có thể bị:

- Trừ tồn kho hai lần.
- Tạo hai Order.
- Gửi hai thông báo.
- Thu tiền hai lần.
- Tăng counter hai lần.

### 19.1. Phân loại kết quả

| Outcome | Ý nghĩa | Cách xử lý |
|---|---|---|
| `COMMITTED` | Đã có bằng chứng ghi theo commit contract | Trả kết quả |
| `REJECTED` | Điều kiện nghiệp vụ không thỏa hoặc lỗi terminal | Không retry kiểu transient |
| `UNKNOWN` | Có thể commit rồi nhưng client không biết | Xác minh bằng authoritative read/ledger |
| `OVERLOADED_BEFORE_ADMISSION` | Chắc chắn chưa khởi chạy DB call ở tầng từ chối | Client có thể thử lại theo policy |
| `PENDING` | Intent đã lưu nhưng business action chưa hoàn tất | Status API + xử lý async |

Không gộp `UNKNOWN` với `OVERLOADED_BEFORE_ADMISSION`: hai trạng thái có safety implications khác nhau.

### 19.2. Idempotency key

Một business request có ID ổn định:

~~~text
POST /reservations
Idempotency-Key: reserve-cart-9001
~~~

DB operation hoặc transaction phải ghi nhận cùng ID để retry có thể phát hiện kết quả đã tồn tại. Nếu request đầu đã commit, trả lại kết quả cũ; nếu request ID trùng nhưng payload khác, trả conflict.

### 19.3. CAS/conditional update

Một atomic conditional update bảo vệ business invariant như `available >= quantity`. Nếu dùng `read available` rồi `write` rời, mọi retry/backoff đều không chữa được race.

### 19.4. Outbox cho side effect

Khi DB commit Order và cần publish event, ghi outbox event trong cùng transaction nếu engine hỗ trợ; worker publish idempotently. Nếu publish timeout rồi retry, consumer phải dedup theo event ID.

### 19.5. Deadline không có quyền hủy transaction đã commit

Application có thể ngừng chờ sau 500 ms, nhưng DB commit vẫn có thể hoàn tất. Vì vậy `timeout` trong HTTP handler **không phải lệnh rollback bảo đảm**.

---

## 20. Java: bounded ThreadPoolExecutor cho truy vấn NoSQL

Một ví dụ Java minh họa **số worker cố định và queue có giới hạn**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class BoundedDbExecutor implements AutoCloseable {

    private final ThreadPoolExecutor executor =
        new ThreadPoolExecutor(
            8,                         // core threads
            8,                         // max threads
            0L,
            TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(32),
            new ThreadPoolExecutor.AbortPolicy()
        );

    public static final class OverloadedException
            extends RuntimeException {
        public OverloadedException(String message) {
            super(message);
        }
    }

    public <T> CompletableFuture<T> submit(
            Callable<T> operation) {

        CompletableFuture<T> result =
            new CompletableFuture<>();

        try {
            executor.execute(() -> {
                if (result.isCancelled()) {
                    return;
                }
                try {
                    result.complete(operation.call());
                } catch (Throwable failure) {
                    result.completeExceptionally(failure);
                }
            });
        } catch (RejectedExecutionException rejected) {
            result.completeExceptionally(
                new OverloadedException(
                    "DB executor at capacity"
                )
            );
        }

        return result;
    }

    public int queuedJobs() {
        return executor.getQueue().size();
    }

    public int activeJobs() {
        return executor.getActiveCount();
    }

    @Override
    public void close() {
        executor.shutdown();
    }
}
~~~

### 20.1. Phạm vi bảo đảm

- Tối đa **8 tasks đang chạy** trong executor này.
- Tối đa **32 tasks đợi** trong `ArrayBlockingQueue`.
- Khi executor không thể nhận task mới, `AbortPolicy` gây reject; wrapper chuyển thành `OverloadedException` trong future.
- `CompletableFuture.cancel()` không tự bảo đảm network DB operation đang chạy được hủy/rollback.
- `close()` chỉ yêu cầu shutdown; production có thể cần await termination/force shutdown theo vòng đời service.

### 20.2. Vì sao không dùng `Executors.newFixedThreadPool(8)` mặc định?

`newFixedThreadPool` dùng queue không có capacity hữu hạn theo cấu hình gọi trực tiếp, nên nếu đầu vào vượt tốc độ phục vụ, backlog có thể tăng rất lớn. `ThreadPoolExecutor` với `ArrayBlockingQueue` cho phép đặt chính sách reject rõ.

### 20.3. Điều còn thiếu trong production

Ví dụ chưa xử lý đầy đủ:

- Deadline/queue age.
- Driver operation timeout.
- Cancellation/interrupt semantics.
- Per-tenant/per-shard fairness.
- Authentication, tracing, metrics.
- Overload response HTTP phù hợp.
- Thread naming và graceful shutdown.
- Retry/idempotency.
- DB connection pool sizing.
- Admission trên toàn bộ instances.

Đây là **một thành phần kiểm soát tải**, không phải một HTTP service production hoàn chỉnh.

### 20.4. Không tạo executor mới cho mỗi HTTP request

Nếu mỗi request tự tạo pool 8 threads và queue 32, giới hạn gần như vô nghĩa; tài nguyên nổ theo số request. Executor/bulkhead phải có **vòng đời phù hợp với service/tenant/dependency scope**.

---

## 21. Java: Semaphore để giới hạn in-flight DB operations

Không phải mọi ứng dụng cần xếp hàng. Một semaphore với `tryAcquire()` có thể từ chối nhanh khi không còn permit:

~~~java
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.Semaphore;

public final class DbConcurrencyGate {

    private final Semaphore permits;

    public DbConcurrencyGate(int maxConcurrent) {
        if (maxConcurrent <= 0) {
            throw new IllegalArgumentException(
                "maxConcurrent must be positive"
            );
        }
        this.permits = new Semaphore(
            maxConcurrent, true
        );
    }

    public <T> T execute(Callable<T> dbCall)
            throws Exception {

        Objects.requireNonNull(dbCall);

        if (!permits.tryAcquire()) {
            throw new OverloadedException(
                "No DB concurrency permit"
            );
        }

        try {
            return dbCall.call();
        } finally {
            permits.release();
        }
    }

    public int availablePermits() {
        return permits.availablePermits();
    }

    public static final class OverloadedException
            extends RuntimeException {
        public OverloadedException(String message) {
            super(message);
        }
    }
}
~~~

### 21.1. `finally` rất quan trọng

Nếu query ném exception mà không release permit, limiter bị “rò” capacity và sau một thời gian sẽ từ chối mọi request.

### 21.2. Fair semaphore

`new Semaphore(maxConcurrent, true)` hỗ trợ fairness trong các đường acquire có xếp hàng. Tuy nhiên `tryAcquire()` không tham số có semantics fairness riêng và có thể barging; vì thế không được suy rằng ví dụ này tự đảm bảo công bằng theo tenant/arrival.

Fairness giữa tenants còn cần thiết kế admission/scheduling riêng.

### 21.3. Từ chối nhanh không phải queue

`tryAcquire()` không giữ request lại chờ. Đây là chính sách phù hợp cho một số request latency-sensitive. Nếu muốn đợi một khoảng ngắn, cần `tryAcquire(timeout, unit)` và phải trừ thời gian chờ vào deadline tổng.

### 21.4. Một semaphore local không là global cap

Nếu có 20 instances, mỗi instance `maxConcurrent=40`, tổng tối đa lý thuyết tới 800 in-flight ở tầng này. Nên chia ngân sách theo scale, quan sát tổng và cân nhắc limiter toàn cụm khi có nhu cầu.

---

## 22. Java: deadline dùng monotonic clock

Một helper để không gửi thêm công việc đã quá hạn:

~~~java
import java.time.Duration;

public final class Deadline {

    private final long deadlineNanos;

    public Deadline(Duration budget) {
        if (budget == null || budget.isNegative()
                || budget.isZero()) {
            throw new IllegalArgumentException(
                "budget must be positive"
            );
        }
        this.deadlineNanos =
            System.nanoTime() + budget.toNanos();
    }

    public long remainingNanos() {
        return Math.max(
            0L, deadlineNanos - System.nanoTime()
        );
    }

    public boolean expired() {
        return remainingNanos() == 0L;
    }
}
~~~

### 22.1. Giới hạn ví dụ

Giả định budget hữu hạn hợp lý để phép tính `nanoTime + duration` không vượt miền biểu diễn đáng quan tâm. Đây là helper local elapsed-time, **không phải absolute deadline đồng bộ giữa các máy**.

Khi truyền deadline qua network, cần protocol rõ về timestamp/remaining budget, độ lệch clock và phần thời gian mạng. Không copy `System.nanoTime()` từ máy này rồi so trực tiếp trên máy khác.

### 22.2. Kiểm tra trước khi lấy permit

~~~text
if deadline expired:
    reject without starting DB operation

else:
    attempt bounded permit acquisition

if insufficient time for useful work:
    do not start a retry
~~~

### 22.3. Không cộng nhiều timeout độc lập

Nếu còn 100 ms trong end-to-end deadline, không cấp mới 300 ms cho connection acquisition và 500 ms cho DB read. Mỗi tầng phải nhận phần **remaining budget** phù hợp.

---

## 23. Rate limit + semaphore + queue: phối hợp theo thứ tự

Một pipeline đơn giản:

~~~mermaid
flowchart TD
    R["Incoming logical request"] --> A["Auth + validate"]
    A --> RL{"Rate/quota allowed?"}
    RL -- "No" --> X["429"]
    RL -- "Yes" --> D{"Deadline valid?"}
    D -- "No" --> Y["Deadline failure"]
    D -- "Yes" --> S{"Concurrency permit?"}
    S -- "Yes" --> DB["DB operation with timeout"]
    S -- "No" --> Q{"Bounded queue has slot and wait budget?"}
    Q -- "No" --> Z["503/429 overload"]
    Q -- "Yes" --> W["Wait bounded time"]
    W --> D
    DB --> F["Release permit"]
~~~

Với queue, cần cẩn thận tránh job được xếp lại nhiều lần khi permit chưa có, tạo busy loop. Sơ đồ chỉ mô tả **quyết định**, implementation dùng scheduler/condition phù hợp.

### 23.1. Vì sao rate limit trước DB?

Không nên để request bị từ chối vì quota vẫn chiếm DB connection hoặc đắt chi phí validation/large payload parsing không cần thiết. Tuy nhiên authentication tối thiểu vẫn cần trước khi gán quota theo tenant/user.

### 23.2. Vì sao concurrency gần DB?

Để số in-flight DB operations không vượt capacity của cluster/partition, nhất là khi queue ở gateway không nhìn thấy shard-specific latency.

### 23.3. Bounded queue rất nhỏ có thể đủ

Nếu DB có capacity cho 100 requests/s và burst đến trong 50 ms, queue 10-20 có thể hấp thụ một phần burst. Queue 10.000 không tăng throughput, chỉ giữ request lâu hơn.

### 23.4. Queue phải được dọn khi client hủy

Nếu client disconnect, pending task chưa chạy nên được loại khỏi queue nếu có thể. Nhưng với write đang chạy, cancellation không chứng minh rollback; cần phân biệt **not started** và **in-flight unknown**.

---

## 24. NoSQL-specific: một hot partition gây overload cục bộ

Giả sử DynamoDB table có nhiều partition keys, nhưng 40% traffic đọc/ghi một key:

~~~text
tenant#VIP
~~~

Toàn cluster có thể còn nhiều capacity nhưng physical partition hoặc access path chứa hot key bị nghẽn.

### 24.1. Global limiter có thể quá thô

Nếu mọi request bị giảm tốc do một hot partition, những tenant khác có thể bị phạt dù shard của họ khỏe.

### 24.2. Key-aware concurrency

Một cách tổ chức:

~~~text
Global DB permits: 300
Per-tenant permits: 20
Per-hot-resource permits: 5
Background analytics permits: 10
~~~

Những mức này chỉ là ví dụ. Để dùng thực tế cần biết partitioning và các key có thể colocation, cũng như xử lý multi-key requests.

### 24.3. Hot key không được giải bằng retry

Nếu cùng một key đang chịu 10.000 conditional writes/s, retry ngay các conditional failures có thể nhân tải nhưng không tăng số yêu cầu có thể commit.

Cần xem:

- Thay data model: bucket/salt, coalesce.
- Queue/serialize theo key khi phù hợp.
- Batching hoặc aggregation.
- Cache reads nếu freshness cho phép.
- Escrow/quota allocation cho invariant cho phép.
- Throttle tenant gây hot spot.

### 24.4. Conditional failure là kết quả nghiệp vụ

Khi `available=0`, một atomic conditional update từ chối reservation. Không nên retry theo exponential backoff như lỗi hạ tầng nếu điều kiện không thể thay đổi theo nghiệp vụ.

### 24.5. Quorum làm tăng chi phí một logical operation

Một read CL=`QUORUM` trên RF=3 có thể liên hệ nhiều replicas. Vì vậy `50 concurrent CQL requests` không đồng nghĩa đúng 50 network RPCs. Cần đo coordinator load, replica-side requests và read repair/speculative execution.

---

## 25. Cassandra: consistency level, timeout, idempotence và speculative execution

Cassandra regular writes thường dùng coordinator gửi mutations tới replicas theo replication strategy và consistency level.

### 25.1. Timeout chưa chắc write chưa xảy ra

Write CL=`QUORUM` timeout có thể là vì chỉ một replica phản hồi trước deadline, trong khi mutation đã áp ở một số nơi. Retry với statement không idempotent có thể gây business side effect khác.

### 25.2. Không đánh dấu mọi query idempotent

Một statement dạng set một giá trị có thể phù hợp retry hơn một câu lệnh cập nhật counter hoặc thao tác bên ngoài DB. Ngay cả lệnh set cùng payload, timestamp và conflict semantics cũng cần được xét.

Một driver có thể sử dụng thông tin idempotence để quyết định retry/speculative execution. Chỉ đánh dấu đúng khi semantics thực sự cho phép.

### 25.3. LOCAL_QUORUM và partition

Một query logic một partition với RF=3 có thể cần nhiều replica. Nếu một DC gặp sự cố, phần lớn requests vào những partitions thuộc DC ấy có thể tăng latency và retries.

Giới hạn đồng thời nên cân nhắc **DC, token range, endpoint, query class**, không chỉ QPS của cả ứng dụng.

### 25.4. Speculative execution không tự an toàn

Driver có thể gửi một read khác khi read trước quá chậm. Nó có thể giảm tail nhưng tăng tải replicas. Nên kiểm soát policy, idempotence và budget, không bật bừa dưới cluster saturation.

### 25.5. Repair/compaction tranh tài nguyên

Trong repair/compaction, throughput hiệu dụng của cluster giảm. Nếu controller chỉ tăng permits theo lượng request tới, nó có thể tạo vòng tắc nghẽn. Theo dõi p99, pending compactions, coordinator errors và replica timeouts.

### 25.6. LWT và contention

Lightweight Transactions/CAS có chi phí nhiều pha và contention semantics khác regular write. Đặt một concurrency cap riêng cho những hot LWT paths thường hữu ích hơn cho fairness và tail latency.

---

## 26. MongoDB: pool wait queue, retryable writes và transaction

MongoDB Java driver có connection pooling và các timeout; tên cấu hình cần đối chiếu theo phiên bản driver/server đang dùng.

### 26.1. Connection pool queue cũng là queue

Nếu API có 500 concurrent handlers nhưng pool chỉ có 50 connections, nhiều operation có thể chờ lấy connection. Nếu service còn có một queue executor lớn, có thể tạo **hai lớp queue nối tiếp**:

~~~text
HTTP queue -> executor queue -> connection-pool wait
  -> database execution -> response
~~~

Từng lớp thêm latency; nếu không có deadline tổng, người dùng có thể timeout ở nhiều điểm khác nhau.

### 26.2. Retryable writes theo driver contract

MongoDB hỗ trợ retryable writes trong những điều kiện thích hợp. Nhưng không nên suy rằng **mọi transaction body và mọi side effect** đều an toàn khi được driver/application chạy lại.

Transaction callback có thể được thực thi lại trong cơ chế retry; không gửi email/payment trực tiếp trong callback nếu không có protocol idempotent phù hợp.

### 26.3. Majority và write concern timeout

Một write đã được primary áp dụng nhưng timeout chờ write concern `majority` có thể có outcome mà client chưa rõ. Retry với ID ổn định, dùng semantics của driver và transaction ledger, không tự tạo Order ID mới.

### 26.4. Bulkhead theo query class

Một aggregate nhiều shard có thể chạy lâu và tiêu tốn memory; không để nó chiếm mọi permits của point lookup hoặc transactional writes.

### 26.5. Failover gây retry herd

Khi primary đổi, hàng nghìn clients cùng nhận lỗi và retry. Backoff/jitter, retry budget, queue bound và driver topology refresh là biện pháp giữ leader mới khỏi bị nhấn chìm.

### 26.6. Bounded executor không sửa server-side lock contention

Nếu một transaction giữ lock lâu hoặc hot document chịu nhiều writes, tăng worker count thường làm contention nặng hơn. Cần tối ưu transaction scope, indexes, data model và concurrency cap.

---

## 27. DynamoDB: throttling, capacity và BatchWrite retry

DynamoDB có provisioned/on-demand capacity và những giới hạn theo partition/index/service. Khi vượt capacity, API có thể trả throttling-related exceptions hoặc một batch API trả về unprocessed items.

### 27.1. Throttling là tín hiệu admission của backend

Đừng coi throttling là “network lỗi ngẫu nhiên, retry ngay càng nhanh càng tốt”. Nó có thể biểu thị tài nguyên/giới hạn nhất định đã chạm ngưỡng.

### 27.2. SDK retries cần được tính vào tổng budget

AWS SDK có retry strategy và các cấu hình theo phiên bản; ứng dụng cần biết SDK đã retry bao nhiêu, rồi mới quyết định application retry, tránh double retries.

### 27.3. BatchWrite và UnprocessedItems

Với những batch APIs, một số item có thể được xử lý, một số chưa. Nếu retry toàn bộ batch mà không phân biệt item đã hoàn tất, tải và semantics có thể sai.

Cần retry **những UnprocessedItems theo contract** với backoff/jitter, đồng thời hiểu tính idempotent của kiểu operation. BatchWrite không phải general transaction atomic cho mọi item.

### 27.4. Hot partition

Một bảng có tổng read/write capacity lớn vẫn có thể bị hot key/partition giới hạn. Query/scan trên GSI cũng có thể tác động capacity/index workload.

### 27.5. 429/503 ở API có thể bảo vệ DynamoDB

Nếu API biết tenant vừa vượt rate budget hoặc DB đang throttling, từ chối sớm một phần request giúp giảm secondary attempts. Đừng để mỗi client tự retry 10 lần vào cùng hot partition.

### 27.6. Strong read và transaction tốn ngân sách khác

Một strong read, eventual read, transaction và GSI query có chi phí/semantics khác nhau. Nếu áp một limiter “requests/s” duy nhất, workload phức tạp có thể chiếm capacity không công bằng.

---

## 28. Redis: single-threaded command execution không nghĩa queue vô hạn

Redis thường xử lý các lệnh của một instance theo mô hình event-driven; một số command/Lua script chạy lâu có thể chặn tiến độ xử lý những commands khác.

### 28.1. Một Lua script đắt là điểm nghẽn

Nếu script quét nhiều key/logic nặng và giữ server thực thi lâu, client calls tiếp tục đến có thể chờ, timeout rồi retry. Concurrency tăng ở API không khiến một Redis instance thực thi script chặn đó nhanh hơn.

### 28.2. Giới hạn clients, buffers và timeouts

Các kết nối và output buffers dùng memory. Một client library có thể có queue các commands đang đợi; cần kiểm tra cấu hình driver và Redis server thay vì mặc định nó tự bounded an toàn.

### 28.3. Redis Cluster hot slot

Một slot/key cực nóng vẫn gây saturation dù cluster có nhiều node. Key hashing phân phối giữa keys, không tự chia một hot key thành nhiều tài nguyên thực thi.

### 28.4. Retry sau failover

Một write timeout trước/giữa failover có thể đã được primary áp dụng, nhưng replica chưa thấy. Retry các increment không idempotent có thể gây đếm trùng; durability cũng tùy replication/persistence. Dùng request ID/transaction semantics phù hợp hoặc chấp nhận mất/đếm trùng theo business contract.

### 28.5. Pub/Sub không phải durable work queue

Nếu cần đảm bảo job async được giữ qua crash, không dùng một queue in-memory tự dựng hoặc pub/sub không có durability phù hợp rồi trả “đã xử lý”. Redis Streams hoặc một message broker durable có thể phù hợp hơn trong một số thiết kế, với consumer acknowledgment và retry/dedup riêng.

---

## 29. Backpressure trong message queue: Kafka/RabbitMQ và ingestion pipeline

Một NoSQL thường được cập nhật qua:

~~~text
Producer -> Broker -> Consumer -> NoSQL
~~~

Nếu NoSQL chậm, consumer phải điều tiết **số messages đang xử lý** và **số writes in-flight**, không đọc vô hạn từ broker.

### 29.1. Kafka consumer

Một consumer có thể kiểm soát:

- Số records lấy mỗi poll.
- Số records xử lý đồng thời.
- Pause/resume partitions khi downstream saturated.
- Commit offsets sau khi hiệu ứng cần thiết đã được ghi/đối soát theo semantics.
- Deadline, retry topic hoặc dead-letter policy.

Không dùng `pause()` như bảo đảm durable processing: messages vẫn còn trong broker theo retention, offset commit và consumer group protocol.

### 29.2. RabbitMQ prefetch

Consumer prefetch limit giới hạn số messages chưa được acknowledged được đẩy tới consumer/channel theo semantics cấu hình. Đây là một lớp backpressure hữu ích.

Nhưng `prefetch=50` không nhất thiết đồng nghĩa chỉ 50 DB calls nếu consumer tự fan-out mỗi message thành nhiều operations.

### 29.3. Ack trước DB commit nguy hiểm

~~~text
Consumer receives message M
Consumer ACKs broker
DB write fails
~~~

Nếu broker đã xóa trách nhiệm redelivery, message có thể bị mất về mặt nghiệp vụ.

Ngược lại, DB commit rồi consumer crash trước broker ACK có thể khiến M được phát lại. Vì vậy consumer cần **idempotent apply** và chiến lược ack/transaction phù hợp.

### 29.4. Retry poison message

Một message lỗi validation không thể xử lý nhưng bị retry vô hạn sẽ chiếm queue/worker. Cần phân loại permanent vs transient, dead-letter có audit và không để một partition bị chặn mãi.

### 29.5. Bounded buffer giữa broker và DB

~~~text
Broker backlog: durable, measured
Consumer in-flight: bounded
Local retry queue: bounded
DB in-flight: bounded
~~~

Phần backlog dài hạn nên nằm ở hệ có retention/durability được thiết kế, **không phải ở heap của API worker**.

---

## 30. Reactive Streams và virtual threads không xóa bỏ nhu cầu giới hạn

### 30.1. Backpressure theo demand

Trong hệ reactive, một consumer có thể chỉ yêu cầu thêm N items khi còn khả năng xử lý. Điều này giúp tránh producer đẩy vô hạn vào buffer.

Tuy nhiên, backpressure chỉ có tác dụng khi **mọi tầng có liên quan tôn trọng demand**, và khi một nguồn push không thể dừng, cần buffer có giới hạn hoặc drop/error policy.

### 30.2. Parallelism là một ngân sách

`flatMap` với concurrency rất lớn có thể khiến một stream nhận 10.000 events rồi phát 10.000 DB calls. Reactive code không mặc nhiên có concurrency limit phù hợp chỉ vì nó không block thread.

### 30.3. Virtual threads

Java virtual threads giúp tạo nhiều tác vụ blocking nhẹ hơn về thread overhead trong nhiều trường hợp. Nhưng chúng **không làm DB có thêm capacity**:

~~~text
100.000 virtual threads
  -> 100.000 in-flight DB calls?
~~~

Nếu không giới hạn, connection pool, memory, remote shard và network vẫn bị bão hòa. Dùng semaphore/bulkhead/driver limits ngay cả với virtual threads.

### 30.4. Bounded operator queues

Một số thư viện có operator buffer/prefetch mặc định; cần kiểm tra vì số item được prefetch trên mỗi subscription/partition có thể nhân lên khi fan-out.

---

## 31. Thiết kế capacity theo request class

Một ứng dụng cần phục vụ:

| Workload | Mức quan trọng | Chi phí tương đối | Chính sách |
|---|---|---|---|
| Point read hồ sơ | Cao | Nhỏ | Concurrency cap, cache hợp lệ |
| Inventory conditional update | Rất cao | Vừa, có contention | Strict admission, idempotency, priority |
| Search nhiều shard | Trung bình | Lớn | Fan-out budget, separate bulkhead |
| Analytics aggregate | Thấp/async | Rất lớn | Queue durable, schedule off-peak |
| CDC event apply | Quan trọng nền | Theo batch | Bounded consumer in-flight |
| Repair/backfill | Vận hành | I/O nặng | Throttle theo SLO/compaction |
| Admin export | Thấp, dài | Rất lớn | Async job, paging, capacity budget |

### 31.1. Không để batch chiếm hết interactive capacity

Nếu một nightly job chạy 5.000 writes đồng thời, checkout có thể timeout dù tổng throughput trung bình tốt. Cần bulkhead và throttling của background writes.

### 31.2. Priority không phải bỏ đói hoàn toàn

Chỉ phục vụ high-priority mãi có thể khiến backlog reconciliation/outbox không bao giờ xong, dẫn đến sai nghiệp vụ. Cần phân bổ **mức tối thiểu hoặc lịch phục vụ** cho tác vụ nền thiết yếu.

### 31.3. Miền lỗi và capacity

Khi một AZ mất, traffic dồn sang AZ khác. Nếu giới hạn được đặt chỉ theo capacity bình thường của tất cả AZ, surviving nodes có thể overload.

Cần capacity planning cho failure modes quan trọng và chính sách giảm mức dịch vụ không thiết yếu.

---

## 32. Một ví dụ tính capacity end-to-end

Giả sử:

~~~text
Logical checkout demand:      800 req/s
Mỗi checkout có 1 DB transaction
DB service time trung bình:    30 ms
DB sustainable throughput:   1.000 tx/s
API total deadline:          300 ms
~~~

### 32.1. Concurrency trung bình cơ sở

Theo Little, khi ổn định và chưa queue:

\[
L=800\times0.03=24.
\]

Khoảng 24 DB transactions in-flight trung bình.

### 32.2. Khi service time tăng 5 lần

Do failover/compaction, DB service time thành 150 ms:

\[
L=800\times0.15=120.
\]

Nếu DB còn chỉ xử lý bền vững 500 tx/s trong sự cố, \(\lambda=800>\mu=500\). Queue sẽ tích tụ, dù dự kiến in-flight theo tải đến có vẻ chỉ 120. Định luật Little **không thể dùng công thức trạng thái ổn định** để hợp thức hóa một hệ đang backlog tăng vô hạn.

### 32.3. Retry x2

Nếu mỗi checkout trung bình tạo hai transaction attempts:

\[
\lambda_{\text{physical}}=800\times2=1600\text{ attempts/s}.
\]

Lúc DB chỉ có capacity 500/s, retry làm overload nghiêm trọng hơn.

### 32.4. Bounded admission

Giả sử trong degradation API chỉ cho DB tối đa 40 active attempts và chờ tối đa 20 request trong 50 ms. Khi hết budget, request mới được từ chối sớm/đưa trạng thái phù hợp.

Hệ không tự tăng throughput từ 500 lên 800; nhưng có thể giữ latency ở những request được nhận và giảm vòng retry vô ích.

### 32.5. Cần phân biệt throughput xử lý với concurrency

Số permits 40 không tự tạo một throughput chính xác, vì duration variance, transaction cost và network. Benchmark phải đo p99, errors, throughput và queue occupancy cùng nhau.

### 32.6. Không đặt queue size bằng “ước lượng tất cả request trong 300 ms”

Nếu request có 300 ms end-to-end, không có nghĩa được phép đợi toàn bộ 300 ms ở queue. Cần chừa budget cho DB execution và response. Queue budget có thể chỉ 20–50 ms tùy workload.

---

## 33. Java: retry có budget, jitter và deadline

Pseudocode Java cho một **read idempotent**:

~~~java
import java.time.Duration;
import java.util.concurrent.Callable;
import java.util.concurrent.ThreadLocalRandom;

public final class BoundedRetry {

    public static <T> T callRead(
            Callable<T> operation,
            Duration budget,
            int maxAttempts) throws Exception {

        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                "maxAttempts must be positive"
            );
        }

        long deadline =
            System.nanoTime() + budget.toNanos();

        Exception last = null;

        for (int attempt = 1;
                attempt <= maxAttempts;
                attempt++) {

            if (deadline - System.nanoTime() <= 0L) {
                break;
            }

            try {
                // Driver call itself must have a timeout
                // bounded by remaining deadline.
                return operation.call();
            } catch (Exception failure) {
                last = failure;

                if (!isRetryableTransient(failure)
                        || attempt == maxAttempts) {
                    throw failure;
                }
            }

            long capMillis = Math.min(
                500L, 50L << Math.min(attempt - 1, 3)
            );

            long remainingMs = Math.max(
                0L,
                (deadline - System.nanoTime()) / 1_000_000L
            );

            long waitMs = ThreadLocalRandom.current()
                .nextLong(capMillis + 1L);

            waitMs = Math.min(waitMs, remainingMs);

            if (waitMs > 0L) {
                Thread.sleep(waitMs);
            }
        }

        throw new IllegalStateException(
            "Request deadline exceeded", last
        );
    }

    private static boolean isRetryableTransient(
            Exception failure) {
        // Placeholder: classify actual driver exception
        // types, server hints and operation semantics.
        return false;
    }
}
~~~

### 33.1. Đây là ví dụ lý luận, không phải retry library production

- `isRetryableTransient` cố tình trả false: người học phải tích hợp phân loại lỗi của đúng driver.
- Chưa có retry budget toàn service.
- Chưa truyền deadline vào connection pool/DB command cụ thể.
- Chưa có tracing/metrics/circuit breaker.
- Chưa phân biệt exception do cancellation/interrupt.
- Không dùng trực tiếp cho write không idempotent hoặc payment.
- Không nên sleep trên event loop; với reactive/async dùng scheduler tương ứng.

### 33.2. Thực thi thiếu thời gian vẫn nguy hiểm

Nếu còn 5 ms mà bắt đầu DB call có thể kéo 2 s, helper không đảm bảo kết thúc trong deadline. Deadline phải được áp vào **tầng I/O thực** hoặc thread/cancellation boundary phù hợp, và unknown write outcome vẫn phải được xử lý.

### 33.3. Retry budget toàn cục

Mỗi instance có thể duy trì token pool cho retry attempts. Khi budget cạn, không retry dù `maxAttempts` của request còn chỗ. Đó là cơ chế chống hệ tự khuếch đại khi lỗi lan rộng.

---

## 34. Điều kiện chọn kích thước queue

Queue capacity không có một số mặc định đúng cho mọi service. Có thể bắt đầu từ:

- Throughput bền vững thực tế tại boundary.
- Maximum queue wait cho workload.
- Variance service time.
- Burst distribution.
- Memory/job.
- SLO p99 và deadline.
- Tỷ lệ request có thể bị drop/reject.
- Khả năng retry của clients.

### 34.1. Công thức trực giác

Nếu service xử lý \(\mu\) jobs/s và chỉ cho đợi thêm \(T_q\) giây, một ngưỡng tham khảo:

\[
Q_{\text{budget}}\lesssim \mu T_q.
\]

Ví dụ \(\mu=400/s,T_q=0.05s\):

\[
Q\lesssim20.
\]

Đây là **heuristic**, không phải bảo đảm worst-case queue wait. Với job kích thước khác nhau, priority/fairness và tail latency, đo thực tế quan trọng hơn.

### 34.2. Độ dài queue là số jobs, nhưng chi phí không đồng nhất

Một queue chứa 10 point lookups và một queue chứa 10 global scans có memory/CPU/IO rất khác nhau. Có thể dùng **weighted admission** theo estimated cost hoặc tách queue classes.

### 34.3. Queue đầy không nên tự động scale thread vô hạn

Mở thêm 500 threads khi DB đã saturated thường tăng context switching, connection acquisition wait và remote overload. Scale worker phải đi kèm downstream capacity hoặc giới hạn khác.

### 34.4. Đo queue wait histogram

Queue depth thấp không chứng minh không có tail latency: một request đang chờ phía connection pool hoặc router có thể bị chặn lâu. Cần đo **wait time của từng tầng**.

### 34.5. Queue mất hiệu lực khi caller đã bỏ cuộc

Nếu 30% queued jobs đã hết deadline, việc xử lý chúng làm throughput “có việc” nhưng không tạo giá trị người dùng. Cần loại job hết hạn trước khi thực thi và theo dõi wasted-work.

---

## 35. Kiểm thử overload, retry và backpressure

Không chỉ chạy happy-path load test. Cần kiểm tra cả lỗi một phần.

### 35.1. Baseline

Đo khi DB khỏe:

- Offered load và success throughput.
- Service time mean/p95/p99.
- Queue wait, active permits.
- Error, timeout, retries.
- DB CPU, disk, network và partition hot spots.
- Memory/GC, connection pool wait.

### 35.2. Step load

Tăng offered traffic từng bậc:

~~~text
100/s -> 200/s -> 400/s -> 600/s -> 800/s
~~~

Quan sát điểm queue bắt đầu tăng dài và p99 đột biến. Mục tiêu là tìm **knee of the curve**, không chỉ throughput tối đa trước crash.

### 35.3. Slow dependency

Trong staging, thêm latency có kiểm soát cho một replica/shard. Kiểm tra limiter có giữ in-flight, queue wait và deadline trong budget không.

### 35.4. Failover

Mô phỏng primary failover hoặc node không sẵn sàng trong môi trường được phép; đo lượng retry cùng lúc, thời gian driver refresh topology, overload rejection và hồi phục.

### 35.5. Hot partition

Cho một tenant/key nhận phần lớn traffic, kiểm tra per-shard limiter, fairness và liệu tenants khác vẫn đáp ứng được không.

### 35.6. Retry amplification

Ghi logical request ID cùng attempt IDs qua gateway/service/driver. Kiểm tra tổng attempts/request ở các lỗi `timeout`, `429`, `503`, conflict, validation.

### 35.7. Cancel/deadline

Cho client cancel ngay khi request vào queue. Xác minh task chưa chạy bị loại; request đang chạy ghi thì được đánh dấu outcome unknown khi cần.

### 35.8. Durable queue recovery

Crash consumer sau DB commit trước broker ACK. Kiểm tra event được redeliver nhưng idempotent handler không lặp side effect.

### 35.9. Safety

Chỉ tiến hành fault injection, network partition hoặc tải phá hủy trong môi trường được phê duyệt. Không tự gây quá tải cluster production khi chưa có runbook và giới hạn.

---

## 36. Dashboard và alert theo nhiều chiều

| Nhóm | Metric | Câu hỏi |
|---|---|---|
| Admission | Offered vs accepted vs rejected | Tải thật là bao nhiêu? |
| Concurrency | Active in-flight / permits | Đã chạm giới hạn chưa? |
| Queue | Depth, age, wait p95/p99 | Request đang chờ lâu bao nhiêu? |
| Retry | Attempts/logical request | Có amplification không? |
| Deadline | Expired before execution | Có wasted work không? |
| DB | Per-shard p99, throttling, failover | Đường nào nghẽn? |
| Pool | Active/idle connections, acquire wait | Pool có trở thành queue? |
| Fairness | Rejections by tenant/endpoint | Một tenant chiếm hết chỗ? |
| Fan-out | Shards per query, RPCs/request | Một request gây bao nhiêu nhánh? |
| Hedging | Hedged reads, hedge win rate | Tốn thêm tải có đáng không? |
| Memory | Heap, GC pause, queued bytes | Queue gây memory pressure? |
| Errors | 429/503/timeout/conflict | Phân loại đúng chưa? |
| Success | Goodput, SLO successful responses | Người dùng nhận được giá trị? |
| Side effects | Duplicate writes, unknown outcomes | Retry ghi có an toàn? |
| Background | Repair/compaction/index backlog | Capacity DB đang bị chia? |

### 36.1. Goodput khác throughput

**Throughput** có thể tính mọi attempt hoặc operation đã chạy. **Goodput** nên tập trung vào công việc hữu ích và kết quả hợp lệ cho user/business.

Một service làm 5.000 DB operations/s nhưng chỉ hoàn thành 1.000 checkout/s vì 4.000 operations là retry vô ích không nên được xem là tốt hơn service hoàn thành 1.000 checkout với 1.200 DB operations.

### 36.2. Phân loại 429/503 đúng

Nhiều overload rejections là tín hiệu limiter đang bảo vệ hệ, không tự động là bug. Tuy nhiên nếu tỉ lệ reject cao thường xuyên, capacity plan hoặc giới hạn cần thay đổi.

### 36.3. Báo động trên queue age, không chỉ depth

Queue depth 20 có thể an toàn khi throughput 1.000/s, nhưng nghiêm trọng khi throughput chỉ 5/s. Queue wait/age phản ánh trực tiếp trải nghiệm người dùng hơn.

### 36.4. Sau recovery vẫn phải giảm retry herd

Khi dependency khỏe lại, nhiều clients có thể đã xếp lịch retry cùng mốc. Giữ jitter, rollout gradual và giới hạn half-open để tránh phá recovery.

---

## 37. Runbook khi database bắt đầu quá tải

### Bước 1 — Xác định điểm nghẽn thực

Kiểm tra:

- DB CPU/disk/IOPS/network/compaction.
- Hot shard/key, leader election, replica lag.
- Connection pool wait.
- Executor queue.
- Gateway offered load.
- Background jobs.
- Retry amplification.

Không tăng thread ngay trước khi biết nút thắt nằm ở đâu.

### Bước 2 — Bảo vệ endpoint quan trọng

Tạm giảm hoặc hoãn analytics, export, backfill, search phức tạp. Giữ permits cho checkout/inventory/status theo business priority.

### Bước 3 — Giảm secondary traffic

- Giới hạn retries ở tầng phù hợp.
- Bật backoff+jitter.
- Dừng hedging không cần thiết.
- Giảm fan-out của query rộng.
- Dedupe requests cùng key nếu phù hợp.

### Bước 4 — Admission rõ ràng

Đặt global/per-tenant/per-shard limits theo capacity hiện tại. Reject sớm phần không thể phục vụ, không thêm queue vô hạn.

### Bước 5 — Giảm queue không hữu ích

Hủy tasks chưa chạy và hết deadline nếu có thể. Không tự hủy write đang có commit outcome unknown rồi báo chắc chắn thất bại.

### Bước 6 — Xử lý failure và correctness

Nếu primary đang failover:

- Cho driver cập nhật topology.
- Không gửi write vào stale leader.
- Retry idempotently theo contract.
- Không coi timeout là chưa commit.
- Theo dõi request pending/reconciliation.

### Bước 7 — Cân nhắc capacity/split hot key

Scale node/partition khi có cơ sở, nhưng hiểu bootstrap/rebalance/cold cache cũng dùng tài nguyên. Không cho rằng autoscaling lập tức giúp.

### Bước 8 — Hồi phục có kiểm soát

Tăng concurrency chậm, theo dõi p99, queue age, DB errors và retry attempts. Không đóng incident chỉ vì error rate tạm giảm khi offered load đã biến mất.

### Bước 9 — Ghi postmortem

Gồm offered load, effective capacity, các lớp retry, peak amplification, queue sizes, rejected count, lost/duplicate effects, recovery time và hành động ngăn tái diễn.

---

## 38. Những ngộ nhận thường gặp

| Ngộ nhận | Hậu quả | Cách hiểu đúng |
|---|---|---|
| “Thêm threads sẽ tăng throughput.” | More contention | Chỉ tăng nếu downstream còn capacity |
| “Queue càng dài càng ít lỗi.” | Timeout, OOM | Bounded queue + fast rejection |
| “Rate limit đã đủ.” | Long operations chiếm in-flight | Cần concurrency cap |
| “Concurrency cap thay rate limit.” | Bursts gây reject quá nhiều | Kết hợp theo workload |
| “Pool 100 connections nghĩa toàn hệ 100 requests.” | Mỗi instance có pool riêng; multiplexing | Đo actual in-flight |
| “Little's Law đảm bảo p99.” | Dùng sai trung bình | Đây là quan hệ trạng thái ổn định |
| “Retry giúp nhanh hồi phục.” | Retry storm | Có budget, backoff, jitter |
| “Mỗi tầng retry ba lần cũng ổn.” | Tới 27 attempts ở ba tầng | Phối hợp retry toàn chuỗi |
| “Timeout chứng minh write thất bại.” | Duplicate Order/payment | UNKNOWN outcome, idempotency |
| “Cancel future rollback DB write.” | Sai business outcome | Cancellation không tự rollback |
| “429 luôn là server bug.” | Đánh giá sai admission | Có thể là chính sách overload đúng |
| “503 thì client nên retry ngay.” | Thêm tải | Retry có deadline, jitter, budget |
| “CallerRunsPolicy luôn tốt.” | Block HTTP/event loop | Chọn execution model phù hợp |
| “Virtual threads làm DB vô hạn capacity.” | In-flight explosion | Vẫn dùng bulkhead/semaphore |
| “Circuit breaker thay semaphore.” | Quá nhiều work khi dependency chậm | Hai cơ chế khác nhau |
| “Tăng timeout chữa DB slow.” | Tích tụ request | Tìm bottleneck, giới hạn tải |
| “Một queue cho mọi tenant công bằng.” | Noisy neighbor | Per-tenant fairness |
| “Fan-out 20 shard chỉ tốn một request.” | 20+ branch operations | Budget theo actual cost |
| “Hedging giảm tail miễn phí.” | Load tăng | Chỉ hedge có điều kiện |
| “Background job không ảnh hưởng OLTP.” | Compaction/I/O tranh tải | Separate bulkhead/throttle |
| “GSI/search không thấy record -> chưa commit.” | Retry tạo trùng | Verify authoritative source |
| “Quota per instance là quota toàn cluster.” | Scale out nhân capacity limit | Tính tổng instances |
| “Kafka pause là ack transaction.” | Nhầm broker state | Offset/ack và DB commit riêng |
| “Queue in-memory durable.” | Mất jobs sau crash | Dùng durable queue cho workflow |
| “Scale out sẽ cứu mọi hot key.” | Hot partition không chia | Đổi data model/limit |
| “P99 thấp nghĩa không có overload.” | Chỉ đo accepted traffic | Xem offered/rejection/goodput |
| “Reject sớm lúc overload luôn tệ.” | Lãng phí tài nguyên nếu nhận hết | Load shedding có thể bảo vệ SLO |

---

## 39. Bài tập 1: tính Little's Law và giới hạn đồng thời

Một service có:

~~~text
Accepted throughput: 600 requests/s
DB operation mean: 50 ms
Queue wait mean:   20 ms
~~~

Trả lời:

1. Số DB operations in-flight trung bình là bao nhiêu?
2. Số request trung bình trong queue + DB là bao nhiêu?
3. Nếu DB mean tăng lên 250 ms mà accepted throughput vẫn giữ được 600/s, concurrency trung bình ở DB là bao nhiêu?
4. Nếu DB sustainable throughput giảm còn 300/s, offered load vẫn 600/s, hệ ổn định được không?
5. Concurrency limit và queue capacity giải quyết vấn đề nào, không giải quyết vấn đề nào?
6. Vì sao không dùng mean để hứa p99?

### Gợi ý

\[
L_{\text{DB}}=600\times0.05=30.
\]

\[
L_{\text{total}}=600\times(0.05+0.02)=42.
\]

Khi mean DB=250 ms:

\[
L_{\text{DB}}=600\times0.25=150.
\]

Điều kiện giữ 600 successful operations/s phải được kiểm chứng; nếu năng lực bền vững chỉ 300/s, backlog không thể ổn định khi offered 600/s.

---

## 40. Bài tập 2: khuếch đại retry nhiều tầng

Giả sử Gateway, Service A và Service B đều retry tối đa 3 attempts trước khi kết luận lỗi. Mỗi logical request tới Gateway và tầng sâu nhất là một DB operation.

1. Số DB attempts tối đa theo cấu hình nested retry?
2. Nếu 1.000 logical requests/s đều gặp lỗi kéo dài và retry hết, số deepest attempts/s có thể đạt bao nhiêu theo mô hình đơn giản?
3. Nếu chỉ cho một tầng retry tối đa 2 attempts, cận trên còn bao nhiêu?
4. Với \(p=0.3,m=3\), tính \(E[A]\) theo giả định độc lập.
5. Vì sao lỗi correlated overload làm mô hình độc lập không đáng tin?
6. Cách nào giới hạn retry theo aggregate budget?

### Gợi ý

Cận trên:

\[
3^3=27.
\]

Nếu mọi logical request đồng thời hoàn thành đủ attempts trong cửa sổ đo, tải cực đại theo mô hình có thể gấp 27 lần; **không dùng phép nhân này như dự đoán chính xác số attempts/s khi có backoff, deadline và queueing**.

Với \(p=0.3\):

\[
E[A]=1+0.3+0.09=1.39.
\]

---

## 41. Bài tập 3: thiết kế bounded executor

Một API có 8 worker threads và SLO end-to-end 300 ms. DB mean=40 ms, p99=120 ms.

Yêu cầu:

- Không dùng unbounded queue.
- Queue capacity có lý do theo latency budget.
- Reject typed khi overload.
- Đo queue wait p95/p99.
- Hủy job chưa thực thi khi client hết deadline.
- Không giả định cancel job đang ghi là rollback.
- Cấu hình graceful shutdown.
- Tách bulkhead point reads và analytics.

Viết skeleton Java `ThreadPoolExecutor` và giải thích vì sao `CallerRunsPolicy` có thể không phù hợp cho HTTP event-loop.

---

## 42. Bài tập 4: rate limit và concurrency

Hai endpoint:

~~~text
GET /profile:
  1.000 req/s
  10 ms mean DB time

POST /reserve:
  200 req/s
  500 ms mean DB transaction time during contention
~~~

1. Số in-flight mean của từng endpoint?
2. Nếu dùng chung limiter 1.200 req/s, endpoint nào có thể chiếm nhiều concurrent resources?
3. Vì sao cần bulkhead hoặc weighted permits?
4. Nếu một endpoint bị hot key, tăng pool có giải quyết?
5. Đặt chính sách xử lý khi queue đầy cho từng endpoint.

Gợi ý:

\[
L_{\text{GET}}=1000\times0.01=10,
\]

\[
L_{\text{POST}}=200\times0.5=100.
\]

POST ít QPS hơn nhưng giữ tài nguyên đồng thời nhiều hơn.

---

## 43. Bài tập 5: phân loại retry và unknown outcome

Đối với NoSQL write:

| Lỗi/kết quả | Có nên retry ngay? | Cần idempotency? | Có phải UNKNOWN? |
|---|---|---|---|
| Validation rejected before DB call | ? | ? | ? |
| Conditional update returned condition false | ? | ? | ? |
| HTTP gateway timeout after DB call started | ? | ? | ? |
| DB write ACK success | ? | ? | ? |
| Overload rejected before admission | ? | ? | ? |
| Primary failover during transaction commit | ? | ? | ? |
| Search GSI has not seen new item | ? | ? | ? |
| Payment provider connection reset after charge request | ? | ? | ? |

Hãy chỉ ra đường xác minh outcome, request ID cần lưu và hành động tiếp theo an toàn.

---

## 44. Bài tập 6: fan-out và retry budget

Một admin query chạm 24 shards, mỗi shard có một query. Một application retry toàn bộ global query 3 lần khi một shard timeout.

1. Mỗi logical query có thể phát tối đa bao nhiêu shard attempts?
2. Khi 200 admin queries/s xảy ra, offered shard attempts tối đa theo mô hình?
3. Có thể retry chỉ shard lỗi không? Điều kiện snapshot/completeness?
4. Nếu chỉ có 8 concurrent shard permits, fan-out scheduling cần làm gì?
5. Khi một shard không sẵn sàng, nên trả partial hay lỗi?
6. Làm sao tách analytics khỏi inventory bulkhead?

Gợi ý: \(24\times3=72\) branch attempts cho một logical query theo mô hình đơn giản, nhưng semantics retry partial/global phụ thuộc consistency requirement.

---

## 45. Bài tập 7: backpressure consumer

Một Kafka consumer group nhận 50.000 events/s, mỗi event sinh một DB update. Khi NoSQL đang compaction chỉ xử lý ổn định 20.000 writes/s.

1. Nếu consumer tiếp tục pull và buffer vô hạn thì điều gì xảy ra?
2. Cách đặt maximum in-flight DB writes?
3. Cách sử dụng pause/resume partitions hoặc giới hạn poll?
4. Offset commit trước DB success có rủi ro nào?
5. Crash sau DB success trước offset commit dẫn đến gì?
6. Vì sao handler cần idempotency theo eventId?
7. Khi backlog lớn, tăng number consumers có giúp nếu DB vẫn chỉ chịu 20.000/s?
8. Metric nào phản ánh event lag và tuổi event chưa xử lý?

---

## 46. Bài tập 8: runbook tình huống thực tế

Bối cảnh:

~~~text
5 application instances.
Mỗi instance có 60 DB connection slots.
MongoDB đang bầu primary mới.
Gateway retry 3 attempts.
Application retry 3 attempts.
p99 tăng từ 80 ms lên 2 giây.
Queue của mỗi instance không giới hạn.
Một tenant chiếm 45% traffic.
Background report cũng đọc collection.
Một số payment callbacks bị timeout.
~~~

Hãy đề xuất:

1. Những số liệu cần xem đầu tiên.
2. Các tầng retry phải phối hợp lại thế nào.
3. Giới hạn concurrent DB operations mỗi instance.
4. Queue có hạn và queue wait budget.
5. Phân tách background report bulkhead.
6. Per-tenant fairness.
7. Bảo vệ payment unknown outcome và idempotency.
8. Cách trả 429/503/202 khi thích hợp.
9. Metric/alert để biết retry storm đang giảm.
10. Điều kiện mở lại concurrency sau primary hồi phục.

Không dùng một phép tính cứng để ra 60 permits chỉ vì pool có 60 connections; điều chỉnh dựa trên driver semantics, capacity và SLO.

---

## 47. Checklist thiết kế chống overload và retry amplification

Trước khi đưa một service NoSQL lên production, hãy trả lời:

1. **Offered vs accepted load** có được đo riêng?
2. **Rate limit** theo client/tenant/endpoint có tồn tại?
3. **Concurrency limit** đã gắn với DB operation thực tế chưa?
4. **Mọi queue** tại gateway, executor, connection pool, broker có bounded?
5. **Queue wait budget** có nhỏ hơn end-to-end deadline phù hợp không?
6. **Admission failure** có trả lỗi typed, nhanh và rõ?
7. **Retry ownership** có một nơi chịu trách nhiệm chính cho từng lỗi?
8. **Retry budget** có ràng buộc số attempts theo logical request và toàn service?
9. **Backoff+jitter** có tránh synchronized retry không?
10. **Timeout/deadline** có propagate qua các tầng?
11. **Unknown write outcome** có được phân biệt với pre-admission rejection?
12. **Idempotency key/ledger** có bảo vệ các write cần retry?
13. **CAS/transaction** có giữ business invariant khi client concurrent?
14. **Bulkheads** có ngăn search/analytics làm nghẽn checkout?
15. **Per-shard/tenant limits** có phát hiện hot partition?
16. **Fan-out/hedging** có tính vào downstream request budget?
17. **Async consumers** có backpressure và ack semantics phù hợp?
18. **DB driver retries** có được kiểm kê cùng application/gateway retries?
19. **Autoscaling** có thời gian chờ, cold cache và rebalance cost được tính?
20. **Metrics** gồm goodput, p99, queue age, reject, retry attempts và shard load?
21. **Load test** có slow replica, failover, partial outage và burst?
22. **Recovery** có gradual reopening và chống retry herd?
23. **Runbook** có phân biệt khi nào giảm tải, khi nào scale, khi nào bảo vệ dữ liệu?
24. **Postmortem** có ghi số logical requests vs physical attempts không?

---

## 48. Tổng kết

Để hệ NoSQL chịu được lỗi phân tán, điều quan trọng không phải là **nhận càng nhiều request càng tốt** mà là **duy trì số công việc có ích trong giới hạn năng lực thực tế**, đồng thời không khuếch đại một lỗi thành sự cố lớn hơn.

Những nguyên tắc cần nhớ:

1. **Rate limit kiểm soát tốc độ đến; concurrency limit kiểm soát số việc đang chạy; bounded queue kiểm soát số việc chờ.** Cả ba giải quyết những vấn đề khác nhau.
2. **Định luật Little giúp liên hệ throughput, latency và số in-flight trung bình** trong điều kiện ổn định; không dùng nó như bằng chứng p99 hoặc capacity trong overload.
3. **Queue vô hạn không tạo thêm throughput**; nó tích tụ latency, memory và công việc đã hết hạn.
4. **Reject sớm có thể bảo vệ goodput**, miễn API phản hồi rõ ràng và clients không retry ngay vô hạn.
5. **Retry nhiều tầng có thể nhân tải theo cấp số nhân**. Cần retry ownership, deadline, aggregate budget, backoff và jitter.
6. **Một logical request có thể fan-out thành nhiều DB operations**, cộng thêm quorum, hedged/speculative execution và retries. Hãy đo actual downstream attempts.
7. **Bulkhead và fairness bảo vệ workload quan trọng** trước hot tenant, hot shard, search và background jobs.
8. **Timeout write có thể là UNKNOWN**. Không retry non-idempotent operation với ID mới; phải có request ledger/CAS/transaction/reconciliation.
9. **Reactive hoặc virtual threads không làm DB vô hạn capacity**. In-flight permits và backpressure vẫn cần thiết.
10. **Hồi phục phải từ từ**. Sau failover hay compaction, mở lại concurrency và retry không kiểm soát có thể gây vòng overload mới.

**Câu cần nhớ: “Khi hệ chậm, đừng chất thêm yêu cầu vào một hàng đợi không đáy và đừng retry ồ ạt. Hãy giới hạn công việc đang chạy, giới hạn việc chờ, từ chối sớm phần vượt ngân sách và chỉ retry khi còn thời gian, còn capacity và thao tác an toàn để thực hiện lại.”**
