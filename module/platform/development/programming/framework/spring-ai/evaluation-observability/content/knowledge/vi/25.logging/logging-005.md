# Rút gọn dữ liệu lớn và che giá trị nhạy cảm

Một pipeline Spring AI xử lý một request có thể tạo ra prompt dài hàng chục nghìn ký tự, hàng chục retrieved chunks, nhiều tool arguments, response streaming và stack trace từ provider. Nếu log toàn bộ object để tiện debug, một event có thể lớn hơn cả request metadata cần thiết; đồng thời nó có thể chứa access token, email, account number, nội dung hội thoại hoặc tài liệu nội bộ.

Log quá lớn làm tăng chi phí truyền tải, indexing và lưu trữ; khiến truy vấn chậm; tạo noise cho người trực vận hành; và làm tăng phạm vi ảnh hưởng khi dữ liệu nhạy cảm bị truy cập sai quyền. Cắt chuỗi theo số ký tự cũng không giải quyết được vấn đề bảo mật: secret có thể nằm ở đầu chuỗi, giữa chuỗi hoặc trong field lồng nhau.

Một logging design tốt cần thực hiện hai việc có thứ tự rõ ràng: **giảm dữ liệu xuống đúng metadata cần thiết và che/loại bỏ giá trị nhạy cảm trước khi serialize**. Với dữ liệu có cấu trúc, xử lý theo field và schema. Với nội dung tự do, dùng detector như lớp bổ sung và giới hạn việc ghi ngay từ đầu. Khi cần giữ prompt, response hoặc context để đánh giá, lưu chúng qua evidence service có policy riêng; log chỉ giữ metadata và opaque reference.

Bài học thuộc module **SPRING_AI_EVALUATION_OBSERVABILITY**. Nội dung tập trung vào log size budgets, field allowlist, structured summarization, recursive redaction, masking, pseudonymization, SLF4J/Logback, Java/Jackson, kiểm thử sentinel và điều tra sự cố. Mục tiêu là giữ log đủ hữu ích để theo dõi chất lượng, latency, chi phí và lỗi của Spring AI mà không lưu payload lớn hoặc secrets ngoài phạm vi cho phép.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao log lớn gây chi phí và rủi ro bảo mật.
2. Phân biệt drop, aggregate, summarize, truncate, sample và reference.
3. Thiết kế size budget theo event, field, string, array và nesting depth.
4. Dùng allowlist để chỉ ghi metadata cần thiết.
5. Nhận diện secrets, credentials, PII và content trong nested JSON.
6. Áp dụng field-aware redaction trước khi serialize.
7. Phân biệt redaction, masking và pseudonymization.
8. Dùng regex/content detectors như lớp phòng thủ bổ sung và hiểu giới hạn của chúng.
9. Tạo structured logs an toàn bằng SLF4J/Logback.
10. Dùng Java/Jackson để giới hạn object fields, array items, string length và event bytes.
11. Ghi error metadata mà không dump exception/request body.
12. Kiểm thử redaction, truncation và secret leakage bằng JUnit.
13. Xây quy trình ứng phó khi log đã chứa dữ liệu nhạy cảm.

## 2. Vì sao log lớn là vấn đề

Một model call có thể chứa:

- Prompt với system/developer/user messages.
- Conversation history và memory.
- Retrieved chunks từ nhiều tài liệu.
- Tool definitions, arguments và results.
- Model response hoặc JSON output.
- Provider error body và stack trace.
- Multimodal metadata hoặc payload references.

Nếu mỗi stage log toàn bộ object, một request có thể tạo nhiều bản sao của cùng content. Log collector phải nhận và index dữ liệu đó; dashboard và search query phải xử lý các field rất lớn; retention và backup cũng tốn thêm tài nguyên.

| Vấn đề | Hệ quả |
| --- | --- |
| Event quá lớn | Collector reject, truncate hoặc chậm |
| Nhiều bản sao payload | Network, storage và indexing cost tăng |
| Raw prompt/response | PII, secrets hoặc tài liệu nội bộ bị lộ |
| Nested objects không giới hạn | Event khó đọc và khó kiểm soát size |
| Stack trace lặp lại | Log noise và alert fatigue |
| Free-text không chuẩn hóa | Khó group, aggregate và tìm root cause |
| Log volume không có budget | Sự cố burst có thể làm nghẽn logging pipeline |

### 2.1. Log phải trả lời câu hỏi vận hành

Trước khi thêm một field, hỏi nó phục vụ quyết định nào:

- Model/provider nào được gọi?
- Prompt version và pipeline version nào?
- Có bao nhiêu retrieved/selected chunks?
- Input/output token usage là bao nhiêu?
- Stage mất bao lâu?
- Tool authorization/execution có thành công không?
- Error code và retry disposition là gì?
- Evidence artifact nào có thể mở theo quyền?

Nếu câu trả lời không giúp tìm, phân loại hoặc xử lý sự cố, field đó có thể không cần nằm trong operational log.

### 2.2. Không lấy log làm bản sao của request

Log không phải request archive, prompt debugger hay evidence store. Giữ bản gốc ở nơi phù hợp với mục đích và quyền truy cập. Operational log nên mô tả hoạt động và trỏ tới evidence nếu policy cho phép.

## 3. Sáu cách giảm dữ liệu và khi nào dùng

| Kỹ thuật | Hành động | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| Drop | Bỏ field không cần | Không ghi raw prompt | Cách an toàn nhất khi field không cần |
| Aggregate | Gộp thành số liệu | result count, error count | Không giữ từng item |
| Summarize | Ghi metadata tóm tắt | token count, status, duration | Không dùng LLM summary làm metadata mặc định |
| Truncate | Giới hạn kích thước | stack frames tối đa 10 | Chỉ sau redaction; đánh dấu bị cắt |
| Sample | Chọn một phần event | sample success events | Không sample mất audit/security events |
| Reference | Lưu opaque ID | evidence.ref | Artifact cần ACL/retention riêng |

### 3.1. Drop

Nếu prompt body không cần trong log, bỏ hẳn field. Đừng thay prompt bằng một đoạn preview; preview vẫn là content.

### 3.2. Aggregate

Thay danh sách chunks bằng result count, selected count, min/max score, top rank hoặc distribution. Thay danh sách lỗi lặp bằng error count theo code/stage. Aggregate cần giữ semantics rõ ràng: số liệu thuộc attempt, case hay run.

### 3.3. Summarize bằng metadata

Ví dụ một retrieval event:

~~~json
{
  "event.name": "ai.retrieval.completed",
  "run.id": "support-eval-v5",
  "case.id": "POLICY-017",
  "rag.corpus.version": "policy-v3",
  "rag.top_k": 8,
  "rag.result.count": 8,
  "rag.selected.chunk_count": 3,
  "rag.context.truncated": true,
  "rag.context.token_estimate": 2100,
  "duration.ms": 74,
  "outcome": "SUCCESS"
}
~~~

Không cần nhúng 8 chunks vào log. Nếu cần review nội dung, dùng evidence reference.

### 3.4. Truncate

Truncate giới hạn kích thước field. Phải đánh dấu field đã bị cắt để người đọc không nhầm phần còn lại là toàn bộ giá trị. Với prompt/response, mặc định không truncate để log; không có lý do để lưu một phần raw content trong operational logs.

### 3.5. Sample

Sampling có thể giảm success logs có volume cao. Nhưng error, security decision, audit event, release decision hoặc event cần durability phải theo policy riêng. Sampling không phải redaction.

### 3.6. Reference

Một opaque evidence ID giữ khả năng drill-down mà không sao chép payload:

~~~json
{
  "content.capture.status": "STORED",
  "evidence.ref": "ev_01JVB8K8M4Y7W8N1",
  "evidence.classification": "CONFIDENTIAL"
}
~~~

Không ghi signed URL hoặc bearer token vào log.

## 4. Thiết kế size budget

Một event cần giới hạn ở nhiều cấp. Chỉ đặt giới hạn tổng event mà không giới hạn field/array/nesting có thể khiến sanitizer phải xử lý object rất lớn trước khi cắt.

Một budget minh họa:

| Cấp | Giới hạn mẫu | Mục đích |
| --- | ---: | --- |
| Event JSON | 16 KiB | Giới hạn record |
| String metadata | 512 ký tự | Không để field text tăng vô hạn |
| Object fields | 40 fields | Chặn map lớn |
| Array items | 20 items | Chặn danh sách dài |
| Nesting depth | 5 levels | Chặn object lồng sâu |
| Error stack frames | 10 frames | Giảm stack noise |
| Message | 160 ký tự | Message dễ đọc |
| Event rate | Theo service budget | Kiểm soát volume theo thời gian |

Đây là giá trị minh họa, không phải mặc định bắt buộc. Chọn budget dựa trên log backend, event schema, workload và chi phí. Đặt giới hạn theo byte khi hệ thống đo size thực; ký tự Unicode không tương đương byte UTF-8.

### 4.1. Giới hạn từng field trước giới hạn toàn event

Một object có 100 field, mỗi field 100 KB, không nên được serialize nguyên khối rồi mới phát hiện event quá lớn. Hãy giới hạn object fields, arrays, depth và string values trong quá trình sanitize.

### 4.2. Có marker cho dữ liệu bị cắt

Ví dụ:

~~~json
{
  "error.message.safe": "Provider returned a long diagnostic message...[TRUNCATED]",
  "logging.truncated": true,
  "logging.truncation.reason": "FIELD_LENGTH_LIMIT"
}
~~~

Marker giúp consumer biết log không đầy đủ. Không dùng chuỗi rỗng để thay cho truncation vì sẽ không phân biệt được empty value và bị cắt.

### 4.3. Event vượt byte budget

Nếu sau khi allowlist, redact và bound fields mà JSON vẫn vượt max bytes, có thể bỏ payload chi tiết và phát một overflow summary event gồm event name, correlation IDs, payload byte count và reason code. Không fallback sang serialize raw object.

### 4.4. Đừng cắt JSON bằng substring

Cắt JSON string ở byte/character bất kỳ có thể tạo JSON không hợp lệ hoặc cắt mất phần đóng quote/brace. Sanitize object trước, serialize JSON hợp lệ sau; nếu vượt budget, tạo một event summary JSON hợp lệ.

## 5. Phân loại field nhạy cảm

Sensitive values thường xuất hiện trong nhiều tên field khác nhau.

| Nhóm | Field/path ví dụ | Xử lý |
| --- | --- | --- |
| Credentials | password, clientSecret, apiKey | Redact hoàn toàn |
| Tokens | accessToken, refreshToken, bearer | Redact hoàn toàn |
| Headers | Authorization, Cookie, Set-Cookie | Redact hoàn toàn |
| Personal data | email, phone, address, national ID | Drop/redact/pseudonymize theo policy |
| Payment/account | card number, bank account | Redact hoặc tokenization |
| AI content | prompt, messages, completion, responseBody | Không log mặc định |
| RAG content | query, chunks, document text | Không log mặc định |
| Tool payload | arguments, result body | Không log mặc định |
| Internal identifiers | tenant ID, document ID, user ID | Pseudonymize hoặc opaque reference |
| Operational metadata | provider, model, duration, token counts | Log nếu policy cho phép |

### 5.1. Tên field không phải bằng chứng duy nhất

Một secret có thể nằm trong field tên message, detail, error, url hoặc debug. Một field có tên token có thể là token count chứ không phải credential. Dùng typed schema và field path allowlist thay vì chỉ tìm từ khóa toàn cục.

### 5.2. Nested JSON

Sensitive value có thể nằm sâu trong:

~~~json
{
  "request": {
    "headers": {
      "Authorization": "Bearer secret-value"
    },
    "messages": [
      {
        "role": "user",
        "content": "My account number is 12345678"
      }
    ]
  }
}
~~~

Redaction phải xử lý recursive object và array. Nếu không cần payload, tốt nhất bỏ cả request object khỏi log event.

### 5.3. Free-text và exception

Exception message có thể chứa URL, query string, response body hoặc input. Free-text detectors giúp phát hiện một số pattern phổ biến nhưng không bảo đảm tìm hết secrets/PII. Ưu tiên safe error codes và allowlisted fields.

## 6. Redaction, masking và pseudonymization

Ba cách xử lý có mục đích khác nhau:

- **Redaction:** loại bỏ giá trị, thay bằng marker như [REDACTED].
- **Masking:** giữ một phần để nhận diện định dạng, ví dụ ****4321.
- **Pseudonymization:** thay giá trị bằng alias ổn định được quản lý, ví dụ user_7F2A.

| Dữ liệu | Redaction | Masking | Pseudonymization |
| --- | --- | --- | --- |
| Email | [REDACTED] | j***@example.com | user_7F2A |
| Account | [REDACTED] | ****4321 | acct_A91C |
| API key | [REDACTED] | Không giữ prefix nếu không cần | Không tạo alias tự chế |
| Tenant ID | [REDACTED] | Không phù hợp | tenant_3C81 |
| Prompt body | Không capture | Preview vẫn là content | Hash không làm prompt vô hại |

### 6.1. Redaction là lựa chọn mặc định cho secrets

Không giữ một phần API key hoặc bearer token chỉ để tiện nhận diện. Nếu cần biết credential nào được dùng, log secret reference/version do secret manager quản lý, không log secret value.

### 6.2. Masking có thể vẫn tiết lộ

Bốn chữ số cuối account/card có thể đủ để liên kết một người hoặc giao dịch. Masking phải được phê duyệt theo mục đích và classification. Đừng giả định masked value là anonymous.

### 6.3. Pseudonymization cần key/mapping được quản lý

Hash email trực tiếp có thể bị dò bằng dictionary. Nếu cần liên kết ổn định, dùng keyed HMAC hoặc tokenization service với key rotation, access control và mapping store riêng. Không ghi key/mapping vào log.

### 6.4. Không thay đổi dữ liệu nghiệp vụ gốc

Sanitizer chỉ tạo bản sao dành cho logging. Không sửa prompt, response, tool arguments, domain event hoặc evidence artifact gốc. Redaction cho log và redaction cho evidence là hai policy khác nhau.

## 7. Thứ tự xử lý an toàn

Một pipeline logging nên thực hiện theo thứ tự:

1. Chọn event type và mục đích.
2. Tạo event DTO chỉ có field được allowlist.
3. Loại bỏ content không cần log.
4. Redact field nhạy cảm theo schema/path.
5. Chạy free-text detectors như lớp bổ sung.
6. Giới hạn string, array, object fields và nesting depth.
7. Serialize JSON.
8. Kiểm tra max event bytes.
9. Gửi tới sink được phê duyệt.

Không serialize raw object trước rồi trông chờ collector xóa field. Collector có thể nhận bản gốc trước khi redaction downstream diễn ra.

### 7.1. Vì sao redaction trước truncation?

Nếu cắt chuỗi trước, secret có thể nằm trong phần đầu còn lại hoặc detector không còn đủ context để nhận diện. Redact trước, sau đó mới bound giá trị an toàn. Với content không được phép log, drop toàn bộ thay vì redaction rồi truncate.

### 7.2. Fail closed

Nếu sanitizer hoặc policy engine lỗi, không fallback sang raw payload. Có thể bỏ field/event chi tiết, phát safe failure code hoặc dừng workflow nếu evidence là điều kiện bắt buộc. Hành vi phải được định nghĩa theo mức độ quan trọng của event.

## 8. Rút gọn dữ liệu cho từng thành phần Spring AI

| Component | Dữ liệu lớn/nhạy cảm | Metadata thay thế |
| --- | --- | --- |
| Prompt assembly | rendered messages, history | template version, role counts, token estimate |
| Retrieval | query, chunks, documents | corpus/index version, top-k, counts, latency |
| Model | request/response body | provider/model, usage, finish reason, duration |
| Tool | arguments/result JSON | tool name/schema, authorization, status, operation ref |
| Evaluator | answer/reference/feedback | metric, verdict, rubric/judge version |
| Error handler | exception body/headers | error code/type, stage, retry disposition |
| Streaming | token chunks | TTFT, chunk count, output tokens, completion status |
| Multimodal | base64/audio/image bytes | media type, byte size, processing status, opaque ref |

### 8.1. Prompt assembly

Ghi template version, digest nếu policy cho phép, message count, role counts và token estimate. Không ghi preview hoặc first N characters.

### 8.2. Retrieval

Ghi retrieved count, selected count, context token estimate, truncation flag, filter/reranker version và duration. Không log chunks hoặc query text. Nếu cần review, log retrieval evidence reference.

### 8.3. Model calls

Ghi provider/model, safe generation parameters, input/output token usage, finish reason, duration, retry count và outcome. Không serialize ChatRequest/ChatResponse.

### 8.4. Tool calling

Ghi tool name, schema version, validation/authorization result, operation status, duration và idempotency reference đã được bảo vệ. Không log arguments/result nguyên trạng.

### 8.5. Evaluator

Ghi metric name/status/score, judge model/version, rubric version và evidence refs. Không log full answer, reference facts hoặc free-form feedback mặc định.

### 8.6. Streaming và multimodal

Đối với streaming, ghi time to first token, chunk count và tổng duration. Với image/audio/video, ghi media type, byte count, processing status và artifact ref. Không ghi base64, transcript hoặc raw chunks.

## 9. Ví dụ event đã được rút gọn

Một retrieval event có thể giữ đủ metadata để phân tích:

~~~json
{
  "event.name": "ai.retrieval.completed",
  "event.version": 1,
  "run.id": "support-eval-v5",
  "case.id": "POLICY-017",
  "attempt.id": "POLICY-017-attempt-1",
  "rag.corpus.version": "policy-v3",
  "rag.top_k": 8,
  "rag.result.count": 8,
  "rag.selected.chunk_count": 3,
  "rag.context.token_estimate": 2100,
  "rag.context.truncated": true,
  "duration.ms": 74,
  "outcome": "SUCCESS",
  "logging.truncated": false
}
~~~

Một model failure event có thể giữ error metadata:

~~~json
{
  "event.name": "ai.model.call.failed",
  "event.version": 1,
  "model.call.id": "model-call-8f31",
  "ai.provider": "example-provider",
  "ai.model": "chat-model-stable",
  "error.code": "AI_PROVIDER_RATE_LIMITED",
  "error.type": "ProviderRateLimitException",
  "retry.disposition": "AFTER_RETRY_AFTER",
  "retry.after.ms": 2000,
  "error.message.safe": "Provider rate limit reached",
  "request.content.status": "NOT_LOGGED",
  "logging.truncated": false
}
~~~

Hai event không cần prompt, retrieved chunks, request body hoặc exception message nguyên bản.

## 10. Java/Jackson: sanitizer đệ quy cho JSON

Một sanitizer tổng quát có thể là lớp phòng thủ bổ sung khi nhận một JSON-like object. Trong production, ưu tiên event DTO allowlist. Không truyền ChatRequest, ChatResponse hoặc tool arguments trực tiếp vào sanitizer với suy nghĩ nó sẽ nhận diện mọi nội dung.

Ví dụ dưới đây minh họa:

- Redact các key nhạy cảm đã biết ở mọi cấp.
- Redact bearer token và email trong free text.
- Giới hạn string length, object fields, array items và nesting depth.
- Kiểm tra event JSON byte budget sau serialize.
- Trả overflow summary JSON nếu vượt budget.

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.TextNode;

import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

public final class SafeJsonLogSanitizer {

    private static final String REDACTED = "[REDACTED]";

    private static final Set<String> SENSITIVE_KEYS = Set.of(
            "authorization",
            "proxyauthorization",
            "cookie",
            "setcookie",
            "password",
            "passwd",
            "secret",
            "clientsecret",
            "apikey",
            "accesskey",
            "accesstoken",
            "refreshtoken",
            "privatekey",
            "credential",
            "credentials",
            "email",
            "phone",
            "phonenumber",
            "nationalid",
            "taxnumber",
            "bankaccount",
            "cardnumber",
            "dateofbirth",
            "address",
            "prompt",
            "systemprompt",
            "userprompt",
            "rawprompt",
            "rawcompletion",
            "completion",
            "response",
            "responsebody",
            "requestbody",
            "messages",
            "context",
            "query",
            "question",
            "answer",
            "transcript",
            "documenttext",
            "chunktext",
            "retrievedchunks",
            "toolarguments",
            "arguments",
            "toolresult",
            "rawresponse",
            "rawrequest",
            "content"
    );

    private static final Pattern BEARER = Pattern.compile(
            "(?i)\\bBearer\\s+[A-Za-z0-9._~+/=-]+");

    private static final Pattern EMAIL = Pattern.compile(
            "(?i)\\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}\\b");

    private final ObjectMapper mapper;
    private final int maxStringChars;
    private final int maxObjectFields;
    private final int maxArrayItems;
    private final int maxDepth;
    private final int maxEventBytes;

    public SafeJsonLogSanitizer(
            ObjectMapper mapper,
            int maxStringChars,
            int maxObjectFields,
            int maxArrayItems,
            int maxDepth,
            int maxEventBytes) {

        this.mapper = mapper;
        this.maxStringChars = maxStringChars;
        this.maxObjectFields = maxObjectFields;
        this.maxArrayItems = maxArrayItems;
        this.maxDepth = maxDepth;
        this.maxEventBytes = maxEventBytes;

        if (maxStringChars < 1 || maxObjectFields < 1
                || maxArrayItems < 1 || maxDepth < 1
                || maxEventBytes < 256) {
            throw new IllegalArgumentException("Invalid logging size budget");
        }
    }

    public String sanitizeJson(Object allowlistedEvent)
            throws JsonProcessingException {

        JsonNode input = mapper.valueToTree(allowlistedEvent);
        JsonNode safe = sanitizeNode(input, 0);
        byte[] bytes = mapper.writeValueAsBytes(safe);

        if (bytes.length <= maxEventBytes) {
            return new String(bytes, StandardCharsets.UTF_8);
        }

        ObjectNode overflow = mapper.createObjectNode();
        overflow.put("event.name", "logging.payload.omitted");
        overflow.put("logging.truncated", true);
        overflow.put("logging.truncation.reason", "EVENT_BYTE_LIMIT");
        overflow.put("logging.max_bytes", maxEventBytes);
        overflow.put("logging.sanitized_bytes", bytes.length);

        return mapper.writeValueAsString(overflow);
    }

    private JsonNode sanitizeNode(JsonNode node, int depth) {
        if (node == null || node.isNull()) {
            return node;
        }

        if (depth > maxDepth) {
            return TextNode.valueOf("[TRUNCATED_DEPTH]");
        }

        if (node.isObject()) {
            ObjectNode safe = mapper.createObjectNode();
            Iterator<Map.Entry<String, JsonNode>> fields = node.fields();
            int count = 0;

            while (fields.hasNext()) {
                Map.Entry<String, JsonNode> field = fields.next();

                if (count >= maxObjectFields) {
                    safe.put("_logging_truncated_fields", true);
                    break;
                }
                count++;

                String name = field.getKey();
                if (isSensitiveKey(name)) {
                    safe.put(name, REDACTED);
                } else {
                    safe.set(name, sanitizeNode(field.getValue(), depth + 1));
                }
            }
            return safe;
        }

        if (node.isArray()) {
            ArrayNode safe = mapper.createArrayNode();
            int limit = Math.min(node.size(), maxArrayItems);

            for (int i = 0; i < limit; i++) {
                safe.add(sanitizeNode(node.get(i), depth + 1));
            }

            if (node.size() > limit) {
                ObjectNode marker = mapper.createObjectNode();
                marker.put("_logging_truncated_items", true);
                safe.add(marker);
            }
            return safe;
        }

        if (node.isTextual()) {
            String redacted = redactFreeText(node.textValue());
            return TextNode.valueOf(bound(redacted));
        }

        return node.deepCopy();
    }

    private boolean isSensitiveKey(String key) {
        String normalized = key
                .replaceAll("[^A-Za-z0-9]", "")
                .toLowerCase(Locale.ROOT);

        return SENSITIVE_KEYS.contains(normalized)
                || normalized.endsWith("apikey")
                || normalized.endsWith("accesstoken")
                || normalized.endsWith("refreshtoken")
                || normalized.endsWith("password");
    }

    private String redactFreeText(String value) {
        String withoutBearer = BEARER.matcher(value)
                .replaceAll("Bearer [REDACTED]");
        return EMAIL.matcher(withoutBearer)
                .replaceAll("[REDACTED_EMAIL]");
    }

    private String bound(String value) {
        if (value.length() <= maxStringChars) {
            return value;
        }

        return value.substring(0, maxStringChars) + "...[TRUNCATED]";
    }
}
~~~

Đây là ví dụ học tập cần review và harden trước production. Nó xử lý một số key/pattern phổ biến; không phát hiện mọi PII, secret hoặc nội dung tự do. Key normalization cũng cần được kiểm tra với schema thực tế. Allowlist event DTO vẫn là lớp bảo vệ chính.

### 10.1. Thứ tự gọi sanitizer

Chỉ truyền event metadata đã được chọn vào sanitizer. Không truyền raw prompt/response rồi hy vọng danh sách key nhạy cảm bắt được mọi biến thể. Các field content nên bị drop trước khi tạo DTO.

### 10.2. Event byte limit là giới hạn cuối

Ví dụ trả overflow summary khi JSON sau sanitize vượt max bytes. Summary giữ event marker và giới hạn, không giữ payload lớn. Trong hệ thống thật, thêm correlation IDs đã allowlist vào overflow event để có thể tìm lại attempt.

### 10.3. String truncation và Unicode

Ví dụ dùng substring theo UTF-16 code units nên có thể cắt giữa surrogate pair trong một số trường hợp hiếm. Implementation production nên cắt theo Unicode code points hoặc theo byte budget sau khi encode UTF-8, đồng thời vẫn giữ JSON hợp lệ.

### 10.4. Sensitive key policy cần mở rộng theo domain

Các key trong ví dụ chưa bao gồm mọi tên như nationalId, taxNumber, bankAccount, phoneNumber hoặc customerAddress. Bổ sung theo data inventory của tổ chức. Không thêm field mới vào allowlist mà chưa review classification.

## 11. Java: log metadata thay vì object lớn

Ví dụ ghi retrieval metadata bằng SLF4J 2.x fluent API:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class RetrievalEventLogger {

    private static final Logger log =
            LoggerFactory.getLogger(RetrievalEventLogger.class);

    public void completed(
            String runId,
            String caseId,
            String attemptId,
            String corpusVersion,
            int topK,
            int resultCount,
            int selectedCount,
            long contextTokenEstimate,
            boolean contextTruncated,
            long durationMs) {

        log.atInfo()
                .addKeyValue("event.name", "ai.retrieval.completed")
                .addKeyValue("event.version", 1)
                .addKeyValue("run.id", runId)
                .addKeyValue("case.id", caseId)
                .addKeyValue("attempt.id", attemptId)
                .addKeyValue("rag.corpus.version", corpusVersion)
                .addKeyValue("rag.top_k", topK)
                .addKeyValue("rag.result.count", resultCount)
                .addKeyValue("rag.selected.chunk_count", selectedCount)
                .addKeyValue("rag.context.token_estimate",
                        contextTokenEstimate)
                .addKeyValue("rag.context.truncated", contextTruncated)
                .addKeyValue("duration.ms", durationMs)
                .addKeyValue("outcome", "SUCCESS")
                .log("AI retrieval completed");
    }
}
~~~

Logger chỉ nhận metadata primitive/bounded values. Không truyền List<Document>, query text hoặc chunk content.

### 11.1. Không log collection.toString()

Tránh:

~~~java
log.debug("Retrieved documents: {}", documents);
log.debug("Tool arguments: {}", arguments);
log.debug("Model response: {}", response);
~~~

Những object này có thể chứa nội dung lớn hoặc nhạy cảm. Trích xuất count, status, schema version, duration và opaque refs.

### 11.2. Ghi message ngắn, fields có cấu trúc

Message giúp người đọc lướt log; fields mới là contract để query. Không đưa dữ liệu động vào message nếu field riêng đã có.

## 12. Rút gọn exception và stack trace

Exception có thể chứa raw response body, request URL, headers hoặc prompt fragments. Không nên ghi nguyên exception message ở mọi boundary.

Một error event vận hành thường cần:

- error.code ổn định.
- exception.type.
- stage/provider/model.
- HTTP status hoặc SDK code nếu an toàn.
- retry disposition.
- attempt number và budget.
- trace ID/span ID.
- safe message đã sanitize.

### 12.1. Stack trace có giới hạn

Nếu stack trace cần cho debugging, cân nhắc ghi tối đa N frames vào sink nội bộ có access control. Không lặp stack trace ở mỗi tầng; chỉ boundary chịu trách nhiệm quyết định retry/fail nên ghi error event chính.

### 12.2. Không serialize exception object

Tránh chuyển exception thành JSON bằng serializer tổng quát. Getter hoặc toString() có thể đưa message/cause/response body vào output. Tạo safe error DTO từ các field đã được kiểm soát.

### 12.3. Error message không thay error code

Message có thể dài, chứa dữ liệu động và thay đổi theo SDK version. Dùng error code/category/retry disposition để query và alert; message chỉ là mô tả ngắn.

## 13. Logback và structured output

Logback pattern encoder và JSON encoder có hành vi khác nhau. Với structured logs, dùng JSON encoder được hỗ trợ và kiểm thử để fields được xuất thành JSON fields đúng kiểu.

Ví dụ cấu hình minh họa với Logstash Logback Encoder:

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

Thêm encoder dependency theo dependency management của dự án. JSON encoding không tự redaction; event DTO và sanitizer phải làm việc đó trước khi log.

### 13.1. Kiểm tra kiểu dữ liệu

Xác nhận duration/token counts là JSON numbers, booleans vẫn là boolean, event name là field riêng và null/unknown có semantics rõ. Đừng nối tất cả thành chuỗi để dễ đọc.

### 13.2. Kiểm tra duplicate appenders

Logger con có thể propagate event lên root. Kiểm additivity và appender routing để tránh duplicate records hoặc gửi event tới sink không phù hợp.

### 13.3. Collector limits

Mỗi collector/backend có giới hạn record size và field size riêng. Kiểm tra giới hạn thực tế; application max event bytes nên thấp hơn mức backend từ chối để có khoảng đệm cho metadata do encoder thêm vào.

## 14. Sampling, rate limiting và aggregation

Giới hạn event size chưa kiểm soát event rate. Một retry storm có thể tạo hàng triệu event nhỏ.

### 14.1. Sampling success events

Có thể sample model-call success metadata khi traffic rất lớn, nhưng phải đảm bảo metric counters/histograms vẫn ghi đầy đủ. Sampling log không được làm sai denominator của evaluation report.

### 14.2. Giữ error và audit theo policy

Không sample mất security denials, config changes, release decisions hoặc audit events nếu policy yêu cầu đầy đủ. Có thể rate-limit chi tiết lặp lại nhưng vẫn ghi counter/summary và first/recovery event.

### 14.3. Aggregate repeated errors

Ví dụ thay vì in cùng stack trace 10.000 lần, ghi summary theo cửa sổ:

~~~json
{
  "event.name": "ai.error.aggregate",
  "error.code": "AI_PROVIDER_RATE_LIMITED",
  "ai.provider": "example-provider",
  "window.seconds": 60,
  "occurrence.count": 10000,
  "affected.attempt.count": 7300,
  "first_seen": "2026-05-18T10:00:00Z",
  "last_seen": "2026-05-18T10:01:00Z",
  "retry.exhausted.count": 120
}
~~~

Không gộp các error code khác nhau hoặc các environment/tenant scope khác nhau nếu điều đó làm mất ý nghĩa điều tra.

### 14.4. Không dùng log sampling để giảm dữ liệu nhạy cảm

Nếu một event chứa secret, sampling 99% không giải quyết vấn đề. Loại bỏ/redact secret ở source trước khi áp dụng sampling.

## 15. Truncation, aggregation và evidence phải có semantics

Consumer cần biết event là đầy đủ hay đã bị rút gọn.

Các marker hữu ích:

| Field | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| logging.truncated | true | Có field/item bị cắt |
| logging.truncation.reason | FIELD_LENGTH_LIMIT | Lý do cắt |
| logging.original_item_count | 250 | Số item ban đầu nếu an toàn |
| logging.logged_item_count | 20 | Số item được giữ |
| content.capture.status | NOT_CAPTURED | Không lưu content |
| evidence.status | AVAILABLE | Có evidence theo quyền |
| evidence.status | EXPIRED | Artifact đã hết hạn |
| redaction.profile | pii-v3 | Profile đã áp dụng |

Không ghi original content length nếu độ dài tự nó nhạy cảm trong workload cụ thể. Chọn metadata theo data classification.

### 15.1. Không suy từ missing field

Field vắng mặt có thể là không áp dụng, chưa được cung cấp, bị redacted hoặc bị loại do size budget. Nếu consumer cần phân biệt, ghi status enum riêng.

### 15.2. Evidence status không phải verdict

STORED/REDACTED/NOT_CAPTURED mô tả trạng thái capture. PASS/FAIL/NOT_EVALUATED mô tả chất lượng. Không trộn hai nhóm.

### 15.3. Digest sau redaction

Nếu lưu redacted artifact, digest cần tính trên bytes redacted và canonicalization version tương ứng. Nếu cần đối chiếu raw source, quản lý digest raw trong secure manifest theo policy; không tự đưa raw digest vào log rộng.

## 16. Kiểm thử redaction và size budget

Unit test cần kiểm các trường hợp:

- Sensitive keys ở root và nested object.
- Sensitive fields trong array.
- Bearer token và email trong free text.
- String dài bị truncate có marker.
- Object fields/array items vượt giới hạn.
- Nesting depth vượt giới hạn.
- Event vượt byte budget trả overflow summary hợp lệ.
- Sanitizer không mutate input object.
- JSON output vẫn parse được.
- Unknown usage không bị đổi thành zero.

### 16.1. Sentinel tests

Dùng giá trị giả duy nhất, không dùng secret thật:

~~~text
RAW_API_KEY_SENTINEL_7A91
RAW_PROMPT_SENTINEL_8C42
PERSONAL_EMAIL_SENTINEL@example.test
RAW_TOOL_RESULT_SENTINEL_3D10
~~~

Serialize event sau sanitize rồi assert không chứa sentinel. Chạy integration test qua logger backend và collector test sink; unit test sanitizer riêng không chứng minh toàn pipeline an toàn.

### 16.2. False positives và false negatives

Detector email có thể che một chuỗi không phải email; detector token có thể bỏ sót định dạng mới. Ghi metric về sanitizer failures/overflow, review mẫu synthetic và cập nhật policy. Không tuyên bố regex bảo vệ toàn diện.

### 16.3. Property-based/fuzz testing

Có thể tạo input lồng sâu, key casing khác nhau, Unicode, newline, control characters và payload rất lớn. Mục tiêu là xác nhận sanitizer không crash, không tạo JSON invalid và luôn tuân size limits. Không đưa dữ liệu thật vào fuzz corpus.

## 17. JUnit: kiểm sanitizer

Ví dụ test với Jackson và JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class SafeJsonLogSanitizerTest {

    private final ObjectMapper mapper = new ObjectMapper();

    private final SafeJsonLogSanitizer sanitizer =
            new SafeJsonLogSanitizer(
                    mapper,
                    32,
                    10,
                    3,
                    3,
                    2048);

    @Test
    void redactsSensitiveNestedKeys() throws Exception {
        var input = mapper.readTree("""
                {
                  "event.name": "ai.tool.call.completed",
                  "request": {
                    "headers": {
                      "Authorization": "Bearer RAW_API_KEY_SENTINEL_7A91"
                    },
                    "provider_api_key": "RAW_API_KEY_SENTINEL_7A91",
                    "messages": [
                      {"role": "user", "content": "RAW_PROMPT_SENTINEL_8C42"}
                    ]
                  }
                }
                """);

        String json = sanitizer.sanitizeJson(input);
        JsonNode output = mapper.readTree(json);

        assertEquals("[REDACTED]",
                output.at("/request/headers/Authorization").asText());
        assertEquals("[REDACTED]",
                output.at("/request/provider_api_key").asText());
        assertFalse(json.contains("RAW_API_KEY_SENTINEL_7A91"));
        assertFalse(json.contains("RAW_PROMPT_SENTINEL_8C42"));
    }

    @Test
    void redactsBearerAndEmailInsideFreeText() throws Exception {
        var textSanitizer = new SafeJsonLogSanitizer(
                mapper, 128, 10, 3, 3, 2048);
        var input = mapper.createObjectNode()
                .put("error.message.safe",
                        "Bearer RAW_API_KEY_SENTINEL_7A91 contact user@example.test");

        String json = textSanitizer.sanitizeJson(input);

        assertFalse(json.contains("RAW_API_KEY_SENTINEL_7A91"));
        assertFalse(json.contains("user@example.test"));
        assertTrue(json.contains("[REDACTED_EMAIL]"));
    }

    @Test
    void boundsLongStringsAndArrays() throws Exception {
        var input = mapper.createObjectNode();
        input.put("message", "x".repeat(200));

        var values = mapper.createArrayNode();
        values.add("one");
        values.add("two");
        values.add("three");
        values.add("four");
        input.set("values", values);

        JsonNode output = mapper.readTree(sanitizer.sanitizeJson(input));

        assertTrue(output.get("message").asText().contains("[TRUNCATED]"));
        assertTrue(output.get("values").size() <= 4);
        assertTrue(output.get("values").get(3)
                .has("_logging_truncated_items"));
    }

    @Test
    void largeEventBecomesSmallValidOverflowSummary() throws Exception {
        var tinyBudgetSanitizer = new SafeJsonLogSanitizer(
                mapper, 1000, 10, 3, 3, 256);
        var input = mapper.createObjectNode()
                .put("message", "x".repeat(500));

        String json = tinyBudgetSanitizer.sanitizeJson(input);
        JsonNode output = mapper.readTree(json);

        assertEquals("logging.payload.omitted",
                output.get("event.name").asText());
        assertEquals("EVENT_BYTE_LIMIT",
                output.get("logging.truncation.reason").asText());
        assertTrue(json.getBytes(java.nio.charset.StandardCharsets.UTF_8)
                .length < 256);
    }
}
~~~

Test dùng Java text blocks, yêu cầu Java 15+; ví dụ cũng giả định Jackson databind và JUnit 5 đã có trong project. Đây là bài kiểm tra học tập, cần điều chỉnh theo Jackson/JDK version đang dùng.

### 17.1. Những test bổ sung nên có

- Key names khác casing hoặc dấu phân cách: api_key, apiKey, API-KEY.
- Nested arrays và object sâu.
- Unicode surrogate boundary khi truncate.
- Null/unknown fields.
- Event có nhiều field metadata và correlation IDs.
- Input object không bị mutate sau sanitize.
- Redactor lỗi phải fail closed.
- Structured encoder không tự thêm raw exception message.

## 18. Kiểm soát log size trong Spring AI pipeline

Một policy thực tế có thể dùng các giới hạn khác nhau theo event type:

| Event | Chính sách size gợi ý |
| --- | --- |
| Model call completed | Chỉ metadata, giới hạn event nhỏ |
| Retrieval completed | Counts, top-k, duration; không chunks |
| Tool call completed | Tool/schema/status; không arguments/result |
| Evaluation completed | Verdict/rubric/evidence refs; không answer |
| Error event | Safe error code/type/message bounded |
| Run summary | Aggregate counts và report ref |
| Content capture event | Artifact metadata only; raw content ở evidence store |

### 18.1. Run summary thay hàng nghìn case events

Một run có thể có nhiều case. Giữ case-level event nếu cần audit/traceability theo policy; bổ sung run summary aggregate để dashboard không phải đọc toàn bộ case logs. Không đưa danh sách case IDs khổng lồ vào một event.

### 18.2. Trace events và span attributes

Không đưa raw prompt/response vào span attributes. Giới hạn số attributes/events theo tracing backend. Trace IDs và span IDs dùng correlation; content cần evidence store.

### 18.3. Metrics cho log pipeline

Theo dõi:

- log event count.
- dropped/sampled event count.
- oversized event count.
- sanitizer failure count.
- redaction count theo rule/category.
- collector rejection/backpressure.
- average/p95 event bytes.
- bytes exported per service/environment.

Không dùng raw secret values làm metric labels. Dùng bounded reason codes.

## 19. Xử lý lỗi sanitizer và overflow

Sanitizer là một phần của logging pipeline và cũng có thể gặp lỗi.

### 19.1. Sanitizer exception

Nếu sanitizer lỗi, không gọi logger với object ban đầu. Có thể ghi một fallback event tối giản gồm event type, correlation IDs đã allowlist và sanitizer error code. Nếu event là audit-critical, dùng durable audit mechanism thay vì nuốt lỗi.

### 19.2. Event quá lớn

Nếu event vượt budget sau sanitize, ghi overflow summary và metric. Nếu event cần thiết cho business workflow, persist business event theo schema/broker policy riêng; không cố ép toàn bộ payload vào operational log.

### 19.3. Collector unavailable

Application logging thường best-effort; không để collector outage làm hỏng request thông thường. Nhưng audit-critical events hoặc evaluation evidence cần durability phải dùng store/outbox tương ứng. Phân biệt rõ hai đường dữ liệu.

### 19.4. Redaction policy không tải được

Fail closed với content. Không tự dùng policy cũ hoặc permissive fallback nếu không được định nghĩa. Ghi policy failure code và dừng content capture; business execution có thể tiếp tục hoặc dừng theo yêu cầu evidence.

## 20. Ứng phó khi phát hiện log đã chứa secret hoặc PII

Nếu phát hiện raw data trong log:

1. Xác định logger/component và source event.
2. Tắt hoặc sửa nguồn phát content ở application/SDK/HTTP client.
3. Giới hạn quyền truy cập index, exports và dashboards liên quan.
4. Xác định thời gian, environment, tenant và loại dữ liệu.
5. Kiểm tra collector, search index, archive, backup và downstream sinks.
6. Rotate/revoke credentials nếu token/secret có thể đã bị ghi.
7. Áp dụng deletion/retention hold theo incident policy.
8. Không copy raw value vào ticket hoặc chat để mô tả incident.
9. Thêm sentinel test và config guard ngăn tái diễn.
10. Ghi closure event bằng metadata và reference được phép.

Không tự xóa dữ liệu tùy tiện nếu incident policy yêu cầu giữ forensic evidence. Việc containment, deletion và legal hold phải theo quy trình tổ chức.

## 21. Anti-pattern thường gặp

**Log toàn bộ request/response rồi truncate.** Secret có thể vẫn nằm trong phần còn lại; payload đã được serialize và gửi vào pipeline.

**Truncate trước redaction.** Detector có thể mất context và secret vẫn lọt vào phần giữ lại.

**Chỉ dùng regex.** Không phát hiện mọi secret/PII và có false positives.

**Dùng masking cho API keys.** Prefix/suffix vẫn có thể giúp nhận diện hoặc khai thác credential.

**Log prompt preview.** Preview vẫn là raw content.

**Serialize List<Document> hoặc ChatResponse.** Object có thể rất lớn và chứa content.

**Giới hạn mỗi string nhưng không giới hạn array/depth.** Event vẫn có thể phình to.

**Cắt JSON bằng substring.** Tạo JSON invalid và mất semantics.

**Dùng LLM summary làm metadata mặc định.** Summary vẫn có thể chứa dữ liệu nhạy cảm.

**Sampling để giảm rò rỉ.** Event còn lại vẫn có thể chứa secret.

**Nuốt sanitizer error rồi log raw fallback.** Biến lỗi bảo vệ thành rò rỉ dữ liệu.

**Không ghi truncation marker.** Người đọc hiểu nhầm dữ liệu một phần là đầy đủ.

**Đưa IDs có cardinality cao vào metrics labels.** Tăng chi phí và khó vận hành.

**Dùng operational log làm evidence archive.** Không có ACL, audit và retention phù hợp cho content.

## 22. Bài thực hành: rút gọn và che dữ liệu trong logging pipeline

**Bối cảnh:** chatbot Spring AI dùng RAG và tool getOrderStatus. Một case tạo prompt dài, 20 retrieved chunks, tool arguments có account number và provider trả exception chứa response body. Log backend giới hạn event 16 KiB.

### Phần A — Data inventory

Liệt kê field của prompt, retrieval, model, tool, evaluator và exception. Đánh dấu metadata, content, PII, secret và field không cần log.

**Đầu ra:** classification matrix và allowlist event schema.

### Phần B — Size budget

Đặt max event bytes, max string chars, object fields, array items, nesting depth và stack frames. Xác định behavior khi vượt từng giới hạn.

**Đầu ra:** logging size budget.

### Phần C — Sanitizer

Implement recursive sanitizer cho JSON-like objects. Redact secret keys, bound arrays/strings/depth, detect bearer/email patterns và tạo overflow summary JSON hợp lệ.

**Đầu ra:** Java sanitizer và unit tests.

### Phần D — Spring AI event DTOs

Tạo metadata DTO cho retrieval/model/tool/evaluator. Không nhận raw ChatRequest, ChatResponse, List<Document> hoặc tool arguments. Log counts, status, duration và evidence refs.

**Đầu ra:** structured log event examples.

### Phần E — Integration tests

Chạy sentinel values qua SLF4J/Logback, provider SDK stub, HTTP mock và tracing exporter. Quét output để bảo đảm sentinel không xuất hiện trong operational logs. Kiểm JSON byte budget.

**Đầu ra:** test report và sample safe events.

### Phần F — Incident drill

Mô phỏng secret bị log trong exception message. Xác định source, tắt logger/SDK wire logging, giới hạn sink access, rotate secret, xử lý retention/deletion và thêm regression test.

**Đầu ra:** incident runbook và containment evidence.

### Checklist nghiệm thu

- [ ] Event schema chỉ chứa metadata được allowlist.
- [ ] Prompt/response/context/tool payload không log mặc định.
- [ ] Có size budget cho event và từng cấu trúc lồng.
- [ ] Object fields, array items và nesting depth được giới hạn.
- [ ] String truncation có marker.
- [ ] Redaction chạy trước truncation.
- [ ] Sensitive keys được xử lý ở mọi cấp.
- [ ] Free-text detectors chỉ là lớp bổ sung.
- [ ] Secrets được redact hoàn toàn.
- [ ] Pseudonymization dùng key/tokenization được quản lý.
- [ ] Sanitizer không mutate dữ liệu nghiệp vụ gốc.
- [ ] JSON output vẫn hợp lệ sau sanitize/overflow.
- [ ] Event byte limit được kiểm sau serialize.
- [ ] Overflow summary không chứa raw payload.
- [ ] Exception message/cause chain được sanitize.
- [ ] Sampling không loại audit-critical events.
- [ ] Run summaries dùng aggregate counts.
- [ ] Evidence refs opaque và có ACL riêng.
- [ ] JUnit tests dùng sentinel giả, không dùng secret thật.
- [ ] Integration tests kiểm log backend/SDK/HTTP/tracing.
- [ ] Incident runbook có containment, rotation và deletion workflow.

### Câu hỏi tự kiểm tra

1. Vì sao log lớn gây chi phí và rủi ro bảo mật?
2. Drop khác truncate như thế nào?
3. Khi nào nên aggregate thay vì ghi danh sách item?
4. Vì sao preview của prompt vẫn là content?
5. Vì sao redaction phải chạy trước truncation?
6. Tại sao không nên cắt JSON bằng substring?
7. Size budget cần giới hạn những cấp nào?
8. Vì sao metadata cũng có thể nhạy cảm?
9. Redaction khác masking và pseudonymization ra sao?
10. Vì sao hash email trực tiếp không đủ an toàn?
11. Regex detector có những false positives/negatives nào?
12. Nested JSON cần được sanitize như thế nào?
13. Vì sao allowlist event DTO tốt hơn serialize object lớn?
14. Khi sanitizer lỗi, vì sao không được fallback raw?
15. Event vượt byte budget nên được xử lý thế nào?
16. Khi nào sampling có thể làm sai evaluation denominator?
17. Vì sao stack trace cần giới hạn và kiểm tra exception message?
18. Làm sao chứng minh log không chứa sentinel?
19. Evidence reference khác raw payload ra sao?
20. Khi secret đã vào log, cần containment những sink nào?

## 23. Tổng kết

Rút gọn log và che giá trị nhạy cảm là hai nhiệm vụ liên quan nhưng khác nhau. Rút gọn kiểm soát volume và kích thước; redaction bảo vệ dữ liệu. Truncate không thay redaction, sampling không thay privacy policy và hash không biến content thành dữ liệu vô hại.

Một pipeline an toàn bắt đầu bằng event DTO allowlist, loại bỏ prompt/response/context/tool payload không cần thiết, redact field nhạy cảm theo schema, chạy detector bổ sung cho free text, giới hạn string/array/object/depth, serialize JSON và kiểm max event bytes. Event vượt budget cần overflow summary hợp lệ; không cắt JSON bằng substring hoặc fallback sang raw object.

Với Spring AI, hãy thay danh sách chunks bằng counts/rank summaries, thay ChatRequest/ChatResponse bằng model metadata, thay tool arguments bằng validation/authorization/status và thay evaluator content bằng verdict/rubric/evidence refs. Dùng SLF4J/Logback cho structured events; kiểm thử sentinel qua logger, SDK, HTTP client và tracing exporter. Khi sanitizer hoặc policy lỗi, fail closed với content.

Kết hợp size budgets, allowlists, redaction, aggregation, sampling có kiểm soát và evidence references giúp log vẫn hữu ích để điều tra quality, latency, token usage và provider failures mà không biến operational log thành kho lưu trữ payload nhạy cảm.

### Tài liệu tham khảo

- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot — Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html#features.logging.structured)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [SLF4J — Manual](https://www.slf4j.org/manual.html)
- [Logback — Configuration](https://logback.qos.ch/manual/configuration.html)
- [Jackson — Databind](https://github.com/FasterXML/jackson-databind)
- [OpenTelemetry — Logs](https://opentelemetry.io/docs/specs/otel/logs/)
- [OpenTelemetry — Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
