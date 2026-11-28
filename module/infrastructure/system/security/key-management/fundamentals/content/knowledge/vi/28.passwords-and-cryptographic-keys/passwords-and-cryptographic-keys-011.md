# Không log password

Không log password là nguyên tắc bảo vệ thông tin xác thực và key material khỏi bị sao chép vào các hệ thống ghi nhận, giám sát và phân tích. Log thường được gửi tới nhiều nơi hơn dữ liệu nghiệp vụ: stdout của container, log collector, SIEM, APM, tracing backend, hệ thống hỗ trợ và kho lưu trữ dài hạn. Nếu password hoặc cryptographic key xuất hiện trong một log event, mọi người và hệ thống có quyền đọc bản ghi đó có thể có thêm khả năng truy cập tài khoản, dữ liệu hoặc dịch vụ.

Phạm vi cần bảo vệ rộng hơn trường `password`. Không ghi raw password, passphrase, PIN, OTP, reset token, API key, bearer token, session cookie, private key, symmetric key, DEK, KEK, recovery share, keystore password hoặc plaintext key trả về từ KMS. Cũng không ghi password hash, verifier hoặc bản mã hóa secret nếu chúng có thể hỗ trợ dò đoán offline hoặc mở rộng quyền truy cập.

Trong quản lý khóa mật mã, log cần cung cấp bằng chứng về **ai đã yêu cầu thao tác gì, trên key/version nào, kết quả ra sao và khi nào**, nhưng không cần lưu giá trị bí mật được dùng để thực hiện thao tác. Thiết kế tốt dùng allowlist metadata an toàn, redaction tại nguồn, kiểm soát các đường log phụ và kiểm thử để chứng minh secret không xuất hiện trong log, trace hay telemetry.

## 1. Vì sao không được log password?

Password là bí mật xác thực. Nếu log chứa password, hậu quả có thể kéo dài hơn thời gian password được dùng trong ứng dụng:

- Log có thể được sao chép tới nhiều hệ thống và vùng lưu trữ khác nhau.
- Người vận hành, developer, vendor hỗ trợ hoặc tài khoản SIEM có thể đọc log dù không được phép dùng tài khoản nghiệp vụ.
- Log thường có retention dài, bản backup và bản export khó thu hồi đồng bộ.
- Một log index có thể được tìm kiếm hàng loạt, tải xuống hoặc chia sẻ trong incident ticket.
- Password có thể được tái sử dụng ở nhiều dịch vụ; một lần lộ có thể dẫn tới credential stuffing.
- Log thường được đưa vào công cụ AI, analytics hoặc môi trường thử nghiệm nếu không có phân loại dữ liệu rõ ràng.
- Secret trong log có thể tồn tại trong snapshot, replica, cache, archive, support bundle và bản sao của bên thứ ba.

Log là một phần của bề mặt tấn công. Việc mã hóa ổ đĩa log hoặc giới hạn quyền đọc là cần thiết nhưng không biến việc ghi password thành an toàn. Khi secret đã được ghi, số bản sao và số hệ thống cần xử lý sự cố thường tăng nhanh.

## 2. Những dữ liệu nào phải được coi là secret?

Không chỉ trường có tên `password` mới nhạy cảm. Cần phân loại theo khả năng dữ liệu đó cho phép xác thực, giải mã, ký, khôi phục hoặc chiếm quyền.

| Nhóm | Ví dụ | Quy tắc logging |
|---|---|---|
| Password/passphrase | Login password, database password, keystore password | Không ghi giá trị, kể cả khi login thất bại |
| PIN/OTP | HSM User PIN, smart-card PIN, TOTP, recovery code | Không ghi giá trị hoặc mã dùng một lần |
| Access credential | API key, bearer token, OAuth refresh token, cloud credential | Không ghi raw token hoặc header chứa token |
| Session material | Session ID, cookie, CSRF token, signed URL | Không ghi giá trị có thể tái sử dụng để chiếm session hoặc truy cập tài nguyên |
| Private key | RSA/EC/EdDSA private key, SSH private key | Không ghi encoded key, PEM, DER hoặc object serialization |
| Symmetric key | AES key, HMAC key, MAC key | Không ghi raw key hoặc byte array |
| Key encryption material | DEK, KEK, wrapping key, plaintext key từ KMS | Không ghi plaintext key; wrapped key cũng cần phân loại theo policy |
| Recovery material | HSM backup share, recovery phrase, seed, unlock token | Không ghi bất kỳ phần nào có thể hỗ trợ khôi phục |
| Password verifier | Password hash, salt kết hợp verifier, authentication proof | Không ghi; verifier có thể bị dùng để dò đoán offline |
| Connection secret | JDBC URL chứa password, connection string, DSN credential | Không ghi toàn bộ chuỗi nếu có credential |
| Challenge/reset data | Password reset link, email verification token, enrollment secret | Không ghi URL/token có thể dùng lại |

Một số metadata có thể ghi sau khi phân loại và giới hạn truy cập:

- Mã định danh principal hoặc workload đã được pseudonymize theo policy.
- Secret reference, key ID, key version hoặc certificate serial/fingerprint.
- Tên provider, thuật toán, operation type và kết quả.
- Authentication method, reason code và correlation ID.
- Thời điểm, service, environment và deployment version.

Metadata không tự động an toàn. Username/email có thể là dữ liệu cá nhân; key ID có thể tiết lộ topology; certificate subject có thể chứa thông tin nội bộ. Áp dụng data classification và minimization cho từng trường.

## 3. Phân biệt log vận hành và audit event

Log vận hành giúp chẩn đoán lỗi và theo dõi sức khỏe dịch vụ. Audit event ghi nhận hành động có ý nghĩa bảo mật hoặc nghiệp vụ. Cả hai đều không cần chứa password hay key material.

| Loại bản ghi | Mục đích | Dữ liệu phù hợp |
|---|---|---|
| Application log | Điều tra lỗi và theo dõi luồng xử lý | Event name, error code, correlation ID, component, duration |
| Security audit | Truy vết hành động và trách nhiệm | Actor ID, action, target reference, policy decision, outcome, timestamp |
| Authentication event | Ghi nhận đăng nhập/thất bại | Principal reference, auth method, outcome, reason code, source metadata đã giảm thiểu |
| Key operation event | Theo dõi thao tác mật mã | Key ID/version, algorithm, operation, provider/HSM reference, result |
| Access log | Thống kê request và phát hiện bất thường | Method, route template, status, latency; tránh raw body, secret headers và query token |
| Trace/span | Theo dõi request qua nhiều service | Trace ID, span name, allowlisted attributes; không capture secret payload |

Audit event cần có tính toàn vẹn, quyền truy cập, retention và đồng bộ thời gian phù hợp. Không ghi secret để “làm bằng chứng”; hãy ghi rằng một secret reference hoặc key version đã được sử dụng, cùng operation ID từ KMS/HSM nếu có.

## 4. Những đường rò rỉ secret phổ biến

Secret có thể đi vào log qua nhiều thành phần khác nhau, kể cả khi code nghiệp vụ không gọi `logger.info(password)`.

### 4.1. Application logging

- Nội suy password hoặc token trực tiếp vào message.
- Log toàn bộ request DTO, form object hoặc authentication object.
- Gọi `toString()`, `JSON.stringify` hoặc serialize object có trường secret.
- Log map chứa toàn bộ request parameters hoặc environment variables.
- Log giá trị `char[]`/`byte[]` sau khi chuyển thành String để debug.
- Log câu lệnh SQL hoặc connection string có credential.

### 4.2. Exception và error handling

- Exception message chứa URL, query parameter, request body hoặc credential.
- Validation exception chứa `rejectedValue` của password field.
- HTTP client exception chứa request headers hoặc response body.
- Database exception hiển thị JDBC URL hoặc câu lệnh có dữ liệu nhạy cảm.
- Debug stack trace từ thư viện bên thứ ba chứa object dump hoặc serialized request.

### 4.3. HTTP server, proxy và gateway

- Access log ghi `Authorization`, `Cookie`, `Set-Cookie` hoặc custom API-key header.
- Request/response body logging ghi payload đăng nhập hoặc token exchange.
- URL query string chứa `access_token`, reset token hoặc signed URL.
- Reverse proxy ghi toàn bộ headers hoặc body khi debug.
- Gateway ghi form fields khi xác thực lỗi.

### 4.4. APM, tracing và metrics

- Auto-instrumentation capture toàn bộ HTTP headers hoặc body.
- Span attribute ghi `url.full` có query string nhạy cảm.
- Exception event ghi message hoặc stack trace có secret.
- Baggage/MDC mang password hoặc token xuyên qua nhiều service.
- Metric label dùng raw username, token hoặc key alias do caller kiểm soát.

### 4.5. Hạ tầng và công cụ phát triển

- CI/CD command echo secret hoặc shell tracing.
- Container stdout/stderr, sidecar log shipper và crash report.
- Heap dump, core dump, thread dump hoặc diagnostic bundle chứa dữ liệu trong memory.
- Kubernetes event/manifest rendering hoặc debug output của secret controller.
- Shell history, process arguments, terminal recording và support ticket.
- Data warehouse, SIEM export, archive và backup chứa log gốc.

Kiểm soát phải bao phủ toàn bộ đường đi từ ứng dụng tới hệ thống lưu trữ và công cụ downstream. Chỉ cấu hình logger trong ứng dụng là chưa đủ.

## 5. Nguyên tắc thiết kế: allowlist trước, redaction bổ sung

Thiết kế an toàn nhất là chỉ ghi các trường đã được xác định rõ là cần thiết và được phép ghi. Đây là allowlist logging. Không serialize nguyên request hoặc object nghiệp vụ rồi cố gắng xóa secret sau đó.

Một event an toàn nên được tạo từ các trường có kiểu và ý nghĩa rõ:

```json
{
  "event": "authentication_failed",
  "principal_ref": "user-ref-7f31",
  "auth_method": "password",
  "reason_code": "INVALID_CREDENTIALS",
  "request_id": "req-8c2d",
  "service": "identity-api",
  "environment": "production",
  "outcome": "DENY"
}
```

Ví dụ trên không chứa password, password hash, raw username/email, request body, cookie hoặc Authorization header. `principal_ref` là mã tham chiếu được tạo theo policy; nếu không cần định danh cụ thể, có thể chỉ ghi loại principal hoặc aggregate counter.

Redaction/masking tại logger hoặc collector là lớp phòng vệ bổ sung. Nó hữu ích để phát hiện và che một số trường có cấu trúc, nhưng không thể nhận diện mọi dạng secret: chuỗi có thể bị encode, chia nhỏ, đặt trong exception, nén hoặc nhúng trong dữ liệu tự do. Không dùng regex redaction làm lý do để cho phép log toàn bộ request.

## 6. Những cách log không an toàn

Các ví dụ sau minh họa lỗi thường gặp. Không dùng trong production:

```java
// Không log password trực tiếp.
logger.info("Login attempt username={} password={}", username, password);

// Không log toàn bộ DTO chứa credential.
logger.debug("Authentication request: {}", request);

// Không chuyển secret thành String để debug.
logger.trace("Secret bytes={}", new String(secretBytes));

// Không ghi URL/connection string có credential.
logger.error("Database connection failed: {}", jdbcUrl, exception);
```

SLF4J placeholder `{}` chỉ trì hoãn việc format message; nó không tự phát hiện hay che secret. Việc dùng parameterized logging không làm cho `logger.info("password={}", password)` an toàn.

Không log một object chỉ vì `toString()` hiện tại có vẻ an toàn. `toString()` có thể được tạo tự động bởi Java record, Lombok `@Data`, IDE hoặc thư viện serialization; thay đổi field trong tương lai có thể làm secret xuất hiện mà không sửa dòng log.

## 7. Ghi authentication event an toàn trong Java

Khi đăng nhập thành công hoặc thất bại, log kết quả và reason code đã chuẩn hóa. Không ghi password, password hash, OTP, reset token, session cookie hoặc toàn bộ đối tượng authentication.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class AuthenticationService {
    private static final Logger log =
        LoggerFactory.getLogger(AuthenticationService.class);

    public boolean authenticate(
            String principalRef,
            char[] password,
            PasswordVerifier verifier,
            String requestId) {
        try {
            boolean accepted = verifier.verify(principalRef, password);
            log.info(
                "authentication_completed principalRef={} outcome={} requestId={}",
                principalRef,
                accepted ? "ALLOW" : "DENY",
                requestId
            );
            return accepted;
        } catch (InvalidCredentialsException exception) {
            log.warn(
                "authentication_failed principalRef={} reason={} requestId={}",
                principalRef,
                "INVALID_CREDENTIALS",
                requestId
            );
            return false;
        } finally {
            if (password != null) {
                java.util.Arrays.fill(password, '\0');
            }
        }
    }
}
```

Đây là ví dụ minh họa; `principalRef` phải là định danh đã được phân loại và được phép ghi. Hàm xóa mảng password đang sở hữu nên caller không được tái sử dụng mảng sau lời gọi. Việc xóa mảng là best-effort, không chứng minh mọi bản sao trong JVM/provider đã bị xóa khỏi memory.

`requestId` cũng phải do server tạo hoặc được kiểm tra độ dài/ký tự trước khi ghi; không đưa chuỗi tùy ý từ caller vào log vì CR/LF có thể tạo log injection. Nếu API thư viện chỉ nhận `String`, tránh tạo thêm String từ password; String bất biến và không thể xóa nội dung theo cách đáng tin cậy sau khi sử dụng.

Không phân biệt quá chi tiết “user không tồn tại” và “password sai” trong log hoặc response nếu điều đó tạo điều kiện dò tài khoản. Nếu đội bảo mật cần phân tích, dùng reason code nội bộ có quyền truy cập phù hợp và không tiết lộ cho client.

## 8. Không log exception chứa dữ liệu nhạy cảm

Không phải mọi exception đều an toàn để ghi stack trace. Một số thư viện đưa URL, request headers, SQL, form values hoặc response body vào message/cause. Nếu chưa biết exception có thể chứa gì, hãy chuyển thành error code an toàn và giữ exception chi tiết trong một kênh điều tra được kiểm soát nếu policy cho phép.

```java
try {
    tokenClient.exchange(credentials);
} catch (TokenExchangeException exception) {
    // Chỉ ghi mã lỗi đã chuẩn hóa; không ghi message/body/headers.
    logger.error(
        "token_exchange_failed requestId={} errorCode={}",
        requestId,
        "UPSTREAM_AUTH_FAILURE"
    );
    throw new AuthenticationDependencyException(
        "Authentication dependency unavailable"
    );
}
```

Nếu cần stack trace, hãy xác nhận thư viện không nhúng secret vào exception và dùng cơ chế sanitization đã kiểm thử. Không gọi `exception.getMessage()` hoặc `exception.toString()` một cách mặc định. Một số hệ thống có thể lưu exception đầy đủ trong kho forensic tách biệt; kho đó vẫn cần phân loại, access control, retention và kiểm tra secret.

Không đưa password vào message của exception khi validate. Thay vì `throw new IllegalArgumentException("Invalid password: " + password)`, dùng reason code như `PASSWORD_POLICY_VIOLATION` và tham chiếu request ID.

## 9. Cẩn thận với Java record, Lombok và serialization

Java record tự tạo `toString()` chứa tên và giá trị component. Lombok `@Data` cũng thường tạo `toString()` từ các field. Nếu DTO chứa password hoặc token, một dòng log tưởng như vô hại có thể làm lộ secret.

```java
// Không an toàn: generated toString() chứa password.
public record LoginRequest(String username, String password) {}

// Không an toàn: Lombok @Data có thể sinh toString() chứa mọi field.
// @Data
// class Credentials { String username; String password; }
```

Giải pháp tốt hơn là không đưa secret vào object được log hoặc serialize. Tách DTO đầu vào khỏi event logging; tạo một event mới chỉ gồm metadata allowlisted. Nếu cần wrapper cho secret, override `toString()` để trả giá trị cố định đã redacted và không cung cấp serializer tự động cho secret. Đây chỉ là hàng rào bổ sung; vẫn phải cấm log object wrapper hoặc serialize secret field ngoài ý muốn.

Ví dụ wrapper tối giản:

```java
import java.util.Arrays;

public final class SecretChars implements AutoCloseable {
    private char[] value;

    public SecretChars(char[] input) {
        if (input == null) {
            throw new IllegalArgumentException("Secret is required");
        }
        this.value = input.clone();
    }

    public char[] copyForUse() {
        if (value == null) {
            throw new IllegalStateException("Secret is closed");
        }
        return value.clone();
    }

    @Override
    public String toString() {
        return "[REDACTED]";
    }

    @Override
    public void close() {
        if (value != null) {
            Arrays.fill(value, '\0');
            value = null;
        }
    }
}
```

`SecretChars` chỉ minh họa giảm rủi ro vô tình in giá trị. `copyForUse()` tạo bản sao mới nên caller phải xóa bản sao sau khi sử dụng. Wrapper không ngăn debugger, heap dump, reflection hoặc code được cấp quyền truy cập lấy secret; thiết kế vẫn cần giới hạn quyền và thời gian tồn tại.

Constructor clone mảng đầu vào, vì vậy caller vẫn sở hữu mảng ban đầu và cần xóa nó khi không còn dùng. Không chuyển wrapper thành record hoặc bật serializer tự động có thể đọc field `value`.

## 10. HTTP request, header và body logging

HTTP logging middleware thường được bật để điều tra lỗi tích hợp. Nếu ghi toàn bộ request/response, nó có thể thu password đăng nhập, token, cookie, private data và secret trong query string.

Các header cần loại khỏi log theo mặc định:

- `Authorization` và `Proxy-Authorization`.
- `Cookie` và `Set-Cookie`.
- Các header API key, access token hoặc HMAC signature riêng của tổ chức.
- Header mang client assertion, enrollment secret hoặc credential nội bộ.

Không log body cho endpoint như login, token exchange, password reset, key import, key unwrap, enrollment hoặc secret retrieval. Nếu phải debug payload, tạo schema log riêng chỉ chứa trường allowlisted, không ghi raw body. Với endpoint khác, vẫn cần phân loại vì dữ liệu nghiệp vụ có thể chứa secret.

URL query string cũng có thể chứa credential như `?access_token=...`, reset token hoặc signed URL. Không đưa secret vào URL; nếu hệ thống legacy bắt buộc, loại query value khỏi access log và migration sang header/body được bảo vệ.

### 10.1. Access log chỉ ghi trường cần thiết

Ưu tiên log method, route template, status, latency và request ID. Dùng route template như `/users/{id}` thay vì raw URL nếu path/query có thể chứa dữ liệu nhạy cảm. Không bật chế độ “log all headers” trong production.

Nếu cần log một số header, dùng allowlist cụ thể như `X-Request-ID` sau khi validate độ dài và ký tự. Không dùng denylist nhỏ kiểu “chỉ che password” vì secret có thể xuất hiện dưới tên trường mới.

### 10.2. Spring và framework logging

Với Spring Boot/Spring Security hoặc framework tương tự:

- Không log toàn bộ `Authentication`, `Principal`, `UserDetails` hoặc request DTO.
- Không ghi `BindingResult` nếu nó chứa `rejectedValue` của password field.
- Tắt request/response body logging cho endpoint xử lý credential.
- Kiểm tra debug log của security filter, HTTP client và database driver.
- Không expose `env`, `configprops`, heap dump hoặc diagnostics endpoint cho người không được phép.
- Dùng event listener để tạo audit event an toàn, chỉ lấy principal reference, outcome và reason code cần thiết.

Không bật `DEBUG`/`TRACE` trên production chỉ để điều tra một lỗi nếu chưa rà soát dữ liệu mà framework sẽ ghi. Nếu cần bật tạm thời, giới hạn package, thời gian, người truy cập và xác minh log output bằng secret canary.

## 11. Tracing, APM và distributed context

Tracing có thể tự động thu thập HTTP attributes, exception event, SQL statement, baggage và custom span attributes. Secret trong một span có thể được nhân bản qua nhiều service và gửi tới vendor APM.

Các nguyên tắc:

- Không capture toàn bộ request/response body cho luồng xác thực hoặc quản lý khóa.
- Không capture `Authorization`, `Cookie`, `Set-Cookie`, API key và custom secret header.
- Loại query parameter nhạy cảm khỏi `url.full`; ưu tiên route template và host đã phân loại.
- Không đưa password, token hoặc key bytes vào span name, attribute, event hay baggage.
- Không đưa secret vào MDC vì MDC thường được tự động copy sang log và async context.
- Kiểm tra auto-instrumentation của HTTP, JDBC, messaging và cloud SDK.
- Giới hạn quyền truy cập trace backend và retention như hệ thống log.

Không dùng raw secret làm metric label. Label có thể được lưu lâu và tạo cardinality rất lớn; chỉ dùng outcome, error code, service và loại operation có tập giá trị giới hạn.

### 11.1. MDC chỉ chứa context an toàn

MDC (Mapped Diagnostic Context) hữu ích để gắn request ID hoặc trace ID vào log. Chỉ thêm các giá trị đã được validate và cho phép. Luôn xóa context trong `finally` để tránh dữ liệu của request trước rò sang thread được tái sử dụng.

```java
import org.slf4j.MDC;

try {
    MDC.put("request_id", validatedRequestId);
    MDC.put("service", "identity-api");
    handleRequest();
} finally {
    MDC.remove("request_id");
    MDC.remove("service");
}
```

Không đưa `password`, `Authorization`, cookie, session ID hoặc raw username vào MDC. Với async/reactive processing, kiểm tra cơ chế context propagation; MDC có thể được copy qua executor hoặc Reactor context theo cách framework cấu hình.

## 12. Không log password hash hoặc verifier

Password hash không phải password gốc, nhưng vẫn là tài sản nhạy cảm. Nếu attacker lấy được hash và salt, họ có thể thử đoán password offline mà không bị rate limit của hệ thống đăng nhập. Việc log hash làm tăng số bản sao verifier và mở rộng đối tượng có thể truy cập.

Không ghi:

- Password hash hoặc encoded Argon2/bcrypt/PBKDF2 string.
- Salt cùng verifier trong một log event.
- Pepper, KDF secret hoặc HSM reference kèm dữ liệu có thể suy ra verifier.
- Authentication proof hoặc challenge response có thể phát lại.

Nếu cần chẩn đoán password migration, chỉ ghi algorithm/profile version, cost parameter, trạng thái upgrade và mã người dùng đã pseudonymize. Không ghi hash đầu vào hoặc kết quả.

## 13. Logging trong KMS/HSM và thao tác key

KMS/HSM audit thường cần ghi nhận thao tác key để chứng minh trách nhiệm và phát hiện lạm dụng. Những event phù hợp gồm:

- `GenerateKey`, `ImportKey`, `Encrypt`, `Decrypt`, `Sign`, `Verify`, `WrapKey`, `UnwrapKey`, `RotateKey`, `DisableKey`, `ScheduleDeletion`.
- Principal/service identity và authorization decision.
- Key ID/version, algorithm, operation context và provider/partition reference.
- Request/operation ID, timestamp, result/error code và latency.
- Thay đổi policy, role, key state, replication hoặc backup metadata.

Không ghi raw key, plaintext DEK, KEK, private key, PIN, HSM authentication data, recovery share hoặc plaintext payload. Với `Decrypt`/`UnwrapKey`, log operation metadata và kết quả kiểm soát, không log plaintext trả về.

Wrapped key cũng cần được phân loại. Nó thường không tương đương raw key nếu chỉ unwrap được trong security boundary phù hợp, nhưng vẫn có thể tiết lộ metadata hoặc tạo điều kiện replay/misuse. Không đưa wrapped key vào log debug nếu không có yêu cầu rõ ràng và phê duyệt.

## 14. Redaction và masking

Redaction loại bỏ trường nhạy cảm khỏi log; masking thay một phần giá trị bằng ký tự thay thế. Hai kỹ thuật hữu ích nhưng phải được áp dụng đúng lớp.

| Kỹ thuật | Ưu điểm | Giới hạn |
|---|---|---|
| Allowlist field | Chỉ ghi dữ liệu đã được duyệt | Cần thiết kế event schema và cập nhật khi nghiệp vụ thay đổi |
| Typed safe event | Khó vô tình serialize request object | Cần tránh đưa secret vào field hoặc serializer khác |
| Source-level redaction | Chặn trước khi dữ liệu rời ứng dụng | Phải bao phủ mọi logger/framework |
| Collector-side masking | Phòng vệ bổ sung cho nhiều nguồn log | Secret đã đi khỏi ứng dụng và có thể tồn tại trong buffer/queue |
| Regex filter | Có thể che một số pattern rõ ràng | Dễ bỏ sót encoding, tên field mới, multiline và exception |
| Access control | Giảm người có thể đọc log | Không ngăn secret tồn tại trong bản ghi hoặc backup |

Không dùng masking một phần password như `p****d` để debug. Ngay cả vài ký tự đầu/cuối có thể giúp tương quan hoặc thu hẹp không gian đoán. Với credential, lựa chọn mặc định là không ghi giá trị nào.

### 14.1. Redaction ở collector là lớp cuối

Collector có thể áp dụng processor để xóa field nhạy cảm trước khi lưu vào backend. Cần bảo đảm redaction diễn ra trước mọi queue, retry buffer, dead-letter store và export. Nếu shipper gửi raw log qua Kafka hoặc object storage rồi mới masking ở SIEM, secret đã tồn tại ở hệ thống trung gian.

Kiểm tra cả structured JSON, multiline stack trace, nested field, escaped string, Base64/URL encoding và dữ liệu nén. Không giả định một regex duy nhất có thể phát hiện mọi secret.

## 15. Không để secret xuất hiện trong CI/CD và shell

Build/deploy pipeline thường in command, environment, test output và diagnostic data. Các rủi ro gồm:

- Shell tracing (`set -x`) in lệnh chứa password hoặc token.
- CLI nhận `--password secret` khiến secret xuất hiện trong process arguments và job log.
- Build tool in toàn bộ environment hoặc configuration khi lỗi.
- Test assertion in request/response object chứa credential.
- Container build lưu secret trong layer, cache hoặc build metadata.
- Deployment template render Secret vào output hoặc artifact.
- Debug artifact và test report đính kèm keystore, `.env`, heap dump hoặc HTTP capture.

Dùng secret masking của CI như lớp bổ sung; nó thường chỉ che giá trị đã đăng ký và có thể bị bypass bởi encoding, substring hoặc format khác. Không echo secret để “kiểm tra đã inject chưa”. Kiểm tra sự hiện diện bằng trạng thái boolean, secret version hoặc một thao tác xác thực thử được thiết kế an toàn.

Tránh truyền secret qua command line. Ưu tiên file descriptor, stdin được bảo vệ, secret file mount hoặc API secret manager tùy công cụ. Không lưu secret trong shell history, script argument, URL hay biến môi trường tồn tại lâu hơn cần thiết.

## 16. Heap dump, crash dump và support bundle

Password và key có thể tồn tại trong memory trong lúc xử lý. Heap dump, core dump, flight recording, debugger snapshot hoặc support bundle có thể chứa bản sao của String, byte array, object graph và request buffer.

Kiểm soát cần có:

- Hạn chế ai được tạo và tải heap/core dump.
- Không tự động đính kèm dump vào ticket hoặc gửi vendor nếu chưa phân loại.
- Mã hóa và giới hạn retention cho dump được phép giữ.
- Xóa dump theo quy trình khi không còn mục đích điều tra.
- Hạn chế dump trên production hoặc dùng cơ chế diagnostic có kiểm soát.
- Không giả định `char[]` và `Arrays.fill` loại bỏ mọi bản sao trong JVM.
- Kiểm tra crash reporter và APM agent có thu thập local variables hoặc request context không.

Đối với private key non-exportable trong HSM, heap dump vẫn có thể chứa PIN, token, key handle, plaintext DEK hoặc dữ liệu ứng dụng đã giải mã. Non-exportable không loại bỏ mọi rủi ro từ memory của process.

## 17. Thiết kế safe audit event

Audit event nên ghi đủ để điều tra mà không cần secret. Ví dụ một lần ký bằng HSM:

```json
{
  "event": "key_operation",
  "operation": "SIGN",
  "actor_ref": "workload:release-signer",
  "key_id": "artifact-signing",
  "key_version": "v12",
  "algorithm": "RSASSA-PSS-SHA256",
  "provider": "SunPKCS11-HSM",
  "hsm_operation_id": "op-91d2",
  "authorization": "ALLOW",
  "outcome": "SUCCESS",
  "request_id": "req-8c2d",
  "timestamp": "2026-11-28T04:00:00Z"
}
```

Event không chứa private key, PIN, signature input hoặc raw signature nếu không cần. Nếu chữ ký là output công khai, chỉ lưu ở artifact/repository phù hợp, không mặc định đẩy vào log. Với thao tác decrypt, không ghi plaintext hoặc plaintext DEK.

## 18. Kiểm soát schema và data classification

Structured logging giúp định nghĩa schema và enforce allowlist. Mỗi field cần có owner, mục đích, mức phân loại, retention và nơi được phép gửi.

Ví dụ schema:

| Field | Phân loại gợi ý | Quy tắc |
|---|---|---|
| `event_name` | Internal | Tập giá trị cố định |
| `principal_ref` | Confidential hoặc pseudonymous | Chỉ ghi nếu cần và được duyệt |
| `auth_method` | Internal | Enum như password, mTLS, OIDC |
| `reason_code` | Internal | Mã chuẩn hóa, không chứa input |
| `request_id` | Internal | Random identifier, không nhúng secret |
| `key_id`/`key_version` | Internal/Confidential | Ghi theo nhu cầu audit |
| `algorithm`/`provider` | Internal | Ghi profile thực tế |
| `password`/`token`/`private_key` | Restricted secret | Cấm ghi |
| `request_body` | Variable | Cấm raw capture ở endpoint nhạy cảm; chỉ allowlist field |
| `exception_message` | Variable | Chỉ ghi sau khi đánh giá hoặc chuẩn hóa |

Schema validation có thể từ chối event chứa field bị cấm hoặc không nằm trong allowlist. Điều này giúp phát hiện code mới vô tình thêm trường nhạy cảm. Không chỉ dựa vào convention hoặc review thủ công.

## 19. Kiểm thử để chứng minh secret không bị log

Không thể chứng minh bằng một lần đọc code rằng mọi đường log đều an toàn. Cần kiểm thử theo hướng chủ động đưa secret giả vào các luồng và tìm xem chúng có xuất hiện trong log, trace, metric, event hoặc test artifact hay không.

Quy trình kiểm thử:

1. Tạo secret canary giả, duy nhất cho từng loại dữ liệu; không dùng password/key thật.
2. Chạy luồng đăng nhập thành công, thất bại, timeout và validation error.
3. Chạy password reset, token exchange, mTLS, KMS decrypt/sign và key import trong môi trường test.
4. Bật cấu hình logging/tracing gần giống production.
5. Thu thập application log, access log, proxy log, trace, APM event, CI output và test report.
6. Tìm canary ở dạng raw, URL-encoded, JSON-escaped, Base64 nếu ứng dụng có encode.
7. Kiểm tra exception, rejected value, MDC, HTTP headers/body và serialized DTO.
8. Xác nhận safe audit event vẫn có đủ metadata để điều tra.
9. Lặp lại khi nâng framework, agent, logback/log4j, gateway hoặc instrumentation.

Ví dụ canary:

```text
TEST_ONLY_PASSWORD_CANARY_7c91
TEST_ONLY_BEARER_CANARY_a82e
TEST_ONLY_PRIVATE_KEY_MARKER_19bd
```

Các chuỗi này chỉ dùng trong môi trường kiểm thử. Không dùng secret thật làm canary và không đẩy canary vào production. Test phải fail nếu tìm thấy canary trong output không được phép; không chỉ kiểm tra một file application log.

### 19.1. Negative test cho logger

Có thể dùng appender test hoặc log capture để xác minh event không chứa canary. Cần kiểm tra cả `message`, arguments, MDC/context, throwable, serialized fields và structured attributes. Nếu logger defer formatting, kiểm tra kết quả cuối cùng ở appender/backend chứ không chỉ kiểm tra chuỗi format ban đầu.

Test redaction cần có case password field mới, header mới, exception lồng nhau, multiline, nested JSON và secret được URL/Base64 encode. Tuy nhiên, allowlist event schema vẫn là kiểm soát chính.

## 20. Incident response khi password xuất hiện trong log

Khi phát hiện secret đã vào log, coi đó là một sự kiện lộ credential cho tới khi đánh giá chứng minh được phạm vi khác. Xóa dòng log ở một dashboard không thu hồi các bản sao đã được gửi đi.

Các bước ứng phó:

1. **Xác định secret:** loại secret, owner, principal, key ID/version, môi trường và thời điểm bị ghi.
2. **Khoanh vùng đường đi:** application log, collector, queue, SIEM, APM, archive, backup, export và bên thứ ba.
3. **Đánh giá khả năng truy cập:** ai có thể đọc, tải, tìm kiếm hoặc sao chép bản ghi; kiểm tra access audit.
4. **Contain:** hạn chế quyền truy cập log, ngừng pipeline ghi secret và tắt capture gây rò rỉ.
5. **Rotate/revoke:** đổi password, revoke token/session, thay API key hoặc xử lý key compromise theo quy trình tương ứng.
6. **Bảo toàn bằng chứng:** giữ audit và metadata cần điều tra trong kho được kiểm soát; không xóa dấu vết trước khi xác định yêu cầu pháp lý/forensic.
7. **Xử lý bản sao:** phối hợp chủ sở hữu log/backup/vendor để purge hoặc rút ngắn retention theo policy và nghĩa vụ lưu trữ.
8. **Kiểm tra downstream:** rà soát ticket, export, analytics, developer workstation, cache và bản tải xuống.
9. **Xác minh:** dùng canary/test để chứng minh đường rò đã được chặn và secret cũ không còn được chấp nhận.
10. **Ghi nhận nguyên nhân:** cập nhật schema, code, framework config, CI rule và runbook.

Nếu private key hoặc DEK bị log, đánh giá như compromise key material: tạo key mới, cập nhật certificate/data protection và xem xét re-encryption hoặc revocation theo loại key. Chỉ xóa log mà giữ nguyên key bị lộ không giải quyết rủi ro.

## 21. Retention và quyền truy cập log

Ngay cả log đã loại secret vẫn có thể chứa dữ liệu cá nhân, định danh workload, key metadata và thông tin topology. Áp dụng:

- Role-based access và least privilege cho log search/export.
- Phân tách quyền quản trị log pipeline với quyền sử dụng hệ thống nghiệp vụ.
- MFA và audit cho tài khoản có thể tìm kiếm hoặc tải log.
- Mã hóa khi truyền và khi lưu; quản lý khóa mã hóa log riêng.
- Retention theo mục đích, luật và chính sách; không giữ vô thời hạn theo mặc định.
- Kiểm soát export, download, support bundle và chia sẻ vendor.
- Integrity protection cho audit log và cảnh báo truy cập bất thường.
- Kiểm tra backup, replica, archive và deletion propagation.

Masking không thay thế access control. Access control cũng không thay thế việc loại secret tại nguồn. Cần kết hợp data minimization, source-level allowlist, redaction defense-in-depth, quyền truy cập và retention.

## 22. Tình huống thực tế: password lọt vào APM khi đăng nhập thất bại

Một dịch vụ Identity API dùng Java/Spring nhận password qua JSON body. Khi xác thực thất bại, controller ghi `logger.warn("login failed request={}", request)`. DTO là Java record nên `toString()` tự in cả username và password. Trong cùng deployment, HTTP instrumentation của APM cũng capture request body khi span có exception. Password xuất hiện trong application log và trace backend dù code không có dòng `logger.info("password={}")`.

Nhóm ứng phó tắt body capture cho endpoint đăng nhập, thay log DTO bằng event allowlist gồm principal reference, outcome, reason code và request ID. Họ rà soát `BindingResult`, exception message, access log và MDC để tìm các đường rò khác. Password bị ảnh hưởng được reset hoặc buộc đổi theo phạm vi; session/token liên quan được revoke khi cần. Log/trace backend được giới hạn truy cập và xử lý các bản sao theo retention/incident policy.

Sau khi sửa, nhóm thêm test canary vào login success/failure, validation error và APM instrumentation. CI thu thập application log và trace test, sau đó fail nếu canary xuất hiện. DTO nhạy cảm không còn được serialize trong log; audit event vẫn đủ dữ liệu để theo dõi lỗi xác thực mà không chứa password.

## 23. Lỗi thường gặp khi triển khai logging

- **Dùng placeholder rồi nghĩ đã an toàn:** `{}` không che secret.
- **Log DTO hoặc record:** `toString()` có thể chứa mọi component.
- **Log exception message mặc định:** thư viện có thể nhúng URL, headers, body hoặc credential.
- **Chỉ che field `password`:** token, cookie, API key và secret field mới vẫn lọt.
- **Masking ở SIEM sau khi ingest:** queue hoặc collector trước đó đã nhận raw secret.
- **Bật HTTP body logging toàn cục:** endpoint login và key management bị capture.
- **Capture toàn bộ headers:** Authorization/Cookie bị gửi tới APM.
- **Dùng URL query cho token:** access log và proxy log có thể ghi query string.
- **Đưa secret vào MDC/baggage:** giá trị được nhân bản qua nhiều log/span.
- **Ghi password hash:** tạo điều kiện dò đoán offline.
- **Dùng secret thật trong test:** canary kiểm thử biến thành credential có giá trị.
- **Tin CI masking:** encoded/partial value có thể vượt qua bộ lọc.
- **Chỉ xóa log trên giao diện:** bản archive, export, backup và vendor copy còn tồn tại.
- **Không rotate secret sau exposure:** dữ liệu đã lộ vẫn dùng được.
- **Không kiểm thử sau khi nâng agent/framework:** instrumentation có thể đổi hành vi capture.

## 24. Checklist không log password

- [ ] Password, passphrase, PIN, OTP và recovery code không xuất hiện trong bất kỳ log event nào.
- [ ] API key, bearer/refresh token, session cookie và reset token không bị ghi.
- [ ] Private key, symmetric key, DEK, KEK, plaintext key response và recovery share không bị ghi.
- [ ] Password hash/verifier không xuất hiện trong log, trace hoặc metric.
- [ ] Không log request DTO, authentication object, record hoặc object có secret field.
- [ ] `toString()`, Lombok-generated output và serialization đã được rà soát.
- [ ] Exception message/stack trace được đánh giá; không log raw request/body/header.
- [ ] HTTP access log chỉ ghi route/field allowlisted; query và secret headers bị loại.
- [ ] APM/tracing không capture credential header, body, URL query hoặc secret baggage.
- [ ] MDC chỉ chứa correlation/context đã được duyệt và luôn được clear.
- [ ] CI/CD không echo secret, không bật shell tracing cho lệnh nhạy cảm.
- [ ] Heap dump, crash dump, support bundle và diagnostic endpoint được bảo vệ.
- [ ] Structured audit ghi actor/action/key reference/outcome mà không ghi key material.
- [ ] Redaction tại collector chỉ là lớp bổ sung; source logging dùng allowlist.
- [ ] Canary test tìm secret trong app log, proxy log, trace, APM, CI và test artifact.
- [ ] Log backend có least privilege, MFA, audit, encryption và retention phù hợp.
- [ ] Incident runbook có revoke/rotate và xử lý bản sao log/backup/vendor.
- [ ] Mọi thay đổi logger, framework, instrumentation và gateway đều có kiểm thử regression.

## 25. Câu hỏi tự kiểm tra

1. Vì sao log có thể làm tăng đáng kể phạm vi ảnh hưởng khi password bị lộ?
2. Những loại dữ liệu nào phải được coi là secret ngoài trường `password`?
3. Vì sao password hash cũng không nên xuất hiện trong log?
4. Audit event có thể ghi những metadata nào để điều tra thao tác KMS/HSM?
5. Parameterized logging của SLF4J có tự động redaction không?
6. Vì sao Java record hoặc Lombok `@Data` có thể làm lộ secret qua `toString()`?
7. Tại sao không nên log exception message và stack trace một cách mặc định?
8. Những HTTP header nào cần loại khỏi access log?
9. Vì sao URL query string không phải nơi phù hợp để truyền token?
10. APM/tracing có thể thu thập secret qua những cơ chế nào?
11. MDC và baggage cần tuân theo nguyên tắc nào?
12. Vì sao allowlist tốt hơn chỉ dùng regex denylist để che password?
13. Redaction ở collector có thể quá muộn trong pipeline ở những trường hợp nào?
14. Heap dump và core dump có thể chứa dữ liệu gì liên quan đến key management?
15. CI/CD masking không bảo đảm điều gì?
16. Secret canary test cần kiểm tra những đầu ra nào?
17. Khi password lọt vào log, vì sao chỉ xóa dòng log không đủ?
18. Khi private key xuất hiện trong log, cần xem xét những bước nào của key lifecycle?
19. Log backend cần kiểm soát access, integrity và retention ra sao?
20. Làm thế nào để audit key operation đầy đủ mà không ghi plaintext key hoặc payload?

Không log password là một yêu cầu xuyên suốt toàn bộ đường đi của dữ liệu, từ ứng dụng đến collector, APM, SIEM, backup và công cụ hỗ trợ. Khi hệ thống chỉ ghi metadata được duyệt, kiểm soát exception/serialization/HTTP instrumentation, kiểm thử bằng secret canary và có quy trình rotate khi exposure xảy ra, tổ chức vừa giữ được khả năng điều tra vừa giảm nguy cơ biến log thành kho chứa credential và cryptographic key.
