# Cấu hình issuer-uri, jwk-set-uri và khóa được tin cậy

## 1. Bài toán: WebFlux Resource Server tin access token của ai?

Một ứng dụng **Spring WebFlux** đóng vai trò **OAuth 2.0 Resource Server** bảo vệ API bằng access token. Client gửi token qua HTTP:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0yMDI2LTAxIn0...
```

API không thể chấp nhận token chỉ vì có ba phần ngăn bằng dấu chấm hoặc payload có `sub` và `scope`. Trước khi tạo authenticated principal, API cần trả lời:

1. **Ai phát hành token?** Claim `iss` có đúng **issuer** được cấu hình tin cậy không?
2. **Chữ ký có thật sự hợp lệ?** Header `alg` và `kid` có dẫn tới một public key được chấp nhận từ nguồn đáng tin không?
3. **Token có dành cho API này?** `aud` phải phù hợp với `orders-api`; token của frontend hay API khác không được mặc nhiên chấp nhận.
4. **Token còn hiệu lực và đúng hồ sơ?** `exp`, `nbf` và các yêu cầu bổ sung của access-token profile phải đạt.
5. **Token có đủ quyền?** `scope`/authorities phải phù hợp endpoint; owner/tenant và business policy vẫn cần kiểm tra.

Trong Spring Security, hai thuộc tính thường thấy là:

- **`issuer-uri`:** định danh Authorization Server hoặc OpenID Provider được tin cậy. Khi dùng discovery, Spring có thể tìm metadata rồi lấy địa chỉ JWKS; Spring cũng phải kiểm tra claim `iss` của JWT.
- **`jwk-set-uri`:** địa chỉ một **JSON Web Key Set (JWKS)** chứa public keys mà Resource Server dùng để xác minh chữ ký JWS. Đường dẫn này cần được lấy từ nhà phát hành đáng tin hoặc cấu hình qua kênh tin cậy, **không lấy từ token do client đưa vào**.

Hai giá trị liên quan nhưng **không thể thay cho nhau**. Một JWKS public key xác minh được chữ ký không tự chứng minh JWT là access token dành cho `orders-api`; claim `iss` phù hợp không tự chứng minh chữ ký nếu nguồn khóa sai.

Bài học nằm trong chương **JWT trong WebFlux** của mô-đun **Spring Security OAuth 2.0 OIDC Resource Server**. Các ví dụ sử dụng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Reactor/WebFlux**. Đường dẫn, domain, key ID, JWT và client đều là dữ liệu minh họa. Với bản thư viện mới hơn, kiểm tra API/builder và auto-configuration tương ứng.

> **Nguyên tắc:** Trust không phát sinh từ `kid`, `alg` hay `iss` nằm trong JWT chưa xác minh. Trust đến từ **cấu hình issuer/nguồn khóa đã cho phép trước**, quy tắc xác minh cryptographic và token validation của Resource Server.

---

## 2. Hình dung luồng xác minh JWT trong WebFlux

Một Resource Server reactive đi qua `SecurityWebFilterChain`, không phải servlet `SecurityFilterChain`. Spring Security lấy Bearer token, gọi `ReactiveJwtDecoder` và tạo authentication nằm trong **Reactor Context** theo request.

```mermaid
sequenceDiagram
    participant C as Client
    participant W as Spring WebFlux SecurityWebFilterChain
    participant D as ReactiveJwtDecoder
    participant M as Trusted issuer metadata/JWKS
    participant A as Reactive Controller / Service

    C->>W: GET /api/orders/42 + Bearer JWT
    W->>D: decode(token)
    opt Cần discovery/JWKS theo cấu hình, cache và key id
        D->>M: HTTPS GET metadata/JWK set từ nguồn đã tin
        M-->>D: issuer metadata / public keys
    end
    D->>D: Kiểm chữ ký + alg + iss + timestamps + aud/profile
    alt JWT bị từ chối
        D-->>W: Reactive authentication failure
        W-->>C: 401 + Bearer challenge
    else JWT hợp lệ
        D-->>W: Jwt verified
        W->>W: Chuyển scope -> authorities
        alt Thiếu quyền của route
            W-->>C: 403 Forbidden
        else Đủ route authority
            W->>A: Reactive request với authenticated principal
            A->>A: Kiểm tra owner/tenant/business policy
            A-->>C: Dữ liệu được phép hoặc bị từ chối
        end
    end
```

Hãy tách thành ba **ranh giới tin cậy**:

| Ranh giới | Bằng chứng cần | Ai kiểm tra? |
|---|---|---|
| **Cryptographic trust** | Token ký bằng private key tương ứng với **public key đáng tin**, thuật toán được phép. | `ReactiveJwtDecoder`/JWS verifier. |
| **Token applicability** | Issuer, audience, thời hạn, token type/profile đúng API. | JWT validators của Resource Server. |
| **Business authorization** | Scope, role, ownership, tenant, trạng thái nghiệp vụ. | `SecurityWebFilterChain`, method/domain service, repository. |

Một lỗi thường gặp là **chỉ làm ranh giới thứ nhất**, rồi gọi token “valid” cho mọi mục đích.

### 2.1. Những thành phần khác với Servlet stack

| Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|
| `SecurityFilterChain` | **`SecurityWebFilterChain`** |
| `HttpSecurity` | **`ServerHttpSecurity`** |
| `JwtDecoder` | **`ReactiveJwtDecoder`** |
| `JwtDecoders` | **`ReactiveJwtDecoders`** |
| `NimbusJwtDecoder` | **`NimbusReactiveJwtDecoder`** |
| `AuthenticationManager` | **`ReactiveAuthenticationManager`** |
| `SecurityContextHolder` dựa trên thread context trong Servlet | **`ReactiveSecurityContextHolder` / Reactor Context** cho reactive flow |
| `MockMvc` | **`WebTestClient`** |

Một ứng dụng `spring-boot-starter-webflux` không nên sao chép `HttpSecurity`, `OncePerRequestFilter` hoặc servlet `JwtDecoder` rồi nghĩ chúng tự bảo vệ các WebFlux routes. Khi có đồng thời WebFlux và MVC dependencies, Spring Boot có thể lựa chọn một web application type khác dự định; cần kiểm tra stack thực sự đang chạy.

---

## 3. Một JWT access token minh họa

Header JWT:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "orders-signing-key-2026-11"
}
```

Payload:

```json
{
  "iss": "https://auth.example.test/realms/orders",
  "sub": "alice-123",
  "aud": ["orders-api"],
  "scope": "orders:read orders:write",
  "iat": 1890000000,
  "nbf": 1890000000,
  "exp": 1890003600,
  "client_id": "web-portal"
}
```

Giải thích:

- `iss` là issuer của access token; phải khớp **issuer đã cấu hình hoặc được allowlist**.
- `sub` định danh subject trong namespace của issuer; không mặc nhiên là owner của mọi order.
- `aud` cho biết resource mà token dành cho. `orders-api` phải nằm trong audience theo hợp đồng.
- `alg=RS256` chỉ là **khẳng định** thuật toán trong JWS header. Decoder phải chỉ chấp nhận các thuật toán được cấu hình, không tự tin mọi giá trị do client gửi.
- `kid` gợi ý **key ID** để chọn key trong bộ JWKS tin cậy. `kid` không phải proof of trust và không phải URL.
- `typ=at+jwt` là header type được profile JWT access token theo RFC 9068 sử dụng. Việc kiểm tra loại token tùy cấu hình/phiên bản; không mặc nhiên cho rằng chỉ có `issuer-uri` là đã triển khai đầy đủ RFC 9068.
- `exp`, `nbf`, `iat` dùng **NumericDate** (giây Unix epoch), không phải milliseconds.
- `scope` thể hiện quyền OAuth theo hợp đồng; Spring Security thường ánh xạ thành authorities `SCOPE_orders:read`, `SCOPE_orders:write`.

Payload JWT **không được mã hóa bí mật bởi Base64URL**. Bất kỳ ai có JWT đều có thể đọc claims nếu nó là JWS thông thường. Giá trị trong payload không được tin cho đến khi chữ ký, issuer và các validators đã đạt.

> **Lưu ý thời gian:** Các số timestamp trên chỉ là ví dụ format. Một token demo có thời gian trong tương lai hoặc quá khứ so với môi trường chạy sẽ bị từ chối nếu kiểm tra `exp`/`nbf` theo thời gian thực. Khi test, tạo timestamps tương đối với `Clock`/`Instant.now()` hoặc cố định clock.

---

## 4. `issuer-uri`: danh tính nguồn phát hành và cơ chế discovery

Trong Spring Boot:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test/realms/orders
```

Với cấu hình issuer-only và không có bean decoder tùy chỉnh, Spring Boot/Spring Security có thể:

1. Sử dụng cơ chế provider/Authorization Server metadata discovery để tìm các endpoint của issuer.
2. Đọc `jwks_uri` từ metadata đáng tin.
3. Tạo `ReactiveJwtDecoder` có khả năng lấy/cập nhật public keys từ JWKS.
4. Thiết lập JWT validation cần thiết, gồm **issuer**.
5. Xác minh access token trong luồng reactive khi request đến.

### 4.1. Discovery metadata có thể trông như thế nào?

Ví dụ một OpenID Provider xuất bản:

```http
GET /realms/orders/.well-known/openid-configuration HTTP/1.1
Host: auth.example.test
Accept: application/json
```

Một metadata document minh họa:

```json
{
  "issuer": "https://auth.example.test/realms/orders",
  "authorization_endpoint":
    "https://auth.example.test/realms/orders/protocol/openid-connect/auth",
  "token_endpoint":
    "https://auth.example.test/realms/orders/protocol/openid-connect/token",
  "jwks_uri":
    "https://auth.example.test/realms/orders/protocol/openid-connect/certs"
}
```

**Không hardcode path discovery giống nhau cho mọi issuer.** Tùy issuer path và chuẩn metadata được hỗ trợ, thư viện có thể thử những URL theo quy tắc của OIDC Discovery và OAuth 2.0 Authorization Server Metadata. `jwks_uri` phải được lấy từ metadata đáng tin, không phải do JWT header chọn.

Cấu hình `issuer-uri` giúp ứng dụng có một **định danh issuer tường minh**. Sau khi có key, JWT claim:

```json
{"iss":"https://auth.example.test/realms/orders"}
```

phải đúng với issuer được chấp nhận. Thường so sánh là **giá trị chuỗi chính xác**, vì vậy không tự coi các URL khác nhau chỉ vì trailing slash, path, scheme hoặc chữ hoa/thường là cùng issuer:

```text
https://auth.example.test/realms/orders
https://auth.example.test/realms/orders/
https://auth.example.test/realms/other
http://auth.example.test/realms/orders
```

Nếu issuer thực tế dùng trailing slash, cấu hình phải theo đúng issuer được công bố và `iss` được phát hành, không “sửa” bằng cách bỏ kiểm tra issuer.

### 4.2. Khi nào issuer-only làm ứng dụng phụ thuộc Authorization Server?

Ở cấu hình tự discovery, decoder/auto-configuration có thể cần gọi metadata endpoint trong quá trình khởi tạo. **Ở những phiên bản/đường cấu hình nhất định, ứng dụng không thể khởi động thành công nếu issuer metadata không truy cập được lúc startup.** Đó là lý do nhiều hệ thống vận hành muốn cấu hình trực tiếp `jwk-set-uri`.

Không nên suy luận từ một bản Spring Security khác rằng discovery luôn được thực hiện ở startup hay luôn được trì hoãn đến request đầu tiên. Cần quan sát hành vi của **phiên bản framework và cấu hình đang dùng**.

### 4.3. Issuer-only vẫn không tự biết audience theo ý nghiệp vụ

Chỉ có:

```yaml
jwt:
  issuer-uri: https://auth.example.test/realms/orders
```

không chứng minh JWT có `aud=orders-api`. Một issuer có thể phát hành token cho `payments-api` và `reports-api` bằng **cùng bộ signing keys**. Nếu Resource Server chỉ kiểm chữ ký + issuer + thời gian, token của API khác có nguy cơ bị nhận nhầm.

Vì vậy API nên xác định audience:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test/realms/orders
          audiences:
            - orders-api
```

Thuộc tính `audiences` được hỗ trợ trong những bản Spring Boot 3.x phù hợp; khi dùng bean `ReactiveJwtDecoder` tự tạo, phải tự gắn validator tương ứng vì auto-configuration có thể nhường quyền cho bean của bạn. Đừng mặc định cấu hình YAML `audiences` tự có hiệu lực với mọi custom decoder.

---

## 5. `jwk-set-uri`: địa chỉ bộ khóa xác minh chữ ký

**JWKS** là một JSON object có trường `keys` chứa các **JSON Web Keys (JWKs)**. Với JWT ký bằng RSA/EC bất đối xứng, phần công khai trong JWKS có thể được dùng để **verify** chữ ký mà không sở hữu private signing key.

Ví dụ JWKS đã rút gọn:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "orders-signing-key-2026-11",
      "alg": "RS256",
      "n": "BASE64URL_PUBLIC_MODULUS_PLACEHOLDER",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "orders-signing-key-2026-12",
      "alg": "RS256",
      "n": "BASE64URL_NEXT_PUBLIC_MODULUS_PLACEHOLDER",
      "e": "AQAB"
    }
  ]
}
```

Các chuỗi `n` placeholder không phải RSA modulus hợp lệ, chỉ minh họa cấu trúc. Trong JWKS thật:

- `kty` xác định kiểu key (`RSA`, `EC`, ...).
- `kid` là key ID để chọn key phù hợp từ một tập key **đã tin cậy**.
- `use=sig` cho biết key được sử dụng để ký/xác minh chữ ký.
- `alg` có thể giới hạn mục đích theo metadata/profile, **nhưng chính decoder phải có algorithm allowlist**, không dựa vào mỗi `alg` của JWKS.
- `n` và `e` là thành phần **public RSA key** (Base64URL).
- Với elliptic curve, JWK thường có `crv`, `x`, `y` thay cho `n`/`e`.

**JWKS không nên chứa private signing key components** như `d` từ RSA. Authorization Server giữ private key ở nơi bảo mật; Resource Server chỉ cần public key để verify khi dùng JWS bất đối xứng.

### 5.1. Cấu hình chỉ `jwk-set-uri`

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://auth.example.test/realms/orders/protocol/openid-connect/certs
```

Ưu điểm: decoder biết trực tiếp nơi lấy public keys mà không cần tìm `jwks_uri` qua metadata discovery.

Nhưng vấn đề cần nhớ: **chỉ biết JWKS URL không tự thiết lập expected issuer**. Nếu Resource Server không thêm issuer validator, token được ký bởi một key trong JWKS có thể được chấp nhận dù claim `iss` không đúng API dự kiến, tùy validators khác. Vì vậy **jwk-set-uri-only không phải cấu hình hoàn chỉnh** cho một API yêu cầu ràng buộc issuer chặt.

Một bất ngờ thường gặp:

```text
Configured JWK Set URI:
  https://auth.example.test/realms/orders/certs

JWT claims:
  iss = https://different-issuer.example.test

Cryptographic signature:
  verifies with configured public key

Question:
  Is issuer mismatch rejected?
Answer:
  Only if issuer validation is configured for the decoder.
```

Không dùng phương án này mà bỏ qua issuer validation chỉ để làm hệ thống khởi động dễ dàng hơn.

### 5.2. `kid` không phải “tin ai thì lấy key của người đó”

Một JWT header có thể là:

```json
{
  "alg": "RS256",
  "kid": "orders-signing-key-2026-11",
  "jku": "https://attacker.example.test/my-jwks"
}
```

Trong một cấu hình an toàn, **`jku` do token tự đưa không được tự động quyết định JWKS endpoint**. Nếu custom decoder lấy key từ URL trong token, attacker có thể:

1. Tự tạo private key và public JWKS tại host của mình.
2. Ký JWT giả chứa quyền admin bằng private key đó.
3. Gắn `jku` trỏ tới JWKS của attacker.
4. Dụ Resource Server tải public key không được allowlist và xác minh chữ ký của token giả.

Đây là lỗi **key-source confusion / untrusted JWK URL**, có thể dẫn tới SSRF hoặc authentication bypass. Spring Security decoder phải chỉ dùng **JWK source đã được cấu hình tin cậy** hoặc một resolver có allowlist issuer chặt. Không lấy `jku`, `x5u` hoặc embedded `jwk` trong header làm nguồn trust tùy ý.

### 5.3. `kid` có thể biến đổi khi xoay vòng khóa

Khi AS đổi signing key, JWT mới có thể có `kid=orders-signing-key-2026-12`. Resource Server nên có khả năng tải lại JWKS từ **cùng trusted endpoint** theo chính sách refresh/cache để xác minh key mới.

**Không khóa cứng một `kid` duy nhất trong code** nếu hệ thống yêu cầu auto-rotation. Mặt khác, không chấp nhận key lạ từ nguồn khác chỉ vì `kid` khớp. Trust source phải ổn định; key ID có thể thay đổi trong nguồn đó.

---

## 6. Kết hợp `issuer-uri` và `jwk-set-uri`: phương án production phổ biến

Để **không phụ thuộc metadata discovery khi startup** nhưng vẫn kiểm tra issuer, dùng cả hai:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test/realms/orders
          jwk-set-uri: https://auth.example.test/realms/orders/protocol/openid-connect/certs
          audiences:
            - orders-api
```

Ý nghĩa:

- **`issuer-uri`**: expected JWT `iss`, bảo vệ ranh giới danh tính issuer.
- **`jwk-set-uri`**: endpoint HTTPS cố định cung cấp public keys, tránh phải discovery `jwks_uri` khi bootstrap.
- **`audiences`**: token phải dành cho `orders-api`, không chỉ cùng issuer.
- **JWT validators**: thời hạn và các điều kiện khác của decoder.
- **HTTP authorization rules**: scope cho từng thao tác.
- **Business policy**: owner/tenant/resource permissions.

Với auto-configuration Spring Boot phù hợp, cách kết hợp này vẫn xác minh issuer trong khi không cần phụ thuộc discovery metadata để tìm JWK set URI. **Không nhầm “không cần discovery startup” với “không bao giờ cần network”.** Khi chưa có JWK tương ứng trong cache, hoặc khi key rotation cần refresh, decoder vẫn cần truy cập JWKS endpoint để xác minh token.

### 6.1. Bảng so sánh ba cách cấu hình

| Cấu hình | Nguồn tìm public key | Kiểm tra issuer | Startup/discovery |
|---|---|---|---|
| **Chỉ `issuer-uri`** | Discovery metadata dẫn đến `jwks_uri`. | Có theo issuer-aware decoder/auto-config. | Có thể phụ thuộc metadata endpoint khi bootstrap tùy version. |
| **Chỉ `jwk-set-uri`** | Cố định trực tiếp bằng config. | **Không suy ra tự động** nếu không cấu hình validator khác. | Không cần issuer discovery để biết JWK URL. |
| **Cả `issuer-uri` và `jwk-set-uri`** | Cố định trực tiếp; trusted config. | Có theo issuer-aware auto-config. | Tránh discovery để định vị JWK URL; vẫn cần JWKS khi xác minh key chưa cache. |

Nếu ứng dụng đã khai báo bean `ReactiveJwtDecoder` tự tạo, các quy tắc của Boot auto-config trên có thể **không tự áp dụng**: bạn phải đảm bảo validator issuer/audience/time/algorithm/profile được cài đúng.

### 6.2. Không lấy đường dẫn JWKS một cách tùy tiện

Một số issuer có metadata:

```json
{
  "issuer": "https://login.example.test/tenant-a",
  "jwks_uri": "https://keys.example.test/tenant-a/jwks.json"
}
```

JWKS **không bắt buộc** ở cùng hostname/path với issuer nếu issuer có hợp đồng đáng tin cho endpoint đó. Điều quan trọng là:

- Endpoint lấy từ **metadata đã xác minh** hoặc **trusted deployment configuration**.
- HTTPS certificate hợp lệ, hostname được xác minh.
- Không nhận URL mới từ Bearer token hoặc query parameter.
- Người vận hành xác nhận URL thuộc đúng realm/tenant/resource.
- Firewall/egress restrictions chặn kết nối tùy ý đến mạng nội bộ.

Không ép “JWKS phải luôn cùng domain với issuer” thành quy tắc giao thức; nhưng JWKS host khác cần được kiểm soát bằng configuration trust.

---

## 7. Spring WebFlux: một `SecurityWebFilterChain` hoàn chỉnh để học

### 7.1. Dependencies Maven

Dùng Spring Boot parent/BOM quản lý versions:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Trong các Boot 3.x thông dụng, resource-server starter quản lý các dependencies cần thiết cho JWT validation. Không trộn riêng phiên bản Nimbus/Jackson tùy ý nếu không có lý do kiểm soát dependency. Xác minh dependency tree khi dùng BOM khác.

### 7.2. WebFlux Security configuration

```java
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
public class ReactiveApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            // Ví dụ API chỉ dùng Bearer header, không dùng
            // cookie session làm credential. Browser app cần CSRF riêng.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)

            .authorizeExchange(exchange -> exchange
                .pathMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()

                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")

                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders:write")

                .pathMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_orders:admin")

                .anyExchange().denyAll()
            )

            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Điểm then chốt:

- **`@EnableWebFluxSecurity`** và **`ServerHttpSecurity`** áp dụng cho reactive stack.
- **`SecurityWebFilterChain`** bảo vệ WebFlux requests, không phải servlet filters.
- **`authorizeExchange`** và **`pathMatchers`** được dùng cho reactive exchange.
- Rule cụ thể theo method/path; `anyExchange().denyAll()` giảm rủi ro endpoint mới vô tình mở quyền.
- `oauth2ResourceServer(...jwt(...))` kích hoạt Bearer JWT authentication.
- `csrf(...disable)` chỉ hợp lý cho API stateless chỉ nhận Bearer header, không dựa vào browser cookies. Với ứng dụng dùng session/cookie cần đánh giá CSRF riêng.

Một token hợp lệ có `scope="orders:write"` không tự được `SCOPE_orders:read`. Scope semantics do issuer và API quy định; không tự giả định write bao gồm read. Và có đủ `SCOPE_orders:read` vẫn không cấp quyền đọc order của tenant/owner khác.

### 7.3. Cấu hình WebFlux không đồng nghĩa API phải dùng HTTP session

Reactive Resource Server thường hoạt động phù hợp stateless Bearer flow, mỗi request xác thực token riêng. Nếu ứng dụng đồng thời có OAuth login/browser session, cần tách `SecurityWebFilterChain` theo matcher, không để web session thay thế Bearer credential của API. `ReactiveSecurityContextHolder` lưu identity trong reactive context; không lấy `SecurityContextHolder` thread-local của Servlet làm nguồn user ở reactive handlers.

Một cấu hình ứng dụng có nhiều filter chains cần quy định độ ưu tiên và `securityMatcher` cho từng chain. Không áp `oauth2Login`/form-login trên API thuần Bearer nếu policy yêu cầu không nhận session cookie.

---

## 8. Khi phải tự tạo `ReactiveJwtDecoder`

Spring Boot cung cấp auto-configuration hữu ích. Nhưng có những trường hợp cần bean decoder riêng:

- Chỉ chấp nhận một tập JWS algorithms tường minh.
- Thêm audience validator bằng code và các custom claim validators.
- Kiểm soát nguồn JWKS/HTTP client/timeouts theo yêu cầu.
- Dùng public key tĩnh trong môi trường đóng.
- Hỗ trợ nhiều issuers theo trust policy cụ thể.
- Ràng buộc thêm token profile như RFC 9068.

**Nhớ:** Bean type là `ReactiveJwtDecoder`, không phải servlet `JwtDecoder`.

### 8.1. Tạo decoder bằng issuer discovery

Ví dụ:

```java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoders;

@Configuration
public class ReactiveDecoderFromIssuerConfig {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(
            @Value("${app.security.issuer}") String issuer) {
        return ReactiveJwtDecoders.fromIssuerLocation(issuer);
    }
}
```

Cấu hình:

```yaml
app:
  security:
    issuer: https://auth.example.test/realms/orders
```

`ReactiveJwtDecoders.fromIssuerLocation(...)` là phương pháp lấy decoder theo issuer metadata. Khi **tự đăng ký decoder bean**, cần xác nhận additional requirements như `aud=orders-api` vẫn được cấu hình trong decoder hoặc validators của bạn; không tự suy ra từ các property Boot vốn được auto-configuration xử lý.

### 8.2. Tạo decoder bằng JWKS URL + issuer + audience

Khi cần tránh issuer discovery nhưng vẫn giữ issuer/audience validation, có thể tự xây decoder:

```java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class ExplicitReactiveJwtDecoderConfig {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.audience}") String requiredAudience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder
                .withJwkSetUri(jwkSetUri)
                // Trust allowlist do server quyết định,
                // không lấy từ trường alg trong JWT.
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(requiredAudience)) {
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
                issuerAndTime,
                audience
            )
        );

        return decoder;
    }
}
```

`application.yml`:

```yaml
app:
  security:
    issuer: https://auth.example.test/realms/orders
    jwk-set-uri: https://auth.example.test/realms/orders/protocol/openid-connect/certs
    audience: orders-api
```

**Ý nghĩa từng lớp bảo vệ:**

1. `withJwkSetUri(jwkSetUri)`: key material đến từ endpoint tin cậy.
2. `jwsAlgorithm(RS256)`: token chỉ được kiểm theo thuật toán do API chọn; đừng tự tin `alg` header.
3. `JwtValidators.createDefaultWithIssuer(issuer)`: áp dụng default time-related validators cùng issuer validator.
4. `audience` custom validator: token phải dành cho `orders-api`.
5. `DelegatingOAuth2TokenValidator`: chỉ cho token đi qua nếu mọi điều kiện cần thiết đạt.
6. Sau decode, WebFlux HTTP authorization vẫn kiểm scope.

**Quan trọng:** Không đăng ký hai bean `ReactiveJwtDecoder` khác nhau từ hai phương án 8.1 và 8.2 mà không chọn rõ bean nào sẽ được dùng. Khi tự định nghĩa bean decoder, Boot auto-config có thể back off; các property `spring.security.oauth2.resourceserver.jwt.audiences` hay các defaults khác sẽ **không nhất thiết** tự thêm vào bean này.

### 8.3. Nếu issuer dùng ES256 hoặc RS512 thì sao?

Ví dụ là **RS256** vì nó phổ biến; không phải tất cả issuers đều dùng RS256. Cần thống nhất cryptographic algorithm được phép với AS và thực sự cấu hình decoder tương ứng.

Trong các builder hỗ trợ, có thể thêm thuật toán được cho phép bằng `jwsAlgorithm(...)`. Ví dụ chỉ minh họa ý định cấu hình:

```java
NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .jwsAlgorithm(SignatureAlgorithm.RS512)
        .build();
```

Điều này mở tập algorithms được chấp nhận; **chỉ làm khi thật sự muốn tin cả hai**. Không viết logic đọc `alg` từ token rồi cấp quyền “chọn thuật toán nào cũng được”. Với EC, cấu hình thuật toán/curve và key type tương ứng theo phiên bản Spring Security/Nimbus.

Không dùng `alg="none"`, không dùng thuật toán đối xứng như `HS256` với một RSA public key theo logic tự chế; đây là dạng algorithm confusion nguy hiểm. Key type và signature verification phải được thư viện cryptographic đã kiểm chứng thực thi.

### 8.4. Ngoài issuer và audience: token type/profile

JWT chứa `iss`/`aud` đúng vẫn có thể thuộc loại **ID Token** hoặc JWT dành cho một mục đích khác nếu issuer dùng chung keyset. Với access token profile RFC 9068, có những yêu cầu thêm như header `typ` và các claims bắt buộc theo profile. Một WebFlux API cần chọn rõ:

- Nó nhận **OAuth 2.0 JWT access tokens** theo profile nào?
- Nó có kiểm `typ=at+jwt` nếu contract yêu cầu?
- Claim nào mô tả OAuth client (`client_id`), actor hoặc delegated user?
- Token từ Authorization Code khác token Client Credentials ra sao?
- Có bắt buộc `azp`, `client_id` hoặc các claims domain-specific không?
- Những claims nào bắt buộc phải có với từng loại token?

Không tự cho rằng `JwtValidators.createDefaultWithIssuer(...)` thực hiện mọi validation của RFC 9068. Cấu hình token type và required claims có thể cần một validator/profile-aware decoder riêng, tương thích phiên bản Spring Security đang dùng.

---

## 9. Kịch bản dùng public key cố định thay vì JWKS

Có những hệ thống kết nối AS qua kênh không ổn định, một số lab nhỏ hoặc service có **một key được phân phối theo quy trình trust nội bộ**. Khi ấy có thể xây decoder với public RSA key tĩnh.

### 9.1. Cấu hình decoder bằng một RSAPublicKey

Ví dụ:

```java
package com.example.orders.security;

import java.security.interfaces.RSAPublicKey;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class FixedPublicKeyDecoderConfig {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(RSAPublicKey trustedKey) {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withPublicKey(trustedKey)
                .signatureAlgorithm(SignatureAlgorithm.RS256)
                .build();

        // PHẢI gắn issuer, audience, time và token-profile validators
        // theo hợp đồng API, tương tự phương án custom decoder trước.
        return decoder;
    }
}
```

Đoạn trên minh họa API builder, **chưa phải một decoder production hoàn chỉnh** vì chưa gắn issuer/audience validators. Có thể thêm:

```java
OAuth2TokenValidator<Jwt> validator =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(expectedIssuer),
        audienceValidator
    );
decoder.setJwtValidator(validator);
```

Trong đó `audienceValidator` kiểm tra token audience đúng API. Không copy code `withPublicKey` vào sản phẩm rồi quên những validators đó.

### 9.2. Public key được tin cậy lấy từ đâu?

Một public key không bí mật như private key, nhưng **nguồn phân phối và tính toàn vẹn** của nó phải được bảo vệ:

- Được kiểm chứng từ AS hoặc quy trình quản lý khóa nội bộ.
- Được phân phối qua config/artifact/secret management có provenance rõ.
- Không lấy key do JWT header/query parameter tự cung cấp.
- Không nhận key từ untrusted endpoint khi ứng dụng đang chạy.
- Có version, owner, quy trình rotation và rollback.

**Public key không phải secret, nhưng thay đổi public key trái phép có thể mở cửa cho attacker ký token giả bằng private key của họ.** Vì vậy quyền sửa trusted public key/config là một quyền an ninh quan trọng.

### 9.3. Trade-off của static key

| Lợi ích | Giới hạn |
|---|---|
| Không cần JWKS network fetch khi xử lý token. | Rotation phải triển khai/phân phối key mới theo quy trình. |
| Ít dependency và dễ vận hành trong lab. | Không tự chọn nhiều keys theo `kid` như JWKS decoder. |
| Có thể pin một key cụ thể theo provenance. | Key bị thu hồi cần rollout/cập nhật ngay; rủi ro token mới bị từ chối. |
| Dễ kiểm tra trust root trong cấu hình. | Không thích hợp khi AS có nhiều signing keys, tenants hoặc vòng đời rotation liên tục. |

Nếu AS thường xuyên rotate keys, **JWKS với overlap old/new keys** thường thuận tiện hơn. Static key có thể hợp lệ trong hệ kiểm soát chặt nhưng cần kế hoạch cutover và giám sát riêng.

---

## 10. Trust root: có gì trong JWKS và bằng chứng nào là đủ?

Một token signed bằng private key tương ứng với một public key được tải từ JWKS **mới chỉ vượt qua điều kiện chữ ký**. Một API an toàn cần ghép:

```text
Trusted issuer configuration
  AND trusted JWKS public key source
  AND allowed JWS algorithm
  AND valid signature
  AND iss == expectedIssuer
  AND aud contains requiredResource
  AND exp/nbf and required token claims pass
  AND token profile/type is accepted
  AND required scope/authority exists
  AND resource owner/tenant policy grants access
```

### 10.1. “Key có trong JWKS” không tự cho mọi token quyền admin

Giả sử issuer phát hành JWT:

```json
{
  "iss": "https://auth.example.test/realms/orders",
  "aud": ["orders-api"],
  "scope": "profile email",
  "sub": "alice-123"
}
```

Nếu chữ ký valid, token có thể được **authenticated** nhưng `GET /api/orders/42` vẫn phải bị 403 khi route yêu cầu `SCOPE_orders:read`. Và nếu token có scope, service vẫn phải kiểm quyền trên order cụ thể.

### 10.2. Không tin JWKS của issuer không được phép

Một sai lầm:

```java
// KHÔNG DÙNG: đọc issuer từ token chưa xác minh rồi tạo trust root.
String issuer = parseUnverifiedJwt(token).getIssuer();
ReactiveJwtDecoder decoder =
    ReactiveJwtDecoders.fromIssuerLocation(issuer);
```

Attacker có thể tự phát hành token với issuer do họ sở hữu, cung cấp JWKS do họ kiểm soát, và được ứng dụng chấp nhận nếu không có allowlist. Ngoài authentication bypass, việc gọi metadata/JWKS tới URL do token quyết định có thể gây **SSRF**.

Với multi-issuer, xây dựng một **allowlist issuer tường minh**, ví dụ theo tenant/provider đã onboard, rồi chọn decoder phù hợp. Chọn issuer từ token trước khi verify chỉ được dùng như một **hint để tìm trong allowlist**, không được trở thành quyết định tin tưởng issuer bất kỳ.

### 10.3. Không tự động trust public keys lấy qua redirect sang host khác

JWKS URL phải đến từ trusted config/metadata. Nếu HTTP client tự động follow redirect và mang theo credential hoặc điều hướng đến host không phù hợp, cần đánh giá rủi ro key injection, SSRF và availability.

JWKS thông thường là public keys, nên request lấy JWKS không cần client secret; **không gửi access token của API caller tới JWKS endpoint**. Đừng nhầm JWKS fetch với opaque-token introspection.

### 10.4. TLS và trust store

Với `https://.../jwks.json`, cần:

- Xác minh hostname/certificate chain theo trust store được chấp nhận.
- Không tắt certificate validation để “sửa” lỗi môi trường.
- Nếu dùng private CA, phân phối CA certificate có kiểm soát.
- Hạn chế outbound network đến issuer/JWKS hosts.
- Cấu hình network timeouts và response size limits phù hợp.
- Không log toàn bộ Bearer JWT khi JWKS fetch thất bại.

Một JWKS endpoint hợp lệ về mặt HTTP nhưng đã bị kiểm soát bởi attacker có thể phát public key của attacker. Bởi vậy xác thực TLS + DNS/proxy/config control là một phần của trust root, không phải tối ưu tùy ý.

---

## 11. Vòng đời của keys: `kid`, caching và rotation

Các Authorization Servers hiện đại thường thay private signing keys định kỳ hoặc khẩn cấp. Resource Server nên xử lý key rotation mà không cần xóa toàn bộ trạng thái ứng dụng hay dừng hoạt động, trong giới hạn cấu hình/thư viện.

### 11.1. Quy trình rotation lành mạnh

```mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant JWKS as Trusted JWKS Endpoint
    participant RS as WebFlux Resource Server

    AS->>JWKS: Publish old public key K1 + new public key K2
    RS->>JWKS: Load/refresh JWKS set
    JWKS-->>RS: K1, K2
    AS->>AS: Sign new access tokens with private key K2
    AS-->>RS: JWT header kid=K2
    RS->>RS: Verify signature using trusted public K2
    Note over AS,RS: Old JWTs signed K1 may remain valid until expiry
    AS->>JWKS: Retire K1 after allowed overlap window
```

Một kế hoạch rotation cơ bản:

1. **Publish public key mới** vào JWKS trước khi bắt đầu phát token ký bằng private key mới.
2. Duy trì **overlap** old/new public keys đủ để xác minh những JWT cũ còn hợp lệ.
3. Bắt đầu ký token mới bằng private key mới và `kid` mới.
4. Theo dõi số lượng `unknown kid`, JWKS refresh failures và JWT authentication failures.
5. Chỉ loại old public key khi hết thời gian cần chấp nhận những token cũ hoặc khi chính sách thu hồi yêu cầu.
6. Khi private key bị lộ, quy trình emergency rotation/revocation có thể cần từ chối cả những token chưa hết hạn; **JWKS chỉ thay key không tự thu hồi mọi token đã phát hành** trong mọi hệ thống.

### 11.2. JWKS caching không phải access-token cache

Một decoder có thể cache **public keys** để tránh tải JWKS qua mạng ở từng request. Điều này khác hoàn toàn với cache kết quả token authentication:

| Cache | Cái được cache | Rủi ro chính |
|---|---|---|
| **JWKS cache** | Public keys/KID metadata từ trusted endpoint. | Chậm nhận biết key mới hoặc key bị loại. |
| **JWT access token authorization cache** nếu do app tự tạo | Kết quả verification/claims/rights của một token. | Quyền đã bị thay đổi nhưng cached principal vẫn được tin. |
| **Introspection cache** (nếu opaque mode) | Metadata active/token từ AS. | Chậm nhận biết revocation/changes. |

**JWT Resource Server với cached JWKS vẫn xác minh JWT**; không vì cache public key mà tạo session cho client. Cơ chế rotation cần phù hợp cache TTL và cách decoder refresh khi gặp `kid` chưa có trong cache. Không mặc định “library luôn refresh ngay lập tức trong mọi lỗi” — behavior phụ thuộc cache configuration và phiên bản.

### 11.3. Unknown `kid` nên xử lý thế nào?

Nếu JWT có `kid=K99` nhưng trusted JWKS hiện chỉ có `K1` và `K2`:

- Decoder có thể thử refresh JWKS từ **trusted endpoint** theo chính sách.
- Nếu không tìm được key phù hợp, **không xác minh được chữ ký** → từ chối token.
- Không gọi một `jku` khác do JWT tự chỉ định để tìm key.
- Không tạm tắt signature validation.
- Không dùng “key đầu tiên trong JWKS” để verify bất chấp loại key/alg/policy.
- Nếu đã tới giới hạn refresh/rate limit, fail closed và log lỗi an toàn.

Với key rotation thật, `unknown kid` có thể là vấn đề đồng bộ giữa AS, CDN/JWKS cache và RS. Cần xác định TTL/caching headers, chứ không giải quyết bằng cách cho phép token không verify.

### 11.4. JWKS endpoint mất mạng

Khi RS đã có public key K1 trong cache, một JWT ký K1 có thể vẫn verify được trong một số implementation/configuration nếu cache còn hiệu lực. Một JWT ký bằng K2 chưa được cache có thể bị từ chối khi JWKS endpoint outage.

Vì vậy:

- Không diễn giải “đã có jwk-set-uri” là “không cần mạng”.
- Có timeout hữu hạn, retry giới hạn và circuit breaker/egress policy nếu cần.
- Không cho phép request đi qua vì AS/JWKS tạm mất mạng.
- Theo dõi p95/p99 JWKS fetch và cache misses, không chỉ 401 rates.
- Thiết kế outage drill với JWT ký key đã cache và JWT ký key mới.
- Không xóa cache keys đang hợp lệ một cách vô lý trong lúc issuer outage.

---

## 12. HTTP 401, 403 và lỗi phụ thuộc JWKS

Một Spring Security WebFlux Resource Server phân biệt authentication với authorization.

| Kịch bản | Bước từ chối | Kết quả điển hình |
|---|---|---|
| Không có Bearer token trên endpoint bảo vệ | Authentication chưa có | **401 Unauthorized**, `WWW-Authenticate: Bearer`. |
| Token sai chữ ký | JWT verification | **401**, có thể `invalid_token`. |
| Token hết hạn hoặc chưa tới `nbf` | JWT validation | **401**, có thể `invalid_token`. |
| Token sai `iss` | Issuer validator | **401**. |
| Token sai `aud` | Audience validator | **401**. |
| Header `alg` không nằm trong allowlist | JWS verification policy | **401**. |
| Key ID không có trong trusted JWKS | Signature verification | **401** nếu không verify được. |
| Token hợp lệ nhưng thiếu `SCOPE_orders:read` | HTTP/method authorization | **403 Forbidden**, có thể `insufficient_scope`. |
| Token hợp lệ, đủ scope nhưng khác owner/tenant | Object-level policy | **403** hoặc **404** theo hợp đồng API. |
| JWKS endpoint unavailable khi cần key | Dependency/authentication cannot complete | Không cấp authentication; HTTP status cụ thể phụ thuộc exception mapping. |
| Claim parser/decoder có bug | Code/integration failure | Có thể **5xx**; không nên giả vờ token hết hạn. |

Các status trên là hành vi thông thường, không phải bảo đảm cứng cho mọi custom handler. WebFlux sử dụng các reactive security handlers như `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler`, không phải servlet `AuthenticationEntryPoint`/`AccessDeniedHandler`.

### 12.1. Bearer challenge

Một HTTP 401 có thể là:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

JWT sai có thể tạo:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

JWT hợp lệ nhưng thiếu scope có thể tạo:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Theo RFC 6750, không phải mọi 401 **không có token** đều cần `error="invalid_token"`; điều kiện và error details phụ thuộc bối cảnh. Không log/raw echo JWT trong header hoặc error body.

### 12.2. Đừng dùng HTTP Basic hoặc web login fallback để cứu một JWT sai

Một API Bearer-only không nên chấp nhận web session/HTTP Basic để “tự động đăng nhập” khi JWT thất bại, trừ khi đó là một chính sách authentication **riêng, tường minh, đã được phê duyệt và kiểm thử**. Khả năng đăng nhập OIDC ở frontend không cho phép dùng ID Token hoặc session cookie làm API access token.

---

## 13. Kiểm thử WebFlux Security bằng `WebTestClient`

### 13.1. Endpoint dùng để quan sát principal

Một controller reactive đơn giản:

```java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class IdentityController {

    @GetMapping("/api/identity")
    public Mono<Map<String, String>> identity(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of("sub", jwt.getSubject()));
    }

    @GetMapping("/api/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }
}
```

Cần thêm route rule `GET /api/identity → authenticated()` trước `anyExchange().denyAll()`:

```java
.pathMatchers(HttpMethod.GET, "/api/identity").authenticated()
```

Controller trên chỉ phục vụ minh họa nhận JWT principal. Không trả toàn bộ JWT claims, scopes, secrets hoặc private identifiers trong production debug endpoint. Với opaque token principal type có thể khác; không cast mù `Jwt`.

### 13.2. Test HTTP authorization bằng `mockJwt()`

`spring-security-test` cung cấp `SecurityMockServerConfigurers.mockJwt()` cho WebFlux. Nó đưa một authenticated JWT mock vào test reactive security context:

```java
package com.example.orders.security;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class OrdersAuthorizationWebFluxTest {

    @Autowired
    WebTestClient client;

    @Test
    void noBearerTokenCannotUseProtectedEndpoint() {
        client.get().uri("/api/identity")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void mockedJwtWithReadAuthorityCanReadRoute() {
        client.mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders:read")))
            .get().uri("/api/orders/probe")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void mockedJwtWithoutReadAuthorityIsDenied() {
        client.mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders:write")))
            .get().uri("/api/orders/probe")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

**Điều kiện:** ứng dụng test phải có endpoint `GET /api/orders/probe`; service/fixture phải cho phép principal mock đọc nội dung tương ứng. Nếu không có controller đó, test 200 không thể chạy đúng như kỳ vọng. Các imports cần đúng bản Spring Boot đang sử dụng.

**Ranh giới quan trọng:** `mockJwt()` **bỏ qua `ReactiveJwtDecoder` và không kiểm tra JWS signature, issuer, audience, JWKS network hoặc algorithm allowlist**. Nó phù hợp để kiểm tra HTTP authorization. **Không dùng kết quả `mockJwt()` làm bằng chứng rằng `issuer-uri` hoặc `jwk-set-uri` đã được cấu hình đúng.**

### 13.3. Test JWT validation với decoder thật

Muốn kiểm chứng trust root, cần một bộ test khác:

1. Tạo **RSA test keypair K1**, không liên quan private key production.
2. Xuất **public JWK** K1 trong một JWKS test endpoint (HTTP server local hoặc HTTPS test server tùy môi trường).
3. Cấu hình `NimbusReactiveJwtDecoder.withJwkSetUri(...)` trỏ tới endpoint test đáng tin.
4. Ký access token bằng **private test key** K1, header `alg=RS256`, `kid=K1`.
5. Gửi Bearer JWT thật qua WebTestClient/embedded WebFlux server.
6. Kiểm tra correct issuer/audience/time thành công, sai conditions bị từ chối.

Không cần gọi Authorization Server production để chạy unit/integration tests; có thể dùng MockWebServer/WireMock hoặc server local. Với TLS test, dùng CA/cert riêng cho môi trường thử nghiệm, không tắt hostname verification trong production.

### 13.4. Ma trận test trust root

| JWT / cấu hình | Điều cần chứng minh | Kết quả kỳ vọng |
|---|---|---|
| Ký K1 đúng, issuer/audience/time đúng, RS256 cho phép | Decoder verify thật. | Authentication thành công. |
| Token bị sửa payload nhưng giữ signature cũ | Chống sửa claim. | 401. |
| JWT ký bằng private key không thuộc trusted JWKS | Trust source đúng. | 401. |
| Token có `kid=K999` không có trong JWKS | Unknown key không được trust. | 401 sau refresh policy nếu không tìm được key. |
| Token có `jku` trỏ tới attacker JWKS | Không chạy key-source theo untrusted header. | 401 nếu signature không hợp lệ theo JWKS đã cấu hình; không fetch attacker URL. |
| JWT có `alg=HS256` hoặc `none` | Algorithm allowlist. | 401. |
| JWT ký hợp lệ nhưng `iss` khác | Issuer validation. | 401. |
| JWT ký hợp lệ nhưng `aud=payments-api` | Audience validation. | 401. |
| JWT ký hợp lệ nhưng `exp` quá khứ | Timestamp validation. | 401. |
| JWT ký hợp lệ nhưng `nbf` ở tương lai | Timestamp validation. | 401. |
| ID Token thay access token | Token type/profile boundary. | Bị từ chối nếu access-token profile được thực thi. |
| JWT hợp lệ thiếu `SCOPE_orders:read` | HTTP authorization. | 403. |
| JWT hợp lệ đủ scope nhưng order thuộc Bob | Object authorization. | 403/404. |
| JWKS cũ K1, JWKS mới K1+K2 | Key rotation. | Token mới ký K2 xác minh được khi refresh keyset. |
| JWKS endpoint outage, key chưa cache | Fail-closed. | Không chấp nhận token chưa verify. |
| Issuer-only và metadata endpoint unavailable tại bootstrap | Startup coupling (tùy version). | Ghi nhận behavior thực; không cho phép trust khác. |
| Issuer+JWKS direct, metadata discovery unavailable | Startup independence khỏi metadata. | Không cần metadata để xác định JWK URL; cần key fetch khi decode. |

Không assert 401 thay cho mọi lỗi hạ tầng một cách máy móc; khi JWKS fetch thất bại có thể phát sinh 5xx tùy exception handler. Bất biến bảo mật cần chứng minh là **request không được cấp quyền từ một token chưa xác minh**.

### 13.5. Dùng `StepVerifier` để test decoder reactive trực tiếp

Khi test riêng `ReactiveJwtDecoder`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import reactor.test.StepVerifier;

class ReactiveJwtDecoderTest {

    private final ReactiveJwtDecoder decoder;

    ReactiveJwtDecoderTest(ReactiveJwtDecoder decoder) {
        this.decoder = decoder;
    }

    @Test
    void validTokenProducesVerifiedClaims() {
        String signedJwt = signedTestJwtForOrdersApi();

        StepVerifier.create(decoder.decode(signedJwt))
            .assertNext(jwt ->
                assertEquals("alice-123", jwt.getSubject()))
            .verifyComplete();
    }

    @Test
    void tokenWithWrongAudienceFails() {
        String signedJwt = signedTestJwtForPaymentsApi();

        StepVerifier.create(decoder.decode(signedJwt))
            .expectError()
            .verify();
    }

    // Hai helper tạo signed JWT test với private key fixture,
    // được triển khai trong bộ test thực tế.
    private String signedTestJwtForOrdersApi() {
        throw new UnsupportedOperationException("test fixture");
    }

    private String signedTestJwtForPaymentsApi() {
        throw new UnsupportedOperationException("test fixture");
    }
}
```

Đoạn này là **skeleton** minh họa `Mono<Jwt>`/`StepVerifier`. Trong test class thực tế, decoder cần được inject/khởi tạo qua setup JUnit hợp lệ; hai helper phải thực sự tạo JWT ký RSA/EC bằng test key. Không chạy nguyên snippet có `UnsupportedOperationException` rồi coi đó là test hoàn chỉnh. Test xác minh signature phải có một case JWT ký sai key hoặc payload bị sửa.

### 13.6. Không kiểm tra trust bằng cách Base64URL decode payload

Một test sai:

```java
String issuer = parseJwtPayloadWithoutVerify(token).get("iss");
assertEquals(expectedIssuer, issuer);
```

Chỉ chứng minh chuỗi JWT **tự khai** issuer giống kỳ vọng. Attacker hoàn toàn có thể tạo token tự khai `iss` đúng. Test thật phải đi qua **`ReactiveJwtDecoder.decode(...)` và JWS verification**.

---

## 14. Multi-issuer: một ứng dụng có thể tin nhiều nhà phát hành không?

Một WebFlux Resource Server có thể phục vụ nhiều tenants hoặc đối tác với nhiều issuers. Nhưng “đa issuer” không có nghĩa:

```text
Accept any JWT
  -> read unverified iss
  -> fetch that issuer's metadata/JWKS
  -> accept token if signature matches issuer it invented
```

Đây là anti-pattern vì attacker có thể dựng issuer và JWKS riêng.

### 14.1. Cách tư duy đúng

Giả sử chỉ có hai issuers đã onboard:

```text
https://idp-a.example.test/realms/orders
https://idp-b.example.test/realms/orders
```

Với từng issuer:

- Có policy trust riêng.
- Có metadata/JWKS URL được tin riêng.
- Có signing algorithms được phép.
- Có audience/resource binding đúng `orders-api`.
- Có token type/profile và claim mapping riêng.
- Có domain identity namespace (`iss` + `sub`) và tenant permissions.
- Có quy trình key rotation riêng.

Spring Security WebFlux hỗ trợ mô hình resolver chọn reactive authentication manager theo issuer được allowlist, chẳng hạn các API thuộc nhóm `JwtIssuerReactiveAuthenticationManagerResolver` trong các phiên bản phù hợp. Khi implement, hãy đảm bảo input issuer chỉ được dùng **chọn trong tập issuer đã tin**; không tạo decoder cho arbitrary URLs.

### 14.2. Cùng `sub` không phải cùng user

Issuer A có `sub=123` và issuer B cũng có `sub=123`; đây không mặc nhiên là một người. Khi lưu owner trong DB hoặc ánh xạ local account, cần namespace theo issuer hoặc ánh xạ internal user ID đã được kiểm soát.

### 14.3. Cùng một JWKS không tự nghĩa cùng issuer

Một Authorization Server có thể dùng cùng signing keys cho nhiều realms hoặc clients. Việc verify signature với public key chung **không hợp nhất** các issuer thành một domain tin cậy. Resource Server vẫn cần check `iss` và `aud` theo từng policy.

---

## 15. WebFlux reactive specifics: đừng vô tình block event loop

JWT verification bằng thuật toán RSA/EC và JWKS fetch có chi phí. Spring Security reactive decoder được thiết kế dùng API non-blocking khi có network IO phù hợp; customizations có thể phá tính reactive nếu thực hiện blocking I/O trên event loop.

### 15.1. Những điều cần tránh

```java
// KHÔNG DÙNG trong reactive authentication flow:
Mono<Jwt> decode(String token) {
    Jwt jwt = blockingHttpClient.getJwksAndVerify(token);
    return Mono.just(jwt);
}
```

Nếu gọi HTTP đồng bộ hoặc đọc file lớn trong một method chạy trên event-loop thread, request latency và throughput có thể giảm nghiêm trọng. Cũng không gọi `.block()` bên trong reactive authentication filter để chờ JWKS/introspection.

### 15.2. Phân biệt khởi tạo bean và xử lý request

Đọc một public key PEM nhỏ **một lần tại startup** để khởi tạo decoder có tính chất khác với đọc file/network blocking cho **mỗi request**. Nhưng startup dependency vẫn cần được đo và kiểm soát. Với `jwk-set-uri`, nên để thư viện reactive decoder sử dụng HTTP client/cache phù hợp, hoặc tùy chỉnh đúng extension để giữ semantics non-blocking.

### 15.3. Reactor Context cho principal

Trong WebFlux:

```java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(authentication -> authentication.getName());
}
```

Đây là minh họa lấy authentication từ **Reactor Context**, không dùng một biến static “last user”. Nếu dùng `@AuthenticationPrincipal Jwt` trong controller, framework thường inject JWT đã xác minh phù hợp; không tự decode raw JWT tại controller.

Nếu có async tasks, thread pools hoặc context changes, cần thiết kế propagation rõ để không rò principal của request khác.

---

## 16. Phòng tránh lỗi cấu hình thường gặp

### Lỗi 1 — Chỉ cấu hình `jwk-set-uri`, quên `iss`

Token ký đúng keyset nhưng `iss` không phải issuer dự kiến có thể vượt qua nếu issuer validator không được cấu hình. Thêm `issuer-uri` hoặc `JwtValidators.createDefaultWithIssuer(...)` trong decoder tự tạo.

### Lỗi 2 — Chỉ cấu hình `issuer-uri`, quên audience

Token khác API nhưng cùng issuer/keyset có thể được nhận. Thêm `audiences` hoặc audience validator theo token contract.

### Lỗi 3 — Nhận ID Token như access token

ID Token của OIDC client có thể ký bởi cùng keys. API phải kiểm đúng `aud` và access-token type/profile, không dựa vào `sub` hay chữ ký để gộp hai loại token.

### Lỗi 4 — Lấy JWKS URI từ JWT `jku`

Attacker có thể trỏ tới keyset do họ sở hữu. Chỉ dùng nguồn khóa đã được cấu hình/allowlist và HTTPS được xác thực.

### Lỗi 5 — Cho `alg` của JWT tự quyết định được phép dùng gì

Header JWS là dữ liệu chưa được xác minh. Decoder cần algorithm allowlist; không chấp nhận `none` hoặc algorithm confusion.

### Lỗi 6 — Hardcode một `kid` bất biến

AS rotation sang key mới khiến token hợp lệ bị từ chối. Thiết kế JWKS refresh và overlap; pin **trust source và algorithms**, không chỉ pin một key ID nếu issuer xoay vòng keys.

### Lỗi 7 — Dùng public key không kiểm provenance

Một public key tải từ host attacker vẫn verify được token attacker. Public key không bí mật nhưng **tính toàn vẹn của key source cực kỳ quan trọng**.

### Lỗi 8 — Nhầm reactive decoder với servlet decoder

WebFlux cần `ReactiveJwtDecoder`, `ServerHttpSecurity` và `SecurityWebFilterChain`. Đừng thêm `HttpSecurity`/`JwtDecoder` rồi nghĩ reactive requests đã được bảo vệ như dự kiến.

### Lỗi 9 — Viết bean decoder rồi quên validators

Khi tự định nghĩa `ReactiveJwtDecoder`, Boot có thể không tự thêm audience/issuer validators như với auto-configuration. Tự kiểm tra đầy đủ và test token sai issuer/audience.

### Lỗi 10 — Chấp nhận mọi issuer qua dynamic resolver

Đọc `iss` từ token chưa verify có thể dùng như hint **chỉ khi đối chiếu allowlist**. Không fetch keyset/metadata từ URL arbitrary do token cung cấp.

### Lỗi 11 — Kiểm tra signature nhưng không kiểm scope/owner

Một JWT signed đúng chỉ chứng minh một assertion của issuer. API vẫn phải áp dụng scope authorities, tenant/owner, ACL và business rules.

### Lỗi 12 — Xóa JWK cache khi issuer outage rồi cho fallback

Nếu không còn public key đáng tin, phải từ chối token chưa verify. Không “để hệ thống sẵn sàng” bằng cách tắt signature check hoặc tin unverified claims.

### Lỗi 13 — Test chỉ dùng `mockJwt()`

Mock JWT bỏ qua decoder. Cần signed-JWT integration tests và local JWKS server để test trust root thật.

### Lỗi 14 — Tin JWT từ HTTP query parameter

Bearer token nên gửi qua `Authorization` header, hạn chế query parameter vì rò trong logs, browser history và gateways. Cấu hình bearer extraction phải rõ, không cho nhiều kênh nhập token tùy ý.

### Lỗi 15 — Log raw JWT khi lỗi JWKS

JWT là credential Bearer và payload có thể chứa PII. Log reason code, issuer configuration ID, request ID, HTTP upstream status; không log Authorization header, token, private key hoặc nội dung nhạy cảm của JWKS.

---

## 17. Runbook khi ký token bằng key mới và API bắt đầu trả 401

Một sự cố phổ biến sau rotation:

```text
Yesterday:
  AS signs with K1
  JWKS contains K1
  Resource Server verifies K1 tokens

Today:
  AS signs with K2
  JWKS cache in RS still contains K1
  API receives JWT kid=K2
  Verification fails -> 401
```

Các bước điều tra:

1. **Xác nhận triệu chứng:** tỷ lệ Bearer 401 tăng, có liên quan `kid` mới, chỉ một issuer/region hay mọi nơi?
2. **Kiểm tra source JWKS được cấu hình:** `issuer-uri` và `jwk-set-uri` có trỏ đúng realm/tenant không? Không thay đường dẫn theo input JWT.
3. **Kiểm tra metadata công bố:** trusted JWKS có chứa K2 public key chưa? AS có publish key mới trước lúc ký không?
4. **Kiểm tra cache/CDN:** JWKS URL có trả response khác nhau theo node/region/cache layer không?
5. **Kiểm tra algorithms:** K2 có đúng key type, `use` và JWS algorithm mà decoder chấp nhận không?
6. **Kiểm tra issuer/audience:** token mới có `iss`/`aud` khác sau migration không? Không nới validator nếu không có hợp đồng.
7. **Kiểm tra TLS/network:** cert/hostname và outbound access tới JWKS có hợp lệ không?
8. **Kiểm tra failures khác:** token có thể hết hạn, sai `nbf`, bị issuer từ chối theo profile; không quy mọi 401 thành key rotation.
9. **Khôi phục theo chính sách:** sửa AS publish overlap, refresh JWKS an toàn hoặc rollback signing key; không bỏ signature check.
10. **Ngăn tái diễn:** staging rotation drill, metrics `unknown kid`/JWKS latency, alert trước khi AS cutover, rollback plan.

### 17.1. Khi private signing key bị lộ

Sự cố nghiêm trọng hơn rotation thông thường. Nếu private key K1 đã bị lộ, attacker có thể ký JWT giả bằng K1 khi Resource Server còn trust public key K1. Cần quy trình thu hồi key/giới hạn token acceptance theo chính sách, có thể yêu cầu **rút K1 khỏi JWKS/cache ngay** và chấp nhận ảnh hưởng tới token cũ.

Không chỉ “đợi token hết hạn” nếu threat model không chấp nhận. Phối hợp issuer, API owners, gateways và các Resource Servers sử dụng keyset, đồng thời kiểm tra revocation/incident response.

---

## 18. Checklist triển khai cấu hình tin cậy

Trước khi đưa reactive JWT Resource Server lên production:

| Hạng mục | Điều cần chốt |
|---|---|
| **Web stack** | Đúng WebFlux, `SecurityWebFilterChain`, `ServerHttpSecurity` và `ReactiveJwtDecoder`. |
| **Issuer** | `issuer-uri` chính xác với `iss` của token được phép. |
| **JWKS source** | `jwk-set-uri` lấy từ trusted metadata/config, HTTPS hợp lệ, không từ token header. |
| **Audience** | `orders-api` bắt buộc; không chấp nhận token phát cho client/API khác. |
| **Algorithm** | Chỉ RS256/ES256/... theo hợp đồng; không dynamic trust `alg`. |
| **Key rotation** | JWKS overlap, cache refresh/TTL, unknown `kid` và incident rollback. |
| **Token profile** | Access token, không nhầm ID Token, required claims/token type. |
| **Time claims** | `exp`/`nbf` và clock skew policy. |
| **HTTP policy** | Scope/authority rõ theo path/method; deny-by-default. |
| **Domain policy** | Owner/tenant/business authorization. |
| **Network safety** | TLS/hostname, egress allowlist, timeouts, bounded retries khi phù hợp. |
| **Startup coupling** | Biết issuer-only có cần metadata discovery khi bootstrap không. |
| **Custom decoder** | Tự gắn issuer/audience/required validators khi Boot auto-config back off. |
| **Reactive behavior** | Không block event loop trong custom authentication. |
| **Error semantics** | 401 token invalid, 403 insufficient scope, dependency failure fail-closed. |
| **Tests** | `mockJwt()` cho authorization; signed JWT + local JWKS cho signature/trust. |
| **Observability** | Correlation ID và mã lỗi; không log raw token, private key hoặc PII. |
| **Multi-issuer** | Chỉ issuer allowlist; namespace subject theo issuer. |

### 18.1. Một quyết định cấu hình thực dụng

Nếu Authorization Server hỗ trợ metadata discovery và môi trường chấp nhận phụ thuộc startup, **`issuer-uri`** thường là cấu hình ngắn gọn nhất. Nếu cần loại bỏ metadata discovery khỏi bootstrap mà vẫn giữ issuer binding, dùng **`issuer-uri + jwk-set-uri`** với audience phù hợp. Nếu dùng **decoder bean tùy chỉnh**, phải thiết lập đầy đủ validators vì không còn được dựa vào các giả định của Boot auto-configuration.

Nếu dùng **public key cố định**, chỉ nên khi có lý do vận hành rõ và quy trình rotation/revocation được tài liệu hóa.

---

## 19. Một bản đồ khái niệm để ghi nhớ

```mermaid
flowchart TD
    A["Trusted Resource Server configuration"] --> B["issuer-uri: expected issuer"]
    A --> C["jwk-set-uri: trusted key endpoint"]
    A --> D["audience: expected resource"]
    A --> E["JWS algorithm allowlist"]
    C --> F["JWKS public keys"]
    F --> G["Verify JWT signature"]
    E --> G
    B --> H["Validate iss"]
    D --> I["Validate aud"]
    G --> J{"Signature hợp lệ?"}
    H --> K{"Claims/profile hợp lệ?"}
    I --> K
    J -->|Không| R["Reject authentication"]
    K -->|Không| R
    J -->|Có| L["JWT verified + token validators"]
    K -->|Có| L
    L --> M["SCOPE_ authorities & reactive route policy"]
    M --> N["Owner/tenant/domain authorization"]
    N --> O["Permit hoặc deny theo policy"]
```

**Nhớ bốn khác biệt:**

1. **`issuer-uri` là nguồn nhận diện issuer**, không phải public key.
2. **`jwk-set-uri` là nơi lấy public keys đáng tin**, không phải bằng chứng audience.
3. **`kid` và `alg` là các trường lựa chọn kỹ thuật trong JWS header**, không phải quyền tự chỉ định trust root.
4. **JWT verify thành công chưa có nghĩa được truy cập mọi tài nguyên** — scope và owner/tenant còn cần kiểm.

---

## 20. Tài liệu tham khảo

- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): issuer metadata, JWKS, `ReactiveJwtDecoder` và HTTP authorization.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `ServerHttpSecurity`, `SecurityWebFilterChain` và cấu hình reactive.
- [Spring Security API — NimbusReactiveJwtDecoder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html): JWK set, public key builders và validators.
- [Spring Security API — ReactiveJwtDecoders](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/ReactiveJwtDecoders.html): tạo decoder từ issuer location.
- [Spring Security — Reactive Tests](https://docs.spring.io/spring-security/reference/reactive/test/index.html): `WebTestClient` và test security context.
- [Spring Boot — OAuth 2.0 Resource Server Properties](https://docs.spring.io/spring-boot/reference/web/spring-security.html): property bindings của Boot, tùy phiên bản.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517.html): cấu trúc JWK/JWK Set, `kty`, `kid` và key parameters.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html): JWS header, signature và thuật toán.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518.html): RS256, ES256 và các thuật toán JOSE.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html): issuer metadata, endpoints, JWKS URI.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): OIDC provider metadata discovery.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): mục đích và profile access token, tránh nhầm ID Token.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): issuer/audience, algorithm confusion và JWT trust boundaries.
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): Bearer request và `WWW-Authenticate` responses.

**Kết luận:** Khi cấu hình JWT Resource Server trên WebFlux, nên bắt đầu từ **issuer được tin**, xác định **JWKS URL đáng tin**, giới hạn **JWS algorithms**, kiểm tra **issuer/audience/thời hạn/token profile**, rồi mới ánh xạ scopes và kiểm tra quyền trên tài nguyên. `issuer-uri`, `jwk-set-uri` và public keys đóng vai trò khác nhau nhưng phải cùng tạo thành một **chuỗi tin cậy không phụ thuộc dữ liệu do client tự chỉ định**. Trong code reactive, hãy dùng `ReactiveJwtDecoder` và `SecurityWebFilterChain`, đồng thời kiểm thử chữ ký thật bằng signed JWT/JWKS thay vì chỉ mock authorities.
