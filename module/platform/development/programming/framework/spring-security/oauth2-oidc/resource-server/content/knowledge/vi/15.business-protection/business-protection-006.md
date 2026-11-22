# AuthorizationManager hoặc thành phần quyết định quyền tùy chỉnh

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, JWT access token hợp lệ mới chỉ chứng minh request đã vượt qua **authentication** theo trust configuration. Sau đó ứng dụng vẫn phải quyết định **principal có được phép làm một hành động cụ thể với tài nguyên cụ thể hay không**. Những rule như `authenticated()`, `hasAuthority("SCOPE_orders.read")` và `hasRole("ADMIN")` giải quyết các trường hợp đơn giản. Nhưng một quy tắc nghiệp vụ như “nhân viên chỉ được duyệt hoàn tiền của merchant mà mình phụ trách, trong hạn mức và khi giao dịch chưa hoàn” cần thêm quan hệ, trạng thái và chính sách động.

Spring Security cung cấp **`AuthorizationManager<T>`** để biểu diễn quyết định truy cập; ứng dụng cũng có thể viết **business authorization service** hoặc **policy component** được gọi từ method/service boundary.

> **Nguyên tắc:** custom authorization là nơi **kiểm tra quyền dựa trên bằng chứng đáng tin**, không phải nơi tự xác minh lại chữ ký JWT, tự phát minh scope/role hoặc tin một tenant ID do client gửi là bằng chứng đã được cấp quyền.

Bài học triển khai trên **Java 17+, Spring Boot, Spring Security Servlet/Spring MVC và JWT Resource Server**. Với WebFlux, cơ chế reactive khác API nhưng tư duy về trust và quyền nghiệp vụ tương tự.

## 1. Authentication không thay thế business authorization

Giả sử JWT access token chứa:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 2000000300
}
~~~

Resource Server dùng `JwtDecoder` xác minh chữ ký, issuer, audience, thời gian và chính sách token. Spring Security thường ánh xạ scope thành:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Tuy nhiên, hai scope không đủ để trả lời:

- User 42 có thuộc tenant `merchant-a` không?
- User được xem mọi order của merchant hay chỉ order được phân công?
- Order `order-9001` có thực sự thuộc tenant trong request?
- Order đã khóa, đã giao hoặc đã refund có được sửa tiếp không?
- Role vừa bị thu hồi có còn được dùng từ một JWT chưa hết hạn không?
- Một yêu cầu phê duyệt có cần nguyên tắc người tạo khác người duyệt không?

Những câu hỏi đó thuộc **business authorization**.

| Lớp | Câu hỏi | Cơ chế thường dùng |
|---|---|---|
| Authentication | Token có hợp lệ và đúng API không? | JWT verification, `iss`, `aud`, `exp` |
| HTTP authorization | Route có đòi scope/role gì? | `authorizeHttpRequests`, `hasAuthority` |
| Tenant authorization | Chủ thể có quyền tại tenant đang yêu cầu? | Membership policy, tenant DB |
| Object-level authorization | Có quyền với bản ghi cụ thể? | Owner/ACL, relationship policy |
| State authorization | Hành động có hợp lệ với trạng thái hiện tại? | Domain policy, transaction |
| Enforcement | Không có quyền thì chặn ở đâu? | Filter, method, business service |

Một JWT có chữ ký đúng là **đầu vào** cho authorization, không phải quyết định toàn quyền.

## 2. Khi nào nên viết thành phần tùy chỉnh?

Ưu tiên rule sẵn có nếu chỉ cần kiểm tra một authority:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
.anyRequest().denyAll()
~~~

Custom policy phù hợp khi kiểm tra thêm:

1. Membership trong tổ chức hoặc tenant.
2. Quyền sở hữu hoặc được phân công tới bản ghi.
3. Quan hệ quản lý giữa hai principal.
4. Hạn mức tài chính và trạng thái giao dịch.
5. Phân tách nhiệm vụ người tạo/người duyệt.
6. Step-up authentication/MFA dựa trên chính sách rõ.
7. Quyền động từ database hoặc policy service.
8. Quyền được áp dụng đồng nhất từ HTTP, message consumer và batch service.

**Chọn điểm kiểm tra theo ngữ cảnh sẵn có.** HTTP manager có URL, method, authentication và path variables, nhưng có thể chưa có entity thật. Nếu quyết định phụ thuộc trạng thái mutable của entity, đặt kiểm tra quan trọng ở service/transaction thường an toàn và rõ ràng hơn.

## 3. Cơ chế `AuthorizationManager<T>`

Spring Security hiện đại dùng `AuthorizationManager<T>` cho các quyết định truy cập tại request/method boundary. Nó thay thế vai trò của các API cũ như `AccessDecisionManager` và `AccessDecisionVoter` trong kiến trúc authorization mới.

Ý tưởng API rút gọn:

~~~java
public interface AuthorizationManager<T> {
    AuthorizationResult authorize(
        Supplier<Authentication> authentication,
        T secureObject
    );
}
~~~

Đoạn trên chỉ minh họa cấu trúc, không phải toàn bộ source interface.

- `Supplier<Authentication>` cho phép lấy authentication khi cần.
- `T` mô tả đối tượng được bảo vệ; có thể là `RequestAuthorizationContext` hoặc `MethodInvocation`.
- `AuthorizationResult` đại diện kết quả quyết định; `AuthorizationDecision` là implementation phổ biến.
- `authorize(...)` có thể trả `new AuthorizationDecision(true)` hoặc `new AuthorizationDecision(false)`.
- `null` thường là abstain: manager không đưa ra quyết định. Không đồng nhất abstain với deny trong mọi cách tổng hợp.

Trong Spring Security 6.4+/7.x, tài liệu khuyến nghị dùng **`authorize(...)`**. API legacy **`check(...)`** đã bị đánh dấu deprecated. Với project dùng Spring Security version cũ, kiểm tra method signatures theo phiên bản đó.

~~~java
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationResult;

AuthorizationResult allow = new AuthorizationDecision(true);
AuthorizationResult deny = new AuthorizationDecision(false);

boolean canProceed = allow.isGranted(); // true
~~~

**Không dùng null để “không biết thì cho qua”.** Với một chính sách cần quyền bắt buộc, hãy đưa ra deny rõ ràng khi thiếu dữ liệu.

## 4. Mối quan hệ PEP, PDP và PIP

Một kiến trúc phân quyền có thể chia thành:

~~~text
HTTP request / service call
          |
          v
PEP — Policy Enforcement Point
    (Security Filter hoặc service)
          |
          | hỏi quyết định
          v
PDP — Policy Decision Point
    (AuthorizationManager / policy engine)
          |
          | lấy dữ liệu tin cậy
          v
PIP — Policy Information Point
    (JWT đã xác minh, ACL, membership, resource state)
          |
          v
ALLOW / DENY / ERROR
          |
          v
PEP chỉ thực hiện thao tác khi được ALLOW
~~~

**PEP** là nơi chặn hành động. **PDP** tính quyết định dựa vào policy. **PIP** cung cấp thuộc tính quyền/tài nguyên.

Trong Spring Security, `AuthorizationFilter` có thể là PEP ở HTTP boundary và custom `AuthorizationManager` là PDP. Nhưng một `OrderService` cũng có thể là PEP để bảo vệ trạng thái order ở transaction boundary.

Việc đã có HTTP authorization không xóa trách nhiệm thực thi invariant nghiệp vụ tại service.

## 5. Đề bài mẫu: quyền đọc order theo tenant

Giả sử endpoint:

~~~http
GET /api/tenants/{tenantId}/orders
Authorization: Bearer <access_token>
~~~

Nghiệp vụ yêu cầu đồng thời:

- JWT hợp lệ, đúng issuer, audience và thời hạn.
- Authentication có `SCOPE_orders.read`.
- URL chứa tenant ID hợp lệ.
- Subject được ánh xạ theo `(issuer, subject)`, tránh nhập nhằng giữa IdP.
- Subject có membership được phép đọc đơn ở tenant yêu cầu.
- Các order thực sự được trả về phải thuộc tenant đó.

Phần membership phải được chứng minh từ **nguồn quyền có thẩm quyền**; tenant ID trong path chỉ mô tả **mục tiêu**, không chứng minh quyền truy cập.

### 5.1. Contract cho nguồn membership

~~~java
package com.example.orders.security;

// Cần implementation truy vấn DB hoặc authorization service đáng tin.
public interface TenantMembershipPolicy {

    boolean canReadOrders(
        String issuer,
        String subject,
        String tenantId
    );
}
~~~

Nếu chỉ định danh subject bằng `sub`, hai issuer khác nhau có thể vô tình bị hợp nhất user. Cặp `(iss,sub)` là cơ sở tốt hơn khi có nhiều issuers.

### 5.2. Implement custom HTTP manager

~~~java
package com.example.orders.security;

import java.util.function.Supplier;

import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.stereotype.Component;

@Component
public final class TenantOrdersReadAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final TenantMembershipPolicy memberships;

    public TenantOrdersReadAuthorizationManager(
            TenantMembershipPolicy memberships) {
        this.memberships = memberships;
    }

    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        Authentication current = authentication.get();

        if (!(current instanceof JwtAuthenticationToken jwtAuth)
                || !current.isAuthenticated()) {
            return new AuthorizationDecision(false);
        }

        boolean hasReadScope = current.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch("SCOPE_orders.read"::equals);

        if (!hasReadScope) {
            return new AuthorizationDecision(false);
        }

        String tenantId = context.getVariables().get("tenantId");

        if (tenantId == null || tenantId.isBlank()) {
            return new AuthorizationDecision(false);
        }

        Jwt jwt = jwtAuth.getToken();
        String subject = jwt.getSubject();
        String issuer = jwt.getIssuer() == null
            ? null : jwt.getIssuer().toString();

        if (issuer == null || subject == null || subject.isBlank()) {
            return new AuthorizationDecision(false);
        }

        boolean allowed =
            memberships.canReadOrders(issuer, subject, tenantId);

        return new AuthorizationDecision(allowed);
    }
}
~~~

Điểm đáng chú ý:

- Manager **không parse JWT bằng tay** và không tự chọn public key.
- Chỉ chấp nhận `JwtAuthenticationToken` do hệ thống JWT Resource Server xác thực.
- Giữ kiểm tra `SCOPE_orders.read`; membership không tự thay thế scope.
- Path variable thiếu hoặc danh tính thiếu → deny.
- Membership từ nguồn tin cậy quyết định kết quả cuối cùng.
- Không thêm `ROLE_ADMIN` hay scope mới vào `Authentication`.

### 5.3. `RequestAuthorizationContext` chứa gì?

`RequestAuthorizationContext` có:

- `getRequest()`: `HttpServletRequest`.
- `getVariables()`: biến đường dẫn đã được matcher trích xuất nếu matcher hỗ trợ.

`context.getVariables().get("tenantId")` phụ thuộc việc pattern `{tenantId}` đã khớp và trích xuất đúng. Khác biệt về `PathPatternRequestMatcher`, Spring MVC integration, servlet path hoặc version có thể ảnh hưởng. Nếu biến không có, mẫu code **fail closed**, không tự lấy một header do client gửi làm bằng chứng membership.

## 6. Đưa manager vào `SecurityFilterChain`

`build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

`audiences` là property của các phiên bản Spring Boot hiện đại; nếu version đang dùng không hỗ trợ, cần audience validator cho `JwtDecoder`. Dùng đúng access token cho Resource Server, không lấy ID token của OIDC client thay thế.

Khai báo filter chain:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            TenantOrdersReadAuthorizationManager tenantOrdersRead)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()

                .requestMatchers(
                    HttpMethod.GET,
                    "/api/tenants/{tenantId}/orders/**")
                    .access(tenantOrdersRead)

                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()

                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

`access(tenantOrdersRead)` buộc Spring Security sử dụng custom manager cho request khớp matcher cụ thể. `anyRequest().denyAll()` đóng mọi đường dẫn không được khai báo trong chain.

Ví dụ này tập trung vào authorization. CSRF, session và CORS cần cấu hình theo cách client dùng credential. Với browser cookie/session, **không tắt CSRF vô điều kiện**. Nếu API stateless chỉ nhận bearer header, chính sách CSRF có thể khác nhưng vẫn cần review.

### 6.1. Thứ tự matcher có thể bỏ qua custom policy

Sai:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/tenants/{tenantId}/orders/**")
        .access(tenantOrdersRead)
    .anyRequest().denyAll()
)
~~~

Rule tổng quát `/api/**` khớp trước và khiến custom manager **không được gọi**. Đặt rule đặc hiệu trước các rule tổng quát.

Khi có nhiều `SecurityFilterChain`, `securityMatcher` chọn chain; `requestMatchers` chọn rule trong chain đó. Không giả định `anyRequest().denyAll()` của chain có `securityMatcher("/api/**")` bảo vệ cả URL ngoài `/api/**`.

## 7. HTTP authorization không chứng minh quyền trên bản ghi

Giả sử user thuộc `tenant-a`, nhưng cố tình gọi:

~~~http
GET /api/tenants/tenant-a/orders/order-from-tenant-b
Authorization: Bearer <valid-access-token>
~~~

HTTP manager xác nhận user có scope và membership tenant A. Nhưng nếu service query:

~~~java
// NGUY HIỂM khi không kiểm tra tenant của order.
Order order = repository.findById(orderId).orElseThrow();
~~~

nó có thể trả dữ liệu tenant B. Đây là **Broken Object Level Authorization (BOLA/IDOR)**.

Cách đúng phải kiểm tra quan hệ order–tenant trong query/logic dịch vụ:

~~~java
// Pseudocode: API repository do ứng dụng tự định nghĩa.
Order order = repository
    .findByIdAndTenantId(orderId, tenantId)
    .orElseThrow(NotFoundException::new);

if (!orderPolicy.canReadOrder(principal, order)) {
    throw new AccessDeniedException("Not permitted");
}

return order;
~~~

Các class `Order`, `NotFoundException`, `orderPolicy` và `principal` là thành phần nghiệp vụ minh họa. Không được mặc định HTTP kiểm tra membership là đủ để mở mọi bản ghi trong tenant.

## 8. `@PreAuthorize` và custom bean quyết định quyền

Một chính sách cần `orderId` hoặc entity thực tế thường nên nằm gần business service. Spring Security method security cho phép dùng `@PreAuthorize` gọi bean policy.

### 8.1. Bật method security

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

### 8.2. Định nghĩa policy tại service boundary

~~~java
package com.example.orders.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("orderAuthz")
public final class OrderAuthorization {

    private final OrderAccessPolicy orderAccess;

    public OrderAuthorization(OrderAccessPolicy orderAccess) {
        this.orderAccess = orderAccess;
    }

    public boolean canRead(
            Authentication authentication,
            String orderId) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)
                || !authentication.isAuthenticated()
                || orderId == null || orderId.isBlank()) {
            return false;
        }

        boolean hasScope = authentication.getAuthorities().stream()
            .anyMatch(a ->
                "SCOPE_orders.read".equals(a.getAuthority()));

        if (!hasScope) {
            return false;
        }

        Jwt jwt = jwtAuth.getToken();
        if (jwt.getIssuer() == null || jwt.getSubject() == null) {
            return false;
        }

        return orderAccess.canReadOrder(
            jwt.getIssuer().toString(),
            jwt.getSubject(),
            orderId
        );
    }
}
~~~

Contract quyền theo order:

~~~java
package com.example.orders.security;

public interface OrderAccessPolicy {

    boolean canReadOrder(
        String issuer,
        String subject,
        String orderId
    );
}
~~~

Implementation của `OrderAccessPolicy` phải kiểm tra owner/tenant/ACL từ nguồn đáng tin, không chỉ so sánh token subject với một field do client tự gửi.

### 8.3. Sử dụng trong method

~~~java
package com.example.orders.service;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@orderAuthz.canRead(authentication, #orderId)")
    public OrderDto getOrder(String orderId) {
        return repository.loadWithSecurityConstraints(orderId);
    }
}
~~~

`OrderRepository`, `OrderDto` và `loadWithSecurityConstraints` là các thành phần domain minh họa. `#orderId` là tên tham số method; dự án có thể cần compiler metadata `-parameters` hoặc cách khai báo tên phù hợp để SpEL resolve chính xác.

**Ưu điểm:** policy ở service còn bảo vệ lời gọi từ nhiều controller. Nhưng vẫn phải xem method có được gọi qua Spring AOP proxy hay không.

### 8.4. Bẫy self-invocation

Với proxy-based method security:

~~~java
public OrderDto internalRead(String orderId) {
    return getOrder(orderId); // Có thể không đi qua AOP proxy
}
~~~

Nếu lời gọi nội bộ trong cùng class không qua proxy, `@PreAuthorize` của method được gọi có thể **không thực thi**. Cần thiết kế boundary đúng, gọi qua bean được quản lý hoặc đặt chính sách cốt lõi trong service/domain code không thể bypass.

### 8.5. `@PostAuthorize` và side effects

`@PostAuthorize` kiểm tra sau khi method chạy. Nó có thể hữu ích cho một số trường hợp đọc dữ liệu sau khi thấy object trả về. Nhưng không dùng post-check làm cách duy nhất để ngăn **chuyển tiền, refund, xóa bản ghi hoặc gửi email**, vì side effects có thể đã xảy ra trước lúc policy từ chối.

Với thao tác ghi, thường cần pre-check và invariant được thực thi trong transaction.

## 9. Custom `AuthorizationManager<MethodInvocation>`

Khi cần một cơ chế method authorization chung hơn việc gọi bean riêng bằng SpEL, có thể triển khai:

~~~java
package com.example.orders.security;

import java.util.function.Supplier;

import org.aopalliance.intercept.MethodInvocation;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;

public final class BusinessMethodAuthorizationManager
        implements AuthorizationManager<MethodInvocation> {

    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authentication,
            MethodInvocation invocation) {

        // Skeleton minh họa: đọc method + args,
        // áp dụng policy có thẩm quyền, trả quyết định rõ.
        boolean allowed = false;

        return new AuthorizationDecision(allowed);
    }
}
~~~

Đoạn trên là **skeleton chỉ để mô tả interface**, không phải implementation nghiệp vụ dùng trực tiếp: hiện nó luôn deny.

Spring Security cung cấp `AuthorizationManagerBeforeMethodInterceptor` và các advisor/pointcut để gắn custom method manager. Nếu thay thế cơ chế method security mặc định, cần cấu hình interceptor theo phiên bản framework và bảo đảm không tạo vùng trống policy.

Với những rule thuộc một hoặc một vài service method, **`@PreAuthorize` gọi bean Java** thường dễ đọc và dễ kiểm thử hơn so với custom infrastructure interceptor.

## 10. Ghép nhiều manager thay vì một hàm điều kiện lớn

Spring Security có những combinators:

- `AuthorizationManagers.allOf(...)`: tổ hợp nhiều điều kiện kiểu AND.
- `AuthorizationManagers.anyOf(...)`: tổ hợp các nhánh kiểu OR.
- `AuthorizationManagers.not(...)`: phủ định quyết định.

Ví dụ, nếu có hai manager độc lập là **kiểm tra scope** và **kiểm tra tenant membership**, có thể ghép:

~~~java
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

AuthorizationManager<RequestAuthorizationContext> scope =
    AuthorityAuthorizationManager.hasAuthority("SCOPE_orders.read");

// tenantOnlyManager là một manager riêng chỉ kiểm tra membership.
AuthorizationManager<RequestAuthorizationContext> tenant =
    tenantOnlyManager;

AuthorizationManager<RequestAuthorizationContext> combined =
    AuthorizationManagers.allOf(
        new AuthorizationDecision(false),
        scope,
        tenant
    );
~~~

Ví dụ trên dùng overload có **default decision khi mọi manager abstain**, hỗ trợ ở các version Spring Security hiện đại. `tenantOnlyManager` là biến minh họa do ứng dụng cung cấp. Nếu dùng `TenantOrdersReadAuthorizationManager` ở phần 5, nó **đã kiểm tra scope lẫn membership**, nên không cần lặp.

### 10.1. Abstain không tự đồng nghĩa deny

Trong một số tổ hợp, manager trả `null` có nghĩa không quyết định. `allOf` và `anyOf` có quy tắc riêng khi tất cả manager abstain; không nên tự giả định kết quả là deny.

Với permission quan trọng, hãy:

1. Ưu tiên kết quả `AuthorizationDecision(true/false)` tường minh.
2. Xác định behavior nếu không manager nào quyết định.
3. Dùng default deny khi API/version hỗ trợ.
4. Kiểm thử cả trường hợp manager trả null hoặc lỗi.

**Chọn OR cũng có thể là lỗi bảo mật.** Nếu policy yêu cầu cả scope và membership, dùng `anyOf` sẽ cho phép người chỉ có một trong hai vượt qua.

## 11. Không nhất thiết mọi business policy phải là interface Spring Security

Một policy phụ thuộc trạng thái entity có thể phù hợp hơn khi viết thành domain service:

~~~java
public interface RefundPolicy {

    boolean canApprove(
        SubjectIdentity actor,
        RefundRequest request,
        Merchant merchant
    );
}
~~~

Sử dụng trong transaction:

~~~java
@Transactional
public RefundReceipt approveRefund(
        String refundId,
        SubjectIdentity actor) {

    RefundRequest refund =
        refundRepository.findForUpdate(refundId);

    Merchant merchant =
        merchantRepository.findById(refund.merchantId());

    if (!refundPolicy.canApprove(actor, refund, merchant)) {
        throw new AccessDeniedException("Not permitted");
    }

    // Kiểm tra invariant và cập nhật atomically.
    return executeRefund(refund);
}
~~~

`SubjectIdentity`, `RefundRequest`, `Merchant`, `RefundReceipt` và repository là ví dụ domain, không phải API Spring Security có sẵn. `@Transactional` thuộc Spring transaction support.

Tại sao làm ở đây?

- Entity mới nhất có thể đã được tải.
- Kiểm tra và ghi có thể nằm trong cùng transaction.
- Domain service còn được gọi từ message consumer/job.
- Tránh duplicate policy giữa nhiều controller.
- Đơn vị kiểm thử gần với yêu cầu nghiệp vụ hơn.

Custom `AuthorizationManager` có thể giúp **chặn sớm** trước controller, nhưng không thay thế kiểm tra quyền tại transaction boundary nếu dữ liệu biến động.

## 12. TOCTOU: quyền thay đổi giữa kiểm tra và thao tác

**Time-of-check to time-of-use** là khoảng cách giữa lúc quyết định và lúc thực thi.

Ví dụ:

~~~text
T0     AuthorizationManager thấy order chưa refund -> ALLOW
T0+50  Request khác refund cùng order thành công
T0+100 Service ban đầu tiếp tục refund lần nữa
~~~

Đối với refund, chuyển tiền, đổi trạng thái hoặc tạo tài nguyên duy nhất, cần thêm:

- Kiểm tra trạng thái bên trong transaction.
- Optimistic locking qua `@Version` khi phù hợp.
- Pessimistic locking/row lock nếu thiết kế cần.
- Conditional update ràng buộc trạng thái.
- Idempotency key và unique constraints.
- Quyền phê duyệt và separation-of-duties ở domain boundary.

**AuthorizationManager không phải lock hoặc transaction manager.**

## 13. PDP bên ngoài và policy service

Một tổ chức có thể quản lý quyền bằng database, entitlement service hoặc policy engine như OPA.

~~~text
AuthorizationFilter / Service PEP
             |
             v
Custom AuthorizationManager
             |
             | identity, action, resource, tenant
             v
Policy Decision Point (PDP)
             |
             +-- membership
             +-- ACL / role / policy versions
             +-- resource attributes
             |
             v
ALLOW / DENY / UNAVAILABLE
~~~

Ví dụ policy request nội bộ:

~~~json
{
  "subject": {
    "issuer": "https://idp.example.com/realms/shop",
    "id": "user-42"
  },
  "action": "orders.read",
  "resource": {
    "type": "tenant-orders",
    "tenantId": "merchant-a"
  },
  "application": "orders-api"
}
~~~

Dữ liệu `subject` phải đến từ `Authentication` đã xác thực, không phải body/header client tự khai.

### 13.1. Trust boundary với PDP

Một PDP đáng tin cần:

- Endpoint do server quản lý, không cho client chọn arbitrary URL.
- TLS/mTLS hoặc kênh xác thực bảo vệ theo thiết kế.
- Quyền gọi PDP và dữ liệu tenant được giới hạn.
- Decision gắn với **đúng subject, action, resource, tenant, policy version**.
- Response được parse theo schema rõ; trường lạ/lỗi không tự thành allow.
- Audit và các chính sách xử lý stale quyền.

### 13.2. Policy service timeout: không fail open

Nếu PDP hoặc database không sẵn sàng, **không trả ALLOW** chỉ để API đáp ứng nhanh. Có thể từ chối request hoặc trả lỗi availability như 503 theo thiết kế, nhưng hành động nghiệp vụ không được thực thi khi chưa xác định quyền.

**Fail closed** không bắt buộc mọi lỗi hạ tầng đều trả 403. Cần phân biệt business deny và sự cố policy service trong telemetry, dù không tiết lộ thông tin nhạy cảm cho client.

### 13.3. Cache quyết định quyền

Cache có thể cải thiện latency nhưng phải gắn đủ context:

~~~text
issuer + subject + action + resource + tenant + policyVersion
~~~

Không cache allow chỉ theo `sub` và tái dùng cho mọi tenant. Cần TTL, invalidation khi thay membership/role, chính sách revocation, cache isolation giữa tenants và giới hạn cho stale decisions. Với quyền nhạy cảm hoặc cần thu hồi ngay, cache allow dài có thể không phù hợp.

## 14. RBAC, ABAC và ReBAC

Nhiều hệ thống kết hợp:

| Mô hình | Trọng tâm | Ví dụ |
|---|---|---|
| **RBAC** | Role được cấp | `ROLE_ORDERS_OPERATOR` |
| **OAuth scope** | Quyền thao tác ở mức API | `SCOPE_orders.read` |
| **ABAC** | Thuộc tính subject/resource/context | Merchant, loại order, hạn mức |
| **ReBAC** | Quan hệ subject–resource | User là thành viên team sở hữu order |
| **Policy-based** | Tổng hợp nhiều điều kiện | Scope AND membership AND trạng thái |

Ví dụ một yêu cầu refund hợp lệ cần:

~~~text
valid access token for refunds-api
AND SCOPE_refunds.approve
AND actor thuộc merchant tương ứng
AND refund amount <= remaining limit
AND payment is settled
AND payment chưa refund
AND actor != request creator (nếu policy yêu cầu)
~~~

Không được suy ra `ROLE_ADMIN` từ email, username hoặc group tùy ý. Nguồn role/entitlement phải do tổ chức kiểm soát, đúng issuer và đúng ứng dụng.

## 15. Multi-issuer, multi-tenant và BOLA

Hai issuer khác nhau có thể cùng tạo `sub=user-42`:

~~~text
(https://idp-a.example.com, user-42)
(https://idp-b.example.com, user-42)
~~~

Đây là **hai danh tính không mặc nhiên giống nhau**. Nếu chỉ query membership theo `sub`, Resource Server có thể nhầm principal của hai issuer.

Token chứa `tenant_id=tenant-a` cũng không mặc nhiên chứng minh chủ thể có quyền admin tenant A. Claim tenant có thể là bối cảnh; cần contract rõ và object/relationship policy.

Một request:

~~~text
GET /api/tenants/tenant-a/orders/order-from-tenant-b
~~~

có thể vượt qua HTTP membership tenant A, nhưng service phải tiếp tục kiểm tra order thuộc tenant nào. Dùng tenant predicate ngay trong truy vấn là cách giảm nguy cơ **Broken Object Level Authorization (BOLA/IDOR)**.

## 16. Các anti-pattern cần tránh

### 16.1. Tin role trong request

~~~java
// SAI: client kiểm soát X-Role header.
if ("ADMIN".equals(request.getHeader("X-Role"))) {
    return new AuthorizationDecision(true);
}
~~~

### 16.2. Tin target tenant là bằng chứng quyền

~~~java
// SAI: mọi tenantId có giá trị đều được cho phép.
String tenantId = request.getParameter("tenantId");
return new AuthorizationDecision(tenantId != null);
~~~

### 16.3. Tự thêm quyền để sửa 403

~~~java
// SAI: token chỉ có read scope không được bù thêm write.
if (hasReadScope) {
    authorities.add(new SimpleGrantedAuthority("SCOPE_orders.write"));
}
~~~

### 16.4. Chỉ đặt manager ở controller

Nếu service được gọi từ scheduler hoặc queue consumer, đường gọi khác có thể bypass policy. Tách policy thành service dùng chung; xác định cách xác thực workload/entrypoint đó.

### 16.5. Đặt matcher tổng quát trước matcher nghiệp vụ

~~~java
// SAI: matcher tổng quát che custom access rule.
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/tenants/{tenantId}/orders/**")
    .access(tenantOrdersRead)
~~~

### 16.6. Post-authorization cho hành động có side effect

Một lần ghi database đã thực hiện trước post-check không thể luôn được hoàn tác. Dùng pre-check và kiểm tra invariant trong transaction.

### 16.7. Cho phép khi nguồn policy lỗi

Một null result, timeout hay exception từ policy service không được mặc định thành allow.

## 17. 401, 403 và lỗi hạ tầng policy

| Tình huống | Kết quả điển hình | Nguyên nhân |
|---|---|---|
| Không gửi bearer token cho endpoint private | 401 | Không có authentication |
| JWT sai chữ ký/issuer/audience/expiration | 401 | Authentication thất bại |
| JWT hợp lệ nhưng thiếu `SCOPE_orders.read` | 403 | Authorization từ chối |
| Có scope nhưng không thuộc tenant | 403 hoặc 404 theo API policy | Business authorization |
| User thuộc tenant A, order thuộc tenant B | 403/404 | Object-level denial |
| Policy service timeout | 5xx/503 hoặc deny theo thiết kế | Policy infrastructure unavailable |
| Không trích xuất được tenant ID | Từ chối | Missing policy context |
| JWT hợp lệ, scope và membership đều đạt | Được vào handler | Vẫn phải kiểm tra entity |

Custom `AuthorizationManager` thông thường **trả `AuthorizationResult`**, không tự trả HTTP response. Spring Security enforcement và exception handling quyết định phản hồi phù hợp.

RFC 6750 mô tả Bearer challenge với `invalid_token` hoặc `insufficient_scope`. Không đưa JWT thật hoặc entitlement nội bộ nhạy cảm vào response lỗi.

## 18. Unit test custom manager

`TenantOrdersReadAuthorizationManager` có thể test bằng `JwtAuthenticationToken` và `RequestAuthorizationContext` giả lập.

~~~java
package com.example.orders.security;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class TenantOrdersReadAuthorizationManagerTest {

    static JwtAuthenticationToken userWithReadScope() {
        Jwt jwt = Jwt.withTokenValue("unit-test-only")
            .header("alg", "RS256")
            .claim("iss", "https://idp.example.com/realms/shop")
            .claim("sub", "user-42")
            .build();

        return new JwtAuthenticationToken(
            jwt,
            List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
        );
    }

    static RequestAuthorizationContext forTenant(String tenantId) {
        MockHttpServletRequest request =
            new MockHttpServletRequest(
                "GET", "/api/tenants/" + tenantId + "/orders"
            );

        return new RequestAuthorizationContext(
            request, Map.of("tenantId", tenantId)
        );
    }

    @Test
    void grantsOnlyWhenMembershipExists() {
        TenantMembershipPolicy policy =
            mock(TenantMembershipPolicy.class);

        when(policy.canReadOrders(
            "https://idp.example.com/realms/shop",
            "user-42",
            "tenant-a"
        )).thenReturn(true);

        var manager = new TenantOrdersReadAuthorizationManager(policy);

        AuthorizationResult decision = manager.authorize(
            () -> userWithReadScope(),
            forTenant("tenant-a")
        );

        assertTrue(decision.isGranted());
    }

    @Test
    void deniesWhenTenantMembershipMissing() {
        TenantMembershipPolicy policy =
            mock(TenantMembershipPolicy.class);

        var manager = new TenantOrdersReadAuthorizationManager(policy);

        AuthorizationResult decision = manager.authorize(
            () -> userWithReadScope(),
            forTenant("tenant-b")
        );

        assertFalse(decision.isGranted());
    }

    @Test
    void deniesWhenScopeMissing() {
        TenantMembershipPolicy policy =
            mock(TenantMembershipPolicy.class);

        var manager = new TenantOrdersReadAuthorizationManager(policy);
        var withScope = userWithReadScope();

        var withoutScope = new JwtAuthenticationToken(
            withScope.getToken(), List.of()
        );

        AuthorizationResult decision = manager.authorize(
            () -> withoutScope,
            forTenant("tenant-a")
        );

        assertFalse(decision.isGranted());
    }
}
~~~

Đây là **unit test policy**, không phải JWT signature test: `Jwt.withTokenValue` tạo object giả lập, không chứng minh issuer, audience hoặc chữ ký đã được xác minh.

### 18.1. Các tình huống cần test

| Tình huống | Mong đợi |
|---|---|
| Authentication thiếu/anonymous | Deny |
| JWT hợp lệ nhưng không có scope | Deny |
| Có scope nhưng không có membership | Deny |
| Tenant ID rỗng/không được matcher trích xuất | Deny |
| Không có subject hoặc issuer cần thiết | Deny |
| Hai issuer có cùng subject | Không nhầm membership |
| PDP timeout | Không allow |
| Order ID ở tenant khác | Deny ở service |
| Role vừa bị thu hồi | Theo chính sách revocation/cache |
| Scope đọc gọi write endpoint | Deny |
| Manager trả null trong composition | Không vô tình grant |

Với `MockMvc`, tiện ích `jwt()` giúp kiểm tra HTTP rule/wiring, nhưng có thể bỏ qua signature validation và converter production. Cần integration test với JWT được ký bằng test key nếu muốn chứng minh cả đường xác thực.

### 18.2. Kiểm thử method-security proxy

Nếu dùng `@PreAuthorize`, kiểm tra qua Spring-managed bean/proxy thay vì gọi trực tiếp một object mới tạo rồi tưởng advice đã được áp dụng. Test quan trọng gồm:

- Method được gọi từ controller bình thường.
- Method bị gọi từ một service khác.
- Self-invocation có/không đi qua proxy.
- Phần business invariant vẫn từ chối khi HTTP pre-check không được gọi.
- Concurrency/state transitions với transaction khi thao tác có side effects.

## 19. Audit, latency và dữ liệu nhạy cảm

Khi truy cập bị từ chối, log có thể ghi:

~~~text
event=authorization_decision
decision=DENY
policy=tenant-orders-read
subjectRef=<internal-principal-reference>
tenantRef=tenant-b
reason=membership_not_found
traceId=7af3...
bearerToken=[REDACTED]
~~~

Không ghi raw `Authorization` header, access token, refresh token hoặc secret. Cần chính sách bảo vệ dữ liệu cho subject/tenant/resource IDs.

Tách metric thành:

- **Authentication failures:** signature, issuer, audience, expiration.
- **Authorization denials:** missing scope, absent membership, wrong owner, wrong state.
- **Policy infrastructure failures:** database timeout, PDP unavailable, cache issue.

Một policy được gọi mỗi request có thể tăng latency. Đo response time, cache hit rate và policy error rate, nhưng không đánh đổi bảo mật bằng fallback grant khi service chậm.

## 20. Khi nào dùng `PermissionEvaluator`, `@PreAuthorize` hoặc custom manager?

| Lựa chọn | Khi thích hợp | Cần lưu ý |
|---|---|---|
| `hasAuthority` / `hasRole` | Scope hoặc role đơn giản | Không thay ownership |
| Custom HTTP `AuthorizationManager<RequestAuthorizationContext>` | Kiểm tra theo request, path, principal và policy source | Matcher order, thiếu object state |
| `@PreAuthorize` + bean policy | Quyền gắn service method/arguments | Spring AOP proxy, parameter names |
| `PermissionEvaluator` / `hasPermission` | Ứng dụng đã có mô hình object permissions | Nguồn ACL, hiệu năng |
| Custom `AuthorizationManager<MethodInvocation>` | Tích hợp method-security infrastructure chuyên biệt | Advisors/pointcuts, version |
| Business service guard trong transaction | State-dependent/side-effecting operations | Atomicity, concurrency, shared entrypoints |
| External PDP | Quyền tập trung nhiều service | Availability, trust, cache, latency |

Không cần viết custom manager chỉ để thể hiện điều kiện một scope. Cơ chế phù hợp nhất là cơ chế **dễ kiểm chứng rằng hành động trái phép không thể đi qua**.

## 21. Những hiểu nhầm cần tránh

**“AuthorizationManager dùng để decode và verify JWT.”** Không. Đó là trách nhiệm của Resource Server authentication/`JwtDecoder`.

**“Token có scope đọc là được đọc mọi bản ghi.”** Không. Tenant/ownership/ACL có thể giới hạn.

**“Path variable tenantId chứng minh membership.”** Không. Nó chỉ mô tả tài nguyên mục tiêu.

**“Một HTTP manager đủ cho cả message consumer và scheduler.”** Không nếu các entrypoint đó bỏ qua HTTP chain. Business policy phải được áp dụng ở boundary dùng chung.

**“`@PreAuthorize` luôn chạy khi method được gọi từ cùng class.”** Không bảo đảm trong proxy-based security.

**“`@PostAuthorize` đủ bảo vệ refund.”** Không khi side effect đã xảy ra.

**“Policy DB lỗi thì cho qua để đảm bảo SLA.”** Sai với một rule bảo mật bắt buộc.

**“Cache allow của user là đủ cho mọi tenant.”** Sai; decision cần gắn resource/action/tenant/version.

**“`allOf` và `anyOf` đều an toàn nếu manager trả null.”** Không mặc định; phải xác định abstain/default behavior.

**“Thấy 403 thì nên thêm quyền ở JWT converter.”** Không. Cần xác minh quyền có được nguồn có thẩm quyền cấp hay không.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Khi nào `hasAuthority("SCOPE_orders.read")` chưa đủ?

> Khi còn điều kiện tenant, owner, ACL, trạng thái entity hoặc chính sách nghiệp vụ không được scope thể hiện.

**Câu 2.** `AuthorizationManager<RequestAuthorizationContext>` nhận những gì?

> Supplier của `Authentication` và context chứa HTTP request cùng path variables mà matcher trích xuất.

**Câu 3.** Với Spring Security mới, phương thức nên implement là gì?

> `authorize(...)` trả `AuthorizationResult`; `check(...)` đã deprecated trong các version mới.

**Câu 4.** Vì sao không tin `tenantId` client gửi?

> Client tùy ý đổi được tenant mục tiêu; quyền phải được kiểm tra bằng nguồn membership có thẩm quyền.

**Câu 5.** Đã có HTTP membership manager, vì sao service vẫn phải filter theo tenant?

> Vì order ID có thể thuộc tenant khác. Nếu query không ràng buộc tenant, có thể xuất hiện BOLA/IDOR.

**Câu 6.** Policy phụ thuộc trạng thái refund nên kiểm tra ở đâu?

> Ở service/domain transaction, với concurrency/atomicity phù hợp. HTTP manager có thể chặn sớm nhưng không thay transaction checks.

**Câu 7.** `null` trong custom manager có chắc nghĩa deny không?

> Không. Nó có thể là abstain; cần hiểu thành phần tổng hợp và test default decision.

**Câu 8.** PDP timeout có nên allow không?

> Không. Phải fail closed hoặc trả lỗi unavailable mà không thực hiện nghiệp vụ trái phép.

**Câu 9.** MockMvc `jwt()` có kiểm tra chữ ký token production không?

> Không. Nó mô phỏng authentication; cần integration test với decoder và signed test token.

**Câu 10.** Khi nào `@PreAuthorize` gọi bean policy phù hợp hơn custom method interceptor?

> Khi quyền gắn với một số method cụ thể, Java policy dễ đọc và dễ test; interceptor phù hợp khi có một cơ chế chung ở tầng method-security infrastructure.

## 23. Tài liệu tham khảo

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager`, `AuthorizationResult` và mô hình authorization.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests`, `access(...)` và custom authorization.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize`, bean policy và custom method authorization.
- [Spring Security — AuthorizationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html): `authorize` và `verify`.
- [Spring Security — AuthorizationResult API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationResult.html): kết quả quyết định quyền.
- [Spring Security — RequestAuthorizationContext API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/intercept/RequestAuthorizationContext.html): request và path variables.
- [Spring Security — AuthorizationManagers API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManagers.html): `allOf`, `anyOf`, `not` và abstain behavior.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT và scope mapping.
- [Spring Security — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): MockMvc JWT authentication test.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer semantics và errors.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): issuer và subject claims.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token, audience và scope.

**Kết luận:** custom `AuthorizationManager` hoặc business policy component nên nhận **principal đã xác thực**, hành động và tài nguyên mục tiêu, truy vấn **nguồn quyền đáng tin**, rồi đưa ra quyết định allow/deny rõ ràng. Với tenant, ownership và trạng thái có thể thay đổi, bảo vệ nghiệp vụ phải nằm cả ở **service/transaction boundary**, không chỉ HTTP. Chọn điểm kiểm tra phù hợp, tránh tự cấp thêm quyền và fail closed khi không chứng minh được quyền.
