# Phân biệt bảo mật bằng phiên, HTTP Basic và Bearer token trong Spring Security Servlet

## Mục tiêu và bối cảnh

Sau bài học, bạn có thể: giải thích browser/client gửi bằng chứng xác thực bằng cách nào; phân biệt trạng thái phía server, chu kỳ sống và cơ chế thu hồi của ba phương án; hiểu CSRF/XSS liên quan ra sao; và lựa chọn cấu hình Spring Security cho website hoặc API Servlet.

HTTP không tự nhớ rằng hai request do cùng một người gửi. Sau lần xác thực đầu tiên, client cần mang một bằng chứng tới các request được bảo vệ. Ba lựa chọn thường gặp là **session ID trong cookie**, **username/password trong HTTP Basic** và **access token trong Bearer header**. Cả ba cần HTTPS khi triển khai thực tế.

**Authentication** trả lời “ai đang gọi?”; **authorization** trả lời “người này có quyền thực hiện thao tác đó không?”. Trong Spring Security Servlet, Authentication chứa principal và authority của request; SecurityContextHolder giúp code trong request truy cập Authentication. SecurityContext có được duy trì qua các request hay không tùy cách lưu/khôi phục context và session policy. Xác thực thành công không có nghĩa là được phép vào mọi endpoint.

**Cookie không đồng nghĩa session**: cookie là cơ chế browser lưu và tự đính kèm một giá trị. **Bearer không đồng nghĩa JWT**: Bearer là cách trình một token trong request; token có thể là JWT hoặc opaque string.

## 1. Bảo mật bằng phiên (session-based)

### Luồng từ đăng nhập đến đăng xuất

1. Browser mở form đăng nhập và POST tên đăng nhập, mật khẩu cùng CSRF token qua HTTPS.
2. Spring Security kiểm tra tài khoản qua AuthenticationProvider. Khi xác thực thành công, luồng form login lưu SecurityContext tương ứng vào HttpSession theo cơ chế đã cấu hình.
3. Server gửi cho browser mã định danh phiên, thường trong cookie JSESSIONID. Browser tự gắn cookie đó vào request tiếp theo nếu domain/path/thuộc tính cookie cho phép.
4. Server tra session ID, tìm phiên còn hợp lệ và khôi phục Authentication để kiểm tra quyền. Browser **không phải gửi lại mật khẩu** trong từng request.
5. Đăng xuất hợp lệ có thể xóa SecurityContext, vô hiệu hóa HttpSession; session cũng có thể hết hạn theo idle timeout hoặc chính sách ứng dụng.

Thông điệp minh họa:

~~~http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=<temporary-id>

username=alice&password=<password>&_csrf=<csrf-token>

HTTP/1.1 302 Found
Set-Cookie: JSESSIONID=<new-id>; Path=/; HttpOnly; Secure; SameSite=Lax
Location: /
~~~

Đây chỉ là ví dụ luồng, **không phải output cố định**: Set-Cookie/SameSite, có cookie trước login hay không, URL chuyển hướng và cách cấp session ID phụ thuộc phiên bản/cấu hình, reverse proxy và ứng dụng. Spring Security có cơ chế bảo vệ **session fixation**, thường thay ID sau đăng nhập thành công; không để client ấn định session ID xác thực.

### Ưu điểm, giới hạn và bảo vệ

Bảo mật bằng phiên thuận tiện với website render HTML, đăng nhập qua form hoặc kiến trúc backend-for-frontend (BFF). Server có thể vô hiệu session ngay, kiểm soát thời gian không hoạt động và đăng xuất ở cấp server. Khi chạy nhiều instance, phải có chiến lược session store dùng chung (ví dụ Spring Session với kho tập trung) hoặc cơ chế routing phù hợp.

Nếu kẻ tấn công lấy được session ID còn hiệu lực, họ có thể chiếm phiên. Cần HTTPS; cookie **Secure**, **HttpOnly**, **SameSite** phù hợp; scope Domain/Path tối thiểu; timeout và logout rõ ràng. HttpOnly giảm việc JavaScript đọc trực tiếp cookie, nhưng không ngăn script độc hại gửi request thay người dùng. SameSite là phòng vệ bổ sung, không mặc nhiên thay thế CSRF token.

**CSRF đặc biệt quan trọng với phiên dùng cookie**: browser tự thêm cookie khi người dùng truy cập URL phù hợp, kể cả request phát sinh từ trang khác trong một số tình huống. Các thao tác đổi trạng thái cần CSRF protection hoặc biện pháp thay thế được thiết kế đúng; Spring Security mặc định bật CSRF khi cấu hình Servlet security thông thường.

## 2. HTTP Basic Authentication

HTTP Basic yêu cầu client gửi header Authorization trên request cần xác thực:

~~~http
GET /api/profile HTTP/1.1
Authorization: Basic <Base64(username:password)>
~~~

Giá trị Basic là Base64 của username:password. **Base64 là biểu diễn, không phải mã hóa bí mật**; chỉ cần giải Base64 là thấy credential. Vì thế Basic phải đi trên HTTPS, hạn chế quyền tài khoản, không log header, không đưa mật khẩu thật vào URL/script/ticket.

Trong Spring Security, **BasicAuthenticationFilter** nhận header, xác thực qua AuthenticationManager/Provider và thiết lập Authentication cho request. Với SessionCreationPolicy.STATELESS, Spring Security không dùng HttpSession để lưu/lấy SecurityContext; mỗi request phải tự mang header Basic. Việc xác thực vẫn có thể cần tra cứu user hoặc password hash.

HTTP Basic **không tự động luôn stateless** trong mọi cấu hình. Session policy và SecurityContextRepository quyết định ứng dụng có sử dụng phiên hay không; muốn API độc lập phiên, cần đặt chính sách rõ ràng.

Ưu điểm là đơn giản và tương thích curl, công cụ HTTP, script nội bộ. Nhược điểm là credential gốc bị gửi đi thường xuyên, khó thu hồi riêng một thiết bị hoặc một client nếu nhiều nơi dùng chung một mật khẩu. Browser có thể cache và tự gửi lại Basic credential, nên trải nghiệm logout kém và **không thể coi Basic qua browser mặc nhiên miễn nhiễm CSRF**.

Thiếu/sai credential ở API Basic thường dẫn đến **401 Unauthorized** cùng header WWW-Authenticate: Basic realm="...". Khi user đã được xác thực nhưng thiếu quyền, response thường là **403 Forbidden**.

## 3. Bearer token Authentication

Client nhận access token thông qua authorization server hoặc identity provider bằng flow phù hợp, chẳng hạn OAuth 2.0 Authorization Code + PKCE cho ứng dụng người dùng, hoặc Client Credentials cho backend. Client gửi token tới resource server:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <access-token>
~~~

**Bearer** nghĩa là người nào cầm token hợp lệ thường có thể sử dụng nó. Bản thân Bearer không ràng buộc token với một người gửi, máy hoặc kết nối cụ thể. Do đó phải bảo vệ token khỏi rò rỉ/phát lại và giảm phạm vi quyền, thời hạn; hệ thống cần chống phát lại mạnh hơn có thể cân nhắc cơ chế token ràng buộc người gửi.

Hai loại access token thường gặp:

- **Opaque token**: chuỗi do issuer phát hành, API không giải cấu trúc để tự suy đoán quyền. Resource server thường dùng token introspection hoặc kho trạng thái đáng tin để xác nhận token còn hiệu lực và scope.
- **JWT access token**: các claim được đóng gói trong token, thường gồm ba phần Base64URL. API có thể xác minh chữ ký và kiểm tra exp, nbf, iss, audience phù hợp, phạm vi quyền và chính sách trust. **Giải mã payload JWT không phải xác minh chữ ký**. JWT ký thường không mã hóa nội dung nên không đặt bí mật trong claim.

Spring Security OAuth2 Resource Server đọc Bearer token bằng **BearerTokenAuthenticationFilter**, dùng JwtDecoder/validator hoặc opaque-token introspector. Khi xác thực thành công, hệ thống đưa principal/authority vào SecurityContext; sau đó quy tắc authorizeHttpRequests vẫn quyết định quyền truy cập. Với JWT Resource Server, scope thường ánh xạ thành authority dạng SCOPE_orders.read nếu token có scope orders.read.

### Thời hạn, thu hồi và lưu trữ

Access token nên có hạn ngắn, audience đúng API và scope tối thiểu. **JWT tự xác minh** giúp resource server tránh introspection mỗi request, nhưng token bị lộ có thể tiếp tục được chấp nhận tới lúc hết hạn nếu không có cơ chế thu hồi bổ sung. **Opaque token** thuận tiện cho kiểm soát/truy vấn trạng thái tập trung, đổi lại thêm sự phụ thuộc và latency. JWT cần chiến lược hạn ngắn, denylist/introspection bổ sung nếu cần thu hồi tức thì.

Refresh token (nếu được cấp) dùng để xin access token mới tại token endpoint, **không gửi thay access token vào API tài nguyên**; bảo vệ và xoay vòng refresh token theo thiết kế của issuer. Đăng xuất bằng cách xóa token ở client **không mặc nhiên thu hồi JWT trên server**.

Đối với browser, token bị XSS lấy được có thể bị dùng lại. Tránh coi lưu access token dài hạn trong localStorage là giải pháp an toàn mặc định. BFF có thể giữ token phía server và cho browser dùng session cookie đã bảo vệ. Nếu đặt Bearer token vào cookie để browser tự gửi, phải đánh giá CSRF giống các credential tự gửi khác. Dùng Authorization header do code chủ động thêm thường giảm bề mặt CSRF kiểu cookie, nhưng không loại bỏ XSS và không thay thế HTTPS.

## 4. Bảng so sánh

| Tiêu chí | Session | HTTP Basic | Bearer token |
| --- | --- | --- | --- |
| Bằng chứng gửi lên | Session ID, thường qua Cookie | Authorization: Basic ... | Authorization: Bearer ... |
| Mật khẩu mỗi request | Không; thường chỉ lúc login | Có, dưới dạng Base64 username:password | Không; gửi access token |
| Trạng thái xác thực trên server | Thường cần HttpSession/store | Không cần session nếu đặt STATELESS, nhưng vẫn cần kiểm tra credential | JWT thường tự xác minh; opaque thường cần introspection/store |
| Hết hạn | Session timeout/chính sách ứng dụng | Tùy mật khẩu/chính sách credential | Token lifetime/exp và chính sách issuer |
| Thu hồi/đăng xuất | Vô hiệu session tương đối trực tiếp | Khó đăng xuất riêng một browser/client đã cache credential | Phụ thuộc loại token, hạn ngắn và chiến lược revocation |
| CSRF | Cần xét vì browser tự gửi cookie | Cần xét nếu browser tự gửi Basic | Header được thêm chủ động ít gặp CSRF kiểu cookie; token trong cookie có nguy cơ CSRF |
| Rủi ro đặc trưng | Session hijacking, fixation, CSRF | Lộ mật khẩu, credential dùng lại, browser cache | Token theft/replay, scope quá rộng, xác minh JWT sai |
| Trường hợp thường dùng | Browser website, BFF | Công cụ/script đơn giản qua HTTPS | API, mobile, OAuth2 và service-to-service |

Cả ba đều có thể bị phát lại khi credential bị đánh cắp. HTTPS ngăn nghe lén trên đường truyền đúng cấu hình; nó không bảo vệ khỏi log nhầm, XSS, extension độc hại hoặc máy client bị xâm nhập.

## 5. Ví dụ Spring Boot 3.x / Spring Security 6 Servlet

Các ví dụ dùng **Java 17+**, Spring MVC Servlet, spring-boot-starter-web và spring-boot-starter-security. JWT Resource Server cần thêm spring-boot-starter-oauth2-resource-server. Các lớp cấu hình dưới đây là **phương án thay thế** trong một ứng dụng: chọn một phương án khi học, hoặc nếu muốn cùng tồn tại phải dùng các SecurityFilterChain với securityMatcher và @Order cụ thể.

Đặt lớp Java dưới package mà @SpringBootApplication quét được, ví dụ example.security. Đây là đoạn cấu hình của dự án Spring Boot có dependency cần thiết; không phải file Java độc lập chạy bằng lệnh javac không có thư viện.

### 5.1. Session + formLogin

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class SessionSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(withDefaults())
                .logout(withDefaults())
                .build();
    }
}
~~~

Với formLogin mặc định, browser chưa đăng nhập vào endpoint bảo vệ thường bị chuyển đến /login. Sau khi đăng nhập hợp lệ, browser giữ cookie phiên. CSRF protection vẫn bật; gửi POST /logout cần CSRF token hợp lệ khi cấu hình theo mặc định. Trên production phải đặt HTTPS và cookie security flags đúng với mạng/proxy, kiểm soát session expiry và quản lý user thực tế.

### 5.2. HTTP Basic không dùng HttpSession

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class BasicSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(withDefaults())
                .build();
    }
}
~~~

Ở đây STATELESS yêu cầu Spring Security không dựa vào HttpSession để duy trì SecurityContext. **Ví dụ vẫn giữ CSRF bật theo mặc định**; các request thay đổi trạng thái như POST không kèm CSRF token có thể bị 403. Chỉ quyết định tắt CSRF sau khi kiểm tra rõ hệ thống không nhận bất kỳ credential nào browser tự đính kèm (đặc biệt phải cẩn thận với browser cache Basic).

### 5.3. Bearer JWT Resource Server

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class BearerSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
                .build();
    }
}
~~~

Chỉ tắt CSRF như trên khi đây là API nhận Bearer token qua Authorization header, **không** dùng cookie/Basic browser tự gửi credential. Dùng JWT Resource Server cần identity provider phát hành JWT được tin cậy; API này không tự cấp JWT.

Tệp application.yml, thay issuer-uri bằng issuer thực:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
~~~

Thêm dependency vào Gradle ứng dụng nếu chưa có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

JWT decoder xác minh token dựa trên issuer và khóa thích hợp, đồng thời kiểm tra các validator cấu hình. Nếu API yêu cầu audience cụ thể, cần cấu hình audience validation tương ứng; chỉ có issuer-uri không đảm bảo mọi chính sách audience tùy ứng dụng. Trong ví dụ này, GET /api/** cần authority SCOPE_orders.read. Token thiếu, hết hạn hoặc không hợp lệ thường gây 401; token đã xác thực nhưng thiếu authority gây 403. Với opaque token, cấu hình introspection thay cho jwt(...).

### 5.4. User demo và endpoint để quan sát Basic/form login

Chỉ cho môi trường học thử cục bộ, có thể thêm user với PasswordEncoder thực sự thay vì dùng plaintext password trong cấu hình lưu trữ:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class DemoUsersConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("learner")
                        .password(encoder.encode("local-example-only"))
                        .roles("USER")
                        .build());
    }
}
~~~

Tạo controller trong package example.web (nằm dưới package example của @SpringBootApplication):

~~~java
package example.web;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/api/hello")
    public String hello(Principal principal) {
        return "Xin chào " + principal.getName();
    }
}
~~~

Khi chạy ứng dụng Boot với **BasicSecurityConfig**, **DemoUsersConfig**, **HelloController** và URL HTTP localhost cho mục đích học cục bộ, lệnh sau gửi Basic header:

~~~bash
curl -i -u learner:local-example-only http://localhost:8080/api/hello
~~~

Nếu server và cấu hình như trên hoạt động, response body chính xác là **Xin chào learner** (không có newline do controller). Không dùng HTTP không mã hóa trên mạng thật; thay bằng HTTPS và không để credential sản xuất trong command history. Bỏ -u hoặc dùng sai mật khẩu sẽ thường nhận HTTP 401. Khi đổi sang **SessionSecurityConfig** thay Basic, mở /api/hello bằng browser chưa xác thực sẽ thường redirect /login; đăng nhập rồi tải lại để quan sát browser gửi cookie JSESSIONID. User demo này không giúp JWT Resource Server cấp token.

## 6. Debug request đúng cách

Khi xem DevTools Network, log HTTP hoặc curl, hãy quan sát **sự có mặt của header** và status code nhưng che toàn bộ password, token và session ID trước khi chia sẻ.

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Browser chưa login gọi URL bảo vệ bị 302 | Form login AuthenticationEntryPoint chuyển tới /login | Kiểm tra chain, entry point và luồng redirect |
| API Basic thiếu/sai username/password bị 401 | Authentication thất bại | Kiểm tra Basic header, PasswordEncoder, nguồn user |
| JWT thiếu, hết hạn hoặc chữ ký sai bị 401 | Resource Server không xác thực được Bearer | Kiểm tra issuer, JWK, thời hạn, token type và clock skew |
| Đã login nhưng bị 403 | Thiếu authority/role hoặc bị CSRF protection chặn | Kiểm tra quyền, scope mapping, phương thức HTTP và CSRF token |
| Session user đột ngột trở thành anonymous | Cookie không được gửi, session hết hạn/không chia sẻ giữa instances | Kiểm tra Secure/SameSite/Path, proxy, TTL, session store |
| API dùng token đúng nhưng trả 401 | Có thể route trúng sai SecurityFilterChain hoặc validator không chấp nhận | Kiểm tra securityMatcher/@Order, JWT vs opaque và validation |

**HTTP 401** thường nghĩa là chưa có xác thực hợp lệ và có thể kèm WWW-Authenticate (Basic hoặc Bearer). **HTTP 403** thường nghĩa là request không đủ quyền hoặc bị chính sách CSRF từ chối. Với trang HTML form login, tình huống chưa xác thực thường nhận redirect 302 thay vì 401. Response cụ thể chịu ảnh hưởng bởi AuthenticationEntryPoint và exception handling.

Các filter đáng nhận biết trong Spring Security Servlet: UsernamePasswordAuthenticationFilter cho form login; BasicAuthenticationFilter cho Basic; BearerTokenAuthenticationFilter cho Bearer; AuthorizationFilter cho luật quyền. SecurityContextHolderFilter/SecurityContextRepository hỗ trợ khôi phục context theo cấu hình. Các filter không tự biến một request hợp lệ về credential thành request đủ quyền.

Khi một hệ thống có cả website dùng session ở /web/** và API dùng Bearer ở /api/**, cần tách SecurityFilterChain với securityMatcher và @Order rõ ràng; cân nhắc CSRF, session policy, entry point và quyền riêng cho mỗi nhóm endpoint. Đừng đặt mọi mechanism lên một chain rồi giả định client luôn nhận challenge mong muốn.

## 7. Chọn phương án và tránh lỗi phổ biến

**Website truyền thống hoặc BFF:** session cookie với CSRF protection, Secure/HttpOnly/SameSite, timeout và invalidation. Phù hợp khi server sở hữu trải nghiệm đăng nhập và có thể quản lý phiên.

**API mobile, SPA hoặc tích hợp OAuth2/OIDC:** Bearer access token giới hạn thời gian, scope và audience; Resource Server xác minh issuer/chữ ký/claims hoặc introspect opaque. Với browser, xem xét PKCE, cách giữ token, XSS và BFF thay cho localStorage dài hạn.

**Script nội bộ đơn giản:** Basic có thể phù hợp nếu bắt buộc HTTPS và quản lý bí mật cẩn thận; tránh chia sẻ một mật khẩu quyền rộng giữa nhiều client. Khi phát triển thêm phân quyền/vòng đời credential, cân nhắc token riêng cho từng client.

**Dịch vụ gọi dịch vụ:** Bearer token qua OAuth2 Client Credentials hoặc danh tính workload có hạn thường dễ giới hạn quyền và vòng đời hơn truyền mật khẩu người dùng.

Các nhận định sai cần sửa ngay:

1. “Basic có Base64 nên an toàn như mã hóa.” — Không; Base64 đảo ngược được.
2. “Bearer token luôn là JWT.” — Không; opaque cũng là Bearer.
3. “JWT có ba phần là chắc chắn hợp lệ.” — Không; phải xác minh chữ ký, nguồn phát hành, thời hạn, audience, scope và chính sách tin cậy.
4. “STATELESS nghĩa là toàn hệ thống không có state.” — Không; nó là chính sách HttpSession/SecurityContext trong Spring Security.
5. “Hễ là REST API thì nên tắt CSRF.” — Không; phải xét browser tự gửi credential nào.
6. “Authorization header sẽ loại trừ mọi CSRF.” — Không nếu hệ thống cũng chấp nhận cookie hoặc Basic cache; thiết kế client và CORS/CSRF phải được đánh giá.
7. “Xóa JWT trong browser là đã revoke token trên server.” — Không; JWT vẫn có thể còn hạn.
8. “Đã xác thực là có quyền truy cập mọi URL.” — Không; authorization kiểm tra quyền độc lập.

## Câu hỏi tự kiểm tra

1. Vì sao session ID thay thế việc gửi lại password mỗi lần, còn Basic vẫn gửi username:password trên request?
2. Vì sao Basic cached trong browser có thể có CSRF dù nó không dùng session cookie?
3. Nếu JWT đúng chữ ký nhưng sai audience hoặc hết hạn, API có nên chấp nhận?
4. Vì sao vô hiệu session phía server dễ hơn thu hồi ngay một JWT tự xác minh còn hạn?
5. Khi một ứng dụng Servlet cần cả form login ở /web/** và Bearer JWT ở /api/**, SecurityFilterChain, CSRF và SessionCreationPolicy phải được tổ chức ra sao?

Khi so sánh bất kỳ phương án nào, hãy luôn lần lượt xác định: **bằng chứng xác thực nằm ở đâu**, **server xác minh và duy trì bằng chứng đó thế nào**, và **quyền thực hiện thao tác được kiểm tra ra sao**.