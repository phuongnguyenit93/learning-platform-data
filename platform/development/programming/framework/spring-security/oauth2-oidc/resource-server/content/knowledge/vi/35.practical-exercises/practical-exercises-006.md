# Tạo bản WebFlux có chính sách tương đương bản Servlet

Khi chuyển một Spring Security OAuth 2.0/OIDC Resource Server từ **Servlet/MVC** sang **WebFlux**, mục tiêu là giữ nguyên quyết định bảo mật đối với cùng một request: cùng issuer được tin cậy, cùng thuật toán và token profile, cùng audience, cùng scope/role, cùng quy tắc public/private, cùng chính sách lỗi và cùng ranh giới tenant/object.

Hai stack có mô hình thực thi khác nhau. Servlet dùng `HttpSecurity`, `SecurityFilterChain`, `JwtDecoder`, `OpaqueTokenIntrospector` và thường lưu `SecurityContext` theo cơ chế gắn với thread. WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveJwtDecoder`, `ReactiveOpaqueTokenIntrospector` và Reactor Context. Vì vậy, chuyển đổi đúng là **chuyển policy và giữ semantics**, đồng thời dùng đúng API reactive.

Bài học này xây dựng một bản WebFlux tương đương một API Servlet mẫu. Phạm vi gồm:

- JWT Resource Server và opaque token Resource Server.
- Issuer, JWKS, thuật toán, timestamp, audience và scope.
- Public/private routes, HTTP method và nhiều security chains.
- Stateless behavior, CSRF, CORS, exception handling.
- Principal, service layer và reactive method security.
- Kiểm thử bằng `WebTestClient`, test token thật và mock authentication.
- Ma trận so sánh kết quả Servlet/WebFlux để xác nhận parity.

> **Nguyên tắc:** không so sánh số lượng class hay dòng code giữa hai stack. Hãy so sánh policy và kết quả quan sát được. Với cùng một token và cùng một request, Servlet và WebFlux phải đưa ra quyết định tương đương theo contract đã thống nhất.

## 1. Bắt đầu bằng policy inventory của bản Servlet

Trước khi viết cấu hình WebFlux, hãy ghi lại chính sách hiện tại. Nếu chỉ chuyển các matcher mà quên decoder validators, session, CSRF hoặc error handling, hai ứng dụng có thể cùng khởi động nhưng bảo vệ API khác nhau.

Giả sử bản Servlet hiện tại có policy:

| Hạng mục | Chính sách của Orders API |
|---|---|
| Authentication | OAuth 2.0 Bearer access token |
| Token format | JWT theo profile của issuer |
| Issuer | `https://login.example.com/realms/shop` |
| JWKS | Endpoint được issuer công bố |
| Algorithm | Chỉ `RS256` |
| Audience | Phải chứa `orders-api` |
| Timestamp | Validate `exp`, `nbf`, `iat` theo profile và clock-skew policy |
| Token type | Access-token profile được API chấp nhận |
| Scope đọc | `SCOPE_orders.read` |
| Scope ghi | `SCOPE_orders.write` |
| Public routes | `/api/public/**` |
| Read routes | `GET /api/orders/**` |
| Write routes | `POST`, `PUT`, `DELETE /api/orders/**` |
| Default route policy | Deny |
| Session | Stateless cho API Bearer |
| CSRF | Tắt chỉ khi API không dùng cookie tự động gửi làm credential |
| CORS | Chỉ cho phép frontend origins đã phê duyệt |
| Authentication failure | 401 và Bearer challenge |
| Authorization failure | 403 |
| Object access | Chỉ đọc/sửa order thuộc tenant hoặc owner được phép |
| Method security | Có thể kiểm tra thêm ở service boundary |

Đây là contract ví dụ. Khi chuyển một hệ thống thật, thay từng giá trị bằng policy đã được xác nhận của ứng dụng Servlet.

### 1.1. Tách authentication, authorization và business authorization

Ba lớp này cần được giữ độc lập:

1. **Authentication:** token có hợp lệ, đúng issuer, chữ ký, audience và thời hạn không?
2. **HTTP authorization:** caller có scope/authority để gọi route và HTTP method này không?
3. **Business authorization:** caller có quyền thao tác trên order, tenant hoặc object cụ thể không?

Ví dụ token có `orders.read` nhưng `aud=billing-api` phải bị từ chối ở authentication. Token có audience `orders-api` nhưng thiếu `orders.write` được xác thực rồi bị từ chối ở HTTP authorization. Token có scope ghi nhưng order thuộc tenant khác phải bị từ chối ở business authorization.

Không gộp các điều kiện này thành một `permitAll()` hoặc một kiểm tra scope duy nhất.

## 2. Ánh xạ Servlet API sang WebFlux API

| Servlet/MVC | WebFlux | Trách nhiệm |
|---|---|---|
| `HttpSecurity` | `ServerHttpSecurity` | Xây dựng security configuration |
| `SecurityFilterChain` | `SecurityWebFilterChain` | Policy cho một nhóm request |
| `FilterChainProxy` | `WebFilterChainProxy` | Chọn security chain |
| Servlet `Filter` | `WebFilter` | Xử lý request trong filter pipeline |
| `RequestMatcher` | `ServerWebExchangeMatcher` | Chọn route/chain |
| `JwtDecoder` | `ReactiveJwtDecoder` | Decode và validate JWT |
| `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` | Introspect opaque token |
| `AuthenticationManager` | Reactive authentication manager | Xác thực credential bất đồng bộ |
| `SecurityContextHolder` | `ReactiveSecurityContextHolder` | Truy cập security context |
| `SecurityContextRepository` | `ServerSecurityContextRepository` | Lưu/tải context theo stack |
| `AuthenticationEntryPoint` | `ServerAuthenticationEntryPoint` | Xử lý authentication failure |
| `AccessDeniedHandler` | `ServerAccessDeniedHandler` | Xử lý access denied |
| `MockMvc` | `WebTestClient` | Kiểm thử HTTP/security |
| `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` | Method security |
| `MockMvc` + `jwt()` | `WebTestClient` + `mockJwt()` | Mock JWT authentication trong test |

Một số khái niệm giống nhau nhưng kiểu dữ liệu khác nhau. Không truyền `JwtDecoder` vào WebFlux configurer hoặc dùng `MockMvc` để kiểm tra `SecurityWebFilterChain`.

## 3. Dependencies và application type

Một ứng dụng WebFlux Resource Server thường cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Spring Boot BOM quản lý các version tương thích. Không ghép Spring Security Test từ một release khác với runtime.

### 3.1. Tránh vô tình chạy Servlet stack

Nếu cùng classpath có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường chọn application type Servlet theo điều kiện auto-configuration. Khi mục tiêu là WebFlux server:

- Xác nhận ứng dụng khởi động với reactive web application type.
- Tránh kéo `spring-boot-starter-web` vào chỉ vì một dependency khác.
- Nếu phải có cả hai stack, cấu hình application type rõ ràng và hiểu thành phần nào thực sự được khởi chạy.
- Kiểm tra logs/startup context để xác nhận WebFlux server và reactive security chain được dùng.

Chỉ đổi controller trả `Mono` không biến một ứng dụng Servlet thành WebFlux.

## 4. Bản Servlet tham chiếu

Ví dụ cấu hình Servlet có thể trông như sau:

~~~java
@Configuration
class ServletApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Đoạn này giả định decoder được cấu hình riêng bằng properties hoặc Bean để kiểm tra issuer, audience, algorithm và token profile. Nó cũng giả định API chỉ nhận Bearer token trong `Authorization` header, không dùng cookie/session làm credential. Vì vậy, CSRF disable phải được đánh giá theo credential model thực tế.

Bản WebFlux sẽ giữ cùng route policy và token validation, nhưng dùng reactive components.

## 5. Cấu hình WebFlux SecurityFilterChain tương đương

### 5.1. Tạo `SecurityWebFilterChain`

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ReactiveApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            .csrf(csrf -> csrf.disable())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .pathMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .pathMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Các tương ứng quan trọng:

- `ServerHttpSecurity` thay `HttpSecurity`.
- `SecurityWebFilterChain` thay `SecurityFilterChain`.
- `authorizeExchange` thay `authorizeHttpRequests`.
- `pathMatchers` thay `requestMatchers`.
- `anyExchange().denyAll()` thay `anyRequest().denyAll()`.
- `oauth2ResourceServer().jwt(...)` vẫn bật JWT Bearer authentication.
- `NoOpServerSecurityContextRepository` thể hiện policy không persist security context vào WebSession cho API này.

Nếu dự án có policy CSRF/CORS khác, hãy giữ policy đó thay vì sao chép `disable()` từ ví dụ.

### 5.2. Khi nào dùng `Customizer.withDefaults()`?

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
)
~~~

Cách này dùng `ReactiveJwtDecoder` phù hợp có trong application context, có thể do Spring Boot auto-configuration tạo từ properties hoặc do ứng dụng khai báo Bean.

Nếu ứng dụng dùng opaque token:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
)
~~~

Không bật cả JWT và opaque chỉ vì muốn “hỗ trợ mọi loại token”. Chỉ bật theo token contract của issuer và cách authentication manager được thiết kế.

### 5.3. Stateless trong WebFlux

Servlet thường dùng:

~~~java
.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
~~~

WebFlux không dùng `SessionCreationPolicy` theo cùng cách. `ServerSecurityContextRepository` quyết định context có được lưu/tải từ server-side session hay không.

Với API Bearer stateless, có thể dùng:

~~~java
.securityContextRepository(
    NoOpServerSecurityContextRepository.getInstance()
)
~~~

Điều này không có nghĩa mọi thành phần của ứng dụng không bao giờ dùng `WebSession`. WebFlux vẫn có thể dùng session cho các chức năng khác. Nó chỉ xác định security context của chain này không được persist theo repository đó.

Nếu ứng dụng có browser login/session, nên dùng chain riêng và repository phù hợp cho browser flow.

## 6. Giữ nguyên JWT validation khi chuyển decoder

### 6.1. Dùng properties nếu policy chuẩn đã đủ

Ví dụ cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://login.example.com/realms/shop/protocol/openid-connect/certs
          jws-algorithms:
            - RS256
~~~

Tên và khả năng của properties như `audiences` phụ thuộc Spring Boot version. Nếu cần bảo đảm audience validation xuyên version, hãy khai báo validator rõ ràng trong decoder và kiểm tra đúng behavior của BOM đang dùng.

`issuer-uri` là canonical issuer. `jwk-set-uri` là nơi lấy public keys. Không thay issuer bằng JWKS URL và không bỏ issuer validation chỉ vì đã biết JWKS URI.

### 6.2. Khai báo `ReactiveJwtDecoder` tường minh

Khi cần policy cụ thể, có thể tạo decoder reactive:

~~~java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration(proxyBeanMethods = false)
public class ReactiveJwtDecoderConfiguration {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder
                .withJwkSetUri(jwkSetUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Required audience is missing",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator
            )
        );

        return decoder;
    }
}
~~~

Cấu hình này giữ:

- Chữ ký JWS qua public keys lấy từ JWKS URI.
- Chỉ cho phép `RS256`.
- Issuer validation.
- Timestamp validation mặc định trong validator tương ứng.
- Audience bắt buộc phải chứa `orders-api` (giá trị lấy từ property).

Nếu API yêu cầu RFC 9068, custom `typ` hoặc token profile riêng, cần thêm validator profile tương ứng. Không tắt type validation rồi quên thay bằng profile validator.

### 6.3. Khi dùng decoder custom, auto-configuration lùi lại

Khai báo `ReactiveJwtDecoder` Bean có thể thay decoder mà Boot định tạo. Vì vậy, không mặc định rằng decoder custom tự nhận toàn bộ properties `issuer-uri`, `audiences` và `jws-algorithms`.

Hãy đưa các điều kiện cần thiết vào decoder custom và viết negative tests cho:

- Issuer sai.
- Audience sai.
- Chữ ký sai.
- Algorithm ngoài allowlist.
- Token hết hạn.
- Token sai type/profile.

### 6.4. Phân biệt JWT authentication với authorization

Decoder chỉ xác minh token. Sau đó Spring Security ánh xạ scope/claim thành `GrantedAuthority`.

Theo convention thông thường, claim `scope` hoặc `scp` được ánh xạ thành authority có prefix `SCOPE_`:

~~~text
scope = "orders.read orders.write"

Authorities:
  SCOPE_orders.read
  SCOPE_orders.write
~~~

Nếu bản Servlet dùng custom `JwtAuthenticationConverter` đọc claim `permissions`, bản WebFlux phải dùng converter reactive tương ứng hoặc adapter phù hợp. Không assume converter Servlet được dùng trực tiếp trong reactive chain.

## 7. Custom authority mapping trong WebFlux

Giả sử token của issuer chứa:

~~~json
{
  "sub": "user-42",
  "permissions": ["orders.read", "orders.write"]
}
~~~

Bản Servlet có thể dùng `JwtAuthenticationConverter` kết hợp `JwtGrantedAuthoritiesConverter`. Trong WebFlux, authentication conversion là reactive; dùng `ReactiveJwtAuthenticationConverter` hoặc adapter mà Spring Security version của dự án cung cấp.

Ví dụ cấu hình khái niệm:

~~~java
ReactiveJwtAuthenticationConverter converter =
    new ReactiveJwtAuthenticationConverter();

JwtGrantedAuthoritiesConverter authoritiesConverter =
    new JwtGrantedAuthoritiesConverter();

authoritiesConverter.setAuthoritiesClaimName("permissions");
authoritiesConverter.setAuthorityPrefix("SCOPE_");

converter.setJwtGrantedAuthoritiesConverter(
    new ReactiveJwtGrantedAuthoritiesConverterAdapter(
        authoritiesConverter
    )
);
~~~

Sau đó gắn converter vào JWT configurer:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(converter)
    )
)
~~~

Các class/adapter và package cụ thể cần được xác nhận theo Spring Security version. Nếu dự án không cần custom claim mapping, giữ default converter là lựa chọn đơn giản hơn.

### 7.1. Parity phải so sánh authority, không chỉ claim

Cùng một token cần tạo ra cùng tập authorities ở hai stack:

| Token claim | Servlet expected | WebFlux expected |
|---|---|---|
| `scope=orders.read` | `SCOPE_orders.read` | `SCOPE_orders.read` |
| `scope=orders.write` | `SCOPE_orders.write` | `SCOPE_orders.write` |
| `permissions=["orders.admin"]` | Theo custom converter | Cùng kết quả từ reactive converter |
| Không có scope | Không có scope authority | Không có scope authority |
| Scope không được nhận diện | Không tự cấp quyền | Không tự cấp quyền |

Nếu một converter dùng `ROLE_` và converter kia dùng `SCOPE_`, hai ứng dụng sẽ có quyết định khác nhau dù cùng token.

## 8. Opaque token: chuyển sang reactive introspection

Nếu Servlet Resource Server dùng opaque token, WebFlux phải dùng `ReactiveOpaqueTokenIntrospector`.

### 8.1. Properties

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: "${ORDERS_INTROSPECTION_CLIENT_SECRET}"
~~~

Nếu Boot version hỗ trợ reactive opaque Resource Server auto-configuration, properties có thể tạo introspector reactive phù hợp. Kiểm tra dependency stack và auto-configuration report của version đang dùng.

### 8.2. Security chain

~~~java
@Bean
SecurityWebFilterChain opaqueApiSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public/**").permitAll()
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(Customizer.withDefaults())
        )
        .build();
}
~~~

### 8.3. Custom reactive introspector

Khi cần custom timeout, HTTP client, cache hoặc response mapping, khai báo `ReactiveOpaqueTokenIntrospector` Bean. Nó trả `Mono<OAuth2AuthenticatedPrincipal>`.

Không gọi Servlet `OpaqueTokenIntrospector` có blocking network I/O trực tiếp trên event loop. Nếu buộc phải tích hợp một thư viện blocking, cần chuyển việc đó sang scheduler dành cho blocking work và quản lý timeout/cancellation rõ ràng; ưu tiên reactive client.

### 8.4. Giữ nguyên opaque token semantics

Cả hai stack cần giữ:

- `active=false` phải bị từ chối.
- Introspection client authentication đúng.
- Issuer/resource context đúng contract.
- Scope mapping giống nhau.
- Timeout và dependency failure không fail open.
- Cache TTL không vượt revocation SLA.
- Không log raw access token hoặc client secret.

Principal mặc định của opaque token thường là `OAuth2AuthenticatedPrincipal`, trong khi JWT principal thường là `Jwt`. Nếu controller đang cast principal thành `Jwt`, cần sửa adapter/domain boundary để hỗ trợ đúng loại token.

## 9. Route policy: chuyển matcher nhưng giữ thứ tự và semantics

### 9.1. Bảng ánh xạ matcher

| Servlet | WebFlux |
|---|---|
| `.authorizeHttpRequests(...)` | `.authorizeExchange(...)` |
| `.requestMatchers("/api/public/**")` | `.pathMatchers("/api/public/**")` |
| `.requestMatchers(HttpMethod.GET, "/api/**")` | `.pathMatchers(HttpMethod.GET, "/api/**")` |
| `.anyRequest().denyAll()` | `.anyExchange().denyAll()` |
| `.hasAuthority("SCOPE_orders.read")` | `.hasAuthority("SCOPE_orders.read")` |
| `.hasRole("ADMIN")` | `.hasRole("ADMIN")` |
| `.authenticated()` | `.authenticated()` |
| `.permitAll()` | `.permitAll()` |

Cùng một tên authority không bảo đảm cùng policy nếu matcher hoặc thứ tự khác nhau.

### 9.2. Ví dụ route policy đầy đủ

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .pathMatchers(
        HttpMethod.POST,
        "/api/orders/**"
    ).hasAuthority("SCOPE_orders.write")
    .pathMatchers(
        HttpMethod.PUT,
        "/api/orders/**"
    ).hasAuthority("SCOPE_orders.write")
    .pathMatchers(
        HttpMethod.DELETE,
        "/api/orders/**"
    ).hasAuthority("SCOPE_orders.write")
    .pathMatchers("/actuator/health").permitAll()
    .anyExchange().denyAll()
)
~~~

Hãy kiểm tra:

- GET không bị áp nhầm scope ghi.
- POST/PUT/DELETE đều cần quyền ghi.
- Public route không vô tình match rộng.
- Actuator policy không làm lộ endpoint quản trị.
- Unknown route bị deny.
- Path variables, trailing slash, encoded path và context path có behavior được xác nhận.

### 9.3. `permitAll()` không bỏ qua Bearer filter

Một request public không cần token để được authorization. Nhưng nếu client vẫn gửi một Bearer token malformed, authentication WebFilter có thể xử lý token đó và từ chối request trước khi controller chạy.

Đây là behavior quan trọng khi so sánh hai stack: không test public route bằng một header invalid rồi kỳ vọng `permitAll()` sẽ luôn bỏ qua credential parsing.

## 10. Nhiều SecurityWebFilterChain và thứ tự

Nếu bản Servlet có nhiều `SecurityFilterChain`, WebFlux cần các `SecurityWebFilterChain` tương ứng, với matcher và `@Order` rõ ràng.

Ví dụ API chain:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**")
        )
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public/**").permitAll()
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

Browser/fallback chain có thể được cấu hình riêng:

~~~java
@Bean
@Order(2)
SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/assets/**").permitAll()
            .anyExchange().denyAll()
        )
        .build();
}
~~~

Các imports chính:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
~~~

`WebFilterChainProxy` chọn chain phù hợp theo matcher và thứ tự. Vì vậy:

- Chain `/api/**` phải đứng trước chain rộng hơn.
- Fallback chain cần policy rõ.
- Không để chain đầu tiên match mọi request ngoài ý muốn.
- Không bỏ sót route nhạy cảm giữa các chain.
- Mỗi chain phải bật đúng authentication mechanism.

Nếu chain API dùng JWT còn chain browser dùng form login, không cần gắn JWT decoder vào browser chain. Nếu hai API chains dùng cùng trust policy, có thể dùng chung reactive decoder; nếu issuer/audience/algorithm khác nhau, phải tách decoder/manager theo trust context.

## 11. CSRF: giữ cùng threat model, không chỉ cùng một dòng config

Servlet và WebFlux đều có CSRF protection, nhưng API và browser flow có thể có credential model khác nhau.

### 11.1. Khi nào có thể tắt CSRF?

Một API chỉ nhận Bearer token qua `Authorization` header mà client chủ động gắn thường có threat model CSRF khác cookie authentication. Nếu ứng dụng không dùng cookie tự động gửi làm credential cho API, có thể cấu hình:

~~~java
.csrf(csrf -> csrf.disable())
~~~

### 11.2. Khi nào không nên tắt?

Nếu browser tự động gửi session cookie hoặc authentication cookie, request cross-site có thể mang credential mà attacker không cần biết. CSRF protection vẫn có thể cần thiết.

JWT không tự loại bỏ CSRF. Nếu JWT được đặt trong cookie, browser có thể gửi cookie tự động; phải đánh giá CSRF theo cách credential được vận chuyển.

### 11.3. Parity test cho CSRF

| Request | Servlet expected | WebFlux expected |
|---|---|---|
| GET private route, token hợp lệ | Cho qua nếu đủ scope | Cùng kết quả |
| POST, Bearer header, CSRF disabled theo policy | Đánh giá theo API contract | Cùng kết quả |
| POST, cookie/session auth, CSRF thiếu | 403 nếu CSRF bật | 403 nếu CSRF bật |
| POST, CSRF token hợp lệ | Tiếp tục authorization | Cùng kết quả |

Không thêm CSRF token vào mọi WebFlux test chỉ để làm test pass. Test phải phản ánh đúng policy của endpoint.

## 12. CORS: chuyển cấu hình sang reactive source

WebFlux dùng reactive CORS configuration source:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration configuration = new CorsConfiguration();

    configuration.setAllowedOrigins(
        List.of("https://app.example.com")
    );
    configuration.setAllowedMethods(
        List.of("GET", "POST", "PUT", "DELETE", "OPTIONS")
    );
    configuration.setAllowedHeaders(
        List.of("Authorization", "Content-Type", "X-Request-Id")
    );
    configuration.setExposedHeaders(
        List.of("WWW-Authenticate")
    );
    configuration.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();

    source.registerCorsConfiguration("/api/**", configuration);

    return source;
}
~~~

Dùng reactive types:

~~~java
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
~~~

Gắn vào chain:

~~~java
.cors(cors -> cors.configurationSource(corsConfigurationSource))
~~~

Các giá trị trên chỉ là ví dụ. Cần giữ đúng origin, methods, headers và credentials policy của bản Servlet.

### 12.1. Những khác biệt cần kiểm tra

- `Authorization` có nằm trong allowed headers không?
- Preflight `OPTIONS` có được xử lý trước authentication không?
- `WWW-Authenticate` có được expose nếu browser JavaScript cần đọc không?
- Có cho phép credentials/cookies không?
- Có dùng wildcard origin trong khi `allowCredentials=true` không?
- Gateway/proxy có sửa CORS headers không?

Mock test kiểm tra response của server; browser E2E mới xác nhận browser thực thi CORS protocol đúng.

## 13. Authentication failure và Access Denied trong WebFlux

Servlet dùng `AuthenticationEntryPoint` và `AccessDeniedHandler`. WebFlux dùng:

- `ServerAuthenticationEntryPoint`.
- `ServerAccessDeniedHandler`.

Spring Security Resource Server có các handler Bearer reactive tương ứng, ví dụ `BearerTokenServerAuthenticationEntryPoint` và `BearerTokenServerAccessDeniedHandler`.

Thông thường, bật `.oauth2ResourceServer().jwt()` hoặc `.opaqueToken()` sẽ cấu hình Bearer authentication behavior mặc định.

### 13.1. Status parity

| Tình huống | Kết quả mong đợi |
|---|---|
| Private route, không có token | 401 |
| Bearer token malformed/invalid | 401 |
| JWT sai issuer/audience/signature | 401 |
| Opaque token inactive | 401 |
| Token hợp lệ nhưng thiếu scope | 403 |
| Tenant/object policy từ chối | 403 hoặc 404 theo contract |
| Request vượt rate limit | 429 nếu gateway/app policy dùng 429 |
| Identity provider timeout | Không authenticated; status phụ thuộc dependency/error contract nhưng không fail open |

Đừng biến audience mismatch thành 403: token không dành cho API không được xác thực tại API đó.

### 13.2. Giữ `WWW-Authenticate`

Với Bearer Resource Server, response 401 nên có challenge `WWW-Authenticate: Bearer`. Invalid token có thể có `error="invalid_token"`. Insufficient scope có thể được phản ánh bằng 403 và `error="insufficient_scope"`.

Nếu custom reactive entry point ghi JSON body, vẫn phải giữ protocol challenge phù hợp. Không để custom handler làm mất header mà client dựa vào.

### 13.3. Custom reactive handlers

Có thể gắn handlers qua exception handling configurer hoặc Resource Server configurer tùy mục tiêu. Dùng các reactive interfaces và trả `Mono<Void>`; không dùng Servlet handler ghi trực tiếp vào `HttpServletResponse`.

Không gọi `.block()` trong handler. Ghi body bằng reactive response APIs và đảm bảo response chỉ được commit một lần.

## 14. Principal và service layer: thay ThreadLocal bằng Reactor Context

Trong Servlet, code có thể đọc:

~~~java
SecurityContextHolder.getContext()
    .getAuthentication();
~~~

Trong WebFlux, dùng:

~~~java
ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication);
~~~

Ví dụ service:

~~~java
@Service
public class CurrentCallerService {

    public Mono<String> currentSubject() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }
}
~~~

Controller có thể dùng:

~~~java
@GetMapping("/api/me")
Mono<Map<String, String>> me(@AuthenticationPrincipal Jwt jwt) {
    return Mono.just(Map.of(
        "subject", jwt.getSubject(),
        "issuer", jwt.getIssuer().toString()
    ));
}
~~~

Hoặc lấy principal chung:

~~~java
@GetMapping("/api/whoami")
Mono<String> whoAmI(ServerWebExchange exchange) {
    return exchange.getPrincipal()
        .map(Principal::getName);
}
~~~

### 14.1. Không giả định principal luôn là Jwt

JWT mode thường dùng `JwtAuthenticationToken` với principal `Jwt`. Opaque mode thường dùng `BearerTokenAuthentication` với principal `OAuth2AuthenticatedPrincipal`.

Nếu bản Servlet controller cast principal thành `Jwt`, hãy xem endpoint WebFlux có thể nhận opaque token hay không. Nếu có, tạo domain abstraction như `CallerIdentity` và map từ các principal được xác thực.

### 14.2. Không gọi `block()` hoặc `subscribe()` trong service

Sai:

~~~java
String subject = ReactiveSecurityContextHolder.getContext()
    .map(context -> context.getAuthentication().getName())
    .block();
~~~

Sai:

~~~java
repository.save(order).subscribe();
return Mono.empty();
~~~

Đúng:

~~~java
public Mono<Order> createOrder(Order order) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(subject ->
            repository.save(order.withOwner(subject))
        );
}
~~~

Các publisher cần nằm trong cùng reactive chain để context, cancellation và error propagation được giữ.

### 14.3. Tenant và object ownership

Ví dụ service chỉ truy vấn order của caller:

~~~java
public Mono<Order> findOrder(String orderId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(subject ->
            repository.findByIdAndOwnerSubject(orderId, subject)
        );
}
~~~

Trong hệ thống multi-issuer, subject có thể trùng giữa các issuer. Domain identity nên dùng canonical user ID hoặc cặp `(issuer, subject)`. Tenant phải được lấy từ claim đã xác minh hoặc membership store đáng tin, không lấy từ header tùy ý.

## 15. Reactive method security

Nếu bản Servlet có:

~~~java
@EnableMethodSecurity
~~~

bản WebFlux dùng:

~~~java
@EnableReactiveMethodSecurity
~~~

Ví dụ:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

Service:

~~~java
@Service
public class OrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Flux<Order> findOrders() {
        return repository.findAll();
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    public Mono<Order> createOrder(Order order) {
        return repository.save(order);
    }
}
~~~

Reactive method security dùng security context của Reactor và các method được bảo vệ cần trả reactive Publisher như `Mono` hoặc `Flux` để authorization chạy trong reactive flow.

### 15.1. HTTP authorization không thay business authorization

Ngay cả khi route yêu cầu `SCOPE_orders.write`, service vẫn có thể cần kiểm tra:

- Order có thuộc tenant của caller không?
- Caller có phải owner hoặc delegate không?
- Trạng thái order có cho phép cập nhật không?
- Service token có được thực hiện hành động này không?
- Resource thuộc đúng organization/project không?

Đây là object-level/business authorization. Chuyển sang WebFlux không làm các quy tắc này tự xuất hiện.

## 16. Kiểm thử WebFlux bằng WebTestClient

### 16.1. Test application context

Ví dụ:

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveOrdersSecurityTests {

    @Autowired
    WebTestClient webTestClient;
}
~~~

Boot tạo WebTestClient theo application context. Đảm bảo test đang chạy WebFlux stack và các security WebFilters được đăng ký.

Nếu tự tạo client từ context:

~~~java
@BeforeEach
void setUp() {
    webTestClient = WebTestClient
        .bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
}
~~~

`springSecurity()` trong reactive test support gắn Spring Security WebFilters vào WebTestClient. Tránh đăng ký security filters trùng khi đã dùng auto-configuration tương ứng.

### 16.2. Test slice với `@WebFluxTest`

~~~java
@WebFluxTest(controllers = OrdersController.class)
@Import(ReactiveApiSecurityConfiguration.class)
class OrdersControllerSecurityTests {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    OrdersService ordersService;
}
~~~

`@WebFluxTest` tải một phần WebFlux context. Hãy import đúng security configuration production cần kiểm tra. Tùy Spring Boot/Spring Framework version, dự án cũ có thể dùng `@MockBean` thay cho `@MockitoBean`.

Không thay security config bằng một chain test `permitAll()` rồi kết luận production policy đúng.

## 17. Mock authentication và Bearer token thật

### 17.1. Dùng `mockJwt()` để test authorization

~~~java
webTestClient
    .mutateWith(mockJwt()
        .jwt(jwt -> jwt
            .subject("user-42")
            .claim("scope", "orders.read")
        )
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    )
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

`mockJwt()` tạo JWT authentication giả lập. Nó hữu ích để kiểm tra:

- Path matcher.
- Authority rules.
- Controller nhận principal.
- Method security.
- Business policy sử dụng authentication.

Nó không chứng minh `ReactiveJwtDecoder` đã verify chữ ký, issuer, audience hoặc JWKS.

### 17.2. Dùng `mockOpaqueToken()`

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .attributes(attributes ->
            attributes.put("sub", "user-42")
        )
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    )
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Request post processor này tạo opaque authentication mẫu. Nó không gọi introspection endpoint.

### 17.3. Test thiếu token và scope

~~~java
@Test
void privateRouteWithoutTokenReturns401() {
    webTestClient
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isUnauthorized()
        .expectHeader().valueMatches(
            HttpHeaders.WWW_AUTHENTICATE,
            "Bearer.*"
        );
}

@Test
void readOnlyTokenCannotCreateOrder() {
    webTestClient
        .mutateWith(mockJwt()
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )
        )
        .post()
        .uri("/api/orders")
        .bodyValue(new CreateOrderRequest("SKU-1", 2))
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Test đầu xác nhận missing Bearer credentials. Test thứ hai xác nhận HTTP authorization với mock authentication. Nếu CSRF vẫn bật trong ứng dụng, POST có thể bị từ chối bởi CSRF trước khi scope rule được kiểm tra; cấu hình/test phải phù hợp credential model.

### 17.4. Gửi Bearer token thực

Muốn kiểm tra resolver, authentication manager và decoder, gửi token qua header:

~~~java
webTestClient
    .post()
    .uri("/api/orders")
    .headers(headers ->
        headers.setBearerAuth(signedAccessToken)
    )
    .bodyValue(new CreateOrderRequest("SKU-1", 2))
    .exchange()
    .expectStatus().isCreated();
~~~

Dùng decoder thật với test key/JWKS hoặc test Authorization Server. Không dùng `mockJwt()` trong test muốn xác nhận chữ ký.

### 17.5. Test opaque introspection thật qua stub

Cấu hình `ReactiveOpaqueTokenIntrospector` trỏ tới HTTP stub. Gửi Bearer token bình thường và xác nhận:

- Introspector được gọi.
- Request dùng POST và client authentication đúng.
- `active=true` tạo authentication.
- `active=false` bị từ chối.
- Scope/authority mapping giống bản Servlet.
- Timeout/5xx không fail open.

Không dùng `mockOpaqueToken()` để chứng minh introspection HTTP hoạt động.

## 18. Test parity: cùng input, so sánh kết quả hai stack

Một cách hiệu quả là tạo bộ test contract dùng chung dữ liệu đầu vào và chạy cho cả Servlet lẫn WebFlux.

### 18.1. Ma trận token

| Token fixture | Servlet expected | WebFlux expected |
|---|---|---|
| JWT hợp lệ, đúng issuer/audience/scope | 2xx theo endpoint | Cùng status/body contract |
| Không có token vào private route | 401 | 401 |
| JWT malformed | 401 | 401 |
| Signature sai | 401 | 401 |
| Issuer sai | 401 | 401 |
| Audience sai | 401 | 401 |
| Token hết hạn | 401 | 401 |
| Algorithm ngoài allowlist | 401 | 401 |
| Sai token type/profile | 401 | 401 |
| Đúng token nhưng thiếu scope | 403 | 403 |
| Opaque token inactive | 401 | 401 |
| Opaque active nhưng thiếu scope | 403 | 403 |

Nếu hai ứng dụng có error body khác nhau nhưng contract không yêu cầu giống body, hãy so sánh status, challenge header và quyết định truy cập. Nếu body là public API contract, phải giữ cùng schema.

### 18.2. Ma trận route

| Request | Servlet | WebFlux |
|---|---|---|
| `GET /api/public/health` không token | Permit | Permit |
| `GET /api/orders` với read scope | Permit | Permit |
| `POST /api/orders` với read scope | 403 | 403 |
| `POST /api/orders` với write scope | Permit | Permit |
| `DELETE /api/orders/42` với read scope | 403 | 403 |
| `GET /admin/reports` với API scope | Theo admin policy | Cùng policy |
| Unknown route | Deny | Deny |

### 18.3. Ma trận principal/business policy

- Cùng issuer và subject tạo cùng domain caller identity.
- Cùng scope tạo cùng authority set.
- Cùng tenant claim được xác minh tạo cùng tenant context.
- Tenant mismatch cho cùng kết quả 403/404.
- Object ownership check có cùng semantics.
- Service token và user token có policy riêng như trước.
- Không có request nào nhận principal từ request trước.

### 18.4. Đừng chỉ so sánh status

Cùng 200 vẫn có thể lộ dữ liệu khác nhau. Cùng 403 vẫn có thể đến từ hai tầng khác nhau.

Với các endpoint nhạy cảm, so sánh thêm:

- Response body và dữ liệu trả về.
- Service/repository calls.
- Side effects.
- Tenant filter trong query.
- Audit events.
- Rate-limit behavior.
- `WWW-Authenticate`.
- Error code ổn định của API.

## 19. Cấu hình test token dùng chung

Để chạy contract tests cho cả hai stack, tạo fixture token có thể tái sử dụng:

~~~text
Test signing key pair
       |
       +--> JWT valid: issuer A, audience orders-api, scope read
       |
       +--> JWT valid: issuer A, audience orders-api, scope write
       |
       +--> JWT wrong issuer
       |
       +--> JWT wrong audience
       |
       +--> JWT expired
       |
       +--> JWT signed by another key
       |
       +--> JWT wrong typ/profile
       |
       +--> JWT with disallowed alg
~~~

Các fixture phải được ký bằng private test key. Public key/JWKS test được dùng bởi cả `JwtDecoder` Servlet và `ReactiveJwtDecoder` WebFlux.

### 19.1. Dùng cùng issuer/audience validator contract

Nếu có thể, tách các policy constants và test fixtures dùng chung ở module không phụ thuộc Servlet/WebFlux:

~~~java
public final class OrdersTokenPolicy {
    public static final String ISSUER =
        "https://idp.test.example";

    public static final String AUDIENCE =
        "orders-api";

    public static final String READ_SCOPE =
        "SCOPE_orders.read";

    public static final String WRITE_SCOPE =
        "SCOPE_orders.write";

    private OrdersTokenPolicy() {
    }
}
~~~

Không nhất thiết chia sẻ cùng một decoder implementation; Servlet và WebFlux cần decoder khác kiểu. Có thể chia sẻ constants, expected outcomes, key fixtures và contract tests.

### 19.2. Tránh tạo policy drift

Nếu cùng một issuer URL được hardcode trong hai config files, chúng có thể lệch nhau khi đổi môi trường. Dùng externalized configuration và kiểm tra profile binding để cả hai stack nhận cùng trust metadata.

Tuy nhiên, không dùng một property chung nếu Servlet và WebFlux thực sự có trust boundary khác nhau. Khi policy khác, phải ghi nhận đó là thay đổi chủ ý, không phải lỗi migration.

## 20. Error handling parity

### 20.1. Authentication failure

Các trường hợp thường trả 401:

- Missing token.
- Malformed bearer token.
- JWT signature invalid.
- Issuer/audience/type validation fail.
- Opaque token inactive.

WebFlux cần giữ Bearer challenge. Không để custom `ServerAuthenticationEntryPoint` bỏ header `WWW-Authenticate`.

### 20.2. Authorization failure

Các trường hợp thường trả 403:

- Thiếu scope.
- Thiếu role.
- Method security từ chối.
- Tenant/ownership policy từ chối (hoặc 404 theo anti-enumeration contract).

Dùng `ServerAccessDeniedHandler` cho reactive path. Không dùng Servlet `AccessDeniedHandler`.

### 20.3. Dependency outage

Nếu JWKS hoặc introspection endpoint timeout:

- Không tạo authenticated principal.
- Không coi timeout như token hợp lệ.
- Không retry vô hạn.
- Phân biệt invalid token với dependency failure trong metrics/logs.
- Status công khai theo API contract có thể là 401 hoặc 503 tùy cách phân loại lỗi; điều bắt buộc là fail closed.

Nếu bản Servlet có custom error mapping cho dependency outage, bản WebFlux cần mapping tương ứng và tests xác nhận.

## 21. CORS và WWW-Authenticate trong browser client

Nếu frontend cần phân biệt missing token và invalid token, nó có thể cần đọc `WWW-Authenticate`. Trong CORS configuration:

~~~java
configuration.setExposedHeaders(
    List.of("WWW-Authenticate")
);
~~~

Nếu không expose header, browser JavaScript có thể không đọc được nó dù server đã trả.

Đây là một ví dụ parity thường bị bỏ sót: Servlet và WebFlux có thể trả cùng 401 nhưng browser nhìn thấy headers khác nhau vì CORS config không tương đương.

## 22. Quan sát và vận hành sau migration

Theo dõi cả hai ứng dụng trong staging:

| Chỉ số | Mục đích |
|---|---|
| 401 rate | Authentication failure |
| 403 rate | Authorization denial |
| JWT decoder latency | Chi phí xác minh |
| JWKS fetch count/duration | Key retrieval |
| Unknown `kid` | Key rotation hoặc input bất thường |
| Introspection latency | Dependency AS |
| 5xx/timeout | Identity provider availability |
| Request p95/p99 | Latency toàn API |
| Active WebFlux connections | Reactive server load |
| Thread/event-loop saturation | Blocking code hoặc CPU pressure |
| Memory/connection pool | Resource usage |
| Tenant authorization denials | Business policy behavior |

Tên metric phụ thuộc Micrometer/instrumentation; bảng là nhóm cần quan sát chứ không khẳng định mọi metric tự có.

### 22.1. Phát hiện blocking trong reactive path

Một bản WebFlux có thể có policy đúng nhưng hiệu năng kém nếu gọi JDBC/blocking HTTP trên event loop. Kiểm tra:

- Có `.block()` trong controller/service/filter không?
- Có `.subscribe()` lồng trong service không?
- Có dùng Servlet `JwtDecoder` đồng bộ trong reactive request path không?
- Có gọi blocking introspection client trên event loop không?
- Có CPU-heavy work không giới hạn concurrency không?
- Có dùng Reactor scheduler đúng cho blocking boundary bắt buộc không?

Chuyển sang WebFlux không tự làm mọi dependency thành non-blocking.

## 23. Lộ trình migration có kiểm soát

**Bước 1 — Ghi nhận policy Servlet.** Lập inventory issuer, JWKS, algorithms, audience, token profile, routes, authorities, session, CSRF, CORS, errors và business rules.

**Bước 2 — Tạo reactive application slice.** Thêm WebFlux dependencies và xác nhận application type thực sự là reactive.

**Bước 3 — Tạo `SecurityWebFilterChain`.** Chuyển request matchers sang `authorizeExchange` và giữ nguyên public/private/method rules.

**Bước 4 — Chuyển decoder.** Dùng `ReactiveJwtDecoder` hoặc `ReactiveOpaqueTokenIntrospector`, giữ issuer/audience/algorithm/type/active checks.

**Bước 5 — Chuyển authority mapping.** Giữ cùng claim source và prefix; xác nhận authority set giống nhau.

**Bước 6 — Chuyển session/CSRF/CORS.** Dùng `ServerSecurityContextRepository` và reactive CORS source theo credential model.

**Bước 7 — Chuyển principal/service.** Thay ThreadLocal access bằng Reactor Context; loại bỏ blocking và nested subscriptions.

**Bước 8 — Chuyển method security.** Dùng `@EnableReactiveMethodSecurity` và publisher-returning methods.

**Bước 9 — Viết parity tests.** Cùng token fixtures và request matrix chạy qua cả Servlet lẫn WebFlux.

**Bước 10 — So sánh staging.** So sánh status, headers, response data, side effects, tenant filters, latency và dependency calls.

**Bước 11 — Rollout có kiểm soát.** Dùng traffic shadow/canary nếu kiến trúc cho phép, theo dõi 401/403 và rollback khi policy drift.

## 24. Những lỗi migration thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| WebFlux nhận token nhưng scope không có | Reactive converter khác Servlet converter | So sánh authority mapping |
| JWT hợp lệ ở Servlet nhưng 401 ở WebFlux | Khác JWKS URI, issuer, audience, algorithm hoặc clock skew | So sánh decoder validators |
| ID token qua một stack nhưng bị từ chối ở stack kia | Token-type validation không đồng nhất | Thống nhất token profile |
| Route public ở Servlet nhưng 401 ở WebFlux | Chain matcher/order hoặc Bearer header invalid | Kiểm tra WebFilter chain và resolver |
| Route private bị mở ở WebFlux | Thiếu `anyExchange().denyAll()` hoặc chain không match | Thêm fallback policy |
| POST luôn 403 | CSRF còn bật trong WebFlux hoặc thiếu CSRF token | Kiểm tra credential model và CSRF policy |
| Browser không đọc được WWW-Authenticate | CORS không expose header | Thêm exposed header |
| Principal có ở controller nhưng rỗng ở service | Service tạo subscription độc lập hoặc dùng ThreadLocal | Dùng `ReactiveSecurityContextHolder` trong cùng chain |
| Request bị chậm dù dùng WebFlux | Blocking I/O trên event loop | Dùng reactive client/repository hoặc scheduler phù hợp |
| Opaque token gây tải AS tăng | Introspection bị gọi nhiều, cache/timeout khác | So sánh introspector policy |
| Nhiều issuer bị chọn sai decoder | Resolver/issuer mapping khác | Dùng trusted issuer registry |
| 403 thay cho 401 | Authentication/authorization handlers hoặc decoder behavior khác | So sánh failure path |
| Security context còn tồn tại ngoài dự kiến | Repository/session policy khác | Kiểm tra `ServerSecurityContextRepository` |
| Tests pass nhưng chữ ký chưa được verify | Dùng `mockJwt()` | Gửi signed Bearer token qua decoder thật |

## 25. Checklist parity trước khi thay traffic

### Token trust

- [ ] Canonical issuer giống bản Servlet.
- [ ] JWKS URI đúng và được tin cậy.
- [ ] Algorithm allowlist giống nhau.
- [ ] Signature verification hoạt động.
- [ ] `exp`, `nbf` và clock skew policy giống nhau.
- [ ] Audience/resource validation giống nhau.
- [ ] Token type/profile validation giống nhau.
- [ ] JWT và opaque token mode đúng contract.
- [ ] Introspection `active=false` bị từ chối.
- [ ] Multi-issuer trust allowlist giống nhau nếu có.

### HTTP authorization

- [ ] Public routes giống nhau.
- [ ] Private routes giống nhau.
- [ ] GET/POST/PUT/DELETE scope rules giống nhau.
- [ ] Role/authority prefix giống nhau.
- [ ] Unknown routes bị deny.
- [ ] Chain matchers và order được kiểm tra.
- [ ] 401/403 semantics giống nhau.
- [ ] `WWW-Authenticate` được giữ.
- [ ] CORS origins/methods/headers/exposed headers giống nhau.
- [ ] CSRF policy phản ánh cùng credential model.

### Principal và business policy

- [ ] Subject/issuer mapping giống nhau.
- [ ] JWT và opaque principal được xử lý đúng.
- [ ] Tenant context đến từ claims đã xác minh hoặc trusted store.
- [ ] Object ownership checks giống nhau.
- [ ] Method security được bật ở reactive stack.
- [ ] Không có `ThreadLocal` hoặc mutable current-user field.
- [ ] Không có blocking/nested subscribe trong reactive path.

### Test và vận hành

- [ ] Cùng token fixtures chạy qua cả hai stacks.
- [ ] Signed JWT test xác minh chữ ký thật.
- [ ] Wrong issuer/audience/type/algorithm đều bị từ chối.
- [ ] Opaque active/inactive và timeout được test.
- [ ] CSRF/CORS/preflight được test.
- [ ] Multi-chain routing được test.
- [ ] Service side effects khi bị từ chối được kiểm tra.
- [ ] Staging metrics và latency được so sánh.
- [ ] Có rollback plan.

## 26. Câu hỏi tự kiểm tra

**1.** API nào của Servlet thay bằng `ServerHttpSecurity` trong WebFlux?

> `HttpSecurity`.

**2.** `SecurityFilterChain` được thay bằng gì?

> `SecurityWebFilterChain`.

**3.** `JwtDecoder` được thay bằng gì?

> `ReactiveJwtDecoder`.

**4.** `OpaqueTokenIntrospector` được thay bằng gì?

> `ReactiveOpaqueTokenIntrospector`.

**5.** `authorizeHttpRequests` được thay bằng gì?

> `authorizeExchange`.

**6.** Vì sao không dùng `SecurityContextHolder` trong WebFlux?

> Vì WebFlux truyền security context bằng Reactor Context theo subscription, không dựa vào ThreadLocal như Servlet mặc định.

**7.** WebFlux stateless API dùng gì thay `SessionCreationPolicy.STATELESS`?

> Có thể dùng `NoOpServerSecurityContextRepository` cho security context của chain.

**8.** Có thể dùng cùng `JwtDecoder` Servlet cho WebFlux không?

> Không. WebFlux cần `ReactiveJwtDecoder`.

**9.** `mockJwt()` có kiểm tra chữ ký thật không?

> Không. Nó tạo mock authentication; muốn kiểm tra chữ ký cần gửi signed Bearer token qua decoder thật.

**10.** Opaque token trong WebFlux cần test helper nào cho authorization?

> `mockOpaqueToken()`, nhưng helper này không gọi introspection endpoint.

**11.** Muốn test introspection pipeline thật cần gì?

> Gửi Bearer header qua WebTestClient và cấu hình reactive introspector thật trỏ tới test AS hoặc HTTP stub.

**12.** Vì sao cùng scope string chưa đủ để bảo đảm parity?

> Vì issuer, audience, token type, converter và route matcher cũng ảnh hưởng quyết định.

**13.** Vì sao `permitAll()` không nhất thiết bỏ qua Bearer token malformed?

> Authentication WebFilter có thể xử lý credential được gửi trước bước authorization.

**14.** WebFlux method security cần annotation nào?

> `@EnableReactiveMethodSecurity`.

**15.** Vì sao service không được gọi `block()` để lấy principal?

> Nó tạo blocking boundary và có thể làm mất reactive execution semantics/context.

**16.** Khi custom decoder WebFlux, cần giữ những validators nào?

> Signature/algorithm policy, issuer, timestamp, audience và token profile theo contract.

**17.** Vì sao phải test CORS `WWW-Authenticate` exposure?

> Browser JavaScript chỉ đọc được response headers được CORS expose.

**18.** Điều gì chứng minh migration đã giữ parity?

> Cùng token fixtures và request scenarios tạo ra cùng authentication/authorization outcomes, response contract và business side effects trong hai stack.

## 27. Tài liệu tham khảo

- [Spring Security — Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/index.html): kiến trúc WebFlux Security và `SecurityWebFilterChain`.
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder`, issuer, JWKS và JWT authentication.
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): `ReactiveOpaqueTokenIntrospector` và opaque authentication.
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/index.html): `authorizeExchange` và reactive authorization.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity` và publisher-returning methods.
- [Spring Security — Reactive Test Support](https://docs.spring.io/spring-security/reference/reactive/test/index.html): kiểm thử WebFlux Security.
- [Spring Security — Testing OAuth 2.0 with WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()`, `mockOpaqueToken()` và test helpers.
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): truy cập SecurityContext trong Reactor Context.
- [Spring Security — ServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html): lưu/tải context trong reactive server.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): reactive web integration tests.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest` và test auto-configuration.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer transport, 401/403 và `WWW-Authenticate`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access-token profile, issuer/audience/type/signature validation.

**Kết luận:** Một bản WebFlux tương đương Servlet phải giữ cùng trust policy và quyết định truy cập, đồng thời chuyển sang reactive security APIs. Dùng `SecurityWebFilterChain`, `ReactiveJwtDecoder` hoặc `ReactiveOpaqueTokenIntrospector`, giữ issuer/audience/algorithm/type validation, chuyển matcher sang `authorizeExchange`, dùng `ServerSecurityContextRepository` cho session policy, và đọc principal bằng Reactor Context. Xác nhận parity bằng cùng token fixtures và request matrix chạy trên cả hai stack; so sánh status, headers, response data và business side effects trước khi chuyển traffic.
