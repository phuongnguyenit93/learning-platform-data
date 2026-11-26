# Che dữ liệu ở log HTTP, log đối tượng và thông báo lỗi

## 1. Bài toán trong ứng dụng Spring Vault

Trong **Spring Vault**, ứng dụng Java thường gọi HashiCorp Vault bằng `VaultTemplate` / `VaultOperations`, xác thực theo workload (AppRole, Kubernetes auth hoặc cơ chế tương đương) và tuân theo Vault policy. Các kết quả nhận được có thể chứa API key từ KV, database password động, Vault token, AppRole SecretID, wrapping token, plaintext Transit hoặc private key PKI. Chúng phải nằm trong phạm vi sử dụng hợp lệ của ứng dụng.

Tuy nhiên, chỉ cần ghi nhầm một đối tượng hoặc exception vào log, bí mật có thể bị sao chép sang console, container runtime, hệ thống tập trung log, APM, trace, backup, ticket xử lý lỗi và nhiều người xem dashboard. Quyền đọc log **không nhất thiết giống quyền được Vault cấp để đọc secret**. Khi secret xuất hiện trong log, việc rotate secret không tự xóa các bản sao cũ.

Ví dụ, dịch vụ `orders-api` đọc `secret/data/orders/payment` từ KV v2:

~~~java
VaultResponse response =
        vaultOperations.read("secret/data/orders/payment");

// SAI: có thể làm lộ toàn bộ map data/metadata và API key.
log.debug("Vault response={}", response);

// SAI: exception có thể chứa body lỗi, URI hoặc thông tin nhạy cảm.
log.error("Vault call failed", exception);
~~~

Bài **“Che dữ liệu ở log HTTP, log đối tượng và thông báo lỗi”** thuộc chương **Quan sát và hiệu năng** giúp xây dựng giải pháp quan sát Spring Vault mà không ghi lại bí mật. Trọng tâm là **allowlist metadata cần cho vận hành**, thay vì ghi dữ liệu thô rồi cố che bằng vài biểu thức regex.

### Kết quả cần đạt

1. Xác định những trường nhạy cảm trong HTTP request/response, object, exceptions và traces.
2. Cấu hình HTTP logging an toàn trên đúng client `VaultTemplate` sử dụng.
3. Viết Java interceptor ghi status/latency, tránh body, header, path nhạy cảm.
4. Bảo vệ `toString()`/serialization của các object chứa secret và xây lỗi an toàn cho caller.
5. Thiết kế metrics/tracing có nhãn hữu hạn, chi phí hợp lý và không lộ secret.
6. Thử nghiệm bằng **secret giả có dấu nhận biết** để phát hiện rò rỉ qua nhiều lớp.

> **Quy tắc nền tảng:** Không log raw `VaultResponse`, request/response body, HTTP headers, exception message hoặc object bất kỳ chứa secret. Chỉ log loại thao tác, kết quả, thời gian, mã trạng thái và mã lỗi đã phân loại.

## 2. Phân loại dữ liệu trước khi viết log

| Dữ liệu | Xuất hiện ở đâu? | Chính sách log |
| --- | --- | --- |
| `X-Vault-Token`, `Authorization` | Request headers | **Không bao giờ ghi giá trị** |
| `auth.client_token`, `client_token`, `secret_id` | Auth, AppRole | **Không ghi** |
| `wrap_info.token` | Response wrapping | **Không ghi**; token dùng một lần vẫn là bearer secret |
| `data.data.password`, `apiKey` | KV v2, database credentials | **Không ghi** |
| `private_key`, PEM bundle | PKI issue | **Không ghi** |
| Transit `plaintext`, `ciphertext`, `context` | Encrypt/decrypt/rewrap | Không ghi raw payload hoặc Base64 |
| `lease_id`, `accessor`, `role_id` | Metadata/token/AppRole | Metadata có thể nhạy cảm; chỉ ghi khi policy cho phép |
| Certificate subject, serial, CA chain | PKI metadata | Có thể lộ topology/danh tính; chọn trường phù hợp |
| Vault path, namespace, tenant ID | URI, exception, metric labels | Không log path đầy đủ/tenant tùy ý; dùng operation label cố định |
| HTTP status, duration, retry count | Quan sát vận hành | Thường có thể ghi, không kèm payload |
| Correlation/request ID hợp lệ | Tracing | Ghi nếu đã xác minh không mang dữ liệu nhạy cảm |

**Base64 không phải che dữ liệu.** Chẳng hạn payload `c2VjcmV0` có thể giải mã ngay thành `secret`. Một số token trông như chuỗi ngẫu nhiên hoặc UUID nhưng vẫn cho phép truy cập Vault; không được đưa chúng vào logs, URI, HTTP response hoặc metric tags.

### 2.1. Dữ liệu định danh cũng có thể gây rò rỉ

Ngay cả khi không có password, `secret/data/tenants/acme/payment`, `orders-prod` hoặc subject của certificate có thể tiết lộ tenant, môi trường, quan hệ giữa dịch vụ và cấu trúc lưu trữ. Số liệu quan sát nên sử dụng nhóm giá trị đã được duyệt: `operation=kv_read`, `engine=kv_v2`, `result=error`. Nếu cần biết chính xác Vault path trong incident, ưu tiên hệ thống audit có phân quyền thay vì gắn raw path lên dashboard.

Không dùng hash của secret để tạo ID log mặc định. Hash của giá trị ít entropy có thể bị brute force; hash ổn định cũng cho phép theo dõi cùng secret ở nhiều nơi. Dùng **KV version**, mã sự kiện độc lập hoặc định danh triển khai đã được phê duyệt.

## 3. Thiết kế sự kiện log từ allowlist

### 3.1. Một log event an toàn trông như thế nào?

~~~json
{
  "event": "vault_client_operation",
  "operation": "kv_read",
  "outcome": "failure",
  "failure_category": "permission_denied",
  "http_status": 403,
  "attempt": 1,
  "duration_ms": 18,
  "trace_id": "d24c1a6f88c94a9aa6a30f8c1d54a231"
}
~~~

Mỗi trường được tạo từ nguồn đáng tin cậy:

- `operation` là hằng số hoặc enum (`kv_read`, `transit_encrypt`, `pki_issue`, `lease_renew`), không lấy từ URL người dùng gửi.
- `outcome` là tập giá trị `success`, `failure`, `timeout`.
- `failure_category` là phân loại ngắn như `permission_denied`, `not_found`, `transport`, `tls`, `vault_unavailable`, `unknown`.
- `http_status` chỉ xuất hiện khi có **HTTP response thật**, không bịa 503 khi lỗi TCP.
- `attempt` và `duration_ms` là số, được đo trong ứng dụng.
- `trace_id` được tracing system tạo/kiểm tra định dạng. Không ghi một chuỗi header tùy ý có thể chứa newline hoặc log injection.

Tránh các trường `message=exception.getMessage()`, `requestHeaders`, `responseBody`, `arguments`, `params` hoặc `debugContext` nếu chúng có thể chứa bí mật.

### 3.2. Vì sao blacklist/regex không đủ?

Nếu chỉ che các từ `password` và `token`, dữ liệu có thể vẫn đi qua tên khác như `api_key`, `privateKeyPem`, `X-Vault-Token`, `credentials.value`, `data.data` hoặc nội dung lồng trong List/Map. Một Spring Vault upgrade có thể thêm field mới mà quy tắc mask chưa biết. Exception message có thể chứa JSON bị escape hoặc token đã URL-encode; Base64, PEM nhiều dòng và binary payload càng khó kiểm tra.

**Không thu thập** body/headers là giải pháp đơn giản hơn và hiệu quả hơn. Khi buộc phải xuất dữ liệu có cấu trúc cho log, dùng một DTO log riêng chỉ chứa field allowlist; không serialize nguyên object rồi lọc chuỗi.

## 4. Che dữ liệu trong HTTP request/response logs

### 4.1. Những điểm có thể ghi payload ngoài ý muốn

~~~mermaid
flowchart LR
    A[Java service] --> B[VaultTemplate / RestOperations]
    B --> C[HTTP interceptor]
    C --> D[HTTP wire logger]
    D --> E[Proxy / Service mesh]
    E --> F[Vault]
    C --> G[Application logs]
    D --> G
    E --> H[Proxy logs / Traces]
    G --> I[Collector / Backup / Dashboard]
    H --> I
~~~

Spring Vault có thể dùng Spring HTTP client với các request factories khác nhau; tùy dự án có Apache HttpClient, JDK HTTP client, Reactor Netty (nếu dùng reactive API), APM agent, ingress hoặc service mesh. Mỗi tầng có cấu hình logging riêng. Che ở `ClientHttpRequestInterceptor` **không bảo đảm** wire logging của HTTP client bên dưới đã tắt.

| Bề mặt | Rủi ro | Kiểm soát |
| --- | --- | --- |
| Headers | `X-Vault-Token`, Authorization, cookie, token của proxy | Không log toàn bộ header map |
| Request body | `secret_id`, Transit plaintext Base64, CSR hoặc payload KV | Không capture request body |
| Response body | KV secret, dynamic password, wrapping token, `auth.client_token`, PKI private key | Không capture response body |
| URI/query | Vault path và tenant; token đôi khi bị đưa nhầm vào query | Chỉ log operation name đã allowlist |
| Error body | Proxy có thể phản chiếu input; Vault trả message tùy phiên bản | Không gọi `getResponseBodyAsString()` để log |
| APM/span | Auto-capture HTTP headers, request/response details | Chặn/loại bỏ attributes nhạy cảm tại agent/collector |

Ví dụ cần tránh:

~~~java
// SAI: log header có thể mang Vault token.
log.debug("headers={}", request.getHeaders());

// SAI: body có thể mang API key hoặc Transit plaintext.
log.debug("request={}", new String(body, StandardCharsets.UTF_8));

// SAI: error body có thể chứa secret hoặc chi tiết nội bộ.
log.error("Vault error body={}", httpError.getResponseBodyAsString());
~~~

Một vấn đề khác của logging body là **hiệu năng**: đọc/buffer response làm tăng bộ nhớ và số bản sao secret. Nếu interceptor tiêu thụ `InputStream` mà không có buffering đúng, tầng sau có thể không đọc được response nữa. Khi chỉ cần status và thời gian, không có lý do động đến body.

### 4.2. Cấu hình logging mặc định

Ví dụ Spring Boot `application.yml` cho môi trường production:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.vault: INFO
    org.springframework.web.client: INFO
    # Chỉ có tác dụng khi HTTP stack sử dụng đúng library:
    org.apache.hc.client5.http.wire: OFF
    org.apache.http.wire: OFF
    reactor.netty.http.client: INFO
~~~

Các logger và tên category phụ thuộc phiên bản thư viện, HTTP client thực tế và công cụ tracing. Danh sách trên chỉ là **một lớp cấu hình**, cần kiểm tra thêm:

1. Logger của Spring Vault và HTTP transport thật sự được `VaultTemplate` sử dụng.
2. Interceptor ghi request/response tự xây, `DEBUG`/`TRACE`, Apache wire logging, Reactor Netty wiretap.
3. APM agent, OpenTelemetry HTTP instrumentation, Spring Security debug.
4. Reverse proxy, ingress, service mesh và collector có thể capture payload sau TLS termination.
5. Tính năng debug thay đổi log level tại runtime và snapshot lỗi của framework.

Không bật `curl -v`, shell `set -x`, HAR capture hoặc wiretap khi làm việc với token/secret thật mà không có quy trình bảo vệ artifact tương ứng.

## 5. Mẫu Java interceptor chỉ đo metadata

Một interceptor có thể ghi HTTP method, status và elapsed time mà không xem headers, URI hay body:

~~~java
import java.io.IOException;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpRequest;
import org.springframework.http.client.ClientHttpRequestExecution;
import org.springframework.http.client.ClientHttpRequestInterceptor;
import org.springframework.http.client.ClientHttpResponse;

public final class VaultSafeHttpInterceptor
        implements ClientHttpRequestInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(VaultSafeHttpInterceptor.class);

    @Override
    public ClientHttpResponse intercept(
            HttpRequest request,
            byte[] body,
            ClientHttpRequestExecution execution) throws IOException {

        long started = System.nanoTime();
        try {
            ClientHttpResponse response = execution.execute(request, body);

            // Không đọc request.getHeaders()/getURI(), body,
            // response.getHeaders() hoặc response.getBody().
            if (log.isDebugEnabled()) {
                log.debug(
                        "vault_http method={} status={} duration_ms={}",
                        request.getMethod(),
                        response.getStatusCode().value(),
                        elapsedMillis(started));
            }

            return response;
        } catch (IOException error) {
            // Không ghi error hoặc error.getMessage() vào log.
            log.warn(
                    "vault_http outcome=transport_failure duration_ms={}",
                    elapsedMillis(started));
            throw error;
        }
    }

    private static long elapsedMillis(long start) {
        return TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - start);
    }
}
~~~

**Kết nối với Spring Vault:** Interceptor phải được gắn vào **HTTP client/`RestTemplate` mà `VaultTemplate` và cơ chế xác thực/session thực sự dùng**. Thêm nó vào một `RestTemplate` bất kỳ không làm thay đổi mọi Vault calls. Cách tạo client, request factory và đăng ký interceptor phụ thuộc Spring Vault version và cấu hình `VaultEndpoint`/`VaultTemplate` của dự án. Xác minh bằng test với đúng client đã cấu hình.

Trong ví dụ, success chỉ log ở DEBUG để hạn chế I/O; lỗi vận chuyển chỉ ghi metadata ở WARN. Ở production có lưu lượng lớn, chuyển phần timing sang Micrometer histogram. Ngoại lệ được ném lên tầng gọi nhằm giữ hành vi HTTP client; **tầng trên không được log nguyên exception** nếu chưa xử lý an toàn.

## 6. Bảo vệ log đối tượng và serialization

### 6.1. `VaultResponse` và Map lồng nhau

Vault KV v2 trả JSON có cấu trúc `data.data`, vì vậy `VaultResponse.getData()` thường chứa cả giá trị bí mật lẫn metadata như version. Không log toàn bộ đối tượng:

~~~java
VaultResponse response =
        vaultOperations.read("secret/data/orders/payment");

// SAI: Spring Vault response có thể chứa toàn bộ secret.
log.info("response={}", response);

// SAI: nested Map vẫn chứa secret.
log.debug("map={}", response.getData());

// SAI: JSON serialization không tự loại bỏ secret.
log.debug("json={}", objectMapper.writeValueAsString(response));
~~~

Tương tự, không log `CertificateBundle`, `VaultToken`, DTO chứa `secret_id`, `private_key` hoặc Map của dynamic credentials.

### 6.2. `toString()`, Lombok và record mặc định

Lombok `@Data`/`@ToString` và Java `record` có thể đưa mọi field vào `toString()`. Ngay cả khi `@JsonIgnore` loại field khỏi JSON, nó **không đảm bảo** field cũng bị ẩn trong `toString()`, debug logger hoặc reflection.

Nếu buộc phải chứa secret trong một object nội bộ, override `toString()` để chỉ lộ metadata được duyệt:

~~~java
public final class PaymentCredential {

    private final String apiKey; // Bí mật, không đưa ra log/API.
    private final long kvVersion;

    public PaymentCredential(String apiKey, long kvVersion) {
        if (apiKey == null || apiKey.isBlank()) {
            throw new IllegalArgumentException(
                    "Payment credential is missing");
        }
        this.apiKey = apiKey;
        this.kvVersion = kvVersion;
    }

    // Chỉ dùng trong lớp gọi hệ thống thanh toán được kiểm soát.
    public String valueForPaymentClient() {
        return apiKey;
    }

    public long kvVersion() {
        return kvVersion;
    }

    @Override
    public String toString() {
        return "PaymentCredential[apiKey=REDACTED, kvVersion="
                + kvVersion + "]";
    }
}
~~~

`PaymentCredential` trong ví dụ không được trả trực tiếp qua controller hoặc serializer. Với Lombok có thể dùng `@ToString.Exclude`, còn record chứa secret cần override `toString()` nếu object có nguy cơ bị log. Cách bảo vệ tốt nhất vẫn là **không log object giữ secret** và tạo một kiểu log event riêng.

| Loại object | Rủi ro | Giải pháp |
| --- | --- | --- |
| `Map<String, Object>` nested | Field mới được thêm và tự lộ | Chỉ trích xuất metadata allowlist |
| Java `record` | `toString()` chứa toàn bộ fields | Không dùng cho log object bí mật, override nếu cần |
| Lombok DTO | Field password/token tự được thêm vào output | `@ToString.Exclude` và test |
| JSON serializer | Getter hoặc reflection có thể xuất giá trị | Không serialize object secret; `@JsonIgnore` là lớp phụ |
| `byte[]`, `char[]` | Có thể thành Base64/hex hoặc bị dump | Không ghi giá trị |
| PKI `KeyStore`/PEM | Có private key hoặc certificate nội bộ | Chỉ ghi expiry/alias đã phê duyệt |
| `VaultResponse`/`VaultResponseSupport` | Có `data` hoặc `auth` | Tránh `log.info("{}", response)` |

Với `String` Java, không thể đảm bảo xóa byte/char cũ khỏi heap do immutable và các bản sao của runtime. Cần hạn chế thời gian sống của tham chiếu, không nhân bản trong message/log/cache.

## 7. Thông báo lỗi và exception là đường rò rỉ độc lập

### 7.1. Không truyền raw exception ra logger/HTTP response

Một lỗi Spring Web hoặc Spring Vault có thể chứa HTTP response body, URL, headers, request path hoặc chuỗi do proxy phản chiếu. Các cách viết dưới đây cần tránh:

~~~java
// SAI khi chưa chắc nội dung cause/message đã được lọc.
log.error("Vault read error: {}", exception.getMessage());
log.error("Vault read error", exception);
throw new IllegalStateException(
        "Vault read failed: " + exception.getMessage(), exception);
~~~

Ngay cả khi `log.error("...", exception)` chủ yếu in stack trace, **message của exception và cause chain** có thể mang response body hoặc thông tin nhạy cảm. Một `@ControllerAdvice` hoặc framework error serializer sau đó có thể đưa message ra HTTP response người dùng.

Không cố phân loại lỗi bằng cách tìm từ `"sealed"`, `"permission denied"` trong raw message rồi ghi phần message đó. Khi có thể, phân loại bằng HTTP status, loại lỗi vận chuyển và endpoint đã được xác định trước.

### 7.2. Bộ phân loại lỗi trả enum, không trả text nguy hiểm

~~~java
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import javax.net.ssl.SSLException;

import org.springframework.web.client.RestClientResponseException;

public final class VaultFailureClassifier {

    public enum Category {
        PERMISSION_DENIED, BAD_REQUEST, NOT_FOUND,
        RATE_LIMITED, VAULT_UNAVAILABLE,
        TLS_FAILURE, TIMEOUT, CONNECT_FAILURE, UNKNOWN
    }

    private VaultFailureClassifier() {}

    public static Category classify(Throwable failure) {
        for (Throwable cause = failure; cause != null;
             cause = cause.getCause()) {

            if (cause instanceof SSLException) {
                return Category.TLS_FAILURE;
            }
            if (cause instanceof SocketTimeoutException) {
                return Category.TIMEOUT;
            }
            if (cause instanceof ConnectException) {
                return Category.CONNECT_FAILURE;
            }
            if (cause instanceof RestClientResponseException httpError) {
                int status = httpError.getStatusCode().value();
                return switch (status) {
                    case 400 -> Category.BAD_REQUEST;
                    case 401, 403 -> Category.PERMISSION_DENIED;
                    case 404 -> Category.NOT_FOUND;
                    case 429 -> Category.RATE_LIMITED;
                    case 500, 502, 503, 504 ->
                            Category.VAULT_UNAVAILABLE;
                    default -> Category.UNKNOWN;
                };
            }
        }
        return Category.UNKNOWN;
    }
}
~~~

**Giới hạn:** Spring Vault có thể bọc HTTP exception trong kiểu khác; khi không có `RestClientResponseException` trong cause chain thì `UNKNOWN` an toàn hơn việc đoán từ raw message. Trong ứng dụng thực, nên giới hạn số bước duyệt cause, chống cấu trúc cause bất thường và kiểm thử với implementation đang dùng.

Mã `429` của **`GET /sys/health`** mặc định biểu thị **standby**, trong khi 429 của API nghiệp vụ có thể là quota/rate limiting. Phải giữ **ngữ cảnh loại request** khi phân loại và không áp chung một chính sách retry chỉ dựa vào số 429.

### 7.3. Đưa thông báo lỗi cố định ra ngoài

~~~java
public final class RequiredSecretUnavailableException
        extends RuntimeException {
    public RequiredSecretUnavailableException() {
        super("Required configuration is temporarily unavailable");
    }
}
~~~

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class VaultSafeErrorHandler {

    @ExceptionHandler(RequiredSecretUnavailableException.class)
    public ProblemDetail onSecretUnavailable(
            RequiredSecretUnavailableException ignored) {

        ProblemDetail response =
                ProblemDetail.forStatus(HttpStatus.SERVICE_UNAVAILABLE);
        response.setTitle("Temporarily unavailable");
        response.setDetail("The requested operation is not available");
        return response;
    }
}
~~~

Ví dụ chỉ trả thông tin vận hành chung; không mang Vault path, token, raw cause hoặc body. Mã lỗi chi tiết hơn cần được giữ trong telemetry nội bộ bằng enum/status và correlation ID độc lập. Một lỗi cấu hình 403 cần được điều tra khác lỗi timeout; không được retry vô hạn chỉ vì response công khai đều là 503.

Khi cần che lỗi cho người dùng, **đừng đính kèm exception gốc vào exception public** rồi để global handler in full stack/`getMessage()`. Có thể giữ metadata an toàn ở một telemetry sink được bảo vệ để chẩn đoán mà không copy payload.

## 8. Ví dụ Spring Vault: KV v2 + log lỗi an toàn + Micrometer

Dịch vụ sau đọc KV v2 theo đường dẫn cố định, kiểm tra cấu trúc trước khi sử dụng, chỉ log tên operation và mã lỗi đã phân loại. Thời gian gọi được đo bằng Micrometer, gắn nhãn có giá trị hữu hạn. Giả định Java 17+, Spring Vault, Spring Web và Micrometer đã được cấu hình; HTTP client dùng TLS và workload auth hợp lệ.

~~~java
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

public final class SafePaymentSecretService {

    private static final Logger log =
            LoggerFactory.getLogger(SafePaymentSecretService.class);

    private static final String PATH =
            "secret/data/orders/payment";
    private static final String OPERATION = "kv_read_payment";

    private final VaultOperations vault;
    private final MeterRegistry metrics;

    public SafePaymentSecretService(
            VaultOperations vault,
            MeterRegistry metrics) {
        this.vault = Objects.requireNonNull(vault);
        this.metrics = Objects.requireNonNull(metrics);
    }

    public PaymentCredential load() {
        long started = System.nanoTime();
        String outcome = "failure";

        try {
            VaultResponse response = vault.read(PATH);

            if (response == null || response.getData() == null) {
                throw new IllegalStateException(
                        "Required KV value not found");
            }

            // Với KV v2, response.getData() chứa data + metadata;
            // bên trong "data" mới là map giá trị nghiệp vụ.
            Object nested = response.getData().get("data");
            if (!(nested instanceof Map<?, ?> values)) {
                throw new IllegalStateException(
                        "Invalid KV v2 response schema");
            }

            Object rawKey = values.get("apiKey");
            if (!(rawKey instanceof String apiKey)
                    || apiKey.isBlank()) {
                throw new IllegalStateException(
                        "Required KV field missing");
            }

            long kvVersion = -1L;
            Object metadata = response.getData().get("metadata");
            if (metadata instanceof Map<?, ?> meta) {
                Object version = meta.get("version");
                if (version instanceof Number number) {
                    kvVersion = number.longValue();
                }
            }

            outcome = "success";
            return new PaymentCredential(apiKey, kvVersion);

        } catch (RuntimeException failure) {
            VaultFailureClassifier.Category category =
                    VaultFailureClassifier.classify(failure);

            // Chỉ ghi enum và operation cố định.
            log.warn(
                    "vault_secret_fetch_failed operation={} category={}",
                    OPERATION, category);

            // Không nối raw exception vào message/cause công khai.
            throw new RequiredSecretUnavailableException();

        } finally {
            Timer.builder("vault.client.operation.duration")
                    .tag("operation", OPERATION)
                    .tag("outcome", outcome)
                    .register(metrics)
                    .record(System.nanoTime() - started,
                            TimeUnit.NANOSECONDS);
        }
    }
}
~~~

Trong ví dụ:

- `PATH` cố định và policy Vault cấp `read` trên `secret/data/orders/payment`, không tự ghép path từ input người dùng.
- `PaymentCredential` có `toString()` đã che. Không log `apiKey`, raw `VaultResponse` hay nested map.
- Exception chỉ được dùng nội bộ để tạo **category**; logger không nhận exception parameter.
- Metrics chỉ có `operation` và `outcome` hằng số, không có tenant/path/secret.
- `kvVersion` dùng để theo dõi bản KV nếu được duyệt; không dùng hash hoặc tiền tố API key làm ID.
- Ví dụ không tự gia hạn token, lease hay cache. Các vòng đời đó thuộc `SessionManager`/`SecretLeaseContainer` hoặc kiến trúc quản lý riêng.

Đây là mã minh họa cách **logging an toàn**. Ở production, cần phân biệt lỗi cấu hình (403/schema sai) và lỗi tạm thời (timeout/5xx) ở lớp điều phối, định nghĩa retry deadline theo loại operation. **Không gắn retry toàn cục lên mọi `VaultOperations`** vì `pki/issue`, `database/creds` hoặc cấp SecretID có thể tạo secret mới sau mỗi lần gọi.

## 9. Tracing, APM và metrics: quan sát mà không giữ secret

### 9.1. Metrics và cardinality

| Chỉ số | Nhãn phù hợp | Không ghi |
| --- | --- | --- |
| `vault.client.operation.duration` | `operation`, `outcome` | Secret path/tenant ID tùy ý |
| `vault.client.error.total` | `operation`, `failure_category` | Raw exception message |
| `vault.client.retry.total` | `operation`, `retry_reason` đã phân loại | Headers/body |
| `vault.client.cache.hit` | `secret_category`, `result` | Cache key thực chứa tenant hoặc secret |
| `vault.token.remaining_seconds` | `auth_method` đã allowlist | Session token value |
| `vault.lease.remaining_seconds` | `secret_engine` đã allowlist | Lease ID, database password |
| `vault.pki.certificate_expiry` | `service_role` được phê duyệt | PEM hoặc private key |
| `vault.transit.duration` | `operation=encrypt/decrypt/rewrap` | Plaintext/ciphertext/context |

Tag là định danh tạo ra các time series. Gắn tenant ID, URL đầy đủ hoặc error message làm tag vừa **rò rỉ thông tin**, vừa làm tăng số series không kiểm soát, gây chi phí bộ nhớ/index và latency của hệ thống metrics.

### 9.2. Span/trace không an toàn theo mặc định trong mọi cấu hình

Có thể ghi span:

~~~json
{
  "name": "vault.kv.read",
  "attributes": {
    "vault.operation": "kv_read",
    "vault.engine": "kv_v2",
    "vault.outcome": "success",
    "http.response.status_code": 200
  }
}
~~~

Không gắn `http.request.body`, `http.response.body`, `http.request.header.x-vault-token`, `vault.secret.value`, `exception.message` hoặc `X-Vault-Wrap-TTL` kèm dữ liệu khác không cần thiết. HTTP auto-instrumentation của OpenTelemetry/APM có thể phát thuộc tính bổ sung; phải xem **payload xuất ra collector test thực sự**.

Không đặt token/secret trong `MDC`, W3C baggage, trace state hoặc correlation ID: các giá trị đó có thể được lan truyền sang dịch vụ khác, được agent thu thập hoặc ghi ở nhiều chỗ. Server nên tạo correlation ID độc lập và xác minh định dạng trước khi ghi.

### 9.3. Quan sát token và lease bằng metadata

Ứng dụng cần biết token còn TTL bao lâu, renew/re-login có thành công không; dynamic credentials còn lease bao lâu; certificate PKI gần `notAfter` chưa; Transit latency và lỗi permission ra sao. Các chỉ số có thể đo **thời gian, trạng thái, loại secret engine và kết quả**, không cần ghi token, secret, private key hay lease identifier thô.

Nếu cần liên kết một sự cố với Vault audit log, dùng timestamp, operation, correlation/request ID hợp lệ và hệ thống audit có phân quyền, không chép response body vào log chung.

## 10. Vault audit log không đồng nghĩa với application log

Vault có audit devices để ghi dấu vết request/response. Nhiều trường nhạy cảm trong audit records được Vault xử lý bằng HMAC với salt của audit device theo cấu hình mặc định, nhưng chi tiết và ngoại lệ phụ thuộc API, loại field, phiên bản và cấu hình audit.

| Nguồn | Mục đích | Chính sách |
| --- | --- | --- |
| **Vault audit device** | Kiểm toán truy cập Vault | Quản trị/bảo vệ sink audit, quyền xem, retention và cấu hình HMAC |
| **Spring application logs** | Sự kiện nghiệp vụ, latency, lỗi ứng dụng | Chỉ metadata allowlist, không raw body/object |
| **HTTP wire logs** | Debug byte-level của transport | Không bật cho secret traffic ở production |
| **Proxy/ingress logs** | Routing, status, latency | Tắt capture body và header credential |
| **APM/tracing** | Quan sát end-to-end, failure/latency | Sanitization, sampling, không đưa secret vào attributes |

Audit log của Vault **không bảo vệ** `log.info("{}", vaultResponse)` trong Java, không che proxy log và không tự lọc dashboard APM. Nếu cần điều tra sâu, dùng bản ghi audit được phân quyền thay vì tăng logging body trên ứng dụng.

## 11. Logging quá nhiều gây suy giảm hiệu năng

Giả sử 100 pod, mỗi pod thực hiện 50 calls Vault/giây: tổng khoảng **5.000 calls/giây**. Nếu mỗi call tạo 1 KB log body, chỉ body đã xấp xỉ **5 MB/giây**, chưa kể JSON, indices, network và backup. Ngoài lộ bí mật, overhead gồm:

- Chuyển byte/JSON thành String, tăng phân bổ heap và GC.
- Buffer response và nhân bản plaintext/ciphertext/private key trong memory.
- Ghi I/O đồng bộ vào file/network, làm tăng p95/p99 latency.
- Log pipeline có thể nghẽn, tạo queue/backpressure hoặc mất sự kiện quan trọng.
- Metrics có tag tenant/path động gây nổ cardinality.

Cấu hình phù hợp hơn:

1. Đo tất cả call bằng Timer/Counter nhẹ với tag hữu hạn.
2. Lấy mẫu traces và chỉ ghi metadata đã sanitize.
3. Log WARN cho lỗi quan trọng, áp dụng **throttling** khi lỗi lặp lại; dùng counter theo category để không mất tín hiệu.
4. Không in mỗi KV/Transit read thành một dòng INFO trên đường xử lý nóng.
5. Nếu dùng async logger, đặt bounded queue và chính sách khi đầy; tuyệt đối không đưa body/exception raw vào fallback logs.
6. Bảo vệ quyền xem và thời gian lưu log, dashboard, traces, artifacts sao cho tương ứng độ nhạy cảm.

Mục tiêu là đủ tín hiệu để chẩn đoán, không tăng chi phí và không tạo thêm bản sao secret.

## 12. Những kênh rò rỉ dễ bị quên

Không chỉ `LoggerFactory` mới có thể xuất bí mật. Kiểm tra thêm:

- Spring Boot Actuator `/env`, `/configprops`, `/heapdump` và các endpoint chẩn đoán: hạn chế exposure/quyền truy cập; không chỉ dựa vào cấu hình che mặc định.
- Exception monitoring (Sentry/APM hoặc dịch vụ khác): request headers/body, breadcrumbs và exception message có thể tự gửi.
- Thread/heap dumps: object chứa String token/API key có thể xuất hiện trong artifact.
- Cấu hình CI/CD: shell `set -x`, `curl -v`, lệnh với token trong argument, output test và biến môi trường bị dump.
- Message broker/queue: object secret có thể bị producer/consumer log hoặc dead-letter queue ghi nguyên văn.
- HTTP proxy, ingress, service mesh: có thể xem plaintext sau TLS termination và capture headers.
- Unit/integration test failures: assertions in raw body, snapshot JSON hoặc test report lưu sentinel thật.
- AOP/filter ghi method arguments hoặc return values: có thể vô tình log `VaultToken`, `VaultResponse`, DTO chứa `secret_id`.

Một cấu hình `logging.level.root=INFO` chưa chứng minh mọi tầng trên đã an toàn. Phải kiểm tra từng sink thực sự được triển khai, đặc biệt khi bật chế độ debug tạm thời trong incident.

## 13. Kiểm thử không rò rỉ bằng sentinel

Dùng Vault test/dev cô lập và **giá trị giả có dấu nhận biết**:

~~~text
TEST_ONLY_VAULT_SECRET_DO_NOT_LOG_2026
TEST_ONLY_PRIVATE_KEY_MARKER
TEST_ONLY_WRAPPING_TOKEN_MARKER
~~~

Các chuỗi là placeholder, không phải credential production. Chèn vào KV v2 test và phản hồi giả của những API liên quan; thu log từ appender, stdout/stderr, HTTP client, proxy, trace exporter và error response.

| Test case | Input tạo tình huống | Kỳ vọng |
| --- | --- | --- |
| KV v2 đọc thành công | `data.data.apiKey` chứa sentinel | Không xuất sentinel vào log/trace/API response |
| HTTP request chứa token | `X-Vault-Token` test | Header value không xuất hiện trong bất kỳ sink nào |
| HTTP response PKI | `private_key` test | Không có PEM/private key trong logging |
| Transit encrypt/decrypt | Plaintext dạng Base64 | Không có plaintext hoặc Base64 của nó |
| Wrapping | `wrap_info.token` test | Không in token vào log, URL, error |
| Object logging | `PaymentCredential.toString()` | Chỉ `REDACTED` và metadata đã duyệt |
| Lỗi HTTP 403 | Exception message chứa sentinel | Chỉ category/status an toàn |
| Lỗi parser KV | Nested Map chứa sentinel và thiếu field | Không dump Map hoặc JSON bị lỗi |
| Lỗi network/TLS | Cause chứa URL và path | Không log raw message/cause |
| Spring debug logs | Nâng log level trong môi trường test | Không xuất raw body/headers |
| Field mới | Thêm `credentials.api_token` vào response | Allowlist không tự ghi field mới |
| Metrics/tracing | Nhiều tenant/request | Không có secret/tenant ID tự do trong tags |

Có thể dùng JUnit cùng test appender để kiểm tra:

~~~java
// Pseudocode: collectedLogs và exportedTraceJson do test setup cung cấp.
String marker = "TEST_ONLY_VAULT_SECRET_DO_NOT_LOG_2026";

assertFalse(collectedLogs.contains(marker));
assertFalse(exportedTraceJson.contains(marker));
assertFalse(errorResponseBody.contains(marker));
assertTrue(collectedLogs.contains("kv_read_payment"));
~~~

Cần kiểm tra **cả biểu diễn Base64** của sentinel vì một số HTTP API Vault dùng Base64 cho plaintext. Không dùng secret thật trong test. Việc `PaymentCredential.toString()` đã redacted **chưa đủ** để kết luận an toàn nếu một HTTP interceptor hoặc error handler khác vẫn ghi payload.

### 13.1. Những mẫu code cần review

~~~text
log.*(vaultResponse)
log.*(response.getData())
log.*(request.getHeaders())
log.*(exception.getMessage())
log.error("...", exception)
ObjectMapper.writeValueAsString(secretObject)
@Data / @ToString / record chứa password, apiKey, token
HTTP wire logging / body capture / network debug
MDC.put("token", ...) / span.setAttribute("secret", ...)
~~~

Danh sách này là tín hiệu để review, **không phải regex kiểm thử đầy đủ**; dependency hoặc APM agent có thể tạo log mà không có dòng code tương ứng trong repository.

## 14. Khi phát hiện đã lộ secret qua log

1. **Ngăn phát sinh thêm**: tắt đường logging gây lộ ở app, HTTP client, proxy hoặc APM.
2. **Xác định loại secret** và khoảng thời gian xuất hiện; không lặp lại secret trong incident message.
3. **Đánh giá phạm vi bản sao**: log platform, dashboards, backups, traces, CI artifacts, tickets và người đã truy cập.
4. **Revoke/rotate**: Vault token/SecretID, wrapping token, API key, dynamic credential, certificate/private key PKI theo loại dữ liệu bị lộ.
5. **Xử lý retention/bản sao** theo quy trình tổ chức; việc xóa một log entry trên dashboard chưa chắc xóa các bản sao ở backup/collector.
6. **Thêm regression test sentinel**, review chỗ ghi object/exception và giám sát sau sửa.
7. **Ghi báo cáo bằng metadata an toàn**, không chép body hay credential vào báo cáo sự cố.

Đối với certificate đã lộ private key, thường cần cấp mới cặp khóa/chứng thư và thu hồi chứng thư cũ theo chính sách PKI; chỉ đổi tên file hoặc cập nhật secret path không vô hiệu khóa bị lộ.

## 15. Checklist triển khai

- [ ] Client Spring Vault dùng HTTPS, CA tin cậy, workload authentication và policy tối thiểu.
- [ ] Không log `X-Vault-Token`, Authorization, SecretID, wrapping token, API key, private key hoặc plaintext Transit.
- [ ] HTTP interceptor chỉ ghi method/status/duration; không đọc/serialize headers, URI nhạy cảm hoặc body.
- [ ] Đã rà soát wire logging thực tế của HTTP stack, proxy, service mesh và APM.
- [ ] Không log raw `VaultResponse`, nested Map, `CertificateBundle`, Token DTO hoặc serialization của chúng.
- [ ] Các object chứa secret có `toString()` đã che hoặc không được đưa vào logger; Lombok/record được review.
- [ ] Không đưa `exception.getMessage()`, raw cause hoặc HTTP error body vào logs/API response.
- [ ] Lỗi được phân loại bằng enum/status; UNKNOWN được giữ khi không có bằng chứng.
- [ ] Micrometer/trace chỉ dùng operation và outcome hữu hạn; không tag tenant/path/secret.
- [ ] Correlation ID được sinh/validate an toàn; không đưa credential vào MDC/baggage.
- [ ] Readiness, token/lease/PKI expiry được quan sát bằng metadata, không bằng giá trị bí mật.
- [ ] Logging có sampling/throttling phù hợp để không làm tăng p95/p99 và chi phí lưu trữ.
- [ ] Vault audit được quản trị riêng; không nhầm HMAC audit với redaction ở ứng dụng.
- [ ] Actuator, heap dumps, error monitoring, test artifacts và CI logs được kiểm soát quyền/retention.
- [ ] Đã chạy test sentinel cho success, 403, parser error, timeout, Transit, PKI và wrapping.
- [ ] Có runbook khi secret xuất hiện trong log: chặn, revoke/rotate, điều tra sink và ngăn tái diễn.

## Tài liệu tham khảo

- Spring Vault, [Reference documentation](https://docs.spring.io/spring-vault/reference/) và [VaultOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html) — client Java và dữ liệu phản hồi Vault.
- Spring Vault, [VaultTemplate API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html) — implementation đồng bộ.
- Spring Framework, [ClientHttpRequestInterceptor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/ClientHttpRequestInterceptor.html) — can thiệp HTTP client.
- Spring Framework, [RestClientResponseException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/client/RestClientResponseException.html) — HTTP status và response body trong lỗi.
- Spring Boot, [Logging](https://docs.spring.io/spring-boot/reference/features/logging.html) và [Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — logging configuration và exposure.
- Micrometer, [Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html) — đo latency và metric tags.
- HashiCorp Vault, [Audit devices](https://developer.hashicorp.com/vault/docs/audit) — bảo vệ audit log và HMAC.
- HashiCorp Vault, [Response Wrapping](https://developer.hashicorp.com/vault/docs/concepts/response-wrapping), [Transit](https://developer.hashicorp.com/vault/docs/secrets/transit) và [PKI](https://developer.hashicorp.com/vault/docs/secrets/pki) — các payload nhạy cảm cần bảo vệ.
