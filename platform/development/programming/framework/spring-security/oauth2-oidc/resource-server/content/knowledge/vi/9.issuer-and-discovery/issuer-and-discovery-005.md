# Cấu hình trực tiếp jwk-set-uri và vẫn kiểm tra issuer

Khi triển khai **Spring Security OAuth 2.0 Resource Server** để nhận **JWT Bearer Access Token**, ứng dụng thường khai báo `issuer-uri` để Spring Security tìm metadata của Authorization Server và từ đó xác định nơi lấy public keys. Tuy nhiên, một số hệ thống đã biết sẵn địa chỉ **JWK Set URI**, hoặc muốn Resource Server khởi động mà không phải thực hiện bước **issuer discovery**. Khi đó có thể **cấu hình `jwk-set-uri` trực tiếp**.

Điểm quan trọng nhất của bài học là: **biết nơi tải khóa xác minh chữ ký không đồng nghĩa đã xác minh JWT được phát hành bởi issuer đúng**. Cấu hình phải giữ cả hai ràng buộc:

1. **Khóa ký đáng tin cậy**: lấy từ JWK Set URI đã được cấu hình.
2. **Issuer đáng tin cậy**: claim **`iss`** của JWT phải khớp chính xác với issuer mà Resource Server chấp nhận.

Ngoài ra, một API thực tế phải kiểm tra **audience**, thời hạn token và phạm vi quyền truy cập. Bài này giải thích rõ hai thuộc tính `issuer-uri` và `jwk-set-uri`, sự khác nhau giữa cấu hình Spring Boot và tự tạo **NimbusJwtDecoder**, cùng ví dụ triển khai, vận hành, kiểm thử.

Các ví dụ dùng Spring Boot 3.x, Spring Security 6.x, Java 17+ và Servlet API. URI trong bài dùng tên miền minh họa `example.test`, cần thay bằng issuer/JWKS thật khi triển khai.

## 1. Issuer và JWK Set URI giải quyết hai việc khác nhau

Giả sử ứng dụng có API quản lý đơn hàng, chỉ chấp nhận token của Authorization Server thuộc realm **demo**:

~~~text
Trusted issuer:
  https://login.example.test/realms/demo

Trusted JWKS endpoint:
  https://login.example.test/realms/demo/protocol/openid-connect/certs

Resource Server audience:
  orders-api
~~~

**Issuer URI** là định danh của bên phát hành token; **JWK Set URI** là địa chỉ HTTP(S) trả về các khóa dưới dạng JSON Web Key Set để Resource Server xác minh chữ ký của token. Một issuer có thể công bố JWK Set thông qua metadata OIDC/OAuth 2.0, nhưng issuer URI và JWK Set URI **không phải cùng một loại địa chỉ**.

| Thành phần | Câu hỏi mà nó giải quyết | Dữ liệu điển hình |
| --- | --- | --- |
| **`issuer-uri`** | “JWT được phát hành bởi đúng nhà phát hành tôi tin cậy chứ?” | `https://login.example.test/realms/demo` |
| **`jwk-set-uri`** | “Tôi lấy khóa công khai ở đâu để xác minh chữ ký JWT?” | `https://login.example.test/realms/demo/protocol/openid-connect/certs` |
| **`aud` validator** | “JWT có được phát hành cho API của tôi không?” | `orders-api` |
| **`exp` / `nbf` validators** | “Token đã có hiệu lực và chưa hết hạn chứ?” | NumericDate trong JWT |
| **Authorization rules** | “Token hợp lệ có quyền gọi API và truy cập bản ghi này không?” | `SCOPE_orders.read`, policy theo tenant |

Một JWT có chữ ký hợp lệ với public key trong JWK Set vẫn có thể bị từ chối nếu **`iss` sai**, **`aud` không chứa API**, đã hết hạn hoặc thiếu quyền. Bởi vậy, “tải khóa thành công” chỉ là một bước trong quá trình xác thực.

## 2. JWT, JOSE và JWK Set trong một request

JWT Access Token dạng JWS compact thường có ba phần:

~~~text
BASE64URL(header).BASE64URL(claims).BASE64URL(signature)
~~~

Header và payload minh họa:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-signing-2026-01",
  "typ": "at+jwt"
}
~~~

~~~json
{
  "iss": "https://login.example.test/realms/demo",
  "sub": "employee-123",
  "aud": ["orders-api"],
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000,
  "scope": "orders.read"
}
~~~

**JOSE Header** cung cấp thông tin như thuật toán `alg` và mã khóa `kid`. **Claims Set** chứa `iss`, `aud`, `exp` và các thông tin được phát hành. Đoạn JSON trên chỉ minh họa, **không phải token có chữ ký hợp lệ**.

Để kiểm tra token RS256:

1. Resource Server nhận header **`Authorization: Bearer <token>`**.
2. Spring Security chuyển token cho **`JwtDecoder`**, thường là **`NimbusJwtDecoder`**.
3. Decoder tìm public key thích hợp trong JWK Set. `kid` giúp chọn khóa, nhưng tự nó **không phải bằng chứng tin cậy**.
4. Decoder xác minh chữ ký bằng thuật toán đã được cấu hình cho phép.
5. Các validator kiểm tra **issuer, thời hạn, audience** và ràng buộc bổ sung.
6. Spring Security chuyển các scope thành authorities và đánh giá quyền truy cập endpoint.

JWT dạng JWS **được ký nhưng không mặc nhiên được mã hóa**: người nắm token có thể đọc payload bằng Base64url. Không đặt bí mật hoặc dữ liệu cá nhân không cần thiết vào token, và không ghi Bearer token vào URL, log hay thông báo lỗi.

## 3. Trường hợp chỉ cấu hình issuer-uri: discovery diễn ra như thế nào?

Cấu hình thường thấy trong `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
~~~

Với cấu hình issuer URI, Spring Security có thể khám phá **Authorization Server metadata** hoặc **OIDC Provider metadata** tại các well-known endpoints phù hợp. Tài liệu metadata chứa **`issuer`** và **`jwks_uri`**:

~~~json
{
  "issuer": "https://login.example.test/realms/demo",
  "jwks_uri": "https://login.example.test/realms/demo/protocol/openid-connect/certs"
}
~~~

Hệ thống sau đó biết địa chỉ chứa public keys để xác minh JWT. Quá trình khái quát:

~~~text
Resource Server
   |
   | issuer-uri đã cấu hình
   v
OIDC/OAuth Authorization Server metadata
   |  issuer = ...
   |  jwks_uri = ...
   v
JWK Set endpoint
   |
   | public keys
   v
JWT signature verification
   |
   v
Validators: iss, exp, nbf, aud...
~~~

Tùy phiên bản Spring Security và cách tạo decoder, việc discovery có thể diễn ra trong quá trình khởi tạo decoder, tại thời điểm sử dụng đầu tiên hoặc khi cần. Điều quan trọng về mặt kiến trúc là **nếu ứng dụng cần discovery lúc startup, việc issuer metadata endpoint không sẵn sàng có thể ảnh hưởng startup**. Với nơi đã biết trước JWK Set URI, cấu hình trực tiếp giúp loại bỏ nhu cầu **tìm JWK URI bằng discovery**, nhưng không loại bỏ mọi khả năng cần kết nối mạng để tải khóa.

Chỉ có `issuer-uri` thường đặt được quy tắc xác minh issuer theo cơ chế tự động của Spring Boot/Spring Security. Tuy nhiên, **audience không nên được giả định là đã được kiểm tra**, vì điều đó phụ thuộc thuộc tính hoặc validator cụ thể.

## 4. Cấu hình trực tiếp cả issuer-uri và jwk-set-uri

Đây là cách cấu hình cần nhớ cho một Spring Boot Resource Server mà issuer và JWKS endpoint đều được quản lý sẵn.

### 4.1. application.yml

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
          jwk-set-uri: https://login.example.test/realms/demo/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

Trong các phiên bản Spring Boot hỗ trợ **`audiences`**, cấu hình có ý nghĩa:

- **`issuer-uri`**: API chỉ chấp nhận JWT với claim `iss` khớp issuer đã khai báo.
- **`jwk-set-uri`**: decoder biết ngay nơi lấy các JWK; không cần gọi issuer metadata chỉ để tìm `jwks_uri`.
- **`audiences`**: JWT phải có audience chứa `orders-api`.
- Decoder vẫn kiểm tra chữ ký, thời hạn và các yêu cầu mặc định phù hợp.

Nếu Spring Boot đang sử dụng phiên bản không hỗ trợ `audiences`, phải thêm **audience validator** thông qua `JwtDecoder` tùy biến; một key YAML không được binding sẽ không làm token an toàn hơn.

### 4.2. Khác biệt với cấu hình chỉ có jwk-set-uri

Hai cấu hình dưới đây **không tương đương** về ý nghĩa tin cậy.

**Cấu hình A — Có cả issuer và JWKS URI:**

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
          jwk-set-uri: https://login.example.test/realms/demo/protocol/openid-connect/certs
~~~

Khi để Spring Boot tự cấu hình Resource Server JWT theo hai thuộc tính này, issuer được dùng để **kiểm tra `iss`**, còn JWK Set URI dùng để lấy khóa.

**Cấu hình B — Chỉ có JWKS URI:**

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://login.example.test/realms/demo/protocol/openid-connect/certs
~~~

Decoder có nguồn public keys để kiểm tra chữ ký nhưng **không có issuer được yêu cầu từ cấu hình này**. Không nên kết luận nó sẽ tự áp quy tắc `iss` giống cấu hình A. Nếu chỉ khai báo `jwk-set-uri`, hãy thêm **validator issuer rõ ràng** bằng Java hoặc cấu hình khác tương đương.

Đây là lỗi dễ bị bỏ sót vì token thử nghiệm đúng issuer vẫn qua được, tạo cảm giác rằng issuer validation đã hoạt động.

### 4.3. Bảng so sánh

| Tiêu chí | Chỉ `issuer-uri` | Chỉ `jwk-set-uri` | Cả hai |
| --- | --- | --- | --- |
| Nơi lấy JWKS | Khám phá từ metadata issuer. | URI đã khai báo. | URI đã khai báo. |
| Cần issuer discovery để tìm JWKS | Có. | Không. | Không. |
| Kiểm tra `iss` theo cấu hình Boot mặc định | Có. | Không có issuer tin cậy được chỉ định. | Có. |
| Xác minh chữ ký | Có, bằng JWK được tìm thấy. | Có, bằng JWK ở URI được cấu hình. | Có, bằng JWK ở URI được cấu hình. |
| Kiểm tra `aud` dành cho API | Cần cấu hình/validator. | Cần cấu hình/validator. | Cần cấu hình/validator. |
| Khả năng JWKS endpoint cần truy cập khi xác minh | Có. | Có. | Có. |

**Kết luận kỹ thuật:** Khi muốn bỏ bước khám phá metadata nhưng vẫn kiểm tra issuer, cấu hình Spring Boot **`issuer-uri` + `jwk-set-uri`** là lựa chọn thẳng nhất. Việc cung cấp trực tiếp JWKS URI **không phải lý do để bỏ issuer validation**.

## 5. JWK Set có gì và vì sao phải chọn đúng nguồn khóa?

JWK Set là JSON object với trường **`keys`** chứa một hoặc nhiều JSON Web Keys. Ví dụ cho RSA public keys (các giá trị modulus đã được thay bằng placeholder):

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "rsa-signing-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "RSA_PUBLIC_MODULUS_BASE64URL",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "rsa-signing-2026-02",
      "use": "sig",
      "alg": "RS256",
      "n": "SECOND_RSA_PUBLIC_MODULUS_BASE64URL",
      "e": "AQAB"
    }
  ]
}
~~~

Trong đó:

- **`kty`** cho biết loại khóa, ví dụ RSA.
- **`kid`** phân biệt khóa ký, hữu ích khi rotation.
- **`n`**, **`e`** là tham số public key RSA.
- **`use: sig`** thể hiện khóa có mục đích sử dụng cho chữ ký.
- **`alg`** mô tả thuật toán tương ứng theo metadata; decoder phải có chính sách thuật toán tin cậy của riêng nó.

Giá trị `n` trong ví dụ không phải RSA modulus hợp lệ; tài liệu này không cung cấp khóa ký hoặc token thật.

Đối với chữ ký RSA, **Authorization Server giữ private key**, còn Resource Server tải **public key**. JWKS công khai không nên chứa tham số private key như `d`. Resource Server không cần giữ private signing key để xác minh token.

### 5.1. JWK endpoint đáng tin cậy là một ranh giới bảo mật

Khi API tải public key từ một JWKS URI, nó đang chấp nhận nguồn đó làm **nền tảng xác minh chữ ký**. Nếu nguồn khóa bị tráo, kẻ tấn công có thể đưa public key do họ kiểm soát và ký token bằng private key tương ứng.

Vì vậy:

1. Lấy JWKS URI từ **cấu hình quản lý đáng tin cậy**, không đọc tự do từ request.
2. Sử dụng **HTTPS** với xác thực TLS đúng.
3. Không tự động đi theo `jku` hoặc `x5u` do JWT header chưa xác minh đưa ra.
4. Không chọn JWKS URI dựa trên `iss` chưa xác minh nếu không có cơ chế **allowlist issuer** chặt chẽ.
5. Giới hạn thuật toán và loại khóa được chấp nhận theo hợp đồng với Authorization Server.
6. Không xử lý lỗi tải khóa bằng cách bỏ qua xác minh chữ ký.

**`kid` không phải secret và cũng không phải dấu chứng nhận issuer.** Nó chủ yếu giúp lựa chọn khóa bên trong **JWKS đã được Resource Server tin cậy**.

## 6. Kết hợp JWKS URI trực tiếp với NimbusJwtDecoder

Cấu hình tự động của Spring Boot đủ cho nhiều ứng dụng. Khi cần kiểm soát validator, thuật toán hoặc cache, có thể tự tạo một **`JwtDecoder`**.

### 6.1. Cấu hình bằng Java

Ví dụ sau xây dựng decoder từ JWKS URI nhưng **đặt issuer validator riêng**, đồng thời kiểm tra audience:

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
public class JwtDecoderConfig {

    private static final String TRUSTED_ISSUER =
        "https://login.example.test/realms/demo";

    private static final String TRUSTED_JWKS =
        "https://login.example.test/realms/demo/protocol/openid-connect/certs";

    private static final String API_AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(TRUSTED_JWKS)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(API_AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "JWT audience is not accepted",
                    null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(TRUSTED_ISSUER),
                audienceValidator));

        return decoder;
    }
}
~~~

Các điểm then chốt:

- **`withJwkSetUri(TRUSTED_JWKS)`** xác định nguồn khóa; bản thân nó **không xác định issuer hợp lệ**.
- **`jwsAlgorithm(SignatureAlgorithm.RS256)`** giới hạn thuật toán cho ví dụ Authorization Server ký bằng RS256. Nếu issuer dùng ES256/RS512 hoặc thuật toán khác, cần thỏa thuận và cấu hình tương ứng.
- **`JwtValidators.createDefaultWithIssuer(TRUSTED_ISSUER)`** bổ sung kiểm tra issuer và các validator mặc định về thời gian; không chỉ kiểm tra chữ ký.
- **`audienceValidator`** ngăn token dành cho API khác bị dùng tại `orders-api`.
- **`DelegatingOAuth2TokenValidator`** kết hợp các quy tắc. Khi gọi **`setJwtValidator`**, cần giữ các ràng buộc mặc định trong bộ mới, tránh vô tình bỏ `exp`, `nbf` hoặc `iss`.

Đây là **một phương án thay thế** cho việc để Spring Boot tự tạo decoder. Nếu định nghĩa bean **`JwtDecoder`**, Spring Boot thường nhường auto-configuration cho bean tùy chỉnh; khi ấy không nên giả định thuộc tính `audiences` từ YAML vẫn được áp vào bean đó. Những validator bắt buộc cần được đặt trong **decoder thật đang sử dụng**.

Trong production, nên nạp issuer, JWKS URI và audience từ cấu hình quản lý theo môi trường. Ví dụ đặt constant chỉ để dễ theo dõi luồng xử lý.

### 6.2. Sai lầm phổ biến: decoder có khóa nhưng không có issuer validator

Đoạn sau **chưa đủ** để xác thực một API tin cậy đúng một issuer:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    return NimbusJwtDecoder
        .withJwkSetUri("https://login.example.test/realms/demo/keys")
        .build();
}
~~~

Decoder có thể xác minh chữ ký bằng khóa tại endpoint được cung cấp, nhưng không thể suy ra chính sách issuer của API chỉ từ thông tin đó. Hãy thêm **`JwtValidators.createDefaultWithIssuer(...)`** và, khi cần, audience validator như ví dụ hoàn chỉnh phía trên.

### 6.3. Nếu chỉ muốn kiểm tra issuer, có phải tự viết lambda?

Không cần tự so chuỗi `jwt.getIssuer().toString()` trong mọi ứng dụng. Spring Security đã có **`JwtValidators.createDefaultWithIssuer(issuer)`** cho trường hợp issuer cụ thể. Dùng validator có sẵn giúp kết hợp đúng ngữ nghĩa với các kiểm tra mặc định.

Chỉ cần custom validator cho các điều kiện ngoài tập đó, ví dụ:

- Audience bắt buộc chứa `orders-api`.
- Claim `tenant_id` bắt buộc có giá trị thuộc miền được phép.
- Token profile hoặc claim riêng của Authorization Server.
- Chính sách thời gian bổ sung nghiêm ngặt hơn nếu nghiệp vụ yêu cầu.

Đừng nhầm **issuer validation** với **authorization**: một JWT có issuer đúng nhưng scope thiếu vẫn phải bị từ chối tại endpoint cần quyền.

## 7. Cấu hình SecurityFilterChain dùng decoder đó

Ví dụ API xác thực bằng Bearer header, không dùng session cookie:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Spring Security sẽ dùng `JwtDecoder` có sẵn từ cấu hình Boot hoặc bean được khai báo. Nếu API không có quyền **`SCOPE_orders.read`**, một token hợp lệ vẫn bị từ chối khi GET tài nguyên cần scope đó.

**Lưu ý kiến trúc:**

- **`STATELESS`** thích hợp với API xác thực mỗi request bằng Bearer Access Token.
- Tắt **CSRF** trong ví dụ chỉ áp dụng cho API thuần Bearer header. Nếu cùng ứng dụng có website đăng nhập bằng cookie/session, phải thiết kế các security chain và CSRF riêng.
- Spring Security thường ánh xạ claim `scope` hoặc `scp` thành authority có tiền tố **`SCOPE_`**. Custom roles/permissions cần converter hoặc policy riêng.
- Khi Authorization Server cấp Access Token cho nhiều API, kiểm tra **`aud`** ở decoder vẫn phải áp dụng cho mỗi API đích.

Một request hợp lệ có thể là:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_FOR_ORDERS_API
Accept: application/json
~~~

Trong thực tế, Access Token là credential nhạy cảm: không đưa token thật vào URL, tài liệu công khai, log hoặc response lỗi.

## 8. Issuer string: so khớp chính xác và những bẫy khó thấy

Claim `iss` của JWT thường là một chuỗi URI, ví dụ:

~~~json
{
  "iss": "https://login.example.test/realms/demo"
}
~~~

Nếu Resource Server cấu hình issuer khác, chẳng hạn:

~~~text
https://login.example.test/realms/demo/
~~~

thì sự khác nhau về dấu **/** cuối chuỗi có thể khiến issuer validator bác token. Không tự ý “chuẩn hóa” `iss` bằng cách cắt path, hạ chữ hoa của path hoặc thay hostname để ép khớp. **Issuer identifier là hợp đồng giữa Authorization Server và Resource Server**, cần lấy đúng giá trị mà nhà phát hành công bố.

### 8.1. Reverse proxy và URL nội bộ

Ví dụ Authorization Server ở sau reverse proxy có URL nội bộ:

~~~text
http://identity-service:8080/realms/demo
~~~

nhưng công bố issuer chính thức:

~~~text
https://login.example.test/realms/demo
~~~

Resource Server phải xác minh **`iss` theo issuer chính thức của token**. Nó có thể tải JWKS từ một URI nội bộ được quản lý chặt trong trường hợp kiến trúc yêu cầu, nhưng việc dùng một đường nội bộ để lấy khóa **không có nghĩa thay `iss` thành URL nội bộ**.

Ví dụ nếu JWKS được cung cấp qua mạng nội bộ có TLS phù hợp:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
          jwk-set-uri: https://identity-internal.example.test/realms/demo/certs
          audiences:
            - orders-api
~~~

Kiến trúc trên chỉ an toàn khi địa chỉ JWKS nội bộ là **nguồn khóa đã được kiểm soát và đúng với issuer**. Không xem bất kỳ địa chỉ nội bộ nào là tin cậy chỉ vì nằm trong mạng doanh nghiệp.

### 8.2. Môi trường phát triển, staging, production

Không nên dùng chung một issuer “ảo” cho mọi môi trường nếu Authorization Server thực tế phát hành token với các `iss` khác nhau. Ví dụ:

| Môi trường | Issuer | JWKS |
| --- | --- | --- |
| Dev | `https://login-dev.example.test/realms/demo` | Endpoint dev của issuer dev |
| Staging | `https://login-staging.example.test/realms/demo` | Endpoint staging |
| Production | `https://login.example.test/realms/demo` | Endpoint production |

Từng môi trường nên có cấu hình rõ và kiểm thử token do đúng issuer phát hành. Không đổi sang JWKS production chỉ để làm token ở dev “qua xác minh chữ ký”: issuer, audience, signing keys và ranh giới dữ liệu cần được tách theo kiến trúc tổ chức.

## 9. Audience và issuer không thể thay thế nhau

Giả sử Authorization Server phát hành JWT:

~~~json
{
  "iss": "https://login.example.test/realms/demo",
  "sub": "user-123",
  "aud": ["billing-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

Resource Server **`orders-api`** có cùng issuer với token và public key hợp lệ. Nhưng `aud` chỉ chứa **`billing-api`**, do đó **orders-api phải từ chối**. Không có ràng buộc audience, token dành cho một resource có thể bị sử dụng sai tại resource khác, kể cả khi cả hai cùng tin issuer.

Ngược lại, token có `aud: ["orders-api"]` nhưng `iss` là issuer lạ cũng phải bị từ chối. Các điều kiện là **độc lập và đồng thời bắt buộc theo chính sách**:

~~~text
Kết quả xác thực JWT thành công
       |
       +-- Chữ ký hợp lệ với khóa tin cậy
       +-- Thuật toán nằm trong danh sách cho phép
       +-- iss == trusted issuer
       +-- aud chứa orders-api
       +-- exp/nbf phù hợp
       +-- Token profile/type đáp ứng yêu cầu (nếu áp dụng)
       |
       v
Authorization: kiểm tra scope, quyền tenant và tài nguyên
~~~

**OIDC ID Token** thường có audience là client ID của ứng dụng đăng nhập, còn **OAuth Access Token** phải phù hợp API. Một JWT được ký hợp lệ cùng issuer **không tự biến ID Token thành Access Token**.

## 10. Khởi động, network và caching khi cung cấp jwk-set-uri trực tiếp

### 10.1. Không discovery không đồng nghĩa offline hoàn toàn

Nếu chỉ khai báo `issuer-uri`, Spring Security cần một cơ chế discovery để tìm JWKS endpoint. Khi khai báo trực tiếp `jwk-set-uri`, ứng dụng đã biết nơi tải khóa mà không cần tìm nó qua metadata.

Điều này có thể giảm phụ thuộc vào **discovery endpoint lúc khởi tạo**. Nhưng JWT vẫn cần public key:

- Nếu decoder chưa có/cached public key thích hợp, nó phải lấy thông tin từ JWKS endpoint.
- Nếu gặp một `kid` mới, decoder có thể cần làm mới JWKS tùy cache policy.
- Khi JWKS endpoint không sẵn sàng và decoder không có khóa xác minh thích hợp, không được xác thực token đó thành công.

**Không** nên dùng fallback “đọc claims nhưng bỏ chữ ký” khi nguồn khóa tạm thời mất kết nối.

### 10.2. Caching và rotation

Authorization Server có thể công bố nhiều JWK trong một khoảng thời gian để xoay khóa:

~~~text
T0: JWKS công bố key-A; Access Token được ký bằng key-A
T1: JWKS công bố key-A và key-B
T2: Token mới được ký bằng key-B; token key-A còn hiệu lực
T3: Token key-A cũ hết hạn hoặc được xử lý theo chính sách
T4: JWKS ngừng công bố key-A
~~~

Decoder và thư viện JOSE thường cache JWK Set để tránh tải lại trên từng request. Thời hạn cache và cơ chế refresh phụ thuộc phiên bản/cấu hình. Khi rotation, cần bảo đảm:

1. Public key mới được công bố trước hoặc kịp thời điểm dùng ký token mới.
2. Cache ở các Resource Server có thể cập nhật để nhận key mới.
3. Key cũ vẫn được duy trì trong thời gian phù hợp với các token còn hiệu lực, trừ trường hợp thu hồi khẩn cấp.
4. Token với key lạ phải bị từ chối khi không thể tìm khóa xác minh tin cậy.

### 10.3. Failure modes cần giám sát

| Sự cố | Biểu hiện | Hướng xử lý |
| --- | --- | --- |
| Discovery endpoint lỗi khi chỉ dùng issuer URI | Khởi tạo/khám phá metadata thất bại tùy thời điểm discovery. | Kiểm tra issuer URI, TLS, metadata; cân nhắc JWKS URI trực tiếp đã được quản lý. |
| JWKS endpoint không truy cập được khi cần key | Request JWT có thể nhận 401 hoặc lỗi xác thực tương ứng. | Kiểm tra kết nối, TLS, cache và độ sẵn sàng của endpoint; giữ nguyên xác minh chữ ký. |
| Issuer sai dấu slash hoặc realm | Chữ ký có thể đúng nhưng JWT bị bác. | So sánh `iss` do issuer công bố với cấu hình tin cậy. |
| JWKS chứa key mới nhưng cache chưa refresh | JWT mới có `kid` lạ bị từ chối. | Xem kế hoạch rotation, TTL/cache và lịch công bố khóa. |
| Token sai audience | JWT đã ký hợp lệ vẫn bị bác. | Kiểm tra audience của API và cấu hình cấp token. |
| Decoder custom ghi đè Boot auto-config | Validator issuer/audience bị mất nếu không đặt lại. | Kiểm tra đúng bean JwtDecoder đang được dùng. |
| Sai thuật toán hoặc loại key | JWT bị bác dù JWKS endpoint truy cập được. | Kiểm tra token profile, thuật toán và key type đã thỏa thuận. |

Theo dõi số lượng lỗi 401/403, nhóm lỗi đã chuẩn hóa và độ sẵn sàng của JWKS endpoint. Không ghi nguyên JWT, Authorization header, secret hoặc stack trace nhạy cảm vào log/metric.

## 11. Kiểm thử việc “vẫn kiểm tra issuer”

Đây là điểm cần xác minh đặc biệt nếu chuyển từ cấu hình discovery sang `jwk-set-uri` trực tiếp.

### 11.1. Ma trận kiểm thử

| Token gửi đến orders-api | Chữ ký / JWKS | Issuer | Audience | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| Token hợp lệ | Đúng key | Đúng | `orders-api` | Qua authentication; còn kiểm tra scope. |
| Token cùng key nhưng issuer khác | Đúng key | **Sai** | `orders-api` | **401** nếu API kiểm tra issuer. |
| Token đúng issuer nhưng audience khác | Đúng key | Đúng | **Sai** | **401** nếu API kiểm tra audience. |
| Token ký bằng private key lạ | **Sai** | Đúng | `orders-api` | **401**. |
| Token đã hết hạn | Đúng key | Đúng | `orders-api` | **401**. |
| Token hợp lệ nhưng thiếu `orders.read` | Đúng key | Đúng | `orders-api` | **403** tại GET cần scope đó. |
| Không có Bearer token | Không có | — | — | **401** ở endpoint bảo vệ. |

Phải có **test với issuer sai nhưng chữ ký đúng**. Nếu chỉ dùng chữ ký sai khi test 401, ta chưa chứng minh rằng issuer validator đang hoạt động: request có thể bị bác ở bước chữ ký trước khi kiểm tra `iss`.

### 11.2. Test authorization bằng MockMvc khác test decoder

Spring Security Test cung cấp `jwt()`:

~~~java
mockMvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Mẫu trên giúp thử authorization, vì `jwt()` tạo Authentication đã được xác thực cho request. **Nó không gửi JWT có chữ ký thật qua NimbusJwtDecoder**, nên không chứng minh rằng issuer/JWKS validation hoạt động. Đặt `iss` sai trong `jwt()` rồi thấy 200 không nhất thiết là lỗi của decoder; decoder không được gọi trong test đó.

Để kiểm tra validator thực sự:

- Dựng **RSA key pair chỉ dùng cho test**.
- Ký JWT bằng private key test.
- Đặt JWKS fixture trả public key test.
- Tạo decoder dùng `withJwkSetUri` trỏ đến JWKS cục bộ, có validator `createDefaultWithIssuer`.
- Thử JWT issuer đúng và JWT issuer sai **nhưng được ký bằng cùng private key test**.

### 11.3. Ví dụ test validator với RSA key test

Đoạn JUnit 5 dưới đây minh họa cách thử **issuer validator** với JWT ký thật. Nó dùng `withPublicKey` để tránh HTTP trong unit test, trong khi production dùng `withJwkSetUri`. Cơ chế kiểm tra `iss` bằng validator tương đương, nhưng **test này chưa xác minh việc tải JWKS qua HTTP**.

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TrustedIssuerDecoderTest {

    private static final String TRUSTED_ISSUER =
        "https://login.example.test/realms/demo";

    private KeyPair keyPair;
    private NimbusJwtDecoder decoder;

    @BeforeEach
    void initialize() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        keyPair = generator.generateKeyPair();

        decoder = NimbusJwtDecoder
            .withPublicKey((RSAPublicKey) keyPair.getPublic())
            .build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "Wrong audience", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(TRUSTED_ISSUER),
                audience));
    }

    private String signedJwt(String issuer) throws Exception {
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .subject("employee-123")
            .audience("orders-api")
            .issueTime(Date.from(Instant.now().minusSeconds(60)))
            .expirationTime(Date.from(Instant.now().plusSeconds(600)))
            .claim("scope", "orders.read")
            .build();

        SignedJWT jwt = new SignedJWT(
            new JWSHeader(JWSAlgorithm.RS256), claims);
        jwt.sign(new RSASSASigner(
            (RSAPrivateKey) keyPair.getPrivate()));
        return jwt.serialize();
    }

    @Test
    void correctIssuerIsAccepted() throws Exception {
        Jwt actual = decoder.decode(signedJwt(TRUSTED_ISSUER));
        assertEquals("employee-123", actual.getSubject());
    }

    @Test
    void wrongIssuerWithValidSignatureIsRejected() throws Exception {
        String token = signedJwt(
            "https://untrusted.example.test/realms/other");
        assertThrows(JwtException.class, () -> decoder.decode(token));
    }
}
~~~

**Vì sao test có ý nghĩa?** Cả hai JWT đều được ký bằng cùng private key, và decoder có đúng public key tương ứng. Vậy nếu token với issuer lạ bị bác, nguyên nhân liên quan tới **claim validation**, không chỉ là chữ ký sai.

Để test **chính xác cấu hình JWKS URI trực tiếp**, có thể mở một HTTP server test cục bộ cung cấp JWK Set với public key test, cấu hình `NimbusJwtDecoder.withJwkSetUri(localJwksUri)`, rồi chạy lại hai kịch bản tương tự. Khi đó cũng cần thử JWKS không có `kid` phù hợp, khóa bị thay đổi và endpoint gặp lỗi.

### 11.4. Thử đường đi HTTP thật

Một integration test với Resource Server phải gửi chuỗi JWT vào HTTP header:

~~~http
GET /api/orders/42 HTTP/1.1
Host: localhost:8080
Authorization: Bearer JWT_SIGNED_BY_TEST_KEY
~~~

Luồng test:

~~~text
JUnit/Test fixture
   |
   +-- private key test dùng ký JWT
   |
   +-- local JWKS endpoint công bố public key test
   |
   v
MockMvc / HTTP test gửi Authorization: Bearer ...
   |
   v
BearerTokenAuthenticationFilter
   |
   v
NimbusJwtDecoder.withJwkSetUri(local JWKS)
   |
   +-- xác minh chữ ký
   +-- validate issuer
   +-- validate audience, exp, nbf
   v
Authorization rule -> 200 / 401 / 403
~~~

Test cục bộ có ích vì tránh phụ thuộc mạng/Authorization Server production. Không dùng token thật hoặc private signing key thật trong test fixture. Nếu ứng dụng dùng nhiều issuer hoặc JWK Set đặc thù, thử thêm việc routing issuer theo allowlist, key selection và cache/rotation.

## 12. Nhiều issuer và những giới hạn của một jwk-set-uri

Một Resource Server có thể cần chấp nhận token từ nhiều tenant hoặc Authorization Server. Không nên giải quyết bằng cách chỉ trỏ đến một JWK Set rồi **bỏ kiểm tra `iss`** để “chấp nhận mọi tenant”.

Ví dụ:

~~~text
Tenant A: issuer https://login-a.example.test
          JWKS   https://login-a.example.test/keys

Tenant B: issuer https://login-b.example.test
          JWKS   https://login-b.example.test/keys
~~~

Cần cơ chế ánh xạ **issuer được phép → decoder/JWK source/validators tương ứng**. Trong Spring Security Servlet có các cơ chế như **JwtIssuerAuthenticationManagerResolver** cho một số mô hình multi-issuer, với điều kiện danh sách issuer tin cậy đã được quản lý rõ.

Một JWT chưa xác minh có thể cung cấp `iss` để **hỗ trợ chọn nhánh xác minh**, nhưng đó chỉ là thao tác **routing**. Nó không làm issuer thành tin cậy; resolver vẫn phải áp allowlist và decoder phải kiểm tra lại chữ ký và `iss` sau khi chọn nhánh.

~~~text
Bearer JWT
  |
  v
Đọc iss để xác định nhánh (chưa tin claim)
  |
  v
Issuer nằm trong allowlist?
  | Không                  | Có
  v                        v
 Từ chối             Chọn decoder tin cậy
                           |
                           v
                 Xác minh chữ ký + issuer
                           |
                           v
                   Audience + thời hạn
                           |
                           v
                      Authorization
~~~

Nếu issuer A và issuer B dùng claim `roles` với ngữ nghĩa khác nhau, API cũng cần policy/claim converter riêng. Không áp chung quyền chỉ vì token cùng có `roles: ["ADMIN"]`.

## 13. Cách xác định nguyên nhân khi cấu hình trực tiếp JWKS mà JWT bị 401

Khi JWT không được chấp nhận, hãy phân tích theo thứ tự từng ranh giới tin cậy:

| Triệu chứng | Cần xác nhận | Hướng điều chỉnh |
| --- | --- | --- |
| API vừa khởi động nhưng không lấy được key | DNS/TLS/firewall/JWKS URI đúng không? | Sửa kết nối hoặc URI đã được quản lý; không bỏ verification. |
| JWT có chữ ký đúng nhưng 401 | `iss` chính xác chưa? Có dấu slash thừa? `aud` đúng API? Token hết hạn? | So sánh claim đã được xác minh với cấu hình. |
| JWT issuer sai vẫn được API chấp nhận | Có thiếu issuer validator khi chỉ cấu hình JWKS URI không? | Bổ sung `issuer-uri` hoặc `createDefaultWithIssuer` vào decoder thực. |
| JWT issuer đúng nhưng JWKS mới có key khác | `kid`, key type, thuật toán và rotation có tương thích? | Kiểm tra JWKS, cache và chính sách ký token. |
| Token dành cho API khác vẫn được nhận | Có thiếu audience validation không? | Thêm `audiences` hoặc custom audience validator và test âm tính. |
| Token hợp lệ nhưng endpoint trả 403 | Authority/scope có đủ không? | Kiểm tra `scope`/`scp`, mapping `SCOPE_` và quyền tài nguyên. |
| Thêm bean JwtDecoder thì hành vi thay đổi | Auto-config của Boot có bị thay? | Đặt đầy đủ validators vào bean custom. |

**Không** khuyến khích copy Access Token thật vào công cụ giải mã trực tuyến hoặc log đầy đủ. Khi điều tra, dùng token giả/fixture, mã lỗi đã chuẩn hóa, trace ID do server sinh và thông tin cấu hình được phép hiển thị. JWKS public keys có thể công bố để xác minh chữ ký, nhưng tuyệt đối không ghi hay công khai private signing key.

### 13.1. Không lẫn lỗi 401 với 403

Với JWT Resource Server thông thường:

- **401 Unauthorized**: không có Bearer token hợp lệ, hoặc chữ ký, issuer, audience, thời hạn hay yêu cầu xác thực khác thất bại.
- **403 Forbidden**: token được xác thực nhưng không đủ scope/role hoặc quyền cần thiết cho endpoint.

Khi tùy biến response, giữ mã HTTP và header **`WWW-Authenticate: Bearer`** phù hợp; không phản chiếu JWT, exception thô hoặc chi tiết khóa ký vào phản hồi lỗi.

## 14. Những nhầm lẫn nên tránh

1. **“Đã cấu hình jwk-set-uri thì tự biết issuer.”** Sai: nguồn khóa chỉ xác minh chữ ký; issuer cần validator riêng hoặc cấu hình kết hợp.
2. **“Khai báo cả hai URI sẽ bắt buộc discovery.”** Khi biết JWKS URI trực tiếp, không cần khám phá metadata chỉ để tìm JWKS; việc lấy khóa vẫn có thể phụ thuộc mạng.
3. **“JWT ký đúng thì chắc chắn dành cho API.”** Cần audience validation; token có thể dành cho API khác.
4. **“JWKS có thể do client chọn từ token header.”** Đây là rủi ro thay nguồn khóa; URI phải đến từ cấu hình đáng tin cậy.
5. **“Issuer là host của JWKS.”** Issuer identifier có thể khác hostname/path của endpoint lấy khóa; kiểm tra `iss` theo hợp đồng phát hành token.
6. **“Chỉ cần scope là bỏ qua issuer.”** Scope mô tả quyền, không chứng minh token có nguồn phát hành tin cậy.
7. **“Đã thêm JwtDecoder bean thì Boot vẫn tự gắn mọi validator YAML.”** Bean custom có thể thay decoder auto-configured; cấu hình validator phải được kiểm tra trên decoder thật.
8. **“Một JWK key được dùng mãi không cần rotation.”** Khóa có thể thay; cần kế hoạch phân phối, cache và làm mới JWK Set.
9. **“Test MockMvc with jwt() chứng minh issuer validation.”** Helper tạo Authentication giả lập, không đi qua JWT signature verification.
10. **“JWKS lỗi thì có thể cho qua để tránh downtime.”** Một token không thể xác minh theo chính sách phải bị từ chối.

## 15. Quy trình áp dụng vào dự án

1. Xác nhận từ Authorization Server **issuer identifier chính thức** và **JWKS endpoint đáng tin cậy**, không tự suy từ token chưa xác minh.
2. Xác nhận token được cấp cho API với **audience** và **scope** đúng, thời hạn và thuật toán phù hợp.
3. Nếu dùng Boot auto-configuration, khai báo **cả `issuer-uri` và `jwk-set-uri`**; bổ sung **`audiences`** trên phiên bản hỗ trợ.
4. Nếu tự tạo **NimbusJwtDecoder.withJwkSetUri**, gọi **`setJwtValidator`** với **`JwtValidators.createDefaultWithIssuer`** và audience validator.
5. Cấu hình **SecurityFilterChain** cho Bearer authentication và authorization theo endpoint, method, tenant và tài nguyên.
6. Kiểm thử **issuer sai nhưng chữ ký đúng** để chứng minh issuer validation không bị bỏ quên; kiểm tra thêm sai audience, expiration, key lạ và scope thiếu.
7. Chuẩn bị vận hành **JWKS caching/rotation**, lỗi kết nối, TLS và logging an toàn; tuyệt đối không bỏ xác minh khi JWKS tạm thời không sẵn sàng.

**Ghi nhớ:** Với Spring Security Resource Server, cấu hình trực tiếp **`jwk-set-uri`** giải quyết nơi lấy public keys; giữ **`issuer-uri`** hoặc issuer validator tường minh bảo đảm JWT đến từ nhà phát hành được tin cậy. Hai điều kiện phải được kết hợp cùng **audience, thời hạn và authorization** để bảo vệ API đúng mục đích.

## Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html).
- [Spring Boot — OAuth 2.0 Resource Server configuration](https://docs.spring.io/spring-boot/reference/web/spring-security.html).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414).
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html).
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
