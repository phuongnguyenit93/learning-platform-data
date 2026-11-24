# PII trong logs của ứng dụng Spring Boot

Trong chương **Security và privacy** của module **SPRING_BOOT_OBSERVABILITY**, PII (Personally Identifiable Information) là thông tin có thể nhận diện một cá nhân trực tiếp hoặc khi kết hợp với dữ liệu khác. Logs giúp điều tra lỗi và hiểu hành vi ứng dụng, nhưng nếu ghi quá nhiều dữ liệu, log pipeline có thể trở thành nơi tập trung email, số điện thoại, địa chỉ, định danh tài khoản, token hoặc nội dung request nhạy cảm.

Mục tiêu của logging an toàn là giữ đủ ngữ cảnh kỹ thuật để vận hành và điều tra, đồng thời giảm dữ liệu cá nhân được thu thập, hiển thị, lưu trữ và chia sẻ. Cách làm hiệu quả bắt đầu từ data minimization và allowlist fields; masking/redaction là lớp bảo vệ bổ sung khi dữ liệu nhạy cảm không thể tránh hoàn toàn. Không nên dựa vào một regex duy nhất để làm sạch mọi log message.

Trong **SPRING_BOOT_OBSERVABILITY**, logs là một tín hiệu liên kết với metrics và distributed tracing. Trace ID, Span ID và event name thường đủ để tìm đúng request trong trace backend; raw payload, credentials hoặc PII không cần được sao chép vào mọi log line. Bài này trình bày cách phân loại PII, thiết kế structured logging, bảo vệ request/response và exception, cấu hình Spring Boot/Logback, kiểm soát access/retention và kiểm thử rò rỉ dữ liệu.

## 1. PII là gì trong bối cảnh logging?

PII là dữ liệu có thể nhận diện hoặc liên kết tới một cá nhân. Phạm vi cụ thể phụ thuộc luật, hợp đồng, ngành nghề và chính sách tổ chức. Một field không có vẻ nhạy cảm khi đứng riêng vẫn có thể trở thành PII khi kết hợp với field khác.

| Nhóm dữ liệu | Ví dụ | Rủi ro khi ghi log |
| --- | --- | --- |
| Định danh trực tiếp | Họ tên, email, số điện thoại | Tìm và nhận diện cá nhân |
| Định danh chính phủ | Số căn cước, hộ chiếu, mã số thuế | Rủi ro cao khi lộ hoặc lưu quá lâu |
| Địa chỉ/vị trí | Địa chỉ nhà, tọa độ, lịch sử vị trí | Tiết lộ nơi ở hoặc thói quen di chuyển |
| Tài khoản | Username, customer ID, account number | Liên kết hoạt động với một cá nhân |
| Tài chính | Số thẻ, tài khoản ngân hàng, giao dịch | Gian lận và tổn thất tài chính |
| Dữ liệu xác thực | Password, access token, session cookie | Chiếm quyền truy cập |
| Dữ liệu sức khỏe | Hồ sơ, chẩn đoán, kết quả xét nghiệm | Dữ liệu nhạy cảm đặc biệt |
| Nội dung tự do | Comment, search term, request body | Có thể chứa bất kỳ thông tin cá nhân nào |

Không phải mọi identifier đều được phân loại giống nhau trong mọi chính sách. Tuy vậy, request ID, user ID, tenant ID hoặc IP address cũng có thể liên kết đến người dùng và có thể có cardinality cao. Cần đánh giá cả privacy và metric cardinality trước khi đưa chúng vào logs/traces/metrics.

### Dữ liệu nhạy cảm không chỉ nằm trong body

PII và secrets có thể xuất hiện ở URL path và query parameters; HTTP headers như Authorization, Cookie, Referer hoặc custom headers; JSON/XML request và response bodies; exception message và stack context; SQL parameters, ORM debug output và database error details; JMS message properties/payload; MDC, tracing baggage và custom span attributes; tên file, object storage path và tên queue được tạo từ dữ liệu người dùng.

Vì vậy, “không log request body” vẫn chưa đủ nếu access token nằm trong header hoặc email nằm trong query string.

## 2. Data minimization là lớp bảo vệ đầu tiên

Nguyên tắc quan trọng nhất là chỉ ghi những field thực sự cần cho mục đích vận hành. Nếu một field không giúp trả lời câu hỏi debug/monitoring, đừng thu thập nó.

Thay vì log toàn bộ request:

```json
{
  "event": "customer.update",
  "requestBody": {
    "name": "Nguyen Van A",
    "email": "person@example.com",
    "phone": "+84...",
    "address": "...",
    "password": "..."
  }
}
```

Hãy ghi event và kết quả tối thiểu:

```json
{
  "event": "customer.update",
  "operation": "update-profile",
  "result": "success",
  "http.route": "/customers/{customerId}",
  "http.status_code": 200,
  "duration_ms": 42
}
```

Ví dụ thứ hai vẫn hỗ trợ phân tích route, kết quả và latency mà không sao chép profile hoặc password vào log. Nếu cần phân biệt một workflow cụ thể, dùng correlation/trace context hoặc identifier nội bộ đã được phê duyệt và kiểm soát quyền truy cập.

Trước khi thêm field mới, trả lời ba câu hỏi:

1. Field này phục vụ use case vận hành hoặc security nào?
2. Có thể đạt mục tiêu bằng giá trị tổng hợp, category hoặc identifier ít nhạy cảm hơn không?
3. Ai cần truy cập field, lưu trong bao lâu và có thể xóa/ẩn danh khi nào?

## 3. Phân biệt masking, redaction, hashing và tokenization

| Kỹ thuật | Cách hoạt động | Khi phù hợp | Giới hạn |
| --- | --- | --- | --- |
| Masking | Ẩn một phần giá trị | Hiển thị hỗ trợ, ví dụ email đã che | Vẫn có thể nhận diện nếu còn quá nhiều ký tự |
| Redaction | Loại bỏ hoặc thay bằng placeholder | Token, password, số thẻ, nội dung không cần giữ | Không thể phục hồi giá trị gốc |
| Hashing | Tạo digest một chiều | So sánh/nhóm giá trị nếu có lý do rõ ràng | Giá trị ít entropy có thể bị dò; hash vẫn có thể là dữ liệu liên kết |
| Tokenization | Thay giá trị bằng token tham chiếu | Cần liên kết có kiểm soát với hệ thống vault | Token vẫn có thể nhạy cảm; vault cần bảo vệ |
| Truncation | Chỉ giữ một phần không định danh | Chẩn đoán format hoặc phiên bản | Có thể vẫn để lộ dữ liệu |

Không dùng masking như lời biện minh để log mọi field. Ví dụ email chỉ che một phần vẫn có thể nhận diện người dùng. Hash email không tự động làm dữ liệu trở thành anonymous; nếu có thể liên kết hoặc dò dictionary thì vẫn có rủi ro privacy.

Với password, access token, refresh token, session cookie và private key, lựa chọn đúng thường là không ghi hoặc redaction hoàn toàn, không phải masking một phần.

## 4. Structured logging và allowlist fields

Structured logging ghi event dưới dạng các field có tên rõ ràng. Nó giúp backend filter và query theo service, operation, outcome, route template và trace context.

Ví dụ log event an toàn hơn:

```json
{
  "timestamp": "2026-11-22T10:15:30Z",
  "level": "INFO",
  "service.name": "customer-service",
  "event.name": "customer.profile.updated",
  "http.request.method": "PATCH",
  "http.route": "/customers/{customerId}",
  "http.response.status_code": 200,
  "duration_ms": 42,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7"
}
```

Field set được chọn trước và không bao gồm raw URL, payload, Authorization header hoặc email. Các tên field ở đây là ví dụ; hệ thống nên thống nhất schema và semantic conventions đang sử dụng.

Allowlist thường an toàn hơn denylist. Denylist chỉ che những field đã biết; payload mới hoặc custom header mới có thể lọt qua. Allowlist chỉ xuất các field đã duyệt, do đó dữ liệu mới mặc định không được log.

Một event schema nên xác định tên event ổn định; service/deployment identity; operation hoặc route template; outcome/status và duration; error type đã chuẩn hóa khi cần; Trace ID/Span ID nếu có; các business identifiers đã được privacy/security review.

## 5. Không log toàn bộ HTTP request/response

Các cách debug tiện lợi như serialize toàn bộ request object, log body hoặc bật wire logging có thể ghi lại PII và secrets. Đặc biệt, request/response bodies có thể chứa dữ liệu không dự đoán trước.

Tránh các mẫu:

```java
log.info("Request: {}", objectMapper.writeValueAsString(request));
log.debug("Authorization: {}", request.getHeader("Authorization"));
log.info("URL: {}", request.getRequestURL() + "?" + request.getQueryString());
```

Thay bằng log có field được chọn:

```java
log.info(
        "Customer profile update completed: route={}, status={}, durationMs={}",
        "/customers/{customerId}",
        200,
        durationMs);
```

Ví dụ dùng parameterized logging để tránh dựng chuỗi không cần thiết. Trong hệ thống thực tế, structured logger/JSON encoder nên ghi field riêng thay vì ghép chuỗi tự do.

Nếu cần debug payload trong môi trường cô lập, dùng synthetic data hoặc bản sao đã được sanitize. Không bật body logging production trong thời gian dài để điều tra sự cố nếu chưa có cơ chế lọc, quyền truy cập và retention phù hợp.

## 6. Bảo vệ HTTP headers và URL

| Header | Vì sao nhạy cảm | Xử lý |
| --- | --- | --- |
| Authorization | Bearer/basic credentials | Redact hoàn toàn |
| Cookie / Set-Cookie | Session IDs và auth state | Redact hoàn toàn |
| Proxy-Authorization | Credentials tới proxy | Redact hoàn toàn |
| X-Api-Key | API key | Redact hoàn toàn |
| Referer | Có thể chứa query/path cá nhân | Bỏ hoặc chuẩn hóa |
| X-Forwarded-For | IP address chain | Chỉ giữ nếu có mục đích và policy rõ |
| Custom tenant/user headers | Có thể nhận diện cá nhân/tổ chức | Allowlist hoặc pseudonymize theo policy |

URL cần được chuẩn hóa trước khi log. Dùng route template như /customers/{customerId}, bỏ query parameters trừ khi có allowlist field an toàn. Không chỉ xóa query string rồi giữ raw path nếu path variable chứa email, phone hoặc account ID.

Nếu cần phân tích một query option, ghi category hoặc boolean như include_history=true sau khi chuẩn hóa, thay vì ghi nguyên query string.

## 7. Redaction trong Logback

Spring Boot thường dùng Logback làm logging backend mặc định khi dùng starter logging. Có thể dùng encoder/layout hoặc filter tùy nhu cầu để kiểm soát output. Một phương án bền vững là chỉ truyền các field đã sanitize vào logger; regex trên toàn bộ rendered message nên là lớp bảo vệ bổ sung, không phải lớp chính.

Ví dụ utility che email cho một use case hiển thị có kiểm soát:

```java
final class LogSanitizer {
    private LogSanitizer() {
    }

    static String maskEmail(String email) {
        if (email == null || email.isBlank()) {
            return "[redacted]";
        }
        int at = email.indexOf('@');
        if (at <= 1) {
            return "[redacted]";
        }
        return email.charAt(0) + "***" + email.substring(at);
    }
}
```

Masking email chỉ là ví dụ và không chứng minh email đã được anonymize. Trong nhiều log event, tốt nhất không ghi email. Nếu business/security use case thực sự cần liên kết user events, dùng internal subject reference đã được phê duyệt hoặc tokenization service.

Không viết sanitizer chỉ xử lý một vài tên field rồi cho phép serialize mọi object. Cần thiết kế allowlist schema trước khi serialize.

### Vì sao regex filter dễ thất bại?

Regex trên rendered log line có thể bỏ sót JSON nested fields hoặc escape sequences; URL encoding/base64; multiline exception messages; header names viết hoa/thường khác nhau; PII trong exception cause sâu hơn; payload định dạng XML, protobuf hoặc binary-to-text.

Nếu bắt buộc phải redaction sau khi serialize, dùng parser theo format và test với các biến thể dữ liệu. Không giả định một regex có thể hiểu mọi cấu trúc.

## 8. Exception messages và stack traces

Stack trace hữu ích để tìm vị trí lỗi, nhưng exception message có thể chứa dữ liệu người dùng hoặc secrets. Ví dụ lỗi validation có thể đưa nguyên giá trị email, số tài khoản hoặc request parameter vào message.

Thực hành:

- Ghi exception class/type đã chuẩn hóa.
- Giữ stack trace khi cần và đã đánh giá nơi lưu/access.
- Không đưa raw exception message vào metric tags hoặc event name.
- Sanitize message ở boundary nếu message có thể chứa dữ liệu nhạy cảm.
- Tránh log cùng một exception nhiều lần ở controller, service và global handler nếu không tăng thêm ngữ cảnh.
- Không log token hoặc request object trong error handler.

Ví dụ:

```java
catch (PaymentGatewayException ex) {
    log.error(
            "Payment authorization failed: dependency={}, errorType={}",
            "payment-gateway",
            ex.getClass().getSimpleName());
    throw ex;
}
```

Nếu cần stack trace, truyền exception như tham số cuối theo logging API đã cấu hình, sau khi xác định exception message/cause không chứa PII hoặc secrets. Khi không thể bảo đảm, tạo exception type/event đã sanitize và giữ chi tiết ở hệ thống được bảo vệ hơn.

## 9. MDC, Trace ID và baggage

MDC thường được dùng để đưa Trace ID, Span ID hoặc correlation fields vào mỗi log line. Đây là cách hữu ích liên kết logs với distributed traces mà không cần ghi payload.

Ví dụ JSON log:

```json
{
  "message": "Inventory reservation completed",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "service.name": "orders-service"
}
```

Trace ID và Span ID thường không phải PII trực tiếp, nhưng vẫn là identifiers có thể liên kết hoạt động. Cần kiểm soát quyền truy cập, retention và khả năng truy vấn theo ID. Không dùng chúng làm metric tags vì cardinality cao.

Tracing baggage là context key-value có thể được propagation qua service boundary. Không đưa email, phone, account number, access token hoặc dữ liệu nhạy cảm vào baggage. Baggage có thể được gửi qua nhiều service và exporter, làm phạm vi lộ dữ liệu rộng hơn dự kiến.

Chỉ propagate keys có allowlist, kích thước nhỏ, giá trị hữu hạn hoặc đã được privacy review. Trace attributes cũng cần redaction/allowlist; tracing không phải vùng lưu trữ an toàn mặc định.

## 10. SQL, JDBC và database logs

SQL logging có thể vô tình ghi literal values hoặc bind parameters. Ví dụ query có email hoặc account number trong WHERE clause. ORM debug logging và JDBC proxy tools có thể in SQL đã thay parameter hoặc parameter values.

Không bật SQL bind parameter logging production nếu chưa đánh giá dữ liệu. Ưu tiên ghi operation/repository name hoặc query fingerprint đã chuẩn hóa; database duration và outcome; dùng DB slow query tooling có quyền truy cập và retention riêng; redact parameters nhạy cảm trước khi log nếu thật sự cần; tránh log connection string có username/password.

Database observability nên liên kết query duration với trace/span và datasource metrics. Không cần ghi đầy đủ SQL parameter values vào application logs để biết query nào chậm.

## 11. JMS và message payload

Message payload có thể mang dữ liệu khách hàng, thanh toán hoặc thông tin xác thực. Không log toàn bộ JMS message khi consumer thất bại. Ghi destination đã chuẩn hóa, message type, schema version, outcome và Trace ID nếu phù hợp.

Không đưa JMS Message ID, Correlation ID, customer ID hoặc order ID thành metric tags. Các identifiers này có thể được ghi trong secured logs khi có mục đích điều tra và retention được phê duyệt; message body cần allowlist/redaction trước khi ghi.

Nếu cần tái xử lý message lỗi, dùng DLQ/replay mechanism có access control và audit. Logs chỉ nên giữ metadata đủ để tìm message trong broker theo quy trình được kiểm soát, không sao chép payload nhạy cảm vào mọi sink.

## 12. Bảo vệ log pipeline và storage

| Lớp | Kiểm soát cần có |
| --- | --- |
| Application | Data minimization, allowlist, redaction |
| Agent/collector | TLS, access credentials, tránh debug dump payload |
| Transport | Authentication, encryption, bounded buffering |
| Storage | Encryption at rest, tenant isolation, retention |
| Query/UI | RBAC, least privilege, audit truy vấn/export |
| Export/download | Phê duyệt, watermark/audit nếu policy yêu cầu |
| Deletion | TTL, legal hold và deletion workflow rõ ràng |
| Backup/archive | Cùng controls và retention với dữ liệu gốc |

Không gửi logs chứa PII sang SaaS/third-party backend trước khi xác định data residency, processing agreement, access scope và retention. Việc log được tạo trong private network không có nghĩa nó tự động an toàn khi được forward.

## 13. Retention và quyền truy cập

Logs nên được lưu trong khoảng thời gian đủ cho vận hành, security investigation và yêu cầu pháp lý đã xác định. Không đặt retention vô hạn chỉ vì storage rẻ.

Một policy có thể phân lớp operational logs, security/audit logs, restricted logs và archive; mỗi lớp cần retention, quyền truy cập và quy trình xóa phù hợp. Không áp dụng một con số retention cho mọi tổ chức. Xác định mục đích, loại dữ liệu, nghĩa vụ pháp lý, hợp đồng và quy trình xóa. Khi không còn mục đích hợp lệ, xóa hoặc anonymize theo policy; backup/archive cũng cần được tính tới.

Quyền truy cập nên theo least privilege. Developer không nhất thiết cần quyền đọc mọi log production. Dùng role theo nhiệm vụ, audit search/export, và hạn chế tải file lớn hoặc truy vấn theo identifier cá nhân.

## 14. Kiểm thử để ngăn PII lọt vào logs

Logging policy cần được kiểm thử tự động như một yêu cầu bảo mật:

1. Tạo request test với marker PII giả, ví dụ email pii-test-482@example.invalid.
2. Gửi Authorization header giả có marker SECRET_TEST_TOKEN.
3. Gửi query string và body chứa các marker nhạy cảm giả.
4. Kích hoạt validation exception có message chứa marker.
5. Capture logs bằng test appender hoặc output stream.
6. Assert marker không xuất hiện trong log output.
7. Assert các field vận hành cần thiết như event, route template, outcome, trace ID vẫn có.
8. Kiểm tra exception cause, nested fields và multiline logs.
9. Kiểm tra MDC/baggage không đưa field nhạy cảm vào output.
10. Chạy test cho cả HTTP, JDBC và JMS logging paths nếu ứng dụng sử dụng chúng.

Ví dụ kiểm tra đơn giản với JUnit:

```java
@Test
void shouldNotWriteSensitiveMarkersToLogs() {
    String logs = captureLogs(() -> customerController.update(
            requestWithEmail("pii-test-482@example.invalid")));

    assertThat(logs).doesNotContain("pii-test-482@example.invalid");
    assertThat(logs).doesNotContain("SECRET_TEST_TOKEN");
    assertThat(logs).contains("customer.profile.updated");
}
```

Đây là pseudocode; cách capture phụ thuộc Logback test appender và test framework. Dùng dữ liệu giả, không dùng thông tin khách hàng thật trong test fixtures. Assert cả nội dung và schema, vì việc xóa toàn bộ log cũng làm test “không chứa PII” nhưng phá khả năng vận hành.

### Kiểm tra logging configuration

Review các logger levels và package cụ thể: HTTP client wire logging; Spring Web request/response logging; Hibernate SQL và bind parameter logging; JDBC proxy logging; JMS provider/client debug logging; Security/authentication debug logging; exception handler và request logging filters.

Một cấu hình DEBUG tạm thời có thể thay đổi lượng dữ liệu được ghi đáng kể. Quy trình bật debug production cần người phê duyệt, phạm vi logger hẹp, thời hạn tự tắt và kiểm tra output trước khi áp dụng rộng.

## 15. Ứng phó khi phát hiện PII đã bị ghi

Nếu phát hiện PII trong log sink:

1. Xác định field, event, service, thời gian và các sink đã nhận dữ liệu.
2. Ngăn nguồn tiếp tục ghi dữ liệu bằng allowlist/redaction hoặc tắt logger cụ thể theo quy trình.
3. Hạn chế quyền truy cập và export tới các index/object chứa dữ liệu.
4. Xác định retention, replica, archive và backup bị ảnh hưởng.
5. Thực hiện deletion/containment theo incident response và legal/privacy policy.
6. Đánh giá liệu có cần thông báo theo quy định hoặc hợp đồng.
7. Thêm regression tests và kiểm tra pipeline để ngăn tái diễn.

Không tự ý xóa audit/security evidence trước khi phối hợp với incident owner và policy lưu giữ. Cần cân bằng containment, nghĩa vụ bảo toàn chứng cứ và quyền của chủ thể dữ liệu.

## 16. Bài tập tình huống

Một team bật DEBUG cho HTTP client và Logback trong 30 phút để điều tra lỗi thanh toán. Log backend bắt đầu chứa Authorization header, email trong query string và response body có địa chỉ khách hàng. Log được forward tới một nền tảng tập trung mà nhiều developer có quyền truy cập.

**Câu hỏi:**

1. Những nguồn PII/secrets nào đang bị ghi?
2. Vì sao chỉ thêm regex che email chưa đủ?
3. Cần thay đổi logging strategy nào để vẫn điều tra được lỗi?
4. Những ai cần được thông báo/đánh giá khi log đã được forward?
5. Cần test nào để tránh sự cố lặp lại?

**Gợi ý phân tích:**

- Authorization header là secret cần redaction hoàn toàn; query string và response body có PII; wire logging có thể ghi nhiều dữ liệu hơn dự kiến.
- Regex có thể bỏ sót URL encoding, JSON nested fields, multiline exception hoặc format khác. Allowlist event fields và tắt body/header logging là lớp chính.
- Giữ event, route template, status, duration, error type, Trace ID/Span ID và dependency name đã chuẩn hóa. Dùng trace backend để xem flow và logs có kiểm soát để điều tra.
- Incident owner, security/privacy team, data owner và log platform owner đánh giá phạm vi, access, retention, deletion và nghĩa vụ thông báo theo policy.
- Dùng synthetic PII/token markers trong integration tests, kiểm tra appender output, nested exception, headers, query, body, MDC và các logger DEBUG.

### Checklist hoàn thành

| Nội dung | Có thể giải thích/kiểm tra |
| --- | --- |
| PII | Nhận diện dữ liệu trực tiếp và dữ liệu có thể liên kết |
| Data minimization | Chỉ ghi fields phục vụ mục đích rõ ràng |
| Allowlist | Chọn schema log an toàn thay vì serialize toàn object |
| Masking/redaction | Chọn kỹ thuật phù hợp; secrets cần loại bỏ hoàn toàn |
| HTTP | Không log raw body, auth headers, cookies hoặc query tự do |
| Exceptions | Kiểm soát message, cause và stack context |
| MDC/baggage | Giữ Trace ID hữu ích, không propagate PII |
| JDBC/JMS | Tránh bind parameters và message payload nhạy cảm |
| Storage/access | Encryption, RBAC, audit, retention và deletion |
| Testing | Dùng marker giả để xác nhận PII không xuất hiện |
| Incident response | Contain, scope, preserve evidence và xử lý theo policy |

**Ghi nhớ:** Logs là một bản sao dữ liệu có thể được forward, index, tìm kiếm, export và lưu trong backup. Bắt đầu bằng data minimization và allowlist fields; dùng redaction cho secrets và dữ liệu không thể tránh, nhưng không dựa vào regex như lớp bảo vệ duy nhất. Kiểm soát headers, URL, exception, SQL, JMS payload, MDC và tracing baggage. Bảo vệ log pipeline bằng encryption, least-privilege access, audit và retention rõ ràng; kiểm thử bằng synthetic PII markers để bảo đảm log vẫn hữu ích mà không làm lộ dữ liệu cá nhân.
