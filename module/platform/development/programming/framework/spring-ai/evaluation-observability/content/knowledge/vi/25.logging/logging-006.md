# Phân biệt phản hồi mô hình, kết quả công cụ và kết quả đánh giá

Một trợ lý Spring AI nhận câu hỏi về trạng thái đơn hàng. Model trả về một tool call yêu cầu chạy `getOrderStatus(orderId=...)`. Ứng dụng kiểm tra quyền, gọi hệ thống đơn hàng và nhận kết quả `SHIPPED`. Kết quả công cụ được đưa trở lại cuộc hội thoại; model tiếp tục tạo câu trả lời “Đơn hàng đã được gửi đi”. Sau đó một evaluator đối chiếu câu trả lời với dữ liệu chuẩn và kết luận PASS.

Trong một luồng ngắn như vậy đã có ba loại output khác nhau:

- **Phản hồi mô hình (model response):** nội dung hoặc chỉ thị do model sinh ra, bao gồm cả yêu cầu gọi công cụ.
- **Kết quả công cụ (tool result):** kết quả do ứng dụng thực thi công cụ và nhận từ hệ thống bên ngoài.
- **Kết quả đánh giá (evaluation result):** phán quyết được tạo bởi evaluator khi so sánh một artifact với tiêu chí/rubric/reference.

Nếu ghi cả ba dưới một field chung như `response` hoặc một trạng thái `SUCCESS`, hệ thống sẽ không thể trả lời chính xác câu hỏi: model đã nói gì, công cụ thực sự trả về gì, và câu trả lời có đạt chất lượng hay không. Một tool call thành công không có nghĩa model đã tạo final answer; một final answer được sinh thành công không có nghĩa câu trả lời đúng; một evaluator PASS cũng không chứng minh tool side effect đã được thực hiện đúng nếu evaluator không kiểm tra operation đó.

Bài học thuộc module **SPRING_AI_EVALUATION_OBSERVABILITY**. Nội dung hướng dẫn thiết kế ranh giới dữ liệu và event cho ba loại kết quả, mô hình hóa vòng đời model/tool/evaluation, theo dõi luồng Spring AI có tool calling, ghi log có correlation, xây Java DTO và kiểm thử các trạng thái độc lập. Mục tiêu là đánh giá đúng chất lượng ứng dụng RAG hoặc tool-using assistant và tìm được nguyên nhân khi pipeline suy giảm.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt model response, tool call request, tool execution result và evaluation verdict.
2. Giải thích vì sao tool call do model sinh ra chưa phải kết quả công cụ.
3. Mô tả vòng đời khi model yêu cầu một hoặc nhiều tool và tiếp tục sau khi nhận tool results.
4. Phân biệt final answer với intermediate assistant message, streaming chunk và structured output.
5. Thiết kế event schema riêng cho model, tool và evaluator.
6. Dùng IDs để nối model call, tool call, tool execution, evaluation, run/case/attempt và trace/span.
7. Tách execution status, tool status, quality verdict và evaluation status.
8. Mô hình hóa timeout, retry, authorization denial và unknown outcome của tool.
9. Đánh giá answer bằng rubric/reference mà không nhầm evaluator output với model answer.
10. Thiết kế log metadata an toàn cho ba loại output.
11. Viết Java DTO/service boundaries và JUnit tests cho pipeline.
12. Điều tra regression bằng event history và evidence references.

## 2. Ba loại output trả lời ba câu hỏi khác nhau

| Loại output | Ai tạo ra? | Nó mô tả điều gì? | Ví dụ |
| --- | --- | --- | --- |
| Model response | Chat model | Model sinh nội dung hoặc yêu cầu hành động nào? | Assistant text, JSON, tool call |
| Tool result | Tool adapter/backend sau khi ứng dụng thực thi | Công cụ thực sự trả về hoặc xác nhận điều gì? | Order status, search results, permission denial |
| Evaluation result | Evaluator/rule engine/human reviewer | Artifact được đánh giá đạt tiêu chí nào? | PASS, FAIL, score 0.92, NOT_EVALUATED |

Ba loại này có thể liên quan tới cùng một turn nhưng không thay thế cho nhau.

### 2.1. Model response

Model response là output từ model invocation. Nó có thể là:

- Assistant text hướng tới người dùng.
- Structured output theo schema.
- Tool call request do model đề xuất.
- Refusal hoặc safety response.
- Intermediate message cần thêm tool results.
- Partial/streaming output chưa hoàn tất.
- Response bị lỗi, bị cắt hoặc không có nội dung sử dụng được.

Một response chứa tool call là một phản hồi hợp lệ của model, nhưng nó biểu đạt ý định yêu cầu ứng dụng thực thi một công cụ. Nó không chứng minh công cụ đã chạy.

### 2.2. Tool result

Tool result được tạo sau khi ứng dụng xử lý tool call. Nó có thể là:

- Tool thực thi thành công và trả dữ liệu.
- Tool bị từ chối bởi authorization policy.
- Arguments không hợp lệ.
- Backend trả lỗi nghiệp vụ.
- Backend timeout.
- Operation có kết quả chưa xác định.
- Tool được retry hoặc reconcile.
- Tool không được chạy do policy hoặc budget.

Tool result có thể được đưa trở lại model như một tool message để model tiếp tục suy luận. Kết quả đó vẫn là output của công cụ; khi model diễn giải nó, phần diễn giải là model response mới.

### 2.3. Evaluation result

Evaluation result là kết quả đánh giá một artifact cụ thể theo rubric/metric. Artifact có thể là:

- Final answer.
- Retrieved context.
- Tool selection hoặc tool arguments.
- Tool execution outcome.
- Toàn bộ workflow của một case.
- Một conversation/turn hoặc một release candidate.

Evaluation result có thể do deterministic rule, evaluator model hoặc human reviewer tạo. Nó phải chỉ rõ đối tượng được đánh giá, rubric/version, evaluator/version, score/verdict và evidence đã dùng.

### 2.4. Ví dụ một turn có đủ ba loại

~~~text
Model response #1:
  tool call request: getOrderStatus(orderId="ORD-17")

Tool result #1:
  status=SUCCESS
  orderStatus=SHIPPED

Model response #2:
  "Đơn hàng ORD-17 đã được gửi đi."

Evaluation result:
  metric=factual_correctness
  verdict=PASS
  score=1.0
  rubric=support-rubric-v3
~~~

Nếu hệ thống chỉ lưu `response="SHIPPED"`, sẽ không biết đó là raw tool result hay câu model đã diễn đạt. Nếu chỉ lưu `success=true`, sẽ không biết success thuộc model call, tool execution hay evaluation.

## 3. Tool call request không phải tool result

Đây là ranh giới quan trọng nhất trong tool calling.

Khi model sinh tool call, nó thường đưa ra tên công cụ và arguments theo schema. Ứng dụng nhận yêu cầu đó, kiểm tra tool có được đăng ký/cho phép không, validate arguments, áp dụng authorization, thực thi adapter và chuẩn hóa kết quả.

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as Spring AI Application
    participant M as Chat Model
    participant T as Tool Adapter
    participant B as Backend
    U->>A: Ask about an order
    A->>M: Prompt + available tool definitions
    M-->>A: Assistant response with tool call request
    Note over M,A: This is model output, not tool execution
    A->>A: Validate schema and authorization
    A->>T: Execute approved tool call
    T->>B: Query order service
    B-->>T: Order status
    T-->>A: Normalized tool result
    A->>M: Tool result as conversation input
    M-->>A: Final assistant response
    A-->>U: User-facing answer
    A->>A: Evaluate answer against rubric/reference
~~~

### 3.1. Model chỉ đề xuất hành động

Model không có quyền tự thực thi một function chỉ vì nó phát ra tool call. Ứng dụng vẫn chịu trách nhiệm:

- Kiểm tra tool name có nằm trong registry không.
- Kiểm tra schema/version của arguments.
- Kiểm tra caller có quyền thực hiện operation không.
- Áp dụng tenant isolation và policy.
- Kiểm tra idempotency/deadline/budget.
- Gọi đúng adapter.
- Xử lý timeout, retry và unknown outcome.
- Ghi kết quả thực thi.

Đừng log trạng thái `TOOL_SUCCEEDED` ngay khi nhận assistant message có tool call.

### 3.2. Tool call ID và execution ID

Tool call ID thường định danh yêu cầu gọi tool trong model response. Tool execution ID do ứng dụng tạo để định danh lần thực thi thực tế. Một tool call có thể có nhiều execution attempts do retry; cần giữ quan hệ:

- modelCallId: invocation sinh ra tool call.
- toolCallId: yêu cầu tool do model phát ra.
- toolExecutionId: operation do application điều phối.
- attemptId: lần thử thực thi cụ thể.
- backendOperationId: ID do backend trả về nếu có.

Không dùng một ID cho tất cả nếu semantics khác nhau.

### 3.3. Một response có thể chứa nhiều tool calls

Model có thể yêu cầu nhiều tool trong một response. Ứng dụng có thể chạy song song hoặc tuần tự tùy dependency và policy. Mỗi tool call cần execution result riêng; không gộp chúng thành một kết quả không thể truy vết.

Nếu tool B phụ thuộc kết quả tool A, phải biểu diễn dependency/order. Không giả định thứ tự trong danh sách tool calls luôn là thứ tự hoàn thành.

## 4. Vòng đời model response

Một model invocation có lifecycle riêng với tool execution và evaluation.

| State | Ý nghĩa |
| --- | --- |
| REQUESTED | Application chuẩn bị gọi model |
| IN_PROGRESS | Request đã được gửi/đang nhận stream |
| COMPLETED | Có response hoàn chỉnh theo transport/model contract |
| INCOMPLETE | Response kết thúc nhưng không đầy đủ |
| FAILED | Model invocation thất bại |
| CANCELLED | Operation bị hủy |
| UNKNOWN | Client không xác định được provider đã xử lý request hay chưa |

Các state là convention của application event model. Loại output là chiều riêng, không phải lifecycle state:

| Response kind | Ý nghĩa |
| --- | --- |
| TEXT | Assistant text |
| STRUCTURED_OUTPUT | Output theo schema |
| TOOL_CALL_REQUEST | Model yêu cầu ứng dụng gọi tool |
| REFUSAL | Model từ chối theo policy/provider contract |
| EMPTY/UNKNOWN | Không có output sử dụng được hoặc không phân loại được |

Một model invocation có thể ở state COMPLETED với response kind TOOL_CALL_REQUEST. Tool execution chỉ bắt đầu sau đó.

### 4.1. Intermediate và final assistant messages

Một assistant message có thể là bước trung gian trước khi tool được gọi. Sau tool result, model có thể sinh thêm assistant message. Đừng coi mọi assistant message là final answer hiển thị cho user.

### 4.2. Structured output

Nếu model trả JSON theo schema, đó vẫn là model response. Việc parse/validate JSON là bước của application. Kết quả validation nên có status riêng; JSON parse thành công không chứng minh nội dung đúng.

### 4.3. Streaming response

Streaming có thể phát nhiều chunks trước khi kết thúc. Chunk không phải một model response hoàn chỉnh và không nên được đánh giá như final answer. Chỉ khi stream hoàn tất theo contract mới tạo model response artifact cuối; nếu cancel hoặc timeout, ghi partial/incomplete status.

### 4.4. Finish reason

Ghi finish reason như STOP, LENGTH, TOOL_CALL hoặc provider-specific enum nếu có. Không diễn giải tất cả finish reasons thành SUCCESS. Ví dụ response bị giới hạn token có thể kết thúc transport bình thường nhưng nội dung không đầy đủ.

## 5. Vòng đời tool execution

Tool execution có lifecycle độc lập:

| State | Ý nghĩa |
| --- | --- |
| REQUESTED | Application nhận tool call request |
| VALIDATING | Kiểm tra tên tool và arguments |
| REJECTED | Schema/policy/authorization từ chối |
| APPROVED | Tool call được phép chạy |
| EXECUTING | Đang gọi adapter/backend |
| SUCCEEDED | Backend result được xác nhận |
| FAILED | Có lỗi xác định |
| RETRY_SCHEDULED | Đã lên lịch retry |
| UNKNOWN_OUTCOME | Không biết side effect đã xảy ra chưa |
| RECONCILED | Đã đối soát kết quả |
| CANCELLED | Operation bị hủy |

### 5.1. Authorization denial là kết quả có ý nghĩa

Nếu tool call bị DENY, đó không nhất thiết là system failure. Có thể policy đã hoạt động đúng. Ghi authorization decision và policy version riêng; không đánh đồng DENIED với backend FAILED.

### 5.2. Tool business error khác technical error

Ví dụ `order_not_found` có thể là kết quả nghiệp vụ hợp lệ. HTTP 503 từ order service là dependency failure. Tool adapter nên chuẩn hóa hai loại này để evaluator và operator hiểu đúng.

### 5.3. Timeout và unknown outcome

Với tool có side effect như refund, cancel order hoặc create ticket, client timeout không chứng minh backend chưa thực hiện. Ghi UNKNOWN_OUTCOME và reconcile theo operation/idempotency reference trước retry.

### 5.4. Tool result có thể không phải dữ liệu tin cậy

Kết quả từ website, document, database hoặc tool bên ngoài có thể chứa nội dung độc hại hoặc prompt injection. Đưa tool result trở lại model không có nghĩa nội dung đó trở thành instruction đáng tin. Giữ provenance và áp dụng policy trước khi model sử dụng.

## 6. Vòng đời evaluation result

Evaluation bắt đầu sau khi có artifact phù hợp. Với answer evaluation, artifact thường là final answer cùng context/reference snapshot.

| State | Ý nghĩa |
| --- | --- |
| NOT_SCHEDULED | Chưa có yêu cầu đánh giá |
| PENDING | Đã tạo evaluation task |
| RUNNING | Evaluator đang chạy |
| COMPLETED | Đã có verdict/score hợp lệ |
| FAILED | Evaluator execution lỗi |
| SKIPPED | Bị bỏ qua theo policy |
| CANCELLED | Evaluation bị hủy |

Khi evaluator chạy xong nhưng evidence chưa đủ, evaluation status vẫn là COMPLETED và quality verdict là INCONCLUSIVE. Như vậy execution lifecycle và quality outcome không bị trộn.

Verdict là một chiều dữ liệu khác với execution state:

| Verdict | Ý nghĩa |
| --- | --- |
| PASS | Đạt tiêu chí |
| FAIL | Không đạt tiêu chí |
| NOT_EVALUATED | Không được đánh giá |
| INCONCLUSIVE | Đã đánh giá nhưng evidence không đủ |
| REVIEW_REQUIRED | Cần human review |

NOT_EVALUATED có thể là verdict tường minh khi evaluator chạy và xác định metric không áp dụng; nếu evaluation bị SKIPPED thì để verdict vắng mặt.

### 6.1. Evaluator hoàn tất không đồng nghĩa PASS

Evaluator có thể chạy thành công và kết luận FAIL. Execution status là COMPLETED; quality verdict là FAIL. Nếu evaluator service timeout, evaluation status là FAILED và không có verdict; nếu evaluator chạy xong nhưng thiếu evidence, status là COMPLETED với verdict INCONCLUSIVE.

### 6.2. Score phải đi cùng metric và scale

Score 0.8 không có nghĩa gì nếu không biết metric, direction, scale, threshold và rubric version. Ví dụ relevance score cao thường tốt; latency score có thể có semantics khác. Ghi metric name, score type/range, direction và threshold version.

### 6.3. Kết quả đánh giá phải gắn artifact cụ thể

Ghi artifact ID/version/hash đã được policy phê duyệt. Nếu answer được regenerate, evaluation cũ không tự áp dụng cho answer mới. Nếu rubric/judge đổi, verdict mới phải là một evaluation run/version khác.

## 7. Không nhầm model self-report với evaluation result

Model có thể nói “Tôi tin câu trả lời trên chính xác” hoặc trả một trường JSON `confidence=0.95`. Đây vẫn là model output. Nó không tự trở thành independent evaluation verdict.

Một evaluator result cần có:

- evaluator identity/type.
- metric/rubric version.
- target artifact reference.
- reference/context snapshot nếu metric cần.
- score/verdict và threshold.
- execution status.
- evidence/provenance.
- timestamp và evaluation ID.

### 7.1. LLM-as-a-judge

Nếu evaluator cũng dùng một model, cần phân biệt model call của judge với verdict do evaluation service chuẩn hóa. Judge raw response là model response; normalized PASS/FAIL/score là evaluation result.

Judge model có thể sai, thiên lệch hoặc không ổn định. Lưu judge model/version, prompt/rubric version, sampling parameters và calibration metadata. Với tiêu chí quan trọng, kết hợp deterministic checks, reference data và human review.

### 7.2. Evaluator không đủ evidence

Nếu không có reference facts, context snapshot hoặc tool execution evidence cần thiết, trả INCONCLUSIVE/NOT_EVALUATED theo semantics. Không ép PASS/FAIL chỉ để hoàn tất dashboard.

### 7.3. Evaluation có thể đánh giá cả tool behavior

Một evaluator có thể chấm tool selection, argument correctness, authorization handling hoặc backend outcome. Khi đó target artifact là tool decision/execution, không phải final answer. Ghi rõ targetType để không so nhầm.

## 8. Luồng đầy đủ trong Spring AI

Spring AI hỗ trợ tool/function calling thông qua tool definitions/callbacks và orchestration của application/ChatClient tùy cách tích hợp. API chi tiết có thể khác giữa phiên bản; adapter của ứng dụng nên chuẩn hóa các output về event model nội bộ.

~~~mermaid
flowchart TD
    A["User turn"] --> B["Prompt assembly"]
    B --> C["Model invocation"]
    C --> D{"Model response kind"}
    D -->|Assistant text / structured output| E["Candidate final answer"]
    D -->|Tool call request| F["Tool validation + authorization"]
    F -->|Rejected| G["Tool rejection result"]
    F -->|Approved| H["Tool adapter execution"]
    H --> I["Tool result / error / unknown outcome"]
    G --> J["Append tool result to conversation"]
    I --> J
    J --> K["Follow-up model invocation"]
    K --> D
    E --> L["Persist answer artifact"]
    L --> M["Evaluation task"]
    M --> N["Evaluator execution"]
    N --> O["Normalized verdict / score"]
    O --> P["Quality report / release gate"]
~~~

### 8.1. Automatic tool execution không làm mất ranh giới

Một API cấp cao có thể tự điều phối tool calls bên trong ChatClient invocation. Điều đó tiện cho application code, nhưng observability vẫn cần ghi nhận các model turns, tool executions và final answer riêng nếu cần điều tra chi tiết.

### 8.2. Một logical turn có nhiều model calls

Một user turn có thể có model call đầu để yêu cầu tool, một hoặc nhiều tool executions, rồi model call tiếp theo để tổng hợp. Tổng latency/cost của turn phải tính tất cả calls/attempts theo attribution policy.

### 8.3. Một model call có thể không tạo final answer

Model có thể chỉ phát tool call requests. Nếu workflow bị dừng sau tool denial, không có final answer. Ghi turn status như NEEDS_FOLLOW_UP/FAILED/CANCELLED theo domain contract; không bịa một response text từ tool result.

## 9. Event taxonomy cho ba loại kết quả

Dùng event names mô tả sự thật đã xảy ra.

| Event | Nhóm | Khi phát |
| --- | --- | --- |
| ai.model.call.started | Model | Model invocation bắt đầu |
| ai.model.response.completed | Model | Response hoàn tất |
| ai.model.tool_call.requested | Model | Model yêu cầu tool |
| ai.model.call.failed | Model | Model invocation thất bại |
| ai.tool.execution.requested | Tool | Application tiếp nhận yêu cầu thực thi |
| ai.tool.execution.rejected | Tool | Validation/authorization từ chối |
| ai.tool.execution.completed | Tool | Tool result được xác nhận |
| ai.tool.execution.failed | Tool | Tool execution lỗi xác định |
| ai.tool.execution.unknown | Tool | Outcome chưa xác định |
| ai.tool.execution.reconciled | Tool | Unknown outcome được đối soát |
| ai.evaluation.started | Evaluation | Evaluation bắt đầu |
| ai.evaluation.completed | Evaluation | Evaluator hoàn tất và có normalized result |
| ai.evaluation.failed | Evaluation | Evaluator execution lỗi |
| ai.evaluation.skipped | Evaluation | Evaluation bị bỏ qua |
| ai.evaluation.review_requested | Evaluation | Cần human review |

Không phát `ai.tool.execution.completed` khi mới nhận tool call request. Không phát `ai.evaluation.completed` nếu evaluator chỉ trả exception. Không phát `ai.model.response.completed` cho partial stream chưa đạt điều kiện complete.

### 9.1. Event envelope

Một envelope có thể chứa:

~~~json
{
  "eventId": "01JVB8K8M4Y7W8N1",
  "eventName": "ai.tool.execution.completed",
  "eventVersion": 1,
  "occurredAt": "2026-05-18T10:30:00Z",
  "producer": "assistant-orchestrator",
  "conversationId": "conv-81",
  "turnId": "turn-12",
  "runId": "support-eval-v5",
  "caseId": "POLICY-017",
  "attemptId": "POLICY-017-attempt-1",
  "modelCallId": "model-call-8f31",
  "toolCallId": "tool-call-2",
  "toolExecutionId": "tool-exec-9",
  "traceId": "actual-trace-id",
  "spanId": "actual-span-id",
  "payload": {
    "toolName": "getOrderStatus",
    "toolSchemaVersion": "v2",
    "executionStatus": "SUCCEEDED",
    "resultType": "ORDER_STATUS",
    "durationMs": 94
  }
}
~~~

Payload chỉ là metadata. Tool result body nên được lưu theo policy hoặc được chuẩn hóa thành business fields an toàn.

### 9.2. IDs phải giữ semantics

conversationId/turnId nối hội thoại; modelCallId nối model invocation; toolCallId nối request do model sinh; toolExecutionId nối operation do application thực thi; evaluationId nối verdict. Trace ID/span ID nối distributed tracing. Không thay thế các business IDs bằng trace ID vì trace có thể sampling/retention khác.

## 10. Schema riêng cho model response

Một event model response có thể ghi:

~~~json
{
  "event.name": "ai.model.response.completed",
  "event.version": 1,
  "model.call.id": "model-call-8f31",
  "turn.id": "turn-12",
  "response.kind": "TOOL_CALL_REQUEST",
  "response.finish_reason": "TOOL_CALL",
  "response.message.count": 1,
  "response.tool_call.count": 1,
  "response.content.status": "NOT_LOGGED",
  "usage.input_tokens": 1680,
  "usage.output_tokens": 42,
  "duration.ms": 410,
  "outcome": "COMPLETED"
}
~~~

### 10.1. response.kind

Dùng enum/bounded values như TEXT, STRUCTURED_OUTPUT, TOOL_CALL_REQUEST, REFUSAL, EMPTY hoặc UNKNOWN. Có thể dùng nhiều field nếu response chứa kết hợp content/tool calls. Định nghĩa semantics rõ trong schema.

### 10.2. Usage và finish reason

Token usage có thể vắng mặt hoặc unknown nếu provider không trả. Không gán zero. Finish reason cần giữ provider mapping hoặc normalized value kèm raw safe code nếu policy cho phép.

### 10.3. Không ghi tool arguments vào model event mặc định

Model response event có thể ghi tool call count, tool names đã allowlist và schema version. Arguments là content/input cần kiểm soát; không serialize raw arguments.

## 11. Schema riêng cho tool result

Tool execution event cần ghi cả quyết định trước execution và outcome sau execution.

~~~json
{
  "event.name": "ai.tool.execution.completed",
  "event.version": 1,
  "tool.call.id": "tool-call-2",
  "tool.execution.id": "tool-exec-9",
  "tool.name": "getOrderStatus",
  "tool.schema.version": "v2",
  "authorization.decision": "ALLOW",
  "validation.status": "VALID",
  "execution.status": "SUCCEEDED",
  "result.type": "ORDER_STATUS",
  "result.content.status": "STORED_AS_EVIDENCE",
  "duration.ms": 94,
  "attempt.number": 1,
  "outcome": "SUCCESS"
}
~~~

### 11.1. Tool result status và business result

Tool execution có thể SUCCEEDED nhưng business result là NOT_FOUND. Ví dụ query order hoàn tất thành công và trả không tìm thấy đơn hàng. Đừng coi NOT_FOUND là technical failure nếu đó là kết quả domain hợp lệ.

### 11.2. Tool result không phải final answer

Tool result `SHIPPED` có thể được model diễn đạt thành “Đơn hàng đã được gửi đi”. Lưu raw/normalized tool result ở tool event; lưu assistant final answer ở model response event. Evaluator có thể so sánh hai nguồn để phát hiện hallucination.

### 11.3. Side effect tools

Với create/update/delete/refund/cancel, ghi idempotency key reference, backend operation ID, authorization policy version và reconciliation state. Không log arguments chứa account/customer data.

## 12. Schema riêng cho evaluation result

Một evaluation result nên mô tả target và tiêu chí.

~~~json
{
  "event.name": "ai.evaluation.completed",
  "event.version": 1,
  "evaluation.id": "eval-991",
  "target.type": "FINAL_ANSWER",
  "target.artifact.id": "answer-artifact-17",
  "run.id": "support-eval-v5",
  "case.id": "POLICY-017",
  "attempt.id": "POLICY-017-attempt-1",
  "metric.name": "factual_correctness",
  "rubric.version": "support-rubric-v3",
  "evaluator.type": "LLM_JUDGE",
  "evaluator.model": "judge-model-v2",
  "evaluator.prompt.version": "judge-prompt-v4",
  "evaluation.status": "COMPLETED",
  "verdict": "PASS",
  "score": 1.0,
  "score.scale": "0..1",
  "evidence.status": "AVAILABLE",
  "duration.ms": 730
}
~~~

### 12.1. target.type

Ví dụ FINAL_ANSWER, RETRIEVAL_RESULT, TOOL_SELECTION, TOOL_ARGUMENTS, TOOL_EXECUTION hoặc FULL_TURN. Ghi rõ target để consumer biết verdict đang chấm cái gì.

### 12.2. Metric và rubric version

Nếu metric đổi semantics hoặc threshold, tăng version. Đừng so score từ hai rubric khác nhau như cùng một thang đo nếu chưa chuẩn hóa.

### 12.3. Evaluator type

Có thể là DETERMINISTIC_RULE, LLM_JUDGE, HUMAN_REVIEW hoặc EXTERNAL_EVALUATOR. Nếu LLM judge được dùng, ghi model/prompt version. Nếu human review, ghi reviewer reference theo policy, không ghi dữ liệu cá nhân không cần thiết.

### 12.4. Evaluation status và verdict

Ví dụ:

| Evaluation status | Verdict | Diễn giải |
| --- | --- | --- |
| COMPLETED | PASS | Đánh giá xong, đạt |
| COMPLETED | FAIL | Đánh giá xong, không đạt |
| COMPLETED | INCONCLUSIVE | Đánh giá xong nhưng evidence chưa đủ |
| FAILED | absent | Evaluator execution lỗi |
| SKIPPED | absent | Policy không yêu cầu đánh giá |
| CANCELLED | absent | Evaluation bị hủy |

Không gán verdict FAIL cho evaluation FAILED; đó là hai ý nghĩa khác nhau.

## 13. Tách runtime outcome khỏi quality outcome

Một workflow có nhiều trục trạng thái độc lập:

| Trục | Ví dụ trạng thái | Ý nghĩa |
| --- | --- | --- |
| Model execution | COMPLETED, FAILED, INCOMPLETE | Model invocation có hoàn tất không? |
| Model response kind | TEXT, TOOL_CALL_REQUEST, REFUSAL | Model đã sinh loại output nào? |
| Tool execution | SUCCEEDED, REJECTED, FAILED, UNKNOWN | Công cụ thực sự làm gì? |
| Business outcome | FOUND, NOT_FOUND, UPDATED, DENIED | Kết quả domain là gì? |
| Evaluation execution | COMPLETED, FAILED, SKIPPED | Evaluator có chạy xong không? |
| Quality verdict | PASS, FAIL, INCONCLUSIVE | Artifact có đạt tiêu chí không? |
| User turn | COMPLETED, NEEDS_FOLLOW_UP, CANCELLED | Turn kết thúc ở trạng thái nào? |

### 13.1. Các tổ hợp hợp lệ

- Model call COMPLETED + response TOOL_CALL_REQUEST + tool REJECTED.
- Model call COMPLETED + response TEXT + evaluator FAIL.
- Tool SUCCEEDED + business result NOT_FOUND + answer PASS.
- Tool UNKNOWN_OUTCOME + evaluation SKIPPED.
- Model call FAILED + evaluation NOT_EVALUATED.
- Model response COMPLETED + evaluator FAILED.

Không ép các trục này vào một boolean success.

### 13.2. Run summary

Evaluation run có thể tổng hợp:

- model invocation success/failure counts.
- tool execution success/reject/failure/unknown counts.
- evaluation completed/failed/skipped counts.
- quality PASS/FAIL/INCONCLUSIVE counts.
- final user turn completion counts.

Các mẫu số phải tách biệt. Ví dụ quality pass rate không lấy tool calls làm denominator nếu metric chấm final answers.

## 14. Correlation xuyên model, tool và evaluator

Một workflow nhiều bước cần IDs rõ ràng:

| ID | Phạm vi |
| --- | --- |
| conversationId | Cuộc hội thoại |
| turnId | Một lượt xử lý user |
| runId | Evaluation run |
| caseId | Dataset case |
| attemptId | Lần chạy case |
| modelCallId | Một lần gọi model |
| toolCallId | Tool request do model sinh |
| toolExecutionId | Operation do ứng dụng thực thi |
| toolAttemptId | Một lần thử tool |
| evaluationId | Một lần đánh giá |
| artifactId | Answer/context/tool evidence |
| traceId/spanId | Distributed trace/span |

### 14.1. Causation và parent-child

Model response tool call gây ra tool execution. Tool result gây ra follow-up model call. Final answer gây ra evaluation task. Ghi causationId hoặc parent reference để dựng timeline.

### 14.2. Không suy thứ tự chỉ từ timestamp

Clock skew và async execution có thể làm timestamp lệch. Dùng event sequence/causation/parent-child IDs khi cần ordering. occurredAt và recordedAt cũng có thể khác nhau.

### 14.3. Trace IDs là telemetry correlation

Trace/span IDs giúp drill-down qua spans, nhưng trace sampling có thể drop. Business IDs và event history vẫn cần tồn tại theo retention contract độc lập.

## 15. Log an toàn cho ba loại output

Operational logs mặc định chỉ ghi metadata:

| Loại | Metadata nên ghi | Content không log mặc định |
| --- | --- | --- |
| Model response | model/provider, response kind, finish reason, usage, duration | assistant text, structured body, tool arguments |
| Tool result | tool name/schema, validation, authorization, status, duration | arguments, raw result, backend payload |
| Evaluation result | target, metric/rubric/evaluator versions, verdict, score, status | answer, reference text, free-form judge rationale |

### 15.1. Evidence references

Nếu cần xem nội dung, lưu prompt/answer/tool result/reference trong evidence store có access control, rồi ghi opaque evidence refs. Không đưa signed URL hoặc bearer URL vào log.

### 15.2. Tránh field chung chung

Không dùng một field `response.content` cho cả model response, tool result và evaluator feedback. Dùng event-specific namespaces hoặc DTOs riêng như `model.response.*`, `tool.result.*`, `evaluation.*`.

### 15.3. Không ghi evaluator rationale tự do mặc định

LLM judge có thể quote answer/reference hoặc chứa dữ liệu nhạy cảm trong explanation. Ghi verdict, score, reason codes đã chuẩn hóa và evidence refs. Nếu cần full rationale, capture qua evidence policy.

## 16. Java: application-owned event DTOs

Không cần buộc toàn bộ code phụ thuộc trực tiếp vào một phiên bản cụ thể của Spring AI response classes. Tạo adapter chuyển framework response thành domain event DTO ổn định.

~~~java
import java.time.Instant;
import java.util.Objects;

public enum ModelResponseKind {
    TEXT,
    STRUCTURED_OUTPUT,
    TOOL_CALL_REQUEST,
    REFUSAL,
    EMPTY,
    UNKNOWN
}

public record ModelResponseEvent(
        String modelCallId,
        String conversationId,
        String turnId,
        ModelResponseKind responseKind,
        String finishReason,
        int toolCallCount,
        Integer inputTokens,
        Integer outputTokens,
        long durationMs,
        String contentEvidenceRef,
        Instant occurredAt) {

    public ModelResponseEvent {
        Objects.requireNonNull(modelCallId);
        Objects.requireNonNull(responseKind);
        Objects.requireNonNull(occurredAt);
        if (toolCallCount < 0 || durationMs < 0) {
            throw new IllegalArgumentException("Counts and duration must be non-negative");
        }
    }
}

public record ToolExecutionEvent(
        String toolCallId,
        String toolExecutionId,
        String toolName,
        String schemaVersion,
        String authorizationDecision,
        String validationStatus,
        String executionStatus,
        String businessOutcome,
        String resultEvidenceRef,
        int attemptNumber,
        long durationMs,
        Instant occurredAt) {

    public ToolExecutionEvent {
        Objects.requireNonNull(toolCallId);
        Objects.requireNonNull(toolExecutionId);
        Objects.requireNonNull(toolName);
        Objects.requireNonNull(executionStatus);
        Objects.requireNonNull(occurredAt);
        if (attemptNumber < 1 || durationMs < 0) {
            throw new IllegalArgumentException("Invalid attempt or duration");
        }
    }
}

public record EvaluationResultEvent(
        String evaluationId,
        String targetType,
        String targetArtifactId,
        String metricName,
        String rubricVersion,
        String evaluatorType,
        String evaluatorVersion,
        String evaluationStatus,
        String verdict,
        Double score,
        String scoreScale,
        String evidenceRef,
        Instant occurredAt) {

    public EvaluationResultEvent {
        Objects.requireNonNull(evaluationId);
        Objects.requireNonNull(targetType);
        Objects.requireNonNull(metricName);
        Objects.requireNonNull(evaluationStatus);
        Objects.requireNonNull(occurredAt);
    }
}
~~~

Đặt mỗi public enum/record ở file Java riêng (ví dụ ModelResponseEvent.java, ToolExecutionEvent.java và EvaluationResultEvent.java). Các định nghĩa được đặt chung trong một code block để trình bày quan hệ giữa chúng.

Đây là ba DTO ứng dụng minh họa. Có thể thay các field status dạng String bằng enum để compiler kiểm tra giá trị hợp lệ. DTO chỉ chứa metadata và evidence references; không có raw model/tool/evaluator content.

## 17. Java: adapter cho model response và tool calls

Adapter nhận output từ Spring AI layer rồi phân loại. Không giả định mọi assistant message đều là final text.

~~~java
public interface ModelResponseAdapter {
    ModelResponseEvent toEvent(
            String modelCallId,
            String conversationId,
            String turnId,
            Object frameworkResponse,
            long durationMs);
}
~~~

`frameworkResponse` ở đây đại diện cho response object của phiên bản Spring AI đang dùng. Implementation thực tế đọc ChatResponse/Generation/AssistantMessage và metadata theo API version đã pin. Adapter phải phân biệt:

- Assistant text/structured content.
- Tool call requests.
- Refusal.
- Empty/incomplete response.
- Finish reason và usage nếu provider trả.

### 17.1. Tool call request DTO

~~~java
public record ToolCallRequest(
        String toolCallId,
        String toolName,
        String schemaVersion,
        String argumentsEvidenceRef) {}
~~~

Arguments không được đưa vào operational log. ToolCallRequest là intent từ model, chưa phải execution result.

### 17.2. Tool dispatcher contract

~~~java
public interface ToolDispatcher {
    ToolExecutionEvent execute(
            ToolCallRequest request,
            ToolExecutionContext context);
}

public record ToolExecutionContext(
        String conversationId,
        String turnId,
        String runId,
        String caseId,
        String attemptId,
        String actorRef,
        String tenantRef,
        String traceId) {}
~~~

Dispatcher chịu trách nhiệm registry lookup, schema validation, authorization, idempotency, deadline, execution và normalization. Không tin tool name/arguments do model sinh ra cho tới khi validate.

### 17.3. Follow-up model call

Sau khi tool result được chuẩn hóa, application adapter chuyển nó thành input conversation message theo API của Spring AI version đang dùng. Tool result không được đổi nhãn thành assistant message; role/provenance phải được giữ để model biết nguồn dữ liệu.

## 18. Java: evaluation service và verdict normalization

~~~java
public record EvaluationRequest(
        String evaluationId,
        String targetType,
        String targetArtifactId,
        String metricName,
        String rubricVersion,
        String evaluatorVersion,
        String referenceEvidenceRef,
        String contextEvidenceRef) {}

public record RawEvaluatorOutput(
        String evaluatorStatus,
        String rawVerdict,
        Double rawScore,
        String rationaleEvidenceRef) {}

public interface Evaluator {
    RawEvaluatorOutput evaluate(EvaluationRequest request);
}
~~~

Evaluation service chuẩn hóa output theo metric contract:

Enum dưới đây mô tả trạng thái kết thúc của một normalized result. PENDING và RUNNING thuộc task lifecycle trước khi có kết quả cuối.

~~~java
public enum EvaluationStatus {
    COMPLETED,
    FAILED,
    SKIPPED,
    CANCELLED
}

public enum QualityVerdict {
    PASS,
    FAIL,
    INCONCLUSIVE,
    NOT_EVALUATED,
    REVIEW_REQUIRED
}

public record NormalizedEvaluationResult(
        EvaluationStatus status,
        QualityVerdict verdict,
        Double score,
        String metricName,
        String rubricVersion,
        String targetArtifactId) {

    public NormalizedEvaluationResult {
        java.util.Objects.requireNonNull(status);
        if (status == EvaluationStatus.COMPLETED && verdict == null) {
            throw new IllegalArgumentException(
                    "Completed evaluation requires a verdict");
        }
        if (status != EvaluationStatus.COMPLETED && verdict != null) {
            throw new IllegalArgumentException(
                    "Non-completed evaluation cannot carry a verdict");
        }
    }
}
~~~

### 18.1. Không map evaluator exception thành FAIL

Nếu evaluator timeout, trạng thái là FAILED và không có verdict. Nếu evaluator chạy xong nhưng evidence không đủ, dùng COMPLETED với verdict INCONCLUSIVE. FAIL chỉ dùng khi evaluator đã đánh giá và kết luận target không đạt.

### 18.2. Kiểm score và threshold

Validate score nằm trong scale đã định nghĩa. Nếu metric dùng 0..1, từ chối score ngoài range. Threshold phải gắn version và direction; ví dụ relevance score >= threshold là PASS nhưng latency score có thể có chiều ngược lại.

### 18.3. Raw judge output và normalized result

Raw LLM judge response là model response của evaluator model. Normalized result là evaluation result. Nếu cần lưu rationale, dùng evidence ref và giữ riêng với operational logs.

### 18.4. Kiểm tra ranh giới bằng JUnit 5

Các test sau xác nhận tool-call request vẫn thuộc model response, tool result có execution ID riêng và evaluator failure không bị biến thành verdict FAIL.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class OutcomeSeparationTest {

    @Test
    void toolCallRequestIsStillAModelResponse() {
        var response = new ModelResponseEvent(
                "model-call-1", "conversation-1", "turn-1",
                ModelResponseKind.TOOL_CALL_REQUEST,
                "TOOL_CALL", 1, 120, 18, 240, null, Instant.now());

        assertEquals(ModelResponseKind.TOOL_CALL_REQUEST,
                response.responseKind());
        assertEquals(1, response.toolCallCount());
        // No ToolExecutionEvent exists until the application dispatches the call.
    }

    @Test
    void toolExecutionCanSucceedWithBusinessNotFound() {
        var tool = new ToolExecutionEvent(
                "tool-call-1", "tool-exec-1", "getOrderStatus", "v2",
                "ALLOW", "VALID", "SUCCEEDED", "NOT_FOUND",
                null, 1, 42, Instant.now());

        assertEquals("SUCCEEDED", tool.executionStatus());
        assertEquals("NOT_FOUND", tool.businessOutcome());
        assertNotEquals(tool.toolCallId(), tool.toolExecutionId());
    }

    @Test
    void evaluatorFailureCannotCarryQualityFailVerdict() {
        assertThrows(IllegalArgumentException.class, () ->
                new NormalizedEvaluationResult(
                        EvaluationStatus.FAILED, QualityVerdict.FAIL,
                        null, "factual_correctness", "v3", "answer-1"));
    }

    @Test
    void completedEvaluationCanReturnFailVerdict() {
        var result = new NormalizedEvaluationResult(
                EvaluationStatus.COMPLETED, QualityVerdict.FAIL,
                0.2, "factual_correctness", "v3", "answer-1");

        assertEquals(EvaluationStatus.COMPLETED, result.status());
        assertEquals(QualityVerdict.FAIL, result.verdict());
    }
}
~~~

Đây là ví dụ kiểm tra contract ở mức domain. Trong dự án, mỗi public enum/record/class nên nằm trong file Java riêng; các test cần dùng cùng package hoặc import đúng package của DTO.

## 19. Structured logging bằng SLF4J

Ghi event-specific fields để người vận hành không nhầm ba loại output.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class AiOutcomeLogger {

    private static final Logger log =
            LoggerFactory.getLogger(AiOutcomeLogger.class);

    public void modelResponse(ModelResponseEvent event) {
        log.atInfo()
                .addKeyValue("event.name", "ai.model.response.completed")
                .addKeyValue("model.call.id", event.modelCallId())
                .addKeyValue("turn.id", event.turnId())
                .addKeyValue("response.kind", event.responseKind().name())
                .addKeyValue("response.tool_call.count", event.toolCallCount())
                .addKeyValue("finish.reason", event.finishReason())
                .addKeyValue("usage.input_tokens", event.inputTokens())
                .addKeyValue("usage.output_tokens", event.outputTokens())
                .addKeyValue("duration.ms", event.durationMs())
                .log("Model response completed");
    }

    public void toolResult(ToolExecutionEvent event) {
        String eventName = switch (event.executionStatus()) {
            case "SUCCEEDED" -> "ai.tool.execution.completed";
            case "REJECTED" -> "ai.tool.execution.rejected";
            case "FAILED" -> "ai.tool.execution.failed";
            case "UNKNOWN_OUTCOME" -> "ai.tool.execution.unknown";
            case "RECONCILED" -> "ai.tool.execution.reconciled";
            default -> "ai.tool.execution.state_changed";
        };
        log.atInfo()
                .addKeyValue("event.name", eventName)
                .addKeyValue("tool.call.id", event.toolCallId())
                .addKeyValue("tool.execution.id", event.toolExecutionId())
                .addKeyValue("tool.name", event.toolName())
                .addKeyValue("tool.authorization", event.authorizationDecision())
                .addKeyValue("tool.validation", event.validationStatus())
                .addKeyValue("tool.execution.status", event.executionStatus())
                .addKeyValue("tool.business.outcome", event.businessOutcome())
                .addKeyValue("duration.ms", event.durationMs())
                .log("Tool execution state recorded");
    }

    public void evaluationResult(EvaluationResultEvent event) {
        String eventName = switch (event.evaluationStatus()) {
            case "COMPLETED" -> "ai.evaluation.completed";
            case "FAILED" -> "ai.evaluation.failed";
            case "SKIPPED" -> "ai.evaluation.skipped";
            case "CANCELLED" -> "ai.evaluation.cancelled";
            default -> "ai.evaluation.state_changed";
        };
        log.atInfo()
                .addKeyValue("event.name", eventName)
                .addKeyValue("evaluation.id", event.evaluationId())
                .addKeyValue("evaluation.target.type", event.targetType())
                .addKeyValue("evaluation.metric", event.metricName())
                .addKeyValue("evaluation.status", event.evaluationStatus())
                .addKeyValue("evaluation.verdict", event.verdict())
                .addKeyValue("evaluation.score", event.score())
                .addKeyValue("evaluation.rubric.version", event.rubricVersion())
                .log("Evaluation state recorded");
    }
}
~~~

Đoạn logger minh họa field separation. Trong implementation thực tế, chỉ log event sau khi state tương ứng đã được xác nhận; không log tool completed khi dispatcher mới nhận request. Cần kiểm encoder giữ đúng kiểu số/boolean và không tự serialize payload content.

## 20. Metrics phải tách theo loại output

Đừng dùng một metric `ai_operation_success_total` cho model, tool và evaluation nếu không có bounded dimension phân biệt.

| Metric | Ý nghĩa | Labels gợi ý |
| --- | --- | --- |
| ai_model_calls_total | Số model invocations | provider, model family, outcome |
| ai_model_tool_call_requests_total | Số tool call requests do model sinh | tool name, model family |
| ai_tool_executions_total | Số tool executions thực tế | tool name, execution status |
| ai_tool_authorization_denials_total | Số tool requests bị deny | tool name, policy version |
| ai_evaluations_total | Số evaluation executions | metric, evaluator type, status |
| ai_evaluation_verdicts_total | Số verdicts | metric, verdict, rubric version |
| ai_model_call_duration | Latency model | provider, model family |
| ai_tool_execution_duration | Latency tool | tool name, status |
| ai_evaluation_duration | Latency evaluator | metric, evaluator type |

### 20.1. Đếm tool call request khác execution

Một model response có thể yêu cầu 2 tool calls; application có thể từ chối một và thực thi một. Khi đó:

- model_tool_call_requests_total tăng 2.
- tool_executions_total tăng 1.
- tool_authorization_denials_total tăng 1.

Không lấy số tool call requests làm số backend executions.

### 20.2. Verdict rate có denominator riêng

Evaluation verdict rate chỉ tính evaluation đã hoàn tất và có verdict phù hợp. Evaluation failed/skipped/inconclusive cần metric riêng. Không coi missing verdict là PASS.

### 20.3. Cardinality

Không dùng raw conversationId, toolCallId, evaluationId, artifact ID hoặc user input làm metric labels. Các IDs thuộc logs/traces. Labels nên bounded.

## 21. Điều tra regression bằng ba event streams

Giả sử assistant trả lời “Đơn hàng đã giao” nhưng dữ liệu thực tế là “Đang vận chuyển”.

1. Mở evaluation result: verdict FAIL, metric factual_correctness, rubric v3.
2. Xác định target answer artifact ID và attempt ID.
3. Mở model response event: response.kind TEXT, model/version, finish reason.
4. Mở các model response trước đó: có tool call request getOrderStatus hay không?
5. Mở tool execution event theo toolCallId/toolExecutionId.
6. Kiểm authorization, validation, execution status và business outcome.
7. So tool result evidence với answer evidence.
8. Kiểm follow-up model call đã nhận đúng tool result/provenance chưa.
9. Kiểm evaluator dùng reference/context snapshot nào.
10. Dùng trace IDs để tìm stage latency hoặc error.

### 21.1. Phân loại root cause

| Bằng chứng | Hướng điều tra |
| --- | --- |
| Không có tool call request | Model/tool selection hoặc prompt issue |
| Có tool call nhưng validation fail | Schema/tool definition |
| Authorization DENY | Policy/actor/tenant scope |
| Tool FAILED | Backend/adapter dependency |
| Tool UNKNOWN_OUTCOME | Reconciliation/idempotency |
| Tool SUCCEEDED nhưng answer sai | Tool result mapping hoặc model synthesis |
| Answer đúng nhưng verdict FAIL | Evaluator/rubric/reference |
| Evaluator FAILED | Evaluation infrastructure |
| Verdict PASS nhưng tool side effect sai | Target/evidence scope của evaluation chưa đủ |

### 21.2. Không kết luận từ một event

Một event riêng lẻ thường không đủ. Dựng timeline từ model response, tool execution, follow-up model response và evaluation result; kiểm artifact refs và causal links trước khi kết luận.

## 22. Anti-pattern thường gặp

**Coi tool call request là tool execution.** Model chỉ đề xuất; application còn phải validate, authorize và execute.

**Coi tool result là assistant answer.** Tool result cần provenance riêng; model có thể diễn giải sai dữ liệu đó.

**Coi evaluator output là model answer.** Judge raw response và normalized verdict là hai artifacts khác nhau.

**Một boolean success cho toàn pipeline.** Che mất model success, tool failure và evaluation FAIL.

**Đếm tool call request thành tool executions.** Sai số lượng backend operations.

**Ghi evaluation FAIL khi evaluator timeout.** Nhầm infrastructure failure với quality failure.

**Đánh giá partial streaming chunk như final answer.** Chưa có artifact hoàn chỉnh.

**Không giữ toolCallId và toolExecutionId.** Không nối được yêu cầu model với operation thực tế.

**Không phân biệt business NOT_FOUND với technical FAILED.** Dashboard và alert sai semantics.

**Retry side-effect tool mà không reconcile.** Có thể tạo duplicate operation.

**Tin tool result như instruction.** Tool content có thể không đáng tin và chứa prompt injection.

**Log raw arguments/results/rationale.** Tăng rủi ro lộ dữ liệu và tạo event quá lớn.

**So sánh score khác rubric như cùng thang.** Kết luận regression không đáng tin.

## 23. Bài thực hành: instrument một assistant có tool và evaluator

**Bối cảnh:** assistant hỗ trợ đơn hàng dùng Spring AI. Model có thể gọi getOrderStatus và cancelOrder. Sau khi tạo final answer, evaluation pipeline chấm factual correctness và tool-use correctness.

### Phần A — Xác định output contracts

Tạo model response kinds TEXT, STRUCTURED_OUTPUT, TOOL_CALL_REQUEST, REFUSAL và INCOMPLETE. Tạo tool execution statuses REQUESTED, REJECTED, SUCCEEDED, FAILED, UNKNOWN_OUTCOME và RECONCILED. Tạo evaluation statuses/verdicts riêng.

**Đầu ra:** state tables và DTO schemas.

### Phần B — Instrument model turns

Ghi modelCallId, response kind, finish reason, usage, duration và tool call count. Không log raw content/arguments. Phân biệt intermediate assistant message và final answer.

**Đầu ra:** model response events.

### Phần C — Instrument tool execution

Ghi toolCallId, toolExecutionId, schema version, authorization, validation, attempt, business outcome và duration. Mô phỏng DENY, invalid args, backend NOT_FOUND, 503, timeout unknown outcome và reconcile.

**Đầu ra:** tool execution events và idempotency tests.

### Phần D — Instrument evaluation

Chấm final answer và tool behavior bằng metric/rubric khác nhau. Ghi target type, artifact ID, evaluator version, evaluation status, verdict, score và evidence refs.

**Đầu ra:** normalized evaluation results.

### Phần E — Correlation

Nối conversation/turn/run/case/attempt, model call, tool call/execution, evaluation và trace/span IDs. Dựng timeline cho một case có hai tool calls và một follow-up model call.

**Đầu ra:** trace/log correlation view.

### Phần F — Regression investigation

Tạo case model gọi đúng tool nhưng tổng hợp sai answer; case tool bị deny; case evaluator timeout; case tool unknown outcome. Xác định root cause theo event streams.

**Đầu ra:** incident/evaluation report.

### Checklist nghiệm thu

- [ ] Model response, tool result và evaluation result có DTO/schema riêng.
- [ ] Tool call request không bị coi là execution result.
- [ ] Tool result giữ toolCallId và toolExecutionId.
- [ ] Multiple tool calls được ghi riêng.
- [ ] Model intermediate response không bị coi là final answer.
- [ ] Streaming chỉ đánh giá sau khi artifact hoàn tất.
- [ ] Authorization/validation status tách khỏi execution status.
- [ ] Business outcome tách khỏi technical status.
- [ ] Timeout side effect có UNKNOWN_OUTCOME và reconciliation.
- [ ] Evaluator FAILED không tự sinh verdict FAIL.
- [ ] Verdict luôn gắn target artifact, metric và rubric version.
- [ ] Judge model response tách khỏi normalized evaluation result.
- [ ] Score có scale/direction/threshold semantics.
- [ ] Model/tool/evaluation metrics có denominator riêng.
- [ ] IDs/correlation/causation links đầy đủ.
- [ ] Logs chỉ chứa metadata và evidence refs theo policy.
- [ ] Raw tool arguments/results/answer/rationale không log mặc định.
- [ ] JUnit tests bao phủ các trạng thái độc lập.
- [ ] Regression investigation dựng được timeline ba event streams.
- [ ] Release gate dùng quality verdict và runtime health riêng.

### Câu hỏi tự kiểm tra

1. Model response khác tool result như thế nào?
2. Vì sao tool call request chưa phải execution?
3. Một assistant message chứa tool call có phải final answer không?
4. ToolCallId khác ToolExecutionId ở đâu?
5. Làm sao xử lý một response có nhiều tool calls?
6. Tool execution SUCCEEDED nhưng business result NOT_FOUND có hợp lệ không?
7. Vì sao timeout của side-effect tool cần UNKNOWN_OUTCOME?
8. Tool result có thể chứa prompt injection không?
9. Evaluation result cần những metadata nào?
10. Evaluator FAILED khác verdict FAIL như thế nào?
11. Judge raw response khác normalized verdict ra sao?
12. Vì sao score phải gắn metric/rubric version?
13. Khi nào verdict nên là INCONCLUSIVE?
14. Model final answer có thể đúng dù tool call trước đó bị retry không?
15. Vì sao không dùng một boolean success cho toàn pipeline?
16. Model tool-call request count khác tool execution count ra sao?
17. Trace ID có thay thế business IDs được không?
18. Làm sao nối tool result với follow-up model response?
19. Cần kiểm tra gì khi answer sai nhưng tool result đúng?
20. Làm sao xác định evaluator hoặc reference gây regression?

## 24. Tổng kết

Phản hồi mô hình, kết quả công cụ và kết quả đánh giá là ba loại output có nguồn gốc và semantics khác nhau. Model response có thể là text, structured output, refusal hoặc tool call request. Tool result chỉ xuất hiện sau khi ứng dụng validate, authorize và thực thi công cụ. Evaluation result là verdict/score được tạo khi evaluator chấm một artifact theo metric và rubric cụ thể.

Một pipeline Spring AI có tool calling thường có nhiều model calls trong cùng một user turn. Tool call request được nối với tool execution qua IDs riêng; tool result được đưa trở lại conversation với provenance đúng; model có thể tiếp tục sinh final answer; evaluator sau đó chấm answer hoặc tool behavior. Từng bước có execution status riêng, và quality verdict không được trộn với runtime success.

Thiết kế event DTO/schema riêng, correlation IDs, causal links và structured logs giúp điều tra chính xác model đã yêu cầu gì, tool thực sự làm gì và artifact có đạt tiêu chí không. Khi kết hợp metrics với denominator đúng, evidence references có quyền truy cập và JUnit tests cho các trạng thái độc lập, nhóm có thể tìm root cause regression mà không đánh đồng lỗi model, lỗi tool và lỗi đánh giá.

### Tài liệu tham khảo

- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring AI — Chat Model API](https://docs.spring.io/spring-ai/reference/api/chatmodel.html)
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [SLF4J — Manual](https://www.slf4j.org/manual.html)
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [OpenTelemetry — Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/)
- [OpenTelemetry — Logs](https://opentelemetry.io/docs/specs/otel/logs/)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
