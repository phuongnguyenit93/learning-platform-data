# oauth2ResourceServer và luồng tiếp nhận Bearer token trong Spring Security Servlet

## 1. Resource Server giải quyết vấn đề gì?

Một API cần biết **request nào được phép gọi và gọi với quyền gì**. Khi dùng OAuth 2.0, client (ứng dụng web, mobile hoặc một service) lấy **access token** từ Authorization Server sau một luồng cấp quyền phù hợp, rồi gửi token khi gọi API. API đóng vai trò **OAuth 2.0 Resource Server**: tiếp nhận access token, kiểm tra token có hợp lệ không, chuyển thông tin token thành đối tượng Authentication và áp dụng authorization rule.

Trong Spring Security Servlet, cấu hình **http.oauth2ResourceServer(...)** bật tập thành phần xử lý loại request này. Token phổ biến được gửi theo RFC 6750:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9...
Accept: application/json
~~~

Đoạn token rút gọn ở trên chỉ minh họa hình dạng header. Một access token thực tế là chuỗi bí mật cần bảo vệ. Resource Server **không tự cấp token**, không tự làm luồng đăng nhập OAuth 2.0, không tự refresh access token và không tự biến một client thành Authorization Server.

Bài này thuộc **Spring Security Servlet / Spring MVC** (Spring Boot 3.x, Spring Security 6.x, Java 17+). Trọng tâm là cách **BearerTokenAuthenticationFilter** tiếp nhận token, cách JWT/opaque token được xác minh, cách tạo SecurityContext và cách AuthorizationFilter quyết định quyền truy cập.

Mục tiêu học tập:

- Phân biệt OAuth 2.0 **client**, **Authorization Server**, **Resource Server** và **protected resource**.
- Hiểu Bearer token là bằng chứng dựa vào **việc sở hữu token**, và tại sao phải dùng HTTPS.
- Theo dõi đầy đủ đường đi Authorization header → filter → AuthenticationManager → JWT decoder hoặc opaque introspector → SecurityContext → authorization → controller.
- Cấu hình JWT Resource Server theo issuer, JWK và claims; hiểu khác biệt với opaque token introspection.
- Đọc được mã lỗi 401/403 và header WWW-Authenticate khi token không hợp lệ hoặc không đủ scope.
- Viết cấu hình và test đúng ranh giới giữa **test authorization giả lập JWT** và **test giải mã/xác minh Bearer thật**.

## 2. Bốn vai trò và ranh giới trách nhiệm

| Vai trò | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Resource Owner | Chủ sở hữu dữ liệu hoặc quyền sử dụng tài nguyên | Người dùng có hồ sơ, hóa đơn |
| Client | Nhận access token qua OAuth 2.0 flow và gọi API | Web frontend, mobile app, service |
| Authorization Server | Xác thực/cấp quyền, phát hành access token, công bố khóa hoặc introspection endpoint | Identity provider |
| Resource Server | Bảo vệ API, kiểm tra token và quyết định truy cập dữ liệu | Spring MVC REST API |

Hệ thống minh họa:

~~~text
                   (1) OAuth 2.0 grant
 Client --------------------------------------> Authorization Server
   |                                                   |
   |               (2) access token                    |
   |<--------------------------------------------------|
   |
   | (3) GET /api/reports
   |     Authorization: Bearer <access token>
   v
 Resource Server (Spring Security Servlet)
   |  - lấy Bearer token từ request
   |  - xác minh chữ ký JWT hoặc hỏi introspection endpoint
   |  - chuyển claim/scope thành Authentication
   |  - kiểm tra authorization rule
   v
 Protected resource / Controller
   |
   +--> (4) response khi được phép
~~~

Dấu **Bearer** nghĩa là bất kỳ ai sở hữu chuỗi token hợp lệ đều có thể sử dụng nó trong thời gian và phạm vi được cấp. Token không tự gắn mật mã với riêng một thiết bị chỉ vì đang dùng Bearer scheme. Không đưa token vào URL/query string, không log giá trị token, không đưa nó vào tài liệu công khai hoặc ảnh chụp. Truyền token qua **HTTPS** và lưu giữ tại client theo mô hình bảo mật phù hợp.

**Access token khác ID token.** ID token của OpenID Connect chủ yếu mô tả sự kiện xác thực cho client, với audience thường là client_id. Resource Server phải nhận **access token dành cho API của nó** và kiểm tra audience/issuer theo contract. Không được mặc nhiên coi một ID token đăng nhập là access token hợp lệ chỉ vì đó cũng là chuỗi JWT ký đúng.

## 3. Luồng xử lý Bearer request trong Servlet filter chain

Một request đi qua servlet container và Spring Security theo thứ tự khái quát:

~~~text
HTTP request
    |
    v
DelegatingFilterProxy("springSecurityFilterChain")
    |
    v
FilterChainProxy -> SecurityFilterChain phù hợp
    |
    +--> SecurityContextHolderFilter và các filter liên quan
    |
    +--> BearerTokenAuthenticationFilter
    |       |
    |       +--> BearerTokenResolver đọc Authorization: Bearer ...
    |       |
    |       +--> AuthenticationManager
    |                 |
    |                 +--> JWT: JwtAuthenticationProvider
    |                 |         -> JwtDecoder -> JwtAuthenticationToken
    |                 |
    |                 +--> opaque: OpaqueTokenAuthenticationProvider
    |                           -> OpaqueTokenIntrospector
    |                           -> BearerTokenAuthentication
    |
    +--> Các filter khác (ví dụ ExceptionTranslationFilter)
    |
    +--> AuthorizationFilter: kiểm tra authority/scope/role
    |
    v
DispatcherServlet -> Controller (nếu được phép)
~~~

Sơ đồ chỉ phản ánh vị trí **chức năng** cần học, không liệt kê toàn bộ internal filter của mọi phiên bản hay thứ tự tuyệt đối giữa tất cả filter khác. Cấu hình form login, CSRF, CORS hoặc nhiều SecurityFilterChain làm danh sách chi tiết thay đổi.

### 3.1. Không có Bearer token

Theo mặc định, **DefaultBearerTokenResolver** tìm token trong header Authorization với scheme Bearer. Nếu không có token, BearerTokenAuthenticationFilter thường **không tự tạo một phiên đăng nhập**, mà để request đi tiếp. Đến authorization, endpoint public có thể trả 200; endpoint cần xác thực sẽ bị chặn và thường trả **401 Unauthorized** với WWW-Authenticate: Bearer.

Điều đó rất khác trường hợp “request thiếu token thì filter phải ném lỗi ngay”. Việc có bắt buộc đăng nhập hay không là chính sách của endpoint.

### 3.2. Có Bearer token

BearerTokenAuthenticationFilter lấy token và tạo **BearerTokenAuthenticationToken** (một Authentication chưa được xác minh). Filter chuyển đối tượng này vào AuthenticationManager thích hợp.

- Với JWT, **JwtAuthenticationProvider** gọi **JwtDecoder** để phân tích và xác minh JWT, rồi ánh xạ thành **JwtAuthenticationToken** chứa principal Jwt và authorities.
- Với opaque token, **OpaqueTokenAuthenticationProvider** gọi **OpaqueTokenIntrospector** để kiểm tra token bằng introspection, rồi tạo **BearerTokenAuthentication** với principal OAuth2AuthenticatedPrincipal.

Khi thành công, filter đặt Authentication đã xác minh vào **SecurityContextHolder** cho quá trình xử lý request. Spring MVC và method security có thể dùng principal, claims và authorities đó. Trường hợp thất bại, entry point của Resource Server xử lý phản hồi thay vì để controller chạy.

### 3.3. Kiểm tra quyền sau khi xác thực

AuthorizationFilter đánh giá các rule như authenticated(), hasAuthority("SCOPE_reports.read"), hasRole("ADMIN"). Một Bearer token **hợp lệ** vẫn có thể thiếu scope hoặc authority và bị từ chối **403 Forbidden**. Xác minh token trả lời “client đưa bằng chứng đáng tin không?”; authorization trả lời “bằng chứng đó có quyền làm thao tác này không?”.

SecurityContext cho request không có nghĩa server đã tạo HTTP session. Với API chỉ dùng Bearer token, thường cấu hình stateless; request sau phải tự mang token hợp lệ.

## 4. Token đi vào từ đâu? RFC 6750 và BearerTokenResolver

Cách chuẩn và nên ưu tiên:

~~~http
Authorization: Bearer <access-token>
~~~

DefaultBearerTokenResolver đọc header Authorization. Cần phân biệt các trường hợp:

| Dạng request | Kết quả khái quát |
| --- | --- |
| Authorization: Bearer token-hợp-lệ | Có thể được xác thực sau khi kiểm tra token |
| Không có Authorization header | Endpoint public có thể đi tiếp; endpoint protected thường 401 |
| Token có định dạng Bearer không hợp lệ hoặc nhiều vị trí token gây mơ hồ | Có thể bị từ chối với lỗi OAuth/Bearer request |
| Bearer đúng cấu trúc nhưng chữ ký sai, hết hạn, issuer không đúng | Xác thực thất bại, thường 401 |
| Token hợp lệ nhưng thiếu quyền của endpoint | Thường 403 |
| Header Basic trong API chỉ cấu hình Resource Server | Không phải Bearer; không mặc nhiên được dùng làm OAuth access token |

Một số RFC cho phép vận chuyển token qua form body hoặc query parameter trong điều kiện nhất định. Tuy nhiên **DefaultBearerTokenResolver không khuyến khích và không bật việc nhận token qua query parameter theo mặc định**. Query string dễ đi vào lịch sử trình duyệt, proxy log, monitoring, Referer và tài liệu hỗ trợ; tránh cách này. Nếu có yêu cầu tương thích đặc biệt, phải đánh giá mô hình đe dọa trước khi thay BearerTokenResolver.

Có thể tùy chỉnh header hoặc resolver qua DSL, nhưng những hệ thống chuẩn nên giữ Authorization: Bearer để gateway, client HTTP và monitoring dễ xử lý nhất quán.

## 5. JWT Resource Server: định dạng và các bước xác minh

**JWT (JSON Web Token)** thường có ba phần phân tách bằng dấu chấm:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

JWT **được ký** không đồng nghĩa nội dung đã **được mã hóa**. Header và payload của JWS/JWT thông thường có thể được base64url-decode để đọc. Không đặt mật khẩu, private key hoặc bí mật lâu dài trong claims.

Payload minh họa một access token:

~~~json
{
  "iss": "https://login.example.org/realms/lab",
  "sub": "account-42",
  "aud": ["reports-api"],
  "scope": "reports.read profile.read",
  "iat": 1750000000,
  "nbf": 1750000000,
  "exp": 1750003600
}
~~~

Các timestamp trên **chỉ minh họa cấu trúc claims**, không đại diện token dùng được ở thời điểm đọc bài. Một token hợp lệ phải được phát hành bởi Authorization Server thực, có chữ ký đúng và thời gian hiệu lực phù hợp.

Các trường cần hiểu:

- **iss (issuer):** thực thể phát hành token. Resource Server phải đối chiếu với issuer được tin cậy.
- **sub (subject):** danh tính subject mà token mô tả; thường dùng để lấy tên principal, nhưng không tự nói rằng subject có quyền admin.
- **aud (audience):** API/đối tượng mà access token dự định phục vụ. Resource Server nên yêu cầu audience thuộc về API của mình.
- **exp / nbf / iat:** thời điểm hết hạn, bắt đầu hiệu lực và phát hành. Decoder thường có kiểm tra thời gian phù hợp; iat không tự tạo mọi chính sách freshness.
- **scope hoặc scp:** các phạm vi quyền được cấp. Spring Security có converter mặc định để biến thành authorities có prefix **SCOPE_**.
- **kid/alg trong header JWT:** giúp chọn public key và thuật toán kiểm tra chữ ký. Resource Server phải có cấu hình thuật toán và nguồn khóa đáng tin, không tùy tiện chấp nhận thuật toán do client muốn dùng.

Đường đi kiểm tra JWT:

1. BearerTokenAuthenticationFilter lấy token.
2. JwtAuthenticationProvider yêu cầu JwtDecoder xác minh token.
3. Decoder giải mã cấu trúc, xác minh chữ ký dựa trên public keys/JWK đáng tin, áp dụng validator cho thời gian và claims được cấu hình.
4. JwtAuthenticationConverter biến JWT thành JwtAuthenticationToken và authorities.
5. Authorization rule quyết định request có vào controller không.

**Chỉ kiểm tra chữ ký là chưa đủ.** Token của một ứng dụng khác vẫn có thể được ký bởi Authorization Server đáng tin. Vì thế phải kiểm tra **audience** theo API; trong nhiều cấu hình Spring Security, việc kiểm tra aud **không tự bật chỉ từ issuer-uri**. Tương tự, không dựa vào username hoặc role claim tự chế nếu chưa định nghĩa mapping và trust contract.

### 5.1. JWK Set và luân chuyển khóa

Authorization Server có thể công bố **JWK Set URI** gồm public keys. Khi có token được ký bằng private key tương ứng, JwtDecoder chọn public key dựa trên thông tin JOSE header (ví dụ kid) và kiểm tra chữ ký. Resource Server cần định kỳ nhận khóa mới khi issuer luân chuyển khóa. Đảm bảo egress tới JWK endpoint, HTTPS chứng chỉ hợp lệ, caching hợp lý và thời gian overlap giữa khóa cũ/mới.

Đừng lưu private signing key trong Resource Server chỉ để xác minh JWT ký bất đối xứng. Trường hợp issuer dùng khóa bí mật chia sẻ có contract riêng; đối với nhiều API và tổ chức, xác minh bằng public key là mô hình dễ tách trách nhiệm hơn.

## 6. Cấu hình JWT trên Spring Boot 3.x và Spring Security 6.x

### 6.1. Dependency

Với dự án Spring Boot quản lý phiên bản dependencies bằng BOM, trong build.gradle (Groovy):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Spring Security cần hỗ trợ resource-server và JWT JOSE cho nhánh JWT; starter Resource Server của Spring Boot đưa vào bộ dependency phù hợp. Không khai báo version Spring Security khác với Boot BOM nếu không có chủ đích tương thích.

### 6.2. Cấu hình issuer

File src/main/resources/application.properties:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://login.example.org/realms/lab
~~~

URI trên **là ví dụ hình thức**, ứng dụng thực phải dùng issuer chính xác do Authorization Server cấp. issuer-uri cho phép cấu hình decoder dựa trên discovery metadata của issuer và kiểm tra iss theo cơ chế của Spring Security. Khởi tạo decoder qua discovery có thể cần Authorization Server truy cập được khi startup, tùy chế độ cấu hình.

Nếu hệ thống có JWK Set URI cố định và muốn tránh phụ thuộc discovery lúc khởi động, có thể đặt **cả issuer-uri và jwk-set-uri** theo đúng endpoint của cùng issuer:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://login.example.org/realms/lab
spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://login.example.org/realms/lab/protocol/openid-connect/certs
~~~

Hai URI đều chỉ là ví dụ kiến trúc. Spring Security vẫn phải xác minh chữ ký theo JWK set và kiểm tra issuer; việc tự cung cấp JWK Set URI không tự hợp thức hóa token từ mọi issuer.

### 6.3. Cấu hình SecurityFilterChain

File src/main/java/demo/resourceserver/SecurityConfig.java:

~~~java
package demo.resourceserver;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/health")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Giải thích:

- **oauth2ResourceServer(...jwt(...))** bật xử lý Bearer token và JWT validation cho chain này. Đây là một API nhận access token, không phải OAuth login client.
- **STATELESS** nói Spring Security không tạo/dùng HTTP session để lưu SecurityContext cho API. Request mới cần token riêng.
- **permitAll()** cho phép health endpoint; endpoint reports yêu cầu **SCOPE_reports.read**; các API khác yêu cầu đã xác thực; URL ngoài /api/** bị từ chối theo ví dụ.
- **csrf.disable()** chỉ hợp lý với API thiết kế **xác thực duy nhất bằng Bearer token tự đặt trong Authorization header**, không dùng cookie tự động gửi để xác thực thao tác thay đổi trạng thái. Nếu cùng app có đăng nhập session/cookie hoặc trình duyệt có cơ chế tự đính kèm credential, cần đánh giá CSRF đúng mô hình, có thể tách nhiều SecurityFilterChain thay vì tắt toàn bộ.

Không cần tự đăng ký BearerTokenAuthenticationFilter bằng addFilterBefore: DSL Resource Server tạo các thành phần cần thiết. Nếu có nhiều SecurityFilterChain, cấu hình JWT, session policy và endpoint matcher phải đặt trong chain thực sự bảo vệ API; chỉ chain đầu tiên match request được dùng.

### 6.4. Một ứng dụng Java và controller để quan sát principal

File src/main/java/demo/resourceserver/ResourceServerApplication.java:

~~~java
package demo.resourceserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceServerApplication.class, args);
    }
}
~~~

File src/main/java/demo/resourceserver/ApiController.java:

~~~java
package demo.resourceserver;

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
    public Identity me(@AuthenticationPrincipal Jwt jwt) {
        return new Identity(
            jwt.getSubject(),
            jwt.getIssuer() == null ? "" : jwt.getIssuer().toString()
        );
    }

    @GetMapping("/reports")
    public Map<String, String> reports() {
        return Map.of("report", "visible-to-reports.read");
    }

    public record Identity(String subject, String issuer) {}
}
~~~

Đây là ví dụ Spring Boot độc lập ở mức lớp ứng dụng/controller/security, cần issuer thực và access token do issuer đó phát hành để kiểm tra endpoint protected. Không tự dùng giá trị “bearer” rỗng hoặc token giả khi chạy thử. Endpoint /api/me chỉ trả một số thông tin principal để học; trong sản phẩm thật không nên trả toàn bộ token/claims nhạy cảm.

Khi chạy qua HTTPS thực và đặt access token hợp lệ vào biến môi trường TOKEN của shell, ví dụ:

~~~bash
curl -i https://api.example.com/api/public/health
curl -i https://api.example.com/api/me -H "Authorization: Bearer $TOKEN"
curl -i https://api.example.com/api/reports -H "Authorization: Bearer $TOKEN"
~~~

Dùng biến shell tránh viết trực tiếp token vào ví dụ chia sẻ; bản thân shell history, môi trường runtime, proxy và CI logs cũng cần được kiểm soát. Đường dẫn và hostname minh họa cần trỏ tới deployment có chứng chỉ và issuer khớp.

Nếu token hợp lệ có scope reports.read, GET /api/reports có thể trả HTTP 200 cùng JSON chứa report. Nếu token hợp lệ nhưng thiếu scope này, endpoint reports sẽ bị từ chối 403 dù /api/me vẫn có thể thành công.

## 7. JWT authorities: scope khác role và claim khác quyết định phân quyền

Với JwtAuthenticationProvider mặc định, Spring Security dùng **JwtAuthenticationConverter** và thành phần trích authorities từ claims. Thông thường claims scope hoặc scp sẽ được map:

~~~text
JWT claim:  "scope": "reports.read profile.read"
     |
     v
GrantedAuthority("SCOPE_reports.read")
GrantedAuthority("SCOPE_profile.read")
~~~

Do đó:

~~~java
.requestMatchers("/api/reports").hasAuthority("SCOPE_reports.read")
~~~

phù hợp với resource server theo scope. **hasAuthority("reports.read")** sẽ không tương đương vì thiếu prefix nếu đang dùng converter mặc định. **hasRole("ADMIN")** thường kiểm tra authority ROLE_ADMIN; role tùy chỉnh trong JWT sẽ không tự động biến thành ROLE_ADMIN nếu chưa cấu hình converter.

Nếu issuer có contract riêng như roles, permissions hoặc scope tùy biến, cần viết/đăng ký JwtAuthenticationConverter có quy tắc rõ ràng. Không gộp mọi claim không rõ nguồn thành authority cao. Cũng không dùng thông tin từ request parameter để gán role.

**Audience validation độc lập với scope.** Token có scope reports.read nhưng aud hướng tới một service khác vẫn không nên được API reports chấp nhận.

### 7.1. Ví dụ bổ sung audience validator

Khi API yêu cầu aud chứa reports-api, có thể tạo decoder rõ ràng với validator cho issuer và audience, dựa trên JWK endpoint đã cấu hình. Đây là **phương án thay thế việc để Boot tự tạo JwtDecoder** khi bạn muốn tự kiểm soát validators.

Trong cùng package, một cấu hình Java minh họa:

~~~java
package demo.resourceserver;

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
public class JwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("https://login.example.org/realms/lab") String issuer,
            @Value("https://login.example.org/realms/lab/protocol/openid-connect/certs")
                    String jwkSetUri) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

        OAuth2TokenValidator<Jwt> defaultAndIssuer =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience =
            new JwtClaimValidator<List<String>>(
                "aud",
                values -> values != null && values.contains("reports-api")
            );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaultAndIssuer, audience
            )
        );
        return decoder;
    }
}
~~~

Ví dụ dùng @Value với **giá trị URI minh họa** để cho thấy cấu trúc, không phải khuyến nghị hard-code issuer/JWK endpoint trong sản phẩm. Ứng dụng thật cần lấy cấu hình từ nguồn cấu hình môi trường được kiểm soát và đảm bảo **issuer và JWK là hai endpoint được tin cậy cùng contract**. Nếu đã có JwtDecoder bean riêng ở ứng dụng, thay hoặc chỉnh bean đang có thay vì khai báo hai bean decoder mâu thuẫn.

JwtValidators.createDefaultWithIssuer kết hợp các kiểm tra mặc định (bao gồm thời hạn theo chính sách hỗ trợ) với kiểm tra issuer. Validator audience yêu cầu claim aud chứa reports-api. Khi API phục vụ nhiều audience hoặc có nhiều issuer, phải xây dựng policy tường minh cho từng trường hợp; không bỏ qua kiểm tra audience để “hợp lệ mọi token”.

**Không tự suy đoán** rằng Resource Server dùng token introspection hay một cơ chế revocation tức thời khi chạy chế độ JWT. Nếu token JWT vẫn còn hạn và khóa/chữ ký/claims hợp lệ, nó có thể tiếp tục được chấp nhận cho tới khi hết hạn hoặc bị chặn bởi kiểm soát bổ sung do hệ thống thiết kế.

## 8. Opaque token: xác minh qua introspection thay vì giải mã JWT

**Opaque access token** có thể là chuỗi ngẫu nhiên, không có cấu trúc ba phần dễ đọc. Resource Server không thể tự xác minh claim và chữ ký như JWT; nó thường gọi **OAuth 2.0 Token Introspection Endpoint** của Authorization Server (RFC 7662). Endpoint trả dữ liệu như active, scope, client_id, sub, exp... tùy contract.

Luồng:

~~~text
Client -> Resource Server
         Authorization: Bearer token
              |
              v
        BearerTokenAuthenticationFilter
              |
              v
        OpaqueTokenAuthenticationProvider
              |
              v
        OpaqueTokenIntrospector
              |
              +---- HTTPS request (token + client credentials)
              |               |
              |               v
              |        Introspection Endpoint
              |               |
              +<--- active + claims/scope
              |
              +--> nếu token active và policy hợp lệ:
                   tạo Authentication, rồi kiểm tra authority
~~~

Ví dụ một phản hồi introspection:

~~~json
{
  "active": true,
  "sub": "account-42",
  "scope": "reports.read",
  "client_id": "dashboard-client",
  "exp": 1750003600
}
~~~

Tất cả dữ liệu là ví dụ cấu trúc, không phải response API thật. **Introspection client credentials là bí mật của Resource Server**, khác với Bearer access token của người dùng; không gửi hai loại credential này cho browser.

Cấu hình thay thế chế độ JWT:

~~~properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://login.example.org/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=reports-resource-server
~~~

Ngoài các property này, phải cấp **client-secret** qua hệ thống quản lý secret hoặc biến môi trường tương ứng của Spring Boot; không đặt secret thật vào repository. Bean SecurityFilterChain dùng:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(org.springframework.security.config.Customizer.withDefaults())
)
~~~

Đây là **đoạn thay thế cấu hình .jwt(...)**, không phải để copy đồng thời vào ví dụ JWT trước đó. Với opaque token, controller không mặc định nhận principal kiểu Jwt qua @AuthenticationPrincipal Jwt; sử dụng Authentication hoặc OAuth2AuthenticatedPrincipal phù hợp.

**Tradeoff**: introspection giúp Authorization Server quyết định token còn active ở thời điểm kiểm tra và có thể hỗ trợ thu hồi token gần thời gian thực, nhưng mỗi request có thể cần network call; cần kế hoạch latency, timeout, availability và caching nếu được phép theo chính sách. Không giả định lúc Authorization Server mất mạng API luôn trả đúng 401: lỗi hạ tầng xác minh token có thể biểu hiện khác nhau tùy cấu hình xử lý exception và fallback.

JWT và opaque là **hai chiến lược xác minh**, không phải tên gọi của client flow: access token phát từ client credentials hoặc authorization code có thể là JWT hoặc opaque, tùy Authorization Server.

## 9. Authentication, 401/403 và WWW-Authenticate

Các status dễ nhầm:

| Tình huống | Kết quả điển hình | Ý nghĩa |
| --- | --- | --- |
| GET endpoint public, không token | 200 nếu controller xử lý được | Bảo mật không yêu cầu authentication ở endpoint đó |
| GET endpoint protected, không token | 401 + WWW-Authenticate: Bearer | Client cần cung cấp token |
| Bearer có cú pháp hợp lệ nhưng signature/issuer/thời gian không hợp lệ | 401, có thể kèm error=invalid_token | Authentication thất bại |
| Bearer token không đúng cách truyền hoặc format | 400 hoặc 401 tùy lỗi, header Bearer mô tả lỗi | Request token malformed |
| Access token hợp lệ, scope không đủ | 403, có thể kèm error=insufficient_scope | Đã được xác thực nhưng không có quyền |
| Access token hợp lệ, endpoint cho phép | 200/2xx hoặc status nghiệp vụ tương ứng | Request đã tới controller |

Ví dụ header thách thức xác thực (trình bày cấu trúc):

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Với token không hợp lệ, server có thể trả thông tin tương đương:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Nếu thiếu scope, một số response có thể chứa:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Không coi mọi status là tuyệt đối: reverse proxy, CORS, request rejection của firewall, entry point tùy biến, controller exceptions và nhiều SecurityFilterChain có thể làm response khác đi. **401** không khẳng định token chưa được gửi; **403** không khẳng định CSRF sai. Dùng error type, log và chain thực tế để chẩn đoán.

Đối với Bearer Authentication, Spring Security có các thành phần chuyên dụng như **BearerTokenAuthenticationEntryPoint** và **BearerTokenAccessDeniedHandler**. Chúng thể hiện ngữ nghĩa OAuth Bearer ở trường hợp authentication/authorization thất bại. Không phải lúc nào ứng dụng cũng nên redirect API client tới form đăng nhập.

## 10. Test Resource Server bằng MockMvc và spring-security-test

Một điểm then chốt: **test dùng jwt() request postprocessor giả lập một Authentication JWT đã được xác thực**. Nó phù hợp để test authorization, scope và controller, nhưng không thực sự giải mã JWT bằng JwtDecoder và không chứng minh cấu hình JWK/issuer ngoài đời hoạt động.

Với các class ở phần 6 và starter test, tạo file src/test/java/demo/resourceserver/ResourceServerSecurityTest.java:

~~~java
package demo.resourceserver;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerSecurityTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    JwtDecoder decoder;

    @Test
    void publicHealthDoesNotRequireToken() throws Exception {
        mvc.perform(get("/api/public/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void protectedEndpointRejectsMissingToken() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void reportsRequireScope() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().jwt(j -> j
                    .claim("sub", "alice")
                    .claim("scope", "profile.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void reportsAcceptCorrectScope() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().jwt(j -> j
                    .claim("sub", "alice")
                    .claim("scope", "reports.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void rejectedBearerFromDecoderReturnsUnauthorized() throws Exception {
        when(decoder.decode("bad.token.value"))
            .thenThrow(new BadJwtException("Signature invalid"));

        mvc.perform(get("/api/me")
                .header(HttpHeaders.AUTHORIZATION, "Bearer bad.token.value"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Trong Spring Boot 3.3, @MockBean thay JwtDecoder bằng mock, giúp context test không phải gọi issuer thực; ở phiên bản Boot mới hơn, API mock bean có thể thay đổi, cần dùng annotation tương ứng với phiên bản đang chạy.

Giải thích từng nhóm test:

- Test public và thiếu token xác nhận matcher/entry point.
- Hai test dùng jwt() xác nhận cách authorities được trích từ scope và được AuthorizationFilter kiểm tra; **chúng bỏ qua giải mã chữ ký JWT thật**.
- Test cuối đưa Authorization header thật qua BearerTokenAuthenticationFilter và buộc mock JwtDecoder từ chối token; nó quan sát phản hồi 401 của đường filter.
- Các test này vẫn **không chứng minh** discovery URL, JWK download, TLS, key rotation, audience contract hoặc introspection thực. Phải có test tích hợp riêng với issuer/test keys đáng tin hoặc môi trường end-to-end.

Lệnh chạy, nếu dự án có Gradle wrapper chuẩn:

~~~bash
./gradlew test
~~~

Không đưa ra stdout giả định vì kết quả còn phụ thuộc môi trường, plugin và test khác. Khi kiểm chứng end-to-end, tạo token từ Authorization Server thử nghiệm thật với issuer, audience, scope và thời gian đúng; không cắt/chỉnh token thủ công rồi mong chữ ký vẫn hợp lệ.

## 11. Test tích hợp và ma trận trường hợp cần có

Trên môi trường tích hợp dùng HTTPS, tối thiểu nên kiểm tra:

| Request | Điều cần xác minh |
| --- | --- |
| /api/public/health không token | Vào được endpoint public, 200 |
| /api/me không token | 401 với Bearer challenge |
| /api/me token hợp lệ, đúng issuer/aud/time | Trả principal dự kiến |
| /api/reports token hợp lệ có reports.read | Đi tới controller, kết quả nghiệp vụ |
| /api/reports token hợp lệ thiếu reports.read | Bị 403, không chạy logic được bảo vệ |
| Token sai chữ ký / kid không tồn tại | Bị 401, không được chấp nhận chỉ vì payload có quyền |
| Token hết hạn hoặc chưa tới nbf | Bị từ chối |
| Token issuer khác | Bị từ chối |
| Token audience của API khác | Bị từ chối khi đã cấu hình audience validator |
| Token trong query string | Không được chấp nhận theo cấu hình an toàn mặc định |
| Preflight OPTIONS của browser | Không bị authentication bắt nhầm; kiểm tra CORS policy riêng |
| Introspection endpoint hết khả dụng (nếu opaque) | Lỗi được xử lý và giám sát, không cho truy cập khi không xác minh được |

Test phân biệt 401 và 403 cần xác định cả **response status, header phù hợp, controller không tạo side effect** trong trường hợp bị chặn. Với nhiều filter chain, phải kiểm tra matcher nào đã chọn chain chứa oauth2ResourceServer.

Để đánh giá hiệu năng và vận hành, cần kiểm tra thời gian truy vấn JWK/introspection, timeout, cache policy, hành vi khi Authorization Server thay đổi key, token expiry và những request đồng thời. Resource Server không nên tự ý bỏ kiểm tra token khi upstream bị lỗi.

## 12. Các tình huống thường gặp và nguyên nhân thực sự

### 12.1. 401 dù token nhìn giống JWT hợp lệ

JWT ba phần chỉ nói rằng chuỗi trông giống một JWT. Kiểm tra **Authorization Bearer header**, issuer-uri, chữ ký, kid/JWK URI, alg được tin cậy, exp/nbf, audience và loại access token. Không copy ID token của frontend làm access token cho API.

### 12.2. 403 dù chữ ký và issuer đều hợp lệ

Token đã xác thực nhưng có thể thiếu authority. Spring Security thường map scope thành **SCOPE_...**; kiểm tra token thực có claims scope/scp đúng contract và rule dùng hasAuthority("SCOPE_reports.read"). JWT role custom không tự map thành ROLE_ADMIN. AuthorizationFilter hoặc method security có thể thêm ràng buộc độc lập với token.

### 12.3. Thiếu JwtDecoder bean hoặc khởi động bị lỗi do issuer

JWT mode cần JwtDecoder. Với Spring Boot, dùng starter/resource-server JWT dependency và cấu hình issuer-uri/JWK URI chính xác; nếu dự án tự định nghĩa JwtDecoder, phải cung cấp validator phù hợp. Discovery metadata từ issuer hoặc egress tới issuer có thể ảnh hưởng startup; xem stack trace và truststore/network thay vì tắt validation.

### 12.4. Chọn nhầm cấu hình JWT cho opaque token

Opaque string không chứa JWT header.payload.signature. Cần introspection configuration và opaqueToken DSL, với client credentials bảo mật. Ngược lại, dùng introspection tùy ý với JWT làm tăng dependency mạng dù một API có thể tự xác minh chữ ký JWT.

### 12.5. Token đúng nhưng API vẫn thấy anonymous

Kiểm tra header Authorization có thật sự đến backend không; proxy/WAF có xóa header không; có nhiều SecurityFilterChain khiến request rơi vào chain không cấu hình resource server không; có custom filter ghi đè SecurityContext không. Một endpoint permitAll không chứng minh xác thực hoạt động: nó có thể chạy kể cả thiếu token.

### 12.6. Client gửi token cho API khác

Mỗi Resource Server nên xác định đúng audience được phép. Một token với scope đủ rộng nhưng aud của service khác không nên hợp lệ. Bổ sung audience validator; không tắt kiểm tra vì “cùng issuer”.

### 12.7. API stateless nhưng vẫn có session/cookie

SessionCreationPolicy.STATELESS liên quan tới nơi Spring Security lưu security context; không tự đảm bảo mọi phần của ứng dụng không tạo session, không phát cookie, hoặc không có xác thực cookie. CSRF phải dựa trên mô hình credential có thể tự đính kèm bởi browser; chỉ disable khi xác nhận API thật sự dùng Authorization Bearer do client kiểm soát và không có đường cookie xác thực thao tác nguy hiểm.

### 12.8. Nhầm Resource Server với OAuth2 Login

**oauth2Login()** phục vụ ứng dụng đóng vai OAuth client với browser login/session. **oauth2ResourceServer()** phục vụ API nhận access token. Một ứng dụng có thể có cả hai, nhưng cần phân chia SecurityFilterChain, entry point, session và CSRF rõ ràng. Không dùng oauth2Login() để kỳ vọng BearerTokenAuthenticationFilter xuất hiện cho API.

### 12.9. CORS preflight bị từ chối

Browser gửi OPTIONS preflight trước một số request cross-origin và không mang Bearer token như request thật. Cần xử lý CORS ở tầng thích hợp, đăng ký allowed origin/method/header Authorization rõ ràng; nếu cần, permit preflight. CORS không thay xác minh Bearer token ở request API thật.

### 12.10. Cố ghi JWT nguyên văn để debug

JWT có thể mang dữ liệu cá nhân và chữ ký token chính là credential cho đến khi hết hạn. Log **request ID, issuer tin cậy, subject có kiểm soát, kết quả validation và mã lỗi**; tránh ghi Authorization header, token body, client secret và refresh token. Che cả token trong tracing/APM/reverse proxy.

## 13. Kiểm soát bảo mật và vận hành đi kèm

**HTTPS xuyên suốt ranh giới công khai.** Bearer token bị đánh cắp thường có thể bị replay. Dùng TLS, đặt thời gian sống token hợp lý, scope tối thiểu, audience chính xác và cơ chế rotation/revocation phù hợp rủi ro.

**Cấp quyền tối thiểu.** Token dành cho reports.read không nên được dùng để xóa báo cáo. Tách quyền đọc/ghi, kiểm tra ownership/resource ID trong business layer; scope không thay được object-level authorization.

**Issuer và JWK nguồn tin cậy.** Không lấy jwk-set-uri từ claim hoặc query parameter do client tự gửi. Token chứa kid do client kiểm soát chỉ được dùng để tìm key trong JWK set đã tin cậy. Nếu multi-tenant, dùng AuthenticationManagerResolver với danh sách issuer tin cậy và quy tắc tenant rõ ràng; không tin toàn bộ URL do token đưa.

**Audience.** Với nhiều API dùng cùng issuer, buộc aud cho API của mình. Nếu Resource Server cần enforce token type, scope hoặc tenant, bổ sung validation theo contract chứ không dựa vào chữ ký duy nhất.

**Rate limit và fault behavior.** Introspection liên quan network availability, JWK refresh phụ thuộc HTTP egress; thiết kế timeout, cache và retry có giới hạn. Lỗi không xác minh được token không được biến thành quyền truy cập mặc định.

**Tách các lớp bảo vệ.** Resource Server là một phần của pipeline; tiếp tục có security headers, CORS, input validation, audit, chống SSRF/injection, kiểm soát dữ liệu nhạy cảm, CSRF khi có cookie authentication và kiểm thử authorization theo đối tượng.

## 14. Bảng thuật ngữ và checklist

| Khái niệm | Nghĩa cần nhớ |
| --- | --- |
| BearerTokenAuthenticationFilter | Lấy Bearer token từ request và gọi AuthenticationManager |
| DefaultBearerTokenResolver | Đọc token từ Authorization header theo quy tắc mặc định |
| JwtDecoder | Phân tích/xác minh JWT và chạy token validators |
| JwtAuthenticationProvider | Xác thực JWT và chuyển thành JwtAuthenticationToken |
| OpaqueTokenIntrospector | Kiểm tra token qua introspection endpoint |
| OAuth2AuthenticatedPrincipal | Principal chứa attributes/authorities cho opaque token |
| SecurityContextHolder | Truy cập Authentication cho request hiện tại |
| JwtGrantedAuthoritiesConverter | Map scope/scp thành authorities có tiền tố SCOPE_ |
| BearerTokenAuthenticationEntryPoint | Phản hồi authentication challenge theo Bearer semantics |
| AuthorizationFilter | Quyết định request đã xác thực có quyền truy cập hay không |

Tự kiểm tra trước khi kết luận API an toàn:

- [ ] API nhận access token qua **Authorization: Bearer** trên HTTPS; không truyền token qua query string.
- [ ] Xác định rõ API đang dùng **JWT local validation** hay **opaque introspection**.
- [ ] JWT được kiểm tra chữ ký, issuer, thời gian và **audience của API**.
- [ ] Quy tắc scope → SCOPE_ authority đã được test, không nhầm với ROLE_ hoặc custom claims.
- [ ] Endpoint public, authenticated và scope-protected trả status đúng.
- [ ] Authentication thất bại trả 401; token hợp lệ nhưng thiếu quyền trả 403 trong policy dự kiến.
- [ ] Session và CSRF được cấu hình theo mô hình credential thực tế, không tắt CSRF chỉ vì có chữ “API”.
- [ ] Có cả MockMvc authorization tests lẫn integration tests xác minh token/issuer/JWK/introspection thật.
- [ ] Proxy, ingress, CORS và SecurityFilterChain cùng xử lý header Authorization đúng.
- [ ] Không log access token/client secret, có policy token expiry, key rotation và khả năng xử lý Authorization Server outage.

**Ghi nhớ:** oauth2ResourceServer mở đường **xác thực Bearer access token** cho ứng dụng Servlet. BearerTokenAuthenticationFilter tiếp nhận token; JwtDecoder hoặc OpaqueTokenIntrospector quyết định bằng chứng có hợp lệ; Spring Security xây dựng Authentication; cuối cùng authorization quyết định tài nguyên nào được dùng. Bảo vệ API đúng phải kiểm tra cả **nguồn token, đối tượng token hướng tới (audience), thời gian, scope và quyền nghiệp vụ**, thay vì chỉ xem token là một chuỗi có chữ ký.
