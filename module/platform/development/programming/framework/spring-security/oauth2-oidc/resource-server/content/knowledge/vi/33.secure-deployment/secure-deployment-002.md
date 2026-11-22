# Danh sách issuer, audience, thuật toán và nguồn khóa được tin cậy

## 1. Trust boundary của Resource Server

Spring Security OAuth 2.0 Resource Server chỉ nên chấp nhận access token được phát hành bởi một Authorization Server đã được cấu hình tin cậy, dành cho đúng API và được ký bằng khóa cùng thuật toán nằm trong policy của hệ thống.

Một JWT có chữ ký hợp lệ vẫn có thể không phù hợp với API hiện tại. Token có thể được ký bởi issuer hợp lệ nhưng dành cho billing-api; có thể có audience đúng nhưng issuer không nằm trong danh sách tin cậy; hoặc có cả issuer và audience đúng nhưng dùng thuật toán mà hệ thống không cho phép. Vì vậy, xác minh chữ ký chỉ là một phần của quyết định xác thực.

Bốn danh sách cần quản lý rõ ràng:

- **Issuer allowlist:** những Authorization Server được phép phát hành token cho hệ thống.
- **Audience allowlist:** những resource identifier được phép nhận token trên API này.
- **Algorithm allowlist:** những thuật toán chữ ký được chấp nhận để xác minh access token.
- **Trusted key sources:** những endpoint hoặc kho khóa được phép cung cấp public key để xác minh chữ ký.

Các danh sách này tạo thành trust policy. Chúng phải được cấu hình từ nguồn quản trị tin cậy, được review và thay đổi theo quy trình. Không để token tự chọn issuer, audience, thuật toán hoặc URL tải khóa rồi biến các giá trị đó thành trust anchor.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của issuer và audience trong access-token validation.
2. Xây dựng allowlist issuer/audience rõ ràng cho Resource Server.
3. Giới hạn thuật toán chữ ký theo policy.
4. Chọn JWKS URI và metadata endpoint từ nguồn cấu hình tin cậy.
5. Phân biệt public signing keys của Authorization Server với JWK do Client gửi trong DPoP proof.
6. Quản lý key rotation, unknown kid và cache refresh.
7. Xử lý nhiều issuer mà không tạo cơ chế discovery tùy ý từ token.
8. Kiểm tra opaque token introspection theo trust boundary tương ứng.
9. Viết negative tests cho issuer, audience, algorithm và key source.
10. Theo dõi thay đổi trust policy mà không làm lộ credential hoặc private key.

---

## 2. Issuer: xác định ai được phép phát hành token

### 2.1. Claim iss là định danh của Authorization Server

JWT access token thường có claim iss:

~~~json
{
  "iss": "https://id.example.com/realms/shop",
  "sub": "user-417",
  "aud": ["orders-api"],
  "exp": 1893456000
}
~~~

Resource Server phải xác minh giá trị iss khớp issuer đã cấu hình. So sánh phải theo giá trị issuer chính xác mà Authorization Server công bố và ký trong token.

Ví dụ, các giá trị sau không nên được coi là tương đương nếu policy chỉ khai báo một issuer:

~~~text
https://id.example.com/realms/shop
https://id.example.com/realms/shop/
http://id.example.com/realms/shop
https://id.example.com/other-realm
~~~

Không tự bỏ slash, đổi scheme, đổi host hoặc chuẩn hóa path theo heuristic để làm token “khớp”. Nếu Authorization Server thay đổi issuer URI, đó là thay đổi trust configuration cần được triển khai có chủ đích.

### 2.2. Issuer không phải subject

Issuer trả lời “ai phát hành token?”. Subject trả lời “token nói về ai?”.

- iss thường định danh Authorization Server.
- sub thường định danh user, service account hoặc principal.
- aud định danh resource server hoặc nhóm resource nhận token.

Không dùng sub để quyết định token được phát hành bởi hệ thống nào. Cũng không dùng một user ID có vẻ quen thuộc để bỏ qua issuer validation.

### 2.3. Cấu hình một issuer tin cậy

Với Spring Boot, cấu hình issuer URI thường là lựa chọn đơn giản:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/shop
~~~

Spring Security sử dụng issuer để tìm metadata/JWK endpoint theo cơ chế discovery được hỗ trợ, tạo decoder và xác minh issuer cùng các điều kiện thời gian mặc định.

Cấu hình issuer URI không có nghĩa Resource Server chấp nhận mọi issuer. Đây là một issuer cụ thể được ứng dụng khai báo.

Nếu ứng dụng cần kiểm soát rõ JWKS endpoint, có thể cấu hình trực tiếp endpoint khóa. Khi dùng JWK Set URI trực tiếp, vẫn phải cấu hình issuer validator; biết URL JWKS không tự chứng minh token có issuer hợp lệ.

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/shop
          jwk-set-uri: https://id.example.com/realms/shop/protocol/openid-connect/certs
~~~

Trong một số cấu hình, khai báo cả hai cho phép ứng dụng biết issuer mong đợi và endpoint JWK Set cụ thể. Hãy kiểm tra hành vi của Spring Boot/Spring Security version đang dùng và xác nhận decoder thực sự có issuer validator.

### 2.4. Khi nào cần custom JwtDecoder?

Có thể cần custom decoder khi ứng dụng phải:

- Bắt buộc audience riêng cho API.
- Chỉ cho phép một tập thuật toán cụ thể.
- Dùng JWKS endpoint được quản trị riêng.
- Kết hợp validator mặc định với policy bổ sung.
- Áp dụng clock skew theo yêu cầu vận hành.
- Dùng nhiều decoder cho nhiều issuer.

Khi tự khai báo bean JwtDecoder, hãy tự chịu trách nhiệm cấu hình đầy đủ các validator. Đừng giả định mọi property Spring Boot trước đó vẫn được tự động áp dụng lên bean tùy chỉnh.

---

## 3. Audience: token phải dành cho đúng API

### 3.1. Vì sao chỉ xác minh issuer là chưa đủ?

Một Authorization Server có thể phát hành token cho nhiều resource:

~~~text
Issuer:
  https://id.example.com/realms/shop

Token A:
  aud = orders-api

Token B:
  aud = billing-api

Token C:
  aud = inventory-api
~~~

Cả ba token có thể được ký bởi cùng issuer. Nhưng Orders API chỉ nên chấp nhận token có audience bao gồm orders-api.

Nếu chỉ kiểm tra issuer và chữ ký, một token dành cho Billing API có thể bị dùng nhầm tại Orders API. Đây là lỗi phân tách resource và có thể tạo token substitution giữa các API.

### 3.2. Audience có thể là một string hoặc danh sách

Trong JWT, aud có thể được biểu diễn thành một giá trị hoặc một mảng. API của Spring Security trả audience dưới dạng danh sách để ứng dụng kiểm tra.

Ví dụ:

~~~json
{
  "aud": "orders-api"
}
~~~

Hoặc:

~~~json
{
  "aud": ["orders-api", "mobile-client"]
}
~~~

Nếu API yêu cầu orders-api, token thứ hai có thể hợp lệ vì audience chứa resource identifier đó. Chính sách cụ thể tùy kiến trúc; điều quan trọng là so sánh với identifier chính xác mà API đã chọn.

Không dùng substring matching, wildcard hoặc kiểm tra “aud không rỗng” thay cho allowlist.

### 3.3. Viết audience validator

Ví dụ validator cho Orders API:

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

static OAuth2TokenValidator<Jwt> audienceValidator(
        String requiredAudience) {

    return jwt -> {
        if (jwt.getAudience().contains(requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Required audience is missing",
            null
        );

        return OAuth2TokenValidatorResult.failure(error);
    };
}
~~~

Validator chỉ chấp nhận token có đúng resource identifier. Khi audience không khớp, decoder từ chối token trước khi tạo Authentication.

### 3.4. Kết hợp issuer, audience và thời gian

~~~java
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;

static OAuth2TokenValidator<Jwt> accessTokenValidator(
        String issuer,
        String audience) {

    OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(issuer);

    return new DelegatingOAuth2TokenValidator<>(
        defaults,
        audienceValidator(audience)
    );
}
~~~

Validator mặc định với issuer kiểm tra issuer và các điều kiện timestamp mặc định của Spring Security. Validator audience bổ sung điều kiện resource.

Với access token, còn cần xác nhận token profile/purpose phù hợp với API. Nếu Authorization Server phát hành cả ID token và access token dưới dạng JWT, không nên chỉ dựa vào việc cả hai đều có chữ ký hợp lệ. Cấu hình issuer, audience và token profile phải phân biệt token dùng cho API với token dùng cho OIDC client authentication.

### 3.5. Không dùng client_id thay cho audience

client_id xác định OAuth client đã yêu cầu token. Audience xác định resource nhận token. Chúng có vai trò khác nhau.

Ví dụ:

~~~text
client_id = shop-mobile
aud       = orders-api
scope     = orders.read
~~~

Client shop-mobile có thể gọi Orders API với scope orders.read. API nên kiểm tra audience của chính nó và scope cần thiết. Việc client_id đúng không có nghĩa token được phát hành cho resource này.

---

## 4. Thuật toán chữ ký: allowlist phải được cấu hình rõ

### 4.1. Header alg là dữ liệu chưa tin cậy

Một JWT có JOSE header:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-01",
  "typ": "JWT"
}
~~~

Giá trị alg được gửi cùng token. Trước khi chữ ký được xác minh, header này là input không tin cậy. Resource Server không được đọc alg rồi chấp nhận bất kỳ thuật toán nào mà token yêu cầu.

Một số lỗi phổ biến:

- Chấp nhận thuật toán none.
- Cho phép cả symmetric và asymmetric algorithm mà không có policy.
- Dùng cùng một key theo hai cách khác nhau và tạo algorithm confusion.
- Không giới hạn thuật toán trong decoder.
- Coi thuật toán được ghi trong JWK là đủ để xác định policy.
- Cho phép token dùng thuật toán yếu hơn chỉ vì thư viện hỗ trợ.

### 4.2. Dùng asymmetric signature cho Resource Server phân tán

Với chữ ký bất đối xứng:

- Authorization Server giữ private signing key.
- Resource Server chỉ cần public verification key.
- Lộ public key không cho phép tạo chữ ký mới.
- Nhiều Resource Server có thể xác minh token mà không chia sẻ private signing key.

Các nhóm thuật toán thường gặp:

| Nhóm | Ví dụ | Đặc điểm |
|---|---|---|
| RSA PKCS#1 v1.5 | RS256, RS384, RS512 | Phổ biến, tương thích rộng |
| RSA-PSS | PS256, PS384, PS512 | Padding hiện đại hơn, cần kiểm tra tương thích |
| ECDSA | ES256, ES384, ES512 | Chữ ký dựa trên elliptic curve |
| HMAC | HS256, HS384, HS512 | Dùng shared secret; verifier cũng giữ bí mật ký |

Với mô hình nhiều Resource Server, asymmetric signature thường thuận lợi hơn vì mỗi Resource Server chỉ cần public key. Nếu dùng HMAC, mọi thành phần có secret xác minh đều có khả năng tạo token hợp lệ. Hãy đánh giá rủi ro chia sẻ secret trước khi chọn.

### 4.3. Cấu hình một thuật toán được phép

Ví dụ dùng RS256:

~~~java
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder jwtDecoder() {
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(
            "https://id.example.com/realms/shop/protocol/openid-connect/certs"
        )
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .build();

    decoder.setJwtValidator(
        accessTokenValidator(
            "https://id.example.com/realms/shop",
            "orders-api"
        )
    );

    return decoder;
}
~~~

Decoder chỉ chấp nhận thuật toán đã khai báo. Validator issuer/audience tiếp tục kiểm tra nội dung token sau khi chữ ký được xác minh.

Đây là ví dụ minh họa cho một issuer và một audience. Hãy đồng bộ thuật toán với signing configuration của Authorization Server. Nếu AS rotate key nhưng vẫn giữ thuật toán, Resource Server có thể nhận key mới từ cùng JWKS endpoint mà không cần nới allowlist.

### 4.4. Khi cần nhiều thuật toán

Chỉ cho phép nhiều thuật toán khi có lý do tương thích hoặc migration rõ ràng. Ví dụ trong giai đoạn chuyển đổi, AS có thể ký bằng RS256 hoặc ES256:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(JWKS_URI)
            .jwsAlgorithms(algorithms -> {
                algorithms.add(SignatureAlgorithm.RS256);
                algorithms.add(SignatureAlgorithm.ES256);
            })
            .build();

    decoder.setJwtValidator(
        accessTokenValidator(ISSUER, AUDIENCE)
    );

    return decoder;
}
~~~

Danh sách phải được khai báo rõ trong code/config. Không xây allowlist động từ giá trị alg do token gửi lên. Sau migration, loại bỏ thuật toán cũ theo kế hoạch và xác nhận không còn token hợp lệ phụ thuộc vào nó.

Nếu builder/version của Spring Security đang dùng không có đúng method trên, kiểm tra Javadoc của artifact đã resolve và dùng API tương ứng. Không đổi sang decoder mặc định không giới hạn chỉ để làm ví dụ biên dịch.

### 4.5. Thuật toán và loại key phải tương thích

Một thuật toán được cho phép vẫn cần key phù hợp:

- RS256 cần RSA public key phù hợp.
- ES256 cần EC key trên curve phù hợp.
- JWK có trường alg nếu được khai báo phải phù hợp với mục đích sử dụng.
- Key phải có mục đích verify/signing đúng theo metadata và policy.
- Key không được chứa private material ở nơi chỉ cần public verification key.

Không dùng một JWK bất kỳ chỉ vì nó có thể được parse. Kiểm tra thuật toán, key type, curve/key size, use và key operations theo policy của tổ chức và thư viện.

---

## 5. Trusted key source: lấy public key từ đâu?

### 5.1. JWKS URI là một trust decision

Resource Server thường lấy public keys từ một JWKS endpoint. Ví dụ:

~~~text
Issuer:
https://id.example.com/realms/shop

JWKS:
https://id.example.com/realms/shop/protocol/openid-connect/certs
~~~

Resource Server cần tin cậy cả hai mối liên hệ:

1. Issuer đã được cấu hình là Authorization Server được chấp nhận.
2. JWKS endpoint là nguồn khóa được phép đại diện cho issuer đó.

Không chọn JWKS endpoint bằng cách lấy một URL bất kỳ trong token. Nếu token chứa jku hoặc x5u, không tự động tải khóa từ URL đó để xác minh access token. Làm như vậy cho phép người gửi token ảnh hưởng nguồn public key mà server dùng để xác thực chính token đó.

### 5.2. Static JWKS URI và issuer discovery

Có hai cách cấu hình phổ biến.

**Issuer discovery:** ứng dụng cấu hình issuer URI, sau đó tìm metadata và jwks_uri theo giao thức discovery được hỗ trợ.

Ưu điểm:

- Cấu hình gọn.
- Metadata liên kết issuer với endpoint khóa.
- Dễ vận hành theo chuẩn OIDC/OAuth Authorization Server metadata.

Điểm cần kiểm soát:

- Metadata phải được lấy từ issuer tin cậy.
- HTTPS và chứng thư TLS phải được xác minh.
- Issuer trong metadata phải khớp issuer mong đợi.
- Không cho token tự đưa ra issuer mới để ứng dụng tự discovery tùy ý.

**Static JWKS URI:** ứng dụng cấu hình endpoint khóa trực tiếp.

Ưu điểm:

- Endpoint rõ ràng trong cấu hình triển khai.
- Có thể tách metadata discovery khỏi đường khởi tạo.
- Hữu ích khi môi trường có endpoint được quản trị riêng.

Điểm cần kiểm soát:

- Vẫn phải validate issuer trong token.
- JWKS URI phải thuộc trust configuration đã review.
- Cấu hình endpoint giữa môi trường dev/staging/prod phải được quản lý.
- Không để một biến môi trường không được kiểm soát ghi đè endpoint production.

### 5.3. HTTPS và TLS certificate validation

JWKS là nguồn public key. Nếu attacker có thể thay response JWKS trên đường truyền hoặc chiếm quyền DNS/endpoint, họ có thể đưa public key do mình kiểm soát và ký token giả.

Do đó:

- Dùng HTTPS cho metadata và JWKS endpoint.
- Giữ TLS certificate validation được bật.
- Quản lý trust store/certificate authority theo policy.
- Không tắt hostname verification trong production.
- Không chấp nhận mọi certificate chỉ để vượt lỗi môi trường.
- Bảo vệ DNS, ingress, service account và cấu hình endpoint.
- Theo dõi thay đổi certificate và endpoint.

Public key có thể công khai, nhưng tính xác thực của nguồn cung cấp public key là yếu tố bảo mật quan trọng.

### 5.4. Không lấy key từ token header

Với access token JWT, Resource Server không nên tin:

- jku URL do token cung cấp.
- x5u URL do token cung cấp.
- JWK nhúng tùy ý trong header.
- Certificate chain do người gửi token cung cấp mà không có trust validation riêng.
- kid được dùng như đường dẫn file hoặc tên endpoint.

kid chỉ là identifier giúp chọn key trong tập khóa đã tin cậy. Nó không phải URL, file path hay bằng chứng rằng key đó đáng tin.

### 5.5. Phân biệt access-token signing key và DPoP proof key

Đây là hai trust model khác nhau:

| Khóa | Ai kiểm soát | Resource Server dùng để làm gì |
|---|---|---|
| AS signing key | Authorization Server | Xác minh chữ ký access token |
| DPoP public key | Client | Xác minh DPoP proof và so thumbprint với cnf.jkt |

DPoP proof có public JWK do Client gửi trong proof header. Đây là thiết kế của DPoP: Resource Server xác minh proof bằng key đó rồi so sánh thumbprint với key binding trong access token đã được AS xác minh.

Không áp dụng quy tắc “không bao giờ dùng JWK từ request” cho DPoP proof một cách máy móc. Phải phân biệt public key được phép lấy từ DPoP proof theo RFC với key nguồn xác minh chữ ký access token. DPoP public key chỉ được chấp nhận sau khi proof signature, claims và cnf.jkt binding đều hợp lệ.

---

## 6. Key selection, kid và key rotation

### 6.1. kid giúp chọn key trong JWKS

JWKS có thể chứa nhiều khóa:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-key-2025",
      "use": "sig",
      "alg": "RS256",
      "n": "<RSA-MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "signing-key-2026",
      "use": "sig",
      "alg": "RS256",
      "n": "<RSA-MODULUS-NEW>",
      "e": "AQAB"
    }
  ]
}
~~~

kid trong JOSE header giúp decoder tìm key tương ứng. Tuy nhiên, kid không được dùng làm trust decision độc lập. Decoder cần chọn key trong JWKS đã tin cậy và xác minh chữ ký bằng key phù hợp.

### 6.2. Quy trình rotate key an toàn

Một quy trình rotation thường có các giai đoạn:

~~~text
Giai đoạn 1: Publish key mới
  JWKS chứa key cũ + key mới

Giai đoạn 2: Chờ Resource Server nhận key mới
  Cache refresh / warm-up / propagation

Giai đoạn 3: Bắt đầu ký bằng key mới
  Token mới có kid mới

Giai đoạn 4: Giữ key cũ trong overlap window
  Token cũ còn hiệu lực vẫn xác minh được

Giai đoạn 5: Hết overlap window
  Gỡ key cũ khỏi JWKS theo policy
~~~

Thời gian overlap phải tính đến:

- Thời hạn access token tối đa.
- Clock skew được cho phép.
- JWK cache lifetime/refresh behavior.
- Độ trễ propagation giữa các Resource Server.
- Request đang chạy và token được phát hành ngay trước khi đổi key.
- Quy trình khẩn cấp nếu key cũ bị compromise.

Không xóa key cũ ngay khi AS bắt đầu ký bằng key mới nếu vẫn còn token hợp lệ được ký bằng key cũ.

### 6.3. Unknown kid

Khi decoder nhận token có kid chưa xuất hiện trong cache, nó có thể refresh JWKS để tìm key. Nếu không tìm được key phù hợp, token phải bị từ chối.

Cần kiểm soát:

- Unknown kid có kích hoạt refresh hay không.
- Số lần refresh trong một khoảng thời gian.
- Hành vi khi JWKS endpoint timeout hoặc 5xx.
- Hành vi khi JWKS trả response không hợp lệ.
- Cache stampede khi nhiều request đồng thời dùng unknown kid.
- Log/metric cho unknown kid mà không log token.

Không tự động chấp nhận key nhúng trong token khi không tìm thấy kid. Điều đó biến failure của trusted key source thành cơ chế trust fallback không an toàn.

### 6.4. Key bị compromise

Nếu signing key bị lộ, quy trình khẩn cấp khác với rotation định kỳ:

1. Ngừng sử dụng private key bị compromise ở AS.
2. Loại bỏ hoặc đánh dấu key đó không còn được tin cậy theo khả năng của hạ tầng.
3. Xem xét invalidation/refresh cache trên Resource Server.
4. Xử lý token đã phát hành bằng key bị compromise.
5. Đánh giá thời gian access token còn hiệu lực và nguy cơ replay.
6. Theo dõi request dùng kid cũ.
7. Thông báo các service owner theo quy trình incident response.

Chỉ xóa key khỏi JWKS có thể chưa đủ tức thời nếu Resource Server còn cache public key. Cần hiểu cache behavior và có cách refresh/invalidate phù hợp với tình huống compromise.

---

## 7. Cấu hình Spring Security cho một issuer và audience

### 7.1. Cấu hình tối thiểu bằng issuer-uri

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/shop
~~~

Cấu hình này là nền tảng cho một issuer. Tuy nhiên, API vẫn cần audience validation nếu token được phát hành cho nhiều resource.

### 7.2. Tạo decoder với issuer, audience và algorithm allowlist

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
public class TrustedJwtConfig {

    private static final String ISSUER =
        "https://id.example.com/realms/shop";

    private static final String JWKS_URI =
        "https://id.example.com/realms/shop/protocol/openid-connect/certs";

    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(JWKS_URI)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token is not intended for orders-api",
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
~~~

Các thành phần:

- JWKS URI là endpoint khóa đã được cấu hình từ nguồn tin cậy.
- RS256 là thuật toán duy nhất trong allowlist ví dụ.
- JwtValidators.createDefaultWithIssuer kiểm tra issuer và timestamp mặc định.
- Audience validator đảm bảo token được phát hành cho Orders API.
- DelegatingOAuth2TokenValidator kết hợp các validator.

Nếu ứng dụng dùng Spring Boot, bean JwtDecoder tùy chỉnh này sẽ là decoder được inject vào Resource Server. Kiểm tra không có bean khác hoặc security chain khác vô tình sử dụng decoder với policy yếu hơn.

### 7.3. Gắn decoder vào Servlet Resource Server

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtDecoder jwtDecoder) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.decoder(jwtDecoder))
            )
            .build();
    }
}
~~~

Decoder xác minh trust policy của token. Authorization rules tiếp tục kiểm tra scope. Issuer/audience validation không thay thế authorization theo endpoint.

### 7.4. Cấu hình ReactiveJwtDecoder

Với WebFlux, nguyên tắc trust policy giống nhau nhưng decoder trả Mono:

~~~java
@Bean
ReactiveJwtDecoder reactiveJwtDecoder() {
    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withJwkSetUri(JWKS_URI)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(ISSUER);

    OAuth2TokenValidator<Jwt> audience =
        audienceValidator(AUDIENCE);

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuerAndTime,
            audience
        )
    );

    return decoder;
}
~~~

Cấu hình decoder vào WebFlux security chain:

~~~java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        ReactiveJwtDecoder reactiveJwtDecoder) {

    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.jwtDecoder(reactiveJwtDecoder))
        )
        .build();
}
~~~

Validator vẫn là API đồng bộ. ReactiveJwtDecoder gọi validator trong pipeline decode và phát lỗi qua Mono nếu validation thất bại. Không đưa blocking network lookup vào OAuth2TokenValidator.

---

## 8. Nhiều issuer: allowlist rõ ràng và decoder riêng

### 8.1. Khi nào cần nhiều issuer?

Một Resource Server có thể phục vụ nhiều tenant hoặc nhiều tổ chức, mỗi tổ chức có Authorization Server riêng. Khi đó token có thể đến từ nhiều issuer được chấp nhận.

Ví dụ:

~~~text
Trusted issuers:
  https://login.alpha.example
  https://login.beta.example

Resource:
  orders-api
~~~

Mỗi issuer có thể có:

- JWKS URI riêng.
- Signing keys riêng.
- Key rotation schedule riêng.
- Audience policy riêng.
- Claim mapping hoặc scope convention riêng.

Không nên dùng một decoder với một JWKS URI cho mọi issuer nếu trust model yêu cầu tách key source.

### 8.2. Chỉ resolve issuer từ danh sách được cấu hình

Spring Security cung cấp AuthenticationManagerResolver để chọn AuthenticationManager theo request. Với multi-issuer, dùng danh sách issuer tin cậy đã khai báo:

~~~java
@Bean
AuthenticationManagerResolver<HttpServletRequest>
authenticationManagerResolver() {

    return JwtIssuerAuthenticationManagerResolver
        .fromTrustedIssuers(
            "https://login.alpha.example",
            "https://login.beta.example"
        );
}
~~~

Đây là mẫu cho Servlet Resource Server. API factory và import cụ thể cần khớp Spring Security version đang dùng.

Điểm quan trọng là issuer được giới hạn trong danh sách tin cậy. Không tạo decoder bằng cách lấy bất kỳ iss nào trong token rồi tự discovery endpoint cho iss đó.

### 8.3. Mỗi issuer có audience policy riêng

Nếu Alpha cấp token cho orders-api nhưng Beta cấp token cho orders-service, hãy cấu hình audience tương ứng trong manager/decoder của từng issuer.

Không dùng một audience validator chung quá rộng chỉ để tái sử dụng code. Có thể tái sử dụng factory tạo decoder nhưng tham số issuer, JWKS URI, audience và algorithm allowlist phải là cấu hình đã được quản trị.

### 8.4. Tránh issuer confusion

Các tình huống cần từ chối:

- Issuer không có trong allowlist.
- Issuer có vẻ giống trusted issuer nhưng khác host/path.
- Issuer hợp lệ nhưng audience không dành cho API.
- Issuer Alpha token được xác minh bằng key của Beta.
- Một issuer được thêm động bởi dữ liệu user-controlled.
- Issuer discovery endpoint chuyển hướng tới host không được phép theo network policy.

Nếu hệ thống hỗ trợ tenant onboarding động, quá trình thêm issuer phải là workflow quản trị: xác minh domain/metadata, phê duyệt key source, xác định audience và lưu trust config. Không tự tin một issuer chỉ vì token chứa URL đó.

---

## 9. Opaque token: trust introspection endpoint và response

### 9.1. Không có JWT signature verification ở Resource Server

Với opaque token, Resource Server thường gửi token đến introspection endpoint đã cấu hình. Authorization Server trả thông tin như:

~~~json
{
  "active": true,
  "sub": "user-417",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "iss": "https://id.example.com/realms/shop"
}
~~~

Resource Server tin kết quả vì request được gửi tới introspection endpoint tin cậy qua kênh được bảo vệ và endpoint được xác thực đúng. Token không tự chọn URL introspection.

### 9.2. Cấu hình endpoint và client authentication

Ví dụ Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ORDERS_INTROSPECTION_SECRET_FROM_SECRET_MANAGER
~~~

Client ID/secret ở đây là credential của Resource Server để gọi introspection endpoint. Không commit secret vào source code hoặc file config được lưu trong repository. Placeholder trong ví dụ biểu diễn giá trị được inject từ secret manager hoặc environment của runtime.

Trong production:

- Dùng secret manager hoặc workload identity nếu AS hỗ trợ.
- Giới hạn quyền của introspection client.
- Dùng HTTPS và certificate validation.
- Không gửi token tới endpoint do Client chỉ định.
- Đặt timeout và connection pool.
- Xoay credential introspection theo quy trình.
- Scrub token và secret khỏi log.

### 9.3. Kiểm tra attributes trong introspection response

Nếu custom OpaqueTokenIntrospector hoặc ReactiveOpaqueTokenIntrospector, xác nhận:

- active là true.
- issuer đúng nếu response có issuer và policy yêu cầu.
- audience chứa resource identifier của API.
- scope đủ cho endpoint.
- subject/principal được map theo contract.
- token type/profile phù hợp.
- client/authorized party đúng khi policy yêu cầu.
- các claim custom không bị biến thành authority ngoài ý muốn.

Không coi HTTP 200 từ introspection endpoint là bằng chứng token active. HTTP 200 có thể chứa active=false. Cũng không coi response thiếu active là active mặc định.

### 9.4. Lỗi introspection endpoint

Nếu endpoint timeout, trả 5xx hoặc TLS validation thất bại, Resource Server không thể xác minh token. Không fail-open bằng cách tạo Authentication mặc định.

Cần phân biệt:

- Token inactive: Authorization Server xác nhận token không còn active.
- Introspection unavailable: không xác định được trạng thái token.
- Credential Resource Server sai: introspection client không được phép gọi endpoint.
- TLS/hostname failure: không thể xác minh endpoint là server tin cậy.

Các trường hợp đều không được tạo Authentication thành công. Error mapping có thể khác nhau, nhưng không được biến dependency failure thành token hợp lệ.

---

## 10. Token profile và mục đích sử dụng

### 10.1. ID token không phải access token

Trong OIDC, ID token mang thông tin về authentication event và được phát hành cho OIDC client. Access token được dùng để truy cập resource server.

Một ID token có thể có chữ ký hợp lệ và issuer đúng, nhưng vẫn không được chấp nhận như access token. Resource Server cần kiểm tra audience và token profile phù hợp với API.

Ví dụ:

~~~text
ID token:
  iss = https://id.example.com
  aud = shop-web-client

Access token:
  iss = https://id.example.com
  aud = orders-api
~~~

Nếu Orders API chấp nhận mọi JWT của issuer mà không kiểm tra audience/purpose, ID token có thể bị sử dụng nhầm ở API.

### 10.2. Kiểm tra token type/profile

Tùy Authorization Server và profile token, có thể dùng header typ hoặc claims được chuẩn hóa để phân biệt access token. Ví dụ JWT access token theo RFC 9068 sử dụng typ at+jwt.

Nếu áp dụng profile đó, cần kiểm tra typ và các claim bắt buộc theo profile. Không tự thêm một check typ tùy ý rồi cho rằng nó thay thế issuer, audience, signature, expiry và scope validation.

Một validator tùy chỉnh có thể kiểm tra typ sau khi decoder đã xác minh chữ ký:

~~~java
static OAuth2TokenValidator<Jwt> accessTokenTypeValidator() {
    return jwt -> {
        Object typ = jwt.getHeaders().get("typ");

        if ("at+jwt".equals(typ)) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Expected an access token JWT",
                null
            )
        );
    };
}
~~~

Chỉ bật validator này nếu Authorization Server thực sự phát hành token theo profile tương ứng. Nếu hệ thống dùng profile khác, cấu hình check đúng với hợp đồng token đã thống nhất.

---

## 11. Test trust policy: positive và negative cases

### 11.1. Test validator audience

~~~java
@Test
void acceptsExpectedAudience() {
    Jwt jwt = validJwtWithAudience("orders-api");

    OAuth2TokenValidatorResult result =
        audienceValidator("orders-api").validate(jwt);

    assertTrue(result.getErrors().isEmpty());
}

@Test
void rejectsDifferentAudience() {
    Jwt jwt = validJwtWithAudience("billing-api");

    OAuth2TokenValidatorResult result =
        audienceValidator("orders-api").validate(jwt);

    assertFalse(result.getErrors().isEmpty());
}
~~~

### 11.2. Test issuer

~~~java
@Test
void rejectsUntrustedIssuer() {
    Jwt jwt = validJwtWithIssuer(
        "https://attacker.example/issuer"
    );

    OAuth2TokenValidator<Jwt> validator =
        JwtValidators.createDefaultWithIssuer(
            "https://id.example.com/realms/shop"
        );

    assertTrue(validator.validate(jwt).hasErrors());
}
~~~

Test này kiểm tra issuer validator. Decoder integration test cần thêm compact JWT có chữ ký để xác nhận toàn bộ đường đi.

### 11.3. Test algorithm allowlist

Dùng token fixture được ký bằng thuật toán được phép và một fixture được ký bằng thuật toán không được phép.

| Fixture | Policy | Kết quả |
|---|---|---|
| RS256, key tin cậy | Chỉ RS256 | Chấp nhận nếu claims hợp lệ |
| ES256, key tin cậy | Chỉ RS256 | Từ chối |
| RS256, key không có trong trusted JWKS | Chỉ RS256 | Từ chối |
| none | Chỉ RS256 | Từ chối |
| HS256 khi policy chỉ asymmetric | Chỉ RS256 | Từ chối |
| RS256, sai audience | Chỉ RS256 | Từ chối |
| RS256, sai issuer | Chỉ RS256 | Từ chối |

Không chỉ sửa chuỗi alg trong header của một token đã ký để tạo test. Chữ ký sẽ không còn hợp lệ và test có thể thất bại ở signature verification thay vì đúng lý do algorithm allowlist. Hãy tạo fixture riêng để xác định rõ nhánh đang được test.

### 11.4. Test trusted key source

Các test nên bao gồm:

- JWKS endpoint hợp lệ trả public key đúng.
- JWKS endpoint TLS hostname mismatch.
- JWKS endpoint timeout.
- JWKS trả malformed JSON/JWK.
- kid không tồn tại.
- JWK key type không phù hợp với algorithm.
- Key rotation có overlap.
- Key cũ bị gỡ khi token cũ vẫn còn hiệu lực.
- JWKS URI bị thay đổi ngoài cấu hình được phê duyệt.

Dùng mock HTTP server hoặc test JWKS endpoint để kiểm soát response. Không gọi production Authorization Server trong test.

### 11.5. Test audience và issuer cùng nhau

Một token chỉ được chấp nhận khi mọi điều kiện đều đúng:

~~~text
issuer trusted
AND signature valid with trusted key
AND algorithm allowed
AND audience contains this API
AND exp/nbf valid
AND token profile acceptable
AND required authorization scope present
~~~

Trong đó scope thường được kiểm tra ở authorization layer sau Authentication. Vì vậy, test decoder và test authorization rule riêng biệt, rồi có integration test xác nhận chúng được nối đúng.

### 11.6. Test nhiều issuer

Với multi-issuer resolver, kiểm tra:

- Issuer Alpha dùng đúng decoder/key source Alpha.
- Issuer Beta dùng đúng decoder/key source Beta.
- Issuer không nằm trong allowlist bị từ chối.
- Token Alpha không được xác minh bằng key Beta.
- Audience policy của từng issuer được áp dụng.
- Thay đổi issuer allowlist cần deploy/config approval theo quy trình.

---

## 12. Logging, metrics và audit cho trust policy

### 12.1. Ghi nhận nguyên nhân từ chối ở mức an toàn

Có thể theo dõi các nhóm lỗi:

- untrusted_issuer
- invalid_audience
- unsupported_algorithm
- signature_invalid
- unknown_kid
- jwks_unavailable
- malformed_jwks
- token_expired
- token_not_yet_valid
- token_profile_invalid
- introspection_inactive
- introspection_unavailable

Dùng error code ổn định hoặc category đã chuẩn hóa. Không đưa raw JWT, access token, client secret, private key hoặc toàn bộ claim nhạy cảm vào log.

### 12.2. Metric cardinality

Metric tag nên có số lượng giá trị giới hạn:

~~~text
security.jwt.validation{outcome="success"}
security.jwt.validation{outcome="invalid_audience"}
security.jwt.validation{outcome="unknown_kid"}
security.jwks.fetch{outcome="error"}
~~~

Không dùng subject, email, token, request ID hoặc kid không giới hạn làm tag. Nếu cần điều tra key cụ thể, ghi sự kiện audit có kiểm soát thay vì tạo metric series cho từng giá trị động.

### 12.3. Audit thay đổi trust configuration

Thay đổi issuer, audience, JWKS URI, thuật toán và key trust phải có thể truy vết:

- Ai thay đổi?
- Thay đổi ở môi trường nào?
- Giá trị cũ và mới là gì?
- Lý do thay đổi?
- Ai review/phê duyệt?
- Thời điểm triển khai?
- Kế hoạch rollback?
- Key rotation có overlap và validation test chưa?

Không ghi private key hoặc secret vào audit. Với JWKS URI và issuer, ghi giá trị endpoint công khai có thể phù hợp, nhưng vẫn cần theo chính sách bảo mật của tổ chức.

---

## 13. Những sai lầm thường gặp

| Sai lầm | Rủi ro | Cách xử lý |
|---|---|---|
| Chỉ xác minh chữ ký | Token từ issuer khác hoặc API khác có thể lọt qua | Kiểm tra issuer và audience |
| Chấp nhận mọi issuer trong token | Attacker có thể điều khiển discovery/key source | Dùng issuer allowlist cấu hình sẵn |
| Chỉ kiểm tra iss | Token dành cho API khác vẫn có thể được chấp nhận | Kiểm tra audience cụ thể |
| Dùng client_id thay audience | Nhầm OAuth client với resource server | Kiểm tra aud theo API |
| Cho phép mọi alg thư viện hỗ trợ | Algorithm confusion và policy yếu | Explicit algorithm allowlist |
| Cho phép none | Không có chữ ký được xác minh | Từ chối none |
| Dùng HMAC secret ở mọi Resource Server | Mọi verifier có thể ký token | Ưu tiên asymmetric key nếu phù hợp |
| Tin jku/x5u trong token | Token tự chọn key source | Cấu hình JWKS URI tin cậy |
| Dùng kid như URL/file path | Key selection bị điều khiển | Chỉ dùng kid để lookup trong trusted JWKS |
| Bỏ issuer validator khi dùng JWKS URI | Key hợp lệ có thể được dùng cho token sai issuer | Gắn issuer validator |
| Dùng một audience chung cho mọi API | Token substitution giữa resource | Audience riêng theo API |
| Chấp nhận ID token ở Resource Server | Sai mục đích token | Kiểm tra access-token profile và audience |
| Xóa key cũ ngay khi rotate | Token cũ còn hiệu lực bị từ chối | Có overlap window |
| Giữ key compromise trong cache vô thời hạn | Token giả có thể tiếp tục được xác minh | Có incident procedure và cache invalidation |
| Unknown kid thì tin JWK nhúng | Fallback trust không an toàn | Chỉ dùng configured key source |
| TLS JWKS tắt certificate validation | Có thể bị thay nguồn khóa trên đường truyền | Giữ TLS validation |
| Introspection HTTP 200 được coi active | Token active=false vẫn có thể qua | Kiểm tra active=true |
| Introspection timeout được coi active | Fail-open | Không cấp Authentication khi không xác minh được |
| Metric tag chứa issuer động/token/user | Cardinality cao và rò rỉ dữ liệu | Dùng category có giới hạn |
| Multi-issuer tự discovery từ iss bất kỳ | SSRF hoặc trust expansion | Allowlist issuer và quản lý onboarding |

---

## 14. Quy trình triển khai trust policy

### Bước 1: Xác định resource identifier

Chọn audience chính thức cho API, ví dụ orders-api. Dùng cùng identifier trong Authorization Server, token issuance và Resource Server validation.

### Bước 2: Xác định issuer được phép

Liệt kê issuer chính xác. Kiểm tra metadata issuer và JWKS endpoint qua kênh tin cậy. Nếu có nhiều issuer, mỗi issuer phải có cấu hình riêng hoặc manager được resolve từ allowlist.

### Bước 3: Chọn thuật toán

Chọn asymmetric signing algorithm phù hợp với AS và crypto policy. Cấu hình allowlist trong decoder. Nếu migration nhiều thuật toán, ghi rõ thời điểm bắt đầu/kết thúc chấp nhận thuật toán cũ.

### Bước 4: Quản lý key source

Cấu hình issuer discovery hoặc static JWKS URI. Bảo đảm HTTPS, TLS validation, network egress policy và cache lifecycle. Không lấy access-token signing key từ URL do token chỉ định.

### Bước 5: Gắn validator

Kết hợp issuer, audience, timestamp và token-profile validators. Giữ scope/role/resource authorization ở authorization layer.

### Bước 6: Thiết kế rotation

Có key overlap, cache refresh, unknown-kid handling và incident response khi key bị compromise. Kiểm thử trên nhiều Resource Server instance.

### Bước 7: Kiểm thử âm

Tạo token sai issuer, audience, alg, signature, kid, expiry và token profile. Xác nhận tất cả đều bị từ chối.

### Bước 8: Quan sát và audit

Theo dõi validation failure category, JWKS fetch và rotation event. Audit mọi thay đổi trust configuration. Không log credential.

---

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Issuer và audience khác nhau thế nào?

**Trả lời:** Issuer xác định Authorization Server phát hành token; audience xác định resource/API được phép nhận token.

**Câu 2.** Vì sao token có chữ ký hợp lệ vẫn có thể bị từ chối?

**Trả lời:** Token có thể sai issuer, sai audience, hết hạn, dùng thuật toán không được phép hoặc không đúng token profile của API.

**Câu 3.** Có nên tin issuer lấy trực tiếp từ claim iss để tự discovery không?

**Trả lời:** Không. Issuer phải nằm trong allowlist đã được cấu hình và quản trị. Token không được tự mở rộng trust boundary.

**Câu 4.** client_id có thay thế audience không?

**Trả lời:** Không. client_id là OAuth client yêu cầu token; aud là resource nhận token.

**Câu 5.** Vì sao cần algorithm allowlist?

**Trả lời:** JOSE alg là input từ token. Allowlist ngăn token tự yêu cầu một thuật toán ngoài policy hoặc tạo algorithm confusion.

**Câu 6.** Vì sao asymmetric key phù hợp với nhiều Resource Server?

**Trả lời:** AS giữ private key để ký, còn Resource Server chỉ cần public key để xác minh. Verifier không cần giữ bí mật có khả năng ký token.

**Câu 7.** Có thể lấy access-token verification key từ jku trong token không?

**Trả lời:** Không nên. JWKS URI phải đến từ trust configuration hoặc metadata của issuer đã tin cậy, không từ URL do token gửi lên.

**Câu 8.** kid có phải bằng chứng key tin cậy không?

**Trả lời:** Không. kid chỉ là identifier để chọn key bên trong trusted JWKS.

**Câu 9.** Khi dùng JWKS URI trực tiếp, có cần kiểm tra issuer không?

**Trả lời:** Có. Cấu hình nguồn key không thay thế issuer validation.

**Câu 10.** Vì sao cần overlap khi rotate key?

**Trả lời:** Resource Server cần thời gian nhận key mới và vẫn phải xác minh token cũ còn hiệu lực được ký bằng key cũ.

**Câu 11.** Nếu JWKS endpoint timeout thì có thể chấp nhận token có key lạ không?

**Trả lời:** Không. Khi không có key tin cậy để xác minh chữ ký, token không thể được xác thực.

**Câu 12.** ID token có thể dùng làm access token không?

**Trả lời:** Không nên. ID token dành cho OIDC client; Resource Server phải kiểm tra audience và token profile của access token.

**Câu 13.** Introspection response HTTP 200 có đủ để chấp nhận opaque token không?

**Trả lời:** Không. Response phải cho biết active=true và các thuộc tính cần thiết phải thỏa trust policy.

**Câu 14.** Multi-issuer nên chọn decoder như thế nào?

**Trả lời:** Dùng resolver với danh sách issuer được cấu hình trước và decoder/key source/audience policy phù hợp cho từng issuer.

**Câu 15.** Metric có nên dùng subject hoặc raw kid làm tag không?

**Trả lời:** Không nên. Những giá trị động này làm tăng cardinality; dùng outcome category có giới hạn và audit riêng khi cần điều tra.

---

## 16. Tài liệu tham khảo

- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): algorithm verification, issuer/audience validation và các lỗi JWT phổ biến.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html): các claim iss, sub, aud, exp, nbf và JWT structure.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517.html): JWK, JWKS, kid, use và key metadata.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): access-token JWT profile và typ at+jwt.
- [OpenID Connect Discovery](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer metadata và jwks_uri.
- [OAuth 2.0 Authorization Server Metadata, RFC 8414](https://www.rfc-editor.org/rfc/rfc8414.html): metadata của Authorization Server.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer-uri, jwk-set-uri, JwtDecoder và validators.
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): ReactiveJwtDecoder và reactive JWT validation.
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): cấu hình JWT decoder và JWS algorithms.
- [Spring Security API — JwtIssuerAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html): resolver cho nhiều issuer tin cậy.
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection và xác thực opaque token.

API có thể thay đổi giữa các phiên bản Spring Security. Hãy kiểm tra Javadoc của đúng artifact đã resolve, đặc biệt với decoder builder, algorithm configuration và multi-issuer resolver.

---

## 17. Ghi nhớ

Resource Server phải có trust policy rõ ràng trước khi chấp nhận token. Chữ ký hợp lệ chỉ chứng minh token được ký bằng một key; issuer, audience, algorithm và key source mới xác định liệu key/token đó có được API tin cậy hay không.

- **Issuer:** chỉ chấp nhận Authorization Server đã được allowlist.
- **Audience:** token phải dành cho đúng API/resource.
- **Algorithm:** khai báo allowlist rõ ràng; không để token tự chọn thuật toán.
- **Key source:** dùng issuer metadata hoặc JWKS URI đã tin cậy qua HTTPS; không tải access-token signing key từ URL do token chỉ định.
- **Key rotation:** có overlap window, xử lý unknown kid và quy trình khẩn cấp khi key bị compromise.
- **Multi-issuer:** mỗi issuer cần decoder, key source và audience policy tương ứng.
- **Opaque token:** tin introspection endpoint đã cấu hình, kiểm tra active và response attributes; dependency failure không được cấp Authentication.
- **Testing/operations:** test cả token hợp lệ và token sai issuer, audience, alg, signature, kid, profile; audit mọi thay đổi trust config.

Một Resource Server an toàn chỉ xác thực token khi toàn bộ trust policy phù hợp với resource đang bảo vệ.
