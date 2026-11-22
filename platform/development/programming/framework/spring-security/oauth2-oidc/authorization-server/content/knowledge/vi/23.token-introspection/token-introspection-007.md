# Tích hợp Resource Server sử dụng opaque token

## 1. Bối cảnh: xác minh token qua Authorization Server

Trong hệ thống OAuth 2.0/OpenID Connect sử dụng **Spring Security**, **Spring Authorization Server** và Spring Boot, Resource Server (RS) nhận access token từ OAuth client rồi quyết định request có được phép truy cập API hay không.

Nếu access token là JWT, RS có thể xác minh chữ ký và claims tại chỗ bằng public key từ JWK Set. Với **opaque access token**, chuỗi token không tự mô tả claims theo định dạng mà RS có thể đọc và xác minh cục bộ. RS cần hỏi Authorization Server (AS) về trạng thái và metadata của token qua **OAuth 2.0 Token Introspection**, được chuẩn hóa trong RFC 7662.

Spring Security cung cấp opaque token support để kết nối RS với Introspection Endpoint. Ứng dụng cấu hình URI endpoint và credential của chính RS; Spring gửi token cần kiểm tra tới AS, đọc response và tạo đối tượng Authentication cho SecurityContext.

Ví dụ hệ thống đặt hàng có:

- **order-web**: OAuth client lấy access token cho người dùng.
- **checkout-api**: Resource Server bảo vệ API checkout.
- **auth.example.com**: Authorization Server phát hành và quản lý access token.
- **checkout-introspector**: client identity riêng để checkout API xác thực khi gọi Introspection Endpoint.

Khi checkout-api nhận request, nó trích bearer token, gửi token đến AS bằng POST form đã được bảo vệ, rồi chỉ xử lý request khi token active và policy của API được thỏa mãn.

Bài học tập trung vào tích hợp **Resource Server sử dụng opaque token** trong Spring Security, từ dependency và cấu hình đến authorities, audience, custom introspector, timeout, cache, lỗi và kiểm thử.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích luồng opaque token từ HTTP request tới Introspection Endpoint.
2. Cấu hình Spring Boot bằng các property introspection-uri, client-id và client-secret.
3. Bật opaque token support trong SecurityFilterChain.
4. Phân biệt introspection client credential với access token được kiểm tra.
5. Hiểu OpaqueTokenIntrospector, OAuth2AuthenticatedPrincipal và BearerTokenAuthentication.
6. Ánh xạ scope thành authorities và bảo vệ endpoint.
7. Bổ sung kiểm tra audience hoặc policy riêng bằng custom introspector.
8. Xử lý opaque token trong controller và method security.
9. Thiết kế cache, timeout, retry, circuit breaker và failure policy.
10. Kiểm thử active/inactive, scope, audience, requester authentication và AS outage.

## 2. Opaque token và introspection trong kiến trúc

Opaque token thường là chuỗi định danh ngẫu nhiên, không chứa claims theo định dạng mà RS có thể tự giải mã. AS lưu hoặc quản lý trạng thái token ở authorization store và trả thông tin cần thiết khi RS introspect.

Ví dụ access token có thể trông như:

~~~text
a4d6f7c8e9...opaque-random-token-value
~~~

RS không được suy ra subject, audience hay expiry bằng cách tự tách chuỗi token. Những dữ liệu này đến từ AS qua giao thức introspection.

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant RS as checkout-api
    participant AS as Authorization Server
    participant DB as Authorization Store

    C->>RS: GET /checkout + Authorization: Bearer token
    RS->>RS: Trích xuất bearer token
    RS->>AS: POST /oauth2/introspect<br/>client authentication + token
    AS->>AS: Xác thực introspection client
    AS->>DB: Tra token và authorization state
    DB-->>AS: Trạng thái và metadata
    AS-->>RS: active + scope/aud/sub/exp...
    RS->>RS: Tạo Authentication và kiểm tra quyền
    RS-->>C: Xử lý API hoặc trả lỗi
~~~

### 2.1. Các thành phần Spring Security

| Thành phần | Trách nhiệm |
|---|---|
| BearerTokenAuthenticationFilter | Đọc bearer token từ request và khởi chạy authentication |
| BearerTokenAuthenticationToken | Mang credential bearer tới AuthenticationManager |
| OpaqueTokenAuthenticationProvider | Gọi introspector và tạo Authentication |
| OpaqueTokenIntrospector | Gửi token tới AS, xử lý response và tạo principal |
| OAuth2AuthenticatedPrincipal | Đại diện principal cùng attributes/authorities |
| BearerTokenAuthentication | Authentication được đặt trong SecurityContext sau khi thành công |
| AuthorizationManager | Đánh giá authority/quy tắc truy cập endpoint |

Đây là pipeline opaque token của Spring Security. Không cần tự viết controller gọi introspection cho mỗi endpoint; tích hợp vào authentication pipeline giúp các quy tắc authorization hiện có hoạt động nhất quán.

### 2.2. Opaque token vẫn là OAuth access token

Opaque chỉ mô tả cách biểu diễn token đối với client/RS. Nó không làm thay đổi ngữ nghĩa OAuth:

- Token vẫn được AS phát hành cho một client và có thể đại diện subject.
- Token vẫn có scope, audience, thời hạn và trạng thái thu hồi.
- Client vẫn gửi token qua Authorization: Bearer.
- RS vẫn phải kiểm tra scope và quyền nghiệp vụ sau khi xác thực token.

Không nhầm opaque token với session cookie hoặc API key tự định nghĩa.

## 3. Dependency cần thiết

Với ứng dụng Spring Boot servlet, dependency phổ biến là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Starter cung cấp các thành phần Spring Security Resource Server và hỗ trợ opaque token. Quản lý phiên bản thông qua Spring Boot dependency management/BOM tương ứng với phiên bản dự án.

Nếu ứng dụng sử dụng WebFlux, cấu hình và interface sẽ khác: dùng ReactiveOpaqueTokenIntrospector và SecurityWebFilterChain. Bài này trình bày servlet stack với HttpSecurity và OpaqueTokenIntrospector.

## 4. Cấu hình tối thiểu bằng Spring Boot properties

Khi đã có starter, cấu hình Introspection Endpoint và credential của RS:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: checkout-introspector
          client-secret: CHECKOUT_INTROSPECTION_SECRET_FROM_SECRET_MANAGER
~~~

Ý nghĩa:

| Property | Ý nghĩa |
|---|---|
| introspection-uri | URL Token Introspection Endpoint của AS |
| client-id | OAuth client ID mà RS dùng để xác thực với endpoint |
| client-secret | Credential của introspection client |

Giá trị CHECKOUT_INTROSPECTION_SECRET_FROM_SECRET_MANAGER là placeholder minh họa. Không commit secret thực vào Git, không ghi vào log cấu hình và không dùng access token end-user làm client secret.

### 4.1. Phân biệt hai credential

Trong request API có hai credential khác nhau:

1. **Access token của caller:** nằm trong Authorization: Bearer và là token RS cần kiểm tra.
2. **Credential của introspection client:** dùng để RS xác thực với AS khi gọi /oauth2/introspect.

| Giá trị | Ai sở hữu? | Dùng ở đâu? |
|---|---|---|
| Access token của user/workload | OAuth client gọi API | Header Authorization tới RS; form token tới AS |
| Client ID/secret của checkout-introspector | Resource Server | Xác thực request introspection tới AS |

Không gửi secret introspection client cho caller bên ngoài. Không dùng access token được introspect làm Basic credential.

### 4.2. Những điều Spring Boot tự cấu hình

Với các property trên và dependency phù hợp, Spring Boot có thể tạo introspector dùng cấu hình đã cung cấp. Nếu ứng dụng chưa tự khai báo OpaqueTokenIntrospector bean, auto-configuration cung cấp introspector mặc định.

Introspector mặc định gửi token tới endpoint bằng credential đã cấu hình, kiểm tra response active và ánh xạ scope thành authority có prefix SCOPE_. Principal mặc định là OAuth2AuthenticatedPrincipal; tên principal thường lấy từ claim sub nếu có.

Nếu ứng dụng khai báo bean OpaqueTokenIntrospector riêng, bean đó thay thế auto-configured introspector. Hãy hiểu rõ việc back-off này trước khi bổ sung custom bean.

## 5. Bật opaque token trong SecurityFilterChain

Cấu hình servlet Resource Server:

~~~java
@Configuration
@EnableWebSecurity
class ResourceServerSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/orders/**/cancel")
                    .hasAuthority("SCOPE_orders.cancel")
                .anyRequest().authenticated())
            .oauth2ResourceServer(resourceServer ->
                resourceServer.opaqueToken(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Khi có Boot properties, Customizer.withDefaults() dùng introspector đã được cấu hình. Request có Authorization: Bearer sẽ đi qua opaque token authentication pipeline.

### 5.1. Đừng chỉ bật authenticated cho mọi route

authenticated() chỉ yêu cầu token được xác thực. Nếu endpoint cần scope cụ thể, hãy dùng authority như SCOPE_orders.read hoặc method security. Những endpoint nhạy cảm nên có quy tắc deny-by-default thay vì cho phép mọi token active.

### 5.2. Bảo vệ method

Có thể bật method security:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

Sau đó:

~~~java
@Service
class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Order findOrder(String orderId) {
        // Kiểm tra quyền sở hữu/tenant ở tầng domain.
        return loadOrder(orderId);
    }
}
~~~

Scope chỉ là coarse-grained permission. Service vẫn phải xác minh caller được phép đọc đúng order/tenant.

## 6. Luồng authentication khi request tới API

Giả sử client gửi:

~~~http
GET /orders/123 HTTP/1.1
Host: checkout-api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Spring Security thực hiện các bước khái quát:

1. BearerTokenAuthenticationFilter tìm bearer token.
2. BearerTokenAuthenticationToken được chuyển tới AuthenticationManager.
3. OpaqueTokenAuthenticationProvider gọi OpaqueTokenIntrospector.introspect(token).
4. Introspector gửi request tới AS và xử lý response.
5. Nếu token active, introspector trả OAuth2AuthenticatedPrincipal.
6. Provider tạo BearerTokenAuthentication với principal và authorities.
7. Authentication được đặt trong SecurityContextHolder.
8. AuthorizationManager kiểm tra authority cho endpoint.
9. Nếu hợp lệ, request đi tới controller; nếu thiếu quyền, Spring trả 403.

Nếu token inactive hoặc introspection không xác minh được theo contract, authentication thất bại. Không tự tạo principal giả để cho request tiếp tục.

### 6.1. Response introspection tối thiểu

AS có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "active": true,
  "scope": "orders.read orders.cancel",
  "client_id": "order-web",
  "sub": "user-42",
  "aud": [
    "https://checkout-api.example.com"
  ],
  "exp": 1794825600,
  "iss": "https://auth.example.com"
}
~~~

Đây là response minh họa theo RFC 7662. Tập metadata tùy token và policy AS. active là trường quan trọng để introspection client xác định token có được AS coi là active hay không.

### 6.2. Inactive response

Với token không active, AS thường trả:

~~~json
{
  "active": false
}
~~~

Spring introspector mặc định từ chối token inactive. Không cần tự viết logic parse chuỗi active ở controller. Không coi HTTP 200 là token active; phải xét boolean active trong response.

## 7. OpaqueTokenIntrospector và principal

OpaqueTokenIntrospector là abstraction chính của Spring Security servlet stack:

~~~java
public interface OpaqueTokenIntrospector {
    OAuth2AuthenticatedPrincipal introspect(String token);
}
~~~

Phương thức nhận token dạng String và trả principal đã được xác minh theo contract introspection. Nếu token không active hoặc endpoint không thể cung cấp kết quả hợp lệ, implementation ném exception thay vì trả một principal active giả.

OAuth2AuthenticatedPrincipal cung cấp:

- getName(): tên principal.
- getAttributes(): metadata từ response introspection.
- getAuthorities(): authorities dùng cho authorization.
- getAttribute(name): truy xuất claim cụ thể.

### 7.1. Truy cập principal trong controller

~~~java
@RestController
@RequestMapping("/api")
class CurrentIdentityController {

    @GetMapping("/identity")
    Map<String, Object> identity(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("name", principal.getName());
        result.put("subject", principal.getAttribute("sub"));
        result.put("clientId", principal.getAttribute("client_id"));
        return result;
    }
}
~~~

Ví dụ chỉ trả một số thuộc tính để minh họa. Không trả toàn bộ attributes của token ra API công khai; introspection response có thể chứa thông tin nội bộ hoặc PII mà caller không được phép xem.

### 7.2. Truy cập BearerTokenAuthentication

Có thể nhận Authentication:

~~~java
@GetMapping("/token-context")
Map<String, Object> tokenContext(
        BearerTokenAuthentication authentication) {

    return Map.of(
        "name", authentication.getName(),
        "authorities", authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .toList()
    );
}
~~~

BearerTokenAuthentication có thể cung cấp token attributes qua getTokenAttributes(). Chỉ expose các trường đã được kiểm tra và được phép hiển thị; không trả raw token.

### 7.3. Principal name không phải lúc nào cũng là client ID

Mặc định principal name thường lấy từ sub. Với user flow, đó có thể là user ID; với client credentials, nó có thể đại diện workload tùy AS. Nếu cần phân biệt requester client, đọc claim client_id đã được AS xác minh.

Không suy ra subject bằng cách parse opaque token hoặc lấy client ID từ request header do caller tự khai.

## 8. Scope được ánh xạ thành authorities

Spring Security opaque token support mặc định đọc claim scope trong introspection response. Scope thường là chuỗi phân tách bằng dấu cách:

~~~json
{
  "active": true,
  "scope": "orders.read orders.cancel"
}
~~~

Các authority được tạo tương ứng:

~~~text
SCOPE_orders.read
SCOPE_orders.cancel
~~~

Do đó, cấu hình:

~~~java
.requestMatchers(HttpMethod.GET, "/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

sẽ khớp scope orders.read.

### 8.1. Scope không phải role tự động

orders.read không đồng nghĩa ROLE_ADMIN. Không ánh xạ mọi scope thành role quản trị. Nếu ứng dụng có claim roles riêng, cần định nghĩa rõ issuer nào phát, ai được phép nhận và mapping nào được tin.

### 8.2. Kiểm tra authority thực tế

Trong test hoặc môi trường development, có thể kiểm tra:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

authentication.getAuthorities().forEach(authority ->
    log.debug("Granted authority: {}", authority.getAuthority()));
~~~

Đoạn code chỉ minh họa quan sát authorities; không log token hoặc toàn bộ principal attributes. Trong production, metric/audit nên giới hạn cardinality và dữ liệu nhận dạng.

## 9. Custom OpaqueTokenIntrospector: kiểm tra audience

Mặc định, introspector xác minh active status và tạo principal. **Không nên giả định chỉ cần active=true là mọi API đều được phép nhận token.** Nếu AS trả aud và API có audience riêng, RS nên kiểm tra audience theo contract.

Ví dụ checkout API chỉ chấp nhận:

~~~text
https://checkout-api.example.com
~~~

Có thể bọc introspector mặc định:

Đăng ký một configuration properties record để bind lại cùng ba property Spring Boot đang dùng:

~~~java
@ConfigurationProperties(
    prefix = "spring.security.oauth2.resourceserver.opaquetoken")
public record IntrospectionClientProperties(
    String introspectionUri,
    String clientId,
    String clientSecret) {
}
~~~

Đăng ký properties class và tạo delegate introspector. Ví dụ dưới đây bổ sung kiểm tra audience:

~~~java
@Configuration
@EnableConfigurationProperties(IntrospectionClientProperties.class)
class AudienceIntrospectionConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            IntrospectionClientProperties properties) {

        OpaqueTokenIntrospector delegate =
            SpringOpaqueTokenIntrospector
                .withIntrospectionUri(properties.introspectionUri())
                .clientId(properties.clientId())
                .clientSecret(properties.clientSecret())
                .build();

        String expectedAudience = "https://checkout-api.example.com";

        return token -> {
            OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

            Object audience = principal.getAttribute("aud");
            boolean matches =
                audience instanceof String value
                    && expectedAudience.equals(value);

            if (audience instanceof Collection<?> values) {
                matches = values.contains(expectedAudience);
            }

            if (!matches) {
                throw new OAuth2IntrospectionException(
                    "Token is not intended for this resource server");
            }

            return principal;
        };
    }
}
~~~

Đây là mẫu servlet API dùng SpringOpaqueTokenIntrospector builder. Import được lược bớt. Khi khai báo bean custom, Spring Boot không tạo introspector mặc định nữa; bean này phải tự cấu hình endpoint và client credentials hoặc bọc một delegate đã được cấu hình. Nếu dự án dùng phiên bản Spring Security cũ, API builder có thể khác; kiểm tra tài liệu đúng version trước khi sao chép.

Khi khai báo bean custom, Spring Boot không tạo introspector mặc định nữa. Bean này phải tự cấu hình endpoint và client credentials hoặc bọc một delegate đã được cấu hình.

### 9.1. Xử lý audience có kiểu String hoặc Collection

RFC 7662 cho phép metadata audience được biểu diễn theo dạng string hoặc array. Code phải xử lý đúng kiểu dữ liệu mà AS thực tế trả về. Không dùng phép so sánh substring như audience.contains("checkout") vì có thể khớp nhầm identifier.

Nếu response không có aud, quyết định policy rõ ràng:

- Từ chối nếu API yêu cầu audience binding.
- Hoặc dùng contract thay thế được AS bảo đảm, chẳng hạn introspection authorization theo requester/resource.
- Không âm thầm bỏ qua kiểm tra chỉ để request pass.

### 9.2. Audience không thay thế scope

Audience xác định token dành cho API nào; scope xác định hành động/quyền được cấp. Token cần thỏa cả hai:

~~~text
aud contains https://checkout-api.example.com
AND
scope contains orders.read
~~~

Token đúng audience nhưng thiếu scope phải bị từ chối ở authorization layer. Token có scope phù hợp nhưng audience sai cũng phải bị từ chối.

## 10. Custom authorities và principal mapping

Một số AS trả claim tùy biến như roles, permissions hoặc tenant_id. Có thể bọc delegate để thêm authority, nhưng chỉ khi claims đó đến từ issuer tin cậy và có schema rõ.

Ví dụ thêm role từ claim roles:

~~~java
final class CustomAuthoritiesIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    CustomAuthoritiesIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            this.delegate.introspect(token);

        Set<GrantedAuthority> authorities =
            new LinkedHashSet<>(principal.getAuthorities());

        Object roles = principal.getAttribute("roles");
        if (roles instanceof Collection<?> values) {
            values.stream()
                .filter(String.class::isInstance)
                .map(String.class::cast)
                .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                .forEach(authorities::add);
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            principal.getAttributes(),
            authorities);
    }
}
~~~

Đây là ví dụ minh họa; cần kiểm tra schema claim và allowlist role của ứng dụng. Không biến giá trị tùy ý do client gửi thành authority. Nếu roles có thể thay đổi nhanh, cân nhắc nguồn authorization hiện tại thay vì token metadata có cache dài.

### 10.1. Không ghi đè authorities mặc định

Khi bọc delegate, giữ lại authorities đã được Spring tạo từ scope nếu policy yêu cầu. Nếu tạo một danh sách mới chỉ từ roles, có thể vô tình làm mất SCOPE_orders.read.

### 10.2. Tenant claim không tự cấp quyền truy cập tenant

Claim tenant_id có thể giúp xác định tenant context, nhưng service vẫn cần kiểm tra tài nguyên thuộc tenant đó. Không lấy tenant từ URL/body rồi ghi đè tenant trong principal.

## 11. Authorization theo scope và dữ liệu nghiệp vụ

Một API nên kiểm tra theo nhiều lớp:

1. Token active và requester/resource binding hợp lệ.
2. Audience chứa API hiện tại.
3. Scope/authority cho phép thao tác.
4. Subject/client được phép truy cập record cụ thể.
5. Tenant, trạng thái và quy tắc domain đều hợp lệ.

Ví dụ:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    OrderView getOrder(@PathVariable String id,
                       @AuthenticationPrincipal
                       OAuth2AuthenticatedPrincipal principal) {

        return orderService.findVisibleOrder(
            id,
            principal.getName(),
            principal.getAttribute("tenant_id"));
    }
}
~~~

orderService.findVisibleOrder phải thực hiện kiểm tra ownership/tenant trong domain. Annotation scope không chứng minh user có quyền đọc mọi order.

### 11.1. Phân biệt 401 và 403

| Tình huống | Kết quả thường gặp |
|---|---|
| Không có bearer token | 401 Unauthorized |
| Token inactive/không hợp lệ | 401 Unauthorized |
| Introspection response không hợp lệ | Authentication thất bại |
| Token active nhưng thiếu scope | 403 Forbidden |
| Token active, scope đủ nhưng không sở hữu record | 403 hoặc 404 theo chính sách chống enumeration |
| Introspection AS tạm unavailable | Lỗi hạ tầng theo failure policy, có thể 503 |

Không dùng 401 cho mọi lỗi nghiệp vụ. Client nên biết khi nào cần credential mới và khi nào caller không có quyền.

## 12. Tích hợp Authorization Server

Spring Authorization Server cung cấp Token Introspection Endpoint trong protocol endpoints. Endpoint thường là /oauth2/introspect nếu dùng path mặc định; path thực tế phụ thuộc AuthorizationServerSettings.

Trong Authorization Server, configurer được áp dụng vào SecurityFilterChain xử lý OAuth endpoints. Ví dụ khung cấu hình:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, Customizer.withDefaults());

    return http.build();
}
~~~

Khi dùng cấu hình Authorization Server mặc định, Token Introspection Endpoint được đăng ký trong các protocol endpoints. Không cần tự viết controller thay thế endpoint chuẩn. Nếu cần tùy biến authentication providers hoặc response handling, dùng hook được phiên bản Spring Authorization Server công bố.

### 12.1. Authorization state phải được chia sẻ

AS cần dùng OAuth2AuthorizationService để tra token. Dịch vụ này phải nhất quán với nơi token được phát hành, refresh và revoke.

- In-memory store phù hợp demo/test đơn giản.
- JDBC store phù hợp deployment cần persistence nếu schema/transaction/index được cấu hình đúng.
- Custom store cần bảo đảm lookup, expiry, revocation và consistency giữa các node.

Nếu token được phát hành trên node A nhưng introspection node B không thấy authorization state, RS có thể nhận active=false cho token hợp lệ. Với nhiều instance, tránh authorization store chỉ tồn tại trong memory từng process.

### 12.2. Đăng ký introspection requester

RS cần được AS nhận diện như một protected resource/client. Ví dụ:

Trong RegisteredClientRepository, AS cần tìm được registration của requester và xác minh phương thức client authentication đã đăng ký, ví dụ client_secret_basic, private_key_jwt hoặc mTLS. Client secret phải được encode bằng PasswordEncoder tương ứng. RegisteredClient cũng mô hình hóa các authorization grant mà client được phép dùng; không thêm Client Credentials chỉ để minh họa introspection nếu dịch vụ không cần quyền xin access token theo grant đó. Kiểm tra validation của RegisteredClient và chính sách registration ở phiên bản đang dùng.

AS vẫn phải có policy cho phép client này introspect. Không phải mọi registered client tự động có quyền kiểm tra mọi token. Tùy cấu hình, có thể dùng private_key_jwt hoặc mTLS thay shared secret.

### 12.3. Introspection response chỉ tiết lộ metadata cần thiết

AS nên trả active và các metadata RS cần cho authorization. Không trả toàn bộ user profile hoặc claims nhạy cảm nếu checkout API không cần.

Có thể giới hạn metadata theo requester/resource, ví dụ chỉ trả subject, audience, scope, client ID và thời hạn. Nếu cần custom response policy, dùng extension point đúng phiên bản và kiểm thử để không làm sai RFC 7662.

## 13. Tùy biến introspector và lỗi endpoint

Một custom introspector có thể kiểm tra audience/resource, chuẩn hóa hoặc bổ sung authorities, ánh xạ claim tùy biến, gắn principal name theo contract và áp dụng policy tenant hoặc token type bổ sung.

Tuy nhiên, nó phải giữ các bảo đảm của delegate: client authentication tới AS, kiểm tra active và xử lý response lỗi.

### 13.1. Phân biệt token inactive và AS unavailable

| Kết quả | Ý nghĩa |
|---|---|
| active=false | AS xác nhận token không active |
| HTTP 401 từ AS | Credential introspection requester có thể sai/hết hạn |
| HTTP 403 từ AS | Requester không được phép introspect |
| HTTP 429 | Requester vượt quota |
| HTTP 5xx | AS hoặc dependency gặp sự cố |
| Timeout/network failure | Không thể xác minh token |
| Response sai schema | Không thể tin kết quả introspection |

Không chuyển timeout thành principal active. Nếu introspection thất bại, authentication không được thành công chỉ vì RS muốn tăng availability.

### 13.2. Error mapping phụ thuộc cấu hình

Spring Security xử lý exception từ introspector trong authentication pipeline. Mã HTTP cuối cùng phụ thuộc loại exception, entry point và cách ứng dụng cấu hình. Hãy test hành vi thực tế cho inactive token, requester credential failure và AS outage; đừng giả định mọi lỗi đều trả cùng 401 hoặc mọi lỗi đều là 503.

Nếu muốn trả 503 cho AS outage để phân biệt dependency failure với credential sai, cần cấu hình exception translation/entry point phù hợp và không làm lộ nội bộ.

## 14. Timeout, retry và circuit breaker

Introspection là network dependency trên đường xác thực. Nếu AS chậm, request API có thể bị chậm theo. Cần thiết kế connect timeout, response/read timeout, tổng request deadline, connection pool giới hạn, retry có giới hạn, circuit breaker/bulkhead và metric latency.

Các API builder/client để cấu hình timeout thay đổi theo Spring Security version. Spring Boot hiện hỗ trợ tùy biến builder introspector bằng builder customizer trong các phiên bản mới; nếu cần kiểm soát hoàn toàn, tạo custom introspector với HTTP client được cấu hình rõ. Kiểm tra public API của đúng version trước khi sao chép cấu hình.

### 14.1. Không retry vô hạn

Một request API có thể tạo nhiều lần introspection nếu client retry cả API request. Kết hợp retry ở gateway, RS và HTTP client có thể nhân tải. Chỉ retry các lỗi tạm thời phù hợp, có backoff/jitter và tổng deadline.

### 14.2. Bulkhead

Giới hạn số introspection call đồng thời để AS chậm không làm cạn toàn bộ servlet threads hoặc connection pool. Nếu bulkhead đầy, từ chối có kiểm soát và quan sát metric; không tạo queue vô hạn.

## 15. Cache introspection trong Resource Server

Không cache mặc định response introspection một cách tùy tiện. Cache có thể giảm latency và tải AS nhưng làm chậm việc nhìn thấy revocation.

### 15.1. Positive cache

Cache active=true cần có key và TTL an toàn:

- Key dùng hash/fingerprint của token, không lưu raw token trong key hiển thị.
- TTL không vượt thời gian còn lại tới exp nếu response có expiry.
- TTL không vượt revocation freshness SLO của sản phẩm.
- Nếu response phụ thuộc requester/audience/tenant, context đó phải tham gia cache key.
- Không chia sẻ principal của token A cho token B.
- Có cơ chế eviction/clear khi cần.

Ví dụ, nếu yêu cầu phát hiện revocation trong tối đa 15 giây, positive cache không thể có TTL 5 phút mà vẫn tuyên bố đạt SLO đó.

### 15.2. Negative cache

Cache active=false ngắn có thể giảm tải khi nhận token rác, nhưng cache quá lâu có thể từ chối token vừa được phát hành hoặc token mới đồng bộ vào store. Cần TTL nhỏ, key fingerprint và kiểm thử eventual consistency.

### 15.3. Cache không thay thế introspection contract

HTTP response introspection có Cache-Control: no-store và Pragma: no-cache. Điều này ngăn intermediary/browser cache response nhạy cảm. Internal cache ở RS là một quyết định stateful riêng của ứng dụng, phải có TTL, encryption/access control, invalidation và observability rõ.

Không cache lỗi timeout như active=true. Nếu AS unavailable, chỉ dùng kết quả positive còn hạn trong cache khi policy cho phép.

## 16. Bảo mật và privacy

- Gọi Introspection Endpoint qua HTTPS/TLS và xác minh certificate AS.
- Dùng credential riêng cho từng Resource Server hoặc workload group.
- Không để caller chọn introspection URL.
- Không gửi token qua URL query string.
- Không log access token, refresh token, Basic header hoặc request body.
- Giới hạn request body và token length.
- Rate limit introspection theo requester đã xác thực.
- Chỉ trả metadata cần thiết cho resource.
- Rotate introspection credential và có quy trình thu hồi khi compromise.
- Bảo vệ authorization store và audit log.

### 16.1. Token fingerprint cho audit

Nếu cần liên kết sự kiện introspection mà không lưu token, có thể dùng hash một chiều hoặc identifier jti từ metadata đã được xác minh. Cần chọn thuật toán, secret salt/key (nếu dùng keyed hash), retention và quyền truy cập phù hợp.

Không dùng raw token làm metric label hoặc log field. Token là bearer credential; bất kỳ nơi nào lưu token đều trở thành bề mặt rủi ro.

### 16.2. Audience và tenant

Nếu AS trả aud, RS phải xác minh token dành cho API hiện tại. Với multi-tenant, kiểm tra tenant context từ metadata tin cậy và đối chiếu với resource. Không cho phép caller gửi tenant header để ghi đè tenant được AS xác nhận.

## 17. Kiểm thử tích hợp

### 17.1. Ma trận token và authorization

| Kịch bản | Kết quả mong đợi |
|---|---|
| Token active, đúng audience, đủ scope | Request được phép |
| Token active, đúng audience, thiếu scope | 403 |
| Token active, sai audience | Bị từ chối theo audience policy |
| Token inactive | 401 |
| Token hết hạn/revoked | AS trả inactive, RS từ chối |
| Không có Authorization header | 401 cho endpoint cần authentication |
| Sai scheme không được hỗ trợ | Không xác thực |
| Introspection response thiếu active | Authentication thất bại |
| active không phải boolean | Response không hợp lệ, từ chối |
| Subject hợp lệ nhưng không sở hữu record | Domain authorization từ chối |
| Tenant không khớp | Từ chối theo policy |

### 17.2. Ma trận requester và dependency

| Kịch bản | Kết quả cần chứng minh |
|---|---|
| Introspection client credential hợp lệ | AS xác thực requester |
| Secret introspection sai | Request introspection bị từ chối |
| Requester không được phép | AS từ chối theo policy |
| AS timeout | Không tạo Authentication active |
| AS trả 5xx | Failure policy được thực thi |
| AS trả 429 | Client không retry storm |
| TLS certificate sai | RS không gửi token tới endpoint không tin cậy |
| Cache positive còn hạn | Có thể dùng theo policy |
| Cache positive hết TTL | Introspect lại |
| Token revoke trong cache window | Độ trễ nằm trong revocation SLO |
| Multi-instance authorization store | Các node thấy trạng thái nhất quán theo thiết kế |

### 17.3. Test với MockMvc

Một test endpoint có thể dùng opaque token giả lập qua custom introspector test:

~~~java
@Test
void requestWithRequiredScopeIsAllowed() throws Exception {
    mockMvc.perform(get("/orders/123")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer test-opaque-token"))
        .andExpect(status().isOk());
}
~~~

Test này chỉ xác minh filter chain/authorization khi introspector test đã trả principal có authority cần thiết. Integration test riêng phải gọi AS test thật hoặc mock HTTP introspection server để kiểm tra request form, client authentication và response parsing.

Không dùng test token giả để kết luận RFC 7662 endpoint production đã được bảo vệ.

## 18. Observability và vận hành

### 18.1. Metrics

Theo dõi:

- Introspection requests/second theo RS requester.
- Tỷ lệ active/inactive.
- HTTP 400/401/403/429/5xx.
- p50/p95/p99 introspection latency.
- Timeout và connection pool usage.
- Cache hit/miss/age.
- Audience/scope authorization failures.
- Thời gian từ revoke tới lúc RS từ chối token.
- Credential rotation và authentication failures.

Không dùng raw token, subject PII hoặc giá trị token tùy ý làm metric labels.

### 18.2. Audit events

Các event có thể gồm:

- OPAQUE_TOKEN_AUTHENTICATED
- OPAQUE_TOKEN_REJECTED
- INTROSPECTION_CLIENT_AUTH_FAILED
- INTROSPECTION_DEPENDENCY_UNAVAILABLE
- OPAQUE_TOKEN_AUTHORIZATION_DENIED

Audit nên có correlation ID, requester client đã xác thực, outcome, nhóm lỗi, endpoint, timestamp và token fingerprint đã pseudonymize nếu cần. Không ghi raw access token hoặc Basic credential.

### 18.3. Runbook khi RS đột ngột trả 401

1. Kiểm tra token thực sự active ở AS hay không.
2. Kiểm tra introspection URI và TLS.
3. Kiểm tra secret/client ID của introspection requester có bị rotate hoặc sai cấu hình không.
4. Kiểm tra AS có trả đúng JSON boolean active không.
5. Kiểm tra authorization store và consistency giữa các node.
6. Kiểm tra audience/scope mapping và custom introspector.
7. Kiểm tra exception translation/entry point.
8. Kiểm tra cache có giữ kết quả cũ không.

Không chữa lỗi bằng cách cho mọi token qua khi AS unavailable hoặc bỏ audience/scope validation.

## 19. Checklist triển khai production

- [ ] Có dependency Spring Boot Resource Server phù hợp servlet/reactive stack.
- [ ] Cấu hình đúng Introspection Endpoint URI.
- [ ] Introspection client ID/secret được bảo vệ trong secret manager.
- [ ] RS xác thực AS qua HTTPS/TLS.
- [ ] SecurityFilterChain bật opaqueToken.
- [ ] Không nhầm introspection credential với access token của caller.
- [ ] Introspection response phải có active boolean true.
- [ ] Scope được ánh xạ và kiểm tra theo endpoint.
- [ ] Audience/resource được kiểm tra theo contract của API.
- [ ] Tenant/ownership được kiểm tra ở domain layer.
- [ ] Custom introspector bọc delegate và giữ active validation.
- [ ] AS issuance/revocation/introspection dùng authorization state nhất quán.
- [ ] Cache TTL tuân theo expiry và revocation SLO.
- [ ] Timeout, connection pool, retry, circuit breaker và bulkhead có giới hạn.
- [ ] AS outage không tự động biến token thành active.
- [ ] Không log token, secret, Basic header hoặc raw introspection response nhạy cảm.
- [ ] Có test active/inactive, audience, scope, requester auth, TLS, outage và cache.
- [ ] Có metrics/audit và runbook ứng cứu.

### Kiến thức cốt lõi

**Opaque token Resource Server dùng introspection để hỏi Authorization Server về trạng thái và metadata của access token.** Spring Boot có thể tự cấu hình bằng ba property introspection-uri, client-id và client-secret; Spring Security tích hợp qua opaqueToken() trong SecurityFilterChain.

Spring gọi OpaqueTokenIntrospector, kiểm tra active, tạo OAuth2AuthenticatedPrincipal và ánh xạ scope thành authorities có prefix SCOPE_. Ứng dụng tiếp tục kiểm tra audience, scope, tenant và quyền nghiệp vụ. Credential dùng để gọi introspection là credential của chính Resource Server, độc lập với access token của caller.

Introspection tạo network dependency nên production cần timeout, quota, cache có giới hạn theo revocation SLO, failure policy, observability và kiểm thử AS outage. **Token active không đồng nghĩa request được phép**; authorization cuối cùng vẫn thuộc Resource Server.

## Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Boot — OAuth2 Resource Server Configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
