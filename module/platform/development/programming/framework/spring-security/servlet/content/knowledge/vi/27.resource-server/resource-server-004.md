# JWT trong Spring Security Resource Server: chữ ký, issuer, thời hạn và audience

> **Phạm vi:** Spring Security **Servlet** 6.x (thường dùng Spring Boot 3.x, Java 17+), ứng dụng đóng vai trò **OAuth 2.0 Resource Server** nhận access token JWT bằng HTTP `Authorization: Bearer …`. Bài học tập trung vào kiểm tra chữ ký và bốn giới hạn tin cậy: **issuer (`iss`), thời gian (`exp`/`nbf`) và audience (`aud`)**. Đây là cơ chế xác thực access token ở API; không mặc nhiên áp dụng y nguyên cho ID token, opaque token hoặc Spring WebFlux.

## 1. Vì sao chữ ký hợp lệ vẫn chưa đủ?

Giả sử hệ thống có hai API: `orders-api` và `payments-api`, đều tin cậy cùng máy chủ phát hành token. Một kẻ có access token hợp lệ để gọi `orders-api` không nhất thiết được dùng token ấy để gọi `payments-api`, kể cả khi chữ ký đúng. Tương tự, token được phát hành bởi một hệ thống khác, token đã hết hạn hoặc token chưa đến thời điểm hiệu lực đều phải bị từ chối.

Một Resource Server cần đặt bốn câu hỏi độc lập:

1. **Chữ ký:** JWT có thật sự được ký bằng khóa được tin cậy cho cơ chế và thuật toán đã cấu hình không?
2. **Issuer:** Ai phát hành token, và `iss` có **khớp chính xác** issuer được tin cậy không?
3. **Thời hạn:** Token có nằm trong khoảng thời gian chấp nhận được, đặc biệt theo `exp` và `nbf` không?
4. **Audience:** Token có được phát hành **cho chính API này** không, hay được định hướng cho API/client khác?

Sau đó còn các quyết định riêng: scope/role, quyền truy cập tài nguyên, tenant, token type, revocation và chính sách ứng dụng. **JWT pass validation không tự đồng nghĩa người dùng được phép làm mọi hành động.**

## 2. JWT là gì, và đâu là bằng chứng đáng tin?

JWT (JSON Web Token) là định dạng mang các claim dưới dạng JSON. Trường hợp access token thường gặp là **signed JWT (JWS)** gồm ba phần, nối bằng dấu chấm:

~~~text
base64url(JWS protected header)
  .
base64url(JWT claims payload)
  .
base64url(signature)
~~~

Ví dụ header và payload **minh họa**, không phải token thực để copy dùng:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-2026-01"
}
~~~

~~~json
{
  "iss": "https://identity.example.test/realms/acme",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893459600,
  "scope": "orders.read orders.write"
}
~~~

- `alg`: thuật toán ký mà JWS khai báo; backend phải **giới hạn thuật toán được tin cậy** và xác minh chữ ký thật, không chỉ tin chuỗi `alg`.
- `kid`: gợi ý chọn khóa xác minh trong bộ khóa mà backend **đã tin cậy**. `kid` không phải quyền cho client chỉ định một server khóa bất kỳ.
- `iss`: issuer, thường là URL định danh authorization server.
- `sub`: subject mà issuer gán; không phải bằng chứng về quyền truy cập khi đứng một mình.
- `aud`: tập các audience mà token dành cho; Resource Server kiểm tra sự hiện diện của audience API.
- `iat`: thời điểm phát hành (issued at). Nó **không thay thế** `exp` và không bảo đảm tự động chặn token quá cũ.
- `nbf`: token không được dùng trước thời điểm này (not before), nếu được phát hành.
- `exp`: thời điểm hết hạn (expiration).
- `scope` hoặc `scp`: quyền mà issuer cấp, sau khi token đã vượt qua các kiểm tra tin cậy.

**Base64URL không phải mã hóa bảo mật.** Ai có JWT thường có thể giải mã header và payload để đọc claim. Chữ ký bảo vệ **tính toàn vẹn và nguồn phát hành**, không che giấu dữ liệu. Không đưa mật khẩu, session secret hoặc dữ liệu nhạy cảm không cần thiết vào payload. JWT mã hóa kiểu JWE là cơ chế khác, và Spring Resource Server theo cấu hình signed JWT thông thường không tự giải mã JWE.

### Nhìn nhận JWT như một vật mang quyền

Sở hữu JWT Bearer thường đủ để gọi API trong thời gian token còn hợp lệ và có quyền phù hợp. Vì vậy phải dùng HTTPS, không đưa token vào query string, tránh log nguyên `Authorization` và không lưu token ở vị trí dễ bị lộ. JWT do client tự sửa claim `scope`/`aud` rồi encode lại sẽ **không còn chữ ký hợp lệ** nếu server thực sự xác minh đúng khóa.

## 3. Spring Security Servlet xử lý Bearer JWT theo luồng nào?

Cấu hình chính là `oauth2ResourceServer(oauth2 -> oauth2.jwt(…))`. Khi request đến endpoint được bảo vệ:

~~~text
Client
  |
  | Authorization: Bearer <JWT>
  v
Servlet FilterChainProxy / SecurityFilterChain
  |
  v
BearerTokenAuthenticationFilter
  |
  v
AuthenticationManager / JwtAuthenticationProvider
  |
  v
JwtDecoder (thường NimbusJwtDecoder)
  |   1. Parse JWS
  |   2. Xác minh chữ ký bằng khóa tin cậy và alg cho phép
  |   3. Chạy OAuth2TokenValidator<Jwt>:
  |      issuer, exp/nbf, audience, chính sách bổ sung
  |
  +--> Không hợp lệ -> authentication thất bại, thường HTTP 401
  |
  +--> Hợp lệ -> JwtAuthenticationToken
                       |
                       v
                  Authorization:
                  scope / authority / business rules
                       |
                       +--> Thiếu quyền -> thường HTTP 403
                       +--> Đủ quyền -> controller
~~~

Các tên lớp này thuộc **Servlet Resource Server**. `JwtDecoder.decode(token)` phải tạo ra đối tượng `Jwt` đã vượt qua xác minh chữ ký và bộ validator tương ứng; **controller không tự Base64-decode để xác thực token**.

`JwtAuthenticationConverter` thường ánh xạ các scope trong JWT thành authorities có tiền tố `SCOPE_` (ví dụ scope `orders.read` thành `SCOPE_orders.read`). Đây là bước phục vụ **authorization**, khác việc xác minh chữ ký, issuer, thời hạn và audience.

### HTTP status có ý nghĩa gì?

- Request endpoint bảo vệ **không có Bearer token**: thường **401 Unauthorized**, kèm `WWW-Authenticate: Bearer`.
- JWT sai chữ ký, issuer, audience hoặc hết hạn: authentication thất bại, thường **401**, có thể có `error="invalid_token"`.
- JWT hợp lệ nhưng thiếu authority/role/permission: thường **403 Forbidden**.
- Controller tự từ chối theo nghiệp vụ: có thể có status khác, độc lập với việc JWT đã pass.

Không dựa duy nhất vào status để kết luận lỗi cụ thể: API gateway, reverse proxy, custom entry point và nhiều security chains có thể thay đổi response.

## 4. Chữ ký JWT: tin khóa nào và thuật toán nào?

### 4.1. Chữ ký bất đối xứng và JWKS

Một authorization server thường dùng private key để ký JWS `RS256`, còn các Resource Server dùng public key tương ứng để xác minh. Public keys có thể được công bố qua **JSON Web Key Set (JWKS)** tại URI do hệ thống cấu hình:

~~~text
Trusted authorization server
   |
   +-- Private key: ký access token
   |
   +-- HTTPS JWKS endpoint: công bố public keys, kèm kid
                                      |
                                      v
                          Trusted JwtDecoder
                          + kiểm tra alg
                          + chọn khóa theo kid
                          + xác minh chữ ký
~~~

Điểm cốt lõi:

- **JWKS URL là cấu hình tin cậy của Resource Server**, không tự lấy từ một URL tùy ý trong token chưa xác thực.
- `kid` chỉ giúp tìm khóa **trong bộ khóa tin cậy**. Nó không thể thay thế xác minh chữ ký.
- `RS256` sử dụng RSA với SHA-256. Thuật toán của token phải nằm trong tập thuật toán decoder cho phép. Không chấp nhận `alg=none` hoặc tự động tin mọi thuật toán client khai báo.
- Key rotation có thể làm xuất hiện một `kid` mới. Authorization server cần công bố khóa mới đúng thời điểm; Resource Server cần có khả năng cập nhật/cache JWKS phù hợp. Token cũ còn hiệu lực có thể vẫn cần public key cũ trong giai đoạn chuyển đổi.
- Chữ ký JWS xác minh thành công chỉ cho biết token được ký bởi **một khóa đang tin cậy**; vẫn phải xét issuer, audience, thời hạn và token type.

### 4.2. Vì sao phải giới hạn thuật toán?

Không được lấy giá trị `alg` do token gửi lên rồi tự lựa chọn một implementation không kiểm soát. Điều đó từng dẫn tới nhóm lỗi **algorithm confusion**: hệ thống nhầm lẫn khóa đối xứng/bất đối xứng, hoặc bỏ kiểm tra khi `alg=none`. Với `NimbusJwtDecoder`, hãy cấu hình tập thuật toán được chấp nhận dựa trên **hợp đồng của issuer**, chẳng hạn chỉ `RS256`, và quản lý các khóa tương ứng. Nếu issuer đổi từ RS256 sang ES256, thực hiện thay đổi cấu hình, bộ khóa và kiểm thử có chủ đích.

### 4.3. Với HS256 thì sao?

HS256 dùng shared secret. Nếu nhiều Resource Server cùng biết secret để xác minh, về nguyên tắc chúng cũng có khả năng **ký** JWT bằng secret đó. Với hệ thống nhiều dịch vụ, thuật toán bất đối xứng như RS256/ES256 thường tạo ranh giới rõ hơn: authorization server giữ private key, API chỉ giữ public key. Không dùng mật khẩu ngắn làm HMAC secret.

## 5. Kiểm tra `iss`: ai thực sự phát hành token?

`iss` (issuer) là định danh của máy chủ phát hành JWT. Ví dụ:

~~~json
{
  "iss": "https://identity.example.test/realms/acme"
}
~~~

Resource Server phải so sánh với issuer đã cấu hình tin cậy. **Đừng suy ra issuer từ chính JWT rồi tin issuer đó.** Nếu chấp nhận bất kỳ `iss` nào mà client tự nêu, một authorization server khác có thể cấp token nhằm truy cập API của bạn.

Trong Spring Boot, cấu hình khai báo thường dùng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/acme
~~~

Khi dùng auto-configuration `issuer-uri` với metadata issuer tương thích, Spring có thể dùng metadata của authorization server để tìm JWKS endpoint và tạo decoder có **issuer validation** cùng các kiểm tra thời gian mặc định. Điều này đòi hỏi issuer hỗ trợ endpoint metadata phù hợp; độ sẵn sàng của issuer có thể ảnh hưởng khởi động khi decoder phải truy xuất metadata.

Nếu biết trước JWKS URI, có thể khai báo cả hai:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/acme
          jwk-set-uri: https://identity.example.test/realms/acme/protocol/openid-connect/certs
~~~

`jwk-set-uri` tường minh tránh phụ thuộc bước **tự discovery metadata** khi khởi động trong các cấu hình tương ứng, còn `issuer-uri` vẫn là cơ sở kiểm tra `iss`. Khi runtime cần xác minh token mới, JWKS endpoint vẫn phải sẵn có hoặc khóa cần thiết phải còn trong cache.

**Các lỗi issuer thường gặp:**

- Sai scheme `http`/`https`, sai path/realm hoặc dấu `/` cuối so với chuỗi do issuer thực phát hành.
- Token được phát hành bởi realm/tenant khác dù cùng domain.
- Trong dev dùng issuer hostname nội bộ nhưng production token chứa public URL khác.
- Custom `JwtDecoder` bean đã thay thế auto-configuration nhưng quên đăng ký `JwtIssuerValidator`.

Issuer phải được quản lý từ cấu hình server hoặc tenant routing **được chứng thực**, không phải một claim chưa được xác minh.

## 6. Thời hạn: `exp`, `nbf`, `iat` và clock skew

JWT dùng **NumericDate**: số giây từ Unix epoch UTC; không phải milliseconds và không phải giờ địa phương.

| Claim | Nghĩa | Kiểm tra |
| --- | --- | --- |
| `exp` | Thời điểm token hết hạn. | Token không được chấp nhận sau khi hết hạn (có thể áp dụng clock skew cho phép). |
| `nbf` | Không có hiệu lực trước thời điểm này. | Từ chối nếu đồng hồ hiện tại vẫn trước `nbf` ngoài dung sai. |
| `iat` | Thời điểm token được phát hành. | Hữu ích cho audit hoặc quy tắc tuổi tối đa nếu ứng dụng tự định nghĩa; không thay `exp`. |

Ví dụ (thời điểm mang tính minh họa):

~~~json
{
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893459600
}
~~~

Một access token quá hạn không trở nên hợp lệ chỉ vì chữ ký vẫn đúng. Validator thời gian ở Spring Security xử lý `exp` và `nbf` theo clock, thường có **clock skew** mặc định để dung sai chênh lệch đồng hồ giữa issuer và resource server. Không cấu hình clock skew rất lớn chỉ để chữa lỗi token hết hạn: hãy đồng bộ thời gian máy chủ, dùng NTP và thiết kế lifetime phù hợp.

### `exp` vắng mặt có được mặc nhiên chấp nhận?

Cần phân biệt **kiểm tra một claim nếu xuất hiện** với **bắt buộc claim đó phải có**. Tùy validator và profile token, timestamp validator có thể không mặc nhiên yêu cầu token chứa `exp`. Nếu sản phẩm định nghĩa mọi access token đều phải có expiration, hãy **bổ sung validator bắt buộc `exp` hiện diện**; ví dụ ở mục 9 thực hiện điều này.

### Còn `iat` và giới hạn tuổi token?

Có `exp` không có nghĩa mặc nhiên hạn chế token quá dài theo chính sách nội bộ. Một token có `exp` sau nhiều năm có thể vượt quá kỳ vọng. Nếu cần TTL tối đa, có thể kiểm tra thêm `iat`/`exp` và khoảng cách giữa chúng với ngưỡng chính sách, đồng thời xử lý clock skew. Đây là quy tắc bổ sung, không tự suy ra từ chữ ký hoặc `JwtTimestampValidator`.

### Vì sao logout không lập tức làm JWT hết hiệu lực?

JWT tự chứa thường có thể được xác minh offline tới `exp`. Resource Server không mặc nhiên tra cơ sở dữ liệu để biết user vừa logout hoặc token bị revoke. Nếu nghiệp vụ yêu cầu thu hồi ngay, cần cơ chế riêng như token lifetime ngắn, denylist theo `jti`, introspection/opaque token, hoặc một lớp trạng thái phiên được thiết kế có cân nhắc. **Signature + exp không đồng nghĩa revocation**.

## 7. Kiểm tra `aud`: token này dành cho API nào?

`aud` (audience) chỉ các đối tượng tiếp nhận được token nhắm đến. Claim có thể được biểu diễn dạng chuỗi hoặc mảng theo JWT; Spring Security `Jwt.getAudience()` cung cấp danh sách để ứng dụng kiểm tra.

~~~json
{
  "aud": ["orders-api", "account-api"]
}
~~~

Nếu backend của bạn là `orders-api`, chính sách tối thiểu là **danh sách audience phải chứa chính xác `orders-api`**. Token chỉ dành cho `payments-api` phải bị loại ngay cả khi issuer, chữ ký, exp đều hợp lệ.

Tại sao quan trọng? Hai API tin cùng issuer/key có thể cùng xác minh được token. Không kiểm tra aud sẽ tạo nguy cơ **token substitution/cross-service token replay**: token được cấp cho một API bị đưa sang API khác.

### Audience khác scope và client ID

- **`aud`** trả lời “token được phép gửi đến Resource Server nào?”.
- **`scope`/`scp`** trả lời “token được cấp khả năng/thao tác gì?” trong ngữ cảnh các policy khác.
- **`client_id`/`azp`** có thể nhận diện client đã xin token hoặc bên được ủy quyền, tùy authorization server/profile; không tự thay `aud`.
- **`sub`** là subject; không thay audience, cũng không tự chứng minh authority.

Một token có `aud=["orders-api"]` nhưng **không có** `scope=orders.read` có thể pass bước JWT validation nhưng **không được gọi** endpoint yêu cầu `SCOPE_orders.read`. Ngược lại, token có scope `orders.read` nhưng audience `payments-api` phải bị chặn ở **authentication/token validation** trước khi xét scope.

### Có nên cho phép mọi audience của issuer?

Không. Chỉ vì token do issuer được tin cậy ký không có nghĩa nó phù hợp với mọi Resource Server. Mỗi API cần biết audience định danh của mình; khi hỗ trợ nhiều audience, hãy có allowlist có chủ đích và test từng trường hợp, không so khớp mơ hồ bằng `startsWith` hoặc substring.

## 8. Cấu hình Java 17+ cho Spring Boot 3: Resource Server JWT

Ứng dụng mẫu nhận Bearer token qua `Authorization`, dùng một issuer HTTPS và JWKS endpoint được quản lý ở phía server. Chọn **RS256**, bắt buộc `exp` và audience `orders-api`. Các file nằm trong package `com.example.orderssecurity` của một Spring Boot app.

Đây là ví dụ tích hợp Spring Boot: mã Java có thể biên dịch trong **dự án đã cài dependency** và các địa chỉ IdP phải được thay bằng issuer thật. Không thể chạy chỉ bằng `javac` khi thiếu thư viện Spring.

### 8.1. Dependencies

Trong một Spring Boot Gradle project đã cấu hình plugin Java và Spring Boot, các dependency chính:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Resource Server starter kéo theo phần JWT/Jose cần thiết cho cấu hình thông thường. Để phiên bản dependency nhất quán, để Spring Boot quản lý phiên bản qua dependency management/BOM của project.

### 8.2. application.yml

**`src/main/resources/application.yml`:**

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/acme
          jwk-set-uri: https://identity.example.test/realms/acme/protocol/openid-connect/certs

app:
  security:
    jwt:
      audience: orders-api
~~~

Các URL `example.test` chỉ là **giá trị minh họa**, không phải identity provider đang hoạt động. Phải thay bằng issuer và JWKS URI thực, tin cậy, dùng HTTPS hợp lệ.

### 8.3. Lớp cấu hình SecurityFilterChain và JwtDecoder

**`src/main/java/com/example/orderssecurity/JwtSecurityConfig.java`:**

~~~java
package com.example.orderssecurity;

import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class JwtSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            // Chỉ dùng lựa chọn này cho API thuần Bearer, không dùng
            // session cookie để xác thực request thay đổi trạng thái.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
                    String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
                    String jwkSetUri,
            @Value("${app.security.jwt.audience}")
                    String requiredAudience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        decoder.setJwtValidator(validationPolicy(issuer, requiredAudience));
        return decoder;
    }

    // Package-private để bài test trong cùng package có thể tái sử dụng.
    static OAuth2TokenValidator<Jwt> validationPolicy(
            String issuer,
            String requiredAudience) {

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            List<String> aud = jwt.getAudience();
            if (aud != null && aud.contains(requiredAudience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token",
                    "JWT audience is not accepted", null));
        };

        OAuth2TokenValidator<Jwt> expirationRequired = jwt -> {
            if (jwt.getExpiresAt() != null) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token",
                    "JWT exp claim is required", null));
        };

        return new DelegatingOAuth2TokenValidator<>(
            issuerAndTime, audience, expirationRequired);
    }
}
~~~

**Giải thích các quyết định quan trọng:**

1. `NimbusJwtDecoder.withJwkSetUri(…)` dùng **JWKS cố định được cấu hình** để xác minh signature; `jwsAlgorithm(RS256)` giới hạn thuật toán được chấp nhận.
2. `JwtValidators.createDefaultWithIssuer(issuer)` tạo các kiểm tra mặc định có **issuer validation và thời gian**. Trong ví dụ, validation policy còn kiểm aud và bắt buộc claim exp hiện diện.
3. `DelegatingOAuth2TokenValidator` yêu cầu **mọi validator** đều thành công, không phải chỉ cần một trong ba.
4. `JwtDecoder` là bean do ứng dụng tự khai báo. Điều này **thay thế decoder được Spring Boot tự cấu hình**; vì vậy phải chủ động giữ đủ kiểm tra mà security policy yêu cầu. Chỉ thêm audience validator và quên issuer/timestamp là một lỗi nghiêm trọng.
5. Rule `hasAuthority("SCOPE_orders.read")` là **authorization** sau JWT validation. Nếu issuer dùng tên claim scope khác mặc định, cần cấu hình `JwtAuthenticationConverter` đúng hợp đồng, không sửa audience để “có quyền”.
6. Ví dụ cấu hình CSRF disabled và session stateless **chỉ đúng khi API thuần Bearer**, không xác thực request bằng cookie trình duyệt. Nếu cùng ứng dụng phục vụ form login/cookie, cần thiết kế chain/CSRF phù hợp thay vì tắt trên mọi endpoint.

Nếu không cần audience bắt buộc hoặc policy riêng, Spring Boot có thể tự cấu hình decoder từ `issuer-uri` mà không cần bean này. Nhưng mục tiêu bài học là **bắt buộc aud và exp**, nên ví dụ khai báo policy tường minh.

### 8.4. Controller mẫu

**`src/main/java/com/example/orderssecurity/OrdersApplication.java`:**

~~~java
package com.example.orderssecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/orderssecurity/OrdersController.java`:**

~~~java
package com.example.orderssecurity;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {

    @GetMapping("/api/public")
    public Map<String, String> status() {
        return Map.of("status", "public");
    }

    @GetMapping("/api/orders")
    public Map<String, String> list() {
        return Map.of("result", "orders visible");
    }
}
~~~

`GET /api/public` không bắt buộc token; `GET /api/orders` yêu cầu JWT hợp lệ **và** authority `SCOPE_orders.read`. Response JSON minh họa khi đủ quyền:

~~~json
{"result":"orders visible"}
~~~

Đây là controller tối giản để thấy ranh giới; dữ liệu thật, permission theo tenant và object-level authorization phải được xây dựng riêng.

### 8.5. Gọi API từ HTTP client

Với token do issuer thật cấp (ký đúng khóa, đúng iss/aud/exp/scope):

~~~bash
curl -i "http://localhost:8080/api/orders" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
~~~

Dấu `<ACCESS_TOKEN>` là placeholder để người học thay thủ công trong terminal, **không đưa vào source code, repository hoặc log**. Đối với PowerShell, có thể đặt token trong biến môi trường/process an toàn, rồi gửi với `curl.exe` hoặc PowerShell `Invoke-WebRequest`; ví dụ trên dùng cú pháp shell Unix.

Dự án Gradle có plugin Spring Boot có thể chạy:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Khi dùng URL `example.test` chưa tồn tại, Bearer request không xác minh được do không thể lấy bộ khóa JWKS. Muốn chạy end-to-end phải có authorization server thật hoặc mock issuer/JWKS trong môi trường test.

## 9. Test JWT validation bằng khóa RSA tự sinh: không cần IdP thật

Để kiểm tra bốn ranh giới tin cậy một cách **độc lập với network**, có thể ký JWT trong test bằng RSA private key tạm thời, đưa RSA public key vào `NimbusJwtDecoder.withPublicKey(…)`, rồi dùng cùng `validationPolicy` ở mục 8. Điều này kiểm chứng signature và claim validator thực sự, khác với một test chỉ mock đối tượng `Jwt`.

**`src/test/java/com/example/orderssecurity/JwtValidationPolicyTest.java`:**

~~~java
package com.example.orderssecurity;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import java.util.List;

import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class JwtValidationPolicyTest {

    private static final String ISSUER =
        "https://identity.example.test/realms/acme";
    private static final String AUDIENCE = "orders-api";

    private KeyPair trusted;
    private NimbusJwtDecoder decoder;

    @BeforeEach
    void init() throws Exception {
        trusted = newKeyPair();

        decoder = NimbusJwtDecoder
            .withPublicKey((RSAPublicKey) trusted.getPublic())
            .build();

        decoder.setJwtValidator(
            JwtSecurityConfig.validationPolicy(ISSUER, AUDIENCE));
    }

    @Test
    void acceptsTrustedSignatureIssuerTimeAndAudience() throws Exception {
        String token = sign(trusted, ISSUER, List.of(AUDIENCE),
            Instant.now().plusSeconds(300));

        assertDoesNotThrow(() -> decoder.decode(token));
    }

    @Test
    void rejectsSignatureFromAnotherKey() throws Exception {
        KeyPair attackerKey = newKeyPair();

        String token = sign(attackerKey, ISSUER, List.of(AUDIENCE),
            Instant.now().plusSeconds(300));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void rejectsWrongIssuer() throws Exception {
        String token = sign(trusted, "https://other-issuer.example.test",
            List.of(AUDIENCE), Instant.now().plusSeconds(300));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void rejectsExpiredToken() throws Exception {
        // Quá hạn 300 giây, vượt dung sai clock skew thường gặp.
        String token = sign(trusted, ISSUER, List.of(AUDIENCE),
            Instant.now().minusSeconds(300));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void rejectsWrongAudience() throws Exception {
        String token = sign(trusted, ISSUER, List.of("payments-api"),
            Instant.now().plusSeconds(300));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void rejectsMissingExpiration() throws Exception {
        String token = sign(trusted, ISSUER, List.of(AUDIENCE), null);

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    private static KeyPair newKeyPair() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    private static String sign(
            KeyPair keyPair,
            String issuer,
            List<String> audience,
            Instant expiration) throws Exception {

        JWTClaimsSet.Builder claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .subject("alice")
            .audience(audience)
            .issueTime(Date.from(Instant.now().minusSeconds(10)));

        if (expiration != null) {
            claims.expirationTime(Date.from(expiration));
        }

        SignedJWT signed = new SignedJWT(
            new JWSHeader.Builder(JWSAlgorithm.RS256)
                .type(JOSEObjectType.JWT)
                .keyID("test-rsa")
                .build(),
            claims.build()
        );

        signed.sign(new RSASSASigner(
            (RSAPrivateKey) keyPair.getPrivate()));
        return signed.serialize();
    }
}
~~~

Các điểm cần hiểu khi chạy test:

- Test sinh khóa RSA **chỉ trong bộ nhớ test**; không dùng khóa test làm khóa sản xuất.
- Trường hợp sai chữ ký ký bằng private key khác, decoder chỉ tin public key cặp `trusted` nên phải từ chối.
- Sai issuer và audience vẫn ký bởi **khóa đúng**; do đó chúng chứng minh signature valid chưa đủ.
- Exp đã quá hạn **300 giây**, để test không tình cờ pass vì default clock skew. Exp thiếu hẳn bị validator riêng từ chối.
- Token JWT trong test là JWS được tạo bởi `SignedJWT`, không phải chuỗi base64 tự ghép thiếu signature.

Chạy với dự án Gradle có dependencies ở mục 8:

~~~bash
./gradlew test
~~~

Hoặc Windows:

~~~powershell
.\gradlew.bat test
~~~

**Kỳ vọng:** sáu test pass khi API và dependency versions đúng với Spring Boot 3/Spring Security 6, không cần IdP mạng. Đây là test thực thi logic decoder và claim validation; nó không kiểm thử `jwk-set-uri` network, caching, rotation, HTTP security filter hay scope authorization.

### 9.1. Vì sao `MockMvc.with(jwt())` chưa kiểm tra chữ ký thật?

`spring-security-test` có request post-processor `jwt()` giúp tạo authentication cho test controller/security rule, nhưng **không nhất thiết gọi `JwtDecoder.decode`**. Nếu chỉ viết:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

thì đó là **fragment** của một MockMvc test đã có biến `mvc` và static imports phù hợp. Test này kiểm tra authorization/controller với authentication giả lập; **không chứng minh** một JWT chữ ký sai bị từ chối. Muốn kiểm tra signature, issuer, exp, aud phải gọi real decoder như ví dụ mục 9 hoặc chạy integration test đưa Bearer token thật qua filter cùng trusted key/JWKS test.

### 9.2. Những ca test bổ sung khi triển khai thật

- `nbf` nằm trong tương lai quá clock skew → bị từ chối.
- Token thiếu `aud` → bị từ chối; token có nhiều audience chứa `orders-api` → được chấp nhận nếu policy cho phép.
- Token alg không nằm trong allowlist, token bị sửa payload, token không có chữ ký, `kid` không tồn tại trong trusted JWKS → bị từ chối.
- Key rotation: token trước/sau khi đổi `kid` và thời gian public key cũ còn được dùng.
- JWT pass validation nhưng không có `SCOPE_orders.read` → bị 403 khi gọi endpoint.
- Request không có Bearer token → bị 401 ở endpoint bảo vệ.
- Tenant issuer khác hoặc token type khác (ví dụ ID token) → phải có policy riêng.

Không cần viết unit test lặp lại từng nhánh code nội bộ nếu các test acceptance/integration đã chứng minh ranh giới bảo mật; ưu tiên kiểm thử theo hành vi và dữ liệu tấn công có ý nghĩa.

## 10. Những lỗi phổ biến trong Spring Resource Server

| Triệu chứng | Nguyên nhân có thể | Cách xác minh và xử lý |
| --- | --- | --- |
| JWT giải Base64 được nhưng API trả 401 | Base64 decode không xác minh chữ ký, khóa/alg không được tin cậy. | Kiểm tra `JwtDecoder`, JWKS, `kid`, alg và chữ ký. |
| Token từ issuer khác được cấp nhưng bị 401 | `iss` không khớp issuer cấu hình. | So sánh đầy đủ scheme/host/path/trailing slash trong `iss`. |
| Hai API dùng chung IdP, token dùng được ở API sai | Không có audience validator. | Bắt buộc kiểm `aud` định danh từng API. |
| Token hết hạn 401 | `exp` ở quá khứ hoặc đồng hồ lệch quá dung sai. | Kiểm tra UTC/NumericDate, NTP, token lifetime; xin token mới. |
| Token chưa hiệu lực 401 | `nbf` trong tương lai. | Kiểm tra đồng hồ issuer và resource server; tránh clock skew quá lớn. |
| Token không có `exp` vẫn qua validator thời gian | Policy chưa bắt buộc claim hiện diện. | Thêm validator `exp required` nếu profile access token yêu cầu. |
| Startup lỗi khi dùng `issuer-uri` | Không lấy được discovery metadata hoặc issuer URI sai. | Kiểm tra metadata/JWKS/config; dùng `jwk-set-uri` tường minh khi thích hợp. |
| Sau key rotation token mới đột ngột 401 | JWKS chưa công bố key mới hoặc decoder chưa refresh cache. | Xem `kid`, JWKS, rollout và caching; không nới alg. |
| JWT pass nhưng endpoint 403 | Không có `SCOPE_…` hoặc policy quyền khác. | Kiểm tra authorities, `JwtAuthenticationConverter`, authorization rule. |
| Có custom `JwtDecoder` nhưng issuer/aud không được kiểm | Custom bean thay auto-config và chỉ xác minh chữ ký. | Gắn `JwtValidators.createDefaultWithIssuer` cùng audience/exp validators. |
| JWT dành cho frontend được chấp nhận như access token | Không xác thực audience/token type đúng hợp đồng. | Dùng access token đúng profile; kiểm aud, typ/token-use nếu issuer cần. |
| Token không còn hiệu lực sau logout vẫn dùng được | JWT tự chứa chưa có cơ chế thu hồi. | TTL ngắn, denylist/introspection theo yêu cầu rủi ro. |
| Browser báo CORS thay vì 401 | Response bị thiếu CORS headers, proxy hoặc filter khác. | Kiểm tra Network và cấu hình CORS; không đánh đồng với JWT validation. |

### Quy trình chẩn đoán an toàn

1. Xác định có Bearer token thật trong request hay không, nhưng **không ghi token đầy đủ vào log**.
2. Kiểm tra `JwtDecoder` nào đang được dùng: Boot auto-config hay bean tự khai báo?
3. Xác nhận issuer/JWKS URL và alg allowlist từ **cấu hình server**, không lấy từ input token.
4. Phân biệt lỗi signature, issuer, exp/nbf và audience bằng test decoder có dữ liệu tin cậy.
5. Nếu decoder thành công nhưng endpoint vẫn 403, kiểm tra authorities/scopes và method/URL matcher.
6. Kiểm tra gateway/proxy, clock đồng bộ, JWKS cache/rotation, nhiều security chains và môi trường triển khai.

Trong production, nên log lỗi theo **loại đã chuẩn hóa** (invalid signature, invalid issuer, expired, invalid audience) với ngữ cảnh request an toàn. Tránh log token, private keys, Authorization header, session cookies, user secrets hoặc exception text chứa dữ liệu do client kiểm soát.

## 11. Những hiểu nhầm nguy hiểm

**“JWT có ba phần và decode được thì hợp lệ.”** Không đúng: phải xác minh chữ ký bằng trusted key và chạy các validator phù hợp.

**“Chỉ cần chữ ký đúng.”** Không đủ: token sai issuer, hết hạn hoặc dành cho audience khác vẫn phải bị loại.

**“Issuer bất kỳ có JWKS HTTPS là tin được.”** Không đúng: HTTPS chỉ bảo vệ kết nối đến endpoint; chính backend phải cấu hình issuer tin cậy. Không để token chỉ định JWKS URL hoặc issuer tùy ý.

**“`aud` là scope.”** Không đúng: audience quyết định resource được nhận token, còn scope biểu diễn quyền cụ thể. Cần cả hai khi policy yêu cầu.

**“`sub` là tài khoản duy nhất toàn cầu.”** Không đúng: subject có ý nghĩa trong **ngữ cảnh issuer**; hai issuer có thể dùng cùng một `sub` cho hai người khác nhau.

**“Clock skew càng lớn càng an toàn.”** Không đúng: skew quá lớn kéo dài thời gian chấp nhận token hết hạn hoặc chưa có hiệu lực. Đồng bộ đồng hồ và cấu hình dung sai hẹp có chủ đích.

**“JWT có exp nên logout tự revoke.”** Không đúng: self-contained JWT thường còn hợp lệ tới exp nếu không có cơ chế thu hồi bổ sung.

**“`with(jwt())` chứng minh decoder xác minh chữ ký.”** Không đúng: test post-processor có thể bypass decoder. Phải test decoder thật hoặc HTTP Bearer integration path.

**“`issuer-uri` luôn tự kiểm audience.”** Không mặc nhiên. Issuer validation là một bước; audience của API cần được khai báo và kiểm tra theo policy khi chưa có cơ chế khác bảo đảm.

**“Mọi access token đều là JWT.”** Không đúng: authorization server có thể phát hành opaque token. `oauth2ResourceServer().opaqueToken(…)` dùng introspection, khác cơ chế JWS/JWKS.

## 12. Câu hỏi tự ôn tập

1. **Token ký đúng bằng private key tin cậy nhưng `iss` khác thì sao?** Từ chối vì issuer không thuộc danh sách tin cậy.
2. **Hai microservice cùng xác minh một JWT RS256, vì sao cần aud?** Ngăn JWT dành cho API này bị sử dụng tại API khác dù cùng issuer/key.
3. **`exp=1893459600` là giây hay millisecond?** NumericDate là giây Unix UTC.
4. **`nbf` khác `exp` ở đâu?** `nbf` là thời điểm sớm nhất có thể sử dụng; `exp` là thời điểm token hết hiệu lực.
5. **`iat` có thể thay `exp` không?** Không; nếu muốn hạn tuổi riêng phải có validator chính sách rõ ràng.
6. **Client gửi token header `alg=none` thì Resource Server làm gì?** Không tin header đó; phải từ chối JWT không được ký hợp lệ bằng thuật toán cho phép.
7. **Làm thế nào phân biệt 401 và 403 trong Resource Server?** 401 thường là chưa có/không hợp lệ authentication; 403 thường là đã xác thực nhưng không đủ quyền.
8. **Custom `JwtDecoder` bean có tự nhận issuer và audience validators từ `application.yml` không?** Không được mặc định giả định; phải cấu hình validator trên decoder theo hợp đồng, như ví dụ mục 8.
9. **Khi đổi khóa ký, tại sao JWT có thể đột ngột bị 401?** JWKS/caching/`kid` chưa thống nhất giữa issuer và Resource Server.
10. **Vì sao bài test decoder dùng RSA key pair mới mà vẫn có giá trị?** Nó kiểm chứng thật chữ ký và các claim validators mà không phụ thuộc IdP mạng; cần bổ sung integration test kiểm tra JWKS/HTTP thực tế.

**Ghi nhớ:** JWT validation của Servlet Resource Server phải gắn **khóa + thuật toán tin cậy** với **issuer được phép**, **khoảng thời gian hợp lệ**, và **audience đúng API**. Chỉ sau khi token vượt qua các bước này mới dùng scope/authority và chính sách nghiệp vụ để quyết định quyền truy cập.