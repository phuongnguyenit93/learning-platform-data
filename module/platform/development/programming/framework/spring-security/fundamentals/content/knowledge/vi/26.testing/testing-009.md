# Kiểm thử CSRF, CORS và các header bảo mật trong Spring Security

> **Phạm vi:** Spring Security fundamentals — nhóm **Kiểm thử**. Bài học dùng Java 17+, Spring Boot 3.3.x, Spring Security 6.x, JUnit 5, Spring Security Test và **MockMvc (Servlet/Spring MVC)**. Trọng tâm là chứng minh cả trường hợp được chấp nhận lẫn bị từ chối, phân biệt vai trò CSRF/CORS/security headers, kiểm tra mặc định và tùy biến. WebFlux dùng `WebTestClient» và `SecurityWebFilterChain»; các điểm khác biệt được giải thích ở cuối.

## 1. Ba cơ chế bảo vệ ba vấn đề khác nhau

Một test “HTTP 200” đơn lẻ không đủ để xác minh các biện pháp bảo vệ của browser. Cần hiểu mỗi cơ chế dùng tín hiệu nào và kẻ tấn công nào bị hạn chế:

| Cơ chế | Nó ngăn hoặc giảm rủi ro gì? | Đầu vào/cấu hình | Điều cần kiểm thử |
| --- | --- | --- | --- |
| **CSRF** (Cross-Site Request Forgery) | Một trang web khác khiến browser của nạn nhân thực hiện hành động đổi trạng thái bằng credential tự động gửi (cookie/session; có thể cả HTTP Basic tùy browser) | CSRF token, token repository, request handler, matcher cho phương thức cần bảo vệ | POST thiếu/sai token bị từ chối; token hợp lệ đi tiếp; CSRF không thay thế authentication |
| **CORS** (Cross-Origin Resource Sharing) | Quy định trình duyệt được cho phép JavaScript từ origin nào đọc response của API, và những cross-origin request nào cần preflight | `Origin», `Access-Control-Request-Method», `Access-Control-Request-Headers»; policy allowed origins/methods/headers/credentials | Preflight đúng origin/method/header được cho phép; origin sai bị từ chối; response có CORS header phù hợp |
| **Security response headers** | Hướng dẫn browser hạn chế MIME sniffing, framing/clickjacking, cache dữ liệu nhạy cảm, nguồn script/style, referer, kết nối HTTP | `X-Content-Type-Options», `X-Frame-Options», `Cache-Control», `Content-Security-Policy», `Referrer-Policy», `Strict-Transport-Security»... | Header mặc định có mặt; CSP/Referrer tùy biến đúng; HSTS chỉ xuất hiện khi request được xem là HTTPS |

**Ba điều không được đánh đồng:**

1. **CORS không phải authentication/authorization.** Request từ curl hoặc server-to-server có thể gửi bất kỳ `Origin» nào hoặc không gửi `Origin»; policy CORS chủ yếu được browser thực thi, không thay thế JWT/session/role.
2. **CORS không thay thế CSRF.** Một origin được phép đọc API không có nghĩa POST của browser đã có CSRF token hợp lệ. Ngược lại, thiếu CORS header không nhất thiết ngăn browser **gửi** một số loại request gây đổi trạng thái; nó có thể chỉ ngăn script đọc response.
3. **Header đúng không chứng minh browser đã áp dụng mọi chính sách.** MockMvc kiểm tra response do server sinh ra. Kiểm thử CSP thực tế, cookie, redirect, cache hay proxy HTTPS có thể cần thêm browser/E2E test.

## 2. CSRF: trường hợp hợp lệ, thiếu token và token sai

### 2.1 Khi nào Spring Security yêu cầu token?

Trong ứng dụng Servlet, bảo vệ CSRF được bật theo mặc định khi cấu hình Spring Security thông thường. Cơ chế thường bảo vệ các phương thức **không an toàn** như POST, PUT, PATCH, DELETE. Các phương thức được xem là an toàn gồm GET, HEAD, OPTIONS, TRACE; chúng **không được tạo tác dụng phụ thay đổi dữ liệu**, vì browser/proxy/cache có thể tự động gọi.

Luồng điển hình:

```text
Browser thực hiện POST /api/notes
     |
     +--> Có session/cookie/credential theo cơ chế client
     |
     +--> CsrfFilter lấy token kỳ vọng từ CsrfTokenRepository
     |                     |
     |               đọc token request
     |               (form field/header theo cấu hình)
     |
     +--> Token thiếu hoặc không khớp => AccessDeniedException
     |                                  => thường HTTP 403
     |
     +--> Token hợp lệ => tiếp tục các filter/authorization
                                |
                                +--> chưa authentication => có thể 401 / redirect
                                +--> thiếu quyền => 403
                                +--> đủ quyền => vào controller
```

**CSRF token hợp lệ không tự động đăng nhập người dùng.** Người dùng có thể gửi token CSRF đúng nhưng chưa có authentication; sau bước CSRF, URL vẫn có thể từ chối do yêu cầu đăng nhập. Ngược lại, một user đã đăng nhập nhưng POST không có token vẫn có thể nhận 403 **trước** khi đến controller.

### 2.2 CSRF RequestPostProcessor trong Spring Security Test

Các helper quan trọng:

```java
// Fragment MockMvc; mvc là MockMvc đã gắn Spring Security.
mvc.perform(post("/api/notes").with(csrf()));                    // token hợp lệ dạng parameter
mvc.perform(post("/api/notes").with(csrf().asHeader()));         // token hợp lệ dạng header
mvc.perform(post("/api/notes").with(csrf().useInvalidToken()));  // token sai
mvc.perform(post("/api/notes"));                                 // không cung cấp token
```

`csrf()» nằm trong `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors». Helper tạo token phù hợp với môi trường test; nó **không** thay thế việc kiểm tra chính sách tạo, xoay vòng, lưu/đọc token và tích hợp JavaScript ngoài đời.

**Định nghĩa kết quả kỳ vọng phải bao gồm trạng thái xác thực.** Nếu test POST với `@WithMockUser» hoặc `.with(user(...))», bạn đang cô lập kiểm thử CSRF khỏi lỗi anonymous. Nếu không cấp user và vẫn mong 200 chỉ nhờ token CSRF, bài test bị hiểu sai.

### 2.3 Những tình huống bắt buộc

| Test | Authentication | CSRF token | Kỳ vọng với endpoint POST cần đăng nhập |
| --- | --- | --- | --- |
| POST có user, không token | Có | Thiếu | **403**, controller không được thực thi |
| POST có user, token sai | Có | Sai | **403** |
| POST có user, token đúng trong form parameter | Có | Hợp lệ | Đi tiếp: **200/201** nếu controller thành công |
| POST có user, token đúng trong header | Có | Hợp lệ | Đi tiếp: **200/201** |
| POST anonymous, token đúng | Không | Hợp lệ | **401** với HTTP Basic; có thể redirect nếu form login |
| GET endpoint chỉ đọc | Tùy URL | Không cần | Không nên bị chặn chỉ vì thiếu CSRF |

Nếu một endpoint POST được cấu hình `csrf.ignoringRequestMatchers(...)», test phải phản ánh **quyết định có chủ đích** ấy; không tự tắt CSRF chỉ để test xanh. Đặc biệt với cookie-based session và browser tự gửi cookie, CSRF vẫn cần đánh giá đầy đủ.

## 3. CORS: hiểu preflight và simple/actual request

### 3.1 Origin chính xác gồm những gì?

Một **origin** là tổ hợp *scheme + host + port*. `https://portal.example.test» khác `http://portal.example.test», khác `https://api.example.test» và khác cùng host trên port khác. CORS là chính sách **cross-origin**; đừng so sánh mỗi hostname rồi cấp quyền bừa bãi.

Một preflight có hình dạng:

```http
OPTIONS /api/notes HTTP/1.1
Origin: https://portal.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Browser thường **không gửi cookie/session** trong preflight. CORS phải được xử lý đủ sớm, trước khi authentication filter chặn OPTIONS vì anonymous. Trong Spring Security Servlet, có thể cấu hình `CorsConfigurationSource» và `http.cors(...)», hoặc tích hợp chính sách CORS từ Spring MVC theo cách phù hợp.

Khi origin/method/header được phép, response có thể chứa:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://portal.example.test
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Allow-Credentials: true
```

Danh sách và thứ tự header thực tế tùy cấu hình/framework. Test nên kiểm tra **giá trị quan trọng** và có thể dùng matcher “chứa POST” thay vì ràng buộc thứ tự cả chuỗi. `Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers» cũng có thể được thêm để cache phân biệt các request; nên kiểm tra khi cache/gateway là phạm vi triển khai.

### 3.2 Preflight khác actual cross-origin request

- **Preflight:** OPTIONS hỏi trước chính sách origin, method, headers; không có credential của user hoặc CSRF token và không chạy nghiệp vụ POST.
- **Actual request:** GET/POST thực sự của browser; CORS filter đưa các `Access-Control-Allow-...» phù hợp vào response và chuyển tiếp xử lý, nhưng authentication/authorization/CSRF vẫn có hiệu lực.
- **Request không có Origin:** không phải CORS request; server vẫn xử lý authentication/CSRF bình thường. Không nên mặc định kỳ vọng `Access-Control-Allow-Origin» trên mọi response.

Khi `allowCredentials=true», không dùng wildcard `*» cho `Access-Control-Allow-Origin» với trình duyệt; hãy khai báo origin chính xác hoặc pattern được thiết kế phù hợp. Không dùng `allowedOriginPatterns("*")» cùng credential để vô tình mở đọc API cho mọi website.

### 3.3 Ma trận CORS cần test

| Test | Origin | Method | Preflight request headers | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Preflight được phép | `https://portal.example.test» | POST | content-type, x-csrf-token | 200; allow-origin đúng; allow-methods chứa POST |
| Preflight sai origin | `https://evil.example.test» | POST | content-type | 403 hoặc kết quả bị CORS processor từ chối; không có allow-origin tin cậy |
| Preflight method ngoài whitelist | Origin hợp lệ | DELETE | content-type | Không được browser cho phép thực hiện cross-origin |
| Preflight yêu cầu header cấm | Origin hợp lệ | POST | x-secret-admin | Không chấp thuận header này |
| Actual GET từ origin được phép | Origin hợp lệ | GET | Không phải preflight | CORS headers đúng **và** yêu cầu quyền vẫn được áp dụng |
| Actual POST origin được phép nhưng không CSRF | Origin hợp lệ | POST | Không có token | Vẫn 403 do CSRF |
| Request cùng origin/không Origin | Không có | GET | Không | Không cần CORS allow-origin |

**Lưu ý:** status lỗi CORS từ bộ xử lý mặc định của Spring thường là 403, nhưng mục tiêu chính là browser không nhận được header cho phép origin/method/header bị cấm. Không dựa **chỉ** vào status để tuyên bố CORS an toàn.

## 4. Các security response headers cần xác minh

Spring Security cung cấp nhiều header mặc định và cho phép tùy biến thêm. Hãy kiểm tra các giá trị thuộc **phiên bản và cấu hình thực tế**; CSP, Referrer-Policy, Permissions-Policy không được tự động có mặt chỉ vì đã dùng starter security.

| Header | Ý nghĩa | Kỳ vọng thường gặp |
| --- | --- | --- |
| `X-Content-Type-Options» | Hạn chế browser đoán MIME type | `nosniff» |
| `X-Frame-Options» | Chống một số kiểu clickjacking bằng framing | `DENY» mặc định; có thể chọn `SAMEORIGIN» |
| `Cache-Control» | Giảm khả năng cache dữ liệu nhạy cảm | Giá trị có `no-cache» và `no-store» với response cần bảo vệ |
| `Pragma», `Expires» | Khả năng tương thích cơ chế cache cũ | Thường có khi bật mặc định cache-control headers |
| `Strict-Transport-Security» (HSTS) | Báo browser ghi nhớ chỉ dùng HTTPS | Chỉ ghi trên request được ứng dụng xem là **HTTPS** |
| `Content-Security-Policy» (CSP) | Giới hạn nguồn resource/script/iframe theo directive | **Phải cấu hình rõ** cho ứng dụng; không giả định có mặc định |
| `Referrer-Policy» | Giới hạn nội dung Referer chuyển sang trang khác | Không có mặc định chung bắt buộc; ví dụ chủ động đặt `no-referrer» |
| `Permissions-Policy» | Giới hạn browser features (camera, location...) | Cần thiết kế và kiểm tra riêng nếu ứng dụng sử dụng |
| `X-XSS-Protection» | Header lịch sử cho browser XSS auditor | Không xem là thay thế CSP/escaping; browser hiện đại thường không dùng |

### 4.1 HSTS và HTTPS trong test

Một request MockMvc thông thường được coi là HTTP. Header **`Strict-Transport-Security»** thường **không** được Spring Security thêm nếu `request.isSecure()» là false. Để kiểm tra HSTS, dùng:

```java
mvc.perform(get("/api/public").secure(true))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Strict-Transport-Security", containsString("max-age=")));
```

Đoạn này là fragment Java với `MockMvc», `get», `header», `containsString» đã import. `secure(true)» **mô phỏng** HTTPS ở servlet request; nó không kiểm thử TLS handshake, certificate hoặc proxy ngoài đời. Khi TLS terminate ở load balancer, ứng dụng phải có cấu hình proxy/Forwarded headers **chỉ tin cậy nguồn proxy**; không tin một `X-Forwarded-Proto» do client bất kỳ tự gửi.

### 4.2 CSP là chính sách phải định nghĩa theo ứng dụng

Ví dụ dùng `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'» để dễ test. CSP này mang ý nghĩa browser và cần phù hợp tài nguyên frontend thật. API thuần JSON có thể không cần cùng CSP chi tiết với trang HTML; không copy một CSP demo lên website có inline script hoặc CDN rồi coi lỗi browser là bug bảo mật của Spring.

`X-Frame-Options: DENY» và directive CSP `frame-ancestors 'none'» đều giúp hạn chế framing; test response header không chứng minh toàn bộ clickjacking được chặn trong mọi browser cũ. Cần kiểm thử browser thực tế khi yêu cầu UX cho phép embedded iframe.

### 4.3 Header không thay cho kiểm soát đầu vào/đầu ra

CSP là lớp giảm thiểu XSS, không thay cho output encoding, validate input, cookie Secure/HttpOnly/SameSite, kiểm tra role, hay review server-side template. `X-Content-Type-Options: nosniff» không sửa được ứng dụng trả MIME sai. HSTS không có ý nghĩa nếu HTTPS chưa được triển khai an toàn. Kết quả kiểm thử phải gắn với threat model và hành vi client.

## 5. Dự án Spring Boot 3.3.5 chạy được — CSRF + CORS + headers

Ví dụ cố ý **giữ CSRF bật**, hỗ trợ CORS chính xác cho một origin và dùng HTTP Basic để làm rõ kiểm thử authenticated/anonymous. HTTP Basic của browser có thể được gửi tự động trong một số tình huống, do đó không tự mặc định tắt CSRF cho API chỉ vì route bắt đầu bằng `/api/».

### 5.1 Cấu trúc và dependencies

```text
web-security-defenses/
├── pom.xml
└── src/
    ├── main/java/com/example/defenses/
    │   └── WebSecurityDefensesApplication.java
    └── test/java/com/example/defenses/
        └── WebSecurityDefensesApplicationTest.java
```

Tạo `pom.xml»:

```xml
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
    <artifactId>web-security-defenses</artifactId>
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
```

### 5.2 Security configuration và controller

Tạo `src/main/java/com/example/defenses/WebSecurityDefensesApplication.java»:

```java
package com.example.defenses;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter.ReferrerPolicy;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
public class WebSecurityDefensesApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebSecurityDefensesApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails tester = User.withUsername("tester")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(tester);
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://portal.example.test"));
        config.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        config.setAllowedHeaders(List.of(
            "Content-Type", "Authorization", "X-CSRF-TOKEN"));
        config.setAllowCredentials(true);
        config.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .cors(Customizer.withDefaults())
            // Cố ý giữ CSRF để có thể kiểm thử.
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; frame-ancestors 'none'"))
                .referrerPolicy(referrer -> referrer
                    .policy(ReferrerPolicy.NO_REFERRER)))
            .build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/api/public")
        String publicPage() {
            return "public ok";
        }

        @GetMapping("/api/profile")
        String profile(Authentication authentication) {
            return "hello " + authentication.getName();
        }

        @PostMapping("/api/notes")
        String addNote() {
            return "note created";
        }
    }
}
```

**Giải thích cấu hình:**

1. `.cors(...)» đưa CORS handling vào security chain; bean `UrlBasedCorsConfigurationSource» xác định origin **chính xác** `https://portal.example.test», những method và request header được phép. CORS preflight có thể được xử lý trước authentication.
2. `.csrf(...)» giữ CSRF bật. Không có đoạn `.csrf(...disable)» hoặc `ignoringRequestMatchers» cho POST.
3. `/api/public» có thể truy cập anonymous; `/api/profile» và `/api/notes» cần xác thực. Quy tắc user không đủ quyền có thể bổ sung trong ứng dụng khác; demo tập trung vào cơ chế CSRF/CORS/header.
4. `httpBasic» làm rõ 401 cho anonymous; `formLogin» bị tắt để test không phải xử lý redirect login.
5. Default headers của Spring Security vẫn còn. Demo **thêm** CSP và Referrer-Policy vì đây không phải default bắt buộc.
6. `allowCredentials(true)» chỉ cho browser biết có thể dùng credentials với origin đã cho phép; nó không cấp authentication/role, cũng không bỏ qua CSRF.
7. Mật khẩu demo yếu chỉ dành cho máy học. Production phải áp dụng chính sách secret, password hash, HTTPS, CSRF token repository và CORS origin phù hợp với frontend thật.

## 6. Bộ kiểm thử MockMvc đầy đủ

Tạo `src/test/java/com/example/defenses/WebSecurityDefensesApplicationTest.java». Dùng `@SpringBootTest» và `@AutoConfigureMockMvc» để chạy `SecurityFilterChain» thật trong MockMvc, còn `@WithMockUser» chỉ cung cấp danh tính giả cho từng test để cô lập yêu cầu xác thực.

```java
package com.example.defenses;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WebSecurityDefensesApplicationTest {

    private static final String ALLOWED = "https://portal.example.test";
    private static final String DENIED = "https://evil.example.test";

    @Autowired
    MockMvc mvc;

    // --- CSRF: 4 trạng thái token và anonymous ---

    @Test
    @WithMockUser
    void missingCsrfTokenBlocksPost() throws Exception {
        mvc.perform(post("/api/notes"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser
    void invalidCsrfTokenBlocksPost() throws Exception {
        mvc.perform(post("/api/notes").with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser
    void validCsrfParameterAllowsPost() throws Exception {
        mvc.perform(post("/api/notes").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("note created"));
    }

    @Test
    @WithMockUser
    void validCsrfHeaderAllowsPost() throws Exception {
        mvc.perform(post("/api/notes").with(csrf().asHeader()))
            .andExpect(status().isOk())
            .andExpect(content().string("note created"));
    }

    @Test
    @WithAnonymousUser
    void csrfTokenDoesNotAuthenticateAnonymousUser() throws Exception {
        mvc.perform(post("/api/notes").with(csrf()))
            .andExpect(status().isUnauthorized());
    }

    // --- CORS: preflight không có login cookie vẫn được xử lý ---

    @Test
    void allowedPreflightIsAccepted() throws Exception {
        mvc.perform(options("/api/notes")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                containsString("POST")))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
    }

    @Test
    void unknownOriginPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/notes")
                .header(HttpHeaders.ORIGIN, DENIED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void disallowedMethodPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/notes")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE"))
            .andExpect(status().isForbidden());
    }

    @Test
    void disallowedHeaderPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/notes")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "x-secret-admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser
    void actualCorsGetRetainsAuthenticationRequirement() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.ORIGIN, ALLOWED))
            .andExpect(status().isOk())
            .andExpect(content().string("hello user"))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED));
    }

    @Test
    @WithMockUser
    void allowedCorsOriginDoesNotBypassCsrf() throws Exception {
        mvc.perform(post("/api/notes")
                .header(HttpHeaders.ORIGIN, ALLOWED))
            .andExpect(status().isForbidden())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED));
    }

    @Test
    void requestWithoutOriginDoesNotRequireCorsHeader() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    // --- Default headers và headers được cấu hình thêm ---

    @Test
    void defaultSecurityHeadersExist() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                HttpHeaders.CACHE_CONTROL, containsString("no-store")));
    }

    @Test
    void customCspAndReferrerPolicyExist() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Content-Security-Policy",
                "default-src 'self'; frame-ancestors 'none'"))
            .andExpect(header().string(
                "Referrer-Policy", "no-referrer"));
    }

    @Test
    void hstsAppearsForHttpsRequest() throws Exception {
        mvc.perform(get("/api/public").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Strict-Transport-Security",
                containsString("max-age=")));
    }

    @Test
    void hstsIsNotAddedForPlainHttp() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                "Strict-Transport-Security"));
    }

    // --- Authentication thật: không nhầm với @WithMockUser ---

    @Test
    void realHttpBasicCredentialCanReadProfile() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("tester", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello tester"));
    }

    @Test
    void realHttpBasicCredentialDoesNotBypassCsrf() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("tester", "demo123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void realHttpBasicCredentialAndCsrfCanPost() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("tester", "demo123"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("note created"));
    }
}
```

### 6.1 Điều gì được kiểm chứng?

Bộ test gồm **19 ca** với ba nhóm:

- **CSRF (5 ca):** thiếu token 403, token sai 403, token hợp lệ ở parameter/header thành công, anonymous có CSRF vẫn chưa authenticated.
- **CORS (7 ca):** preflight đúng được thông qua không cần login, origin/method/header sai bị từ chối; actual request nhận allow-origin nhưng vẫn phải thỏa authentication/CSRF; request không Origin không cần CORS header.
- **Security headers và xác thực thật (7 ca):** `nosniff», `DENY», `no-store», CSP, Referrer-Policy, HSTS HTTPS/HTTP; HTTP Basic với password thật; POST vẫn cần CSRF.

Ví dụ dùng `@WithMockUser» để test filter CSRF **không phụ thuộc** việc login; dùng `httpBasic(...)» trong các ca riêng để gửi header Basic và đi qua authentication provider/PasswordEncoder thật của demo. Nếu chỉ dùng mock user, kết quả 200 không chứng minh password đúng.

### 6.2 Cách chạy và kết quả mong đợi

Cài JDK 17+ và Maven, mở terminal tại thư mục dự án chứa `pom.xml»:

```bash
mvn test
mvn spring-boot:run
```

`mvn test» chạy bộ test JUnit/MockMvc. Các status/body trong bảng là **kỳ vọng từ source**; không nên nói test đã qua khi chưa chạy trong môi trường thật.

Test thêm bằng curl:

```bash
# Endpoint công khai không có CSRF token vì đây là GET:
curl -i http://localhost:8080/api/public

# GET có HTTP Basic credential:
curl -i -u tester:demo123 http://localhost:8080/api/profile

# POST dù credential đúng vẫn thiếu CSRF -> 403:
curl -i -u tester:demo123 -X POST http://localhost:8080/api/notes

# CORS preflight tới origin được phép:
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H "Origin: https://portal.example.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
```

Các dòng lệnh trên dành cho shell Unix/macOS/Git Bash; trên Windows PowerShell `curl» có thể là alias theo phiên bản, nên có thể dùng `curl.exe». Ví dụ POST dùng curl đơn thuần không thực hiện quy trình cấp CSRF token thực tế; `MockMvc.with(csrf())» đã mô phỏng token cho bài kiểm thử.

**Tại sao không tạo POST “cứ dùng curl là thành công”?** Vì mục tiêu bài học là **kiểm thử CSRF đang bật**; việc tự động cho mọi POST qua mà không có token sẽ che đi lỗ hổng mà ta cần chứng minh. Trong ứng dụng thật, frontend có thể nhận token qua endpoint/HTML/cookie theo `CsrfTokenRepository» và request handler được thiết kế phù hợp.

## 7. Kiểm thử CSRF với session, cookie hoặc SPA thực tế

Spring Security 6 có cơ chế token **deferred loading** và bảo vệ BREACH theo cấu hình mặc định; cách token được đưa ra cho client và xử lý lại phụ thuộc `CsrfTokenRequestHandler», `CsrfTokenRepository» và loại frontend. `csrf()» thuận tiện cho MockMvc nhưng không kiểm tra đầy đủ vòng đời token của browser.

Nếu ứng dụng dùng session/cookie hoặc SPA, cần bổ sung:

1. **Nhận token:** frontend được phép lấy token đúng cách (render hidden field, endpoint cấp token, hoặc cookie nếu phù hợp kiến trúc).
2. **Gửi token:** POST/PUT/PATCH/DELETE gửi đúng header/form field; browser gửi cookie xác thực theo chính sách.
3. **Token thiếu/sai:** phải bị từ chối kể cả khi browser có session hợp lệ.
4. **Đăng nhập/đăng xuất/đổi session:** kiểm tra token cũ còn dùng được hay bị xoay/xóa theo chính sách thực tế.
5. **SameSite/Secure/HttpOnly:** kiểm tra cookie trên **response thực** và hành vi browser; `SameSite» là lớp bảo vệ bổ sung, không nên mặc nhiên thay thế CSRF.
6. **Không tiết lộ token qua URL:** query string có thể xuất hiện trong log, history hoặc Referer.
7. **Các tuyến được miễn CSRF:** chỉ miễn những luồng phù hợp với threat model, kiểm thử cả negative path; không miễn rộng `/api/**» mà không có bằng chứng rằng client không dùng credential tự động gửi.

Trong ứng dụng stateless chỉ chấp nhận Bearer token do JavaScript gắn thủ công vào `Authorization» và **không** dùng cookie/session/HTTP Basic tự động gửi, rủi ro CSRF có thể khác; việc tắt CSRF cần dựa trên cách browser nhận credential và threat model, đồng thời vẫn test CORS và authorization. Không có quy tắc “REST API thì luôn tắt CSRF”.

## 8. Kiểm thử CORS ở browser và reverse proxy

### 8.1 MockMvc chứng minh gì, chưa chứng minh gì?

`MockMvc» gọi ứng dụng ở servlet test environment và có thể kiểm tra CORS filter. Nó chứng minh server **phát header đúng** khi request mang `Origin»/preflight headers. Tuy nhiên, nó **không thực thi Same-Origin Policy của browser**.

Cần browser-based E2E khi muốn xác minh:
- Frontend ở origin A có đọc được response API ở origin B trong thực tế hay không.
- Cookie `SameSite», `Secure», `credentials: "include"» và redirect authentication.
- CDN/reverse proxy có vô tình thêm `Access-Control-Allow-Origin: *», xóa `Vary» hoặc cache phản hồi theo nhầm origin không.
- Preflight cache và policy theo environment (dev/staging/production).
- CSP frame/script policy có chặn đúng resource và không phá chức năng ứng dụng không.

### 8.2 Đừng mở CORS để “sửa 403”

Một 403 có thể do CSRF, authentication, thiếu quyền, CORS hoặc upstream proxy. Trước khi sửa, kiểm tra:

1. Request có `Origin» hay không? Có thực sự là preflight OPTIONS với `Access-Control-Request-Method» không?
2. HTTP status và header nào do `CorsFilter»/gateway tạo? Browser console báo CORS error hay server thực sự từ chối authorization?
3. POST có CSRF token hợp lệ theo repository/handler không?
4. User đã authenticated chưa, authority có đúng không?
5. Origin scheme/host/port có khớp whitelist không? Frontend có gửi credential và policy có `allowCredentials» phù hợp không?
6. Có nhiều `SecurityFilterChain», `CorsConfigurationSource» hoặc proxy override header không?

Không nên chuyển `allowedOrigins» thành wildcard để né lỗi. Một response có `Access-Control-Allow-Origin» đúng chỉ chứng minh CORS configuration của server, không chứng minh endpoint được bảo vệ khỏi CSRF hay quyền truy cập trái phép.

## 9. Kiểm thử header khi deployment dùng HTTPS và frontend thật

### 9.1 Bộ header cần kiểm tra theo môi trường

| Lớp kiểm tra | Kiểm tra cụ thể | Công cụ |
| --- | --- | --- |
| Spring Security filter | `X-Content-Type-Options», `X-Frame-Options», cache headers | MockMvc |
| Tùy biến ứng dụng | CSP, Referrer-Policy, Permissions-Policy nếu cấu hình | MockMvc |
| HTTPS | HSTS chỉ trên HTTPS, redirect HTTP->HTTPS nếu được yêu cầu | MockMvc mô phỏng + integration qua HTTPS |
| Proxy/CDN | Proxy không xóa/ghi đè các header hoặc làm mất `Vary» | Test với deployment thực tế |
| Browser | CSP vi phạm có xuất hiện? iframe có bị từ chối? | Browser devtools/E2E |
| File tĩnh và dữ liệu công khai | Cache-Control có phù hợp endpoint và asset không? | Integration/contract test |

Spring Security mặc định đặt cache-control tránh cache phản hồi nhạy cảm. Nhưng file tĩnh versioned (ví dụ `app.abc123.js») có thể cần policy cache riêng. Đừng viết một test cứng yêu cầu `no-store» cho **mọi URL** mà không xem mục đích tài nguyên và cấu hình override. Trong demo, endpoint `/api/public» vẫn nhận default header vì không custom cache policy.

### 9.2 HSTS và chuyển tiếp HTTPS

HSTS cần HTTPS thật để browser tin cậy. Khi ứng dụng sau reverse proxy, request tới server nội bộ có thể là HTTP dù browser dùng HTTPS. Kiểm tra trusted forwarded-header configuration, proxy headers và bảo đảm client tùy ý không giả mạo scheme.

Chỉ dùng `.secure(true)» trong MockMvc để kiểm tra điều kiện của writer; cần một integration test qua endpoint HTTPS công khai để xác minh môi trường. Nếu tăng `max-age», bật `includeSubDomains» hoặc `preload», hãy cân nhắc phạm vi toàn bộ subdomain; không bật preload một cách tùy tiện chỉ để test header có giá trị.

### 9.3 Header không được Spring Security tự thêm

**CSP, Referrer-Policy, Permissions-Policy** cần được cấu hình khi phù hợp. Trong demo CSP và Referrer đã được cấu hình chủ động. Không kết luận “Spring Security thiếu bảo mật” chỉ vì response không có CSP của một API JSON không trả HTML; cần quyết định policy theo ứng dụng. Nếu header là yêu cầu hợp đồng bảo mật của dự án, hãy thêm cấu hình và test chính xác để tránh regression.

### 9.4 Không kiểm tra những mặc định đã lỗi thời

`X-XSS-Protection» là header lịch sử và có thể hiện diện với giá trị tắt hoặc không hiện diện theo phiên bản/cấu hình. Browser hiện đại chủ yếu dựa vào CSP và output encoding. Không sao chép các kỳ vọng từ Spring Security 4.x/5.x rồi áp đặt lên 6.x/7.x; đối chiếu tài liệu phiên bản đang dùng.

## 10. Lỗi thường gặp trong bộ test và cách tránh

### Lỗi A — Bỏ `csrf()» để test POST nhanh

POST có user mà không có token thường bị 403 đúng thiết kế. Không tắt toàn bộ CSRF trong cấu hình production chỉ để test qua. Tách test **POST không token phải 403**, **POST đúng token phải thành công**.

### Lỗi B — Cho rằng `@WithMockUser» tạo sẵn CSRF token

`@WithMockUser» tạo identity giả, không tự gắn request CSRF token. Test nên chọn rõ authentication và CSRF như **hai chiều độc lập**. Với `.with(csrf())», test anonymous vẫn có thể nhận 401 vì thiếu authentication.

### Lỗi C — Gửi CORS preflight với HTTP Basic rồi gọi đó là chuẩn browser

Browser preflight thông thường không mang session cookie. Nếu Spring Security đòi authentication trên OPTIONS, frontend có thể thất bại ngay cả khi GET/POST business code đúng. Test preflight **không đăng nhập**, chỉ có `Origin» và `Access-Control-Request-*».

### Lỗi D — Thấy allowed origin rồi tin POST đã qua CSRF

CORS xử lý quyền đọc cross-origin; CSRF bảo vệ hành động thay đổi trạng thái. Test `allowedCorsOriginDoesNotBypassCsrf» chứng minh request có allow-origin vẫn phải qua CSRF và có thể bị 403.

### Lỗi E — Test CORS chỉ bằng status 200

Một OPTIONS có thể trả 200 nhưng thiếu `Access-Control-Allow-Origin» hoặc không cho phép header/method cần thiết, khiến browser không gửi actual request. Phải assert allow-origin, allow-methods, allow-headers/credentials khi liên quan; test origin và method sai ở negative path.

### Lỗi F — Dùng `Access-Control-Allow-Origin: *» với credential

Browser không cho phép wildcard cho cross-origin credentialed response. Whitelist origin cụ thể và test giá trị đúng. Kiểm tra có proxy thay đổi header sau Spring Security hay không.

### Lỗi G — Coi `Origin» là bằng chứng danh tính

Công cụ HTTP ngoài browser có thể tùy ý gửi `Origin». Không dùng header Origin để cấp role, bypass xác thực hay cho truy cập resource. CORS là một lớp quản lý browser cross-origin.

### Lỗi H — Assert HSTS trên HTTP MockMvc

HSTS chỉ được thêm cho secure request; HTTP MockMvc bình thường có thể không có header. Test cả `.secure(true)» và request bình thường. Với reverse proxy, kiểm thử proxy/forwarded headers đúng cách.

### Lỗi I — Assert CSP như header mặc định

Spring Security không tự chọn CSP phù hợp cho mọi website. Nếu dự án cần CSP, cấu hình rõ bằng `headers.contentSecurityPolicy(...)» và test policy. CSP quá chặt cũng có thể chặn resource hợp lệ; cần xác minh browser.

### Lỗi J — Tắt filter chain trong MockMvc

Nếu `@AutoConfigureMockMvc(addFilters = false)» hoặc `MockMvcBuilders.standaloneSetup(controller)» không tích hợp Spring Security, test có thể trả 200 cả khi thiếu CSRF; đây **không phải bằng chứng endpoint an toàn**. Dùng `@AutoConfigureMockMvc» mặc định hoặc `MockMvcBuilders.webAppContextSetup(context).apply(springSecurity())».

### Lỗi K — Kiểm thử “đúng header” nhưng quên negative path

Chỉ assert `X-Frame-Options» và CSP không phát hiện một POST thiếu token đang lọt qua hoặc origin sai được CORS chấp nhận. Bộ test nên cân bằng **allow case và deny case**, kiểm tra URL và method thực.

### Lỗi L — Bỏ qua vai trò proxy/CDN

Header có thể bị rewrite khi đi qua ingress/API gateway. Unit/MockMvc test chỉ xác nhận ứng dụng tạo ra header, cần kiểm tra thêm deployment để biết response cuối đến browser có còn nguyên hay không.

## 11. Checklist QA trước khi merge

1. **CSRF:** kiểm tra GET/HEAD không đổi trạng thái, POST/PUT/DELETE có test token thiếu/sai/hợp lệ; authentication và CSRF được test độc lập.
2. **CORS:** test origin hợp lệ và không hợp lệ, method/header được phép và cấm, preflight anonymous, actual request có authentication/CSRF; không dùng wildcard cùng credential.
3. **Header mặc định:** `nosniff», frame option, cache-control đúng theo version; không assert các header lịch sử lỗi thời.
4. **Header tùy biến:** CSP, Referrer-Policy, Permissions-Policy nếu là yêu cầu hệ thống; kiểm tra directive đúng và browser không bị phá chức năng.
5. **HSTS/HTTPS:** test secure request, không đòi HSTS trên HTTP; nếu có TLS termination, kiểm tra proxy thật.
6. **HTTP security:** 401/403/200 theo cấu hình, không để lỗi CSRF/CORS bị nhầm với role. Khi từ chối, business handler không được chạy.
7. **Cấu hình test:** security filter chain đang bật; `spring-security-test» có trong test dependency, MockMvc thực sự tích hợp Spring Security.
8. **Xác thực thật:** nếu cần chứng minh password/JWT/OAuth2 hoạt động, có test gửi credential/token thật; `@WithMockUser» chỉ mô phỏng context.
9. **Quan sát lỗi:** log/metric không chứa CSRF token, session cookie, raw Authorization/JWT hoặc thông tin nhạy cảm.
10. **Regression:** test cả browser/E2E cho CSP, cookie, CORS ở frontend origin, gateway header và ứng dụng production-like khi cần.

## 12. Ghi nhớ

- **CSRF** ngăn browser thực hiện hành động đổi trạng thái trái ý chủ tài khoản; cần test token hợp lệ, thiếu và sai, không nhầm token với việc đăng nhập.
- **CORS** là chính sách để browser kiểm soát cross-origin; preflight phải chạy trước authentication và test cả origin/method/header bị cấm. CORS **không** thay authentication/CSRF.
- **Security response headers** hướng dẫn browser; kiểm tra mặc định đúng phiên bản, CSP/Referrer nếu đã cấu hình và HSTS chỉ trên HTTPS.
- **MockMvc** chứng minh filter/handler của Spring Security tạo response phù hợp; không mô phỏng toàn bộ browser, TLS, proxy, cache và JavaScript frontend.
- Bộ test tốt bao gồm **negative cases** (403 do CSRF sai, preflight cấm, không có HSTS trên HTTP) cùng với **positive cases** (CSRF hợp lệ, origin được phép, header đầy đủ trên HTTPS).
- Không tắt filter hoặc mở wildcard để “làm xanh test”; hãy sửa đúng nguyên nhân và giữ cơ chế bảo vệ được kiểm thử.

## Tài liệu tham khảo chính thức

- Spring Security — Servlet CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Testing with CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — CORS for Servlet Applications: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — Security HTTP Response Headers (Servlet): https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html
- Spring Security — MockMvc Testing Integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — Setup MockMvc with Spring Security: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html
- Spring Framework — CORS: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Security — Reactive CSRF (đối chiếu WebFlux): https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html