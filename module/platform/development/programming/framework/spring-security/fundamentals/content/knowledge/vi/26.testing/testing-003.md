# @WithMockUser, @WithAnonymousUser và danh tính dùng trong kiểm thử Spring Security

> **Phạm vi:** Spring Security fundamentals, nhóm **Kiểm thử**. Bài này hướng dẫn tạo danh tính cho test bằng `@WithMockUser», `@WithAnonymousUser», `@WithUserDetails» và các `RequestPostProcessor» của Spring Security Test; kiểm tra anonymous, authenticated, role/authority, method security và giới hạn của mock. Ví dụ dùng **Java 17, Spring Boot 3.3.x, Spring Security 6.x, JUnit 5, MockMvc (Servlet/Spring MVC)**. Phần WebFlux được phân biệt ở cuối.

## 1. Vì sao cần danh tính riêng cho mỗi bài kiểm thử?

Trong ứng dụng được bảo vệ, cùng một URL hoặc phương thức có thể cho kết quả khác nhau tùy người gọi:

- **Anonymous**: chưa đăng nhập; thường phải xác thực khi truy cập tài nguyên riêng tư.
- **Authenticated, ít quyền**: đã xác thực nhưng không có authority cần thiết, thường nhận 403.
- **Authenticated, đủ quyền**: được phép chạy controller/service và nhận kết quả nghiệp vụ.
- **Principal tùy biến**: không chỉ có username mà còn tenant ID, customer ID hay thông tin hồ sơ phục vụ nghiệp vụ.

Để kiểm thử quy tắc ủy quyền, ta cần thiết lập một `Authentication» đáng tin cậy trong **môi trường test**. Spring Security Test cung cấp annotation và request post-processor giúp làm việc đó mà không cần viết giao diện login hoặc gọi kho user ở mọi test.

**Giới hạn quan trọng:** một danh tính được *giả lập* là đầu vào của phép kiểm tra quyền, **không chứng minh quá trình xác thực mật khẩu, JWT, OAuth2 hay cookie đã hoạt động đúng**. Để kiểm tra authentication thật, phải gửi credential/token qua cơ chế tương ứng và kiểm tra filter/provider/decoder thực tế.

## 2. Nền tảng: SecurityContext, Authentication và principal

Khi request đã được xác thực trong ứng dụng Servlet, Spring Security thường đặt `Authentication» vào `SecurityContext», và `SecurityContextHolder» giúp truy cập nó trong luồng request. Một `Authentication» có:

| Thuộc tính | Ví dụ | Tác dụng trong test |
| --- | --- | --- |
| `principal» | `UserDetails», JWT claims, đối tượng domain | Đại diện danh tính; type ảnh hưởng code nhận `@AuthenticationPrincipal» |
| `name» | `"mai"» | Có thể được dùng trong kiểm tra chủ sở hữu |
| `authorities» | `ROLE_ADMIN», `SCOPE_docs.read» | Đầu vào trực tiếp cho `hasRole»/`hasAuthority» |
| `credentials» | Password hoặc giá trị giả trong test | Với mock, không phải credential được backend xác thực |
| `authenticated» | Trạng thái do Spring Security định nghĩa | Không dùng riêng cờ này để nhận diện anonymous trong mọi trường hợp |

Khi chạy test, `WithSecurityContextTestExecutionListener» của `spring-security-test» thiết lập và dọn `SecurityContextHolder» theo annotation trước/sau test. Với `@SpringBootTest»/Spring Test thông thường, listener được tích hợp cùng Spring Test; không cần viết `ThreadLocal» hoặc tự giữ trạng thái giữa các test.

**Lưu ý:** `AnonymousAuthenticationToken» cũng là một `Authentication» và có thể có `isAuthenticated() == true» theo cách implementation đặt cờ. Hãy dùng `authenticated()», `isAuthenticated()» trong Spring Security expression hoặc cơ chế `AuthenticationTrustResolver» phù hợp để phân biệt anonymous, thay vì tự suy luận chỉ từ một cờ.

### Tại sao dùng mock thay vì đăng nhập thật trong mọi test?

- Kiểm tra quy tắc URL/method nhanh và độc lập với username/password thực.
- Tạo nhiều vai trò, scope và danh tính biên dễ dàng.
- Tránh phụ thuộc IdP, database hoặc token signing key trong các bài kiểm thử quyền đơn vị/tích hợp nhỏ.
- Khi test cần chính xác principal type hoặc luồng đăng nhập thật, có công cụ khác chuyên biệt hơn.

Tuy vậy, vẫn cần **một lớp kiểm thử riêng cho cơ chế xác thực thật**. Ví dụ: test HTTP Basic với password đúng/sai; test JWT với decoder/key; test đăng nhập form và quản lý session/CSRF; test OAuth2 callback hoặc token exchange theo đúng phạm vi cần xác minh.

## 3. @WithMockUser: thiết lập danh tính giả cho test

`@WithMockUser» thuộc package `org.springframework.security.test.context.support». Có thể đặt ở method hoặc class test. Annotation tạo `SecurityContext» chứa `UsernamePasswordAuthenticationToken» với principal thường là một `User» của Spring Security.

Cấu hình mặc định:

```java
@Test
@WithMockUser
void runsAsDefaultUser() {
    // username = "user"
    // password trong principal = "password" (giá trị giả)
    // authorities = ["ROLE_USER"]
}
```

Đây là **fragment** của JUnit 5, cần import `@Test» và `@WithMockUser»; không phải file độc lập.

Tùy biến username và role:

```java
@Test
@WithMockUser(username = "mai", roles = {"USER", "ADMIN"})
void runsAsMaiWithTwoRoles() {
    // name = "mai"
    // authorities = ROLE_USER, ROLE_ADMIN
}
```

**Role không giống authority:**

- `@WithMockUser(roles = "ADMIN")» tạo authority `ROLE_ADMIN» theo quy ước mặc định.
- `@WithMockUser(authorities = "SCOPE_docs.read")» giữ **đúng chuỗi** `SCOPE_docs.read», không thêm `ROLE_».
- `hasRole("ADMIN")» theo cấu hình role prefix mặc định kiểm tra `ROLE_ADMIN».
- `hasAuthority("SCOPE_docs.read")» kiểm tra chính xác chuỗi `SCOPE_docs.read».
- Khi dùng `authorities», không đồng thời cấu hình `roles» theo cách mâu thuẫn. Nếu muốn cả role và scope, truyền chúng chung vào `authorities = {"ROLE_ADMIN", "SCOPE_docs.read"}».
- Không truyền `roles = "ROLE_ADMIN"» để cố yêu cầu tiền tố hai lần; với `roles» hãy dùng tên role không có `ROLE_».

Ví dụ thiết lập authority chính xác:

```java
@Test
@WithMockUser(
    username = "reader",
    authorities = {"ROLE_READER", "SCOPE_docs.read"}
)
void hasRoleAndScope() {
    // Có cả ROLE_READER và SCOPE_docs.read.
}
```

**Không có lời gọi xác minh password nào xảy ra chỉ vì `@WithMockUser(password = "...")».** Dù bạn đặt password là một giá trị sai, test vẫn có danh tính giả đã xác thực. Thuộc tính `password» dành cho principal của test, không phải input để `PasswordEncoder.matches» hoặc `AuthenticationProvider» kiểm tra.

## 4. @WithAnonymousUser: test khi chưa đăng nhập

`@WithAnonymousUser» cũng thuộc `org.springframework.security.test.context.support». Annotation tạo môi trường anonymous; với test context, Spring Security dùng `AnonymousAuthenticationToken».

```java
@Test
@WithAnonymousUser
void anonymousCannotViewPrivatePage() throws Exception {
    mvc.perform(get("/api/me"))
        .andExpect(status().isUnauthorized());
}
```

Đây là fragment: `mvc» là `MockMvc» đã tích hợp Spring Security, route và HTTP Basic entry point phải được cấu hình tương ứng. 401 là kỳ vọng của **cấu hình ví dụ bên dưới**, không phải mọi ứng dụng anonymous đều trả 401; form login có thể redirect 302.

### Ghi đè danh tính mặc định ở mức class

Có thể đặt `@WithMockUser» ở class để phần lớn test chạy dưới tài khoản giả, rồi ghi đè ở một test:

```java
@WithMockUser(username = "staff", roles = "USER")
class ExampleIdentityTests {

    @Test
    void authenticatedByDefault() {
        // Chạy với staff / ROLE_USER.
    }

    @Test
    @WithAnonymousUser
    void explicitlyAnonymous() {
        // Phương thức này dùng anonymous thay cho staff.
    }
}
```

Đoạn này chỉ minh họa **annotation scope**; thêm class/method test thực sự và cấu hình Spring Test khi áp dụng. Mức method được ưu tiên cho method đó. Cách đặt test tường minh giúp không vô tình kiểm thử tài nguyên công khai bằng một user đã đăng nhập.

### Anonymous khác với quyền USER

Không nên giả định anonymous có `ROLE_USER» hoặc quyền truy cập tài nguyên chỉ vì security context có một token. Với `@WithAnonymousUser», bạn cần test hành vi riêng cho tài nguyên `permitAll», `authenticated», `hasRole» và cơ chế yêu cầu đăng nhập của ứng dụng.

## 5. Ví dụ chạy được: Spring Boot 3.3 + MockMvc + Method Security

Bộ ví dụ sau dùng HTTP Basic để kiểm tra credential thật bên cạnh annotation mock. Nó có bốn tài nguyên:

- `GET /api/public» ai cũng truy cập được.
- `GET /api/me» cần authenticated, trả `Authentication.getName()».
- `GET /api/admin» chỉ cho `ROLE_ADMIN».
- `GET /api/scoped» yêu cầu authority `SCOPE_docs.read» thông qua `@PreAuthorize».

Mỗi đường đi tách rõ **xác thực**, **ủy quyền theo URL**, và **ủy quyền mức phương thức**.

### 5.1 Cấu trúc dự án

```text
security-test-identities/
├── pom.xml
└── src/
    ├── main/java/com/example/securitytest/
    │   └── SecurityTestDemoApplication.java
    └── test/java/com/example/securitytest/
        └── SecurityTestDemoApplicationTest.java
```

### 5.2 Maven dependencies

Tạo `pom.xml», dùng Java 17, Spring Boot 3.3.5. `spring-security-test» bắt buộc để có `@WithMockUser», `@WithAnonymousUser», `@WithUserDetails» và các `RequestPostProcessor» bảo mật.

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
    <artifactId>security-test-identities</artifactId>
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

### 5.3 Ứng dụng và quy tắc quyền

Tạo `src/main/java/com/example/securitytest/SecurityTestDemoApplication.java»:

```java
package com.example.securitytest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
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
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityTestDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityTestDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails actualAdmin = User.withUsername("real-admin")
            .password(encoder.encode("demo123"))
            .roles("ADMIN")
            .build();
        return new InMemoryUserDetailsManager(actualAdmin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }

    @RestController
    static class DemoController {

        @GetMapping("/api/public")
        public String publicPage() {
            return "public ok";
        }

        @GetMapping("/api/me")
        public String currentUser(Authentication authentication) {
            return authentication.getName();
        }

        @GetMapping("/api/admin")
        public String adminOnly() {
            return "admin ok";
        }

        @PreAuthorize("hasAuthority('SCOPE_docs.read')")
        @GetMapping("/api/scoped")
        public String scopedOnly() {
            return "scope ok";
        }
    }
}
```

**Cách suy luận kết quả:**

1. `/api/public» luôn được `permitAll», kể cả anonymous.
2. `/api/me» chỉ kiểm tra đã authenticated, dùng username của `Authentication» để phản hồi.
3. `/api/admin» dùng `hasRole("ADMIN")», mặc định đòi `ROLE_ADMIN».
4. `/api/scoped» đi qua rule `authenticated» của URL, sau đó `@PreAuthorize» kiểm tra chính xác `SCOPE_docs.read». `@EnableMethodSecurity» là điều kiện để annotation method-security được xử lý trong demo này.
5. `httpBasic» cung cấp authentication entry point 401 cho request không có hoặc sai credential; đã đăng nhập nhưng thiếu quyền thì thường nhận 403. `formLogin» bị tắt để demo không redirect sang trang login.
6. User `real-admin» là tài khoản **thực trong kho in-memory của ứng dụng demo**. Không có username `mai», `reader», `staff» trong kho này, nhưng `@WithMockUser» vẫn có thể tạo danh tính đó trong test. Đây chính là khác biệt cần kiểm chứng.
7. Mật khẩu `demo123» chỉ dùng để học; `BCryptPasswordEncoder» được dùng cho việc lưu hash, nhưng production cần secret/policy/phân quyền và kho danh tính thích hợp.

### 5.4 Kiểm thử hoàn chỉnh bằng JUnit 5 và MockMvc

Tạo file `src/test/java/com/example/securitytest/SecurityTestDemoApplicationTest.java»:

```java
package com.example.securitytest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityTestDemoApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser
    void defaultMockUserHasUsernameUser() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(content().string("user"));
    }

    @Test
    @WithMockUser(username = "mai", roles = "USER")
    void namedMockUserIsAuthenticated() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(content().string("mai"));
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotReadPrivateEndpoint() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithAnonymousUser
    void anonymousCanReadPublicEndpoint() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public ok"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void regularUserCannotOpenAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "fake-admin", roles = "ADMIN")
    void mockAdminCanOpenAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin ok"));
    }

    @Test
    @WithMockUser(authorities = "SCOPE_docs.read")
    void scopeAuthorityPassesMethodSecurity() throws Exception {
        mvc.perform(get("/api/scoped"))
            .andExpect(status().isOk())
            .andExpect(content().string("scope ok"));
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminRoleDoesNotAutomaticallyGrantScope() throws Exception {
        mvc.perform(get("/api/scoped"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithUserDetails("real-admin")
    void realUserDetailsPrincipalCanBeLoaded() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(content().string("real-admin"));
    }

    @Test
    void requestScopedMockIdentity() throws Exception {
        mvc.perform(get("/api/me")
                .with(user("request-user").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("request-user"));
    }

    @Test
    void actualHttpBasicCredentialSucceeds() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("real-admin", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin ok"));
    }

    @Test
    void incorrectHttpBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("real-admin", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }
}
```

Bộ test gồm **12 ca**: mặc định/đổi tên của mock, anonymous ở endpoint private/public, quyền USER/ADMIN, authority `SCOPE_docs.read», `@WithUserDetails», danh tính cấp request, và HTTP Basic credential đúng/sai. Nó đối chiếu đủ **200/401/403** theo cấu hình đã khai báo.

Mốc đáng chú ý: test `mockAdminCanOpenAdminEndpoint» dùng `fake-admin», tài khoản **không có** trong `InMemoryUserDetailsManager». Test vẫn 200 vì nhiệm vụ là kiểm tra **ủy quyền dựa trên Authentication do test cấp**. Trái lại, test `actualHttpBasicCredentialSucceeds» và `incorrectHttpBasicPasswordIsRejected» gửi credential qua HTTP Basic filter, nên có kiểm tra password thực tế của demo.

### 5.5 Cách chạy và kết quả mong đợi

Trong thư mục dự án chứa `pom.xml», yêu cầu Java 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Bốn request thủ công sau minh họa cách test ngoài annotation:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i -u real-admin:demo123 http://localhost:8080/api/admin
curl -i -u real-admin:wrong-password http://localhost:8080/api/admin
```

| Request | Status kỳ vọng | Body chính |
| --- | --- | --- |
| `GET /api/public» anonymous | 200 | `public ok» |
| `GET /api/me» anonymous | 401 | Body tùy entry point; có Basic challenge |
| `GET /api/admin» với password đúng | 200 | `admin ok» |
| `GET /api/admin» với password sai | 401 | Không được chạy controller |

`mvn test» phải chạy các test nếu nguồn và dependencies đúng; ví dụ đưa ra kết quả **kỳ vọng theo cấu hình**, không khẳng định đã chạy trong môi trường của người đọc.

## 6. @WithUserDetails: khi principal cần đến từ UserDetailsService

`@WithMockUser» sinh principal thông thường của Spring Security và **không cần username tồn tại** trong kho. Điều này có thể không phù hợp nếu code ứng dụng cần custom principal có field `tenantId», `employeeId» hoặc chỉ định type cụ thể trong `@AuthenticationPrincipal».

`@WithUserDetails» thì khác:

- Dùng `UserDetailsService» bean từ Spring Test application context để tải tài khoản theo username.
- Username **phải tồn tại** tại thời điểm thiết lập security context.
- Principal có type do `UserDetailsService» trả về, nên phù hợp kiểm thử code dùng `CustomUserDetails».
- Vẫn **không gọi password validation** chỉ vì người dùng được load bằng annotation; nó thiết lập context trực tiếp.
- Nếu nhiều bean `UserDetailsService», có thể xác định `userDetailsServiceBeanName».

Ví dụ fragment:

```java
@Test
@WithUserDetails(
    value = "real-admin",
    userDetailsServiceBeanName = "users"
)
void loadedUserUsesSelectedService() throws Exception {
    mvc.perform(get("/api/me"))
        .andExpect(status().isOk())
        .andExpect(content().string("real-admin"));
}
```

Trong dự án đầy đủ phần 5, bean `users» chính là `UserDetailsService» được khai báo; fragment này chạy được khi thêm trong class test. Khi ứng dụng có custom principal, phương thức/field trả về phải do custom `UserDetailsService» thật sự xây dựng, không được ép kiểu một `User» mặc định rồi hy vọng có các field domain.

### Khi @BeforeEach tạo fixture

Mặc định `WithSecurityContextTestExecutionListener» thiết lập danh tính tại `TestExecutionEvent.TEST_METHOD», tức **trước `@BeforeEach» của JUnit 5**. Nếu cần tạo user trong `@BeforeEach» rồi mới load bằng `@WithUserDetails», đổi thời điểm:

```java
@Test
@WithUserDetails(
    value = "fixture-user",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
void userCreatedByBeforeEachCanBeLoaded() {
    // Test dùng user mà @BeforeEach đã tạo.
}
```

Fragment cần import `org.springframework.security.test.context.support.TestExecutionEvent» và fixture thực sự trong `@BeforeEach». Với `TEST_EXECUTION», context được đặt sau `@BeforeEach», trước test method; vì vậy code `@BeforeEach» không được giả định nó đã thấy Authentication của annotation.

Cách chọn thời điểm cũng áp dụng cho `@WithMockUser» và `@WithAnonymousUser». Sau test, test listener dọn context để hạn chế rò rỉ danh tính giữa các test; không dùng static `SecurityContext» hoặc tự tạo trạng thái chia sẻ khó kiểm soát.

## 7. Khi nào cần @WithSecurityContext và principal tùy biến?

`@WithSecurityContext» giúp tạo custom annotation/`WithSecurityContextFactory» nếu cần một `Authentication» không thể biểu diễn tốt bằng `@WithMockUser» hoặc `@WithUserDetails». Ví dụ principal của ứng dụng chứa tenant ID và quyền theo tổ chức.

Ý tưởng tạo factory (fragment; `TenantPrincipal» là kiểu do dự án định nghĩa):

```java
// Custom annotation do dự án khai báo:
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@WithSecurityContext(factory = WithTenantIdentityFactory.class)
public @interface WithTenantIdentity {
    String username() default "mai";
    String tenantId() default "tenant-a";
}
```

```java
// Factory là một class riêng trong test sources.
public final class WithTenantIdentityFactory
        implements WithSecurityContextFactory<WithTenantIdentity> {

    @Override
    public SecurityContext createSecurityContext(WithTenantIdentity data) {
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        TenantPrincipal principal = new TenantPrincipal(
            data.username(), data.tenantId());
        Authentication auth = UsernamePasswordAuthenticationToken.authenticated(
            principal,
            "N/A",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
        context.setAuthentication(auth);
        return context;
    }
}
```

Đây là **hai fragment có chủ đích**, không phải hai file Java độc lập: cần import `java.lang.annotation», `java.util.List», các class Spring Security tương ứng, và hiện thực `TenantPrincipal» theo ứng dụng. Một factory đúng phải tạo **SecurityContext mới** cho mỗi lần sử dụng, không dùng lại instance toàn cục; chỉ thiết lập quyền cần thiết, không cấp thừa role để cho qua test.

Nếu chỉ cần username/role/scope, dùng `@WithMockUser» sẽ đơn giản hơn. Nếu cần principal type từ repository, cân nhắc `@WithUserDetails». Chỉ tạo custom annotation khi domain thực sự đòi hỏi thuộc tính không biểu diễn được bằng các lựa chọn có sẵn.

### Meta-annotation cho bộ quyền lặp lại

Các annotation giả lập có thể tái sử dụng:

```java
@Retention(RetentionPolicy.RUNTIME)
@WithMockUser(username = "reviewer", roles = "REVIEWER")
public @interface WithReviewer {
}
```

Đây là fragment và cần import; giúp test viết `@WithReviewer» thay vì lặp chuỗi role. Đặt tên rõ ràng, tránh để helper annotation âm thầm cấp `ROLE_ADMIN» cho mọi bài test.

## 8. RequestPostProcessor: danh tính thuộc từng request

Bên cạnh annotation đặt trên test method, Spring Security Test hỗ trợ các helper của `SecurityMockMvcRequestPostProcessors»:

| Helper của MockMvc | Ý nghĩa |
| --- | --- |
| `user("mai").roles("USER")» | Gắn mock user cho **request cụ thể** |
| `user(userDetails)» | Gắn principal từ một `UserDetails» đã được tạo |
| `anonymous()» | Gửi request dưới anonymous |
| `authentication(authentication)» | Gắn đối tượng `Authentication» có sẵn |
| `securityContext(context)» | Dùng context có sẵn cho request |
| `httpBasic("real-admin", "demo123")» | Gắn HTTP Basic header để **filter xác thực thật** kiểm tra credential |
| `csrf()» | Gắn token CSRF hợp lệ vào request test khi cần |
| `jwt()»/`oauth2Login()» | Giả lập thành phần OAuth2/Bearer phù hợp với bài test authorization |

Đối với helper `user(...)»/`authentication(...)», Spring Security MockMvc cần được tích hợp đúng để context gắn với request được dùng bởi filter chain. Với `@SpringBootTest» + `@AutoConfigureMockMvc» mặc định, ứng dụng sẽ cấu hình filter; nếu tự tạo `MockMvcBuilders», hãy dùng `.apply(springSecurity())» hoặc tích hợp `FilterChainProxy» phù hợp.

Ví dụ request-scoped:

```java
mvc.perform(get("/api/me")
        .with(user("first").roles("USER")))
    .andExpect(status().isOk())
    .andExpect(content().string("first"));

mvc.perform(get("/api/me")
        .with(user("second").roles("ADMIN")))
    .andExpect(status().isOk())
    .andExpect(content().string("second"));
```

Fragment này cho thấy **mỗi request có danh tính riêng** trong cùng một test. Không cần gắn `@WithMockUser» ở cấp method nếu đang dùng helper theo request. Để kiểm tra anonymous ngay cả khi có user mặc định trong bộ thiết lập, dùng `.with(anonymous())» khi phù hợp.

**Cảnh báo về `jwt()»:** helper tạo `Authentication» giả cho test; nó **không xác nhận tính hợp lệ của chữ ký, issuer, audience hay expiry của JWT thật**. Những trách nhiệm đó cần test riêng với decoder/filter hoạt động thật. Tương tự, `oauth2Login()» không thay thế kiểm thử redirect, authorization code hoặc token exchange thực.

### CSRF là một biến độc lập

`@WithMockUser» giải quyết **danh tính**, không tạo CSRF token. Nếu test POST/PUT/DELETE trong ứng dụng đang bật CSRF, có thể cần:

```java
mvc.perform(post("/api/action")
        .with(user("mai").roles("USER"))
        .with(csrf()))
    .andExpect(status().is2xxSuccessful());
```

Đây chỉ là **fragment cú pháp**: `/api/action» và quy tắc quyền/handler phải thực sự tồn tại thì mới kỳ vọng 2xx. Nếu CSRF token thiếu, status 403 có thể xuất hiện **trước cả** khi role được kiểm tra; không được vội kết luận `@WithMockUser» sai.

## 9. Phân biệt cấp độ kiểm thử: security context và authentication thật

| Bài kiểm thử cần chứng minh | Công cụ phù hợp | Điều chưa được chứng minh |
| --- | --- | --- |
| Controller trả principal name đúng | `@WithMockUser(username = "...")» | User đó có trong database hay không |
| `hasRole("ADMIN")» từ chối USER | `@WithMockUser(roles = "USER")» | Mật khẩu đã qua PasswordEncoder |
| `@PreAuthorize("hasAuthority('SCOPE_x')")» | `@WithMockUser(authorities = "SCOPE_x")» | Token thật có scope đúng từ issuer |
| Chưa login không được vào private route | `@WithAnonymousUser» hoặc `anonymous()» | Cơ chế OAuth2 redirect đầy đủ |
| Principal domain từ UserDetailsService | `@WithUserDetails» | User đã gửi credential hợp lệ |
| Kiểm tra HTTP Basic password đúng/sai | `httpBasic(...)» với filter/provider thật | Các phương thức đăng nhập khác |
| Kiểm tra JWT chữ ký, claims và expiry | Request có Bearer token thật + decoder/key test | Không thay bằng `jwt()» nếu kiểm tra cryptography |
| Kiểm tra end-to-end server, cookie, session | Web server test thật với HTTP client | MockMvc chạy mock servlet, không mở socket |

**Quan trọng với full HTTP test:** `@WithMockUser», `@WithUserDetails» và `@WithSecurityContext» thường thiết lập `SecurityContextHolder» trong **luồng test**. Khi `@SpringBootTest(webEnvironment = RANDOM_PORT)» gửi HTTP qua socket tới một server chạy ở luồng khác, server không tự đọc `ThreadLocal» của test. Với test end-to-end này, **hãy xác thực chính request HTTP**; đừng kỳ vọng annotation trên phương thức test đăng nhập thay cho client. MockMvc là một mô hình xử lý servlet request trong quá trình test, có tích hợp security test, vì vậy có thể dùng annotation như các test ở phần 5.

### Khi dùng @WebMvcTest

`@WebMvcTest» chỉ tải MVC slice và các bean/auto-config liên quan; nó có thể thiếu service, user store, method-security hoặc security config của ứng dụng. Nếu test không chạy được do bean thiếu hay kết quả 401/403 khác mong đợi, kiểm tra slice đã import config thích hợp chưa. Đừng tắt toàn bộ filter chỉ để làm test xanh nếu mục tiêu là kiểm tra security.

`@SpringBootTest» trong ví dụ đầy đủ tải context rộng hơn và giảm nguy cơ thiếu các quy tắc bảo mật. Khi tối ưu suite, có thể dùng slice test nhưng phải cấu hình chủ đích.

### Test reactive/WebFlux khác Servlet

Trong WebFlux, security context dùng Reactor Context; integration test có thể dùng `WebTestClient» với `SecurityMockServerConfigurers.mockUser()» hoặc mock authentication tương ứng. Khi test reactive method security, Spring Security có `ReactorContextTestExecutionListener». Không dùng `MockMvc» Servlet hoặc giả định ThreadLocal của test tự truyền qua event-loop/WebClient.

## 10. Các lỗi thường gặp và cách sửa

### Lỗi 1 — Dùng mock rồi kết luận login đã an toàn

`@WithMockUser(password = "wrong")» không kiểm tra mật khẩu. Test endpoint trả 200 chỉ chứng minh **quy tắc access với một context đã được cài sẵn**. Sửa bằng một nhóm test riêng gửi HTTP Basic/form credentials hoặc JWT thật qua filter/provider để xác minh authentication.

### Lỗi 2 — Nhầm ROLE_ADMIN và ADMIN

`@WithMockUser(roles = "ADMIN")» tạo `ROLE_ADMIN»; `@WithMockUser(authorities = "ADMIN")» thì không. Test có thể 403 vì chuỗi authority không khớp với `hasRole("ADMIN")». Ghi rõ role prefix, dùng `hasAuthority» khi kiểm tra chuỗi chính xác và không gán role rộng hơn yêu cầu.

### Lỗi 3 — Nghĩ username của mock phải tồn tại

Mock user có thể mang username không có trong database. Nếu ứng dụng thực sự cần profile tùy biến, dùng `@WithUserDetails» hoặc custom context thay vì ép `@AuthenticationPrincipal» về một class không tồn tại trong mock.

### Lỗi 4 — Test anonymous bằng context cũ

Nếu class có `@WithMockUser», một test không gắn annotation vẫn dùng mock user của class. Hãy dùng `@WithAnonymousUser» để ghi đè rõ ràng. Không phụ thuộc test nào chạy trước hoặc context từ test trước.

### Lỗi 5 — MockMvc không tích hợp Spring Security filter

Tự xây `MockMvcBuilders.standaloneSetup(controller)» mà thiếu security integration có thể khiến `@WithMockUser» không được truyền đúng tới request, hoặc các luật filter không được kiểm tra. Sử dụng `.apply(springSecurity())» với cấu hình phù hợp hoặc dùng `@AutoConfigureMockMvc» có filter.

### Lỗi 6 — Hiểu nhầm 401 và 403

Anonymous cần đăng nhập thường 401 với HTTP Basic, nhưng form login có thể trả 302. Đã authenticated nhưng thiếu quyền thường 403. 403 còn có thể do CSRF token thiếu; kiểm tra request và cấu hình trước khi sửa role.

### Lỗi 7 — Bỏ qua @EnableMethodSecurity

`@PreAuthorize» không có hiệu lực trong cấu hình chưa bật method security. Test chỉ kiểm tra `authorizeHttpRequests» rồi kết luận permission của method an toàn là chưa đủ. Ví dụ đã dùng `@EnableMethodSecurity», test `scopeAuthorityPassesMethodSecurity» và `adminRoleDoesNotAutomaticallyGrantScope» để chứng minh nhánh này.

### Lỗi 8 — Mở quyền quá rộng trong test

Một test chỉ đặt `@WithMockUser(roles = "ADMIN")» cho mọi request có thể bỏ qua lỗi quyền của USER/anonymous. Nên có ma trận **anonymous, authenticated không đủ quyền, đủ quyền**, và khi dùng scope/tenant cần thêm danh tính ngoài tenant hoặc thiếu scope.

### Lỗi 9 — Principal type khác môi trường chạy thật

`@WithMockUser» thường tạo principal `User» của Spring Security; nếu controller nhận `@AuthenticationPrincipal TenantPrincipal», phép cast/truy xuất field có thể thất bại hoặc null trong test. Dùng `@WithUserDetails» trả custom `UserDetails» hoặc `@WithSecurityContext» tạo principal đúng type.

### Lỗi 10 — Trộn annotation và request identity mơ hồ

`@WithMockUser» định danh cho test, `.with(user(...))» định danh cho request. Nếu trộn cả hai, phải nắm precedence của môi trường, default request và filter; tốt nhất **chọn một nguồn danh tính rõ ràng cho từng ca kiểm thử**. Khi muốn đổi user nhiều lần trong cùng test, dùng request post-processor một cách tường minh.

### Lỗi 11 — Đánh giá policy theo HTTP status duy nhất

Một endpoint `permitAll» có thể vẫn 200 khi test giả ADMIN, và bạn không biết anonymous có bị chặn nhầm hay không. Test cả body và nhánh status thích hợp. Với resource quan trọng, có thể xác minh service phía sau **không bị gọi** khi từ chối (dùng mock service/spy phù hợp).

### Lỗi 12 — Chạy full server và mong annotation truyền qua socket

Mock security context của test thread không tự truyền vào request của running server. Với `RANDOM_PORT»/HTTP client thật, gửi header/cookie/token hợp lệ qua client và đối chiếu filter, encoder, decoder thật. Chọn phạm vi test phù hợp trước khi kết luận “annotation không hoạt động”.

## 11. Checklist trước khi hoàn tất bộ test phân quyền

1. **Ranh giới:** đây là test authorization với mock context hay test authentication bằng credential thật? Hai mục tiêu cần ca kiểm thử riêng.
2. **Danh tính:** username, principal type, authorities và trạng thái anonymous đã mô tả rõ chưa?
3. **Role/scope:** có nhầm `ROLE_» với authority chính xác không? Có kiểm tra user có đúng *ít* quyền và đúng *đủ* quyền không?
4. **Hook bảo mật:** filter chain, method-security và `@PreAuthorize» có được bật trong test context đúng không?
5. **Dữ liệu:** `@WithUserDetails» có user thật trong `UserDetailsService» của test không? Thứ tự tạo fixture so với setup security context thế nào?
6. **HTTP semantics:** anonymous 401 hay 302 theo cấu hình; thiếu quyền 403; CSRF 403 được test riêng?
7. **Tách kết quả:** kết quả của mock identity có bị báo cáo nhầm là đã kiểm tra password, JWT signature, token expiry, session login không?
8. **Cô lập:** test có phụ thuộc thứ tự thực thi, ThreadLocal cũ hay role mặc định của class test không?
9. **Loại stack:** Servlet/MockMvc hay reactive/WebTestClient, dùng listener/mutator đúng?
10. **Kiểm tra âm:** endpoint nhạy cảm không chạy nghiệp vụ khi thiếu quyền; test chặn anonymous và role thấp luôn hiện diện.

## 12. Điều cần nhớ

- **`@WithMockUser»** thiết lập người dùng giả được xác thực, phù hợp test **authorization và logic theo principal**. Mặc định là `user» có `ROLE_USER»; role và authority có quy tắc prefix khác nhau.
- **`@WithAnonymousUser»** tái hiện anonymous rõ ràng, nhất là khi có mock user ở mức class. Hành vi HTTP 401/302 tùy cơ chế login.
- **`@WithUserDetails»** tải principal từ `UserDetailsService», hữu ích khi cần custom `UserDetails», nhưng không xác minh password của một request.
- **`@WithSecurityContext»** dành cho principal/domain authentication đặc biệt; chỉ cấp quyền cần thiết và tạo context mới cho mỗi test.
- **Request post-processors** giúp thiết lập user khác nhau theo request; riêng `httpBasic(...)» gửi credential qua filter để test authentication thật.
- **MockMvc + spring-security-test** kiểm tra security chain trong mô hình servlet request; test full HTTP server cần gửi credential thật thay vì tin test ThreadLocal.
- Muốn test vững, luôn có **anonymous, thiếu quyền, đủ quyền**, cùng ít nhất một kiểm thử đường xác thực thật của ứng dụng.

## Tài liệu tham khảo

- Spring Security — Testing Method Security (`@WithMockUser», `@WithAnonymousUser», `@WithUserDetails», `@WithSecurityContext»): https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — Spring MVC Test Integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — Running as a User in Spring MVC Test: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Spring Security — Setting up MockMvc and Spring Security: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html
- Spring Security API — `WithMockUser»: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithMockUser.html
- Spring Security API — `WithAnonymousUser»: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithAnonymousUser.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html