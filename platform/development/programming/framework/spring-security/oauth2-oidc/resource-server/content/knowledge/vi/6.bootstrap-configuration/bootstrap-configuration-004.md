# Cấu hình JWT bằng issuer-uri, jwk-set-uri hoặc khóa được quản lý

Một **Spring Security OAuth 2.0 Resource Server** nhận access token từ client, xác minh token rồi quyết định quyền truy cập API. Khi access token là **JWT có chữ ký (JWS)**, Resource Server phải có **nguồn public key tin cậy** để xác minh rằng token thực sự được Authorization Server phát hành và chưa bị sửa đổi. Ba hướng cấu hình thường dùng trong Spring Boot là:

1. **`issuer-uri`:** khai báo issuer đáng tin để Spring Security khám phá metadata và JWK Set URI.
2. **`jwk-set-uri`:** khai báo trực tiếp endpoint công bố các public key, có thể kết hợp với `issuer-uri` để giữ kiểm tra `iss`.
3. **Khóa được quản lý:** cung cấp public key qua file hoặc cấu hình ứng dụng, hoặc tạo `JwtDecoder` tùy biến khi không muốn phụ thuộc metadata/JWKS endpoint tại runtime.

Ba cách này giải quyết **nguồn khóa xác minh**; chúng không thay thế việc kiểm tra `aud`, `exp`, `nbf`, loại token, scope và quyền trên từng tài nguyên. Bài học sử dụng Spring Boot và Spring Security **Servlet/Spring MVC**; với WebFlux, dùng `ReactiveJwtDecoder` và `SecurityWebFilterChain` tương ứng.

## 1. Mô hình tin cậy của Resource Server

~~~text
Authorization Server                         Resource Server (orders-api)
     |                                                 |
     | ký JWT bằng private key                          |
     |                                                 |
     +--> Client --> Authorization: Bearer <JWT> ------>|
                                                       |
                                        1. Tìm public key tin cậy
                                        2. Kiểm tra chữ ký JWS
                                        3. Kiểm tra iss / aud / exp / nbf
                                        4. Ánh xạ scope thành authority
                                        5. Kiểm tra quyền với endpoint/dữ liệu
                                                       |
                                                   200 / 401 / 403
~~~

Với thuật toán bất đối xứng như `RS256`, Authorization Server sử dụng **private key** để ký và Resource Server sử dụng **public key** tương ứng để xác minh. Public key có thể được công bố trong **JWK Set** hoặc phân phối từ một hệ thống quản lý cấu hình tin cậy. Resource Server không cần biết private key của Authorization Server.

JWT dạng JWS compact thường có ba phần:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Header có thể chứa `alg`, `kid`; payload chứa `iss`, `sub`, `aud`, `exp` và `scope`. Chỉ Base64URL decode được header/payload **không chứng minh tính hợp lệ**. Sau khi kiểm tra chữ ký, Spring Security vẫn cần các validator về issuer, audience, thời gian và loại token. Sau khi token hợp lệ, ứng dụng tiếp tục kiểm tra quyền.

### Những thành phần Spring Security cần biết

| Thành phần | Trách nhiệm |
|---|---|
| `BearerTokenAuthenticationFilter` | Lấy bearer token từ HTTP request |
| `JwtAuthenticationProvider` | Điều phối việc xác thực JWT |
| `JwtDecoder` | Giải mã và xác minh JWT theo cấu hình |
| `NimbusJwtDecoder` | Implementation phổ biến dựa trên Nimbus JOSE + JWT |
| `OAuth2TokenValidator<Jwt>` | Kiểm tra claim và chính sách token |
| `JwtAuthenticationConverter` | Ánh xạ JWT thành principal/authorities |
| `SecurityFilterChain` | Áp dụng rule xác thực và phân quyền |

Một JWT có `scope="orders.read"` thường được Spring Security chuyển thành authority `SCOPE_orders.read`, **sau khi token được xác minh**. Đây là lớp phân quyền riêng với việc xác minh chữ ký.

## 2. Chuẩn bị ứng dụng Spring Boot

### 2.1. Dependency

Trong ứng dụng Spring MVC dùng Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Starter Resource Server của Spring Boot đưa vào các thư viện cần thiết cho JWT. Nếu quản lý từng module Spring Security bằng tay, hỗ trợ JWT cần cả `spring-security-oauth2-resource-server` và `spring-security-oauth2-jose`.

### 2.2. Cấu hình SecurityFilterChain dùng chung

Đây là filter chain có thể dùng với cả ba cách cung cấp public key:

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
                .requestMatchers("/actuator/health").permitAll()
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

Cấu hình này yêu cầu JWT bearer cho các route được bảo vệ. Các yêu cầu riêng về CORS, CSRF, session và browser cookie phải được thiết kế theo kiến trúc ứng dụng; đừng vô hiệu hóa CSRF vô điều kiện nếu browser còn sử dụng cookie để xác thực request.

`oauth2.jwt()` chỉ bật cơ chế xử lý JWT. Resource Server vẫn phải biết **public key lấy ở đâu** và **issuer/audience nào được chấp nhận**.

## 3. Phương án A: `issuer-uri` — khám phá nguồn khóa qua issuer

Đây là lựa chọn phổ biến khi Authorization Server hỗ trợ **OpenID Connect Discovery** hoặc **OAuth 2.0 Authorization Server Metadata**.

### 3.1. Cấu hình application.yml

Giả sử issuer được công bố là `https://idp.example.com/realms/shop` và API hiện tại có audience `orders-api`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

Ý nghĩa:

- `issuer-uri` là **định danh Authorization Server đáng tin**, không phải token endpoint hay trang đăng nhập.
- Spring Security có thể khám phá metadata của issuer, tìm `jwks_uri` và dùng public keys ở đó để xác minh chữ ký JWT.
- Spring Security áp dụng validator `iss` tương ứng issuer đã khai báo.
- `audiences` là thuộc tính Spring Boot hỗ trợ trong các phiên bản hiện đại để kiểm tra `aud`. Nếu phiên bản Boot đang dùng chưa hỗ trợ, phải cung cấp audience validator riêng.

**Giá trị `issuer-uri` phải khớp chính xác claim `iss` trong token** theo hợp đồng của Authorization Server. Sự khác biệt về đường dẫn hoặc dấu `/` cuối có thể khiến kiểm tra issuer thất bại.

### 3.2. Điều gì xảy ra khi discovery?

Ở mức khái niệm:

~~~text
Resource Server
    |
    | issuer-uri đã tin cậy
    v
OIDC Provider Configuration / OAuth AS Metadata
    |
    | tìm jwks_uri
    v
JWK Set endpoint của AS
    |
    | public keys: kid, kty, n, e...
    v
JwtDecoder
    |
    +-- chọn khóa phù hợp
    +-- kiểm tra chữ ký
    +-- kiểm tra issuer, exp, nbf, audience và policy
    v
Authentication hợp lệ hoặc lỗi
~~~

Ví dụ một endpoint metadata mà nhà cung cấp OIDC **có thể** hỗ trợ:

~~~text
https://idp.example.com/realms/shop/.well-known/openid-configuration
~~~

Phản hồi minh họa:

~~~json
{
  "issuer": "https://idp.example.com/realms/shop",
  "jwks_uri": "https://idp.example.com/realms/shop/protocol/openid-connect/certs"
}
~~~

Đường dẫn metadata/JWKS phụ thuộc nhà cung cấp. Spring Security có quy tắc khám phá những endpoint chuẩn tương ứng với issuer, kể cả những issuer có path. Không tự đoán cấu trúc URL nếu có tài liệu/metadata chính thức.

### 3.3. Các điều kiện cần có ngoài chữ ký

Với đường cấu hình Spring Security Resource Server chuẩn, hệ thống kiểm tra chữ ký, `exp`, `nbf` và `iss` theo cấu hình. **Không mặc định có audience validation chỉ vì có `issuer-uri`**; khai báo `audiences` hoặc validator riêng.

Ví dụ:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["billing-api"],
  "scope": "billing.read"
}
~~~

Dù chữ ký hợp lệ và đúng issuer, `orders-api` phải từ chối token chỉ dành cho `billing-api`. Kiểm tra audience giúp ngăn client dùng token cho dịch vụ khác trong cùng hệ thống.

### 3.4. Discovery diễn ra khi startup hay lúc nhận request?

Các phiên bản/cách cấu hình Spring Security có thể khác nhau về thời điểm truy cập metadata/JWKS. Tài liệu Spring Security hiện đại mô tả khả năng **lazily discover** thông tin issuer khi nhận JWT đầu tiên thông qua `SupplierJwtDecoder`. Điều này giúp startup không nhất thiết phụ thuộc AS luôn online.

Tuy nhiên, nếu tự tạo decoder bằng một factory eager hoặc thay bean mặc định, việc truy cập AS có thể diễn ra sớm hơn. Do đó cần phân biệt:

- **Ứng dụng startup**: có thể không cần kết nối AS tức thời khi dùng cơ chế lazy phù hợp.
- **JWT đầu tiên**: nếu chưa có metadata/keys, việc xác minh có thể cần network.
- **Những JWT tiếp theo**: public keys được cache theo cơ chế của decoder; key rotation có thể đòi refresh.
- **Custom JwtDecoder**: cần xem chính xác factory/bean được tạo ra khi nào.

Không dựa vào khẳng định “`issuer-uri` lúc nào cũng chặn startup” hoặc “`issuer-uri` không bao giờ cần mạng khi runtime”. Hãy kiểm tra Spring Boot/Security version và cách tạo decoder thực tế.

### 3.5. Khi nào nên chọn `issuer-uri`?

Phù hợp khi Authorization Server công bố metadata chuẩn, Resource Server có kết nối tới AS/JWKS, cần key rotation qua nhiều khóa và muốn sử dụng cấu hình Spring Boot đơn giản. Đây thường là điểm khởi đầu tốt cho IdP/OIDC Provider chuẩn.

## 4. Phương án B: `jwk-set-uri` — chỉ rõ JWK Set endpoint

Một số Authorization Server phát hành JWT và công bố JWKS nhưng không hỗ trợ metadata discovery, hoặc đội vận hành muốn kiểm soát tường minh địa chỉ JWKS.

### 4.1. Chỉ cấu hình `jwk-set-uri`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://idp.example.com/realms/shop/protocol/openid-connect/certs
~~~

Spring Security biết nguồn public keys, không phải khám phá URI từ metadata. Nhưng cần nhớ:

> **JWK Set URI cho biết khóa lấy ở đâu; nó không tự xác định issuer nào là hợp lệ.**

Nếu chỉ khai báo `jwk-set-uri`, không mặc định Spring Security kiểm tra claim `iss` theo một issuer mong muốn. Resource Server phải thêm issuer validation nếu API có issuer tin cậy cố định. Cũng cần kiểm tra `aud` và các policy token khác.

### 4.2. Cấu hình khuyến nghị khi biết cả issuer và JWKS

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
~~~

Đây là một lựa chọn hữu ích:

| Thuộc tính | Trách nhiệm |
|---|---|
| `issuer-uri` | Giá trị `iss` được tin cậy |
| `jwk-set-uri` | Nguồn public keys được tin cậy |
| `audiences` | Tài nguyên/API mà token phải nhắm tới |

Khi có `jwk-set-uri`, Resource Server **không cần discovery metadata chỉ để tìm JWKS URI**. Nhưng nó vẫn có thể phải kết nối JWKS endpoint để tải khóa chưa có hoặc cập nhật khóa mới. Nếu AS/JWKS mất kết nối, JWT có khóa đã cache có thể vẫn được xử lý tùy cache và cấu hình.

### 4.3. JWK Set và `kid`

Ví dụ phản hồi JWKS đơn giản:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-key-A",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-modulus-A>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "signing-key-B",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-modulus-B>",
      "e": "AQAB"
    }
  ]
}
~~~

- `keys`: danh sách khóa công khai.
- `kid`: định danh khóa giúp chọn khóa tương ứng với JWT header.
- `kty`: loại khóa, ví dụ RSA.
- `alg` và `use`: mô tả thuật toán/mục đích nếu AS cung cấp.
- `n`, `e`: thành phần RSA public key.

Ví dụ minh họa ở đây không chứa key thật. Authorization Server không nên công bố private-key material trong JWKS công khai.

JWT header có thể chứa:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-B"
}
~~~

`kid` chỉ là **gợi ý chọn khóa trong nguồn JWKS đã tin cậy**. Header JWT là dữ liệu chưa xác minh; không lấy URL tùy ý từ header `jku` hay `x5u` rồi tin khóa của attacker. Cấu hình trusted JWKS URI phải đến từ hệ thống quản lý cấu hình của ứng dụng, không từ request.

### 4.4. Tạo decoder với JWKS bằng Java

Khi cần tự cấu hình validator thay vì chỉ dùng properties, ví dụ:

~~~java
package com.example.orders.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwksDecoderConfig {

    private static final String ISSUER =
        "https://idp.example.com/realms/shop";
    private static final String JWKS =
        "https://idp.example.com/realms/shop/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(JWKS).build();

        OAuth2TokenValidator<Jwt> audience =
            new JwtClaimValidator<List<String>>(
                "aud", values -> values != null &&
                        values.contains("orders-api")
            );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audience
            )
        );

        return decoder;
    }
}
~~~

Đây là cách giữ **issuer, thời gian và audience validation** khi tự tạo decoder. `JwtValidators.createDefaultWithIssuer(...)` cung cấp những kiểm tra mặc định kèm issuer; `JwtClaimValidator` thêm điều kiện audience.

Trong ứng dụng thực tế, chuyển URL/expected audience sang configuration properties theo môi trường. URL của issuer và JWKS phải được quản lý bởi hệ thống đáng tin.

**Lưu ý về Spring Boot auto-configuration:** khi bạn tự khai báo bean `JwtDecoder`, Boot thường dừng tự tạo decoder mặc định. Không giả định các property như `audiences` trong YAML sẽ tự động gắn vào decoder bạn viết. Hãy tự cấu hình đủ validators.

## 5. Phương án C: khóa xác minh được quản lý cục bộ

Nếu Resource Server không thể truy cập JWKS endpoint, hoặc hệ thống triển khai phân phối public key qua file/config volume, có thể dùng một RSA public key được quản lý.

### 5.1. Thuộc tính `public-key-location`

Spring Boot hỗ trợ chỉ định file public key:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          public-key-location: classpath:keys/as-public.pem
          audiences:
            - orders-api
~~~

Ví dụ file `src/main/resources/keys/as-public.pem` theo định dạng **PEM X.509 SubjectPublicKeyInfo**:

~~~text
-----BEGIN PUBLIC KEY-----
<base64-encoded-public-key>
-----END PUBLIC KEY-----
~~~

Phần giữa là dữ liệu ví dụ, không phải khóa có thể dùng thật. Đối với JWS bất đối xứng, Resource Server chỉ cần public key để xác minh, **không chứa private signing key của AS**.

Có thể đặt file ngoài application artifact:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          public-key-location: file:/etc/orders/security/as-public.pem
~~~

Điều này phù hợp khi vận hành phân phối public key qua volume hoặc hệ thống quản lý cấu hình. Tuy nhiên, **đổi file trên đĩa không bảo đảm decoder đang chạy tự nạp lại khóa**. Cần có chính sách reload, rolling restart hoặc cơ chế phân phối key thay thế.

### 5.2. Khóa được quản lý ở đâu?

“Managed key” có thể là một trong các mô hình:

| Mô hình | Đặc điểm | Cân nhắc |
|---|---|---|
| Public key đóng gói trong jar | Ít phụ thuộc runtime | Thay key có thể cần build/deploy |
| Public key trên volume | Tách khóa khỏi artifact | Phải quản lý quyền đọc và reload |
| Public key từ config/secret manager | Quản lý tập trung, audit | Bảo vệ quyền sửa nguồn trust và caching |
| JWKS nội bộ do tổ chức quản lý | Công bố nhiều public keys | Vẫn là mô hình `jwk-set-uri` |
| Private key của AS nằm ở HSM/KMS | Bảo vệ thao tác ký ở AS | RS thông thường chỉ lấy public key, không cần quyền ký |

Việc **public key không bí mật** không có nghĩa ai cũng được quyền thay nó. Nếu kẻ tấn công thay public key đáng tin trong cấu hình của Resource Server, chúng có thể khiến API chấp nhận token được ký bằng private key do chúng nắm giữ.

### 5.3. Một khóa cố định có hạn chế gì?

Với `NimbusJwtDecoder.withPublicKey(publicKey)`, một decoder cố định tin khóa được truyền vào. Nó không tự biết danh sách key rotation của AS. Khi AS thay private key ký token, API phải có public key mới tương ứng. Trong giai đoạn cả JWT cũ và mới cùng còn hiệu lực, có thể cần chấp nhận đồng thời nhiều khóa; JWKS nhiều public keys thường phù hợp hơn việc hardcode một key.

Nếu dùng `public-key-location`, Resource Server cũng không tự suy ra **issuer hợp lệ** từ nội dung public key. Hãy bảo đảm issuer validator (và audience validator) được áp dụng theo cấu hình Boot/Security cụ thể.

### 5.4. Tự tạo decoder từ RSA public key được quản lý

Ví dụ ứng dụng nhận RSA public key từ resource path và chủ động cấu hình issuer/audience:

~~~yaml
security:
  jwt:
    public-key-location: file:/etc/orders/security/as-public.pem
    issuer: https://idp.example.com/realms/shop
    audience: orders-api
~~~

~~~java
package com.example.orders.security;

import java.security.interfaces.RSAPublicKey;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class ManagedPublicKeyConfig {

    @Bean
    JwtDecoder jwtDecoder(
        @Value("${security.jwt.public-key-location}") RSAPublicKey publicKey,
        @Value("${security.jwt.issuer}") String issuer,
        @Value("${security.jwt.audience}") String audience
    ) {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withPublicKey(publicKey).build();

        OAuth2TokenValidator<Jwt> audienceValidator =
            new JwtClaimValidator<List<String>>(
                "aud",
                aud -> aud != null && aud.contains(audience)
            );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator
            )
        );

        return decoder;
    }
}
~~~

Spring Security hỗ trợ chuyển đổi một số dạng RSA public key resource thành `RSAPublicKey` thông qua conversion service phù hợp. Trong ứng dụng không có converter tương ứng, có thể nhận `Resource` rồi parse PEM bằng `RsaKeyConverters.x509()` hoặc cấu hình bean nạp khóa riêng. Việc cấp khóa phải được kiểm tra theo version và phương thức tích hợp đang dùng.

**Điểm quan trọng:** `withPublicKey(...)` lựa chọn public key để xác minh chữ ký, **không tự xác định issuer/audience**. Ví dụ trên chủ động dùng `JwtValidators.createDefaultWithIssuer(...)` cùng audience validator.

### 5.5. Đừng nhầm public key với private key hoặc shared secret

~~~text
Authorization Server                      Resource Server
  private key                                public key
      |                                          |
      | ký JWT                                   | verify JWT
      v                                          v
     JWT -------------------------------------> JWT
~~~

- **Private key** dùng ký JWS bất đối xứng; chỉ AS hoặc dịch vụ ký được ủy quyền cần sử dụng.
- **Public key** dùng kiểm tra chữ ký; có thể phân phối tới nhiều Resource Server.
- **HMAC secret (HS256)** dùng chung cho tạo và kiểm tra MAC; nếu chia sẻ secret cho RS, RS cũng có khả năng tạo MAC. Vì vậy nó có rủi ro trust khác so với mô hình bất đối xứng. Spring Security hỗ trợ `withSecretKey`, nhưng không nên mặc định chọn HMAC cho hệ thống đa Resource Server nếu phân tách quyền ký là yêu cầu quan trọng.

## 6. So sánh ba lựa chọn

| Tiêu chí | `issuer-uri` | `jwk-set-uri` | Public key quản lý |
|---|---|---|---|
| Cần biết trước | Issuer | JWKS URI | Public key/resource |
| Metadata discovery | Có | Không cần để tìm JWKS | Không cần |
| Nguồn public keys | JWKS tìm qua metadata | JWKS cấu hình trực tiếp | File/config/key provider |
| Kiểm tra `iss` | Có theo issuer config | Cần cấu hình issuer/validator | Cần cấu hình issuer/validator |
| Kiểm tra `aud` | Cấu hình audience riêng | Cấu hình audience riêng | Cấu hình audience riêng |
| Hỗ trợ nhiều public keys | Theo JWKS | Theo JWKS | Tùy cách quản lý |
| Rotation | Refresh JWKS | Refresh JWKS | Phân phối/reload key |
| Runtime network | Metadata/JWKS khi cần | JWKS khi cần | Có thể offline |
| Trường hợp phù hợp | AS hỗ trợ discovery | AS chỉ công bố JWKS hoặc muốn endpoint cố định | Hạ tầng tách mạng, cung cấp key riêng |
| Rủi ro vận hành | Metadata sai/không sẵn sàng | URI sai hoặc quên issuer | Key cũ, sai định dạng, không có reload |

Quy tắc lựa chọn:

~~~text
Authorization Server có discovery chuẩn?
    |
    +-- Có ----> issuer-uri
    |              |
    |              +-- Nếu muốn chỉ rõ JWKS: thêm jwk-set-uri
    |
    +-- Không
         |
         +-- Có JWKS endpoint ---> jwk-set-uri + issuer validator
         |
         +-- Chỉ có public key --> public-key-location/custom JwtDecoder
~~~

Trong cả ba nhánh, cần xác minh `iss`/`aud` theo hợp đồng API. Không chọn chiến lược khóa chỉ dựa vào việc token “đọc được bằng Base64URL”.

## 7. Kiểm soát thuật toán ký JWT

Header token có thể tự khai báo:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-02"
}
~~~

JWT header là dữ liệu **chưa tin cậy trước khi xác minh**. Decoder phải dùng thuật toán ký thuộc tập được cho phép, đồng thời kiểm tra loại khóa tương ứng. Đường cấu hình Spring Security phổ biến mặc định tin thuật toán theo chính sách của decoder, thường là `RS256` trong cấu hình được tài liệu mô tả.

Khi AS thực sự ký bằng `RS512`, có thể khai báo:

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

Hoặc trong custom decoder:

~~~java
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;

// ...
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(jwksUri)
    .jwsAlgorithm(SignatureAlgorithm.RS512)
    .build();
~~~

Nếu tự tạo decoder, nhớ gắn các claim validators như phần trước. Không đổi thuật toán để “chữa” một JWT giả chữ ký; phải xác định rõ thuật toán AS ký thực tế và đảm bảo public key tương thích.

Không chấp nhận `alg=none` trong API yêu cầu JWT đã ký, không để token tự làm thay đổi nguồn khóa/thuật toán ngoài trust configuration.

## 8. Issuer, audience và thời hạn là các lớp kiểm tra riêng

### Issuer (`iss`)

Issuer khẳng định token được phát hành bởi bên nào theo hợp đồng. Với một issuer cố định:

~~~json
{
  "iss": "https://idp.example.com/realms/shop"
}
~~~

Phải khớp cấu hình mà API tin. Việc người gọi sửa `iss` trong payload không đủ để biến token thành hợp lệ vì chữ ký phải được kiểm tra cùng các claim.

### Audience (`aud`)

Audience trả lời **token này dùng ở API nào**:

~~~json
{
  "aud": ["orders-api"]
}
~~~

Nếu token dành cho `inventory-api`, `orders-api` phải từ chối ngay cả khi chữ ký và issuer đúng. Với Spring Boot hiện đại, dùng `spring.security.oauth2.resourceserver.jwt.audiences`; custom decoder phải gắn audience validator rõ ràng.

### Thời gian hiệu lực

- `exp`: từ chối JWT hết hạn.
- `nbf`: không chấp nhận JWT trước thời điểm bắt đầu hiệu lực.
- `iat`: thời điểm phát hành; có thể áp dụng chính sách tuổi token bổ sung.

Spring Security cung cấp `JwtTimestampValidator` và mặc định kiểm tra thời gian trong đường cấu hình chuẩn. Nếu thay validator bằng custom logic, phải giữ các kiểm tra thời gian cần thiết. Giới hạn clock skew ở mức có chủ đích và đồng bộ thời gian máy chủ.

### Token type và profile

Trong OpenID Connect, **ID token** dành cho OIDC client; **access token** dành cho Resource Server. Không dùng ID token thay access token chỉ vì cả hai là JWT. Với profile JWT access token theo RFC 9068, có thể kiểm tra thêm token type và các claim theo profile. Điều này là chính sách bổ sung, không chỉ là việc chọn public key.

### Sau khi token hợp lệ: phân quyền

Access token có `scope=orders.read` có thể giúp truy cập `GET /api/orders`, nhưng không tự được phép `POST /api/orders`. Và ngay cả khi có scope đọc, API phải kiểm tra người dùng có quyền trên **đơn hàng cụ thể** hay không.

## 9. Key rotation và cache public keys

### 9.1. Rotation qua JWKS

AS có thể chuyển từ `key-A` sang `key-B` theo lộ trình:

~~~text
T0: JWKS có key-A; AS ký bằng key-A
T1: JWKS công bố key-A và key-B
T2: AS bắt đầu ký JWT mới bằng key-B
T3: Token ký bằng key-A đã hết hạn
T4: AS gỡ key-A khỏi JWKS
~~~

Khi JWKS có cả hai public keys, Resource Server có cơ sở xác minh token cũ và mới trong giai đoạn chuyển tiếp. Decoder/JWKS cache cần được làm mới phù hợp khi gặp `kid` mới. Những lỗi thường gặp là AS ký bằng key mới trước khi public key xuất hiện trong JWKS, hoặc AS gỡ key cũ quá sớm.

Cơ chế JWKS của Spring Security/Nimbus có cache/refresh theo implementation và version. Vận hành cần kiểm tra timeout, cache TTL, key-rotation schedule, TLS/DNS và hành vi khi không tải được JWKS.

### 9.2. Rotation của key file

Nếu Resource Server nạp **một public key cố định**, việc thay file/biến môi trường không đồng nghĩa bean `JwtDecoder` tự cập nhật ngay. Cần triển khai hoặc reload khóa theo kế hoạch. Nếu muốn chấp nhận đồng thời nhiều khóa, có thể chọn JWKS hoặc `JWKSource` tin cậy hỗ trợ nhiều khóa thay cho việc hardcode một public key duy nhất.

### 9.3. Khóa cũ có nên bị gỡ ngay?

Không nhất thiết. Một access token được ký bằng key cũ có thể vẫn còn hạn. Nếu gỡ key khỏi JWKS trước khi tất cả token cũ hết hạn, API sẽ bắt đầu trả `401` cho các token đó. Thời điểm gỡ key cần cân bằng bảo mật, thời hạn token và trường hợp khẩn cấp phải vô hiệu hóa khóa.

Trong trường hợp private key bị lộ, có thể phải ưu tiên thu hồi/loại bỏ khóa ngay dù token hợp lệ trước đó bị ảnh hưởng. Đây là quyết định incident response cần phối hợp toàn hệ thống.

## 10. Cấu hình khác nhau theo môi trường

Không sử dụng nhầm issuer/JWKS/public key giữa dev, staging và production.

`application-dev.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp-dev.example.com/realms/shop
          audiences:
            - orders-api-dev
~~~

`application-prod.yml`:

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
~~~

Các giá trị issuer/JWKS là thông tin có thể công khai nhưng **quyền sửa chúng là quyền bảo mật nhạy cảm**. Nếu attacker thay được `jwk-set-uri` sang endpoint do họ sở hữu, họ có thể khiến API tin chữ ký giả mạo khi các điều kiện khác không đủ chặt.

Với key được mount trên filesystem, đặt quyền truy cập chỉ đọc phù hợp, xác định vòng đời rotate và đảm bảo mọi instance đọc cùng phiên bản khóa theo rollout. Không chứa private key của AS trong Resource Server repository, image hoặc config.

## 11. Custom decoder và tác động tới auto-configuration

Nếu ứng dụng có bean:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    return NimbusJwtDecoder.withJwkSetUri(jwksUri).build();
}
~~~

Spring Boot thường **back off** thay vì tạo `JwtDecoder` mặc định khác. Do đó:

- Các property YAML như `issuer-uri` hoặc `audiences` có thể không được áp dụng vào decoder tùy biến.
- `withJwkSetUri(...)` chỉ chọn nguồn khóa; nó không tự biết issuer được tin.
- Khi gọi `setJwtValidator(...)`, hãy kết hợp issuer, thời gian và audience thay vì vô tình thay mất những validator cần thiết.
- Tạo bean eager có thể làm thay đổi thời điểm gọi metadata/JWKS so với đường auto-config lazy.
- Nếu nhiều filter chain cùng tồn tại, xác định chuỗi nào thực sự xử lý URL hiện tại.

Nếu nhu cầu chỉ là chọn issuer/JWKS/audience thông thường, cấu hình Boot bằng YAML thường gọn và ít rủi ro cấu hình thiếu hơn.

### Tránh nhầm hai API tạo decoder

~~~java
JwtDecoder byIssuer =
    JwtDecoders.fromIssuerLocation(issuerUri);

NimbusJwtDecoder byJwks =
    NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();
~~~

`fromIssuerLocation(...)` cần **issuer URI**, không phải URL của JWKS. `withJwkSetUri(...)` cần **JWK Set URI**, không phải issuer URI. Với decoder do builder JWKS tạo, phải tự bổ sung issuer validation khi cần.

## 12. Trường hợp nhiều issuer hoặc nhiều tenant

Một Resource Server phục vụ nhiều tenant có thể phải chấp nhận JWT từ một tập issuer được doanh nghiệp phê duyệt:

~~~text
tenant-A -> https://idp-a.example.com
tenant-B -> https://idp-b.example.com
~~~

Lúc này, ứng dụng có thể cần đọc claim `iss` **chưa xác minh** để chọn decoder. Điều đó chỉ được phép dùng làm **gợi ý chọn ứng viên trong allowlist issuer đã tin cậy**, sau đó decoder được chọn phải kiểm tra lại chữ ký, issuer, audience và tenant policy.

Không tự động khám phá JWKS từ mọi URL `iss` mà client gửi tới; hành vi đó có thể gây SSRF hoặc làm Resource Server tin một issuer do attacker điều khiển. Hãy dùng trust registry/allowlist, giới hạn network destinations và kiểm soát cấu hình từng tenant.

Các API hỗ trợ multi-tenant trong Spring Security có thể thay đổi theo phiên bản; chọn thiết kế tương thích với stack cụ thể và tránh tự viết cơ chế chọn khóa dựa trên token chưa xác minh nếu không cần thiết.

## 13. Chẩn đoán lỗi khi cấu hình JWT

### 13.1. `401 Unauthorized`

Các nguyên nhân phổ biến:

| Triệu chứng | Nơi cần kiểm tra |
|---|---|
| JWT đọc được payload nhưng chữ ký bị từ chối | Public key/JWKS, thuật toán, JWS signature |
| `iss` khác `issuer-uri` | Issuer thực từ AS; đường dẫn và dấu `/` cuối |
| `aud` không chứa API hiện tại | Audience validator, token được cấp cho API nào |
| JWT hết hạn/chưa hiệu lực | `exp`, `nbf`, đồng bộ thời gian, clock skew |
| Header có `kid` mới nhưng API thiếu khóa | AS JWKS, cache/refresh, rotation |
| JWKS 404 hoặc TLS lỗi | URI, DNS, certificate trust, firewall, proxy |
| AS không hỗ trợ discovery | Chuyển sang `jwk-set-uri` trực tiếp và giữ issuer validation |
| Dùng ID token/opaque token thay JWT access token | Luồng OAuth/OIDC, loại token, cấu hình Resource Server |
| YAML đúng nhưng decoder hành xử khác | Có custom `JwtDecoder` bean hoặc nhiều SecurityFilterChain không? |

**Lưu ý:** nhìn thấy `scope` hoặc `iss` qua Base64URL decoder không có nghĩa token đã xác minh được. JWT payload dễ đọc, kể cả khi signature giả.

### 13.2. `403 Forbidden`

Nếu JWT đã xác thực nhưng thiếu `SCOPE_orders.write` để gọi POST, API có thể trả `403`. Đây là lỗi **phân quyền**, không nhất thiết liên quan key source. Ngoài scope, service còn có thể kiểm tra ownership hoặc tenant.

### 13.3. JWKS/AS không sẵn sàng

- Với `issuer-uri`, metadata/JWKS có thể phải được gọi khi discovery hoặc refresh chưa hoàn tất.
- Với `jwk-set-uri`, bỏ được discovery nhưng vẫn có thể cần network tới JWKS endpoint.
- Với managed public key trong local resource, có thể xác minh offline miễn là decoder có khóa phù hợp.
- Với JWKS cache đã có key, một số token có thể tiếp tục được xác minh khi endpoint gặp sự cố; không mặc định mọi token/khóa mới đều xử lý được.

Không **fail open** và chấp nhận token chưa xác minh chỉ vì không truy cập được AS/JWKS.

### 13.4. Public key file có định dạng sai

Một số lỗi thực tế:

- Path sai hoặc service account không có quyền đọc.
- File chứa `-----BEGIN RSA PUBLIC KEY-----` dạng PKCS#1 thay vì `-----BEGIN PUBLIC KEY-----` dạng X.509 SubjectPublicKeyInfo mà loader mong đợi.
- File là certificate PEM hoặc private key không đúng định dạng được hỗ trợ.
- Public key không khớp private key mà AS dùng để ký.
- Algorithm yêu cầu EC nhưng cấu hình lại dùng RSA public key.
- File đã đổi nhưng decoder vẫn giữ key cũ trong bộ nhớ.

Xử lý bằng cách xác định format của key material và contract của loader; không tắt verify signature để “chạy được”.

## 14. Bảo vệ token và thông tin cấu hình

Bearer token là credential: bên nào nắm được access token hợp lệ có thể sử dụng các quyền mà token cho phép, nếu không có cơ chế ràng buộc khác. Vì vậy:

- Sử dụng HTTPS khi client gọi Resource Server và khi Resource Server lấy metadata/JWKS.
- Không log nguyên `Authorization` header hoặc access token.
- Không dán token thật vào website JWT decoder, chat, ticket hay issue công khai.
- Không mở endpoint debug cho phép client đọc trust config nội bộ hoặc toàn bộ JWT claims.
- Giới hạn audience, scope và thời hạn token.
- Ghi telemetry phân loại lỗi mà không để lộ credential.

Log minh họa:

~~~text
event=jwt_authentication_failed
path=/api/orders
reason=invalid_audience
expectedAudience=orders-api
traceId=3c2a...
bearerToken=[REDACTED]
~~~

Địa chỉ JWKS/issuer có thể là public URL nhưng vẫn là **điểm đặt niềm tin**, vì vậy phải bảo vệ quy trình thay đổi cấu hình và có giám sát đối với key rotation.

## 15. Ví dụ triển khai hoàn chỉnh: orders-api dùng `issuer-uri`

Nếu AS công bố metadata chuẩn, cấu hình gọn:

`build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

`SecurityConfig.java`:

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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
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

Controller có thể sử dụng JWT principal đã xác thực:

~~~java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/orders/whoami")
    public Map<String, String> whoami(
            @AuthenticationPrincipal Jwt jwt) {
        return Map.of("subject", jwt.getSubject());
    }
}
~~~

Ví dụ này giả định token hợp lệ có `sub` không null theo hợp đồng AS. Trong sản phẩm thực tế, không trả claim nhạy cảm không cần thiết và vẫn kiểm tra quyền trên dữ liệu.

Gọi API bằng access token kiểm thử do AS phát hành:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.com/api/orders/whoami
~~~

Các kết quả điển hình:

| Trường hợp | HTTP dự kiến | Lý do |
|---|---|---|
| JWT hợp lệ, đúng issuer/audience, có `orders.read` | `200` | Xác thực và phân quyền thành công |
| Không gửi bearer token | `401` | Thiếu xác thực |
| JWT sai chữ ký | `401` | Decoder từ chối |
| JWT đúng chữ ký nhưng `iss` sai | `401` | Issuer validation thất bại |
| JWT đúng chữ ký nhưng `aud` sai | `401` | Audience validation thất bại |
| JWT hết hạn | `401` | Time validation thất bại |
| JWT hợp lệ nhưng thiếu `orders.read` | `403` | Thiếu authority |
| Không tải được JWKS khi cần key mới | Tùy cách xử lý exception/cache | Không đủ điều kiện để xác minh token |

HTTP status thực tế có thể thay đổi theo filter chain, exception handler và custom error mapping; cần quan sát runtime.

## 16. Tình huống lựa chọn trong thực tế

### Trường hợp A — OIDC Provider chuẩn

AS công bố `.well-known/openid-configuration` và `jwks_uri`. Dùng `issuer-uri` kèm `audiences` để giảm cấu hình thủ công và tận dụng JWKS rotation.

### Trường hợp B — AS chỉ có JWKS

Không có endpoint discovery nhưng có URL JWKS tin cậy. Dùng **`issuer-uri` + `jwk-set-uri` + `audiences`** nếu phù hợp; direct JWKS để lấy khóa và issuer property để validate claim `iss`.

### Trường hợp C — API chạy trong mạng tách biệt

Resource Server không thể truy cập metadata/JWKS, nhưng được cấp public key qua hệ thống triển khai. Dùng `public-key-location` hoặc custom `JwtDecoder`, gắn đầy đủ issuer/audience validators và tổ chức quy trình key rotation.

### Trường hợp D — nhiều issuer

Không cho phép client chọn JWKS tùy ý. Sử dụng danh sách issuer đã được phê duyệt, chọn decoder theo registry, xác minh lại issuer sau khi chọn rồi thực thi tenant/audience policy.

## 17. Những hiểu nhầm cần tránh

**“`issuer-uri` là địa chỉ JWKS.”** Sai. Nó là định danh issuer. Spring Security có thể sử dụng issuer để khám phá JWKS qua metadata.

**“`jwk-set-uri` đã tự bảo đảm `iss` đúng.”** Sai. Cần issuer validator hoặc khai báo đồng thời issuer property.

**“Có `issuer-uri` là `aud` tự được kiểm tra.”** Không mặc định. Hãy cấu hình expected audience rõ ràng.

**“`jwk-set-uri` nghĩa là API không còn phụ thuộc mạng.”** Sai. Nó bỏ bước metadata discovery, nhưng vẫn cần tải/refresh JWKS khi cần.

**“Có một file public key thì JWT luôn hợp lệ.”** Sai. Public key chỉ phục vụ signature verification; vẫn cần kiểm tra claim và quyền.

**“Spring Boot luôn dùng properties của mình dù đã có custom JwtDecoder.”** Không bảo đảm. Bean custom có thể làm auto-configuration back off.

**“JWT header `kid` là nguồn trust.”** Sai. Nó là gợi ý chọn khóa trong tập khóa đáng tin cậy.

**“Public key file tự reload khi bị thay.”** Không mặc định. Decoder có thể giữ khóa đã nạp; cần thiết kế reload/deploy.

**“RS cần private key của AS để verify.”** Sai với thuật toán bất đối xứng; RS chỉ cần public key.

**“JWT chữ ký đúng thì endpoint nào cũng được gọi.”** Sai. Audience, scope và authorization policy vẫn quyết định phạm vi.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** AS có discovery chuẩn và luân chuyển public keys qua JWKS. Nên bắt đầu bằng cách nào?

> Dùng `issuer-uri` và expected audience. Spring Security khám phá nguồn khóa và kiểm tra issuer theo cấu hình.

**Câu 2.** AS không có metadata, chỉ có JWKS URL. Làm sao giữ kiểm tra issuer?

> Khai báo cả `issuer-uri` và `jwk-set-uri` hoặc custom decoder với `JwtValidators.createDefaultWithIssuer(...)`.

**Câu 3.** JWT có `aud=billing-api`, được ký bằng cùng khóa mà `orders-api` tin. Cho phép dùng không?

> Không. Nếu `orders-api` yêu cầu `aud=orders-api`, audience validator phải từ chối token.

**Câu 4.** Khi AS đổi key, token mới bị `401` nhưng token cũ vẫn hoạt động. Cần kiểm tra gì?

> `kid` mới, JWKS đã công bố public key mới chưa, cache/refresh, thuật toán, TLS/DNS và khả năng tải endpoint. Không bỏ qua xác minh chữ ký.

**Câu 5.** Với `public-key-location`, Resource Server có cần private signing key không?

> Không. RSA public key đủ để xác minh JWS bất đối xứng; private key phải được bảo vệ ở Authorization Server.

**Câu 6.** Đã tự khai báo `JwtDecoder` bean, property `audiences` không có hiệu lực. Hướng xử lý?

> Kiểm tra cơ chế Boot back-off và gắn audience validator vào decoder tự tạo; giữ issuer/time validation.

## 19. Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer discovery, direct JWK Set URI, trusted algorithms, validation và authorization.
- [Spring Boot — OAuth2 Resource Server](https://docs.spring.io/spring-boot/reference/security/oauth2.html): các property `issuer-uri`, `jwk-set-uri`, `public-key-location` và `audiences`.
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): builders dùng issuer, JWK Set, RSA public key và shared secret.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): JWS format và signature.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK và JWK Set.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): các JWT claims.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): chuẩn metadata của AS.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer và OIDC provider configuration.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): trust của thuật toán và khóa, issuer/audience validation.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token.

Khi cấu hình Resource Server, hãy tách rõ ba quyết định: **lấy public key đáng tin từ đâu**, **issuer/audience nào được phép**, và **request nào được cấp quyền sau khi token hợp lệ**. `issuer-uri`, `jwk-set-uri` và khóa được quản lý giải quyết phần đầu; các validators và chính sách Spring Security giải quyết những phần còn lại.
