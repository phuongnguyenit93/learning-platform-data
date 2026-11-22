# JWS và JWE: ký, mã hóa và phạm vi hỗ trợ của decoder

## 1. Bối cảnh: JWT, JOSE và Resource Server

Khi xây dựng **Spring Security OAuth 2.0 / OIDC Resource Server**, API thường nhận access token dưới dạng JWT qua HTTP:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

Trong các thiết kế dùng **JWT**, cấu trúc token có thể thuộc hai dạng JOSE khác nhau:

- **JWS (JSON Web Signature)**: bảo vệ **tính toàn vẹn** và xác minh chữ ký/MAC của nội dung. Payload không được che giấu chỉ nhờ chữ ký.
- **JWE (JSON Web Encryption)**: bảo vệ **tính bí mật** của nội dung bằng mã hóa và cung cấp kiểm tra tính toàn vẹn của bản mã qua cơ chế mật mã thích hợp.

Hai dạng này dễ bị nhầm vì đều có thể truyền dưới dạng một chuỗi gọn, cùng bắt đầu bằng phần header mã hóa Base64URL. Nhưng **kiểm tra chữ ký** và **giải mã dữ liệu** là các thao tác khác nhau, cần khóa khác nhau và thường được hỗ trợ bởi các thành phần khác nhau.

**Mục tiêu bài học:** hiểu JWS/JWE trong họ chuẩn **JOSE**, nhận diện dạng token theo cấu trúc, biết giới hạn của `NimbusJwtDecoder` trong Spring Security Resource Server, và biết cách thiết kế khi nhà phát hành cung cấp JWE thay vì access token JWS thông thường.

### 1.1. Các thuật ngữ nền tảng

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **JWT** | JSON Web Token: biểu diễn tập claim, thường dùng cho access token hoặc ID Token | `iss`, `sub`, `aud`, `exp` |
| **JOSE** | Họ chuẩn xử lý chữ ký, mã hóa và khóa với JSON | JWS, JWE, JWK, JWA |
| **JWS** | Biểu diễn thông điệp có chữ ký số hoặc MAC | JWT ký với RS256 |
| **JWE** | Biểu diễn thông điệp được mã hóa | JWT mã hóa bằng RSA-OAEP-256 + A256GCM |
| **JWK** | JSON Web Key: biểu diễn khóa bằng JSON | Public key RSA/EC |
| **JWKS** | JSON Web Key Set: tập các JWK | Endpoint `jwks_uri` của issuer |
| **JWA** | JSON Web Algorithms: tên và tham số thuật toán | `RS256`, `PS256`, `ES256`, `A256GCM` |

JWT được mô tả bởi RFC 7519. Khi JWT được bảo vệ bằng JWS hoặc JWE, nó kế thừa quy tắc của JWS (RFC 7515) hoặc JWE (RFC 7516). **Không phải mọi chuỗi có ba phần ngăn bởi dấu chấm đều là JWT đáng tin**, và cũng không phải mọi chuỗi JWT đều là JWT đã ký.

## 2. JWS: ký để xác minh tính toàn vẹn và nguồn phát hành

### 2.1. Cấu trúc JWS Compact Serialization

Một **JWS compact** thường gồm **3 phần** phân tách bằng dấu chấm:

~~~text
BASE64URL(protected header)
.
BASE64URL(payload)
.
BASE64URL(signature)
~~~

Viết liền trên HTTP:

~~~text
eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMifQ.<signature>
~~~

Chuỗi trên chỉ minh họa cấu trúc; `<signature>` không phải chữ ký thật.

Phần protected header có thể chứa:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-2026-01"
}
~~~

Payload có thể chứa các claim:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1999999700,
  "exp": 2000000000
}
~~~

Các JSON trên dùng để giải thích cấu trúc, không đại diện một token có thể xác minh. Trong JWS Compact, header và payload thường chỉ được **Base64URL-encode**, không được mã hóa bí mật; bất kỳ người nhận chuỗi token nào cũng có thể đọc nội dung khi decode.

### 2.2. JWS bảo vệ điều gì?

Về khái niệm, đối với JWT JWS với `alg = RS256`:

~~~text
signingInput = BASE64URL(header) + "." + BASE64URL(payload)
signature    = RSA-SHA256-SIGN(privateSigningKey, signingInput)
~~~

Resource Server dùng **public key** tương ứng để kiểm tra chữ ký.

~~~mermaid
flowchart LR
    A["Issuer / Authorization Server"] --> B["JWT claims"]
    B --> C["Ký JWS bằng private key"]
    C --> D["Access token compact (3 phần)"]
    D --> E["Spring Resource Server"]
    F["JWKS public key"] --> G["JWS signature verifier"]
    E --> G
    G --> H["Validate iss, aud, exp, nbf, scope..."]
    H --> I["Quyết định truy cập API"]
~~~

Nếu chữ ký hợp lệ với khóa tin cậy, bên xác minh có bằng chứng rằng **nội dung đã được bảo vệ bởi khóa ký phù hợp** và không bị thay đổi sau khi ký. Tuy nhiên, ứng dụng còn phải xác định khóa thuộc issuer nào và token được cấp cho audience nào; chỉ xác minh chữ ký là chưa đủ để cho phép truy cập.

JWS **không cung cấp tính bí mật** của payload. Không đặt mật khẩu, khóa riêng, secret hoặc dữ liệu cá nhân không cần thiết vào claim rồi cho rằng ký JWT sẽ che giấu chúng.

### 2.3. Các thuật toán chữ ký thường gặp

| `alg` | Cách xác minh | Đặc điểm |
|---|---|---|
| `RS256` | Public key RSA, SHA-256 | Phổ biến ở các OAuth/OIDC provider |
| `PS256` | Public key RSA-PSS, SHA-256 | Chữ ký RSA-PSS |
| `ES256` | Public key EC, ECDSA P-256/SHA-256 | Chữ ký EC nhỏ hơn trong nhiều tình huống |
| `HS256` | Shared secret, HMAC-SHA256 | Bên ký và bên xác minh cùng biết bí mật |

Với nhiều Resource Server độc lập, chữ ký **bất đối xứng** cho phép API xác minh bằng public key mà không nắm private key ký token. Nếu dùng HMAC, mọi bên nắm shared secret có thể tạo MAC hợp lệ; cần thiết kế ranh giới tin cậy khác.

Giá trị `alg` nằm trong token là **input chưa đáng tin** cho đến khi việc xác thực hoàn tất. Hệ thống phải có **allowlist thuật toán** mong đợi và cấu hình khóa đúng loại. Không cho token tự quyết định ứng dụng phải dùng thuật toán hay khóa nào mà không kiểm soát.

### 2.4. `kid` và JWKS không tự quyết định tin cậy

Header `kid` giúp tìm **khóa phù hợp trong bộ khóa đã tin cậy**. Nó không có nghĩa là Resource Server được phép tải một khóa từ URL bất kỳ do token cung cấp.

Điển hình:

1. Resource Server đã cấu hình issuer/JWKS URI tin cậy.
2. Token có `kid` chỉ ra khóa ký.
3. Decoder tìm khóa trong JWKS của issuer đã cấu hình.
4. Xác minh signature bằng thuật toán cho phép.
5. Kiểm tra `iss`, `aud`, `exp` và các claim/chính sách khác.

JWKS thường cung cấp **public keys** để xác minh JWS; nó không phát tán private signing key của Authorization Server.

## 3. JWE: mã hóa để bảo vệ nội dung

### 3.1. Cấu trúc JWE Compact Serialization

**JWE compact** thường gồm **5 phần**, cũng nối bằng dấu chấm:

~~~text
BASE64URL(protected header)
.
BASE64URL(encrypted key)
.
BASE64URL(initialization vector)
.
BASE64URL(ciphertext)
.
BASE64URL(authentication tag)
~~~

Viết gọn:

~~~text
<protected-header>.<encrypted-key>.<iv>.<ciphertext>.<tag>
~~~

Lưu ý: phần `encrypted-key` có thể **rỗng** với một số cơ chế quản lý khóa như `alg = dir`. Vì vậy một phần rỗng không tự khiến chuỗi JWE sai định dạng.

Một protected header JWE điển hình:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "orders-encryption-2026-01",
  "typ": "JWT"
}
~~~

Trong JWE:

- **`alg`** mô tả thuật toán **quản lý/trao đổi khóa** dùng để có được Content Encryption Key (CEK), ví dụ `RSA-OAEP-256`.
- **`enc`** mô tả thuật toán **mã hóa nội dung** bằng CEK, ví dụ `A256GCM`.
- **IV** (initialization vector/nonce) và **authentication tag** hỗ trợ thuật toán mã hóa nội dung; thông số phải được tạo và sử dụng theo yêu cầu của thuật toán.
- **Ciphertext** chứa dữ liệu đã mã hóa; không thể suy ra claims chỉ bằng Base64URL-decode.

JWE yêu cầu giải mã với khóa thích hợp. Nếu dùng khóa công khai RSA của bên nhận để mã hóa CEK, bên nhận cần **private decryption key** tương ứng; public JWKS dùng để xác minh JWS **không tự cung cấp khả năng giải mã JWE**.

### 3.2. Thuộc tính an toàn của JWE

JWE nhằm bảo vệ **bí mật nội dung** và **tính toàn vẹn của bản mã**. Với AEAD như `A256GCM`, authentication tag giúp phát hiện bản mã hoặc dữ liệu liên quan đã bị thay đổi.

Nhưng **mã hóa không đồng nghĩa với chứng minh danh tính người phát hành**.

Giả sử public key của Orders API được công bố để các bên mã hóa token. Bất kỳ ai có public key cũng có thể tạo một JWE mã hóa về phía Orders API; vì thế việc API **giải mã thành công** chưa đủ chứng minh thông điệp được Authorization Server hợp lệ phát hành.

Muốn chứng minh issuer độc lập với người mã hóa, cần một cơ chế xác thực phát hành được thiết kế rõ: điển hình là **JWS được ký trước, sau đó được bọc trong JWE** (nested JWT), hoặc một trust model khác có đầy đủ ràng buộc khóa, nguồn và claims.

### 3.3. So sánh trực diện JWS và JWE

| Tiêu chí | JWS | JWE |
|---|---|---|
| Mục tiêu chính | Chữ ký/MAC, toàn vẹn, xác thực khóa ký | Bí mật nội dung và integrity/authentication tag của bản mã |
| Compact serialization | Thường 3 phần | Thường 5 phần |
| Payload đọc được khi Base64URL-decode? | Có, đối với JWT JWS thông thường | Không, cần giải mã |
| Header quan trọng | `alg`, `kid`, `typ` | `alg` (key management), `enc` (content encryption), `kid` |
| Khóa ở Resource Server | Public key để xác minh chữ ký (phổ biến) hoặc shared secret | Private decryption key hoặc key material thích hợp |
| Có đủ để xác thực người phát hành? | Chỉ khi khóa ký và issuer được tin cậy, claim được kiểm tra | Không mặc định; phụ thuộc mô hình xác thực nguồn và có thể cần JWS bên trong |
| Vai trò với Spring JWT Resource Server mặc định | Hình thức JWT signed được hỗ trợ thông thường | Cần xử lý giải mã riêng trước/bên ngoài decoder mặc định |

Không nên hiểu hai chuẩn theo kiểu “JWE an toàn hơn JWS trong mọi hoàn cảnh”. **JWS và JWE đáp ứng những nhu cầu bảo vệ khác nhau**. Một API có thể cần JWS và TLS, hoặc có thêm JWE nếu yêu cầu bảo mật nội dung xuyên qua nhiều trung gian.

## 4. JWT ký rồi mã hóa: Nested JWT

Khi cần **xác minh token do issuer phát hành** đồng thời **không để các trung gian đọc claims**, có thể dùng mô hình **sign-then-encrypt**.

~~~mermaid
flowchart TD
    A["JSON JWT claims"] --> B["Issuer ký tạo JWS"]
    B --> C["JWS compact - 3 phần"]
    C --> D["Mã hóa tạo JWE bên ngoài"]
    D --> E["JWE compact - 5 phần"]
    E --> F["Resource Server giải mã JWE"]
    F --> G["Trích JWS bên trong"]
    G --> H["Xác minh JWS bằng khóa ký của issuer"]
    H --> I["Kiểm tra iss / aud / exp / scope"]
    I --> J["Cấp quyền truy cập nếu hợp lệ"]
~~~

Ở lớp JWE bên ngoài, header `cty` có thể thể hiện nội dung bên trong là một JWT:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "cty": "JWT"
}
~~~

Theo quy tắc nested JWT của RFC 7519, `cty: "JWT"` có ý nghĩa thông báo payload là JWT được bọc. Nhưng **`cty` chỉ là metadata**; không thay thế giải mã, xác minh chữ ký và validation chính sách.

Quy trình phía Resource Server cần giữ đúng thứ tự:

1. Xác minh cú pháp và **chỉ chấp nhận thuật toán JWE đã cho phép**.
2. Chọn khóa giải mã từ tập khóa đáng tin, giải mã và xác minh integrity tag.
3. Kiểm tra rằng payload bên trong có đúng loại/token/profile được hợp đồng cho phép.
4. Nếu bên trong là JWS, **xác minh chữ ký của JWS** bằng khóa ký tin cậy của issuer.
5. Kiểm tra `iss`, `aud`, `exp`, `nbf`, token type và scope/authority theo API.
6. Sau khi các kiểm tra thành công mới dựng authentication principal và ra quyết định phân quyền.

Không nên lấy JSON claim sau giải mã JWE rồi tự tạo principal, bỏ qua bước chứng minh nó được issuer đáng tin phát hành. Tương tự, không được bỏ kiểm tra audience chỉ vì outer JWE dành cho đúng khóa giải mã của API.

## 5. Spring Security JWT decoder mặc định hỗ trợ gì?

### 5.1. Resource Server xử lý Bearer token và JWS

Với Spring Boot, khi thêm dependency OAuth2 Resource Server và cấu hình:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

Ứng dụng có thể xây dựng Resource Server nhận **JWT access token ký bằng JWS**. `issuer-uri` là địa chỉ issuer minh họa; phải dùng giá trị thực tế của Authorization Server.

Ví dụ SecurityFilterChain:

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
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Ở đây:

- `BearerTokenAuthenticationFilter` trích xuất chuỗi Bearer token.
- `JwtAuthenticationProvider` gọi `JwtDecoder` để giải mã/kiểm tra JWT.
- Implementation mặc định phổ biến là **`NimbusJwtDecoder`**, tích hợp với thư viện Nimbus JOSE + JWT.
- Decoder xác minh JWS với khóa và thuật toán phù hợp rồi kiểm tra các validator JWT đã cấu hình.
- Sau khi xác thực, Spring tạo authentication; chính sách endpoint kiểm tra quyền truy cập.

**Phân biệt tên thư viện và năng lực cấu hình:** thư viện **Nimbus JOSE + JWT** tự thân có API xử lý JWS, JWE và nhiều loại JOSE; nhưng **`NimbusJwtDecoder` của Spring Security không tự giải mã JWE compact thành JWT đã xác thực theo cấu hình Resource Server JWT thông thường**. Việc đặt dependency Nimbus trong classpath không tự bật hỗ trợ encrypted access token.

### 5.2. Decoder JWS dùng JWKS

Một Resource Server thường tin issuer và khóa công khai được công bố tại JWKS endpoint. Tùy cấu hình, Spring có thể đọc metadata của issuer để xác định `jwks_uri` và dùng public keys để kiểm tra chữ ký.

Header:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-01",
  "typ": "JWT"
}
~~~

Trình xác minh dùng `kid` để chọn public key trong JWKS tin cậy, nhưng vẫn áp dụng giới hạn thuật toán đã cấu hình. Nó không cần private signing key của Authorization Server.

**JWKS public key để xác minh JWS khác với khóa giải mã JWE.** Trỏ `jwk-set-uri` đến endpoint chứa signing public keys sẽ không tự cho phép Resource Server đọc ciphertext của JWE.

### 5.3. Cấu hình thuật toán JWS cho phép

Ví dụ chọn chính xác thuật toán `RS256` nếu issuer có hợp đồng ký token bằng RS256:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder() {
        return NimbusJwtDecoder
            .withJwkSetUri("https://id.example.test/realms/shop/protocol/openid-connect/certs")
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();
    }
}
~~~

Đường dẫn `jwks_uri` trong ví dụ mang cấu trúc của một số IdP; cần đọc metadata thật của provider. Đoạn mã minh họa cách **giới hạn thuật toán xác minh JWS**, chưa phải cấu hình validation hoàn chỉnh của ứng dụng.

**Lưu ý khi tự tạo bean decoder:** phải thêm/giữ lại đầy đủ validator cần thiết như issuer, hạn, audience. Không vô tình làm mất validator issuer chỉ vì bạn thay thế cấu hình tự động của Spring Boot bằng decoder tự tạo.

Một ví dụ đầy đủ hơn về validator cho signed JWT access token ở dưới đây.

### 5.4. Validator đối với JWS access token

~~~java
package com.example.orders.security;

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
public class OrdersJwtConfig {

    private static final String ISSUER =
        "https://id.example.test/realms/shop";

    private static final String JWKS_URI =
        "https://id.example.test/realms/shop/protocol/openid-connect/certs";

    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS_URI)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> expectedAudience = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Access token audience is not orders-api",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                standard,
                expectedAudience
            )
        );

        return decoder;
    }
}
~~~

Mã trên minh họa việc xác minh **JWS chữ ký hợp lệ + issuer/thời hạn + audience**. Các endpoint vẫn cần cấu hình `hasAuthority("SCOPE_orders.read")` hoặc kiểm tra quyền tương đương. Với chuẩn JWT access token và những yêu cầu như `typ = at+jwt`, có thể cần validator phù hợp profile/token type và phiên bản Spring Security dùng trong dự án.

Thư viện, bean và những validation ở đây **không biến `NimbusJwtDecoder` thành JWE decoder**.

## 6. Điều gì xảy ra khi đưa JWE vào Resource Server chỉ cấu hình JWT mặc định?

Giả sử client gửi **JWE compact 5 phần** trong Bearer token:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <jwe-header>.<encrypted-key>.<iv>.<ciphertext>.<tag>
~~~

Resolver vẫn có thể tách chuỗi khỏi header `Authorization` vì đây là Bearer token ở tầng HTTP. Nhưng `NimbusJwtDecoder` thông thường mong đợi **signed JWT/JWS** theo cấu hình Resource Server JWT.

Do đó API **không tự giải mã** token JWE chỉ bằng cấu hình `issuer-uri` hoặc `jwk-set-uri`; kết quả thông thường là **401 Unauthorized** vì xác thực JWT thất bại, chứ không phải một JWT đã được giải mã rồi kiểm tra scope.

Các thao tác không giải quyết được vấn đề JWE:

- Thay tên header từ `Authorization` sang `X-Access-Token`: chỉ đổi nơi đọc Bearer token.
- Thêm `jwk-set-uri` của signing keys: chỉ cung cấp public keys để xác minh chữ ký JWS.
- Đặt `jwsAlgorithm(ES256)` hoặc `jwsAlgorithm(RS256)`: chỉ cấu hình xác minh **JWS**, không kích hoạt JWE.
- Base64URL-decode phần ciphertext: không phải giải mã.
- Parse JSON claim từ ciphertext hoặc bỏ qua validation sau khi giải mã: không tạo một authentication đáng tin.
- Dùng OIDC ID Token thay cho access token: ID Token có audience và mục đích riêng, không được dùng làm chứng thư gọi API.

### 6.1. Bảng hành vi theo loại token

| Token bên ngoài | Resource Server JWT mặc định | Giải thích |
|---|---|---|
| Signed JWS access token (3 phần), thuật toán/issuer/claim hợp lệ | **Có thể xác thực** | Cần JWS signature và validators đều thành công |
| Signed JWS nhưng signature sai | **Từ chối** | Không xác minh được chữ ký |
| Signed JWS nhưng sai `aud` nếu có validator audience | **Từ chối** | Token không dành cho API |
| JWE compact (5 phần) | **Không tự giải mã** | Cần thành phần decrypt JWE được cấu hình rõ |
| Nested JWT: JWS nằm trong JWE | **Không tự giải mã lớp ngoài** | Phải giải mã JWE rồi xác minh JWS trong |
| Opaque access token | **Không thể xác minh như JWT** | Cần opaque-token introspection nếu provider hỗ trợ |
| Plain/unsigned JWT | **Không coi như signed JWS đáng tin** | Không thể bỏ yêu cầu ký chỉ vì payload là JSON |

Bảng nói về luồng `oauth2ResourceServer(...jwt(...))` của Spring Security Servlet và cấu hình JWT thông thường. Hệ thống tự viết `JwtDecoder` chuyên dụng hoặc chuyển đổi token tại gateway có thể có kiến trúc khác; phải đánh giá riêng.

## 7. Nếu hệ thống buộc phải nhận JWE thì thiết kế thế nào?

### 7.1. Ưu tiên thống nhất hợp đồng phát hành token

Nếu Resource Server chỉ cần kiểm tra access token và không có yêu cầu mã hóa nội dung ở lớp token, phương án đơn giản, dễ vận hành là để Authorization Server phát hành **signed JWS access token** đúng audience cho API.

TLS bảo vệ dữ liệu trên đường truyền; kiểm soát log và lưu token an toàn vẫn là bắt buộc. JWS không giấu claim khỏi người nắm token, vì vậy hạn chế claim nhạy cảm và thời gian sống.

Không phải IdP nào cũng cấp JWE cho Resource Server. Hãy xác nhận cụ thể:

- Access token do issuer phát hành là **JWS, JWE hay opaque**?
- Nếu JWT, token có **3 hay 5 phần compact**?
- Có scope, audience và token type nào?
- Issuer phát hành **JWKS cho khóa ký**, còn khóa giải mã JWE thuộc bên nào?
- Có yêu cầu lưu bí mật claims xuyên qua proxy/gateway mà TLS thông thường không giải quyết được?

Không nên phán đoán dạng access token chỉ từ việc hệ thống có hỗ trợ OIDC hoặc client nhận ID Token.

### 7.2. Tùy chọn kiến trúc A: decode JWE trước Resource Server

Một thành phần chuyên trách có thể **giải mã và xác minh** JWE, sau đó chuyển một token/credential nội bộ đã được ràng buộc chặt tới backend. Nếu kết quả là JWS nguyên bản do issuer ký và có audience phù hợp, Resource Server có thể xác minh JWS đó qua decoder thông thường.

Sơ đồ khái niệm:

~~~mermaid
flowchart LR
    A["Client: Bearer JWE"] --> B["Gateway / JWE service"]
    B --> C["Decrypt + enforce alg/enc/key/typ"]
    C --> D["Validate nested JWS + issuer/audience"]
    D --> E["Internal token exchange / trusted handoff"]
    E --> F["Spring Resource Server"]
    F --> G["Endpoint policy"]
~~~

Đây là lựa chọn cần làm rõ **vùng tin cậy**: backend có thể bị gọi trực tiếp bỏ qua gateway không; gateway xóa header do client tự đặt chưa; kết nối nội bộ có TLS/mTLS hoặc xác thực dịch vụ không; token chuyển tiếp có đúng audience cho backend không. Không mặc định tin một header plain text kiểu `X-Authenticated-User` do bất kỳ client nào cũng có thể gửi.

### 7.3. Tùy chọn kiến trúc B: viết \`JwtDecoder\` tùy chỉnh

Spring Security hỗ trợ hợp đồng interface **`JwtDecoder`**. Nếu có yêu cầu rõ để API trực tiếp nhận JWE, một implementation tùy chỉnh có thể:

1. Nhận chuỗi Bearer token từ filter.
2. Nhận diện/parse **JWE compact** từ dữ liệu chưa đáng tin.
3. Chỉ cho phép tổ hợp `alg` và `enc` được hợp đồng phê duyệt.
4. Chọn khóa giải mã đúng, kiểm tra integrity và giải mã JWE.
5. Nếu hợp đồng định nghĩa nested JWS, xác minh JWS bên trong bằng **khóa của issuer tin cậy**.
6. Validate đầy đủ `iss`, `aud`, `exp`, `nbf`, token type, scope và các ràng buộc tương ứng.
7. Chỉ sau khi thành công mới trả về Spring `Jwt` hợp lệ cho pipeline Resource Server.

Hình dạng tích hợp với Spring có thể mô tả bằng **pseudocode** sau; đây là thiết kế các bước, không phải class có sẵn để copy vào production:

~~~java
// PSEUDOCODE: cần implementation decryption, signature verification
// và claim validation hoàn chỉnh theo hợp đồng JWE/JWS thực tế.
class ContractAwareJweJwtDecoder implements JwtDecoder {

    @Override
    public Jwt decode(String compactJwe) throws JwtException {
        var decrypted = decryptJweWithApprovedAlgorithmsAndKeys(compactJwe);
        var signedJws = requireNestedSignedJwt(decrypted);
        var validatedJwt = verifyJwsAndValidateClaims(signedJws);

        return validatedJwt;
    }
}
~~~

Các hàm `decryptJweWithApprovedAlgorithmsAndKeys`, `requireNestedSignedJwt` và `verifyJwsAndValidateClaims` chỉ là tên mô tả bước xử lý. Không nên lấp chúng bằng thao tác Base64URL hoặc parse JSON thủ công; cần thư viện JOSE thích hợp, chính sách khóa và thuật toán, xử lý lỗi/rotation và validation phù hợp.

Trong Spring Security, custom decoder được nối vào Resource Server:

~~~java
JwtDecoder customDecoder = /* decoder JWE hoàn chỉnh do ứng dụng cung cấp */;

http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.decoder(customDecoder))
);
~~~

Đoạn trên minh họa **điểm mở rộng**, không cung cấp implementation `customDecoder`. Khi có nhiều `SecurityFilterChain`, decoder phải được nối đúng chain nhận token. Nếu decoder chỉ nhận JWE, API không nên âm thầm chấp nhận cả unsigned JWT hoặc token theo profile khác.

### 7.4. JWE chưa chắc là nested JWS

Giải mã một JWE có thể cho ra một JSON claim set trực tiếp hoặc một JWT/JWS khác, tùy hợp đồng. Không được mặc định payload nào cũng là signed JWT, hoặc mặc định token JWE giải mã xong đã chứng minh issuer.

Với hệ thống yêu cầu xác thực một Authorization Server bên ngoài, **nested JWS bên trong JWE** là cách rõ ràng để tách **chứng minh nguồn ký** và **bảo mật nội dung**. Nếu chọn profile JWE khác, phải mô tả rõ bằng chứng xác thực bên phát hành, key ownership và threat model. Đặc biệt, mã hóa bằng public key của API chỉ đảm bảo rằng người giữ private key mới đọc được, **không chứng minh ai đã mã hóa**.

### 7.5. Không chuyển token sang client secret hay một dạng khác tùy tiện

Không nên “giải quyết” JWE bằng cách xuất private decryption key cho các Resource Server không đáng tin, đẩy private key lên JWKS công khai, bỏ qua chữ ký trong nested JWT hoặc thay thế token bằng một header do gateway không xác thực đặt ra.

Nếu nhà cung cấp hỗ trợ **OAuth 2.0 Token Introspection** cho opaque access token, đây là cơ chế khác với giải mã JWE. Introspection có thể phù hợp cho opaque token, nhưng không có quy tắc rằng mọi JWE đều introspect được; phụ thuộc Authorization Server và hợp đồng API.

## 8. Ví dụ: phân biệt lớp bảo vệ và dữ liệu có thể đọc

### 8.1. JWS access token

Header:

~~~json
{"alg":"RS256","typ":"JWT","kid":"sig-2026-a"}
~~~

Payload:

~~~json
{
  "iss":"https://id.example.test/realms/shop",
  "sub":"user-123",
  "aud":"orders-api",
  "scope":"orders.read",
  "exp":2000000000
}
~~~

Kẻ nắm token có thể đọc claim bằng Base64URL-decode, nhưng không thể thay `aud` từ `orders-api` thành `billing-api` mà vẫn giữ chữ ký RSA hợp lệ nếu không nắm private signing key.

Resource Server cần xác minh chữ ký và các claim; còn `scope` chỉ là một phần phân quyền. Khi đọc đơn hàng, ứng dụng vẫn có thể cần kiểm tra user/tenant sở hữu từng bản ghi.

### 8.2. JWE access token

Outer protected header:

~~~json
{
  "alg":"RSA-OAEP-256",
  "enc":"A256GCM",
  "cty":"JWT",
  "kid":"enc-2026-a"
}
~~~

Payload là ciphertext, nên không thể nhìn thấy `sub`, `aud` hoặc `scope` chỉ bằng Base64URL-decode. Bên nhận phải có private decryption key phù hợp để giải mã. Nếu sau giải mã có nested JWS, cần kiểm tra chữ ký JWS và các claim của token bên trong.

Đoạn header ở trên **chỉ minh họa metadata**, không phải một JWE hoàn chỉnh. Mọi giá trị cryptographic như IV, CEK, tag và chữ ký phải do thư viện đạt chuẩn tạo ra.

### 8.3. JWT với `alg: none`

Một token có thể có header:

~~~json
{"alg":"none","typ":"JWT"}
~~~

Đó không phải JWS có chữ ký mà Resource Server nên chấp nhận trong luồng access token ký bằng issuer. Dù một chuẩn biểu diễn JWT có mô tả JWT không bảo vệ, không được bật chấp nhận unsigned JWT chỉ vì payload chứa `sub`, `iss` và `scope` “có vẻ đúng”.

## 9. Ranh giới bảo mật phải được thiết kế rõ

### 9.1. Không tin khóa từ URL do token tự chỉ định

Các header JOSE có thể chứa metadata như `kid`, và trong một số profile có tham chiếu khóa. Đây là input bên ngoài. Resource Server phải dùng **issuer, key source và allowlist thuật toán được cấu hình**, không tùy tiện tải khóa từ `jku`/`x5u` hay địa chỉ không được phê duyệt để xác minh token.

Nếu không, attacker có thể cố đưa khóa của chính họ vào quá trình xác thực.

### 9.2. Validate issuer và audience sau xác minh mật mã

- **`iss`**: token do đúng Authorization Server phát hành.
- **`aud`**: token dành cho Resource Server hiện tại.
- **`exp`**, **`nbf`**: thời gian token được phép sử dụng.
- **`scope`** hoặc authority tương ứng: quyền API.
- **`typ`** và profile token: đảm bảo API không chấp nhận nhầm ID Token hoặc JWT thuộc mục đích khác.
- **`sub`**, tenant, resource ownership: áp dụng chính sách nghiệp vụ nếu cần.

Không dùng email/name trong claims để thay thế quyền truy cập. Một JWT có chữ ký hợp lệ nhưng `aud` không chứa Orders API vẫn phải bị từ chối khi API có yêu cầu audience tương ứng.

### 9.3. Phân tách khóa ký và khóa giải mã

Trong triển khai bất đối xứng:

- Authorization Server giữ **private signing key** để tạo JWS.
- Resource Server dùng **public verification key** để xác minh JWS.
- Đối với JWE mã hóa cho Resource Server, sender có thể dùng **public encryption key** của Resource Server.
- Resource Server giữ **private decryption key** tương ứng để mở JWE.

Có thể một tổ chức dùng nhiều khóa và thuật toán theo profile; nguyên tắc là khóa phải phục vụ đúng mục đích, quản lý vòng đời và quyền truy cập riêng. Không mặc định dùng cùng một khóa cho mọi tác vụ mật mã.

### 9.4. Key rotation và vận hành

Issuer thường thay signing key theo chu kỳ. Với JWS, JWKS có thể chứa nhiều public key trong giai đoạn chuyển tiếp; `kid` hỗ trợ chọn khóa đúng. Với JWE, việc chuyển đổi khóa giải mã cần bảo đảm những token chưa hết hạn vẫn có thể được giải mã theo chính sách.

Hệ thống nên kiểm soát:

- Khóa hoạt động, khóa cũ trong cửa sổ chuyển tiếp và khóa đã thu hồi.
- Khả năng cache/refresh JWKS theo thư viện và hạ tầng.
- Lỗi network đến issuer/JWKS và cách trả lời xác thực khi khóa không xác minh được.
- Không log chuỗi access token hay plaintext nhạy cảm sau giải mã.
- Giới hạn kích thước token, nested depth và thuật toán để giảm rủi ro tiêu tốn tài nguyên.
- Kiểm tra cấu hình crypto và secret/private key trong kho quản lý khóa phù hợp.

## 10. Tình huống xác định nguyên nhân lỗi

### 10.1. Nhìn token có năm phần và API trả 401

Nếu Resource Server chỉ có:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

và token thực tế là **JWE compact**, nguyên nhân có thể là decoder mặc định không hỗ trợ giải mã lớp JWE. Hãy xác nhận **định dạng/token contract** với issuer. Không cố đổi `jwsAlgorithm` hoặc header để “bật JWE”.

### 10.2. Token ba phần nhưng vẫn 401

Ba phần gợi ý JWS compact, nhưng cần xác minh:

1. Header `alg` có nằm trong thuật toán được phép?
2. Signature có khớp khóa tin cậy của issuer?
3. `iss` có đúng issuer cấu hình?
4. `exp`/`nbf` có phù hợp thời gian?
5. `aud` có dành cho API không?
6. Có nhầm **ID Token** của OIDC client với **access token** dành cho Resource Server không?

Không chẩn đoán một token bằng cách in nguyên giá trị vào log hay đẩy nó đến website của bên thứ ba. Có thể dùng thông tin không nhạy cảm hoặc môi trường test với token giả lập để xác định dạng và cấu hình.

### 10.3. JWE giải mã thành công nhưng vẫn không thể cấp quyền

Giải mã chỉ cung cấp plaintext. Nếu payload là JWS, phải kiểm tra chữ ký JWS, issuer, audience và quyền. Nếu payload chỉ là JSON claims, cần xem hợp đồng có cơ chế nào chứng minh người phát hành và ràng buộc token vào issuer/API. Nếu không có bằng chứng tin cậy phù hợp, không nên tạo Authentication cho request.

### 10.4. Khóa có trong JWKS nhưng JWE không giải mã được

JWKS mà Resource Server nhận được có thể chỉ là **public signing keys**. Để giải mã JWE thường cần **private decryption key** hoặc symmetric key thích hợp, đồng thời phải hỗ trợ `alg` và `enc` thực sự của token. `kid` trùng tên một khóa không đủ để chứng minh khóa có mục đích giải mã.

### 10.5. Nên mã hóa mọi access token để tăng bảo mật?

Không phải lúc nào cũng cần. JWS có thể phù hợp với API xác thực quyền truy cập qua HTTPS; giảm claim không cần thiết và bảo vệ token khỏi log/leak. JWE bổ sung bí mật nội dung token khi có nhu cầu cụ thể, nhưng tăng phức tạp về khóa giải mã, luồng nested token, rotation và xử lý lỗi. Chọn theo threat model, không theo số lượng lớp mật mã.

## 11. Tóm lược bằng quyết định triển khai

| Nhu cầu | Hướng thiết kế thường phù hợp |
|---|---|
| API xác thực token do issuer ký | JWT **JWS** và `NimbusJwtDecoder` của Spring Security |
| API chỉ cho phép token từ issuer và đúng audience | JWS signature validation + `iss`/`aud`/thời hạn + authorization |
| Cần giấu claims trước bên trung gian không tin cậy | Cân nhắc **JWE** theo hợp đồng đã thiết kế |
| Cần cả mã hóa lẫn chứng minh issuer ký | **Nested JWS trong JWE**, giải mã rồi xác minh chữ ký/claim |
| Issuer cấp opaque access token | Dùng Resource Server **opaque token introspection** nếu issuer hỗ trợ |
| Token 5 phần nhưng Resource Server chỉ cấu hình JWT issuer URI | Cần xác nhận và xử lý **JWE** riêng; decoder JWT mặc định không đủ |
| Khóa public từ `jwks_uri` | Thường dùng **xác minh JWS**, không giải mã JWE bằng private key |

**Điểm phân biệt quan trọng nhất:** **JWS ký để kiểm tra toàn vẹn và nguồn ký khi khóa được tin cậy; JWE mã hóa để che nội dung và kiểm tra tính toàn vẹn của bản mã.** Đối với Spring Security OAuth 2.0 Resource Server, cấu hình `oauth2ResourceServer().jwt()` với `NimbusJwtDecoder` là đường đi thông thường cho **signed JWS access token**. **Encrypted JWE và nested JWT cần thiết kế giải mã, kiểm tra nguồn và validation bổ sung**, không tự được xử lý nhờ dependency Nimbus hay cấu hình issuer/JWKS đơn thuần.

### Tài liệu chuẩn để tra cứu

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)

