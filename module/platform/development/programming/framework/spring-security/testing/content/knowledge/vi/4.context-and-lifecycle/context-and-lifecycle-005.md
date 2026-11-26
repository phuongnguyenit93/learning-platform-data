# Quan hệ giữa khởi tạo danh tính với @BeforeEach

Một bài test cần tạo tài khoản trong `@BeforeEach`, rồi dùng chính tài khoản đó làm người dùng đang đăng nhập. Nếu gắn `@WithUserDetails("lan")` theo cách mặc định, test có thể thất bại trước khi `@BeforeEach` kịp chạy. Ngược lại, có bài test cần đọc người dùng hiện hành ngay trong `@BeforeEach` để tạo dữ liệu theo chủ sở hữu. Hai nhu cầu này có thứ tự khởi tạo khác nhau.

Trong module **SPRING_SECURITY_TESTING**, việc kết hợp danh tính giả lập với `@BeforeEach` là một phần quan trọng của kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test`. Bài học thuộc chương **Ngữ cảnh và vòng đời**, tập trung vào cách phối hợp fixture, `Authentication`, `SecurityContext` và vòng đời JUnit/Spring TestContext trên Servlet. Các ví dụ cũng chỉ ra ranh giới khi chuyển sang `MockMvc`, `WebTestClient`, JWT/OAuth2/OIDC giả lập và xử lý bất đồng bộ.

Sau bài học, bạn sẽ biết chọn một trong ba cách: để listener chuẩn bị danh tính trước `@BeforeEach`, trì hoãn việc dựng danh tính tới sau `@BeforeEach`, hoặc tự tạo authentication trong `@BeforeEach` khi dữ liệu của test quyết định principal.

## 1. Hai việc khởi tạo có quan hệ phụ thuộc

Trong một test tích hợp, thường có hai loại trạng thái:

- **Fixture/dữ liệu kiểm thử:** tài khoản trong repository, tenant, bản ghi, mock, dữ liệu sở hữu bởi người dùng, hoặc cấu hình cần cho test.
- **Danh tính bảo mật:** `Authentication` và `SecurityContext` mà mã ứng dụng đọc thông qua `SecurityContextHolder` hoặc thông qua request đã được bảo vệ.

Hai trạng thái có thể phụ thuộc nhau theo hai chiều:

| Nhu cầu | Thứ tự cần có |
| --- | --- |
| `@BeforeEach` cần biết người dùng hiện hành để tạo dữ liệu của người đó | Listener tạo authentication → `@BeforeEach` tạo fixture |
| `@BeforeEach` tạo tài khoản mà `UserDetailsService` sẽ tải thành principal | `@BeforeEach` tạo tài khoản → listener gọi `UserDetailsService` để tạo authentication |
| Principal phụ thuộc dữ liệu động do test tự tạo | `@BeforeEach` tạo fixture → test tự tạo `Authentication` từ fixture |
| Người dùng giả lập không phụ thuộc database hoặc fixture | Có thể dùng `@WithMockUser`; chọn thời điểm theo nhu cầu của `@BeforeEach` |

Điểm quyết định là **danh tính cần được tạo trước hay sau fixture**. `@BeforeEach` không tự động chạy trước mọi cơ chế chuẩn bị security context; thứ tự phụ thuộc vào `setupBefore` của annotation bảo mật.

## 2. Thứ tự mặc định: listener tạo user trước @BeforeEach

Với `@WithMockUser`, `@WithUserDetails` và annotation tùy biến dựa trên `@WithSecurityContext`, `WithSecurityContextTestExecutionListener` của Spring Security Test mặc định thiết lập context ở sự kiện `TestExecutionEvent.TEST_METHOD`.

Trong JUnit Jupiter dùng `SpringExtension`, trình tự quan trọng là:

~~~text
Spring TestContext: beforeTestMethod
  └─ WithSecurityContextTestExecutionListener
       └─ tạo SecurityContext từ annotation (TEST_METHOD)
JUnit Jupiter: @BeforeEach
  └─ fixture/setup có thể đọc Authentication
Spring TestContext: beforeTestExecution
JUnit Jupiter: @Test
  └─ thực hiện assertions / gọi dịch vụ / gửi MockMvc request
Spring TestContext: afterTestExecution
JUnit Jupiter: @AfterEach
Spring TestContext: afterTestMethod
  └─ listener dọn TestSecurityContextHolder và SecurityContextHolder
~~~

Do đó, trong chế độ mặc định, một phương thức `@BeforeEach` có thể đọc danh tính mà `@WithMockUser` trên phương thức test tạo ra:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(IdentityBeforeEachTest.Config.class)
class IdentityBeforeEachTest {

    @BeforeEach
    void prepareDataForCurrentUser() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        assertThat(authentication).isNotNull();
        assertThat(authentication.getName()).isEqualTo("lan");

        // Ví dụ: tạo dữ liệu báo cáo thuộc sở hữu của "lan".
    }

    @Test
    @WithMockUser(username = "lan", roles = "READER")
    void userIsAvailableDuringBeforeEach() {
        assertThat(SecurityContextHolder.getContext()
                .getAuthentication().getAuthorities())
                .extracting("authority")
                .contains("ROLE_READER");
    }

    @Configuration
    static class Config {
    }
}
~~~

Đây là lựa chọn hợp lý khi `@BeforeEach` cần đọc principal/authorities để chuẩn bị dữ liệu theo người dùng. Ví dụ, một service test có thể tạo bản ghi với `ownerId` lấy từ `Authentication.getName()`, hoặc một mock có thể được cấu hình theo quyền của người dùng.

Không nên hard-code một username trong `@BeforeEach` dùng chung cho lớp có nhiều test với danh tính khác nhau. Nếu từng test có user riêng, hãy đọc danh tính hiện hành một cách tổng quát, hoặc chuyển fixture phụ thuộc người dùng vào một helper được gọi từ từng test.

## 3. Khi @BeforeEach phải tạo user: trì hoãn việc dựng Authentication

Trường hợp ngược lại thường gặp với `@WithUserDetails`. Annotation này yêu cầu Spring Security Test gọi một `UserDetailsService` để tải tài khoản và xây `Authentication`. Nếu tài khoản chỉ được tạo ở `@BeforeEach`, chế độ mặc định có thể gọi service **trước khi tài khoản tồn tại**.

### 3.1. Vấn đề với TEST_METHOD

~~~text
@WithUserDetails("lan") — mặc định TEST_METHOD
       │
       ▼
beforeTestMethod
  └─ WithUserDetailsSecurityContextFactory
       └─ UserDetailsService.loadUserByUsername("lan")
            └─ Không tìm thấy tài khoản
       │
       X test thất bại trước khi chạy @BeforeEach
       │
@BeforeEach
  └─ createUser("lan") — quá muộn
~~~

Trong trường hợp này, thay đổi thời điểm thành `TestExecutionEvent.TEST_EXECUTION`. Spring TestContext sẽ chạy `@BeforeEach` trước, sau đó mới gọi factory tạo security context.

### 3.2. Ví dụ với InMemoryUserDetailsManager

Ví dụ sau sử dụng `InMemoryUserDetailsManager` làm `UserDetailsService`. Tài khoản `lan` được tạo trong `@BeforeEach`, và `@WithUserDetails` tải tài khoản đó ngay trước khi thân `@Test` bắt đầu:

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.InMemoryUserDetailsManager;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.test.context.support.TestExecutionEvent;
import org.springframework.security.test.context.support.WithUserDetails;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(UserDetailsFixtureTest.Config.class)
class UserDetailsFixtureTest {

    @Autowired
    InMemoryUserDetailsManager testUsers;

    @BeforeEach
    void createUserForThisTest() {
        // Phòng trường hợp fixture được dùng lại trong cùng context.
        if (testUsers.userExists("lan")) {
            testUsers.deleteUser("lan");
        }

        UserDetails lan = User.withUsername("lan")
                .password("{noop}test-password")
                .authorities("report:read")
                .build();

        testUsers.createUser(lan);
    }

    @Test
    @WithUserDetails(
            value = "lan",
            userDetailsServiceBeanName = "testUsers",
            setupBefore = TestExecutionEvent.TEST_EXECUTION
    )
    void loadsTheUserCreatedInBeforeEach() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        assertThat(authentication.getName()).isEqualTo("lan");
        assertThat(authentication.getPrincipal())
                .isInstanceOf(UserDetails.class);
        assertThat(authentication.getAuthorities())
                .extracting("authority")
                .contains("report:read");
    }

    @AfterEach
    void removeFixture() {
        if (testUsers.userExists("lan")) {
            testUsers.deleteUser("lan");
        }
    }

    @Configuration
    static class Config {
        @Bean
        InMemoryUserDetailsManager testUsers() {
            return new InMemoryUserDetailsManager();
        }
    }
}
~~~

Trình tự ở ví dụ này:

1. Spring TestContext gọi `beforeTestMethod`. Listener nhận ra `TEST_EXECUTION`, nên chưa gọi factory của `@WithUserDetails`.
2. JUnit chạy `@BeforeEach`. Tài khoản `lan` được thêm vào `testUsers`.
3. Spring TestContext gọi `beforeTestExecution`. Factory của `@WithUserDetails` gọi `loadUserByUsername("lan")` trên bean `testUsers`, rồi tạo context.
4. Thân `@Test` chạy với principal `lan` và authority `report:read`.
5. JUnit chạy `@AfterEach`, xóa fixture của ví dụ. Sau đó callback `afterTestMethod` của Spring TestContext dọn security context.

`{noop}` ở đây chỉ để tạo password encoder đơn giản cho dữ liệu test. Bài test **không xác minh mật khẩu**: `@WithUserDetails` tải đối tượng `UserDetails` trực tiếp, không gửi password qua endpoint đăng nhập.

Với database thực tế, có thể thay `InMemoryUserDetailsManager` bằng repository hoặc service fixture. Nếu dùng dữ liệu transaction test, hãy kiểm tra thứ tự transaction và listener của dự án; bảo đảm tài khoản được nhìn thấy trong cùng transaction/context mà `UserDetailsService` sử dụng. `WithSecurityContextTestExecutionListener` chỉ tạo và dọn security context, không tự tạo, commit hay rollback dữ liệu.

## 4. Khi danh tính không cần tải từ UserDetailsService

Nếu `@BeforeEach` cần tạo fixture trước khi test dùng một người dùng giả lập, nhưng principal không phụ thuộc vào database, có thể dùng `@WithMockUser(setupBefore = TEST_EXECUTION)`:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.TestExecutionEvent;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(MockUserAfterFixtureTest.Config.class)
class MockUserAfterFixtureTest {

    private boolean fixtureReady;

    @BeforeEach
    void createFixture() {
        fixtureReady = true;

        // Chưa có Authentication từ @WithMockUser ở thời điểm này.
        // Chuẩn bị dữ liệu độc lập với danh tính trước.
        assertThat(SecurityContextHolder.getContext()
                .getAuthentication()).isNull();
    }

    @Test
    @WithMockUser(
            username = "lan",
            authorities = "report:read",
            setupBefore = TestExecutionEvent.TEST_EXECUTION
    )
    void mockUserIsAvailableAfterFixtureSetup() {
        assertThat(fixtureReady).isTrue();
        assertThat(SecurityContextHolder.getContext()
                .getAuthentication().getName()).isEqualTo("lan");
    }

    @Configuration
    static class Config {
    }
}
~~~

Assertion `null` trong `@BeforeEach` chỉ đúng với context test độc lập này, khi không có extension hoặc mã khác đặt authentication trước đó. Điều được bảo đảm bởi `TEST_EXECUTION` là **authentication do annotation tạo chưa được listener đặt vào `@BeforeEach`**. Nếu fixture của bạn không phụ thuộc user, đây là cách rõ ràng để chuẩn bị dữ liệu trước rồi mới bắt đầu phần kiểm thử bảo mật.

## 5. Tự tạo Authentication trong @BeforeEach khi principal phụ thuộc fixture

Có tình huống danh tính không thể khai báo tĩnh bằng `@WithMockUser`: principal phải lấy từ đối tượng vừa tạo, tenant được cấp động, hoặc authorities được tính từ dữ liệu của test. Khi đó có thể tạo `Authentication` trong `@BeforeEach`.

Dùng `TestSecurityContextHolder.setAuthentication(...)` để đặt authentication cho cả test holder và security holder:

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.TestSecurityContextHolder;

import static org.assertj.core.api.Assertions.assertThat;

class DynamicPrincipalTest {

    @BeforeEach
    void createFixtureAndAuthentication() {
        // Giả định fixtureService tạo account và trả về mã người dùng động.
        String userId = "user-42";

        Authentication authentication =
                new UsernamePasswordAuthenticationToken(
                        userId,
                        "N/A",
                        AuthorityUtils.createAuthorityList(
                                "report:read", "report:export"));

        TestSecurityContextHolder.setAuthentication(authentication);
    }

    @Test
    void serviceReadsDynamicPrincipal() {
        assertThat(SecurityContextHolder.getContext()
                .getAuthentication().getName()).isEqualTo("user-42");
    }

    @AfterEach
    void clearSecurityState() {
        TestSecurityContextHolder.clearContext();
    }
}
~~~

Ví dụ dùng mã người dùng cố định để minh họa; trong dự án, thay bằng ID/username thực sự được fixture tạo ra. Authentication có authorities được truyền vào constructor sẽ ở trạng thái đã xác thực để phục vụ test phân quyền.

Cần phân biệt:

- `TestSecurityContextHolder.setAuthentication(authentication)` cập nhật cả `TestSecurityContextHolder` và `SecurityContextHolder`.
- `SecurityContextHolder.setContext(context)` chỉ đặt context cho holder hiện tại; nó không tự đồng bộ test holder.
- `TestSecurityContextHolder.clearContext()` dọn cả hai holder.
- `SecurityContextHolder.clearContext()` chỉ dọn holder của luồng hiện tại, có thể để lại test context nếu trước đó đã đặt bằng `TestSecurityContextHolder`.

Khi tự quản lý danh tính bằng code, cần có điểm dọn tương ứng, ví dụ `@AfterEach` gọi `TestSecurityContextHolder.clearContext()`. Nếu dùng annotation do listener quản lý, listener dọn ở `afterTestMethod`; không nên tạo thêm cơ chế dọn trùng lặp mà không hiểu thứ tự.

Một biến thể khác là tự tạo `SecurityContext`:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
TestSecurityContextHolder.setContext(context);
~~~

Cách này hữu ích khi test cần principal hoặc token tùy chỉnh hơn. Tạo context mới giúp tránh sửa một context đang được thành phần khác tham chiếu.

## 6. Tránh ghi đè danh tính một cách vô ý

Khi kết hợp annotation và `@BeforeEach`, hãy xác định rõ thành phần nào là nguồn sự thật của authentication.

| Cấu hình | Trạng thái tại `@BeforeEach` | Trạng thái khi vào `@Test` |
| --- | --- | --- |
| `@WithMockUser` mặc định (`TEST_METHOD`) | Có authentication do listener tạo | Có authentication, trừ khi mã setup thay đổi |
| `@WithUserDetails` mặc định (`TEST_METHOD`) | Listener đã tải user trước đó | Có authentication từ UserDetails |
| `@WithMockUser(setupBefore = TEST_EXECUTION)` | Authentication của annotation chưa được đặt | Listener đã đặt authentication |
| `@WithUserDetails(setupBefore = TEST_EXECUTION)` | Fixture có thể tạo user trong setup | Listener tải user sau `@BeforeEach` |
| Không dùng annotation, tự đặt trong `@BeforeEach` | Test tự tạo authentication | Có authentication nếu không bị thay đổi |
| Annotation mặc định và `@BeforeEach` gọi `setAuthentication(...)` | Authentication của annotation bị thay bằng authentication thủ công | Test dùng giá trị được đặt sau |

Một lỗi dễ gặp là vừa khai báo `@WithMockUser(username = "lan")`, vừa đặt `TestSecurityContextHolder.setAuthentication(...)` trong `@BeforeEach` cho `mai`. Trong chế độ mặc định, listener tạo `lan` trước; sau đó code setup ghi đè bằng `mai`. Khi thân `@Test` bắt đầu, danh tính là `mai`. Đây có thể là chủ đích, nhưng nếu không được thể hiện rõ, test sẽ khó đọc và dễ gây hiểu nhầm.

Nếu danh tính được tạo hoàn toàn bằng code, cân nhắc bỏ annotation. Nếu dùng `@WithUserDetails`, hãy để listener là thành phần tạo authentication sau khi fixture đã sẵn sàng. Nếu `@BeforeEach` chỉ cần đọc người dùng của annotation, giữ mặc định `TEST_METHOD`.

## 7. Tương tác với MockMvc: setup fixture và request được bảo vệ

Trong kiểm thử Servlet, có hai thời điểm khác nhau:

1. `@BeforeEach` tạo fixture hoặc cấu hình dữ liệu.
2. `MockMvc.perform(...)` thực thi request qua chuỗi filter Spring Security (khi MockMvc được tích hợp đúng).

Ví dụ sau giả định ứng dụng có endpoint `GET /api/reports` yêu cầu `ROLE_READER`, và cấu hình HTTP Basic để request vô danh nhận `401`:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.TestExecutionEvent;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    void prepareReportData() {
        // Tạo báo cáo và các fixture cần thiết.
        // Nếu fixture không cần Authentication, có thể dùng TEST_EXECUTION.
    }

    @Test
    @WithMockUser(
            username = "lan",
            roles = "READER",
            setupBefore = TestExecutionEvent.TEST_EXECUTION
    )
    void readerCanReadReports() throws Exception {
        mockMvc.perform(get("/api/reports"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(
            username = "mai",
            roles = "GUEST",
            setupBefore = TestExecutionEvent.TEST_EXECUTION
    )
    void guestIsForbidden() throws Exception {
        mockMvc.perform(get("/api/reports"))
                .andExpect(status().isForbidden());
    }
}
~~~

Ví dụ này cần endpoint, `SecurityFilterChain` và cấu hình ứng dụng tương ứng. `@AutoConfigureMockMvc` thường tích hợp security filter trong Spring Boot; nếu tự dựng MockMvc từ `WebApplicationContext`, hãy áp dụng `springSecurity()` khi build.

Nếu `@BeforeEach` cần tạo báo cáo theo người dùng hiện hành, đổi annotation về mặc định `TEST_METHOD` và đọc principal trong setup. Nếu dữ liệu báo cáo độc lập với người dùng, `TEST_EXECUTION` cho phép fixture được tạo trước khi listener đặt danh tính. Cả hai chế độ đều có thể cấp user cho request gửi trong thân `@Test`.

Đừng xem một assertion đọc `SecurityContextHolder` trên test thread là bằng chứng filter HTTP đã thực thi. Hãy kiểm tra response hoặc hành vi endpoint cho cả trường hợp được phép và bị từ chối. Với HTTP Basic, các kỳ vọng thường là `401` cho vô danh, `403` cho người dùng đã xác thực nhưng thiếu quyền, và `200` cho người dùng đủ quyền; form login hoặc entry point tùy chỉnh có thể trả mã khác.

Nếu gọi server thật qua cổng mạng (ví dụ `@SpringBootTest(webEnvironment = RANDOM_PORT)`), context trên luồng JUnit không tự truyền qua HTTP. Request cần mang credentials, bearer token, cookie hoặc session thích hợp.

## 8. Các điểm cần lưu ý với WebTestClient và Reactive

`setupBefore` chỉ điều khiển lúc listener đặt context cho test. Nó không thay đổi cơ chế truyền context của ứng dụng.

- Trên Servlet, `SecurityContextHolder` mặc định dùng `ThreadLocal`. Khi tác vụ chạy ở executor khác, phải truyền context qua executor wrapper/decorator nếu nghiệp vụ yêu cầu.
- Trên WebFlux, Spring Security dùng Reactor Context. Không giả định `SecurityContextHolder` của luồng JUnit tự xuất hiện trong toàn bộ reactive pipeline.
- `WebTestClient` có các request configurer như `mockUser()` để cấp danh tính cho request Reactive; đó là cơ chế request riêng.
- `jwt()`, `oauth2Login()` và `oidcLogin()` mô phỏng danh tính/claims/authorities phục vụ kiểm tra phân quyền. Chúng không chứng minh token thật đã được giải mã hoặc xác minh chữ ký, issuer, audience hay thời hạn.

Ví dụ Reactive:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

webTestClient.mutateWith(mockUser("lan").roles("READER"))
        .get().uri("/api/reports")
        .exchange()
        .expectStatus().isOk();
~~~

Ví dụ yêu cầu `WebTestClient` đã được tích hợp Spring Security WebFlux và endpoint cho phép `ROLE_READER`. Với pipeline reactive, danh tính được truyền theo Reactor Context, không theo giả định rằng toàn bộ xử lý nằm trên cùng một thread.

## 9. Bảng chọn cách khởi tạo danh tính

| Tình huống của `@BeforeEach` | Cách phù hợp | Vì sao |
| --- | --- | --- |
| Cần biết user hiện hành để tạo dữ liệu sở hữu bởi user | `@WithMockUser` mặc định (`TEST_METHOD`) | Listener tạo authentication trước setup |
| Tạo tài khoản trong database để `UserDetailsService` tải | `@WithUserDetails(setupBefore = TEST_EXECUTION)` | Fixture tồn tại trước khi factory tải user |
| Tạo fixture độc lập, sau đó test mới cần user giả lập | `@WithMockUser(setupBefore = TEST_EXECUTION)` | Setup chạy trước danh tính của annotation |
| Principal lấy từ ID hoặc đối tượng động do fixture trả về | Tạo `Authentication` trong `@BeforeEach` và đặt qua `TestSecurityContextHolder` | Test tự kiểm soát principal theo dữ liệu |
| Mỗi request cần một user khác nhau | `MockMvc` request postprocessor như `user(...)`, `authentication(...)` | Danh tính được gắn tại từng request |
| WebFlux request cần user giả lập | `WebTestClient.mutateWith(mockUser(...))` | Dùng cơ chế dành cho Reactive |

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `@WithUserDetails` báo không tìm thấy user được tạo ở `@BeforeEach` | Factory chạy trước setup theo mặc định `TEST_METHOD` | Đổi sang `TEST_EXECUTION` hoặc tạo fixture sớm hơn |
| `@BeforeEach` đọc authentication nhưng nhận `null` | Annotation dùng `TEST_EXECUTION` | Di chuyển logic cần user vào `@Test`, hoặc dùng `TEST_METHOD` |
| `@BeforeEach` luôn thấy cùng username dù từng test khai báo user khác nhau | Setup đang hard-code một danh tính | Đọc `Authentication.getName()` hoặc chuyển fixture vào helper theo test |
| Test có annotation nhưng không có context | Thiếu Spring TestContext/listener hoặc cấu hình listener bị thay thế | Kiểm tra `SpringExtension`, annotation Spring test và `@TestExecutionListeners` |
| Test thủ công còn user cũ sau khi chạy | Chỉ dọn `SecurityContextHolder` hoặc không dọn test holder | Dùng `TestSecurityContextHolder.clearContext()` trong `@AfterEach`/`finally` |
| Test request bị `401` dù `@BeforeEach` thấy authentication | Request không nhận context hoặc MockMvc thiếu filter tích hợp | Kiểm tra `springSecurity()`/`@AutoConfigureMockMvc` và postprocessor |
| Request `POST` bị `403` dù user đủ quyền | CSRF token chưa được cấp | Dùng `csrf()` trong request hợp lệ và giữ ca kiểm tra thiếu token |
| Test Reactive mất danh tính khi đổi thread | Dựa vào ThreadLocal trong reactive pipeline | Dùng Reactor Context và công cụ test WebFlux |

Không dùng `@DirtiesContext` hoặc đổi chiến lược `SecurityContextHolder` toàn JVM chỉ để chữa một lỗi thứ tự setup. Hai thao tác đó tác động rộng hơn vấn đề cần giải quyết. Hãy xác định fixture cần có trước hay danh tính cần có trước, rồi chọn đúng điểm thiết lập.

## 11. Bài thực hành

Xây dựng test cho `ReportService` và endpoint `GET /api/reports` yêu cầu `ROLE_READER`:

1. Dùng `@WithMockUser` mặc định. Trong `@BeforeEach`, đọc tên user và tạo dữ liệu báo cáo thuộc user đó.
2. Tạo user `lan` trong `@BeforeEach`, dùng `@WithUserDetails` mặc định và quan sát vì sao factory chưa tìm thấy user.
3. Đổi `setupBefore` sang `TEST_EXECUTION`, chạy lại và xác minh principal được nạp sau khi fixture tồn tại.
4. Viết một test không dùng annotation: tạo account động trong `@BeforeEach`, dựng `Authentication` từ account và gọi `TestSecurityContextHolder.setAuthentication(...)`.
5. Kiểm tra cả `@AfterEach` và `afterTestMethod` trong vòng đời: giải thích tại sao listener dọn sau `@AfterEach`, và vì sao test thủ công cần chủ động dọn context.
6. Dùng `MockMvc` để kiểm tra người dùng đủ quyền và thiếu quyền; phân biệt kết quả HTTP với assertion đọc `SecurityContextHolder` trên test thread.
7. Viết thêm một request WebFlux với `WebTestClient.mutateWith(mockUser(...))` và mô tả danh tính được truyền qua Reactor Context.

Hãy tự trả lời ba câu hỏi trước khi kết thúc: **Fixture cần được tạo trước hay sau danh tính? `@BeforeEach` có cần đọc principal không? Ai chịu trách nhiệm dọn context và fixture?** Khi trả lời rõ ba câu hỏi này, bạn có thể chọn đúng cách khởi tạo danh tính cho từng loại kiểm thử.

## Tài liệu tham khảo

- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security API — TestExecutionEvent](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/TestExecutionEvent.html)
- [Spring Security API — WithUserDetails](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithUserDetails.html)
- [Spring Security API — WithMockUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithMockUser.html)
- [Spring Security API — TestSecurityContextHolder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/TestSecurityContextHolder.html)
- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
