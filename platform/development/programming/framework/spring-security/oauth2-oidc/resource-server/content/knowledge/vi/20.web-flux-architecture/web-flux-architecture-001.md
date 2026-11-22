# SecurityWebFilterChain và cấu hình qua ServerHttpSecurity

## 1. Vì sao WebFlux có một hệ thống Spring Security riêng?

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, một API có thể chạy trên Spring MVC hoặc Spring WebFlux. Cả hai đều có thể tiếp nhận HTTP Bearer access token, xác minh JWT hay opaque token và kiểm tra scopes; nhưng **security filter infrastructure** của chúng khác nhau.

| Servlet/Spring MVC | Reactive/Spring WebFlux |
|---|---|
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| Servlet `Filter` và `FilterChainProxy` | WebFlux `WebFilter` và `WebFilterChainProxy` |
| `SecurityContextHolder` dựa trên ThreadLocal | `ReactiveSecurityContextHolder` dựa trên Reactor Context |
| `JwtDecoder` | `ReactiveJwtDecoder` |
| `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| `MockMvc` | `WebTestClient` |

Chỉ đổi kiểu trả về của controller từ `OrderDto` sang `Mono<OrderDto>` **không có nghĩa** một cấu hình Servlet `SecurityFilterChain` sẽ tự trở thành security configuration cho WebFlux. Khi triển khai reactive API, cần dùng các abstraction phản ứng tương ứng.

Hai thành phần quan trọng nhất:

- **`SecurityWebFilterChain`:** mô tả các `WebFilter` bảo vệ một nhóm HTTP exchanges.
- **`ServerHttpSecurity`:** DSL builder để thiết lập authentication, authorization, OAuth 2.0 Resource Server, CSRF, CORS, exception handling và security headers.

Một bean `SecurityWebFilterChain` thường là kết quả của `ServerHttpSecurity.build()`. Khi có nhiều chains, Spring Security chọn chain đầu tiên match request theo thứ tự đã cấu hình.

### Mục tiêu

Sau bài học, có thể:

1. Tạo `SecurityWebFilterChain` cho WebFlux.
2. Dùng `authorizeExchange`, `pathMatchers` và `anyExchange` để mô tả policy.
3. Bật `oauth2ResourceServer(...jwt(...))` hoặc `opaqueToken(...)`.
4. Phân biệt lỗi authentication 401 và authorization 403.
5. Thiết kế nhiều chains bằng `securityMatcher` và `@Order`.
6. Hiểu CSRF/CORS, stateless Bearer API, Reactor Context và reactive principal.
7. Tích hợp reactive method security và kiểm thử bằng `WebTestClient`.

## 2. WebFlux security hoạt động trên WebFilter chain

### 2.1. `WebFilter` không phải Servlet `Filter`

Một WebFlux filter sử dụng:

~~~java
package org.springframework.web.server;

public interface WebFilter {
    Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    );
}
~~~

Đây là chữ ký giản lược để minh họa; các types được Spring Framework cung cấp. `ServerWebExchange` đại diện request/response trong WebFlux. `Mono<Void>` biểu diễn một tác vụ hoàn thành bất đồng bộ, không phải một giá trị trả ngay sau khi đã xử lý toàn bộ request.

Servlet code thường dùng `Filter#doFilter(ServletRequest, ServletResponse, FilterChain)`, còn WebFlux dùng reactive publishers. Vì thế các điểm mở rộng security cũng phải là reactive types.

### 2.2. Pipeline tổng quan

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Spring WebFlux WebFilter pipeline"]
    B --> C["Spring Security WebFilterChainProxy"]
    C --> D{"SecurityWebFilterChain nào match?"}
    D --> E["Authentication WebFilters"]
    E --> F{"JWT hoặc opaque token hợp lệ?"}
    F -->|Không| G["Authentication error, thường 401"]
    F -->|Có| H["Reactive Authentication trong Reactor Context"]
    H --> I["AuthorizationWebFilter"]
    I --> J{"Rule authorizeExchange cho phép?"}
    J -->|Không| K["Access denied, thường 403"]
    J -->|Có| L["WebFlux controller / handler"]
    L --> M["Mono hoặc Flux phản hồi"]
~~~

Sơ đồ mang tính khái quát, không liệt kê đầy đủ các WebFilters và thứ tự của mọi Spring Security version.

Một số thành phần thường gặp:

| Thành phần | Vai trò |
|---|---|
| `WebFilterChainProxy` | Chọn security chain phù hợp |
| `SecurityWebFilterChain` | Danh sách WebFilters của một security policy |
| `ServerHttpSecurity` | Builder tạo chain |
| `AuthenticationWebFilter` | Thực hiện bước authentication theo cơ chế đã cấu hình |
| `ServerBearerTokenAuthenticationConverter` | Đọc Bearer token từ request |
| `ReactiveAuthenticationManager` | Xác thực credential và tạo Authentication |
| `ReactiveJwtDecoder` | Giải mã/xác minh JWT theo validators |
| `ReactiveOpaqueTokenIntrospector` | Introspect opaque token |
| `AuthorizationWebFilter` | Kiểm tra authorization cho exchange |
| `ReactiveSecurityContextHolder` | Truy cập security context qua Reactor Context |

**Authentication** và **authorization** là hai công việc khác nhau. JWT hợp lệ không có nghĩa caller được đọc mọi đơn hàng; URL scope rules và quyền tenant/owner vẫn cần kiểm tra.

### 2.3. Reactor Context thay ThreadLocal

Servlet code thường truy cập:

~~~java
SecurityContextHolder.getContext().getAuthentication();
~~~

Trong WebFlux, pipeline có thể chuyển threads. ThreadLocal không tự truyền theo một reactive subscription. Spring Security WebFlux sử dụng Reactor Context:

~~~java
ReactiveSecurityContextHolder.getContext();
~~~

Phương thức này trả `Mono<SecurityContext>`. Không gọi `block()` trong request processing chỉ để lấy Authentication đồng bộ.

## 3. Khởi tạo một ứng dụng WebFlux Resource Server

### 3.1. Gradle dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Dùng Spring Boot plugin/BOM để quản lý các version tương thích, không tự trộn tùy tiện Spring Framework và Spring Security versions.

**Lưu ý khi thêm cả hai web starters:** nếu dự án có đồng thời `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường ưu tiên Servlet web application theo cơ chế suy luận web type. Không suy ra ứng dụng đang reactive chỉ vì dependency WebFlux hoặc một số `Mono` có trong source.

### 3.2. Imports đúng

~~~java
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
~~~

Không nhầm với:

~~~java
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
~~~

Nhóm thứ hai thuộc Servlet stack.

## 4. Cấu hình SecurityWebFilterChain tối thiểu

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .build();
    }
}
~~~

Đây là cấu hình minh họa **policy authorization**, chưa chọn cơ chế xác thực Bearer token.

- `@EnableWebFluxSecurity` kích hoạt WebFlux security support.
- `@Bean` cung cấp một security chain cho Spring context.
- `authorizeExchange(...)` quy định authorization theo ServerWebExchange.
- `pathMatchers(...)` chọn các paths cụ thể.
- `permitAll()` bỏ yêu cầu authorization cho các paths đó.
- `authenticated()` yêu cầu principal đã được xác thực.
- `build()` tạo `SecurityWebFilterChain`.

Spring Boot có thể tự cấu hình security mặc định trong một số tình huống; khi cần policy riêng, nên định nghĩa bean rõ ràng và kiểm thử các HTTP routes.

### 4.1. So sánh DSL WebFlux và Servlet

Servlet:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().authenticated()
);
~~~

WebFlux:

~~~java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public/**").permitAll()
    .anyExchange().authenticated()
);
~~~

Không dùng `authorizeHttpRequests` trực tiếp trên `ServerHttpSecurity`. Trong reactive stack, DSL được thiết kế cho `ServerWebExchange` và các reactive matchers/managers.

## 5. Cấu hình JWT Resource Server hoàn chỉnh

### 5.1. Issuer và audience

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences:
            - orders-api
~~~

Issuer/audience là ví dụ. Token hợp lệ cho Resource Server cần đúng chữ ký, issuer, thời hạn và audience của chính API. `audiences` là Boot property trên các phiên bản hỗ trợ; với custom decoder, cần giữ audience validator một cách tường minh.

**Không dùng OIDC ID Token như access token.** ID Token được phát hành cho OIDC client để phục vụ xác thực login; API cần OAuth access token có audience/profile đúng.

### 5.2. Bật JWT và kiểm soát scopes

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class OrdersApiSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/api/orders", "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST,
                    "/api/orders", "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Trong cấu hình thông thường, Spring Security đọc `scope` hoặc `scp` từ JWT và chuyển thành authorities có prefix `SCOPE_`. Ví dụ:

~~~json
{"scope": "orders.read orders.export"}
~~~

có thể trở thành:

~~~text
SCOPE_orders.read
SCOPE_orders.export
~~~

Rule `hasAuthority("SCOPE_orders.write")` không tự được thỏa khi token chỉ chứa `orders.read`.

### 5.3. Ý nghĩa của DSL

| DSL | Ý nghĩa |
|---|---|
| `authorizeExchange(...)` | Khai báo các quy tắc HTTP authorization |
| `pathMatchers(HttpMethod.GET, ...)` | Giới hạn rule theo method và path |
| `hasAuthority("SCOPE_orders.read")` | So khớp authority string chính xác |
| `authenticated()` | Yêu cầu Authentication hợp lệ |
| `oauth2ResourceServer(...)` | Bật Resource Server Bearer authentication |
| `jwt(Customizer.withDefaults())` | Dùng reactive JWT verification mặc định |
| `build()` | Tạo security WebFilter chain |

**`authenticated()` không tự giải mã Bearer JWT.** Cần kích hoạt authentication mechanism như `oauth2ResourceServer(...jwt(...))` để token được xác minh.

### 5.4. Các kết quả HTTP điển hình

Request không có token tới protected URL:

~~~http
GET /api/orders/42 HTTP/1.1
~~~

thường nhận **401** với Bearer challenge.

Token sai signature/hết hạn/sai issuer/audience: authentication thất bại, thường **401** với `invalid_token`.

Token hợp lệ nhưng không có `SCOPE_orders.read`: authorization từ chối, thường **403**. Quyền trên tài nguyên cụ thể có thể tiếp tục bị từ chối bởi tenant/owner policy ngay cả khi scope hợp lệ.

## 6. Quy tắc matcher: rule cụ thể phải đứng trước rule rộng

### 6.1. Cấu hình có nguy cơ làm public API

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").permitAll()
    .pathMatchers("/api/admin/**")
        .hasAuthority("SCOPE_admin")
    .anyExchange().authenticated()
)
~~~

Rule `"/api/**"` quá rộng đứng trước, nên matcher admin phía sau có thể không được sử dụng. Tên rule trông nghiêm ngặt trên source không cứu được thứ tự sai.

Đúng hơn:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers("/api/admin/**")
        .hasAuthority("SCOPE_admin")
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyExchange().authenticated()
)
~~~

### 6.2. `anyExchange().authenticated()` hay `denyAll()`?

Nếu dùng:

~~~java
.anyExchange().authenticated()
~~~

thì một endpoint mới chưa được gắn scope riêng vẫn có thể truy cập bởi **bất kỳ token đã xác thực**. Đây có thể là policy chủ đích, nhưng cần hiểu trade-off.

Nếu dùng:

~~~java
.anyExchange().denyAll()
~~~

thì mọi unmatched route bị từ chối theo nguyên tắc **default deny**. Khi thêm route mới, developer phải cập nhật policy một cách chủ động.

| Mục tiêu | Fallback thường phù hợp |
|---|---|
| Mọi API route đều cần token, một số route cần scope riêng | `authenticated()` |
| Chỉ mở những route được liệt kê rõ | `denyAll()` |
| Public API hoàn toàn, có hạn chế riêng | Cần policy chi tiết, không đặt broad `permitAll` vô tình |

Một fallback denyAll còn có thể gây 403 cho URL vốn không tồn tại, vì authorization diễn ra trước handler routing. Không nhầm 403 này với controller 404.

### 6.3. Chú ý HTTP method và path gốc

Rule:

~~~java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

không tự kiểm soát POST. Nếu POST phải cần write scope, thêm rule tường minh.

Path `/api/orders` có thể cần matcher riêng với `/api/orders/**` tùy pattern matching semantics. Bài dùng cả hai path trong ví dụ 5 để diễn đạt rõ endpoint gốc và endpoints con.

## 7. Nhiều SecurityWebFilterChain và thứ tự @Order

### 7.1. Tại sao có nhiều chain?

Một ứng dụng có thể có:

- `/api/**`: Bearer JWT/opaque token.
- `/actuator/health`: health check cho platform.
- `/admin/**`: quy tắc chặt hơn.
- `/web/**`: OIDC browser login/session.

Có thể tạo các `SecurityWebFilterChain` riêng, mỗi chain có một `securityMatcher`.

### 7.2. Mẫu cấu hình nhiều chains

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class MultiChainSecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain health(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                    "/actuator/health"
                )
            )
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().permitAll()
            )
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                    "/api/**"
                )
            )
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain fallback(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().denyAll()
            )
            .build();
    }
}
~~~

Đây là **một cấu hình thay thế** cho ví dụ single-chain, không đăng ký hai nhóm config trùng nhau trong một application mà không kiểm soát matcher/priority.

**Lưu ý:** health endpoint có thể chỉ `/actuator/health`, trong khi `/actuator/health/liveness` là route khác. Nếu cần cho public cả children, phải thêm matcher phù hợp và test riêng; không mở public toàn bộ `/actuator/**` chỉ để health chạy được. Một số actuator endpoints có dữ liệu nhạy cảm cần authentication riêng.

### 7.3. Hai tầng matching khác nhau

~~~text
SecurityWebFilterChain.securityMatcher(...)
    -> request có được đưa vào chain này không?

ServerHttpSecurity.authorizeExchange(...)
    -> bên trong chain được chọn, request cần quyền gì?
~~~

Security chain **đầu tiên match** được áp dụng theo thứ tự, không phải mọi chains đều chạy tiếp để tìm một rule permit. Nếu chain rộng `"/api/**"` với `permitAll` đứng trước chain `"/api/admin/**"`, chain admin có thể không bao giờ được chọn.

### 7.4. Fallback chain giúp tránh vùng bảo mật bị bỏ trống

Nếu không có chain nào match một đường dẫn, request có thể không nhận policy mong muốn. Một `fallback` với `anyExchange().denyAll()` cho ứng dụng áp dụng default-deny.

Mỗi route mới, CORS preflight, actuator, health, metrics, websocket handshake hoặc static resource cần được kiểm tra chain coverage trước production.

## 8. ReactiveJwtDecoder và custom JWT validation

### 8.1. Reactive decoder

WebFlux dùng:

~~~java
org.springframework.security.oauth2.jwt.ReactiveJwtDecoder
org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder
~~~

Không dùng Servlet `JwtDecoder` bean làm lựa chọn mặc định rồi gọi `block()`. Decoder reactive chịu trách nhiệm xử lý token trong Reactive authentication flow.

### 8.2. Issuer discovery và JWK Set URI

Cấu hình phổ biến:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

Nếu dùng issuer discovery, framework xác định thông tin issuer và JWKS theo metadata được AS công bố. Tùy phiên bản/cách khởi tạo, network discovery có thể xảy ra ở startup hoặc khi decode request đầu tiên.

Khi có JWKS URI tin cậy theo hợp đồng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          jwk-set-uri: https://id.example.test/realms/shop/protocol/openid-connect/certs
~~~

có thể giảm dependency lên metadata discovery, nhưng **không được bỏ kiểm tra issuer**. JWT được ký bởi cùng IdP nhưng có audience dành cho API khác cũng phải bị từ chối.

### 8.3. Reactive decoder bean có issuer và audience validators

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class ReactiveDecoderConfig {

    private static final String ISSUER =
        "https://id.example.test/realms/shop";

    private static final String JWKS_URI =
        "https://id.example.test/realms/shop/protocol/openid-connect/certs";

    private static final String AUDIENCE = "orders-api";

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(JWKS_URI)
                .build();

        OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token audience is not orders-api",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                standard,
                audience
            )
        );

        return decoder;
    }
}
~~~

**Quan trọng khi tự tạo decoder:**

- Spring Boot auto-config có thể nhường chỗ cho custom `ReactiveJwtDecoder` bean; properties như `audiences` không chắc được tự gắn vào decoder đó.
- `setJwtValidator(...)` đặt validators của decoder; không được thay chỉ bằng custom audience validator rồi làm mất issuer/timing checks.
- Kiểm tra JWT signature/`alg` allowlist, `iss`, `aud`, `exp`, `nbf` và các custom claims bắt buộc theo hợp đồng.
- Không dùng giá trị `jku`/`kid` chưa xác minh để tải key từ host bất kỳ.
- Tránh log bearer token thô.

## 9. Reactive authority converter và phạm vi quyền token

### 9.1. Scopes thành authorities

Với token:

~~~json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-42"
}
~~~

Spring Security mặc định thường tạo:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

`hasAuthority("SCOPE_orders.read")` khớp theo chuỗi. Claim `app_roles` hoặc `groups` không tự thành `ROLE_ADMIN`. Chỉ ánh xạ role qua converter có issuer/audience/schema/allowlist rõ.

### 9.2. ReactiveJwtAuthenticationConverterAdapter

Một cách dùng converter synchronous cho claims in-memory trong WebFlux:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;

@Configuration
public class ReactiveAuthoritiesConfig {

    @Bean
    ReactiveJwtAuthenticationConverterAdapter jwtConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        scopes.setAuthoritiesClaimName("scope");
        scopes.setAuthorityPrefix("SCOPE_");

        JwtAuthenticationConverter delegate =
            new JwtAuthenticationConverter();

        delegate.setJwtGrantedAuthoritiesConverter(scopes);

        return new ReactiveJwtAuthenticationConverterAdapter(delegate);
    }
}
~~~

Trong chain có thể inject `ReactiveJwtAuthenticationConverterAdapter jwtConverter`:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(jwtConverter)
    )
)
~~~

Adapter tiện cho ánh xạ nhanh không I/O. Nếu converter cần gọi DB/network reactive, hãy dùng reactive converter phù hợp hoặc authorization service riêng. **Không gọi `block()` trong JWT converter** để lấy roles từ DB.

### 9.3. Không biến local permission thành scope

Một token chỉ có `orders.read` không tự được `orders.approve` vì user có role approve trong DB. Nếu một endpoint phê duyệt yêu cầu **scope của token và local entitlement**, policy phải diễn đạt AND:

~~~text
ALLOW_APPROVE =
    JWT active and intended for API
    AND SCOPE_orders.approve
    AND current local entitlement permits approve
    AND order tenant/owner/ACL permits action
~~~

Không chỉ gộp OAuth scopes với database permissions thành một tập rồi dùng OR.

## 10. API stateless: CSRF, Basic/Form Login và SecurityContextRepository

### 10.1. Khi nào có thể tắt CSRF?

CSRF là vấn đề khi browser tự gửi **ambient credentials** như session cookie. Với một API chỉ chấp nhận **Bearer token ở Authorization header**, không dùng cookie authentication và không có browser login trong chain, có thể cân nhắc disable CSRF.

Nhưng **không** tắt CSRF bừa bãi trong app dùng cookie/session hoặc browser OIDC login. Cần áp dụng theo security chains và threat model.

### 10.2. Ví dụ Bearer-only, không duy trì WebSession SecurityContext

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

@Configuration
@EnableWebFluxSecurity
public class BearerOnlyApiConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Đây là **phương án thay thế** cho chain ở phần 5; không đăng ký nhiều chains match trùng khi chưa thiết kế `securityMatcher` và `@Order`.

`NoOpServerSecurityContextRepository` không lưu SecurityContext vào WebSession giữa các requests. Nó **không xóa authentication của request hiện tại**: Bearer authentication vẫn được đưa vào Reactor Context cho authorization.

### 10.3. Cookie-based Web UI phải giữ policy riêng

Một ứng dụng có:

~~~text
/api/** -> Bearer-only stateless -> JSON 401/403
/web/** -> OIDC login/session    -> redirects, CSRF bảo vệ browser flows
~~~

thường nên dùng security chains khác nhau. Đừng đặt global CSRF disable chỉ vì `/api/**` là Bearer-only.

## 11. CORS trong WebFlux

### 11.1. Vì sao frontend có thể gặp CORS 401?

SPA tại `https://app.example.test` gọi API `https://api.example.test` với header `Authorization`. Browser có thể gửi OPTIONS preflight trước request thực. Nếu preflight bị chặn vì không có JWT, frontend có thể chỉ nhận thông báo CORS error.

CORS phải được xử lý phù hợp trong reactive pipeline. CORS không làm token hợp lệ, và không thay thế OAuth 2.0 validation.

### 11.2. Reactive CorsWebFilter

~~~java
package com.example.orders.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class ReactiveCorsConfig {

    @Bean
    CorsWebFilter corsWebFilter() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(
            List.of("https://app.example.test")
        );
        cors.setAllowedMethods(
            List.of("GET", "POST", "PUT", "DELETE", "OPTIONS")
        );
        cors.setAllowedHeaders(
            List.of("Authorization", "Content-Type")
        );
        cors.setExposedHeaders(
            List.of("WWW-Authenticate", "X-Request-Id")
        );

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return new CorsWebFilter(source);
    }
}
~~~

Đây là **WebFlux** `CorsWebFilter` và reactive `UrlBasedCorsConfigurationSource`, không phải Servlet `CorsFilter`.

Nếu dùng `ServerHttpSecurity.cors(...)` hoặc cấu hình CORS WebFlux khác, cần có một chiến lược nhất quán, không vô ý xử lý duplicate CORS filters với policies khác nhau.

### 11.3. Expose Bearer challenge

Nếu frontend JavaScript cần đọc `WWW-Authenticate` trên cross-origin response:

~~~http
Access-Control-Expose-Headers: WWW-Authenticate
~~~

Khi dùng cookie credentials, không đặt wildcard origins thiếu kiểm soát. Với preflight, đảm bảo allowed origins/methods/headers được cấu hình cụ thể và xử lý trước Bearer authorization.

## 12. Reactive errors: authentication entry point và access denied handler

### 12.1. Extension points khác Servlet

Trong WebFlux:

~~~java
org.springframework.security.web.server.ServerAuthenticationEntryPoint
org.springframework.security.web.server.authorization.ServerAccessDeniedHandler
~~~

Các methods hoạt động trên `ServerWebExchange` và trả `Mono<Void>`. Chúng khác Servlet `AuthenticationEntryPoint` và `AccessDeniedHandler`.

Có thể nối qua:

~~~java
http.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint(myReactiveEntryPoint)
    .accessDeniedHandler(myReactiveDeniedHandler)
);
~~~

`myReactiveEntryPoint` và `myReactiveDeniedHandler` là reactive implementations do ứng dụng cung cấp. Khi chỉ cần Bearer errors chuẩn, ưu tiên default handlers của OAuth2 Resource Server thay vì tự làm header.

### 12.2. RFC 6750 và HTTP status

| Tình huống | HTTP thường gặp | Bearer error |
|---|---|---|
| Không gửi token tới protected endpoint | 401 | Challenge Bearer, thường không `error` |
| JWT invalid/expired | 401 | `invalid_token` |
| Bearer request malformed | 400 | `invalid_request` khi đúng tình huống |
| Token valid nhưng thiếu OAuth scope | 403 | `insufficient_scope` |
| Tenant/owner/ACL denied | 403 hoặc 404 theo policy | Không tự giả rằng thiếu scope |
| JWKS/introspection unavailable | Lỗi hạ tầng theo config | Không fail open hoặc tự tuyên bố token revoked |

Nếu thêm body JSON theo RFC 9457:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required or the token is invalid.",
  "code": "invalid_token"
}
~~~

thì actual HTTP status vẫn phải là 401, `Content-Type` là `application/problem+json` và `WWW-Authenticate` phải được giữ. **Không trả HTTP 200 kèm JSON status 401**.

### 12.3. WebFlux response không dùng Servlet sendError

Một reactive handler thiết lập `ServerHttpResponse`, status/headers và trả publisher ghi body. Không dùng `HttpServletResponse.sendError(...)` trong WebFlux. Không tự `subscribe()` rồi trả `Mono.empty()` vì có thể hoàn thành response trước khi body được ghi hoặc mất error/context propagation.

Nếu response đã committed, không thể chắc chắn thay status/headers. Khi muốn JSON thống nhất, test các đường Bearer filter, authorization WebFilter và handler exceptions ở Spring Security version thực tế.

## 13. Opaque token introspection trong WebFlux

### 13.1. Cấu hình opaque token

Nếu Authorization Server phát opaque token hoặc API cần online introspection:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

Không commit `client-secret` vào code và không đưa secret sang browser frontend. Resource Server cần client credential riêng để được phép introspect.

### 13.2. Bật opaque Resource Server

~~~java
@Bean
SecurityWebFilterChain opaqueSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public/**").permitAll()
            .pathMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(Customizer.withDefaults())
        )
        .build();
}
~~~

Đây là **phương án thay thế** cho JWT chain, không phải một bean cần thêm khi cùng request path đã có JWT chain khác.

### 13.3. ReactiveOpaqueTokenIntrospector

WebFlux sử dụng interface:

~~~java
org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector
~~~

Introspection có thể phản ánh `active:false` từ AS khi token bị thu hồi, nhưng cũng thêm một HTTP dependency. Các rủi ro:

- Network latency và tail-latency.
- Timeout/HTTP 5xx/rate limits của AS.
- Không có quyết định tin cậy mới khi introspection endpoint down.
- Cache result làm stale `active` và scopes.
- `active:true` không tự cho phép đọc mọi tenant/owner.

Không chuyển sang Servlet synchronous `OpaqueTokenIntrospector` rồi gọi `block()` trong reactive security pipeline.

### 13.4. Opaque principal

Opaque Resource Server thường tạo principal kiểu `OAuth2AuthenticatedPrincipal`, không phải `Jwt`. Nếu controller cần claims nhưng ứng dụng có cả opaque và JWT workflows, chọn principal abstraction theo security chain hoặc dùng một identity DTO nội bộ.

## 14. Principal và SecurityContext trong reactive controller

### 14.1. WebFlux controller nhận `@AuthenticationPrincipal Jwt`

~~~java
package com.example.orders.api;

import reactor.core.publisher.Mono;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/api/me")
    public Mono<MeResponse> me(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just(
            new MeResponse(
                jwt.getSubject(),
                jwt.getClaimAsString("tenant_id")
            )
        );
    }

    public record MeResponse(
        String subject,
        String tenantId
    ) {}
}
~~~

Ví dụ giả định JWT-only protected endpoint và contract của access token yêu cầu claims phù hợp. Nếu `tenant_id` quyết định phạm vi dữ liệu, phải validate đúng kiểu/giá trị ở JWT decoder hoặc policy, không tự mặc định tenant toàn cục khi thiếu claim.

### 14.2. Lấy Authentication từ Reactor Context

~~~java
package com.example.orders.service;

import reactor.core.publisher.Mono;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

public class CallerService {

    public Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }
}
~~~

Nếu không có context, pipeline có thể hoàn thành rỗng. Với endpoint `permitAll`, caller cần xác định chính sách guest/null rõ ràng; đừng để `Mono.empty()` vô tình dẫn tới một quyền mặc định.

### 14.3. Không dùng ThreadLocal cho reactive security

Một code pattern dễ sai:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
~~~

Trong WebFlux, thread xử lý các operators có thể thay đổi. Trừ khi có tích hợp context propagation đặc biệt được cấu hình/đánh giá đúng, không dựa vào ThreadLocal làm nguồn chân lý. Ưu tiên `ReactiveSecurityContextHolder` hoặc principal được Spring Security inject.

### 14.4. Không tự `subscribe()` để tách authorization và business side effect

Sai ý tưởng:

~~~java
public Mono<Void> approve(String id) {
    policy.canApprove(id).subscribe(allowed -> {
        if (allowed) {
            orders.approve(id).subscribe();
        }
    });

    return Mono.empty();
}
~~~

Đây là hai detached subscriptions. HTTP response có thể hoàn tất trước khi authorization/DB write chạy; security context, transaction và error propagation có thể bị mất.

Tốt hơn:

~~~java
public Mono<Void> approve(String id) {
    return policy.canApprove(id)
        .flatMap(allowed -> {
            if (!allowed) {
                return Mono.error(
                    new AccessDeniedException(
                        "Approval is not permitted"));
            }

            return orders.approve(id);
        });
}
~~~

`policy` và `orders` là reactive application services minh họa. Imports: `reactor.core.publisher.Mono` và `org.springframework.security.access.AccessDeniedException`.

**Đừng gọi `block()` trong WebFlux request path** chỉ để lấy authentication hay quyền DB đồng bộ.

## 15. Reactive method security và ranh giới nghiệp vụ

### 15.1. Bật annotation reactive

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {
}
~~~

Nó phù hợp với Reactor Context và các publishers của reactive application. Không chỉ bật Servlet `@EnableMethodSecurity` rồi coi method security reactive đã chạy.

### 15.2. Service trả về Mono

~~~java
package com.example.orders.service;

import reactor.core.publisher.Mono;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrdersQueryService {

    private final ReactiveOrderRepository orders;

    public OrdersQueryService(ReactiveOrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<OrderDto> load(String id) {
        return orders.findDtoById(id);
    }
}
~~~

`ReactiveOrderRepository` và `OrderDto` do ứng dụng định nghĩa. Ở reactive method security, nên dùng `Mono`/`Flux` returns theo hợp đồng framework/version để interceptor kết hợp policy vào publisher.

### 15.3. Quyền tenant/ACL vẫn cần ở service

Token có `SCOPE_orders.read` nhưng order thuộc tenant khác vẫn phải bị từ chối. Có thể ghép check với reactive repository:

~~~java
public Mono<OrderDto> loadForCaller(
        String orderId,
        String subject,
        String tenantId) {

    return access.canReadOrder(subject, tenantId, orderId)
        .flatMap(allowed -> {
            if (!allowed) {
                return Mono.error(
                    new AccessDeniedException(
                        "Order access denied"));
            }

            return orders.findByIdAndTenantId(orderId, tenantId)
                .switchIfEmpty(
                    Mono.error(
                        new ResponseStatusException(
                            HttpStatus.NOT_FOUND)));
        });
}
~~~

Đây là ví dụ nghiệp vụ; `access` và `orders` phải là services/repositories reactive thực. Scope ở URL/method security và quyền trên object/tenant là các điều kiện **cùng cần thỏa** nếu contract yêu cầu.

### 15.4. Self-invocation vẫn là vấn đề AOP

Dù code reactive, một method:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.approve')")
public Mono<Void> approve(String orderId) { ... }
~~~

có thể bị bypass nếu một method khác trong cùng target bean gọi `this.approve(orderId)` theo mô hình Spring AOP proxy. Tách method có policy riêng sang một bean khác rồi gọi qua dependency injection, hoặc bảo vệ public entry point phù hợp với toàn bộ workflow.

Không dựa vào việc annotation “có trong source” để kết luận mọi đường đi đều được bảo vệ.

## 16. Non-blocking phải được giữ xuyên suốt security flow

### 16.1. Những thao tác blocking cần tránh

- `Thread.sleep(...)` trong reactive operator.
- `RestTemplate` blocking HTTP gọi trực tiếp trên event loop.
- JDBC/JPA repository synchronous trong request handler.
- `Mono.block()`/`Flux.block()` trên WebFlux event-loop thread.
- File I/O blocking không được đưa ra scheduler phù hợp.

Một Resource Server reactive vẫn có thể nghẽn nếu business code chặn event loop.

### 16.2. Khi còn legacy blocking dependency

Giải pháp chuyển tiếp:

~~~java
public Mono<OrderDto> findLegacyOrder(String id) {
    return Mono.fromCallable(
            () -> jdbcRepository.findOrderDto(id))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Import `reactor.core.scheduler.Schedulers`. Bounded elastic giúp chuyển blocking work khỏi event loop, nhưng không biến JDBC thành reactive I/O và cũng không bảo đảm concurrency vô hạn. Cần kiểm soát timeout/throughput và load test.

Với native reactive stack, ưu tiên `WebClient`, reactive drivers/repositories phù hợp; không tự dùng `subscribe()` hoặc `block()` để nối security flow.

## 17. WebSocket, SSE và luồng kéo dài

WebFlux có thể phục vụ Server-Sent Events, streaming `Flux` và WebSocket handshake. Cần phân biệt:

- Authentication/authorization khi **thiết lập request/handshake**.
- Quyền trên **từng message/record/event** khi stream còn chạy.
- Khả năng token hết hạn hoặc bị revoke **sau khi request ban đầu đã qua security**.

`SecurityWebFilterChain` không mặc định xác minh lại Bearer token cho **mỗi phần tử Flux** của một response streaming dài. Với hệ thống yêu cầu revocation hoặc entitlement freshness trong long-lived streams, phải xây cơ chế kiểm tra lại theo policy.

Không xuất dữ liệu nhạy cảm trong stream trước khi ownership/tenant authorization đã thành công.

## 18. Kiểm thử WebFlux Security bằng WebTestClient

### 18.1. Khác biệt với Servlet MockMvc

WebFlux dùng:

~~~java
org.springframework.test.web.reactive.server.WebTestClient
~~~

Test Spring Boot có thể:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ApiSecurityTests {

    @Autowired
    WebTestClient client;
}
~~~

Imports/tên annotation test starter có thể thay đổi giữa Spring Boot major versions; ví dụ này theo phong cách Spring Boot 3.x.

### 18.2. Không token: 401

~~~java
@Test
void protectedApiRequiresBearerToken() {
    client.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isUnauthorized();
}
~~~

Khi test đầy đủ Bearer response, assert thêm `WWW-Authenticate` tương ứng.

### 18.3. Test authority với `mockJwt()`

Spring Security Test cung cấp reactive helper:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

import org.springframework.security.core.authority.SimpleGrantedAuthority;
~~~

Cho GET với `SCOPE_orders.read`:

~~~java
@Test
void readScopeAllowsGet() {
    client.mutateWith(
            mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )
        )
        .get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk();
}
~~~

Thiếu scope:

~~~java
@Test
void missingReadScopeIsForbidden() {
    client.mutateWith(
            mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")
            )
        )
        .get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

`mockJwt()` cần `WebTestClient` đã tích hợp Spring Security test support, ví dụ thông qua cấu hình `springSecurity()` cho application-context-bound client. Việc `@AutoConfigureWebTestClient` có tự nối integration phù hợp hay không cần kiểm tra Spring Boot/test setup version.

**Quan trọng:** `mockJwt()` tạo Authentication giả lập, không tự kiểm tra signature, issuer, audience, expiration hay JWKS. Để kiểm tra JWT verification, dùng test token thực được ký với test key/JWKS, hoặc stub `ReactiveJwtDecoder` trong integration context rồi xác minh Bearer filter behavior.

### 18.4. Ma trận tests

| Request | Principal/token | Kỳ vọng về security |
|---|---|---|
| GET `/api/orders/42` | Không token | 401 |
| GET `/api/orders/42` | JWT hợp lệ với `SCOPE_orders.read` | Vượt URL authz |
| GET `/api/orders/42` | Chỉ `SCOPE_profile` | 403 |
| POST `/api/orders` | Chỉ `SCOPE_orders.read` | 403 khi write rule đúng |
| POST `/api/orders` | `SCOPE_orders.write` | Vượt URL authz |
| GET `/api/public/info` | Không token | Permit qua security |
| GET public URL | Bearer sai | Có thể 401 do filter vẫn authenticate |
| GET URL chưa có rule | Token hợp lệ | Theo fallback authenticated/denyAll |
| GET health URL | Không token | Theo health chain |
| JWT sai signature/expired | Bearer thật | 401 qua decoder |
| JWT sai audience | Bearer thật | 401 nếu audience validator có cấu hình |
| API read đủ scope nhưng sai tenant | JWT hợp lệ | Service policy deny |
| OPTIONS preflight | Không Bearer token | Theo CORS policy, không ép authn |
| Browser đọc Bearer challenge | Cross-origin | Expose header đúng |

“Vượt URL authz” **không mặc nhiên bằng HTTP 200**. Controller có thể trả 404 vì order không tồn tại hoặc 500 do test fixture thiếu. Khi viết tests, phân biệt rõ kiểm tra security và nghiệp vụ.

### 18.5. Test nhiều chains

Với `@Order`, cần test các paths:

- `/actuator/health` chọn đúng health chain.
- `/api/orders/42` chọn API JWT chain.
- URL còn lại chọn fallback deny chain.
- Không có public chain rộng đứng trước API chain.
- 401/403 từ JWT chain không biến thành OIDC browser redirects.
- Không có route mới được phép chỉ vì fallback quá rộng.

## 19. Lỗi kiến trúc thường gặp

### Lỗi 1 — Dùng `HttpSecurity` trong WebFlux app

`HttpSecurity`/`SecurityFilterChain` dùng cho Servlet. Với WebFlux, dùng `ServerHttpSecurity`/`SecurityWebFilterChain`.

### Lỗi 2 — Không bật `oauth2ResourceServer(...)`

`anyExchange().authenticated()` là policy, không tự verify JWT Bearer token. Cần reactive authentication mechanism.

### Lỗi 3 — Dựa vào ThreadLocal `SecurityContextHolder`

Reactive publishers có thể chuyển threads. Dùng `ReactiveSecurityContextHolder` hoặc injected principal.

### Lỗi 4 — Rule `permitAll` rộng che rules cần scope

Matcher order có hiệu lực. Đặt rule cụ thể trước rule rộng.

### Lỗi 5 — Tưởng nhiều chains cộng dồn policies

Chỉ chain đầu tiên match được chọn. `@Order` và `securityMatcher` quyết định security boundary.

### Lỗi 6 — Không có fallback chain

Những URLs không match chain nào có thể không được bảo vệ theo ý định. Với default-deny, dùng fallback `anyExchange().denyAll()`.

### Lỗi 7 — Tắt CSRF cho cả browser login

Chỉ cân nhắc disable theo chain Bearer-only và threat model. Cookie-based flows vẫn cần bảo vệ CSRF phù hợp.

### Lỗi 8 — Dùng Servlet CORS classes

WebFlux cần reactive CORS support như `CorsWebFilter`. Đảm bảo preflight và expose `WWW-Authenticate` nếu SPA cần đọc challenge.

### Lỗi 9 — Gọi blocking code trên event loop

`block()`, synchronous JDBC/HTTP và `Thread.sleep` có thể gây latency và nghẽn. Dùng reactive composition, hoặc scheduler chuyển tiếp được quản lý.

### Lỗi 10 — Dùng `@EnableMethodSecurity` thay reactive method security

WebFlux reactive method security phù hợp dùng `@EnableReactiveMethodSecurity` và Reactor context-aware interception.

### Lỗi 11 — ID Token thay access token

Resource Server cần OAuth access token có audience/token profile đúng. OIDC ID Token không mặc nhiên dành cho API.

### Lỗi 12 — Scope đủ thì cho xem mọi tenant

Scope bảo vệ loại hành động; kiểm tra owner/ACL/tenant phải do service/repository thực hiện.

### Lỗi 13 — Test `mockJwt()` rồi kết luận decoder hoàn hảo

`mockJwt()` cho authorization tests, không chứng minh chữ ký/issuer/audience. Cần decoder/JWKS tests riêng.

### Lỗi 14 — Reactive handler trả HTTP 200 chứa JSON lỗi

Invalid JWT thường 401; valid token thiếu authority thường 403. JSON body không được thay ngữ nghĩa của HTTP response.

### Lỗi 15 — Logging Bearer token/secret

Không log `Authorization`, raw JWT, opaque token, introspection client secret. Dùng correlation ID, category lỗi và metrics đã redact.

## 20. Sơ đồ kiến trúc tổng hợp

~~~mermaid
flowchart TD
    A["Client Bearer request"] --> B["WebFlux WebFilterChainProxy"]
    B --> C{"SecurityWebFilterChain + @Order"}
    C --> D["API SecurityWebFilterChain"]
    C --> E["Health SecurityWebFilterChain"]
    C --> F["Fallback deny chain"]
    D --> G["Reactive authentication"]
    G --> H{"JWT hay opaque?"}
    H --> I["ReactiveJwtDecoder + validators"]
    H --> J["ReactiveOpaqueTokenIntrospector"]
    I --> K["Authentication trong Reactor Context"]
    J --> K
    K --> L["authorizeExchange path/method/scope"]
    L --> M{"Đủ quyền?"}
    M -->|Không| N["401/403 đúng ngữ nghĩa"]
    M -->|Có| O["WebFlux handler Mono/Flux"]
    O --> P["Reactive method security"]
    P --> Q["Entitlement + tenant/owner/ACL"]
    Q --> R["Reactive repository"]
    R --> S["HTTP response"]
~~~

JWT và opaque trong sơ đồ là **hai phương án xác thực theo cấu hình**, không phải yêu cầu bật cả hai với một token.

## 21. Tổng kết

**`SecurityWebFilterChain`** là chain bảo vệ request của WebFlux; **`ServerHttpSecurity`** là DSL cấu hình chain đó. Hai khái niệm tương tự Servlet `SecurityFilterChain`/`HttpSecurity` về trách nhiệm, nhưng không dùng thay thế trực tiếp.

Những nguyên tắc cốt lõi:

1. **Đúng reactive stack:** `@EnableWebFluxSecurity`, `ServerHttpSecurity`, `SecurityWebFilterChain`, reactive decoder/introspector.
2. **Rõ exchange authorization:** `authorizeExchange`, method/path matchers, scopes và fallback.
3. **Không nhầm chain selection với policy:** `securityMatcher` và `@Order` chọn chain; `authorizeExchange` định nghĩa quyền trong chain.
4. **Bật Resource Server thật:** `jwt(...)` hoặc `opaqueToken(...)`; `authenticated()` một mình không verify Bearer token.
5. **Giữ Reactor Context:** `ReactiveSecurityContextHolder` và `Mono`/`Flux` composition thay ThreadLocal, `block()` hay detached subscriptions.
6. **CSRF/CORS theo threat model:** Bearer-only có thể khác browser cookie/session; preflight cần xử lý đúng.
7. **Scope không thay thế nghiệp vụ:** owner/tenant/ACL và entitlement có thể cần kiểm tra đồng thời.
8. **Test đúng stack:** `WebTestClient`, `mockJwt()` cho authz, decoder/introspection tests cho authn.
9. **Giữ response semantics:** sai token thường 401; token hợp lệ thiếu scope thường 403; không trả HTTP 200 kèm JSON lỗi.

### Tài liệu tham khảo

- [Spring Security Reference — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security Reference — Resource Server JWT (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security Reference — Resource Server Opaque Token (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security Reference — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security Reference — WebFlux Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html)
- [Spring Security API — ServerHttpSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security API — SecurityWebFilterChain](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/SecurityWebFilterChain.html)
- [Spring Security API — ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Spring Framework Reference — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)

