# Tương quan log ứng dụng với request ID và audit của Vault

## 1. Mục tiêu: truy vết một lời gọi Vault từ Java đến audit log

Trong module **SPRING_VAULT**, ứng dụng Java gọi HashiCorp Vault qua `VaultTemplate` hoặc `VaultOperations` để đọc KV secrets, tạo database credentials, mã hóa bằng Transit, lấy chứng thư PKI hoặc gia hạn token và lease. Khi một lời gọi thất bại, log Spring Boot có thể chỉ ghi `VaultException` hoặc HTTP 403. Người vận hành vẫn cần trả lời những câu hỏi cụ thể:

- Request nghiệp vụ nào trong `orders-api` dẫn tới lời gọi Vault?
- Vault đã nhận request nào, ở mount, namespace và đường dẫn nào?
- Request có bị từ chối vì ACL, token hết hạn, sai KV v2 path hay do lỗi engine?
- Một request Java đã phát sinh bao nhiêu lời gọi Vault, kể cả đăng nhập lại và gia hạn lease?
- Có thể đối chiếu bằng chứng giữa log ứng dụng và audit của Vault **mà không ghi token hoặc secret vào log** không?

Giải pháp là kết nối các định danh có vai trò khác nhau: **application correlation ID**, **trace ID** (nếu dùng distributed tracing) và **Vault request ID**. Đặc biệt, Vault sinh định danh riêng cho mỗi API request; định danh đó giúp đối chiếu response ở phía ứng dụng với các entry `request` / `response` trong Vault audit.

Bài này hướng dẫn tổ chức log, lấy request ID trong Spring Vault, truy vấn audit JSON và thiết kế kiểm thử tích hợp. Mục tiêu là **quan sát được nguyên nhân sự cố và độ trễ** trong khi vẫn giữ chính sách phân quyền và bảo vệ dữ liệu nhạy cảm.

## 2. Ba định danh khác nhau và phạm vi của chúng

| Định danh | Ai tạo? | Phạm vi | Dùng để làm gì? |
|---|---|---|---|
| `app_request_id` / correlation ID | API gateway, ứng dụng hoặc công cụ tracing đã được tin cậy | Một lần xử lý yêu cầu nghiệp vụ | Nhóm các dòng log cùng một HTTP request / message |
| `trace_id` (OpenTelemetry/Micrometer Tracing) | Hệ thống distributed tracing | Một distributed trace qua nhiều service/span | Liên kết lời gọi REST, JDBC, Vault client và service khác nếu đã instrument |
| `vault_request_id` | **Vault server** cho mỗi API request | Một lời gọi API Vault cụ thể | Ghép log Java với audit entry có `request.id` tương ứng |

Giả sử một request HTTP `GET /orders/123` khiến ứng dụng phải đọc secret và thực hiện Transit encryption. Ta có thể gặp:

~~~text
app_request_id = 8fbb9e31-6d3b-4411-82e3-0871454f2464

Java -> Vault GET  secret/data/apps/orders/config
        vault_request_id = 22a8124e-e47f-4fc9-9964-c5623dd66357

Java -> Vault POST transit/encrypt/orders-key
        vault_request_id = 6ba42291-5d46-4a4a-883b-60d79b984833
~~~

Hai Vault request IDs ở trên chỉ là **UUID minh họa**. Cả hai có thể thuộc cùng `app_request_id` và cùng `trace_id`, nhưng **không** được mong đợi có cùng Vault request ID.

**Không tự gán Vault request ID bằng cách gửi application correlation ID trong một HTTP header tùy ý.** Vault sinh request ID và trả về theo giao thức của nó. Nếu bạn gắn `X-Request-ID` hay `traceparent` vào HTTP request, các header đó không mặc nhiên thay thế trường `request.id` của Vault audit.

Lời gọi đăng nhập workload (Kubernetes auth/AppRole), token renewal, lease renewal và SecretLeaseContainer rotation cũng có thể tạo **những Vault request IDs riêng** ngoài phạm vi request nghiệp vụ đang được xử lý.

## 3. Ba nguồn log cần phân biệt

| Nguồn | Được sinh ở đâu? | Nội dung hữu ích | Giới hạn |
|---|---|---|---|
| Log ứng dụng Spring Boot | JVM / logging backend của dịch vụ | `app_request_id`, `trace_id`, operation, path template, `vault_request_id` khi có, kết quả, thời gian | Không chứng minh request thực sự được Vault xử lý nếu chỉ ghi “sắp gửi” |
| Vault **audit log** | Audit device đã bật trên Vault cluster | Entry `request`/`response`, `request.id`, operation, path, namespace, auth metadata, error | Có thể HMAC dữ liệu; chỉ đầy đủ với các sự kiện thực sự được audit và audit devices hoạt động |
| Vault **operational log** và telemetry | Vault server / metrics endpoint | Trạng thái server, leader, storage, plugin, latency, số lỗi hệ thống | Không thay audit log để truy vết quyền của một request cụ thể |

Một sự kiện `permission denied` có thể xuất hiện ở cả ba nơi nhưng mang ý nghĩa khác nhau:

- Ứng dụng ghi nhận ngoại lệ khi gọi một path.
- Vault audit có thể cho biết operation/path/namespace/auth context cùng trường `error` hoặc kết quả policy.
- Operational log cho biết có lỗi server, seal, storage, plugin hoặc proxy gần cùng thời điểm hay không.

Đừng nhầm access log của reverse proxy với Vault audit. Proxy có thể ghi status code và HTTP route, nhưng không thay thế kiểm tra policy hoặc dữ liệu audit do Vault sinh.

## 4. Luồng tương quan từ request nghiệp vụ tới audit

~~~mermaid
sequenceDiagram
    participant U as Client / API gateway
    participant J as Spring Boot service
    participant V as HashiCorp Vault
    participant A as Vault audit device
    participant L as Hệ thống tập trung log

    U->>J: HTTP request (app_request_id, trace context)
    J->>J: Đặt MDC / trace context
    J->>V: Vault API request (token workload)
    V->>A: Audit entry type=request, request.id=V123
    V->>V: Xác thực, ACL và secrets engine
    V->>A: Audit entry type=response, request.id=V123
    V-->>J: HTTP response (request_id=V123 nếu có)
    J->>L: App log: app_request_id, vault_request_id=V123
    A->>L: Audit request/response với request.id=V123
    L->>L: Join vault_request_id = request.id
    J-->>U: Phản hồi nghiệp vụ
~~~

Trong ứng dụng có distributed tracing, `trace_id` giúp định vị luồng giữa các service; `vault_request_id` là **chìa khóa đối chiếu chính xác nhất** khi đã biết Vault xử lý request nào.

Nếu ứng dụng thất bại do DNS, TLS handshake hoặc timeout **trước khi Vault nhận request**, có thể **không có audit entry**. Ngược lại, nếu Vault đã xử lý nhưng response bị mất trên đường về, audit có thể tồn tại trong khi Java chưa nhận được `request_id`. Do đó, việc không tìm thấy ID ở Java **không tự chứng minh** Vault không nhận request.

## 5. Cấu trúc audit log và trường dùng để ghép

Audit log của Vault thường là các dòng JSON độc lập (JSON Lines). Mỗi request/response được log thành entry phù hợp cấu hình audit và hành vi cụ thể của server.

Các trường quan trọng:

| Audit JSON path | Ý nghĩa | Cách dùng |
|---|---|---|
| `type` | `request` hoặc `response` | Phân biệt hai pha của cùng lần gọi |
| `request.id` | ID Vault tạo cho request | **Join chính** với `vault_request_id` từ Java |
| `request.operation` | `read`, `update`, `create`, `delete`, `list`... | Phân loại loại thao tác mà Vault thực hiện |
| `request.path` | API path mà Vault xử lý | Tìm đúng mount và endpoint, ví dụ `kv/data/...` |
| `request.namespace` | Namespace / ID nếu có | Phân biệt những nơi có mount/path trùng tên |
| `request.mount_type` và `request.mount_accessor` | Metadata mount nếu được ghi | Xác định engine hoặc auth mount |
| `auth` / `request.policy_results` | Context xác thực/quyền nếu có | Chẩn đoán ACL; không phải mọi request đều có đủ trường |
| `error` | Lý do lỗi khi có | Hỗ trợ phân biệt denied, invalid request và backend error |
| `time` | Thời gian ghi entry | Ghép với mốc từ ứng dụng, đánh giá timeline |
| `response` | Metadata phản hồi cho entry response | Phân tích kết quả khi có, lưu ý HMAC |

**Trường cần tra trong audit là `request.id`**, kể cả khi `type=response`. Không phụ thuộc vào giả định rằng response audit luôn chứa trường top-level `request_id`.

Ví dụ hai entry đã lược bớt trường và thay giá trị nhạy cảm bằng placeholder:

~~~json
{"type":"request","time":"2026-11-25T10:30:00.100Z","request":{"id":"22a8124e-e47f-4fc9-9964-c5623dd66357","operation":"read","path":"kv/data/apps/orders/config","namespace":{"id":"root"}},"auth":{"policies":["orders-reader"]}}
{"type":"response","time":"2026-11-25T10:30:00.113Z","request":{"id":"22a8124e-e47f-4fc9-9964-c5623dd66357","operation":"read","path":"kv/data/apps/orders/config","namespace":{"id":"root"}},"response":{"data":{"data":{"api_key":"hmac-sha256:<redacted>"}}}}
~~~

Các giá trị trong ví dụ không phải audit log thực và **không phải một schema đầy đủ**. Nội dung xuất hiện ở từng entry phụ thuộc loại request, phiên bản Vault, loại audit device, các ngoại lệ HMAC và bộ lọc audit.

Đối với các audit devices khác nhau, Vault dùng khóa HMAC riêng theo device; **cùng một giá trị bí mật có thể ra chuỗi HMAC khác nhau**. Hãy dùng `request.id` để ghép request/response; không cố ghép hai device bằng hash token hoặc hash dữ liệu nếu không biết ngữ cảnh.

## 6. Bật và bảo vệ audit device

Audit device thuộc trách nhiệm **Vault operator**, không thuộc token runtime của Java service. Trong môi trường thử nghiệm, người vận hành có thể bật:

~~~bash
# Chỉ chạy trên Vault test/staging bằng token có quyền operator.
vault audit enable -path=application-audit file \
  file_path=/var/log/vault/application-audit.log

vault audit list -detailed
~~~

Đường dẫn file ở đây là ví dụ trên máy chạy Vault, cần được tạo/cấu hình với quyền hệ điều hành, volume và log rotation phù hợp. Không tự động chạy lệnh bật audit trong `@PostConstruct` hoặc mỗi lần Spring Boot khởi động.

Vault khuyến nghị **ít nhất hai audit devices** phù hợp yêu cầu vận hành và lưu trữ tập trung. Vault phải ghi audit request thành công tới ít nhất một device để phục vụ request; sự cố audit sink có thể ảnh hưởng khả năng phục vụ của Vault. Khi một cluster có nhiều devices, cần hiểu cách thu thập để không bỏ sót; cùng request ID có thể xuất hiện lặp lại giữa các devices.

Kiểm soát audit log:

- Chỉ cấp quyền đọc cho nhóm vận hành và điều tra được ủy quyền.
- Giữ log trên volume phân quyền rõ, truyền qua TLS tới hệ thống tập trung, đặt retention theo quy định.
- Kiểm tra audit sink có tạo/ghi file được sau thay đổi cấu hình và khi đầy đĩa.
- Không bật `log_raw=true` trong production chỉ để xem giá trị secret.
- Hạn chế các tùy chọn bỏ HMAC như `audit_non_hmac_request_keys` và `audit_non_hmac_response_keys`; chỉ sử dụng theo đánh giá bảo mật cụ thể.
- Nếu dùng audit filters, nắm rõ những request nào có thể **không có trong log**; đừng dùng bộ lọc làm bằng chứng rằng request chưa xảy ra.

Vault che phần lớn **giá trị chuỗi** trong audit bằng HMAC-SHA256 theo mặc định. Không được xem toàn bộ audit log là an toàn tuyệt đối: đường dẫn, operation, số, Boolean, metadata và các trường được miễn HMAC vẫn có thể chứa thông tin nhạy cảm. Đừng ghi token hay plaintext bí mật vào audit fields tùy biến.

## 7. Lấy Vault request ID từ Spring Vault khi có response

Spring Vault cung cấp `VaultResponse` / `VaultResponseSupport`. Đối với những lời gọi đọc trả về một `VaultResponse` tiêu chuẩn, có thể truy cập **`getRequestId()`** để lấy trường `request_id` trong payload JSON của Vault.

Ví dụ service đọc một secret KV v2. Mã cố tình **chỉ log metadata**, không log `response.getData()` hoặc nội dung secret:

~~~java
import java.util.Objects;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Service;
import org.springframework.vault.VaultException;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public final class OrdersVaultReader {

    private static final Logger log =
            LoggerFactory.getLogger(OrdersVaultReader.class);

    private static final String PATH_TEMPLATE =
            "kv/data/apps/orders/{orderId}";

    private final VaultOperations vault;

    public OrdersVaultReader(VaultOperations vault) {
        this.vault = Objects.requireNonNull(vault);
    }

    public VaultResponse readById(String orderId) {
        if (orderId == null || !orderId.matches("[A-Za-z0-9-]{1,64}")) {
            throw new IllegalArgumentException("Invalid order ID");
        }

        String path = "kv/data/apps/orders/" + orderId;
        long startedAt = System.nanoTime();

        try {
            VaultResponse result = vault.read(path);
            String requestId =
                    result == null ? null : result.getRequestId();

            log.info(
                "vault_call operation=read path_template={} " +
                "vault_request_id={} outcome={} duration_ms={}",
                PATH_TEMPLATE,
                requestId,
                result == null ? "not_found" : "success",
                (System.nanoTime() - startedAt) / 1_000_000
            );
            return result;
        } catch (VaultException exception) {
            log.warn(
                "vault_call operation=read path_template={} " +
                "vault_request_id=unavailable outcome=error " +
                "error_type={} duration_ms={}",
                PATH_TEMPLATE,
                exception.getClass().getSimpleName(),
                (System.nanoTime() - startedAt) / 1_000_000
            );
            throw exception;
        }
    }
}
~~~

Ý nghĩa:

1. `VaultOperations.read(...)` thực hiện API GET với danh tính/token của Vault client đang cấu hình. Ví dụ dùng **API path thực `kv/data/...`** vì gọi `read` trực tiếp, không qua `opsForKeyValue(..., KV_2)`.
2. `result.getRequestId()` lấy Vault ID từ response khi có. Đây là ID của **một lần gọi**; không thay bằng correlation ID của ứng dụng.
3. `path_template` giúp log thao tác có cấu trúc mà không ghi tên thực của mọi secret key. Với dữ liệu không nhạy cảm có thể log path cụ thể khi chính sách bảo mật cho phép.
4. Khi `read` trả `null` (ví dụ secret không tồn tại tùy phiên bản/client) hoặc ném `VaultException`, code trên có thể không lấy được `request_id`. Phải chẩn đoán lỗi qua HTTP client/audit một cách phù hợp.
5. Không ghi `exception.getMessage()` hoặc toàn bộ exception theo mặc định trong logging lớp bảo mật. Thông điệp và stack trace có thể mang URL, metadata hoặc nội dung nhạy cảm tùy client/custom interceptor; cần quy tắc lọc trước khi ghi.
6. `VaultResponse` bản thân có thể chứa bí mật. Đừng log `result`, `result.getData()`, `toString()` hoặc payload HTTP.

Đây là code minh họa cho một `VaultOperations` đã được cấu hình hợp lệ. Phần chọn session manager, xác thực Kubernetes/AppRole, timeout và TLS nằm ở cấu hình Spring Vault của ứng dụng.

### Khi dùng API chuyên biệt

`VaultTemplate.opsForKeyValue(...)`, `opsForTransit()` và `opsForPki()` trả abstraction chuyên biệt; các phương thức có thể trả object khác `VaultResponse` hoặc đã bóc tách dữ liệu. Đừng giả định mọi kết quả đều cung cấp `getRequestId()`. Nếu cần một request ID cho các API chuyên biệt, có thể:

- Chọn một API trả `VaultResponse` khi phù hợp nghiệp vụ và quy tắc an toàn.
- Instrument HTTP transport/response một lần ở tầng client để thu thập **chỉ metadata có thể xác minh**, có kiểm soát response body và error handling.
- Với request lỗi không trả ID, dùng audit join theo thời gian/namespace/path và request metadata đã lọc; không tự bịa ID.

Không viết một interceptor đọc hết body response rồi bỏ đi: nó có thể làm deserializer của Spring Vault không còn dữ liệu, đồng thời tăng rủi ro lộ secret khi buffer/log raw payload.

## 8. Thêm application correlation ID vào MDC một cách an toàn

Trong Spring MVC, có thể tạo `app_request_id` ở ranh giới HTTP và đặt trong SLF4J MDC. Ví dụ dùng UUID do ứng dụng tạo để tránh đặt dữ liệu header từ client không tin cậy vào log:

~~~java
import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class ApplicationCorrelationFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String correlationId = UUID.randomUUID().toString();
        MDC.put("app_request_id", correlationId);
        try {
            response.setHeader("X-Application-Request-ID", correlationId);
            chain.doFilter(request, response);
        } finally {
            MDC.remove("app_request_id");
        }
    }
}
~~~

Nếu API gateway đã phát một correlation ID đáng tin cậy, ứng dụng có thể nhận ID đó **sau khi kiểm tra định dạng/độ dài và mô hình trust**, thay vì tạo ID khác. Không đưa trực tiếp `X-Request-ID` tùy ý của khách hàng vào MDC vì có nguy cơ log injection, độ dài quá mức hoặc giả mạo để đánh lạc hướng điều tra.

Cấu hình pattern logging cần bao gồm MDC key tương ứng, ví dụ:

~~~yaml
logging:
  pattern:
    level: "%5p [app_request_id=%X{app_request_id:-}]"
~~~

Với JSON structured logging, nên có field riêng `app_request_id`, `trace_id`, `vault_request_id`. Đây là schema do ứng dụng định nghĩa, không phải tên field tiêu chuẩn bắt buộc của Spring Vault.

Nếu đã dùng **Micrometer Tracing/OpenTelemetry**, hệ thống có thể thêm `traceId`/`spanId` vào MDC hoặc log encoder; hãy xác minh cách cấu hình thực tế. Không tạo ngẫu nhiên một trace ID khác rồi gán nhãn là trace có thực.

**Lưu ý asynchronous execution:** MDC thường gắn với thread. `@Async`, scheduler, message listener và reactive pipeline có thể chuyển luồng thực thi. Cần context propagation phù hợp, và xóa MDC trong `finally` hoặc cơ chế tương đương để tránh trộn định danh giữa các request. Không giả định filter của Spring MVC sẽ tự bao phủ token renewal background.

## 9. Một mẫu structured log có thể truy vấn được

Ví dụ bản ghi của `orders-api` (mọi giá trị là minh họa):

~~~json
{
  "timestamp": "2026-11-25T10:30:00.116Z",
  "level": "INFO",
  "service": "orders-api",
  "environment": "staging",
  "app_request_id": "8fbb9e31-6d3b-4411-82e3-0871454f2464",
  "trace_id": "e6758c9f632fc1177b07a9d04ae0b0ed",
  "event": "vault_call",
  "operation": "read",
  "engine": "kv",
  "path_template": "kv/data/apps/orders/{orderId}",
  "vault_request_id": "22a8124e-e47f-4fc9-9964-c5623dd66357",
  "outcome": "success",
  "duration_ms": 16
}
~~~

Đề xuất log khi **mỗi lời gọi Vault đã hoàn tất**:

| Field | Nên ghi? | Giải thích |
|---|---|---|
| `event=vault_call` | Có | Lọc log dễ dàng |
| `app_request_id` | Có, nếu đã tạo | Liên kết với request nghiệp vụ |
| `trace_id`, `span_id` | Có, khi tracing đang hoạt động | Liên kết với distributed trace |
| `vault_request_id` | Có khi response có ID | Join chính sang Vault audit |
| `operation`, `engine` | Có | Phân nhóm read/write/encrypt/decrypt/issue/renew |
| `path_template` | Có nếu đã kiểm tra | Phân loại API, tránh lộ tên secret/tenant |
| `outcome`, `duration_ms` | Có | Chẩn đoán lỗi/hiệu năng |
| `http_status` | Chỉ khi biết chính xác | Không đoán 403/404 dựa vào exception class |
| `token`, `private_key`, `secret_value` | **Không** | Dữ liệu cần được bảo vệ |
| `VaultResponse.toString()` hoặc body | **Không** | Có thể chứa secrets hoặc thông tin xác thực |

Với những lời gọi thất bại, giữ `vault_request_id` ở giá trị `null` hoặc bỏ field nếu không có bằng chứng ID thật. Không dùng chuỗi ngẫu nhiên làm ID thay thế vì sẽ làm việc join audit sai. `app_request_id` vẫn giúp truy vết application log và thời điểm xảy ra lỗi.

## 10. Truy vấn audit bằng Vault request ID

Với quyền truy cập audit file của môi trường thử nghiệm, tìm mọi entry có cùng `request.id`. Ví dụ sử dụng `jq` trên JSON Lines:

~~~bash
AUDIT_FILE=/var/log/vault/application-audit.log
REQUEST_ID=22a8124e-e47f-4fc9-9964-c5623dd66357

jq -c --arg id "$REQUEST_ID" \
  'select(.request.id == $id) |
   {time, type,
    vault_request_id: .request.id,
    operation: .request.operation,
    path: .request.path,
    namespace: .request.namespace,
    error: (.error // null)}' \
  "$AUDIT_FILE"
~~~

Output ví dụ:

~~~json
{"time":"2026-11-25T10:30:00.100Z","type":"request","vault_request_id":"22a8124e-e47f-4fc9-9964-c5623dd66357","operation":"read","path":"kv/data/apps/orders/config","namespace":{"id":"root"},"error":null}
{"time":"2026-11-25T10:30:00.113Z","type":"response","vault_request_id":"22a8124e-e47f-4fc9-9964-c5623dd66357","operation":"read","path":"kv/data/apps/orders/config","namespace":{"id":"root"},"error":null}
~~~

**Quy trình điều tra sự cố:**

1. Tìm lỗi trong log ứng dụng theo `app_request_id` hoặc `trace_id`.
2. Tìm đúng sự kiện `vault_call` và lấy `vault_request_id` nếu có.
3. Truy vấn audit bằng `request.id`, lấy cả entry request và response.
4. Kiểm tra `request.operation`, `request.path`, namespace, audit `error` và auth/policy context được phép xem.
5. Đối chiếu timestamp application/Vault, các lời gọi liên quan và metrics.
6. Kết luận nguyên nhân theo bằng chứng: ACL, path, workload auth, engine, timeout hay tình huống khác.

Ở hệ thống log tập trung như Elasticsearch, Loki hoặc Splunk, index trường `request.id` thành field có thể truy vấn; nếu định dạng dữ liệu không hỗ trợ dấu chấm trong tên field, đặt tên được thống nhất lúc parse. **Không nhân bản toàn bộ audit response chứa secrets vào ứng dụng** chỉ để truy vấn nhanh.

### Có nhiều audit devices hoặc nhiều Vault instances

Các audit devices có thể ghi cùng request và response. Khi tính **số request duy nhất**, deduplicate theo `request.id` trong phạm vi cluster/cửa sổ dữ liệu phù hợp. Khi xây dựng cặp request/response, vẫn phải giữ cả `type=request` và `type=response`; nếu deduplicate chỉ theo ID mà bỏ type, bạn sẽ làm mất nửa câu chuyện.

Trong hệ thống multi-cluster, chỉ dùng request ID sau khi đã xác định Vault cluster/namespace đang phục vụ workload. ID là duy nhất theo request do Vault tạo nhưng không phải thay thế cho toàn bộ thông tin định tuyến và bối cảnh sự cố.

## 11. Nếu request ID không có trong ứng dụng

Không phải mọi request đều có một response body mà Spring Vault chuyển thành `VaultResponse`. Những tình huống thường gặp:

| Tình huống | Vì sao Java không có Vault ID? | Hướng xử lý |
|---|---|---|
| TLS handshake hoặc DNS fail | Request chưa đến Vault | Kiểm tra network/TLS ở client, proxy và Vault operational logs |
| HTTP timeout | Vault có thể đã nhận hoặc chưa nhận request | Dùng thời gian, path, namespace, audit và reverse proxy; không kết luận từ timeout một mình |
| HTTP 403 | Error handler có thể ném exception trước khi code nhận response | Thu thập status có kiểm soát, tìm audit theo thời gian/identity/path |
| HTTP 404 / secret không tồn tại | Client có thể trả `null` hoặc exception tùy API | Phân biệt missing secret với sai mount/KV version |
| Transit/PKI high-level API | Object trả về có thể không chứa request ID | Instrument transport phù hợp hoặc dùng API trả metadata khi thật sự cần |
| Token renewal chạy nền | Không cùng application request/thread | Ghi event lifecycle riêng, thời gian và ID nếu API trả về |
| Client qua Vault Agent / proxy | Có lớp mạng hoặc auth trung gian | Xem cách agent/proxy xử lý request, response và danh tính thực |

Trong trường hợp thiếu ID, chỉ có thể **thu hẹp ứng viên** từ operation, path, namespace, timestamp, actor và proxy route. Nếu nhiều request giống nhau cùng xảy ra, kết quả đó **không phải join chính xác**. Hãy ghi rõ mức độ chắc chắn thay vì gán bừa một `request.id`.

Nếu cần lấy request ID cả ở lỗi, cân nhắc instrumentation ở tầng HTTP client theo phiên bản Spring Vault và contract Vault: interceptor/error handler phải xử lý dữ liệu an toàn, bảo toàn response body cho decoder và phân biệt lỗi transport với HTTP response. Thử trên môi trường test trước khi triển khai.

## 12. Liên hệ với các loại thao tác của SPRING_VAULT

Một request nghiệp vụ có thể kích hoạt các thao tác Vault khác nhau. Mỗi loại có điểm cần quan sát riêng:

| Nghiệp vụ | Path API minh họa | Tín hiệu điều tra |
|---|---|---|
| KV v2 get | `kv/data/apps/orders/config` | Sai `data`/`metadata`, thiếu `read`, secret không tồn tại |
| KV v2 list | `kv/metadata/apps/orders` | Thiếu `list`, path liệt kê khác với GET |
| Transit encrypt | `transit/encrypt/orders-key` | Thiếu `update`, input/context sai, lỗi version policy |
| Transit decrypt | `transit/decrypt/orders-key` | Thiếu `update`, ciphertext/khóa/context không phù hợp |
| PKI issue | `pki/issue/orders-server` | Token thiếu `update` hoặc PKI role từ chối CN/SAN/TTL |
| Database dynamic creds | `database/creds/orders-readonly` | Vault ACL, plugin DB, SQL creation, credential lease |
| Token lookup/renew | `auth/token/lookup-self`, `auth/token/renew-self` | Token TTL, quyền, trạng thái session manager |
| Lease renew/revoke | `sys/leases/renew`, `sys/leases/revoke` | Lease ID, TTL, backend cleanup; cần bảo vệ dữ liệu định danh lease |

Các ví dụ path giả định mount giống tên trong bài. Nếu engine được mount ở tên khác, request path/audit path thay đổi theo cấu hình thực.

**Bối cảnh đặc biệt với renewal:** `SessionManager` có thể đăng nhập lại/renew token; `SecretLeaseContainer` có thể renew hoặc rotate secret ngoài thread xử lý HTTP. Để theo dõi, nên log sự kiện `vault_token_renewal`, `vault_secret_renewal`, `vault_secret_rotation` với outcome và duration nếu có, nhưng **không log token, secret ID, password hoặc private key**.

Một lỗi làm đứt connection pool có thể xuất hiện **sau** lỗi renew lease hàng phút; phải phân tích chuỗi sự kiện theo thời gian, không chỉ tìm Vault audit request trùng thời điểm JDBC lỗi.

## 13. Tương quan với metrics và distributed tracing

Log trả lời “request cụ thể nào?”, metrics giúp trả lời “vấn đề có lan rộng không?”, tracing mô tả “độ trễ nằm ở đoạn nào?”.

### Metrics nên đo

| Metric do ứng dụng định nghĩa | Kiểu | Nhãn có thể dùng |
|---|---|---|
| `vault_client_requests_total` | Counter | `engine`, `operation`, `outcome` |
| `vault_client_request_duration_seconds` | Timer/histogram | `engine`, `operation`, `outcome` |
| `vault_client_errors_total` | Counter | `error_class` đã chuẩn hóa, `engine` |
| `vault_token_renew_failures_total` | Counter | `auth_method` hoặc môi trường không nhạy cảm |
| `vault_secret_lease_renew_failures_total` | Counter | `secret_type` được phân loại |
| `vault_db_credentials_rotations_total` | Counter | `role_category` cố định thay vì username phát sinh |

**Không đặt `vault_request_id`, `app_request_id`, `trace_id`, raw secret path, tenant ID có số lượng rất lớn hoặc lease ID thành metric labels.** Chúng có cardinality cao, làm metric store phình ra và có thể rò rỉ metadata. Đặt request IDs trong log/traces có retention và kiểm soát truy cập phù hợp.

Khi đo độ trễ từ Java bằng `System.nanoTime()`, kết quả là thời gian tổng phía client (bao gồm pool, networking, retries nếu method làm các việc đó). Không mặc định bằng chênh lệch hai timestamp trong Vault audit; Vault audit có thời điểm ghi request/response phía server. Chênh lệch giúp nhận diện độ trễ network và client, nhưng phải có đồng hồ đồng bộ và hiểu cơ chế đo trước khi diễn giải.

### Trace và span

Khi Spring Boot sử dụng Micrometer Tracing/OpenTelemetry, có thể tạo span cho một lời gọi Vault nếu instrumentation phù hợp. Gắn các thuộc tính đã lọc như:

~~~text
span.name = "vault.kv.read"
vault.engine = "kv"
vault.operation = "read"
vault.path_template = "kv/data/apps/orders/{id}"
vault.request_id = "22a8124e-e47f-4fc9-9964-c5623dd66357"  # nếu có
~~~

Đừng đưa bí mật, đường dẫn chứa tenant nhạy cảm hoặc token làm span attributes. Một application trace ID có thể liên quan nhiều Vault request IDs; vì vậy mỗi span Vault nên ghi ID riêng khi biết, để đối chiếu audit chính xác.

## 14. Kiểm thử tích hợp cơ chế tương quan

Mock `VaultOperations` có thể kiểm tra code logging, nhưng **không chứng minh** rằng Vault audit đã ghi đúng ID. Nên dùng một Vault instance thử nghiệm có audit device và một ứng dụng Spring Boot test với workload token giới hạn.

### Ma trận kiểm thử

| Ca | Thao tác | Bằng chứng mong đợi |
|---|---|---|
| C01 | GET một KV v2 secret có thật | `VaultResponse.getRequestId()` không rỗng và có cặp audit entry chứa `request.id` ấy |
| C02 | Hai GET độc lập trên cùng path | Hai Vault request IDs khác nhau, dù cùng application correlation ID |
| C03 | HTTP request tạo hai thao tác Vault | Hai `vault_request_id` gắn với cùng `app_request_id`/`trace_id` |
| C04 | Token thiếu quyền đọc secret | Java ghi outcome error an toàn; audit thể hiện request và lý do từ chối nếu Vault nhận |
| C05 | Sai path hoặc secret không tồn tại | Phân biệt 404/missing secret và lỗi ACL bằng nguồn kết quả thích hợp |
| C06 | Vault tắt kết nối / DNS fail | App log có lỗi transport và correlation ID; không yêu cầu audit phải có entry |
| C07 | Token/lease renewal nền | Có log lifecycle riêng, không gán sai app request đang xử lý |
| C08 | Audit file bị thu thập từ hai devices | Giữ đủ request/response, deduplicate event theo logic phù hợp |
| C09 | Ghi log secret có dữ liệu nhạy cảm | Scan log xác nhận không xuất hiện token, password, plaintext, private key |
| C10 | Asynchronous request / thread reuse | MDC được truyền/giải phóng đúng, không lẫn correlation IDs |

### Ví dụ JUnit 5 đọc Vault response ID

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@SpringBootTest
class VaultRequestIdIntegrationTest {

    @Autowired
    private VaultOperations vault;

    @Test
    void vaultProvidesRequestIdsForTwoIndependentReads() {
        // Fixture: KV v2 mount "kv", key này đã tồn tại trước test.
        String path = "kv/data/apps/orders/it-config";

        VaultResponse first = vault.read(path);
        VaultResponse second = vault.read(path);

        assertNotNull(first);
        assertNotNull(second);
        assertNotNull(first.getRequestId());
        assertNotNull(second.getRequestId());
        assertNotEquals(first.getRequestId(), second.getRequestId());

        // Bước kế tiếp của harness tích hợp:
        // truy vấn audit sink test theo hai ID vừa nhận và xác nhận
        // mỗi ID có cả request/response; không đọc/log data secrets.
    }
}
~~~

Điều kiện để chạy:

1. `@SpringBootTest` phải kết nối **Vault thực hoặc Vault thử nghiệm tương thích**, với Vault authentication và policy được cấp phù hợp.
2. Key đã tồn tại trước khi chạy test; nếu gọi `read` vào key không có thật, test không cô lập được việc thiếu request ID khỏi lỗi not-found.
3. Audit sink test phải được operator cấu hình và cho phép harness đọc dữ liệu đã lọc; bản thân test workload **không cần quyền quản trị audit device**.
4. Việc tìm chính xác cặp audit entries cần tính đến độ trễ đẩy log tới hệ thống tập trung; dùng retry hữu hạn thay vì giả định log xuất hiện tức thì.
5. Đừng assert ID bằng giá trị UUID cố định. Chỉ kiểm tra ID thật là duy nhất giữa các request và có thể tra audit tương ứng.
6. Đối với tình huống lỗi 403 và network fail, kiểm chứng theo test riêng; không bắt `VaultResponse` tồn tại sau khi exception ném ra.

### Kiểm tra không lộ secrets

Tạo một giá trị canary dành riêng cho fixture test, ghi vào KV và thực hiện một request đọc hợp lệ. Sau đó quét **application log**, **trace attributes** và **metrics labels** xem canary xuất hiện ở đâu. Không dùng canary là mật khẩu sản xuất hoặc token thật. Với Vault audit, chấp nhận rằng có thể xuất hiện HMAC/masked metadata; bảo đảm không có plaintext do cấu hình `log_raw` hoặc ngoại lệ HMAC.

## 15. Runbook điều tra: ứng dụng Java gặp 403 hoặc timeout

Tình huống: `orders-api` thất bại khi đọc cấu hình sau một đợt deploy.

**Bước 1 — Xác định nghiệp vụ.** Tìm request bị lỗi qua `app_request_id` hoặc trace; ghi thời gian và service instance, release/version đang chạy.

**Bước 2 — Xác định lời gọi Vault.** Tìm `vault_call` có operation `read`, `engine=kv`, `path_template` và `vault_request_id` nếu nhận được. Xem thời gian phía client và loại lỗi; không yêu cầu log phải có raw exception hoặc body.

**Bước 3 — Ghép Vault audit.** Nếu có ID, tìm các entry `request.id` trùng ID. Đối chiếu operation, path, namespace, auth/policy context và `error`.

**Bước 4 — Phân loại lỗi.**

| Bằng chứng | Giả thuyết ưu tiên | Hành động |
|---|---|---|
| Audit chỉ ra `permission denied` trên `kv/data/...` | Token không có `read`, policy path sai hoặc token/namespace không đúng | Kiểm tra auth role, token capabilities, KV version |
| Audit path là `kv/apps/...` nhưng engine KV v2 | Client đang dùng đường dẫn KV v1 | Sửa code/config đúng API `data` |
| Audit có lỗi do secrets engine/plugin | Backend tạm lỗi hoặc cấu hình engine | Xem Vault operational logs và backend health |
| Không có ID trong app; Vault audit có request tương ứng gần đó | Response có thể mất/exception trước khi decode | Phân tích theo timestamp/path/identity, ghi rõ mức độ chắc chắn |
| Không có audit event, có lỗi TLS handshake trước HTTP | Request có thể chưa đến Vault | Kiểm tra CA trust, network, proxy, DNS, timeout |
| Client duration cao nhưng audit gap rất ngắn | Có thể tắc ở client/network/retry | Kiểm tra connection pool, TCP, TLS, DNS và instrumentation |
| Vault request/response audit gap cao | Có thể chậm ở Vault/backend | Kiểm tra telemetry, storage, plugin và server logs |

**Bước 5 — Khôi phục đúng tầng.** Sửa workload ACL hoặc API path khi có bằng chứng, xử lý Vault health/DB plugin khi backend lỗi, xử lý client timeout/TLS khi request chưa tới Vault. Không tăng quyền `sys/*` hoặc dùng root token chỉ để làm request đang lỗi trở nên thành công.

**Bước 6 — Xác nhận sau sửa.** Chạy lại positive và negative tests với workload token, đối chiếu request ID mới và bảo đảm secret không bị ghi vào log.

## 16. Những lỗi thường gặp trong cơ chế correlation

| Triệu chứng | Sai lầm | Cách sửa |
|---|---|---|
| Không tìm được audit entry khi search bằng `trace_id` | Trace ID do ứng dụng sinh, Vault audit không mặc định lưu nó | Tìm `vault_request_id` và join với `request.id` |
| Có 2 audit entries cho 1 request | Vault ghi cả `type=request` và `type=response` | Cặp này là mong đợi; giữ cả hai để điều tra |
| Có 4 entry cho 1 request | Hai audit devices ghi lặp lại cùng request/response | Deduplicate theo device/source, request ID và type khi thống kê |
| App log có secret value | Log raw `VaultResponse` hoặc HTTP body | Xóa payload khỏi log, dùng allowlist metadata và scrub lịch sử theo quy trình |
| Audit token hash khác giữa hai devices | HMAC key/salt theo từng device | Join bằng `request.id`, không join bằng token HMAC |
| Không có `vault_request_id` khi HTTP 403 | Error handler ném exception trước khi lấy response | Instrument failure metadata an toàn; audit theo thời gian nếu cần |
| `app_request_id` bị trùng giữa các request | MDC không xóa hoặc header từ client không tin cậy | Dùng `finally` và kiểm tra format/nguồn ID |
| Log và audit lệch thời gian | Clock skew, timezone hoặc ingestion delay | Chuẩn hóa UTC/NTP và phân biệt event time với ingest time |
| Dashboard có cardinality cực cao | Gắn request IDs làm metric tags | Giữ IDs trong log/traces; metrics chỉ dùng low-cardinality labels |
| Revoke lease lỗi nhưng business trace không báo | Renewal/revocation ở background | Ghi event riêng cho thành phần quản lý lease |
| Quá nhiều Vault request IDs cho một request | Client retry/auth refresh/secret reads phát sinh thêm cuộc gọi | Ghi operation, span và thời gian mỗi lần gọi; kiểm tra retry thực tế |

## 17. Checklist triển khai và câu hỏi tự kiểm tra

Trước khi đưa logging/correlation vào production:

- [ ] Mỗi lời gọi Vault có sự kiện log metadata với `operation`, `engine`, outcome và duration.
- [ ] `app_request_id` và `trace_id` được tạo/truyền đúng và có cách kiểm soát độ dài, nguồn tin cậy.
- [ ] Với response có `request_id`, Spring Vault lấy và log `vault_request_id`, không tự bịa giá trị.
- [ ] Có schema/đường truy vấn map `vault_request_id` ở app sang `request.id` trong audit.
- [ ] Audit device được operator bật, kiểm tra có ghi dữ liệu, giám sát lỗi và retention.
- [ ] Đã rà soát HMAC, non-HMAC exceptions, filters và quyền xem audit logs.
- [ ] Không log token, password, KV value, PKI private key, Transit plaintext hoặc toàn bộ response.
- [ ] Metrics dùng nhãn có cardinality thấp; IDs được giữ trong log/traces phù hợp.
- [ ] Có tests cho success, ACL denied, transport failure, nhiều Vault calls và background renewal.
- [ ] Đã xác minh log cleanup/MDC propagation khi xử lý async/reactive.

Câu hỏi ôn tập:

1. Một HTTP request của người dùng gọi Vault ba lần. Có bao nhiêu `vault_request_id` và bao nhiêu `app_request_id` theo mô hình thông thường?
2. Trường audit nào dùng để ghép entry request và response với nhau? Có nên tìm `response.request_id` không?
3. Vì sao `VaultResponse.getRequestId()` có thể dùng cho GET thành công, nhưng một HTTP 403 không nhất thiết để lại ID trong log Java?
4. Khi audit có HMAC của token, có thể dùng hash đó để join trực tiếp giữa hai audit devices không?
5. Vì sao không đưa `vault_request_id` vào nhãn Prometheus metric?
6. Khi không có audit entry và Java báo TLS handshake failure, có thể khẳng định ACL của Vault từ chối request hay không?

## 18. Tổng kết

**Tương quan log ứng dụng với audit của Vault** dựa trên việc giữ các định danh đúng vai trò: `app_request_id` nhóm sự kiện nghiệp vụ, `trace_id` liên kết các span phân tán, và **`vault_request_id`** định vị một lần gọi Vault. Trong Vault audit, cặp `request`/`response` có cùng **`request.id`**. Với các API phù hợp, Spring Vault cung cấp `VaultResponse.getRequestId()` để ứng dụng ghi lại giá trị này.

Khả năng truy vết có ích nhất khi kết hợp **log metadata đã lọc**, **audit devices được bảo vệ**, **metrics không chứa nhãn cardinality cao**, và **kiểm thử tích hợp** cho cả request thành công lẫn thất bại. Cần luôn phân biệt request đã được Vault nhận nhưng response bị mất với request thất bại trước khi đến Vault; không có ID không đồng nghĩa chắc chắn không có audit.

Khi thực hành KV, token/lease, Transit, PKI và database dynamic credentials trong **SPRING_VAULT**, cách làm này giúp khoanh vùng lỗi theo đúng thành phần, đo độ trễ, hiểu ACL thực tế và hỗ trợ điều tra mà không phải mở rộng quyền hoặc lộ dữ liệu bí mật.

### Tài liệu tham khảo

- [HashiCorp Vault — Audit log entry schema](https://developer.hashicorp.com/vault/docs/audit/schema)
- [HashiCorp Vault — Audit devices](https://developer.hashicorp.com/vault/docs/audit)
- [HashiCorp Vault — Audit logging best practices](https://developer.hashicorp.com/vault/docs/audit/best-practices)
- [HashiCorp Vault — Troubleshoot Vault](https://developer.hashicorp.com/vault/tutorials/monitoring/troubleshooting-vault)
- [Spring Vault — VaultResponse API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultResponse.html)
- [Spring Vault — VaultResponseSupport API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultResponseSupport.html)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
