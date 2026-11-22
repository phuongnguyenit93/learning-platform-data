# Phân biệt đăng xuất cục bộ, thu hồi token và đăng xuất tại hệ thống danh tính ngoài

## Mục tiêu bài học

Trong ứng dụng Spring Security, chữ **“đăng xuất”** có thể chỉ ba hành động hoàn toàn khác nhau:

1. **Đăng xuất cục bộ (local logout):** chấm dứt phiên và Authentication của **ứng dụng hiện tại**.
2. **Thu hồi token (token revocation):** yêu cầu hệ thống phát hành hoặc kho xác minh làm cho một **access token, refresh token hay credential dài hạn** không còn sử dụng được.
3. **Đăng xuất tại hệ thống danh tính ngoài (federated / Identity Provider logout):** chấm dứt phiên **SSO tại OpenID Provider hoặc Identity Provider**, đôi khi phối hợp thông báo đăng xuất đến các ứng dụng khác.

Ba hành động này có thể cùng xảy ra, nhưng **không hành động nào tự động bao hàm hai hành động còn lại**. Một nút “Đăng xuất” trông đơn giản ở giao diện có thể cần một workflow nhiều bước, nhiều hệ thống và nhiều loại credential.

Sau bài học, bạn có thể:

- Giải thích ranh giới trách nhiệm của **Spring Security LogoutFilter**, **OAuth 2.0 revocation endpoint**, **OIDC RP-Initiated Logout / Back-Channel Logout** và **SAML Single Logout (SLO)**.
- Chỉ ra vì sao xóa `JSESSIONID` không tự thu hồi access token, còn thu hồi refresh token không nhất thiết làm JWT access token hiện tại ngừng được chấp nhận ngay.
- Cấu hình một **local logout** chuẩn trong Spring Boot Servlet và kiểm chứng bằng Java 17+ / curl.
- Tích hợp hướng **OIDC RP-Initiated Logout** bằng `OidcClientInitiatedLogoutSuccessHandler` khi có một OIDC Provider hỗ trợ.
- Viết một client Java 17 gửi **RFC 7009 token revocation request** tới Authorization Server, đồng thời hiểu giới hạn của HTTP 200.
- Thiết kế kịch bản kiểm thử đúng cho “đăng xuất trên thiết bị này”, “đăng xuất tất cả thiết bị” và “đăng xuất khỏi SSO”.

**Phạm vi:** Spring Security **Servlet** (Spring Boot / Spring MVC) và các chuẩn OAuth 2.0, OpenID Connect 1.0, SAML 2.0. Với WebFlux, lớp filter, session và API cấu hình khác. Ví dụ local logout chạy không cần IdP; ví dụ OIDC/revocation **yêu cầu một provider thật** để kiểm thử end-to-end.

## 1. Vẽ ranh giới của từng hệ thống

Một hệ thống sử dụng SSO thường có ít nhất bốn lớp trạng thái:

~~~text
                        Trình duyệt
                     /      |       \
                    v       v        v
             Cookie App  Cookie IdP  Access/Refresh token
                    |       |        |
                    v       v        v
           +--------------+  +-------------------+
           | Ứng dụng A   |  | Identity Provider |
           | HttpSession  |  | (OP / IdP)         |
           | SecurityCtx  |  | SSO session        |
           +--------------+  +-------------------+
                    |                   |
                    v                   v
             Resource API          Token service
                /                      |
               v                       v
        Token validator          Revocation store
~~~

**Các sự thật cần ghi nhớ:**

- **App session** và **IdP session** thường dùng cookie **khác domain**, được phát bởi hai bên khác nhau.
- **OAuth access token** là credential để truy cập API; không nhất thiết có liên hệ một-một với HttpSession của trình duyệt.
- **Refresh token** cho phép client xin access token mới; ngừng cấp token mới và ngừng chấp nhận token cũ là hai vấn đề khác nhau.
- **ID token** của OpenID Connect chứng thực sự kiện đăng nhập và chứa thông tin người dùng. Nó **không** phải access token dùng để gọi API và cũng không phải lệnh logout.
- Ứng dụng A và B có thể cùng đăng nhập từ một IdP nhưng giữ **hai phiên cục bộ khác nhau**. Hủy A không có nghĩa B sẽ tự biến mất.
- Cookie bị xóa trên trình duyệt hiện tại không xóa bản sao cookie đã bị đánh cắp, không hủy toàn bộ session trên server và không gọi revocation endpoint.

Trước khi viết logout logic, phải trả lời rõ: **logout cái gì, ở đâu, trên thiết bị nào, trong bao lâu và với mức bảo đảm nào?**

## 2. Bảng so sánh ba thao tác

| Tiêu chí | Local logout | Token revocation | Logout tại IdP |
| --- | --- | --- | --- |
| **Nơi thực hiện** | Ứng dụng / Relying Party (RP) | Authorization Server hoặc kho token của issuer | OpenID Provider / SAML Identity Provider |
| **Đối tượng chính** | HttpSession, SecurityContext, cookie của ứng dụng | Refresh token, access token hoặc credential cần thu hồi | Phiên đăng nhập SSO của provider |
| **Cơ chế điển hình** | `POST /logout`, `LogoutFilter` | OAuth RFC 7009 `POST /revoke` hoặc API provider | OIDC `end_session_endpoint`, back-channel/front-channel; SAML SLO |
| **Cần trình duyệt?** | Thường có với browser app, không bắt buộc cho API | Không; client/backend có thể gọi trực tiếp | RP-Initiated thường redirect browser; back-channel là server-to-server |
| **Ảnh hưởng ứng dụng khác?** | Không mặc nhiên | Tùy các app dùng token/grant bị thu hồi | Tùy khả năng IdP và cơ chế SLO của từng RP |
| **Ảnh hưởng access JWT đang còn hạn?** | Không mặc nhiên | Có thể không tức thời nếu resource server xác minh JWT offline | Không mặc nhiên |
| **Ảnh hưởng refresh token?** | Không mặc nhiên | Có nếu yêu cầu và server hỗ trợ | Tùy chính sách IdP/authorization server |
| **Có thể logout tất cả thiết bị?** | Cần hủy các session theo user | Cần revoke mọi grant/refresh token liên quan theo chính sách | Tùy phạm vi phiên tại IdP, SLO và phiên tại từng ứng dụng |

Không sử dụng một ô “logout=true” trong UI như bằng chứng rằng mọi loại token/session ở mọi nơi đã bị thu hồi.

## 3. Local logout trong Spring Security Servlet

### 3.1. LogoutFilter làm gì?

Khi ứng dụng dùng Spring Security Servlet thông thường, framework hỗ trợ endpoint `/logout`. Với CSRF được bật, **GET /logout** thường hiển thị trang xác nhận; **POST /logout** với CSRF token hợp lệ thực hiện logout.

Các `LogoutHandler` tiêu chuẩn xử lý những việc như:

- **SecurityContextLogoutHandler:** vô hiệu hóa HttpSession theo cấu hình, xóa SecurityContext khỏi holder/repository.
- **RememberMeServices:** làm sạch remember-me cookie và, nếu dùng persistent remember-me, có thể xóa token remember-me phía server.
- **CsrfLogoutHandler:** xóa CSRF token đã lưu khi logout.
- **LogoutSuccessEventPublishingLogoutHandler:** phát sự kiện logout.
- **LogoutSuccessHandler:** quyết định response/redirect sau khi cleanup, ví dụ redirect `/login?logout` hoặc trả HTTP 204.

Sơ đồ:

~~~text
POST /logout + CSRF hợp lệ
       |
       v
    LogoutFilter
       |
       +--> invalidate HttpSession (nếu được cấu hình)
       +--> clear SecurityContext
       +--> cleanup remember-me
       +--> cleanup CSRF / phát event
       |
       v
    LogoutSuccessHandler
       |
       +--> HTTP 302 đến trang public
         HOẶC HTTP 204 cho API
~~~

### 3.2. Local logout KHÔNG làm gì?

Nếu cấu hình chỉ có local logout:

- Không tự gọi **OAuth token revocation endpoint** ở Authorization Server.
- Không tự hủy session **SSO cookie tại IdP**.
- Không tự hủy HttpSession của **ứng dụng B** hoặc các session khác của ứng dụng A trên thiết bị khác.
- Không tự làm access token JWT đã bị sao chép mất hiệu lực ở mọi API.
- Không tự revoke refresh token được lưu bởi một backend client, trừ khi ứng dụng có logic riêng hoặc provider integration thực hiện.
- Không đảm bảo mọi cookie browser đã bị xóa nếu cấu hình domain/path không khớp.

**Tình huống rất phổ biến:** người dùng click “Đăng xuất” ở A, phiên của A bị hủy; click “Đăng nhập” lại và được đưa qua IdP vẫn còn SSO session, nên IdP có thể đăng nhập A trở lại **không yêu cầu nhập password**. Đó không nhất thiết là lỗi local logout: bạn chưa yêu cầu IdP logout.

### 3.3. Dùng POST và CSRF thay vì logout bằng GET

Một endpoint logout qua GET dễ bị kích hoạt bởi ảnh, link, prefetch hoặc trang bên ngoài. Trong browser app có cookie, hãy giữ CSRF protection và dùng **POST /logout**.

Đừng tắt toàn bộ CSRF để “logout hoạt động”. Nếu ứng dụng là API stateless với Bearer token gửi chủ động trong header, threat model có thể khác; vẫn cần quyết định dựa trên cách client gửi credential, không chỉ dựa trên nhãn REST.

### 3.4. Tự viết controller logout có thể sai ở đâu?

Nếu chỉ làm:

~~~java
// Đoạn minh họa CHƯA đủ để thay LogoutFilter.
SecurityContextHolder.clearContext();
return ResponseEntity.noContent().build();
~~~

Bạn mới dọn context cho request hiện tại, còn HttpSession, SecurityContextRepository, cookie, remember-me và các handler khác có thể chưa được xử lý. Trong Spring Security 6, nên dùng **`http.logout(...)`** hoặc gọi đúng các LogoutHandler với lý do rõ ràng; đừng chỉ xóa ThreadLocal rồi tuyên bố đã logout hoàn toàn.

## 4. Ví dụ chạy được: local logout bằng Spring Boot + Java 17

Ví dụ này cố tình **không có OAuth hay IdP**. Nó chứng minh local logout đúng cách, để bạn so sánh với các luồng liên bang ở phần sau.

### 4.1. Dự án Gradle

Yêu cầu Java 17+, Gradle wrapper tương thích Spring Boot. Tạo:

~~~text
local-logout-demo/
  settings.gradle
  build.gradle
  src/main/java/example/logout/LocalLogoutApplication.java
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'local-logout-demo'
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

### 4.2. Mã Java hoàn chỉnh

Tạo file **src/main/java/example/logout/LocalLogoutApplication.java**:

~~~java
package example.logout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.HttpStatusReturningLogoutSuccessHandler;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LocalLogoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(LocalLogoutApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                .password(encoder.encode("change-me"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/csrf").permitAll()
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            )
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .logoutSuccessHandler(
                    new HttpStatusReturningLogoutSuccessHandler(
                        HttpStatus.NO_CONTENT
                    )
                )
            );
        return http.build();
    }

    @RestController
    public static class Api {

        public record CsrfInfo(String headerName, String token) {}
        public record MeInfo(String username) {}

        @GetMapping("/csrf")
        public CsrfInfo csrf(CsrfToken token) {
            return new CsrfInfo(
                token.getHeaderName(), token.getToken()
            );
        }

        @GetMapping("/me")
        public MeInfo me(Authentication authentication) {
            return new MeInfo(authentication.getName());
        }
    }
}
~~~

**Lý do cấu hình:**

- **IF_REQUIRED:** Spring Security tạo session khi cần; đăng nhập form có thể lưu Authentication vào HttpSession.
- **formLogin:** dùng authentication mechanism chuẩn, không tự viết controller login nên không cần xử lý thủ công mọi bước `SecurityContextRepository.saveContext(...)`.
- **logout:** hủy session và làm sạch Authentication; trả **204 No Content** để dễ dùng trong API. Đây là xử lý **cục bộ**, không có mã nào gọi IdP hay revoke OAuth token.
- **/csrf:** cung cấp CSRF token cho client thử form POST; không cần tắt CSRF.
- **demo/change-me:** tài khoản học tập; production dùng user store và password policy thích hợp.

Ví dụ không bật `oauth2Login()`, không có `OAuth2AuthorizedClientService` hay token access/refresh, nên không thể kết luận gì về token revocation từ demo này.

### 4.3. Chạy và thử local logout

Tại thư mục project:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Ứng dụng mặc định chạy tại **http://localhost:8080**. Các lệnh sau dùng **Bash/WSL/Git Bash, curl và Python 3**.

**Bước 1 — lấy CSRF token và cookie phiên:**

~~~bash
csrf=$(curl -fsS -c cookies.txt \
  http://localhost:8080/csrf \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
test -n "$csrf"
~~~

**Bước 2 — form login với cookie và CSRF token:**

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $csrf" \
  --data-urlencode "username=demo" \
  --data-urlencode "password=change-me" \
  http://localhost:8080/login
~~~

Kết quả thường là **302 redirect** sau login thành công. Spring Security có thể thay session ID để chống session fixation; cookie jar được cập nhật nếu server trả Set-Cookie.

**Bước 3 — dùng phiên mới để truy cập endpoint bảo vệ:**

~~~bash
curl -sS -b cookies.txt http://localhost:8080/me
# {"username":"demo"}
~~~

Đây là **Authentication từ session của ứng dụng này**, không phải phiên IdP.

**Bước 4 — lấy CSRF token mới (token cũ có thể bị xoay sau login):**

~~~bash
csrf=$(curl -fsS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
~~~

**Bước 5 — POST logout bằng cùng phiên:**

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $csrf" \
  -X POST http://localhost:8080/logout
# HTTP/1.1 204 (dòng trạng thái dự kiến)
~~~

**Bước 6 — thử dùng cookie cũ:**

~~~bash
curl -i -b cookies.txt http://localhost:8080/me
# Thường 302 về /login, vì đã không còn Authentication
~~~

Đừng cứng nhắc kỳ vọng 401 trong ví dụ **formLogin**: với form entry point, request vô danh thường được redirect tới `/login`. Mã 204 ở bước logout được cấu hình rõ ràng; nội dung header chi tiết còn phụ thuộc Servlet container.

**Điều đã chứng minh:** phiên local bị hủy và request sau không còn đăng nhập cục bộ. **Điều chưa chứng minh:** token OAuth/SSO/ứng dụng khác đã được thu hồi.

## 5. Thu hồi token theo OAuth 2.0 RFC 7009

### 5.1. Revocation endpoint là gì?

OAuth 2.0 Token Revocation (RFC 7009) quy định client có thể gửi **HTTP POST** tới revocation endpoint của **Authorization Server** để thông báo token không còn được dùng.

Request khái niệm:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: authorization-server.example
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client credentials được encode>

token=<token-value>&token_type_hint=refresh_token
~~~

Đường dẫn `/oauth2/revoke` chỉ là ví dụ; **địa chỉ thật do Authorization Server công bố**. Không tự đoán URL revocation của một IdP. Với một confidential client, thường xác thực client bằng client ID/secret, private_key_jwt, mTLS hoặc cơ chế được server hỗ trợ.

Các tham số phổ biến:

- **token:** giá trị token muốn revoke; gửi qua kết nối HTTPS.
- **token_type_hint:** gợi ý loại token, thường `refresh_token` hoặc `access_token`; chỉ là **hint**, không bảo đảm issuer sẽ chỉ tìm đúng loại đó.
- **client authentication:** bảo đảm client được phép yêu cầu thu hồi token thuộc authorization grant/client tương ứng.

**RFC 7009 yêu cầu hỗ trợ thu hồi refresh token và khuyến nghị hỗ trợ access token**, với các điều kiện và chính sách có thể khác theo issuer.

### 5.2. HTTP 200 của revocation nghĩa là gì?

Đây là điểm dễ hiểu sai: RFC 7009 quy định **response thành công vẫn là HTTP 200 nếu token được gửi vốn đã không hợp lệ hoặc không tìm thấy**. Cách này hạn chế việc dò token có tồn tại.

Do đó:

- HTTP 200 nghĩa là **revocation request được server xử lý theo giao thức**, không phải bằng chứng rằng token đã từng tồn tại.
- Không log token raw, không in token vào phản hồi frontend.
- Sau HTTP 200, client phải **ngừng dùng token đó**, xóa bản lưu an toàn và cập nhật trạng thái local.
- Không suy ra mọi access token được cấp từ cùng grant đều ngừng hoạt động tức thời; điều đó phụ thuộc khả năng và chính sách Authorization Server.

### 5.3. Refresh token và access token khác nhau khi revoke

**Refresh token:** nếu bị revoke, client thường không thể tiếp tục đổi nó lấy access token mới; server cũng có thể revoke cả token family/authorization grant.

**Opaque access token:** API có thể hỏi introspection endpoint (RFC 7662) hoặc shared server store; khi token bị thu hồi, hệ thống có thể trả `active=false` ở lần kiểm tra tiếp theo, tùy cache và thời gian đồng bộ.

**Self-contained JWT access token:** nhiều Resource Server xác minh JWT offline bằng chữ ký, issuer, audience và `exp`. Nếu không có introspection/denylist/security epoch hoặc kiểm tra trạng thái server-side, **JWT có chữ ký đúng vẫn có thể được chấp nhận cho đến khi hết hạn**, dù refresh token đã bị revoke.

Bảng:

| Credential | Khi revoke thường thay đổi gì? | Cần chú ý |
| --- | --- | --- |
| **Refresh token** | Không còn xin access token mới được | Token family, rotation, session grant, chính sách issuer |
| **Opaque access token** | Có thể bị introspection/store báo inactive | Cache introspection và độ trễ propagation |
| **JWT access token** | Không nhất thiết ngừng được chấp nhận ngay bởi API kiểm tra offline | TTL ngắn, denylist, token version hoặc introspection theo yêu cầu |
| **ID token** | Không phải OAuth access token; không mặc nhiên là mục tiêu revocation chuẩn để “logout” | IdP session và RP session xử lý riêng |
| **Local HttpSession cookie** | Không tự bị hủy khi revoke OAuth token | Cần local logout/SessionRegistry tương ứng |

**Mẹo thiết kế:** nếu yêu cầu “ngừng quyền truy cập trong vài giây” thì một JWT sống 60 phút được kiểm tra offline sẽ không đáp ứng chỉ bằng revoke refresh token. Cần chọn token lifetime, cache TTL, back-channel revocation/denylist và độ trễ chấp nhận được ngay từ kiến trúc.

### 5.4. Lưu token ở đâu và ai được phép revoke?

Một ứng dụng BFF/server-side OAuth client thường lưu Authorized Client trên server, kết nối tới user session. Một SPA có thể dùng cơ chế BFF hoặc luồng riêng với giới hạn của public client. Phương án lưu phụ thuộc OAuth threat model; không đặt client secret trong JavaScript browser.

Với Spring Security OAuth2 Client:

- **OAuth2AuthorizedClientService** hoặc **OAuth2AuthorizedClientRepository** giữ thông tin access/refresh token của client.
- Gọi `removeAuthorizedClient(registrationId, principalName)` sẽ **xóa dữ liệu Authorized Client cục bộ**, không phải yêu cầu OAuth RFC 7009 tới provider.
- Nếu muốn revoke ở AS, phải có **HTTP request riêng** tới endpoint đúng với client authentication phù hợp hoặc dùng SDK/API mà provider cung cấp.
- Sau khi revoke, nên dọn bản lưu local để tránh tái sử dụng token, nhưng không đảo ngược thứ tự hay nuốt lỗi một cách có thể tạo tuyên bố “đã revoke” sai.

## 6. Ví dụ Java 17: gửi yêu cầu RFC 7009 tới Authorization Server

Đây là một chương trình **Java SE độc lập**, không dùng thư viện Spring. Nó chỉ thực sự thành công khi bạn đã có Authorization Server hỗ trợ RFC 7009, đúng endpoint, client credential và token. Ví dụ này **không phát hành token hoặc giả lập issuer**.

Tạo file **RevokeOAuthToken.java**:

~~~java
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class RevokeOAuthToken {

    private RevokeOAuthToken() {
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Missing environment variable: " + key
            );
        }
        return value;
    }

    private static String encode(String value) {
        return URLEncoder.encode(
            value, StandardCharsets.UTF_8
        );
    }

    public static void main(String[] args) throws Exception {
        URI endpoint = URI.create(required("REVOCATION_ENDPOINT"));
        if (!"https".equalsIgnoreCase(endpoint.getScheme())) {
            throw new IllegalArgumentException(
                "Revocation endpoint must use HTTPS"
            );
        }

        String clientId = required("OAUTH_CLIENT_ID");
        String clientSecret = required("OAUTH_CLIENT_SECRET");
        String token = required("TOKEN_TO_REVOKE");

        // OAuth client password credentials qua HTTP Basic.
        String basicPair = encode(clientId) + ":" + encode(clientSecret);
        String basic = Base64.getEncoder().encodeToString(
            basicPair.getBytes(StandardCharsets.UTF_8)
        );

        String body = "token=" + encode(token)
            + "&token_type_hint=refresh_token";

        HttpRequest request = HttpRequest.newBuilder(endpoint)
            .header("Content-Type",
                "application/x-www-form-urlencoded")
            .header("Authorization", "Basic " + basic)
            .POST(HttpRequest.BodyPublishers.ofString(body))
            .build();

        HttpClient client = HttpClient.newHttpClient();
        HttpResponse<Void> response = client.send(
            request, HttpResponse.BodyHandlers.discarding()
        );

        if (response.statusCode() == 200) {
            System.out.println("Revocation request accepted");
        } else {
            System.out.println(
                "Revocation request failed; HTTP "
                    + response.statusCode()
            );
        }
    }
}
~~~

Compile/run bằng JDK 17+:

~~~bash
javac RevokeOAuthToken.java
java RevokeOAuthToken
~~~

Cần cấu hình các biến môi trường **REVOCATION_ENDPOINT**, **OAUTH_CLIENT_ID**, **OAUTH_CLIENT_SECRET**, **TOKEN_TO_REVOKE** trước khi chạy. Không chép giá trị token/client secret thật vào tài liệu, source code, shell history hoặc CI log.

Nếu provider hỗ trợ `client_secret_basic` và xử lý thành công, stdout dự kiến là:

~~~text
Revocation request accepted
~~~

Nếu issuer trả status lỗi, chương trình chỉ in mã HTTP, không in secret. **Chương trình không tuyên bố token chắc chắn đã bị API ngừng chấp nhận ngay**; đó là kiểm thử riêng.

**Giới hạn mẫu:**

- Dùng `token_type_hint=refresh_token`; nếu thu hồi access token, thay hint phù hợp.
- RFC 6749 cho phép client authentication khác Basic; sử dụng đúng cơ chế issuer yêu cầu. Không áp dụng Basic với public client không có secret.
- Không bật retry vô hạn. Nếu bị timeout, không biết server đã xử lý request hay chưa; client cần thiết kế retry an toàn/idempotent và quan sát trạng thái.
- Không dùng endpoint HTTP không mã hóa trong production. Không truyền token ở URL/query string.
- HTTP 200 không chứng minh access JWT đã bị từ chối; cần request tới Resource Server và quan sát thời điểm hết hiệu lực theo chính sách.

## 7. Đăng xuất tại hệ thống danh tính ngoài: OpenID Connect

### 7.1. RP và OP là ai?

- **RP (Relying Party):** ứng dụng sử dụng đăng nhập liên bang, ví dụ website A.
- **OP (OpenID Provider):** hệ thống xác thực người dùng, giữ phiên SSO (ví dụ một máy chủ danh tính doanh nghiệp).
- **Session tại RP:** phiên browser với website A; không đồng nhất với phiên tại OP.
- **Session tại OP:** phiên giúp user đăng nhập nhiều RP mà không nhập lại credential.

**OIDC login thành công không hàm ý OIDC logout đã được cấu hình.** `oauth2Login()` giúp ứng dụng đăng nhập qua provider, còn việc phối hợp logout cần cơ chế riêng.

### 7.2. Chỉ local logout khi dùng OIDC

~~~text
Browser -> POST /logout ở RP A
            |
            +--> A hủy HttpSession A
            +--> A xóa cookie A
            |
            v
       IdP SSO cookie vẫn còn
            |
            v
Browser -> /oauth2/authorization/<registrationId>
            |
            +--> redirect đến OP
            +--> OP thấy SSO session còn hợp lệ
            +--> user có thể đăng nhập lại A không cần password
~~~

Đây là kết quả hợp lệ của local logout. Nếu sản phẩm yêu cầu “thoát cả tài khoản SSO”, cần thao tác ở OP, không chỉ tại A.

### 7.3. OIDC RP-Initiated Logout (client khởi xướng)

Chuẩn **OpenID Connect RP-Initiated Logout 1.0** cho phép RP redirect user agent tới **end_session_endpoint** do OP công bố, thường lấy từ Discovery metadata.

Luồng:

~~~text
User nhấn "Đăng xuất"
       |
       v
RP A chạy local logout
       |
       +--> LogoutSuccessHandler tạo redirect đến OP
       |       - end_session_endpoint của OP
       |       - có thể có id_token_hint
       |       - có thể có post_logout_redirect_uri
       |
       v
Browser đến OP logout endpoint
       |
       v
OP thực hiện chính sách chấm dứt SSO session
       |
       +--> Có thể yêu cầu xác nhận của user
       +--> Có thể thông báo logout tới các RP khác
       |
       v
Browser có thể được redirect về RP A theo URI đã đăng ký
~~~

**Các tham số cần hiểu:**

- **end_session_endpoint:** URL OP dành cho logout, không được suy ra từ token endpoint.
- **id_token_hint:** ID token đã được OP cấp, giúp OP xác định user/session của yêu cầu logout. Không thay bằng access token.
- **post_logout_redirect_uri:** địa chỉ quay lại RP; phải phù hợp với danh sách được OP cho phép/đăng ký. Không lấy URI tùy ý từ query parameter user rồi redirect, tránh open redirect.
- **state:** tùy chuẩn/triển khai, giúp RP liên kết response với yêu cầu logout; cần cấu hình và kiểm tra phù hợp.

**Không hứa OP luôn logout mọi RP.** RP-Initiated Logout yêu cầu OP kết thúc phiên theo chính sách và có thể kích hoạt thông báo liên bang, nhưng ảnh hưởng tới A/B phụ thuộc OP/RP có hỗ trợ front-channel/back-channel SLO và khả năng nhận thông báo.

### 7.4. Spring Security: OidcClientInitiatedLogoutSuccessHandler

Khi ứng dụng Spring Boot đã cấu hình **OAuth2/OIDC client registration** hợp lệ, có thể dùng handler:

~~~java
// Đoạn cấu hình tích hợp vào application có OIDC ClientRegistration.
@Bean
LogoutSuccessHandler oidcLogoutSuccessHandler(
        ClientRegistrationRepository registrations) {

    OidcClientInitiatedLogoutSuccessHandler handler =
        new OidcClientInitiatedLogoutSuccessHandler(registrations);

    handler.setPostLogoutRedirectUri("{baseUrl}/signed-out");
    return handler;
}

@Bean
SecurityFilterChain oidcSecurityFilterChain(
        HttpSecurity http,
        LogoutSuccessHandler oidcLogoutSuccessHandler)
        throws Exception {

    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/signed-out").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2Login(Customizer.withDefaults())
        .logout(logout -> logout
            .logoutSuccessHandler(oidcLogoutSuccessHandler)
        );

    return http.build();
}
~~~

Đây là **cấu hình trích**: cần class `@Configuration` hoặc `@SpringBootApplication`, import `@Bean`, `LogoutSuccessHandler`, `OidcClientInitiatedLogoutSuccessHandler`, `ClientRegistrationRepository`, `SecurityFilterChain`, `Customizer`, `HttpSecurity`, dependency `spring-boot-starter-oauth2-client`, client registration chứa issuer URI/credentials hợp lệ và endpoint `GET /signed-out` public.

Khi được hỗ trợ, handler dùng thông tin OIDC hiện có và discovery của provider để tạo redirect đến logout endpoint. **Nếu provider không công bố end_session_endpoint hoặc phiên không phải OIDC, handler không thể bảo đảm logout toàn bộ IdP**. Phải test với provider thật, không chỉ kiểm tra Spring context khởi động.

Để tránh cấu hình Bean trùng, **không chép nguyên SecurityFilterChain thứ hai** vào một ứng dụng đang có chain khác mà không hiểu `securityMatcher`/thứ tự chain. Ví dụ local demo ở mục 4 và OIDC snippet là **hai bối cảnh cấu hình khác nhau**.

### 7.5. OIDC Back-Channel Logout: OP chủ động thông báo cho RP

Không phải lúc nào user cũng nhấn logout trong ứng dụng A. User có thể logout ở OP hoặc tài khoản bị thu hồi; OP có thể thông báo cho các RP qua **OIDC Back-Channel Logout**.

Luồng:

~~~text
OP: user logout / account session ended
          |
          v
OP ký Logout Token (JWT có claims theo đặc tả)
          |
          v
Server-to-server POST đến RP logout endpoint
          |
          v
RP xác minh chữ ký, iss, aud, iat, jti, events, sid/sub
          |
          v
RP tìm local session ứng với sid hoặc subject và issuer
          |
          v
RP hủy các session tương ứng
~~~

**Logout Token không phải access token hay ID token thông thường.** Theo đặc tả, nó có events claim nhận dạng sự kiện back-channel logout; phải xác minh issuer, audience, signature, timestamps, session/subject, chống replay và yêu cầu **không có nonce**.

- Nếu token có **sid**, RP có thể xác định phiên liên quan tới OP session cụ thể.
- Nếu không có sid nhưng có **sub**, RP thường phải xem xét chấm dứt các phiên của cùng subject trong phạm vi issuer/audience.
- Token cần được kiểm tra toàn diện; không chấp nhận một JSON tự khai `sub` như lệnh hủy session.

Spring Security Servlet có hỗ trợ `oidcLogout().backChannel(...)` và endpoint mặc định dạng `/logout/connect/back-channel/{registrationId}` khi được cấu hình. Phải kết nối provider metadata/callback URL, session mapping và handler đúng phiên bản framework.

**Lưu ý quan trọng trong ứng dụng nhiều node:** session mapping OIDC mà node A giữ cục bộ có thể không tồn tại trên node B. Với Spring Session và nhiều pod, hãy xét **OidcSessionRegistry** dùng chung, event lifecycle và cookie session. Tài liệu Spring Security lưu ý back-channel handler mặc định dùng tên cookie `JSESSIONID`, trong khi Spring Session thường dùng `SESSION`; khi phối hợp chúng cần cấu hình `setSessionCookieName("SESSION")` và kiểm thử toàn đường đi theo phiên bản đang dùng.

### 7.6. Front-Channel Logout khác Back-Channel như thế nào?

| Kỹ thuật | Kênh thực hiện | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **RP-Initiated Logout** | Browser redirect từ RP đến OP | Tự nhiên khi user nhấn logout ở RP | OP và các RP phải hỗ trợ để có hiệu quả liên bang |
| **Front-Channel Logout** | Thông báo logout qua browser, iframe/redirect | Có thể đồng bộ nhiều RP qua user agent | Bị ảnh hưởng cookie bên thứ ba, tracker blocking, CSP, browser không thực thi |
| **Back-Channel Logout** | OP gọi server RP trực tiếp | Không phụ thuộc iframe/browser đang mở | Cần endpoint bảo mật, xác minh Logout Token, session mapping, retry/event handling |

**Bản chất:** “Logout khỏi IdP” và “mọi ứng dụng đều hết session” là hai yêu cầu khác nhau. Khi IdP session bị hủy nhưng RP B không nhận/không xử lý notification, RP B có thể tiếp tục cho phép truy cập dựa vào local session còn hạn.

## 8. SAML 2.0 Single Logout (SLO)

Với **SAML 2.0**, khái niệm tương đương phối hợp đăng xuất giữa Service Provider (SP/RP) và Identity Provider (IdP) thường là **Single Logout**:

- **SP-initiated SLO:** ứng dụng gửi `saml2:LogoutRequest` có chữ ký phù hợp tới IdP, nhận `LogoutResponse`.
- **IdP-initiated SLO:** IdP gửi `LogoutRequest` đến ứng dụng, ứng dụng xác minh message và hủy local session.
- Metadata, chứng thư ký, binding, endpoint và name/session identifier phải được cấu hình tương thích với IdP.

Spring Security Servlet hỗ trợ `saml2Logout()` khi đã có `saml2Login()`, `RelyingPartyRegistration`, metadata, signing credentials và SLO endpoint phù hợp.

~~~java
// Minh họa: chỉ có tác dụng khi cấu hình SAML đầy đủ.
http
    .saml2Login(Customizer.withDefaults())
    .saml2Logout(Customizer.withDefaults());
~~~

Đây **không phải** logout OIDC: SAML và OIDC dùng giao thức, message, session identifier và validation khác nhau. Không tự viết một redirect đến IdP URL rồi coi đó là SAML SLO hợp lệ; message phải tuân thủ SAML, bao gồm chữ ký khi IdP yêu cầu.

Spring Security cũng cho phép **local logout riêng** và **SAML RP-initiated logout riêng**, ví dụ dùng `POST /logout` chỉ để xóa phiên local và một endpoint khác để khởi xướng SLO. Thiết kế UI cần giải thích rõ hai lựa chọn nếu sản phẩm có cả hai.

## 9. Ba kiểu “đăng xuất” thường được người dùng yêu cầu

### 9.1. “Đăng xuất khỏi ứng dụng này”

**Mục tiêu:** user không dùng được session của browser hiện tại ở ứng dụng A.

Các bước điển hình:

1. POST /logout với CSRF hợp lệ nếu browser dùng cookie.
2. LogoutFilter hủy local HttpSession/context, dọn remember-me nếu có.
3. Xóa cookie phiên/bộ nhớ client tương ứng.
4. Chuyển tới trang public; test gọi endpoint bảo vệ bằng cookie cũ thất bại.

**Không tuyên bố:** access token ở API đã bị revoke; SSO session ở IdP đã hết; các thiết bị khác đã bị logout.

### 9.2. “Đăng xuất mọi thiết bị của tài khoản này”

**Mục tiêu:** vô hiệu hóa **mọi phương thức truy cập hiện có do hệ thống quản lý** của user, không chỉ session hiện tại.

Thường cần:

- Liệt kê/hủy mọi HttpSession theo principal nếu ứng dụng stateful, dùng kho session chung/index phù hợp.
- Xóa persistent remember-me token của user.
- Revoke refresh token/token family và các access token có thể revoke từ issuer đang quản lý.
- Nếu dùng JWT offline, thiết kế security version/denylist hoặc chấp nhận độ trễ tới `exp` theo SLA.
- Nếu có API key/personal access token, quyết định có thu hồi cùng không.
- Nếu yêu cầu bao trùm SSO ngoài, phối hợp IdP và RPs; không thể tự hủy session ở một domain/issuer khác nếu không có giao thức/quyền được hỗ trợ.
- Ghi audit và thông báo tới user, không để log chứa token/cookie.

**Không có một lệnh Spring Security chung mặc định** đảm bảo tất cả tác vụ trên.

### 9.3. “Đăng xuất khỏi tài khoản SSO / hệ thống danh tính”

**Mục tiêu:** đóng phiên tại IdP, ngăn browser tự nhận diện qua SSO session cũ và nếu được hỗ trợ thì phối hợp logout RPs.

Cách thường dùng:

- OIDC RP-Initiated Logout chuyển user agent tới `end_session_endpoint`.
- OIDC Back-Channel Logout xử lý yêu cầu do OP gửi tới RP.
- SAML Single Logout theo cấu hình SP/IdP.
- Các provider không hỗ trợ chuẩn có thể cung cấp API logout riêng. Phải đọc tài liệu provider, không đoán endpoint hoặc scope.

**Giới hạn:** ngay cả khi IdP session đã kết thúc, một access JWT đã được cấp và đang hợp lệ có thể vẫn truy cập API cho đến hết hạn nếu API không có cơ chế revoke. Một RP khác không tham gia SLO cũng có thể còn local session.

## 10. Quy tắc orchestration và thứ tự các bước

Với một UI cung cấp “Đăng xuất khỏi ứng dụng” và “Đăng xuất khỏi mọi nơi”, nên mô hình hóa **yêu cầu + kết quả từng hệ thống**, thay vì chỉ gọi một endpoint rồi luôn trả success.

Ví dụ workflow tổng quát:

~~~text
User chọn loại logout
        |
        +--> Local-only
        |      |
        |      +--> local LogoutFilter / cookie cleanup
        |      +--> trả kết quả local
        |
        +--> Global / security-sensitive logout
               |
               +--> xác minh user và quyền thực hiện
               +--> revoke refresh/access tokens thuộc phạm vi
               +--> invalidate relevant local sessions/remember-me
               +--> yêu cầu OP/IdP logout theo giao thức hỗ trợ
               +--> theo dõi trạng thái/timeout/retry của bước ngoài
               +--> chỉ tuyên bố các phạm vi THỰC SỰ đã hoàn tất
~~~

### 10.1. Không có transaction nguyên tử giữa các hệ thống

Một database transaction tại ứng dụng A **không thể** bao trùm đồng thời việc IdP hủy cookie SSO, Authorization Server revoke refresh token và Resource Server từ chối mọi JWT offline.

Do đó:

- Định nghĩa **hành động tối thiểu bắt buộc**, thứ tự ưu tiên theo an toàn bảo mật và thông báo UX.
- Xử lý lỗi từng bước: token revocation timeout có thể để lại cửa sổ token vẫn hợp lệ.
- Sử dụng retry có giới hạn, idempotency và audit để tránh “success giả”.
- Khi user mất thiết bị hoặc có nghi ngờ compromise, ưu tiên chặn credential có thể tái sử dụng trên server/issuer; chỉ xóa cookie trên thiết bị đang dùng là không đủ.
- Không cất token plaintext trong queue/log để retry; nếu cần, dùng storage mã hóa, TTL và quy trình bảo mật.
- Không gọi logout URL ngoài bằng JavaScript lấy trực tiếp một URL do user gửi mà không validate để tránh open redirect/SSRF.

### 10.2. Xóa token local không đồng nghĩa revoke tại issuer

Với `OAuth2AuthorizedClientService`:

~~~java
// Ví dụ minh họa, sau khi đã thực hiện chính sách revoke ở issuer:
authorizedClientService.removeAuthorizedClient(
    registrationId, principalName
);
~~~

Thao tác này xóa thông tin Authorized Client phía app, **không gọi RFC 7009**. Để thu hồi, cần gửi request tới revocation endpoint với client authentication phù hợp. Trong hệ thống có nhiều client grants, xác định rõ phải revoke token nào và có cần toàn bộ token family không.

### 10.3. Đừng đánh đồng OIDC login với OAuth access token

Một website dùng `oauth2Login()` có thể có:

- Local HttpSession (Spring Security đã lưu Authentication).
- ID token để hiểu identity.
- Access token để gọi UserInfo/resource API.
- Refresh token (nếu được cấp và client lưu).
- SSO cookie tại OpenID Provider.

Một nút logout có thể tác động tới **một, hai hoặc nhiều** thành phần trên. Cần viết rõ chính sách của sản phẩm và test từng thành phần, thay vì nghĩ `logout()` luôn thu hồi mọi token do IdP cấp.

## 11. Ma trận kiểm thử ba lớp

| Kịch bản | Kiểm tra local session | Kiểm tra token | Kiểm tra IdP/SSO |
| --- | --- | --- | --- |
| Chỉ local logout tại A | Cookie cũ không được dùng lại để khôi phục A | Không mặc nhiên revoke | OP session có thể còn |
| Local logout rồi login lại qua OIDC | A không còn session cũ | Không kết luận chỉ từ redirect | Nếu OP SSO còn, có thể login lại không cần password |
| Revoke refresh token | Local session có thể còn | Không xin access token mới bằng refresh token đó | OP SSO có thể còn |
| Revoke opaque access token | Local session có thể còn | Introspection có thể chuyển inactive sau propagation | Không mặc nhiên ảnh hưởng |
| Revoke refresh token khi JWT access còn sống | Local session độc lập | JWT có thể còn hợp lệ tới exp nếu offline validation | OP session độc lập |
| RP-Initiated OIDC logout | A có thể cleanup local theo thiết kế | Không mặc nhiên revoke mọi OAuth token | OP thực hiện logout theo policy |
| OP gửi back-channel logout | RP hủy session khớp sid/sub sau validate | Không mặc nhiên revoke access token | OP session đã kết thúc/đang xử lý |
| SAML SLO thành công | SP xử lý session theo message | Không thay thế OAuth revocation | IdP/SP phối hợp theo SLO |
| Logout all devices theo yêu cầu bảo mật | Mọi local session đã được hủy theo user | Tokens đã revoke theo phạm vi | Chỉ khi IdP hỗ trợ và đã phối hợp |
| Mất kết nối IdP khi logout | A có thể đã logout local | Trạng thái token có thể chưa rõ | Không tuyên bố OP đã logout |

### 11.1. Test local với MockMvc

Với Spring Security Test, kiểm tra:

- Không có CSRF token thì `POST /logout` bị từ chối theo cấu hình browser/cookie.
- Login thành công có session; `POST /logout` hợp lệ xóa Authentication.
- Request tiếp theo chỉ mang session cookie cũ bị redirect/401 theo entry point.
- Remember-me được cleanup theo loại dịch vụ cấu hình.

Ví dụ test theo chủ đích, cần test context đã cấu hình:

~~~java
// Mã minh họa trong test có MockMvc và csrf().
mockMvc.perform(post("/logout").with(csrf()))
       .andExpect(status().isNoContent());
~~~

Nếu chưa có Authentication, handler vẫn có thể trả status; vì vậy **chỉ kiểm tra 204 không chứng minh session thật đã bị hủy**. Test phải tạo session authenticated trước và kiểm tra request sau.

### 11.2. Test token revocation

Dùng Authorization Server kiểm thử hỗ trợ RFC 7009:

1. Phát hành access/refresh token cho client.
2. Gọi API được bảo vệ thành công bằng access token.
3. Revoke refresh token.
4. Dùng refresh token cũ xin access token mới: **thất bại**.
5. Kiểm tra access token cũ tại Resource Server theo chính sách thực: có thể tiếp tục hợp lệ tới exp nếu là JWT offline.
6. Nếu yêu cầu near-real-time revocation, đo độ trễ từ revoke tới bị từ chối thay vì tuyên bố “ngay lập tức”.
7. Lặp lại revoke một token đã invalid: response 200 có thể vẫn đúng giao thức.

### 11.3. Test OIDC logout liên bang

Với hai Relying Party A/B và một OP test:

1. Đăng nhập vào A và B bằng cùng OP; tạo session ở cả hai.
2. Logout **chỉ local A**, xác nhận B vẫn hoạt động và OP SSO có thể còn.
3. Khởi xướng RP-Initiated Logout từ A, xác minh browser được redirect đến **end_session_endpoint** đúng; `post_logout_redirect_uri` đúng URI đã đăng ký.
4. Xác minh OP session đã kết thúc theo chính sách; lần login OIDC mới đòi xác thực hoặc nhận kết quả phù hợp.
5. Nếu OP hỗ trợ back-channel, kiểm tra B nhận và xác minh **Logout Token**, rồi hủy session theo sid/sub.
6. Thử Logout Token sai signature, issuer/audience, expired/replay: **không được hủy session**.
7. Thử trong môi trường nhiều pod: session mapping, cookie name, registry và shared store còn nhất quán không.

**Một HTTP 302 tới IdP không chứng minh IdP đã logout thành công.** Cần kiểm tra toàn luồng và trạng thái SSO.

### 11.4. Test SAML Single Logout

Dùng SAML IdP/RP test với metadata, signing credentials và endpoint SLO phù hợp:

- SP phát `LogoutRequest` hợp lệ, IdP trả `LogoutResponse` hợp lệ và local session được kết thúc.
- IdP-initiated SLO thực sự được SP xác minh và xử lý.
- Message sai signature/issuer/destination bị từ chối.
- Không tuyên bố logout mọi RP nếu một RP không hỗ trợ hay không nhận được SLO.

## 12. Những lỗi phổ biến và cách sửa

### 12.1. “Đã xóa JSESSIONID, vậy JWT chắc chắn không còn hiệu lực”

**Sai.** JWT access token là credential riêng. API kiểm tra chữ ký/exp offline có thể vẫn chấp nhận JWT cho tới hết hạn. Cần revoke/denylist/introspection hoặc thiết kế token TTL phù hợp.

### 12.2. “Gọi RFC 7009 thành công thì mọi phiên OIDC đã logout”

**Sai.** Revocation xử lý token/grant theo server policy; IdP browser SSO session là trạng thái khác. Cần cơ chế OIDC logout thích hợp nếu muốn đóng phiên tại OP.

### 12.3. “Đăng xuất khỏi IdP rồi thì mọi ứng dụng khác bị logout tức thời”

**Không được bảo đảm.** Các RP phải nhận và xử lý SLO notification, hoặc yêu cầu xác thực lại theo chính sách; browser front-channel có thể bị chặn, back-channel có thể thất bại, một RP có thể giữ local session riêng.

### 12.4. “Xóa OAuth2AuthorizedClientService là đã revoke token ở provider”

**Sai.** Thao tác đó dọn kho token local của client. Cần một request revocation riêng hoặc API provider tương ứng.

### 12.5. “Có thể dùng GET /logout cho tiện”

**Không khuyến nghị cho ứng dụng browser có cookie.** Dùng POST và CSRF để tránh logout do trang ngoài/prefetch kích hoạt. GET có thể là trang xác nhận logout mặc định khi CSRF được bật.

### 12.6. “Phải tự viết controller /logout và clearContext”

**Không cần thiết ở đường chuẩn.** Dùng LogoutFilter và LogoutHandler/LogoutSuccessHandler do Spring Security cung cấp. `clearContext()` một mình không hủy HttpSession/remember-me/repository.

### 12.7. “Logout success redirect cho phép URL tuỳ ý từ người dùng”

**Rủi ro open redirect.** Khi cấu hình `post_logout_redirect_uri`, dùng URI đã đăng ký/allowlist. Không lấy một `next` parameter chưa kiểm tra để điều hướng sang domain bất kỳ.

### 12.8. “Logout Token từ OP chỉ cần có sub hợp lệ”

**Sai.** Back-channel Logout Token phải được xác minh chữ ký, issuer, audience, claims, sự kiện logout, thời gian, replay và sid/sub theo đặc tả. Không chấp nhận request JSON tự khai username để xóa phiên.

### 12.9. “JWT access token có thể revoke ngay ở mọi Resource Server mà không cần cơ chế bổ sung”

**Không đúng khi validator hoàn toàn offline.** Cần denylist, security epoch, token version, introspection/cache hoặc lifetime ngắn để đáp ứng yêu cầu gần thời gian thực.

### 12.10. “Với nhiều pod, registry session SSO cục bộ là đủ”

**Không bảo đảm.** OP logout notification có thể tới pod khác; cần chia sẻ thông tin phiên/sid/sub và repository theo yêu cầu của cơ chế logout. Với Spring Session cookie `SESSION`, kiểm tra tương thích với OIDC back-channel handler mong `JSESSIONID` theo mặc định.

### 12.11. “Trả HTTP 200 từ revocation chứng minh token trước đó tồn tại”

**Sai.** RFC 7009 chủ đích trả 200 cả cho token không hợp lệ/không tìm thấy nhằm tránh token fishing.

### 12.12. “Logout tất cả thiết bị chỉ cần xóa cookie thiết bị hiện tại”

**Sai.** Không thể xóa cookie ở một browser khác bằng response cho browser hiện tại. Phải thu hồi session/token **phía server** hoặc dựa vào protocol hỗ trợ trên từng issuer/RP.

## 13. Checklist thiết kế logout cho hệ thống thật

Trước khi chốt yêu cầu sản phẩm, trả lời các câu hỏi:

- Người dùng muốn **local**, **revoke token**, **SSO**, hay **all devices**? UI có giải thích scope?
- Hệ thống đang dùng **HttpSession**, remember-me, OAuth access/refresh token, ID token, SAML session, API key hay phối hợp nhiều kiểu?
- Ai sở hữu trạng thái cần thu hồi: app, resource server, authorization server, IdP hay bên thứ ba?
- Với refresh token, có quyền gọi **RFC 7009** không? Token family/rotation policy ra sao?
- Với access token JWT, thời hạn sống tối đa và độ trễ revoke cho phép là bao lâu?
- Có yêu cầu invalidate **mọi HttpSession** của cùng user trên các node khác không? Có shared session registry/index không?
- OIDC OP hỗ trợ **end_session_endpoint**, back-channel/front-channel không? Redirect URI đã đăng ký chưa?
- Nếu dùng Spring Session, cookie tên gì và OIDC logout session mapping có tương thích/được chia sẻ qua cluster không?
- SAML IdP có hỗ trợ SLO, metadata, signing và endpoint khớp không?
- Khi IdP/revocation endpoint lỗi hoặc timeout, UI báo gì? Có retry/audit và trạng thái **chưa hoàn tất** không?
- Cookie, token, client secret và Logout Token có được bảo vệ khi truyền/lưu/log không?
- Test đã chứng minh **kết quả mong muốn của từng hệ thống**, hay chỉ assert HTTP 204/302?

**Nguyên tắc tổng kết:** đừng trả lời “đã đăng xuất khỏi mọi nơi” chỉ vì ứng dụng đã xóa SecurityContext. Một luồng logout đúng phải xác định **phạm vi thu hồi**, **chủ sở hữu trạng thái** và **bằng chứng đã hoàn tất** trên từng hệ thống liên quan.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** User logout tại ứng dụng A bằng `POST /logout`, rồi click login và được IdP cho vào ngay. Đã xảy ra điều gì?

**Trả lời:** A đã local logout nhưng SSO session tại IdP có thể vẫn còn. Cần OIDC RP-Initiated Logout hoặc cơ chế IdP phù hợp nếu muốn đóng phiên SSO.

**Câu 2.** Backend revoke refresh token thành công; một JWT access token chưa hết hạn vẫn gọi được API. Có chắc đó là lỗi revocation?

**Trả lời:** Không. Resource Server xác minh JWT offline có thể tiếp tục chấp nhận cho tới `exp` nếu không có kiểm tra denylist/revocation bổ sung.

**Câu 3.** `OAuth2AuthorizedClientService.removeAuthorizedClient(...)` có gửi RFC 7009 request không?

**Trả lời:** Không. Nó xóa authorized-client record ở ứng dụng. Phải gọi revocation endpoint riêng nếu cần issuer thu hồi token.

**Câu 4.** HTTP 200 từ revoke endpoint chứng minh token còn hoạt động trước khi gọi không?

**Trả lời:** Không. RFC 7009 trả 200 cả khi token không hợp lệ/không tồn tại.

**Câu 5.** Khi RP A logout local, RP B có tự logout không?

**Trả lời:** Không mặc định. B giữ session riêng; chỉ khi có SLO hoặc chính sách/notification phù hợp mới có thể hủy session B.

**Câu 6.** Trong OIDC, ID token có phải access token để revoke hoặc thay cho `Logout Token` không?

**Trả lời:** Không. ID token xác nhận đăng nhập, access token cấp quyền gọi API, Logout Token có hợp đồng claims riêng cho back-channel logout.

**Câu 7.** Vì sao backend cần xác minh `iss`, `aud`, signature và `sid/sub` của Logout Token?

**Trả lời:** Vì đây là yêu cầu hủy phiên có tác động bảo mật; chỉ tin payload tự khai sẽ cho phép giả mạo lệnh logout hoặc hủy nhầm phiên.

**Câu 8.** App dùng Spring Session cookie `SESSION` với OIDC back-channel handler giả định `JSESSIONID`. Cần làm gì?

**Trả lời:** Cấu hình handler/session mapping khớp tên cookie và kiểm thử thực tế theo phiên bản Spring Security đang dùng, đặc biệt khi có nhiều pod.

**Câu 9.** Để “logout tất cả thiết bị”, chỉ revoke refresh token có đủ không?

**Trả lời:** Chưa chắc. Cần invalidation các local HttpSession, remember-me tokens, access tokens theo mô hình thực và có thể cả SSO session tại IdP nếu yêu cầu bao trùm.

**Câu 10.** Khi token revocation hoặc IdP logout timeout nhưng local session đã bị hủy, nên báo gì?

**Trả lời:** Có thể xác nhận phạm vi **đăng xuất cục bộ** đã hoàn tất, đồng thời cho biết bước thu hồi/token/SSO chưa được xác nhận; không báo mọi nơi đã logout khi chưa có bằng chứng.

## Tài liệu chính thức

- [Spring Security 6.5 — Handling Logouts (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security — OIDC Logout for Servlet](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html)
- [Spring Security 6.5 — OidcClientInitiatedLogoutSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/oidc/web/logout/OidcClientInitiatedLogoutSuccessHandler.html)
- [Spring Security 6.5 — SAML 2.0 Single Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html)
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0-final.html)
