# Xử lý token thiếu, sai định dạng, hết hạn hoặc không đủ scope — Spring Security Reactive JWT Resource Server

## 1. Bối cảnh và mục tiêu

Một ứng dụng **Spring WebFlux** đóng vai trò **OAuth2 Resource Server** không phát access token và không đăng nhập người dùng thay Authorization Server. Nó nhận yêu cầu HTTP, lấy Bearer token, xác minh token và quyết định caller có được thao tác với tài nguyên hay không. Ví dụ:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

Có ít nhất bốn lỗi phải phân biệt:

1. **Token thiếu:** request vào một endpoint protected nhưng không có Bearer authentication.
2. **Sai định dạng hoặc không hợp lệ:** header `Authorization` không theo quy tắc Bearer, hoặc một chuỗi được nhận là token nhưng JWT parser/signature validator bác bỏ.
3. **Token hết hạn/chưa hiệu lực:** `exp` đã qua, `nbf` chưa tới, hoặc token không đạt những claim validators khác như `iss` và `aud`.
4. **Token hợp lệ nhưng không đủ scope:** đã được xác thực thành công nhưng không có `GrantedAuthority` tương ứng với endpoint.

Chúng thường tương ứng với **401**, **400/401**, **401** và **403**, nhưng cần hiểu **lỗi xảy ra ở tầng nào** thay vì đoán status chỉ từ một câu “invalid JWT”.

Sau bài này, bạn sẽ:

- Hiểu luồng Reactive `ServerBearerTokenAuthenticationConverter` → `JwtReactiveAuthenticationManager` → `ReactiveJwtDecoder` → `JwtAuthenticationToken` → authorization.
- Phân biệt `BearerTokenServerAuthenticationEntryPoint` và `BearerTokenServerAccessDeniedHandler` theo **RFC 6750**.
- Thiết lập kiểm tra chữ ký, trusted JWK Set, `iss`, `aud`, `exp`, `nbf` và scope mapping.
- Xây một ví dụ **Java 17+ / Spring Boot 3.x / Spring Security 6.x** có GET/POST yêu cầu scope khác nhau.
- Test 401/403 và `WWW-Authenticate` bằng `WebTestClient`, phân biệt `mockJwt()` với decoder validation thật.
- Chẩn đoán clock skew, key rotation, API audience, bearer request syntax, CORS/CSRF và các lỗi hạ tầng.

> **Phạm vi:** Reactive stack dùng `ServerHttpSecurity` và `SecurityWebFilterChain`. Không copy code Servlet `HttpSecurity` hoặc `BearerTokenAuthenticationFilter` của MVC vào ứng dụng WebFlux. OAuth2 Client xin token, Authorization Server phát token, còn Resource Server **tiêu thụ và xác minh** Bearer token.

## 2. Hai cửa kiểm tra: authentication trước, authorization sau

**Authentication:** token tồn tại không, có đúng Bearer format không, JWT có chữ ký hợp lệ, token đã được phát hành từ issuer đáng tin và còn hiệu lực chứ? Nếu thất bại, không được cấp `Authentication` đã xác thực.

**Authorization:** `Authentication` hợp lệ có authority/scope đúng cho action không? Resource có thuộc principal hoặc tenant này không? Nếu thiếu quyền, từ chối dù JWT thật, chưa hết hạn và có chữ ký đúng.

Chính sách API mẫu:

~~~text
GET  /public/ping   → public
GET  /api/profile   → yêu cầu authenticated JWT
GET  /api/orders    → yêu cầu SCOPE_orders.read
POST /api/orders    → yêu cầu SCOPE_orders.write
~~~

Ví dụ:

- Request GET `/api/orders` không có header Authorization → **401**.
- `Authorization: Bearer x.y.z` nhưng signature/JWT sai → **401 invalid_token**.
- JWT đúng signature nhưng `exp` đã quá hạn → **401 invalid_token**.
- JWT đúng, còn hạn, scope `profile` nhưng thiếu `orders.read` → **403**, thường có `insufficient_scope`.
- JWT đúng scope nhưng user Alice truy cập đơn của Bob → authorization nghiệp vụ vẫn phải từ chối **403 hoặc 404 theo policy**, vì scope không thay thế object ownership.

Không coi 401 là “người dùng chưa đủ quyền”, cũng không dùng 403 để thông báo “mật khẩu/token không đúng” trong mọi trường hợp.

## 3. Bảng phân loại lỗi thường gặp

| Dấu hiệu | Thành phần phát hiện | Status thường gặp | Ý nghĩa |
| --- | --- | --- | --- |
| Không có `Authorization` | Authorization yêu cầu authentication | **401** | Chưa có thông tin xác thực |
| Có `Authorization: Basic ...` nhưng API chỉ bật Bearer | Converter không nhận scheme | Thường **401** | Tương tự chưa có Bearer credential |
| `Authorization: Bearer` không có token | Bearer request parser | **400 hoặc 401** | Tùy parser xác định `invalid_request` hay missing token |
| Cung cấp token trùng/lẫn nhiều cơ chế | Bearer converter | Thường **400 invalid_request** | HTTP request sai hợp đồng |
| Chuỗi được coi là token nhưng JWT format/base64url lỗi | JWT decoder | Thường **401 invalid_token** | Không thể xác minh JWT |
| Chữ ký không đúng / thuật toán không tin cậy | JWT decoder | **401 invalid_token** | Không tin JWT payload |
| `exp` đã qua hoặc `nbf` ở tương lai | JWT timestamp validator | **401 invalid_token** | Không thuộc khoảng thời gian hợp lệ |
| `iss` không khớp trusted issuer | Claim validator | **401 invalid_token** | Phát hành bởi issuer không được phép |
| `aud` không chứa API audience | Claim validator bổ sung | **401 invalid_token** | Token không dành cho Resource Server này |
| JWT hợp lệ nhưng thiếu `orders.read` | Authorization policy | **403**, thường `insufficient_scope` | Caller không có quyền yêu cầu |
| JWT có scope nhưng thiếu quyền với resource cụ thể | Domain authorization | **403/404** | Object-/tenant-level access denied |
| JWKS provider/metadata/network bị lỗi | Hạ tầng decode/discovery | Có thể **5xx** hoặc error riêng | Không được xem như token hỏng một cách mặc định |
| Request body JSON bị lỗi sau authentication | WebFlux decoder/validation | **400** | Lỗi input, không phải Bearer `invalid_request` |

**Không khẳng định mọi malformed header đều 401 hay mọi 403 đều `insufficient_scope`.** Spring Security 6.x phân biệt parse error (`invalid_request`) với token validation (`invalid_token`); gateway, custom handler và kiểu security chain có thể ảnh hưởng response. Kiểm tra status **và** `WWW-Authenticate` của request thật.

## 4. Reactive authentication pipeline

~~~mermaid
flowchart TD
    A[HTTP Request] --> B[SecurityWebFilterChain]
    B --> C{Có Bearer token hợp cú pháp?}
    C -->|Không có| D[Authorization kiểm tra yêu cầu]
    D -->|Public| Z[Cho phép request]
    D -->|Protected| E[Authentication Entry Point 401]
    C -->|Bearer request malformed| F[Bearer invalid_request]
    C -->|Có token| G[JwtReactiveAuthenticationManager]
    G --> H[ReactiveJwtDecoder: parse, JWS verify, claims validate]
    H -->|JWT invalid / expired| I[Bearer invalid_token 401]
    H -->|JWT hợp lệ| J[JwtAuthenticationToken + GrantedAuthority]
    J --> K{Endpoint authority đủ?}
    K -->|Không| L[Bearer access denied 403]
    K -->|Có| M[Domain ownership/tenant rules]
    M -->|Hợp lệ| N[Controller response]
    M -->|Bị từ chối| O[403 hoặc 404 theo policy]
~~~

Trong WebFlux, lớp trích Bearer thường là `ServerBearerTokenAuthenticationConverter`, tương tác với `AuthenticationWebFilter` và `JwtReactiveAuthenticationManager`. Decoder `NimbusReactiveJwtDecoder` sử dụng key trusted để xác minh chữ ký, kiểm tra JWT claims, sau đó `JwtAuthenticationToken` được đưa vào Reactor/Spring Security authentication context.

**Điều đặc biệt:** `@RestControllerAdvice` không phải nơi mặc định xử lý mọi 401/403. Spring Security filters thường từ chối request **trước khi** controller được gọi. Nếu muốn thay response body, phải dùng đúng `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler`, không chỉ exception handler của controller.

### Public endpoint có thể vẫn bị lỗi khi gửi Bearer token sai

`permitAll()` cho phép request **không cần authentication** tại endpoint; nó không hứa bỏ qua mọi attempt authentication do client đã chủ động gửi Bearer header. Nếu một client tự gắn token hỏng cho `/public/ping`, authentication filter có thể từ chối trước khi authorization xét `permitAll`. Vì vậy không cấu hình frontend `WebClient`/HTTP client tự đính kèm một bearer token vào **mọi URL** vô điều kiện.

## 5. Bearer challenge và các mã RFC 6750

### 5.1. Không có token: 401 + Bearer challenge

Khi request thiếu authentication và endpoint protected:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Nếu có realm:

~~~http
WWW-Authenticate: Bearer realm="orders-api"
~~~

Theo RFC 6750, khi request **không hề có thông tin xác thực**, server nên tránh gửi error code/description không cần thiết. `BearerTokenServerAuthenticationEntryPoint` giúp tạo challenge đúng giao thức.

### 5.2. Token không hợp lệ hoặc expired: `invalid_token`

Ví dụ minh họa:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Đó có thể là token không parse được, sai signature, expired, revoked theo mô hình kiểm chứng hoặc không đạt claim validation. Client nên xin token mới theo grant/refresh flow phù hợp **nếu vấn đề có thể khắc phục bằng token mới**.

Không trả raw JWT, private key/JWK, stack trace, full decoder message hoặc `error_description` chứa dữ liệu bí mật cho client.

### 5.3. Bearer request sai cấu trúc: `invalid_request`

Ví dụ một request chứa nhiều cách truyền token không hợp lệ theo policy:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request"
~~~

`invalid_request` nghĩa là **cách trình bày request/token** có lỗi. Nó khác token đã được trích ra nhưng chữ ký/hạn dùng không hợp lệ. Với `Authorization: Bearer` thiếu token, status cụ thể còn tùy converter/handler; không tự assert tất cả header malformed đều là 400.

### 5.4. Token hợp lệ nhưng không đủ scope: `insufficient_scope`

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

`BearerTokenServerAccessDeniedHandler` cố xác định request có OAuth2 authentication hợp lệ hay không; nếu xác định được, nó có thể dùng `insufficient_scope`. Không phải mọi lỗi 403 bắt buộc có chuỗi này: CSRF, object policy hoặc custom access-denied handler có thể tạo response khác.

**Chốt lại:** đối với API Bearer, **status + `WWW-Authenticate` là hợp đồng**, không chỉ JSON body.

## 6. Token decode được không đồng nghĩa đã xác thực

Một JWT thường có dạng:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Attacker có thể tạo payload `{"sub":"admin","scope":"orders.write"}` rồi Base64URL encode. Chỉ đọc header/payload không chứng minh token do IdP đáng tin phát hành.

Resource Server JWT cần kiểm chứng:

1. **JWS signature** bằng trusted JWK/public key.
2. **Trusted algorithms**: không chấp nhận `alg=none` hoặc thuật toán lấy trực tiếp từ token mà không đối chiếu allowlist.
3. **Issuer `iss`** đúng IdP/tenant được phép.
4. **Audience `aud`** chứa audience của API; không dùng token phát cho service khác.
5. **Expiry `exp`, not-before `nbf`** với đồng hồ và clock skew hợp lý.
6. **Token type/claims** cần cho Resource Server; không nhầm OIDC ID token với API access token.
7. **Scope/authorities** được chuyển đổi đúng rồi kiểm tra quyền cho action/resource.

Spring Security 6.x có `ReactiveJwtDecoder` và `JwtValidators` để thực hiện các lớp kiểm tra này. Khi tự cấu hình decoder, **giữ validator mặc định** chứ không thay bằng một audience validator duy nhất.

### Clock skew ảnh hưởng kiểm thử expired

Spring Security Resource Server có tolerance độ lệch thời gian, thường mặc định quanh **60 giây**. Token quá hạn vài giây có thể vẫn được chấp nhận trong tolerance. Để test hết hạn, tạo JWT quá hạn **vài phút** hoặc test trực tiếp `JwtTimestampValidator(Duration.ZERO)` khi muốn chắc chắn ranh giới `exp`.

Không nới clock skew thành nhiều giờ chỉ để làm bài test xanh; cần đồng bộ đồng hồ/NTP và cấu hình token lifetime đúng.

### JWKS, `kid` và key rotation

Authorization Server có thể xoay khóa. Resource Server lấy public keys từ JWKS trusted, đối chiếu `kid`/algorithm theo cơ chế decoder và cache/reload. Nếu IdP thay key đột ngột hoặc JWKS hỏng, nhiều request có thể thất bại; vận hành cần tách **token invalid** với **key fetch outage**. Không tắt verify signature để vượt sự cố mạng.

## 7. Scope trong JWT và `SCOPE_` authorities

Ví dụ JWT claims:

~~~json
{
  "sub": "alice",
  "iss": "https://idp.example.test/tenant",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write"
}
~~~

Một IdP khác có thể dùng `scp`:

~~~json
{
  "sub": "alice",
  "scp": ["orders.read", "orders.write"]
}
~~~

Mặc định `JwtGrantedAuthoritiesConverter` chuyển OAuth2 scopes thành authorities với prefix `SCOPE_`:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Trong WebFlux security config:

~~~java
.pathMatchers(HttpMethod.GET, "/api/orders")
    .hasAuthority("SCOPE_orders.read")
.pathMatchers(HttpMethod.POST, "/api/orders")
    .hasAuthority("SCOPE_orders.write")
~~~

`hasAuthority("orders.read")` **không giống** `hasAuthority("SCOPE_orders.read")`. `hasRole("ADMIN")` thường đòi `ROLE_ADMIN`, không tự map từ `scope=admin`. Nếu IdP dùng `permissions` hoặc `roles` riêng, phải cấu hình JWT-to-authentication converter có kiểm soát, không tin trường role do client gửi trong query.

**Scope chỉ là điều kiện cần.** Nếu JWT có `orders.read`, user Alice vẫn không tự động đọc được orders của Bob; cần object-level authorization/tenant boundary. 403 do thiếu scope khác 403/404 do resource ownership.

## 8. Ứng dụng Java 17+ minh họa đầy đủ

Mô hình: API thuần Bearer trong `Authorization`, **không có form login, cookie session authentication hoặc HTTP Basic**. GET/POST dùng scopes khác nhau:

- `GET /public/ping` — public.
- `GET /api/profile` — cần authenticated JWT.
- `GET /api/orders` — `SCOPE_orders.read`.
- `POST /api/orders` — `SCOPE_orders.write`.

Config dùng domain IdP giả có chủ đích. App và test mock có thể chạy; để xác thực JWT thật phải cấu hình issuer/JWKS thật hoặc một test IdP. **Không có API nào nên chấp nhận JWT chưa ký chỉ để demo.**

### 8.1. Dependencies trong `build.gradle`

Trong dự án Spring Boot 3.x đã thiết lập Gradle plugin, repositories, Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Starter Resource Server cung cấp phần cần thiết cho OAuth2 Resource Server/JWT/Jose thông qua dependency management của Spring Boot. Không thêm `spring-boot-starter-web` chỉ để có REST controller, vì đây là **WebFlux Reactive**.

### 8.2. `src/main/resources/application.yml`

~~~yaml
server:
  port: 8080

demo:
  jwt:
    issuer: https://idp.example.test/tenant
    jwk-set-uri: https://idp.example.test/tenant/jwks.json
    audience: orders-api
~~~

Ba giá trị phải thay bằng thông số thực khi triển khai: issuer trusted, URL JWKS của IdP và audience API. Không cho client chỉ định JWKS URL qua request. Ví dụ dùng custom `demo.jwt` properties vì ta cần minh họa audience validator.

Spring Boot còn có cấu hình Resource Server cơ bản:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/tenant
          jwk-set-uri: https://idp.example.test/tenant/jwks.json
~~~

Đoạn thứ hai là **một phương án thay thế**, không thêm đồng thời khi demo đã tự khai báo `ReactiveJwtDecoder` rồi mong hai cấu hình cộng dồn. Khi dùng Boot properties, thêm audience validation theo khả năng của Boot version hoặc decoder customization tương thích.

### 8.3. `src/main/java/demo/jwterrors/JwtErrorsApplication.java`

~~~java
package demo.jwterrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JwtErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(JwtErrorsApplication.class, args);
    }
}
~~~

### 8.4. `src/main/java/demo/jwterrors/SecurityConfig.java`

~~~java
package demo.jwterrors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context
    .NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .csrf(csrf -> csrf.disable())
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .authorizeExchange(ex -> ex
                .pathMatchers("/public/ping").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Vì sao `csrf.disable()` chỉ xuất hiện ở đây?** Đây là demo được giới hạn vào **stateless API chỉ xác thực bằng Bearer token do client chủ động gửi trong header**. Không dùng cookie/browser-managed credentials hay form login. Trong sản phẩm có browser session, HTTP Basic tự gửi hoặc nhiều authentication mechanisms, **đừng sao chép dòng tắt CSRF**; phải đánh giá threat model, giữ CSRF cho unsafe methods cần bảo vệ hoặc tách security chains.

`NoOpServerSecurityContextRepository` không lưu authentication vào session cho request sau. Client phải gửi Bearer token cho **mỗi** request protected. `httpBasic` và `formLogin` bị tắt để API không redirect tới HTML login khi thiếu Bearer.

`oauth2ResourceServer(...jwt(...))` đăng ký Bearer flow và dùng `ReactiveJwtDecoder` bean ở phần kế tiếp. Spring Security mặc định thiết lập Bearer entry point/access denied handler theo RFC 6750.

### 8.5. `src/main/java/demo/jwterrors/JwtDecoderConfig.java`

~~~java
package demo.jwterrors;

import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimNames;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class JwtDecoderConfig {

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${demo.jwt.issuer}") String issuer,
            @Value("${demo.jwt.jwk-set-uri}") String jwks,
            @Value("${demo.jwt.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwks).build();

        OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator =
            new JwtClaimValidator<List<String>>(
                JwtClaimNames.AUD,
                aud -> aud != null && aud.contains(audience));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaults, audienceValidator));

        return decoder;
    }
}
~~~

Trong kết quả Markdown, Spring placeholders `@Value("${demo.jwt.issuer}")` tương ứng với cú pháp Spring chuẩn, dấu dollar là thành phần bắt buộc của property expression.

Điểm quan trọng là `JwtValidators.createDefaultWithIssuer(issuer)` giữ kiểm tra `iss`, `exp` và `nbf`; audience validator được **ghép thêm**, không thay thế các validation mặc định. `NimbusReactiveJwtDecoder` còn phải verify chữ ký JWT qua JWKS trusted. Nếu token từ issuer đúng nhưng dành cho một API khác, audience validator từ chối trước khi vào controller.

### 8.6. `src/main/java/demo/jwterrors/OrderController.java`

~~~java
package demo.jwterrors;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.oauth2.server.resource.authentication
    .JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OrderController {

    public record CreateOrderRequest(String sku) {}

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/profile")
    public Mono<Map<String, String>> profile(
            JwtAuthenticationToken authentication) {
        return Mono.just(Map.of(
            "subject", authentication.getName()));
    }

    @GetMapping("/api/orders")
    public Mono<Map<String, Object>> orders(
            JwtAuthenticationToken authentication) {
        return Mono.just(Map.of(
            "owner", authentication.getName(),
            "ids", List.of("order-101", "order-102")));
    }

    @PostMapping("/api/orders")
    public Mono<ResponseEntity<Map<String, String>>> create(
            @RequestBody Mono<CreateOrderRequest> body,
            JwtAuthenticationToken authentication) {
        return body.map(input ->
            ResponseEntity.status(HttpStatus.CREATED).body(
                Map.of(
                    "createdBy", authentication.getName(),
                    "sku", input.sku())));
    }
}
~~~

Controller chỉ minh họa HTTP responses, **không có database**. `JwtAuthenticationToken.getName()` mặc định thường dựa vào `sub` claim đã được decoder xác minh. Trong sản phẩm thực, việc truy xuất danh sách orders vẫn phải lọc theo user/tenant và chính sách resource; không trả mọi đơn hàng chỉ vì token có `orders.read`.

### 8.7. Chạy

~~~bash
# Linux/macOS
./gradlew bootRun

# Windows
gradlew.bat bootRun
~~~

`GET /public/ping` trả status 200 và body:

~~~json
{"status":"ok"}
~~~

Domain JWKS `idp.example.test` là minh họa **không có dịch vụ thật**. Không kỳ vọng bất kỳ JWT thực nào được xác minh qua endpoint này. Có thể kiểm thử các nhánh no-token, mock authentication và mocked decoder; muốn end-to-end phải cấu hình IdP/JWKS thật hoặc test JWKS server.

## 9. Kiểm tra bằng `curl`

**Không có token:**

~~~bash
curl -i http://localhost:8080/api/orders
~~~

Kỳ vọng 401 và `WWW-Authenticate: Bearer`.

**Có header Bearer nhưng token không phải JWT hợp lệ:**

~~~bash
curl -i \
  -H 'Authorization: Bearer broken.jwt.value' \
  http://localhost:8080/api/orders
~~~

Một decoder hoạt động với trusted JWKS sẽ từ chối token sai định dạng/chữ ký, thường 401 `invalid_token`. Với IdP demo không hoạt động, test runtime còn phụ thuộc việc lỗi được phát hiện ở parser hay key lookup; hãy dùng mocked decoder/test JWKS để kiểm chứng status lặp lại được.

**Header thiếu token sau Bearer scheme:**

~~~bash
curl -i \
  -H 'Authorization: Bearer' \
  http://localhost:8080/api/orders
~~~

Đừng đoán status tuyệt đối. Converter có thể phân loại malformed Bearer request (`invalid_request`) hoặc xem như không có token; kiểm tra header/status thật và Spring Security version.

**JWT thực sự hết hạn:**

~~~bash
curl -i \
  -H "Authorization: Bearer EXPIRED_SIGNED_TEST_JWT" \
  http://localhost:8080/api/orders
~~~

`EXPIRED_SIGNED_TEST_JWT` chỉ là ký hiệu trong bài. Để test **expiry**, token phải có chữ ký/issuer/audience đúng, nhưng `exp` đã qua đủ lâu. Nếu chỉ nhập chuỗi ký hiệu, bạn đang test malformed JWT, không phải expiry.

**JWT hợp lệ nhưng thiếu scope:**

~~~bash
curl -i \
  -H "Authorization: Bearer VALID_SIGNED_JWT_WITH_PROFILE_ONLY" \
  http://localhost:8080/api/orders
~~~

Token test cần **qua được decoder**, có `scope=profile` nhưng thiếu `orders.read`; kết quả điển hình 403 `insufficient_scope`. Một token sai chữ ký sẽ 401, không đủ điều kiện để kiểm tra scope.

**Đúng JWT + scope:**

~~~bash
curl -i \
  -H "Authorization: Bearer VALID_SIGNED_JWT_WITH_ORDERS_READ" \
  http://localhost:8080/api/orders
~~~

Dùng signed token thử nghiệm thật do IdP test phát hành mới kỳ vọng 200. Tất cả `VALID_*` ở đây là ký hiệu **không phải credentials**.

## 10. Test authorization bằng `WebTestClient` và `mockJwt()`

`SecurityMockServerConfigurers.mockJwt()` của Spring Security Test cung cấp `JwtAuthenticationToken` giả trong test để kiểm tra **authorization policies** mà không cần ký JWT và chạy IdP. Nó **không thực hiện chữ ký/expiry/issuer/audience validation**, vì vậy không dùng để chứng minh decoder production đã đúng.

Tệp `src/test/java/demo/jwterrors/JwtScopePolicyTest.java`:

~~~java
package demo.jwterrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class JwtScopePolicyTest {

    @Autowired
    WebTestClient client;

    @Test
    void noTokenReturns401AndBearerChallenge() {
        client.get().uri("/api/orders").exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().value(HttpHeaders.WWW_AUTHENTICATE,
                value -> assertTrue(value.startsWith("Bearer")));
    }

    @Test
    void publicPingIsAllowed() {
        client.get().uri("/public/ping").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void validJwtWithoutReadScopeReturns403() {
        client.mutateWith(mockJwt().jwt(
                jwt -> jwt.claim("scope", "profile")))
            .get().uri("/api/orders").exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void readScopeAllowsGet() {
        client.mutateWith(mockJwt().jwt(
                jwt -> jwt.claim("scope", "orders.read")))
            .get().uri("/api/orders").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.ids[0]").isEqualTo("order-101");
    }

    @Test
    void readScopeDoesNotAllowPost() {
        client.mutateWith(mockJwt().jwt(
                jwt -> jwt.claim("scope", "orders.read")))
            .post().uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"sku\":\"notebook\"}")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void writeScopeAllowsPost() {
        client.mutateWith(mockJwt().jwt(
                jwt -> jwt.claim("scope", "orders.write")))
            .post().uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"sku\":\"notebook\"}")
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.sku").isEqualTo("notebook");
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests 'demo.jwterrors.JwtScopePolicyTest'
~~~

**Diễn giải:** JWT authentication giả được chèn trước authorization. Token thiếu 401; authenticated nhưng scope thiếu 403; GET/POST yêu cầu scopes khác nhau. Không gọi các test trên là “test chữ ký JWT”; `mockJwt()` có thể tạo Jwt `alg=none` trong test nhưng điều đó **không thay đổi chính sách verify token thật** của decoder production.

## 11. Test error handling khi decoder từ chối JWT

Để kiểm tra liệu decoder failure có được chuyển thành 401 và `WWW-Authenticate: Bearer error="invalid_token"` không, có thể dùng test-specific Mockito mock cho `ReactiveJwtDecoder`. **Đây là test giao tiếp filter/handler**, không xác minh expiry/chữ ký thật.

Tệp `src/test/java/demo/jwterrors/JwtAuthenticationFailureTest.java`:

~~~java
package demo.jwterrors;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwtValidationException;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class JwtAuthenticationFailureTest {

    @Autowired
    WebTestClient client;

    @MockBean
    ReactiveJwtDecoder decoder;

    @Test
    void invalidJwtReturns401InvalidToken() {
        when(decoder.decode("broken.jwt.value"))
            .thenReturn(Mono.error(
                new BadJwtException("Synthetic malformed JWT")));

        client.get().uri("/api/orders")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer broken.jwt.value")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().value(HttpHeaders.WWW_AUTHENTICATE,
                value -> assertTrue(value.contains("invalid_token")));
    }

    @Test
    void syntheticExpiryErrorReturns401InvalidToken() {
        var validationError = new JwtValidationException(
            "Synthetic expired JWT",
            List.of(new OAuth2Error(
                "invalid_token", "expired", null)));

        when(decoder.decode("expired.jwt.value"))
            .thenReturn(Mono.error(validationError));

        client.get().uri("/api/orders")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer expired.jwt.value")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().value(HttpHeaders.WWW_AUTHENTICATE,
                value -> assertTrue(value.contains("invalid_token")));
    }
}
~~~

`@MockBean` được Spring Boot 3.x hỗ trợ, nhưng đã deprecated ở một số bản Boot 3.4+ để chuyển sang cơ chế Mockito bean override mới hơn. Khi dự án nâng version, cập nhật annotation test phù hợp thay vì thay decoder production.

**Không hiểu `expired.jwt.value` là token hết hạn thật.** Mockito giả lập `JwtValidationException` của validator. Test này chỉ kiểm tra **mapping exception → 401 invalid_token**.

### Test thời hạn `exp` trực tiếp

Tệp `src/test/java/demo/jwterrors/JwtExpiryValidatorTest.java`:

~~~java
package demo.jwterrors;

import java.time.Duration;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

import static org.junit.jupiter.api.Assertions.assertTrue;

class JwtExpiryValidatorTest {

    @Test
    void jwtExpiredFiveMinutesAgoIsRejected() {
        Instant now = Instant.now();

        Jwt token = Jwt.withTokenValue("synthetic-test-token")
            .header("alg", "RS256")
            .claim("sub", "alice")
            .issuedAt(now.minusSeconds(3600))
            .expiresAt(now.minusSeconds(300))
            .build();

        assertTrue(
            new JwtTimestampValidator(Duration.ofSeconds(60))
                .validate(token).hasErrors());
    }
}
~~~

Đây là test **timestamp validator**, không thử signature dù `header("alg","RS256")` đã có. Để kiểm tra hoàn chỉnh, cần JWT ký bằng private key test và decoder dùng public JWK tương ứng.

## 12. Test JWT thật với JWKS test server

Khi nâng lên integration tests, hãy tạo một RSA/EC keypair **chỉ trong môi trường test**, host JWKS qua mock server, ký JWT test, rồi gửi `Authorization: Bearer ...` thực qua `WebTestClient` mà không dùng `mockJwt()`. Bộ case nên có:

| Test token | Chữ ký | `iss` | `aud` | `exp` | Scope | Kỳ vọng |
| --- | --- | --- | --- | --- | --- | --- |
| Read hợp lệ | Đúng | Đúng | orders-api | Tương lai | orders.read | 200 GET |
| Missing | Không token | — | — | — | — | 401 |
| Tampered | Sai | Đúng trong payload giả | Đúng giả | Tương lai | orders.read | 401 invalid_token |
| Malformed JWT | Không parse | — | — | — | — | 401 invalid_token |
| Expired | Đúng | Đúng | Đúng | Quá hạn vài phút | orders.read | 401 invalid_token |
| Not-before | Đúng | Đúng | Đúng | Tương lai, nbf sau hiện tại | orders.read | 401 invalid_token |
| Wrong issuer | Đúng | Sai | Đúng | Tương lai | orders.read | 401 invalid_token |
| Wrong audience | Đúng | Đúng | billing-api | Tương lai | orders.read | 401 invalid_token |
| Missing scope | Đúng | Đúng | Đúng | Tương lai | profile | 403 insufficient_scope |
| Read on POST | Đúng | Đúng | Đúng | Tương lai | orders.read | 403 |
| Write on POST | Đúng | Đúng | Đúng | Tương lai | orders.write | 201 |

Khi test `kid`/key rotation, thay JWKS giữa các requests và quan sát cache/reload theo chính sách. **Không** dùng production private keys trong tests. Lưu ý access token có thể là opaque, không phải JWT; nếu IdP phát opaque tokens, Resource Server phải cấu hình introspection, không ép decoder JWT đọc opaque token.

## 13. Custom JSON error: giữ chuẩn Bearer

Mặc định Spring Security có:

- `BearerTokenServerAuthenticationEntryPoint`: bắt đầu xác thực/challenge khi Bearer token không có hoặc authentication hỏng.
- `BearerTokenServerAccessDeniedHandler`: xử lý `AccessDeniedException` khi request đã xác thực nhưng không đủ quyền.

Nếu cần khai báo tường minh trong `oauth2ResourceServer` DSL:

~~~java
// Chỉ là trích đoạn SecurityWebFilterChain để minh họa.
.oauth2ResourceServer(oauth2 -> oauth2
    .authenticationEntryPoint(
        new BearerTokenServerAuthenticationEntryPoint())
    .accessDeniedHandler(
        new BearerTokenServerAccessDeniedHandler())
    .jwt(Customizer.withDefaults()))
~~~

Imports:

~~~text
org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint
org.springframework.security.oauth2.server.resource.web.access.server.BearerTokenServerAccessDeniedHandler
~~~

Nhiều REST APIs muốn thêm body:

~~~json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "A valid access token is required"
}
~~~

Điều này có thể làm qua custom `ServerAuthenticationEntryPoint` hoặc `ServerAccessDeniedHandler`, nhưng phải bảo toàn:

1. Status **401/403/400** đúng ý nghĩa và Bearer error code.
2. Header `WWW-Authenticate` đúng RFC 6750; JSON body không thay thế challenge.
3. Không tiết lộ raw JWT, JWK, claims nhạy cảm, stack trace, server filesystem paths hoặc client secret.
4. Không trả 200 với body có trường error.
5. Không ghi response hai lần; nếu delegate đã `setComplete()`/commit response thì không ghép `.then(writeJson())` một cách mù quáng.
6. Không đặt logic “refresh token” trong Resource Server error handler. Client OAuth2 chịu trách nhiệm xin token mới.
7. Test bằng `WebTestClient` cả status/header và body, kể cả response thiếu token, expired, insufficient scope.

Một policy an toàn là **giữ Bearer entry point/denied handler mặc định** nếu frontend đã xử lý status/challenge; chỉ tùy biến khi sản phẩm thực sự cần error envelope riêng.

## 14. Token hết hạn: Resource Server và Client phải làm gì?

**Resource Server:** kiểm tra `exp`/`nbf`, fail closed khi token không còn hợp lệ, trả Bearer `invalid_token` nếu phù hợp, không tái cấp token.

**OAuth2 Client:** nếu có refresh token theo Authorization Code, dùng refresh-token flow phù hợp với Authorization Server; nếu dùng Client Credentials, thường xin access token mới bằng client authentication, không có refresh token. Client không được cứ retry mãi bằng cùng JWT expired.

**Cẩn thận retry:** Nếu một POST đã có side effect và client nhận 401/timeout, việc tự gửi lại có thể tạo giao dịch trùng khi response bị mất; cần idempotency key/contract trước khi retry. Một GET idempotent có thể retry thuận lợi hơn nhưng vẫn cần giới hạn.

**Clock skew:** nếu tất cả các service đồng loạt coi JWT “chưa hợp lệ”, kiểm tra NTP/`nbf` và issuer clock. Nếu chỉ một node từ chối, kiểm tra node đó và phiên bản validator. Không cấp token thời hạn vô hạn để né clock drift.

## 15. CSRF, CORS, Basic và JWT là các cơ chế khác nhau

Trong demo, `csrf.disable()` chỉ hợp lý vì đường API được giới hạn vào **stateless Bearer token mà client gắn chủ động trong header**, không có browser tự đính kèm cookie/session để xác thực. Nếu ứng dụng hỗ trợ form login/browser cookies hoặc Basic credentials được browser tự gửi, threat model CSRF thay đổi; cần giữ CSRF cho unsafe methods hoặc tách `SecurityWebFilterChain`.

**CORS:** frontend từ origin khác có thể phải preflight khi gửi header `Authorization`. Preflight OPTIONS cần được CORS xử lý đúng thứ tự và allowed headers/methods. CORS lỗi không đồng nghĩa 401 JWT; browser đôi khi hiển thị “CORS error” vì response 401/500 thiếu CORS headers. Không bật wildcard origins + credentials để sửa nhanh.

**HTTP Basic:** `Authorization: Basic ...` không phải Bearer. Khi Basic bị disable và API protected chỉ nhận Bearer, dùng Basic thường không tạo authenticated identity, nên response thường là 401 Bearer challenge. Không trộn `httpBasic()` và JWT Bearer vào cùng chain nếu hợp đồng API không yêu cầu cả hai.

## 16. Những sai lầm phổ biến

**Sai lầm 1: Base64URL decode rồi tin `scope`.** Signature phải được verify; payload có thể bị attacker tự tạo.

**Sai lầm 2: Chấp nhận mọi `alg`/`kid` do JWT khai báo.** Dùng trusted algorithms/JWKS allowlist và key resolution đúng, không gọi URL theo header không tin cậy.

**Sai lầm 3: Chỉ kiểm tra `iss`, bỏ `aud`.** Token của API khác có thể dùng nhầm ở API này.

**Sai lầm 4: Chuyển 401 expired thành 403.** Hết hạn là authentication failure; thiếu scope mới thường là authorization denial.

**Sai lầm 5: Coi mọi malformed header là `invalid_token`.** `invalid_request` thường mô tả lỗi cấu trúc Bearer request, có thể status 400.

**Sai lầm 6: Dùng `hasRole("orders.read")` khi JWT có scope.** Mặc định scope chuyển thành `SCOPE_orders.read`.

**Sai lầm 7: Đã có scope nên bỏ object authorization.** API còn phải kiểm tra owner/tenant/resource constraints.

**Sai lầm 8: Dùng `mockJwt()` test và tuyên bố đã kiểm thử signature/expiry.** Mock authentication bỏ qua decoder.

**Sai lầm 9: Cho token vào URL query string.** Token có thể rò qua logs, history, referrer và cache; dùng header Authorization qua HTTPS.

**Sai lầm 10: In toàn bộ `Authentication`/JWT vào log.** Có thể lộ access token, claims, personal information; chỉ log loại lỗi, request ID và metrics an toàn.

**Sai lầm 11: Nới clock skew vài giờ hoặc tắt validation.** Cần sửa đồng hồ/provider và lifecycle, không mở chấp nhận expired token.

**Sai lầm 12: Khi JWKS lỗi, cho token đi qua không verify.** Phải fail closed và có monitoring/outage strategy.

**Sai lầm 13: Dùng OIDC `id_token` để gọi API yêu cầu access token.** Token type/audience/scopes phải phù hợp resource server.

**Sai lầm 14: Resource Server tự lấy refresh token khi thấy 401.** Client/AS quản lý refresh; Resource Server chỉ nhận và xác minh access token.

## 17. Quy trình chẩn đoán

1. **Đúng route và chain?** Kiểm tra method/path và `SecurityWebFilterChain`, có bị match vào chain khác hay không.
2. **Status + challenge là gì?** 400, 401, 403 hay 5xx; có `WWW-Authenticate: Bearer` và error code nào?
3. **Có Bearer token không?** Kiểm tra client có gửi đúng Authorization header, không ghi giá trị token thật vào ticket.
4. **JWT có parse/verify được?** Trusted JWKS, algorithm, signature, `kid` và khả năng fetch keys.
5. **Claims có hợp lệ?** `iss`, `aud`, `exp`, `nbf`, clock skew/NTP và token type.
6. **Nếu 403:** authorities có `SCOPE_` phù hợp chưa? Cần scope khác cho GET/POST? Object/tenant policy có từ chối?
7. **Nếu nhiều nodes:** kiểm tra clock và caches, issuer/JWKS config nhất quán, key rotation.
8. **Nếu browser khác curl:** kiểm tra CORS preflight, cookie/CSRF trong security model, Authorization header injection.
9. **Nếu lỗi hàng loạt 5xx:** kiểm tra JWKS/IdP/network và service logs, không giả là token hết hạn.
10. **Chạy negative tests** cho missing, malformed, bad signature, expired, wrong issuer/audience và insufficient scope.

### Bảng gợi ý vận hành

| Dấu hiệu | Hướng xử lý |
| --- | --- |
| 401 Bearer không có error | Client thiếu credentials hoặc token không được nhận theo scheme |
| 401 `invalid_token` | Decode/validation thất bại; phân loại nội bộ signature/expiry/issuer/aud |
| 400 `invalid_request` | Sửa cấu trúc HTTP request/Bearer |
| 403 `insufficient_scope` | Sửa grants/scopes hoặc quyền truy cập, không tăng quyền ngầm |
| 403 khác | Kiểm tra domain ownership/CSRF/custom denied handler |
| 5xx JWKS | Kiểm tra upstream/timeout/cache/key rotation |
| GET thành công, POST thất bại | Scope đọc/ghi khác nhau; hoặc CSRF trong mô hình dùng cookie |
| Test mock pass nhưng JWT thật fail | `mockJwt()` không kiểm tra signature/claims |
| Public request có Bearer sai bị 401 | Filter có thể authentication attempt dù route `permitAll` |

## 18. Checklist chất lượng và production

| Kiểm tra | Kết quả cần đạt |
| --- | --- |
| Token transport | Bearer header qua HTTPS, không token trong URL |
| Missing | Protected route **401** và Bearer challenge |
| Header malformed | `invalid_request`/status theo parser thực, không chấp nhận ambiguity |
| JWT invalid | Signature/issuer/audience/expiry sai → **401 invalid_token** |
| Scope thiếu | JWT hợp lệ thiếu `SCOPE_...` → **403** |
| Resource-level policy | Owner/tenant authorization riêng biệt |
| Decoder | `ReactiveJwtDecoder` trusted algorithms/JWKS |
| Claims | `iss`/`aud`/`exp`/`nbf` validation bật |
| Key rotation | Trusted JWKS cache/refresh/timeout được test |
| Clock | NTP đúng, skew nhỏ và có chủ đích |
| Entry point | `BearerTokenServerAuthenticationEntryPoint` semantics |
| Denied handler | `BearerTokenServerAccessDeniedHandler` semantics |
| Error response | Status/header chuẩn, không lộ tokens/stack traces |
| JWT type | Không coi ID token là API access token |
| CSRF | Tắt chỉ khi đúng bearer-only stateless threat model |
| Test policy | `WebTestClient` + `mockJwt()` cho authorities |
| Test actual decoder | Signed JWT với mock JWKS cho signature/audience/time |
| Logs | Không chứa `Authorization`, JWT, refresh tokens, private keys |
| Client | Refresh/re-authorize qua AS; không retry vô hạn |
| Multi-tenant | Issuer/decoder allowlist và tenant boundaries |

## 19. Câu hỏi tự kiểm tra

**1. Thiếu Authorization header trên GET protected phải trả 403 hay 401?**  
Thường 401, kèm Bearer challenge vì request chưa có authentication hợp lệ.

**2. JWT hợp lệ nhưng thiếu `orders.read` phải trả gì?**  
Thường 403, có thể `insufficient_scope` với Bearer denied handler.

**3. JWT `exp` đã qua nhưng vẫn có `scope=orders.read` có được xử lý không?**  
Không; authentication phải thành công trước authorization. JWT expired không tạo trusted `Authentication`.

**4. `invalid_request` khác `invalid_token` thế nào?**  
`invalid_request` mô tả cấu trúc Bearer request sai; `invalid_token` mô tả token được trình bày nhưng không hợp lệ.

**5. Vì sao không chỉ cần `Base64.decode` JWT payload?**  
Vì payload không có tính tin cậy nếu chưa xác minh chữ ký và claims.

**6. `scope=orders.read` map thành authority nào theo mặc định?**  
`SCOPE_orders.read`.

**7. Vì sao cần `aud` nếu đã kiểm tra `iss`?**  
Một issuer có thể cấp token cho nhiều API; `aud` bảo đảm token dành cho API hiện tại.

**8. `mockJwt()` có xác minh chữ ký và `exp` không?**  
Không. Nó mô phỏng authentication để test authorization; muốn test decoder thật phải có signed JWT/JWKS test.

**9. Ai refresh access token khi Resource Server trả 401 expired?**  
OAuth2 Client/Authorization Server, không phải Resource Server.

**10. Có nên luôn tắt CSRF khi bật JWT?**  
Không. Phải xét cách browser truyền credentials; demo chỉ tắt vì stateless Bearer header-only.

## Ghi nhớ

- **Missing token → 401 Bearer challenge.**
- **Invalid/expired JWT → thường 401 `invalid_token`; malformed Bearer request → có thể 400 `invalid_request`.**
- **Valid JWT nhưng thiếu scope → thường 403 `insufficient_scope`.**
- Authentication qua `ReactiveJwtDecoder` phải xét signature, issuer, audience, time và trusted keys; authorization xét `SCOPE_` cùng quyền tài nguyên.
- Không tin JWT chỉ vì decode được và không coi `mockJwt()` là test signature.
- Giữ `WWW-Authenticate` theo RFC 6750; tránh lộ token hoặc stack trace trong JSON/log.
- Resource Server không tự cấp/refresh token, và scope không thay ownership/tenant policy.

### Tài liệu chính thức

- [Spring Security 6.5 — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — OAuth2 Resource Server WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html)
- [Spring Security — Testing OAuth2 in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security 6.5 — BearerTokenServerAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/web/server/BearerTokenServerAuthenticationEntryPoint.html)
- [Spring Security 6.5 — BearerTokenServerAccessDeniedHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/web/access/server/BearerTokenServerAccessDeniedHandler.html)
- [Spring Security 6.5 — BearerTokenErrorCodes](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/BearerTokenErrorCodes.html)
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
