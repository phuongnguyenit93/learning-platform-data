# Đặt ngân sách đánh giá và giới hạn số công việc đồng thời

## 1. Vì sao evaluation cần budget và concurrency control?

Một evaluation run có thể gọi ứng dụng candidate hàng nghìn lần, tạo embedding, truy vấn VectorStore, gọi tool và chạy LLM-as-a-judge. Nếu chạy toàn bộ dataset với nhiều candidate cùng lúc, chi phí có thể tăng nhanh, provider có thể trả 429, queue có thể phình to và các request quan trọng của người dùng có thể bị chậm.

Ngân sách và giới hạn đồng thời giúp nhóm kiểm soát hai câu hỏi:

- **Có thể tiêu bao nhiêu để đánh giá?** Giới hạn tiền, tokens, số model calls, số judge calls, thời gian worker và tổng thời gian run.
- **Có thể chạy bao nhiêu việc cùng lúc?** Giới hạn số evaluation jobs, case attempts, model calls và tool calls đang hoạt động theo năng lực ứng dụng/provider.

Trong module SPRING_AI_EVALUATION_OBSERVABILITY, budget phải tính đến candidate execution cost và evaluation cost. Một case RAG có thể tạo nhiều model calls; một case tool calling có thể tạo tool loop; evaluator có thể gọi judge nhiều lần. Chỉ nhân số case với giá trung bình của một model call sẽ đánh giá thấp ngân sách.

Concurrency cũng không chỉ là số thread. Một evaluation job có thể fan out thành nhiều requests; mỗi request lại gọi embedding, ChatModel, VectorStore và tools. Cần giới hạn ở đúng tầng tạo tải và phối hợp các giới hạn để không vượt provider quota hoặc capacity của hệ thống.

### Kết quả học tập

Sau bài này, người học có thể:

1. Ước tính budget cho dataset, candidate, repetitions, judge và retries.
2. Phân biệt hard budget, soft budget, reservation và actual spend.
3. Đặt giới hạn theo tiền, token, model calls, tool calls và wall-clock time.
4. Thiết kế concurrency limit ở cấp run, tenant, provider, model và operation.
5. Tổ chức queue, backpressure, fairness và cancellation.
6. Xử lý rate limit, timeout, retry và partial results.
7. Dùng distributed coordination khi evaluation workers chạy trên nhiều instance.
8. Theo dõi budget utilization, queue wait, throughput, latency và quality.
9. Thiết kế bài kiểm thử để xác nhận hệ thống không vượt budget hoặc provider quota.

## 2. Phân biệt job, case, attempt và operation

Muốn đặt giới hạn đúng, trước hết phải phân biệt các cấp công việc:

| Cấp | Định nghĩa | Ví dụ |
|---|---|---|
| Evaluation run | Một lần chạy một tập dataset với một cấu hình benchmark | So sánh prompt A và B trên dataset RAG v4 |
| Candidate | Cấu hình prompt/model/retriever/tool được đánh giá | candidate-a, candidate-b |
| Evaluation case | Một tình huống dữ liệu và expected outcome | hỏi trạng thái đơn hàng |
| Attempt | Một lần thử chạy case cho candidate | lần đầu, retry sau timeout |
| Application request | Request được gửi đến candidate application | POST /api/answers |
| Model call | Một lần gọi ChatModel hoặc EmbeddingModel | planning, answer, judge |
| Tool operation | Một lần thực thi tool/API | order lookup |
| Infrastructure task | Công việc worker/queue/storage | load fixture, persist result |

Một run có 1.000 cases và 3 candidates không có nghĩa chỉ có 3.000 model calls. Mỗi attempt có thể có nhiều model calls, retrieval calls, tool calls và evaluator calls. Retry có thể làm số operation tăng thêm.

### Đặt concurrency ở đúng cấp

Ví dụ có 10 evaluation jobs, mỗi job chạy 20 cases song song, mỗi case có thể tạo 2 model calls và 1 judge call. Nếu chỉ đặt thread pool của runner là 10, hệ thống vẫn có thể tạo hàng trăm requests downstream.

Do đó, cần ít nhất:

- Run-level limit: số evaluation runs cùng hoạt động.
- Case-level limit: số case attempts đang chạy trong một run.
- Provider/model limit: số model requests đồng thời tới một provider/model.
- Tool-level limit: số tool operations đồng thời tới một dịch vụ.
- Global application limit: tổng tải mà candidate application chịu được.

Các giới hạn này cần phối hợp. Một case permit không đồng nghĩa có quyền gửi vô hạn model/tool calls.

## 3. Phân rã ngân sách evaluation

Một evaluation run có thể phát sinh các khoản:

| Nhóm | Hoạt động |
|---|---|
| Candidate generation | ChatModel calls của candidate, gồm tool loop và retries |
| Query embedding | Embedding câu hỏi hoặc sub-questions |
| Retrieval | Vector DB query/read, metadata fetch, search |
| Reranking | Reranker model hoặc compute |
| Tool execution | API, database, compute và dịch vụ ngoài |
| Evaluation | Judge, fact checker, semantic evaluator, adjudication |
| Data processing | Dataset loading, parsing, transformation |
| Infrastructure | Worker CPU/RAM/GPU, queue, storage, network |
| Observability | Trace/log/metric ingest, retention và query |

Phải công bố budget scope:

- Candidate budget: chỉ chi phí chạy candidate.
- Evaluator budget: chi phí đo chất lượng.
- Run budget: candidate + evaluator + overhead được chọn.
- Fully allocated budget: run cost + shared infrastructure/observability allocation.

Không cộng evaluator cost vào candidate A nhưng bỏ khỏi candidate B. Nếu evaluator chạy sau mỗi candidate, hãy tính riêng và cộng vào run total theo cùng quy tắc.

### Công thức tổng quan

\[
B_{\mathrm{run}} =
B_{\mathrm{candidate}} +
B_{\mathrm{evaluation}} +
B_{\mathrm{shared}}
\]

Trong đó:

\[
B_{\mathrm{candidate}} =
B_{\mathrm{generation}} +
B_{\mathrm{embedding}} +
B_{\mathrm{retrieval}} +
B_{\mathrm{tools}}
\]

\[
B_{\mathrm{evaluation}} =
B_{\mathrm{judge}} +
B_{\mathrm{factcheck}} +
B_{\mathrm{evaluation\ compute}}
\]

Đây là mô hình ngân sách. Khi tính tiền thực tế, dùng usage events và price catalog có version; không thay cost ledger bằng công thức ước lượng.

## 4. Ước tính số operation trước khi chạy

Giả sử:

- N là số evaluation cases.
- K là số candidates.
- R là số repetitions mỗi case/candidate.
- A là số attempts tối đa cho mỗi attempt logic (bao gồm retry theo policy).
- M là số model calls trung bình trên một attempt.
- J là số judge calls trung bình trên một case/candidate.

Ước tính upper bound:

\[
N_{\mathrm{candidate\ attempts}} = N \times K \times R \times A
\]

\[
N_{\mathrm{model\ calls}} \approx
N \times K \times R \times A \times M
\]

\[
N_{\mathrm{judge\ calls}} \approx N \times K \times R \times J
\]

Đây chỉ là planning estimate. Một số judge có thể chạy lại theo attempt; nếu vậy, nhân judge calls với A. Tool loops và retrieval fan-out cũng cần ước tính riêng.

### Ví dụ

Một benchmark có:

- 500 cases.
- 2 candidates.
- 1 repetition.
- Trung bình 2 model calls cho mỗi candidate attempt.
- 1 judge call cho mỗi case/candidate.
- Tối đa 2 attempts nếu retry.

Upper bound đơn giản:

- Candidate attempts: 500 × 2 × 2 = 2.000.
- Candidate model calls: 2.000 × 2 = 4.000.
- Judge calls: 500 × 2 = 1.000 nếu judge chỉ chạy sau kết quả cuối.

Nếu judge được chạy lại cho mỗi attempt, upper bound judge calls thành 2.000. Ghi rõ giả định này trong experiment manifest.

## 5. Ước tính chi phí từ pilot run

Không nên dùng một average duy nhất cho mọi loại case. Hãy chọn pilot đại diện:

- Simple answer không RAG/tool.
- RAG có ít và nhiều chunks.
- Tool workflow một vòng và nhiều vòng.
- Long-context.
- Case có retry/failure.
- High-risk cần nhiều evaluator checks.

Với mỗi cohort, đo:

- Cost per candidate attempt.
- Input/output/cached tokens.
- Model calls per attempt.
- Embedding/retrieval/tool usage.
- Judge calls và judge tokens.
- p50/p90/p95 cost và latency.
- Failure/retry rate.

### Ước tính theo cohort

\[
B_{\mathrm{pilot}} =
\sum_{c=1}^{n}
N_c \times \widehat{C}_c
\]

Trong đó N_c là số case dự kiến của cohort c, còn Ĉ_c là cost ước tính mỗi case từ pilot. Có thể dùng p90/p95 cost thay average cho hard budget để dự phòng case đắt bất thường.

### Buffer không thay thế hard cap

Thêm buffer cho usage variance, retries và provider pricing uncertainty. Ví dụ dự trù 20% không có nghĩa hệ thống được phép chi vượt budget đã được phê duyệt. Hard cap vẫn phải được enforce trước khi phát sinh thêm operation.

## 6. Đặt nhiều loại budget

Một run nên có các giới hạn độc lập:

| Budget | Giới hạn | Mục đích |
|---|---|---|
| Monetary budget | USD hoặc currency khác | Không vượt khoản chi được duyệt |
| Input token budget | Tổng input tokens | Kiểm soát context và prompt |
| Output token budget | Tổng output tokens | Tránh generation dài |
| Model call budget | Số model calls | Giới hạn planner/tool loop/retry |
| Tool call budget | Số tool operations | Tránh tool loop và API cost |
| Embedding budget | Token/items/requests | Kiểm soát query và document embedding |
| Case budget | Số cases/attempts | Giới hạn quy mô run |
| Time budget | Deadline/wall-clock | Tránh run kéo dài vô hạn |
| Concurrency budget | Số operation đang chạy | Bảo vệ capacity |

Không dùng monetary budget thay thế các limit khác. Một tool call có thể rẻ nhưng gây side effect; một model call có thể rẻ nhưng chiếm provider quota; một task có thể dùng ít tiền nhưng chạy quá lâu.

### Hard limit và soft threshold

- Soft threshold: cảnh báo, giảm tốc độ hoặc yêu cầu xác nhận theo policy.
- Hard limit: từ chối cấp reservation mới khi budget không còn.
- Emergency stop: dừng run khi phát hiện cost spike, runaway loop hoặc provider incident.

Soft threshold không tự động cho phép vượt hard limit. Mỗi loại budget cần định nghĩa hành động cụ thể khi chạm ngưỡng.

## 7. Reservation trước khi chạy và actual cost sau khi chạy

Nếu chỉ kiểm tra actual cost sau mỗi request, nhiều worker đồng thời có thể cùng nhìn thấy budget còn đủ và cùng gửi operation vượt quá số dư.

Dùng cơ chế reservation:

1. Ước tính cost/usage tối đa cho batch hoặc case.
2. Atomically reserve phần budget đó trước khi dispatch.
3. Worker thực hiện operation trong reservation.
4. Ghi actual usage/cost khi có kết quả.
5. Release phần reservation không dùng.
6. Nếu actual lớn hơn reservation, ghi variance và kiểm tra hard cap trước operation tiếp theo.

### Công thức ngân sách khả dụng

\[
B_{\mathrm{available}} =
B_{\mathrm{limit}} -
B_{\mathrm{actual}} -
B_{\mathrm{reserved}}
\]

Chỉ cấp thêm reservation nếu available budget đủ theo policy.

### Không double count reservation

Reservation là khoản giữ chỗ, không phải actual cost. Khi settle:

- Trừ reservation tương ứng.
- Cộng actual cost vào ledger.
- Release phần chênh chưa dùng.
- Nếu thiếu usage, giữ trạng thái pending/estimated và reconcile sau.

Không cộng reservation vào invoice total.

## 8. Budget ở cấp run, tenant và toàn hệ thống

Budget thường có nhiều scope lồng nhau:

| Scope | Ví dụ giới hạn |
|---|---|
| Organization/global | Tổng chi evaluation mỗi ngày/tháng |
| Tenant/project | Ngân sách cho một khách hàng hoặc team |
| Evaluation run | Max cost/tokens/cases/time |
| Candidate | Max model calls hoặc cost cho một candidate |
| Case | Max cost/calls/tool rounds cho một case |
| Operation | Max tokens cho một model call hoặc max units cho một tool |

Một operation chỉ được chạy nếu mọi scope liên quan còn budget. Ví dụ run còn 10 USD nhưng tenant đã hết monthly quota thì không được dispatch.

### Quy tắc trừ budget

Với một operation, kiểm tra và reserve theo thứ tự xác định trong một transaction/atomic coordinator:

1. Global.
2. Tenant/project.
3. Run.
4. Candidate.
5. Case.
6. Operation-specific.

Thứ tự cụ thể có thể khác, nhưng việc kiểm tra và reserve các scope phải atomic hoặc có rollback rõ ràng. Không reserve global thành công rồi để tenant reservation thất bại mà không release global reservation.

## 9. Đặt giới hạn model calls và tool rounds

Model có thể yêu cầu tool liên tiếp hoặc lặp lại một tool. Cần giới hạn:

- Max model calls per case attempt.
- Max tool rounds per request.
- Max calls per tool name.
- Max total tool calls per case.
- Max total tokens per case.
- Max elapsed time per case.

Ví dụ policy:

~~~yaml
evaluationLimits:
  case:
    maxModelCalls: 5
    maxToolCalls: 4
    maxToolRounds: 3
    maxInputTokens: 16000
    maxOutputTokens: 2000
    maxDurationSeconds: 45
  run:
    maxCases: 1000
    maxAttemptsPerCase: 2
    maxJudgeCallsPerCase: 2
    maxDurationMinutes: 90
~~~

Đây là cấu hình ứng dụng minh họa, không phải property chuẩn Spring AI. Giá trị phải dựa trên task risk, provider limits và budget thực tế.

### Khi chạm giới hạn

- Dừng tạo model/tool operations mới.
- Persist trạng thái budget_exceeded hoặc limit_reached.
- Giữ partial result nếu đã có dữ liệu hữu ích.
- Không tự retry để vượt qua hard limit.
- Ghi operation cuối cùng và lý do dừng.

Nếu giới hạn được chạm trong một tool loop, không gửi model call follow-up chỉ để hỏi model có muốn dừng hay không. Runner phải áp dụng policy ngay tại application boundary.

## 10. Concurrency là nhiều giới hạn phối hợp

Concurrency là số operation đang hoạt động tại cùng thời điểm. Không đồng nhất:

- Số worker threads.
- Số evaluation cases đang chạy.
- Số HTTP requests đang in-flight.
- Số model calls đang in-flight.
- Số requests provider chấp nhận đồng thời.

Một thread có thể tạo nhiều asynchronous requests. Một case có thể chạy parallel retrieval và tool calls. Vì vậy, thread pool size không đủ để bảo vệ downstream.

### Các lớp giới hạn

| Lớp | Ví dụ |
|---|---|
| Global run scheduler | Tối đa 3 evaluation runs |
| Worker pool | Tối đa 12 case workers |
| Candidate application | Tối đa 8 requests đồng thời |
| Provider account | Tối đa 6 model calls in-flight |
| Model deployment | Tối đa 4 calls tới model X |
| Embedding provider | Tối đa 2 embedding batches |
| Tool service | Tối đa 3 inventory lookups |
| Database | Connection pool và query concurrency |

Giới hạn nên phản ánh capacity thật và quota hợp đồng. Nếu provider không công bố concurrency quota, bắt đầu conservative, quan sát 429/latency và tăng dần qua load test.

## 11. Phân biệt concurrency limit với rate limit

Hai cơ chế giải quyết hai loại quá tải khác nhau:

- **Concurrency limit** giới hạn số requests đang xử lý cùng lúc.
- **Rate limit** giới hạn số requests/tokens được gửi trong một khoảng thời gian.

Một provider có thể cho phép 10 requests đồng thời nhưng chỉ 60 requests mỗi phút và 100.000 tokens mỗi phút. Chỉ đặt concurrency 10 vẫn có thể vượt RPM/TPM nếu response nhanh.

### Các quota phổ biến

| Quota | Đơn vị |
|---|---|
| RPM | Requests per minute |
| RPS | Requests per second |
| TPM | Tokens per minute |
| Input TPM | Input tokens per minute |
| Output TPM | Output tokens per minute |
| Concurrent requests | Requests in-flight |
| Daily/monthly quota | Requests, tokens hoặc spend theo kỳ |

Nếu provider tính token quota theo estimated maximum output tokens ở thời điểm request, rate limiter phải reserve theo mức tối đa được phép hoặc theo policy an toàn. Sau response, reconcile reservation với usage thực tế.

## 12. Token-aware rate limiting

Rate limiter chỉ đếm request có thể không bảo vệ được TPM. Một request prompt 15.000 tokens khác request 200 tokens.

Một cách tiếp cận:

1. Ước tính input tokens trước khi gửi.
2. Reserve input tokens và output token allowance theo quota policy.
3. Kiểm tra cả RPM và TPM.
4. Dispatch khi cả hai quota đủ.
5. Sau response, settle bằng usage thực tế.
6. Release phần output allowance không dùng.

Nếu không có tokenizer chính xác cho provider/model, dùng estimate bảo thủ và ghi rõ. Không coi character count là token count chính xác.

### Token bucket

Token bucket cho phép tích lũy capacity đến một burst limit:

- Bucket có capacity tối đa.
- Token được refill theo thời gian.
- Mỗi request tiêu thụ một số token tương ứng.
- Nếu không đủ token, request chờ hoặc bị reject.

Có thể dùng một bucket cho RPM và một bucket cho TPM. Hai bucket phải cùng được kiểm tra trước khi dispatch.

### Leaky bucket và fixed window

Leaky bucket phát request với tốc độ đều hơn, phù hợp làm phẳng burst. Fixed window dễ triển khai nhưng có thể tạo burst ở ranh giới hai cửa sổ. Sliding window hoặc token bucket thường kiểm soát tốt hơn khi quota provider nghiêm ngặt.

## 13. Queue, backpressure và admission control

Không dispatch tất cả cases ngay lập tức. Dùng queue có giới hạn và chỉ nhận thêm việc khi có capacity.

~~~mermaid
flowchart TD
    A["Evaluation run request"] --> B["Budget admission"]
    B -->|Budget denied| X["Reject / wait for approval"]
    B -->|Accepted| Q["Bounded job queue"]
    Q --> W["Worker pool"]
    W --> C["Case concurrency gate"]
    C --> P["Provider/model rate and concurrency gates"]
    P --> R["Run candidate + evaluator"]
    R --> S["Persist usage, cost and result"]
    S --> T["Release permits and settle budget"]
    T --> Q
    R -->|429 / overload| D["Backoff / reschedule"]
    D --> Q
~~~

### Bounded queue

Queue cần có:

- Max pending jobs/cases.
- Max queue wait time.
- Admission policy khi queue đầy.
- Priority hoặc fairness giữa tenants/runs.
- Cancellation và expiry.
- Dead-letter/review path cho job lỗi không thể retry.

Queue không giới hạn có thể biến overload ngắn thành backlog kéo dài, chiếm storage và làm người dùng chờ không xác định.

### Backpressure

Khi downstream chậm hoặc provider trả 429:

- Giảm dispatch rate.
- Tạm dừng nhận batch mới.
- Giữ pending jobs trong queue có giới hạn.
- Trả trạng thái queued/paused cho caller.
- Không tạo thêm retry song song cho cùng operation.

Backpressure nên truyền từ provider gate về scheduler để toàn hệ thống giảm tốc, thay vì từng worker tự retry và tạo thêm tải.

## 14. Chọn concurrency từ capacity và latency

Một ước lượng đơn giản dùng Little's Law:

\[
L = \lambda W
\]

Trong đó:

- L là số requests trung bình đang in-flight.
- λ là throughput (requests/second).
- W là thời gian xử lý trung bình (seconds).

Ví dụ, nếu mục tiêu 2 requests/second và thời gian xử lý trung bình 3 seconds:

\[
L = 2 \times 3 = 6
\]

Trung bình cần khoảng 6 requests in-flight để đạt throughput đó, chưa tính burst, tail latency, retries và giới hạn provider.

Đây là quan hệ trung bình, không phải giá trị concurrency an toàn tối đa. Hãy load test và theo dõi queueing, p95/p99, error rate, memory và provider throttling.

### Tăng dần concurrency

1. Bắt đầu với concurrency thấp.
2. Chạy workload đại diện.
3. Tăng từng bước nhỏ.
4. Theo dõi throughput, p95/p99, 429/5xx, queue wait và resource saturation.
5. Dừng tăng khi throughput không cải thiện hoặc latency/error tăng nhanh.
6. Chọn operating point có headroom cho production traffic.

Không chọn concurrency chỉ vì benchmark đạt throughput cao nhất. Một mức gần saturation có thể rất nhạy với burst và provider incidents.

## 15. Phân bổ concurrency công bằng giữa runs và tenants

Một evaluation run lớn có thể chiếm hết worker pool và provider quota, khiến run nhỏ hoặc tenant khác phải chờ.

Các policy thường dùng:

- FIFO: đơn giản, nhưng job dài có thể chặn job ngắn.
- Weighted fair queue: phân chia capacity theo trọng số tenant/team.
- Per-tenant cap: một tenant không chiếm toàn bộ concurrency.
- Priority queue: production regression hoặc release gate được ưu tiên.
- Deficit round robin: phân bổ lượt chạy công bằng theo cost/work units.

### Tránh starvation

Nếu job priority thấp luôn bị đẩy xuống, nó có thể không bao giờ chạy. Có thể dùng aging: tăng priority theo thời gian chờ, hoặc dành một phần capacity cho background jobs.

Priority không được bỏ qua hard budget, authorization hoặc provider quota. Một run release-critical có thể được ưu tiên queue, nhưng vẫn phải reserve budget và lấy permit hợp lệ.

## 16. Giới hạn riêng cho model, embedding, tool và judge

Không phải downstream nào cũng có cùng capacity:

| Operation | Vì sao cần gate riêng |
|---|---|
| ChatModel | RPM/TPM, concurrent requests, context/output limit |
| EmbeddingModel | Batch size, input TPM, request quota |
| VectorStore | Query concurrency, connection pool, read/write capacity |
| Reranker | Pair count, token limit, model-specific quota |
| Tool/API | Service-specific rate limit, side effects, timeout |
| Judge model | Quota riêng, cost budget riêng, có thể dùng model khác |
| Dataset store | Read throughput và connection pool |
| Result store | Write throughput, transaction contention |

Nếu candidate và judge dùng cùng provider account, chúng có thể tranh quota. Có thể dành quota riêng cho judge hoặc ưu tiên candidate execution, tùy mục tiêu benchmark. Ghi rõ policy vì nó ảnh hưởng latency và throughput đo được.

### Không tạo deadlock giữa các semaphore

Nếu một request giữ permit provider A rồi chờ provider B, trong khi request khác giữ B rồi chờ A, hệ thống có thể deadlock. Tránh giữ nhiều permit trong thời gian dài; acquire theo thứ tự toàn cục cố định hoặc chỉ giữ permit ngay quanh operation tương ứng.
## 17. Xử lý 429, retry và Retry-After

HTTP 429 thường báo rate limit hoặc quota đã chạm. Một số provider trả Retry-After hoặc reset headers. Scheduler cần dùng thông tin đó để trì hoãn dispatch, không để mọi worker retry cùng lúc.

Quy trình:

1. Phân loại lỗi: 429/rate limit, 5xx/transient, timeout, validation hay authorization.
2. Nếu có Retry-After, tôn trọng khoảng chờ provider yêu cầu.
3. Nếu không có, dùng exponential backoff với jitter.
4. Áp dụng max attempts và deadline tổng.
5. Giữ reservation budget trong thời gian retry theo policy; không reserve mới trùng operation.
6. Ghi mỗi attempt và provider request ID riêng.
7. Nếu hết retry budget, đánh dấu case failed/retry_exhausted.

### Exponential backoff và jitter

\[
d_n = \min(d_{\max}, d_0 \times 2^n) + J_n
\]

Trong đó d0 là delay ban đầu, dmax là giới hạn, Jn là jitter ngẫu nhiên trong phạm vi policy. Jitter giúp nhiều worker không đồng loạt retry tại cùng một thời điểm.

Không retry:

- Lỗi validation/schema không thay đổi.
- 401/403 hoặc authorization failure.
- Hard budget exceeded.
- Tool write operation không có idempotency protection.
- Lỗi permanent được provider xác định rõ.

### Retry có thể làm vượt budget

Một request timeout có thể đã được provider tính phí. Trước khi retry, tính cả khả năng attempt trước đã phát sinh usage. Nếu usage chưa rõ, đánh dấu pending/unknown và áp retry policy bảo thủ. Không coi timeout là cost bằng 0.

## 18. Cancellation và dừng run an toàn

Evaluation run có thể bị hủy bởi người dùng, budget guard, provider incident hoặc deadline. Cancellation cần được truyền qua scheduler, queue, worker và operation.

Khi cancel:

1. Đánh dấu run là cancel_requested.
2. Không dispatch case mới.
3. Hủy job còn pending.
4. Yêu cầu worker đang chạy dừng ở safe boundary.
5. Cancel HTTP/model/tool request nếu client hỗ trợ.
6. Không bắt đầu model follow-up hoặc tool call mới.
7. Persist partial results và usage đã biết.
8. Settle/release reservation theo actual usage.
9. Đóng run với trạng thái cancelled hoặc partially_completed.

### Không giả định cancel đồng nghĩa provider ngừng tính phí

Client cancel có thể chỉ đóng kết nối; provider có thể tiếp tục xử lý. Ghi cancellation timestamp và provider request ID, sau đó reconcile usage/billing nếu cần.

### Safe boundary

Với operation read-only, có thể dừng ngay khi cancellation được nhận. Với operation có side effect, phải kiểm tra trạng thái thực thi và idempotency trước khi retry hoặc báo thất bại. Không gửi lệnh ghi trùng chỉ vì worker không nhận được response.

## 19. Job state machine và idempotency

Một job có thể bị worker restart, lease timeout hoặc message delivery lặp. State machine giúp đảm bảo một case không bị tính kết quả/cost hai lần.

~~~mermaid
stateDiagram-v2
    [*] --> Queued
    Queued --> Reserved
    Reserved --> Running
    Running --> Succeeded
    Running --> Failed
    Running --> RetryWaiting
    RetryWaiting --> Reserved
    Queued --> Cancelled
    Reserved --> Cancelled
    Running --> CancelRequested
    CancelRequested --> Cancelled
    Succeeded --> Settled
    Failed --> Settled
    Cancelled --> Settled
~~~

Các transition cần có điều kiện:

- Queued → Reserved chỉ khi budget và concurrency permits đã được cấp.
- Reserved → Running chỉ khi worker nhận lease hợp lệ.
- Running → RetryWaiting chỉ với lỗi transient và còn retry budget.
- Running → CancelRequested khi run bị dừng.
- Terminal state → Settled sau khi usage/cost đã ghi hoặc được đánh dấu pending.

### Idempotency keys

Tạo key ổn định cho logical case attempt, ví dụ gồm run ID, candidate ID, case ID và attempt number. Mỗi external provider call có call ID riêng. Persist result theo unique key để redelivery không tạo duplicate evaluation result.

Nếu provider call đã được gửi nhưng worker crash trước khi ghi response, trạng thái operation cần là unknown/pending reconciliation. Không tự gửi lại ngay nếu tool có side effect hoặc provider có thể đã tính phí.

## 20. Nhiều worker instance cần distributed coordination

Một Semaphore trong JVM chỉ giới hạn concurrency của một process. Nếu có bốn worker instances và mỗi instance cho phép 5 model calls, tổng cộng có thể có 20 calls.

Để áp quota toàn cụm, cần coordinator dùng chung:

- Database row/transaction với atomic counter.
- Redis semaphore/token bucket có atomic script.
- Distributed rate limiter.
- Queue consumer concurrency được quản lý tập trung.
- Provider gateway quản lý quota tập trung.

### Distributed permit cần lease

Một worker có thể crash khi đang giữ permit. Nếu permit không tự hết hạn, capacity sẽ bị khóa vĩnh viễn.

Lease nên có:

- Permit ID và owner worker ID.
- AcquiredAt và expiresAt.
- TTL/heartbeat policy.
- Release idempotent.
- Recovery khi worker chết.
- Fencing token hoặc generation để worker cũ không tiếp tục thao tác sau khi lease đã được cấp lại.

Không chỉ dựa vào timeout để thu hồi permit nếu operation có side effect. Cần fencing/idempotency để tránh hai worker cùng thực hiện một logical job.

### Phân biệt local và global cap

Có thể giữ local semaphore để giảm contention và global distributed permit để bảo vệ provider account. Local cap không thay thế global cap.

## 21. Ví dụ Java: giới hạn operation bằng Semaphore

Ví dụ dưới đây minh họa local concurrency gate quanh một operation. Trong production nhiều instance, cần distributed limiter nếu quota là quota toàn provider account.

~~~java
import java.time.Duration;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class ProviderGate {

    private final Semaphore permits;

    public ProviderGate(int maxConcurrentCalls) {
        this.permits = new Semaphore(maxConcurrentCalls);
    }

    public <T> T execute(
            Duration waitTimeout,
            CheckedSupplier<T> operation) throws Exception {

        boolean acquired = permits.tryAcquire(
                waitTimeout.toMillis(), TimeUnit.MILLISECONDS);

        if (!acquired) {
            throw new IllegalStateException("provider concurrency limit reached");
        }

        try {
            return operation.get();
        } finally {
            permits.release();
        }
    }

    @FunctionalInterface
    public interface CheckedSupplier<T> {
        T get() throws Exception;
    }
}
~~~

Gate chỉ giữ permit trong lúc operation thực sự chạy. Không giữ permit khi worker đang sleep để backoff hoặc chờ người dùng. Nếu client async, permit phải được release khi future hoàn tất, thất bại hoặc bị cancel; không release ngay khi method trả về một future chưa hoàn tất.

## 22. Ví dụ cấu hình scheduler và worker pool

Một runner có thể dùng bounded executor để giới hạn số case workers trong một instance:

~~~java
import java.util.concurrent.Executor;
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class EvaluationWorkerConfiguration {

    @Bean
    Executor evaluationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("evaluation-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();
        return executor;
    }
}
~~~

Ví dụ minh họa local worker pool, không phải cấu hình quota provider hoàn chỉnh. Queue capacity hữu hạn và rejection policy giúp scheduler biết hệ thống đang đầy. Caller cần xử lý rejection thành queued/rejected theo admission policy; không bỏ job hoặc tạo queue không giới hạn.

Spring Boot/Spring Framework version có thể ảnh hưởng API và lifecycle. Trong ứng dụng thực tế, cân nhắc cấu hình executor qua properties và graceful shutdown. Không tạo một thread pool mới cho mỗi evaluation run.
## 23. Reservation nguyên tử cho nhiều scope

Một request có thể cần đồng thời reservation ở global, tenant, run và provider. Nếu từng worker đọc số dư rồi cập nhật riêng, race condition có thể làm tổng reservation vượt limit.

Ví dụ sai:

1. Worker A đọc available budget = 1 USD.
2. Worker B cũng đọc available budget = 1 USD.
3. A reserve 0,80 USD.
4. B reserve 0,80 USD dựa trên số dư cũ.
5. Tổng reservation thành 1,60 USD dù limit chỉ 1 USD.

### Cách thực hiện an toàn

- Dùng transaction với row lock hoặc atomic conditional update.
- Hoặc dùng distributed atomic script/transaction trong coordinator.
- Reserve tất cả scopes theo một thao tác logic.
- Nếu một scope thất bại, rollback/release các scope đã reserve.
- Ghi reservation ID duy nhất để release/settle idempotent.

Pseudocode:

~~~text
reserve(request):
  begin atomic transaction
  lock global budget
  lock tenant budget
  lock run budget
  lock provider quota

  if any scope lacks available capacity:
    rollback
    return DENIED

  create reservation with unique reservationId
  increment reserved amount in all scopes
  commit
  return reservationId

settle(reservationId, actualUsage):
  begin atomic transaction
  load reservation and verify not already settled
  decrement reserved amounts
  increment actual usage/cost
  release unused capacity
  mark reservation settled
  commit
~~~

Đây là pseudocode, không phải implementation database cụ thể. Chọn isolation/locking phù hợp với database và throughput. Cần xử lý transaction retry, deadlock và coordinator outage.

## 24. Budget policy và manifest của evaluation run

Budget policy nên được version hóa để có thể giải thích vì sao một run bị từ chối, dừng hoặc chạy với concurrency cụ thể.

~~~yaml
evaluationBudget:
  policyVersion: evaluation-budget-v3
  currency: USD
  run:
    maxEstimatedCost: 25.00
    maxActualCost: 25.00
    maxCases: 1000
    maxAttemptsPerCase: 2
    maxWallClockMinutes: 90
  usage:
    maxModelCalls: 5000
    maxJudgeCalls: 2000
    maxToolCalls: 1500
    maxInputTokens: 12000000
    maxOutputTokens: 2000000
  concurrency:
    maxRuns: 3
    maxCaseWorkersPerRun: 8
    maxProviderCalls: 6
    maxEmbeddingCalls: 2
    maxToolCallsInFlight: 3
  thresholds:
    warnAtPercent: 75
    pauseAtPercent: 90
    stopAtPercent: 100
~~~

Đây là ví dụ cấu hình nội bộ, không phải property chuẩn Spring AI. Max estimated cost là admission estimate; max actual cost là hard spend ceiling. Khi reservation không còn đủ, scheduler phải pause/stop trước khi gửi operation mới.

### Ghi policy vào run manifest

Khi run được tạo, snapshot:

- Budget policy version.
- Price catalog version.
- Dataset/rubric/evaluator versions.
- Candidate configuration versions.
- Concurrency/rate limit settings.
- Retry, timeout và cancellation policy.
- Estimated budget và reservation ID.

Không chỉ lưu giá trị hiện tại trong config server; run lịch sử cần biết chính sách nào đã áp dụng.

## 25. Theo dõi budget utilization và concurrency

Một dashboard vận hành cần thể hiện cả tiền, usage, queue và năng lực:

| Nhóm | Chỉ số |
|---|---|
| Budget | Limit, reserved, actual, available |
| Usage | Model calls, input/output tokens, tool calls, embedding units |
| Concurrency | In-flight case attempts, model calls, tool calls |
| Queue | Pending jobs, oldest job age, queue wait p50/p95 |
| Throughput | Cases/minute, model calls/second, tokens/second |
| Reliability | 429, 5xx, timeout, retry, cancellation |
| Cost | Estimate, actual/settled, cost per case, cost per success |
| Quality | Cases completed, hard-gate failures, score distribution |

### Metric names gợi ý

Đây là tên metric do ứng dụng tự thiết kế:

- ai_evaluation_budget_limit_usd
- ai_evaluation_budget_reserved_usd
- ai_evaluation_budget_actual_usd
- ai_evaluation_budget_available_usd
- ai_evaluation_jobs_queued
- ai_evaluation_jobs_running
- ai_evaluation_case_attempts_in_flight
- ai_provider_requests_in_flight
- ai_provider_rate_limit_events_total
- ai_evaluation_queue_wait_seconds
- ai_evaluation_cases_completed_total
- ai_evaluation_budget_stop_total

Gauge phù hợp với current in-flight/available values; counter phù hợp với event counts; histogram phù hợp với queue wait/duration. Không đặt requestId, caseId, runId hoặc userId vào labels có cardinality cao.

### Cảnh báo

- Budget utilization vượt soft threshold.
- Available budget thấp nhưng queue còn nhiều jobs.
- Provider 429 tăng liên tục.
- Queue wait p95 vượt ngưỡng.
- In-flight count cao nhưng throughput không tăng.
- Reservation hết hạn chưa được release.
- Run không tiến triển trong thời gian dài.
- Actual cost tăng nhanh hơn estimate.

## 26. Fairness và bảo vệ traffic production

Evaluation workload thường là background traffic. Không để nó chiếm hết quota hoặc thread pool mà production requests cần.

Các biện pháp:

- Dùng executor/queue riêng cho evaluation.
- Dành quota provider riêng hoặc giới hạn evaluation share.
- Đặt per-tenant/per-run cap.
- Giới hạn tổng outbound calls từ evaluation workers.
- Ưu tiên production traffic tại shared gateway nếu dùng chung provider account.
- Pause evaluation khi production latency/error vượt ngưỡng.
- Chạy batch evaluation ngoài peak hours nếu phù hợp.

### Isolation ở cấp hạ tầng

Nếu candidate application dùng chung database, vector store hoặc tool services với production, concurrency cap ở runner chưa đủ. Cân nhắc:

- Dedicated test tenant/index.
- Read-only fixtures hoặc mock tools.
- Separate connection pool.
- Dedicated worker deployment.
- Quota và namespace riêng.
- Synthetic data thay dữ liệu thật khi không cần production data.

Không để test tool có side effect ghi đơn hàng, gửi email hoặc thay đổi trạng thái khách hàng. Dùng mock/sandbox có kiểm soát cho evaluation.

## 27. Runbook khi budget hoặc concurrency chạm ngưỡng

### Khi budget đạt soft threshold

1. Hiển thị budget remaining và forecast.
2. Kiểm tra cost/case theo cohort.
3. Giảm tốc độ dispatch nếu forecast cho thấy có thể vượt hard cap.
4. Giữ ưu tiên cho cases cần thiết để hoàn thành release gate.
5. Ghi cảnh báo và owner.

### Khi budget đạt hard limit

1. Ngừng reservation mới.
2. Không dispatch model/tool calls mới.
3. Cho operation đang chạy hoàn tất hoặc cancel theo policy.
4. Persist partial results và usage.
5. Release reservation chưa dùng.
6. Đánh dấu run budget_exceeded.
7. Chỉ tiếp tục khi có budget mới được phê duyệt hoặc scope được điều chỉnh.

### Khi provider trả 429 liên tục

1. Đọc Retry-After/reset headers.
2. Giảm concurrency/rate ở provider gate.
3. Tạm dừng batch mới.
4. Backoff có jitter cho operation retryable.
5. Kiểm tra RPM/TPM và usage reservations.
6. Xác nhận traffic production không bị ảnh hưởng.
7. Resume theo ramp-up chậm sau khi quota phục hồi.

### Khi queue tăng nhưng throughput không tăng

- Kiểm tra provider throttling/latency.
- Kiểm tra worker saturation và database connection pool.
- Kiểm tra semaphore permit bị leak.
- Kiểm tra job stuck/lease expired.
- Kiểm tra retry storm hoặc dependency outage.
- Giảm admission rate và xử lý backlog theo priority/fairness.

## 28. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Chỉ giới hạn thread pool | Async fan-out vẫn tạo nhiều downstream calls | Gate từng provider/tool operation |
| Chỉ giới hạn concurrency | RPM/TPM vẫn có thể bị vượt | Dùng rate limiter song song |
| Chỉ kiểm tra actual cost sau run | Nhiều worker có thể cùng vượt budget | Reservation nguyên tử |
| Reservation bị tính là actual | Double count cost | Tách reserved và settled |
| Mỗi JVM tự giữ semaphore | Tổng cluster concurrency vượt quota | Distributed coordinator |
| Retry mọi lỗi | Tăng cost và gây retry storm | Phân loại lỗi, max attempts, backoff/jitter |
| Timeout được xem là miễn phí | Underestimate provider spend | Pending usage và reconciliation |
| Queue không giới hạn | Backlog kéo dài, memory/storage tăng | Bounded queue và admission control |
| Một run chiếm toàn bộ worker | Tenant khác bị starvation | Fair scheduling/per-tenant cap |
| Hủy client rồi nghĩ provider dừng | Provider vẫn có thể tính phí | Reconcile request ID và usage |
| Release permit ngay khi async method trả future | Permit không phản ánh operation in-flight | Release khi future complete/cancel |
| Đếm case thay vì operation | Không thấy model/tool fan-out | Theo dõi cả cấp case và operation |

## 29. Bài thực hành: chạy evaluation dưới budget và quota

Chuẩn bị:

- Dataset 200 cases gồm simple, RAG, tool và long-context.
- Hai candidates dùng cùng evaluation rubric.
- Candidate có ChatModel, EmbeddingModel, VectorStore và một tool read-only fixture.
- Cost ledger ghi từng model/tool/embedding operation.
- Provider test double có thể trả 429, timeout và delay.
- Evaluation runner có bounded queue và configurable concurrency.

Thực hiện:

1. Pilot 20 cases và đo cost/usage theo cohort.
2. Ước tính upper bound model calls, judge calls, tokens và tool calls.
3. Đặt run monetary budget, token budget, call budget và deadline.
4. Đặt run-level và case-level concurrency.
5. Đặt provider/model RPM, TPM và in-flight limits.
6. Chạy benchmark ở concurrency thấp, sau đó tăng từng bước.
7. Ghi throughput, queue wait, p95 latency và 429 rate.
8. Inject 429 với Retry-After và xác nhận scheduler backoff.
9. Inject timeout rồi xác nhận usage pending được reconcile.
10. Chạm soft budget threshold và xác nhận cảnh báo/slowdown.
11. Chạm hard budget cap và xác nhận không dispatch operation mới.
12. Cancel run và xác nhận pending jobs bị hủy, partial results được lưu.
13. Chạy hai worker instances và xác nhận global concurrency không vượt cap.
14. Import cùng job/event lần hai và xác nhận idempotency.
15. Kiểm tra reservation được settle/release đúng, không double count.

### Kết quả cần ghi

| Chỉ số | Trước giới hạn | Sau giới hạn |
|---|---:|---:|
| Max provider calls in-flight | Đo thực tế | Không vượt cap |
| Requests/minute | Đo thực tế | Không vượt quota |
| Tokens/minute | Đo thực tế | Không vượt quota |
| Budget overshoot | Đo thực tế | 0 operation mới sau hard stop |
| Queue wait p95 | Đo thực tế | Trong ngưỡng đã chọn |
| 429/retry rate | Đo thực tế | Có backoff, không retry storm |
| Result duplicates | Đo thực tế | 0 duplicate logical results |

Không điền số giả định vào kết quả thực hành. Ghi cấu hình test, số đo và giới hạn của test double.

### Câu hỏi tự kiểm

**Câu 1:** Có 8 worker threads. Có thể kết luận chỉ tối đa 8 model calls đang in-flight không?

Không. Mỗi worker có thể fan-out async thành nhiều model calls. Cần provider operation gate.

**Câu 2:** Concurrency là 4 nhưng provider vẫn trả 429. Vì sao?

Có thể RPM/TPM vượt quota, burst ở fixed window, hoặc quota account bị traffic khác sử dụng. Cần rate limiter và shared quota coordination.

**Câu 3:** Hai workers cùng đọc available budget rồi reserve. Làm sao tránh overspend?

Dùng atomic transaction/conditional update hoặc distributed coordinator; reservation phải có ID và settle idempotent.

**Câu 4:** Client timeout trước khi nhận usage metadata. Có được release toàn bộ cost reservation như actual bằng 0 không?

Không. Ghi usage pending/unknown và reconcile provider request ID trước khi kết luận.

**Câu 5:** Semaphore local có bảo vệ provider account khi chạy 5 replicas không?

Không. Nó chỉ giới hạn từng JVM; cần global distributed limiter/gateway.

## 30. Checklist trước khi chạy evaluation lớn

- [ ] Đã khóa dataset, candidate, rubric và evaluator versions.
- [ ] Đã xác định budget scope: candidate, evaluator, run hay fully allocated.
- [ ] Đã ước tính cases, candidates, repetitions, attempts và model/tool/judge calls.
- [ ] Đã pilot theo cohort và có p90/p95 cost forecast.
- [ ] Có monetary, token, model-call, tool-call, case và time hard limits.
- [ ] Có soft threshold, hard stop và emergency stop.
- [ ] Reservation được cấp atomically ở mọi scope liên quan.
- [ ] Reservation, actual và released amount được lưu riêng.
- [ ] Có run/case/provider/model/tool concurrency gates.
- [ ] Có RPM/TPM/token-aware rate limiter.
- [ ] Có bounded queue, admission control và backpressure.
- [ ] Có fairness/per-tenant cap và production traffic protection.
- [ ] Retry phân loại lỗi, tôn trọng Retry-After và có jitter/max attempts.
- [ ] Cancellation dừng dispatch mới và lưu partial results.
- [ ] Job state machine và idempotency ngăn duplicate execution/result.
- [ ] Global concurrency được quản lý giữa nhiều worker instances.
- [ ] Async permit chỉ release khi operation hoàn tất hoặc cancel.
- [ ] Dashboard hiển thị budget, reservation, queue, in-flight, throughput và 429.
- [ ] Có runbook cho budget cap, provider throttling và stuck jobs.
- [ ] Có test overspend race, quota, retry storm, cancellation và worker crash.
- [ ] Cost/usage pending được reconcile sau timeout hoặc disconnect.

### Tài liệu chính thức để triển khai

- Spring Framework Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Boot Task Execution and Scheduling: https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html
- Resilience4j RateLimiter: https://resilience4j.readme.io/docs/ratelimiter
- Resilience4j Bulkhead: https://resilience4j.readme.io/docs/bulkhead
- Micrometer Observation: https://docs.micrometer.io/micrometer/reference/observation.html
- OpenTelemetry GenAI semantic conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/

**Kết luận:** chạy evaluation an toàn cần dự báo usage trước, reserve budget nguyên tử, giới hạn concurrency và rate ở từng operation, rồi settle theo actual usage. Bounded queue, backpressure, fairness, retry có kiểm soát và distributed permits giúp bảo vệ provider quota lẫn production capacity. Theo dõi budget, queue, in-flight calls, quality và latency cùng nhau để run hoàn tất trong giới hạn đã duyệt mà vẫn tạo ra kết quả đánh giá đáng tin cậy.
