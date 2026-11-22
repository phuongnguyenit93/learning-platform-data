# Rà soát nội dung log để bảo vệ quyền riêng tư trong Java

## 1. Vì sao phải rà soát nội dung log?

**Rà soát nội dung log (log content review)** là quá trình kiểm tra **thông tin nào đang được ghi**, có thực sự cần để vận hành/điều tra hay không, mức độ nhạy cảm của dữ liệu, ai nhận được nó và nó tồn tại bao lâu. Đối với ứng dụng Java, việc rà soát không dừng ở `logger.info(...)`: thông tin còn có thể đi qua formatter, appender, MDC/ThreadContext, stdout, file, hệ thống giám sát, collector, báo cáo lỗi và kho lưu trữ.

Một lời gọi log tưởng như vô hại có thể chứa password trong payload, access token trong HTTP header, email trong DTO, dữ liệu cá nhân trong stack trace hoặc query string trong URL. Khi đến hệ thống tập trung, một bản ghi có thể được sao chép sang nhiều nơi và được đọc bởi nhiều nhóm hơn dữ liệu gốc.

**Mục tiêu** là giữ đủ bằng chứng kỹ thuật/phục vụ an ninh, nhưng **không thu thập quá mức** và không biến log thành kho dữ liệu cá nhân không có quản trị.

Sau bài này, bạn có thể:
- Lập danh mục event log và phân loại field theo mục đích, độ nhạy cảm, retention và quyền truy cập.
- Nhận diện nơi dữ liệu nhạy cảm rò rỉ từ Java code, framework, HTTP, exception, MDC và appender.
- Chọn giải pháp theo thứ tự ưu tiên: **không ghi → giảm dữ liệu → chuẩn hóa/snapshot → mask hoặc pseudonymize → chặn/kiểm soát ở pipeline**.
- Kiểm tra chống **log injection** bằng allowlist/structured fields, giới hạn độ dài và encoder.
- Viết ví dụ Java 17+ chỉ log trường cho phép, và test rằng thông tin bí mật không xuất hiện.
- Thiết kế quy trình review tự động trong CI, kiểm tra dữ liệu thực tế ở collector và xử lý sự cố khi phát hiện log nhạy cảm.

## 2. Log nào đáng giữ và dữ liệu nào không nên xuất hiện?

### 2.1. Bắt đầu bằng mục đích của từng event

Thay vì hỏi “Có thể log object này không?”, hãy hỏi:
1. **Vì sao** sự kiện cần được ghi? Debug lỗi, cảnh báo an ninh, đo latency, audit hay điều tra một giao dịch?
2. **Ai** cần đọc? Developer, on-call, SOC, quản trị viên hay hệ thống cảnh báo?
3. **Trường tối thiểu** nào giúp trả lời mục đích trên?
4. **Điểm nhận nào** cần dữ liệu? Console dev, file production, SIEM hoặc collector riêng?
5. **Bao lâu** cần giữ, ai có quyền truy cập và cách xóa/ẩn danh?
6. Có cách thay thế ít nhạy cảm hơn không, như mã event, bucket lỗi, request ID ngẫu nhiên hoặc metric?

Một event chẩn đoán thường chỉ cần mã lỗi, loại hành động, kết quả, thời gian và ID tương quan. Toàn bộ HTTP request/response hoặc đối tượng người dùng hiếm khi là lựa chọn tối thiểu.

### 2.2. Bảng phân loại thực hành

| Dữ liệu | Rủi ro hoặc ví dụ | Hướng xử lý khi rà soát |
| --- | --- | --- |
| Password, OTP, PIN, access/refresh token, API key, private key | Có thể cho phép truy cập hệ thống/tài khoản | **Không ghi giá trị**; không chỉ mask vài ký tự nếu vẫn hữu ích để khai thác |
| Cookie phiên, Authorization header, connection string có credential | Có thể chứa bí mật đăng nhập | Loại bỏ hoặc thay bằng trạng thái/loại xác thực không nhạy cảm |
| Số thẻ, tài khoản, thông tin sức khỏe, giấy tờ định danh | Dữ liệu cá nhân nhạy cảm hoặc phải bảo vệ đặc biệt | Không ghi mặc định; đánh giá mục đích/tuân thủ trước mọi ngoại lệ |
| Email, số điện thoại, địa chỉ, tên, ngày sinh | Có thể nhận diện cá nhân | Hạn chế/loại bỏ; dùng ID thay thế có quản lý khi thực sự cần |
| IP, user agent, định danh thiết bị, tọa độ | Có thể nhận diện hoặc theo dõi cá nhân trong ngữ cảnh | Chỉ lưu phần phục vụ mục đích, giới hạn retention và truy cập |
| URL, query string, referrer, HTTP headers | Có thể mang token, email, mã khôi phục hoặc payload | Log route/template, method/status; lọc bỏ query/header không nằm trong allowlist |
| Raw body, DTO, `toString()` của entity | Có thể chứa mọi field kể cả field mới | **Không log nguyên object**; chọn từng field được cho phép |
| Stack trace, SQL statement, HTTP client error | Có thể lộ path, dữ liệu đầu vào, tham số hoặc header | Giữ thông tin cần debug, loại field nhạy cảm; xem cause/message của exception |
| `requestId`/`traceId` sinh độc lập | Hữu ích để tương quan bản ghi | Cho phép nếu không nhúng PII và có giới hạn truy cập/thời hạn |
| Mã sự kiện, outcome, latency bucket, status code | Thường ít nhạy cảm hơn | Ưu tiên log dạng cấu trúc với kiểu và enum được kiểm soát |

**Pseudonymization không đồng nghĩa anonymization**: mã định danh thay thế hoặc hash nhất quán vẫn có thể liên kết các sự kiện và có thể còn là dữ liệu cá nhân trong ngữ cảnh. Không tự kết luận `SHA-256(email)` là “ẩn danh” nếu email có thể bị đoán, dò theo từ điển hoặc liên kết với hệ thống khác.

Mức độ được phép xử lý dữ liệu còn phụ thuộc luật áp dụng, chính sách tổ chức, hợp đồng và mục đích cụ thể. Bài này trình bày kỹ thuật kiểm soát; không coi bất kỳ retention hoặc field nào là hợp lệ về pháp lý trong mọi hệ thống.

## 3. Những đường rò rỉ thường gặp trong Java

### 3.1. Log nguyên object hoặc request

```java
// Ví dụ mã KHÔNG nên áp dụng: object có thể chứa password/token.
LOG.info("registration={}", registrationRequest);
LOG.debug("headers={}", httpHeaders);
LOG.info("user={}", userEntity);
```

Parameterized logging giúp giảm chi phí định dạng khi mức log tắt, **không** bảo vệ dữ liệu khi mức log bật. Phương thức `toString()` của Java record, Lombok `@ToString`, DTO hoặc entity có thể tự bao gồm field nhạy cảm; field mới thêm về sau có thể vô tình xuất hiện mà không ai sửa câu log.

Cách an toàn hơn là chọn rõ field có trong **hợp đồng logging**:

```java
// Đoạn minh họa cần biến/Logger/DTO được định nghĩa trong ứng dụng.
LOG.info("event=registration_result requestId={} outcome={}",
         requestId, outcomeCode);
```

Điều kiện: `requestId` phải được tạo độc lập/kiểm tra hợp lệ, `outcomeCode` là enum hoặc mã được quản lý. Không truyền `registrationRequest` hoặc email/password vào message.

### 3.2. Header, URL và body

Các giá trị sau có thể chứa bí mật:
- `Authorization: Bearer ...`, `Cookie`, `Set-Cookie`, `X-API-Key`.
- Query string `?token=...`, `?email=...`, `?code=...`, đôi khi ngay cả path segment.
- Form/body JSON, multipart upload, nội dung file và phản hồi của đối tác.
- Query SQL cùng tham số bind, đặc biệt khi ORM/driver hoặc datasource logging được bật DEBUG/TRACE.

Trong HTTP server, nên log `method`, **route pattern** như `/users/{id}`, status, latency và correlation ID do server cấp. Đừng log toàn bộ URL rồi cố tìm/xóa một vài tham số bằng regex; tên tham số có thể thay đổi, token có thể nằm trong path và encoding có thể biến hóa.

Không bật request/response logging toàn cục trên production chỉ để chẩn đoán tạm thời. Khi thật sự cần một phần body, thiết kế danh sách field được phép, cỡ mẫu, giới hạn độ dài, thời gian bật, người phê duyệt và điểm nhận tách biệt.

### 3.3. Exception và stack trace

```java
// Mã cần xem xét vì message ngoại lệ có thể chứa giá trị người dùng.
LOG.error("failed to process request {}", request, exception);
```

Thông tin trong `exception.getMessage()` hoặc nested cause có thể chứa input, đường dẫn nội bộ, SQL hoặc URL có credential. Tuy nhiên **không nên bỏ toàn bộ exception** một cách máy móc: stack trace là thông tin quan trọng để điều tra lỗi.

Cách tiếp cận cân bằng:
- Log mã lỗi, loại lỗi và ID tương quan đã an toàn.
- Quyết định có ghi throwable/stack trace theo loại sự kiện, môi trường và mức nhạy cảm.
- Đảm bảo custom exception không đưa secret vào message ngay từ lúc tạo.
- Kiểm tra formatter/encoder có tự ghi cause chain, suppressed exceptions và context không.
- Với lỗi cần điều tra sâu, cân nhắc kênh chẩn đoán bảo mật tách biệt thay vì ném toàn bộ dữ liệu vào log thông thường.

### 3.4. MDC/ThreadContext và structured logging

SLF4J MDC hoặc Log4j 2 ThreadContext giúp gắn `requestId`, `traceId`, `tenantId`. Nhưng khi pattern có `%X` hoặc JSON layout xuất toàn bộ context, một field từng được đưa vào MDC có thể đi theo **mọi event** của request.

Ví dụ rủi ro:

```java
// Không nên lưu Authorization header trong MDC.
MDC.put("authorization", authorizationHeader);
```

Thay vào đó, chỉ thêm key/value được phê duyệt, với giới hạn độ dài và kiểm tra dữ liệu. Thu dọn context trong `finally` hoặc dùng scoped API đúng framework; tránh rò rỉ context giữa request khi dùng thread pool. Với executor/virtual thread, bảo đảm context propagation theo cơ chế thật của hệ thống; không giả định `ThreadLocal` tự hoạt động giống nhau trong mọi kịch bản.

## 4. Nguyên tắc thiết kế: allowlist thay vì chỉ blacklist

**Allowlist** là cách định nghĩa trước tập field/event được phép ghi. Mọi dữ liệu khác mặc định **không được đưa vào log**. Cách này thường an toàn hơn rà soát vô số chuỗi bằng regex để tìm dữ liệu không nên có.

Ví dụ hợp đồng cho sự kiện xác thực:

| Field | Kiểu/ràng buộc | Cho vào log? | Lý do |
| --- | --- | --- | --- |
| `event` | Enum cố định: `auth_decision` | Có | Phân loại sự kiện |
| `request_id` | ID ngẫu nhiên do server cấp, ký tự/độ dài giới hạn | Có | Correlate lỗi |
| `outcome` | `SUCCESS`, `DENIED`, `UNKNOWN` | Có | Chẩn đoán và bảo vệ an ninh |
| `email` | Định danh cá nhân | Không mặc định | Không cần cho log xác thực chung |
| `access_token` | Bí mật có thể dùng truy cập | **Không** | Nguy cơ chiếm quyền truy cập |
| `raw_client_text` | Input bên ngoài, chưa tin cậy | Không | Rò rỉ dữ liệu và log injection |
| `password` | Bí mật xác thực | **Không** | Không có lý do hợp lệ để ghi |
| `user_agent`/IP | Có thể liên quan người dùng | Chỉ khi có mục đích và policy | Không tự coi là phi nhạy cảm |

Một hệ thống có thể cần định danh tài khoản để điều tra hành vi gian lận. Khi ấy nên xem xét ID nội bộ riêng và quyền truy cập phù hợp thay vì tự động log email thô ở mọi event. Quy tắc phải được chấp thuận và kiểm thử như một phần thiết kế sự kiện.

**Gợi ý tổ chức code:** đặt một kiểu event riêng chỉ chứa field được duyệt, thay vì để module bất kỳ truyền cả DTO vào logger. Nếu phải log text tùy ý, dùng structured encoding với escaping thích hợp; để tránh log injection, không chỉ gọi `trim()` hoặc cắt chuỗi mà bỏ qua CR/LF.

## 5. Ví dụ Java 17+ độc lập: review bằng allowlist và test dữ liệu nhạy cảm

Ví dụ chỉ dùng `java.util.logging` và các API chuẩn. Input mô phỏng có email giả, token giả và văn bản chứa xuống dòng. Ta **không ghi ba trường đó**, chỉ dựng message từ các field được cho phép, và kiểm tra rằng ID không hợp lệ không thể đưa CR/LF vào bản ghi.

Tạo tệp **`LogContentReviewDemo.java`**:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogContentReviewDemo {
    record AuthAttempt(String requestId, String email,
                       String accessToken, String rawClientText,
                       String outcome) {}

    static String safeRequestId(String value) {
        return value != null && value.matches("[A-Za-z0-9_-]{1,32}")
                ? value : "invalid";
    }

    static String safeOutcome(String value) {
        return "SUCCESS".equals(value) || "DENIED".equals(value)
                ? value : "UNKNOWN";
    }

    static String safeLine(AuthAttempt attempt) {
        return "event=auth_decision request_id="
                + safeRequestId(attempt.requestId())
                + " outcome=" + safeOutcome(attempt.outcome());
    }

    public static void main(String[] args) {
        AuthAttempt input = new AuthAttempt("req_27",
                "alice@example.invalid", "top-secret",
                "bad\nWARN forged", "DENIED");

        String line = safeLine(input);
        if (!line.equals(
                "event=auth_decision request_id=req_27 outcome=DENIED")
                || line.contains("alice@")
                || line.contains("top-secret")
                || line.contains("\n")) {
            throw new AssertionError("Privacy contract failed");
        }

        AuthAttempt malicious = new AuthAttempt(
                "req_28\nERROR injected",
                input.email(), input.accessToken(),
                input.rawClientText(), "unexpected");

        String checked = safeLine(malicious);
        if (!checked.equals(
                "event=auth_decision request_id=invalid outcome=UNKNOWN")) {
            throw new AssertionError(
                    "Untrusted fields escaped allowlist");
        }

        Logger log = Logger.getAnonymousLogger();
        log.setUseParentHandlers(false);
        log.setLevel(Level.INFO);

        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " " + record.getMessage());
                }
            }

            @Override public void flush() {}
            @Override public void close() {}
        };
        sink.setLevel(Level.ALL);
        log.addHandler(sink);

        try {
            log.info(line);
            System.out.println("review_checks=PASS");
        } finally {
            log.removeHandler(sink);
            sink.close();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac LogContentReviewDemo.java
java LogContentReviewDemo
```

**Standard output xác định:**

```text
INFO event=auth_decision request_id=req_27 outcome=DENIED
review_checks=PASS
```

### Vì sao ví dụ không làm rò rỉ dữ liệu?

1. `safeLine` **không truy cập** `email`, `accessToken` hoặc `rawClientText`. Tốt hơn là không nhận chúng vào hệ thống logging thật ngay từ đầu.
2. `requestId` chỉ được giữ nếu khớp allowlist `[A-Za-z0-9_-]{1,32}`; chuỗi chứa `\n` bị thay bằng `invalid`.
3. `outcome` được chuyển thành ba giá trị hữu hạn. Input `unexpected` thành `UNKNOWN`, không được ghi nguyên văn.
4. Test khẳng định message không chứa chuỗi token/email hoặc newline, và event chứa input tấn công được dựng thành kết quả an toàn.
5. Logger/handler dùng riêng nên chương trình không cần Logback hoặc cấu hình root toàn JVM; `finally` tháo handler và đóng nó.

**Đây là ví dụ minh họa chính sách, không phải bộ lọc dữ liệu cá nhân tổng quát.** Allowlist ID trong ứng dụng thật phải đồng bộ với cách ID được sinh/nhận. Nếu `request_id` của bạn vốn chứa dữ liệu cá nhân hoặc ID có thể liên kết cá nhân, regex hợp lệ vẫn **không** bảo đảm giá trị không nhạy cảm. Chọn ID server-generated và xác minh mục đích sử dụng.

Kết quả kiểm tra ở ví dụ chạy trên một thread đồng bộ. Nếu backend thực tế dùng async, test cần chờ event đến sink bằng cơ chế có timeout hoặc flush đúng API trước khi assert bản ghi đầu cuối.

## 6. Masking, redaction, pseudonymization: khác nhau như thế nào?

| Kỹ thuật | Ví dụ khái niệm | Ưu điểm | Rủi ro/giới hạn |
| --- | --- | --- | --- |
| **Không ghi** | Chỉ ghi `auth_failed`, không ghi token | Giảm tối đa rủi ro dữ liệu | Cần thiết kế event tốt |
| **Data minimization** | Ghi mã lỗi và request ID, không log request body | Giữ thông tin đủ dùng | Phải xác định mục đích |
| **Masking** | Che một phần giá trị không được phép hiện đầy đủ | Hỗ trợ một số use case đặc thù | Phần còn lại vẫn có thể nhạy cảm; dễ bị lộ qua đường khác |
| **Redaction** | Thay toàn bộ secret bằng `[REDACTED]` | Hỗ trợ phòng vệ bổ sung | Phải nhận diện chính xác secret/field |
| **Pseudonymization** | Mã định danh ngẫu nhiên có mapping an toàn | Có thể liên kết event mà không hiện PII gốc | Mapping/khả năng liên kết vẫn cần bảo vệ |
| **Hashing** | Tạo digest cho một identifier theo policy | Dùng cho một số phép so khớp | Identifier dễ đoán có thể bị dò; hash không tự động ẩn danh |
| **Encryption** | Mã hóa payload với khóa quản lý riêng | Giảm rủi ro khi mất quyền truy cập lưu trữ | Ai giữ khóa vẫn giải mã được; không giải quyết việc thu thập dư thừa |

**Ưu tiên không ghi và chọn đúng field tại nguồn**, rồi mới đến redaction ở appender/collector. Bởi nếu lọc ở cuối pipeline, giá trị thô có thể đã nằm trong heap, queue async, console, agent buffer hoặc một appender khác.

### Vì sao regex redaction không phải lá chắn duy nhất?

Giả sử chỉ xóa những chuỗi khớp email:
- Secret có thể nằm dưới dạng URL-encoded, Base64, JSON escaped, không có dấu `@` hoặc có định dạng mới.
- Token không có cấu trúc giống email; JWT, khóa API, session ID có nhiều kiểu.
- Regex có thể tạo false negative (lọt) hoặc false positive (che nhầm), làm mất dữ liệu chẩn đoán.
- Một số loại regex tốn CPU hoặc bị lợi dụng bằng input lớn nếu thiết kế kém.

Nếu dùng bộ lọc ở pipeline, hãy có tập test fixture đa dạng và **đo false negative**; không tuyên bố “không còn PII” chỉ vì một biểu thức chính quy không tìm thấy gì.

### Hash định danh người dùng có an toàn không?

Không nên mặc định `SHA-256(email)` là anonymous: tập email/phone có thể bị thử đoán, và cùng digest qua nhiều log vẫn liên kết được hoạt động. Nếu yêu cầu liên kết được duyệt, có thể dùng mã ngẫu nhiên nội bộ hoặc cơ chế keyed pseudonymization (ví dụ HMAC với khóa riêng, rotation có kiểm soát) phù hợp; secret của HMAC không xuất hiện trong log. Hệ thống vẫn phải quản lý quyền, retention, key lifecycle và nguy cơ tái nhận diện.

## 7. Chống log injection khi có dữ liệu từ client

**Log injection** xảy ra khi dữ liệu không tin cậy làm giả ranh giới hoặc trường bản ghi. Ví dụ attacker gửi một user name chứa `\r\nERROR access granted`, rồi code nối chuỗi vào text log. Trình xem log có thể hiển thị thành một dòng lỗi giả, làm nhiễu điều tra và cảnh báo.

Ngoài CR/LF, định dạng text tự ghép có thể bị đánh lừa bởi tab, dấu `=`, dấu phân cách CSV, quote, ký tự điều khiển hoặc cấu trúc JSON không escape đúng.

Phòng vệ theo thứ tự:
1. **Không log raw user input** khi không cần; trong ví dụ ở mục 5, `rawClientText` không bao giờ được đưa vào `safeLine`.
2. Nếu phải log, **validate kiểu/ràng buộc** (enum, ID hợp lệ, giới hạn byte/độ dài) và thay giá trị không hợp lệ bằng mã an toàn.
3. Dùng structured JSON encoder/schema được bảo trì, escape chuỗi theo format, giới hạn chiều dài từng field và tổng event. Chỉ thêm key cố định thay vì cho client quyết định tên key.
4. Giữ template logging là hằng số, truyền tham số thay vì nối một phần template từ input.
5. Test CR/LF, ký tự điều khiển, quote, unicode đặc biệt, chuỗi lớn và field lồng nhau tại **điểm ghi cuối**.
6. Cấu hình viewer/dashboard để hiển thị text như text, không render HTML/script do client cung cấp như mã thực thi.

**Parameterized logging không tự chống CRLF injection.** Ví dụ `LOG.warn("bad input={}", untrusted)` là cách truyền đối số rõ hơn nối template, nhưng nếu encoder output plain text không escape ký tự xuống dòng, log vẫn có thể bị phá cấu trúc. Cần kết hợp schema và output encoding phù hợp.

## 8. Rà soát mã Java và cấu hình logging như thế nào?

### 8.1. Kiểm tra call site

Khi code review, ưu tiên tìm những mẫu sau (không nên xem grep đơn lẻ là kết luận cuối):
- `logger.info("{}", request)`, `LOG.debug("dto={}", dto)`, `System.out.println(entity)`.
- `logger.error("...", exception)` với exception message có user input.
- Serialize DTO thành JSON rồi log nguyên chuỗi.
- `MDC.put("email", ...)`, `MDC.put("token", ...)` và ThreadContext chứa field lạ.
- Log URL có query, headers, HTTP body, SQL binding parameters.
- `toString()` của entity/record và annotation tự sinh string.
- Logging ở interceptor, filter, middleware hoặc instrumentation được bật bởi config chứ không hiện rõ trong service code.

Một bảng review cho từng call site:

| Câu hỏi | Bằng chứng cần ghi |
| --- | --- |
| Sự kiện dùng để làm gì? | Mục đích chẩn đoán/an ninh/audit và người đọc |
| Field được lấy từ nguồn nào? | Constant, server-generated ID, DTO, HTTP input, DB, secret store |
| Có field nào ngoài allowlist? | Tên field, mức nhạy cảm, quyết định loại bỏ |
| Level/backend có làm ghi rộng hơn dự kiến? | Effective level, appender, MDC, layout |
| Có nhiều đích cùng nhận event không? | Console, file, collector, APM/OTel, backup |
| Dữ liệu bị giữ bao lâu? | Retention, chỉ mục, archive, export, ticket |
| Có kiểm thử với dữ liệu canary không? | Kết quả tìm trên event/JSON cuối đường |

Không cần log dữ liệu nhạy cảm thật để kiểm thử. Dùng **canary giả** có hình dạng tương tự token/email nhưng không cho phép truy cập thật.

### 8.2. Rà soát cấu hình Logback và Log4j 2

Với Logback, xem:
- `logback.xml`, `logback-test.xml` và các file cấu hình được chọn qua framework/launcher.
- Pattern như `%msg`, `%X{key}` hoặc `%X` (xuất toàn bộ MDC).
- Appender file/console/network; AsyncAppender chỉ đổi đường đi, không tự redact PII.
- Filter, encoder/layout, cấu hình level theo environment và appender bổ sung do thư viện.

Với Log4j 2, xem:
- `log4j2.xml`/`log4j2-test.xml`, template JSON, PatternLayout và cách xuất context data.
- `ThreadContext` và các field bổ sung tự động.
- AsyncLogger/AsyncAppender, tuyến filter và appender reference.
- Liệu serializer của custom message, throwable hoặc layout có đưa field không mong muốn ra output.

Với JUL, xem:
- `java.util.logging.config.file`/`LogManager`, `Handler`, `Formatter`, `Filter`.
- Các tham số `logger.log(Level, ...)` và `LogRecord` có throwable/parameters.
- Bridge giữa JUL và SLF4J khiến log đi qua backend khác hay không.

**Một filter loại token tại appender duy nhất không bảo đảm an toàn nếu cùng event cũng đi sang appender khác trước khi filter áp dụng.** Cần kiểm tra mọi tuyến nhận.

## 9. Rà soát log ở runtime và collector

Code review chỉ kiểm tra ý định; kiểm tra thực tế cho biết hệ thống đã tạo và lưu gì. Quy trình thử nghiệm an toàn:

```text
Sinh dữ liệu canary giả trong môi trường thử nghiệm
      |
      v
Gửi request/tạo exception/test event
      |
      v
Capture tại application logger/appender
      |
      v
Capture tại stdout/file/agent buffer
      |
      v
Tra cứu log ở collector và dashboard
      |
      v
Kiểm tra archive/export/backup và retention
      |
      v
So với hợp đồng event + quy tắc quyền riêng tư
```

Những nơi dễ bị bỏ sót:
- Agent APM hoặc tracing tự thu request attributes/exception message.
- HTTP client wire log hoặc access log do reverse proxy/container runtime tạo.
- Retry queue, dead-letter queue, log shipper buffer hoặc staging index.
- CI job artifacts, screenshot, bản export CSV/JSON, file đính kèm ticket.
- Log ở library/SDK tích hợp hoặc thành phần bên thứ ba.
- Development debug console và bản ghi test có dùng dữ liệu production.

Không tải log production chứa dữ liệu nhạy cảm về máy cá nhân để rà soát tùy ý. Dùng quyền được phê duyệt, môi trường bảo vệ thích hợp, công cụ quét được quản lý và kết quả tổng hợp/đã giảm nhạy cảm.

### Metrics cho kết quả review

Có thể theo dõi:
- Số call site/event schema đã rà soát và tỷ lệ được phê duyệt.
- Số field không nằm trong allowlist, theo service/backend/đích.
- Số phát hiện secret/PII canary còn lọt qua collector.
- Mức độ bao phủ test cho các event nhạy cảm; số lỗi redaction tái phát.
- Số exception/stack trace hoặc body dump cần xử lý.
- Tình trạng retention, export, quyền đọc, audit truy cập và những nơi còn bản sao.

**Cảnh báo false confidence:** “không có kết quả quét” không phải bằng chứng chắc chắn không có dữ liệu nhạy cảm. Bộ quét có thể bỏ sót encoding, loại token mới, payload nén, trường lồng nhau hoặc event hiếm gặp. Kết hợp review thiết kế, kiểm thử với canary, scan có giám sát và kiểm tra pipeline.

## 10. Kiểm thử bằng JUnit và test data giả

### 10.1. Unit test hợp đồng event

Trong JUnit 5, có thể kiểm tra trực tiếp hàm dựng chuỗi an toàn ở mục 5. Đoạn sau là ví dụ tích hợp **cần JUnit Jupiter**, không chạy độc lập bằng JDK thuần:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class LogContentReviewTest {
    @Test
    void neverIncludesPrivateFields() {
        var e = new LogContentReviewDemo.AuthAttempt(
                "req_27", "alice@example.invalid", "top-secret",
                "bad\nWARN forged", "DENIED");

        String line = LogContentReviewDemo.safeLine(e);

        assertEquals(
                "event=auth_decision request_id=req_27 outcome=DENIED",
                line);
        assertFalse(line.contains("alice@"));
        assertFalse(line.contains("top-secret"));
        assertFalse(line.contains("\n"));
    }

    @Test
    void rejectsUntrustedIdentifiers() {
        var e = new LogContentReviewDemo.AuthAttempt(
                "req\nERROR injected", "someone@example.invalid",
                "top-secret", "ignored", "UNKNOWN");

        assertEquals(
                "event=auth_decision request_id=invalid outcome=UNKNOWN",
                LogContentReviewDemo.safeLine(e));
    }
}
```

Phương thức record và `safeLine` ở mục 5 có quyền truy cập package-private; test cần nằm cùng package hoặc bạn công khai API phù hợp. Đây là test của **hợp đồng event**, chưa chứng minh backend không thêm field riêng ở layout.

### 10.2. Integration test ở appender

Với Logback hoặc Log4j 2, có thể gắn appender test bằng bộ nhớ, phát event rồi kiểm tra field cuối cùng:
- Level, message template, map MDC và exception fields.
- Không có email, token, cookie, raw body hay giá trị canary.
- JSON output parse được, không chứa field ngoài schema.
- Các character như `\r`, `\n` không tạo bản ghi giả.
- Event debug/trace tự động bật trong test không vô tình làm lộ dữ liệu.

Nếu backend async, chờ theo điều kiện có timeout (latch/poll) và xác minh worker đã nhận event. Không dùng `Thread.sleep(100)` để suy luận log luôn được flush. Khi test xong, tháo appender, reset đúng phạm vi và khôi phục MDC/level trong `finally`. Tránh sửa global root logger trong các test chạy song song.

### 10.3. Bài test chống hồi quy nên có

1. Khi DTO thêm field mới tên `passwordHash`, sự kiện allowlist **không thay đổi**.
2. Một URL chứa `?token=canary` không xuất hiện nguyên chuỗi trong log.
3. Header `Authorization` và `Cookie` không được in.
4. Exception cause chứa secret giả không rò qua formatter.
5. `MDC` không chứa giá trị email/token hoặc field không phê duyệt.
6. Input `"\nERROR forged"` không tạo một dòng log khác.
7. Cấu hình production có nhiều appender/collector vẫn tuân theo cùng chính sách.
8. Mọi file archive, backup và export phục vụ kiểm thử đều được xóa sau test theo chính sách.

## 11. Khi nào cần structured logging?

Structured logging dùng key/value có schema, ví dụ minh họa **một event hợp lệ**:

```json
{
  "event": "auth_decision",
  "request_id": "req_27",
  "outcome": "DENIED",
  "severity": "WARN"
}
```

Lợi ích:
- Người review có thể xác định rõ field nào xuất hiện, kiểu dữ liệu và trách nhiệm sở hữu.
- Dễ viết policy chỉ cho phép key cố định, giới hạn chiều dài, validate kiểu.
- Dễ parse/test và tích hợp với collector mà không dựa vào regex đọc free-form text.
- JSON encoder đúng chuẩn escape CR/LF/quote bên trong giá trị, giảm nguy cơ phá ranh giới bản ghi.

Nhưng **structured không tự động bảo mật**. Nếu bạn ghi `"authorization": "Bearer ..."` hoặc `"request": entireDto`, dữ liệu nhạy cảm vẫn bị thu thập. Và nếu định dạng JSON được ghép thủ công bằng nối chuỗi, nó có thể không escape đúng. Dùng encoder/layout đáng tin cậy, xác định schema/allowlist và test trên output thực tế.

Trong Java, có thể dùng SLF4J 2.x fluent API với `addKeyValue` hay Log4j 2 structured messages/JsonTemplateLayout tùy backend. API cung cấp trường có cấu trúc; chính ứng dụng và cấu hình output vẫn phải quyết định có nên ghi giá trị đó không.

## 12. Quyền truy cập, retention và chia sẻ log

Rà soát nội dung phải đi kèm rà soát **đường đi** và **thời gian sống**:

| Nơi lưu/đọc | Câu hỏi kiểm soát |
| --- | --- |
| File cục bộ | Owner/group/ACL có giới hạn? File và thư mục sau rotation có cùng chính sách? |
| Console/stdout | Ai xem logs container/CI? Có bị sao chép vào hệ thống chung? |
| Collector | Ai có quyền tìm kiếm, export, tạo dashboard, gọi API? |
| S3/object storage hoặc backup | Encryption, IAM, retention, bản sao, legal hold và lifecycle có được xác định? |
| SIEM/APM | Có tự bổ sung HTTP body, request metadata, exception hoặc field không duyệt? |
| Ticket/đính kèm | Ai nhận, có thể download và lưu lại? Có cơ chế xóa/redact hợp lệ không? |

Áp dụng:
- **Need-to-know** và role-based access, kết hợp audit truy cập đối với log nhạy cảm.
- Retention theo mục đích và nghĩa vụ cụ thể; phân biệt debug, operational, security/audit log.
- Encryption in transit/at rest khi thích hợp; quản lý khóa riêng.
- Tránh chia sẻ raw log qua chat/email công khai; dùng link có quyền hoặc trích đoạn đã loại dữ liệu nhạy cảm.
- Quy trình xử lý yêu cầu liên quan dữ liệu cá nhân phải xét cả bản sao, chỉ mục, export và backup; chính sách xóa/ẩn danh phụ thuộc nghĩa vụ pháp lý và khả năng hệ thống.

Không đưa ra một số ngày retention “chuẩn” cho mọi hệ thống: thời hạn thích hợp khác theo loại event, hợp đồng, yêu cầu an ninh và quy định áp dụng.

## 13. Khi phát hiện secret hoặc PII đã bị ghi

Đây là **sự cố dữ liệu**, không chỉ là lỗi format. Trình tự xử lý phụ thuộc mức nghiêm trọng và quy trình tổ chức:

1. **Xác định loại dữ liệu, nguồn phát và phạm vi**: service, thời điểm, level, appender, index, backup, export. Không lan truyền raw value trong ticket/báo cáo sự cố.
2. **Hạn chế phát sinh mới**: sửa call site/schema, tắt debug không cần thiết hoặc chặn tại điểm thu phù hợp; không xóa bừa bằng cách làm mất dấu vết điều tra.
3. Nếu là **credential còn hiệu lực**, đánh giá **thu hồi/rotate** ngay theo quy trình bảo mật. Chỉ mask log cũ không vô hiệu hóa token đã lộ.
4. **Hạn chế truy cập** các log bị ảnh hưởng, kiểm tra lịch sử truy cập/export nếu hệ thống hỗ trợ.
5. **Xử lý dữ liệu đã thu** theo chính sách và yêu cầu pháp lý: xóa/redact index, export hoặc bản sao khi được phép; tính đến backup/retention và preservation obligation.
6. Đánh giá nghĩa vụ thông báo/báo cáo với nhóm phụ trách privacy/security/legal khi cần.
7. Bổ sung test chống hồi quy, review các event tương tự và theo dõi cải thiện.

Đừng đăng nguyên token, email khách hàng hay dữ liệu đã lộ vào kênh điều tra để “chứng minh” sự cố. Dùng mã nhận diện, fingerprint an toàn hoặc bản trích đã che phù hợp, với quyền truy cập hạn chế.

## 14. Quy trình rà soát có thể áp dụng trong một sprint

### Bước 1 — Lập danh mục

Tập hợp các event theo module, loại nghiệp vụ và độ rủi ro. Chú ý authentication, payment, profile, upload, request/response, integration, exception, tracing và logging của thư viện bên thứ ba.

### Bước 2 — Phân loại field

Đối với mỗi event: chỉ rõ purpose, owner, field, nguồn tạo, kiểu, giới hạn độ dài, sensitivity, điểm nhận và retention. Đánh dấu **cấm trực tiếp** cho password, token và những bí mật khác.

### Bước 3 — Thiết kế allowlist và chuẩn hóa

Tạo template/event schema, ưu tiên ID không nhạy cảm và enum outcome. Với định danh liên kết cá nhân, chỉ sử dụng sau khi có policy phù hợp. Đối với text từ nguồn không tin cậy, dùng validation, encoding và giới hạn cỡ.

### Bước 4 — Sửa source, MDC và appender

Loại dump DTO/headers/raw body. Review throwable. Kiểm tra mọi appender, context provider, async path và interceptor. Không chỉ sửa một pattern nếu vẫn có đường khác ghi giá trị đó.

### Bước 5 — Test với canary

Sinh email/token/URL mẫu vô hại, chạy luồng thành công và thất bại, test injection và exception. Kiểm tra cùng một event ở đầu appender, stdout/file, collector và export. Đo cả false negative.

### Bước 6 — Review quyền và vòng đời

Xem quyền truy cập và bản sao lưu, thời gian giữ, dự án/tenant cùng dùng collector và khả năng chia sẻ cho bên thứ ba. Đảm bảo người dùng không có quyền không thể đọc dữ liệu đó.

### Bước 7 — Đưa vào CI và vận hành

Thêm checklist reviewer, test schema, scanner có kiểm soát, cảnh báo canary và hướng dẫn xử lý phát hiện. Kiểm tra lại khi thay DTO, dependency, layout, logging level hoặc collector.

### Mẫu bảng kiểm cuối cùng

| Kiểm tra | Tiêu chí chấp nhận |
| --- | --- |
| Có mục đích cho từng event? | Có owner, purpose và consumer rõ |
| Có field bị cấm? | Không chứa password/token/session secret/credential |
| Có data minimization? | Không dump nguyên body/headers/DTO không cần |
| Có schema/allowlist? | Key và kiểu dữ liệu đã được duyệt |
| Có chống injection? | Giá trị untrusted được validate/escape theo format |
| Có kiểm tra MDC/exception? | Không rò PII qua context hoặc cause |
| Có kiểm tra mọi sink? | File/stdout/agent/collector/export tương ứng |
| Có test tự động? | Unit + integration với canary, có kiểm tra negative |
| Có kiểm soát truy cập? | Need-to-know, audit access khi cần |
| Có retention/backup? | Thời hạn, vòng đời và cách xử lý bản sao rõ |
| Có kịch bản phản ứng? | Biết thu hồi secret, khoanh vùng và ngăn tái phát |

## 15. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| “Chỉ DEBUG mới có PII nên production an toàn” | DEBUG có thể bật tạm; INFO/error vẫn có exception/DTO | Review mọi level và runtime override |
| Chỉ quét regex email | Token và payload encoding khác có thể lọt | Allowlist + test canary + quét bổ sung |
| Log toàn bộ object rồi dùng `@ToString.Exclude` | Field mới/serializer khác vẫn có thể bị ghi | Tạo event DTO riêng chỉ có field được phép |
| Hash email rồi coi là anonymous | Digest vẫn đoán và liên kết được | Đánh giá rủi ro tái nhận diện; dùng ID/pseudonymization quản lý |
| Redact ở collector là đủ | Dữ liệu thô đã đi qua queue/agent/file trước đó | Loại/minimize ngay tại nguồn |
| Chỉ kiểm tra file, bỏ qua MDC | Layout có thể xuất mọi context | Review MDC/ThreadContext và structured attributes |
| Dùng placeholder rồi tin rằng chống CRLF | Plain-text encoder vẫn có thể giữ xuống dòng | Structured escaping + validation |
| Log mọi exception message | Cause có thể chứa input và bí mật | Kiểm tra nguồn exception, thiết kế error taxonomy |
| Copy nguyên log vào ticket/chat | Mở rộng số người có thể đọc và thời gian lưu | Trích an toàn hoặc liên kết có kiểm soát |
| Chỉ review source, không kiểm tra collector | Interceptor, agent, sidecar có thể tự thu thêm | Integration test đầu cuối và inventory |
| Bỏ log audit để “đảm bảo privacy” | Mất dấu vết an ninh bắt buộc | Thiết kế audit tối thiểu, đúng quyền và retention |
| Dùng production data để test | Tạo bản sao nhạy cảm mới | Dùng canary giả, dữ liệu kiểm thử |

## 16. Bài tập thực hành

1. Chạy `LogContentReviewDemo`. Giải thích vì sao email và token không xuất hiện, tại sao request ID chứa xuống dòng bị đổi thành `invalid`.
2. Thêm field `passwordHash` vào record input. Giữ nguyên `safeLine` và xác minh output **không thay đổi**; đây là lợi ích của allowlist.
3. Viết test JUnit cho các giá trị `requestId`: rỗng, quá dài, chứa `\r\n`, dấu quote, Unicode tùy ý, ID hợp lệ; xác minh không phá cấu trúc.
4. Tìm năm call site logging trong một ứng dụng demo; phân loại event, field, nguồn dữ liệu và quyết định giữ/bỏ/mask.
5. Dùng appender test thu Logback `ILoggingEvent`/Log4j event và kiểm tra MDC, throwable, message; thử một canary token giả.
6. Tạo structured JSON event với encoder thực. Gửi chuỗi chứa xuống dòng và dấu quote, xác minh JSON parse được và không tạo event giả.
7. Mô phỏng request có query `?code=canary` và kiểm tra access log của HTTP server/proxy lẫn application log. Giảm log về route pattern và status.
8. Tạo checklist collector: ai đọc được, retention bao lâu, có bản copy ở index/export/backup nào; giải thích vì sao chỉ kiểm tra `application.log` là thiếu.

## 17. Ghi nhớ

- **Rà soát nội dung log** là kiểm soát **field, mục đích, mức nhạy cảm, đường đi, người đọc và thời gian giữ** — không chỉ tìm chuỗi password trong source.
- Ưu tiên **không ghi** dữ liệu nhạy cảm hoặc **allowlist** event fields trước khi dùng regex masking/redaction ở pipeline.
- Placeholder và structured logging không tự bảo đảm riêng tư; encoder, schema và dữ liệu đầu vào phải được kiểm soát.
- Test với dữ liệu canary và các tình huống CR/LF, exception, MDC, nhiều appender và async.
- Rà soát cả file, stdout, collector, dashboard, export và backup. Xử lý credential đã lộ bằng thu hồi/rotate và quy trình sự cố phù hợp.
- Giữ log phục vụ an ninh/audit ở mức cần thiết nhưng áp dụng quyền truy cập, retention và cơ chế bảo vệ theo chính sách.

### Tài liệu tham khảo

- OWASP — *Logging Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP — *Log Injection*: https://owasp.org/www-community/attacks/Log_Injection
- OWASP — *Implement Security Logging and Monitoring*: https://devguide.owasp.org/en/04-design/02-web-app-checklist/09-logging-monitoring/
- Oracle Java 17 — `java.util.logging.Logger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle Java 17 — `java.util.logging.LogRecord`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html
