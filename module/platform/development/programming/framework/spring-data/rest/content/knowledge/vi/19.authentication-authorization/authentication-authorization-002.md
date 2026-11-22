# Xác thực bằng session hoặc bearer token theo kiến trúc ứng dụng

Spring Data REST xuất repository thành HTTP API. Mọi request tới collection, item, search và association resource đều phải đi qua chính sách xác thực và phân quyền của ứng dụng. Spring Security hỗ trợ nhiều cách xác thực, trong đó hai mô hình phổ biến là **session cookie** và **bearer token**.

- **Session authentication** phù hợp với ứng dụng web đăng nhập tương tác. Server duy trì session, browser gửi cookie session trong các request tiếp theo.
- **Bearer token authentication** phù hợp với API client, mobile app hoặc service-to-service. Client chủ động gửi access token trong header Authorization.
- Có thể hỗ trợ cả hai trong một hệ thống, nhưng cần phân chia route và chính sách credential rõ ràng. CSRF protection phải phù hợp với cách browser gửi credential.

Xác thực xác định request thuộc về ai; phân quyền quyết định người đó được phép làm gì. CORS chỉ kiểm soát request cross-origin từ browser và khả năng đọc response. CORS không thay thế authentication hoặc authorization.

## 1. Request Spring Data REST đi qua Spring Security

Request đi qua Spring Security filter chain trước khi tới Spring Data REST dispatcher và repository. Luồng thông thường:

1. Browser hoặc API client gửi request tới resource, ví dụ GET /people.
2. Spring Security đọc credential từ session cookie hoặc header Authorization.
3. Authentication mechanism xác minh credential và tạo đối tượng Authentication.
4. Authorization rules kiểm tra request có được phép đi tiếp không.
5. Spring Data REST xử lý request và gọi repository.
6. Nếu bật method security, annotation trên repository hoặc service còn có thể kiểm tra quyền khi method được gọi.

Một repository được xuất thành REST resource không có nghĩa endpoint đó tự động công khai. Quyền truy cập phụ thuộc vào filter chain, method security và cấu hình ứng dụng.

Request chưa xác thực thường nhận 401 Unauthorized hoặc được chuyển tới trang login tùy kiểu ứng dụng. Người dùng đã xác thực nhưng không đủ quyền thường nhận 403 Forbidden.

## 2. Session authentication hoạt động như thế nào?

Session phù hợp khi browser là client chính và người dùng đăng nhập vào một ứng dụng web có trạng thái.

Sau khi đăng nhập thành công:

- Spring Security xác thực thông tin đăng nhập.
- Server lưu SecurityContext trong HTTP session.
- Browser nhận cookie định danh session, thường là JSESSIONID.
- Các request tiếp theo gửi cookie đó theo chính sách cookie của browser.
- Server tra session để khôi phục danh tính và quyền của người dùng.

Cookie session nên được cấu hình với Secure, HttpOnly và SameSite phù hợp với topology của ứng dụng. HttpOnly ngăn JavaScript đọc cookie; Secure giới hạn cookie trên HTTPS. SameSite cần được chọn theo cách frontend và API được triển khai, đặc biệt nếu chúng nằm ở các site khác nhau.

Ví dụ cấu hình filter chain cho ứng dụng web dùng form login:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            )
            .build();
    }
}
~~~

IF_REQUIRED cho phép Spring Security tạo session khi luồng xác thực cần. Với ứng dụng web truyền thống, đây thường là hành vi phù hợp. CSRF protection mặc định của Spring Security vẫn được bật; không tắt chỉ để làm cho POST, PUT, PATCH hoặc DELETE từ browser chạy được.

## 3. CSRF protection khi dùng session cookie

Browser tự động gửi cookie theo domain, path, SameSite và credential policy. Một trang web độc hại có thể cố khiến browser của người dùng đã đăng nhập gửi request thay đổi dữ liệu tới API. Đây là lý do ứng dụng dùng session cookie cần bảo vệ CSRF cho các request làm thay đổi trạng thái.

Với Spring Security:

- Giữ CSRF protection bật cho request dùng session cookie.
- Lấy CSRF token theo cơ chế mà ứng dụng cấu hình.
- Gửi token trong header hoặc parameter mà server mong đợi.
- Không coi SameSite là biện pháp thay thế hoàn toàn cho CSRF token.
- Không dùng GET để thực hiện thao tác thay đổi dữ liệu.

Một SPA có thể dùng CookieCsrfTokenRepository để browser nhận cookie chứa CSRF token và gửi lại token trong request header. Ví dụ cấu hình cơ bản:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieCsrfTokenRepository.withHttpOnlyFalse()
    )
);
~~~

Trong cấu hình này, cookie CSRF cần được JavaScript đọc để gửi token trong request header, nên cookie CSRF được đặt không HttpOnly. Cookie session vẫn nên HttpOnly. Hãy triển khai request handler cho SPA theo đúng phiên bản Spring Security đang dùng; từ Spring Security 6, cơ chế deferred token và BREACH protection có thể yêu cầu handler xử lý token riêng.

Các thao tác ghi của Spring Data REST như POST, PUT, PATCH và DELETE cần CSRF token khi request được xác thực bằng session cookie. Nếu thiếu token, Spring Security thường từ chối request trước khi repository được gọi.

## 4. Bearer token authentication hoạt động như thế nào?

Bearer token phù hợp khi client chủ động gửi access token cho từng request. Token thường được cấp bởi authorization server sau một luồng OAuth 2.0 hoặc OpenID Connect phù hợp.

Request có dạng:

~~~http
GET /people
Authorization: Bearer eyJ...
Accept: application/hal+json
~~~

Resource server xác minh token và xây dựng Authentication. Với JWT, việc xác minh thường gồm chữ ký, issuer, thời hạn và các claim cần thiết; hệ thống còn có thể kiểm tra audience và scope theo yêu cầu.

Bearer token không đáng tin chỉ vì nó có dạng chuỗi JWT. Server phải xác minh token bằng issuer, key và trust configuration phù hợp. Không nhận token từ query parameter hoặc URL; token chỉ nên được truyền qua header bảo mật.

## 5. Cấu hình Spring Security Resource Server cho JWT

Với Spring Boot, thêm resource server starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Cấu hình issuer URI để Spring Security khám phá metadata và khóa xác minh JWT từ authorization server:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://identity.example.com/issuer
~~~

Ví dụ filter chain cho API dùng bearer token:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(Customizer.withDefaults())
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
~~~

Chỉ tắt CSRF trong filter chain dành cho API stateless khi credential được gửi rõ ràng qua Authorization: Bearer và API không dùng cookie tự động để xác thực. Nếu cùng endpoint chấp nhận session cookie hoặc bearer token, không thể tùy tiện tắt CSRF cho request dùng cookie. Hãy tách route/filter chain hoặc thiết kế credential policy rõ ràng.

STATELESS yêu cầu Spring Security không tạo hoặc sử dụng HTTP session để lưu SecurityContext cho chain đó. Token được xác minh ở từng request. Đây là lựa chọn phù hợp cho API bearer stateless.

## 6. Phân biệt scope, role và authority

JWT có thể mang các claim như scope, scp, roles hoặc nhóm quyền tùy authorization server. Spring Security Resource Server thường ánh xạ OAuth scope thành authority có prefix SCOPE_.

Ví dụ token có scope people.read có thể được kiểm tra bằng:

~~~java
.requestMatchers(HttpMethod.GET, "/people/**")
.hasAuthority("SCOPE_people.read")
~~~

Method security cũng có thể kiểm tra authority:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.data.repository.CrudRepository;

@PreAuthorize("hasAuthority('SCOPE_people.write')")
public interface PersonRepository extends CrudRepository<Person, Long> {
}
~~~

Bật method security nếu dùng PreAuthorize:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Không giả định claim roles tự động được ánh xạ giống scope. Nếu authorization server phát role theo claim riêng, cấu hình JwtAuthenticationConverter hoặc converter phù hợp để ánh xạ claim thành GrantedAuthority. Sau đó kiểm tra đúng tên authority trong filter chain và method annotation.

Phân quyền ở URL và ở method có thể bổ sung cho nhau. URL rule quyết định request có được vào resource hay không; method rule bảo vệ thao tác repository/service kể cả khi method được gọi từ một luồng khác trong ứng dụng.

## 7. Hỗ trợ session và bearer trong cùng hệ thống

Một ứng dụng có thể có browser UI dùng session và API dành cho mobile/service dùng bearer. Cách rõ ràng là tách bề mặt API theo route, rồi dùng các SecurityFilterChain riêng với thứ tự ưu tiên.

Ví dụ kiến trúc:

| Route | Credential | Session policy | CSRF |
|---|---|---|---|
| /web/** | Session cookie | IF_REQUIRED | Bật |
| /api/** | Bearer JWT | STATELESS | Có thể tắt nếu không dùng cookie auth |
| /actuator/health | Public theo chính sách triển khai | Không phụ thuộc UI session | Theo cấu hình endpoint |

Một filter chain cho API có thể được giới hạn bằng securityMatcher("/api/**"); chain còn lại xử lý web route. Hãy bảo đảm Spring Data REST base path nằm đúng trong route matcher đã chọn.

Không nên tạo hai chain cùng bắt mọi request với thứ tự không rõ ràng. Spring Security chỉ dùng chain đầu tiên khớp request. Nếu matcher sai, request có thể rơi vào chain khác với authentication, CSRF hoặc session policy không mong muốn.

Nếu cùng một URI phải hỗ trợ cả cookie và bearer, cần thiết kế rõ cách phân biệt credential và vẫn bảo vệ CSRF cho cookie-authenticated request. Không nên đơn giản tắt CSRF trên toàn bộ API chỉ vì một số client gửi bearer token.

## 8. CORS khi frontend khác origin

Nếu browser frontend và Spring Data REST API khác origin, cấu hình CORS cho origin frontend được phép, method và header cần thiết.

Ví dụ:

~~~java
@Configuration
public class RestCorsConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        cors.addMapping("/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
            .allowedHeaders(
                "Authorization",
                "Content-Type",
                "X-XSRF-TOKEN",
                "If-Match",
                "If-None-Match"
            )
            .allowCredentials(true)
            .exposedHeaders("Location", "ETag", "Link");
    }
}
~~~

Điều chỉnh danh sách theo authentication mode:

- Session cookie cross-origin có thể cần allowCredentials(true) và cấu hình cookie SameSite/Secure phù hợp.
- Bearer token thường cần cho phép request header Authorization.
- Nếu client gửi CSRF header, phải cho phép header đó.
- Nếu frontend đọc Location hoặc ETag, cần expose các response header tương ứng.

Không kết hợp wildcard origin * với credentialed CORS. CORS không cấp quyền truy cập dữ liệu và không thay thế CSRF hoặc authorization. Nếu dùng Spring Security, bảo đảm CORS được xử lý trước khi preflight bị chặn bởi authentication.

## 9. Cookie session và bearer token có rủi ro lưu trữ khác nhau

Session cookie thường được browser quản lý và tự gửi theo cookie policy. Cấu hình cookie nên có:

- Secure khi chạy HTTPS.
- HttpOnly để JavaScript không đọc session cookie.
- SameSite phù hợp với topology và luồng đăng nhập.
- Path và Domain càng hẹp càng tốt theo deployment.

Bearer token là credential dạng possession: ai sở hữu token có thể dùng token cho tới khi token hết hạn hoặc bị thu hồi. Vì vậy:

- Không ghi token vào log, URL, analytics hoặc error report.
- Dùng HTTPS cho mọi request.
- Ưu tiên access token có thời hạn ngắn và scope tối thiểu.
- Lưu token theo mô hình threat phù hợp; tránh lưu lâu dài trong nơi JavaScript bất kỳ có thể đọc nếu có lựa chọn an toàn hơn.
- Dùng refresh-token rotation/revocation theo chính sách của authorization server.
- Không chuyển tiếp token tới host khác chỉ vì API trả về một link.

Nếu bearer token được đặt trong cookie tự động gửi bởi browser, request trở lại có đặc tính CSRF giống credential cookie. Không được coi một token JWT là lý do tự động tắt CSRF.

## 10. Kiểm tra response 401 và 403

Hai trạng thái cần được phân biệt:

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| 401 Unauthorized | Request thiếu credential hợp lệ hoặc token không hợp lệ/hết hạn | Không gửi token, session hết hạn, JWT sai issuer |
| 403 Forbidden | Đã xác thực nhưng không đủ quyền hoặc bị CSRF policy từ chối | Thiếu scope, role không đủ, thiếu CSRF token |

Với browser dùng form login, unauthenticated request có thể được redirect tới login page thay vì trả 401 JSON. Với API bearer, nên trả response 401/403 theo API contract để client xử lý rõ ràng.

Không trả chi tiết nội bộ về chữ ký, key hoặc claim nhạy cảm trong error body. Ghi log ở server với correlation ID và thông tin đủ để chẩn đoán, nhưng không ghi raw bearer token hoặc session ID.

## 11. Ví dụ gọi API bằng session cookie

Có thể kiểm tra session flow bằng curl lưu cookie trong cookie jar. Ví dụ minh họa với form login:

~~~bash
curl -i -c cookies.txt -X POST https://api.example.com/login -H "Content-Type: application/x-www-form-urlencoded" --data "username=demo&password=REPLACE_ME"
~~~

Sau khi đăng nhập, dùng cookie jar cho request tiếp theo:

~~~bash
curl -i -b cookies.txt -H "Accept: application/hal+json" https://api.example.com/people
~~~

Với request ghi, cần lấy CSRF token theo contract ứng dụng và gửi lại cùng cookie session:

~~~bash
curl -i -b cookies.txt -X POST https://api.example.com/people -H "Content-Type: application/json" -H "X-XSRF-TOKEN: REPLACE_WITH_CSRF_TOKEN" --data '{"name":"An Nguyen"}'
~~~

Tên endpoint login, cách lấy CSRF token và header cụ thể phụ thuộc cấu hình. Không dùng password thật trong shell history hoặc script chia sẻ.

## 12. Ví dụ gọi API bằng bearer token

Client gửi access token trong header:

~~~bash
curl -i -H "Authorization: Bearer REPLACE_WITH_ACCESS_TOKEN" -H "Accept: application/hal+json" https://api.example.com/people
~~~

Nếu endpoint yêu cầu scope ghi:

~~~bash
curl -i -X POST https://api.example.com/people -H "Authorization: Bearer REPLACE_WITH_ACCESS_TOKEN" -H "Content-Type: application/json" -H "Accept: application/hal+json" --data '{"name":"An Nguyen"}'
~~~

Token phải do issuer tin cậy cấp và có scope/authority phù hợp. Không dùng token giả hoặc token hết hạn để kết luận endpoint hoạt động; hãy kiểm tra cả token hợp lệ, thiếu scope và hết hạn trong test.

## 13. Kiểm thử session và bearer với MockMvc

Spring Security Test cung cấp request post-processors để kiểm tra các trạng thái xác thực khác nhau. Ví dụ session/user đã xác thực:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void authenticatedSessionUserCanReadPeople() throws Exception {
    mockMvc.perform(get("/people").with(user("alice").roles("USER")))
        .andExpect(status().isOk());
}

@Test
void sessionWriteRequiresCsrfToken() throws Exception {
    mockMvc.perform(post("/people")
            .with(user("alice").roles("USER"))
            .contentType("application/json")
            .content("{\"name\":\"An\"}"))
        .andExpect(status().isForbidden());
}

@Test
void sessionWriteSucceedsWithCsrfToken() throws Exception {
    mockMvc.perform(post("/people")
            .with(user("alice").roles("USER"))
            .with(csrf())
            .contentType("application/json")
            .content("{\"name\":\"An\"}"))
        .andExpect(status().isCreated());
}
~~~

Để test bearer JWT, dùng jwt() request post-processor từ Spring Security Test:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

@Test
void bearerScopeCanReadPeople() throws Exception {
    mockMvc.perform(get("/people")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_people.read")
            )))
        .andExpect(status().isOk());
}
~~~

Các test trên giả định URL rule và repository fixture tương ứng. Với integration test xác minh JWT thật, cần kiểm tra issuer, chữ ký, audience và expiry bằng cấu hình resource server thực tế; jwt() chủ yếu giúp kiểm tra authorization behavior mà không cần ký token thật.

## 14. Checklist chọn và triển khai authentication

- Xác định client chính: browser web, SPA, mobile, service hay nhiều loại.
- Chọn session cho luồng browser tương tác cần server-side session; chọn bearer cho API client gửi token rõ ràng.
- Với session cookie, giữ CSRF protection và cấu hình cookie Secure/HttpOnly/SameSite.
- Với bearer JWT, cấu hình trusted issuer/JWK và kiểm tra expiry, issuer, audience, scope.
- Chỉ đặt API stateless và tắt CSRF khi API thực sự không dùng credential cookie tự động gửi.
- Nếu hỗ trợ cả hai, tách route/filter chain hoặc có chính sách CSRF phù hợp cho từng loại credential.
- Bảo vệ Spring Data REST ở filter chain và cân nhắc method security cho repository/service.
- Cấu hình CORS theo origin, request headers và response headers mà browser cần.
- Trả 401 cho request chưa xác thực và 403 cho request đã xác thực nhưng không đủ quyền theo API contract.
- Không log password, session ID hoặc raw bearer token.
- Kiểm thử request anonymous, session hợp lệ, session hết hạn, thiếu CSRF, bearer hợp lệ, token hết hạn và thiếu scope.

Tài liệu tham khảo chính thức:

- [Spring Security — Servlet Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/index.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — CORS Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Data REST — Security](https://docs.spring.io/spring-data/rest/reference/security.html)
