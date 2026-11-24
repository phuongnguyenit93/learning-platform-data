# Audit quyết định tại method boundary trong Spring Security

**Chương:** Method security  
**Chủ đề:** Audit quyết định tại method boundary  
**Phạm vi:** SECURITY_TOKEN_SECURITY_FUNDAMENTALS — mô hình tin cậy và vòng đời token bảo mật; JWT, opaque token, access token, refresh token; xác thực, phân quyền, OAuth 2.0/OIDC; kiểm tra claims, scope, audience, lưu trữ, thu hồi và chống token bị đánh cắp/phát lại.

## 1. Tại sao cần audit ngay ở method boundary?

Trong Spring Security, một HTTP request có thể đi qua nhiều tầng trước khi gọi đến nghiệp vụ: bộ lọc xác thực bearer token, kiểm tra quyền ở endpoint, controller, service, repository và database. **Method boundary** là ranh giới trước hoặc sau khi gọi một phương thức ứng dụng, nơi **method security** có thể đưa ra quyết định cho phép hoặc từ chối dựa trên principal, authorities, tham số và đối tượng kết quả.

Ví dụ: người dùng có scope đọc đơn hàng, nhưng chỉ được xem đơn hàng của tenant A. API **GET /api/tenants/tenant-b/orders/123** có thể vượt qua kiểm tra HTTP sơ bộ yêu cầu xác thực, rồi bị từ chối tại **OrderService.readOrder(...)** vì tenant không khớp.

Nếu hệ thống chỉ ghi **HTTP 403**, người vận hành chưa biết chính sách nào từ chối, hành động được yêu cầu là gì và quyết định xảy ra ở service nào. Ngược lại, ghi log mọi lần gọi method mà không ghi trạng thái của phép kiểm tra quyền sẽ không tạo ra được audit trail phân quyền có giá trị.

**Audit quyết định tại method boundary** là ghi lại một sự kiện có cấu trúc thể hiện:

- **Ai** đang yêu cầu: chủ thể đã được xác thực, client hoặc service account (theo dữ liệu được xác thực).
- **Muốn làm gì**: tên hành động nghiệp vụ và tài nguyên đích.
- **Ở đâu**: tenant, method hoặc mã chính sách được áp dụng.
- **Kết quả kiểm tra quyền**: **PERMIT** hay **DENY**, kèm mã lý do an toàn.
- **Bằng ngữ cảnh nào**: thời điểm, request/trace ID, nguồn xác thực và phiên bản policy nếu có.

Audit cho phép điều tra truy cập trái phép, xác minh chính sách least privilege, đối chiếu thay đổi quyền theo vòng đời token và phát hiện các dấu hiệu dùng token bị đánh cắp hoặc phát lại. Tuy nhiên, **audit không thay thế bước thực thi phân quyền**: nếu quyết định là DENY thì lời gọi phải thực sự bị chặn.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **quyết định phân quyền**, **kết quả thực thi nghiệp vụ** và **kết quả HTTP**.
2. Nhận diện vị trí Spring Security thực thi **@PreAuthorize** và **@PostAuthorize**; xác định được những trường hợp không đi qua method interceptor.
3. Thiết kế một **authorization decision event** có đủ ngữ cảnh nhưng không rò rỉ token hoặc dữ liệu cá nhân không cần thiết.
4. Triển khai ghi nhận cả **PERMIT** lẫn **DENY** trong một chính sách method security; xử lý đúng quan hệ giữa claim tenant và authority.
5. Kiểm thử audit cho trường hợp token không hợp lệ, sai quyền, truy cập chéo tenant, lỗi nghiệp vụ và thay đổi quyền.

## 2. Phân biệt ba loại kết quả dễ bị nhầm

Giả sử lời gọi **OrderService.readOrder("tenant-a", id)** được phép chạy theo chính sách. Sau đó repository không tìm thấy bản ghi. Điều này tạo ra:

| Khía cạnh | Kết quả | Diễn giải |
|---|---|---|
| Authentication | Thành công | Access token hợp lệ đối với API |
| Authorization decision | **PERMIT** | Người dùng có quyền đọc trong tenant-a |
| Business outcome | **NOT_FOUND** | Không có đơn hàng với ID được yêu cầu trong tenant-a |
| HTTP response | 404 | Phản hồi từ controller/API, không đồng nghĩa bị từ chối quyền |

Một ví dụ khác: token có **tid = tenant-a** nhưng request muốn truy cập **tenant-b**.

| Khía cạnh | Kết quả | Diễn giải |
|---|---|---|
| Authentication | Thành công | Token được xác thực |
| Authorization decision | **DENY** | Policy chặn vì tenant không khớp |
| Business outcome | **NOT_EXECUTED** | Nghiệp vụ chưa được gọi |
| HTTP response | Thường 403 | Đã xác thực nhưng không đủ quyền |

Ngược lại, nếu JWT hết hạn hoặc sai audience, Resource Server từ chối token **trước khi gọi service**. Khi đó thường trả về **401 Unauthorized** và **không tồn tại authorization decision tại method boundary**. Muốn có nhật ký đầy đủ của toàn hệ thống phải kết hợp audit xác thực ở filter/resource server với audit phân quyền ở method.

**Quy tắc quan trọng:** Không suy ra **PERMIT** chỉ vì API trả 200, không suy ra **DENY** chỉ vì API trả 403 và không coi một ngoại lệ nghiệp vụ là kết quả của kiểm tra quyền. Mỗi nguồn sự kiện phải ghi đúng điều mà nó thực sự quan sát.

## 3. Vị trí kiểm tra và ghi audit trong luồng bảo mật token

~~~mermaid
flowchart TD
    C[Client gọi API cùng access token] --> A[Bearer token authentication]
    A --> B{Xác thực và validate token?}
    B -->|Không| U[401 + authentication audit]
    B -->|Có| H[HTTP authorization]
    H -->|Từ chối| X[403 + HTTP authorization audit]
    H -->|Cho phép| M[Controller gọi Spring-managed service proxy]
    M --> P{Method authorization policy}
    P -->|DENY| D[Ghi decision=DENY]
    D --> F[Chặn lời gọi - thường 403]
    P -->|PERMIT| G[Ghi decision=PERMIT]
    G --> S[Thực thi service]
    S --> R[Repository lọc theo tenant]
    R --> O[Business result / lỗi nghiệp vụ]
~~~

**Method boundary** thường nằm ở Spring AOP proxy bọc method được bảo vệ, không nhất thiết trùng với điểm vào HTTP. Một service cũng có thể được gọi từ scheduled job, messaging consumer hoặc service khác: nếu lời gọi đi qua proxy và có security context phù hợp, quy tắc method security vẫn được áp dụng.

Với Spring Security 6, **@EnableMethodSecurity** kích hoạt cơ chế dùng các authorization interceptor/manager cho các annotation tương ứng. Các cơ chế thường gặp:

| Cơ chế | Thời điểm kiểm tra | Audit cần lưu ý |
|---|---|---|
| **@PreAuthorize** | Trước khi thực thi method | Phù hợp để chặn trước các thao tác đọc/ghi có kiểm tra quyền |
| **@PostAuthorize** | Sau khi method trả kết quả, trước khi trả về cho caller | Có thể kiểm tra quyền dựa trên **returnObject**, nhưng nghiệp vụ đã được thực thi |
| **@PreFilter** | Lọc tham số collection trước khi thực thi | Cần phân biệt phép lọc phần tử với quyết định cho phép chạy method |
| **@PostFilter** | Lọc collection kết quả | Không được diễn giải phần tử bị loại là một HTTP 403 |
| **@Secured**, **JSR-250** | Kiểm tra quyền theo annotation tương ứng | Không tự cung cấp đủ ngữ cảnh tenant hoặc reason code nghiệp vụ |

Đối với hành động **thay đổi trạng thái hoặc có side effect**, ưu tiên kiểm tra trước khi thực hiện. Nếu chỉ đặt **@PostAuthorize** sau lệnh chuyển tiền, gửi email hoặc cập nhật dữ liệu, một kết quả DENY đến muộn không đảm bảo đảo ngược được tác động đã xảy ra.

### 3.1. Method security và HTTP security bổ sung cho nhau

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders/**").authenticated()
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Ví dụ dùng Spring Security 6 / Spring Boot 3 và cần các import **@Configuration**, **@Bean**, **@EnableMethodSecurity**, **HttpSecurity**, **SecurityFilterChain**, **Customizer** theo package tương ứng. Cấu hình minh họa giả định đã có **JwtDecoder** tin cậy, xác minh chữ ký, issuer, thời gian hợp lệ và kiểm tra **audience** dành cho API. Định nghĩa HTTP ở đây chỉ yêu cầu người gọi đã xác thực; **service** sẽ quyết định quyền cụ thể hơn.

**@EnableMethodSecurity** không khiến mọi method trong ứng dụng đều được audit tự động. Chỉ những method có chính sách tương ứng và các lời gọi thực sự đi qua Spring proxy hoặc cơ chế interceptor được cấu hình mới được đánh giá tại ranh giới này.

## 4. Thiết kế schema của authorization decision event

Sự kiện nên có **cấu trúc ổn định**, có mã thay cho chuỗi diễn giải tự do, đủ để lọc/cảnh báo và đối chiếu với trace mà không cần đọc token gốc.

Ví dụ:

~~~json
{
  "event_type": "METHOD_AUTHORIZATION_DECISION",
  "occurred_at": "2026-11-23T03:25:00Z",
  "correlation_id": "req-7a2c",
  "trace_id": "trace-c91e",
  "service": "orders-api",
  "policy_id": "order.read.v1",
  "method": "OrderService.readOrder",
  "action": "orders.read",
  "subject_id": "user-123",
  "client_id": "portal-web",
  "tenant_id": "tenant-b",
  "resource_type": "order",
  "resource_id": "order-456",
  "decision": "DENY",
  "reason_code": "TENANT_MISMATCH",
  "token_type": "access_token",
  "issuer_id": "company-idp",
  "audience_check": "PASSED"
}
~~~

Đây là **schema minh họa**, không phải định dạng sự kiện mặc định Spring Security. Các trường bổ sung phải lấy từ nguồn hợp lệ:

| Trường | Ý nghĩa | Lưu ý |
|---|---|---|
| **occurred_at** | Thời điểm quyết định, nên dùng UTC | Dùng timestamp server; không lấy thời gian từ client |
| **service / method / policy_id** | Vị trí thực thi chính sách | Policy ID ổn định tốt hơn phụ thuộc hoàn toàn vào tên method có thể refactor |
| **subject_id / client_id** | Chủ thể và OAuth client đã được xác thực | Không ghi email, tên, số điện thoại nếu không cần |
| **tenant_id** | Tenant được yêu cầu hoặc tenant đã xác nhận theo hợp đồng schema | Đặt tên rõ nếu lưu cả **requested_tenant_id** và **token_tenant_id** |
| **resource_type / resource_id** | Loại tài nguyên, định danh mục tiêu | Có thể cần pseudonymize/hash nếu nhạy cảm; tránh toàn bộ object |
| **decision** | **PERMIT**, **DENY** hoặc trạng thái được định nghĩa riêng | Không trộn với **BUSINESS_FAILED** hoặc lỗi hệ thống |
| **reason_code** | Mã ngắn: **MISSING_PERMISSION**, **TENANT_MISMATCH**, **POLICY_DENIED** | Mã nội bộ không nhất thiết phải trả cho client |
| **correlation_id / trace_id** | Liên kết với request và distributed tracing | Kiểm soát nguồn request ID để tránh log injection |
| **issuer_id / audience_check** | Thông tin xác thực token đã được kiểm tra | Không tự suy ra từ một JWT chưa validate |
| **policy_version** | Phiên bản rule khi có thay đổi chính sách | Hữu ích khi điều tra vì sao quyền thay đổi theo thời gian |

**Không ghi** access token, refresh token, mã authorization code, cookie phiên, API key, chữ ký JWT, toàn bộ payload JWT, thông tin bí mật hoặc dữ liệu nghiệp vụ không liên quan. Các claims như **jti**, **sub**, **sid** có thể mang tính định danh; chỉ ghi nếu mục đích điều tra thực sự cần, có kiểm soát truy cập/retention phù hợp và cân nhắc băm hoặc rút gọn.

Lý do từ chối nên dùng tập mã hữu hạn. Ví dụ **TENANT_MISMATCH** giúp nhóm bảo mật nhận ra truy cập chéo tenant, trong khi thông báo trả cho client có thể chỉ là **Access denied** để không tiết lộ quá nhiều về policy hoặc trạng thái membership.

## 5. Ví dụ Spring Security: audit cả PERMIT và DENY tại method

Giả sử Authorization Server cấp **JWT access token** cho **một tenant hiện hành**, với claim tùy biến **tid = tenant-a** và scope **orders.read**. Tại Resource Server, JWT đã được validate và scope được ánh xạ thành authority **SCOPE_orders.read**. Quy tắc đọc đơn hàng là:

> Chỉ cho phép khi principal được xác thực bằng JWT, tenant trên đường dẫn khớp với claim tid đã validate, và principal có authority SCOPE_orders.read.

Vì **SCOPE_orders.read** có thể là scope API chung, không được dùng riêng scope đó để kết luận người dùng có quyền với mọi tenant. Nếu hệ thống dùng opaque token, phải có cơ chế lấy tenant và authorities từ principal đã qua introspection; không dùng trực tiếp đoạn code dành riêng cho **JwtAuthenticationToken** bên dưới.

### 5.1. Định nghĩa event và điểm nhận audit

~~~java
import java.time.Instant;

public record MethodAuthorizationAuditEvent(
    Instant occurredAt,
    String policyId,
    String action,
    String subjectId,
    String requestedTenantId,
    String resourceId,
    String decision,
    String reasonCode,
    String correlationId
) {}

public interface MethodAuthorizationAuditSink {
    void record(MethodAuthorizationAuditEvent event);
}
~~~

**MethodAuthorizationAuditSink** là cổng giao tiếp do ứng dụng sở hữu. Lớp triển khai có thể gửi log JSON vào hệ thống tập trung, message queue hoặc kho audit có kiểm soát. Không đặt logic gọi API bên ngoài hoặc ghi database tốn thời gian trực tiếp trong SpEL; cần chọn phương thức ghi audit thích hợp với yêu cầu độ bền, hiệu năng và bảo vệ dữ liệu. Ví dụ dưới đây gọi **sink.record(...)** để thể hiện chính xác điểm phát sinh sự kiện.

### 5.2. Chính sách đánh giá đồng thời ghi nhận quyết định

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import org.slf4j.MDC;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("orderReadPolicy")
public class OrderReadPolicy {
    private final MethodAuthorizationAuditSink auditSink;

    public OrderReadPolicy(MethodAuthorizationAuditSink auditSink) {
        this.auditSink = auditSink;
    }

    public boolean allow(Authentication authentication,
                         String requestedTenantId, UUID orderId) {
        JwtAuthenticationToken jwt =
            authentication instanceof JwtAuthenticationToken token ? token : null;

        String tokenTenantId =
            jwt == null ? null : jwt.getToken().getClaimAsString("tid");

        boolean tenantMatches = jwt != null
            && tokenTenantId != null
            && !tokenTenantId.isBlank()
            && Objects.equals(tokenTenantId, requestedTenantId);

        boolean hasReadScope = jwt != null
            && jwt.getAuthorities().stream()
                .anyMatch(authority ->
                    "SCOPE_orders.read".equals(authority.getAuthority()));

        boolean permit = tenantMatches && hasReadScope;

        String reason = jwt == null ? "NO_VALID_JWT_CONTEXT"
            : !tenantMatches ? "TENANT_MISMATCH"
            : !hasReadScope ? "MISSING_PERMISSION"
            : "POLICY_PERMITTED";

        String subject = jwt == null ? "unknown" : jwt.getToken().getSubject();

        auditSink.record(new MethodAuthorizationAuditEvent(
            Instant.now(),
            "order.read.v1",
            "orders.read",
            subject,
            requestedTenantId,
            orderId == null ? null : orderId.toString(),
            permit ? "PERMIT" : "DENY",
            reason,
            MDC.get("correlationId")
        ));

        return permit;
    }
}
~~~

Trong thiết kế này, **một hàm chính sách** đánh giá toàn bộ điều kiện và phát ra **một sự kiện PERMIT hoặc DENY** cho mỗi lần được gọi. Vì policy nhận **Authentication** đã được Resource Server tạo, claim **tid** chỉ được tin sau khi JWT qua bước xác thực và validation ở tầng trước. Tên **order.read.v1** là ID quản trị policy do ứng dụng chọn.

**Lưu ý về phạm vi audit:** Sự kiện PERMIT được ghi **khi kiểm tra quyền cho phép đi tiếp**, trước khi gọi repository. Nó không khẳng định đã tìm thấy đơn hàng hoặc request xử lý thành công. Nếu policy bị bỏ qua (do thiếu interceptor, lời gọi trực tiếp không qua proxy) thì không có audit event. Nếu token bị chặn ở bộ lọc trước service thì cũng không gọi hàm policy này.

**Lưu ý về reason:** Với ví dụ, một token thiếu tid sẽ nhận **TENANT_MISMATCH**; trong hệ thống sản xuất có thể tách mã **TENANT_CONTEXT_MISSING** để giám sát chính xác hơn. Không dựa vào **authentication.getName()** nếu giá trị ấy chưa được chuẩn hóa thành mã chủ thể phù hợp.

### 5.3. Gắn policy vào service và ràng buộc truy vấn dữ liệu

~~~java
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderService {
    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @PreAuthorize(
        "@orderReadPolicy.allow(authentication, #tenantId, #orderId)"
    )
    public Order readOrder(@P("tenantId") String tenantId,
                           @P("orderId") UUID orderId) {
        return orderRepository.findByTenantIdAndId(tenantId, orderId)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Order not found"));
    }
}
~~~

**Order** và **OrderRepository** là các kiểu nghiệp vụ minh họa; repository cần cung cấp phương thức lọc bằng **tenantId** và **orderId**. Chú thích **@P** cho phép Spring Security phân giải **#tenantId** và **#orderId** ổn định khi biên dịch không giữ tên tham số.

Khi một phương thức khác cần quyền ghi, tạo policy phù hợp với **orders.write** và check cả tenant. Không copy đơn giản chính sách đọc rồi thay tên log mà quên cập nhật permission. Nếu request có **tenantId** từ URL, giá trị này là tenant **được yêu cầu**; phép so khớp với **tid** đã được xác thực vẫn bắt buộc.

| Bước | Tenant token | Tenant request | Authority | Audit | Kết quả method |
|---|---|---|---|---|---|
| Đọc hợp lệ | tenant-a | tenant-a | SCOPE_orders.read | PERMIT, POLICY_PERMITTED | Thực thi repository |
| Sai tenant | tenant-a | tenant-b | SCOPE_orders.read | DENY, TENANT_MISMATCH | Bị @PreAuthorize chặn |
| Thiếu scope | tenant-a | tenant-a | Không có scope đọc | DENY, MISSING_PERMISSION | Bị @PreAuthorize chặn |
| Token không hợp lệ | Không có Authentication JWT hợp lệ | tenant-a | Không áp dụng | Không có method event nếu bị chặn ở filter | 401 từ tầng xác thực |

### 5.4. Vấn đề nguyên tử và tính sẵn sàng của audit sink

Nếu **auditSink.record(...)** ném exception, lời gọi policy có thể dừng trước khi trả về PERMIT/DENY. Ứng dụng phải **chọn và tài liệu hóa** hành vi khi kênh audit gặp lỗi:

- Với hành động đặc biệt nhạy cảm, có thể yêu cầu ghi được sự kiện trước khi cho phép tiếp tục; nếu không ghi được thì từ chối/không hoàn tất thao tác theo chính sách an toàn của hệ thống.
- Với API có yêu cầu availability cao, có thể đẩy event vào bộ đệm hoặc outbox bền vững rồi gửi bất đồng bộ; phải theo dõi việc trễ/mất sự kiện, retry, duplicate và giới hạn backlog.
- Nếu dùng cùng transaction với nghiệp vụ, cần hiểu rằng **rollback nghiệp vụ có thể làm mất audit record**. Audit từ chối trước khi gọi repository thường không nên phụ thuộc vào transaction nghiệp vụ sẽ bị rollback.
- Nếu xử lý retry/at-least-once, thiết kế **event_id** hoặc khóa idempotency để hỗ trợ loại trùng, thay vì đếm mỗi retry là một quyết định độc lập mà không có dấu hiệu.

Không tùy tiện bắt và bỏ qua toàn bộ lỗi ghi audit. Quyết định **fail-open/fail-closed** của pipeline audit phải được phê duyệt theo yêu cầu hệ thống, không ẩn trong một đoạn **catch (Exception ignored)**.

## 6. Audit bằng sự kiện framework và sự kiện ứng dụng

Spring Security có các abstraction như **AuthorizationEventPublisher** và các sự kiện liên quan đến quyết định phân quyền, ví dụ **AuthorizationDeniedEvent**. Chúng có thể được dùng để thu thập deny event từ các điểm tích hợp được cấu hình. Cần kiểm tra cách phiên bản Spring Security đang dùng kết nối event publisher với **method security interceptor**; không nên mặc định cho rằng mọi PERMIT, DENY, **@PreFilter** hoặc **@PostAuthorize** đều đã được ghi sẵn.

Hai hướng thường được dùng:

| Hướng | Điểm mạnh | Giới hạn |
|---|---|---|
| **Framework authorization events** | Thu thập từ cơ chế phân quyền tập trung; hữu ích để phát hiện nhiều loại DENY | Event không nhất thiết có đủ tenant/action/reason nghiệp vụ; publish grant có thể cần cấu hình tùy biến |
| **Ứng dụng ghi ngay trong policy** | Có đủ action, tenant, resource và reason code mà policy trực tiếp hiểu | Phải đảm bảo tất cả policy quan trọng đều đi qua điểm chung; không thấy request bị chặn trước đó |

Hai nguồn có thể bổ sung cho nhau. Khi gom vào SIEM, cần chuẩn hóa **event_type**, **policy_id**, thời điểm và dấu hiệu nguồn; tránh đếm trùng một lần từ chối được phát bởi cả framework lẫn policy ứng dụng. Nếu cần audit 100% mọi quyết định grant/deny, hãy thiết kế một điểm phát sinh duy nhất hoặc một adapter chung cho các authorization manager đang thực thi, rồi kiểm thử trên chính phiên bản thư viện được dùng.

**Không chỉ bắt AccessDeniedException để suy ra toàn bộ quyết định.** Exception cho biết lời gọi bị từ chối ở một điểm nào đó, nhưng không tự mang đủ ngữ cảnh method/tenant, và một số nhánh bị từ chối ở HTTP layer sẽ không đi qua method. Tương tự, AOP aspect ghi mọi lần method chạy không thể khẳng định kết quả authorization nếu nó không quan sát chính phép kiểm tra.

## 7. Token claims và độ tin cậy của thông tin audit

Trong OAuth 2.0/OIDC, authorization decision tại method thường sử dụng dữ liệu từ **access token** đã được xác thực:

| Dữ liệu | Cách dùng khi đánh giá quyền | Cách ghi audit |
|---|---|---|
| **sub** | Xác định chủ thể | Ghi mã định danh tối thiểu cần thiết |
| **iss** | Chọn/trust nhà phát hành hợp lệ | Có thể ghi mã issuer đã chuẩn hóa |
| **aud** | Xác nhận token dành cho Resource Server/API hiện tại | Ghi trạng thái kiểm tra hoặc mã audience có liên quan |
| **exp, nbf, iat** | Kiểm tra hiệu lực token, thời gian | Thường không cần lặp lại toàn bộ timestamps trong mỗi method event |
| **scope / scp** | Ánh xạ permissions được cấp | Ghi action đã kiểm tra và reason thiếu scope; tránh dump tất cả scope |
| **tid / tenant** tùy biến | Giới hạn quyền theo tenant | Chỉ tin sau khi validate token và mapping đúng contract |
| **jti** nếu có | Hỗ trợ điều tra replay/thu hồi tùy hệ thống | Bảo vệ như định danh nhạy cảm; không dùng làm nguồn duy nhất phát hiện replay |

**JWT access token** được xác minh bằng chữ ký/khóa tin cậy và các validator; **opaque access token** thường được kiểm tra bằng introspection (hoặc cơ chế tin cậy tương đương). Dù dùng kiểu token nào, method policy chỉ nên đọc **principal/authorities đã qua xác thực**. Không dùng đoạn **Base64 decode** JWT chưa verify để tạo subject hoặc tenant audit.

**Access token không phải ID token.** ID token trong OIDC được thiết kế để client nhận thông tin về phiên xác thực của người dùng, không phải bằng chứng phân quyền cho mọi API. **Refresh token** dành cho việc nhận access token mới tại Authorization Server và không được chuyển đến business method để làm căn cứ cho quyền.

### 7.1. Quyền thay đổi khi access token vẫn còn hiệu lực

Ví dụ, người dùng bị gỡ quyền **orders.read** khỏi tenant-a lúc 10:05, nhưng JWT đã cấp lúc 10:00 có **exp = 10:15**. Nếu API chỉ kiểm tra JWT offline và không tham chiếu lại quyền hiện hành, lời gọi 10:07 vẫn có thể được policy cho phép.

Audit tại method có thể ghi **PERMIT** vào lúc 10:07. Đó có thể là kết quả đúng **theo entitlement được đưa vào token** nhưng không đúng với trạng thái phân quyền mới nhất trong cơ sở dữ liệu. Khi điều tra cần đối chiếu thời điểm cấp token, thời điểm thay đổi membership và chính sách thu hồi.

Các chiến lược giảm độ trễ thu hồi gồm access token ngắn hạn, kiểm tra membership/permission động ở hành động nhạy cảm, token version hoặc denylist, và opaque token với introspection kiểm tra trạng thái. Nếu dùng **refresh token rotation**, phát hiện reuse và thu hồi token theo phiên, nên liên kết các sự kiện ở Authorization Server với audit method bằng định danh đã được bảo vệ và chính sách retention phù hợp.

### 7.2. Phát hiện token bị đánh cắp hoặc phát lại

Audit method có thể hỗ trợ phát hiện các mẫu như nhiều lần DENY do sai tenant, chuỗi hành động khác thường của cùng chủ thể, hoặc cùng phiên cấp token xuất hiện từ những ngữ cảnh rủi ro. Tuy nhiên:

- Một event **DENY** đơn lẻ không chứng minh có tấn công; có thể là lỗi UI, quyền vừa thay đổi hoặc request không hợp lệ.
- Nhiều PERMIT từ một bearer token **không tự chứng minh** có replay: một token hợp lệ thường được dùng nhiều lần.
- **jti** chỉ là token identifier khi có và được phát hành đúng; bản thân jti không làm access token trở thành one-time token.
- Có thể dùng sender-constrained tokens như DPoP hoặc mTLS để giảm khả năng sử dụng token bị lấy cắp trong những kiến trúc hỗ trợ.

Không gửi raw token vào SIEM để tiện điều tra. Nếu cần tương quan, dùng khóa được kiểm soát hoặc fingerprint phù hợp với threat model và yêu cầu bảo vệ thông tin.

## 8. Những giới hạn thường khiến audit sai hoặc bị thiếu

### 8.1. Self-invocation và Spring AOP proxy

~~~java
@Service
public class ReportService {
    public void runBatch() {
        // Lời gọi this.exportSecret() trong cùng object có thể bỏ qua proxy.
        this.exportSecret();
    }

    @PreAuthorize("hasAuthority('SCOPE_reports.export')")
    public void exportSecret() {
        // Tác vụ nhạy cảm
    }
}
~~~

Với cơ chế Spring proxy thông thường, **this.exportSecret()** không đi qua proxy, nên annotation security và audit gắn với interceptor có thể không chạy. Cách khắc phục là đưa method nhạy cảm sang bean Spring riêng và gọi qua bean được inject, hoặc thiết kế enforcement trực tiếp ở policy/service boundary phù hợp. Chú ý những method/đối tượng không được Spring quản lý, method không thể được proxy đúng cách, cấu hình proxy, và lời gọi từ constructor.

### 8.2. Bối cảnh bất đồng bộ và reactive

**SecurityContext** của ứng dụng Servlet thường gắn với thread hiện hành; khi chuyển sang executor, scheduled task hoặc message consumer, ngữ cảnh xác thực có thể không tự xuất hiện hoặc bị mất nếu chuyển không đúng cách. Không gán mặc định actor cuối cùng của HTTP request cho một background job.

Trong ứng dụng reactive, Spring Security sử dụng ngữ cảnh qua **Reactor Context**; không dựa vào **ThreadLocal/MDC** thông thường để đảm bảo actor hoặc trace ID luôn đúng sau mọi operator. Dùng cơ chế method security reactive và cách truyền context tương ứng. Với job hệ thống, ghi rõ **actor_type = SYSTEM** và danh tính workload được xác thực, đồng thời định nghĩa policy riêng.

### 8.3. Quyền đối tượng và hiệu ứng của @PostAuthorize

Một quyết định PERMIT ở đầu method có thể chỉ kiểm tra scope/tenant của request; nó chưa thay thế việc lọc **tenant_id** ở repository. Query chỉ bằng **orderId** có thể trả về dữ liệu tenant khác dù policy đã cho phép request cho tenant-a.

**@PostAuthorize** có thể quyết định dựa trên **returnObject** sau khi method thực thi, nhưng cần thận trọng vì code nghiệp vụ, IO hoặc side effect có thể đã xảy ra. Đối với lệnh ghi dữ liệu, kiểm tra trước và lọc dữ liệu theo tenant từ tầng truy xuất là lựa chọn dễ kiểm soát hơn.

### 8.4. Policy phức hợp, lỗi đánh giá và trùng sự kiện

Xét biểu thức:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read') " +
              "and @tenantGuard.check(authentication, #tenantId)")
~~~

Do cơ chế **short-circuit**, nếu thiếu scope, **tenantGuard.check(...)** có thể không được gọi. Nếu chỉ ghi audit bên trong **tenantGuard**, quyết định DENY do thiếu scope sẽ bị mất. Ví dụ mục 5 dùng **một hàm policy duy nhất** để tính toàn bộ điều kiện và phát ra sự kiện. Với hệ thống nhiều rule phức tạp, nên gom quyết định qua cùng một policy evaluator hoặc cơ chế publisher phù hợp.

Nếu một lời gọi đi qua nhiều boundary, cùng một request có thể phát nhiều sự kiện PERMIT/DENY hợp lệ. Cần xác định **decision_id**, **policy_id**, parent span hoặc method invocation ID để phân biệt nhiều quyết định thực sự với các bản ghi lặp do retry.

## 9. Bảo mật pipeline audit và khả năng vận hành

Audit chứa dữ liệu liên quan quyền truy cập nên chính pipeline ghi audit cũng là một bề mặt cần bảo vệ:

| Kiểm soát | Cách áp dụng |
|---|---|
| **Bảo mật dữ liệu** | Chỉ thu thập trường phục vụ mục tiêu cụ thể; masking/pseudonymization; mã hóa trong truyền và lưu trữ |
| **Truy cập audit** | Phân quyền đọc/tra cứu tách biệt với người thao tác nghiệp vụ; giám sát thao tác xuất/xóa |
| **Tính toàn vẹn** | Hạn chế sửa/xóa; thiết lập retention, immutable append hoặc bằng chứng chống sửa tùy yêu cầu |
| **Tính sẵn sàng** | Buffer/outbox, retry, backpressure và cảnh báo khi collector hoặc queue lỗi |
| **Hiệu năng** | Không log toàn bộ request/response; kiểm soát cardinality của label metric; log sampling không phù hợp nếu yêu cầu audit đầy đủ |
| **Dữ liệu đầu vào** | Structured logging; không nối nguyên văn input có newline/control characters vào chuỗi log |
| **Tương quan** | Dùng trace/correlation ID nhất quán giữa xác thực, method decision và business outcome |
| **Giữ và xóa** | Đặt thời hạn lưu trữ theo yêu cầu bảo mật, pháp lý và nội bộ; không giữ vô hạn theo mặc định |

Có thể tạo metric như tỷ lệ **DENY** theo service, policy ID, loại reason; tránh dùng **subject_id/resource_id/token_id** làm nhãn metric cardinality cao. Mọi cảnh báo truy cập nghi vấn nên xem cùng bối cảnh xác thực, phiên cấp token, thay đổi role và kết quả nghiệp vụ.

## 10. Kịch bản kiểm thử cần chứng minh

Giả định endpoint gọi **OrderService.readOrder(tenantId, orderId)** qua Spring-managed bean; token có scope **orders.read** và claim **tid**.

| Trường hợp | Authentication / request | Audit mong đợi | Enforcement mong đợi |
|---|---|---|---|
| Đúng tenant, đủ scope | JWT hợp lệ; tid=tenant-a; URL tenant-a | 1 PERMIT, POLICY_PERMITTED | Method được thực thi |
| Sai tenant | JWT hợp lệ; tid=tenant-a; URL tenant-b | 1 DENY, TENANT_MISMATCH | Service bị chặn, thường 403 |
| Thiếu scope | JWT hợp lệ; tid=tenant-a; không có orders.read | 1 DENY, MISSING_PERMISSION | Service bị chặn, thường 403 |
| Không có token | Request tới endpoint yêu cầu auth | Không phát sinh method event nếu filter chặn | 401 và auth-layer audit |
| JWT sai chữ ký/hết hạn | Resource Server từ chối | Không phát sinh method event | 401 |
| JWT sai aud/iss | Validator từ chối | Không phát sinh method event | 401 |
| Scope đủ nhưng order không tồn tại | JWT hợp lệ, đúng tenant | 1 PERMIT | Repository trả rỗng, API thường 404 |
| Resource ID thuộc tenant khác | JWT đúng tenant-a; ID của tenant-b | 1 PERMIT ở policy đọc theo tenant-a | Query tenant-a + ID không trả bản ghi tenant-b |
| Policy ghi audit lỗi | Collector hoặc sink không hoạt động | Metric/cảnh báo lỗi theo thiết kế | Hành vi theo quyết định fail-open/fail-closed được quy định |
| Self-invocation | this.methodB() trong cùng bean | Test phải phát hiện interceptor không chạy | Refactor luồng gọi qua proxy / policy boundary |
| Thu hồi quyền khi JWT còn hạn | User bị gỡ membership | PERMIT hoặc DENY theo chính sách token/revocation thực tế | Kiểm tra độ trễ thu hồi đã cam kết |
| Retry sự kiện | Hàng đợi gửi lại cùng event | Event có ID để nhận biết duplicate | Không nhân đôi số lần quyết định thực |
| Async job | Không có HTTP caller | Ghi actor SYSTEM/workload đúng | Chính sách riêng, không dùng nhầm SecurityContext |

### Các lớp kiểm thử nên dùng

1. **Unit test policy:** truyền **Authentication** giả lập có authorities và claims có kiểm soát; assert kết quả boolean và nội dung **MethodAuthorizationAuditEvent**. Kiểm tra **không có token thô** trong dữ liệu audit.
2. **Method security integration test:** bật **@EnableMethodSecurity**, gọi service **qua bean Spring** với security context phù hợp; xác minh method không thực thi khi DENY và audit được phát đúng một lần. Test trực tiếp **new OrderService(...)** không kiểm chứng được AOP interceptor.
3. **HTTP/resource server test:** token hợp lệ, hết hạn, sai issuer/audience; xác minh lỗi bị chặn ở tầng xác thực thì không kỳ vọng method event.
4. **Persistence isolation test:** dùng dữ liệu của ít nhất hai tenant; xác minh truy vấn có tenant_id, ngay cả khi client đoán đúng resource ID tenant khác.
5. **Resilience test:** mô phỏng audit sink lỗi/timeout, retry và event trùng để kiểm tra chính sách độ bền và cảnh báo.

Các test cần đối chiếu **decision event** với **kết quả thực thi** như hai đối tượng độc lập. Một method có thể được PERMIT nhưng thất bại khi truy vấn database; test không nên biến lỗi database thành một bản ghi **DENY** giả.

## 11. Bài thực hành và câu hỏi tự kiểm tra

**Tình huống:** Một API xuất báo cáo đã bật **@EnableMethodSecurity**. Controller xác thực JWT và gọi **ReportService.generate(...)**. Trong cùng service, **generate(...)** gọi **this.exportSensitiveData(...)**; method thứ hai có **@PreAuthorize** yêu cầu scope đặc biệt. Nhóm phát triển dùng interceptor để audit mọi DENY nhưng không thấy sự kiện nào khi xuất dữ liệu nhạy cảm.

**Câu hỏi 1:** Vì sao không có DENY event?  
**Gợi ý:** Lời gọi nội bộ **this.exportSensitiveData(...)** có thể bỏ qua Spring AOP proxy. Method security có thể không thực thi; không có decision để interceptor ghi. Đưa phương thức nhạy cảm sang bean riêng rồi gọi qua proxy, và bổ sung integration test để chứng minh enforcement có hiệu lực.

**Câu hỏi 2:** Nếu refactor qua proxy, JWT hợp lệ nhưng thiếu scope và request bị chặn, nên ghi event gì?  
**Gợi ý:** Ghi **METHOD_AUTHORIZATION_DECISION, DENY, MISSING_PERMISSION** kèm action, actor, tài nguyên/tenant yêu cầu và correlation ID; không ghi raw JWT. HTTP thường trả **403** do đã xác thực nhưng thiếu quyền.

**Câu hỏi 3:** Một request được policy cho phép nhưng repository ném lỗi kết nối. Có nên sửa audit **PERMIT** thành **DENY**?  
**Gợi ý:** Không. Policy đã cho phép chạy method; lỗi repository là **business/technical outcome** khác. Ghi lỗi vận hành riêng và tương quan qua trace ID.

**Câu hỏi 4:** Vì sao một hệ thống chỉ thu **AuthorizationDeniedEvent** vẫn có thể chưa đủ cho yêu cầu kiểm toán?  
**Gợi ý:** Không chứng minh được những hành động đã được cho phép, có thể thiếu reason code nghiệp vụ và không nhìn thấy token bị chặn trước method. Cần xác định rõ mức bao phủ và kết hợp các nguồn audit phù hợp.

## 12. Ghi nhớ

**Audit tại method boundary phải phản ánh đúng quyết định mà policy thực sự đưa ra.** Một sự kiện **PERMIT** không bảo đảm nghiệp vụ thành công; một JWT bị từ chối ở tầng xác thực sẽ không tạo ra quyết định ở method; và một annotation bị bỏ qua do self-invocation đồng nghĩa không có enforcement/audit như mong đợi.

Để audit có giá trị điều tra và tuân thủ, hãy:

- Bảo đảm policy có hiệu lực ở đúng ranh giới method và kiểm tra cả action, tenant, resource.
- Ghi **PERMIT/DENY** một cách nhất quán, có **policy_id**, **reason_code** và **correlation_id**.
- Chỉ dùng dữ liệu của principal/token đã được validate; bảo vệ audit khỏi rò rỉ access token và refresh token.
- Phân biệt **authorization decision**, **HTTP response** và **business outcome**.
- Kiểm thử cả việc **chặn lời gọi** lẫn việc **phát audit event** ở những đường đi quan trọng.

Đó là nền tảng để kết nối phân quyền Spring Security với giám sát, phát hiện truy cập trái phép, điều tra token bị lạm dụng và theo dõi thay đổi quyền xuyên suốt vòng đời token.
