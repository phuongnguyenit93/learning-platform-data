# Không kiểm soát PII trong Java Logging: anti-pattern, hậu quả và cách phòng tránh

## 1. Bản chất của anti-pattern

**Không kiểm soát PII (Personally Identifiable Information)** trong logging là tình trạng ứng dụng ghi hoặc để các thành phần trong pipeline ghi **dữ liệu có thể nhận diện một cá nhân** mà không có mục đích, giới hạn, cơ chế bảo vệ và thời hạn lưu giữ phù hợp. Lỗi này xuất hiện không chỉ khi developer cố tình ghi email hoặc số điện thoại, mà còn khi một object, HTTP request, exception, MDC, framework hoặc thư viện tự phát dữ liệu vào log.

Ví dụ nguy hiểm:

~~~java
logger.info("Login input: {}", loginRequest);
logger.warn("Authentication failed: user={} password={}",
        email, password);
logger.debug("HTTP headers: {}", request.getHeaderNames());
~~~

Đây là **các đoạn minh họa tích hợp**, không phải chương trình Java độc lập. Ở dòng đầu, \`loginRequest.toString()\` có thể chứa email, mật khẩu hoặc số giấy tờ tùy DTO. Dòng thứ hai trực tiếp ghi credential. Dòng thứ ba hiển thị danh sách tên header, không phải giá trị header, nhưng nếu được sửa thành dump nguyên header map, Authorization hoặc Cookie có thể bị lộ.

Một thiết kế an toàn hơn là tạo **event có schema cho phép**:

~~~java
logger.warn("event={} requestId={} outcome={}",
        "login_rejected", validatedRequestId, "DENIED");
~~~

Đây cũng là đoạn tích hợp, đòi hỏi SLF4J hoặc API logging tương thích. Chỉ log mã sự kiện, kết quả và requestId được cấp/kiểm tra phù hợp. Không phải mọi thông tin nhận diện đều cần xuất ra để debug.

Vấn đề cốt lõi không phải mức log DEBUG/INFO/ERROR: **dòng ERROR chứa token vẫn là rò rỉ**. Bật DEBUG tạm thời ở production chỉ khiến đường rò có thể mở rộng nhanh hơn.

## 2. PII là gì trong bối cảnh log?

PII là thông tin có thể nhận diện một người **trực tiếp hoặc khi kết hợp với thông tin khác**. Khái niệm và nghĩa vụ pháp lý cụ thể tùy khu vực, chính sách tổ chức và mục đích xử lý; không có một danh sách trường cố định phù hợp mọi hệ thống.

| Nhóm | Ví dụ | Rủi ro trong logs |
| --- | --- | --- |
| Định danh trực tiếp | Họ tên, email, số điện thoại, số giấy tờ | Nhận diện cá nhân, lộ liên hệ |
| Định danh trực tuyến | IP, device ID, cookie ID, advertising ID | Theo dõi hành vi, liên kết nhiều phiên |
| Định danh nghiệp vụ | customerId, accountId, loyaltyId | Có thể liên kết tới hồ sơ khách hàng |
| Thông tin nhạy cảm | Sức khỏe, tài chính, sinh trắc, vị trí chính xác | Tác động riêng tư cao |
| Nội dung do người dùng tạo | Bình luận, tệp đính kèm, tìm kiếm, địa chỉ giao hàng | Có thể chứa PII không theo schema |
| Metadata tương quan | requestId, traceId, sessionRef, timestamp | Có thể hỗ trợ tái nhận diện khi liên kết nhiều nguồn |
| Thông tin thanh toán | PAN, tài khoản ngân hàng và các định danh thanh toán | Rủi ro gian lận và nghĩa vụ kiểm soát chuyên biệt |
| Dữ liệu xác thực | Password, access/refresh token, API key, session cookie | Không phải trường nào cũng là PII về mặt phân loại, nhưng đều là **secret** cần tránh log |

**Secret và PII chồng lấp nhưng không đồng nghĩa.** Một API key của service có thể không nhận diện cá nhân nhưng vẫn cực kỳ nguy hiểm khi lộ. Vì vậy policy logging phải bảo vệ **cả PII lẫn credential, bí mật nghiệp vụ và dữ liệu có tính nhạy cảm khác**.

Ví dụ một requestId dạng UUID do server sinh có thể an toàn hơn email trong log, nhưng nếu ID đó trỏ tới hồ sơ khách hàng và được giữ lâu, nó **không tự trở thành dữ liệu ẩn danh**.

## 3. PII rò ra bằng những con đường nào?

Mô hình một pipeline:

~~~text
HTTP request / message / database row / external API
                    |
                    v
        Java object + application code
                    |
         +----------+-----------+
         |          |           |
         v          v           v
     logger args   MDC       Throwable/toString
         |          |           |
         +----------+-----------+
                    |
                    v
         SLF4J / JUL / Log4j 2
                    |
                    v
        Encoder / Appender / stdout
                    |
                    v
       Agent / Collector / Transport
                    |
                    v
     Index / Dashboard / SIEM / Export
                    |
                    v
              Backup / Archive
~~~

Các nguồn điển hình:

1. **DTO/entity.toString()** do Lombok \`@Data\`, IDE generator hoặc record tự tạo, làm lộ nhiều field ngoài dự định.
2. **Parameterized logging** với object thô; cơ chế placeholder chỉ định dạng argument, không tự redact.
3. **Raw request/response body**, query string, URL có token hoặc signed URL.
4. **HTTP headers** như Authorization, Cookie, X-Api-Key, Set-Cookie.
5. **MDC** chứa email/user object hoặc customerId; mọi log line có thể bị nhân thêm dữ liệu đó.
6. **Exception message**, nested causes, SQL exception hoặc HTTP client error có thể mang URL/body/bind values.
7. **SQL/ORM bind parameter logging**, đặc biệt khi bật TRACE cho thư viện.
8. **Messaging**: Kafka/RabbitMQ payload, dead-letter, deserialization error, retry debug logs.
9. **Access logs** của proxy, ingress, API gateway dù Java code không log.
10. **Agent/collector enrichment**, trace attributes, APM error capture và monitoring SDK.
11. **Support workflow**: copy/paste log vào ticket, email, chat, tài liệu hoặc công cụ AI mà không có policy.

Cần kiểm tra **toàn bộ tuyến**. Chỉ sửa một câu \`logger.info\` không đảm bảo HTTP wire logger hoặc exception reporter ngừng xuất dữ liệu.

## 4. Hậu quả khi PII vào logging pipeline

Một dòng PII có thể bị sao chép tới nhiều nơi hơn dữ liệu nghiệp vụ gốc:

| Tác động | Tình huống minh họa |
| --- | --- |
| Rò rỉ riêng tư | Người vận hành không có quyền dữ liệu khách hàng đọc được email/địa chỉ từ logs |
| Mở rộng phạm vi truy cập | Developer có quyền dashboard nhưng không được truy cập production database |
| Lan truyền sang nhà cung cấp | Logs được chuyển tới managed observability/SIEM ngoài vùng bảo vệ ban đầu |
| Khó xóa dữ liệu | Bản sao nằm trong index, snapshots, archive, export hoặc laptop |
| Duy trì bí mật đã lộ | Credential ghi vào log vẫn có hiệu lực cho tới khi rotate/revoke |
| Tái nhận diện | Nhiều field tưởng là vô hại kết hợp thành hồ sơ hành vi |
| Tăng chi phí và giảm signal | Raw payload lớn khiến index, retention và điều tra kém hiệu quả |
| Tăng blast radius | Một leak của log storage có thể bao gồm dữ liệu từ nhiều service/tenant |

Đừng đánh đồng **log được mã hóa khi truyền** với việc nó không chứa PII. TLS bảo vệ trên đường truyền; người có quyền backend, archive, support export hoặc key có thể vẫn đọc nội dung.

PII bị ghi vào một **audit log bất biến/WORM** còn khó sửa hơn. Khi thiết kế, nên ngăn dữ liệu không cần thiết đi vào vùng lưu trữ có retention lock ngay từ nguồn.

## 5. Nguyên tắc an toàn: không ghi là tốt nhất

Thứ tự ưu tiên nên là:

1. **Không log những trường không cần thiết.**
2. Chỉ ghi **schema allowlist** với eventCode, outcome, service, elapsedMs, errorCode, requestId phù hợp.
3. **Validate** các ID kỹ thuật trước khi đưa vào event.
4. Khi cần thông tin về trường nhạy cảm, ghi **presence/status** hoặc **marker redaction** thay vì raw value.
5. Dùng structured encoder, giới hạn độ dài và output escaping đúng format.
6. Áp một lớp **filter/redaction ở collector** để phòng vệ thêm, không xem đó là tuyến bảo vệ duy nhất.
7. Tách quyền truy cập, retention, monitoring và incident response cho toàn bộ hệ thống log.

Ví dụ thay vì:

~~~java
logger.error("Payment failed for {}", paymentRequest);
~~~

hãy ghi:

~~~java
logger.error("event={} paymentAttemptId={} errorCode={}",
        "payment_failed", validatedAttemptId, "CARD_DECLINED");
~~~

Nếu cần xem request body để điều tra một lỗi phức tạp, nên có **kênh evidence được kiểm soát, thời hạn giữ và phê duyệt phù hợp**, không tạo thói quen dump tất cả body ở ERROR.

**Không cố giữ “4 ký tự đầu của token” cho tiện debug.** Partial masking credential thường tạo thêm khả năng đối chiếu bí mật; với nhiều trường nên omit toàn bộ.

## 6. Phân loại field và hợp đồng dữ liệu log

Một schema logging có thể dùng ba nhóm quyết định:

| Nhóm | Ví dụ | Chính sách |
| --- | --- | --- |
| **Allowed** | eventCode, outcome, errorCode, durationMs, serviceVersion | Ghi khi có ích và được chuẩn hóa |
| **Conditional** | accountRef, IP, deviceRef, tenantRef, error details | Chỉ dùng khi mục đích, quyền, retention đã xác định |
| **Forbidden in general logs** | password, access token, session cookie, CVV, private key, raw body nhạy cảm | Không ghi nội dung gốc |

**Danh mục conditional không phải mặc định an toàn**. Một IP có thể là personal data theo ngữ cảnh; một customerRef có thể nhận diện người dùng qua hệ thống CRM. Cần data owner/privacy/security review khi schema mới được bổ sung.

Một registry event có thể mô tả:

~~~yaml
event: login_rejected
schemaVersion: 1
allowedFields:
  - eventCode
  - requestId
  - outcome
  - reasonCode
forbiddenFields:
  - password
  - authorization
  - sessionCookie
  - rawRequestBody
retentionClass: operational
~~~

Đây là **YAML minh họa chính sách**, không phải tính năng tự động của Logback hoặc một chuẩn schema chính thức. Chính sách chỉ hiệu quả nếu được triển khai trong code, encoder, code review và tests.

Khi một event mới cần thêm field, nên hỏi: **điều tra sự cố nào yêu cầu field này, dữ liệu có thể xác định ai, và giữ trong bao lâu?** Tránh thêm field tự do chỉ vì “biết đâu sau này cần”.

## 7. Anti-pattern: log toàn bộ object và toString()

Trong Java, một DTO như sau có thể rò dữ liệu nếu logger format object:

~~~java
record Registration(String email, String phone,
                    String password, String referralCode) {}

Registration registration = /* object từ request */;
logger.info("register={}", registration);
~~~

Đây là **đoạn tích hợp minh họa**, không phải file Java hoàn chỉnh. Với Java record, \`toString()\` tạo biểu diễn gồm tên component và giá trị theo implementation record; mật khẩu có thể xuất hiện ở chuỗi log. DTO dùng Lombok \`@Data\`, \`@ToString\` hoặc entity được generate thường có nguy cơ tương tự.

**Không tin rằng chỉ override toString() là đủ bảo vệ**: object có thể bị JSON serialize, exception serialize hoặc logger structured argument đọc field trực tiếp. Tuy vậy, tránh đưa secret vào toString vẫn là hàng rào quan trọng.

Thay vì log object:

~~~java
logger.info("event={} requestId={} validationResult={}",
        "registration_submitted", validatedRequestId, "ACCEPTED");
~~~

Đừng dùng \`logger.debug("{}", object)\` chỉ vì DEBUG mặc định bị tắt. Môi trường staging/production có thể bật DEBUG khi incident; lazy formatting của logging API cũng không phải cơ chế privacy.

## 8. Anti-pattern: HTTP body, headers và URL

Các vị trí dễ lộ:

~~~text
POST /login
Authorization: Bearer <secret>
Cookie: session=<secret>
Content-Type: application/json

{"email":"alice@example.test","password":"<secret>"}
~~~

Đây là **payload giả lập** dùng để minh họa.

Những câu lệnh nguy hiểm:

~~~java
logger.debug("request body: {}", body);
logger.info("request URI: {}", request.getRequestURI());
logger.info("query: {}", request.getQueryString());
logger.debug("Authorization={}", request.getHeader("Authorization"));
~~~

Các dòng phụ thuộc servlet framework. \`getRequestURI()\` thường không bao gồm query string theo servlet API, nhưng URI **vẫn có thể chứa định danh trong path**; \`getQueryString()\` có thể chứa email, session key hoặc signed token. Đừng gom mọi trường URL thành an toàn.

Thay thế bằng:

- Route template: \`/orders/{orderId}\` thay vì full URI/raw path có PII.
- HTTP method, status code, latency, errorCode.
- **Request body size/schema version** khi cần, không payload raw.
- Cờ **credentialPresent** khi nó có mục đích kiểm soát và được phê duyệt, không value.
- Chỉ một số header đã được **allowlist**, như requestId đã validate.

**Web server, reverse proxy, gateway và service mesh** cũng có access/wire logs riêng. Kiểm tra chúng song song với Java code.

## 9. Anti-pattern: MDC chứa PII

MDC (Mapped Diagnostic Context) được dùng rộng rãi để gắn requestId và traceId. Nhưng nếu code:

~~~java
MDC.put("email", customerEmail);
MDC.put("customerProfile", customer.toString());
~~~

thì encoder có thể xuất toàn bộ MDC vào **mọi dòng log** của request. Một email duy nhất có thể nhân thành hàng trăm bản ghi, làm tăng rủi ro và chi phí.

Thiết kế phù hợp hơn:

~~~java
String previous = MDC.get("requestId");
try {
    MDC.put("requestId", validatedRequestId);
    service.process();
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
~~~

Đây là đoạn tích hợp cần SLF4J và các biến \`validatedRequestId\`, \`service\` được ứng dụng cung cấp. **validatedRequestId phải thực sự được tạo/kiểm tra**, không chỉ mang tên như vậy.

Cần bảo vệ hai mặt:

1. **Nội dung MDC:** chỉ field cho phép, không raw PII/secret.
2. **Vòng đời MDC:** restore/remove trong finally, kể cả khi exception; context không được rò từ request A sang request B qua thread pool.

Nếu một wrapper chỉ sở hữu key requestId, đừng gọi MDC.clear() và xóa cả traceId do framework khác quản lý. Với CompletableFuture, executor hoặc message consumers, dùng capture/activate/restore context đúng boundary; MDC thường không tự lan truyền giữa threads.

## 10. Anti-pattern: exception và stack trace mang dữ liệu riêng tư

Một stack trace hữu ích cho debug nhưng có thể đi kèm message nhạy cảm:

~~~text
java.lang.IllegalArgumentException:
  Cannot process request for alice@example.test?token=<secret>
    at example.PaymentService.execute(PaymentService.java:87)
~~~

Dòng này chỉ minh họa. Exception message có thể đến từ HTTP client, ORM, parser, database, thư viện thứ ba hoặc input do user kiểm soát. \`Throwable.getMessage()\`, nested causes, suppressed exceptions và structured error capture đều cần review.

Ví dụ nguy hiểm:

~~~java
logger.error("Request failed: {}", exception.getMessage());
logger.error("Could not authenticate user={} token={}",
        email, authorizationHeader, exception);
~~~

**Không nên áp quy tắc “luôn bỏ stack trace” một cách máy móc.** Stack location, exception type và cause rất có giá trị khi xử lý sự cố. Giải pháp là **không đưa secret vào exception message từ nguồn**, ghi eventCode, exceptionType, traceId đã validate và cấu hình formatter/sink có policy cho nội dung Throwable.

Ví dụ:

~~~java
logger.error("event={} requestId={} exceptionType={}",
        "request_failed", validatedRequestId,
        exception.getClass().getSimpleName());
~~~

Đây là cách giữ phần metadata lỗi nhưng không truyền Throwable; vì vậy có thể mất stack trace. Nếu cần stack trace để điều tra, phải lựa chọn tuyến bảo vệ/formatter phù hợp thay vì giả định line trên thay thế toàn bộ observability.

## 11. Anti-pattern: SQL/ORM, messaging và SDK bên thứ ba

### JDBC/ORM

Khi bật DEBUG/TRACE SQL hoặc bind parameters ở Hibernate/JDBC, values có thể gồm email, địa chỉ, token, thông tin tài chính. Dù app logger không hề dùng biến password, một thư viện vẫn có thể ghi nó.

Ưu tiên:

- Query fingerprint/identifier và thời gian thực thi.
- SQLState hoặc exception class theo policy.
- Connection pool metrics thay cho dump SQL bind parameters.
- Chỉ bật diagnostic logging có giới hạn về scope và thời gian.

### Message broker

Log raw Kafka/RabbitMQ payload khi retry, deserialization failure hoặc DLQ có thể đưa PII vào sink khác. Sử dụng messageId/eventId, topic/queue, partition/offset, attemptNo, outcome/errorCode, payloadSchemaVersion; không mặc định in toàn bộ message.

### Third-party SDK

Authentication, payment, email, HTTP client, APM và tracing SDK có thể bật wire/debug logs. Một bản nâng cấp dependency hoặc đổi config production có thể mở ra nguồn PII mới. Cần **inventory loggers và kiểm thử regression** khi thêm SDK.

**Không chỉ review code logger của đội mình**. Privacy policy phải áp cả module do framework và nhà cung cấp vận hành.

## 12. Java 17 độc lập: tạo event an toàn theo allowlist

Ví dụ sau dùng **java.util.logging (JUL)** có sẵn trong JDK 17. Nó nhận một object chứa dữ liệu giả lập nhạy cảm, nhưng chỉ đưa **event code, requestId đã validate và outcome** vào log. Một custom Handler in ra mỗi event theo format ổn định để người học kiểm tra stdout.

Tạo file **PiiLoggingDemo.java**:

~~~java
import java.util.Locale;
import java.util.regex.Pattern;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class PiiLoggingDemo {
    private static final Pattern REQUEST_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    enum EventCode { LOGIN_REJECTED }
    enum Outcome { DENIED }

    record LoginInput(String requestId, String email,
                      String authorization, String freeText) {}

    static final class LineHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                System.out.println(record.getLevel().getName()
                        + " " + record.getMessage());
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    private static String safeRequestId(String raw) {
        return raw != null && REQUEST_ID.matcher(raw).matches()
                ? raw : "invalid";
    }

    private static String safeEvent(EventCode event,
                                    LoginInput input,
                                    Outcome outcome) {
        return "event=" + event.name().toLowerCase(Locale.ROOT)
                + " requestId=" + safeRequestId(input.requestId())
                + " outcome=" + outcome.name().toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        LoginInput input = new LoginInput(
                "req-42",
                "alice@example.test",
                "Bearer demo-access-token",
                "Please contact my private address");
        LoginInput forgedId = new LoginInput(
                "req-43\r\nINFO fake=ok",
                input.email(), input.authorization(), input.freeText());

        String first = safeEvent(
                EventCode.LOGIN_REJECTED, input, Outcome.DENIED);
        String second = safeEvent(
                EventCode.LOGIN_REJECTED, forgedId, Outcome.DENIED);

        Logger logger = Logger.getLogger("pii.logging.demo");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        LineHandler handler = new LineHandler();
        handler.setLevel(Level.INFO);
        logger.addHandler(handler);
        try {
            logger.log(Level.INFO, first);
            logger.log(Level.INFO, second);
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        String combined = first + "|" + second;
        boolean piiAbsent =
                !combined.contains(input.email())
                && !combined.contains(input.authorization())
                && !combined.contains(input.freeText());
        boolean singleLine =
                !combined.contains("\r") && !combined.contains("\n");

        System.out.println("piiAbsent=" + piiAbsent);
        System.out.println("singleLine=" + singleLine);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PiiLoggingDemo.java
java PiiLoggingDemo
~~~

**Stdout chính xác**:

~~~text
INFO event=login_rejected requestId=req-42 outcome=denied
INFO event=login_rejected requestId=invalid outcome=denied
piiAbsent=true
singleLine=true
~~~

### Phân tích ví dụ

1. \`LoginInput\` có email, Authorization và freeText giả, nhưng \`safeEvent\` **không bao giờ nối ba giá trị này** vào log message.
2. \`EventCode\` và \`Outcome\` là enums, tránh lấy tên sự kiện từ raw user input.
3. RequestId được kiểm tra bằng regex hữu hạn; chuỗi chứa CR/LF bị chuyển thành \`invalid\`, tránh giả mạo dòng log trong ví dụ.
4. JUL \`Logger\` và \`LineHandler\` được cấu hình không truyền event lên parent handlers, nên không có console log mặc định thừa ngoài các dòng đã nêu.
5. **piiAbsent=true** chỉ chứng minh ba dữ liệu giả được đưa vào ví dụ không xuất hiện trong hai dòng output. Nó **không chứng minh** mọi hệ thống tự phát hiện được mọi PII.
6. **singleLine=true** chỉ kiểm tra hai chuỗi event được tạo trong chương trình, không chứng minh toàn bộ đường thu log không có log forging.
7. \`logger.log(Level.INFO, first)\` minh họa use-case đơn giản; trong hệ thống thật nên dùng structured logging API/encoder và test sink thực.
8. Dữ liệu nhạy cảm vẫn tồn tại trong bộ nhớ ứng dụng, và phương thức \`safeEvent\` không loại bỏ nó ở nguồn request. **Data minimization trong log không phải là xóa dữ liệu nghiệp vụ**.

Các giá trị \`alice@example.test\` và \`demo-access-token\` chỉ là dữ liệu thử nghiệm; tuyệt đối không dùng token production để kiểm tra logging.

## 13. Tránh phụ thuộc vào regex redaction toàn cục

Một anti-pattern khác là **ghi mọi dữ liệu rồi dùng một regex khổng lồ để che ở cuối pipeline**.

Ví dụ tưởng như an toàn:

~~~text
message="customer alice@example.test called from +00-000"
regex masks patterns matching email and phone
~~~

Những rủi ro:

- Một giá trị có thể được URL-encoded, base64-encoded, split qua nhiều fields hoặc nằm trong JSON nested.
- PII có format địa phương, Unicode, biến thể tên key và văn bản tự do.
- Regex có thể bỏ sót hoặc **false positive** làm mất dữ liệu chẩn đoán quan trọng.
- Nếu redaction chạy ở collector thì raw secret **đã qua stdout, file, agent spool và network**.
- Exception stack trace có thể bypass filter chỉ áp cho %msg.
- Regex kém tối ưu gây CPU overhead hoặc backtracking khi gặp payload dài.
- Khi schema mới thêm trường PII, regex cũ không biết field đó.

Một chính sách **schema allowlist trước khi tạo event** dễ kiểm chứng hơn. Regex/field redaction ở encoder/collector vẫn hữu ích như **lớp phòng vệ thứ hai**, đặc biệt với thư viện ngoài, nhưng không phải giải pháp duy nhất.

**Quan trọng:** JSON escaping, placeholder \`{}\` của SLF4J và URL encoding **không đồng nghĩa redaction**. Chúng xử lý định dạng/transport, không quyết định quyền được lộ dữ liệu.

## 14. Redaction, masking, hashing, HMAC và tokenization

Các thuật ngữ cần phân biệt:

| Phương pháp | Ví dụ | Giới hạn |
| --- | --- | --- |
| **Omission** | Không có trường email trong log | Ưu tiên khi không cần dữ liệu |
| **Full redaction** | email=[REDACTED] | Marker có thể vẫn tiết lộ trường xuất hiện |
| **Masking** | phone=******1234 | Phần còn lại có thể giúp tái nhận diện |
| **Hash không khóa** | SHA-256(email) | Email/phone dễ dictionary attack |
| **HMAC có khóa** | HMAC(key, accountRef) | Cần quản lý khóa, vẫn có thể linkable |
| **Tokenization** | customerRef=tkn-xyz | Mapping token–định danh cần quyền/retention |
| **Encryption** | ciphertext được lưu và có thể giải mã | Bảo mật lưu/truyền, không tự là redaction |
| **Aggregation** | số yêu cầu lỗi theo region | Có thể giảm rủi ro nếu nhóm không quá nhỏ |

**Hash PII rồi tuyên bố dữ liệu “ẩn danh tuyệt đối” là sai.** Với miền nhỏ như số điện thoại/email, attacker có thể dựng bảng ứng viên và so digest. HMAC với key bí mật giảm một số kiểu đoán nhưng vẫn tạo một giá trị có thể dùng để liên kết hoạt động người dùng; cần đánh giá theo mục đích, chính sách và quyền truy cập.

Không tự triển khai thuật toán crypto để “mã hóa ID cho đẹp”. Nếu correlation giữa logs thực sự cần định danh, cân nhắc opaque random ID hoặc token được quản lý và chỉ giữ mapping ở hệ thống có quyền chặt chẽ.

**Điểm quyết định là cần giữ gì để điều tra**, không phải có thể biến mọi field thành dạng nhìn ít giống PII hay không.

## 15. Structured logging và giới hạn event schema

Một event có cấu trúc giúp tránh rò PII do text dump tùy ý:

~~~json
{
  "timestamp": "2026-11-10T03:30:00Z",
  "level": "WARN",
  "service": "auth-service",
  "eventCode": "LOGIN_REJECTED",
  "requestId": "req-42",
  "outcome": "DENIED",
  "reasonCode": "INVALID_CREDENTIALS"
}
~~~

Đây là **JSON minh họa**, không phải output tự động của JUL/Logback. JSON serializer chuẩn chỉ giúp escape đúng. Một event JSON chứa \`"email":"alice@example.test"\` vẫn lộ PII nếu field không cần thiết.

Khuyến nghị:

- Key names thuộc **schema quản lý tập trung**, không nhận key tùy ý từ client.
- \`eventCode\`, \`reasonCode\`, \`outcome\` dùng enum/allowlist để hạn chế cardinality và input không tin cậy.
- \`requestId\`/traceId được validate, có nguồn đáng tin và lifespan phù hợp.
- \`durationMs\`, HTTP status, dependency name, error class được ghi khi cần.
- Không thêm field \`payload\`, \`userObject\`, \`headers\`, \`debugContext\` với object thô.
- Nếu schema có field conditional chứa PII, phân quyền, retention và sampling phải được thiết kế riêng.

**Không dùng message string duy nhất để quyết định alert.** Alert nên dựa trên eventCode/errorCode ổn định, giúp vận hành không phải giữ dữ liệu cá nhân trong text để tìm sự cố.

## 16. Cấu hình SLF4J/Logback và quyền riêng tư

SLF4J là logging facade; Logback là một backend thường dùng. Cần kiểm tra encoder/appender cụ thể:

- Pattern có \`%X\` hoặc xuất **toàn MDC map** hay không?
- Pattern có \`%msg\`, \`%ex\` hoặc throwable converter nào, có filter/redaction bao phủ không?
- JSON encoder có serialize structured arguments, markers, key-value pairs ngoài message?
- Appender nào đi ra console, rolling file, async queue, network?
- Có logger riêng cho security/audit logs và quyền riêng tư khác?
- Khi bật DEBUG/TRACE, thư viện có ghi headers/body/SQL bind parameters không?
- Agent/collector có thêm attributes từ environment hoặc request context không?

Ví dụ pattern Logback minh họa:

~~~text
%d{ISO8601} %-5level service=auth request=%X{requestId} event=%msg%n
~~~

Pattern chỉ xuất requestId nếu MDC có key này. Nó **không tự validate requestId**, không tự redact field trong \`%msg\` và không bảo vệ Throwable đi qua provider.

Khi phát triển logging wrapper, nên tránh API nhận \`Object payload\` tự do hoặc \`Map<String,Object>\` không ràng buộc. Có thể tạo **typed event** chỉ nhận safe fields và test API này. Tuy nhiên wrapper không bao phủ các lời gọi logger trực tiếp từ thư viện bên ngoài; cần policy/lint/review bổ sung.

## 17. Log level, debug mode và sự cố production

Một tình huống phổ biến:

1. Service lỗi ở production, bật DEBUG để điều tra.
2. HTTP client hoặc ORM bắt đầu ghi body/headers/bind values.
3. Log collector tiếp nhận lượng lớn PII/credential.
4. Sau sự cố, trả INFO nhưng **bản log đã lộ vẫn còn trong backend/archive**.

Vì vậy bật verbose logging phải có:

- Owner và lý do cụ thể.
- Scope hẹp theo service, logger name, instance hoặc time window.
- Quy định các logger **không bao giờ bật** ở production khi có nguy cơ lộ payload.
- Cơ chế tự hết hạn/khôi phục cấu hình nếu có.
- Monitoring tăng volume, disk usage, collector drop và chi phí.
- Audit việc thay đổi log level/cấu hình.
- Kiểm tra không có secret được phát trong canary tests.

**Giảm level từ DEBUG sang INFO chỉ giảm tương lai**, không xử lý dữ liệu đã bị ghi. Với PII rò qua ERROR, đổi level còn có thể che nguyên nhân mà không khắc phục leak.

## 18. Security boundary: source, appender, agent, collector và backend

Các lớp cần phối hợp:

| Lớp | Nên làm | Không thể thay thế |
| --- | --- | --- |
| Java business code | Tránh tạo event có PII, chọn field allowlist | Không bao phủ thư viện/framework nếu chưa kiểm |
| Logging wrapper/encoder | Cấu trúc hóa field, redaction theo schema | Không tự quyết định ý nghĩa của dữ liệu không biết |
| Local appender/stdout/file | Tránh dump raw secret, output escaping | Không thay quyền truy cập local host |
| Host agent | Parse/filter/enrich bổ sung, buffer và TLS | Raw data đã có thể nằm trên disk |
| Collector/gateway | Redaction lớp hai, route theo classification | Không xóa được bản đã sao chép upstream |
| Search/dashboard | RBAC, field-level controls, retention | UI masking không xóa dữ liệu gốc |
| Backup/archive/export | Encryption, access logs, lifecycle và deletion | Không tự phân loại field trước ingest |

**Không chọn duy nhất dashboard masking để gọi là “đã redact”**. Một export JSON, API query, support snapshot hoặc backup vẫn có thể chứa raw email/token.

Các processor ở nhiều lớp phải có test với **cùng một bộ canary data**, đồng thời phân biệt event có field đã được chặn từ source với event bị che muộn ở collector. Cần biết chính xác PII xuất hiện lần đầu tại đâu.

## 19. Retention, quyền xem và chính sách pháp lý

Một hệ thống log có kiểm soát cần trả lời:

- Những vai trò nào được xem log mức DEBUG/INFO/ERROR, audit và security?
- Những trường nào chỉ được xem ở môi trường được bảo vệ?
- Data có được chuyển sang nhà cung cấp ngoài tổ chức hoặc vùng địa lý khác không?
- Log có tồn tại trong local files, agent spools, collector buffers, index, archive và backups bao lâu?
- Ai có quyền export, share link, screenshot hoặc tạo support ticket?
- Có cách xác định tất cả bản sao khi phát hiện một secret/PII đã lọt vào log không?
- Retention và legal hold được phê duyệt theo loại dữ liệu/sự kiện nào?
- Có cơ chế theo dõi truy cập vào kho log nhạy cảm không?

**Retention ngắn không biến việc ghi PII không cần thiết thành an toàn.** PII vẫn có thể bị xem hoặc rò trong vài phút tồn tại. Ngược lại, redaction không thay thế RBAC và encryption: các metadata còn lại vẫn có thể nhạy cảm hoặc đủ để liên kết người dùng.

Phân loại PII và nghĩa vụ thông báo/xóa dữ liệu phụ thuộc quy định áp dụng, hợp đồng, chính sách tổ chức và bối cảnh; không khẳng định một regex hoặc cơ chế masking tự động đáp ứng mọi luật về bảo vệ dữ liệu.

## 20. Kiểm thử không rò PII: unit tests

Một bộ test cần dùng **giá trị nhạy cảm giả** và chứng minh event được phép xuất không chứa chúng. Các test nên bao phủ:

1. Safe event có **eventCode/outcome/errorCode** vẫn đủ để debug.
2. \`email\`, \`phone\`, \`authorization\`, \`cookie\`, \`password\` không xuất trong message, structured fields hoặc MDC.
3. DTO.toString() không được truyền trực tiếp vào logging API ở những đường nhạy cảm.
4. Invalid requestId chứa CR/LF hoặc Unicode control được loại bỏ/chuẩn hóa.
5. Exception message chứa secret giả không bị logger/encoder đưa nguyên ra sink công khai.
6. Khi DTO thêm một trường PII mới, schema allowlist vẫn không lộ trường đó.
7. Khi logger disabled hoặc enabled DEBUG, không có đường debug mới dump payload.
8. Null values, nested objects, arrays/maps và input dài không bypass policy.
9. Redaction marker không vô tình tiết lộ phần credential không cần thiết.
10. Correlation/diagnostic fields vẫn hiện diện để event còn khả năng điều tra.

Ví dụ assertion tích hợp (không phải chương trình JUnit độc lập):

~~~java
String output = captureLogFromRequest(fakeLoginRequest);
assertFalse(output.contains("alice@example.test"));
assertFalse(output.contains("Bearer demo-access-token"));
assertTrue(output.contains("event=login_rejected"));
assertTrue(output.contains("requestId=req-42"));
~~~

Để chạy đoạn trên cần JUnit, hàm captureLogFromRequest và fixture giả. **Không chỉ kiểm tra một field đã redact**: cần kiểm tra cả message, structured arguments, MDC, Throwable và output encoder.

Đừng dùng dữ liệu khách hàng hoặc credential production để test. Canary secret giả phải rõ ràng để phát hiện đường rò mà không tạo rủi ro thật.

## 21. Integration tests: kiểm tra mọi sink

Unit test helper tạo safe string có thể PASS trong khi **HTTP client wire logger** vẫn ghi token. Test integration nên thu được output thực:

| Test case | Điều phải kiểm tra |
| --- | --- |
| HTTP request chứa header Authorization giả | Không có raw header ở console/file/collector |
| JSON body có email/phone giả | Không có raw payload ngoài policy |
| DTO.toString() chứa PII | Logger wrapper và serializer không dump object |
| Throwable chứa URL query token | Exception formatter/sink được kiểm soát |
| MDC có ID sai hoặc key nhạy cảm | Encoder không phát PII, worker context không leak |
| ORM SQL bind có personal data | Diagnostic logging không xuất raw value |
| Kafka/RabbitMQ retry/DLQ | Không dump message payload hoặc headers nhạy cảm |
| DEBUG tạm bật ở staging | Không có logger thư viện bypass policy |
| Async appender + queue drain | Event snapshot đúng nhưng không phát raw secret |
| Collector filtering/routing | Redaction ở lớp hai đúng, không tạo raw archive |
| Backup/export/dashboard | Quyền truy cập, field masks, retention đúng |
| Canary bằng encoding khác | Chứng minh parser/policy không dễ bypass |

**Đếm dòng log không chứng minh PII không tồn tại ở sink khác.** Với nhiều appenders, test đúng từng destination hoặc một fixture dựng pipeline thực tế.

Ngoài negative assertions ("không chứa secret"), cần **positive assertions**: eventCode, requestId và errorCode đủ để hỗ trợ điều tra, để biện pháp bảo vệ không làm logging mất hết giá trị.

## 22. Code review, lint và CI guardrails

Một quy trình giảm rủi ro nên có:

- **Review checklist** mỗi khi thêm logger call cho request/response, DTO, exception hoặc MDC.
- **Static rules** cảnh báo \`logger.*(requestBody)\`, \`logger.*(password)\`, \`MDC.put("email", ...)\`, \`toString()\` của entity nhạy cảm.
- **Dependency/config review** khi nâng cấp HTTP client, ORM, tracing SDK hoặc logging backend.
- **Schema registry/typed logging API** giới hạn field được phát; không chỉ dựa vào regex nhận diện tên biến.
- **Canary integration test** chạy trong staging với token/email giả.
- **Security review** cho hệ thống có event privacy-sensitive, audit logs, payment/health data.
- **Production controls** cho dynamic log level, remote config và thay đổi collector.
- **Metrics** theo dõi logging volume, parse errors, drop rate, buffer và log export anomalies.

Static analysis không nhìn thấy mọi dữ liệu runtime. Một biến tên \`details\` có thể chứa PII, còn biến \`emailHash\` có thể vẫn nhận diện được qua dictionary attack. Vì vậy kết hợp **field policy + test động + review kiến trúc**.

Không tự tạo alert chứa raw PII khi scanner phát hiện một sự kiện: cảnh báo nên gửi event reference, source/sink và classification, để người có quyền truy cập bằng kênh bảo vệ.

## 23. Phân tích lỗi khó phát hiện: dữ liệu kết hợp

Ngay cả khi log không có email hoặc tên, một tập metadata có thể đủ để suy luận danh tính:

~~~text
userRef=U731 route=/rare-medical-claim outcome=DENIED
timestamp=2026-11-10T03:11:24Z ip=198.51.100.22
~~~

Đây là dữ liệu minh họa sử dụng một IP thuộc dải ví dụ. **userRef**, route rất hiếm, timestamp và địa chỉ IP có thể liên kết với nguồn khác để suy ra hoạt động của một cá nhân.

Các biện pháp:

- Không thu thập mọi metadata chỉ vì chúng “không phải email”.
- Giảm độ chính xác/thời gian hoặc dùng aggregation khi mục tiêu điều tra cho phép.
- Dùng role-based access hoặc tách kho bảo vệ đối với dữ liệu có nguy cơ tái nhận diện.
- Giới hạn retention theo data classification.
- Đánh giá cần thiết của từng field theo use case, không theo tên trường bề ngoài.

**Pseudonymization** giúp giảm rủi ro nhưng không luôn loại bỏ tính chất dữ liệu cá nhân. Một ID có thể linkable theo thời gian và được map trở lại profile ở hệ thống khác.

## 24. Khi phát hiện PII đã bị ghi vào production logs

Khi thấy token hoặc dữ liệu cá nhân trong log, cần đối xử như **sự cố xử lý dữ liệu** và làm theo incident response của tổ chức.

Một quy trình thường gồm:

1. **Ngăn thêm rò rỉ:** tắt đường dump hoặc triển khai sửa code/encoder theo change control, không che tất cả logging thiết yếu.
2. **Phân loại dữ liệu:** credential, thông tin cá nhân, thanh toán, dữ liệu nghiệp vụ, mức độ nhạy cảm và số lượng event.
3. **Xác định nguồn phát:** logger, HTTP client, ORM, exception, MDC, collector hoặc SDK nào.
4. **Lập bản đồ các bản sao:** stdout, file, container logs, agent spool, collector buffer, index, archive, export, backup và dịch vụ bên ngoài.
5. **Giảm quyền xem:** giới hạn truy cập, khóa export liên quan và theo dõi truy cập khi cần.
6. **Rotate/revoke secrets:** nếu token/password/API key lộ, ưu tiên vô hiệu hóa theo quy trình phù hợp.
7. **Xử lý dữ liệu đã lưu:** xóa, reindex, hạn chế truy cập hoặc giữ theo legal hold/chính sách; không tuyên bố xóa hết khi backup/archive chưa được xử lý.
8. **Đánh giá nghĩa vụ thông báo:** phối hợp bảo mật, privacy, pháp chế và owners theo quy định áp dụng.
9. **Thêm regression tests** và xác nhận không còn rò ở mọi sink.
10. **Postmortem:** xác định vì sao schema/review/CI không phát hiện và sửa quy trình.

**Không paste lại raw secret trong ticket hoặc chat để mô tả sự cố.** Dùng eventId, time range, source logger và một reference tới kho bằng chứng có phân quyền.

## 25. Checklist tránh anti-pattern trong Java Logging

| Hạng mục | Tiêu chí hoàn thành |
| --- | --- |
| Data classification | PII/secret/metadata được phân loại và có owner |
| Data minimization | Không log raw user object, body, headers hay token |
| Event schema | Chỉ field allowlist, eventCode/errorCode ổn định |
| Input validation | requestId/traceId hoặc ID kỹ thuật có grammar/độ dài |
| SLF4J/JUL/Log4j | Logger không tự đưa DTO.toString() hoặc secret vào event |
| MDC | Không chứa PII, cleanup và propagation đúng |
| Exceptions | Throwable message/cause/stack trace được review |
| Third-party | HTTP wire, ORM bind, messaging/tracing SDK được kiểm soát |
| Encoding | JSON/text escape đúng và ngăn log forging |
| Redaction | Ưu tiên ở nguồn; collector chỉ là phòng vệ bổ sung |
| Access | RBAC, field access, export audit và TLS phù hợp |
| Retention | Local files, indexes, archives, backups có lifecycle |
| QA | Unit + integration + canary secrets giả qua mọi sink |
| Incident | Có quy trình thu hồi credential và xử lý bản sao |
| Operations | DEBUG production chỉ bật có giới hạn và được audit |

**Kết luận:** anti-pattern “không kiểm soát PII” xuất hiện khi logging được xem như nơi đổ toàn bộ trạng thái chương trình. Cách sửa bền vững nhất trong Java là **không đưa dữ liệu không cần thiết vào log ngay từ đầu**, thiết kế event theo allowlist, kiểm tra các đường gián tiếp như MDC/Throwable/toString/SDK, dùng encoder an toàn và kiểm thử từ ứng dụng tới collector/backend. Redaction, encryption, RBAC và retention là những lớp bổ sung cần thiết, nhưng không thay thế quyết định cơ bản: **trường nhạy cảm nào thực sự cần được ghi?**