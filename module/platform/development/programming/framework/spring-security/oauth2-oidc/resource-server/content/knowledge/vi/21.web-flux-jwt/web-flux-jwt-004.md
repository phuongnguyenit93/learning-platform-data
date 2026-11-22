# Kiểm tra chữ ký, issuer, audience và mốc thời gian

## 1. Vì sao JWT có chữ ký hợp lệ vẫn có thể bị từ chối?

Trong **Spring Security OAuth 2.0/OIDC Resource Server sử dụng WebFlux**, client gửi access token đến API qua cơ chế HTTP Bearer:

    GET /api/orders/42 HTTP/1.1
    Host: orders-api.example.com
    Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0...

Một JWT được ký đúng **chưa tự chứng minh nó được dùng cho API đang nhận request**. Resource Server phải kiểm tra đồng thời:

1. **Chữ ký JWS**: JWT được ký bằng khóa đáng tin và thuật toán đã được cho phép?
2. **Issuer (iss)**: token do đúng Authorization Server mà API tin cậy phát hành?
3. **Audience (aud)**: token được phát hành cho API hiện tại, không phải API khác?
4. **Mốc thời gian (exp và nbf)**: token còn trong cửa sổ hiệu lực?
5. **Issued At (iat)**: nếu API yêu cầu token freshness hoặc max-age, iat có đạt chính sách riêng không?
6. **Token purpose/profile**: token là access token dành cho Resource Server, không phải OIDC ID token hoặc JWT assertion?
7. **Authorization**: sau khi token được xác thực, scope, role và domain policy có cho phép hành động không?

Cần tách **xác thực credential** và **phân quyền nghiệp vụ**. Một token có chữ ký, issuer, audience và thời hạn đúng nhưng chỉ có scope orders.read có thể được xác thực thành công; nếu endpoint đòi orders.write, request thường bị từ chối với HTTP 403. Ngược lại, một JWT có scope orders.write nhưng aud=billing-api phải bị chặn ở bước token acceptance, thường HTTP 401.

Có thể hình dung:

    tokenAccepted =
        signatureValid
        AND jwsAlgorithmAllowed
        AND issuerTrusted
        AND audienceMatchesResource
        AND timeWindowValid
        AND tokenProfileValid

    requestAllowed =
        tokenAccepted
        AND scopeOrAuthorityAllowed
        AND domainPermissionAllowed

**Các điều kiện chữ ký, issuer, audience và thời gian hoạt động theo phép AND. Không điều kiện nào thay thế được điều kiện khác.**

## 2. Vị trí của JWT verification trong Spring WebFlux

Luồng điển hình:

    HTTP Authorization: Bearer JWT
                 |
                 v
    ServerWebExchange / WebFilterChainProxy
                 |
                 v
    AuthenticationWebFilter
                 |
                 v
    ServerBearerTokenAuthenticationConverter
      trích raw credential, chưa xác thực
                 |
                 v
    BearerTokenAuthenticationToken
                 |
                 v
    ReactiveAuthenticationManager
                 |
                 v
    ReactiveJwtDecoder
      - parse JWS
      - lấy key từ trusted JWKS
      - verify chữ ký và thuật toán
      - validate iss, aud, exp, nbf, token profile
                 |
                 v
    Authentication với principal và authorities
                 |
                 v
    ReactiveSecurityContextHolder
                 |
                 v
    WebFlux authorization / method security
                 |
                 v
    Controller / domain service

Các thành phần:

| Thành phần | Vai trò |
|---|---|
| **ServerBearerTokenAuthenticationConverter** | Lấy Bearer credential từ ServerWebExchange |
| **BearerTokenAuthenticationToken** | Mang raw token trước khi xác thực |
| **ReactiveAuthenticationManager** | Điều phối quá trình authentication |
| **ReactiveJwtDecoder** | API reactive để decode/verify/validate JWT |
| **NimbusReactiveJwtDecoder** | Implementation Spring Security sử dụng Nimbus JOSE + JWT |
| **OAuth2TokenValidator<Jwt>** | Hợp đồng validation JWT claims |
| **JwtIssuerValidator** | Kiểm tra iss |
| **JwtTimestampValidator** | Kiểm tra exp và nbf với clock skew |
| **DelegatingOAuth2TokenValidator** | Kết hợp nhiều validators |
| **ServerHttpSecurity** | DSL cấu hình WebFlux security |
| **SecurityWebFilterChain** | Chuỗi WebFilters bảo vệ request |
| **ReactiveSecurityContextHolder** | SecurityContext theo Reactor Context |

So sánh hai stack:

| Servlet | WebFlux |
|---|---|
| HttpSecurity | ServerHttpSecurity |
| SecurityFilterChain | SecurityWebFilterChain |
| JwtDecoder | ReactiveJwtDecoder |
| NimbusJwtDecoder | NimbusReactiveJwtDecoder |
| HttpServletRequest | ServerWebExchange |
| Servlet Filter | WebFilter |
| Thread-local security context thường gặp | Reactor Context |

**Không sao chép JwtDecoder/HttpSecurity của Servlet và gọi block() để dùng trong WebFlux.** Với WebFlux, dùng thành phần reactive và để security pipeline xác thực token trước khi controller được phép dùng claims.

ReactiveJwtDecoder.decode(String) trả **Mono<Jwt>**. Nếu token được xác thực, Mono phát Jwt; nếu không, quá trình decode/validate báo error. Một Jwt object dựng thủ công trong unit test không chứng minh JWT đã được verify chữ ký.

## 3. JWT, JWS và chữ ký khác việc đọc JSON

JWT access token được ký thường dùng **JWS Compact Serialization**:

    BASE64URL(Protected Header)
        .
    BASE64URL(Payload)
        .
    BASE64URL(Signature)

Ví dụ header:

    {
      "alg": "RS256",
      "typ": "at+jwt",
      "kid": "rsa-2026-11"
    }

Ví dụ payload:

    {
      "iss": "https://auth.example.com/realms/shop",
      "sub": "user-42",
      "aud": ["orders-api"],
      "scope": "orders.read orders.write",
      "client_id": "shop-web",
      "iat": 1794729600,
      "nbf": 1794729600,
      "exp": 1794731400
    }

Đây là các giá trị minh họa, không phải JWT đã ký thật. Ba bước phải tách biệt:

- **Base64URL decoding** chỉ giải mã bytes để đọc header/payload; không xác thực.
- **JWS signature verification** kiểm tra dữ liệu đã được ký bằng key đáng tin.
- **Claims validation** kiểm tra issuer, audience, thời hạn, token type và những ràng buộc khác.

Attacker có thể tự tạo JSON khai sub=admin và scope=orders.admin rồi Base64URL encode. Nếu một filter tự viết đọc những claims đó trước khi verify signature, nó có thể cấp quyền sai nghiêm trọng.

**JWS ký payload, không mã hóa payload.** Token có thể mang dữ liệu cá nhân đọc được nếu bị lộ. JWE là cơ chế mã hóa khác; không giả định JWT decoder JWS tự xử lý mọi JWE hoặc nested JWT.

## 4. Nguồn key tin cậy và JWKS

Với bất đối xứng RSA/EC:

    Authorization Server:
      giữ private signing key
      ký JWT access token
             |
             v
    OAuth Client:
      chuyển Bearer JWT tới Resource Server
             |
             v
    WebFlux Resource Server:
      lấy public verification key từ nguồn tin cậy
      verify JWS signature

**JWKS (JSON Web Key Set)** là tập các JSON Web Keys do issuer công bố, thường qua một HTTPS endpoint. Ví dụ rút gọn:

    {
      "keys": [
        {
          "kty": "RSA",
          "kid": "rsa-2026-11",
          "use": "sig",
          "alg": "RS256",
          "n": "PUBLIC_MODULUS_BASE64URL",
          "e": "AQAB"
        }
      ]
    }

Đây là key giả định, không dùng được cho verify. Các field:

| Field | Ý nghĩa |
|---|---|
| **kty** | Key type, ví dụ RSA, EC, OKP |
| **kid** | Key ID để chọn key trong key set |
| **use** | Key purpose như sig, nếu được khai |
| **key_ops** | Các thao tác key cho phép, nếu có |
| **alg** | Thuật toán tương ứng nếu có |
| **n, e** | RSA public key components |

Public JWKS không được chứa private key components như RSA d/p/q. Với symmetric key, trường k của JWK dạng oct là secret, **không được đưa lên public JWKS**.

Chữ ký hợp lệ với **public key do attacker tự đưa ra** không chứng minh token đáng tin. Resource Server phải nhận key từ **issuer/JWKS đã được cấu hình và cho phép**.

## 5. alg, kid và chính sách tin cậy

Header:

    {
      "alg": "RS256",
      "kid": "key-a"
    }

- **alg** nói JWS algorithm ghi trong token.
- **kid** giúp chọn public key phù hợp trong JWKS đã được tin cậy.
- Cả hai đều là dữ liệu của token; chúng không được tự thay đổi trust policy.

Một thiết kế sai:

    Đọc alg từ token -> tự bật thuật toán bất kỳ.
    Đọc kid từ token -> tạo URL tải public key.
    Đọc jku/x5u từ token -> HTTP request đến host tùy ý.
    Verify bằng key đó -> tin user claims.

Thiết kế đúng:

    Configured issuer allow-list
       -> trusted JWKS/key source
       -> allowed JWS algorithms
       -> chọn candidate key theo kid/kty/alg
       -> verify signature
       -> validate iss/aud/exp/nbf/profile

### Algorithm confusion

Một lỗi lịch sử xảy ra khi verifier đáng lẽ dùng RSA public key để kiểm tra RS256 nhưng lại chấp nhận HS256 do JWT tự khai, và dùng RSA public key bytes làm HMAC secret. Một implementation yếu kiểu này có thể bị giả mạo MAC.

Cách tránh:

1. Chỉ cho phép JWS algorithms đã thỏa thuận với AS.
2. Kiểm tra algorithm tương thích key type.
3. Không tự chuyển thuật toán theo token.
4. Không chấp nhận unsigned alg=none làm signed access token.
5. Không dùng một RSA public key làm symmetric HMAC secret.

### kid không phải global identifier

Hai issuer có thể cùng kid là signing-2026. Không dùng kid như ID của issuer hoặc khóa toàn cục. Tìm key theo kid **trong JWKS của đúng issuer**. Khi không tìm được kid, có thể do key rotation, cache cũ, sai JWKS URI hoặc token giả; không tự tải JWKS bất kỳ từ header do caller cung cấp.

## 6. Những thuật toán JWS thường gặp

| Algorithm | Cơ chế ký | Key verify | Ghi chú |
|---|---|---|---|
| RS256 | RSA PKCS#1 v1.5 + SHA-256 | RSA public key | Spring Security default phổ biến |
| RS512 | RSA + SHA-512 | RSA public key | Chỉ bật khi issuer dùng |
| PS256 | RSA-PSS + SHA-256 | RSA public key | Cần issuer/decoder hỗ trợ |
| ES256 | ECDSA + SHA-256 | EC P-256 public key | Không dùng RSA key |
| ES384 | ECDSA + SHA-384 | EC P-384 public key | Phải khớp curve |
| EdDSA | Edwards curve | OKP public key | Phụ thuộc version/provider |
| HS256 | HMAC + SHA-256 | Shared secret | Bên verify có secret cũng có thể ký |
| none | Không ký | Không | Không phù hợp signed Bearer JWT |

Spring Security Reference mô tả **NimbusReactiveJwtDecoder mặc định tin và verify RS256** trong cấu hình JWT Resource Server tiêu chuẩn. Nếu AS thực sự dùng ES256 hoặc RS512, chỉ thêm algorithm đó sau khi đã xác định contract, key family và khả năng hỗ trợ.

Cấu hình Spring Boot:

    spring:
      security:
        oauth2:
          resourceserver:
            jwt:
              issuer-uri: https://auth.example.com/realms/shop
              jws-algorithms:
                - RS256

Cấu hình Java minh họa:

    import org.springframework.context.annotation.Bean;
    import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
    import org.springframework.security.oauth2.jwt.JwtValidators;
    import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
    import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        String issuer = "https://auth.example.com/realms/shop";

        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withIssuerLocation(issuer)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .build();

        decoder.setJwtValidator(
                JwtValidators.createDefaultWithIssuer(issuer));

        return decoder;
    }

Đoạn code chọn RS256 và issuer đáng tin. Nếu dùng HMAC, lưu ý secret phải được giữ kín và phân phối khác asymmetric public key.

## 7. Issuer: trường iss xác định ai phát hành

Issuer claim:

    {
      "iss": "https://auth.example.com/realms/shop"
    }

Spring Boot configuration:

    spring:
      security:
        oauth2:
          resourceserver:
            jwt:
              issuer-uri: https://auth.example.com/realms/shop

AS có thể có nhiều realms:

    https://auth.example.com/realms/shop
    https://auth.example.com/realms/admin
    https://auth.example.com/realms/partners

Chúng có thể dùng cùng phần mềm IAM, thậm chí cùng hạ tầng, nhưng vẫn có issuer identifiers và policies khác nhau. Token phát từ admin realm không mặc nhiên được chấp nhận ở API chỉ tin shop realm.

### Exact issuer matching

    Expected:
      https://auth.example.com/realms/shop

    Received:
      https://auth.example.com/realms/shop/

Hai URI khác nhau bởi trailing slash không mặc nhiên đồng nhất trong issuer validation. Không tự rewrite hostname/path/realm một cách tùy tiện để token được chấp nhận. Điều chỉnh AS/RS theo metadata contract.

**Signature và issuer đều phải hợp lệ:**

- iss đúng nhưng signature sai: reject.
- signature verify với key khác nhưng iss sai: reject.
- signature/iss đúng nhưng aud sai: reject.

Đọc iss từ JWT chưa verify chỉ có thể làm **routing hint** cho trusted issuer allow-list, không phải quyền yêu cầu API tự khám phá một issuer mới.

## 8. Audience: token được phát cho API nào?

Audience claim:

    {
      "aud": ["orders-api"]
    }

RFC 7519 cho phép aud ở dạng string hoặc mảng string. Spring Security Jwt cung cấp getAudience() để lấy danh sách audience.

Một access token có:

    {
      "iss": "https://auth.example.com/realms/shop",
      "sub": "user-42",
      "aud": ["billing-api"],
      "scope": "orders.read",
      "exp": 1794731400
    }

**không được dùng tại orders-api** nếu orders-api yêu cầu aud chứa orders-api. Một scope có tên orders.read không thể thay audience validation.

Một audience validator đơn giản:

    jwt.getAudience().contains("orders-api")

### client_id không thay aud

- **aud** là intended recipient/resource của JWT.
- **client_id** là OAuth Client được cấp token.
- **scope/scp** là các phạm vi quyền được cấp.
- **sub** là subject trong phạm vi issuer.

Token dành cho orders-api được cấp cho client shop-web có thể mang cả aud=orders-api và client_id=shop-web; hai field không có cùng ý nghĩa.

### Multi-audience

    {
      "aud": ["orders-api", "inventory-api"]
    }

Nếu token profile cho phép nhiều audience, validator contains("orders-api") có thể chấp nhận. Nếu API yêu cầu chỉ một audience, phải thêm kiểm tra riêng. Token đa audience có thể tăng nơi Bearer token được dùng lại, nên cần xem least privilege.

## 9. Spring Boot YAML: issuer, audience, key set

Spring Boot hỗ trợ property audiences cho cả Servlet và reactive Resource Server ở các phiên bản phù hợp.

    spring:
      security:
        oauth2:
          resourceserver:
            jwt:
              issuer-uri: https://auth.example.com/realms/shop
              audiences:
                - orders-api
              jws-algorithms:
                - RS256

Có thể khai trực tiếp JWKS URI tin cậy:

    spring:
      security:
        oauth2:
          resourceserver:
            jwt:
              issuer-uri: https://auth.example.com/realms/shop
              jwk-set-uri: https://auth.example.com/realms/shop/jwks
              audiences:
                - orders-api
              jws-algorithms:
                - RS256

JWKS URI trong ví dụ chỉ là placeholder. Không có một path JWKS được chuẩn hóa cho mọi Authorization Server.

**issuer-uri xác định trust identity**; **jwk-set-uri xác định nguồn public keys**. Khi tự tạo decoder chỉ với jwk-set-uri, cần giữ issuer validator. Đừng mặc định property issuer-uri trong YAML sẽ tự gắn vào một custom ReactiveJwtDecoder bean đã override auto-configuration.

## 10. SecurityWebFilterChain cho JWT Resource Server

    import org.springframework.context.annotation.Bean;
    import org.springframework.context.annotation.Configuration;
    import org.springframework.http.HttpMethod;
    import org.springframework.security.config.Customizer;
    import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
    import org.springframework.security.config.web.server.ServerHttpSecurity;
    import org.springframework.security.web.server.SecurityWebFilterChain;

    @Configuration
    @EnableWebFluxSecurity
    public class OrdersSecurity {

        @Bean
        SecurityWebFilterChain api(ServerHttpSecurity http) {
            return http
                    .authorizeExchange(auth -> auth
                            .pathMatchers("/api/public/**").permitAll()
                            .pathMatchers(HttpMethod.GET, "/api/orders/**")
                                .hasAuthority("SCOPE_orders.read")
                            .pathMatchers(HttpMethod.PUT, "/api/orders/**")
                                .hasAuthority("SCOPE_orders.write")
                            .anyExchange().authenticated())
                    .oauth2ResourceServer(oauth2 -> oauth2
                            .jwt(Customizer.withDefaults()))
                    .build();
        }
    }

Resource Server xử lý:

1. Trích Bearer credential.
2. Verify JWS và validate issuer/audience/temporal claims.
3. Tạo authenticated principal và authorities.
4. Xét scope/authority theo WebFlux HTTP security.
5. Có thể xét thêm tenant, ownership, resource status và quyền hiện hành trong domain.

**hasAuthority không tự verify JWT.** Nó dựa vào Authentication đã được Resource Server xác thực. JWT chữ ký sai không được vào giai đoạn authorization như một principal đáng tin.

## 11. Thời gian JWT sử dụng NumericDate

RFC 7519 có:

| Claim | Ý nghĩa | Vai trò |
|---|---|---|
| **exp** | Expiration Time | Không chấp nhận token sau thời điểm hết hạn, với tolerance hợp lý |
| **nbf** | Not Before | Token chưa có hiệu lực trước mốc này |
| **iat** | Issued At | Thời điểm token phát hành; có thể dùng cho custom freshness |
| **auth_time** | OIDC authentication time | Không giống iat |
| **expires_in** | OAuth response field | Thời lượng, không phải JWT exp |
| **jti** | JWT ID | Không phải mốc thời gian |

Ví dụ:

    {
      "iat": 1794729600,
      "nbf": 1794729600,
      "exp": 1794731400
    }

Khoảng exp - iat là **1.800 giây = 30 phút**.

JWT NumericDate là **seconds since Unix epoch**, không phải milliseconds:

    JWT seconds:     1794729600
    Milliseconds:    1794729600000

AS ghi milliseconds vào exp dưới dạng seconds có thể tạo token trông còn hạn rất lâu. Cần sửa token producer, không nới verifier để chấp nhận thời gian vô lý.

## 12. exp: hết hạn và cửa sổ chấp nhận thực tế

    Resource Server UTC: 10:31:00
    JWT exp:             10:30:00

JWT đã qua thời điểm expiration. JwtTimestampValidator thường kiểm tra exp, có **clock skew tolerance** để xử lý sai lệch đồng hồ.

Một access token chưa exp có thể vẫn mang role cũ:

    09:00 AS phát token scope=orders.write, exp=09:20
    09:05 Admin thu hồi write
    09:06 JWT cũ vẫn chứa scope=orders.write

Nếu API chỉ dựa JWT scope, quyền cũ có thể còn được sử dụng cho đến khi token hết hạn. exp không phải current-entitlement lookup. Nếu yêu cầu revocation gần tức thời, cần token revocation/denylist, versioning, short TTL hoặc domain authorization hiện hành.

### exp missing

Không nên giả định **mọi version JwtTimestampValidator đều mặc định yêu cầu exp tồn tại**. Spring Security 7.x có API kiểm soát việc cho phép thiếu exp và nbf, và default có thể cho phép field thiếu. Nếu token profile của API bắt buộc exp:

    Condition 1: exp phải hiện diện.
    Condition 2: exp phải chưa hết hạn theo temporal validator.

Cần required-exp validator tường minh, không chỉ dựa vào một assumption về default behavior.

## 13. nbf: thời điểm bắt đầu hiệu lực

Ví dụ:

    {
      "iat": 1794729600,
      "nbf": 1794730200,
      "exp": 1794731400
    }

Token có thể được phát trước nhưng chỉ được dùng sau nbf.

    iat = 09:00
    nbf = 09:10
    exp = 09:30

Không ép iat=nbf. Nếu now trước nbf, JWT phải bị từ chối theo temporal policy, trừ clock skew được cho phép.

nbf là optional theo JWT general specification nhưng một profile riêng có thể yêu cầu nó. Nếu API bắt buộc nbf, cần validator kiểm tra claim tồn tại.

## 14. iat không tự thay exp hoặc max-age

iat cho biết JWT được phát hành lúc nào.

    iat = 09:00
    exp = 09:30
    now = 09:25

Token còn hạn nhưng đã 25 phút tuổi. Nếu API muốn maxAge 10 phút, phải thêm policy riêng. **JwtTimestampValidator không tự hứa sẽ kiểm tra max token age chỉ vì JWT có iat.**

Một token có:

    now = 10:00
    iat = 11:00

có thể bị xem là có issuer clock sai hoặc token profile sai. Nếu API muốn chặn iat trong tương lai quá leeway, cần validator như iat <= now + futureLeeway.

Trong OIDC, **auth_time** chỉ thời điểm user authentication tại OP; **iat** chỉ thời điểm token phát hành. Refresh token flow có thể tạo access token mới với iat mới dù user không vừa đăng nhập.

## 15. Clock skew: vì sao token vừa cấp có thể bị 401?

    Authorization Server UTC: 10:00:00
    Resource Server UTC:     09:59:53
    Lệch:                   7 giây

Nếu nbf=10:00:00, Resource Server nhận token ngay có thể thấy nbf ở tương lai. JwtTimestampValidator dùng **clock skew tolerance**. Tài liệu Spring Security mô tả mức leeway mặc định **60 giây** trong các version được dẫn.

Tư duy xấp xỉ:

    nbf validity: now + skew >= nbf
    exp validity: now - skew < exp

Clock skew nới cửa sổ chấp nhận, không chỉ giúp nhận token mới. Nếu skew quá lớn, token có thể được chấp nhận lâu sau exp hoặc trước nbf.

Khuyến nghị:

- Đồng bộ NTP/chrony.
- Dùng UTC nhất quán.
- Chọn skew nhỏ theo đo lường.
- Giám sát clock drift từng instance.
- Không dùng skew sửa NumericDate sai đơn vị.
- Tính skew vào token lifetime/revocation SLA.

## 16. Cấu hình custom NimbusReactiveJwtDecoder đầy đủ

Khi cần audience và required exp rõ ràng:

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
    public class OrdersJwtValidationConfig {

        private static final String ISSUER =
                "https://auth.example.com/realms/shop";
        private static final String AUDIENCE = "orders-api";

        @Bean
        ReactiveJwtDecoder reactiveJwtDecoder() {
            NimbusReactiveJwtDecoder decoder =
                    NimbusReactiveJwtDecoder.withIssuerLocation(ISSUER)
                            .jwsAlgorithm(SignatureAlgorithm.RS256)
                            .build();

            OAuth2TokenValidator<Jwt> defaults =
                    JwtValidators.createDefaultWithIssuer(ISSUER);

            OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
                    jwt.getAudience().contains(AUDIENCE)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Required audience missing",
                                        null));

            OAuth2TokenValidator<Jwt> requiredExp = jwt ->
                    jwt.getExpiresAt() != null
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Required exp missing",
                                        null));

            decoder.setJwtValidator(
                    new DelegatingOAuth2TokenValidator<>(
                            defaults,
                            audienceValidator,
                            requiredExp));

            return decoder;
        }
    }

Các ý chính:

1. **withIssuerLocation** dùng trusted issuer để lấy metadata/JWKS.
2. **jwsAlgorithm(RS256)** hạn chế allowed signature algorithm.
3. **JwtValidators.createDefaultWithIssuer** giữ issuer/time defaults theo version.
4. **audienceValidator** yêu cầu aud chứa orders-api.
5. **requiredExp** đòi claim exp hiện diện theo token contract.
6. **DelegatingOAuth2TokenValidator** kết hợp các điều kiện.
7. **setJwtValidator thay các validators đã gắn với decoder**, nên phải giữ toàn bộ yêu cầu cần thiết.

Code chỉ minh họa một issuer/RS256/audience. Nếu AS dùng RFC 9068 hay profile riêng, cần token-purpose và required-claim validation phù hợp.

## 17. Tùy biến JwtTimestampValidator và clock skew

Có thể dùng:

    import java.time.Duration;
    import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

    JwtTimestampValidator timestamp =
            new JwtTimestampValidator(Duration.ofSeconds(30));

Ghép với các validator khác:

    import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
    import org.springframework.security.oauth2.jwt.JwtIssuerValidator;

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    timestamp,
                    new JwtIssuerValidator(ISSUER),
                    audienceValidator,
                    requiredExpiration));

Các biến decoder, audienceValidator và requiredExpiration được giả định tạo trong cùng method; đây là fragment chỉ cách ghép.

**Không gọi setJwtValidator hai lần rồi tưởng lần sau chỉ thêm một validator.** Lần sau thay tổ hợp trước. Phải giữ issuer, audience, timestamp, required claims và token purpose.

Spring Security 7.x có các setter cho phép/không cho phép exp hoặc nbf vắng mặt; không sao chép method của 7.x sang 6.x nếu API chưa có.

## 18. Custom iat max-age validator

Nếu contract yêu cầu access token không quá 10 phút tuổi, có thể thêm:

    import java.time.Clock;
    import java.time.Duration;
    import java.time.Instant;
    import org.springframework.security.oauth2.core.OAuth2Error;
    import org.springframework.security.oauth2.core.OAuth2TokenValidator;
    import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
    import org.springframework.security.oauth2.jwt.Jwt;

    public final class TokenAgeValidator
            implements OAuth2TokenValidator<Jwt> {

        private final Duration maxAge;
        private final Duration futureLeeway;
        private final Clock clock;

        public TokenAgeValidator(
                Duration maxAge, Duration futureLeeway, Clock clock) {
            this.maxAge = maxAge;
            this.futureLeeway = futureLeeway;
            this.clock = clock;
        }

        @Override
        public OAuth2TokenValidatorResult validate(Jwt jwt) {
            Instant iat = jwt.getIssuedAt();

            if (iat == null) {
                return reject("iat is required");
            }

            Instant now = clock.instant();

            if (iat.isAfter(now.plus(futureLeeway))) {
                return reject("iat is too far in the future");
            }

            if (iat.isBefore(now.minus(maxAge))) {
                return reject("token exceeds permitted max age");
            }

            return OAuth2TokenValidatorResult.success();
        }

        private OAuth2TokenValidatorResult reject(String reason) {
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token", reason, null));
        }
    }

Tạo:

    OAuth2TokenValidator<Jwt> maxAge =
            new TokenAgeValidator(
                    Duration.ofMinutes(10),
                    Duration.ofSeconds(30),
                    Clock.systemUTC());

Phải ghép cùng issuer, audience và exp/nbf validators. **Max age là policy tùy chọn**, không tự có trong JWT general specification. Nếu AS cố ý cấp token 30 phút mà API yêu cầu 10 phút, client/AS và Resource Server phải thống nhất.

## 19. OIDC ID token không phải JWT access token

Một ID token:

    {
      "iss": "https://auth.example.com/realms/shop",
      "sub": "user-42",
      "aud": "shop-web-client",
      "iat": 1794729600,
      "exp": 1794730200
    }

Access token cho orders-api:

    {
      "iss": "https://auth.example.com/realms/shop",
      "sub": "user-42",
      "aud": ["orders-api"],
      "scope": "orders.read",
      "iat": 1794729600,
      "exp": 1794731400
    }

Hai token có thể dùng cùng issuer/JWKS nhưng có **audience/purpose khác nhau**.

- ID token dùng cho OIDC Client/Relying Party.
- Access token dùng cho Resource Server.
- Refresh token, JWT client assertion hoặc logout token có thể có mục đích khác.
- Không coi tất cả JWT có signature đúng là API access token.

Nếu AS phát hành **RFC 9068 JWT Access Token Profile**, Resource Server có thể cần validate typ=at+jwt và các required claims của profile. Spring Security có hỗ trợ profile validator như JwtValidators.createAtJwtValidator() trong các phiên bản phù hợp. Cấu hình JOSE type validation có thể cần phối hợp với builder validateTypes(false). Không áp đặt RFC 9068 cho một issuer đang dùng token profile khác mà chưa thống nhất.

## 20. Discovery, jwk-set-uri và key rotation

Với issuer-uri, Spring Security có thể dùng OIDC Provider Configuration hoặc OAuth Authorization Server Metadata để tìm jwks_uri. Metadata rút gọn:

    {
      "issuer": "https://auth.example.com/realms/shop",
      "jwks_uri": "https://auth.example.com/realms/shop/jwks"
    }

Nếu khai trực tiếp jwk-set-uri, Resource Server có thể tránh dependency vào metadata discovery ở một số thời điểm khởi tạo, nhưng vẫn cần tải trusted public keys.

Spring Boot/Spring Security có cơ chế **lazy decoder initialization**, chẳng hạn SupplierReactiveJwtDecoder trong những cấu hình phù hợp. Custom decoder bean tạo bằng withIssuerLocation có thể truy cập metadata ở thời điểm khác. Không khẳng định mọi cấu hình đều chờ AS ở startup hay mọi cấu hình đều lazy.

### Rotation timeline

    T0: AS ký JWT bằng key kid=old.
    T1: AS công bố JWKS gồm old và new.
    T2: AS bắt đầu ký JWT bằng kid=new.
    T3: RS refresh trusted JWKS nếu cần.
    T4: Token cũ hết hạn; AS có thể loại old khỏi JWKS.

Overlap giúp giảm lỗi do JWKS cache chưa cập nhật. Khi token kid=new bị từ chối:

- Kiểm tra issuer, jwks_uri và HTTPS trust.
- Kiểm tra kid/kty/alg tương thích.
- Kiểm tra JWKS cache/refresh.
- Kiểm tra AS đã công bố new key trước khi ký token mới chưa.
- Không bỏ signature verification để chữa lỗi.

**JWKS timeout không tự chứng minh token expired.** Khi không có trusted key phù hợp, phải fail closed nhưng ghi nhận dependency/trust error chính xác trong metrics.

## 21. Multi-issuer: issuer chưa verify chỉ được dùng như routing hint

Một API có thể chấp nhận:

    Issuer A: https://auth.example.com/realms/shop
    Issuer B: https://auth.example.com/realms/partners
    Issuer C: https://login.partner.net/

Mỗi issuer có JWKS và validators riêng:

    JWT incoming
         |
         v
    Đọc iss như untrusted routing hint
         |
         v
    Trusted issuer allow-list
         |
         +-- A -> decoder/JWKS A
         +-- B -> decoder/JWKS B
         +-- C -> decoder/JWKS C
         |
         v
    Verify signature + exact issuer
         |
         v
    Validate audience + time + token purpose

Không dùng iss trong JWT chưa verify để tự tải JWKS của issuer bất kỳ, vì có nguy cơ SSRF hoặc tạo trust domain do attacker điều khiển. Trong WebFlux có thể dùng reactive authentication-manager resolver với trusted-issuer strategy; không sao chép HttpServletRequest-based resolver của Servlet.

Hai issuers có thể cùng sub=123 hoặc kid=signing-key nhưng vẫn là hai user/two key namespaces khác nhau. Khi mapping local identity, thường dùng **(issuer, subject)**, không dùng sub một mình.

## 22. Lỗi 401/403 trong JWT Resource Server

| Tình huống | Tầng xử lý | HTTP điển hình |
|---|---|---|
| Không Bearer token ở protected endpoint | Authentication required | 401 |
| JWT signature sai | ReactiveJwtDecoder | 401 invalid_token |
| JWS algorithm không được phép | Signature policy | 401 invalid_token |
| iss sai | Issuer validator | 401 invalid_token |
| aud sai | Audience validator | 401 invalid_token |
| exp đã qua | Timestamp validator | 401 invalid_token |
| nbf chưa tới | Timestamp validator | 401 invalid_token |
| iat vi phạm custom max-age | Custom validator | 401 invalid_token |
| ID token dùng thay access token | Token-purpose check | 401 invalid_token |
| Token hợp lệ, thiếu orders.write | Authorization | 403 insufficient_scope khi phù hợp |
| Token hợp lệ, sai tenant/ownership | Domain authorization | 403 hoặc domain-specific denial |
| JWKS fetch timeout | Dependency/trust | Fail closed, không tự kết luận token expired |

Ví dụ:

    HTTP/1.1 401 Unauthorized
    WWW-Authenticate: Bearer error="invalid_token"

Và:

    HTTP/1.1 403 Forbidden
    WWW-Authenticate: Bearer error="insufficient_scope"

Không trả raw token, private key, stack trace hoặc dữ liệu authorization nhạy cảm trong response lỗi.

## 23. Ma trận test chữ ký, issuer, aud và thời gian

Các tình huống này là **thiết kế kịch bản test**, không phải kết quả đã chạy.

| Input | Kỳ vọng |
|---|---|
| JWT ký đúng trusted RS256 key, iss/aud/time đúng | Authentication thành công nếu profile đạt |
| Sửa payload sau ký | Signature rejection |
| JWT ký bằng key của issuer lạ | Reject |
| alg=none | Reject |
| alg=HS256 trong decoder chỉ cho RS256 | Reject |
| kid không nằm trong trusted JWKS | Reject hoặc trusted refresh; không tin key lạ |
| Issuer khác realm | Reject |
| Issuer khác bởi trailing slash | Reject nếu exact issuer mismatch |
| aud=billing-api | Reject ở orders-api |
| aud chứa orders-api trong array | Có thể pass audience check nếu profile cho phép |
| Thiếu aud khi audience required | Reject |
| exp hết hạn ngoài skew | Reject |
| nbf future ngoài skew | Reject |
| exp mới qua trong leeway | Theo clock skew policy |
| iat tương lai | Reject khi future-iat policy bật |
| iat quá cũ | Reject khi max-age policy bật |
| exp thiếu | Reject nếu profile đòi required-exp |
| Chữ ký và claims đúng nhưng thiếu scope | Authenticated, authorization có thể 403 |
| ID token dùng làm API credential | Reject theo token purpose/aud |
| JWKS cache stale sau rotation | Fail closed, điều tra key refresh |
| Replica RS clock lệch | Temporal errors có thể không nhất quán |

**Unit tests của validators** chỉ xác nhận predicate trên Jwt object, không chứng minh signature được verify. **ReactiveJwtDecoder integration tests** cần signed tokens và trusted test keys. **WebTestClient security integration tests** kiểm tra request đi qua WebFlux SecurityWebFilterChain và kết quả HTTP 401/403, WWW-Authenticate. Spring Security Test mockJwt() có thể tạo Authentication giả, phù hợp test authorization nhưng không thay thế crypto verification tests.

## 24. Chẩn đoán khi JWT nhận 401

Một luồng điều tra:

    [1] Authorization: Bearer có được gửi?
     |
     v
    [2] Bearer converter trích được credential?
     |
     v
    [3] JWT compact format hợp lệ?
     |
     v
    [4] JWS alg nằm trong allow-list?
     |
     v
    [5] Trusted JWKS có key tương thích kid/alg?
     |
     v
    [6] Signature verify đúng?
     |
     v
    [7] iss exact match?
     |
     v
    [8] aud chứa Resource Server?
     |
     v
    [9] exp/nbf hợp lệ với skew?
     |
     v
    [10] Token purpose/required claims hợp lệ?
     |
     v
    [11] Optional iat freshness policy có đạt?
     |
     v
    [12] Scope/domain authorization đủ?

Thứ tự thật của decoder có thể khác sơ đồ; đây là checklist chẩn đoán, không phải một test thực thi.

| Triệu chứng | Khả năng nguyên nhân |
|---|---|
| Mọi token 401 sau deploy | Sai issuer-uri/jwk-set-uri/alg, custom decoder override |
| Token cũ pass, token mới 401 | Key rotation, kid, JWKS cache |
| JWT scope đúng nhưng 401 | Signature/iss/aud/time/purpose chưa đạt |
| JWT vừa phát nhưng nbf future | Clock skew hoặc issuer clock sai |
| exp chưa hết nhưng vẫn 401 | Sai iss/aud/alg/nbf hoặc maxAge policy |
| exp missing vẫn pass | Required exp validator chưa có |
| iat future vẫn pass | Chưa cấu hình future-iat rule |
| JWT authenticated nhưng 403 | SCOPE_ mapping hoặc domain policy |
| Chỉ một RS instance lỗi | Clock/config drift hoặc JWKS cache |
| JWKS lỗi TLS/timeout | Truststore, hostname, AS availability |
| ID token được nhận làm access token | Token-purpose/audience policy thiếu |

### Logging an toàn

Ghi request ID, issuer configuration ID, loại lỗi signature/issuer/audience/expired/not_before, JWKS fetch status và latency. Không log raw access token, Authorization header, private key hoặc full payload có PII. Trước verify, các trường kid và iss là dữ liệu chưa đáng tin; không dùng raw values làm metrics labels không giới hạn.

## 25. Những anti-pattern cần tránh

| Anti-pattern | Nguy cơ | Giải pháp |
|---|---|---|
| Chỉ decode Base64URL | Không xác thực signature | ReactiveJwtDecoder |
| Chỉ so sánh iss | Attacker tự khai issuer | Verify JWS bằng trusted key |
| Chỉ verify signature | Token sai issuer/audience vẫn có thể lọt | Claim validators |
| Dùng scope thay aud | Token substitution giữa APIs | Require audience |
| Tin alg do JWT tự chọn | Algorithm confusion | Allowed algorithms |
| Chấp nhận alg=none | Không có chữ ký | Require signed JWT |
| kid tự trỏ URL JWKS | SSRF/key substitution | Trusted JWKS URI |
| Bỏ qua exp required | Credential có thể sống quá lâu | Required-exp validator |
| Dùng iat thay exp | Sai semantics | Exp/nbf và optional max-age |
| Clock skew cực lớn | Nới token validity | NTP, bounded skew |
| Chấp nhận OIDC ID token làm access token | Cross-JWT confusion | Profile và audience |
| Dùng JwtDecoder Servlet rồi block | Sai reactive architecture | ReactiveJwtDecoder |
| Custom WebFilter tự tạo authenticated JWT | Có thể bypass security | Resource Server chuẩn |
| setJwtValidator chỉ có aud | Mất issuer/time checks | Delegating validators |
| JWKS timeout thì cho token qua | Fail open | Fail closed |
| Mock JWT test rồi tin crypto đã chạy | Decoder không nhất thiết chạy | Signed JWT integration tests |
| Log raw Bearer JWT | Lộ credential | Sanitized telemetry |

## 26. Tổng kết

    JWT access token
         |
         v
    ReactiveJwtDecoder
         |
         +-- Trusted signature key + allowed JWS alg
         |
         +-- Issuer exact match
         |
         +-- Audience intended for this API
         |
         +-- exp/nbf validity, bounded clock skew
         |
         +-- Required token purpose/claims
         |
         +-- Optional iat freshness policy
         |
         v
    Authenticated principal
         |
         v
    Scope / authorities / domain authorization
         |
         v
    Protected business operation

Những nguyên tắc quan trọng:

1. **Verify signature bằng key và thuật toán đáng tin**, không chỉ đọc payload.
2. **iss khớp issuer mà Resource Server tin cậy**; không tự tải issuer/JWKS tùy ý từ token chưa xác thực.
3. **aud phải dành cho API hiện tại**; client_id và scope không thay aud.
4. **exp/nbf là cửa sổ hiệu lực**; clock skew chỉ để dung sai đồng hồ nhỏ.
5. **iat không tự là expiration hoặc max-age**; chính sách iat tùy chọn phải được định nghĩa rõ.
6. **Token purpose và required claims** phải theo access-token profile của issuer.
7. **Custom validators phải được ghép đầy đủ**, đặc biệt khi gọi setJwtValidator.
8. **Dùng ReactiveJwtDecoder và SecurityWebFilterChain trong WebFlux**, không tạo filter JWT song song.
9. **OIDC ID token không phải API access token**, dù cùng issuer/signing key.
10. **Token hợp lệ chưa đủ cho business action**; cần xét scope, tenant và domain permissions sau authentication.

**Kết luận:** Một JWT chỉ được Spring Security WebFlux Resource Server chấp nhận khi JWS signature, issuer, audience, temporal window và token profile cùng đạt trust contract. ReactiveJwtDecoder chịu trách nhiệm token acceptance; WebFlux authorization và domain policy quyết định hành động tiếp theo.

## 27. Tài liệu tham khảo

- **Spring Security — Reactive OAuth 2.0 Resource Server JWT:** signature, issuer, JWKS, audience, timestamps và ReactiveJwtDecoder. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security — Reactive Resource Server:** WebFlux Bearer architecture. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html
- **Spring Security API — NimbusReactiveJwtDecoder:** withIssuerLocation, withJwkSetUri, setJwtValidator. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html
- **Spring Security API — JwtTimestampValidator:** exp/nbf và clock skew. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html
- **Spring Boot — Resource Server:** issuer-uri, audiences và jwk-set-uri cho WebFlux/Servlet. https://docs.spring.io/spring-boot/reference/security/oauth2.html
- **Spring Security — WebFlux Security:** ServerHttpSecurity/SecurityWebFilterChain. https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- **Spring Security — Reactive JWT 6.5:** đối chiếu API các version 6.x. https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- **RFC 7519 — JWT:** iss, aud, exp, nbf, iat và NumericDate. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 7515 — JWS:** chữ ký, protected header. https://www.rfc-editor.org/rfc/rfc7515
- **RFC 7517 — JWK:** JSON Web Keys và JWKS. https://www.rfc-editor.org/rfc/rfc7517
- **RFC 7518 — JWA:** algorithms và key compatibility. https://www.rfc-editor.org/rfc/rfc7518
- **RFC 8725 — JWT Best Current Practices:** thuật toán, issuer, audience, token confusion. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access token purpose và required claims. https://www.rfc-editor.org/rfc/rfc9068
- **OpenID Connect Core:** ID token, aud và auth_time. https://openid.net/specs/openid-connect-core-1_0.html
