# Introspection, JWKS và các khả năng cần kiểm chứng ở từng môi trường

Khi tích hợp **Spring Security OAuth 2.0/OIDC Resource Server** với một Authorization Server (AS), việc biết URL `issuer-uri` hoặc nhận được một access token chưa đủ để kết luận tích hợp đã sẵn sàng. Resource Server còn phụ thuộc vào các khả năng cụ thể của nhà phát hành: **metadata discovery**, **JWK Set (JWKS)** để xác minh JWT, **token introspection** để kiểm tra trạng thái token, cơ chế xác thực client tại introspection endpoint, chính sách audience, key rotation, TLS, cache, timeout và khả năng phục hồi khi AS gặp sự cố.

Những khả năng đó có thể khác nhau giữa development, integration test, staging và production. Một endpoint tồn tại ở môi trường test chưa chắc được expose qua mạng production; một issuer có thể hỗ trợ JWT ở staging nhưng production còn bật opaque token; một JWKS endpoint có thể trả khóa mới nhưng Resource Server vẫn giữ cache cũ; một introspection endpoint có thể trả `active=true` nhưng chưa giới hạn token cho đúng API.

> **Nguyên tắc:** kiểm tra từng capability bằng endpoint, response, credential, token và hành vi thực tế trong đúng môi trường. Không suy ra rằng AS hỗ trợ JWKS, introspection, revocation, audience hay key rotation chỉ từ tên sản phẩm hoặc từ một môi trường khác.

Bài này tập trung vào ba nhóm thành phần:

- **Metadata/discovery:** Resource Server tìm issuer, endpoint và khả năng của AS như thế nào.
- **JWKS:** Resource Server lấy public keys và xác minh JWT access token ra sao.
- **Introspection:** Resource Server hỏi AS về trạng thái hiện tại của token như thế nào.

Các ví dụ chính dùng **Spring Security Servlet Resource Server** với Spring Boot và Spring Authorization Server. API WebFlux có các lớp Reactive tương ứng; không sao chép `JwtDecoder`, `OpaqueTokenIntrospector`, `RestClient` hay `SecurityFilterChain` của Servlet sang Reactive stack mà không đối chiếu version.

## 1. Ba khái niệm cần tách biệt

| Thành phần | Câu hỏi nó trả lời | Dữ liệu thường gặp |
|---|---|---|
| Issuer metadata / OIDC discovery | AS là ai, công bố những endpoint nào và hỗ trợ capability nào? | `issuer`, `jwks_uri`, `introspection_endpoint`, token endpoint |
| JWKS | Public keys nào được dùng để xác minh chữ ký token do issuer này phát hành? | `keys[]`, `kid`, `kty`, `use`, `alg`, `n`, `e`, `x`, `y` |
| Token introspection | Token được gửi hiện còn active và có context nào theo quyết định của AS? | `active`, `sub`, `client_id`, `scope`, `aud`, `exp` |

Ba thành phần liên quan nhưng không thay thế nhau:

- Metadata có thể công bố `jwks_uri`; nó không phải bản thân JWK Set.
- JWKS cung cấp public key; nó không cho biết một token opaque có bị revoke hay không.
- Introspection cho biết trạng thái token theo quyết định của AS; nó không tự động cung cấp endpoint discovery hoặc public keys.
- `issuer` xác định nguồn phát hành token; `aud` xác định tài nguyên token được gửi tới.
- OIDC Provider Configuration và OAuth Authorization Server Metadata có phần giao nhau nhưng không phải hai tên gọi luôn thay thế được cho mọi deployment.

Một tích hợp có thể dùng **JWT + JWKS**, **opaque token + introspection**, hoặc **JWT nhưng vẫn introspect mỗi request** nếu AS hỗ trợ và hệ thống cần trạng thái thu hồi cập nhật hơn.

## 2. Metadata discovery: xác định đúng nhà phát hành trước khi gọi endpoint

### 2.1. Issuer là định danh, không chỉ là hostname

Ví dụ issuer:

~~~text
https://login.example.com/realms/shop
~~~

JWT access token được phát hành cho API phải có claim:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Resource Server cần so sánh giá trị `iss` với issuer đã cấu hình theo đúng contract. Không tự bỏ path, chuyển HTTPS thành HTTP, thêm/bỏ trailing slash hoặc lowercase toàn bộ chuỗi để làm cho hai issuer khác nhau trở nên giống nhau.

RFC 8414 yêu cầu metadata `issuer` trả về phải giống chính xác issuer identifier được dùng để tạo metadata URL. Nếu không khớp, metadata response không được sử dụng. Điều này giúp ngăn nhầm lẫn giữa các Authorization Servers.

### 2.2. OIDC Discovery và OAuth Authorization Server Metadata

Hai loại metadata thường gặp:

- **OpenID Connect Provider Configuration:** thường được công bố tại một endpoint có tên `/.well-known/openid-configuration`, theo quy tắc discovery của OIDC.
- **OAuth 2.0 Authorization Server Metadata:** được chuẩn hóa trong RFC 8414, dùng well-known URI `/.well-known/oauth-authorization-server` theo quy tắc tạo URL của RFC.

Với issuer có path, vị trí well-known có thể khác cách nối chuỗi đơn giản `issuer + "/.well-known/..."`. Spring Security hỗ trợ một số discovery patterns, nhưng mỗi AS có thể công bố URL theo profile/version riêng. Hãy lấy **discovery URL chính thức** từ tài liệu hoặc cấu hình của nhà phát hành.

Metadata response minh họa:

~~~json
{
  "issuer": "https://login.example.com/realms/shop",
  "authorization_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.com/realms/shop/protocol/openid-connect/certs",
  "introspection_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/token/introspect",
  "revocation_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/revoke",
  "scopes_supported": ["openid", "profile", "orders.read", "orders.write"],
  "grant_types_supported": ["authorization_code", "client_credentials"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic", "private_key_jwt"],
  "introspection_endpoint_auth_methods_supported": ["client_secret_basic"]
}
~~~

Đây là response **minh họa**, không phải metadata mặc định của mọi nhà phát hành. Một số trường là optional; trường vắng mặt không tự chứng minh tính năng tương ứng có hoặc không có theo một cách thống nhất. Cần đối chiếu tài liệu AS và kiểm tra endpoint thực tế.

### 2.3. Các metadata fields cần ghi nhận

| Field | Ý nghĩa | Cần kiểm tra |
|---|---|---|
| `issuer` | Issuer identifier canonical | Có khớp claim `iss` của token không? |
| `jwks_uri` | URL JWK Set | Có HTTPS, có truy cập được từ Resource Server không? |
| `introspection_endpoint` | URL introspection | Có được công bố không, hoặc lấy từ cấu hình chính thức nào? |
| `introspection_endpoint_auth_methods_supported` | Cách Resource Server xác thực tại introspection endpoint | Có hỗ trợ method ứng dụng định dùng không? |
| `token_endpoint_auth_methods_supported` | Cách OAuth client xác thực ở token endpoint | Không nhầm với credentials của Resource Server tại introspection |
| `grant_types_supported` | Grant types AS công bố hỗ trợ | Client registration có được phép dùng grant đó không? |
| `scopes_supported` | Scopes được AS công bố | API có được cấp scope cần thiết không? |
| `revocation_endpoint` | Endpoint revoke token | Có hỗ trợ và có tác dụng với loại token đang dùng không? |
| `code_challenge_methods_supported` | PKCE methods | Public client có dùng được `S256` không? |
| `authorization_endpoint` / `token_endpoint` | Các endpoint của OAuth flow | Host, path và TLS certificate có đúng môi trường không? |

Metadata là **hợp đồng capability được công bố**, không thay thế kiểm thử end-to-end. Ví dụ, metadata có `introspection_endpoint` chưa chứng minh Resource Server client đã được cấp quyền gọi endpoint đó.

### 2.4. Metadata có thể không công bố đủ thông tin

Một AS có thể:

- Không hỗ trợ discovery và yêu cầu cấu hình endpoint thủ công.
- Công bố JWKS nhưng không công bố introspection endpoint.
- Công bố introspection endpoint nhưng yêu cầu client authentication method không có trong metadata.
- Hỗ trợ OIDC Provider Configuration nhưng không expose một số OAuth extensions.
- Chỉ cho phép gọi metadata/JWKS từ mạng nội bộ.
- Có endpoint công khai khác nhau giữa public issuer và internal network.

Nếu thiếu metadata field, hãy ghi nhận đó là **capability chưa được xác nhận**. Không tự đoán URL bằng cách thêm `/jwks`, `/certs`, `/introspect` hoặc `/oauth2/introspect` vào issuer.

## 3. JWKS: nguồn public keys để xác minh JWT

### 3.1. JWK và JWK Set là gì?

**JWK (JSON Web Key)** mô tả một khóa mật mã. **JWK Set (JWKS)** là JSON object chứa một mảng các keys.

Ví dụ JWKS RSA public key:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "orders-signing-2026-a",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

Các thành phần:

| Field | Ý nghĩa |
|---|---|
| `kty` | Loại khóa, ví dụ `RSA`, `EC` |
| `kid` | Key ID, dùng chọn khóa phù hợp |
| `use` | Mục đích sử dụng, ví dụ `sig` |
| `alg` | Thuật toán liên quan khóa, nếu được công bố |
| `n`, `e` | Public modulus/exponent của RSA |
| `crv`, `x`, `y` | Curve và tọa độ public key của EC |
| `key_ops` | Các phép toán khóa được phép, nếu có |
| `x5c` | Certificate chain, nếu được công bố |

Các chuỗi trong dấu `<...>` là placeholder, không phải key dùng được. JWKS của Resource Server phải chứa **public key material** cần thiết để xác minh; không công bố private parameters như RSA `d`, `p`, `q` hoặc EC private scalar.

### 3.2. JWKS không phải token và không phải endpoint introspection

~~~text
JWT access token
   |
   +-- header.kid
   +-- payload.iss / aud / exp / scope
   +-- signature
          |
          v
Resource Server lấy JWKS từ issuer đã tin
          |
          v
Tìm public key phù hợp với kid/alg/key type
          |
          v
Verify chữ ký + validate claims
          |
          v
Authentication
~~~

JWKS cung cấp khóa xác minh. Nó không chứa danh sách đầy đủ các access tokens đã phát hành và không phải cơ chế kiểm tra token đã bị revoke.

### 3.3. `kid` không phải bằng chứng tin cậy

JWT header có thể chứa:

~~~json
{
  "alg": "RS256",
  "kid": "orders-signing-2026-a",
  "typ": "at+jwt"
}
~~~

`kid` chỉ là chỉ dẫn chọn khóa trong **key source đã được tin cậy**. Không được:

- Tìm khóa bằng cách gọi URL `jku` hoặc `x5u` tùy ý do token gửi.
- Chấp nhận khóa chỉ vì `kid` khớp chuỗi.
- Dùng một `kid` làm cache key global giữa các issuer.
- Tự thêm public key từ token vào trust store.
- Cho phép thuật toán bất kỳ do JWT header yêu cầu.

Hai issuers có thể dùng cùng `kid` nhưng public keys khác nhau. Namespace của key source phải gắn với issuer/JWKS URI được cấu hình.

### 3.4. JWKS endpoint cần đáp ứng những gì?

Tại từng môi trường, kiểm tra:

1. URL đúng với issuer và tài liệu AS.
2. HTTPS và certificate chain/hostname hợp lệ.
3. Resource Server có thể resolve DNS và kết nối từ đúng network segment.
4. Response thành công, đúng JSON content type và schema JWK Set.
5. Public keys có `kid` phù hợp với JWT được phát hành.
6. `kty`, `use`, `alg`, `key_ops` tương thích với thuật toán ký.
7. Không lộ private key parameters.
8. JWKS có thể được cập nhật khi key rotation.
9. Cache headers/TTL và behavior khi `kid` mới xuất hiện được hiểu rõ.
10. Rate limit, timeout và egress policy không làm gián đoạn key refresh.

RFC 8414 quy định `jwks_uri` nếu được công bố phải dùng HTTPS. JWK Set URI riêng của từng nhà phát hành có thể không theo một path cố định; không hardcode path dựa trên sản phẩm.

## 4. Spring Security xác minh JWT qua issuer và JWKS

### 4.1. Luồng xác thực mặc định

Trong Servlet Resource Server:

~~~text
HTTP Authorization: Bearer <JWT>
                 |
                 v
BearerTokenAuthenticationFilter
                 |
                 v
JwtAuthenticationProvider
                 |
                 v
JwtDecoder
                 |
                 +-- Lấy JWKS (nếu cần)
                 +-- Chọn public key
                 +-- Verify JWS signature
                 +-- Validate exp / nbf
                 +-- Validate iss
                 +-- Validate aud nếu cấu hình
                 |
                 v
JwtAuthenticationToken
                 |
                 v
HTTP authorization / method security
~~~

Spring Security dùng `JwtAuthenticationProvider`, `JwtDecoder` và `JwtAuthenticationConverter` trong đường xác thực JWT. Mặc định, scopes từ claim `scope` hoặc `scp` được ánh xạ thành authorities có prefix `SCOPE_` theo convention tương ứng.

### 4.2. Cấu hình `issuer-uri`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences: orders-api
~~~

`issuer-uri` cho Spring biết issuer cần được tin và dùng discovery để tìm public keys. `audiences` là cấu hình Spring Boot ở các version hỗ trợ, dùng kiểm tra token có được gửi tới `orders-api` hay không.

Spring Security hiện hành có thể trì hoãn discovery tới **request đầu tiên mang JWT**, nên startup của ứng dụng không nhất thiết phụ thuộc ngay vào việc AS có sẵn sàng hay không. Điều này không bảo đảm request đầu tiên sẽ thành công nếu metadata/JWKS endpoint đang lỗi.

### 4.3. Cấu hình `issuer-uri` và `jwk-set-uri` trực tiếp

Nếu AS không hỗ trợ discovery hoặc Resource Server cần khởi động độc lập với AS:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://keys.internal.example/realms/shop/jwks
          audiences: orders-api
~~~

Với cấu hình này:

- `jwk-set-uri` xác định nơi lấy public keys.
- `issuer-uri` vẫn giữ validation claim `iss`.
- Resource Server không cần discovery để tìm JWKS URI.
- Network address nội bộ của JWKS có thể khác public issuer nếu mapping đã được quản trị và bảo vệ.

Không bỏ `issuer-uri` chỉ vì JWKS endpoint nằm ở hostname nội bộ. Issuer identity và đường vận chuyển public keys là hai thông tin khác nhau.

### 4.4. Cấu hình SecurityFilterChain

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Ví dụ minh họa HTTP authorization sau khi token được xác thực. Trong ứng dụng thực tế, cần chia rule theo HTTP method và scope đọc/ghi/xóa; quyền tenant và object ownership vẫn phải kiểm tra ở service.

### 4.5. Khi nào cần custom `JwtDecoder`?

Custom decoder có ích khi cần:

- Audience validator riêng.
- JWS algorithm allowlist tường minh.
- Clock skew hoặc token profile policy riêng.
- HTTP client, proxy hoặc timeout riêng.
- Cache JWKS tùy chỉnh.
- Nhiều issuers có decoder/validator khác nhau.

Khi tự khai báo `JwtDecoder` bean, Spring Boot có thể back off khỏi decoder auto-configuration. Vì vậy hãy cấu hình lại **đầy đủ** issuer, audience, timestamps và các validators bắt buộc; không nghĩ rằng custom bean chỉ thay HTTP client nhưng mọi validation property sẽ tự được áp lại.

Ví dụ validator audience:

~~~java
package com.example.orders.security;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class AudienceValidator implements OAuth2TokenValidator<Jwt> {

    private final String requiredAudience;

    public AudienceValidator(String requiredAudience) {
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience().contains(this.requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Required audience is missing",
                null
            )
        );
    }
}
~~~

Đăng ký kết hợp với validator mặc định:

~~~java
@Bean
JwtDecoder jwtDecoder(
        @Value("${app.security.issuer}") String issuer,
        @Value("${app.security.jwk-set-uri}") String jwkSetUri,
        @Value("${app.security.audience}") String audience) {

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri(jwkSetUri)
        .build();

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            new AudienceValidator(audience)
        )
    );

    return decoder;
}
~~~

Ví dụ cần các imports `Value`, `Bean`, `NimbusJwtDecoder`, `JwtDecoder`, `JwtValidators`, `DelegatingOAuth2TokenValidator` và `OAuth2TokenValidator`. Các validators theo RFC 9068/token type hoặc business contract cần được bổ sung nếu API yêu cầu. Không thay toàn bộ validators mặc định bằng một audience check đơn lẻ.

## 5. Key rotation: khả năng phải kiểm chứng bằng token thật

AS có thể xoay signing keys theo chu kỳ hoặc khi key bị lộ. Một quy trình rotation thường có giai đoạn overlap:

~~~text
T0: JWKS công bố key-A
    Token-A ký bằng key-A

T1: JWKS công bố key-A + key-B
    Resource Server có thời gian nhận key-B

T2: AS bắt đầu ký token mới bằng key-B
    Token-B cần được xác minh bằng key-B

T3: Token-A cũ vẫn có thể còn hiệu lực
    JWKS tiếp tục giữ key-A trong overlap window

T4: Token-A hết hạn theo chính sách
    AS có thể loại key-A sau khi không còn token hợp lệ cần nó
~~~

Thời gian overlap phải tính tới:

- Maximum access-token lifetime.
- Clock skew của Resource Server.
- JWKS cache TTL.
- Thời điểm các replicas refresh keys.
- Khả năng AS rollback về key cũ.
- Quy trình xử lý key compromise khẩn cấp.

### 5.1. Spring Security tự động rotate keys không có nghĩa cập nhật tức thì

Spring Security Resource Server hỗ trợ cập nhật keys khi AS công bố key mới. Tuy nhiên, thời điểm một instance nhận key mới phụ thuộc cache, request pattern và cách key source refresh.

Đừng chỉ kiểm tra JWKS bằng browser rồi kết luận mọi Resource Server replica đã thấy key mới. Hãy phát token ký bằng key mới trong staging, gửi qua từng instance hoặc qua load balancer và kiểm tra kết quả.

### 5.2. Cache JWKS trong Spring Security Servlet

Tài liệu Servlet hiện hành mô tả:

- `NimbusJwtDecoder` mặc định cache JWK Set trong memory khoảng **5 phút**.
- Có thể truyền Spring `Cache` qua builder `.cache(...)` để điều chỉnh cache và dùng cache provider khác.
- Cache dùng JWK Set URI làm key và JSON JWK Set làm value.

Ví dụ:

~~~java
@Bean
JwtDecoder jwtDecoder(
        CacheManager cacheManager,
        @Value("${app.security.issuer}") String issuer) {

    return NimbusJwtDecoder
        .withIssuerLocation(issuer)
        .cache(cacheManager.getCache("authorization-server-jwks"))
        .build();
}
~~~

Đây là API của **Servlet `NimbusJwtDecoder`** trong các version tài liệu hóa cách cấu hình này. WebFlux sử dụng `NimbusReactiveJwtDecoder` và API/cache extension khác; không copy `.cache(Cache)` sang Reactive builder nếu Javadoc của version không cung cấp method đó.

Spring Cache không tự là cache provider. Ứng dụng phải thêm implementation phù hợp và xác định eviction, TTL, serialization, namespace và failure behavior.

### 5.3. Kiểm tra key rotation theo từng môi trường

| Test | Điều cần quan sát |
|---|---|
| Token dùng key hiện tại | Xác minh thành công |
| JWKS thêm key mới | Response có `kid` mới và public key đúng |
| Token mới dùng `kid` mới | Resource Server nhận key mới theo refresh policy |
| Token cũ trong overlap | Vẫn xác minh được nếu còn trong thời hạn và key còn được công bố |
| Key cũ bị gỡ quá sớm | Phát hiện 401 cho token chưa hết hạn |
| Một replica chưa refresh | Phát hiện hành vi không đồng nhất giữa instances |
| JWKS tạm lỗi | Token có key cache và token cần key mới có behavior đúng policy |
| Key compromise | Có quy trình thu hồi/deny và rotation khẩn cấp, không chỉ chờ TTL |

Không test bằng cách chỉ thay JSON trong một file local. Phải xác minh toàn bộ đường từ AS, proxy/cache tới decoder đang chạy.

## 6. Token introspection: hỏi AS về trạng thái token hiện tại

### 6.1. Introspection giải quyết bài toán nào?

Opaque token thường không chứa claims có thể được Resource Server tự xác minh. Resource Server gửi token tới **introspection endpoint** để hỏi AS về trạng thái và metadata của token.

RFC 7662 định nghĩa introspection response là JSON mô tả token, bao gồm trạng thái `active`. Ý nghĩa `active` do AS xác định; thông thường token đã được AS phát hành, chưa hết hạn, chưa bị revoke và được phép dùng tại Resource Server đang hỏi.

Request theo RFC 7662 thường là HTTP POST:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <resource-server-client-credentials>

token=OPAQUE_ACCESS_TOKEN
~~~

Introspection endpoint phải được bảo vệ bằng TLS và cần cơ chế xác thực Resource Server theo policy của AS.

### 6.2. Response minh họa

~~~json
{
  "active": true,
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-42",
  "client_id": "storefront-web",
  "aud": ["orders-api"],
  "scope": "orders.read orders.create",
  "exp": 2000000300,
  "iat": 1999999700
}
~~~

Không phải mọi introspection response đều phải chứa tất cả claims trong ví dụ. RFC 7662 định nghĩa `active` là thành phần cốt lõi; các thông tin khác phụ thuộc AS và token context.

Resource Server phải biết rõ:

- `active` được tính dựa trên những điều kiện nào.
- AS có kiểm tra token đúng audience/resource không.
- AS có kiểm tra expiry, not-before và revocation không.
- Scope có được lọc theo Resource Server gọi introspection không.
- Client credentials của Resource Server có được phép introspect loại token đó không.
- Response có cung cấp issuer/subject/tenant cần thiết cho authorization không.

### 6.3. `active=true` không phải quyền truy cập mọi endpoint

Một token có thể active nhưng:

- Không có `orders.write`.
- Được cấp cho `billing-api`, không phải `orders-api`.
- Thuộc client không được gọi endpoint admin.
- Không có membership trong tenant được yêu cầu.
- Đã bị policy nghiệp vụ thu hồi quyền truy cập một object.

Introspection trả trạng thái token; Spring Security tiếp tục ánh xạ scopes/authorities, rồi HTTP/service authorization quyết định quyền trên tài nguyên.

### 6.4. Response `active=false`

Với token không tồn tại, hết hạn hoặc đã revoke, AS có thể trả:

~~~json
{
  "active": false
}
~~~

Theo RFC 7662, response inactive nên hạn chế thông tin bổ sung để tránh làm lộ trạng thái nội bộ của AS. Resource Server không được tự tạo principal khi `active=false`, response sai schema hoặc introspection call thất bại.

## 7. Cấu hình opaque token trong Spring Security

### 7.1. Spring Boot properties

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/realms/shop/introspect
          client-id: orders-resource-server
          client-secret: "${ORDERS_INTROSPECTION_CLIENT_SECRET}"
~~~

Ba giá trị phải đúng môi trường:

- `introspection-uri`: endpoint đã được AS công bố hoặc team tích hợp xác nhận.
- `client-id`: OAuth client dành cho **Resource Server introspection**, không nhầm với client ID của web/mobile application.
- `client-secret`: secret tương ứng, lấy từ secret manager hoặc environment được kiểm soát.

Không commit secret vào Git, YAML public, Docker image, log hay pipeline artifact.

### 7.2. SecurityFilterChain

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OpaqueApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Khi có Bearer token, Spring Security dùng `OpaqueTokenAuthenticationProvider` và `OpaqueTokenIntrospector`. Introspector gửi token cùng client credentials tới endpoint; khi response xác nhận `active=true`, scopes được ánh xạ thành authorities theo convention `SCOPE_`.

Principal mặc định thường là `OAuth2AuthenticatedPrincipal`, và `Authentication` thường là `BearerTokenAuthentication`. Điều này khác principal JWT là `Jwt` trong `JwtAuthenticationToken`.

### 7.3. Dùng `SpringOpaqueTokenIntrospector` tường minh

Nếu muốn tự tạo bean:

~~~java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${app.security.opaque.introspection-uri}") String uri,
        @Value("${app.security.opaque.client-id}") String clientId,
        @Value("${app.security.opaque.client-secret}") String clientSecret) {

    return SpringOpaqueTokenIntrospector
        .withIntrospectionUri(uri)
        .clientId(clientId)
        .clientSecret(clientSecret)
        .build();
}
~~~

Bean custom sẽ thay thế auto-configured introspector tương ứng. Khi tự cấu hình, cần bảo đảm credentials và endpoint đúng môi trường, TLS được kiểm tra, timeout phù hợp và authority mapping không cấp quyền ngoài contract.

## 8. Introspection với JWT: định dạng token không quyết định endpoint

Một điểm quan trọng: **introspection không chỉ dành cho opaque token**.

Spring Security Opaque Token support không phụ thuộc token có phải JWT hay không; nó gửi token tới introspection endpoint đã cấu hình. Nếu AS hỗ trợ introspect JWT access token và trả trạng thái phù hợp, Resource Server có thể dùng introspection để xác minh JWT.

Ví dụ:

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

Dù token là JWT, `Authentication` được tạo qua opaque-token authentication flow và principal attributes phụ thuộc response introspection.

Lựa chọn này có ích khi cần hỏi AS về trạng thái token ở mỗi request, ví dụ revocation phải có hiệu lực sớm hơn thời hạn JWT. Đổi lại, mỗi request có thể phụ thuộc network, latency và availability của introspection service.

**Không nhầm hai cách:**

| Cách xác minh | JWT + JWKS | JWT + introspection |
|---|---|---|
| Chữ ký được xác minh ở đâu? | Resource Server | AS theo introspection contract, nếu AS thực hiện đầy đủ |
| Network request mỗi API request? | Thường không khi key đã có trong cache | Thường có, trừ cache introspection |
| Revocation trước `exp` | Cần cơ chế bổ sung hoặc policy riêng | Có thể được phản ánh qua `active=false` |
| Principal mặc định Spring | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| Nguồn authority | Claims JWT đã verify | Attributes từ introspection response |
| Phụ thuộc AS lúc runtime | Khi discovery/key refresh cần mạng | Khi introspection được gọi |
| Điều phải kiểm chứng | Issuer/JWKS/signature/claims | Endpoint/client auth/active/resource context |

## 9. Caching: JWKS cache và introspection cache có rủi ro khác nhau

### 9.1. Cache JWKS

JWKS cache giữ public keys hoặc JWK Set JSON. Nó giúp Resource Server không phải tải public keys mỗi lần xử lý JWT.

Các yếu tố cần thống nhất:

- TTL mặc định và TTL mong muốn.
- Cache per-instance hay shared cache.
- Namespace theo issuer/JWK Set URI.
- Refresh khi AS công bố key mới.
- Hành vi khi key cũ bị gỡ.
- Eviction khi issuer/JWKS URL thay đổi.
- Serialization và quyền truy cập cache.
- Behavior khi cache backend không sẵn sàng.

**Cache JWKS không phải cache kết quả xác thực token.** Resource Server vẫn phải xác minh chữ ký và claims của từng JWT.

### 9.2. Cache introspection

Introspection response chứa trạng thái token và có thể có scopes/roles/tenant attributes. Cache response giúp giảm số lần gọi AS nhưng có thể làm trạng thái cũ được sử dụng sau khi token bị revoke hoặc quyền thay đổi.

RFC 7662 nhấn mạnh trade-off:

- TTL ngắn: trạng thái mới hơn, nhưng tăng traffic và tải AS.
- TTL dài: giảm tải, nhưng tăng cửa sổ sử dụng token đã bị revoke.
- Không cache: freshness cao hơn, nhưng mỗi request phụ thuộc introspection endpoint.

Một chính sách cache nên đặt TTL không vượt quá thời gian còn lại tới `exp` nếu response có expiry, và phải nằm trong revocation SLA mà tổ chức chấp nhận.

Ví dụ nguyên tắc:

~~~text
effectiveCacheTTL =
    min(configuredTTL, remainingTokenLifetime, revocationSLA)
~~~

Đây là công thức thiết kế, không phải hàm có sẵn trong Spring Security.

### 9.3. Cache key phải bảo vệ token

Nếu tự cache introspection, tránh đưa raw access token vào:

- Cache metrics label.
- Log.
- Distributed tracing.
- Key dễ quan sát trong admin UI.

Có thể dùng digest có khóa hoặc cơ chế cache key an toàn, đồng thời namespace theo introspection endpoint/resource server. Cần đảm bảo hai token khác nhau không va chạm theo cách có thể khiến một token dùng nhầm kết quả active/authority của token khác.

### 9.4. Không cache quá hạn hoặc sai audience

Một introspection response active ở Resource Server A không nhất thiết có thể dùng làm quyết định cho Resource Server B. RFC 7662 cho phép AS trả response khác nhau tùy protected resource gọi introspection.

Vì vậy, cache phải gắn với **resource server context** và client credentials, không chia sẻ bừa bãi giữa APIs có audience/permission khác nhau.

## 10. Timeout, retry và availability

### 10.1. Có hai đường mạng khác nhau

JWT + JWKS có thể cần network khi:

- Discovery metadata chưa được tải.
- JWKS cache chưa có.
- Cần refresh keys.
- Một key mới xuất hiện.

Opaque introspection thường cần network khi xử lý token, trừ khi ứng dụng có cache/decorator riêng.

Do đó, timeout của JWKS và timeout introspection nên được cấu hình/đo riêng; chúng có latency profile và tần suất gọi khác nhau.

### 10.2. Timeout introspection trong Spring Security

Tài liệu Servlet hiện hành mô tả timeout mặc định connect/socket của Resource Server khi liên lạc AS là khoảng **30 giây mỗi loại**. Giá trị này có thể quá dài với API có latency budget thấp.

Spring Security hiện hành cung cấp `RestClientOpaqueTokenIntrospector`, có thể dùng `RestClient` được cấu hình `ClientHttpRequestFactory` riêng.

Ví dụ với Spring Framework/Spring Security version có API tương ứng:

~~~java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${app.security.opaque.introspection-uri}") String uri,
        @Value("${app.security.opaque.client-id}") String clientId,
        @Value("${app.security.opaque.client-secret}") String clientSecret) {

    SimpleClientHttpRequestFactory requestFactory =
        new SimpleClientHttpRequestFactory();

    requestFactory.setConnectTimeout(Duration.ofSeconds(2));
    requestFactory.setReadTimeout(Duration.ofSeconds(3));

    RestClient restClient = RestClient.builder()
        .requestFactory(requestFactory)
        .defaultHeaders(headers ->
            headers.setBasicAuth(clientId, clientSecret))
        .build();

    return new RestClientOpaqueTokenIntrospector(uri, restClient);
}
~~~

Ví dụ này dùng các API hiện hành của `RestClientOpaqueTokenIntrospector`. Nếu project dùng Spring Security/Spring Framework version cũ hơn, hãy kiểm tra Javadoc/BOM: có thể phải dùng `SpringOpaqueTokenIntrospector` với `RestOperations` thay thế.

Các giá trị 2 và 3 giây chỉ là ví dụ. Hãy chọn theo p95/p99 latency, network topology, API SLO và timeout budget của gateway.

### 10.3. Timeout JWKS cho Servlet decoder

Trong Servlet Resource Server, có thể tùy chỉnh HTTP client dùng bởi `NimbusJwtDecoder` qua `RestOperations`:

~~~java
@Bean
JwtDecoder jwtDecoder(
        RestTemplateBuilder builder,
        @Value("${app.security.issuer}") String issuer) {

    RestOperations rest = builder
        .setConnectTimeout(Duration.ofSeconds(2))
        .setReadTimeout(Duration.ofSeconds(3))
        .build();

    return NimbusJwtDecoder
        .withIssuerLocation(issuer)
        .restOperations(rest)
        .build();
}
~~~

Đây là ví dụ theo Servlet builder. WebFlux dùng `WebClient`/Reactive decoder APIs riêng. Timeout connect/read không nhất thiết là tổng deadline end-to-end; discovery, DNS, TLS, retries, body parsing và connection pool có thể cộng thêm latency.

### 10.4. Retry phải có giới hạn

Không retry vô hạn mọi lỗi:

- HTTP 401/403 do client credentials sai không tự hết khi retry.
- JWT signature sai không cần gọi JWKS lặp lại vô hạn.
- DNS/TLS misconfiguration không được chữa bằng retry liên tục.
- Một outage có thể tạo retry storm nếu mọi API request cùng thử lại.
- Timeout cần có tổng retry budget và backoff/jitter nếu policy cho phép.

Khi không lấy được key đáng tin hoặc không thể xác nhận token active, **không xác thực thành công**. Không biến lỗi network thành grant.

## 11. Khả năng ở phía Authorization Server

### 11.1. Các endpoint có thể cần

Một AS thường có các endpoint OAuth/OIDC:

| Endpoint | Dùng để làm gì? | Cần cho Resource Server? |
|---|---|---|
| Authorization endpoint | Browser/user authorization flow | Không trực tiếp cho JWT verification |
| Token endpoint | Phát access token | Dùng bởi OAuth clients |
| Provider Configuration / AS Metadata | Công bố issuer và endpoint/capability | Cần nếu dùng discovery |
| JWK Set endpoint | Công bố public keys | Cần nếu xác minh JWT qua JWKS |
| Introspection endpoint | Kiểm tra trạng thái token | Cần nếu dùng introspection |
| Revocation endpoint | Thu hồi token | Có ích khi policy cần revoke |
| UserInfo endpoint | Trả user claims theo OIDC | Thường dành cho OIDC client, không phải JWT key verification |
| End-session/logout endpoint | OIDC logout | Không thay API token validation |

Không phải mọi AS đều expose mọi endpoint hoặc bật cùng một profile.

### 11.2. Spring Authorization Server

Spring Authorization Server có cấu hình mặc định hỗ trợ các protocol endpoints như token, introspection, revocation, AS metadata và JWK Set. Tuy nhiên:

- **JWK Set endpoint chỉ được cấu hình khi có bean `JWKSource<SecurityContext>`.**
- **OIDC 1.0 endpoints bị tắt mặc định** trong cấu hình tối thiểu; cần bật OIDC configurer nếu ứng dụng cần Provider Configuration/UserInfo/Logout.
- Endpoint paths có thể được tùy chỉnh qua `AuthorizationServerSettings`.
- Việc endpoint có tồn tại không chứng minh client/resource server đã được cấu hình đúng.

Ví dụ JWK source trong AS:

~~~java
@Bean
JWKSource<SecurityContext> jwkSource() {
    RSAKey rsaKey = loadOrCreateSigningKeyFromSecureKeyManagement();

    JWKSet jwkSet = new JWKSet(rsaKey);

    return (jwkSelector, securityContext) ->
        jwkSelector.select(jwkSet);
}
~~~

`loadOrCreateSigningKeyFromSecureKeyManagement()` là placeholder cho key management do ứng dụng triển khai; không tự tạo một signing key mới mỗi lần ứng dụng khởi động. Production cần quản lý key persistence, HSM/KMS hoặc secret storage, rotation và access control.

### 11.3. JWK Set endpoint không được lộ private key

AS có thể giữ private signing key và công bố public key trong JWKS. Cần kiểm tra:

- Public key có đúng key ký token không?
- `kid` trong JWT khớp key công bố không?
- JWK không chứa private parameters.
- Key rotation không ghi đè mất key cũ quá sớm.
- Private signing keys không được lưu chung nơi công khai với JWKS JSON.

### 11.4. Introspection endpoint cần bảo vệ

Resource Server là một OAuth client khi gọi introspection endpoint. Cần kiểm tra:

- Endpoint yêu cầu client authentication method nào.
- Client ID/secret hoặc key/certificate có đúng không.
- Credentials có được giới hạn quyền introspect không.
- Endpoint có TLS và certificate validation đúng không.
- Endpoint có rate limiting và audit không.
- Response có kiểm tra trạng thái token đầy đủ không.
- Token thuộc API khác có bị đánh dấu inactive hoặc bị giới hạn scopes đúng không.

## 12. Capability matrix theo môi trường

Không dùng một kết quả test từ dev để đại diện cho production. Tạo một ma trận có owner và bằng chứng rõ ràng.

| Capability | Development | CI/Integration test | Staging | Production |
|---|---|---|---|---|
| Canonical issuer | Issuer dev riêng | Issuer stub/test | Issuer staging riêng | Issuer production chính thức |
| Discovery metadata | URL và issuer khớp | Mock response có contract | Endpoint thật, DNS/TLS thật | Endpoint thật, HA và monitoring |
| `jwks_uri` | Public key test/dev | JWKS stub hoặc test AS | Key staging | Key production |
| JWK algorithms | Khớp contract | Test cả algorithm hợp lệ/sai | Khớp production | Allowlist được duyệt |
| Key rotation | Có thể trigger nhanh | Test old/new key | Diễn tập rotation | Quy trình rotation/rollback |
| Introspection endpoint | Có thể dùng AS dev | Mock `active=true/false` | Endpoint thật | HA, rate limit, auth |
| Introspection auth method | Credentials dev | Test auth success/failure | Credential staging | Secret/key production |
| Audience/resource binding | API dev | Token sai audience phải fail | Giống production | Policy bắt buộc |
| Revocation | Có thể revoke test token | Test active → inactive | Kiểm tra propagation | SLA và quy trình khẩn cấp |
| Cache/TTL | Có thể ngắn để test | Deterministic | Gần production | Theo revocation/SLO |
| Timeout/retry | Ngắn để phát hiện lỗi | Inject timeout/5xx | Theo network thực | Theo SLO và budget |
| TLS/trust chain | CA dev | Test CA riêng | Certificate tương tự prod | CA chính thức, rotation |
| Network/egress | Developer network | CI allowlist | Firewall/service mesh | Egress policy được duyệt |
| Monitoring | Log local | Assertions | Dashboard test | Alert/on-call/runbook |

Mỗi ô nên có ít nhất một trong các bằng chứng:

- URL/issuer được xác nhận.
- HTTP response mẫu đã được lưu an toàn.
- Test report với request/response đã redact.
- Owner phía AS xác nhận capability.
- Runbook key rotation/revocation.
- Metrics/dashboards từ môi trường đó.

### 12.1. Những khác biệt môi trường thường gây lỗi

**Issuer khác nhau:** staging token không thể xác minh ở production nếu `iss` và signing keys khác nhau. Đây thường là thiết kế đúng.

**Audience khác nhau:** token `aud=orders-api-staging` không nên được chấp nhận bởi `orders-api`.

**JWK Set khác nhau:** dev public key không được đưa vào production trust store.

**Client credentials khác nhau:** introspection client của staging không được dùng ở production.

**Endpoint path khác nhau:** một nhà phát hành có thể expose `/oauth2/introspect` ở staging và path khác ở production; cấu hình phải lấy từ nguồn được quản lý, không tự suy đoán.

**TLS khác nhau:** certificate nội bộ, CA chain hoặc mTLS có thể khiến một môi trường kết nối được còn môi trường khác thất bại.

**Capability flags khác nhau:** một số AS bật introspection hoặc revocation ở production nhưng không bật ở dev, hoặc ngược lại.

## 13. Quy trình kiểm tra discovery metadata

Trước khi cấu hình Resource Server, kiểm tra metadata của từng môi trường.

### 13.1. Kiểm tra HTTP response

~~~bash
curl --fail --show-error --silent \
  "$AUTH_SERVER_METADATA_URL"
~~~

`AUTH_SERVER_METADATA_URL` phải là URL discovery chính thức của môi trường. Không mặc định rằng nối chuỗi `issuer + "/.well-known/..."` luôn tạo đúng URL.

Kiểm tra:

- HTTP status 200.
- `Content-Type: application/json`.
- Field `issuer` đúng canonical issuer.
- `jwks_uri` có mặt nếu dùng JWT/JWKS.
- `introspection_endpoint` có mặt hoặc được cấu hình theo tài liệu chính thức nếu dùng introspection.
- Auth methods được công bố phù hợp client credentials.
- Không có endpoint trỏ sang host môi trường khác.
- URL dùng HTTPS theo yêu cầu của profile.

### 13.2. Kiểm tra metadata issuer equality

Nếu metadata trả:

~~~json
{
  "issuer": "https://login.example.com/realms/shop"
}
~~~

thì đây phải là issuer canonical mà JWT sử dụng. Nếu token trả:

~~~json
{
  "iss": "https://login.example.com/realms/other"
}
~~~

Resource Server phải từ chối nếu issuer đó không được cấu hình tin.

Không khắc phục issuer mismatch bằng cách tắt issuer validator hoặc tự rewrite claim.

### 13.3. Metadata không phải danh sách endpoint được tin vô điều kiện

Discovery document là một phần của trust bootstrap. Chỉ lấy metadata từ issuer đã được phê duyệt và kết nối qua TLS đúng. Không cho request bearer token điều khiển issuer URL để server đi fetch metadata tùy ý; việc đó có thể tạo SSRF và trust injection.

## 14. Quy trình kiểm tra JWKS

### 14.1. Lấy JWKS URL từ metadata

Không hardcode URL dựa trên tên vendor. Dùng `jwks_uri` của issuer đã được xác nhận hoặc URL chính thức do AS cung cấp.

### 14.2. Kiểm tra response

~~~bash
curl --fail --show-error --silent \
  "$JWKS_URI"
~~~

Kiểm tra:

- HTTP 200.
- JSON có `keys` là array.
- Mỗi key có `kty` và public material cần thiết.
- `kid` trùng với key ID trong token test.
- Algorithm phù hợp với signing policy.
- Không có private key material.
- Response không bị redirect tới host lạ.
- Resource Server có thể truy cập từ network runtime, không chỉ laptop developer.

### 14.3. Kiểm tra token thực

Một JWT access token test phải được ký bởi private key tương ứng với public key có trong JWKS.

Kiểm tra token:

- `iss` đúng issuer.
- `aud` chứa API hiện tại.
- `exp` và `nbf` hợp lệ.
- `alg` thuộc allowlist.
- `kid` có trong JWKS.
- Token type/profile phù hợp access token, không phải ID token.
- Scope được cấp đúng.

Không dùng `jwt.io` hoặc Base64 decode làm bằng chứng xác minh chữ ký. Có thể đọc claims để debug, nhưng quyết định trust phải đến từ decoder và validator thật.

## 15. Quy trình kiểm tra introspection

### 15.1. Xác minh endpoint và client authentication

Dùng một test token được cấp trong đúng môi trường và client credentials của Resource Server. Ví dụ:

~~~bash
curl --fail --show-error \
  --user "$INTROSPECTION_CLIENT_ID:$INTROSPECTION_CLIENT_SECRET" \
  --request POST \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "token=$ACCESS_TOKEN" \
  "$INTROSPECTION_URI"
~~~

Chỉ dùng token và credentials test được cấp riêng. Tránh bật shell tracing hoặc lưu raw command output chứa secret/token trong CI logs.

### 15.2. Các response cần kiểm tra

| Token được gửi | Response mong đợi theo contract |
|---|---|
| Access token còn hạn, đúng API | `active=true`, scope/resource phù hợp |
| Token hết hạn | `active=false` |
| Token đã revoke | `active=false` theo revocation policy |
| Token không tồn tại | `active=false` |
| Token được cấp cho API khác | `active=false` hoặc response không cấp quyền cho API hiện tại |
| Token từ issuer khác | Theo trust federation/introspection contract; không tự chấp nhận |
| Client credentials sai | Endpoint từ chối client, thường 401/403 |
| Token thiếu/format sai | Không được tạo authenticated principal |
| Introspection endpoint timeout | Authentication không được xác nhận |
| Response sai JSON/schema | Fail closed và ghi nhận dependency error |

Không phải mọi AS trả cùng status cho mọi lỗi. Cần phân biệt **client authentication failure**, **inactive token** và **upstream infrastructure failure**.

### 15.3. Kiểm tra `active` có thực sự bao gồm revocation không

Không dừng ở một token active bình thường. Hãy:

1. Cấp một token test.
2. Xác nhận introspection trả `active=true`.
3. Revoke token qua cơ chế được AS hỗ trợ.
4. Gọi introspection lại.
5. Xác định thời gian từ lúc revoke đến khi `active=false`.
6. Nếu Resource Server có cache, xác định thời gian token cũ vẫn có thể được chấp nhận.
7. So sánh với revocation SLA.

Nếu AS chỉ trả `active=true` theo thời gian expiry mà không kiểm tra trạng thái revoke theo contract, introspection không cung cấp khả năng thu hồi tức thời như mong đợi.

## 16. Kiểm thử tích hợp với Spring Security

### 16.1. `MockMvc.with(jwt())` kiểm tra authorization, không kiểm tra JWKS

Ví dụ:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
~~~

Đây là cách hữu ích để kiểm tra rule HTTP `hasAuthority`. Nhưng mock JWT có thể bỏ qua:

- Metadata discovery.
- Network request tới JWKS.
- JWS signature verification.
- Issuer/audience validators.
- Key rotation.
- TLS và timeout.

Không dùng test này để tuyên bố integration với nhà phát hành đã hoạt động.

### 16.2. Test JWT thực với key test và JWKS stub

Một integration test nên:

1. Sinh RSA/EC key pair riêng cho test.
2. Chạy JWKS stub chỉ công bố public key.
3. Tạo JWT access token ký bằng private test key.
4. Cấu hình `NimbusJwtDecoder` trỏ tới JWKS stub và issuer test.
5. Gửi request thật qua `BearerTokenAuthenticationFilter`.
6. Xác nhận token đúng signature/issuer/audience được xác thực.
7. Xác nhận signature sai bị từ chối.
8. Xác nhận issuer sai bị từ chối.
9. Xác nhận audience sai bị từ chối.
10. Xác nhận token hết hạn hoặc `nbf` ở tương lai bị từ chối.
11. Đếm JWKS HTTP calls để hiểu cache/refresh.
12. Cập nhật JWKS với key mới và kiểm tra token mới sau refresh.

Các private keys chỉ dùng trong test fixture, không dùng khóa production.

### 16.3. Test opaque introspection với stub

Dùng mock HTTP server hoặc test AS:

- Token A trả `active=true`.
- Token B trả `active=false`.
- Token C có scope đọc nhưng không có scope ghi.
- Token D trả audience khác.
- Token E khiến endpoint timeout.
- Một trường hợp trả HTTP 401 do client credentials sai.
- Một trường hợp response malformed.

Gửi các token qua đường Bearer filter thật để kiểm tra `OpaqueTokenIntrospector` và `OpaqueTokenAuthenticationProvider`.

### 16.4. Test cache và revocation

Nếu có cache introspection:

~~~text
1. Token T -> introspection active=true.
2. Resource Server cache response.
3. AS revoke T.
4. Request T trước khi cache hết hạn.
5. Request T sau khi cache hết hạn.
~~~

Ghi nhận chính xác cửa sổ mà token đã revoke còn có thể được chấp nhận. Nếu vượt SLA, giảm TTL hoặc thay đổi cache strategy.

### 16.5. Test theo environment không dùng chung credentials

CI/staging/prod cần credentials riêng. Không để test chạy vào introspection endpoint production bằng token hoặc client secret thật. Test contract của production nên dùng synthetic account/tenant được phê duyệt và một quy trình kiểm tra có kiểm soát.

## 17. Cách đọc các lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| App start được nhưng JWT đầu tiên trả 401 | Discovery/JWKS lỗi hoặc token sai | Metadata, JWKS, issuer, key ID |
| `Unable to resolve Configuration with issuer` | Discovery URL sai hoặc metadata không tương thích | Issuer canonical và well-known path |
| `Unable to resolve JWK Set` | `jwks_uri` sai, DNS/TLS/HTTP lỗi | Metadata response, egress, certificate |
| `No matching key(s) found` | `kid` không có trong JWKS/cache hoặc key rotation chưa đồng bộ | JWT header và JWKS |
| Invalid signature | Token ký bằng key khác hoặc algorithm sai | Signing key, `kid`, `alg`, key type |
| Issuer validation failed | Claim `iss` không khớp | Exact issuer equality |
| Audience validation failed | Token dành cho API khác | `aud` và AS audience mapping |
| Opaque token inactive | Token hết hạn/revoked/không hợp lệ | Introspection response và AS state |
| Introspection 401/403 | Resource Server credentials hoặc auth method sai | Client registration, credentials |
| Introspection timeout | Network hoặc AS quá tải | Connect/read timeout, DNS, proxy, SLO |
| Token revoked nhưng vẫn qua một thời gian | Cache introspection còn hiệu lực | TTL và invalidation |
| Staging chạy, production lỗi | Endpoint, key, issuer, secret hoặc egress khác nhau | Environment capability matrix |
| `SCOPE_*` không xuất hiện | AS không trả scope đúng field hoặc mapper sai | `scope`/`scp` và authority converter |
| User token qua, service token fail | Client scope/audience/token profile khác | AS client registration và token claims |
| Token đúng nhưng tenant khác bị truy cập | Business authorization thiếu | Tenant membership, owner/ACL |

**401** thường liên quan authentication thất bại; **403** thường liên quan principal hợp lệ nhưng thiếu quyền. Network outage có thể được map thành authentication error hoặc infrastructure error tùy exception handling; đừng gộp mọi sự cố thành “token invalid”.

## 18. Security và vận hành khi tích hợp nhiều môi trường

### 18.1. Trust boundary

- Chỉ tin issuer đã được phê duyệt.
- Metadata và JWKS lấy từ issuer/URL đã được quản trị.
- Không để JWT `jku`, `x5u`, `iss` chưa verify hoặc request header điều khiển arbitrary outbound URL.
- Kiểm tra TLS server certificate/hostname.
- Giới hạn egress từ Resource Server tới AS/JWKS/introspection.
- Không tắt TLS verification để xử lý lỗi certificate.
- Không dùng key hoặc client credentials từ dev trong production.

### 18.2. Secrets và token handling

- Introspection client secret nằm trong secret manager.
- Không log `Authorization` header hoặc raw token.
- Không đưa token vào query string.
- Ưu tiên POST cho introspection theo RFC 7662.
- Không ghi full introspection response nếu chứa PII.
- Không đưa private signing key vào JWKS.
- Có rotation cho introspection client credentials.
- Hạn chế quyền truy cập secret và audit lần đọc.

### 18.3. Availability và fail closed

Khi JWKS endpoint lỗi:

- Token có key phù hợp trong cache có thể tiếp tục được xác minh theo behavior decoder/cache.
- Token cần key mới mà Resource Server không lấy được key thì không thể xác minh.
- Không tự chấp nhận chữ ký chưa xác minh.

Khi introspection endpoint lỗi:

- Resource Server không thể xác nhận trạng thái token theo nguồn authoritative.
- Có thể trả lỗi authentication/dependency theo handler.
- Không tạo principal giả hoặc coi timeout như `active=true`.

### 18.4. Theo dõi metrics

Nên tách các nhóm:

| Metric/event | Mục đích |
|---|---|
| Metadata discovery success/failure | Theo dõi bootstrap và metadata |
| JWKS fetch count/duration/failure | Theo dõi network/key source |
| Unknown `kid` | Phát hiện rotation hoặc token bất thường |
| JWT signature/issuer/audience failures | Phân loại token validation |
| Introspection request count/latency | Theo dõi AS load và dependency |
| Introspection `active=false` | Theo dõi token inactive |
| Introspection 401/403 | Phát hiện client credentials/config |
| Introspection timeout/5xx | Theo dõi availability |
| Cache hit/miss/eviction | Hiểu freshness và tải mạng |
| Authentication 401 | Lỗi token/authentication |
| Authorization 403 | Thiếu scope/role/policy |

Tên metrics cụ thể phụ thuộc Micrometer, Spring Security version và instrumentation. Bảng là nhóm dữ liệu cần quan sát, không khẳng định mọi metric có sẵn tự động.

Không dùng raw token, email hoặc full claims làm metric label vì có nguy cơ lộ dữ liệu và tạo cardinality lớn.

## 19. Capability checklist trước khi tích hợp một môi trường mới

### Issuer và metadata

- [ ] Canonical issuer đã được nhà phát hành xác nhận.
- [ ] Discovery URL chính xác và trả HTTP 200.
- [ ] Metadata `issuer` khớp chính xác issuer cấu hình.
- [ ] Metadata không trỏ sang host/môi trường ngoài dự kiến.
- [ ] Đã xác nhận `jwks_uri` nếu API dùng JWT local verification.
- [ ] Đã xác nhận `introspection_endpoint` nếu API dùng introspection.
- [ ] Đã ghi nhận client authentication methods và scopes/grants liên quan.

### JWKS/JWT

- [ ] JWKS trả JWK Set JSON hợp lệ.
- [ ] `kid` của token có public key tương ứng.
- [ ] `kty`, `use`, `alg` và key operations đúng contract.
- [ ] Không có private key material.
- [ ] Issuer validator được bật.
- [ ] Audience/resource validator được bật.
- [ ] Allowed algorithms được giới hạn.
- [ ] `exp`, `nbf`, clock skew và token profile được kiểm tra.
- [ ] Đã test key rotation với old/new keys và overlap window.
- [ ] Đã xác định cache TTL, timeout và behavior khi AS outage.

### Introspection

- [ ] Endpoint đúng môi trường và có TLS.
- [ ] Resource Server client authentication thành công.
- [ ] Credentials được lấy từ secret manager.
- [ ] `active=true` và `active=false` được test.
- [ ] AS kiểm tra expiry, revocation, signature nếu áp dụng và resource binding.
- [ ] Scope/audience/issuer attributes đáp ứng API contract.
- [ ] Đã test token revoked.
- [ ] Đã xác định timeout/retry/cache TTL.
- [ ] Introspection failure không fail open.
- [ ] Raw token không xuất hiện trong logs/traces.

### Environment và vận hành

- [ ] Dev/staging/prod dùng issuer, key, audience và credentials đúng môi trường.
- [ ] CI dùng test keys hoặc stub, không gọi production bằng secret thật.
- [ ] Network egress, DNS, proxy và CA chain được kiểm tra từ runtime.
- [ ] Dashboard/alert cho discovery, JWKS và introspection đã có.
- [ ] Owner AS và Resource Server có runbook key rotation/revocation.
- [ ] Có quy trình disable issuer/client khi credential bị compromise.
- [ ] Có integration tests cho từng môi trường hoặc contract test phù hợp.
- [ ] Những capability chưa xác nhận có owner và thời hạn xử lý.

## 20. Câu hỏi tự kiểm tra

**1.** Metadata discovery, JWKS và introspection khác nhau thế nào?

> Metadata công bố issuer/endpoints/capabilities; JWKS cung cấp public keys để verify JWT; introspection trả trạng thái và metadata token theo quyết định của AS.

**2.** `issuer` và `jwks_uri` có phải cùng một URL không?

> Không. `issuer` là danh tính AS; `jwks_uri` là endpoint public keys. Có thể khác host/path nhưng mapping phải được quản trị và issuer vẫn phải validate.

**3.** `jwks_uri` có bắt buộc trong mọi metadata response không?

> Không. Trong RFC 8414, `jwks_uri` là optional; nếu AS dùng JWT/JWKS thì Resource Server cần nguồn khóa được xác nhận.

**4.** `introspection_endpoint` có bắt buộc được công bố trong metadata không?

> Không. RFC 8414 định nghĩa nó là optional; nếu dùng introspection mà metadata không có field, phải lấy endpoint từ cấu hình/tài liệu chính thức khác.

**5.** JWKS chứa private signing key không?

> Không. Resource Server chỉ cần public key material để xác minh chữ ký.

**6.** `kid` có phải bằng chứng token hợp lệ?

> Không. Nó chỉ giúp chọn khóa trong JWK source đã được tin cậy.

**7.** JWT có cần gọi JWKS endpoint ở mỗi request không?

> Không. Public keys có thể được cache; mỗi token vẫn phải được verify bằng key phù hợp.

**8.** Vì sao vẫn cấu hình `issuer-uri` khi đã biết `jwk-set-uri`?

> Để giữ validation claim `iss`; JWK Set URI chỉ nói nơi lấy khóa.

**9.** Introspection `active=true` có đồng nghĩa token được phép gọi mọi endpoint?

> Không. Còn audience/resource binding, scope, role và business authorization.

**10.** Có thể introspect JWT access token không?

> Có, nếu AS hỗ trợ. Spring Security Opaque Token support có thể gửi token bất kỳ tới introspection endpoint đã cấu hình; việc xác minh khi đó dựa vào AS.

**11.** Vì sao introspection cache TTL dài có rủi ro?

> Token đã revoke hoặc quyền đã đổi có thể tiếp tục được chấp nhận trong thời gian response cũ còn cache.

**12.** Vì sao phải test `active=false`?

> Để chứng minh Resource Server từ chối token inactive, không chỉ kiểm tra đường happy path.

**13.** `issuer-uri` có thể khác giữa staging và production không?

> Có và thường nên dùng issuer riêng theo môi trường; token staging không nên tự được tin ở production.

**14.** Spring Authorization Server có luôn expose JWKS endpoint trong mọi cấu hình không?

> Không. JWK Set endpoint chỉ được cấu hình khi có `JWKSource<SecurityContext>` bean.

**15.** OIDC endpoints có bật mặc định trong Spring Authorization Server minimal config không?

> Không. Cần bật OIDC configurer nếu cần Provider Configuration/UserInfo/Logout endpoints.

**16.** Nếu JWKS hoặc introspection endpoint timeout, có nên cho request đi tiếp để tăng availability không?

> Không. Khi không chứng minh được token hợp lệ, Resource Server phải fail closed.

## 21. Tài liệu tham khảo

- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer discovery, JWKS, JWT validation, audience, key rotation, cache và timeout.
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection, `active`, `OpaqueTokenIntrospector`, timeout và introspection với JWT.
- [Spring Security — WebFlux Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): các API Reactive tương ứng.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): endpoint metadata, token, introspection, revocation và JWK Set.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer, `jwks_uri`, `introspection_endpoint` và metadata validation.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Provider Configuration và OIDC discovery.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK và JWK Set.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT claims như `iss`, `aud`, `exp`, `nbf`.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection request/response, `active`, client authentication và cache trade-offs.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access-token JWT profile và audience.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): issuer/audience/algorithm validation và token confusion.
- [Spring Framework — RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): cấu hình HTTP client và request factory.

**Kết luận:** Một Resource Server tích hợp thành công với AS cần chứng minh được ba việc: **metadata xác định đúng issuer và capability**, **JWKS cung cấp public keys đáng tin để xác minh JWT**, và **introspection trả trạng thái token đúng contract khi cần kiểm tra trạng thái hiện tại**. Những capability này phải được kiểm tra ở từng môi trường vì issuer, keys, credentials, endpoint paths, audience, TLS, cache và network policy có thể khác nhau. Hãy test cả token hợp lệ lẫn token sai, key rotation, revocation, timeout và outage; giữ issuer/audience validation và fail closed khi không thể xác minh token.
