# Ngăn nhầm thuật toán, nhầm loại token và dùng token cho sai tài nguyên

Một JWT có chữ ký hợp lệ vẫn có thể là credential **không được phép dùng tại API hiện tại**. Resource Server cần xác minh nhiều điều kiện độc lập:

1. **Thuật toán và khóa:** token được ký bằng thuật toán nằm trong allowlist và khóa đúng loại, đúng issuer.
2. **Loại token:** JWT đang nhận thực sự là access token theo profile mà API chấp nhận, không phải OIDC ID token, client assertion, logout token hay một JWT dùng cho mục đích khác.
3. **Issuer:** token được phát hành bởi Authorization Server đã được tin cậy.
4. **Audience/resource:** token được cấp cho đúng API hoặc resource server đang xử lý request.
5. **Thời hạn và trạng thái:** token còn hiệu lực theo `exp`, `nbf`, policy và cơ chế thu hồi được sử dụng.
6. **Quyền nghiệp vụ:** token có scope/authority cần thiết và caller được phép thao tác trên đúng tenant/object.

Ba lỗi trong đề bài tương ứng với ba dạng nhầm lẫn bảo mật thường gặp:

- **Algorithm confusion:** Resource Server chấp nhận thuật toán hoặc cách diễn giải khóa khác với policy dự kiến.
- **Token-type confusion / cross-JWT confusion:** một JWT được phát hành cho mục đích A lại được chấp nhận trong ngữ cảnh B.
- **Audience confusion / token substitution:** access token hợp lệ cho API A bị dùng tại API B.

RFC 8725 (JWT Best Current Practices) yêu cầu kiểm tra thuật toán, dùng explicit typing khi cần và thiết kế validation rules loại trừ lẫn nhau giữa các loại JWT. RFC 9068 định nghĩa profile JWT access token của OAuth 2.0, trong đó `typ=at+jwt` giúp Resource Server nhận diện access token, còn `aud` xác định resource được token hướng tới.

> **Nguyên tắc:** chữ ký hợp lệ chỉ chứng minh token được ký bằng một khóa mà decoder tin cậy theo thuật toán đã cấu hình. Nó không tự chứng minh token là access token, dành cho API này hay có quyền thực hiện hành động đang yêu cầu.

Bài học thuộc phần **Triển khai an toàn**, sử dụng Spring Security Servlet Resource Server, Spring Boot và Java. WebFlux có `ReactiveJwtDecoder` và `SecurityWebFilterChain` tương ứng; các nguyên tắc thuật toán, token profile, issuer và audience vẫn giống nhau nhưng API cấu hình khác.

## 1. Bốn câu hỏi phải trả lời trước khi chấp nhận JWT

Giả sử request tới Orders API:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

Resource Server không nên dừng ở câu hỏi “JWT có parse được không?”. Nó cần trả lời:

| Câu hỏi | Ví dụ điều kiện | Nếu sai |
|---|---|---|
| Ai phát hành? | `iss=https://login.example.com/realms/shop` | Từ chối token |
| Có được ký bằng thuật toán/khóa này? | `alg=RS256`, key thuộc issuer đã cấu hình | Từ chối token |
| Token thuộc loại nào? | OAuth JWT access token `typ=at+jwt` theo RFC 9068 | Từ chối token không đúng profile |
| Token dành cho API nào? | `aud` chứa `orders-api` | Từ chối token dành cho resource khác |
| Token còn hiệu lực? | `exp`, `nbf` và các policy hợp lệ | Từ chối token |
| Caller có quyền gì? | `scope=orders.read` | Authorization quyết định 403 nếu thiếu |

Một token có thể vượt qua một số điều kiện nhưng thất bại ở điều kiện khác. Ví dụ:

- Chữ ký đúng nhưng `alg=HS256` trong khi API chỉ cho phép `RS256`.
- Chữ ký đúng và issuer đúng nhưng JWT là OIDC ID token.
- JWT là access token đúng profile nhưng `aud=billing-api`.
- Audience đúng nhưng scope chỉ có `orders.read`, trong khi endpoint cần `orders.write`.

Mỗi điều kiện có một mục đích riêng. Không dùng một claim để thay thế nhiều điều kiện khác.

## 2. Algorithm confusion: vì sao phải khóa thuật toán?

### 2.1. JWT header có trường `alg`

Một signed JWT/JWS thường có header:

~~~json
{
  "alg": "RS256",
  "kid": "orders-signing-key-1",
  "typ": "at+jwt"
}
~~~

`alg` chỉ ra thuật toán ký được dùng cho JWS. Các ví dụ:

| Thuật toán | Cơ chế | Khóa dùng để xác minh |
|---|---|---|
| `RS256` | RSA + SHA-256 | RSA public key |
| `PS256` | RSA-PSS + SHA-256 | RSA public key |
| `ES256` | ECDSA P-256 + SHA-256 | EC public key |
| `HS256` | HMAC + SHA-256 | Shared secret |
| `none` | Không có chữ ký | Không có xác minh chữ ký |

Resource Server phải có policy rõ ràng về thuật toán nào được chấp nhận. Không để JWT header của request quyết định thuật toán một cách tự do.

### 2.2. `alg` là input chưa đáng tin

Trước khi chữ ký được xác minh, toàn bộ JWT header là dữ liệu do bên gửi cung cấp:

~~~json
{
  "alg": "HS256",
  "kid": "some-key",
  "typ": "JWT"
}
~~~

Attacker có thể tạo token với `alg` tùy ý. Việc parser đọc được `alg=HS256` không có nghĩa ứng dụng được phép dùng HS256.

RFC 8725 yêu cầu ứng dụng chỉ cho phép tập thuật toán đã xác định, kiểm tra thuật toán trong header với thuật toán thực sự dùng cho phép xác minh, và ràng buộc mỗi khóa với đúng một thuật toán.

### 2.3. Ví dụ RSA/HMAC confusion

Giả sử Authorization Server ký access token bằng `RS256`:

- AS giữ RSA private key.
- Resource Server dùng RSA public key lấy từ JWKS.
- Public key không phải shared secret.

Một implementation sai có thể lấy bytes của RSA public key rồi dùng chúng làm HMAC secret khi token header khai báo `HS256`. Nếu Resource Server chấp nhận cả hai cách diễn giải mà không ràng buộc thuật toán với key type, attacker có thể tạo HMAC bằng dữ liệu public và giả mạo chữ ký theo cách implementation yếu đó.

Mô hình đúng:

~~~text
Issuer đã được tin cậy
       |
       v
RS256 + RSA signing key
       |
       v
JWKS công bố RSA public key
       |
       v
Resource Server chỉ cho phép RS256
       |
       v
Public key chỉ dùng để verify chữ ký RS256
~~~

Không dùng RSA public key bytes làm HMAC secret. Nếu hệ thống thực sự cần HMAC, phải quản lý shared secret riêng, không tái sử dụng public key material và không chia sẻ key giữa các algorithm families.

### 2.4. Từ chối `alg=none`

Một unsecured JWT có thể có header:

~~~json
{
  "alg": "none",
  "typ": "JWT"
}
~~~

Token không có chữ ký mật mã. OAuth JWT access token theo RFC 9068 **MUST NOT** sử dụng `none`. Resource Server cho access token cần reject token này.

Không cấu hình decoder theo kiểu “nếu có chữ ký thì verify, nếu không thì vẫn đọc claims”. Không lấy `sub`, `scope` hoặc `role` từ token không được xác minh.

### 2.5. Key type và algorithm phải tương thích

Ví dụ mapping mong muốn:

| JWK key type | Thuật toán dự kiến | Điều cần kiểm tra |
|---|---|---|
| RSA | `RS256`, nếu được policy cho phép | RSA key và signature algorithm tương thích |
| EC P-256 | `ES256`, nếu được policy cho phép | Curve và thuật toán phù hợp |
| Octet/shared secret | `HS256`, nếu thật sự được thiết kế | Secret riêng, bảo vệ và phân phối an toàn |
| Bất kỳ key | `none` | Không chấp nhận |

JWK có thể chứa `alg`, `use` hoặc `key_ops`; nếu các trường đó được công bố, chúng phải phù hợp với cách sử dụng khóa. Không suy luận rằng mọi key trong JWKS đều được phép dùng cho mọi algorithm.

### 2.6. `kid` không quyết định thuật toán

`kid` chỉ giúp chọn key trong nguồn khóa đã tin cậy. Nó không phải bằng chứng rằng:

- Key được phép dùng với `alg` mà JWT khai báo.
- Token thuộc issuer mong đợi.
- Token là access token.
- Token dành cho API hiện tại.

Không tải key từ `jku` hoặc `x5u` tùy ý trong JWT header. Chỉ lấy public keys từ JWKS URI được cấu hình hoặc discovery từ issuer đã được phê duyệt. Nếu key ID được dùng trong truy vấn database/cache, phải tránh injection và giới hạn kích thước/format.

## 3. Cấu hình allowlist thuật toán trong Spring Security

### 3.1. Mặc định của NimbusJwtDecoder

Spring Security Resource Server sử dụng `NimbusJwtDecoder` cho JWT trong Servlet stack. Theo tài liệu Spring Security hiện hành, decoder mặc định chỉ tin cậy thuật toán `RS256`.

Điều này có nghĩa token `HS256`, `none` hoặc thuật toán khác không tự động được chấp nhận chỉ vì JWT parser có thể đọc chúng.

Tuy nhiên, khi ứng dụng tự tạo decoder, cần cấu hình allowlist tường minh theo hợp đồng của issuer. Không mở rộng thuật toán theo header token hoặc theo dữ liệu do caller gửi.

### 3.2. Spring Boot property

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
          audiences:
            - orders-api
~~~

Đây là cấu hình minh họa cho Spring Boot version hỗ trợ các properties tương ứng. Cần xác nhận property names với BOM/phiên bản Spring Boot của ứng dụng.

Ý nghĩa:

- `issuer-uri`: issuer canonical mà Resource Server tin.
- `jwk-set-uri`: nguồn public keys đã được quản trị.
- `jws-algorithms`: allowlist thuật toán ký.
- `audiences`: resource identifier mà token phải chứa.

Nếu AS chỉ ký bằng RS256, không cần thêm HS256/ES256 “để phòng trường hợp sau này”. Khi thay thuật toán, phải có thay đổi policy và rollout có kiểm soát.

### 3.3. Cấu hình `NimbusJwtDecoder` bằng Java

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtDecoderConfiguration {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer =
            "https://login.example.com/realms/shop";

        String jwkSetUri =
            "https://login.example.com/realms/shop/protocol/openid-connect/certs";

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(issuer)
        );

        return decoder;
    }
}
~~~

Đoạn code này:

1. Lấy keys từ JWKS URI cố định.
2. Chỉ chấp nhận RS256.
3. Giữ validation mặc định về issuer và thời gian.
4. Trả `JwtDecoder` cho Resource Server.

Nó chưa thêm audience hoặc token-type validation. Những điều kiện đó sẽ được bổ sung trong phần tiếp theo.

Nếu issuer thực sự phát hành nhiều thuật toán đã được phê duyệt, có thể gọi `.jwsAlgorithm(...)` nhiều lần hoặc `.jwsAlgorithms(...)` để khai báo tập cho phép. Mỗi thuật toán phải có lý do, key type tương thích và test âm tính. Không cho phép toàn bộ thuật toán chỉ vì JWKS có nhiều loại keys.

### 3.4. Không tự viết verifier dựa trên header

Tránh code kiểu:

~~~java
// Không an toàn: attacker điều khiển alg trong JWT header.
String algorithm = unverifiedJwt.getHeaders().get("alg").toString();

if ("HS256".equals(algorithm)) {
    verifyWithHmac(jwt);
} else if ("RS256".equals(algorithm)) {
    verifyWithRsa(jwt);
}
~~~

Nếu cần hỗ trợ nhiều thuật toán, hãy cấu hình decoder/key selector bằng allowlist cố định. Thư viện JOSE phải kiểm tra thuật toán và key tương ứng trong cùng một quy trình xác minh.

## 4. Token-type confusion: một JWT có thể được phát hành cho nhiều mục đích

### 4.1. JWT chỉ là định dạng, không phải một loại credential duy nhất

Một hệ thống có thể sử dụng JWT cho nhiều mục đích:

| Loại JWT/credential | Người tiêu thụ dự kiến | Mục đích |
|---|---|---|
| OAuth access token | Resource Server/API | Truy cập protected resource |
| OIDC ID token | OIDC client/Relying Party | Thông tin xác thực người dùng |
| Client assertion | Authorization Server token endpoint | Xác thực OAuth client |
| Logout token | OIDC relying party | Thông báo logout/back-channel logout |
| Security Event Token | Event receiver | Truyền security event |
| Internal service JWT | Một service cụ thể | Identity/delegation nội bộ theo contract |

Các loại này có thể cùng dùng JWT, cùng được ký bởi một issuer và thậm chí cùng được ký bằng một key. Nếu API chỉ kiểm tra “chữ ký hợp lệ” và “có `sub`”, một JWT được phát hành cho mục đích khác có thể bị sử dụng nhầm.

Đây là **cross-JWT confusion** theo RFC 8725.

### 4.2. OIDC ID token không phải access token

OIDC ID token được phát cho OIDC client để client biết kết quả authentication của end-user.

Ví dụ ID token:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-42",
  "aud": "storefront-web",
  "azp": "storefront-web",
  "nonce": "client-generated-nonce",
  "auth_time": 2000000000,
  "exp": 2000000300,
  "iat": 2000000000
}
~~~

Ở đây `aud` là OIDC client ID (`storefront-web`) theo OIDC Core. Token hướng tới client đó để client kiểm tra authentication.

Ví dụ access token dành cho Orders API:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "client_id": "storefront-web",
  "scope": "orders.read",
  "exp": 2000000300,
  "iat": 2000000000
}
~~~

Access token hướng tới resource server `orders-api`. Nó thể hiện quyền truy cập API theo authorization policy của AS.

**Không dùng ID token làm Bearer access token cho API.** ID token có chữ ký hợp lệ và có thể chứa `sub`, `email`, `name`, `aud`; các thuộc tính đó không làm nó trở thành access token.

### 4.3. Vì sao kiểm tra `sub` không đủ?

Cả ID token và access token có thể có:

~~~text
iss = https://login.example.com/realms/shop
sub = user-42
exp = ...
```

Nếu API chỉ kiểm tra:

~~~java
if (jwt.getSubject() != null) {
    allow();
}
~~~

thì token được cấp cho một client khác có thể lọt qua. `sub` chỉ xác định subject theo issuer; nó không nói token được phát hành cho API nào hoặc mục đích gì.

### 4.4. OIDC ID token audience và access token audience khác nhau

| Token | `aud` biểu diễn | Bên cần validate |
|---|---|---|
| OIDC ID token | OIDC client/Relying Party `client_id` | OIDC client |
| OAuth JWT access token | Resource Server/resource indicator | API/Resource Server |

Một API có `aud=orders-api` không nên chấp nhận ID token có `aud=storefront-web`. Tương tự, OIDC client không nên chấp nhận ID token chỉ vì `aud` chứa một API identifier.

Không dùng `azp` để thay thế audience validation. `azp` có ý nghĩa authorized party trong OIDC ID token; nó không biến client ID thành resource audience của access token.

## 5. Explicit typing và RFC 9068 access-token profile

### 5.1. JWT `typ` và OAuth `token_type` là hai khái niệm khác nhau

Có hai trường dễ bị nhầm:

**JOSE header `typ`:**

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256"
}
~~~

Nó chỉ loại JWT theo media-type/profile.

**OAuth token response `token_type`:**

~~~json
{
  "access_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 600
}
~~~

Nó cho OAuth client biết cách trình token khi gọi resource. `token_type=Bearer` không phải claim trong JWT và không thay thế việc kiểm tra JWT `typ`.

Một token có thể là JWT access token theo RFC 9068 (`typ=at+jwt`) và được trả về trong OAuth response với `token_type=Bearer`.

### 5.2. RFC 9068 yêu cầu `typ=at+jwt`

RFC 9068 định nghĩa JWT Profile for OAuth 2.0 Access Tokens. Theo profile này:

- JWT access token phải được ký.
- `alg=none` không được phép.
- `typ` phải là `at+jwt` hoặc `application/at+jwt`.
- Các claims cần thiết của access-token profile phải có mặt, bao gồm issuer, subject, audience, expiry, issued-at, JWT ID và client ID.
- Resource Server phải kiểm tra issuer chính xác.
- Resource Server phải xác nhận `aud` chứa identifier của chính resource server.
- Resource Server phải xác minh chữ ký theo thuật toán được hỗ trợ và khóa của Authorization Server.

Giá trị `at+jwt` cho biết đây là JWT access token theo profile, không phải ID token hoặc JWT tùy ý.

### 5.3. `typ=JWT` không đủ để phân biệt access token

Nhiều JWT có thể dùng:

~~~json
{
  "typ": "JWT"
}
~~~

Giá trị này chỉ nói token là JWT chung. Nó không khẳng định đây là OAuth access token.

Nếu AS không triển khai RFC 9068, token có thể dùng type riêng hoặc profile riêng. Resource Server cần định nghĩa rõ contract với issuer và validation rules loại trừ token sai mục đích. Không ép `at+jwt` nếu AS chưa phát hành profile đó; cũng không tự coi `typ=JWT` là đủ cho mọi API.

### 5.4. Validation rules phải loại trừ lẫn nhau

RFC 8725 yêu cầu nếu cùng một issuer phát hành nhiều loại JWT, validation rules cho từng loại phải loại trừ lẫn nhau và reject JWT sai loại.

Các cách có thể kết hợp:

- Explicit `typ` khác nhau cho từng profile.
- `aud` khác nhau cho từng mục đích.
- Required claims và giá trị claim khác nhau.
- Khóa ký riêng cho từng loại token.
- Issuer riêng cho từng loại token.
- Validator riêng cho từng loại token.

Không dựa vào một trường duy nhất nếu profile có thể bị nhầm. Ví dụ, nếu cả ID token và access token đều có `typ=JWT`, cần dùng audience và các required claims khác để phân biệt.

## 6. Dùng audience để ngăn token bị dùng sai resource

### 6.1. `aud` chỉ ra recipient dự kiến

JWT claim `aud` xác định recipient mà token hướng tới. Nó có thể là một string hoặc array of strings.

Ví dụ:

~~~json
{
  "aud": ["orders-api"]
}
~~~

Orders API chỉ chấp nhận nếu `orders-api` là một audience được cho phép.

Một access token có:

~~~json
{
  "aud": ["billing-api"]
}
~~~

phải bị Orders API từ chối, kể cả khi:

- Chữ ký hợp lệ.
- Issuer đúng.
- Token chưa hết hạn.
- Scope có tên `orders.read`.
- Subject là người dùng hợp lệ.

### 6.2. Scope không thay thế audience

Scope trả lời câu hỏi: **token được cấp những quyền nào?**

Audience trả lời câu hỏi: **token được cấp cho resource nào?**

Ví dụ:

~~~json
{
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

Không nên cho Orders API chấp nhận token chỉ vì scope tên `orders.read` xuất hiện. Scope có thể có ý nghĩa khác giữa APIs; resource binding phải được kiểm tra độc lập.

### 6.3. `client_id` không phải audience

Ví dụ:

~~~json
{
  "client_id": "storefront-web",
  "aud": ["orders-api"]
}
~~~

- `client_id`: OAuth client đã nhận/được cấp token theo contract.
- `aud`: resource server dự kiến tiêu thụ token.

Không viết policy:

~~~java
if ("storefront-web".equals(jwt.getClaimAsString("client_id"))) {
    allowOrdersApi();
}
~~~

nếu không kiểm tra `aud`. Một client có thể xin token cho nhiều APIs; client ID không tự ràng buộc resource.

### 6.4. Audience có thể là nhiều giá trị

JWT `aud` có thể là string hoặc array. Spring `Jwt#getAudience()` cung cấp danh sách audience đã chuẩn hóa.

Ví dụ:

~~~json
{
  "aud": ["orders-api", "inventory-api"]
}
~~~

Nếu AS phát token có nhiều audiences, mỗi API cần xác nhận policy cho phép token multi-resource đó. Không tự động chấp nhận mọi token có một audience bất kỳ chỉ vì nó có một audience “gần giống”.

Với kiến trúc cần token theo từng resource, RFC 8707 Resource Indicators cho phép client chỉ rõ tài nguyên dự kiến trong token request. AS có thể dùng thông tin đó để phát access token với audience phù hợp.

### 6.5. Sai audience phải fail authentication

Nếu token được ký hợp lệ nhưng `aud` không chứa resource identifier của API, Resource Server nên từ chối như invalid token (thường 401). Không chuyển lỗi audience mismatch thành 403 vì token vốn không được cấp cho API này.

Sau khi audience đúng và token đã authenticated, thiếu scope/role mới là authorization denial (thường 403).

## 7. Cấu hình Spring Security theo RFC 9068

Spring Security có hỗ trợ validator cho JWT access token theo RFC 9068. API `JwtValidators.createAtJwtValidator()` có từ Spring Security 6.5.

Ví dụ Servlet Resource Server:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class AccessTokenDecoderConfiguration {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer =
            "https://login.example.com/realms/shop";

        String jwkSetUri =
            "https://login.example.com/realms/shop/protocol/openid-connect/certs";

        String audience = "orders-api";

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .validateTypes(false)
            .build();

        decoder.setJwtValidator(
            JwtValidators.createAtJwtValidator()
                .issuer(issuer)
                .audience(audience)
                .build()
        );

        return decoder;
    }
}
~~~

### 7.1. Từng dòng làm nhiệm vụ gì?

- `withJwkSetUri(...)`: lấy public keys từ endpoint được quản trị.
- `jwsAlgorithm(RS256)`: chỉ cho phép RS256.
- `validateTypes(false)`: tắt type validation mặc định của Nimbus để profile validator của Spring kiểm tra type theo RFC 9068.
- `createAtJwtValidator()`: tạo validator dành cho OAuth JWT access-token profile.
- `issuer(...)`: yêu cầu issuer cụ thể.
- `audience(...)`: yêu cầu resource identifier của Orders API.

Đây là cấu hình cho issuer đã cam kết phát JWT access token theo RFC 9068. Nếu AS dùng custom token profile, phải thay type/profile validator cho đúng contract.

### 7.2. Khi nào thêm `clientId(...)`?

Builder cho phép chỉ định client ID:

~~~java
JwtValidators.createAtJwtValidator()
    .issuer(issuer)
    .audience(audience)
    .clientId("storefront-web")
    .build();
~~~

Chỉ thêm `.clientId(...)` nếu API thực sự chỉ chấp nhận token từ một OAuth client. Nếu nhiều web/mobile/service clients được phép gọi API, không khóa vào một client ID duy nhất; dùng policy allowlist riêng khi nghiệp vụ cần.

Dù có client ID allowlist, vẫn phải kiểm tra audience. `client_id` không thay thế resource binding.

### 7.3. Phiên bản Spring Security cần được thống nhất

- `JwtValidators.createAtJwtValidator()` có từ Spring Security 6.5.
- Tài liệu Spring Security hiện hành hướng dẫn dùng `.validateTypes(false)` cùng `createAtJwtValidator()` để xác minh RFC 9068.
- Các thay đổi mặc định liên quan JWT `typ` đã xuất hiện trong các dòng version mới; hãy theo đúng tài liệu của BOM mà ứng dụng đang dùng.

Không sao chép validator từ version khác mà không kiểm tra behavior của `typ`, vì có thể tạo xung đột giữa Nimbus type verifier và access-token profile validator.

## 8. Nếu issuer không dùng RFC 9068

Không phải mọi Authorization Server đều phát access token theo RFC 9068. Có thể AS phát JWT với:

~~~json
{
  "typ": "JWT",
  "iss": "https://legacy-idp.example.com",
  "aud": "orders-api",
  "sub": "user-42",
  "scope": "orders.read"
}
~~~

Khi đó, Resource Server cần một profile được thống nhất riêng:

- Thuật toán được phép.
- Issuer chính xác.
- Audience bắt buộc.
- Claim/type dùng để nhận diện access token.
- Required claims.
- Time validation.
- Cách map scopes/roles.
- Cách phân biệt token này với ID token hoặc JWT khác cùng issuer.

Có thể viết `OAuth2TokenValidator<Jwt>` riêng để kiểm tra header `typ` hoặc custom claims. Tuy nhiên, phải kết hợp với validators issuer/time/audience chuẩn và không bỏ signature verification.

Ví dụ validator kiểm tra custom header type:

~~~java
private OAuth2TokenValidator<Jwt> customAccessTokenTypeValidator() {
    return jwt -> {
        Object type = jwt.getHeaders().get("typ");

        if ("orders-access+jwt".equals(type)) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Unexpected JWT type",
                null
            )
        );
    };
}
~~~

Đây chỉ là một validator thành phần. Khi dùng custom profile, phải cấu hình decoder để type handling không xung đột với validator, và kết hợp validator này với:

- `JwtIssuerValidator`.
- `JwtTimestampValidator`.
- Audience validator.
- Signature algorithm allowlist.

Không copy custom `typ` từ ví dụ này vào production nếu AS chưa phát hành đúng giá trị đó.

## 9. Ví dụ custom audience validator

Nếu không dùng RFC 9068 builder, hoặc cần audience policy phức tạp, có thể dùng `OAuth2TokenValidator`.

~~~java
package com.example.orders.security;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class OrdersAudienceValidator
        implements OAuth2TokenValidator<Jwt> {

    private static final String REQUIRED_AUDIENCE = "orders-api";

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience().contains(REQUIRED_AUDIENCE)) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Token is not intended for Orders API",
                null
            )
        );
    }
}
~~~

Kết hợp validator:

~~~java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        new OrdersAudienceValidator()
    )
);
~~~

Đoạn code này minh họa audience validator bổ sung. Nếu cần explicit type validation theo custom profile, thêm validator tương ứng theo đúng Spring Security version và không để default type validation vô tình từ chối token hợp lệ hoặc chấp nhận token sai loại.

**Lưu ý:** `createDefaultWithIssuer(...)` giữ các validators mặc định mà Spring cung cấp cho generic JWT trong version tương ứng. Nếu bạn chủ động thay đổi type validation, hãy xác nhận bộ validators cuối cùng vẫn kiểm tra timestamp, issuer, audience và type theo profile đã chọn.

## 10. Phân biệt ID token và access token bằng nhiều lớp

Một chiến lược an toàn không nên chỉ dựa vào `typ`. Hãy kết hợp:

| Thuộc tính | ID token | JWT access token theo RFC 9068 |
|---|---|---|
| JOSE `typ` | Có thể là `JWT` hoặc theo provider profile | `at+jwt` hoặc `application/at+jwt` |
| `aud` | OIDC client ID | Resource server identifier |
| `iss` | OIDC Provider issuer | Authorization Server issuer |
| `sub` | End-user subject | Subject theo access-token profile |
| `client_id` | Không phải claim cốt lõi của ID token | Claim access-token profile |
| `scope` | Không phải cách xác định API permission | Có thể mang OAuth scopes |
| Consumer | OIDC client | Resource Server |
| Validation profile | OIDC Core ID Token validation | RFC 9068 access-token validation |

Các giá trị trong bảng là profile tiêu biểu. Không phải provider nào cũng phát mọi custom claim giống nhau. Cần lấy contract từ issuer thực tế.

### 10.1. ID token có thể được ký bằng cùng signing key

Đừng giả định:

~~~text
ID token -> key A
Access token -> key B
~~~

Một issuer có thể dùng cùng signing key cho cả hai. Khi đó, chỉ kiểm tra chữ ký sẽ không phân biệt được token.

Hãy dùng explicit token type, audience khác nhau và validation rules loại trừ lẫn nhau. Nếu AS hỗ trợ key separation cho các token purpose, đó là một lớp bổ sung hữu ích.

### 10.2. Không dùng `nonce` làm API audience

`nonce` trong OIDC flow giúp client liên kết ID token với authentication request. Nó không phải resource indicator của Orders API.

Không thay `aud` check bằng `nonce`, `azp`, `client_id`, `email` hoặc `preferred_username`.

### 10.3. ID token không phải credential cho downstream API

Một web client có thể nhận:

- ID token để biết người dùng đã authenticate.
- Access token để gọi Orders API.
- Refresh token để xin access token mới tại token endpoint theo policy.

Mỗi token có mục đích riêng. Không forward ID token tới Orders API hoặc Billing API. Khi gọi API, dùng access token đúng audience/resource.

## 11. Token substitution giữa nhiều API

### 11.1. Ví dụ token dành cho API A bị gửi tới API B

Hệ thống có:

~~~text
Authorization Server
    |
    +-- Billing API
    |
    +-- Orders API
    |
    +-- Inventory API
~~~

AS phát:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-42",
  "aud": ["billing-api"],
  "scope": "read"
}
~~~

Billing API được phép chấp nhận token này. Orders API phải reject vì audience không chứa `orders-api`.

Nếu cả ba APIs đều chỉ kiểm tra issuer và chữ ký, token có thể bị sử dụng xuyên resource. Đây là substitution attack được RFC 8725 nhấn mạnh.

### 11.2. Scope tên giống nhau không làm token dùng chung

Giả sử cả Billing và Orders đều có scope `read`:

~~~text
billing-api: read
orders-api: read
~~~

Hai scope này không tự có cùng semantics. Access token phải được ràng buộc tới resource dự kiến, và API phải áp dụng quyền theo đúng contract.

Có thể dùng naming convention rõ hơn:

~~~text
billing.read
orders.read
inventory.read
~~~

Nhưng naming convention vẫn không thay audience validation.

### 11.3. Resource Indicators

RFC 8707 định nghĩa Resource Indicators cho OAuth 2.0. Client có thể chỉ định resource mà access token dự kiến sử dụng.

Ví dụ token request:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
resource=https%3A%2F%2Fapi.example.com%2Forders
~~~

AS có thể dùng `resource` để ràng buộc token với audience tương ứng. Cách mapping resource URI sang `aud` phải được thống nhất giữa AS và Resource Server.

Không phải mọi AS đều hỗ trợ RFC 8707. Nếu không hỗ trợ, cần cơ chế audience mapping khác đã được xác nhận.

### 11.4. Token exchange khi gọi downstream API

Nếu API A cần gọi API B thay mặt user, không nên forward access token `aud=api-a` sang API B rồi kỳ vọng B chấp nhận.

Các lựa chọn tùy kiến trúc:

- Xin access token mới dành cho `api-b`.
- Dùng OAuth Token Exchange theo RFC 8693 nếu AS hỗ trợ.
- Dùng on-behalf-of flow theo vendor/AS contract.
- Giữ actor/subject delegation semantics rõ ràng.

API B vẫn phải xác minh audience của token mới. Không sửa claim `aud` trong JWT cũ hoặc tạo token nội bộ bằng cách copy payload.

## 12. Multi-issuer: issuer, algorithm và audience phải đi cùng nhau

Một API có thể tin nhiều issuers:

~~~text
Issuer A -> JWKS A -> RS256 -> aud orders-api
Issuer B -> JWKS B -> ES256 -> aud orders-api
~~~

Không nên dùng một policy mơ hồ như:

~~~text
accept any issuer
accept any algorithm
accept any audience
```

Mỗi issuer nên có trust profile riêng:

| Thuộc tính | Issuer A | Issuer B |
|---|---|---|
| Canonical `iss` | URL A | URL B |
| JWKS URI | JWKS A | JWKS B |
| Allowed algorithm | RS256 | ES256 |
| Audience | orders-api | orders-api |
| Token type | at+jwt | at+jwt |
| Required claims | RFC 9068 + policy | RFC 9068 + policy |
| Client allowlist | clients A | clients B |

### 12.1. Chọn manager chỉ từ trusted issuer registry

Có thể dùng `JwtIssuerAuthenticationManagerResolver` với allowlist:

~~~java
@Bean
AuthenticationManagerResolver<HttpServletRequest> issuerResolver() {
    return JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://issuer-a.example.com",
        "https://issuer-b.example.com"
    );
}
~~~

Resolver chọn manager theo issuer, nhưng token vẫn phải qua decoder/validators của issuer đó. `iss` trong payload chưa được xác minh không được dùng để cấp quyền.

Mỗi manager/decoder cần đúng algorithm allowlist, JWKS URI, audience và token-type policy.

### 12.2. Không dùng key của issuer A cho issuer B

Hai issuers có thể cùng dùng:

~~~text
kid = signing-key-1
~~~

Nhưng public keys khác nhau. Không cache key chỉ theo `kid`; phải namespace theo issuer/JWKS source.

### 12.3. Không fetch JWKS URL từ JWT header

Không để `jku`, `x5u` hoặc một claim chưa xác minh điều khiển outbound key lookup. Điều đó có thể tạo SSRF và làm attacker đưa khóa của họ vào trust path.

## 13. Opaque token cũng cần resource binding

Không phải access token nào cũng là JWT. Opaque token không có JOSE `alg`, `typ` hoặc `kid` để Resource Server tự kiểm tra.

Với opaque token, Resource Server gọi introspection endpoint:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <resource-server-credentials>

token=opaque-access-token
~~~

Response minh họa:

~~~json
{
  "active": true,
  "iss": "https://login.example.com",
  "sub": "user-42",
  "client_id": "storefront-web",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

Resource Server cần kiểm tra:

- `active=true`.
- Token thuộc issuer/introspection trust context phù hợp.
- Audience/resource phù hợp với API, nếu AS trả trường này.
- Scope/authorities phù hợp.
- Expiry và các thuộc tính theo contract.

RFC 7662 cho phép AS trả response khác nhau tùy protected resource gọi introspection. Nếu response không có `aud`, phải có contract rõ rằng endpoint/client authentication chỉ trả active token phù hợp cho resource server đó. Không mặc định mọi opaque token active đều có thể dùng tại mọi API.

Opaque token không dùng JOSE algorithm confusion, nhưng vẫn có thể gặp token substitution giữa APIs nếu resource binding bị bỏ qua.

## 14. Cấu hình HTTP authorization sau khi token đã xác thực

Sau authentication và validation, Spring Security ánh xạ scope thành authority, thường có prefix `SCOPE_`.

Ví dụ:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

Đoạn này chỉ minh họa authorization. Nó giả định `JwtDecoder` đã được cấu hình để kiểm tra:

- Algorithm allowlist.
- Signature.
- Issuer.
- Access-token profile/type.
- Audience/resource.
- Time claims.

Nếu token dành cho Billing API nhưng có `orders.read`, decoder phải reject trước khi authority mapping và HTTP authorization diễn ra.

### 14.1. Authentication failure và authorization failure

| Trường hợp | Kết quả thường gặp | Lý do |
|---|---:|---|
| `alg=none` | 401 | Không có chữ ký hợp lệ |
| `HS256` trong khi chỉ allow RS256 | 401 | Thuật toán không được chấp nhận |
| Chữ ký sai | 401 | Token không xác thực được |
| ID token gửi tới API theo RFC 9068 | 401 | Sai token profile/type và audience |
| Access token có `aud=billing-api` gửi tới Orders API | 401 | Token không dành cho resource này |
| Issuer không được tin | 401 | Sai trust context |
| Token hợp lệ đúng audience nhưng thiếu scope | 403 | Authorization thất bại |
| Token đúng scope nhưng order thuộc tenant khác | 403/404 theo policy | Business authorization |

Audience mismatch và wrong token type là lỗi authentication/profile validation, không phải chỉ thiếu quyền ở endpoint.

## 15. Kiểm thử algorithm confusion

Một bộ test cần chứng minh decoder chỉ chấp nhận thuật toán được cấu hình.

### 15.1. Ma trận test

| JWT | Cấu hình decoder | Kết quả mong đợi |
|---|---|---|
| RS256, đúng RSA key | RS256 allowlist | Pass nếu claims đúng |
| RS256, key khác | RS256 allowlist | Reject signature |
| HS256, dù dùng bytes public key làm secret | RS256 allowlist | Reject algorithm |
| `alg=none` | RS256 allowlist | Reject |
| ES256 | RS256 allowlist | Reject |
| RS512 | RS256 allowlist | Reject |
| Header có `jku` trỏ URL attacker | JWKS URI cố định | Không fetch URL từ header |
| `kid` không tồn tại | JWKS của issuer | Reject sau key lookup/refresh theo policy |

### 15.2. Dùng key test riêng

- Sinh RSA key pair dành riêng cho test.
- Dùng private key ký JWT hợp lệ.
- Cấu hình decoder bằng RSA public key hoặc test JWKS.
- Tạo một token khác dùng key pair khác.
- Tạo token với thuật toán không nằm trong allowlist.
- Xác nhận decoder từ chối các token sai.

Không dùng signing keys production trong unit/integration test.

### 15.3. Không chỉ test `jwt()` mock

`MockMvc` với `.with(jwt())` hoặc WebTestClient `.mockJwt()` thường tạo authentication giả lập và bỏ qua decoder. Chúng hữu ích để test authorization, nhưng không chứng minh algorithm allowlist hoặc chữ ký.

Muốn test algorithm, hãy gửi `Authorization: Bearer <signed-token>` qua filter chain thật với `JwtDecoder` thực.

## 16. Kiểm thử token-type confusion

Tạo các JWT riêng:

| Token fixture | Header/payload | Kết quả tại Orders API |
|---|---|---|
| Access token đúng profile | `typ=at+jwt`, `aud=orders-api` | Pass nếu các claims/rights đúng |
| ID token | `typ` theo OIDC provider, `aud=storefront-web` | Reject |
| JWT chung | `typ=JWT`, không có access-token profile | Reject nếu API yêu cầu RFC 9068 |
| Client assertion | Audience token endpoint, không phải Orders API | Reject |
| Logout/security event token | Token profile khác | Reject |
| Access token profile đúng nhưng audience sai | `typ=at+jwt`, `aud=billing-api` | Reject |

### 16.1. ID token có chữ ký đúng vẫn phải bị từ chối

Một test quan trọng:

1. Ký ID token bằng cùng test key mà decoder tin cậy.
2. Dùng cùng issuer.
3. Đặt `aud=storefront-web`.
4. Gửi token đó tới Orders API.
5. Xác nhận API từ chối vì token type/profile và audience không phù hợp.

Test này chứng minh hệ thống không dựa vào chữ ký đơn lẻ.

### 16.2. Test `typ`

Với RFC 9068:

- Chấp nhận `at+jwt` hoặc `application/at+jwt`.
- Từ chối `JWT` nếu profile validator yêu cầu access-token type.
- Từ chối type của token khác.
- Từ chối thiếu `typ` nếu profile bắt buộc.
- Không thay đổi behavior bằng cách tắt type validation mà quên bổ sung profile validator.

### 16.3. Không giả định mọi AS phát cùng type

Nếu AS chưa hỗ trợ RFC 9068, hãy kiểm thử theo profile thực tế. Không tự sửa JWT trong test để có `typ=at+jwt` rồi kết luận issuer production đã tương thích.

## 17. Kiểm thử audience/resource substitution

Tạo hai APIs:

~~~text
orders-api
billing-api
~~~

Và hai token:

~~~json
{
  "iss": "https://login.example.com",
  "aud": ["orders-api"],
  "scope": "read"
}
~~~

~~~json
{
  "iss": "https://login.example.com",
  "aud": ["billing-api"],
  "scope": "read"
}
~~~

Test:

| Request | Token | Kết quả |
|---|---|---|
| Orders API | Audience orders-api | Pass nếu scope đúng |
| Orders API | Audience billing-api | 401 |
| Billing API | Audience billing-api | Pass nếu scope đúng |
| Billing API | Audience orders-api | 401 |
| Orders API | Audience có cả hai resource | Theo policy multi-audience đã định nghĩa |
| Orders API | Không có `aud` | Reject |
| Orders API | `aud` rỗng | Reject |

Một test có thể assert controller/service không được gọi khi audience sai:

~~~java
mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + billingToken))
    .andExpect(status().isUnauthorized());

verifyNoInteractions(ordersService);
~~~

Test này cần `billingToken` được ký bằng test key và request đi qua decoder thật.

## 18. Kiểm thử cross-issuer và key confusion

Nếu API tin nhiều issuers:

- Issuer A và B có key khác nhau.
- Cả hai có thể dùng cùng `kid`.
- Cả hai có thể dùng cùng thuật toán.
- Mỗi issuer có audience/token profile riêng.

Test:

1. Token A ký bằng key A và `iss=A`.
2. Token B ký bằng key B và `iss=B`.
3. Token A sửa `iss=B` nhưng giữ chữ ký A.
4. Token B gửi tới decoder A.
5. Hai issuer cùng `kid=key-1`, xác nhận đúng decoder/key namespace.
6. Issuer không allowlist.
7. `jku` trỏ host khác.
8. Audience của issuer A không đúng resource B.

Không dùng một decoder global có thể nhận khóa từ issuer bất kỳ. Dùng issuer-specific manager/decoder đã được cấu hình tin cậy.

## 19. Các anti-pattern cần tránh

### 19.1. Chấp nhận mọi `alg`

~~~java
// Sai về thiết kế: không có allowlist rõ ràng.
acceptAlgorithm(jwt.getHeaders().get("alg"));
~~~

Thuật toán phải được cấu hình theo issuer và key policy, không theo token header.

### 19.2. Cho phép HS256 chỉ vì API đang dùng RS256

Không dùng RSA public key bytes làm HMAC secret. Nếu có nhu cầu HMAC, thiết kế shared-secret key management riêng và không dùng chung key với asymmetric signature.

### 19.3. Chỉ kiểm tra chữ ký

JWT có chữ ký đúng vẫn có thể là ID token, client assertion hoặc access token của API khác. Cần type/profile, issuer và audience validators.

### 19.4. Chỉ kiểm tra `sub`

`sub` không chứng minh token là access token hoặc dành cho resource hiện tại.

### 19.5. Dùng `client_id` thay `aud`

Client ID nhận diện OAuth client; audience nhận diện recipient/resource. Không dùng một field thay field kia.

### 19.6. Dùng scope thay audience

Scope `read` có thể xuất hiện ở nhiều APIs. Nó không chứng minh token được cấp cho API đang xử lý.

### 19.7. Chấp nhận ID token ở API

ID token được phát cho OIDC client. Resource Server phải nhận access token theo profile mà nó hỗ trợ.

### 19.8. Tắt type validation mà không thay validator

Nếu dùng `.validateTypes(false)` để tích hợp RFC 9068, phải gắn `JwtValidators.createAtJwtValidator()` theo hướng dẫn version tương ứng. Nếu chỉ tắt type validation, API có thể mất một lớp phân biệt JWT profile.

### 19.9. Tin `jku`/`x5u` tùy ý

Không để JWT header điều khiển nơi Resource Server tải signing key. Chỉ dùng issuer/JWKS URI đã được tin cậy.

### 19.10. Một validator dùng chung cho mọi issuer/token purpose

Nếu cùng issuer phát ID token và access token, validation rules phải loại trừ lẫn nhau. Dùng profile-specific decoders/validators khi cần.

### 19.11. Chấp nhận audience bất kỳ

Không dùng “audience có tồn tại” thay cho “audience có chứa resource identifier của API này”.

### 19.12. Chỉ test bằng mock authentication

`jwt()`/`mockJwt()` có thể bypass signature, algorithm, issuer, type và audience validation. Cần test bearer request với signed token.

### 19.13. Trả 403 cho token sai audience

Token không dành cho API không được authenticated tại API đó. Reject ở authentication validation, thường 401.

## 20. Quy trình triển khai an toàn

**Bước 1 — Chọn token profile.** Xác nhận AS phát JWT access token theo RFC 9068 hay custom profile.

**Bước 2 — Xác nhận issuer và JWKS.** Chọn issuer canonical, JWKS URI và key rotation contract.

**Bước 3 — Khóa thuật toán.** Cấu hình allowlist cụ thể, ví dụ RS256. Kiểm tra key type và key usage.

**Bước 4 — Xác định token type.** Yêu cầu `typ=at+jwt` nếu dùng RFC 9068; nếu custom, định nghĩa type/claim rules riêng.

**Bước 5 — Xác định audience.** Chọn resource identifier ổn định cho từng API. Không dùng client ID thay resource audience.

**Bước 6 — Cấu hình validators.** Signature, issuer, time, audience, type/profile và required claims.

**Bước 7 — Cấu hình authorization.** Map scopes/roles sau khi authentication thành công; kiểm tra tenant và ownership trong business layer.

**Bước 8 — Viết negative tests.** `alg=none`, HS/RS confusion, wrong typ, ID token, wrong issuer, wrong audience và token hết hạn.

**Bước 9 — Kiểm tra nhiều APIs.** Gửi token của API A sang API B và xác nhận bị từ chối.

**Bước 10 — Rollout theo issuer.** Nếu thay algorithm hoặc token profile, phối hợp AS và Resource Servers, có giai đoạn overlap/rollback được quản lý.

## 21. Ma trận quyết định authentication

| Chữ ký/alg | Token type | Issuer | Audience | Kết quả |
|---|---|---|---|---|
| Đúng | Access token | Đúng | Orders API | Tiếp tục kiểm tra expiry/scope |
| Sai | Access token | Đúng | Orders API | Reject |
| Dùng `alg` ngoài allowlist | Access token | Đúng | Orders API | Reject |
| Đúng | ID token | Đúng | Web client | Reject tại Orders API |
| Đúng | Access token | Sai | Orders API | Reject |
| Đúng | Access token | Đúng | Billing API | Reject tại Orders API |
| Đúng | Access token | Đúng | Orders API | Scope thiếu -> 403 |
| Đúng | Access token | Đúng | Orders API | Tenant/owner sai -> 403/404 theo policy |
| Đúng | Token type không xác định | Đúng | Orders API | Reject |
| Không có chữ ký | Bất kỳ | Bất kỳ | Bất kỳ | Reject |

Thứ tự triển khai cụ thể có thể khác theo decoder, nhưng không được bỏ qua bất kỳ điều kiện nào.

## 22. Câu hỏi tự kiểm tra

**1.** Vì sao không được để JWT header tự quyết định thuật toán?

> Header chưa được xác minh và do bên gửi kiểm soát. Resource Server phải dùng allowlist algorithm được cấu hình trước.

**2.** Algorithm confusion giữa RS256 và HS256 xảy ra khi nào?

> Khi implementation nhầm public key của thuật toán asymmetric thành HMAC secret hoặc không ràng buộc key với thuật toán được phép.

**3.** `alg=none` có được chấp nhận cho OAuth JWT access token theo RFC 9068 không?

> Không. Access token phải được ký và `none` không được phép.

**4.** Chữ ký JWT hợp lệ có chứng minh token là access token không?

> Không. Nó chỉ chứng minh chữ ký theo trust/key policy; cần token-type/profile validation.

**5.** OIDC ID token được gửi cho ai?

> OIDC client/Relying Party; `aud` phải chứa client ID của client đó.

**6.** Access token audience biểu diễn điều gì?

> Resource Server hoặc resource identifier mà token được cấp để truy cập.

**7.** `typ=at+jwt` có ý nghĩa gì?

> JWT là OAuth 2.0 access token theo profile RFC 9068.

**8.** `token_type=Bearer` và JOSE `typ=at+jwt` có giống nhau không?

> Không. Một trường chỉ cách client trình access token; trường kia xác định JWT profile/type.

**9.** `client_id` có thay được `aud` không?

> Không. Client ID nhận diện OAuth client; audience nhận diện resource recipient.

**10.** Scope `orders.read` có đủ để Orders API chấp nhận token không?

> Không. Cần đúng issuer, chữ ký, token type và audience trước khi xét scope.

**11.** Vì sao cùng issuer và cùng signing key vẫn có thể gây token-type confusion?

> Vì issuer có thể phát nhiều loại JWT; chữ ký chung không phân biệt mục đích. Cần explicit typing và validation rules loại trừ nhau.

**12.** RFC 9068 validator trong Spring Security có từ version nào?

> `JwtValidators.createAtJwtValidator()` có từ Spring Security 6.5.

**13.** Vì sao code RFC 9068 dùng `.validateTypes(false)`?

> Để giao việc kiểm tra JWT access-token type cho profile validator thay vì type verifier mặc định của Nimbus; phải gắn `createAtJwtValidator()` ngay sau đó theo version docs.

**14.** Token có `aud=billing-api` nhưng gửi tới Orders API nên trả gì?

> Từ chối authentication, thường là 401, vì token không dành cho Orders API.

**15.** Nếu token đúng audience nhưng thiếu scope thì sao?

> Token đã authenticated nhưng không đủ quyền, thường 403.

**16.** Có thể dùng `jwt()` trong MockMvc để chứng minh algorithm allowlist không?

> Không. `jwt()` tạo mock authentication; cần signed bearer token qua decoder thật.

**17.** Có thể tin `jku` hoặc `x5u` trong JWT header không?

> Không nếu URL chưa được kiểm soát; chỉ dùng JWKS/key source thuộc issuer đã tin cậy.

**18.** Nếu một API cần gọi API khác thay mặt user, có nên forward access token cũ không?

> Chỉ khi audience của token cho phép resource đích. Thông thường cần token mới đúng audience, token exchange hoặc on-behalf-of flow.

## 23. Tài liệu tham khảo

- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): algorithm verification, key/algorithm binding, explicit typing, mutually exclusive validation rules, substitution và cross-JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): `typ=at+jwt`, required claims, issuer/audience/signature validation và access-token profile.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, `aud`, `azp`, `nonce` và validation phía OIDC client.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515.html): JOSE header và JWS signature.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517.html): JWK, `kty`, `kid`, `use`, `key_ops`, public key material.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html): JWT claims `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707.html): chỉ định resource trong OAuth token request.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): token exchange và delegation giữa resources/services.
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): algorithm allowlist, `NimbusJwtDecoder`, issuer/audience validation và RFC 9068.
- [Spring Security 6.5 — Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): `JwtValidators.createAtJwtValidator()` và cấu hình RFC 9068.
- [Spring Security — JwtValidators API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html): `createAtJwtValidator()` và builder cho JWT access-token profile.
- [Spring Security — JWT Type Validation Migration](https://docs.spring.io/spring-security/reference/7.0/migration/servlet/oauth2.html): thay đổi type validation trong dòng Spring Security mới.
- [Spring Security — Multi-tenancy Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): issuer-aware authentication manager và multi-issuer setup.

**Kết luận:** Một Resource Server chỉ nên chấp nhận JWT khi thuật toán/khóa nằm trong trust policy, token thuộc đúng profile, issuer được tin cậy và audience chứa resource identifier của chính API. Algorithm allowlist ngăn nhầm cách xác minh chữ ký; explicit typing và mutually exclusive validators ngăn ID token hoặc JWT khác mục đích bị dùng làm access token; audience validation ngăn access token của API này bị gửi sang API khác. Sau các bước đó, Spring Security mới ánh xạ scope/authority và ứng dụng tiếp tục kiểm tra tenant, ownership cùng quyền nghiệp vụ.
