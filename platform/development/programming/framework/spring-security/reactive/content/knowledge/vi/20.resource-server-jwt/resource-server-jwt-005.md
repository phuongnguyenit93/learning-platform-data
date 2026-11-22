# Xác minh chữ ký và kiểm tra iss, exp, nbf, aud trong Spring Security Reactive Resource Server JWT

> **Module:** Spring Security - reactive  
> **Chủ đề cha:** Resource Server JWT  
> **Bài học:** Xác minh chữ ký và kiểm tra `iss`, `exp`, `nbf`, `aud`  
> **Mục tiêu:** Hiểu khác biệt giữa *đọc* JWT và *xác thực* JWT; cấu hình decoder/validators đúng Spring WebFlux; chặn token giả mạo, sai issuer, hết hạn, chưa đến hiệu lực, sai audience; thực hành Java 17+ và test bằng RSA key pair ký thật.

## 1. Từ một JWT đến quyết định có cho truy cập hay không

JWT thường có dạng `header.payload.signature`, trong đó header và payload được mã hóa bằng Base64URL, **không phải mã hóa bảo mật nội dung**. Ai cũng có thể giải mã hai đoạn đầu. Vì vậy thấy chuỗi `"role":"admin"` hoặc `"sub":"alice"` trong payload không đồng nghĩa người gửi thực sự có quyền đó.

Ví dụ payload:

~~~json
{
  "iss": "https://idp.example.com/realms/acme",
  "sub": "user-42",
  "aud": ["reports-api"],
  "iat": 1762500000,
  "nbf": 1762500000,
  "exp": 1762503600,
  "scope": "reports.read"
}
~~~

Thời gian trong ví dụ chỉ minh họa **Unix seconds**, không phải token đang còn hạn vào ngày bạn đọc. Resource Server phải quyết định theo **đồng hồ hiện tại**, issuer/audience đã cấu hình và chữ ký được verify bằng khóa tin cậy.

Một JWT được chấp nhận khi tất cả điều kiện phù hợp:

~~~text
Accept request only if:
  (1) Bearer token có cú pháp phù hợp
  (2) JWS signature hợp lệ với trusted public key
  (3) alg được allowlist và không phải alg=none
  (4) iss khớp trusted issuer
  (5) exp còn hiệu lực theo policy/clock skew
  (6) nbf không ở tương lai vượt skew (nếu claim có)
  (7) aud chứa ID chính xác của API hiện tại
  (8) scope/role đủ cho route, quyền owner/tenant đủ cho object
Otherwise: fail closed
~~~

Chữ ký hợp lệ nhưng `aud` là service khác vẫn phải bị từ chối. Chữ ký không hợp lệ nhưng payload có mọi claim đẹp cũng phải bị từ chối.

## 2. Vai trò của Authorization Server, Client và Resource Server

~~~mermaid
flowchart TD
    I["Trusted Authorization Server / IdP"] -->|"Ký access token bằng private key"| C["Client"]
    I -->|"Công bố JWKS public keys"| R["WebFlux Resource Server"]
    C -->|"Authorization: Bearer access-token"| R
    R --> D{"Verify JWS signature + alg?"}
    D -->|"Không"| X["401 invalid_token"]
    D -->|"Có"| V{"iss + exp + nbf + aud đúng?"}
    V -->|"Không"| X
    V -->|"Có"| A["JwtAuthenticationToken + GrantedAuthorities"]
    A --> P{"Scope / owner / tenant có quyền?"}
    P -->|"Không"| F["403 hoặc 404 che object, tùy API policy"]
    P -->|"Có"| H["Controller / domain service"]
~~~

- **Authorization Server** nắm private signing key; có thể công bố public keys qua JSON Web Key Set (JWKS).
- **Client** nhận access token bằng OAuth2 flow thích hợp rồi gửi nó đến resource server qua HTTPS.
- **Resource Server** xác minh JWT, issuer, time, audience và authorization. Nó **không tự ký/cấp token** chỉ vì đã bật `oauth2ResourceServer().jwt()`.
- **Authentication** trả lời token có thể đại diện một subject hợp lệ cho API hay không. **Authorization** trả lời subject đó được làm gì và trên object nào.

Đừng nhầm OAuth2 Login Client (browser redirect, WebSession) với JWT Resource Server (nhận Bearer ở từng request). Cũng đừng dùng ID Token OIDC như access token: ID Token có audience hướng tới OIDC client, không nhất thiết là API của bạn.

## 3. JWT, JWS, JWE, alg và kid

| Từ | Ý nghĩa | Hệ quả |
| --- | --- | --- |
| JWT | Định dạng claim set | Không tự bảo đảm token đã được ký |
| JWS | JSON Web Signature | Có protected header, payload, signature |
| JWE | JSON Web Encryption | Payload được mã hóa; ví dụ này không giải mã JWE |
| `alg` | Thuật toán JWS, ví dụ RS256 | Chỉ chấp nhận thuật toán được server allowlist |
| `kid` | Key identifier | Giúp tra khóa trong JWKS **đáng tin** |
| `typ` | Loại token trong header | Có thể cần validate profile access token |
| `iss` | Issuer | Phải thuộc issuer tin cậy và khớp chính xác |
| `aud` | Audience | Phải chứa chính API resource server |
| `scope`/`scp` | Quyền hành động | Thường được map thành authorities `SCOPE_...` |

Header JWT cũng là **input từ caller trước verification**. Không vì token nói `kid=abc` mà tin một key lấy từ URL tùy ý. Không dùng `jku`/`x5u` trong token làm địa chỉ HTTP để tự fetch public key, vì attacker có thể ép server truy cập host riêng hoặc nội bộ (SSRF).

## 4. Xác minh chữ ký: public key tin cậy chứ không phải payload

Với `RS256`, IdP ký JWS bằng RSA private key; Resource Server verify bằng RSA public key tương ứng.

~~~text
IdP: base64url(header) + "." + base64url(payload)
                       |
                 RS256 private key
                       |
                  JWS signature
                       |
             header.payload.signature

Resource Server: header.payload + signature
                        |
              trusted public key (JWKS)
                        |
            Verify signature and allowed alg
                        |
            Pass or reject before trusting claims
~~~

Bên nhận **không cần private key** của IdP. Không copy private signing key vào Resource Server hoặc Git. Khi `alg` ghi `none`, token không có JWS signature được chấp nhận; phải từ chối trong policy ký bắt buộc. Khi IdP chuyển từ RS256 sang ES256/PS256, thay đổi allowlist dựa trên hợp đồng của IdP và test; không cho token tự chọn bất kỳ thuật toán nào.

**Algorithm confusion:** Nếu ứng dụng tự lập trình code kiểm tra chữ ký và nhầm RSA public key thành HMAC secret, có thể xuất hiện lỗ hổng chấp nhận token giả. Dùng thư viện JOSE/JWT đã được bảo trì và pin algorithm phù hợp.

## 5. JWKS, kid và key rotation

JWKS là một JSON chứa danh sách JWK public keys, ví dụ cấu trúc minh họa:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "illustrative-rsa-modulus",
      "e": "AQAB"
    }
  ]
}
~~~

Chuỗi `n` ở trên chỉ là minh họa; không phải public key thực có thể verify. Trong ứng dụng thật, JWKS do IdP đáng tin công bố qua **HTTPS** và có key material đúng thuật toán.

Decoder dùng `kid` (khi có) để chọn khóa phù hợp từ tập keys tin cậy, kiểm tra JWS signature, rồi mới xác thực claims. Với key rotation, IdP có thể công bố cả public key cũ và mới một thời gian để các JWT chưa hết hạn tiếp tục verify. Nimbus/Spring quản lý retrieval/cache theo cấu hình và phiên bản; không đoán TTL cố định khi chưa kiểm tra.

Các trường hợp phải **fail closed**: JWKS URI không tin cậy; TLS certificate sai; `kid` không có khóa tương ứng; signature sai; key type/alg không phù hợp; JWKS outage khi decoder không có key tin cậy cần thiết. Không fallback sang decode không verify.

## 6. Kiểm tra iss — đúng nhà phát hành

`iss` chỉ issuer của JWT, ví dụ `https://idp.example.com/realms/acme`. Resource Server phải so sánh với giá trị trusted configuration, **không so substring**. Hai issuer khác path/tenant có thể dùng cùng hostname nhưng **không** tương đương.

| Token iss | Trusted issuer | Kết quả |
| --- | --- | --- |
| `https://idp.example.com/realms/acme` | Cùng URI | Có thể tiếp tục |
| `https://idp.example.com/realms/other` | acme | Từ chối |
| `http://idp.example.com/realms/acme` | https | Từ chối |
| Thiếu iss | acme | Từ chối theo issuer validator |

Trong Spring Security, `JwtValidators.createDefaultWithIssuer(issuer)` cung cấp issuer validation kết hợp timestamp validation mặc định. Nếu bạn tự khai báo `ReactiveJwtDecoder` Bean từ JWKS URI nhưng không gắn issuer validator, không thể mặc định Boot sẽ tự chèn issuer check vào custom Bean.

**Multi-issuer:** không lấy chuỗi `iss` chưa xác thực rồi tự download metadata/JWKS từ URL đó. Dùng allowlist những issuer đã được tổ chức phê duyệt, ánh xạ đúng issuer → decoder, chống SSRF và token mix-up.

## 7. Kiểm tra exp — thời hạn kết thúc

`exp` là NumericDate (số giây Unix) chỉ thời điểm JWT **không còn được phép chấp nhận**, có thể áp dụng leeway/clock skew nhỏ để bù đồng hồ lệch.

~~~text
server time: 12:00 UTC
exp:         11:45 UTC   => expired, reject
exp:         12:10 UTC   => còn hạn, tiếp tục kiểm tra claims khác
~~~

Spring Security dùng `JwtTimestampValidator` và mặc định có clock skew nhỏ (tài liệu nêu thường 60 giây). Skew không phải giấy phép dùng token đã hết hạn nhiều phút/giờ. Đồng hồ các nodes/IdP phải đồng bộ NTP, không giải lỗi bằng cách nới skew quá rộng.

**JWT RFC coi `exp` là optional**, nhưng API có thể chọn policy bắt buộc token có expiration. Bài lab thêm `ExpirationRequiredValidator` để chặn token thiếu exp — một chính sách tăng cường minh bạch, không phải tuyên bố rằng JWT specification bắt buộc mọi token có exp.

Đừng nhầm `iat` (issued at) với exp. Một token ghi iat gần hiện tại vẫn có thể bị reject vì signature/issuer/aud sai.

## 8. Kiểm tra nbf — thời hạn bắt đầu

`nbf` (“not before”) chỉ mốc token **chưa được dùng trước thời điểm đó**. Ví dụ bây giờ 12:00 UTC, `nbf` là 13:00 UTC thì decoder phải từ chối dù `exp` là 14:00 UTC và chữ ký đúng.

| Server now | nbf | Xử lý |
| --- | --- | --- |
| 12:00 | 11:50 | Đã đến hiệu lực |
| 12:00 | 13:00 | Chưa hiệu lực, từ chối |
| 12:00 | Không có claim | RFC cho phép; nếu profile yêu cầu cần custom presence validator |

JWT RFC không bắt buộc `nbf` trong mọi token. Lab dùng default timestamp validator **đánh giá nbf khi có**, không yêu cầu claim phải hiện diện. Hệ thống nào bắt buộc nbf phải viết validator presence rõ ràng và test missing nbf.

**Không hoán đổi nbf với exp:** nbf là giới hạn bên trái, exp là giới hạn bên phải của khoảng hiệu lực. Các token future-dated hoặc clock skew sai có thể dẫn đến 401 trên một số nodes; kiểm tra server time và issuer time trước khi nới security policy.

## 9. Kiểm tra aud — token đúng API

`aud` định danh resource/API được nhận token; có thể biểu diễn là string hoặc array trong JSON, Spring JWT API thường cung cấp `jwt.getAudience()` dạng danh sách.

Ví dụ:

~~~json
{
  "iss": "https://idp.example.com/realms/acme",
  "aud": ["reports-api", "analytics-api"],
  "scope": "reports.read"
}
~~~

Nếu API hiện tại có ID `reports-api`, token có thể tiếp tục qua audience validation. Nếu audience chỉ là `billing-api`, phải reject, kể cả hai APIs dùng cùng issuer và signature vẫn hợp lệ.

**Chính sách đúng:** dùng so sánh *exact membership* `jwt.getAudience().contains("reports-api")`. Không dùng substring như `aud.contains("report")`; không lấy expected audience từ request header; không bỏ qua aud vì token “đã ký bởi IdP chúng ta tin”.

**Audience khác scope:** aud nói **gửi cho ai**; scope nói **được làm gì**. Token đúng aud nhưng thiếu `reports.read` thường nhận 403 tại route yêu cầu `SCOPE_reports.read`. Token sai aud nhận 401 từ authentication, không nên chờ đến authorization layer.

## 10. Thứ tự xử lý request trong Spring Security Reactive

~~~mermaid
sequenceDiagram
    participant Client
    participant Security as WebFlux Security
    participant Decoder as NimbusReactiveJwtDecoder
    participant JWKS as Trusted JWKS
    participant Controller
    Client->>Security: GET /api/reports + Authorization Bearer
    Security->>Decoder: decode(token)
    Decoder->>JWKS: Fetch/cache keys khi cần
    JWKS-->>Decoder: Trusted public JWK set
    Decoder->>Decoder: Verify signature & algorithm
    Decoder->>Decoder: Validate iss/exp/nbf/aud
    alt invalid
        Decoder-->>Security: JwtException
        Security-->>Client: 401 invalid_token
    else valid
        Decoder-->>Security: Jwt verified
        Security->>Security: Map scope to SCOPE_...
        alt insufficient scope
            Security-->>Client: 403 forbidden
        else allowed
            Security->>Controller: @AuthenticationPrincipal Jwt
            Controller-->>Client: 200 JSON
        end
    end
~~~

Các tên API:
- `ServerBearerTokenAuthenticationConverter` lấy Bearer token từ HTTP request.
- `JwtReactiveAuthenticationManager` gọi `ReactiveJwtDecoder`.
- `NimbusReactiveJwtDecoder` xác minh JWS và giải mã claims.
- `JwtValidators` + `OAuth2TokenValidator<Jwt>` kiểm tra điều kiện.
- `JwtAuthenticationToken` thể hiện Authentication sau khi thành công.
- `ReactiveJwtAuthenticationConverter` và default authority mapping có thể chuyển scope thành `SCOPE_...`.

Không cho controller kiểm tra một payload JWT được Base64 decode thô rồi tự đưa ra quyền. Chỉ sử dụng `Jwt` đã đi qua decoder/validators hoặc Authentication được framework xác thực.

## 11. Cấu hình nhanh bằng Spring Boot properties

Khi IdP hỗ trợ issuer discovery, cấu hình tối giản:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/acme
~~~

Spring Security Reactive có thể discovery JWKS, xác minh signature, issuer và thời gian. **Không mặc định aud của API đã được kiểm tra** trong mọi phiên bản/cấu hình chỉ vì có issuer-uri. Có thể dùng Boot audiences property nếu version hỗ trợ hoặc custom audience validator.

Để xác định JWKS URI từ config và tránh network discovery tại startup trong cấu hình phù hợp:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/acme
          jwk-set-uri: https://idp.example.com/realms/acme/protocol/openid-connect/certs
~~~

Cấu hình thực phải lấy đúng trusted issuer/JWKS từ tài liệu của IdP, dùng HTTPS và có audience policy. Nếu tự viết custom decoder Bean, việc Boot tự cấu hình Bean theo properties có thể bị override; hãy giữ lại validators issuer/aud/time theo code.

## 12. Project Java 17+ / Maven

Bài lab dùng Spring Boot `3.3.13` làm mốc minh họa Spring Security 6.x. Dòng Boot 3.3 đã hết hỗ trợ OSS, nên production mới phải nâng lên bản còn được hỗ trợ và chạy lại tests. Ví dụ gồm app WebFlux Resource Server và hai loại tests:

~~~text
jwt-validation-reactive/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/jwt/
    │   │   ├── JwtApplication.java
    │   │   ├── JwtSecurityConfig.java
    │   │   └── ReportsController.java
    │   └── resources/application.yml
    └── test/java/demo/jwt/
        ├── JwtCryptographicTest.java
        └── JwtRouteTest.java
~~~

### 12.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>jwt-validation-reactive</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <properties>
    <java.version>17</java.version>
  </properties>
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
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Chọn `spring-boot-starter-oauth2-resource-server` để nhận Bearer/JWT, không phải OAuth2 Login starter. Không thêm `spring-boot-starter-web` vì đây là WebFlux, không phải Servlet MVC.

### 12.2. JwtApplication.java

~~~java
package demo.jwt;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JwtApplication {
    public static void main(String[] args) {
        SpringApplication.run(JwtApplication.class, args);
    }
}
~~~

### 12.3. application.yml

~~~yaml
server:
  port: 8080

lab:
  jwt:
    issuer: ${JWT_ISSUER:https://issuer.example.invalid/realms/demo}
    jwks-uri: ${JWT_JWKS_URI:https://issuer.example.invalid/realms/demo/protocol/openid-connect/certs}
    audience: ${JWT_AUDIENCE:reports-api}
~~~

`.invalid` là placeholder **không có server thật**. Các unit tests dùng RSA key pair nội bộ và WebTestClient mock authentication nên không phải liên hệ IdP. Để dùng HTTP Bearer token thật, đặt `JWT_ISSUER`, `JWT_JWKS_URI` và `JWT_AUDIENCE` đúng theo IdP và Resource Server của bạn.

Không cho caller tự truyền JWKS URL hoặc issuer để decoder tự gọi mạng.

## 13. JwtSecurityConfig.java — signature, iss, exp, nbf, aud

File `src/main/java/demo/jwt/JwtSecurityConfig.java`:

~~~java
package demo.jwt;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class JwtSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .requestCache(ServerHttpSecurity.RequestCacheSpec::disable)
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${lab.jwt.issuer}") String issuer,
            @Value("${lab.jwt.jwks-uri}") String jwksUri,
            @Value("${lab.jwt.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwksUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> validator =
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                new AudienceValidator(audience),
                new ExpirationRequiredValidator()
            );
        decoder.setJwtValidator(validator);
        return decoder;
    }
}

final class AudienceValidator implements OAuth2TokenValidator<Jwt> {
    private final String expected;

    AudienceValidator(String expected) {
        this.expected = expected;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience() != null
                && jwt.getAudience().contains(expected)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token", "Wrong JWT audience", null));
    }
}

final class ExpirationRequiredValidator
        implements OAuth2TokenValidator<Jwt> {

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getExpiresAt() != null) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token", "exp is required", null));
    }
}
~~~

**Vì sao cấu hình như vậy?**

1. `withJwkSetUri(jwksUri)` lấy public keys từ JWKS **được admin cho phép**, không lấy khóa từ JWT tùy ý. Phần ký của IdP vẫn dùng private key ở IdP.
2. `jwsAlgorithm(SignatureAlgorithm.RS256)` pin thuật toán ký theo hợp đồng test. Nếu IdP thật chọn ES256/PS256, thay bằng allowlist đúng và kiểm thử.
3. `JwtValidators.createDefaultWithIssuer(issuer)` kiểm tra đúng issuer và timestamp exp/nbf.
4. `AudienceValidator` thêm aud vì API phải nhận đúng token **dành cho reports-api**.
5. `ExpirationRequiredValidator` là yêu cầu riêng của API: không chấp nhận token không có exp. Trong JWT RFC, exp optional; bài lab chủ động đặt policy chặt hơn.
6. Không yêu cầu nbf phải hiện diện, nhưng nếu có thì timestamp validator phải xét not-before và clock skew.
7. `NoOpServerSecurityContextRepository` và tắt form login/HTTP Basic làm ví dụ trở thành **header-only JWT API**, không dựa vào WebSession cookie để xác thực.
8. CSRF disable **chỉ thích hợp với header-only Bearer API không chấp nhận credentials được browser auto-send**. Nếu API dùng cookie JWT/session/Basic cùng chain, phải xem lại chính sách CSRF.
9. `hasAuthority("SCOPE_reports.read")` chỉ xác minh quyền route, không tự kiểm tra owner/tenant.
10. `anyExchange().denyAll()` chặn routes chưa được khai báo.

**Điểm dễ sai:** Nếu bạn tự tạo `ReactiveJwtDecoder` Bean, đừng tự giả định mọi defaults của Boot vẫn được áp dụng sau đó. Hãy compose issuer/timestamp/audience policies tường minh như code và viết negative tests.

## 14. ReportsController.java — chỉ lấy subject đã xác thực

File `src/main/java/demo/jwt/ReportsController.java`:

~~~java
package demo.jwt;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReportsController {

    @GetMapping("/public/health")
    public Mono<Map<String, String>> health() {
        return Mono.just(Map.of("status", "up"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of("subject", jwt.getSubject()));
    }

    @GetMapping("/api/reports")
    public Mono<Map<String, String>> reports() {
        return Mono.just(Map.of(
            "report", "Visible to reports.read scope"));
    }
}
~~~

Khi access token đúng issuer/times/audience/chữ ký và đủ scope, `GET /api/reports` trả JSON có khóa `report`. Controller **không** nhận raw JWT do caller tự parse. Không log hoặc trả `jwt.getTokenValue()` ra JSON. Với dữ liệu thực, phải thêm kiểm tra owner, tenant, domain policy và database authorization để chống BOLA/IDOR.

## 15. Hai loại kiểm thử bắt buộc không thể thay nhau

**Nhóm A — cryptographic/claims tests:** tạo cặp khóa RSA tạm thời, ký JWT thật bằng `NimbusJwtEncoder`, giải mã/verify bằng `NimbusReactiveJwtDecoder.withPublicKey(...)`. Test cả token hợp lệ và chữ ký giả; test **issuer sai, expired, nbf tương lai, aud sai/missing, exp missing**. Không cần IdP hoặc HTTP network.

**Nhóm B — WebTestClient security tests:** dùng `mockJwt()` để xác nhận các route trả 401/403/200 khi có hoặc không có Authentication và scope. Đây là test authorization, **không** gọi JWT decoder; không dùng mockJwt để tuyên bố chữ ký, exp, nbf, iss, aud đã được xác minh.

Nhóm A dùng pinned test public key; production dùng JWKS. Cần bài integration test thứ ba nếu muốn chứng minh retrieval/rotation qua JWKS HTTPS. Bài học sẽ nêu rõ giới hạn, không nhập nhằng kết quả.

## 16. JwtCryptographicTest.java — ký JWT bằng RSA riêng của test

File `src/test/java/demo/jwt/JwtCryptographicTest.java`:

~~~java
package demo.jwt;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import reactor.test.StepVerifier;

class JwtCryptographicTest {
    static final String ISSUER =
        "https://idp.example.invalid/realms/demo";
    static final String AUDIENCE = "reports-api";

    private JwtEncoder encoder;
    private NimbusReactiveJwtDecoder decoder;

    private KeyPair keyPair() throws Exception {
        KeyPairGenerator g = KeyPairGenerator.getInstance("RSA");
        g.initialize(2048);
        return g.generateKeyPair();
    }

    private JwtEncoder encoderFor(KeyPair pair) {
        RSAKey signingKey =
            new RSAKey.Builder((RSAPublicKey) pair.getPublic())
                .privateKey((RSAPrivateKey) pair.getPrivate())
                .keyID("test-key")
                .build();

        JWKSource<SecurityContext> source =
            new ImmutableJWKSet<>(new JWKSet(signingKey));

        return new NimbusJwtEncoder(source);
    }

    @BeforeEach
    void setUp() throws Exception {
        KeyPair trustedKeys = keyPair();
        encoder = encoderFor(trustedKeys);
        decoder = NimbusReactiveJwtDecoder
            .withPublicKey((RSAPublicKey) trustedKeys.getPublic())
            .build();

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                new AudienceValidator(AUDIENCE),
                new ExpirationRequiredValidator()));
    }

    private String signed(
            JwtEncoder signingEncoder,
            String issuer,
            List<String> audience,
            Instant notBefore,
            Instant expiresAt) {

        Instant now = Instant.now();
        Instant issuedAt =
            expiresAt != null && expiresAt.isBefore(now)
                ? now.minusSeconds(7200)
                : now;

        JwtClaimsSet.Builder claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("alice")
            .audience(audience)
            .issuedAt(issuedAt)
            .claim("scope", "reports.read");

        if (notBefore != null) {
            claims.notBefore(notBefore);
        }
        if (expiresAt != null) {
            claims.expiresAt(expiresAt);
        }

        JwsHeader header = JwsHeader
            .with(SignatureAlgorithm.RS256)
            .keyId("test-key")
            .build();

        return signingEncoder.encode(
            JwtEncoderParameters.from(header, claims.build()))
            .getTokenValue();
    }

    private String validToken() {
        Instant now = Instant.now();
        return signed(encoder, ISSUER, List.of(AUDIENCE),
            now.minusSeconds(10), now.plusSeconds(600));
    }

    @Test
    void validSignatureAndAllClaimsPass() {
        StepVerifier.create(decoder.decode(validToken()))
            .assertNext(jwt -> {
                assertEquals("alice", jwt.getSubject());
                assertEquals(ISSUER, jwt.getIssuer().toString());
                assertTrue(jwt.getAudience().contains(AUDIENCE));
            })
            .verifyComplete();
    }

    @Test
    void signatureFromDifferentPrivateKeyFails() throws Exception {
        JwtEncoder attacker = encoderFor(keyPair());
        Instant now = Instant.now();
        String forged = signed(attacker, ISSUER, List.of(AUDIENCE),
            now.minusSeconds(10), now.plusSeconds(600));

        StepVerifier.create(decoder.decode(forged))
            .expectError(JwtException.class)
            .verify();
    }

    @Test
    void wrongIssuerFailsWithValidSignature() {
        Instant now = Instant.now();
        String bad = signed(encoder,
            "https://idp.example.invalid/realms/another",
            List.of(AUDIENCE),
            now.minusSeconds(10), now.plusSeconds(600));

        StepVerifier.create(decoder.decode(bad))
            .expectError(JwtException.class)
            .verify();
    }

    @Test
    void expiredTokenFailsWithValidSignature() {
        Instant now = Instant.now();
        String expired = signed(encoder, ISSUER, List.of(AUDIENCE),
            now.minusSeconds(7100), now.minusSeconds(600));

        StepVerifier.create(decoder.decode(expired))
            .expectError(JwtException.class)
            .verify();
    }

    @Test
    void futureNbfFailsWithValidSignature() {
        Instant now = Instant.now();
        String premature = signed(encoder, ISSUER, List.of(AUDIENCE),
            now.plusSeconds(3600), now.plusSeconds(7200));

        StepVerifier.create(decoder.decode(premature))
            .expectError(JwtException.class)
            .verify();
    }

    @Test
    void wrongAudienceFailsWithValidSignature() {
        Instant now = Instant.now();
        String bad = signed(encoder, ISSUER, List.of("billing-api"),
            now.minusSeconds(10), now.plusSeconds(600));

        StepVerifier.create(decoder.decode(bad))
            .expectError(JwtException.class)
            .verify();
    }

    @Test
    void absentAudienceFails() {
        Instant now = Instant.now();
        String bad = signed(encoder, ISSUER, List.of(),
            now.minusSeconds(10), now.plusSeconds(600));

        StepVerifier.create(decoder.decode(bad))
            .expectError(JwtException.class)
            .verify();
    }

    @Test
    void missingExpirationFailsUnderLabPolicy() {
        Instant now = Instant.now();
        String bad = signed(encoder, ISSUER, List.of(AUDIENCE),
            now.minusSeconds(10), null);

        StepVerifier.create(decoder.decode(bad))
            .expectError(JwtException.class)
            .verify();
    }
}
~~~

**Điểm then chốt của 8 tests:**
- Một private key khác không giả mạo được token với các claims hợp lệ; chữ ký phải khớp **trusted public key**.
- Một token được ký đúng private key vẫn không được chấp nhận nếu `iss`/`aud`/`exp`/`nbf` vi phạm.
- Token thiếu exp bị chặn bởi policy bổ sung.
- Test key pair được sinh ngẫu nhiên, không tải JWKS, không dùng private key thật của IdP.

**Lưu ý:** các thời gian test cách nhau hàng trăm hoặc hàng nghìn giây để tránh flake với clock skew 60 giây. Không viết exp gần `Instant.now()` từng mili-giây rồi khẳng định kết quả tất định.

## 17. JwtRouteTest.java — WebFlux authentication và scope

File `src/test/java/demo/jwt/JwtRouteTest.java`:

~~~java
package demo.jwt;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class JwtRouteTest {

    @Autowired
    WebTestClient client;

    @Test
    void healthIsPublic() {
        client.get().uri("/public/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("up");
    }

    @Test
    void missingBearerGets401() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void mockedJwtPrincipalMayReadProfile() {
        client.mutateWith(mockJwt().jwt(jwt ->
                jwt.subject("alice")))
            .get().uri("/api/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("alice")
            .jsonPath("$.access_token").doesNotExist();
    }

    @Test
    void wrongScopeGets403() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void reportsReadScopeGets200() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.report").exists();
    }

    @Test
    void unknownRouteIsDenied() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read")))
            .get().uri("/api/admin/debug")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

**Sáu test này chỉ kiểm tra HTTP security:** public route, 401 khi thiếu token, mock principal, 403 khi thiếu scope, 200 khi đúng scope, deny unknown route.

`mockJwt()` tạo Authentication cho WebTestClient **mà không gọi ReactiveJwtDecoder**. Một mockJwt trong test có thể có header `alg=none` mà vẫn được cấp Authentication do cơ chế mock; điều này **không** chứng minh production decoder chấp nhận unsigned JWT. Khi kiểm tra chữ ký/claims phải dùng signed JWT thật và decoder như mục 16.

## 18. Chạy Maven và quan sát HTTP

Tại thư mục chứa `pom.xml`:

~~~bash
mvn clean test
~~~

Bộ ví dụ có **8 cryptographic tests + 6 HTTP security tests = 14 JUnit tests**. Kỳ vọng chúng được chạy trong Java 17+ với Spring Boot 3.3.13 khi dependencies hoạt động đúng. Không có stdout nghiệp vụ cố định; Maven/JUnit report thay đổi theo môi trường. Bài không tuyên bố đã chạy Maven trên máy người đọc.

Khởi động ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Request public:

~~~bash
curl -i "http://localhost:8080/public/health"
~~~

Expected JSON body:

~~~json
{"status":"up"}
~~~

Request private thiếu token:

~~~bash
curl -i "http://localhost:8080/api/reports"
~~~

Kỳ vọng **401**, vì chưa xác thực. Với cấu hình `.invalid` trong YAML, **không** thể verify token JWT thật qua JWKS online; chỉ có unit/mock tests hoạt động offline. Để end-to-end, thay đúng issuer/JWKS/audience và lấy access token do trusted IdP phát.

Ví dụ gọi API khi đã có token hợp lệ (không đưa token thật vào URL/log):

~~~bash
curl -i "http://localhost:8080/api/reports" \
  -H "Authorization: Bearer <valid-access-token>"
~~~

Khi chữ ký, issuer, thời gian, audience và scope reports.read đều hợp lệ, kỳ vọng **200**. Token hợp lệ nhưng thiếu scope thường **403**. Token có chữ ký/claims không hợp lệ thường **401**. Response header `WWW-Authenticate` có thể giúp phân biệt `invalid_token` với `insufficient_scope`, không được lộ raw token trong logs.

## 19. Vì sao 401 khác 403?

| Tình huống | Kết quả điển hình | Tầng xử lý |
| --- | --- | --- |
| Không có Bearer token | 401 | Authentication |
| JWT malformed hoặc bị tamper | 401 | Decoder/JWS verification |
| Chữ ký sai, alg không allowlist, unknown kid | 401 | Decoder/JWKS |
| `iss` khác issuer tin cậy | 401 | Issuer validation |
| `exp` đã hết hạn ngoài clock skew | 401 | Timestamp validation |
| `nbf` còn ở tương lai | 401 | Timestamp validation |
| `aud` thiếu hoặc sai API | 401 | Audience validation |
| `exp` thiếu trong lab profile | 401 | Required expiration validator |
| Chữ ký/claims hợp lệ nhưng thiếu scope | 403 | Authorization |
| Token hợp lệ và đủ scope | 200 | Controller |
| Token hợp lệ, route không khai báo | 403 | denyAll |
| Token đủ scope nhưng user sai tenant/owner | 403 hoặc 404 theo API contract | Domain authorization |

CORS error ở browser không thay thế JWT debugging. Nếu API thiếu CORS response headers, browser có thể che status 401/403 trong console. Đọc Network và server logs đã sanitise; không tắt signature/issuer/audience checks để “cho request qua”.

## 20. Test JWKS/network và key rotation mở rộng

Unit test mục 16 dùng pinned RSA public key, không kiểm tra fetch/caching JWKS. Để test tích hợp kỹ hơn:

1. Dựng mock JWKS server nội bộ do test kiểm soát, trả JWK public key hợp lệ và key ID.
2. Cấu hình `lab.jwt.jwks-uri` trỏ tới server test, không phải host do request user chọn.
3. Sinh private RSA key, ký JWT có `iss`/`aud`/`exp`/`nbf` đúng.
4. Gửi HTTP request chứa Bearer thật qua `WebTestClient` vào Resource Server, kiểm tra 200.
5. Thay chữ ký hoặc aud/iss/exp/nbf, kiểm tra 401.
6. Thử JWT có `kid` của key mới sau khi mock JWKS công bố key cũ + mới; test behavior cache/rotation theo Spring/Nimbus version.
7. Làm JWKS timeout/5xx/TLS failure, bảo đảm không có đường “accept anything” hoặc fallback bỏ signature.

Đây là **bài nâng cao** chứ không phải file Java có sẵn trong ví dụ. Token key rotation có thể có cache TTL/refresh behavior thay đổi theo version, vì vậy không tuyên bố một số giây cố định nếu chưa đo và đọc tài liệu đúng version.

## 21. Các cấu hình decoder: chọn cách nào?

| Cách | Phù hợp khi | Giới hạn/điểm phải kiểm tra |
| --- | --- | --- |
| Boot `issuer-uri` | IdP có metadata discovery chuẩn | Aud policy bổ sung, availability/discovery |
| Boot `issuer-uri` + `jwk-set-uri` | Muốn trực tiếp dùng trusted JWKS URI | Vẫn phải xác minh iss và aud |
| `ReactiveJwtDecoders.fromIssuerLocation` | Custom Java Bean dựa trên issuer discovery | Network lúc tạo decoder tùy version, giữ validators |
| `NimbusReactiveJwtDecoder.withJwkSetUri` | Cần pin JWKS URI, algorithm, custom validators | Dễ quên iss/aud/timestamp khi thay defaults |
| `NimbusReactiveJwtDecoder.withPublicKey` | Test hoặc môi trường pin một public key | Rotation cần chủ động, không dùng remote JWKS tự động |

Tài liệu Spring Security mô tả các decoder builders và validators. Production chọn phương án ít custom code **nhưng đủ security policy**, không dựng decoder từ raw token input hoặc cho client tự chọn trusted key.

## 22. Multi-issuer, tenants và cross-JWT confusion

Một hệ thống multi-tenant có thể tin nhiều issuers, nhưng phải có **allowlist issuer** do admin quản lý. Phương pháp sau sai:

~~~java
// PSEUDOCODE KHÔNG AN TOÀN:
String userProvidedIssuer = unverifiedJwt.getClaimAsString("iss");
ReactiveJwtDecoder chosen =
    ReactiveJwtDecoders.fromIssuerLocation(userProvidedIssuer);
~~~

Token chưa verify mà đã được dùng để điều khiển network discovery là SSRF/trust injection. Thiết kế đúng dùng issuer → decoder registry đã allowlist, với trusted JWKS/alg/audience khác nhau theo resource/API.

Khi hai issuers phát cùng `sub`, không được mặc định cùng người dùng. Nếu ứng dụng cần user ID ổn định, mapping phải dựa trên `(issuer, subject)`. Khi tenant membership đổi, quyền trong token có thể stale đến hết hạn; domain authorization hoặc cơ chế revoke/refresh phải xử lý theo SLA.

**Cross-JWT confusion:** ID Token OIDC và JWT access token có thể cùng ký bởi IdP nhưng dành cho recipients/mục đích khác. Audience validation là rào cản quan trọng; với hệ thống theo JWT access token profile RFC 9068 cần kiểm tra thêm `typ`/`client_id` và claims theo contract, không chỉ bốn claim của bài học.

## 23. Lỗi production và chẩn đoán

| Triệu chứng | Khả năng | Việc cần làm |
| --- | --- | --- |
| 401 dù JWT payload trông đúng | Chữ ký sai/JWKS không trusted | Không tin payload; kiểm tra key/alg |
| Token A bị API B chấp nhận | Thiếu aud check | Expected audience theo B |
| API trả 200 với mockJwt alg=none | Mock bypass decoder | Dùng signed token test |
| Prod 401 nhưng mock test pass | Issuer/aud/time/signature khác test | Test decoder thật và fake JWKS |
| Có JWT nhưng thiếu `SCOPE_reports.read` | Authorization policy | Map scope và route |
| `nbf` tương lai | Đồng hồ/issuer time lệch | NTP, skew nhỏ, kiểm tra nbf |
| `exp` quá hạn mà vẫn pass | Custom decoder quên timestamp validator | Ghép JwtValidators + negative tests |
| Sau key rotation mọi token 401 | JWKS cache/kid/alg mismatch | Cập nhật key overlap/cache |
| JWKS endpoint không liên lạc được | DNS/TLS/timeouts, chưa có key cache | Fail closed, giám sát IdP |
| Token valid nhưng data tenant sai | Không có domain-level auth | Owner/tenant/DB policy |
| Token bị revoke vẫn pass trước exp | Stateless verification không introspect | Short TTL/introspection/revocation |
| Muốn sửa 401 bằng bỏ issuer validator | Security anti-pattern | Xác định config sai, không fail open |
| API Boot dùng issuer-uri nhưng startup không được | Metadata discovery hoặc issuer sai | Trusted issuer config, deferred decoder behavior |

Thứ tự debug: Bearer header đúng → JWS syntax/alg/kid → trusted JWKS → chữ ký → issuer → timestamps → audience → Authentication authorities → object/tenant authorization. Không log token/claims nhạy cảm nguyên văn để điều tra.

## 24. An toàn vận hành

- Chỉ chấp nhận Bearer qua **HTTPS**; không truyền token trong URL/query, logs, screenshots, analytics hoặc exception text.
- Pin thuật toán, trusted issuer và JWKS URL; không tin `jku`/`x5u`/issuer URL từ token chưa xác minh.
- Không lưu private signing key ở Resource Server. Key công khai trong JWKS là public key.
- Đồng bộ NTP, skew nhỏ, test expired/not-before ở các nodes.
- Theo dõi IdP/JWKS availability, retry/caching có giới hạn, key rotation overlap.
- Hạn chế token/header size và rate limit để tránh token/JWKS endpoint DoS.
- Nếu cần revoke ngay, thiết kế revocation/introspection/token TTL phù hợp; signature validation không tự biết token đã bị rút trước exp.
- Scope/role mapping không thay kiểm tra object/tenant/ownership.
- Nếu JWT được browser auto-send qua cookie, CSRF cần được đánh giá; việc lab tắt CSRF chỉ dựa trên header-only Bearer.
- Với các API theo RFC 9068, kiểm tra toàn bộ token profile/typ chứ không chỉ iss/exp/nbf/aud.

## 25. Bài tập thực hành

**A. Giả mạo claims:** đổi raw JWT payload `scope` mà không ký lại. Tại sao chữ ký bị sai? Thử với token giả trong test, không dùng token thật.

**B. Chữ ký sai:** ký JWT bằng cặp khóa RSA khác, vẫn giữ iss/aud/exp/nbf đúng. Expect JwtException ở decoder trusted public key.

**C. Issuer khác realm:** cùng private key nhưng iss từ realm khác → từ chối. Giải thích vì sao hostname giống không đủ.

**D. Expired vs future nbf:** token đã exp 10 phút và token nbf 1 giờ sau đều phải bị từ chối dù chữ ký đúng.

**E. Audience khác:** token aud billing-api gửi tới reports-api phải reject; token aud có reports-api mới được tiếp tục.

**F. Không có exp:** bỏ exp từ một token đã ký, so sánh kết quả với ExpirationRequiredValidator.

**G. Route authorization:** mockJwt có SCOPE_profile truy cập reports phải 403; SCOPE_reports.read → 200. Nhắc lại mock không kiểm tra chữ ký.

**H. Mock JWKS:** viết integration test JWKS key rotation và outage, bảo đảm không fail-open.

**I. Multi-tenant:** dùng allowlist hai issuers và hai audiences, không cho token của tenant A truy cập B.

**J. Cập nhật phiên bản:** nâng Spring Security/Boot trong sandbox, chạy lại crypto negative tests và kiểm tra defaults về alg/typ/validators.

### Checklist

- [ ] Phân biệt đọc payload và verify JWS signature.
- [ ] Biết trusted JWKS/public key, alg allowlist và kid/key rotation.
- [ ] `iss` exact match trusted issuer.
- [ ] `exp` được so với hiện tại/clock skew và có policy khi thiếu.
- [ ] `nbf` trong tương lai bị reject, hiểu đây là claim optional theo RFC.
- [ ] `aud` chứa đúng Resource Server ID, không so substring.
- [ ] Phân biệt 401 authentication với 403 authorization.
- [ ] Compose `JwtValidators.createDefaultWithIssuer` + AudienceValidator.
- [ ] Có RSA signed-token tests và WebTestClient mockJwt tests độc lập.
- [ ] Không dùng ID Token làm API access token tùy tiện.
- [ ] Không trust issuer/JWKS URL do caller cung cấp.
- [ ] Không bỏ qua tenant/owner checks sau khi token hợp lệ.

## 26. Câu hỏi tự kiểm tra

1. Vì sao đọc Base64URL JWT không chứng minh danh tính?
2. Header alg/kid là gì và tại sao cần allowlist?
3. Public key có thể verify chữ ký mà không biết private key ra sao?
4. Vì sao iss hợp lệ nhưng aud sai vẫn phải reject?
5. exp và nbf khác nhau về đầu/cuối hiệu lực như thế nào?
6. Exp/nbf có bắt buộc trong RFC 7519 không? Lab chọn policy gì?
7. Tại sao không chọn JWKS URL dựa trên iss chưa xác minh?
8. Một JWT hợp lệ nhưng thiếu reports.read tại sao nhận 403?
9. Tại sao mockJwt không chứng minh token signature, issuer, exp, nbf, aud?
10. Khi key rotation, vì sao cần giai đoạn hai keys overlap?
11. Khi token được revoke trước exp, verify chữ ký có biết điều đó không?
12. Vì sao ID Token OIDC không được coi như access token cho reports-api?
13. Khi muốn hỗ trợ nhiều issuers, nên chọn decoder thế nào để tránh SSRF?
14. Tại sao Resource Server vẫn phải kiểm tra owner/tenant sau authentication?

## 27. Tài liệu tham khảo

- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): issuer/JWKS, signed JWT, timestamp validator và custom audience validator.
- [Spring Security — Reactive JWT Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): mockJwt, authorities và giới hạn mock.
- [Spring Security API — NimbusReactiveJwtDecoder](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html): decoder/JWK builder.
- [Spring Security API — JwtValidators](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/jwt/JwtValidators.html): default validators.
- [Spring Security — WebFlux HTTP Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): rule based routing.
- [RFC 7519 — JWT](https://www.rfc-editor.org/rfc/rfc7519): iss, aud, exp, nbf và NumericDate.
- [RFC 7515 — JWS](https://www.rfc-editor.org/rfc/rfc7515): JSON Web Signature.
- [RFC 7517 — JWK](https://www.rfc-editor.org/rfc/rfc7517): JWKS representation và key identifiers.
- [RFC 8725 — JWT BCP](https://www.rfc-editor.org/rfc/rfc8725): algorithm confusion, key validation và cross-JWT confusion.
- [RFC 9068 — JWT Access Token Profile](https://www.rfc-editor.org/rfc/rfc9068): bổ sung access-token-specific claims và typ.
- [OWASP — JSON Web Token for Java Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): JWT security.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, object authorization.

**Kết luận:** Trong Spring Security Reactive, `NimbusReactiveJwtDecoder` xác minh JWS bằng **trusted public key**, sau đó validators đánh giá issuer, thời gian và audience. `iss` chặn token từ nhà phát hành sai; `exp` chặn token hết hạn; `nbf` chặn token dùng sớm; `aud` chặn token dành cho API khác. Chữ ký và bốn claims thành công vẫn chưa đủ cho quyền nghiệp vụ: phải kiểm tra scope, owner và tenant. **Dùng JWT ký thật để test crypto/claims; dùng mockJwt để test authorization — không hoán đổi hai loại bằng chứng.**