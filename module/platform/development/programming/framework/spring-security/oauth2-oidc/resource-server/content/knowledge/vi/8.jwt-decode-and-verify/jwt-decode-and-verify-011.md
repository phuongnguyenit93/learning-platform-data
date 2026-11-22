# Thay decoder mặc định mà vẫn giữ các kiểm tra cần thiết

Trong **Spring Security OAuth 2.0 Resource Server**, `JwtDecoder` là thành phần biến chuỗi Bearer JWT từ HTTP request thành đối tượng `Jwt` **đã được xác minh theo chính sách của API**. Nhiều ứng dụng chỉ cần khai báo `issuer-uri` để Spring Boot/Spring Security tự tạo decoder; nhưng khi cần đổi nguồn JWK, thuật toán ký, cấu hình HTTP client, thời gian chờ hoặc yêu cầu kiểm tra audience riêng, ta có thể cần **thay decoder mặc định**.

Điểm quan trọng nhất: **thay cách tạo decoder không được làm mất các kiểm tra vốn bảo vệ Resource Server**. Một JWT có thể giải mã được phần JSON mà vẫn không đáng tin; chữ ký có thể hợp lệ nhưng token hết hạn, sai issuer hoặc được cấp cho API khác. Decoder tùy chỉnh phải bảo toàn các điều kiện tin cậy có liên quan, rồi chỉ trả `Jwt` khi token đáp ứng hợp đồng của API.

Bài học thuộc phần **Giải mã và xác minh JWT** của module *Spring Security OAuth 2.0 OIDC Resource Server*, tập trung vào ứng dụng **Servlet/Spring MVC**, đồng thời đối chiếu cách làm tương ứng ở WebFlux. Các URI, audience, token và tên hệ thống bên dưới chỉ là ví dụ minh họa.

## 1. Decoder nằm ở đâu trong chuỗi xác thực?

Client gửi access token:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

Tại Servlet Resource Server, luồng xử lý JWT phổ biến như sau:

~~~mermaid
flowchart TD
    A["HTTP Authorization: Bearer token"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["BearerTokenAuthenticationToken"]
    C --> D["AuthenticationManager / ProviderManager"]
    D --> E["JwtAuthenticationProvider"]
    E --> F["JwtDecoder"]
    F --> G["Kiểm tra JOSE/JWS, chữ ký và nguồn khóa tin cậy"]
    G --> H["OAuth2TokenValidator: iss, exp, nbf, aud, ..."]
    H --> I["Jwt đã xác minh"]
    I --> J["JwtAuthenticationConverter"]
    J --> K["JwtAuthenticationToken + GrantedAuthority"]
    K --> L["SecurityContext / Authorization"]
    L --> M["Controller nếu đủ quyền"]
~~~

`JwtDecoder` chủ yếu chịu trách nhiệm **xác minh token và tạo đối tượng JWT đáng tin**. `JwtAuthenticationConverter` tiếp tục chuyển claims đã xác minh thành `Authentication` và `GrantedAuthority`, ví dụ ánh xạ `scope="orders.read"` sang `SCOPE_orders.read`. `authorizeHttpRequests` hoặc `@PreAuthorize` mới áp dụng quyền.

Vì vậy cần phân biệt hai hướng tùy biến:

| Nhu cầu | Thành phần nên thay |
|---|---|
| Chọn đúng JWK Set/khóa công khai, thuật toán ký | `JwtDecoder` / builder hoặc JWK source của decoder |
| Kiểm tra `iss`, `aud`, `exp`, `nbf` và claim bảo mật bắt buộc | `OAuth2TokenValidator<Jwt>` tích hợp vào decoder |
| Đổi principal name từ `sub` sang claim khác | `JwtAuthenticationConverter` |
| Ánh xạ `scope`/`scp`/`roles` thành authorities | `JwtGrantedAuthoritiesConverter` hoặc converter tùy chỉnh |
| Quy định endpoint cần `SCOPE_orders.read` | `SecurityFilterChain` và HTTP authorization |
| Kiểm tra tài nguyên thuộc đúng chủ sở hữu/tenant | Authorization ở service/domain |

**Không giải quyết sai audience bằng cách sửa converter**, vì converter chỉ chạy sau bước xác thực. Cũng không thay decoder để cấp thêm role nếu công việc thực chất là ánh xạ authorities.

## 2. Decoder mặc định làm được những gì?

Ví dụ Spring Boot Resource Server dùng Spring MVC:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Trong `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
~~~

Khi điều kiện auto-configuration được đáp ứng và ứng dụng chưa tự cung cấp bean decoder thay thế, Spring Boot có thể tạo `JwtDecoder` dựa trên issuer. Spring Security có thể dùng thông tin discovery của issuer để tìm JWK Set, xác minh chữ ký và chạy validator liên quan.

Một JWT access token minh họa có claims:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1924988400,
  "nbf": 1924988400,
  "exp": 1924992000
}
~~~

Payload trên **không phải một token đã ký** và không thể được dùng làm credential thực. Với decoder dùng issuer, các kiểm tra mặc định quan trọng thường bao gồm:

- **Chữ ký và thuật toán JWS**: token phải được ký bằng thuật toán và khóa phù hợp với nguồn tin cậy đã cấu hình.
- **Issuer (`iss`)**: giá trị issuer của token phải khớp với issuer tin cậy.
- **Thời gian hiệu lực (`exp`, `nbf`)**: từ chối token đã hết hạn hoặc chưa đến thời điểm có hiệu lực, xét theo clock skew được chấp nhận.
- **Những yêu cầu token profile/JOSE khác**: có thể khác theo phiên bản Spring Security và cách khởi tạo decoder, chẳng hạn validation của header `typ`.

**Audience (`aud`) cần được kiểm tra một cách có chủ đích** cho API của bạn. Chỉ khai báo issuer không phải bằng chứng token được cấp cho đúng API. Một số phiên bản Spring Boot có thể cung cấp property hoặc cơ chế cấu hình audience; nếu tự định nghĩa decoder, hãy bảo đảm validator audience vẫn được áp dụng.

### Bảng ràng buộc bảo mật cần cân nhắc giữ lại

| Điều kiện | Đối tượng kiểm tra | Tác hại nếu bỏ qua |
|---|---|---|
| Chữ ký JWS hợp lệ | Tính toàn vẹn và nguồn phát hành | Kẻ tấn công tự sửa claims và nâng quyền |
| Khóa lấy từ nơi tin cậy | JWK Set/key pinning theo issuer | Token chọn khóa của kẻ tấn công |
| Thuật toán được cho phép | `alg` và JOSE header processing | Chấp nhận cách ký không được phê duyệt |
| `iss` chính xác | Trusted issuer của API | Token từ tenant/issuer khác được dùng |
| `exp` và `nbf` | Hiệu lực thời gian | Token hết hạn hoặc chưa có hiệu lực được chấp nhận |
| `aud` phù hợp | API/resource được phép nhận | Token dành cho Billing API vào Orders API |
| Token type/profile | Access token hay ID token, `typ` theo profile | Dùng token sai mục đích |
| Các claim bắt buộc khác | Tenant, client, grant, token age... theo hợp đồng | Token đúng chữ ký nhưng sai ngữ cảnh |

Không phải mọi claim đều được Spring Security bắt buộc kiểm tra trong mọi phiên bản. **Hợp đồng token** phải quyết định đâu là yêu cầu bắt buộc cho ứng dụng. Với JWT access token profile RFC 9068, có các quy tắc profile cụ thể khác JWT chung; cần cấu hình validator tương ứng nếu API dựa vào profile này.

## 3. Khi nào thực sự cần thay `JwtDecoder`?

| Yêu cầu triển khai | Cách xử lý phù hợp |
|---|---|
| Chỉ cần tin một issuer với cấu hình mặc định | Dùng `issuer-uri`, tránh tùy biến không cần thiết |
| Cần JWK Set URL cố định, không phụ thuộc discovery tại startup | Dùng cấu hình `jwk-set-uri` thích hợp hoặc custom decoder có validator issuer |
| Cần audience riêng cho Orders API | Bổ sung audience validation bằng API/property được hỗ trợ |
| Nhà phát hành ký bằng thuật toán khác mặc định | Cấu hình thuật toán JWS được phép trong decoder |
| Cần timeout, proxy, HTTP client hoặc caching đặc biệt cho JWK Set | Tùy biến builder/HTTP client/JWK source theo API của phiên bản |
| Cần kết hợp issuer, audience, token type và claim đặc thù | Decoder + `OAuth2TokenValidator<Jwt>` được ghép có chủ đích |
| Có nhiều issuer tin cậy với JWK Set khác nhau | Cân nhắc `AuthenticationManagerResolver`, mỗi issuer một decoder/policy |
| Chỉ muốn đổi quyền từ `scope`/`roles` | Giữ decoder, thay `JwtAuthenticationConverter` |

Khi “thay decoder”, phải biết **cơ chế nào đang giữ vai trò decoder mặc định**. Có thể ứng dụng đang dùng auto-configuration của Spring Boot, cấu hình từ `issuer-uri`, một `JwtDecoder` bean riêng hoặc decoder gắn trực tiếp vào DSL. Nếu tự tạo decoder mới, hãy xác định rõ chính sách validation nào cần được tái áp dụng.

## 4. Ba cách gắn decoder và thứ tự ưu tiên

### 4.1. Để Spring Boot tạo decoder

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
~~~

Và dùng:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
        .build();
}
~~~

Trong đoạn method trên, cần import `HttpSecurity`, `SecurityFilterChain`, `@Bean` và static `Customizer.withDefaults` tương ứng. Đó là trường hợp đơn giản mà Boot có thể cung cấp decoder từ cấu hình.

### 4.2. Khai báo một bean `JwtDecoder` tùy chỉnh

~~~java
@Bean
JwtDecoder jwtDecoder() {
    // Tự tạo decoder, nguồn khóa và validators ở đây.
}
~~~

Khi ứng dụng cung cấp bean `JwtDecoder`, Spring Boot thông thường **back off** và không tạo decoder mặc định cùng loại. Bean mới được Resource Server dùng nếu HTTP security được cấu hình lấy decoder từ ApplicationContext. **Các property cũ không tự động được ghép validation vào bean do bạn trả về**: hãy cấu hình chúng ngay trong code hoặc dùng cấu hình trung tâm do ứng dụng quản lý.

### 4.3. Gắn decoder trực tiếp trong Resource Server DSL

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
    jwt.decoder(customJwtDecoder)
));
~~~

Đoạn này là API trong `HttpSecurity` Servlet. Decoder được gắn **trực tiếp** cho chain tương ứng. Hãy tránh duy trì hai cấu hình decoder khác nhau mà không biết chain dùng cái nào. Khi có nhiều `SecurityFilterChain`, mỗi chain có thể dùng matcher/decoder riêng; phải kiểm soát thứ tự và phạm vi để không có chain bảo vệ endpoint bằng chính sách token yếu hơn dự kiến.

**Nguyên tắc thực hành:** chọn một điểm tích hợp rõ ràng cho mỗi chain. Nếu đang định nghĩa bean decoder toàn ứng dụng, thường chỉ cần `jwt(withDefaults())`; nếu đang gắn trực tiếp qua `jwt.decoder(...)`, bảo đảm instance đó có đầy đủ validator.

## 5. Ví dụ an toàn: thay decoder, giữ issuer/time và bổ sung audience

Giả sử hợp đồng của Orders API:

~~~text
Trusted issuer:  https://login.example.test/realms/company
Trusted JWKS:    https://login.example.test/realms/company/protocol/openid-connect/certs
Expected aud:    orders-api
Allowed JWS alg: RS256
Required scope:  orders.read cho GET /api/orders/**
~~~

Ở đây URL JWK Set phải được lấy từ tài liệu/metadata của **issuer đã tin cậy**. Không suy ra JWK URL bằng cách nối chuỗi tùy tiện nếu nhà phát hành không công bố đúng đường dẫn.

### 5.1. Dùng property riêng cho decoder do ứng dụng quản lý

~~~yaml
app:
  security:
    jwt:
      issuer: https://login.example.test/realms/company
      jwk-set-uri: https://login.example.test/realms/company/protocol/openid-connect/certs
      audience: orders-api
~~~

`app.security.jwt.*` là **property do ví dụ tự định nghĩa**, không phải một nhóm property auto-configuration chính thức của Spring Boot. Cách này giúp tránh cấu hình hai nguồn issuer không đồng bộ khi bạn tự cung cấp bean `JwtDecoder`.

### 5.2. Tạo `NimbusJwtDecoder` với validator rõ ràng

~~~java
import org.springframework.beans.factory.annotation.Value;
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
class OrdersJwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        // Giữ các kiểm tra mặc định về thời gian và đúng issuer.
        OAuth2TokenValidator<Jwt> defaultsAndIssuer =
            JwtValidators.createDefaultWithIssuer(issuer);

        // Bổ sung audience của Resource Server hiện tại.
        OAuth2TokenValidator<Jwt> requiredAudience = jwt -> {
            if (jwt.getAudience() != null
                    && jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token audience does not include this API",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaultsAndIssuer,
                requiredAudience
            )
        );

        return decoder;
    }
}
~~~

Đoạn ví dụ sử dụng nhóm API Java của Spring Security hiện đại; những khác biệt cụ thể về builder, validator có thể phụ thuộc phiên bản Spring Security của ứng dụng.

**Tại sao cách này giữ được các điều kiện cần thiết?**

1. `NimbusJwtDecoder.withJwkSetUri(jwkSetUri)` chọn **nguồn khóa công khai đã tin cậy**. Token không được phép tự chọn một JWK Set lạ qua header.
2. `jwsAlgorithm(SignatureAlgorithm.RS256)` cấu hình thuật toán ký phù hợp với hợp đồng ví dụ. Với hệ thống sử dụng nhiều thuật toán, cần danh sách cho phép rõ ràng và xem chính xác semantics của builder ở phiên bản áp dụng.
3. `JwtValidators.createDefaultWithIssuer(issuer)` tái sử dụng bộ validation mặc định phù hợp, bao gồm kiểm tra thời gian và issuer. Nhờ đó việc tạo decoder thủ công không vô tình bỏ qua những ràng buộc này.
4. `requiredAudience` yêu cầu `aud` chứa `orders-api`, từ chối token không có audience hoặc token của Resource Server khác.
5. `DelegatingOAuth2TokenValidator` ghép các điều kiện; token phải vượt qua tất cả validator, không chỉ cần một trong số chúng.
6. `setJwtValidator(...)` được gọi **sau khi** builder tạo decoder. Phương thức này đặt validator mới cho decoder; vì vậy phải ghép đủ các validator cần giữ vào đối tượng mới.

**Lưu ý về `setJwtValidator`:** đây là thao tác **thay bộ validator** gắn trên decoder, không phải một thao tác “append” ngầm giữ lại mọi validator mà instance có trước đó. Nếu chỉ gọi:

~~~java
decoder.setJwtValidator(requiredAudience);
~~~

thì có nguy cơ **mất validation mặc định về issuer/thời gian** vốn phải được giữ. Đây là lỗi bảo mật quan trọng khi thay `JwtDecoder`.

### 5.3. Gắn decoder vào HTTP security

Với bean `JwtDecoder` ở trên, chuỗi bảo mật có thể viết:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Spring Security nhận bean `JwtDecoder` từ context; việc xác minh issuer/time/audience xảy ra **trước khi** map scope và kiểm tra `SCOPE_orders.read`. Trong ứng dụng thật, quyền đọc từng đơn hàng còn phải kiểm tra chủ sở hữu/tenant; scope không tự cho quyền xem mọi bản ghi.

Đây là cấu hình của API **chỉ dùng Bearer JWT cho request đang xét**. Nếu ứng dụng đồng thời cung cấp login dựa trên cookie/session, cần thiết kế CSRF và filter chain riêng theo mô hình ứng dụng. Ví dụ không tự tắt CSRF để tránh nhầm đó là điều kiện bắt buộc khi thay decoder.

### 5.4. Một cách tương đương qua issuer discovery

Nếu muốn decoder tự lấy metadata/JWK Set từ trusted issuer thay vì cấu hình JWK URI riêng, có thể thay cách khởi tạo bằng:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(issuer)
    .jwsAlgorithm(SignatureAlgorithm.RS256)
    .build();

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        requiredAudience
    )
);
~~~

Đoạn code này là **một phương án thay thế khối khởi tạo và gắn validator ở mục 5.2**, không phải bean độc lập. Nó tiếp tục dựa vào issuer tin cậy và có thể thực hiện discovery để xác định JWK Set; đặc điểm khởi tạo mạng/cache phụ thuộc phiên bản và cơ chế triển khai. Nếu hệ thống yêu cầu không phụ thuộc discovery khi start, JWK Set URI đã biết là một lựa chọn.

**Không đồng nhất nguồn khóa và issuer:** `withJwkSetUri(...)` biết lấy khóa ở đâu, nhưng **không tự chứng minh `iss` hợp lệ**. Chính `JwtValidators.createDefaultWithIssuer(...)` đảm nhận ràng buộc issuer trong ví dụ sử dụng JWK URI trực tiếp.

## 6. Một decoder cần giữ những validator nào?

### 6.1. Issuer chính xác: đừng dùng phép so chuỗi lỏng lẻo

Ví dụ trusted issuer:

~~~text
https://login.example.test/realms/company
~~~

Các giá trị sau **không tương đương** theo hợp đồng issuer:

~~~text
https://login.example.test/realms/personal
https://login.example.test/realms/company/
https://login.attacker.test/realms/company
~~~

Trong hệ thống có nhiều tenant hoặc realm, chỉ vì cùng tên miền hoặc cùng một máy chủ IdP không có nghĩa token của mọi issuer đều được chấp nhận. `JwtValidators.createDefaultWithIssuer(issuer)` mang điều kiện issuer cụ thể vào decoder.

Không dùng logic kiểu:

~~~java
// PHẢN VÍ DỤ: kiểm tra issuer quá lỏng lẻo
boolean trusted = jwt.getIssuer() != null
    && jwt.getIssuer().toString().contains("login.example.test");
~~~

Nội dung `iss` đến từ token; phải xác minh chữ ký và so khớp theo issuer được cấu hình. Việc so khớp phải theo hợp đồng issuer chính thức, không dùng substring hoặc tự bỏ path tenant.

### 6.2. Thời gian: `exp`, `nbf` và clock skew

Trong một JWT:

- `exp` là mốc token hết hạn; sau thời điểm này token không còn được chấp nhận, trừ dung sai clock skew đã xác định.
- `nbf` là thời điểm token bắt đầu hợp lệ; trước thời điểm đó token phải bị từ chối.
- `iat` là thời điểm token được phát hành; nó **không tự đồng nghĩa** với thời hạn hoặc thời điểm bắt đầu hiệu lực.

`JwtValidators.createDefaultWithIssuer(issuer)` giúp giữ cơ chế kiểm tra timestamp mặc định của Spring Security. Đối với profile yêu cầu các claim thời gian bắt buộc như `exp`, cần xác nhận rõ profile và validator có yêu cầu claim **phải tồn tại** hay chỉ kiểm tra khi claim hiện diện.

Nếu muốn bắt buộc access token có `exp`, có thể ghép thêm validator:

~~~java
OAuth2TokenValidator<Jwt> requireExpiry = jwt -> {
    if (jwt.getExpiresAt() != null) {
        return OAuth2TokenValidatorResult.success();
    }
    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Access token must contain exp",
            null
        )
    );
};
~~~

Sau đó ghép với default/issuer và audience:

~~~java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        requiredAudience,
        requireExpiry
    )
);
~~~

Đây là đoạn thay thế dòng `setJwtValidator` ở ví dụ trước. Nó giả định biến `decoder`, `issuer` và `requiredAudience` đã được tạo trong cùng cấu hình. Nếu thêm chính sách **token không được quá cũ**, cần validator riêng dựa trên `iat` và thời gian hiện tại, xử lý rõ các token thiếu `iat`, các giá trị nằm trong tương lai và clock skew.

**Clock skew không phải vô hạn.** Các máy chủ có thể lệch đồng hồ một khoảng nhỏ; việc nới dung sai quá rộng khiến token vừa hết hạn hoặc chưa có hiệu lực được chấp nhận lâu hơn dự kiến. Nếu thay cơ chế timestamp mặc định, hãy xác định rõ dung sai và cách đồng bộ đồng hồ hệ thống, thay vì vô hiệu hóa validator.

### 6.3. Audience là tập resource được phép nhận token

Giả sử có hai API:

~~~text
Orders API:  aud = orders-api
Billing API: aud = billing-api
~~~

Token:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

Token này **không thuộc Orders API**, dù issuer và chữ ký hợp lệ, thậm chí claim scope có từ `orders.read`. Audience validator trong mục 5 sẽ từ chối trước khi `JwtAuthenticationConverter` và HTTP rule xử lý scope.

Claim `aud` trong JWT có thể là một chuỗi hoặc mảng chuỗi. `Jwt.getAudience()` trình bày audience dưới dạng danh sách để việc kiểm tra resource rõ ràng hơn. Chính sách ví dụ chấp nhận khi danh sách chứa `orders-api`. Nếu API không cho phép token nhiều audience, cần chính sách bổ sung kiểm tra số lượng/giá trị audience theo hợp đồng.

### 6.4. Kiểm tra token type và tránh nhầm ID token với access token

OpenID Connect có **ID token** dành cho OIDC client. OAuth 2.0 Resource Server phải kiểm tra **access token** dành cho API. Cả hai token có thể có định dạng JWT và cùng issuer, nên không được kết luận “đúng chữ ký = đúng token type”.

Một số hệ thống dùng JWT access token profile theo **RFC 9068**, với JOSE header `typ` mang giá trị như `at+jwt`; những hệ thống khác có token profile riêng. Ví dụ JOSE header:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-01",
  "typ": "at+jwt"
}
~~~

Khi API yêu cầu RFC 9068, cần kiểm tra **token type/profile** theo đúng cách Spring Security hỗ trợ ở phiên bản đang chạy. Cơ chế validate JOSE header `typ` của Nimbus và validator profile có thể phụ thuộc builder/version; hãy dùng các API hỗ trợ profile nếu có và không tưởng rằng một lambda kiểm tra claim tự động bỏ qua được kiểm tra JOSE typ vốn chạy trước đó.

Không áp điều kiện `typ=at+jwt` cho **mọi** Resource Server nếu Authorization Server thực tế không phát hành profile đó. Việc thắt chặt phải dựa trên hợp đồng với issuer; việc bỏ qua token type cũng không được làm ID token trở thành access token.

### 6.5. Claim riêng: client, tenant, grant và quyền truy cập

API có thể yêu cầu thêm một trong các điều kiện:

| Claim/metadata | Yêu cầu ứng dụng có thể đặt ra | Ghi chú |
|---|---|---|
| `client_id` | Token chỉ dành cho client trong allowlist | Phải hiểu cách issuer phát hành claim |
| `tenant_id` | Tenant trong token thuộc nhóm được phép | Không thay kiểm tra sở hữu dữ liệu tại service |
| `azp` | Authorized party phù hợp một số profile | Không mặc nhiên có trong mọi OAuth access token |
| `jti` | Token identifier dùng cho audit/revocation | Có `jti` không tự chứng minh token chưa bị thu hồi |
| `iat` | Token không vượt quá tuổi đời cho phép | Cần validator thời gian có clock skew rõ |
| `scope` / `scp` | Quyền thực hiện thao tác | Thường xử lý bằng authority converter và authorization rule |

Nếu claim ảnh hưởng **khả năng chấp nhận token ngay từ đầu** (ví dụ audience, token type hay issuer), nên đặt nó ở **validator**. Nếu claim chỉ mô tả quyền để áp rule, converter là nơi thích hợp. Nếu rule liên quan bản ghi cụ thể, hãy kiểm tra tại authorization của nghiệp vụ.

## 7. Nguồn JWK và thuật toán: thay decoder không được thay trust model

### 7.1. Ký hiệu `alg` và `kid` không phải chính sách tin cậy

Một JWT ký số thường có ba phần:

~~~text
BASE64URL(JOSE_HEADER).BASE64URL(CLAIMS).BASE64URL(SIGNATURE)
~~~

Ví dụ header:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-01"
}
~~~

`kid` giúp decoder tìm khóa thích hợp trong **bộ khóa đã tin cậy**. `alg` cho biết thuật toán được khai báo cho việc xác minh token. Tuy nhiên, cả header và claims ban đầu là **dữ liệu chưa được xác thực**: decoder không được cho phép token tự quyết định issuer hoặc nơi tải JWK Set không nằm trong policy.

Nguy cơ xuất hiện nếu ứng dụng:

- Chấp nhận thuật toán `none` hoặc một thuật toán không được phê duyệt.
- Tin khóa do attacker gửi trong JWT header hoặc URL `jku`/`x5u` chưa được allowlist.
- Chuyển từ kiểm tra chữ ký bất đối xứng sang sử dụng một secret tùy ý mà không đánh giá hợp đồng token.
- Tải JWK Set từ endpoint do token nhận từ client chỉ ra, dẫn đến nguy cơ SSRF và chấp nhận nguồn khóa lạ.
- Chỉ gọi Base64URL decode JSON rồi tạo `Jwt` mà không xác minh JWS signature.

### 7.2. JWK Set URI và issuer phải cùng ranh giới tin cậy

Với `NimbusJwtDecoder.withJwkSetUri(...)`, ứng dụng chủ động chọn endpoint chứa public keys. Hãy lấy URL đó từ metadata/đặc tả của **issuer đã cho phép**, sử dụng HTTPS và giới hạn truy cập mạng phù hợp.

~~~text
Trusted issuer:
  https://login.example.test/realms/company

Trusted JWKS:
  https://login.example.test/realms/company/protocol/openid-connect/certs

Expected audience:
  orders-api
~~~

Việc khai báo JWK Set URL **không tự thêm issuer validation** nếu decoder tùy chỉnh không ghép validator. Ngược lại, việc kiểm tra issuer bằng claim mà không kiểm tra chữ ký tin cậy cũng không có giá trị bảo mật: token giả có thể tự ghi `iss` giống issuer thật.

### 7.3. Đọc metadata từ trusted issuer

Khi sử dụng discovery, Spring có thể lấy metadata của issuer rồi tìm JWK Set tương ứng. Điều kiện an toàn:

1. Issuer đầu vào phải là giá trị **được cấu hình/allowlist** trước.
2. Metadata và `jwks_uri` cần được lấy qua cơ chế tin cậy (HTTPS, kiểm tra TLS và nguồn phát hành).
3. Thuật toán/khóa được chấp nhận tuân thủ policy của API.
4. Sau khi xác minh chữ ký, validator vẫn phải kiểm tra `iss`, `aud`, thời gian và claim bắt buộc.

Không thiết kế “issuer động” bằng cách lấy bất kỳ claim `iss` trong token chưa xác thực rồi gọi discovery đến URI đó. Trường hợp nhiều issuer phải có **registry tin cậy** riêng.

### 7.4. Khóa cố định thay cho JWK Set động

Một số môi trường offline hoặc hệ thống tích hợp đặc biệt có thể có public key được triển khai sẵn. Decoder có builder dùng public key, chẳng hạn:

~~~java
// publicKey là RSAPublicKey đã lấy từ nguồn tin cậy.
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withPublicKey(publicKey)
    .build();

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        requiredAudience
    )
);
~~~

`publicKey` và `issuer` ở đây là những giá trị do hệ thống kiểm soát, không lấy từ payload của request. Khi dùng khóa cố định, phải có quy trình **key rotation** và thay khóa đúng thời điểm; một JWT do issuer ký bằng khóa mới có thể bị từ chối nếu ứng dụng vẫn chỉ tin khóa cũ.

Không có yêu cầu phải tải JWK mỗi request khi dùng JWK Set: triển khai thường cache khóa và refresh theo cơ chế của HTTP client/JWK source. **Chính sách TTL, timeout và refresh** phải được xác nhận theo bản Spring Security/Nimbus đang dùng.

## 8. Kết hợp `issuer-uri` và `jwk-set-uri` trong Spring Boot

Nếu mục tiêu chỉ là **khai báo JWK URI sẵn có để tránh discovery lúc startup**, không nhất thiết phải viết bean decoder:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
          jwk-set-uri: https://login.example.test/realms/company/protocol/openid-connect/certs
~~~

Với cấu hình được Spring Boot/Spring Security hỗ trợ, ứng dụng biết trước địa chỉ JWK Set và vẫn có thể thực hiện issuer validation theo `issuer-uri`. Điều này hữu ích khi Authorization Server không sẵn sàng ngay trong thời gian khởi động, nhưng **không loại bỏ phụ thuộc vào JWK endpoint khi cần lấy khóa chưa có trong cache**.

Nếu muốn audience validation mà phiên bản Spring Boot cung cấp property `audiences`, có thể ưu tiên property chính thức tương ứng sau khi xác nhận phiên bản. Nếu không, hãy thêm validator tùy chỉnh qua API mà framework hỗ trợ. Không ghi giả rằng một property được hỗ trợ ở tất cả phiên bản.

**Phân biệt hai cấu hình:**

| Cách làm | Ai tạo decoder | Ai chịu trách nhiệm validation? |
|---|---|---|
| `issuer-uri` đơn thuần | Auto-config/Spring Security | Framework cung cấp default issuer/time/crypto; API bổ sung claim cần thiết |
| `issuer-uri` + `jwk-set-uri` | Auto-config/Spring Security | Framework vẫn có ngữ cảnh issuer; API kiểm tra audience/policy riêng |
| Bean `JwtDecoder` dùng `withJwkSetUri` | Ứng dụng | Ứng dụng phải ghép đầy đủ default validator, issuer và claim bắt buộc |
| Decoder gắn trực tiếp `jwt.decoder(...)` | Ứng dụng cho chain | Decoder đó phải tự có đủ crypto + validators; không mong bean/property khác tự vá |

Các API và thứ tự ưu tiên cụ thể có thể thay đổi giữa các phiên bản Spring Security/Spring Boot. Khi dùng nhiều nguồn cấu hình, hãy thiết kế một nguồn giá trị issuer/audience thống nhất để tránh API chạy với chính sách khác tài liệu.

## 9. Giữ validator khi thêm yêu cầu khác

Giả sử ngoài issuer/audience, API cần bảo đảm token có claim `client_id` nằm trong danh sách client được phép. Tùy thuộc hợp đồng với issuer, có thể tạo thêm validator:

~~~java
Set<String> allowedClients = Set.of(
    "web-orders-client",
    "orders-mobile-client"
);

OAuth2TokenValidator<Jwt> allowedClientValidator = jwt -> {
    String clientId = jwt.getClaimAsString("client_id");
    if (clientId != null && allowedClients.contains(clientId)) {
        return OAuth2TokenValidatorResult.success();
    }
    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Client is not allowed for this API",
            null
        )
    );
};
~~~

Đoạn này cần import `java.util.Set`, đồng thời các class `OAuth2TokenValidator`, `OAuth2TokenValidatorResult`, `OAuth2Error` và `Jwt` như phần 5. Hãy ghép toàn bộ thành một validator:

~~~java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        requiredAudience,
        allowedClientValidator
    )
);
~~~

Ví dụ `client_id` là claim **đã được issuer bảo đảm trong access token profile**; không mặc định mọi Authorization Server đều phát hành claim này. Đặc biệt, không dùng một claim do request parameter chưa được xác minh gửi lên để quyết định client được phép.

### Khi ghép nhiều validator

~~~text
JwtDecoder
   ├── Xác minh JWS và thuật toán/khóa
   └── DelegatingOAuth2TokenValidator
         ├── Defaults + issuer
         ├── Audience orders-api
         └── Client allowlist (theo hợp đồng)
                ↓
         Chỉ trả Jwt khi hợp lệ
~~~

Nếu một điều kiện không đạt, decoder không trả JWT đã xác thực cho `JwtAuthenticationProvider`. Chỉ khi qua toàn bộ xác thực, Spring Security mới ánh xạ principal và authorities để kiểm tra `hasAuthority(...)`.

### Cẩn thận khi chồng các validator thời gian

Nếu muốn thay clock skew mặc định bằng một giá trị cụ thể, không nên vừa giữ validator timestamp mặc định với skew A, vừa thêm validator timestamp mới với skew B rồi cho rằng giá trị B đã thay thế A. Hai validator có thể cùng chạy, khiến giới hạn hiệu lực khác kỳ vọng.

Hãy chọn một cấu hình thời gian rõ ràng, giữ các kiểm tra khác của default/profile theo cách tương ứng với phiên bản framework. Nếu thay nguyên bộ default bằng tập validator tự tạo, cần xác nhận không bỏ sót những kiểm tra mà bộ mặc định đang cung cấp ở version đó.

## 10. Thay decoder trong Spring WebFlux: cùng chính sách, khác interface

Trên **Spring WebFlux**, Resource Server vẫn nhận Bearer JWT và cần giữ nguyên các kiểm tra issuer, audience, chữ ký, thời gian. Tuy nhiên, security pipeline sử dụng **reactive API**:

| Trách nhiệm | Servlet / Spring MVC | Reactive / WebFlux |
|---|---|---|
| HTTP Security | `HttpSecurity` | `ServerHttpSecurity` |
| Bean filter chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Interface decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Nimbus decoder | `NimbusJwtDecoder` | `NimbusReactiveJwtDecoder` |
| Kết quả decode | `Jwt` hoặc exception | `Mono<Jwt>` hoặc tín hiệu lỗi |
| Resource Server DSL | `oauth2ResourceServer(o -> o.jwt(...))` | Cùng ý định nhưng trên `ServerHttpSecurity` |
| Security context | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |

Dependency thông dụng của WebFlux Resource Server:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Cùng nhóm property `app.security.jwt.*` như phần 5 có thể được sử dụng nếu ứng dụng tự cung cấp reactive decoder.

### 10.1. Ví dụ bean `ReactiveJwtDecoder`

~~~java
import org.springframework.beans.factory.annotation.Value;
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
class ReactiveOrdersJwtDecoderConfig {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience() != null
                    && jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token audience is not allowed",
                    null
                )
            );
        };

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

Ý tưởng validation **không đổi so với Servlet**: source JWK Set tin cậy, thuật toán cho phép, default + issuer và audience. API Java thay đổi ở kiểu decoder và mô hình phản hồi reactive.

### 10.2. Gắn reactive decoder vào WebFlux security chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveOrdersApiSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Với bean `ReactiveJwtDecoder` từ phần 10.1, chain reactive lấy decoder tương ứng từ context. Nếu cấu hình gắn decoder trực tiếp qua DSL, decoder đó cũng phải có các validator tương đương. **Không dùng `JwtDecoder` đồng bộ của Servlet làm decoder trực tiếp của WebFlux**, và không đưa những lời gọi blocking không cần thiết vào event loop khi tự tùy biến nguồn JWK/HTTP.

## 11. Nhiều issuer: thay một decoder chưa chắc là đủ

Giả sử API được phép nhận token từ hai issuer:

~~~text
Issuer A: https://login.example.test/realms/company
Issuer B: https://partners.example.test/oauth2/default
Audience của API: orders-api
~~~

Nếu chỉ dùng một `NimbusJwtDecoder` với JWK Set của Issuer A, JWT từ Issuer B không thể được xác minh phù hợp dù Issuer B thực sự nằm trong allowlist. **Không xử lý bằng cách bỏ issuer validation**, hoặc trộn tất cả khóa từ mọi issuer thành một tập không còn ranh giới nguồn.

Mô hình phù hợp thường là **issuer-aware authentication manager resolver**:

~~~mermaid
flowchart TD
    A["Bearer JWT"] --> B["Đọc iss như gợi ý định tuyến chưa tin cậy"]
    B --> C{"iss thuộc danh sách issuer tin cậy?"}
    C -->|No| D["Từ chối"]
    C -->|Yes| E["Chọn AuthenticationManager/decoder theo issuer"]
    E --> F["Xác minh chữ ký bằng JWK của chính issuer đó"]
    F --> G["Validate iss, exp, nbf, aud và policy"]
    G --> H["JwtAuthenticationToken"]
~~~

Trong Servlet Spring Security có `JwtIssuerAuthenticationManagerResolver` hoặc cách xây dựng `AuthenticationManagerResolver<HttpServletRequest>` để chọn manager cho mỗi issuer được tin cậy; WebFlux có phương án resolver reactive tương ứng. Tên constructor/factory và cách wiring có thể khác theo phiên bản, nên cần áp dụng API thực tế của dự án.

Điểm tinh tế: resolver có thể phải đọc `iss` **trước khi chữ ký token được xác minh** để chọn decoder. Khi đó `iss` chỉ là **gợi ý định tuyến**, chưa phải tuyên bố đáng tin. Resolver phải kiểm tra allowlist rồi decoder được chọn xác minh chữ ký bằng **key của đúng issuer** và xác nhận claim `iss` thật sự khớp.

### Khi mỗi issuer có quy tắc khác nhau

| Chính sách | Issuer A | Issuer B |
|---|---|---|
| Trusted JWKS | JWK Set A | JWK Set B |
| Thuật toán ký | RS256 theo hợp đồng A | Thuật toán được phép theo hợp đồng B |
| Expected audience | `orders-api` | `orders-api` hoặc resource ID riêng |
| Claim scope | `scope` | Có thể là `scp` |
| Claim tenant | `tenant_id` | Có thể là claim khác |
| Profile token | Chính sách của A | Chính sách của B |

Nếu cùng một scope string có ý nghĩa khác nhau giữa hai issuer, converter và authorization policy cũng cần phân biệt. Không mặc định token `scope="admin"` của issuer B là quyền quản trị tương đương issuer A.

**Không triển khai discovery động cho mọi issuer do client gửi lên**, vì có thể bị lợi dụng để gọi đến địa chỉ không đáng tin hoặc giả mạo nguồn phát hành. Quản lý issuer là quyết định tin cậy của máy chủ.

## 12. Thay decoder nhưng không thay đổi nhầm `JwtAuthenticationConverter`

Một nhầm lẫn khá phổ biến là thay decoder để “đọc role từ token”, sau đó làm mất các validator mặc định trong quá trình đó. Nếu token đã được xác minh và chỉ cần ánh xạ claim `roles`, hãy giữ nguyên decoder đang an toàn.

Ví dụ JWT hợp lệ có:

~~~json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "roles": ["AUDITOR"]
}
~~~

Spring Security JWT Resource Server thường chuyển scope thành `SCOPE_orders.read`. Nếu muốn thêm `ROLE_AUDITOR`, ta cần converter authorities dựa trên **claim đã xác minh**, không cần đổi nguồn khóa hay bỏ issuer validation.

~~~java
JwtGrantedAuthoritiesConverter scopeConverter =
    new JwtGrantedAuthoritiesConverter();

JwtAuthenticationConverter authenticationConverter =
    new JwtAuthenticationConverter();

authenticationConverter.setJwtGrantedAuthoritiesConverter(
    scopeConverter
);
~~~

Đây là cấu trúc cơ bản của converter, với import từ package `org.springframework.security.oauth2.server.resource.authentication`. Khi cần role riêng, có thể cung cấp converter ghép scope và role; đó là logic ánh xạ bổ sung sau validation.

Đăng ký converter ở JWT DSL:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
    jwt.jwtAuthenticationConverter(authenticationConverter)))
~~~

Điều này khác:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
    jwt.decoder(customJwtDecoder)))
~~~

Một API có thể cần cả hai, nhưng **decoder** xác nhận token đáng tin còn **converter** tạo principal/authorities. Thứ tự rõ ràng giúp không đưa dữ liệu claim chưa được xác minh vào quyền Spring Security.

## 13. Token hợp lệ về chữ ký nhưng vẫn bị từ chối

Giả sử Orders API tin issuer `https://login.example.test/realms/company`, audience `orders-api` và GET yêu cầu authority `SCOPE_orders.read`.

| JWT nhận được | Decoder làm gì? | Authorization sau decoder |
|---|---|---|
| Chữ ký đúng, `iss` đúng, `aud=orders-api`, chưa hết hạn, scope đọc | Trả `Jwt` hợp lệ | Cho request qua rule đọc; service tiếp tục policy dữ liệu |
| Sai chữ ký hoặc bị sửa payload | Ném lỗi xác thực | Không có principal đủ tin cậy |
| `iss` khác trusted issuer | Từ chối | Không đến bước scope |
| `aud=billing-api` | Audience validator từ chối | Không đến bước scope |
| Không có `aud` khi API yêu cầu | Audience validator từ chối | Không đến bước scope |
| `exp` đã hết hạn | Timestamp validator từ chối | Không đến bước scope |
| `nbf` ở tương lai ngoài clock skew cho phép | Timestamp validator từ chối | Không đến bước scope |
| JWS algorithm không được phép | Decoder từ chối | Không đến bước scope |
| Khóa/JWK không phù hợp | Decoder từ chối | Không đến bước scope |
| Token hợp lệ, chỉ có `orders.create` | Decoder trả `Jwt` hợp lệ | Thiếu `SCOPE_orders.read`, bị từ chối phân quyền |
| Token hợp lệ, đủ scope, không sở hữu bản ghi | Decoder trả `Jwt` hợp lệ | Service/domain từ chối truy cập dữ liệu |

Điểm phân biệt:

- **Lỗi decoder/validator** = lỗi **authentication**, Resource Server thường trả HTTP **401 Unauthorized**.
- **Token đã xác thực nhưng thiếu authority/policy** = lỗi **authorization**, Resource Server thường trả **403 Forbidden**.
- Lỗi hạ tầng JWK/metadata không nhất thiết có cùng status với token sai; nhưng **không được cho request đi tiếp khi không thể xác minh token**.

Ví dụ challenge Bearer token:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Với scope thiếu:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
~~~

Đây là minh họa theo RFC 6750; chi tiết response thực tế phụ thuộc Spring Security, gateway và exception handling. Không ghi full JWT, secret, JWK private material hoặc chi tiết nội bộ vào thông báo lỗi gửi về client.

## 14. Các trường hợp dễ mất kiểm tra khi tự viết `JwtDecoder`

### 14.1. Chỉ giải mã payload JSON

~~~java
// PHẢN VÍ DỤ — giải mã payload không phải xác minh chữ ký:
String json = new String(
    Base64.getUrlDecoder().decode(jwtSegments[1]),
    StandardCharsets.UTF_8
);
~~~

Mã này chỉ trích nội dung Base64URL, không kiểm tra JWS. Kẻ tấn công có thể tự thay `sub`, `scope` hoặc `aud` trong JSON. **Không trả đối tượng Jwt tin cậy từ payload chưa xác minh**.

### 14.2. Tạo JWT giả trong decoder

~~~java
// PHẢN VÍ DỤ — tuyệt đối không dùng cho request thật:
// return Jwt.withTokenValue(token)
//     .header("alg", "none")
//     .claim("sub", "anonymous")
//     .claim("scope", "orders.read")
//     .build();
~~~

`Jwt.withTokenValue(...)` có ích để xây dữ liệu test converter, nhưng không thay cho decoder xác minh chữ ký. Trả một Jwt dựng thủ công từ token chưa kiểm tra sẽ làm `JwtAuthenticationProvider` nhận kết quả giả đáng tin.

### 14.3. Ghi đè validator chỉ với audience

~~~java
// PHẢN VÍ DỤ — có thể làm mất issuer/time validation:
decoder.setJwtValidator(requiredAudience);
~~~

Cách đúng về ý tưởng là ghép:

~~~java
decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
    JwtValidators.createDefaultWithIssuer(issuer),
    requiredAudience
));
~~~

### 14.4. Chỉ đặt `jwk-set-uri` rồi quên `iss`

Một bộ public keys tin cậy có thể xác minh chữ ký, nhưng nếu mã không kiểm tra issuer, API có thể chấp nhận token sai realm/tenant/issuer trong một số kiến trúc khóa dùng chung hoặc ranh giới tin cậy phức tạp. Nguồn khóa và issuer là **hai điều kiện bổ trợ**.

### 14.5. Thêm audience nhưng bỏ default/profile validators

Một validator duy nhất dựa trên `jwt.getAudience().contains(...)` không tự kiểm tra hết hạn, issuer, token type hoặc những ràng buộc khác. Ngoài validation nằm trong Nimbus/JWS layer, hãy ghép **đủ tập claim validators** theo hợp đồng token.

### 14.6. Tắt kiểm tra `typ` để “sửa” JWT bị reject

Nếu Spring Security/Nimbus từ chối JWT vì JOSE `typ` không phù hợp, nguyên nhân có thể là **API nhận sai loại token** hoặc profile chưa được cấu hình đầy đủ. Không chỉ tắt type validation và coi vấn đề đã được giải quyết. Nếu API yêu cầu RFC 9068, dùng token profile validator thích hợp; nếu issuer dùng profile riêng, phải thống nhất và xác minh chính xác kiểu token hợp lệ.

### 14.7. Chấp nhận mọi issuer có `kid` khớp

`kid` chỉ là key identifier trong một JWK Set. Cùng một `kid` ở hai issuer khác nhau không có nghĩa cùng trust. Không lấy `kid` làm định danh issuer, audience hay principal.

### 14.8. Cho request qua khi JWKS endpoint lỗi

Khi không tìm được public key tin cậy hoặc endpoint tạm unavailable, việc bỏ qua xác minh chữ ký để tránh downtime sẽ biến API thành endpoint chấp nhận token giả. Cần thiết kế cache/timeout/alert và **fail closed** về quyền truy cập.

### 14.9. Tin mọi claim `roles` ngay khi nhìn thấy JSON

Claim có ý nghĩa cấp quyền chỉ sau validation. Nếu muốn ánh xạ role, dùng converter trên `Jwt` đã xác minh. Đừng viết một servlet filter đọc raw payload, set `ROLE_ADMIN` từ request trước khi authentication.

### 14.10. Dùng `issuer-uri` nhưng không xác định resource identity

Một Authorization Server có thể cấp token cho nhiều API. Nếu chỉ kiểm tra issuer mà bỏ audience, token từ Billing API có thể được Orders API chấp nhận khi scope/claims tình cờ tương thích. Thiết kế một **expected audience** rõ ràng là một phần của hợp đồng Resource Server.

## 15. Lưu ý vận hành khi đổi nguồn khóa

### 15.1. Key rotation

Authorization Server có thể thay public key theo chu kỳ. Với decoder dùng JWK Set động:

1. Issuer công bố JWK Set với các khóa đang hợp lệ.
2. Khi chuẩn bị đổi khóa, issuer có thể công bố khóa mới trước khi ký token bằng khóa đó.
3. Resource Server cập nhật JWK Set theo cơ chế cache/refresh được hỗ trợ.
4. Trong giai đoạn chuyển tiếp, issuer thường giữ public key cũ nếu JWT đã phát hành bằng khóa cũ vẫn còn hiệu lực.
5. Sau khi token cũ hết hiệu lực và chính sách cho phép, issuer loại khóa cũ.

Nếu API pin một public key duy nhất bằng `withPublicKey(...)`, quá trình thay khóa cần triển khai/đổi cấu hình có phối hợp. Đừng “sửa nhanh” bằng cách vô hiệu hóa xác minh chữ ký.

### 15.2. Thời gian chờ và phụ thuộc mạng

Decoder dùng remote JWK Set có thể cần HTTP kết nối để lấy khóa. Cần xem xét:

| Khía cạnh | Điều cần quyết định |
|---|---|
| Connect/read timeout | Không để request treo vô hạn khi JWK endpoint chậm |
| TLS/truststore | Tin cậy đúng CA và hostname của endpoint |
| Proxy/firewall | API truy cập được JWK URL đã được phê duyệt |
| Cache TTL | Đáp ứng rotation mà không gọi mạng quá thường xuyên |
| Refresh khi `kid` mới | Có cơ chế cập nhật JWK Set đúng phiên bản |
| Retry/circuit breaker | Không tạo retry storm khi issuer outage |
| Fail-closed policy | Không cho token chưa được xác minh đi qua |

Tùy API Spring Security/Nimbus đang dùng, có thể cấu hình HTTP client qua builder hoặc custom JWK source; không giả định mọi property timeout của HTTP client chung trong ứng dụng tự động tác động lên decoder.

### 15.3. Ghi log an toàn

Theo dõi nên tập trung vào **loại thất bại** và hiệu năng, chẳng hạn:

- Số lỗi `invalid_token` do chữ ký/issuer/audience/timestamp (phân loại nội bộ phù hợp).
- Số lỗi không tìm được `kid` hoặc lấy JWK Set thất bại.
- Latency và số lỗi HTTP tới JWK endpoint.
- Số request 401/403 theo endpoint và request ID.
- Phiên bản cấu hình issuer/audience/allowed algorithms và lần cập nhật khóa.

Không log nguyên Bearer token, HTTP `Authorization` header, private key, client secret hay payload đầy đủ chứa PII. Khi cần audit, dùng định danh và metadata ít nhạy cảm được chính sách cho phép; không lấy token thật đưa vào issue hoặc transcript chia sẻ.

## 16. Cách kiểm chứng decoder mới thực sự giữ các điều kiện bảo mật

Khi thay decoder, câu hỏi chính không phải chỉ “JWT hợp lệ có truy cập được endpoint không?” mà còn là **“JWT sai theo từng điều kiện đã được từ chối tại đúng bước chưa?”**. Có hai cấp kiểm tra khác nhau:

1. **Kiểm tra decoder/validator thực**: gọi logic xác minh với JWT có chữ ký thật bằng khóa thử nghiệm, JWK Set thử nghiệm và các trường hợp claim/algorithm khác nhau.
2. **Kiểm tra authorization của security chain**: sau khi authentication hợp lệ, xác nhận `SCOPE_*` hoặc role được ánh xạ đúng và các endpoint thực thi rule dự kiến.

Không nên dùng test chỉ mock principal để kết luận **chữ ký, issuer, audience và thời gian** đã được kiểm tra, vì một mock authentication thường **bỏ qua decoder thật**.

### 16.1. Ma trận hành vi cần thể hiện

Giả sử hợp đồng Orders API:

~~~text
Issuer được tin:       https://login.example.test/realms/company
Expected audience:     orders-api
JWS algorithm:         RS256 theo hợp đồng
Required scope GET:    orders.read
Token profile:         OAuth 2.0 access token được API chấp nhận
~~~

| Trường hợp | Tính chất JWT | Kỳ vọng ở decoder | Kỳ vọng HTTP đối với GET bảo vệ |
|---|---|---|---|
| Đúng toàn bộ | Ký đúng, issuer đúng, audience đúng, chưa hết hạn, scope đọc | Thành công | Qua HTTP rule |
| Chữ ký bị thay | Nội dung claims không đi kèm chữ ký hợp lệ | Từ chối | 401 |
| Khóa ký không tin cậy | Chữ ký từ key không thuộc trusted JWK Set | Từ chối | 401 |
| Thuật toán ngoài policy | JOSE `alg` không được phép | Từ chối | 401 |
| Issuer không đúng | `iss` của realm khác | Từ chối | 401 |
| Audience API khác | `aud=["billing-api"]` | Từ chối | 401 |
| Audience vắng mặt | Không có `aud` trong token | Từ chối theo hợp đồng | 401 |
| JWT hết hạn | `exp` nằm trong quá khứ ngoài clock skew | Từ chối | 401 |
| JWT chưa có hiệu lực | `nbf` nằm trong tương lai ngoài clock skew | Từ chối | 401 |
| JWT thiếu `exp` | Không có hạn dùng | Theo validator/profile yêu cầu | 401 nếu `exp` bắt buộc |
| Sai token type | ID token hoặc `typ` không đúng profile được phép | Từ chối theo policy | 401 |
| Đúng token, thiếu scope | Mọi claim xác thực hợp lệ, không có `orders.read` | Thành công | 403 |
| Token đúng, scope đủ, sai chủ dữ liệu | Token hợp lệ, nhưng đơn hàng không thuộc principal | Thành công | 403 hoặc 404 tùy policy nghiệp vụ |
| JWK endpoint outage | Chưa có key đáng tin trong cache | Không thể xác minh | Không cho request đi qua; mã HTTP tùy xử lý lỗi |

Nếu `JwtDecoder` tùy chỉnh chấp nhận token sai issuer/audience dù `SecurityFilterChain` vẫn từ chối một số scope, đó vẫn là **lỗi ở tầng authentication**. Chính sách HTTP quyền không thể bù hoàn toàn việc decoder đã tin sai token.

### 16.2. Vì sao `mockMvc().with(jwt())` chưa đủ?

Spring Security Test có `jwt()` request post processor, giúp tạo một authentication giả định đã thành công. Ví dụ:

~~~java
mockMvc.perform(
        get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            ))
    )
    .andExpect(status().isOk());
~~~

Đây là ví dụ về **test rule phân quyền** trên endpoint giả định trả HTTP 200 cho principal có quyền, với import và setup test đầy đủ của `MockMvc`/`spring-security-test`. Việc gọi `jwt()` như trên **không chứng minh `NimbusJwtDecoder` đã tải JWK Set, kiểm tra chữ ký, issuer hoặc audience**.

Để xác minh decoder thật, cần token **được ký bằng private key thử nghiệm**, đưa **public JWK** tương ứng qua endpoint được stub/khóa tin cậy, rồi kiểm tra token hợp lệ và token biến thể sai. Tách nhóm test decoder với nhóm test authorization để khi lỗi có thể xác định đúng lớp.

### 16.3. Khi thay decoder sau khi có mã nguồn cũ

Nếu hệ thống trước đây chỉ dùng `issuer-uri`, trước khi chuyển sang custom `JwtDecoder` nên biết:

- Issuer và JWK Set đã được lấy từ đâu.
- Bộ thuật toán ký được chấp nhận là gì.
- Từng validator mặc định thực sự được cài trong version hiện tại.
- API có audience validation ở property, bean hay custom filter nào khác chưa.
- Có profile JWT access token riêng hoặc claim tenant/client bắt buộc nào không.
- Có nhiều security chain hoặc nhiều issuer cùng sử dụng decoder không.
- Thay đổi khi JWK endpoint không sẵn sàng lúc startup và khi request runtime như thế nào.

Từ đó tạo một decoder mới **tương đương hoặc chặt chẽ hơn** theo hợp đồng. Không cần bọc mọi thư viện xác minh JWT bằng code tự viết nếu Spring Security/Nimbus đã có implementation chính thức được duy trì.

## 17. Cách chẩn đoán lỗi sau khi thay decoder

| Hiện tượng | Nguyên nhân thường gặp | Hướng phân tích |
|---|---|---|
| Mọi Bearer token bị 401 | Sai issuer, JWK URI, allowed algorithm, thiếu key, sai audience | Phân biệt validation exception với lỗi tải JWK; kiểm tra cấu hình nguồn sự thật |
| JWT dùng được trước khi thay decoder, sau đó bị 401 | Bộ validator mới có policy khác hoặc cấu hình typ/alg không tương thích | So sánh hợp đồng token và config decoder của phiên bản |
| JWT hết hạn vẫn được chấp nhận | `setJwtValidator` chỉ nhận audience/custom validator, không còn timestamp validation | Tái ghép `JwtValidators.createDefaultWithIssuer` hoặc bộ validator tương đương |
| Token issuer khác cũng được chấp nhận | Chỉ cấu hình JWK URI, quên issuer validator hoặc trust boundary | Kiểm tra `iss` chính xác, key source theo issuer |
| Token API khác được chấp nhận | Không áp audience validator | Ràng buộc `aud` với expected resource ID |
| Chỉ thiếu scope thì trả 403 | Decoder thành công, converter không sinh authority cần thiết | Kiểm tra `scope`/`scp`, prefix `SCOPE_` và HTTP rule |
| `401` xuất hiện khi IdP đổi khóa | JWK cache chưa refresh hoặc issuer đã bỏ khóa quá sớm | Kiểm tra `kid`, vòng đời JWK và chính sách rotation |
| Startup phụ thuộc IdP | Decoder làm discovery ở lúc khởi tạo | Cân nhắc JWK Set URI đã được tin cậy và startup policy phù hợp |
| Ứng dụng MVC có bean nhưng decoder không chạy | DSL gắn decoder khác hoặc security chain không match | Kiểm tra cấu hình decoder của đúng chain |
| Bean `JwtDecoder` không được inject ở WebFlux | Ứng dụng reactive yêu cầu `ReactiveJwtDecoder` | Chuyển đúng interface và pipeline |
| Lỗi `typ` khi chuyển sang RFC 9068 | Token profile và JOSE typ processing chưa thống nhất | Đối chiếu profile issuer, API validation và khả năng hỗ trợ của phiên bản |
| JWK URL gặp TLS/timeout | CA, hostname, proxy, network hoặc timeout config | Điều chỉnh HTTP client/truststore đúng policy; không bỏ xác minh |

### Phân biệt 401 do token với lỗi hạ tầng

Một JWT có chữ ký không hợp lệ hoặc sai audience là **credential bị từ chối**. Nhưng khi JWK Set của issuer không truy cập được, nguyên nhân có thể là **mạng/IdP hoặc cấu hình vận hành**. Cả hai đều không được tạo authentication thành công; tuy nhiên log nội bộ, metric và mã phản hồi cho client có thể cần phân biệt để vận hành đúng.

Không trả lại raw JWT, private key hoặc nội dung network exception chứa secret trong HTTP response. Nếu muốn ghi một request ID để liên kết trace, chỉ dùng metadata do hệ thống tạo và được phép ghi log.

## 18. Quy trình ra quyết định khi tùy biến decoder

~~~mermaid
flowchart TD
    A["Cần đổi hành vi Resource Server?"] --> B{"Chỉ đổi scope/role/principal?"}
    B -->|Yes| C["Tùy biến JwtAuthenticationConverter"]
    B -->|No| D{"Chỉ cần cấu hình issuer/JWK/audience chuẩn?"}
    D -->|Yes| E["Ưu tiên Spring Boot/Security properties được hỗ trợ"]
    D -->|No| F["Tạo JwtDecoder / ReactiveJwtDecoder riêng"]
    F --> G["Chọn JWK source & algorithms tin cậy"]
    G --> H["Ghép default + issuer validators"]
    H --> I["Thêm audience + profile/custom validators"]
    I --> J["Gắn vào đúng SecurityFilterChain"]
    J --> K["Kiểm tra các trường hợp hợp lệ và bị từ chối"]
~~~

Khi API dùng JWT access token, có thể ghi nhớ:

~~~text
Raw Bearer JWT
  |
  v
Decoder với nguồn khóa/thuật toán đã tin
  |
  v
Xác minh chữ ký + validate issuer/time/audience/profile
  |
  v
Jwt đã xác minh
  |
  v
JwtAuthenticationConverter
  |
  v
JwtAuthenticationToken + SCOPE_*/ROLE_* authorities
  |
  v
SecurityContext + authorization rules + nghiệp vụ
~~~

**Thay decoder mặc định là thay điểm tạo niềm tin cho JWT.** Hãy giữ đầy đủ việc xác minh chữ ký và nguồn khóa, issuer, thời gian hiệu lực và những validator thuộc hợp đồng API; bổ sung audience và token profile khi cần. Nếu tự gọi `setJwtValidator(...)`, luôn ghép lại các kiểm tra mặc định mà ứng dụng vẫn cần, vì phương thức này không tự động nối thêm validator vào bộ cũ. Khi giữ được ranh giới đó, việc thay decoder để đáp ứng hạ tầng đặc thù vẫn có thể duy trì mô hình xác thực và phân quyền an toàn của Spring Security.

## Tài liệu tham khảo

- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet Bearer Token Authentication](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — JWT Decoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtDecoder.html)
- [Spring Security — NimbusJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Spring Security — JwtValidators Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtValidators.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
