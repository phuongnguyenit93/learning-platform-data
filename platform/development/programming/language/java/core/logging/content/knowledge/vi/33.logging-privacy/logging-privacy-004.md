# Mask dữ liệu nhạy cảm trong Java Logging

## 1. Mục tiêu: giữ khả năng quan sát nhưng không làm rò rỉ thông tin

**Mask dữ liệu nhạy cảm (data masking/redaction trong logging)** là quá trình không đưa hoặc loại bỏ, che một phần hay thay thế các giá trị nhạy cảm trước khi bản ghi được lưu, hiển thị, chuyển tới collector hoặc chia sẻ. Ví dụ, thay số thẻ thử nghiệm `4111111111111111` bằng `****1111`, hoặc thay toàn bộ access token bằng `[REDACTED]`.

Trong Java, một lời gọi logger có thể tạo dữ liệu ở nhiều nơi: **message**, **tham số**, **exception và stack trace**, **MDC/ThreadContext**, **HTTP headers**, **request body**, **URL/query**, **đối tượng được `toString()`**, thuộc tính của JSON event và bản ghi sinh ra bởi thư viện. Vì vậy, chỉ dùng regex sửa phần message là **không đủ**.

Mục tiêu thực tế theo thứ tự ưu tiên:

1. **Không thu thập/không log** dữ liệu không cần thiết.
2. **Chỉ log các trường đã được phép (allowlist)**, ưu tiên mã sự kiện, trạng thái và định danh nội bộ ít nhạy cảm hơn.
3. **Mask/redact/tokenize** những trường thật sự cần một phần giá trị để điều tra, với chính sách rõ ràng và phép kiểm có thể lặp lại.
4. **Bổ sung lớp phòng vệ tại formatter/appender/collector** để giảm thiểu lỗi của code ứng dụng; không coi đây là bảo đảm tuyệt đối.
5. **Bảo vệ vòng đời bản ghi** bằng kiểm soát truy cập, mã hóa, lưu giữ và xóa theo chính sách.

**Mask không làm dữ liệu trở thành vô hại.** Một email đã lộ ký tự đầu và domain vẫn có thể giúp nhận diện người dùng; bốn số cuối thẻ đôi khi có thể kết hợp với dữ liệu khác. Cần cân nhắc mức độ cần thiết và yêu cầu bảo vệ thông tin theo bối cảnh.

## 2. Phân loại dữ liệu trước khi thiết kế quy tắc

Một chính sách điển hình có thể phân nhóm như sau (cần hiệu chỉnh theo hệ thống và quy định áp dụng):

| Nhóm | Ví dụ | Chiến lược mặc định | Vì sao |
| --- | --- | --- | --- |
| Bí mật xác thực | Password, PIN, OTP, access/refresh token, API key, cookie phiên, Authorization header | **Không ghi** giá trị; thay bằng cờ hiện diện hoặc `[REDACTED]` | Một chuỗi ngắn có thể cấp quyền truy cập thật |
| Khóa và vật liệu mật mã | Private key, seed, recovery code, secret cấu hình | **Không ghi**, kể cả prefix/suffix khi không cần | Nguy cơ xâm nhập hệ thống |
| Thông tin thanh toán | PAN/số thẻ, CVV, số tài khoản | Không ghi; chỉ giữ trường tối thiểu được phép, ví dụ last4 theo policy | Dữ liệu tài chính nhạy cảm |
| Thông tin cá nhân | Email, số điện thoại, địa chỉ, định danh, dữ liệu sức khỏe | Tránh ghi hoặc che/tách định danh theo mục đích | Dễ tái nhận diện và có yêu cầu quyền riêng tư |
| HTTP request/response | Query string, body, header, cookie | Chỉ log method, route template, status, duration, mã lỗi | Có thể chứa token và PII ở vị trí không dự đoán trước |
| Connection/database | JDBC URL chứa credential, SQL bind values, URI tích hợp | Ghi tên dịch vụ, mã lỗi và độ trễ; không ghi credential/bind nhạy cảm | Connection string và câu SQL có thể mang bí mật |
| Dữ liệu hoạt động | Event code, service name, status, duration, correlation ID | Cho phép theo schema và retention | Đủ để giám sát mà không cần dữ liệu gốc |

Chính sách **không thể** chỉ dựa vào tên trường. `userId` có thể là một định danh cá nhân, `traceId` có thể giúp liên kết hành vi, còn một `errorMessage` tưởng vô hại có thể chứa token trong URL.

Áp dụng nguyên tắc *data minimization*: chỉ giữ dữ liệu thực sự cần để debug, giám sát, điều tra sự cố, bảo mật hoặc kiểm toán; xác định mục đích trước khi ghi.

## 3. Phân biệt các kỹ thuật thường bị gọi chung là “mask”

| Kỹ thuật | Biến đổi | Khả năng khôi phục hoặc liên kết |
| --- | --- | --- |
| **Omit/drop field** | Không đưa trường vào log | Không thể lấy từ bản ghi đó; thường an toàn nhất |
| **Full redaction** | `token=[REDACTED]` | Không tiết lộ giá trị gốc qua trường đã redact |
| **Partial masking** | `a***@example.test` hoặc `****1111` | Giữ một phần dữ liệu; vẫn có nguy cơ suy luận/re-identification |
| **Pseudonymization** | Thay người dùng bằng mã tham chiếu | Có thể liên kết sự kiện; vẫn có rủi ro quyền riêng tư |
| **Tokenization** | Thay dữ liệu bằng token tra cứu theo hệ thống quản lý | Có thể khôi phục qua token vault nếu được cấp quyền |
| **Hashing** | Biến đầu vào thành digest | Một chiều theo hàm, nhưng dễ bị dò với tập giá trị nhỏ |
| **HMAC có khóa** | Tạo định danh ổn định từ bí mật và message | Hữu ích cho correlation có kiểm soát; cần bảo vệ và xoay khóa |
| **Encryption** | Mã hóa dữ liệu gốc | Có thể giải mã bằng khóa; bản ghi vẫn chứa dữ liệu nhạy cảm đã mã hóa |

**Hash SHA-256 trực tiếp email/số điện thoại không đồng nghĩa ẩn danh.** Tập giá trị có thể bị đoán hoặc brute-force. HMAC với khóa được quản lý riêng giảm khả năng dò offline nhưng vẫn tạo định danh có thể liên kết và cần chính sách kiểm soát. Tokenization/HMAC không thay thế việc đánh giá quyền riêng tư.

Khi chỉ cần biết “header Authorization có được gửi hay không”, log `authorizationPresent=true` thường phù hợp hơn bất kỳ dạng token đã mask nào.

## 4. Lọc tại nguồn trước khi đưa dữ liệu vào logger

Phương án an toàn hơn:

~~~java
// Minh họa: log các trường có trong allowlist, không log request hoặc DTO đầy đủ.
log.info("login result={} reason={} requestId={}",
        safeResult, safeReasonCode, requestId);
~~~

Các biến ở trên phải được **chuẩn hóa và xét quyền ghi** trước khi gọi logger. Đây là đoạn dùng SLF4J/Log4j 2 với logger đã khai báo, không phải chương trình Java độc lập.

Phương án rủi ro:

~~~java
// KHÔNG nên làm: đối tượng có thể chứa password, token, email, cookie.
log.info("incoming request={}", request);
log.error("login failed, headers={}", headers);
log.debug("user profile={}", user.toString());
~~~

Ngay cả khi DEBUG đang tắt, một lần bật DEBUG trong sự cố có thể vô tình xuất toàn bộ dữ liệu. `toString()` sinh tự động bởi Lombok, record hoặc IDE có thể thêm các trường mới sau này mà code log không thay đổi.

Thiết kế tốt là tạo **SafeLogEvent** hoặc map chỉ chứa các trường được cho phép, ví dụ:

~~~text
eventCode: "LOGIN_DENIED"
result: "DENIED"
reasonCode: "INVALID_CREDENTIALS"
requestId: "req-7f2a"
credentialPresent: true
~~~

Đây là **schema minh họa**. Không đặt raw email, password, token hoặc full HTTP request vào event và trông chờ formatter xóa sau.

## 5. Ba ranh giới phải kiểm soát

~~~text
Nguồn dữ liệu (HTTP/DB/queue/config)
   │
   ├─ [1] App/service: chọn trường + sanitize/mask theo schema
   ▼
Log API: message + arguments + Throwable + MDC
   │
   ├─ [2] Logger/Formatter/Appender/Encoder: chặn lần hai
   ▼
File / stdout / socket / agent
   │
   ├─ [3] Collector/index/storage: ingest policy + phân quyền + retention
   ▼
Dashboard / truy vấn / export / archive / backup
~~~

**[1] Trước lời gọi logger** là tuyến phòng vệ quan trọng nhất: ở đây code biết loại trường, purpose và quyền ghi. **[2] Ở logging backend** là lớp giảm thiểu bổ sung khi có nơi phát log ngoài tầm kiểm soát; regex có thể không bao phủ mọi message/exception/context. **[3] Tại collector/storage** cần có quy tắc ingest và quản trị vì log có thể từ nhiều phiên bản dịch vụ hoặc thư viện khác nhau.

Nếu dữ liệu đã gửi tới sink rồi, mask ở UI dashboard **không xóa được dữ liệu gốc** trong file, index, archive hoặc bản export. Ngăn dữ liệu vào pipeline ngay từ đầu luôn ít rủi ro hơn.

## 6. Ví dụ Java 17 độc lập: mask đúng trước khi log

Ví dụ dùng `java.util.logging` (JUL), không cần thư viện ngoài JDK. Chương trình chủ động **không truyền secret gốc** vào logger; email được mask, số thẻ giả lập chỉ giữ 4 chữ số cuối, reasonCode được allowlist để chặn cả dữ liệu không mong muốn có newline.

Tạo tệp **SensitiveMaskDemo.java**:

~~~java
import java.util.Locale;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class SensitiveMaskDemo {
    private static final Logger LOG =
            Logger.getLogger(SensitiveMaskDemo.class.getName());

    private static String maskEmail(String input) {
        if (input == null) return "[REDACTED]";
        int at = input.indexOf('@');
        if (at < 1 || at != input.lastIndexOf('@') ||
                at == input.length() - 1) return "[REDACTED]";
        String local = input.substring(0, at);
        String domain = input.substring(at + 1);
        if (!local.matches("[A-Za-z0-9._%+-]{1,64}") ||
                !domain.matches("[A-Za-z0-9.-]{1,253}") ||
                domain.indexOf('.') < 0) return "[REDACTED]";
        return local.charAt(0) + "***@" +
                domain.toLowerCase(Locale.ROOT);
    }

    private static String maskCard(String digits) {
        if (digits == null || !digits.matches("[0-9]{12,19}"))
            return "[REDACTED]";
        return "****" + digits.substring(digits.length() - 4);
    }

    private static String safeReason(String reason) {
        return "INVALID_INPUT".equals(reason) ? "INVALID_INPUT" : "OTHER";
    }

    public static void main(String[] args) {
        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord event) {
                return event.getLevel().getName() + " "
                        + formatMessage(event) + System.lineSeparator();
            }
        });
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(handler);
        try {
            String email = "alice@example.test";
            String testCard = "4111111111111111";
            String testSecret = "TEST_SECRET_DO_NOT_LOG";
            String untrustedReason = "INVALID_INPUT\nERROR forged";

            LOG.log(Level.INFO, "auth result={0} user={1} reason={2}",
                    new Object[]{"DENIED", maskEmail(email),
                            safeReason(untrustedReason)});
            LOG.log(Level.INFO, "payment result={0} card={1}",
                    new Object[]{"REJECTED", maskCard(testCard)});
            LOG.log(Level.INFO, "credential_present={0}",
                    !testSecret.isEmpty());
        } finally {
            LOG.removeHandler(handler);
            handler.flush();
            handler.close();
        }
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac --release 17 SensitiveMaskDemo.java
java SensitiveMaskDemo
~~~

**Standard error (stderr) chính xác**, vì `ConsoleHandler` ghi ra stderr:

~~~text
INFO auth result=DENIED user=a***@example.test reason=OTHER
INFO payment result=REJECTED card=****1111
INFO credential_present=true
~~~

**Standard output (stdout):** trống. Exit code: `0`.

Diễn giải:

- `maskEmail(...)` chỉ cho phép một tập con nhỏ các địa chỉ ASCII để demo; nếu đầu vào không khớp, trả `[REDACTED]` thay vì thử in giá trị gốc. Đây **không** phải bộ kiểm tra cú pháp email đầy đủ hoặc bộ masking Unicode/email quốc tế hóa.
- `maskCard(...)` kiểm tra chuỗi số 12–19 ký tự, **không xác thực số thẻ hoặc kiểm tra Luhn**, rồi giữ bốn số cuối. Trong hệ thống thật chỉ dùng last4 khi chính sách cho phép; tuyệt đối không log CVV/PIN.
- `testSecret` chỉ dùng để suy ra boolean `credential_present`; toàn bộ chuỗi bí mật không được đưa vào `LogRecord`.
- `safeReason(...)` chỉ chấp nhận `INVALID_INPUT`. Chuỗi lạ, kể cả chuỗi chứa ký tự xuống dòng dùng cho log injection, bị đổi thành `OTHER`.
- `Formatter.formatMessage(event)` của JUL định dạng đúng các placeholder `{0}`, `{1}`, `{2}`. Formatter không tự mask; **dữ liệu truyền vào đã được xử lý**.
- `LOG.setUseParentHandlers(false)` tránh log trùng qua root handler trong demo; không phải một bước bảo mật thay cho kiểm soát sink.

**Ranh giới ví dụ:** một email đã mask vẫn bộc lộ ký tự đầu và domain. Nếu domain hoặc danh tính không cần thiết, chính sách có thể thay bằng `[REDACTED_EMAIL]` hoàn toàn. Với số thẻ, thường hệ thống nên **không đưa PAN đầy đủ vào service logging** ngay từ đầu; ví dụ này chỉ giúp thấy rõ quy tắc masking.

## 7. Thiết kế API cho trường nhạy cảm: mặc định từ chối

Thay vì trả về `toString()` của một DTO chứa tất cả thuộc tính, tạo lớp mô tả event phục vụ log với **danh sách trường cố định**:

~~~java
// Minh họa schema nội bộ không phụ thuộc framework logging.
record LoginAuditView(
        String eventCode,
        String result,
        String reasonCode,
        String correlationId,
        boolean credentialPresent) {}
~~~

Ở tầng ứng dụng, chuyển object nghiệp vụ sang `LoginAuditView` bằng phép biến đổi có kiểm soát. **Đừng** thêm `password`, `accessToken`, `rawHeaders` vào record này. Nếu một trường mới được thêm vào domain DTO, nó không tự động chui vào schema log đã duyệt.

Trong công cụ log structured, chỉ xuất các field của `LoginAuditView` hoặc một map allowlist đã được xác thực. Khi không thể phân loại dữ liệu, chọn **không ghi** thay vì serialize toàn bộ và trông chờ regex che hết.

Các trạng thái quan trọng:

- `null`, malformed hoặc input vượt giới hạn: trả sentinel như `[REDACTED]` hoặc bỏ trường.
- Việc mask thất bại: **fail closed** (không ghi raw) và tăng metric an toàn; không dùng `catch (Exception e) { return raw; }`.
- Dữ liệu đầu vào phải được giới hạn kích thước để chống regex tốn CPU hoặc log amplification.
- Đối với đối tượng mutable xử lý bởi async logger, lấy snapshot các trường an toàn tại thời điểm event; đừng truyền cả object nhạy cảm sang queue.

## 8. Những vị trí dễ rò rỉ ngoài message

Mask message nhưng bỏ qua các nguồn sau vẫn có thể mất an toàn:

| Nguồn | Ví dụ rủi ro | Phương án |
| --- | --- | --- |
| **Throwable.getMessage()** | HTTP client exception chứa URL kèm token; SQL exception chứa query | Log error code + exception class; stack trace chỉ ở kênh được kiểm soát và đã kiểm định |
| **Suppressed/cause chain** | Thông tin bí mật xuất hiện ở exception lồng nhau | Xét toàn chuỗi/stack trace khi đánh giá policy |
| **MDC / ThreadContext** | `MDC.put("email", rawEmail)` khiến mọi event bị lộ | Chỉ cho phép correlation ID/thuộc tính đã mask |
| **HTTP headers** | Authorization, Cookie, Set-Cookie, X-API-Key | Denylist hẳn các header bí mật; tốt hơn dùng allowlist header an toàn |
| **URL/query string** | `?access_token=...`, email trong query | Log route template không chứa query, thay vì full URI |
| **HTTP body** | Password, OTP, tài liệu, PII | Không log body mặc định; debug cần môi trường riêng và quy trình phê duyệt |
| **Database/SQL** | Bind parameter hoặc JDBC URL có credential | Log mã lỗi, statement identifier, duration; bỏ raw bind values |
| **JSON encoder** | Có thể serialize nhiều trường hơn PatternLayout | Xác định schema, loại field và kiểm thử output JSON thực |
| **Exception renderer** | Layout tự append stack trace dù pattern chỉ định `%msg` | Kiểm tra chính xác output cả với Throwable |
| **Access log, proxy/ingress** | Được ghi ngoài code Java ứng dụng | Kiểm tra cấu hình ở web server/gateway/collector |

Đừng chỉ sửa ở một nơi rồi kết luận toàn bộ pipeline an toàn. Một appender khác, đặc biệt audit/debug/console hoặc exporter phụ, có thể còn nhận bản ghi thô.

## 9. JUL: custom Formatter/Filter và điểm giới hạn

`java.util.logging` có các phần:

- `Logger` tạo `LogRecord` từ message, parameters và Throwable.
- `Filter.isLoggable(LogRecord)` quyết định có cho phép record đi tiếp.
- `Handler` nhận record, dùng `Formatter.format(LogRecord)` tạo text và ghi sink.
- `LogRecord.getMessage()`, `getParameters()`, `getThrown()` có thể chứa dữ liệu nhạy cảm từ đầu.

**Chú ý:** `Filter` có giao diện trả boolean (cho phép/không cho phép), không phải API chuyên để biến đổi hoặc xóa từng trường bên trong record. Nếu mục đích là mask một trường, tốt hơn **xử lý trước khi gọi `Logger.log`** hoặc viết formatter/handler chuyên biệt có phạm vi rõ.

Ví dụ trong phần 6 dùng:

~~~java
LOG.log(Level.INFO, "auth result={0} user={1} reason={2}",
        new Object[]{"DENIED", maskEmail(email), safeReason(reason)});
~~~

Đây là dòng minh họa với biến `reason` đã khai báo trong chương trình khác; nguyên tắc là **giá trị an toàn được tạo trước khi thành log argument**. Một custom `Formatter` có thể redact message text trước khi xuất, nhưng phải quan tâm đến `LogRecord.getThrown()` và các tham số còn nguyên. Nếu có nhiều handler, một handler không mask vẫn có thể ghi dữ liệu gốc.

`Formatter.formatMessage(record)` chỉ định dạng, không phải công cụ ngăn lộ secret. Việc dùng `record.getMessage()` thay vì `formatMessage(record)` có thể bỏ qua parameters nhưng **không biến sự kiện trở thành an toàn**: dữ liệu thô vẫn nằm trong record.

## 10. SLF4J và Logback: ưu tiên mask từ ứng dụng

SLF4J là facade; backend thực tế quyết định layout và đích xuất. Với ứng dụng dùng SLF4J + Logback:

~~~java
// Đoạn minh họa; LOG và các biến đã được khai báo.
LOG.info("login result={} email={} errorCode={}",
        safeResult, maskEmail(email), safeErrorCode);
~~~

Mẫu `{}` chỉ giúp truyền tham số riêng và trì hoãn định dạng. Nó **không tự xóa bí mật**. Lời gọi sau vẫn có thể gây rò rỉ:

~~~java
// Tránh: backend vẫn nhận được token gốc khi INFO được bật.
LOG.info("Authorization token={}", rawToken);
~~~

Nếu dùng **SLF4J 2.x Fluent API**, có thể gắn các trường an toàn:

~~~java
LOG.atInfo()
        .addKeyValue("eventCode", "LOGIN_DENIED")
        .addKeyValue("reasonCode", safeErrorCode)
        .addKeyValue("userRef", maskedUserRef)
        .log("login denied");
~~~

Đoạn này chỉ chạy khi dự án dùng SLF4J 2.x, logger và biến tương ứng đã khởi tạo. Việc trường `addKeyValue` có được in vào log hay không phụ thuộc encoder/layout. Không đưa `rawToken` hoặc PII chưa xử lý vào builder.

### Logback PatternLayout: lớp chặn thứ hai có giới hạn

Logback hỗ trợ conversion `%replace(...)`; ví dụ một **lớp mask bổ sung** chỉ cho message có mẫu `token=...`:

~~~xml
<!-- Fragment trong encoder của appender Logback; kiểm thử với phiên bản đang chạy. -->
<pattern>%d %-5level %logger - %replace(%msg){'(?i)(token=)\S+', '$1[REDACTED]'}%n</pattern>
~~~

Nếu message chứa `token=sample_value`, pattern dự định thay giá trị theo regex thành `token=[REDACTED]`.

**Đây không phải cơ chế chống rò rỉ toàn diện:**

- Regex chỉ bắt **mẫu đã biết** trong phần chuỗi được chọn, không bao phủ object JSON, tên key mới, escaped/unicode variants, email ở trường khác.
- `%msg` chỉ là message. Exception, stack trace, MDC hoặc field được encoder xuất riêng **không nhất thiết được mask**.
- Logback có hành vi xuất exception bổ sung tùy pattern/layout; phải kiểm tra cả sự kiện chứa Throwable, không chỉ message.
- Regex chạy trên dòng log có thể gây overhead; pattern kém có thể gây vấn đề hiệu năng, nhất là trên message rất dài.
- Các sink sử dụng encoder khác, ví dụ JSON encoder, cần policy riêng tương ứng.

Đừng tự viết `PatternLayout` khiến `getFormattedMessage()` hoặc `toString()` của payload được gọi **trước khi mask**, rồi cho rằng dữ liệu không bao giờ tồn tại ở hệ thống logging. Mục tiêu vẫn là loại secret tại nguồn.

## 11. Log4j 2: PatternLayout, JSON và các lớp lọc

Với Log4j 2 API, các lời gọi parameterized cũng **không tự mask**:

~~~java
// Đoạn minh họa; cần Log4j 2 API và LOG đã khởi tạo.
LOG.warn("login rejected userRef={} reason={}",
        maskedUserRef, safeReasonCode);
~~~

Log4j 2 `PatternLayout` hỗ trợ `%replace{pattern}{regex}{substitution}`. Ví dụ một fragment:

~~~xml
<PatternLayout pattern="%d %-5p %c - %replace{%msg}{(?i)(token=)\S+}{$1[REDACTED]}%n"/>
~~~

Pattern trên chỉ minh họa cách thay một mẫu `token=...` trong **message**. Log4j 2 cũng hỗ trợ `RegexReplacement` ở cấp `PatternLayout` áp dụng trên chuỗi đầu ra được layout tạo, nhưng không nên kết luận nhờ đó mọi đường lộ bí mật đều bị chặn. Cần kiểm thử chính xác encoder, exception rendering, MDC, marker, arguments và field bổ sung.

Khi cần log JSON theo schema, Log4j 2 khuyến nghị **JSON Template Layout** cho output cấu trúc. Với `JsonTemplateLayout`, nên **chọn rõ những resolver/field được phép** và kiểm tra file JSON kết quả; đừng bật serialize nguyên object hoặc exception message chứa bí mật chỉ vì event có kiểu JSON. Cần dependency tương ứng `log4j-layout-template-json` khi dùng layout này.

Filter `DENY` của Log4j 2 có thể chặn **cả event**, nhưng không mặc nhiên làm được mask một field. Quy tắc “không chứa dữ liệu nhạy cảm” thuộc schema và pipeline redaction, không phải một threshold filter theo level.

## 12. MDC, ThreadContext và correlation an toàn

MDC (trong SLF4J/Logback) và `ThreadContext` (Log4j 2) giúp đưa metadata của request vào nhiều sự kiện log. Đây là vị trí hay bị bỏ quên:

~~~java
// Tránh: email/token đi theo mọi log event của luồng hiện tại.
MDC.put("email", rawEmail);
MDC.put("token", rawToken);
~~~

Thay bằng định danh ít nhạy cảm hoặc đã được xử lý:

~~~java
// Minh họa trong app dùng SLF4J.
MDC.put("requestId", safeRequestId);
try {
    runBusinessLogic();
} finally {
    MDC.remove("requestId");
}
~~~

Các biến/hàm cần được khai báo trong ứng dụng và `safeRequestId` phải được kiểm tra tính hợp lệ, độ dài và nguồn phát. Không coi UUID hoặc correlation ID là dữ liệu công khai tuyệt đối; nó vẫn cho phép liên kết nhiều sự kiện.

Với thread pool, coroutine/reactive workflow hoặc virtual thread, cần quản lý **phạm vi truyền context** phù hợp. Tránh để context từ một request rò sang request tiếp theo do quên remove/clear. Không dùng `MDC.clear()` bừa bãi nếu bạn không sở hữu toàn bộ context của thread; có thể xóa cả thông tin do framework khác quản lý.

Ở Log4j 2, áp dụng cùng nguyên tắc với `ThreadContext.put/remove`. Nếu backend JSON tự động đưa toàn bộ MDC vào output, mọi giá trị bạn đặt trong MDC phải được xem là **có thể xuất hiện trong log**.

## 13. Stack trace và exception: nguồn rò rỉ khó nhận ra

Exception message thường chứa dữ liệu nguồn:

~~~java
// Tránh đưa object lỗi chưa kiểm soát sang kênh log công khai.
LOG.error("HTTP request failed", ex);
~~~

Đây là đoạn SLF4J/Log4j 2 minh họa. Khi `ex.getMessage()` chứa URL, token, SQL bind values hoặc body request, renderer có thể in ra các thông tin đó. Chuỗi `cause` và `suppressed exceptions` cũng có thể chứa dữ liệu tương tự.

Lựa chọn phù hợp tùy mức bảo mật:

- **Kênh thông thường:** log event code, error category, HTTP status, định danh yêu cầu đã kiểm tra và nguyên nhân phân loại từ allowlist.
- **Kênh điều tra hạn chế quyền:** khi thực sự cần stack trace, cho phép theo policy, dùng cơ chế bảo vệ/retention riêng và kiểm tra toàn bộ exception rendering.
- **Không chuyển ngoại lệ chưa kiểm soát thành text rồi mask bằng regex đơn lẻ**, vì stack trace có thể chứa nhiều định dạng và tầng cause khác nhau.
- **Không tạo một exception mới chứa bản sao secret** trong thông báo chỉ để dễ debug.

Bỏ stack trace hoàn toàn không phải lúc nào cũng hợp lý: có thể làm mất bằng chứng điều tra. Giải pháp là phân tầng kênh, kiểm soát kiểu dữ liệu và quyền truy cập; khi cần có thể xây error DTO an toàn cho log phổ thông.

## 14. Log injection: tách bạch với masking

**Log injection/forging** xảy ra khi giá trị không đáng tin cậy chứa newline hoặc control character làm xuất bản ghi giả:

~~~text
reason=INVALID_INPUT
ERROR admin authenticated successfully
~~~

Nếu nối trực tiếp input của người dùng vào một file log dòng đơn, người đọc hoặc pipeline parser có thể hiểu nhầm đây là hai sự kiện. Mask dữ liệu nhạy cảm và chống log injection **là hai yêu cầu khác nhau**.

Các biện pháp:

1. Với trạng thái và reason code, dùng **allowlist enum/code**. Ví dụ Java 17 trả `OTHER` nếu input lạ, không chuyển `\n` tới log.
2. Với field text cần lưu, dùng encoder có cấu trúc và xử lý/escape control characters theo định dạng đích; thử cả CR, LF, tab, NUL và Unicode bất thường.
3. Giới hạn độ dài field để tránh log amplification và regex tốn tài nguyên.
4. Không dùng `String.replace("\n", "")` như giải pháp duy nhất cho mọi format: còn CR, control char, encoding và dữ liệu cấu trúc.
5. Với JSON, dùng JSON encoder thực sự thay vì nối chuỗi dấu ngoặc kép bằng tay; việc escape JSON **không** đồng nghĩa secret được redact.

Ví dụ `safeReason` trong chương trình chỉ nhận giá trị đúng `INVALID_INPUT`; do đó chuỗi `"INVALID_INPUT\nERROR forged"` bị ánh xạ thành `OTHER`. Kết quả vẫn ghi được mục đích nghiệp vụ mà không chèn dòng giả.

## 15. Regex masking: nên dùng khi nào và giới hạn ở đâu?

Regex thường hữu ích như **defense in depth** đối với một số mẫu tương đối ổn định, ví dụ `token=...` trong log của thư viện khó sửa. Nhưng không nên dùng regex như phương pháp chính cho mọi secret.

Các tình huống khó:

- Key khác tên: `accessToken`, `auth`, `Authorization`, `apikey`, `api_key`, biến thể chữ hoa/thường.
- Secret ở JSON được escape, base64, URL encode hoặc xuống dòng.
- Giá trị ở field có kiểu dữ liệu khác text message.
- Email/điện thoại chứa Unicode, country code, punctuation và định dạng quốc tế.
- Secret nằm trong **Throwable**, MDC, user-agent, SQL, header hoặc object `toString()`.
- Regex bắt nhầm chuỗi vô hại, làm mất chứng cứ điều tra, hoặc không bắt do thay đổi format.
- Regex có catastrophic backtracking trên input dài.

Nếu regex được dùng để che một mẫu, hãy xây test case **positive** (phải che), **negative** (không che nhầm), **adversarial** (newline, escaped, encoded, giới hạn kích thước). Không chấp nhận “một regex che hết mọi dữ liệu nhạy cảm”.

Nếu một key/value thật sự chứa credential, phương án chắc chắn hơn là **không ghi field đó** thay vì mask phần đầu/cuối của nó.

## 16. Structured logging và ingest policy

Một event JSON an toàn có thể trông như sau:

~~~json
{
  "eventCode": "LOGIN_DENIED",
  "result": "DENIED",
  "reasonCode": "INVALID_CREDENTIALS",
  "requestId": "req-7f2a",
  "credentialPresent": true
}
~~~

**Không** tự cho rằng event này vô hại tuyệt đối: request ID vẫn có thể liên kết với người dùng ở hệ thống khác; cần quyền truy cập và lưu giữ phù hợp.

Khi pipeline có nhiều lớp:

- **Ứng dụng:** emit event theo allowlist. Không đưa field bí mật vào MDC hay JSON arguments.
- **Encoder/formatter:** cấu hình xuất các field được chọn, định dạng và escape đúng chuẩn. Nếu cần redact, kiểm tra các phần ngoài message.
- **Agent/collector:** áp dụng policy ingest, điều chỉnh export, giới hạn quyền xem secret/PII còn sót; metric và alert cho rule violation.
- **Index/storage:** mã hóa khi lưu/truyền, phân quyền đọc, audit truy cập, thời hạn retention và xóa theo yêu cầu.
- **Dashboard/export:** đảm bảo masking ở giao diện không phải đường bảo vệ duy nhất; bản gốc ở hệ thống lưu trữ vẫn cần xử lý.

Một collector có thể nhận file cũ hoặc bản gửi từ ứng dụng trước khi nâng cấp. Vì vậy, phải cân nhắc **dữ liệu lịch sử** trong index/archive/backups khi thay đổi policy.

## 17. Kiểm thử masking: dùng dữ liệu giả và assert không rò rỉ

Bài test có chất lượng không chỉ kiểm tra hàm `maskEmail` mà phải kiểm tra **toàn bộ output thực của appender/encoder**.

| Test | Dữ liệu giả | Kỳ vọng |
| --- | --- | --- |
| Email hợp lệ theo demo | `alice@example.test` | `a***@example.test` hoặc redaction toàn bộ theo policy |
| Email sai format | `not_an_email` | `[REDACTED]`, không in raw |
| Thẻ giả 16 chữ số | `4111111111111111` | `****1111` nếu policy cho phép last4 |
| Chuỗi thẻ không hợp lệ | `12-34-not-a-card` | `[REDACTED]` |
| Token giả | `TEST_SECRET_DO_NOT_LOG` | **Không xuất hiện ở bất cứ field hoặc stack trace nào** |
| Reason với newline | `INVALID_INPUT\nERROR forged` | Không xuất hiện dòng log giả |
| HTTP request | Authorization/Cookie/query chứa secret giả | Chỉ xuất method, route template, status, duration |
| Throwable | Message/cause chứa sentinel bí mật | Không lộ ở stack trace được xuất |
| MDC | Secret trong context cũ | Không còn ở event hoặc thread kế tiếp |
| JSON encoder | Field lạ hoặc nested object chứa secret | Bị loại theo allowlist hoặc fail validation |
| Async appender | Snapshot và log ở background | Không truyền raw object nhạy cảm vào queue |
| Nhiều sink | Console, file, network, audit | Mọi đích có phạm vi bảo vệ đúng policy |

Dùng **sentinel giả có độ đặc trưng cao** trong test, ví dụ `TEST_SECRET_DO_NOT_LOG`, rồi assert chuỗi đó không có trong text/JSON cuối cùng. Dùng email giả miền `.test` và số thẻ thử nghiệm công khai trong kiểm thử, không copy secret thật từ production.

Ví dụ kiểm thử tích hợp SLF4J/Logback nên sử dụng test appender in-memory và kiểm tra mọi trường của `ILoggingEvent` hoặc output từ encoder; nếu chỉ xem `getFormattedMessage()` mà quên `getThrowableProxy()` và MDC thì test còn thiếu.

Với Log4j 2, kiểm thử cả event JSON sau khi layout chạy, bởi `PatternLayout` và `JsonTemplateLayout` xuất dữ liệu khác nhau. Đồng thời chạy smoke test từ ứng dụng tới collector để xác minh các tầng ingest.

Một bộ CI nên báo fail khi thấy secret sentinel ở bất kỳ đầu ra nào; đồng thời kiểm tra rằng những event hợp lệ vẫn đủ thông tin giám sát, tránh “bảo mật bằng cách tắt toàn bộ logging”.

## 18. Kỹ thuật HMAC/pseudonym cho correlation có kiểm soát

Đôi khi cần liên kết nhiều log liên quan đến cùng một chủ thể nhưng không nên ghi email/định danh gốc. Khi mục đích hợp lệ và có quyền xử lý dữ liệu, có thể cân nhắc định danh giả dựa trên **HMAC**:

~~~text
subjectId nội bộ
   -> chuẩn hóa đầu vào và mục đích
   -> HMAC với khóa riêng của môi trường
   -> encoded pseudonym (giới hạn độ dài theo thiết kế)
   -> log pseudonym, eventCode, status
~~~

Đây là **sơ đồ kiến trúc**, không phải code sẵn sàng triển khai. Cần xác định quyền dùng khóa, nguồn entropy, thuật toán chuẩn, quy tắc xoay khóa, ổn định correlation và khả năng liên kết qua môi trường. Không lưu khóa HMAC ngay trong mã nguồn, config được log hay cùng một event.

- HMAC giúp chống đoán offline tốt hơn hash không khóa cho giá trị ít entropy.
- Dữ liệu pseudonym vẫn có thể thuộc phạm vi dữ liệu cá nhân vì khả năng liên kết.
- Mỗi dịch vụ có thể dùng khóa/phạm vi khác nhau để hạn chế correlation không cần thiết.
- Khi xoay khóa, cùng một subject có thể sinh mã khác; phải có kế hoạch vận hành cho điều đó.
- Nếu không cần correlation, **bỏ hẳn định danh** thường tốt hơn tạo pseudonym.

Không tự chế thuật toán “mã hóa” bằng Base64 hay thay vài ký tự; Base64 là encoding có thể đảo lại dễ dàng, không phải masking hay encryption.

## 19. Hiệu năng, async logging và xử lý khi lỗi mask

Một rule mask có thể được gọi trên mỗi log event. Với tải cao, cần theo dõi **chi phí** và **độ an toàn**:

- Ưu tiên phép biến đổi theo **schema và field type**, không phải chạy nhiều regex phức tạp trên toàn bộ text.
- Tránh tạo stack trace hoặc serialize full request chỉ để sau đó redact.
- Đừng truyền object có secret vào async logger rồi kỳ vọng worker mask trước khi object thoát khỏi process; queue, debug dump và appender khác vẫn có thể nhìn thấy object.
- Với sự kiện không thể mask theo policy, chọn **bỏ trường hoặc bỏ event phụ**, không ghi giá trị thô để “tránh mất log”.
- Masking thất bại là tín hiệu vận hành: tăng metric không chứa bí mật, cảnh báo và điều tra ở kênh được phép.
- Không viết error handler `catch(Exception ex){ log.error("mask failed raw={}", raw); }`; chính nhánh xử lý lỗi này có thể làm rò dữ liệu.
- Benchmark với lưu lượng và backend thật: throughput, latency, GC, drop rate, mức độ che và tỷ lệ false positive/negative.

Nếu backend có nhiều đích, một appender hỏng hoặc bỏ qua filter vẫn có thể tiết lộ dữ liệu. Quy trình review phải tính đầy đủ đường đi của event và các phương thức backup/export.

## 20. Ứng phó khi secret đã rơi vào log

Masking mới chỉ ngăn **những bản ghi trong tương lai**. Khi phát hiện một token hoặc dữ liệu cá nhân thật đã vào log, xử lý như một sự kiện an toàn thông tin:

1. **Hạn chế lan truyền:** tắt hoặc sửa nguồn phát log, giảm quyền truy cập phù hợp; không dùng cách tự in lại token để “xác minh”.
2. **Đánh giá phạm vi:** dòng thời gian, môi trường, file/index/collector, ứng dụng xem log, export và backup có thể chứa bản gốc.
3. **Thu hồi/xoay credential** nếu bí mật có hiệu lực; kiểm tra hành vi sử dụng bất thường bằng kênh an toàn.
4. **Xử lý bản sao:** lập kế hoạch xóa hoặc cô lập theo retention, khả năng hỗ trợ của hệ thống và yêu cầu chứng cứ/tuân thủ; không xóa tùy tiện làm mất bằng chứng sự cố.
5. **Thông báo đúng quy trình:** phối hợp bộ phận an toàn thông tin/quyền riêng tư và yêu cầu pháp lý áp dụng.
6. **Ngăn tái diễn:** thêm regression test, linter/config review, kiểm tra logging từ thư viện và collector.

Không coi việc che giá trị trên dashboard là đã hoàn tất xử lý nếu dữ liệu gốc vẫn còn ở file, index, export, cache hoặc archive.

## 21. Checklist thiết kế và code review

1. Có phân loại trường nhạy cảm và định nghĩa “được log” theo mục đích không?
2. Password, token, private key, cookie và thông tin xác thực có bị **cấm ghi** thay vì mask một phần không?
3. Log chỉ chứa **event code, trạng thái, mã lỗi, correlation ID được phép** và các trường có schema không?
4. Có code log cả request/response/DTO/headers/exception mà chưa đánh giá field bên trong không?
5. Mask ở nguồn có xử lý null, input sai, Unicode, dữ liệu dài và failure theo nguyên tắc fail closed không?
6. Nếu có email/last4, việc bộc lộ phần còn lại có thực sự cần và được policy cho phép không?
7. Có kiểm tra message, args, MDC, Throwable, suppressed cause, JSON fields, access logs và mọi appender không?
8. Regex ở backend chỉ là lớp phòng vệ phụ hay đang là biện pháp duy nhất?
9. Có test chứa sentinel giả và assert không xuất hiện trên sink cuối không?
10. Có test chống CR/LF injection, JSON escaping, data truncation và false positives không?
11. Có cơ chế bảo vệ log lưu trữ: TLS, encryption at rest, RBAC, audit access, retention và export control không?
12. Khi lộ secret, có quy trình incident response, credential rotation, xử lý bản sao và regression test không?

## 22. Câu hỏi tự kiểm tra

1. Vì sao `logger.info("request={}", request)` vẫn nguy hiểm dù dùng parameterized logging?
2. So sánh **không log**, **mask email**, **tokenization** và **HMAC pseudonym** theo khả năng khôi phục/liên kết.
3. Tại sao regex `token=\S+` không bảo vệ được `Authorization` header trong JSON hoặc `Throwable.getMessage()`?
4. Mask ở `%msg` của Logback/Log4j 2 có bảo đảm toàn bộ stack trace và MDC đã sạch không?
5. `MDC.put("email", rawEmail)` có thể ảnh hưởng bao nhiêu event?
6. Vì sao không nên log raw exception nếu nó chứa HTTP URL có credential?
7. Chuỗi `INVALID_INPUT\nERROR forged` trong ví dụ Java 17 được xử lý thế nào?
8. Nếu mask thất bại, trả dữ liệu gốc để tránh mất log có an toàn không?
9. Vì sao hash SHA-256 email trực tiếp vẫn có nguy cơ bị nhận diện?
10. Một token đã bị leak vào log hôm qua; thêm masking hôm nay có xử lý được mọi bản copy không?
11. Khi nào có thể dùng last4 và khi nào phải redact toàn bộ số thẻ?
12. Tại sao cần assert trên cả output thực của encoder/collector, không chỉ test một hàm mask?

**Gợi ý:** (1) đối tượng có thể chứa secret và backend sẽ render nó; (2) mức lộ thông tin/khả năng liên kết khác nhau; (3) regex chỉ xem một mẫu/chuỗi nhất định; (4) không; (5) nhiều event có cùng context; (6) exception message/cause có thể lộ secret; (7) chỉ map thành `OTHER`; (8) phải fail closed; (9) dễ brute-force tập nhỏ; (10) không, phải xử lý dữ liệu lịch sử; (11) theo mục đích và policy; (12) mọi sink có thể có cách encode riêng.

## 23. Tài liệu tham khảo chính thức

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu không nên log, sanitization, log injection, truyền và lưu log an toàn.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): vòng đời credential và giới hạn phơi bày secret.
- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): ghi message/parameters/Throwable.
- [Java SE 17 — java.util.logging.LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): trường message, parameters, thrown.
- [Java SE 17 — java.util.logging.Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html): định dạng `LogRecord`.
- [Logback — Layouts](https://logback.qos.ch/manual/layouts.html): `PatternLayout`, `%replace`, message và exception formatting.
- [SLF4J Manual](https://www.slf4j.org/manual.html): parameterized logging và Fluent API/key-value.
- [Log4j 2 — Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html): `%replace`, `RegexReplacement`, xử lý message và exception.
- [Log4j 2 — JSON Template Layout](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html): cấu trúc event template/resolver và các trường xuất JSON.

