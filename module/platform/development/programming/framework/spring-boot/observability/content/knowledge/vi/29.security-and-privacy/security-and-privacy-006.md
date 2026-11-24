# Mask response body

Trong chương **Security và privacy** của mô-đun **SPRING_BOOT_OBSERVABILITY**, mask response body là kỹ thuật loại bỏ hoặc thay thế dữ liệu nhạy cảm trong HTTP response trước khi nội dung được ghi vào logs, traces hoặc telemetry khác. Response có thể chứa access token, email, số tài khoản, địa chỉ, dữ liệu cá nhân, thông tin thanh toán hoặc kết quả nghiệp vụ nội bộ. Nếu ứng dụng ghi toàn bộ body để debug, dữ liệu có thể bị sao chép sang nhiều hệ thống observability có quyền truy cập và thời gian lưu khác nhau.

Cần xác định rõ response body được capture ở đâu. Spring Boot và Micrometer Observation không mặc định ghi toàn bộ body của mọi HTTP response vào metrics hoặc spans. Rủi ro thường phát sinh từ logging filters/interceptors tự viết, HTTP client debug logging, gateway/proxy logs, exception handlers hoặc instrumentation bổ sung. Masking phải được đặt ngay trước điểm ghi dữ liệu, đồng thời hạn chế capture ngay từ đầu.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích response body masking và rủi ro khi log body nguyên bản.
2. Xác định điểm capture response body trong Spring MVC, WebFlux, HTTP clients và gateway.
3. Phân biệt masking, redaction, truncation và omission.
4. Thiết kế allowlist dữ liệu được phép log.
5. Mask JSON fields theo cấu trúc thay vì thay chuỗi tùy tiện.
6. Xử lý response streaming, binary, multipart và nội dung lớn.
7. Hiểu tác động của response wrappers tới buffering, memory và response commitment.
8. Bảo đảm exception/error responses cũng tuân thủ masking policy.
9. Ngăn response body đi vào trace attributes, baggage và metric tags.
10. Kiểm thử bằng canary values và xây dựng quy trình xử lý sự cố rò rỉ.

## 2. Response body có thể làm lộ điều gì?

HTTP response thường chứa dữ liệu gửi tới client, nhưng điều đó không có nghĩa dữ liệu an toàn để lưu trong logs.

~~~json
{
  "customer": {
    "id": "C-9182",
    "email": "alice@example.com",
    "name": "Alice Nguyen"
  },
  "accessToken": "eyJhbGciOi...",
  "account": {
    "number": "001234567890",
    "balance": 1250000
  }
}
~~~

Nếu response này được ghi nguyên bản, logs có thể chứa:
- Access/refresh tokens, session identifiers và API keys.
- Email, tên, số điện thoại, địa chỉ và identifiers cá nhân.
- Account numbers, payment details và dữ liệu tài chính.
- Nội dung nghiệp vụ bí mật hoặc dữ liệu nội bộ.
- Error details, stack traces hoặc downstream payloads.
- Dữ liệu có thể kết hợp với những trường khác để nhận diện cá nhân.

Response body có thể được ghi ở application logs, reverse proxy, API gateway, ingress, service mesh, APM agent, HTTP client wire logs hoặc test/debug tooling. Kiểm tra toàn bộ đường đi của dữ liệu, không chỉ controller code.

## 3. Masking, redaction, truncation và omission

| Kỹ thuật | Cách hoạt động | Khi phù hợp |
| --- | --- | --- |
| Masking | Thay một phần/giá trị bằng ký tự hoặc nhãn cố định. | Giữ cấu trúc để debug, ví dụ email thành a***@example.com. |
| Redaction | Loại bỏ giá trị và thay bằng nhãn như [REDACTED]. | Secret hoặc dữ liệu không được phép lưu. |
| Truncation | Giới hạn độ dài nội dung. | Giảm log volume sau khi đã áp dụng policy. |
| Omission | Không capture hoặc không ghi body. | Streaming, binary, sensitive endpoints hoặc không có nhu cầu debug. |
| Allowlisting | Chỉ ghi các field được phê duyệt. | Response schema đa dạng hoặc mặc định có dữ liệu nhạy cảm. |

Truncation không phải masking: cắt 2 KB đầu response vẫn có thể giữ nguyên token hoặc email. Regex thay thế toàn văn bản cũng không bảo đảm an toàn khi JSON có nested objects, arrays, escaped strings hoặc field aliases. Với dữ liệu nhạy cảm, allowlist và omission thường là lựa chọn an toàn hơn.

## 4. Xác định nơi response body bị capture

Trước khi viết masking code, tìm tất cả nơi có thể đọc hoặc log response body:

- Spring MVC filters, HandlerInterceptors, response advice và exception handlers.
- WebFlux WebFilters, ExchangeFilterFunction và response decorators.
- RestTemplate/RestClient interceptors.
- WebClient filters và connector-level wire logging.
- Reverse proxy, API gateway, ingress và service mesh.
- OpenTelemetry Java Agent extensions hoặc APM agents.
- Logging appenders, structured logging processors và log shippers.

Micrometer HTTP observations thường ghi method, URI, status, outcome và duration. Chúng không cần response body để tạo các metrics cơ bản. Tránh thêm body vào span attributes chỉ để tiện debug.

~~~mermaid
flowchart TD
    Handler["Controller / downstream client"]
    Response["HTTP response body"]
    Capture["Optional capture point"]
    Policy["Response data classification"]
    Mask["Allowlist / structural masking"]
    Log["Safe structured log"]
    Trace["Trace attributes"]
    Store["Log / trace backend"]
    Handler --> Response --> Capture --> Policy --> Mask
    Mask --> Log --> Store
    Mask --> Trace --> Store
~~~

Nếu không có yêu cầu vận hành cụ thể, không capture body. Khi cần capture, chỉ tạo safe representation sau khi phân loại và masking.

## 5. Ưu tiên allowlist thay vì log toàn bộ response

Response schema có thể thay đổi theo version hoặc thêm field mới. Nếu dùng denylist, field mới có thể vô tình được log trước khi policy cập nhật. Allowlist chỉ chọn các trường thực sự cần thiết.

Ví dụ log representation an toàn:

~~~json
{
  "event": "http.response.completed",
  "route": "/orders/{orderId}",
  "status": 200,
  "response": {
    "result": "accepted",
    "itemCount": 3
  }
}
~~~

Không log toàn bộ object response bằng toString(), JSON serialization mặc định hoặc generated toString(). Những cách đó có thể đưa field nhạy cảm vào log mà người viết không nhận ra.

Policy nên xác định endpoint/route được capture, content types được xử lý, field được giữ/mask/redact, kích thước tối đa, response phải bỏ qua và vai trò được đọc logs.

## 6. Mask JSON theo cấu trúc

Nếu phải giữ một phần JSON để điều tra, parse body thành JSON tree và xử lý field theo tên/path. Tránh regex thay thế toàn văn bản.

| JSON path | Xử lý |
| --- | --- |
| $.accessToken | Redact toàn bộ. |
| $.refreshToken | Redact toàn bộ. |
| $.customer.email | Mask theo policy email. |
| $.customer.name | Omit hoặc mask. |
| $.account.number | Chỉ giữ suffix nếu policy cho phép. |
| $.account.balance | Omit hoặc phân nhóm, tùy mục đích. |
| $.result | Allowlist nếu là enum cố định. |
| $.itemCount | Allowlist nếu không nhạy cảm. |

Ví dụ minh họa Java dùng Jackson:

~~~java
@Component
class ResponseBodySanitizer {

    private final ObjectMapper objectMapper;

    ResponseBodySanitizer(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    JsonNode sanitize(byte[] body) throws IOException {
        JsonNode root = objectMapper.readTree(body);

        if (root instanceof ObjectNode object) {
            object.remove("accessToken");
            object.remove("refreshToken");

            JsonNode customerNode = object.get("customer");
            if (customerNode instanceof ObjectNode customer) {
                customer.put("email", "[REDACTED]");
                customer.remove("name");
            }

            JsonNode accountNode = object.get("account");
            if (accountNode instanceof ObjectNode account) {
                account.put("number", "[REDACTED]");
                account.remove("balance");
            }
        }
        return root;
    }
}
~~~

Đây là ví dụ tối giản cho schema đã biết. Ứng dụng thực tế cần xử lý nested arrays, nhiều object cùng schema, JSON primitives, malformed payload và content type. Nếu parse thất bại, lựa chọn an toàn là không ghi body hoặc ghi metadata không nhạy cảm; không fallback sang log raw body.

Một field token có thể xuất hiện ở nhiều cấp hoặc trong arrays. Policy cần xử lý recursive paths và aliases như access_token, refresh_token, authorization, cardNumber và tên tương đương. Tốt hơn nữa, dùng schema/DTO allowlist riêng cho logging thay vì tái sử dụng toàn bộ response DTO.

## 7. Response masking trong Spring MVC

Trong Servlet stack, response body thường được ghi bởi HttpMessageConverter sau khi controller trả về. Nếu cần capture body cho logging, có thể dùng ContentCachingResponseWrapper, nhưng wrapper này buffer nội dung response và yêu cầu copy body về response thật sau khi đọc.

~~~java
@Component
class SafeResponseLoggingFilter extends OncePerRequestFilter {

    private final ResponseBodySanitizer sanitizer;

    SafeResponseLoggingFilter(ResponseBodySanitizer sanitizer) {
        this.sanitizer = sanitizer;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        ContentCachingResponseWrapper wrapped =
                new ContentCachingResponseWrapper(response);
        try {
            filterChain.doFilter(request, wrapped);
            byte[] body = wrapped.getContentAsByteArray();

            if (shouldCapture(request, wrapped, body.length)) {
                JsonNode safe = sanitizer.sanitize(body);
                logSafeResponse(request, wrapped.getStatus(), safe);
            }
        } finally {
            wrapped.copyBodyToResponse();
        }
    }

    private boolean shouldCapture(
            HttpServletRequest request,
            ContentCachingResponseWrapper response,
            int size) {
        return size <= 16384
                && response.getContentType() != null
                && response.getContentType().contains("application/json");
    }

    private void logSafeResponse(
            HttpServletRequest request, int status, JsonNode safeBody) {
        // Ghi metadata và safeBody đã được sanitize.
    }
}
~~~

Ví dụ này minh họa lifecycle wrapper, không phải filter production hoàn chỉnh. Cần giới hạn route/content type/size, bỏ qua streaming và xử lý exception paths. Không ghi body nếu sanitizer ném lỗi. copyBodyToResponse() phải được gọi đúng lifecycle để client vẫn nhận nội dung response.

### Giới hạn của ContentCachingResponseWrapper

- Nội dung được buffer trong memory, làm tăng memory pressure.
- Response lớn có thể gây allocation cao hoặc OutOfMemoryError.
- Streaming/SSE có thể mất lợi ích streaming hoặc không phù hợp.
- File download/binary không nên parse như JSON.
- Response đã commit hoặc async dispatch cần lifecycle handling cẩn thận.
- Filter order ảnh hưởng nội dung wrapper nhìn thấy.
- Nếu quên copy body về response, client có thể nhận body rỗng.

Không dùng response caching wrapper cho mọi request production mà không đo memory và latency. Nếu chỉ cần debug một số endpoint, dùng route allowlist và giới hạn bytes.

## 8. WebFlux và reactive responses

WebFlux sử dụng reactive streams và DataBuffer; response body có thể được phát theo nhiều chunks, không nhất thiết có sẵn dưới dạng byte array hoàn chỉnh. Buffer có reference counting và cần được release đúng cách. Việc join toàn bộ DataBuffers để mask có thể làm mất streaming, tăng memory và tạo leak nếu quản lý sai.

Nguyên tắc:
- Không buffer SSE, streaming JSON, video, file hoặc response lớn chỉ để log.
- Chỉ decorate response khi thật sự cần và content type được allowlist.
- Nếu transform DataBuffers, giữ đúng ownership/release semantics.
- Không subscribe thêm vào publisher chỉ để log; điều đó có thể consume body hai lần hoặc lặp side effects.
- Khi không parse được hoặc buffer vượt giới hạn, bỏ body capture.

Với WebClient, response body thường chỉ được consume một lần. Nếu filter đọc body để log, phải rebuild response body để caller downstream vẫn đọc được. Cách này phức tạp và phụ thuộc connector; ưu tiên log metadata/status/route và để body nguyên vẹn.

## 9. Streaming, binary và multipart

Các loại response nên mặc định không capture:
- text/event-stream (Server-Sent Events).
- application/octet-stream.
- PDF, image, audio, video và archive.
- Multipart responses.
- Streaming JSON/NDJSON.
- Nội dung có kích thước không xác định hoặc rất lớn.

Với những response này, log metadata như content type, status, content length nếu có, route template và duration. Không log bytes đầu tiên như một cách mask, vì token hoặc PII có thể nằm ngay đầu body.

Nếu nghiệp vụ bắt buộc kiểm tra một phần nội dung, thiết kế metadata riêng có schema rõ và kiểm soát kích thước; không biến HTTP body thành log payload.

## 10. Error responses và exception handlers

Error response thường chứa dữ liệu nhạy cảm hơn response thành công: validation input, stack trace, database error, internal hostname hoặc downstream error body. Masking policy phải áp dụng cả đường đi thành công và thất bại.

Các điểm cần kiểm tra:
- @ExceptionHandler và @ControllerAdvice.
- Problem Details (ProblemDetail) và custom error DTOs.
- Servlet error dispatch và container error pages.
- WebFlux exception handlers.
- HTTP client error body khi downstream trả 4xx/5xx.
- Retry/dead-letter logs có serialize response payload không.

Không trả stack trace, SQL message hoặc downstream raw body cho client chỉ vì đã mask logs. Response sanitization và client-facing error handling là hai policy khác nhau. Chỉ trả error code/message công khai đã được thiết kế; log nội bộ dùng error category và correlation ID.

## 11. Không đưa response body vào spans, baggage hoặc metric tags

Distributed traces được chia sẻ qua nhiều service và backend. Response body không phải span attribute mặc định cần thiết cho HTTP instrumentation. Không thêm raw body vào span attributes, span events, baggage, metric tags, MDC hoặc structured log fields chưa sanitize.

Nếu cần trace một lỗi cụ thể, dùng HTTP method, route template, status, outcome, error type ổn định, correlation/request ID được quản lý an toàn và link tới log record đã mask theo access policy.

Metric tags phải low-cardinality. Response field như order ID, user email, token hoặc error detail vừa nhạy cảm vừa có thể tạo hàng triệu series.

## 12. Giới hạn kích thước và hiệu năng

Body capture có chi phí CPU, allocation, memory và latency. Xác định trước:
- Chỉ capture content types được allowlist.
- Giới hạn bytes tối đa được đọc và xử lý.
- Giới hạn độ sâu JSON và số phần tử arrays nếu parser hỗ trợ.
- Không nén/giải nén payload không cần thiết để log.
- Không parse body nhiều lần ở nhiều filters.
- Có sampling cho debug capture, nhưng sampling không thay thế masking.
- Khi quá giới hạn, ghi body_captured=false và metadata an toàn.

Ví dụ metadata khi bỏ qua body:

~~~json
{
  "event": "http.response.completed",
  "route": "/reports/{reportId}",
  "status": 200,
  "contentType": "application/octet-stream",
  "bodyCaptured": false,
  "bodyCaptureReason": "unsupported-content-type"
}
~~~

Đảm bảo bodyCaptureReason là tập giá trị cố định, không phải exception message tùy ý.

## 13. Kiểm thử response masking bằng canary values

Tạo các giá trị giả chỉ dùng trong test để dễ tìm rò rỉ:

~~~text
CANARY_ACCESS_TOKEN=canary-token-DO-NOT-LOG
CANARY_EMAIL=canary-user@example.invalid
CANARY_ACCOUNT=9999000011112222
~~~

Kiểm thử nên xác minh:
1. Response gửi tới client vẫn đúng nội dung theo API contract.
2. Log representation không chứa canary secrets/PII.
3. Field được allowlist vẫn có mặt nếu policy yêu cầu.
4. Nested objects và arrays được xử lý.
5. Malformed JSON dẫn tới omit body, không log raw.
6. Response lớn vượt limit được bỏ capture an toàn.
7. Binary/streaming/multipart không bị buffer để parse.
8. Exception/error response cũng được mask.
9. Không có canary values trong span attributes, baggage hoặc MDC.
10. copyBodyToResponse() được gọi kể cả khi sanitizer lỗi.

Ví dụ unit test cho sanitizer:

~~~java
@Test
void removesSecretsFromResponseJson() throws Exception {
    byte[] body = """
            {
              "accessToken": "canary-token-DO-NOT-LOG",
              "customer": {
                "email": "canary-user@example.invalid"
              }
            }
            """.getBytes(StandardCharsets.UTF_8);

    JsonNode safe = sanitizer.sanitize(body);
    String output = objectMapper.writeValueAsString(safe);

    assertThat(output).doesNotContain("canary-token-DO-NOT-LOG");
    assertThat(output).doesNotContain("canary-user@example.invalid");
}
~~~

Đây chỉ là test sanitizer; cần integration test ở filter/client logging boundary để xác minh không có component khác log raw body trước sanitizer.

## 14. Retention, access và incident response

Masking tại application là một lớp bảo vệ. Logs/traces đã export cần thêm RBAC theo vai trò và mục đích truy cập, encryption in transit/at rest, retention phù hợp, audit truy vấn/export, giới hạn download/sharing và quy trình xóa/contain dữ liệu khi phát hiện rò rỉ.

Nếu phát hiện response body nhạy cảm đã vào logs:
1. Xác định field/value, service, thời gian và các sinks nhận dữ liệu.
2. Ngăn capture tiếp tục bằng config/code change đã kiểm soát.
3. Hạn chế quyền truy cập và dừng export/forwarding nếu phù hợp.
4. Xác định retention/deletion capabilities của log/trace backend.
5. Thực hiện incident process và đánh giá nghĩa vụ thông báo theo policy.
6. Xoay vòng token/credential nếu secret bị lộ.
7. Kiểm thử canary values sau fix và rà soát services khác có cùng logging pattern.

Không cho rằng xóa log ở một backend đồng nghĩa dữ liệu đã biến mất khỏi replicas, archive, index, backup hoặc downstream SIEM.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Client nhận response body rỗng | Wrapper không copy body về response thật. | Kiểm tra copyBodyToResponse() trong finally. |
| Response lớn làm memory tăng | ContentCachingResponseWrapper buffer quá nhiều. | Giới hạn capture size/route/content type hoặc bỏ capture. |
| JSON log vẫn có token | Field alias/nested path chưa được policy xử lý. | Dùng structural sanitizer và test nested arrays. |
| Masking chỉ áp dụng response 200 | Error handler/container dispatch đi qua path khác. | Kiểm tra exception advice và error dispatch. |
| WebFlux body bị consume hai lần | Filter subscribe/consume publisher riêng để log. | Decorate/rebuild đúng lifecycle hoặc bỏ body capture. |
| SSE/streaming bị chậm hoặc ngừng | Response bị buffer toàn bộ. | Bỏ capture với streaming content types. |
| SQL/downstream error xuất hiện trong body log | Exception handler serialize raw exception/downstream payload. | Dùng safe error DTO và sanitize tại boundary. |
| Span có response body | Custom instrumentation hoặc agent capture payload. | Kiểm tra span processors, agent config và custom attributes. |
| Body bị cắt nhưng secret vẫn lộ | Truncation được dùng thay masking. | Mask trước truncation hoặc omit body. |
| Test sanitizer pass nhưng log vẫn lộ | Component khác log raw body trước sanitizer. | Tìm filters, wire logs, gateway và agent capture. |

## 16. Runbook: response body bị ghi vào telemetry

1. Xác định service, route, response content type và log/trace sink bị ảnh hưởng.
2. Tìm nguồn capture: filter, interceptor, HTTP client, gateway, agent hoặc wire logger.
3. Xác định data classification và canary/secret values đã bị ghi.
4. Tắt body capture hoặc thu hẹp allowlist tại nguồn theo quy trình change.
5. Áp dụng structural masking trước khi serialize log/trace event.
6. Bỏ capture streaming, binary, multipart và body vượt size limit.
7. Kiểm tra error responses và exception handling path.
8. Rà soát span attributes, baggage, MDC và metric tags.
9. Kiểm thử bằng canary values ở application và gateway boundaries.
10. Xác định log/trace indexes, archives, backups và quyền truy cập chịu ảnh hưởng.
11. Xoay vòng credentials nếu access token/API key bị lộ.
12. Ghi incident findings và bổ sung regression tests/policy.

## 17. Bài tập tự kiểm tra

### Bài 1 — Truncation

Một filter chỉ log 1 KB đầu response. Có thể coi đây là masking không?

**Đáp án:** Không. Token, email hoặc account data có thể nằm trong phần đầu. Truncation chỉ giới hạn độ dài; phải mask/redact theo policy hoặc omit body.

### Bài 2 — Allowlist hay denylist?

Response schema thay đổi thường xuyên và có thể thêm field nhạy cảm. Nên chọn chiến lược nào?

**Đáp án:** Allowlist các field được phép log. Field mới mặc định không xuất hiện trong logs, giảm nguy cơ vô tình ghi dữ liệu.

### Bài 3 — Streaming response

Có nên dùng ContentCachingResponseWrapper để parse và mask toàn bộ SSE response?

**Đáp án:** Không. SSE là streaming; buffering toàn bộ có thể phá streaming, tăng memory và latency. Log metadata an toàn thay vì body.

### Bài 4 — WebFlux

Một WebClient filter đọc body để log, sau đó service nhận body rỗng. Vì sao?

**Đáp án:** Reactive response body thường chỉ được consume một lần. Filter đã consume publisher mà không rebuild body cho downstream.

### Bài 5 — Error response

ControllerAdvice tạo ProblemDetail từ exception và log object đó. Cần kiểm tra gì?

**Đáp án:** Đảm bảo properties/detail không chứa raw exception message, SQL, host hoặc downstream payload; dùng safe error code và áp dụng masking policy cho error path.

### Bài 6 — Canary test

Sanitizer unit test không còn canary token, nhưng production logs vẫn có token. Nguyên nhân có thể?

**Đáp án:** Một filter, gateway, HTTP client wire logger hoặc agent khác ghi raw body trước/sau sanitizer. Cần kiểm tra toàn bộ capture points và export pipeline.

## 18. Checklist triển khai

- [ ] Đã lập danh sách mọi điểm capture response body.
- [ ] Không capture body nếu không có nhu cầu vận hành rõ.
- [ ] Có allowlist route và content type được phép xử lý.
- [ ] Dùng allowlist field/schema cho safe log representation.
- [ ] JSON được mask theo cấu trúc, bao gồm nested objects và arrays.
- [ ] Secret, token, PII, payment data và account identifiers được redacted/omitted.
- [ ] Malformed/unsupported payload dẫn tới omit, không fallback raw body.
- [ ] Streaming, binary, multipart và response lớn không bị buffer tùy tiện.
- [ ] Response wrappers luôn preserve body và lifecycle đúng.
- [ ] Error responses/exception handlers áp dụng cùng privacy policy.
- [ ] Response body không được đưa vào span attributes, baggage hoặc metric tags.
- [ ] Capture size, parser depth, CPU và memory overhead có giới hạn.
- [ ] Canary tests xác minh không rò dữ liệu tại log/trace boundary.
- [ ] Logs/traces có RBAC, encryption, retention và audit phù hợp.
- [ ] Có incident runbook và credential rotation khi secret bị lộ.
- [ ] Gateway, agent và downstream telemetry sinks đã được rà soát.

**Ghi nhớ:** Mask response body bắt đầu bằng quyết định có cần capture hay không. Nếu cần, chỉ giữ field được allowlist, mask JSON theo cấu trúc và bỏ qua streaming/binary hoặc payload không hỗ trợ. Đặt sanitization trước mọi log/trace export, bảo toàn response lifecycle, kiểm thử bằng canary values và kiểm soát quyền truy cập/retention ở backend. Metrics và traces cơ bản thường không cần lưu response body để cung cấp observability hữu ích.
