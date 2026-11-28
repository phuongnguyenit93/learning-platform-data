# Thiết kế log có cấu trúc cho ứng dụng Spring AI

Một chatbot Spring AI trả lời sai chính sách. Dashboard cho thấy factual correctness giảm, p95 latency tăng và số lần gọi model cao hơn bình thường. Developer mở log và chỉ thấy những dòng như “Calling model”, “Request failed” hoặc một stack trace dài. Không có run ID để tìm case, không biết prompt version nào được dùng, không thấy retrieval có trả đúng tài liệu hay không, và không thể nối lỗi với trace hoặc evidence đã lưu.

Log hữu ích phải trả lời được **sự kiện nào đã xảy ra, ở bước nào, trong ngữ cảnh nào, với kết quả ra sao và cần mở bằng chứng nào tiếp theo**. Với ứng dụng AI, điều này đòi hỏi log có cấu trúc, correlation IDs nhất quán, event names ổn định và quy tắc bảo vệ dữ liệu rõ ràng.

**Structured logging** ghi mỗi sự kiện thành một record có trường được đặt tên và kiểu dữ liệu xác định, thường được xuất dưới dạng JSON. Hệ thống có thể lọc theo event, stage, provider, status hoặc run ID mà không phải phân tích chuỗi message tự do. Khi kết hợp với metrics, traces và evidence artifacts, log giúp đội phát triển hiểu hành vi của Spring AI qua từng phiên bản prompt, model, RAG pipeline và tool.

Trong module **SPRING_AI_EVALUATION_OBSERVABILITY**, bài học này tập trung thiết kế log cho các luồng ChatClient/ChatModel, retrieval, tool calling và evaluation. Bạn sẽ học cách ghi đủ metadata để điều tra chất lượng và vận hành, đồng thời hạn chế lộ prompt, context, dữ liệu cá nhân, secrets và payload nhạy cảm.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích structured logging khác log chuỗi tự do như thế nào.
2. Thiết kế event schema ổn định cho ứng dụng Spring AI.
3. Liên kết log với run, case, attempt, model call, tool call và trace.
4. Chọn trường phù hợp cho model, retrieval, tool và evaluator events.
5. Phân biệt log, metric, trace và evidence artifact.
6. Dùng SLF4J/Logback để ghi structured fields từ Java.
7. Thiết kế logging policy theo severity, privacy, sampling và retention.
8. Tránh ghi raw prompt, context, tool arguments, credentials và dữ liệu cá nhân.
9. Tạo log an toàn có khả năng drill-down tới evidence refs.
10. Kiểm thử event schema, redaction, correlation và lỗi logging.
11. Điều tra một regression hoặc latency spike bằng structured logs.
12. Đưa logging conventions vào CI và vận hành production.

## 2. Vì sao log chuỗi tự do khó điều tra AI

Một log truyền thống thường ghi message như:

~~~text
2026-05-18 10:15:04 INFO Calling chat model
2026-05-18 10:15:05 WARN Retry request
2026-05-18 10:15:07 INFO Response received
~~~

Các dòng trên cho biết có hoạt động, nhưng thiếu những câu trả lời quan trọng:

- Model/provider nào được gọi?
- Request thuộc evaluation run, case và attempt nào?
- Đây là lần gọi thứ mấy của case?
- Prompt, dataset, pipeline và corpus version nào?
- Retry do 429, timeout hay lỗi khác?
- Response hoàn tất hay bị cắt?
- Có bao nhiêu input/output tokens?
- Có retrieval/tool calls trước hoặc sau không?
- Trace/evidence nào liên quan?

Nếu log message được viết tự do, mỗi developer có thể đặt tên khác nhau như “model call”, “invoke llm”, “chat request” hoặc “calling provider”. Truy vấn cần tìm nhiều biến thể, dashboard khó ổn định và phân tích tự động dễ sai.

### 2.1. Structured log giải quyết điều gì?

Một event JSON có thể trông như sau:

~~~json
{
  "timestamp": "2026-05-18T10:15:04.231Z",
  "level": "INFO",
  "service": "support-assistant",
  "environment": "staging",
  "event.name": "ai.model.call.completed",
  "event.version": 1,
  "run.id": "support-eval-v5",
  "case.id": "POLICY-017",
  "attempt.id": "POLICY-017-attempt-1",
  "model.call.id": "model-call-8f31",
  "ai.provider": "example-provider",
  "ai.model": "chat-model-stable",
  "ai.operation": "chat",
  "duration.ms": 842,
  "usage.input_tokens": 1680,
  "usage.output_tokens": 185,
  "outcome": "SUCCESS",
  "trace.id": "actual-trace-id"
}
~~~

Các trường minh họa. Một log backend có thể đổi cách đặt tên, nhưng event contract phải nhất quán trong toàn ứng dụng.

### 2.2. Log không phải nơi chứa mọi dữ liệu

Structured logging không có nghĩa ghi toàn bộ request/response vào JSON. Một record nên chứa metadata cần cho vận hành và tham chiếu tới evidence store có quyền truy cập. Raw prompt/context hoặc payload nhạy cảm thường cần kho riêng, access control và retention chặt hơn.

## 3. Phân biệt log, metric, trace và evidence

Bốn loại dữ liệu phục vụ các câu hỏi khác nhau.

| Loại | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Log** | Sự kiện gì đã xảy ra? | Model call bị 429 ở attempt 2 |
| **Metric** | Xu hướng/tần suất/giá trị tổng hợp là gì? | Tỷ lệ 429 theo provider trong 5 phút |
| **Trace** | Một request đi qua các thành phần theo thứ tự và thời gian nào? | ChatClient → VectorStore → ChatModel → tool |
| **Evidence** | Nội dung nào chứng minh verdict hoặc hành vi? | Answer, effective context, reference facts, tool result |

Một log báo model call mất 2,4 giây. Histogram metric cho biết p95 của model calls tăng. Trace cho thấy thời gian nằm ở provider span. Evidence cho biết answer của case có thực sự sai hay không.

Không dùng log thay histogram khi cần tính percentile. Không dùng trace thay answer/context evidence. Không dùng metric labels để chứa mọi ID của từng case.

### 3.1. Mối quan hệ giữa bốn loại dữ liệu

~~~mermaid
flowchart TD
    A["Spring AI operation"] --> B["Structured log events"]
    A --> C["Metrics"]
    A --> D["Trace spans"]
    A --> E["Evidence artifacts"]
    B --> F["Search / incident investigation"]
    C --> G["Dashboard / alert"]
    D --> H["Latency / dependency analysis"]
    E --> I["Quality review / audit"]
    F --> J["Correlated diagnosis"]
    G --> J
    H --> J
    I --> J
~~~

## 4. Thiết kế event schema chung

Trước khi viết log ở từng class, thống nhất một envelope chung. Mỗi event có metadata mô tả nguồn và nội dung nghiệp vụ cụ thể.

| Field | Kiểu | Ý nghĩa |
| --- | --- | --- |
| timestamp | ISO-8601 UTC | Thời điểm sự kiện |
| level | string | DEBUG/INFO/WARN/ERROR |
| service.name | string | Tên service |
| deployment.environment | string | dev/test/staging/prod |
| event.name | string | Tên event ổn định |
| event.version | integer | Version của event schema |
| message | string | Mô tả ngắn, không chứa payload nhạy cảm |
| run.id | string | Evaluation run nếu có |
| case.id | string | Case nếu có |
| attempt.id | string | Execution attempt nếu có |
| trace.id | string | Trace ID thực tế nếu có |
| span.id | string | Span ID thực tế nếu có |
| outcome | string | SUCCESS/FAILURE/SKIPPED/UNKNOWN |
| error.code | string | Mã lỗi chuẩn hóa |
| duration.ms | number | Thời lượng nếu có |

### 4.1. Event name phải ổn định

Dùng tên event theo quy ước có cấu trúc:

~~~text
ai.request.accepted
ai.prompt.assembled
ai.retrieval.completed
ai.model.call.started
ai.model.call.completed
ai.model.call.failed
ai.tool.call.requested
ai.tool.call.completed
ai.tool.authorization.denied
ai.evaluation.completed
ai.evaluation.failed
ai.evaluation.run.completed
~~~

Không đặt event name chứa ID hoặc dữ liệu động như model-call-8f31-completed. ID là field riêng.

### 4.2. Event version

Khi thay schema không tương thích, tăng event.version. Ví dụ version 1 ghi duration.ms là số nguyên milliseconds; version 2 chuyển sang duration nanoseconds hoặc thay semantics. Consumer cần biết cách diễn giải.

Không đổi nghĩa một field mà giữ nguyên version. Có thể thêm field optional tương thích, nhưng vẫn cần schema governance.

### 4.3. Field names và types

- Dùng một tên duy nhất cho một ý nghĩa: run.id, không lúc runId, lúc evaluationRun.
- Timestamp dùng UTC, ISO-8601 hoặc epoch theo convention được công bố.
- Duration dùng numeric unit rõ ràng, ví dụ duration.ms.
- Token counts là integer, không phải chuỗi “1680 tokens”.
- Boolean giữ kiểu boolean.
- Unknown/null cần semantics rõ: bỏ field, null hay giá trị trạng thái UNKNOWN.

### 4.4. Không phụ thuộc vào message text

Message nên ngắn và dành cho người đọc. Truy vấn và dashboard phải dựa trên event.name, outcome, error.code, provider, stage và IDs. Đừng parse chuỗi message để quyết định pipeline có thành công hay không.

## 5. Correlation IDs xuyên suốt evaluation run

Một request Spring AI có thể tạo nhiều model calls, retrievals, tool calls và evaluator calls. Muốn điều tra phải giữ quan hệ giữa chúng.

| ID | Phạm vi | Ví dụ |
| --- | --- | --- |
| request.id | Một request vào ứng dụng | req-82 |
| run.id | Một logical evaluation run | support-eval-v5 |
| case.id | Một dataset case | POLICY-017 |
| attempt.id | Một lần thực thi case | POLICY-017-attempt-2 |
| model.call.id | Một model invocation | model-call-8f31 |
| tool.call.id | Một tool invocation | tool-call-a42c |
| evaluation.id | Một lần chấm | eval-judge-v2-781 |
| trace.id | Distributed trace | ID do tracing system cấp |
| span.id | Một span trong trace | ID do tracing system cấp |

### 5.1. Quy tắc truyền ID

- Tạo run.id khi bắt đầu logical evaluation run.
- Mỗi case giữ case.id từ dataset snapshot.
- Mỗi lần execution/retry tạo attempt.id mới.
- Mỗi model/tool/evaluator invocation có ID riêng.
- Trace/span IDs lấy từ tracing context thực tế.
- Event ở stage nào cũng giữ các parent IDs cần thiết.

Không tự tạo trace.id ngẫu nhiên để thay thế OpenTelemetry trace context. Nếu trace không có do sampling hoặc instrumentation gap, ghi trạng thái trace unavailable; vẫn giữ run/case/attempt IDs.

### 5.2. Correlation không có nghĩa mọi ID phải là metric label

Log có thể tìm kiếm theo case/attempt ID. Metrics backend không nên tạo time series riêng cho mỗi case. Trace attributes cũng cần tuân thủ cardinality và privacy policy.

### 5.3. Correlation qua async/thread boundaries

MDC thường gắn với thread. Khi dùng executor, CompletableFuture, reactive pipeline hoặc streaming callback, context có thể không tự truyền qua thread khác. Dùng context propagation được framework/Micrometer/OpenTelemetry hỗ trợ; nếu cần, capture các IDs nghiệp vụ rồi khôi phục context trong task. Không giả định MDC ở thread khởi tạo sẽ luôn tồn tại trong callback.

## 6. Phân loại event theo stage của Spring AI

Một taxonomy thống nhất giúp điều tra theo pipeline.

| Stage | Event | Trường đặc thù |
| --- | --- | --- |
| Request intake | ai.request.accepted | request ID, suite, case |
| Prompt assembly | ai.prompt.assembled | prompt version/digest, message count |
| Retrieval | ai.retrieval.completed | corpus/index, top-k, result count, duration |
| Model | ai.model.call.completed | provider/model, usage, finish reason |
| Tool | ai.tool.call.completed | tool name/schema, authorization, duration |
| Evaluation | ai.evaluation.completed | metric, verdict, rubric/judge version |
| Run summary | ai.evaluation.run.completed | counts, coverage, report ref |
| Failure | ai.stage.failed | stage, error code, retryability |

### 6.1. Event lifecycle

Một stage có thể ghi started, completed hoặc failed. Chọn mức chi tiết phù hợp với nhu cầu điều tra và volume. Với stage rất ngắn, một completion event có duration có thể đủ. Với operation dài hoặc streaming, start/end event hữu ích để xác định task bị treo.

Không ghi completed nếu chỉ nhận được HTTP response nhưng chưa validate schema hoặc chưa persist evidence. Định nghĩa rõ điểm mà stage được xem là hoàn tất.

### 6.2. Business outcome và technical outcome

Một tool authorization bị DENY có thể là business/security outcome mong đợi. Provider timeout là technical failure. Model trả câu trả lời sai là quality failure. Tách các trường:

- execution.status: trạng thái chạy.
- quality.status: verdict chất lượng.
- authorization.decision: ALLOW/DENY.
- error.code: lỗi kỹ thuật nếu có.

Đừng gộp tất cả vào success=false.

## 7. Logging cho prompt và context assembly

Prompt là dữ liệu nhạy cảm và có thể chứa user content, policy, business secrets hoặc dữ liệu được truy xuất. Mặc định không ghi toàn bộ rendered prompt vào application log.

Một event prompt assembly có thể chứa:

~~~json
{
  "event.name": "ai.prompt.assembled",
  "event.version": 1,
  "run.id": "support-eval-v5",
  "case.id": "POLICY-017",
  "attempt.id": "POLICY-017-attempt-1",
  "prompt.template.version": "support-prompt-v7",
  "prompt.template.digest": "sha256:...",
  "prompt.message.count": 3,
  "prompt.input.token_estimate": 1680,
  "prompt.content.status": "NOT_LOGGED",
  "prompt.evidence.ref": "secure://evidence/rendered-prompt/8f31",
  "outcome": "SUCCESS"
}
~~~

### 7.1. Template version và rendered prompt

Lưu template version/digest không cho biết model đã thực sự nhận nội dung gì. Rendered prompt có thể khác vì variables, advisors, memory, query rewrite, tool definitions và truncation.

Nếu cần review rendered prompt, lưu secure evidence artifact với quyền riêng. Log chỉ chứa reference/digest và trạng thái capture. Nếu policy cấm cả rendered prompt, không tạo artifact; ghi NOT_CAPTURED và giải thích giới hạn.

### 7.2. Không ghi prompt bằng debug mặc định

Một dòng logger.debug với toàn bộ prompt có thể bị bật ở production khi cần điều tra và vô tình đẩy raw content vào log sink. Không dựa vào log level để bảo vệ dữ liệu. Hãy dùng allowlist metadata và explicit evidence capture policy.

### 7.3. Tránh prompt injection qua log viewer

User input có thể chứa newline, ANSI escape, JSON fragments hoặc chuỗi giống log header. Structured encoder giúp tách field, nhưng message/raw fields vẫn phải được serialize an toàn. Không ghép user input trực tiếp vào multi-line message hoặc terminal control sequence.

## 8. Logging cho RAG retrieval và context

Retrieval event nên giúp trả lời retriever đã chạy với cấu hình nào, trả về bao nhiêu kết quả, mất bao lâu và evidence nằm ở đâu.

Ví dụ:

~~~json
{
  "event.name": "ai.retrieval.completed",
  "event.version": 1,
  "run.id": "support-eval-v5",
  "case.id": "POLICY-017",
  "attempt.id": "POLICY-017-attempt-1",
  "retrieval.id": "retrieval-31",
  "rag.corpus.version": "policy-v3",
  "rag.index.version": "policy-index-v3",
  "rag.embedding.model": "embedding-v2",
  "rag.top_k": 5,
  "rag.result.count": 5,
  "rag.selected.chunk_count": 2,
  "rag.filter.version": "filter-v3",
  "duration.ms": 46,
  "evidence.retrieval.ref": "secure://evidence/retrieval/31",
  "outcome": "SUCCESS"
}
~~~

### 8.1. Retrieved count không phải selected count

Retriever có thể trả 5 chunks nhưng reranker/filter chỉ chọn 2; context assembler có thể tiếp tục cắt. Ghi riêng:

- rag.result.count
- rag.selected.chunk_count
- rag.context.chunk_count
- rag.context.truncated

Không suy effective context từ retrieved count.

### 8.2. Có nên log document IDs?

Document IDs có thể hữu ích khi điều tra, nhưng cũng có thể tiết lộ tenant, chủ đề, mã hợp đồng hoặc dữ liệu nội bộ. Đánh giá sensitivity và cardinality. Có thể log số lượng, rank summary, pseudonymous IDs hoặc evidence ref; raw chunk text không nên xuất hiện trong log mặc định.

### 8.3. Retrieval failure và empty result

Không gộp EMPTY_RESULT với VECTOR_STORE_ERROR. Empty result có thể là kết quả hợp lệ của query; error là thao tác không hoàn thành. Ghi outcome, result.count, error.code và stage riêng.

## 9. Logging cho model calls

Model call thường là nơi phát sinh latency và cost lớn. Log cần đủ metadata để so sánh provider/model mà không chứa raw request/response.

Ví dụ:

~~~json
{
  "event.name": "ai.model.call.completed",
  "event.version": 1,
  "run.id": "support-eval-v5",
  "case.id": "POLICY-017",
  "attempt.id": "POLICY-017-attempt-1",
  "model.call.id": "model-call-8f31",
  "ai.provider": "example-provider",
  "ai.model.requested": "chat-model-stable",
  "ai.model.resolved": "model-revision-if-exposed",
  "ai.operation": "chat",
  "ai.temperature": 0,
  "ai.max_output_tokens": 800,
  "usage.input_tokens": 1680,
  "usage.output_tokens": 185,
  "finish.reason": "STOP",
  "duration.ms": 842,
  "retry.count": 0,
  "response.content.status": "STORED_AS_EVIDENCE",
  "response.evidence.ref": "secure://evidence/answer/8f31",
  "outcome": "SUCCESS"
}
~~~

### 9.1. Những field hữu ích

- Provider và requested/resolved model IDs nếu có.
- Operation type: chat, embedding, rerank hoặc operation khác.
- Parameters quan trọng: temperature, max output tokens, response format.
- Duration, finish reason, usage.
- Retry count và error code.
- Request/provider correlation ID nếu an toàn.
- Prompt/response evidence refs thay vì raw content.

### 9.2. Usage có thể thiếu

Không phải provider nào cũng trả usage cho mọi response, đặc biệt streaming hoặc timeout. Dùng usage.status=AVAILABLE/NOT_PROVIDED/UNKNOWN và không tự gán token bằng 0. Token estimate trước call phải có field riêng với provider-reported usage.

### 9.3. Không log từng token streaming

Log mỗi token hoặc chunk có thể tạo volume rất lớn và vô tình lưu toàn bộ output. Thay vào đó, ghi lifecycle event, time-to-first-token, chunk count, total duration, finish reason và evidence reference theo policy.

## 10. Logging cho tool calling

Tool logs phải thể hiện model đã đề xuất gì, ứng dụng validate/authorize ra sao và backend thực thi kết quả nào.

~~~json
{
  "event.name": "ai.tool.call.completed",
  "event.version": 1,
  "run.id": "support-eval-v5",
  "case.id": "ORDER-004",
  "attempt.id": "ORDER-004-attempt-1",
  "tool.call.id": "tool-call-a42c",
  "tool.name": "getOrderStatus",
  "tool.schema.version": "support-tools-v4",
  "tool.arguments.status": "REDACTED",
  "tool.validation": "VALID",
  "tool.authorization": "DENY",
  "tool.authorization.reason": "ORDER_NOT_OWNED_BY_USER",
  "tool.execution.status": "DENIED",
  "tool.result.ref": "secure://evidence/tool-result/a42c",
  "duration.ms": 38,
  "outcome": "EXPECTED_DENIAL"
}
~~~

### 10.1. Arguments phải được allowlist

Không log toàn bộ tool arguments bằng cách gọi toString(). Một tool có thể nhận email, access token, account number, payment details hoặc nội dung người dùng. Chỉ log trường đã được phê duyệt, hoặc trạng thái redacted cùng secure evidence ref.

### 10.2. Authorization decision là dữ liệu quan trọng

Log ALLOW/DENY, policy version và reason code chuẩn hóa. Không log toàn bộ policy input hoặc secret. Điều này giúp phân biệt model chọn sai tool với backend đã từ chối đúng.

### 10.3. Side effects cần operation correlation

Với tool tạo đơn, hoàn tiền hoặc gửi email, lưu business operation ID/idempotency reference đã pseudonymize. Nếu timeout tạo unknown outcome, log trạng thái đó và reconciliation event; không ghi FAILED nếu chưa biết backend đã commit hay chưa.

## 11. Logging cho evaluator và evaluation run

Evaluation log cần liên kết verdict với rubric, judge và evidence refs. Không chỉ ghi score=0.8.

Ví dụ:

~~~json
{
  "event.name": "ai.evaluation.completed",
  "event.version": 1,
  "run.id": "support-eval-v5",
  "case.id": "POLICY-017",
  "attempt.id": "POLICY-017-attempt-1",
  "evaluation.id": "eval-judge-v2-781",
  "metric.name": "factualCorrectness",
  "metric.status": "FAIL",
  "metric.score": 0.25,
  "rubric.version": "support-rubric-v3",
  "judge.model": "judge-model-v2",
  "judge.prompt.version": "fact-check-v4",
  "evidence.answer.ref": "secure://evidence/answer/8f31",
  "evidence.context.ref": "secure://evidence/context/31",
  "evidence.reference.ref": "artifact://policy/policy-v3/refund-pro",
  "feedback.status": "REDACTED",
  "outcome": "QUALITY_FAIL"
}
~~~

### 11.1. Tách execution status và quality status

Một evaluator có thể hoàn thành thành công nhưng verdict là FAIL. Đây không phải lỗi kỹ thuật. Ghi riêng execution.status=COMPLETED và quality.status=FAIL, hoặc schema tương đương.

Nếu judge timeout, ghi evaluation error/NOT_EVALUATED. Không ghi quality FAIL nếu chưa có verdict.

### 11.2. Aggregate run summary

Run completion event nên ghi counts đã định nghĩa: selected, completed, pass, fail, not evaluated, technical error, skipped, coverage, duration và report ref. Ghi numerator/denominator policy hoặc aggregation version để không hiểu sai tỷ lệ.

Không log danh sách hàng nghìn case IDs vào một event; lưu report artifact ref và query/index phù hợp.

## 12. Error logging và exception taxonomy

Log lỗi phải đủ để phân loại và điều tra, nhưng không được dump toàn bộ exception payload một cách thiếu kiểm soát.

Một error event nên có:

- event.name và stage.
- error.type (class/category đã chuẩn hóa).
- error.code ổn định.
- error.retryable boolean hoặc trạng thái.
- error.message.safe đã sanitize.
- attempt.number và retry budget còn lại nếu phù hợp.
- duration.ms, provider/model/tool.
- Trace/correlation IDs.
- Stack trace ở nơi phù hợp và theo retention/access policy.

### 12.1. Phân loại lỗi

| Nhóm | Ví dụ | Log level gợi ý |
| --- | --- | --- |
| Input validation | Schema/input không hợp lệ | WARN |
| Expected business denial | Tool authorization DENY đúng policy | INFO |
| Quality failure | Answer factual FAIL | WARN/INFO theo severity |
| Transient dependency | 429/503/temporary timeout | WARN |
| Retry exhausted | Đã hết retry budget | ERROR |
| Configuration/security | Credential thiếu, permission misconfigured | ERROR |
| Persistence/integrity | Evidence không ghi được/digest mismatch | ERROR |
| Cancellation | Run bị hủy theo yêu cầu | INFO/WARN |

Level là guideline; policy của service quyết định. Không phát ERROR cho mọi case quality FAIL nếu đây là kết quả kiểm thử bình thường trong batch lớn. Summary/gate sẽ đánh giá chất lượng; error log nên tập trung vào sự cố thực thi.

### 12.2. Không log exception message nguyên trạng nếu có thể chứa secrets

SDK exception có thể chứa URL query, request headers, body hoặc input. Chuẩn hóa error code/type; message hiển thị phải qua sanitizer. Stack trace có thể cần giữ trong sink hạn chế, nhưng phải kiểm tra thư viện có nhúng payload nhạy cảm hay không.

### 12.3. Retry events cần có parent correlation

Mỗi retry ghi attempt number, error code, backoff duration, provider, call ID và parent case attempt. Không ghi API key, raw header hoặc full request.

## 13. Logging an toàn: dữ liệu nào không được ghi mặc định

AI request có thể chứa nội dung người dùng, tài liệu nội bộ, dữ liệu cá nhân, secrets hoặc kết quả tool. Một log tập trung có thể được nhiều hệ thống và nhóm truy cập; vì vậy log thường phải tối giản hơn evidence store.

| Dữ liệu | Chính sách mặc định |
| --- | --- |
| API keys, bearer tokens, passwords | Không ghi |
| Authorization/Cookie headers | Không ghi |
| Raw prompt và conversation history | Không ghi mặc định |
| Raw retrieved chunks/context | Không ghi mặc định |
| Full model response | Lưu evidence có quyền nếu được phép |
| Tool arguments | Allowlist/sanitize hoặc secure ref |
| Email, phone, account identifiers | Redact/pseudonymize |
| Document IDs | Đánh giá sensitivity; có thể pseudonymize |
| Model/provider/version | Có thể ghi nếu không nhạy cảm |
| Token counts/latency/status | Thường có thể ghi |
| Evidence refs | Chỉ ghi opaque refs, không phải bearer URLs |

### 13.1. Allowlist tốt hơn blocklist

Blocklist cố xóa một số trường nhạy cảm nhưng dễ bỏ sót field mới. Allowlist chỉ xuất các trường đã được duyệt cho event đó. Ví dụ model event chỉ nhận provider, model, token counts, duration, status và evidence ref.

### 13.2. Redaction trước khi serialize

Thứ tự đúng:

1. Tạo event object từ trường đã được phê duyệt.
2. Chuẩn hóa/sanitize các giá trị được phép.
3. Áp redaction/pseudonymization.
4. Serialize thành JSON.
5. Gửi tới sink.

Không serialize raw payload rồi hy vọng pipeline downstream xóa hết secrets. Một bản copy có thể đã được gửi tới collector trước redaction.

### 13.3. Redaction không chỉ là regex

Regex có thể bỏ sót token có định dạng mới hoặc nhầm dữ liệu bình thường. Dùng typed fields, schema allowlist và secret detection ở boundary. Pseudonymization phải dùng secret/key được quản lý an toàn; không dùng hash thường của email/phone làm định danh nếu có thể brute-force.

### 13.4. Log injection

Serialize field theo JSON encoder chuẩn. Không nối chuỗi user input vào prefix/suffix log; loại bỏ hoặc encode control characters nếu message được render ở terminal. Không để input tạo dòng log giả hoặc markup thực thi trong viewer.

## 14. SLF4J: ghi structured fields từ Java

Với SLF4J 2.x, fluent logging API cho phép thêm key-value pairs. Encoder/backend phải được cấu hình để xuất các key-value này thành JSON fields.

Ví dụ:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class ModelCallLogger {

    private static final Logger log =
            LoggerFactory.getLogger(ModelCallLogger.class);

    public void completed(
            String runId,
            String caseId,
            String attemptId,
            String modelCallId,
            String provider,
            String model,
            long durationMs,
            Integer inputTokens,
            Integer outputTokens,
            String outcome) {

        var event = log.atInfo()
                .addKeyValue("event.name", "ai.model.call.completed")
                .addKeyValue("event.version", 1)
                .addKeyValue("run.id", runId)
                .addKeyValue("case.id", caseId)
                .addKeyValue("attempt.id", attemptId)
                .addKeyValue("model.call.id", modelCallId)
                .addKeyValue("ai.provider", provider)
                .addKeyValue("ai.model", model)
                .addKeyValue("duration.ms", durationMs)
                .addKeyValue("outcome", outcome);

        if (inputTokens != null) {
            event.addKeyValue("usage.input_tokens", inputTokens);
        }
        if (outputTokens != null) {
            event.addKeyValue("usage.output_tokens", outputTokens);
        }

        event.log("AI model call completed");
    }
}
~~~

### 14.1. Vì sao token fields nullable?

Nếu provider không trả usage, null hoặc NOT_PROVIDED thể hiện thiếu dữ liệu. Không truyền 0 vì 0 có nghĩa usage thực sự bằng không. Chọn một convention thống nhất cho schema.

### 14.2. Không đưa payload vào message

Tránh:

~~~java
log.info("Model request: {}", request);
log.debug("Model response: {}", response);
~~~

Dùng event logger nhận metadata đã được allowlist. Nếu cần raw evidence, ghi qua evidence service có access control, rồi log artifact ref.

### 14.3. Helper logger không nên nuốt lỗi ứng dụng

Logging failure không nên làm mất business operation nếu policy cho phép fallback, nhưng cũng không nên âm thầm bỏ qua audit-critical event. Phân biệt operational log best-effort với audit event cần durability. Với audit-critical records, dùng durable event/outbox mechanism thay vì trông chờ một dòng application log.

## 15. MDC và correlation context

MDC (Mapped Diagnostic Context) giúp gắn một số trường vào các log events trong một scope, ví dụ request ID hoặc run ID.

Ví dụ đồng bộ:

~~~java
import org.slf4j.MDC;

public final class EvaluationCaseRunner {

    public void runCase(
            String runId,
            String caseId,
            String attemptId) {

        try (var run = MDC.putCloseable("run.id", runId);
             var testCase = MDC.putCloseable("case.id", caseId);
             var attempt = MDC.putCloseable("attempt.id", attemptId)) {

            // Các log trong scope có thể nhận correlation fields.
            processCase(caseId);
        }
    }

    private void processCase(String caseId) {
        // Retrieval, model call, tool và evaluation.
    }
}
~~~

Đây là ví dụ scope đơn giản. Với nested MDC keys có giá trị cũ cần khôi phục, kiểm tra semantics của SLF4J version hoặc tự capture/restore context rõ ràng.

### 15.1. MDC không tự truyền qua mọi thread

Khi task chuyển qua executor hoặc reactive scheduler, MDC có thể mất. Không khắc phục bằng cách dùng InheritableThreadLocal một cách tùy tiện; thread pool tái sử dụng thread và có thể rò context giữa requests.

Dùng context propagation được hỗ trợ bởi Micrometer Context Propagation/OpenTelemetry hoặc wrapper executor capture/restore. Test bằng cách thực sự đổi thread và xác nhận context không bị thiếu hoặc trộn.

### 15.2. Dọn context sau mỗi request

Context cũ sót lại có thể gắn nhầm case ID vào log của request tiếp theo. Luôn dùng scope/try-finally hoặc context snapshot restore. Không chỉ put mà quên remove.

### 15.3. Trace context và MDC

Trace ID/span ID thường được bridge vào MDC bởi instrumentation/configuration. Không tự copy một trace ID giả. Kiểm tra logger pattern/JSON encoder đã xuất các trường trace correlation đúng tên và đúng format.

## 16. Logback và JSON output

Một logger có key-value pairs chỉ hữu ích nếu backend xuất chúng thành field có cấu trúc. Nếu backend chỉ nối chúng vào chuỗi message, lợi ích truy vấn bị giảm.

Một lựa chọn phổ biến là Logback kết hợp JSON encoder. Ví dụ cấu hình minh họa với Logstash Logback Encoder:

~~~xml
<configuration>
    <appender name="JSON_CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
    </appender>

    <logger name="com.example.ai" level="INFO"/>

    <root level="INFO">
        <appender-ref ref="JSON_CONSOLE"/>
    </root>
</configuration>
~~~

Thư viện encoder cần được thêm theo dependency management của dự án. Cấu hình thực tế nên đặt trong logback-spring.xml nếu cần Spring profile/property resolution.

### 16.1. Kiểm tra JSON output thật

Không chỉ đọc XML và kết luận đã có structured logging. Chạy một event thử và xác nhận output là một JSON object, event.name là field riêng, duration/token giữ kiểu số và MDC fields được xuất đúng.

### 16.2. Spring Boot structured logging

Một số phiên bản Spring Boot mới hỗ trợ structured logging format tích hợp. Khả năng và property names phụ thuộc phiên bản. Kiểm tra tài liệu của đúng Spring Boot version trước khi dùng. Không cấu hình đồng thời nhiều encoder khiến một event bị serialize lồng hoặc field bị nhân đôi.

### 16.3. Không log ra console production mà không có collector policy

Console JSON thường được container platform thu thập, nhưng cần xác định retention, access, transport encryption, parsing failure và backpressure. Local development có thể dùng console; production cần sink/collector được quản trị.

## 17. Sampling, volume và chi phí logging

Một evaluation run có hàng nghìn cases; mỗi case có retrieval, model, tool và evaluator events. Ghi mọi event ở DEBUG cùng payload có thể tạo volume lớn và tăng chi phí lưu trữ/index.

### 17.1. Chọn event theo nhu cầu

| Event | Chính sách gợi ý |
| --- | --- |
| Run started/completed | Luôn ghi |
| Case completed/failed | Ghi summary theo case hoặc report store |
| Model call success | Ghi metadata; sampling theo traffic nếu volume cao |
| Model call failure | Ghi đủ để điều tra, có rate limiting |
| Retry event | Ghi attempt/reason, có thể aggregate khi burst |
| Prompt/context raw | Không ghi mặc định |
| Security/authorization denial | Ghi theo audit/security policy |
| DEBUG internal details | Chỉ bật có thời hạn và scope |

### 17.2. Không sampling mất audit-critical events

Sampling log thành công có thể giảm volume; nhưng audit/security events, release decisions, critical failures và durable evaluation outcomes có thể cần ghi đầy đủ. Định nghĩa rõ event nào được sample, event nào bắt buộc.

### 17.3. Rate limiting và suppression

Khi provider trả 429 hàng nghìn lần, log một stack trace đầy đủ cho mỗi request có thể làm hệ thống log quá tải. Có thể rate-limit repeated detail logs, nhưng vẫn cần counter/metric và summary event để không che quy mô sự cố.

Ghi suppressed.count hoặc summary theo cửa sổ thời gian nếu áp dụng suppression. Không để suppression xóa mất first occurrence, recovery event hoặc tổng số lỗi.

### 17.4. Log sampling khác trace sampling

Một trace có thể bị drop trong khi error log vẫn được ghi. Một success log có thể bị sample trong khi metrics vẫn đếm đầy đủ. Ghi rõ sampling policy và không suy rằng thiếu log có nghĩa sự kiện không xảy ra.

## 18. Retention, access control và audit

Log thường được sao chép sang collector, search index, archive và backup. Một khi dữ liệu nhạy cảm đã vào log, việc xóa hết bản sao rất khó.

### 18.1. Tách lớp log

- Application operational logs: phục vụ debug/operation, retention theo nhu cầu.
- Security/audit logs: ghi authorization, policy changes, access và release decisions.
- Evaluation evidence: lưu answer/context/reference có quyền riêng.
- Metrics/traces: retention và sampling theo observability backend.

Không ép mọi loại dữ liệu vào cùng một index và cùng quyền truy cập.

### 18.2. Access control

Giới hạn ai có thể tìm log theo environment/tenant và ai được mở evidence refs. Một log có artifact reference không được biến thành bearer URL có thể truy cập vô thời hạn.

### 18.3. Retention và xóa dữ liệu

Xác định retention theo mục đích và sensitivity. Khi evidence hết hạn, log có thể giữ metadata tối thiểu hợp lệ với trạng thái EXPIRED; không giữ raw content hoặc digest/ref nhằm né yêu cầu xóa. Nếu có legal hold/audit retention, phải theo policy được phê duyệt.

### 18.4. Clock và timestamp

Dùng UTC, đồng bộ clock của host/container và lưu event timestamp cùng ingestion timestamp nếu pipeline có thể trễ. Chênh lệch clock giữa services có thể làm thứ tự event nhìn sai. Trace spans có thể giúp phân tích quan hệ parent-child nhưng không sửa được mọi clock skew.

## 19. Log schema và contract testing

Logging là một phần của interface vận hành. Nếu field names thay đổi âm thầm, dashboard và alert có thể hỏng mà unit tests vẫn xanh.

### 19.1. Schema registry hoặc JSON Schema

Có thể định nghĩa JSON Schema cho từng event type. Ví dụ rút gọn:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "AiModelCallCompleted",
  "type": "object",
  "required": [
    "timestamp",
    "level",
    "event.name",
    "event.version",
    "ai.provider",
    "ai.model",
    "duration.ms",
    "outcome"
  ],
  "properties": {
    "event.name": {
      "const": "ai.model.call.completed"
    },
    "event.version": {
      "type": "integer",
      "const": 1
    },
    "ai.provider": {
      "type": "string",
      "minLength": 1
    },
    "ai.model": {
      "type": "string",
      "minLength": 1
    },
    "duration.ms": {
      "type": "number",
      "minimum": 0
    },
    "usage.input_tokens": {
      "type": "integer",
      "minimum": 0
    },
    "usage.output_tokens": {
      "type": "integer",
      "minimum": 0
    },
    "outcome": {
      "enum": ["SUCCESS", "FAILURE", "UNKNOWN"]
    }
  },
  "additionalProperties": true
}
~~~

JSON Schema cho phép key có dấu chấm, nhưng trong Java map/object model có thể cần quy ước mapping. Tổ chức có thể chọn nested objects thay cho dotted keys; điều quan trọng là giữ contract thống nhất.

### 19.2. Kiểm tra required fields và types

Một test cần xác nhận:

- Event name/version đúng.
- Timestamp parse được.
- Duration và token counts là số.
- Outcome thuộc enum.
- IDs được gắn đúng case/attempt.
- Secret/raw content không xuất hiện.
- Evidence refs có format được chấp nhận.

### 19.3. Kiểm tra backward compatibility

Consumer có thể phụ thuộc field names. Thêm field optional thường ít rủi ro hơn đổi tên hoặc đổi type. Khi breaking change, tăng event version và hỗ trợ migration trong consumer.

## 20. Java: tạo event record có allowlist

Thay vì truyền một request object lớn vào logger, tạo event DTO chỉ chứa field đã được duyệt.

~~~java
import java.time.Instant;
import java.util.Objects;

public record ModelCallCompletedEvent(
        Instant timestamp,
        String eventName,
        int eventVersion,
        String runId,
        String caseId,
        String attemptId,
        String modelCallId,
        String provider,
        String model,
        long durationMs,
        Integer inputTokens,
        Integer outputTokens,
        String outcome,
        String evidenceRef) {

    public ModelCallCompletedEvent {
        Objects.requireNonNull(timestamp);
        Objects.requireNonNull(eventName);
        Objects.requireNonNull(provider);
        Objects.requireNonNull(model);
        Objects.requireNonNull(outcome);

        if (durationMs < 0) {
            throw new IllegalArgumentException("durationMs must be >= 0");
        }
        if (inputTokens != null && inputTokens < 0) {
            throw new IllegalArgumentException("inputTokens must be >= 0");
        }
        if (outputTokens != null && outputTokens < 0) {
            throw new IllegalArgumentException("outputTokens must be >= 0");
        }
    }
}
~~~

DTO này không có prompt, answer, headers hoặc tool arguments. Đây là allowlist ở cấp kiểu dữ liệu. Thêm field nhạy cảm cần review schema/privacy trước khi thay đổi.

### 20.1. Logger cho event DTO

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class AiStructuredEventLogger {

    private static final Logger log =
            LoggerFactory.getLogger(AiStructuredEventLogger.class);

    public void modelCallCompleted(ModelCallCompletedEvent event) {
        var builder = log.atInfo()
                .addKeyValue("event.name", event.eventName())
                .addKeyValue("event.version", event.eventVersion())
                .addKeyValue("run.id", event.runId())
                .addKeyValue("case.id", event.caseId())
                .addKeyValue("attempt.id", event.attemptId())
                .addKeyValue("model.call.id", event.modelCallId())
                .addKeyValue("ai.provider", event.provider())
                .addKeyValue("ai.model", event.model())
                .addKeyValue("duration.ms", event.durationMs())
                .addKeyValue("outcome", event.outcome());

        if (event.inputTokens() != null) {
            builder.addKeyValue("usage.input_tokens", event.inputTokens());
        }
        if (event.outputTokens() != null) {
            builder.addKeyValue("usage.output_tokens", event.outputTokens());
        }
        if (event.evidenceRef() != null) {
            builder.addKeyValue("evidence.ref", event.evidenceRef());
        }

        builder.log("AI model call completed");
    }
}
~~~

Đoạn code yêu cầu SLF4J 2.x fluent API và backend/encoder có hỗ trợ key-value pairs. Nếu dự án dùng SLF4J 1.7, dùng API tương thích hoặc nâng dependency theo Spring Boot BOM; không trộn nhiều phiên bản SLF4J.

## 21. JUnit: kiểm schema, redaction và correlation

Test dưới đây minh họa kiểm event DTO. Nó chưa thay thế test JSON output của encoder thực tế.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.Arrays;
import org.junit.jupiter.api.Test;

class ModelCallCompletedEventTest {

    @Test
    void eventContainsOnlyApprovedMetadata() {
        var event = new ModelCallCompletedEvent(
                Instant.parse("2026-05-18T10:00:00Z"),
                "ai.model.call.completed",
                1,
                "run-1",
                "case-1",
                "attempt-1",
                "model-call-1",
                "provider-a",
                "model-a",
                842,
                120,
                45,
                "SUCCESS",
                "secure://evidence/answer-1");

        assertEquals("ai.model.call.completed", event.eventName());
        assertEquals(1, event.eventVersion());
        assertEquals("run-1", event.runId());
        assertEquals("case-1", event.caseId());
        assertEquals("attempt-1", event.attemptId());
        assertEquals(842, event.durationMs());

        var fields = Arrays.stream(
                ModelCallCompletedEvent.class.getRecordComponents())
                .map(component -> component.getName())
                .toList();

        assertFalse(fields.contains("prompt"));
        assertFalse(fields.contains("rawResponse"));
        assertFalse(fields.contains("authorizationHeader"));
    }

    @Test
    void negativeDurationIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                new ModelCallCompletedEvent(
                        Instant.now(),
                        "ai.model.call.completed",
                        1,
                        "run-1",
                        "case-1",
                        "attempt-1",
                        "model-call-1",
                        "provider-a",
                        "model-a",
                        -1,
                        null,
                        null,
                        "SUCCESS",
                        null));
    }

    @Test
    void missingUsageIsNotConvertedToZero() {
        var event = new ModelCallCompletedEvent(
                Instant.now(),
                "ai.model.call.completed",
                1,
                "run-1",
                "case-1",
                "attempt-1",
                "model-call-1",
                "provider-a",
                "model-a",
                100,
                null,
                null,
                "SUCCESS",
                null);

        assertNull(event.inputTokens());
        assertNull(event.outputTokens());
    }
}
~~~

### 30.1. Ví dụ test redaction trước khi log

Nếu có sanitizer, kiểm bằng input chứa secret và xác nhận output đã che:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class SafeLogValueTest {

    @Test
    void authorizationHeaderIsNeverReturned() {
        var safe = SafeLogValue.sanitizeHeader(
                "Authorization",
                "Bearer top-secret-token");

        assertEquals("[REDACTED]", safe);
        assertFalse(safe.contains("top-secret-token"));
    }
}
~~~

SafeLogValue là helper cần được triển khai theo allowlist/header policy của dự án. Không nên dùng một regex chung để sanitize mọi object.

## 22. Điều tra regression bằng structured logs

Giả sử factual correctness giảm sau khi nâng prompt. Hãy điều tra theo thứ tự:

1. Mở ai.evaluation.run.completed, kiểm tra dataset, rubric, counts và report ref.
2. Tìm ai.evaluation.completed có quality.status=FAIL hoặc verdict FAIL.
3. Lấy run.id, case.id, attempt.id.
4. Tìm ai.prompt.assembled để biết prompt version/digest.
5. Tìm ai.retrieval.completed và context assembly metadata.
6. Tìm model call completed/failed theo attempt ID.
7. Tìm tool events nếu case có tool.
8. Mở evidence refs cho actual answer, effective context và reference.
9. Dùng trace ID/span ID nếu có để phân tích latency.
10. So sánh với baseline run của cùng case.

### 22.1. Query minh họa

Ngôn ngữ query phụ thuộc log backend. Logic lọc nên tương đương:

~~~text
event.name = "ai.evaluation.completed"
AND run.id = "support-eval-v5"
AND case.id = "POLICY-017"
AND metric.status = "FAIL"
~~~

Từ event đó, lấy attempt.id để tìm các event cùng attempt. Nếu log backend hỗ trợ nested JSON fields, query theo field; không tìm bằng cách match cả chuỗi message.

### 22.2. Điều tra latency spike

- Tìm model call events có duration.ms cao.
- Nhóm theo provider/model/operation.
- Kiểm tra retry count và error code.
- Mở trace để xem thời gian nằm ở model, retrieval hay tool.
- Đối chiếu token input/output và prompt version.
- So với baseline trong cùng điều kiện tải.

Log event cho từng call giúp điều tra một case; histogram metrics mới là nguồn phù hợp để tính p95/p99 toàn hệ thống.

### 22.3. Khi log và trace không khớp

Có thể log được ghi nhưng trace bị sampled out; hoặc trace có span nhưng log event bị sampling. Kiểm tra sampling/collector policy và correlation context. Không tự kết luận event chưa xảy ra chỉ vì không tìm thấy một trong hai.

## 23. Những anti-pattern thường gặp

**Log toàn bộ prompt/response ở DEBUG.** Log level không phải cơ chế bảo vệ dữ liệu.

**Chỉ ghi message tự do.** Khó query và schema không ổn định.

**Đưa case ID/trace ID vào metric labels.** Tạo cardinality cao và chi phí không cần thiết.

**Tạo trace ID thủ công.** Phá semantics distributed tracing và không liên kết với spans thực.

**Ghi success=false cho mọi loại thất bại.** Không phân biệt technical error, quality FAIL và expected authorization denial.

**Ghi token usage bằng 0 khi provider không trả.** Biến dữ liệu thiếu thành số liệu sai.

**Log tool arguments bằng toString().** Có thể lộ dữ liệu cá nhân, token hoặc thông tin giao dịch.

**Log document chunks trong retrieval event.** Tăng volume và lộ nội dung corpus.

**Dùng MDC mà không restore.** Có thể gắn nhầm run/case vào log của request khác.

**Nuốt logging exception ở audit-critical path.** Mất dấu sự kiện cần kiểm toán.

**Rate-limit mọi error mà không có summary.** Che mất quy mô sự cố.

**Dùng log làm nguồn tính p95.** Log sampling và event loss khiến percentile sai; dùng histogram metrics.

**Không version event schema.** Consumer có thể đọc sai field sau một lần deploy.

**Ghi signed URL vào log.** Có thể biến log search thành đường truy cập artifact ngoài ý muốn.

## 24. Bài thực hành: xây structured logging cho pipeline Spring AI

**Bối cảnh:** chatbot hỗ trợ chính sách dùng Spring AI, RAG và tool getOrderStatus. Evaluation run có 100 case. Nhóm muốn điều tra quality FAIL và latency mà không lưu raw prompt/context vào log index.

### Phần A — Thiết kế event contract

Định nghĩa event names cho request, prompt assembly, retrieval, model call, tool, evaluation và run summary. Quy định field types, event version, required/optional fields và error taxonomy.

**Đầu ra:** event catalog và JSON Schema cho ít nhất model call, retrieval và evaluator events.

### Phần B — Thêm correlation IDs

Truyền run/case/attempt IDs qua các stage. Liên kết modelCallId/toolCallId/evaluationId. Lấy trace/span IDs thật nếu có. Kiểm tra async boundaries không làm mất hoặc trộn MDC.

**Đầu ra:** log events có thể lọc theo một attempt.

### Phần C — Logging an toàn

Tạo allowlist cho mỗi event. Không log prompt, answer, raw chunks, authorization headers hoặc tool arguments. Lưu evidence qua secure artifact store nếu policy cho phép, log opaque refs và digest. Kiểm tra log injection.

**Đầu ra:** privacy policy và redaction tests.

### Phần D — Structured JSON output

Cấu hình SLF4J/Logback encoder hoặc structured logging của Spring Boot version đang dùng. Phát một model event và một retrieval event, xác nhận JSON fields, types và correlation.

**Đầu ra:** JSON logs có thể query theo event.name/provider/run.id.

### Phần E — Điều tra lỗi mô phỏng

Mô phỏng:

- Model call 429 rồi retry thành công.
- Retrieval trả empty result.
- Tool authorization DENY đúng policy.
- Evaluator hoàn thành với quality FAIL.
- Judge timeout khiến NOT_EVALUATED.
- Trace sampled out.
- Provider usage không được cung cấp.

Kiểm tra event thể hiện đúng outcome, không gộp mọi tình huống vào ERROR.

**Đầu ra:** incident timeline và query hướng dẫn.

### Phần F — Kiểm thử và vận hành

Kiểm event schema, required fields, numeric types, redaction, correlation, retention, sampling và suppression. Tạo dashboard metrics riêng cho latency/error/retry; dùng logs để drill-down.

**Đầu ra:** logging contract, JUnit tests và runbook điều tra.

### Checklist nghiệm thu

- [ ] Event names ổn định và có version.
- [ ] Log records có timestamp UTC, service, environment, level và event name.
- [ ] Run/case/attempt IDs được truyền qua các stage.
- [ ] Trace/span IDs lấy từ tracing context thực tế.
- [ ] Prompt template version/digest được ghi mà không log raw prompt.
- [ ] Retrieval results và effective context được phân biệt.
- [ ] Model provider/model/usage/duration/status được ghi đúng.
- [ ] Tool schema/authorization/result refs được ghi an toàn.
- [ ] Evaluator execution status tách khỏi quality verdict.
- [ ] Unknown usage không bị chuyển thành zero.
- [ ] Secrets và raw sensitive payload không xuất hiện.
- [ ] MDC/context được restore qua async/thread boundaries.
- [ ] JSON encoder xuất field đúng kiểu.
- [ ] Event schema có contract tests.
- [ ] Sampling không loại audit-critical events.
- [ ] Suppression có summary/count và không che first/recovery event.
- [ ] Retention/access control được xác định.
- [ ] Metrics histogram được dùng cho p95/p99.
- [ ] Report/evidence refs có quyền truy cập riêng.
- [ ] Log queries hỗ trợ điều tra theo run/case/attempt.

### Câu hỏi tự kiểm tra

1. Structured logging khác chuỗi log tự do ở điểm nào?
2. Vì sao log không thay thế metrics, traces hoặc evidence artifacts?
3. Event name và event version cần ổn định như thế nào?
4. Vì sao attempt ID khác trace ID?
5. MDC có thể mất hoặc bị trộn trong tình huống nào?
6. Vì sao không nên log raw prompt/context ở DEBUG?
7. Retrieved count khác selected chunk count và effective context như thế nào?
8. Một tool authorization DENY đúng policy nên được phân loại ra sao?
9. Judge timeout khác quality FAIL như thế nào?
10. Vì sao token usage không được gán 0 khi provider không trả?
11. Khi nào nên dùng evidence ref thay raw content?
12. Vì sao log cardinality cao khác metric cardinality cao?
13. Log sampling khác trace sampling như thế nào?
14. Vì sao cần suppression count khi rate-limit repeated errors?
15. Làm sao kiểm JSON encoder thật thay vì chỉ kiểm Logback XML?
16. Khi nào operational log best-effort không đủ và cần durable audit event?
17. Vì sao log không phải nguồn phù hợp để tính p95?
18. Làm sao lần từ một factual FAIL tới retrieval/context/answer của đúng attempt?

## 25. Tổng kết

Structured logging biến hoạt động của ứng dụng Spring AI thành các event có tên, schema và correlation IDs ổn định. Nhờ đó, đội phát triển có thể tìm từ run/case/attempt tới prompt assembly, RAG retrieval, model calls, tool execution và evaluator verdict. Các field như provider/model, duration, usage, status, error code và evidence refs giúp log có giá trị điều tra mà không cần chứa raw payload.

Một logging design tốt phân biệt log với metrics, traces và evidence; tách technical outcome khỏi quality verdict và authorization decision; truyền correlation qua async boundaries; version event schema; và dùng allowlist/redaction trước khi serialize. Raw prompt, context, secrets và tool arguments không nên được ghi mặc định. Sampling, rate limiting, retention và access control phải được thiết kế theo từng loại event, đặc biệt với audit/security events.

Khi structured logs liên kết với metrics histogram, trace spans và evidence artifacts có quyền truy cập, nhóm có thể điều tra regression, latency và chi phí theo từng phiên bản prompt, model và pipeline. Điều quan trọng là mỗi log event phải phản ánh chính xác điều đã xảy ra, ghi rõ phần dữ liệu không có và không tạo ra cảm giác truy vết đầy đủ khi bằng chứng thực tế chưa được capture.

### Tài liệu tham khảo

- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot — Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html#features.logging.structured)
- [SLF4J — Manual](https://www.slf4j.org/manual.html)
- [Logback — Architecture](https://logback.qos.ch/manual/architecture.html)
- [Logstash Logback Encoder](https://github.com/logfellow/logstash-logback-encoder)
- [Micrometer — Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [OpenTelemetry — Logs](https://opentelemetry.io/docs/specs/otel/logs/)
- [OpenTelemetry — Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
