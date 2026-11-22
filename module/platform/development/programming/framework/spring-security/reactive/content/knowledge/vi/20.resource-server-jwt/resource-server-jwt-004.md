# ReactiveJwtDecoder và lựa chọn thuật toán chữ ký tin cậy

> **Chủ đề:** Spring Security – reactive  
> **Nhóm kiến thức:** Resource Server JWT  
> **Trọng tâm:** Xác minh chữ ký JWT trên Spring WebFlux với `ReactiveJwtDecoder` và `NimbusReactiveJwtDecoder`; giới hạn các JWS signing algorithms được tin cậy, xác minh issuer/audience/expiration, kết nối trusted JWKS và kiểm thử token được ký thật bằng Java 17+.

## 1. Tại sao đọc được JWT vẫn chưa thể tin JWT?

API báo cáo `GET /api/reports` nhận:

```http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

JWT dạng JWS Compact Serialization gồm:

```text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
```

Ví dụ header và claims:

```json
{
  "typ": "JWT",
  "alg": "RS256",
  "kid": "rsa-2026-01"
}
```

```json
{
  "iss": "https://issuer.example.test",
  "sub": "user-123",
  "aud": ["reports-api"],
  "scope": "reports.read",
  "iat": 1794000000,
  "nbf": 1794000000,
  "exp": 1794003600
}
```

Các số thời gian chỉ minh họa định dạng NumericDate, **không phải token dùng được**. Ai cũng có thể Base64URL-decode payload hoặc tự tạo chuỗi JWT giả. Vì vậy:

1. **Parse:** Chuỗi có đúng cấu trúc JWS/JWT không?
2. **Cryptographic verification:** Signature có hợp lệ với **public key tin cậy** và **thuật toán đã được server cho phép** không?
3. **Claims validation:** `iss`, `aud`, `exp`, `nbf`, token type có đáp ứng policy của API không?
4. **Authorization:** Principal/token hợp lệ có quyền `reports.read` và quyền trên resource cụ thể không?

**Đọc/giải mã không đồng nghĩa xác minh.** Một JWT đúng chữ ký RSA của nhà phát hành nhưng có `aud=payment-api` vẫn phải bị API reports từ chối. Một JWT hợp lệ về issuer và audience nhưng thiếu scope vẫn có thể được xác thực rồi bị **403** ở tầng phân quyền.

### Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt `ReactiveJwtDecoder` với `JwtDecoder` Servlet và biết `Mono<Jwt>` xử lý lỗi thế nào.
- Hiểu `alg`, `kid`, JWKS, key rotation và lý do phải cấu hình thuật toán tin cậy ở **phía server**, không theo dữ liệu token tự khai.
- Dùng Spring Boot properties `issuer-uri`, `jwk-set-uri`, `jws-algorithms` và `audiences` khi phù hợp.
- Tạo custom `NimbusReactiveJwtDecoder` với `jwsAlgorithm(SignatureAlgorithm.RS256)`, giữ default issuer/time validators và thêm audience validator.
- Phân biệt RS256, PS256, ES256, HS256 và `alg=none`.
- Viết Spring Security WebFlux Resource Server Java 17+ và kiểm thử real-signed JWT với `NimbusJwtEncoder` + `StepVerifier`.
- Test HTTP 401/403/scope bằng `WebTestClient`, biết rõ `mockJwt()` **không kiểm tra chữ ký**.

## 2. Vị trí ReactiveJwtDecoder trong WebFlux Resource Server

Một đường xử lý đã được giản lược:

```text
HTTP Authorization: Bearer <token>
          |
          v
SecurityWebFilterChain / Bearer authentication
          |
          v
ReactiveJwtDecoder.decode(token)
          |
          +-- JWT parse, header alg policy, select trusted key
          +-- verify cryptographic signature
          +-- validate iss/aud/exp/nbf/type theo cấu hình
          |
          +-- sai -> JwtException / authentication failure -> thường 401
          |
          v
JwtAuthenticationToken (Jwt principal + authorities)
          |
          v
AuthorizationWebFilter
          |
          +-- thiếu SCOPE_reports.read -> thường 403
          +-- đủ quyền -> WebFlux controller Mono/Flux
```

`ReactiveJwtDecoder` là interface ở package `org.springframework.security.oauth2.jwt`:

```java
// Chữ ký API để tham khảo:
Mono<Jwt> decode(String token) throws JwtException;
```

`decode` trả publisher `Mono<Jwt>`. Với WebFlux, lỗi signature/validation thường được phát thành **reactive error signal**. Bạn không cần gọi `.block()` hay `.subscribe()` để “kích hoạt decoder” trong controller: Spring Security thực hiện trong authentication filter trước khi controller nhận request.

**So sánh stack:**

| Stack | Decoder | Kết quả |
| --- | --- | --- |
| Spring WebFlux reactive | `ReactiveJwtDecoder` | `Mono<Jwt>` |
| Spring Security Servlet | `JwtDecoder` | `Jwt` |
| Nimbus reactive implementation | `NimbusReactiveJwtDecoder` | JWT đã được verify/validate |
| Nimbus imperative implementation | `NimbusJwtDecoder` | Chỉ dùng cho cấu hình phù hợp Servlet |

Không đưa bean `JwtDecoder` kiểu `HttpSecurity` từ tutorial Servlet vào một app chỉ dùng `ServerHttpSecurity` rồi hy vọng reactive resource server sẽ lấy nó.

### 2.1. JWT Authentication và quyền truy cập không giống nhau

Spring Security thường ánh xạ `scope` hoặc `scp` trong JWT sang `GrantedAuthority` dạng `SCOPE_...`:

```text
scope claim: "reports.read reports.write"
                    |
                    v
SCOPE_reports.read
SCOPE_reports.write
```

Khi rule là `hasAuthority("SCOPE_reports.read")`, JWT có chữ ký hợp lệ nhưng chỉ có `SCOPE_profile.read` sẽ bị authorization từ chối. Trong nhiều cấu hình, authentication failure trả HTTP **401** có Bearer challenge; thiếu quyền của principal hợp lệ trả **403**. CORS, CSRF hoặc gateway cũng có thể trả 403 nên không phải mọi 403 đều do scope.

## 3. Thuật toán chữ ký tin cậy: mặc định RS256

Tài liệu Spring Security 6.5 nêu rõ `NimbusReactiveJwtDecoder` **mặc định chỉ tin cậy RS256** trong cấu hình JWT Resource Server. Không mở rộng chỉ vì decoder có thể hỗ trợ nhiều thuật toán; chỉ thay đổi khi Authorization Server thực sự phát access tokens với thuật toán khác và bạn đã xác nhận loại key, issuer, profile.

| JWS algorithm | Họ mật mã | Key dùng để xác minh | Ghi chú |
| --- | --- | --- | --- |
| `RS256` | RSA PKCS#1 v1.5 / SHA-256 | RSA public key | Mặc định Spring Security 6.5 |
| `RS384`, `RS512` | RSA SHA-384/512 | RSA public key | Không tự bật nếu IdP không sử dụng |
| `PS256`, `PS384`, `PS512` | RSA-PSS | RSA public key | Khác RS*, dù cùng key family |
| `ES256` | ECDSA P-256 / SHA-256 | EC public key | Phải đúng curve/key |
| `ES384`, `ES512` | ECDSA phù hợp curve | EC public key | Chỉ bật theo provider |
| `HS256`, `HS384`, `HS512` | HMAC | Shared secret | Bên verify có secret cũng có thể ký |
| `none` | Không có chữ ký | Không có | Không được chấp nhận cho protected Bearer JWT |

`SignatureAlgorithm.RS256` và `SignatureAlgorithm.PS256` đều có ở package `org.springframework.security.oauth2.jose.jws`. Với RSA public-key builder, API dùng `.signatureAlgorithm(...)`; với trusted JWKS builder, API dùng `.jwsAlgorithm(...)`.

### 3.1. Header alg luôn là dữ liệu chưa đáng tin

Sai về nguyên tắc:

```java
// Pseudocode sai: không triển khai theo mẫu này.
String algorithm = parseUnverifiedHeader(token).get("alg");
ReactiveJwtDecoder decoder = trustAlgorithmFromCaller(algorithm);
```

Kẻ tấn công kiểm soát header. Nếu server tự chấp nhận “alg do token yêu cầu”, có thể xuất hiện **algorithm confusion/substitution** (ví dụ trộn RSA public key và HMAC secret trong một verifier sai thiết kế). Khóa tin cậy, thuật toán được phép và đối tượng phát hành phải được quyết định **từ cấu hình backend**, không từ JWT chưa xác minh.

Đúng:

```java
// Snippet bên trong cấu hình có trusted JWKS URI.
NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder.withJwkSetUri(trustedJwksUri)
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .build();
```

Đây mới là **chốt thuật toán**. Sau đó vẫn phải cấu hình issuer/audience validators.

### 3.2. Khi cần hai thuật toán trong thời gian migration

```java
// Chỉ bật khi issuer thật đã công bố cả hai và có kế hoạch cutover.
NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder.withJwkSetUri(trustedJwksUri)
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .jwsAlgorithm(SignatureAlgorithm.ES256)
        .build();
```

Mỗi lời gọi `jwsAlgorithm` trên JWKS builder **thêm** một thuật toán được chấp nhận; không phải chỉ thay giá trị trước đó. Một migration an toàn cần giới hạn thời gian, test token RS256/ES256, key rotation và cuối cùng gỡ thuật toán cũ. Không đưa toàn bộ thuật toán vào allowlist để dập mọi lỗi HTTP 401.

### 3.3. RS256 và PS256 không đồng nghĩa

Cả hai dùng RSA public/private keys, nhưng RS256 là RSA PKCS#1 v1.5 còn PS256 dùng RSA-PSS. Nếu decoder chỉ allow RS256 thì JWT ký bằng PS256 **phải bị từ chối**, **ngay cả khi** chữ ký PS256 được tạo bằng cùng RSA private key đang được tin cậy. Test thực tế ở mục 9 cố ý kiểm tra điều này.

### 3.4. HMAC là một trust model khác

```java
// Snippet HMAC riêng: chỉ dùng khi thiết kế tin cậy shared secret.
NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder.withSecretKey(secretKey)
        .macAlgorithm(MacAlgorithm.HS256)
        .build();
```

`MacAlgorithm` được import từ `org.springframework.security.oauth2.jose.jws.MacAlgorithm`; `secretKey` phải là `javax.crypto.SecretKey` đủ entropy và lấy từ secrets manager. **Không** dùng RSA public key làm HMAC secret. Với nhiều Resource Servers, chữ ký bất đối xứng thường phù hợp hơn vì các API chỉ nhận public keys mà không thể ký JWT giả.

## 4. JWKS, kid và ranh giới tin cậy

Authorization Server có thể công bố **JWKS** (JSON Web Key Set) qua HTTPS:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "rsa-2026-01",
      "alg": "RS256",
      "n": "BASE64URL_RSA_MODULUS",
      "e": "AQAB"
    }
  ]
}
```

Đây là **ví dụ cấu trúc**, chưa phải key khả dụng. JWKS public không được lộ private exponent `d`, key primes hay secret ký. Resource Server chọn key từ **JWKS URL được cấu hình tin cậy**:

```text
JWS header alg=RS256, kid=rsa-2026-01
             |
             v
Allowlist algorithms của server (RS256?)
             |
             v
Trusted JWKS source của đúng issuer
             |
             v
Lọc key phù hợp kid/kty/use/alg/key material
             |
             v
Xác minh chữ ký
             |
             v
Validate JWT claims và policy API
```

`kid` chỉ là **gợi ý key identifier**, không chứng minh issuer/key đáng tin. Các JOSE headers như `jku`/`x5u` có thể chứa URL; **không tự động tải public key từ URL do token do người gọi cung cấp**. Nếu làm vậy sẽ mở rủi ro SSRF và key injection: attacker có thể chuyển verifier sang key họ tự sở hữu.

Khi AS xoay khóa, công bố public key mới **trước khi** hoặc cùng lúc phát tokens ký bằng key mới, duy trì key cũ đủ lâu cho token còn hạn. Spring Security/Nimbus có hỗ trợ chọn và refresh keys từ JWKS, nhưng vẫn phải kiểm thử cache TTL, rotate, outage, unknown kid, concurrency và nhiều replica. Không fallback “bỏ qua chữ ký” khi JWKS tạm lỗi.

### 4.1. Key rotation khác algorithm migration

- **Rotate key, giữ RS256:** thêm `kid` mới trong JWKS, vẫn cho RS256.
- **Chuyển RS256 sang ES256:** thêm algorithm/key type mới theo kế hoạch, test cùng lúc hai profile, rồi thu hồi thuật toán cũ.
- **Đổi issuer:** cần trust policy/decoder routing mới, không chỉ đổi `kid`.

Nếu hệ thống nhận token từ nhiều issuers, phải cấu hình **trusted issuer allowlist** và gắn mỗi issuer với JWKS/audience phù hợp. Dùng `iss` chưa xác minh như chỉ dẫn *trong tập issuer đã tin cậy*, không tải JWKS từ mọi issuer string trong token.

## 5. Spring Boot properties: cấu hình nhanh, rõ và có ranh giới

Với Resource Server WebFlux dùng **Boot auto-configuration** và không tự khai custom decoder bean:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test
          jwk-set-uri: https://issuer.example.test/oauth2/jwks
          jws-algorithms: RS256
          audiences:
            - reports-api
```

- `issuer-uri` giúp kiểm tra `iss` và có thể dùng cho metadata discovery.
- `jwk-set-uri` là **trusted URL** lấy public signing keys. Khi khai cả hai, Resource Server không cần discovery để tìm JWKS URL lúc khởi tạo; xác minh token mới vẫn có thể cần kết nối JWKS.
- `jws-algorithms` chọn JWS signing algorithms được tin cậy. Ví dụ chỉ cho RS256.
- `audiences` buộc API kiểm tra `aud` theo config Boot được hỗ trợ, ngăn token dành cho API khác.

Chỉ có `jwk-set-uri` mà không có issuer validation thích hợp **không đủ** để khẳng định mọi token từ đúng issuer. Một issuer có thể cấp token cho nhiều Resource Servers, vì vậy audience thường là yêu cầu riêng. 

Nếu ứng dụng cung cấp **`@Bean ReactiveJwtDecoder`**, chính bean custom sẽ thay thế decoder auto config của Spring Boot; **không mặc nhiên nghĩ** properties trên vẫn được áp lên bean. Custom bean phải tự cấu hình allowed algorithms, key source và validators. Mục 8 dùng cách custom bean để rõ từng bước.

### 5.1. Spring Security WebFlux DSL

```java
// Snippet trong @Configuration (import withDefaults).
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/health").permitAll()
            .pathMatchers("/api/reports")
                .hasAuthority("SCOPE_reports.read")
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
        .build();
}
```

Nếu dùng Boot properties, Resource Server JWT tự dùng decoder bean do Boot tạo. `ServerHttpSecurity` là WebFlux; không thay bằng `HttpSecurity` của Servlet.

## 6. Custom NimbusReactiveJwtDecoder và các validators

Đôi khi cần kiểm tra audience, token profile hoặc nhiều issuers/algorithms. Cấu hình Java:

```java
// Snippet trong class @Configuration, phần đầy đủ nằm ở mục 8.
@Bean
ReactiveJwtDecoder jwtDecoder() {
    String issuer = "https://issuer.example.test";
    String jwks = issuer + "/oauth2/jwks";

    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withJwkSetUri(jwks)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

    OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(issuer);
    OAuth2TokenValidator<Jwt> audience =
        new AudienceValidator("reports-api");

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(defaults, audience));
    return decoder;
}
```

`AudienceValidator` là class được viết đầy đủ ở mục 8. Trong cấu hình này:

1. JWKS URL được tin cậy và không suy ra từ token.
2. Chỉ tin RS256 dù JWKS có những keys khác.
3. `JwtValidators.createDefaultWithIssuer` giữ các validator mặc định (bao gồm thời gian) và issuer.
4. Audience được kiểm tra riêng: JWT phải có `aud=reports-api`.
5. Nếu token vượt qua decoder, Spring mới map claims thành authorities để xét endpoint permission.

**Cảnh báo về `setJwtValidator`:** nó **thay thế** validator hiện tại. Nếu chỉ đặt `new AudienceValidator(...)` và bỏ default validators, bạn có nguy cơ bỏ mất kiểm tra `iss`, `exp`/`nbf`. Hãy kết hợp bằng `DelegatingOAuth2TokenValidator` như trên.

### 6.1. Clock skew

Nhiều hệ thống có lệch đồng hồ vài giây. Spring Security sử dụng `JwtTimestampValidator` kiểm tra `exp` và `nbf`, với skew mặc định được tài liệu mô tả thường **60 giây**. Đừng tăng skew quá lớn để hợp thức hóa token hết hạn. Đồng bộ NTP và test các trường hợp token expired và `nbf` quá xa tương lai. Ví dụ tests dùng cách biệt vài phút để không flaky.

### 6.2. Audience, issuer và scope là ba khái niệm khác nhau

| Claim | Câu hỏi |
| --- | --- |
| `iss` | Ai phát hành JWT? |
| `aud` | JWT được phát cho Resource Server nào? |
| `sub` | Chủ thể được token nói tới là ai? |
| `exp` | Khi nào token hết hạn? |
| `nbf` | Khi nào bắt đầu có hiệu lực? |
| `scope`/`scp` | Quyền được AS cấp để dùng tài nguyên nào? |

JWT có scope đúng nhưng audience sai phải **bị từ chối từ decoder**, không được đi đến rule phân quyền. JWT có audience đúng nhưng scope thiếu có thể **được xác thực và sau đó bị 403**. JWT đúng signature nhưng là **OIDC ID token** với `aud=web-client` không nên được dùng thay access token gọi Resource Server.

### 6.3. JWT type: access token vs ID token

OIDC ID token dành cho OIDC Client xác minh danh tính người dùng. OAuth2 access token dành cho Resource Server. Trong thực tế cả hai có thể là JWT do cùng issuer ký. Chỉ kiểm tra signature/issuer có thể gây **token substitution/cross-JWT confusion**. Tùy issuer, cần kiểm tra audience, token type `typ`, `client_id`, scope hoặc profile RFC 9068.

Spring Security 6.5 có `JwtValidators.createAtJwtValidator()` để xây validator theo RFC 9068 khi Authorization Server phát JWT access tokens theo profile đó; phải cấu hình type/header validation tương thích, không áp vào provider bất kỳ mà chưa đọc tài liệu token profile.

## 7. Quy tắc an toàn khi sử dụng decode() từ reactive code

```java
// Tác vụ reactive ngoài filter (snippet, yêu cầu decoder được inject):
return decoder.decode(rawToken)
    .map(Jwt::getSubject)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("No JWT was produced")));
```

Phần lớn API **không cần gọi decoder thủ công trong controller**: Spring Security Resource Server filter đã xác thực Bearer trước request. Nếu có use case khác, hãy trả publisher và xử lý `onError`, không gọi:

```java
// Không dùng trong Netty event loop:
Jwt jwt = decoder.decode(rawToken).block();

// Không tạo subscription rời rồi giả định request đã xác thực:
decoder.decode(rawToken).subscribe(jwt -> allowRequest());
```

`.block()` chặn thread và `.subscribe()` thủ công tách lifecycle/errors/cancellation khỏi request. Trong WebFlux, `Authentication` của request được mang qua **Reactor Context**, đọc bằng `ReactiveSecurityContextHolder`, không lấy từ `SecurityContextHolder` ThreadLocal theo assumption Servlet.

## 8. Project Java 17+ WebFlux: chữ ký RS256 và audience

Project sau dùng **Spring Boot 3.5.16** (bản OSS cuối của nhánh 3.5, chỉ làm baseline học Spring Security 6.5; production năm 2026 nên dùng nhánh còn được hỗ trợ). **Maven tests chạy offline** với JWT ký thật bằng keypair sinh tại test runtime và mock JWT cho HTTP authorization. Ứng dụng chạy thử được endpoint public/401, nhưng muốn HTTP Bearer token hợp lệ end-to-end phải thay issuer/JWKS ví dụ bằng một IdP sandbox thực.

### 8.1. Cấu trúc

```text
reactive-jwt-algorithms/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/jwt/
    │   │   ├── Application.java
    │   │   ├── AudienceValidator.java
    │   │   ├── JwtSecurityConfiguration.java
    │   │   └── ReportController.java
    │   └── resources/application.yml
    └── test/java/demo/jwt/
        ├── JwtDecoderSignatureTests.java
        └── HttpJwtAuthorizationTests.java
```

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-jwt-algorithms</artifactId>
    <version>1.0.0</version>
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
```

`spring-boot-starter-oauth2-resource-server` cung cấp các dependencies Resource Server/JWT JOSE cần thiết trong dự án Boot. Không dùng OAuth2 Client starter nếu app chỉ **nhận và kiểm tra** Bearer JWT, không xin token cho outbound API.

### 8.3. src/main/resources/application.yml

```yaml
app:
  security:
    jwt:
      issuer: https://issuer.example.test
      jwk-set-uri: https://issuer.example.test/oauth2/jwks
      audience: reports-api
server:
  port: 8080
```

Đây là properties **riêng** `app.security.jwt.*` để Java config đọc. Chúng không phải Spring Boot decoder auto-configuration keys ở mục 5. `issuer.example.test` chỉ là host ví dụ: **không có Authorization Server thật tại URL này**. Không nhập private signing key hoặc client secret vào resource server.

### 8.4. src/main/java/demo/jwt/Application.java

```java
package demo.jwt;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 8.5. src/main/java/demo/jwt/AudienceValidator.java

```java
package demo.jwt;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class AudienceValidator
        implements OAuth2TokenValidator<Jwt> {

    private final String expectedAudience;

    public AudienceValidator(String expectedAudience) {
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience().contains(expectedAudience)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token",
                "JWT audience is not this resource server", null));
    }
}
```

`AudienceValidator` **chỉ** kiểm tra `aud`. Nó không tự xác minh chữ ký/issuer/expiration; cấu hình phải kết hợp nó với bộ default validators.

### 8.6. src/main/java/demo/jwt/JwtSecurityConfiguration.java

```java
package demo.jwt;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class JwtSecurityConfiguration {

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwksUri,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwksUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> defaultWithIssuer =
            JwtValidators.createDefaultWithIssuer(issuer);
        OAuth2TokenValidator<Jwt> audienceValidator =
            new AudienceValidator(audience);

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaultWithIssuer, audienceValidator));

        return decoder;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .pathMatchers("/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            // Chỉ cho API Bearer header trong demo, không có browser session.
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
```

**Giải thích:** Custom `ReactiveJwtDecoder` chỉ tin RS256, lấy public keys từ JWKS trust URL, giữ issuer/time validators, thêm audience check. Security filter yêu cầu JWT Bearer và tách quyền `SCOPE_reports.read`. `httpBasic`/`formLogin` bị tắt để không lẫn cơ chế login. `csrf.disable()` chỉ hợp lý theo giả định **API thuần Bearer** không dùng session cookie hay credentials tự động của browser; không sao chép vào website cookie-based mà không phân tích CSRF.

### 8.7. src/main/java/demo/jwt/ReportController.java

```java
package demo.jwt;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReportController {

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("OK");
    }

    @GetMapping("/api/reports")
    public Mono<String> reports() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "report:" + auth.getName());
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "subject:" + auth.getName());
    }
}
```

`getName()` thường ánh xạ từ `sub` của JWT trong cấu hình Resource Server mặc định, nhưng có thể tùy biến bằng converter. Đây là **identity đã qua Spring Security authentication**, không được lấy từ `?user=` hoặc client-provided `X-User`. Với dữ liệu thật, còn phải kiểm tra ownership và tenant theo repository đáng tin.

## 9. Test mật mã thật: RS256 được chấp nhận, PS256 bị từ chối

Bộ test này tạo RSA keypair ngẫu nhiên trong **bộ nhớ test**, ký JWT bằng private key qua `NimbusJwtEncoder`, rồi decode JWT với **public key** bằng `NimbusReactiveJwtDecoder`. Các trường hợp sai thuật toán, key, issuer, audience, thời hạn và unsigned đều được xác minh bằng `StepVerifier`.

### 9.1. src/test/java/demo/jwt/JwtDecoderSignatureTests.java

```java
package demo.jwt;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.PlainJWT;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class JwtDecoderSignatureTests {

    private static final String ISSUER =
        "https://issuer.example.test";
    private static final String AUDIENCE = "reports-api";

    private static KeyPair trustedKeyPair;
    private static NimbusReactiveJwtDecoder decoder;

    @BeforeAll
    static void setup() throws Exception {
        trustedKeyPair = makePair();
        decoder = NimbusReactiveJwtDecoder
            .withPublicKey((RSAPublicKey) trustedKeyPair.getPublic())
            .signatureAlgorithm(SignatureAlgorithm.RS256)
            .build();
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(ISSUER),
            new AudienceValidator(AUDIENCE)));
    }

    private static KeyPair makePair() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    private static String sign(
            KeyPair keyPair, SignatureAlgorithm algorithm,
            String issuer, String audience,
            Instant notBefore, Instant expiresAt) {

        RSAKey jwk = new RSAKey.Builder(
                (RSAPublicKey) keyPair.getPublic())
            .privateKey((RSAPrivateKey) keyPair.getPrivate())
            .keyID("test-kid")
            .build();

        NimbusJwtEncoder encoder = new NimbusJwtEncoder(
            new ImmutableJWKSet<>(new JWKSet(jwk)));

        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("alice")
            .audience(List.of(audience))
            .issuedAt(Instant.now().minusSeconds(900))
            .notBefore(notBefore)
            .expiresAt(expiresAt)
            .claim("scope", "reports.read")
            .build();

        JwsHeader header = JwsHeader.with(algorithm)
            .keyId("test-kid")
            .build();

        return encoder.encode(
            JwtEncoderParameters.from(header, claims))
            .getTokenValue();
    }

    private static String validToken() {
        Instant now = Instant.now();
        return sign(trustedKeyPair, SignatureAlgorithm.RS256,
            ISSUER, AUDIENCE,
            now.minusSeconds(120), now.plusSeconds(300));
    }

    @Test
    void trustedRs256AndClaimsAreAccepted() {
        StepVerifier.create(decoder.decode(validToken()))
            .assertNext(jwt -> {
                assertEquals("alice", jwt.getSubject());
                assertEquals(ISSUER, jwt.getIssuer().toString());
                assertEquals(List.of(AUDIENCE), jwt.getAudience());
            })
            .verifyComplete();
    }

    @Test
    void signedPs256IsRejectedWhenOnlyRs256IsAllowed() {
        Instant now = Instant.now();
        String token = sign(trustedKeyPair,
            SignatureAlgorithm.PS256, ISSUER, AUDIENCE,
            now.minusSeconds(120), now.plusSeconds(300));

        StepVerifier.create(decoder.decode(token))
            .expectError(JwtException.class).verify();
    }

    @Test
    void rs256WithDifferentSigningKeyIsRejected() throws Exception {
        Instant now = Instant.now();
        String token = sign(makePair(), SignatureAlgorithm.RS256,
            ISSUER, AUDIENCE,
            now.minusSeconds(120), now.plusSeconds(300));

        StepVerifier.create(decoder.decode(token))
            .expectError(JwtException.class).verify();
    }

    @Test
    void validSignatureWithWrongIssuerIsRejected() {
        Instant now = Instant.now();
        String token = sign(trustedKeyPair, SignatureAlgorithm.RS256,
            "https://other.example.test", AUDIENCE,
            now.minusSeconds(120), now.plusSeconds(300));

        StepVerifier.create(decoder.decode(token))
            .expectError(JwtException.class).verify();
    }

    @Test
    void validSignatureWithWrongAudienceIsRejected() {
        Instant now = Instant.now();
        String token = sign(trustedKeyPair, SignatureAlgorithm.RS256,
            ISSUER, "payments-api",
            now.minusSeconds(120), now.plusSeconds(300));

        StepVerifier.create(decoder.decode(token))
            .expectError(JwtException.class).verify();
    }

    @Test
    void expiredJwtIsRejected() {
        Instant now = Instant.now();
        String token = sign(trustedKeyPair, SignatureAlgorithm.RS256,
            ISSUER, AUDIENCE,
            now.minusSeconds(900), now.minusSeconds(300));

        StepVerifier.create(decoder.decode(token))
            .expectError(JwtException.class).verify();
    }

    @Test
    void futureNbfJwtIsRejected() {
        Instant now = Instant.now();
        String token = sign(trustedKeyPair, SignatureAlgorithm.RS256,
            ISSUER, AUDIENCE,
            now.plusSeconds(600), now.plusSeconds(1200));

        StepVerifier.create(decoder.decode(token))
            .expectError(JwtException.class).verify();
    }

    @Test
    void unsignedPlainJwtIsRejected() {
        String plain = new PlainJWT(
            new JWTClaimsSet.Builder().subject("alice").build())
            .serialize();

        StepVerifier.create(decoder.decode(plain))
            .expectError(JwtException.class).verify();
    }
}
```

Đây là **8 bài kiểm thử cryptographic**. Test PS256 quan trọng nhất cho chủ đề lựa chọn thuật toán: chữ ký PS256 có thể do cùng RSA private key tạo ra, nhưng decoder configured RS256-only **vẫn phải reject** vì alg không thuộc allowlist. Test issuer/audience chứng minh việc **ký đúng chưa đủ** để được Resource Server chấp nhận.

**Không kiểm thử bằng cách so một signature string cứng:** RSA keypair được tạo ngẫu nhiên, `Instant.now()` tạo thời gian động, nên test chỉ assert đúng kết quả decoded/exception. `JwtException` là superclass phù hợp để không buộc test vào message nội bộ hay chính xác subclass của phiên bản thư viện.

**Giới hạn:** decoder này dùng public key trực tiếp để verify. Nó không chứng minh remote JWKS retrieval, HTTP filter hay key rotation; các phần đó cần integration test riêng.

## 10. Test HTTP: 401/403 và SCOPE_ mapping

`mockJwt()` giúp test Spring WebFlux URL authorization mà **không yêu cầu JWT thật**. Đây là mục tiêu khác với unit tests cryptographic ở trên.

### 10.1. src/test/java/demo/jwt/HttpJwtAuthorizationTests.java

```java
package demo.jwt;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class HttpJwtAuthorizationTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void healthIsPublic() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("OK");
    }

    @Test
    void missingBearerIs401() {
        client.get().uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void correctScopeIs200() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.subject("alice"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_reports.read")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report:alice");
    }

    @Test
    void wrongScopeIs403() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.write")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unprefixedScopeIs403() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("reports.read")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void jwtSubjectAvailableInReactiveContext() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt.subject("bob")))
            .get().uri("/api/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("subject:bob");
    }

    @Test
    void basicAuthenticationDoesNotReplaceBearer() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("alice", "demo123"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownPathDeniedEvenWithJwt() {
        client.mutateWith(mockJwt())
            .get().uri("/api/internal")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Có **8 WebTestClient tests**. Trong đó `mockJwt` **bypass decoder**, nên test `correctScopeIs200` không chứng minh chữ ký RSA hợp lệ; nó chỉ chứng minh URL rule `SCOPE_reports.read` và Reactor Context hoạt động. Trái lại, `JwtDecoderSignatureTests` thực sự xử lý JWT ký bằng private key, nhưng không test full HTTP filter/JWKS. Hai nhóm test **bổ trợ**, không thay thế cho nhau.

### 10.2. Ma trận kết quả

| Case | Test suite | Kết quả mong đợi |
| --- | --- | --- |
| RS256 đúng chữ ký/claims | StepVerifier | Emit Jwt |
| PS256 khi chỉ cho RS256 | StepVerifier | JwtException |
| RS256 ký bằng key khác | StepVerifier | JwtException |
| Issuer sai | StepVerifier | JwtException |
| Audience sai | StepVerifier | JwtException |
| Expired hoặc future nbf | StepVerifier | JwtException |
| Unsigned/plain | StepVerifier | JwtException |
| Health không JWT | WebTestClient | HTTP 200 |
| API không Bearer | WebTestClient | HTTP 401 |
| JWT mock + read scope | WebTestClient | HTTP 200 |
| JWT mock + wrong scope | WebTestClient | HTTP 403 |
| JWT mock + unprefixed scope | WebTestClient | HTTP 403 |
| JWT mock truy cập subject | WebTestClient | HTTP 200 |
| HTTP Basic thay Bearer | WebTestClient | HTTP 401 |
| JWT mock trên unknown route | WebTestClient | HTTP 403 |

Tổng cộng **16 bài test**: 8 test chữ ký/claims và 8 test HTTP authorization. Không dùng những kết quả dự kiến này để khẳng định đã xác minh remote issuer/JWKS thực tế.

## 11. Chạy Maven và thử bằng curl

Tại thư mục chứa `pom.xml`:

```bash
java -version
mvn -version
mvn clean test
```

**Kỳ vọng** (khi môi trường tương thích): `Tests run: 16, Failures: 0, Errors: 0` và `BUILD SUCCESS`. Đây là kỳ vọng theo ví dụ, **không phải khẳng định Maven đã chạy trên môi trường của người đọc hoặc trong phiên biên soạn**. Nếu build lỗi, kiểm tra `target/surefire-reports`, JDK, Maven, version dependencies và API signatures theo phiên bản.

Khởi động ứng dụng:

```bash
mvn spring-boot:run
```

Health endpoint public:

```bash
curl -i http://localhost:8080/health
```

Kết quả body mong đợi: `OK`, HTTP 200.

Không cung cấp token:

```bash
curl -i http://localhost:8080/api/reports
```

Dự kiến HTTP **401 Unauthorized**, với `WWW-Authenticate: Bearer` hoặc biến thể phù hợp.

### 11.1. HTTP Bearer token thật cần Authorization Server hợp lệ

Ứng dụng cấu hình `issuer.example.test` là **địa chỉ học tập**, chưa có issuer/JWKS thật. Muốn gọi protected endpoint thành công qua HTTP:

1. Chọn IdP sandbox và khai issuer/JWKS đúng URL đáng tin.
2. Bảo đảm IdP phát JWT access token **RS256**, đúng `iss`, `aud=reports-api`, thời hạn và `reports.read` scope.
3. Truy cập JWKS qua TLS, xác minh cert/keys/kid, đồng bộ giờ.
4. Gửi access token nguyên vẹn trong `Authorization: Bearer`.
5. Kiểm tra HTTP 200, đồng thời thử wrong key/algorithm/issuer/audience (401) và thiếu scope (403).

Ví dụ sử dụng biến môi trường khi đã có **token sandbox thật**:

```bash
curl -i -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/reports
```

Không ghi private signing key hoặc raw Bearer token vào log, ticket, source code hay screenshots. Với production dùng HTTPS; token là credential, đọc được payload và có thể bị dùng lại nếu lộ.

## 12. Debug khi Resource Server trả 401 hoặc 403

| Hiện tượng | Nguyên nhân | Hướng kiểm tra |
| --- | --- | --- |
| 401, không có Bearer | Chưa xác thực | Client gửi access token thật chưa? |
| 401, token có `alg=PS256` | Allowlist chỉ có RS256 | Chỉ mở PS256 khi AS/issuer policy xác nhận |
| 401, `kid` lạ | JWKS chưa có key/rotation/cache | Kiểm tra trusted JWKS, key ID, cache |
| 401, token ký bằng key khác | Signature verify thất bại | So key public AS trusted |
| 401, token đúng signature nhưng `iss` sai | Không tin issuer này | Chặn token, kiểm tra registration/issuer config |
| 401, `aud` sai | Token không dành cho API | Thêm audience validation, client xin đúng API token |
| 401, `exp` quá hạn | Token hết hiệu lực | Client refresh/re-authorize, không bỏ timestamp check |
| 401, `nbf` tương lai | Chưa có hiệu lực | Clock sync/AS timestamps, skew hợp lý |
| 401, AS JWKS offline | Key retrieval lỗi | Timeout/cache, fail closed, không skip signature |
| 401, token bị từ chối khi đổi alg | AS/RS không đồng bộ migration | Đồng bộ key type/allowed algorithms |
| 403, valid token nhưng scope thiếu | Authorization policy | `SCOPE_` mapping/tenant/resource checks |
| 403, JWT của user khác có role admin | Quyền resource-level khác nhau | Kiểm tra object ownership, tenant, policy |
| Test `mockJwt()` pass, token thật 401 | Mock bypass crypto | Viết signed-token decoder/JWKS test |
| YAML `spring.security...` không tác dụng | Custom decoder bean thay auto config | Sửa đúng bean/config nguồn |
| Dùng `JwtDecoder` Servlet trong WebFlux | Sai interface | Dùng `ReactiveJwtDecoder` |
| Header có `jku` URL bất kỳ | Key injection/SSRF risk | Chỉ dùng trusted config JWKS |
| JWT dùng `alg=none` | Không có chữ ký | Từ chối, không “fallback” |
| Copy `HS256` secret sang nhiều APIs | Secret holders cũng có thể ký | Xem lại trust model, ưu tiên asymmetric |
| CORS browser báo lỗi, API log 401 | Error response thiếu CORS headers | Debug preflight/CORS riêng với authentication |
| API dùng JWT cho frontend client khác | Token substitution | Kiểm tra audience/token type và issuer |

### 12.1. Cách debug theo thứ tự

1. Phân biệt 401 authentication với 403 authorization.
2. Xác nhận client gửi **access token**, không gửi OIDC ID token hay refresh token.
3. Kiểm tra bean decoder thực tế, allowed JWS algorithms, trusted JWKS URL.
4. Kiểm tra header `kid/alg` chỉ để chẩn đoán, **không** coi chúng là tín hiệu đáng tin.
5. Xác minh signature theo trusted key, sau đó issuer/audience/time/token type.
6. Sau khi decoder pass, kiểm tra authorities `SCOPE_...`, URL/method/object-level policy.
7. Kiểm thử wrong-alg/key/issuer/audience/expired thay vì chỉ test success.
8. Đánh giá cache/key rotation, JWKS outage và error handling qua gateway.
9. Redact token, secret, PII và raw Authorization headers trong mọi logs.

## 13. Các trường hợp nâng cao cần phân biệt

### 13.1. Signing (JWS) không phải encryption (JWE)

JWS bảo vệ toàn vẹn/xuất xứ bằng signature, nhưng header/payload có thể đọc được. JWE là chuẩn mã hóa khác. `ReactiveJwtDecoder` ví dụ này xử lý signed access tokens; **không** mặc định giải mã mọi encrypted JWT. Nếu issuer dùng nested JWT/JWE cần một giải pháp riêng và keys/decryption policy rõ ràng, không bỏ kiểm tra chữ ký vì payload “đã mã hóa”.

### 13.2. Token có cùng issuer và chữ ký vẫn chưa đủ

IdP đôi khi dùng cùng signing keys phát nhiều loại token cho nhiều applications. Resource Server phải xem **`aud`** và token-purpose profile. Một token `aud=web-client` (ID token) không được truy cập `reports-api` chỉ vì signature hợp lệ. Đây là lý do audience validators và RFC 8725 cross-JWT confusion guidance quan trọng.

### 13.3. JWKS mất kết nối

Nếu public key không nằm trong cache và JWKS endpoint đang outage, verification không thể hoàn thành. Hành vi phải **fail closed** hoặc trả lỗi availability đúng policy, tuyệt đối không cho qua unsigned token. Thiết kế timeout, retries giới hạn, cache và key-rotation transition có test để giữ khả năng phục vụ mà không phá trust boundary.

### 13.4. Nhiều tenants/issuers

Trong SaaS multi-tenant, mỗi issuer có thể có JWKS và audience policy riêng. Không tạo một “hộp khóa công khai” chung rồi chấp nhận mọi JWT do bất cứ key nào ký. Nếu dùng `JwtIssuerReactiveAuthenticationManagerResolver` để route, chỉ route trong danh sách issuer đã được cấu hình tin cậy; không dùng `iss` chưa verify làm URL mạng tùy ý.

### 13.5. JWT signature vs business authorization

Ngay cả JWT hợp lệ có scope `reports.read` chưa bảo đảm user `alice` được đọc báo cáo `bob`. Ở service/database vẫn phải kiểm tra owner/tenant từ nguồn đáng tin; method security `@PreAuthorize`, `ReactiveAuthorizationManager` và checks trên resource có thể bổ sung. Không lấy `owner` do client tự khai làm bằng chứng quyền sở hữu dữ liệu.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `ReactiveJwtDecoder.decode` trả kiểu gì?  
**Đáp án:** `Mono<Jwt>` khi hợp lệ; error signal nếu JWT parse/verification/validation thất bại.

**Câu 2.** Mặc định Spring Security 6.5 reactive JWT Resource Server tin JWS alg nào?  
**Đáp án:** **RS256**.

**Câu 3.** Vì sao không cho client chọn allowed alg qua JWT header?  
**Đáp án:** Header là dữ liệu chưa xác minh do attacker điều khiển, có thể gây algorithm confusion.

**Câu 4.** `kid` có tự chứng minh key thuộc issuer không?  
**Đáp án:** Không. Nó chỉ giúp chọn key **trong trusted JWKS**, không cho phép tải URL từ client header.

**Câu 5.** RS256 và PS256 dùng cùng RSA keypair có đồng nghĩa không?  
**Đáp án:** Không. Hai signing schemes khác nhau; RS256-only decoder phải từ chối PS256.

**Câu 6.** JWT signature đúng nhưng `aud=payments-api` có vào `reports-api` không?  
**Đáp án:** Không; audience không khớp.

**Câu 7.** `JwtValidators.createDefaultWithIssuer` quan trọng vì sao?  
**Đáp án:** Giữ default validators, gồm thời gian, và xác minh issuer; không bỏ đi khi thêm audience check.

**Câu 8.** Resource Server có cần private key để kiểm tra RS256 không?  
**Đáp án:** Không. Nó chỉ cần public key; private key do issuer giữ để ký.

**Câu 9.** HMAC HS256 khác RS256 về trust boundary thế nào?  
**Đáp án:** HS256 dùng shared secret mà bên verify cũng có thể ký; RS256 verify bằng public key tách khỏi private signing key.

**Câu 10.** Nếu JWT hợp lệ nhưng thiếu `SCOPE_reports.read`, HTTP status thông thường là gì?  
**Đáp án:** **403**, vì authentication đã pass nhưng authorization thiếu.

**Câu 11.** Nếu token không có signature, đặt `alg=none`, API cần làm gì?  
**Đáp án:** Từ chối, không bỏ qua verification.

**Câu 12.** `mockJwt()` test pass có chứng minh Remote JWKS/signature đúng không?  
**Đáp án:** Không; mock bypass decoder. Phải test với signed JWT và network/JWKS path riêng.

**Câu 13.** Custom `@Bean ReactiveJwtDecoder` có tự thừa hưởng mọi Boot YAML `audiences` không?  
**Đáp án:** Không nên giả định; phải tự gắn validator theo policy vào bean custom.

**Câu 14.** Một JWT có issuer chính xác nhưng audience của web frontend?  
**Đáp án:** Phải bị API từ chối, dù ký bằng key IdP tin cậy.

**Câu 15.** Vì sao không kéo JWKS từ `jku` bất kỳ do JWT cung cấp?  
**Đáp án:** SSRF/key injection: verifier có thể dùng key do attacker sở hữu.

**Câu 16.** Khi rotate RSA key nhưng vẫn RS256, có phải bật ES256 không?  
**Đáp án:** Không. Key rotation là đổi key ID/material; algorithm migration là thay đổi chính sách riêng.

## 15. Checklist production và nguồn tham khảo

- [ ] Spring WebFlux dùng `ReactiveJwtDecoder`/ `ServerHttpSecurity`, không lẫn Servlet decoder.
- [ ] Trusted JWS algorithm allowlist có căn cứ từ AS và **không phụ thuộc header của request**.
- [ ] Trusted JWKS URL được quản trị, không nhận `jku/x5u` tùy ý.
- [ ] RSA/EC/HMAC key types được ràng buộc đúng algorithm, không cho `none`.
- [ ] Chỉ public verification keys nằm tại Resource Server; private signing keys được bảo vệ tại AS.
- [ ] Chữ ký, issuer, audience, `exp`, `nbf` được kiểm tra.
- [ ] Custom validator không loại bỏ default timestamp/issuer checks.
- [ ] Token type/profile đủ rõ để ngăn OIDC ID token bị dùng như OAuth access token.
- [ ] JWT valid vẫn phải qua URL, method, scope và object/tenant authorization.
- [ ] Có negative tests wrong alg/key/issuer/aud/exp/nbf/unsigned.
- [ ] `mockJwt` chỉ dùng cho authz tests, có signed-token tests độc lập.
- [ ] Có integration test dùng trusted JWKS network/server và key rotation trước production.
- [ ] Key rotation, JWKS outage/cache, clock skew, timeout/retry được vận hành theo fail-closed.
- [ ] Không `block()` hoặc `subscribe()` tùy tiện trong WebFlux request.
- [ ] Không log Bearer token, private key, shared secret hoặc JWT claims nhạy cảm.
- [ ] Java/Spring Boot/Spring Security bản production còn được hỗ trợ.

**Kết luận:** `ReactiveJwtDecoder` không chỉ đọc JWT — nó là một phần **ranh giới tin cậy** giữa token người gửi đưa vào và `JwtAuthenticationToken` được Spring Security chấp nhận. Hãy giới hạn JWS algorithm ở **phía server**, chọn keys từ **issuer JWKS đáng tin**, kiểm tra claims về issuer/audience/time/token type và **sau đó** kiểm tra scope/permission. Test decoder bằng **JWT thực sự được ký**, còn test authorization HTTP bằng `WebTestClient`; không nhầm hai loại chứng cứ này.

**Tài liệu chính thức:**

- Spring Security 6.5 – Reactive JWT Resource Server, trusted algorithms, JWKS và validators: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.5 – `ReactiveJwtDecoder` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html
- Spring Security 6.5 – `NimbusReactiveJwtDecoder` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html
- Spring Security 6.5 – `JwtValidators`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html
- Spring Security 6.5 – `NimbusJwtEncoder`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusJwtEncoder.html
- Spring Security 6.5 – Reactive JWT tests: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Boot 3.5.16 release/end of OSS support: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
- RFC 7515 – JSON Web Signature: https://www.rfc-editor.org/rfc/rfc7515
- RFC 7517 – JSON Web Key: https://www.rfc-editor.org/rfc/rfc7517
- RFC 7518 – JSON Web Algorithms: https://www.rfc-editor.org/rfc/rfc7518
- RFC 7519 – JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- RFC 8725 – JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 9068 – JWT Profile for OAuth2 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
- OWASP JSON Web Token Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html
