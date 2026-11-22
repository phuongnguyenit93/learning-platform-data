# Tích hợp MockMvc bằng springSecurity và chuỗi bộ lọc thực

> **Phạm vi:** Spring Security 6.x trên Servlet stack (Spring MVC, Spring Boot 3.x, Java 17+, Jakarta Servlet), sử dụng Spring Security Test và MockMvc. Trọng tâm là cách tích hợp `SecurityMockMvcConfigurers.springSecurity()` để request giả lập **đi qua các filter Spring Security thật được cấu hình trong ApplicationContext**: `FilterChainProxy`/`SecurityFilterChain`, xác thực, phân quyền, xử lý exception và CSRF. “Filter thật” ở đây không có nghĩa khởi chạy HTTP server hay chạy một trình duyệt/Servlet Container thật; request/response vẫn do MockMvc mô phỏng.

## 1. Vấn đề cần giải quyết

Giả sử ứng dụng có API chỉ cho user có quyền `REPORT_READ` đọc báo cáo, và chỉ user có `REPORT_WRITE` được tạo báo cáo. Một controller test đơn thuần có thể gọi handler trực tiếp và nhận HTTP 200 ngay cả khi chính sách thực tế phải từ chối.

Muốn kiểm thử **bảo mật HTTP** đáng tin, ta phải để các request thử nghiệm đi qua cùng cơ chế Spring Security mà ứng dụng dùng, thay vì chỉ assert nội dung trả về của controller.

Có ba câu hỏi khác nhau:

1. **Controller làm đúng không?** Với input hợp lệ, handler trả status/body mong muốn?
2. **Chuỗi filter bảo vệ HTTP đúng không?** Request chưa đăng nhập có bị từ chối? Principal có authority nào? `CsrfFilter` có chặn POST thiếu token? `ExceptionTranslationFilter` xử lý access denied/unauthenticated thế nào?
3. **Xác thực thực tế có đúng không?** Authentication provider, `UserDetailsService`, password encoder, JWT decoder, IdP, session/headers có được kiểm tra trên đường đi tương ứng không?

MockMvc + `springSecurity()` hỗ trợ mạnh cho câu (1) và (2); câu (3) **chỉ được kiểm chứng cho những authentication components thật mà request test thực sự kích hoạt**. Ví dụ `httpBasic()` có thể làm `BasicAuthenticationFilter` và `AuthenticationProvider` thật chạy trên mock HTTP request, trong khi `@WithMockUser`/`user()` **đặt sẵn authentication giả** và bỏ qua khâu xác minh mật khẩu.

**Kết luận ngay từ đầu:** dùng MockMvc **có Spring Security filter chain** để kiểm thử bảo mật HTTP. Không chỉ “test trả 403”, mà còn xác nhận **đúng nguyên nhân bị từ chối**, đúng filter chain đang chạy và những loại xác thực nào đã/không được kiểm tra.

## 2. Các thành phần có liên quan

| Thành phần | Vai trò |
| --- | --- |
| `MockMvc` | Mô phỏng request/response của Spring MVC mà không chạy server TCP thực. |
| `MockMvcBuilders.webAppContextSetup(context)` | Tạo MockMvc từ `WebApplicationContext` với controllers, filters, MVC config, services trong context. |
| `MockMvcBuilders.standaloneSetup(controller)` | Dựng MVC nhỏ gọn quanh một/vài controller; không tự mang toàn bộ cấu hình ứng dụng. |
| `SecurityMockMvcConfigurers.springSecurity()` | Gắn tích hợp Spring Security Test vào MockMvc builder; sử dụng Spring Security `FilterChainProxy`/filter chain từ context trong cách setup phù hợp. |
| `FilterChainProxy` | Bộ lọc đại diện cho Spring Security; chọn `SecurityFilterChain` khớp request và áp dụng các security filters bên trong. |
| `SecurityFilterChain` | Tập các security filters cho phạm vi request được cấu hình, thường bằng `HttpSecurity` và `@Bean`. |
| `DelegatingFilterProxy` | Cầu nối từ Servlet Container sang Spring-managed filter `springSecurityFilterChain` trong ứng dụng triển khai thực. |
| `SecurityContextHolder` | Nơi các thành phần Spring Security truy cập `Authentication` hiện tại theo chiến lược context. |
| `SecurityMockMvcRequestPostProcessors` | Các helper `user()`, `httpBasic()`, `csrf()`, `jwt()`,... cho request test. |
| `@WithMockUser` | Tạo `Authentication` giả trong Spring TestContext; thuận tiện kiểm thử authorization. |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Cách Boot dựng app context và MockMvc thường kèm đăng ký application filters, mặc định `addFilters=true`. |

Một ứng dụng Servlet bình thường có đường đi khái niệm:

~~~text
HTTP request thật
  -> Servlet Container
  -> DelegatingFilterProxy("springSecurityFilterChain")
  -> FilterChainProxy
  -> chọn SecurityFilterChain phù hợp request
  -> Security filters: context, CSRF, authentication, authorization...
  -> DispatcherServlet -> Controller
  -> HTTP response
~~~

Còn test MockMvc tích hợp đúng:

~~~text
MockHttpServletRequest
  -> MockMvc filter registration
  -> FilterChainProxy từ Spring ApplicationContext
  -> chọn SecurityFilterChain phù hợp
  -> Spring Security filters thật
  -> DispatcherServlet/Controller từ WebApplicationContext
  -> MockHttpServletResponse
  -> assertions status/headers/body/security state
~~~

Điểm khác là **container/network được mô phỏng**, không phải toàn bộ **Spring Security chain bị mock**. Đó là ý nghĩa chính xác của “chuỗi bộ lọc thực” trong MockMvc.

## 3. Tích hợp springSecurity(): hai cách phổ biến

### 3.1 Tự dựng MockMvc từ WebApplicationContext

Khi bạn trực tiếp dùng `MockMvcBuilders`, cách thông dụng là:

~~~java
import static org.springframework.security.test.web.servlet.setup
        .SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.setup
        .MockMvcBuilders.webAppContextSetup;

MockMvc mvc = webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
~~~

Đoạn trên là **code nằm trong test class có biến `WebApplicationContext webApplicationContext`**, không phải một ứng dụng Java SE độc lập. Khi context có bean `springSecurityFilterChain` từ Spring Security, `springSecurity()` kết nối các helper và filter cần thiết cho Spring Security Test; request sẽ trải qua logic Spring Security đang cấu hình.

Ví dụ test class đầy đủ ở phần 8.

**Phân biệt:** `springSecurity()` là một `MockMvcConfigurer` của Spring Security Test, **không phải** DSL `HttpSecurity`. Nó không tự tạo một chính sách `hasRole` mới. Chính sách vẫn đến từ bean `SecurityFilterChain` trong app context.

### 3.2 Spring Boot @AutoConfigureMockMvc

Trong Spring Boot Test, cách ngắn hơn:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class HttpSecurityTest {

    @Autowired
    MockMvc mvc;
}
~~~

`@AutoConfigureMockMvc` tạo `MockMvc` trên app context và **mặc định đăng ký application filters** (`addFilters = true`), gồm Spring Security filter nếu ứng dụng đã cấu hình nó. Trong cấu hình Boot thông dụng này, **không cần tự build MockMvc và gọi lại `.apply(springSecurity())`**. Đừng gắn trùng filter chain vô tình khi đã để Boot tự cấu hình.

**Kiểm tra điều kiện:** phải có dependency `spring-security-test`, security configuration phù hợp và các filter được đăng ký trong context. Một context bị test profile thay SecurityFilterChain bằng cấu hình khác sẽ kiểm tra **cấu hình test đó**, không mặc nhiên là cấu hình production.

### 3.3 Khi nào cách nào tốt hơn?

| Tình huống | Lựa chọn |
| --- | --- |
| App Spring Boot và muốn kiểm thử nhiều lớp HTTP với cấu hình thật | `@SpringBootTest` + `@AutoConfigureMockMvc`. |
| Tự kiểm soát MockMvc setup từ `WebApplicationContext` | `webAppContextSetup(context).apply(springSecurity()).build()`. |
| Chỉ tập trung controller, mock các dependencies khác | `@WebMvcTest`, nhưng phải xác nhận security config/filter chain nào được nạp. |
| Chỉ dựng `standaloneSetup(controller)` | Không đủ để kết luận full Spring Security integration, trừ khi bạn **chủ động** gắn filter/context cần thiết. |
| Muốn test TLS, reverse proxy, servlet container, network session behavior thực tế | Integration test chạy server/browser hoặc môi trường staging; MockMvc không thay thế. |

**Không dùng** `@AutoConfigureMockMvc(addFilters = false)` để kiểm thử behavior của `SecurityFilterChain`: tham số đó loại application filters khỏi MockMvc registration, có thể làm API nhạy cảm trả 200 mà security filter không chạy. Nó có thể hữu ích trong **controller-only tests** có mục đích rõ, nhưng phải đặt tên test và kỳ vọng đúng phạm vi.

## 4. Spring Security FilterChainProxy và việc chọn chain

Spring Security có thể có **nhiều** `SecurityFilterChain`. `FilterChainProxy` duyệt các chain theo thứ tự đã cấu hình và thường chọn **chain đầu tiên có `RequestMatcher` khớp**. Vì thế một request MockMvc phải được kiểm thử với đúng method, path và các điều kiện matcher tương ứng.

Ví dụ quy tắc khái niệm:

~~~text
@Order(1): /api/admin/**   -> admin security rules
@Order(2): /api/**         -> API security rules
@Order(3): /**             -> web security rules
~~~

Nếu đặt chain chung `/**` lên trước chain `/api/admin/**`, một request có thể match chain chung trước và **không được kiểm tra** bằng policy admin dự kiến. MockMvc đi qua `FilterChainProxy` thật sẽ giúp phát hiện sự khác biệt khi test request đúng đường đi.

Cần phân biệt hai cấp matcher:

- `http.securityMatcher(...)` / `SecurityFilterChain.matches(request)`: **chọn filter chain** được áp dụng.
- `authorizeHttpRequests(...requestMatchers(...))` bên trong chain: **quyết định quyền** của request đã vào chain đó.

Một URL không khớp bất kỳ chain nào có thể đi tiếp mà **không được Spring Security bảo vệ**. Hãy thiết kế chain phủ đúng vùng cần bảo vệ và có test cho những đường vào nhạy cảm, kể cả HTTP methods khác nhau.

### Các filter không chỉ làm authentication

Trên một chuỗi Spring Security bình thường, có thể có các filter xử lý `SecurityContext`, CSRF, logout, Basic/Form login, authentication exception, session management và authorization. Filter cụ thể/phạm vi/thứ tự tùy DSL/version. Không nên hard-code rằng ứng dụng nào cũng có mọi filter hay thứ tự hoàn toàn giống nhau.

Để chẩn đoán, có thể bật logging Spring Security ở mức phù hợp trong **test profile**:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Log có thể giúp thấy request được security filter xử lý và chain nào được áp dụng. Không bật TRACE/DEBUG chứa thông tin nhạy cảm ở production chỉ để xem test; tránh log credential, cookie, access token và PII.

## 5. Bộ ví dụ end-to-end: cấu hình SecurityFilterChain thật

Một ví dụ Java 17+/Spring Boot 3.x cho phép phân biệt chính xác authentication, authorization và CSRF. Các lớp đặt dưới package `com.example.mocksecurity`, và test trong package tương ứng. Đây là demo dùng user in-memory; ứng dụng thật dùng user store/IdP và quản lý mật khẩu phù hợp.

### 5.1 Maven dependencies

Bên trong `pom.xml` của một Spring Boot project (đã dùng Boot parent/BOM và Java 17+), thêm:

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

Đây là **mảnh cấu hình Maven**, không phải POM đầy đủ. Spring Security Test phải ở test classpath và phù hợp phiên bản của Spring Security ứng dụng; dùng dependency management của Spring Boot thay vì ép phiên bản tuỳ ý.

### 5.2 Điểm khởi chạy

File `src/main/java/com/example/mocksecurity/MockSecurityApplication.java`:

~~~java
package com.example.mocksecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MockSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(MockSecurityApplication.class, args);
    }
}
~~~

### 5.3 Cấu hình security theo HTTP method và quyền

File `src/main/java/com/example/mocksecurity/SecurityConfig.java`:

~~~java
package com.example.mocksecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/*")
                    .hasAuthority("REPORT_READ")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("REPORT_WRITE")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Điểm cần hiểu:

1. `GET /api/public` được phép không cần authentication.
2. `GET /api/reports/{id}` đòi authority `REPORT_READ`.
3. `POST /api/reports` đòi `REPORT_WRITE`.
4. `anyRequest().denyAll()` từ chối endpoint/method còn lại chưa khai báo; tránh vô tình mở đường truy cập.
5. `httpBasic` cho phép demo gửi username/password qua HTTP `Authorization: Basic ...` để đi qua **BasicAuthenticationFilter thật**.
6. Không gọi `csrf.disable()`. Spring Security mặc định bảo vệ CSRF với những request thay đổi trạng thái khi phù hợp; vì thế POST phải có CSRF token trong các tests tương ứng.
7. `hasAuthority("REPORT_WRITE")` kiểm tra tên authority chính xác, **không tự thêm `ROLE_`**. Với `hasRole("ADMIN")`, mặc định authority sẽ là `ROLE_ADMIN`.

Cấu hình này phù hợp để test hành vi HTTP Basic của ứng dụng mẫu, **không** mặc nhiên là cấu hình đúng cho mọi REST API dùng stateless Bearer tokens. Production API bearer-only cần thiết kế session/CSRF theo mô hình threat cụ thể, không tắt CSRF bằng phản xạ.

### 5.4 Users và PasswordEncoder cho demo

File `src/main/java/com/example/mocksecurity/DemoUsersConfig.java`:

~~~java
package com.example.mocksecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class DemoUsersConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader-test-password"))
                .authorities("REPORT_READ")
                .build(),
            User.withUsername("writer")
                .password(encoder.encode("writer-test-password"))
                .authorities("REPORT_READ", "REPORT_WRITE")
                .build()
        );
    }
}
~~~

Hai user chỉ dùng **trong ứng dụng demo/test**. Mã nguồn production không nên chứa mật khẩu người dùng thật. `reader` chỉ đọc; `writer` được đọc và tạo báo cáo. Vì ứng dụng có `PasswordEncoder` và `UserDetailsService` thật, test gửi HTTP Basic với mật khẩu chính xác có thể kích hoạt provider xác thực thật của ứng dụng mẫu; sai mật khẩu phải bị từ chối.

Bảo vệ username/password qua HTTP Basic trong môi trường triển khai **bắt buộc có HTTPS**. MockMvc không khởi chạy TLS: test không thể chứng minh transport protection production đã đúng.

### 5.5 Controller để quan sát rõ status và body

File `src/main/java/com/example/mocksecurity/ReportController.java`:

~~~java
package com.example.mocksecurity;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping(value = "/api/public",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping(value = "/api/reports/{id}",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String readReport(@PathVariable long id) {
        return "report " + id;
    }

    @PostMapping(value = "/api/reports",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> createReport() {
        return ResponseEntity.status(HttpStatus.CREATED).body("created");
    }
}
~~~

Controller cố ý rất đơn giản để kết quả HTTP phản ánh rõ hành vi của security filters. Với ứng dụng thật, ngoài `REPORT_READ` còn phải kiểm tra **owner/tenant/resource ID** trong service/data layer; chỉ quyền đọc tổng quát không chứng minh user có quyền với tất cả báo cáo.

## 6. Bài kiểm thử @SpringBootTest + @AutoConfigureMockMvc

Đây là phần quan trọng nhất: sử dụng **cấu hình SecurityFilterChain, users và controller thật trong Spring ApplicationContext**, không tắt filters.

File `src/test/java/com/example/mocksecurity/ReportHttpSecurityTest.java`:

~~~java
package com.example.mocksecurity;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ReportHttpSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void protectedEndpointChallengesAnonymous() throws Exception {
        mvc.perform(get("/api/reports/7"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/reports/7")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void realBasicAuthenticationCanRead() throws Exception {
        mvc.perform(get("/api/reports/7")
                .with(httpBasic("reader", "reader-test-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("report 7"));
    }

    @Test
    void readerCannotPostEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("reader", "reader-test-password"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void writerPostWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("writer", "writer-test-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void writerPostWithCsrfCanCreate() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("writer", "writer-test-password"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("created"));
    }

    @Test
    void invalidCsrfIsRejectedEvenForWriter() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("writer", "writer-test-password"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }
}
~~~

Những tests trên dùng **`httpBasic(...)` để thêm Authorization header**, không dựng trước một Authentication đã được xác thực. Nếu chain thực sự được đăng ký, `BasicAuthenticationFilter` nhận header, đi qua `AuthenticationManager`/provider, `UserDetailsService` và `PasswordEncoder` của app mẫu. Do đó test sai password có ý nghĩa lớn hơn test dùng `@WithMockUser`.

Kết quả kỳ vọng cho **chính cấu hình minh họa**:

| Request test | Rule/Filter đáng chú ý | Kỳ vọng |
| --- | --- | --- |
| Anonymous GET `/api/public` | `permitAll` | 200, body `public`. |
| Anonymous GET `/api/reports/7` | Chưa có auth và cần `REPORT_READ` | 401 (HTTP Basic entry point). |
| Reader gửi password sai qua Basic | BasicAuthenticationFilter/provider xác minh thất bại | 401. |
| Reader đúng password GET report | Basic authentication thành công, có `REPORT_READ` | 200, body `report 7`. |
| Reader POST với CSRF đúng | CSRF pass, thiếu `REPORT_WRITE` | 403 do thiếu quyền. |
| Writer POST thiếu CSRF | `CsrfFilter` từ chối trước khi vào controller | 403 do CSRF. |
| Writer POST với CSRF đúng | Xác thực và quyền đầy đủ | 201, body `created`. |
| Writer POST với CSRF sai | Invalid CSRF token | 403. |

**Cực kỳ quan trọng:** cả hai tests “reader thiếu quyền” và “writer thiếu CSRF” đều nhận 403, nhưng chứng minh **hai điều khác nhau**. Nếu muốn kiểm tra phân quyền, luôn gửi CSRF hợp lệ trong test POST để không pass sai lý do.

Để chạy trong dự án Maven có Spring Boot parent/BOM và đầy đủ các class nói trên:

~~~bash
mvn test
~~~

Không gắn stdout giả định cho Maven vì số test, phiên bản plugin và môi trường khác nhau. Với cấu hình demo nhất quán, các assertion trong class test này dự kiến pass. Nếu chúng không pass, phân tích lý do bằng filter chain, credentials, request matcher và CSRF; không tắt bảo vệ cho test “dễ xanh”.

### Vì sao test HTTP Basic này đáng giá hơn việc tự gọi controller?

Nếu bạn gọi trực tiếp `new ReportController().readReport(7)`, method trả `"report 7"` dù người gọi không có quyền. Điều đó không phải bug của controller demo, vì authorization được đặt ở Servlet filter chain. **Kiểm thử controller đơn lẻ không thể chứng minh Servlet filter chain bảo vệ request**.

Một test HTTP đi qua chain thật mới kiểm chứng rằng rule `GET /api/reports/*` được áp dụng trước khi vào handler, `BasicAuthenticationFilter` nhận header và các security components phản ứng đúng như thiết kế.

## 7. Kiểm thử thủ công bằng springSecurity() thay vì Boot tự cấu hình

Đây là một **test class riêng** minh họa cách dựng `MockMvc` thủ công từ `WebApplicationContext`. Không chạy cách này **đồng thời** với một MockMvc đã được auto-configured và thêm filter chain trùng.

File `src/test/java/com/example/mocksecurity/ManualSecurityMockMvcTest.java`:

~~~java
package com.example.mocksecurity;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.setup
        .SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup
        .MockMvcBuilders.webAppContextSetup;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

@SpringBootTest
class ManualSecurityMockMvcTest {

    @Autowired
    WebApplicationContext applicationContext;

    MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = webAppContextSetup(applicationContext)
                .apply(springSecurity())
                .build();
    }

    @Test
    void securityChainAuthenticatesBasicCredentials() throws Exception {
        mvc.perform(get("/api/reports/9")
                .with(httpBasic("reader", "reader-test-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("report 9"));
    }

    @Test
    void securityChainRejectsUnknownUser() throws Exception {
        mvc.perform(get("/api/reports/9")
                .with(httpBasic("unknown", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Giải thích:

1. `WebApplicationContext` có Spring MVC beans và Spring Security filter chain của ứng dụng.
2. `webAppContextSetup(...)` dùng context đó để dựng MockMvc.
3. `springSecurity()` gắn tích hợp test và Spring Security `FilterChainProxy` phù hợp từ context.
4. Tests gửi HTTP Basic header, vì vậy code xác thực có thể được thực thi trên request mock.
5. Đây là cùng một demo app với `SecurityConfig` và `DemoUsersConfig` đã viết ở trên, không phải một dự án thứ hai có users khác.

**Lưu ý:** Nếu `springSecurity()` không thể tìm filter chain trong ApplicationContext, đó là dấu hiệu cần kiểm tra dependencies/security configuration, không nên thay bằng controller-only setup rồi tuyên bố test bảo mật đã chạy.

### standaloneSetup có đủ không?

`standaloneSetup(controller)` rất hữu ích cho unit-style MVC tests, nhưng không tự dựng toàn bộ `FilterChainProxy`, security exception handling, service proxies và cấu hình Spring context. Muốn dùng nó để test security, phải chủ động cung cấp những filter/beans thích hợp và hiểu phần nào vẫn bị thiếu. Để kiểm thử “chuỗi bộ lọc thực” theo đề bài, cách an toàn và dễ bảo trì hơn là **`webAppContextSetup(...).apply(springSecurity())` hoặc `@AutoConfigureMockMvc` với filters được bật**.

## 8. Phân biệt HTTP authentication thật với user() và @WithMockUser

Spring Security Test cung cấp nhiều cách tạo danh tính trong request test. Chúng không có cùng độ sâu kiểm thử.

### 8.1 .with(httpBasic("reader", "password"))

`httpBasic(...)` đặt header `Authorization: Basic ...` vào **MockHttpServletRequest**. Khi `BasicAuthenticationFilter` và authentication providers có mặt trong chain, request **được xác thực qua logic thực của app** như `UserDetailsService` và `PasswordEncoder`.

Nó không tạo TCP connection, không chứng minh TLS, không gọi LDAP thật nếu app đang được cấu hình bằng users in-memory. Nhưng với ứng dụng mẫu, nó kiểm tra đúng provider và password validation đang được cấu hình.

### 8.2 .with(user("reader")): giả lập principal đã xác thực

Ví dụ:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;

mvc.perform(get("/api/reports/7")
        .with(user("not-in-database")
            .authorities(new SimpleGrantedAuthority("REPORT_READ"))))
   .andExpect(status().isOk());
~~~

Đây là **đoạn method test**, giả định có biến `mvc`, mock request chain và import `org.springframework.security.core.authority.SimpleGrantedAuthority` cùng static imports của MockMvc. `user(...)` đặt identity giả cho **một request**, không bắt `UserDetailsService` phải tìm user và không kiểm tra password.

Đặc biệt, username `not-in-database` không tồn tại vẫn có thể truy cập, vì test **cố tình mô phỏng** một người đã xác thực. Kết quả 200 chỉ chứng minh rule `REPORT_READ` chấp nhận Authentication có authority đó.

### 8.3 @WithMockUser: giả lập SecurityContext ở mức test

Ví dụ test method với cùng MockMvc `@SpringBootTest`:

~~~java
@Test
@WithMockUser(username = "synthetic-user",
              authorities = "REPORT_READ")
void authorizationWorksForAnAlreadyAuthenticatedPrincipal()
        throws Exception {
    mvc.perform(get("/api/reports/7"))
        .andExpect(status().isOk());
}
~~~

`@WithMockUser` đi qua Spring TestContext listener để chuẩn bị SecurityContext test. Nó không gọi HTTP Basic provider, không load user `synthetic-user` từ DB và không xác minh password. Với `@SpringBootTest`/`@AutoConfigureMockMvc` tích hợp Spring Security, request được kiểm tra **authorization** theo authorities test.

Cả `user()` và `@WithMockUser` đều hữu ích, **nhưng không được dùng làm bằng chứng rằng login hoặc credential validation đã được test**.

### 8.4 Bảng phạm vi xác minh

| Kỹ thuật test | Tác động | Kiểm chứng được | Không tự kiểm chứng |
| --- | --- | --- | --- |
| `with(user(...))` | Chèn Authentication/username/authorities giả cho một MockMvc request. | URL authorization, handler behavior với identity giả. | Password check, user store, login flow. |
| `@WithMockUser` | Đặt Authentication giả theo Spring TestContext cho test. | Authorization theo user/authority test. | Credential/token validation, DB role mapping. |
| `with(httpBasic(...))` | Thêm Authorization Basic header. | BasicAuthenticationFilter và provider **nếu** chúng nằm trong chain đã cài. | TLS, container, SSO/JWT pipeline khác. |
| `with(csrf())` | Thêm CSRF token test hợp lệ cho request. | CSRF protection tương tác với request đã giả lập. | Giao thức lấy/đổi token từ browser thật. |
| `with(jwt())` trong Resource Server tests | Gắn JWT/authentication test tùy helper. | Rule authorization theo claims/authorities đã dựng. | JWT signature/issuer/audience validation thực, nếu decoder bị bypass. |
| MockMvc với request và filter chain thật | Chạy Spring Security filters từ context trên mock request. | URL matcher, authn/authz/exception/CSRF behavior được kích hoạt. | HTTP server, TLS, reverse proxy, browser cookie policy thực tế. |

**Không dùng một từ “integration test” chung chung.** Hãy ghi rõ phép kiểm tra đã đi qua thành phần nào và thành phần nào được mô phỏng.

## 9. CSRF: tránh test 403 thành công sai lý do

Khi ứng dụng có session/cookie-based authentication hoặc một thiết kế có rủi ro CSRF, Spring Security thường dùng `CsrfFilter` để bảo vệ request thay đổi trạng thái. MockMvc test phải chủ động xác định muốn test **CSRF** hay **authorization**.

Những so sánh quan trọng:

~~~java
// Kiểm tra quyền: dùng token CSRF đúng để request đi qua CsrfFilter.
mvc.perform(post("/api/reports")
        .with(httpBasic("reader", "reader-test-password"))
        .with(csrf()))
   .andExpect(status().isForbidden());

// Kiểm tra thiếu CSRF: writer có quyền vẫn phải bị chặn.
mvc.perform(post("/api/reports")
        .with(httpBasic("writer", "writer-test-password")))
   .andExpect(status().isForbidden());

// Kiểm tra happy path: cả quyền và CSRF đều hợp lệ.
mvc.perform(post("/api/reports")
        .with(httpBasic("writer", "writer-test-password"))
        .with(csrf()))
   .andExpect(status().isCreated());
~~~

Đây là các **đoạn test riêng**, sử dụng cùng app demo và biến `mvc`. Nếu bỏ `.with(csrf())` trong test đầu, bạn có thể nhận 403 vì thiếu CSRF **ngay cả khi đã xóa rule `hasAuthority("REPORT_WRITE")`**. Khi đó test “reader bị từ chối vì thiếu quyền” **không còn chứng minh** điều mà tên test khẳng định.

Spring Security Test có `csrf().useInvalidToken()` để kiểm tra token sai. `csrf()` là test post-processor dùng để chuẩn bị giá trị cần thiết; nó **không đồng nghĩa** với việc browser production đã nhận cookie/hidden form field đúng đường đi.

Ngoài CSRF còn có CORS, SameSite, cookies và session. MockMvc có thể kiểm tra header/filter behavior ở Spring layer, nhưng không tái tạo đầy đủ việc browser tự chặn cross-site requests/cookies. Bảo vệ CSRF không thay thế authorization; CORS cũng **không phải** kiểm tra quyền truy cập tài nguyên.

## 10. Cần test cả anonymous, access denied và authentication entry point

HTTP status phụ thuộc cấu hình xác thực, không phải một con số cố định cho mọi ứng dụng.

| Trạng thái request | Với cấu hình demo HTTP Basic | Với form login thường gặp |
| --- | --- | --- |
| Chưa xác thực, truy cập tài nguyên protected | 401 và thường có `WWW-Authenticate`. | Thường redirect 302 tới login page. |
| Đã xác thực nhưng thiếu authority | 403. | 403. |
| POST thiếu/sai CSRF token | Thường 403 do CSRF. | Thường 403 do CSRF. |
| Đúng quyền, hợp lệ | 2xx tùy handler. | 2xx hoặc redirect tùy controller. |

Trong demo ở phần 5, `httpBasic(Customizer.withDefaults())` khiến unauthorized protected GET thường trả 401. Nếu app thật dùng `formLogin` thay vì Basic, test assert 401 máy móc có thể thất bại vì **302** là hành vi đúng.

Để test 401/403 có ý nghĩa:

1. Xác định `AuthenticationEntryPoint` và `AccessDeniedHandler` mà app đang dùng.
2. Dùng request đúng method/path; với POST hãy đưa token CSRF phù hợp khi mục tiêu là kiểm tra quyền.
3. Test happy path với user có đủ quyền để chứng minh endpoint không bị chặn do lỗi matcher/chưa tạo controller.
4. Kiểm tra response status, location/header khi liên quan và body không lộ dữ liệu.
5. Test người không có credential, credential sai và người đúng credential nhưng thiếu quyền **riêng biệt**.

Nếu test chỉ assert `status().isForbidden()`, bạn chưa chắc phân biệt được “không được phép” với “CSRF thiếu” hay một filter khác từ chối.

## 11. Lưu ý về @WebMvcTest, @MockBean và cấu hình bị cắt lớp

`@WebMvcTest` là **MVC slice test**, có thể load controllers/MVC security-related configuration ở phạm vi test mà không load toàn bộ service/repository/IdP beans của app. Điều đó phù hợp cho nhiều bài test controller, nhưng cần kiểm tra **cấu hình SecurityFilterChain nào thực sự tồn tại trong slice**.

Ví dụ rủi ro:

- Production dùng một chain tùy chỉnh có `hasAuthority("REPORT_WRITE")`.
- Test slice không import/cấu hình chain đó, hoặc thay bằng chain mặc định khác.
- `MockMvc` có filter, nhưng không phải rule production mà bạn nghĩ đang test.
- Test xanh vì mock authentication và matcher trong slice khác production.

Để tránh tự tin sai:

- Nếu mục tiêu là full HTTP filter chain trong ứng dụng, ưu tiên `@SpringBootTest + @AutoConfigureMockMvc` hoặc context phù hợp.
- Nếu dùng `@WebMvcTest`, import đúng security config, mock dependencies có chủ đích, và khẳng định test đang kiểm chứng **slice**; xem lại context/filters.
- Đừng thay `SecurityFilterChain` bằng `permitAll` trong test chỉ để controller khởi tạo. Nếu cần controller-only test, đặt tên/giới hạn phạm vi rõ ràng.
- Một số kỹ thuật mock bean hoặc profile có thể làm khác behavior production. Tài liệu test phải nói rõ dependency nào bị mock.

### Vì sao addFilters=false rất nguy hiểm cho test security?

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

Nếu muốn kiểm tra security filter chain, annotation này làm sai mục tiêu vì nó không đăng ký các application filters cho MockMvc theo cách mặc định. Một request thiếu authorization có thể đến thẳng controller. Chỉ dùng khi bạn **chủ động kiểm thử MVC/controller không có filters** và không kết luận nó chứng minh HTTP security.

### standaloneSetup: giới hạn cụ thể

`MockMvcBuilders.standaloneSetup(controller)` không dựng toàn bộ Spring WebApplicationContext; `@PreAuthorize` trên một bean có thể không được proxy như production nếu chỉ truyền object controller tự tạo. Các filter/exception handlers/configurers cũng không xuất hiện trừ khi bạn cung cấp. Vì vậy “controller trả 200” trong standalone test không chứng minh đường HTTP của app thật đã an toàn.

## 12. Test HTTP có kiểm chứng method security không?

**Có thể**, nếu method security được bật, service/controller được quản lý đúng bởi Spring và lời gọi đi qua interceptor/proxy. MockMvc gửi HTTP request qua filters rồi MVC handler gọi service; nếu service có `@PreAuthorize`, method security có thể chạy sau HTTP layer.

Ví dụ chính sách bổ sung tại service:

~~~java
@PreAuthorize("hasAuthority('REPORT_READ') and " +
              "@reportAccess.canRead(authentication, #p0)")
public Report read(long reportId) {
    return repository.findById(reportId).orElseThrow();
}
~~~

Đây là **mẫu kiến trúc**, không phải code Java độc lập vì `Report`, `reportAccess` và `repository` là domain components giả định. Để method security hoạt động, cần `@EnableMethodSecurity` và lời gọi qua Spring-managed bean/interceptor. Với production resource policies, `reportAccess` phải kiểm tra owner/tenant từ server-side data store, không tin `ownerId` client gửi.

**Quan trọng:** nếu đã dùng `@WithMockUser`, method policy nhận một principal giả. Điều đó giúp kiểm chứng rule, nhưng không kiểm tra mapping principal/roles từ login thật. Nếu ứng dụng dùng JWT/OIDC/SAML custom principal, cần test type/claims hoặc integration path thích hợp.

Trong HTTP integration tests, nên kiểm tra **ít nhất hai tầng** khi nghiệp vụ nhạy cảm:

- URL authorization: route/method chỉ người có quyền vào được.
- Domain authorization: role giống nhau nhưng user khác owner/tenant vẫn bị chặn.

Không chỉ bảo vệ nút trên UI hoặc chỉ check `authenticated()`; điều đó không ngăn IDOR/BOLA.

## 13. Khi dùng JWT Resource Server/OIDC/SAML: thay request processor phù hợp

HTTP Basic trong ví dụ là một phép kiểm tra tiện vì dễ nhìn thấy chu trình password verification. Nếu production dùng **Bearer JWT**, `with(httpBasic(...))` không kiểm chứng đúng mô hình. Chọn cách thử phù hợp:

### Với JWT Resource Server

- `with(jwt())` dựng JWT/authentication giả phục vụ test authorization theo `scope`, claims hoặc authorities.
- Vì helper thường bỏ qua JWT decoder/signature validation, cần test riêng **issuer, audience, expiry, signature/key rotation** qua decoder/filter thực hoặc integration environment.
- Để đi qua `BearerTokenAuthenticationFilter` và decoder thật, dùng request có `Authorization: Bearer <test-token>` và cấu hình test decoder/keys phù hợp (đừng gọi production IdP).
- Đảm bảo JWT authorities converter được test, ví dụ scope trở thành `SCOPE_reports.read`. Không tự gắn authority vào mock rồi kết luận production converter luôn ánh xạ đúng.

### Với OAuth2 Login/OIDC và SAML2 Login

Các helper test principal thường **không** diễn lại browser redirects, authorization code exchange hoặc SAML Response signature verification. Chúng chỉ cung cấp trạng thái xác thực cần thiết cho controller/authorization tests.

Muốn kiểm chứng protocol flow thật, cần test IdP/AS sandbox, fixture có signature hợp lệ hoặc môi trường tích hợp được kiểm soát. Đồng thời test URL matcher, callback endpoint, session state, CSRF/SameSite khi liên quan và quyền người dùng sau mapping.

### Với session và form login

Có thể test `formLogin()` helper hoặc gửi POST login request theo endpoint thực, rồi kiểm tra status, session và cookie khi thích hợp. Tuy nhiên MockMvc vẫn không tái hiện hoàn toàn browser session cookie policy, domain/SameSite behavior hay TLS. Nếu dùng real browser/server để kiểm tra UX và external IdP, hãy giữ đó là **bộ test riêng**, không trộn kết luận với test MockMvc.

## 14. Nhiều SecurityFilterChain: cách kiểm tra chọn đúng chain

Với app có API và trang web, có thể phân vùng:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());
    return http.build();
}
~~~

Đây là **mảnh Java trong một class @Configuration**, cần imports `@Bean`, `@Order`, `SecurityFilterChain`, `HttpSecurity` và `Customizer`; không phải một file độc lập. Nó minh họa cách chọn chain theo `securityMatcher`, **không phải cấu hình để dán thêm vào app demo phần 5**. Hai ví dụ thuộc **hai phương án thay thế**: nếu dán cả hai bộ `@Bean SecurityFilterChain` vào cùng project mà không xét thứ tự/phạm vi, kết quả thay đổi.

Để test chain selection đúng:

1. Gửi `GET /api/...` và `GET /web/...` với anonymous để nhìn khác biệt 401/302, nếu entry point của từng chain được cấu hình khác nhau.
2. Gửi các method/path có thể trùng matcher (ví dụ `/api/admin/**` trước/ sau `/api/**`).
3. Kiểm tra URL ngoài mọi matcher có được bảo vệ bằng một fallback chain hay không.
4. Đừng lấy HTTP 200 từ controller khi filter chain bị disable làm bằng chứng rằng policy đúng.
5. Xem logs/test config để xác nhận thứ tự chain và filter registrations; assert cụ thể trên response.

**Chú ý:** đoạn thứ hai không có `securityMatcher` hẹp nên là fallback chain; nên có thứ tự sau các chain cụ thể, thay vì đặt toàn cục trước làm che chain API.

## 15. Kiểm tra SecurityContext, principal và response

Spring Security Test có matchers để kiểm tra authentication status sau request khi phù hợp, chẳng hạn `authenticated()` hoặc `unauthenticated()`. Nhưng phải hiểu scope request: với HTTP Basic, việc xử lý authentication có thể diễn ra mỗi request; không suy ra một browser login session lâu dài chỉ từ matcher này.

Ví dụ đoạn test:

~~~java
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;

mvc.perform(get("/api/reports/7")
        .with(httpBasic("reader", "reader-test-password")))
   .andExpect(status().isOk())
   .andExpect(authenticated().withUsername("reader"));
~~~

Đây là **đoạn trong test class có `mvc` và các imports cần thiết**, dựa trên cấu hình demo. Nó xác nhận request được Spring Security nhìn nhận là authenticated với username tương ứng; nhưng vẫn phải kiểm tra access control qua status và dữ liệu trả về.

Khi làm việc với request async, session hoặc security context persistence, có thể có chi tiết cần kiểm thử riêng: một request đơn lẻ không chứng minh authentication đã được lưu/được propagate đúng sang request khác hay thread khác.

### Không leak dữ liệu khi test

Đừng dùng `andDo(print())` trên response chứa token, password, personal data hay session IDs mà không lọc. Logging toàn bộ Authorization header hoặc cookie có thể khiến secrets lộ vào CI logs. Với payload nhạy cảm, chỉ log metadata không nhạy hoặc mask fields.

## 16. Kịch bản kiểm thử tối thiểu nên có cho một API nhạy cảm

Một bộ test bảo mật HTTP có ý nghĩa nên bao gồm các lớp trường hợp:

| Nhóm | Ví dụ | Kết quả cần khẳng định |
| --- | --- | --- |
| Public | Anonymous GET `/api/public` | Endpoint public trả đúng body/status. |
| Authentication | Anonymous GET protected | Bị chặn qua entry point phù hợp. |
| Credential | Gửi Basic password sai | Provider từ chối, không tới protected handler. |
| Authorization âm | Reader POST nhưng CSRF hợp lệ | Bị chặn vì thiếu `REPORT_WRITE`. |
| Authorization dương | Writer POST có CSRF hợp lệ | Được thực thi, status/body đúng. |
| CSRF âm | Writer POST thiếu hoặc sai CSRF | Bị `CsrfFilter` từ chối. |
| Method/path coverage | GET, POST, PATCH, DELETE, đường mới | Không có route nhạy cảm bị bỏ sót matcher. |
| Resource-level | User đúng role nhưng sai tenant/owner | Bị từ chối hoặc không trả dữ liệu ngoài quyền. |
| SecurityContext | Principal và authorities được map đúng | Không dựa vào mock permission để suy ra login thật. |
| Error handling | 401/302/403/404 theo policy | Không leak thông tin và không pass test sai lý do. |

### Test âm tính là bắt buộc

Test chỉ chứng minh writer được tạo báo cáo không phát hiện lỗi `anyRequest().permitAll()`. Cần test reader thiếu quyền và anonymous để xác nhận **đường từ chối**. Tương tự, test nhận 403 vì CSRF thiếu không bảo đảm endpoint đã có authorization. Một bộ test tốt cố tình cấu hình các điều kiện sao cho chỉ còn **một nguyên nhân** quyết định kết quả trong từng phép thử.

### Bảo vệ cả dữ liệu, không chỉ endpoint

`hasAuthority("REPORT_READ")` trên `GET /api/reports/*` không tự bảo đảm mỗi user chỉ thấy báo cáo được phép. Đối với đối tượng được định danh bằng ID, phải có policy theo owner/tenant/data-access. Test một người đọc báo cáo của người khác qua URL trực tiếp là thiết yếu, dù UI không hiển thị link đó.

## 17. Khi test không chạy như mong đợi: bảng chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Hành động kiểm tra |
| --- | --- | --- |
| Anonymous GET protected trả 200 | Filter chain không được gắn vào MockMvc, security matcher không khớp, rule `permitAll` quá rộng. | Xem `@AutoConfigureMockMvc(addFilters=false)`, `springSecurity()`, chain order và matcher. |
| Anonymous GET nhận 302 thay vì 401 | App dùng form login hoặc entry point là redirect. | Kiểm tra config của chain thực; điều chỉnh expectation, không ép status theo Basic. |
| `with(httpBasic(...))` vẫn 401 dù đúng credentials | UserDetailsService/PasswordEncoder/provider sai hoặc Basic filter không áp dụng. | Kiểm tra chain, username, hash và test config. |
| `with(user(...))` pass nhưng Basic password sai | `user()` bỏ qua credential validation theo thiết kế. | Dùng Basic/form-login request thật để test authentication provider. |
| Reader POST trả 403 nhưng xóa role rule vẫn 403 | Test không có CSRF hợp lệ nên bị CsrfFilter chặn trước. | Thêm `.with(csrf())` trong test phân quyền. |
| Writer POST vẫn 403 dù có role đúng | Thiếu/invalid CSRF, thiếu permission chính xác hoặc handler/matcher sai. | Phân biệt `ROLE_*` và authority, kiểm tra CSRF và security debug. |
| Test sử dụng `@WebMvcTest` có behavior khác production | Slice context không nạp cùng security config/providers. | Kiểm tra bean security được load; dùng `@SpringBootTest` khi cần full context. |
| Test direct controller call pass dù API ngoài đời cấm | Không đi qua filter chain. | Dùng MockMvc HTTP request với filters bật. |
| Thêm manual `springSecurity()` vào MockMvc Boot auto rồi thấy filter trùng | Đăng ký hai lần chain/configurers. | Chọn một cơ chế MockMvc setup, không gắn duplicate. |
| Một route admin chạy qua chain web chung | Chain `/**` match trước chain admin. | Đặt `@Order` phù hợp và test từng route. |
| @PreAuthorize không thực thi dù filter chạy | Chưa bật method security hoặc gọi object/self-invocation không qua proxy. | Xác nhận `@EnableMethodSecurity`, Spring-managed bean và entry path. |
| Test JWT mock pass còn production trả 401 | Mock JWT bỏ qua decoder/issuer/audience validation. | Test decoder/converter và real Bearer path riêng. |
| MockMvc pass, production vẫn có lỗi cookie/TLS | MockMvc không chạy browser/proxy/network thực. | Thêm HTTP server/browser/staging tests với HTTPS và browser policy. |
| Request GET đúng endpoint nhưng body bị lộ dữ liệu tenant khác | URL-level authority đủ nhưng thiếu object-level authorization. | Test và sửa policy ở service/repository/data layer. |

## 18. Checklist trước khi kết luận filter-chain integration test đáng tin

1. `spring-security-test` có mặt trên test classpath và tương thích Spring Security của app.
2. Bạn biết đang dùng **một trong hai cách**: Boot `@AutoConfigureMockMvc` (filters bật mặc định) hoặc `webAppContextSetup(...).apply(springSecurity())`.
3. MockMvc request **thực sự đi qua `FilterChainProxy` từ ApplicationContext**; không dùng `addFilters=false` hoặc controller-only setup rồi gắn nhãn full security test.
4. Các `SecurityFilterChain` được dùng là cấu hình mong muốn, không bị test profile/slice thay ngoài ý định.
5. Có test anonymous, credential sai, có/thiếu quyền và happy path; status cùng nội dung response đều được assert khi có ý nghĩa.
6. Với POST/PUT/PATCH/DELETE, CSRF token được chuẩn bị đúng **cho mục tiêu của từng test**; không dùng 403 thiếu CSRF để chứng minh authorization.
7. Phân biệt `with(user())` / `@WithMockUser` (giả Authentication) với `httpBasic()` hoặc đường xác thực thực của protocol.
8. Nếu app dùng JWT/OIDC/SAML, có test riêng cho decoder/issuer/audience/signature và authority/principal mapping thật.
9. Kiểm tra nhiều chains, path/method matchers, thứ tự `@Order`, fallback chain, endpoints/callbacks công khai và đường bypass.
10. Test ownership/tenant/resource-level policy; URL authentication không thay kiểm tra dữ liệu.
11. Đã bật method security khi test method annotations và gọi qua Spring-managed beans.
12. Không kết luận MockMvc đã kiểm tra TLS, reverse proxy, browser SameSite policy hoặc multi-node session behavior; bổ sung tests triển khai thật.
13. Không log credentials/tokens, session cookies, SAML assertions hay dữ liệu nhạy cảm vào CI output.
14. Kết quả test ghi rõ được kiểm tra ở **Servlet security filter chain**, **authentication provider**, **authorization**, **CSRF** hay **business policy**, thay vì chỉ ghi “security passed”.

## 19. Tổng kết

`springSecurity()` của Spring Security Test giúp tích hợp **Spring Security filter chain từ ApplicationContext** vào MockMvc được dựng thủ công. Trong Spring Boot, `@SpringBootTest + @AutoConfigureMockMvc` với filters bật là một cách tương đương về mục tiêu: gửi mock HTTP requests qua các security filters và Spring MVC handlers thật đang cấu hình.

Điều cần nhớ là **“chuỗi bộ lọc thực” không đồng nghĩa “HTTP server thực”**. MockMvc kiểm tra logic framework trên request/response mô phỏng; dùng `with(httpBasic(...))` có thể kiểm chứng Basic authentication provider thật của ứng dụng mẫu, còn `with(user(...))` và `@WithMockUser` chủ đích bỏ qua xác minh credential. `csrf()` cho phép tách CSRF khỏi kiểm tra permission, tránh test 403 pass sai lý do.

**Quy tắc thực hành:** *Hãy bảo đảm request test thật sự đi qua SecurityFilterChain cần kiểm tra, sau đó tách riêng authentication, authorization, CSRF, quyền theo đối tượng và các ranh giới mà MockMvc không thể mô phỏng.*

## Tài liệu tham khảo chính thức

- Spring Security Reference — MockMvc Support: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security Reference — Security MockMvc Setup: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html
- Spring Security Reference — MockMvc RequestPostProcessors: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html
- Spring Security Reference — Spring Security Architecture / FilterChainProxy: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Boot Reference — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/reference/testing/index.html
