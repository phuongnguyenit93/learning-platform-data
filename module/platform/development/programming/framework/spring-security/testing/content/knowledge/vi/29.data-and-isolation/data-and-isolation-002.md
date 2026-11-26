# Tạo dữ liệu trước đúng thời điểm `@WithUserDetails` được xử lý

## 1. Tình huống: tạo người dùng trong `@BeforeEach` nhưng test vẫn báo không tìm thấy

Trong Spring Security Test, `@WithUserDetails` giúp viết một test chạy với **người dùng đã được tải từ `UserDetailsService`**, thay vì tự tạo principal có username và quyền bằng `@WithMockUser`.

Một ca thường gặp là:

~~~java
@BeforeEach
void setUp() {
    users.createUser(
        User.withUsername("alice")
            .password("{noop}test-password")
            .roles("AUDITOR")
            .build());
}

@Test
@WithUserDetails("alice")
void canReadAuditLog() {
    // ...
}
~~~

Mặc dù `@BeforeEach` đã có logic tạo `alice`, test có thể thất bại **trước khi chạy đến phương thức `setUp()`**. Nguyên nhân: thời điểm mặc định của `@WithUserDetails` là `TestExecutionEvent.TEST_METHOD`, nghĩa là `WithSecurityContextTestExecutionListener` dựng `SecurityContext` **trước callback `@BeforeEach` của JUnit Jupiter**.

Đây là chủ đề trọng tâm của chương **Dữ liệu và cô lập** trong module `SPRING_SECURITY_TESTING`: kiểm thử xác thực, phân quyền và bảo vệ HTTP thực tế với Spring Security Test trên Servlet và Reactive. Muốn test ổn định, cần biết **ai tạo dữ liệu, khi nào tạo, ai đọc dữ liệu và khi nào dọn dữ liệu**.

Sau bài này, người học sẽ có thể:

1. Mô tả chính xác vòng đời `@WithUserDetails`, `@BeforeEach` và các callback của Spring Test.
2. Dùng `setupBefore = TestExecutionEvent.TEST_EXECUTION` để cho phép fixture được tạo trong `@BeforeEach` trước khi Spring Security tải người dùng.
3. Viết test với `InMemoryUserDetailsManager` và `StepVerifier`/`MockMvc` phù hợp mục tiêu.
4. Lựa chọn giữa tạo dữ liệu tại `@BeforeEach`, `@BeforeAll`, `@Sql` hoặc fixture có sẵn.
5. Tránh dữ liệu rò rỉ giữa các test, ảnh hưởng do transaction và lỗi khi chạy song song.
6. Phân biệt **tải `UserDetails`** với **xác minh mật khẩu, JWT/OAuth2/OIDC hay một request HTTP thật**.

## 2. `@WithMockUser` khác `@WithUserDetails` thế nào?

| Cơ chế | Principal được tạo từ đâu? | Có gọi `UserDetailsService`? | Kiểm tra password thật? |
| --- | --- | --- | --- |
| `@WithMockUser(username = "alice", roles = "AUDITOR")` | Spring Security Test tạo authentication giả theo annotation | Không | Không |
| `@WithUserDetails("alice")` | Spring Security Test gọi `UserDetailsService.loadUserByUsername("alice")` rồi dựng authentication | **Có** | Không |
| `MockMvc` gửi form login thật | Các authentication filters, manager và provider đã cấu hình | Có thể có, tùy cơ chế | Có, nếu thực sự dùng password authentication |
| `WebTestClient` gửi HTTP Basic/Bearer thật | Security filter chain và authentication manager/decoder | Tùy cơ chế, có thể dùng reactive service | Có với Basic; JWT thì xác minh theo decoder/validator |

`@WithUserDetails` hữu ích khi cần:

- Kiểm tra quyền mà ứng dụng **thực sự cấp từ `UserDetailsService`**.
- Sử dụng `UserDetails` tùy biến chứa ID, tenant, trạng thái tài khoản hoặc các thuộc tính nội bộ.
- Tránh viết lại `roles`/`authorities` thủ công cho từng test.

Tuy nhiên, `@WithUserDetails` **không nhập mật khẩu rồi đi qua cơ chế xác thực**. Nó gọi `loadUserByUsername` để lấy người dùng và đặt authentication cho test. Vì vậy, không dùng test thành công với `@WithUserDetails` để kết luận mật khẩu được hash đúng, tài khoản khóa bị từ chối lúc login, token JWT còn hạn hoặc OAuth2/OIDC đã xác minh IdP.

## 3. Vòng đời thực tế: sự khác nhau giữa `TEST_METHOD` và `TEST_EXECUTION`

Spring TestContext có các callback riêng. Với JUnit Jupiter và Spring Security Test listener mặc định, trình tự quan trọng là:

~~~mermaid
flowchart TD
    A["Spring TestContext chuẩn bị test instance"] --> B["beforeTestMethod của TestExecutionListener"]
    B --> C["JUnit @BeforeEach"]
    C --> D["beforeTestExecution của TestExecutionListener"]
    D --> E["JUnit @Test: gọi method / HTTP assertions"]
    E --> F["afterTestExecution"]
    F --> G["JUnit @AfterEach"]
    G --> H["afterTestMethod; Spring Security dọn context"]
~~~

`WithSecurityContextTestExecutionListener` có thể tạo `SecurityContext` ở hai thời điểm:

| `@WithUserDetails.setupBefore` | Thời điểm Spring Security tải người dùng | Fixture nào có thể đã tồn tại? |
| --- | --- | --- |
| **`TestExecutionEvent.TEST_METHOD`** (mặc định) | Trong `beforeTestMethod` | Dữ liệu khởi tạo trước test, `@BeforeAll` hoặc một fixture được chuẩn bị sớm hơn listener |
| **`TestExecutionEvent.TEST_EXECUTION`** | Trong `beforeTestExecution`, sau `@BeforeEach` | Bao gồm dữ liệu vừa tạo bởi `@BeforeEach` của test hiện tại |

Với fixture được tạo trong `@BeforeEach`, giải pháp rõ ràng là:

~~~java
import org.springframework.security.test.context.support.WithUserDetails;
import org.springframework.security.test.context.support.TestExecutionEvent;

@Test
@WithUserDetails(
    value = "alice",
    setupBefore = TestExecutionEvent.TEST_EXECUTION)
void canReadAuditLog() {
    // @BeforeEach đã tạo alice trước khi listener tải UserDetails.
}
~~~

**Tại sao không chỉ di chuyển `@BeforeEach` lên phía trên annotation trong file?** Thứ tự **các dòng mã nguồn** không quyết định thứ tự callback. Spring Test và JUnit kích hoạt callback dựa trên vòng đời, không dựa trên vị trí khai báo phương thức.

### 3.1. Điều gì xảy ra khi test chạy?

Giả sử `UserDetailsService.loadUserByUsername("alice")` chỉ trả về người dùng nếu dữ liệu đã được tạo. Với cấu hình mặc định:

1. Spring Security Test listener cố tải `alice` tại `beforeTestMethod`.
2. Vì `@BeforeEach` chưa chạy, repository chưa có `alice`.
3. `loadUserByUsername` ném `UsernameNotFoundException` hoặc service trả lỗi tương ứng.
4. Test thất bại trước khi thực hiện assertion nghiệp vụ.

Khi đổi sang `TEST_EXECUTION`:

1. Spring gọi `beforeTestMethod` nhưng listener chưa tải user.
2. JUnit chạy `@BeforeEach`: tạo `alice` trong store.
3. Spring gọi `beforeTestExecution`: listener đọc `alice` từ `UserDetailsService`.
4. Test chạy với `SecurityContext` chứa authentication của `alice`.
5. Cuối test, Spring Security Test dọn context; việc xóa **dữ liệu fixture** vẫn là trách nhiệm riêng của test.

**Điểm tinh tế:** `@WithUserDetails` tải một snapshot `UserDetails` ở thời điểm setup. Nếu sửa quyền hoặc xóa user **sau khi** authentication đã được tạo, `SecurityContext` trong test không tự động được tải lại từ repository.

## 4. Ví dụ tự chứa: `InMemoryUserDetailsManager` và method security

Đây là ví dụ phù hợp để hiểu thời điểm setup mà không cần database hay HTTP server.

### 4.1. Cấu hình `UserDetailsService` và service cần phân quyền

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration
        .EnableMethodSecurity;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
class FixtureSecurityConfig {

    @Bean("userDetailsService")
    InMemoryUserDetailsManager userDetailsService() {
        // Cố tình để rỗng: test sẽ tạo user trong @BeforeEach.
        return new InMemoryUserDetailsManager();
    }

    @Bean
    AuditService auditService() {
        return new AuditService();
    }
}
~~~

Service dùng authority `AUDIT_READ` và đọc principal hiện tại:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.SecurityContextHolder;

class AuditService {

    @PreAuthorize("hasAuthority('AUDIT_READ')")
    public String readAuditLog() {
        String username = SecurityContextHolder.getContext()
                .getAuthentication()
                .getName();
        return "audit-for-" + username;
    }
}
~~~

`@EnableMethodSecurity` giúp Spring đăng ký các advisor/proxy áp dụng `@PreAuthorize`. Test phải **inject bean `AuditService` từ Spring**, không tự gọi `new AuditService()` rồi kỳ vọng method security được thực thi.

### 4.2. Test có fixture được tạo đúng lúc

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.test.context.support.TestExecutionEvent;
import org.springframework.security.test.context.support.WithUserDetails;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(classes = FixtureSecurityConfig.class)
class WithUserDetailsTimingTests {

    @Autowired
    InMemoryUserDetailsManager users;

    @Autowired
    AuditService audits;

    @BeforeEach
    void createFixtureUsers() {
        // Chủ động làm sạch nếu test context tái sử dụng store.
        deleteIfPresent("alice");
        deleteIfPresent("bob");

        users.createUser(User.withUsername("alice")
                .password("{noop}unused-test-password")
                .authorities("AUDIT_READ")
                .build());
        users.createUser(User.withUsername("bob")
                .password("{noop}unused-test-password")
                .authorities("PROFILE_READ")
                .build());
    }

    @AfterEach
    void removeFixtureUsers() {
        deleteIfPresent("alice");
        deleteIfPresent("bob");
    }

    private void deleteIfPresent(String username) {
        if (users.userExists(username)) {
            users.deleteUser(username);
        }
    }

    @Test
    @WithUserDetails(
        value = "alice",
        userDetailsServiceBeanName = "userDetailsService",
        setupBefore = TestExecutionEvent.TEST_EXECUTION)
    void userLoadedAfterBeforeEachCanReadAudit() {
        assertEquals("audit-for-alice", audits.readAuditLog());
    }

    @Test
    @WithUserDetails(
        value = "bob",
        userDetailsServiceBeanName = "userDetailsService",
        setupBefore = TestExecutionEvent.TEST_EXECUTION)
    void userLoadedAfterBeforeEachStillNeedsAuthority() {
        assertThrows(AccessDeniedException.class, audits::readAuditLog);
    }
}
~~~

Hai test kiểm tra những điều riêng biệt:

- `alice` tồn tại ở thời điểm listener tải user, có `AUDIT_READ` nên được phép gọi service.
- `bob` cũng tồn tại và được tải thành công, nhưng chỉ có `PROFILE_READ` nên **bị từ chối bởi method security**, không phải do thiếu dữ liệu.

Việc có một **ca tải thành công nhưng thiếu quyền** giúp phân biệt lỗi setup fixture với lỗi authorization. Nếu chỉ có test user không tồn tại, bạn không biết policy có thực sự được chạy hay chưa.

### 4.3. Vì sao phải chỉ định `userDetailsServiceBeanName`?

`@WithUserDetails` có thể tìm `UserDetailsService` theo cấu hình mặc định. Khi application có nhiều `UserDetailsService`, việc chỉ rõ bean name làm test bớt mơ hồ:

~~~java
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "userDetailsService",
    setupBefore = TestExecutionEvent.TEST_EXECUTION)
~~~

Nếu test có nhiều data source, tenant hoặc user-detail services, đừng để test tình cờ đọc sai store. Cần kiểm tra đúng bean mà luồng authorization liên quan thực tế sử dụng.

## 5. Ví dụ sai để nhận diện lỗi thời điểm

Trong cùng lớp test và fixture tạo trong `@BeforeEach`, đoạn sau là **anti-pattern**:

~~~java
@Test
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "userDetailsService")
void flakyOrFailingSetup() {
    assertEquals("audit-for-alice", audits.readAuditLog());
}
~~~

Vì không chỉ định `setupBefore`, Spring Security Test dùng `TEST_METHOD`. Nếu store đang rỗng khi `beforeTestMethod` chạy, user chưa tồn tại và test thất bại; nếu một test trước đó tình cờ để lại `alice`, test có thể xanh, tạo **thất bại phụ thuộc thứ tự**.

Đừng chữa bằng cách bắt `UsernameNotFoundException` rồi bỏ qua assertion. Đây không phải lỗi cần được lờ đi; test phải bảo đảm dữ liệu tồn tại **trước thời điểm listener tải**.

### 5.1. Không phải mọi dữ liệu đều nên tạo ở `@BeforeEach`

Giữ `setupBefore = TEST_METHOD` vẫn đúng nếu người dùng đã tồn tại trước `beforeTestMethod`, chẳng hạn:

- Fixture được nạp khi tạo Spring test context, trước mỗi test.
- Người dùng có sẵn từ test dataset độc lập, ổn định.
- Dữ liệu được tạo bằng một callback sớm hơn `beforeTestMethod` và không phụ thuộc test khác.

Không bắt buộc mọi test đổi sang `TEST_EXECUTION`. Quyết định phụ thuộc vòng đời tạo fixture và loại dữ liệu cần kiểm thử.

## 6. Khi dùng cơ sở dữ liệu thay vì store trong bộ nhớ

Ở ứng dụng thật, `UserDetailsService` thường truy vấn database, LDAP, hoặc tích hợp kho danh tính riêng. Với Spring Security JDBC user store thông thường, bạn có thể có các bảng `users` và `authorities`; một `JdbcUserDetailsManager` hoặc `JdbcDaoImpl` đọc các hàng đó.

Trong môi trường test có schema chuẩn và `JdbcUserDetailsManager` được cấu hình, fixture có thể được tạo bằng `JdbcTemplate` ở `@BeforeEach`:

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

class JdbcUserFixture {

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void seedUser() {
        clearUser();
        jdbc.update(
            "INSERT INTO users(username, password, enabled) "
                + "VALUES (?, ?, ?)",
            "case-alice", "{noop}not-used", true);
        jdbc.update(
            "INSERT INTO authorities(username, authority) VALUES (?, ?)",
            "case-alice", "AUDIT_READ");
    }

    @AfterEach
    void cleanupUser() {
        clearUser();
    }

    private void clearUser() {
        jdbc.update("DELETE FROM authorities WHERE username = ?",
                "case-alice");
        jdbc.update("DELETE FROM users WHERE username = ?",
                "case-alice");
    }
}
~~~

Đoạn code **giả định schema Spring Security JDBC tương ứng đã tồn tại** và application đã đăng ký `UserDetailsService` đọc từ các bảng đó. Đây là một lựa chọn fixture, không phải yêu cầu tạo thêm schema/file mới cho bài học.

Test sử dụng cùng database cần chỉ rõ service:

~~~java
@Test
@WithUserDetails(
    value = "case-alice",
    userDetailsServiceBeanName = "databaseUserDetailsService",
    setupBefore = TestExecutionEvent.TEST_EXECUTION)
void loadsDatabaseUserCreatedInBeforeEach() {
    // Gọi bean hoặc HTTP endpoint được bảo vệ bằng AUDIT_READ.
}
~~~

Tên `databaseUserDetailsService` phải khớp **bean thật** trong dự án; đừng sao chép tên minh họa rồi giả định Spring Boot tự tạo bean ấy.

Nếu repository dùng JPA, MongoDB hoặc một user-details adapter tùy biến, ý tưởng không đổi: tạo và flush dữ liệu đúng lúc, xác nhận service nhìn thấy nó, rồi mới để listener tải `UserDetails`.

### 6.1. Tạo dữ liệu nhưng quên flush

Với ORM/JPA, gọi `repository.save(...)` chưa luôn đồng nghĩa mọi truy vấn qua transaction/connection khác sẽ nhìn thấy thay đổi. Trong test dùng cùng transaction, ORM có thể flush trước truy vấn; trong test khác transaction hoặc qua HTTP server thật, cần quan tâm cả flush **và commit**.

Đừng cố giải quyết mọi lỗi bằng `flush()`: **flush không tương đương commit**. Nếu request chạy ở transaction khác thì dữ liệu chưa commit vẫn có thể vô hình, bất kể đã flush trong test.

## 7. `@Sql` và thứ tự Spring Test listeners

Spring Test có `@Sql` để chuẩn bị/thu hồi dữ liệu SQL theo phase. Ví dụ khi dự án **đã có sẵn** script fixture:

~~~java
@Sql(
    scripts = "/sql/seed-security-users.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
@Test
@WithUserDetails(
    value = "seeded-alice",
    setupBefore = TestExecutionEvent.TEST_EXECUTION)
void usesSqlSeededUser() {
    // ...
}
~~~

Đoạn này có tính minh họa: cần có script thật trong classpath, schema tương ứng và `UserDetailsService` trỏ đến database đó. Bài học hiện tại **không tạo hoặc đọc một SQL fixture bổ sung**.

`SqlScriptsTestExecutionListener` thường xử lý `@Sql` ở phase `BEFORE_TEST_METHOD`. Với `@WithUserDetails(setupBefore = TEST_EXECUTION)`, thời điểm tải user rõ ràng nằm **sau `@BeforeEach`** và sau các thao tác `BEFORE_TEST_METHOD` đã hoàn tất.

Trong một số cấu hình phổ biến, `@Sql(BEFORE_TEST_METHOD)` cũng chạy trước `@WithUserDetails` mặc định nhờ thứ tự listeners. Tuy nhiên không nên dựa một cách vô điều kiện vào kết quả đó nếu test có:

- `@TestExecutionListeners` tùy biến hoặc thay thế listeners mặc định.
- `@SqlConfig` riêng với transaction manager khác.
- Script SQL phụ thuộc lifecycle của application hoặc context.
- Nhiều data sources có transaction và schema khác nhau.

**Quy tắc dễ hiểu và ổn định:** nếu dữ liệu phải được tạo bằng `@BeforeEach`, chọn `TEST_EXECUTION`. Nếu muốn dùng `@Sql`, xác nhận chính xác phase chạy script, schema, transaction và listener đang kích hoạt trong dự án.

### 7.1. Đừng vô tình tắt listener của Spring Security

Khi tự khai báo `@TestExecutionListeners`, chế độ thay thế danh sách mặc định có thể làm mất `WithSecurityContextTestExecutionListener`. Khi đó `@WithUserDetails` không được xử lý như mong đợi, hoặc context không được thiết lập/thu hồi đúng.

Nếu cần thêm listener tùy biến, ưu tiên merge với defaults:

~~~java
@TestExecutionListeners(
    listeners = CustomFixtureListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
~~~

Trong ví dụ trên, `CustomFixtureListener` là một listener **do dự án tự định nghĩa**; chỉ dùng annotation này khi thật sự cần. Không thêm listener chỉ để vượt qua vấn đề có thể giải bằng `setupBefore = TEST_EXECUTION`.

## 8. Test transaction, rollback và giới hạn dữ liệu nhìn thấy

`@Transactional` trong Spring Test thường mở một **test-managed transaction** cho từng phương thức test. Các thao tác trong `@BeforeEach` có thể tham gia transaction đó, và sau test dữ liệu có thể được rollback.

Tuy nhiên, cần phân biệt:

| Bối cảnh | Dữ liệu mới tạo trong `@BeforeEach` có thể thấy? | Cách cô lập |
| --- | --- | --- |
| `@WithUserDetails(TEST_EXECUTION)` tải user cùng test thread/transaction | Thường có, nếu cùng datasource và transaction phù hợp | Rollback hoặc cleanup |
| Gọi bean Spring trực tiếp trong test | Thường có, với transaction tương ứng | Rollback, fixture riêng |
| `MockMvc` qua mock Servlet request trong cùng luồng thực thi test | Có thể cùng transaction của test trong cấu hình thông thường | Xác nhận transaction boundary |
| `@SpringBootTest(RANDOM_PORT)` gửi HTTP thật | Server xử lý ở thread/transaction khác; **không thấy dữ liệu chưa commit** theo isolation thông thường | Commit fixture trước request; cleanup độc lập |
| Reactive WebFlux xử lý bất đồng bộ | Ngữ cảnh transaction và thread phụ thuộc Reactive transaction manager/pipeline | Kiểm soát transaction, fixture đã commit |
| User store nằm ở dịch vụ ngoài | Phụ thuộc kết nối và state của dịch vụ | Fixture có namespace riêng và cleanup đáng tin |

Một lỗi dễ gặp:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class RealHttpUserTests {
    @BeforeEach
    void createUser() {
        // Ghi user trong transaction của thread test, chưa commit.
    }

    @Test
    void loginOverHttp() {
        // HTTP server có transaction khác, có thể không thấy user.
    }
}
~~~

**Nguyên tắc:** rollback của test không tự động áp dụng cho các giao dịch do server HTTP thật thực hiện ở thread khác. Khi test cần đi qua network boundary, hãy chuẩn bị fixture **đã commit** (bằng transaction setup tách biệt phù hợp), sau đó dọn bằng lệnh/tài khoản fixture tương ứng. Đừng gắn `@Commit` tràn lan để chữa test chập chờn mà không có kế hoạch cleanup.

### 8.1. Chú ý dữ liệu bên ngoài transaction

Việc tạo user trong `InMemoryUserDetailsManager`, Redis, cache, một mock identity service hoặc hệ thống LDAP thử nghiệm **không được rollback bởi transaction của JDBC/JPA**. Phải tự dọn dữ liệu, thay thế instance, hoặc dùng fixture có vòng đời được quản lý rõ ràng.

Ngược lại, xóa user khỏi database sau test không đồng nghĩa principal đã được xóa khỏi các session đang tồn tại; những session/authentication test cần được xử lý riêng.

## 9. Cô lập dữ liệu để không có test phụ thuộc thứ tự

Spring TestContext thường **cache application context** để giảm thời gian khởi động. Các bean in-memory, cache và datasource được nạp trong context ấy có thể được tái sử dụng giữa nhiều test methods hoặc test classes.

Nếu test A tạo `alice` mà không dọn, test B dùng `@WithUserDetails("alice")` mặc định có thể xanh dù không hề tự tạo fixture. Khi chạy riêng test B, nó lại thất bại. Đây là lỗi **order-dependence** đặc trưng của dữ liệu test.

Các nguyên tắc áp dụng:

1. Mỗi test tự chuẩn bị dữ liệu cần thiết, hoặc khai báo rõ fixture chung bất biến.
2. Dùng username/ID chuyên biệt cho fixture (`alice-security-case-01`) để tránh va chạm với dữ liệu khác.
3. Dọn dữ liệu theo thứ tự an toàn (authorities/quan hệ phụ thuộc trước users nếu schema yêu cầu).
4. Không dựa vào test chạy trước để tạo user hoặc authority.
5. Tách kiểm thử dữ liệu và kiểm thử phân quyền: thêm ca user tồn tại nhưng thiếu authority.
6. Giữ quyền tối thiểu trong fixture; đừng cấp `ROLE_ADMIN` cho mọi test để “dễ xanh”.
7. Kiểm soát session, cache và authentication của test; dọn database không tự xóa `SecurityContext` đã được đặt.

### 9.1. Test chạy song song cần chiến lược rõ ràng

`@BeforeEach`/`@AfterEach` không phải cơ chế đồng bộ nếu hai test chạy đồng thời và cùng sửa `users["alice"]`:

~~~text
Test A: tạo alice có AUDIT_READ
Test B: xóa alice, tạo alice có PROFILE_READ
Test A: listener tải alice → có quyền của B hoặc không còn user
~~~

Vì `@WithUserDetails` dùng username tĩnh trong annotation, tạo một username động hoàn toàn ngẫu nhiên **cho mỗi lần chạy** không thuận tiện. Các lựa chọn hợp lý:

- Dùng một username **riêng cho từng test method** đã biết trước.
- Dùng một test database/schema hoặc in-memory service instance riêng cho lớp test cần cô lập cao.
- Tắt thực thi song song **cho nhóm test dùng chung mutable fixture**, hoặc khóa tài nguyên test dùng chung theo quy định của JUnit.
- Dùng `@DirtiesContext` khi thật sự cần dựng lại context, chấp nhận chi phí khởi tạo lớn; đây không nên là giải pháp đầu tiên cho dữ liệu không được dọn.

Chỉ dùng `@BeforeEach` xóa rồi tạo lại cùng user chưa đủ bảo đảm an toàn trong **parallel execution**. Test ổn định khi chạy tuần tự vẫn có thể race khi chạy song song.

## 10. `@WithUserDetails` có ý nghĩa gì với `MockMvc`?

Đối với ứng dụng Servlet, `MockMvc` có thể kiểm tra HTTP security cùng với `@WithUserDetails`. Giả sử có controller:

~~~java
@RestController
class AuditController {

    private final AuditService auditService;

    AuditController(AuditService auditService) {
        this.auditService = auditService;
    }

    @GetMapping("/api/audit")
    String audit() {
        return auditService.readAuditLog();
    }
}
~~~

Một test Spring Boot với MockMvc, đã nạp controller, security filters và `UserDetailsService`:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AuditHttpSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    InMemoryUserDetailsManager users;

    @BeforeEach
    void seedUser() {
        if (users.userExists("alice")) {
            users.deleteUser("alice");
        }
        users.createUser(User.withUsername("alice")
            .password("{noop}unused-test-password")
            .authorities("AUDIT_READ")
            .build());
    }

    @AfterEach
    void cleanup() {
        if (users.userExists("alice")) {
            users.deleteUser("alice");
        }
    }

    @Test
    @WithUserDetails(
        value = "alice",
        setupBefore = TestExecutionEvent.TEST_EXECUTION)
    void auditEndpointAllowsLoadedUser() throws Exception {
        mockMvc.perform(get("/api/audit"))
                .andExpect(status().isOk())
                .andExpect(content().string("audit-for-alice"));
    }
}
~~~

Ví dụ sử dụng `@AutoConfigureMockMvc` để tích hợp filter chain của ứng dụng. Với `MockMvcBuilders.webAppContextSetup(...)` thủ công, cần áp dụng `springSecurity()` và hỗ trợ test security context phù hợp. Thêm imports của JUnit, Spring Boot Test, `MockMvcRequestBuilders.get` và `MockMvcResultMatchers` tương ứng.

Ở ca này, authentication được **listener đặt sẵn** cho MockMvc request; test không chứng minh form login hay HTTP Basic đã kiểm tra password. Nó chứng minh Spring MVC/security filters và quyền ứng dụng chấp nhận một principal được tải từ `UserDetailsService`.

Nếu ứng dụng dùng form login và muốn kiểm tra **mật khẩu hoặc session login thật**, cần một test riêng gửi form credentials và CSRF token qua `MockMvc`, không dựa vào `@WithUserDetails` để coi như đã login thật.

## 11. Điều gì thay đổi với WebFlux và `WebTestClient`?

Trong Reactive, Spring Security truyền authentication qua **Reactor Context**. Spring Security Test hỗ trợ `@WithMockUser` và các test mutators như `mockUser()`, `mockJwt()` và `mockOidcLogin()` cho `WebTestClient` gắn mock WebFlux context.

`@WithUserDetails` được thiết kế để gọi một **`UserDetailsService` đồng bộ**. Đừng mặc định nó tự gọi `ReactiveUserDetailsService.findByUsername(...)` của ứng dụng WebFlux: đó là interface khác. Nếu ứng dụng chỉ có `ReactiveUserDetailsService`, cần chọn một chiến lược test phù hợp với cơ chế Reactive đang dùng.

Ví dụ kiểm tra **policy** Reactive bằng danh tính giả:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

webTestClient.mutateWith(mockUser("alice")
        .authorities(new SimpleGrantedAuthority("AUDIT_READ")))
    .get()
    .uri("/api/audit")
    .exchange()
    .expectStatus().isOk();
~~~

Ví dụ trên chỉ đúng khi test đang có WebFlux route và `SecurityWebFilterChain` tương ứng, và WebTestClient đã được tích hợp Spring Security Test (chẳng hạn thông qua `bindToApplicationContext(...).apply(springSecurity())`). Nó **không** chứng minh người dùng được tìm thấy trong `ReactiveUserDetailsService`.

Muốn kiểm tra Reactive authentication thực tế, cấu hình `ReactiveUserDetailsService`/`ReactiveAuthenticationManager` thật rồi gửi HTTP Basic credentials đến endpoint:

~~~java
webTestClient.get()
    .uri("/api/audit")
    .headers(headers -> headers.setBasicAuth(
        "alice", "correct-test-password"))
    .exchange()
    .expectStatus().isOk();
~~~

Thêm ca password sai mong đợi `401` theo HTTP Basic entry point. Test đó mới kiểm tra luồng xác thực Reactive đang dùng `ReactiveUserDetailsService`, thay vì dùng annotation tạo sẵn authentication.

Khi test `WebTestClient.bindToServer()` qua `RANDOM_PORT`, `@WithUserDetails` trong thread JUnit cũng không thể **tự chuyển authentication qua network**. Phải gửi headers, cookies hoặc bearer token thật theo cơ chế của server.

## 12. Các tình huống lỗi và cách khoanh vùng

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `UsernameNotFoundException` dù `@BeforeEach` có createUser | `@WithUserDetails` được xử lý ở `TEST_METHOD`, trước `@BeforeEach` | Đặt `setupBefore = TEST_EXECUTION` |
| Test chỉ xanh khi chạy cả lớp, chạy riêng thất bại | Dựa vào user do test trước tạo | Fixture độc lập và cleanup |
| Test chạy song song lúc xanh lúc đỏ | Hai test dùng chung username/store mutable | Username riêng, context/database tách hoặc quản lý parallel |
| `@WithUserDetails` tìm sai `UserDetailsService` | Có nhiều beans hoặc bean name chưa đúng | Đặt `userDetailsServiceBeanName` chính xác |
| User được tải nhưng vẫn nhận `403` | Authorities không đủ, `@PreAuthorize` từ chối | Kiểm tra quyền thực trả từ service |
| Test load user được nhưng login thật vẫn lỗi | Annotation bỏ qua password authentication | Thêm test login đúng/sai mật khẩu |
| `@Transactional` đã save, HTTP thật vẫn không thấy user | Test transaction chưa commit, server dùng transaction khác | Seed và commit fixture trước HTTP request |
| `save()` JPA không giúp test khác thấy user | Flush/commit chưa phù hợp | Xác nhận transaction boundaries; đừng nhầm flush với commit |
| `@Sql` đã chạy nhưng listener vẫn không thấy dữ liệu | Sai data source, phase, listener order hoặc transaction | Kiểm tra `@Sql` setup và chọn thời điểm setup tường minh |
| Test context không áp dụng `@WithUserDetails` | Spring Security listener bị loại khi tùy biến `@TestExecutionListeners` | Merge với default listeners |
| User bị xóa ở `@AfterEach` nhưng test khác vẫn thấy | Cache, session hoặc fixture khác còn tồn tại | Dọn đúng store/cache và cô lập test |
| `@WithUserDetails` dùng trong Reactive không tải được user | Ứng dụng chỉ cung cấp `ReactiveUserDetailsService` | Test bằng `mockUser()` cho policy hoặc HTTP Basic thật cho reactive lookup |
| `MockMvc` controller không thấy test principal | Spring Security test context chưa được tích hợp đúng | Dùng `@AutoConfigureMockMvc` hoặc `springSecurity()` đúng |
| Test thiếu quyền trả 200 | Method security chưa bật, service không đi qua proxy | Bật `@EnableMethodSecurity` và test ca âm |

## 13. Ma trận kiểm thử tối thiểu

| Ca | Dữ liệu trước khi listener xử lý | Setup event | Kỳ vọng |
| --- | --- | --- | --- |
| A | `alice` chỉ được tạo ở `@BeforeEach` | `TEST_METHOD` | Có thể fail do user chưa tồn tại |
| B | `alice` được tạo ở `@BeforeEach` | `TEST_EXECUTION` | Tải đúng user, đủ quyền |
| C | `bob` được tạo ở `@BeforeEach`, thiếu `AUDIT_READ` | `TEST_EXECUTION` | Tải user thành công, từ chối quyền |
| D | User có sẵn từ fixture sớm | `TEST_METHOD` | Có thể tải thành công |
| E | Dữ liệu JPA chưa commit, server HTTP thật ở thread khác | Bất kỳ | Có thể không nhìn thấy user |
| F | Đã commit fixture, server xử lý HTTP credentials thật | Không dùng `@WithUserDetails` | Kiểm tra authentication thực |
| G | `@WithMockUser` có quyền | Không tải user từ store | Kiểm tra policy, không kiểm tra lookup |
| H | Test song song cùng sửa `alice` | Bất kỳ | Có nguy cơ race, cần cô lập |

Ma trận này nhấn mạnh hai trục khác nhau: **thời điểm dữ liệu tồn tại** và **thành phần xác thực nào được chạy**. Một test đã giải quyết đúng thời điểm `@WithUserDetails` vẫn chưa phải là end-to-end test của login.

## 14. Bài tập thực hành

### Bài 1: sửa lỗi “user not found”

Cho lớp test dùng `InMemoryUserDetailsManager`, tạo `alice` trong `@BeforeEach`, còn test dùng `@WithUserDetails("alice")`. Phân tích thứ tự callback rồi sửa test với `setupBefore = TestExecutionEvent.TEST_EXECUTION`. Viết ca khẳng định `alice` được tải đúng.

### Bài 2: phân biệt thiếu dữ liệu và thiếu authority

Tạo `alice` có `AUDIT_READ` và `bob` chỉ có `PROFILE_READ`. Dùng `@WithUserDetails` tải lần lượt hai user, kiểm tra `alice` đọc audit thành công còn `bob` gặp `AccessDeniedException`. Giải thích vì sao lỗi của `bob` **không** phải `UsernameNotFoundException`.

### Bài 3: tìm lỗi phụ thuộc thứ tự

Viết hai test dùng cùng username và cùng `InMemoryUserDetailsManager` nhưng không cleanup. Chạy từng test riêng và toàn bộ lớp, quan sát nguy cơ kết quả khác nhau. Bổ sung cleanup và username riêng để không còn phụ thuộc thứ tự; không giữ lại fixture bẩn trong code cuối.

### Bài 4: transaction và HTTP thật

Dùng `@SpringBootTest(RANDOM_PORT)`, seed một user trong test-managed transaction rồi gửi Basic credentials qua WebTestClient. Xác định vì sao server có thể không thấy dữ liệu chưa commit. Đề xuất cách seed trong transaction đã commit và cleanup sau test theo môi trường.

### Bài 5: Servlet và Reactive dùng chiến lược khác nhau

Với Servlet, viết một ca MockMvc dùng `@WithUserDetails` để xác nhận authorities được load từ `UserDetailsService`. Với WebFlux, viết một ca `mockUser()` kiểm tra policy và một ca HTTP Basic dùng `ReactiveUserDetailsService` thật. Giải thích mỗi ca đã kiểm tra được thành phần nào.

### Bài 6: lúc nào `@Sql` đủ?

Giả sử một test có script `@Sql(BEFORE_TEST_METHOD)` tạo user. Kiểm tra Spring Test listeners/transaction và phân tích khi nào `TEST_METHOD` có thể tải user, khi nào nên chọn `TEST_EXECUTION` để thời điểm rõ ràng hơn. Không suy luận chỉ từ tên annotation.

## 15. Checklist trước khi kết luận test ổn định

- [ ] `@WithUserDetails` trỏ đúng `UserDetailsService` và username fixture.
- [ ] Fixture tồn tại **trước thời điểm `setupBefore` đã chọn**.
- [ ] Nếu tạo trong `@BeforeEach`, dùng `TEST_EXECUTION`.
- [ ] Có cả ca user đủ quyền và user có thật nhưng thiếu quyền.
- [ ] Không phụ thuộc dữ liệu của test chạy trước; có cleanup hoặc rollback phù hợp.
- [ ] Không dùng chung mutable username/store một cách không kiểm soát khi test song song.
- [ ] Nếu có database, đã kiểm tra flush/commit/transaction boundary.
- [ ] Với `RANDOM_PORT`, fixture phải hiển thị cho server thread và test không dựa vào authentication local của JUnit.
- [ ] `@WithUserDetails` được hiểu là **tải principal**, không phải xác minh password.
- [ ] Với JWT/OAuth2/OIDC hoặc Reactive, kiểm thử riêng các cơ chế authentication thực cần được chứng minh.

## 16. Kết luận

`@WithUserDetails` tạo security context bằng cách **tải người dùng từ `UserDetailsService`**. Với mặc định `setupBefore = TEST_METHOD`, listener tải user trước `@BeforeEach`, nên dữ liệu tạo trong `@BeforeEach` chưa kịp sẵn sàng. Dùng **`setupBefore = TestExecutionEvent.TEST_EXECUTION`** sẽ dời bước tải user đến sau `@BeforeEach` — đây là giải pháp đúng khi fixture được tạo ở callback đó.

Song song với việc sửa thời điểm, cần quản lý **isolation**: dọn dữ liệu, hạn chế shared state, hiểu transaction/commit và phân biệt principal giả với authentication thực. Một test chỉ bền vững khi tự có đủ dữ liệu, chạy độc lập với thứ tự test và kết luận đúng những gì request hoặc listener thực sự đã kiểm tra.

## 17. Tài liệu tham khảo

- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser`, `@WithUserDetails` và `setupBefore`.
- [Spring Security — WithUserDetails API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithUserDetails.html): user details service bean, username và `TestExecutionEvent`.
- [Spring Security — Spring Test integration](https://docs.spring.io/spring-security/reference/servlet/test/index.html): security test listeners và tích hợp TestContext.
- [Spring Framework — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): vòng đời callback Spring Test và JUnit.
- [Spring Framework — Transaction Management for Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transactions và rollback.
- [Spring Framework — Executing SQL Scripts](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): `@Sql`, phase và cấu hình transaction.
- [Spring Security — Reactive Web Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html): test mutators và reactive security context với WebTestClient.
