# @WithAnonymousUser và các trường hợp chưa đăng nhập: kiểm thử method security trong Spring Security Servlet

## 1. Tại sao phải kiểm thử một người dùng chưa đăng nhập?

Trong ứng dụng Spring Security Servlet, kiểm thử bảo mật không thể chỉ có tình huống người dùng đã đăng nhập thành công. Một API thường phải xử lý cả người truy cập công khai và người chưa cung cấp credentials:

- Trang tin tức, trang trạng thái có thể mở cho khách truy cập.
- Trang hồ sơ, lịch sử giao dịch, thao tác cập nhật tài khoản phải từ chối khách chưa xác thực.
- Endpoint yêu cầu vai trò hoặc quyền riêng có thể từ chối **cả người đã đăng nhập nhưng thiếu quyền**.
- Một số logic riêng cho người dùng ẩn danh, chẳng hạn hiển thị lời mời đăng nhập, có thể dùng biểu thức `isAnonymous()`.
- Login, logout, session expiry, remember-me, CSRF và Bearer token lỗi đều có hành vi khác nhau cần kiểm thử độc lập.

Spring Security Test cung cấp annotation **`@WithAnonymousUser`** để mô phỏng tình trạng **anonymous authentication** trong bài kiểm thử có Spring TestContext. Annotation này đặc biệt hữu ích cho **method security**: gọi một Spring bean được bảo vệ bằng `@PreAuthorize` hoặc `@PostAuthorize` và xác nhận quyền đã được áp dụng với một principal ẩn danh.

**Mấu chốt:** “anonymous” trong Spring Security thường là **một `AnonymousAuthenticationToken` được framework tạo ra**, không nhất thiết là `SecurityContextHolder.getContext().getAuthentication() == null`. Hai trạng thái cần được phân biệt khi viết assertion.

Mục tiêu của bài:

1. Hiểu chính xác `@WithAnonymousUser` tạo ra điều kiện kiểm thử nào.
2. Kiểm tra các biểu thức `isAnonymous()`, `isAuthenticated()`, `isFullyAuthenticated()` và điều kiện quyền trong method security.
3. So sánh kiểm thử trực tiếp một service bean với kiểm thử HTTP bằng `MockMvc`.
4. Phân biệt HTTP `401`/`403`, session không còn hợp lệ, remember-me và authentication thất bại.
5. Tránh các bài test “pass” nhưng không thật sự kích hoạt Spring Security.

## 2. Anonymous authentication là gì?

Một request không mang thông tin đăng nhập vẫn có thể được Spring Security biểu diễn thành `AnonymousAuthenticationToken` trong filter chain. Cơ chế này thường do **`AnonymousAuthenticationFilter`** thiết lập khi chưa có `Authentication` phù hợp trong `SecurityContextHolder`.

Với cấu hình chuẩn, token anonymous có principal đại diện khách, thường có authority `ROLE_ANONYMOUS`. Các chi tiết principal hoặc authorities có thể thay đổi theo cấu hình riêng; chính sách không nên dựa vào chuỗi tên principal của khách như một danh tính thật.

| Tình huống | `Authentication` trong context | Ý nghĩa bảo mật |
| --- | --- | --- |
| Không có context authentication | Có thể là `null` | Chưa có authentication object; không nên truy cập thuộc tính mà thiếu null check |
| Anonymous authentication | `AnonymousAuthenticationToken` | Framework biểu diễn người chưa đăng nhập bằng một token đặc biệt |
| Đã đăng nhập với username/password | Ví dụ `UsernamePasswordAuthenticationToken` được xác thực | Danh tính đã được xác thực qua cơ chế cấu hình |
| Remember-me authentication | Ví dụ `RememberMeAuthenticationToken` | Có danh tính được tái lập từ cookie remember-me; không nhất thiết tương đương fresh login |
| JWT Bearer authentication | Ví dụ `JwtAuthenticationToken` | Danh tính hoặc client đã được xác thực theo token và validation của resource server |

### 2.1. Điểm dễ nhầm: isAuthenticated() trên token khác biểu thức isAuthenticated()

Một `AnonymousAuthenticationToken` thông thường **có thể trả `true` khi gọi trực tiếp `Authentication.isAuthenticated()`**. Nhưng các biểu thức bảo mật Spring như `isAuthenticated()` của method security hoặc `AuthenticatedAuthorizationManager` sử dụng logic phân biệt anonymous theo **AuthenticationTrustResolver**.

Do đó, trong chính sách authorization:

| Biểu thức | Anonymous | User đăng nhập bình thường | Remember-me |
| --- | --- | --- | --- |
| `permitAll()` | Cho qua | Cho qua | Cho qua |
| `denyAll()` | Từ chối | Từ chối | Từ chối |
| `isAnonymous()` | Cho qua | Từ chối | Từ chối |
| `isAuthenticated()` | Từ chối | Cho qua | Thường cho qua |
| `isFullyAuthenticated()` | Từ chối | Cho qua | Từ chối |
| `hasAuthority('REPORT_READ')` | Thường từ chối | Phụ thuộc authority | Phụ thuộc authority |

“Cho qua” ở bảng nghĩa là riêng **biểu thức đó** đạt điều kiện; các chốt bảo mật khác như CSRF, URL rules, tenant authorization và business validation vẫn có thể từ chối request.

**Đừng viết** `if (auth != null && auth.isAuthenticated())` rồi coi đó là kiểm tra user thực sự đăng nhập trong mọi ngữ cảnh Servlet. Nếu có anonymous token, điều kiện raw này dễ bị hiểu sai. Ưu tiên policy Spring Security rõ ràng: `.authenticated()`, `.fullyAuthenticated()`, `@PreAuthorize("isAuthenticated()")` hoặc kiểm tra trust resolver khi thật sự cần.

### 2.2. Anonymous không phải tài khoản dùng chung

Một khách anonymous không sở hữu user ID đã được xác minh. Không sử dụng `auth.getName()` của anonymous làm khóa truy cập dữ liệu nhạy cảm hoặc quyền sở hữu tài nguyên. Nếu endpoint công khai cần trạng thái giỏ hàng tạm thời, dùng session/token phù hợp và bảo vệ riêng; không biến anonymous principal thành một user đã xác minh.

Việc anonymous đi qua filter chain cũng không có nghĩa framework tự chứng minh request vô hại. Một endpoint `permitAll()` có thể vẫn nhận input độc hại; cần validation, rate limiting, chống lạm dụng và các kiểm soát thích hợp.

## 3. @WithAnonymousUser hoạt động như thế nào trong Spring Security Test?

`@WithAnonymousUser` nằm trong package:

~~~java
import org.springframework.security.test.context.support.WithAnonymousUser;
~~~

Annotation được Spring Security Test sử dụng thông qua **Spring TestContext** và test execution listener tương ứng. Trước khi chạy test, nó đặt một `SecurityContext` mô phỏng anonymous authentication để các lời gọi bảo mật trong test có thể quan sát trạng thái người chưa đăng nhập.

Ví dụ về hình thức dùng:

~~~java
@Test
@WithAnonymousUser
void anonymousCannotReadPrivateData() {
    // Gọi service đã bật method security và kiểm tra bị từ chối.
}
~~~

Đây mới là **method trong class test**, không phải một chương trình Java độc lập.

**Điều annotation này không làm:**

- Không thực hiện một request HTTP thật tới server.
- Không chạy một luồng browser login hoặc xác thực username/password.
- Không kiểm tra trực tiếp cookie/session đã hết hạn hay Bearer token sai.
- Không đảm bảo `AnonymousAuthenticationFilter` đã chạy trong request network thật.
- Không tự bật `@PreAuthorize`; application/test context vẫn phải có **`@EnableMethodSecurity`**.
- Không tự biến một object được tạo bằng `new MyService()` hoặc một Mockito mock thành Spring AOP proxy bảo mật.

Trong test tích hợp có cấu hình đúng, context được thiết lập theo vòng đời kiểm thử. Spring Security Test cũng có cơ chế dọn context giữa các test; tránh tự thay strategy của `SecurityContextHolder` thành global, hoặc dùng static field giữ user của test trước.

### 3.1. So sánh các annotation thử danh tính

| Cách dùng | Ngữ cảnh tạo ra | Phù hợp để kiểm tra |
| --- | --- | --- |
| `@WithAnonymousUser` | Anonymous authentication | Method bị từ chối với khách, method chỉ cho khách, method công khai |
| `@WithMockUser` | Mock authenticated user, có thể đặt username/roles/authorities | Phân quyền method cho user đã đăng nhập |
| `@WithUserDetails` | Tải user từ `UserDetailsService` theo cấu hình test | Tương tác với dữ liệu người dùng thử nghiệm |
| `@WithSecurityContext` custom | Factory tự tạo SecurityContext theo dữ liệu test | Principal/token/claim/provider đặc thù |
| `SecurityMockMvcRequestPostProcessors.anonymous()` | Anonymous cho **một request MockMvc cụ thể** | Trạng thái khách ở tầng Servlet filter/URL |
| `SecurityMockMvcRequestPostProcessors.user(...)` | Mock user cho request MockMvc | HTTP authorization cho user đã có authentication |

**Phân biệt annotation và request post-processor:** `@WithAnonymousUser` thiết lập context cho phương thức test; còn `.with(anonymous())` chủ đích gắn anonymous vào request `MockMvc`. Khi test HTTP, cách chỉ định trực tiếp bằng request post-processor thường làm trường hợp kiểm thử rõ ràng hơn và ít phụ thuộc vào trạng thái test class.

### 3.2. Đặt annotation ở class hay method?

Với nhiều test anonymous:

~~~java
@WithAnonymousUser
class AnonymousTests {
    @Test
    void firstCase() { /* ... */ }

    @Test
    void secondCase() { /* ... */ }
}
~~~

Khi dùng annotation ở class, hãy kiểm tra framework test đang tích hợp đúng listener. Method có thể có annotation danh tính khác để kiểm tra ngoại lệ một cách chủ đích.

Ví dụ class-level `@WithMockUser` nhưng một method cần khách:

~~~java
@WithMockUser(username = "alice")
class ServiceSecurityTests {

    @Test
    @WithAnonymousUser
    void guestIsDenied() { /* ... */ }
}
~~~

Annotation riêng trên method tạo tình huống anonymous cho test này. Cần đọc tên test và assertion rõ ràng để tránh nhầm “alice” của class-level còn được dùng trong method đó.

## 4. Chuẩn bị project kiểm thử method security

Ví dụ dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x và JUnit Jupiter**. Các code Java trong mục 4–7 là thành phần của một **dự án Spring Boot**, không biên dịch độc lập bằng `javac` nếu không có dependencies và Spring container.

Các dependency Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Lưu ý `spring-security-test` phải có trên **test classpath**. Với Maven, khai báo dependency `org.springframework.security:spring-security-test` ở scope `test`, tương ứng với Spring Boot BOM. Thiếu dependency này, annotation `@WithAnonymousUser` và post-processor `anonymous()` sẽ không được nhận dạng.

Một cấu trúc project mẫu:

~~~text
src/main/java/com/example/demo/
  DemoApplication.java
  MethodSecurityConfig.java
  GreetingService.java
  WebSecurityConfig.java
  DemoController.java
src/test/java/com/example/demo/
  GreetingServiceSecurityTest.java
  AnonymousHttpSecurityTest.java
~~~

### 4.1. Application entry point

File `DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 4.2. Bật method security

File `MethodSecurityConfig.java`:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Trong Spring Security 6, `@EnableMethodSecurity` là cách thông dụng để bật method-level authorization. Nếu không bật, `@PreAuthorize` có thể chỉ còn là annotation hiện diện trong source mà không được áp cho lời gọi service.

Các test phải lấy **Spring bean** thông qua dependency injection; method security thông thường dùng Spring AOP proxy, không tự áp trên object được tạo bằng toán tử `new`.

### 4.3. Service có các policy khác nhau

File `GreetingService.java`:

~~~java
package com.example.demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    @PreAuthorize("isAnonymous()")
    public String anonymousLanding() {
        return "guest";
    }

    @PreAuthorize("isAuthenticated()")
    public String memberProfile() {
        return "member";
    }

    @PreAuthorize("isFullyAuthenticated()")
    public String sensitiveSettings() {
        return "settings";
    }

    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String report() {
        return "report";
    }

    @PreAuthorize("permitAll()")
    public String welcome() {
        return "welcome";
    }
}
~~~

Các method trả hằng số để test chỉ tập trung vào authorization, không trộn với database/API. Trong sản phẩm thật, `memberProfile()` còn phải kiểm tra tài nguyên thuộc user hiện tại; `isAuthenticated()` không thay thế kiểm tra chủ sở hữu dữ liệu.

**Vì sao tách method?** Mỗi method giúp thấy khác biệt giữa “chỉ khách”, “đăng nhập”, “đăng nhập đầy đủ”, “quyền đặc biệt” và “công khai”. Đây cũng là cách tạo test bảo mật có assertion cụ thể thay vì chỉ kiểm mã HTTP chung chung.

## 5. Unit/integration test trực tiếp Spring bean bằng @WithAnonymousUser

File `GreetingServiceSecurityTest.java`:

~~~java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class GreetingServiceSecurityTest {

    @Autowired
    GreetingService service;

    @Test
    @WithAnonymousUser
    void guestMayCallAnonymousOnlyAndPublicMethods() {
        assertEquals("guest", service.anonymousLanding());
        assertEquals("welcome", service.welcome());
    }

    @Test
    @WithAnonymousUser
    void guestCannotCallMethodsRequiringLogin() {
        assertThrows(AccessDeniedException.class,
            service::memberProfile);
        assertThrows(AccessDeniedException.class,
            service::sensitiveSettings);
        assertThrows(AccessDeniedException.class,
            service::report);
    }

    @Test
    @WithMockUser(username = "alice")
    void authenticatedUserIsNotAnonymous() {
        assertThrows(AccessDeniedException.class,
            service::anonymousLanding);
        assertEquals("member", service.memberProfile());
        assertEquals("settings", service.sensitiveSettings());
        assertThrows(AccessDeniedException.class,
            service::report);
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"REPORT_READ"})
    void userWithExplicitAuthorityCanReadReport() {
        assertEquals("report", service.report());
    }
}
~~~

Các method sử dụng `assertThrows(AccessDeniedException.class, ...)` vì chúng gọi **proxy method security** với context anonymous hoặc user thiếu quyền. Khi bảo vệ ở tầng HTTP, ngoại lệ đó có thể được xử lý thành response 401/403 tùy authentication entry point và trust resolver; không được suy ra HTTP status từ test service này.

**Khi nào các test trên đáng tin?**

- `@SpringBootTest` nạp Spring application context từ `DemoApplication`.
- `@EnableMethodSecurity` đã bật pre/post method authorization.
- `GreetingService` được inject từ Spring container, do đó lời gọi thông qua proxy.
- `spring-security-test` và Spring TestContext listener tạo SecurityContext theo annotation cho từng test.
- Không tự mock toàn bộ `GreetingService` hoặc tạo bằng `new`.

Nếu dùng `@MockBean GreetingService` hay Mockito `@Mock GreetingService`, lời gọi đến mock thường **không kiểm tra `@PreAuthorize` của bean thật**. Bài kiểm thử “pass” trong trường hợp đó không chứng minh chính sách authorization của service. Có thể mock repository/downstream dependency, **nhưng giữ service cần test ở dạng bean/proxy thật**.

### 5.1. Vì sao user("alice") mặc định thiếu REPORT_READ?

`@WithMockUser(username = "alice")` thông thường tạo user có vai trò mặc định (ví dụ `ROLE_USER`), không tự thêm authority `REPORT_READ`. Vì service dùng `hasAuthority('REPORT_READ')`, test yêu cầu khai báo **`authorities={"REPORT_READ"}`**.

Đừng nhầm:

- `roles={"ADMIN"}` thường được biến thành authority `ROLE_ADMIN`.
- `authorities={"ADMIN"}` là authority với tên **nguyên văn** `ADMIN`.
- `hasRole('ADMIN')` và `hasAuthority('ROLE_ADMIN')` thường có ý nghĩa tương đương theo default role prefix; `hasAuthority('ADMIN')` thì không giống.

Khi test đã đăng nhập nhưng thiếu quyền, đừng dùng `@WithAnonymousUser` thay thế. Cần user authenticated riêng để xác minh hệ thống không nhầm **“chưa đăng nhập”** với **“đã đăng nhập nhưng không được phép”**.

### 5.2. Có thể áp annotation ở cấp class

Nếu phần lớn test cần khách:

~~~java
@SpringBootTest
@WithAnonymousUser
class GuestMethodTests {
    @Autowired
    GreetingService service;

    @Test
    void publicMethodWorks() {
        assertEquals("welcome", service.welcome());
    }

    @Test
    @WithMockUser(username = "alice")
    void specialUserOverride() {
        assertEquals("member", service.memberProfile());
    }
}
~~~

Đoạn trên **minh họa class riêng**, cần imports tương tự mục 5; không đặt thêm một class cùng tên vào file test khác rồi kỳ vọng chạy như một compilation unit. Annotation method giúp ghi đè ngữ cảnh test theo mục đích.

### 5.3. Không có Authentication khác với @WithAnonymousUser

Một số lập trình viên dùng `@WithAnonymousUser` để mô phỏng **`SecurityContextHolder.clearContext()`**. Không chính xác:

- Khi xóa hoàn toàn `SecurityContextHolder`, `getAuthentication()` có thể là `null`.
- Với `@WithAnonymousUser`, test tạo anonymous authentication cho security expression.
- Trong một request Servlet thông thường, `AnonymousAuthenticationFilter` có thể tạo token anonymous; nhưng trước khi filter chạy, trong thread nền hoặc custom chain, Authentication có thể thật sự null.

Nếu nghiệp vụ quan tâm “chưa có `Authentication` object”, hãy viết test riêng cho **empty context**. Tuy nhiên test method security thường nên mô phỏng điều kiện **anonymous thực tế của Servlet** bằng `@WithAnonymousUser`. Đừng trộn hai ngữ cảnh rồi khẳng định `null == AnonymousAuthenticationToken`.

## 6. Kiểm thử tầng HTTP với MockMvc: 401 và 403 là hai trường hợp khác

`@WithAnonymousUser` rất phù hợp để test method. Nhưng để kiểm tra **Servlet filter chain, status code, entry point và response**, cần thêm HTTP test với `MockMvc` hoặc integration test thật.

Cấu hình ví dụ trong `WebSecurityConfig.java`:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/account").authenticated()
                .requestMatchers("/api/reports")
                    .hasAuthority("REPORT_READ")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây là policy đơn giản cho mục đích học. Production thường có nhiều endpoint, CORS/CSRF, session hoặc bearer authentication; cần thiết kế đầy đủ. `httpBasic()` được bật để ví dụ có phản hồi **401** cho khách thay vì redirect tới login page. Nếu dùng form login, một request anonymous có thể nhận **302 redirect**; nếu API Bearer, challenge thường là `WWW-Authenticate: Bearer`.

Controller file `DemoController.java`:

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public Map<String, String> publicData() {
        return Map.of("visibility", "public");
    }

    @GetMapping("/api/account")
    public Map<String, String> account() {
        return Map.of("visibility", "private");
    }

    @GetMapping("/api/reports")
    public Map<String, String> reports() {
        return Map.of("visibility", "reports");
    }
}
~~~

Với Spring MVC, endpoint `/api/public` được phép anonymous; `/api/account` yêu cầu authenticated; `/api/reports` còn cần authority chính xác.

### 6.1. MockMvc test những trạng thái HTTP

File `AnonymousHttpSecurityTest.java`:

~~~java
package com.example.demo;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.anonymous;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AnonymousHttpSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCanReadPublicButNotPrivate() throws Exception {
        mvc.perform(get("/api/public").with(anonymous()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.visibility").value("public"));

        mvc.perform(get("/api/account").with(anonymous()))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/reports").with(anonymous()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedWithoutReportAuthorityIsForbidden()
            throws Exception {
        mvc.perform(get("/api/reports").with(user("alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedWithReportAuthorityMayContinue()
            throws Exception {
        mvc.perform(get("/api/reports")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("REPORT_READ"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.visibility").value("reports"));
    }
}
~~~

**Ghi chú khi sao chép import Java:** để tương thích mọi compiler/style checker, hãy đặt mỗi khai báo `import static ...;` trên **một dòng**. Chẳng hạn, import đầy đủ cho `anonymous` là:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.anonymous;
~~~

Các import ở ví dụ nhiều dòng nhằm trình bày dễ đọc trong Markdown; khi đưa vào file Java thực tế, chuẩn hóa chúng thành import một dòng. Cách chia thành nhiều dòng không làm thay đổi cấu trúc class, nhưng build formatter của dự án có thể có quy tắc nghiêm ngặt.

**Cách test hoạt động:**

- `.with(anonymous())` áp dụng anonymous cho request đó. Nó khác với đặt `@WithAnonymousUser` trên phương thức JUnit, dù cả hai đều giúp mô phỏng khách.
- `.with(user("alice"))` tạo mock authenticated user; nó **không** gửi đúng chuỗi Basic password qua mạng và **không** kiểm thử `UserDetailsService` hoặc password encoder.
- Với `httpBasic()` và policy phía trên, khách ở route private thường nhận `401 Unauthorized` (HTTP Basic entry point); user authenticated nhưng thiếu `REPORT_READ` nhận `403 Forbidden`.
- `@AutoConfigureMockMvc` kết hợp Spring Boot Test cung cấp MockMvc sử dụng Spring Security filter chain khi cấu hình hợp lệ. Nếu tự dựng standalone MockMvc, cần áp dụng cấu hình Spring Security Test đúng cách; không tự giả định filter chain luôn chạy.

**Không biến `401/403` thành assertion chung cho mọi ứng dụng**: HTTP status phụ thuộc entry point (Basic/form/OAuth), exception translation, URL rule, custom handler và proxy. Trong service-level test, `AccessDeniedException` không phải một HTTP response.

### 6.2. Chưa đăng nhập do session hết hạn có giống anonymous không?

Khi browser có session cookie nhưng session đã hết hạn/không tồn tại, request vào endpoint yêu cầu đăng nhập có thể được xử lý như một khách anonymous **sau khi các filter đọc session và thiết lập security context**. Tuy nhiên `@WithAnonymousUser` không test được:

- Cookie thực tế có bị browser gửi hay không.
- Session repository/JDBC/Redis xử lý ID không tồn tại ra sao.
- Request cache, redirect tới login, CSRF token của session cũ.
- Session fixation defense, logout invalidation và concurrency control.

Muốn kiểm tra các vấn đề đó, viết **MockMvc với session lifecycle rõ ràng** hoặc integration test HTTP/browser có cookie jar, không chỉ annotation.

### 6.3. Còn “anonymous với token sai” thì sao?

Request hoàn toàn thiếu credentials khác với request **cung cấp credential sai**. Ví dụ API Resource Server nhận:

~~~http
GET /api/account HTTP/1.1
Authorization: Bearer broken-token
~~~

Filter có thể thử decode token và trả lỗi xác thực ngay cả khi endpoint sử dụng `permitAll()`, vì permitAll chỉ là chính sách **authorization** chứ không nhất thiết tắt **authentication filter**.

`@WithAnonymousUser` không kích hoạt decoder JWT, kiểm tra chữ ký, expiry, issuer hoặc introspection. Muốn test token lỗi, cần gửi HTTP header giả với decoder/mock hoặc test tích hợp Authorization Server/Resource Server phù hợp, rồi xác nhận `401 invalid_token` hoặc mã tương ứng theo giao thức.

## 7. Kiểm thử các trường hợp chưa đăng nhập khó hơn

### 7.1. Không có auth, anonymous và remember-me

| Trạng thái | Cách tạo test phù hợp | Bài test cần khẳng định |
| --- | --- | --- |
| Anonymous trong method security | `@WithAnonymousUser` | `isAnonymous()` true; `isAuthenticated()`/role có bảo vệ đúng |
| Anonymous tại HTTP request | `.with(anonymous())` | Public OK; private bị entry point chặn |
| Empty SecurityContext | Xóa hoặc cấu hình context rỗng trong test riêng | Code không ném NullPointerException, policy fail closed |
| User có mật khẩu hợp lệ đã đăng nhập | `@WithMockUser` hoặc `.with(user(...))` | Được quyền tối thiểu đúng vai trò |
| Remember-me | Tạo `RememberMeAuthenticationToken` phù hợp hoặc integration test cookie | `isAuthenticated()` có thể true nhưng `isFullyAuthenticated()` false |
| User đăng nhập nhưng thiếu authority | `@WithMockUser` không có authority cần thiết | Access denied/HTTP 403, không được coi là khách |

**Remember-me** đặc biệt quan trọng với thao tác nhạy cảm: một cookie nhớ đăng nhập không đồng nghĩa người dùng vừa xác minh mật khẩu/MFA. Hãy test `fullyAuthenticated()` hoặc policy step-up nếu thao tác đổi mật khẩu, thay email khôi phục, chuyển tiền.

Đừng gán thuộc tính `authenticated=true` thủ công lên token không đáng tin chỉ để test pass; nên tạo authentication đúng loại và dùng API test tiêu chuẩn để phản ánh mô hình bảo mật thật.

### 7.2. Khách vẫn có thể được phép xem trang công khai

Một method ghi `@PreAuthorize("permitAll()")` là public về method authorization, kể cả có SecurityContext anonymous. Nhưng nếu controller tương ứng nằm sau URL rule `.authenticated()`, request guest vẫn có thể bị chặn **trước khi method được gọi**. Ngược lại, endpoint URL `permitAll()` mà gọi service `@PreAuthorize("isAuthenticated()")` thì khách có thể bị từ chối **trong service**.

Do đó cần test **hai tầng**:

- Tầng service: `@WithAnonymousUser` và lời gọi qua proxy.
- Tầng Servlet: `MockMvc` với request anonymous, đúng filter chain, URL matcher và HTTP entry point.

Tình huống lộ dữ liệu thường phát sinh khi developer chỉ test một tầng rồi suy rằng tầng kia cũng đã bảo vệ.

### 7.3. Unauthenticated vs unauthenticated nhưng session còn dữ liệu

Một session có thể chứa thông tin UI hoặc giỏ hàng của khách, nhưng **không biến nó thành user authenticated**. Khi test, không sử dụng session attribute như `login=true`/`username="alice"` để giả định Spring Security tin đó là Authentication. Spring Security quản lý context qua các cơ chế/filter/repository của mình. Khi thiết kế custom authentication, mọi việc “đặt vào context” phải xuất phát từ chứng cứ được server xác minh.

Nếu session mang SecurityContext cũ nhưng credential bị thu hồi, cần policy revoke/session invalidation thích hợp. Chỉ test `@WithAnonymousUser` không bao phủ phân tán session, logout và thu hồi trong production.

### 7.4. Authentication exception khác authorization exception

Một `AuthenticationException` thường có ý nghĩa authentication thất bại hoặc không có credentials hợp lệ; `AccessDeniedException` thể hiện không được phép truy cập. Trong HTTP pipeline, `ExceptionTranslationFilter` thường dùng trust resolver và các handler để chọn cách trả challenge hoặc response bị từ chối.

Với method test, Spring Security có thể ném `AccessDeniedException` khi anonymous không đạt `@PreAuthorize`. Trong HTTP pipeline, request tương tự lại có thể được chuyển thành `401` bởi `AuthenticationEntryPoint`, bởi vì anonymous cần được mời xác thực chứ không chỉ nhận lỗi thiếu quyền.

**Đừng viết assertion “method @PreAuthorize luôn ném HTTP 401”.** Method không biết HTTP nếu nó được gọi trực tiếp từ một test/service không qua Servlet pipeline.

## 8. CSRF, method HTTP và anonymous

CSRF không chỉ quan trọng với user đã đăng nhập. Nếu ứng dụng sử dụng cookie/session và có endpoint thay đổi trạng thái, cần kiểm tra CSRF policy. Ví dụ `POST /signup` có thể là public theo authentication nhưng vẫn chịu kiểm soát CSRF hoặc chính sách ngoại lệ cụ thể.

Với `MockMvc`:

~~~java
mvc.perform(post("/public-action")
        .with(anonymous()))
    .andExpect(status().isForbidden());
~~~

Đây là **trích đoạn của test đã có `MockMvc mvc`, static imports và endpoint/cấu hình CSRF phù hợp**; status phụ thuộc URL và chain. Nếu route cho phép anonymous nhưng vẫn bật CSRF, POST thiếu CSRF token thường bị `403` ngay trước controller. Nó không chứng minh khách bị từ chối vì chưa đăng nhập.

Để test request hợp lệ với CSRF:

~~~java
mvc.perform(post("/public-action")
        .with(anonymous())
        .with(csrf()))
    .andExpect(status().isOk());
~~~

Ví dụ này chỉ đúng nếu `/public-action` là endpoint POST thực sự tồn tại, được `permitAll()` và controller trả 200; nó **không phải một route đã khai báo trong DemoController ở mục 6**. Cần tạo fixture tương ứng trước khi chạy.

Không bỏ qua vấn đề này khi viết test guest. Một `403` có thể đến từ **thiếu CSRF token**, không phải từ `@PreAuthorize` hoặc URL authorization. Kiểm thử cần xác định lý do từ chối đúng lớp.

## 9. Lỗi kiểm thử hay gặp

| Biểu hiện | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `@WithAnonymousUser` không có tác dụng | Test không chạy Spring TestContext/listener | Dùng Spring test integration, `@SpringBootTest` hoặc context phù hợp |
| Method có `@PreAuthorize` nhưng anonymous vẫn gọi được | Chưa bật method security, gọi object qua `new`, self-invocation | Bật `@EnableMethodSecurity`, inject bean/proxy và gọi qua proxy |
| Test pass với Mockito mock của service | Mock không chạy method interceptor | Giữ service bean thật, chỉ mock phụ thuộc bên dưới |
| `getAuthentication() == null` assertion thất bại | AnonymousAuthenticationToken đã có trong context | Phân biệt anonymous token và empty context |
| `Authentication.isAuthenticated()` true dù khách chưa login | Raw token flag không phản ánh trust resolver | Dùng `isAuthenticated()` expression hoặc resolver phù hợp |
| Test HTTP mong 403 nhưng nhận 401 | Anonymous được đưa tới authentication entry point | Kiểm tra Basic/Bearer/form login và authorization flow |
| Test HTTP mong 401 nhưng nhận 302 | Form login redirect tới trang đăng nhập | Assert redirect hoặc chuyển test fixture sang HTTP Basic |
| Test guest bị 403 trên POST công khai | CSRF filter chặn trước method/controller | Test `.with(csrf())` và phân biệt nguyên nhân từ chối |
| `@WithMockUser(roles="ADMIN")` vẫn không đạt hasAuthority("ADMIN") | Prefix `ROLE_` khác chuỗi authority | Dùng `hasRole("ADMIN")` hoặc authority rõ ràng đúng policy |
| API public có Bearer token sai vẫn trả 401 | Filter thử authenticate trước khi authorization permitAll | Kiểm tra BearerTokenResolver/resource-server filters |
| Test service thấy quyền đúng nhưng HTTP vẫn bị chặn | URL matcher/filter chain khác service policy | Kiểm thử cả method và Servlet với MockMvc |
| Một test bị ảnh hưởng user của test trước | Tự thiết lập holder/strategy mà không cleanup | Dùng test listener và clear context trong finally khi setup thủ công |
| Guest xem được thông tin account trong response | Endpoint/service thiếu check, hoặc business object không gắn quyền sở hữu | Áp URL + method/resource authorization; test dữ liệu cụ thể |

### Kết quả chạy minh họa

Với project Gradle đã có application/config/test files đúng như mục 4–6:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Nếu test trong project Maven đã khai báo dependency tương đương:

~~~bash
./mvnw test
~~~

Output test runner phụ thuộc phiên bản Gradle/Maven/JUnit, nên không giả lập nguyên văn dòng `BUILD SUCCESSFUL` hoặc số lượng test khi chưa chạy. Điều cần đánh giá là test thật sự tải Spring context, đi qua method security proxy và các assertion đúng như dự kiến.

## 10. Mẫu kiểm thử bổ sung: anonymous ngay cả khi mặc định class là user

Một test suite lớn có thể dùng `@WithMockUser` cấp class để bớt lặp. Khi thêm test anonymous, cần định danh rõ để không vô tình kế thừa user.

Mã sau là **class minh họa riêng**, có imports tương tự mục 5:

~~~java
@SpringBootTest
@WithMockUser(username = "tester", authorities = {"REPORT_READ"})
class DefaultLoggedInSuite {

    @Autowired
    GreetingService service;

    @Test
    void defaultUserCanReadReport() {
        assertEquals("report", service.report());
    }

    @Test
    @WithAnonymousUser
    void anonymousOverrideCannotReadReport() {
        assertThrows(AccessDeniedException.class,
            service::report);
    }
}
~~~

Điểm đáng học: annotation `@WithAnonymousUser` trên **test method** khiến test riêng đó không dùng mock user đã khai ở class. Đảm bảo không có `@BeforeEach` tự ghi đè `SecurityContextHolder`, vì như vậy có thể làm tình huống test không còn tương ứng với tên test.

Nếu dự án có nhiều cơ chế identity (JWT, OAuth2 Login, SAML), nên tạo các test case riêng cho từng principal/token type, không dùng một `@WithMockUser` chung để “chứng minh” mọi cơ chế login.

## 11. Biến thể: kiểm thử lỗi khi SecurityContext trống thật sự

Trong một số service/worker chạy **ngoài Servlet filter chain**, `SecurityContextHolder.getContext().getAuthentication()` có thể là `null`. Khi đó, mục tiêu test là kiểm tra code fail closed và không ném `NullPointerException` ngoài ý muốn.

Một ví dụ **Java 17 thuần** chạy được, không cần Spring, minh họa phân biệt `null` và một dấu anonymous:

File `GuestStateDemo.java`:

~~~java
public class GuestStateDemo {
    enum AuthState {
        MISSING, ANONYMOUS, AUTHENTICATED
    }

    static boolean mayReadPrivate(AuthState state) {
        return state == AuthState.AUTHENTICATED;
    }

    static boolean mayReadPublic(AuthState state) {
        return state != null;
    }

    public static void main(String[] args) {
        System.out.println(mayReadPrivate(AuthState.MISSING));
        System.out.println(mayReadPrivate(AuthState.ANONYMOUS));
        System.out.println(mayReadPrivate(AuthState.AUTHENTICATED));
        System.out.println(mayReadPublic(AuthState.ANONYMOUS));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac GuestStateDemo.java
java GuestStateDemo
~~~

Stdout **chính xác**:

~~~text
false
false
true
true
~~~

Ví dụ này chỉ mô hình hóa policy tối giản. Trong Spring Security thật, lựa chọn trạng thái phải dựa trên authentication được xác minh và logic authorization của framework; không dùng enum do client truyền để quyết định quyền.

Với Spring, nếu cần chủ đích xóa context trong một test hẹp, có thể dùng:

~~~java
SecurityContextHolder.clearContext();
Authentication value =
    SecurityContextHolder.getContext().getAuthentication();
assertNull(value);
~~~

Đây là **đoạn test**, cần static import `Assertions.assertNull` và Spring Security context import; nếu test có cấu hình holder strategy đặc biệt, phải kiểm soát vòng đời và dọn trong `finally`. Không lấy hành vi context trống đó làm bằng chứng rằng một Servlet request thực tế đi qua anonymous filter cũng chứa authentication null.

## 12. Kiểm tra sự khác biệt giữa @WithAnonymousUser và anonymous() bằng một kế hoạch QA

**Nhóm A – method authorization:** chạy `GreetingServiceSecurityTest`. Kết quả mong đợi: khách được phép gọi `anonymousLanding()` và `welcome()`, nhưng bị từ chối ở `memberProfile()`, `sensitiveSettings()` và `report()`. User được cấp `REPORT_READ` mới gọi `report()` thành công. Đây là kiểm tra **AOP method security**.

**Nhóm B – HTTP authorization:** chạy `AnonymousHttpSecurityTest`. Kết quả mong đợi với HTTP Basic: `/api/public` trả 200, `/api/account` và `/api/reports` khi anonymous trả 401, user đăng nhập không có authority ở `/api/reports` trả 403, user có authority trả 200. Đây là kiểm tra **filter chain, URL authorization và entry point**.

**Nhóm C – failure mode:** tạo các test không cookie, session hết hạn, Basic password sai, JWT hết hạn, POST thiếu CSRF, remember-me, route không tồn tại. Những ca này **không được thay thế bằng một `@WithAnonymousUser` duy nhất**; chúng cần fixture và pipeline phù hợp.

**Nhóm D – chống rò thông tin:** với guest, kiểm tra response không chứa dữ liệu của user khác, authorities, access token, stack trace hoặc thông tin session. Một phản hồi 401 đúng vẫn chưa đủ nếu body/log làm lộ dữ liệu nhạy cảm.

**Nhóm E – cách ly test:** chạy test theo thứ tự ngẫu nhiên hoặc song song trong phạm vi cấu hình được hỗ trợ, xác minh không có người dùng của test trước lọt sang test sau. Nếu tự tạo SecurityContext, phải dọn đúng thread và không dùng holder strategy global.

## 13. Checklist trước khi kết luận method security hoạt động

- [ ] Thêm `spring-security-test` với phiên bản tương thích Boot/Security.
- [ ] Dùng Spring TestContext (ví dụ `@SpringBootTest`) để `@WithAnonymousUser` được thực thi.
- [ ] Bật `@EnableMethodSecurity` để `@PreAuthorize` thực sự được áp dụng.
- [ ] Inject service bean từ Spring, không gọi object `new` hoặc một Mockito mock thay cho service cần kiểm tra.
- [ ] Kiểm tra `isAnonymous()`, `isAuthenticated()`, `isFullyAuthenticated()` và authority theo đúng semantics.
- [ ] Không xem `AnonymousAuthenticationToken` là user đăng nhập chỉ vì raw `isAuthenticated()` có thể true.
- [ ] Tách test guest khỏi test user authenticated nhưng thiếu role/scope.
- [ ] Với HTTP, dùng MockMvc và post-processor `anonymous()`; kiểm tra entry point Basic/Bearer/form khác nhau.
- [ ] Phân biệt method exception với mã HTTP `401/403/302` do filter pipeline chuyển đổi.
- [ ] Không lấy `permitAll()` của URL làm bằng chứng các service phía sau đã được bảo vệ.
- [ ] Có test request sai credentials, session expiry, remember-me và CSRF nếu ứng dụng hỗ trợ.
- [ ] Đảm bảo test runner thực sự chạy security filter chain và security AOP, không phải fixture bỏ qua chúng.
- [ ] Test không lộ dữ liệu riêng trong body/log, kể cả khi server trả đúng status lỗi.
- [ ] Dọn SecurityContext sau setup thủ công, tránh rò user giữa các test/thread.

**Kết luận:** `@WithAnonymousUser` là công cụ kiểm thử **ngữ cảnh anonymous** ở Spring Security Test, rất phù hợp để xác nhận method `@PreAuthorize` bảo vệ đúng người chưa đăng nhập. Nó không đồng nghĩa với context rỗng hoặc mô phỏng một HTTP request thất bại hoàn chỉnh. Để kiểm thử Servlet security toàn diện, cần kết hợp **service test qua Spring AOP proxy**, **MockMvc với `anonymous()`** và các ca riêng cho credential sai, session expiry, remember-me, CSRF và người đã đăng nhập nhưng thiếu quyền.
