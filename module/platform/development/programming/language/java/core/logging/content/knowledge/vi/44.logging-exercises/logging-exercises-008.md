# Thêm masking dữ liệu trong Java Logging — Dự án thực hành bảo vệ thông tin nhạy cảm

## 1. Mục tiêu của bài thực hành

Trong một hệ thống Java, log giúp điều tra lỗi, giám sát hoạt động và truy vết một giao dịch. Tuy nhiên, các dòng log có thể vô tình chứa **mật khẩu, access token, header Authorization, cookie, email, số điện thoại, địa chỉ, mã định danh cá nhân, thông tin thanh toán hoặc nội dung request**. Khi đã được gửi tới file, sidecar, collector và hệ thống lưu trữ tập trung, phạm vi người có thể tiếp cận dữ liệu thường lớn hơn phạm vi của ứng dụng ban đầu.

**Masking dữ liệu trong logging** là việc chủ động **ẩn, thay thế, rút gọn hoặc loại bỏ** các phần nhạy cảm khỏi bản ghi trước khi dữ liệu tới những nơi không cần biết giá trị gốc.

Bài thực hành tập trung vào **thiết kế và tích hợp một cơ chế tạo log an toàn trong Java**: có quy tắc theo trường, có xử lý mặc định an toàn, có ví dụ chạy độc lập trên Java 17, và có phương pháp kiểm thử tại cả ứng dụng lẫn pipeline thu thập.

Sau bài học, bạn có thể:

1. Phân loại các trường dữ liệu cần bỏ, che toàn bộ, che một phần hoặc được phép ghi.
2. Phân biệt **masking, redaction, tokenization, hashing/HMAC và encryption**.
3. Tránh anti-pattern `log.info("request={}", request)` hoặc `log.error("{}", exception.getMessage())`.
4. Tạo **một event log có cấu trúc**, giữ operation/correlation/outcome hữu ích mà không lộ dữ liệu.
5. Viết mã Java 17 minh họa **fail-closed khi gặp field không nằm trong allowlist**.
6. Tích hợp chính sách vào SLF4J/Logback, HTTP filters, message consumers, MDC và exception logging.
7. Viết test xác minh **secret không xuất hiện trong file/JSONL/collector**, kể cả với input độc hại.
8. Biết rõ giới hạn: masking không thay thế authentication, authorization, encryption at rest, audit integrity hoặc retention policy.

**Nguyên tắc quan trọng nhất:** nếu một trường **không cần thiết cho mục đích logging**, tốt nhất **không tạo/ghi trường đó**, thay vì ghi raw rồi hy vọng một regex ở collector sẽ xóa hết.

## 2. Nhận diện vấn đề bằng ví dụ trước và sau

Giả sử API cập nhật hồ sơ nhận JSON sau:

```json
{
  "email": "alice@example.com",
  "phone": "+84901234567",
  "password": "not-for-logs",
  "accessToken": "eyJhbGciOi..."
}
```

**Anti-pattern** trong Java:

```java
// Mã minh họa cần tránh: có thể gọi toString() trên toàn bộ DTO.
log.info("Update profile: {}", request);

// Mã minh họa cần tránh: đưa credential thẳng vào log.
log.debug("Authorization header: {}", authorizationHeader);

// Mã minh họa cần tránh: exception message có thể chứa request/SQL/token.
log.error("Update failed: {}", failure.getMessage());
```

Nếu DTO có `toString()` sinh tự động từ toàn bộ fields, logger có thể in cả password/token. Dù DEBUG bị tắt hôm nay, một thay đổi runtime level ngày mai có thể khiến bí mật lộ ra. `request.toString()` cũng có thể thay đổi theo code generation, Lombok hoặc một thư viện, nên không phải hàng rào an toàn.

Một bản ghi tốt hơn:

```json
{
  "event": "profile.update.result",
  "requestId": "req-101",
  "outcome": "SUCCEEDED",
  "email": "[MASKED]",
  "phone": "[MASKED]",
  "authorization": "[REDACTED]",
  "durationMs": 24
}
```

Trong nhiều trường hợp, **không đưa email, phone và authorization vào log ngay từ đầu còn tốt hơn**:

```json
{
  "event": "profile.update.result",
  "requestId": "req-101",
  "outcome": "SUCCEEDED",
  "durationMs": 24
}
```

Hai mẫu trên không phủ định nhau: mẫu đầu minh họa masking để bảo vệ một field mà pipeline hiện vẫn cần xuất; mẫu thứ hai dùng **data minimization**. Chọn phương án phù hợp với nhu cầu điều tra và chính sách dữ liệu.

### 2.1. Các câu hỏi định hướng

Trước khi ghi một field, hãy hỏi:

- Có thực sự cần giá trị này để xử lý sự cố hoặc đối soát không?
- Có thể thay bằng `requestId`, `operationId`, `errorCode`, loại dữ liệu hoặc số đếm không?
- Ai là người được phép đọc log? Những nơi nào nhận bản sao?
- Một phần giá trị (ví dụ bốn chữ số cuối) có còn gây lộ danh tính không?
- Dữ liệu này có thể chứa **nội dung tùy ý của client** không?
- Nếu masking bị lỗi, log sẽ **bỏ trường** hay vô tình ghi bản raw?
- Khi hệ thống có nhiều nguồn log, chính sách này được áp dụng ở tất cả đường đi chưa?

## 3. Phân loại dữ liệu trước khi thiết kế masking

Một chính sách gợi ý, **không phải phân loại pháp lý mặc định**:

| Loại dữ liệu | Ví dụ | Chính sách gợi ý | Lưu ý |
| --- | --- | --- | --- |
| Credential/secret | password, bearer token, private key, cookie session, OTP | **DROP** hoặc `[REDACTED]` hoàn toàn | Không giữ prefix/suffix token khi không thật cần |
| Dữ liệu cá nhân | email, phone, address, tên, IP tùy bối cảnh | **OMIT** hoặc `[MASKED]` | Có thể vẫn nhận diện được nếu kết hợp nhiều trường |
| Thông tin thanh toán | số thẻ, CVV, account number | **Không log raw** | Những tiêu chuẩn ngành có thể có yêu cầu bổ sung |
| Định danh kỹ thuật đáng tin | event code, status, operation, duration | **ALLOW** | Validate format và cardinality |
| Correlation/request ID | requestId, traceId, messageId | **ALLOW có kiểm soát** | Không coi ID client tự khai là tin cậy |
| Business ID | orderId, customerId, paymentId | Tùy mục đích và độ nhạy | ID vẫn có thể là dữ liệu cá nhân |
| Payload/headers bất định | `requestBody`, `responseBody`, `headers`, `metadata` | **DROP mặc định** | Field con có thể chứa secret không biết trước |
| Exception message | error text từ SQL/HTTP/driver | **Hạn chế hoặc redact** | Có thể chứa URL/token/SQL literal |
| File path / host nội bộ | path, hostname, JDBC URL | Tùy hệ thống | Có thể lộ topology hoặc credential |
| Nội dung audit bắt buộc | Actor, action, target, result | Schema riêng, quyền và retention riêng | Masking không thay thế audit integrity |

Không nên áp quy tắc “mọi `id` đều an toàn”. Một customer ID có thể cho phép tra cứu hồ sơ, một trace ID có thể liên kết nhiều hành vi, và một IP có thể là dữ liệu cá nhân tùy mục đích và quy định.

**Allowlist trước, denylist sau.** Với các event quan trọng, hãy định nghĩa rõ field được phép ghi và cách biểu diễn. Denylist các từ `password`, `secret`, `token` vẫn có ích để phòng thủ bổ sung, nhưng dễ bỏ sót các tên lạ như `auth`, `bearer`, `credentialValue`, `api_key`, `session`, `refresh` hoặc một property nested.

## 4. Hiểu đúng: masking, redaction, tokenization, HMAC và encryption

| Kỹ thuật | Ví dụ output | Mục tiêu | Rủi ro/giới hạn |
| --- | --- | --- | --- |
| **Omit/drop** | Không xuất `password` | Ít dữ liệu nhất | Không tra cứu theo giá trị đó |
| **Redaction hoàn toàn** | `token=[REDACTED]` | Giữ dấu hiệu có trường mà không ghi giá trị | Vẫn cho biết field tồn tại |
| **Masking toàn bộ** | `email=[MASKED]` | Giấu giá trị nhưng giữ loại field | Không thể liên kết theo email |
| **Masking một phần** | `a***@example.com` | Hỗ trợ người đọc xác nhận một phần | Có thể lộ domain, độ dài, danh tính |
| **Tokenization** | `customerRef=tok_...` | Thay giá trị bằng token theo hệ thống token | Cần quản lý kho ánh xạ hoặc thuật toán/token service |
| **Keyed HMAC** | `actorTag=HMAC(key, identifier)` | Liên kết giả danh mà không để lộ trực tiếp | Vẫn linkable, cần bảo vệ khóa và kiểm soát key rotation |
| **Hash không khóa** | SHA-256(email) | Tạo digest | Email/phone có thể bị đoán bằng dictionary attack |
| **Encryption** | Ciphertext có thể giải mã bởi bên có khóa | Bảo mật dữ liệu khi lưu/truyền | Không phải masking; người có khóa có thể phục hồi raw |

Khi mục đích chỉ là debug một HTTP request, không cần thêm HMAC phức tạp nếu `requestId` do hệ thống tạo đã đủ. Khi cần liên kết cùng một chủ thể giữa các event mà không ghi identifier, HMAC có thể phù hợp với **threat model và chính sách quyền** rõ ràng. HMAC không tự làm thông tin ẩn danh tuyệt đối vì khả năng liên kết vẫn tồn tại.

Không tạo giá trị giả kiểu `****1234` với mọi dữ liệu chỉ để thấy “đã masking”. **Bốn chữ số cuối** đôi khi vẫn đủ nhạy cảm; chỉ dùng partial masking nếu có căn cứ nghiệp vụ, phê duyệt và kiểm soát truy cập.

## 5. Thiết kế pipeline masking tại nguồn

Nên coi đường dữ liệu log là một pipeline với nhiều khả năng rò rỉ:

```text
HTTP / message / DB / external service
              |
              v
        Business code
              |
        Classify fields
              |
       Drop / Mask / Validate
              |
          Safe log event
              |
         JUL / SLF4J
              |
       Encoder / Appender
              |
      stdout / file / network
              |
    Sidecar / node collector
              |
       Log storage / SIEM
```

**Vị trí ưu tiên là trước khi gọi logger.** Nếu raw data đã đi vào `LoggingEvent`, một appender thứ hai, logger khác hoặc exception renderer có thể ghi nó trước khi filter cuối pipeline hoạt động.

Có thể áp dụng **defense in depth**:

1. **Application boundary:** chỉ tạo event với fields đã được cho phép.
2. **Logging API/builder:** centralize classification, sanitization, masking và schema.
3. **Encoder/appender:** bổ sung redaction khi format, với test xem cả message/arguments/MDC/Throwable.
4. **Collector:** phòng tuyến thứ hai để phát hiện secret patterns, route/drop/quarantine theo policy.
5. **Storage:** phân quyền, retention, tìm kiếm và audit truy cập phù hợp.

Không coi bước 4 là biện pháp duy nhất: collector có thể nhận dữ liệu sau khi raw đã nằm trên disk, hoặc có pipeline khác bypass collector.

### 5.1. Chiến lược fail-closed

Một event chứa trường không nằm trong allowlist có thể được:

- **Bỏ field** và giữ các trường kỹ thuật an toàn.
- Thay giá trị bằng `[REDACTED]` nếu vẫn cần biết trường tồn tại.
- **Không phát event** và tăng metric/health signal nếu đây là log audit cần chính sách nghiêm ngặt.
- Báo lỗi kiểm soát schema qua một **kênh không chứa raw input**.

**Không nên:** nếu parser/regex thất bại thì in `originalMessage` để “dễ debug”. Đây là đường rò rỉ đúng vào lúc xử lý dữ liệu bất thường.

Thế nào là fail-closed còn tùy yêu cầu: với diagnostic log best-effort, bỏ field có thể hợp lý; với audit bắt buộc, mất cả record có thể vi phạm yêu cầu và cần một cơ chế capture an toàn khác.

## 6. Java 17 chạy độc lập: allowlist + masking theo field

Ví dụ sau sử dụng duy nhất **JDK 17 và `java.util.logging`**. Chính sách được định nghĩa tập trung:

- `event`, `requestId`, `outcome`, `errorCode`: **CODE**, chỉ nhận ký tự chữ/số ASCII cùng `_`, `-`, `.`, độ dài 1–64.
- `email`, `phone`: **MASK**, thay toàn bộ giá trị bằng `[MASKED]`.
- `authorization`, `accessToken`: **REDACT**, không giữ bất kỳ ký tự bí mật nào.
- Field **không nằm trong danh sách**: **bỏ qua** (fail-closed).
- ID bị chèn newline hoặc ký tự bất thường: thay thành `[INVALID]` trước khi ghi.
- `Logger` sử dụng một handler demo in stdout để kiểm tra chính xác kết quả.

Ví dụ cố tình đưa dữ liệu nhạy cảm và một ID có **newline giả log line** nhằm chứng minh dữ liệu không bị phát ra.

Lưu file **`SafeLoggingDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SafeLoggingDemo {
    private enum Treatment { CODE, MASK, REDACT }

    private static final Map<String, Treatment> POLICY = Map.of(
            "requestId", Treatment.CODE,
            "outcome", Treatment.CODE,
            "errorCode", Treatment.CODE,
            "email", Treatment.MASK,
            "phone", Treatment.MASK,
            "authorization", Treatment.REDACT,
            "accessToken", Treatment.REDACT
    );

    private static String safeCode(String value) {
        if (value != null
                && value.matches("[A-Za-z0-9_.-]{1,64}")) {
            return value;
        }
        return "[INVALID]";
    }

    private static String safeValue(
            Treatment treatment, String value) {
        return switch (treatment) {
            case CODE -> safeCode(value);
            case MASK -> value == null ? "-" : "[MASKED]";
            case REDACT -> value == null ? "-" : "[REDACTED]";
        };
    }

    private static String safeEvent(
            String event, Map<String, String> input) {
        StringBuilder result = new StringBuilder("event=")
                .append(safeCode(event));

        for (Map.Entry<String, String> field : input.entrySet()) {
            Treatment treatment = POLICY.get(field.getKey());

            // Trường không có trong chính sách sẽ không được log.
            if (treatment == null) {
                continue;
            }

            result.append(' ')
                    .append(field.getKey())
                    .append('=')
                    .append(safeValue(treatment, field.getValue()));
        }

        return result.toString();
    }

    private static void assertSafe(String line) {
        if (line.contains("alice@example.com")
                || line.contains("Bearer")
                || line.contains("card=4111")
                || line.contains("secret-token")
                || line.contains("\n")
                || line.contains("\r")) {
            throw new AssertionError("Sensitive content leaked");
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.safe-logging");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler stdout = new Handler() {
            {
                setLevel(Level.ALL);
            }

            @Override
            public void publish(LogRecord record) {
                if (record != null && isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " " + record.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        logger.addHandler(stdout);
        try {
            Map<String, String> first = new LinkedHashMap<>();
            first.put("requestId", "req-101");
            first.put("outcome", "SUCCEEDED");
            first.put("email", "alice@example.com");
            first.put("phone", "+84901234567");
            first.put("authorization", "Bearer secret-token");
            first.put("rawPayload", "card=4111111111111111");

            String firstLine = safeEvent(
                    "profile.update.result", first);
            assertSafe(firstLine);
            logger.info(firstLine);

            Map<String, String> second = new LinkedHashMap<>();
            second.put("requestId", "req-102\nERROR forged");
            second.put("outcome", "FAILED");
            second.put("errorCode", "PROVIDER_TIMEOUT");
            second.put("accessToken", "secret-token");

            String secondLine = safeEvent(
                    "payment.authorize.result", second);
            assertSafe(secondLine);
            logger.info(secondLine);
        } finally {
            logger.removeHandler(stdout);
            stdout.close();
        }
    }
}
```

Biên dịch và chạy trên **JDK 17 trở lên**:

```bash
javac SafeLoggingDemo.java
java SafeLoggingDemo
```

**Stdout chính xác** của chương trình:

```text
INFO event=profile.update.result requestId=req-101 outcome=SUCCEEDED email=[MASKED] phone=[MASKED] authorization=[REDACTED]
INFO event=payment.authorize.result requestId=[INVALID] outcome=FAILED errorCode=PROVIDER_TIMEOUT accessToken=[REDACTED]
```

Không xuất hiện giá trị email, số điện thoại, bearer token, raw payload hoặc đoạn `ERROR forged`. Nếu kiểm tra trong `assertSafe` thất bại, chương trình ném `AssertionError` và **không được coi là thành công**.

### 6.1. Giải thích từng phần của mã

1. `POLICY` là **allowlist các field đã biết**. Một field `rawPayload` không có trong policy sẽ bị bỏ qua hoàn toàn.
2. `LinkedHashMap` giữ thứ tự chèn để stdout có thứ tự field xác định.
3. `safeCode` không cố “sửa” input nguy hiểm thành một ID nhìn hợp lệ; nó trả `[INVALID]` khi format không hợp lệ.
4. `MASK` và `REDACT` đều trả về một giá trị hằng trong demo. Đây là **full masking**, không cần regex.
5. Handler JUL tắt parent handlers để không in lặp và không có timestamp biến thiên trong ví dụ.
6. `assertSafe` là **smoke check trên các payload test cụ thể**, không phải một bằng chứng toán học rằng mọi secret tương lai sẽ bị loại. Kiểm thử thực tế phải dùng nhiều bộ dữ liệu hơn.
7. `stdout` chỉ là đích hiển thị của demo; không có storage, encryption, rotation hay collector.
8. String chứa newline trong requestId không được đưa nguyên văn vào log, giảm nguy cơ **log injection**.

### 6.2. Những giới hạn quan trọng của demo

**Không dùng nguyên xi như một hệ thống masking production.**

- Mỗi field cần **phân loại dữ liệu có trách nhiệm**. Nếu nhầm `customerEmail` thành `CODE`, policy sẽ không tự hiểu nó là PII.
- Có những ID hợp lệ chứa Unicode hoặc định dạng dài hơn 64 ký tự; cần thiết kế validator thực tế thay vì nới lỏng không kiểm soát.
- `[MASKED]` và `[REDACTED]` trong ví dụ có cùng mức che dữ liệu, nhưng tên thể hiện hai ý nghĩa chính sách khác nhau.
- Policy theo **field name** không phát hiện secret giấu trong một field được phép, ví dụ `errorCode="Bearer xxx"` hoặc `event` do client tự quyết định. Đó là lý do mã `CODE` chỉ chấp nhận một grammar rất hẹp; với giá trị dynamic khác cần policy riêng.
- `assertSafe` chạy sau khi tạo chuỗi tạm trong bộ nhớ, không phải cơ chế bảo vệ memory dump.
- Giá trị của field bị che vẫn được truyền đến hàm `safeEvent`; cách tốt hơn là **không thu thập secret từ đầu** nếu không cần.
- Việc bỏ unknown field có thể làm mất thông tin điều tra; nên có metrics/cảnh báo schema violation ở kênh an toàn nếu cần.
- Không có cơ chế kiểm soát `Throwable`, MDC, message template, custom `toString()`, sidecar hoặc appenders khác. Phải bảo vệ các đường đó riêng.

## 7. Nâng bài thực hành lên một thiết kế ứng dụng thực tế

Từ demo JUL, có thể mở rộng thành các thành phần:

```text
com.example.logging
  FieldClassification        (loại nhạy cảm, mức cho phép)
  LogEventSchema             (event name, allowed fields, types)
  SafeLogEventBuilder        (chỉ nhận dữ liệu được phép)
  MaskingPolicy              (DROP/MASK/REDACT/ALLOW...)
  Sanitizer                  (validate, normalize, escape)
  SafeLogPublisher           (chuyển event đã kiểm duyệt tới logger)
  MaskingPolicyTest          (unit tests)
  LoggingPipelineTest        (integration tests)
```

Đây là **gợi ý kiến trúc**, không phải các file đã được tạo sẵn. Một ứng dụng có thể dùng ít lớp hơn nếu phạm vi nhỏ; mục tiêu là **tập trung quy tắc**, không để mỗi controller tự viết regex khác nhau.

Hợp đồng API nên tách:

- **Raw input:** chỉ được phép tồn tại ở tầng xử lý nghiệp vụ, chưa phải loggable data.
- **Safe value:** kiểu/kết quả đã xử lý theo policy.
- **Safe log event:** object gồm event code, fields đã cho phép và kết quả.
- **Publisher:** xuất đúng structured event, không bổ sung raw payload trở lại.

Một lựa chọn nâng cao là dùng **type-safe wrappers** thay vì `Map<String, String>` chung chung, ví dụ `SafeRequestId`, `SanitizedErrorCode`, `MaskedEmail`. Compiler không chứng minh mọi field an toàn, nhưng API có thể hạn chế việc một developer vô tình truyền cả DTO vào logger.

## 8. Thiết kế schema và masking theo loại sự kiện

Một quy tắc global `fieldName=email => MASK` có thể hữu ích nhưng chưa đủ. Các event có mục đích khác nhau.

| Event | Trường an toàn nên có | Trường phải loại hoặc che |
| --- | --- | --- |
| `auth.login.result` | event, outcome, errorCode, requestId | password, OTP, raw authorization, session |
| `profile.update.result` | requestId, operation, result, duration | full profile payload, email, phone, address |
| `payment.capture.result` | paymentRef theo policy, status, errorCode | card number, CVV, token, bank details |
| `http.request.completed` | method, route template, status, duration, requestId | raw URL/query, cookies, body |
| `message.processing.failed` | event ID, message type, attempt, safe errorCode | message body, secret headers |
| `order.create.result` | order ID theo policy, outcome, correlation ID | object graph có customer PII |
| `config.change.result` | authenticated actor, setting name, approved change ID, outcome | giá trị secret, connection strings |
| `job.run.completed` | job name, run ID, counts, duration | full exported records và data snapshot |

Với **config changes**, có thể ghi `secretChanged=true` thay vì `oldSecret`/`newSecret`. Với request cần debug, dùng `route=/api/orders/{id}` thay vì raw path/query có user data.

**Lưu ý về số liệu:** masking có thể thay đổi giá trị nhìn thấy nhưng **không nên thay đổi nghĩa của outcome, duration, status**. Nếu policy che một reasonCode trong khi dashboard dùng reasonCode làm label, cần thiết kế mapping mã lỗi vô hại thay thế, không chỉ mask toàn bộ rồi làm mất khả năng giám sát.

## 9. Structured logging: che trước khi serialize

Trong ứng dụng Java hiện đại, thường muốn xuất JSONL với fields:

```json
{
  "timestamp": "2026-11-10T02:00:00Z",
  "level": "INFO",
  "service": "accounts-api",
  "event": "profile.update.result",
  "requestId": "req-101",
  "outcome": "SUCCEEDED",
  "email": "[MASKED]"
}
```

Nên xây `SafeLogEvent` trước, rồi **serialize bằng encoder JSON có escaping đúng chuẩn**. Nếu dùng `log.info("{}", request)` và hy vọng encoder tự nhận biết nested email/password, không có bằng chứng chắc chắn cho việc đó.

**Không tự nối JSON string trong production**, kể cả khi chuỗi trông đơn giản: quote, backslash, newline, control characters, invalid Unicode hoặc nested objects có thể phá JSON hoặc dẫn tới log injection. Jackson/encoder của logging backend hoặc một serializer tương thích giúp kiểm soát cú pháp; **nhưng serializer không tự xác định trường nào là secret**.

### 9.1. Structured logging và field-level redaction

Một pipeline ví dụ:

```text
SafeLogEvent(
  event = "profile.update.result",
  fields = {
    requestId = "req-101",
    outcome   = "SUCCEEDED",
    email     = MASKED
  }
)
  -> JSON encoder
  -> one JSON object per line
  -> file/stdout
  -> collector parse JSON
  -> storage
```

Các quy tắc:

- Chỉ những **field name nằm trong catalog** được đưa tới encoder.
- Trường text có giới hạn độ dài và escaping.
- Trường `durationMs` phải giữ kiểu number; `status` giữ kiểu integer nếu schema quy định.
- Field null/unknown có contract rõ: omit, `null` hoặc mã `UNKNOWN`.
- Không cho client quyết định field names vì nguy cơ **mapping explosion**.
- Tránh đưa raw object dưới `details` hoặc `additionalFields` vì nó có thể bypass policy.
- Kiểm tra output tại sink thực tế, không chỉ object trước khi serialize.

## 10. Tích hợp SLF4J 2 và Logback

SLF4J là **API facade**, còn Logback là một backend. Khi ứng dụng dùng SLF4J 2.x, bạn có thể phát key-value attributes:

```java
// Đoạn tích hợp: log là org.slf4j.Logger từ SLF4J 2.x.
// Các biến sau đã được SafeLogEventBuilder xử lý theo policy.
log.atInfo()
        .addKeyValue("event", "profile.update.result")
        .addKeyValue("requestId", safeRequestId)
        .addKeyValue("outcome", "SUCCEEDED")
        .addKeyValue("email", maskedEmail)
        .log("Profile update completed");
```

**Điểm bắt buộc:** `maskedEmail` phải là giá trị đã che, **không phải email raw**. `addKeyValue` không tự mask hoặc redact. Backend/encoder phải xuất key-value đúng định dạng; một pattern chỉ in `%msg` có thể bỏ attributes.

Với Logback và encoder JSON tương thích, một cấu hình tích hợp thường có dạng:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Đây là **mảnh cấu hình cho dự án đã có dependency tương thích** với `logstash-logback-encoder`, ngoài SLF4J/Logback. Nó **không tự bật masking** và không thể chạy với JDK thuần. Tên fields, cách xuất MDC, structured arguments và Throwable phụ thuộc encoder/version cụ thể.

Đặc biệt, Logback có thể đưa dữ liệu vào event từ nhiều đường:

- `message` hoặc formatted message;
- template arguments;
- structured key-value pairs;
- markers;
- `MDC`;
- `Throwable`/stack trace;
- metadata của logger/thread.

Một filter chỉ thay `formattedMessage` **không chứng minh** các đường còn lại đã được mask. Nếu dùng encoder-level masking (ví dụ decorators/field-name filters được thư viện hỗ trợ), phải xác nhận chính xác thứ tự xử lý, version, support nested objects và phạm vi mà nó áp dụng.

### 10.1. Cẩn thận với double logging

Nếu đã xuất event JSON an toàn từ Java nhưng một agent khác thu thêm text console chưa được mask, raw data có thể vẫn rò. Kiểm tra **mọi appender và sink**: file, console, rolling archive, HTTP exporter, stdout của sidecar, collector debug log và error-status logger.

Masking ở một pipeline **không bù** cho một pipeline khác đang ghi raw. Nếu có audit trail riêng, áp dụng chính sách dành cho audit trail đó và kiểm chứng quyền truy cập/retention.

## 11. HTTP logging: xử lý header và body

HTTP middleware thường là điểm dễ lộ dữ liệu vì request có thể chứa `Authorization`, `Cookie`, query parameters và body.

**Không nên:**

```java
// Mã minh họa cần tránh trong Servlet/Spring web code.
log.debug("headers={}", request.getHeaderNames());
log.debug("authorization={}",
        request.getHeader("Authorization"));
```

Dòng đầu có thể chỉ in Enumeration chứ không in toàn bộ headers, nhưng việc dùng một generic header dumper để ghi tất cả tên/giá trị là rủi ro. Dòng thứ hai chắc chắn đưa credential vào log nếu DEBUG được bật.

**Nên:** chọn một schema access log có `method`, `routeTemplate`, `status`, `durationMs`, `requestId` đã validate. Ví dụ:

```json
{
  "event": "http.request.completed",
  "method": "POST",
  "route": "/api/orders",
  "status": 201,
  "requestId": "req-101",
  "durationMs": 18
}
```

Đây là ví dụ sự kiện, không phải output của một đoạn Servlet chạy độc lập.

Nếu một số HTTP headers cần thiết cho debug, dùng **allowlist tên headers** và chính sách riêng cho từng header, không in `Authorization`, `Cookie`, `Set-Cookie`, các custom auth headers hoặc raw query. `User-Agent` vẫn là dữ liệu tự khai có thể chứa newline/chuỗi dài và có yếu tố fingerprinting; chỉ ghi dạng giới hạn/chuẩn hóa nếu được phép.

Với Spring Boot, có thể dùng `OncePerRequestFilter` hoặc instrumentation/filter phù hợp để đo request lifecycle, nhưng **chú ý async request**: filter trả về không phải lúc nào response/business transaction cũng đã hoàn tất. Đặt event name theo ranh giới đã quan sát.

### 11.1. Không log request/response body mặc định

Body có thể gồm mật khẩu, hồ sơ khách hàng, payment data hoặc file upload. Một request có thể là binary, streaming, rất lớn hoặc chứa nhiều schema động. Generic body dumper là nguồn rò rỉ khó kiểm soát.

Nếu có trường hợp điều tra cần body, dùng một cơ chế debug được phê duyệt, **scope hẹp, thời hạn ngắn, quyền hạn cụ thể và masking theo schema**, chứ không bật log full body toàn hệ thống khi gặp sự cố.

## 12. MDC, TraceContext và vấn đề dữ liệu lọt qua thread pool

SLF4J `MDC` cho phép đính kèm context vào nhiều sự kiện trong cùng scope. Nhưng nếu đặt raw client value vào MDC, encoder có thể xuất nó trong **mọi log event**:

```java
// Mảnh tích hợp cần tránh.
MDC.put("authorization", request.getHeader("Authorization"));
```

Một mẫu tốt hơn:

```java
import org.slf4j.MDC;

// Mảnh tích hợp: validatedRequestId đã được kiểm tra format/length.
String previous = MDC.get("requestId");
try {
    if (validatedRequestId == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", validatedRequestId);
    }

    processRequest();
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
```

Đây **không phải class chạy độc lập**; biến, `processRequest()` và dependency SLF4J phải do dự án cung cấp.

Nguyên tắc:

1. Chỉ đưa **những context keys đã được allowlist** vào MDC.
2. Validate/normalize trước khi đưa vào MDC, không tin `X-Request-ID` client gửi nguyên dạng.
3. Dùng `finally` để khôi phục context, vì thread pool tái sử dụng thread.
4. Với `CompletableFuture`, executor, Reactor/WebFlux hoặc scheduler, context **không tự lan qua mọi luồng**; dùng propagation đúng framework.
5. Nếu copying MDC map qua task, đừng copy raw headers, tokens hay user profile vào context mới.
6. Tránh đưa traceId, userId, requestId vào **metric labels** có cardinality cao.
7. Trace/correlation IDs hỗ trợ tìm log, **không phải danh tính được xác thực** và không chứng minh tác vụ thành công.

Một lỗi gây rò data nghiêm trọng: thread A xử lý user 1 và quên clear MDC; thread đó tiếp tục xử lý user 2, làm log user 2 mang identifier của user 1. Cần test concurrency và thread reuse, không chỉ test một request đơn.

## 13. Exception logging: đường rò rỉ thường bị bỏ sót

Một lỗi từ database, HTTP client hay validation library có thể chứa SQL query, URL với token, header/body fragment, hostname hoặc file path trong `Throwable.getMessage()`.

Ví dụ rủi ro:

```java
// Mã minh họa không nên dùng nếu message không được đánh giá an toàn.
log.error("External call failed: {}", failure.getMessage());
```

**Không kết luận** chỉ vì dùng `log.error("... ", failure)` là an toàn: việc truyền `Throwable` giữ cause chain phục vụ điều tra, nhưng **một encoder có thể in chính các exception messages có chứa secret**. Điều này tạo ra sự đánh đổi:

- **Preserve root cause:** giữ bằng chứng kỹ thuật, hữu ích để phân tích.
- **Protect sensitive data:** không đưa raw exception text chứa secret tới sink không được phép.

Một chính sách thực tế:

1. Ở event thường, ghi `errorCode`, `exceptionType`, `operationId`, `dependency` (giá trị allowlisted) và outcome; tránh raw `failure.getMessage()`.
2. Với exception cần stack trace, dùng đường log nội bộ được bảo vệ và cấu hình renderer/redaction đã kiểm thử — không trả stack trace ra API response.
3. Nếu muốn log đầy đủ `Throwable`, kiểm tra library có thể chứa gì trong message/cause/suppressed và test encoder thực tế.
4. Với lỗi liên quan secret, có thể cần **safe exception wrapper** không chứa secret text, đồng thời giữ correlation tới một hệ điều tra được bảo vệ theo chính sách.
5. Chỉ bắt/unwrap exception theo contract; đừng nuốt lỗi hoặc thay đổi logic retry chỉ vì che log.
6. Không dump object exception thành JSON tùy ý; object graph có thể có cyclic refs, các fields không kiểm soát và dữ liệu nhạy cảm.

**Masking exception bằng regex trên stack trace là phòng tuyến bổ sung, không phải bảo đảm.** Một stack trace chứa dữ liệu với escape/encoding khác thường có thể bypass pattern.

## 14. Masking theo regex: nơi dùng và giới hạn

Regex có thể là một lớp phòng thủ thứ hai cho **free-text legacy logs** khi chưa thể chuyển sang structured fields.

Ví dụ mục tiêu phát hiện một dạng chuỗi `Authorization: Bearer ...` trong log text. Dù biểu thức chính xác có thể được viết, vẫn có các vấn đề:

- Client có thể thay đổi **case, spacing, delimiter, percent encoding, unicode hoặc newline**.
- Secret có thể ở dạng JSON key khác, XML attribute, query parameter, URL encoded, base64 hoặc nested field.
- Regex có thể vô tình che những chuỗi vô hại, làm mất thông tin điều tra.
- Regex không biết giá trị nào thuộc `email`, `password` trong một object nested nếu parsing thất bại.
- Một regex phức tạp có thể gây chi phí CPU lớn hoặc catastrophic backtracking với input độc hại.
- Regex chạy ở collector **sau khi raw đã tới file** không xóa được những bản sao nằm trên disk trước đó.

Một ví dụ nhỏ về regex dùng cho **chuỗi được giới hạn và format đã biết**, chỉ để làm rõ cơ chế:

```java
// Mảnh tích hợp, KHÔNG phải quy tắc bảo mật đầy đủ.
// Chỉ xử lý một pattern cố định, không đảm bảo mọi biến thể bearer token.
String sanitized = rawLine.replaceAll(
        "(?i)Authorization: Bearer [A-Za-z0-9._~+/-]+",
        "Authorization: Bearer [REDACTED]");
```

Đoạn này là **minh họa**, `rawLine` phải có sẵn và không nên cho log nếu regex thất bại. Nó **không** xử lý toàn bộ credential syntax, header folding, Unicode lạ, dấu `=`, token khác pattern hoặc secret xuất hiện ở field khác. Không thay thế cơ chế allowlist ở nguồn bằng snippet này.

Nếu làm masking sâu trên JSON, hãy **parse JSON với schema và field path được cho phép**, thay vì dùng regex thay substring trong JSON string. Nhưng parser có thể thất bại với JSON hỏng; fallback phải an toàn, không in raw payload.

## 15. Masking một phần: khi nào có thể chấp nhận?

Đôi khi bộ phận hỗ trợ muốn xác định “số điện thoại mà người dùng đã nhập có đúng hai chữ số cuối không?”. Có thể có yêu cầu che một phần, nhưng phải đánh giá rủi ro.

Ví dụ:

```text
phone="[MASKED]"
email="[MASKED]"
cardNumber="[REDACTED]"
```

so với:

```text
phone="********67"
email="a***@example.com"
```

Mẫu thứ hai tiết lộ nhiều hơn: hậu tố điện thoại và domain email. Nó có thể cho phép đối chiếu danh tính khi kết hợp với thời điểm, địa điểm, requestId hoặc dữ liệu rò rỉ khác.

Một policy hợp lệ cần nêu:

- Field nào được phép che một phần?
- Số ký tự còn lại, vị trí, và trường hợp chuỗi ngắn xử lý ra sao?
- Có cần normalize định dạng trước khi tính prefix/suffix không?
- Unicode/code point và ký tự tổ hợp có khiến partial masking lộ hoặc cắt sai không?
- Ai được xem giá trị đã che một phần, retention bao lâu?
- Có nên dùng token/HMAC thay thế để liên kết mà không lộ suffix?

**Không áp dụng “giữ bốn số cuối” cho password, private key hoặc access token.** Nếu không có yêu cầu cụ thể, full redaction là mặc định an toàn hơn.

## 16. Idempotency và pseudonymization bằng HMAC

Trong một số bài toán, SRE cần liên kết các bản ghi của **cùng một entity** mà không ghi identifier raw. Có thể cân nhắc tạo tag bằng **HMAC với key được quản lý an toàn**.

Ví dụ khái niệm:

```text
raw identifier
    |
HMAC(secret key, canonical identifier)
    |
short-lived / scoped pseudonym tag
    |
log: actorTag=...
```

Khác với SHA-256(email) không khóa, HMAC khó bị tấn công dictionary nếu key được giữ bí mật và đủ mạnh. Tuy nhiên, **pseudonym không phải anonymous**: một tag ổn định còn cho phép liên kết hành vi; người có key hoặc quyền tham chiếu khác vẫn có thể suy ra danh tính. Vì thế cần:

- Secret/key storage và rotation policy.
- Scope theo mục đích/tenant nếu cần hạn chế cross-context linkage.
- Chính sách retention và quyền truy cập tag.
- Đánh giá khi đổi key: có cần nối lịch sử hay chủ đích làm mất linkage?
- Kiểm thử canonicalization của input để tránh một người có nhiều tag do format khác nhau.
- Không đưa raw identifier vào log khi tạo tag thất bại.
- Không log HMAC key hoặc stack trace chứa secret key.

Chỉ thêm cơ chế này nếu có yêu cầu điều tra thực sự và đã đánh giá privacy. Với nhiều ứng dụng, `requestId` và `errorCode` an toàn đã đủ.

## 17. Kiểm thử masking: từ unit test đến end-to-end

Một test masking phải chứng minh **giá trị nhạy cảm không thể xuất hiện trên những đường được đánh giá**, không chỉ rằng một chuỗi `"[MASKED]"` tồn tại.

### 17.1. Ma trận kiểm thử

| Input hoặc tình huống | Kỳ vọng |
| --- | --- |
| Email đầy đủ | Không có địa chỉ raw ở log |
| Phone number | Không còn số điện thoại raw |
| Bearer token | Không có token/prefix bí mật ngoài policy |
| Cookie/session | Không có session ID |
| Password/OTP | Omit/redact, không lưu một phần giá trị |
| Nested `user.credentials.password` | Field-path policy nhận diện hoặc object bị drop |
| Unknown field | Fail-closed, không in nguyên giá trị |
| Null/empty | Xử lý theo schema, không NPE |
| JSON string với quote/backslash | Encoder escape đúng |
| Newline/CR/tab | Không tạo log line giả |
| Unicode/emoji | Không làm hỏng encoding; masking đúng code point |
| Base64/URL encoding | Không dựa vào regex đơn giản để đảm bảo che toàn bộ |
| Object `toString()` | Không vô tình dump fields nhạy cảm |
| Throwable message chứa token | Không lộ qua cause/stack trace ở sink |
| MDC chứa giá trị nhạy cảm | Không export hoặc đã redact |
| Async/thread pool | Không leak context giữa các tasks |
| Multiple appenders | Không một sink nào nhận raw |
| Logback encoder JSON | Field names, types và redaction đúng |
| File rotation | Archive cũ không còn dữ liệu raw ngoài policy |
| Sidecar collector | Không log raw trong debug/error logs của collector |
| Remote 429/503 | Retry/buffer không gây dump payload khi lỗi |
| Masking rule missing | Không dùng nguyên giá trị như fallback |
| Schema cập nhật | Field mới được phân loại trước khi phát hành |
| High throughput | Masking không gây log storm/CPU spike hoặc drop không đo được |

### 17.2. Test cho mã Java 17 ở mục 6

Chương trình đã có hai payload thử nghiệm và `assertSafe`:

- `email` phải thành `[MASKED]`.
- `authorization` và `accessToken` phải thành `[REDACTED]`.
- `rawPayload` không được phát vì không nằm trong policy.
- Request ID chứa newline phải thành `[INVALID]`.
- Không được xuất thêm một dòng `ERROR forged`.

Đây là một **smoke test**. Khi đưa thành library, nên viết **JUnit 5 parameterized tests** theo từng sensitivity class, bao gồm nhiều dạng null, unicode, khoảng trắng, nested data và syntax bất thường. Unit test nên kiểm tra **giá trị của SafeLogEvent**, không phụ thuộc logger đã bật INFO hay chưa.

### 17.3. Kiểm tra sau encoder và collector

Quy trình integration có thể gồm:

1. Tạo tập **synthetic secrets** duy nhất chỉ dùng cho test, ví dụ chuỗi đánh dấu `SYNTHETIC_SECRET_ALPHA`.
2. Phát events qua đúng logging backend/encoder của ứng dụng.
3. Thu log file/console bằng test appender hoặc temp volume cô lập.
4. Nếu là JSONL, dùng **JSON parser thực** đọc từng dòng; xác nhận số event/schema.
5. Tìm các synthetic secret canary trên **mọi output** và field nested.
6. Cho dữ liệu chạy qua sidecar/collector test và query log sink thử nghiệm.
7. Xác minh collector không phát raw value trong status/error/debug logs.
8. Thử rotation, restart, buffer retry, process crash và network outage.
9. Kiểm tra dữ liệu lịch sử trong archive và destination đã được áp dụng retention phù hợp.
10. Đánh giá logs của **các thư viện bên thứ ba** nếu chúng có đường logging độc lập.

**Không dùng secret thật làm dữ liệu thử nghiệm.** Khi test phát hiện leak, việc lưu lại screenshot/raw logs trong ticket cũng có thể mở rộng rủi ro; ghi kết quả kiểm tra và canary test có kiểm soát thay vì copy credential thật.

## 18. Rủi ro ở các tầng thường bị quên

### 18.1. Log trước masking

Một controller gọi `log.debug("request={}", request)` trước khi `SafeLogEventBuilder` xử lý. Dù event chính đã an toàn, log debug đầu tiên vẫn leak. Cần review **toàn bộ vị trí tạo log** trong critical flows.

### 18.2. Multiple log sinks

Console appender có masking, nhưng file appender hoặc telemetry exporter vẫn lưu raw. Trường hợp ngược lại cũng xảy ra. Test tất cả appenders và đường dẫn.

### 18.3. Exception chain

Một wrapper exception giữ nguyên cause có thể giữ cả exception message chứa URL/token. Đừng chỉ mask `getMessage()` của wrapper rồi cho encoder tự in `Caused by` raw bên dưới.

### 18.4. Runtime log level change

DEBUG/TRACE hiện đang tắt nhưng có thể được bật trong sự cố. Chính sách masking phải **đúng ở mọi level**, không chỉ INFO/ERROR.

### 18.5. Request bodies và message payload

Ghi toàn bộ object DTO hoặc Kafka record dễ chứa field không nằm trong policy. Chỉ phát **metadata và event code** cần thiết. Dữ liệu deserialize lỗi cũng không nên bị dump raw vào catch block.

### 18.6. Collector parse lỗi

Một JSON event hỏng có thể khiến collector log ra raw line để giúp debug. Nếu có dữ liệu nhạy cảm, việc này tạo một **bản sao mới** ở collector logs. Cần cấu hình error logging/invalid record quarantine an toàn.

### 18.7. Masking nhầm làm hỏng observability

Nếu che luôn `event`, `outcome`, `errorCode`, `traceId`, dashboard có thể mất giá trị. Nên phân loại theo field và mục đích; dùng mã lỗi chuẩn và IDs hợp lệ, chứ không blanket replace mọi chuỗi.

### 18.8. Log injection dù đã masking

Che email/token không ngăn một field public chứa `\nERROR forged`. Phải validate/escape **tất cả dữ liệu có thể do client điều khiển**, kể cả correlation ID và message text.

### 18.9. Thông tin trong URL/query

Token có thể xuất hiện trong `httpClient.get(url)` exception, proxy access log hoặc raw `request.getRequestURL()`. Với HTTP logging, dùng route template/method/status thay cho raw URL khi có thể.

### 18.10. Diagnostic event chứa snapshot cấu hình

Một debug log có thể in toàn bộ môi trường/system properties, file config hoặc connection string. Thường không nên ghi raw; hãy log tên setting và trạng thái `changed`/ `enabled`, bỏ phần secret value.

## 19. Hiệu năng và kích thước của masking pipeline

Masking có chi phí:

- Phân loại field/lookup policy.
- Copy string/JSON encoding và allocation.
- Regex scan trên message lớn (nếu dùng).
- Traversal nested objects; dễ tăng CPU nếu không giới hạn sâu.
- Định dạng/escape các chuỗi dài.
- Chi phí thêm trên mọi event khi throughput cao.

Khuyến nghị:

1. **Data minimization trước:** không đưa object lớn vào log để sau đó mới scan.
2. Dùng **catalog cố định và lookup map/enum** cho fields thường gặp.
3. Tránh regex trên raw payload lớn; nếu không tránh được, giới hạn size và độ phức tạp pattern.
4. Có giới hạn field count, string length, nesting depth.
5. Không serialize dữ liệu debug đắt tiền khi level bị tắt.
6. Đo p95/p99 latency logging, CPU/allocation, dropped events và queue utilization.
7. Với audit cần lưu, thiết kế đường ghi bền vững độc lập khỏi sampling.
8. Dùng test load để xem masking có làm appender/collector bị nghẽn không.

Với SLF4J:

```java
// Đoạn tích hợp: expensiveDebugView() có thể tốn CPU.
if (log.isDebugEnabled()) {
    log.debug("event=debug.summary data={}",
            expensiveDebugView()); // Hàm trả dữ liệu đã cho phép log.
}
```

Placeholder không làm `expensiveDebugView()` lazy vì Java đánh giá argument trước khi gọi `debug`. Nhưng cũng không nên lấy `request.toString()` trong hàm này; chỉ trả một DTO debug **đã được phân loại và giới hạn field**.

## 20. Chính sách khi masking thất bại

Masking cũng là code và có thể lỗi vì:

- Rule không tồn tại cho field mới.
- Null/unexpected object type.
- Parser JSON thất bại.
- Regex timeout hoặc quá tốn CPU.
- Serializer gặp invalid Unicode/cyclic object.
- Cấu hình policy bị thiếu hoặc sai phiên bản.
- Một downstream encoder không tuân theo schema đã định.

Chọn hành vi rõ:

| Trường hợp | Hành vi đề xuất |
| --- | --- |
| Field mới chưa được phân loại | Omit hoặc `[REDACTED]`; cảnh báo schema policy an toàn |
| Secret field có null | Omit/biểu diễn null theo schema, không NPE |
| Public identifier không hợp lệ | `[INVALID]` hoặc fallback server-generated ID |
| Lỗi serializer | Không in raw object như fallback |
| JSON parse lỗi ở collector | Quarantine/drop theo policy, không dump raw line |
| Masking quá chậm | Giới hạn kích thước và instrumentation; không tắt masking |
| Audit event không thể bảo vệ | Tuân thủ policy fail-closed/fail-safe đã định, không âm thầm bỏ |
| Test phát hiện secret | Chặn release, đánh giá log tồn lưu và xử lý incident phù hợp |

Nếu service không thể tạo một **audit record an toàn** nhưng nghiệp vụ nhạy cảm bắt buộc có audit, xử lý phải tuân thủ business policy (có thể từ chối thao tác). Với diagnostic log thông thường, bỏ một field rủi ro có thể tốt hơn đưa secret vào sink.

**Không dùng nội dung raw làm thông điệp lỗi của chính cơ chế masking.** Ví dụ tránh `throw new RuntimeException("mask failed for: " + raw)`; nó có thể lại bị logger ghi ra.

## 21. Quy trình rollout trong dự án

Một kế hoạch thực hành có thể gồm các bước:

### Giai đoạn 1: Xác định phạm vi và các đường log

- Liệt kê HTTP access logs, business logs, exception logs, message consumer, scheduled jobs và thư viện bên thứ ba.
- Ghi nhận appenders: console, file, rolling archive, remote/OTLP, sidecar.
- Dùng **synthetic secret canary** để phát hiện đường rò trong môi trường test.
- Chọn một luồng cụ thể như `profile.update.result` để thực hành đầu tiên.

### Giai đoạn 2: Thiết lập chính sách

- Catalog fields và sensitivity class.
- Tách `DROP`, `REDACT`, `MASK`, `ALLOW`.
- Định nghĩa enum error codes và validators.
- Chốt default cho unknown fields: fail-closed.
- Xác định người phê duyệt khi muốn mở rộng allowlist.

### Giai đoạn 3: Tạo SafeLogEventBuilder

- Bắt đầu từ Java 17 demo.
- Chuyển policy sang cấu hình/Java types phù hợp, có version.
- Không nhận arbitrary object graph nếu chưa có serializer kiểm soát.
- Giới hạn string length, key length, field count.
- Tách việc encode JSON và việc quyết định data sensitivity.

### Giai đoạn 4: Tích hợp vào logger

- Cấu hình SLF4J/Logback hoặc Log4j 2 tương ứng.
- Xuất structured fields thật qua encoder.
- Áp dụng field policy cho MDC, Throwable và các appender.
- Bỏ các log raw request/body/header cũ.
- Không nhân đôi event qua nhiều tuyến ingest.

### Giai đoạn 5: Kiểm thử và giám sát

- Unit tests cho từng field class và trường hợp ngoại lệ.
- Integration tests cho output JSONL/console/file.
- Test collector và retention/rotation.
- Test negative với canary và log injection.
- Dashboard metrics cho masking policy violations (không có giá trị raw).
- Review thủ công một tập sample logs đã được kiểm soát.

### Giai đoạn 6: Đánh giá lịch sử và vận hành

- **Masking mới không xóa dữ liệu đã bị ghi trước đó.** Nếu phát hiện leak lịch sử, cần quy trình ứng phó phù hợp: đánh giá tác động, quyền truy cập, retention, xóa theo chính sách và rotation credentials khi cần.
- Hạn chế truy cập những sink có thể còn raw data.
- Cập nhật coding standards, code review checklist và onboarding.
- Bổ sung CI guardrails như test synthetic secrets hoặc static analysis có căn cứ.
- Theo dõi hiệu năng, false positives/false negatives và trải nghiệm điều tra.

## 22. Tiêu chí nghiệm thu cho bài thực hành

Một kết quả hoàn chỉnh nên đáp ứng:

| Tiêu chí | Bằng chứng mong muốn |
| --- | --- |
| **Có source policy rõ** | Danh sách field và treatment được review |
| **Chạy Java 17 độc lập** | `javac` và `java` chạy thành công |
| **Che secret** | Không có `Bearer secret-token` trong stdout |
| **Che PII** | Không có email/phone raw |
| **Unknown field fail-closed** | `rawPayload` không được xuất |
| **Chặn log injection cơ bản** | ID chứa newline thành `[INVALID]` |
| **Event context vẫn đủ** | `event`, `requestId`, `outcome`, `errorCode` đúng |
| **Không có pipeline bypass** | Mọi appender/collector được kiểm tra |
| **JSONL hợp lệ nếu dùng JSON** | Parse thành object, kiểu field đúng |
| **Throwable và MDC được đánh giá** | Không leak qua exception/ThreadLocal |
| **Hoạt động khi rotate/retry** | Không phát raw vào archive hoặc collector lỗi |
| **Có test canary** | Không thấy synthetic secret ở sink cuối |
| **Có cảnh báo chính sách** | Schema violation được đo không kèm raw |
| **Có quản lý lifecycle dữ liệu** | Retention, quyền và ứng phó dữ liệu đã lộ được xác định |

Các tiêu chí này dành cho một bài thực hành/thử nghiệm có kiểm soát. Một hệ thống tài chính/y tế/định danh thật có thể cần quy trình threat modeling, kiểm toán và yêu cầu ngành sâu hơn.

## 23. Những anti-pattern cần tránh

### 23.1. Mask ở collector nhưng vẫn ghi raw xuống disk

Dữ liệu đã tồn tại trong archive/local volume và có thể được backup trước khi đến collector. Mask tại nguồn trước, collector chỉ là phòng tuyến bổ sung.

### 23.2. Chỉ mask message, bỏ MDC/Throwable

Những nơi đó vẫn có thể chứa token hoặc dữ liệu cá nhân. Đánh giá toàn bộ `LoggingEvent` và các appenders.

### 23.3. In object/DTO theo `toString()`

Tự động sinh `toString()` có thể thêm một field mới sau khi deploy. Chọn fields cụ thể thay vì serialize toàn bộ object.

### 23.4. Dựa hoàn toàn vào regex email

Một secret có thể không giống email hoặc có encoding bất thường. Regex không thay thế field classification.

### 23.5. Mask một phần mặc định

Giữ domain/suffix có thể đủ để tái nhận diện. Mặc định full masking/drop khi không có nhu cầu cụ thể.

### 23.6. Hash email không khóa rồi gọi là ẩn danh

Email và phone có không gian đoán tương đối nhỏ, có thể bị dictionary attacks. Cân nhắc HMAC và privacy policy nếu phải liên kết.

### 23.7. Log raw khi masking exception thất bại

Đây là fail-open. Thiết kế fallback không bao giờ đưa raw data vào logger.

### 23.8. Cho phép arbitrary field name

Client có thể tạo field `token123` hay hàng nghìn keys khác gây mapping explosion và bypass các quy tắc. Field name phải có catalog.

### 23.9. Bật DEBUG để “xem toàn bộ request”

Đây là cách làm dễ lộ password, card data và cookie. Bật một debug mode hẹp có dữ liệu đã kiểm duyệt, quyền và thời hạn rõ ràng.

### 23.10. Coi masking là giải pháp duy nhất

Dù đã mask đúng, dữ liệu log vẫn có thể chứa thông tin metadata nhạy cảm và cần RBAC, TLS, retention, encryption và audit truy cập.

## 24. Checklist trước khi đưa lên production

- [ ] Phân loại field theo sensitivity, mục đích và quyền sử dụng.
- [ ] Mặc định không ghi secret, raw payload, full headers hay DTO `toString()`.
- [ ] Có allowlist và default fail-closed cho field chưa biết.
- [ ] Chọn DROP/REDACT/MASK/ALLOW riêng theo field/event.
- [ ] Không dùng SHA-256(email) đơn thuần để tuyên bố ẩn danh.
- [ ] Validate/escape IDs và input điều khiển để chống log injection.
- [ ] Dùng encoder structured JSON phù hợp khi cần truy vấn.
- [ ] Kiểm tra MDC, request/response, message consumer, Throwable và suppressed causes.
- [ ] Review mọi appender, logger và đường collect — kể cả log debug của collector.
- [ ] Kiểm thử Java17 example, unit tests, integration tests và synthetic canary tại sink.
- [ ] Test khi debug level bật, async queue đầy, rotate, restart và network lỗi.
- [ ] Giới hạn string size/nesting, đo CPU/GC và memory overhead.
- [ ] Có metrics cho policy violations không mang dữ liệu raw.
- [ ] Không để masking mới che mất dữ liệu đã ghi cũ: có kế hoạch xử lý lịch sử.
- [ ] Bảo vệ logs với RBAC/TLS/retention và audit truy cập thích hợp.
- [ ] Audit event nhạy cảm có durability/integrity riêng ngoài log chẩn đoán.
- [ ] Có quy trình review schema khi thêm field, thay đổi DTO hoặc dependency.

**Kết luận:** **Thêm masking dữ liệu** là một phần thiết yếu của thiết kế chiến lược Java Logging. Cách vững chắc nhất là **giảm dữ liệu từ nguồn, chỉ cho phép những field đã phân loại, kiểm duyệt trước khi tạo log event và kiểm chứng đầu ra ở mọi sink**. Java 17 demo cho thấy cách làm đơn giản: allowlist, full masking/redaction, validation và fail-closed. Khi đưa vào SLF4J/Logback/JSONL, phải tiếp tục bảo vệ **MDC, Throwable, payload, collector và archive**, vì một đường log không được che có thể làm vô hiệu toàn bộ chính sách.
