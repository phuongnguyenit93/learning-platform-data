# Tích hợp Resource Server qua introspection cho reference token

## 1. Bối cảnh: Resource Server cần biết token còn hiệu lực hay không

Một OAuth 2.0 Resource Server nhận access token từ client qua HTTP Bearer Authentication. Trước khi trả dữ liệu hoặc thực hiện thao tác, nó phải xác định token có được Authorization Server phát hành, còn hiệu lực và có quyền truy cập resource hiện tại hay không.

Có hai cách phổ biến để xác minh access token:

- **Local validation:** Resource Server tự xác minh chữ ký và claims của một self-contained token, thường là JWT.
- **Token introspection:** Resource Server gửi token tới Introspection Endpoint của Authorization Server để nhận trạng thái hiện tại và metadata của token.

Bài này tập trung vào reference token (opaque token) và RFC 7662 Token Introspection. Reference token là một chuỗi định danh ngẫu nhiên; nội dung và quyền của token được lưu tại Authorization Server. Resource Server không cần biết cấu trúc token, mà hỏi Authorization Server mỗi khi cần xác thực.

Trong hệ sinh thái Spring:

- **Spring Authorization Server (SAS)** phát reference access token, lưu authorization, cung cấp Token Introspection Endpoint và trả metadata của token.
- **Spring Security Resource Server** trích Bearer token từ request, gọi OpaqueTokenIntrospector và tạo Authentication sau khi nhận kết quả hợp lệ.
- **Ứng dụng API** dùng scope, audience, tenant và policy nghiệp vụ để quyết định request có được phép thực hiện hay không.

Introspection hữu ích khi cần thu hồi token có hiệu lực nhanh trên nhiều Resource Server. Đổi lại, request API phụ thuộc vào khả năng kết nối với Authorization Server và cần thiết kế tải, timeout, cache và fail-closed cẩn thận.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt reference token và self-contained JWT access token.
2. Giải thích giao thức RFC 7662 và trường active.
3. Cấu hình SAS phát access token dạng REFERENCE.
4. Cấu hình và bảo vệ Token Introspection Endpoint.
5. Đăng ký Resource Server như một client được phép introspect.
6. Cấu hình Spring Security Resource Server bằng Boot properties.
7. Hiểu OpaqueTokenIntrospector và BearerTokenAuthentication.
8. Ánh xạ scope thành authority và bảo vệ endpoint.
9. Kiểm tra audience, issuer và quyền theo resource.
10. Đồng bộ introspection với token revocation.
11. Thiết kế cache, timeout, resilience và fail-closed.
12. Kiểm thử end-to-end, vận hành và xử lý lỗi production.

## 2. Reference token và self-contained token

OAuth 2.0 không bắt buộc access token phải có một định dạng cụ thể. Một token có thể là reference string hoặc một cấu trúc tự chứa được bảo vệ.

| Tiêu chí | Reference / opaque token | Self-contained token (thường là JWT) |
|---|---|---|
| Nội dung token | Chuỗi tham chiếu khó đoán | Claims được ký hoặc bảo vệ |
| Nơi lưu metadata | Authorization Server | Có thể nằm ngay trong token |
| Xác minh | Hỏi Introspection Endpoint | Resource Server xác minh chữ ký và claims |
| Thu hồi | Có thể có hiệu lực ở lần introspection kế tiếp | Thường cần denylist, token version hoặc introspection |
| Độ trễ request | Có network call tới Authorization Server | Có thể xác minh local |
| Phụ thuộc runtime | Phụ thuộc endpoint introspection | Phụ thuộc key distribution/rotation |
| Lộ metadata | Client không đọc được claims từ token | Payload JWT có thể đọc được, dù chữ ký bảo vệ tính toàn vẹn |
| Cache | Cache làm chậm nhận biết revoke | Cache key/JWKS và policy local |

Reference token không phải một loại OAuth grant. Nó là định dạng access token. Client vẫn dùng Authorization Code, Client Credentials hoặc grant type khác để nhận token.

### 2.1. Token opaque không có nghĩa là không có metadata

Authorization Server vẫn lưu subject, client, scopes, thời điểm phát hành, thời điểm hết hạn, trạng thái revoke và metadata khác. Reference token chỉ che cấu trúc đó khỏi client và Resource Server.

Khi Resource Server gọi introspection, Authorization Server có thể trả các thuộc tính cần thiết để xác thực và phân quyền.

### 2.2. Khi nào nên dùng introspection?

Introspection phù hợp khi access token cần bị vô hiệu hóa tập trung, nhiều API cần cùng một nguồn sự thật về trạng thái token, token chứa thông tin nhạy cảm không muốn để client đọc, hoặc policy về trạng thái người dùng cần được kiểm tra online. Hệ thống phải chấp nhận chi phí network và vận hành Authorization Server với độ sẵn sàng phù hợp.

Local JWT validation phù hợp hơn khi độ trễ thấp, khả năng hoạt động độc lập và tải lớn là ưu tiên, còn thời gian revoke có thể được kiểm soát bằng token TTL ngắn hoặc cơ chế bổ sung.

## 3. Kiến trúc tích hợp

~~~mermaid
flowchart LR
    C[OAuth2 Client] -->|Bearer reference token| RS[Spring Resource Server]
    RS -->|POST /oauth2/introspect| AS[Spring Authorization Server]
    AS --> STORE[(OAuth2AuthorizationService)]
    AS --> CLIENTS[(RegisteredClientRepository)]
    AS -->|active + scope + claims| RS
    RS -->|Authentication + authorities| API[API authorization]
~~~

Có hai loại client identity cần phân biệt:

- OAuth client đã xin access token. Trường **client_id** trong introspection response thường xác định client này.
- Introspection caller là Resource Server đang xác thực với Introspection Endpoint. Nó dùng credential riêng để chứng minh quyền truy vấn trạng thái token.

Hai vai trò có thể nằm trong cùng một ứng dụng, nhưng nên có client registration và credential riêng để tách quyền, audit và vòng đời secret.

### 3.1. Luồng xử lý một API request

~~~mermaid
sequenceDiagram
    participant C as OAuth2 Client
    participant RS as Resource Server
    participant AS as Authorization Server
    participant DB as Authorization Store

    C->>RS: GET /orders + Authorization: Bearer token
    RS->>RS: BearerTokenAuthenticationFilter trích token
    RS->>AS: POST /oauth2/introspect + client authentication
    AS->>DB: Tìm authorization và token metadata
    DB-->>AS: Token state, scopes, subject, expiry
    AS-->>RS: active=true + metadata
    RS->>RS: Kiểm tra audience và tạo authorities
    RS->>RS: AuthorizationManager kiểm tra scope
    RS-->>C: 200 OK hoặc 403 Forbidden
~~~

Nếu token không tồn tại, đã hết hạn, chưa tới thời điểm có hiệu lực, bị revoke hoặc không được phép sử dụng tại Resource Server đó, Authorization Server trả **active: false**. Spring Security từ chối xác thực Bearer token.

## 4. RFC 7662 định nghĩa gì?

RFC 7662 định nghĩa giao thức để Protected Resource hỏi Authorization Server về trạng thái hiện tại và metadata của OAuth token.

Introspection request sử dụng HTTP POST với body **application/x-www-form-urlencoded**. Tham số bắt buộc là **token**; **token_type_hint** là tùy chọn.

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_RESOURCE_SERVER_CLIENT
Accept: application/json
Content-Type: application/x-www-form-urlencoded

token=OPAQUE_ACCESS_TOKEN&token_type_hint=access_token
~~~

Endpoint phải được bảo vệ bằng TLS và phải yêu cầu xác thực cho Resource Server. Nếu endpoint không được bảo vệ, attacker có thể thử nhiều giá trị token để dò tìm token hợp lệ.

### 4.1. Trường active

**active** là trường bắt buộc trong introspection response:

- **true:** Authorization Server xác nhận token hiện đang active theo policy của nó.
- **false:** token không active, không tồn tại, không hợp lệ hoặc Resource Server không được phép biết trạng thái của token.

Response inactive nên chỉ chứa **active: false**, tránh tiết lộ token có tồn tại hay vì sao nó không hợp lệ.

### 4.2. Các trường metadata thường gặp

| Trường | Ý nghĩa |
|---|---|
| active | Trạng thái token |
| scope | Danh sách scope cách nhau bằng dấu cách |
| client_id | Client đã yêu cầu token |
| username | Định danh hiển thị của resource owner, nếu có |
| token_type | Loại token, ví dụ Bearer |
| exp | Thời điểm hết hạn, Unix timestamp |
| iat | Thời điểm phát hành |
| nbf | Thời điểm token bắt đầu có hiệu lực |
| sub | Subject của token |
| aud | Resource hoặc audience dự định sử dụng token |
| iss | Issuer của token |
| jti | Định danh token |

Các trường ngoài **active** phần lớn là tùy chọn theo RFC 7662. Resource Server cần thống nhất contract với Authorization Server và không giả định mọi claim luôn xuất hiện.

### 4.3. Ví dụ response active

~~~json
{
  "active": true,
  "client_id": "orders-worker",
  "scope": "orders.read",
  "sub": "service-account-42",
  "aud": ["https://api.example.com/orders"],
  "iss": "https://auth.example.com",
  "token_type": "Bearer",
  "iat": 1784282400,
  "exp": 1784282700
}
~~~

Đây là response minh họa. Giá trị thực tế phụ thuộc Authorization Server và token customizer. Không tự giả định SAS luôn trả tất cả các trường tùy chọn.

## 5. Spring Authorization Server phát reference token

Trong Spring Authorization Server 1.5.8, **TokenSettings** mặc định dùng **OAuth2TokenFormat.SELF_CONTAINED**, thường tạo JWT khi có JwtGenerator. Muốn phát reference token, cần cấu hình **OAuth2TokenFormat.REFERENCE** cho RegisteredClient tương ứng.

~~~java
RegisteredClient ordersWorker = RegisteredClient
    .withId(UUID.randomUUID().toString())
    .clientId("orders-worker")
    .clientSecret(passwordEncoder.encode(secretFromSecretManager))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("orders.read")
    .scope("orders.write")
    .tokenSettings(TokenSettings.builder()
        .accessTokenFormat(OAuth2TokenFormat.REFERENCE)
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
~~~

Đây là ví dụ machine-to-machine. Nếu client dùng Authorization Code, cấu hình grant và redirect URI tương ứng; phần quan trọng cho bài này là **accessTokenFormat(REFERENCE)**.

### 5.1. REFERENCE là cấu hình theo RegisteredClient

Mỗi RegisteredClient có thể dùng TokenSettings riêng. Một Authorization Server có thể phát JWT cho một client và reference token cho client khác.

Điều này giúp di chuyển theo từng API hoặc từng nhóm client. Resource Server nhận token phải được cấu hình theo định dạng và phương thức xác minh tương ứng.

### 5.2. Access token reference được tạo và lưu như thế nào?

**OAuth2AccessTokenGenerator** tạo reference access token. Token là chuỗi tham chiếu tới metadata lưu trong **OAuth2Authorization**. **OAuth2AuthorizationService** là nguồn lưu trữ authorization và được dùng bởi token issuance, introspection và revocation.

Trong production:

- Dùng JdbcRegisteredClientRepository hoặc implementation lưu trữ bền vững tương đương.
- Dùng JdbcOAuth2AuthorizationService hoặc kho dùng chung có tính nhất quán phù hợp.
- Không dùng InMemoryRegisteredClientRepository hay InMemoryOAuth2AuthorizationService cho cụm production nhiều node.
- Đảm bảo mọi node Authorization Server cùng đọc/ghi một nguồn trạng thái có khả năng phục hồi.

## 6. Cấu hình Token Introspection Endpoint trong SAS

Spring Authorization Server cung cấp Token Introspection Endpoint. Endpoint mặc định là **/oauth2/introspect**, có thể thay đổi qua **AuthorizationServerSettings**.

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .tokenIntrospectionEndpoint("/oauth2/introspect")
        .build();
}
~~~

**AuthorizationServerSettings** là thành phần cấu hình bắt buộc của Authorization Server. Nếu không thay endpoint, SAS dùng path mặc định.

### 6.1. Endpoint có sẵn trong cấu hình Authorization Server

Khi dùng **OAuth2AuthorizationServerConfigurer**, SAS đăng ký **OAuth2TokenIntrospectionEndpointFilter** cùng các thành phần mặc định:

- **OAuth2TokenIntrospectionAuthenticationConverter** đọc request.
- **OAuth2TokenIntrospectionAuthenticationProvider** xử lý introspection.
- Success handler trả **OAuth2TokenIntrospection**.
- Error handler trả OAuth2 error response.

Provider mặc định dùng **RegisteredClientRepository** để xác thực client và **OAuth2AuthorizationService** để tra cứu authorization.

### 6.2. SecurityFilterChain tối thiểu

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, Customizer.withDefaults());

    return http.build();
}
~~~

Ví dụ này sử dụng các endpoint mặc định của SAS. Nếu ứng dụng đã có Authorization Server filter chain, hãy giữ một cấu hình thống nhất và kiểm tra endpoint introspection không bị một filter chain khác chặn hoặc vô tình public.

## 7. Xác thực Resource Server khi gọi introspection

RFC 7662 yêu cầu Protected Resource xác thực khi gọi Introspection Endpoint. SAS mặc định yêu cầu client authentication tại Token Introspection Endpoint.

Các phương thức client authentication SAS hỗ trợ gồm:

- client_secret_basic
- client_secret_post
- private_key_jwt
- client_secret_jwt
- tls_client_auth
- self_signed_tls_client_auth
- none cho public client

Đối với Resource Server gọi introspection, nên dùng một confidential client với phương thức xác thực có thể chứng minh danh tính dịch vụ. Không dùng **none** cho một API production cần được phép truy vấn trạng thái token.

### 7.1. Tách credential introspection khỏi credential của ứng dụng gọi API

Ví dụ, **orders-worker** là OAuth client xin token để gọi API; **orders-api-introspection** là danh tính dịch vụ mà API dùng để gọi **/oauth2/introspect**.

Tách hai credential giúp xoay vòng secret của Resource Server mà không tác động client bên ngoài, thu hồi quyền introspection của một API độc lập, audit chính xác dịch vụ nào đã truy vấn trạng thái token và tránh dùng credential của client frontend để gọi endpoint nội bộ.

Đăng ký introspection caller trong **RegisteredClientRepository** bằng client authentication method phù hợp. Lưu secret đã encode theo **PasswordEncoder** của SAS và phân phối secret thô cho Resource Server qua secret manager.

### 7.2. Giới hạn quyền introspection

RFC 7662 khuyến nghị Authorization Server chỉ cho phép Protected Resource được phép gọi endpoint này. Nếu nhiều API dùng chung Authorization Server, nên xác định API nào được introspect token của resource nào.

Không xem việc client authentication thành công là lý do để trả toàn bộ metadata của mọi token. Có thể tùy biến **OAuth2TokenIntrospectionAuthenticationProvider** hoặc response handling để áp dụng policy theo client, resource và dữ liệu được phép tiết lộ.

## 8. Giới hạn audience của reference token

**active: true** không tự động có nghĩa token phù hợp với mọi API. Một token có thể còn hiệu lực nhưng được phát cho một Resource Server khác.

Với API có yêu cầu phân tách resource, hãy dùng audience rõ ràng. RFC 7662 định nghĩa **aud** là một hoặc nhiều resource dự định nhận token. Authorization Server cần kiểm tra token được sử dụng tại Resource Server đang introspect.

### 8.1. Thêm audience cho opaque access token

SAS hỗ trợ **OAuth2TokenCustomizer<OAuth2TokenClaimsContext>** để thêm claims cho opaque access token. Ví dụ, ánh xạ một client tới Orders API:

~~~java
@Bean
OAuth2TokenCustomizer<OAuth2TokenClaimsContext> accessTokenCustomizer() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())
                && "orders-worker".equals(
                    context.getRegisteredClient().getClientId())) {

            context.getClaims().claim(
                "aud",
                List.of("https://api.example.com/orders"));
        }
    };
}
~~~

Đây là policy minh họa. Trong hệ thống có nhiều resource, audience phải được tính từ policy server-side hoặc resource indicator đã được xác minh. Không lấy một giá trị **aud** tùy ý từ client request rồi đưa thẳng vào token.

Claims của opaque token được lưu cùng authorization và có thể được dùng trong introspection response. Hãy kiểm thử response thực tế của SAS để bảo đảm **aud** được trả về đúng kiểu và đúng giá trị mà Resource Server mong đợi. Nếu ứng dụng tự khai báo **OAuth2TokenGenerator** thay vì dùng generator mặc định, phải gắn access-token customizer vào **OAuth2AccessTokenGenerator** trong **DelegatingOAuth2TokenGenerator**; chỉ khai báo bean customizer không tự cấu hình một generator tùy chỉnh.

### 8.2. Authorization Server phải kiểm tra resource đích

Khi có audience, Authorization Server phải xác định Resource Server đang introspect và chỉ trả **active: true** nếu token được phép dùng tại resource đó. RFC 7662 yêu cầu Authorization Server thực hiện các kiểm tra resource-specific có áp dụng. Việc thêm claim **aud** vào token chỉ cung cấp dữ liệu để kiểm tra; nó không tự thực thi policy introspection.

Provider mặc định của SAS xử lý trạng thái authorization và token. Nếu cần giới hạn một introspection caller chỉ được hỏi về một số audience hoặc resource nhất định, hãy triển khai policy riêng bằng **AuthenticationProvider** và đăng ký qua **tokenIntrospectionEndpoint(...).authenticationProviders(...)**. Không chỉ dựa vào client authentication hoặc claim **aud** do Resource Server tự kiểm tra.

Nếu token không có audience mà hệ thống cần phân tách API, hãy bổ sung contract audience trước khi đưa token vào production. Đừng coi scope là thay thế hoàn toàn cho audience: scope mô tả quyền, audience xác định nơi quyền đó có hiệu lực.

## 9. Cấu hình Spring Boot Resource Server

Với Spring Boot, cấu hình tối thiểu gồm Introspection URI và credential của Resource Server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: SECRET_FROM_SECRET_MANAGER
~~~

Dependency tối thiểu cho opaque Bearer token là **spring-boot-starter-oauth2-resource-server** trong Spring Boot hoặc **spring-security-oauth2-resource-server** khi tự quản lý dependency.

Spring Boot tự cấu hình **OpaqueTokenIntrospector** và Resource Server filter chain từ các thuộc tính này. Secret trong ví dụ là placeholder; production phải lấy từ secret manager, environment secret injection hoặc cơ chế quản lý credential phù hợp.

### 9.1. Không nhầm introspection-uri với token-uri

- **introspection-uri** là endpoint để Resource Server hỏi trạng thái token.
- **token-uri** là endpoint để OAuth client đổi grant lấy token.

Resource Server trong bài này không xin access token cho mỗi request API. Nó nhận token từ client và gửi token đó tới introspection endpoint.

### 9.2. Tự cấu hình SecurityFilterChain

Nếu ứng dụng đã có **SecurityFilterChain** riêng, phải bật opaque token support:

~~~java
@Bean
SecurityFilterChain resourceServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/actuator/health").permitAll()
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.opaqueToken(Customizer.withDefaults()));

    return http.build();
}
~~~

Khi đã khai báo SecurityFilterChain riêng, không nên giả định Boot vẫn áp dụng cấu hình mặc định cho mọi endpoint. Hãy kiểm tra matcher, thứ tự filter chain và authorization rules.

## 10. Luồng xử lý trong Spring Security

Spring Security dùng các thành phần chính sau:

1. **BearerTokenAuthenticationFilter** trích access token từ Authorization header.
2. Filter tạo **BearerTokenAuthenticationToken**.
3. **AuthenticationManager** chuyển request tới **OpaqueTokenAuthenticationProvider**.
4. Provider gọi **OpaqueTokenIntrospector**.
5. Introspector gửi token tới endpoint và đọc response.
6. Nếu token active, provider tạo **BearerTokenAuthentication**.
7. Authentication được đặt trong **SecurityContextHolder**.

Mặc định, principal là **OAuth2AuthenticatedPrincipal**. Authorities bao gồm scope đã được chuyển thành authority với prefix **SCOPE_** và bearer factor authority.

### 10.1. Token được gửi trong header

~~~http
GET /orders/123 HTTP/1.1
Host: api.example.com
Authorization: Bearer OPAQUE_ACCESS_TOKEN
Accept: application/json
~~~

Không gửi access token qua query string, URL path hoặc tham số form. Token trong URL dễ bị lưu vào browser history, proxy log, analytics và Referer header.

### 10.2. Lấy principal sau khi xác thực

Controller có thể nhận **BearerTokenAuthentication** hoặc **OAuth2AuthenticatedPrincipal**:

~~~java
@GetMapping("/whoami")
Map<String, Object> whoami(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

    return Map.of(
        "subject", principal.getName(),
        "clientId", principal.getAttribute("client_id"),
        "scopes", principal.getAttribute("scope"));
}
~~~

**Authentication#getName** mặc định ánh xạ tới claim **sub** nếu introspection response có trường này. Với Client Credentials, subject có thể đại diện cho workload hoặc client thay vì End-User. Không giả định mọi token đều đại diện cho người dùng.

## 11. Ánh xạ scope thành quyền

Nếu introspection response có:

~~~json
{
  "active": true,
  "scope": "orders.read orders.write"
}
~~~

Spring Security tạo authorities:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Do đó, API nên kiểm tra scope cụ thể:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.opaqueToken(Customizer.withDefaults()));

    return http.build();
}
~~~

### 11.1. Method security

Có thể bảo vệ business method bằng **@PreAuthorize**:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}

@Service
class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Order findOrder(String orderId) {
        // Load order and apply ownership/tenant checks.
        return ...;
    }
}
~~~

Scope không thay thế authorization nghiệp vụ. API vẫn phải kiểm tra tenant, quyền sở hữu resource, trạng thái đơn hàng và các policy domain khác.

### 11.2. Scope không được tự suy ra từ client identity

Không cấp quyền chỉ vì **client_id** đúng tên hoặc token active. Scope trong introspection response phải phản ánh quyền thực tế được Authorization Server cấp và Resource Server phải kiểm tra scope theo từng endpoint.

Nếu API dùng role hoặc permission riêng, hãy ánh xạ claims đã được tin cậy thành GrantedAuthority bằng custom introspector. Không tin một claim tùy ý mà Authorization Server không kiểm soát.

## 12. Kiểm tra audience bằng custom OpaqueTokenIntrospector

Spring Security mặc định xác minh **active** và ánh xạ scope. Nếu API cần ràng buộc audience, hãy thêm một lớp kiểm tra sau khi delegate đã introspect thành công.

~~~java
public final class AudienceCheckingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String expectedAudience;

    public AudienceCheckingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedAudience) {
        this.delegate = delegate;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            this.delegate.introspect(token);

        Object audience = principal.getAttribute("aud");
        boolean accepted = false;

        if (audience instanceof String value) {
            accepted = this.expectedAudience.equals(value);
        } else if (audience instanceof Collection<?> values) {
            accepted = values.contains(this.expectedAudience);
        }

        if (!accepted) {
            throw new BadOpaqueTokenException(
                "The token is not intended for this resource server");
        }

        return principal;
    }
}
~~~

Nếu introspection response không có **aud**, wrapper từ chối token. Đây là lựa chọn fail-closed phù hợp khi API bắt buộc audience. Trước khi bật kiểm tra, cần cấu hình Authorization Server phát claim audience và xác nhận endpoint trả claim đó.

### 12.1. Đăng ký custom introspector

Với cấu hình timeout hoặc audience riêng, có thể tạo delegate từ URI và credential do ứng dụng inject:

~~~java
@ConfigurationProperties(
    "spring.security.oauth2.resourceserver.opaquetoken")
public record IntrospectionProperties(
    String introspectionUri,
    String clientId,
    String clientSecret
) {
}
~~~

Đăng ký record này bằng **@EnableConfigurationProperties(IntrospectionProperties.class)** hoặc **@ConfigurationPropertiesScan**. Prefix và tên field khớp với các thuộc tính Boot ở phần 9, vì vậy không phải duy trì hai bộ credential khác nhau.

~~~java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        IntrospectionProperties properties) {

    OpaqueTokenIntrospector delegate =
        SpringOpaqueTokenIntrospector
            .withIntrospectionUri(properties.introspectionUri())
            .clientId(properties.clientId())
            .clientSecret(properties.clientSecret())
            .build();

    return new AudienceCheckingOpaqueTokenIntrospector(
        delegate,
        "https://api.example.com/orders");
}
~~~

Khi cung cấp **OpaqueTokenIntrospector** bean, ứng dụng thay thế introspector auto-configuration của Boot. Bean mới phải giữ lại delegate để xác minh token qua Authorization Server; không tự tạo principal chỉ từ chuỗi token.

### 12.2. Kiểm tra issuer khi hệ thống cần ràng buộc rõ

Nếu Resource Server dùng nhiều Authorization Server hoặc có trust boundary riêng, có thể kiểm tra thêm **iss** sau introspection. Endpoint introspection phải được cố định trong cấu hình tin cậy; không chọn endpoint dựa trên dữ liệu chưa xác minh từ token.

## 13. Ánh xạ claim tùy chỉnh

Một số API cần ánh xạ claim **roles**, **permissions**, **tenant_id** hoặc **organization**. Có thể bọc delegate và tạo principal mới với authorities được kiểm soát.

~~~java
public final class PermissionOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public PermissionOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            this.delegate.introspect(token);

        Collection<GrantedAuthority> authorities =
            new ArrayList<>(principal.getAuthorities());

        Collection<String> permissions =
            principal.getAttribute("permissions");

        if (permissions != null) {
            permissions.stream()
                .map(permission ->
                    new SimpleGrantedAuthority("PERM_" + permission))
                .forEach(authorities::add);
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            principal.getAttributes(),
            authorities);
    }
}
~~~

Ví dụ chỉ minh họa cách ánh xạ. Trong production, phải validate kiểu dữ liệu của claim, giới hạn giá trị hợp lệ và tránh cấp role quản trị từ dữ liệu do client có thể tự kiểm soát.

Không bỏ các authorities do delegate tạo ra nếu vẫn cần **SCOPE_** authorities và bearer factor. Nếu thay toàn bộ authorities, phải chủ động tái tạo những authority mà policy của ứng dụng yêu cầu.

## 14. Phân biệt scope, audience và tenant

Ba khái niệm trả lời các câu hỏi khác nhau:

| Thuộc tính | Câu hỏi | Ví dụ |
|---|---|---|
| Scope | Token được phép làm hành động nào? | orders.read |
| Audience | Token được phép gửi tới API nào? | https://api.example.com/orders |
| Tenant | Request đang thao tác trong phạm vi tổ chức nào? | tenant-42 |

Một token có thể có scope **orders.read** nhưng audience dành cho Billing API. Orders API phải từ chối token đó.

Một token có thể có đúng audience và scope nhưng thuộc tenant khác. Resource Server vẫn phải xác minh tenant từ claim tin cậy và so sánh với tenant trong resource/request theo policy.

Không đưa tenant ID do client gửi trực tiếp vào principal hoặc coi nó là bằng chứng quyền truy cập. Token claim phải do Authorization Server xác định hoặc xác minh từ nguồn tin cậy.

## 15. Revocation và vòng đời token

Một lợi ích lớn của introspection là Resource Server có thể nhận biết token đã bị thu hồi mà không phải chờ JWT hết hạn, miễn là request được introspect lại và không dùng cache quá dài.

Spring Authorization Server có Token Revocation Endpoint. Khi token bị revoke, **OAuth2Authorization** và token metadata được cập nhật trong **OAuth2AuthorizationService**. Introspection tiếp theo có thể trả **active: false**.

### 15.1. Luồng revoke

~~~mermaid
sequenceDiagram
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant DB as Authorization Store
    participant RS as Resource Server

    C->>AS: POST /oauth2/revoke + token
    AS->>AS: Authenticate client
    AS->>DB: Mark token invalidated
    AS-->>C: 200 OK
    RS->>AS: POST /oauth2/introspect + same token
    AS->>DB: Read token state
    DB-->>AS: Token inactive
    AS-->>RS: {"active": false}
    RS-->>C: Reject next API request
~~~

### 15.2. Revoke không có nghĩa mọi request đang chạy bị dừng ngay lập tức

Introspection kiểm tra trạng thái khi Resource Server xác thực request. Request đã được xác thực trước thời điểm revoke có thể tiếp tục chạy. Nếu API thực hiện thao tác nhạy cảm kéo dài, có thể cần kiểm tra quyền ở ranh giới transaction hoặc domain operation.

Nếu Resource Server cache positive introspection result, token bị revoke có thể vẫn được chấp nhận cho tới khi cache hết hạn. Đây là trade-off phải được quy định rõ trong SLA bảo mật.

### 15.3. Dữ liệu phải được chia sẻ giữa các node

Nếu Authorization Server chạy nhiều node, tất cả node cần nhìn thấy cùng trạng thái authorization. Một node revoke token nhưng node introspection khác đọc kho in-memory riêng sẽ có thể trả trạng thái sai.

Dùng shared persistent authorization store và kiểm tra tính nhất quán của đường đọc sau ghi. Nếu dùng replica đọc trễ, thời gian lan truyền revoke phải được tính vào security SLA.

## 16. Cache introspection response

RFC 7662 cho phép Resource Server cache response để giảm tải và giảm network latency. Cache làm giảm độ mới của thông tin token.

| Chiến lược | Ưu điểm | Rủi ro |
|---|---|---|
| Không cache | Nhận biết revoke ở lần request tiếp theo | Mỗi request tạo network call |
| Cache ngắn | Giảm tải, cửa sổ stale nhỏ | Revoke có độ trễ bằng TTL |
| Cache dài | Tối ưu throughput | Token đã revoke vẫn có thể được chấp nhận lâu hơn |

### 16.1. Quy tắc cache an toàn

- Không cache response lâu hơn **exp**.
- Nếu không có **exp**, dùng TTL rất ngắn và có giới hạn rõ.
- Positive cache TTL phải nhỏ hơn thời gian chấp nhận revoke của hệ thống.
- Không biến lỗi mạng hoặc timeout thành response **active: true**.
- Không cache lỗi xác thực client như thể token inactive.
- Cache key nên là hash/HMAC của token, tránh giữ raw bearer token trong key hoặc log.
- Nếu Authorization Server trả kết quả khác nhau theo Resource Server, cache phải phân biệt resource/client context.
- Có cơ chế invalidate khi nhận event revoke nếu kiến trúc hỗ trợ.

### 16.2. Cache inactive token

Có thể cache kết quả inactive trong khoảng ngắn để giảm token scanning và lặp lại request sai. TTL phải ngắn, không làm che khuất token vừa được cấp hoặc thay đổi trạng thái sau một workflow hợp lệ.

### 16.3. Không giả định Spring Security tự cache

Opaque token support của Spring Security gọi introspector theo authentication flow. Nếu muốn cache, hãy chủ động bọc **OpaqueTokenIntrospector** bằng cache có TTL và policy phù hợp; không dựa vào cache HTTP hoặc proxy một cách ngầm định.

## 17. Timeout, retry và khả năng sẵn sàng

Introspection nằm trên đường xử lý request API. Một Authorization Server chậm hoặc mất kết nối có thể làm API tăng latency hoặc không thể xác thực token.

Spring Security 6.5 mặc định dùng connection timeout và socket timeout 30 giây cho kết nối introspection. Với API latency-sensitive, giá trị này thường cần điều chỉnh theo ngân sách request của hệ thống.

### 17.1. Đặt timeout có chủ đích

Có thể cấu hình **RestTemplateBuilder** để đặt timeout:

~~~java
@Bean
OpaqueTokenIntrospector introspector(
        IntrospectionProperties properties,
        RestTemplateBuilder builder) {

    RestOperations restOperations = builder
        .basicAuthentication(
            properties.clientId(), properties.clientSecret())
        .setConnectTimeout(Duration.ofSeconds(2))
        .setReadTimeout(Duration.ofSeconds(2))
        .build();

    return new SpringOpaqueTokenIntrospector(
        properties.introspectionUri(), restOperations);
}
~~~

Hai giây chỉ là ví dụ. Chọn timeout theo p95/p99 latency, network topology, retry policy và thời gian còn lại của request API. Không dùng timeout quá dài khiến thread pool bị giữ trong lúc Authorization Server gặp sự cố.

### 17.2. Retry có giới hạn

Retry chỉ nên áp dụng cho lỗi tạm thời và phải có deadline, backoff và jitter. Không retry vô hạn trên mọi request; điều đó có thể khuếch đại sự cố của Authorization Server.

Lỗi credential sai hoặc token inactive không phải lỗi transient để retry. Không retry một token không hợp lệ chỉ để tìm response active.

### 17.3. Circuit breaker và fail-closed

Khi introspection endpoint không thể truy cập:

- Không chấp nhận token dựa trên lần xác thực cũ nếu cache đã hết hạn.
- Không giả lập **active: true**.
- Không bỏ qua authentication filter.
- Trả lỗi dịch vụ phù hợp, đồng thời giữ request chưa xác thực.
- Giới hạn tải và phục hồi theo circuit breaker/backoff.

Đây là fail-closed: hệ thống có thể từ chối request hợp lệ khi Authorization Server mất kết nối, nhưng không cấp quyền dựa trên trạng thái không xác minh được.

## 18. Bảo mật Introspection Endpoint

Introspection endpoint nhận bearer token trong body và trả dữ liệu được dùng để quyết định quyền truy cập. Endpoint này cần được bảo vệ như một endpoint nhạy cảm.

### 18.1. Bảo vệ transport

- Chỉ expose qua HTTPS.
- Hỗ trợ TLS 1.2 trở lên và xác minh certificate server.
- Không tắt hostname verification.
- Dùng private network hoặc service mesh nếu phù hợp, nhưng vẫn giữ TLS và client authentication.
- Giới hạn truy cập endpoint ở network layer theo danh sách Resource Server.

### 18.2. Bảo vệ client credential

- Dùng một credential riêng cho từng Resource Server.
- Ưu tiên **private_key_jwt** hoặc mTLS khi yêu cầu assurance cao.
- Nếu dùng client secret, lưu trong secret manager và có lịch rotate.
- Không ghi Authorization header vào log.
- Thu hồi client registration khi API bị decommission hoặc credential bị lộ.

### 18.3. Bảo vệ dữ liệu token

- Chỉ chấp nhận POST theo RFC 7662.
- Không ghi body token vào access log, trace hoặc exception message.
- Không gửi token qua query parameter.
- Giới hạn request body và số lần gọi theo client.
- Không trả thêm metadata cho inactive token.
- Chỉ trả claim cần thiết cho từng Resource Server.

### 18.4. Rate limiting và chống token scanning

Introspection endpoint phải xác thực caller trước khi tra cứu token. Có thể giới hạn tốc độ theo client ID, IP mạng tin cậy và resource identity. Theo dõi tỷ lệ token inactive cao, request bất thường và lỗi client authentication.

Không dùng raw token làm metric label hoặc log field.

## 19. Introspection response và quyền riêng tư

Authorization Server có thể trả metadata khác nhau cho các Protected Resource khác nhau. Ví dụ, Orders API chỉ cần scope và subject liên quan đến Orders, không cần biết các quyền của token trên Billing API.

Hãy xác định contract response theo nguyên tắc tối thiểu:

- **active** để quyết định trạng thái.
- **scope** để kiểm tra quyền.
- **sub** nếu API cần subject.
- **aud** để ràng buộc resource.
- **exp** để giới hạn cache và vòng đời.
- **client_id** cho audit hoặc policy client.
- Claim tenant/organization chỉ khi Resource Server thực sự cần.

Không trả email, profile, nhóm tổ chức hoặc thông tin cá nhân chỉ vì token có thể chứa các thuộc tính đó. Introspection không phải endpoint UserInfo.

## 20. Kiểm thử end-to-end

Kiểm thử nên chạy qua Authorization Server, kho authorization và Resource Server thật trong môi trường integration test. Mock introspector chỉ phù hợp với test authorization rule đơn lẻ; nó không xác minh được protocol contract hoặc revoke propagation.

### 20.1. Test phát token

- RegisteredClient cần reference token có **accessTokenFormat(REFERENCE)**.
- Client nhận access token dạng opaque string.
- Authorization được lưu vào **OAuth2AuthorizationService**.
- Scope và audience được lưu theo policy.
- Token TTL đúng với cấu hình.
- Client khác vẫn nhận định dạng token theo TokenSettings riêng.

### 20.2. Test introspection

| Trường hợp | Kết quả mong đợi |
|---|---|
| Token active và đúng audience | active: true, Resource Server chấp nhận |
| Token không tồn tại | active: false |
| Token hết hạn | active: false |
| Token bị revoke | active: false |
| Token chưa tới nbf | active: false |
| Sai client credentials | Endpoint từ chối xác thực caller |
| Caller không được phép biết token | active: false theo policy |
| Response thiếu audience bắt buộc | Custom introspector từ chối |
| Scope không đủ | Token authenticated nhưng API trả 403 |
| Authorization Server timeout | Request không được xác thực |

### 20.3. Test revoke propagation

1. Xin access token.
2. Gọi API và xác nhận thành công.
3. Gọi Token Revocation Endpoint.
4. Gọi lại API.
5. Xác nhận introspection trả inactive và API từ chối.
6. Nếu có cache, đo thời gian tối đa trước khi token bị từ chối.

### 20.4. Test lỗi hạ tầng

- Authorization Server không truy cập được.
- TLS certificate hết hạn hoặc không tin cậy.
- Secret introspection bị rotate.
- Authorization store tạm thời lỗi.
- Một node SAS không thấy bản ghi do replication lag.
- Introspection response malformed.
- Cache backend mất kết nối.
- Circuit breaker mở rồi phục hồi.

## 21. Observability và vận hành

Theo dõi tổng số introspection request theo Resource Server client ID, tỷ lệ active/inactive, latency p50/p95/p99, lỗi client authentication, timeout, TLS, connection refused, malformed response, số lần API trả 401/403, thời gian lan truyền revoke và cache hit/miss.

### 21.1. Log an toàn

Log nên có correlation ID, Resource Server client ID, endpoint hoặc resource đang được truy cập, kết quả phân loại active/inactive/error, thời gian xử lý và loại lỗi.

Không log raw bearer token, client secret, Authorization header hoặc toàn bộ introspection response nếu có PII. Nếu cần liên kết sự kiện revoke với token, dùng token fingerprint được tạo bằng HMAC có khóa bảo vệ.

### 21.2. Runbook khi mọi API bắt đầu trả 401

1. Kiểm tra client credentials dùng cho introspection có bị rotate hoặc hết hạn không.
2. Kiểm tra Token Introspection Endpoint có hoạt động và đúng path không.
3. Kiểm tra TLS certificate và hostname.
4. Kiểm tra Authorization Server có truy cập được authorization store không.
5. Kiểm tra response active và scope có thay đổi sau deployment không.
6. Kiểm tra Resource Server có dùng đúng introspection URI/issuer không.
7. Kiểm tra cache có giữ kết quả inactive cũ hoặc response stale không.
8. Kiểm tra clock synchronization nếu policy phụ thuộc exp/nbf.
9. Kiểm tra audience và resource mapping nếu chỉ một API bị ảnh hưởng.

Không khắc phục bằng cách bỏ introspection hoặc chấp nhận token khi endpoint đang lỗi.

## 22. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Quên accessTokenFormat(REFERENCE) | SAS tiếp tục phát JWT mặc định | Cấu hình TokenSettings theo RegisteredClient |
| Dùng JWT decoder cho reference token | Không thể xác minh token local | Dùng opaque token introspection |
| Resource Server không có client credentials | Introspection endpoint từ chối request | Đăng ký confidential caller |
| Dùng credential của client frontend | Lộ quyền hoặc khó audit | Tách service identity |
| Chỉ kiểm tra active | Token có thể sai audience hoặc thiếu scope | Kiểm tra audience và authorization policy |
| Coi scope là audience | Token có thể được dùng sai API | Ràng buộc aud riêng |
| Không persist authorization trong production | Token mất trạng thái sau restart hoặc không đồng bộ node | Dùng shared persistent OAuth2AuthorizationService |
| Cache positive quá lâu | Token revoke vẫn được chấp nhận | TTL ngắn, giới hạn theo exp và revoke SLA |
| Nuốt timeout rồi coi token active | Bypass xác thực | Fail-closed |
| Ghi token vào log | Rò rỉ bearer credential | Redact body và Authorization header |
| Dùng GET cho introspection | Token có thể lọt vào URL/log | Chỉ dùng POST form body |
| Cho mọi client gọi introspection | Token scanning và lộ metadata | Authenticate, authorize và rate-limit caller |
| Không test revoke propagation | Không biết thời gian vô hiệu token thực tế | End-to-end revoke test |
| Dùng in-memory authorization store trong cluster | Trạng thái token khác nhau giữa node | Dùng shared persistence |

## 23. Lựa chọn introspection so với JWT local validation

| Câu hỏi kiến trúc | Introspection reference token | JWT local validation |
|---|---|---|
| Cần revoke nhanh? | Phù hợp, tùy cache | Cần cơ chế bổ sung hoặc TTL ngắn |
| Chấp nhận network call mỗi lần xác thực? | Có | Không |
| Muốn token không tiết lộ claims? | Phù hợp | Payload JWT có thể đọc được |
| Resource Server cần hoạt động khi AS down? | Không nếu cache hết hạn | Có thể |
| Quản lý trạng thái tập trung? | Có | Phải bổ sung |
| Tải introspection lớn? | Cần scale AS và cache cẩn thận | Ít phụ thuộc AS hơn |
| Phân tách nhiều API? | Dùng audience/policy trong introspection | Dùng aud claim và local validator |

Không có lựa chọn nào phù hợp cho mọi hệ thống. Một số kiến trúc dùng JWT nhưng vẫn introspect để kiểm tra revoke online. Spring Security opaque-token support không phụ thuộc token có cấu trúc hay không; nó gửi token tới endpoint và sử dụng kết quả introspection.

## 24. Checklist triển khai production

### Authorization Server

- [ ] RegisteredClient cần reference token dùng OAuth2TokenFormat.REFERENCE.
- [ ] Access token TTL được giới hạn theo risk.
- [ ] OAuth2AuthorizationService dùng persistent store dùng chung.
- [ ] RegisteredClientRepository dùng persistent store.
- [ ] Token Introspection Endpoint có path và issuer cố định.
- [ ] Endpoint yêu cầu client authentication.
- [ ] Resource Server caller được đăng ký và có credential riêng.
- [ ] Caller được phép introspect đúng phạm vi token.
- [ ] Response chỉ trả claim cần thiết.
- [ ] Audience được gắn theo resource policy.
- [ ] Revocation cập nhật cùng authorization store.
- [ ] Endpoint dùng TLS và có rate limit.

### Resource Server

- [ ] Có spring-security-oauth2-resource-server.
- [ ] introspection-uri trỏ tới endpoint tin cậy.
- [ ] Credential introspection được lấy từ secret manager.
- [ ] Dùng opaqueToken() trong SecurityFilterChain.
- [ ] Scope được map và kiểm tra bằng SCOPE_ authority.
- [ ] Audience được kiểm tra nếu API cần resource isolation.
- [ ] Tenant và ownership được kiểm tra ở domain layer.
- [ ] Timeout phù hợp ngân sách latency.
- [ ] Lỗi introspection dẫn tới fail-closed.
- [ ] Cache có TTL và revoke SLA rõ ràng.
- [ ] Log không chứa token hoặc secret.

### Kiểm thử và vận hành

- [ ] Test active, inactive, expired và revoked token.
- [ ] Test introspection caller credentials sai.
- [ ] Test audience mismatch và scope insufficient.
- [ ] Test Authorization Server unavailable.
- [ ] Test revocation propagation qua nhiều node.
- [ ] Test cache stale và cache expiration.
- [ ] Có dashboard latency và active/inactive ratio.
- [ ] Có alert cho authentication failure tăng bất thường.
- [ ] Có runbook cho lỗi credential, TLS, store và cache.
- [ ] Có quy trình rotate introspection client secret.

### Kiến thức cốt lõi

Reference token là chuỗi tham chiếu tới authorization metadata lưu tại Authorization Server. Với Spring Authorization Server, TokenSettings mặc định dùng self-contained token; cần cấu hình OAuth2TokenFormat.REFERENCE cho RegisteredClient muốn phát opaque token. SAS cung cấp /oauth2/introspect, xác thực caller và tra cứu token qua OAuth2AuthorizationService.

Spring Security Resource Server dùng OpaqueTokenIntrospector để gửi token tới endpoint. Khi response active là true, framework tạo BearerTokenAuthentication và ánh xạ scope thành authority SCOPE_. API vẫn phải kiểm tra audience, scope, tenant, ownership và policy nghiệp vụ. Introspection hỗ trợ nhận biết revoke ở lần kiểm tra tiếp theo; cache, timeout và sự cố mạng quyết định độ trễ và tính sẵn sàng của cơ chế này.

Thiết kế production cần tách credential của Resource Server khỏi OAuth client gọi API, dùng TLS, hạn chế quyền introspection, không log token, dùng persistent authorization store và fail-closed khi không thể xác minh trạng thái. Hãy kiểm thử từ token issuance đến introspection, API authorization và revocation để bảo đảm toàn bộ chuỗi hoạt động đúng.

## Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707.html)
- [Spring Security 6.5 — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security 6.5 — SpringOpaqueTokenIntrospector API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html)
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server 1.5.8 — OAuth2TokenFormat API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/OAuth2TokenFormat.html)
- [Spring Authorization Server 1.5.8 — OAuth2TokenIntrospectionAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenIntrospectionAuthenticationProvider.html)
