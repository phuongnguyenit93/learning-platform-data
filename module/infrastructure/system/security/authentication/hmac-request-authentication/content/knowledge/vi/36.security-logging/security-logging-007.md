# Log reason tổng quát khi xác thực HTTP request bằng HMAC

## 1. Vì sao cần log reason tổng quát?

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, một HTTP request được xác thực bằng HMAC tạo từ **shared secret** và **canonical request** đã thỏa thuận. Hợp đồng ký có thể bao gồm method, URI, các header và/hoặc digest của body. Server phải kiểm tra chữ ký, timestamp/nonce để chống replay, trạng thái key khi rotation và tác động của proxy/gateway. Khi đã xác thực được principal, hệ thống vẫn cần **phân quyền** độc lập.

Chương **Security logging** tập trung vào việc ghi nhận các sự kiện bảo mật mà không biến hệ thống log thành nơi lộ bí mật. Bài **Log reason tổng quát** trả lời ba câu hỏi:

1. Khi HMAC verification thất bại, **nên ghi nhận nhóm nguyên nhân nào** để vận hành và điều tra có thể hành động?
2. Thông tin **nào được trả cho client**, thông tin nào chỉ được giữ trong log nội bộ?
3. Làm sao bảo đảm log không chứa shared secret, chữ ký, canonical request nhạy cảm, body, dữ liệu định danh không cần thiết hoặc chuỗi do đối tượng tấn công điều khiển?

Ví dụ đối tác gọi:

~~~http
POST /api/signed/payments HTTP/1.1
Content-Type: application/json
X-Key-Id: merchant-a-v2
X-Timestamp: 2026-11-28T03:20:00Z
X-Nonce: f45b6f1e-6d3b-4c6f-9a7a-36a9cf8cb21f
X-Signature: <base64-signature>

{"amount":125000,"currency":"VND"}
~~~

Nếu chữ ký sai, service trả lỗi xác thực nhất quán. Ở nội bộ, service vẫn cần biết lỗi đến từ input thiếu, signature không hợp lệ, replay, lệch đồng hồ hoặc hệ thống xác minh không khả dụng. **“Log reason tổng quát”** nghĩa là ghi các **mã lý do có kiểm soát, ổn định, đủ phân nhóm**, thay vì ghi toàn bộ exception message, canonical string hoặc giá trị do client cung cấp.

## 2. Hai nơi tiêu thụ thông tin lỗi có mục đích khác nhau

Client cần biết **hành động tiếp theo**: ký lại request, điều chỉnh thời gian hệ thống, kiểm tra quyền truy cập hoặc thử lại khi hệ thống đang gián đoạn. Đội vận hành cần số liệu để chẩn đoán lỗi tích hợp, phát hiện replay và xác định sự cố key/nonce store. Hai nhu cầu này không đòi hỏi phải công khai mọi nguyên nhân xác minh.

| Kênh | Nội dung nên cung cấp | Nội dung cần tránh |
|---|---|---|
| HTTP response cho client | HTTP status chính xác, error code công khai ổn định, request ID được chuẩn hóa | Key có tồn tại không, secret, MAC kỳ vọng, canonical string, nonce đã dùng lúc nào |
| Security event nội bộ | Mã reason từ enum có kiểm soát, trạng thái, route template, trace ID, kết quả authn/authz | Header HMAC nguyên văn, request/response body, raw query chứa dữ liệu nhạy cảm |
| Metrics | Bộ đếm theo reason/status/route nhóm và số liệu độ trễ | Key ID/nonce/signature/trace ID làm nhãn metric |
| Trace | Span xác minh và trạng thái tổng quát, correlation giữa gateway và service | Tự động ghi nguyên header/body, URL chứa token hoặc query nhạy cảm |
| Điều tra có kiểm soát | Có thể cần bằng chứng bổ sung từ hệ thống chuyên dụng, theo thời hạn và quyền riêng | Bật debug toàn bộ credential trong production |

Một API có thể trả cùng lỗi **401 Unauthorized** cho key ID không tồn tại, chữ ký sai, timestamp bị từ chối và nonce replay. Điều này hạn chế khả năng dùng response làm **oracle** suy đoán key/secret và giúp client xử lý lỗi nhất quán.

Ngược lại, lỗi kho nonce/secret không khả dụng là vấn đề vận hành: response **503 Service Unavailable** có thể phù hợp hơn 401 vì không có đủ cơ sở kết luận credential sai. Tuy vậy, request **vẫn phải bị chặn** vì không thể bảo đảm xác thực/chống replay.

## 3. Một taxonomy reason đủ rộng và ổn định

### 3.1. Các mã reason dành cho nội bộ

Taxonomy đề xuất cho service HMAC (tên mã chỉ là ví dụ, cần version và thống nhất trong hệ thống):

| Reason code nội bộ | Khi nào ghi | Nhóm sự kiện |
|---|---|---|
| `CREDENTIAL_MISSING` | Route yêu cầu HMAC nhưng thiếu một hoặc nhiều trường ký | `authn_rejected` |
| `CREDENTIAL_MALFORMED` | Header lặp, signature encoding sai, timestamp/nonce sai cú pháp | `authn_rejected` |
| `CREDENTIAL_INVALID` | Key không còn được chấp nhận, signature không khớp, canonical contract không xác minh được | `authn_rejected` |
| `FRESHNESS_REJECTED` | Timestamp ngoài cửa sổ đã cấu hình | `authn_rejected` |
| `REPLAY_REJECTED` | Nonce đã được claim trong phạm vi client/key tương ứng | `authn_rejected` |
| `VERIFICATION_UNAVAILABLE` | Lỗi key store, nonce store hoặc thành phần cần thiết để xác minh | `authn_unavailable` |
| `AUTHORIZATION_DENIED` | Principal HMAC hợp lệ nhưng không đủ quyền/không được truy cập resource | `authz_denied` |
| `PAYLOAD_LIMIT_REJECTED` | Body vượt giới hạn kích thước trước khi xác minh | `input_rejected` |
| `AUTHENTICATED` | Request xác thực HMAC thành công | `authn_accepted` |

**Reason phải đến từ một enum hoặc bảng ánh xạ cố định**, do phía server lựa chọn theo kết quả xử lý. Không nhận `reason` từ header, không ghép `exception.getMessage()` vào log, không dùng raw client input làm tên reason.

Một quyết định hữu ích là **gộp “unknown key”, “key revoked”, “wrong secret”, “bad body digest” vào `CREDENTIAL_INVALID`** ở log thông thường. Nếu hệ thống thật sự cần phân tích sâu, sử dụng một trường chẩn đoán riêng có bảo vệ và kiểm soát quyền, không để trạng thái tồn tại của một key trở thành dữ liệu quan sát rộng rãi.

**Không gán `BODY_MISMATCH` chỉ từ việc HMAC không khớp.** Signature sai có thể do method, raw URI, header, body, phiên bản canonical hoặc secret khác nhau. Chỉ khi có bằng chứng độc lập rằng byte body client gửi khác byte verifier nhận (ví dụ test fixture và digest trong môi trường kiểm thử) mới có cơ sở phân loại cụ thể hơn.

### 3.2. Mã lỗi HTTP và reason không phải cùng một khái niệm

| Bước bị từ chối | Reason nội bộ | Response gợi ý |
|---|---|---|
| Thiếu/sai định dạng credential bắt buộc | `CREDENTIAL_MISSING` hoặc `CREDENTIAL_MALFORMED` | 401 theo policy của ví dụ; trường hợp lỗi cú pháp HTTP có thể là 400 |
| Không kiểm tra được HMAC trên request | `CREDENTIAL_INVALID` | 401 |
| Timestamp sai cửa sổ | `FRESHNESS_REJECTED` | 401 |
| Nonce trùng | `REPLAY_REJECTED` | 401 |
| Không truy cập được kho key/nonce | `VERIFICATION_UNAVAILABLE` | 503; fail closed |
| Xác thực xong nhưng thiếu authority | `AUTHORIZATION_DENIED` | 403 |
| Body vượt giới hạn | `PAYLOAD_LIMIT_REJECTED` | 413 |
| HMAC hợp lệ, đủ quyền | `AUTHENTICATED` (và authorization outcome riêng nếu cần) | Theo kết quả nghiệp vụ |

Đối với HTTP 401, server phải gửi header `WWW-Authenticate` với challenge áp dụng cho tài nguyên. Nếu API tự định nghĩa scheme HMAC, ví dụ `WWW-Authenticate: HMAC realm="signed-api"` là **quy ước riêng của hợp đồng**, không phải một scheme được mặc định chuẩn hóa bởi Spring Security.

Ví dụ response cho nhiều nguyên nhân xác thực khác nhau:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: HMAC realm="signed-api"
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: 22a7c641a5494aa9

{"type":"about:blank","title":"Unauthorized","status":401}
~~~

Không gửi reason nội bộ như `REPLAY_REJECTED` hay `CREDENTIAL_INVALID` trong body lỗi nếu chính sách công khai không cho phép. Với hệ thống cần thông báo hướng dẫn “clock skew” cho client, phải cân nhắc mức độ tiết lộ và hợp đồng; trong mô hình cơ bản hãy dùng phản hồi chung, rồi đối chiếu mã request trong kênh hỗ trợ được xác thực.

## 4. Luồng ghi nhận sự kiện đúng vị trí

~~~mermaid
flowchart TD
    A[HTTP request qua gateway] --> B[HMAC filter / verifier]
    B --> C{Kiểm tra thế nào?}
    C -- Thiếu/sai format/MAC --> D[401 chung cho client]
    C -- Lệch timestamp / nonce replay --> D
    C -- Kho key hoặc nonce lỗi --> E[503; fail closed]
    C -- Xác thực thành công --> F[SecurityContext / principal]
    F --> G{Đủ authority?}
    G -- Không --> H[403]
    G -- Có --> I[Handler nghiệp vụ]
    D --> J[Security audit: reason enum]
    E --> J
    H --> J
    F --> K[Authn success event, nếu policy yêu cầu]
    J --> L[Metrics + cảnh báo + log tập trung]
    K --> L
~~~

**Tách “quyết định xác thực” và “ghi log quyết định”**: verifier xác định trạng thái có chứng cứ; lớp security/audit biến trạng thái đó thành event với schema cố định. Không để caller tự cung cấp reason hoặc message chứa dữ liệu request tùy ý.

Thời điểm phát event:

1. Tạo correlation/request ID tin cậy khi nhận request (hoặc xác thực một ID có sẵn theo quy tắc của gateway).
2. Kiểm tra phạm vi route HMAC; không tạo failure reason cho các route cố ý không dùng HMAC.
3. Từ kết quả verifier, ghi **một event authn outcome** cho mỗi lần kiểm tra có kết luận.
4. Nếu xác thực thành công nhưng authorization từ chối, ghi **event authz riêng**, không đổi authn success thành “bad signature”.
5. Khi xảy ra lỗi hạ tầng, ghi event `VERIFICATION_UNAVAILABLE` theo cách không chứa secret hoặc exception message.
6. Dừng request theo HTTP status phù hợp; không tiếp tục chain sau khi từ chối.

Trong hệ thống có nhiều filter, cần tránh ghi trùng một sự kiện ở cả verifier, filter, entry point và exception handler. Một cơ chế **centralized audit publisher** tại nơi kết luận outcome giúp event nhất quán; các bước chi tiết có thể phát metric riêng khi cần.

## 5. Schema log an toàn và dễ truy vấn

Thay vì ghi một câu tự do:

~~~text
HMAC failed for keyId=merchant-a-v2 signature=abc... body={"amount":...}
~~~

hãy ghi sự kiện có cấu trúc (JSON minh họa):

~~~json
{
  "event": "security.hmac.authentication",
  "schema_version": 1,
  "outcome": "rejected",
  "reason": "CREDENTIAL_INVALID",
  "http_status": 401,
  "route": "POST /api/signed/payments",
  "request_id": "22a7c641a5494aa9",
  "principal_ref": "anonymous",
  "duration_ms": 8,
  "service": "payment-service"
}
~~~

Timestamp thường được hệ thống log tự gắn bằng clock UTC. Có thể bổ sung trace/span ID, deployment environment, gateway identity đã xác thực hoặc revision hợp đồng HMAC nếu có giá trị vận hành. Tránh các label có cardinality không giới hạn trong metric.

| Field | Cách tạo an toàn |
|---|---|
| `event`, `schema_version` | Hằng số của ứng dụng; thay đổi có quản lý phiên bản |
| `outcome` và `reason` | Enum cố định từ kết quả server xác minh |
| `http_status` | Mã thực tế được trả, do response handler quyết định |
| `route` | **Route template** hoặc route ID được server xác định; không phải raw URL/query người dùng gửi |
| `request_id` | ID do hệ thống tạo hoặc nhận từ gateway tin cậy, kiểm tra giới hạn dài/ký tự |
| `principal_ref` | `anonymous` trước xác thực; sau xác thực có thể là mã tham chiếu giả danh phía server |
| `duration_ms` | Đo từ clock đơn điệu cho elapsed time, không dùng timestamp do client khai báo |
| `service` | Tên service do cấu hình nội bộ cung cấp |

**Key ID, client ID, tenant ID, IP và user agent đều có thể là dữ liệu nhận dạng.** Nếu bài toán thực sự cần truy vết theo client, hãy dùng mã tham chiếu nội bộ có kiểm soát hoặc pseudonymization theo chính sách (ví dụ một HMAC riêng cho mục đích log, với secret tách khỏi secret xác thực). Đừng đưa raw `X-Key-Id` chưa xác thực vào log hoặc metric như một định danh đáng tin; đối tượng tấn công có thể tạo giá trị tùy ý, gây log injection/cardinality explosion.

### 5.1. Những thứ không nên log

- Shared secret, chuỗi secret mã hóa Base64/hex, khóa đang rotate hoặc thông tin trong secret manager.
- `X-Signature` nguyên văn, HMAC kỳ vọng, byte canonical request có dữ liệu nhạy cảm, raw body hoặc raw query chứa token/PII.
- `Authorization`, cookie/session ID, API key, `X-Nonce` nguyên văn hoặc toàn bộ header map.
- Full stack trace của lỗi credential khi exception message chứa request data/secret. Với lỗi hạ tầng, chỉ ghi loại exception và mã sự cố đã kiểm soát; chi tiết kỹ thuật cần cân nhắc quyền truy cập.
- Bản sao toàn bộ HTTP request/response từ reverse proxy, tracing agent hoặc debug filter khi route có dữ liệu tài chính hay credential.

Hash không đồng nghĩa ẩn danh: SHA-256 của thông tin có không gian giá trị nhỏ có thể bị dò; digest payload cố định có thể cho phép liên kết các giao dịch. Chỉ lưu digest khi có mục đích điều tra và chính sách retention thích hợp, ưu tiên môi trường test với payload giả.

### 5.2. Chống log injection

Header từ client có thể chứa ký tự bất thường, ký tự xuống dòng sau các lớp decode hoặc chuỗi dài. Nếu nối trực tiếp vào message log, đầu vào không đáng tin có thể làm giả dòng log hoặc phá parser:

~~~java
// Không nên: đưa nội dung của client hoặc exception message vào log.
log.warn("HMAC rejected: " + request.getHeader("X-Key-Id")
        + " reason=" + exception.getMessage());
~~~

Chỉ ghi **enum/hằng số**, giới hạn độ dài và làm sạch mọi trường cần thiết phải có nguồn từ client; để logging library thực hiện escaping JSON khi dùng structured logging. Parameterized logging giúp tránh dựng chuỗi thừa nhưng **không tự động khiến giá trị không đáng tin trở thành an toàn**.

## 6. Ví dụ Java 17+ với SLF4J: phát event reason tổng quát

Ví dụ dưới đây độc lập với cách tạo canonical request. Verifier phải trả kết quả hoặc exception đã phân loại; lớp audit chỉ nhận các field được server kiểm soát. `routeTemplate` đến từ route registry, `requestId` được phát hành/kiểm tra tại boundary, `actorRef` là danh tính giả danh từ principal đáng tin, không lấy nguyên từ HTTP header.

~~~java
public enum HmacReason {
    CREDENTIAL_MISSING,
    CREDENTIAL_MALFORMED,
    CREDENTIAL_INVALID,
    FRESHNESS_REJECTED,
    REPLAY_REJECTED,
    VERIFICATION_UNAVAILABLE,
    AUTHORIZATION_DENIED,
    PAYLOAD_LIMIT_REJECTED,
    AUTHENTICATED
}
~~~

~~~java
public record HmacAuditEvent(
        String requestId,
        String routeTemplate,
        String actorRef,
        HmacReason reason,
        Integer httpStatus,
        long durationMs) {
    // Caller chỉ truyền ID/route đã được tạo hoặc chuẩn hóa phía server.
}
~~~

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class HmacSecurityAuditLogger {
    private static final Logger LOG =
            LoggerFactory.getLogger(HmacSecurityAuditLogger.class);

    public void record(HmacAuditEvent event) {
        String outcome = switch (event.reason()) {
            case AUTHENTICATED -> "accepted";
            case VERIFICATION_UNAVAILABLE -> "unavailable";
            default -> "rejected";
        };

        // Các giá trị field đã được kiểm soát tại boundary.
        // Dùng log encoder cấu trúc (JSON) của ứng dụng trong production.
        LOG.info(
            "security_event=hmac outcome={} reason={} status={} "
                + "route={} request_id={} principal_ref={} duration_ms={}",
            outcome,
            event.reason().name(),
            event.httpStatus(),
            event.routeTemplate(),
            event.requestId(),
            event.actorRef(),
            event.durationMs()
        );
    }
}
~~~

Một lần ghi nhận tại filter sau khi verifier kết luận:

~~~java
// Pseudocode điều phối; mỗi nhánh trả response và dừng chain đúng chỗ.
try {
    Authentication auth = verifier.verify(request);
    audit.record(new HmacAuditEvent(
        trustedRequestId, routeTemplate, trustedActorRef(auth),
        HmacReason.AUTHENTICATED, null, elapsedMs()));
    continueFilterChain(auth);
} catch (BadCredentialsException invalid) {
    audit.record(new HmacAuditEvent(
        trustedRequestId, routeTemplate, "anonymous",
        HmacReason.CREDENTIAL_INVALID, 401, elapsedMs()));
    sendGeneric401AndReturn();
} catch (AuthenticationServiceException unavailable) {
    audit.record(new HmacAuditEvent(
        trustedRequestId, routeTemplate, "anonymous",
        HmacReason.VERIFICATION_UNAVAILABLE, 503, elapsedMs()));
    send503AndReturn();
}
~~~

Đây là **pseudocode** để diễn tả vị trí event, không phải một servlet filter đầy đủ. Trong triển khai thực, `BadCredentialsException` có thể đại diện cho nhiều dạng sai credential; chỉ ghi reason chi tiết hơn nếu **verifier có kết quả đáng tin cậy**. `httpStatus = null` trong event success ví dụ thể hiện **chưa có HTTP response cuối cùng**; JSON encoder có thể bỏ field status khi chưa biết. Nếu cần status thực tế, hãy ghi thêm event khi response được commit hoặc tách `planned_status` và `response_status`.

Để log chính xác một lần và tránh trùng lặp, có thể dùng một audit result duy nhất từ authentication/authorization decision, còn HTTP status cuối cùng được capture trong một response observer độc lập. Nếu một request đã xác thực nhưng handler trả lỗi 500, event authentication vẫn là **`AUTHENTICATED`**; không tự đổi nó thành credential failure.

### 6.1. Servlet và WebFlux có điểm khác nhau

**Spring MVC/Servlet:** có thể gắn request ID vào `MDC` khi bắt đầu request, nhưng phải `MDC.remove(...)` hoặc `MDC.clear()` trong `finally` để tránh rò context giữa các request được xử lý trên thread pool. `AuthenticationEntryPoint` và `AccessDeniedHandler` là điểm xử lý 401/403 phù hợp, còn audit publisher ghi reason ở nơi kết luận.

**Spring WebFlux:** `MDC` dựa trên `ThreadLocal` không tự đi theo chuỗi reactive khi đổi thread. Hãy dùng **Reactor Context** và cơ chế context propagation/observability tương thích (hoặc truyền correlation data tường minh). Không gọi `block()` để log và không dùng các thao tác log network blocking trên Netty event-loop. Nếu pipeline logging bất đồng bộ có hàng đợi giới hạn, cần quy tắc rõ khi đầy queue.

## 7. Correlation qua gateway/proxy và multi-tenant

Một giao dịch có thể đi qua gateway, service mesh và service:

~~~text
Client → Gateway  →  Payment service  →  Nonce store
          req_id A        req_id A          trace/span A
             |               |
          route map       HMAC reason
~~~

Cho phép một correlation ID dùng để liên kết sự kiện theo request, nhưng phải xác định **ai là bên đáng tin cậy tạo ID**. Nếu client gửi `X-Request-Id`, gateway có thể tạo lại hoặc chuẩn hóa/giới hạn giá trị. Không dùng chuỗi do client gửi không giới hạn làm log field hay làm khoá phân quyền.

Khi gateway rewrite `/public/v1/payments` thành `/payments`, log tại service nên có **route template nội bộ** và, nếu thật sự cần, **public route ID đã được xác thực bởi gateway**. Không log toàn bộ raw URI để “so sánh cho nhanh”, bởi raw query có thể chứa token, email hay dữ liệu nhạy cảm.

Trong multi-tenant, key ID có thể thuộc client/tenant khác nhau. Log `principal_ref=anonymous` khi chưa chứng thực, rồi mới gắn tenant/client reference từ key store **sau khi HMAC hợp lệ**. Không suy ra tenant đáng tin từ `X-Tenant-Id` của request chưa được xác thực.

Khi cần theo dõi tỷ lệ lỗi theo một đối tác, chỉ tạo nhãn định danh theo chính sách bảo vệ dữ liệu và giới hạn cardinality. Thường nên dùng dashboard theo service/route/reason, rồi tra cứu một request cụ thể bằng correlation ID trong log nội bộ có quyền.

## 8. Phân tích vận hành bằng metrics, logs và cảnh báo

### 8.1. Chọn metric có cardinality giới hạn

Một metric dạng counter hữu ích:

~~~text
hmac_auth_requests_total{
    outcome="rejected",
    reason="CREDENTIAL_INVALID",
    route="payments.create",
    service="payment-service"
}
~~~

Các label như `reason`, `outcome` và route ID là tập giá trị có thể dự đoán trước. **Không** dùng nonce, signature, raw path, request ID, key ID tự khai báo hoặc IP làm metric label; số lượng chuỗi tùy ý có thể khiến chi phí và dung lượng bộ nhớ bùng nổ.

Một số tín hiệu vận hành cần quan sát:

| Tín hiệu | Khả năng gợi ý | Việc kiểm tra tiếp theo |
|---|---|---|
| `CREDENTIAL_INVALID` tăng đồng loạt trên một route | Proxy rewrite sai canonical, secret/algorithm đổi, client ký sai hoặc truy cập độc hại | So sánh version canonical và deployment gần nhất; dùng test vector |
| `FRESHNESS_REJECTED` tăng | Đồng hồ client/server lệch, timestamp format hoặc retry cũ | Kiểm tra NTP/clock, skew và thời gian trung gian |
| `REPLAY_REJECTED` tăng | Retry dùng lại nonce, duplicate delivery hoặc replay attack | Kiểm tra nonce scope, idempotency và request correlation |
| `VERIFICATION_UNAVAILABLE` xuất hiện | Redis/key store/secret manager lỗi | Kiểm tra timeout, dependency saturation và fail closed |
| `AUTHORIZATION_DENIED` tăng sau thay đổi role/policy | Quyền client/tenant bị thay đổi hoặc route map sai | Kiểm tra policy/authority, không sửa xác minh HMAC |
| `PAYLOAD_LIMIT_REJECTED` tăng | SDK gửi payload lớn hoặc traffic bất thường | Kiểm tra giới hạn body và phương án streaming |

Không kết luận chắc chắn “đang bị tấn công” chỉ vì 401 tăng. Một bản deploy gateway thay path hoặc chính sách canonical sai có thể tạo triệu chứng tương tự. Cần đối chiếu thay đổi cấu hình, đường đi request, tỷ lệ theo route và sự cố các dịch vụ phụ thuộc.

### 8.2. Sampling, retention và bảo vệ luồng log

Request hợp lệ có thể có lưu lượng cao; có thể tổng hợp bằng metrics, sampling log success hoặc chỉ ghi audit những thao tác quan trọng theo chính sách. Event lỗi xác thực và lỗi kho nonce cần đủ bằng chứng để giám sát, nhưng **bản thân logging không được tạo đường DoS**: giới hạn dung lượng event, số trường, kích thước queue và rate; không lấy toàn bộ request làm payload log.

Áp dụng retention theo mục đích và quy định, phân quyền truy cập log/trace, mã hóa đường truyền và nơi lưu, audit việc truy cập kho log. Đặt lại quyền định danh khi dữ liệu đi vào SIEM hoặc dịch vụ quan sát bên ngoài; tránh gửi credential tới vendor mặc định.

Lỗi hệ thống logging thông thường **không phải bằng chứng để cho qua HMAC**. Quyết định xác thực vẫn phải được thực thi độc lập. Nếu nghiệp vụ thuộc diện bắt buộc audit bền vững trước khi thực hiện, cần thiết kế chính sách fail closed/transactional audit riêng, đo lường hậu quả về availability; không tự ngầm biến log thành điểm cho phép xác thực.

## 9. Kiểm thử reason và tính an toàn của log

Để kiểm thử đúng, cần assert cả **HTTP status**, **không có side effect** khi từ chối và **audit event được phân loại đúng**. Nên có một audit sink in-memory/fake để quan sát event mà không phụ thuộc log text formatter. Test phải kiểm tra rằng không có field chứa secret hoặc raw user input.

| Test case | HTTP | Event reason mong đợi |
|---|---|---|
| Thiếu tất cả header HMAC trên signed route | 401 | `CREDENTIAL_MISSING` |
| Trùng `X-Signature` hoặc signature không phải Base64 hợp lệ | 401 theo policy | `CREDENTIAL_MALFORMED` |
| Key ID không hợp lệ hoặc MAC không khớp | 401 | `CREDENTIAL_INVALID` (không lộ key có tồn tại) |
| Thay một byte body đã ký | 401 | `CREDENTIAL_INVALID`; không suy diễn body là nguyên nhân duy nhất |
| Timestamp quá cũ/quá xa tương lai | 401 | `FRESHNESS_REJECTED` |
| Gửi lại request có cùng nonce đã claim | 401 | `REPLAY_REJECTED` |
| Hai request cạnh tranh nonce giữa hai replica | Tối đa một request qua authn | Mỗi attempt có một outcome; replay được phân nhóm đúng |
| Key hoặc nonce store bị timeout | 503 | `VERIFICATION_UNAVAILABLE` |
| HMAC đúng nhưng thiếu `payments:write` | 403 | Authn success và authz `AUTHORIZATION_DENIED` |
| Body vượt hạn mức trước verify | 413 | `PAYLOAD_LIMIT_REJECTED` |
| Proxy rewrite public path sai | 401 hoặc lỗi route theo hợp đồng | Chỉ phân loại nội bộ theo bằng chứng verifier có |
| Request tới endpoint công khai ngoài HMAC filter | Theo route đó | Không có event lỗi HMAC giả |
| Client gửi key ID/header chứa CRLF hoặc chuỗi rất dài | 401/400 theo policy | Log không bị chèn dòng, không in chuỗi tùy ý |
| Client gửi signature, secret giả, JSON chứa PII | 401 | Không có credential/body trong log hoặc trace |

Ví dụ cách kiểm thử một record event sau thất bại:

~~~java
// Pseudocode JUnit/Mockito: verifier trả BadCredentialsException.
mockMvc.perform(post("/api/signed/payments")
        .header("X-Key-Id", "untrusted-attacker-value")
        .header("X-Signature", "bad-signature")
        .content("{\"amount\":125000}"))
    .andExpect(status().isUnauthorized());

verify(auditSink).publish(argThat(event ->
        event.reason() == HmacReason.CREDENTIAL_INVALID
        && event.httpStatus() == 401
        && "anonymous".equals(event.actorRef())));
verifyNoInteractions(paymentService);
~~~

Ở ứng dụng thật, test còn cần kiểm tra các nhánh `AuthenticationServiceException` → 503, authorization → 403, filter không gọi tiếp chain sau từ chối, request ID do gateway/service cấp an toàn và không có bản sao header/body trong auto-instrumentation.

### 9.1. Test “không lộ dữ liệu”

Một test có thể dùng secret/nonce/body giả có chuỗi nhận diện đặc trưng:

~~~text
TEST_SECRET_MUST_NOT_APPEAR
TEST_SIGNATURE_MUST_NOT_APPEAR
TEST_BODY_PII_MUST_NOT_APPEAR
TEST_NONCE_MUST_NOT_APPEAR
~~~

Sau khi chạy các request thành công và thất bại, kiểm tra output từ log encoder, trace exporter hoặc in-memory appender; mọi chuỗi nhạy cảm này phải **vắng mặt**. Chạy lại test với gateway/proxy bật access log để chắc chắn hệ thống quan sát ở biên không ghi raw URL/query hay header xác thực ngoài chính sách.

Khi cần test log injection, tạo dữ liệu untrusted chứa newline/control characters và chuỗi dài rồi xác minh event vẫn là **một record có cấu trúc**, reason là một giá trị enum; không có sự kiện giả được sinh ra từ dữ liệu client.

## 10. Các lỗi triển khai thường gặp

**Ghi `exception.getMessage()` để chẩn đoán “nhanh”.** Message từ thư viện hoặc do người viết verifier tạo có thể chứa key ID, signature, canonical request hay body; hãy ánh xạ exception sang enum reason và chỉ lưu loại lỗi kỹ thuật đã kiểm soát.

**Gửi reason rất chi tiết cho client.** Phản hồi khác nhau giữa “key tồn tại nhưng MAC sai” và “key không tồn tại” có thể tạo oracle. Giữ response chung cho các nguyên nhân credential, cân nhắc chi tiết hỗ trợ qua kênh xác thực riêng.

**Đưa nonce/signature/route raw vào metric label.** Dữ liệu đầu vào có cardinality gần vô hạn. Dùng route template, enum reason và service ID để lập biểu đồ; tra cứu từng request bằng trace ID trong log.

**Đồng nhất mọi 401 thành body mismatch.** HMAC sai còn có thể do URI, header, thuật toán, key rotation hoặc timestamp; reason tổng quát giúp tránh kết luận khi chưa có chứng cứ.

**Xem 403 như thất bại xác thực HMAC.** HMAC đúng mới có principal; nếu principal thiếu quyền, đó là `AUTHORIZATION_DENIED`, không nên tăng counter signature mismatch.

**Nuốt exception hạ tầng thành “bad credentials” rồi trả 401.** Khi kho nonce không hoạt động, cần fail closed và ghi reason hạ tầng. Không được “cho qua tạm” để tránh gián đoạn.

**Ghi trùng mỗi lỗi ở nhiều lớp.** Một request có thể tạo nhiều dòng với các reason mâu thuẫn. Thiết kế một nguồn phát audit quyết định và cho tracing/metrics sử dụng cùng outcome.

**Dựa vào ThreadLocal MDC trong pipeline WebFlux.** Khi đổi thread, log có thể mất/nhầm correlation ID. Dùng Reactor Context hoặc cơ chế propagation đã kiểm chứng.

**Giữ log vĩnh viễn vì cho rằng không có secret.** Ngay cả reason, ID đã băm và route cũng có thể trở thành dữ liệu nhạy cảm khi ghép chéo; retention và truy cập phải được quản lý.

## 11. Checklist áp dụng

- [ ] Reason được lấy từ enum/taxonomy nội bộ, có schema version và quy tắc ánh xạ rõ ràng.
- [ ] 401 cho chứng thực không hợp lệ; 403 cho thiếu quyền sau xác thực; 503 khi không thể xác minh; 413 khi body vượt giới hạn.
- [ ] HTTP response không tiết lộ key tồn tại hay không, expected signature, shared secret hoặc nonce state.
- [ ] Security event có route template, trusted correlation ID, outcome/reason, status và thời gian xử lý; không chứa raw URL/body/header HMAC.
- [ ] Trước xác thực không coi key ID/tenant từ header là danh tính đáng tin; principal reference chỉ phát từ dữ liệu server sau khi xác minh.
- [ ] Structured logging bảo vệ trước log injection, giới hạn kích thước event và không đưa nguyên giá trị untrusted vào log.
- [ ] Metrics dùng label ít giá trị (reason/outcome/route), không dùng signature, nonce, key ID hoặc request ID làm label.
- [ ] Có cơ chế bảo vệ log/trace (quyền truy cập, mã hóa, retention, audit và chia sẻ đúng mục đích).
- [ ] Servlet MDC được dọn ở cuối request; WebFlux dùng context propagation phù hợp.
- [ ] Mỗi attempt có outcome audit nhất quán, không ghi trùng từ nhiều security handler.
- [ ] Key/nonce store lỗi không cho request đi qua; replay và key rotation được theo dõi bằng reason/metric riêng.
- [ ] Kiểm thử HTTP status, side effect, mã reason và sự vắng mặt của secret/PII trong log/trace.

**Điểm cốt lõi:** reason tổng quát là một **ngôn ngữ sự kiện có kiểm soát** giữa verifier HMAC và hệ thống quan sát. Nó giúp phân biệt lỗi credential, freshness, replay, phân quyền và hạ tầng mà không buộc ứng dụng công khai dữ liệu có thể hỗ trợ tấn công. Khi được ghi đúng thời điểm, đúng phạm vi và bảo vệ theo vòng đời dữ liệu, security logging vừa hữu ích cho vận hành vừa giữ nguyên ranh giới xác thực và phân quyền.
