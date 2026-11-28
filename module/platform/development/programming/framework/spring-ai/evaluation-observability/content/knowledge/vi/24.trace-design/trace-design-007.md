# Phân tích retry, chờ đợi và các nhánh thực thi

Một request Spring AI có thể nhìn như một operation duy nhất ở API, nhưng bên trong có nhiều lần gọi model, retry HTTP, backoff, chờ connection pool, chờ queue, fan-out sang nhiều retrievers hoặc tool, rồi join kết quả trước khi trả lời. Nếu trace chỉ có một span tổng dài vài giây, ta biết request chậm nhưng không biết **thời gian nằm ở đâu, lần thử nào thất bại, nhánh nào quyết định latency cuối cùng và có operation nào bị chạy lặp ngoài dự kiến**.

Bài học thuộc chương **Thiết kế trace** của module `SPRING_AI_EVALUATION_OBSERVABILITY`. Module giúp đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời theo dõi metrics, traces, chi phí và độ trễ qua các phiên bản prompt, model và pipeline. Vì vậy, việc instrument retry, wait và execution branches phải giúp giải thích cả độ tin cậy vận hành lẫn biến động chất lượng/cost.

Sau bài học, bạn có thể:

- Phân biệt logical operation, attempt, retry backoff và thời gian chờ dependency.
- Thiết kế span tree cho retry, queue wait, fan-out/fan-in và tool loop.
- Tính latency theo wall-clock và critical path, tránh cộng trùng các nhánh chạy song song.
- Đặt timeout/deadline, retry budget, exponential backoff và jitter hợp lý.
- Nhận diện retry amplification giữa SDK, HTTP client, service và job runner.
- Theo dõi cancellation, fallback, idempotency và trạng thái cuối.
- Dùng Micrometer Observation/OpenTelemetry để tạo trace có thể điều tra trong Spring AI.

## 1. Một logical operation có thể có nhiều attempts

**Logical operation** là công việc nghiệp vụ mà hệ thống muốn hoàn tất, ví dụ “trả lời câu hỏi”, “tìm nguồn cho query” hoặc “đánh giá một case”. **Attempt** là một lần thực thi cụ thể của operation hoặc một dependency call. Một logical operation có thể có một hoặc nhiều attempts.

Ví dụ model provider timeout ở lần đầu, trả HTTP 503 ở lần hai và thành công ở lần ba:

```text
app.ai.answer                         [logical operation]
└── app.ai.model.generate             [logical model operation]
    ├── HTTP CLIENT attempt=1         ERROR: timeout
    ├── retry.backoff                 200 ms
    ├── HTTP CLIENT attempt=2         ERROR: HTTP 503
    ├── retry.backoff                 430 ms
    └── HTTP CLIENT attempt=3         success
```

Ở đây:

- `app.ai.answer` đo toàn bộ thời gian tạo answer.
- `app.ai.model.generate` đo logical model call gồm retry policy.
- Các HTTP client spans phản ánh request thực tế tới provider.
- Backoff là khoảng chờ giữa các attempts; có thể là event hoặc span nếu đủ dài/quan trọng.

Nếu instrumentation HTTP đã tạo spans cho từng request, không cần tạo một span thủ công trùng y hệt từng HTTP attempt. Span logical operation có thể bao quanh retry policy và chứa tổng attempt count/final outcome.

### 1.1. Không gộp mọi thứ vào một span “retry”

Một span duy nhất tên `retry` kéo dài từ đầu đến cuối sẽ che mất:

- Số lần request thực tế đã gửi.
- Attempt nào timeout, attempt nào trả 429/503.
- Thời gian xử lý dependency so với thời gian backoff.
- Retry có xảy ra ở tầng SDK hay tầng application.
- Attempt cuối có thành công hay vẫn thất bại.

Hãy giữ ranh giới operation, attempts và wait phù hợp với mục tiêu điều tra.

### 1.2. Không tạo span cho mọi vòng lặp vô nghĩa

Không phải mỗi vòng lặp nội bộ đều cần span. Nếu một vòng lặp chỉ kiểm tra một biến trong vài microseconds, attribute/event hoặc counter là đủ. Tạo span khi có operation có duration, I/O, retry, side effect hoặc ranh giới cần điều tra.

## 2. Mô hình timeline: duration, wait và attempt

Một operation kéo dài có thể gồm nhiều loại thời gian:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Queue wait | Chờ message được consumer nhận | 1.200 ms |
| Executor wait | Chờ thread/pool slot | 80 ms |
| Connection pool wait | Chờ connection | 45 ms |
| Dependency duration | Thời gian HTTP/DB/model call thực hiện | 600 ms |
| Backoff | Chờ trước attempt tiếp theo | 200 ms |
| Serialization/mapping | Chuẩn bị request hoặc xử lý response | 12 ms |
| Join wait | Chờ nhánh song song còn lại | 350 ms |

Một span tổng có thể bao phủ nhiều thành phần. Để phân tích đúng, cần biết thành phần nào có span riêng, thành phần nào chỉ là khoảng chờ, và thành phần nào chồng thời gian với nhánh khác.

### 2.1. Wall-clock duration

Wall-clock duration là thời gian thực từ start đến end của một operation:

\[
T_{\text{wall}} = t_{\text{end}} - t_{\text{start}}
\]

Đây là thời gian người dùng hoặc caller phải chờ nếu operation nằm trên đường phản hồi.

### 2.2. Self-time và child duration

Một span cha có thể chứa các spans con. Self-time là phần thời gian cha thực thi ngoài các khoảng được tính cho child spans theo cách backend hiển thị. Tùy công cụ, self-time có thể được tính xấp xỉ và không nhất thiết bằng phép trừ đơn giản khi children chạy song song hoặc không bao phủ toàn bộ operation.

Không cộng duration của tất cả child spans để suy ra wall-clock. Nếu hai child chạy song song, tổng duration của chúng có thể lớn hơn duration cha.

### 2.3. Một timeline có retry

```text
Time (ms)  0       300  500       950  1100
           |--------|----|----------|----|
model op   [-----------------------------]
attempt 1  [------]
backoff           [----]
attempt 2              [---------]
backoff                           [--]
attempt 3                              [---]
```

Giả sử:

- Attempt 1 mất 300 ms.
- Backoff 1 mất 200 ms.
- Attempt 2 mất 450 ms.
- Backoff 2 mất 150 ms.
- Attempt 3 mất 150 ms.

Logical operation mất 1.250 ms. Tổng dependency time là 900 ms; tổng backoff là 350 ms. Nếu chỉ nhìn span model 1.250 ms, khó biết 28% thời gian là chờ retry.

## 3. Thiết kế span cho retry

### 3.1. Span logical operation và attempt spans

Một mô hình phổ biến:

```text
app.ai.model.generate
  attributes:
    retry.max_attempts = 3
    retry.attempt_count = 3
    retry.final_outcome = success
  ├── gen_ai.client.request / HTTP attempt 1   ERROR
  ├── retry.backoff                            event/span
  ├── gen_ai.client.request / HTTP attempt 2   ERROR
  ├── retry.backoff                            event/span
  └── gen_ai.client.request / HTTP attempt 3   OK
```

Tên HTTP/GenAI spans phụ thuộc instrumentation; không tự giả định một tên cụ thể cho mọi Spring AI version. Nếu provider client tự instrument retries, hãy xem trace thực tế trước khi thêm attempt spans thủ công.

### 3.2. Attributes cần cho retry

| Key gợi ý | Kiểu | Ví dụ | Ý nghĩa |
|---|---|---|---|
| `app.retry.policy` | string | `model-transient-v2` | Policy áp dụng |
| `app.retry.max_attempts` | integer | `3` | Giới hạn attempts |
| `app.retry.attempt` | integer | `2` | Attempt hiện tại |
| `app.retry.reason` | string enum | `timeout` | Lý do đã phân loại |
| `app.retry.delay_ms` | integer | `400` | Backoff được chọn |
| `app.retry.final_outcome` | string enum | `success` | Kết quả cuối |
| `app.retry.exhausted` | boolean | `false` | Đã hết budget chưa |

Giữ attribute values trong tập hữu hạn nếu có thể. Không dùng exception message, raw URL hoặc request payload làm retry reason.

### 3.3. Event hay span cho backoff?

Chọn theo độ dài và ý nghĩa:

- Backoff 10–30 ms có thể ghi attribute/event trên logical operation.
- Backoff hàng trăm milliseconds hoặc seconds có thể đáng để tạo span `app.retry.backoff` nhằm thấy rõ thời gian chờ.
- Nếu scheduler/queue đã tạo span chờ hoặc delay, không tạo span trùng lặp.
- Event `retry_scheduled` có thể ghi attempt tiếp theo, delay và reason; span backoff đo duration thực tế nếu cần.

### 3.4. Error status của attempts và logical operation

Một attempt lỗi nhưng logical operation cuối cùng thành công:

- Attempt span có thể là ERROR theo lỗi của request đó.
- Logical operation cuối cùng có thể không ERROR vì retry phục hồi thành công.
- Attribute `app.retry.attempt_count` và `app.retry.recovered` giải thích quá trình.
- Metrics vẫn phải đếm số dependency failures/attempts, không chỉ logical failures.

Nếu mọi attempt thất bại, logical operation nên có ERROR và `app.retry.exhausted=true`. Không xóa lỗi attempt trước chỉ vì attempt sau thành công; lịch sử này giải thích latency và cost.

## 4. Retry ở nhiều tầng và retry amplification

Một ứng dụng Spring AI có thể có retry ở:

1. SDK của model provider.
2. HTTP client/transport.
3. Spring Retry hoặc Resilience4j.
4. Service orchestration.
5. Message broker redelivery.
6. Evaluation runner/scheduler.

Nếu mỗi tầng đều cho phép nhiều attempts, số request thực tế có thể lớn hơn dự kiến.

### 4.1. Ví dụ retry amplification

Giả sử:

- Application service thử tối đa 3 lần.
- HTTP client tự retry tối đa 2 lần cho mỗi lần gọi.
- SDK provider tự retry tối đa 3 lần cho mỗi HTTP request.

Trong trường hợp xấu, số provider requests có thể lên tới:

\[
3 \times 2 \times 3 = 18
\]

Đây là phép nhân minh họa khi các tầng retry độc lập và mỗi tầng có thể kích hoạt tối đa số attempts nêu trên. Một số thư viện chia sẻ retry budget hoặc không retry cho mọi lỗi, vì vậy phải đo số request thật ở transport/stub/provider metrics.

### 4.2. Chọn một owner cho retry policy

Với mỗi dependency, xác định rõ:

- Tầng nào sở hữu retry policy chính.
- Các tầng thấp hơn có retry hay không.
- Lỗi nào retry được.
- Tổng attempts và tổng deadline.
- Cách tính Retry-After, backoff và jitter.
- Cách ghi attempt count và final outcome.

Nếu SDK provider đã retry transient failures, application không nên bọc thêm retry rộng mà không hiểu hành vi đó. Hãy cấu hình một retry owner hoặc giới hạn rõ retry ở từng tầng.

### 4.3. Phân biệt retry với fallback

Retry thực hiện lại cùng operation vì lỗi tạm thời. Fallback chuyển sang một chiến lược khác:

- Retry vector search sau timeout.
- Fallback từ semantic retrieval sang keyword retrieval khi backend semantic unavailable.
- Retry model call sau HTTP 429.
- Fallback sang cached answer hoặc model khác theo policy.

Trace nên thể hiện fallback rõ ràng bằng span/event/attribute riêng. Không gọi fallback là retry vì semantics, latency, quality và cost khác nhau.

## 5. Backoff, jitter và Retry-After

Retry cần có khoảng chờ để tránh gửi request liên tục vào một dependency đang quá tải. Một công thức exponential backoff cơ bản:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Trong đó \(d_0\) là delay ban đầu, \(n\) là số thứ tự attempt tiếp theo và \(d_{\max}\) là giới hạn delay.

Ví dụ \(d_0=200\) ms, \(d_{\max}=2.000\) ms:

| Attempt tiếp theo | Delay trước jitter |
|---:|---:|
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 1.600 ms |
| 6 | 2.000 ms (cap) |

### 5.1. Jitter tránh đồng loạt retry

Nếu hàng nghìn clients nhận lỗi cùng lúc và cùng retry sau đúng 1 giây, hệ thống có thể nhận một đợt request mới đồng loạt. Jitter thêm ngẫu nhiên vào delay để phân tán tải.

Một biến thể full jitter:

\[
d_n^{\text{actual}} \sim U(0, d_n)
\]

Trong đó \(U(0,d_n)\) là phân phối đều từ 0 tới delay cap của attempt. Các chiến lược khác có thể dùng equal jitter hoặc decorrelated jitter; chọn một thuật toán thống nhất và ghi policy version.

### 5.2. Retry-After

HTTP 429 hoặc 503 có thể trả header `Retry-After`. Nếu provider gửi giá trị hợp lệ:

- Ưu tiên tôn trọng server hint trong giới hạn deadline và policy.
- Không retry sớm hơn thời điểm server yêu cầu chỉ vì local backoff nhỏ hơn.
- Nếu Retry-After vượt request deadline, kết thúc bằng timeout/deadline exceeded thay vì chờ vô hạn.
- Ghi nguồn delay như `server_hint` hoặc `client_backoff`, không ghi nguyên response body.

### 5.3. Không retry mọi lỗi

Thông thường có thể retry một số lỗi tạm thời như timeout, connection reset, 429 hoặc một số 5xx. Không nên retry mặc định:

- Validation error do request sai.
- Authentication/authorization failure.
- Tool policy denied.
- Judge trả verdict FAIL hợp lệ.
- 4xx nghiệp vụ không được xác định là transient.
- Operation có side effect không idempotent khi chưa có cơ chế chống lặp.

Danh sách chính xác phải theo provider API, transport và business contract; không dùng một rule “retry mọi exception”.

### 5.4. Retry budget và deadline

Đặt giới hạn theo cả:

- Maximum attempts.
- Tổng thời gian operation.
- Tổng số provider requests.
- Tổng token/cost budget nếu operation gọi model.
- Deadline còn lại của request/job.

Một attempt mới chỉ nên bắt đầu nếu còn đủ thời gian cho attempt và xử lý response. Retry không được kéo operation vượt deadline của caller một cách âm thầm.

## 6. Timeout, deadline và cancellation

Ba khái niệm thường bị nhầm:

- **Timeout:** giới hạn thời gian cho một operation hoặc một lần chờ/call cụ thể.
- **Deadline:** thời điểm tuyệt đối mà toàn bộ logical operation phải hoàn tất.
- **Cancellation:** tín hiệu dừng công việc vì caller không còn cần kết quả hoặc deadline đã hết.

Ví dụ HTTP request có deadline 3 giây. Model call có timeout 2 giây, nhưng request đã tiêu tốn 1,5 giây cho retrieval và tool. Không thể bắt đầu một attempt model mới với timeout 2 giây nếu deadline còn lại chỉ 1,5 giây.

### 6.1. Propagate deadline còn lại

Mỗi downstream call nên nhận timeout nhỏ hơn hoặc bằng deadline còn lại. Có thể tính:

\[
T_{\text{remaining}} =
\max(0, T_{\text{deadline}} - T_{\text{now}})
\]

Khi \(T_{\text{remaining}}=0\), không bắt đầu attempt mới. Với HTTP/gRPC, truyền timeout/deadline theo cơ chế transport/framework hỗ trợ; không chỉ đặt timeout ở UI hoặc ở outer controller.

### 6.2. Span cho timeout và cancellation

Ghi rõ operation bị kết thúc vì:

- `timeout`: dependency không trả kết quả trong giới hạn.
- `deadline_exceeded`: logical operation hết tổng budget.
- `cancelled_by_caller`: caller đóng request hoặc hủy future.
- `cancelled_by_parent`: parent operation bị hủy.
- `shutdown`: service dừng và task bị hủy.

Đây là error/outcome categories gợi ý. Không ghi raw cancellation message nếu có thể chứa thông tin nhạy cảm.

Một span bị cancel nên kết thúc đúng lifecycle và không để child spans tiếp tục chạy vô hạn. Nếu task không thể hủy ngay (ví dụ blocking JDBC call), ghi nhận cancellation requested và operation thực sự kết thúc ở thời điểm nào; đừng giả định cancel future đồng nghĩa dependency đã dừng.

### 6.3. Không retry sau deadline

Pseudo-flow:

```text
while attempts remain:
  remaining = deadline - now
  if remaining <= 0:
      finish(DEADLINE_EXCEEDED)

  attemptTimeout = min(configuredAttemptTimeout, remaining)
  result = invokeDependency(attemptTimeout)

  if success:
      finish(SUCCESS)

  if error is not retryable:
      finish(ERROR)

  delay = backoff(attempt)
  if delay >= remaining:
      finish(DEADLINE_EXCEEDED)

  wait(delay)
```

Pseudo-flow cần thêm cancellation checks, Retry-After và idempotency policy theo dependency. Nó mô tả logic, không phải code production hoàn chỉnh.

## 7. Phân tích các khoảng chờ

Một trace có duration lớn không có nghĩa dependency thực thi chậm. Operation có thể tiêu tốn phần lớn thời gian để **chờ được thực thi**.

### 7.1. Queue wait

Với message-driven evaluation:

```text
TRACE T1: answer request
  app.ai.answer
    └── evaluation.event.publish

QUEUE
  message produced at t0
  consumer starts at t1
  queue wait = t1 - t0

TRACE T2: evaluation worker
  app.ai.evaluation.process
    ├── judge.model.generate
    └── evaluation.result.persist
```

Queue wait không nhất thiết là duration của một span child vì producer và consumer có thể thuộc hai traces/lifecycles khác nhau. Ghi timestamps/metrics từ broker hoặc messaging instrumentation:

- Message publish time.
- Consumer start time.
- Queue/partition/consumer group đã chuẩn hóa.
- Delivery count.
- Queue/lag/wait duration.

Không dùng raw message body hoặc user ID làm attributes. Nếu consumer trace là trace riêng, có thể link tới producer span theo thiết kế messaging; correlation IDs nghiệp vụ vẫn cần trong event/result store.

### 7.2. Executor wait và pool saturation

Nếu task được submit vào executor nhưng thread chỉ bắt đầu sau 500 ms, thời gian đó là queueing delay trong executor. Span được tạo **sau khi task bắt đầu** có thể không bao gồm thời gian chờ này.

Để đo:

- Ghi submit timestamp và task start timestamp.
- Dùng executor metrics: active threads, queue size, completed tasks, rejected tasks.
- Có thể tạo một span/job operation từ lúc submit đến lúc hoàn tất nếu operation có ý nghĩa và context/lifecycle phù hợp.
- Tạo event hoặc attribute `queue_wait_ms` trên job span.

Đừng chỉ tăng thread pool khi chưa xác định bottleneck; thread nhiều hơn có thể tăng contention, connection pressure và model provider rate limit.

### 7.3. Connection pool wait

Một DB span có thể chỉ đo thời gian query sau khi đã lấy connection, trong khi request chờ pool slot trước đó. Theo dõi:

- Connection acquire latency.
- Active/idle/pending connections.
- Pool timeout/rejection.
- SQL duration riêng.

Nếu backend instrumentation không tạo span riêng cho acquire wait, dùng pool metrics hoặc custom observation ở ranh giới acquire. Không nhầm pool wait với database query duration.

### 7.4. Lock contention và rate limiter wait

Các operation có thể chờ:

- Semaphore/concurrency limiter.
- Rate limiter token.
- Distributed lock.
- Circuit breaker half-open permit.
- Application-level queue.

Nếu thời gian chờ ảnh hưởng latency, ghi duration/metrics ở ranh giới đó. Span/event nên dùng tên rõ như `app.ai.rate_limit.wait` hoặc `app.ai.semaphore.acquire`, không dùng tên chung `wait`.

## 8. Circuit breaker, bulkhead và retry

Retry có thể giúp vượt lỗi transient, nhưng nếu dependency đang down, retries làm tăng tải. Circuit breaker và bulkhead giới hạn ảnh hưởng lan rộng.

### 8.1. Circuit breaker

Circuit breaker có các trạng thái thường gặp:

- **CLOSED:** cho phép calls; thống kê lỗi.
- **OPEN:** chặn calls nhanh trong thời gian reset.
- **HALF_OPEN:** cho phép một số probe calls để kiểm tra dependency hồi phục.

Trace nên thể hiện:

- Operation bị short-circuit không gọi dependency thật.
- Circuit state và outcome đã chuẩn hóa.
- Probe attempt ở HALF_OPEN.
- Fallback nếu được kích hoạt.

Không tạo HTTP client span giả cho một call bị circuit breaker chặn trước transport. Có thể tạo span/event `circuit_breaker.rejected` và attribute `dependency.name`.

### 8.2. Bulkhead

Bulkhead giới hạn concurrency hoặc cô lập tài nguyên. Khi không lấy được permit:

- Ghi outcome `rejected` hoặc `bulkhead_full`.
- Đo thời gian chờ permit nếu có queueing.
- Không đánh đồng rejection với dependency timeout.
- Theo dõi active permits, queue size và rejection counter.

### 8.3. Circuit breaker không phải retry

Retry thử lại operation; circuit breaker quyết định có cho phép call đi tiếp không. Nếu circuit OPEN, retry liên tục thường không có ích. Chỉ retry khi breaker policy cho phép và dependency có cơ hội hồi phục.

### 8.4. Trace model cho resilience

```text
app.ai.tool.execute
  ├── bulkhead.acquire
  ├── circuit_breaker.check
  ├── HTTP CLIENT attempt=1  ERROR: 503
  ├── retry.backoff
  ├── circuit_breaker.check
  └── fallback.cache.read    SUCCESS
```

Đây là mô hình minh họa; implementation có thể đặt circuit breaker quanh toàn logical operation hoặc từng attempt. Span hierarchy phải phản ánh vị trí thực tế của decorator/aspect.

## 9. Fan-out và fan-in: nhiều nhánh thực thi trong một operation

RAG hybrid thường chạy semantic search và keyword search song song. Tool orchestration cũng có thể gọi nhiều tool độc lập rồi tổng hợp kết quả. Đây là **fan-out/fan-in**:

- Fan-out: một parent operation khởi chạy nhiều nhánh.
- Fan-in: parent chờ hoặc tổng hợp kết quả từ các nhánh.

### 9.1. Cây span cho hai retrievers song song

```text
app.rag.hybrid.retrieve
  ├── app.rag.semantic.search
  │     └── DB/HTTP client
  └── app.rag.keyword.search
        └── DB/HTTP client
```

Hai child spans có cùng parent, có thể chồng thời gian. Nếu parent chờ cả hai hoàn tất, latency của parent thường bị chi phối bởi nhánh chậm nhất cộng overhead trước/sau fan-out.

### 9.2. Wall-clock và critical path

Giả sử:

- Semantic search mất 420 ms.
- Keyword search mất 260 ms.
- Hai nhánh bắt đầu gần như cùng lúc.
- Merge mất 40 ms.

Latency gần đúng của retrieval:

\[
T_{\text{retrieve}} \approx
\max(420,260)+40 = 460\text{ ms}
\]

Không phải \(420+260+40=720\) ms, vì hai nhánh chạy song song. Nếu có 80 ms chuẩn bị trước fan-out và 30 ms overhead sau merge, tổng wall-clock có thể khoảng 570 ms. Hãy xem timeline thực tế thay vì cộng tất cả child durations.

### 9.3. Một nhánh chậm có thể quyết định toàn operation

Nếu semantic mất 420 ms và keyword mất 1.800 ms, parent chờ cả hai có thể mất khoảng 1.840 ms hoặc hơn. Cần xem:

- Có thật sự cần chờ cả hai không?
- Có thể dùng early result/first-success strategy không?
- Nhánh chậm có timeout riêng không?
- Khi một nhánh lỗi, có thể fallback sang nhánh còn lại không?
- Merge có đợi một future bị treo vì cancellation không?

Nếu logic yêu cầu cả hai nguồn, timeout/cancel cần có policy rõ; không âm thầm bỏ nhánh rồi vẫn báo đủ evidence.

### 9.4. Fan-out nhiều tool

Một agent có thể gọi tool inventory và tool policy song song:

```text
app.ai.answer
  └── app.ai.tool.dispatch
        ├── app.ai.tool.execute inventory.lookup
        └── app.ai.tool.execute policy.lookup
  └── app.ai.model.generate
```

Nếu model yêu cầu hai tools trong cùng một lượt và ứng dụng thực thi song song, hai execution spans là siblings. Model generation tiếp theo chỉ bắt đầu sau khi kết quả được tổng hợp, nếu protocol/orchestration yêu cầu.

## 10. Timeout và partial result trong nhánh song song

Fan-out thường cần một trong ba chính sách:

1. **All required:** đợi tất cả nhánh; một nhánh lỗi làm operation thất bại hoặc kích hoạt fallback đã định nghĩa.
2. **First successful/quorum:** hoàn tất khi có một hoặc đủ số nhánh thành công; hủy nhánh còn lại nếu không cần.
3. **Best effort:** chờ tới deadline, dùng các nhánh hoàn tất và ghi rõ nguồn thiếu.

### 10.1. Ghi partial result đúng nghĩa

Một response có thể được tạo từ một trong hai retrievers vì nhánh còn lại timeout. Trace cần cho thấy:

```text
app.rag.hybrid.retrieve
  attributes:
    app.rag.branch.expected = 2
    app.rag.branch.completed = 1
    app.rag.partial_result = true
  ├── semantic.search   SUCCESS
  └── keyword.search    TIMEOUT / CANCELLED
```

`partial_result=true` là outcome vận hành, không tự động nói retrieval quality FAIL. Evaluation phải xem nguồn thực tế đã dùng và chấm relevance/groundedness theo rubric.

### 10.2. Cancellation phải truyền xuống nhánh

Khi parent đạt quorum hoặc deadline:

- Hủy futures/Reactive subscriptions còn lại nếu operation cho phép.
- Propagate cancellation tới HTTP client/driver nếu hỗ trợ.
- Kết thúc child spans với outcome phù hợp.
- Đo thời gian từ cancellation request tới khi task thực sự dừng.
- Không tính một child đã hủy là thành công.

Một future bị cancel ở caller không bảo đảm socket/DB query đã dừng. Nếu dependency tiếp tục chạy, trace và metrics nên phản ánh điều đó để phát hiện resource leak.

### 10.3. Branch identifiers

Nếu cần xác định từng nhánh, dùng attribute có giá trị giới hạn:

| Key | Ví dụ |
|---|---|
| `app.ai.branch.name` | `semantic` / `keyword` |
| `app.ai.branch.strategy` | `hybrid` |
| `app.ai.branch.required` | `true` |
| `app.ai.branch.outcome` | `success` / `timeout` / `cancelled` |

Không nhúng query, document ID hoặc customer ID vào span name. Nếu cần provenance từng nguồn, lưu source IDs trong result artifact theo chính sách.

## 11. Parallel execution, executor và Reactor

Một nhánh chạy trên thread khác vẫn có thể là child span của parent nếu context được capture/propagate đúng và công việc thuộc cùng logical operation.

### 11.1. Executor context propagation

Với Spring Framework 6.1+, có thể cấu hình executor sử dụng `ContextPropagatingTaskDecorator`:

```java
import java.util.concurrent.Executor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class AiExecutorConfiguration {
    @Bean("ragExecutor")
    Executor ragExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("rag-");
        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
```

Task decorator capture/restore context được hỗ trợ trong lúc submit và thực thi. Cần cấu hình context propagation phù hợp với Micrometer/Tracing bridge đang dùng; class này không tự instrument mọi operation và không quyết định retry/branch policy. Với Spring Framework cũ hơn, chọn cơ chế tương thích version.

### 11.2. Chạy hai nhánh và đợi kết quả

Ví dụ minh họa bằng `CompletableFuture`:

```java
CompletableFuture<List<Document>> semanticFuture =
        CompletableFuture.supplyAsync(
                () -> semanticRetriever.search(query),
                ragExecutor);

CompletableFuture<List<Document>> keywordFuture =
        CompletableFuture.supplyAsync(
                () -> keywordRetriever.search(query),
                ragExecutor);

CompletableFuture<List<Document>> mergedFuture =
        semanticFuture.thenCombine(
                keywordFuture,
                this::mergeAndDeduplicate);

List<Document> documents = mergedFuture.join();
```

Đây là đoạn minh họa orchestration; các retrievers nên instrument operation bên trong, hoặc dùng instrumentation framework hiện có. Không tạo thêm span bọc từng future nếu một observation đã được tạo ở retriever/service layer.

### 11.3. Reactor context

Trong pipeline Reactor, thread có thể thay đổi qua scheduler operators. Không dựa vào ThreadLocal thông thường để giữ trace context. Dùng Micrometer Context Propagation/Reactor integration tương thích với Spring Boot version, và kiểm tra:

- Span trước và sau `publishOn`/`subscribeOn` có đúng parent.
- Context được khôi phục khi signal chạy ở thread khác.
- Cancellation signal kết thúc child spans.
- Retry operator tạo attempt spans hoặc events theo policy.
- Không tạo nhiều active spans bị giữ mở sau `onError`/`cancel`.

### 11.4. Không dùng common pool không kiểm soát

`ForkJoinPool.commonPool()` có thể dùng chung cho nhiều workload không liên quan. Khi model/RAG tasks blocking hoặc chờ network, common pool có thể bị starvation. Dùng executor có giới hạn, queue capacity, rejection policy và metrics phù hợp; đo queue wait và active threads.

## 12. Ví dụ Java: instrument logical call, attempt và backoff

Ví dụ dưới đây minh họa một retry owner ở tầng ứng dụng bằng Micrometer Observation. Nó không thay thế retry mechanism của provider SDK; trước khi dùng cần tắt hoặc giới hạn retry ở tầng khác để tránh amplification.

### 12.1. Retry executor có observation riêng

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.time.Duration;
import java.util.concurrent.Callable;

final class ObservedRetryExecutor {
    private final ObservationRegistry observations;

    ObservedRetryExecutor(ObservationRegistry observations) {
        this.observations = observations;
    }

    <T> T execute(
            String dependency,
            int maxAttempts,
            Callable<T> operation) {

        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "maxAttempts must be at least 1");
        }

        Observation logical = Observation.createNotStarted(
                        "app.dependency.call", observations)
                .lowCardinalityKeyValue(
                        "app.dependency.name", dependency)
                .lowCardinalityKeyValue(
                        "app.retry.max_attempts",
                        Integer.toString(maxAttempts));

        return logical.observe(() -> {
            for (int attempt = 1; attempt <= maxAttempts; attempt++) {
                try {
                    return Observation.createNotStarted(
                                    "app.dependency.attempt", observations)
                            .lowCardinalityKeyValue(
                                    "app.dependency.name", dependency)
                            .lowCardinalityKeyValue(
                                    "app.retry.attempt",
                                    Integer.toString(attempt))
                            .observe(() -> invoke(operation));
                } catch (AttemptFailure failure) {
                    if (!isRetryable(failure.getCause())
                            || attempt == maxAttempts) {
                        throw failure;
                    }

                    Duration delay = backoff(attempt);
                    Observation.createNotStarted(
                                    "app.retry.backoff", observations)
                            .lowCardinalityKeyValue(
                                    "app.retry.reason",
                                    classify(failure.getCause()))
                            .observe(() -> sleep(delay));
                }
            }
            throw new IllegalStateException("Unreachable retry state");
        });
    }

    private <T> T invoke(Callable<T> operation) {
        try {
            return operation.call();
        } catch (Exception error) {
            throw new AttemptFailure(error);
        }
    }

    private boolean isRetryable(Throwable error) {
        return error instanceof java.net.SocketTimeoutException
                || error instanceof java.io.IOException;
    }

    private String classify(Throwable error) {
        return error instanceof java.net.SocketTimeoutException
                ? "timeout" : "io_error";
    }

    private Duration backoff(int failedAttempt) {
        int exponent = Math.min(failedAttempt - 1, 4);
        long delayMs = Math.min(2_000L, 200L * (1L << exponent));
        return Duration.ofMillis(delayMs);
    }

    private void sleep(Duration delay) {
        try {
            Thread.sleep(delay.toMillis());
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new AttemptFailure(interrupted);
        }
    }

    private static final class AttemptFailure extends RuntimeException {
        AttemptFailure(Throwable cause) {
            super(cause);
        }
    }
}
```

Đây là ví dụ giáo dục rút gọn, chưa có jitter, Retry-After, deadline propagation, cancellation token hoặc retry budget tổng. Danh sách retryable exceptions phải theo contract dependency; `IOException` trong ví dụ không có nghĩa mọi lỗi I/O đều retry an toàn. Production cần thêm giới hạn thời gian và idempotency.

### 12.2. Gọi ChatClient qua retry owner

Nếu ứng dụng thực sự sở hữu retry policy cho model call:

```java
String answer = retryExecutor.execute(
        "chat-model",
        3,
        () -> chatClient.prompt()
                .user(question)
                .call()
                .content());
```

Trước khi áp dụng, kiểm tra ChatModel/provider SDK/HTTP client hiện có retry chưa. Nếu đã có, ưu tiên quan sát attempts do client phát ra hoặc cấu hình một retry layer duy nhất. Không bọc thêm retry chỉ để có span.

### 12.3. Lưu ý về Observation lifecycle

- Logical observation bao toàn bộ attempts và backoff.
- Attempt observation chỉ bao một lần gọi dependency.
- Backoff observation chỉ bao khoảng sleep thực tế.
- Khi attempt lỗi, observation kết thúc cùng exception để handler có thể đánh dấu error.
- Khi retry phục hồi, logical operation kết thúc thành công; metrics vẫn đếm attempt failures.

Nếu muốn thêm `attempt_count` cuối cùng lên logical span, dùng API cập nhật context/observation phù hợp phiên bản và chỉ cập nhật trước khi observation dừng. Không giả định mọi key-values đều có thể sửa sau khi start.

## 13. Queue wait, redelivery và job retry

Với evaluation worker, cần phân biệt:

- **Queue wait:** thời gian message nằm trong broker trước khi consumer bắt đầu.
- **Processing duration:** thời gian một consumer invocation xử lý message.
- **Retry backoff:** thời gian worker chờ trước khi thử lại dependency.
- **Redelivery delay:** thời gian broker chờ trước khi phát lại message sau lỗi/nack/visibility timeout.
- **Scheduled retry:** job runner lên lịch một invocation mới sau một khoảng thời gian.

### 13.1. Một message được retry bên trong worker

```text
app.ai.evaluation.process
  ├── judge.attempt 1      ERROR: timeout
  ├── retry.backoff        500 ms
  ├── judge.attempt 2      ERROR: 429
  ├── retry.backoff        1.000 ms
  ├── judge.attempt 3      SUCCESS
  └── evaluation.persist  SUCCESS
```

Các attempts là child của cùng worker invocation vì cùng một lần xử lý message và cùng deadline/budget. Ghi `delivery_count` riêng nếu broker cung cấp; không nhầm attempt nội bộ với số lần broker redelivery.

### 13.2. Broker redelivery tạo invocation mới

Nếu worker chết trước khi ack hoặc message visibility timeout, broker có thể giao lại message. Lần xử lý mới có thể có trace mới hoặc tiếp tục producer context theo messaging convention, nhưng cần giữ:

- Event/message ID ổn định.
- Delivery count/attempt metadata từ broker.
- Run/case/variant/rubric version.
- Trace ID của từng invocation.
- Final result key/idempotency key.

Trace mới không có nghĩa là một evaluation case mới. Một case có thể có nhiều processing attempts nhưng chỉ một final result hợp lệ theo run contract.

### 13.3. Queue delay và end-to-end job latency

Đo riêng:

\[
T_{\text{job}} =
T_{\text{queue wait}} +
T_{\text{processing}}
\]

Nếu có scheduled retry/redelivery:

\[
T_{\text{job total}} =
\sum T_{\text{queue wait},i} +
\sum T_{\text{processing},i} +
\sum T_{\text{scheduled delay},i}
\]

Đây là phép cộng theo timeline tuần tự. Nếu job có nhiều nhánh song song, phải tính wall-clock/critical path chứ không cộng duration của tất cả nhánh.

### 13.4. Dead-letter queue

Khi vượt delivery/retry limit, message có thể chuyển sang DLQ. Trace/event cần cho biết:

- Lý do đưa vào DLQ đã phân loại.
- Delivery count cuối.
- Error type cuối.
- Event/case ID opaque để tra result.
- Hành động tiếp theo: manual review, replay hoặc mark ERROR.

Không ghi toàn bộ payload vào log/trace DLQ. DLQ không đồng nghĩa evaluation FAIL; có thể là ERROR vì operation chưa hoàn thành.

## 14. Idempotency và side effects khi retry

Retry an toàn với một số read-only operations, nhưng nguy hiểm khi operation tạo side effect:

- Tool đặt hàng hoặc hoàn tiền.
- Gửi email/notification.
- Ghi dữ liệu hoặc cập nhật trạng thái workflow.
- Tạo evaluation result mới hoặc charge model usage.

Nếu client timeout sau khi server đã thực hiện side effect nhưng response bị mất, retry có thể thực hiện side effect lần thứ hai.

### 14.1. Idempotency key

Một tool execution có thể dùng key nghiệp vụ ổn định:

```text
tool_operation_key =
  (conversation_id, tool_call_id)

payment_key =
  (tenant_scope, business_operation_id)

evaluation_result_key =
  (run_id, case_id, variant, rubric_version)
```

Đây là ví dụ; key thật phải theo business contract. Tracing IDs không phải idempotency keys. Một retry có thể có attempt span ID khác nhưng phải giữ cùng idempotency key cho cùng một logical side effect.

### 14.2. Ghi trace để phân biệt duplicate và retry

Các thuộc tính gợi ý:

| Key | Ví dụ | Ý nghĩa |
|---|---|---|
| `app.operation.idempotency_supported` | `true` | Operation có cơ chế chống lặp |
| `app.operation.idempotency_result` | `created` / `replayed` | Kết quả xử lý key |
| `app.operation.duplicate_detected` | `true` | Request trùng được nhận diện |
| `app.retry.attempt` | `2` | Attempt hiện tại |
| `app.operation.logical_id` | Opaque ID | Tra logical operation |

Không ghi idempotency key có chứa customer/order data trực tiếp vào telemetry nếu có thể liên kết tới dữ liệu nhạy cảm. Có thể dùng opaque hash/pseudonymous identifier theo policy.

### 14.3. Tool calling trong Spring AI

Model có thể phát cùng tool call lại sau timeout hoặc sau khi hội thoại được replay. Ứng dụng cần xác định:

- Tool có read-only hay có side effect.
- Tool call ID có ổn định qua retry hay không.
- Server downstream có hỗ trợ idempotency key không.
- Kết quả đã thực hiện nhưng response bị mất được khôi phục thế nào.
- Retry có giữ nguyên arguments/operation intent hay model được gọi lại và tạo tool call mới.

Không coi hai tool calls giống tên là cùng một operation. Dùng tool call ID/business operation ID để phân biệt.

## 15. Đọc một trace để tìm bottleneck

Hãy phân tích timeline theo thứ tự:

1. Xác định root operation và user-visible deadline.
2. Tìm các khoảng chờ trước khi dependency bắt đầu.
3. Đếm attempts thực tế và phân biệt tầng retry.
4. Xác định backoff, Retry-After và retry budget.
5. Với nhánh song song, tìm nhánh nằm trên critical path.
6. Kiểm tra cancellation/fallback và kết quả cuối.
7. Đối chiếu token/cost và evaluation result.

### 15.1. Case A: model call chậm do retry

```text
app.ai.answer                              2.450 ms
└── app.ai.model.generate                  2.180 ms
    ├── HTTP attempt 1                     620 ms  TIMEOUT
    ├── retry.backoff                      300 ms
    ├── HTTP attempt 2                     810 ms  503
    ├── retry.backoff                      250 ms
    └── HTTP attempt 3                     200 ms  SUCCESS
```

Nhận định:

- Dependency time là 1.630 ms.
- Backoff là 550 ms.
- Model logical operation mất 2.180 ms.
- Attempt cuối phục hồi thành công nhưng hai failures đầu vẫn có ý nghĩa vận hành.
- Cần kiểm tra retry policy, provider health, rate limit và tổng token/cost.

### 15.2. Case B: RAG chậm vì một nhánh fan-out

```text
app.rag.hybrid.retrieve                  1.920 ms
  ├── semantic.search                      390 ms
  └── keyword.search                     1.870 ms
app.rag.results.merge                      50 ms
```

Hai nhánh bắt đầu gần nhau và parent đợi cả hai. Keyword search nằm trên critical path. Cộng hai child durations thành 2.260 ms sẽ sai vì chúng chạy song song; wall-clock khoảng 1.920 ms phản ánh thời gian chờ thực tế của parent.

Kiểm tra keyword index, query plan, pool wait, filter và timeout. Nếu product semantics cho phép, cân nhắc early-result/quorum strategy; nếu không, tối ưu nhánh chậm.

### 15.3. Case C: evaluation worker trễ vì queue

```text
answer-api
  app.ai.answer                           1.100 ms
  evaluation.event.publish                   8 ms

message queue wait                      8.500 ms

evaluation-worker
  app.ai.evaluation.process              2.400 ms
    ├── judge.model.generate              2.050 ms
    └── evaluation.result.persist           90 ms
```

Judge chỉ mất khoảng 2 giây, nhưng thời gian từ publish tới hoàn tất job gần 11 giây. Nếu dashboard chỉ nhìn worker processing duration, sẽ bỏ qua queue lag. Theo dõi queue wait và worker throughput riêng.

### 15.4. Case D: retry amplification

Một logical tool operation chỉ hiển thị 3 attempts ở application span, nhưng HTTP access logs cho thấy 9 outbound requests. Điều đó có thể xảy ra nếu mỗi application attempt được HTTP client retry thêm 2 lần. Kiểm tra:

- SDK retry configuration.
- HTTP client retry interceptor.
- Resilience4j/Spring Retry aspect.
- Broker redelivery hoặc job runner.
- Số requests thực ở stub/provider metrics.

Không suy ra outbound request count chỉ từ số attempts của outer span.

## 16. Thuộc tính và metrics cho retry/wait/branches

### 16.1. Span attributes gợi ý

| Nhóm | Key gợi ý | Mục đích |
|---|---|---|
| Retry | `app.retry.attempt` | Attempt index |
| Retry | `app.retry.max_attempts` | Attempt limit |
| Retry | `app.retry.reason` | Failure category |
| Retry | `app.retry.delay_ms` | Delay thực/được chọn |
| Retry | `app.retry.recovered` | Có phục hồi không |
| Wait | `app.wait.kind` | queue/executor/pool/lock |
| Wait | `app.wait.duration_ms` | Duration chờ |
| Branch | `app.ai.branch.name` | Tên nhánh |
| Branch | `app.ai.branch.outcome` | success/timeout/cancelled |
| Branch | `app.ai.branch.required` | Nhánh bắt buộc hay tùy chọn |
| Operation | `app.operation.deadline_ms` | Budget tổng |
| Operation | `app.operation.remaining_ms` | Budget còn lại khi bắt đầu attempt |

Các key custom trên là ví dụ; dùng key semantic convention khi có định nghĩa chuẩn tương ứng. Không lặp lại duration vào attribute nếu span duration đã đủ, trừ khi cần ghi queue wait hoặc phần thời gian cụ thể không có span riêng.

### 16.2. Metrics nên có

| Metric | Type | Dimensions có giới hạn |
|---|---|---|
| `app.retry.attempts` | Counter | dependency, outcome, operation |
| `app.retry.recovered` | Counter | dependency, policy |
| `app.retry.exhausted` | Counter | dependency, error type |
| `app.retry.backoff` | Histogram | dependency, policy |
| `app.queue.wait` | Histogram | queue, consumer group |
| `app.executor.queue.wait` | Histogram | executor name |
| `app.pool.acquire.wait` | Histogram | pool name |
| `app.ai.branch.duration` | Histogram | operation, branch |
| `app.ai.branch.outcome` | Counter | operation, branch, outcome |
| `app.operation.deadline.exceeded` | Counter | operation |

Không thêm trace ID, message ID, case ID hoặc customer ID vào metric labels. Dùng traces/result store để tra một execution cụ thể.

### 16.3. Không đếm attempts thành logical requests

Nếu 1.000 logical model calls có 1.200 HTTP attempts:

- Logical call counter = 1.000.
- Dependency attempt counter = 1.200.
- Retry count = 200 attempts vượt lần đầu (nếu định nghĩa như vậy).
- Logical success/failure được đếm theo final outcome.

Nếu gộp tất cả thành một counter “model requests”, dashboard có thể hiểu nhầm provider nhận 1.000 calls trong khi thực tế nhận 1.200 outbound requests.

## 17. Kiểm thử trace cho retry, wait và execution branches

Không cần gọi model thật để kiểm tra phần lớn semantics của retry/tracing. Dùng fake dependency, controllable clock/sleeper, executor test và in-memory exporter/Observation handler.

### 17.1. Ma trận kiểm thử

| ID | Kịch bản | Kỳ vọng |
|---|---|---|
| `TRACE-EXEC-01` | Attempt đầu thành công | Một logical span, một attempt span |
| `TRACE-EXEC-02` | Timeout rồi retry thành công | Attempt lỗi được giữ, logical operation success |
| `TRACE-EXEC-03` | Tất cả attempts thất bại | Logical span ERROR, exhausted=true |
| `TRACE-EXEC-04` | Lỗi không retryable | Chỉ một attempt, không backoff |
| `TRACE-EXEC-05` | Retry-After dài hơn deadline | Không bắt đầu attempt mới |
| `TRACE-EXEC-06` | Caller cancel trong backoff | Không tiếp tục dependency call |
| `TRACE-EXEC-07` | SDK và app retry cùng bật | Test đếm outbound requests thật để phát hiện amplification |
| `TRACE-EXEC-08` | Queue redelivery | Invocation mới, event ID giữ nguyên |
| `TRACE-EXEC-09` | Executor queue bị nghẽn | Queue wait đo riêng với task duration |
| `TRACE-EXEC-10` | Connection pool cạn | Acquire wait khác SQL duration |
| `TRACE-EXEC-11` | Hai retrievers chạy song song | Sibling spans cùng parent |
| `TRACE-EXEC-12` | Một branch timeout | Partial/failed result đúng policy |
| `TRACE-EXEC-13` | Parent đạt quorum và cancel branch còn lại | Child ghi cancellation, không success giả |
| `TRACE-EXEC-14` | Tool có side effect và retry | Idempotency ngăn duplicate action |
| `TRACE-EXEC-15` | Metrics với 1.000 logical calls/1.200 attempts | Logical count và attempt count tách biệt |

### 17.2. Assertion cho retry spans

Với test exporter/handler, kiểm tra:

```text
logical span:
  name = app.dependency.call
  retry.max_attempts = 3
  retry.final_outcome = success

attempt spans:
  count = 3
  attempt 1 outcome = error
  attempt 2 outcome = error
  attempt 3 outcome = success

backoff spans:
  count = 2
```

Tên và attribute thực tế phải khớp naming convention của ứng dụng. Không hardcode tên spans do provider SDK tạo nếu version instrumentation chưa được khóa.

### 17.3. Assertion cho fan-out/fan-in

```text
semantic.parentSpanId == hybridRetrieve.spanId
keyword.parentSpanId == hybridRetrieve.spanId
semantic.traceId == keyword.traceId
hybridRetrieve.duration >= max(semantic.duration, keyword.duration)
```

Điều kiện duration có thể có sai số nhỏ do setup/merge và timestamps. Không assert parent duration bằng tổng child durations. Nếu có queue/executor wait trước khi child bắt đầu, đo riêng phần đó.

### 17.4. Dùng clock/sleeper giả

Backoff và deadline tests không nên ngủ thật nhiều giây. Inject `Clock` và `Sleeper`/scheduler abstraction để tiến thời gian giả lập, kiểm tra:

- Backoff tăng theo policy.
- Jitter nằm trong khoảng cho phép.
- Retry-After được tôn trọng.
- Deadline ngăn attempt tiếp theo.
- Cancellation kết thúc wait.

Không cần test framework cụ thể trong bài này; mục tiêu là làm cho thời gian và retry deterministic trong unit test.

## 18. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Một span duy nhất cho nhiều attempts | Không biết lần nào lỗi | Logical span + attempt spans |
| Chỉ ghi attempt count cuối | Mất latency/error từng attempt | Giữ child spans/events |
| Gộp backoff vào dependency duration | Đổ lỗi nhầm cho provider | Đo wait/backoff riêng |
| Mỗi tầng retry không giới hạn | Retry amplification | Một retry owner, budget/deadline tổng |
| Retry mọi exception | Lặp lỗi permanent hoặc side effect | Phân loại retryable errors |
| Không tôn trọng Retry-After | Tăng tải provider | Dùng server hint trong deadline |
| Không có jitter | Retry storm | Exponential backoff + jitter |
| Retry sau deadline | Caller đã timeout nhưng dependency vẫn bị gọi | Propagate remaining deadline |
| Cancel future nhưng không cancel dependency | Request nền vẫn chạy, tốn tài nguyên | Kiểm tra transport/driver cancellation |
| Cộng duration các nhánh song song | Latency tính lớn hơn thực tế | Dùng wall-clock/critical path |
| Không đo queue/executor wait | Nhầm scheduling delay thành dependency latency | Tách queue wait và execution |
| Gọi fallback là retry | Phân tích sai strategy/cost | Ghi fallback riêng |
| Retry tool side effect không idempotent | Duplicate transaction/action | Idempotency key và dedup |
| Nhầm broker redelivery với attempt nội bộ | Sai số lần thực thi | Ghi delivery count và attempt riêng |
| Chỉ đếm logical calls | Đánh giá thấp outbound requests | Metrics logical và dependency attempts |
| Tạo spans thủ công trùng auto-instrumentation | Trace phình và đếm đôi | Kiểm tra spans có sẵn |

## 19. Bài thực hành: điều tra một request Spring AI chậm

**Bối cảnh:** API trả lời chính sách dùng RAG hybrid (semantic + keyword), gọi ChatClient và có thể gọi tool. Model provider có retry; evaluation worker chấm fact checking bất đồng bộ qua queue. Người dùng phản ánh một số câu trả lời mất 8–12 giây.

### Phần A — Instrument logical operation

1. Tạo span `app.ai.answer` bao toàn bộ request.
2. Tạo logical spans cho `app.rag.hybrid.retrieve` và `app.ai.model.generate`.
3. Xác định HTTP/model spans do auto-instrumentation đã tạo.
4. Đặt attempt spans cho mỗi outbound request nếu client chưa tự instrument.
5. Ghi backoff, retry reason, final outcome và deadline còn lại.

### Phần B — Phân tích nhánh song song

1. Chạy semantic và keyword retrieval trên executor có giới hạn.
2. Propagate tracing context qua executor.
3. Kiểm tra hai spans là siblings cùng parent.
4. Mô phỏng keyword branch chậm hơn semantic branch.
5. Xác định critical path và quyết định all-required/first-success/best-effort.
6. Mô phỏng cancellation và xác minh child span kết thúc đúng.

### Phần C — Retry và queue

1. Mô phỏng provider timeout rồi 503 rồi thành công.
2. Xác minh số outbound requests thật, không chỉ số application attempts.
3. Mô phỏng HTTP 429 có Retry-After.
4. Mô phỏng worker redelivery và phân biệt delivery count với judge retry count.
5. Đo queue wait riêng với worker processing.
6. Thêm idempotency key cho tool side effect và evaluation result.

### Phần D — Đối chiếu quality/cost

1. So source IDs và selected chunks trong RAG result.
2. Ghi token usage của từng model turn và judge call.
3. So prompt/model/index/pipeline/rubric versions.
4. Đối chiếu fact checking/relevance verdict trong result store.
5. Không coi retry success là quality PASS; không coi judge timeout là answer FAIL.
6. Tính latency/cost theo logical operation và số dependency attempts.

### Câu hỏi tự kiểm tra

**1. Một model operation có ba HTTP attempts, hai lỗi và một thành công. Span nào nên ERROR?**  
Hai attempt spans có thể ERROR. Logical model operation và answer operation có thể thành công nếu retry phục hồi trong deadline. Metrics vẫn đếm hai dependency failures.

**2. Backoff 500 ms có nên cộng vào HTTP client span duration không?**  
Không. Backoff là thời gian chờ giữa các requests; đo riêng bằng event hoặc span để phân biệt dependency latency với retry delay.

**3. Hai retrievers chạy song song mất 400 ms và 900 ms. Parent đợi cả hai thường mất bao lâu?**  
Khoảng 900 ms cộng setup/merge overhead, không phải 1.300 ms. Nhánh 900 ms nằm trên critical path.

**4. Worker queue job mất 2 giây xử lý nhưng message chờ 10 giây. Latency end-to-end là bao nhiêu?**  
Khoảng 12 giây từ publish tới hoàn tất, nếu chỉ có một lần delivery và không có scheduled delay khác. Cần metrics queue wait và processing duration riêng.

**5. Vì sao retry cùng một tool call có thể gây duplicate side effect?**  
Server có thể đã thực hiện action nhưng response bị mất. Retry cần idempotency key/dedup để server trả lại kết quả cũ thay vì thực hiện action lần nữa.

**6. Nếu SDK và application đều retry ba lần, tối đa có bao nhiêu provider requests?**  
Có thể lên tới chín nếu hai tầng độc lập, mỗi application attempt kích hoạt ba SDK attempts. Cần đo request thực và giới hạn retry budget.

## 20. Ghi nhớ

- **Logical operation và attempt là hai cấp khác nhau**: operation đo công việc nghiệp vụ; attempt đo một lần thực thi dependency.
- **Retry trace nên giữ từng attempt và backoff** để phân biệt provider latency, client wait và final outcome.
- **Retry amplification** xuất hiện khi SDK, HTTP client, service và runner đều retry; cần một retry owner, budget và deadline tổng.
- **Exponential backoff, jitter và Retry-After** giúp giảm retry storm; không retry lỗi permanent hoặc side effect không idempotent.
- **Timeout, deadline và cancellation** phải được propagate; không bắt đầu attempt mới khi hết budget.
- **Queue wait, executor wait, connection pool wait và dependency duration** là các thành phần khác nhau, cần đo riêng.
- **Fan-out/fan-in** tạo sibling spans; latency parent thường do critical path/nhánh chậm nhất quyết định, không phải tổng child durations.
- **Partial result, fallback và cancellation** phải được ghi rõ để không giả định mọi evidence/branch đều hoàn tất.
- **Broker redelivery** là invocation mới; attempt nội bộ là lần thử trong cùng invocation. Cần event ID và idempotency key để deduplicate.
- **Metrics logical calls và dependency attempts** phải tách riêng; trace dùng để điều tra từng execution.
- **Tool side effects cần idempotency**; trace ID không phải idempotency key.
- **Trace success không phải quality PASS**: relevance, groundedness, fact checking và tool accuracy vẫn cần evaluation result riêng.

Phân tích đúng retry, chờ đợi và các nhánh thực thi biến một trace từ tổng thời gian khó giải thích thành timeline có thể quy trách nhiệm cho từng operation. Khi attempts, backoff, queue wait, pool wait, fan-out branches, cancellation và fallback được biểu diễn đúng, nhóm phát triển Spring AI có thể tìm bottleneck, giảm retry amplification, kiểm soát chi phí và xác định chính xác vì sao latency hoặc chất lượng thay đổi giữa các phiên bản prompt, model và pipeline.
