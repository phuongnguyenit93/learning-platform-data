# Kiểm thử nhiều chuỗi, endpoint chưa khớp và quy tắc dự phòng

**Module:** Spring Security – Servlet  
**Chủ đề cha:** Kiểm thử HTTP

## 1. Bài toán: vì sao một URL có thể được bảo vệ bởi chuỗi khác với dự kiến?

Trong ứng dụng Spring Security Servlet, có thể tồn tại nhiều bean `SecurityFilterChain`: một chuỗi dành riêng cho API, một chuỗi dành cho đường dẫn quản trị, và một chuỗi chung cho những request còn lại. Mỗi chuỗi có matcher, filter và quy tắc authorization riêng.

Ví dụ, ứng dụng có:

- `/api/admin/stats`: chỉ người có `ROLE_API_ADMIN` được xem.
- `/api/reports`: người có `SCOPE_reports.read` được xem.
- `/api/public`: tài nguyên public.
- `/web/feedback`: form POST cần user có `ROLE_USER` và CSRF token hợp lệ.
- `/shadow`: controller tồn tại, nhưng chưa có quyết định cho phép trong chính sách security.

Nếu chuỗi `/api/**` có ưu tiên cao hơn `/api/admin/**`, request quản trị có thể bị xử lý theo chính sách API chung. Nếu cả hai chuỗi chỉ match một phần URL mà **không có fallback chain**, một request ngoài phạm vi mọi matcher có thể **không được Spring Security filter chain bảo vệ**. Nếu chỉ kiểm thử endpoint quen thuộc mà không thử URL chưa match, lỗi này có thể không lộ ra.

**Mục tiêu của bài:**

1. Giải thích cách `FilterChainProxy` chọn **chuỗi đầu tiên có `RequestMatcher` khớp**.
2. Phân biệt **`securityMatcher` chọn SecurityFilterChain** với **`requestMatchers` bên trong `authorizeHttpRequests` chọn quy tắc cho request đã vào chuỗi**.
3. Cấu hình `@Order` để đường dẫn chuyên biệt được xét trước đường dẫn tổng quát.
4. Đặt quy tắc dự phòng **`anyRequest().denyAll()`** trong từng chuỗi và một **catch-all SecurityFilterChain** để xử lý các đường dẫn ngoài phạm vi chuỗi chuyên biệt.
5. Dùng `MockMvc`, `spring-security-test`, `user()`, `csrf()` và các assertion HTTP để kiểm thử ranh giới 200 / 401 / 403, cũng như tránh suy luận nhầm từ 404.
6. Phát hiện false positive do test không chạy filter, matcher sai ngữ cảnh, `web.ignoring()`, nhiều chuỗi trùng lặp hoặc cấu hình auth/CSRF khác nhau.

**Phạm vi:** Spring Security **Servlet stack** với `HttpSecurity`, không phải WebFlux `SecurityWebFilterChain`.

## 2. Cơ chế chọn chuỗi: chỉ chuỗi đầu tiên khớp được áp dụng

Spring Security Servlet sử dụng một `FilterChainProxy` chứa danh sách các `SecurityFilterChain`. Mỗi chain có một `RequestMatcher` xác định request nào thuộc chain đó và tập security filter tương ứng.

~~~text
HTTP request
     |
     v
DelegatingFilterProxy ("springSecurityFilterChain")
     |
     v
FilterChainProxy
     |
     +--> @Order(1)  securityMatcher("/api/admin/**")?
     |      | Có -> CHỌN CHUỖI NÀY, KHÔNG thử chuỗi sau
     |      | Không
     |      v
     +--> @Order(2)  securityMatcher("/api/**")?
     |      | Có -> CHỌN CHUỖI API
     |      | Không
     |      v
     +--> @Order(3)  không securityMatcher tùy biến?
     |      | Có -> CHỌN CHUỖI DỰ PHÒNG (match mọi request)
     |      v
     +--> Không chuỗi nào khớp:
            Không có Spring Security filters áp dụng cho request đó
     |
     v
Filter của chuỗi đã chọn -> DispatcherServlet -> Controller
~~~

**Một request không đồng thời được xử lý bởi cả hai SecurityFilterChain.** Các `requestMatchers` trong chuỗi thứ hai **không được xét** nếu chuỗi thứ nhất đã match. Vì vậy, một policy `denyAll` ở chuỗi ưu tiên cao có thể chặn request ngay cả khi chuỗi ưu tiên thấp hơn định cho phép nó. Đây là hành vi mong muốn khi thứ tự và phạm vi được thiết kế đúng.

### 2.1. securityMatcher và requestMatchers là hai cấp matcher khác nhau

| Cấp | API | Trách nhiệm |
| --- | --- | --- |
| **Chọn chuỗi** | `http.securityMatcher("/api/**")` | Quyết định request có đi vào **SecurityFilterChain này** không. |
| **Phân quyền bên trong chuỗi** | `authorizeHttpRequests(auth -> auth.requestMatchers(...).hasAuthority(...))` | Sau khi chuỗi được chọn, áp quy tắc quyền tương ứng. |
| **Fallback bên trong chuỗi** | `auth.anyRequest().denyAll()` | Từ chối các request vào chuỗi nhưng không được một quy tắc cho phép trước đó match. |
| **Fallback giữa các chuỗi** | Bean SecurityFilterChain cuối không gọi `securityMatcher` tùy biến | Để mọi request còn lại vẫn được Spring Security kiểm tra. |

Trong một chuỗi, các quy tắc authorization được xét **theo thứ tự khai báo**, matcher đầu tiên phù hợp quyết định policy. Đặt matcher chuyên biệt trước matcher tổng quát; `anyRequest()` nên nằm **cuối**.

**Hai tầng “dự phòng” là khác nhau:**

- `anyRequest().denyAll()` **trong chain API** chỉ áp dụng request mà **chain API đã match**.
- Một `SecurityFilterChain` **catch-all** mới bao phủ request chưa match chain API/admin.

Có `anyRequest().denyAll()` bên trong chuỗi `securityMatcher("/api/**")` **không bảo vệ** `/shadow` ở ngoài `/api/**`, nếu không còn chuỗi nào khác match.

### 2.2. Trường hợp cấu hình nguy hiểm: không có chuỗi dự phòng

~~~java
// MINH HỌA THIẾU BẢO VỆ — KHÔNG DÙNG NGUYÊN TRONG PRODUCTION.
@Bean
SecurityFilterChain onlyApi(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
~~~

Nếu đây là **chain duy nhất**, request `/shadow` không khớp `/api/**`; `FilterChainProxy` không áp các filter của Spring Security cho request đó. Nếu MVC có controller `GET /shadow` và không có lớp bảo vệ khác, route có thể trả dữ liệu mà không yêu cầu authentication.

**Cách phòng tránh:** có chuỗi cuối không giới hạn path, cùng policy explicit `permitAll` cho endpoint thực sự public và `denyAll` cho phần còn lại. Đừng dựa vào việc “chưa có controller nên sẽ 404”; một endpoint có thể được thêm trong tương lai, hoặc filter/servlet khác có thể xử lý request.

## 3. Thứ tự @Order và các vùng giao nhau

Giả sử:

~~~text
Chain 1: /api/admin/**       (hẹp, chuyên biệt)
Chain 2: /api/**             (rộng hơn)
Chain 3: any request         (catch-all)
~~~

URL `/api/admin/stats` khớp cả mẫu chain 1 lẫn chain 2. Vì **chain 1 được xét trước**, chỉ chính sách chain 1 có hiệu lực.

| URL | Chuỗi cần chọn | Vì sao |
| --- | --- | --- |
| `GET /api/admin/stats` | Chain 1 | Khớp `/api/admin/**` trước. |
| `GET /api/reports` | Chain 2 | Không thuộc `/api/admin/**`, thuộc `/api/**`. |
| `GET /api/public` | Chain 2 | Có rule permit public trong API chain. |
| `GET /api/unknown` | Chain 2 | Vẫn thuộc `/api/**`; dùng `denyAll` nếu chưa khai báo. |
| `GET /health` | Chain 3 | Không khớp hai chain trên, vào catch-all. |
| `GET /shadow` | Chain 3 | Không khớp chuyên biệt; bị fallback denyAll. |

**Không** tin rằng khai báo `@Order(20)` trên một chain rồi Spring sẽ gộp các quyền của chain `@Order(10)` và `@Order(20)`. Thứ tự chỉ điều khiển **chain nào được xét trước**.

Nếu hai chain có cùng order hoặc không rõ order, việc lựa chọn phụ thuộc cấu hình và thứ tự đăng ký thực tế; không nên dựa vào thứ tự không được cam kết. Dùng `@Order(1)`, `@Order(2)`, `@Order(3)` rõ ràng và có test cho path giao nhau.

**Không dùng** `http.securityMatcher("/api/**")` rồi cho rằng `requestMatchers("/admin/**")` bên trong nó sẽ tự bắt `/admin/**` ngoài `/api/**`. Rule authorization không mở rộng vùng match của chain.

## 4. Thiết kế chính sách kiểm thử được

Ta chọn policy cụ thể:

| Chain | Matcher và @Order | Rule trước fallback | Fallback |
| --- | --- | --- | --- |
| **Admin API** | `@Order(1)`, `/api/admin/**` | GET `/api/admin/stats`: `ROLE_API_ADMIN` | `denyAll` |
| **General API** | `@Order(2)`, `/api/**` | GET `/api/public`: public; GET `/api/reports`: `SCOPE_reports.read` | `denyAll` |
| **General fallback** | `@Order(3)`, không giới hạn matcher | GET `/`, `/health`: public; POST `/web/feedback`: `ROLE_USER` | `denyAll` |

Trong ví dụ:

- Dùng **HTTP Basic** để kiểm tra authentication/authority thuận tiện bằng MockMvc; không có Identity Provider hoặc database.
- **Giữ CSRF bảo vệ mặc định** cho các HTTP method đổi trạng thái. HTTP Basic trong browser có thể là credential do browser tự gửi, nên không tắt CSRF chỉ vì đường dẫn có tiền tố `/api`.
- POST `/web/feedback` chỉ thành công khi **có role đúng và CSRF token đúng**.
- Endpoint `/shadow` tồn tại trong MVC nhưng không nằm trong allowlist, nhằm chứng minh fallback thật sự từ chối.
- Với ứng dụng API thuần bearer token stateless và không dựa vào cookie/browser-auto credential, CSRF policy có thể khác; phải đánh giá riêng chứ không sao chép `csrf.disable()` từ tutorial khác.

Đây là thiết kế **fail closed**: mặc định không cấp quyền cho path/method mới. Khi cần mở endpoint, phải thêm một matcher cho phép có chủ đích và viết test tương ứng.

## 5. Ví dụ chạy được: Spring Boot 3.3.5, Java 17, ba SecurityFilterChain

**Yêu cầu:** JDK 17+, Maven, Spring Boot 3.3.5 (để minh họa cú pháp Spring Security 6.x). Dự án thực tế nên dùng phiên bản được hỗ trợ và cập nhật bản vá bảo mật.

Cấu trúc:

~~~text
multi-chain-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/
    │       ├── MultiChainApplication.java
    │       ├── SecurityConfig.java
    │       └── DemoController.java
    └── test/
        └── java/demo/MultiChainSecurityTest.java
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>multi-chain-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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

`starter-web` cung cấp Spring MVC Servlet, `starter-security` cung cấp security filter infrastructure, `starter-test` cung cấp MockMvc/JUnit/AssertJ và `spring-security-test` hỗ trợ mock user và CSRF request processor.

### 5.2. src/main/java/demo/MultiChainApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiChainApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultiChainApplication.class, args);
    }
}
~~~

### 5.3. src/main/java/demo/SecurityConfig.java

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // Chỉ dùng account cố định cho demo local.
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo-only"))
                .authorities("SCOPE_reports.read")
                .build(),
            User.withUsername("api-admin")
                .password(encoder.encode("demo-only"))
                .roles("API_ADMIN")
                .build(),
            User.withUsername("web-user")
                .password(encoder.encode("demo-only"))
                .roles("USER")
                .build()
        );
    }

    // Ưu tiên 1: chuỗi hẹp dành cho /api/admin/**.
    @Bean
    @Order(1)
    SecurityFilterChain adminApiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/admin/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/admin/stats")
                    .hasRole("API_ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Không tắt CSRF mù quáng cho HTTP Basic.
        return http.build();
    }

    // Ưu tiên 2: chuỗi API chung, không nhận /api/admin/**
    // vì chain @Order(1) đã match các URL quản trị.
    @Bean
    @Order(2)
    SecurityFilterChain generalApiChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    // Ưu tiên 3: không có securityMatcher => catch-all.
    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/", "/health")
                    .permitAll()
                .requestMatchers(HttpMethod.POST, "/web/feedback")
                    .hasRole("USER")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // CSRF mặc định vẫn bật cho POST /web/feedback.
        return http.build();
    }
}
~~~

**Giải thích các điểm khó:**

- `@Order(1)` phải đặt trước `@Order(2)` bởi đường dẫn `/api/admin/**` là tập con của `/api/**`.
- Trong chain 1, một user có `SCOPE_reports.read` nhưng không có `ROLE_API_ADMIN` vẫn bị từ chối ở `/api/admin/stats`. Spring không thử lại chain 2.
- `requestMatchers(HttpMethod.GET, "/api/reports")` cho phép **chỉ method GET** theo authority định nghĩa. `POST /api/reports` không tự được phép, ngay cả khi controller có tồn tại.
- `anyRequest().denyAll()` trong từng chain làm policy cho path/method chưa khai báo rõ ràng.
- Chain 3 **không** gọi `securityMatcher`; nó match mọi request còn lại. Nếu bỏ chain 3, `/shadow` có thể không còn được Spring Security bảo vệ.
- `httpBasic()` được chọn để mô phỏng authentication đơn giản. `@WithMockUser` hoặc `user()` của Spring Security Test không kiểm chứng mật khẩu thực tế, vì vậy sau cùng vẫn cần integration test Basic login nếu dự án sử dụng cơ chế này.
- Không bật `web.ignoring()` cho endpoint động chỉ để bỏ qua security, vì cách đó **bypass Spring Security filters** (bao gồm cả các header/filter hữu ích); `permitAll()` trong đúng chain thường là lựa chọn phù hợp cho public endpoint.

### 5.4. src/main/java/demo/DemoController.java

~~~java
package demo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    Map<String, String> home() {
        return Map.of("message", "home");
    }

    @GetMapping("/health")
    Map<String, String> health() {
        return Map.of("status", "up");
    }

    @GetMapping("/api/public")
    Map<String, String> publicApi() {
        return Map.of("resource", "public-api");
    }

    @GetMapping("/api/reports")
    Map<String, String> reports() {
        return Map.of("resource", "reports");
    }

    @GetMapping("/api/admin/stats")
    Map<String, String> adminStats() {
        return Map.of("resource", "admin-stats");
    }

    @PostMapping("/web/feedback")
    Map<String, String> feedback() {
        return Map.of("status", "feedback-received");
    }

    // Controller CÓ THẬT nhưng fallback không cho phép truy cập.
    @GetMapping("/shadow")
    Map<String, String> shadow() {
        return Map.of("secret", "must-not-be-exposed");
    }
}
~~~

Không có controller cho `GET /api/not-configured`. Tuy nhiên, trong cấu hình này request đó match chain API, và `anyRequest().denyAll()` được xét **trước khi** DispatcherServlet xác định có controller hay không.

Điều này rất quan trọng khi viết test: bạn có thể nhận **403** thay vì **404** với user đã authenticated. Đó là hệ quả policy security chặn request **trước** MVC routing, không phải bằng chứng rằng endpoint tồn tại.

### 5.5. Chạy thủ công

Từ thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Thử endpoint public:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/health
~~~

Kỳ vọng HTTP **200**.

Thử API cần quyền đọc:

~~~bash
curl -i http://localhost:8080/api/reports

curl -i -u reader:demo-only \
  http://localhost:8080/api/reports
~~~

Kỳ vọng: request đầu **401** do chưa xác thực, request thứ hai **200** khi Basic credentials đúng và người dùng có `SCOPE_reports.read`.

Thử admin và đường dẫn ngoài matcher:

~~~bash
curl -i -u reader:demo-only \
  http://localhost:8080/api/admin/stats

curl -i -u api-admin:demo-only \
  http://localhost:8080/api/admin/stats

curl -i -u api-admin:demo-only \
  http://localhost:8080/shadow
~~~

Kỳ vọng: **403**, **200**, **403** tương ứng. `/shadow` thực sự có controller, nhưng bị catch-all denyAll. Không đưa password demo vào tài liệu vận hành hoặc shell history thực tế; lệnh trên chỉ dành cho máy local học tập. Với credentials thật luôn dùng HTTPS và cơ chế quản lý bí mật.

Các kết quả trên là **kỳ vọng theo cấu hình**, không phải log thực thi đã được kiểm chứng trong môi trường hiện tại.

## 6. Kiểm thử HTTP với MockMvc và spring-security-test

Một bài kiểm thử nhiều chain cần kiểm tra **cả trường hợp được cho phép lẫn trường hợp bị từ chối**, đặc biệt là URL giao nhau và URL không có rule. Chỉ test `200 OK` ở endpoint public không đủ.

### 6.1. src/test/java/demo/MultiChainSecurityTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpMethod;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MultiChainSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicApiDoesNotRequireAuthentication() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.resource").value("public-api"));
    }

    @Test
    void protectedApiRejectsAnonymousUser() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void reportScopeAllowsAccessToReports() throws Exception {
        mvc.perform(get("/api/reports")
                .with(user("reader").authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read")
                )))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.resource").value("reports"));
    }

    @Test
    void unrelatedRoleDoesNotGrantReportScope() throws Exception {
        mvc.perform(get("/api/reports")
                .with(user("web-user").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminChainWinsOverOverlappingApiChain() throws Exception {
        // Dù có scope đọc báo cáo, user không có ROLE_API_ADMIN.
        mvc.perform(get("/api/admin/stats")
                .with(user("reader").authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read")
                )))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleCanAccessAdminChain() throws Exception {
        mvc.perform(get("/api/admin/stats")
                .with(user("admin").roles("API_ADMIN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.resource").value("admin-stats"));
    }

    @Test
    void unknownAdminPathIsDeniedEvenForAdmin() throws Exception {
        mvc.perform(get("/api/admin/new-operation")
                .with(user("admin").roles("API_ADMIN")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownApiPathIsDeniedRatherThanFallingThrough() throws Exception {
        mvc.perform(get("/api/not-configured")
                .with(user("reader").authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read")
                )))
            .andExpect(status().isForbidden());
    }

    @Test
    void unlistedHttpMethodIsDenied() throws Exception {
        // Token test được đưa vào để cô lập nguyên nhân từ chối
        // là policy anyRequest denyAll chứ không chỉ vì thiếu CSRF.
        mvc.perform(post("/api/reports")
                .with(user("reader").authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read")
                ))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void healthIsPublicThroughFallbackChain() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("up"));
    }

    @Test
    void mappedButUnlistedControllerIsBlockedByFallback()
            throws Exception {
        mvc.perform(get("/shadow")
                .with(user("admin").roles("API_ADMIN")))
            .andExpect(status().isForbidden());
    }

    @Test
    void feedbackRequiresCsrfEvenWithCorrectRole() throws Exception {
        mvc.perform(post("/web/feedback")
                .with(user("web-user").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void feedbackRequiresRoleEvenWithCsrf() throws Exception {
        mvc.perform(post("/web/feedback")
                .with(user("reader").authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read")
                ))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void feedbackWithRoleAndCsrfIsAccepted() throws Exception {
        mvc.perform(post("/web/feedback")
                .with(user("web-user").roles("USER"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("feedback-received"));
    }
}
~~~

**Tại sao dùng `.with(user(...))`?** Đây là test request processor của `spring-security-test`: gắn test principal và authorities vào request cho mục tiêu **authorization integration**. Nó không gửi Basic credentials thật và không chứng minh user details/password encoder hoạt động đúng. Có thể dùng `httpBasic("reader","demo-only")` trong một test khác nếu muốn xác minh cơ chế HTTP Basic end-to-end trong MockMvc.

**Tại sao ở test POST bị denyAll lại dùng `.with(csrf())`?** Nếu thiếu CSRF token, request có thể bị từ chối **trước khi** `AuthorizationFilter` xét `anyRequest().denyAll()`. Thêm token hợp lệ giúp test xác nhận cụ thể rằng **rule cho method chưa khai báo** là nguyên nhân từ chối. Đây là kỹ thuật cô lập biến khi viết security tests.

### 6.2. Chạy các test

~~~bash
mvn test
~~~

Kỳ vọng **14 test** được chạy: các case public, anonymous, scope, role, chain overlap, unknown path, method chưa khai báo, fallback và CSRF. Nếu chạy đúng nguồn trên, mục tiêu là **0 failures, 0 errors**. Đây là **kết quả dự kiến**, không phải kết quả thực thi đã được quan sát trong môi trường làm bài.

Chạy riêng test class:

~~~bash
mvn -Dtest=MultiChainSecurityTest test
~~~

**Một test có thể xanh sai** nếu cấu hình test không thực sự tích hợp Spring Security filters. `@SpringBootTest` + `@AutoConfigureMockMvc` trong ví dụ sử dụng application context đầy đủ cùng bộ filter của ứng dụng. Nếu dùng `MockMvcBuilders.standaloneSetup(...)`, cần chủ động tích hợp Spring Security phù hợp thay vì nghĩ Spring Security tự được áp dụng.

## 7. Cách chứng minh đúng chain được chọn, không chỉ đo HTTP status

Một status code đơn lẻ **không chứng minh** chain nào được chọn:

- **401** có thể do nhiều entry point hoặc cơ chế authentication khác nhau.
- **403** có thể do `denyAll`, thiếu role/scope, CSRF token sai hoặc authorization theo resource.
- **200** có thể do endpoint public được phép, do test bỏ security filters hoặc do một chain có policy quá rộng.
- **404** có thể do MVC không tìm thấy handler, nhưng cũng có thể bị che bởi security policy chạy trước routing.

Để kiểm chứng chain selection, dùng **ma trận các đường dẫn giao nhau** và đặt những policy khác nhau có thể phân biệt bằng behavior:

1. `/api/admin/stats` với `SCOPE_reports.read` phải **403**, vì chain chuyên biệt yêu cầu `ROLE_API_ADMIN`.
2. Cùng URL với `ROLE_API_ADMIN` phải **200**.
3. `/api/reports` với `SCOPE_reports.read` phải **200**, vì vào API chain chung.
4. `/api/not-configured` với user đã xác thực phải **403**, vì chain API đã match nhưng không có allow rule.
5. `/shadow` với user đã xác thực phải **403** dù MVC controller có mặt, vì catch-all denyAll.
6. `/health` anonymous phải **200**, chứng minh fallback vẫn cho phép các endpoint chủ đích public.

Khi cần quan sát chi tiết hơn trong môi trường phát triển, có thể bật logging/trace có kiểm soát cho Spring Security, xem `FilterChainProxy` và các matcher để hiểu path nào đang được bảo vệ. **Không log Authorization header, session cookie, JWT hay secret thật.**

Nếu cần test cấu trúc chain ở mức đơn vị, có thể lấy `FilterChainProxy` từ Spring context và kiểm tra chain/matchers qua API mà **phiên bản Spring Security thực tế hỗ trợ**. Tránh phụ thuộc log string/version-internal API làm test hợp đồng duy nhất; kiểm thử hành vi HTTP vẫn là bảo chứng chính.

### 7.1. Với nhiều chain, số lượng filter có thể khác nhau

Chuỗi A có thể có BasicAuthenticationFilter, chuỗi B có OAuth2 Resource Server filters và chuỗi C có form login/CSRF. Vì chỉ **một chain** được chọn theo request, endpoint đi vào sai chain có thể dùng sai kiểu authentication, khác CSRF, khác session policy, khác security headers hoặc khác entry point.

Vì vậy security tests phải bao phủ **nhiều chiều**: path, method, anonymous/authenticated, role/scope, CSRF, request headers và các dispatcher types quan trọng.

## 8. Endpoint chưa khớp: ba trường hợp thường bị nhầm

### 8.1. Không khớp controller nhưng khớp SecurityFilterChain

Request `GET /api/not-configured`:

- Khớp `securityMatcher("/api/**")`.
- Không khớp các rule `GET /api/public` và `GET /api/reports`.
- Khớp `anyRequest().denyAll()`.
- Nếu đã authenticated, thường bị trả **403 trước khi DispatcherServlet kiểm tra có handler hay không**.

**Đừng viết test mặc định yêu cầu 404** cho mọi endpoint không có MVC mapping. Khi security hoạt động trước routing, authentication và authorization có thể chặn trước. Muốn test 404 thật sự, phải chọn một đường dẫn **được security cho phép đi tới MVC** nhưng không có handler, hoặc kiểm thử trực tiếp lớp MVC theo cách có chủ đích. Không mở một public path trong production chỉ để ép nhận 404 nếu nó không thuộc hợp đồng API.

### 8.2. Có controller nhưng nằm ngoài mọi SecurityFilterChain

Nếu không có catch-all chain, request `GET /shadow` có thể đi qua `FilterChainProxy` mà không được áp Spring Security filters rồi tới controller `/shadow`. Đó là **lỗ hổng phạm vi bảo vệ** nếu controller dựa hoàn toàn vào Spring Security.

Một bộ test chỉ gọi `/api/reports` không phát hiện được điều này. Hãy có **canary endpoint đã được MVC map nhưng phải bị từ chối**, giống `/shadow`, hoặc test danh sách endpoint ngoài phạm vi đã kiểm soát.

### 8.3. Có controller và khớp chain nhưng thiếu quyền

Request `GET /api/admin/stats` với scope đọc báo cáo:

- Khớp **admin chain**.
- Path có controller thật.
- User thiếu `ROLE_API_ADMIN`.
- Trả **403** khi đã có authentication nhưng không đủ quyền.

Đây là **authorization failure**, khác với routing 404 hoặc authentication failure. Không sửa bằng cách thêm `permitAll` tùy tiện; điều chỉnh role mapping, nguồn authentication hoặc policy nếu yêu cầu nghiệp vụ thực sự khác.

## 9. Chọn fallback “permit hay deny” thế nào?

Một catch-all chain thường nên có rule rõ ràng:

~~~java
@Bean
@Order(999)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/health").permitAll()
        .anyRequest().denyAll()
    ).httpBasic(Customizer.withDefaults());

    return http.build();
}
~~~

Đây là **đoạn bean minh họa khác**, không đồng thời thêm vào project mục 5 vốn đã có `fallbackChain`. Nếu thêm hai catch-all chain không có thiết kế, chain ưu tiên trước có thể làm chain sau trở nên không thể match.

**Hai chiến lược phổ biến:**

- **Default deny:** `anyRequest().denyAll()`. Endpoint mới phải được thêm vào allowlist/role policy rõ ràng. An toàn khi security boundary nhạy cảm và hệ thống được quản trị theo route inventory.
- **Default authenticated:** `anyRequest().authenticated()`. Endpoint mới cần đăng nhập nhưng không nhất thiết đủ quyền nghiệp vụ. Có thể hữu ích cho web app nơi phần lớn trang dùng cùng policy, nhưng **không bảo đảm role, tenant hoặc ownership**; phải có kiểm tra chi tiết.

**Tránh** `anyRequest().permitAll()` làm fallback chung cho ứng dụng có endpoint nhạy cảm, trừ khi đó thực sự là hợp đồng public rõ ràng. Nó có thể tạo lỗ hổng khi route mới được thêm mà không ai cập nhật security policy.

Nếu muốn vài endpoint public như health/static assets, cho phép **đúng path/method** theo nghiệp vụ và ghi test. Đặt `denyAll` cuối để tránh vô tình nới quyền.

## 10. SecurityMatcher, servlet path, request dispatch và proxy

### 10.1. Matcher phải phản ánh path thực mà Spring Security nhìn thấy

Với Servlet app có context path, servlet path, nhiều DispatcherServlet hoặc custom `PathPatternParser`, matcher có thể khác giả định khi nhìn URL trong browser. Khi dùng `requestMatchers(String...)`, Spring Security lựa chọn cách tạo `RequestMatcher` dựa trên môi trường ứng dụng và phiên bản; không nên giả định toàn bộ là raw string prefix hoặc tùy ý chuyển sang thư viện Ant matcher cũ mà chưa kiểm chứng.

Các yếu tố cần xét:

- **Context path:** URL công khai `/myapp/api/reports` không nhất thiết có nghĩa pattern security phải bắt đầu bằng `/myapp`. Kiểm chứng cách matcher được framework đánh giá.
- **Servlet path:** với nhiều servlet mapping, cần matcher phù hợp hoặc `MvcRequestMatcher` được cấu hình cùng `HandlerMappingIntrospector` khi trường hợp đó được hỗ trợ.
- **Trailing slash và path normalization:** `/api`, `/api/`, `/api//reports`, encoding `%2F` hoặc ký tự semicolon có thể được server/container xử lý khác nhau. Không thiết kế bảo mật dựa vào normalize path bằng tay.
- **Forwarded headers:** proxy/load balancer phải được tin cậy đúng. Không tin `X-Forwarded-*` do client Internet tự thêm; header ảnh hưởng đến scheme/host/redirect nhưng không nên làm mất ranh giới authentication.
- **Case sensitivity:** `/API/reports` và `/api/reports` có thể được route khác nhau. Kiểm thử cả những biến thể có nguy cơ đi ngoài matcher.
- **Đường dẫn API mới:** một endpoint không thuộc pattern `/api/**` (ví dụ `/v2/reports`) phải được fallback bảo vệ cho đến khi có rule explicit.

**Lời khuyên:** kiểm thử qua URL thật như client sẽ gọi, không tự suy luận từ tên controller hoặc base path trong source.

### 10.2. DispatcherType: REQUEST, ERROR, FORWARD

Một HTTP request có thể phát sinh dispatch nội bộ, ví dụ tới `/error` khi Controller phát sinh lỗi, hoặc forward tới view. Security filter có thể được đăng ký với nhiều dispatcher type tùy runtime và cấu hình; security matching/authorization có thể áp dụng thêm cho dispatch mới.

Hậu quả thường gặp: một controller được phép chạy nhưng khi render lỗi, `ERROR` dispatch tới `/error` lại bị catch-all `denyAll`, khiến response cuối thành 403 hoặc 401 thay vì mã lỗi dự kiến. Cần thiết kế error handling phù hợp.

Một lựa chọn **tùy hoàn cảnh** là cho phép `DispatcherType.ERROR` hoặc một error endpoint cụ thể:

~~~java
// Trích đoạn minh họa trong authorizeHttpRequests:
.dispatcherTypeMatchers(jakarta.servlet.DispatcherType.ERROR).permitAll()
~~~

Chỉ áp dụng khi bạn đã đánh giá vì sao error dispatch an toàn, không mở các URL nhạy cảm ngoài ý muốn. `FORWARD` cũng có thể cần thiết với MVC/JSP tùy kiến trúc, nhưng không nên cho phép mọi forward mù quáng để vượt qua security.

**Không nên** coi mọi request 401/403 tại `/error` là thiếu role của endpoint gốc; hãy xem dispatcher type và dispatch path.

### 10.3. Multiple filter chains và điểm vào login

Nếu một chain có `securityMatcher("/web/**")` rồi cấu hình `formLogin()`, các endpoint mặc định `/login` (GET/POST) có thể **nằm ngoài phạm vi chain đó**. Khi ấy login flow bị đứt dù rule `anyRequest().authenticated()` có vẻ hợp lý.

Để dùng form login hoặc logout với chain hẹp:

1. Xác định rõ URL login processing, default login page và logout.
2. Bảo đảm những URL đó **được match bởi chain có filter liên quan**, hoặc đưa chúng vào vùng match đúng.
3. Kiểm thử GET login, POST login + CSRF, POST logout và redirect.
4. Tránh chain rộng hơn có độ ưu tiên cao chiếm URL callback/login của chain khác.

Ví dụ bài này dùng HTTP Basic để không phải thiết kế login page/session trong nhiều chain. Với OAuth2 Login cũng phải kiểm tra `/oauth2/authorization/{registrationId}` và `/login/oauth2/code/{registrationId}` có thuộc đúng chain không.

## 11. Những lỗi MockMvc test rất dễ mắc

### 11.1. Không chạy filter nhưng vẫn báo 200

Nếu dùng:

~~~java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new DemoController())
    .build();
~~~

đây chỉ là snippet minh họa; `standaloneSetup` không tự đưa Spring Security `FilterChainProxy` vào như ví dụ `@SpringBootTest` đầy đủ. Test `GET /shadow` có thể trả 200 và khiến bạn tưởng security cho phép, trong khi thực tế bạn **không kiểm thử security**.

Nếu dùng standalone MockMvc, phải có security configuration/filter chain và tích hợp `springSecurity()`/filter phù hợp, hoặc dùng `@AutoConfigureMockMvc` với Spring ApplicationContext khi cần kiểm thử HTTP security thật.

**Không cấu hình `@AutoConfigureMockMvc(addFilters = false)`** khi mục tiêu là xác minh filter chain; nó có thể bỏ qua chính các filter bạn cần kiểm tra.

### 11.2. Nhầm mock user với Basic credential thật

~~~java
.with(user("admin").roles("API_ADMIN"))
~~~

tạo principal test. Không kiểm chứng PasswordEncoder hay BasicAuthenticationFilter giải mã credentials.

Muốn kiểm tra HTTP Basic thật, có thể dùng helper của spring-security-test:

~~~java
// Đoạn thêm vào test có mvc và in-memory user details:
mvc.perform(get("/api/reports")
        .with(httpBasic("reader", "demo-only")))
    .andExpect(status().isOk());
~~~

Cần thêm static import:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
~~~

Đoạn trên là snippet bên trong test method, không phải file Java độc lập. Với production không dùng password demo và không gọi HTTP Basic qua kết nối không TLS.

### 11.3. Không phân biệt CSRF 403 với authorization 403

Với POST và CSRF bật:

~~~java
mvc.perform(post("/web/feedback")
        .with(user("web-user").roles("USER")))
    .andExpect(status().isForbidden());
~~~

Đây là test thiếu CSRF. Muốn test quyền, thêm `.with(csrf())` để bảo đảm request vượt qua kiểm tra token trước, rồi xác nhận role.

Nếu một test POST trả 403 mà bạn quên `csrf()`, nó **không chứng minh** `hasRole` hay `denyAll` đang hoạt động.

### 11.4. Sử dụng @WithMockUser và .with(user()) khác nhau thế nào?

- `@WithMockUser`: đặt user cho test qua Spring TestContext listener; hữu ích khi nhiều lời gọi trong một test dùng cùng principal.
- `.with(user(...))`: gắn user vào **một MockMvc request cụ thể**; rất tiện khi một test cần gọi cùng URL với nhiều vai trò khác nhau.

Đừng mặc định một principal giả từ request trước sẽ được “đăng nhập bền vững” cho request sau. MockMvc test không chứng minh session/login lifecycle thật trừ khi bạn kiểm tra rõ cookie/session và flow phù hợp.

### 11.5. Test 200 không đủ; test cả denial

Bộ test phải có tối thiểu: anonymous → 401/redirect; authenticated không đủ quyền → 403; đủ quyền → 200; URL không khai báo → deny; path giao nhau → đúng chain; POST thiếu CSRF → 403; POST hợp lệ → thành công.

Nếu chỉ test positive path, một việc vô tình đổi `anyRequest().denyAll()` thành `permitAll()` có thể **không làm test hiện tại thất bại**.

## 12. Một cách kiểm tra vùng phủ bảo mật có hệ thống

Có thể tạo **ma trận endpoint** trong tài liệu dự án, không cần thêm dependency riêng để hiểu nguyên tắc:

| Nhóm | URL điển hình | Method | Kỳ vọng anonymous | User thiếu quyền | User đủ quyền |
| --- | --- | --- | --- | --- | --- |
| Public API | `/api/public` | GET | 200 | 200 | 200 |
| API cần scope | `/api/reports` | GET | 401 | 403 | 200 |
| Admin API | `/api/admin/stats` | GET | 401 | 403 | 200 |
| Endpoint API chưa khai báo | `/api/not-configured` | GET | 401 | 403 | 403 theo denyAll |
| Method mới chưa khai báo | `/api/reports` | POST + CSRF | 401/403 tùy filter xử lý đầu tiên | 403 | 403 |
| Web action | `/web/feedback` | POST + CSRF | 401/403 tùy filter xử lý đầu tiên | 403 | 200 |
| Health public | `/health` | GET | 200 | 200 | 200 |
| Controller ngoài allowlist | `/shadow` | GET | 401 | 403 | 403 |

**Chú ý:** HTTP status còn phụ thuộc entry point và thứ tự filter; với POST thiếu token, `CsrfFilter` có thể trả 403 trước cơ chế authentication. Do đó bảng cần ghi rõ có CSRF hợp lệ không, và test phải cô lập điều kiện khi cần. Không đặt kỳ vọng cứng “mọi anonymous request đều 401” cho mọi phương thức và chain.

### 12.1. Test bất biến khi thêm endpoint mới

Khi thêm `/api/reports/export`:

1. Xác định endpoint thuộc chain nào.
2. Viết test **bị từ chối** trong trường hợp chưa cấp policy.
3. Thêm rule đúng method/scope/role nếu chức năng được phép.
4. Viết test positive và negative cho chính rule đó.
5. Kiểm tra route không làm một matcher rộng hơn “ăn” đường dẫn chuyên biệt.
6. Với mutation endpoint, test CSRF/threat model và object-level authorization.
7. Chạy suite theo profile/reverse proxy path/context path quan trọng.

Nếu thiếu fallback chain, test chỉ ở nhóm API có thể không nhận ra `/new-private-path` nằm ngoài security. Hãy giữ một test kiểm soát vùng phủ bằng controller thực sự tồn tại mà không được allowlist và bị từ chối.

## 13. Các tình huống mở rộng cần lưu ý

### 13.1. Chain cho API JWT và chain web session

Trong hệ thống thật có thể có:

~~~text
@Order(1): /api/** -> Resource Server JWT
@Order(2): /web/** -> form login / session cookie
@Order(3): catch-all -> denyAll
~~~

Đây là **sơ đồ**; không phải code đã triển khai. Với API dùng bearer token ở Authorization header, `JwtAuthenticationConverter` và JWT validator thường quyết định authorities; với web session, role đến từ `UserDetailsService` hoặc provider login.

Cần test riêng:

- API bearer không có token, token sai, issuer/audience sai, scope thiếu/đủ.
- Web session anonymous, login/logout, CSRF, session fixation, cookie policy.
- URL giao nhau, callback login, các endpoint Actuator/static/error không rơi ngoài chuỗi.
- Trường hợp gửi Basic/session credential vào API mà chỉ định chấp nhận bearer: không vô tình tạo cơ chế auth phụ.
- Kết quả error/forward dispatch khi có nhiều chain.

### 13.2. @Order thấp hơn không “cứu” một request đã bị deny ở chain cao hơn

Nếu chain 1 match `/api/admin/stats` rồi `denyAll`, Spring Security **không thử tiếp** chain 2 với `/api/**` để tìm `permitAll`. Điều này ngăn kiểu fallback authorization “cứ thử tiếp đến khi có rule cho phép”. Muốn truy cập, phải thay đổi rule của **chain thực sự được chọn**, không thêm rule ở chain thấp hơn và kỳ vọng nó được dùng.

### 13.3. Security headers, CORS, filters không chỉ là authorization

Khi một request không match SecurityFilterChain, không chỉ mất `AuthorizationFilter`; nó còn có thể bỏ qua các filter liên quan đến **security headers, CSRF, session/context, authentication**. Nếu ứng dụng có custom servlet filters bên ngoài `FilterChainProxy`, chúng có thể vẫn chạy, nhưng không được tính như bằng chứng Spring Security đã bảo vệ request.

Vì vậy đừng nói “controller không cần auth” chỉ vì nhận 200 từ một request chưa match chain. Hãy kiểm thử vùng phủ và các header/behavior cần thiết.

### 13.4. @PreAuthorize không thay thế hoàn toàn HTTP chain

Method security có thể giúp giảm rủi ro khi HTTP matcher thiếu, nhưng không đảm bảo mọi controller/service đều được bảo vệ. Những phương thức không có annotation, self-invocation bypass proxy hoặc các path không đi qua service bảo vệ có thể vẫn lộ. Trách nhiệm HTTP chain matching và method authorization phải được kiểm thử độc lập.

## 14. Quy trình kiểm tra và debug

Khi một endpoint trả kết quả bất ngờ:

1. **Xác nhận request thực**: URL, HTTP method, context path, headers cần thiết, dispatcher type; không log secret.
2. **Liệt kê các SecurityFilterChain cấu hình** và `@Order`; tìm chain đầu tiên match request.
3. **Kiểm tra securityMatcher** của chain đó, không bắt đầu bằng việc đọc mỗi `requestMatchers`.
4. **Kiểm tra authorization rule đầu tiên khớp** trong `authorizeHttpRequests`; xác nhận có fallback `denyAll` hoặc policy rõ ràng.
5. **Kiểm tra authentication**: anonymous, authenticated, authorities `ROLE_`/`SCOPE_`, token/Basic/session đúng cơ chế.
6. **Nếu POST**, xác nhận CSRF token/chính sách của chain, không nhầm 403 do CSRF với 403 do role.
7. **Kiểm tra MVC routing** chỉ sau khi chắc request qua được security; 404 không đồng nghĩa một URL đã được bảo vệ an toàn.
8. **Chạy test giao nhau**: path chuyên biệt, path tổng quát, path ngoài cả hai, method mới và user thiếu/đủ quyền.
9. **Xem `ERROR`/`FORWARD` dispatch** nếu mã lỗi cuối không khớp nguyên nhân ban đầu.
10. **Kiểm tra FilterChainProxy thật có trong MockMvc**; không kết luận từ test đã vô tình bỏ filter.
11. **Đối chiếu log có kiểm soát** tại tầng Spring Security/servlet container nếu vẫn không rõ; xóa hoặc che token/cookie/password.
12. **Thêm regression test** mô tả đúng path/role/method dẫn tới bug trước khi sửa policy.

## 15. Các lỗi thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Đặt `/api/**` ở order 1, `/api/admin/**` ở order 2. | API chain rộng match trước, admin chain không được thử. | Đặt chain hẹp trước, test đường dẫn giao nhau. |
| Có `anyRequest().denyAll()` trong chain API rồi nghĩ mọi URL đều bảo vệ. | Nó chỉ áp cho URL đã match API chain. | Thêm catch-all SecurityFilterChain không giới hạn matcher. |
| Cấu hình `requestMatchers("/admin/**")` trong chain giới hạn `securityMatcher("/api/**")`. | Rule không mở rộng phạm vi chain. | Đổi chain matcher hoặc tạo chain riêng. |
| Dùng `web.ignoring()` cho endpoint công khai. | Request bỏ qua nhiều Spring Security filters khác. | Dùng `permitAll()` trong chain đúng nếu phù hợp. |
| Bỏ `anyRequest` hoặc để policy rộng khó hiểu. | Endpoint/method mới không có hợp đồng rõ ràng. | Đặt rule explicit, fallback `denyAll` theo chính sách. |
| Coi 404 là bằng chứng URL được bảo vệ. | 404 thuộc routing; có thể khác security behavior. | Dùng test endpoint thực sự mapped + denial. |
| Coi mọi 403 là lỗi role. | CSRF cũng thường trả 403. | Với POST, thêm `csrf()` trong test authorization. |
| `MockMvc` chạy `addFilters=false`. | Test không kiểm tra security chain. | Bật filters và dùng Spring Security Test. |
| Chỉ dùng mock user rồi tuyên bố Basic/JWT login đúng. | Không xác minh cơ chế credentials/token thật. | Viết authentication integration test riêng. |
| Cho `anyRequest().permitAll()` ở catch-all mà không đánh giá. | Path mới có thể public ngoài ý muốn. | Dùng default deny hoặc authenticated theo hợp đồng. |
| Một chain form login quá hẹp không match `/login`. | Login filter/page không xử lý đúng URL. | Bao phủ login/logout/callback path và viết test. |
| Không kiểm tra context path / servlet path / dispatch type. | Matcher khác URL browser hoặc error/forward làm đổi kết quả. | Kiểm tra theo môi trường Servlet thật. |
| Tắt CSRF cho API sử dụng HTTP Basic trong browser vì thấy chữ API. | Browser có thể gửi Basic credential tự động. | Giữ CSRF hoặc đánh giá threat model kỹ trước khi tắt. |
| Đổi status code mà không kiểm tra chain selection. | Che triệu chứng, không sửa matcher/authorization gốc. | Trace chain đầu tiên khớp và rule tương ứng. |

## 16. Checklist nghiệm thu

- [ ] Có ít nhất một test cho đường dẫn nằm trong **hai matcher chồng lấn**.
- [ ] Chain chuyên biệt có `@Order` cao hơn (giá trị nhỏ hơn) chain tổng quát.
- [ ] Mỗi chain có rule cuối rõ ràng cho request/method chưa khai báo.
- [ ] Có catch-all chain bao phủ những URL không thuộc chain chuyên biệt.
- [ ] Catch-all dùng `denyAll` hoặc chính sách default được phê duyệt.
- [ ] Có test controller **thực sự mapped** nhưng bị catch-all từ chối.
- [ ] Có test API path chưa khai báo và HTTP method chưa được phép.
- [ ] Có test anonymous → cần authentication; user thiếu quyền → denied; user đủ quyền → 200.
- [ ] Với POST/session/Basic browser credentials có kiểm tra CSRF và tách nguyên nhân 403.
- [ ] MockMvc chạy filter chain thật; không dùng `addFilters=false` cho security test.
- [ ] Test không phụ thuộc vào principal còn sót lại hoặc thứ tự chạy giữa các ca.
- [ ] Đã xét login/logout/OAuth callback/error/forward và context path nếu ứng dụng dùng.
- [ ] Không dùng `web.ignoring()` làm cách “nới quyền” cho endpoint động.
- [ ] Authentication và authorization theo object/tenant được test ngoài matcher URL nếu dữ liệu nhạy cảm.
- [ ] Không log credentials, access token, session cookie hoặc nội dung bearer header.

## 17. Câu hỏi tự kiểm tra

**Câu 1:** Có `securityMatcher("/api/**")` và `anyRequest().denyAll()` trong chain đó. Request `/web/admin` được bảo vệ chưa?

**Trả lời:** Không tự động. `anyRequest` chỉ xét request đã vào chain `/api/**`. Nếu không có chain khác match `/web/admin`, request không được Spring Security filters bảo vệ. Cần catch-all chain hoặc thiết kế matcher bao phủ đường dẫn đó.

**Câu 2:** Chain `/api/**` có order 1, chain `/api/admin/**` order 2; request `/api/admin/stats` chạy chuỗi nào?

**Trả lời:** Chain `/api/**` ở order 1 sẽ match trước. Spring không tiếp tục sang admin chain. Phải đảo ưu tiên để chain chuyên biệt được chọn.

**Câu 3:** Vì sao `GET /api/not-configured` có thể trả 403 thay vì 404?

**Trả lời:** Vì chain API match request và `anyRequest().denyAll()` từ chối trước khi DispatcherServlet tìm controller. 403 không chứng minh endpoint tồn tại; 404 không tự chứng minh endpoint được bảo vệ.

**Câu 4:** Một test POST trả 403 khi không kèm CSRF token. Có thể kết luận `hasRole` đã từ chối không?

**Trả lời:** Chưa. `CsrfFilter` có thể trả 403 trước authorization. Để kiểm tra role, bổ sung token test hợp lệ bằng `csrf()` và thay đổi authority.

**Câu 5:** Vì sao nên có controller `/shadow` mapped nhưng bị fallback deny?

**Trả lời:** Nó giúp kiểm tra có một chain dự phòng thật sự bao phủ path ngoài chuỗi chuyên biệt; nếu bỏ fallback và controller trở nên public, regression test sẽ phát hiện.

**Câu 6:** `@WithMockUser` hoặc `.with(user())` có xác minh mật khẩu/Basic authentication hoặc JWT signature không?

**Trả lời:** Không. Chúng giả authentication để kiểm tra authorization. Cần test cơ chế credentials/token riêng khi mục tiêu là xác thực thật.

**Câu 7:** Nên luôn dùng `anyRequest().permitAll()` cho fallback để không bị 404/403 khó hiểu?

**Trả lời:** Không. Với hệ thống có endpoint nhạy cảm, đó là default-open rất dễ bỏ sót policy cho route mới. `denyAll` hoặc quy tắc `authenticated` theo hợp đồng thường an toàn hơn.

**Câu 8:** Tại sao cần kiểm tra `/login` khi một chain chỉ match `/web/**`?

**Trả lời:** Vì login page và login processing URL có thể nằm ngoài `/web/**`; form login filter của chain đó sẽ không xử lý request. Cần bao phủ đúng login/logout/callback và viết test.

---

**Ghi nhớ cuối bài:** Với nhiều `SecurityFilterChain`, Spring Security Servlet **chỉ dùng chuỗi đầu tiên match**. `securityMatcher` chọn chuỗi; `requestMatchers` chọn rule trong chuỗi; `anyRequest().denyAll()` bảo vệ các request chưa được cấp phép trong chuỗi; và **catch-all chain** bảo vệ các endpoint chưa khớp bất kỳ chuỗi chuyên biệt nào. Muốn kiểm thử đúng, phải thử cả path giao nhau, path mới, method mới, controller mapped nhưng bị deny, anonymous/role/scope và CSRF; không kết luận an toàn từ một HTTP status đơn lẻ.