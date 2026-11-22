# DelegatingAuthenticationEntryPoint để chọn cách phản hồi theo yêu cầu trong Spring Security Servlet

**Phạm vi:** Java 17+, Spring Security 6.x, Spring Boot 3.x và Jakarta Servlet. Chủ đề thuộc nhóm **Phản hồi lỗi**. Bài học giải thích cách dùng <code>DelegatingAuthenticationEntryPoint</code> để chọn phản hồi khi request chưa được xác thực hoặc không đáp ứng yêu cầu xác thực: API thường cần 401 JSON, AJAX cần dữ liệu máy đọc được, còn trình duyệt HTML thường cần redirect đến trang login. Trọng tâm là cơ chế <code>RequestMatcher</code>, **thứ tự match**, default entry point, luồng <code>ExceptionTranslationFilter</code> và cách phân biệt 401 với 403.

**Nguyên tắc cốt lõi:** <code>AuthenticationEntryPoint</code> quyết định **cách yêu cầu client bắt đầu hoặc thực hiện lại xác thực** khi cơ chế bảo vệ cần điều đó. Nó không phải policy cấp quyền truy cập tài nguyên. Việc một API được phản hồi JSON hay một trang web được redirect chỉ là **định dạng/luồng phản hồi**, không được biến thành điều kiện bỏ qua authorization.

## 1. Bài toán: cùng backend, nhiều loại client

Hãy hình dung một ứng dụng Servlet phục vụ đồng thời:
- Browser mở <code>GET /app/profile</code> và muốn nhìn trang đăng nhập khi chưa có session.
- JavaScript frontend gọi <code>GET /api/data</code> và cần HTTP 401 cùng JSON để hiển thị thông báo/hướng dẫn login.
- Một AJAX request gọi <code>/app/profile</code> với header <code>X-Requested-With: XMLHttpRequest</code>; JavaScript muốn nhận JSON 401 thay vì nhận HTML của form login.
- Một user đã đăng nhập nhưng không có ROLE_ADMIN gọi <code>GET /api/admin/summary</code>; trường hợp này phải được từ chối theo authorization, **không** nhầm với chưa đăng nhập.

Nếu dùng đúng một entry point mặc định cho toàn bộ đường dẫn, UI có thể gặp các vấn đề:
- API trả 302 tới <code>/login</code>; fetch tự follow redirect, rồi cố parse HTML như JSON.
- Browser truy cập trang web lại nhìn body JSON <code>{"error":"unauthorized"}</code> thay vì trang đăng nhập.
- Một HTTP Basic client không nhận được <code>WWW-Authenticate</code> phù hợp, dẫn đến không biết cơ chế cung cấp credential.
- Việc đánh đồng 401 và 403 khiến frontend thử đăng nhập liên tục dù user đã đăng nhập nhưng thiếu quyền.

<code>DelegatingAuthenticationEntryPoint</code> cho phép ứng dụng **định tuyến phản hồi authentication failure theo đặc điểm request** trong cùng một <code>SecurityFilterChain</code>.

### Ma trận hành vi mong muốn

| Yêu cầu | Authentication | Kết quả |
| --- | --- | --- |
| GET /public | Anonymous | 200 — endpoint công khai |
| GET /api/data | Anonymous | 401 JSON |
| GET /api/admin/summary | Anonymous | 401 JSON — cần authentication trước |
| GET /app/profile | Anonymous, browser thường | 302 redirect đến /login |
| GET /app/profile, X-Requested-With: XMLHttpRequest | Anonymous | 401 JSON |
| GET /api/data | User đã đăng nhập | 200 JSON |
| GET /api/admin/summary | User ROLE_USER | 403 — có identity nhưng thiếu ROLE_ADMIN |
| GET /api/admin/summary | User ROLE_ADMIN | 200 JSON |

Bảng trên là **contract của demo**, không có nghĩa mọi ứng dụng phải dùng 302 hay cùng body JSON. Với SPA, một API auth endpoint và login flow khác có thể phù hợp hơn. Phải định nghĩa contract trước khi viết matcher.

## 2. AuthenticationEntryPoint là interface nào?

Spring Security Servlet cung cấp interface:

~~~java
package org.springframework.security.web;

public interface AuthenticationEntryPoint {
    void commence(
        jakarta.servlet.http.HttpServletRequest request,
        jakarta.servlet.http.HttpServletResponse response,
        org.springframework.security.core.AuthenticationException authException
    ) throws java.io.IOException, jakarta.servlet.ServletException;
}
~~~

Chữ ký trên được viết lại để minh họa contract, không phải file interface người học cần tạo. Method <code>commence</code> bắt đầu một phản hồi dành cho client cần xác thực.

Một số implementation phổ biến:

| Entry point | Hành vi điển hình |
| --- | --- |
| <code>LoginUrlAuthenticationEntryPoint</code> | Redirect browser tới URL login |
| <code>HttpStatusEntryPoint</code> | Trả một HTTP status cố định, không tự tạo JSON body |
| <code>BasicAuthenticationEntryPoint</code> | Gửi 401 cùng challenge <code>WWW-Authenticate: Basic ...</code> |
| <code>BearerTokenAuthenticationEntryPoint</code> | Hỗ trợ challenge Bearer theo OAuth2 Resource Server/RFC 6750 |
| <code>Http403ForbiddenEntryPoint</code> | Trả 403 trong một số mô hình xác thực nhất định; không phải lựa chọn mặc định cho API anonymous cần 401 |
| <code>DelegatingAuthenticationEntryPoint</code> | Chọn một entry point khác theo danh sách <code>RequestMatcher</code> có thứ tự |

Interface này **không tự thực hiện login**. Chẳng hạn redirect tới <code>/login</code> chỉ hướng browser đến luồng xác thực; việc xử lý username/password thuộc authentication filter/provider tương ứng.

Một <code>AuthenticationEntryPoint</code> có thể gửi redirect, ghi body JSON, đặt header hoặc trả challenge. Nếu tự implement, phải xử lý response nhất quán và không đưa nội dung exception nhạy cảm ra client.

## 3. ExceptionTranslationFilter quyết định khi nào gọi entry point

Trong một request được bảo vệ, <code>ExceptionTranslationFilter</code> đóng vai trò cầu nối giữa Java security exceptions và phản hồi HTTP.

~~~text
HTTP request
    |
    v
Spring SecurityFilterChain
    |
    v
Authorization / downstream protected component
    |
    +-- Cho phép ------------------------> Controller
    |
    +-- AuthenticationException --------> ExceptionTranslationFilter
    |                                      |
    |                                      v
    |                              AuthenticationEntryPoint.commence(...)
    |                                      |
    |                             JSON 401 / login redirect
    |
    '-- AccessDeniedException
           |
           +-- Anonymous hoặc authentication
           |   chưa đáp ứng yêu cầu phù hợp
           |       |
           |       v
           |   AuthenticationEntryPoint.commence(...)
           |
           '-- Đã xác thực nhưng thiếu quyền
                   |
                   v
              AccessDeniedHandler
                   |
                  403
~~~

Cơ chế thực tế có thêm <code>AuthenticationTrustResolver</code>, remember-me, chính sách yêu cầu xác thực đầy đủ và <code>RequestCache</code>. Điều quan trọng là không sử dụng quy tắc đơn giản “mọi AccessDeniedException đều 403” hoặc “mọi 401 đều do một exception giống nhau”.

**Trường hợp người dùng anonymous** truy cập <code>/api/admin/summary</code> được rule <code>hasRole("ADMIN")</code> từ chối; <code>ExceptionTranslationFilter</code> có thể khởi động authentication entry point thay vì trả 403 trực tiếp, vì người dùng chưa xác thực.

**Trường hợp user ROLE_USER đã đăng nhập** nhưng thiếu ADMIN, authorization thất bại; thông thường <code>AccessDeniedHandler</code> trả 403, không gọi delegating authentication entry point. Hai luồng này cần được test riêng.

### Ranh giới quan trọng

<code>DelegatingAuthenticationEntryPoint</code> không nhất thiết xử lý **mọi** lỗi đăng nhập. Ví dụ form-login failure có thể do <code>AuthenticationFailureHandler</code> của <code>UsernamePasswordAuthenticationFilter</code> xử lý; HTTP Basic thất bại có thể do <code>BasicAuthenticationFilter</code> gọi entry point của chính nó; OAuth2 Resource Server có handlers và challenge riêng. Đừng kết luận thay một entry point sẽ thay luôn tất cả error handlers của mọi authentication mechanism.

## 4. DelegatingAuthenticationEntryPoint lựa chọn ra sao?

Implementation <code>org.springframework.security.web.authentication.DelegatingAuthenticationEntryPoint</code> nhận một ánh xạ **có thứ tự** từ <code>RequestMatcher</code> tới <code>AuthenticationEntryPoint</code>.

Luồng lựa chọn:

~~~text
DelegatingAuthenticationEntryPoint.commence(request, response, exception)
         |
         v
Kiểm tra matcher thứ nhất
         |
         +-- matches? YES --> entryPoint #1.commence(...)
         |
         '-- NO --> kiểm tra matcher thứ hai
                              |
                              +-- YES --> entryPoint #2.commence(...)
                              |
                              '-- NO --> ... thử tiếp
                                           |
                                           v
                                     defaultEntryPoint
~~~

API cốt lõi:

~~~java
LinkedHashMap<RequestMatcher, AuthenticationEntryPoint> mappings =
    new LinkedHashMap<>();

mappings.put(apiMatcher, jsonEntryPoint);
mappings.put(ajaxMatcher, jsonEntryPoint);

DelegatingAuthenticationEntryPoint selected =
    new DelegatingAuthenticationEntryPoint(mappings);

selected.setDefaultEntryPoint(
    new LoginUrlAuthenticationEntryPoint("/login"));
~~~

**Dùng <code>LinkedHashMap</code>** để giữ thứ tự chèn. Khi có nhiều matcher cùng khớp, entry point của **matcher đầu tiên** được gọi. <code>HashMap</code> không có cam kết insertion order, nên không nên dùng khi priority của matcher là một phần của behavior.

Luôn có **default entry point** rõ ràng cho những request không khớp matcher được liệt kê. Nếu không có fallback phù hợp, cấu hình/khởi tạo có thể thất bại; ngay cả khi cơ chế kiểm tra cho phép, những request không được phân loại vẫn không có contract phản hồi mong muốn.

### Matcher không phải authorization rule

Hai ý sau khác nhau:
- <code>requestMatchers("/api/**").authenticated()</code>: request cần authentication để truy cập.
- <code>apiMatcher -&gt; jsonEntryPoint</code>: nếu cần bắt đầu authentication ở request này, response được gửi theo định dạng JSON.

Việc matcher chọn JSON không cấp quyền gọi API. Đừng viết điều kiện kiểu “nếu là AJAX thì permitAll vì frontend sẽ tự xử lý”; client có thể tự gửi header AJAX. **Client-side UX không phải authorization**.

## 5. Chọn matcher: path, header, Accept và thứ tự

Các thuộc tính request thường dùng để định dạng phản hồi:
- **Path:** <code>/api/**</code> dùng JSON, <code>/app/**</code> dành cho trang web.
- **Header:** <code>X-Requested-With: XMLHttpRequest</code> cho request AJAX của một số frontend.
- **Accept:** <code>Accept: application/json</code> có thể gợi ý mong muốn JSON.
- **Content negotiation:** cơ chế <code>MediaTypeRequestMatcher</code> có thể được cấu hình để hiểu Accept/media type phức tạp hơn.

Trong demo, chọn hai matcher dễ dự đoán: <code>/api/**</code> trước, header <code>X-Requested-With</code> sau, default login redirect cuối. Chọn path làm tiêu chí chính giúp API luôn trả JSON kể cả client gửi <code>Accept: */*</code> hay không gửi header.

### Vì sao cần cẩn thận với Accept?

Một số browser và HTTP clients gửi:
- <code>Accept: */*</code>, nghĩa là chấp nhận mọi loại.
- <code>Accept: text/html,application/xhtml+xml,...</code> cho navigation.
- <code>Accept: application/json</code> cho JavaScript fetch.
- Nhiều media types kèm <code>q</code> priorities.

Kiểm tra chuỗi bằng <code>header.contains("application/json")</code> có thể xử lý sai một header phức tạp. Khi cần content negotiation thật, sử dụng abstraction như <code>MediaTypeRequestMatcher</code> với <code>ContentNegotiationStrategy</code> đúng phiên bản; kiểm thử cả <code>*/*</code>, quality factors, malformed headers và default.

Đừng sử dụng Accept để thay đổi quyền truy cập tài nguyên. Nó chỉ là tín hiệu về **representation**, không phải dấu hiệu user đáng tin cậy.

### Header X-Requested-With có đáng tin?

<code>X-Requested-With</code> có thể được client tự đặt. Vì vậy nó chỉ nên chọn JSON/redirect, **không** dùng như một security boundary để bỏ CSRF, bỏ authentication hoặc nâng role. AJAX client mới cũng có thể không tự gửi header này; cần định nghĩa contract frontend rõ ràng.

## 6. Xác định response contract trước khi implement

Trong hệ thống demo:

| Loại request chưa đăng nhập | Matcher | Phản hồi |
| --- | --- | --- |
| Bất kỳ <code>/api/**</code> | Path API | 401; <code>Content-Type: application/json</code>; body <code>{"error":"unauthorized"}</code> |
| Non-API nhưng header AJAX chuẩn | Header X-Requested-With | 401 với cùng JSON body |
| Điều hướng web thông thường | Không khớp hai matcher trên | 302 với <code>Location: /login</code> hoặc URL tương đương theo context |
| Endpoint <code>/public</code> | Authorization permitAll | Không gọi entry point; 200 |
| User được xác thực nhưng thiếu role | AccessDeniedHandler | 403; body tùy cấu hình |

Ví dụ JSON được cố ý giữ **ổn định, không chứa exception message**:

~~~json
{"error":"unauthorized"}
~~~

Trong production, có thể thêm <code>code</code>, <code>message</code>, <code>traceId</code> không nhạy cảm hoặc một error envelope chung, nhưng không trả stack trace, username bị đoán, raw token, login credentials hoặc chi tiết nội bộ.

**Đừng redirect API rồi trả 200 HTML login page**, vì một fetch client có thể tự follow redirect và không còn nhìn thấy 401. Ngược lại, browser navigation đến một trang HTML cần đăng nhập thường có trải nghiệm tốt hơn khi redirect có chủ đích.

## 7. Dự án mẫu hoàn chỉnh với Spring Boot và Spring Security

Ví dụ dùng **Java 17, Spring Boot 3.3.5, Spring Security 6.x và Maven**. Ứng dụng có form login với hai tài khoản demo; endpoint public, API, trang web và API admin. Mục đích là cho thấy delegating entry point hoạt động trong **một SecurityFilterChain**.

Cấu trúc:

~~~text
delegating-entry-point-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/entrypoint/
    │   ├── EntryPointApplication.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/com/example/entrypoint/
        └── DelegatingEntryPointTest.java
~~~

Tài khoản demo:
- <code>alice</code>: ROLE_USER, password <code>alice-local-1234</code>.
- <code>admin</code>: ROLE_USER và ROLE_ADMIN, password <code>admin-local-1234</code>.

Các password này chỉ dùng ở localhost; không dùng cho deployment thực.

### 7.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>delegating-entry-point-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.2. EntryPointApplication.java

Tạo <code>src/main/java/com/example/entrypoint/EntryPointApplication.java</code>:

~~~java
package com.example.entrypoint;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EntryPointApplication {
    public static void main(String[] args) {
        SpringApplication.run(EntryPointApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfiguration.java

Tạo <code>src/main/java/com/example/entrypoint/SecurityConfiguration.java</code>:

~~~java
package com.example.entrypoint;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.DelegatingAuthenticationEntryPoint;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-local-1234"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-local-1234"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        // Ưu tiên các request có path /api/**.
        RequestMatcher apiMatcher = new AntPathRequestMatcher("/api/**");

        // Một số frontend nhận diện AJAX bằng X-Requested-With.
        RequestMatcher ajaxMatcher = request ->
            "XMLHttpRequest".equals(
                request.getHeader("X-Requested-With"));

        // Response cho API/AJAX khi yêu cầu authentication.
        AuthenticationEntryPoint json401 =
            (request, response, exception) -> {
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                response.setCharacterEncoding(
                    StandardCharsets.UTF_8.name());
                response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
                // Không trả exception.getMessage() ra client.
                response.getWriter()
                    .write("{\"error\":\"unauthorized\"}");
            };

        LinkedHashMap<RequestMatcher, AuthenticationEntryPoint> mapping =
            new LinkedHashMap<>();
        mapping.put(apiMatcher, json401);
        mapping.put(ajaxMatcher, json401);

        DelegatingAuthenticationEntryPoint delegated =
            new DelegatingAuthenticationEntryPoint(mapping);

        // Request web thông thường chuyển đến form đăng nhập.
        delegated.setDefaultEntryPoint(
            new LoginUrlAuthenticationEntryPoint("/login"));

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login", "/error")
                    .permitAll()
                .requestMatchers("/api/admin/**", "/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers("/api/**", "/app/**")
                    .authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .exceptionHandling(errors ->
                errors.authenticationEntryPoint(delegated))
            .build();
    }
}
~~~

**Phân tích theo thứ tự:**
1. <code>apiMatcher</code> chỉ dựa vào path <code>/api/**</code>, nên API nhận JSON 401 kể cả request không gửi <code>X-Requested-With</code>.
2. <code>ajaxMatcher</code> được xét sau API và áp dụng cho những URL còn lại khi header bằng <code>XMLHttpRequest</code>.
3. <code>LinkedHashMap</code> giữ ưu tiên rõ ràng; không dùng <code>HashMap</code>.
4. <code>delegated.setDefaultEntryPoint(...)</code> cung cấp fallback redirect cho web navigation.
5. <code>.exceptionHandling(errors -&gt; errors.authenticationEntryPoint(delegated))</code> cấu hình entry point cho các lỗi được <code>ExceptionTranslationFilter</code> chuyển thành yêu cầu bắt đầu authentication.
6. <code>.formLogin(...)</code> cung cấp luồng username/password và trang login mặc định.
7. <code>/login</code> được permitAll để tránh redirect loop và cho phép trang login hiển thị khi anonymous.
8. <code>/api/admin/**</code> được liệt kê **trước** <code>/api/**</code> trong authorization rules, nhờ đó ROLE_ADMIN vẫn là điều kiện riêng. Đừng đảo hai URL rules này rồi tưởng entry point lựa chọn JSON sẽ tự giữ quyền admin.
9. <code>.anyRequest().denyAll()</code> từ chối đường chưa được khai báo; trong ứng dụng thật phải phân loại thêm static resources, health checks và các route hợp lệ.
10. <code>json401</code> ghi JSON tối thiểu, status 401, charset UTF-8 và cache-control no-store; không trả chi tiết exception ra ngoài.

**Lưu ý kỹ thuật:** <code>AntPathRequestMatcher</code> có mặt trong Spring Security 6.3.x của Spring Boot 3.3.5; ở những dòng Spring Security mới hơn, một số API matcher có thể được khuyến nghị thay bằng request matcher dựa trên path pattern. Khi nâng version, dùng matcher đúng API và xác minh path semantics. Không áp dụng máy móc code theo bản mới vào bản 6.3 hoặc ngược lại.

### 7.4. DemoController.java

Tạo <code>src/main/java/com/example/entrypoint/DemoController.java</code>:

~~~java
package com.example.entrypoint;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/data")
    public Map<String, String> apiData(Authentication auth) {
        return Map.of("name", auth.getName(), "data", "sample");
    }

    @GetMapping("/app/profile")
    public Map<String, String> appProfile(Authentication auth) {
        return Map.of("name", auth.getName());
    }

    @GetMapping("/api/admin/summary")
    public Map<String, String> adminSummary() {
        return Map.of("status", "admin-only");
    }

    @GetMapping("/admin/panel")
    public Map<String, String> adminPanel() {
        return Map.of("status", "admin-panel");
    }
}
~~~

Trong demo, cả <code>/app/profile</code> và <code>/api/data</code> trả JSON khi đã xác thực, để test tập trung vào **response khi authentication chưa đủ**. Một ứng dụng HTML thật có thể trả template ở <code>/app/profile</code>; điều này không làm thay đổi nhiệm vụ của entry point.

User anonymous không được gọi tới controller của route private: <code>ExceptionTranslationFilter</code> sẽ đưa yêu cầu bắt đầu xác thực đến entry point thích hợp.

## 8. Test bằng MockMvc — phải xác nhận từng nhánh matcher

Tạo <code>src/test/java/com/example/entrypoint/DelegatingEntryPointTest.java</code>:

~~~java
package com.example.entrypoint;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DelegatingEntryPointTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRouteDoesNotInvokeAnEntryPoint() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void anonymousApiRequestGetsJson401() throws Exception {
        mvc.perform(get("/api/data"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.error").value("unauthorized"))
            .andExpect(header().string("Cache-Control", "no-store"));
    }

    @Test
    void anonymousApiAdminStillGets401BeforeLogin() throws Exception {
        mvc.perform(get("/api/admin/summary"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("unauthorized"));
    }

    @Test
    void anonymousBrowserNavigationRedirectsToLogin()
            throws Exception {
        mvc.perform(get("/app/profile"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void ajaxRequestToWebPathGetsJson401() throws Exception {
        mvc.perform(get("/app/profile")
                .header("X-Requested-With", "XMLHttpRequest"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.error").value("unauthorized"));
    }

    @Test
    void apiMatcherWinsEvenWithoutAjaxHeader() throws Exception {
        mvc.perform(get("/api/data")
                .header("Accept", "text/html"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("unauthorized"));
    }

    @Test
    void authenticatedWithoutAdminRoleGets403NotLoginRedirect()
            throws Exception {
        mvc.perform(get("/api/admin/summary")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedUsersCanAccessAllowedResources()
            throws Exception {
        mvc.perform(get("/api/data")
                .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"));

        mvc.perform(get("/api/admin/summary")
                .with(user("admin").roles("USER", "ADMIN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("admin-only"));
    }

    @Test
    void defaultLoginPageIsReachableWithoutAuthentication()
            throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk());
    }
}
~~~

Test chứng minh nhiều điều độc lập:
- Authorization permitAll thực sự bỏ qua entry point cho /public.
- Anonymous vào API cần auth được 401 JSON, không thành 302/HTML.
- Anonymous vào admin API vẫn là trường hợp cần bắt đầu authentication, không trả 403 chỉ vì URL yêu cầu ADMIN.
- Browser vào web path nhận redirect login như default entry point.
- AJAX vào cùng web path nhận JSON 401, cho thấy selector có tác dụng theo request.
- API path luôn được ưu tiên, ngay cả khi Accept là text/html.
- User đã authenticated nhưng không có ROLE_ADMIN bị 403 theo access denied flow.
- User có quyền hợp lệ nhận 200 và dữ liệu endpoint.
- Login page được permitAll để không tạo vòng lặp.

<code>.with(user(...))</code> của Spring Security Test thiết lập user cho MockMvc request. Nó phù hợp kiểm tra authorization/entry point trong test; nó **không** chứng minh form login database, password hashing hoặc session cookie thực tế đã hoạt động. Với những nội dung đó, viết thêm test POST /login với CSRF, session persistence và login failure handler.

**Giới hạn kết quả:** test code được soát về API và logic nhưng chưa được chạy thực tế trong bài soạn này. Hãy dùng <code>mvn test</code> với JDK 17+ và dependency tương ứng để xác nhận mọi assertion trên framework version đang dùng; redirect URL và generated login page cũng có thể khác theo context path tùy deployment.

## 9. Thử thủ công bằng curl và browser

Chạy:

~~~bash
mvn test
mvn spring-boot:run
~~~

Ví dụ yêu cầu khi chưa đăng nhập:

~~~bash
# Public: 200 JSON.
curl -i http://localhost:8080/public

# API: 401 JSON.
curl -i http://localhost:8080/api/data

# API vẫn JSON dù Accept gợi ý HTML.
curl -i -H "Accept: text/html" http://localhost:8080/api/data

# Browser-style request: redirect đến /login.
curl -i http://localhost:8080/app/profile

# AJAX request tới web path: 401 JSON.
curl -i -H "X-Requested-With: XMLHttpRequest" \
  http://localhost:8080/app/profile

# Trang đăng nhập của Spring Security.
curl -i http://localhost:8080/login
~~~

Đối với form login, việc truy cập <code>GET /login</code> có thể render HTML. Khi kiểm thử đăng nhập qua POST /login bằng curl phải gửi CSRF token hợp lệ và cookie tương ứng; nếu chỉ gửi username/password mà bỏ CSRF, 403 có thể là hành vi đúng. Không tắt CSRF để làm request thủ công thuận tiện.

| Request | Dự kiến | Giải thích |
| --- | --- | --- |
| GET /public anonymous | 200 JSON | permitAll |
| GET /api/data anonymous | 401 JSON | API matcher |
| GET /api/data, Accept text/html | 401 JSON | API path vẫn được ưu tiên |
| GET /app/profile anonymous | 302 /login | Default LoginUrlAuthenticationEntryPoint |
| GET /app/profile, X-Requested-With | 401 JSON | AJAX matcher |
| GET /login anonymous | 200 HTML login | Form-login page |
| GET /api/admin/summary, user ROLE_USER | 403 | AccessDeniedHandler |
| GET /api/admin/summary, user ROLE_ADMIN | 200 JSON | Đã đủ quyền |

Để thử các hàng authenticated bằng browser, đăng nhập theo form rồi dùng cookie session. Không giả định curl <code>-u username:password</code> sẽ đăng nhập thành công khi demo chỉ cấu hình **form login**, không bật <code>httpBasic()</code>. Nếu muốn dùng HTTP Basic trong dự án, cần cấu hình nó riêng và hiểu semantics của BasicAuthenticationFilter/entry point trước khi test.

## 10. 401 khác 403: không dùng DelegatingAuthenticationEntryPoint cho mọi lỗi

**401 Unauthorized** trong HTTP thực tế thường có nghĩa client chưa được xác thực hợp lệ để truy cập resource; tùy authentication scheme, response có thể cần challenge <code>WWW-Authenticate</code>. Đặc biệt HTTP Basic và OAuth2 Bearer có yêu cầu giao thức khác với JSON-only demo.

**403 Forbidden** nghĩa request được hiểu nhưng server từ chối quyền truy cập; trong Spring Security nó thường xuất hiện khi Authentication đã có nhưng authority/policy không cho action. Một 403 khác có thể do CSRF chặn request, kể cả khi user chưa login; không suy ra 403 chắc chắn là thiếu role.

Ví dụ:

~~~text
Anonymous -> GET /api/admin/summary
    |
    v
hasRole(ADMIN) không đạt
    |
ExceptionTranslationFilter nhận thấy chưa xác thực
    |
DelegatingAuthenticationEntryPoint
    |
401 {"error":"unauthorized"}


Alice đã login (ROLE_USER) -> GET /api/admin/summary
    |
    v
hasRole(ADMIN) không đạt
    |
AccessDeniedHandler
    |
403 (body tùy cấu hình)
~~~

Nếu muốn **403 JSON nhất quán** cho API, hãy cấu hình riêng <code>AccessDeniedHandler</code>, có thể dùng matcher/delegation tương ứng; không ép <code>AuthenticationEntryPoint</code> phải xử lý cả hai tình huống.

Một trích đoạn ý tưởng (không phải file chạy độc lập):

~~~java
AccessDeniedHandler apiForbidden = (request, response, denied) -> {
    response.setStatus(HttpServletResponse.SC_FORBIDDEN);
    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
    response.getWriter().write("{\"error\":\"forbidden\"}");
};

// Đây là handler cho access denied, không phải AuthenticationEntryPoint.
// Kết hợp path matcher nếu chỉ muốn JSON cho /api/**.
~~~

Nếu gọi <code>apiForbidden</code> cho toàn bộ ứng dụng, các trang HTML cũng có thể trả JSON 403. Giống authentication entry point, access-denied response cần policy theo contract của client. Tuy nhiên **quyết định thiếu quyền** phải đến từ authorization, không từ header Accept hoặc X-Requested-With.

## 11. Vì sao một request login thất bại không nhất thiết đi qua delegate?

Có nhiều nguồn lỗi có vẻ giống “chưa đăng nhập” nhưng được xử lý bởi các component khác:

| Tình huống | Thành phần liên quan |
| --- | --- |
| Anonymous vào protected URL | ExceptionTranslationFilter + AuthenticationEntryPoint |
| User authenticated nhưng thiếu role | AccessDeniedHandler |
| POST /login sai password | UsernamePasswordAuthenticationFilter + AuthenticationFailureHandler |
| POST thiếu CSRF token | CsrfFilter + AccessDeniedHandler/exception translation tùy tình huống |
| HTTP Basic credentials không hợp lệ | BasicAuthenticationFilter và authentication entry point phù hợp |
| JWT Bearer token sai/hết hạn | Bearer token filter/handler và OAuth2 resource-server entry point |
| Controller tự ném exception nghiệp vụ | MVC exception resolver / error handling, không mặc định là auth entry point |

Trong demo, <code>.formLogin(Customizer.withDefaults())</code> còn có hành vi riêng khi form-login failure, thường redirect tới <code>/login?error</code>. Chỉ cấu hình <code>DelegatingAuthenticationEntryPoint</code> không làm một POST /login sai password tự động trả JSON như GET /api/data anonymous.

Nếu ứng dụng có API login riêng, phải định nghĩa failure handler/exception handling cho **chính endpoint đó**, đồng thời giữ CSRF/session policy phù hợp.

## 12. HTTP Basic và OAuth2 Bearer: challenge không chỉ là JSON

HTTP Basic quy định client có thể nhận challenge:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
~~~

Với OAuth2 Bearer, header có thể mang scheme Bearer và thông tin lỗi theo RFC 6750:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Các header trên là ví dụ định dạng; dữ liệu thực phụ thuộc authentication server/filter và trạng thái token. Với một OAuth2 resource server, <code>BearerTokenAuthenticationEntryPoint</code> và <code>BearerTokenAccessDeniedHandler</code> được thiết kế để đáp ứng semantics của Bearer. Đừng thay toàn bộ chúng bằng custom 401 JSON đơn giản nếu điều đó làm mất <code>WWW-Authenticate</code> hoặc thông tin challenge bắt buộc.

Tương tự, <code>BasicAuthenticationEntryPoint</code> không chỉ chọn status 401 mà còn tạo challenge Basic. Nếu bật cả <code>httpBasic()</code> và <code>formLogin()</code>, framework có cơ chế mặc định chọn entry point theo request media type và authentication flow; cách lựa chọn đó không nhất thiết giống selector đơn giản do ta tự viết.

**Quy tắc:** nếu một client cần tuân thủ protocol authentication (Basic, Bearer/OAuth2, OIDC), ưu tiên dùng handler/entry point chuẩn của scheme đó và kiểm thử header/status. Chỉ dùng custom JSON khi contract của ứng dụng phù hợp, và cấu hình để không phá đường xử lý error độc lập của authentication filter.

## 13. RequestCache và SavedRequest: side effect của redirect/login

Trong ứng dụng form login, Spring Security có thể lưu một request cần authentication vào <code>RequestCache</code>, thường qua cơ chế liên quan <code>HttpSessionRequestCache</code>, để redirect user về trang ban đầu sau khi đăng nhập.

Ví dụ:

~~~text
Anonymous browser: GET /app/profile
    |
    v
Security yêu cầu login
    |
RequestCache có thể lưu /app/profile
    |
    v
Redirect /login
    |
User đăng nhập
    |
    v
Chuyển về trang trước khi login (nếu cấu hình như vậy)
~~~

Đây có thể là UX mong muốn cho web navigation. Nhưng request API trả 401 JSON thường **không cần** server tạo session chỉ để lưu một failed API request. Nếu dùng cùng một security chain cho browser+API, cần kiểm tra liệu request-cache logic có tạo HttpSession không mong muốn cho API anonymous.

Một hướng thiết kế là cấu hình <code>RequestCache</code> có matcher chỉ lưu browser navigation, hoặc tách API/web thành các <code>SecurityFilterChain</code> có session/request-cache policy riêng. <code>NullRequestCache</code> là lựa chọn cho flow không muốn lưu yêu cầu; **không thay toàn bộ request cache bằng NullRequestCache** nếu sản phẩm vẫn cần quay lại trang trước sau form login.

Lựa chọn response JSON hay redirect không tự thay đổi session creation policy. Phải kiểm thử cả <code>Set-Cookie</code>, session store và saved request khi yêu cầu vận hành cần stateless API.

## 14. Một chain có delegate hay nhiều SecurityFilterChain?

<code>DelegatingAuthenticationEntryPoint</code> hữu ích khi các request chia sẻ cùng một security chain và phần lớn authentication/session behavior, chỉ khác **response khi bắt đầu authentication**.

Khi API và HTML web có sự khác biệt lớn về:
- Authentication mechanism (Bearer JWT vs session form login).
- Session policy (STATELESS vs IF_REQUIRED).
- CSRF rules.
- Request cache và CORS.
- Authorization rules và failure handlers.
- OAuth2 protocol challenge.

thì tách thành nhiều <code>SecurityFilterChain</code> với <code>securityMatcher("/api/**")</code> cho API và fallback chain cho web có thể rõ ràng hơn.

~~~text
Incoming request
        |
        v
FilterChainProxy chọn SecurityFilterChain đầu tiên khớp
        |
        +--> API chain: Bearer, STATELESS, API entry point
        |
        '--> WEB chain: formLogin, sessions, login redirect
~~~

**Phân biệt hai cấp lựa chọn:**
1. <code>FilterChainProxy</code> chọn SecurityFilterChain theo chain-level matcher và thứ tự <code>@Order</code>.
2. Trong một chain, <code>DelegatingAuthenticationEntryPoint</code> chọn AuthenticationEntryPoint theo matcher khi cần bắt đầu authentication.

Một delegate trong chain B **không** có tác dụng với request đã được chain A chọn. Và không nên dùng authentication entry point thay cho policy chọn authentication filter.

## 15. Custom error response phải an toàn

Khi tự implement JSON entry point:
- Giữ body chung, không expose <code>AuthenticationException.getMessage()</code>, stack trace, user existence hoặc thông tin cấu hình nội bộ.
- Dùng status đúng với scheme/contract; API cần auth trong demo trả 401, browser redirect 302.
- Giữ <code>Content-Type</code> nhất quán và body JSON hợp lệ; không ghi nửa JSON rồi redirect.
- Có thể dùng <code>Cache-Control: no-store</code> cho auth-related response có thể bị cache.
- Không echo token, password, cookie hay nguyên Authorization header vào error body/log.
- Nếu tạo trace ID, bảo đảm ID không để lộ secret và có correlation trong log bảo mật.
- Không tự tin header <code>X-Requested-With</code> hoặc <code>Accept</code>; chúng chỉ chọn định dạng phản hồi.
- Không lấy <code>returnUrl</code> từ query để <code>sendRedirect</code> tới arbitrary external URL, vì dễ tạo open redirect/phishing. Nếu cần return-to, kiểm tra allowlist và lưu safe path.

Cần thống nhất response envelope giữa gateway, Spring MVC exception handler, authentication entry point và access denied handler. Các lớp này có thể xử lý những exception khác nhau; **không có một handler nào tự bao phủ mọi lỗi**.

## 16. CSRF, CORS và AJAX không phải là lý do bỏ xác thực

Một frontend SPA có thể dùng fetch API, gửi <code>Accept: application/json</code> và <code>X-Requested-With</code>. Các header đó **không** cấp thêm quyền truy cập tài nguyên. CORS chỉ kiểm soát browser-origin access, không thay thế authentication/authorization. API được gọi từ browser với cookie/session vẫn có thể cần CSRF protection trên POST/PUT/DELETE.

Trong demo, GET là đường read-only, CSRF được giữ mặc định. Nếu bổ sung:

~~~java
@PostMapping("/api/update")
public void update(@RequestBody UpdateBody input) {
    // Thay đổi trạng thái; phải có policy, validation và CSRF phù hợp.
}
~~~

đó chỉ là trích đoạn minh họa; cần định nghĩa <code>UpdateBody</code> và authorization trong hệ thống thật. Không disable CSRF toàn application chỉ vì API muốn JSON 401; lỗi CSRF là một nhánh khác với anonymous GET. Với Bearer-only stateless API không dựa trên cookie tự gửi, threat model có thể khác; phải phân tích theo cách credential được truyền.

### Response sau timeout session

Một user đang ở trang web có session hết hạn:
- Browser navigation tới trang private có thể nhận redirect login.
- Background fetch tới API có thể nhận 401 JSON.
- Frontend cần xử lý 401 để cập nhật UI, tránh retry vô hạn và không coi JSON lỗi là dữ liệu thành công.

Nhưng nếu user đã authenticated mà bị 403, frontend nên hiển thị thông báo thiếu quyền hoặc đưa người dùng tới luồng xin quyền, không bắt họ đăng nhập lại vô hạn.

## 17. Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| API nhận 302/HTML login | API matcher không khớp, default redirect thắng | Kiểm tra path, context/servlet mapping và matcher order |
| Web navigation nhận 401 JSON | Header/path matcher quá rộng | Thu hẹp matcher; test request không có AJAX header |
| Chuyển sang HashMap khiến phản hồi thay đổi | Không có insertion order | Dùng LinkedHashMap, matcher cụ thể trước |
| Request không khớp bị xử lý bất thường | Thiếu hoặc sai default entry point | Đặt fallback tường minh |
| GET /login redirect vòng lặp | /login không accessible cho anonymous | permitAll login page và đường phụ trợ |
| API user đã login thiếu role bị 403 không phải JSON401 | Đây là AccessDeniedHandler, không phải entry point | Cấu hình 403 handler riêng nếu cần JSON |
| Form login sai password vẫn redirect /login?error | AuthenticationFailureHandler riêng | Cấu hình login failure contract nếu có yêu cầu |
| POST API thiếu CSRF bị 403 | CSRF filter chặn | Thiết kế CSRF/token phù hợp, không tắt bừa |
| Client HTTP Basic không hiện challenge | Entry point JSON không gửi WWW-Authenticate | Dùng BasicAuthenticationEntryPoint đúng scheme |
| Bearer client thiếu challenge/invalid_token semantics | Override resource server entry point quá rộng | Giữ BearerTokenAuthenticationEntryPoint |
| API anonymous tạo HttpSession ngoài ý muốn | RequestCache hoặc session policy stateful | Điều chỉnh request cache/chain/sessions |
| Matcher chỉ xét Accept rồi phát HTML cho API | Accept */* hoặc header sai | Ưu tiên API path hoặc content negotiation đúng |
| AJAX header tạo điều kiện bypass authorization | Nhầm response selection với access policy | Header chỉ chọn representation, không quyền |
| API và web dùng nhiều chain nhưng delegate nằm sai chain | FilterChainProxy chọn chain khác | Kiểm tra chain-level securityMatcher/@Order |
| Test MockMvc dùng @WithMockUser cho anonymous test | Test không còn anonymous | Tách test anonymous và authenticated |
| Tất cả 401 bị thay thành 403 | Dùng 403 entry point cho API anonymous | Rà lại contract authentication challenge |
| JSON body bị lỗi encoding hoặc chứa exception detail | Custom entry point viết trực tiếp không kiểm soát | Body cố định, UTF-8, no-store và safe logging |
| Bypass proxy/gateway gây path matcher sai | Servlet path, context path hoặc forwarded headers khác | Test URI thực trên deployment và cấu hình proxy đúng |

## 18. Checklist test và vận hành

1. Liệt kê loại client: browser HTML, SPA AJAX, API machine, Basic/Bearer/OIDC và yêu cầu response của từng client.
2. Xác định ranh giới authentication/authorization: entry point cho **bắt đầu auth**, access denied handler cho **thiếu quyền sau auth**.
3. Chọn RequestMatchers có chủ đích; ưu tiên path ổn định cho API và header/media-type để tinh chỉnh representation.
4. Dùng <code>LinkedHashMap</code> để bảo toàn priority; matcher cụ thể trước matcher rộng.
5. Cấu hình default entry point cho những request không khớp.
6. Xác nhận login page/public resources được permitAll, tránh redirect loop.
7. Giữ riêng policy URL: <code>/api/admin/**</code> phải được xét trước <code>/api/**</code>.
8. Test JSON 401: status, content-type, body, header cache, **không có redirect**.
9. Test browser redirect: status 3xx và Location tới login đúng context path.
10. Test AJAX đến web path để chứng minh nhánh header được dùng.
11. Test anonymous vào admin API nhận 401, user ROLE_USER vào cùng endpoint nhận 403, admin nhận 200.
12. Test form login failure riêng; không mặc định delegate xử lý mọi credential failure.
13. Nếu bật HTTP Basic/OAuth2 Bearer, xác nhận WWW-Authenticate/challenge đúng protocol.
14. Kiểm tra RequestCache/session creation cho API anonymous nếu yêu cầu không tạo session.
15. Với nhiều SecurityFilterChain, xác nhận chain-level matcher và thứ tự chọn chain.
16. Không dùng client headers làm điều kiện bỏ CSRF, authentication hoặc authorization.
17. Không trả raw exception, token, password, session ID hoặc stacktrace trong JSON response/log.
18. Khi đổi context path, reverse proxy, matcher framework hoặc Spring Security version, chạy lại integration tests end-to-end.

## 19. Câu hỏi tự kiểm tra

**Câu 1:** <code>DelegatingAuthenticationEntryPoint</code> quyết định user có quyền xem tài liệu không?  
**Đáp án:** Không. Nó chỉ chọn cách phản hồi khi cần bắt đầu authentication. Authorization do các request/method policies riêng quyết định.

**Câu 2:** Vì sao dùng <code>LinkedHashMap</code> thay vì <code>HashMap</code> khi khai báo matchers?  
**Đáp án:** Vì entry point đầu tiên có matcher khớp được chọn; insertion order cần được bảo đảm.

**Câu 3:** Anonymous gọi <code>/api/admin/summary</code> nên nhận 401 hay 403 trong demo?  
**Đáp án:** 401 JSON vì trước hết chưa được xác thực; sau khi đăng nhập nhưng thiếu ADMIN mới nhận 403.

**Câu 4:** User ROLE_USER đã login, gọi API ADMIN bị 403. Có phải delegating authentication entry point bị lỗi không?  
**Đáp án:** Không. Đây là access-denied flow do thiếu quyền; muốn 403 JSON phải xử lý AccessDeniedHandler riêng.

**Câu 5:** POST /login sai password có chắc đi qua <code>DelegatingAuthenticationEntryPoint</code> không?  
**Đáp án:** Không. Form login có <code>AuthenticationFailureHandler</code> riêng, thường chuyển tới /login?error; các authentication filters khác cũng có handlers riêng.

**Câu 6:** API nhận 401 JSON có chắc không tạo HttpSession nào không?  
**Đáp án:** Không. RequestCache/session policy độc lập với response entry point; cần test và cấu hình riêng nếu yêu cầu stateless.

**Câu 7:** Nếu client tự gửi <code>X-Requested-With: XMLHttpRequest</code>, nó có được bỏ kiểm tra ROLE_ADMIN không?  
**Đáp án:** Không. Header chỉ thay đổi định dạng phản hồi khi authentication chưa đủ, không có tác dụng cấp quyền.

**Câu 8:** Vì sao HTTP Basic hoặc Bearer cần cân nhắc trước khi thay bằng custom 401 JSON?  
**Đáp án:** Vì scheme có thể yêu cầu <code>WWW-Authenticate</code>/challenge semantics đúng chuẩn; custom body không được làm mất các header cần thiết.

**Câu 9:** Khi có hai <code>SecurityFilterChain</code>, delegate trong web chain có quyết định phản hồi cho API chain không?  
**Đáp án:** Không. FilterChainProxy chọn chain phù hợp trước; delegate chỉ hoạt động trong chain có dùng nó.

**Câu 10:** Khi nào nên dùng nhiều chain thay vì một chain có delegate?  
**Đáp án:** Khi API và web khác lớn về authentication mechanism, session, CSRF, request cache hoặc protocol; delegate phù hợp nhất khi khác biệt chính là cách yêu cầu xác thực.

**Ghi nhớ:** <code>DelegatingAuthenticationEntryPoint</code> là **bộ chọn cách phản hồi authentication commencement theo RequestMatcher có thứ tự**, không phải bộ phân quyền. Trong Spring Security Servlet, hiểu rõ <code>ExceptionTranslationFilter</code>, phân biệt 401/403, dùng fallback rõ ràng, giữ challenges đúng giao thức và kiểm thử cả API/AJAX/browser lẫn trạng thái user đã xác thực.
