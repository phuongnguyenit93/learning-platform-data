# Kiểm soát đường gọi trực tiếp và xác minh tại ranh giới API được thiết kế

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, một API cần tự xác minh request tại ranh giới mà nó thực sự nhận traffic. Điều này đặc biệt quan trọng khi hệ thống có API Gateway, reverse proxy, ingress controller, service mesh hoặc nhiều đường truy cập nội bộ. Nếu backend chỉ dựa vào việc request đã đi qua gateway, một caller có thể tìm đường gọi thẳng tới service và bỏ qua các kiểm tra được đặt ở lớp trước.

Một kiến trúc an toàn cần trả lời rõ:

- Client nào được phép kết nối tới API?
- Request có đi qua gateway hay có thể gọi trực tiếp origin?
- Thành phần nào xác minh chữ ký, issuer, audience và thời hạn của Access Token?
- API nào là resource server nhận token và kiểm tra scope?
- Quyền truy cập được kiểm tra ở route, method và đối tượng dữ liệu nào?
- Header do proxy thêm có thể được tin cậy từ những hop nào?
- Service gọi service khác dùng danh tính và token nào?

**Ranh giới xác minh phải nằm tại API được thiết kế để nhận và bảo vệ tài nguyên.** Gateway có thể xác thực sớm, lọc traffic, rate limit và chuẩn hóa request, nhưng backend vẫn phải xác minh credential và authorization theo resource của chính nó nếu backend có thể được truy cập trực tiếp hoặc nằm trong một trust boundary riêng.

Bài học thuộc chương **Triển khai an toàn**, dùng **Java 17+, Spring Boot 3.x và Spring Security 6.x** làm bối cảnh. Nội dung tập trung vào direct-origin access, defense in depth, OAuth audience/scope, tenant/object authorization, token relay và delegation, network ingress, proxy headers, cấu hình Servlet/WebFlux, CORS/CSRF và kiểm thử các đường bypass.

## 1. Ranh giới API là nơi request được quyết định có quyền hay không

Hãy xem một ứng dụng gồm Gateway, Orders API và Billing API:

~~~text
                         Internet
                            |
                            v
                    API Gateway / WAF
                      /           \
                     v             v
               Orders API       Billing API
                     |             |
                     v             v
                Orders DB      Billing DB
~~~

Trong một deployment lý tưởng, traffic công khai đi qua gateway. Nhưng nếu Orders API có public load balancer, port container bị publish, DNS nội bộ bị lộ hoặc network policy cho phép caller truy cập trực tiếp, đường đi thực tế có thể là:

~~~text
Caller -----------------------> Orders API
          bỏ qua Gateway
~~~

Nếu Gateway là nơi duy nhất kiểm tra JWT, direct caller có thể tới backend mà không trải qua xác minh. Nếu backend tin header do gateway thường thêm như X-User, X-Roles hoặc X-Authenticated, caller có thể tự gửi những header đó.

Cần phân biệt:

- **Network boundary:** ai có thể mở kết nối tới service.
- **Authentication boundary:** API xác minh danh tính/credential nào.
- **Authorization boundary:** API quyết định subject được làm operation nào trên resource nào.
- **Trust boundary:** thành phần nào được phép cung cấp assertion/header mà API tin.

Một lớp không thay thế các lớp còn lại. Network chặn direct access rất hữu ích, nhưng không thay thế kiểm tra token ở API. JWT hợp lệ cũng không tự cấp quyền truy cập mọi endpoint hoặc mọi tenant.

## 2. Gateway là lớp bảo vệ bổ sung

Gateway có thể kết thúc TLS, xác minh token sơ bộ, route path, áp rate limit/WAF, giới hạn request size, chuẩn hóa trace headers và relay token theo cấu hình. Backend vẫn cần kiểm tra những điều liên quan tới tài nguyên mà backend bảo vệ:

- Token được phát hành bởi issuer được tin cậy.
- Audience dành cho API hiện tại.
- Token chưa hết hạn và đã đến thời điểm có hiệu lực.
- Scope/authority đủ cho operation.
- Subject/tenant có quyền với đối tượng cụ thể.
- Token type và delegation phù hợp với contract.

| Kiểm tra | Gateway | API backend |
| --- | --- | --- |
| Chặn request không có token | Có thể | Có, nếu endpoint yêu cầu authentication |
| Xác minh chữ ký/issuer | Có thể | Phải tự làm nếu API nhận Bearer Token |
| Audience của API đích | Có thể kiểm tra route | Phải kiểm tra audience của resource |
| Scope của operation | Có thể lọc sơ bộ | Phải kiểm tra quyền backend thực sự cần |
| Quyền trên order/account cụ thể | Thường không có đủ domain context | Backend phải kiểm tra |
| Tenant isolation | Có thể có policy chung | Backend phải áp vào truy vấn/dữ liệu |
| Business invariants | Không thay domain logic | Backend chịu trách nhiệm |

Không giả định request hợp lệ chỉ vì gateway đã chuyển tiếp nó. Backend phải có đủ dữ liệu đã xác minh để quyết định quyền truy cập của chính nó.

### 2.1. Nếu backend chỉ chấp nhận gateway

Có thể thiết kế topology trong đó chỉ gateway được phép kết nối tới backend. Khi đó network policy, firewall/security group, private subnet, service mesh authorization và workload identity phải thực sự cưỡng chế điều này.

Ngay cả trong topology đó, backend vẫn nên xác minh Access Token hoặc một assertion nội bộ có chữ ký/nguồn tin cậy rõ ràng nếu backend chịu trách nhiệm authorization. Chỉ dựa vào source IP hoặc header không có cơ chế xác thực là yếu, đặc biệt trong môi trường nhiều workload.

### 2.2. Direct call có thể là use case hợp lệ

Không phải mọi direct call đều là bypass. Một mobile app, partner integration hoặc service nội bộ có thể được thiết kế để gọi API origin trực tiếp. Khi đó:

1. Đường gọi phải được định nghĩa trong API contract.
2. Client phải có cơ chế authentication được chấp nhận.
3. Resource Server xác minh token tại origin.
4. Audience và scope phải dành cho API đó.
5. Network, rate limit và monitoring phải áp dụng cho direct path.
6. Không dựa vào header chỉ gateway mới được cho là thêm.

Mục tiêu là kiểm soát mọi đường được hỗ trợ, không giả định chỉ tồn tại một route.

## 3. Kiểm soát đường gọi trực tiếp ở network layer

~~~text
Internet
   |
   v
Public Load Balancer
   |
   v
Gateway / WAF
   |
   v
Private Service Network
   |
   +-- Orders API (private ingress only)
   |
   +-- Billing API (private ingress only)
   |
   +-- Inventory API (private ingress only)
~~~

Các biện pháp thường dùng:

- Không publish port backend ra public network nếu không cần.
- Dùng private load balancer hoặc internal service discovery.
- Security group/firewall chỉ cho phép source workload/gateway được chỉ định.
- Kubernetes NetworkPolicy giới hạn ingress giữa namespaces/pods.
- Service mesh authorization policy giới hạn workload source và destination.
- Dùng mTLS/workload identity cho kết nối service-to-service.
- Tách management/actuator ports khỏi public API ingress.
- Kiểm soát DNS và route để không có đường truy cập ngoài dự kiến.

### 3.1. Network policy không thay authorization

Một service được phép kết nối tới Orders API vẫn có thể không được phép đọc mọi order. Network policy quyết định workload nào được mở kết nối; token/scope/domain authorization quyết định caller được làm gì.

~~~text
Network allow:
  inventory-service -> orders-api

Application authorization:
  inventory-service token aud=orders-api
  scope=orders.read
  operation=read-order-for-fulfillment
  tenant/order ownership policy passes
~~~

## 4. Access Token phải dành cho API đang nhận request

Một JWT có thể hợp lệ về chữ ký nhưng không dành cho resource hiện tại:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": ["inventory-api"],
  "scope": "inventory.read",
  "exp": 1893456000
}
~~~

Nếu token trên được gửi tới Orders API, Orders API phải từ chối nếu audience contract yêu cầu orders-api. Chữ ký hợp lệ chỉ chứng minh token được phát hành bởi issuer và chưa bị sửa; nó không chứng minh token được cấp cho mọi service.

### 4.1. Audience là ranh giới giữa các resource server

~~~text
Access Token T_inventory
  aud = inventory-api
  scope = inventory.read
       |
       +----> Inventory API: có thể chấp nhận
       |
       +----> Orders API: từ chối audience không phù hợp
       |
       +----> Billing API: từ chối audience không phù hợp
~~~

Không dùng một audience chung quá rộng cho mọi API nếu các resource có trust boundary và quyền khác nhau. Nếu kiến trúc dùng một gateway/resource façade làm audience chung, phải xác định rõ gateway là resource thực sự và các backend nhận assertion/delegation nào.

### 4.2. Scope phải được kiểm tra ở API

Audience trả lời token dành cho resource nào; scope trả lời nhóm hành động được cấp.

| API operation | Scope tối thiểu minh họa |
| --- | --- |
| Đọc order | orders.read |
| Tạo order | orders.write |
| Xem invoice | billing.read |
| Xem tồn kho | inventory.read |

Backend không được suy ra quyền write chỉ từ việc token đã authenticated. Kiểm tra scope/authority cho từng route hoặc method.

### 4.3. Issuer và algorithm cũng phải được giới hạn

Resource Server cần chỉ tin issuer đã cấu hình, lấy JWKS từ endpoint tin cậy gắn với issuer, chấp nhận signing algorithms theo allowlist, kiểm tra audience, expiration/not-before và profile claims. Không dùng token header để tự quyết định JWKS URL hoặc issuer trust.

Nếu hệ thống multi-issuer, dùng registration/resolver được quản trị; không fetch discovery từ issuer URL bất kỳ lấy từ request.

## 5. Xác minh tại route, method và object boundary

~~~text
Authentication:
  Token signature valid
  iss trusted
  aud = orders-api
  exp valid
       |
       v
Route authorization:
  scope includes orders.read
       |
       v
Object authorization:
  user belongs to tenant
  AND user may read order-42
       |
       v
Return order
~~~

### 5.1. Route-level authorization

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/actuator/health").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt())
        .build();
}
~~~

Ví dụ này minh họa Servlet stack. Trong production, xác định rõ endpoint health nào được public, thứ tự matcher, HTTP methods và rule cho mọi route. Không để matcher rộng đặt trước rule chặt hơn.

### 5.2. Method-level authorization

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

~~~java
@Service
public class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Order getOrder(String orderId) {
        return repository.findById(orderId)
            .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

Method security hữu ích khi service có nhiều caller khác nhau, ví dụ HTTP controller, message listener hoặc scheduled job. Nhưng scope check vẫn chưa đủ nếu quyền phụ thuộc tenant, owner hoặc trạng thái đối tượng.

### 5.3. Object-level authorization

Không được cho phép caller tự chọn order ID rồi chỉ kiểm tra scope. Backend cần kiểm tra tenant/owner/relationship trong truy vấn hoặc domain service:

~~~java
public Mono<Order> getOrder(
        String orderId,
        String authenticatedTenantId) {
    return repository.findByIdAndTenantId(
        orderId,
        authenticatedTenantId);
}
~~~

Tenant ID lấy từ principal/claim đã xác minh hoặc context nội bộ đáng tin cậy theo contract. Không lấy tenant ID từ request body rồi coi đó là bằng chứng người dùng thuộc tenant.

## 6. Cấu hình JWT Resource Server cho Servlet API

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(
                "https://identity.example.test/oauth2/jwks")
                .build();

        OAuth2TokenValidator<Jwt> issuer =
            new JwtIssuerValidator(
                "https://identity.example.test");

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        OAuth2ErrorCodes.INVALID_TOKEN,
                        "Token is not intended for orders-api",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                new JwtTimestampValidator(Duration.ofSeconds(30)),
                issuer,
                audience));

        return decoder;
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt())
            .build();
    }
}
~~~

Trong ví dụ, JWKS URI và issuer là cấu hình server-side; timestamp validator kiểm tra thời gian; audience validator ràng buộc token vào Orders API; route rules yêu cầu scope phù hợp; stateless session policy tránh dùng HTTP session làm danh tính ngầm cho Bearer API.

Đây là ví dụ nền tảng; cần cấu hình error handling, CORS, CSRF và method/object authorization theo ứng dụng. Không tắt CSRF chỉ vì ứng dụng dùng Spring Security: việc disable phù hợp khi API chỉ nhận Bearer token qua Authorization header và không dùng cookie/session credential tự động được browser gửi. Nếu có cookie authentication, CSRF vẫn cần được xử lý.

## 7. Cấu hình Resource Server cho WebFlux

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/actuator/health").permitAll()
                .pathMatchers(
                    HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(
                    HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt())
            .build();
    }
}
~~~

Trong WebFlux, authentication và authorization được thực hiện trong WebFilter chain. Không dùng Servlet SecurityFilterChain cho reactive application, và không đọc SecurityContext qua ThreadLocal trong reactive code.

### 7.1. Reactive method security

~~~java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

Method có thể trả Mono/Flux và dùng PreAuthorize. Các kiểm tra quyền phải diễn ra trong reactive execution; tránh gọi block để lấy principal hoặc chờ repository.

## 8. Không tin header identity do client gửi

Một số hệ thống dùng header nội bộ:

~~~http
X-Authenticated-User: alice
X-Authenticated-Roles: ADMIN
X-Tenant-Id: tenant-42
~~~

Nếu API nhận những header này trực tiếp từ internet và tin chúng, caller có thể giả danh user/role/tenant.

### 8.1. Strip header đầu vào tại proxy

Gateway có thể xóa mọi header identity do client gửi, xác thực Access Token, chỉ tạo assertion nội bộ theo contract và gửi assertion qua kết nối đã được xác thực tới backend.

Backend cần xác minh nguồn assertion, ví dụ chữ ký, mTLS workload identity hoặc một cơ chế token nội bộ. Nếu backend cũng nhận direct traffic, nó phải từ chối header identity không có nguồn tin cậy.

### 8.2. Header forwarding không phải authentication

Các header như X-Forwarded-For, X-Forwarded-Proto, Forwarded, X-Forwarded-Host có thể được dùng để xây dựng client IP hoặc external URL, nhưng chỉ được tin khi request đến từ proxy được cấu hình và proxy đã ghi đè giá trị do client gửi.

Không dùng X-Forwarded-For để quyết định user identity hoặc quyền truy cập. Client có thể gửi header giả nếu edge proxy không strip/overwrite đúng cách.

### 8.3. Forwarded headers và host poisoning

Host/forwarded host có thể ảnh hưởng redirect URL, link tạo trong email, callback URL và origin checks. Hãy cấu hình trusted proxy ranges và allowed hosts. Không dùng giá trị Host do request cung cấp để tự tạo issuer URI, JWKS URI hoặc redirect URI.

## 9. Token relay và service-to-service calls

Khi Orders API gọi Inventory API, cần chọn credential phù hợp:

~~~text
User token T_orders
  aud = orders-api
       |
       v
Orders API
       |
       +-- relay T_orders tới Inventory API?
       |       Không, nếu audience không bao gồm inventory-api.
       |
       +-- exchange/delegate tại Authorization Server
               |
               v
           T_inventory
             aud = inventory-api
             scope = inventory.read
               |
               v
           Inventory API
~~~

### 9.1. Khi nào relay token hiện tại?

Relay chỉ phù hợp nếu token hiện tại vốn được phát hành cho downstream resource và policy cho phép delegation. Không relay token chỉ vì hai service nằm trong cùng private network.

### 9.2. Khi nào cần token exchange?

Nếu downstream là resource khác, dùng OAuth Token Exchange hoặc cơ chế delegation được Authorization Server hỗ trợ để lấy token mới với audience/resource và scope phù hợp. Backend chọn resource theo server-side policy; không để caller tự chọn audience bất kỳ.

### 9.3. Client credentials không tự đại diện user

Service có thể gọi downstream bằng client credentials. Token đó đại diện client/service theo policy, không mặc nhiên đại diện user cuối. Nếu nghiệp vụ yêu cầu authorization theo user, cần delegation/actor semantics và audit trail rõ ràng.

### 9.4. Không truyền token tới URL tùy ý

Downstream URI phải đến từ service registry/configuration được tin cậy. Không nhận URL từ request rồi gắn Access Token hiện tại vào request outbound. Nếu cần fetch URL do user nhập, tách HTTP client không mang OAuth credential và áp SSRF controls.

## 10. CORS không phải authorization

CORS là cơ chế browser kiểm soát JavaScript origin nào được đọc response. Nó không chặn mọi client khác như curl, mobile app, backend service hoặc script tự viết.

~~~text
Browser JavaScript from https://app.example
        |
        | CORS policy checked by browser
        v
API

curl / backend client
        |
        | Does not enforce browser CORS policy
        v
API
~~~

Do đó, CORS allowlist không thay JWT authentication; CORS không thay scope/role/object authorization; không coi request không có Origin là trusted; và actual request vẫn cần authentication/authorization dù preflight OPTIONS được cho phép.

## 11. CSRF phụ thuộc credential được browser tự động gửi

CSRF chủ yếu liên quan credential mà browser tự động đính kèm, chẳng hạn session cookie. Bearer token do JavaScript chủ động thêm vào Authorization header có đặc tính khác, nhưng nếu ứng dụng lưu token trong cookie hoặc dùng session cookie, CSRF vẫn có thể xảy ra.

| Kiểu authentication | CSRF cần xem xét? |
| --- | --- |
| Session cookie | Có. |
| Access Token trong cookie | Có, vì browser tự gửi cookie. |
| Bearer token trong Authorization header do client chủ động gắn | Rủi ro CSRF truyền thống thấp hơn; vẫn cần bảo vệ XSS/token storage. |
| Mixed cookie + Bearer API | Phải đánh giá toàn bộ credential và endpoint. |

Không disable CSRF toàn cục chỉ để làm API test dễ hơn. Nếu có endpoint cookie-authenticated và Bearer API trong cùng ứng dụng, có thể tách SecurityFilterChain theo matcher/priority và cấu hình CSRF riêng cho từng chain.

## 12. Tách SecurityFilterChain cho API và browser routes

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .csrf(csrf -> csrf.disable())
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .build();
}
~~~

Đây là skeleton minh họa. API chain chỉ disable CSRF nếu API thực sự không dùng cookie/session authentication. Browser chain tiếp tục có CSRF protection mặc định phù hợp session/cookie login.

Đảm bảo mọi request khớp một chain có policy rõ ràng. Một chain thiếu matcher hoặc thứ tự sai có thể khiến endpoint rơi vào policy không dự kiến.

## 13. Kiểm soát direct call ở service mesh

~~~text
Orders workload identity
       |
       | mTLS identity: orders-service
       v
Inventory workload
       |
       +-- verifies source workload
       +-- validates user/delegated Access Token
       +-- checks inventory.read
~~~

mTLS xác minh workload peer và bảo vệ transport. Nó không tự chứng minh user cuối có quyền đọc dữ liệu. Nếu API cần cả service identity lẫn user delegation, kiểm tra workload identity, subject/delegation, audience, scope/authority và tenant/object permission.

Không dùng một service account chung quyền admin cho tất cả workload.

## 14. Trust proxy configuration

Khi app đứng sau reverse proxy, framework có thể cần biết scheme, host và client address ban đầu. Nhưng chỉ tin proxy được quản trị:

- Edge proxy xóa forwarded headers đầu vào do client gửi.
- Proxy ghi lại header bằng giá trị nó tự xác định.
- Backend chỉ nhận traffic từ proxy/workload được phép.
- Forwarded header strategy được cấu hình theo deployment.
- Host allowlist và redirect policy không dựa vào giá trị tùy ý.

Không cấu hình trust all proxies trong môi trường mà direct caller có thể truy cập origin. Nếu backend vẫn nhận direct traffic, caller có thể tự tạo forwarded headers.

## 15. API boundary cho multi-tenant

~~~text
Verified token
  sub = user-42
  tenant_id = tenant-A
  aud = orders-api
  scope = orders.read
       |
       v
Orders API
       |
       +-- route scope check
       +-- tenant context from verified principal
       +-- query constrained to tenant-A
       +-- object permission check
       |
       v
Return only tenant-A order
~~~

Các nguyên tắc:

- Tenant claim chỉ tin sau khi token signature/issuer/audience được xác minh.
- Không cho request body/query ghi đè tenant context đã xác thực.
- Mọi repository query cần áp tenant constraint theo domain model.
- Kiểm tra tenant ở cả read và write path.
- Không để batch/export/admin endpoint bỏ qua tenant filters.
- Service-to-service calls phải giữ tenant/delegation context theo contract đã xác minh.

Nếu token không có tenant claim nhưng hệ thống có membership database, resolve membership từ subject đã xác thực và kiểm tra quyền tại domain service.

## 16. Error response tại API boundary

| Trường hợp | Kết quả thường dùng |
| --- | --- |
| Không có credential ở route protected | 401 |
| Token sai chữ ký/issuer/audience/expired | 401 |
| Token hợp lệ nhưng thiếu scope | 403 |
| Subject không có quyền trên object | 403 hoặc 404 theo anti-enumeration policy |
| Issuer/introspection không sẵn sàng | Lỗi dependency 5xx/503 theo error contract |
| Direct path bị network policy chặn | Kết nối bị từ chối/không route được |

Không trả stack trace, signing key details, client secret, token, raw introspection response hoặc internal topology cho caller. Log nội bộ có correlation ID và error category; không log Authorization header.

## 17. Kiểm thử các đường bypass

Một test suite chỉ gọi endpoint qua Gateway chưa chứng minh backend an toàn. Cần kiểm tra trực tiếp origin hoặc test cấu hình network để chứng minh đường đó bị chặn.

### 17.1. Test matrix

| Đường gọi | Credential/header | Kỳ vọng |
| --- | --- | --- |
| Public gateway, không token | Không có | 401 ở route protected |
| Public gateway, JWT hợp lệ cho Orders API | Token aud=orders-api, scope đủ | Được phép nếu object policy pass |
| Public gateway, token aud=Inventory API | Token hợp lệ nhưng sai audience | 401 |
| Public gateway, thiếu scope | Token aud đúng | 403 |
| Direct origin, không token | Không có | Bị network chặn hoặc API trả 401 |
| Direct origin, token hợp lệ cho Orders API | Bearer token | Chỉ được phép nếu direct origin là path được thiết kế |
| Direct origin, giả X-Authenticated-User | Header giả, không token | Không authenticated |
| Gateway path, client tự gửi X-User: admin | Header giả | Proxy strip/overwrite; không tăng quyền |
| Forwarded header giả từ direct caller | X-Forwarded-Host/IP | Không được tin |
| Token tenant A truy cập order tenant B | Token hợp lệ, scope đủ | Bị từ chối theo object/tenant policy |
| Service token aud sai | Workload mTLS đúng | Bị từ chối ở resource authorization |
| Token exchange cho resource không allowlist | Request sửa audience | Không exchange/call downstream |
| CORS không cho origin | Browser request | Browser không đọc response; API auth vẫn độc lập |
| Request không có Origin | Không có | Không mặc định trusted |

### 17.2. Test authorization với MockMvc

~~~java
mockMvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());

mockMvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_inventory.read"))))
    .andExpect(status().isForbidden());
~~~

Đây là test authorization với Authentication giả. Nó không xác minh chữ ký hoặc audience decoder. Dùng signed JWT và Resource Server thật để kiểm tra issuer/audience/time validation.

### 17.3. Test WebFlux với mockJwt

~~~java
webTestClient.mutateWith(
        mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

Tương tự MockMvc, helper mockJwt bỏ qua decoder thật. Cần test riêng JWT decoder và test integration với Bearer header thực.

### 17.4. Test direct origin

Trong integration/environment test:

1. Gọi public hostname qua gateway.
2. Gọi private origin/service address từ một workload test được phép.
3. Xác minh direct path bị network policy chặn nếu topology yêu cầu gateway-only.
4. Nếu direct path được hỗ trợ, gửi token thiếu/sai audience và xác nhận API tự từ chối.
5. Gửi header identity giả và xác nhận không được tin.
6. Xác minh audit/metrics ghi nhận ingress route phù hợp.

Không dùng test chỉ dựa vào URL public gateway để kết luận direct origin không truy cập được. Cần kiểm tra network policy/firewall/deployment configuration ở môi trường thực.

## 18. Những anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Gateway xác thực, backend tin mọi request nội bộ | Direct-origin bypass | Backend xác minh token/assertion tin cậy |
| Backend tin X-User/X-Roles do request gửi | Header spoofing, privilege escalation | Strip và xác thực assertion từ proxy |
| Một audience chung cho mọi service | Token dùng chéo resource | Audience riêng theo resource boundary |
| Chỉ kiểm tra scope, không kiểm tra object | IDOR/BOLA | Tenant/owner/object authorization |
| Dùng source IP làm danh tính user | Shared NAT/proxy và spoofing | OAuth principal + workload identity |
| Dùng mTLS thay toàn bộ user authorization | Service identity bị nhầm với user identity | Kiểm tra cả workload và subject/delegation |
| Cho caller chọn issuer/JWKS URL | SSRF và trust injection | Trusted issuer registry |
| Dùng CORS làm authentication | Non-browser caller bỏ qua CORS | Resource Server authentication |
| Disable CSRF dù dùng cookie auth | Cross-site request forgery | CSRF policy theo credential |
| Trust mọi forwarded headers | Host/IP spoofing | Chỉ trust proxy được quản trị |
| Token relay tới mọi downstream | Credential disclosure/audience mismatch | Relay đúng audience hoặc token exchange |
| Client credentials đại diện user cuối | Audit và authorization sai | Delegation/actor model rõ ràng |
| Chỉ test gateway route | Bỏ sót direct access | Test gateway và origin/network path |
| Health/actuator public toàn bộ | Lộ thông tin và thao tác quản trị | Expose tối thiểu, tách management ingress |

## 19. Quy trình thiết kế và triển khai

1. **Vẽ tất cả ingress paths:** public gateway, internal gateway, direct service DNS, load balancer, management port và service mesh.
2. **Xác định resource boundary:** API nào là resource server, issuer nào được tin và audience nào đại diện resource đó.
3. **Định nghĩa client classes:** browser, mobile, partner, service workload và administrative client.
4. **Chọn credential contract:** Bearer Access Token, workload mTLS, token exchange hoặc assertion nội bộ có chữ ký.
5. **Đặt authentication ở API:** JWT decoder/opaque introspector được cấu hình với issuer/resource trust.
6. **Đặt authorization theo operation:** route/method scope và role policy.
7. **Kiểm tra object/tenant:** domain service và data access layer áp ownership/membership.
8. **Giới hạn network:** private origin, firewall/security group, NetworkPolicy, mesh authorization.
9. **Làm sạch proxy headers:** strip input, overwrite tại trusted proxy, không trust direct caller.
10. **Cấu hình CORS/CSRF đúng credential:** CORS cho browser; CSRF cho credential browser tự gửi.
11. **Thiết kế service-to-service delegation:** token audience phù hợp, least privilege và audit actor/subject.
12. **Test bypass:** gateway, direct origin, forged headers, wrong audience, missing scope, cross-tenant object và service identity.
13. **Quan sát production:** phân biệt ingress path, auth failure, authorization denial và network rejection.

**Ghi nhớ:** Gateway là lớp lọc và bảo vệ bổ sung. API phải xác minh token và quyền tại ranh giới resource mà nó bảo vệ, kể cả khi có đường gọi trực tiếp. Kiểm tra **issuer, audience, thời hạn, scope, tenant và quyền trên object**; không tin header identity hoặc forwarded header từ caller. Network policy/mTLS giới hạn workload có thể kết nối, còn OAuth authorization quyết định caller được làm gì. Kiểm thử phải bao gồm cả gateway path lẫn direct-origin path, và lỗi của hệ thống xác thực không được biến thành quyền truy cập mặc định.

## Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700).
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705).
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693).
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html).
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/index.html).
- [Spring Security — Reactive OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html).
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html).
- [OWASP API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x00-header/).
- [OWASP API1:2023 Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/).
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html).
