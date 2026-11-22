# Giữ dữ liệu token nhạy cảm ngoài phản hồi API và nhật ký

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, access token là bằng chứng mà client trình cho API để được xác thực. JWT có thể mang các claims về chủ thể, client, tenant và quyền truy cập; opaque token có thể được đối chiếu với Authorization Server để lấy thông tin tương tự. Sau khi xác thực, Spring Security đặt principal và các authorities vào một đối tượng `Authentication` để ứng dụng thực thi phân quyền.

**Principal được xác thực không đồng nghĩa toàn bộ dữ liệu token đều được phép công bố.** Một lỗi phổ biến là trả thẳng `Jwt`, `Authentication`, `OAuth2AuthenticatedPrincipal` hoặc đối tượng chứa header `Authorization` trong JSON API. Một lỗi khác là dùng logger, HTTP tracing hoặc exception handler để in nguyên access token, claims nhạy cảm hoặc thông tin xác thực gửi đến introspection endpoint. Những thông tin đó có thể bị lưu lâu trong log, hệ thống quan sát, báo lỗi hoặc dữ liệu hỗ trợ khách hàng, làm tăng phạm vi ảnh hưởng nếu có người đọc được.

Bài học này tập trung vào mục tiêu **giữ dữ liệu token nhạy cảm ngoài phản hồi API và nhật ký** trong ngữ cảnh **Principal và danh tính**: phân loại thông tin, chọn dữ liệu principal tối thiểu, thiết kế DTO, sử dụng Spring Security an toàn, kiểm soát log và tracing xuyên suốt request, đồng thời kiểm chứng rằng hệ thống không vô tình tạo một con đường tiết lộ credential.

> Tất cả token, hostname, định danh người dùng và tenant xuất hiện trong ví dụ đều là giá trị giả lập. Không sử dụng access token thật trong tài liệu, ví dụ HTTP, ảnh chụp màn hình, test fixture chia sẻ hoặc câu lệnh được ghi lại trong CI.

## 1. Phân biệt credential, claim, principal và dữ liệu được phép trả

Giả sử client gọi Orders API:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

Nếu access token là JWT, nó có thể mang các thông tin minh họa:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read profile",
  "client_id": "shop-web",
  "tenant_id": "tenant-a",
  "jti": "token-id-example",
  "iat": 1924988400,
  "exp": 1924992000,
  "email": "person@example.test",
  "groups": ["sales", "internal"]
}
~~~

Đây chỉ là phần **payload chưa kèm chữ ký** để đọc hiểu. Một Resource Server đáng tin phải xác minh chữ ký/nguồn khóa, issuer, thời gian, audience và những yêu cầu token profile trước khi sử dụng các claims.

Sau xác thực:

~~~text
HTTP Authorization header:
    Bearer <ACCESS_TOKEN>          ← credential bí mật
             |
             v
JwtDecoder / OpaqueTokenIntrospector
             |
             v
Authentication:
    principal    = Jwt / OAuth2AuthenticatedPrincipal
    name         = subject hoặc giá trị theo mapping
    authorities  = SCOPE_orders.read, SCOPE_profile
    credentials  = thông tin do implementation giữ
             |
             v
Controller/service:
    sử dụng danh tính đã xác thực
    áp phân quyền
    xây response DTO chỉ có field nghiệp vụ cần thiết
             |
             v
HTTP response:
    KHÔNG chứa raw token, Authorization header, claim tùy ý
~~~

### 1.1. Bảng phân loại dữ liệu

| Dữ liệu | Độ nhạy cảm / rủi ro | Chính sách đề xuất |
|---|---|---|
| **Raw access token** | Bearer credential; ai sở hữu có thể gọi API trong phạm vi token | **Không trả JSON; không ghi log/trace/metric; không đính kèm lỗi** |
| **Refresh token** | Có thể dùng lấy access token mới; thường rất nhạy cảm | Không xuất hiện trong Resource Server response/log |
| **ID token** | Có thể mang claims danh tính và PII; dành cho OIDC client | Không echo qua API Resource Server; không dùng thay access token |
| **`Authorization: Bearer ...`** | Mang raw access token | Redact toàn header ở mọi tầng |
| **`Authorization: Basic ...`** từ introspection | Mang client ID/secret được mã hóa Base64, không được bảo vệ chỉ bằng Base64 | Redact toàn header, bảo vệ secret bằng secret manager |
| **Client secret/private key** | Credential của ứng dụng hoặc khóa ký | Không trả response, không log, không commit |
| **Cookie/session identifier** | Có thể là credential truy cập phiên | Không log giá trị; bảo vệ qua cookie policy |
| **`sub` / username / email** | Danh tính hoặc dữ liệu cá nhân; có thể cho phép liên kết hoạt động | Chỉ trả cho caller được phép và mục đích đã xác định; hạn chế log |
| **`tenant_id`, nhóm, vai trò** | Dữ liệu nội bộ và phạm vi tổ chức | Trả theo nhu cầu, không expose toàn bộ token profile |
| **`scope`, `aud`, `iss`, `client_id`** | Thường không phải secret tự thân, nhưng tiết lộ cấu trúc/quyền và có thể tương quan người dùng | Không tự động đưa vào public response hoặc high-cardinality log |
| **`jti`** | Token identifier, có thể liên kết các request với một credential | Không dùng raw trong log công khai; cần policy riêng nếu dùng audit/revocation |
| **`kid`** | Key identifier; thường công khai trong JOSE/JWKS nhưng có thể là input tùy ý | Chỉ dùng metadata quan sát có giới hạn, không tin làm bằng chứng authentication |
| **Request ID/trace ID do hệ thống tạo** | Dùng tương quan vận hành, không phải credential | Có thể trả/log nếu được thiết kế tránh PII và injection |

Nguyên tắc **tối thiểu hóa dữ liệu** không chỉ áp dụng cho giá trị “bí mật tuyệt đối”. Một claim như `email` hoặc `sub` có thể không giúp attacker trực tiếp gọi API, nhưng vẫn mang thông tin nhận dạng hoặc hoạt động của người dùng. Chỉ trả hoặc ghi nó khi có nhu cầu nghiệp vụ, quyền truy cập và chính sách lưu giữ rõ ràng.

### 1.2. Tại sao Bearer token đặc biệt nhạy cảm?

Theo mô hình Bearer token, bên giữ token có thể trình token cho Resource Server và được xử lý theo quyền của token, **không nhất thiết phải chứng minh mình là người nhận ban đầu** bằng một khóa riêng. Nếu token còn hiệu lực, được cấp đúng audience và scope, việc rò rỉ token có thể dẫn đến lạm dụng quyền trong cửa sổ sống của nó.

Một số hệ thống triển khai sender-constrained token (ví dụ DPoP hoặc mTLS-bound token) giảm khả năng dùng lại token nếu không có thêm bằng chứng phù hợp, nhưng **không vì thế được phép log token**. Token vẫn có giá trị bảo mật, có thể chứa PII và cần được quản lý riêng theo profile.

**Mã hóa Base64URL của JWT không phải mã hóa bí mật.** Bất kỳ ai có token thường đều có thể giải mã header/payload JWT để đọc claims; bảo mật đến từ chữ ký và kiểm soát ai được thấy token, không phải từ việc payload nhìn như chuỗi khó đọc.

## 2. Các nguồn rò rỉ token thường gặp

Một request API có thể đi qua nhiều thành phần trước khi phản hồi:

~~~mermaid
flowchart LR
    C["Client"] --> G["API Gateway / Proxy"]
    G --> F["Servlet Filter / Spring Security"]
    F --> S["Controller / Service"]
    S --> R["Response DTO"]
    G -. "access logs" .-> L["Log pipeline / SIEM"]
    F -. "debug / exceptions" .-> L
    S -. "application logs" .-> L
    G -. "tracing" .-> T["APM / Traces"]
    F -. "tracing" .-> T
    S -. "metrics / audit" .-> T
~~~

Rò rỉ có thể xảy ra ở **nhiều tầng độc lập**:

| Điểm phát sinh | Ví dụ không an toàn | Hậu quả |
|---|---|---|
| Controller response | `return jwt;` hoặc `return authentication;` | Serializer có thể đưa token/attributes vào JSON |
| Controller debug endpoint | Trả toàn bộ `SecurityContextHolder.getContext()` | Lộ principal, authority, credential |
| Exception handler | `return Map.of("error", ex.getMessage())` với message chứa token/header | Đưa dữ liệu nội bộ vào HTTP response |
| Application logger | `log.info("auth={}", authentication)` | Implementation/toString có thể bộc lộ dữ liệu nhạy cảm |
| Log request headers | `log.debug("headers={}", request.getHeaderNames()...)` | Ghi `Authorization`, Cookie, API key |
| Log query string/body | Token được truyền sai vào query/body | Access log, tracing hoặc analytics thu token |
| HTTP client đến IdP | Log outgoing request introspection/token exchange | Lộ token introspect và client secret |
| Gateway/ingress | Access log có header hoặc full URL | Credential bị copy vào hệ thống log tập trung |
| Distributed tracing | Gắn token, `sub`, email làm span attribute/baggage | Lan dữ liệu sang nhiều service/nhà cung cấp APM |
| Error reporting | SDK tự thu HTTP request, exception, local variables | Token nằm trong crash report |
| Support/debug workflow | Dán cURL từ request thật vào ticket | Credential xuất hiện trong nơi lưu dài hạn |
| Test/CI pipeline | In `Authorization` khi test thất bại | Token được giữ lại trong build log |

**Redaction ở ứng dụng Java không đủ để bảo vệ toàn bộ hệ thống** nếu gateway hoặc APM đã ghi token từ trước khi request tới controller. Cần chính sách xuyên suốt các lớp mạng, ứng dụng, observability và support.

## 3. Phân biệt `Jwt`, `Authentication` và response DTO

Với JWT Resource Server, principal phổ biến là `Jwt` được gắn trong `JwtAuthenticationToken`. Đối tượng `Jwt` giữ cả token value và claims đã được xác minh. Một controller có thể inject:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class IdentityController {

    @GetMapping("/api/me")
    Object me(@AuthenticationPrincipal Jwt jwt) {
        return jwt; // PHẢN VÍ DỤ: không trả cả Jwt.
    }
}
~~~

Đây là **phản ví dụ**, không nên triển khai. Vì các phiên bản/serializer khác nhau có thể serialize thuộc tính khác nhau, không thể dựa vào giả định rằng Jackson sẽ tự loại token value hoặc mọi claim nhạy cảm. **Không trả cả đối tượng security framework**.

Tương tự:

~~~java
// PHẢN VÍ DỤ:
@GetMapping("/api/debug/authentication")
public Authentication debug(Authentication authentication) {
    return authentication;
}
~~~

Một `Authentication` có thể chứa principal, credential, authorities và details. Trả thẳng nó tạo coupling với implementation và mở rộng bề mặt dữ liệu ngoài hợp đồng API.

### 3.1. Dùng DTO rõ ràng, chỉ chọn field được phép

Một endpoint `/api/me` hợp lý có thể chỉ cần trả định danh hiển thị đã được phép và một nhãn account:

~~~java
public record MeResponse(
    String displayName,
    String accountType
) {}
~~~

Controller:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class MeController {

    @GetMapping("/api/me")
    MeResponse me(@AuthenticationPrincipal Jwt jwt) {
        // Chỉ dùng claim đã xác minh, sau khi đã áp policy.
        String displayName = jwt.getClaimAsString("preferred_username");
        if (displayName == null || displayName.isBlank()) {
            displayName = "Authenticated user";
        }
        return new MeResponse(displayName, "user");
    }
}
~~~

Ví dụ này giả định `preferred_username` được hợp đồng token cho phép dùng làm tên hiển thị, caller có quyền nhận nó và endpoint được bảo vệ. **Không nên dùng `preferred_username` để quyết định quyền sở hữu tài nguyên**, vì tên hiển thị có thể thay đổi và không duy nhất. `sub` và issuer/tenant thường phù hợp hơn cho identity logic, theo chính sách của hệ thống.

Không xuất `jwt.getTokenValue()`, `jwt.getClaims()` hoặc `jwt.getHeaders()` để “tiện debug”. Khi client thực sự cần một thuộc tính, hãy thêm **field riêng vào DTO** kèm quyết định quyền truy cập thay vì trả toàn bộ claim map.

### 3.2. Dùng danh tính nội bộ, tránh đưa raw subject ra client khi không cần

Không phải ứng dụng nào cũng cần trả `sub`. Một API đơn hàng có thể đọc `sub` nội bộ để truy vấn đúng owner nhưng response chỉ đưa dữ liệu đơn hàng:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {
    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/api/orders/{id}")
    OrderResponse getOrder(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
        String subject = jwt.getSubject();
        String issuer = jwt.getIssuer().toString();

        // Phân quyền trên bản ghi thuộc service/domain.
        return orders.findVisibleOrder(id, issuer, subject);
    }
}
~~~

`OrderService`, `OrderResponse` và `findVisibleOrder` là thành phần nghiệp vụ do ứng dụng định nghĩa. Ví dụ minh họa việc **dùng claim để kiểm tra quyền nội bộ** mà không echo claim vào JSON. Trong hệ thống đa tenant, identity key còn có thể cần tenant ID theo hợp đồng.

### 3.3. Đối với opaque token

Nếu Resource Server dùng introspection, principal phổ biến là `OAuth2AuthenticatedPrincipal`. Tránh cách làm:

~~~java
// PHẢN VÍ DỤ:
@GetMapping("/api/debug/principal")
Object principal(@AuthenticationPrincipal OAuth2AuthenticatedPrincipal p) {
    return p; // Có thể expose toàn bộ introspection attributes.
}
~~~

Thay bằng DTO chỉ chứa thuộc tính phù hợp:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OpaqueMeController {

    @GetMapping("/api/account-kind")
    AccountKindResponse accountKind(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        // Không trả principal.getAttributes() trực tiếp.
        return new AccountKindResponse("authenticated");
    }
}

record AccountKindResponse(String kind) {}
~~~

Introspection response có thể mang `sub`, `scope`, `client_id`, email hoặc claims tùy issuer. Chỉ vì Authorization Server **được phép trả** dữ liệu cho Resource Server không có nghĩa API được phép **trả nguyên dữ liệu đó** cho client.

## 4. Tách identity nội bộ khỏi hợp đồng JSON bên ngoài

Một Resource Server có thể nhận tokens từ những client khác nhau, mỗi loại token profile có chủ thể khác nhau. Các kiểu identity thường thấy:

| Trường hợp | Principal có thể đại diện | Điều không nên giả định |
|---|---|---|
| Authorization Code + user consent | Người dùng cuối và bối cảnh client | Mọi claim user đều được phép công bố |
| Client Credentials | Service/application | Có username/email của người dùng |
| Token Exchange | Principal/client được ủy quyền theo hợp đồng | `sub` luôn có cùng nghĩa với token ban đầu |
| Access token opaque | Principal từ introspection | Introspection attributes được phép trả public |
| Multi-tenant resource | Subject theo issuer/tenant | `sub` là duy nhất trên mọi issuer/tenant |

Đối với response API, hãy định nghĩa **ngôn ngữ nghiệp vụ**: tên hiển thị, trạng thái đặt hàng, quyền UI đã được sản phẩm chấp thuận, hoặc mã account nội bộ không tiết lộ token. Không đồng nhất DTO với cấu trúc claims phát hành bởi Authorization Server.

### 4.1. Không dùng claims làm DTO động

Một phản ví dụ thường gặp:

~~~java
// PHẢN VÍ DỤ: expose tùy ý các claim được issuer thêm về sau.
return Map.copyOf(jwt.getClaims());
~~~

Hôm nay JWT chỉ có `sub` và `scope`; ngày mai Identity team thêm `email`, `phone_number` hoặc claim dành cho hệ thống kiểm soát gian lận. Endpoint “debug” có thể tự động phơi bày các trường mới mà không qua rà soát.

DTO có danh sách field cố định là **allowlist ở cấp contract**. Nếu thêm một field, cần quyết định nguồn dữ liệu, quyền caller, mục đích, khả năng nhận dạng cá nhân và cách kiểm thử.

### 4.2. Cẩn thận với `Authentication.getName()`

`getName()` không tự động là trường an toàn để trả công khai. Với JWT, tên có thể được ánh xạ từ `sub` hoặc claim do ứng dụng cấu hình như `preferred_username`; với opaque token, nó phụ thuộc introspector/principal. Đừng giả định `getName()` luôn là mã hiển thị vô hại.

Một string “đã xác thực” vẫn có thể là email, ID nhân sự hoặc danh tính có thể liên kết xuyên dịch vụ. Quyết định hiển thị phải nằm trong hợp đồng API.

## 5. Ghi nhật ký có kiểm soát trong Servlet Resource Server

Spring Security dùng nhiều thành phần để xác thực request: `BearerTokenAuthenticationFilter`, `AuthenticationManager`, `JwtDecoder` hoặc `OpaqueTokenIntrospector`, rồi đặt `Authentication` vào `SecurityContextHolder`. Ứng dụng đôi khi cần log hoạt động để điều tra lỗi hoặc đo hiệu suất, nhưng **log nghiệp vụ không cần raw Bearer token**.

### 5.1. Tránh log toàn bộ request, principal hoặc security context

Các ví dụ **không nên triển khai**:

~~~java
// PHẢN VÍ DỤ:
log.info("Authorization={}", request.getHeader("Authorization"));
log.debug("All headers={}", Collections.list(request.getHeaderNames()));
log.info("Authentication={}", authentication);
log.debug("Principal={}", authentication.getPrincipal());
log.info("JWT={}", jwt.getTokenValue());
log.debug("JWT claims={}", jwt.getClaims());
log.info("Credentials={}", authentication.getCredentials());
log.error("Request failed: {}", request, exception);
~~~

Lý do:

- `Authorization` có thể chứa Bearer access token hoặc Basic credentials.
- Một header khác có thể chứa API key, Cookie hoặc credential của hệ thống.
- `Authentication`, principal và `Jwt` mang các trường security; cách `toString()`/serialization xử lý chúng không phải hợp đồng chống rò rỉ của ứng dụng.
- `getClaims()` có thể chứa PII, tenant, group, email, permission nội bộ.
- `request.toString()`, exception chain hoặc logger HTTP framework có thể vô tình chứa URL/query/header/body tùy phiên bản và configuration.
- Log DEBUG/TRACE khi được bật trong production có thể làm lộ dữ liệu mà mức INFO không từng ghi.

**Không dựa vào việc “logger hiện tại dường như che token” làm biện pháp bảo vệ duy nhất**. Một lần nâng cấp framework, đổi encoder hoặc thêm dependency có thể thay đổi cách stringify object.

### 5.2. Thiết kế log event theo allowlist

Thay vì log credential, log một sự kiện có các trường **được lựa chọn trước**:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderAuditEvents {
    private static final Logger log =
        LoggerFactory.getLogger(OrderAuditEvents.class);

    public void orderReadCompleted(String requestId, String outcome) {
        // requestId phải do hệ thống tạo hoặc đã được kiểm tra an toàn.
        // outcome là enum/nhóm giá trị hữu hạn, không lấy raw từ client.
        log.info(
            "event=order_read result={} request_id={}",
            outcome,
            requestId
        );
    }
}
~~~

Ví dụ log:

~~~text
INFO event=order_read result=allowed request_id=8f5279f1-0fd2-4c1d-a316-24048e5ef3d6
WARN event=order_read result=denied request_id=6220ec22-ea34-4fbd-8026-7a10c2a80f51
~~~

Log này phục vụ đếm và truy vết mà không phát tán token hoặc subject. Trong hệ thống audit có nghĩa vụ pháp lý phải xác định ai thực hiện thao tác, có thể dùng **audit store được bảo vệ riêng**, với actor ID nội bộ phù hợp, mã sự kiện, quyền đọc hạn chế và retention rõ ràng. Không vì nhu cầu audit mà đưa toàn bộ claims/credential vào application log thông thường.

### 5.3. Request ID không phải token

Để kết nối request với log, có thể dùng một **request ID ngẫu nhiên do hệ thống tạo**. Ví dụ một `OncePerRequestFilter` trên Servlet:

~~~java
import java.io.IOException;
import java.util.UUID;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public final class RequestIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();
        request.setAttribute("requestId", requestId);
        response.setHeader("X-Request-ID", requestId);

        MDC.put("requestId", requestId);
        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove("requestId");
        }
    }
}
~~~

Đăng ký filter này **một lần** theo cấu hình Servlet/Spring Security thực tế, tránh vô tình vừa auto-register như Servlet filter vừa thêm vào security chain theo cách chạy lặp lại. Với ứng dụng cần trace xuyên services, ưu tiên tích hợp observability đã được cấu hình của tổ chức để các ID tương quan đúng chuẩn.

Ví dụ này chủ động **tạo request ID mới**, không chấp nhận trực tiếp chuỗi tùy ý từ `X-Request-ID` do client gửi để ngăn log injection hoặc giá trị quá dài. Nếu muốn nhận một ID từ gateway tin cậy, phải xác định ranh giới trust và validate cú pháp/độ dài.

**MDC dựa trên ngữ cảnh xử lý thread**. Khi dùng async Servlet, `@Async` hoặc executor riêng, không giả định MDC/request context được tự truyền qua mọi thread; phải dùng công cụ context propagation phù hợp nếu cần và dọn dẹp context đúng vòng đời. Không sao chép access token vào MDC để “dễ tìm log”.

### 5.4. Không đưa dữ liệu token vào MDC

Phản ví dụ:

~~~java
// PHẢN VÍ DỤ:
MDC.put("accessToken", jwt.getTokenValue());
MDC.put("subject", jwt.getSubject());  // Cần chính sách riêng nếu định dùng.
MDC.put("email", jwt.getClaimAsString("email"));
~~~

MDC thường được tự động chèn vào **mọi dòng log** khi layout/encoder cấu hình `%X` hoặc JSON structured logging. Một lần thêm giá trị nhạy cảm vào MDC có thể nhân bản dữ liệu qua hàng trăm log event không liên quan. Token càng không nên được đặt vào MDC.

Các trường hữu ích hơn:

~~~text
requestId
traceId
spanId
serviceName
routeName / operationName đã chuẩn hóa
httpStatus
durationBucket
errorCategory
~~~

Tránh dùng email, raw `sub`, full URL hoặc token làm nhãn metric: ngoài quyền riêng tư, chúng còn gây **high cardinality**, làm tăng chi phí và giảm hiệu năng hệ thống quan sát.

## 6. Bảo vệ response lỗi: xác thực thất bại không cần lộ token

Một API nên có phản hồi lỗi giúp client biết bước tiếp theo, nhưng không cần tiết lộ token mà client gửi. Ví dụ một request có JWT sai hoặc hết hạn:

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <INVALID_ACCESS_TOKEN>
~~~

Phản hồi hợp lý:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
Content-Type: application/json

{
  "code": "UNAUTHENTICATED",
  "message": "Access token is missing or invalid."
}
~~~

Đây là phản hồi minh họa; một Spring Security Resource Server có thể chỉ trả Bearer challenge mà không có JSON body. **Không bắt buộc thêm body nếu chưa có hợp đồng API về lỗi**. Nếu thêm body, dùng thông điệp trung tính, không echo JWT hoặc exception nội bộ.

Khi token hợp lệ nhưng thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
Content-Type: application/json

{
  "code": "FORBIDDEN",
  "message": "You do not have permission to perform this action."
}
~~~

Header `WWW-Authenticate` cho Bearer token có quy tắc riêng theo **RFC 6750**. Đừng bỏ header hoặc đưa nội dung bất kỳ khi tự viết handler. Tránh nhét full token, `Authorization` header hay chi tiết xác minh chữ ký vào `error_description`.

### 6.1. Spring Security xử lý 401/403 trước controller

Trong Servlet, lỗi xác thực Bearer token thường được xử lý bởi các security filters và các thành phần như `BearerTokenAuthenticationEntryPoint`, trong khi thiếu quyền được xử lý qua `AccessDeniedHandler`. Vì vậy **`@RestControllerAdvice` không tự động bắt mọi lỗi authentication xảy ra trước DispatcherServlet**.

Một cấu hình Servlet phổ biến:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Spring Security có xử lý Bearer entry point/access-denied phù hợp cho cấu hình Resource Server này. Nếu ứng dụng cần custom JSON error, hãy gắn custom `AuthenticationEntryPoint` và `AccessDeniedHandler` vào đúng security chain, **đảm bảo duy trì semantics 401/403 và Bearer challenge**. Nội dung lỗi phải được chọn từ những giá trị công bố được, không serialize nguyên `AuthenticationException` hoặc `AccessDeniedException`.

### 6.2. DTO lỗi nghiệp vụ không lấy chi tiết security từ exception

Ví dụ một DTO chung:

~~~java
public record ApiError(
    String code,
    String message,
    String requestId
) {}
~~~

Với lỗi xử lý nghiệp vụ trong MVC:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiErrorHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> notFound(OrderNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError(
                "ORDER_NOT_FOUND",
                "The requested order was not found.",
                null
            ));
    }
}
~~~

`OrderNotFoundException` là exception nghiệp vụ giả định của ứng dụng. Mẫu này **không đưa `ex.getMessage()` vào response** vì message có thể được tạo từ nội dung nhạy cảm, data source hoặc thông tin nội bộ. Đối với error body thực tế, `requestId` nên được lấy từ cơ chế request context tin cậy và chỉ trả khi đã xác định chính sách.

### 6.3. Không để exception debug bật thông tin không mong muốn

Một vài thuộc tính liên quan error response, stack trace hoặc error message của framework có thể làm body công khai chi tiết hơn khi bật sai môi trường. Trong Spring Boot, nên kiểm soát các tùy chọn như **include-message**, **include-stacktrace**, **include-binding-errors** và trang error mặc định theo profile triển khai.

Ví dụ cấu hình production có thể dùng:

~~~yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
~~~

Các property này giúp hạn chế nội dung lỗi MVC mặc định theo Spring Boot được dùng, nhưng **không thay thế kiểm soát ở Spring Security filter, gateway, logger, custom exception handler hoặc APM**. Không giả định rằng một property trong YAML sẽ tự redact mọi raw token khỏi hệ thống.

### 6.4. `toString()` của exception không phải dữ liệu response

Phản ví dụ:

~~~java
// PHẢN VÍ DỤ:
return ResponseEntity.status(401).body(
    Map.of("error", exception.toString()));
~~~

Exception có thể chứa endpoint URL, JOSE parsing info, claim value hoặc request data. Chỉ trả mã lỗi công khai (ví dụ `UNAUTHENTICATED`) cùng message ngắn được soạn riêng. Log nội bộ cũng cần tránh in exception message nếu chưa biết nó chứa gì; khi cần stack trace, phải áp redaction/quyền truy cập và retention phù hợp.

## 7. Lỗi bảo mật khi log HTTP request/response tự động

Trong ứng dụng Spring Boot, rò rỉ không chỉ đến từ câu lệnh `log.info()` do developer viết. Một số công cụ **log HTTP wire**, **request/response body**, **headers**, **proxy** hoặc **HTTP client** có thể tự thu thông tin nhạy cảm khi cấu hình mức log quá chi tiết.

### 7.1. Những loại log cần xem xét

| Lớp | Nguy cơ | Biện pháp |
|---|---|---|
| Servlet container access log | URL/query và metadata request; có thể được tùy biến log header | Không log `Authorization`, cookies, query nhạy cảm |
| Servlet logging filters | In mọi header/body request | Tránh blanket logging; sử dụng allowlist field và redaction |
| Spring Security DEBUG/TRACE | Có thể ghi chi tiết authentication/context hoặc exception | Chỉ bật khi thật cần, giới hạn thời gian, scrub dữ liệu nhạy cảm |
| HTTP clients `RestClient`/`WebClient` | Outgoing Bearer token, Basic auth, introspection `token` trong form | Không bật full wire/body logging trong production |
| Netty/Reactor/Apache HTTP client wire logs | Có thể chứa request/response headers/body | Tắt hoặc cấu hình redaction trước khi thu |
| API gateway / ingress | Full request URL hoặc header được đưa vào access log | Chỉ log metadata được phê duyệt |
| Service mesh/sidecar | Telemetry của HTTP hoặc mTLS connection | Không thu payload credential, review processor/filter |
| APM/error monitoring | Tự động gom headers, query, local variables | Filter/denylist ngay tại instrumentation |

Trong các hệ thống dùng **OAuth 2.0 opaque token introspection**, outbound request thường có form field `token=<ACCESS_TOKEN>` và Basic credentials của Resource Server. Vì vậy nếu HTTP client log **toàn bộ request body** khi gọi introspection, cả access token và credential quản trị introspection có thể xuất hiện trong log cùng lúc.

### 7.2. Lọc ở nguồn tốt hơn sửa sau khi dữ liệu đã lưu

Có thể thiết kế các lớp bảo vệ:

~~~text
Ứng dụng không tạo log raw secret
        ↓
Logging middleware chỉ thu field allowlisted
        ↓
Collector/agent có bộ lọc và redaction phụ
        ↓
Log storage mã hóa + RBAC + retention
        ↓
Quy trình truy cập/audit truy vấn log
~~~

Nếu phải **redact** một header, nên **bỏ toàn giá trị**:

~~~text
Authorization: [REDACTED]
Cookie: [REDACTED]
X-API-Key: [REDACTED]
Proxy-Authorization: [REDACTED]
~~~

Không ghi “6 ký tự đầu và 6 ký tự cuối” chỉ để nhận diện access token, vì các mẩu token vẫn là dữ liệu phát sinh từ credential, và việc gộp thông tin nhiều nguồn có thể tăng rủi ro. Với token ngắn, việc lộ một phần thậm chí tiết lộ tỷ lệ lớn credential. Nếu thật sự cần định danh một sự kiện bảo mật, sử dụng request ID/audit ID riêng được tạo có chủ đích.

### 7.3. URL query có thể đã chứa credential do lỗi client

RFC 6750 khuyến nghị client gửi Bearer token qua header; truyền token trong query string là cách đặc biệt rủi ro vì query có thể xuất hiện trong browser history, reverse proxy log, Referrer, metric và các dịch vụ trung gian.

Ví dụ không nên dùng:

~~~http
GET /api/orders/42?access_token=<ACCESS_TOKEN> HTTP/1.1
~~~

Ngay cả khi Resource Server **không hỗ trợ** query token, proxy hoặc access log vẫn có thể lưu query từ request sai. Vì thế chặn query token ở ứng dụng không thay thế việc kiểm soát access log tại gateway/ingress và telemetry.

## 8. WebFlux: dữ liệu nhạy cảm cũng có thể đi vào log reactive

Nếu API dùng **Spring WebFlux**, nguyên tắc không thay đổi:

- Token vẫn đến qua `Authorization: Bearer ...`.
- JWT được xử lý qua `ReactiveJwtDecoder`, opaque token qua `ReactiveOpaqueTokenIntrospector`.
- Principal chỉ được dùng để kiểm tra identity và quyền.
- Response phải là DTO tối thiểu, không phải raw `Jwt` hay `Authentication`.
- Không đưa token vào Reactor `Context`, diagnostic logging, MDC, `baggage` hoặc span attributes theo cách làm chúng xuất hiện trong telemetry.

Một WebFlux controller:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReactiveMeController {

    @GetMapping("/api/me")
    Mono<PublicProfile> me(@AuthenticationPrincipal Jwt jwt) {
        String displayName = jwt.getClaimAsString("preferred_username");
        if (displayName == null || displayName.isBlank()) {
            displayName = "Authenticated user";
        }
        return Mono.just(new PublicProfile(displayName));
    }
}

record PublicProfile(String displayName) {}
~~~

Ví dụ giả định Resource Server nhận JWT và endpoint `/api/me` chỉ có người đã xác thực mới gọi được. Với opaque token, principal là `OAuth2AuthenticatedPrincipal` và cần thiết kế ánh xạ khác. Một `Mono<Jwt>` hoặc `Mono<Authentication>` trả ra HTTP vẫn có khả năng làm lộ dữ liệu như ở Servlet; kiểu reactive **không phải biện pháp tự động che token**.

### 8.1. Tránh Reactor Netty wiretap chứa credential

Khi debug kết nối, một số đội bật HTTP wiretap hoặc log mức TRACE trên Reactor Netty, WebClient, API gateway hoặc thư viện HTTP. Tùy configuration, wire logging có thể in **headers**, **body**, hoặc cả hai. Nếu request chứa Bearer token, đó là một nguồn rò rỉ nghiêm trọng.

Trong môi trường production:

1. Ưu tiên metric kết nối, latency và status thay cho full wire dump.
2. Nếu cần bật logging tạm thời, đảm bảo **redaction tại nguồn** và giới hạn người có quyền truy cập log.
3. Tránh log các request OAuth token/introspection hoặc downstream API có credentials.
4. Tắt cấu hình debug sau khi điều tra; xác định retention và kiểm tra những bản log đã được tạo.

Với WebFlux, MDC dựa trên thread không tự truyền đầy đủ qua asynchronous/reactive execution. Nếu cần correlation ID, sử dụng công cụ context propagation/tracing phù hợp; **không dùng token làm correlation key**.

### 8.2. Đừng để `doOnNext` ghi cả principal

Phản ví dụ:

~~~java
// PHẢN VÍ DỤ: có thể lộ claim hoặc credential.
return ReactiveSecurityContextHolder.getContext()
    .doOnNext(context ->
        log.debug("securityContext={}", context));
~~~

Một ví dụ chỉ ghi sự kiện đã được chọn trước:

~~~java
return orderService.findVisibleOrders()
    .doOnSuccess(ignored ->
        log.info("event=orders_lookup outcome=success"));
~~~

`orderService` và `log` là những thành phần ứng dụng giả định. Nếu cần log request ID, hãy lấy từ tracing/context đã được quản lý thay vì đọc và truyền raw access token qua toàn bộ stream.

## 9. Tracing, metrics và log tập trung

Một hệ thống microservices thường kết hợp Spring Boot Actuator, Micrometer Observation/Tracing, OpenTelemetry, API gateway và backend thu log. Các công cụ này có thể tạo **bản sao dữ liệu request** ngoài ứng dụng chính.

### 9.1. Span attributes nào nên và không nên thu?

| Nhóm dữ liệu | Ví dụ nên cân nhắc | Ví dụ nên tránh |
|---|---|---|
| HTTP | Method, route template, status, latency | Full request URI có query credential |
| Service | Service name, environment, operation name | Thông tin hạ tầng bí mật không cần thiết |
| Request correlation | Trace ID, span ID, request ID | Raw Bearer token hoặc hash token không được phê duyệt |
| Authentication outcome | `authenticated` / `invalid_token` / `insufficient_scope` (phân loại giới hạn) | Toàn bộ `Authentication`/`Jwt`/`getClaims()` |
| Identity | Mã actor nội bộ đã được phê duyệt trong audit sink hạn chế | Email, phone, raw subject trong trace công khai |
| Authorization | Rule/category như `orders.read` khi policy cho phép | Toàn bộ nhóm/role claim hoặc bản ghi nhạy cảm |

Các giá trị **high-cardinality** như email, raw subject, `jti`, token value không nên làm metric label. Ngoài quyền riêng tư, một chuỗi mới cho mỗi request có thể làm tăng lớn số series trong time-series storage.

### 9.2. Tracing baggage có thể lan qua services

Khác với một biến local trong JVM, **baggage** trong distributed tracing có thể được đưa vào HTTP headers khi gọi downstream. Một số công cụ còn đưa baggage vào span events/logs. Vì vậy:

~~~text
Được cân nhắc:
  trace ID được tạo bởi hệ thống
  operation name chuẩn hóa

Không đưa vào baggage:
  access token
  refresh token
  client secret
  email, phone
  raw JWT claims
~~~

Nếu nghiệp vụ cần truyền identity đến downstream, sử dụng **mô hình xác thực được thiết kế cho service-to-service**: access token phù hợp audience downstream, token exchange hoặc một cơ chế danh tính nội bộ đã được xác thực. Đừng truyền identity bằng một header `X-User` tùy ý rồi coi đó là chứng cứ xác thực ở mọi service.

### 9.3. Tránh phản ánh token qua error tracker

Một số SDK error monitoring tự động lấy request headers, query parameters, body hoặc breadcrumbs. Cần cấu hình:

- Bỏ `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie` và API-key headers.
- Bỏ parameter `access_token`, `id_token`, `refresh_token`, `client_secret` và các tên credential tương đương.
- Không tự thu toàn bộ local variables của controller/decoder/exception.
- Redact trước khi gửi dữ liệu ra backend APM, không chỉ dùng quy tắc lọc khi người dùng xem dashboard.
- Giới hạn retention/quyền truy cập và có quy trình xử lý sự cố nếu phát hiện leak.

Một token có thể xuất hiện ở tên parameter khác do client sai giao thức; vì thế mô hình **allowlist dữ liệu quan sát** an toàn hơn việc chỉ duy trì denylist tên trường.

## 10. Nguy cơ ở gateway, proxy và CDN

Resource Server thường đứng sau load balancer, API gateway, reverse proxy hoặc service mesh. Những lớp này có thể thấy Bearer header **trước khi** Spring Security kiểm tra token.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway/Ingress
    participant R as Spring Security Resource Server
    participant L as Log/Telemetry Storage
    C->>G: Authorization: Bearer <token>
    Note over G: Auth header không được ghi vào access log
    G->>R: Forward request theo policy
    R->>R: Xác minh token, tạo principal
    R-->>G: Response DTO tối thiểu
    G-->>C: HTTP response không chứa token
    G-->>L: Method, route, status, request ID
    R-->>L: Event category, trace ID, status
~~~

Cần kiểm tra riêng:

- **Access logs** có in `$http_authorization`, `%{Authorization}i` hoặc trường tương đương không.
- **Request mirroring** có sao chép headers/requests đến môi trường kiểm thử không.
- **API analytics** có lưu full URL/query string, request body hay cookie không.
- **Error pages** do gateway tạo có echo request header/query/body hoặc diagnostic dump không.
- **WAF/security event** có lưu token trong payload mẫu không; nếu cần giữ chứng cứ sự cố, phải bảo vệ quyền truy cập, retention và token revocation.
- **Cache HTTP response** có vô tình cache nội dung cá nhân hóa theo principal và trả cho caller khác không.

### 10.1. Không cache phản hồi người dùng giữa các danh tính

Một endpoint `GET /api/me` hoặc `GET /api/orders` có dữ liệu cá nhân hóa. Ngoài việc không echo token, phải tránh cache shared/CDN trả nhầm nội dung của người dùng A cho người dùng B. Với dữ liệu riêng tư, nên thiết kế cache policy rõ ràng; có thể dùng:

~~~http
Cache-Control: private, no-store
~~~

Đó là ví dụ chính sách hạn chế lưu dữ liệu response. **Không áp `no-store` một cách máy móc cho mọi tài nguyên public**, nhưng response liên quan identity/token nên có quyết định cache phù hợp với mức độ nhạy cảm và kiến trúc gateway. Cũng không nên ghi access token vào cache key công khai hoặc nhãn cache metric.

### 10.2. Redaction không được dựa trên một định dạng token

JWT có thể nhìn như ba phần phân cách bằng dấu chấm, opaque token có thể là chuỗi bất kỳ. Đừng chỉ redact chuỗi trông như JWT:

~~~text
JWT:    xxxxx.yyyyy.zzzzz
Opaque: opa_7e0d... (minh họa)
~~~

Chính sách nên dựa trên **vị trí/ý nghĩa dữ liệu**, ví dụ `Authorization` header hoặc form field `token` của introspection. Mặt khác, credential có thể xuất hiện trong payload JSON có field tùy biến; cần phát hiện ở ranh giới ứng dụng theo hợp đồng hoặc tránh body logging ngay từ đầu.

## 11. Outbound token và introspection credentials

Resource Server có thể gọi Authorization Server hoặc các API downstream. Đây là nơi dữ liệu có chủ đích **được truyền đến bên nhận hợp lệ**, nhưng không được xuất hiện trong phản hồi hoặc nhật ký.

### 11.1. Opaque token introspection

Mẫu HTTP:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.test
Authorization: Basic <ENCODED_RESOURCE_SERVER_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<ACCESS_TOKEN>&token_type_hint=access_token
~~~

Phải bảo vệ **cả token cần introspect lẫn introspection client credentials**. Cụ thể:

- Không log `Authorization: Basic ...`: Base64 không phải mã hóa bảo mật.
- Không log form body có tham số `token` hoặc `client_secret`.
- Không log full response introspection nếu nó chứa subject/email/metadata nhạy cảm.
- Không đưa raw response introspection vào HTTP response của Orders API.
- Dùng HTTPS, endpoint tin cậy và secret manager.
- Với lỗi introspection (401/403 upstream, 5xx, timeout), chỉ ghi loại lỗi và request ID; không đưa credential vào exception diagnostics.

Ví dụ một bộ logger HTTP tùy chỉnh chỉ ghi:

~~~text
event=introspection_call outcome=success latency_bucket=under_100ms
event=introspection_call outcome=authentication_error latency_bucket=under_100ms
event=introspection_call outcome=timeout latency_bucket=over_500ms
~~~

Các khoảng độ trễ trên chỉ là ví dụ phân nhóm, không phải SLO mặc định. Một kết quả introspection `active=false` cũng không cần đi kèm raw token trong log để ứng dụng quyết định từ chối.

### 11.2. Gọi downstream API

Trong một thiết kế microservice hợp lệ, việc gắn Bearer token vào **request outbound gửi đến đúng Resource Server** có thể là cần thiết. Tuy nhiên:

1. Chỉ dùng token hợp lệ cho **audience** của downstream API.
2. Nếu token inbound dành cho Orders API, không tự động chuyển nguyên token đó cho Billing API. Có thể cần token exchange hoặc lấy token mới theo hợp đồng.
3. Không log request outbound đã gắn `Authorization`.
4. Không đưa token outbound vào body, query, exception, response gửi về caller hoặc tracing baggage.
5. Không dùng cùng client secret hoặc service credential cho mọi môi trường.

**“Không log token” không đồng nghĩa “không bao giờ gửi token qua mạng”.** Credential vẫn phải được trình đến đích được phép để thực hiện xác thực; chính sách ở đây ngăn **tiết lộ ngoài luồng được ủy quyền**.

### 11.3. Phân biệt access token và OIDC ID token

Một OIDC client nhận ID token để xác minh thông tin về lần đăng nhập, không phải để tùy tiện gọi mọi Resource Server. Nếu một dịch vụ “debug” echo ID token, nó có thể rò rỉ claims danh tính, đồng thời khuyến khích client dùng sai token type.

Đối với API Resource Server:

~~~text
Client → API:
  Authorization: Bearer <ACCESS_TOKEN_F0R_API>

API → Client:
  Response DTO nghiệp vụ
  KHÔNG: raw access token
  KHÔNG: ID token / refresh token
  KHÔNG: toàn bộ Jwt/Authentication
~~~

Một số endpoint Authorization Server/token endpoint **có chức năng phát hành token** và tất nhiên phải trả token theo OAuth 2.0 protocol. Bài học này dành cho **Resource Server/API nghiệp vụ**, không phủ nhận chức năng phát hành token hợp lệ của một Authorization Server.

## 12. Hạn chế thông tin nhạy cảm trong audit và debugging

Giám sát bảo mật có thể cần biết “ai đã gọi thao tác nào” hoặc “vì sao bị từ chối”. Tuy nhiên, audit và debugging cũng phải có mục đích, quyền truy cập và thời hạn lưu giữ.

### 12.1. Ba cấp độ dữ liệu vận hành

| Cấp độ | Nên lưu | Tránh |
|---|---|---|
| **Operational metrics** | Số request 401/403, error category, latency, service/route chuẩn hóa | Raw tokens, user/email identifiers làm label |
| **Application logs** | Request ID, event name, status, operation category | Full `Authentication`, headers, claims, body chứa secret |
| **Restricted security audit** | Actor ID tối thiểu, thời gian, mục đích, resource ID theo chính sách, outcome | Raw credential; thông tin không liên quan đến điều tra |

Nếu cần liên kết actor identity với audit:

- Chọn identity key nhất quán theo **issuer + subject + tenant** khi hợp đồng yêu cầu, không mặc nhiên lấy username.
- Bảo vệ audit sink bằng RBAC, encryption at rest/in transit, retention và audit truy cập audit.
- Không sao chép audit metadata sang public log/traces chỉ vì tiện correlation.
- Với tenant hoặc email, cân nhắc mã định danh nội bộ hoặc pseudonymization theo yêu cầu riêng tư.
- Không dùng raw `jti`/access token làm actor key phổ biến cho application metrics.

### 12.2. Không nhúng credential vào message rồi chờ redaction regex

Phản ví dụ:

~~~java
// PHẢN VÍ DỤ:
log.warn("Failed token {} for user {}", token, email);
~~~

Một biểu thức chính quy thay thế token sau đó có thể bỏ sót opaque token, token bị cắt, header format khác hoặc Unicode/encoding khác. Tốt hơn:

~~~java
log.warn("event=authentication_rejected reason=invalid_token");
~~~

Nếu log event cần request/trace ID, lấy từ nguồn tin cậy; nếu cần danh mục lỗi chi tiết, dùng enum/constant đã giới hạn, không đưa nguyên exception/claims vào event.

### 12.3. Môi trường development và staging cũng phải được bảo vệ

Không nên bật full HTTP dumps trong development rồi chuyển cùng cấu hình sang staging/production. Đặc biệt:

- Developer có thể dùng token thật để test nhầm môi trường.
- Dữ liệu staging đôi khi được sao chép từ production, tạo thêm rủi ro PII.
- Build logs và crash reports có thể được lưu lâu hơn log production.
- Hệ thống hỗ trợ khách hàng có thể chứa request mẫu được copy từ browser DevTools.

Ưu tiên fake tokens, test issuer và keys riêng cho môi trường thử nghiệm. Nếu lỡ đưa credential thật vào log hoặc ticket, hãy coi đó là sự cố cần đánh giá thu hồi/rotation, không chỉ xóa dòng log trên màn hình.

## 13. Kiểm tra response và log bằng test không chứa credential thật

Một API có thể hoạt động đúng về authentication và authorization nhưng vẫn lộ token qua serialization/logging. Vì vậy nên có **những tình huống kiểm thử tiết lộ dữ liệu**, phân biệt với kiểm thử chữ ký JWT.

### 13.1. Ma trận tình huống cần bao phủ

| Tình huống | Bề mặt cần quan sát | Kỳ vọng |
|---|---|---|
| GET `/api/me` với JWT giả lập có email và scope | Response JSON | Chỉ có các field DTO được phép; không có raw token hoặc claim email không được chọn |
| GET protected API với JWT invalid | Error response | Có 401/Bearer challenge hợp lệ; không echo Authorization |
| GET protected API với JWT valid nhưng thiếu scope | Response 403 | Không chứa full claims, credentials hoặc exception stack trace |
| Opaque introspection `active=true` | API response và log | Không expose introspection response hay Basic credentials |
| Introspection trả 401 hoặc timeout | Outbound log và API error | Không log form `token` hoặc client secret; request không được xác thực |
| JWT decoder nhận token sai chữ ký | Application log/APM | Không log token/JWS payload; ghi lỗi ở mức category được phép |
| Client gửi token qua query sai cách | Gateway/access log | Không lưu query credential; API không nhận token qua con đường không được cho phép |
| Custom exception từ service | Error body và logs | Không trả `exception.getMessage()` chứa dữ liệu nhạy cảm |
| Bật HTTP DEBUG trong môi trường test | Framework/HTTP client logs | Không làm xuất hiện token/header nhạy cảm |
| Request đi qua proxy/CDN | Access logs và response headers | Header credential không bị log/echo; response user riêng không bị shared cache nhầm |
| Trace xuyên service | Span/baggage | Không có token, email/PII không được chấp thuận |
| Test/CI thất bại | Build output | Không dump credential thật vào stdout/stderr/artifact |

### 13.2. Test DTO bằng `MockMvc` và token giả lập

Giả sử ứng dụng có controller `/api/me` chỉ trả `MeResponse(displayName, accountType)` ở phần 3. Có thể dùng Spring Security Test với post processor `jwt()` để tạo authentication thử nghiệm.

Dependency test:

~~~gradle
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MeResponsePrivacyTest {

    @Autowired
    MockMvc mvc;

    @Test
    void meDoesNotEchoCredentialOrPrivateClaims() throws Exception {
        String fakeToken = "test-only-not-a-real-access-token";
        String privateEmail = "private-person@example.test";

        String json = mvc.perform(
                get("/api/me")
                    .with(jwt().jwt(builder -> builder
                        .tokenValue(fakeToken)
                        .claim("sub", "user-123")
                        .claim("preferred_username", "Example User")
                        .claim("email", privateEmail)
                        .claim("scope", "profile")
                    ))
            )
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        assertThat(json).contains("Example User");
        assertThat(json).doesNotContain(fakeToken);
        assertThat(json).doesNotContain(privateEmail);
        assertThat(json).doesNotContain("scope");
    }
}
~~~

Đây là ví dụ test **response mapping** và yêu cầu setup test MVC thực sự có endpoint `/api/me`. `jwt()` dựng authentication mô phỏng: **nó không chạy chữ ký/JWK validation thật**. Vì thế cần có test decoder/security chain riêng nếu muốn chứng minh issuer/audience/time được xác thực đúng.

Đối với opaque token, có thể dùng hỗ trợ test `opaqueToken()` hoặc stub introspection endpoint để kiểm tra response mapping; không gửi raw opaque token production vào test.

### 13.3. Test sự vắng mặt của token trong application logs

Spring Boot Test có `OutputCaptureExtension` để thu stdout/stderr của test. Ví dụ một test tích hợp có thể kiểm tra chuỗi giả lập **không xuất hiện** trong nội dung được thu:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

@ExtendWith(OutputCaptureExtension.class)
class SafeLoggingExampleTest {

    @Test
    void loggingDoesNotContainCredential(CapturedOutput output) {
        String fakeCredential = "fake-token-for-test-only";

        // Tại đây gọi đường xử lý ứng dụng với fakeCredential
        // bằng setup test phù hợp, không dùng credential thật.

        assertThat(output.getOut()).doesNotContain(fakeCredential);
        assertThat(output.getErr()).doesNotContain(fakeCredential);
    }
}
~~~

Phần comment phải được thay bằng một request/operation thực tế trong bài test của dự án, nếu không kiểm tra trên chỉ là minh họa. `OutputCaptureExtension` **không chứng minh mọi nơi lưu log đều an toàn**: nó không tự thu gateway logs, APM events, remote collector hoặc tất cả appender/async sink. Nên kết hợp test tại những tầng nhận dữ liệu.

### 13.4. Test serialization với một canary không phải token thật

Một kỹ thuật hữu ích là tạo giá trị giả có hình dạng dễ nhận biết như:

~~~text
LEAK-CANARY-ACCESS-TOKEN-DO-NOT-USE-001
LEAK-CANARY-EMAIL@example.test
~~~

Đưa canary vào các thuộc tính giả lập và theo dõi liệu nó có xuất hiện ở **response, application log, proxy log, trace, error tracker** hay không. Tuy nhiên đừng dùng chuỗi mang ý nghĩa credential thật hoặc đặt canary trong nơi mà policy yêu cầu log body. Canary chỉ kiểm tra được những đường thực sự được exercise; nó không thay thế review cấu hình logger/telemetry.

### 13.5. Negative tests nên kiểm tra điều gì?

Ngoài việc bảo đảm token hợp lệ dẫn đến response đúng, nên kiểm tra:

- Không có `Authorization` ở API bảo vệ → 401; body không chứa raw header.
- Bearer credential sai → 401; log không chứa credential giả lập.
- Access token active nhưng thiếu scope → 403; response không có nguyên `Jwt` hoặc introspection attributes.
- Exception chứa chuỗi giả lập nhạy cảm → HTTP response không echo message nhạy cảm.
- Cấu hình HTTP client lỗi → error và log không chứa client secret/Basic header.
- Thay đổi tên/kiểu claim ở issuer → DTO không tự động xuất field mới ngoài contract.
- Client gửi Bearer ở vị trí không hỗ trợ → gateway vẫn không log query credential.

**Kiểm tra privacy có thể được tự động hóa như một phần kiểm thử API**, nhưng phải dùng dữ liệu giả lập và không lưu token production trong source code test hoặc kết quả CI.

## 14. Xử lý khi phát hiện access token đã xuất hiện trong log

Việc một token xuất hiện trong log không chỉ là “sai định dạng nhật ký”. Nếu token còn hiệu lực và log đã được truyền đến backend tập trung, một đối tượng không được phép có thể đã đọc credential.

Quy trình xử lý nên tách thành những quyết định:

### 14.1. Xác định phạm vi rò rỉ

Làm rõ:

1. **Loại token/credential nào** đã xuất hiện: access token, refresh token, ID token, Basic client secret, private key hay cookie?
2. Token thuộc issuer/resource nào và có khả năng còn hiệu lực không?
3. Log đã đến đâu: local console, container logs, collector, SIEM, APM, backup, ticket, CI artifact?
4. Ai có quyền truy cập và có dấu hiệu tải/xem/sao chép hay không?
5. Cấu hình nào đã tạo ra leak và có thể còn đang hoạt động?

Không copy nguyên token sang một ticket điều tra thứ hai để minh họa. Dùng incident ID, request ID hoặc metadata an toàn và quyền truy cập giới hạn.

### 14.2. Ngăn tiếp tục rò rỉ

Tắt body/header logging gây leak, sửa serialization hoặc exception handler, kiểm tra gateway/APM và rollout bản sửa phù hợp. Đừng chỉ ẩn một trường trong giao diện log viewer nếu collector vẫn nhận và lưu raw credential.

Nếu secret đã phát tán, cần phối hợp đội Identity/Security để cân nhắc:

- **Thu hồi/revoke access token** nếu có cơ chế và theo đánh giá rủi ro.
- **Thu hồi refresh token** và các phiên liên quan khi phù hợp.
- **Rotate client secret, introspection credentials hoặc signing keys** nếu chính những loại secret đó bị lộ. Việc đổi signing key là biện pháp ảnh hưởng rộng, cần incident policy rõ ràng.
- Giới hạn quyền của credential còn hoạt động và theo dõi dấu hiệu sử dụng bất thường.
- Thực hiện thông báo/sự kiện tuân thủ theo quy định của tổ chức nếu dữ liệu cá nhân cũng bị lộ.

### 14.3. Xử lý dữ liệu đã lưu và ngăn tái diễn

Xác định nơi phải xóa, khoanh vùng, đặt thời hạn lưu hoặc giảm quyền truy cập; lưu ý log đã được replica hoặc backup có thể không biến mất chỉ vì xóa một bản. Sau khi sửa, dùng fake credential/canary để kiểm tra đường leak đã ngừng, và đưa trường hợp đó vào test/config review để tránh tái diễn.

**Không coi token hết hạn là bằng chứng sự cố không còn tác động**: access log có thể chứa PII, client secret hoặc thông tin về hệ thống vẫn hữu ích cho attacker sau khi JWT hết hạn.

## 15. Checklist thiết kế một endpoint dùng principal

Trước khi đưa một API ra production, có thể tự trả lời:

| Câu hỏi | Quyết định mong muốn |
|---|---|
| API thực sự cần trả field nào từ identity? | DTO có danh sách field rõ ràng |
| Có trả `Jwt`, `Authentication` hoặc introspection response trực tiếp không? | **Không** |
| DTO có tự động thay đổi khi issuer thêm claim không? | **Không**; thay contract phải được review |
| Có field nào là email, phone, subject, tenant, group, role không? | Chỉ sử dụng khi cần và caller được phép |
| Request/response được log ở đâu? | Có danh mục sink và redaction tại nguồn |
| Gateway có thể log `Authorization` hoặc query không? | Không thu credential |
| HTTP client outbound có wiretap/full body logging không? | Không thu token hoặc secret |
| Exception handler có trả `getMessage()`/stacktrace không? | Không đưa nội dung nội bộ ra client |
| APM có thu headers/body/baggage không? | Đã kiểm soát field nhạy cảm |
| Có dùng token, `sub`, email làm metric labels không? | Không cho metric chung; audit actor ID phải có policy riêng |
| Có request ID/trace ID độc lập với token không? | Có, với cơ chế tạo và quản lý an toàn |
| Có test response/log với fake credential không? | Có các trường hợp xác thực thành công/thất bại |
| Khi token leak, có quy trình revoke/rotation không? | Có quyền sở hữu và phương án thực thi |

### 15.1. Lựa chọn mặc định an toàn cho API nghiệp vụ

Đối với **Orders API**:

~~~text
Input:
  Authorization: Bearer <access_token>

Authentication:
  JwtDecoder / OpaqueTokenIntrospector
  → principal & GrantedAuthority

Authorization:
  scope / role / tenant / owner policy

Output:
  OrderResponse {
    id,
    status,
    createdAt,
    ... field nghiệp vụ được phép
  }

Application logs:
  event, outcome, requestId, duration

Không output/log:
  token value, Authorization, refresh token, client secret,
  nguyên Jwt/Authentication, arbitrary claims, stacktrace nhạy cảm
~~~

Việc trả một `OrderResponse` vẫn phải tuân thủ quyền truy cập từng bản ghi; chỉ loại token khỏi JSON **không tự đảm bảo** dữ liệu nghiệp vụ đã đúng tenant/owner.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Resource Server đã xác thực JWT thành công thì trả thẳng `Jwt` cho client được không?

**Không nên.** `Jwt` chứa token value và claims mà client có thể không được phép nhận. Hãy tạo DTO với field được lựa chọn rõ ràng.

**Câu 2.** `authentication.getName()` có luôn là dữ liệu công khai không?

**Không.** Giá trị này có thể là `sub`, username hoặc định danh khác theo cấu hình. Nó có thể là PII hoặc định danh nội bộ; việc trả ra phải dựa trên hợp đồng API.

**Câu 3.** Có thể log `Authorization: Bearer ...` để debug 401 không?

**Không.** Nên log loại lỗi, request/trace ID, trạng thái và metadata đã được phê duyệt. Raw token có thể được sử dụng như credential trong thời gian còn hiệu lực.

**Câu 4.** Nếu token là opaque string không đọc được thì có an toàn để log không?

**Không.** Opaque token vẫn là bearer credential. Không cần có cấu trúc JWT để trở thành dữ liệu nhạy cảm.

**Câu 5.** Chỉ bật `server.error.include-stacktrace=never` đã đủ chưa?

**Chưa.** Security filters, custom exception handler, access logs, outbound HTTP logging, gateway, APM và tracing có thể rò rỉ độc lập.

**Câu 6.** Vì sao không dùng token làm correlation ID?

Vì token là credential. Đưa nó vào MDC/log/trace/baggage làm token phát tán qua nhiều hệ thống và tăng phạm vi rủi ro. Hãy dùng request ID/trace ID được tạo riêng.

**Câu 7.** Một service cần gọi downstream có được gửi Bearer token không?

Có khi hợp đồng cho phép và token dành đúng audience downstream, nhưng chỉ gửi tới endpoint được phép qua kênh bảo mật; **không echo token trong response hoặc ghi log**, và không tự chuyển tiếp inbound token có audience sai.

**Câu 8.** Khi kiểm thử với `jwt()` trong Spring Security Test, có chứng minh decoder thật không làm lộ token không?

Không đầy đủ. Post processor này thường mock kết quả xác thực và bỏ qua JWS validation thật. Nó giúp kiểm tra DTO/security rules, còn logging/gateway và decoder thật cần những kiểm tra riêng với dữ liệu giả lập.

## 17. Kết luận

Resource Server phải dùng principal và access token để **xác thực và áp quyền**, nhưng không vì thế mà gửi mọi thông tin xác thực cho client hoặc lưu chúng vào log:

1. **Credential không phải dữ liệu response.** Raw access token, refresh token, ID token, client secret và Authorization headers không xuất hiện trong JSON nghiệp vụ.
2. **Principal không phải DTO.** Đọc những thuộc tính đã xác thực mà service cần, sau đó trả một DTO có field được phép; không serialize nguyên `Jwt`, `Authentication` hoặc `OAuth2AuthenticatedPrincipal`.
3. **Logging theo allowlist.** Ghi event name, outcome, request/trace ID và metric chuẩn hóa thay vì raw headers, token, arbitrary claims hoặc exception dump.
4. **Bảo vệ xuyên các tầng.** Servlet/WebFlux, gateway, HTTP client, introspection, distributed tracing, error tracker và CI đều có khả năng ghi dữ liệu nhạy cảm.
5. **Kiểm thử và ứng cứu.** Dùng fake credentials để kiểm tra response/log, đồng thời chuẩn bị quy trình xác định phạm vi và thu hồi credential khi phát hiện leak.

Quy tắc dễ ghi nhớ:

~~~text
Nhận token → xác minh → xây principal → phân quyền
          → chọn field nghiệp vụ được phép → trả DTO tối thiểu

Log/trace:
  requestId + event + outcome + status

KHÔNG:
  echo token, serialize security context,
  log Authorization headers, dump claims,
  đặt bearer credential vào baggage/metrics
~~~

**Giữ dữ liệu token nhạy cảm ngoài phản hồi API và nhật ký là một phần của hợp đồng bảo mật**, không chỉ là một mẹo cấu hình logger. Spring Security giúp API xác định danh tính và quyền; ứng dụng vẫn phải chủ động kiểm soát dữ liệu nào rời khỏi request processing qua JSON, telemetry và hệ thống vận hành.

## Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Servlet Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [OWASP Cheat Sheet — Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Cheat Sheet — REST Security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
