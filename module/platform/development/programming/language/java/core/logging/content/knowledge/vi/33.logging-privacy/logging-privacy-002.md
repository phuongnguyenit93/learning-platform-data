# Bí mật trong log: bảo vệ dữ liệu nhạy cảm khi logging Java

## 1. Mục tiêu và bối cảnh

Log giúp tìm lỗi, quan sát hoạt động và điều tra sự cố, nhưng cũng có thể trở thành **kênh làm lộ bí mật**. Một lời gọi như `logger.debug("headers={}", headers)` có thể ghi cả `Authorization` token; một exception có thể chứa URL kèm API key; một JSON encoder có thể xuất toàn bộ đối tượng người dùng nếu developer đưa object đó vào message. Sau khi được ghi, dữ liệu còn có thể đi qua stdout, file, collector, dashboard, kho lưu trữ, bản sao lưu và hệ thống cảnh báo.

**Bí mật trong log** là vấn đề ngăn các giá trị đáng lẽ phải được giữ kín lọt vào sự kiện logging, bất kể mức log hay đích ghi. Nguyên tắc ưu tiên là **không tạo hoặc không đưa dữ liệu nhạy cảm vào log event ngay từ đầu**. Masking/redaction ở appender hoặc collector chỉ là lớp phòng vệ bổ sung, không thay thế kiểm soát tại nguồn.

Sau bài học, bạn có thể:

- Nhận diện mật khẩu, access token, API key, private key, session cookie, connection string và thông tin định danh cá nhân có thể xuất hiện trong log.
- Hiểu những đường rò rỉ ở Java: string concatenation, `toString()`, structured logging, exception, MDC, HTTP access logging, ORM SQL trace và asynchronous appender.
- Viết logging theo **allowlist** các trường an toàn, dùng mã sự kiện và correlation ID thay vì in payload bí mật.
- Phân biệt **không log**, **redact**, **mask**, **tokenize/pseudonymize** và **hash** cùng giới hạn của từng cách.
- Kiểm thử bằng dữ liệu giả có chủ đích, kiểm tra cả log ở ứng dụng lẫn các sink phía sau, và xử lý khi đã lỡ ghi secret.

## 2. Những loại dữ liệu không nên ghi nguyên văn

Không phải mọi giá trị trông như một chuỗi đều có cùng rủi ro. Dùng phân loại theo yêu cầu bảo mật thực tế của ứng dụng.

| Nhóm | Ví dụ | Rủi ro nếu bị ghi vào log |
| --- | --- | --- |
| Thông tin xác thực | Mật khẩu, mã OTP, recovery code, PIN | Có thể hỗ trợ chiếm tài khoản hoặc vượt xác thực |
| Token/phiên | Bearer access token, refresh token, session ID, cookie xác thực | Có thể bị dùng lại nếu còn hiệu lực |
| Khóa và chứng chỉ nhạy cảm | API key, client secret, private key, signing key, secret JWT | Có thể cho phép truy cập hoặc giả mạo |
| Kết nối hệ thống | JDBC URL có credential, DSN chứa password, thông tin tài khoản dịch vụ | Mở đường vào database hoặc dịch vụ nội bộ |
| Dữ liệu cá nhân | Email, số điện thoại, địa chỉ, số giấy tờ, dữ liệu sức khỏe, tài chính | Rủi ro riêng tư và tuân thủ chính sách bảo vệ dữ liệu |
| Dữ liệu ứng dụng bí mật | Thông tin giao dịch chưa công bố, request body riêng tư, nội dung tài liệu | Lộ bí mật kinh doanh hoặc thông tin người dùng |
| Metadata có thể kết hợp để nhận diện | IP, user-agent, device ID, địa điểm chính xác, trace gắn với định danh | Có thể liên kết hoạt động người dùng qua nhiều nguồn |

**Mật khẩu và token xác thực gần như không có lý do chính đáng để xuất nguyên văn trong application log.** Với dữ liệu cá nhân, mức xử lý tùy mục đích xử lý, chính sách nội bộ và nghĩa vụ pháp lý áp dụng; không tự coi email hoặc IP là “vô hại” chỉ vì chúng thường dùng làm trường tìm kiếm.

Ví dụ thông điệp **không nên tạo**:

```text
Login failed: username=alice@example.test password=demo-password
Request headers: Authorization=Bearer demo-token-123
Database URL: jdbc:vendor://db.internal/app?user=svc&password=demo-secret
```

Tất cả giá trị trên là **dữ liệu giả dùng để minh họa điều cần tránh**, không phải giá trị thực. Ngay cả khi token trong ví dụ đã hết hạn, vẫn nên loại nó khỏi log theo quy tắc thiết kế.

Thay thế bằng thông điệp có mục đích quan sát rõ ràng:

```text
event=login_denied requestId=req-74 result=DENIED reason=INVALID_CREDENTIALS
event=outbound_http_error service=payments route=/payments/{id} status=401
event=db_connection_failed pool=orders-db causeType=AUTHENTICATION_REJECTED
```

Lưu ý `requestId` nên do server sinh hoặc được kiểm tra cú pháp/độ dài; không đưa nguyên văn một header tùy ý do client kiểm soát vào log để làm correlation ID.

## 3. Mô hình đường rò rỉ của một log event

```text
Request / message / database / external API
                   |
                   v
       Java objects, maps, exceptions
                   |
          +--------+--------+
          |                 |
  message formatting   MDC/structured fields
          |                 |
          +--------+--------+
                   |
                   v
             Logging API
                   |
          filter / appender / encoder
                   |
                   v
          async queue / buffer
                   |
                   v
        stdout / stderr / file / network
                   |
                   v
        collector / index / dashboard / backup
```

Có ít nhất ba ranh giới phải bảo vệ:

1. **Trước khi tạo log event**: quyết định field được phép xuất, không serialize cả object có secret; xử lý message, exception, MDC và header.
2. **Trên đường xuất**: encoder/appender/collector áp thêm chính sách che dữ liệu và giới hạn kích thước; phát hiện lỗi hoặc dữ liệu bị lọt qua.
3. **Sau khi lưu**: quyền xem log, phân quyền theo nhóm, mã hóa đường truyền/lưu trữ, retention, truy vấn, export và audit truy cập.

Nếu chỉ redact sau khi ghi file, **file thô đã có bí mật**. Nếu chỉ redact trong collector, stdout/stderr hoặc queue trước collector vẫn có thể chứa secret. Do đó **kiểm soát tại nguồn là ưu tiên số một**.

## 4. Những cách Java vô tình đưa bí mật vào log

### 4.1. Nối chuỗi, parameterized logging và `toString()`

Với SLF4J, các câu lệnh sau đều nguy hiểm nếu object chứa thông tin nhạy cảm:

```java
// Mảnh mã minh họa trong ứng dụng có logger, request và credentials.
logger.debug("credentials=" + credentials);
logger.debug("credentials={}", credentials);
logger.info("request={}", request);
logger.trace("requestBody={}", request.getBody());
```

Dấu `{}` giúp trì hoãn **định dạng** theo cơ chế của SLF4J, **không làm nội dung tự an toàn**. Khi event được chấp nhận, backend có thể gọi `toString()` hoặc serializer của object, gây rò rỉ nếu object chứa password, token hoặc body. Phép nối chuỗi còn có thể làm `toString()` chạy ngay cả khi level bị tắt.

Java record tự sinh `toString()` có thể liệt kê các component trong biểu diễn mặc định. Ví dụ `record Credentials(String username, String password) {}` không nên được log nguyên object. Lombok `@ToString` hoặc IDE-generated `toString` cũng có rủi ro tương tự nếu không loại trường bí mật. Dù object có `toString()` đã mask, **không dựa duy nhất** vào masking đó để thay thế lựa chọn field an toàn ở call site.

### 4.2. Header, cookie, query string và request body

Những đường rò rỉ phổ biến:

- `Authorization: Bearer ...`, `Proxy-Authorization`.
- `Cookie`, `Set-Cookie` mang session identifiers hoặc thông tin xác thực.
- URL chứa token trong query như `?access_token=...`, `?api_key=...` hoặc đường dẫn có mã xác thực.
- HTTP request/response body, đặc biệt login, reset password, payment hoặc API tích hợp.
- Multipart payload, webhook secret, signed URL và callback URL có query nhạy cảm.

Ví dụ gọi `request.getHeader("Authorization")` để quyết định xác thực là thao tác nghiệp vụ hợp lệ, nhưng ghi raw header vào logger là hành vi khác. Nếu cần debug HTTP, nên log **HTTP method, route template, status, duration, retry count và một request ID an toàn**, thay vì toàn bộ headers/body.

Không dùng `request.getRequestURI()` kèm toàn bộ query string làm “route”; route template như `/orders/{id}` thường giảm rủi ro lộ định danh hoặc token trong URL. Với outbound HTTP client, bật wire logging/payload logging chỉ sau khi đã xem chính xác cơ chế loại headers và body nhạy cảm.

### 4.3. Exceptions và thông báo lỗi

Lời gọi:

```java
// Mảnh minh họa với SLF4J, exception là Throwable thực tế.
logger.error("Request failed", exception);
```

có thể ghi cả **exception message, cause chain và stack trace**. Bản thân stack trace thường chỉ chứa class/file/line; nhưng **message** của exception hoặc suppressed/cause có thể chứa URL, headers, SQL, request fragments hay dữ liệu người dùng. Ví dụ, một thư viện HTTP có thể đưa URI đầy đủ vào exception, hoặc mã ứng dụng tự tạo `IllegalArgumentException("Invalid token: " + token)`.

Không thể nói “stack trace luôn an toàn” cũng như không nên loại toàn bộ stack trace của mọi lỗi. Hướng thực tế là:
- Không tạo exception message chứa bí mật.
- Dùng lỗi đã chuẩn hóa, error code và metadata ít nhạy cảm.
- Khi thư viện ngoài có thể phát sinh message chứa secret, xem xét xử lý chẩn đoán ở ranh giới phù hợp; không in raw exception vào logger công khai.
- Chỉ ghi chi tiết cần thiết ở nơi có kiểm soát, theo quy trình bảo mật và chính sách truy cập.

### 4.4. MDC, trace context và structured fields

MDC là nơi thường chứa metadata theo thread. Nếu dùng:

```java
// Mảnh tích hợp với SLF4J.
org.slf4j.MDC.put("authorization", authHeader);
org.slf4j.MDC.put("password", password);
```

thì encoder có cấu hình xuất `%X` hoặc JSON MDC fields có thể vô tình ghi hai giá trị đó vào **mọi log event phát sinh trên thread**, kể cả log của thư viện khác.

Chỉ đưa vào MDC các field đã được cho phép, ví dụ `request_id` an toàn, `operation`, `service` hoặc trace/span ID theo chính sách. Không đặt Bearer token, Cookie hay PII raw vào MDC. Dọn/khôi phục MDC trong `finally` của task để không rò rỉ thông tin giữa các request khi thread pool tái sử dụng thread.

Structured logging không tự động bảo vệ dữ liệu. `logger.atInfo().addKeyValue("payload", request).log("...")` vẫn có thể làm encoder serialize toàn bộ request. **Chọn field rõ ràng** quan trọng hơn việc thay text log bằng JSON.

## 5. Ví dụ Java 17 độc lập: chỉ log dữ liệu được phép

Ví dụ sử dụng `java.util.logging` (JUL) có sẵn trong JDK, không cần Maven hoặc thư viện ngoài. Một đối tượng chứa email, password và bearer token giả lập. Thay vì log nguyên object, chương trình chỉ ghi **event code, request ID cố định và trạng thái**. Cuối cùng chương trình kiểm tra nội dung đã xuất có chứa ba giá trị nhạy cảm hay không.

Tạo file `SecretSafeLoggingDemo.java`:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class SecretSafeLoggingDemo {
    private record LoginInput(
            String email, String password, String authorization) {}

    private static final class CapturingHandler extends Handler {
        private final StringBuilder output;

        CapturingHandler(StringBuilder output) {
            this.output = output;
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            output.append(record.getLevel().getName())
                    .append(" | ")
                    .append(record.getMessage())
                    .append('\n');
        }

        @Override
        public void flush() {
            // Không có I/O hay bộ đệm ngoài StringBuilder.
        }

        @Override
        public void close() {
            flush();
        }
    }

    public static void main(String[] args) {
        LoginInput input = new LoginInput(
                "alice@example.test",
                "demo-password",
                "Bearer demo-access-token");

        Logger logger = Logger.getLogger("lesson.privacy.secrets");
        logger.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);

        StringBuilder captured = new StringBuilder();
        Handler handler = new CapturingHandler(captured);
        logger.addHandler(handler);

        try {
            // Chỉ log những trường đã được duyệt và không nhạy cảm.
            logger.info("event=login_denied requestId=req-74 result=DENIED");
            logger.warning(
                    "event=auth_failed requestId=req-74 reason=INVALID_CREDENTIALS");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        String output = captured.toString();
        System.out.print(output);
        boolean secretFound =
                output.contains(input.email())
                || output.contains(input.password())
                || output.contains(input.authorization());
        System.out.println("secretFound=" + secretFound);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac SecretSafeLoggingDemo.java
java SecretSafeLoggingDemo
```

**Stdout chính xác** trong một JVM mới, không có thành phần ngoài can thiệp vào logger của demo:

```text
INFO | event=login_denied requestId=req-74 result=DENIED
WARNING | event=auth_failed requestId=req-74 reason=INVALID_CREDENTIALS
secretFound=false
```

Giải thích:

1. `LoginInput` cố tình chứa ba giá trị không được xuất; cả ba là **dữ liệu giả**, không phải bí mật thật. Chương trình không gọi `input.toString()`, không gửi input cho logger và không lấy bất kỳ giá trị credential nào để tạo message.
2. `CapturingHandler` chỉ ghi level và message của hai record được tạo. `logger.setUseParentHandlers(false)` ngăn event chuyển tới root handler, tránh thêm output có timestamp hoặc gửi qua đích không phục vụ demo.
3. Phép kiểm tra `secretFound` được thực hiện trên text đã capture và cho kết quả `false`. Đây là **kiểm tra tính chất của đúng ví dụ**, không phải bằng chứng một ứng dụng production không thể rò rỉ dữ liệu qua mọi đường khác.
4. Các message sử dụng **event code** và `requestId` do chương trình kiểm soát, không dùng username/email hay token làm khóa tra cứu. Giá trị `reason` cũng là mã lỗi cố định thay vì thông điệp chứa dữ liệu do người dùng nhập.
5. Handler là thành phần mô phỏng cho một thread, không phải ứng dụng logging đa luồng hoàn chỉnh; việc dùng `StringBuilder` không đồng bộ ở đây được cố ý giới hạn vào một luồng.

### 5.1. Điều cần học từ ví dụ

**Allowlist khi tạo log** thường dễ kiểm toán hơn một bộ lọc theo blacklist: từ đầu chỉ chọn những field hữu ích và được phép. Nếu event chưa từng chứa password hay access token, appender không cần “cứu” chúng bằng regex.

Trong dự án có nhiều logger/backend, đặt cơ chế kiểm thử ở sink có kiểm soát để xác nhận không chỉ message mà còn cả exception, MDC, key-value fields, các encoder và collector. Kiểm tra chỉ trên text message sẽ **không phát hiện** bí mật nằm ở một trường JSON khác.

## 6. Logging an toàn với SLF4J và structured logs

SLF4J thường được dùng như facade với Logback hoặc Log4j 2 phía sau. Có thể tạo message rõ ràng theo dạng:

```java
// Đoạn tích hợp: logger là SLF4J logger; các giá trị được kiểm soát.
logger.info("event=login_denied requestId={} reason={}",
        safeRequestId, "INVALID_CREDENTIALS");
```

Đây **không phải chương trình độc lập**; nó giả định đã có logger và request ID được chuẩn hóa/được ứng dụng sinh ra. Đừng thay `safeRequestId` bằng header tùy ý chưa kiểm tra. Không chèn `credentials`, `headers` hoặc `request` để tiện debug.

Với **SLF4J 2.x**, fluent API có thể tạo key-value pairs:

```java
// Đoạn tích hợp cần SLF4J 2.x và backend/encoder hỗ trợ structured fields.
logger.atInfo()
      .addKeyValue("event", "login_denied")
      .addKeyValue("request_id", safeRequestId)
      .addKeyValue("result", "DENIED")
      .log("Authentication rejected");
```

Để JSON encoder xuất các field này, backend phải được cấu hình tương ứng. Dù ở dạng key-value, nếu `addKeyValue("authorization", header)` thì token vẫn có thể bị lộ. **Structured logging chỉ thay hình thức dữ liệu**, không đảm bảo field hợp lệ về bảo mật.

### 6.1. Thiết kế sự kiện theo schema và allowlist

Một schema an toàn cho log xác thực có thể quy định:

| Tên field | Ví dụ | Ghi chú |
| --- | --- | --- |
| `event` | `login_denied` | Tên sự kiện cố định |
| `request_id` | `req-74` | Sinh/kiểm tra bởi server, không chứa input tự do |
| `result` | `DENIED` | Mã kết quả cố định |
| `reason` | `INVALID_CREDENTIALS` | Không nêu username có tồn tại hay không |
| `latency_ms` | `23` | Số đo không nhạy cảm |
| `service` | `identity-api` | Giá trị cấu hình không chứa bí mật |

Không thêm mặc định `password`, `access_token`, `refresh_token`, `cookie`, `authorization` hoặc toàn bộ `request_body`. Trường `user_id` cũng có thể là dữ liệu cá nhân; nếu không cần, bỏ nó. Nếu cần định danh cho chẩn đoán, đánh giá phương án pseudonymous ID, retention và quyền truy cập theo mục đích thực tế.

JSON encoder phải escape chuỗi hợp lệ. Nếu dựng thủ công bằng nối chuỗi có dữ liệu do người dùng nhập, có thể xuất JSON sai cú pháp hoặc gặp **log injection**: ký tự xuống dòng/điều khiển làm log trông như một record khác. Dùng encoder chuẩn, giới hạn độ dài và chuẩn hóa các field có thể được phép nhưng do client kiểm soát.

### 6.2. Dùng marker và mã lỗi thay cho secret

Đôi khi muốn biết một request “có Authorization header hay không”. Log một boolean hoặc trạng thái phân loại thay vì header:

```java
// Mảnh code tích hợp; không ghi giá trị của Authorization header.
logger.debug("event=auth_header_check present={}",
        authorizationHeader != null);
```

Ngay cả `present=true/false` cũng chỉ nên log nếu thực sự hữu ích. Với lỗi xác thực, tránh thông điệp quá chi tiết có thể giúp kẻ tấn công phân biệt tài khoản tồn tại hay không. Chính sách thông tin phản hồi cho client và thông tin lưu trong log đều cần đánh giá riêng.

## 7. Redaction, masking, hashing: công dụng và giới hạn

| Kỹ thuật | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| **Không log** | Loại field ngay từ call site/schema | Phải kiểm soát toàn bộ code path có thể log dữ liệu đó |
| **Redaction** | Thay toàn bộ giá trị bằng `[REDACTED]` hoặc bỏ field | Nếu làm muộn, dữ liệu raw đã tồn tại ở tầng trước |
| **Masking** | Chỉ hiện một phần (ví dụ 4 ký tự cuối) | Phần còn lại vẫn có thể nhạy cảm hoặc đủ để liên kết danh tính |
| **Pseudonymization/tokenization** | Thay định danh bằng token có quản lý | Vẫn có thể liên kết hành vi và cần bảo vệ bảng ánh xạ |
| **Hashing** | Tính giá trị băm để so sánh | Hash không tự động làm dữ liệu vô danh; input ít giá trị có thể bị đoán, không phù hợp để log password |
| **Encryption at rest/in transit** | Bảo vệ kho lưu trữ và đường truyền | Người có quyền giải mã/truy cập log vẫn có thể thấy raw secret |

**Redaction tại nguồn** là chính sách tốt cho những trường cố định. Một filter ở Logback encoder/appender hoặc Log4j 2 layout có thể đóng vai trò **defense in depth**, giúp giảm thiểu lỗi từ một logger không tuân thủ schema. Tuy nhiên, pattern regex thông thường khó phát hiện mọi biến thể: token lồng JSON, chuỗi URL-encoded, Base64, tên header khác nhau, dữ liệu chia trên nhiều dòng hoặc object tùy chỉnh.

Không dùng việc lọc chuỗi theo một vài từ khóa (`password=`, `token=`) như tuyên bố rằng toàn bộ log đã an toàn. Các API/framework có thể biểu diễn secret ở nhiều dạng khác nhau hoặc gắn chúng ở các field khác message.

### 7.1. Rủi ro của hashing

Ví dụ hash một email bằng SHA-256 rồi log giá trị đó vẫn có thể cho phép người xem đoán email từ một tập ứng viên nhỏ và băm lại để so sánh. Hash có thể trở thành một **định danh ổn định để liên kết người dùng** qua nhiều sự kiện. Khi cần đối chiếu mà không lộ danh tính, cân nhắc cơ chế có khóa như HMAC, quản lý khóa riêng và kế hoạch thay khóa; bản thân HMAC cũng là dữ liệu pseudonymous cần kiểm soát retention/truy cập.

**Không log hash mật khẩu từ database** chỉ vì nó không phải mật khẩu dạng rõ. Hash mật khẩu là dữ liệu xác thực cần được bảo vệ.

### 7.2. Masking chỉ là một quyết định nghiệp vụ

Hiển thị `****1234` của một số định danh có thể giúp tổng đài xác nhận giao dịch, nhưng có thể không phù hợp với mọi loại dữ liệu hoặc mọi chính sách. Đừng áp quy tắc “hiện 4 ký tự cuối” bừa bãi cho JWT, API key, session ID hay thông tin cá nhân. Với các token này, thông thường tốt hơn là **không log**.

## 8. Các điểm cấu hình thường gây rò rỉ

### 8.1. Logback, Log4j 2 và pattern/JSON encoder

Với Logback, pattern như `%msg` xuất message; `%ex`/`%throwable` có thể xuất chi tiết exception; `%X` hoặc `%mdc` xuất MDC. Các encoder JSON có thể bao gồm key-value fields, arguments, exception hoặc custom attributes tùy cấu hình. Log4j 2 cũng có pattern/layout và context map/ThreadContext tương ứng.

Vì vậy, khi kiểm tra một appender phải hỏi:
- Nó nhận được message, parameter object, exception hay các trường MDC nào?
- Formatter/encoder gọi `toString()` hoặc JSON serialization trên những object nào?
- Có bật include-all MDC/headers/arguments hay không?
- Output có được gửi tiếp sang secondary appender, fallback hay collector khác không?
- Một rule masking có xử lý cả message, exception text và structured fields không?

Ví dụ một JSON event không an toàn:

```json
{
  "event": "login_denied",
  "request_id": "req-74",
  "authorization": "Bearer demo-token",
  "password": "demo-password"
}
```

Thay bằng:

```json
{
  "event": "login_denied",
  "request_id": "req-74",
  "result": "DENIED",
  "reason": "INVALID_CREDENTIALS"
}
```

Hai object JSON chỉ là **minh họa schema**, không phải dữ liệu quan sát thực tế. Trường `authorization` hoặc `password` phải bị loại ngay từ bước tạo event; không nhất thiết cần giữ chúng dưới dạng `[REDACTED]` nếu schema không đòi hỏi.

### 8.2. HTTP logging và access log

Access log của server có thể mặc định ghi method, path, status, duration, user-agent hoặc IP. Khi tùy biến để thêm headers, query string hay request body, rủi ro tăng rõ rệt. Kiểm tra các tính năng debug/wire logging của servlet framework, HTTP client, reverse proxy, API gateway và service mesh; secret có thể bị ghi **ngoài ứng dụng Java**.

Ưu tiên:
- Route template hoặc tên endpoint thay cho URL đầy đủ chứa query.
- Status, duration, method và request ID an toàn.
- Không log `Authorization`, `Cookie`, `Set-Cookie` và request/response body ở endpoint xác thực hoặc thanh toán.
- Tắt hoặc giới hạn wire logging; cấu hình allowlist những trường cần thiết.
- Kiểm tra cả error path, timeout và retry, vì thư viện có thể in raw request khi lỗi.

### 8.3. SQL và ORM logging

Bật log SQL có thể hữu ích để điều tra hiệu năng, nhưng khi thêm **binding parameter values**, câu truy vấn có thể lộ email, token, số giấy tờ hoặc dữ liệu nhạy cảm khác. Phân biệt:
- SQL template có placeholders, ví dụ `SELECT ... WHERE email = ?`.
- Giá trị bind thực tế, ví dụ email được truyền tới query.

Không ghi tất cả bind values vào log production nếu không có kiểm soát đặc biệt. Với exception database, connection URL hoặc driver diagnostics có thể chứa thông tin kết nối; kiểm tra nơi exception được xử lý. Đừng tự gắn credential vào URI/connection string có thể bị exception hiển thị.

### 8.4. MDC/ThreadContext, async và luồng nền

Nếu logging bất đồng bộ, event có thể được queue trong memory, serialize ở thread khác hoặc đưa đến collector. Việc “redact ở cuối pipeline” có thể để lại dữ liệu raw trong queue, heap dump hoặc diagnostic output. Vì vậy, tránh đưa secret vào event ngay từ đầu.

Thread pool tái sử dụng worker; nếu MDC của một request không được dọn, request kế tiếp có thể mang metadata cũ. Dùng `try/finally` hoặc cơ chế scope/context propagation có quản lý để khôi phục trạng thái đúng. Tuyệt đối không lưu credential thô trong MDC với kỳ vọng sẽ tự biến mất khi request kết thúc.

## 9. Test để phát hiện bí mật trong log trước khi release

Không thể chứng minh “mọi log luôn an toàn” chỉ với một regex. Nhưng có thể thiết kế bộ test có khả năng phát hiện rò rỉ sớm và ngăn tái phạm.

### 9.1. Dữ liệu giả (canary) có chủ đích

Tạo thông tin kiểm thử **không còn quyền truy cập thật**:
- Mật khẩu giả có chuỗi nhận diện.
- Token giả có prefix dễ nhận ra.
- Email giả với domain dành cho ví dụ như `example.test`.
- Giá trị header/cookie giả.
- Dữ liệu chứa dấu ngoặc kép, dấu gạch chéo, ký tự xuống dòng hoặc dấu Unicode để thử escaping.

Sau đó kích hoạt các đường:
1. Xác thực thành công và thất bại.
2. Lỗi 4xx/5xx, exception và nested cause.
3. Timeout, retry, cancellation và shutdown.
4. HTTP inbound/outbound và database error.
5. Async logging, MDC/context và các appender dự phòng.

Tìm tất cả canary trong log được capture **ở nhiều tầng**. Kiểm tra message text, structured fields, stack trace, raw file, console stream, collector/index và backup nếu có quyền test. Với test offline, tránh tải raw log nhạy cảm thật xuống laptop cá nhân.

### 9.2. Kiểm thử bằng assertion

Kiểm tra tương tự ví dụ Java 17:
- Event an toàn có mặt.
- Không có chuỗi password/token/email giả.
- Không có key không được phép như `authorization` hoặc `cookie` trong schema JSON.
- Không có log injection làm một event biến thành nhiều dòng giả.
- Khi appender dùng redaction, kiểm thử cả biến thể uppercase/lowercase, header format, giá trị escape và JSON nested.

Cần bổ sung test cho **code path chưa được nhìn thấy**: tìm những lời gọi logger ghi trực tiếp các object request, response, credential, user entity, headers, claims hoặc exception được tạo từ dữ liệu nhạy cảm. Static analysis và review code là lớp bổ sung quan trọng; grep các từ khóa không thay thế đánh giá luồng dữ liệu (data flow).

### 9.3. Negative test và false confidence

Nếu test chỉ tìm chuỗi `password=`, nó có thể bỏ qua `"pwd":"..."` hoặc một JSON field `secretKey`. Nếu kiểm thử chỉ dùng logger INFO, một đường DEBUG/TRACE bật khi điều tra sự cố có thể lộ bí mật. Nếu chỉ kiểm tra application file, access logs ở proxy hoặc collector có thể vẫn chứa dữ liệu.

Bộ test nên gồm cả **thay đổi cấu hình level** trong môi trường kiểm thử và kiểm tra encoder thực tế. Không vì mục đích test mà mở DEBUG/TRACE cho toàn bộ production hoặc tạo ra bí mật thật để thử.

## 10. Quyền truy cập, lưu trữ và vòng đời của log

Ngăn rò rỉ ở call site là cần thiết nhưng chưa đủ; dữ liệu còn có thể tồn tại trong nơi ghi và vận chuyển:

- **Quyền đọc:** giới hạn người/ứng dụng được truy cập file, dashboard, log search, export, snapshot và backup theo nguyên tắc ít quyền nhất.
- **Đường truyền:** dùng kênh bảo mật và xác thực phù hợp giữa agent, collector và backend.
- **Lưu trữ:** mã hóa khi lưu nếu chính sách yêu cầu; không coi encryption là thay thế cho redaction vì người được cấp quyền vẫn có thể đọc dữ liệu.
- **Retention:** giữ log đúng thời hạn cần thiết, giảm bản sao thừa, kiểm soát việc xóa theo chính sách và nghĩa vụ pháp lý áp dụng.
- **Tách môi trường:** không sao chép raw production logs có dữ liệu người dùng vào test/demo hoặc chia sẻ trên chat/ticket công khai.
- **Alert và nội dung trích dẫn:** dashboard, notification và incident tickets cũng có thể tái phát tán secret nếu chèn nguyên message.

Cần hiểu rằng sau khi log bị phát tới nhiều sink, việc xóa một file cục bộ **không xóa** mọi bản sao ở backend, export hay backup. Chính sách xử lý phải bao phủ vòng đời dữ liệu trên toàn hệ thống.

## 11. Khi phát hiện bí mật đã lọt vào log

Một sự cố lộ secret cần được xử lý như một sự kiện an ninh, không chỉ là lỗi format:

1. **Ngăn tiếp tục phát sinh:** vô hiệu hóa log path vi phạm, rollback cấu hình debug hoặc triển khai bản sửa để loại field tại nguồn. Không in thêm bí mật vào ticket hay kênh chẩn đoán khi đang sửa.
2. **Xác định phạm vi:** loại secret nào, xuất hiện từ lúc nào, ở những sink/replica/backup nào, ai có quyền truy cập, có thể đã được export hoặc gửi cảnh báo chưa.
3. **Vô hiệu hóa/rotate credential:** với access token, API key, cookie/session hoặc password bị lộ, thực hiện revoke/rotation/reset theo chính sách của hệ thống. **Chỉ che log hiện có không làm một credential đã bị lộ trở nên an toàn.**
4. **Kiểm soát dữ liệu đã lưu:** hạn chế quyền truy cập, thực hiện xóa/retention/quarantine theo hướng dẫn an ninh và nghĩa vụ quản trị áp dụng; chú ý collector và backup.
5. **Đánh giá và thông báo:** phối hợp đội an ninh/quyền riêng tư, điều tra dấu hiệu bị lạm dụng và thực hiện nghĩa vụ thông báo nếu có. Không tự suy đoán mọi trường hợp đều có cùng yêu cầu pháp lý.
6. **Ngăn tái diễn:** thêm test canary, schema allowlist, review các điểm log raw object, HTTP headers, exceptions và MDC; theo dõi coverage qua các backend.

**Không đăng lại token thật để xin hỗ trợ**. Dùng tên field, thời điểm, vị trí log và giá trị giả hoặc fingerprint được phép. Đối với secret vẫn còn hiệu lực, hành động quan trọng là revoke/rotate theo quy trình, không phải chỉ thay chuỗi trong message.

## 12. Sai lầm thường gặp và cách sửa

| Sai lầm | Vì sao nguy hiểm | Hướng sửa |
| --- | --- | --- |
| Log nguyên `request`, `headers` hoặc `credentials` | `toString`/serializer có thể in token/password/cookie | Chọn field an toàn theo allowlist |
| Tưởng `logger.debug` tắt thì mọi giá trị đều không bị tạo | Nối chuỗi, `toJson`, accessor vẫn có thể chạy tại call site | Tránh tạo secret trong log; dùng guard/lazy để giảm cost, không coi đó là biện pháp bảo mật |
| Dùng `{}` rồi nghĩ token được che | Parameterized logging định dạng, không loại secret | Không truyền token/password làm đối số |
| Ghi nguyên exception | Message/cause có thể chứa URI, SQL, headers, input | Kiểm soát nơi tạo exception và cách log lỗi |
| Đưa Authorization header vào MDC | Encoder xuất MDC ở mọi log của thread | Chỉ dùng metadata được phép, cleanup bằng scope |
| Tắt INFO nhưng bật TRACE khi sự cố | Đường trace có thể lộ dữ liệu ẩn trước đó | Kiểm thử mọi log level có thể bật |
| Dựa chỉ vào regex ở collector | Log thô đã đi qua stream/queue/file; regex dễ bỏ sót | Loại secret tại nguồn, redaction ở sink như lớp bổ sung |
| Hash email/token rồi coi là vô danh | Dễ liên kết hoặc đoán input ít giá trị | Hạn chế định danh, dùng pseudonymization có chính sách nếu cần |
| Log toàn bộ request body để debug | Có thể chứa credential, tài liệu cá nhân, thanh toán | Chỉ log route/status/duration và field an toàn |
| Bật SQL bind logging rộng rãi | Giá trị truy vấn có thể chứa dữ liệu riêng tư | Log SQL template/metrics; kiểm soát param logging |
| Chỉ kiểm tra một file log | Các bản sao console/collector/backup vẫn có thể lộ | Test và quản trị toàn pipeline |
| Đã xóa log thì token không còn nguy hiểm | Secret có thể bị copy/export trước đó | Revoke/rotate và điều tra truy cập |

## 13. Bài tập kiểm tra hiểu biết

**Câu 1.** Dòng sau có an toàn không?

```java
logger.info("Login failed: {}", credentials);
```

**Không thể coi là an toàn.** `credentials` có thể được render bằng `toString()` hoặc serializer có chứa password. Thay bằng event code, request ID an toàn và mã lý do cố định. Câu lệnh trên là **mảnh code tích hợp**, không phải lớp Java độc lập.

**Câu 2.** Ứng dụng đã che `Authorization` trên log console nhưng vẫn có một raw JSON appender. Có thể kết luận token không bị lộ không?

**Không.** Mỗi appender/encoder có thể xuất các field khác nhau. Nếu raw event có chứa token, appender JSON vẫn có thể ghi nó. Loại field ngay từ nguồn và test mọi sink.

**Câu 3.** Dùng SHA-256 để băm email rồi log hash đã biến email thành dữ liệu vô danh chưa?

**Chưa chắc.** Email thường có thể đoán từ danh sách ứng viên và được liên kết qua nhiều log; hash không phải cơ chế ẩn danh tuyệt đối. Cần đánh giá nhu cầu, khả năng liên kết, quyền truy cập, retention và phương án có khóa nếu phù hợp.

**Câu 4.** Một lỗi HTTP bao gồm URL có query token. Nếu ghi `logger.error("failed", exception)` thì token có thể xuất hiện không?

**Có thể.** Exception message/cause được backend định dạng có thể chứa URL. Cần xử lý lỗi bằng mã/metadata an toàn và tránh tạo exception message chứa secret.

**Câu 5.** Khi token thật đã xuất hiện trong log và đã bị người không nên có quyền truy cập nhìn thấy, chỉ sửa code và xóa một dòng là đủ chưa?

**Chưa.** Token có thể còn hiệu lực hoặc đã được sao chép. Cần revoke/rotate theo chính sách, kiểm soát nơi lưu, điều tra phạm vi và bổ sung kiểm thử.

## 14. Checklist trước khi đưa logging vào production

1. Logger chỉ nhận những field **thật sự cần cho chẩn đoán/vận hành**; credentials, token và private key không vào message, args hay structured fields.
2. Không log raw headers, URL query, request/response body hoặc SQL bind values chứa dữ liệu nhạy cảm.
3. Exception và error messages không vô tình chứa token, URL kèm secret, dữ liệu tài khoản hoặc payload.
4. `toString()` của record/entity, serializer JSON, Lombok-generated methods và log raw objects đã được review.
5. MDC/ThreadContext chỉ chứa metadata được phép; task cleanup trong `finally`; không rò rỉ giữa thread.
6. Các appender/encoders Logback/Log4j 2/JUL và collector downstream đã được kiểm tra, kể cả fallback, error logs và JSON fields.
7. Nếu có redaction/masking bổ sung, đã test đa dạng format và biết giới hạn của nó.
8. Đã kiểm thử bằng canary giả ở INFO/DEBUG/TRACE, exception path, HTTP path và async/collector theo cấu hình thực tế.
9. Quyền truy cập, bảo vệ đường truyền, retention, export và backup của log đáp ứng chính sách bảo mật/riêng tư.
10. Có quy trình phản ứng khi secret lọt log, bao gồm cô lập, revoke/rotate và ngăn tái diễn.

**Kết luận:** Bảo vệ bí mật trong Java logging bắt đầu **trước khi gọi logger**: chỉ tạo sự kiện chứa dữ liệu được phép, tránh log raw object, header, token, password, exception message nhạy cảm và MDC không kiểm soát. Redaction tại encoder/collector, phân quyền, retention và kiểm thử bằng canary là các lớp bảo vệ bổ sung. Một log hữu ích phải giúp giải thích sự cố mà **không trở thành bản sao của bí mật hoặc dữ liệu cá nhân**.