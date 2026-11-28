# Quản lý retry và chạy tiếp từ các ca chưa hoàn tất

Một batch đánh giá Spring AI có 500 ca. Sau khi 320 ca đã hoàn tất, provider bắt đầu trả 429; runner retry một số request, các request khác timeout, rồi máy CI bị dừng. Khi job được chạy lại, nhóm cần biết ca nào đã có kết quả đáng tin, ca nào cần thử lại và ca nào có thể đã thực hiện một hành động tool nhưng chưa ghi được kết quả.

Chạy lại toàn bộ dataset có thể gọi lại những ca đã hoàn tất, phát sinh chi phí, tạo câu trả lời khác do model có tính xác suất và lặp side effect của tool. Tiếp tục từ số thứ tự cuối cùng cũng không an toàn: các ca chạy song song hoàn tất không theo thứ tự, nên cursor có thể bỏ sót hoặc chạy trùng.

Giải pháp là kết hợp **retry có chính sách** với **checkpoint theo từng case/attempt**. Retry xử lý lỗi có khả năng phục hồi; checkpoint lưu trạng thái và bằng chứng đã hoàn thành; resume khôi phục đúng những ca còn thiếu trong cùng một cấu hình đánh giá. Ba cơ chế này cần đi cùng định danh ổn định, lưu kết quả bền vững, giới hạn số lần thử, timeout, idempotency và quy tắc chọn kết quả.

Trong module **SPRING_AI_EVALUATION_OBSERVABILITY**, quy trình này giúp các bộ đánh giá relevance, fact checking, RAG và tool calling chạy ổn định trên dataset lớn, đồng thời giữ metrics, traces, token, chi phí và độ trễ để so sánh các phiên bản prompt, model và pipeline.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt retry một model/tool call, retry một evaluation attempt và chạy lặp một case để đo độ biến thiên.
2. Phân loại lỗi retryable, non-retryable và unknown outcome theo hợp đồng của từng thao tác.
3. Thiết kế retry budget, exponential backoff, jitter, Retry-After, timeout và deadline.
4. Tránh retry mù quáng đối với tool có side effect bằng idempotency key và bước đối soát.
5. Lưu trạng thái theo run, case và attempt để phục hồi sau khi runner dừng.
6. Thiết kế checkpoint bền vững và resume mà không chạy lại các case đã có kết quả được chấp nhận.
7. Phân biệt lỗi thực thi với FAIL chất lượng và lỗi evaluator.
8. Tổ chức claim/lease để nhiều worker không xử lý cùng một case ngoài ý muốn.
9. Tích hợp retry và resume với bounded concurrency, provider rate limit và chi phí.
10. Kiểm thử timeout, crash, duplicate delivery, retry exhaustion và phục hồi bằng Java/JUnit.

## 2. Phân biệt retry call, retry attempt và resume run

Trước khi thiết kế code, cần thống nhất đơn vị đang được thử lại.

| Thao tác | Phạm vi | Ví dụ | Có tạo answer mới không? |
| --- | --- | --- | --- |
| **Call retry** | Một lời gọi provider/tool | ChatModel trả 429, thử lại request | Có thể, tùy thao tác |
| **Attempt retry** | Chạy lại pipeline của một case | Retrieval + generation + tool orchestration | Thường có |
| **Evaluator retry** | Chạy lại bước chấm trên evidence đã lưu | Judge timeout sau khi answer đã lưu | Không cần tạo answer mới |
| **Run resume** | Tiếp tục các case chưa có terminal outcome | CI job chạy tiếp sau khi máy dừng | Chỉ chạy case còn thiếu theo policy |
| **Repeated evaluation** | Chủ đích chạy lại case để đo biến thiên | Chạy 5 lần với cùng prompt/model | Có nhiều answer có chủ đích |

**Không gộp các thao tác này vào một biến `retryCount`.** Một attempt có thể có hai lần thử ChatModel, một lần gọi tool và một lần thử judge; một case có thể có ba execution attempts; một run có thể được resume nhiều lần.

Nên lưu riêng `modelCallAttempt`, `toolCallAttempt`, `evaluationAttemptId`, `caseAttemptId` và `resumeSessionId` khi các đơn vị này có ý nghĩa trong hệ thống.

### 2.1. Ví dụ một case có nhiều lần thử

~~~text
runId = eval-v5
caseId = REFUND-001

execution attempt #1
  retrieval: success
  model call #1: 429
  model call #2: timeout
  case outcome: TECHNICAL_ERROR

execution attempt #2
  retrieval: success
  model call #1: success
  answer persisted
  judge call #1: timeout
  case execution: COMPLETED
  factual correctness: NOT_EVALUATED

evaluator attempt #2
  reuse persisted answer + effective context
  judge call: success
  factual correctness: PASS
~~~

Attempt thứ hai không cần chạy lại generation khi chỉ có lỗi ở judge và evidence đã lưu đủ. Nếu chạy lại toàn pipeline, câu trả lời có thể khác, token/cost tăng và việc so sánh không còn là cùng một phép chấm.

## 3. Phân loại lỗi trước khi retry

Retry chỉ hữu ích khi lỗi **có khả năng tạm thời** và thao tác được thử lại an toàn. Không phải mọi exception, HTTP status hoặc verdict FAIL đều được retry.

| Tình huống | Phân loại gợi ý | Hành động |
| --- | --- | --- |
| HTTP 429 / provider rate limit | Transient, thường retryable | Tuân thủ Retry-After, backoff và quota |
| HTTP 503 / dịch vụ tạm unavailable | Transient, có thể retry | Backoff có giới hạn |
| Connection reset trước khi gửi request | Thường retryable | Kiểm tra client/network |
| Timeout sau khi gửi request | **Unknown outcome** | Kiểm tra khả năng đã xử lý/đã tính phí |
| HTTP 400 do input/schema sai | Permanent | Sửa input hoặc code |
| HTTP 401/403 do credential/quyền sai | Thường permanent | Sửa cấu hình/quyền |
| Model trả câu trả lời sai | Quality FAIL | Lưu evidence; không retry để tìm answer đẹp hơn |
| Judge timeout | Evaluation error | Retry evaluator trên evidence đã lưu |
| Tool đọc trạng thái timeout | Có thể retry nếu read-only | Giới hạn số lần và deadline |
| Tool tạo giao dịch timeout | Unknown outcome, side effect | Đối soát trạng thái/idempotency trước |
| Result store tạm lỗi | Persistence error | Retry ghi idempotent, không gọi lại model |
| Runner bị kill | Interrupted/unknown | Phục hồi từ checkpoint và lease |

### 3.1. Phân loại theo hợp đồng, không chỉ HTTP status

HTTP 403 không phải luôn là lỗi: trong ca security test, từ chối quyền có thể là hành vi mong đợi và được chấm PASS. HTTP 404 có thể là dữ liệu không tồn tại theo kỳ vọng, hoặc có thể là sai endpoint. Cần phân loại dựa trên **operation contract**, không chỉ mã status.

Tương tự, model trả JSON sai schema có thể là quality/contract FAIL nếu response đã được nhận và kiểm chứng; không retry vô hạn đến khi model tình cờ tạo JSON đúng.

### 3.2. Timeout không đồng nghĩa thao tác chưa xảy ra

Khi client hết thời gian chờ, request có thể đã đến provider/backend và được xử lý, nhưng response bị mất. Với generation, điều này có thể phát sinh usage/cost dù runner không nhận answer. Với tool có side effect, giao dịch có thể đã commit.

Ghi trạng thái `UNKNOWN_OUTCOME` khi chưa biết kết quả. Trước khi retry thao tác side effect, cần đối soát bằng operation ID/idempotency key hoặc truy vấn trạng thái backend.

## 4. Retry policy và ngân sách

Một retry policy nên định nghĩa:

- `maxTotalAttempts`: tổng số lần thử tối đa, **bao gồm lần đầu**.
- `retryableErrorCodes`: loại lỗi có thể thử lại.
- `initialBackoff` và `maxBackoff`.
- Jitter để nhiều worker không retry cùng lúc.
- Cách xử lý `Retry-After`.
- Per-call timeout và overall deadline.
- Retry budget theo case, provider và toàn run.
- Những thao tác không được retry tự động.
- Cách ghi lại attempts và lý do dừng.

Ví dụ policy giả định:

~~~yaml
retryPolicy:
  maxAttemptsPerModelCall: 3
  maxAttemptsPerCase: 2
  initialBackoffMs: 500
  maxBackoffMs: 8000
  jitter: full
  honorRetryAfter: true
  perModelCallTimeoutMs: 20000
  caseDeadlineMs: 60000
  retryableCodes:
    - RATE_LIMIT
    - TEMPORARY_UNAVAILABLE
    - CONNECTION_RESET
  nonRetryableCodes:
    - INVALID_REQUEST
    - AUTHENTICATION_FAILED
    - PERMISSION_DENIED
    - INVALID_SCHEMA
  toolSideEffects:
    automaticRetry: false
    requireIdempotencyOrReconciliation: true
~~~

Đây là cấu hình minh họa, không phải cấu hình mặc định của Spring AI hoặc mọi provider.

### 4.1. maxAttempts khác maxRetries

Một số thư viện gọi maxAttempts=3 là tổng cộng ba lần thử (một lần đầu + hai retry); một số cấu hình khác dùng maxRetries=3 nghĩa là một lần đầu + ba retry. Đọc rõ semantics của thư viện đang dùng.

Trong manifest của hệ thống đánh giá, nên chuẩn hóa thành tên không mơ hồ như `maxTotalAttempts`.

### 4.2. Retry budget nhiều tầng

Chỉ giới hạn số lần thử trên mỗi call chưa đủ. Một run 10.000 case, mỗi case ba lần thử và mỗi attempt có bốn model calls có thể tạo tải rất lớn.

| Ngân sách | Phạm vi | Mục tiêu |
| --- | --- | --- |
| Per-call attempts | Một model/tool/evaluator call | Tránh retry vô hạn một request |
| Per-case attempts | Một case execution | Tránh lặp toàn pipeline quá nhiều |
| Per-provider retry budget | Tất cả calls cùng quota | Tránh retry storm lên provider |
| Per-run retry budget | Một evaluation run | Giới hạn tổng call phát sinh thêm |
| Cost budget | Một run hoặc stage | Không vượt ngân sách token/chi phí |
| Deadline budget | Một case/run | Không retry khi không còn thời gian hữu ích |

Một run có thể dừng retry dù một case vẫn còn số lần thử theo policy, vì provider-wide budget hoặc run deadline đã hết. Ghi rõ nguyên nhân dừng.

## 5. Exponential backoff, jitter và Retry-After

Nếu nhiều case cùng nhận 429 rồi chờ đúng một giây, chúng có thể cùng gửi lại và tiếp tục bị throttle. Backoff giúp giãn khoảng cách giữa các lần thử; jitter thêm ngẫu nhiên để giảm đồng bộ.

### 5.1. Exponential backoff

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Trong đó \(d_0\) là thời gian chờ ban đầu, \(n\) là số lần retry đã thất bại và \(d_{\max}\) là giới hạn thời gian chờ.

Ví dụ \(d_0=500\) ms và \(d_{\max}=8\) giây:

| Lần retry | Backoff trước jitter |
| ---: | ---: |
| 1 | 500 ms |
| 2 | 1.000 ms |
| 3 | 2.000 ms |
| 4 | 4.000 ms |
| 5 trở đi | 8.000 ms |

### 5.2. Jitter

Với full jitter, chọn độ trễ ngẫu nhiên trong khoảng từ 0 đến giới hạn backoff của lần đó:

\[
d_{\mathrm{actual}} \sim U(0,d_n).
\]

Một số policy dùng equal jitter hoặc decorrelated jitter. Điều quan trọng là dùng chiến lược được định nghĩa rõ, có cap và không retry sớm hơn thời điểm provider yêu cầu.

### 5.3. Tuân thủ Retry-After

Provider có thể trả `Retry-After` dưới dạng số giây hoặc HTTP date. Nếu SDK/client cung cấp giá trị đã parse, ưu tiên dùng giá trị đó. Khi header yêu cầu chờ lâu hơn backoff nội bộ, không gửi sớm hơn chỉ vì local cap nhỏ.

Nếu thời gian `Retry-After` vượt deadline còn lại của case/run, ghi `RETRY_DEFERRED_DEADLINE` hoặc trạng thái tương đương và kết thúc lần thực thi hiện tại. Có thể tiếp tục ở một resume session sau nếu policy cho phép.

### 5.4. Nhả semaphore trước backoff

Nếu semaphore giới hạn số provider calls đang thực sự chạy, cần nhả permit sau khi call thất bại, rồi mới chờ backoff. Giữ permit trong lúc ngủ làm giảm concurrency hữu ích và chặn các request khác.

Với runner bất đồng bộ, tốt hơn là đưa retry vào hàng đợi có thời điểm chạy lại thay vì chiếm worker thread trong lúc sleep.

## 6. Timeout và deadline

| Giới hạn | Phạm vi | Ví dụ |
| --- | --- | --- |
| Connect timeout | Thiết lập kết nối | 3 giây |
| Per-call timeout | Một model/tool/evaluator call | 20 giây |
| Case deadline | Retrieval + generation + tool + evaluation | 60 giây |
| Run deadline | Toàn bộ batch | 30 phút |

Một case có ba lần thử, mỗi lần timeout 20 giây và backoff tổng 5 giây có thể vượt deadline 60 giây nếu còn retrieval/tool/evaluator. Phải tính thời gian còn lại trước khi bắt đầu call hoặc chờ retry.

### 6.1. Truyền deadline xuống các tầng

Áp remaining duration vào model client/HTTP client, VectorStore, tool backend, evaluator, backoff và bước persist. Không bắt đầu một model call có timeout 20 giây khi case chỉ còn hai giây.

### 6.2. Hủy task không bảo đảm dừng request

`Future.cancel(true)` và `shutdownNow()` thường gửi interrupt. Một blocking client có thể không dừng ngay. Cần dùng timeout/cancellation API của HTTP client/SDK và kiểm tra request đã thực sự kết thúc hay chưa.

Đừng đánh dấu case đã dừng hoàn toàn chỉ vì Future được cancel. Với side effect, trạng thái có thể cần là `UNKNOWN_OUTCOME` cho đến khi đối soát.

## 7. Ba lớp retry trong pipeline Spring AI

Một evaluation case có thể đi qua retrieval, generation, tool orchestration và evaluator. Cần xác định retry ở lớp nào.

### 7.1. Retry một model call

Dùng khi lỗi provider được phân loại transient và request an toàn để thử lại. Lưu từng call attempt, model ID, status, retry reason, usage nếu provider trả về, latency và response ref.

Nếu provider SDK đã tự retry, tránh bọc thêm retry ở tầng ứng dụng mà không biết tổng số lần call. Hai lớp retry lồng nhau có thể tạo số lần thử lớn hơn dự kiến.

### 7.2. Retry toàn bộ case execution

Dùng khi pipeline cần chạy lại từ đầu vì một stage bắt buộc thất bại và không thể tiếp tục từ evidence đã lưu. Ví dụ retrieval timeout trước generation.

Không dùng case retry chỉ vì câu trả lời FAIL về chất lượng. Nếu mục tiêu là đánh giá đúng output của candidate, retry để lấy câu trả lời đẹp hơn sẽ làm sai kết quả. Nếu muốn đo độ biến thiên, đó là **repeated evaluation** với attempt riêng và quy tắc tổng hợp riêng.

### 7.3. Retry evaluator độc lập

Nếu answer, effective context, reference và metadata đã được lưu bền vững, judge timeout có thể được retry mà không gọi lại ChatModel. Lưu `evaluationAttemptId`, `judgeVersion`, rubric version và lỗi trước đó.

Nếu judge/rubric thay đổi, đây là một lần chấm mới theo cấu hình khác, không phải retry tương đương. Lưu phiên bản và không ghi đè verdict lịch sử.

### 7.4. Retry tool call

- Tool read-only như `getOrderStatus`: có thể retry lỗi kết nối tạm thời nếu request semantics an toàn.
- Tool có side effect như `refundOrder`, `createOrder`, `sendEmail`: chỉ retry nếu backend hỗ trợ idempotency hoặc có bước đối soát đáng tin cậy.
- Tool trả kết quả nghiệp vụ như `DENIED` hoặc `NOT_FOUND`: đó có thể là output hợp lệ, không phải lý do retry.

Nếu model tự gọi tool nhiều vòng, retry toàn bộ `ChatClient.call()` có thể thực hiện lại cả chuỗi tool. Phải hiểu cách framework/provider thực thi tool trong phiên bản ứng dụng đang dùng và bảo vệ backend ở cấp giao dịch.

## 8. Idempotency và thao tác có side effect

**Idempotent operation** có nghĩa gọi lại cùng một thao tác với cùng định danh không tạo thêm tác dụng phụ ngoài kết quả đã định nghĩa. Ví dụ API hoàn tiền nhận idempotency key duy nhất cho giao dịch.

### 8.1. Idempotency key theo nghiệp vụ

~~~text
evaluationRunId / caseId / businessOperationId
eval-v5 / REFUND-017 / refund-attempt-1
~~~

Backend lưu key và kết quả. Nếu cùng key đến lần nữa, backend trả kết quả trước đó hoặc trạng thái tương đương thay vì thực hiện refund lần hai.

Không dùng key mới ở mỗi lần retry của cùng thao tác logic, vì backend có thể xem đó là giao dịch mới.

### 8.2. Timeout sau commit

1. Runner gọi `refundOrder` với idempotency key K.
2. Backend commit giao dịch.
3. Response bị mất do network timeout.
4. Runner không biết refund đã xảy ra hay chưa.

Hành động đúng:

- Ghi attempt `UNKNOWN_OUTCOME`.
- Query backend theo operation ID hoặc idempotency key.
- Nếu đã commit, ghi nhận kết quả đã xảy ra và tiếp tục xác minh.
- Nếu backend xác nhận chưa commit, chỉ thử lại theo policy.
- Nếu không thể đối soát, chuyển manual review hoặc terminal unknown; không gửi key mới để “thử cho chắc”.

### 8.3. Idempotency ở result store

Việc ghi attempt/outcome cũng phải chống ghi trùng. Dùng unique key như `(runId, attemptId)` hoặc `(runId, caseId, attemptNumber)`, transaction/upsert có điều kiện và không ghi đè evidence của attempt trước.

## 9. Checkpoint theo case, không chỉ theo cursor

Một checkpoint hữu ích trả lời được case nào đã được chọn, attempt nào đang chạy, answer/context/tool evidence đã được lưu chưa, metric nào còn pending và có thao tác tool nào cần đối soát hay không.

### 9.1. Vì sao checkpoint theo cursor không đủ?

Giả sử dataset theo thứ tự 1–100, runner có concurrency 4. Các case hoàn tất theo thứ tự 2, 3, 4, 1. Nếu ghi `lastCompletedIndex=4` khi case 4 xong, runner có thể tưởng case 1 đã xong và bỏ sót. Nếu chỉ ghi index 2, nó có thể chạy trùng case 3/4.

Vì vậy, **checkpoint phải lưu trạng thái theo `caseId`/`attemptId`** hoặc tập hoàn thành có thể đối chiếu với dataset snapshot. Cursor chỉ là tối ưu nạp dữ liệu, không phải nguồn sự thật duy nhất.

### 9.2. Bản ghi checkpoint minh họa

~~~json
{
  "runId": "support-eval-v5",
  "caseId": "REFUND-017",
  "caseStatus": "COMPLETED",
  "acceptedAttemptId": "REFUND-017-attempt-2",
  "attemptCount": 2,
  "retryableError": false,
  "retryBudgetAvailable": false,
  "lastStage": "EVIDENCE_PERSISTED",
  "evaluationStatus": {
    "relevance": "PASS",
    "groundedness": "PENDING",
    "factualCorrectness": "PENDING"
  },
  "evidenceRefs": {
    "answer": "secure-answer-ref",
    "effectiveContext": "secure-context-ref"
  },
  "updatedAt": "2026-05-18T10:15:00Z"
}
~~~

Dữ liệu chỉ minh họa. Checkpoint và evidence cần được ghi bền vững; không để raw context nhạy cảm vào checkpoint nếu chỉ cần reference có phân quyền.

### 9.3. Lưu theo stage

~~~text
case: REFUND-017
  eligibility: RECORDED
  retrieval: COMPLETED (evidenceRef=...)
  generation: COMPLETED (answerRef=...)
  tool: NOT_REQUIRED
  evaluation:
    relevance: PASS
    groundedness: PENDING
    factualCorrectness: PENDING
  aggregate: INCONCLUSIVE
~~~

Nếu runner dừng ở bước judge, resume có thể tiếp tục chấm từ evidence. Nếu runner dừng trước khi lưu answer, generation có thể cần chạy lại, nhưng phải xem attempt trước có trạng thái unknown hay không.

## 10. Append-only attempt history và case projection

Một thiết kế bền vững phân biệt **lịch sử attempt** với **projection trạng thái hiện tại của case**.

### 10.1. Attempt history

Mỗi attempt lưu một bản ghi riêng:

- `runId`, `caseId`, `attemptId`, `attemptNumber`.
- `startedAt`, `endedAt`, worker/lease reference.
- `executionStatus`, `failureStage`, `errorCode`.
- `retryable`, `retryReason`, `backoffDuration`.
- Model/tool call IDs, trace ID nếu có.
- Answer/context/tool evidence refs.
- Token usage, latency, estimated cost.
- Quan hệ với attempt trước nếu cần.

Không xóa attempt ERROR chỉ vì attempt sau PASS. Lịch sử giải thích reliability và chi phí.

### 10.2. Case projection

Một record cho mỗi `(runId, caseId)` có thể giữ eligibility, số attempt, retry budget còn lại, accepted attempt, metric verdicts, terminal status và lease/version. Projection có thể được tái tạo từ attempt history; khi update, dùng optimistic locking để tránh hai worker ghi đè nhau.

### 10.3. Không dùng latest attempt wins một cách mù quáng

Attempt mới nhất có thể timeout trong khi attempt trước đã có answer hợp lệ. Chính sách chọn accepted attempt phải dựa trên trạng thái và contract, không chỉ timestamp.

Nếu attempt #1 đã COMPLETED và evidence bền vững, một duplicate delivery tạo attempt #2 không nên tự động thay thế attempt #1. Có thể giữ #1 là accepted và ghi #2 là duplicate/redundant.

## 11. Resume run: khôi phục đúng các ca chưa hoàn tất

Resume là tiếp tục **cùng một logical evaluation run** dưới cùng manifest/dataset/rubric. Nên tạo `resumeSessionId` hoặc execution segment mới để theo dõi mỗi lần tiếp tục, nhưng giữ `runId` gốc.

### 11.1. Điều kiện trước khi resume

1. Manifest của run đọc được và bất biến.
2. Dataset snapshot/digest còn khớp.
3. Prompt/model/pipeline/rubric/judge versions cùng cấu hình của run.
4. Outcomes đã lưu được đọc và kiểm tra tính toàn vẹn.
5. Lease cũ đã hết hạn hoặc xác nhận không còn owner.
6. Unknown side effects đã được đối soát hoặc cách ly.
7. Retry budget và run deadline còn hiệu lực hoặc được gia hạn theo policy có audit.
8. Provider quota/credentials/fixture đã sẵn sàng.

Nếu candidate config thay đổi (prompt/model/index/rubric), **tạo run mới**. Không resume một run bằng cấu hình khác rồi trộn kết quả vào cùng báo cáo.

### 11.2. Phân loại case khi resume

| Trạng thái đã lưu | Xử lý khi resume |
| --- | --- |
| COMPLETED + evidence đầy đủ | Bỏ qua execution; có thể tiếp tục metric đang PENDING |
| COMPLETED + quality FAIL | Giữ FAIL; chỉ chạy lại nếu có policy repeated/re-evaluation rõ |
| ERROR retryable + còn budget | Đưa vào hàng đợi retry |
| ERROR permanent | Giữ terminal error hoặc manual review |
| SKIPPED theo policy | Giữ skip; chỉ xét lại nếu eligibility policy đổi trong run mới |
| RUNNING với lease còn hạn | Không claim lại |
| RUNNING với lease hết hạn | Đánh giá stale attempt; kiểm tra unknown outcome trước |
| NOT_STARTED | Đưa vào hàng đợi |
| Evaluator error, evidence đủ | Chạy lại evaluator, không generation |
| Tool side effect UNKNOWN | Đối soát backend trước khi quyết định |

**Quality FAIL không phải lỗi tạm thời.** Resume không được tự động chạy lại tất cả FAIL để tìm kết quả PASS. Nếu muốn đo variance, tạo repeated attempts có chủ đích và báo phân bố.

### 11.3. Thuật toán resume khái niệm

~~~text
load immutable run manifest
verify dataset digest, rubric, prompt/model/pipeline versions
load planned case IDs and case projections

for each caseId:
    if SKIPPED by approved policy:
        keep terminal skip
    else if accepted execution evidence is complete:
        keep accepted attempt
        schedule only pending evaluator stages
    else if an active lease exists:
        leave it to current owner
    else if a stale attempt has unknown side effects:
        schedule reconciliation, not blind replay
    else if retry budget remains and error is retryable:
        enqueue retry
    else if case is NOT_STARTED:
        enqueue first execution
    else:
        preserve terminal error / manual review

run queued work under bounded concurrency and provider quotas
persist every attempt and checkpoint before acknowledging completion
recompute summary from durable records
~~~

Đây là pseudocode mô tả hành vi. Việc thực thi thật cần transaction/claim atomic để hai runner resume cùng lúc không nhận cùng case.

## 12. Claim, lease và nhiều worker

Nếu một run được tiếp tục bởi nhiều worker hoặc CI jobs, hai process có thể cùng đọc thấy case PENDING và cùng chạy. Dùng cơ chế claim có tính atomic.

### 12.1. Lease-based claim

Một case có thể có:

- `leaseOwner`: worker/job đang xử lý.
- `leaseUntil`: thời điểm lease hết hạn.
- `leaseVersion`: fencing token/version tăng mỗi lần claim.
- `caseStatus`: PENDING/RUNNING/COMPLETED/ERROR...
- `updatedAt`.

Worker claim case bằng database operation có điều kiện: chỉ cập nhật khi case đang PENDING/RETRY_WAIT hoặc lease cũ đã hết hạn. Worker khác không được claim nếu lease còn hiệu lực.

### 12.2. Lease expiry chưa chứng minh worker cũ đã chết

Một worker có thể bị network partition hoặc GC pause, lease hết hạn, worker mới claim; sau đó worker cũ tỉnh lại và vẫn cố ghi kết quả. Dùng **fencing token** hoặc optimistic version để từ chối write từ owner cũ.

Mọi update phải xác minh lease/version hiện hành, không chỉ dựa vào tên worker.

### 12.3. Pseudocode claim

~~~sql
UPDATE evaluation_case_state
SET lease_owner = :workerId,
    lease_until = :leaseUntil,
    lease_version = lease_version + 1,
    status = 'RUNNING'
WHERE run_id = :runId
  AND case_id = :caseId
  AND (
       status IN ('NOT_STARTED', 'RETRY_WAIT')
       OR lease_until < CURRENT_TIMESTAMP
  );
~~~

Đây là SQL minh họa. Database và dialect cụ thể có thể cần RETURNING, row lock hoặc transaction khác. Worker chỉ được xử lý khi thao tác claim thực sự cập nhật đúng một row và nhận fencing token mới.

### 12.4. Ghi kết quả có fencing

Khi lưu outcome, yêu cầu `lease_version` phải khớp version được cấp. Nếu worker cũ ghi sau khi lease đã được cấp lại, database từ chối. Unique key của `attemptId` ngăn ghi duplicate.

## 13. Lưu bền vững và checkpoint an toàn

Một quy trình case có thể:

1. Claim case và persist trạng thái RUNNING.
2. Tạo `attemptId` và persist attempt STARTED.
3. Chạy retrieval/generation/tool.
4. Persist answer, context và tool evidence refs.
5. Chạy evaluator, persist từng verdict.
6. Persist accepted outcome và checkpoint.
7. Mark case terminal/ready-for-resume theo policy.
8. Release lease.

Nếu process chết giữa bước 3 và 4, không có evidence answer; cần kiểm tra provider/side effect trước khi replay. Nếu chết sau bước 4 nhưng trước bước 5, resume có thể tiếp tục evaluator.

### 13.1. Atomicity giữa evidence và checkpoint

Không đánh dấu case COMPLETED trước khi answer/evidence đã được ghi bền vững. Nếu checkpoint được ghi trước còn evidence store ghi sau rồi fail, resume sẽ bỏ qua một case không có dữ liệu chấm lại.

Tùy kiến trúc, có thể:
- Ghi evidence và attempt state trong cùng database transaction nếu cùng kho.
- Dùng trạng thái `EVIDENCE_PENDING` rồi finalize sau khi artifact store xác nhận.
- Dùng outbox/event pattern để đảm bảo sự kiện persist được xử lý lại.
- Kiểm tra artifact refs tồn tại và digest trước khi accepted.

### 13.2. Atomic file checkpoint

Với runner đơn ghi file JSON, nên ghi file tạm cùng filesystem, flush/close, rồi đổi tên nguyên tử khi filesystem hỗ trợ. Không ghi đè trực tiếp file duy nhất mà không có bản phục hồi. Với nhiều worker/process, file cục bộ không thay thế transaction/claim coordination.

### 13.3. Tần suất checkpoint

Ghi theo lô giảm I/O nhưng khi crash sẽ phải replay các case sau checkpoint. Nếu có tool side effects hoặc generation tốn phí, cần ghi attempt/evidence đủ sớm. Có thể checkpoint theo từng case hoặc batch nhỏ với replay-safe operations.

## 14. Java: retry policy và phân loại lỗi

Ví dụ Java 17+ minh họa policy tổng số attempts, phân loại lỗi và backoff có jitter. Đây là lớp tiện ích của test harness; cần nối với error types thực của SDK/provider.

~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.ThreadLocalRandom;

public final class RetryPolicy {

    public record Failure(
            String code,
            boolean transientFailure,
            Duration retryAfter) {}

    private final int maxTotalAttempts;
    private final Duration initialBackoff;
    private final Duration maxBackoff;

    public RetryPolicy(
            int maxTotalAttempts,
            Duration initialBackoff,
            Duration maxBackoff) {

        if (maxTotalAttempts < 1) {
            throw new IllegalArgumentException(
                    "maxTotalAttempts must be >= 1");
        }
        if (initialBackoff.isNegative() || initialBackoff.isZero()
                || maxBackoff.compareTo(initialBackoff) < 0) {
            throw new IllegalArgumentException("Invalid backoff bounds");
        }

        this.maxTotalAttempts = maxTotalAttempts;
        this.initialBackoff = initialBackoff;
        this.maxBackoff = maxBackoff;
    }

    public boolean shouldRetry(
            Failure failure,
            int completedAttempts,
            Duration remainingDeadline) {

        Objects.requireNonNull(failure);
        Objects.requireNonNull(remainingDeadline);

        if (completedAttempts < 1) {
            throw new IllegalArgumentException(
                    "completedAttempts must be >= 1 after a failed call");
        }
        if (!failure.transientFailure()) return false;
        if (completedAttempts >= maxTotalAttempts) return false;
        if (remainingDeadline.isZero() || remainingDeadline.isNegative()) {
            return false;
        }

        Duration delay = nextDelay(completedAttempts, failure.retryAfter());
        return delay.compareTo(remainingDeadline) < 0;
    }

    public Duration nextDelay(
            int failedAttemptNumber,
            Duration retryAfter) {

        if (failedAttemptNumber < 1) {
            throw new IllegalArgumentException(
                    "failedAttemptNumber must be >= 1");
        }

        double multiplier = Math.pow(
                2.0, Math.min(failedAttemptNumber - 1, 30));

        long baseMillis = initialBackoff.toMillis();
        long capMillis = maxBackoff.toMillis();
        long exponentialMillis = (long) Math.min(
                capMillis, baseMillis * multiplier);

        // Full jitter: giá trị ngẫu nhiên từ 0 đến exponential cap.
        long jitterMillis = exponentialMillis == 0
                ? 0
                : ThreadLocalRandom.current()
                        .nextLong(exponentialMillis + 1);

        Duration jittered = Duration.ofMillis(jitterMillis);

        // Không retry sớm hơn thời điểm provider yêu cầu.
        if (retryAfter != null && retryAfter.compareTo(jittered) > 0) {
            return retryAfter;
        }
        return jittered;
    }

    public int maxTotalAttempts() {
        return maxTotalAttempts;
    }
}
~~~

Trong code production, validate thêm trường hợp Duration quá lớn/overflow và chuẩn hóa `Retry-After` từ HTTP response. `shouldRetry` chỉ là một điều kiện: caller còn phải kiểm tra provider-wide budget, run budget, cost budget và trạng thái idempotency.

### 14.1. Mã lỗi cần được chuẩn hóa

Không phân loại retry bằng cách tìm từ “timeout” trong raw exception message. Tạo adapter ánh xạ SDK/provider errors thành mã ổn định như `RATE_LIMIT`, `TEMPORARY_UNAVAILABLE`, `INVALID_REQUEST`, `AUTHENTICATION_FAILED` và `UNKNOWN_OUTCOME`.

Raw message có thể chứa URL, headers, input hoặc thông tin nhạy cảm; chỉ lưu ở log có kiểm soát nếu thực sự cần.

## 15. Java: retry executor không retry mọi exception

Ví dụ sau dùng interface để tách thao tác, predicate phân loại lỗi và sleeper. Nhờ đó có thể test mà không phải chờ thời gian thực.

~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.function.Predicate;

public final class RetryExecutor {

    @FunctionalInterface
    public interface Operation<T> {
        T execute(int attemptNumber) throws Exception;
    }

    @FunctionalInterface
    public interface Sleeper {
        void sleep(Duration duration) throws InterruptedException;
    }

    private final Sleeper sleeper;

    public RetryExecutor(Sleeper sleeper) {
        this.sleeper = Objects.requireNonNull(sleeper);
    }

    public <T> T execute(
            Operation<T> operation,
            Predicate<Exception> retryable,
            RetryPolicy policy) throws Exception {

        Objects.requireNonNull(operation);
        Objects.requireNonNull(retryable);
        Objects.requireNonNull(policy);

        for (int attempt = 1; ; attempt++) {
            try {
                return operation.execute(attempt);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw interrupted;
            } catch (Exception failure) {
                if (attempt >= policy.maxTotalAttempts()
                        || !retryable.test(failure)) {
                    throw failure;
                }

                Duration delay = policy.nextDelay(attempt, null);
                // Operation đã kết thúc; caller có thể nhả provider permit.
                try {
                    sleeper.sleep(delay);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw interrupted;
                }
            }
        }
    }
}
~~~

Đây là ví dụ synchronous. Nếu sleeper bị interrupt, `InterruptedException` được truyền lên; lớp gọi cần giữ semantics hủy (thường re-interrupt thread nếu bắt exception rồi xử lý). Không bắt `Throwable` để retry `OutOfMemoryError`, `LinkageError` hoặc lỗi JVM nghiêm trọng.

Executor này là bản tối giản để minh họa luồng điều khiển; nó truyền `null` cho `retryAfter` vì chưa có adapter đọc response của provider. Khi tích hợp thật, lấy `Retry-After` từ response/exception đã chuẩn hóa và truyền vào `RetryPolicy.nextDelay`. Không bỏ header này chỉ vì executor mẫu chưa nối với HTTP client.

### 15.1. Không ngủ trong worker pool nếu batch lớn

Đối với runner nhiều case, một thread sleep trong backoff vẫn chiếm worker slot. Hệ thống production có thể lưu `nextEligibleAt` và dùng scheduler/queue để nạp lại công việc đúng thời điểm. Cần giữ bounded queue và giới hạn số provider calls.

## 16. Java: trạng thái attempt và checkpoint

~~~java
import java.time.Instant;
import java.util.List;

public final class EvaluationCheckpoint {

    public enum CaseStatus {
        NOT_STARTED, RUNNING, RETRY_WAIT,
        COMPLETED, ERROR, SKIPPED, CANCELLED,
        UNKNOWN_OUTCOME
    }

    public enum AttemptStatus {
        STARTED, SUCCEEDED, FAILED_RETRYABLE,
        FAILED_FINAL, UNKNOWN_OUTCOME, CANCELLED
    }

    public record AttemptRecord(
            String runId,
            String caseId,
            String attemptId,
            int attemptNumber,
            AttemptStatus status,
            String errorCode,
            String answerRef,
            String effectiveContextRef,
            String traceId,
            Instant startedAt,
            Instant endedAt) {}

    public record CaseCheckpoint(
            String runId,
            String caseId,
            CaseStatus status,
            String acceptedAttemptId,
            int totalAttempts,
            boolean retryableError,
            boolean retryBudgetAvailable,
            Instant nextEligibleAt,
            String leaseOwner,
            long leaseVersion,
            List<String> completedEvaluationIds,
            Instant updatedAt) {

        public CaseCheckpoint {
            completedEvaluationIds =
                    List.copyOf(completedEvaluationIds);
        }
    }

    private EvaluationCheckpoint() {}
}
~~~

Trong thiết kế thật, `AttemptRecord` thường là append-only; `CaseCheckpoint` là projection có thể cập nhật bằng optimistic locking. `acceptedAttemptId` phải được chọn theo policy, không tự động là attempt mới nhất.

## 17. Resume planner: chỉ đưa case đủ điều kiện trở lại queue

Định nghĩa repository contract giúp tách business policy khỏi database cụ thể:

~~~java
import java.util.List;
import java.util.Optional;

public interface EvaluationResumeRepository {

    Optional<EvaluationCheckpoint.CaseCheckpoint> findCase(
            String runId, String caseId);

    List<EvaluationCheckpoint.CaseCheckpoint> findCases(
            String runId);

    boolean claim(
            String runId,
            String caseId,
            String workerId,
            long expectedLeaseVersion);

    void appendAttempt(
            EvaluationCheckpoint.AttemptRecord attempt);

    void saveCheckpoint(
            EvaluationCheckpoint.CaseCheckpoint checkpoint);
}
~~~

Đây là interface minh họa; triển khai JDBC/JPA phải đảm bảo claim atomic và transaction semantics phù hợp.

### 17.1. Quy tắc chọn công việc resume

~~~java
import java.util.ArrayList;
import java.util.List;

public final class ResumePlanner {

    public enum Action {
        SKIP_ALREADY_COMPLETED,
        RESUME_EVALUATION_ONLY,
        RETRY_EXECUTION,
        RECONCILE_UNKNOWN_OUTCOME,
        WAIT_FOR_ACTIVE_LEASE,
        KEEP_TERMINAL,
        START_FIRST_ATTEMPT
    }

    public record Decision(String caseId, Action action, String reason) {}

    public static List<Decision> plan(
            List<EvaluationCheckpoint.CaseCheckpoint> checkpoints) {

        List<Decision> decisions = new ArrayList<>();

        for (var checkpoint : checkpoints) {
            Action action;
            String reason;

            switch (checkpoint.status()) {
                case COMPLETED -> {
                    action = checkpoint.completedEvaluationIds().isEmpty()
                            ? Action.RESUME_EVALUATION_ONLY
                            : Action.SKIP_ALREADY_COMPLETED;
                    reason = "Reuse persisted execution evidence";
                }
                case RETRY_WAIT -> {
                    action = Action.RETRY_EXECUTION;
                    reason = "Retry policy and budget must be rechecked";
                }
                case UNKNOWN_OUTCOME -> {
                    action = Action.RECONCILE_UNKNOWN_OUTCOME;
                    reason = "Check backend/provider outcome before replay";
                }
                case RUNNING -> {
                    action = Action.WAIT_FOR_ACTIVE_LEASE;
                    reason = "Do not duplicate a case with an active owner";
                }
                case NOT_STARTED -> {
                    action = Action.START_FIRST_ATTEMPT;
                    reason = "No execution attempt has been accepted";
                }
                case ERROR -> {
                    if (checkpoint.retryableError()
                            && checkpoint.retryBudgetAvailable()) {
                        action = Action.RETRY_EXECUTION;
                        reason = "Retryable error and budget remains";
                    } else {
                        action = Action.KEEP_TERMINAL;
                        reason = "Permanent error or retry budget exhausted";
                    }
                }
                case SKIPPED, CANCELLED -> {
                    action = Action.KEEP_TERMINAL;
                    reason = "Requires explicit policy to reopen";
                }
            }

            decisions.add(new Decision(
                    checkpoint.caseId(), action, reason));
        }

        return List.copyOf(decisions);
    }

    private ResumePlanner() {}
}
~~~

Đây là planner minh họa, không tự kiểm lease expiration, deadline, retry budget, manifest compatibility hoặc idempotency. Các điều kiện đó phải được kiểm tra trước khi action thực sự claim/submit case. Đặc biệt `ERROR` có thể là permanent hoặc retryable; không tự retry mọi ERROR.

### 17.2. Resume cùng run, cấu hình mới là run mới

Khi tiếp tục job bị ngắt, giữ `runId` và manifest bất biến, tạo `resumeSessionId` mới. Khi thay prompt, model, corpus/index, rubric hoặc dataset, tạo `runId` mới. Nếu thay judge nhưng muốn chấm lại evidence cũ, tạo evaluation session riêng có tham chiếu tới generation evidence và judge version mới.

## 18. Tích hợp với Spring AI pipeline

Giả sử ứng dụng có một `ChatClient` đã cấu hình cùng advisor/RAG pipeline:

~~~java
import org.springframework.ai.chat.client.ChatClient;

public final class SpringAiCaseProcessor {

    private final ChatClient chatClient;

    public SpringAiCaseProcessor(ChatClient chatClient) {
        this.chatClient = chatClient;
    }

    public String generate(String question) {
        return chatClient.prompt()
                .user(question)
                .call()
                .content();
    }
}
~~~

Đoạn code cho thấy một generation call đơn giản. Trong evaluation pipeline thật, processor cần capture actual retrieved/effective context, tool invocation events, model usage, response metadata và trace correlation theo khả năng instrumentation của phiên bản Spring AI đang dùng.

### 18.1. Không bọc toàn bộ pipeline bằng retry chung một cách mù quáng

Ví dụ không an toàn về semantics:

~~~java
retryExecutor.execute(
        attempt -> fullRagAndToolWorkflow.execute(testCase),
        this::isTransient,
        policy);
~~~

Nếu `fullRagAndToolWorkflow` có tool tạo side effect, retry toàn hàm có thể gọi lại giao dịch đã commit. Nếu answer đã được lưu nhưng judge lỗi, retry cả pipeline lại tạo answer mới không cần thiết.

Tốt hơn là tách stage:

- Retrieval có retry policy riêng nếu query an toàn.
- Generation có call retry policy và attempt evidence.
- Tool có policy dựa trên read-only/idempotency/reconciliation.
- Persistence retry idempotent.
- Evaluator retry độc lập trên evidence đã lưu.

### 18.2. Khi SDK đã retry

Kiểm tra cấu hình retry của model provider SDK và Spring integration. Nếu SDK tự thử lại ba lần và runner lại thử ba lần, có thể thành tối đa chín request cho một logical call. Ghi số request thực tế khi SDK cung cấp, hoặc ít nhất ghi cấu hình retry ở cả hai tầng.

## 19. Retry, resume và observability

Mỗi lần thử cần liên kết với cùng `runId`/`caseId` nhưng `attemptId` riêng. Nếu tracing có hỗ trợ, mỗi attempt/call có span/event riêng và correlation ID rõ.

### 19.1. Metrics nên theo dõi

| Metric | Ý nghĩa |
| --- | --- |
| `evaluation.retry.count` | Tổng retry theo stage/reason |
| `evaluation.retry.exhausted` | Hết retry budget |
| `evaluation.case.resume.count` | Số case được tiếp tục từ checkpoint |
| `evaluation.case.duplicate_claim` | Claim bị từ chối vì đã có owner |
| `evaluation.case.unknown_outcome` | Thao tác chưa xác định kết quả |
| `evaluation.case.checkpoint.failure` | Không ghi được checkpoint |
| `evaluation.case.execution.status` | COMPLETED/ERROR/SKIPPED... |
| `evaluation.evaluator.retry.count` | Retry chấm độc lập |
| `evaluation.provider.rate_limit` | 429/rate-limit events |
| `evaluation.cost.retry` | Chi phí ước tính phát sinh do retry |

Dùng tags hữu hạn như stage, provider, error family và status. Không đưa `caseId`, raw prompt, user ID hoặc trace ID có cardinality cao vào metric labels; lưu các ID trong attempt records/evidence store có phân quyền.

### 19.2. Đo latency đúng cách

Báo cả latency của từng provider call, tổng thời gian attempt gồm backoff, thời gian từ lần đầu tới accepted outcome, thời gian chờ queue/resume và thời gian evaluator riêng.

Nếu chỉ đo model call thành công cuối cùng, báo cáo sẽ bỏ qua độ trễ retry mà hệ thống thực sự chịu. Với streaming, theo dõi time-to-first-token và thời gian hoàn tất riêng.

### 19.3. Token và chi phí của attempts lỗi

Provider có thể đã xử lý request nhưng response bị mất. Nếu usage không có, ghi cost `UNKNOWN`/`ESTIMATED` theo chính sách, không tự gán 0. Khi provider trả usage, lưu theo từng call attempt và cộng generation, tool rounds, evaluator/judge riêng.

### 19.4. Trace không có cũng phải được thể hiện trung thực

Sampling có thể khiến một attempt không có trace. Lưu `traceUnavailableReason` hoặc trường tương đương; đừng tự tạo trace ID. Khi resume, trace của attempt mới khác trace attempt cũ, nhưng cả hai phải cùng liên kết về case và run.

## 20. Báo cáo run sau retry và resume

Một báo cáo hoàn chỉnh cần thể hiện cả kết quả cuối và lịch sử retry:

~~~json
{
  "runId": "support-eval-v5",
  "runStatus": "COMPLETED",
  "resumeSessions": [
    {"sessionId": "initial", "startedAt": "2026-05-18T10:00:00Z"},
    {"sessionId": "resume-1", "startedAt": "2026-05-18T10:25:00Z"}
  ],
  "counts": {
    "selectedCases": 500,
    "completedCases": 485,
    "qualityPass": 440,
    "qualityFail": 30,
    "inconclusive": 15,
    "technicalError": 10,
    "skipped": 5,
    "retryAttempts": 42,
    "resumedCases": 173,
    "unknownOutcomes": 0
  },
  "execution": {
    "manifestRef": "run-manifest-ref",
    "datasetDigestRef": "dataset-digest-ref",
    "retryPolicyVersion": "retry-v2"
  },
  "artifacts": {
    "caseOutcomes": "case-outcomes.jsonl",
    "attemptHistory": "attempt-history.jsonl",
    "retryEvents": "retry-events.jsonl",
    "evaluationGaps": "evaluation-gaps.jsonl"
  }
}
~~~

Số liệu hoàn toàn minh họa; tổng các nhóm cần được diễn giải theo đúng định nghĩa selected, eligible, completed, error, skip và các case chưa kết thúc. Trong hệ thống thật, hãy kiểm invariant thay vì sao chép con số.

### 20.1. Những invariant nên kiểm

- Mỗi `attemptId` là duy nhất trong phạm vi lưu trữ.
- Mỗi `caseId` thuộc đúng dataset snapshot của `runId`.
- Mỗi case có một case projection hiện tại, không có hai accepted attempts trái quy tắc.
- Một case không vừa `SKIPPED` vừa có generation attempt được chấp nhận nếu schema không cho phép.
- `retryAttempts` đếm số lần thử lại, không đếm lần đầu và không đếm repeated evaluation như retry.
- `resumedCases` đếm case có tiếp tục từ checkpoint, không phải tổng case chạy lại.
- `COMPLETED` chỉ được ghi sau khi evidence cần thiết đã persist.
- Case `UNKNOWN_OUTCOME` phải có reconciliation status hoặc được liệt kê rõ.
- `runStatus=COMPLETED` không có nghĩa mọi quality verdict PASS.
- Summary và attempt history phải có thể đối chiếu.

## 21. JUnit: kiểm thử retry và resume

Các test dưới đây kiểm logic policy/planner bằng dữ liệu giả, không gọi provider thật.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import org.junit.jupiter.api.Test;

class RetryPolicyTest {

    @Test
    void transientFailureRetriesWhileBudgetRemains() {
        var policy = new RetryPolicy(
                3, Duration.ofMillis(100), Duration.ofSeconds(2));

        var failure = new RetryPolicy.Failure(
                "RATE_LIMIT", true, Duration.ZERO);

        assertTrue(policy.shouldRetry(
                failure, 1, Duration.ofSeconds(10)));
    }

    @Test
    void permanentFailureDoesNotRetry() {
        var policy = new RetryPolicy(
                3, Duration.ofMillis(100), Duration.ofSeconds(2));

        var failure = new RetryPolicy.Failure(
                "INVALID_REQUEST", false, null);

        assertFalse(policy.shouldRetry(
                failure, 1, Duration.ofSeconds(10)));
    }

    @Test
    void exhaustedAttemptsDoNotRetry() {
        var policy = new RetryPolicy(
                3, Duration.ofMillis(100), Duration.ofSeconds(2));

        var failure = new RetryPolicy.Failure(
                "TEMPORARY_UNAVAILABLE", true, null);

        assertFalse(policy.shouldRetry(
                failure, 3, Duration.ofSeconds(10)));
    }

    @Test
    void retryAfterLongerThanDeadlinePreventsRetry() {
        var policy = new RetryPolicy(
                3, Duration.ofMillis(100), Duration.ofSeconds(2));

        var failure = new RetryPolicy.Failure(
                "RATE_LIMIT", true, Duration.ofSeconds(8));

        assertFalse(policy.shouldRetry(
                failure, 1, Duration.ofSeconds(5)));
    }
}
~~~

### 21.1. Test resume planner

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class ResumePlannerTest {

    private EvaluationCheckpoint.CaseCheckpoint checkpoint(
            String caseId,
            EvaluationCheckpoint.CaseStatus status,
            List<String> evaluationIds) {

        return new EvaluationCheckpoint.CaseCheckpoint(
                "run-1",
                caseId,
                status,
                null,
                1,
                false,
                false,
                null,
                null,
                0,
                evaluationIds,
                Instant.parse("2026-05-18T10:00:00Z"));
    }

    @Test
    void completedCaseWithEvidenceIsNotExecutedAgain() {
        var row = checkpoint(
                "A",
                EvaluationCheckpoint.CaseStatus.COMPLETED,
                List.of("eval-1"));

        var decision = ResumePlanner.plan(List.of(row)).get(0);

        assertEquals(
                ResumePlanner.Action.SKIP_ALREADY_COMPLETED,
                decision.action());
    }

    @Test
    void completedCaseCanResumePendingEvaluation() {
        var row = checkpoint(
                "A",
                EvaluationCheckpoint.CaseStatus.COMPLETED,
                List.of());

        var decision = ResumePlanner.plan(List.of(row)).get(0);

        assertEquals(
                ResumePlanner.Action.RESUME_EVALUATION_ONLY,
                decision.action());
    }

    @Test
    void unknownOutcomeRequiresReconciliation() {
        var row = checkpoint(
                "A",
                EvaluationCheckpoint.CaseStatus.UNKNOWN_OUTCOME,
                List.of());

        var decision = ResumePlanner.plan(List.of(row)).get(0);

        assertEquals(
                ResumePlanner.Action.RECONCILE_UNKNOWN_OUTCOME,
                decision.action());
    }

    @Test
    void retryableErrorWithBudgetIsScheduledAgain() {
        var row = new EvaluationCheckpoint.CaseCheckpoint(
                "run-1",
                "A",
                EvaluationCheckpoint.CaseStatus.ERROR,
                null,
                1,
                true,
                true,
                null,
                null,
                0,
                List.of(),
                Instant.parse("2026-05-18T10:00:00Z"));

        var decision = ResumePlanner.plan(List.of(row)).get(0);

        assertEquals(
                ResumePlanner.Action.RETRY_EXECUTION,
                decision.action());
    }

    @Test
    void notStartedCaseCanBeScheduled() {
        var row = checkpoint(
                "A",
                EvaluationCheckpoint.CaseStatus.NOT_STARTED,
                List.of());

        var decision = ResumePlanner.plan(List.of(row)).get(0);

        assertEquals(
                ResumePlanner.Action.START_FIRST_ATTEMPT,
                decision.action());
    }
}
~~~

`List.getFirst()` có từ Java 21. Ví dụ dùng `get(0)` để tương thích Java 17. Test planner chưa thay thế integration test cho lease/atomic claim, database crash recovery và side effect reconciliation.

## 22. Bài thực hành: mô phỏng batch bị dừng rồi resume

**Bối cảnh:** một evaluation run có 200 case cho chatbot RAG và tool calling. Runner giới hạn 4 case in-flight. Sau 90 case hoàn tất, provider trả 429 trong một khoảng thời gian; một case tool timeout với outcome chưa xác định; job CI bị dừng.

### Phần A — Thiết kế retry policy

1. Phân loại lỗi provider, VectorStore, tool, judge và persistence.
2. Đặt `maxTotalAttempts`, backoff, jitter, Retry-After, per-call timeout và case deadline.
3. Xác định retry budget toàn provider/run và giới hạn chi phí.
4. Chỉ định thao tác nào read-only, thao tác nào có side effect.

**Đầu ra:** `retry-policy-v1` và error taxonomy.

### Phần B — Lưu attempt và checkpoint

Với mỗi case, lưu run/case/attempt IDs, stage status, answer/context/tool refs, usage, trace và timestamps. Lưu accepted outcome riêng với attempt history. Đảm bảo evidence persist trước khi case được đánh dấu COMPLETED.

**Đầu ra:** checkpoint có thể đọc lại sau khi process dừng.

### Phần C — Mô phỏng lỗi và retry

- Một model call 429 rồi thành công sau backoff.
- Một model call 400 không retry.
- Một judge timeout nhưng answer đã lưu.
- Một tool read-only timeout có thể thử lại.
- Một tool side effect timeout sau commit, cần reconciliation.
- Một lỗi result store tạm thời, cần ghi idempotent.

**Đầu ra:** attempt history có đầy đủ retry reason và không duplicate side effect.

### Phần D — Dừng runner và resume

Sau khi một số case đã hoàn tất, dừng process. Khởi động resume session mới với cùng run ID và manifest. Kiểm tra digest/config, load checkpoint, xử lý stale leases, chỉ enqueue các case phù hợp. Các ca đã có accepted evidence không chạy lại generation; judge còn pending chỉ chạy lại evaluator.

**Đầu ra:** report có `resumeSessionId`, `resumedCases`, retry count và danh sách unknown outcomes.

### Phần E — Kiểm tính toàn vẹn

Đối chiếu planned case IDs với case projections và attempt history. Tìm duplicate claims, thiếu evidence, accepted attempt sai, ca bị skip ngoài policy và retry budget vượt mức. Đảm bảo run status PARTIAL nếu còn case chưa có terminal outcome.

**Đầu ra:** validation report và summary nhất quán.

### Checklist nghiệm thu

- [ ] Retry phân biệt transient, permanent và unknown outcome.
- [ ] `maxTotalAttempts` có semantics rõ, bao gồm lần đầu.
- [ ] Backoff có cap, jitter và tuân thủ Retry-After.
- [ ] Không retry sau khi hết deadline hoặc budget.
- [ ] Provider semaphore được nhả trước backoff.
- [ ] Retry của evaluator không chạy lại generation.
- [ ] Tool side effect có idempotency/reconciliation.
- [ ] Mỗi execution attempt có ID riêng và history append-only.
- [ ] Checkpoint theo case/attempt, không chỉ theo cursor.
- [ ] Resume xác minh manifest, dataset digest và rubric/config.
- [ ] Completed cases không bị chạy lại generation ngoài policy.
- [ ] Stale lease có fencing/version để chống worker cũ ghi.
- [ ] Unknown outcomes được đối soát trước replay.
- [ ] Evidence được persist trước khi đánh dấu COMPLETED.
- [ ] Summary phân biệt retry, resume, repeated evaluation và quality verdict.
- [ ] Run partial không được báo như đã hoàn tất.

### Câu hỏi tự kiểm tra

1. Call retry khác case retry và repeated evaluation như thế nào?
2. Vì sao model answer FAIL về chất lượng không nên được retry đến khi PASS?
3. `maxAttempts=3` thường bao gồm những lần nào và vì sao cần chuẩn hóa tên?
4. Khi provider trả Retry-After 10 giây nhưng case chỉ còn deadline 5 giây, xử lý thế nào?
5. Vì sao không nên giữ semaphore trong thời gian backoff?
6. Timeout sau khi gửi `refundOrder` có chứng minh giao dịch chưa commit không?
7. Idempotency key cần ổn định qua những lần retry nào?
8. Vì sao checkpoint cursor không đủ cho batch chạy song song?
9. Khi generation đã hoàn tất nhưng judge timeout, resume nên chạy lại stage nào?
10. Khi nào phải tạo run ID mới thay vì resume run cũ?
11. Lease hết hạn có đủ chứng minh worker cũ đã chết không?
12. Fencing token ngăn tình huống nào?
13. Vì sao append-only attempt history quan trọng cho chi phí và reliability?
14. Nếu attempt #1 COMPLETED nhưng attempt #2 timeout, có nên tự động chọn attempt #2 vì nó mới nhất không?
15. Làm sao xử lý khi provider SDK và application đều có retry?
16. Vì sao run COMPLETED không đồng nghĩa mọi case quality PASS?

## 23. Những sai lầm thường gặp

**Retry mọi exception.** Có thể lặp request vô ích, tăng chi phí hoặc tạo side effect.

**Retry answer FAIL để tìm output đẹp hơn.** Làm sai phép đánh giá; nếu đo biến thiên, dùng repeated evaluation có policy riêng.

**Chỉ giới hạn retry theo case.** Tổng số request có thể bùng nổ; cần provider/run/cost budgets.

**Backoff không jitter.** Nhiều worker có thể retry đồng loạt và tiếp tục bị throttle.

**Bỏ qua Retry-After.** Gửi request quá sớm và làm provider tiếp tục rate limit.

**Giữ semaphore khi sleep.** Giữ slot provider trong lúc không có call đang chạy.

**Dùng một retry wrapper cho toàn bộ RAG/tool workflow.** Có thể chạy lại tool side effect hoặc generation không cần thiết.

**Coi timeout là chắc chắn chưa thực thi.** Kết quả có thể unknown; phải đối soát.

**Chỉ lưu `lastCompletedIndex`.** Batch song song có thể hoàn tất ngoài thứ tự, dẫn đến bỏ sót hoặc chạy trùng.

**Overwrite attempt cũ bằng attempt mới.** Mất dấu lỗi, usage, trace và lịch sử.

**Resume bằng prompt/model/rubric mới trong cùng run.** Trộn các kết quả không cùng manifest.

**Cho hai worker cùng claim một case.** Cần atomic claim, lease và fencing.

**Đánh dấu COMPLETED trước khi evidence được lưu.** Resume có thể bỏ qua case không thể chấm lại.

**Đếm retry như repeated evaluation hoặc ngược lại.** Hai phép đo có mục đích và mẫu số khác nhau.

**Giả định cancel đồng nghĩa provider request đã dừng.** Phải kiểm timeout/cancellation ở client và trạng thái side effect.

## 24. Tổng kết

Quản lý retry và resume đúng cách giúp evaluation run Spring AI có thể phục hồi sau 429, timeout, lỗi tool, judge hoặc runner mà vẫn giữ tính toàn vẹn của kết quả.

**Retry** cần phân loại lỗi, giới hạn attempts, backoff/jitter, Retry-After, deadline và ngân sách. **Idempotency/reconciliation** bảo vệ tool có side effect và xử lý timeout không rõ kết quả. **Checkpoint theo case/attempt** giữ tiến độ bền vững; **append-only history** bảo toàn lỗi, chi phí và evidence; **resume cùng manifest** chỉ tiếp tục các stage/case còn thiếu. Với generation đã lưu nhưng evaluator lỗi, chạy lại evaluator trên evidence thường hợp lý hơn chạy lại cả pipeline.

Khi `runId`, `caseId`, `attemptId`, lease, evidence và trạng thái được quản lý rõ, nhóm có thể tiếp tục batch mà không bỏ sót hoặc âm thầm nhân đôi ca, đồng thời giữ metrics, traces, token, latency và chi phí để giải thích từng lần thử. Một run được phục hồi thành công vẫn cần báo riêng quality PASS/FAIL, technical errors, evaluation gaps và outcome chưa xác định.

### Tài liệu tham khảo

- [Spring AI — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring AI — Chat Model API](https://docs.spring.io/spring-ai/reference/api/chatmodel.html)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring Boot — Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Java — Duration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html)
- [Java — ThreadLocalRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
