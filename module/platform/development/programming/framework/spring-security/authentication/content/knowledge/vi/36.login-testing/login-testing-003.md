# @WithMockUser, @WithUserDetails và @WithSecurityContext trong kiểm thử Spring Security

## 1. Mục tiêu của bài học

Khi kiểm thử ứng dụng có Spring Security, chúng ta thường cần tạo ra ba tình huống: request không đăng nhập, request của người dùng thông thường và request của người dùng có quyền/kiểu principal đặc biệt. Với JUnit 5 và Spring Security Test, ba annotation rất hữu ích là:

- **`@WithMockUser`**: tạo một user giả với username và authorities/roles chỉ định, **không cần user đó tồn tại trong database hoặc UserDetailsService**.
- **`@WithUserDetails`**: lấy một `UserDetails` thực từ `UserDetailsService` trong ApplicationContext kiểm thử rồi đưa user đó vào SecurityContext.
- **`@WithSecurityContext`**: nền tảng cho annotation tùy biến, cho phép tạo **SecurityContext/Authentication bất kỳ**, chẳng hạn custom principal chứa tenant ID, service identity hoặc một authentication type chuyên biệt.

Chúng giúp kiểm tra **authorization** và cách ứng dụng sử dụng `SecurityContext`, nhưng **không tự động thực hiện luồng login thật**. Một test được đánh dấu `@WithMockUser` rồi truy cập trang bảo vệ không chứng minh password đã được `PasswordEncoder.matches` kiểm tra, JWT signature đã được xác minh hay MFA đã thành công.

### Kết quả học tập

Sau khi hoàn thành, bạn có thể:

1. Giải thích vòng đời `SecurityContext` trong Spring Test và MockMvc.
2. Sử dụng đúng `@WithMockUser(username, roles, authorities)`.
3. Sử dụng `@WithUserDetails` để kiểm tra principal và quyền lấy từ `UserDetailsService`.
4. Tạo annotation `@WithTenantUser` dựa trên `@WithSecurityContext` cùng `WithSecurityContextFactory`.
5. Phân biệt `hasRole("ADMIN")` với `hasAuthority("ROLE_ADMIN")`, `docs:write`.
6. Kết hợp `@SpringBootTest`, `@AutoConfigureMockMvc`, `spring-security-test`, `csrf()` và `httpBasic()`.
7. Viết cả **negative tests**: 401, 403, thiếu CSRF, thiếu quyền, kiểu principal sai.
8. Phân biệt test giả lập authentication với test thực sự đi qua `AuthenticationManager`/PasswordEncoder.
9. Tránh các lỗi về setupBefore, bean naming, test slice, context leakage và claims bảo mật giả.

> **Trọng tâm:** Ba annotation là công cụ *thiết lập ngữ cảnh xác thực cho bài test*. Chúng không thay thế kiểm thử xác thực credential, session, OAuth2/OIDC, MFA hoặc các cơ chế sản xuất.

## 2. Những đối tượng chính trong Spring Security Test

Một request đã đăng nhập được biểu diễn bằng `Authentication`, được giữ trong `SecurityContext` và được truy cập thông qua `SecurityContextHolder` ở Servlet stack.

~~~text
JUnit 5 + Spring TestContext Framework
       |
       | WithSecurityContextTestExecutionListener
       | đọc annotation trên test method/class
       v
SecurityContextHolder / TestSecurityContextHolder
       |
       +--> Authentication
       |       |
       |       +--> principal: User/UserDetails/CustomPrincipal
       |       +--> authorities: ROLE_USER, docs:write...
       |       +--> authenticated: true/false
       |
       v
MockMvc tích hợp Spring Security filters
       |
       +--> SecurityFilterChain
       +--> AuthorizationManager / hasRole / hasAuthority
       +--> Controller / @PreAuthorize / service
       |
       v
Kết quả: 200, 401, 403 hoặc lỗi nghiệp vụ
~~~

Spring Security cung cấp `WithSecurityContextTestExecutionListener` để chuẩn bị `SecurityContext` trước mỗi bài test và **dọn context sau test**. Trong MockMvc, cần tích hợp Spring Security đúng cách: `@AutoConfigureMockMvc` của Spring Boot thường tự đăng ký filter chain; với MockMvc tự xây, dùng `.apply(springSecurity())`.

### 2.1. Authentication và principal có phải là một?

Không. `Authentication` chứa:
- **principal**: đại diện user/service (có thể là `User`, custom `UserDetails`, `Jwt`, `OAuth2User`, record riêng...);
- **credentials**: thông tin dùng để xác thực, tùy cơ chế; không nên được log hay đưa vào response;
- **authorities**: các `GrantedAuthority` mà authorization dùng để quyết định quyền;
- **authenticated**: cờ biểu diễn trạng thái đã xác thực của object.

Một test dùng `@WithMockUser` thường tạo `UsernamePasswordAuthenticationToken` đã authenticated với principal `org.springframework.security.core.userdetails.User`. Điều đó khác việc browser đã gửi POST login thành công.

### 2.2. Hai lớp test cần phân biệt

| Lớp kiểm thử | Chúng ta muốn biết | Công cụ phù hợp |
|---|---|---|
| **Authorization / controller/service** | User có role/scope X có được gọi endpoint Y? | `@WithMockUser`, `@WithUserDetails`, `@WithSecurityContext`, MockMvc |
| **Authentication flow** | Password/token thật có được kiểm tra, bị từ chối, tạo session đúng? | MockMvc `httpBasic()`, `formLogin()`, OIDC/JWT integration test, browser E2E |
| **Business principal** | App có lấy đúng tenant/user ID từ principal? | `@WithUserDetails` với custom UserDetails; custom `@WithSecurityContext` |
| **Infrastructure** | SecurityFilterChain/CSRF/AuthenticationProvider đang chạy đúng? | `@SpringBootTest`, `@AutoConfigureMockMvc`, integration test |

Đừng báo một test là “login bảo mật” chỉ vì `@WithMockUser` cho kết quả HTTP 200.

## 3. So sánh trực tiếp ba annotation

| Tiêu chí | `@WithMockUser` | `@WithUserDetails` | `@WithSecurityContext` |
|---|---|---|---|
| User phải tồn tại? | Không | **Có**, phải load được từ `UserDetailsService` | Không bắt buộc, tùy factory |
| Principal mặc định | Spring Security `User` | Object `UserDetails` trả về từ service | Bất kỳ object do factory tạo |
| Authentication thường gặp | `UsernamePasswordAuthenticationToken` | `UsernamePasswordAuthenticationToken` | Tùy bạn |
| Cách chỉ định quyền | `roles` hoặc `authorities` trong annotation | Từ `UserDetails.getAuthorities()` | Factory tự tạo authorities |
| Kiểm tra mapping DB/UDS? | Không | Có load test data qua UDS | Chỉ khi factory làm như vậy |
| Kiểm tra password thật? | Không | **Không** | **Không**, trừ khi factory cố ý thực thi flow |
| Hợp custom principal? | Thường không | Có, nếu UDS trả custom UserDetails | Có, linh hoạt nhất |
| Chi phí setup | Thấp | Cần ApplicationContext và UDS | Cần annotation + factory |
| Use case chính | Unit/slice authorization test | Test quy tắc dựa trên dữ liệu user đã nạp | Test tenant, principal và authentication đặc biệt |

**Quy tắc chọn nhanh:** nếu chỉ quan tâm role/quyền, chọn `@WithMockUser`; nếu ứng dụng phụ thuộc dữ liệu `UserDetailsService`, chọn `@WithUserDetails`; nếu principal/authentication có cấu trúc riêng, chọn `@WithSecurityContext`.

## 4. @WithMockUser: nhanh và độc lập với user repository

Annotation thuộc package:

~~~java
import org.springframework.security.test.context.support.WithMockUser;
~~~

Ví dụ cơ bản:

~~~java
@Test
@WithMockUser
void hasDefaultUser() {
    Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

    assertEquals("user", authentication.getName());
    assertTrue(authentication.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_USER")));
}
~~~

`@WithMockUser` không có tham số tạo mặc định:
- username: `user`;
- password trong mock user: `password` (chỉ thuộc object test; không được đối chiếu DB);
- role: `ROLE_USER`;
- authentication type: `UsernamePasswordAuthenticationToken`.

**User `user` không cần tồn tại trong database.** Đây là điểm hữu ích khi kiểm thử logic phân quyền mà không muốn khởi tạo dữ liệu account.

### 4.1. Username tùy chỉnh

~~~java
@Test
@WithMockUser(username = "alice")
void showsAlice() {
    assertEquals("alice",
        SecurityContextHolder.getContext()
            .getAuthentication().getName());
}
~~~

`value="alice"` cũng là một alias tương ứng cho username ở annotation này.

### 4.2. `roles` và `authorities` khác nhau

~~~java
@WithMockUser(username = "admin", roles = {"USER", "ADMIN"})
~~~

Tương đương authorities `ROLE_USER` và `ROLE_ADMIN`. Spring áp dụng tiền tố role mặc định `ROLE_`.

Nếu muốn quyền có tên nguyên văn, dùng:

~~~java
@WithMockUser(username = "writer", authorities = {"docs:read", "docs:write"})
~~~

Ở đây **không tự thêm** `ROLE_`. `hasAuthority("docs:write")` kiểm tra chuỗi `docs:write` chính xác; `hasRole("ADMIN")` theo thiết lập mặc định đòi `ROLE_ADMIN`.

**Không cấu hình `roles` và `authorities` tùy tiện cùng lúc** để “đủ cả hai”; hãy dùng một hình thức có chủ đích (hoặc khai báo tất cả authorities trong danh sách `authorities`).

### 4.3. Sự nhầm lẫn thường gặp

~~~java
// Role-based authorization:
.requestMatchers("/api/admin").hasRole("ADMIN")

// Test ĐÚNG với role name:
@WithMockUser(roles = "ADMIN")

// Nếu dùng authorities trực tiếp, phải đúng full string:
@WithMockUser(authorities = "ROLE_ADMIN")

// Không tương đương với ROLE_ADMIN:
@WithMockUser(authorities = "ADMIN")
~~~

Nếu test bị 403 dù “đã đặt ADMIN”, kiểm tra xem code đòi `hasRole("ADMIN")` hay `hasAuthority("ADMIN")`. Hai biểu thức có ý nghĩa chuỗi khác nhau.

### 4.4. Class level và override

Có thể đặt annotation trên class, áp dụng chung cho nhiều tests:

~~~java
@WithMockUser(username = "tester", roles = "USER")
class ProfileTests {

    @Test
    void loggedInAsTester() { }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void testAdminOverride() { }

    @Test
    @WithAnonymousUser
    void anonymousScenario() { }
}
~~~

Đây là minh họa cấu trúc class; cần JUnit/Spring Test setup và imports nếu đặt vào project riêng. Dùng `@WithAnonymousUser` để ghi đè class-level mock cho negative test. Hỗ trợ các kịch bản `@Nested` theo cơ chế annotation của Spring Test.

### 4.5. Khi nào KHÔNG nên dùng @WithMockUser?

- Controller ép kiểu `authentication.getPrincipal()` thành custom `TenantPrincipal` hoặc `CustomUserDetails`; principal `User` mặc định không đúng.
- Cần thử user được load từ repository hoặc chính sách `enabled/locked/expired` thực của `UserDetailsService`.
- Cần kiểm tra password hash, `DaoAuthenticationProvider`, form login, JWT signature, session fixation, OAuth2 callback hay WebAuthn assertion.
- Cần khẳng định browser đã trải qua MFA/passkey. Mock không chứng minh điều này.

`@WithMockUser` tạo **ngữ cảnh đã xác thực giả**, không chạy trình tự xác thực credential.

## 5. @WithUserDetails: lấy user từ UserDetailsService

Package:

~~~java
import org.springframework.security.test.context.support.WithUserDetails;
~~~

Ví dụ:

~~~java
@Test
@WithUserDetails("alice")
void usesStoredUserDetails() {
    Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();
    assertEquals("alice", authentication.getName());
}
~~~

Khác với `@WithMockUser`, annotation này yêu cầu Spring ApplicationContext cung cấp **ít nhất một bean `UserDetailsService` phù hợp**, và `loadUserByUsername("alice")` trả về user được yêu cầu.

Nếu ứng dụng có nhiều `UserDetailsService`, chỉ định tên bean:

~~~java
@Test
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "demoUsers")
void loadsFromNamedService() {
    // Principal đúng object do demoUsers trả về.
}
~~~

### 5.1. @WithUserDetails có thực sự login bằng password không?

**Không.** Test listener gọi `UserDetailsService` để lấy principal và dựng authentication đã xác thực. Nó không tự gửi request login, không gọi `PasswordEncoder.matches(raw, encoded)`, không thực thi MFA. Vì vậy nó phù hợp kiểm thử:
- custom `UserDetails` với `tenantId`, `accountId`, trạng thái profile;
- authorities được nạp từ test fixtures/repository;
- business authorization dùng `UserDetails`;
- code đọc `@AuthenticationPrincipal` hoặc `SecurityContextHolder`.

Nếu bạn muốn kiểm tra password đúng/sai, dùng **một request thật** đi qua authentication filter trong integration test (phần 11).

### 5.2. Rủi ro về fixture và bean lifecycle

- User chưa được tạo: listener có thể ném `UsernameNotFoundException` **trước khi test method chạy**; `assertThrows` bên trong method không bắt được lỗi setup này.
- Có nhiều UDS beans nhưng chưa chỉ định `userDetailsServiceBeanName`: Spring có thể không biết chọn bean nào.
- Test context chỉ có `@WebMvcTest` mà không import/mock UDS: annotation không thể load được user.
- Dữ liệu được tạo trong `@BeforeEach` có thể đến **sau** thời điểm listener mặc định load user; cần `setupBefore = TestExecutionEvent.TEST_EXECUTION` khi phù hợp.
- Nếu UDS đọc DB thật, fixture phải cách ly giữa tests, xử lý transaction và cleanup.
- Nếu cache UserDetails, cần reset/invalidate state khi tests thay đổi roles.

### 5.3. Khi user là custom UserDetails

Ví dụ domain application:

~~~java
public final class AccountUserDetails
        implements UserDetails {

    private final String username;
    private final long accountId;
    private final String tenantId;
    private final Collection<? extends GrantedAuthority> authorities;
    private final String passwordHash;

    // Constructor, getUsername/getPassword/getAuthorities,
    // isEnabled và các method cần thiết theo interface.
}
~~~

Đây là **khung thiết kế minh họa**, không phải file Java runnable độc lập (chưa có constructor/method implementations). Nếu `UserDetailsService` thực trả `AccountUserDetails`, `@WithUserDetails` sẽ mang cùng principal type và cho phép test nghiệp vụ dựa trên `accountId/tenantId`. Dữ liệu được đưa vào `SecurityContext` vẫn là **test identity**, chưa chứng minh password authentication.

## 6. @WithSecurityContext: làm chủ Authentication và principal

`@WithSecurityContext` là **meta-annotation** để tạo một annotation riêng, ví dụ `@WithTenantUser`. Nó cần:
- Một annotation có `@Retention(RUNTIME)`.
- Thuộc tính `factory=...class` trỏ tới lớp implement `WithSecurityContextFactory<AnnotationType>`.
- Factory tạo một `SecurityContext` **mới** bằng `SecurityContextHolder.createEmptyContext()`.
- Factory dựng đúng `Authentication`: principal, credentials (không cần secret thật trong mock), authorities, trạng thái authenticated.
- Trả context đã gắn authentication.

Ví dụ dùng ở test:

~~~java
@Test
@WithTenantUser(
    username = "alice",
    tenantId = "tenant-a",
    authorities = {"tenant:read"})
void verifiesTenantPrincipal() {
    // SecurityContext chứa TenantPrincipal("alice", "tenant-a")
}
~~~

Không có `@WithTenantUser` mặc định trong Spring Security. Đó là **annotation do dự án tự tạo** dựa trên `@WithSecurityContext`. Phần 9 cung cấp đầy đủ class, annotation và factory.

### 6.1. Khi nào cần factory tùy chỉnh?

- Principal từ JWT/OIDC có custom claims hoặc roles.
- `Authentication` không phải `UsernamePasswordAuthenticationToken`.
- Application cần `tenantId`, `organizationId`, `accountId`, `actorType` hoặc custom permission set.
- Một nhóm tests lặp lại cùng tổ hợp authorities/principal.
- Muốn dùng `@Autowired` trong factory để đọc fixture/test bean (Spring Security hỗ trợ factory được Spring quản lý).

**Tránh “thổi phồng” độ tin cậy:** nếu factory tự gắn `isMfaVerified=true` hoặc `JWT_AUTHENTICATED`, đó chỉ là dữ liệu giả do test tạo. Nó dùng kiểm thử policy *sau xác thực*, không chứng minh giao thức xác minh OTP/JWT thực tế an toàn.

## 7. Vòng đời thiết lập SecurityContext trong JUnit 5

Spring Security Test listener chuẩn bị context trong quá trình Spring TestContext chạy:

~~~text
beforeTestMethod (mặc định)
    |
    +--> WithSecurityContextTestExecutionListener đọc annotation
    +--> tạo Authentication và SecurityContext
    v
JUnit @BeforeEach
    v
beforeTestExecution (nếu chọn setupBefore=TEST_EXECUTION)
    |
    v
@Test method
    |
    v
@AfterEach và Spring TestContext cleanup
    |
    v
SecurityContextHolder được dọn cho test tiếp theo
~~~

### 7.1. Khi nào cần setupBefore?

Mặc định:

~~~java
@WithMockUser(setupBefore = TestExecutionEvent.TEST_METHOD)
~~~

Context đã có khi `@BeforeEach` chạy. Nếu test tạo user ở `@BeforeEach` và `@WithUserDetails` cần đọc user sau thời điểm đó, dùng:

~~~java
@WithUserDetails(
    value = "newlyCreatedUser",
    setupBefore = TestExecutionEvent.TEST_EXECUTION)
~~~

`TEST_EXECUTION` diễn ra sau `@BeforeEach`, trước test method. Tùy annotation/custom meta annotation, cơ chế `setupBefore` có thể được cung cấp từ `@WithSecurityContext`.

**Quan trọng:** `@WithMockUser` mặc định tạo context trước `@BeforeEach`; đừng cho rằng test user chỉ xuất hiện khi vào dòng đầu tiên của `@Test`.

### 7.2. Không chia sẻ SecurityContext giữa threads tùy tiện

Trong Servlet stack, `SecurityContextHolder` mặc định dùng ThreadLocal strategy. Test dùng `@Async`, `CompletableFuture`, thread pool hoặc reactive WebFlux không thể mặc định trông đợi context được propagate sang thread khác. Cần các cơ chế delegation/context propagation tương ứng hoặc `ReactorContextTestExecutionListener` với reactive security tests.

Không tạo static `SecurityContext` dùng chung cho tất cả tests; điều đó làm tests phụ thuộc thứ tự, có thể rò principal/authorities giữa các test.

## 8. Tạo dự án kiểm thử có thể chạy với Java 17 và Spring Security 6.5

Để so sánh ba annotation trong cùng một bộ kiểm thử, ta xây dựng API demo:
- `GET /api/whoami`: yêu cầu đăng nhập, trả tên và kiểu principal.
- `GET /api/admin`: yêu cầu role `ADMIN`.
- `POST /api/docs`: yêu cầu authority `docs:write` và CSRF token.
- `GET /api/tenant`: yêu cầu authority `tenant:read` **và** custom `TenantPrincipal`.

Dự án test có **một `UserDetailsService` fixture** cung cấp Alice và Bob. Test class dùng cả ba annotation và so sánh với request HTTP Basic thật.

### 8.1. Cấu trúc project

~~~text
security-annotations-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/securitytest/
    │   ├── SecurityTestDemoApplication.java
    │   ├── SecurityConfiguration.java
    │   ├── ApiController.java
    │   └── TenantPrincipal.java
    └── test/java/com/example/securitytest/
        ├── TestUsersConfiguration.java
        ├── WithTenantUser.java
        ├── WithTenantUserSecurityContextFactory.java
        └── AuthenticationAnnotationsTest.java
~~~

Mã dưới đây tương thích JDK 17+, Spring Boot 3.5.x/Spring Security 6.5.x. Các ví dụ **không kết nối Internet để xác thực**, không gọi API bên ngoài và không cần database.

### 8.2. `pom.xml`: spring-security-test là dependency thiết yếu

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>security-annotations-demo</artifactId>
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

**Phân biệt dependencies:**
- `spring-boot-starter-security` cung cấp Spring Security runtime.
- `spring-security-test` cung cấp `@WithMockUser`, `@WithUserDetails`, `@WithSecurityContext`, MockMvc postprocessors `csrf`, `httpBasic`, `user` và matchers.
- `spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Test, MockMvc và thư viện assertion phổ biến.
- Spring Boot parent/BOM quản lý version tương thích; không ép một Spring Security Test version khác với runtime.

### 8.3. Main class

File `src/main/java/com/example/securitytest/SecurityTestDemoApplication.java`:

~~~java
package com.example.securitytest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityTestDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityTestDemoApplication.class, args);
    }
}
~~~

### 8.4. SecurityFilterChain thật cho bài kiểm thử

File `src/main/java/com/example/securitytest/SecurityConfiguration.java`:

~~~java
package com.example.securitytest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .requestMatchers(
                                HttpMethod.POST, "/api/docs")
                            .hasAuthority("docs:write")
                        .requestMatchers(
                                HttpMethod.GET, "/api/tenant")
                            .hasAuthority("tenant:read")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

- `anyRequest().authenticated()` bảo vệ `GET /api/whoami`.
- `hasRole("ADMIN")` yêu cầu `ROLE_ADMIN` theo role prefix mặc định.
- `hasAuthority("docs:write")` yêu cầu đúng chuỗi đó.
- `httpBasic()` chỉ phục vụ thử **authentication thật** trong demo; production browser login nên chọn cơ chế phù hợp (session/OIDC/passkey).
- **CSRF protection vẫn bật theo mặc định**. Với POST, một authenticated test user vẫn bị từ chối nếu thiếu token CSRF hợp lệ.
- Demo không thiết kế account persistence, production authorizations hay rate limiting; không triển khai như hệ thống xác thực production.

### 8.5. Principal tùy biến chứa tenant

File `src/main/java/com/example/securitytest/TenantPrincipal.java`:

~~~java
package com.example.securitytest;

import java.security.Principal;

public record TenantPrincipal(
        String username,
        String tenantId) implements Principal {

    @Override
    public String getName() {
        return username;
    }
}
~~~

`TenantPrincipal` implement `java.security.Principal`, nên `Authentication.getName()` có thể trả `username` khi `Authentication` giữ object này làm principal. Nó không implement `UserDetails`, vì demo dùng nó làm identity sau khi test factory đã tạo authentication.

### 8.6. Controller nhận Authentication đã xác thực

File `src/main/java/com/example/securitytest/ApiController.java`:

~~~java
package com.example.securitytest;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/whoami")
    public Map<String, String> whoami(Authentication authentication) {
        return Map.of(
                "name", authentication.getName(),
                "principalType",
                authentication.getPrincipal().getClass().getSimpleName());
    }

    @GetMapping("/admin")
    public Map<String, String> admin() {
        return Map.of("result", "admin-only");
    }

    @PostMapping("/docs")
    public Map<String, String> createDocument() {
        return Map.of("result", "document-created");
    }

    @GetMapping("/tenant")
    public Map<String, String> tenant(Authentication authentication) {
        if (!(authentication.getPrincipal()
                instanceof TenantPrincipal principal)) {
            throw new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "Tenant principal required");
        }
        return Map.of(
                "name", principal.getName(),
                "tenantId", principal.tenantId());
    }
}
~~~

Hệ thống sản xuất nên kiểm tra tenant/resource ở service/repository theo ID đã xác thực. Controller demo chỉ chứng minh **quyền truy cập và kiểu principal**, không phải một implementation đầy đủ của multi-tenant authorization.

### 8.7. Test fixture thực sự có UserDetailsService

File `src/test/java/com/example/securitytest/TestUsersConfiguration.java`:

~~~java
package com.example.securitytest;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@TestConfiguration(proxyBeanMethods = false)
public class TestUsersConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean("demoUsers")
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        var alice = User.withUsername("alice")
                .password(encoder.encode("local-only-alice-password"))
                .authorities("ROLE_USER", "docs:write")
                .build();

        var bob = User.withUsername("bob")
                .password(encoder.encode("local-only-bob-password"))
                .authorities("ROLE_ADMIN", "docs:read")
                .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }
}
~~~

Đây là **dữ liệu giả trong test source**:
- Alice có `ROLE_USER`, `docs:write`.
- Bob có `ROLE_ADMIN`, `docs:read`.
- Cả hai có password hash thông qua `PasswordEncoder` để HTTP Basic tests có thể thực hiện **password verification thật**.
- `@WithUserDetails` load principal từ bean có tên `demoUsers`, nhưng **không gọi matches**.
- Class nằm dưới `src/test`, không được dùng như production identity service.

**Lý do khai báo bean name:** tránh mơ hồ khi ứng dụng có nhiều `UserDetailsService`. Test dùng `@Import(TestUsersConfiguration.class)` để nạp fixture vào ApplicationContext.

## 9. Tự tạo @WithSecurityContext với TenantPrincipal

### 9.1. Định nghĩa annotation

File `src/test/java/com/example/securitytest/WithTenantUser.java`:

~~~java
package com.example.securitytest;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.security.test.context.support.WithSecurityContext;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@WithSecurityContext(
        factory = WithTenantUserSecurityContextFactory.class)
public @interface WithTenantUser {

    String username() default "tenant-user";

    String tenantId() default "tenant-a";

    String[] authorities() default {"tenant:read"};
}
~~~

### 9.2. Factory dựng SecurityContext mới

File `src/test/java/com/example/securitytest/WithTenantUserSecurityContextFactory.java`:

~~~java
package com.example.securitytest;

import java.util.Arrays;
import java.util.List;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

public class WithTenantUserSecurityContextFactory
        implements WithSecurityContextFactory<WithTenantUser> {

    @Override
    public SecurityContext createSecurityContext(
            WithTenantUser annotation) {

        TenantPrincipal principal = new TenantPrincipal(
                annotation.username(), annotation.tenantId());

        List<GrantedAuthority> authorities =
                Arrays.stream(annotation.authorities())
                    .map(name ->
                        (GrantedAuthority) new SimpleGrantedAuthority(name))
                    .toList();

        Authentication authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                        principal, null, authorities);

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        return context;
    }
}
~~~

Những điểm cần kiểm tra:
- `WithSecurityContextFactory<WithTenantUser>` đúng generic type của annotation.
- Factory được trỏ tới bằng `@WithSecurityContext(factory=...)`; nó **không phải một AuthenticationProvider của runtime**.
- Context mới được tạo cho mỗi bài test; không tái dùng static context.
- Credentials đặt `null`; không tạo password/token bí mật giả rồi vô tình log.
- Authorities lấy từ test annotation, nên test **chỉ chứng minh authorization sau khi identity đã được thiết lập**.
- `TenantPrincipal` là object thật với `username` và `tenantId`, do đó controller có thể kiểm tra `instanceof TenantPrincipal`.

Factory có thể dùng Spring dependency injection khi cần dữ liệu fixture, nhưng test càng phụ thuộc nhiều backend/data store càng nên được phân loại là integration test; tránh factory gọi hệ thống bên ngoài.

## 10. JUnit 5 + MockMvc: kiểm thử ba annotation và login thật

File `src/test/java/com/example/securitytest/AuthenticationAnnotationsTest.java`:

~~~java
package com.example.securitytest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Import(TestUsersConfiguration.class)
class AuthenticationAnnotationsTest {

    @Autowired
    MockMvc mvc;

    @Test
    void noAuthenticationReturns401() throws Exception {
        mvc.perform(get("/api/whoami")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithAnonymousUser
    void anonymousOverrideReturns401() throws Exception {
        mvc.perform(get("/api/whoami")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser
    void defaultMockUserHasUsernameUser() throws Exception {
        mvc.perform(get("/api/whoami"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("user"))
            .andExpect(jsonPath("$.principalType").value("User"));
    }

    @Test
    @WithMockUser(username = "root", roles = "ADMIN")
    void mockAdminHasRole() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value("admin-only"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void mockOrdinaryUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "docs:write")
    void customAuthorityCanCreateDocument() throws Exception {
        mvc.perform(post("/api/docs").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value(
                    "document-created"));
    }

    @Test
    @WithMockUser(authorities = "docs:write")
    void missingCsrfIsStillRejected() throws Exception {
        mvc.perform(post("/api/docs"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithUserDetails(
            value = "alice",
            userDetailsServiceBeanName = "demoUsers")
    void userDetailsComesFromRealService() throws Exception {
        mvc.perform(get("/api/whoami"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.principalType").value("User"));

        mvc.perform(post("/api/docs").with(csrf()))
            .andExpect(status().isOk());
    }

    @Test
    @WithUserDetails(
            value = "bob",
            userDetailsServiceBeanName = "demoUsers")
    void loadedAdminPermissionsAreApplied() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isOk());
    }

    @Test
    @WithTenantUser(
            username = "alice",
            tenantId = "tenant-a",
            authorities = {"tenant:read"})
    void customSecurityContextProvidesTenantPrincipal()
            throws Exception {
        mvc.perform(get("/api/tenant"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.tenantId").value("tenant-a"));
    }

    @Test
    @WithMockUser(authorities = "tenant:read")
    void roleIsNotEnoughWithoutCustomPrincipal()
            throws Exception {
        mvc.perform(get("/api/tenant"))
            .andExpect(status().isForbidden());
    }

    @Test
    void realHttpBasicPasswordIsVerified() throws Exception {
        mvc.perform(get("/api/whoami")
                .with(httpBasic(
                    "alice", "local-only-alice-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"));
    }

    @Test
    void wrongHttpBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/whoami")
                .with(httpBasic("alice", "incorrect")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

### 10.1. Mỗi test chứng minh điều gì?

| Test | Cơ chế | Ý nghĩa |
|---|---|---|
| Không có annotation | Anonymous/no credentials | Endpoint bảo vệ trả 401 |
| `@WithAnonymousUser` | Anonymous test context | Override authenticated context khi cần |
| `@WithMockUser` mặc định | Mock context | Username/role mặc định hoạt động |
| Mock admin | `roles="ADMIN"` | `hasRole("ADMIN")` cho 200 |
| Mock USER | Thiếu admin role | `hasRole` từ chối 403 |
| Mock `docs:write` + CSRF | Authority + token | Có quyền và CSRF thì POST 200 |
| Mock `docs:write` không CSRF | Authority nhưng thiếu CSRF | POST 403, không bỏ qua filter |
| `@WithUserDetails("alice")` | UserDetailsService bean | Principal, quyền được nạp từ fixture |
| `@WithUserDetails("bob")` | Role lấy từ fixture | Bob có `ROLE_ADMIN` |
| `@WithTenantUser` | Custom factory | TenantPrincipal và tenant ID đúng |
| Mock user có authority tenant | Principal type sai | Controller từ chối 403 |
| HTTP Basic đúng password | Real filter/provider | Password hash được xác minh |
| HTTP Basic sai password | Real filter/provider | Credential sai trả 401 |

Điểm mạnh của ma trận là **đặt synthetic authentication cạnh actual credential authentication**. Nó giúp nhìn rõ một lần MockMvc trả 200 có thể đến từ annotation tạo user giả, trong khi request HTTP Basic không có annotation phải đi qua xác minh password.

### 10.2. Chạy dự án

Yêu cầu JDK 17+ và Maven:

~~~bash
mvn clean test
~~~

**Kỳ vọng:** JUnit Jupiter chạy **13 test methods**, không có failures/errors; surefire report tương ứng nằm dưới `target/surefire-reports/`. Test không cần trình duyệt, server đang chạy hoặc PostgreSQL. Thời gian và đường dẫn cache phụ thuộc môi trường Maven; không có một stdout byte-for-byte cố định cho cả lệnh `mvn test`.

Giả định ở đây là cấu hình Maven/Spring Boot 3.5.x cùng dependencies đã được tải thành công. Khi dùng phiên bản Boot/Security khác, kiểm tra Javadoc và behavior của bản đó thay vì sao chép cấu hình một cách máy móc.

### 10.3. Vì sao tests dùng @SpringBootTest?

`@SpringBootTest` khởi tạo ApplicationContext đầy đủ, trong đó có `SecurityFilterChain`, controller và test `UserDetailsService`. `@AutoConfigureMockMvc` tạo MockMvc với filters. `@Import(TestUsersConfiguration.class)` nạp fixture test.

Với `@WebMvcTest(ApiController.class)`, Spring chỉ khởi tạo **một slice**; cần import/mock những bean mà controller/security cần, và phải xác nhận filter chain không bị bỏ qua. Không đặt `@AutoConfigureMockMvc(addFilters = false)` rồi kết luận “security cho phép” từ HTTP 200: tắt filters có thể loại bỏ authorization/CSRF mà bạn muốn kiểm tra.

### 10.4. Vì sao chọn HTTP Basic làm đối chứng?

HTTP Basic dễ kích hoạt một request xác thực thật trong MockMvc:

~~~java
mvc.perform(get("/api/whoami")
        .with(httpBasic("alice", "local-only-alice-password")))
    .andExpect(status().isOk());

mvc.perform(get("/api/whoami")
        .with(httpBasic("alice", "wrong")))
    .andExpect(status().isUnauthorized());
~~~

Trong mô hình demo này, `httpBasic()` tạo Authorization header phù hợp, `BasicAuthenticationFilter` gọi authentication manager/provider, rồi `PasswordEncoder` xử lý password. Đó là **một phần quan trọng của authentication flow thật**; tuy nhiên chưa kiểm tra form login, CSRF của form, session fixation, OTP, OAuth2 hoặc WebAuthn.

Nếu ứng dụng dùng form login, có thể dùng helper `formLogin()` của `spring-security-test`, **với điều kiện cấu hình `.formLogin(...)` trong SecurityFilterChain**. Không trộn helper formLogin với một application chỉ hỗ trợ Basic rồi kỳ vọng form login tự hoạt động.

## 11. Ví dụ Java 17 độc lập: vì sao role khác authority

Chương trình sau không phụ thuộc Spring để cho thấy **chuỗi quyền** được kiểm tra. Nó không thay thế Spring AuthorizationManager nhưng giúp tránh nhầm lẫn khi đặt test annotation.

File `AuthorityNameDemo.java`:

~~~java
import java.util.Set;

public final class AuthorityNameDemo {
    static boolean hasRole(Set<String> authorities, String role) {
        return authorities.contains("ROLE_" + role);
    }

    static boolean hasAuthority(
            Set<String> authorities, String authority) {
        return authorities.contains(authority);
    }

    public static void main(String[] args) {
        Set<String> granted = Set.of(
                "ROLE_ADMIN", "docs:write");

        System.out.println("hasRole ADMIN="
                + hasRole(granted, "ADMIN"));
        System.out.println("hasAuthority ADMIN="
                + hasAuthority(granted, "ADMIN"));
        System.out.println("hasAuthority ROLE_ADMIN="
                + hasAuthority(granted, "ROLE_ADMIN"));
        System.out.println("hasAuthority docs:write="
                + hasAuthority(granted, "docs:write"));
    }
}
~~~

Lệnh:

~~~bash
javac AuthorityNameDemo.java
java AuthorityNameDemo
~~~

**Stdout chính xác:**

~~~text
hasRole ADMIN=true
hasAuthority ADMIN=false
hasAuthority ROLE_ADMIN=true
hasAuthority docs:write=true
~~~

Đoạn này **cố ý mô hình hóa role prefix mặc định** của Spring Security. Nếu ứng dụng tùy chỉnh role prefix, quy tắc thực tế có thể khác. Các tên `docs:write` là authorities do hệ thống định nghĩa, không phải một tập scope có ý nghĩa tự động được Spring gán từ phía client.

## 12. Method Security: kiểm tra @PreAuthorize với cùng annotation

Ba annotation cũng hữu ích khi test các method được bảo vệ bởi `@PreAuthorize`, không chỉ HTTP endpoints. Ví dụ một service:

~~~java
@Service
public class ReportService {
    @PreAuthorize("hasAuthority('reports:read')")
    public String readReport() {
        return "report";
    }
}
~~~

Đây là **mảnh code minh họa**, chưa phải một file Java độc lập; cần import `@Service`, `@PreAuthorize` và bật method security bằng `@EnableMethodSecurity` trên configuration.

Kiểm thử:

~~~java
@Test
@WithMockUser(authorities = "reports:read")
void canReadReport() {
    assertEquals("report", reportService.readReport());
}

@Test
@WithMockUser(roles = "USER")
void missingReportPermissionIsDenied() {
    assertThrows(AccessDeniedException.class,
            () -> reportService.readReport());
}
~~~

Lưu ý:
- Đảm bảo service được lấy **qua Spring bean/proxy**; `new ReportService()` có thể không có method security interceptor.
- `@EnableMethodSecurity` được bật ở test ApplicationContext.
- Chỉ test đúng quyền nếu annotation và proxy thực sự được áp dụng.
- `@WithMockUser` không tự tạo account trong DB; method security chỉ nhìn Authentication đã được listener dựng.
- Với quyền phụ thuộc user/tenant data thật, dùng `@WithUserDetails` hoặc custom context + fixture thích hợp.

## 13. MockMvc postprocessors so với annotation

Trong cùng một test, có thể không cần annotation class-level mà chỉ gắn identity cho **một HTTP request**:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.*;

mvc.perform(get("/api/admin").with(user("bob").roles("ADMIN")))
    .andExpect(status().isOk());
~~~

`user("bob").roles("ADMIN")` gắn identity giả vào request MockMvc cụ thể; `@WithMockUser` chuẩn bị `SecurityContext` cho test lifecycle. Cách nào phù hợp tùy muốn cấu hình nhiều requests hay chỉ một request.

### 13.1. Khi test nhiều nhân vật trong một method

~~~java
mvc.perform(get("/api/admin")
        .with(user("alice").roles("USER")))
    .andExpect(status().isForbidden());

mvc.perform(get("/api/admin")
        .with(user("bob").roles("ADMIN")))
    .andExpect(status().isOk());
~~~

Đây là cách rõ ràng khi cần hai principals trong **cùng bài test**. Không phải tạo `@WithMockUser` hai lần trên một method.

### 13.2. MockMvc tự xây cần apply(springSecurity())

~~~java
MockMvc mvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(springSecurity())
        .build();
~~~

Cần static import từ `SecurityMockMvcConfigurers.springSecurity`. Việc `apply(springSecurity())` đăng ký các security filters và test postprocessor, giúp annotation/context tương tác đúng với MockMvc. Nếu bạn dùng `@AutoConfigureMockMvc` theo Spring Boot, không cần viết lại đoạn này.

### 13.3. @WithMockUser không cấp CSRF token

Ngay cả khi test đã authenticated:

~~~java
@Test
@WithMockUser(authorities = "docs:write")
void csrfMatters() throws Exception {
    mvc.perform(post("/api/docs"))
        .andExpect(status().isForbidden());

    mvc.perform(post("/api/docs").with(csrf()))
        .andExpect(status().isOk());
}
~~~

CSRF token **không phải quyền truy cập**. Ngược lại, có `.with(csrf())` không tự tạo principal hoặc authority; nếu user thiếu quyền, request vẫn bị từ chối. Đây là hai lớp bảo vệ độc lập trong ứng dụng web session-based.

## 14. Các tình huống custom Authentication phức tạp

### 14.1. JWT Resource Server

Nếu ứng dụng thật dùng JWT access token, authentication thường là `JwtAuthenticationToken` cùng issuer/audience/scope validation. `@WithMockUser(authorities="SCOPE_orders:read")` có thể phù hợp để test rule `hasAuthority`, nhưng:
- không xác minh JWT signature;
- không kiểm tra `iss`, `aud`, `exp`, `nbf`;
- không chứng minh converter của token map scopes đúng;
- không mô phỏng chính xác custom claim/tenant logic.

Với MockMvc Resource Server, dùng `jwt()` request postprocessor để test principal/claims/authorities ở tầng web. Với xác thực JWT thật, viết integration test đi qua `JwtDecoder` được cấu hình, dùng issuer/JWK test fixture tin cậy. Hai lớp test phải được ghi tên rõ ràng.

### 14.2. OAuth2 Login / OIDC

`@WithMockUser` không làm principal thành `OAuth2User` hay `OidcUser`. Nếu controller đòi một `OidcUser`, dùng `oidcLogin()` hoặc `oauth2Login()` trong MockMvc để thiết lập OAuth2 authentication phù hợp, hoặc custom `@WithSecurityContext` khi cần principal đặc biệt.

Để kiểm thử Authorization Code Flow thật, state/nonce, ID Token signature, UserInfo và redirect callback, cần integration tests IdP/test Authorization Server. Dùng annotation mock để test phân quyền **sau login**, không đưa ra kết luận toàn bộ OIDC flow đã an toàn.

### 14.3. Pre-authentication hoặc service account

Ứng dụng có thể dùng `PreAuthenticatedAuthenticationToken` hoặc một loại Authentication riêng để lưu service identity. `@WithSecurityContext` có thể tạo loại token đó và principal phù hợp; tuy nhiên phải test **trusted proxy/mTLS/header sanitization** ở integration layer riêng để chứng minh một header giả từ Internet không được chấp nhận.

### 14.4. WebAuthn/passkey

Một mock authentication với `method="WEBAUTHN"` không chứng minh authenticator đã ký challenge hay server đã kiểm tra `origin`, RP ID và public key. Muốn kiểm tra passkey ceremony, cần WebAuthn verifier và test fixtures/E2E browser tương ứng. `@WithSecurityContext` chỉ hỗ trợ test logic **sau khi** một principal giả định đã được xác thực.

## 15. @WithUserDetails và dữ liệu test thay đổi theo thời gian

### 15.1. Test tạo user trong @BeforeEach

Nếu `@BeforeEach` seed user `alice` vào DB và `@WithUserDetails("alice")` mặc định load trước đó, setup có thể thất bại. Một cấu hình có chủ đích:

~~~java
@Test
@WithUserDetails(
    value = "alice",
    setupBefore = TestExecutionEvent.TEST_EXECUTION)
void accountLoadedAfterBeforeEach() {
    // Test data từ @BeforeEach đã được tạo.
}
~~~

Cần import `org.springframework.security.test.context.support.TestExecutionEvent`. Điều này chỉ giải quyết **thứ tự chuẩn bị SecurityContext**, không tự bảo đảm transaction isolation giữa `@BeforeEach` và test method; phụ thuộc Spring Test transaction lifecycle và dữ liệu nguồn.

### 15.2. UserDetailsService bean thật có thể trả custom principal

Nếu UDS của ứng dụng thật trả `CustomAccountUserDetails` (kế thừa/implement `UserDetails`), dùng `@WithUserDetails` giúp test:
- account ID/tenant ID lấy đúng trong principal;
- mapping `GrantedAuthority` theo domain roles;
- trạng thái account và các cờ được nạp đúng;
- các downstream services/SpEL expressions trích xuất data đúng.

**Nhưng** annotation có thể bypass checks của login provider như password, MFA hoặc việc từ chối `disabled/locked` trong quy trình xác thực thật. Hãy kiểm tra các trạng thái đó bằng authentication integration tests riêng.

### 15.3. Cẩn trọng khi thay role giữa hai test

Một test cấp `ROLE_ADMIN` cho Alice trong DB và test kế tiếp mong Alice là `ROLE_USER` có thể thất bại nếu:
- data cleanup chưa chạy;
- UDS cache chưa invalidated;
- context từ test trước bị tái sử dụng sai;
- test chạy song song trên cùng DB fixture.

Khắc phục bằng dữ liệu riêng/test transactions, reset state rõ ràng và không dùng singleton mutable authentication làm fixture.

## 16. Positive test và negative test phải đi đôi

Chỉ có `@WithMockUser(roles="ADMIN")` rồi assert 200 là chưa đủ, vì endpoint có thể đang **bị mở nhầm cho mọi user**. Cần ít nhất:

~~~text
Unauthenticated GET /api/admin → 401
USER role GET /api/admin      → 403
ADMIN role GET /api/admin     → 200
Token hợp lệ nhưng sai tenant → 403
POST thiếu CSRF              → 403 (nếu CSRF enabled)
POST đủ quyền + CSRF          → 200
~~~

### Ma trận kiểm thử khuyến nghị

| Tình huống | Annotation/công cụ | Kiểm tra |
|---|---|---|
| Anonymous vào protected endpoint | Không annotation / `@WithAnonymousUser` | 401 hoặc redirect login theo entry point |
| Mock USER truy cập ADMIN | `@WithMockUser(roles="USER")` | 403 |
| Mock ADMIN truy cập ADMIN | `@WithMockUser(roles="ADMIN")` | 200 |
| Sai `authorities` với role | `@WithMockUser(authorities="ADMIN")` | Không qua `hasRole("ADMIN")` |
| Có `docs:write` | `@WithMockUser(authorities="docs:write")` | Rule đúng |
| Có role nhưng thiếu CSRF | Mock user + POST không `csrf()` | 403 |
| Có role và CSRF | Mock user + `csrf()` | 200 |
| User thực thuộc fixture | `@WithUserDetails("alice")` | Authorities từ UDS |
| Fixture user không tồn tại | `@WithUserDetails("missing")` | Lỗi setup, không phải HTTP 401 |
| Nhiều UserDetailsServices | Annotation có `userDetailsServiceBeanName` | Chọn đúng bean |
| Custom principal đúng tenant | `@WithTenantUser` | Body và authorization đúng |
| Thiếu custom principal | `@WithMockUser(authorities="tenant:read")` | Không giả lập được TenantPrincipal |
| Password thật đúng | `httpBasic("alice", goodPassword)` | 200 qua BasicAuthenticationFilter |
| Password thật sai | `httpBasic("alice", badPassword)` | 401 |
| JWT claim giả | `jwt()`/mock context | Policy đúng với claims giả |
| JWT signature sai | Decoder integration test | Từ chối token |
| UserDetail disabled/locked | Integration test qua provider | Auth bị từ chối |
| Session hết hạn | Browser/MockMvc session test | Không còn được truy cập |
| Authentication context test isolation | JUnit test liên tiếp | Principal không rò giữa tests |
| @PreAuthorize thiếu quyền | Spring bean/proxy + annotation | AccessDeniedException |
| Factory tạo principal loại khác | `@WithSecurityContext` custom | Controller xử lý hoặc từ chối đúng |

Mã HTTP không phải lúc nào luôn giống ví dụ: khi dùng form login, unauthenticated request có thể **302 redirect** tới trang login thay vì 401; khi dùng Basic/Bearer API thường trả 401. Hãy assert status theo `AuthenticationEntryPoint` thực tế, không ép 401 cho mọi kiến trúc.

## 17. Các lỗi phổ biến và cách chẩn đoán

### Lỗi 1: "UserDetailsService not found" hoặc không tìm thấy user

Nguyên nhân:
- Test context thiếu `UserDetailsService` bean.
- Không import test configuration trong `@WebMvcTest`.
- Sai `value` username.
- Có nhiều UDS beans mà thiếu `userDetailsServiceBeanName`.
- User được seed sau thời điểm listener đọc.

Cách xử lý: kiểm tra ApplicationContext và bean name; dùng `setupBefore=TEST_EXECUTION` nếu fixture tạo trong `@BeforeEach`; không tạo một user mock khác để che lỗi đang cần kiểm thử.

### Lỗi 2: ClassCastException khi đọc custom principal

`@WithMockUser` tạo principal kiểu Spring Security `User`, không phải `CustomAccountUserDetails` hoặc `TenantPrincipal`. Chọn `@WithUserDetails` nếu UDS trả custom user, hoặc `@WithSecurityContext` factory để dựng đúng principal.

### Lỗi 3: Có `@WithMockUser` nhưng request MockMvc vẫn 401

Có thể:
- MockMvc tự build chưa `.apply(springSecurity())`.
- Security filters/listeners không được tích hợp phù hợp.
- Test tạo request khác thread/async.
- Handler của ứng dụng yêu cầu authentication type/claim khác.
- Test slice không chứa SecurityConfig hoặc security chain bị thay.

Không khắc phục bằng cách tắt filters; cần xác minh cơ chế tích hợp security test.

### Lỗi 4: Có quyền nhưng POST trả 403

Kiểm tra CSRF token với `.with(csrf())`. Nếu đã có CSRF nhưng vẫn 403, kiểm tra authorities chính xác, `@PreAuthorize`, quyền object-level, tenant policy và entry point/exception handling.

### Lỗi 5: `roles="ADMIN"` nhưng rule yêu cầu `hasAuthority("ADMIN")`

`roles="ADMIN"` tạo `ROLE_ADMIN`, trong khi `hasAuthority("ADMIN")` đòi `ADMIN`. Dùng đúng `roles` hoặc `authorities` theo hợp đồng, đừng sửa production policy chỉ để test pass nếu rule ban đầu là đúng.

### Lỗi 6: Test @WithUserDetails pass nên kết luận login pass

Sai kết luận: annotation **không xác thực password**. Bổ sung test request thật đi qua filter/provider, bao gồm password sai, account disabled/locked, session và MFA nếu có.

### Lỗi 7: Factory tạo Authentication với authorities tùy ý

Điều này là bình thường ở **authorization unit test**, nhưng không chứng minh user thật có thể được cấp authorities đó. Cần tests cho role mapping từ DB/JWT/IdP ở một lớp riêng.

### Lỗi 8: Sử dụng SecurityContextHolder static trên nhiều threads

Context mặc định thread-bound; tác vụ async có thể không nhận được context hoặc dùng context sai nếu tự propagate thiếu kiểm soát. Test xác định đúng thread/context strategy và cơ chế delegation, dọn context sau mỗi test.

### Lỗi 9: Test chạy riêng PASS nhưng cả suite FAIL

Có thể do trạng thái user fixtures, cached ApplicationContext, mutable repository, context leakage, song song hóa tests hoặc DB cleanup. Dùng fixtures độc lập và tránh thay dữ liệu global.

### Lỗi 10: Test only admin success, không có negative case

Một route mở nhầm cho mọi user vẫn làm test admin success PASS. Luôn có anonymous/user-without-authority tests.

## 18. Chiến lược kiểm thử đăng nhập đầy đủ

Thường nên chia bài test thành bốn tầng:

### Tầng A — Unit logic phân quyền

Dùng `@WithMockUser` / `@WithSecurityContext` trong Spring TestContext để kiểm tra service `@PreAuthorize`, tenant policy và các điều kiện do application định nghĩa. Không cần phát hành password/token thật.

### Tầng B — Web/security slice

Dùng MockMvc với filter chain, `@WithMockUser`, `@WithUserDetails`, `@WithAnonymousUser` và `csrf()`. Kiểm tra URL, HTTP method, status và request authorization. Mẫu demo phần 10 nằm chủ yếu ở tầng này.

### Tầng C — Authentication integration

Không sử dụng annotation giả ở test đó; gọi `httpBasic`, `formLogin` hoặc resource-server/SSO flow với fixture đã được kiểm soát, rồi kiểm tra:
- PasswordEncoder/DaoAuthenticationProvider.
- UserDetailsService/locked/disabled/expired.
- JWT issuer/audience/signature/expiry hoặc IdP callback.
- Session fixation, logout, cookie/CSRF.
- MFA/reauthentication/step-up thật.

### Tầng D — End-to-end browser và hệ thống

Test trình duyệt/IdP/gateway, HTTPS, redirect, CORS/CSRF, session cookie, passkey/WebAuthn và network trust boundaries. Không có annotation Java nào thay thế được các kiểm tra này.

**Đọc kết quả test theo đúng tầng.** Khi báo “authorization test PASS”, không dùng câu “đã kiểm thử toàn bộ cơ chế login” nếu chưa có authentication integration/E2E.

## 19. Checklist trước khi hoàn tất module

- [ ] Dependency `spring-security-test` có test scope và phù hợp Spring Security runtime.
- [ ] Có Spring TestContext/JUnit 5 và SecurityContext test listener.
- [ ] MockMvc có filter chain; nếu build thủ công đã `.apply(springSecurity())`.
- [ ] `@WithMockUser` chỉ tạo user giả; default username/role được hiểu đúng.
- [ ] Phân biệt `roles` thêm `ROLE_` với `authorities` giữ nguyên.
- [ ] `@WithUserDetails` nạp đúng `UserDetailsService` bean và username.
- [ ] Không coi `@WithUserDetails` là password authentication.
- [ ] Custom `@WithSecurityContext` có `@Retention(RUNTIME)` và factory đúng generic.
- [ ] Factory tạo context mới, principal/authentication/authorities chính xác.
- [ ] Custom principal được sử dụng đúng kiểu trong controller/service.
- [ ] Dùng `setupBefore=TEST_EXECUTION` nếu fixture tạo trong `@BeforeEach`.
- [ ] Không rò `SecurityContext` giữa tests và threads.
- [ ] Positive + negative tests gồm 401/403/200, thiếu quyền, thiếu CSRF.
- [ ] Tests password/token thật đi qua filter/provider ở integration layer riêng.
- [ ] Tests JWT/OIDC/WebAuthn thật không chỉ đặt claims/roles giả rồi coi là đã xác minh.
- [ ] Không bỏ SecurityFilterChain hoặc tắt CSRF để làm cho test pass.
- [ ] Quan sát lỗi `@WebMvcTest`/bean import thay vì dùng test config che lấp production bug.
- [ ] Không đưa password/token production vào test logs hoặc fixture.
- [ ] Có test business authorization theo tenant/object, không chỉ role-level.
- [ ] Test suite chạy được bằng `mvn clean test` và CI lưu report phục vụ review.

## 20. Ghi nhớ

- **`@WithMockUser`:** tạo identity giả nhanh để kiểm tra phân quyền. Không yêu cầu user tồn tại, không xác minh password.
- **`@WithUserDetails`:** dùng user được `UserDetailsService` nạp, phù hợp khi principal/authorities phụ thuộc dữ liệu; vẫn không chạy login/password verification.
- **`@WithSecurityContext`:** tự tạo annotation/factory cho custom principal và Authentication. Rất linh hoạt, nhưng vẫn là ngữ cảnh do test dựng.
- **`roles="ADMIN"` khác `authorities="ADMIN"`:** role mặc định có tiền tố `ROLE_`.
- **`@WithMockUser` không cấp CSRF:** POST vẫn phải tuân theo security chain.
- **Kiểm thử login thật** cần gửi credential qua cơ chế như HTTP Basic/form login hoặc tích hợp IdP/token verifier, không dùng annotation để bỏ qua bước xác thực.

Ba annotation này giúp kiểm thử **“khi đã có principal X, ứng dụng có xử lý đúng không?”**. Câu hỏi **“principal X có thật sự được xác thực đúng cách không?”** cần một nhóm kiểm thử khác.

## 21. Tài liệu tham khảo

1. [Spring Security 6.5 — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html): hướng dẫn chính thức về `@WithMockUser`, `@WithUserDetails`, `@WithSecurityContext`, custom factory và `setupBefore`.
2. [Spring Security 6.5 — MockMvc Security Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): tích hợp SecurityFilterChain và `springSecurity()`.
3. [Spring Security 6.5 — MockMvc Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html): `user()`, annotation-based request identity và custom authentication.
4. [Spring Security 6.5 — MockMvc Request PostProcessors](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/request-post-processors.html): `csrf()`, `httpBasic()`, `formLogin()`, `jwt()`, `oauth2Login()`, `oidcLogin()`.
5. [Spring Security 6.5 — @WithMockUser API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/test/context/support/WithMockUser.html): username, roles, authorities, setupBefore.
6. [Spring Security 6.5 — @WithUserDetails API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/test/context/support/WithUserDetails.html): userDetailsServiceBeanName và test listener.
7. [Spring Security 6.5 — @WithSecurityContext API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/test/context/support/WithSecurityContext.html): metadata và factory.
8. [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize` và kiểm soát quyền ở service.
9. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@AutoConfigureMockMvc`, web slices và test configuration.
10. [Spring Security 6.5 — Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html): tổng quan công cụ Spring Security Test.
