# Phân loại prompt, tài liệu, phản hồi và đối số công cụ trong telemetry Spring AI

Một request gửi tới chatbot hỗ trợ khách hàng có thể chứa tên, email, số đơn hàng và nội dung trao đổi riêng tư. Ứng dụng truy xuất tài liệu nội bộ, ghép nội dung vào prompt, gọi model, thực thi tool rồi ghi trace để điều tra khi có lỗi. Nếu instrumentation lưu nguyên prompt, tool arguments, HTTP headers hoặc response vào telemetry, một yêu cầu vốn chỉ được phép xử lý trong phạm vi ứng dụng có thể bị sao chép sang nhiều hệ thống khác: log platform, tracing backend, metrics store, collector, dashboard, bản sao lưu và tài khoản của nhà cung cấp quan sát.

**Telemetry cũng là dữ liệu cần được bảo vệ.** Trace ID không phải dữ liệu vô hại trong mọi ngữ cảnh; span attributes có thể chứa thông tin cá nhân; error message có thể vô tình ghi API key; evaluation dataset có thể chứa nguyên câu hỏi và bằng chứng nội bộ. Vì vậy, observability cần được thiết kế theo nguyên tắc **thu thập tối thiểu, phân loại dữ liệu trước khi ghi, kiểm soát đường xuất và giới hạn người được xem**.

Bài này thuộc chương **Bảo vệ dữ liệu** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module hướng tới đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm giữa các phiên bản prompt, model và pipeline. Bài tập trung vào bảo vệ prompt, response, dữ liệu RAG, tool arguments, evaluation records và metadata khi đưa chúng vào metrics, traces, logs hoặc hệ thống quan sát bên ngoài.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện các loại dữ liệu nhạy cảm có thể xuất hiện trong telemetry của ứng dụng AI.
2. Vẽ luồng dữ liệu từ API ingress qua RAG, prompt, model, tool, evaluator đến exporter và backend.
3. Áp dụng data classification và data minimization trước khi tạo span, log hoặc metric.
4. Phân biệt masking, redaction, pseudonymization, tokenization và anonymization.
5. Thiết kế thuộc tính quan sát an toàn cho ChatModel, retrieval, tool calling và evaluation.
6. Bảo vệ API keys, authorization headers, provider request IDs, raw prompts, tool arguments và stack traces.
7. Kiểm soát truy cập, mã hóa, retention, deletion, audit và ranh giới tenant của nền tảng telemetry.
8. Viết test để xác nhận dữ liệu nhạy cảm không xuất hiện trong metrics, spans, logs hoặc error events.
9. Duy trì khả năng điều tra bằng correlation IDs, safe metadata và verified business records mà không sao chép toàn bộ dữ liệu nghiệp vụ vào telemetry.

## 2. Telemetry có thể chứa những dữ liệu gì?

Trong hệ thống Spring AI, telemetry thường được tạo ở nhiều tầng. Dữ liệu nhạy cảm có thể xuất hiện ở những vị trí mà nhóm phát triển ban đầu không dự định.

| Nguồn | Ví dụ dữ liệu có thể lộ | Rủi ro |
|---|---|---|
| **HTTP ingress** | Request body, query parameters, cookies, authorization headers, IP address. | PII, session secrets, credentials. |
| **Conversation** | Lịch sử chat, tên, email, địa chỉ, thông tin sức khỏe/tài chính. | Tiết lộ nội dung riêng tư. |
| **Prompt assembly** | System prompt, developer instructions, retrieved context, hidden metadata. | Lộ logic nội bộ và tài liệu không được phép. |
| **ChatModel response** | Câu trả lời, thông tin người dùng khác, dữ liệu do model suy đoán. | Sao chép dữ liệu nhạy cảm sang log/trace. |
| **RAG retrieval** | Document content, chunk text, source URI, tenant ID, ACL metadata. | Vượt ranh giới phân quyền hoặc lộ tài liệu nội bộ. |
| **Tool calling** | Account/order IDs, addresses, payment references, arguments và results. | Lộ dữ liệu giao dịch hoặc quyền thao tác. |
| **HTTP client/provider** | API key, bearer token, request headers, provider request ID, raw response body. | Lộ credentials hoặc metadata nội bộ. |
| **Exception/logging** | URL có query secrets, SQL, stack trace, serialized request/response. | Rò rỉ dữ liệu qua lỗi. |
| **Evaluation** | Gold answers, user questions, claim evidence, reference documents. | Sao chép dữ liệu thật vào môi trường kiểm thử. |
| **Metrics labels** | User ID, case ID, request ID, prompt hash, raw error text. | Cardinality bùng nổ và lộ định danh. |

### 2.1. Một trường có thể nhạy cảm dù không phải PII

Thông tin sau cũng có thể cần bảo vệ:

- System prompt, policy nội bộ và cấu hình tool.
- Tên index, database, bucket, cluster hoặc host nội bộ.
- Provider request IDs và deployment identifiers.
- Kết quả điều tra gian lận hoặc quyết định nghiệp vụ.
- Tên tài liệu mật, đường dẫn nội bộ và source identifiers.
- Chi tiết lỗi bảo mật, stack traces và phiên bản dễ bị khai thác.

Phân loại dữ liệu không chỉ dựa vào câu hỏi “có tên người hay không?”. Cần xét **khả năng liên kết, tác động khi lộ và chính sách truy cập**.

## 3. Luồng dữ liệu và ranh giới tin cậy

Một prompt có thể đi qua nhiều thành phần trước khi trở thành span attribute hoặc log event. Nếu chỉ kiểm tra ở cuối pipeline, dữ liệu đã có thể bị ghi ở tầng framework hoặc HTTP client.

```mermaid
flowchart TD
    U["Người dùng / API request"] --> IN["Ingress + authentication"]
    IN --> APP["Application workflow"]
    APP --> RET["RAG retrieval + ACL filter"]
    RET --> PROMPT["Prompt assembly"]
    PROMPT --> MODEL["ChatModel / provider"]
    MODEL --> TOOL["Tool callback"]
    TOOL --> BACK["Business backend"]
    MODEL --> OUT["Response validation"]
    BACK --> OUT
    OUT --> EVAL["Evaluation / quality gate"]
    APP --> OBS["Observation / logs / metrics"]
    RET --> OBS
    MODEL --> OBS
    TOOL --> OBS
    EVAL --> OBS
    OBS --> COL["Collector / processors / exporters"]
    COL --> STORE["Metrics, traces, logs backends"]
    STORE --> USERS["Dashboard / operators / vendors"]
```

Sơ đồ cho thấy telemetry được tạo ở nhiều điểm và sau đó đi qua collector/exporter tới một hoặc nhiều backend. **Collector không phải ranh giới duy nhất để bảo vệ dữ liệu**: ứng dụng có thể đã log raw prompt trước khi exporter nhận dữ liệu; một agent cũng có thể tự động capture HTTP headers hoặc bodies.

### 3.1. Xác định trust boundaries

Các ranh giới cần được rà soát:

1. Browser/client → API gateway.
2. API gateway → application service.
3. Application → vector store/document service.
4. Application → model provider hoặc AI gateway.
5. Application → tool service/business backend.
6. Application/collector → observability vendor.
7. Backend observability → dashboard, alerting và người dùng nội bộ.
8. Production → evaluation/staging datasets.

Mỗi ranh giới cần câu trả lời: **Dữ liệu nào được phép đi qua? Ai có quyền xem? Có mã hóa không? Có redaction không? Được giữ trong bao lâu?**

### 3.2. Telemetry backend là một kho dữ liệu

Không nên mặc định tracing/logging platform là nơi “chỉ có metadata kỹ thuật”. Người có quyền đọc trace có thể thấy attributes, events, exception messages và đôi khi cả request/response nếu instrumentation được cấu hình capture body. Vì vậy cần áp dụng chính sách truy cập, retention và audit tương tự các kho dữ liệu khác, theo mức nhạy cảm thực tế.

## 4. Data classification trước khi instrument

Một cách thực tế là định nghĩa cấp phân loại ngay trong dự án. Tên cấp độ dưới đây là **taxonomy nội bộ minh họa**, cần được điều chỉnh theo chính sách tổ chức và yêu cầu pháp lý áp dụng.

| Cấp | Ví dụ | Cách xử lý telemetry |
|---|---|---|
| **Public** | Tên service công khai, loại operation chung. | Có thể ghi theo mục đích vận hành. |
| **Internal** | Feature name, pipeline version, error category không nhạy cảm. | Ghi theo allowlist, giới hạn quyền phù hợp. |
| **Confidential** | Tenant reference, case reference, source document ID, business operation reference. | Chỉ ghi nếu có nhu cầu rõ, pseudonymize hoặc giới hạn truy cập/retention. |
| **Restricted / secret** | API keys, passwords, bearer tokens, private keys, raw payment credentials. | Không ghi vào telemetry; phải loại bỏ ở nguồn. |
| **Personal / sensitive** | Email, số điện thoại, địa chỉ, nội dung hội thoại, dữ liệu cá nhân nhạy cảm. | Mặc định không ghi raw; chỉ xử lý khi có cơ sở, mục đích và kiểm soát phù hợp. |

### 4.1. Phân loại theo trường, không chỉ theo hệ thống

Một trace có thể chứa nhiều loại dữ liệu:

```text
service.name          = support-ai                 [Internal]
feature               = order-support              [Internal]
operation             = refund.lookup              [Internal]
trace.id              = 4bf9...                    [Confidential/contextual]
evaluation.case_id    = case-014                   [Confidential]
user.email            = customer@example.test      [Personal]
authorization         = Bearer eyJ...               [Restricted secret]
prompt                = "Tôi bị..."                 [Personal / possibly sensitive]
```

Mức phân loại thực tế phụ thuộc khả năng liên kết và chính sách của tổ chức. Trace ID có thể không trực tiếp là PII, nhưng khi liên kết được với hồ sơ người dùng hoặc giao dịch thì cần kiểm soát tương ứng.

### 4.2. Không đưa dữ liệu chưa phân loại vào telemetry

Nếu một field mới được thêm vào tool arguments hoặc provider metadata, không tự động đưa nó vào span attributes. Cần xác định nguồn dữ liệu và owner, mục đích thu thập, phân loại và quyền truy cập, có cần giá trị gốc hay chỉ cần enum/count, retention và nơi xuất, cùng cách test rằng field không rò rỉ qua log, trace hoặc exception.

## 5. Data minimization: chỉ thu thập điều cần thiết

**Data minimization** nghĩa là thu thập ít nhất dữ liệu đủ để đạt mục đích đã xác định. Với observability, phần lớn câu hỏi vận hành có thể trả lời bằng operation name, duration, outcome, model family và error category mà không cần lưu nguyên prompt hoặc response.

### 5.1. Thay raw content bằng thông tin cấu trúc

| Không nên ghi mặc định | Thay bằng |
|---|---|
| Toàn bộ câu hỏi người dùng | Feature, operation, input length bucket, language nếu thực sự cần. |
| Toàn bộ system/user prompt | Prompt release/version và prompt template ID được quản lý. |
| Retrieved chunk text | Số chunk, retrieval outcome, source reference đã được kiểm soát. |
| Tool arguments đầy đủ | Tool name, schema version, outcome category. |
| Tool response body | Business status đã chuẩn hóa và reason code allowlist. |
| Model response đầy đủ | Output length, finish reason, validator verdict. |
| Authorization header | Chỉ ghi trạng thái auth result, không ghi credential. |
| Raw exception message | Exception class và error category đã chuẩn hóa. |
| Full URL/query string | Route template, host group hoặc endpoint category. |

### 5.2. Ví dụ một span đủ dùng để điều tra

```json
{
  "name": "app.ai.rag.retrieval",
  "attributes": {
    "app.feature": "order-support",
    "app.pipeline.version": "rag-v3",
    "app.retrieval.outcome": "success",
    "app.retrieval.top_k": 5,
    "app.retrieval.result_count": 4,
    "app.retrieval.duration_bucket": "100-250ms"
  }
}
```

Đây là **ví dụ schema nội bộ**, không phải semantic convention bắt buộc. Nó có thể giúp biết retrieval có kết quả, dùng pipeline nào và có bao nhiêu chunk mà không sao chép nội dung tài liệu. Nếu cần biết chính xác tài liệu nào đã được dùng, hãy liên kết tới evaluation/source store có phân quyền.

### 5.3. Không ghi để “phòng khi cần”

Ghi tất cả prompt, response, headers và tool arguments “để debug sau này” tạo ra một kho dữ liệu lớn, khó kiểm soát và không có mục đích rõ. Thay vào đó:

1. Xác định câu hỏi chẩn đoán cụ thể.
2. Chọn trường tối thiểu trả lời câu hỏi.
3. Dùng dữ liệu giả hoặc redacted fixtures cho test.
4. Nếu cần lưu nội dung thật cho một điều tra, dùng quy trình riêng có quyền, thời hạn và audit.

## 6. Redaction, masking, pseudonymization và anonymization

Các thuật ngữ này không đồng nghĩa. Chọn sai phương pháp có thể khiến dữ liệu vẫn nhận diện được hoặc làm mất khả năng đối soát.

| Kỹ thuật | Mô tả | Ví dụ | Giới hạn |
|---|---|---|---|
| **Redaction** | Loại bỏ trường/đoạn không được phép lưu. | Xóa authorization header khỏi event. | Không thể phục hồi giá trị đã bỏ; cần làm ở mọi đường ghi. |
| **Masking** | Che một phần để giảm hiển thị. | `****1234`. | Phần còn lại vẫn có thể nhận diện hoặc suy đoán. |
| **Pseudonymization** | Thay định danh bằng mã thay thế có thể liên kết qua khóa/bảng riêng. | HMAC của customer reference. | Vẫn có thể là dữ liệu cá nhân/pseudonymous; cần bảo vệ khóa và bảng mapping. |
| **Tokenization** | Thay giá trị bằng token, mapping được giữ trong hệ thống riêng. | Account reference → opaque token. | Token vault/mapping trở thành tài sản nhạy cảm. |
| **Anonymization** | Biến đổi để cá nhân không còn nhận diện được bằng phương tiện hợp lý trong bối cảnh sử dụng. | Tổng hợp dữ liệu đủ lớn, loại bỏ liên kết. | Khó bảo đảm; dữ liệu có thể tái nhận diện khi kết hợp nguồn khác. |

### 6.1. Redaction nên xảy ra trước khi export

Nếu raw prompt đã được ghi vào application log, việc redaction ở collector không xóa bản log đó. Nếu HTTP agent capture request body, custom Observation không thể ngăn field đã được agent thu thập. Vì vậy:

- Tắt body/header capture không cần thiết tại instrumentation.
- Không log raw prompt/response trong business code.
- Dùng allowlist attribute ở nguồn.
- Redact exception và structured logs trước khi ghi.
- Dùng collector processors như lớp phòng vệ bổ sung, không phải biện pháp duy nhất.

### 6.2. Masking không phải anonymization

Che email thành `j***@example.com` có thể vẫn nhận diện được người trong tập nhỏ. Che bốn số cuối của mã tài khoản cũng không làm dữ liệu vô danh. Khi đánh giá mức bảo vệ, phải xét các trường khác có thể kết hợp để tái nhận diện.

### 6.3. Hash không tự biến định danh thành vô danh

Hash email hoặc số điện thoại thường có thể bị dò bằng dictionary vì không gian giá trị dễ đoán. Nếu cần correlation ổn định, có thể cân nhắc HMAC với khóa bí mật được quản lý:

```text
pseudonymous_ref = HMAC-SHA-256(secret_key, canonical_identifier)
```

HMAC giúp người không có khóa khó tự tạo cùng mã cho một định danh đoán trước, nhưng **không biến dữ liệu thành anonymous**. Mã vẫn liên kết các hoạt động của cùng một người, có thể bị coi là dữ liệu cá nhân theo bối cảnh và phải có kiểm soát. Không dùng plain SHA-256 của email/phone như giải pháp bảo vệ.

### 6.4. Quản lý khóa và rotation

Nếu dùng HMAC/tokenization:

- Khóa ở secret manager/KMS, không trong source code, config công khai hoặc telemetry.
- Có key version để biết mã được tạo bằng khóa nào.
- Có quy trình rotation và xử lý correlation giữa các giai đoạn.
- Giới hạn ai có quyền tạo/tra mã.
- Không đưa giá trị gốc và pseudonym cùng một event.
- Không dùng pseudonymous IDs làm metric labels nếu cardinality cao.

## 7. Bảo vệ prompt và response của model

Prompt có thể chứa dữ liệu người dùng, context RAG, system instructions và tool schema. Response có thể phản chiếu lại nội dung nhạy cảm hoặc tạo thông tin sai. **Raw prompt/response không nên là span attribute hoặc log field mặc định.**

### 7.1. Trường nên ghi thay cho prompt

```text
prompt.template_id         = support-answer
prompt.version             = v4
prompt.input_size_bucket   = 1k-2k
prompt.context_chunk_count = 4
prompt.policy_mode         = grounded-only
model.family               = chat-family-x
response.finish_reason     = stop
response.validation        = pass
```

Đây là các key nội bộ minh họa. Version, template ID và policy mode cần lấy từ danh mục được quản lý, không lấy nguyên văn do người dùng/model cung cấp.

### 7.2. Không capture request/response body để tiện debug

Một số HTTP client interceptors, SDK debug modes hoặc auto-instrumentation agents có thể capture body/header. Cần rà soát cấu hình để:

- Không ghi request body chứa prompt.
- Không ghi response body chứa câu trả lời.
- Không ghi Authorization/Cookie/API key.
- Không ghi URL query parameters có token hoặc PII.
- Không ghi multipart media hoặc binary payload.
- Chỉ giữ headers allowlist, sau khi xem xét từng field.

### 7.3. Error path cũng có thể làm lộ prompt

Một exception có thể chứa URL, headers hoặc snippets của request. Nếu code log `ex.getMessage()` nguyên văn, dữ liệu đã lọt ra logs. Hãy chuẩn hóa lỗi thành category/code và giữ exception gốc chỉ trong memory để xử lý, hoặc ghi stack trace đã kiểm soát nếu chính sách cho phép. Không log request object hoặc toàn bộ SDK response trong catch block.

## 8. Bảo vệ dữ liệu RAG và vector retrieval

RAG đưa tài liệu từ nhiều nguồn vào context của model. Telemetry có thể vô tình lưu nội dung chunk nguyên văn, tên file/URL chứa tên khách hàng hoặc dự án, document IDs liên kết trực tiếp với hồ sơ, tenant IDs và ACL metadata, query text có thông tin cá nhân, hoặc kết quả reranker chứa các đoạn trích nhạy cảm.

### 8.1. Phân quyền phải xảy ra trước khi dữ liệu đi vào prompt

Thứ tự an toàn:

1. Xác thực caller và xác định tenant/authorization context từ nguồn tin cậy.
2. Truy vấn theo tenant và policy filter.
3. Kiểm tra quyền trên từng tài liệu/chunk trước khi đưa vào context.
4. Chỉ chọn nội dung cần thiết.
5. Ghi telemetry tổng hợp: result count, source class, retrieval status và timing.
6. Nếu cần điều tra source IDs, lưu ở evaluation store có phân quyền và liên kết bằng reference an toàn.

Không đưa tất cả documents vào prompt rồi trông chờ model tự bỏ qua tài liệu không được phép. Không dùng trace baggage hoặc model-generated tenant ID làm căn cứ authorization.

### 8.2. Source reference vẫn có thể nhạy cảm

Một ID tài liệu không có tên người nhưng có thể tra cứu ra hợp đồng, bệnh án hoặc hồ sơ nhân sự. Do đó, document identifier không tự động là dữ liệu public. Cần phân loại source references và kiểm soát truy cập backend chứa mapping.

### 8.3. Ghi retrieval evidence theo lớp

Metrics:

```text
app.rag.retrieval.duration
app.rag.retrieval.results
app.rag.retrieval.empty
```

Trace attributes an toàn:

```text
retrieval.top_k = 5
retrieval.result_count = 4
retrieval.index_family = policy-index
retrieval.outcome = success
```

Evaluation record có kiểm soát:

```json
{
  "caseRef": "case-014",
  "corpusVersion": "policy-2026-11",
  "sourceRefs": ["source-ref-a", "source-ref-b"],
  "claimEvidence": [
    {"claimRef": "claim-2", "sourceRef": "source-ref-a"}
  ],
  "accessScope": "restricted-evaluation"
}
```

Đây là schema nội bộ minh họa. Evaluation record có thể chứa dữ liệu nhạy cảm và cần quyền/retention riêng; không đẩy nguyên văn source content vào metrics hoặc traces.

## 9. Bảo vệ tool arguments và business results

Tool calling có thể chạm tới dữ liệu hoặc hành động quan trọng. Arguments do model tạo **không phải dữ liệu đáng tin** và không nên được log nguyên văn.

### 9.1. Log tên tool và kết quả đã chuẩn hóa

Thay vì:

```json
{
  "tool": "refund",
  "arguments": {
    "customerEmail": "customer@example.test",
    "accountNumber": "123456789",
    "authorizationToken": "secret"
  }
}
```

Ghi tín hiệu tối thiểu:

```json
{
  "tool.name": "refund.lookup",
  "tool.schema.version": "v2",
  "tool.technical_outcome": "success",
  "tool.business_outcome": "pending",
  "tool.duration_bucket": "100-250ms"
}
```

Không lưu secret, email hoặc account number trong event. Nếu cần truy vết giao dịch, dùng operation reference đã được phân loại, pseudonymize nếu phù hợp và giữ mapping ở backend được bảo vệ.

### 9.2. Không để model quyết định quyền truy cập

Tool handler phải lấy principal/tenant từ security context đáng tin cậy, xác minh quyền với backend trước khi đọc hoặc thay đổi dữ liệu, validate arguments theo schema và business constraints, áp dụng idempotency cho thao tác có side effect, trả status chuẩn hóa và ghi audit event theo chính sách riêng.

Không nhận `userId`, `tenantId` hoặc `role` do model cung cấp làm bằng chứng quyền. Không đưa credential vào prompt để model “gọi đúng tool”.

### 9.3. Technical success, business outcome và quality verdict

```text
HTTP response        = 200 OK
Tool execution       = SUCCESS
Business status      = FAILED
Assistant statement = "Đã hoàn tiền thành công"
Tool consistency     = FAIL
```

Đây là năm khái niệm khác nhau. Không gộp vào một field `success=true`. Một trace thành công về kỹ thuật không chứng minh tác vụ nghiệp vụ thành công; một tool result cũng cần được kiểm tra để đảm bảo assistant diễn giải đúng.

## 10. Bảo vệ metrics: cardinality và nội dung nhãn

Metrics được thiết kế để tổng hợp. Không đưa định danh từng request/người dùng hoặc nội dung tự do vào labels.

### 10.1. Tránh các label sau

```text
user.id
tenant.id (nếu số lượng tenant lớn hoặc nhạy cảm)
request.id
trace.id
evaluation.case.id
order.id
document.id
raw.question
prompt.hash-per-request
exception.message
provider.request.id
```

Các giá trị này có thể tạo hàng nghìn/hàng triệu time series, đồng thời tiết lộ dữ liệu riêng. Dùng metrics theo nhóm:

```text
feature = order-support | policy-qa
operation = retrieval | generation | tool | evaluation
outcome = success | error | timeout | unknown
criterion = relevance | groundedness | tool-consistency
tool = lookupOrder | refundLookup
```

Chỉ dùng các giá trị được kiểm soát. Nếu một chiều không phục vụ dashboard/alert cụ thể, cân nhắc bỏ nó.

### 10.2. Hash không giải quyết cardinality

Nếu mỗi request ID được hash thành một chuỗi khác nhau, số giá trị phân biệt vẫn gần như giữ nguyên. Hash có thể làm giá trị khó đọc nhưng không giảm cardinality. Dùng trace identifier trong exemplars nếu hệ thống hỗ trợ liên kết metric sample với trace; không tạo label riêng cho mỗi trace.

### 10.3. Histogram và bucket

Histogram có thể tạo nhiều series cho mỗi tổ hợp labels. Khi thiết kế latency metrics, dùng số lượng nhãn hữu hạn, chọn bucket/SLO boundaries có mục đích, theo dõi series count và churn, không thêm case ID chỉ để tìm request chậm, và dùng trace backend cho điều tra từng request.

## 11. Bảo vệ trace context, baggage và span attributes

Trace context chủ yếu chứa IDs/flags phục vụ liên kết. Baggage có thể truyền metadata qua nhiều dịch vụ theo cấu hình; span attributes và events lưu thông tin về operation. Mỗi loại đều cần kiểm soát.

### 11.1. Trace ID không phải bí mật xác thực nhưng vẫn cần bảo vệ

Trace ID không thay thế password hoặc token. Tuy nhiên, nếu người có trace ID có thể truy vấn backend để thấy dữ liệu nhạy cảm, trace ID trở thành một **correlation handle** cần kiểm soát. Không công khai trace search endpoint hoặc dùng trace ID làm authorization token.

### 11.2. Baggage có thể lan truyền rộng

Không đưa email, phone, account/order IDs nếu không được phép, access token, session cookie, API key, raw prompt, conversation history hoặc retrieved text, tenant/role do caller không tin cậy gửi mà chưa xác thực vào baggage.

Nếu cần baggage, chỉ truyền metadata nhỏ, đã kiểm soát, không nhạy cảm và có mục đích correlation rõ. Giới hạn kích thước và số lượng trường.

### 11.3. Span attributes không phải kho JSON

Tránh đính kèm nguyên object request, model response, tool arguments hoặc toàn bộ exception. Chọn trường có cấu trúc và allowlist:

```text
app.feature = order-support
app.operation = refund.lookup
app.outcome = pending
app.pipeline.version = rag-v3
gen_ai.request.model = model-family-a
```

Các key cụ thể của GenAI cần theo convention version đang dùng; ví dụ trên minh họa nguyên tắc. Không tự ghi raw provider payload.

## 12. Error handling an toàn: không để exception làm lộ dữ liệu

### 12.1. Phân loại lỗi thay vì ghi message tùy ý

| Error category | Log/metric value an toàn hơn | Tránh ghi |
|---|---|---|
| Provider rate limit | `provider_rate_limited` | Raw headers/token/quota payload nếu nhạy cảm. |
| Provider timeout | `provider_timeout` | Full request/response body. |
| Authentication error | `provider_auth_failed` | Authorization header, API key. |
| Tool validation | `tool_argument_invalid` | Toàn bộ arguments có PII. |
| Business rejection | `business_rejected` + reason code allowlist | Raw business record. |
| Evaluator failure | `evaluation_execution_error` | Raw prompt/evidence trong exception message. |
| JSON/schema failure | `output_schema_invalid` | Response đầy đủ nếu có dữ liệu riêng. |

### 12.2. Không log exception message một cách mù quáng

Thông báo lỗi từ SDK có thể chứa URL, query parameters, headers hoặc snippets của request. Stack trace cũng có thể chứa dữ liệu từ exception lồng nhau. Nên chuẩn hóa category/code, ghi exception class và operation name nếu cần, redact theo allowlist trước khi ghi message, không serialize toàn bộ request/response vào error event, hạn chế stack trace ở nơi có quyền phù hợp và kiểm tra cả exception cause chain.

### 12.3. Log correlation an toàn

```json
{
  "service": "support-ai",
  "feature": "order-support",
  "operation": "refund.lookup",
  "outcome": "timeout",
  "trace_id": "trace-reference-if-policy-allows",
  "error_code": "PROVIDER_TIMEOUT"
}
```

Không chứa prompt, customer identity, authorization hoặc tool payload. Trace reference chỉ ghi khi chính sách cho phép và backend log/tracing có quyền tương ứng.

## 13. Bảo vệ collector, exporter và backend

Lọc ở ứng dụng là lớp đầu tiên. Collector và backend là các lớp kiểm soát tiếp theo.

### 13.1. Defense in depth

```mermaid
flowchart TD
    SRC["Application instrumentation"] --> L1["Source allowlist + no raw body capture"]
    L1 --> COL["Collector"]
    COL --> L2["Redaction / attribute filtering / transform"]
    L2 --> ROUTE["Routing by sensitivity and purpose"]
    ROUTE --> M["Metrics backend"]
    ROUTE --> T["Tracing backend"]
    ROUTE --> L["Log backend"]
    M --> IAM["RBAC / tenant isolation / audit"]
    T --> IAM
    L --> IAM
    IAM --> RET["Retention, deletion, backup lifecycle"]
```

Collector processors có thể lọc, xóa hoặc biến đổi attributes trước khi export. Tuy nhiên, cần kiểm tra processor thực tế, thứ tự pipeline, các exporter khác và đường log độc lập. Một processor chỉ áp dụng cho traces không tự bảo vệ logs hoặc metrics.

### 13.2. Allowlist an toàn hơn denylist đơn thuần

Denylist chỉ loại bỏ các key đã biết. Một thư viện mới có thể thêm field nhạy cảm với tên chưa được liệt kê. Với telemetry quan trọng, cân nhắc allowlist chỉ xuất các trường được phê duyệt, denylist bổ sung secrets/PII phổ biến, schema validation và redaction.

Không coi regex là DLP hoàn chỉnh. Regex có thể bỏ sót dữ liệu được mã hóa, chia nhỏ, viết sai định dạng hoặc xuất hiện trong ngôn ngữ tự nhiên.

### 13.3. Mã hóa và xác thực

- TLS/mTLS giữa application, collector và backend khi phù hợp.
- Authentication riêng cho exporter/collector, xoay vòng credentials.
- Mã hóa at rest theo khả năng của nền tảng.
- Quản lý encryption keys ngoài repository.
- Hạn chế network egress tới đúng collector/vendor được phê duyệt.
- Không để endpoint ingest mở công khai hoặc cho phép tenant ghi telemetry tùy ý.

### 13.4. Quyền truy cập và audit

Phân quyền theo vai trò và mục đích:

| Vai trò | Quyền phù hợp |
|---|---|
| **Developer** | Xem metrics tổng hợp; truy cập trace/log đã redacted trong môi trường được phép. |
| **On-call engineer** | Truy cập trace chi tiết theo incident và thời hạn phù hợp; hành động được audit. |
| **Evaluator/researcher** | Truy cập dataset/evaluation records đã được duyệt, không mặc nhiên xem production secrets. |
| **Platform admin** | Quản lý backend và quyền; truy cập nội dung theo nguyên tắc tối thiểu. |
| **External vendor/support** | Chỉ nhận dữ liệu được hợp đồng và tổ chức cho phép; tránh gửi raw user content. |

Tách quyền xem metrics, trace attributes, raw logs và evaluation artifacts nếu mức nhạy cảm khác nhau. Ghi audit cho truy vấn/export dữ liệu nhạy cảm khi nền tảng hỗ trợ.

## 14. Retention, deletion và data lifecycle

Telemetry có thể được sao chép qua hot storage, cold storage, archive, snapshots và backups. Đặt retention chỉ trên giao diện dashboard chưa chắc xóa toàn bộ bản sao.

### 14.1. Retention theo mục đích và độ nhạy cảm

| Loại dữ liệu | Hướng thiết kế |
|---|---|
| Metrics tổng hợp không chứa định danh | Có thể giữ lâu hơn để theo dõi xu hướng, theo chính sách vận hành. |
| Traces đã redacted | Retention theo nhu cầu điều tra và chi phí. |
| Logs lỗi chi tiết | Giới hạn thời gian, nội dung và quyền truy cập. |
| Evaluation records có dữ liệu thật | Theo chính sách dataset, quyền và mục đích đánh giá. |
| Audit events nghiệp vụ | Theo yêu cầu kiểm toán/quy định riêng của hệ thống. |
| Secrets/credentials | Không lưu trong telemetry; nếu lộ cần xử lý như sự cố secret. |

Không có một con số retention chung phù hợp mọi tổ chức. Cần ghi owner, mục đích, thời hạn, nơi lưu, bản sao và quy trình xóa cho từng loại dữ liệu.

### 14.2. Deletion phải tính đến các bản sao

Khi cần xóa dữ liệu, rà soát application logs và tracing/metrics backends, collector queues/buffers và persistent volumes, archive/snapshots/backups/replicas, exported files và incident attachments, evaluation datasets/fixtures/derived artifacts, cùng bảng mapping pseudonymization/tokenization.

Khả năng xóa một record cụ thể phụ thuộc backend và thiết kế lưu trữ. Đừng hứa xóa ngay khỏi mọi bản sao nếu hệ thống chỉ hỗ trợ retention theo block hoặc backup expiry.

### 14.3. Không ghi dữ liệu thật vào fixture nếu không cần

Dùng synthetic data hoặc dữ liệu đã được phê duyệt cho test/benchmark. Nếu cần một case thật để tái hiện lỗi, cần quy trình kiểm soát riêng, giới hạn người xem, thời gian lưu và redaction trước khi đưa vào issue/PR.

## 15. Ví dụ Java: chỉ ghi telemetry từ allowlist

Ví dụ sau minh họa một lớp tiện ích chỉ nhận các giá trị enum/nội bộ đã chuẩn hóa. Nó không nhận prompt, response, tool arguments hoặc tùy ý một map từ request.

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.Objects;

public final class SafeAiTelemetry {

    public enum Feature {
        POLICY_QA, ORDER_SUPPORT
    }

    public enum Operation {
        RETRIEVAL, GENERATION, TOOL, EVALUATION
    }

    public enum Outcome {
        SUCCESS, ERROR, TIMEOUT, UNKNOWN
    }

    private final ObservationRegistry observations;
    private final MeterRegistry meters;

    public SafeAiTelemetry(
        ObservationRegistry observations,
        MeterRegistry meters
    ) {
        this.observations = Objects.requireNonNull(observations);
        this.meters = Objects.requireNonNull(meters);
    }

    public <T> T observe(
        Feature feature,
        Operation operation,
        java.util.function.Supplier<T> action
    ) {
        String featureTag = feature.name().toLowerCase();
        String operationTag = operation.name().toLowerCase();

        return Observation
            .createNotStarted("app.ai.operation", observations)
            .lowCardinalityKeyValue("feature", featureTag)
            .lowCardinalityKeyValue("operation", operationTag)
            .observe(action);
    }

    public void recordOutcome(
        Feature feature,
        Operation operation,
        Outcome outcome
    ) {
        meters.counter(
            "app.ai.operation.outcomes",
            "feature", feature.name().toLowerCase(),
            "operation", operation.name().toLowerCase(),
            "outcome", outcome.name().toLowerCase()
        ).increment();
    }
}
```

Lớp này giúp giới hạn metric tags ở enum hữu hạn. Nó **không tự redaction** các spans/logs được tạo bởi thư viện khác, không chặn HTTP agent capture body và không bảo đảm exporter đã cấu hình an toàn. Cần rà soát tất cả instrumentation/handlers/agents đang hoạt động.

### 15.1. Cách dùng ở application service

```java
String answer = telemetry.observe(
    SafeAiTelemetry.Feature.ORDER_SUPPORT,
    SafeAiTelemetry.Operation.GENERATION,
    () -> chatClient.prompt()
        .user(question)
        .call()
        .content()
);
```

Trong ví dụ, `question` chỉ được dùng để xử lý nghiệp vụ và **không được truyền vào telemetry API**. Tuy nhiên, nếu HTTP client agent hoặc framework được cấu hình capture body, prompt vẫn có thể bị ghi ở tầng khác. Vì vậy cần tắt capture raw payload và test end-to-end.

### 15.2. Tránh một API tiện lợi nhưng nguy hiểm

```java
// Anti-pattern: nhận mọi thuộc tính từ caller.
void record(Map<String, Object> allRequestFields) {
    allRequestFields.forEach(observation::highCardinalityKeyValue);
}
```

API này cho phép bất kỳ request field nào lọt vào telemetry, kể cả secrets và PII. Dùng method có tham số rõ, enum/allowlist, schema validation và review khi thêm field.

## 16. Ví dụ Java: redaction phải giới hạn phạm vi và có test

Một bộ lọc đơn giản có thể xóa một số header nhạy cảm khỏi bản ghi đã chuẩn hóa:

```java
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public final class SafeHeaderView {

    private static final Set<String> ALLOWED = Set.of(
        "content-type",
        "x-request-correlation"
    );

    public Map<String, String> allowlisted(Map<String, String> headers) {
        return headers.entrySet().stream()
            .filter(e -> ALLOWED.contains(
                e.getKey().toLowerCase(Locale.ROOT)))
            .collect(Collectors.toUnmodifiableMap(
                e -> e.getKey().toLowerCase(Locale.ROOT),
                Map.Entry::getValue
            ));
    }
}
```

Đây là **ví dụ allowlist tối giản**, không phải một HTTP security filter hoàn chỉnh. Header correlation cũng cần được phân loại theo policy. Không đưa Authorization, Cookie, Set-Cookie, API keys hoặc arbitrary headers vào allowlist chỉ vì một môi trường test đang dùng chúng.

### 16.1. Vì sao allowlist tốt hơn chỉ xóa Authorization?

HTTP request có thể chứa secret trong header tùy chỉnh, query parameters, URL, body hoặc exception. Một denylist chỉ có Authorization sẽ bỏ sót các vị trí khác. Allowlist làm giảm số trường có thể xuất hiện, nhưng vẫn cần review nội dung **giá trị** của từng header được phép.

### 16.2. Regex redaction không phải biện pháp duy nhất

Regex có thể hỗ trợ phát hiện email, số điện thoại hoặc token theo định dạng quen thuộc, nhưng có thể bỏ sót nội dung bị chia nhỏ/mã hóa, nhận diện nhầm chuỗi hợp lệ, không hiểu ngữ cảnh và không phát hiện secret trong binary/multimodal payload.

Ưu tiên ngăn ghi từ nguồn, schema allowlist và data classification. Dùng DLP/scanning như lớp bổ sung, không thay thế thiết kế thu thập tối thiểu.

## 17. Kiểm thử bảo vệ dữ liệu telemetry

Test cần xác minh **nội dung cuối cùng được export**, không chỉ kiểm tra helper redaction. Dữ liệu có thể đi vào spans qua agent, exception handler hoặc framework instrumentation mà code ứng dụng không nhìn thấy.

### 17.1. Test cases cơ bản

| Test | Dữ liệu đầu vào | Kỳ vọng |
|---|---|---|
| **DP01 — Authorization header** | Bearer token giả. | Không xuất hiện trong logs/spans/export payload. |
| **DP02 — Cookie/session** | Session cookie giả. | Bị loại khỏi telemetry. |
| **DP03 — Prompt PII** | Email/phone giả trong câu hỏi. | Raw prompt không xuất hiện trong telemetry. |
| **DP04 — RAG content** | Chunk có marker bí mật. | Nội dung chunk không xuất hiện trong spans/logs. |
| **DP05 — Tool arguments** | Account/order identifiers và token giả. | Chỉ tool name/outcome an toàn được ghi. |
| **DP06 — Exception message** | Exception chứa secret marker. | Error category được ghi; secret marker bị loại. |
| **DP07 — URL query** | URL có query token. | Chỉ route template/host category an toàn. |
| **DP08 — Metric labels** | Nhiều request IDs khác nhau. | Không tạo series riêng theo request ID. |
| **DP09 — Baggage** | Caller gửi baggage có PII. | Không propagate field không được phép. |
| **DP10 — Tenant isolation** | Hai tenant có source IDs riêng. | Người của tenant A không đọc telemetry/evaluation record của B. |
| **DP11 — Redaction fallback** | Field không biết/không đúng schema. | Không export hoặc cách ly theo policy. |
| **DP12 — Retention/deletion** | Record hết hạn hoặc có yêu cầu xóa hợp lệ. | Hành vi theo chính sách và phạm vi backend được hỗ trợ. |

### 17.2. Test bằng secret marker

Trong test, dùng chuỗi giả dễ tìm:

```text
TEST_SECRET_DO_NOT_EXPORT_9F21
TEST_EMAIL_person@example.test
TEST_ACCOUNT_00009999
```

Chạy một workflow fixture rồi kiểm tra exported span attributes, span events và exception events, application logs, HTTP client/server instrumentation payloads, metric names/label values và collector output nếu có test collector.

Assertions nên xác nhận marker **không xuất hiện** trong bất kỳ tín hiệu nào được phép kiểm tra. Không dùng credential thật làm test marker.

### 17.3. Kiểm tra tenant isolation

Test phải chứng minh tenant A chỉ truy xuất được documents thuộc A; tool handler lấy tenant từ authenticated context, không từ model arguments; evaluation record của A không thể truy vấn bằng quyền của B; dashboard/trace backend có ranh giới quyền phù hợp; collector/exporter không gộp hoặc route dữ liệu nhạy cảm sai đích.

### 17.4. Kiểm tra auto-instrumentation

Nếu có OTel agent hoặc HTTP client instrumentation tự động, chạy integration test với đúng agent flags/configuration dùng trong production. Unit test custom Observation không phát hiện việc agent tự capture HTTP body hoặc headers. Cần rà soát HTTP client request/response capture, exception stacktrace capture, SQL statement/parameter capture, header allow/deny lists, baggage propagation và collector processors/exporter routes.

## 18. Incident response khi telemetry đã lộ dữ liệu

Nếu phát hiện raw prompt, credentials hoặc PII đã vào backend observability, xử lý theo incident process của tổ chức. Trình tự khái quát:

1. **Ngăn phát sinh mới:** tắt instrumentation/capture gây lộ hoặc áp dụng filter ở nguồn.
2. **Đánh giá phạm vi:** loại dữ liệu, khoảng thời gian, service, tenant, backend và bản sao.
3. **Hạn chế truy cập:** khóa truy vấn/export không cần thiết, kiểm tra audit logs.
4. **Xử lý credentials:** nếu secret/token bị lộ, revoke/rotate theo quy trình; không chỉ xóa log.
5. **Xóa hoặc hạn chế bản ghi:** theo khả năng backend, retention và quy trình phê duyệt.
6. **Đánh giá nghĩa vụ thông báo:** do bộ phận có trách nhiệm và quy định áp dụng quyết định.
7. **Sửa nguyên nhân gốc:** instrumentation, log statements, agent config, collector pipeline và test.
8. **Xác minh sau khắc phục:** chạy lại secret marker tests và kiểm tra export payload.

Không tự kết luận một sự kiện là “không đáng kể” chỉ vì trace backend yêu cầu đăng nhập. Cần xem ai có quyền, dữ liệu gì đã được lưu, có vendor/region/backup nào và chính sách nào áp dụng.

## 19. Bài tập thực hành

Ứng dụng hỗ trợ khách hàng Spring AI có pipeline:

```text
POST /chat
  user question: chứa email và mã đơn
  RAG: truy xuất 4 chunks từ kho chính sách
  ChatModel: gọi provider với prompt/context
  Tool: lookupRefundStatus(orderId)
  Evaluator: groundedness + tool-result consistency
  Telemetry: metrics, traces, logs gửi tới observability vendor
```

Một trace mẫu hiện lưu:

```json
{
  "http.url": "/chat?session=abc123",
  "http.request.header.authorization": "Bearer TEST_SECRET_DO_NOT_EXPORT_9F21",
  "app.user.email": "person@example.test",
  "gen_ai.prompt": "Tôi là ... email ... đơn hàng ...",
  "rag.document.content": "Chính sách hoàn tiền nội bộ ...",
  "tool.arguments": {
    "orderId": "ORD-1042",
    "customerEmail": "person@example.test"
  },
  "exception.message": "Refund lookup failed for ORD-1042"
}
```

### Câu hỏi

1. Xác định tất cả trường có thể chứa dữ liệu nhạy cảm hoặc secret.
2. Với mỗi trường, đề xuất: bỏ hoàn toàn, thay bằng metadata an toàn, hoặc lưu ở kho khác có phân quyền.
3. Vì sao xóa authorization ở collector chưa đủ nếu application log đã ghi nó?
4. Phân biệt redaction, masking và pseudonymization bằng một ví dụ cho mã đơn hàng.
5. Những trường nào có thể làm metric labels cardinality cao?
6. Làm sao giữ khả năng nối trace với evaluation record mà không lưu raw prompt?
7. Đề xuất 5 test cases với secret marker để xác minh không rò rỉ.
8. Nếu token provider bị lộ trong trace đã export, cần làm gì ngoài việc xóa span?
9. Làm sao đảm bảo tenant A không truy cập source/evaluation record của tenant B?
10. Nêu hai giới hạn của regex redaction.

### Gợi ý đáp án

**1.** URL query session, authorization, email, prompt, RAG document content, tool arguments và exception message đều cần kiểm soát. Các trường này có thể chứa session token, credentials, PII hoặc tài liệu nội bộ.

**2.** Giữ route template /chat, không query token; bỏ authorization; dùng feature/prompt version thay raw prompt; dùng result count/source reference được kiểm soát thay chunk content; chỉ ghi tool name/outcome thay arguments; chuẩn hóa error code thay message có mã đơn.

**3.** Vì dữ liệu có thể đã được ghi ở application logs, agent, queue hoặc backend khác trước collector. Phải ngăn ở nguồn và rà soát mọi bản sao.

**4.** Redaction: xóa mã đơn; masking: `******1042`; pseudonymization: dùng HMAC/token reference có khóa/mapping riêng. Mã HMAC vẫn có thể là dữ liệu liên kết và cần bảo vệ.

**5.** Email, order ID, session ID, trace ID, prompt text, document ID, raw exception message. Không đưa các trường này vào metric labels.

**6.** Tạo trace ID tự nhiên cho execution, lưu evaluation case reference đã được kiểm soát trong evaluation store, dùng một correlation mapping có quyền và không đưa prompt raw vào span. Trace ID chỉ là liên kết kỹ thuật, không phải quyền truy cập.

**7.** Authorization marker, prompt marker, RAG chunk marker, tool argument marker, exception marker; kiểm tra spans, logs, metrics, baggage và exporter output.

**8.** Ngăn export mới, revoke/rotate token, xác định backend/bản sao/ai truy cập, audit, xóa hoặc hạn chế dữ liệu theo khả năng và xử lý incident theo chính sách.

**9.** Tenant identity lấy từ authenticated context; ACL filter ở retrieval/tool; authorization trên evaluation store; RBAC/tenant isolation trên telemetry backend; test truy cập chéo tenant.

**10.** Regex có thể bỏ sót dữ liệu mã hóa/chia nhỏ hoặc không nhận diện ngữ cảnh; cũng có thể xóa nhầm dữ liệu hợp lệ. Vì vậy phải kết hợp allowlist, source-level minimization và test.

## 20. Ghi nhớ

Telemetry của Spring AI có thể chứa prompt, response, retrieved documents, tool arguments, provider headers, exception messages và định danh người dùng. Hãy **phân loại dữ liệu trước khi instrument**, chỉ thu thập metadata tối thiểu, loại bỏ secrets ở nguồn, tách metrics/traces/logs/evaluation records theo mục đích, và dùng redaction/pseudonymization đúng ngữ nghĩa. Bảo vệ cả collector, exporter, backend, dashboard, backup và quyền truy cập; đặt retention/deletion rõ ràng; kiểm thử bằng secret markers trên toàn đường xuất. Một hệ observability tốt vẫn cần giúp điều tra latency, cost và quality regression, nhưng không nên biến mỗi trace thành bản sao của cuộc hội thoại hoặc hồ sơ nghiệp vụ.

### Tài liệu tham khảo

- [OpenTelemetry — Security](https://opentelemetry.io/docs/security/): cân nhắc bảo mật khi thu thập và xuất telemetry.
- [OpenTelemetry — Collector Configuration](https://opentelemetry.io/docs/collector/configuration/): pipeline receivers, processors và exporters.
- [OpenTelemetry — Transform Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/transformprocessor): biến đổi/lọc telemetry ở collector; cần kiểm tra version triển khai.
- [OpenTelemetry — Sensitive Data](https://opentelemetry.io/docs/security/handling-sensitive-data/): hướng dẫn xử lý dữ liệu nhạy cảm trong telemetry.
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html): Observation API và handlers.
- [Micrometer — High Cardinality](https://docs.micrometer.io/micrometer/reference/observation/components.html): phân biệt low/high-cardinality key-values.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): tích hợp observability trong Spring Boot.
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): observations của các thành phần Spring AI theo phiên bản.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu không nên ghi và bảo vệ logs.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): quản lý secrets và khóa.
