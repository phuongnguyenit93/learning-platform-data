# spring-security-test, MockMvc và tích hợp filter chain thật

Trong ứng dụng **Spring Security Servlet + Spring MVC**, một bài kiểm thử HTTP có thể trả `200 OK` vì controller được gọi trực tiếp qua MockMvc nhưng **không hề chạy chính sách bảo mật**. Đó là lỗi kiểm thử dễ tạo cảm giác an toàn giả: các assertion về JSON vẫn pass, trong khi `SecurityFilterChain`, authentication, authorization hoặc CSRF chưa được kiểm tra.

Mục tiêu của bài học là cấu hình `spring-security-test` cùng `MockMvc` sao cho request đi qua **`FilterChainProxy` thật từ `ApplicationContext`**, rồi chứng minh bằng test rằng request không có credentials bị chặn, credentials sai bị từ chối, credentials hợp lệ nhưng thiếu quyền nhận `403`, quyền đầy đủ truy cập được controller, và CSRF hoạt động với phương thức ghi.

**Phạm vi ví dụ:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, JUnit Jupiter (JUnit 5), Spring MVC/Servlet và HTTP Basic. Không dùng mô hình reactive `WebFlux`/`WebTestClient` trong ví dụ runnable. Trên Spring Boot 4.x, một số package test auto-configuration thay đổi; cần đọc Javadoc đúng phiên bản thay vì sao chép nguyên import của Boot 3.5.

## 1. Ba lớp kiểm thử phải phân biệt

| Kiểu kiểm thử | Thiết lập tiêu biểu | Có chain bảo mật của ứng dụng? | Dùng khi |
| --- | --- | --- | --- |
| Controller đơn lẻ | `MockMvcBuilders.standaloneSetup(controller)` | **Không tự động**; chỉ có filter nào được thêm thủ công | Kiểm thử mapping, validation, serialization/controller logic cô lập |
| Web MVC slice | `@WebMvcTest(ReportController.class)` + `MockMvc` | Có thể có Spring Security test infrastructure, nhưng **chưa chắc có `SecurityFilterChain` riêng của ứng dụng**; phải kiểm tra/import cấu hình cần thiết | Kiểm thử nhanh controller và policy web đã khai báo rõ |
| Full application context | `@SpringBootTest` + `@AutoConfigureMockMvc` | **Có**, khi filter registration được bật (mặc định `addFilters=true`) và cấu hình app được nạp | Kiểm thử tích hợp HTTP với security filters, user store, service/method security |
| Live HTTP end-to-end | `@SpringBootTest(webEnvironment=RANDOM_PORT)` + HTTP client thật | Có, qua embedded server | Khi cần kiểm tra network/port, container behavior, reverse proxy hay cookie thực tế |

**`MockMvc` không khởi động socket HTTP.** Nó sử dụng mock request/response của Servlet API để đi qua Spring MVC và filter chain được đăng ký. Vì vậy “filter chain thật” trong ngữ cảnh MockMvc có nghĩa là **các bean `SecurityFilterChain` của ứng dụng được `FilterChainProxy` thực thi**, không phải trình duyệt, TLS hay HTTP server thực. Những tình huống đó cần bài kiểm thử chạy server thật.

Không suy ra một request đã đi qua bảo mật chỉ vì:
- Có dependency `spring-security-test` trong `pom.xml`.
- Test dùng `@WithMockUser` hoặc `with(user("..."))`.
- MockMvc trả `200` cho endpoint.
- Có annotation `@EnableMethodSecurity` nhưng chỉ gọi controller bằng `new`.

## 2. Các thành phần phối hợp với nhau

~~~text
JUnit test
  |
  +-- @SpringBootTest: tải ApplicationContext và bean thật
  +-- @AutoConfigureMockMvc: tạo MockMvc, đăng ký filters (mặc định)
  |
  v
MockMvc.perform(request)
  |
  v
Spring Servlet Filter chain
  |
  +-- DelegatingFilterProxy / springSecurityFilterChain
  |       |
  |       '-- FilterChainProxy
  |             |
  |             +-- SecurityFilterChain phù hợp với request
  |             +-- Authentication filters: HTTP Basic, ...
  |             +-- CsrfFilter (với request cần CSRF)
  |             '-- AuthorizationFilter (quy tắc URL)
  |
  v
DispatcherServlet -> Controller -> Spring-managed Service
                                  |
                                  '-- Method security (nếu bật)
  |
  v
MockHttpServletResponse -> status, header, JSON, SecurityContext
~~~

`spring-security-test` cung cấp:
- Request post-processors: `httpBasic(username, password)`, `user(...)`, `anonymous()`, `csrf()`, `jwt()`/`oauth2Login()` khi có mô-đun liên quan.
- Annotation test: `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails` cùng cơ chế điền `SecurityContext` trước bài test.
- Matchers/handlers hỗ trợ kiểm tra security, như `authenticated()`, `unauthenticated()`.
- `SecurityMockMvcConfigurers.springSecurity()` cho trường hợp bạn tự khởi tạo `MockMvc`.

`spring-security-test` **không tự thêm policy thực của ứng dụng** vào một controller được dựng bằng `standaloneSetup`, cũng không chứng minh mật khẩu thật qua `@WithMockUser`.

## 3. Thiết lập dependency chính xác

Với dự án Maven Spring Boot **3.5.x** đang kế thừa Spring Boot parent hoặc import BOM, khai báo các dependency sau; phiên bản starter và security-test được quản lý đồng bộ bởi Boot:

~~~xml
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
~~~

Đây là **đoạn dependency của `pom.xml`**, không phải `pom.xml` độc lập; dự án phải có Spring Boot parent/BOM, plugin build và cấu hình Java 17 phù hợp. Nếu build Gradle, mục tiêu tương đương là `implementation("org.springframework.boot:spring-boot-starter-web")`, `implementation("org.springframework.boot:spring-boot-starter-security")`, `testImplementation("org.springframework.boot:spring-boot-starter-test")`, `testImplementation("org.springframework.security:spring-security-test")`.

Kiểm tra dependency thực tế trong Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.security
~~~

Với Windows: `mvnw.cmd dependency:tree -Dincludes=org.springframework.security`. Không ghép `spring-security-test` phiên bản 7.x với runtime Spring Security 6.x chỉ để dùng API test mới. Khi import không tồn tại, kiểm tra classpath/test scope và release thật.

## 4. Ứng dụng demo có filter chain thật

Để có test có thể kiểm tra được, ta khai báo **đúng một** Spring Boot application trong package `com.example.securitytest`. Các tệp dưới đây là code đầy đủ cho phần ứng dụng; có thể đặt vào project Spring Boot 3.5.x với dependency ở trên.

**`src/main/java/com/example/securitytest/SecurityTestApplication.java`**

~~~java
package com.example.securitytest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityTestApplication.class, args);
    }
}
~~~

`@EnableMethodSecurity` cho phép thêm rule cho service bằng `@PreAuthorize`. Đối với phép kiểm tra URL thông thường, `SecurityFilterChain` vẫn là lớp kiểm soát trước controller.

**`src/main/java/com/example/securitytest/SecurityConfiguration.java`**

~~~java
package com.example.securitytest;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("REPORT_READ")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("REPORT_WRITE")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        // CSRF vẫn được bật theo mặc định.
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password("{noop}reader123")
                .authorities("REPORT_READ")
                .build(),
            User.withUsername("editor")
                .password("{noop}editor123")
                .authorities(
                    "REPORT_READ", "REPORT_WRITE", "REPORT_EXPORT")
                .build(),
            User.withUsername("guest")
                .password("{noop}guest123")
                .authorities("OTHER")
                .build()
        );
    }
}
~~~

Ý nghĩa rule:
- `GET /api/ping` cho phép anonymous.
- `GET /api/reports/**` yêu cầu authority `REPORT_READ`.
- `POST /api/reports` yêu cầu `REPORT_WRITE` và vẫn phải vượt qua `CsrfFilter`.
- Rule cuối buộc mọi endpoint khác phải xác thực. Trong ví dụ, `DispatcherType.ERROR` được cho phép để lỗi gốc như 404 không bị biến thành lỗi phân quyền trong error dispatch.
- `{noop}` chỉ để demo: mật khẩu lưu plain text không an toàn cho production. Dự án thực cần PasswordEncoder phù hợp, user store thật hoặc phương thức xác thực tương ứng.

**`src/main/java/com/example/securitytest/ReportService.java`**

~~~java
package com.example.securitytest;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ReportService {

    public Report get(long id) {
        if (id != 42L) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Report not found");
        }
        return new Report(42L, "Monthly");
    }

    @PreAuthorize("hasAuthority('REPORT_EXPORT')")
    public String export() {
        return "EXPORT-OK";
    }

    public Report create(String title) {
        // Demo cố định: không ghi database.
        return new Report(43L, title);
    }

    public record Report(long id, String title) {}
}
~~~

**`src/main/java/com/example/securitytest/ReportController.java`**

~~~java
package com.example.securitytest;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ReportController {

    private final ReportService service;

    public ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/reports/{id}")
    public ReportService.Report get(@PathVariable long id) {
        return service.get(id);
    }

    @GetMapping("/reports/export")
    public String export() {
        return service.export();
    }

    @PostMapping("/reports")
    public ResponseEntity<ReportService.Report> create(
            @RequestBody CreateReport request) {
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(service.create(request.title()));
    }

    public record CreateReport(String title) {}
}
~~~

`GET /api/reports/export` vừa qua kiểm tra URL `REPORT_READ`, vừa qua `@PreAuthorize("hasAuthority('REPORT_EXPORT')")` ở service. Đây là tình huống tốt để xác minh **filter chain và method security cùng chạy**. `POST /api/reports` đòi thêm CSRF token vì ví dụ cố ý **không** tắt CSRF.

## 5. Kiểm thử tích hợp: @SpringBootTest + @AutoConfigureMockMvc

Đây là cấu hình chính cho mục tiêu **kiểm thử security filter chain thật**:

~~~java
@SpringBootTest
@AutoConfigureMockMvc // addFilters = true theo mặc định
class ReportSecurityIntegrationTests {
    @Autowired MockMvc mvc;
}
~~~

`@SpringBootTest` tạo ApplicationContext có `SecurityConfiguration`, `ReportController`, `ReportService`, `UserDetailsService` và `springSecurityFilterChain`. `@AutoConfigureMockMvc` cấu hình MockMvc qua chính context và đăng ký filters được tìm thấy trong context; không cần tự dựng controller bằng `new`. **Không** thêm `@AutoConfigureMockMvc(addFilters=false)` vào một test có mục tiêu xác minh bảo mật.

Tệp sau bao phủ các hành vi quan trọng.

**`src/test/java/com/example/securitytest/ReportSecurityIntegrationTests.java`**

~~~java
package com.example.securitytest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportSecurityIntegrationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousCannotReadProtectedReport() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("Basic")));
    }

    @Test
    void wrongPasswordIsRejectedByAuthentication() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedGuestLacksReadAuthority() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("guest", "guest123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void readerCanGetExistingReport() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.title").value("Monthly"));
    }

    @Test
    void authorizedReaderGets404ForMissingRecord() throws Exception {
        mvc.perform(get("/api/reports/99")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void unauthenticatedRequestDoesNotReach404Decision() throws Exception {
        mvc.perform(get("/api/reports/99"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void editorWithoutCsrfTokenGets403() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("editor", "editor123"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"New\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorWithInvalidCsrfTokenGets403() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("editor", "editor123"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"New\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void readerCannotWriteEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("reader", "reader123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"New\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorCanWriteWithValidCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("editor", "editor123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"New\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value(43))
            .andExpect(jsonPath("$.title").value("New"));
    }

    @Test
    void readerPassesUrlRuleButFailsMethodRule() throws Exception {
        mvc.perform(get("/api/reports/export")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorPassesBothUrlAndMethodRules() throws Exception {
        mvc.perform(get("/api/reports/export")
                .with(httpBasic("editor", "editor123")))
            .andExpect(status().isOk())
            .andExpect(content().string("EXPORT-OK"));
    }

    @Test
    @WithMockUser(authorities = "REPORT_READ")
    void mockUserCanTestAuthorizationWithoutRealPassword() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isOk());
    }
}
~~~

Chạy toàn bộ test trong Maven project:

~~~bash
./mvnw test
~~~

Trên Windows chạy `mvnw.cmd test`; nếu không có Maven wrapper, dùng `mvn test`. Với project và dependencies được cấu hình đúng như ví dụ, **14 test được kỳ vọng pass**. Đây là kết quả suy ra từ mã mẫu; không phải log thực thi đã được xác minh trên một project cụ thể. Các trạng thái kỳ vọng bao gồm `200` (public/reader/export), `201` (create), `401` (no/wrong Basic credentials), `403` (missing permission/CSRF/method authority) và `404` (ID không tồn tại sau khi đã qua security).

### Vì sao các test này cho bằng chứng mạnh?

1. **Sai mật khẩu trả 401:** `httpBasic("reader", "wrong")` chỉ tạo header `Authorization: Basic ...`. Nó không đánh dấu user là đã xác thực. Kết quả `401` chỉ xuất hiện đúng khi authentication filter/provider được gọi với user store thực.
2. **Khách có danh tính nhưng thiếu quyền trả 403:** xác minh `AuthorizationFilter` áp dụng rule `hasAuthority("REPORT_READ")`.
3. **POST thiếu/sai CSRF trả 403; có CSRF và quyền trả 201:** xác minh `CsrfFilter` thật được chạy, sau đó mới là authorization và controller.
4. **URL pass nhưng method deny:** xác minh service được Spring quản lý/proxy và `@EnableMethodSecurity` có hiệu lực.
5. **Reader đủ quyền nhưng ID thiếu trả 404:** chứng minh request đã vượt qua filter chain để tới logic tìm tài nguyên; thiếu credentials với cùng ID vẫn `401`.
6. **`@WithMockUser` pass chỉ xác minh policy với security context giả lập:** không được xem là bằng chứng password/token thực đã được kiểm tra; test Basic 401/200 mới đáp ứng phần đó.

Một phép kiểm tra `403` đơn lẻ **không chứng minh** đúng rule: CSRF cũng có thể tạo 403 trước phân quyền. Vì thế cần có cặp test `with(csrf())` và không có `csrf()` để tách nguyên nhân.

## 6. Khi tự tạo MockMvc: phải tích hợp Spring Security một cách tường minh

Không phải dự án nào cũng dùng `@AutoConfigureMockMvc`. Nếu sử dụng `WebApplicationContext` và builder thủ công, cấu hình đúng là:

~~~java
package com.example.securitytest;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

@SpringBootTest
class ManualMockMvcSecurityTests {

    @Autowired
    WebApplicationContext context;

    MockMvc mvc;

    @BeforeEach
    void setup() {
        mvc = webAppContextSetup(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void anonymousMustBeRejected() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

`SecurityMockMvcConfigurers.springSecurity()` gắn `FilterChainProxy` và thiết lập phần hỗ trợ test security context. Đây là điểm khác biệt cốt lõi so với:

~~~java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new ReportController(new ReportService()))
    .build();
~~~

Đoạn `standaloneSetup` trên là **phản ví dụ minh họa**, không dùng để khẳng định security rules chạy: nó chỉ dựng controller và service bằng `new`, không tải bean `SecurityFilterChain` hoặc proxy method security. Lời gọi `GET /api/reports/42` có thể trả 200 ngay cả khi không có thông tin xác thực. Nếu mục tiêu là test security thật, hãy dùng `webAppContextSetup(context).apply(springSecurity())` hoặc cấu hình Boot tích hợp ở phần 5.

Không nên kết hợp tùy tiện `@AutoConfigureMockMvc` với việc tự dựng một `MockMvc` thứ hai rồi nghĩ rằng hai đối tượng có chung cấu hình. Đối tượng đã inject bởi Spring Boot và đối tượng do builder tạo có thể mang danh sách filter khác nhau.

## 7. Chọn đúng công cụ mô phỏng danh tính

| Cách cấp danh tính | Điều được kiểm tra | Điều **không** được chứng minh |
| --- | --- | --- |
| `with(httpBasic("reader", "reader123"))` | Header Basic và **pipeline authentication thực** khi filter chain chạy | Không tự động chứng minh một Bearer/JWT pipeline khác |
| `@WithMockUser(authorities="REPORT_READ")` | Authorization dựa trên `SecurityContext` giả lập | User tồn tại trong DB, mật khẩu đúng, authentication provider chạy |
| `with(user("tester").authorities(...))` | Request mang principal/authorities đã chọn | Ký xác thực token hay xác minh password thực |
| `@WithUserDetails("reader")` | Nạp principal qua `UserDetailsService` rồi đặt `SecurityContext` | Không tự kiểm thử password verification trên mỗi HTTP request |
| `with(jwt())` / `with(oauth2Login())` | Các tình huống authorization với authentication mô phỏng tương ứng | JWT signature, issuer, audience, JWKS retrieval, OAuth redirect/handshake thật |
| Header `Authorization: Bearer <token>` thực | Có thể kiểm thử toàn bộ resource-server authentication chain nếu app được cấu hình thật | Không đồng nghĩa có network/TLS vì MockMvc vẫn dùng mock request |

`@WithMockUser` mặc định tạo user có `ROLE_USER`. Với `hasAuthority("REPORT_READ")` cần đặt `authorities="REPORT_READ"`; `roles="ADMIN"` thường tạo authority `ROLE_ADMIN`. Không trộn `ROLE_ADMIN` với `ADMIN` khi kiểm thử rồi quy lỗi cho filter.

Với test HTTP Basic, `httpBasic` tốt hơn `with(user(...))` nếu yêu cầu là **chứng minh credential checking**. Đối với Resource Server, dùng `jwt()` để viết test phân quyền nhanh, nhưng phải có thêm test token thật hoặc test `JwtDecoder`/validators để chứng minh chữ ký và claims được kiểm tra đúng.

## 8. Một bẫy phổ biến: @WebMvcTest không nhất thiết mang policy thật

`@WebMvcTest(ReportController.class)` chỉ dựng slice MVC: controller và một số thành phần web được chọn, không tải mọi `@Service`/`@Configuration` như `@SpringBootTest`. Khi dùng slice:
- Spring Security trên classpath có thể kích hoạt bảo mật mặc định, nhưng default security **không đại diện** cho `SecurityFilterChain` ứng dụng nếu config riêng không nằm trong slice.
- Nếu controller cần service, cung cấp `@MockitoBean` (Spring Boot 3.4+/Spring Framework 6.2+) hoặc cấu hình collaborator phù hợp.
- Nếu muốn test rule cụ thể, dùng `@Import(SecurityConfiguration.class)` và bảo đảm mọi dependency của cấu hình có mặt; sau đó xác minh không có filter chain test nào ghi đè.
- `@AutoConfigureMockMvc(addFilters=false)` có thể hữu ích cho controller-only test, nhưng **không** dùng nó cho bài kiểm thử security integration.

Ví dụ cấu trúc *minh họa* của slice test:

~~~java
@WebMvcTest(ReportController.class)
@Import(SecurityConfiguration.class)
class ReportControllerSliceTests {
    @Autowired MockMvc mvc;
    @MockitoBean ReportService service;

    // Các test HTTP tiếp theo phải kiểm tra filter thực sự được add.
}
~~~

Đoạn này được đặt riêng để giải thích **phạm vi của slice**; muốn biên dịch cần thêm imports đúng Boot 3.5 và định nghĩa test đầy đủ. Chỉ `@WebMvcTest` không chứng minh method security của `ReportService` thật, vì bean đó đang được mock. Đối với yêu cầu “tích hợp filter chain thật cùng service security thật”, ưu tiên `@SpringBootTest` ở phần 5.

## 9. Chẩn đoán test 200/403/404 bất ngờ

| Dấu hiệu | Nguyên nhân hay gặp | Cách xác minh/sửa |
| --- | --- | --- |
| Anonymous gọi endpoint bảo vệ nhưng test vẫn 200 | MockMvc được dựng bằng `standaloneSetup` hoặc `addFilters=false` | Chuyển sang context có `springSecurityFilterChain` và giữ registration bật; thêm test anonymous = 401 |
| Anonymous GET nhận 302 thay vì 401 | Ứng dụng bật form login redirect | Kiểm tra `AuthenticationEntryPoint`; thử đúng API chain `httpBasic`/Bearer hoặc assert redirect theo contract |
| POST với user có quyền vẫn 403 | Thiếu/sai CSRF | Thêm `with(csrf())` trong test dự kiến thành công; giữ test invalid/missing CSRF riêng |
| POST không cần CSRF mà vẫn 201 | CSRF bị tắt, đường dẫn excluded, hoặc filter không chạy | Kiểm tra `SecurityFilterChain` và CSRF matcher; test negative case bắt buộc |
| `with(user(...))` pass nhưng Basic password sai lại thất bại | User postprocessor bỏ qua password verification | Dùng `httpBasic` để test authentication thực; `user` chỉ để test authorization |
| `@PreAuthorize` không chặn | Thiếu `@EnableMethodSecurity`, gọi qua `this`/`new`, service bị mock | Gọi Spring bean qua proxy, test method denial với role phù hợp |
| Test thấy 403 thay cho 404 | Security chặn trước MVC, hoặc ERROR dispatch bị chặn tiếp | Tạo test authenticated đủ quyền; kiểm tra dispatcher và rule |
| Dùng `hasRole("ADMIN")` nhưng mock có authority `ADMIN` | Lệch tiền tố `ROLE_` | Dùng `roles("ADMIN")` hoặc authority `ROLE_ADMIN` cho rule hasRole |
| `@WebMvcTest` khác với production | Slice thiếu bean/filter config hoặc auto-config khác | Import cấu hình yêu cầu; có ít nhất một `@SpringBootTest` kiểm chứng tích hợp |
| Thử `jwt()` và kết luận signature hợp lệ | `jwt()` chỉ mô phỏng authentication | Thêm test token Bearer thực hoặc test decoder/validator |
| Controller return 200 nhưng service có rule deny | Method bị mock hoặc self-invocation bỏ qua proxy | Tránh mock service trong test full security và gọi qua Spring bean |
| Unit test không thấy status 401 vì trả 403 | CSRF có thể chặn trước authentication ở unsafe method | Trước tiên kiểm tra anonymous GET; POST luôn cần test CSRF riêng |

Khi debug, có thể tạm bật log:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Xem `SecurityFilterChain` nào match request, điểm authentication và authorization, nhưng không mặc định coi log là bằng chứng duy nhất: **assertion HTTP trên input âm/dương** mới là kiểm tra bền vững. Log `TRACE` có thể rất lớn, tránh bật lâu tại production.

## 10. Đo lường đúng phạm vi “tích hợp thật”

Để đánh giá kết quả kiểm thử, cần tách ba lớp:

1. **Security configuration**: Bean `SecurityFilterChain` của ứng dụng có được tạo hay không; request match chain nào; filter nào được kích hoạt. Có nhiều filter chain thì request path có thể chọn chain khác nhau (`securityMatcher` + thứ tự `@Order`).
2. **Authentication/authorization behavior**: Không credential, sai credential, đúng credential thiếu quyền, đúng quyền; quyền URL và quyền method; các matcher đặc biệt như dispatcher types.
3. **HTTP contract**: Body, header `WWW-Authenticate`, mã `401/403/404/201`, JSON serialization và CSRF. Một response đúng có thể bị tạo ra vì lý do sai; vì vậy phải có test đối chiếu điều kiện nguyên nhân.

Đối với ứng dụng có nhiều chain, viết test cho **mỗi nhóm URL quan trọng**. Ví dụ `/api/**` và `/admin/**` có thể dùng cơ chế đăng nhập khác nhau; một test pass ở `/api/reports/42` không chứng minh `/admin/**` an toàn. Nếu có security headers hoặc session fixation policies quan trọng, thêm assertion header/cookie cụ thể.

**Giới hạn của MockMvc:** không mô phỏng hoàn chỉnh browser origin/cookie policy, proxy headers, TLS và Servlet container network. Các luồng login liên quan redirect, SameSite, CORS thực và token issuance/JWKS nên có thêm một số integration test chạy server thật khi rủi ro yêu cầu.

## 11. Checklist trước khi chấp nhận bộ test

- [ ] Có `spring-boot-starter-test` và `spring-security-test` trong test classpath, version khớp runtime Spring Security.
- [ ] Test yêu cầu full integration dùng `@SpringBootTest + @AutoConfigureMockMvc` hoặc `webAppContextSetup(context).apply(springSecurity())`.
- [ ] Không dùng `standaloneSetup` hoặc `addFilters=false` làm bằng chứng security thật.
- [ ] Có negative case anonymous → **401/challenge phù hợp cấu hình**.
- [ ] Có negative case HTTP Basic password sai → **401**.
- [ ] Có authenticated nhưng thiếu authority → **403** và có authority → **2xx**.
- [ ] Với unsafe methods có CSRF: test thiếu/sai CSRF → **403**, token hợp lệ và đủ quyền → **2xx**.
- [ ] Có test đủ quyền nhưng business resource không tồn tại → **404**.
- [ ] Nếu có method security: test `@PreAuthorize` deny và allow qua bean thật.
- [ ] Phân biệt `@WithMockUser`/`with(user())` với xác thực credential thật.
- [ ] Với `@WebMvcTest`: xác nhận config thực đã được import, dependency khác được mock hợp lý, không suy diễn sang full context.
- [ ] Với OAuth2 Resource Server: test authorization mock và token validator/signature riêng.
- [ ] Có một số test live HTTP nếu yêu cầu liên quan server/network/proxy/TLS/cookie/browser.
- [ ] Test chạy lại nhất quán và không phụ thuộc dữ liệu chia sẻ/ordering.

## Tài liệu chính thức

1. [Spring Security 6.5 — Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/).
2. [Spring Security 6.5 — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html).
3. [Spring Security 6.5 — Running a Test as a User](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html).
4. [Spring Security 6.5 — HTTP Basic MockMvc Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html).
5. [Spring Security 6.5 — CSRF Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html).
6. [Spring Security 6.5 — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html).
7. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).
8. [Spring Framework 6.2 — MockMvc Setup Options](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/setup-options.html).

Một bộ test HTTP đáng tin về bảo mật phải chứng minh rằng **quyết định thực sự đi qua đúng filter chain**, user store/provider hoạt động, CSRF được kiểm tra và method security không bị bỏ qua. Những test âm (không danh tính, sai mật khẩu, thiếu quyền, thiếu CSRF) có giá trị quyết định để phát hiện việc vô tình bỏ qua filter.
