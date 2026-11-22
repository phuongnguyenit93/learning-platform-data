# Spring Security filter chain và cấu hình resource server

## 1. Resource server bảo vệ REST API ở đâu?

Trong OAuth 2.0, **resource server** nhận **access token** từ caller để bảo vệ API; **authorization server** phát hành token. **Authentication** xác định principal và độ tin cậy của token, còn **authorization** kiểm tra quyền thao tác trên resource. Resource server không nhất thiết cung cấp login page hay cấp token.

Ví dụ:

~~~http
GET /api/v1/orders/ord-501 HTTP/1.1
Authorization: Bearer eyJ...
Accept: application/json
~~~

Orders API phải xác minh **chữ ký, issuer, audience, thời hạn và scope**, rồi xác nhận principal có quyền với **ord-501 thuộc đúng tenant**. Access token dành cho Catalog API hoặc đơn hàng của tenant B không thể tự động dùng cho đơn của tenant A.

Bài thuộc chương **Xác thực**, module **INTEGRATION_API_REST**: thiết kế REST qua resource/URI, HTTP method/status, cache, idempotency, OpenAPI, phân quyền, lỗi và kiểm thử Java/Spring. Nội dung tập trung **Servlet Spring MVC + Spring Security 6.x / Spring Boot 3.x**, ví dụ Java 17+. Với WebFlux phải dùng **SecurityWebFilterChain**, không copy trực tiếp cấu hình Servlet.

Mục tiêu: hiểu **DelegatingFilterProxy → FilterChainProxy → SecurityFilterChain**; phân biệt chain matching với authorization rules; cấu hình Bearer JWT hoặc opaque introspection; xử lý 401/403, CSRF/CORS; bảo vệ dữ liệu đa tenant; kiểm thử MVC lẫn token verification thực tế.

## 2. Cấu trúc filter chain của Spring Security

Trong ứng dụng Servlet, request không đi thẳng vào @RestController. Một servlet filter tên **DelegatingFilterProxy** nối hạ tầng Servlet với Spring bean **springSecurityFilterChain**, thường là **FilterChainProxy**. FilterChainProxy tìm **SecurityFilterChain đầu tiên có RequestMatcher phù hợp**, chạy các security filters theo thứ tự rồi mới chuyển request tiếp xuống MVC.

~~~mermaid
flowchart TD
  A[HTTP request] --> B[Servlet container]
  B --> C[DelegatingFilterProxy]
  C --> D[FilterChainProxy]
  D --> E{SecurityFilterChain nào khớp?}
  E --> F[SecurityContext + authentication filters]
  F --> G[ExceptionTranslationFilter]
  G --> H[AuthorizationFilter]
  H --> I{Đủ quyền?}
  I -->|Có| J[DispatcherServlet / Controller]
  I -->|Không| K[401 hoặc 403]
  E -->|Không chain nào khớp| L[Không đi qua Spring Security chain]
~~~

Sơ đồ là mô hình tư duy, **không phải danh sách thứ tự filter tuyệt đối** cho mọi phiên bản/cấu hình. Một số filter quan trọng trong ứng dụng resource server:

| Thành phần | Trách nhiệm |
| --- | --- |
| **SecurityContextHolderFilter** | Làm việc với SecurityContext cho request theo chính sách lưu context được cấu hình. |
| **BearerTokenAuthenticationFilter** | Tìm Bearer token trong request, tạo Authentication request và gọi AuthenticationManager. |
| **AuthenticationProvider/JwtDecoder** | Xác thực token và tạo Authentication đã xác thực. |
| **AnonymousAuthenticationFilter** | Cung cấp anonymous Authentication khi chưa xác thực, theo chain config. |
| **ExceptionTranslationFilter** | Chuyển một số AuthenticationException/AccessDeniedException từ phần downstream thành hành vi HTTP phù hợp. |
| **AuthorizationFilter** | Áp AuthorizationManager/rules với request trước khi tới controller. |

**Không đoán filter order từ tên:** Spring Security quản lý thứ tự bằng cơ chế filter-chain; thêm filter custom bằng addFilterBefore/After cần xác định vị trí và mục đích. BearerTokenAuthenticationFilter có thể tự khởi tạo authentication entry point khi token lỗi, không phải mọi 401 đều đi qua @ControllerAdvice hay cùng một nhánh ExceptionTranslationFilter.

### Authentication và SecurityContext

Luồng Bearer JWT điển hình:

~~~text
Authorization: Bearer <access-token>
  -> BearerTokenAuthenticationFilter
  -> JwtAuthenticationProvider + JwtDecoder
  -> verify signature, exp/nbf, issuer, audience theo policy
  -> JwtAuthenticationToken (principal/authorities)
  -> SecurityContext của request
  -> AuthorizationFilter + @PreAuthorize (nếu có)
  -> Service kiểm tra quyền trên từng resource
~~~

**SecurityContext không tự động cấp quyền trên row dữ liệu.** Nếu user có authority đọc đơn nhưng resource thuộc tenant khác, service/repository vẫn phải từ chối hoặc trả 404 theo chính sách.

## 3. SecurityFilterChain: chain nào được chọn?

Có hai lớp matching rất dễ nhầm:

- **http.securityMatcher("/api/**")** xác định **request có đi vào SecurityFilterChain này hay không**.
- **authorizeHttpRequests().requestMatchers(...)** chọn **quy tắc authorization** bên trong chain đã được chọn.

Khi có nhiều SecurityFilterChain, **chain đầu tiên khớp** được dùng; filter chains **không tự cộng dồn**. Nếu chain API có matcher quá rộng và order cao, nó có thể nuốt request dành cho chain actuator/browser. Ngược lại, nếu bạn khai báo chỉ một chain match /api/** mà không có chain fallback, những URI ngoài phạm vi có thể **không được Spring Security bảo vệ**.

Ví dụ ứng dụng chỉ muốn API và từ chối các endpoint còn lại:

~~~java
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/v1/products/**")
                    .hasAuthority("SCOPE_catalog:read")
                .requestMatchers(
                    HttpMethod.GET, "/api/v1/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(
                    HttpMethod.POST, "/api/v1/orders")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                .sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll())
            .build();
    }
}
~~~

Cần imports Java/Spring Security phù hợp. Code này là mẫu **API thuần dùng Authorization: Bearer**, không phải cấu hình mẫu cho web app có login form/cookie. Nếu application có health endpoint, actuator hoặc documentation công khai, viết rules và chain phù hợp **một cách có chủ đích** thay vì mở permitAll tùy tiện.

**Thứ tự rules cũng quan trọng:** matcher cụ thể đặt trước **anyRequest**; một **permitAll** quá rộng trước rule cần quyền sẽ làm endpoint bị mở. Ví dụ trên cố ý từ chối mọi API path/method chưa được định nghĩa.

### Một chain duy nhất khi không cần phân vùng

Nếu tất cả request của ứng dụng đều là API, thường đơn giản hơn là **một chain không dùng securityMatcher** và khai báo toàn bộ requestMatchers/anyRequest. Khi đó không có vùng URL vô tình nằm ngoài mọi chain. Nhiều chain chỉ hữu ích khi thật sự cần chính sách khác nhau (API vs browser/actuator) và có test xác minh thứ tự.

## 4. 401, 403 và trách nhiệm của authentication/authorization

| Trường hợp | HTTP thường đúng | Ghi chú |
| --- | --- | --- |
| Không có Bearer token khi endpoint yêu cầu | **401 Unauthorized** | Server yêu cầu xác thực; thường có WWW-Authenticate: Bearer. |
| Bearer token hết hạn/chữ ký sai/malformed | **401** | Challenge có thể có error=invalid_token; không log token. |
| JWT hợp lệ nhưng thiếu authority cần thiết | **403 Forbidden** | Có thể kèm error=insufficient_scope theo cấu hình và chuẩn. |
| Đủ scope nhưng không sở hữu order | **403 hoặc 404** | Chọn chính sách tránh lộ resource tenant khác. |
| Sai Content-Type trong POST đã xác thực | **415** | Lỗi media type, không đồng nghĩa xác thực. |
| API không cho phép method này | **405** hoặc **403** tùy lớp kiểm tra | Phải test contract/thứ tự filter thay vì suy đoán. |

Ví dụ không có token:

~~~http
GET /api/v1/orders/ord-501 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Cache-Control: no-store
~~~

Token hợp lệ nhưng không đủ scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
Cache-Control: no-store
~~~

**WWW-Authenticate là một phần quan trọng của HTTP authentication semantics.** Nếu custom error body thành application/problem+json, phải giữ status và challenge đúng scheme. **@RestControllerAdvice không tự bắt được mọi lỗi xuất phát trước controller trong Spring Security filter chain**; dùng **AuthenticationEntryPoint/AccessDeniedHandler** khi thật sự cần tùy biến.

Không trả **200 với JSON {"status":401}**, không dùng 404 cho lỗi token thiếu chỉ để “giấu” hệ thống, và không tiết lộ nguyên nhân ký số, user IDs hoặc cấu hình internal issuer trong detail công khai.

## 5. JWT: issuer, audience, signature và thời hạn

Trong Spring Boot 3.x, REST resource server thường cần starter security và OAuth2 resource server:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Một cấu hình ban đầu:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.internal/realms/shop
~~~

Spring Security có thể dùng issuer metadata để tìm JWK set và xác minh JWT bằng chữ ký của **trusted issuer**. Decoder/validators cũng kiểm tra mốc thời gian và issuer theo cấu hình. Token chỉ mới **base64url-decode** chưa phải token đã xác thực; không bao giờ chỉ giải mã payload rồi tin sub/scope.

| JWT claim | Ý nghĩa và giới hạn |
| --- | --- |
| **iss** | Định danh authorization server phát hành token. |
| **aud** | Resource server mà token hướng tới; Orders API cần có audience **orders-api**. |
| **exp, nbf** | Hết hạn và thời điểm bắt đầu hiệu lực; tính đến clock skew hợp lý. |
| **sub** | Danh tính principal tại issuer; không tự đồng nghĩa user ID nội bộ/tenant. |
| **scope/scp** | Phạm vi quyền được cấp; cần mapping và authorization policy. |
| **azp/client_id** | Client được ủy quyền; **không thay thế** aud/scope. |

**Issuer đúng không có nghĩa audience đúng.** Access token cho Billing API vẫn có thể được cùng issuer ký. Orders API không được nhận token đó chỉ vì signature hợp lệ. Khi dùng built-in config, kiểm tra **audience validation có được bật và hỗ trợ trong phiên bản Boot của dự án hay chưa**; nếu không, khai báo validator rõ.

Ví dụ validator riêng cho Spring Security 6.x; các property chỉ lấy từ cấu hình server đáng tin:

~~~java
@Configuration
class JwtTrustConfig {
    @Bean
    JwtDecoder jwtDecoder(Environment env) {
        String issuer =
            env.getRequiredProperty("app.security.issuer");
        String jwks =
            env.getRequiredProperty("app.security.jwk-set-uri");

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwks)
            .build();

        OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience() != null &&
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Audience not accepted",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                standard, audience));
        return decoder;
    }
}
~~~

~~~yaml
app:
  security:
    issuer: https://id.example.internal/realms/shop
    jwk-set-uri: https://id.example.internal/realms/shop/protocol/openid-connect/certs
~~~

Ví dụ dùng **Environment**, **NimbusJwtDecoder**, validators và imports tương ứng, không cần placeholder trực tiếp trong annotation. **JWK Set URI không được nhận từ request do client gửi**. Khi tự đăng ký JwtDecoder bean, một số auto-configuration của Spring Boot sẽ không còn tự tạo decoder, vì vậy phải tự kiểm chứng toàn bộ trust policy tương đương.

Bên cạnh issuer/audience, kiểm tra:

- Chỉ chấp nhận thuật toán ký phù hợp với chính sách; **không tin alg=none hoặc tự chọn key theo input không đáng tin**.
- Đồng bộ đồng hồ node, TTL token và clock skew; giới hạn kích thước header/token.
- Thử nghiệm **JWK rotation**: kid mới, cache keys, thời điểm key cũ hết hiệu lực; không bypass auth khi IdP/JWK endpoint gián đoạn.
- JWT offline verification không tự biết token vừa bị thu hồi; cần thiết kế lifetime/revocation phù hợp.
- **OIDC ID token không được dùng thay OAuth2 access token**, dù cả hai có thể có định dạng JWT.

Một request chứa token đã hết hạn thường nhận:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
~~~

Nội dung error_description chính xác phụ thuộc entry point và cấu hình; đừng công bố chi tiết chữ ký/khoá/issuer nội bộ trong lỗi trả client.

## 6. Ánh xạ OAuth2 scopes thành GrantedAuthority

Trong cấu hình mặc định thông dụng, Spring Security chuyển claim scope:

~~~text
scope: "orders:read orders:write"

GrantedAuthority:
  SCOPE_orders:read
  SCOPE_orders:write
~~~

Vì vậy:

~~~java
.requestMatchers(HttpMethod.GET, "/api/v1/orders/**")
    .hasAuthority("SCOPE_orders:read")
~~~

khác với **hasRole("orders:read")** (kiểm tra ROLE_orders:read theo cấu hình mặc định). Đặt nhầm prefix khiến token hợp lệ nhận 403. Không tự biến claims không đáng tin thành ROLE_ADMIN; mappings phải được gắn với hợp đồng của authorization server.

Một IdP có thể dùng **permissions** thay vì scope. Resource server được cấu hình rõ:

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter granted =
        new JwtGrantedAuthoritiesConverter();
    granted.setAuthoritiesClaimName("permissions");
    granted.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(granted);
    return converter;
}
~~~

Thay phần jwt(Customizer.withDefaults()) trong apiChain bằng:

~~~java
.oauth2ResourceServer(oauth -> oauth.jwt(jwt ->
    jwt.jwtAuthenticationConverter(jwtAuthenticationConverter())))
~~~

Đây là **phương án thay thế**, không đặt hai lựa chọn rồi nghĩ chúng tự cộng. Test với token thật để xác nhận claim permissions là string/array tương thích converter, authority prefix, principal name và kết quả authorization.

**Scope là quyền ở mức API; không thay thế quyền ở mức tài nguyên.** User có SCOPE_orders:read vẫn không được xem đơn thuộc tenant khác.

## 7. Chọn JWT hay opaque-token introspection

OAuth2 access token không nhất thiết là JWT. Với **opaque token**, resource server gửi token đến **introspection endpoint** của authorization server để xác định token active và lấy metadata/quyền theo hợp đồng IdP.

Ví dụ cấu hình Boot cho opaque token (chọn thay thế cấu hình JWT nếu đó là dạng token chính thức của hệ thống):

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.internal/oauth2/introspect
~~~

**Client credentials cho introspection phải được cấu hình bổ sung** (client-id, client-secret), ưu tiên secret manager/biến môi trường, không hard-code trong YAML commit lên git. Nếu thiếu credential cần thiết, introspection không thể hoạt động đúng. Có thể dùng tên biến môi trường tương ứng với properties Spring Boot, hoặc đưa secret vào hệ thống quản lý cấu hình bảo mật.

| Yếu tố | JWT local verification | Opaque introspection |
| --- | --- | --- |
| Cơ chế | Xác minh chữ ký/claims bằng keys đáng tin | IdP trả thông tin token active |
| Network mỗi request | Thường không cần nếu keys đã cache | Thường cần gọi introspection; caching phải có policy |
| Revoke sớm | Không tự nhìn thấy ngay nếu chỉ verify offline | Có thể phản ánh revoke nhanh hơn |
| Hiệu năng | Ít phụ thuộc IdP trên request path | Thêm latency, rate limit và nguy cơ IdP outage |
| Vận hành | JWK rotation, audience, issuer | Bảo vệ client secret, timeout, fail closed |
| Phù hợp | Token JWT và lưu lượng cao | Token opaque, cần kiểm tra trạng thái tập trung |

**Không đoán loại token dựa trên hình dạng chuỗi.** Nếu phải chấp nhận nhiều issuer/token type, thiết kế một resolver có allowlist/tenant trust policy cụ thể; tuyệt đối không “thử nhiều decoder cho đến khi một cái pass” mà không giới hạn trust boundary.

**Introspection thất bại do IdP outage phải fail closed.** Cache introspection giúp giảm latency nhưng kéo dài cửa sổ token đã bị thu hồi vẫn được chấp nhận; đây là quyết định security. TLS, secret storage, thời gian chờ và authority mapping đều cần test trên provider thực.

## 8. Stateless, CSRF và CORS là ba cơ chế khác nhau

### Stateless không tự động loại bỏ CSRF

Trong cấu hình API đầu bài có:

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
.csrf(csrf -> csrf.disable())
~~~

Điều này phù hợp với **API chỉ nhận Bearer token qua Authorization header**, không dùng cookie credentials tự động kèm request từ browser. Nhưng với ứng dụng dùng **session cookie**, browser có thể tự gắn cookie khi gửi request cross-site: **CSRF vẫn cần được bảo vệ**, dù server được gọi là “stateless” ở một tầng khác. Không copy disable CSRF sang form login, cookie session hoặc endpoint thay đổi mật khẩu mà không phân tích kiểu credential.

**STATELESS** hướng Spring Security không dùng session để lấy SecurityContext theo mô hình thông thường. Nó không bảo đảm các thư viện khác không bao giờ tạo session hoặc mọi request đã được xác thực.

### CORS preflight chạy trước authorization phù hợp

Một browser cross-origin có thể gửi preflight:

~~~http
OPTIONS /api/v1/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Preflight thường **không có Authorization: Bearer**. Nếu bảo vệ như POST thật trước khi xử lý CORS, browser có thể bị chặn trước khi gửi request chính. Bật CORS tại Security chain:

~~~java
.cors(Customizer.withDefaults())
~~~

và khai báo policy cụ thể:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cfg = new CorsConfiguration();
    cfg.setAllowedOrigins(List.of("https://app.example.com"));
    cfg.setAllowedMethods(
        List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
    cfg.setAllowedHeaders(
        List.of("Authorization", "Content-Type", "If-Match"));
    cfg.setExposedHeaders(
        List.of("Location", "ETag", "X-Request-Id"));

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cfg);
    return source;
}
~~~

**CORS không phải authorization.** curl, Java HttpClient và service-to-service vẫn gọi server được mà không có browser CORS enforcement. Đừng lấy Origin làm tenant/user identity, đừng mở wildcard với credentials và đừng permitAll toàn API để chữa một preflight lỗi. Phải test **OPTIONS** không có token và **POST** thật thiếu token là 401 riêng biệt.

## 9. Phân quyền tại endpoint và tại dữ liệu

**Endpoint rule bảo vệ phương thức/URI, không tự cấp quyền trên mọi row.** Caller có SCOPE_orders:read nhưng gọi ID đơn của tenant khác là ca **Broken Object Level Authorization (BOLA/IDOR)** nếu service chỉ dùng findById rồi trả JSON.

~~~http
GET /api/v1/orders/ord-of-another-tenant HTTP/1.1
Authorization: Bearer <valid-orders-reader-token>
~~~

Controller dùng principal JWT đã xác minh:

~~~java
@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {
    private final OrderQueryService queries;

    public OrderController(OrderQueryService queries) {
        this.queries = queries;
    }

    @GetMapping("/{id}")
    public OrderResponse get(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {

        return queries.findVisible(
            jwt.getSubject(),
            jwt.getClaimAsString("tenant_id"),
            id);
    }
}
~~~

Service/repository **phải lọc tenant trước khi trả entity hoặc COUNT**:

~~~java
public OrderResponse findVisible(
        String subject, String tenant, String id) {
    if (tenant == null || tenant.isBlank()) {
        throw new AccessDeniedException("Tenant required");
    }

    OrderEntity order = repository
        .findByPublicIdAndTenantId(id, tenant)
        .orElseThrow(() -> new ResponseStatusException(
            HttpStatus.NOT_FOUND));

    if (!orderPolicy.canRead(subject, order)) {
        throw new ResponseStatusException(HttpStatus.NOT_FOUND);
    }
    return mapper.toResponse(order);
}
~~~

Các loại **OrderQueryService, repository, orderPolicy, mapper** là thành phần ứng dụng. Claim tenant chỉ đáng tin khi issuer/audience được xác minh và hợp đồng IdP cam kết nó; nếu không, **tra scope tenant từ domain database theo principal**. Ví dụ dùng 404 nhất quán để tránh tiết lộ resource; hệ thống khác có thể dùng 403 theo chính sách.

Có thể bật **@EnableMethodSecurity** và thêm **@PreAuthorize** trên service để kiểm tra scope; annotation vẫn không thay điều kiện tenant trong SQL. Tương tự, áp authorization cho **GET collection/count/pagination, ETag/304 cache, POST owner/tenant server-owned, PUT/PATCH/DELETE, CSV export, async job và SSE**. Không tin tenantId do client gửi trong request body.

## 10. SecurityContext và xử lý bất đồng bộ

Trong Servlet MVC, **SecurityContextHolder** mặc định sử dụng cơ chế gắn với thread. Khi chuyển việc sang **@Async, Executor, CompletableFuture** hoặc một thread mới, **không được giả định** SecurityContext tự động xuất hiện đúng và sạch. Không tự lưu Authentication vào static field, ThreadLocal dùng chung hoặc singleton service.

Các hướng an toàn:

1. Ở request boundary, trích **subject/tenant/scope được xác thực** thành một context bất biến có kiểm soát, đưa vào service/worker như tham số. Worker vẫn kiểm tra quyền cho thao tác cần làm.
2. Nếu thật sự cần propagation SecurityContext trong task ngắn, dùng cơ chế **DelegatingSecurityContextExecutor** hoặc wrapper phù hợp Spring Security, quản lý capture/clear context đúng lifecycle.
3. Với job bền vững/queue, không serialize cả access token vào message hay lưu token người dùng vô hạn. Lưu **job owner/tenant, quyền đã được cho phép** và thực hiện re-authorization theo policy khi chạy/trả kết quả.
4. Với WebFlux, sử dụng **ReactiveSecurityContextHolder**, không lấy ThreadLocal Servlet rồi mong đúng trên reactive pipeline.

**Resource server không tự cấp token cho outbound HTTP client.** Khi gọi downstream, xác định dùng service-to-service credential hay token relay theo trust/audience; không tự động forward inbound Bearer token sang mọi service.

## 11. Error handling và bảo mật dữ liệu

**401/403 từ Security filter chain** thường được xử lý bằng **AuthenticationEntryPoint/AccessDeniedHandler**, không tự đi qua @RestControllerAdvice. Nếu tùy biến thành application/problem+json, bảo toàn **HTTP status và WWW-Authenticate** theo Bearer scheme, không chuyển thành 200 hoặc redirect HTML. Problem Details có thể dùng **type/code ổn định và detail chung**, không phải message chứa user/issuer/key nội bộ.

| Điểm | Rủi ro | Biện pháp |
| --- | --- | --- |
| Access logs/tracing | Lộ Authorization/JWT/PII | Redact header, chỉ ghi endpoint template/requestId/status |
| Error body | Tiết lộ owner/tenant, SQL hoặc token | Detail an toàn, no-store phù hợp |
| Cache/ETag | Trộn response của nhiều tenant | Authz trước khi cache, private/no-store theo dữ liệu |
| JWT claims | Tin role/tenant sai issuer/audience | Validate đầy đủ, claim mapping allowlist |
| JWK/introspection outage | Mở bypass auth khi IdP lỗi | Fail closed, alert và retry hạ tầng có giới hạn |

Không truyền JWT qua URL query vì có thể nằm trong history/log. Tránh lưu PII không cần thiết trong access token ngay từ authorization server.

## 12. Kiểm thử SecurityFilterChain với MockMvc

Dùng **spring-security-test**; test phải kích hoạt đúng SecurityFilterChain. Với integration test Servlet:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderSecurityTests {
    @Autowired MockMvc mvc;

    @Test
    void noBearerTokenGets401() throws Exception {
        mvc.perform(get("/api/v1/orders/ord-501"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                startsWith("Bearer")));
    }

    @Test
    void wrongScopeGets403() throws Exception {
        mvc.perform(get("/api/v1/orders/ord-501")
            .with(jwt().authorities(
                new SimpleGrantedAuthority(
                    "SCOPE_catalog:read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void otherTenantDoesNotSeeOrder() throws Exception {
        mvc.perform(get("/api/v1/orders/ord-501")
            .with(jwt()
                .jwt(j -> j.claim("tenant_id", "tenant-b"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders:read"))))
            .andExpect(status().isNotFound());
    }
}
~~~

Cần **fixture** có ord-501 thuộc tenant khác và principal/authorization policy phù hợp; import MockMvc, SecurityMockMvcRequestPostProcessors.jwt, Hamcrest, JUnit, Spring Security Test. **jwt() mock** dựng Authentication cho MVC, **không xác minh chữ ký/expiry/issuer/audience**: phải có test riêng dùng JWT được ký với key test và mock JWKS/authorization server để chứng minh **token sai chữ ký, iss, aud, exp, nbf bị từ chối**. Test thêm key rotation và opaque introspection inactive/outage nếu dùng.

## 13. Ma trận kiểm thử và hợp đồng OpenAPI

| Case | Kết quả mong đợi |
| --- | --- |
| Token thiếu/sai/hết hạn | 401, WWW-Authenticate phù hợp |
| Token đúng issuer nhưng aud sai | 401, không vào service |
| Token đúng nhưng thiếu scope | 403 |
| Scope đúng, tenant sai | 403/404 theo policy, không lộ resource |
| GET đúng scope và tenant | 200, schema DTO hợp đồng |
| POST thiếu scope | 403, không ghi database |
| CORS OPTIONS đúng origin | Preflight thành công theo policy, không đòi Bearer |
| CORS origin lạ | Browser không được cấp quyền CORS |
| Multi-chain matcher/actuator | Không URL nào vô tình ngoài security policy |
| Parallel requests T1/T2 | Không rò principal, headers hoặc cached body |
| Async job/SSE | Worker/subscriber giữ đúng identity và re-authorization |

Một phần OpenAPI 3.1:

~~~yaml
openapi: 3.1.0
info: { title: Orders API, version: 1.0.0 }
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
paths:
  /api/v1/orders/{id}:
    get:
      security:
        - bearerAuth: []
      responses:
        '200': { description: Đơn hàng được phép đọc }
        '401':
          description: Thiếu hoặc sai access token
          headers:
            WWW-Authenticate:
              schema: { type: string }
        '403': { description: Thiếu quyền đọc }
        '404': { description: Không tìm thấy trong phạm vi được xem }
~~~

**bearerFormat: JWT** là gợi ý tài liệu, không tự xác minh token. Đối với HTTP bearer scheme, OpenAPI không mô tả scope như OAuth2 flows; các quyền thực tế phải ghi rõ trong description/policy và tests.

## 14. Bài tập: bảo vệ Orders API đa tenant

Thiết kế Spring MVC resource server có **GET /api/v1/orders/{id}**, **POST /api/v1/orders**, **GET /api/v1/products/{id}**. Identity provider phát JWT với **iss, aud, sub, scope, tenant_id**.

1. Viết hai SecurityFilterChain có thứ tự rõ (API + fallback) và luật scope đọc/ghi; giải thích securityMatcher khác requestMatchers.
2. Cấu hình JWT decoder kiểm tra issuer/audience/time/signature; chứng minh key rotation, token sai audience bị chặn.
3. Chặn truy vấn đơn ngoài tenant tại repository/service, không tin tenant_id trong request body.
4. Tạo ví dụ HTTP cho 200, 401 + WWW-Authenticate, 403/404 và Problem Details an toàn.
5. Cấu hình stateless Bearer API, giải thích khi nào **không** được disable CSRF và test CORS preflight.
6. Viết tối thiểu 8 test gồm quyền, tenant, token lỗi, actuator/fallback và thread/async.
7. Đề xuất biến thể opaque introspection, phân tích latency, revoke và fail-closed.

**Sản phẩm:** cấu hình Spring, DTO/controller/service, OpenAPI, HTTP transcript và test matrix.

## 15. Checklist trước khi triển khai

- **Chain coverage:** không có request rơi ngoài mọi SecurityFilterChain; matcher/order đã test.
- **Token trust:** signature, issuer, audience, time, key rotation; không nhận ID token thay access token.
- **Authorities:** SCOPE_/ROLE_ và claim mapping đúng issuer, không tự cấp quyền.
- **Authz:** resource/tenant, pagination, cache, job và SSE được kiểm tra ở service.
- **HTTP:** 401/403 và WWW-Authenticate đúng; 2xx không chứa dữ liệu ngoài quyền.
- **Browser:** CORS preflight riêng, CSRF theo loại credential thực.
- **Ops:** TLS, no token logging, IdP outage fail closed, metrics/alerts thích hợp.
- **Tests:** MockMvc cho filter/rules, JWT/JWKS thực cho decoder, database cho BOLA.

**Kết luận:** **SecurityFilterChain xác định cách request được kiểm tra; resource-server decoder xác thực access token; authorization rules và service bảo vệ thao tác cùng từng tài nguyên**. API đáng tin không dừng ở việc thấy Bearer token hợp lệ: nó phải kiểm tra đúng **issuer, audience, scope, tenant và dữ liệu**, đồng thời chứng minh bằng HTTP/security tests.





