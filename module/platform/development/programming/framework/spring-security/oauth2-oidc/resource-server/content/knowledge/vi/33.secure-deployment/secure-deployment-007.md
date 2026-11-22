# Phân phối khóa xác minh, tránh đưa khóa ký bất đối xứng vào Resource Server

Trong OAuth 2.0 Resource Server dùng JWT, Authorization Server (AS) ký access token bằng **private signing key**. Resource Server chỉ cần **public verification key** để xác minh chữ ký và claims. Phân phối đúng public key giúp nhiều API xác minh token độc lập mà không phải chia sẻ bí mật có khả năng ký token.

Nguyên tắc quan trọng là: **private key thuộc về issuer và vùng ký token; Resource Server chỉ nhận public key qua một kênh tin cậy như JWKS/metadata discovery**. Nếu đưa private signing key vào Resource Server, một API bị xâm nhập có thể bị lợi dụng để tạo JWT giả mạo issuer, mở rộng ảnh hưởng từ một service sang toàn bộ hệ thống tin cậy key đó.

Bài học này trình bày cách phân phối public verification keys bằng JSON Web Key Set (JWKS), cấu hình Spring Security Servlet/WebFlux, quản lý `kid` và thuật toán, xoay vòng khóa an toàn, xử lý key compromise, cache JWKS, multi-issuer, kiểm thử và vận hành.

## 1. Ranh giới tin cậy giữa nơi ký và nơi xác minh

Với chữ ký bất đối xứng như RS256 hoặc ES256, một cặp khóa có hai vai trò:

- Private key ký JWT. Chỉ AS hoặc signing service được ủy quyền mới được sử dụng.
- Public key xác minh chữ ký. Có thể phân phối cho các Resource Servers cần tin cậy issuer.

~~~text
                  TRUST BOUNDARY: AUTHORIZATION SERVER
                  ------------------------------------
                  Private signing key (KMS / HSM)
                             |
                             | sign JWT (RS256 / ES256)
                             v
Client ---- access token JWT ----> API Gateway / Resource Server
                                           |
                                           | fetch public keys
                                           v
                                   HTTPS JWKS endpoint
                                           |
                                           v
                                  Public verification key
                                           |
                                           v
                                  Verify signature + claims
~~~

Resource Server không cần và không nên có private signing key để xác minh token. Nếu một API có private key, bất kỳ lỗ hổng đọc file, environment variable, heap dump, container image hoặc secret store nào cũng có thể biến API đó thành một issuer giả mạo.

### 1.1. Public key không phải secret, nhưng tính toàn vẹn của nó rất quan trọng

Public key có thể được công bố công khai. Tuy nhiên, Resource Server phải chắc chắn public key đó thực sự thuộc issuer đã cấu hình. Nếu attacker thay thế JWKS bằng key do họ kiểm soát, Resource Server có thể xác minh JWT giả bằng public key giả.

Do đó cần bảo vệ:

- Tính xác thực của issuer URI và JWKS URI.
- TLS và chứng chỉ của endpoint metadata/JWKS.
- DNS, reverse proxy, CDN và deployment pipeline phân phối JWKS.
- Cấu hình Resource Server, tránh để người dùng chọn tùy ý issuer/JWKS URL.
- Quyền truy cập và audit đối với thao tác publish/rotate keys.

Không cần giữ bí mật public key, nhưng phải bảo vệ đường phân phối để ngăn thay key trái phép.

### 1.2. Vì sao không chia sẻ private key cho mọi Resource Server?

Nếu tất cả services cùng có private signing key:

- Bất kỳ service nào bị compromise đều có thể ký token giả.
- Khó xác định service nào đã phát hành một token.
- Rotation phải phân phối bí mật tới nhiều nơi.
- Secret có thể xuất hiện trong image, backup, CI logs hoặc crash dump.
- Một lỗi quyền truy cập ở Resource Server có thể trở thành compromise toàn bộ trust domain.

Với asymmetric signing, AS giữ private key; Resource Servers nhận public key. Khi cần nhiều issuer hoặc nhiều signing domains, dùng key pair và issuer riêng cho từng trust domain.

## 2. So sánh asymmetric signing và symmetric signing

| Thuật toán / mô hình | Ký | Xác minh | Hệ quả phân phối |
|---|---|---|---|
| RS256 (RSA + SHA-256) | Private RSA key | Public RSA key | Resource Server chỉ cần public key |
| PS256 (RSA-PSS + SHA-256) | Private RSA key | Public RSA key | Resource Server chỉ cần public key |
| ES256 (ECDSA P-256 + SHA-256) | Private EC key | Public EC key | Resource Server chỉ cần public key |
| HS256 (HMAC + SHA-256) | Shared secret | Cùng shared secret | Mỗi verifier cũng có khả năng tạo chữ ký |

Với HS256, cùng một secret dùng để ký và xác minh. Nếu nhiều Resource Servers cùng giữ secret, compromise một Resource Server có thể cho phép attacker ký token mà các Resource Servers khác chấp nhận. Đây là lý do asymmetric signing thường phù hợp hơn khi có nhiều services độc lập.

Không nên kết luận HS256 luôn sai. Nó có thể phù hợp trong một trust boundary nhỏ, nơi signer và verifier cùng được quản trị như một hệ thống. Nhưng nếu muốn Resource Server chỉ có quyền xác minh, asymmetric signing tạo ranh giới quyền rõ hơn.

## 3. JWKS là gì?

JSON Web Key (JWK) là định dạng biểu diễn một khóa mật mã. JSON Web Key Set (JWKS) là một JSON object có thuộc tính `keys`, chứa một mảng JWK. JWKS thường được công bố tại endpoint HTTPS do issuer metadata chỉ ra.

Ví dụ JWKS chỉ chứa public RSA key:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "key_ops": ["verify"],
      "alg": "RS256",
      "kid": "rsa-signing-2026-01",
      "n": "sXch...public-modulus...",
      "e": "AQAB"
    }
  ]
}
~~~

Các trường phổ biến:

| Trường | Ý nghĩa |
|---|---|
| `kty` | Loại khóa, ví dụ `RSA` hoặc `EC` |
| `use` | Mục đích, thường là `sig` cho signing/verification |
| `key_ops` | Các operation được phép; public verifier thường có `verify` |
| `alg` | Thuật toán dự kiến, ví dụ `RS256` |
| `kid` | Key ID để chọn khóa tương ứng với JWT header |
| `n`, `e` | Public modulus và exponent của RSA |
| `crv`, `x`, `y` | Curve và tọa độ public point của EC |

JWK private RSA có thể chứa các trường như `d`, `p`, `q`, `dp`, `dq`, `qi`; private EC có thể chứa `d`; symmetric JWK có thể chứa `k`. **Không publish các private members trong JWKS public endpoint.**

### 3.1. JWT header dùng kid để chọn public key

Một JWT có thể có protected header:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-signing-2026-01",
  "typ": "at+jwt"
}
~~~

Resource Server đọc `kid` để tìm JWK tương ứng trong key set đã cấu hình. `kid` là identifier để lựa chọn key, không phải bằng chứng rằng key đáng tin cậy. Trust vẫn đến từ issuer/JWKS endpoint được cấu hình và xác minh qua TLS/metadata.

`kid` nên duy nhất trong một JWKS tại một thời điểm và ổn định trong suốt vòng đời của key. Không tái sử dụng cùng `kid` cho key material khác nhau vì cache và verifier có thể giữ bản cũ.

### 3.2. JWKS có thể chứa nhiều public keys

Trong thời gian rotation, JWKS thường chứa cả key cũ và key mới:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "key_ops": ["verify"],
      "alg": "RS256",
      "kid": "signing-old",
      "n": "old-public-modulus",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "use": "sig",
      "key_ops": ["verify"],
      "alg": "RS256",
      "kid": "signing-new",
      "n": "new-public-modulus",
      "e": "AQAB"
    }
  ]
}
~~~

Issuer có thể bắt đầu ký token mới bằng `signing-new`, trong khi Resource Servers vẫn xác minh token cũ được ký bằng `signing-old`.

### 3.3. Không đưa private key vào public JWKS

Ví dụ sau là sai đối với public JWKS:

~~~json
{
  "kty": "RSA",
  "kid": "do-not-publish",
  "n": "public-modulus",
  "e": "AQAB",
  "d": "PRIVATE-EXPONENT",
  "p": "PRIVATE-PRIME-P",
  "q": "PRIVATE-PRIME-Q"
}
~~~

Nếu private members bị publish, cần coi signing key đã compromise: dừng sử dụng key, tạo key pair mới, rotate, đánh giá token được ký trong thời gian lộ key và thực hiện incident response. Chỉ xóa các trường private khỏi response không đủ nếu private key đã từng bị truy cập trái phép.

## 4. Phân phối khóa qua issuer metadata và JWKS

Resource Server thường cần biết issuer URI. Từ issuer metadata, nó tìm `jwks_uri` và tải key set.

Với OpenID Connect Discovery, metadata thường được công bố tại:

~~~text
https://id.example.com/.well-known/openid-configuration
~~~

Metadata có thể chứa:

~~~json
{
  "issuer": "https://id.example.com",
  "jwks_uri": "https://id.example.com/oauth2/jwks",
  "authorization_endpoint": "https://id.example.com/oauth2/authorize",
  "token_endpoint": "https://id.example.com/oauth2/token"
}
~~~

Với OAuth 2.0 Authorization Server Metadata, RFC 8414 cũng định nghĩa metadata endpoint và thuộc tính `jwks_uri`. Đối với OpenID Connect, discovery metadata được định nghĩa trong OIDC Discovery specification.

Resource Server không cần lấy private key hoặc client secret từ issuer metadata. `jwks_uri` chỉ là địa chỉ để tải public verification keys.

### 4.1. Luồng discovery và xác minh token

~~~text
Resource Server startup / first request
        |
        | configured issuer URI
        v
Issuer metadata endpoint
        |
        | issuer + jwks_uri
        v
JWKS endpoint
        |
        | public JWK set
        v
JWK cache / key selector
        |
        | JWT header kid + alg
        v
Signature verification
        |
        v
Validate iss / exp / nbf / audience / token profile
        |
        v
Authentication
~~~

### 4.2. HTTPS và cấu hình issuer đáng tin cậy

Trong production:

- Dùng HTTPS cho metadata và JWKS endpoint.
- Cấu hình issuer URI từ trusted deployment configuration.
- Validate issuer claim (`iss`) trong JWT.
- Kiểm tra audience của API.
- Không cho request body/query/header tùy ý chỉ định `jwk-set-uri`.
- Hạn chế outbound network của Resource Server tới các issuer/JWKS hosts được phê duyệt.

Public key không bí mật, nhưng attacker có thể thay key distribution để giả mạo token. TLS certificate validation, issuer pinning/configuration và network egress policy là một phần của trust model.

### 4.3. Không tin jku/x5u do token tự khai

JWT header có thể chứa `jku` hoặc `x5u` để tham chiếu nơi lấy key/certificate. Resource Server không nên tự động fetch URL tùy ý từ header của token. Điều đó có thể tạo SSRF hoặc cho attacker chỉ định key set do họ kiểm soát.

Spring Resource Server nên sử dụng `issuer-uri`/`jwk-set-uri` đã cấu hình và JWK source gắn với issuer tin cậy. Không xây decoder tùy biến đọc URL trong JWT header rồi tải key từ URL đó trừ khi có một protocol chuyên biệt, allowlist và threat model rõ ràng.

## 5. Cấu hình Spring Security Resource Server

Spring Security hỗ trợ JWT verification bằng public keys từ JWKS. Ứng dụng chỉ cần cấu hình issuer hoặc JWK Set URI; không cần cung cấp private signing key.

### 5.1. Spring Boot cấu hình bằng issuer-uri

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com
~~~

Với `issuer-uri`, Spring Security tìm metadata của issuer và lấy JWKS URI. Decoder xác minh chữ ký bằng public key và kiểm tra issuer theo cấu hình.

Ưu điểm:

- Cấu hình theo issuer thay vì hard-code JWKS URL.
- Tự lấy `jwks_uri` từ metadata.
- Có thể dùng issuer validation cùng JWT validation mặc định.
- Key rotation được xử lý thông qua JWKS refresh theo behavior của decoder/library.

### 5.2. Cấu hình trực tiếp jwk-set-uri

Nếu deployment đã biết JWKS endpoint:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://id.example.com/oauth2/jwks
~~~

Khi chỉ cấu hình `jwk-set-uri`, hãy bảo đảm ứng dụng vẫn kiểm tra issuer claim theo trust policy của mình. Có thể cấu hình cả `issuer-uri` và `jwk-set-uri` để giữ issuer validation trong khi không cần metadata discovery tại startup:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com
          jwk-set-uri: https://id.example.com/oauth2/jwks
~~~

Khi kết hợp hai thuộc tính, `issuer-uri` xác định issuer tin cậy và `jwk-set-uri` chỉ rõ nơi lấy public keys. Điều này hữu ích khi metadata discovery endpoint không nên bị gọi trong startup path nhưng Resource Server vẫn cần issuer validation.

### 5.3. SecurityFilterChain cho Servlet

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Boot tạo/configure decoder từ properties. Security chain chỉ bật JWT Resource Server support. Không inject private key vào `HttpSecurity` hoặc `JwtDecoder`.

### 5.4. SecurityWebFilterChain cho WebFlux

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Reactive Resource Server cũng dùng public keys từ issuer/JWKS. Phần khác biệt là reactive decoder và filter chain; trust model phân phối khóa vẫn giống Servlet.

## 6. Giới hạn thuật toán và xác minh claims

Chữ ký hợp lệ chỉ chứng minh JWT được ký bởi một private key tương ứng với public key đã tin cậy. Nó không tự chứng minh token dành cho API hiện tại hoặc có quyền thực hiện thao tác.

Resource Server cần kiểm tra ít nhất:

- Chữ ký theo thuật toán được cho phép.
- Issuer (`iss`) đúng với trust configuration.
- Thời gian (`exp`, `nbf`, và clock skew) hợp lệ.
- Audience (`aud`) bao gồm API hiện tại.
- Token type/profile phù hợp với access token mà API chấp nhận.
- Scope/authorities đủ cho endpoint.

### 6.1. Không để token tự quyết định thuật toán được chấp nhận

JWT header là dữ liệu do người gửi cung cấp. Resource Server phải giới hạn thuật toán được chấp nhận trong cấu hình. Không viết verifier lấy `alg` từ header rồi chấp nhận mọi thuật toán mà thư viện hỗ trợ.

Ví dụ, nếu issuer chỉ ký RS256, cấu hình verifier chỉ chấp nhận RS256. Không chấp nhận `none`, không chuyển tùy tiện từ asymmetric sang HMAC, và không dùng cùng một key material trong các thuật toán có semantics khác nhau.

`alg` trong JWK có thể giúp mô tả key, nhưng policy allowlist của Resource Server mới là ranh giới quyết định.

### 6.2. Cấu hình decoder Servlet với thuật toán và audience rõ ràng

Nếu cần tự tạo decoder thay vì Boot auto-configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtDecoderConfiguration {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer = "https://id.example.com";
        String jwkSetUri = "https://id.example.com/oauth2/jwks";
        String audience = "orders-api";

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Required audience is missing",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                audienceValidator));

        return decoder;
    }
}
~~~

`JwtValidators.createDefaultWithIssuer` cung cấp issuer và timestamp validation mặc định. Audience validator được ghép thêm bằng `DelegatingOAuth2TokenValidator`; đừng vô tình thay thế validator mặc định khi thêm một validator tùy chỉnh.

Ví dụ dùng URL và audience cố định để dễ đọc. Production nên đưa chúng vào trusted configuration, secret/config management phù hợp và deployment environment. JWKS URL không phải secret nhưng vẫn là một cấu hình trust-sensitive.

### 6.3. Cấu hình decoder WebFlux

Reactive decoder có cùng validation policy:

~~~java
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

@Configuration
class ReactiveJwtDecoderConfiguration {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder() {
        String issuer = "https://id.example.com";
        String jwkSetUri = "https://id.example.com/oauth2/jwks";
        String audience = "orders-api";

        NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Required audience is missing",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator));

        return decoder;
    }
}
~~~

Reactive decoder fetches JWKS through its configured reactive infrastructure. Không gọi blocking JWK fetch thủ công trên event-loop.

### 6.4. kid không thay thế signature verification

`kid` chỉ là hint chọn JWK. Một attacker có thể tự tạo JWT với `kid` bất kỳ. Resource Server phải tìm key trong JWKS của issuer đã tin cậy và xác minh chữ ký. Nếu không tìm thấy key phù hợp hoặc chữ ký không đúng, token phải bị từ chối.

Không dùng `kid` làm bằng chứng rằng token được phát hành bởi một user, tenant hoặc client cụ thể.

## 7. Quản lý private signing key tại issuer

Resource Server không cần private key, nhưng issuer phải bảo vệ key ký cẩn thận vì compromise private key cho phép tạo token giả có chữ ký hợp lệ.

### 7.1. KMS hoặc HSM

Nên cân nhắc lưu/generate private key trong:

- Hardware Security Module (HSM).
- Cloud Key Management Service (KMS) có asymmetric signing API.
- Signing service tách biệt có policy và audit riêng.

Application issuer có thể gửi payload/digest tới signing operation được kiểm soát thay vì export private key ra file hoặc environment. Khả năng ký phải được giới hạn theo workload identity, key alias, algorithm và authorization policy.

### 7.2. Quyền tối thiểu

Một signing workload nên có quyền ký bằng đúng key cần thiết. Resource Server workload không cần quyền Sign, Decrypt hoặc export private key. Nó chỉ cần truy cập public JWKS endpoint.

Tách role/identity:

| Workload | Quyền cần thiết |
|---|---|
| Authorization Server / signing service | Sign bằng key được chỉ định |
| JWKS publisher | Publish public JWK tương ứng |
| Resource Server | Fetch/read public JWKS |
| Operator | Rotate/disable key theo approval và audit |
| CI/CD | Deploy cấu hình, không đọc private signing key |

### 7.3. Backup và recovery

Private key backup phải tuân theo policy của KMS/HSM. Không copy private key vào repository hoặc artifact để dễ khôi phục. Quy trình disaster recovery cần chứng minh issuer có thể ký bằng key được khôi phục và Resource Servers có thể nhận public key mới.

### 7.4. Không lưu private key trong Resource Server config

Các ví dụ cần tránh:

~~~yaml
resource-server:
  signing:
    private-key: classpath:private-key.pem
~~~

~~~java
// Resource Server không cần private signing key để verify JWT.
RSAPrivateKey privateKey = loadPrivateSigningKey();
~~~

Nếu ứng dụng vừa là Authorization Server vừa là Resource Server trong cùng một process, private key chỉ nên được inject vào signing component có trách nhiệm rõ ràng. Không đưa private key vào bean hoặc configuration dùng chung chỉ vì hai vai trò nằm cùng deployment.

## 8. Xoay vòng signing key an toàn

Rotation phải cho phép Resource Servers nhận public key mới trước khi issuer bắt đầu ký token bằng private key tương ứng. Đồng thời, public key cũ phải còn được publish đủ lâu để xác minh những access tokens đã phát hành.

### 8.1. Quy trình rotation bình thường

Giả sử issuer đang ký bằng key A và chuẩn bị chuyển sang key B:

~~~text
Phase 1 — Generate
    Generate private/public key pair B in KMS/HSM
    Keep private B accessible only to signing workload

Phase 2 — Publish
    Add public B to JWKS alongside public A
    Keep signing with private A

Phase 3 — Propagate
    Wait for JWKS caches / CDN / Resource Servers to refresh
    Confirm key B is visible to verifiers

Phase 4 — Switch signer
    Sign newly issued JWTs with private B
    JWT header kid = B

Phase 5 — Overlap
    Continue publishing public A and public B
    Resource Servers verify old and new tokens

Phase 6 — Retire
    Wait until every token signed by A has expired
    Remove public A from JWKS
    Retire private A according to key-retention policy
~~~

### 8.2. Vì sao phải publish key mới trước khi ký?

Resource Server có thể đang cache JWKS cũ. Nếu issuer bắt đầu ký token bằng B trước khi Resource Server biết public B, verifier không tìm thấy `kid=B` và request hợp lệ có thể bị từ chối.

Một số thư viện có thể refresh JWKS khi gặp unknown `kid`, nhưng không nên dùng behavior này làm cơ chế rollout duy nhất. Có thể bị ảnh hưởng bởi cache, network outage, rate limiting hoặc version thư viện. Pre-publish và chờ propagation giúp rollout có thể dự đoán.

### 8.3. Giữ key cũ bao lâu?

Gọi:

- `T_last_old`: thời điểm issuer phát hành token cuối cùng bằng key A.
- `L_max`: thời hạn access token tối đa được ký bằng A.
- `S`: clock skew/leeway cho phép.
- `P`: khoảng an toàn cho propagation và vận hành.

Thời điểm sớm nhất nên loại public A khỏi JWKS:

\[
T_{\text{remove A}} \ge T_{\text{last old}} + L_{\text{max}} + S + P
\]

Nếu token có expiry riêng, có thể xác định theo token cuối cùng thực sự được ký bằng A. Nếu không có khả năng thống kê chính xác, dùng maximum lifetime policy của issuer.

Không xóa key A ngay sau khi chuyển signer sang B. Các token còn hạn ký bằng A vẫn cần public A để xác minh.

### 8.4. Lập timeline mẫu

| Thời điểm | JWKS | Signing key | Kết quả |
|---|---|---|---|
| Day 0 | A | A | Hệ thống bình thường |
| Day 1 | A + B | A | Public B được phân phối trước |
| Day 1 sau propagation | A + B | B | Token mới dùng B, token cũ dùng A |
| Sau maximum token lifetime + leeway | A + B | B | Không còn token A hợp lệ theo lifetime policy |
| Sau thời gian overlap | B | B | Có thể retire A |

Thời gian cụ thể phụ thuộc TTL JWKS, CDN cache, token lifetime, clock skew và khả năng refresh của Resource Server.

### 8.5. Đừng thay key material nhưng giữ nguyên kid

Nếu public key A được thay bằng public key B nhưng vẫn dùng cùng `kid`, Resource Server có thể giữ key A trong cache và không biết key material đã đổi. Dùng `kid` mới cho mỗi key pair. Không tái sử dụng `kid` trong khi verifier có thể còn cache phiên bản cũ.

## 9. Xử lý signing key bị compromise

Key compromise khác rotation định kỳ. Nếu attacker có private key, họ có thể tạo JWT giả với bất kỳ subject/scope/audience/expiry nào mà Resource Server chấp nhận theo validator.

### 9.1. Phản ứng khẩn cấp

Khi nghi private signing key bị lộ:

1. Dừng issuer/signing workload dùng key bị compromise.
2. Tạo key pair mới trong KMS/HSM hoặc signing boundary sạch.
3. Publish public key mới và chuyển signer sang key mới.
4. Xóa public key compromise khỏi JWKS theo incident policy.
5. Invalidate/refresh JWKS caches ở CDN, gateway và mọi Resource Servers.
6. Chủ động từ chối `kid` bị compromise nếu cần bảo đảm tức thời trong lúc cache cũ còn tồn tại.
7. Revoke token/session/family có liên quan theo khả năng AS.
8. Điều tra token giả đã được tạo, logs, API usage và dữ liệu bị truy cập.
9. Thông báo cho các Resource Server owners và theo dõi propagation.

### 9.2. Xóa public key khỏi JWKS không tự động có hiệu lực tức thời

Resource Server có thể đã cache public key A. Dù JWKS endpoint đã xóa A, verifier vẫn có thể dùng key A cho đến khi cache refresh hoặc bị invalidated. CDN/proxy cũng có thể giữ JWKS response cũ.

Vì vậy emergency response phải xử lý cả:

- JWKS origin cache.
- CDN/reverse proxy cache.
- Nimbus/JWK cache bên trong ứng dụng.
- Local caches của các Resource Server instances.
- Các node đang offline hoặc không nhận invalidation event.

### 9.3. Block compromised kid

Trong incident, có thể thêm policy từ chối JWT có `kid` bị compromise. Đây là lớp phòng vệ bổ sung khi key cũ còn trong cache. Ví dụ validator:

~~~java
import java.util.Set;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

final class DenyCompromisedKeyIds implements OAuth2TokenValidator<Jwt> {

    private final Set<String> deniedKids;

    DenyCompromisedKeyIds(Set<String> deniedKids) {
        this.deniedKids = Set.copyOf(deniedKids);
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        Object rawKid = jwt.getHeaders().get("kid");
        if (rawKid instanceof String kid && deniedKids.contains(kid)) {
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Signing key is no longer trusted",
                    null));
        }
        return OAuth2TokenValidatorResult.success();
    }
}
~~~

Ghép validator này với issuer/time/audience validators hiện có. Danh sách denied `kid` phải được phân phối qua một control plane tin cậy, có audit và có thể cập nhật nhanh. Không dùng validator này thay cho việc loại key compromise khỏi JWKS và xử lý incident.

### 9.4. Khi attacker đã ký token giả

Token giả được ký bằng private key bị lộ có thể có `exp` rất xa trong tương lai. Khi public key compromise còn được tin cậy, chữ ký của token giả vẫn hợp lệ. Chỉ chờ access token thông thường hết hạn có thể không đủ.

Cần cân nhắc:

- Deny `kid` bị compromise trên toàn bộ Resource Servers.
- Revoke session/token family hoặc account bị ảnh hưởng.
- Dùng denylist hoặc introspection cho các luồng cần thu hồi tức thời.
- Kiểm tra token issuance logs và phát hiện token không được AS thực sự phát hành.
- Đánh giá liệu attacker có thể đã lấy thêm key hoặc credential khác.

### 9.5. Không retire private key mà quên public key và token cũ

Retire private key ngăn ký mới bằng key đó; nó không làm token đã ký biến mất. Public key vẫn cần cho token cũ tới khi hết hạn, trừ trường hợp emergency compromise yêu cầu từ chối toàn bộ token ký bằng key đó.

## 10. JWKS cache và hành vi khi endpoint không khả dụng

Resource Server thường cache JWKS để không tải key set ở mỗi request. JWKS caching khác với introspection caching:

- JWKS cache lưu public key material để xác minh chữ ký.
- Introspection cache lưu trạng thái/claims của token cụ thể.

### 10.1. JWKS cache ảnh hưởng rotation

Nếu Resource Server giữ JWKS cũ, nó có thể:

- Chưa biết key mới và từ chối token vừa được ký bằng key mới.
- Tiếp tục tin key cũ sau khi issuer đã xóa key đó khỏi JWKS.

Vì vậy TTL/cache headers và quy trình rotation phải được phối hợp.

### 10.2. Cache-Control, ETag và CDN

JWKS endpoint có thể sử dụng HTTP caching headers như `Cache-Control`, `ETag` và `Last-Modified` để điều khiển cache/proxy. Cần xác định:

- `max-age` phù hợp với rotation SLA.
- CDN có cache theo đúng endpoint/issuer không.
- Invalidation có thể được thực hiện khẩn cấp khi compromise không.
- Resource Server library có honor HTTP caching headers như kỳ vọng không.
- Unknown `kid` có trigger refresh hay không ở version đang dùng.

Không giả định mọi decoder/library có cùng cache TTL hoặc refresh behavior. Kiểm tra tài liệu version cụ thể và đo hành vi trong integration test.

### 10.3. JWKS endpoint tạm thời down

Nếu Resource Server đã cache public key cần thiết, một số verifier có thể tiếp tục xác minh token bằng key đã biết trong thời gian cache còn hiệu lực. Token dùng key mới chưa cache có thể thất bại khi JWKS endpoint down.

Không nên biến JWKS fetch error thành chấp nhận mọi chữ ký hoặc bỏ qua signature verification. Khi key chưa biết và không thể tải key tin cậy, fail closed là hành vi an toàn.

### 10.4. Stale key và emergency invalidation

Trong rotation bình thường, giữ key cũ trong JWKS overlap window. Trong key compromise, stale cache có thể là rủi ro. Cần có phương án:

- Purge CDN/reverse proxy.
- Force refresh hoặc invalidate JWK cache theo khả năng thư viện.
- Distribute denylist `kid`.
- Restart/replace instances nếu đó là cơ chế được kiểm chứng và có kiểm soát.
- Xác nhận tất cả nodes đã nhận policy mới.

Restart không phải giải pháp tổng quát nếu CDN vẫn trả JWKS cũ hoặc node khởi động lại rồi tải lại cùng cache response stale.

## 11. Nhiều issuer và multi-tenant

Một Resource Server có thể tin cậy nhiều issuer. Khi đó, mỗi issuer có JWKS riêng và validation policy riêng.

### 11.1. Không dùng một JWKS cache namespace cho mọi issuer

Một public key của issuer A không được dùng để xác minh token issuer B chỉ vì thuật toán và `kid` giống nhau. `kid` không nhất thiết duy nhất toàn cầu; nó thường chỉ có ý nghĩa trong key set của issuer.

Cache và decoder phải gắn với issuer:

~~~text
issuer A
    -> metadata A
    -> JWKS A
    -> decoder A
    -> issuer/audience policy A

issuer B
    -> metadata B
    -> JWKS B
    -> decoder B
    -> issuer/audience policy B
~~~

### 11.2. Allowlist issuer

Nếu ứng dụng chọn issuer dựa trên claim `iss` trong JWT, đừng tự động tin bất kỳ URL nào token đưa ra. Một attacker có thể gửi issuer trỏ tới server của họ, khiến Resource Server tải metadata/JWKS tùy ý (SSRF hoặc trust injection).

Chỉ chấp nhận issuer từ allowlist hoặc registry tenant đã được provision và kiểm soát. Kiểm tra issuer trước khi tạo decoder hoặc thực hiện outbound fetch.

### 11.3. Spring Security issuer resolver

Spring Security có các resolver hỗ trợ nhiều issuer, chẳng hạn `JwtIssuerAuthenticationManagerResolver` ở Servlet stack và `JwtIssuerReactiveAuthenticationManagerResolver` ở reactive stack. Khi dùng, cấu hình trusted issuers rõ ràng hoặc cung cấp resolver tra cứu từ registry đã kiểm soát.

Không xây resolver lấy URL từ `iss` rồi fetch bất kỳ endpoint nào mà không kiểm tra allowlist. Multi-tenant discovery phải giới hạn host, scheme, issuer identity, tenant status và cache capacity.

### 11.4. Tenant onboarding và offboarding

Khi thêm tenant:

- Provision issuer URI và JWKS endpoint qua admin/control plane.
- Kiểm tra metadata issuer khớp tenant đã đăng ký.
- Thiết lập audience và scope policy.
- Giới hạn số issuer/decoder/cache entries.

Khi offboard tenant:

- Ngừng chấp nhận issuer đó.
- Xóa/disable decoder mapping và cache namespace.
- Thu hồi tenant credentials/session theo policy.
- Xác nhận không còn route hoặc background process tin cậy issuer đó.

## 12. Bảo vệ JWKS endpoint và signing pipeline

JWKS public endpoint thường không cần authentication vì Resource Servers cần tải public keys. Điều đó không có nghĩa mọi thao tác liên quan key đều public.

### 12.1. Tách read public key và write/publish key

- Public JWKS endpoint: chỉ đọc public JWK set.
- Signing API/KMS: chỉ workload ký được gọi.
- Key management API: chỉ operator/control plane được phép tạo, rotate, disable key.
- Deployment pipeline: chỉ publish public material đã được phê duyệt.

Không dùng cùng endpoint hoặc credential để vừa đọc JWKS vừa upload private key.

### 12.2. Publish JWKS theo kiểu atomic

Khi cập nhật JWKS, publish một document hoàn chỉnh và nhất quán. Tránh để endpoint tạm thời trả JSON thiếu key, key trùng `kid` hoặc key set chỉ có một phần trong lúc deployment.

Nếu dùng object storage/CDN, có thể upload version mới rồi chuyển pointer/route atomically. Kiểm tra response thực tế sau publish trước khi chuyển signer.

### 12.3. Kiểm tra nội dung JWKS trước khi publish

Pipeline có thể kiểm tra:

- JSON parse được và có `keys` array.
- Mỗi key có `kty`, `kid` và public parameters phù hợp.
- Không có private parameters như `d`, `p`, `q`, `dp`, `dq`, `qi` hoặc symmetric secret `k`.
- `kid` không trùng trong set.
- `use`/`key_ops` phù hợp với verification.
- `alg` thuộc allowlist.
- Key size/curve đáp ứng cryptographic policy.
- Public key khớp key pair mà signing service đang dùng.

Kiểm tra key pair bằng cách ký một test payload trong pipeline và xác minh bằng public JWK tương ứng trước khi publish/switch.

### 12.4. Network egress và SSRF

Resource Server chỉ nên kết nối metadata/JWKS endpoints đã được cấu hình. Với multi-tenant dynamic discovery, registry phải kiểm soát issuer và host; không cho user-controlled URL đi vào HTTP client.

Đặt outbound network policy, DNS resolution policy, timeout và response size limit. JWKS endpoint chỉ nên trả payload nhỏ có cấu trúc; giới hạn kích thước response để giảm rủi ro resource exhaustion.

## 13. Kiểm thử phân phối và rotation key

Một test chỉ dùng `mockJwt()` không chứng minh JWKS endpoint, key selection hoặc signature verification hoạt động. Cần kiểm thử ít nhất một request với JWT ký thật và decoder lấy public key từ JWKS endpoint.

### 13.1. Test với local JWKS server

Trong integration test:

1. Tạo RSA key pair A dành riêng cho test.
2. Tạo JWKS JSON chỉ chứa public JWK A.
3. Khởi động mock HTTP server cục bộ tại một URI cố định.
4. Cấu hình `jwk-set-uri` trỏ tới mock server.
5. Dùng private A ký JWT có `kid=A`.
6. Gửi Bearer token qua WebTestClient/MockMvc và assert endpoint chấp nhận.

Mock server giúp test không phụ thuộc Internet hoặc Authorization Server thật. Dùng private key test sinh riêng, không dùng key production.

### 13.2. Test key rotation

Một kịch bản integration:

~~~text
JWKS version 1 = public A
Signer = private A
Token A -> Resource Server accepts

JWKS version 2 = public A + public B
Wait/force JWKS refresh as test setup requires
Signer switches to private B
Token B -> Resource Server accepts
Token A -> Resource Server still accepts

JWKS version 3 = public B only
After token A expires and cache refreshes:
Token B -> Resource Server accepts
Token A -> Resource Server rejects (or is expired)
~~~

Đừng dùng thời gian sleep tùy tiện để giả lập cache. Nếu có thể, cấu hình cache/test clock có thể điều khiển hoặc chủ động làm mới JWKS theo API mà thư viện hỗ trợ. Nếu không, dùng TTL ngắn trong test và chờ có giới hạn.

### 13.3. Test token dùng kid không tồn tại

Ký token bằng key C nhưng JWKS chỉ chứa A/B. Resource Server phải từ chối vì không có trusted verification key phù hợp. Không fallback sang một key bất kỳ hoặc chấp nhận token chỉ vì `iss` hợp lệ.

### 13.4. Test sai chữ ký nhưng kid đúng

Tạo JWT có header `kid=A` nhưng ký bằng private key khác. JWKS chứa public A. Decoder phải từ chối chữ ký. Điều này chứng minh hệ thống không chỉ kiểm tra sự tồn tại của `kid`.

### 13.5. Test algorithm policy

Nếu API chỉ chấp nhận RS256:

- Token RS256 với key hợp lệ: được xác minh.
- Token dùng thuật toán không được phép: bị từ chối.
- Token `alg=none`: bị từ chối.
- Token cố gắng dùng HMAC với public RSA material: bị từ chối.

### 13.6. Test issuer và audience riêng

Tạo JWT có chữ ký đúng nhưng:

- Issuer khác trusted issuer.
- Audience không chứa API hiện tại.
- Token đã hết hạn.
- `nbf` ở tương lai ngoài clock skew cho phép.

Các token này phải bị từ chối dù chữ ký cryptographically valid.

### 13.7. Test private material không xuất hiện trong JWKS

Pipeline test có thể parse JWKS response và assert không có private JWK members. Với RSA, kiểm tra không có `d`, `p`, `q`, `dp`, `dq`, `qi`; với EC, không có `d`; với octet/symmetric key, không có `k`.

## 14. Kiểm thử sự cố key distribution

### 14.1. JWKS endpoint trả 5xx

Test xác minh:

- Token dùng key đã cache có behavior theo policy của decoder/cache.
- Token dùng `kid` mới chưa biết không được chấp nhận nếu không thể lấy public key tin cậy.
- Error được log/metric mà không lộ token.
- Request không bị treo vô hạn; HTTP timeout có giới hạn.

### 14.2. JWKS response malformed

Nếu JSON lỗi, key thiếu public parameter hoặc có duplicate `kid`, decoder phải từ chối load key set hoặc không thể xác minh token tương ứng. Pipeline publish nên phát hiện trước khi document được đưa vào production.

### 14.3. Key compromise và denylist

Test `DenyCompromisedKeyIds` với token có `kid` bị block và token có `kid` mới. Đảm bảo denylist được cập nhật trên mọi nodes và không vô tình block issuer khác có cùng `kid` nhưng thuộc namespace khác.

### 14.4. Multi-issuer isolation

Tạo hai issuer test A/B với cùng `kid` nhưng key pair khác nhau. Token A phải được xác minh bằng decoder A; token B bằng decoder B. Không cho token issuer A xác minh bằng public key của B.

## 15. Quan sát và vận hành key distribution

Phân phối khóa là một dependency runtime của JWT verification. Nếu JWKS endpoint hoặc cache gặp sự cố, Resource Server có thể từ chối token hợp lệ mới hoặc tiếp tục tin key cũ lâu hơn dự kiến.

### 15.1. Metrics hữu ích

Có thể theo dõi:

| Metric | Ý nghĩa |
|---|---|
| JWKS fetch count | Số lần Resource Server tải JWKS |
| JWKS fetch latency | Thời gian lấy key set |
| JWKS fetch errors | Timeout, TLS failure, HTTP 4xx/5xx, malformed JSON |
| JWK cache hit/miss | Cache behavior theo decoder/library |
| Unknown kid count | Token có key ID chưa có trong JWKS hiện tại |
| Signature validation failures | Chữ ký không hợp lệ hoặc không tìm được key |
| Issuer/audience validation failures | Token sai trust context |
| Key rotation propagation time | Thời gian từ publish public key tới lúc các nodes xác nhận nhìn thấy |
| Compromised kid denials | Số token bị từ chối bởi emergency deny policy |

Tên metric là gợi ý. Labels phải bounded như issuer alias, environment, outcome và resource-server name. Không đưa toàn bộ JWT, subject hoặc token ID vào metrics.

### 15.2. Structured logs

Log sự kiện có thể hữu ích:

~~~text
event=jwks_fetch issuer=main outcome=success key_count=2
event=jwks_fetch issuer=main outcome=error reason=timeout
event=jwt_validation issuer=main outcome=invalid_signature
event=jwt_validation issuer=main outcome=unknown_kid
event=key_rotation issuer=main phase=public_key_published kid_alias=signing-next
event=key_rotation issuer=main phase=signer_switched kid_alias=signing-next
event=key_compromise issuer=main action=deny_kid kid_alias=signing-old
~~~

Không log token raw hoặc private key. `kid` có thể được log nếu đó là identifier không chứa bí mật và được xử lý theo log policy; nếu `kid` được coi là dữ liệu nội bộ nhạy cảm, dùng alias.

### 15.3. Alert nên gắn với impact

Alert hữu ích:

- JWKS endpoint không thể truy cập trong thời gian vượt threshold.
- JWKS response malformed hoặc không có key dùng được.
- Unknown `kid` tăng đột biến ngoài lịch rotation.
- Signature failures tăng bất thường.
- Một số nodes không thấy public key mới sau propagation deadline.
- Key sắp hết thời gian overlap nhưng token cũ vẫn được phát hành.
- Denylist compromise chưa được xác nhận trên tất cả nodes.

Một vài signature failure có thể do token sai hoặc client lỗi; alert nên dựa trên tỷ lệ, issuer/resource context và pattern thay vì từng request đơn lẻ.

### 15.4. Runbook khi token hợp lệ đột nhiên bị 401

Kiểm tra:

1. JWT header có `kid` nào?
2. JWKS endpoint của đúng issuer có chứa key đó không?
3. Resource Server đang dùng đúng issuer/JWKS URI không?
4. CDN/proxy có đang trả JWKS cũ không?
5. Decoder/JWK cache có refresh theo version và policy hiện tại không?
6. Thuật toán token có nằm trong allowlist không?
7. Chữ ký có verify được bằng public key đã tải không?
8. Issuer, audience, `exp` và `nbf` có hợp lệ không?
9. Có nhiều security chains/decoder khiến request đi nhầm cấu hình không?

Không giải quyết lỗi bằng cách disable signature/issuer/audience validation hoặc chấp nhận bất kỳ key nào.

### 15.5. Runbook khi token giả vẫn được chấp nhận

Kiểm tra:

1. Token `kid` có bị compromise hoặc đã bị retire không?
2. Public key tương ứng còn trong JWKS/cache không?
3. Resource Server có đang tin issuer/JWKS URI bị thay đổi trái phép không?
4. Có resolver multi-issuer cho phép issuer tùy ý không?
5. Có custom decoder tin `jku`/`x5u` từ JWT header không?
6. Có validator bỏ qua `iss`, `aud`, `exp` hoặc algorithm allowlist không?
7. Denylist compromised `kid` đã được áp dụng trên mọi nodes chưa?

## 16. Những lỗi triển khai thường gặp

### 16.1. Đưa private key vào Resource Server

Resource Server chỉ cần public key để verify. Private key trong API làm tăng blast radius và cho phép tạo token giả khi API bị compromise.

### 16.2. Publish private members trong JWKS

JWKS public chỉ chứa public key parameters. Private RSA/EC/symmetric members phải được giữ trong key management boundary.

### 16.3. Chỉ kiểm tra chữ ký mà không kiểm tra issuer/audience

Token có chữ ký hợp lệ từ một issuer hoặc audience khác vẫn có thể không dành cho API hiện tại. Xác minh chữ ký, issuer, audience, thời gian và scope là các bước riêng.

### 16.4. Tin kid mà không verify signature

`kid` chỉ giúp chọn key. Không chấp nhận token chỉ vì key ID tồn tại trong JWKS.

### 16.5. Chấp nhận thuật toán do token header tự chọn

Pin thuật toán theo issuer policy. Không chấp nhận `none` hoặc algorithm fallback ngoài dự kiến.

### 16.6. Thay signer trước khi publish public key mới

Resource Server có thể chưa cache key mới. Pre-publish, đợi propagation, rồi mới chuyển signer.

### 16.7. Xóa public key cũ ngay sau khi rotation

Token cũ còn hạn sẽ không thể verify. Giữ key overlap tới khi mọi token cũ hết hạn và cache/clock allowance được tính đến.

### 16.8. Giữ cùng kid cho key pair mới

Cache có thể nhầm key material cũ và mới. Mỗi key pair cần một `kid` ổn định, mới và không tái sử dụng trong thời gian có cache.

### 16.9. Dựa vào JWKS cache TTL cho emergency revocation

Xóa key khỏi JWKS không xóa ngay key đang cache. Cần cache invalidation, CDN purge và emergency deny policy nếu compromise.

### 16.10. Dynamic issuer không có allowlist

Đừng fetch metadata/JWKS từ issuer URL do token hoặc user tùy ý cung cấp. Điều này tạo SSRF và trust injection.

### 16.11. Dùng symmetric secret trong mọi Resource Server

Với HMAC, mỗi verifier cũng có thể ký. Nếu cần phân tách quyền ký và xác minh giữa services, ưu tiên asymmetric key pair.

### 16.12. Nghĩ JWKS endpoint phải được bảo vệ như private key

JWKS public endpoint có thể cho phép GET công khai. Điều phải bảo vệ là quyền publish/modify key set và tính toàn vẹn của đường phân phối.

## 17. Checklist triển khai

### 17.1. Key ownership

- [ ] Private signing key chỉ nằm trong AS/signing service/KMS/HSM.
- [ ] Resource Server chỉ có public verification keys.
- [ ] Signing permission và key export permission được giới hạn.
- [ ] Private key backup/recovery theo policy của KMS/HSM.
- [ ] CI/CD và Resource Server identities không đọc được private signing key.

### 17.2. JWKS và trust configuration

- [ ] JWKS public endpoint chỉ chứa public JWK members.
- [ ] `kid` duy nhất và không tái sử dụng cho key material khác.
- [ ] `kty`, `use`, `key_ops`, `alg` và public parameters phù hợp.
- [ ] Metadata/JWKS được tải qua HTTPS.
- [ ] Issuer URI/JWKS URI là trusted configuration.
- [ ] Issuer, audience, expiry và not-before được validate.
- [ ] Thuật toán được pin theo allowlist.
- [ ] Không fetch `jku`/`x5u` tùy ý từ token header.
- [ ] Multi-issuer có allowlist/tenant registry và cache isolation.

### 17.3. Rotation và incident

- [ ] Public key mới được publish trước khi signer dùng key mới.
- [ ] Có propagation wait/verification trước khi switch signer.
- [ ] Key cũ được giữ đủ lâu cho token cũ hết hạn.
- [ ] `kid` mới được cấp cho mỗi key pair.
- [ ] Có quy trình emergency key compromise.
- [ ] Có khả năng invalidate CDN/JWK caches hoặc deny compromised `kid`.
- [ ] Có cách xác nhận policy mới tới mọi Resource Server nodes.

### 17.4. Testing và operations

- [ ] Integration test dùng JWT ký thật qua JWKS endpoint.
- [ ] Test unknown `kid`, wrong signature và unsupported algorithm.
- [ ] Test issuer, audience, exp và nbf.
- [ ] Test key overlap/rotation và old-key retirement.
- [ ] Test JWKS endpoint outage/malformed response.
- [ ] Test multi-issuer isolation.
- [ ] Metrics theo dõi fetch errors, unknown kid và rotation propagation.
- [ ] Logs không chứa token/private key.
- [ ] Runbook xử lý key compromise và stale JWKS cache.

## 18. Kết luận

Với asymmetric JWT signing, Authorization Server giữ private signing key và Resource Server chỉ nhận public verification keys. JWKS là cách tiêu chuẩn để công bố public keys; issuer metadata cho biết JWKS endpoint; Spring Security có thể cấu hình qua `issuer-uri` hoặc `jwk-set-uri` cho cả Servlet và WebFlux.

Phân phối khóa chỉ an toàn khi Resource Server tin đúng issuer, tải key từ endpoint đã cấu hình, pin thuật toán, xác minh chữ ký và kiểm tra issuer/audience/time claims. `kid` hỗ trợ chọn key nhưng không thay thế signature verification.

Rotation bình thường cần pre-publish key mới, chờ cache propagation, chuyển signer, giữ key cũ tới khi token cũ hết hạn rồi mới retire. Khi private key bị compromise, phải dừng ký, thay key, invalidation JWKS caches và có thể block `kid` cũ để ngăn token giả còn được xác minh bằng stale cache.

**Resource Server không cần quyền ký token để thực hiện vai trò xác minh.** Giữ private key trong KMS/HSM hoặc signing boundary riêng, phân phối public key qua JWKS có xác thực, và kiểm thử rotation/compromise trên mọi instances là nền tảng của trust model an toàn.

## Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — JwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtDecoder.html)
- [Spring Security — ReactiveJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html)
- [Nimbus JOSE + JWT](https://connect2id.com/products/nimbus-jose-jwt)

