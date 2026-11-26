# Giữ nguyên nguyên nhân lỗi mà không đưa secret vào thông báo

Trong chương **Lỗi và khả năng phục hồi**, một lỗi khi ứng dụng Java truy cập HashiCorp Vault thường đi qua nhiều lớp: HTTP client, Spring Vault, service nghiệp vụ, controller, logger, tracing và hệ thống giám sát. Nếu xử lý không cẩn thận, ngoại lệ có thể bị **mất nguyên nhân gốc**, khiến khó xác định vì sao workload không đăng nhập được hoặc vì sao một secret không được đọc. Ngược lại, việc ném hoặc ghi log nguyên ngoại lệ cũng có nguy cơ làm lộ **Vault token, SecretID, private key, API key, request body hoặc response body**.

Mục tiêu của bài là thiết kế cơ chế **giữ quan hệ nhân quả cho chẩn đoán nội bộ** đồng thời **chỉ công bố thông tin lỗi an toàn** ở các ranh giới: thông báo cho người dùng, HTTP response, log, metrics, tracing, job report và cảnh báo. Ví dụ sử dụng **SPRING_VAULT** với `VaultOperations`/`VaultTemplate`, xác thực workload và KV v2; cùng quy tắc có thể áp dụng cho Transit encryption, PKI và vòng đời token/lease.

Bạn sẽ học cách:

1. Phân biệt *nguyên nhân lỗi* với *thông tin được phép hiển thị*.
2. Bọc một ngoại lệ mà vẫn giữ `Throwable cause`, không ghép `cause.getMessage()` vào thông báo.
3. Phân loại lỗi để xử lý retry, phân quyền và lỗi dữ liệu mà không suy đoán từ chuỗi thông báo.
4. Xuất HTTP Problem Details và log có mã lỗi/mã tham chiếu theo **allowlist**.
5. Kiểm thử việc bảo toàn cause và ngăn secret lọt qua các kênh quan sát.

## 1. Một ngoại lệ có những loại thông tin nào?

Giả sử service `orders` đọc `secret/data/orders/config` bằng Spring Vault. Token hết hạn hoặc policy thiếu quyền khiến Vault trả lỗi; ở tầng Java, một ngoại lệ có thể mang:

| Dữ liệu | Ví dụ | Có thể đưa ra HTTP/log thường? |
| --- | --- | --- |
| Loại lỗi đã phân loại | `VAULT_ACCESS_DENIED`, `VAULT_UNAVAILABLE` | Có, nếu mã này nằm trong danh sách an toàn |
| Tên thao tác nội bộ đã định nghĩa trước | `ORDERS_CONFIG_READ` | Có, nếu được duyệt về mức tiết lộ |
| Mã tham chiếu sinh ngẫu nhiên | `7c41...` | Có, giúp đối chiếu sự cố |
| HTTP status **từ Vault** | `403`, `429`, `503` | Có thể ghi ở telemetry nội bộ, không nhất thiết trả nguyên trạng |
| Loại exception | `ResourceAccessException`, `VaultException` | Có thể ghi tên lớp đã lọc để chẩn đoán |
| `exception.getMessage()` | Có thể chứa URL, body lỗi, dữ liệu đầu vào | **Không** mặc định |
| `cause` và `stack trace` | Có thể chứa toàn bộ message của các lớp bên dưới | **Không** mặc định |
| Token, SecretID, khóa riêng, plaintext | Dữ liệu xác thực hoặc nghiệp vụ nhạy cảm | Không |
| Nội dung `RestClientResponseException.getResponseBodyAsString()` | Toàn bộ response server | Không, trừ hệ thống điều tra có kiểm soát rõ ràng |

Một URL Vault có thể vô tình chứa namespace, tên tài nguyên, tham số query hoặc dữ liệu do caller đưa vào; **không coi việc log toàn bộ URL là an toàn**. Ngay cả khi Vault thường không trả plaintext secret trong thông báo lỗi, proxy, plugin tùy biến, ngoại lệ do ứng dụng tạo và tầng HTTP khác vẫn có thể đưa dữ liệu nhạy cảm vào `message`.

### Giữ cause khác với hiển thị cause

Đoạn mã sau bảo toàn thông tin điều tra:

~~~java
throw new SafeVaultAccessException(
        VaultFailureKind.VAULT_UNAVAILABLE,
        "ORDERS_CONFIG_READ",
        referenceId,
        originalException); // Giữ nguyên cause trong đối tượng nội bộ.
~~~

Tuy nhiên, nếu ở lớp trên lại gọi:

~~~java
log.error("Không thể đọc Vault", exception);
~~~

SLF4J/logging backend thông thường sẽ ghi **toàn bộ stack trace và chuỗi cause**, trong đó có thể xuất hiện dữ liệu nhạy cảm. Vì vậy, **chỉ giữ nguyên cause trong object không đủ để chống lộ secret**. Phải kiểm soát mọi điểm serialize, xuất/log và truyền exception ra ngoài.

## 2. Những cách xử lý gây lỗi bảo mật hoặc mất nguyên nhân

### Ghép message của exception gốc

~~~java
// KHÔNG NÊN: có nguy cơ đưa dữ liệu từ Vault/HTTP body vào message mới.
throw new IllegalStateException(
        "Đọc Vault thất bại: " + originalException.getMessage(),
        originalException);
~~~

Ví dụ trên **giữ cause** nhưng message công khai không an toàn. Lệnh `getMessage()` không có hợp đồng bảo đảm sẽ lọc secret; cú pháp tạo chuỗi với `e`, `e.toString()` hay `String.format("%s", e)` có cùng rủi ro.

### Mất chuỗi nguyên nhân

~~~java
// KHÔNG NÊN: không còn nguyên nhân gốc để phân biệt timeout và 403.
throw new IllegalStateException("Không thể đọc cấu hình");
~~~

Code này tuy không làm lộ message gốc nhưng bỏ mất loại lỗi, nơi phát sinh và stack trace cho điều tra nội bộ.

### Trả raw error hoặc in stack trace ra bên ngoài

~~~java
// KHÔNG NÊN: raw exception/response body không phải dữ liệu API công khai.
return ResponseEntity.internalServerError()
        .body(originalException.toString());
~~~

Tương tự, tránh trả trực tiếp `Throwable` qua JSON serializer, bật `include-stacktrace=always` trên endpoint lỗi công khai, gắn `exception.message` vào distributed tracing hoặc gửi full stack trace sang kênh cảnh báo không được bảo vệ.

**Nguyên tắc thiết kế:** Giữ exception nội bộ để hệ thống có bằng chứng về thất bại; tạo **một biểu diễn lỗi khác** dành cho người dùng và hệ thống quan sát thông thường.

## 3. Thiết kế ba lớp của lỗi an toàn

~~~mermaid
flowchart TD
    A[Vault HTTP/TLS/Auth lỗi] --> B[Spring Vault exception]
    B --> C[Adapter/service phân loại lỗi]
    C --> D[SafeVaultAccessException với cause gốc]
    D --> E[HTTP boundary]
    D --> F[Log/metrics/tracing boundary]
    E --> G[Public code, thông báo cố định, reference ID]
    F --> H[Code, operation ID, reference ID, status/class đã lọc]
    D --> I[Điều tra nội bộ theo quyền]
    I --> J[Kiểm soát truy cập và redaction trước khi xuất]
~~~

Ba lớp này có trách nhiệm khác nhau:

- **Lớp truy cập Vault** nắm thao tác cụ thể, gọi Vault và phát hiện kết quả bất thường. Lớp này giữ exception nguyên gốc làm cause khi cần bọc.
- **Lớp lỗi ứng dụng** gắn mã phân loại và ID tham chiếu an toàn. Nó không xây message từ dữ liệu tự do do Vault/HTTP trả về.
- **Lớp trình bày/quan sát** chỉ đọc các trường đã định nghĩa được phép công bố. Nó **không** tự động serialize cause hoặc gọi `log.error(..., exception)`.

Trong tài liệu này, chúng ta coi `reference ID` là chuỗi định danh sinh ngẫu nhiên cho từng lỗi. Nếu hệ thống đã có trace ID tương thích và được kiểm tra không chứa dữ liệu nhạy cảm, có thể dùng trace ID thay thế. Mã tham chiếu không phải Vault token, lease ID hay secret value.

### Bảng phân loại lỗi gợi ý

| Mã lỗi nội bộ | Nguyên nhân điển hình | Hướng xử lý | Thông điệp cho bên gọi |
| --- | --- | --- | --- |
| `VAULT_ACCESS_DENIED` | Token không hợp lệ, policy thiếu quyền, workload auth sai | Kiểm tra auth và ACL; không retry mù | Thông điệp dependency chung |
| `SECRET_NOT_FOUND` | KV path không tồn tại hoặc secret đã bị xóa | Kiểm tra cấu hình/path; không tự tạo giá trị giả | Thông điệp dependency chung |
| `VAULT_UNAVAILABLE` | Timeout, kết nối TLS/HTTP lỗi, Vault tạm không sẵn sàng | Retry có giới hạn, cảnh báo và circuit breaker | Dịch vụ tạm thời chưa sẵn sàng |
| `VAULT_THROTTLED` | HTTP 429/rate limit | Backoff theo policy và hạn mức | Dịch vụ tạm thời chưa sẵn sàng |
| `INVALID_VAULT_RESPONSE` | Dữ liệu thành công thiếu trường bắt buộc | Báo lỗi hợp đồng dữ liệu; không dùng secret rỗng | Lỗi xử lý nội bộ |
| `UNEXPECTED_VAULT_FAILURE` | Exception chưa được phân loại | Bảo toàn cause, theo dõi để cải tiến classifier | Lỗi xử lý nội bộ |

Đây là **mã do ứng dụng tự định nghĩa**, không phải danh sách lỗi mặc định do Spring Vault phát ra. Cần giới hạn tập giá trị bằng `enum` thay vì lấy nguyên văn error string từ server.

## 4. Hiện thực exception giữ cause nhưng message an toàn

Trước hết, định nghĩa loại lỗi. Tên `enum` có thể được ghi log hoặc ánh xạ sang mã lỗi công khai theo chính sách:

~~~java
public enum VaultFailureKind {
    VAULT_ACCESS_DENIED,
    SECRET_NOT_FOUND,
    VAULT_UNAVAILABLE,
    VAULT_THROTTLED,
    INVALID_VAULT_RESPONSE,
    UNEXPECTED_VAULT_FAILURE
}
~~~

Tiếp theo, tạo exception chỉ nhận **operation ID cố định** và **reference ID đã kiểm soát**. `getCause()` vẫn giữ đúng đối tượng lỗi gốc:

~~~java
import java.util.Objects;

public final class SafeVaultAccessException extends RuntimeException {

    private final VaultFailureKind kind;
    private final String operation;
    private final String referenceId;

    public SafeVaultAccessException(
            VaultFailureKind kind,
            String operation,
            String referenceId,
            Throwable originalCause) {

        // String này chỉ gồm dữ liệu nội bộ có kiểm soát;
        // tuyệt đối không dùng originalCause.getMessage().
        super("Vault operation failed; reference=" + referenceId,
                originalCause);

        this.kind = Objects.requireNonNull(kind, "kind");
        this.operation = Objects.requireNonNull(operation, "operation");
        this.referenceId = Objects.requireNonNull(referenceId, "referenceId");
    }

    public VaultFailureKind kind() {
        return kind;
    }

    public String operation() {
        return operation;
    }

    public String referenceId() {
        return referenceId;
    }
}
~~~

Trong ví dụ này, lời gọi constructor phải do lớp đáng tin cậy thực hiện với `operation` là một hằng số, `referenceId` sinh từ UUID hoặc trace ID đã được xác minh. **Không truyền operation/raw path/ref từ request người dùng vào exception** nếu chưa được ánh xạ sang danh sách giá trị cho phép.

Khi lỗi gốc tồn tại:

~~~java
Throwable original = new IllegalStateException("lỗi gốc chỉ dành cho nội bộ");
SafeVaultAccessException wrapped = new SafeVaultAccessException(
        VaultFailureKind.UNEXPECTED_VAULT_FAILURE,
        "ORDERS_CONFIG_READ",
        "ref-123",
        original);

assert wrapped.getCause() == original;
assert !wrapped.getMessage().contains("lỗi gốc");
~~~

Hai điều kiện trên mô tả hai yêu cầu **độc lập**: điều tra nội bộ còn nguyên `cause`; thông báo của exception bọc chỉ chứa thông tin đã được duyệt.

> **Cảnh báo về ranh giới:** Dù `wrapped.getMessage()` an toàn, `wrapped.printStackTrace()` vẫn in các cause kèm message gốc. Cấu hình serializer, logger, APM và error-reporting phải tuân đúng ranh giới an toàn; bản thân lớp exception không thể ép các thành phần bên ngoài tự redaction.

## 5. Đọc KV v2 trong Spring Vault và bọc lỗi đúng cách

Ví dụ sau dùng Java 17+, Spring Vault `VaultOperations` và KV v2 `secret/`. Ứng dụng giả định đã cấu hình Vault endpoint, TLS trust, workload authentication và policy `read` cho `secret/data/orders/config`. Nó **chỉ trả secret khi dữ liệu hợp lệ**; exception không bao gồm nội dung API key.

~~~java
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientResponseException;

@Service
public class OrdersSecretReader {

    private static final String OPERATION = "ORDERS_CONFIG_READ";
    private final VaultKeyValueOperations kv;

    public OrdersSecretReader(VaultOperations vault) {
        this.kv = vault.opsForKeyValue("secret", KeyValueBackend.KV_2);
    }

    public String readApiKey() {
        String referenceId = UUID.randomUUID().toString();
        VaultResponse response;

        try {
            response = kv.get("orders/config");
        } catch (RestClientResponseException ex) {
            // Khi HTTP status có thể truy cập bằng loại exception này,
            // chỉ dùng mã số; không đọc response body hoặc message.
            int status = ex.getStatusCode().value();
            VaultFailureKind kind = switch (status) {
                case 401, 403 -> VaultFailureKind.VAULT_ACCESS_DENIED;
                case 404 -> VaultFailureKind.SECRET_NOT_FOUND;
                case 429 -> VaultFailureKind.VAULT_THROTTLED;
                default -> status >= 500
                        ? VaultFailureKind.VAULT_UNAVAILABLE
                        : VaultFailureKind.UNEXPECTED_VAULT_FAILURE;
            };
            throw new SafeVaultAccessException(
                    kind, OPERATION, referenceId, ex);

        } catch (ResourceAccessException ex) {
            // Thường liên quan I/O, kết nối hoặc timeout.
            throw new SafeVaultAccessException(
                    VaultFailureKind.VAULT_UNAVAILABLE,
                    OPERATION, referenceId, ex);

        } catch (RuntimeException ex) {
            // Spring Vault cũng có thể bọc lỗi dưới các loại
            // exception khác, chẳng hạn VaultException.
            // Không suy ra status bằng cách parse ex.getMessage().
            throw new SafeVaultAccessException(
                    VaultFailureKind.UNEXPECTED_VAULT_FAILURE,
                    OPERATION, referenceId, ex);
        }

        // Lỗi dữ liệu cũng cần báo an toàn, không log toàn response.
        if (response == null) {
            throw new SafeVaultAccessException(
                    VaultFailureKind.SECRET_NOT_FOUND,
                    OPERATION, referenceId, null);
        }
        Map<String, Object> data = response.getData();
        Object raw = data == null ? null : data.get("apiKey");
        if (!(raw instanceof String apiKey) || apiKey.isBlank()) {
            throw new SafeVaultAccessException(
                    VaultFailureKind.INVALID_VAULT_RESPONSE,
                    OPERATION, referenceId, null);
        }
        return apiKey;
    }
}
~~~

Trong ví dụ, mọi lỗi truy cập được bọc cùng kiểu exception an toàn. Quan trọng là `throw new SafeVaultAccessException(..., ex)` **không đánh mất loại, stack trace và cause của exception gốc**. Nếu server trả body lỗi chứa secret hoặc path nhạy cảm, dữ liệu đó có thể còn nằm trong `ex` để điều tra với quyền phù hợp nhưng **không bị ghép vào message của exception bọc**.

Các lớp exception thực tế thay đổi theo phiên bản Spring Vault và HTTP transport. Chẳng hạn, lỗi từ `VaultTemplate` có thể xuất hiện dưới `VaultException` thay vì `RestClientResponseException`; nhánh cuối vẫn giữ nguyên cause mà không đoán lỗi dựa vào text. Nếu cần phân biệt HTTP status của ngoại lệ đã bọc, chỉ trích xuất qua API kiểu dữ liệu đáng tin cậy và kiểm thử với client/version đang dùng; không viết classifier bằng biểu thức regex trên `getMessage()`.

**Chú ý HTTP 404:** một đường dẫn KV v2 sai mount, namespace không phù hợp hoặc key không tồn tại đều có thể xuất hiện như “không tìm thấy”. Không trả thẳng “secret X không tồn tại” cho bên gọi công khai vì câu đó tiết lộ cấu trúc Vault; log nội bộ vẫn chỉ chứa `OPERATION` cố định.

### Vì sao không bắt `Throwable` hoặc bỏ qua nguyên nhân?

Không cần bắt `Throwable` trong service để xử lý lỗi thông thường: nó bao gồm các lỗi JVM nghiêm trọng như `OutOfMemoryError`. Hãy bắt những ngoại lệ từ client phù hợp và một fallback `RuntimeException` khi cần thiết. Không chuyển mọi lỗi thành giá trị `null` hoặc chuỗi secret mặc định, vì điều đó có thể khiến ứng dụng chạy tiếp với trạng thái thiếu quyền hoặc bí mật sai.

## 6. HTTP boundary: công bố Problem Details an toàn

Với Spring Framework 6 và Spring Boot, `ProblemDetail` phù hợp để trả lỗi theo định dạng `application/problem+json`. Controller advice dưới đây phân biệt **dependency tạm không sẵn sàng** với lỗi xử lý nội bộ, nhưng không đưa message/cause gốc ra bên ngoài:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class VaultFailureAdvice {

    private static final Logger log =
            LoggerFactory.getLogger(VaultFailureAdvice.class);

    @ExceptionHandler(SafeVaultAccessException.class)
    public ResponseEntity<ProblemDetail> handle(SafeVaultAccessException ex) {
        boolean temporarilyUnavailable = switch (ex.kind()) {
            case VAULT_UNAVAILABLE, VAULT_THROTTLED -> true;
            default -> false;
        };
        HttpStatus status = temporarilyUnavailable
                ? HttpStatus.SERVICE_UNAVAILABLE
                : HttpStatus.INTERNAL_SERVER_ERROR;

        ProblemDetail problem = ProblemDetail.forStatus(status);
        problem.setTitle("Không thể hoàn tất yêu cầu");
        problem.setDetail(temporarilyUnavailable
                ? "Dịch vụ tạm thời chưa sẵn sàng."
                : "Dịch vụ không thể xử lý yêu cầu.");
        problem.setProperty("code", temporarilyUnavailable
                ? "DEPENDENCY_UNAVAILABLE"
                : "INTERNAL_DEPENDENCY_ERROR");
        problem.setProperty("referenceId", ex.referenceId());

        // Chỉ log các trường đã kiểm soát, không truyền ex làm tham số log.
        log.warn("vault_failure operation={} kind={} referenceId={}",
                ex.operation(), ex.kind(), ex.referenceId());

        return ResponseEntity.status(status).body(problem);
    }
}
~~~

Ví dụ response:

~~~json
{
  "type": "about:blank",
  "title": "Không thể hoàn tất yêu cầu",
  "status": 503,
  "detail": "Dịch vụ tạm thời chưa sẵn sàng.",
  "code": "DEPENDENCY_UNAVAILABLE",
  "referenceId": "7f1269b1-92c6-4bc0-a722-071d1cba5fa4"
}
~~~

Mã `referenceId` cho phép đội vận hành tìm bản ghi tương ứng. Bên gọi không cần biết mount `secret/`, auth method, policy, nguyên nhân phân quyền, URL Vault hay loại exception từ SDK.

**Không trả nguyên HTTP status 403 của Vault thành 403 cho người dùng** chỉ vì dependency không có quyền đọc. `403` ở phía Vault là lỗi **quyền của backend/workload**, không nhất thiết là người dùng HTTP đã bị từ chối theo nghiệp vụ. Nếu gộp hai điều này, client bên ngoài có thể đưa ra quyết định sai hoặc biết thêm về cấu hình Vault. Lỗi 503 chỉ nên dùng khi dependency thực sự tạm unavailable; sai policy/config thường là lỗi máy chủ cần sửa vận hành, không nên retry từ phía client công khai.

Để giảm rủi ro Spring Boot tự xuất message/stacktrace ở đường lỗi chưa được advice xử lý, có thể giới hạn cấu hình lỗi mặc định:

~~~yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
~~~

Các lựa chọn này hỗ trợ hạn chế nội dung trên endpoint lỗi mặc định. Chúng **không** tự bảo vệ custom controller/advice, logger, tracing, message broker, audit sink hoặc thư viện báo lỗi khác; mọi kênh vẫn cần review.

## 7. Logging và tracing mà vẫn giữ được khả năng điều tra

### Log an toàn theo allowlist

Nên ghi những trường đã được kiểm soát:

~~~java
log.warn("vault_failure operation={} kind={} ref={}",
        ex.operation(), ex.kind(), ex.referenceId());
~~~

Khi thật sự cần thêm thông tin về loại cause trong khu vực log nội bộ, chỉ lấy **class name**:

~~~java
Throwable cause = ex.getCause();
String causeClass = cause == null
        ? "none"
        : cause.getClass().getSimpleName();

log.warn("vault_failure kind={} ref={} causeClass={}",
        ex.kind(), ex.referenceId(), causeClass);
~~~

Tránh những cách ghi log sau:

~~~java
// KHÔNG NÊN:
log.error("Vault failed", ex);                      // In full stack/cause.
log.error("Vault failed: {}", ex.getMessage());     // Có thể lộ dữ liệu.
log.error("Cause: {}", ex.getCause());              // Có thể gọi toString().
log.error("Payload: {}", requestBody);              // Secret trong request.
log.error("Response: {}", vaultResponse.getData()); // Secret trong response.
~~~

Một số backend SLF4J nhận tham số `Throwable` ở vị trí cuối và tự hiểu đó là exception cần in stack trace, kể cả khi đặt placeholder. Vì vậy, **không truyền nguyên Throwable vào lời gọi log thường**. Quy tắc tương tự áp dụng cho `System.err.println(ex)`, `printStackTrace()`, log của interceptors, `@ControllerAdvice`, message queue dead-letter và exception reporter.

### Metrics và distributed tracing

Với Micrometer/Prometheus, metric nên có label giới hạn cardinality và được duyệt:

~~~text
vault_operation_failures_total{
  operation="ORDERS_CONFIG_READ",
  kind="VAULT_ACCESS_DENIED"
}
~~~

Không gắn `token`, `secret value`, `role_id`, `secret_id`, URL đầy đủ, request payload hoặc `exception.message` vào metric label. Một `referenceId` riêng cho mỗi sự cố cũng **không phù hợp làm label Prometheus** do cardinality quá cao; giữ ID trong log/traces phù hợp.

Với OpenTelemetry/APM, việc gọi `span.recordException(ex)` hoặc để framework tự record lỗi có thể ghi các attribute như `exception.message` và `exception.stacktrace`. Khi cần chống lộ bí mật, phải cấu hình instrumentation/exporter để **không tự xuất các trường đó** hoặc xử lý qua chính sách redaction đã kiểm thử, rồi chỉ record mã lỗi/cause class đã lọc. Không giả định công cụ tracing mặc định an toàn.

### Debug có kiểm soát

Việc **bảo toàn cause** vẫn có ích: đội vận hành có thể phân biệt nguyên nhân mạng, TLS, Vault auth, role/policy và hợp đồng API. Nếu tổ chức cần lưu full stack trace để điều tra sự cố nghiêm trọng, nên dùng kênh chẩn đoán có quyền truy cập riêng, retention ngắn, cơ chế redaction được thử nghiệm và quy trình phê duyệt; không bật “debug logging toàn bộ” trên production. Chính cause có thể mang thông tin nhạy cảm, nên ngay cả kho log nội bộ cũng không mặc nhiên được phép lưu thô.

## 8. Retry và khả năng phục hồi dựa trên loại lỗi, không dựa vào message

Lỗi Vault cần được phân loại để tránh retry vô hạn hoặc làm sự cố nặng hơn:

| Loại lỗi | Có retry? | Giải thích |
| --- | --- | --- |
| Lỗi auth/403, policy thiếu quyền | Không retry cùng credential liên tục | Cần sửa role/policy hoặc tái xác thực theo cơ chế token phù hợp |
| Lỗi 404 do secret bắt buộc không tồn tại | Không retry nhanh vô hạn | Cần sửa path/provision dữ liệu |
| 429/rate limit | Có thể retry có giới hạn | Backoff/jitter; tôn trọng `Retry-After` nếu server/client cung cấp và phù hợp |
| Timeout hoặc kết nối gián đoạn | Có thể retry có giới hạn với thao tác đọc | Cần timeout/deadline, tránh request storm |
| 5xx Vault | Có thể retry ngắn hạn | Kết hợp circuit breaker, cảnh báo và giới hạn song song |
| Response hợp lệ HTTP nhưng thiếu trường bắt buộc | Không retry tùy tiện | Kiểm tra version/engine/schema, không dùng giá trị giả |
| Lỗi chưa phân loại | Không tự động retry | Bảo toàn cause và điều tra để bổ sung classifier có bằng chứng |

Đối với KV read chỉ đọc, retry thường ít rủi ro hơn so với request cấp PKI certificate, tạo SSH certificate hoặc Transit rewrap/rotate. Một request thay đổi trạng thái đã **thành công ở Vault nhưng mất response** có thể sinh tác dụng phụ lần nữa khi retry. Phải xác minh tính idempotent và hợp đồng cụ thể của từng endpoint trước khi áp dụng cùng chính sách retry.

**Circuit breaker không thay thế quản lý token.** Nếu token hết hạn, policy bị rút hoặc AppRole/Kubernetes auth không hoạt động, breaker có thể giúp hạn chế lưu lượng nhưng không sửa được lỗi phân quyền. Spring Vault session manager và bộ phận vận hành auth phải xử lý đúng nguồn phát sinh.

### Không dùng secret cũ vượt giới hạn cho phép

Một số ứng dụng cache secret để tiếp tục vận hành khi Vault mất mạng. Điều này chỉ phù hợp nếu từng loại dữ liệu có **chính sách độ mới và thời hạn rõ ràng**. Không được lặng lẽ dùng credential đã bị thu hồi, lease đã hết hạn hoặc X.509 certificate quá `Not After`. Khi fail, có thể giữ cấu hình cũ **còn hợp lệ** trong thời gian giới hạn đã được duyệt; hết hạn thì fail closed và báo sự cố.

## 9. Các tình huống thực tế ở KV, Transit, PKI và token

### KV v2: bí mật thiếu hoặc lỗi phân quyền

Ứng dụng gọi `GET /v1/secret/data/orders/config`. Nếu dữ liệu không tồn tại, với API mức cao có thể nhận `null`; nếu policy thiếu `read`, có thể nhận exception. Cả hai không được trả raw error string cho frontend; mặt khác không nên gộp chúng thành một lỗi “không có secret” ở tầng nội bộ vì hướng xử lý hoàn toàn khác nhau.

### Transit: plaintext và ciphertext dễ lộ qua exception/log

Gọi `transit/encrypt/orders-key` có `plaintext` là Base64 của dữ liệu cần mã hóa. **Base64 không che giấu plaintext**. Tránh log request body, đầu vào, response ciphertext nếu nó bị quy định là dữ liệu nhạy cảm, cũng như message của exception khi server/plugin có thể phản chiếu tham số request. Mã lỗi công khai nên là `DEPENDENCY_UNAVAILABLE` hoặc `INTERNAL_DEPENDENCY_ERROR`, còn nội bộ ghi `TRANSIT_ENCRYPT` và loại lỗi.

### PKI: private key trong response cấp chứng thư

`pki/issue/<role>` có thể trả `private_key` cùng chứng thư và chain. Lỗi ở bước lưu/cập nhật TLS không được làm cho logger in cả `CertificateBundle` hoặc response map. Với request PKI dùng CSR, CSR và DN/SAN có thể chứa định danh nội bộ; nên chỉ log alias role được duyệt và mã tham chiếu.

### Workload authentication: phân biệt credentials với lỗi cấu hình

AppRole dùng `role_id`/`secret_id`, Kubernetes auth dùng service-account JWT. Nếu login thất bại, không log hai giá trị xác thực hay raw body request. Giữ cause để phân biệt timeout TLS, role không tồn tại, JWT không được chấp nhận hoặc policy không phù hợp. Ngay cả sự kiện login thành công cũng không nên log Vault token nhận về.

### Lease: token renewal và secret lease là hai vòng đời

Một lỗi renew token không đồng nghĩa DB credential lease cũng thất bại hoặc ngược lại. Gắn `operation` khác nhau như `VAULT_TOKEN_RENEW` và `DATABASE_LEASE_RENEW` để tìm đúng cơ chế hỏng. Không đính kèm raw token/lease ID vào message công khai; lease ID có thể chứa path/danh tính nội bộ.

## 10. Kiểm thử khả năng giữ cause và chống rò rỉ secret

Để kiểm thử, dùng **chuỗi sentinel giả** có hình dạng dễ phát hiện, ví dụ `SENSITIVE_TEST_VALUE_NEVER_LOG`. Không dùng token thật khi làm test logging, HTTP hoặc tracing. Có thể dùng Vault dev/test instance hoặc HTTP server giả lập tương thích Vault để trả về response lỗi chứa sentinel.

| Trường hợp | Thiết lập | Điều kiện PASS |
| --- | --- | --- |
| Giữ cause | Giả lập `RuntimeException` gốc, gọi adapter | Exception bọc có `getCause() == original` |
| Không ghép message | Cause chứa sentinel | `SafeVaultAccessException.getMessage()` không chứa sentinel |
| HTTP không lộ | Cause/body Vault chứa sentinel | Body `ProblemDetail` chỉ có mã công khai, câu cố định và reference ID |
| Log không lộ | Ghi nhận log khi lời gọi thất bại | Log không chứa sentinel, request body, token hoặc raw exception message |
| Trace không lộ | Bật instrumentation và exporter test | Không có `exception.message`/`stacktrace` chứa sentinel |
| Quyền bị từ chối | HTTP lỗi Vault 403 hoặc VaultException tương ứng | Không trả 403 của dependency như lỗi authorization của caller một cách máy móc |
| Vault tạm ngừng | Timeout, lỗi kết nối, 429, 5xx | Mã lỗi nội bộ phù hợp, retry/breaker có giới hạn, không in raw cause |
| KV không tồn tại | Response `null` hoặc 404 theo client | Không dùng secret mặc định; lỗi an toàn, có reference ID |
| Dữ liệu malformed | Body thành công thiếu `apiKey` | Báo `INVALID_VAULT_RESPONSE`, không log response |
| Lỗi từ Transit/PKI | Giả lập request/response chứa plaintext hoặc private key giả | Không có secret trên HTTP/log/traces của đường lỗi |
| Unhandled error | Một exception khác lọt khỏi adapter | Global handler vẫn không hiển thị stacktrace hoặc raw message |

Ví dụ assertion về nguyên tắc:

~~~java
String sentinel = "SENSITIVE_TEST_VALUE_NEVER_LOG";
RuntimeException original = new RuntimeException(sentinel);
SafeVaultAccessException wrapped = new SafeVaultAccessException(
        VaultFailureKind.UNEXPECTED_VAULT_FAILURE,
        "ORDERS_CONFIG_READ",
        "test-ref-001",
        original);

if (wrapped.getCause() != original) {
    throw new AssertionError("Đã mất nguyên nhân gốc");
}
if (wrapped.getMessage().contains(sentinel)) {
    throw new AssertionError("Message của wrapper đã lộ secret");
}
// Ở test tích hợp, assert thêm HTTP body, captured logs và trace exports
// đều KHÔNG chứa sentinel. Không kiểm tra chỉ mỗi getMessage().
~~~

Test bảo mật cần chạy qua **đúng serializer, logger và instrumentation production đang sử dụng**. Chỉ mock `SafeVaultAccessException` và kiểm tra message của nó không thể chứng minh framework sẽ không tự ghi cause stack trace. Nếu thay logging library, APM agent hay cấu hình Spring Boot, phải kiểm tra lại ranh giới.

## 11. Checklist review code và vận hành

- [ ] Các message lỗi được xây từ chuỗi cố định, `enum` và ID đã kiểm soát; không chứa `getMessage()` từ nguồn không tin cậy.
- [ ] Khi bọc lỗi, dùng constructor nhận `Throwable cause`; không phá mất nguyên nhân của lỗi I/O, auth hoặc Vault operation.
- [ ] `@RestControllerAdvice` chỉ trả mã lỗi, thông điệp công khai và reference ID; không serialize trực tiếp Throwable.
- [ ] Logger không nhận Throwable, raw request/response, token, private key hoặc secret value ở các luồng thông thường.
- [ ] Trace/metric/audit sink không xuất `exception.message`, stack trace hay raw URL có tham số bí mật.
- [ ] Mã `operation` nằm trong allowlist và phân biệt KV, auth, lease, Transit, PKI.
- [ ] Retry có giới hạn chỉ cho lỗi phù hợp, đã xem xét idempotency của từng Vault endpoint.
- [ ] Không chuyển lỗi thiếu secret/quyền thành secret mặc định hoặc credential cũ hết hạn.
- [ ] Test dùng sentinel kiểm tra đồng thời cause, HTTP, log, tracing và failure fallback.
- [ ] Người vận hành có cách đối chiếu reference ID với audit/trace an toàn mà không cần tiết lộ secret cho người dùng.

## 12. Ghi nhớ

Có hai yêu cầu cùng đúng: **giữ nguyên nguyên nhân lỗi** để phục vụ phân loại và điều tra; **không đưa dữ liệu nhạy cảm từ lỗi gốc ra kênh công khai**. Trong Spring Vault, cách làm thực tế là bọc exception với `cause` nguyên vẹn, thêm loại lỗi và mã tham chiếu có kiểm soát, sau đó chặn việc serialize/log/tracing toàn bộ cause ở các ranh giới.

Không có quy tắc “chỉ cần không gọi `getMessage()` là đủ”: logger mặc định, APM và serializer vẫn có thể đọc cause. Bảo đảm an toàn bằng **allowlist các trường được phép xuất, phân quyền chẩn đoán, kiểm thử với sentinel và giám sát toàn bộ luồng lỗi**.

### Câu hỏi tự kiểm tra

1. Vì sao `throw new IllegalStateException("Lỗi Vault: " + ex.getMessage(), ex)` vẫn có thể làm lộ secret dù đã giữ cause?
2. Cách nào cho phép giữ `Throwable` gốc nhưng không lộ response body Vault qua HTTP?
3. Vì sao `log.error("Vault failed", wrapped)` có thể nguy hiểm dù `wrapped.getMessage()` chỉ chứa reference ID?
4. Khi Spring Vault trả lỗi do policy 403, HTTP API bên ngoài có nhất thiết phải trả 403 cho người dùng không? Tại sao?
5. Có nên retry `pki/issue/<role>` sau timeout giống thao tác `GET` KV không? Những điều kiện nào cần kiểm tra?
6. Một test chỉ assert `wrapped.getMessage()` không chứa sentinel đã đủ chứng minh hệ thống không rò rỉ secret chưa?
7. Trong Spring Vault, bạn nên lưu loại thông tin nào vào metrics, logs và traces để giữ khả năng điều tra mà không làm tăng rủi ro lộ dữ liệu?

### Tài liệu tham khảo

- [Spring Vault — VaultTemplate và truy cập Vault](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault — Vault client và xác thực](https://docs.spring.io/spring-vault/reference/vault/vault-client.html)
- [Spring Vault — Secrets engines và KV](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)
- [Spring Framework — Exception handling trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html)
- [Spring Framework — Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [HashiCorp Vault — Policies](https://developer.hashicorp.com/vault/docs/concepts/policies)
- [HashiCorp Vault — Audit devices](https://developer.hashicorp.com/vault/docs/audit)
- [HashiCorp Vault — Lease, revoke và renew](https://developer.hashicorp.com/vault/docs/concepts/lease)
