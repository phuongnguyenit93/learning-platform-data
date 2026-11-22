# Đăng nhập OIDC khác với xác thực một yêu cầu Bearer tại Resource Server

Một ứng dụng Spring Security có thể làm **OAuth 2.0 Client để đăng nhập người dùng bằng OpenID Connect (OIDC)**, làm **OAuth 2.0 Resource Server để bảo vệ API bằng Bearer Access Token**, hoặc đảm nhiệm cả hai vai trò. Hai chức năng này có thể cùng tin cậy một Identity Provider (IdP), nhưng chúng giải quyết **hai câu hỏi khác nhau**:

- **OIDC Login:** “Người dùng vừa đăng nhập là ai, và ứng dụng web duy trì phiên đăng nhập của họ như thế nào?”
- **Bearer authentication tại Resource Server:** “Yêu cầu HTTP hiện tại mang Access Token nào, token đó có hợp lệ cho API này và có đủ quyền để thực hiện thao tác không?”

Nhầm lẫn hai câu hỏi sẽ dẫn đến việc gửi ID Token vào API, trông chờ API tự chuyển hướng sang trang đăng nhập, hoặc cho rằng một lần đăng nhập OIDC tự động xác thực mọi yêu cầu Bearer.

## 1. Bối cảnh: OAuth 2.0, OIDC và các vai trò

**OAuth 2.0** là khung ủy quyền: một client nhận Access Token để gọi tài nguyên được bảo vệ. **OpenID Connect** bổ sung một lớp xác thực danh tính trên OAuth 2.0, nổi bật là **ID Token** để client xác nhận danh tính người dùng.

| Thành phần | Trách nhiệm |
| --- | --- |
| End User | Người dùng đăng nhập hoặc sử dụng ứng dụng. |
| OAuth 2.0 / OIDC Client | Ứng dụng yêu cầu đăng nhập, tham gia luồng authorization code, nhận token và xây dựng phiên đăng nhập cho người dùng. |
| Authorization Server / OpenID Provider | Xác thực người dùng, phát hành authorization code, Access Token và (trong OIDC) ID Token. |
| Resource Server | API tiếp nhận Access Token và chỉ trả dữ liệu khi token cùng quyền truy cập thỏa chính sách. |

Một IdP như Keycloak có thể đồng thời là OpenID Provider và OAuth 2.0 Authorization Server. Điều đó **không** khiến ứng dụng đăng nhập và API trở thành cùng một vai trò.

Ví dụ: website quản lý đơn hàng đăng nhập nhân viên qua OIDC; ứng dụng di động hoặc dịch vụ giao hàng gọi API đơn hàng bằng Bearer Access Token. Website cần nhận biết người đang đăng nhập. API cần đánh giá token của **mỗi yêu cầu**.

## 2. So sánh trực tiếp hai cơ chế

| Góc nhìn | Đăng nhập OIDC trong ứng dụng web | Xác thực Bearer tại Resource Server |
| --- | --- | --- |
| Điểm bắt đầu | Trình duyệt truy cập trang cần đăng nhập. | Client gửi HTTP request đến API được bảo vệ. |
| Cách mang thông tin | Browser redirect, authorization code, OIDC token; sau đó thường dùng session cookie. | Header **Authorization: Bearer ACCESS_TOKEN** trong từng request. |
| Token dùng đúng mục đích | **ID Token** giúp client xác thực danh tính người dùng; Access Token có thể dùng gọi API. | **Access Token** dành cho API đó, không dùng ID Token thay thế. |
| Đối tượng xác thực trực tiếp | Người dùng đăng nhập với OpenID Provider; client xử lý kết quả OIDC. | Yêu cầu hiện tại với Access Token do Authorization Server cấp. |
| Kiểu trao đổi | Có redirect và callback; thường qua trình duyệt. | API thường trả HTTP 401/403, không tổ chức vòng đăng nhập tương tác. |
| Trạng thái | Web backend thường lưu Authentication trong HTTP session. | API Bearer thường không lưu phiên; request nào cũng trình token. |
| Spring Security | **oauth2Login()**, **OAuth2LoginAuthenticationFilter**, **OidcUser**. | **oauth2ResourceServer()**, **BearerTokenAuthenticationFilter**, **JwtAuthenticationToken** hoặc xác thực opaque token. |
| Quyền truy cập | Quyền truy cập web có thể dựa trên principal/roles của phiên đăng nhập. | Quyền API dựa trên scope/authorities và chính sách cho tài nguyên cụ thể. |

**Cùng là “authentication” nhưng ở hai lớp khác nhau:** OIDC Login xác lập danh tính người dùng cho một client; Resource Server kiểm tra quyền sử dụng một API được chỉ định bằng Access Token.

## 3. Luồng A — Người dùng đăng nhập bằng OIDC

Giả sử ứng dụng web Spring Boot có registration ID là **oidc-web**.

~~~text
Trình duyệt                Spring Web (OIDC Client)             OpenID Provider
    | GET /profile                    |                              |
    |-------------------------------->|                              |
    | 302: cần đăng nhập              |                              |
    |<--------------------------------|                              |
    | GET /oauth2/authorization/oidc-web                            |
    |-------------------------------->|                              |
    | 302 đến authorization endpoint  |                              |
    |<--------------------------------|                              |
    |----------------------------------------------> /authorize     |
    |                          Đăng nhập, đồng ý (nếu cần)           |
    |<---------------------------------------------- code + state   |
    | GET /login/oauth2/code/oidc-web?code=...&state=...            |
    |-------------------------------->|                              |
    |                                 | POST /token (đổi code)       |
    |                                 |----------------------------->|
    |                                 |<-----------------------------|
    |                                 | ID Token + Access Token     |
    |                                 | Kiểm tra OIDC, tạo OidcUser  |
    | Set-Cookie: session, redirect   |                              |
    |<--------------------------------|                              |
    | GET /profile + session cookie   |                              |
    |-------------------------------->|                              |
    | Trang hồ sơ người dùng          |                              |
    |<--------------------------------|                              |
~~~

Diễn biến cần hiểu:

1. **Client chủ động khởi tạo login.** Spring Security chuyển hướng browser đến authorization endpoint của OpenID Provider. Authorization Code Flow là luồng phù hợp cho ứng dụng web backend.
2. **Provider xác thực người dùng.** Sau khi hoàn tất, provider redirect về callback của client kèm authorization code và tham số state. Client kiểm tra state trước khi tiếp tục.
3. **Client đổi code lấy token.** Yêu cầu đến token endpoint được thực hiện giữa các bên phù hợp với loại client. Với OIDC, phản hồi có ID Token; Access Token cũng thường được cấp.
4. **Client kiểm tra kết quả OIDC.** Việc kiểm tra ID Token bao gồm chữ ký, issuer, audience, thời hạn và các ràng buộc của luồng như nonce khi áp dụng. Đây là bằng chứng đăng nhập dành cho **client đã yêu cầu**.
5. **Ứng dụng tạo Authentication cho người dùng.** Trong Spring Security Servlet, principal của phiên OIDC thường là **OidcUser**; SecurityContext của ứng dụng web thường được lưu qua HTTP session.
6. **Các request web tiếp theo dùng phiên đăng nhập.** Browser gửi session cookie; backend khôi phục Authentication đã đăng nhập. Browser không phải gửi lại ID Token ở mỗi lần xem trang.

Đường dẫn mặc định thường gặp:

- Bắt đầu đăng nhập: **/oauth2/authorization/{registrationId}**.
- Callback nhận code: **/login/oauth2/code/{registrationId}**.

Hai đường dẫn này thuộc **OAuth 2.0 Client Login**. Resource Server không cần các endpoint ấy để kiểm tra Bearer token.

### ID Token đại diện điều gì?

Một ID Token ở dạng JWT có thể mang các claim minh họa:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "user-123",
  "aud": "web-client",
  "exp": 1790000000,
  "email": "user@example.test"
}
~~~

Giá trị **aud = web-client** nói rằng ID Token được phát hành cho OIDC Client mang client ID tương ứng. ID Token có mục tiêu chính là thông báo việc xác thực người dùng cho client. Nó **không mặc nhiên cấp quyền** gọi API đơn hàng.

Lưu ý: nội dung JSON trên chỉ minh họa payload, không phải JWT hoàn chỉnh có chữ ký; không thể dùng nó làm credential thực tế.

## 4. Luồng B — Resource Server xác thực Bearer request

Giả sử một client đã được Authorization Server cấp Access Token có quyền đọc đơn hàng. Nó gọi:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer eyJ...access-token...
~~~

Luồng Resource Server:

~~~text
API Client                         Spring Resource Server        Authorization Server
    | GET /api/orders                    |                            |
    | Authorization: Bearer ...          |                            |
    |----------------------------------->|                            |
    |                                    | Đọc Bearer token            |
    |                                    | Kiểm tra chữ ký JWT bằng    |
    |                                    | public key từ JWK Set       |
    |                                    | (hoặc introspection nếu     |
    |                                    | Access Token là opaque)     |
    |                                    |                            |
    |                                    | Kiểm tra iss, exp, nbf, aud |
    |                                    | và scope theo cấu hình      |
    |                                    |                            |
    |                                    | Tạo Authentication,         |
    |                                    | kiểm tra quyền endpoint     |
    |<-----------------------------------|                            |
    | 200, 401 hoặc 403                  |                            |
~~~

Với **JWT Access Token**, API có thể kiểm tra chữ ký bằng khóa công khai từ JWK Set, kiểm tra claims và áp dụng authorization cục bộ. Không cần gọi endpoint xác thực người dùng hay đổi authorization code cho **mỗi request**. Resource Server có thể lấy và làm mới JWK qua metadata của issuer theo cấu hình.

Với **opaque Access Token** (chuỗi token không tự giải mã được dưới dạng JWT), Resource Server thường gọi **token introspection endpoint** của Authorization Server để xác định trạng thái và thuộc tính token. Đây là lựa chọn cấu hình khác của Resource Server; không có nghĩa là phải bật OIDC Login.

Kết quả Spring Security thường là:

- Với JWT: **JwtAuthenticationToken**, principal thường là đối tượng **Jwt**, tên principal mặc định thường lấy từ **sub**.
- Với opaque token: Authentication sử dụng thông tin do introspection trả về.
- Với scope chuẩn **orders.read** trong claim **scope** hoặc **scp**, Spring Security thường ánh xạ thành authority **SCOPE_orders.read**.

Resource Server có thể xác thực token được cấp thay mặt **người dùng** hoặc theo luồng **client credentials** cho dịch vụ máy với máy. Do đó một Bearer request hợp lệ **không nhất thiết** có người dùng đăng nhập tương tác.

### Điều kiện để token phù hợp API

Để chấp nhận token, việc kiểm tra cần phù hợp với thiết kế Authorization Server và API:

1. **Chữ ký / nguồn xác minh:** JWT được ký bởi khóa thuộc nhà phát hành tin cậy, dùng thuật toán được chấp thuận; hoặc opaque token được xác nhận qua introspection tin cậy.
2. **Thời gian:** Token còn hiệu lực, xét các claim như exp và nbf.
3. **Issuer (iss):** Đúng Authorization Server mà API tin cậy.
4. **Audience (aud):** Token được phát hành cho chính API này, ví dụ **orders-api**. Đây là kiểm tra quan trọng cần cấu hình rõ.
5. **Quyền:** Scope hoặc authorities cho phép hành động cụ thể, chẳng hạn **orders.read** cho GET /api/orders.
6. **Chính sách bổ sung:** Tenant, tổ chức, chủ sở hữu tài nguyên hoặc các claim khác nếu nghiệp vụ yêu cầu.

**Chú ý về cấu hình mặc định:** khi bật JWT Resource Server chỉ với issuer URI, Spring Security kiểm tra chữ ký, thời hạn và issuer, đồng thời ánh xạ scope. API cần **bổ sung kiểm tra audience** tương ứng với API của mình; không nên suy luận rằng một JWT hợp lệ từ cùng issuer đều phù hợp.

## 5. ID Token và Access Token không thể tráo vai trò

| Thuộc tính | ID Token | Access Token |
| --- | --- | --- |
| Mục đích chính | Xác nhận danh tính/end-user authentication cho OIDC Client. | Cho phép truy cập protected resources. |
| Bên nhận dự kiến | Relying Party / OIDC Client. | Resource Server được token nhắm tới. |
| Claim quan trọng | iss, sub, aud = client ID, exp; có thể có auth_time, nonce, acr... | issuer, audience của API, thời hạn, scope/permissions; cấu trúc tùy profile và nhà cấp. |
| Định dạng | JWT theo OIDC. | Có thể là JWT hoặc opaque string. |
| Cách dùng đúng | Client kiểm tra trong quá trình đăng nhập. | Client gửi trong **Authorization: Bearer** khi gọi API. |

Ví dụ Access Token dạng JWT được phát hành cho API:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 1790000000
}
~~~

Hai token có thể có cùng **iss**, **sub** và cùng được ký bằng khóa hợp lệ, nhưng **audience và ý nghĩa khác nhau**. API cấu hình sơ sài có thể vô tình nhận cả ID Token nếu chỉ kiểm tra chữ ký, issuer và thời hạn. Đó là lỗ hổng phân tách token cần phòng ngừa bằng kiểm tra audience và token profile phù hợp, không phải bằng cách tin rằng framework tự phân biệt mọi loại JWT.

Một số nhầm lẫn điển hình:

- **“Đăng nhập OIDC xong là gọi API được.”** Chưa đủ: API cần nhận **Access Token đúng audience và scope**, hoặc một cơ chế phiên đã được thiết kế riêng cho backend đó.
- **“ID Token là JWT có chữ ký nên API cứ nhận.”** Sai mục đích: ID Token thường có audience là OIDC Client, không phải API.
- **“Mọi Access Token đều giải mã JWT được.”** Sai: Access Token có thể opaque; khi đó Resource Server cần introspection hoặc cơ chế xác minh phù hợp.
- **“Có scope openid tức là được đọc dữ liệu nghiệp vụ.”** Sai: **openid** yêu cầu cơ chế OIDC và ID Token; quyền đọc đơn hàng là scope nghiệp vụ như **orders.read**.
- **“Bearer nghĩa là có session người dùng.”** Sai: token có thể dành cho service account và mỗi request được xác thực độc lập.

## 6. Spring Boot: cấu hình hai vai trò trong cùng một ứng dụng

Đây là ví dụ ứng dụng MVC có trang **/profile** sử dụng OIDC Login và API **/api/** nhận Bearer JWT. Mỗi khu vực được phân vào một **SecurityFilterChain** để xác định rõ cách xử lý request.

### 6.1. Dependencies

Ví dụ Gradle (Groovy DSL, trong dự án Spring Boot đã có plugin quản lý dependency):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Starter **oauth2-client** phục vụ luồng login; starter **oauth2-resource-server** phục vụ Bearer authentication. Cần cả hai khi một backend làm cả hai vai trò.

### 6.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          oidc-web:
            provider: example-idp
            client-id: ${OIDC_WEB_CLIENT_ID}
            client-secret: ${OIDC_WEB_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
        provider:
          example-idp:
            issuer-uri: https://idp.example.test/realms/training
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/training
          audiences:
            - orders-api
~~~

Đây là cấu hình **minh họa**: thay issuer, client registration, audience và biến môi trường bằng giá trị thực của hệ thống. Giá trị **issuer-uri** cho client giúp khám phá metadata OIDC; giá trị issuer của Resource Server xác định nhà phát hành JWT được tin cậy. Chúng có thể trùng nhau nhưng phục vụ **hai quá trình xử lý độc lập**.

Trường **audiences** (trên các bản Spring Boot hỗ trợ thuộc tính này) yêu cầu JWT dùng cho Resource Server có **aud** chứa **orders-api**. Nếu dự án dùng phiên bản khác hoặc cần quy tắc phức tạp, cấu hình **JwtDecoder** với **OAuth2TokenValidator** tùy chỉnh như mục 6.4.

### 6.3. Hai SecurityFilterChain theo đường dẫn

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Vì sao tách chuỗi lọc?**

- Request **/api/** khớp chain có thứ tự ưu tiên cao nhất, sử dụng Bearer JWT và **STATELESS**. API không cần browser redirect để đăng nhập; request không có token hợp lệ sẽ gặp cơ chế lỗi của Resource Server.
- Request web như **/profile** khớp chain còn lại, sử dụng **oauth2Login()** với redirect, callback và session của browser.
- Chỉ vô hiệu hóa **CSRF** trong API thuần Bearer vì client chủ động gửi Authorization header. Với web dùng session cookie, vẫn giữ CSRF protection mặc định; cách áp dụng thực tế tùy endpoint và mô hình đe dọa.
- **CORS** là cơ chế riêng cho trình duyệt gọi API khác origin; bật oauth2Login hay oauth2ResourceServer không tự giải quyết CORS.

Các request matcher phải phản ánh chính xác URL và quyền của ứng dụng thật. Trong ví dụ, mọi endpoint thuộc **/api/orders/** yêu cầu scope đọc; ứng dụng thực nên phân biệt **GET** và **POST/PUT/DELETE** để áp các scope đọc/ghi khác nhau.

### 6.4. Kiểm tra audience bằng JwtDecoder khi cần tùy biến

Nếu không dùng thuộc tính **audiences** hoặc muốn kiểm soát chính sách xác minh, có thể định nghĩa decoder với validator. Chỉ dùng **một nguồn cấu hình audience** có chủ đích để tránh cấu hình lệch nhau.

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "Token is not for orders-api", null));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            audienceValidator));

        return decoder;
    }
}
~~~

**JwtValidators.createDefaultWithIssuer** giữ các quy tắc mặc định về issuer và thời hạn; **audienceValidator** bổ sung kiểm tra API đích. Thực tế có thể cần kiểm tra token profile, client/tenant và quyền chi tiết theo yêu cầu của Authorization Server. Đừng chỉ decode payload JWT mà bỏ qua chữ ký và các validators.

### 6.5. Hai endpoint cho thấy principal khác nhau

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/profile")
    Map<String, String> webProfile(@AuthenticationPrincipal OidcUser user) {
        return Map.of("loginSubject", user.getSubject());
    }

    @GetMapping("/api/whoami")
    Map<String, String> apiIdentity(@AuthenticationPrincipal Jwt jwt) {
        return Map.of("tokenSubject", jwt.getSubject());
    }

    @GetMapping("/api/orders/list")
    Map<String, String> orders() {
        return Map.of("result", "sample orders");
    }
}
~~~

Trong cấu hình này, **/profile** sử dụng principal của login bằng OIDC. **/api/whoami** sử dụng principal là JWT đến từ Bearer request; **/api/orders/list** cần authority **SCOPE_orders.read**. Đây là endpoint minh họa để quan sát security flow, chưa phải API dữ liệu thật.

Nếu client gọi **/api/whoami** bằng opaque token thì principal không phải **Jwt**; controller phải lấy kiểu **Authentication** hoặc **OAuth2AuthenticatedPrincipal** phù hợp với cấu hình opaque-token.

## 7. Thử hành vi HTTP và phân biệt lỗi

Sau khi cấu hình IdP, client và API đúng, quan sát các trường hợp:

| Request / tình huống | Hành vi dự kiến | Vì sao |
| --- | --- | --- |
| Browser GET **/profile** khi chưa đăng nhập | 302 đến trang login hoặc authorization endpoint (tùy cấu hình) | Đây là OIDC Client Login với browser redirect. |
| Browser hoàn tất OIDC rồi GET **/profile** với session cookie | 200 cùng dữ liệu của OidcUser | Ứng dụng đã duy trì phiên đăng nhập. |
| GET **/api/orders/list** không có Bearer token | 401 Unauthorized, thường có WWW-Authenticate: Bearer | API yêu cầu xác thực Bearer. |
| API nhận token sai chữ ký, hết hạn, sai issuer hoặc audience | 401 Unauthorized | Authentication thất bại. |
| API nhận Access Token hợp lệ nhưng thiếu **orders.read** | 403 Forbidden | Đã xác thực nhưng không đủ authority. |
| API nhận Access Token hợp lệ, đúng audience và có **orders.read** | 200, nếu endpoint xử lý thành công | Qua được authentication và authorization. |
| Gửi ID Token có audience chỉ là **web-client** đến API yêu cầu **orders-api** | 401 Unauthorized | Không đạt điều kiện audience; không phải Access Token dành cho API. |

Các lệnh thử (thay placeholder bằng Access Token thực do Authorization Server phát hành):

~~~bash
curl -i http://localhost:8080/api/orders/list

curl -i -H "Authorization: Bearer YOUR_ACCESS_TOKEN" http://localhost:8080/api/whoami

curl -i -H "Authorization: Bearer YOUR_ACCESS_TOKEN" http://localhost:8080/api/orders/list
~~~

Với browser, mở **http://localhost:8080/profile** và đăng nhập qua IdP. Để khởi tạo luồng OIDC trực tiếp, có thể mở **http://localhost:8080/oauth2/authorization/oidc-web**. Callback URL phải được đăng ký chính xác với IdP, chẳng hạn **http://localhost:8080/login/oauth2/code/oidc-web** trong môi trường phát triển được cho phép.

Không suy ra **403** chỉ từ việc trả thiếu token: thiếu/không hợp lệ token thuộc bước **authentication** nên thường là **401**; chỉ khi token hợp lệ nhưng quyền không đủ mới thuộc bước **authorization** và thường là **403**.

## 8. Một hệ thống có thể kết hợp hai cách theo những kiến trúc nào?

### Kiến trúc A: Server-rendered web, session cookie

Browser đăng nhập OIDC vào web backend. Spring Security lưu Authentication vào session. Browser truy cập trang bằng cookie; backend có thể dùng Access Token đã được client lưu để gọi API downstream qua cơ chế **OAuth2AuthorizedClient**, với chính sách cấp token thích hợp. Bản thân trình duyệt không nhất thiết phải xử lý token.

### Kiến trúc B: SPA / mobile + API Resource Server

Frontend thực hiện luồng authorization code với PKCE theo thiết kế phù hợp, nhận **Access Token** và gửi nó trong Authorization header khi gọi backend API. Backend chỉ cần bật **oauth2ResourceServer()** để xử lý những API request đó. Frontend có thể cũng có quá trình OIDC Login, nhưng trạng thái đăng nhập của frontend **không thay thế** việc backend xác minh Access Token.

### Kiến trúc C: Backend for Frontend (BFF)

Browser làm việc với BFF qua session cookie; BFF thực hiện OIDC Login và quản lý token ở server. BFF chuyển tiếp các lời gọi cần thiết đến Resource Server bằng Access Token thích hợp. Khi đó cần phân biệt:

- **Browser → BFF:** cookie phiên đăng nhập, có CSRF protection phù hợp.
- **BFF → Resource Server:** Bearer Access Token và kiểm tra quyền tại API.

### Kiến trúc D: Service-to-service

Một service dùng grant **client_credentials** để lấy Access Token cho chính nó rồi gọi API. Resource Server tiếp nhận Bearer token như bình thường; không có user login, ID Token hay session browser trong đường đi này.

## 9. Các lỗi cấu hình và nguyên tắc triển khai

1. **Nhầm audience của ID Token với audience của API.** Hãy yêu cầu Access Token được cấp cho resource/audience đúng, và xác thực audience tại Resource Server.
2. **Tin mọi JWT cùng issuer.** Chữ ký hợp lệ chưa đủ để quyết định một token phù hợp cho mọi ứng dụng hoặc mọi API.
3. **Dùng sai bộ lọc cho endpoint.** Nếu một API chỉ dành cho client gửi Bearer token, cấu hình **oauth2Login()** đơn thuần có thể dẫn tới redirect và nội dung HTML thay vì phản hồi API 401 thích hợp.
4. **Gộp session login vào API một cách vô tình.** Dùng matcher và SecurityFilterChain theo khu vực; nếu API chủ trương stateless, áp chính sách session thích hợp.
5. **Tắt CSRF trên mọi endpoint vì có API Bearer.** Cookie-based web vẫn chịu rủi ro CSRF; xem xét CSRF riêng theo bề mặt xác thực.
6. **Dùng role/scope thiếu quy ước.** Resource Server mặc định ánh xạ scope thành authority tiền tố **SCOPE_**; các role tùy biến từ claim như realm_access hoặc roles phải được chuyển đổi rõ ràng.
7. **Nhầm 401 với 403.** Chưa được xác thực hoặc token hỏng → 401; token hợp lệ nhưng thiếu quyền → 403.
8. **Đặt token vào URL hay log.** Bảo vệ token như thông tin bí mật, dùng HTTPS, tránh query string và log token đầy đủ; Bearer token có thể bị dùng lại nếu lộ.
9. **Quên thời hạn token và refresh.** Client có thể quản lý refresh token theo chính sách của Authorization Server; Resource Server thông thường **không** dùng refresh token để sửa một request Access Token đã hết hạn.
10. **Giả định JWT Access Token luôn có claim cố định.** Phải kiểm tra tài liệu của Authorization Server: tên claim scope, audience, permissions, format token, mô hình tenant và token profile có thể khác nhau.

## 10. Cách tự chọn đúng cơ chế

Khi thiết kế một endpoint, đặt câu hỏi theo thứ tự:

1. **Đây là trang web phục vụ người dùng trong trình duyệt?** Cần một quy trình đăng nhập tương tác và session? Khi ấy **OIDC Login / oauth2Login()** là ứng viên phù hợp.
2. **Đây là API được gọi bằng Authorization: Bearer?** Khi ấy **Resource Server / oauth2ResourceServer()** cần kiểm tra Access Token cho từng request.
3. **Cả hai loại endpoint tồn tại trong cùng ứng dụng?** Dùng đường dẫn và SecurityFilterChain có phạm vi rõ, hoặc tách thành các dịch vụ riêng.
4. **Ai nhận token và token được phát hành cho ai?** ID Token dành cho OIDC Client; Access Token phải phù hợp Resource Server, scope và chính sách dữ liệu.

**Ghi nhớ:** OIDC Login xác thực danh tính người dùng **cho client** và thường xây dựng phiên đăng nhập; Bearer authentication xác thực **request đến API** bằng Access Token. Cùng IdP hoặc cùng JWT không làm cho hai cơ chế trở thành một.

## Tài liệu tham khảo

- [Spring Security — OAuth 2.0 và OIDC: tổng quan các vai trò](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html).
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html).
- [Spring Security — OAuth 2.0 Resource Server với JWT và token validation](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
