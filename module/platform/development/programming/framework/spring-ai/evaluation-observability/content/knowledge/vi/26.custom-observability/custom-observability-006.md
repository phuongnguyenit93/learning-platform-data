# Quan sát pipeline đánh giá theo lô

Một evaluation run có thể gồm hàng nghìn cases, được chia thành nhiều batches và xử lý song song bởi nhiều workers. Mỗi case có thể gọi retriever, model, tool và judge; một số case thành công ngay, một số retry, timeout hoặc chỉ hoàn tất một phần. Nếu chỉ quan sát một HTTP request hay một trace riêng lẻ, nhóm vận hành khó trả lời các câu hỏi quan trọng: run đang tiến triển đến đâu, batch nào bị nghẽn, case nào tốn token nhất, judge có chậm hơn candidate model không, và kết quả quality có đại diện cho toàn bộ dataset hay không?

Bài học thuộc chương **Quan sát tùy chỉnh** của module `SPRING_AI_EVALUATION_OBSERVABILITY`. Module tập trung đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để tìm nguyên nhân suy giảm giữa các phiên bản prompt, model và pipeline. Với pipeline theo lô, observability cần kết nối trạng thái vận hành với kết quả evaluation và provenance của từng run.

Sau bài học, bạn có thể:

- Mô hình hóa telemetry theo run, batch, case và attempt.
- Định nghĩa lifecycle và trạng thái cho batch evaluation.
- Instrument metrics cho progress, throughput, queue, latency, error, token và cost.
- Thiết kế trace hierarchy và context propagation qua worker bất đồng bộ.
- Quan sát partial failure, retries, cancellation, checkpoint và resume.
- Phân tích quality scores theo slice, model, prompt và rubric.
- Xây dashboard, alert và run summary có thể hành động.
- Giới hạn cardinality và bảo vệ prompt, answer, evidence, tool arguments.

## 1. Vì sao batch evaluation cần observability riêng?

Evaluation đồng bộ cho một request thường có một lifecycle ngắn. Batch evaluation có lifecycle dài hơn nhiều:

1. Nhận yêu cầu chạy dataset.
2. Xác định candidate, baseline, rubric và dataset snapshot.
3. Chia cases thành batches.
4. Đưa batches vào queue.
5. Worker claim batch và thực hiện từng case.
6. Mỗi case gọi retrieval/model/tool/judge.
7. Retry hoặc đánh dấu lỗi theo policy.
8. Persist per-case results và aggregate metrics.
9. Hoàn tất run, hoặc dừng một phần vì cancel/budget/deadline.

Một run có thể kéo dài vài phút hoặc vài giờ. Trong thời gian đó, một số workers có thể chết, queue có thể tăng, provider có thể throttling, và kết quả có thể chỉ được persist một phần. Vì vậy, một log “run started” và một log “run finished” không đủ để vận hành.

### 1.1. Những câu hỏi vận hành cần trả lời

| Nhóm | Câu hỏi |
|---|---|
| Progress | Bao nhiêu cases đã chọn, đã chạy, còn lại, bị skip? |
| Queue | Batch chờ bao lâu? Worker có đủ capacity không? |
| Throughput | Cases/phút và model calls/phút là bao nhiêu? |
| Latency | Chậm ở queue, retrieval, model, judge hay persistence? |
| Reliability | Timeout, 429, invalid output và retry tập trung ở đâu? |
| Cost | Model candidate, judge, embedding và retry tiêu bao nhiêu? |
| Quality | Score giảm ở slice/model/prompt nào? |
| Completeness | Kết quả aggregate có đủ coverage để kết luận không? |
| Recovery | Run có resume an toàn sau worker crash không? |
| Privacy | Telemetry có vô tình chứa raw prompt, answer hoặc secrets? |

### 1.2. Tách vận hành pipeline và chất lượng answer

Một evaluation case có thể có hai kết quả độc lập:

- **Execution outcome:** worker có thực hiện được operation và thu được output hợp lệ không?
- **Quality verdict:** output có đạt rubric không?

Ví dụ judge hoàn tất bình thường nhưng chấm answer là FAIL: execution thành công, quality không đạt. Nếu judge timeout: execution lỗi, không có verdict hợp lệ. Không gộp cả hai thành một error counter.

### 1.3. Một run hoàn tất không có nghĩa mọi case đều thành công

Run có thể kết thúc với:

- Tất cả cases PASS.
- Một số quality FAIL nhưng mọi cases đã được chấm.
- Một số execution ERROR/TIMEOUT.
- Một số cases SKIPPED/NOT_RUN_BUDGET.
- Run bị CANCELLED hoặc ABORTED.

Run status phải thể hiện trạng thái tổng hợp và coverage. Không dùng `COMPLETED` để ngầm khẳng định chất lượng đạt hoặc tất cả cases thành công.

## 2. Mô hình dữ liệu telemetry: run → batch → case → attempt

Trước khi tạo metrics hoặc spans, cần một mô hình định danh ổn định. Mọi telemetry phải có thể truy ngược về đúng run và candidate configuration.

### 2.1. Bốn cấp độ

| Entity | Phạm vi | Ví dụ |
|---|---|---|
| `Run` | Một lần evaluation trên một candidate/dataset/rubric | `run-2026-11-27-a91f` |
| `Batch` | Một nhóm cases được worker xử lý | `batch-0042` |
| `Case` | Một sample trong dataset | `case-rag-017` |
| `Attempt` | Một lần thực thi case hoặc external operation | `attempt-2` |

Một case có thể có nhiều attempts do retry. Một attempt có thể chứa nhiều operation spans: retrieval, model generation, tool execution và judge. Phân biệt retry của cả case với retry của một HTTP request bên trong case.

### 2.2. Quan hệ

```text
Evaluation Run
  |
  +-- Batch 001
  |     +-- Case 001
  |     |     +-- Attempt 1
  |     |     |     +-- Retrieval
  |     |     |     +-- Model generation
  |     |     |     +-- Judge
  |     |     +-- Attempt 2 (retry)
  |     |
  |     +-- Case 002
  |
  +-- Batch 002
        +-- Case 003
              +-- Attempt 1
                    +-- Retrieval
                    +-- Tool execution
                    +-- Model generation
                    +-- Judge
```

### 2.3. Run manifest

Một run manifest nên ghi lại các version cần thiết để tái lập:

```yaml
run:
  run_id: "run-2026-11-27-a91f"
  trigger: "nightly"
  started_at: "2026-11-27T20:00:00Z"
  dataset_id: "policy-assistant-regression"
  dataset_version: "v18"
  rubric_version: "groundedness-v6"
  evaluator_version: "judge-adapter-v4"

candidate:
  prompt_version: "answer-v21"
  model_provider: "provider-a"
  model_id: "model-revision-2026-11"
  pipeline_version: "rag-tool-pipeline-v12"
  embedding_version: "embed-v5"
  index_snapshot: "policy-index-2026-11-26"

execution:
  selected_cases: 1200
  batch_size: 40
  max_concurrency: 8
  max_cost_usd: 25.00
  deadline_seconds: 7200
```

Không đưa API key, raw prompt, raw answer hoặc customer identifiers vào manifest. Những dữ liệu đó cần nằm ở artifact store có access control nếu thực sự cần lưu.

### 2.4. Candidate fingerprint

Tạo một fingerprint từ các cấu hình ảnh hưởng output:

\[
F = hash(prompt, model, parameters, retriever, index, tools, rubric, evaluator)
\]

Lưu fingerprint trong run metadata và result records. Không dùng fingerprint làm metric label nếu nó thay đổi theo từng commit; lưu trong result store hoặc trace attributes theo policy.

### 2.5. Định danh không đồng nghĩa metric dimensions

`run_id`, `batch_id`, `case_id`, `attempt_id` cần thiết để truy xuất artifacts, nhưng không nên trở thành labels của metrics. Chúng có thể có cardinality gần bằng số records và làm backend metrics phình nhanh.

## 3. Định nghĩa lifecycle và trạng thái của run

Run status phải có semantics rõ. Một state machine giúp UI, scheduler, worker và aggregator hiểu giống nhau.

### 3.1. Run lifecycle

```text
CREATED
   |
   v
VALIDATING
   |
   v
QUEUED
   |
   v
RUNNING
   | \
   |  +----> CANCELLING ----> CANCELLED
   |
   +----> FINALIZING
              |
              +----> COMPLETED
              +----> COMPLETED_WITH_ERRORS
              +----> FAILED
              +----> ABORTED
```

Ý nghĩa:

| State | Ý nghĩa |
|---|---|
| `CREATED` | Run record đã được tạo |
| `VALIDATING` | Kiểm tra dataset, config, budget và dependencies |
| `QUEUED` | Đã sẵn sàng, đang chờ worker capacity |
| `RUNNING` | Có batches đang được xử lý |
| `CANCELLING` | Đã nhận yêu cầu cancel, đang dừng công việc đang chạy |
| `FINALIZING` | Tổng hợp, persist summary và đóng artifacts |
| `COMPLETED` | Hoàn tất theo contract, không có execution errors cần phân loại riêng |
| `COMPLETED_WITH_ERRORS` | Đã kết thúc nhưng có cases execution error/timeout |
| `FAILED` | Run không thể hoàn tất vì lỗi run-level |
| `CANCELLED` | Người dùng hoặc policy yêu cầu dừng |
| `ABORTED` | Hệ thống dừng ngoài kế hoạch, ví dụ deadline/budget/fatal infrastructure |

Quality verdict FAIL không tự biến run thành FAILED. Run có thể COMPLETED trong khi một tỷ lệ answer không đạt rubric.

### 3.2. Case lifecycle

```text
PENDING -> CLAIMED -> RUNNING -> EVALUATING -> PERSISTING -> FINISHED
                  |       |             |
                  |       +-> RETRY_WAIT |
                  |                     +-> ERROR
                  +-> LEASE_EXPIRED

PENDING -> SKIPPED
RUNNING -> CANCELLED
RETRY_WAIT -> RUNNING
```

Các status case nên gồm `PENDING`, `CLAIMED`, `RUNNING`, `RETRY_WAIT`, `FINISHED`, `QUALITY_FAIL`, `ERROR`, `TIMEOUT`, `INVALID`, `SKIPPED`, `CANCELLED` và `NOT_RUN_BUDGET`. Nếu dùng `FINISHED` cho execution complete, lưu verdict riêng để không nhập nhằng.

### 3.3. Attempt status

Một attempt có thể kết thúc `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `CANCELLED` hoặc `UNKNOWN`. Lưu attempt number và reason code đã chuẩn hóa. Không chỉ ghi attempt cuối vì attempt đầu có thể tiêu token/cost hoặc bộc lộ reliability issue.

### 3.4. State transition phải idempotent

Worker có thể gửi event nhiều lần do message redelivery hoặc retry. Cập nhật state phải có:

- Version/sequence number hoặc compare-and-set.
- Idempotency key cho event.
- Kiểm tra transition hợp lệ.
- Timestamp từ nguồn có ý nghĩa.
- Actor/source tạo transition.

Không để event `FINISHED` cũ ghi đè state `CANCELLED` mới hơn.

## 4. Event model cho pipeline theo lô

Metrics cho biết xu hướng; events giải thích vì sao state thay đổi. Event model cần thống nhất giữa scheduler, worker, evaluator và aggregator.

### 4.1. Các event chính

| Event | Khi phát | Attributes nên có |
|---|---|---|
| `evaluation.run.created` | Tạo run | trigger, dataset version, candidate fingerprint |
| `evaluation.run.started` | Bắt đầu dispatch | selected cases, batch count |
| `evaluation.batch.queued` | Batch vào queue | batch size, queue name |
| `evaluation.batch.claimed` | Worker nhận batch | worker pool, lease duration |
| `evaluation.case.started` | Bắt đầu case | task type, feature |
| `evaluation.operation.completed` | Model/retrieval/tool/judge xong | operation, duration, status |
| `evaluation.case.completed` | Case có kết quả | execution outcome, verdict |
| `evaluation.case.retry_scheduled` | Lên lịch retry | attempt, reason, backoff |
| `evaluation.batch.completed` | Batch kết thúc | completed, failed, skipped counts |
| `evaluation.run.finalized` | Run đóng | aggregate counts, quality summary |
| `evaluation.run.cancelled` | Run bị hủy | reason, actor |

### 4.2. Event envelope

Một envelope tham chiếu:

```json
{
  "event_id": "evt-8f12",
  "event_type": "evaluation.case.completed",
  "occurred_at": "2026-11-27T20:12:18.210Z",
  "run_id": "run-2026-11-27-a91f",
  "batch_id": "batch-0042",
  "case_id": "case-rag-017",
  "attempt": 2,
  "sequence": 19,
  "execution_status": "SUCCEEDED",
  "quality_verdict": "PASS",
  "duration_ms": 1840,
  "input_tokens": 1530,
  "output_tokens": 284
}
```

Đây là ví dụ schema event; không phải API bắt buộc của Spring AI. Dùng event ID để deduplicate và sequence/version để xử lý out-of-order events.

### 4.3. Event không thay thế result record

Event stream phục vụ progress và audit. Result store là nguồn dữ liệu chuẩn cho per-case final result và aggregate. Nếu event consumer mất event, có thể rebuild progress từ persisted state; nếu result store không lưu answer/verdict, không thể tái lập evaluation chỉ từ log.

### 4.4. Phân biệt event time và processing time

- `occurred_at`: thời điểm operation thực sự xảy ra theo producer.
- `received_at`: thời điểm collector/consumer nhận event.
- `processed_at`: thời điểm aggregator xử lý.

Chênh lệch giúp phát hiện queue lag, clock skew và consumer backlog. Đồng bộ clock giữa hosts; dùng monotonic clock để đo duration trong cùng process.

## 5. Bộ metrics cốt lõi cho batch evaluation

Metrics phải trả lời được run đang chạy tốt đến đâu và bottleneck ở đâu. Nên chia thành progress, throughput, queue, latency, reliability, quality và resource consumption.

### 5.1. Progress và throughput

| Metric | Type | Ý nghĩa |
|---|---|---|
| `evaluation.runs` | Counter | Số run được tạo/kết thúc theo status |
| `evaluation.cases.selected` | Counter/Gauge | Số cases được chọn |
| `evaluation.cases.completed` | Counter | Số cases execution đã kết thúc |
| `evaluation.cases.pending` | Gauge | Số cases còn chờ |
| `evaluation.cases.in_flight` | Gauge | Số cases đang chạy |
| `evaluation.cases.skipped` | Counter | Số cases bị bỏ qua |
| `evaluation.case.duration` | Timer/Histogram | Thời gian một case |
| `evaluation.case.throughput` | Derived rate | Cases hoàn tất trên một đơn vị thời gian |
| `evaluation.batches.completed` | Counter | Số batches hoàn tất |

Đừng chỉ hiển thị `completed / selected`. Cần tách cases đã hoàn tất, skipped, not-run, in-flight và pending. Một run có 90% completed nhưng 10% critical cases chưa chạy có thể chưa đủ điều kiện kết luận.

### 5.2. Queue và worker capacity

| Metric | Type | Dùng để |
|---|---|---|
| `evaluation.queue.depth` | Gauge | Số batches đang chờ |
| `evaluation.queue.wait` | Timer | Thời gian từ enqueue đến claim |
| `evaluation.worker.active` | Gauge | Workers đang xử lý |
| `evaluation.worker.available` | Gauge | Workers sẵn sàng |
| `evaluation.worker.lease_expired` | Counter | Batch lease hết hạn |
| `evaluation.worker.restarts` | Counter | Worker process restart |
| `evaluation.batch.claim.duration` | Timer | Thời gian claim/initialize batch |
| `evaluation.batch.size` | DistributionSummary | Số cases trong batch |

Queue depth tăng liên tục trong khi worker active đạt max thường cho thấy capacity hoặc downstream dependency là bottleneck. Queue depth thấp nhưng throughput thấp có thể do scheduler không dispatch hoặc batches chưa được tạo.

### 5.3. Latency theo stage

Đo duration riêng cho:

- Queue wait.
- Batch claim/setup.
- Retrieval.
- Model generation.
- Tool execution.
- Judge/evaluator.
- Result persistence.
- Aggregation/finalization.

Một case duration lớn có thể đến từ queue wait hoặc provider call. Nếu chỉ có `evaluation.case.duration`, không thể phân biệt nguyên nhân.

### 5.4. Reliability và retry

| Metric | Dimensions gợi ý |
|---|---|
| `evaluation.case.errors` | task type, reason code |
| `evaluation.case.timeouts` | operation, provider alias |
| `evaluation.case.invalid` | output type, validation code |
| `evaluation.case.retries` | dependency, retry reason |
| `evaluation.case.retry_exhausted` | dependency, reason |
| `evaluation.batch.failures` | worker pool, reason |
| `evaluation.run.aborted` | run trigger, abort reason |
| `evaluation.provider.rate_limited` | provider alias, operation |

Không dùng exception message làm label. Chuẩn hóa reason code như `rate_limited`, `connect_timeout`, `read_timeout`, `invalid_schema`, `policy_denied`, `provider_unavailable`.

### 5.5. Quality metrics

Quality metrics phải được tính từ result store, không tính từ sampled traces:

- Verdict counts: PASS/FAIL/INVALID/ERROR.
- Relevance score distribution.
- Groundedness/fact-check score distribution.
- Tool selection and argument validity.
- Abstention correctness.
- Required evidence coverage.
- Per-slice pass rate.

Nếu rubric cho điểm liên tục, lưu score distribution hoặc histogram. Không chỉ lưu pass rate vì hai candidates có thể cùng pass rate nhưng khác mức độ quality.

### 5.6. Token, cost và resource usage

Tách theo role và stage:

| Metric | Role/dimension |
|---|---|
| `evaluation.tokens.input` | candidate, judge, embedding/reranker nếu có |
| `evaluation.tokens.output` | candidate, judge |
| `evaluation.cost` | provider alias, model alias, role, currency |
| `evaluation.model.calls` | provider alias, model alias, role |
| `evaluation.retry.cost` | dependency, retry reason |
| `evaluation.memory` | worker pool |
| `evaluation.cpu` | worker pool |

Cost nên được tính từ usage metadata và pricing snapshot. Nếu chỉ là ước tính, gắn nguồn/độ chính xác trong run report; đừng đặt metric name hàm ý actual billed cost.

### 5.7. Không dùng Gauge thay cho Counter

Quy tắc đơn giản:

- Counter cho sự kiện tích lũy: cases completed, calls, errors, tokens.
- Gauge cho trạng thái hiện tại: queue depth, in-flight, budget remaining.
- Timer/Histogram cho duration và phân phối.
- DistributionSummary cho số lượng hoặc kích thước như batch size/token per case.

Counter có thể reset khi process restart; backend thường xử lý rate qua scrape series. Không cộng các counter process-local một cách thủ công thành giá trị cumulative không chính xác.

## 6. Cardinality và dimension policy

Batch pipeline tạo ra rất nhiều IDs. Nếu đưa ID vào metric tags, số time series có thể tăng theo số cases hoặc runs và làm monitoring backend quá tải.

### 6.1. Dimension được phép

Những dimensions thường có cardinality thấp:

- `environment`: dev/staging/prod.
- `run_type`: pr/nightly/release/manual.
- `feature`: tập feature được kiểm soát.
- `task_type`: rag/tool/direct/structured.
- `operation`: retrieval/generation/judge/persist.
- `provider_alias`: alias cấu hình ổn định.
- `model_alias`: alias có số lượng giới hạn.
- `status`: tập enum hữu hạn.
- `reason_code`: enum đã chuẩn hóa.
- `worker_pool`: tập pool hữu hạn.

### 6.2. Dimension không nên đưa vào metrics

- `run_id`, `batch_id`, `case_id`, `attempt_id`.
- Trace ID/span ID.
- Commit SHA hoặc full config fingerprint.
- Prompt text, user query, answer, document ID.
- Raw model ID do người dùng cung cấp.
- Tool arguments hoặc exception message.

Các giá trị này có thể nằm trong result store hoặc trace attributes theo policy. Tránh đưa chúng vào metric labels.

### 6.3. Ước tính series budget

Giả sử một metric có 3 environments, 4 task types, 5 operations và 6 statuses:

\[
3 \times 4 \times 5 \times 6 = 360
\]

Đây là upper bound từ các dimensions đã liệt kê, chưa tính histogram buckets và các labels khác. Nếu thêm 1.000 case IDs, số series có thể tăng thêm nhiều bậc độ lớn.

### 6.4. Model version và prompt version

Prompt/model versions có thể hữu ích để so sánh quality, nhưng có thể tăng theo mỗi commit. Có ba lựa chọn:

1. Đưa vào run result store và dashboard query theo run.
2. Đưa vào trace attributes cho phép drill-down.
3. Chỉ dùng metric label nếu có bounded alias/approved release channel và series budget.

Không dùng full commit SHA làm label chỉ để lọc một dashboard.

## 7. Thiết kế trace hierarchy cho worker bất đồng bộ

Trace giúp nối các stage của một case. Batch processing lại có nhiều cases và workers song song, nên không nên tạo một root span khổng lồ kéo dài toàn bộ run nếu run tồn tại hàng giờ.

### 7.1. Run span và batch span

Có thể tạo một run span ngắn cho lifecycle control:

```text
evaluation.run.start
  -> validate manifest
  -> create batches
  -> enqueue batches
  -> return run_id

evaluation.batch.process (worker trace)
  -> claim batch
  -> process cases
  -> persist batch summary

evaluation.run.finalize
  -> reconcile expected/completed counts
  -> aggregate quality
  -> persist final summary
```

Run span không cần mở suốt nhiều giờ. Run ID trong manifest/event/result store kết nối các traces độc lập.

### 7.2. Một trace cho một batch hoặc một case?

Lựa chọn tùy thời gian sống và số spans:

| Trace boundary | Ưu điểm | Nhược điểm |
|---|---|---|
| Một trace/run | Dễ thấy toàn bộ run | Rất lớn, kéo dài, dễ vượt limits |
| Một trace/batch | Thấy worker và nhiều cases | Batch quá lớn tạo trace nhiều spans |
| Một trace/case | Dễ drill-down quality/latency | Nhiều traces; cần liên kết bằng run/batch IDs |
| Một trace/attempt | Tách retry rõ | Nhiều trace, phải nối attempt history qua result store |

Một thiết kế thực tế thường dùng trace theo batch hoặc case, với run/batch/case IDs trong attributes và persisted metadata. Với batch rất lớn, tạo trace theo case để tránh trace phình.

### 7.3. Span tree cho một case

```text
evaluation.case
  ├── app.rag.retrieve
  │    ├── retrieval.query_rewrite
  │    └── vector_store.search
  ├── app.ai.model.generate
  │    └── provider.http.request
  ├── app.ai.tool.execute
  │    └── tool.http.client
  ├── evaluation.judge
  │    └── judge.model.generate
  └── evaluation.result.persist
```

Nếu case không dùng tool, không tạo tool span giả chỉ để mọi traces có cùng hình dạng.

### 7.4. Span attributes

Các attributes hữu ích:

| Key | Ví dụ | Lưu ý |
|---|---|---|
| `evaluation.run.type` | nightly | Enum |
| `evaluation.batch.size` | 40 | Numeric |
| `evaluation.task.type` | rag | Enum |
| `evaluation.operation` | judge | Enum |
| `evaluation.attempt` | 2 | Numeric |
| `evaluation.execution.status` | succeeded | Enum |
| `evaluation.quality.verdict` | fail | Chỉ có sau judge |
| `app.ai.prompt.version` | answer-v21 | Theo policy |
| `gen_ai.request.model` | model alias | Dùng convention tương thích |
| `gen_ai.usage.input_tokens` | 1530 | Numeric |
| `gen_ai.usage.output_tokens` | 284 | Numeric |

Không ghi raw input, answer hoặc full evidence vào span attributes. Nếu cần điều tra nội dung, dùng artifact reference opaque có access control.

## 8. Context propagation qua queue và worker

HTTP context không tự động đi qua message broker hoặc job queue. Nếu worker xử lý batch ở process khác, cần inject/extract trace context rõ ràng.

### 8.1. Propagation model

Khi scheduler publish message:

1. Tạo producer span.
2. Inject W3C Trace Context (`traceparent`, `tracestate`) vào message headers nếu dùng W3C propagator.
3. Gửi message cùng opaque run/batch IDs.

Khi worker nhận message:

1. Extract context từ headers.
2. Tạo consumer/process span theo messaging semantic convention phù hợp.
3. Gắn run/batch metadata đã được allowlist.
4. Tạo case spans dưới processing context hoặc dùng span links nếu fan-out lớn.

### 8.2. Parent-child hay span links?

Nếu một batch message được tạo từ một producer span, worker span có thể là child của producer context. Nhưng nếu một worker xử lý nhiều batches hoặc một batch kết hợp nhiều parent contexts, span links có thể biểu diễn quan hệ tốt hơn parent-child đơn.

Không tạo một parent span kéo dài suốt run chỉ để nối mọi worker. Run ID trong result store vẫn là correlation key nghiệp vụ.

### 8.3. Ví dụ inject/extract với OpenTelemetry

```java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.context.propagation.TextMapSetter;
import io.opentelemetry.context.propagation.TextMapGetter;
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.context.Context;

Map<String, String> headers = new HashMap<>();

TextMapSetter<Map<String, String>> setter =
        (carrier, key, value) -> carrier.put(key, value);

openTelemetry.getPropagators()
        .getTextMapPropagator()
        .inject(Context.current(), headers, setter);

// Publish headers with the batch message.

TextMapGetter<Map<String, String>> getter =
        new TextMapGetter<>() {
            @Override
            public Iterable<String> keys(Map<String, String> carrier) {
                return carrier.keySet();
            }

            @Override
            public String get(Map<String, String> carrier, String key) {
                return carrier.get(key);
            }
        };

Context extracted = openTelemetry.getPropagators()
        .getTextMapPropagator()
        .extract(Context.root(), headers, getter);

try (var scope = extracted.makeCurrent()) {
    processBatch(message);
}
```

Đây là skeleton minh họa API OTel; trong Spring Boot có thể inject `OpenTelemetry` và dùng propagator được cấu hình. Nếu dùng Micrometer Tracing bridge, dùng propagation API/observation conventions của bridge để tránh tạo hai context propagation stacks.

### 8.4. Không tin trace headers từ message không đáng tin

Message headers là dữ liệu truyền qua hệ thống. Validate kích thước/format và không dùng trace context làm identity hoặc authorization. Không cho phép client tự chọn trace IDs để truy cập dữ liệu khác.

## 9. Instrumentation với Micrometer Observation trong Spring Boot

Spring Boot và Micrometer Observation cung cấp một điểm instrument chung cho metrics và tracing. Observation có thể tạo Timer/Counter handlers và tracing handlers theo cấu hình application.

### 9.1. Observation cho batch processing

Một custom observation có thể bao quanh mỗi batch:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public final class BatchProcessor {

    private final ObservationRegistry observations;

    public BatchProcessor(ObservationRegistry observations) {
        this.observations = observations;
    }

    public BatchSummary process(Batch batch) {
        return Observation.createNotStarted(
                        "evaluation.batch.process", observations)
                .lowCardinalityKeyValue(
                        "evaluation.task.type", batch.taskType())
                .lowCardinalityKeyValue(
                        "evaluation.worker.pool", batch.workerPool())
                .observe(() -> processBatch(batch));
    }

    private BatchSummary processBatch(Batch batch) {
        // Claim, execute cases, and persist summary.
        return BatchSummary.empty();
    }
}
```

`batch.id` và `run.id` không được đưa vào low-cardinality tags. Nếu cần correlation trong trace, có thể dùng high-cardinality values theo policy hoặc log/result metadata.

### 9.2. Observation cho từng case

```java
public CaseResult evaluate(EvaluationCase testCase) {
    return Observation.createNotStarted(
                    "evaluation.case.execute", observations)
            .lowCardinalityKeyValue(
                    "evaluation.task.type", testCase.taskType())
            .lowCardinalityKeyValue(
                    "evaluation.feature", testCase.feature())
            .observe(() -> evaluateCase(testCase));
}
```

Nếu số cases lớn, trace sampling có thể giảm spans. Metrics handlers vẫn cần giữ counts/durations theo sampling policy của registry. Result persistence phải luôn độc lập với Observation sampling.

### 9.3. Low-cardinality và high-cardinality values

Trong Micrometer Observation:

- Low-cardinality key-values có thể trở thành metric tags và span attributes.
- High-cardinality key-values chủ yếu dành cho tracing, không trở thành metric tags.

Đặt case/run/batch IDs ở high-cardinality context nếu thật sự cần và policy cho phép. Đừng đưa chúng vào low-cardinality key-values.

### 9.4. Error handling

Nếu operation ném exception:

- Để Observation lifecycle kết thúc đúng.
- Đánh dấu error theo handler/convention phù hợp.
- Ghi reason code đã chuẩn hóa.
- Không ghi exception message có thể chứa prompt/tool arguments.
- Persist case execution status theo result contract.

Quality verdict FAIL là kết quả nghiệp vụ; không ném exception chỉ để biến nó thành span ERROR.

### 9.5. Đăng ký Counter, Timer và Gauge cho batch

Observation phù hợp cho operation lifecycle. Một số progress/queue metrics cần được ghi trực tiếp bằng MeterRegistry:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.util.concurrent.BlockingQueue;

public final class BatchMeters {

    private final Counter completedCases;
    private final Counter failedCases;
    private final Timer batchDuration;

    public BatchMeters(
            MeterRegistry registry,
            BlockingQueue<BatchMessage> queue) {

        this.completedCases = Counter.builder(
                        "evaluation.cases.completed")
                .tag("task.type", "rag")
                .register(registry);

        this.failedCases = Counter.builder(
                        "evaluation.cases.failed")
                .tag("task.type", "rag")
                .register(registry);

        this.batchDuration = Timer.builder(
                        "evaluation.batch.process")
                .publishPercentileHistogram()
                .register(registry);

        Gauge.builder(
                        "evaluation.queue.depth",
                        queue,
                        BlockingQueue::size)
                .register(registry);
    }

    public BatchSummary record(Batch batch) {
        return batchDuration.record(() -> {
            BatchSummary summary = process(batch);
            completedCases.increment(summary.completedCount());
            failedCases.increment(summary.failedCount());
            return summary;
        });
    }

    private BatchSummary process(Batch batch) {
        // Execute and persist the batch.
        return BatchSummary.empty();
    }
}
```

Đây là skeleton; thay BatchMessage, BatchSummary và process bằng types của ứng dụng. Queue object phải sống lâu hơn Gauge registration; nếu tạo queue mới liên tục và giữ references trong registry, có thể gây memory leak.

### 9.6. Tránh double-counting metrics

Nếu Observation handler đã tạo Timer cho `evaluation.batch.process`, không đăng ký thêm Timer cùng tên/tags rồi record cùng duration lần nữa. Chọn một owner cho mỗi metric:

- Observation handler sở hữu operation Timer/span.
- MeterRegistry thủ công sở hữu queue depth, progress counters hoặc gauges không gắn với một Observation lifecycle.
- Result store sở hữu quality verdict counts và denominators chuẩn.

Counter completed nên tăng đúng một lần khi case transition sang terminal state hợp lệ. Nếu message bị redeliver, deduplicate state transition trước khi increment; không increment mỗi lần worker nhận message.

## 10. Quan sát batch scheduler và worker pool

Scheduler chịu trách nhiệm chia run thành batches, xếp hàng và phân phối. Worker pool chịu trách nhiệm claim, xử lý và báo kết quả. Instrument cả hai để phân biệt thiếu capacity với downstream chậm.

### 10.1. Batch size là một trade-off

Batch quá nhỏ:

- Tăng số message và scheduler overhead.
- Tăng số lần claim/lease/persist.
- Tạo nhiều traces và events.

Batch quá lớn:

- Một worker giữ nhiều cases lâu hơn.
- Worker crash có thể làm mất nhiều progress chưa checkpoint.
- Một case chậm kéo dài batch completion.
- Retry batch có thể chạy lại nhiều cases đã hoàn tất nếu persistence không idempotent.

Theo dõi `evaluation.batch.size`, batch duration, cases per worker, lease expiry và retry count. Chọn batch size dựa trên case duration distribution và recovery cost, không chỉ theo số lượng cases.

### 10.2. Queue wait và processing time

Định nghĩa:

\[
T_{\text{end-to-end}} =
T_{\text{queue-wait}} +
T_{\text{processing}} +
T_{\text{persist}}
\]

Nếu batch queue wait tăng nhưng processing time ổn, cần tăng capacity hoặc điều chỉnh dispatch. Nếu queue wait ổn nhưng processing tăng, xem provider latency, retries hoặc batch size.

### 10.3. Worker pool metrics

Nên quan sát:

- Active/available worker count.
- Queue depth và oldest message age.
- Batch claim rate và completion rate.
- Worker heartbeat age.
- Lease renew failures/expiry.
- Worker crash/restart count.
- Processing duration theo worker pool.
- Number of cases in-flight.

Oldest message age thường hữu ích hơn queue depth đơn lẻ: queue có thể chỉ vài batches nhưng một batch đã chờ quá lâu.

### 10.4. Worker heartbeat và lease

Worker xử lý batch dài cần heartbeat hoặc lease renewal. Nếu lease hết hạn, scheduler có thể giao batch cho worker khác trong khi worker cũ vẫn đang chạy. Điều này tạo duplicate execution.

Telemetry cần ghi:

- Worker ID opaque hoặc pool identity.
- Lease acquired/renewed/expired.
- Lease duration.
- Heartbeat age.
- Duplicate claim detection.

Worker ID chỉ dùng trong logs/traces hoặc worker diagnostics; tránh biến thành metric label nếu số workers thay đổi liên tục.

### 10.5. Phát hiện worker bị stuck

Một worker có thể còn heartbeat nhưng một case bị treo trong provider call. Dùng operation deadline, case age và stage duration để phát hiện:

- Batch đang RUNNING lâu hơn p99 bình thường.
- Case in-flight vượt deadline.
- Không có span/event progress trong khoảng thời gian dài.
- Provider request pending hoặc retry loop.
- Result persistence bị block.

Alert nên chỉ rõ run/batch reference để operator mở result store và trace tương ứng.

## 11. Checkpoint, retry và idempotency

Batch worker có thể chết giữa chừng. Để resume an toàn, cần biết case nào đã persist result, case nào đang chạy, case nào được retry và attempt nào là final.

### 11.1. Checkpoint theo case

Một checkpoint nên lưu:

- run_id, batch_id, case_id.
- Current case status.
- Last completed stage.
- Attempt number.
- Candidate fingerprint.
- Result/artifact reference nếu đã tạo.
- Lease/worker metadata.
- Updated timestamp và state version.

Checkpoint không nhất thiết chứa raw answer; có thể tham chiếu protected artifact.

### 11.2. Persist result trước khi acknowledge message

Thứ tự xử lý message quan trọng:

1. Claim message/batch.
2. Chạy case.
3. Persist per-case result idempotently.
4. Update checkpoint/state.
5. Acknowledge message hoặc mark case complete.

Nếu acknowledge trước khi persist, worker crash có thể làm mất kết quả. Nếu persist xong nhưng chưa acknowledge, message có thể được redeliver; idempotency key giúp không tạo duplicate result.

### 11.3. Idempotency key

Một result key có thể là:

```text
result_key = (
  run_id,
  case_id,
  candidate_fingerprint,
  rubric_version,
  evaluator_version,
  replicate_id
)
```

Nếu rerun là retry của cùng logical evaluation, giữ cùng key và lưu attempt history riêng. Nếu chủ đích chạy replicate để đo randomness, dùng `replicate_id` khác.

### 11.4. Phân biệt retry ở các cấp

| Retry level | Ví dụ | Telemetry |
|---|---|---|
| Transport retry | HTTP 429/5xx | attempt span/event cho request |
| Model operation retry | Model call timeout, gọi lại model | operation attempt, tokens/cost từng lần |
| Tool retry | Tool service unavailable | tool attempt và side-effect/idempotency key |
| Case retry | Restart cả case từ checkpoint | case attempt number |
| Batch redelivery | Message broker giao lại batch | delivery count/lease owner |

Không gộp tất cả thành một `retry_count`; cần biết retry xảy ra ở layer nào để tính cost và reliability đúng.

### 11.5. Retry có thể tạo side effects

Với tool có side effects:

- Dùng idempotency key ở tool boundary nếu service hỗ trợ.
- Phân biệt timeout trước và sau khi side effect đã commit.
- Không tự động retry operation không idempotent khi outcome unknown.
- Ghi outcome `UNKNOWN` để cần reconciliation.

Một retry có thể tạo hai đơn hàng hoặc hai lần cập nhật nếu tool không idempotent.

### 11.6. Checkpoint và provenance

Không resume case bằng candidate fingerprint khác mà vẫn giữ attempt history như cùng một evaluation. Nếu prompt/model/index/rubric/evaluator thay đổi, tạo run/candidate mới. Checkpoint chỉ resume cùng immutable configuration.

## 12. Cancellation, deadline và resume

Run dài cần hỗ trợ cancel. Cancel không chỉ đổi status run; scheduler phải ngừng dispatch, workers cần dừng ở boundary an toàn và aggregator phải đóng summary với coverage đúng.

### 12.1. Cancellation flow

```text
User / policy requests cancel
          |
          v
Run -> CANCELLING
          |
          +--> Stop creating/enqueueing new batches
          |
          +--> Signal workers
          |       |
          |       +--> Stop before next case
          |       +--> Cancel in-flight calls if supported
          |       +--> Persist current outcome/checkpoint
          |
          v
Reconcile active leases and pending messages
          |
          v
Finalize partial summary
          |
          v
Run -> CANCELLED
```

### 12.2. Cancellation phải cooperative

Một worker không thể luôn hủy provider request đã gửi. Có thể:

- Cancel future/client request nếu SDK hỗ trợ.
- Không bắt đầu case tiếp theo.
- Đánh dấu attempt đang chạy `CANCELLED` hoặc `UNKNOWN` tùy khả năng biết outcome.
- Persist usage nếu response đến sau cancellation.
- Release lease hoặc cho lease expire theo policy.

Không ghi attempt là CANCELLED nếu provider có thể đã xử lý và tính phí mà client không nhận được response.

### 12.3. Deadline theo nhiều cấp

Thiết lập:

- Run deadline.
- Batch deadline.
- Case deadline.
- Operation timeout.
- Per-attempt timeout.

Các deadline phải nhất quán: operation timeout không thể dài hơn phần thời gian còn lại của case; case deadline không thể dài hơn run deadline. Khi deadline gần hết, không dispatch case mới nếu không đủ thời gian hoàn tất theo policy.

### 12.4. Resume semantics

Khi resume:

1. Kiểm tra run chưa final và candidate fingerprint không đổi.
2. Đọc checkpoint/result store.
3. Xác định cases đã persist final result.
4. Kiểm tra lease hết hạn và attempts đang unknown.
5. Requeue cases chưa hoàn tất theo retry policy.
6. Giữ nguyên attempt history và cost đã phát sinh.

Không tính lại các cases đã hoàn tất như mới nếu không chủ đích tạo replicate.

### 12.5. Run budget khi resume

Budget đã tiêu trước khi crash phải được giữ lại. Resume không được cấp lại full budget như một run mới nếu cùng run ID. Lưu budget consumed/reserved trong durable store và reconcile trước khi dispatch tiếp.

## 13. Partial failure và aggregation

Một batch run thường có partial failures. Aggregator phải tổng hợp chính xác mà không làm mất denominator hoặc biến missing results thành PASS.

### 13.1. Tách execution status và quality verdict

Ví dụ result schema:

```json
{
  "case_id": "case-rag-017",
  "execution_status": "SUCCEEDED",
  "quality_verdict": "FAIL",
  "quality_scores": {
    "relevance": 0.92,
    "groundedness": 0.41
  },
  "attempt_count": 1,
  "usage": {
    "input_tokens": 1530,
    "output_tokens": 284
  }
}
```

Một case khác có thể có `execution_status=TIMEOUT` và không có quality verdict. Không gán quality score 0 cho timeout nếu 0 có nghĩa là judge đã chấm và xác định answer hoàn toàn sai; missing/unknown phải có representation riêng.

### 13.2. Denominator rõ ràng

Nên báo cáo các mẫu số riêng:

- Selected: cases được chọn cho run.
- Eligible: cases phải được chạy trong tier.
- Started: cases đã bắt đầu.
- Executed: cases có execution result.
- Judged: cases có quality verdict hợp lệ.
- Completed: cases đạt terminal state.

Ví dụ 100 selected, 100 started, 95 executed, 92 judged, 5 timeout và 3 judge invalid. Pass rate trên 92 judged cases khác với coverage trên 100 selected cases. Report phải hiển thị cả hai.

### 13.3. Aggregate theo slice

Với mỗi slice, báo:

- Selected/executed/judged counts.
- Pass/Fail/Invalid/Error/Timeout counts.
- Mean/median và score distribution.
- Confidence interval hoặc uncertainty.
- Cost/case và latency p50/p95.
- Required evidence coverage.

Không gộp slice nhỏ vào overall average mà không nêu sample size.

### 13.4. Weighted aggregate

Nếu cần một overall score, trọng số phải được định nghĩa trước:

\[
Q_{\text{overall}} = \sum_{s=1}^{k} w_s Q_s,\qquad
\sum_{s=1}^{k} w_s = 1
\]

Trong đó \(Q_s\) là score của slice s và \(w_s\) là trọng số theo product risk/traffic hoặc evaluation policy. Không dùng số cases tự nhiên làm trọng số nếu dataset bị over-represent một feature.

### 13.5. Late results và duplicate events

Một worker có thể gửi result sau khi batch đã retry ở worker khác. Aggregator cần:

- Idempotency key cho result.
- Attempt precedence policy.
- Version/sequence kiểm soát update.
- Quy tắc xử lý late response.
- Audit record khi hai workers cùng hoàn tất một case.

Không chọn kết quả “đến sau cùng” một cách tùy tiện. Dùng attempt state và execution policy để xác định result hợp lệ.

### 13.6. Finalization invariant

Trước khi đánh dấu run final:

1. Mọi batches đã terminal hoặc được mark cancelled/aborted.
2. Selected/eligible/started/executed/judged counts reconciled.
3. Không còn active leases chưa xử lý.
4. Pending messages được xử lý hoặc ghi rõ not-run.
5. Aggregate summary được persist idempotently.
6. Final run status phản ánh partial failures và cancellation.

Nếu không thể reconcile, finalization cần fail rõ ràng thay vì ghi một summary có vẻ đầy đủ.

## 14. Dashboard cho batch evaluation

Dashboard nên được tổ chức theo câu hỏi vận hành, không phải theo danh sách tất cả metrics. Một operator cần biết run có tiến triển, có nghẽn, có vượt budget và có đủ evidence để kết luận hay không.

### 14.1. Run overview

Một trang overview có thể gồm:

- Run status, trigger, start time, elapsed time.
- Candidate fingerprint, dataset/rubric/evaluator versions.
- Selected, eligible, completed, judged, failed, skipped và pending cases.
- Progress percentage và estimated time remaining.
- Total candidate/judge calls, tokens và cost.
- Current queue depth và active workers.
- Quality summary và required slice coverage.
- Link tới batch list, case failures và traces.

Progress percentage nên định nghĩa rõ:

\[
progress = \frac{terminal\_cases}{eligible\_cases}\times100\%
\]

Trong đó terminal cases gồm trạng thái terminal đã quy định. Nếu muốn hiển thị judged coverage, dùng công thức riêng:

\[
judged\_coverage = \frac{judged\_cases}{eligible\_cases}\times100\%
\]

Không dùng một thanh progress để thay cho cả execution completion và quality coverage.

### 14.2. Throughput và ETA

Throughput có thể tính từ số cases terminal trong một cửa sổ thời gian:

\[
throughput = \frac{\Delta completed\_cases}{\Delta time}
\]

ETA đơn giản:

\[
ETA = \frac{remaining\_eligible\_cases}{recent\_throughput}
\]

ETA chỉ là estimate. Nếu throughput thay đổi theo slice hoặc provider rate limits, dùng rolling window và hiển thị uncertainty. Không hiển thị ETA khi throughput bằng 0 hoặc chưa có đủ samples.

### 14.3. Batch/worker dashboard

Các panel hữu ích:

- Queue depth và oldest queued batch age.
- Queue wait p50/p95.
- Active workers so với configured capacity.
- Batch duration p50/p95.
- Cases per batch và cases per worker.
- Lease expirations, duplicate claims, worker restarts.
- Completion rate và error rate theo worker pool.

### 14.4. Stage latency dashboard

Stack hoặc percentile chart cho:

- Queue wait.
- Retrieval.
- Candidate generation.
- Tool execution.
- Judge.
- Persistence.
- Finalization.

Dùng cùng time window và dimensions để so sánh. Nếu judge p95 tăng nhưng candidate generation ổn, không cần điều tra retriever trước.

### 14.5. Quality dashboard

Quality view nên có:

- Overall score và per-slice score.
- Verdict distribution.
- Groundedness/relevance/correctness histograms.
- Critical case pass/fail.
- Evidence coverage.
- Tool selection/argument validity.
- Candidate so với baseline.
- Confidence/uncertainty và sample count.

Hiển thị số cases bên cạnh mọi tỷ lệ. Một slice có 100% pass trên 2 cases không tương đương 100% trên 200 cases.

### 14.6. Cost dashboard

Tách:

- Candidate model cost.
- Judge cost.
- Embedding/reranker cost.
- Tool/dependency cost nếu có.
- Retry cost.
- Cost theo case, batch, feature và run.
- Cost budget used/remaining.
- Token input/output theo role.

Có thể hiển thị top cases theo cost trong run detail, nhưng case IDs nên đến từ result store chứ không làm metric labels.

## 15. Instrument Spring AI evaluation pipeline end-to-end

Một pipeline điển hình có retrieval, generation, tool calling và judge. Mỗi operation cần một observation/span với tên ổn định, cùng run/case context đã được truyền đúng cách.

### 15.1. Flow tham chiếu

```text
BatchScheduler
  -> publish BatchMessage
      -> EvaluationWorker
          -> CaseExecutor
              -> RAG retriever
              -> Spring AI ChatClient / ChatModel
              -> Tool callback (nếu được chọn)
              -> Judge evaluator
              -> ResultRepository
          -> BatchSummaryRepository

RunAggregator
  -> reconcile case states
  -> compute quality/cost/latency summaries
  -> finalize run
```

### 15.2. Tên operation ổn định

Ví dụ tên:

- `evaluation.run.validate`
- `evaluation.batch.process`
- `evaluation.case.execute`
- `app.rag.retrieve`
- `app.ai.model.generate`
- `app.ai.tool.execute`
- `evaluation.judge`
- `evaluation.result.persist`
- `evaluation.run.aggregate`

Không đưa case ID, query hoặc prompt version vào span name. Tên ổn định giúp group/query dễ dàng.

### 15.3. Gắn metadata vào đúng boundary

| Boundary | Metadata phù hợp |
|---|---|
| Run | trigger, dataset version, rubric version, candidate fingerprint |
| Batch | batch size, worker pool, queue name, delivery attempt |
| Case | task type, feature, risk tier, case reference theo privacy policy |
| Model call | provider/model alias, prompt version, token usage |
| Retrieval | strategy, topK, hit count, index version |
| Tool | tool name, allow/deny outcome, duration |
| Judge | rubric, judge alias, verdict, score |
| Persistence | repository operation, rows affected, duration |

Chỉ thêm fields có thể hành động. Tránh lặp cùng một metadata trên mọi spans nếu nó đã có ở parent/resource và không cần thiết để query.

### 15.4. Retrieval instrumentation

Với RAG, ghi:

- Retrieval strategy (semantic, hybrid, keyword).
- topK requested.
- hit count.
- Index/snapshot version.
- Filter category đã chuẩn hóa.
- Retrieval duration.
- Reranker duration/score summary nếu có.

Không ghi raw query, document text hoặc user-supplied filter values. Nếu cần xem document-level evidence, dùng protected artifact reference.

### 15.5. Model instrumentation

Với candidate và judge calls, tách role:

- candidate
- judge
- rewrite
- reranker nếu là model call

Ghi provider/model alias, request duration, usage metadata, finish reason đã chuẩn hóa, retry attempt và error type. Không mặc định token usage có sẵn; nếu provider không trả usage, đánh dấu estimated/unknown.

### 15.6. Tool instrumentation

Một tool operation nên ghi:

- Tool name allowlisted.
- Policy outcome: allowed/denied.
- Execution outcome.
- Duration.
- Retry count.
- Side-effect state nếu cần reconciliation.

Không ghi arguments/results raw. Nếu tool bị policy deny, trace có thể có policy decision span/event nhưng không nên có downstream call span nếu callback không được dispatch.

### 15.7. Judge instrumentation

Judge span cần phân biệt:

- Judge execution status.
- Judge verdict.
- Rubric version.
- Score dimensions.
- Judge model alias.
- Judge tokens/cost/latency.
- Parser/schema validation outcome.

Judge trả verdict FAIL là execution thành công. Judge timeout hoặc invalid schema là execution/evaluator failure, không phải answer quality FAIL.

## 16. Structured logs và correlation

Logs giúp điều tra sự kiện chi tiết, nhưng cần có schema thống nhất để kết nối với metrics/traces và không biến log thành nơi chứa raw payload.

### 16.1. Structured log fields

Một log record có thể có:

```json
{
  "timestamp": "2026-11-27T20:12:18.210Z",
  "level": "INFO",
  "event": "evaluation.case.completed",
  "run_id": "run-2026-11-27-a91f",
  "batch_id": "batch-0042",
  "case_id": "case-rag-017",
  "attempt": 2,
  "worker_pool": "evaluation-default",
  "execution_status": "SUCCEEDED",
  "quality_verdict": "PASS",
  "duration_ms": 1840,
  "trace_id": "opaque-trace-reference"
}
```

Đây là log schema tham chiếu. Không ghi prompt, answer, API key, authorization header, tool arguments hoặc document content.

### 16.2. Correlation fields

Những IDs thường cần trong logs:

- run_id.
- batch_id.
- case_id.
- attempt number.
- worker pool.
- trace_id/span_id nếu tracing được bật.

IDs nên opaque và không chứa customer identifiers. Dùng chúng trong log/result store để tìm records; không đưa chúng vào metric dimensions.

### 16.3. Log event thay vì log từng polling loop

Nên log state transition và boundary:

- batch queued/claimed/completed.
- case started/completed/retry.
- worker lease expired.
- run cancelled/finalized.
- budget exhausted.

Không log mỗi lần worker poll queue hoặc mỗi token chunk nếu không có nhu cầu chẩn đoán cụ thể. Dùng metrics cho tần suất cao và logs cho sự kiện cần giải thích.

### 16.4. Log levels

| Level | Ví dụ |
|---|---|
| DEBUG | Chi tiết scheduler/worker trong môi trường debug |
| INFO | Run/batch/case lifecycle transitions |
| WARN | Retry scheduled, queue lag, partial failure, unknown usage |
| ERROR | Fatal run error, persistence failure, invariant violation |

Một quality verdict FAIL không nhất thiết là application ERROR. Có thể log INFO hoặc WARN theo policy, đồng thời ghi verdict vào result store.

## 17. Cost attribution và reconciliation

Batch evaluation dễ tính thiếu chi phí nếu chỉ tính candidate model. Judge, query rewrite, embedding, reranking và retries đều có thể tạo external calls.

### 17.1. Cost theo role

Cost ledger nên ghi mỗi usage record với:

- run_id, case_id, attempt.
- role: candidate/judge/rewrite/reranker/embedding.
- provider/model alias và revision.
- input/output/cached/reasoning tokens nếu có.
- pricing snapshot/version.
- estimated cost và actual usage source.
- request reference hoặc trace reference.

Ledger có thể dùng run/case IDs vì đây là dữ liệu lưu trữ, không phải metric tags.

### 17.2. Cost formula

Với model có giá input/output khác nhau:

\[
C = \frac{T_{in}}{10^6}P_{in}
  + \frac{T_{out}}{10^6}P_{out}
\]

Nếu có cached input hoặc token categories khác, cộng các thành phần theo pricing contract. Không cộng lại cùng một usage record khi event bị redeliver; dùng unique usage ID/idempotency key.

### 17.3. Actual, estimated và unknown

Phân biệt ba trạng thái:

- `ACTUAL`: usage metadata từ provider hoặc billing source.
- `ESTIMATED`: token/cost ước tính từ tokenizer hoặc historical profile.
- `UNKNOWN`: request có thể đã được provider xử lý nhưng không có usage response.

Không thay `UNKNOWN` bằng 0. Khi run có unknown usage, report phải thể hiện cost uncertainty và có thể cần reserve conservative amount cho budget.

### 17.4. Reconcile cost sau run

Sau run:

1. Cộng usage records idempotently.
2. So internal estimate với provider usage/billing nếu có.
3. Tách candidate/judge/embedding/retry costs.
4. Ghi pricing snapshot.
5. Tính cost per judged case và cost per selected case.
6. Gắn discrepancy reason nếu ledger và provider bill khác nhau.

Provider billing có thể cập nhật trễ. Run summary có thể chứa provisional cost và được reconcile sau, nhưng cần giữ timestamp/source của lần cập nhật.

### 17.5. Cost attribution theo batch và case

Cost theo case cho biết cases nào đắt; cost theo batch giúp phát hiện batch skew; cost theo run giúp kiểm soát tổng budget. Nếu một request phục vụ nhiều cases (ví dụ batch embedding), phân bổ cost theo quy tắc rõ ràng như token count hoặc số items. Ghi rõ allocation method để không hiểu allocation là provider billing trực tiếp.

## 18. Alerting theo triệu chứng và SLO

Alert nên dựa trên triệu chứng ảnh hưởng đến run hoặc release decision, không alert mọi metric thay đổi nhỏ. Một alert tốt cho biết điều kiện, phạm vi, tác động và bước kiểm tra đầu tiên.

### 18.1. Progress stalled

Điều kiện tham chiếu:

- Run ở RUNNING.
- Eligible cases còn lại lớn hơn 0.
- Completed count không tăng trong một khoảng thời gian.
- Queue depth hoặc in-flight state cho biết run chưa kết thúc.

Điều tra:

1. Queue depth và oldest message age.
2. Worker active/heartbeat/lease expiry.
3. Case spans đang mở hoặc stage duration bất thường.
4. Provider rate limits/timeouts.
5. Result persistence errors.

Không alert stalled chỉ vì một run nhỏ không có case trong vài giây; dùng run-specific deadline và expected throughput.

### 18.2. Queue backlog

Alert khi oldest queued batch age hoặc queue wait p95 vượt SLO. Queue depth tăng nhanh có thể là symptom, nhưng queue depth đơn lẻ không nói được message nào đã chờ lâu.

Hành động:

- Kiểm tra worker capacity.
- Kiểm tra provider quotas và downstream latency.
- Kiểm tra batch size và scheduling fairness.
- Xem worker pool có bị một slice chậm chiếm hết slots không.

### 18.3. Error/retry spike

Theo dõi:

- Case execution error rate.
- Provider timeout/429 rate.
- Retry attempts per logical case.
- Retry exhausted count.
- Invalid judge output rate.
- Worker lease expiry/duplicate claim.

Phân nhóm theo provider alias, operation và reason code. Không alert theo raw exception text.

### 18.4. Budget burn rate

Một run có thể tiêu cost nhanh hơn dự kiến vì retry loop hoặc prompt/context dài. Alert khi:

- Cost consumed vượt tỷ lệ thời gian/progress dự kiến.
- Remaining budget thấp trong khi eligible cases còn nhiều.
- Actual usage vượt estimate liên tục.
- Unknown usage tăng.

Ví dụ, nếu run mới hoàn tất 20% cases nhưng đã tiêu 80% cost cap, dừng dispatch mới và điều tra trước khi tiếp tục.

### 18.5. Quality regression

Quality alert nên so candidate với baseline trên cùng dataset/rubric/evaluator version. Tách:

- Hard safety/critical failures.
- Relative score drop.
- Per-slice regression.
- Coverage/evaluator validity.

Không phát alert regression từ một aggregate score nếu candidate và baseline dùng dataset hoặc judge versions không tương thích.

### 18.6. Finalization invariant failure

Alert khi:

- Run finalization không reconcile được counts.
- Có active leases sau khi run final.
- Duplicate final result vượt tolerance.
- Event consumer lag làm progress stale.
- Run ở FINALIZING quá lâu.

Đây là lỗi integrity của evaluation pipeline, có thể làm quality report không đáng tin.

## 19. Runbook điều tra batch evaluation

Runbook giúp operator bắt đầu từ triệu chứng, tìm đúng telemetry và xác định hành động an toàn.

### 19.1. Run không tiến triển

1. Mở run overview và xem state/elapsed time.
2. Kiểm tra pending, in-flight và completed cases.
3. Xem queue oldest age và active workers.
4. Nếu không có worker, kiểm tra scheduler/worker health.
5. Nếu worker active nhưng không progress, mở batch/case traces.
6. Xác định stage bị treo: retrieval, model, tool, judge hay persistence.
7. Dừng dispatch hoặc cancel theo deadline/budget policy nếu cần.

### 19.2. Queue tăng nhưng workers vẫn active

Kiểm tra worker utilization và stage duration. Nếu model provider p95 tăng hoặc 429 nhiều, thêm workers có thể làm tình hình tệ hơn. Hạ concurrency, tôn trọng rate limits và kiểm tra retry amplification trước khi scale.

### 19.3. Cost tăng bất thường

1. So candidate/judge/embedding costs.
2. Kiểm tra token input/output per call.
3. Kiểm tra context size/topK và prompt version.
4. Kiểm tra retry attempts và model fallback.
5. Kiểm tra duplicate event/result/usage records.
6. So pricing snapshot và usage source.

Không sửa aggregate cost bằng cách xóa usage records; sửa deduplication/allocation logic và lưu reconciliation record.

### 19.4. Quality score giảm

1. Xác nhận candidate/baseline dùng cùng dataset/rubric/evaluator.
2. Mở per-slice và per-case regression list.
3. Kiểm tra retrieved evidence và prompt/model versions.
4. Phân biệt execution errors với quality verdicts.
5. Xem judge calibration và invalid output.
6. Tạo reproducer và bổ sung regression case nếu phát hiện behavior mới.

### 19.5. Run có nhiều partial failures

Kiểm tra:

- Error/timeout theo operation.
- Retry exhausted và worker lease expiry.
- Case states còn pending/unknown.
- Queue redelivery/duplicate claims.
- Persistence failures.
- Provider outage hoặc rate limiting.

Nếu coverage không đủ, giữ decision INCONCLUSIVE/COMPLETED_WITH_ERRORS theo contract. Không dùng các cases đã pass để suy ra những cases chưa chạy cũng pass.

### 19.6. Worker crash và resume

1. Xác định worker lease đã hết hạn chưa.
2. Kiểm tra checkpoint và result persistence.
3. Tìm cases đã persist final result.
4. Xác định calls có outcome unknown và usage có thể đã bị tính phí.
5. Requeue chỉ các cases chưa hoàn tất theo policy.
6. Giữ run fingerprint và budget consumed.
7. Kiểm tra duplicate results sau khi resume.

## 20. Privacy, security và retention

Batch evaluation có thể lưu hàng nghìn prompts, answers, retrieved documents và tool results. Observability phải tuân theo data classification và retention policy.

### 20.1. Dữ liệu không nên ghi vào metrics/traces/logs

- Raw user prompt/query.
- Full model answer.
- Retrieved document content.
- Tool arguments và tool results raw.
- API keys, bearer tokens, cookies, auth headers.
- SQL bind values hoặc secrets trong exception messages.
- Customer identifiers hoặc PII.

### 20.2. Dùng allowlist và opaque references

Chỉ ghi attributes đã được phê duyệt:

```text
ALLOWED:
  - evaluation.task.type
  - evaluation.operation
  - evaluation.execution.status
  - evaluation.quality.verdict
  - evaluation.attempt
  - app.ai.prompt.version (bounded policy)
  - gen_ai.request.model (approved alias)

PROTECTED / DO NOT EXPORT:
  - raw.prompt
  - raw.answer
  - retrieved.document.content
  - tool.arguments
  - tool.result
  - authorization
  - cookie
  - customer.email
```

Danh sách này là ví dụ. Thực tế cần review theo data classification, semantic conventions và instrumentation libraries. Một key mới từ dependency upgrade không nên tự động được export.

### 20.3. Artifact reference

Nếu reviewer cần xem nội dung case:

- Lưu artifact trong store có access control.
- Dùng opaque artifact reference trong result record.
- Kiểm tra quyền truy cập khi mở artifact.
- Đặt retention và audit access.
- Không nhúng signed URL lâu hạn vào traces/logs.

### 20.4. Trace context và metadata không phải authorization

Trace ID/run ID chỉ giúp correlation. Không dùng chúng để cấp quyền truy cập artifact, resume run hoặc gọi tool. Mọi thao tác cần authorization độc lập.

### 20.5. Retention theo loại dữ liệu

Có thể áp dụng retention khác nhau:

- Metrics aggregate: thời gian dài hơn để phân tích xu hướng.
- Traces: ngắn hơn, sampling theo policy.
- Per-case result metadata: theo thời gian phục vụ regression/audit.
- Raw prompts/answers/artifacts: ngắn nhất có thể và giới hạn quyền truy cập.

Không giữ raw payload vô thời hạn chỉ vì nó hữu ích khi debug.

## 21. Bài thực hành: instrument một batch evaluation run

**Bối cảnh:** Một evaluation service chạy nightly dataset 1.200 cases cho Spring AI policy assistant. Scheduler chia 30 batches, mỗi batch 40 cases. Tám workers xử lý song song. Mỗi case có thể retrieval, candidate model, tool callback và judge. Team muốn quan sát progress, latency, quality, cost và có thể resume sau worker crash.

### Phần A — Mô hình run và events

1. Tạo run manifest với dataset, prompt, model, index, rubric và evaluator versions.
2. Tạo run/batch/case/attempt IDs opaque.
3. Định nghĩa run/case/attempt state machines.
4. Phát events khi run/batch/case chuyển state.
5. Dùng event ID/sequence để deduplicate và xử lý out-of-order delivery.

### Phần B — Metrics

1. Tạo counters cho selected/completed/error/retry cases.
2. Tạo gauges cho pending/in-flight/queue depth/active workers.
3. Tạo timers cho queue wait, case duration và stage durations.
4. Ghi token/cost theo candidate, judge, embedding và retry.
5. Giữ run/batch/case IDs ngoài metric tags.
6. Tạo dashboard progress, worker, latency, quality và cost.

### Phần C — Tracing

1. Tạo run control span ngắn.
2. Tạo batch processing hoặc case spans theo quy mô.
3. Inject W3C trace context vào message headers.
4. Extract context tại worker và tạo consumer/process span.
5. Instrument retrieval, generation, tool, judge và persistence.
6. Dùng run/batch/case metadata theo privacy policy.

### Phần D — Recovery và aggregation

1. Persist case result trước khi acknowledge message.
2. Tạo checkpoint theo case và candidate fingerprint.
3. Phân biệt transport/model/case/batch retries.
4. Thực hiện cancellation cooperative và giữ budget khi resume.
5. Tính selected/executed/judged/completed denominators.
6. Aggregate per-slice scores và confidence.
7. Chỉ finalize khi mọi counts/leases/messages được reconcile.

### Phần E — Dashboard và runbook

1. Tạo alert progress stalled và queue backlog.
2. Tạo alert provider 429/timeout và retry exhausted.
3. Tạo alert budget burn rate và unknown usage.
4. Tạo alert finalization invariant failure.
5. Thử worker crash ở giữa batch.
6. Resume run và xác minh không duplicate results hoặc cấp lại full budget.
7. Kiểm tra canary values không xuất hiện trong telemetry/artifacts.

### Câu hỏi tự kiểm tra

**1. Vì sao không tạo một root span kéo dài suốt run hàng giờ?**  
Vì trace có thể quá lớn, khó export/query và bị ảnh hưởng bởi worker fan-out. Dùng run metadata cùng các traces ngắn theo batch/case và correlation IDs.

**2. Vì sao cần tách execution status và quality verdict?**  
Judge có thể chạy thành công nhưng chấm FAIL; timeout/invalid judge output thì không có verdict hợp lệ. Hai điều này có ý nghĩa khác nhau.

**3. Có thể đưa case ID vào metric tag để drill-down không?**  
Không nên vì cardinality tăng theo số cases. Dùng result store, logs hoặc trace attributes có policy.

**4. Khi worker persist result rồi crash trước khi acknowledge message, điều gì xảy ra?**  
Message có thể được redeliver. Idempotency key và state version giúp worker thứ hai nhận ra result đã có và không tạo duplicate.

**5. Vì sao phải giữ budget consumed khi resume?**  
Vì provider calls trước crash có thể đã bị tính phí. Cấp lại full budget có thể làm run vượt cap.

**6. Một case timeout có quality score bằng 0 không?**  
Không mặc định. Timeout không có verdict; missing/unknown khác với judge đã chấm score 0.

**7. Khi nào run được final?**  
Khi batches/leases/messages được reconcile, case counts và aggregate được persist idempotently, và status phản ánh đúng partial failures/cancellation.

## 22. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ log run started/finished | Không biết batch nào nghẽn | Metrics progress/queue và traces theo case |
| Một trace khổng lồ cho cả run | Trace quá lớn và kéo dài | Trace theo batch/case, run metadata riêng |
| Đưa run/case IDs vào metric tags | Cardinality explosion | IDs trong result store/log/trace attributes |
| Gộp quality FAIL thành execution ERROR | Sai reliability và quality rates | Hai trường status riêng |
| Chỉ đếm completed cases | Che skipped/not-run/invalid | Tách selected/eligible/executed/judged/terminal |
| Đếm evaluation từ sampled traces | Sai denominator | Result store là source of truth |
| Retry batch không idempotent | Duplicate model calls/results/side effects | Checkpoint và idempotency keys |
| Acknowledge trước khi persist | Mất kết quả khi worker crash | Persist rồi mới acknowledge |
| Resume cấp lại full budget | Cost vượt cap | Durable consumed/reserved budget |
| Dùng exception message làm reason label | Cardinality và privacy leak | Normalized reason codes |
| Chỉ đo case duration | Không thấy queue/provider/judge bottleneck | Stage timers |
| Queue depth đơn lẻ | Không biết batch chờ lâu đến đâu | Oldest message age và queue wait |
| Worker active nghĩa là healthy | Worker có thể bị stuck | Heartbeat, lease, case age và progress |
| Dùng trace context làm authorization | Lỗ hổng truy cập | Authorization độc lập |
| Ghi raw prompt/answer vào traces | Rò rỉ dữ liệu | Allowlist và protected artifact references |
| Finalize khi còn active leases | Late results làm summary sai | Finalization invariants và reconciliation |
| Gộp missing score thành 0 | Làm méo quality distribution | Null/unknown/invalid semantics |
| Không lưu candidate fingerprint | Không tái lập được run | Fingerprint và immutable manifest |

## 23. Ghi nhớ

- **Batch observability** cần nhìn thấy run, batch, case và attempt cùng trạng thái vận hành và quality.
- **Run status** không đồng nghĩa quality verdict; execution outcome và quality verdict phải tách riêng.
- **Event model** mô tả lifecycle/state transitions; result store là nguồn chuẩn cho per-case results và aggregate.
- **Metrics** cần có progress, throughput, queue, worker, stage latency, reliability, quality, tokens và cost.
- **Cardinality policy** giữ run/batch/case/attempt IDs ngoài metric tags.
- **Tracing** nên theo batch hoặc case; run ID kết nối các traces độc lập trong result store.
- **Context propagation** qua queue cần inject/extract W3C trace context; span links phù hợp khi fan-out/fan-in phức tạp.
- **Micrometer Observation** giúp instrument operation thống nhất cho metrics và tracing trong Spring Boot.
- **Checkpoint/idempotency** giúp resume sau worker crash mà không tạo duplicate results hoặc side effects.
- **Cancellation/deadline** cần cooperative handling và không được giả định provider request đã gửi có thể hủy hoàn toàn.
- **Aggregation** phải giữ denominator selected/eligible/executed/judged/completed và phân tích theo slice.
- **Cost ledger** tách candidate/judge/embedding/retry, actual/estimated/unknown usage và pricing snapshot.
- **Dashboards/alerts** tập trung progress stalled, queue backlog, latency stage, retry spike, budget burn và finalization integrity.
- **Privacy** cần allowlist, opaque references, access control và retention riêng cho metrics/traces/results/raw artifacts.

Quan sát pipeline đánh giá theo lô giúp nhóm biết evaluation run đang tiến triển, worker nào bị nghẽn, stage nào làm tăng latency, model/judge nào tiêu cost và slice nào suy giảm quality. Khi run lifecycle, event model, metrics, traces, result store và checkpoint dùng chung semantics, batch evaluation trở nên có thể điều tra và resume an toàn mà không đánh đổi độ chính xác của coverage, cost accounting hoặc dữ liệu nhạy cảm.
