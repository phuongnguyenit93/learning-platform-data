# Phân biệt log metadata với nội dung prompt và phản hồi

Một chatbot Spring AI vừa trả lời sai chính sách. Người phát triển muốn điều tra request đã gửi tới model và câu trả lời model trả về. Họ bật DEBUG cho toàn bộ HTTP client, in đối tượng ChatClient request ra log và ghi response body để “dễ debug”. Chỉ trong vài phút, log tập trung đã chứa prompt hệ thống, câu hỏi người dùng, đoạn tài liệu nội bộ được truy xuất, tool arguments và nội dung trả lời. Các dữ liệu này được sao chép sang nhiều collector, search index, dashboard và bản sao lưu; người có quyền đọc log rộng hơn nhiều so với người được phép xem dữ liệu gốc.

Đây là một lỗi thiết kế observability thường gặp: **metadata mô tả một lần tương tác AI bị trộn với chính nội dung của tương tác đó**.

Metadata cho biết request nào, model/provider nào, prompt version nào, chạy trong bao lâu, dùng bao nhiêu token, kết thúc với trạng thái nào và có evidence reference nào. Nội dung prompt/response là payload thực tế: system/developer instructions, user messages, conversation history, retrieved context, tool arguments/results và model output. Hai nhóm dữ liệu phục vụ những mục đích khác nhau và cần chính sách lưu trữ, quyền truy cập, thời hạn lưu và cách xử lý riêng.

Trong module **SPRING_AI_EVALUATION_OBSERVABILITY**, bài học này giúp thiết kế ranh giới giữa log metadata và content evidence. Mục tiêu là điều tra được chất lượng, latency, chi phí và lỗi của Spring AI mà không vô tình đưa raw prompt hoặc response vào log stream. Khi cần xem nội dung để đánh giá, hệ thống dùng cơ chế capture có kiểm soát trong evidence store; log chỉ giữ metadata và reference đã được phép.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt metadata, prompt content, response content, retrieved context và tool payload.
2. Giải thích vì sao log metadata và content evidence cần hai chính sách khác nhau.
3. Thiết kế event schema chỉ chứa metadata đã được allowlist.
4. Theo dõi model/provider, prompt version, token usage, latency và outcome mà không ghi raw content.
5. Xác định các điểm trong Spring AI, SDK, HTTP client và logging framework có thể làm lộ prompt/response.
6. Tách application logs khỏi kho evidence có mã hóa và access control.
7. Xây content capture policy theo mục đích, môi trường, tenant và data classification.
8. Áp dụng redaction, pseudonymization và retention đúng cách.
9. Hiểu giới hạn của hashing, masking và sampling.
10. Dùng SLF4J/Logback để ghi metadata an toàn.
11. Thiết kế test bảo đảm secret và raw content không xuất hiện trong log.
12. Điều tra một case bằng metadata và evidence reference.
13. Xây runbook xử lý khi phát hiện prompt/response đã lọt vào log.

## 2. Metadata và content trả lời hai loại câu hỏi

**Metadata** mô tả một thao tác đã diễn ra như thế nào. **Content** là dữ liệu thực tế đã được gửi hoặc nhận.

| Nhóm | Ví dụ | Câu hỏi trả lời |
| --- | --- | --- |
| Request metadata | request ID, operation, timestamp | Request nào đã chạy? |
| Model metadata | provider, model ID, parameters | Model nào đã xử lý? |
| Prompt metadata | template version, digest, message count | Prompt được tạo từ phiên bản nào? |
| Usage metadata | input/output tokens, cached tokens | Dùng bao nhiêu tài nguyên? |
| Timing metadata | duration, time to first token | Chậm ở giai đoạn nào? |
| Outcome metadata | finish reason, status, error code | Kết quả thực thi ra sao? |
| Prompt content | system/user/developer messages | Model thực sự nhận nội dung gì? |
| Context content | retrieved chunks, memory, documents | Những dữ liệu nào được đưa vào context? |
| Response content | text, structured output, refusal | Model thực sự trả lời gì? |
| Tool content | arguments, tool result | Model yêu cầu và nhận dữ liệu gì từ tool? |

Ví dụ metadata của một model call:

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
  "prompt.template.version": "support-prompt-v7",
  "prompt.digest": "sha256:...",
  "usage.input_tokens": 1680,
  "usage.output_tokens": 185,
  "duration.ms": 842,
  "outcome": "SUCCESS",
  "prompt.content.status": "NOT_LOGGED",
  "response.content.status": "STORED_AS_EVIDENCE"
}
~~~

Đây là metadata, không có raw prompt hoặc response. Người điều tra vẫn có thể xác định model call và phiên bản prompt; nếu có quyền, họ mở evidence artifact theo reference được quản lý riêng.

### 2.1. Content không chỉ là chuỗi văn bản

Trong ứng dụng AI, content có thể là:

- System/developer instructions.
- User prompt và conversation history.
- Memory hoặc summary được đưa vào model.
- Retrieved documents, chunks và reranker output.
- Tool definitions, arguments và tool results.
- Model text response, JSON output hoặc refusal.
- Image, audio, video, file attachments hoặc multimodal payload.
- Embeddings hoặc dữ liệu trung gian có thể tiết lộ nội dung nguồn.

Không giả định rằng chỉ field tên prompt hoặc response mới chứa dữ liệu nhạy cảm. Một exception message, URL, tool result, document title hoặc trace attribute cũng có thể chứa content.

## 3. Vì sao không nên trộn metadata với raw content

Raw content trong log gây ra nhiều vấn đề đồng thời.

**Quyền truy cập bị mở rộng.** Log thường được đọc bởi developer, SRE, support, security và hệ thống bên thứ ba. Những người này có thể không được phép xem conversation hoặc tài liệu gốc.

**Dữ liệu bị nhân bản.** Một log event có thể được forward tới collector, search cluster, archive, backup và SIEM. Xóa một bản không bảo đảm xóa hết bản sao.

**Retention không phù hợp.** Operational logs thường giữ theo ngày/tuần; evaluation evidence có thể cần retention khác. Gộp chúng khiến việc xóa hoặc giữ đúng mục đích khó hơn.

**Chi phí tăng.** Prompt/context dài làm tăng log volume, indexing cost và network traffic.

**Cardinality và truy vấn kém.** Raw text không phải field tốt để group/aggregate; dữ liệu lớn khiến index nặng và query chậm.

**Nguy cơ prompt injection vào công cụ vận hành.** User content có thể chứa newline, terminal escape, HTML hoặc chuỗi giả dạng log entry. Raw content trong log viewer có thể gây hiểu nhầm hoặc khai thác parser.

**Rò rỉ secrets và dữ liệu cá nhân.** Prompt có thể chứa API keys, account IDs, email, thông tin hợp đồng, dữ liệu sức khỏe hoặc thông tin nội bộ.

**Khó kiểm soát downstream.** Một khi content vào log pipeline, các consumer có thể tạo dashboard/export mà không biết dữ liệu gốc thuộc classification nào.

### 3.1. Log level không phải privacy boundary

Đặt raw prompt ở DEBUG không làm nó an toàn. DEBUG có thể được bật tạm thời trong production, được thu thập ở staging hoặc được giữ trong file local. Không dựa vào log level để bảo vệ content.

### 3.2. Sampling không phải redaction

Sampling giảm số event được ghi; nó không loại bỏ content nhạy cảm khỏi các event còn lại. Một prompt bị ghi trong 1% request vẫn có thể là sự cố dữ liệu.

### 3.3. Hash không thay thế content policy

Digest giúp kiểm tra tính toàn vẹn tương đối với một giá trị tin cậy. Nó không biến dữ liệu nhạy cảm thành dữ liệu vô hại, không chứng minh nội dung đúng và không cho phép người xem hiểu ngữ nghĩa của prompt.

## 4. Phân loại dữ liệu trước khi thiết kế log

Một schema tốt bắt đầu từ data classification. Mỗi field phải có mục đích, chủ sở hữu, mức nhạy cảm và chính sách xử lý.

| Classification | Ví dụ | Cách xử lý |
| --- | --- | --- |
| PUBLIC | event name, operation type công khai | Có thể log theo policy |
| INTERNAL | service version, model family, stage | Log theo quyền vận hành |
| CONFIDENTIAL | tenant pseudonym, document reference, prompt digest | Hạn chế truy cập và retention |
| SENSITIVE_CONTENT | prompt, response, retrieved context, tool payload | Không log mặc định; evidence store có kiểm soát |
| SECRET | API key, password, bearer token, signing key | Không ghi vào log hoặc evidence thông thường |

Tên classification là ví dụ của policy tổ chức. Điều quan trọng là có định nghĩa rõ và áp dụng thống nhất.

### 4.1. Metadata cũng có thể nhạy cảm

Một document ID có thể tiết lộ mã khách hàng. Model route có thể tiết lộ chiến lược nội bộ. Prompt digest có thể cho phép liên kết hai request cùng nội dung. Tenant ID hoặc case ID có thể là dữ liệu định danh.

Vì vậy, “metadata” không đồng nghĩa “public”. Mỗi field metadata vẫn cần được đánh giá sensitivity và quyền truy cập.

### 4.2. Content có thể xuất hiện trong field không ngờ tới

Các nguồn dễ bỏ sót:

- exception message chứa request body hoặc URL query.
- HTTP wire logging chứa headers và body.
- SDK debug log chứa serialized request/response.
- Tool arguments được ghi bằng toString().
- JSON serialization của toàn bộ ChatRequest hoặc ChatResponse.
- MDC chứa user input hoặc tenant data.
- Trace span attributes ghi prompt/completion.
- Metrics tags nhận document name hoặc tool argument.
- Access log ghi query string có token.
- Error tracker tự động capture local variables.

Data classification cần bao phủ toàn bộ đường đi, không chỉ logger trong service.

## 5. Thiết kế metadata schema bằng allowlist

Mỗi event type chỉ được chứa các field cần thiết cho mục đích quan sát. Đừng truyền toàn bộ object request vào logger rồi cố xóa field nhạy cảm sau đó.

Một model call metadata schema có thể gồm:

| Field | Kiểu | Mục đích |
| --- | --- | --- |
| event.name | string | Phân loại event |
| event.version | integer | Schema version |
| timestamp | UTC timestamp | Thời điểm |
| service.name | string | Producer |
| environment | enum/string | dev/test/staging/prod |
| run.id | opaque ID | Evaluation run |
| case.id | opaque/pseudonymous ID | Dataset case |
| attempt.id | opaque ID | Execution attempt |
| model.call.id | opaque ID | Model invocation |
| ai.provider | bounded string | Provider |
| ai.model | bounded string | Requested/resolved model |
| prompt.template.version | bounded string | Prompt release |
| prompt.digest | digest | Fingerprint theo policy |
| usage.input_tokens | integer/unknown | Input usage |
| usage.output_tokens | integer/unknown | Output usage |
| duration.ms | number | Latency |
| outcome | enum | SUCCESS/FAILURE |
| content.capture.status | enum | NOT_CAPTURED/STORED/REDACTED |
| evidence.ref | opaque reference | Evidence lookup nếu được phép |
| trace.id/span.id | tracing IDs | Correlation nếu có |

### 5.1. Không log raw text trong field metadata

Không dùng các field như:

- prompt.preview
- response.summary
- first.200.characters
- user.question
- retrieved.document.text
- tool.arguments.json

Một preview ngắn vẫn là content. Nếu tổ chức cho phép một số nội dung đã biến đổi, phải định nghĩa classification, redaction và purpose riêng; không mặc định đưa chúng vào operational logs.

### 5.2. Giữ unknown khác zero

Nếu provider không trả token usage, ghi status NOT_PROVIDED hoặc để usage field absent theo schema. Không gán 0. Nếu response bị timeout và chưa biết provider có xử lý request hay không, ghi usage UNKNOWN. Zero là số đo thực tế; unknown là thiếu bằng chứng.

### 5.3. Bounded values

Provider, operation, model family, stage, status và environment nên dùng tập giá trị được kiểm soát. Không đưa prompt text, customer names hoặc URL động vào labels. Field ID có thể có cardinality cao trong logs, nhưng vẫn cần pseudonymization và retention policy.

## 6. Ranh giới dữ liệu qua pipeline Spring AI

Một request có thể biến đổi qua nhiều bước. Mỗi bước cần phân biệt metadata và content.

~~~mermaid
flowchart TD
    A["User request / conversation"] --> B["Prompt assembly"]
    B --> C["Retrieval + memory"]
    C --> D["Effective model request"]
    D --> E["ChatModel / provider"]
    E --> F["Model response"]
    F --> G["Tool execution / post-processing"]
    G --> H["Final answer"]
    B --> L["Metadata logs"]
    C --> L
    D --> L
    E --> L
    F --> L
    G --> L
    H --> L
    D --> X["Secure evidence capture (policy gated)"]
    F --> X
    G --> X
    H --> X
    L --> M["Operational log backend"]
    X --> N["Evidence store with separate ACL/retention"]
~~~

Metadata log có thể ghi prompt version, retrieval count, model ID, duration, token usage, finish reason và status. Evidence capture có thể lưu rendered prompt hoặc answer nếu policy cho phép. Hai đường dữ liệu có quyền và retention khác nhau.

### 6.1. Prompt assembly

Ghi template version, digest, số messages, loại role, số token ước tính và trạng thái capture. Không ghi body của từng message.

### 6.2. Retrieval

Ghi corpus/index version, top-k, result count, selected count, filters version, duration và retrieval evidence reference. Nội dung chunks thuộc content; document IDs có thể nhạy cảm.

### 6.3. Model call

Ghi provider/model, parameters, usage, finish reason, request correlation ID đã được phép, duration và outcome. Prompt và response body cần policy riêng.

### 6.4. Tool execution

Ghi tool name/schema version, validation result, authorization decision, execution status, duration và opaque operation reference. Tool arguments/result có thể chứa dữ liệu nhạy cảm; không serialize nguyên object.

### 6.5. Final answer và evaluation

Ghi answer artifact reference, evaluator ID, rubric version, judge version, metric name/status và score. Không cần copy toàn bộ answer hoặc evaluator feedback vào operational log.

## 7. Prompt content: điều gì thực sự cần lưu?

Một prompt gửi tới model có thể gồm nhiều phần:

- System instructions.
- Developer instructions.
- User message.
- Conversation history.
- Memory/advisor content.
- Retrieved context.
- Tool definitions.
- Response format/schema.
- Provider-specific metadata.

Template file không đủ để tái dựng request thực tế. Nhưng điều đó không có nghĩa raw rendered prompt phải được đưa vào log.

### 7.1. Metadata đủ cho nhiều câu hỏi vận hành

Ví dụ:

~~~json
{
  "event.name": "ai.prompt.assembled",
  "event.version": 1,
  "run.id": "support-eval-v5",
  "case.id": "POLICY-017",
  "attempt.id": "POLICY-017-attempt-1",
  "prompt.template.version": "support-prompt-v7",
  "prompt.template.digest": "sha256:...",
  "prompt.message.count": 4,
  "prompt.role.count.system": 1,
  "prompt.role.count.user": 1,
  "prompt.role.count.assistant": 1,
  "prompt.role.count.context": 1,
  "prompt.token_estimate": 1680,
  "prompt.content.status": "NOT_LOGGED",
  "outcome": "SUCCESS"
}
~~~

Các trường role count là convention của event schema mẫu. Không ghi role body.

### 7.2. Khi nào cần rendered prompt?

Một số câu hỏi quality cần biết model thực sự nhận context nào. Ví dụ groundedness cần actual effective context; prompt regression có thể cần so sánh rendered prompt. Khi đó, dùng evidence capture service riêng với:

- Mục đích capture rõ ràng.
- Policy/approval phù hợp.
- Tenant và environment scope.
- Data classification.
- Redaction profile.
- Encryption at rest và in transit.
- Access control/audit log.
- Retention/deletion policy.
- Content digest và schema version.
- Opaque artifact reference trong logs.

Nếu policy không cho phép capture, ghi NOT_CAPTURED và chấp nhận giới hạn điều tra. Không tự chuyển raw content vào operational log để bù.

### 7.3. Prompt version và digest

Template version xác định bản template. Digest giúp phát hiện nội dung template thay đổi ngoài dự kiến. Digest của rendered prompt có thể tạo khả năng liên kết các request có nội dung giống nhau; đánh giá rủi ro này trước khi log. Không hash secret hoặc dữ liệu nhạy cảm có entropy thấp như một cách pseudonymize.

## 8. Response content: metadata không phải câu trả lời

Model response có thể là plain text, JSON, refusal, tool call hoặc streaming chunks. Metadata giúp biết response hoàn tất thế nào; content là dữ liệu thực tế trả về.

Ví dụ metadata:

~~~json
{
  "event.name": "ai.model.response.completed",
  "event.version": 1,
  "model.call.id": "model-call-8f31",
  "ai.model": "chat-model-stable",
  "finish.reason": "STOP",
  "response.format": "TEXT",
  "response.byte_count": 842,
  "response.content.status": "STORED_AS_EVIDENCE",
  "response.evidence.ref": "evidence-artifact-991",
  "usage.output_tokens": 185,
  "duration.ms": 842,
  "outcome": "SUCCESS"
}
~~~

Byte count và token count là metadata, nhưng có thể tiết lộ phần nào độ dài nội dung. Cân nhắc nếu workload nhạy cảm.

### 8.1. Không log response preview

Các cách sau vẫn ghi content:

- response.substring(0, 200)
- firstLine
- response.toString()
- JSON response body
- “safe summary” do model khác tạo

Một summary có thể chứa dữ liệu cá nhân hoặc bí mật giống raw response. Nếu cần summary, phải có policy và review riêng; không mặc định coi summary là metadata.

### 8.2. Streaming response

Không log từng token/chunk. Có thể ghi:

- time to first token.
- chunk count.
- total output tokens nếu provider cung cấp.
- total duration.
- finish reason.
- stream completion status.
- response evidence reference nếu được phép.

Nếu stream bị cancel giữa chừng, ghi PARTIAL/CANCELLED/UNKNOWN theo semantics; không giả định output đã hoàn tất.

### 8.3. Refusal và safety outcome

Có thể ghi response.outcome=REFUSAL hoặc reason code chuẩn hóa. Không cần ghi toàn bộ refusal text. Nếu cần audit nội dung, lưu secure evidence theo policy.

## 9. Retrieved context, memory và tool payload cũng là content

Prompt/response thường được chú ý, nhưng dữ liệu trung gian có thể nhạy cảm tương đương.

| Dữ liệu | Metadata có thể log | Nội dung cần bảo vệ |
| --- | --- | --- |
| Retrieved documents | corpus version, result count, rank summary | chunk text, title nhạy cảm |
| Conversation memory | memory policy/version, message count | lịch sử hội thoại |
| Tool arguments | tool name, schema version, validation status | arguments thực tế |
| Tool results | result status, duration, opaque operation ref | order/customer/account data |
| Image/audio/file | media type, byte size, processing status | bytes, transcript, OCR |
| Embedding | model/version, dimensions, duration | vector và dữ liệu nguồn có thể suy ra |
| Evaluator feedback | metric, verdict, rubric version | free-form feedback có thể quote answer |

### 9.1. Document IDs có thể tiết lộ thông tin

ID như customer-123-contract-termination có thể tiết lộ nội dung dù không chứa paragraph. Dùng opaque/pseudonymous references hoặc secure evidence IDs. Không log document title nếu title chứa tên người/khách hàng.

### 9.2. Tool arguments không phải metadata

Tool name và schema version là metadata. JSON arguments là content. Đừng log toàn bộ arguments object; chọn status/field an toàn đã được phê duyệt hoặc dùng evidence reference.

### 9.3. Multimodal content

Image/audio/video có thể chứa khuôn mặt, giọng nói, tài liệu, vị trí hoặc dữ liệu nhận dạng. Chỉ log media type, byte size, processing status và opaque ref khi phù hợp. Không lưu base64 hoặc transcript vào operational logs.

## 10. Hai kho dữ liệu với hai chính sách

Thiết kế khuyến nghị tách:

**Operational log store**

- Metadata event và error codes.
- Run/case/attempt correlation IDs theo policy.
- Model/provider/versions.
- Token usage, duration, status.
- Evidence refs opaque.
- Retention ngắn hơn và quyền vận hành.

**Evidence store**

- Rendered prompt, answer, effective context, tool payload hoặc evaluator details nếu được phép.
- Encryption at rest/in transit.
- Tenant-scoped access control.
- Audit log khi đọc.
- Retention theo mục đích và data classification.
- Redaction/version lineage.
- Content digest và immutable artifact IDs.

### 10.1. Không dùng log backend làm evidence store

Log backend thường tối ưu tìm kiếm, aggregation và retention ngắn. Nó không nhất thiết có tenant isolation, per-artifact authorization, deletion workflow hoặc audit access phù hợp với raw content.

### 10.2. Opaque evidence reference

Log có thể lưu:

~~~json
{
  "evidence.ref": "ev_01JVB8K8M4Y7W8N1",
  "evidence.status": "AVAILABLE",
  "evidence.classification": "CONFIDENTIAL"
}
~~~

Reference này không phải URL truy cập trực tiếp. Người xem phải gọi evidence service, service kiểm tra identity, tenant, role, purpose và policy tại thời điểm đọc.

### 10.3. Tránh signed URL trong log

Signed URL có thể là bearer credential. Nếu bị copy sang ticket, chat hoặc search index, người khác có thể mở artifact trong thời gian URL còn hiệu lực. Dùng opaque ID và authorization gateway.

## 11. Content capture policy

Không phải mọi environment hoặc case đều được phép capture raw content. Policy nên được đánh giá tại runtime bằng mục đích, classification, environment, tenant và consent/legal basis nếu có.

Một quyết định capture có thể có các trạng thái:

| Status | Ý nghĩa |
| --- | --- |
| DISABLED | Capture bị tắt theo policy |
| ALLOWED | Có thể lưu artifact theo scope |
| REDACT_ONLY | Chỉ được lưu bản redacted |
| DENIED | Không được phép capture |
| NOT_APPLICABLE | Event không có content |
| FAILED | Policy cho phép nhưng storage/capture thất bại |

### 11.1. Mặc định an toàn

Operational logging mặc định không ghi prompt/response body. Content capture phải là quyết định riêng, bật theo mục đích và scope. Không bật capture toàn cục chỉ vì một case đang khó debug.

### 11.2. Tách môi trường

- Local development: dùng synthetic data hoặc fixture đã được phê duyệt.
- Automated tests: fixture không chứa dữ liệu thật.
- Staging: dùng dữ liệu giả/pseudonymized; capture theo policy.
- Production: capture hạn chế, có purpose, approval và access audit nếu cần.

Environment name không tự tạo quyền capture. Staging vẫn có thể chứa dữ liệu production nếu copy dữ liệu không kiểm soát.

### 11.3. Purpose-bound capture

Một policy có thể cho phép capture một case trong thời gian điều tra incident. Ghi purpose code, ticket/incident reference, scope, expiry và người phê duyệt. Khi hết hạn, policy tự dừng capture và artifact được xử lý theo retention.

### 11.4. Không dùng feature flag làm authorization duy nhất

Feature flag log-prompt=true không đủ. Cần server-side authorization, tenant scope, data classification, expiry và audit. Người vận hành không nên bật raw capture chỉ bằng một toggle thiếu kiểm soát.

## 12. Redaction, masking và pseudonymization

Ba kỹ thuật này không giống nhau.

- Redaction: loại bỏ phần dữ liệu.
- Masking: thay một phần bằng ký tự che, ví dụ ****1234.
- Pseudonymization: thay định danh bằng token/alias có thể liên kết qua key hoặc mapping được kiểm soát.

Ví dụ:

| Input | Redacted | Masked | Pseudonymized |
| --- | --- | --- | --- |
| Email | [REDACTED] | j***@example.com | user_7F2A |
| Account | [REDACTED] | ****4321 | acct_A91C |
| API token | [REDACTED] | Không nên giữ prefix nếu không cần | Không dùng alias có thể đảo ngược tùy tiện |
| Prompt body | Không capture | Không nên chỉ lấy preview | Không hash trực tiếp để giả danh |

### 12.1. Redaction phải theo schema

Một regex email có thể không bắt được phone, account ID, access token, địa chỉ hoặc thông tin nội bộ. Redact theo typed fields và data classification trước khi serialize. Với nội dung tự do, dùng detector phù hợp và coi kết quả là best effort; không tuyên bố bảo đảm xóa mọi dữ liệu nhạy cảm.

### 12.2. Redaction có thể làm mất ý nghĩa đánh giá

Nếu xóa tên entity hoặc số tiền, evaluator có thể không còn kiểm được factual correctness. Cần lưu rõ redaction profile/version và trạng thái evidence. Nếu nội dung redacted không đủ để chấm, verdict phải là NOT_EVALUATED hoặc dùng phương pháp đã được định nghĩa; không suy kết quả từ bản đã mất dữ liệu.

### 12.3. Pseudonymization cần quản lý key/mapping

Hash email trực tiếp có thể bị dò bằng dictionary. Nếu cần liên kết ổn định, dùng keyed HMAC hoặc tokenization service với key được quản lý, rotation và access control. Không ghi key hoặc mapping table vào log.

### 12.4. Redaction lineage

Bản redacted là artifact mới, có reference tới source theo policy, redaction profile/version, timestamp và digest riêng. Không ghi đè raw artifact. Nếu raw artifact bị xóa theo policy, lineage phải ghi trạng thái phù hợp và không giữ bản sao trá hình.

## 13. Hash, digest và giới hạn của nó

Có thể ghi digest của prompt hoặc response để so sánh phiên bản hoặc phát hiện bytes thay đổi, nhưng cần hiểu rõ giới hạn.

**Digest không ẩn mọi thông tin.** Với nội dung có thể đoán hoặc entropy thấp, attacker có thể hash candidate values và so sánh.

**Digest không chứng minh nội dung đúng.** Hash một câu trả lời sai vẫn cho digest hợp lệ.

**Digest không thay thế raw evidence.** Không thể đọc lại prompt từ SHA-256.

**Digest không tự chứng minh nguồn.** Nếu attacker sửa cả artifact và digest ở nơi không được bảo vệ, so sánh vẫn có thể bị đánh lừa.

Nếu cần digest:

- Hash bytes theo canonicalization đã version.
- Dùng SHA-256 hoặc thuật toán được policy phê duyệt.
- Ghi algorithm và canonicalization version.
- Bảo vệ manifest/digest bằng trusted storage hoặc signature khi cần.
- Đánh giá privacy/linkability trước khi log digest.
- Không hash secret values hoặc dữ liệu định danh entropy thấp để pseudonymize.

## 14. Spring AI: các điểm dễ ghi content ngoài ý muốn

Ứng dụng có thể không gọi logger trực tiếp mà content vẫn đi vào log.

### 14.1. ChatClient request/response logging

Tránh log toàn bộ ChatClient prompt hoặc response object. Một object có thể chứa messages, metadata, tool calls và content. Ghi event DTO đã allowlist.

### 14.2. Observation/trace conventions

Spring AI dùng observation/metrics integration trong hệ sinh thái Micrometer. Tùy phiên bản, observation convention và cấu hình, prompt/completion content có thể được thêm vào observation metadata khi bật các tùy chọn capture tương ứng. Kiểm tra tài liệu đúng version đang dùng; không giả định mọi span chỉ có metadata.

Nếu policy yêu cầu metadata-only:

- Không bật prompt/completion capture trong observations.
- Kiểm tra span attributes thực tế ở exporter.
- Không thêm raw content qua custom observation convention.
- Dùng opaque evidence refs nếu cần liên kết.
- Test cả in-memory span và exported telemetry.

### 14.3. HTTP client wire logging

HTTP client debug có thể ghi URL, headers, request body và response body. Với AI provider, body thường chính là prompt và response. Không bật wire logging toàn bộ trong production. Nếu cần debug protocol, dùng synthetic payload và môi trường cô lập hoặc sanitizer đã kiểm chứng.

### 14.4. SDK debug logging

Một số SDK tự ghi request/response hoặc provider error body. Kiểm tra logger categories và dependency versions. Không dựa vào việc application code không in prompt để kết luận log stream an toàn.

### 14.5. Exception và retry wrappers

Exception có thể giữ request body, response body, endpoint URL hoặc header. Không log exception message/stack trace vào index rộng mà chưa đánh giá. Tạo safe error code, status, retry disposition và provider request ID đã được phép.

### 14.6. Actuator và configuration diagnostics

Endpoint diagnostics có thể hiển thị property values, bean state hoặc environment. Bảo vệ management endpoints, sanitize sensitive keys và không dump response của endpoint vào log thường.

### 14.7. Tool callback

Tool callback nhận arguments và trả result. Không gọi toString() trên arguments hoặc serialize object để debug. Ghi tool name/schema, validation, authorization, duration, outcome và opaque operation/evidence reference.

## 15. Java: metadata DTO không có raw content

Tạo DTO chuyên biệt cho metadata. Vì raw prompt/response không phải field của type này, logger khó vô tình serialize chúng.

~~~java
import java.time.Instant;
import java.util.Objects;

public record ModelInteractionMetadata(
        Instant timestamp,
        String eventName,
        int eventVersion,
        String runId,
        String caseId,
        String attemptId,
        String modelCallId,
        String provider,
        String requestedModel,
        String promptVersion,
        String promptDigest,
        Integer inputTokens,
        Integer outputTokens,
        long durationMs,
        String outcome,
        String contentCaptureStatus,
        String evidenceRef) {

    public ModelInteractionMetadata {
        Objects.requireNonNull(timestamp);
        Objects.requireNonNull(eventName);
        Objects.requireNonNull(provider);
        Objects.requireNonNull(requestedModel);
        Objects.requireNonNull(outcome);
        Objects.requireNonNull(contentCaptureStatus);

        if (eventVersion < 1) {
            throw new IllegalArgumentException("eventVersion must be >= 1");
        }
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

Đây là metadata DTO; prompt body, response body, tool arguments và headers không xuất hiện. Trong hệ thống thực, dùng enum cho outcome/capture status và validate provider/model values theo schema.

### 15.1. SLF4J logger chỉ nhận metadata DTO

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class ModelMetadataLogger {

    private static final Logger log =
            LoggerFactory.getLogger(ModelMetadataLogger.class);

    public void completed(ModelInteractionMetadata event) {
        var builder = log.atInfo()
                .addKeyValue("event.name", event.eventName())
                .addKeyValue("event.version", event.eventVersion())
                .addKeyValue("run.id", event.runId())
                .addKeyValue("case.id", event.caseId())
                .addKeyValue("attempt.id", event.attemptId())
                .addKeyValue("model.call.id", event.modelCallId())
                .addKeyValue("ai.provider", event.provider())
                .addKeyValue("ai.model.requested", event.requestedModel())
                .addKeyValue("prompt.template.version", event.promptVersion())
                .addKeyValue("duration.ms", event.durationMs())
                .addKeyValue("outcome", event.outcome())
                .addKeyValue("content.capture.status",
                        event.contentCaptureStatus());

        if (event.promptDigest() != null) {
            builder.addKeyValue("prompt.digest", event.promptDigest());
        }
        if (event.inputTokens() != null) {
            builder.addKeyValue("usage.input_tokens", event.inputTokens());
        }
        if (event.outputTokens() != null) {
            builder.addKeyValue("usage.output_tokens", event.outputTokens());
        }
        if (event.evidenceRef() != null) {
            builder.addKeyValue("evidence.ref", event.evidenceRef());
        }

        builder.log("AI model interaction completed");
    }
}
~~~

Yêu cầu SLF4J 2.x fluent API và backend/encoder xuất key-value pairs. Không thêm logger DEBUG ghi prompt ở nơi gọi method này.

### 15.2. Đừng truyền ChatResponse vào DTO

Chỉ trích xuất metadata cần thiết từ response: finish reason, usage, model metadata, provider request ID và status. Không truyền nguyên ChatResponse, Generation hoặc Message object sang logger.

## 16. Content capture qua evidence service

Khi cần lưu prompt/response cho evaluation, gọi một service riêng. Service này kiểm tra policy và ghi artifact vào store có encryption, access control và audit. Logger chỉ nhận kết quả capture metadata.

~~~java
public enum CaptureDecision {
    ALLOWED,
    REDACT_ONLY,
    DENIED,
    DISABLED
}

public enum EvidenceStatus {
    STORED,
    REDACTED,
    NOT_CAPTURED,
    DENIED,
    FAILED
}

public record EvidenceCapturePolicy(
        CaptureDecision decision,
        String purposeCode,
        String classification,
        String redactionProfile,
        String retentionPolicy,
        String tenantScope) {}

public record EvidenceArtifactMetadata(
        String artifactId,
        String artifactType,
        String contentDigest,
        String classification,
        String redactionProfile,
        String retentionPolicy) {}

public record EvidenceCaptureResult(
        EvidenceStatus status,
        String evidenceRef,
        String contentDigest) {}
~~~

Các type trên là contract minh họa. Hệ thống thật nên validate policy và dùng enum/schema version có kiểm soát.

### 16.1. Store contract

~~~java
public interface SecureEvidenceStore {

    EvidenceArtifactMetadata store(
            String artifactType,
            byte[] approvedContent,
            EvidenceCapturePolicy policy,
            String parentAttemptId);
}

public interface ContentRedactor {
    byte[] redact(
            String artifactType,
            byte[] rawContent,
            String redactionProfile);
}
~~~

Contract cần quy định store mã hóa dữ liệu, enforce tenant/role authorization, ghi access audit, kiểm retention và trả artifact ID opaque. Không trả signed URL lâu hạn để đưa vào log.

### 16.2. Quy tắc capture

1. Đánh giá policy trước khi persist.
2. Nếu DISABLED hoặc DENIED, không gọi storage.
3. Nếu ALLOWED, persist theo encryption và ACL.
4. Nếu REDACT_ONLY, redactor chạy trước storage.
5. Nếu redactor lỗi, không fallback sang lưu raw.
6. Nếu storage lỗi, trả FAILED và log metadata lỗi đã sanitize.
7. Trả opaque artifact ID; không trả bearer URL vào log.
8. Ghi capture status, classification, redaction profile và retention metadata.

Đây là ranh giới kiến trúc quan trọng: logger không nhận raw content; evidence service là thành phần duy nhất được phép xử lý capture theo policy.

### 16.3. Fail closed khi policy không rõ

Nếu policy service không truy cập được, không tự chuyển sang ALLOWED. Với capture raw content, lựa chọn an toàn thường là không capture và ghi FAILED/NOT_CAPTURED theo semantics đã định nghĩa. Business request có thể tiếp tục nếu evidence không bắt buộc; release/evaluation workflow có thể phải dừng nếu evidence là điều kiện bắt buộc.

### 16.4. Không log lỗi storage kèm content

Khi evidence store lỗi, log error code, artifact type, attempt ID, storage backend và retry disposition. Không log byte array, raw prompt, response hoặc exception message chưa sanitize.

## 17. Redaction trước capture và sau capture

Nếu policy chỉ cho lưu bản redacted, redaction phải diễn ra trước khi bytes được gửi tới store.

~~~mermaid
flowchart TD
    A["Raw prompt/response in memory"] --> B["Policy decision"]
    B -->|DENIED / DISABLED| C["Do not persist content"]
    B -->|ALLOWED| D["Secure encrypted evidence store"]
    B -->|REDACT_ONLY| E["Schema-aware redactor"]
    E --> F["Validate redaction result"]
    F --> G["Secure evidence store"]
    D --> H["Opaque artifact reference"]
    G --> H
    H --> I["Metadata log"]
~~~

### 17.1. Redaction failure

Nếu redactor lỗi hoặc không chắc chắn, không fallback sang lưu raw. Ghi capture status FAILED hoặc DENIED theo policy và báo evidence gap.

### 17.2. Không coi masking là xóa dữ liệu

Masking một phần email hoặc account có thể vẫn đủ để nhận diện. Đánh giá khả năng liên kết và re-identification. Với secret, không giữ prefix/suffix nếu không có nhu cầu rõ ràng.

### 17.3. Redaction profile có version

Ghi redaction profile/version và thời điểm áp dụng. Khi thay thuật toán, có thể cần tạo artifact mới; không sửa âm thầm artifact cũ đã dùng cho report.

## 18. Trace và metrics không nên chứa content

Observability không chỉ là log. Prompt/response cũng có thể lọt vào trace attributes, metric labels hoặc exemplars nếu instrumentation được cấu hình không cẩn thận.

### 18.1. Trace attributes

Dùng các field metadata như operation, provider, model family, stage, status và version. Không thêm raw prompt, response, retrieved chunks, tool arguments hoặc user identity vào span attributes mặc định.

Trace ID/span ID dùng để correlation, không phải bằng chứng nội dung.

### 18.2. Metrics labels

Labels nên có cardinality thấp:

- provider.
- model family.
- operation.
- stage.
- outcome.
- environment.
- bounded error code.

Không dùng prompt text, response text, case ID, tenant ID, trace ID, document ID hoặc tool arguments làm metric labels.

### 18.3. Exemplars

Exemplar có thể mang trace ID để mở trace tương ứng. Nó không nên chứa raw content hoặc PII. Kiểm tra exemplar exporter và backend policy.

### 18.4. Spring AI observation configuration

Kiểm tra đúng Spring AI/Spring Boot/Micrometer version đang triển khai. Một số instrumentation có tùy chọn include prompt/completion hoặc content-bearing metadata. Nếu yêu cầu metadata-only, đặt capture content ở trạng thái tắt và test exported spans. Đừng dựa vào cấu hình mặc định của phiên bản khác.

## 19. Error handling và exception sanitization

Exception có thể chứa nhiều dữ liệu hơn tên class và status code. Ví dụ HTTP client exception có request URL, response body, headers hoặc serialized prompt.

Một error event an toàn có thể ghi:

~~~json
{
  "event.name": "ai.model.call.failed",
  "event.version": 1,
  "run.id": "support-eval-v5",
  "case.id": "POLICY-017",
  "attempt.id": "POLICY-017-attempt-1",
  "model.call.id": "model-call-8f31",
  "ai.provider": "example-provider",
  "error.code": "AI_PROVIDER_RATE_LIMITED",
  "error.category": "DEPENDENCY",
  "error.retryable": true,
  "retry.after.ms": 2000,
  "error.message.safe": "Provider rate limit reached",
  "exception.type": "ProviderRateLimitException",
  "request.content.status": "NOT_LOGGED",
  "trace.id": "actual-trace-id"
}
~~~

### 19.1. Safe error mapping

Tạo adapter chuyển exception thành:

- error code ổn định.
- exception type/class.
- provider HTTP status hoặc SDK code.
- retry disposition.
- sanitized message.
- provider request ID nếu policy cho phép.

Không ghi exception message nguyên bản vào index rộng nếu chưa kiểm tra. Stack trace có thể được giữ ở sink hạn chế; nhưng vẫn cần kiểm tra cause chain và suppressed exceptions.

### 19.2. Tránh duplicate logging

Các layer thấp có thể rethrow; chỉ boundary quyết định retry/fail nên phát actionable error event chính. Nếu mỗi layer log nguyên exception, content có thể bị lặp nhiều lần ở nhiều nơi.

### 19.3. HTTP wire logs

Đặt riêng policy cho HTTP request/response logging. Production nên tắt body/header logging với AI provider trừ khi có cơ chế sanitize được kiểm thử, scope rất hẹp và thời gian giới hạn. Không bật toàn bộ wire log để điều tra một case.

## 20. Retention, access control và deletion

Metadata log và content evidence không nên dùng cùng retention policy.

| Store | Dữ liệu | Chính sách gợi ý |
| --- | --- | --- |
| Operational logs | metadata, error codes, durations | Retention theo vận hành và compliance |
| Metrics | aggregate measurements | Retention theo observability backend |
| Traces | spans và bounded attributes | Sampling/retention theo tracing policy |
| Evidence store | prompt/response/context/tool payload | Purpose-bound retention, strict ACL |
| Audit store | ai đã truy cập/thay đổi/phê duyệt | Integrity và retention theo audit policy |

### 20.1. Access control ở thời điểm đọc

Không chỉ kiểm quyền lúc capture. Mỗi lần mở evidence phải kiểm user/service identity, tenant, purpose, artifact classification và policy hiện tại. Quyền truy cập có thể bị thu hồi sau khi artifact được tạo.

### 20.2. Access audit

Ghi ai đã xem artifact, thời điểm, purpose, authorization decision và artifact ID. Không ghi raw content vào access audit log.

### 20.3. Deletion và retention expiry

Khi artifact hết hạn hoặc bị xóa theo policy, cập nhật trạng thái evidence và giữ metadata tối thiểu được phép. Không giữ raw content trong log, cache, trace hoặc backup khác để né deletion. Phải hiểu retention của bản sao và downstream exports.

### 20.4. Incident containment

Nếu raw prompt/response đã lọt vào log:

1. Dừng nguồn phát log content.
2. Giới hạn quyền truy cập index và exports liên quan.
3. Xác định phạm vi thời gian, service, tenant và sink.
4. Xác định loại dữ liệu và secrets/PII có thể xuất hiện.
5. Áp dụng deletion/retention hold theo incident policy.
6. Rotate/revoke credentials nếu secret có thể bị lộ.
7. Ghi audit/incident record không chứa lại raw content.
8. Kiểm thử cấu hình mới để xác nhận không còn capture ngoài ý muốn.

Không tự xóa log theo cách phá hủy evidence của incident; thực hiện theo security/privacy response policy.

## 21. JUnit: kiểm metadata DTO và ngăn content fields

Test sau kiểm tra metadata DTO không có component dành cho raw prompt/response.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.RecordComponent;
import java.time.Instant;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

class ModelInteractionMetadataTest {

    @Test
    void metadataRecordDoesNotContainRawContentFields() {
        Set<String> names = Arrays.stream(
                        ModelInteractionMetadata.class.getRecordComponents())
                .map(RecordComponent::getName)
                .collect(Collectors.toSet());

        assertFalse(names.contains("prompt"));
        assertFalse(names.contains("response"));
        assertFalse(names.contains("context"));
        assertFalse(names.contains("toolArguments"));
        assertFalse(names.contains("requestBody"));
    }

    @Test
    void metadataRequiresValidVersionAndNonNegativeDuration() {
        assertThrows(IllegalArgumentException.class, () ->
                new ModelInteractionMetadata(
                        Instant.now(),
                        "ai.model.call.completed",
                        0,
                        "run-1",
                        "case-1",
                        "attempt-1",
                        "call-1",
                        "provider-a",
                        "model-a",
                        "prompt-v1",
                        null,
                        null,
                        null,
                        100,
                        "SUCCESS",
                        "NOT_LOGGED",
                        null));

        assertThrows(IllegalArgumentException.class, () ->
                new ModelInteractionMetadata(
                        Instant.now(),
                        "ai.model.call.completed",
                        1,
                        "run-1",
                        "case-1",
                        "attempt-1",
                        "call-1",
                        "provider-a",
                        "model-a",
                        "prompt-v1",
                        null,
                        null,
                        null,
                        -1,
                        "SUCCESS",
                        "NOT_LOGGED",
                        null));
    }
}
~~~

### 21.1. Capture policy tests

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class EvidenceCapturePolicyTest {

    @Test
    void disabledCaptureDoesNotReturnArtifactReference() {
        var result = new EvidenceCaptureResult(
                EvidenceStatus.NOT_CAPTURED,
                null,
                null);

        assertEquals(EvidenceStatus.NOT_CAPTURED, result.status());
        assertNull(result.evidenceRef());
        assertNull(result.contentDigest());
    }

    @Test
    void deniedCaptureDoesNotReturnArtifactReference() {
        var result = new EvidenceCaptureResult(
                EvidenceStatus.DENIED,
                null,
                null);

        assertEquals(EvidenceStatus.DENIED, result.status());
        assertNull(result.evidenceRef());
    }

    @Test
    void storedCaptureUsesOpaqueReference() {
        var result = new EvidenceCaptureResult(
                EvidenceStatus.STORED,
                "ev_01JVB8K8M4Y7W8N1",
                "sha256:abc123");

        assertTrue(result.evidenceRef().startsWith("ev_"));
        assertFalse(result.evidenceRef().contains("https://"));
    }
}
~~~

Đây là test contract minh họa, không phải integration test của evidence store. Test thực cần kiểm rằng DENIED/DISABLED không gọi storage, REDACT_ONLY chỉ gửi bytes đã redact, policy service lỗi fail closed, storage failure không log content và access control chặn tenant khác.

### 21.2. Log output test

Dùng appender test/in-memory encoder để capture JSON event. Assert:

- event.name, model, duration và usage có đúng type.
- prompt/response text và secret sentinel không xuất hiện.
- evidence ref là opaque ID.
- trace/span IDs có đúng correlation nếu context tồn tại.
- null usage không biến thành zero.
- MDC không còn dữ liệu sau khi request kết thúc.

Một unit test trên DTO không đủ để chứng minh toàn bộ logging pipeline an toàn. Cần integration test với logger backend, HTTP client, SDK logger và tracing exporter thực tế.

## 22. Quy trình điều tra chất lượng mà không mở raw content trong log

Ví dụ report cho biết factual correctness của POLICY-017 FAIL.

1. Tìm verdict event theo run/case/attempt IDs.
2. Kiểm tra prompt template version/digest, model/provider và config snapshot.
3. Kiểm tra retrieval count, selected chunk count, corpus/index version và duration.
4. Kiểm tra input/output token usage, finish reason và model latency.
5. Kiểm tra content capture status.
6. Nếu evidence AVAILABLE và người điều tra có quyền, mở evidence qua secure evidence service.
7. Đối chiếu rendered prompt, effective context, answer và reference facts.
8. Nếu evidence NOT_CAPTURED, ghi rõ giới hạn; không tìm raw prompt trong log index bằng cách tăng quyền tùy tiện.
9. Dùng trace spans để phân tích timing và dependency path.
10. Ghi root cause và corrective action bằng metadata/evidence references.

### 22.1. Ví dụ so sánh hai run

| Metadata | Baseline | Candidate |
| --- | --- | --- |
| Prompt version | v6 | v7 |
| Model | model-A | model-A |
| Corpus | policy-v3 | policy-v3 |
| Retrieved count | 5 | 5 |
| Selected chunks | 3 | 1 |
| Input tokens | 1.520 | 840 |
| Model latency | 780 ms | 620 ms |
| Factual verdict | PASS | FAIL |
| Evidence status | AVAILABLE | AVAILABLE |

Metadata gợi ý context assembly thay đổi; evidence refs cho phép reviewer có quyền mở actual context và answer để xác minh. Không thể kết luận nguyên nhân chỉ từ token count hoặc selected chunk count.

### 22.2. Khi content không được capture

Có thể vẫn điều tra nhiều câu hỏi:

- Model/provider/route nào?
- Prompt template version nào?
- Retrieval trả bao nhiêu chunks?
- Token usage và latency ra sao?
- Có timeout, retry hoặc malformed response không?
- Tool authorization/operation status thế nào?
- Verdict và rubric version nào?

Nhưng không thể khẳng định nội dung model đã nhận hoặc đã trả lời nếu evidence không tồn tại. Ghi rõ phần chưa thể kết luận.

## 23. Checklist rà soát các đường rò content

Trước khi đưa service vào production, rà soát từng nguồn:

- [ ] Application logger không serialize ChatClient request/response.
- [ ] Không có prompt/response preview ở INFO/WARN/DEBUG.
- [ ] SLF4J/Logback encoder không nhận object chứa raw content.
- [ ] HTTP wire logging không ghi body hoặc secret headers.
- [ ] Provider SDK debug logs được kiểm tra.
- [ ] Exception message/cause chain đã được đánh giá.
- [ ] Spring AI observation settings không capture prompt/completion ngoài policy.
- [ ] Custom observation conventions không thêm content attributes.
- [ ] Trace exporter không gửi raw prompt/context/tool payload.
- [ ] Metrics labels không chứa content hoặc identifiers không bounded.
- [ ] Tool arguments/results không bị log qua toString().
- [ ] MDC chỉ chứa opaque correlation metadata.
- [ ] Actuator/config diagnostics được bảo vệ và sanitize.
- [ ] Error tracker không tự capture request body/local variables nhạy cảm.
- [ ] Log collector/index/backup có ACL và retention đúng.
- [ ] Evidence store có encryption, tenant isolation, access audit và deletion.
- [ ] Content capture policy fail closed khi không xác định.
- [ ] Redaction profile/version được lưu.
- [ ] Synthetic sentinel tests không tìm thấy secret/raw content trong log.
- [ ] Incident runbook có bước containment và deletion phù hợp.

## 24. Bài thực hành: xây ranh giới metadata và content

**Bối cảnh:** một chatbot Spring AI sử dụng RAG và tool getOrderStatus. Nhóm cần đánh giá factual correctness, lưu evidence cho một số case được phê duyệt và vận hành log metadata cho toàn bộ request.

### Phần A — Data inventory

Liệt kê các nguồn: user input, system prompt, conversation history, memory, retrieved chunks, effective context, model response, tool arguments/results, evaluator feedback, exception và telemetry attributes.

Phân loại PUBLIC, INTERNAL, CONFIDENTIAL, SENSITIVE_CONTENT hoặc SECRET. Ghi mục đích, owner, retention và access group.

**Đầu ra:** data inventory và classification matrix.

### Phần B — Metadata event schema

Thiết kế event cho prompt assembled, retrieval completed, model call completed, tool call completed và evaluation verdict. Chỉ dùng allowlisted metadata, không có raw text.

**Đầu ra:** JSON Schema và event fixtures.

### Phần C — Evidence capture

Tạo EvidenceCapturePolicy với DISABLED, ALLOWED, REDACT_ONLY và DENIED. Xây secure store adapter trả opaque artifact ID. Kiểm tenant scope, purpose, retention, encryption và access audit.

**Đầu ra:** evidence capture service và policy tests.

### Phần D — Spring AI instrumentation

Kiểm tra ChatClient/ChatModel observations, SDK logger, HTTP client wire logging, Logback và tracing exporter. Đặt metadata-only policy; test exported logs/spans.

**Đầu ra:** cấu hình và integration tests chứng minh không có prompt/response content trong operational logs.

### Phần E — Điều tra regression

Tạo hai run có prompt version khác nhau. So sánh model, token usage, retrieval counts, duration, outcome và evidence refs. Mở content chỉ qua evidence service với quyền phù hợp.

**Đầu ra:** regression investigation report có metadata và evidence lineage.

### Phần F — Incident drill

Mô phỏng một secret sentinel lọt vào HTTP debug log. Xác định sink bị ảnh hưởng, dừng nguồn phát, giới hạn quyền, kiểm tra exports/backups, áp dụng deletion/rotation theo policy và thêm test ngăn tái diễn.

**Đầu ra:** incident runbook và containment evidence.

### Checklist nghiệm thu

- [ ] Metadata và content được định nghĩa riêng.
- [ ] Mỗi event chỉ chứa field được allowlist.
- [ ] Prompt/response raw không xuất hiện trong operational logs.
- [ ] Prompt version/digest được ghi theo policy.
- [ ] Retrieved context và tool payload được phân loại là content.
- [ ] Unknown usage không bị chuyển thành zero.
- [ ] Evidence capture có purpose, scope và retention.
- [ ] Capture policy fail closed.
- [ ] Redaction xảy ra trước khi persist.
- [ ] Redaction failure không fallback sang raw content.
- [ ] Evidence refs opaque, không phải signed URLs.
- [ ] Evidence store enforce tenant ACL và access audit.
- [ ] Spring AI observation content capture được kiểm soát.
- [ ] HTTP/SDK wire logging không làm lộ body/headers.
- [ ] Exception messages đã được sanitize.
- [ ] Metrics labels và trace attributes không chứa raw content.
- [ ] JUnit tests kiểm DTO, capture decision và redaction.
- [ ] Integration tests kiểm JSON logs và exported spans.
- [ ] Retention/deletion áp dụng cả downstream copies.
- [ ] Runbook có containment khi content lọt vào log.

### Câu hỏi tự kiểm tra

1. Metadata khác prompt content ở điểm nào?
2. Vì sao một prompt preview ngắn vẫn là content?
3. Những field metadata nào vẫn có thể nhạy cảm?
4. Vì sao log level DEBUG không phải privacy boundary?
5. Template version có đủ để biết model đã nhận nội dung gì không?
6. Khi nào rendered prompt nên được capture?
7. Evidence store khác log backend như thế nào?
8. Vì sao evidence reference không nên là signed URL?
9. Redaction khác masking và pseudonymization ra sao?
10. Vì sao hash email không phải pseudonymization an toàn?
11. Digest có thể chứng minh answer đúng không?
12. Vì sao retrieval chunks và tool arguments cũng là content?
13. Spring AI observations có thể làm lộ prompt/completion ở đâu?
14. HTTP wire logging có thể ghi dữ liệu nào?
15. Khi provider không trả token usage, log nên biểu diễn thế nào?
16. Khi content capture policy service lỗi, hành vi an toàn là gì?
17. Vì sao trace attributes và metrics labels cần metadata-only policy?
18. Nếu evidence NOT_CAPTURED, những kết luận nào không thể đưa ra?
19. Làm sao kiểm tra raw content không lọt vào log pipeline?
20. Khi phát hiện prompt/response đã lọt vào log, cần containment bước nào?

## 25. Tổng kết

Metadata và prompt/response content là hai loại dữ liệu khác nhau. Metadata mô tả request, model, prompt version, usage, latency, status và correlation; content gồm system/user messages, conversation history, retrieved context, tool arguments/results và model response. Metadata có thể phục vụ operational logs, metrics và traces theo schema đã kiểm soát. Content cần data classification, purpose, capture policy, encryption, access control, audit và retention riêng.

Một thiết kế an toàn dùng allowlist metadata DTO và không serialize toàn bộ ChatRequest, ChatResponse, exception hoặc configuration object. Spring AI observations, SDK debug logging, HTTP wire logs, trace exporters, tool callbacks và error trackers đều có thể trở thành đường rò content. Vì vậy cần kiểm tra toàn bộ pipeline, không chỉ các lệnh logger do ứng dụng viết.

Khi cần review nội dung để đánh giá chất lượng, capture có kiểm soát vào evidence store và chỉ log opaque reference. Redaction phải diễn ra trước khi persist, policy không rõ phải fail closed, và missing evidence phải được báo rõ. Hash/digest hỗ trợ kiểm tra integrity nhưng không thay thế raw evidence hoặc chứng minh nội dung đúng.

Với ranh giới rõ ràng giữa metadata và content, nhóm có thể theo dõi chất lượng, latency, token usage và lỗi của Spring AI trên toàn bộ traffic mà vẫn giữ quyền truy cập nội dung ở đúng phạm vi. Đây là nền tảng để điều tra regression có trách nhiệm và vận hành hệ thống AI an toàn.

### Tài liệu tham khảo

- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot — Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html#features.logging.structured)
- [SLF4J — Manual](https://www.slf4j.org/manual.html)
- [Logback — Architecture](https://logback.qos.ch/manual/architecture.html)
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [OpenTelemetry — Logs](https://opentelemetry.io/docs/specs/otel/logs/)
- [OpenTelemetry — Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
