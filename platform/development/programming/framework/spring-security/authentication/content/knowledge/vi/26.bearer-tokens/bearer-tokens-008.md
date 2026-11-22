# Thành phần xác thực JWT và opaque bearer token trong Spring Security WebFlux (reactive)

## 1. Vấn đề: cùng là Authorization: Bearer nhưng xác thực bằng cách nào?

Trong một **OAuth 2.0 Resource Server** xây trên **Spring WebFlux**, client gửi access token ở header:

```http
GET /api/messages HTTP/1.1
Host: api.example.org
Authorization: Bearer <access-token>
```

Resource Server phải xác định token có hợp lệ và dành cho API này không, sau đó tạo đối tượng `Authentication` chứa principal và `GrantedAuthority` cho quyết định phân quyền.

Có hai cách chính:

- **JWT (JSON Web Token)**: token là cấu trúc có thể giải mã; Resource Server tự xác minh chữ ký và các claims với khóa tin cậy, sau đó chuyển claims thành principal và authorities. Thành phần trung tâm là `ReactiveJwtDecoder`.
- **Opaque token**: Resource Server coi token là một chuỗi không cần biết cấu trúc bên trong; nó gọi **OAuth 2.0 Token Introspection Endpoint** do Authorization Server cung cấp, kiểm tra trạng thái `active` và lấy thuộc tính/quyền. Thành phần trung tâm là `ReactiveOpaqueTokenIntrospector`.

**Chú ý:** đây là **hai chiến lược xác thực**, không đơn thuần là hai loại chuỗi. Một access token có định dạng JWT **vẫn có thể được kiểm tra bằng introspection** khi hệ thống muốn có quyết định trạng thái tại Authorization Server (ví dụ thu hồi quyền/token gần thời gian thực). Cấu hình `opaqueToken()` trong Spring Security mô tả cách kiểm tra qua introspection, không nhất thiết khẳng định chuỗi token không có cấu trúc JWT.

### Câu hỏi chính khi thiết kế

1. Token thuộc loại nào và Authorization Server bảo đảm gì?
2. Resource Server cần kiểm tra chữ ký/claim cục bộ hay hỏi Authorization Server mỗi request?
3. Principal nào được tạo sau xác thực, scope nào biến thành `GrantedAuthority`?
4. API yêu cầu những quyền nào, xử lý 401/403 ra sao?
5. Nền tảng là **WebFlux/reactive** hay **Servlet**? Các API tương ứng khác nhau.

## 2. Luồng xử lý reactive từ HTTP request đến SecurityContext

```text
HTTP request + Authorization: Bearer ...
               |
               v
SecurityWebFilterChain (ServerHttpSecurity)
               |
               v
AuthenticationWebFilter
  -> ServerBearerTokenAuthenticationConverter
  -> BearerTokenAuthenticationToken (chưa xác thực)
               |
               v
ReactiveAuthenticationManager.authenticate(authentication)
        |                               |
        v                               v
 JWT path                         Introspection path
 JwtReactiveAuthenticationManager  OpaqueTokenReactiveAuthenticationManager
        |                               |
 ReactiveJwtDecoder                  ReactiveOpaqueTokenIntrospector
  parse + verify signature            call Authorization Server introspection
  validate claims                     validate active/response
        |                               |
  Jwt + converter                  OAuth2AuthenticatedPrincipal + converter
        |                               |
 JwtAuthenticationToken              BearerTokenAuthentication
        +---------------+---------------+
                        |
                        v
   Reactive SecurityContext (Reactor Context) trong request
                        |
                        v
   AuthorizationWebFilter / @PreAuthorize / handler
                        |
                        v
   200 nếu đủ quyền; 401 nếu không được xác thực;
   403 nếu đã xác thực nhưng thiếu quyền
```

Tài liệu tham chiếu ở đây là **Spring Security 6.x**, ví dụ chạy trên **Spring Boot 3.x, Java 17+**. Tên các lớp và cấu hình WebFlux ở dưới không được nhầm với các lớp Servlet như `BearerTokenAuthenticationFilter`, `JwtAuthenticationProvider`, `OpaqueTokenAuthenticationProvider`, `HttpSecurity` và `SecurityContextHolder` dựa trên ThreadLocal.

### Các lớp chính và trách nhiệm

| Thành phần reactive | Trách nhiệm |
| --- | --- |
| `SecurityWebFilterChain` | Chuỗi security filters cho `ServerWebExchange` |
| `ServerHttpSecurity.oauth2ResourceServer(...)` | DSL bật bearer resource server: chọn `jwt(...)` hoặc `opaqueToken(...)` |
| `ServerBearerTokenAuthenticationConverter` | Trích bearer token từ request (mặc định header `Authorization`) |
| `BearerTokenAuthenticationToken` | Mang chuỗi token chưa được xác thực, làm input của manager |
| `ReactiveAuthenticationManager` | Hợp đồng `Mono<Authentication> authenticate(Authentication)` |
| `JwtReactiveAuthenticationManager` | Gọi decoder và chuyển `Jwt` thành `Authentication` |
| `ReactiveJwtDecoder` | Giải mã, xác minh chữ ký và áp dụng validators cho JWT |
| `OpaqueTokenReactiveAuthenticationManager` | Gọi introspector và tạo `Authentication` từ dữ liệu introspection |
| `ReactiveOpaqueTokenIntrospector` | `Mono<OAuth2AuthenticatedPrincipal> introspect(String token)` |
| `ReactiveJwtAuthenticationConverterAdapter` | Chuyển bộ chuyển đổi JWT đồng bộ thành hợp đồng converter reactive |
| `ReactiveSecurityContextHolder` | Đọc `SecurityContext` từ Reactor Context trong luồng xử lý hiện tại |

**Hợp đồng `ReactiveAuthenticationManager`:** một `Mono` phát ra `Authentication` khi xác thực được; có thể trả `Mono.empty()` nếu manager không có quyết định cho input; trả `Mono.error(...)` nếu xác thực thất bại. Gọi method rồi bỏ qua publisher sẽ không thực hiện đầy đủ side effect mà publisher đại diện.

**Đừng tự gọi `block()` trong WebFlux request handler/filter** để chờ decoder/introspector; điều đó có thể chặn event loop. Framework đã nối các `Mono` vào pipeline.

## 3. JWT: thành phần và chuỗi xác minh

### 3.1. ReactiveJwtDecoder

API quan trọng:

```java
public interface ReactiveJwtDecoder {
    Mono<Jwt> decode(String token) throws JwtException;
}
```

Đoạn trên chỉ thể hiện chữ ký interface; không phải file Java độc lập. `ReactiveJwtDecoder` thường được Spring Boot tự cấu hình khi có `spring.security.oauth2.resourceserver.jwt.issuer-uri`. Implementation phổ biến là `NimbusReactiveJwtDecoder`.

Khi nhận một JWT hợp lệ, resource server có thể:

1. Parse cấu trúc JWS/JWT, xác định thuật toán trong allowlist tin cậy và khóa ký tương ứng từ JWK Set hoặc public key đã cấu hình.
2. **Xác minh chữ ký** (không được chỉ Base64 decode payload rồi tin claims).
3. Kiểm tra thời gian `exp`, `nbf` và `iss` theo validators đã cấu hình. Với `issuer-uri` thông dụng, Spring Security có validator issuer.
4. **Kiểm tra audience (`aud`), token type và ràng buộc ứng dụng nếu nghiệp vụ yêu cầu**. Không mặc định coi xác thực chữ ký và issuer là đủ cho mọi API.
5. Chuyển token `Jwt` đã qua decoder thành `JwtAuthenticationToken` qua converter, lấy `sub` làm tên principal mặc định nếu có và ánh xạ scope thành quyền `SCOPE_...`.

JWT là bearer token: ai giữ được token hợp lệ có thể sử dụng nó trong phạm vi token cho phép. HTTPS, giữ bí mật token, TTL, revocation strategy và chống phát lại là trách nhiệm của thiết kế tổng thể.

### 3.2. JwtReactiveAuthenticationManager

Manager loại JWT nhận một `BearerTokenAuthenticationToken`, chuyển chuỗi token đến `ReactiveJwtDecoder`, rồi áp dụng converter để tạo `JwtAuthenticationToken`. Hai lớp này không thể thay thế nhau: decoder đảm nhận xác minh/đọc claims, manager hoàn tất **Spring Authentication**.

```text
BearerTokenAuthenticationToken("eyJ...") 
  -> JwtReactiveAuthenticationManager
  -> ReactiveJwtDecoder.decode(token)
  -> Jwt(header + validated claims)
  -> JWT AuthenticationConverter
  -> JwtAuthenticationToken
        principal = Jwt
        authorities = [SCOPE_message:read, ...]
```

Với claim ví dụ:

```json
{
  "iss": "https://idp.example.org/issuer",
  "sub": "user-42",
  "aud": ["message-api"],
  "scope": "message:read message:write",
  "exp": 1999999999
}
```

Nếu token thực sự được phát hành và kiểm chứng hợp lệ, các scope thông dụng được ánh xạ thành `SCOPE_message:read` và `SCOPE_message:write`. JSON trên chỉ là minh họa claims; **không phải một JWT đã ký** và không thể dùng làm bearer token thật.

### 3.3. JWK rotation và decoder configuration

Khi Resource Server biết `issuer-uri`, Spring Security có thể dùng thông tin discovery của issuer để xác định JWK Set, sau đó lấy và cập nhật khóa công khai khi cần. Không tải một public key cố định rồi giả định Authorization Server sẽ không bao giờ rotate.

Nếu sử dụng **chỉ `jwk-set-uri`** mà không có issuer validator tương ứng, cần tự kiểm tra liệu `iss` được xác minh hay chưa. Một cấu hình kết hợp issuer và JWK Set URI có thể dùng để giữ issuer check đồng thời cấu hình điểm lấy khóa tường minh.

Với nhiều issuer/tenant, không lấy giá trị `iss` do client khai rồi tin mọi issuer tùy ý. Resolver/decoder phải giới hạn tập issuer được phép trước khi thực hiện discovery và xử lý token.

## 4. Opaque token: thành phần và introspection

### 4.1. ReactiveOpaqueTokenIntrospector

Đây là interface chịu trách nhiệm hỏi Authorization Server về token:

```java
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

Đoạn này là chữ ký rút gọn để hiểu API. Spring Security 6.x có `SpringReactiveOpaqueTokenIntrospector` để kết nối endpoint, sử dụng client credentials được cấu hình và diễn giải kết quả.

Một request introspection thường gửi access token tới endpoint an toàn của Authorization Server. Phản hồi ví dụ:

```json
{
  "active": true,
  "sub": "user-42",
  "client_id": "frontend",
  "scope": "message:read message:write",
  "exp": 1999999999
}
```

Thông tin `active: true` là quyết định của Authorization Server theo chuẩn introspection. Nếu token không hợp lệ, hết hạn, bị thu hồi hoặc không được phép tra cứu, server có thể trả `active: false` hoặc lỗi tương ứng; resource server **không được tiếp tục coi token là hợp lệ**.

### 4.2. OpaqueTokenReactiveAuthenticationManager

Manager lấy input `BearerTokenAuthenticationToken`, gọi `ReactiveOpaqueTokenIntrospector.introspect(...)` và tạo `BearerTokenAuthentication` chứa `OAuth2AuthenticatedPrincipal` cùng `GrantedAuthority`.

```text
BearerTokenAuthenticationToken("token-value")
  -> OpaqueTokenReactiveAuthenticationManager
  -> ReactiveOpaqueTokenIntrospector.introspect(token)
  -> OAuth2AuthenticatedPrincipal(attributes, authorities)
  -> BearerTokenAuthentication
        principal = OAuth2AuthenticatedPrincipal
        authorities = [SCOPE_message:read, ...]
```

Trong cách cấu hình tiêu chuẩn, Spring Security đọc các scope từ kết quả introspection và gắn prefix `SCOPE_`. Nếu Authorization Server trả claim riêng cho role/permission, cần tùy biến introspector hoặc converter theo hợp đồng tin cậy với server đó.

**Sự khác biệt vận hành:** introspection thường cần request mạng tới Authorization Server cho mỗi lần xác thực, nên độ trễ, timeout, rate limit và trạng thái endpoint ảnh hưởng API. Caching có thể giảm chi phí nhưng tạo khoảng trễ phát hiện token bị revoke. Cần quyết định TTL/cache theo rủi ro, không mặc định rằng opaque là “luôn cập nhật ngay lập tức” nếu có cache hoặc Authorization Server xử lý thu hồi trễ.

### 4.3. Opaque token không có nghĩa là không kiểm tra audience

Dù introspection trả `active=true`, Resource Server vẫn cần xác định **token có dành cho tài nguyên này không** theo contract `aud`, `client_id`, `resource` hoặc policy của Authorization Server. Một token dành cho API khác không nên được dùng chỉ vì nó active. Trách nhiệm audience có thể được thực hiện bởi Authorization Server theo client/introspection policy và/hoặc rule kiểm tra nội bộ; phải kiểm chứng rõ.

## 5. Dự án Spring Boot WebFlux dùng JWT

Tạo một ứng dụng Spring Boot 3.x, Java 17+, chọn **Spring Reactive Web** và **OAuth2 Resource Server**. Với Gradle, dependencies cần có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Starter Resource Server bao gồm các thành phần phù hợp cho JWT/Jose. Nếu tự khai báo dependencies ở mức Spring Security module thay vì starter, JWT cần cả `spring-security-oauth2-resource-server` **và** `spring-security-oauth2-jose`.

Tạo file **`src/main/java/demo/JwtApiApplication.java`**:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class JwtApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(JwtApiApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping").permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/messages")
                            .hasAuthority("SCOPE_message:read")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @GetMapping("/public/ping")
    Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/messages")
    Mono<String> readMessages(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just("message for " + jwt.getSubject());
    }
}
```

Tạo **`src/main/resources/application.yml`**:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/issuer
```

**Các bước chạy:** thay issuer bằng issuer OIDC/OAuth2 có thật, có metadata/JWKS và token được ký phù hợp. Chạy `./gradlew bootRun` (Windows: `gradlew.bat bootRun`) trong project Boot. Lệnh:

```bash
curl -s http://localhost:8080/public/ping
```

Trả đúng body:

```text
pong
```

Một token access JWT **thật**, được phát hành cho API và có scope `message:read`, có thể kiểm tra bằng:

```bash
curl -i -H "Authorization: Bearer <VALID_ACCESS_TOKEN>" \
  http://localhost:8080/api/messages
```

`<VALID_ACCESS_TOKEN>` là placeholder cần thay, không phải token mẫu chạy được. Nếu đã qua validation và được cấp quyền, response có dạng `message for user-42` khi `sub=user-42`; nếu token thiếu/không hợp lệ sẽ không có quyền gọi route bảo vệ.

**Mục tiêu ví dụ:** dùng chính DSL `.oauth2ResourceServer(...jwt...)` để framework tự cấu hình bearer filter/manager, dùng `Jwt` đã được xác thực làm principal trong handler, và hạn chế authorization theo scope. Không tự giải mã payload bằng Base64 trong controller.

## 6. Chuyển sang opaque introspection (cùng API, thay đường xác thực)

Để làm **một project opaque resource server riêng**, giữ dependencies và endpoint `/public/ping` như trước, rồi thay JWT config bằng đoạn sau trong `apiSecurity`:

```java
@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/public/ping").permitAll()
                    .pathMatchers(HttpMethod.GET, "/api/messages")
                        .hasAuthority("SCOPE_message:read")
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .opaqueToken(Customizer.withDefaults()))
            .build();
}
```

Đổi endpoint cần principal vì loại principal thành công khác JWT:

```java
@GetMapping("/api/messages")
Mono<String> readMessages(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    return Mono.just("message for " + principal.getName());
}
```

Import bổ sung `org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal`. Đây là hai **đoạn thay thế** cho method cũ, không giữ đồng thời hai `@Bean apiSecurity` và hai `@GetMapping` trùng nhau trong cùng class.

Đổi **`application.yml`** sang introspection:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.org/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Phải cấp biến môi trường `INTROSPECTION_CLIENT_ID`, `INTROSPECTION_CLIENT_SECRET`, triển khai một Authorization Server hỗ trợ introspection, cấu hình HTTPS và quyền truy cập endpoint. **Không hard-code secret trong repo hoặc log.**

Khi resource server introspect token và thấy `active=true` với scope `message:read`, route `/api/messages` sẽ được phép. Token inactive hoặc introspection thất bại sẽ không được chấp nhận. Trong route này `Authentication` thành công là `BearerTokenAuthentication`; `@AuthenticationPrincipal` được inject là `OAuth2AuthenticatedPrincipal` từ introspection.

### Tự khai báo introspector khi cần

Nếu không muốn dùng property auto-configuration, Spring Security 6.5 hỗ trợ bean:

```java
@Bean
ReactiveOpaqueTokenIntrospector opaqueTokenIntrospector() {
    return SpringReactiveOpaqueTokenIntrospector
            .withIntrospectionUri("https://idp.example.org/oauth2/introspect")
            .clientId(introspectionClientId)
            .clientSecret(introspectionClientSecret)
            .build();
}
```

Đây là **mảnh cấu hình**; `introspectionClientId`/`introspectionClientSecret` phải được inject từ cấu hình an toàn, không phải biến Java tự xuất hiện. Import:

```java
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
```

Dùng một nguồn cấu hình introspector phù hợp; nếu đồng thời đặt custom `introspector()` trong DSL, bean mặc định do Boot tạo có thể không còn là thành phần được dùng.

## 7. Test chính xác hai ReactiveAuthenticationManager mà không cần IdP

Đây là **unit test cho contract chuyển đổi**. Nó dùng decoder/introspector giả lập nên **không chứng minh xác thực chữ ký JWT hoặc introspection mạng**. Mục đích là kiểm tra các manager nhận input bearer token, phát `Mono<Authentication>`, trả đúng kiểu Authentication/quyền, và từ chối dữ liệu không hợp lệ.

Với project Boot có dependencies ở mục 5, tạo file **`src/test/java/demo/ReactiveManagerTest.java`**:

```java
package demo;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.authentication.OpaqueTokenReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveManagerTest {

    private static boolean hasScope(
            Iterable<? extends GrantedAuthority> authorities, String scope) {
        for (GrantedAuthority authority : authorities) {
            if (authority.getAuthority().equals("SCOPE_" + scope)) {
                return true;
            }
        }
        return false;
    }

    @Test
    void jwtManagerValidatesViaDecoderThenCreatesJwtAuthentication() {
        ReactiveJwtDecoder fakeDecoder = token -> {
            if (!"sample-jwt".equals(token)) {
                return Mono.error(new BadJwtException("Rejected demo JWT"));
            }
            // Jwt này là fixture; không có chữ ký mật mã thật.
            Jwt jwt = Jwt.withTokenValue(token)
                    .header("alg", "RS256")
                    .claim("sub", "alice")
                    .claim("scope", "message:read")
                    .build();
            return Mono.just(jwt);
        };

        var manager = new JwtReactiveAuthenticationManager(fakeDecoder);

        StepVerifier.create(manager.authenticate(
                        new BearerTokenAuthenticationToken("sample-jwt")))
                .assertNext(authentication -> {
                    assertInstanceOf(JwtAuthenticationToken.class, authentication);
                    assertEquals("alice", authentication.getName());
                    assertTrue(hasScope(authentication.getAuthorities(), "message:read"));
                })
                .verifyComplete();

        StepVerifier.create(manager.authenticate(
                        new BearerTokenAuthenticationToken("wrong-jwt")))
                .expectError()
                .verify();
    }

    @Test
    void opaqueManagerIntrospectsThenCreatesBearerAuthentication() {
        ReactiveOpaqueTokenIntrospector fakeIntrospector = token -> {
            if (!"sample-opaque".equals(token)) {
                return Mono.error(new BadOpaqueTokenException("Inactive token"));
            }
            return Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
                    "bob",
                    Map.of(
                            "sub", "bob",
                            "scope", List.of("message:read")),
                    List.of(new SimpleGrantedAuthority("SCOPE_message:read"))));
        };

        var manager = new OpaqueTokenReactiveAuthenticationManager(
                fakeIntrospector);

        StepVerifier.create(manager.authenticate(
                        new BearerTokenAuthenticationToken("sample-opaque")))
                .assertNext(authentication -> {
                    assertInstanceOf(BearerTokenAuthentication.class, authentication);
                    assertEquals("bob", authentication.getName());
                    assertTrue(hasScope(authentication.getAuthorities(), "message:read"));
                })
                .verifyComplete();

        StepVerifier.create(manager.authenticate(
                        new BearerTokenAuthenticationToken("wrong-opaque")))
                .expectError()
                .verify();
    }
}
```

Chạy `./gradlew test --tests demo.ReactiveManagerTest` (Windows: `gradlew.bat test --tests demo.ReactiveManagerTest`). Kỳ vọng **hai tests PASS** khi sử dụng Spring Security 6.x/Boot 3.x tương thích. `StepVerifier` subscribe/đợi publisher hoàn thành và kiểm tra giá trị hoặc lỗi; không dùng `block()` trong WebFlux handler.

**Hạn chế có chủ đích:** fixture JWT giả sử bước xác minh chữ ký được thay bằng decoder giả, và fixture introspection tự cấp attributes. Do đó những token mẫu `sample-jwt`/`sample-opaque` **không được gửi tới hệ thống thật** và hai unit tests không thay thế integration test với JWK/introspection endpoint. Một test end-to-end phải chứng minh cả URL, issuer, audience, signature, active state, quyền và response HTTP.

## 8. Tùy biến chuyển claims/attributes thành GrantedAuthority

### 8.1. JWT authority converter

Spring Security 6.x thường đọc các claim scope như `scope` hoặc `scp` và tạo quyền `SCOPE_message:read`. Nếu provider dùng claim khác, chẳng hạn `permissions`, có thể chỉ định converter rõ ràng.

Mảnh cấu hình (đặt trong class `@Configuration`, thay phần `jwt(Customizer.withDefaults())` bằng `jwt(jwt -> jwt.jwtAuthenticationConverter(...))`):

```java
Converter<Jwt, Mono<AbstractAuthenticationToken>> jwtAuthoritiesConverter() {
    var claimsToAuthorities = new JwtGrantedAuthoritiesConverter();
    claimsToAuthorities.setAuthoritiesClaimName("permissions");
    claimsToAuthorities.setAuthorityPrefix("");

    var authenticationConverter = new JwtAuthenticationConverter();
    authenticationConverter.setJwtGrantedAuthoritiesConverter(
            claimsToAuthorities);

    return new ReactiveJwtAuthenticationConverterAdapter(authenticationConverter);
}

// Trong DSL của SecurityWebFilterChain:
// .oauth2ResourceServer(oauth2 -> oauth2
//     .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtAuthoritiesConverter())))
```

Các imports cần thêm:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;
import reactor.core.publisher.Mono;
```

Ở ví dụ này, nếu claim có dạng:

```json
{ "permissions": ["REPORT_READ", "REPORT_WRITE"] }
```

thì authorities có thể là `REPORT_READ` và `REPORT_WRITE` (**không** có `SCOPE_`). Khi đó authorization phải dùng `hasAuthority("REPORT_READ")`, không dùng `hasRole("REPORT_READ")` hoặc `SCOPE_REPORT_READ`. Đây là sự thay đổi chính sách, phải kiểm tra tin cậy issuer/audience và khả năng token bị cấp quá rộng trước khi áp dụng.

`ReactiveJwtAuthenticationConverterAdapter` thích hợp khi bộ converter bên trong **không có I/O blocking**. Nếu muốn truy vấn DB/quyền bên ngoài, thiết kế converter reactive thực sự; đừng gọi JPA/JDBC blocking trực tiếp trên event loop.

### 8.2. Opaque token authority customization

Với introspection, `ReactiveOpaqueTokenIntrospector` trả `OAuth2AuthenticatedPrincipal` có `getAttributes()` và `getAuthorities()`. Có thể bọc introspector để sửa authorities sau **khi delegate đã xác thực trạng thái token**:

```java
ReactiveOpaqueTokenIntrospector withApplicationRole(
        ReactiveOpaqueTokenIntrospector delegate) {

    return token -> delegate.introspect(token).map(principal -> {
        // Policy demo: chỉ giữ authorities mà delegate đã xác minh.
        var authorities = List.copyOf(principal.getAuthorities());
        return new DefaultOAuth2AuthenticatedPrincipal(
                principal.getName(),
                principal.getAttributes(),
                authorities);
    });
}
```

Imports cho mảnh trên:

```java
import java.util.List;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
```

Đoạn này chỉ cho thấy **vị trí cần tùy biến**; nó chưa thêm quyền mới. Muốn bổ sung role nội bộ, thực hiện mapping từ thuộc tính **đã xác minh** tới nguồn quyền/allowlist tin cậy, xử lý tenant và lỗi theo hướng từ chối. Không tin một chuỗi `groups` tùy ý đến từ token hoặc từ client để cấp quyền admin.

Ở các phiên bản có `ReactiveOpaqueTokenAuthenticationConverter`, đó cũng là extension point để tạo `Authentication` từ introspection result. Chỉ sử dụng khi thật sự muốn đổi kiểu principal/token; cấu hình introspector thường đủ cho việc nạp claims/authorities.

## 9. Token thất bại, 401 và 403

Ba tình huống có ý nghĩa khác nhau:

| Trường hợp | Kỳ vọng thông thường |
| --- | --- |
| Không gửi bearer token tới endpoint bảo vệ | 401 Unauthorized và thử thách Bearer (tùy cấu hình exception handling) |
| Gửi token sai, hết hạn, sai chữ ký/issuer/audience hoặc introspection inactive | 401; không tạo authenticated principal |
| Token xác thực được nhưng thiếu `SCOPE_message:read` | 403 Forbidden; authentication hợp lệ nhưng không đủ quyền |
| Không có token, truy cập endpoint `permitAll()` | Thường được xử lý không yêu cầu token |
| Gửi một bearer token **sai** tới endpoint `permitAll()` | Filter vẫn có thể cố xác thực token được gửi; không mặc định bypass token sai vì đường dẫn public |

Spring Security Resource Server dùng chuẩn Bearer error response và có thể gửi header `WWW-Authenticate: Bearer ...` theo lỗi. Không hard-code body lỗi nếu chưa cấu hình response handler của ứng dụng.

**Phân biệt lỗi mạng introspection với token bị từ chối:** nếu AS không truy cập được hoặc timeout, không được mặc định “cho qua” request. Cần monitoring và chính sách retry/circuit-breaker có giới hạn; khi không xác minh được token thì fail closed. Một lỗi hệ thống bên ngoài có thể dẫn tới HTTP khác 401 tùy handler/cấu hình; tránh khẳng định mọi lỗi introspection đều trả đúng 401.

## 10. Stateless, SecurityContext và Reactor Context

Một API chỉ dùng `Authorization: Bearer` thường mong muốn **mỗi request tự chứng minh danh tính**, không cần duy trì browser login session.

- `ReactiveSecurityContextHolder` giữ context theo **Reactor Context** trong pipeline của request, tránh ThreadLocal `SecurityContextHolder` kiểu Servlet.
- `ServerSecurityContextRepository` là abstraction nạp/lưu context giữa requests; chiến lược stateless có thể dùng `NoOpServerSecurityContextRepository.getInstance()`.
- Nếu hệ thống có các luồng đăng nhập khác dùng `WebSession`, hoặc request cache/CSRF/stateful feature khác, việc thêm JWT resource server **không tự đảm bảo toàn bộ ứng dụng stateless**.
- Một request JWT/opaque thành công thường tạo authentication cho chính request đó; request sau phải cung cấp token mới/chưa hết hạn. Đừng thay bearer token bằng cookie session tự tạo mà không có thiết kế bảo mật rõ ràng.
- Bên trong handler/filter reactive, đọc context bằng `ReactiveSecurityContextHolder.getContext()` hoặc nhận principal qua argument do Spring Security cung cấp.

Ví dụ method reactive đọc tên và authority:

```java
// Mảnh method trong class @RestController, cần Reactor Context do filter cấp.
@GetMapping("/api/current-user")
Mono<String> currentUser() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .map(auth -> auth.getName() + ":" + auth.getAuthorities().size());
}
```

Import thêm `org.springframework.security.core.context.ReactiveSecurityContextHolder`. Đây là code minh họa trong Spring WebFlux app có security chain phù hợp, không phải chương trình Java độc lập.

## 11. So sánh JWT và introspection trong vận hành

| Tiêu chí | JWT xác minh local | Introspection / opaque strategy |
| --- | --- | --- |
| Thành phần kiểm tra | `ReactiveJwtDecoder` | `ReactiveOpaqueTokenIntrospector` |
| Manager | `JwtReactiveAuthenticationManager` | `OpaqueTokenReactiveAuthenticationManager` |
| Tạo Authentication | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| Principal thông dụng | `Jwt` | `OAuth2AuthenticatedPrincipal` |
| Dữ liệu quyền | Claims trong JWT đã xác minh, converter | Introspection attributes/authorities, converter |
| Cần gọi Authorization Server ở mọi lần xác thực? | Thường không, trừ lúc discovery/JWK refresh hoặc logic riêng | Thường có; cache là lựa chọn riêng |
| Phản ứng khi revoke | Theo TTL/denylist/revalidation đặc biệt | Có thể nhận trạng thái mới khi introspect tiếp theo; phụ thuộc AS và cache |
| Điểm yếu vận hành | Sai audience/trust, JWK rotation, token TTL quá dài | Network latency, endpoint downtime, credentials/timeout/rate limit |
| Tính phù hợp | API phân tán, throughput cao, offline verification | Muốn kiểm soát token status tập trung, token tự thân không cần tiết lộ claims |

**Quy tắc chọn lựa:** xem yêu cầu thu hồi, độ trễ, thông tin nhạy cảm, khả năng mở rộng, trust model và mức độ kiểm soát Authorization Server. Không chọn JWT chỉ vì “hiện đại”, cũng không mặc định opaque là “an toàn hơn” ở mọi bối cảnh.

## 12. Các lỗi phổ biến khi triển khai

**(1) Nhầm Servlet với WebFlux.** Copy `HttpSecurity`, `BearerTokenAuthenticationFilter`, `JwtAuthenticationProvider` hoặc `OpaqueTokenAuthenticationProvider` sang app reactive. Dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và các *ReactiveAuthenticationManager* tương ứng.

**(2) Đọc JWT bằng Base64 rồi dùng claims chưa xác minh.** Decoder phải xác minh JWS signature/alg/key và validators. JWT đã decode chưa đồng nghĩa JWT đã authenticated.

**(3) Cấu hình chỉ `jwk-set-uri` và quên issuer/audience.** Bảo đảm validate đúng issuer, `aud` và chính sách token type theo API; chữ ký hợp lệ từ một issuer có nhiều tài nguyên chưa đủ chứng minh token dành cho API này.

**(4) Đưa nhầm ID Token vào API làm Bearer access token.** OIDC ID Token phục vụ client/RP xác thực người dùng; Resource Server thông thường cần **access token** dành đúng audience.

**(5) Quên tiền tố `SCOPE_`.** Scope `message:read` mặc định được convert thành `SCOPE_message:read`. `hasRole("message:read")` thường kiểm tra `ROLE_message:read` nên không khớp.

**(6) Mặc định opaque introspection loại bỏ mọi rủi ro revocation.** Token status phụ thuộc Authorization Server, cache, timeout và tần suất kiểm tra. Cần kiểm thử trường hợp revoke.

**(7) Tự viết converter gọi `block()` trong event loop.** Reactive pipeline phải giữ `Mono`/`Flux`, dùng `flatMap` và non-blocking HTTP; nếu bắt buộc gọi thư viện blocking, cần cách ly scheduler thích hợp và đo lường.

**(8) Gọi `ReactiveJwtDecoder.decode(token)` nhưng không subscribe/nối publisher.** `Mono` lazy; việc trả publisher không được consume thì validation không diễn ra như kỳ vọng.

**(9) Dùng `SecurityContextHolder.getContext()` ThreadLocal trong handler reactive.** Dữ liệu bảo mật có thể không theo ThreadLocal qua các operator. Dùng `ReactiveSecurityContextHolder`.

**(10) Đưa bearer token vào URL query và log nguyên token.** Header `Authorization` là đường truyền mặc định; token trong URL dễ rò qua lịch sử browser, proxy và log. Che giá trị nhạy cảm trong log/metrics/traces.

**(11) Để client quyết định redirect/introspection URI tùy ý.** Endpoint introspection, issuer/JWK URL phải được quản trị/allowlist. Không đưa dữ liệu của bên không tin cậy vào URL request server-side gây SSRF.

**(12) Cấu hình cả `jwt()` và `opaqueToken()` trong một chain rồi tưởng framework tự chọn theo hình dạng chuỗi.** Chọn rõ một chiến lược mỗi chain, hoặc thiết kế `ReactiveAuthenticationManagerResolver<ServerWebExchange>` với policy xác định khi thật sự hỗ trợ nhiều issuer/token type. Không phân loại token chỉ bằng “có hai dấu chấm” rồi bypass validator.

**(13) Chỉ thử status 200, bỏ qua negative tests.** Cần test missing token, malformed token, sai `alg`, issuer/audience, expired, not-before, introspection inactive, AS downtime, thiếu scope và cross-tenant.

**(14) Sử dụng refresh token từ client làm Authorization bearer.** Refresh token phục vụ token endpoint, không phải resource server request. Không lưu nó trong app log hay forward cho downstream API.

**(15) Quên phân biệt identity và permission.** `sub` cho biết chủ thể token; `scope`/`scp` chỉ các quyền được cấp cho token trong một bối cảnh. Endpoint nghiệp vụ có thể cần thêm kiểm tra account/tenant/ownership của tài nguyên.

## 13. Kịch bản kiểm thử tích hợp gợi ý

| Test | JWT | Opaque |
| --- | --- | --- |
| Token hợp lệ có `message:read` | 200; `JwtAuthenticationToken` | 200; `BearerTokenAuthentication` |
| Token hợp lệ nhưng chỉ có `message:write` | 403 | 403 |
| Không có token trên route protected | 401 | 401 |
| Token hết hạn hoặc bị AS vô hiệu hóa | Decoder từ chối theo `exp`/policy | Introspection `active=false`, từ chối |
| Token ký bởi issuer/keys lạ | Từ chối signature/issuer | AS không công nhận token |
| Token đúng issuer nhưng `aud` sai | Cần validator aud, từ chối | Cần introspection/policy đảm bảo audience, từ chối |
| JWK được rotate | Decoder cần lấy đúng key mới theo chính sách | Không phụ thuộc JWK cục bộ nếu chỉ introspect |
| AS downtime | JWT local có thể tiếp tục nếu khóa/metadata đã sẵn có và policy cho phép | Introspection không xác minh được => fail closed |
| Token bị revoke trong khi còn `exp` | Cần kế hoạch TTL/revocation bổ sung | Lần introspection tiếp theo có thể trả inactive |
| Missing/duplicate Authorization headers | Bảo đảm converter xử lý đúng theo RFC | Tương tự |
| Request WebFlux chạy qua nhiều Reactor operators | `ReactiveSecurityContextHolder` giữ đúng authentication | Tương tự |

Khi dùng `WebTestClient`, có thể kiểm thử status và route với Spring Security test hỗ trợ mock authentication. Tuy nhiên **mock JWT/opaque** chỉ kiểm tra đường authorization và controller; bài test integration thật phải gửi token được phát hành và được kiểm tra bởi decoder/introspector thật hoặc một test IdP phù hợp.

## 14. Checklist triển khai

1. Xác định format/token validation strategy; chọn **JWT decode** hoặc **opaque introspection** theo hợp đồng với Authorization Server.
2. Sử dụng `spring-boot-starter-webflux` và `spring-boot-starter-oauth2-resource-server`; cấu hình `SecurityWebFilterChain` bằng `ServerHttpSecurity`.
3. Với JWT: xác thực issuer, signature, allowed alg, `exp`/`nbf`, audience, type/tenant theo yêu cầu; bảo đảm JWK rotation.
4. Với introspection: giữ client secret an toàn, HTTPS, timeout, monitoring, cache/revocation policy và kiểm tra `active`/resource context.
5. Chuẩn hóa `GrantedAuthority` và quy tắc `hasAuthority`/`hasRole`; không tự cấp role admin từ claim không được quản trị.
6. Đảm bảo API authorization bao gồm cả permission và ràng buộc ownership/tenant nếu nghiệp vụ yêu cầu.
7. Không log bearer token; dùng HTTPS, kiểm soát CORS theo client và tránh truyền token qua query string.
8. Giữ pipeline reactive, không dùng ThreadLocal hoặc blocking I/O trong event loop.
9. Chạy unit test manager/converter và integration tests có thật cho positive/negative cases và sự cố IdP.
10. Theo dõi số lượng 401/403, độ trễ introspection, JWK fetch failures và token validator failures mà không tiết lộ secret.

### Tài liệu chính thức

- Spring Security 6.5 — OAuth2 WebFlux Resource Server: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security 6.5 — Reactive JWT Resource Server: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.5 — Reactive Opaque Token: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html
- Spring Security 6.5 — Reactive Bearer Tokens: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/bearer-tokens.html
- `ReactiveAuthenticationManager` API: https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authentication/ReactiveAuthenticationManager.html
- `JwtReactiveAuthenticationManager` API: https://docs.spring.io/spring-security/site/docs/6.5.0-M1/api/org/springframework/security/oauth2/server/resource/authentication/JwtReactiveAuthenticationManager.html
- `OpaqueTokenReactiveAuthenticationManager` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html

**Điểm cần nhớ:** cả JWT và opaque bearer token cùng đi qua đường `BearerTokenAuthenticationToken -> ReactiveAuthenticationManager -> Authentication -> Reactive SecurityContext` trong WebFlux. JWT dùng `ReactiveJwtDecoder` và thường tạo `JwtAuthenticationToken`; introspection dùng `ReactiveOpaqueTokenIntrospector` và thường tạo `BearerTokenAuthentication`. Hợp đồng token, ranh giới tin cậy và quyền ứng dụng mới quyết định cấu hình an toàn.
