# Danh sách thuật toán được phép và ghép đúng loại khóa khi xác minh JWT

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, xác minh một JWT access token không chỉ là tìm được public key rồi gọi hàm kiểm tra chữ ký. Resource Server cần bảo đảm **thuật toán JWS được cho phép theo chính sách**, **khóa dùng để xác minh có loại và đặc tính phù hợp với thuật toán**, và **khóa đó đến từ issuer đáng tin**.

Một quy tắc nền tảng của [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725) là ứng dụng phải giới hạn tập thuật toán được chấp nhận và không cho header `alg` của token tự quyết định vượt qua chính sách bảo mật. Với từng khóa, ứng dụng còn phải ràng buộc nó với thuật toán thích hợp. Vì vậy:

> **Token khai báo `alg` nào chỉ là dữ liệu đầu vào để đối chiếu. Resource Server quyết định `alg` nào được phép, dùng khóa nào được tin và liệu phép xác minh bằng đúng thuật toán đó có thành công hay không.**

Bài học tập trung vào thuật toán của **JWS (JSON Web Signature)** khi Resource Server xác minh JWT đã ký. Không nên nhầm trường `alg` của JWS với thuật toán mã hóa `enc` của JWE.

## 1. Từ JWT đến lựa chọn thuật toán và khóa

Một JWT access token dạng JWS compact thường gồm ba phần:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
~~~

Ví dụ header sau khi giải mã Base64URL:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-01",
  "typ": "at+jwt"
}
~~~

Payload có thể chứa:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "alice",
  "aud": ["orders-api"],
  "exp": 2000000000,
  "scope": "orders.read"
}
~~~

Các giá trị này chưa đáng tin chỉ vì đọc được JSON. Trước khi sử dụng claim, Resource Server phải xử lý quy trình:

~~~text
                       JWT từ HTTP request
                                |
                                v
                    Parse JWS compact structure
                                |
                                v
              Đọc alg, kid (chỉ là untrusted hints)
                                |
                                v
              alg thuộc ALLOWLIST được cấu hình?
                     /                         \
                   Không                        Có
                    |                           |
                    v                           v
                  Reject                 Chọn khóa trong
                                         TRUSTED key source
                                                |
                                                v
                                Key type/curve/use/alg phù hợp?
                                         /               \
                                       Không              Có
                                        |                 |
                                        v                 v
                                      Reject         Verify signature
                                                          |
                                            +-------------+-------------+
                                            |                           |
                                          Fail                        Pass
                                            |                           |
                                            v                           v
                                          Reject             Validate iss/aud/exp/nbf
                                                                        |
                                                                        v
                                                          Map scope -> authorities
                                                                        |
                                                                        v
                                                              Authorize request
~~~

**Không được thay đổi thứ tự tin cậy** bằng cách đọc `scope=admin` từ payload chưa xác minh rồi cấp quyền. Và **chữ ký hợp lệ chưa tự bảo đảm đủ quyền**: phải tiếp tục kiểm tra issuer, audience, thời hạn, loại token và điều kiện truy cập tài nguyên.

## 2. “Danh sách thuật toán được phép” là gì?

**Algorithm allowlist** là tập hợp các thuật toán xác minh mà Resource Server đã chấp thuận theo hợp đồng với Authorization Server (AS) và chính sách bảo mật ứng dụng.

Ví dụ, một hệ thống chỉ phát hành JWT bằng RSA RS256 có thể đặt:

~~~text
Allowed JWS algorithms = { RS256 }
~~~

Nếu AS đang chuyển đổi có kiểm soát từ RS256 sang PS256, ứng dụng có thể tạm thời cho phép:

~~~text
Allowed JWS algorithms = { RS256, PS256 }
~~~

Tập trên phải được **quản trị bằng cấu hình tin cậy**, không được xây dựng từ `alg` trong request, claim `iss` chưa kiểm tra hoặc một URL do client cung cấp.

### Ba điều kiện cần đồng thời đúng

| Điều kiện | Ý nghĩa | Ví dụ từ chối |
|---|---|---|
| **Thuật toán được phép** | `alg` là một phần tử của allowlist đã phê duyệt | Chỉ cho RS256 nhưng token khai báo HS256 |
| **Khóa phù hợp** | Loại khóa, kích thước/curve, mục đích và binding tương thích với `alg` | Dùng RSA public key để kiểm tra HMAC HS256 |
| **Chữ ký/MAC hợp lệ** | Phép kiểm tra mật mã trên nội dung JWS thực sự thành công | Payload bị sửa nhưng signature không được ký lại |

Sau ba điều kiện này mới đánh giá claim và quyền.

**Lưu ý về RFC 8725:** Với mỗi khóa, hệ thống phải kiểm soát thuật toán được dùng cùng khóa đó, không tự tái sử dụng key tùy ý cho mọi thuật toán trong cùng family. Dù một RSA key về mặt toán học có thể được dùng bởi nhiều scheme, việc có chấp nhận `RS256`, `RS512` hay `PS256` là quyết định chính sách cụ thể theo key và issuer.

## 3. Các họ thuật toán JWS thường gặp

Các định danh thuật toán sau đến từ JOSE/JWA. Khả năng hỗ trợ runtime còn phụ thuộc version thư viện, JCA provider, loại khóa và cấu hình Spring Security; bảng này **không có nghĩa phải cho phép tất cả**.

| JWS `alg` | Cơ chế | Khóa dùng ở AS | Khóa dùng ở Resource Server | Lưu ý |
|---|---|---|---|---|
| `HS256` | HMAC-SHA-256 | Shared secret | **Cùng shared secret** | Bên verify cũng có khả năng tạo MAC |
| `HS384` | HMAC-SHA-384 | Shared secret | Cùng shared secret | Secret cần đủ entropy và độ dài |
| `HS512` | HMAC-SHA-512 | Shared secret | Cùng shared secret | Không ghép với RSA/EC public key |
| `RS256` | RSA PKCS#1 v1.5 + SHA-256 | RSA private key | RSA public key | Cấu hình mặc định thường gặp |
| `RS384` | RSA PKCS#1 v1.5 + SHA-384 | RSA private key | RSA public key | Phải được allowlist rõ |
| `RS512` | RSA PKCS#1 v1.5 + SHA-512 | RSA private key | RSA public key | Không có nghĩa đổi sang RSA key khác loại |
| `PS256` | RSA-PSS + SHA-256 | RSA private key | RSA public key | Padding scheme khác RS256 |
| `PS384` | RSA-PSS + SHA-384 | RSA private key | RSA public key | PSS parameters phải đúng |
| `PS512` | RSA-PSS + SHA-512 | RSA private key | RSA public key | Cần decoder hỗ trợ |
| `ES256` | ECDSA + SHA-256 | EC private key trên P-256 | EC public key trên P-256 | Curve là một phần của kiểm tra phù hợp |
| `ES384` | ECDSA + SHA-384 | EC private key trên P-384 | EC public key trên P-384 | Không tráo curve |
| `ES512` | ECDSA + SHA-512 | EC private key trên P-521 | EC public key trên P-521 | Tên ES512 **không có nghĩa** P-512 |
| `EdDSA` | EdDSA (theo JOSE profile hỗ trợ) | Ed25519/Ed448 private key | Public key tương ứng | Cần kiểm tra phiên bản Nimbus/Spring/JCA provider |
| `none` | Không có chữ ký/MAC | Không có | Không có | **Từ chối** trong API đòi signed JWT |

Tên `RS256` và `PS256` đều dùng RSA key, nhưng khác scheme ký. `ES256` dùng **EC public key** với curve tương ứng; không thể thay bằng RSA key hoặc một EC key bất kỳ.

Các thuật toán mạnh nên lựa chọn theo chính sách doanh nghiệp, khuyến nghị mật mã hiện hành, hỗ trợ AS và support cụ thể của thư viện. Không cố “hỗ trợ nhiều hơn cho chắc” bằng cách cho phép mọi thuật toán.

## 4. Khóa công khai và khóa bí mật khác nhau thế nào?

### 4.1. RSA / RSA-PSS

Với `RS256` hoặc `PS256`:

~~~text
Authorization Server                      Resource Server
        |                                        |
   RSA private key                          RSA public key
        |                                        |
        +-- sign JWT --> client --> JWT -------->+-- verify
~~~

Resource Server chỉ cần RSA public key để xác minh. Private signing key được bảo vệ tại AS hoặc hệ thống ký như HSM/KMS.

Cấu trúc public key trong JWKS thường có:

~~~json
{
  "kty": "RSA",
  "kid": "rsa-key-1",
  "use": "sig",
  "alg": "RS256",
  "n": "<base64url-modulus>",
  "e": "AQAB"
}
~~~

Các giá trị `n`/`e` trên chỉ minh họa. Đối với production, còn cần chính sách kích thước RSA key đủ mạnh, vòng đời key và nguồn phân phối đáng tin. Một RSA public key của issuer A không được tùy tiện dùng để xác minh token của issuer B.

### 4.2. ECDSA

Với `ES256`:

~~~text
Authorization Server                      Resource Server
        |                                        |
EC private key (P-256)                  EC public key (P-256)
        |                                        |
        +-- sign JWT --> client --> JWT -------->+-- verify
~~~

JWK EC có thể có:

~~~json
{
  "kty": "EC",
  "kid": "ec-key-1",
  "use": "sig",
  "alg": "ES256",
  "crv": "P-256",
  "x": "<base64url-x-coordinate>",
  "y": "<base64url-y-coordinate>"
}
~~~

Cần kiểm tra chính xác **curve** theo thuật toán. `ES256` tương ứng P-256, `ES384` tương ứng P-384 và `ES512` tương ứng P-521. Không chấp nhận một curve không mong muốn chỉ vì `kty=EC`.

Spring Security dùng NimbusJwtDecoder với JWK Set có thể xử lý các thuật toán ký bất đối xứng được hỗ trợ theo cấu hình. Nhưng `NimbusJwtDecoder.withPublicKey(...)` trong API thông dụng nhận **`RSAPublicKey`**; không nên cố truyền `ECPublicKey` vào RSA-specific builder. Với ECDSA, JWK Set hoặc cấu hình Nimbus `JWKSource` phù hợp thường là hướng thích hợp.

### 4.3. HMAC

Với `HS256`, cả AS lẫn RS cần cùng **shared secret**:

~~~text
Authorization Server                      Resource Server
        |                                        |
   Shared secret S                           Shared secret S
        |                                        |
        +-- MAC JWT --> client --> JWT ----------+-- verify MAC
~~~

Điểm khác với RSA: bên nào biết secret để **xác minh HMAC** về mặt kỹ thuật cũng có khả năng **tạo HMAC hợp lệ**. Nếu chia sẻ secret cho nhiều Resource Server, việc một RS bị chiếm quyền có thể làm ảnh hưởng cả các dịch vụ cùng tin secret đó.

Theo RFC 7518, secret cho `HS256` cần ít nhất 256 bit entropy/độ dài phù hợp; `HS384` và `HS512` đòi secret có độ mạnh tương ứng. Không dùng mật khẩu dễ đoán hoặc chuỗi ngắn như `"secret"` chỉ vì API chấp nhận `SecretKey`.

JWK HMAC (khi dùng trong hệ thống nội bộ có quyền truy cập hạn chế) có thể chứa:

~~~json
{
  "kty": "oct",
  "kid": "hmac-key-1",
  "alg": "HS256",
  "k": "<base64url-secret-key-material>"
}
~~~

**Không công bố JWK có `kty=oct` và `k` chứa secret ra JWKS công khai.** JWKS thường được Resource Server tải để xác minh chữ ký bất đối xứng chỉ nên công bố **public keys**. Nếu secret được lộ, attacker có thể tạo token với MAC hợp lệ.

### 4.4. EdDSA và các thuật toán mới

JOSE còn có thuật toán `EdDSA` dùng khóa dạng OKP như Ed25519/Ed448 theo profile thích hợp. Tuy nhiên không mặc định mọi version Spring Security, Nimbus, Java Cryptography provider hay IdP đều hỗ trợ đầy đủ.

Trước khi bật thuật toán mới, cần xác nhận **version của thư viện**, **JCA provider**, **kiểu JWK**, **key curve**, **policy issuer** và **validation behavior**. Một token “được ký bởi thuật toán hiện đại” không phải lý do để tắt allowlist.

## 5. Bản đồ ghép `alg`, `kty` và `crv`

| Header `alg` | JWK `kty` mong đợi | `crv` / điều kiện nổi bật | Bên xác minh cần |
|---|---|---|---|
| `RS256`, `RS384`, `RS512` | `RSA` | RSA modulus/exponent hợp lệ, độ dài key đạt policy | RSA public key |
| `PS256`, `PS384`, `PS512` | `RSA` | RSA-PSS scheme và key size phù hợp | RSA public key |
| `ES256` | `EC` | `crv=P-256` | EC P-256 public key |
| `ES384` | `EC` | `crv=P-384` | EC P-384 public key |
| `ES512` | `EC` | `crv=P-521` | EC P-521 public key |
| `HS256`, `HS384`, `HS512` | `oct` | Shared secret đủ mạnh, được bảo vệ | Secret key |
| `EdDSA` | `OKP` | Curve/primitive được thư viện hỗ trợ | EdDSA public key |
| `none` | Không áp dụng | Không được chấp nhận cho signed JWT | Từ chối |

**Các trường hợp sai cần từ chối:**

- Token khai báo `HS256` nhưng ứng dụng chỉ có RSA public key để verify.
- Token khai báo `ES256`, JWKS chỉ có RSA key.
- Token khai báo `ES256` nhưng khóa EC dùng P-384.
- Token khai báo `RS256` nhưng ứng dụng chỉ cho phép `PS256`.
- Token khai báo `none` dù API yêu cầu JWT có chữ ký.
- Token dùng RSA key của một issuer khác, dù thuật toán và kiểu khóa trông hợp lệ.

Tương thích **kiểu khóa** là điều kiện cần, không đủ. Key còn phải đến từ nguồn tin cậy, được AS chỉ định dùng cho mục đích signature và không vi phạm binding `kid`/`alg` hoặc chính sách ứng dụng.

## 6. Ba lớp kiểm soát: algorithm policy, key source, claims policy

Để triển khai đúng, hãy định nghĩa riêng ba câu hỏi:

1. **Algorithm policy:** Resource Server cho phép những giá trị `alg` nào?
2. **Key source and binding:** Khóa tương ứng được tải từ nguồn tin cậy nào, với loại khóa và ràng buộc thuật toán nào?
3. **Claims policy:** Sau khi xác minh chữ ký, những giá trị `iss`, `aud`, `exp`, `nbf`, token type và scope nào hợp lệ?

Ví dụ API `orders-api`:

~~~text
Issuer          = https://idp.example.com/realms/shop
JWK Set URI     = https://idp.example.com/realms/shop/protocol/openid-connect/certs
Allowed algs    = { RS256 }
Audience        = orders-api
Required scope  = orders.read (với GET /api/orders)
~~~

Một token mang `alg=RS256`, chữ ký đúng nhưng `aud=billing-api` **vẫn phải bị từ chối**. Một token có `aud=orders-api` và `scope=orders.read` nhưng `alg=HS256` trong khi RS chỉ tin `RS256` **cũng phải bị từ chối**.

Lỗi nguy hiểm thường xảy ra khi developer kiểm tra một trong ba lớp rồi xem như đủ:

~~~java
// SAI: chỉ đọc payload của token, không kiểm tra chữ ký
String role = parseBase64UrlPayload(jwt).get("role");
if ("ADMIN".equals(role)) {
    allowAdminOperation();
}
~~~

Một bên không được ủy quyền có thể tự tạo payload chứa `role=ADMIN` và Base64URL encode. Cơ chế xác thực chuẩn phải kiểm tra chữ ký và policy trước khi tạo principal đã xác thực.

## 7. Algorithm confusion: vì sao phải ghép đúng loại khóa?

**Algorithm confusion** là lớp lỗi trong đó cùng một giá trị key bị sử dụng hoặc diễn giải theo thuật toán khác với mục đích dự kiến, dựa vào `alg` do attacker kiểm soát.

### 7.1. Ví dụ kinh điển: RSA và HMAC bị nhầm lẫn

Giả sử hệ thống thiết kế để nhận JWT `RS256`:

~~~text
AS dùng RSA private key để ký.
RS dùng RSA public key để verify.
~~~

Một implementation sai có thể cho client chọn `alg=HS256` rồi dùng **chính bytes của RSA public key** làm secret của HMAC. Public key vốn công khai. Khi đó attacker có thể tạo một HMAC với secret mà họ cũng biết.

~~~text
Mô hình đúng:
  alg = RS256
  key = RSA PUBLIC KEY (verify only)
  chỉ có AS sở hữu RSA private key để ký

Mô hình lỗi:
  alg = HS256 do token chọn
  key = bytes của RSA public key làm HMAC secret
  public key vốn không bí mật -> nguy cơ giả MAC
~~~

Đây là lý do **không cho token tự quyết định thuật toán** và **không bao giờ sử dụng RSA public key làm HMAC secret**. Các thư viện hiện đại như Nimbus thực hiện phân biệt loại khóa, nhưng chính sách ứng dụng vẫn phải hạn chế thuật toán để tránh cấu hình sai, fallback không an toàn hoặc custom processor nguy hiểm.

### 7.2. `alg=none`

Trong JOSE có giá trị `none` để biểu diễn JWS không có bảo vệ chữ ký/MAC. Nó không phù hợp với API đòi signed access token.

Nếu một bộ xử lý parse token rồi thấy `alg=none` và vẫn tin claim `sub`/`scope`, attacker có thể tự tạo token không cần ký. Resource Server phải từ chối thay vì tự động “chấp nhận vì không cần xác minh”.

### 7.3. Tự động chọn thuật toán theo token header

Mẫu pseudocode sai:

~~~java
// SAI: token header không được quyết định policy
String algorithm = parseHeaderWithoutVerification(token).get("alg");
Verifier verifier = createVerifierFromAnyAlgorithm(algorithm, someKey);
return verifier.verify(token);
~~~

Cách đúng về mặt ý tưởng:

~~~java
// ĐÂY LÀ PSEUDOCODE: thư viện JOSE thật thực hiện các bước này
Set<String> allowed = Set.of("RS256");
String advertisedAlg = readUntrustedHeader(token).alg();

if (!allowed.contains(advertisedAlg)) {
    rejectToken();
}

TrustedKey key = resolveFromTrustedIssuerJwks(token);
if (!key.matchesPolicy(advertisedAlg)) {
    rejectToken();
}

verifyJwsSignatureOrReject(token, key);
validateIssuerAudienceTimeOrReject(token);
~~~

Không viết lại logic cryptographic verification bằng tay. Dùng Spring Security `JwtDecoder`, Nimbus và policy cấu hình được review.

## 8. Spring Security mặc định cho phép thuật toán nào?

Theo tài liệu Spring Security Resource Server JWT, `NimbusJwtDecoder` ở đường cấu hình mặc định **tin `RS256`** để xác minh JWT có chữ ký. Khi Authorization Server dùng `RS512`, `PS256`, `ES256` hoặc thuật toán khác được hỗ trợ, cần cấu hình allowlist thích hợp. Không mặc định bật mọi thuật toán chỉ vì Nimbus biết cách xử lý chúng.

Với ứng dụng Spring Boot dùng Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Một filter chain tối thiểu:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Filter chain bảo vệ API, còn `JwtDecoder` chịu trách nhiệm xác minh token. Các đoạn YAML ở phần tiếp theo cung cấp nguồn khóa và algorithm policy. Vấn đề CSRF/cookie, CORS, session và method security cần cấu hình thêm theo kiến trúc ứng dụng, không được giải quyết chỉ bằng allowlist thuật toán.

## 9. Cho phép một thuật toán bằng Spring Boot properties

Giả sử AS phát hành JWT bằng `RS512` và công bố public key qua JWKS:

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          jwk-set-uri: https://idp.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
          jws-algorithms:
            - RS512
~~~

Cấu hình này nêu rõ:

- **Issuer** mà Resource Server tin.
- **Nguồn JWKS** để chọn RSA public key phù hợp.
- **Audience** mà JWT phải chứa.
- **JWS algorithm** được cho phép là `RS512`.

Nếu AS vẫn phát hành `RS256` nhưng cấu hình chỉ cho `RS512`, token `RS256` phải bị từ chối, dù chữ ký của nó có thể hợp lệ theo `RS256`.

Khi issuer có discovery metadata chuẩn, có thể lược `jwk-set-uri` và chỉ dùng `issuer-uri` để Spring Security tìm JWKS theo cách được hỗ trợ. Khi sử dụng `jwk-set-uri` riêng mà thiếu `issuer-uri`, cần chủ động bổ sung issuer validation nếu API yêu cầu issuer cố định.

**Chú ý phiên bản:** `jws-algorithms` và `audiences` là những property được Spring Boot hiện đại hỗ trợ. Nếu dự án dùng phiên bản khác hoặc tự tạo `JwtDecoder` bean, phải kiểm tra thuộc tính có thực sự áp dụng vào decoder đang chạy không.

### Cho phép nhiều thuật toán khi có kế hoạch chuyển đổi

Ví dụ AS đang chuyển từ `RS256` sang `PS256`, chỉ trong giai đoạn được phê duyệt:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          jwk-set-uri: https://idp.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
          jws-algorithms:
            - RS256
            - PS256
~~~

Điều này chỉ có ý nghĩa nếu decoder và JWK Set thực tế hỗ trợ hai algorithm, keys tương ứng đã được công bố và mỗi key có binding hợp lệ. **Không mở rộng allowlist vô thời hạn** sau khi chuyển đổi xong. Đưa việc thêm/xóa algorithm vào thay đổi cấu hình có kiểm soát, giống thay đổi trusted issuer.

## 10. Dùng `NimbusJwtDecoder` builder để giới hạn thuật toán

Khi ứng dụng cần custom decoder hoặc validator phức tạp, có thể dùng `NimbusJwtDecoder`.

### 10.1. `withJwkSetUri(...)` và `jwsAlgorithm(...)`

Ví dụ chỉ chấp nhận `RS256` từ một JWKS tin cậy:

~~~java
package com.example.orders.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class StrictRsaDecoderConfig {

    private static final String ISSUER =
        "https://idp.example.com/realms/shop";
    private static final String JWKS =
        "https://idp.example.com/realms/shop/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audience =
            new JwtClaimValidator<List<String>>(
                "aud",
                values -> values != null && values.contains("orders-api"));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audience));

        return decoder;
    }
}
~~~

Ví dụ này thể hiện rõ ba lớp:

1. `withJwkSetUri(JWKS)`: nguồn khóa được tin.
2. `jwsAlgorithm(RS256)`: thuật toán được phép.
3. `setJwtValidator(...)`: issuer, thời gian và audience validation.

**Không dùng `NimbusJwtDecoder.withJwkSetUri(...).build()` rồi cho rằng decoder tự biết expected issuer và audience.** Với custom bean, phải tự cấu hình validators. Spring Boot thường back off khỏi auto-config decoder khi ứng dụng đã cung cấp bean `JwtDecoder`; YAML có thể không tự thêm các validators/algorithm policy vào custom bean.

### 10.2. Builder nhiều thuật toán

Tài liệu Spring Security cho phép dùng `jwsAlgorithm(...)` nhiều lần:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(jwksUri)
    .jwsAlgorithm(SignatureAlgorithm.RS256)
    .jwsAlgorithm(SignatureAlgorithm.PS256)
    .build();
~~~

Có thể dùng `jwsAlgorithms(...)` với tập thuật toán được quản lý. Tuy nhiên cần nhớ **mở rộng allowlist là một quyết định bảo mật**, không phải thao tác tương thích mặc định. Nếu chỉ ký RS256, hãy giữ RS256.

Trong thực tế mỗi key phải có binding algorithm thích hợp; không vì cả hai thuật toán đều dùng RSA mà tự bật cả hai cho mọi khóa.

### 10.3. Lấy thuật toán từ JWKS có phải luôn an toàn?

Nimbus/Spring Security có những khả năng phát hiện danh sách thuật toán từ JWK Set trong một số phiên bản/cách cấu hình. Điều này hữu ích khi AS kiểm soát đầy đủ JWKS và hợp đồng đã được phê duyệt.

Tuy nhiên **JWKS trusted source và algorithm policy không nhất thiết đồng nghĩa**. Một JWKS có nhiều key loại RSA/EC không có nghĩa API chấp nhận mọi thuật toán mà key ấy có thể sử dụng. Nếu chính sách bảo mật yêu cầu `RS256` duy nhất, cấu hình allowlist tường minh. Khi dùng cơ chế lấy algorithm từ JWKS, phải bảo đảm nguồn JWKS, key metadata và phạm vi thuật toán được tin phù hợp với chính sách.

Không cho token tự quyết định nơi tải key bằng `jku`/`x5u` hoặc tự thêm algorithm vào allowlist.

## 11. Dùng RSA public key cố định

Đối với hệ thống chỉ có một RSA public key được quản lý, Spring Security hỗ trợ builder:

~~~java
import java.security.interfaces.RSAPublicKey;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

// rsaPublicKey là khóa công khai được nạp từ nguồn tin cậy
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withPublicKey(rsaPublicKey)
    .signatureAlgorithm(SignatureAlgorithm.RS256)
    .build();
~~~

Chữ ký trong ví dụ chỉ được kiểm tra theo RSA/RS256 với khóa đưa vào. Cần tiếp tục gắn issuer, audience và time validators phù hợp, tương tự đoạn code `StrictRsaDecoderConfig` trước.

Đặc biệt lưu ý: **`PublicKeyJwtDecoderBuilder.signatureAlgorithm(...)` của Spring Security sử dụng RSA key và hỗ trợ những lựa chọn RS256/RS384/RS512 được tài liệu API mô tả**. Nếu cần RSA-PSS/EC hoặc nhiều key, lựa chọn thiết kế có thể là JWK Set, `JWKSource` tin cậy hoặc Nimbus configuration phù hợp, thay vì ép một builder chỉ dành cho RSA public key vào mọi loại thuật toán.

Với Spring Boot, có thể cung cấp public key bằng property:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          public-key-location: classpath:keys/as-public.pem
~~~

File PEM minh họa:

~~~text
-----BEGIN PUBLIC KEY-----
<base64-encoded-rsa-public-key>
-----END PUBLIC KEY-----
~~~

Resource Server chỉ nên nạp public key, không giữ private signing key của AS. Với một public key cố định, cần có quy trình cập nhật key khi AS rotation; việc thay file trên đĩa không mặc định khiến `JwtDecoder` nạp lại.

## 12. Trường hợp HMAC: `withSecretKey(...)` khác `withPublicKey(...)`

Nếu AS và Resource Server có hợp đồng bắt buộc `HS256`, decoder sẽ cần **shared SecretKey**, không phải RSA public key.

Ví dụ có tính minh họa về API Spring Security:

~~~java
import javax.crypto.SecretKey;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

// hmacSecretKey lấy từ secret manager / nguồn tin cậy.
// Không hardcode secret vào source code.
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withSecretKey(hmacSecretKey)
    .macAlgorithm(MacAlgorithm.HS256)
    .build();
~~~

Một lần nữa, phải áp dụng issuer/audience/time validators phù hợp. Đoạn này chỉ thể hiện builder HMAC, không phải toàn bộ cấu hình Resource Server.

Không dùng ví dụ thiếu an toàn:

~~~java
// SAI: secret ngắn, dễ đoán
SecretKey secretKey =
    new SecretKeySpec("secret".getBytes(UTF_8), "HmacSHA256");
~~~

Với HS256 cần dùng secret sinh ngẫu nhiên đủ mạnh và độ dài tối thiểu theo chuẩn, cấp phát qua kho bí mật và tránh log. Đối với nhiều Resource Server, cân nhắc giải pháp ký bất đối xứng vì mỗi RS có secret HMAC đồng nghĩa mỗi RS nắm khả năng tạo MAC theo cùng key.

**Không bao giờ dùng bytes của RSA public key như `SecretKey` để xác minh HS256**. Một public key vốn được công bố rộng rãi không thể trở thành shared secret bí mật của HMAC.

## 13. JWK metadata: `kty`, `use`, `key_ops`, `alg` và `kid`

JWK có thể chứa metadata hỗ trợ chọn khóa. Ví dụ một RSA key trong JWK Set:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "rsa-sig-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

| Trường | Ý nghĩa | Cách ứng dụng nên xử lý |
|---|---|---|
| `kty` | Loại khóa, như `RSA`, `EC`, `oct`, `OKP` | Phải phù hợp họ thuật toán |
| `kid` | Gợi ý định danh khóa | Chỉ chọn trong trusted key source |
| `use` | Mục đích dùng khóa, như `sig` hoặc `enc` | Không dùng khóa mã hóa vào mục đích signature nếu policy cấm |
| `key_ops` | Danh sách thao tác được phép như `verify`, `sign` | Không trái với ý định sử dụng khóa |
| `alg` | Thuật toán mà JWK khai báo dự định sử dụng | Đối chiếu với allowlist và binding của key |
| `crv` | Curve trong EC/OKP | Phải tương thích thuật toán được yêu cầu |
| `n`, `e` | RSA public parameters | Chỉ dùng material hợp lệ từ nguồn tin cậy |
| `x`, `y` | EC public point coordinates | Phải nằm trên curve phù hợp và được thư viện xác thực |

**Metadata chỉ có ý nghĩa khi JWK Set đến từ nguồn tin cậy.** Tuy nhiên, ngay cả JWKS tin cậy cũng phải được quản lý như cấu hình bảo mật: nếu JWKS URI trỏ nhầm môi trường hoặc cho phép bên không được phê duyệt sửa nội dung, API có thể tin sai khóa.

### `kid` là gợi ý, không phải chứng nhận

JWT header có thể chứa:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-sig-2026-01"
}
~~~

Resource Server chỉ dùng `kid` để chọn khóa **trong tập khóa đã được cấu hình đáng tin**. Không tự tải bất kỳ URL nào từ token header `jku` hoặc `x5u`, vì có thể bị lợi dụng để SSRF hoặc đưa khóa do attacker kiểm soát vào đường xác minh.

Nếu `kid` trùng lặp hoặc không khớp key trong trusted JWKS, cần xử lý theo chính sách selector và từ chối khi không xác minh được, không fallback sang “bất kỳ key nào ký được” ngoài trust policy.

### `key_ops` và `use` có thể không có

JWK không bắt buộc luôn có mọi metadata. Việc thiếu `use` hoặc `alg` không tự biến key thành an toàn hoặc không an toàn trong mọi ngữ cảnh. Application và library phải kết hợp các trường thực tế có mặt với **chính sách bên ngoài**: issuer, danh sách thuật toán, loại key và mục đích token.

Nếu JWK nêu `alg=RS256` nhưng JWT header yêu cầu `HS256`, hệ thống không được diễn giải RSA key thành HMAC secret. Tương tự, `use=enc` không nên tự được dùng cho `sig`.

## 14. Phân biệt `alg` của JWS và `alg`/`enc` của JWE

Một nhầm lẫn khác là coi mọi giá trị `alg` của JOSE như thuật toán ký. Với **JWS**, `alg` thường chỉ thuật toán signature/MAC:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt"
}
~~~

Với **JWE**, header có thể chứa:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "cty": "JWT"
}
~~~

Ở JWE:

- `alg` là thuật toán quản lý/trao đổi khóa dùng cho mã hóa.
- `enc` là thuật toán mã hóa nội dung.
- JWT có thể được nested (JWE chứa JWS) và cần xử lý nhiều bước nếu contract yêu cầu.

**Không đưa `RSA-OAEP-256` hay `A256GCM` vào allowlist JWS signatures**. Và đừng nhầm “giải mã nội dung JWE thành công” với “token được chấp nhận”: issuer, audience, thời gian, token type và phân quyền vẫn phải được kiểm tra.

Một access token không phải JWS ba phần, chẳng hạn opaque token hoặc JWE, không nên bị ép qua đường xử lý `oauth2ResourceServer().jwt()` nếu hệ thống chưa hỗ trợ đúng cấu trúc và cơ chế xác minh của nó.

## 15. Khi nào thay đổi allowlist?

Những tình huống hợp lý:

### 15.1. Authorization Server đổi từ RS256 sang PS256

Đây là một thay đổi có chủ đích về padding scheme của RSA signature. Kế hoạch tối thiểu:

1. Xác nhận AS thực sự phát hành `PS256` và Resource Server/Nimbus đang dùng hỗ trợ.
2. Công bố public keys tương ứng qua JWKS tin cậy.
3. Thêm `PS256` vào allowlist với ranh giới key/issuer rõ ràng.
4. Theo dõi request bị từ chối do thuật toán/key mismatch.
5. Khi các JWT RS256 cũ hết hạn và AS ngừng phát hành, thu hẹp allowlist theo chính sách.

Đừng chuyển `RS256` sang `PS256` bằng cách thay header token. Chữ ký phải do AS tạo đúng scheme.

### 15.2. AS đổi RSA sang ECDSA

Nếu AS dự định dùng `ES256`:

- JWKS phải công bố EC public key `kty=EC` và `crv=P-256`.
- Allowlist phải chấp nhận `ES256` theo hợp đồng.
- Decoder/JCA provider phải hỗ trợ xác minh ECDSA đúng định dạng JOSE.
- Không cố xác minh ES256 bằng RSA public key cũ.

Trong giai đoạn chuyển đổi, JWKS có thể công bố cả RSA và EC keys với `kid` riêng. Phải biết key nào gắn với alg nào, issuer/audience vẫn giữ policy phù hợp.

### 15.3. Đổi kích thước digest trong cùng family RSA

`RS256`, `RS384` và `RS512` đều sử dụng RSA signature dạng PKCS#1 v1.5 nhưng khác hash. Điều này không có nghĩa mỗi giá trị được tự động chấp nhận. Chỉ thêm thuật toán khi có yêu cầu và có kế hoạch vận hành; xem xét kích thước RSA key, khuyến nghị mật mã và tương thích thư viện.

## 16. Chẩn đoán lỗi thuật toán và khóa

Khi request nhận `401 Unauthorized` dù JWT có thể Base64URL decode, các khả năng sau đáng xem xét:

| Dấu hiệu | Nguyên nhân có thể | Hướng xác minh |
|---|---|---|
| JWT header `alg=HS256`, RS cấu hình chỉ RS256 | Algorithm bị từ chối bởi allowlist | Kiểm tra thuật toán AS thực sự dùng |
| JWT header `alg=ES256`, JWKS chỉ có `kty=RSA` | Không có key đúng loại/curve | Xác nhận JWKS và key type |
| JWT header `alg=RS256`, decoder chỉ tin PS256 | Sai algorithm policy | Đồng bộ AS và RS allowlist |
| JWT header `alg=none` | Không có chữ ký theo contract signed token | Từ chối token |
| `kid` mới chưa có trong JWKS cache | AS key rotation, key fetch chưa cập nhật | Kiểm tra JWKS mới và cache |
| `kid` có nhưng không verify được | Key sai issuer, public key sai, signature bị sửa | Kiểm tra trust source và ký thực tế |
| `HS256` token dùng secret quá ngắn/khác secret | HMAC key mismatch hoặc policy từ chối | Secret manager, key rotation, key length |
| `ES256` token dùng EC key P-384 | Curve mismatch | `crv`, cấu hình signer và decoder |
| JWKS URI trỏ staging trong production | Chọn sai key source | Cấu hình deployment, issuer, môi trường |
| Token đúng signature nhưng `aud` khác | JWT claim validation từ chối | Audience validator |
| Token đúng signature nhưng `exp` đã qua | JWT time validation từ chối | Đồng bộ thời gian, claim validator |
| Token hợp lệ nhưng thiếu `SCOPE_orders.write` | Authorization failure | Authority mapping, endpoint rule |

Đọc được `alg` và `kid` chỉ giúp **đặt giả thuyết**. Kết luận phải dựa vào decoder thực hiện xác minh thật bằng khóa đã tin và validator cấu hình đúng.

### Phân biệt mã lỗi

- **401** thường gặp khi token thiếu, không hợp lệ hoặc không vượt qua bước xác thực JWT.
- **403** thường gặp khi token đã xác thực nhưng thiếu authority hoặc quyền đối với tài nguyên.
- Lỗi JWKS/metadata hoặc key management có thể tạo exception khác tùy phiên bản và error handler. Không mặc định mọi lỗi mạng đều được ánh xạ thành 401.

Không tự động **fail open** bằng cách chấp nhận token khi không có key phù hợp hoặc không verify được signature.

## 17. Đọc log và điều tra an toàn

Bearer token là credential. Một bên có được access token còn hiệu lực có thể dùng nó theo quyền token cho phép. Vì vậy:

- Không ghi nguyên token hoặc `Authorization` header vào log.
- Không dán access token thật vào công cụ web JWT decoder, issue, chat hay ticket.
- Khi cần chẩn đoán, ghi mã lỗi như `algorithm_not_allowed`, `key_not_found`, `invalid_signature` hoặc `invalid_audience` nếu policy cho phép.
- Có thể ghi identifier của trusted issuer/JWKS configuration, request ID/trace ID và endpoint, nhưng tránh ghi PII hay secret.
- Không trả chi tiết nội bộ về loại key/thuật toán cho client nếu điều đó làm lộ thông tin không cần thiết.
- Thực hiện điều tra với test token ngắn hạn, scope hẹp, trong môi trường được kiểm soát.

Log minh họa:

~~~text
event=jwt_authentication_failed
path=/api/orders
reason=algorithm_not_allowed
configuredAlgorithms=[RS256]
traceId=4cf7...
bearerToken=[REDACTED]
~~~

Không dùng các đường “debug only” bỏ xác minh chữ ký cho production, kể cả khi endpoint đã có IP allowlist; lỗi xác minh cần được xử lý từ nguồn gốc.

## 18. Một ví dụ kiến trúc hoàn chỉnh

Giả sử hệ thống shop có:

- Issuer: `https://idp.example.com/realms/shop`.
- Resource Server: `orders-api`.
- JWT access token được ký bằng RSA `RS256`.
- JWKS công bố các public keys của issuer.
- API `GET /api/orders` đòi `SCOPE_orders.read`.

Cấu hình `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          jwk-set-uri: https://idp.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
          jws-algorithms:
            - RS256
~~~

Cùng `SecurityConfig`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Request thử nghiệm:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.com/api/orders
~~~

Các trường hợp dự kiến:

| JWT | Dự kiến | Giải thích |
|---|---|---|
| `RS256`, RSA key đúng issuer, signature hợp lệ, `aud=orders-api`, scope đọc | Cho phép GET | Mọi điều kiện chính đều đạt |
| `HS256` dù payload `aud=orders-api` | Từ chối | Không thuộc allowlist |
| `ES256` dù `kid` tồn tại cho RSA key | Từ chối | Algorithm/key type không khớp |
| `RS256`, đúng RSA key nhưng payload bị sửa | Từ chối | Signature không hợp lệ |
| `RS256`, signature hợp lệ nhưng `aud=billing-api` | Từ chối | Audience sai |
| `RS256`, chữ ký và audience hợp lệ nhưng thiếu scope đọc | Thường 403 | Authentication thành công, authorization thất bại |
| `RS256`, signature hợp lệ nhưng token đã hết hạn | Từ chối | Time validator thất bại |

Khi thay đổi thuật toán, cập nhật **AS signing configuration**, **JWKS/key source**, **RS allowlist** và **validator policy** theo một kế hoạch thống nhất. Không sửa mỗi `alg` trong header token.

## 19. Một số hiểu nhầm thường gặp

**“JWT header nói `alg=RS256` nên token chắc chắn được ký bằng RS256.”** Không đúng. Đó là khai báo chưa tin; Resource Server phải verify bằng đúng thuật toán được phép và khóa phù hợp.

**“Thư viện hiểu HS256 và RS256 thì cứ bật cả hai.”** Sai. Mở rộng allowlist làm tăng bề mặt cấu hình sai, đặc biệt trong các hệ thống từng có lỗi algorithm confusion.

**“RSA public key có thể dùng làm HMAC secret.”** Không. Public key là dữ liệu công khai; HMAC secret phải được giữ bí mật.

**“RS256 và PS256 giống nhau vì đều dùng RSA.”** Không. Chúng khác signature scheme/padding và phải được chọn rõ.

**“ES256 chỉ cần EC key bất kỳ.”** Không. Nó cần đường ký/xác minh ECDSA phù hợp với P-256.

**“`kid` trùng nghĩa là signature hợp lệ.”** Không. `kid` chỉ giúp chọn key; signature vẫn phải được verify.

**“`jwk-set-uri` cho biết issuer và audience hợp lệ.”** Không. JWKS là nguồn khóa; issuer và audience là những claim policies riêng.

**“`withPublicKey(...)` có thể dùng cho ECDSA và HMAC như nhau.”** Không. Builder thông dụng của `NimbusJwtDecoder` nhận RSA public key. HMAC có `withSecretKey(...)`, ECDSA thường dùng JWKS/JWKSource thích hợp.

**“Chữ ký hợp lệ rồi thì không cần `iss`, `aud` hay `exp`.”** Sai. Signature verification và claims validation đều cần thiết.

**“Key rotation chỉ cần đổi `kid`.”** Không. AS phải cung cấp material mới đáng tin, ký bằng key tương ứng và bảo đảm RS cập nhật key source đúng thời điểm.

## 20. Bài tập suy luận

### Câu 1: JWT có `alg=HS256` nhưng API chỉ dùng RSA

API chỉ tin `RS256` và có RSA public key từ JWKS. Một JWT mới khai báo `HS256` nhưng claim `sub`/`aud` nhìn chính xác. Có được chấp nhận?

> Không. `HS256` không có trong allowlist và không được xác minh bằng RSA public key. Chỉ đọc payload không tạo độ tin cậy.

### Câu 2: JWKS chứa EC P-384, JWT khai báo ES256

Có thể kiểm tra ES256 bằng EC key P-384 không?

> Không. ES256 tương ứng P-256. Với EC, curve phải khớp thuật toán, ngoài yêu cầu đúng issuer và signature.

### Câu 3: AS chuyển từ RS256 sang PS256

Cần làm gì ngoài đổi `jws-algorithms`?

> Bảo đảm AS thực sự ký PS256, key/selector và Nimbus/Spring hỗ trợ scheme này, JWKS công bố key thích hợp, có kế hoạch rollout/rotation và không duy trì allowlist rộng quá cần thiết.

### Câu 4: Đã tự khai báo `JwtDecoder` custom

Ứng dụng có `jws-algorithms: [RS256]` trong YAML nhưng custom decoder lại chấp nhận thuật toán khác. Vì sao?

> Bean custom thường làm Boot auto-configuration back off; property có thể không được áp dụng lên decoder custom. Phải cấu hình allowlist trực tiếp trong builder/processor và giữ issuer/audience/time validators.

### Câu 5: JWT chữ ký hợp lệ, issuer đúng nhưng bị 403

Có phải do algorithm mismatch?

> Thường không. Khi authentication đã thành công, 403 thường thuộc authorization: thiếu scope/authority hoặc chính sách tài nguyên không cho phép. Cần tách lỗi xác minh và lỗi quyền.

### Câu 6: Vì sao không nên công bố shared HMAC secret qua JWKS?

> Nếu shared secret bị công bố, bất cứ ai có secret cũng có thể tạo HMAC hợp lệ. Public JWKS cho asymmetric algorithms chỉ nên công bố public-key material; HMAC secret phải được bảo vệ.

## 21. Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): cấu hình trusted algorithms, issuer/JWK Set và JWT decoder.
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): factory/builders cho JWKS, RSA public key, SecretKey và validator.
- [Spring Security — NimbusJwtDecoder PublicKeyJwtDecoderBuilder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.PublicKeyJwtDecoderBuilder.html): cấu hình RSA public key và signature algorithm.
- [Spring Security — NimbusJwtDecoder SecretKeyJwtDecoderBuilder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.SecretKeyJwtDecoderBuilder.html): `macAlgorithm` và HMAC key.
- [Spring Security — NimbusJwtDecoder JwkSetUriJwtDecoderBuilder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.JwkSetUriJwtDecoderBuilder.html): `jwsAlgorithm`, `jwsAlgorithms`, key source và cache.
- [Spring Boot — OAuth2 Resource Server](https://docs.spring.io/spring-boot/reference/security/oauth2.html): các property liên quan JWT Resource Server.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS format và quy tắc signature.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): các trường `kty`, `kid`, `use`, `key_ops` và public key representation.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): HS, RS, PS, ES và đặc điểm thuật toán/khóa.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và claims.
- [RFC 8037 — CFRG Elliptic Curve Algorithms for JOSE](https://www.rfc-editor.org/rfc/rfc8037): khóa OKP và EdDSA.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm verification, key/algorithm binding, trusted keys và chống JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile và chính sách xác minh JWT access token.

Khi thiết kế JWT Resource Server, **`alg` trong token không phải quyết định bảo mật**. Quyết định nằm trong **allowlist do hệ thống quản lý**, **khóa đúng loại từ issuer tin cậy**, và **bộ validators kiểm tra token dành cho API này**. Chỉ sau các bước đó mới được dùng scope và claim để phân quyền.
