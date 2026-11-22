# Tránh ghi thông tin bí mật hoặc dữ liệu cá nhân vào message và log khi xử lý exception trong Java

## 1. Mục đích của chẩn đoán lỗi an toàn

Exception và log giúp trả lời **thao tác nào thất bại, khi nào, ở đâu, thuộc loại lỗi gì và cần xử lý tiếp thế nào**. Tuy nhiên, nếu lỗi được xây từ dữ liệu đầu vào hoặc thông tin của dependency, message và stack trace có thể vô tình chứa password, token, cookie, hồ sơ khách hàng, nội dung request hay dữ liệu riêng tư. Khi lỗi được ghi vào file, stdout, nền tảng giám sát, crash report hoặc trả về HTTP, dữ liệu đó có thể tồn tại trong nhiều bản sao với quyền truy cập và thời gian lưu khác nhau.

**Nguyên tắc:** chỉ ghi thông tin **cần thiết, an toàn và được phép**. Một bản ghi lỗi tốt thường có mã sự kiện, operation thuộc danh sách cho phép, mã lỗi ổn định, thời gian, correlation ID không nhạy cảm và trạng thái nghiệp vụ. Nó không cần chứa raw payload hay bất kỳ credential nào.

Một số khái niệm:

- **Secret:** thông tin dùng để xác thực hoặc cấp quyền, như password, API key, access token, refresh token, JWT, cookie phiên, OTP, private key.
- **PII / dữ liệu cá nhân:** thông tin liên quan đến một người có thể nhận diện, trực tiếp hoặc khi kết hợp với dữ liệu khác; ví dụ email, số điện thoại, địa chỉ, mã định danh, lịch sử hoạt động.
- **Exception message:** `Throwable.getMessage()` và các thông điệp được gắn vào Throwable.
- **Log sink:** bất kỳ đích nào nhận dữ liệu log, như console, file, cloud collector, APM, tracing agent, audit store và dịch vụ cảnh báo.
- **Data minimization:** chỉ thu thập và lưu đúng các trường cần cho mục đích đã được xác định.

Cần phân biệt **không đưa dữ liệu vào log** với **che dữ liệu ở giao diện người dùng**. Hai kiểm soát đều cần nhưng không thay thế nhau.

## 2. Các loại dữ liệu đặc biệt dễ bị lộ

| Nhóm dữ liệu | Ví dụ | Rủi ro thường gặp |
| --- | --- | --- |
| Credential | Password, token, API key, cookie, OTP | Chiếm đoạt tài khoản, mạo danh yêu cầu |
| Dữ liệu nhận diện | Họ tên, email, số điện thoại, địa chỉ | Lộ danh tính, liên hệ trái phép, liên kết hồ sơ |
| Dữ liệu nhạy cảm theo ngữ cảnh | Thông tin sức khỏe, tài chính, đơn hàng, vị trí | Xâm phạm quyền riêng tư và bí mật kinh doanh |
| Request/response tự do | JSON body, file upload, HTTP header | Chứa giá trị khó dự đoán hoặc dữ liệu bên thứ ba |
| Thông tin nội bộ | Connection string, cấu hình, đường dẫn, SQL đầy đủ | Lộ hạ tầng, endpoint và đôi khi credential |
| Mã tương quan | Request ID, trace ID, entity ID | Có thể liên kết hoạt động nếu không thiết kế hợp lý |

Không thể chỉ nhìn **tên trường** rồi kết luận nó an toàn. Ví dụ `userId` có thể là một định danh cá nhân, `requestId` có thể do client gửi lên chứa email, và `url` có thể có query parameter chứa token. Mỗi trường cần được phân loại theo **nguồn và mục đích**.

Phương án ít rủi ro nhất thường là **không thu thập giá trị nhạy cảm** thay vì thu thập rồi cố xóa khi đã gửi tới nhiều nơi.

## 3. Exception message không nên nối trực tiếp với dữ liệu đầu vào

Những mẫu dưới đây là **ví dụ nguy hiểm**, không phải mã khuyến nghị:

```java
throw new IllegalArgumentException("Invalid password: " + password);
throw new IllegalStateException("Unexpected bearer token: " + token);
throw new IOException("Remote request failed, body=" + requestBody);
```

Các biến `password`, `token`, `requestBody` do ứng dụng giả định đã định nghĩa. Một message có thể đi qua nhiều tầng như sau:

```text
Input của người dùng hoặc dependency
    -> exception message
    -> cause / suppressed exception
    -> logger / APM / console / HTTP error handler
    -> log collector, index, alert, export, backup
```

Ngay cả khi một controller cuối cùng trả response an toàn, một tầng trung gian hoặc auto-instrumentation agent có thể đã ghi nguyên Throwable.

Thay vì nhúng giá trị, dùng loại exception phù hợp và **mã phân loại lỗi**:

```java
throw new IllegalArgumentException("INVALID_CREDENTIALS");
```

Đây là đoạn trong phương thức, không phải chương trình độc lập. Trong hệ thống lớn, một class exception có `errorCode` là enum có thể rõ hơn một chuỗi tự do. Dù vậy, việc trả về mã “INVALID_CREDENTIALS” cho client hay không còn phụ thuộc chính sách không để lộ sự tồn tại tài khoản.

Đừng giả định message của thư viện/SDK là an toàn. Một HTTP client có thể đưa URL, header hoặc response body vào lỗi; JDBC driver có thể chứa SQL và dữ liệu; nhiều API bên ngoài có thể trả nguyên nội dung người dùng. **Nội dung exception từ dependency cần được coi là không đáng tin về tính an toàn dữ liệu.**

## 4. Những lệnh ghi lỗi có thể vô tình tiết lộ dữ liệu

### `getMessage()` và `toString()`

`ex.getMessage()` trả thông điệp từ nguồn lỗi; `ex.toString()` thường gồm class name và localized message. Hai cách ghi này đều có thể xuất secret:

```java
logger.error("Failed: {}", ex.getMessage());
System.err.println(ex);
```

Dòng đầu là **mảnh API logging kiểu SLF4J**, dòng thứ hai là Java SE trong phương thức có `ex`. Cả hai chỉ an toàn nếu dữ liệu Throwable đã được phép xuất qua sink cụ thể.

### Stack trace, cause và suppressed exceptions

`ex.printStackTrace()` hoặc nhiều framework khi gọi:

```java
logger.error("Operation failed", ex);
```

sẽ ghi loại lỗi, message, các stack frame, **cause chain** và thường cả **suppressed exceptions**. Message của `ex.getCause()` hoặc `ex.getSuppressed()` có thể mang dữ liệu nhạy cảm dù message của lỗi ngoài cùng đã được đổi thành chuỗi an toàn.

Không được suy ra rằng `throw new ServiceException("Safe message", original)` làm sạch toàn bộ cây lỗi. Nếu logger in cause, message của `original` vẫn có thể lộ. Tuy nhiên cũng không nên xóa mọi cause một cách vô điều kiện vì sẽ phá khả năng chẩn đoán; cần phân loại nơi nào được giữ Throwable đầy đủ và nơi nào chỉ được ghi event an toàn.

### `toString()` của DTO

Một `record` Java có `toString()` mặc định thường bao gồm giá trị các thành phần. Vì vậy:

```java
logger.debug("request={}", request);
```

là **mảnh code framework cần đánh giá**, kể cả khi không gọi `getMessage()`. Nếu `request` chứa password hoặc token, chuỗi biểu diễn có thể in toàn bộ. An toàn hơn là không log nguyên object chứa thông tin riêng tư, và tạo log event từ các trường allowlist.

## 5. Tách lỗi nội bộ khỏi thông báo công khai

Một request thất bại thường có ít nhất hai kênh:

**Kênh client:** báo mã lỗi ổn định, thông điệp dễ hiểu không tiết lộ cấu trúc hệ thống, và request ID không nhạy cảm khi cần hỗ trợ.

```json
{
  "error": "SERVICE_UNAVAILABLE",
  "message": "The service is temporarily unavailable",
  "requestId": "req-7"
}
```

Đây là **response JSON minh họa**; không phải định dạng mặc định của Java hay framework.

**Kênh vận hành:** ghi sự kiện dạng `event=OPERATION_FAILED`, `operation=FETCH_PROFILE`, `reason=UPSTREAM_UNAVAILABLE`, `request_id=req-7`, thời gian và số lần retry nếu cần. Không cần sao chép exception text từ dependency.

Đừng trả `ex.toString()` hoặc toàn bộ stack trace vào HTTP 500. Điều đó có thể tiết lộ token, nội dung đầu vào, tên class và đường dẫn nội bộ. **Request ID** phục vụ liên kết lỗi không được mang vai trò bearer token hay cấp quyền truy vấn dữ liệu.

Nếu cần xử lý sâu một sự cố, dùng quy trình chẩn đoán nội bộ được phân quyền và giới hạn thời gian, thay vì mặc định đưa toàn bộ raw exception vào log mà đội support, nhà cung cấp hoặc client có thể xem.

## 6. Danh sách trường cho phép thay vì log mọi thứ rồi che

Một schema sự kiện điển hình:

| Field | Nguồn phù hợp | Yêu cầu |
| --- | --- | --- |
| `event` | Hằng số/enum | Không nhận từ request |
| `operation` | Enum `FETCH_PROFILE` hoặc `CREATE_ACCOUNT` | Không ghép user-supplied URL |
| `reason` | Enum `INVALID_INPUT` hoặc `UPSTREAM_UNAVAILABLE` | Không biến raw exception message thành mã |
| `request_id` | Opaque ID do hạ tầng tạo/kiểm soát | Không dùng token/email làm ID |
| `duration_ms` | Số đo runtime | Không nhúng payload |
| `outcome` | Enum `SUCCESS`, `FAILURE`, `CANCELLED` | Phân biệt kết quả thật |
| `dependency` | Tên dịch vụ từ cấu hình đã biết | Không dùng endpoint tự do có query |

Đây là **allowlist**: mã chỉ cho phép những trường đã được xét đủ an toàn. Structured logging theo JSON hay placeholder không tự tạo ra bảo mật. Câu:

```java
logger.warn("email={} token={}", email, token);
```

vẫn làm lộ dữ liệu, dù dùng placeholder. Các mảnh logger ở đây giả định SLF4J hoặc API tương tự.

Một cách an toàn hơn:

```java
logger.warn("event={} operation={} reason={} request_id={}",
        "AUTH_FAILED", "SIGN_IN", "INVALID_CREDENTIALS", requestId);
```

Trong đó `requestId` đã được kiểm soát bởi hệ thống đáng tin cậy. Dù dùng whitelist, hãy kiểm tra các trường enum/ID được gán giá trị ở đâu. Một ID có pattern hợp lệ chưa chắc không mang dữ liệu cá nhân nếu được client chỉ định.

## 7. Ví dụ Java 17+ độc lập, biên dịch và chạy được

Ví dụ mô phỏng **hai exception chứa dữ liệu không nên xuất hiện trong log**: một `IOException` có header `Authorization` trong message và một `IllegalArgumentException` có email trong message. Handler không ghi trực tiếp hai exception đó mà tạo **sự kiện và response từ enum cố định**.

File **`SafeExceptionLoggingDemo.java`**:

```java
import java.io.IOException;

public class SafeExceptionLoggingDemo {
    enum Operation { FETCH_PROFILE, CREATE_ACCOUNT }
    enum FailureCode { UPSTREAM_UNAVAILABLE, INVALID_INPUT }

    record ApiError(int status, String code, String message) {}

    static void fetchProfile(String authorizationHeader) throws IOException {
        // A dependency may put request content in its exception message.
        throw new IOException("remote echoed " + authorizationHeader);
    }

    static void validateEmail(String email) {
        throw new IllegalArgumentException("Rejected email: " + email);
    }

    static void audit(String requestId, Operation operation, FailureCode code) {
        if (!requestId.matches("req-[0-9]{1,6}")) {
            throw new IllegalArgumentException("invalid internal request ID");
        }
        System.out.println("event=OPERATION_FAILED request_id=" + requestId
                + " operation=" + operation + " code=" + code);
    }

    static ApiError clientError(FailureCode code) {
        return switch (code) {
            case UPSTREAM_UNAVAILABLE ->
                    new ApiError(503, "SERVICE_UNAVAILABLE",
                            "The service is temporarily unavailable");
            case INVALID_INPUT ->
                    new ApiError(400, "INVALID_INPUT",
                            "The submitted data is invalid");
        };
    }

    public static void main(String[] args) {
        String demoToken = "demo-token-not-real";
        try {
            fetchProfile("Bearer " + demoToken);
        } catch (IOException ex) {
            // Never log ex, ex.getMessage(), or the token here.
            audit("req-7", Operation.FETCH_PROFILE,
                    FailureCode.UPSTREAM_UNAVAILABLE);
            ApiError error = clientError(FailureCode.UPSTREAM_UNAVAILABLE);
            System.out.println("client_status=" + error.status()
                    + " client_code=" + error.code());
        }

        try {
            validateEmail("user@example.invalid");
        } catch (IllegalArgumentException ex) {
            audit("req-8", Operation.CREATE_ACCOUNT, FailureCode.INVALID_INPUT);
            ApiError error = clientError(FailureCode.INVALID_INPUT);
            System.out.println("client_status=" + error.status()
                    + " client_code=" + error.code());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 SafeExceptionLoggingDemo.java
java SafeExceptionLoggingDemo
```

Standard output đã kiểm chứng:

```text
event=OPERATION_FAILED request_id=req-7 operation=FETCH_PROFILE code=UPSTREAM_UNAVAILABLE
client_status=503 client_code=SERVICE_UNAVAILABLE
event=OPERATION_FAILED request_id=req-8 operation=CREATE_ACCOUNT code=INVALID_INPUT
client_status=400 client_code=INVALID_INPUT
```

Giải thích:

1. `demoToken` là chuỗi giả **không phải credential thật**. `fetchProfile` cố tình mô phỏng một dependency kém an toàn làm lộ dữ liệu trong exception message.
2. Lệnh `catch` không in Throwable, message, stack trace hoặc header. Nó chọn `Operation`/`FailureCode` thuộc enum.
3. `ApiError` tạo response an toàn từ mã lỗi, không lấy nội dung tùy ý của exception.
4. `audit` chỉ in các giá trị đã kiểm soát. Trong production, sử dụng logger đã cấu hình sink, quyền truy cập, schema và retention; `System.out.println` chỉ giúp demo Java SE không cần thư viện.
5. Regex với request ID bảo vệ **hình thức**, không thay thế việc tạo ID không nhạy cảm từ hạ tầng tin cậy.
6. `record` và `switch expression` đều dùng được trong Java 17.

Giới hạn quan trọng: vì exception mô phỏng vẫn **chứa** dữ liệu thô trong memory, một auto-capture SDK, crash dump hay logger ở vị trí khác vẫn có thể thu chúng. Đừng lấy ví dụ này làm lý do cho phép code tạo exception chứa token; trong ứng dụng thật phải **giảm dữ liệu ở nguồn** và kiểm tra các sink ngoài đoạn handler.

## 8. Vì sao chỉ lọc bằng regex chưa đủ?

Một số ứng dụng cho phép log mọi chuỗi, sau đó áp regex để thay pattern email, `password=...`, `Bearer ...` hoặc số thẻ bằng `[REDACTED]`. Đây có thể là **lớp phòng thủ bổ sung**, nhưng không đủ làm chính sách duy nhất:

- Credential có nhiều dạng: header, query, JSON, base64, URL-encoded hoặc format riêng của SDK.
- Một token có thể xuất hiện **không có tiền tố** như `Bearer`.
- Dữ liệu cá nhân không chỉ là email/điện thoại; nội dung hội thoại, địa chỉ hay mã hồ sơ khó nhận diện bằng regex.
- Chuỗi có thể bị escape, cắt đoạn hoặc chứa nhiều dòng và ký tự điều khiển.
- Collector có thể lưu bản sao **trước khi** bộ lọc được áp dụng.
- Regex quá rộng xóa thông tin chẩn đoán hữu ích; regex quá hẹp bỏ lọt dữ liệu.
- Vendor thay đổi format message có thể làm bộ lọc cũ mất tác dụng.

Ưu tiên theo thứ tự: **không thu thập → không tạo exception chứa secret → chọn field allowlist → mask/redact ở nguồn nếu thật sự cần → filter bổ sung tại collector → kiểm thử mọi sink**.

**Hash không tự làm một giá trị thành vô danh.** Hash email dễ bị đối chiếu/dictionary attack khi miền giá trị đoán được; ngay cả ID giả danh cũng có thể liên kết với con người khi kết hợp dữ liệu khác. Nếu cần pseudonymization/tokenization, phải có threat model, bảo vệ khóa/bảng ánh xạ và chính sách truy cập phù hợp.

## 9. Không dump raw HTTP request, response hoặc SQL khi lỗi

Đây là mảnh code framework **không nên áp dụng trực tiếp**:

```java
catch (Exception ex) {
    logger.error("headers={} body={}", headers, requestBody, ex);
}
```

`headers` có thể chứa `Authorization`, `Cookie`, `Set-Cookie`, credential hoặc user-agent chứa thông tin riêng. `requestBody` có thể là hồ sơ khách hàng hoặc dữ liệu tài chính. Nếu exception in thêm cause, rủi ro tăng gấp nhiều lần.

Tương tự:

- URL đầy đủ có thể chứa query parameter nhạy cảm; ưu tiên tên operation hoặc **route template**, ví dụ `/customers/{id}` thay cho URL có ID thật.
- SQL statement có literal values hoặc JDBC bind parameters có thể chứa dữ liệu cá nhân; chỉ log mã câu lệnh/nhóm truy vấn và mã lỗi đã kiểm soát khi được phép.
- Response body từ dependency không phải message an toàn để phát tán trong log.
- Bật HTTP wire logging, JDBC trace/bind logging hoặc APM “capture all headers” ở production có thể làm lộ dữ liệu ngoài ý muốn.

Với client/server framework, chính sách cần áp dụng cả **filter, interceptor, exception resolver, access logger và HTTP client**. Chỉ sửa `catch` của một service không đủ nếu một middleware khác tự ghi nguyên request.

## 10. Cause chain, suppressed exception và lỗi từ async worker

Java có nhiều đường chuyển thông tin lỗi:

- `throw new ServiceException("safe", cause)` giữ `cause`; nếu logger in stack trace, message nhạy cảm của cause vẫn có thể lộ.
- `try-with-resources` có thể gắn lỗi từ `close()` thành suppressed exception; message thứ cấp cũng cần đánh giá.
- `Future.get()` có thể ném `ExecutionException` chứa cause từ worker.
- `CompletableFuture.join()` thường ném `CompletionException` có cause.
- Uncaught exception handler có thể in Throwable không qua controller.
- Framework scheduler có thể lưu exception của background task rồi báo về monitoring.

Điều này có nghĩa một dependency đã đưa secret vào Throwable thì **mọi điểm quan sát cause chain** đều có thể trở thành điểm rò rỉ. Không chỉ kiểm tra `getMessage()` của wrapper ngoài cùng.

Nếu phải giữ Throwable để phục vụ xử lý nội bộ, phân biệt rõ **khả năng giữ cause trong bộ nhớ** và **quyền xuất toàn bộ cause ra sink**. Có thể giữ mã lỗi/correlation ID ở log thông thường và dùng đường chẩn đoán hạn chế, được phê duyệt khi cần điều tra chi tiết. Không tự động cắt bỏ cause ở mọi tầng gây mất khả năng xác định nguyên nhân lỗi; nhưng cũng không mặc định lưu nguyên exception ở nơi nhiều người có quyền xem.

Với async work, một task có thể lỗi sau khi request ban đầu đã kết thúc. Phải xác định chủ sở hữu việc theo dõi `Future` hoặc stage, đặt policy log an toàn cho worker và tránh ghi cùng một exception nhiều lần tại từng dependent stage.

## 11. Correlation ID, tracing và MDC

Correlation ID giúp nối log từ nhiều service để truy nguyên một request **không cần in payload gốc**. ID cần được tạo hoặc xác minh bởi thành phần tin cậy, không dùng email, token, password hay mã truy cập có quyền bảo mật làm ID.

Một `X-Request-ID` do client gửi **không tự nhiên an toàn**: client có thể chèn dữ liệu cá nhân hoặc chuỗi điều khiển vào đó. Hệ thống nên kiểm tra độ dài/cú pháp, hoặc tự tạo internal ID và lưu quan hệ an toàn nếu thật sự cần.

Nhiều ứng dụng Java sử dụng `MDC` để gắn request ID vào log. Đây là mảnh code **minh họa SLF4J** trong một class có `service` và `safeRequestId`:

```java
MDC.put("request_id", safeRequestId);
try {
    service.process();
} finally {
    MDC.remove("request_id");
}
```

Cần import `org.slf4j.MDC` và cấu hình logging thích hợp; đoạn này **không độc lập** với Java SE. Thread pool có thể tái sử dụng worker; nếu không dọn context, một request có thể bị gắn nhầm metadata của request khác. `CompletableFuture` và các callback async không mặc nhiên kế thừa thread-local/MDC đúng như ngữ cảnh parent; dùng cơ chế context propagation của framework nếu có.

Không đặt nguyên JWT claims, request headers, email hoặc toàn bộ user profile vào MDC/baggage. Baggage có thể truyền qua nhiều service và log downstream, khiến phạm vi rò rỉ rộng hơn nhiều nơi tạo dữ liệu ban đầu.

## 12. Log injection từ input không đáng tin

Ngoài rủi ro privacy, attacker có thể đưa newline, tab, JSON fragment hoặc ký tự điều khiển vào input. Nếu log thẳng:

```java
logger.warn("Login failed for " + suppliedName);
```

một giá trị người dùng có thể tạo dòng log giả hoặc đánh lừa parser/alert. Đây là mảnh code **nguy hiểm để nhận diện**, không phải mẫu khuyến nghị.

Cách giảm rủi ro:

1. Tránh đưa user-supplied strings vào log nếu không có nhu cầu xác định.
2. Dùng event name và reason code lấy từ enum.
3. Với trường tự do thật sự cần thiết, giới hạn độ dài, chuẩn hóa/encode ký tự điều khiển phù hợp với định dạng log.
4. Dùng JSON encoder chuẩn, không tự ghép JSON string bằng phép nối chuỗi.
5. Kiểm tra bộ đọc log, dashboard và alert không coi nội dung log là lệnh/HTML đáng tin.

Parameterized logging làm việc với template tiện hơn, nhưng **không tự redaction dữ liệu** và không giải quyết toàn bộ log injection nếu giá trị chứa ký tự điều khiển.

## 13. Application log và audit log đều phải kiểm soát dữ liệu

**Application log** phục vụ chẩn đoán vận hành. **Security audit log** chứng minh hành động, thời điểm và kết quả của một sự kiện quan trọng. Audit log có thể có yêu cầu đặc biệt về tính toàn vẹn và thời gian lưu, nhưng điều đó **không hợp thức hóa việc ghi credential**.

Sự kiện đăng nhập thất bại nên ưu tiên mã sự kiện và kết quả, ví dụ:

```text
event=AUTHENTICATION_FAILURE
operation=SIGN_IN
outcome=DENIED
reason=INVALID_CREDENTIALS
request_id=req-7
```

Không ghi password người dùng nhập sai để “điều tra”. Nếu phải gắn một principal ID, hãy kiểm tra sự cần thiết và quyền đọc; đó có thể vẫn là dữ liệu cá nhân. Tránh phân biệt “tài khoản không tồn tại” với “sai password” trong response công khai nếu gây nguy cơ liệt kê tài khoản.

Với log bảo mật và log chẩn đoán, tránh dùng một kho dữ liệu mở rộng quyền truy cập để lưu tất cả chi tiết. Nếu cần xử lý sự cố đặc biệt, dùng môi trường chẩn đoán kiểm soát chặt và có thời gian giới hạn.

## 14. Mức DEBUG/TRACE không miễn trừ yêu cầu bảo vệ

Một anti-pattern thường xuất hiện trong điều tra production: tạm bật DEBUG/TRACE hoặc HTTP wire log để “thấy toàn bộ dữ liệu”. Điều này có thể khiến nhiều sink thu headers, body hoặc exception message mà bình thường không xuất hiện.

Mức log chỉ là **điều kiện về tần suất và độ chi tiết**, không phải cấp phép thu thập dữ liệu nhạy cảm.

- `ERROR`: event code, operation, request ID và context an toàn.
- `WARN`: tình trạng degraded, retry bất thường, mã lý do.
- `INFO`: mốc vận hành cần thiết.
- `DEBUG/TRACE`: chỉ thêm dữ liệu đã được phân loại và cho phép; không đưa password/token/body thô vào.

Nếu cần bật tạm mức chi tiết, phải có chủ sở hữu, phạm vi service, thời hạn tự tắt, giám sát khối lượng và kiểm tra cấu hình redaction/collector. Một kiểm tra kiểu `logger.isDebugEnabled()` chỉ giúp tránh tính dữ liệu khi DEBUG tắt; **không chứng minh nội dung sẽ an toàn khi DEBUG bật**.

## 15. Bảo vệ vòng đời log sau khi ghi

Ngay cả một event không chứa secret rõ ràng vẫn có thể cho biết lịch sử hoạt động. Cần quản lý:

- **Thu thập:** loại bỏ trường không cần ngay tại nguồn.
- **Vận chuyển:** bảo vệ kết nối appender/agent tới collector.
- **Lưu trữ:** phân quyền, mã hóa khi cần và phân tách môi trường.
- **Truy cập:** giới hạn tìm kiếm, xuất file, tải dashboard, API đọc log.
- **Retention:** chỉ giữ trong khoảng thời gian có mục đích vận hành/tuân thủ.
- **Sao chép:** nhận biết backup, index, data warehouse, cảnh báo/chatops có lưu bản sao.
- **Xóa và phản ứng sự cố:** có kế hoạch đánh giá phạm vi dữ liệu khi phát hiện rò rỉ.

Nếu **token thật** đã bị ghi nhầm vào log, chỉ xóa một dòng có thể chưa đủ: bản sao có thể đã tới collector, index, email alert hoặc backup. Quy trình xử lý có thể cần thu hồi/luân phiên credential, rà soát truy cập, gỡ bản sao theo khả năng và đánh giá nghĩa vụ thông báo áp dụng. Không dùng secret thật để “test liệu nó có bị ghi không”.

## 16. Những sai lầm thường gặp

| Cách làm | Tại sao không an toàn | Cách tốt hơn |
| --- | --- | --- |
| `throw new Exception("token=" + token)` | Token đi vào message và cause | Error code không nhạy cảm |
| `logger.error("{}", ex.getMessage())` | Nội dung dependency không được kiểm soát | Reason code và context allowlist |
| `logger.error("failed", ex)` không đánh giá dữ liệu | Stack trace/cause/suppressed có thể lộ secret | Policy riêng cho Throwable theo sink |
| `logger.debug("dto={}", dto)` | `toString()` có thể in password/email | Trường đã được chọn và phân loại |
| Ghi toàn bộ headers/body/SQL bind | Có thể chứa dữ liệu xác thực/cá nhân | Route template, status, statement ID |
| Trả `ex.toString()` trong HTTP 500 | Lộ class, message và nội bộ | Public code/message an toàn |
| Lọc mọi chuỗi bằng một regex | Không đủ nhận diện dữ liệu mới/mã hóa | Ngăn từ nguồn, allowlist, filter bổ sung |
| Hash email rồi coi là dữ liệu vô danh | Có thể đoán và đối chiếu | Threat model, pseudonymization đúng nghĩa |
| Dùng JWT/session làm request ID | Phát tán credential qua nhiều service | Server-generated opaque ID |
| Ghi cùng exception ở mỗi async stage | Bản sao log nhiều lần và lộ rộng | Một nơi chịu trách nhiệm quan sát lỗi |
| Tắt kiểm soát khi DEBUG/TRACE | Leak khi sự cố xảy ra | Mọi level phải tuân thủ policy |
| Chỉ xử lý leak ở app log | Collector, APM, proxy vẫn thu dữ liệu | Kiểm tra toàn bộ log pipeline |

## 17. Kiểm thử log và message an toàn

Ngoài unit test logic, nên có integration test đưa **dữ liệu giả dễ nhận biết** qua những đường lỗi thật hoặc mô phỏng, rồi kiểm tra mọi sink quan trọng.

| Tình huống | Kết quả cần xác minh |
| --- | --- |
| SDK ném exception có token giả | Log và client response không có token |
| Validation exception có email giả | Không lộ email qua error response hoặc appender |
| Throwable cause/suppressed chứa secret giả | Logger/collector không in nguyên exception |
| Request có `Authorization`/`Cookie` | Access/wire logs không chứa header nhạy cảm |
| DTO `toString()` chứa field password | Không dump object nguyên vẹn |
| Input có newline/control chars | Không chèn được sự kiện giả |
| `Future`/`CompletableFuture` lỗi | Đường quan sát async không log raw message |
| HTTP 4xx/5xx | Có mã lỗi và ID an toàn, không có stack |
| DEBUG/TRACE bật trong test | Chính sách dữ liệu vẫn được thực thi |
| Log tới APM/collector | Không tồn tại bản sao thô ngoài ứng dụng |

Dùng chuỗi canary **không phải bí mật thật** như `demo-token-not-real` hoặc `user@example.invalid`. Test nên assert chúng **không xuất hiện** trong nội dung thu từ logger test, response, trace event và các sink cần kiểm soát; đồng thời assert reason code/correlation ID an toàn **có xuất hiện** để chẩn đoán vẫn hữu ích.

Chỉ test một `catch` không đủ nếu middleware/agent còn tự thu Throwable; test cần mô phỏng toàn bộ đường dữ liệu phù hợp với kiến trúc. Đừng chỉ tìm `Bearer`, vì token có thể xuất hiện độc lập. Không phụ thuộc hoàn toàn vào snapshot text của exception message do bên ngoài tạo.

## 18. Checklist dùng khi review Java exception/logging

1. Mọi exception message được tạo mới đều tránh nối password, token, request body hoặc PII.
2. Không tự động biến `Throwable.getMessage()`/`toString()` thành HTTP response.
3. Không in raw `Throwable` ở sink rộng quyền khi source/cause chưa được đánh giá.
4. Log dùng event/operation/reason code và fields thuộc allowlist.
5. Correlation ID không chứa credential hoặc định danh không cần thiết; dữ liệu từ header ngoài phải được kiểm tra.
6. Logging không nhận nguyên object `record`/DTO có secret qua `toString()`.
7. Cause, suppressed exception, `CompletionException` và `ExecutionException` đều nằm trong đánh giá an toàn.
8. Wire logs, SQL bind logs, APM, stderr, job scheduler và cloud collector được cấu hình phù hợp.
9. Redaction là lớp bổ sung; không coi regex hoặc hashing mặc nhiên bảo vệ toàn diện.
10. Phân quyền, retention, encryption, backup và quy trình phản ứng sự cố đã được xác định.
11. Kiểm thử với token/email **giả** xác nhận log và response không chứa giá trị thô.
12. Vẫn giữ được thông tin vận hành: error code, operation, request ID, trạng thái và thời điểm.

**Kết luận:** muốn xử lý exception an toàn, hãy coi message và log là **đầu ra có thể bị sao chép ra ngoài ranh giới bảo mật**. Chọn dữ liệu được phép xuất ngay từ nguồn, tách lỗi nội bộ khỏi phản hồi công khai, quản lý cause chain và bảo vệ toàn bộ pipeline ghi log. Khả năng debug tốt đến từ event rõ ràng và correlation an toàn, không phải từ việc lưu tất cả dữ liệu mà exception tình cờ chứa.
