# Khác biệt giữa cấu hình Bean tường minh và cấu hình tự động

Khi xây dựng **Spring Security OAuth 2.0/OIDC Resource Server**, ứng dụng có thể được cấu hình bằng properties của Spring Boot, bằng các `@Bean` tường minh, hoặc kết hợp cả hai. Điểm quan trọng là Spring Boot không bật một chế độ “tự động” duy nhất rồi tắt toàn bộ khi ta viết Java configuration. Resource Server gồm nhiều thành phần độc lập, và mỗi thành phần có quy tắc thay thế riêng.

Với Servlet Resource Server dùng JWT, các thành phần chính là:

- `SecurityFilterChain`: xác định request nào đi qua Spring Security, cách xác thực Bearer token và chính sách authorization.
- `JwtDecoder`: parse, xác minh chữ ký và validate claims của JWT.
- `JwtAuthenticationConverter`: chuyển `Jwt` đã xác minh thành `Authentication` và authorities.

Với opaque token, `JwtDecoder` được thay bằng:

- `OpaqueTokenIntrospector`: gọi introspection endpoint, kiểm tra token có `active=true` và tạo principal/attributes.

Spring Boot có thể tự cấu hình security chain và decoder/introspector từ properties. Khi ứng dụng khai báo Bean riêng, Boot thường **lùi lại đối với đúng loại Bean đã được thay thế**. Những thành phần khác vẫn có thể tiếp tục được tự cấu hình.

> **Nguyên tắc cốt lõi:** `SecurityFilterChain`, `JwtDecoder` và `OpaqueTokenIntrospector` là những điểm mở rộng độc lập. Thêm một Bean tường minh không có nghĩa toàn bộ Resource Server auto-configuration biến mất. Cần biết chính xác Bean nào đang thay thế Bean mặc định và trách nhiệm nào ứng dụng phải tự đảm nhận.

Bài học tập trung vào Spring Boot và Spring Security Servlet Resource Server, đồng thời chỉ ra các API tương ứng trong WebFlux. Ví dụ sử dụng Java và YAML. Tên API, property và điều kiện auto-configuration cần được đối chiếu với Spring Boot/Spring Security BOM thực tế của dự án.

## 1. Hai cách tiếp cận và vai trò của chúng

### 1.1. Cấu hình tự động bằng properties

Ta khai báo thông tin nhà phát hành và policy cơ bản:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

Spring Boot đọc properties, tạo các thành phần Resource Server phù hợp nếu ứng dụng có dependencies cần thiết và không có Bean tường minh thay thế chúng.

Với JWT, đường đi tổng quát:

~~~text
application.yml
      |
      v
Spring Boot Resource Server auto-configuration
      |
      +--> SecurityFilterChain mặc định
      |
      +--> JwtDecoder mặc định
                |
                +--> issuer metadata / JWKS
                +--> signature validation
                +--> issuer / time / audience validation
      |
      v
Bearer token request
      |
      v
Authentication + authorization
~~~

Ưu điểm:

- Ít code và dễ đọc.
- Properties dễ tách theo profile/môi trường.
- Các mặc định Spring Security được sử dụng nhất quán.
- Dễ kiểm tra thay đổi cấu hình qua deployment mà không phải sửa Java.
- Phù hợp khi issuer, JWKS, audience và scope mapping theo convention thông thường.

Giới hạn:

- Khi cần nhiều decoder, nhiều issuer, custom HTTP client, validation đặc thù hoặc cách ánh xạ principal khác chuẩn, properties có thể không đủ.
- Security chain mặc định chỉ là cấu hình nền. Nó không biết endpoint nghiệp vụ nào public, endpoint nào cần scope đọc/ghi riêng.
- Khi ứng dụng tự tạo Bean thay thế, các properties liên quan tới Bean đó không nhất thiết tiếp tục được áp dụng.

### 1.2. Cấu hình Bean tường minh

Ứng dụng tự khai báo thành phần cần tùy chỉnh:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

Bean này mô tả security chain và authorization rules. Nếu ứng dụng vẫn dùng properties để khai báo `issuer-uri`, `audiences` và algorithm policy, decoder do Boot tạo vẫn có thể được sử dụng.

Ta cũng có thể tự khai báo decoder:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    // Decoder do ứng dụng tự xây dựng
}
~~~

Khi đó ứng dụng chịu trách nhiệm đảm bảo decoder thực hiện đầy đủ các bước xác minh cần thiết.

Ưu điểm:

- Kiểm soát chính xác filter chain, matcher, authorization và exception handling.
- Có thể thêm validator, converter, HTTP client, cache hoặc key source riêng.
- Có thể cấu hình nhiều security chains hoặc nhiều issuer.
- Dễ tích hợp policy đặc thù của hệ thống.

Chi phí:

- Code nhiều hơn.
- Dễ vô tình bỏ mất issuer/audience/timestamp validation.
- Có thể làm mất các mặc định Boot trước đó đang cung cấp.
- Cần test đầy đủ hơn vì ứng dụng sở hữu nhiều trách nhiệm cấu hình.

### 1.3. So sánh nhanh

| Tiêu chí | Auto-configuration | Bean tường minh |
|---|---|---|
| Nguồn cấu hình chính | `application.yml` / properties | Java/Kotlin `@Configuration` |
| Security chain | Boot tạo chain mặc định nếu không có chain khác | Ứng dụng định nghĩa `SecurityFilterChain` |
| JWT decoder | Boot tạo từ issuer/JWKS properties nếu không có decoder thay thế | Ứng dụng tự tạo hoặc truyền decoder vào DSL |
| Opaque introspector | Boot tạo từ introspection properties nếu không có introspector thay thế | Ứng dụng tự tạo hoặc truyền introspector vào DSL |
| Authorization rules | Mặc định yêu cầu authenticated | Tự định nghĩa matcher và quyền |
| Custom validation | Giới hạn bởi properties/API hỗ trợ | Có thể kết hợp nhiều `OAuth2TokenValidator` |
| Custom authority mapping | Có thể dùng converter qua DSL/Bean phù hợp | Có thể cài converter tường minh |
| Độ phức tạp | Thấp | Cao hơn |
| Trách nhiệm bảo toàn validation | Chủ yếu do cấu hình chuẩn của Boot/Security | Ứng dụng phải kiểm tra khi thay decoder/introspector |

## 2. Auto-configuration không phải một khối duy nhất

Một cách hiểu dễ gây lỗi là: “Khi đã khai báo `SecurityFilterChain`, Spring Boot sẽ ngừng cấu hình Resource Server”. Điều đó không chính xác.

Với Servlet JWT Resource Server, cần phân biệt tối thiểu hai Bean:

1. `SecurityFilterChain`: cấu hình HTTP security và bật JWT Resource Server.
2. `JwtDecoder`: xác minh và giải mã chuỗi token.

Với opaque token, cặp tương ứng là:

1. `SecurityFilterChain`.
2. `OpaqueTokenIntrospector`.

Các thành phần này có điều kiện thay thế độc lập.

### 2.1. Ma trận Bean và hành vi back-off

| Bean ứng dụng khai báo | Bean mặc định bị thay thế/lùi lại | Thành phần khác |
|---|---|---|
| `SecurityFilterChain` | Security chain mặc định của Boot | `JwtDecoder` hoặc `OpaqueTokenIntrospector` vẫn có thể được Boot tạo |
| `JwtDecoder` | Decoder mặc định của Boot | Security chain mặc định vẫn có thể được Boot tạo |
| `OpaqueTokenIntrospector` | Introspector mặc định của Boot | Security chain mặc định vẫn có thể được Boot tạo |
| `SecurityFilterChain` + `JwtDecoder` | Cả chain mặc định và decoder mặc định | Ứng dụng kiểm soát cả HTTP policy và JWT validation |
| `SecurityFilterChain` + `OpaqueTokenIntrospector` | Cả chain mặc định và introspector mặc định | Ứng dụng kiểm soát cả HTTP policy và introspection |

Quy tắc thực tế cần nhớ:

- Có `SecurityFilterChain` riêng thì không còn dựa vào default chain của Boot để bảo vệ route.
- Có `JwtDecoder` riêng thì không nên kỳ vọng decoder đó tự nhận toàn bộ properties mà Boot đã dùng cho decoder mặc định.
- Có `OpaqueTokenIntrospector` riêng thì không nên kỳ vọng endpoint/credentials của Boot tự được gắn vào introspector custom.
- Các Bean không bị thay thế vẫn có thể tiếp tục được cấu hình tự động.

### 2.2. Cấu hình chain và decoder là hai trách nhiệm khác nhau

Ví dụ, ứng dụng khai báo:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

Bean này thay thế default chain. Nhưng `.jwt(Customizer.withDefaults())` vẫn yêu cầu JWT Resource Server hoạt động bằng decoder phù hợp trong application context. Nếu không có `JwtDecoder` custom, Boot vẫn có thể cung cấp decoder từ properties.

Ngược lại, nếu ứng dụng chỉ khai báo `JwtDecoder` Bean mà không khai báo `SecurityFilterChain`, default chain của Boot vẫn có thể được dùng và gọi decoder custom đó.

### 2.3. Đừng nhầm Bean tùy chỉnh với DSL tùy chỉnh

Có hai cách đưa decoder vào chain:

**Dùng decoder từ application context:**

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
)
~~~

Cách này cho phép Spring Security sử dụng decoder được cấu hình trong context, bao gồm decoder mặc định của Boot hoặc `JwtDecoder` Bean do ứng dụng cung cấp.

**Truyền decoder trực tiếp vào DSL:**

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.decoder(myCustomDecoder))
)
~~~

Cách thứ hai thay decoder mà chain sử dụng. Nếu truyền trực tiếp decoder, không nên giả định các properties tạo decoder mặc định của Boot vẫn được áp dụng cho decoder vừa truyền.

## 3. Trường hợp 1: chỉ dùng properties

Đây là cách đơn giản nhất khi ứng dụng dùng một issuer và JWT access token theo convention thông thường.

### 3.1. Dependencies

Với Spring Boot, có thể dùng starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Starter và BOM quản lý các module Spring Security tương ứng. Khi tự quản lý dependencies ngoài Spring Boot, JWT support cần cả Resource Server module và module JOSE để decode/verify JWT.

### 3.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
          jws-algorithms:
            - RS256
~~~

Ý nghĩa:

- `issuer-uri`: issuer identifier phải khớp claim `iss` trong JWT.
- `audiences`: các audience mà API chấp nhận.
- `jws-algorithms`: tập thuật toán ký được cho phép.

Khi có dependencies và properties phù hợp, Boot/Spring Security tự cấu hình decoder và security chain mặc định.

### 3.3. Default security chain có ý nghĩa gì?

Cấu hình mặc định tương đương về mặt ý tưởng:

~~~java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

Điều này có nghĩa request phải được xác thực. Nó chưa mô tả các route public, scope đọc/ghi, quyền admin hay object ownership.

Đối với một API production, thường cần một `SecurityFilterChain` riêng để mô tả authorization rõ hơn, trong khi vẫn để Boot tạo decoder từ properties.

### 3.4. Discovery và thời điểm gọi Authorization Server

Với `issuer-uri`, Spring Security có thể dùng Provider Configuration hoặc Authorization Server Metadata để tìm JWKS URI. Theo tài liệu Spring Security hiện hành, quá trình discovery được trì hoãn tới request đầu tiên có JWT trong các cấu hình tương ứng. Điều này giúp startup không nhất thiết phụ thuộc ngay vào khả năng truy cập Authorization Server.

Nếu Authorization Server không hỗ trợ discovery, hoặc Resource Server cần biết JWKS URI trực tiếp:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://keys.internal.example/realms/shop/jwks
          audiences:
            - orders-api
~~~

Khi khai báo cả `issuer-uri` và `jwk-set-uri` theo property, Resource Server có thể lấy keys trực tiếp từ JWKS URI nhưng vẫn validate claim `iss`.

Không tự suy đoán JWKS URI bằng cách nối chuỗi từ issuer. Hãy dùng endpoint được Authorization Server công bố hoặc xác nhận.

## 4. Trường hợp 2: khai báo SecurityFilterChain, giữ decoder tự động

Đây là kiểu kết hợp thường dùng nhất: ứng dụng cần custom authorization rules nhưng không cần tự viết decoder.

### 4.1. Properties vẫn quản lý issuer và audience

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
          jws-algorithms:
            - RS256
~~~

### 4.2. SecurityFilterChain tường minh

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
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
}
~~~

Ở đây:

- `SecurityFilterChain` là Bean do ứng dụng sở hữu.
- Default chain của Boot lùi lại.
- `JwtDecoder` vẫn có thể được Boot tạo từ `issuer-uri`, `audiences` và `jws-algorithms`.
- `.jwt(Customizer.withDefaults())` dùng decoder có trong application context.
- Authorization rules được ứng dụng định nghĩa.

Đây là một ví dụ rõ ràng về việc dùng Bean tường minh và auto-configuration cùng lúc.

### 4.3. Những điều cần tự chịu trách nhiệm khi thay chain

Khi custom chain được đăng ký, đừng cho rằng các rule mặc định vẫn còn. Ứng dụng phải xác định:

- Route nào public.
- Route nào cần authentication.
- Scope/role nào bảo vệ từng HTTP method.
- Request không match rule nào sẽ được xử lý ra sao.
- CSRF có cần bật hay tắt theo credential model.
- CORS được cấu hình thế nào.
- Session policy có phù hợp với API không.
- Exception handling và `WWW-Authenticate` có đúng contract không.
- Chain matcher có bao phủ đúng route không.

Nếu API dùng bearer token trong `Authorization` header và không dùng cookie tự động gửi từ browser, có thể đánh giá stateless session và CSRF policy phù hợp. Không tắt CSRF chỉ vì token là JWT.

## 5. Trường hợp 3: chỉ khai báo JwtDecoder Bean

Ứng dụng có thể cần custom decoder nhưng vẫn dùng security chain mặc định của Boot.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
public class JwtDecoderConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwk-set-uri}") String jwkSetUri) {

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

Properties riêng của decoder:

~~~yaml
app:
  security:
    issuer: https://login.example.com/realms/shop
    jwk-set-uri: https://keys.internal.example/realms/shop/jwks
~~~

Trong trường hợp này:

- Bean `JwtDecoder` mặc định của Boot bị thay thế.
- `SecurityFilterChain` mặc định vẫn có thể được Boot tạo.
- Chain mặc định bật JWT Resource Server và sử dụng decoder custom trong context.

### 5.1. Custom decoder phải giữ validation cần thiết

Khi tự tạo `JwtDecoder`, hãy tự bảo đảm:

- Chữ ký được xác minh bằng public key đúng.
- Thuật toán nằm trong allowlist.
- Issuer đúng.
- `exp` và `nbf` được kiểm tra.
- Audience chứa resource identifier của API.
- Token profile/type đúng contract nếu hệ thống yêu cầu.
- Clock skew được chọn theo policy.
- Claim mapping không làm thay đổi ý nghĩa security claims.

Ví dụ trên giữ validator mặc định về issuer và timestamps qua `JwtValidators.createDefaultWithIssuer(issuer)`. Nó chưa thêm audience validator; nếu API cần audience, phải bổ sung rõ ràng.

### 5.2. Custom decoder không tự nhận properties của Boot

Đây là một lỗi cấu hình phổ biến.

Giả sử trước đó có:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          audiences:
            - orders-api
          jws-algorithms:
            - RS256
~~~

Sau đó ứng dụng khai báo `@Bean JwtDecoder`. Boot có thể lùi lại khỏi decoder mặc định. Không nên mặc định rằng Bean custom sẽ tự nhận `audiences` và `jws-algorithms` từ Boot như decoder auto-configured.

Nếu custom decoder chỉ kiểm tra chữ ký và issuer, API có thể vô tình mất audience validation hoặc algorithm restriction mong muốn.

### 5.3. Bổ sung audience validator

Ví dụ validator:

~~~java
public final class OrdersAudienceValidator
        implements OAuth2TokenValidator<Jwt> {

    private final String requiredAudience;

    public OrdersAudienceValidator(String requiredAudience) {
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience().contains(this.requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Required audience is missing",
            null
        );

        return OAuth2TokenValidatorResult.failure(error);
    }
}
~~~

Kết hợp với issuer và timestamp validators:

~~~java
@Bean
JwtDecoder jwtDecoder(
        @Value("${app.security.issuer}") String issuer,
        @Value("${app.security.jwk-set-uri}") String jwkSetUri,
        @Value("${app.security.audience}") String audience) {

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri(jwkSetUri)
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .build();

    OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audienceValidator =
        new OrdersAudienceValidator(audience);

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            defaults,
            audienceValidator
        )
    );

    return decoder;
}
~~~

Các imports chính:

~~~java
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
~~~

Đoạn code minh họa cách kết hợp validators. Nếu ứng dụng dùng RFC 9068, custom `typ`, multi-issuer hoặc policy khác, cần dùng validator tương ứng và test token sai profile.

## 6. Trường hợp 4: thay decoder trực tiếp trong DSL

Spring Security cung cấp nhiều mức tùy chỉnh trong `oauth2ResourceServer().jwt()`.

### 6.1. Dùng `jwkSetUri()`

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwkSetUri("https://keys.internal.example/realms/shop/jwks")
            )
        )
        .build();
}
~~~

`jwkSetUri()` trong DSL có độ ưu tiên cao hơn JWK Set URI được cấu hình bằng property.

Dùng cách này khi cần ghi đè JWKS endpoint ở cấp chain. Tuy nhiên, cần kiểm tra rõ issuer validation và các validators khác trong cấu hình cuối cùng. Không chỉ thay URI rồi giả định mọi validator từ property đã được giữ nguyên trong mọi version/cách wiring.

Nếu muốn bỏ metadata discovery nhưng vẫn giữ issuer validation theo property, cấu hình `issuer-uri` cùng `jwk-set-uri` trong properties là cách rõ ràng.

### 6.2. Dùng `decoder()`

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    JwtDecoder decoder = createOrdersJwtDecoder();

    return http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.decoder(decoder))
        )
        .build();
}
~~~

`decoder()` thay decoder mà DSL sử dụng và có thể thay thế toàn bộ auto-configuration decoder của Boot đối với chain đó.

Phù hợp khi cần:

- Custom algorithm allowlist.
- Custom `OAuth2TokenValidator`.
- Custom JWK source/cache/HTTP client.
- Nhiều issuer hoặc decoder routing.
- Claim-set conversion.
- Token profile validation.
- Decoder được khởi tạo bởi một module bảo mật riêng.

Vì decoder được truyền trực tiếp, ứng dụng phải kiểm tra các validators và key source của nó. Không trông đợi các `spring.security.oauth2.resourceserver.jwt.*` properties tự động được hợp nhất vào object đó.

### 6.3. Thay converter không đồng nghĩa thay decoder

Ví dụ custom authority mapping:

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter authorities =
        new JwtGrantedAuthoritiesConverter();

    authorities.setAuthoritiesClaimName("permissions");
    authorities.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(authorities);

    return converter;
}
~~~

Gắn converter vào chain:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtAuthenticationConverter jwtAuthenticationConverter)
        throws Exception {

    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(jwtAuthenticationConverter)
            )
        )
        .build();
}
~~~

Converter chỉ thay cách ánh xạ `Jwt` đã xác minh thành authorities/Authentication. Nó không thay:

- JWKS URI.
- Chữ ký.
- Issuer validation.
- Timestamp validation.
- Audience validation.

Nếu chỉ cần đổi claim chứa permissions, hãy giữ decoder mặc định và thay converter. Không cần tạo một `JwtDecoder` mới chỉ để map authorities.

## 7. Opaque token: auto-config và Bean tường minh

Opaque token dùng introspection thay cho xác minh chữ ký JWT ở Resource Server.

### 7.1. Chỉ dùng properties

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

Spring Boot/Spring Security có thể tự cấu hình:

- Default `SecurityFilterChain` với opaque token support.
- `OpaqueTokenIntrospector` sử dụng introspection URI và credentials.
- Mapping scopes thành authorities có prefix `SCOPE_`.

Khi request gửi Bearer token, introspector gọi endpoint và kiểm tra response có `active=true` hay không. Principal mặc định là `OAuth2AuthenticatedPrincipal`; `Authentication` thường là `BearerTokenAuthentication`.

### 7.2. Custom chain, vẫn giữ introspector tự động

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
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
~~~

Nếu không có `OpaqueTokenIntrospector` Bean thay thế, cấu hình introspection properties vẫn có thể được dùng để tạo introspector mặc định.

### 7.3. Khai báo `OpaqueTokenIntrospector` Bean

~~~java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${app.security.introspection-uri}") String uri,
        @Value("${app.security.client-id}") String clientId,
        @Value("${app.security.client-secret}") String clientSecret) {

    return SpringOpaqueTokenIntrospector
        .withIntrospectionUri(uri)
        .clientId(clientId)
        .clientSecret(clientSecret)
        .build();
}
~~~

Bean custom thay thế introspector mặc định của Boot.

Nếu custom chain gọi:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
)
~~~

thì cấu hình cần dùng introspector tương ứng trong context.

Khi tự tạo introspector, ứng dụng phải tự bảo đảm:

- Introspection URI đúng môi trường.
- Client authentication đúng method và credentials.
- TLS được xác minh.
- Timeout/connect/read policy phù hợp.
- `active=false` bị từ chối.
- Scope/attributes được map đúng.
- Audience/resource và issuer được kiểm tra theo contract của AS.
- Lỗi network không bị coi là token active.

### 7.4. Ghi đè URI và credentials trong DSL

Có thể cấu hình trực tiếp:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(opaque -> opaque
        .introspectionUri("https://login.example.com/oauth2/introspect")
        .introspectionClientCredentials(
            "orders-resource-server",
            introspectionClientSecret
        )
    )
)
~~~

`introspectionUri()` và `introspectionClientCredentials()` trong DSL có thể ghi đè giá trị properties.

### 7.5. Truyền introspector custom trong DSL

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(opaque -> opaque
        .introspector(customIntrospector)
    )
)
~~~

`introspector()` thay introspector auto-configured. Cách này hữu ích khi cần decorator, caching, custom HTTP client, response adaptation hoặc kiểm tra attributes bổ sung.

Không dùng đồng thời nhiều nguồn cấu hình một cách mơ hồ. Hãy xác định URI/credentials nằm ở properties, Bean hay DSL, và kiểm tra object thực tế mà chain đang dùng.

## 8. So sánh các mức thay thế của JWT và opaque token

| Nhu cầu | JWT | Opaque token |
|---|---|---|
| Chỉ cấu hình endpoint bằng properties | `issuer-uri`, `jwk-set-uri` | `introspection-uri`, `client-id`, `client-secret` |
| Tùy chỉnh route/authorization | Khai báo `SecurityFilterChain` | Khai báo `SecurityFilterChain` |
| Tùy chỉnh cách xác minh token | `JwtDecoder` Bean hoặc `.decoder()` | `OpaqueTokenIntrospector` Bean hoặc `.introspector()` |
| Đổi nguồn key/endpoint | `.jwkSetUri()` hoặc properties | `.introspectionUri()` |
| Đổi credentials | Thường liên quan key source/HTTP client | `.introspectionClientCredentials()` |
| Đổi authority mapping | `JwtAuthenticationConverter` | `OpaqueTokenAuthenticationConverter` hoặc authority mapping trong introspector |
| Kiểm tra issuer/audience | JWT validators | Dựa trên introspection response và contract |
| Xác minh token | Chữ ký + claims | AS trả `active=true` và attributes |

JWT và opaque token có thể cùng dùng Bearer scheme ở HTTP layer, nhưng thành phần xác minh khác nhau. Không truyền `JwtDecoder` vào opaque configurer hoặc `OpaqueTokenIntrospector` vào JWT configurer.

## 9. WebFlux: cùng nguyên tắc, Bean type khác

Với WebFlux, các loại Bean tương ứng là:

| Servlet | WebFlux |
|---|---|
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `JwtDecoder` | `ReactiveJwtDecoder` |
| `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| `JwtAuthenticationProvider` | Reactive authentication manager/provider path |
| `MockMvc` | `WebTestClient` |

Spring Boot có thể tự cấu hình default `SecurityWebFilterChain` và decoder/introspector reactive. Khi ứng dụng khai báo Bean reactive tường minh, quy tắc back-off tương tự áp dụng theo đúng loại Bean.

### 9.1. Properties cho Reactive JWT Resource Server

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

### 9.2. SecurityWebFilterChain tường minh

~~~java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http) {

    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public/**").permitAll()
            .pathMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

Nếu không khai báo `ReactiveJwtDecoder` Bean thay thế, Boot vẫn có thể tạo decoder từ properties.

### 9.3. Reactive decoder tường minh

~~~java
@Bean
ReactiveJwtDecoder reactiveJwtDecoder(
        @Value("${app.security.issuer}") String issuer,
        @Value("${app.security.jwk-set-uri}") String jwkSetUri) {

    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri).build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(issuer)
    );

    return decoder;
}
~~~

Đây là ví dụ reactive; decoder đồng bộ `JwtDecoder` không thay thế được `ReactiveJwtDecoder`.

### 9.4. Reactive opaque introspector

Khi dùng opaque token trong WebFlux, sử dụng `ReactiveOpaqueTokenIntrospector`. Không đưa một introspector đồng bộ có network I/O vào event loop chỉ bằng cách gọi nó trong reactive pipeline.

Các properties và nguyên tắc thay thế tương tự Servlet, nhưng cần dùng đúng reactive API của Spring Security version đang chạy.

## 10. Nhiều SecurityFilterChain: custom chain có thể làm thay đổi toàn bộ routing

Khi có ít nhất một `SecurityFilterChain` tường minh, không nên dựa vào default chain của Boot để tự bảo vệ các route còn lại. Nếu ứng dụng cần nhiều vùng bảo mật, hãy định nghĩa từng chain với matcher và thứ tự rõ ràng.

Ví dụ:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}

@Bean
@Order(2)
SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/assets/**", "/login").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

`FilterChainProxy` chọn chain đầu tiên match request. Vì vậy:

- Chain `/api/**` phải có thứ tự trước chain tổng quát.
- Chain browser không được vô tình nhận request API.
- Phải có policy cho các route không match chain đặc hiệu.
- Không để route nhạy cảm lọt qua chain có policy yếu hơn.
- Nếu có fallback chain, hãy cấu hình `denyAll()` hoặc rule rõ ràng cho phần còn lại.

Một `JwtDecoder` Bean có thể được dùng bởi chain JWT; chain form login không cần decoder. Không tạo decoder riêng chỉ vì có thêm một chain nếu trust policy và token validation giống nhau.

## 11. Khi nào nên dùng properties, khi nào cần Bean riêng?

### 11.1. Chỉ dùng properties khi

- Chỉ có một issuer hoặc một cấu hình Resource Server đơn giản.
- JWT dùng JWKS endpoint tiêu chuẩn.
- Audience và algorithm policy có thể mô tả bằng properties.
- Default timestamps/issuer validation đáp ứng contract.
- Opaque token dùng introspection URI và client credentials thông thường.
- Scope mapping theo convention `SCOPE_`.
- Không cần custom HTTP client hoặc cache phức tạp.

### 11.2. Chỉ custom SecurityFilterChain khi

- Cần public/private route rõ ràng.
- Cần rule theo HTTP method và scope.
- Cần nhiều chains cho API, admin, browser.
- Cần custom CORS, CSRF, session, exception handling.
- Decoder/introspector mặc định vẫn đáp ứng yêu cầu.

Đây là trường hợp giữ decoder/introspector auto-configured thường đơn giản và an toàn.

### 11.3. Custom JwtDecoder khi

- Cần validator phức tạp hoặc token profile riêng.
- Cần nhiều issuer và decoder khác nhau.
- Cần JWK source/HTTP client/cache riêng.
- Cần algorithm policy đặc thù.
- Cần custom claim-set conversion.
- Cần tích hợp key management hoặc trust source riêng.

### 11.4. Custom OpaqueTokenIntrospector khi

- Cần HTTP client và timeout riêng.
- Cần cache introspection theo revocation SLA.
- Cần bổ sung validation cho issuer/audience/tenant.
- Cần chuyển đổi response của AS sang principal nội bộ.
- Cần metrics, tracing hoặc retry policy có giới hạn.
- Cần phối hợp nhiều introspection sources.

### 11.5. Tránh custom Bean chỉ để thay đổi một giá trị đơn giản

Nếu chỉ cần đổi issuer hoặc audience, hãy ưu tiên properties. Nếu chỉ cần đổi authority mapping, hãy thay converter. Nếu chỉ cần đổi JWKS URI, dùng property hoặc DSL phù hợp.

Custom decoder làm ứng dụng chịu trách nhiệm nhiều hơn về validation. Không nên tạo decoder riêng chỉ vì muốn đổi một thuộc tính mà Boot đã hỗ trợ.

## 12. Những khác biệt quan trọng khi migration từ properties sang Bean

Giả sử ứng dụng ban đầu:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          audiences:
            - orders-api
          jws-algorithms:
            - RS256
~~~

Sau đó nhóm phát triển tạo decoder:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    return NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();
}
~~~

Việc này có thể khiến Boot ngừng tạo decoder mặc định. Nếu decoder mới không được cấu hình issuer, audience và algorithm policy, ứng dụng đã thay đổi security behavior.

### 12.1. Những gì cần kiểm tra khi thay decoder

| Cấu hình trước | Khi tự tạo decoder phải kiểm tra |
|---|---|
| `issuer-uri` | Validator `iss` vẫn được bật |
| `audiences` | Audience validator vẫn có |
| `jws-algorithms` | Decoder chỉ cho phép thuật toán đã duyệt |
| Timestamp validation | `exp`, `nbf` và clock skew được giữ |
| JWKS URI | Đúng issuer/key source và TLS |
| JWKS cache | TTL, refresh, timeout và eviction |
| Token type/profile | Có validator đúng profile nếu yêu cầu |
| Custom claim conversion | Không làm thay đổi trust semantics |
| Error handling | Invalid token không bị fail open |

### 12.2. Những gì cần kiểm tra khi thay chain

| Cấu hình mặc định | Khi tự tạo `SecurityFilterChain` |
|---|---|
| Mọi request cần authentication | Viết matcher và rule theo route |
| JWT Resource Server | Bật `.oauth2ResourceServer().jwt(...)` |
| Default entry point | Giữ hoặc thay bằng handler đúng protocol |
| CSRF/CORS defaults | Đánh giá theo credential model |
| Session behavior | Xác định stateless/stateful rõ ràng |
| Fallback behavior | Không để request lọt qua chain khác |
| Scope mapping | Đảm bảo authority prefix khớp rule |

### 12.3. Migration nên chia nhỏ

Một quy trình dễ kiểm soát:

1. Ghi nhận properties và behavior hiện tại.
2. Thêm custom `SecurityFilterChain`, vẫn gọi `.jwt(Customizer.withDefaults())`.
3. Test public/private routes và scope rules.
4. Xác nhận decoder vẫn là decoder được Boot cấu hình.
5. Chỉ khi có nhu cầu thực sự mới thêm `JwtDecoder` Bean.
6. Khi thêm decoder, chuyển đầy đủ issuer/audience/algorithm/time/profile validators.
7. Test token hợp lệ và token sai.
8. Kiểm tra startup behavior và JWKS network calls.
9. Triển khai staging và so sánh authentication/authorization metrics.
10. Sau khi xác nhận, mới loại bỏ properties không còn được sử dụng.

## 13. Test để biết Bean nào đang được dùng

Đừng chỉ kiểm tra ứng dụng khởi động thành công. Hãy kiểm tra hành vi và dependency thực tế.

### 13.1. Test HTTP authorization qua filter chain

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerConfigurationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void privateEndpointRequiresBearerToken() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void publicEndpointDoesNotRequireToken() throws Exception {
        mvc.perform(get("/api/public/health"))
            .andExpect(status().isOk());
    }
}
~~~

Test phải giữ MockMvc filters được bật. Không dùng `@AutoConfigureMockMvc(addFilters = false)` khi mục tiêu là kiểm tra Spring Security.

### 13.2. Test decoder được sử dụng

Có thể kiểm tra Bean trong application context:

~~~java
@Autowired
JwtDecoder jwtDecoder;
~~~

Nếu cần chứng minh bearer filter gọi đúng decoder, gửi `Authorization: Bearer ...` qua MockMvc và dùng test decoder hoặc Mockito spy phù hợp. Không dùng `.with(jwt())` để kiểm tra decoder vì request post processor này tạo authentication giả lập và bỏ qua decoder thông thường.

### 13.3. Test signature, issuer và audience

Với decoder thật:

- Tạo test RSA key pair.
- Ký JWT bằng private test key.
- Cấu hình JWKS/public key test.
- Gửi token bằng Bearer header.
- Xác nhận token đúng chữ ký, issuer, audience được chấp nhận.
- Gửi token ký bằng key khác và xác nhận 401.
- Gửi token sai issuer/audience và xác nhận bị từ chối.
- Xác nhận scope thiếu dẫn tới 403 sau authentication.

Không dùng signing key production trong tests.

### 13.4. Test converter riêng với decoder

Nếu thay `JwtAuthenticationConverter`, tạo token có claims theo contract và kiểm tra authorities sau authentication.

Ví dụ:

~~~text
JWT claim:
  permissions = ["orders.read"]

Expected Authentication:
  SCOPE_orders.read
~~~

Test converter unit có thể dựng `Jwt` trực tiếp. Integration test cần Bearer token thật để xác nhận converter được gọi sau decoder.

### 13.5. Test opaque introspection

Dùng HTTP stub/test Authorization Server:

- `active=true` với scope đúng.
- `active=false`.
- Scope thiếu.
- Audience/resource không đúng theo contract.
- Introspection client credentials sai.
- Timeout/5xx.
- Response malformed.

Gửi Bearer header qua filter chain. Không dùng `.with(opaqueToken())` nếu mục tiêu là xác nhận introspector thật được gọi.

### 13.6. Test nhiều SecurityFilterChain

Tạo request cho từng matcher:

| Request | Chain mong đợi | Kết quả cần kiểm tra |
|---|---|---|
| `/api/orders` | API chain | Bearer authentication |
| `/api/public/health` | API chain | Permit all |
| `/login` | Browser chain | Login behavior |
| `/admin/reports` | Admin chain nếu có | Admin authorities |
| Route không match chain đặc hiệu | Fallback | Deny/authentication theo policy |

Kiểm tra `@Order` và matcher overlap. Một chain tổng quát đứng trước chain đặc hiệu có thể khiến chain đặc hiệu không bao giờ được chọn.

### 13.7. Test điều kiện auto-configuration

Khi cần chẩn đoán vì sao Bean mặc định không xuất hiện:

- Khởi động ứng dụng với `--debug` để xem condition evaluation report.
- Kiểm tra application context có Bean nào thuộc type `SecurityFilterChain`, `JwtDecoder`, `OpaqueTokenIntrospector` hay không.
- Xác nhận profile đang hoạt động và properties đã bind đúng.
- Kiểm tra dependency/classpath có đúng Servlet hay Reactive stack.
- Kiểm tra có cấu hình test nào thay thế Bean production không.

Nếu dùng Actuator và đã bật endpoint conditions một cách an toàn, có thể dùng condition report để điều tra. Không công khai endpoint chẩn đoán cấu hình nhạy cảm ra Internet.

## 14. Lỗi phổ biến khi kết hợp auto-config và Bean tường minh

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Có custom chain nhưng API không nhận Bearer token | Chain không gọi `oauth2ResourceServer` hoặc matcher không đúng | Kiểm tra chain và request matcher |
| Custom chain chạy nhưng không có `JwtDecoder` | Không có properties hợp lệ và không có decoder Bean | Kiểm tra điều kiện tạo decoder |
| JWT đúng chữ ký nhưng issuer sai vẫn được nhận | Custom decoder không giữ issuer validator | Kiểm tra `JwtValidators` |
| Token API khác được chấp nhận | Custom decoder thiếu audience validator | Kiểm tra `aud` |
| Thuật toán ngoài policy được chấp nhận | Custom decoder allowlist quá rộng hoặc không rõ | Kiểm tra JWS algorithms |
| Scope không được ánh xạ | Converter đọc sai claim/prefix | Kiểm tra `JwtAuthenticationConverter` |
| Opaque token luôn inactive | Introspection URI/credentials sai hoặc response không có `active=true` | Kiểm tra introspector |
| Opaque token active nhưng authority thiếu | Mapping scopes/attributes sai | Kiểm tra response và converter |
| Route public vẫn bị yêu cầu token | Matcher/chain order sai hoặc Bearer token malformed được gửi | Kiểm tra filter chain |
| Một route không được bảo vệ | Custom chain không match và thiếu fallback | Kiểm tra chain coverage |
| App start thất bại khi AS down sau khi thêm decoder Bean | Decoder custom thực hiện discovery eager lúc tạo Bean | Kiểm tra discovery/JWKS initialization strategy |
| Properties đổi nhưng behavior không đổi | Custom Bean/DSL đã thay component auto-config | Xác định source of truth |
| Hai introspection calls cho một request | Có nhiều chain/filter hoặc custom decorator gọi lặp | Kiểm tra wiring và call path |
| Reactive app có lỗi type Bean | Dùng `JwtDecoder` thay vì `ReactiveJwtDecoder` | Dùng đúng reactive types |

## 15. Cấu hình nên tránh

### 15.1. Custom chain nhưng quên bật Resource Server

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .build();
}
~~~

Chain này yêu cầu authentication nhưng chưa cấu hình JWT/opaque bearer support. Có thể ứng dụng dùng một authentication mechanism khác hoặc request bị từ chối mà không có Resource Server behavior mong muốn.

Nếu API cần JWT:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
)
~~~

### 15.2. Custom decoder chỉ parse claims

Không được tự decode Base64 payload rồi coi claims là trusted. Decoder phải xác minh chữ ký, issuer, audience, timestamp và token profile theo policy.

### 15.3. Custom decoder thay thế nhưng quên validators

Một decoder Bean không tự kế thừa toàn bộ property-based validation của Boot. Hãy cấu hình validators trong decoder custom.

### 15.4. Tạo decoder mới cho mỗi request

`JwtDecoder` là thành phần dùng chung trong application context. Không tạo decoder mới bên trong controller/filter cho mỗi request. Việc đó có thể lặp discovery, tạo cache mới và làm tăng tải JWKS.

### 15.5. Dùng cùng một Bean type cho hai trust policies khác nhau

Nếu hai issuer có audience, algorithm hoặc validator khác nhau, đừng ép chúng vào một decoder global với policy quá rộng. Hãy dùng issuer-aware resolver và decoder riêng theo trust context.

### 15.6. Khai báo quá nhiều chain không có matcher

Một chain không có matcher đặc hiệu có thể match rộng và che các chain khác. Dùng `securityMatcher`, `@Order` và fallback policy rõ ràng.

### 15.7. Trộn Servlet và Reactive Bean

Không dùng:

- `SecurityFilterChain` trong WebFlux thay `SecurityWebFilterChain`.
- `JwtDecoder` thay `ReactiveJwtDecoder`.
- `OpaqueTokenIntrospector` thay `ReactiveOpaqueTokenIntrospector`.
- `MockMvc` thay `WebTestClient`.

Boot chọn application type và auto-configuration tương ứng. Bean type phải phù hợp với stack đang chạy.

### 15.8. Để secret trong Java source

Không hardcode introspection client secret trong `@Bean`. Dùng secret manager, environment variable hoặc externalized configuration có kiểm soát.

### 15.9. Cấu hình cùng một giá trị ở nhiều nơi

Nếu issuer/JWKS URI nằm trong YAML, một `@Value`, một `@Bean` và một DSL hardcode, việc đổi môi trường dễ tạo cấu hình lệch nhau. Chọn một nguồn cấu hình chính và tránh ghi đè không cần thiết.

## 16. Checklist trước khi chọn cách cấu hình

### Khi dùng auto-configuration

- [ ] Có đúng Resource Server dependencies.
- [ ] `issuer-uri` hoặc `jwk-set-uri` đúng môi trường.
- [ ] Audience được cấu hình nếu API yêu cầu.
- [ ] Algorithm allowlist phù hợp issuer.
- [ ] Introspection URI và credentials đúng nếu dùng opaque token.
- [ ] Default authorization policy đủ hoặc đã thay bằng chain phù hợp.
- [ ] Không có custom Bean vô tình làm auto-configuration back off.
- [ ] Đã test token hợp lệ và token sai.

### Khi khai báo SecurityFilterChain tường minh

- [ ] Đã cấu hình `.oauth2ResourceServer().jwt()` hoặc `.opaqueToken()`.
- [ ] Đã định nghĩa public/private route.
- [ ] Scope/authority rules đúng.
- [ ] Matcher và `@Order` không che nhau.
- [ ] Có fallback policy.
- [ ] CSRF/CORS/session policy phù hợp.
- [ ] Entry point và access-denied handler phù hợp.
- [ ] Decoder/introspector mặc định vẫn có trong context nếu muốn dùng auto-config.

### Khi khai báo JwtDecoder tường minh

- [ ] JWKS URI/key source đáng tin.
- [ ] Chữ ký được xác minh.
- [ ] Algorithm allowlist rõ.
- [ ] Issuer validator được giữ.
- [ ] Timestamp validator được giữ.
- [ ] Audience validator được thêm.
- [ ] Token type/profile được kiểm tra nếu yêu cầu.
- [ ] Cache/timeout/rotation được cân nhắc.
- [ ] Không phụ thuộc nhầm vào properties mà Boot không còn áp dụng.
- [ ] Integration tests dùng Bearer token thật.

### Khi khai báo OpaqueTokenIntrospector tường minh

- [ ] Endpoint và client authentication đúng.
- [ ] TLS và timeout được cấu hình.
- [ ] `active=false` bị từ chối.
- [ ] Scope/authority mapping đúng.
- [ ] Audience/resource binding được kiểm tra theo contract.
- [ ] Cache TTL đáp ứng revocation SLA.
- [ ] Không fail open khi AS lỗi.
- [ ] Tests xác nhận introspection được gọi.

## 17. Lộ trình chọn cấu hình theo nhu cầu

Có thể bắt đầu bằng câu hỏi: “Phần nào thực sự cần khác mặc định?”

~~~text
Bắt đầu với Resource Server
          |
          v
Chỉ cần issuer/JWKS/audience/scope convention?
          |
       Có | Không
          | 
          v
   Dùng properties
          |
          v
Cần route rules, public paths, multiple chains?
          |
       Có | Không
          |
          v
Khai báo SecurityFilterChain
và giữ decoder/introspector mặc định
          |
          v
Cần custom validation, key source,
HTTP client, cache hoặc token mapping?
          |
       Có | Không
          |
          v
Khai báo decoder/introspector riêng
và tự giữ đầy đủ security validations
~~~

Không nhất thiết phải đi hết mọi bước. Nếu properties đã đủ, không cần thêm Java Bean. Nếu chỉ cần custom authorization, một `SecurityFilterChain` là đủ. Chỉ thay decoder/introspector khi yêu cầu xác minh token thực sự khác mặc định.

## 18. Câu hỏi tự kiểm tra

**1.** Spring Boot Resource Server auto-configuration có những thành phần chính nào?

> Với JWT là default `SecurityFilterChain` và `JwtDecoder`; với opaque token là default `SecurityFilterChain` và `OpaqueTokenIntrospector`.

**2.** Khi khai báo `SecurityFilterChain` riêng, `JwtDecoder` mặc định có tự động biến mất không?

> Không. Boot default chain lùi lại; decoder vẫn có thể được Boot tạo nếu ứng dụng không cung cấp decoder khác.

**3.** Khi khai báo `JwtDecoder` Bean riêng, default security chain có còn không?

> Có thể còn. Hai Bean có điều kiện thay thế độc lập.

**4.** `.jwt(Customizer.withDefaults())` có ý nghĩa gì?

> Bật JWT Resource Server trong chain và dùng decoder phù hợp có trong application context.

**5.** `.jwkSetUri()` và `.decoder()` khác nhau thế nào?

> `jwkSetUri()` cung cấp JWKS URI trong DSL và ưu tiên hơn property; `decoder()` thay decoder mà chain sử dụng.

**6.** Khai báo `JwtDecoder` custom có tự kế thừa `audiences` từ Boot không?

> Không nên giả định như vậy. Khi Boot lùi lại khỏi decoder mặc định, custom decoder phải tự áp dụng audience validation cần thiết.

**7.** `JwtAuthenticationConverter` thay đổi phần nào?

> Nó chuyển JWT đã xác minh thành Authentication/authorities; nó không thay chữ ký, issuer, audience hoặc timestamp validation.

**8.** Khi dùng opaque token, Bean nào tương ứng với `JwtDecoder`?

> `OpaqueTokenIntrospector`.

**9.** `.introspector()` khác `.introspectionUri()` như thế nào?

> `.introspectionUri()` cấu hình endpoint/credentials cho introspector mặc định; `.introspector()` thay bằng implementation custom.

**10.** Nếu chỉ cần custom route authorization thì có cần custom decoder không?

> Không. Có thể khai báo `SecurityFilterChain` và giữ decoder tự động.

**11.** Khi custom chain được khai báo, vì sao cần fallback policy?

> Vì default chain của Boot đã lùi lại; route không match chain đặc hiệu cần được xử lý rõ ràng.

**12.** WebFlux dùng Bean type nào thay `JwtDecoder`?

> `ReactiveJwtDecoder`.

**13.** Có thể dùng `OpaqueTokenIntrospector` đồng bộ trong WebFlux không?

> Không nên dùng cho reactive request path nếu nó thực hiện blocking I/O; hãy dùng `ReactiveOpaqueTokenIntrospector`.

**14.** Vì sao custom decoder có thể làm ứng dụng mất audience validation?

> Vì Boot không còn tạo decoder mặc định để áp dụng properties; decoder custom phải tự cấu hình validator.

**15.** Làm thế nào xác nhận decoder thật được dùng?

> Gửi Bearer token qua filter chain thật và kiểm tra decoder/validation path; `.with(jwt())` không gọi decoder thông thường.

**16.** Có nên khai báo issuer/JWKS URI ở nhiều nơi không?

> Không nên nếu không có lý do. Nên chọn một nguồn cấu hình chính để tránh giá trị bị lệch giữa properties, Bean và DSL.

## 19. Tài liệu tham khảo

- [Spring Boot — OAuth2](https://docs.spring.io/spring-boot/reference/security/oauth2.html): Resource Server properties, issuer URI, JWK Set URI và audience.
- [Spring Security — Servlet Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): default chain, decoder, override/replacement, trusted algorithms, validators và converter.
- [Spring Security — Servlet Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): default introspector, `introspectionUri()`, `introspector()` và authentication flow.
- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `SecurityWebFilterChain`, `ReactiveJwtDecoder` và auto-configuration trong WebFlux.
- [Spring Security — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): `ReactiveOpaqueTokenIntrospector` và reactive introspection.
- [Spring Security — `JwtDecoder` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoder.html): interface giải mã và xác minh JWT.
- [Spring Security — `OpaqueTokenIntrospector` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html): interface introspection.
- [Spring Security — `SecurityFilterChain` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/SecurityFilterChain.html): Servlet security chain.
- [Spring Security — `SecurityWebFilterChain` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/SecurityWebFilterChain.html): Reactive security chain.
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): kiểm tra JWT/opaque authorization và giới hạn mock authentication.
- [Spring Security — Testing OAuth 2.0 with WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): reactive security testing.

**Kết luận:** Cấu hình Bean tường minh và auto-configuration có thể cùng tồn tại. Khai báo `SecurityFilterChain` thay security chain mặc định nhưng không tự loại `JwtDecoder` hoặc `OpaqueTokenIntrospector`; khai báo decoder/introspector riêng chỉ thay đúng thành phần xác minh token tương ứng. Hãy dùng properties cho issuer, JWKS, audience và introspection khi mặc định đáp ứng yêu cầu; khai báo chain riêng khi cần route authorization; chỉ thay decoder/introspector khi cần validation hoặc integration đặc thù, và khi đó phải tự giữ đầy đủ signature, issuer, timestamp, audience, active-state và token-policy checks.
