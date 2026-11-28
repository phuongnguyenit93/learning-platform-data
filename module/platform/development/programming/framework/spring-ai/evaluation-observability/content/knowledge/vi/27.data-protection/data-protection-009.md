# Kiểm thử trường hợp nội dung nhạy cảm lọt vào thông báo lỗi

Một request Spring AI có thể thất bại ở nhiều tầng: xác thực đầu vào, truy vấn vector store, gọi ChatModel, gọi tool, parse structured output, gọi external evaluator hoặc ghi kết quả vào database. Khi lỗi xảy ra, framework/provider thường tạo exception để hỗ trợ kỹ sư điều tra. Exception message có thể chứa URL, request body, response fragment, prompt, retrieved document, tool arguments, account reference hoặc token. Nếu ứng dụng trả nguyên exception cho client, ghi nguyên stack trace vào log hoặc đính kèm body vào trace, một lỗi kỹ thuật có thể trở thành đường rò rỉ dữ liệu.

**Kiểm thử lỗi phải xác nhận nội dung nhạy cảm không xuất hiện ở bất kỳ kênh đầu ra nào, kể cả khi lỗi phát sinh sâu trong pipeline.** Ứng dụng cần chuyển lỗi nội bộ thành mã lỗi và thông báo an toàn; giữ chẩn đoán kỹ thuật trong nơi có quyền truy cập; lọc dữ liệu trước khi ghi logs/traces; và kiểm tra các đường đồng bộ, streaming, retry, fallback, async và background job.

Bài này thuộc chương **Bảo vệ dữ liệu** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline. Bài tập trung vào kiểm thử trường hợp nội dung nhạy cảm lọt vào thông báo lỗi, logs và telemetry khi ứng dụng AI gặp sự cố.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện các đường lỗi có thể mang theo PII, secrets và nội dung nghiệp vụ.
2. Phân biệt thông báo lỗi dành cho client với diagnostic details dành cho vận hành.
3. Chuẩn hóa exception thành safe error code, message và correlation reference.
4. Xử lý exception từ Spring AI, model provider, vector store, tool và evaluator.
5. Tránh ghi raw exception, request/response body hoặc prompt vào logs/traces.
6. Bảo vệ validation errors, stack traces, streaming errors và async failures.
7. Thiết kế redaction/sanitization có cấu trúc và fail closed.
8. Kiểm thử response body, headers, logs, traces, metrics, retries và exports bằng synthetic markers.
9. Dùng MockMvc/WebTestClient và test doubles để tái hiện lỗi sâu trong pipeline.
10. Điều tra lỗi với correlation ID mà không làm lộ thêm dữ liệu.

## 2. Vì sao thông báo lỗi là một ranh giới dữ liệu?

Một lỗi có thể được quan sát bởi nhiều đối tượng: end user, API gateway, browser, support engineer, on-call, log backend, trace backend, alert notification và external monitoring service. Mỗi kênh có audience, retention và quyền truy cập khác nhau.

Ví dụ, một provider trả HTTP 400 và body chứa đoạn prompt không hợp lệ. Nếu code nối response body vào exception message rồi global exception handler trả exception message về client, nội dung provider body có thể đi ra ngoài. Nếu logger ghi exception đầy đủ, stack trace có thể chứa cùng message. Nếu instrumentation ghi exception event vào span, trace backend cũng có thể nhận dữ liệu đó.

### 2.1. Error channel inventory

| Kênh | Ví dụ | Nguy cơ |
|---|---|---|
| **HTTP response** | JSON error body, headers, status text. | Người gọi nhận prompt, PII, provider body hoặc stack trace. |
| **Application logs** | Exception message, stack trace, structured fields. | Người có quyền đọc logs thấy dữ liệu ngoài scope. |
| **Trace events** | Exception type/message, span attributes. | Nội dung lỗi bị sao chép vào telemetry backend. |
| **Metrics labels** | Error message hoặc request identifier làm label. | Cardinality tăng và dữ liệu nhạy cảm bị lộ rộng. |
| **Gateway/proxy logs** | Request URI, body, upstream error. | Body/header bị ghi ở tầng hạ tầng. |
| **Alert/notification** | Error snippet, trace link, ticket description. | Dữ liệu bị gửi tới nhóm người nhận rộng. |
| **Streaming response** | SSE error event hoặc partial output. | Client nhận raw exception sau khi stream đã bắt đầu. |
| **Async job status** | Failed job details, queue dead-letter payload. | Worker/operator xem được raw content không cần thiết. |
| **Evaluation report** | Judge rationale, failed case excerpt. | Nội dung nhạy cảm được đưa vào report/export. |

### 2.2. Lỗi không chỉ là HTTP 500

Rò rỉ có thể xảy ra với 400 validation error, 401/403, 404, 409, 429 provider rate limit, 502/503 upstream failure, timeout, cancellation hoặc lỗi parse. Không giả định chỉ lỗi server mới cần sanitization.

### 2.3. Exception message là dữ liệu không đáng tin

Message có thể đến từ thư viện, provider, database driver, tool backend hoặc user-controlled input. Không được coi nó là text an toàn chỉ vì exception được tạo trong code Java. Xử lý exception message như một payload cần phân loại trước khi hiển thị hoặc ghi.

## 3. Các loại nội dung nhạy cảm có thể lọt vào lỗi

| Loại | Ví dụ marker giả | Vị trí có thể xuất hiện |
|---|---|---|
| **PII** | PERSON_MARKER_A71, EMAIL_MARKER_B82 | Validation message, provider body, tool error. |
| **Credentials** | API_KEY_MARKER_C93, BEARER_MARKER_D04 | HTTP client exception, header dump, config error. |
| **Private documents** | PRIVATE_DOC_MARKER_E15 | Vector store, parser exception, retrieval error. |
| **Conversation content** | PROMPT_MARKER_F26, ANSWER_MARKER_G37 | Model request/response, judge error. |
| **Business identifiers** | ACCOUNT_MARKER_H48, ORDER_MARKER_J59 | Tool arguments, SQL exception, downstream response. |
| **Internal configuration** | INTERNAL_HOST_MARKER_K60 | Connection exception, stack trace, environment diagnostics. |
| **Security metadata** | JWT claims, session IDs, signed URLs | Authentication/authorization exception. |
| **Evaluation artifacts** | Gold answer, judge rationale, rubric | Evaluator and report generation failures. |

Marker trong bảng chỉ là dữ liệu tổng hợp dùng cho kiểm thử. Không dùng thông tin khách hàng thật để chứng minh redaction.

## 4. Threat model theo pipeline Spring AI

Một request AI có nhiều thành phần tạo exception. Cần xác định nơi raw content đi vào exception và nơi exception được chuyển tiếp.

| Thành phần | Lỗi thường gặp | Dữ liệu có thể lộ |
|---|---|---|
| **Ingress/controller** | JSON binding, validation, request size. | Input field, header, query parameter. |
| **ChatClient/ChatModel** | Provider 4xx/5xx, timeout, serialization. | Prompt, model response, provider body, request ID. |
| **EmbeddingModel** | Batch embedding failure, invalid input. | Document text, chunk metadata. |
| **VectorStore/retriever** | Query/filter error, connection failure. | Search query, document reference, filter values. |
| **Prompt assembly** | Missing variable, template rendering. | Prompt variables và conversation history. |
| **Tool callback** | Business exception, downstream API failure. | Tool arguments, order/account details. |
| **Structured output parser** | JSON parse/schema validation. | Raw model completion. |
| **External evaluator** | Judge timeout, provider rejection, invalid score. | Candidate answer, evidence, rubric, judge response. |
| **Persistence** | Constraint violation, serialization, object storage. | Entity values, document content, identifiers. |
| **Async/streaming** | Worker failure, client disconnect, partial event. | Queue payload, partial answer, exception. |

### 4.1. Data flow khi lỗi xảy ra

```mermaid
flowchart TD
    REQ["User request / conversation"] --> APP["Spring AI application"]
    APP --> MODEL["ChatModel / provider"]
    APP --> RAG["Retriever / vector store"]
    APP --> TOOL["Tool callback"]
    APP --> EVAL["External evaluator"]
    MODEL --> EX["Exception / provider response"]
    RAG --> EX
    TOOL --> EX
    EVAL --> EX
    EX --> MAP["Safe error mapper"]
    MAP --> CLIENT["Client-safe error response"]
    EX --> DIAG["Restricted diagnostic pipeline"]
    DIAG --> REDACT["Field allowlist / sanitizer"]
    REDACT --> LOG["Logs and trace metadata"]
    MAP --> AUDIT["Security/audit event"]
¤¤¤

Error mapper tạo response đã chuẩn hóa. Diagnostic pipeline chỉ ghi các field được duyệt; không chuyển nguyên exception object sang mọi exporter. Audit event ghi loại sự kiện và correlation reference, không ghi payload nhạy cảm.

## 5. Phân biệt client-safe error và internal diagnostic

Một lỗi nên có hai biểu diễn riêng:

| Biểu diễn | Mục tiêu | Nội dung |
|---|---|---|
| **Client-safe error** | Giúp caller biết thao tác thất bại và cần làm gì tiếp. | Error code ổn định, message chung, correlation ID nếu cần, retry guidance an toàn. |
| **Internal diagnostic** | Giúp người vận hành tìm nguyên nhân. | Exception type, component, provider status, sanitized category, trace reference, deployment version. |

### 5.1. Ví dụ response an toàn

```json
{
  "type": "https://api.example.test/problems/ai-provider-unavailable",
  "title": "AI service temporarily unavailable",
  "status": 503,
  "code": "AI_PROVIDER_UNAVAILABLE",
  "detail": "The request could not be completed. Please retry later.",
  "correlationId": "corr-opaque-71"
}
```

Đây là response minh họa theo phong cách Problem Details. Correlation ID phải là reference ngẫu nhiên/opaque, không chứa user ID, prompt hoặc tenant secret. Không trả stack trace, provider response body, SQL, hostname nội bộ hoặc raw exception message.

### 5.2. Ví dụ response không an toàn

```json
{
  "status": 500,
  "message": "Provider rejected prompt: CUSTOMER_EMAIL=...",
  "exception": "HttpClientResponseException",
  "stackTrace": ["..."],
  "requestBody": "full prompt and retrieved documents"
}
```

Response kiểu này tiết lộ nội dung, cấu trúc nội bộ và chi tiết triển khai. Không trả exception class/stack trace nếu client không cần chúng để xử lý.

### 5.3. Error code phải ổn định

Dùng code có nghĩa nghiệp vụ/kỹ thuật rõ như AI_PROVIDER_UNAVAILABLE, RETRIEVAL_FAILED, TOOL_EXECUTION_FAILED, INVALID_MODEL_OUTPUT hoặc EVALUATION_UNAVAILABLE. Không tạo error code bằng cách nối exception message. Client có thể dùng code để quyết định retry hoặc hiển thị thông báo.

### 5.4. Không tiết lộ sự tồn tại của tài nguyên

Với resource không thuộc quyền caller, response nên tuân theo policy tránh xác nhận resource có tồn tại ở tenant khác. Ví dụ RESOURCE_NOT_FOUND có thể được dùng chung cho “không tồn tại” và “không được phép biết”, tùy API design.

## 6. Nguyên tắc thiết kế error handling

1. **Normalize:** chuyển exception về nhóm lỗi nội bộ có định nghĩa.
2. **Allowlist:** chỉ chọn field được phép xuất hiện trong response/log/trace.
3. **Minimize:** không mang raw input/output sang error object.
4. **Sanitize:** lọc CR/LF, control characters, secrets và nội dung không mong muốn khi field text thực sự cần ghi.
5. **Correlate:** dùng request/trace reference để nối các tín hiệu an toàn.
6. **Separate:** client response và internal diagnostic có schema/quyền riêng.
7. **Fail closed:** nếu sanitizer hoặc policy gặp lỗi, bỏ nội dung chẩn đoán nhạy cảm thay vì ghi raw.
8. **Test all sinks:** response, logs, traces, metrics, alerts, queues và exports.

### 6.1. Không dựa vào regex đơn lẻ

Regex có thể phát hiện một số email, phone hoặc token pattern nhưng không nhận diện hết dữ liệu nhạy cảm trong mọi ngôn ngữ/format. Kết hợp schema allowlist, structured error codes, secret detection, field-level classification và synthetic leak tests. Redaction là lớp phòng vệ bổ sung; thiết kế tốt nhất là không đưa raw content vào error metadata ngay từ đầu.

### 6.2. Không log exception nguyên vẹn một cách mặc định

Logger ghi exception đầy đủ có thể ghi message và nested causes. Chỉ dùng khi exception đã được kiểm soát và không mang payload nhạy cảm. Với exception từ provider/tool/parser, hãy log một diagnostic object đã chọn lọc; nếu cần stack trace, chỉ ghi exception class và stack trong sink được giới hạn, sau khi xác nhận message/cause không chứa dữ liệu nhạy cảm hoặc dùng handler loại bỏ message.

## 7. Chuẩn hóa exception thành safe error

Tạo một abstraction nội bộ biểu diễn lỗi đã được chuẩn hóa:

```java
public record SafeApplicationError(
    String code,
    int httpStatus,
    String clientMessage,
    String category,
    boolean retryable
) {}
```

Ví dụ mapping:

```java
public SafeApplicationError mapAiException(Throwable error) {
    if (hasCause(error, ProviderUnavailableException.class)) {
        return new SafeApplicationError(
            "AI_PROVIDER_UNAVAILABLE",
            503,
            "The AI service is temporarily unavailable.",
            "provider_unavailable",
            true
        );
    }

    if (hasCause(error, InvalidModelOutputException.class)) {
        return new SafeApplicationError(
            "INVALID_MODEL_OUTPUT",
            502,
            "The AI service returned an invalid response.",
            "invalid_model_output",
            false
        );
    }

    return new SafeApplicationError(
        "AI_REQUEST_FAILED",
        500,
        "The request could not be completed.",
        "unexpected",
        false
    );
}
¤¤¤

Đây là pseudocode minh họa. hasCause cần duyệt cause chain an toàn và tránh vòng lặp. Không đưa error.getMessage() vào clientMessage. Không giả định tất cả provider exception có cùng class; adapter cần chuyển provider-specific failures về exception category nội bộ.

### 7.1. Giữ nguyên nguyên nhân để điều tra ở nơi phù hợp

Không nhất thiết phải bỏ mọi thông tin chẩn đoán. Có thể ghi error.category, component, sanitized provider status, exception type, trace reference và build version. Nếu cần stack trace, lưu vào restricted diagnostic sink với retention/access riêng và bảo đảm message/cause đã được xử lý.

### 7.2. Retry guidance phải chính xác

Chỉ đánh dấu retryable cho lỗi tạm thời như timeout/rate limit theo policy. Không khuyến khích retry validation, authorization hoặc business rule failures. Client-safe response có thể có retryable hoặc Retry-After khi phù hợp; không tiết lộ provider quota internals.

## 8. Bảo vệ exception từ model provider

Model provider có thể trả lỗi chứa request IDs, model identifiers, content filters, quota information hoặc fragments của request/response. Adapter phải chuẩn hóa chúng trước khi exception đi lên controller.

### 8.1. Không nối response body vào exception message

Tránh:

```java
throw new AiProviderException(
    "Provider failed with body: " + responseBody
);
```

Nên dùng exception nội bộ chỉ mang category và status:

```java
throw new AiProviderException(
    ProviderErrorCategory.RATE_LIMITED,
    upstreamStatus,
    safeProviderRequestRef
);
```

Ví dụ constructor là abstraction nội bộ. Nếu cần raw body để điều tra, xử lý ở adapter với redaction/allowlist và sink riêng; không lưu nó trong exception message phổ biến.

### 8.2. Xử lý provider request ID

Provider request ID có thể giúp support tra cứu. Chỉ lưu nếu policy cho phép, giới hạn quyền và không trả về ID có thể truy vấn dữ liệu provider ngoài ý muốn. Dùng internal correlation ID làm ID công khai cho client.

### 8.3. Timeout và network exceptions

Network exception có thể chứa host, path, query string hoặc proxy configuration. Client chỉ nên nhận code chung như AI_PROVIDER_UNAVAILABLE. Logs có thể giữ endpoint alias đã allowlist, status category và duration; không ghi URL có credential hoặc signed query.

## 9. Bảo vệ lỗi từ RAG, vector store và document parsing

Retriever/vector store errors có thể chứa query text, filter expression, collection name, document IDs hoặc chunk contents. Parser errors có thể đưa ra đoạn text từ PDF/HTML hoặc tên file nhạy cảm.

### 9.1. Không đưa search query vào lỗi trả client

Nếu vector store reject filter, trả RETRIEVAL_FAILED hoặc INVALID_RETRIEVAL_CONFIGURATION; không đưa query/filter expression vào response. Chỉ ghi retriever version, store alias, error category và correlation reference.

### 9.2. Bảo vệ document parser

Exception khi parse file có thể chứa path, filename, extracted text hoặc metadata. Client nên nhận message chung như DOCUMENT_PROCESSING_FAILED. Log file reference dạng opaque và parser category; tránh ghi full extracted text.

### 9.3. Filter/tenant errors

Nếu tenant filter không hợp lệ hoặc không có quyền, không ghi expression có tenant IDs hoặc resource references thô. Ghi reason code như scope_filter_rejected và audit authorization decision theo schema an toàn.

## 10. Bảo vệ tool callback errors

Tool thường kết nối với business services và có thể nhận account/order/customer data. Khi tool thất bại, exception có thể chứa request/response body của downstream service.

### 10.1. Tool result và exception là untrusted data

Không trả nguyên downstream error cho model. Tool handler nên chuyển lỗi thành outcome code đã định nghĩa, ví dụ ORDER_NOT_FOUND, ACTION_NOT_ALLOWED, DEPENDENCY_UNAVAILABLE. Nếu model cần thông tin để trả lời user, chỉ cung cấp nội dung đã được authorization và giảm thiểu.

### 10.2. Không đưa raw tool exception vào prompt

Nếu tool exception bị đưa lại vào conversation history, model có thể lặp nó cho user hoặc gửi tiếp sang external judge. Tách tool error code khỏi diagnostic detail; chỉ thêm safe error result vào model context.

### 10.3. Side-effect failure

Với refund/update/delete, error message có thể chứa transaction ID hoặc trạng thái tài khoản. Dùng idempotency reference và business outcome code. Không log payload thanh toán hoặc raw identifiers chỉ để mô tả lỗi.

## 11. Validation, parser và serialization errors

Validation framework có thể đưa rejected value vào error object. Nếu field chứa email, prompt, document text hoặc token, response validation mặc định có thể làm lộ giá trị.

### 11.1. Không trả rejected value

Response lỗi nên chứa field name, stable code và safe message; không chứa rejectedValue, raw JSON, property value hoặc binding target object.

### 11.2. Structured output parser

Parser error có thể giữ toàn bộ model completion. Tránh ghi rawOutput trong exception hoặc validation message. Ghi parser type, schema version và failure category; nếu cần lưu candidate output cho evaluation, phải đi qua content capture policy riêng.

### 11.3. Serialization errors

Jackson/JSON serialization exceptions có thể nêu property path và giá trị lỗi. Chỉ trả thông tin schema cần thiết; không trả raw object hoặc nested payload.

## 12. Spring Boot global exception handler

Dùng một điểm xử lý HTTP exception tập trung để tránh mỗi controller tự trả message khác nhau.

Ví dụ minh họa:

```java
import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class SafeApiExceptionHandler {

    private final SafeErrorMapper errorMapper;
    private final CorrelationIdProvider correlationIds;

    public SafeApiExceptionHandler(
        SafeErrorMapper errorMapper,
        CorrelationIdProvider correlationIds
    ) {
        this.errorMapper = errorMapper;
        this.correlationIds = correlationIds;
    }

    @ExceptionHandler(Exception.class)
    public ProblemDetail handleUnexpected(Exception exception) {
        SafeApplicationError safe = errorMapper.map(exception);
        ProblemDetail problem = ProblemDetail.forStatus(
            HttpStatus.valueOf(safe.httpStatus())
        );
        problem.setType(URI.create(
            "https://api.example.test/problems/" + safe.code().toLowerCase()
        ));
        problem.setTitle(safe.code());
        problem.setDetail(safe.clientMessage());
        problem.setProperty("code", safe.code());
        problem.setProperty("correlationId", correlationIds.current());
        return problem;
    }
}
¤¤¤

Ví dụ cần điều chỉnh theo Spring Boot/Spring Framework version và API contract. Handler không trả exception message hoặc stack trace. Error mapper nên phân biệt lỗi đã biết với unexpected errors; logging diagnostics được thực hiện riêng qua safe diagnostic service. Không để exception handler ghi nguyên exception bằng default logger nếu message/cause có thể chứa payload.

### 12.1. Xử lý validation errors riêng

Với MethodArgumentNotValidException hoặc binding errors, map mỗi field sang field name và error code đã allowlist. Không serialize FieldError nguyên vẹn vì nó có thể chứa rejected value.

### 12.2. Không để handler che mất security events

401/403 và access denial cần audit event an toàn. Response không nên tiết lộ tenant/resource khác, nhưng hệ thống vẫn cần ghi reason category và actor reference trong security audit sink.

## 13. Sanitization cho logs và traces

### 13.1. Structured logging theo allowlist

Nên ghi:

```text
event = ai.request.failed
error.code = AI_PROVIDER_UNAVAILABLE
error.category = provider_unavailable
component = chat_model
provider.alias = approved-provider-a
http.status_code = 503
retryable = true
correlation.id = corr-opaque-71
pipeline.version = support-ai-v4
```

Không ghi raw prompt, candidate answer, retrieved chunks, tool arguments, provider body, Authorization header hoặc exception message không được kiểm soát.

### 13.2. CR/LF và log injection

Nếu cần ghi text do user/provider cung cấp, phải encode/sanitize control characters để ngăn log forging và line injection. Nhưng không dựa vào việc loại newline để làm an toàn cho PII/secret; nội dung vẫn có thể nhạy cảm trên một dòng.

### 13.3. Trace exception events

Instrumentation có thể tự động thêm exception type/message/stacktrace vào span. Cần kiểm tra Micrometer/OTel instrumentation và exporter configuration. Có thể bỏ exception message, chỉ ghi safe error code/category hoặc dùng processor có allowlist. Không giả định chỉ vì ứng dụng không gọi logger thì exception sẽ không xuất hiện trong trace.

### 13.4. Metrics labels

Chỉ dùng error category/code có tập giá trị giới hạn. Không dùng exception message, prompt fragment, request ID, customer ID hoặc raw path làm label. Những giá trị này vừa có thể chứa dữ liệu nhạy cảm vừa tạo cardinality cao.

### 13.5. Alert payload

Alert chỉ nên có service, environment, error code, time window và link có authorization. Tránh copy exception message hoặc raw log line vào email/chat notification.

## 14. Streaming, async và background job failures

### 14.1. Streaming response

Sau khi HTTP headers/SSE stream đã bắt đầu, ứng dụng có thể không còn đổi status code. Khi lỗi xảy ra giữa stream, gửi event theo schema an toàn:

```text
event: error
data: {"code":"AI_STREAM_FAILED","message":"The response stream ended unexpectedly.","correlationId":"corr-opaque-71"}
```

Không gửi exception message trong SSE event. Nếu stream đã phát partial answer, cần xác định policy về giữ/hiển thị phần đã gửi và không tự động ghi partial content vào error logs.

### 14.2. Reactive pipelines

Trong Reactor, onErrorResume hoặc error hooks có thể chuyển exception thành response. Tránh dùng error.getMessage() trong fallback; map sang safe error DTO. Kiểm tra cả doOnError hooks và instrumentation tự động ghi exception event.

### 14.3. CompletableFuture và executor

Exception có thể bị wrap trong CompletionException hoặc ExecutionException. Duyệt cause chain để phân loại nhưng không log toàn bộ message chain. Correlation context cần được truyền qua executor theo cơ chế phù hợp.

### 14.4. Queue và dead-letter queue

Không đưa raw request payload vào error description của failed job. Dead-letter queue có thể giữ nguyên message body; cần ACL, encryption, retention và quy trình redrive. Chỉ ghi job reference, error category và retry state vào dashboard.

### 14.5. Retry/fallback không được bỏ qua sanitizer

Mỗi attempt có thể tạo một exception mới. Cả provider fallback, tool retry và evaluator retry phải đi qua cùng error mapping, logging policy và payload redaction.

## 15. Test strategy: kiểm tra cả response lẫn side channels

Một test chỉ kiểm tra HTTP body là chưa đủ. Cùng exception có thể xuất hiện trong logs, traces, metrics, alert hoặc async job metadata.

### 15.1. Synthetic marker strategy

Dùng marker giả, dễ tìm và khác nhau theo loại dữ liệu:

```text
PII_PERSON_MARKER_A71
PII_EMAIL_MARKER_B82@example.test
SECRET_API_KEY_MARKER_C93
SECRET_BEARER_MARKER_D04
RAG_PRIVATE_DOC_MARKER_E15
PROMPT_CONTENT_MARKER_F26
TOOL_ACCOUNT_MARKER_G37
JUDGE_RATIONALE_MARKER_H48
INTERNAL_HOST_MARKER_J59
```

Đặt markers vào input, provider error body, retrieved chunk, tool arguments, parser output và nested cause. Sau khi request thất bại, tìm markers trong response, headers, logs, traces, metric labels, alert payload và dead-letter metadata.

### 15.2. Test layers

| Layer | Cách test | Điều cần xác nhận |
|---|---|---|
| **Unit** | Gọi error mapper với exception có marker. | Client message/code không chứa marker. |
| **Web slice** | MockMvc/WebTestClient và mock service. | HTTP status/body/header an toàn. |
| **Integration** | Mock provider/vector/tool server trả lỗi có marker. | Adapter không truyền raw body lên. |
| **Observability** | Capture appender và in-memory span exporter. | Logs/spans không có marker. |
| **Async** | Worker/queue failure với marker. | Job status/DLQ metadata không lộ. |
| **End-to-end** | Chạy request qua toàn pipeline. | Không có marker ở bất kỳ sink nào đã khai báo. |

### 15.3. Kiểm tra serialized payload

Kiểm tra body sau serialization, không chỉ object trước khi serialize. Jackson custom serializer, ProblemDetail properties hoặc exception handler có thể thêm field ngoài dự kiến. Quét response bytes/string và headers trong test.

## 16. Ví dụ test với MockMvc

Ví dụ minh họa controller/service trả exception có chứa marker:

```java
@WebMvcTest(AiController.class)
@Import(SafeApiExceptionHandler.class)
class AiErrorResponseTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    AiService aiService;

    @Test
    void doesNotExposeSensitiveExceptionMessage() throws Exception {
        String marker = "SECRET_API_KEY_MARKER_C93";
        given(aiService.answer(anyString()))
            .willThrow(new RuntimeException("Upstream failed: " + marker));

        mvc.perform(post("/api/ai/answer")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"question\":\"hello\"}"))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code").value("AI_REQUEST_FAILED"))
            .andExpect(content().string(not(containsString(marker))));
    }
}
¤¤¤

Đây là ví dụ minh họa; điều chỉnh annotations/imports theo Spring Boot và Spring Framework version. Test cần xác nhận handler thực sự được import và status/error code khớp API contract. Có thể thêm assertions cho Content-Type, headers, không có stackTrace, exception hoặc requestBody.

## 17. Ví dụ test với provider adapter và log capture

Một fake provider trả lỗi có marker giúp kiểm tra adapter:

```java
@Test
void providerBodyDoesNotEscapeThroughNormalizedException() {
    String marker = "PROMPT_CONTENT_MARKER_F26";
    fakeProvider.respondWithError(400, "Rejected input: " + marker);

    AiProviderException error = assertThrows(
        AiProviderException.class,
        () -> chatModel.call(testPrompt())
    );

    assertEquals(ProviderErrorCategory.INVALID_REQUEST, error.category());
    assertFalse(error.getMessage().contains(marker));
}
¤¤¤

Nếu logger/trace exporter tự ghi exception, bổ sung test capture appender và in-memory exporter. Ví dụ khái niệm:

```java
String allDiagnostics = capturedLogs + capturedSpanEvents;
assertFalse(allDiagnostics.contains("SECRET_API_KEY_MARKER_C93"));
assertFalse(allDiagnostics.contains("PROMPT_CONTENT_MARKER_F26"));
assertTrue(allDiagnostics.contains("AI_PROVIDER_UNAVAILABLE"));
¤¤¤

Không nên chỉ assert marker vắng mặt trong getMessage(); kiểm tra nested causes, suppressed exceptions, serialized logs và trace events. Test code minh họa, tên fake provider/appender phụ thuộc test infrastructure của dự án.

## 18. Test matrix đầy đủ

| Test | Kịch bản | Kỳ vọng |
|---|---|---|
| **ERR01 — Generic 500** | Exception chứa prompt marker. | Response chỉ có safe code/message. |
| **ERR02 — Provider body** | Provider 4xx body chứa PII/secret marker. | Marker không vào response/log/trace. |
| **ERR03 — Nested cause** | Marker nằm trong deepest cause. | Không leak qua cause chain. |
| **ERR04 — Suppressed exception** | Marker nằm trong suppressed exception. | Không leak khi log diagnostics. |
| **ERR05 — Validation rejected value** | Field chứa email/token marker. | Error body không có rejected value. |
| **ERR06 — Parser raw output** | Model completion chứa private document marker rồi parse fail. | Parser error không lộ raw completion. |
| **ERR07 — Vector store query** | Query/filter có tenant marker rồi backend throw. | Response/log chỉ có safe category. |
| **ERR08 — Document parser** | File parser exception chứa extracted text. | Không lộ content/path nhạy cảm. |
| **ERR09 — Tool downstream** | Tool service trả account/order marker trong error body. | Model/client chỉ nhận safe outcome. |
| **ERR10 — External judge** | Judge provider error chứa candidate/rubric marker. | Không lộ payload trong error channels. |
| **ERR11 — Stack trace** | Stack trace/message có secret marker. | Client không nhận stack; diagnostic sink được lọc/giới hạn. |
| **ERR12 — Trace exception event** | OTel instrumentation tự thêm exception message. | Span chỉ có safe category hoặc message đã loại bỏ. |
| **ERR13 — Metric cardinality** | Exception message thay đổi theo request. | Không tạo label từ raw message/request data. |
| **ERR14 — Alert notification** | Error trigger có marker. | Alert payload không chứa marker. |
| **ERR15 — SSE failure** | Stream fail sau khi đã gửi một phần output. | SSE error event dùng safe schema. |
| **ERR16 — Reactive error hook** | onErrorResume nhận exception có marker. | Fallback không dùng raw message. |
| **ERR17 — Async/DLQ** | Background job thất bại với payload có marker. | Job status/DLQ metadata được kiểm soát. |
| **ERR18 — Retry/fallback** | Provider A lỗi có marker, provider B cũng lỗi. | Không leak ở bất kỳ attempt nào. |
| **ERR19 — Sanitizer failure** | Sanitizer timeout/throws. | Không fallback sang raw logging/response. |
| **ERR20 — Correlation ID** | Error response chứa correlation reference. | ID opaque, không chứa PII/tenant secret. |
| **ERR21 — Header leakage** | Upstream response có sensitive headers. | Không forward headers nguyên bản tới client. |
| **ERR22 — Serialization** | JSON serialization error chứa property value. | Response không trả object/rejected value. |
| **ERR23 — Unauthorized resource** | Lỗi lookup resource tenant khác. | Không xác nhận resource existence ngoài scope. |
| **ERR24 — Error report export** | Export failed cases có marker. | Report chỉ chứa fields được phép. |
| **ERR25 — Regression guard** | Thêm dependency/instrumentation mới. | Leak tests vẫn pass trên toàn sinks. |

## 19. Xử lý lỗi khi sanitizer hoặc logging backend thất bại

Sanitizer là một thành phần có thể lỗi. Không để lỗi của sanitizer tạo ra fallback nguy hiểm.

### 19.1. Fail closed

Nếu sanitizer không thể xử lý exception message, không ghi message đó. Có thể ghi một event tối thiểu như:

```text
event = diagnostic_suppressed
reason = sanitizer_failure
component = chat_model
correlation.id = corr-opaque-71
```

Không gắn exception gốc vào event này nếu chính exception đó có thể chứa dữ liệu nhạy cảm.

### 19.2. Không làm request nghiệp vụ thất bại chỉ vì log sink lỗi

Logging/telemetry thường là side channel. Nếu exporter lỗi, ứng dụng có thể tiếp tục trả safe error response và ghi metric tối thiểu tại local buffer theo policy. Không được chuyển sang log raw exception để “đảm bảo có đủ thông tin”.

### 19.3. Diagnostic quarantine

Nếu tổ chức cần giữ exception gốc cho forensic, dùng một restricted diagnostic store riêng với access approval, encryption, short retention và audit. Không coi dead-letter queue hoặc general application logs là nơi quarantine an toàn.

## 20. Quy trình điều tra lỗi không làm lộ dữ liệu

1. Nhận correlation ID và error code từ client.
2. Tìm trace/log metadata theo correlation reference trong backend có quyền.
3. Xác định component, provider alias, status category, latency và pipeline version.
4. Kiểm tra exception type/cause đã được sanitize.
5. Nếu cần raw content, yêu cầu access theo incident purpose và tenant scope.
6. Dùng synthetic reproduction hoặc redacted case để tái hiện.
7. Xác định các sinks đã nhận event và phạm vi người có thể đọc.
8. Xử lý log/trace/report copies theo retention/deletion policy nếu đã có leak.
9. Thêm regression test ở layer nơi lỗi được tạo và mọi sink nhận lỗi.

Không copy raw exception vào ticket/chat chỉ để chia sẻ nhanh. Dùng error code, correlation reference và diagnostic summary đã giảm thiểu.

## 21. Bài tập thực hành

Một endpoint /api/assistant chạy Spring AI RAG. Khi vector store timeout, adapter ném exception chứa query và filter. Controller không bắt lỗi; global handler trả exception message. Logger ghi stack trace, OpenTelemetry instrumentation tự ghi exception event, còn API gateway đang bật request/response body logging. Một evaluator chạy async cũng lưu exception message vào job status.

### Câu hỏi

1. Liệt kê tất cả kênh có thể làm lộ nội dung.
2. Thiết kế safe error response cho client.
3. Adapter vector store nên ném exception dạng nào?
4. Làm thế nào kiểm tra OTel exception events?
5. Gateway body logging cần cấu hình ra sao?
6. Job status và DLQ nên lưu field nào?
7. Nếu sanitizer lỗi thì behavior mong muốn là gì?
8. Viết test với marker trong deepest cause.
9. Đề xuất sáu regression tests sau khi sửa.
10. Nếu marker đã xuất hiện trong production logs, cần xử lý gì?

### Gợi ý đáp án

**1.** HTTP response, application stack trace, trace exception event, gateway request/response logs, async job status và DLQ payload. Alert/report cũng cần kiểm tra nếu được tạo từ lỗi.

**2.** Trả status 503, code RETRIEVAL_UNAVAILABLE, message chung và opaque correlation ID; không trả query/filter/exception/stack.

**3.** Dùng exception nội bộ có category như VECTOR_STORE_TIMEOUT, sanitized store alias/status và retryability; không nối raw query/filter/body vào message.

**4.** Dùng in-memory span exporter, tạo exception có marker trong message/cause, rồi kiểm tra span events/attributes. Cấu hình bỏ raw exception message hoặc thay bằng safe category.

**5.** Tắt body logging cho route có dữ liệu nhạy cảm; redact headers; không ghi Authorization/cookie; chỉ giữ metadata request cần thiết.

**6.** Job reference, task type, error code/category, retry count, timestamps và correlation reference. Payload gốc nằm trong store riêng có ACL/retention nếu thực sự cần.

**7.** Không ghi raw message; emit event tối thiểu diagnostic_suppressed và trả safe error response.

**8.** Tạo nested cause chain, đặt marker trong deepest cause, gọi error mapper/handler, assert marker vắng trong response/log/trace và safe code hiện diện.

**9.** Provider body, nested cause, OTel event, gateway logging, async/DLQ và sanitizer failure tests. Có thể thêm alert/export regression.

**10.** Xác định index/time range/recipients, hạn chế quyền truy cập, xử lý bản sao theo incident và retention policy, đánh giá phạm vi lộ dữ liệu, bảo toàn audit và bổ sung regression tests. Không tuyên bố đã xóa mọi bản sao nếu chưa xác minh.

## 22. Ghi nhớ

Thông báo lỗi là một data output và phải được kiểm soát như response thông thường. Exception từ model provider, RAG, tool, evaluator, parser, validation và async worker có thể mang theo prompt, PII, secrets hoặc business identifiers. Hãy chuẩn hóa lỗi thành safe code/message/correlation ID cho client; giữ diagnostic metadata theo allowlist và sink có quyền riêng. Không trả getMessage(), rejected values, request body, provider body hoặc stack trace; kiểm tra cả nested/suppressed causes và exception events do instrumentation tự tạo. Streaming, retry, fallback, gateway, queue, alert và export đều là error channels cần test. Dùng synthetic markers và kiểm tra serialized response, logs, traces, metrics cùng side channels; nếu sanitizer lỗi thì fail closed. Nhờ đó, đội vận hành vẫn điều tra được latency, reliability và chất lượng Spring AI mà không biến sự cố thành nguồn rò rỉ dữ liệu.

### Tài liệu tham khảo

- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): Problem Details và xử lý lỗi REST.
- [Spring Framework — Controller Advice](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html): xử lý exception tập trung qua controller advice.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): cấu hình logging trong Spring Boot.
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): quan sát các thành phần Spring AI và cách dữ liệu đi vào observations.
- [OpenTelemetry — Exception Recording](https://opentelemetry.io/docs/specs/semconv/exceptions/exceptions-spans/): exception events trên spans và semantic conventions.
- [OpenTelemetry — Handling Sensitive Data](https://opentelemetry.io/docs/security/handling-sensitive-data/): giảm thiểu dữ liệu nhạy cảm trong telemetry.
- [OWASP — Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html): thông báo lỗi an toàn và diagnostic handling.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): nội dung không nên ghi và bảo vệ logs.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): bảo vệ secrets và credentials.
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): xử lý lỗi API, response và security controls cho REST.
