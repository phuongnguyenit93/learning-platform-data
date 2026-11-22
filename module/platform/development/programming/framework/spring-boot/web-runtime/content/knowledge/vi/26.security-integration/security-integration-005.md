# Phối hợp bảo mật với CORS, CSRF và cookie phiên trong Spring Boot

Trong ứng dụng Spring Boot sử dụng session login, browser thường nhận cookie chứa một session ID để gắn các request với phiên đã xác thực. Khi frontend và backend khác origin, **CORS** quyết định JavaScript của origin nào được phép đọc response. Vì browser có thể tự động gửi cookie, **CSRF protection** bảo vệ những thao tác thay đổi dữ liệu khỏi request được tạo bởi trang không đáng tin cậy. **Cookie attributes** như HttpOnly, Secure và SameSite bổ sung giới hạn truyền cookie. Ba cơ chế này liên quan chặt chẽ nhưng không thể thay thế nhau.

Ví dụ, frontend chạy tại **https://app.example.test** gọi API Spring Boot tại **https://api.example.test**. Hai host có origin khác nhau và cần CORS nếu JavaScript đọc response. Nhưng cả hai thường được coi là same-site khi dùng HTTPS và cùng registrable domain example.test. Cookie host-only của API có thể được browser gửi khi frontend gọi API nếu có credentials mode phù hợp; điều đó lại tạo ra nhu cầu CSRF protection cho POST/PATCH/DELETE sử dụng phiên.

Bài thuộc nhóm **Tích hợp bảo mật**, module **Spring Boot - web-runtime**, sử dụng **Java 17+, Spring Boot 3.3.x, Spring Security 6.x, Spring MVC Servlet**, Maven và Thymeleaf làm ví dụ. Tài khoản, mật khẩu và domain trong bài đều là dữ liệu thử nghiệm. Trong production phải dùng HTTPS, identity management và security policy riêng.

## 1. Mục tiêu học tập

Sau bài, bạn cần:

1. Phân biệt **cross-origin** và **cross-site**, hiểu vì sao chúng không đồng nghĩa.
2. Hiểu **CORS preflight OPTIONS**, Allowed-Origin, Allowed-Credentials, allowed methods/headers và vai trò của browser.
3. Hiểu **CSRF threat model** khi browser tự động gửi cookie phiên, và vì sao CORS không tự chặn CSRF.
4. Nắm ý nghĩa **HttpOnly, Secure, SameSite=Strict/Lax/None, Domain, Path** và sự khác nhau giữa thời hạn cookie và session timeout.
5. Tạo **SecurityFilterChain** bật CORS đúng vị trí và giữ CSRF mặc định cho các phương thức thay đổi dữ liệu.
6. Phân biệt response **401 thiếu xác thực**, **403 thiếu quyền/CSRF token**, **CORS error** và lỗi cookie delivery.
7. Tạo project hoàn chỉnh có login form, API GET/POST, CSRF token Thymeleaf, cookie session và cấu hình CORS.
8. Viết **MockMvc tests** cho preflight hợp lệ/bị cấm, API chưa login, POST có/không có CSRF, login và session.
9. Biết giải quyết vấn đề SPA khác origin: XSRF-TOKEN, token refresh, deferred loading và BREACH trong Spring Security 6.
10. Lập checklist bảo mật cho subdomain, proxy, cache, nhiều replicas và production.

## 2. Mỗi cơ chế trả lời câu hỏi gì?

| Cơ chế | Vai trò | Không thay thế được |
| --- | --- | --- |
| **CORS** | Browser kiểm soát quyền JavaScript đọc response giữa các origin, và preflight đối với một số request. | Authentication, authorization, CSRF, network firewall. |
| **Session cookie** | Browser gửi ID để server tìm phiên đã xác thực. | Ý định của user và quyền thao tác. |
| **CSRF token** | Một unsafe request có bằng chứng hợp lệ từ ứng dụng không? | Login, authorization, XSS protection, CORS. |
| **SameSite** | Browser hạn chế gửi cookie trong cross-site requests. | CSRF token cho mọi trường hợp, đặc biệt same-site subdomain. |
| **HttpOnly** | Ngăn document.cookie đọc session cookie. | Không ngăn browser tự gửi cookie, không ngăn mọi XSS. |
| **Secure** | Giới hạn cookie ở kết nối bảo mật phù hợp. | Không ngăn CSRF, XSS hay session fixation. |
| **Authorization** | Principal được phép truy cập resource/operation không? | Không xác nhận request có bị giả mạo từ website khác không. |

Một website độc hại có thể tạo request nhưng không đọc được response vì CORS; **side effect vẫn có thể xảy ra** nếu ứng dụng thiếu CSRF. Ngược lại, một origin được CORS whitelist không tự động có quyền đọc tài khoản của bất kỳ người dùng nào: API vẫn phải xác thực và phân quyền.

## 3. Cross-origin khác cross-site

### 3.1. Origin được xác định bằng scheme, hostname và port

~~~text
https://app.example.test        origin A
https://api.example.test        origin B: khác hostname
https://app.example.test:8443   origin C: khác port
http://app.example.test         origin D: khác scheme
~~~

JavaScript tại A gọi B là cross-origin và chịu Same-Origin Policy. CORS là cơ chế để **server B cho phép** một số origin đọc response thông qua headers. CORS không giới hạn khả năng một chương trình curl/Postman/backend service gửi HTTP request.

### 3.2. Site thường phụ thuộc scheme và registrable domain

Browser hiện đại dùng khái niệm **schemeful same-site**, thường dựa trên scheme và eTLD+1/registrable domain, không giống origin:

| Frontend → API | Cross-origin | Cross-site | Ý nghĩa |
| --- | --- | --- | --- |
| **https://app.example.test → https://api.example.test** | Có | Thường không | CORS vẫn cần; SameSite=Lax có thể cho cookie trong fetch. |
| **https://app.example.test → https://api.other.test** | Có | Có | Cross-site cookie chịu SameSite, Secure, third-party cookie policy. |
| **https://app.example.test → http://api.example.test** | Có | Có theo schemeful site | Khác scheme; không nên hạ cấp HTTPS. |
| **http://localhost:5173 → http://localhost:8080** | Có | Thường same-site | Khác port nên fetch cần CORS; cookie không scope theo port. |
| **https://app.example.test → https://app.example.test:8443** | Có | Không | Khác origin vì port nhưng cùng site. |

Một cookie host-only của **api.example.test** được gửi đến chính api.example.test khi request hợp lệ. Không cần đặt **Domain=.example.test** chỉ vì frontend nằm ở app.example.test. Mở Domain sang nhiều subdomain có thể làm ranh giới cookie yếu hơn.

**Same-site không đồng nghĩa đáng tin**: trang độc hại ở **evil.example.test** có thể cùng site với API. Vì thế, **SameSite=Lax không thay thế CSRF token**, và CORS không nên tùy tiện cho mọi subdomain. Khi subdomain được vận hành bởi bên thứ ba, hãy xem đó là một trust boundary thực sự.

## 4. CORS hoạt động như thế nào?

### 4.1. Simple request và preflight

Một số request đủ điều kiện CORS-safelisted có thể được browser gửi thẳng, sau đó browser mới kiểm tra response header để quyết định có cho JavaScript đọc dữ liệu hay không. Một số request khác (ví dụ POST JSON hoặc có custom CSRF header) cần **OPTIONS preflight** trước actual request.

Ví dụ preflight:

~~~http
OPTIONS /api/notes HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Response ví dụ:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Max-Age: 3600
Vary: Origin
~~~

Preflight là request browser dùng để hỏi chính sách, **không phải lời gọi nghiệp vụ**. Nó **thường không mang JSESSIONID**, nên không được để authentication filter bắt nó đăng nhập trước khi CORS xử lý. Tài liệu Spring Security yêu cầu **CORS được xử lý trước Security** để tránh tình huống preflight bị coi là unauthenticated.

**Max-Age trong preflight** là thời gian browser cache kết quả preflight theo chính sách riêng, không có nghĩa server session sống 3600 giây.

### 4.2. Credentialed CORS

Frontend cross-origin muốn browser cân nhắc gửi cookie:

~~~javascript
fetch("https://api.example.test/api/me", {
  method: "GET",
  credentials: "include"
});
~~~

Server, nếu cho origin đó đọc response có credentials, trả:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Không được kết hợp Access-Control-Allow-Origin: * với credentialed CORS**. Trường hợp credentials=true cần origin cụ thể. Spring CORS có validation để ngăn **allowedOrigins("*")** với **allowCredentials(true)**.

**credentials: include không vượt được các chính sách cookie khác**: SameSite, Secure, Domain/Path, third-party cookie blocking, browser permissions hay cookie bị xóa. Nếu fetch có include nhưng network request không có Cookie header, cần kiểm tra cookie policy chứ không mặc định sửa CORS.

### 4.3. CORS không phải CSRF protection

Một HTML form đơn giản có thể khiến browser phát POST cross-origin dù JavaScript không được đọc response. Nếu server xử lý side effect chỉ dựa trên session cookie, hành động sai vẫn có thể xảy ra. CORS chặn quyền JavaScript đọc response, không thay thế **CSRF token validation** cho unsafe methods.

**curl cũng không tuân theo browser Same-Origin Policy**. Gửi curl không có Origin header vẫn có thể gọi API; backend phải kiểm tra authentication và authorization ở mọi request. Không dùng Origin header như bằng chứng duy nhất của danh tính client.

### 4.4. Origin reflection, allowlist và Vary

Cấu hình kiểu **cho tất cả origin hoặc phản chiếu bất kỳ Origin được gửi** rất nguy hiểm khi có cookies. Nếu cho phép nhiều origin có kiểm soát, cache/proxy phải xử lý **Vary: Origin** và các preflight Vary fields phù hợp. Đừng xóa Vary để tăng cache hit nếu response thay đổi theo Origin.

**CORS chỉ nên áp dụng cho route thực sự cần browser cross-origin access**, ví dụ /api/**; login, admin hoặc internal management endpoints không cần mở cùng chính sách theo quán tính.

## 5. CSRF là gì trong hệ thống dùng cookie phiên?

### 5.1. Browser tự gửi ambient credentials

Người dùng đã login tại một trang ngân hàng. Browser giữ cookie session. Một site độc hại có thể tạo HTML form gửi POST đến ngân hàng; nếu browser cho cookie được gửi theo chính sách hiện hành, server có thể thấy request mang session hợp lệ dù người dùng không hề bấm nút chuyển tiền trên site ngân hàng.

~~~html
<form action="https://bank.example.test/transfer" method="post">
  <input name="to" value="attacker">
  <input name="amount" value="100">
</form>
~~~

Đây là **minh họa threat model**: cookie tự động được đính kèm là lý do CSRF xuất hiện. CORS không giải quyết vì attacker không nhất thiết cần đọc response. Chính sách SameSite hiện đại chặn nhiều trường hợp, nhưng không bảo đảm chặn mọi same-site subdomain hoặc bối cảnh browser.

### 5.2. Synchronizer CSRF token

Trong ứng dụng dùng Spring Security + HttpSession, mô hình điển hình:

1. Server có một **CSRF token** liên kết với session/ngữ cảnh bảo vệ.
2. Ứng dụng render token trong HTML form hoặc cung cấp cho JavaScript bằng cơ chế có kiểm soát.
3. Browser gửi token ở **hidden form parameter** hoặc **X-CSRF-TOKEN/X-XSRF-TOKEN header**.
4. Spring Security **CsrfFilter** kiểm tra token với giá trị mong đợi.
5. Token thiếu hoặc sai → **403 Forbidden**; controller thay đổi dữ liệu không được thực thi.

Mẫu HTML biểu diễn cơ chế:

~~~html
<form action="/api/notes" method="post">
  <input name="note" value="hello">
  <input type="hidden" name="_csrf" value="TOKEN_SERVER_RENDERED">
  <button type="submit">Lưu</button>
</form>
~~~

**TOKEN_SERVER_RENDERED** là placeholder để giải thích, không phải token sử dụng thực tế. Token thật phải được tạo và kiểm tra bởi framework. Không đưa token vào URL query string vì có nguy cơ lộ qua history, proxy logs và Referer.

### 5.3. GET/HEAD/OPTIONS và unsafe methods

Spring Security mặc định áp dụng CSRF cho các HTTP method không thuộc nhóm safe, ví dụ **POST, PUT, PATCH, DELETE**. **GET/HEAD/OPTIONS** được xem là safe theo HTTP semantics; vì vậy application **không được cập nhật dữ liệu bằng GET** để rồi kỳ vọng CSRF tự chặn.

**POST /login và POST /logout** cũng là state-changing actions trong browser workflow. Nếu CSRF đang được bật, Spring Security yêu cầu token phù hợp. Việc đăng nhập bằng session và logout không nên được chuyển thành GET vì muốn dùng một hyperlink đơn giản.

### 5.4. CSRF khác authorization và XSS

CSRF token không có nghĩa user được phép thực hiện mọi thao tác. Request phải vượt **authentication và authorization** trước khi xử lý dữ liệu. Một user role VIEWER có CSRF token hợp lệ vẫn không nên được xóa tài liệu.

XSS cho script độc hại chạy trong origin tin cậy và có thể đọc token ở DOM hoặc gọi API cùng origin. Vì vậy CSRF token **không loại bỏ XSS**. Cần HTML escaping, CSP phù hợp, tránh DOM injection và bảo vệ supply chain. **HttpOnly** giúp ngăn đọc trực tiếp session cookie bằng JS nhưng không ngăn JS độc hại cùng origin gửi request.

## 6. Cookie phiên: các thuộc tính và chính sách

### 6.1. Cookie mẫu

~~~http
Set-Cookie: JSESSIONID=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- **HttpOnly**: JavaScript không đọc được giá trị cookie bằng document.cookie.
- **Secure**: browser chỉ gửi cookie qua kết nối an toàn phù hợp; production dùng HTTPS.
- **SameSite=Strict**: hạn chế cookie trong cross-site requests mạnh hơn, có thể làm mất trải nghiệm khi điều hướng từ site ngoài.
- **SameSite=Lax**: giảm một số bối cảnh cross-site POST nhưng vẫn có ngoại lệ an toàn/top-level navigation và cùng-site.
- **SameSite=None**: cho phép gửi cookie trong một số cross-site contexts khi đi kèm **Secure** và browser cho phép; third-party cookie restrictions vẫn có thể cản.
- **Path/Domain**: phạm vi URL và host của cookie, không phải boundary của permission.
- **Max-Age/Expires**: thời điểm browser có thể xóa cookie, khác với server HttpSession idle timeout.

### 6.2. Cấu hình Spring Boot

Ví dụ **application.yml** trên local:

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        same-site: lax
~~~

**server.servlet.session.timeout** là thời gian không hoạt động của session phía server. Cookie còn tồn tại không có nghĩa session còn hiệu lực; khi ID cũ được gửi, server có thể trả 401/redirect. **server.servlet.session.cookie.max-age** chỉ ảnh hưởng thời gian browser lưu cookie, không tự tăng lifetime của HttpSession.

Trong môi trường HTTPS production, thường thêm:

~~~yaml
server:
  servlet:
    session:
      cookie:
        secure: true
~~~

Không dùng block Secure production này vào bài demo HTTP localhost nếu browser vì cookie Secure mà không gửi session. Ngược lại, không hạ xuống Secure=false trong production chỉ để lách lỗi reverse proxy; phải xử lý HTTPS và forwarded headers từ nguồn tin cậy.

### 6.3. SameSite và topology

Với **https://app.example.test** gọi **https://api.example.test**, khác origin nhưng thường same-site. Cookie **host-only** của API có thể được gửi trong credentialed fetch nếu mọi điều kiện khác đúng. Không cần đặt Domain=.example.test hoặc SameSite=None chỉ vì khác hostname.

Với **https://app.other.test** gọi **https://api.example.test**, là cross-site. Một fetch sử dụng cookie có thể đòi **SameSite=None; Secure**, nhưng chính sách third-party cookie của browser có thể vẫn chặn. Nếu dự án phải hoạt động khi third-party cookie bị chặn, cân nhắc **backend-for-frontend (BFF)** cùng origin/site, reverse proxy frontend và API, hoặc mô hình authentication khác được đánh giá bảo mật đầy đủ.

### 6.4. Cookie host-only, Domain và nhiều cổng localhost

Cookie **không scope theo port**. Hai ứng dụng khác port trên localhost vẫn có thể dùng cookie cùng tên gây lẫn khi test. Với production, ưu tiên cookie **host-only** nếu API là host duy nhất cần session. Chỉ đặt Domain rộng khi thật sự cần chia sẻ cookie giữa subdomains và đã phân tích rủi ro; đặc biệt thận trọng khi có subdomain do người khác sở hữu.

Cookie prefix **__Host-** có ràng buộc bổ sung khi dùng Secure, Path=/ và không có Domain, hữu ích để harden session cookie trong một số môi trường. Tuy vậy nó **không thay CSRF token** hay authorization.

### 6.5. Session fixation, logout và CSRF token rotation

Spring Security thường đổi session ID sau khi authentication thành công để hạn chế **session fixation**. Khi logout, phải invalidate session phía server và xử lý cookie expire theo name/path/domain thực tế. Đơn giản xóa trạng thái ở frontend hoặc xóa một biến localStorage không thu hồi session server.

Spring Security cũng có thể **clear CSRF token sau login/logout**. Browser/template hoặc SPA phải lấy token mới; nếu giữ token cũ để POST tiếp, 403 là hợp lý. Không tắt CSRF để chữa lỗi lifecycle token.

## 7. Thực hành đầy đủ với Spring Boot 3.3 và Java 17

Project demo có form login với HttpSession, hai API và CORS cho một origin cố định:

- **GET /**: trang Thymeleaf có form POST ghi chú mẫu và form POST logout.
- **GET /api/me**: trả JSON user hiện tại, cần authenticated session.
- **POST /api/notes**: trả lại ghi chú mẫu, cần authenticated session **và CSRF token**.
- **GET/POST /login**, **POST /logout**: form login/logout của Spring Security.
- **CORS** chỉ mở cho origin **https://app.example.test** đối với các endpoint **/api/**.

**Giới hạn demo:** Login page do backend phục vụ cùng origin với API. Đây chưa phải một SPA login cross-origin hoàn chỉnh; CORS chỉ minh họa quyền frontend đọc API sau khi đã có session. Khi dùng SPA thật, phải thiết kế riêng việc cấp và refresh token (mục 11).

### 7.1. Cấu trúc project

~~~text
cors-csrf-cookie-demo/
  pom.xml
  mvnw
  mvnw.cmd
  src/
    main/
      java/com/example/websecurity/
        WebSecurityApplication.java
        WebSecurityConfig.java
        PageController.java
        NotesController.java
      resources/
        application.yml
        templates/index.html
    test/
      java/com/example/websecurity/
        WebSecurityIntegrationTest.java
~~~

Tạo Maven project từ Spring Initializr với Java 17+, Spring Web, Spring Security và Thymeleaf.

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cors-csrf-cookie-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

**spring-security-test** cho các helper MockMvc **user()** và **csrf()**. Dependency version do Spring Boot BOM quản lý, không pin riêng Spring Security version không tương thích. Mốc Spring Boot 3.3.13 để minh họa; deployment mới nên dùng release được hỗ trợ và áp dụng bản vá bảo mật phù hợp.

### 7.3. Main class

**src/main/java/com/example/websecurity/WebSecurityApplication.java**

~~~java
package com.example.websecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebSecurityApplication.class, args);
    }
}
~~~

### 7.4. Security configuration hoàn chỉnh

**src/main/java/com/example/websecurity/WebSecurityConfig.java**

~~~java
package com.example.websecurity;

import java.util.List;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            CorsConfigurationSource corsSource) throws Exception {

        http
            .cors(cors -> cors.configurationSource(corsSource))
            .csrf(withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().authenticated())
            .formLogin(withDefaults())
            .exceptionHandling(ex -> ex.defaultAuthenticationEntryPointFor(
                (request, response, exception) ->
                    response.sendError(
                            HttpServletResponse.SC_UNAUTHORIZED),
                new AntPathRequestMatcher("/api/**")))
            .logout(withDefaults());

        return http.build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Thay bằng origin đã được duyệt trong production.
        cors.setAllowedOrigins(
                List.of("https://app.example.test"));
        cors.setAllowedMethods(
                List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build());
    }
}
~~~

**Các điểm cần hiểu:**

1. **cors(cors -> cors.configurationSource(...))** tích hợp CORS vào Spring Security để preflight không bị chặn vì thiếu session.
2. **csrf(withDefaults())** giữ CSRF protection cho POST/PUT/PATCH/DELETE và login/logout theo policy mặc định.
3. **requestMatchers("/api/**").authenticated()** bắt buộc session authentication trước khi API trả dữ liệu.
4. **formLogin(withDefaults())** bật login page mặc định, CSRF token được tạo/phát qua form integration.
5. **defaultAuthenticationEntryPointFor** trả **401** cho API chưa xác thực, không tự đưa AJAX client tới HTML /login.
6. CORS chỉ áp dụng **/api/** và allowlist đúng một frontend origin; không bật cross-origin login cho demo.
7. **allowCredentials(true)** không đồng nghĩa cho mọi user truy cập; session authentication vẫn cần.
8. CORS methods và headers có scope tối thiểu cho GET/POST demo; nếu thêm PATCH/DELETE phải cập nhật policy có chủ đích.
9. **student/demo-pass** chỉ là test account. Production dùng identity provider và credential storage phù hợp; không hardcode password vào repo.
10. Đừng đổi toàn bộ security config thành **csrf.disable()** để tránh lỗi 403 do thiếu token.

### 7.5. Controller phục vụ trang

**src/main/java/com/example/websecurity/PageController.java**

~~~java
package com.example.websecurity;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {
    @GetMapping("/")
    public String index() {
        return "index";
    }
}
~~~

### 7.6. Controller API

**src/main/java/com/example/websecurity/NotesController.java**

~~~java
package com.example.websecurity;

import java.security.Principal;
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class NotesController {

    @GetMapping("/me")
    public ResponseEntity<Map<String, String>> me(
            Principal principal) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of("username", principal.getName()));
    }

    @PostMapping("/notes")
    public ResponseEntity<Map<String, String>> save(
            Principal principal,
            @RequestParam String note) {

        // Không ghi DB; chỉ trả lại dữ liệu để demo.
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                    "savedBy", principal.getName(),
                    "note", note));
    }
}
~~~

**ResponseEntity.noStore()** được dùng thông qua **CacheControl.noStore()** để response thông tin riêng không bị cache theo HTTP cache. Controller demo không thực thi nghiệp vụ ghi dữ liệu thật; trong hệ thống sản xuất phải có authorization theo resource, validation, transaction, chống XSS và logging an toàn.

### 7.7. HTML Thymeleaf tự tích hợp CSRF

**src/main/resources/templates/index.html**

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Session + CORS + CSRF demo</title>
</head>
<body>
  <h1>Demo bảo mật phiên</h1>
  <p>Đăng nhập ở /login: student / demo-pass.</p>

  <form th:action="@{/api/notes}" method="post">
    <label for="note">Ghi chú</label>
    <input id="note" name="note" value="hello" required>
    <button type="submit">Gửi POST</button>
  </form>

  <form th:action="@{/logout}" method="post">
    <button type="submit">Đăng xuất</button>
  </form>
</body>
</html>
~~~

Với Thymeleaf + Spring MVC/Spring Security, **th:action** trên form có unsafe method tích hợp **RequestDataValueProcessor** để thêm hidden CSRF input. Khi xem HTML đã render, form POST cần có token thực tế; bạn **không nên hardcode** một token vào template. Nếu dùng template engine không tích hợp, phải render hidden parameter bằng một cơ chế lấy token do Spring Security cung cấp.

Trang / là public ở demo để xem form. Nếu chưa đăng nhập, POST /api/notes vẫn cần authentication và CSRF; phải login đúng workflow trước khi sử dụng.

### 7.8. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: cors-csrf-cookie-demo

server:
  port: 8080
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        same-site: lax
~~~

Đây là cấu hình **HTTP localhost cho lab**. Production cần HTTPS và cookie Secure theo security policy. Session timeout 30 phút không đồng nghĩa cookie bị xóa sau đúng 30 phút; nếu cookie ID cũ được gửi sau server idle timeout, API phải xử lý session không còn hợp lệ.

### 7.9. Chạy project

Linux/macOS:

~~~bash
./mvnw clean package
java -jar target/cors-csrf-cookie-demo-0.0.1-SNAPSHOT.jar
~~~

Windows:

~~~text
mvnw.cmd clean package
java -jar target/cors-csrf-cookie-demo-0.0.1-SNAPSHOT.jar
~~~

Nếu project chưa có Maven wrapper, dùng **mvn clean package** hoặc **mvn spring-boot:run**. Vào **http://localhost:8080/login** bằng browser, đăng nhập **student/demo-pass**, sau đó tới **http://localhost:8080/** và bấm nút submit. POST mẫu có CSRF token nên được xử lý; browser sẽ hiển thị JSON kết quả.

**Đừng hiểu nhầm** domain https://app.example.test trong CORS config là frontend đã được tạo. Đây chỉ là allowlist minh họa; để test trình duyệt ở http://localhost:5173 phải cập nhật đúng allowed origin local đó, không dùng wildcard.

## 8. Kiểm thử bằng Spring Security Test và MockMvc

**MockMvc** kiểm tra filter chain và controller mà không cần browser thật. Nó rất phù hợp cho CORS policy, CSRF token validation và authentication entry point. Tuy nhiên nó không áp dụng cookie restrictions của Chrome/Firefox thật (SameSite, Secure, third-party blocking) và không chứng minh proxy HTTPS đã cấu hình đúng.

### 8.1. Test class hoàn chỉnh

**src/test/java/com/example/websecurity/WebSecurityIntegrationTest.java**

~~~java
package com.example.websecurity;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WebSecurityIntegrationTest {
    @Autowired
    MockMvc mvc;

    @Test
    void apiRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/me")
                .header(HttpHeaders.ACCEPT, "application/json"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void preflightWithoutCookieAllowed() throws Exception {
        mvc.perform(options("/api/notes")
                .header(HttpHeaders.ORIGIN,
                        "https://app.example.test")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                        "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Access-Control-Allow-Origin",
                    "https://app.example.test"))
            .andExpect(header().string(
                    "Access-Control-Allow-Credentials", "true"));
    }

    @Test
    void untrustedOriginPreflightRejected() throws Exception {
        mvc.perform(options("/api/notes")
                .header(HttpHeaders.ORIGIN,
                        "https://evil.example.test")
                .header("Access-Control-Request-Method", "POST"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithoutCsrfForbiddenEvenWhenAuthenticated()
            throws Exception {
        mvc.perform(post("/api/notes")
                .with(user("student"))
                .param("note", "hello"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfAndUserSucceeds() throws Exception {
        mvc.perform(post("/api/notes")
                .with(user("student"))
                .with(csrf())
                .param("note", "hello"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.savedBy").value("student"))
            .andExpect(jsonPath("$.note").value("hello"));
    }

    @Test
    void loginSessionCanAccessApi() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        HttpSession raw = login.getRequest().getSession(false);
        assertNotNull(raw);
        MockHttpSession session = (MockHttpSession) raw;

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("student"));
    }
}
~~~

Các test xác nhận:

- **API 401** khi chưa xác thực, không để fetch nhận HTML login 200.
- **OPTIONS preflight không cookie** được CORS xử lý trước authentication.
- **Origin độc hại** không được CORS cho phép.
- **POST có authenticated principal nhưng thiếu CSRF token** nhận 403.
- **POST có principal và CSRF token** trả 200 JSON.
- **Login form với CSRF** tạo session và request kế tiếp dùng được identity.

Để dùng **with(csrf())** và **with(user(...))**, cần dependency test **spring-security-test**. Chạy:

~~~bash
./mvnw test
~~~

**MockMvc pass không chứng minh browser cookie được gửi cross-site**. Thực hiện thêm browser integration tests với frontend/backend thực và DevTools Network, đặc biệt khi HTTPS kết thúc tại proxy/ingress.

## 9. Test CORS bằng curl

### 9.1. OPTIONS origin được chấp nhận

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
~~~

Kỳ vọng **200** và headers **Access-Control-Allow-Origin: https://app.example.test**, **Access-Control-Allow-Credentials: true** cùng allow-methods/headers thích hợp. Đây là kiểm tra response server; **curl không phải browser CORS enforcement**.

### 9.2. OPTIONS origin lạ

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H 'Origin: https://evil.example.test' \
  -H 'Access-Control-Request-Method: POST'
~~~

Với CorsFilter trong demo, origin lạ thường bị trả **403 Invalid CORS request**. Không đổi whitelist thành wildcard để request này thành công.

### 9.3. GET API không login

~~~bash
curl -i -H 'Accept: application/json' \
  -H 'Origin: https://app.example.test' \
  http://localhost:8080/api/me
~~~

Kỳ vọng **401** dù origin được phép. Điều này chứng minh CORS allowlist **không cấp authentication**.

### 9.4. POST /login thiếu CSRF

~~~bash
curl -i -X POST http://localhost:8080/login \
  -d 'username=student&password=demo-pass'
~~~

Có thể nhận **403** vì chưa gửi CSRF token, dù thông tin demo account đúng. Muốn dùng curl để đăng nhập đầy đủ, phải GET trang login để lấy hidden token và lưu cookie bằng cookie jar trước khi POST. Dùng browser và kiểm tra form sẽ đơn giản hơn. **Đừng dùng csrf.disable() để sửa một bài thử thiếu token.**

## 10. API 401, 403 và lỗi browser CORS khác nhau

| Kết quả | Ý nghĩa thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| **401 Unauthorized** | Chưa xác thực, cookie/session thiếu hoặc hết hạn | Cookie gửi chưa, login/session store, entry point. |
| **403 do CSRF** | Unsafe request thiếu hoặc sai token | Hidden field/header, token lifecycle, request handler. |
| **403 do Authorization** | Đã xác thực nhưng không có quyền | Principal, role, tenant, access rules. |
| **403 Invalid CORS request** | Origin/method/header không được phép | CorsConfigurationSource, preflight headers. |
| **Browser CORS error** | JavaScript không được đọc response theo CORS policy | DevTools Origin/Allow-Origin/Credentials; request có thể vẫn đã tới backend. |
| **302 HTML login trong fetch** | Form login entry point đang redirect API | Tách API 401 với UI navigation redirect. |
| **200 HTML sau redirect** | Fetch đã theo redirect đến trang login | Kiểm tra response URL/Content-Type và security entry point. |
| **No Cookie request** | credentials mode, SameSite, Secure, Domain/Path hoặc browser policy | Network tab Set-Cookie/Cookie; không mặc định lỗi CORS. |

**Không tự động retry POST khi thấy 403 hoặc 401** vì có thể tạo side effect kép nếu client không biết request trước đã thành công hay chưa. Thiết kế idempotency key/transaction cho hành động quan trọng.

## 11. SPA cross-origin: cách lấy CSRF token đúng

### 11.1. Vì sao SPA cần xử lý riêng?

Form Thymeleaf trong demo được server render, dùng **RequestDataValueProcessor** để đưa CSRF hidden input vào form. Một frontend JavaScript ở origin khác không có form do backend render; nó phải có **cơ chế nhận token hợp lệ** và gửi token trong custom HTTP header.

Ví dụ request từ SPA **khi đã có token**:

~~~javascript
async function createNote(csrfToken, note) {
  const res = await fetch(
    "https://api.example.test/api/notes",
    {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRF-TOKEN": csrfToken
      },
      body: new URLSearchParams({note}).toString()
    }
  );

  if (res.status === 401) {
    throw new Error("Login required");
  }
  if (res.status === 403) {
    throw new Error("Forbidden or invalid CSRF token");
  }
  if (!res.ok) {
    throw new Error("HTTP request failed");
  }
  return res.json();
}
~~~

**Code trên không phát sinh csrfToken**. Token phải được backend cung cấp qua một flow có kiểm soát như trang HTML được render, endpoint riêng hay cookie repository phù hợp; không hardcode trong JavaScript bundle hoặc query string.

### 11.2. CookieCsrfTokenRepository và XSRF-TOKEN

Spring Security cung cấp **CookieCsrfTokenRepository**, thường dùng trong SPA theo pattern **XSRF-TOKEN cookie** và header **X-XSRF-TOKEN**. Với **CookieCsrfTokenRepository.withHttpOnlyFalse()**, JavaScript có thể đọc CSRF cookie khi cookie thuộc origin/scope hợp lệ. **Đó không phải session cookie JSESSIONID.** Session cookie vẫn nên HttpOnly.

Tuy nhiên, từ Spring Security 6 có một số điểm cần xử lý:

- **Deferred CSRF tokens:** token không nhất thiết được tạo ở mọi GET nếu code không yêu cầu.
- **BREACH masking:** token được đưa vào form/request attribute có thể được mã hóa/che ngẫu nhiên; raw token từ cookie khác masked form token.
- **CsrfTokenRequestHandler:** SPA cần xử lý raw token trong header khác với cách form submit token masked. Tài liệu mô tả **SpaCsrfTokenRequestHandler** cho trường hợp này.
- **CSRF token rotation:** sau authentication/logout, token cũ có thể bị clear; SPA phải lấy token mới trước POST tiếp.
- **403 không luôn là token lỗi:** có thể do thiếu authorization; đừng retry vô hạn.

**Không lấy một snippet từ Spring Security 7 rồi áp dụng nguyên vào Security 6**: API/DSL đã có thay đổi. Hãy làm theo hướng dẫn Spring Security dành cho version đang chạy và viết test token sau login/logout.

### 11.3. Frontend JS khác host không đọc được host-only cookie API

Nếu JavaScript chạy trên **app.example.test** mà CSRF cookie là **host-only** của **api.example.test**, trình duyệt có thể gửi cookie API khi fetch, nhưng **document.cookie ở app.example.test không đọc được cookie của api.example.test**. Hai site có thể cùng eTLD+1 nhưng cookie scope vẫn gắn với host.

Những phương án đáng cân nhắc:

1. **Same-origin BFF/reverse proxy:** frontend và API đi qua một origin, đơn giản hóa cookie/token handling.
2. **Endpoint cấp token** trên API: trả token bằng JSON/header có CORS allowlist chặt, gắn với session và không cache public.
3. **Cookie Domain chung có kiểm soát:** đánh giá kỹ subdomain trust, token leakage và nguy cơ cookie injection; không mở rộng Domain theo quán tính.
4. **Kiến trúc token khác:** nếu API thực sự stateless và không dùng ambient cookies, threat model CSRF có thể khác, nhưng cần kiểm tra mọi auth mechanism.

### 11.4. SameSite=None không phải giải pháp cho mọi SPA

Khi frontend và API **cross-site thật sự**, SameSite=None; Secure có thể cần để browser gửi cookie trong credentialed fetch. Nhưng nhiều browser hạn chế third-party cookie, và cấu hình None làm giảm lớp phòng vệ SameSite. Nếu có thể dùng BFF/same-origin endpoint, cấu trúc đó thường ổn định hơn. Không tắt CSRF chỉ vì đã cấu hình SameSite=None.

## 12. Khi nào không cần CSRF token?

Một API **thực sự stateless**, mọi request xác thực bằng bearer token do client chủ động đặt vào Authorization header, không dùng cookie session, HTTP Basic hay hình thức ambient browser credential, có thể có threat model không yêu cầu synchronizer CSRF token cho một số route.

Nhưng **không có quy tắc "REST API thì tắt CSRF"**. Nếu API vẫn có cookie login, form login, logout hoặc session, các unsafe routes vẫn có nguy cơ CSRF. Khi miễn CSRF cho một nhóm endpoint, dùng scope chính xác như **csrf.ignoringRequestMatchers(...)** với lý do được ghi rõ và review security, thay vì disable toàn bộ chain. CORS và authorization vẫn phải giữ.

Một endpoint upload/file delete dùng token rõ ràng cũng cần đánh giá request replay, idempotency, content type, session binding và XSS; CSRF không phải lớp bảo vệ duy nhất.

## 13. Ảnh hưởng của reverse proxy, HTTPS và Spring Session

### 13.1. HTTPS kết thúc ở proxy

Nếu browser đến reverse proxy qua HTTPS nhưng proxy gửi HTTP nội bộ vào Spring Boot, cookie Secure và redirect URLs cần cấu hình đúng ở edge/Boot. Server chỉ nên tin **Forwarded/X-Forwarded-Proto** từ proxy được kiểm soát, không chấp nhận header giả từ Internet.

Thử trực tiếp origin lẫn URL qua proxy; so sánh **Set-Cookie, Cookie, Location, Scheme, Host, Port** và Origin. Một cấu hình chạy localhost nhưng fail trên staging có thể do browser thấy cross-site hoặc proxy đổi scheme.

### 13.2. Session nhiều replicas

Nếu mỗi instance giữ local HttpSession và load balancer gửi request tới replica khác, user có thể nhận 401 dù cookie vẫn tồn tại. Dùng **Spring Session Redis/JDBC** hoặc chiến lược sticky routing có cân nhắc failover. Khi có Spring Session, cookie có thể là **SESSION** thay vì JSESSIONID. CSRF token repository và session store phải có tính nhất quán để các POST tới replica khác không nhận 403 ngẫu nhiên.

### 13.3. Cookie expiry khác session expiry

Session cookie có thể còn sau khi server xóa HttpSession; cookie stale không có authentication. HttpSession có thể còn dù client đã xóa cookie nhưng không có ID để tra lại. Cấu hình **server.servlet.session.timeout** và cookie Max-Age theo hai mục tiêu khác nhau, không nhầm cả hai là một deadline tuyệt đối.

### 13.4. Multi-tab và logout

User có thể logout ở một tab nhưng tab khác vẫn giữ CSRF token trước đó. Request unsafe sau logout cần thất bại và UI nên yêu cầu đăng nhập lại. Sau login, đừng tự động gửi lại POST có side effect; refresh CSRF token, kiểm tra idempotency và điều hướng an toàn.

## 14. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Xử lý |
| --- | --- | --- |
| OPTIONS trả 401 | CORS chạy sau authentication; preflight không có cookie | Tích hợp http.cors và test OPTIONS không cookie. |
| Allow-Origin là wildcard với credentials=true | Cấu hình sai quy tắc credentialed CORS | Whitelist origin cụ thể. |
| GET thành công nhưng POST 403 | Thiếu hoặc stale CSRF token | Kiểm tra form hidden/header, token repository và lifecycle. |
| Browser CORS error, backend có side effect | Simple request đã được gửi, JS bị cấm đọc response | CSRF + authorization trên server, không dựa vào CORS. |
| Cookie không gửi | fetch credentials, SameSite, Secure, Domain/Path, third-party blocking | Xem Network tab thay vì tăng CORS origins. |
| Login đúng password nhưng 403 | POST /login thiếu CSRF | Dùng form có token hoặc flow cấp token hợp lệ. |
| Session mất sau redirect | Cookie Path/Domain, HTTP↔HTTPS hoặc reverse proxy | So URL thực tế và Set-Cookie. |
| Bật SameSite=None vẫn không gửi cookie | Secure thiếu hoặc browser chặn third-party cookie | Dùng HTTPS; cân nhắc BFF. |
| 403 sau login trong SPA | Token bị clear/rotate, deferred/masked token | Refresh token và request handler đúng Security 6. |
| 403 khi gọi endpoint từ curl không có Origin | Authorization hoặc CSRF, không phải CORS | Kiểm tra Principal, roles, token. |
| API nhận HTML login thay JSON | Form login redirect được áp dụng cho API | Tách API 401 entry point với UI redirect. |
| Multi-replica lúc 200 lúc 401/403 | Local sessions/token không chia sẻ | Shared session store và consistent policy. |
| Cookie HttpOnly nhưng vẫn bị CSRF | Cookie tự gửi, HttpOnly chỉ cấm JS đọc | Giữ CSRF token và SameSite defense-in-depth. |
| Lộ dữ liệu ở CDN/browser cache | Cache-Control/Vary sai | no-store cho dữ liệu nhạy cảm, cache key/authorization đúng. |
| CSRF disabled để fix mọi POST | Bỏ qua threat model cookie | Khôi phục CSRF, thiết kế token delivery phù hợp. |

## 15. Kiểm thử với browser và production checklist

### 15.1. Những gì phải xem trong DevTools

1. **Origin, Request URL**: xác định đúng scheme, host, port; phân biệt site.
2. **OPTIONS**: method/header được phép, status, Allow-Origin và Allow-Credentials, có bị 401/403 không.
3. **Actual Cookie**: browser có gửi JSESSIONID/SESSION không, cookie host-only hay Domain, Path, SameSite, Secure.
4. **Set-Cookie**: browser có chặn cookie vì SameSite=None thiếu Secure, third-party restriction hoặc domain sai không.
5. **Request CSRF header/form field**: token có tồn tại, đúng tên, đúng session và còn hiệu lực không.
6. **Response code**: 401 authentication, 403 có thể CSRF/authorization, CORS browser error là thiếu quyền đọc.
7. **Redirect**: fetch có bị 302 đến HTML /login không.
8. **Cache-Control**: dữ liệu riêng có no-store không.
9. **Network topology**: TLS termination, forwarded headers, proxy/CDN và instances.
10. **Multi-tab state**: logout/login lại có cập nhật token và user state không.

Không log hoặc dán nguyên session cookie, CSRF token, password hay bearer token vào bug report. Dùng request ID riêng, che dữ liệu nhạy cảm và kiểm soát retention.

### 15.2. Checklist trước khi deploy

- [ ] CORS cho đúng **origin cụ thể**, không kết hợp wildcard với allowCredentials=true.
- [ ] **http.cors(...)** xử lý preflight trước authentication/session filter.
- [ ] API path, allowedMethods và allowedHeaders được giới hạn đúng nhu cầu.
- [ ] Các unsafe methods dùng cookie session đều giữ CSRF protection hoặc có threat model miễn rõ ràng.
- [ ] Form login/logout có token, không dùng GET để thay đổi trạng thái.
- [ ] API không login trả **401**, không trả HTML 200 do redirect ngoài hợp đồng.
- [ ] User đã login vẫn bị **403** nếu thiếu quyền; CSRF token không thay authorization.
- [ ] Session cookie có **HttpOnly, Secure trên HTTPS, SameSite và Path/Domain** phù hợp.
- [ ] Không nhầm SameSite với CORS, không tự mở Domain=.example.test.
- [ ] SPA có cơ chế lấy/refresh CSRF token và xử lý BREACH/deferred token của Spring Security 6.
- [ ] Cookie host-only của API không bị JS frontend origin khác đọc nhầm theo giả định.
- [ ] Cross-site cookie cần None/Secure được đánh giá với third-party cookie restrictions.
- [ ] Data riêng không nằm trong public shared cache; có Cache-Control no-store và Vary đúng.
- [ ] Reverse proxy chỉ tin forwarded headers từ nguồn tin cậy.
- [ ] Cluster/session store và CSRF token repository hoạt động nhất quán giữa replicas.
- [ ] MockMvc test 401, CORS preflight, forbidden origin, CSRF missing và CSRF success.
- [ ] Browser staging test cookie delivery, logout, timeout, multi-tab và HTTPS thực.
- [ ] Metrics/log không tiết lộ session ID, CSRF token hay credentials.

## 16. Câu hỏi tự kiểm tra

**1. app.example.test gọi api.example.test là cross-origin không?** Có vì hostname khác, dù có thể cùng site.

**2. CORS cho phép origin có nghĩa user không cần đăng nhập?** Không. CORS là browser read policy; authentication/authorization độc lập.

**3. Khi credentials=true có thể trả Access-Control-Allow-Origin: * không?** Không cho credentialed response; chọn origin cụ thể.

**4. OPTIONS preflight có bắt buộc có session cookie không?** Không; thường không mang cookie và phải được CORS xử lý trước security authentication.

**5. Website khác bị CORS chặn có thể gây POST side effect không?** Có thể, ví dụ qua simple form; phải dựa vào CSRF token và authorization.

**6. HttpOnly có loại bỏ nguy cơ CSRF không?** Không. Cookie vẫn tự gửi dù JavaScript không đọc được giá trị.

**7. Lax có nghĩa chỉ gửi cookie khi same-origin?** Không. Lax quan tâm site, không phải origin.

**8. Vì sao POST /login trả 403 dù password đúng?** Có thể thiếu CSRF token vì Spring Security bảo vệ login POST.

**9. Vì sao SPA không đọc được XSRF-TOKEN host-only tại api.example.test từ app.example.test?** JS khác host không có quyền đọc cookie đó; cần token endpoint hoặc same-origin architecture.

**10. Khi nào có thể đánh giá tắt CSRF cho API?** Khi API thật sự stateless và không dựa vào credential được browser tự gửi, với threat model và phạm vi route rõ.

## 17. Tài liệu tham khảo

1. [Spring Security — CORS (Servlet)](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): CORS xử lý trước security, preflight không cookie, CorsConfigurationSource.
2. [Spring Security — CSRF (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): token pattern, HTML forms, JavaScript SPA, deferred CSRF, BREACH và tests.
3. [Spring Security — CSRF MockMvc Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): with(csrf()) và positive/negative tests.
4. [Spring Boot 3.3 — Servlet Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): SameSite cookie và embedded servlet configuration.
5. [Spring Boot 3.3 — Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): server.servlet.session.cookie.*, timeout.
6. [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS): cross-origin, preflight, credentials.
7. [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie): HttpOnly, Secure, SameSite, Domain, Path.
8. [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF defenses và giới hạn của SameSite.

**Tóm kết:** **CORS** kiểm soát quyền JavaScript đọc response cross-origin; **cookie phiên** mang session ID mà browser có thể tự gửi; **CSRF protection** bảo vệ unsafe requests khỏi sự tự động đó; **authorization** quyết định user có quyền thao tác. Trong Spring Boot, phải tích hợp CORS trước security, giữ CSRF cho flow cookie login, đặt HttpOnly/Secure/SameSite theo site topology và kiểm chứng trên browser thật, không chỉ MockMvc hoặc curl.