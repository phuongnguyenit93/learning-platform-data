# AuthenticationManagerResolver cho nhiều issuer với danh sách tin cậy trong Spring Security Servlet

## 1. Bài toán của Resource Server đa issuer

Trong một hệ thống đa tổ chức, API có thể nhận access token do nhiều Authorization Server hoặc nhiều realm độc lập phát hành. Ví dụ ứng dụng quản lý đơn hàng chấp nhận người dùng thuộc tổ chức A và B:

- **Issuer A:** https://id-a.example.org/realms/a.
- **Issuer B:** https://id-b.example.org/realms/b.
- **Resource Server:** một Spring MVC API tại https://api.example.org.

Cả hai client gửi access token trong request:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.org
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Accept: application/json
~~~

Đoạn Bearer token trên chỉ mô phỏng cấu trúc. Access token thực tế là credential nhạy cảm; không được sao chép token vào mã nguồn, query string, ticket hoặc log.

Khi có đúng một issuer, Resource Server thường cấu hình một **JwtDecoder** dựa trên issuer-uri. Khi có nhiều issuer, mỗi issuer có thể dùng JWK Set, khóa ký, policy, tenant và metadata khác nhau. Cần một cơ chế quyết định **AuthenticationManager nào kiểm tra token hiện tại** mà không bỏ qua tính xác thực.

**AuthenticationManagerResolver<T>** là giao diện Spring Security thực hiện lựa chọn đó. Với Servlet stack, T thường là **HttpServletRequest**. **JwtIssuerAuthenticationManagerResolver** là triển khai chuyên dụng cho JWT: xem claim **iss** để chọn manager tương ứng.

Điểm quan trọng nhất: giá trị iss được đọc **trước khi chữ ký JWT được xác minh**. Nó chỉ là gợi ý định tuyến không đáng tin, **không phải bằng chứng** cho biết token đến từ issuer hợp pháp. Hệ thống phải từ chối issuer ngoài danh sách được quản trị và chỉ dùng decoder/JWK phù hợp cho những issuer đã được phê duyệt.

Mục tiêu bài học là hiểu FilterChainProxy, BearerTokenAuthenticationFilter, resolver, cơ chế tin cậy, code Java 17+ dùng Spring Boot 3.x / Spring Security 6.x, kiểm thử và cách xử lý lỗi.

## 2. Phân biệt resolver, authentication và authorization

| Khái niệm | Câu hỏi nó trả lời |
| --- | --- |
| AuthenticationManagerResolver | Request này nên chuyển cho manager nào kiểm tra credential? |
| AuthenticationManager | Credential có chứng minh được danh tính hợp lệ không? |
| JwtAuthenticationProvider | Dùng decoder JWT để xác minh chữ ký/claims và tạo Authentication |
| JwtDecoder | JWT có chữ ký, issuer, thời gian và claims hợp lệ theo policy không? |
| AuthorizationFilter | Principal đã xác thực có quyền gọi endpoint không? |
| Business authorization | Principal có quyền thao tác đúng bản ghi hoặc tenant cụ thể không? |

Ví dụ: access token của A có thể hợp lệ và có scope orders.read. Điều này không có nghĩa nó được phép xem đơn hàng của tenant B. Resolver xác định cách kiểm tra token, rồi authorization ở lớp API và nghiệp vụ vẫn cần kiểm tra quyền trên tài nguyên.

**Resource Server không tự cấp access token.** Authorization Server phát hành token; OAuth client nhận và gửi token; Resource Server chỉ kiểm tra và quyết định cho phép truy cập protected resources.

**Access token không phải ID token.** ID token của OpenID Connect thường hướng tới client đăng nhập; API phải yêu cầu access token đúng audience, issuer, token profile và quyền.

## 3. Luồng xử lý trong FilterChainProxy

~~~text
Client gửi Authorization: Bearer <token>
                  |
                  v
Servlet container (Tomcat/Jetty...)
                  |
                  v
DelegatingFilterProxy -> FilterChainProxy
                  |
                  v
SecurityFilterChain phù hợp
                  |
                  v
BearerTokenAuthenticationFilter
                  |
                  +--> BearerTokenResolver đọc Authorization header
                  |
                  +--> BearerTokenAuthenticationToken (chưa xác thực)
                  |
                  +--> AuthenticationManagerResolver<HttpServletRequest>
                          |
                          v
                     Đọc iss từ JWT
                     CHƯA VERIFY SIGNATURE
                          |
                     Exact allowlist lookup
                      /             \
                  Issuer lạ       Issuer A/B đã duyệt
                    |                 |
                  Từ chối       AuthenticationManager A/B
                                      |
                                 JwtAuthenticationProvider
                                      |
                                 JwtDecoder A/B
                                      |
                      Kiểm tra chữ ký, exp, nbf, iss, aud
                                      |
                          JwtAuthenticationToken
                                      |
                                SecurityContext
                                      |
                              AuthorizationFilter
                               /             \
                          Thiếu quyền       Đủ quyền
                           -> 403              |
                                              v
                                  DispatcherServlet/Controller
~~~

Sơ đồ phản ánh các bước chức năng; vị trí tương đối của những filter khác có thể khác theo cấu hình. BearerTokenAuthenticationFilter nằm trong security filter chain do Spring Security tạo khi bật **oauth2ResourceServer(...)**.

Nếu không có token, BearerTokenAuthenticationFilter thường để request đi tiếp. Endpoint được permitAll có thể hoạt động; endpoint yêu cầu authentication sẽ nhận challenge 401 ở giai đoạn bảo vệ quyền. Nếu có token hỏng hoặc không được tin cậy, quá trình authentication thất bại trước khi controller xử lý.

**Resolver không trực tiếp ký, giải mã hay xác thực JWT.** Nó chọn AuthenticationManager; manager mới phải làm bước kiểm tra mật mã và token validators.

## 4. Vì sao iss phải được coi là untrusted?

JWT dạng JWS thường có ba phần:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Payload ví dụ:

~~~json
{
  "iss": "https://id-a.example.org/realms/a",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000000
}
~~~

Những claims này **ai cũng có thể tự tạo** thành một chuỗi JSON rồi mã hóa Base64URL. Claim iss chỉ có giá trị đáng tin sau khi JWT được xác minh chữ ký và validator phù hợp đã chạy. Khi dùng JwtIssuerAuthenticationManagerResolver, framework có thể đọc iss trước để biết decoder nào nên thử; bước này không phải authentication.

Xét một đoạn thiết kế sai:

~~~java
// Ý tưởng KHÔNG AN TOÀN; getIssuerUnverified là tên hàm giả lập.
String issuer = getIssuerUnverified(token);
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
~~~

Đoạn trên không phải file Java độc lập có thể biên dịch. Rủi ro nằm ở việc lấy issuer từ token chưa xác minh rồi **tự tải issuer metadata/JWK**. Kẻ tấn công có thể đưa một địa chỉ họ kiểm soát để API tin khóa của họ, hoặc trỏ đến máy chủ nội bộ gây SSRF. Hàng nghìn issuer giả còn có thể tạo quá nhiều decoder hoặc request discovery.

Quy tắc an toàn:

1. Tập issuer tin cậy phải có trước request và được phê duyệt bởi hệ thống.
2. Claim iss chỉ dùng để **tra cứu** trong tập này, không để tự thêm issuer.
3. Issuer không được phép phải bị từ chối; không truy vấn metadata/JWK ở URL lạ.
4. Issuer được phép sẽ chọn AuthenticationManager gắn với bộ khóa và validators của chính issuer đó.
5. Decoder sau cùng phải kiểm tra **chữ ký và iss thực sự**. Không được coi lookup thành công là đã xác thực.

## 5. Thiết kế danh sách issuer tin cậy

Ví dụ cấu hình:

~~~text
TRUSTED:
  https://id-a.example.org/realms/a
  https://id-b.example.org/realms/b

LOOKUP:
  iss=https://id-a.example.org/realms/a  -> manager A
  iss=https://id-b.example.org/realms/b  -> manager B
  iss=https://evil.example.net          -> không có manager
  iss=http://127.0.0.1:8080             -> không có manager
~~~

Danh sách tin cậy cần **so khớp chính xác toàn bộ chuỗi URI issuer**, không dùng startsWith, contains hay suffix chung. Các cách so khớp prefix có thể tin nhầm URI có thêm hostname, path hoặc realm nằm ngoài chính sách. Dấu gạch chéo cuối URL cũng phải thống nhất với metadata/contract của Authorization Server, không tự sửa tùy tiện theo token client gửi.

Không cho client tự bổ sung issuer thông qua X-Issuer, query parameter, JWT payload hoặc path. Các nguồn cấu hình đáng tin có thể là application configuration được quản trị, registry onboarding có phê duyệt hoặc cơ sở dữ liệu quyền quản lý nội bộ. Quá trình thêm issuer phải kiểm tra ownership, HTTPS, JWK Set URI, thuật toán, audience, token profile và người chịu trách nhiệm vận hành.

Đừng nhầm **issuer identifier** với **JWK Set URI**. Issuer là giá trị cần so khớp với claim iss; JWK Set URI là nguồn public keys đã được kiểm soát để kiểm tra chữ ký. Không lấy jku hoặc x5u từ JWT header để tự quyết định endpoint tải khóa.

## 6. Spring Security: một issuer so với nhiều issuer

Cách cấu hình thường gặp cho một issuer:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://id-a.example.org/realms/a
~~~

Và DSL:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(org.springframework.security.config.Customizer.withDefaults())
);
~~~

Với nhiều issuer, Resource Server sử dụng resolver:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .authenticationManagerResolver(trustedIssuerResolver)
);
~~~

Trong đó **trustedIssuerResolver** có kiểu AuthenticationManagerResolver<HttpServletRequest>. Mỗi request mang JWT từ một issuer được chọn manager riêng. Không cần tự đăng ký BearerTokenAuthenticationFilter bằng addFilterBefore; DSL Resource Server thêm filter cần thiết.

**Không chọn manager bằng cách thử mọi decoder cho tới khi có cái đồng ý.** Cách đó tạo độ trễ và dễ gây nhầm ranh giới giữa issuer, khóa và audience. Khi dùng issuer-based routing, phải chọn đúng issuer tin cậy rồi yêu cầu chính manager của issuer đó xác minh token.

## 7. Ví dụ Spring Boot 3.x / Spring Security 6.x / Java 17+

Ví dụ dùng **hai issuer cố định**, một API chung và audience orders-api. Các tên miền example.org chỉ dùng để minh họa, không phải hệ thống phát hành token thực. Muốn chạy end-to-end, thay issuer và JWK URI bằng dữ liệu từ Authorization Server hoạt động và có access token thật.

### 7.1. Dependency

Trong build.gradle của dự án Spring Boot đã cấu hình Boot plugin/BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Dùng phiên bản Spring Security tương thích với Spring Boot BOM, không trộn các version tùy tiện. Ví dụ dùng Servlet API **jakarta.servlet**, không phải javax.servlet của nền tảng cũ.

### 7.2. Ứng dụng chính

File src/main/java/demo/multiissuer/MultiIssuerApplication.java:

~~~java
package demo.multiissuer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiIssuerApplication {
    public static void main(String[] args) {
        SpringApplication.run(MultiIssuerApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfig: map issuer → manager → decoder

File src/main/java/demo/multiissuer/SecurityConfig.java:

~~~java
package demo.multiissuer;

import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    private static final String ISSUER_A =
        "https://id-a.example.org/realms/a";
    private static final String ISSUER_B =
        "https://id-b.example.org/realms/b";

    private static final String JWK_A =
        "https://id-a.example.org/realms/a/certs";
    private static final String JWK_B =
        "https://id-b.example.org/realms/b/certs";

    private static final String API_AUDIENCE = "orders-api";

    @Bean
    AuthenticationManagerResolver<HttpServletRequest>
            trustedIssuerResolver() {
        Map<String, AuthenticationManager> managers = Map.of(
            ISSUER_A, managerFor(ISSUER_A, JWK_A),
            ISSUER_B, managerFor(ISSUER_B, JWK_B)
        );

        // Chỉ trả manager cho issuer có trong map server quản lý.
        return new JwtIssuerAuthenticationManagerResolver(managers::get);
    }

    private static AuthenticationManager managerFor(
            String issuer, String trustedJwkSetUri) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(trustedJwkSetUri)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience =
            new JwtClaimValidator<List<String>>(
                "aud",
                values -> values != null
                    && values.contains(API_AUDIENCE)
            );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                audience
            )
        );

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(decoder);
        return provider::authenticate;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManagerResolver<HttpServletRequest>
                    trustedIssuerResolver) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/public/health"
                ).permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/orders"
                ).hasAuthority("SCOPE_orders.read")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(trustedIssuerResolver)
            )
            .build();
    }
}
~~~

**Phân tích từng điểm của mã:**

- Map.of có hai issuer cố định và không nhận đầu vào từ client. JWT khai một issuer khác sẽ không tìm được manager.
- JwtIssuerAuthenticationManagerResolver đọc claim iss chưa xác minh để làm lookup; việc chọn A không chứng minh token do A phát hành.
- Manager A sở hữu decoder gắn với JWK A; B sở hữu decoder gắn với JWK B. Các URL JWK đều lấy từ cấu hình server đã tin cậy.
- JwtValidators.createDefaultWithIssuer(issuer) bao gồm bộ kiểm tra mặc định và xác minh claim iss tương ứng. Không thay bằng một validator chỉ kiểm tra audience rồi bỏ kiểm tra issuer và thời hạn.
- Audience validator đòi aud chứa orders-api. Token của issuer A dành cho một ứng dụng khác vẫn không được dùng để gọi API này dù chữ ký đúng.
- JwtAuthenticationProvider tạo JwtAuthenticationToken từ JWT sau khi decoder chấp nhận; scope/scp thường được chuyển thành GrantedAuthority với tiền tố SCOPE_.
- Rule orders yêu cầu SCOPE_orders.read, mọi đường dẫn API khác cần authentication và các URL ngoài phạm vi ví dụ bị denyAll.
- STATELESS là chính sách session cho API Bearer. **csrf.disable() chỉ phù hợp khi ví dụ thực sự dùng Bearer token do client chủ động đính kèm và không có phương thức xác thực dựa cookie/session tự động gửi trên các thao tác thay đổi trạng thái.** Ứng dụng có browser session cần bảo vệ CSRF riêng hoặc tách SecurityFilterChain.

**Ghi chú tính runnable:** lớp trên có thể biên dịch với Spring Boot 3 / Security 6 tương thích. Nhưng địa chỉ example.org là dữ liệu minh họa; để xác minh JWT thành công cần cấu hình issuer, JWK URI, algorithm, audience và access token thực từ AS đã được phê duyệt. Mỗi issuer có thể cần chính sách thuật toán cụ thể nếu họ không dùng thuật toán mặc định của decoder.

### 7.4. Controller quan sát principal đã xác minh

File src/main/java/demo/multiissuer/ApiController.java:

~~~java
package demo.multiissuer;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/public/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "issuer", jwt.getIssuer().toString(),
            "subject", String.valueOf(jwt.getSubject())
        );
    }

    @GetMapping("/orders")
    public Map<String, String> orders() {
        return Map.of("result", "read-permitted");
    }
}
~~~

GET /api/public/health không cần token. GET /api/me cần token hợp lệ từ một issuer tin cậy. GET /api/orders yêu cầu thêm scope orders.read. Trong ứng dụng thật không nên trả toàn bộ JWT/claims ra client; phần kiểm tra quyền xem **đơn hàng cụ thể** vẫn thuộc business layer.

Với dự án có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Gọi API qua HTTPS sau khi thay các URI minh họa bằng cấu hình thật:

~~~bash
curl -i https://api.example.org/api/public/health
curl -i https://api.example.org/api/me \
  -H "Authorization: Bearer $TOKEN_FROM_A"
curl -i https://api.example.org/api/orders \
  -H "Authorization: Bearer $TOKEN_FROM_B"
~~~

Không đưa token trực tiếp vào file nguồn; biến môi trường, terminal history, APM và proxy logs vẫn phải được bảo vệ. Nếu token B hợp lệ, aud=orders-api và scope chứa orders.read, endpoint orders có thể trả 200. Nếu token B hợp lệ nhưng thiếu scope đó, authorization trả 403.

## 8. Những validator không được bỏ qua

### 8.1. Chữ ký và thuật toán

JWT ký JWS không đồng nghĩa payload được mã hóa. Decoder phải xác minh chữ ký bằng public key trong JWK Set **đã tin cậy**, giới hạn thuật toán ký theo policy của issuer, không tin tùy ý vào tham số alg, jku hay x5u do token đưa. Nếu token có kid, kid chỉ giúp tìm khóa trong JWK Set đáng tin; không phải chỉ dẫn tải khóa từ internet.

### 8.2. Issuer sau khi đã chọn manager

Lookup issuer trong resolver chỉ là routing hint. Khi decoder chạy, phải kiểm tra claim iss đúng **chính xác issuer của manager được chọn**. Một token ký bằng khóa B nhưng tự ghi iss=A phải thất bại ở decoder A.

### 8.3. Thời gian

Thông thường cần kiểm tra exp, nbf theo policy clock skew của framework. iat có thể cần ràng buộc riêng theo token profile. Một token hết hạn không hợp lệ dù chữ ký còn đúng.

### 8.4. Audience

API phải xác nhận aud chứa đối tượng API của mình, ví dụ orders-api. Token được ký đúng nhưng cấp cho frontend-client, analytics-api hoặc một resource server khác không nên được chấp nhận. **issuer-uri không đủ để thay thế audience validation** nếu policy yêu cầu audience.

### 8.5. Loại token

Resource Server nhận **access token**, không mặc nhiên nhận ID token OpenID Connect dùng cho client đăng nhập. Nếu hệ thống tuân theo một token profile cụ thể, hãy kiểm tra claim/type theo contract. Không dùng một JWT chỉ vì có đủ ba phần và decode được JSON.

### 8.6. Scope và authority

Spring Security thường chuyển claim scope/scp thành GrantedAuthority như SCOPE_orders.read. Vì thế quy tắc hasAuthority("SCOPE_orders.read") cần token có scope orders.read theo converter được cấu hình. Custom roles của issuer A không tự động tương đương ROLE_ADMIN hoặc roles của issuer B.

## 9. Phiên bản khác: factory fromTrustedIssuers

Ở những phiên bản Spring Security có hỗ trợ, có thể tạo resolver trực tiếp từ danh sách issuer đáng tin bằng factory:

~~~java
JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://id-a.example.org/realms/a",
        "https://id-b.example.org/realms/b"
    );
~~~

Đoạn này minh họa API **phụ thuộc phiên bản Spring Security**. Cần kiểm tra thư viện đang dùng; một số bản 6.x trước đó có các constructor hoặc cơ chế khác. Nếu cần audience riêng, converter đặc biệt hoặc khóa JWK cố định cho từng issuer, map issuer → AuthenticationManager ở phần 7 giúp biểu diễn chính sách rõ hơn.

**Dù dùng factory hay map, không nên chấp nhận issuer tự do.** Trust policy phải do server kiểm soát. Factory tiện dụng không có nghĩa token từ issuer hợp lệ sẽ mặc nhiên có đúng audience hoặc đủ quyền nghiệp vụ.

## 10. Multi-tenant: issuers, subjects và resource ownership

Có ít nhất ba kiểu kiến trúc dễ bị lẫn:

1. **Mỗi tenant một issuer:** token của tenant A có iss=A, tenant B có iss=B. Resolver biết cách chọn manager, nhưng việc đọc dữ liệu tenant vẫn phải kiểm tra ở backend.
2. **Một issuer chung, nhiều tenant:** claim iss giống nhau, claim tenant_id hoặc organization_id phân tách tenant. Chỉ có resolver theo issuer là chưa đủ để bảo vệ dữ liệu giữa tenant.
3. **Nhiều issuer cho cùng một tổ chức:** các nhà cung cấp danh tính khác nhau có thể cùng được phép gọi một API. Cần quy tắc liên kết tài khoản và quyền rõ ràng.

Hai issuer có thể cùng cấp sub="42" cho hai người hoàn toàn khác nhau. Không lấy **sub một mình** làm định danh global duy nhất. Thường cần namespace **(issuer, subject)** hoặc ánh xạ chủ thể vào ID nội bộ đã được xác minh.

Không coi X-Tenant-ID, query tenant hoặc path /tenants/A là bằng chứng định danh. Những giá trị này mô tả tài nguyên client muốn thao tác; hệ thống phải đối chiếu với principal đã được decoder xác minh và điều kiện phân quyền từng bản ghi. Scope orders.read chỉ là quyền đọc nói chung, không chứng minh được sở hữu của mọi đơn hàng.

## 11. Cập nhật issuer động có kiểm soát

Với hai issuer cố định, Map.of là thiết kế dễ kiểm toán. Với hàng trăm tenant, có thể có registry đáng tin được đội quản trị cập nhật. Một resolver lazy có thể thực hiện:

1. Đọc iss chưa xác minh.
2. Tra **exact membership** trong snapshot registry trusted.
3. Nếu không tồn tại hoặc đã disabled, từ chối ngay.
4. Nếu tồn tại, tạo hoặc lấy AuthenticationManager từ **JWK URI/validator cấu hình trong registry**.
5. Cache manager theo trusted issuer và policy version.
6. Khi issuer bị thu hồi, cập nhật registry và invalidate manager/cache theo quy trình.

Cần giới hạn số decoder, bảo vệ concurrency, timeout và retry. Nếu viết computeIfAbsent trên iss chưa được allowlist, attacker có thể tạo hàng nghìn manager hoặc khiến API gọi network tới URL nội bộ. Registry phải do hệ thống quản trị, không nhận write từ JWT hoặc request header.

Khi thêm issuer, cần xác minh người chịu trách nhiệm, miền sở hữu, TLS, metadata, JWK, algorithm, audience, scope semantics và kế hoạch khóa/thu hồi. Khi gỡ issuer, đảm bảo các instance ứng dụng đang chạy không tiếp tục giữ snapshot tin cậy cũ ngoài cửa sổ rollout đã kiểm soát.

## 12. Kiểm thử theo nhiều lớp

### 12.1. Test chính sách exact allowlist với JDK 17 độc lập

Mã sau chỉ kiểm tra nguyên tắc membership, không giải mã JWT. File TrustedIssuerDemo.java:

~~~java
import java.util.Set;

public class TrustedIssuerDemo {
    public static void main(String[] args) {
        Set<String> trusted = Set.of(
            "https://id-a.example.org/realms/a",
            "https://id-b.example.org/realms/b"
        );

        System.out.println(
            trusted.contains("https://id-a.example.org/realms/a")
        );
        System.out.println(
            trusted.contains("https://evil.example.net")
        );
        System.out.println(
            trusted.contains("https://id-a.example.org/realms/a.evil")
        );
    }
}
~~~

Chạy:

~~~bash
javac TrustedIssuerDemo.java
java TrustedIssuerDemo
~~~

Stdout chính xác:

~~~text
true
false
false
~~~

Ví dụ cho thấy exact match chặn issuer lạ và chuỗi trông giống prefix. Nó không thể thay thế kiểm thử JwtIssuerAuthenticationManagerResolver hoặc chữ ký.

### 12.2. Test Spring Security authorization bằng MockMvc

Với spring-security-test, postprocessor **jwt()** tạo Authentication JWT giả lập. Nó phù hợp test rule scope và controller, nhưng **bỏ qua** việc trích Bearer token, chọn manager và xác minh chữ ký.

Trong một test Spring Boot đã có SecurityFilterChain phù hợp, kiểm tra:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
            .claim("scope", "orders.read"))))
    .andExpect(status().isOk());

mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
            .claim("scope", "profile.read"))))
    .andExpect(status().isForbidden());
~~~

Đây là **đoạn test rút gọn** đặt trong phương thức @Test với biến MockMvc mvc và các static imports tương ứng, không phải một file Java độc lập. Vì jwt() bypass authentication thật, ngay cả claim iss giả có thể đi qua nếu test đã cấp đủ authority. Không lấy nó làm bằng chứng allowlist hoạt động.

### 12.3. Test thực sự đi qua Bearer filter và resolver

Dùng HTTPS test issuer/JWK endpoint hoặc test fixture có khóa ký tương ứng rồi gọi HTTP với Authorization: Bearer. Ma trận quan trọng:

| Request | Kết quả đúng |
| --- | --- |
| JWT A ký bằng khóa A, iss=A, aud=orders-api, scope=orders.read | Authentication A thành công; /api/orders được phép |
| JWT B ký bằng khóa B, iss=B, aud=orders-api, scope=orders.read | Authentication B thành công; /api/orders được phép |
| JWT issuer không có trong allowlist | 401, không tải metadata/JWK của issuer lạ |
| JWT khai iss=A nhưng ký bằng khóa B | Decoder A từ chối chữ ký |
| JWT ký đúng nhưng aud sai | Authentication thất bại |
| JWT hết hạn hoặc chưa đến nbf | Authentication thất bại |
| JWT hợp lệ nhưng thiếu orders.read | 403 ở authorization |
| JWT không có iss / JSON hỏng / header malformed | Không tự chọn manager mặc định |
| JWT A hợp lệ nhưng truy cập đơn hàng tenant B | Object-level authorization phải từ chối |
| JWK endpoint A timeout | Không được bỏ kiểm tra chữ ký để fallback cho qua |

Test tích hợp cần xác minh status, WWW-Authenticate khi phù hợp, controller không tạo side effect ở trường hợp bị chặn, network không gọi tới issuer lạ và trace đúng chain. Có thể dùng mock HTTP server riêng để phục vụ metadata/JWK test theo cấu hình tin cậy; không sử dụng URL do payload chưa xác minh đưa vào.

### 12.4. Test nhiều SecurityFilterChain

Nếu ứng dụng có một chain cho API và một chain cho form login, **chỉ chain đầu tiên match request** được chọn bởi FilterChainProxy. Kiểm thử các URL /api/** và các route fallback. Resolver không bảo vệ request nằm ngoài một chain được cấu hình. Đặt chain chuyên biệt theo thứ tự và có fallback phù hợp.

## 13. Phân biệt 401, 403 và lỗi mạng

| Tình huống | Phản hồi thường gặp | Lớp cần xem |
| --- | --- | --- |
| Thiếu Bearer token cho endpoint protected | 401 Unauthorized | Security entry point |
| Issuer không tin cậy | 401 Unauthorized | JwtIssuerAuthenticationManagerResolver |
| JWT sai chữ ký, hết hạn, aud hoặc iss không đúng | 401 Unauthorized | JwtDecoder / JwtAuthenticationProvider |
| JWT hợp lệ nhưng scope thiếu | 403 Forbidden | AuthorizationFilter / method security |
| JWT hợp lệ nhưng đối tượng tài nguyên không thuộc tenant | 403 hoặc 404 theo chính sách che giấu tài nguyên | Business authorization |
| JWK endpoint không sẵn sàng | Phụ thuộc lỗi xác minh và exception handling | Network, decoder, metrics |
| Bearer header malformed | 400 hoặc 401 tùy loại lỗi | BearerTokenResolver / entry point |

Một ví dụ Bearer challenge:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Khi token invalid, có thể có:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Không mặc định mọi 401 đều là issuer lạ; proxy có thể xóa Authorization header hoặc request có thể vào SecurityFilterChain khác. Không mặc định mọi 403 là scope thiếu vì CSRF, authorization rule và method security cũng có thể chặn.

## 14. Vận hành: JWK rotation, quan sát và an toàn

- **TLS và token hygiene:** Bearer token phải truyền qua HTTPS; không log Authorization header, refresh token, client secret hoặc private key. Che token trong APM, exception, proxy logs và tracing.
- **Key rotation:** JWK Set của issuer tin cậy có thể thay đổi key/kid. Cần cache và refresh hợp lý, đảm bảo đường kết nối TLS đáng tin và khoảng chuyển đổi khóa nếu Authorization Server yêu cầu.
- **Tính sẵn sàng:** JWT offline validation tránh introspection trên mọi request nhưng vẫn phụ thuộc JWK refresh. Nếu AS lỗi, không được cho qua token chưa xác minh; thiết kế timeout, retry có giới hạn, báo động và quan sát theo issuer.
- **Thu hồi token:** JWT còn hạn có thể vẫn được chấp nhận khi không có cơ chế revocation bổ sung. Nếu nghiệp vụ yêu cầu thu hồi nhanh, cân nhắc token TTL ngắn, denylist/introspection hoặc kiến trúc phù hợp contract.
- **Giới hạn cache:** Không tạo decoder mới cho mỗi request hoặc issuer tùy ý. Chỉ cache manager cho những issuer trong registry trusted.
- **Chính sách quyền:** Scope của issuer A không tự động tương đương quyền role của issuer B. Chuẩn hóa claims có chủ đích; kiểm tra data ownership ở service.
- **Audit:** Ghi kết quả authentication, issuer đã xác minh, request ID, thời điểm và lỗi, nhưng không ghi raw token/claims nhạy cảm.
- **Phòng chống tài nguyên lạ:** Không đọc jku/x5u hay metadata URL từ JWT chưa xác minh; các request mạng chỉ tới JWK endpoints được cấu hình tin cậy.

## 15. Các lỗi thiết kế thường gặp

**Lỗi 1 — Chấp nhận mọi issuer có HTTPS.** HTTPS chỉ bảo vệ kết nối đến host, không cấp quyền cho host thành Authorization Server đáng tin của API. Bắt buộc allowlist.

**Lỗi 2 — Chạy discovery theo iss chưa xác minh.** Có thể gây SSRF và tin khóa của attacker. Đầu tiên phải so khớp trusted registry, sau đó mới dùng JWK URI do server quản lý.

**Lỗi 3 — Chỉ so khớp issuer ở resolver rồi bỏ issuer validation.** Lookup không xác minh token; decoder phải kiểm tra iss sau signature verification cùng bộ validators mặc định.

**Lỗi 4 — Quên audience.** Một token của issuer A cho frontend không nên được API orders chấp nhận. Cấu hình validator aud tương ứng với resource server.

**Lỗi 5 — Xem sub là ID global độc nhất.** Hai issuer có thể cấp cùng sub. Dùng namespace issuer + subject hoặc ID nội bộ đã liên kết an toàn.

**Lỗi 6 — Cho role/scope của issuer này ngang với issuer khác một cách mù quáng.** Cần contract và converter per-issuer, đặc biệt ở ứng dụng nhiều tenant.

**Lỗi 7 — Dùng MockMvc jwt() để tuyên bố chống issuer giả đã thành công.** jwt() chủ yếu giả lập Authentication; không chứng minh resolver, chữ ký hoặc JWK trust. Bổ sung end-to-end Bearer tests.

**Lỗi 8 — Vô hiệu CSRF cho cả ứng dụng có cookie login.** API stateless Bearer thường có thể tắt CSRF theo mô hình credential, nhưng luồng browser dựa cookie vẫn cần đánh giá và bảo vệ riêng.

**Lỗi 9 — Dùng nhiều chain không có fallback.** Một số URL có thể không qua bảo vệ mong muốn. Rà soát FilterChainProxy match order và deny-by-default.

**Lỗi 10 — Chỉ xóa issuer khỏi dashboard nhưng manager vẫn còn trong cache runtime.** Phải có policy refresh/invalidation khi revoke trusted issuer.

## 16. Checklist và kết luận

- [ ] Issuer được duyệt trước khi nhận request; dùng exact allowlist thay vì prefix/suffix.
- [ ] Resolver chỉ dùng iss như **untrusted routing hint**; unknown issuer không trigger discovery.
- [ ] Mỗi issuer có manager, decoder, JWK source và validators đúng contract.
- [ ] JWT được kiểm tra signature, issuer, time và audience; thuật toán không lấy tùy ý từ JWT.
- [ ] Scope và tenant claims được diễn giải có kiểm soát; có object-level authorization.
- [ ] SecurityFilterChain chọn đúng resolver và fallback không để hở URL.
- [ ] Bearer token chỉ gửi qua HTTPS, không bị leak qua query string/log/tracing.
- [ ] Có unit test allowlist, authorization test và real Bearer/JWK integration test cho issuer hợp lệ/lạ.
- [ ] Quy trình onboard/revoke issuer, rotate keys, giám sát JWK outages và cache manager được kiểm toán.
- [ ] Đội vận hành phân biệt 401 authentication, 403 authorization và lỗi JWK/network.

**Ghi nhớ:** AuthenticationManagerResolver giải quyết bài toán **chọn người kiểm tra token**, chứ không thay thế việc kiểm tra token. Với nhiều issuer, luồng đúng là **chỉ cho phép issuer thuộc danh sách tin cậy → chọn manager tương ứng → decoder xác minh chữ ký và claims → authorization quyết định quyền với tài nguyên**.
