# `@WithUserDetails` và dữ liệu người dùng trong `ApplicationContext` khi kiểm thử method security

Khi kiểm thử một phương thức có `@PreAuthorize`, `@PostAuthorize` hoặc quy tắc Spring Security khác, ta cần đặt một `Authentication` thích hợp vào `SecurityContext`. Với ca kiểm thử đơn giản, `@WithMockUser` thường đủ. Nhưng nếu nghiệp vụ sử dụng **kiểu principal tùy biến**, **quyền thực tế do `UserDetailsService` trả về**, hoặc dữ liệu người dùng được cung cấp qua Spring bean trong **`ApplicationContext`**, hãy dùng `@WithUserDetails`.

Mục tiêu của bài: hiểu chính xác `@WithUserDetails` lấy dữ liệu ở đâu, tại sao khác `@WithMockUser`, cách cấu hình bean và fixture dữ liệu cho test, cách kiểm tra quyền ở tầng phương thức, và cách xử lý vòng đời test khi người dùng được tạo trong `@BeforeEach`.

## 1. Phân biệt `ApplicationContext` và `SecurityContext`

Hai context này đảm nhiệm hai việc khác nhau:

- **`ApplicationContext`**: container của Spring, quản lý các bean như `UserDetailsService`, repository, service nghiệp vụ và cấu hình method security. Bean `UserDetailsService` có thể đọc người dùng từ bộ nhớ, từ database hoặc từ nguồn khác; bản thân `ApplicationContext` không phải là cơ sở dữ liệu người dùng.
- **`SecurityContext`**: chứa `Authentication` của lời gọi đang được kiểm thử, bao gồm principal và các `GrantedAuthority`. Spring Security đọc context này để đánh giá biểu thức phân quyền, ví dụ `@PreAuthorize("hasRole('ADMIN')")`.
- **`SecurityContextHolder`**: nơi truy cập `SecurityContext` cho ngữ cảnh thực thi hiện tại. Trong kiểm thử thông thường, Spring Security Test chuẩn bị context cho thread thực hiện test và dọn dẹp sau đó.

Dòng dữ liệu khi dùng annotation:

```text
ApplicationContext
  └── UserDetailsService bean ("accounts")
        └── loadUserByUsername("alice")
              └── UserDetails (có thể là CustomPrincipal)
                       |
                       v
        @WithUserDetails test listener
                       |
                       v
             Authentication
                       |
                       v
             SecurityContextHolder
                       |
                       v
    Spring-managed service proxy
                       |
                       v
        @PreAuthorize / @PostAuthorize
                       |
                 được phép / bị từ chối
```

**`@WithUserDetails` không đăng nhập qua HTTP, không kiểm tra mật khẩu và không tự tạo bản ghi người dùng.** Nó lấy một `UserDetails` đã có thể truy xuất qua bean được Spring quản lý rồi dựng `Authentication` cho test. Theo cách triển khai tiêu chuẩn, kiểu authentication được đặt vào context là `UsernamePasswordAuthenticationToken`, còn principal chính là đối tượng `UserDetails` được service trả về.

Nếu `loadUserByUsername("alice")` không tìm thấy người dùng, bước chuẩn bị security context sẽ thất bại trước khi phần thân test chạy. Vì thế phải cung cấp fixture dữ liệu hợp lệ, bằng bộ nhớ hoặc dữ liệu kiểm thử đã được seed ở đúng thời điểm.

## 2. Chọn `@WithMockUser` hay `@WithUserDetails`

| Tiêu chí | `@WithMockUser` | `@WithUserDetails` |
| --- | --- | --- |
| Principal đến từ đâu? | Spring Security Test dựng trực tiếp từ các thuộc tính annotation | Bean `UserDetailsService` lấy từ `ApplicationContext` trả về |
| Có cần username thực sự tồn tại không? | Không | Có, trong nguồn dữ liệu mà `UserDetailsService` đọc |
| Có gọi `loadUserByUsername(...)` không? | Không | Có |
| Principal có thể là kiểu tùy biến `AccountPrincipal` không? | Không qua thuộc tính thông thường của `@WithMockUser` | Có, nếu service trả về kiểu đó |
| Quyền của user lấy từ đâu? | `roles` / `authorities` trong annotation | `getAuthorities()` của `UserDetails` đã được load |
| Khi nào thuận tiện? | Thử nhanh rule `hasRole`, `hasAuthority` không cần dữ liệu domain | Kiểm tra rule và mã nghiệp vụ phụ thuộc custom principal hoặc nguồn user thật của test |

Ví dụ annotation:

```java
@WithMockUser(username = "alice", roles = "ADMIN")

@WithUserDetails("alice")

@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "accounts"
)
```

Các đoạn trên minh họa cú pháp đặt **trên test method hoặc test class**, không phải ba lệnh Java đứng riêng. `@WithUserDetails` mặc định tìm username `"user"` nếu không chỉ định; giá trị `"alice"` được truyền làm đầu vào cho `UserDetailsService.loadUserByUsername("alice")`.

Lưu ý khi so sánh role: `roles = "ADMIN"` của `@WithMockUser` cho authority `ROLE_ADMIN` theo quy ước mặc định. `hasRole("ADMIN")` cũng kiểm tra `ROLE_ADMIN`. Nếu custom service trả về authority `"ADMIN"` không có tiền tố, nó sẽ không khớp rule `hasRole("ADMIN")` với cấu hình tiền tố mặc định.

## 3. Ví dụ Java 17+ hoàn chỉnh: custom principal và kiểm thử `@PreAuthorize`

Đây là ví dụ dành cho **Spring Boot 3.x / Spring Security 6.x, JUnit Jupiter và Java 17+**. Trong dự án Spring Boot Gradle đã quản lý phiên bản dependency, cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tạo file **`src/test/java/example/WithUserDetailsMethodTest.java`**:

```java
package example;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;
import org.springframework.stereotype.Service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(classes = WithUserDetailsMethodTest.TestApplication.class)
class WithUserDetailsMethodTest {

    @Autowired
    ReportService reports;

    @Test
    @WithUserDetails(
        value = "alice",
        userDetailsServiceBeanName = "accounts"
    )
    void adminLoadsCustomPrincipalAndCanExport() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        assertInstanceOf(
            UsernamePasswordAuthenticationToken.class,
            authentication
        );

        AccountPrincipal principal =
            assertInstanceOf(
                AccountPrincipal.class,
                authentication.getPrincipal()
            );

        assertEquals("alice", authentication.getName());
        assertEquals(101L, principal.accountId());
        assertEquals("report-ready", reports.export());
    }

    @Test
    @WithUserDetails(
        value = "bob",
        userDetailsServiceBeanName = "accounts"
    )
    void viewerLoadsSuccessfullyButCannotExport() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        AccountPrincipal principal =
            assertInstanceOf(
                AccountPrincipal.class,
                authentication.getPrincipal()
            );

        assertEquals(202L, principal.accountId());
        assertThrows(
            AccessDeniedException.class,
            () -> reports.export()
        );
    }

    @Test
    @WithMockUser(username = "shadow", roles = "ADMIN")
    void mockUserCanPassRoleCheckWithoutExistingInUserService() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        assertEquals("shadow", authentication.getName());
        assertFalse(
            authentication.getPrincipal() instanceof AccountPrincipal
        );
        assertEquals("report-ready", reports.export());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    @Import({TestUsers.class, ReportService.class})
    static class TestApplication {
    }

    @Configuration(proxyBeanMethods = false)
    static class TestUsers {

        @Bean("accounts")
        UserDetailsService accounts() {
            Map<String, UserDetails> users = Map.of(
                "alice",
                new AccountPrincipal("alice", 101L, "ROLE_ADMIN"),
                "bob",
                new AccountPrincipal("bob", 202L, "ROLE_VIEWER")
            );

            return username -> {
                UserDetails user = users.get(username);
                if (user == null) {
                    throw new UsernameNotFoundException(
                        "Unknown test user: " + username
                    );
                }
                return user;
            };
        }
    }

    static class AccountPrincipal extends User {

        private final long accountId;

        AccountPrincipal(
            String username,
            long accountId,
            String authority
        ) {
            super(
                username,
                "{noop}test-only",
                List.of(new SimpleGrantedAuthority(authority))
            );
            this.accountId = accountId;
        }

        long accountId() {
            return accountId;
        }
    }

    @Service
    static class ReportService {

        @PreAuthorize("hasRole('ADMIN')")
        public String export() {
            return "report-ready";
        }
    }
}
```

Chạy trong dự án Spring Boot Gradle:

```bash
./gradlew test --tests example.WithUserDetailsMethodTest
```

Nếu dùng Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.WithUserDetailsMethodTest
```

Với đúng dependency và cấu hình trên, **kỳ vọng ba test đều PASS**. JUnit không tự in chuỗi `"report-ready"` ra stdout; đây là **giá trị trả về** được so sánh bằng `assertEquals`.

### Vì sao từng test có ý nghĩa?

**Test 1 — `alice`:** annotation lấy bean tên `accounts`, gọi `loadUserByUsername("alice")`, nhận một `AccountPrincipal` có `accountId=101` và `ROLE_ADMIN`. Vì method security được kích hoạt, lời gọi `reports.export()` đi qua Spring AOP proxy và được `@PreAuthorize("hasRole('ADMIN')")` cho phép. Test đồng thời xác minh **đúng kiểu principal** và **đúng quyền**.

**Test 2 — `bob`:** `bob` là người dùng hợp lệ và được load thành công, nhưng chỉ có `ROLE_VIEWER`. Vì thế test xác minh object principal được thiết lập thành công trước, rồi kiểm tra `reports.export()` ném `AccessDeniedException`. Đây là từ chối **authorization** ở tầng method; không phải lỗi không tìm thấy user hoặc sai mật khẩu.

**Test 3 — `shadow`:** username `"shadow"` không nằm trong `Map` của bean `accounts` nhưng `@WithMockUser` vẫn tạo authentication với `ROLE_ADMIN`. Phương thức được gọi thành công bởi rule chỉ kiểm tra role, còn principal không phải `AccountPrincipal`. Test nêu rõ khi nào `@WithMockUser` là đủ và khi nào nó có thể bỏ sót việc mã nghiệp vụ cần kiểu principal riêng.

Trong ví dụ, `{noop}test-only` chỉ là mật khẩu giả **nằm trong fixture test**; `@WithUserDetails` không xác minh giá trị này. Không dùng cấu hình `{noop}` để lưu mật khẩu thật trong production.

Ví dụ đặt `UserDetailsService` và `ReportService` trong cùng file test để có thể đọc, chạy và xác minh độc lập. Trong ứng dụng thực tế, nên **kiểm thử bean service thật**, dùng `UserDetailsService` thật hoặc fixture được kiểm soát, và tránh cấu hình test thay thế một cách vô tình quy tắc cần đánh giá.

## 4. Vai trò của `ApplicationContext` và tên bean

`@WithUserDetails` tìm bean có kiểu `UserDetailsService` trong **Spring Test `ApplicationContext`**. Vì ví dụ dùng:

```java
@Bean("accounts")
UserDetailsService accounts() {
    // Trả về service đọc các user trong fixture test.
}
```

nên annotation dùng:

```java
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "accounts"
)
```

Hai snippet này chỉ lấy ra phần cấu hình của ví dụ đầy đủ phía trên. Khi chỉ có một `UserDetailsService` phù hợp, có thể dùng dạng ngắn:

```java
@WithUserDetails("alice")
```

Khi có **nhiều bean** `UserDetailsService` (chẳng hạn `internalUsers`, `customerUsers`), cần xác định bean đúng bằng `userDetailsServiceBeanName` hoặc đảm bảo cơ chế chọn bean được cấu hình rõ ràng. Không đổi tên tùy tiện nếu muốn test chạy đúng cùng nguồn dữ liệu user mà nghiệp vụ cần.

Với ứng dụng lưu người dùng ở database, sơ đồ đúng là:

```text
Spring Test ApplicationContext
  └── UserDetailsService bean
        └── UserRepository bean
              └── database / fixture
                    └── bản ghi người dùng
```

`ApplicationContext` chứa bean service/repository; **bản ghi người dùng có thể nằm bên ngoài context**. Nếu service dựa vào dữ liệu thật của ứng dụng, hãy seed dữ liệu test trước lúc `@WithUserDetails` chạy. Không giả định việc thêm một bean có tên hợp lệ tự động tạo user tương ứng.

### Cần gì khi chỉ kiểm thử tầng phương thức?

- `spring-security-test` trên test classpath để có `@WithUserDetails`, `@WithMockUser` và test listener.
- Spring Test Context (trong ví dụ dùng `@SpringBootTest`) để có `ApplicationContext` và bean `UserDetailsService`.
- `@EnableMethodSecurity` trong cấu hình áp dụng cho context test nếu muốn kiểm chứng `@PreAuthorize`/`@PostAuthorize`. Spring Boot Starter Security không tự bật method security.
- Lời gọi đi qua **Spring-managed bean/proxy**. Tự `new ReportService()` hoặc gọi nội bộ `this.export()` trong cùng instance có thể không đi qua AOP advice, khiến phép thử phân quyền sai ý nghĩa.
- Quyền và thông tin domain trong đối tượng `UserDetails` cần khớp chính sách nghiệp vụ. Nếu hệ thống dùng role hierarchy hoặc biểu thức tùy biến, kiểm thử phải nạp cấu hình đó.

Không cần MockMvc khi đối tượng cần kiểm tra là **service method**. Với HTTP controller, MockMvc và Security Filter Chain là phạm vi kiểm thử khác; việc context của một test thread có authentication không có nghĩa một HTTP request chạy trên server ở thread khác đã đăng nhập.

## 5. Timing: `@WithUserDetails` chạy trước hay sau `@BeforeEach`?

Đây là lỗi rất dễ gặp khi fixture user được thêm trong phương thức chuẩn bị JUnit.

Mặc định, Spring Security Test thiết lập `SecurityContext` ở sự kiện `beforeTestMethod`, **trước** `@BeforeEach` của JUnit Jupiter. Do đó, trình tự có thể là:

```text
1. Spring Test context sẵn sàng
2. @WithUserDetails -> loadUserByUsername("late-user")
3. JUnit @BeforeEach -> tạo "late-user" trong repository
4. @Test -> chạy phần thân
```

Nếu user chỉ được thêm ở bước 3, bước 2 đã thất bại và test không chạy như mong đợi.

Giải pháp là chuyển thời điểm thiết lập security context sang `TEST_EXECUTION`:

```java
import org.springframework.security.test.context.support.TestExecutionEvent;
import org.springframework.security.test.context.support.WithUserDetails;

@Test
@WithUserDetails(
    value = "late-user",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
void shouldLoadUserCreatedInBeforeEach() {
    // Khi test bắt đầu, UserDetailsService đã có thể đọc "late-user".
}
```

Đây là **snippet minh họa lifecycle**, giả định có test class cấu hình Spring và `@BeforeEach` đã tạo user `"late-user"` vào nguồn dữ liệu đúng với bean `UserDetailsService`. Đoạn này không phải class Java chạy độc lập.

Khi đó, trình tự trở thành:

```text
1. Spring Test context sẵn sàng
2. JUnit @BeforeEach -> tạo user
3. @WithUserDetails -> loadUserByUsername(...)
4. @Test -> chạy phần thân
```

Với dữ liệu được tạo bằng `@Sql`, repository hoặc transaction trong test, phải xác nhận thời điểm fixture được commit/nhìn thấy bởi `UserDetailsService`. `TEST_EXECUTION` chỉ giải quyết **thứ tự callback**, không tự giải quyết transaction isolation, cache hay kết nối tới database. Thực tế nên ưu tiên fixture được tạo ổn định ở đúng giai đoạn chuẩn bị context/test; chỉ đổi `setupBefore` khi cần.

## 6. Phân biệt ba loại lỗi khi chạy test

| Triệu chứng | Nguyên nhân thường gặp | Hướng xác minh |
| --- | --- | --- |
| Test không vào phần thân, báo không tìm thấy username | `@WithUserDetails` gọi service nhưng fixture user chưa tồn tại hoặc tra sai nguồn | Kiểm tra `loadUserByUsername`, username, dữ liệu fixture, thời điểm `setupBefore` |
| Không tìm thấy hoặc chọn nhầm `UserDetailsService` | Chưa nạp đúng bean vào `ApplicationContext`, nhiều bean cùng kiểu, sai `userDetailsServiceBeanName` | Kiểm tra cấu hình context và bean name chính xác |
| Test chạy nhưng `@PreAuthorize` từ chối | Principal đã load nhưng authorities không đủ hoặc biểu thức/quy tắc không khớp | Kiểm tra `getAuthorities()`, `ROLE_` prefix, cấu hình method security |
| Test sai kiểu principal (`ClassCastException`) | Dùng `@WithMockUser` trong mã yêu cầu principal domain tùy biến | Dùng `@WithUserDetails` với service trả về đúng `UserDetails` |
| `@PreAuthorize` dường như không có tác dụng | Chưa bật `@EnableMethodSecurity`, đối tượng không phải Spring bean hoặc gọi method không qua proxy | Kiểm tra cấu hình và cách lấy bean trong test |
| Test pass nhưng HTTP thật bị từ chối | Annotation chỉ cấp `SecurityContext` cho môi trường test; request server không được xác thực theo cùng cách | Test riêng HTTP login/token/cookie và filter chain thực tế |

`@WithUserDetails` không biến một principal hợp lệ thành principal **đủ quyền**. User có thể tồn tại nhưng thiếu `ROLE_ADMIN`, và từ chối trong `@PreAuthorize` lúc này là kết quả kiểm thử đúng.

Cũng không nên coi `AccessDeniedException` từ method security tương đương với **HTTP 403** trong mọi hoàn cảnh. Trong test gọi trực tiếp service, ta assert exception; HTTP status chỉ xuất hiện khi có HTTP layer, filter/exception translation hoặc exception handler phù hợp.

## 7. Những lỗi thiết kế test cần tránh

**Giả định user chỉ cần trùng tên:** annotation sẽ gọi `loadUserByUsername`; nếu service không có user hoặc dữ liệu không khả dụng, test thất bại trong khâu chuẩn bị. Chỉ `@WithMockUser` mới cho phép tạo principal giả mà không cần bản ghi.

**Dùng mock principal cho logic phụ thuộc custom principal:** nếu code truy cập `((AccountPrincipal) authentication.getPrincipal()).accountId()`, `@WithMockUser` không đại diện đúng kiểu trả về từ service. Test nên dùng `@WithUserDetails` và xác minh kiểu dữ liệu.

**Bỏ qua quyền lấy từ service:** `.roles("ADMIN")` của `@WithMockUser` có thể giúp test pass nhưng không kiểm tra `UserDetailsService` thật sự gán `ROLE_ADMIN` cho user; dùng `@WithUserDetails` khi sự khác biệt đó quan trọng.

**Để dữ liệu fixture thay đổi giữa các test:** context của Spring có thể được cache giữa test class; in-memory store hoặc DB dùng chung có thể gây phụ thuộc thứ tự chạy. Tạo dữ liệu xác định, dọn dẹp đúng cách và không dùng chung user mutable giữa các test nếu test thay đổi trạng thái.

**Nhầm authentication giả lập với việc test mật khẩu:** `@WithUserDetails` xây dựng context đã xác thực phục vụ test; nó không chạy `DaoAuthenticationProvider`, password encoder hay login endpoint. Muốn kiểm thử xác thực thật, phải viết test riêng cho authentication flow.

**Tự gọi method trong cùng class service:** Spring AOP proxy thường chỉ chặn lời gọi đi qua proxy. Self-invocation có thể bỏ qua `@PreAuthorize`; một test chỉ chạy `new` hoặc gọi nội bộ có thể cho kết luận sai.

**Tin rằng `@WithUserDetails` lan sang mọi thread:** test context thường gắn với thread thực hiện phép thử. Task bất đồng bộ và HTTP gọi tới server chạy ở thread khác cần chiến lược truyền `SecurityContext` hoặc xác thực request riêng; annotation không tự bảo đảm điều đó.

**Cho rằng có `@SpringBootTest` là method security được bật:** hãy kiểm tra `@EnableMethodSecurity` và sự hiện diện của bean dưới AOP proxy. Nếu muốn test cả rule tùy biến, phải nạp đúng security configuration.

## 8. Checklist kiểm thử method security bằng user từ context

- [ ] Có bean `UserDetailsService` hợp lệ trong `ApplicationContext` của test.
- [ ] Username trong `@WithUserDetails` thực sự tồn tại trong nguồn mà bean truy cập.
- [ ] Nếu nhiều service, `userDetailsServiceBeanName` chỉ đúng bean.
- [ ] Nếu fixture được tạo trong `@BeforeEach`, cân nhắc `setupBefore = TEST_EXECUTION`.
- [ ] Xác minh `Authentication.getPrincipal()` có đúng kiểu custom principal và thuộc tính domain cần kiểm tra.
- [ ] Kiểm tra cả user **được phép** và user **bị từ chối**; với lời gọi service, assert giá trị hoặc exception tương ứng.
- [ ] `@EnableMethodSecurity` được bật và lời gọi đi qua Spring-managed bean/proxy.
- [ ] Hiểu rõ test đang xác minh method authorization; không diễn giải nó như test đăng nhập, password hoặc HTTP response.
- [ ] Dữ liệu fixture độc lập, lặp lại được và không lệ thuộc thứ tự test.

## Tài liệu chính thức

- [Spring Security — Testing Method Security (`@WithMockUser`, `@WithUserDetails`)](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — Method Security (`@EnableMethodSecurity`, `@PreAuthorize`)](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Authentication in MockMvc Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
