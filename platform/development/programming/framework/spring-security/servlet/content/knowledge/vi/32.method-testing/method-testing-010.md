# Phân biệt giả lập danh tính với kiểm thử AuthenticationProvider thực

> **Phạm vi:** Spring Security trên Servlet stack (Spring Boot 3.x, Spring Security 6.x, Java 17+, JUnit Jupiter, MockMvc). Bài tập trung vào kiểm thử **method security** và cơ chế **authentication**: một danh tính được đặt sẵn vào `SecurityContext` có thể giúp kiểm tra phân quyền, nhưng **không chứng minh `AuthenticationProvider` đã xác minh mật khẩu, trạng thái tài khoản, token hay nguồn danh tính thực**.

## 1. Vì sao hai kiểu kiểm thử thường bị nhầm?

Giả sử có phương thức:

```java
@PreAuthorize("hasAuthority('PAYMENT_APPROVE')")
public String approve(String paymentId) {
    return "approved:" + paymentId;
}
```

Một test viết:

```java
@Test
@WithMockUser(username = "alice", authorities = "PAYMENT_APPROVE")
void aliceCanApprove() {
    assertEquals("approved:123", paymentService.approve("123"));
}
```

Test này hữu ích: nó cho biết **method-security rule cho phép** một `Authentication` có authority `PAYMENT_APPROVE`. Nhưng **không chứng minh** user `alice` tồn tại, password của cô ấy đúng, account chưa bị khóa, LDAP bind đã thành công, JWT signature đúng hoặc MFA đã đạt yêu cầu.

Trong thực tế, bạn cần phân biệt hai câu hỏi:

1. **Authorization:** *Nếu* Spring Security đã có một principal với tập authorities xác định, người đó được gọi method nào? Đây là mục tiêu tự nhiên của `@WithMockUser`, `@WithUserDetails`, `user(...)` hoặc `jwt()` test fixtures.
2. **Authentication:** Với một credential **chưa được xác thực** (username/password, bearer token, certificate...), `AuthenticationManager`/`AuthenticationProvider` hoặc filter tương ứng có thực sự kiểm tra được credential, account status và các policy cần thiết hay không?

Hai nhóm test **bổ sung nhau**, không thay thế nhau. Một hệ thống có thể pass toàn bộ `@WithMockUser` tests mà production login vẫn lỗi hoặc để lọt tài khoản khóa. Ngược lại, provider xác thực đúng mật khẩu nhưng method security cấu hình nhầm `permitAll` vẫn có lỗ hổng phân quyền.

## 2. Bốn tầng của Spring Security cần quan sát riêng

Với web MVC, một luồng cơ bản là:

```text
HTTP request: Authorization: Basic ...
      |
      v
SecurityFilterChain / authentication filter
      |    trích xuất credential chưa xác thực
      v
AuthenticationManager (thường là ProviderManager)
      |    chọn AuthenticationProvider hỗ trợ token type
      v
AuthenticationProvider
      |    tải user / xác minh mật khẩu / kiểm tra status
      v
Authentication đã authenticated + GrantedAuthority
      |
      v
SecurityContextHolder (ngữ cảnh của request)
      |
      v
Spring MVC Controller -> Bean method-security proxy
      |    kiểm tra @PreAuthorize/@PostAuthorize
      v
Business method hoặc AccessDeniedException
```

Tách rõ vai trò:

| Thành phần | Trách nhiệm | Test phù hợp |
|---|---|---|
| `Authentication` | Mang principal, credentials, authorities và trạng thái authenticated | Assertion về principal/authorities; không tự là bằng chứng credential hợp lệ |
| `SecurityContextHolder` | Cung cấp context bảo mật cho thread/request hiện tại | `@WithMockUser` và test method-security |
| `AuthenticationManager` | Điều phối yêu cầu authentication | Gọi `authenticate(...)` với token chưa xác thực |
| `AuthenticationProvider` | Thực thi cách kiểm tra credential/identity cụ thể | Provider-level integration test với dữ liệu đúng/sai/khóa |
| HTTP authentication filter | Chuyển HTTP header/form/cookie thành `Authentication` input; xử lý success/failure | MockMvc qua `SecurityFilterChain`, không mock principal |
| `SecurityFilterChain` | Chọn filter, CSRF, session, authentication entry point và URL authorization | MockMvc với filters enabled |
| Method security interceptor | Bảo vệ lời gọi method qua proxy theo `@PreAuthorize` | Test gọi **Spring bean được inject**, không tự `new` |
| User store/IdP/LDAP/JWT decoder | Cấp dữ liệu cần xác thực | Integration/E2E test với fixture an toàn hoặc mock external system có hợp đồng rõ |

Trong Spring Security, `ProviderManager` chọn những provider có `supports(authentication.getClass())` phù hợp; một provider có thể trả Authentication đã xác thực, không xử lý (null), hoặc ném `AuthenticationException`. Thứ tự nhiều provider, cách xử lý exception và policy về parent manager phải được kiểm thử nếu hệ thống dùng nhiều cơ chế.

**Không nhầm `AccessDeniedException` với `AuthenticationException`.** Exception thứ nhất thường là user đã có identity nhưng **không đủ quyền**; loại thứ hai gắn với **không xác thực được credential hoặc trạng thái tài khoản**. Trên HTTP, 401/302/403 còn phụ thuộc filter, entry point, CSRF, anonymous/remember-me và cấu hình nên không suy đoán chỉ từ status.

## 3. So sánh nhanh các fixture và con đường kiểm thử

| Cách test | Identity đến từ đâu? | Có kiểm tra password/provider không? | Phù hợp để kiểm chứng |
|---|---|---|---|
| `@WithMockUser(username="alice", roles="ADMIN")` | Annotation tạo `SecurityContext` test | **Không** | `@PreAuthorize`, `hasRole`, authorities, logic authorization |
| `@WithUserDetails("alice")` | `UserDetailsService` tải principal trong fixture | **Không xác minh password**; có gọi service tải user | Mapping authorities từ user fixture, principal type, lookup user |
| `@WithSecurityContext` custom factory | Factory dựng principal/Authentication | Không, trừ khi chính factory được thiết kế có kiểm chứng thực (không nên dùng làm test provider mặc định) | Custom principal, tenant, claims/attributes giả lập |
| MockMvc `.with(user("alice"))` | Request post-processor tạo identity | **Không** | HTTP authorization và method security với một user cố định |
| MockMvc `.with(jwt())` | Tạo JWT authentication fixture theo helper | **Không xác minh chữ ký JWT thực** trong cấu hình thông dụng | Mapping claims/authority ở các lớp dùng authentication fixture |
| MockMvc `.with(httpBasic("alice","password"))` | Thêm HTTP Basic header vào request | **Có, nếu request đi qua Basic filter và manager/provider thật** | HTTP authentication, password/account status và 401/403 |
| `AuthenticationManager.authenticate(unauthenticatedToken)` | Credential input đưa trực tiếp tới manager | **Có**, tại provider được chọn | Quy tắc credential, encoder, account disabled/locked, provider selection |
| Browser E2E/HTTP qua container thật | Request thực qua network và hạ tầng | Có thể, tùy flow | TLS, reverse proxy, cookie, session, MFA/SSO, tích hợp toàn tuyến |

Hai ô quan trọng nhất: **`@WithMockUser` là authenticated fixture**, còn **`httpBasic(...)` chỉ gắn credential chưa được xác thực vào request**. Thứ hai thực sự đi qua provider **chỉ nếu** MockMvc có Spring Security filters và endpoint/chains sử dụng HTTP Basic provider như hệ thống đang thử.

### 3.1. Tại sao @WithMockUser có thể “đăng nhập” user không tồn tại?

`@WithMockUser` được xử lý bởi `WithSecurityContextTestExecutionListener` của Spring TestContext. Listener tạo một `SecurityContext` có `Authentication` giả lập và đặt nó trước test. Nó không kiểm tra user store.

Vì vậy:

```java
@Test
@WithMockUser(username = "nonexistent-user", roles = "ADMIN")
void authorizationRuleCanStillAllowThisMockIdentity() {
    // Nếu method chỉ yêu cầu ROLE_ADMIN, test vẫn có thể PASS.
}
```

Điều đó **không phải lỗi framework**. Mục tiêu là cô lập chính sách quyền khỏi quá trình login. Muốn xác minh username không tồn tại bị từ chối, phải dùng manager/provider hoặc HTTP filter thật với credential của username ấy.

### 3.2. @WithUserDetails cũng không phải password test

`@WithUserDetails("reader")` gọi `UserDetailsService.loadUserByUsername("reader")` để lấy fixture; sau đó listener tạo context. Nó **không gửi raw password qua `PasswordEncoder.matches(...)`**, không thực thi đầy đủ `DaoAuthenticationProvider` pre/post checks của một luồng login bình thường.

Vì vậy test `@WithUserDetails` có thể cho biết một user fixture có quyền `REPORT_READ`, nhưng không chứng minh password đúng, user khóa bị chặn khi login hoặc credential đã hết hạn được xử lý.

## 4. Tín hiệu xác thực thực: raw credential phải đi qua provider

Trong mô hình username/password, input chưa xác thực thường là:

```java
Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "reader", "reader-password");
```

Đoạn code này chỉ tạo token input, **chưa xác thực**. Hãy dùng:

```java
Authentication result = authenticationManager.authenticate(request);
```

Khi manager có `DaoAuthenticationProvider` phù hợp, provider thường:

1. Tìm `UserDetails` qua `UserDetailsService`.
2. Kiểm tra account status như disabled, locked, expired theo quy tắc của provider.
3. Dùng `PasswordEncoder.matches(rawPassword, storedEncodedPassword)` để xác minh.
4. Tạo `Authentication` được xác thực với authorities từ user store nếu thành công.
5. Ném `AuthenticationException` phù hợp khi không hợp lệ. Nhiều provider cố ý ẩn sự khác biệt giữa unknown username và wrong password để giảm enumeration.

**Không đặt token đã authenticated bằng tay** rồi khẳng định provider được gọi. Cũng không đặt `SecurityContextHolder.getContext().setAuthentication(...)` trong production từ dữ liệu client chưa được kiểm chứng: đó là bỏ qua ranh giới xác thực.

Sau success, `ProviderManager` có thể xóa credentials khỏi Authentication kết quả để giảm rò rỉ. Vì thế test nên khẳng định **`result.isAuthenticated()`**, principal và authorities, không giả định raw password vẫn nằm trong `result.getCredentials()`.

### 4.1. Provider-level test không đại diện toàn bộ HTTP

Gọi `authenticationManager.authenticate(...)` trực tiếp giúp đo hành vi xác thực lõi, nhưng **không kiểm thử** Basic header parsing, filter chain, security context persistence, session, CSRF, authentication entry point hoặc cookie. Để khẳng định API được bảo vệ đúng, thêm test HTTP MockMvc.

Ngược lại, MockMvc test dùng `@WithMockUser` có thể đi qua authorization filter và method proxy nhưng **không đi qua quy trình password authentication**. Chọn test dựa trên câu hỏi cần kiểm chứng, không dựa trên việc test đó ngắn hay dài.

## 5. Mô hình kiểm thử theo ba lớp

Một chiến lược có sức chứng minh tốt thường gồm:

**Lớp A — Method authorization:** tạo identity fixture bằng `@WithMockUser`, gọi Spring bean được proxy, khẳng định user có/không có authority. Rất nhanh, lỗi dễ khoanh vùng.

**Lớp B — Provider authentication:** gửi input chưa xác thực vào `AuthenticationManager`, khẳng định đúng password thành công, password sai/username lạ/disabled/locked bị từ chối, mapping authorities chính xác. Không cần network.

**Lớp C — MVC security integration:** gửi request MockMvc qua filter chain với credential thực (ví dụ `httpBasic(...)`); kiểm tra 401 thiếu/sai credential, 403 user hợp lệ thiếu quyền, 200 user có quyền, 403 thiếu CSRF trên POST, 200 đúng credential + quyền + CSRF.

```text
Method test:
 @WithMockUser → SecurityContext → method proxy → authorize

Provider test:
 unverified username/password → AuthenticationManager
                             → DaoAuthenticationProvider
                             → UserDetailsService + PasswordEncoder

MVC integration:
 httpBasic(...) → SecurityFilterChain → AuthenticationManager
                → SecurityContext → Controller
                → method proxy → authorize
```

Ba lớp này phát hiện ba nhóm lỗi khác nhau. Nếu chỉ test Lớp A, sai cấu hình `PasswordEncoder` và tài khoản disabled không bị phát hiện. Nếu chỉ test Lớp B, code thiếu `@EnableMethodSecurity` hoặc gọi service bằng `new` có thể không bị phát hiện. Nếu chỉ test Lớp C với một account admin, rule cho user thiếu quyền có thể không được kiểm thử đầy đủ.

## 6. Dự án Spring Boot 3.3.x + Java 17: mã minh họa chạy được

Mục tiêu là có một dự án Servlet nhỏ với **provider thật** và **method-security proxy thật** để đối chiếu các loại test. Nó dùng `InMemoryUserDetailsManager` làm kho tài khoản **trong bộ nhớ dành riêng cho học tập**, không gọi cơ sở dữ liệu hay IdP production.

### 6.1. Gradle

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Cấu trúc tệp:

```text
src/
  main/java/demo/authcheck/
    AuthCheckApplication.java
    SecurityConfig.java
    ApprovalService.java
    ApprovalController.java
  test/java/demo/authcheck/
    MethodAuthorizationTest.java
    AuthenticationManagerTest.java
    HttpAuthenticationIntegrationTest.java
```

Các lớp dùng đúng package `demo.authcheck`; tạo dự án Gradle với wrapper tương ứng. Tất cả chuỗi mật khẩu bên dưới là **test fixture**, không được dùng trong môi trường sản xuất.

### 6.2. Entry point

`src/main/java/demo/authcheck/AuthCheckApplication.java`:

```java
package demo.authcheck;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthCheckApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthCheckApplication.class, args);
    }
}
```

### 6.3. Cấu hình Security và AuthenticationManager thật

`src/main/java/demo/authcheck/SecurityConfig.java`:

```java
package demo.authcheck;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-local-pass"))
            .authorities("REPORT_READ")
            .build();

        UserDetails approver = User.withUsername("approver")
            .password(encoder.encode("approver-local-pass"))
            .authorities("PAYMENT_APPROVE")
            .build();

        UserDetails blocked = User.withUsername("blocked")
            .password(encoder.encode("blocked-local-pass"))
            .authorities("PAYMENT_APPROVE")
            .disabled(true)
            .build();

        return new InMemoryUserDetailsManager(reader, approver, blocked);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http,
                                    AuthenticationManager manager)
            throws Exception {
        return http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/payments/*/approve")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

**Điểm mấu chốt:**

- `UserDetailsService` lưu **BCrypt hash**; raw password chỉ có trong fixture khi chạy test. `DaoAuthenticationProvider` kiểm tra password qua encoder.
- User `blocked` có mật khẩu đúng nhưng `disabled(true)`. Provider phải **từ chối** chứ không cho phép vì password khớp.
- `AuthenticationManager` là bean `ProviderManager` có một `DaoAuthenticationProvider`. Cùng manager được đưa vào `HttpSecurity`, giúp direct provider test và HTTP Basic integration test kiểm tra cùng cấu hình.
- Rule URL chỉ yêu cầu `authenticated()` đối với hai endpoint. **Quyền cụ thể** được kiểm ở service với `@PreAuthorize`. Vì vậy test có thể phát hiện sai lệch “login hợp lệ” nhưng “không đủ authority”.
- `@EnableMethodSecurity` bật kiểm tra `@PreAuthorize`. Không tự `new ApprovalService()` để test security vì sẽ bỏ qua Spring proxy.
- CSRF giữ mặc định; POST cần CSRF token khi test MockMvc. Không tắt CSRF chỉ để làm POST demo chạy.

Cấu hình này là baseline chuyên dùng cho ví dụ. Ứng dụng thật có nhiều provider/chain, IdP, password migration hoặc user store riêng cần test đúng wiring và failure mode của nó.

### 6.4. Service có hai quyền độc lập

`src/main/java/demo/authcheck/ApprovalService.java`:

```java
package demo.authcheck;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ApprovalService {
    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String readReport() {
        return "report-for-test";
    }

    @PreAuthorize("hasAuthority('PAYMENT_APPROVE')")
    public String approve(String paymentId) {
        return "approved:" + paymentId;
    }
}
```

Không có giao dịch hoặc thay đổi dữ liệu thật trong ví dụ. Nó chủ ý trả chuỗi cố định để tập trung vào security rule thay vì side effect. Trong hệ thống sản xuất, ngay cả user có `PAYMENT_APPROVE` cũng cần kiểm tra **quyền trên tài nguyên cụ thể** như tổ chức, khoản tiền, trạng thái giao dịch và người sở hữu.

### 6.5. Controller Servlet/MVC

`src/main/java/demo/authcheck/ApprovalController.java`:

```java
package demo.authcheck;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApprovalController {
    private final ApprovalService service;

    public ApprovalController(ApprovalService service) {
        this.service = service;
    }

    @GetMapping(value = "/api/reports",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String report() {
        return service.readReport();
    }

    @PostMapping(value = "/api/payments/{id}/approve",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public String approve(@PathVariable String id) {
        return service.approve(id);
    }
}
```

Tại đây, request `GET /api/reports` và `POST /api/payments/123/approve` đi vào security filter chain trước controller; service được **inject từ Spring** nên `@PreAuthorize` có hiệu lực. API trả plain text theo mục tiêu học tập; ứng dụng thật cần object response, audit và kiểm tra lỗi nghiệp vụ phù hợp.

## 7. Test A: giả lập identity để kiểm tra method security

File `src/test/java/demo/authcheck/MethodAuthorizationTest.java`:

```java
package demo.authcheck;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class MethodAuthorizationTest {
    @Autowired
    ApprovalService service;

    @Test
    @WithMockUser(username = "ghost", authorities = "PAYMENT_APPROVE")
    void nonexistentMockIdentityCanPassAuthorizationRule() {
        // ghost không tồn tại trong UserDetailsService.
        // Test chỉ hỏi: authority có đủ để gọi method không?
        assertEquals("approved:123", service.approve("123"));
    }

    @Test
    @WithMockUser(authorities = "REPORT_READ")
    void mockReaderCanReadReport() {
        assertEquals("report-for-test", service.readReport());
    }

    @Test
    @WithMockUser(authorities = "REPORT_READ")
    void mockReaderCannotApprove() {
        assertThrows(AccessDeniedException.class,
                () -> service.approve("123"));
    }

    @Test
    @WithUserDetails("reader")
    void userDetailsFixtureCarriesReportPermission() {
        assertEquals("report-for-test", service.readReport());
    }

    @Test
    @WithUserDetails("reader")
    void userDetailsFixtureLacksApprovalPermission() {
        assertThrows(AccessDeniedException.class,
                () -> service.approve("123"));
    }
}
```

**Điều test chứng minh:** method-security proxy nhận context và thực thi authority checks đúng. User `ghost` không tồn tại nhưng fixture được cho quyền, do đó method approve được phép: đây chính là minh chứng **mock auth không phải authentication-provider test**.

**Điều test không chứng minh:** password `reader-local-pass` đúng, account `reader` chưa bị disabled theo provider, Basic filter đã parse header đúng, session/TLS/cookie an toàn hoặc database/LDAP thật hoạt động.

`@WithUserDetails("reader")` lấy user từ fixture, song không chạy `PasswordEncoder.matches`; muốn phát hiện account disabled bị chặn ở provider, dùng test B.

## 8. Test B: AuthenticationManager và DaoAuthenticationProvider thực

File `src/test/java/demo/authcheck/AuthenticationManagerTest.java`:

```java
package demo.authcheck;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class AuthenticationManagerTest {
    @Autowired
    AuthenticationManager manager;

    @Autowired
    UserDetailsService users;

    @Autowired
    PasswordEncoder encoder;

    @Test
    void storedPasswordIsEncodedAndMatchesExpectedRawPassword() {
        String stored = users.loadUserByUsername("reader").getPassword();

        assertFalse("reader-local-pass".equals(stored));
        assertTrue(encoder.matches("reader-local-pass", stored));
    }

    @Test
    void correctPasswordIsActuallyAuthenticatedByProvider() {
        Authentication input =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "reader", "reader-local-pass");
        assertFalse(input.isAuthenticated());

        Authentication result = manager.authenticate(input);

        assertTrue(result.isAuthenticated());
        assertTrue(result.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("REPORT_READ")));
    }

    @Test
    void wrongPasswordIsRejected() {
        assertThrows(BadCredentialsException.class,
            () -> manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "reader", "wrong-password")));
    }

    @Test
    void nonexistentAccountIsRejected() {
        assertThrows(BadCredentialsException.class,
            () -> manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "ghost", "any-password")));
    }

    @Test
    void disabledAccountIsRejectedEvenWhenPasswordMatches() {
        assertThrows(DisabledException.class,
            () -> manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "blocked", "blocked-local-pass")));
    }
}
```

Bây giờ mỗi lần `authenticate(...)` được gọi, input là **unauthenticated token** đi qua `ProviderManager` và `DaoAuthenticationProvider` đã cấu hình:

- Đúng password → authenticated result có authority từ `UserDetailsService`.
- Sai password → `BadCredentialsException`.
- User không tồn tại → `BadCredentialsException` trong cấu hình provider thông dụng; việc che nguyên nhân giúp giảm user enumeration.
- Account disabled → `DisabledException` ngay cả khi password đúng.

Đây là lớp test **thực sự có bằng chứng provider đã được thực thi**, nhưng vẫn chưa chứng minh Servlet filter, error handler, HTTP status, CSRF và cookie. Nếu dùng LDAP, OAuth2, X.509 hay custom provider, đổi token type, provider và fixture cho đúng protocol; không sử dụng `UsernamePasswordAuthenticationToken` để thay thế việc xác minh JWT.

### 8.1. Trường hợp provider có cache hoặc nhiều nguồn user

Nếu provider cache `UserDetails`, cơ chế khóa user/đổi password có thể không được phản ánh ngay. Một bộ test tốt còn kiểm tra password rotation, disabled/locked sau cache invalidation và nhiều providers có thể cùng `supports(...)` một token class. Cần phân biệt provider trả `null` (không xử lý) với provider ném exception và chính sách fallback/parent manager.

Trong hệ thống multi-provider, đừng chỉ assert “có authenticated result”; hãy kiểm tra **provider/issuer đáng tin nào đã xác thực** và principal/authority có đúng nguồn. Không cấu hình một provider dễ dãi làm đường fallback khi provider chính báo lỗi.

## 9. Test C: MockMvc với credential thực đi qua HTTP Basic filter

File `src/test/java/demo/authcheck/HttpAuthenticationIntegrationTest.java`:

```java
package demo.authcheck;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpAuthenticationIntegrationTest {
    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCallerGets401ForProtectedReport() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "ghost", authorities = "REPORT_READ")
    void mockIdentityCanReadEvenWithoutRealAccount() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isOk())
            .andExpect(content().string("report-for-test"));
    }

    @Test
    void httpBasicWithValidCredentialRunsRealProvider() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("reader", "reader-local-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("report-for-test"));
    }

    @Test
    void badPasswordFailsBeforeController() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("reader", "bad-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownUserFailsBeforeController() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("ghost", "any-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void disabledUserCannotUseCorrectPassword() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("blocked", "blocked-local-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedReaderWithoutApprovalAuthorityGets403()
            throws Exception {
        mvc.perform(post("/api/payments/123/approve")
                .with(httpBasic("reader", "reader-local-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void validApproverStillNeedsCsrfTokenOnPost()
            throws Exception {
        mvc.perform(post("/api/payments/123/approve")
                .with(httpBasic("approver", "approver-local-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validApproverWithCsrfCanApprove()
            throws Exception {
        mvc.perform(post("/api/payments/123/approve")
                .with(httpBasic("approver", "approver-local-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("approved:123"));
    }

    @Test
    void approverWithoutReportAuthorityCannotReadReport()
            throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("approver", "approver-local-pass")))
            .andExpect(status().isForbidden());
    }
}
```

**Đọc đúng kết quả:**

- `httpBasic(...)` là request post-processor tạo header `Authorization: Basic ...`. Nó **không tự authenticate**. Vì MockMvc bật Spring Security filter chain, `BasicAuthenticationFilter` đọc credential và chuyển qua **manager/provider thật**.
- `@WithMockUser("ghost")` giúp test rule nhưng **bypass việc kiểm tra sự tồn tại tài khoản**; ca `ghost` có thể 200 nếu có authority giả lập.
- User `reader` được provider xác thực thành công khi password đúng, nhưng vẫn bị `@PreAuthorize("hasAuthority('PAYMENT_APPROVE')")` từ chối đối với approve.
- User `approver` có quyền approve vẫn bị CSRF filter chặn trên POST thiếu token. Cần `.with(csrf())` để kiểm tra nhánh **authorization**, không được lấy một 403 do CSRF làm bằng chứng rule phân quyền đúng.
- 401 ở các ca wrong/disabled là HTTP translation của lỗi authentication qua Basic entry point. Trong test B, chúng thể hiện bằng `BadCredentialsException`/`DisabledException`; test A không kiểm tra các ngoại lệ này.

Để test HTTP Basic filter đúng, tránh `@AutoConfigureMockMvc(addFilters=false)`, `MockMvcBuilders.standaloneSetup(...)` không có Spring Security hoặc controller unit test bằng Mockito thuần. Các cách đó có mục đích khác và không đại diện authentication pipeline.

## 10. Chạy test, đối chiếu lỗi và sự khác biệt của từng lớp

Trong dự án Gradle có wrapper và Java 17:

```bash
./gradlew test
```

Chạy từng lớp:

```bash
./gradlew test --tests demo.authcheck.MethodAuthorizationTest
./gradlew test --tests demo.authcheck.AuthenticationManagerTest
./gradlew test --tests demo.authcheck.HttpAuthenticationIntegrationTest
```

Đây là lệnh kiểm thử; output chi tiết của Gradle phụ thuộc version wrapper, cache, JDK và cấu hình logging nên không khẳng định từng dòng console luôn giống nhau. Những test **kỳ vọng 401, 403 hoặc exception** vẫn là **PASS** khi hệ thống trả đúng trạng thái.

Nếu gặp lỗi, phân loại trước khi sửa:

| Hiện tượng | Nhóm nguyên nhân cần kiểm tra | Không nên kết luận |
|---|---|---|
| Method test cho phép tất cả mọi người | `@EnableMethodSecurity` thiếu, bean không qua proxy, annotation sai | Không đổ lỗi cho `@WithMockUser` ngay |
| `@WithUserDetails` lỗi trước khi chạy `@Test` | Không tìm thấy username hoặc `UserDetailsService` bean | Không suy ra mật khẩu không đúng |
| Direct manager test password sai nhưng thành công | Provider/encoder/wiring sai, provider fallback, fixture bất thường | Không chấp nhận vì MockMvc `@WithMockUser` pass |
| HTTP Basic đúng password nhận 401 | Filter chain không bật Basic, provider không được chọn, encoder khác | Không sửa thành mock principal để che lỗi |
| HTTP Basic sai password nhận 200 | Security filter bị bỏ qua, fallback provider, context được tạo sẵn | Đây là tình huống cần chặn release |
| POST của user đủ quyền nhận 403 | Thiếu CSRF, role sai, method security deny | Không kết luận ngay chỉ từ status |
| Mock principal “ghost” được approve | Đây là đặc trưng fixture authority | Không coi là chứng minh user ghost đăng nhập được thực tế |
| Token JWT test bằng `jwt()` pass | Fixture token được chèn theo helper | Không coi là bằng chứng JWK/signature/audience đúng |

### 10.1. Vì sao không gọi test provider là “unit test thuần” một cách máy móc?

Direct `AuthenticationManager` test trong demo dùng **ApplicationContext thật** và `InMemoryUserDetailsManager`, nên là một **integration test nhẹ trong phạm vi ứng dụng**. Unit test thuần của custom `AuthenticationProvider` có thể mock những dependency của provider để cô lập thuật toán, nhưng nó sẽ không chứng minh encoder/user store/bean wiring đã phối hợp đúng.

Phân loại theo **thành phần thực sự chạy**, không chỉ theo tên file hoặc annotation `@SpringBootTest`.

### 10.2. Chú ý lỗi do @WithMockUser kế thừa giữa test

Annotation có thể nằm ở class hoặc method. Nếu một test provider vô tình cũng gắn `@WithMockUser`, HTTP request có thể nhận security context giả đã được xác thực, khiến test password sai không còn đi qua logic như bạn mong đợi. Do đó các lớp `AuthenticationManagerTest` và `HttpAuthenticationIntegrationTest` trong demo **không gắn `@WithMockUser` ở class level**; chỉ một testcase cố ý dùng nó để so sánh.

Với các test có request post-processor `user(...)`, `jwt()` hoặc `oauth2Login()`, cũng tránh dùng những fixture đó trong ca đang muốn test filter/provider thật. Viết tên test rõ “mock identity” hay “real credential” và luôn có một ca negative.

## 11. Phân biệt trong hệ thống dùng JWT, OIDC, LDAP, MFA hoặc certificate

Mặc dù ví dụ dùng `DaoAuthenticationProvider`, nguyên tắc vẫn áp dụng khi cơ chế authentication thay đổi.

### 11.1. JWT resource server

`jwt()` của `spring-security-test` thường cung cấp `JwtAuthenticationToken` fixture với claims/authorities tùy chỉnh; điều này hữu ích khi test `@PreAuthorize` hoặc authorization policies dựa trên scopes.

Nhưng fixture đó **không chứng minh** `JwtDecoder` đã xác minh chữ ký, issuer, audience, `exp`, algorithm allowlist hoặc JWK rotation. Để kiểm chứng token validation, phải gửi một bearer token thật qua filter trong môi trường test và dùng decoder/test keys theo hợp đồng, hoặc test riêng `JwtDecoder`/authentication provider được cấu hình thực tế. Test cả token sai chữ ký, issuer lạ, sai audience, expired và missing required scopes.

### 11.2. OIDC/SAML và SSO

`oauth2Login()` hoặc các helper tạo principal trong test có thể bypass quá trình redirect, authorization code exchange, ID token validation, SAML assertion signature và account linking. SSO integration test cần IdP test environment/contract hoặc module validation cụ thể; kiểm tra `state`, `nonce`, redirect URI, issuer/audience và certificate/key rotation. Không thử bằng credential thật của người dùng production.

### 11.3. LDAP và account status

`@WithUserDetails` có thể tải một `UserDetails` từ directory adapter/fixture nhưng **không bind LDAP bằng password người dùng**. Muốn chứng minh LDAP auth, cần provider thật cùng directory test container hoặc môi trường tích hợp được cấp phép, TLS chính xác, user/group fixtures, wrong password, disabled account và downtime. Không lấy user lookup pass làm bằng chứng bind authentication pass.

### 11.4. X.509 và pre-auth

Tự tạo `Authentication` chứa tên trông giống Subject DN không chứng minh client certificate đã được xác thực ở TLS endpoint. Cần test mTLS/PKI tại container/proxy phù hợp, chứng thư hợp lệ/hết hạn/bị thu hồi, mapping SAN/subject và bypass đường upstream. Header client tự khai không phải chứng cứ xác thực.

### 11.5. MFA và step-up

`@WithMockUser(roles="ADMIN")` không chứng minh có hai factor độc lập hoặc user vừa thực hiện step-up. Nếu endpoint yêu cầu MFA, test policy với fixture factor-state đúng/sai **và** test luồng authentication thật tạo ra factor state theo hợp đồng. Không chỉ gán authority như `MFA_VERIFIED` rồi coi như đã test TOTP/WebAuthn/IdP.

## 12. Thiết kế test matrix cho ứng dụng thật

| Câu hỏi bảo mật | Cách test chính | Điều kiện PASS |
|---|---|---|
| Method yêu cầu `REPORT_READ` có chặn authority khác? | `@WithMockUser` gọi injected bean | Bị `AccessDeniedException` nếu thiếu authority |
| Mapper tạo đúng authorities từ user store? | `@WithUserDetails` | Principal/authorities từ fixture đúng |
| Password đúng hoạt động? | `AuthenticationManager.authenticate(...)` | Provider trả authenticated result |
| Password sai hoặc user lạ? | Provider direct + HTTP Basic filter | Exception tương ứng và HTTP 401 |
| Tài khoản disabled/locked? | Provider direct + HTTP integration | Không xác thực dù password đúng |
| HTTP filter có thực sự gọi manager? | MockMvc `httpBasic(...)`/`formLogin()` | Valid 200 và invalid 401 theo config |
| User có login nhưng thiếu quyền nghiệp vụ? | HTTP Basic valid + method-security | 403 |
| POST thiếu CSRF? | MockMvc thiếu `with(csrf())` | 403 trước thao tác |
| POST có quyền và CSRF? | MockMvc credential hợp lệ + `with(csrf())` | 200 và nghiệp vụ đúng |
| Method security proxy có hoạt động? | Inject service Spring, `@EnableMethodSecurity` | Ca deny không bị bypass |
| JWT validation thực? | Signed/invalid JWT qua decoder/filter | Token sai chữ ký/issuer/audience bị từ chối |
| SSO flow thực? | IdP integration/contract test | Redirect, state/nonce, token/assertion checks đúng |
| MFA step-up? | Policy tests + flow factor thực | User chưa đạt factor không thể thao tác nhạy cảm |
| Đổi quyền trong user store? | Provider refresh/session lifecycle | Quyền không bị giữ quá SLA |
| Multiple providers? | Direct + filter tests với type/failure khác nhau | Không fallback sang provider dễ dãi |
| Logout/session? | MVC integration/E2E | Current session invalidation đúng, không tưởng nhầm token bị revoke |

### 12.1. Mẫu phân bố test thực dụng

Không cần mọi test đều khởi động browser, directory hoặc IdP. Với một dự án thông thường:

- Nhiều test method-security nhỏ bằng `@WithMockUser` cho ma trận allow/deny theo role, tenant và quyền tài nguyên.
- Một nhóm provider integration với dữ liệu được kiểm soát để xác minh password encoder, account flags, identity lookup, provider selection và các lỗi credential.
- Một nhóm MVC filter integration cho entry point, valid/invalid credential, CSRF, session, exception translation và mapping URL.
- Một số ít E2E cho TLS/proxy, IdP, cookie/redirect, refresh/revocation và nhánh recovery quan trọng.

Đặt test fixtures và secret riêng biệt; không đưa password/token production vào repository hoặc log. Những luồng dùng database nên chạy với transaction cleanup/fixture riêng; những luồng dùng cache phải kiểm tra invalidation để test không vô tình pass với user state cũ.

## 13. Lỗi phổ biến và nguyên nhân sâu xa

**1. “@WithMockUser PASS nghĩa là login an toàn.”** Sai: nó chỉ đặt `Authentication` vào `SecurityContext`. Phải có provider test và filter integration riêng.

**2. “@WithUserDetails đã gọi UserDetailsService nên password được kiểm tra.”** Sai: user lookup không tương đương `PasswordEncoder.matches` hoặc account status check của provider.

**3. “httpBasic(...) tự authenticate.”** Sai: helper chỉ tạo header; filter và manager/provider của ứng dụng mới xử lý credential. Nếu filter bị disable, test không còn chứng minh điều cần thiết.

**4. “403 luôn là thiếu quyền.”** Sai: CSRF cũng thường trả 403; cần thêm CSRF hợp lệ vào ca test authorization để phân biệt.

**5. “200 trên request mock là một người dùng thật đã login.”** Sai: principal có thể được tạo từ annotation hoặc post-processor, kể cả username không tồn tại.

**6. “Đủ quyền là đủ bảo mật.”** Sai: user có quyền cần được xác thực bằng cơ chế tin cậy; sau đó còn kiểm tra quyền trên object/tenant và các điều kiện nghiệp vụ.

**7. “Tự new service là test method security.”** Sai: `@PreAuthorize` có thể được triển khai qua proxy; gọi object mới bên ngoài container không có advice bảo mật.

**8. “Provider bị lỗi thì thử provider kế tiếp, miễn pass.”** Nguy hiểm nếu fallback yếu hơn. Phải xem policy chọn provider, loại token, nguồn issuer và cách xử lý failure.

**9. “Test JWT bằng jwt() nghĩa là đã test signature.”** Không. Phải có test decoder/filter với signed token và các trường hợp sai chữ ký, issuer, audience, expiry.

**10. “Tài khoản disabled nhưng mock role ADMIN vẫn pass, vậy framework lỗi.”** Không: mock không thực thi account status. Provider direct phải từ chối disabled account; endpoint thật phải chặn tương ứng.

**11. “Đã gọi AuthenticationManager thì session, CSRF và HTTP status cũng được test.”** Sai: direct manager không bao phủ Servlet filter chain, entry point, logout, session hoặc CSRF.

**12. “Đã có test integration nên không cần negative cases.”** Sai: cần wrong password, unknown user, disabled, thiếu quyền và thiếu CSRF để phát hiện bypass.

## 14. Checklist nghiệm thu

- [ ] Đã xác định rõ test nào chỉ mock `Authentication` và test nào chạy `AuthenticationManager`/`AuthenticationProvider` thật.
- [ ] Đã kiểm tra dependency `spring-security-test` cùng phiên bản với Spring Security.
- [ ] Method-security tests có `@EnableMethodSecurity` và gọi Spring bean đã được proxy.
- [ ] `@WithMockUser`/`@WithUserDetails` chỉ dùng để chứng minh authorization/fixture, không khẳng định password validity.
- [ ] Provider tests bắt đầu bằng `Authentication` chưa xác thực; kiểm tra correct/wrong password, unknown/disabled/locked account và authority mapping.
- [ ] MockMvc có Spring Security filters; kiểm tra credential-based path bằng HTTP Basic hoặc cơ chế filter thật phù hợp.
- [ ] HTTP integration tests không vô tình kế thừa mock principal từ annotation cấp class.
- [ ] Ca POST kiểm tra quyền có CSRF hợp lệ; ca thiếu CSRF được kiểm tra riêng.
- [ ] Có ca unauthorized, unauthenticated, authenticated-but-forbidden và authorized.
- [ ] Với JWT/SSO/LDAP/X.509/MFA, test đúng provider/protocol của nguồn danh tính thay vì chỉ tạo fixture trông giống danh tính thật.
- [ ] Test failure của provider không mở fallback yếu, không rò credential/token/secret trong logs.
- [ ] Các trạng thái quyền theo account/tenant, session và thu hồi được kiểm tra theo SLA thực tế.
- [ ] Kết quả được giải thích theo lớp: fixture, manager/provider, filter/entry point, method-security hoặc hạ tầng E2E.

**Tóm tắt:** Dùng `@WithMockUser`, `@WithUserDetails` và các mock request helpers để kiểm tra **nếu một principal đã được xác thực và có authorities nhất định thì authorization quyết định đúng không**. Dùng token **chưa xác thực** với `AuthenticationManager` hoặc gửi credential qua **filter thật** để kiểm tra **tài khoản/mật khẩu/token có thực sự được xác minh không**. Hệ thống đáng tin cậy cần cả hai loại bằng chứng, đặc biệt trên các đường dẫn nhạy cảm.