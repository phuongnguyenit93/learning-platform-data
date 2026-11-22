# spring-security-test và các TestExecutionListener liên quan

> **Phạm vi:** Kiểm thử bảo mật phương thức (method security) trên **Spring Security Servlet**, Spring Boot 3.x, Spring Security 6.x, JUnit Jupiter và Java 17+. Bài tập trung vào cách `spring-security-test` phối hợp với Spring TestContext, đặc biệt là `WithSecurityContextTestExecutionListener`, cách tạo principal trong test, thời điểm nạp/dọn `SecurityContext` và cách không nhầm mock authentication với xác thực thực sự qua HTTP.

## 1. Vì sao cần thư viện spring-security-test?

Ứng dụng sử dụng `@EnableMethodSecurity` và `@PreAuthorize` thường có yêu cầu như:

```java
@PreAuthorize("hasAuthority('REPORT_READ')")
public String readReport() {
    return "report-visible";
}
```

Để kiểm thử method này, cần xác định **caller nào đang được Spring Security xem là authenticated** và caller đó có authorities nào. Trong request HTTP thật, chuỗi filter có thể xác thực Basic, form login, JWT hoặc OIDC rồi tạo `Authentication` trong `SecurityContextHolder`. Nhưng trong một bài test gọi trực tiếp Spring bean, **không nhất thiết có HTTP request hoặc authentication filter chạy trước**.

`spring-security-test` cung cấp các công cụ chuyên biệt:

- Annotation `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails` và `@WithSecurityContext` để tạo security context phù hợp cho test.
- Spring `TestExecutionListener` tự động thiết lập/dọn trạng thái test, thường là `WithSecurityContextTestExecutionListener`.
- Request post-processors cho MockMvc như `user(...)`, `httpBasic(...)`, `csrf()`, `jwt(...)` và `oauth2Login()` (tùy module/cách dùng).
- `SecurityMockMvcConfigurers.springSecurity()` để tích hợp bảo mật vào MockMvc khi tự xây builder.
- Các assertion/test helper dành cho bảo mật MVC, giúp kiểm tra cả endpoint và cơ chế security trong request.

**Điểm quan trọng:** Annotation `@WithMockUser` chỉ **mô phỏng `Authentication`**; nó không kiểm tra password, JWT signature, client secret hoặc việc người dùng có tồn tại trong database. Muốn xác minh toàn tuyến cần thêm test đi qua filter thực và các integration/E2E tests phù hợp.

## 2. Spring TestContext, JUnit và listener: ai làm gì?

Có **ba nhóm thành phần** dễ bị nhầm:

1. **JUnit Jupiter**: chạy `@Test`, `@BeforeEach`, `@AfterEach`, các assertion và extension.
2. **Spring TestContext Framework**: quản lý `ApplicationContext`, dependency injection, transactions, test instance và gọi các `TestExecutionListener`.
3. **Spring Security Test**: cắm listener và annotation bảo mật vào TestContext để nạp/dọn `SecurityContext` trước/sau bài test.

Luồng đơn giản:

```text
JUnit bắt đầu chạy một test
          |
SpringExtension / SpringBootTestContextBootstrapper
          |
Spring TestContext tạo hoặc tái sử dụng ApplicationContext
          |
Các TestExecutionListener của Spring thực thi theo lifecycle
          |
WithSecurityContextTestExecutionListener
   +-- đọc @WithMockUser / @WithUserDetails / @WithSecurityContext
   +-- tạo Authentication và đặt SecurityContext cho luồng test
          |
@Test gọi service bean Spring / MockMvc
          |
Spring Method Security interceptor kiểm tra @PreAuthorize
          |
Assertion về kết quả hoặc AccessDeniedException
          |
TestContext cleanup security context
```

`@SpringBootTest` đã tích hợp JUnit 5 thông qua `SpringExtension`; thông thường **không cần khai báo thêm `@ExtendWith(SpringExtension.class)`**. Nếu dùng cấu hình Spring TestContext tối thiểu (`@ContextConfiguration`), cần bảo đảm test chạy với SpringExtension.

`WithSecurityContextTestExecutionListener` thuộc module **`spring-security-test`**, không phải `spring-security-web` hay `spring-security-config`. Vì vậy chỉ có starter security cho ứng dụng mà **quên dependency test** sẽ không có các annotation và listener này trong test classpath.

### 2.1. TestExecutionListener không phải HTTP Servlet filter

| Thành phần | Chạy ở đâu? | Trách nhiệm |
|---|---|---|
| `WithSecurityContextTestExecutionListener` | Spring TestContext lifecycle của bài test | Dựng/đặt/dọn `SecurityContext` cho `@WithMockUser`, `@WithUserDetails` hoặc custom annotation |
| `DependencyInjectionTestExecutionListener` | Spring TestContext | Inject bean, chuẩn bị đối tượng test |
| `TransactionalTestExecutionListener` | Spring TestContext khi có transaction test | Quản lý test transaction và rollback theo cấu hình |
| `SecurityFilterChain` | HTTP request trong ứng dụng Servlet | Nhận request, chạy authentication/authorization filters |
| `WithSecurityContextFactory` | Được listener gọi trong test | Tạo `SecurityContext` từ custom annotation |
| `AuthenticationManager` / `AuthenticationProvider` | Cơ chế authentication của app | Kiểm tra credentials qua provider thực |
| Method-security interceptor | Lời gọi bean đã được proxy/advised | Thực thi `@PreAuthorize`/`@PostAuthorize` |

Một test `@WithMockUser` **không tự gửi request**, không tự gọi `AuthenticationProvider`, không mở session trình duyệt và không bảo đảm Spring security filter chain được cấu hình đúng.

### 2.2. Phân biệt các TestExecutionListener liên quan

Trong Spring Security Test có các listener liên quan tới context bảo mật:

- **`WithSecurityContextTestExecutionListener`**: xử lý các annotation tạo security context cho test dựa trên TestContext, nạp theo thời điểm `setupBefore`, dọn sau test. Đây là listener cốt lõi cho **Servlet method-security tests**.
- **`ReactorContextTestExecutionListener`**: hỗ trợ bối cảnh bảo mật của Reactor khi có reactive security và môi trường phù hợp. Đối với bài này trên **Servlet/MVC**, không nhầm nó với filter hoặc điều kiện bắt buộc để `@WithMockUser` có tác dụng trong service thông thường.

Spring TestContext còn có nhiều listener mặc định do Spring Framework hoặc Spring Boot sử dụng (ví dụ dependency injection, transaction, test database). Chúng có vòng đời/độ ưu tiên riêng. Không nên thay toàn bộ listener mặc định chỉ để “bật Spring Security Test”.

## 3. Dependency và cấu hình tối thiểu

Với Gradle, dùng `spring-security-test` ở scope **test** và quản lý version đồng bộ với Spring Security của ứng dụng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Trong Maven, thông thường:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

Đoạn XML minh họa trong dự án đã sử dụng Spring Boot dependency management. Không tự gán version `spring-security-test` khác với `spring-security-core`/`config`/`web` nếu chưa có kiểm chứng tương thích.

Kiểm tra phiên bản resolved trên Gradle:

```bash
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
```

Với Spring Security 6 trên Servlet stack, code Java thường dùng `jakarta.servlet.*` thay cho `javax.servlet.*`. Test service thuần không cần khởi chạy browser; test full application context cần đủ bean và cấu hình `@EnableMethodSecurity`.

## 4. @WithMockUser: tạo Authentication giả lập, không kiểm tra password

`@WithMockUser` cho phép khai báo principal và granted authorities ở class hoặc method.

Ví dụ:

```java
@Test
@WithMockUser(username = "alice", roles = "ADMIN")
void adminCanApprove() {
    // Trong test, SecurityContext có một Authentication
    // với principal "alice" và authority "ROLE_ADMIN".
}
```

Tính chất quan trọng:

- Mặc định `@WithMockUser` có username `user` và role `USER`, tương ứng authority `ROLE_USER`.
- `roles = "ADMIN"` tạo authority `ROLE_ADMIN`. Không truyền prefix `ROLE_` vào phần tử `roles`: hãy dùng `roles = "ADMIN"`, **không phải** `roles = "ROLE_ADMIN"`.
- `authorities = "REPORT_READ"` tạo authority chính xác `REPORT_READ`, không tự thêm `ROLE_`. Nếu muốn test `hasAuthority("REPORT_READ")`, dùng `authorities` là cách trực tiếp nhất.
- Tránh phối hợp `roles` và `authorities` trong cùng annotation khi không rõ cách thuộc tính được xử lý; nên chỉ dùng một cấu hình authority minh bạch.
- `@WithMockUser` có thể đặt trên class để áp dụng chung, rồi override tại method khi có ca riêng; hãy đọc precedence khi dùng annotation kết hợp.
- Không cần tạo user `alice` trong `UserDetailsService`. Đây là lợi ích để test authorization cô lập nhưng cũng là **giới hạn** khi test login/credential verification.

### 4.1. Test điều được phép và bị từ chối

Giả sử service bean có:

```java
@Service
public class ReportService {
    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String readReport() {
        return "report-visible";
    }
}
```

Cả `@Service` và `@PreAuthorize` phải được import và bean phải đi qua method security proxy khi gọi. Test:

```java
@Test
@WithMockUser(authorities = "REPORT_READ")
void readerCanRead() {
    assertEquals("report-visible", reportService.readReport());
}

@Test
@WithMockUser(authorities = "OTHER")
void unrelatedAuthorityCannotRead() {
    assertThrows(AccessDeniedException.class,
            reportService::readReport);
}
```

Các method trên là đoạn minh họa nằm trong một class test có field `reportService` do Spring inject; mục 8 cung cấp chương trình **đầy đủ với file thật**. Nếu bạn trực tiếp `new ReportService()` mà không dùng bean được Spring proxy, `@PreAuthorize` có thể không chạy; test trả PASS giả.

## 5. @WithUserDetails: lấy user từ UserDetailsService thật của test

`@WithUserDetails("reader")` khác `@WithMockUser(username = "reader")`:

- `@WithMockUser` tạo principal giả, không cần gọi `UserDetailsService`.
- `@WithUserDetails` yêu cầu có `UserDetailsService` trong `ApplicationContext` và **tải `UserDetails` theo username**. Nó dùng thông tin authorities/principal từ fixture thực.
- Cả hai đều thiết lập security context cho test; **không gọi password authentication provider để kiểm tra mật khẩu**.
- Nếu user không tồn tại trong fixture hoặc không có bean `UserDetailsService` thích hợp, `@WithUserDetails` có thể lỗi ở giai đoạn chuẩn bị test **trước khi thân `@Test` chạy**.
- Nếu nhiều `UserDetailsService`, dùng thuộc tính `userDetailsServiceBeanName` để xác định bean cần tải.

Ví dụ:

```java
@Test
@WithUserDetails(value = "reader")
void loadedReaderHasPermission() {
    assertEquals("report-visible", reportService.readReport());
}
```

Trường hợp user thật trong kho dữ liệu bị **disabled, locked hoặc password expired**, `@WithUserDetails` vẫn không tự thay cho test authentication manager kiểm tra các chính sách credential/account status: nó chuẩn bị principal đã authenticated cho test. Nếu cần xác minh từ chối credential của tài khoản disabled, hãy đi qua provider/filter thật.

**Chú ý dữ liệu test:** dùng tài khoản fixture riêng, không dùng database production, không lưu mật khẩu thật hoặc phân quyền bí mật trong test logs.

## 6. TestExecutionListener đặt và xóa SecurityContext khi nào?

### 6.1. setupBefore = TEST_METHOD

Mặc định, các annotation `@WithMockUser`/`@WithUserDetails` dùng thời điểm `TestExecutionEvent.TEST_METHOD`. `WithSecurityContextTestExecutionListener` thiết lập context trong giai đoạn **beforeTestMethod** của Spring TestContext, tức thông thường **trước JUnit `@BeforeEach`**.

Điều đó có nghĩa test setup như sau có thể quan sát principal đã giả lập:

```java
@BeforeEach
void prepare() {
    Authentication a = SecurityContextHolder.getContext().getAuthentication();
    // Với @WithMockUser setupBefore=TEST_METHOD,
    // Authentication thường đã tồn tại tại đây.
}
```

Đây là snippet trong class test đã import `Authentication` và `SecurityContextHolder`. Nó không chứng minh trạng thái toàn hệ thống, mà chỉ cho thấy context ở **test thread**.

### 6.2. setupBefore = TEST_EXECUTION

Có lúc cần `@BeforeEach` chạy **trước khi security context được cài**: chẳng hạn bạn muốn chuẩn bị dữ liệu test, reset fixture hoặc thay đổi UserDetailsService rồi mới load user.

```java
@Test
@WithUserDetails(
    value = "reader",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
void readerLoadedAfterBeforeEach() {
    // Context được thiết lập trong beforeTestExecution,
    // ngay trước thân method @Test, sau @BeforeEach.
}
```

`TestExecutionEvent` có package `org.springframework.security.test.context.support.TestExecutionEvent`. Thời điểm này có thể hữu ích khi user được tạo trong `@BeforeEach`. Nhưng nếu fixture nằm trong transaction do test listener quản lý, cần đánh giá transaction boundary và khả năng lookup thực tế; đừng giả định mọi thao tác repository/DB cùng context và đã commit.

**Không dùng `setupBefore=TEST_EXECUTION` nếu `@BeforeEach` dựa vào principal đã được tạo.** Nếu setup phải kiểm tra quyền trước test method, mặc định `TEST_METHOD` phù hợp hơn.

### 6.3. Dọn SecurityContext tránh rò trạng thái

Sau test, listener dọn test security context để method sau không vô tình thừa hưởng principal/authority cũ. Đây là lý do sử dụng cơ chế chuẩn tốt hơn tự gọi:

```java
SecurityContextHolder.getContext().setAuthentication(...);
```

nếu không có cleanup tương ứng.

Một số giới hạn cần nhớ:

- `SecurityContextHolder` mặc định dùng cơ chế lưu trữ theo thread; cùng một test thread nhưng trạng thái không được dọn có thể ảnh hưởng test kế tiếp.
- `@Async`, thread pool hoặc scheduler có thể chạy trên thread khác và **không tự nhận context test**, trừ khi có propagation phù hợp; đừng kết luận framework sai chỉ vì test không truyền security context qua thread boundary.
- Nếu tự sửa `TestSecurityContextHolder` hoặc thay security context strategy, phải khôi phục state và tránh các race conditions giữa bài test chạy song song.
- Đặt principal ở `@BeforeAll` hoặc expect annotation method-level có hiệu lực tại `@BeforeAll` là sai vòng đời: listener đặt context **cho từng test method**.
- Nếu test dùng transaction, listener của Spring có lifecycle/order riêng; phân biệt rollback DB với cleanup authentication.

## 7. TestExecutionListeners custom: cách tránh mất listener bảo mật

Spring TestContext cung cấp `@TestExecutionListeners` để gắn listener vào vòng đời test. Sai lầm quen thuộc:

```java
@TestExecutionListeners(MyAuditListener.class)
class ReportMethodSecurityTest {
    // Có nguy cơ thay tập listener mặc định.
}
```

Khi khai báo tập listener tùy chỉnh mà không chỉ rõ cách merge, bạn có thể vô tình thay default listeners. Hậu quả gồm mất dependency injection, transaction setup hoặc `WithSecurityContextTestExecutionListener`; khi đó `@WithMockUser` không được áp dụng như kỳ vọng.

Cách an toàn hơn nếu cần bổ sung listener:

```java
import org.springframework.test.context.TestExecutionListeners;

@TestExecutionListeners(
    listeners = MyAuditListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class ReportMethodSecurityTest {
    // Giữ tập listener mặc định và bổ sung MyAuditListener.
}
```

Đây là snippet minh họa, `MyAuditListener` là listener tùy chỉnh do ứng dụng định nghĩa, **không phải class có sẵn** trong Spring Security. Không paste vào demo mục 8 nếu chưa có class này. Khi cần tùy chỉnh lifecycle:

1. Triển khai `TestExecutionListener` hoặc mở rộng `AbstractTestExecutionListener`.
2. Chọn callback thích hợp (`beforeTestMethod`, `beforeTestExecution`, `afterTestExecution`, `afterTestMethod`).
3. Giữ `MERGE_WITH_DEFAULTS` trừ khi thực sự muốn thay tập mặc định và hiểu toàn bộ hậu quả.
4. Nếu listener mới đọc auth, quan tâm **order** tương quan với `WithSecurityContextTestExecutionListener`; listener chạy trước khi auth được đặt có thể thấy context trống.
5. Tránh listener khởi tạo principal toàn cục hoặc ghi dữ liệu nhạy cảm vào log.

**TestExecutionListener khác JUnit Extension.** `@ExtendWith(...)` gắn JUnit 5 extension; `@TestExecutionListeners(...)` gắn Spring TestContext listeners. Với `@SpringBootTest`, SpringExtension thường đã có; không sửa danh sách listeners chỉ để “đăng ký Spring”.

### 7.1. Một ví dụ listener tùy chỉnh không phụ thuộc principal

Nếu cần thu thập thông tin test name trong môi trường thử nghiệm, một listener minh họa có thể là:

```java
import org.springframework.test.context.TestContext;
import org.springframework.test.context.support.AbstractTestExecutionListener;

public final class TestNameListener extends AbstractTestExecutionListener {
    @Override
    public void beforeTestMethod(TestContext testContext) {
        String testName = testContext.getTestMethod().getName();
        // Ghi metric test name qua reporter đã cấu hình (nếu cần).
        // Không log password, session ID hoặc token.
    }
}
```

Đoạn này là **class Java minh họa** và cần đặt tên file `TestNameListener.java` trong package thích hợp; biến `testName` cho thấy thời điểm lấy metadata, không phải production telemetry. Không dùng listener tự viết để gán quyền admin cho test suite.

## 8. Ví dụ hoàn chỉnh: Spring Boot 3.3.x, Java 17, method security và MockMvc

Phần này chứa một dự án Gradle mẫu để kiểm tra đồng thời:

- `@PreAuthorize` thực sự áp dụng trên bean Spring.
- `@WithMockUser` dựng security context cho method test.
- `@WithUserDetails` lấy user từ in-memory `UserDetailsService`.
- `MockMvc` với security filters cho thấy sự khác nhau giữa **mock principal** và **HTTP Basic credential thật**.
- CSRF còn hiệu lực trên POST, tránh nhầm HTTP 403 do CSRF với thiếu role.

### 8.1. Cấu trúc dự án và Gradle

`build.gradle`:

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

Tạo package `demo.securitytest` theo cây file:

```text
src/
  main/java/demo/securitytest/
    SecurityTestApplication.java
    SecurityConfig.java
    ReportService.java
    ReportController.java
  test/java/demo/securitytest/
    ReportMethodSecurityTest.java
    ReportMvcSecurityTest.java
```

Đây là demo **local** với tài khoản cố định cho mục đích test, không phải hệ thống người dùng production. Với dự án có Gradle Wrapper, ví dụ sẽ dùng `./gradlew test`.

### 8.2. Ứng dụng chính

`src/main/java/demo/securitytest/SecurityTestApplication.java`:

```java
package demo.securitytest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityTestApplication.class, args);
    }
}
```

### 8.3. Cấu hình SecurityFilterChain, UserDetailsService và method security

`src/main/java/demo/securitytest/SecurityConfig.java`:

```java
package demo.securitytest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("local-read-pass"))
            .authorities("REPORT_READ")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("local-admin-pass"))
            .authorities("ROLE_ADMIN", "REPORT_READ")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers("/reports/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

**Giải thích:** `@EnableMethodSecurity` bật method authorization; `hasAuthority('REPORT_READ')` so khớp chính xác một authority, `hasRole('ADMIN')` thường trông đợi `ROLE_ADMIN`. SecurityFilterChain chỉ đòi authenticated cho `/reports/**`, còn quyền cụ thể do `@PreAuthorize` trên service kiểm soát. Cách chia lớp này cho thấy **authentication ở HTTP** và **authorization ở method** là hai tầng khác nhau.

CSRF vẫn bật mặc định, nên POST `/reports/approve` cần `csrf()` trong MockMvc khi dùng session-like request; test thiếu CSRF cho kết quả 403 **trước khi kiểm tra quyền service**. Không vô hiệu hóa CSRF để test dễ hơn.

### 8.4. Service bảo vệ bằng @PreAuthorize

`src/main/java/demo/securitytest/ReportService.java`:

```java
package demo.securitytest;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String readReport() {
        return "report-visible";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String approve() {
        return "approved";
    }
}
```

Lưu ý phải inject `ReportService` từ Spring. Nếu tạo bằng `new ReportService()` hoặc gọi một phương thức được bảo vệ qua **self-invocation nội bộ** không đi qua proxy, test có thể bỏ qua advice của method security. Đó là lỗi wiring chứ không phải do `@WithMockUser`.

### 8.5. MVC controller để kiểm tra filter chain

`src/main/java/demo/securitytest/ReportController.java`:

```java
package demo.securitytest;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    private final ReportService reports;

    public ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping(value = "/public", produces = MediaType.TEXT_PLAIN_VALUE)
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping(value = "/reports/read",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String readReport() {
        return reports.readReport();
    }

    @PostMapping(value = "/reports/approve",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public String approve() {
        return reports.approve();
    }
}
```

Khi test MVC, tất cả request phải đi qua filter chain cấu hình. Nếu dùng `@AutoConfigureMockMvc(addFilters = false)` hoặc tự tạo `MockMvcBuilders.standaloneSetup(...)` mà không gắn Spring Security, bạn có thể nhận false positive/negative về authentication/authorization.

### 8.6. Method-security test dùng @WithMockUser và @WithUserDetails

`src/test/java/demo/securitytest/ReportMethodSecurityTest.java`:

```java
package demo.securitytest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class ReportMethodSecurityTest {
    @Autowired
    ReportService reports;

    @Test
    @WithMockUser(authorities = "REPORT_READ")
    void mockReaderIsAllowed() {
        assertEquals("report-visible", reports.readReport());
    }

    @Test
    @WithMockUser(authorities = "OTHER")
    void wrongAuthorityIsDenied() {
        assertThrows(AccessDeniedException.class,
                reports::readReport);
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void mockAdminCanApprove() {
        assertEquals("approved", reports.approve());
    }

    @Test
    @WithUserDetails("reader")
    void realUserDetailsFixtureHasReportAuthority() {
        assertEquals("report-visible", reports.readReport());
    }

    @Test
    @WithUserDetails("reader")
    void loadedReaderCannotApprove() {
        assertThrows(AccessDeniedException.class,
                reports::approve);
    }
}
```

Các test này **không gửi HTTP request** và không xác minh password. `@WithUserDetails` dùng user `reader` trong `InMemoryUserDetailsManager` để kiểm tra mapping authority thực của fixture; `@WithMockUser` tạo trực tiếp principal và authority theo annotation. Method security hoạt động vì `ReportService` là bean được proxy, `@EnableMethodSecurity` đang bật.

### 8.7. MockMvc test dùng mock principal, CSRF và HTTP Basic thật

`src/test/java/demo/securitytest/ReportMvcSecurityTest.java`:

```java
package demo.securitytest;

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
class ReportMvcSecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointWorks() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousReportRequestIsChallengedByBasicAuth()
            throws Exception {
        mvc.perform(get("/reports/read"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(authorities = "REPORT_READ")
    void mockReaderCanReadOverMvc() throws Exception {
        mvc.perform(get("/reports/read"))
            .andExpect(status().isOk())
            .andExpect(content().string("report-visible"));
    }

    @Test
    @WithMockUser(authorities = "OTHER")
    void mockUserWithoutAuthorityGets403() throws Exception {
        mvc.perform(get("/reports/read"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminNeedsCsrfForPost() throws Exception {
        mvc.perform(post("/reports/approve"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminWithCsrfCanApprove() throws Exception {
        mvc.perform(post("/reports/approve").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("approved"));
    }

    @Test
    void validBasicCredentialsUseRealAuthenticationProvider()
            throws Exception {
        mvc.perform(get("/reports/read")
                .with(httpBasic("reader", "local-read-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("report-visible"));
    }

    @Test
    void invalidBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/reports/read")
                .with(httpBasic("reader", "not-the-password")))
            .andExpect(status().isUnauthorized());
    }
}
```

Hai test cuối khác bản chất với `@WithMockUser`: `httpBasic(...)` chỉ đính kèm **HTTP Authorization header** vào request. Spring Security HTTP Basic filter phải thực sự kiểm chứng username/password thông qua `AuthenticationManager` và `UserDetailsService`; vì vậy đây là kiểm tra gần hơn với authentication thật trong app demo.

Dẫu vậy, MockMvc không mở socket mạng, không kiểm tra TLS/proxy/browser, và `InMemoryUserDetailsManager` chỉ là fixture. E2E cần thêm test theo môi trường triển khai.

### 8.8. Chạy và đọc kết quả

Trong dự án có Gradle Wrapper:

```bash
./gradlew test
```

Kết quả đúng là **mọi test hoàn thành PASS**, bao gồm các test cố ý kỳ vọng ngoại lệ hoặc HTTP 403/401. Vì output Gradle phụ thuộc phiên bản wrapper, cấu hình logging và trạng thái cache, không giả định từng dòng console giống hệt máy khác.

Có thể chạy riêng class:

```bash
./gradlew test --tests demo.securitytest.ReportMethodSecurityTest
./gradlew test --tests demo.securitytest.ReportMvcSecurityTest
```

Nếu gặp `UnsatisfiedDependencyException`, kiểm tra bean cấu hình. Nếu `@PreAuthorize` không chặn, kiểm tra `@EnableMethodSecurity`, bean proxy và self-invocation trước khi đổi annotation test. Nếu HTTP Basic test không thành công, kiểm tra `PasswordEncoder` và user fixture, không sửa kỳ vọng 401/403 theo cảm tính.

## 9. Tạo custom security context bằng @WithSecurityContext

Khi `@WithMockUser` không đủ diễn đạt kiểu principal hoặc authorities của domain, có thể dùng meta-annotation `@WithSecurityContext` với factory tùy chỉnh. Cơ chế là:

```text
@WithReportReader trên test
     |
WithSecurityContextTestExecutionListener đọc annotation
     |
WithReportReaderFactory.createSecurityContext(...)
     |
SecurityContext chứa Authentication mô phỏng
     |
Spring method-security interceptor đọc authorities
```

Dưới đây là **hai file độc lập dành cho `src/test/java`** trong package `demo.securitytest`. Chúng có thể thêm vào dự án mục 8 nếu cần mô phỏng một reader có username riêng.

**`src/test/java/demo/securitytest/WithReportReader.java`:**

```java
package demo.securitytest;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.test.context.support.WithSecurityContext;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithSecurityContext(factory = WithReportReaderFactory.class)
public @interface WithReportReader {
    String username() default "domain-reader";
}
```

**`src/test/java/demo/securitytest/WithReportReaderFactory.java`:**

```java
package demo.securitytest;

import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

public final class WithReportReaderFactory
        implements WithSecurityContextFactory<WithReportReader> {
    @Override
    public SecurityContext createSecurityContext(WithReportReader annotated) {
        var auth = new UsernamePasswordAuthenticationToken(
            annotated.username(),
            "N/A",
            List.of(new SimpleGrantedAuthority("REPORT_READ"))
        );
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(auth);
        return context;
    }
}
```

Phần này **chỉ tạo principal/authorities giả lập**, hoàn toàn không kiểm tra password `"N/A"` và không tự tải user từ database. Ví dụ dùng trong class method test:

```java
@Test
@WithReportReader(username = "tenant-a-reader")
void readerAnnotationAllowsReading() {
    assertEquals("report-visible", reports.readReport());
}
```

Ưu điểm là giảm lặp và đặt rõ ý nghĩa nghiệp vụ của fixture. Khi ứng dụng cần custom principal chứa tenant, department hoặc subject ID, factory phải tạo đúng loại principal và đi kèm các authority được kiểm soát. Đừng tự gán `ROLE_ADMIN` cho mọi custom annotation; test an toàn cần có ca **không có quyền** và ca **khác tenant**.

## 10. MockMvc và listener: dùng annotation hay request post-processor?

Cả hai hướng đều có ích nhưng không tương đương toàn bộ.

### 10.1. Dùng @WithMockUser ở method test

```java
@Test
@WithMockUser(authorities = "REPORT_READ")
void test() throws Exception {
    mvc.perform(get("/reports/read"))
        .andExpect(status().isOk());
}
```

Annotation thiết lập context cho test method qua listener, tiện khi một testcase dùng cùng identity trong nhiều lời gọi. Nó không buộc endpoint sử dụng credential thật. Phải chạy với Spring TestContext và MockMvc tích hợp filter đúng.

### 10.2. Dùng request post-processor trên từng request

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;

mvc.perform(get("/reports/read")
        .with(user("reader").authorities(
            new SimpleGrantedAuthority("REPORT_READ"))))
    .andExpect(status().isOk());
```

Đây là **snippet** nằm trong một method test có `mvc` và import `SimpleGrantedAuthority`. Request post-processor phù hợp khi một test cần so sánh nhiều danh tính trên nhiều request riêng biệt. Nếu tự cấu hình `MockMvcBuilders`, phải tích hợp `springSecurity()` phù hợp, nếu không user fixture đặt vào request có thể không đi qua các filter/context đúng.

### 10.3. Khi nào phải đi qua authentication filter thật?

- Kiểm tra **password encoder/account lockout**: gửi `httpBasic(...)` hoặc `formLogin(...)` với credential có thật trong test fixture, không dùng `@WithMockUser` làm bằng chứng.
- Kiểm tra **JWT signature, issuer, audience**: `jwt()` post-processor tạo bối cảnh giả và thường bypass JWT decoder; cần test thực qua `JwtDecoder` hoặc token ký bằng test key khi muốn kiểm tra validation.
- Kiểm tra **OIDC login protocol/state/nonce/redirect**: `oauth2Login()` helper tạo authentication giả theo mục tiêu test; test integration thật phải xác minh client/IdP callback contract.
- Kiểm tra **CSRF**: `with(csrf())` đặt request token hợp lệ để test logic sâu hơn; cố ý thử không có hoặc sai token để kiểm chứng bảo vệ. HTTP 403 từ CSRF không đồng nghĩa `@PreAuthorize` đã từ chối.

## 11. Failure modes trong method-security tests

**1. Thiếu `spring-security-test`.** Annotation không compile, hoặc custom fixture/listener không tồn tại. Thêm dependency ở `testImplementation`/`test` và dùng version phù hợp Spring Security.

**2. Test không chạy qua Spring TestContext.** Gọi method của object được `new` trong JUnit test thuần không có listener và không có method-security proxy. Dùng SpringExtension + Spring context khi cần test AOP security.

**3. Quên `@EnableMethodSecurity`.** `@PreAuthorize` trên service không tự được enforce trong một cấu hình chưa bật method security. Kiểm tra cấu hình security thực tế.

**4. Tạo service bằng `new` hoặc self-invocation.** Lời gọi không đi qua Spring proxy nên có thể bỏ qua advice. Inject bean vào test và điều chỉnh thiết kế service/authorization.

**5. Nhầm `roles` với `authorities`.** `roles = "ADMIN"` thường tạo `ROLE_ADMIN`; `authorities = "ADMIN"` chỉ tạo `ADMIN`. Rule `hasRole('ADMIN')` có ý nghĩa khác với `hasAuthority('ADMIN')`.

**6. Tin `@WithMockUser` kiểm tra login.** Fake principal đã authenticated sẵn. Mật khẩu sai/đúng, account status, session, JWT decoder và IdP không được kiểm thử bởi annotation này.

**7. `@WithUserDetails` báo user không tồn tại trước khi test chạy.** Listener tải user theo đúng tên vào `UserDetailsService`; fixture thiếu hoặc được tạo quá muộn. Dùng `setupBefore = TEST_EXECUTION` nếu cần tạo dữ liệu ở `@BeforeEach`, sau khi xem transaction boundary.

**8. `@TestExecutionListeners` làm mất default listeners.** Custom annotation thiếu `MERGE_WITH_DEFAULTS` có thể thay tập listeners, dẫn tới inject bean hoặc `WithSecurityContextTestExecutionListener` không hoạt động. Kiểm tra test bootstrap config.

**9. Test method SecurityContext khác request context.** TestContext, MockMvc và thread-local phải tích hợp đúng. Với async/multithread, cần propagation hoặc test tầng riêng.

**10. Phân quyền bị CSRF che mất.** POST thiếu CSRF trả 403 trước controller. Dùng `with(csrf())` cho ca kiểm tra quyền và thêm ca âm độc lập để kiểm tra CSRF.

**11. Test pass dù thiếu security filter.** `@AutoConfigureMockMvc(addFilters = false)` hoặc standalone MockMvc không gắn `springSecurity()` khiến test không phản ánh FilterChainProxy thật.

**12. Chạy song song gây lộ trạng thái.** Thao tác trực tiếp vào `SecurityContextHolder`, global mutable state hoặc static context không có cleanup làm các bài test ảnh hưởng nhau; prefer listeners và fixture riêng.

**13. Kiểm tra sai lớp của hệ thống.** Unit method test xác minh `@PreAuthorize` không chứng minh UI, reverse proxy, gateway, session fixation hoặc authorization trên một endpoint khác. Tách mục tiêu test cho từng lớp.

## 12. Thiết kế ma trận kiểm thử có ý nghĩa

| Case | Fixture/đường kiểm thử | Assertion cần có |
|---|---|---|
| Được phép theo authority | `@WithMockUser(authorities="REPORT_READ")` gọi injected service | Method trả dữ liệu hợp lệ |
| Bị từ chối theo authority | `@WithMockUser(authorities="OTHER")` | `AccessDeniedException` |
| Quyền ROLE_ | `@WithMockUser(roles="ADMIN")` | `hasRole('ADMIN')` cho phép |
| User fixture thật | `@WithUserDetails("reader")` | Authorities từ `UserDetailsService` áp dụng đúng |
| Unauthenticated HTTP | MockMvc GET path protected không credential | 401 hoặc challenge theo entry point được cấu hình |
| Authorized MockMvc | `@WithMockUser` + request đến controller | 200, dữ liệu đúng, không bypass Method Security |
| POST thiếu CSRF | `@WithMockUser(roles="ADMIN")` nhưng không token | 403 tại CSRF filter |
| POST có CSRF | `with(csrf())` và ADMIN | 200, method chạy |
| HTTP Basic đúng password | `httpBasic("reader", validPassword)` | 200, authentication provider thật chạy |
| HTTP Basic sai password | `httpBasic("reader", invalidPassword)` | 401, không trả dữ liệu |
| Custom annotation | `@WithSecurityContext` + custom factory | Principal/authorities được tạo đúng |
| Custom listener | `@TestExecutionListeners(...MERGE_WITH_DEFAULTS)` | Listener bảo mật và dependency injection vẫn hoạt động |
| Context timing | `setupBefore=TEST_METHOD/TEST_EXECUTION` | Trạng thái tại `@BeforeEach` đúng theo contract |
| Async method | Thread pool/`@Async` | Không phụ thuộc giả định tự truyền thread-local; có test propagation |
| Test cleanup | Hai test chạy kế tiếp với user khác nhau | Không thừa hưởng auth từ ca trước |

Đối với các rule phức tạp (tenant ownership, ACL, dữ liệu theo tổ chức), cần thêm fixture **người dùng đủ authority nhưng không sở hữu tài nguyên**. Chỉ dùng `hasRole` trên một user giả thường chưa đủ để chứng minh phân quyền ở mức đối tượng.

## 13. Checklist và ghi nhớ

- [ ] Dependency `spring-security-test` có trong test classpath, version thống nhất với Spring Security.
- [ ] Test dùng Spring TestContext; `WithSecurityContextTestExecutionListener` có cơ hội chạy.
- [ ] Khi có custom `@TestExecutionListeners`, đã bảo toàn default listeners bằng merge mode thích hợp.
- [ ] Application context bật `@EnableMethodSecurity` và test gọi bean Spring được proxy.
- [ ] Chọn `@WithMockUser` để test authorization cô lập, `@WithUserDetails` để lấy user fixture; không nhầm hai loại với credential authentication.
- [ ] Phân biệt `roles`/`ROLE_` với `authorities` trực tiếp.
- [ ] Chọn `setupBefore` đúng vòng đời `@BeforeEach` và user fixture.
- [ ] Có ca **allow** và **deny**, role thấp/cao, principal khác tenant và resource không sở hữu khi phù hợp.
- [ ] MockMvc có filter chain; POST test authorization có CSRF hợp lệ, và có ca CSRF âm độc lập.
- [ ] Với test password/JWT/OIDC thật, đi qua đúng authentication provider/decoder/client, không chỉ tạo principal giả.
- [ ] SecurityContext được dọn giữa các method, không rò qua async/thread pool.
- [ ] Kết quả test giải thích đúng lớp: listener, method interceptor, MVC filter hay IdP/proxy.

**Tóm tắt:** `spring-security-test` là bộ công cụ làm cho **SecurityContext có thể kiểm thử được**, không phải hệ thống login thu nhỏ. `WithSecurityContextTestExecutionListener` chuẩn bị và dọn context theo lifecycle của Spring TestContext; `@WithMockUser` tạo principal giả, `@WithUserDetails` lấy user fixture, `@WithSecurityContext` tạo fixture tùy chỉnh. Với method security, phải bật `@EnableMethodSecurity` và gọi bean được Spring proxy; với MockMvc, phải gắn filter chain và phân biệt auth giả với credential thật. Cả listener đúng và assertion đúng mục tiêu mới cho một bộ test đáng tin.