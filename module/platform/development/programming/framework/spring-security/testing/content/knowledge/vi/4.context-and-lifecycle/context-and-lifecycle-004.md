# Thời điểm TEST_METHOD so với TEST_EXECUTION

Một bài kiểm thử sử dụng `@WithUserDetails("lan")` có thể thất bại vì chưa tìm thấy người dùng `lan`, mặc dù phương thức `@BeforeEach` đã viết lệnh tạo người dùng đó. Nguyên nhân thường nằm ở **thời điểm Spring Security Test dựng `SecurityContext`**: mặc định việc dựng diễn ra *trước* `@BeforeEach`. Nếu chuyển sang `TestExecutionEvent.TEST_EXECUTION`, người dùng mới được nạp *sau* bước chuẩn bị dữ liệu.

Trong chương **Ngữ cảnh và vòng đời** của module **SPRING_SECURITY_TESTING**, hai giá trị `TEST_METHOD` và `TEST_EXECUTION` giúp bạn điều khiển chính xác ranh giới thời gian của danh tính giả lập. Hiểu đúng chúng rất quan trọng khi kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên Servlet (`MockMvc`) hoặc Reactive (`WebTestClient`): một phép thử có thể thành công hoặc thất bại chỉ vì `Authentication` chưa tồn tại tại thời điểm mã test cần đọc.

Bài học giải thích cơ chế, các điểm chèn trong vòng đời JUnit Jupiter/Spring TestContext, cách dùng `@WithMockUser` và `@WithUserDetails`, những trường hợp nên đổi chế độ, tác động tới `@BeforeEach` và `@AfterEach`, ví dụ kiểm thử HTTP và các giới hạn khi sang luồng hoặc mô hình Reactive.

## 1. TEST_METHOD và TEST_EXECUTION là gì?

Cả hai là giá trị của enum `TestExecutionEvent` trong `spring-security-test`:

```java
import org.springframework.security.test.context.support.TestExecutionEvent;
```

Chúng được truyền vào thuộc tính `setupBefore` trên các annotation bảo mật như `@WithMockUser` hoặc `@WithUserDetails`:

```java
@WithMockUser(
    username = "lan",
    roles = "READER",
    setupBefore = TestExecutionEvent.TEST_METHOD
)
```

```java
@WithMockUser(
    username = "lan",
    roles = "READER",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
```

Hai cách trên đều tạo một `SecurityContext` chứa `Authentication` giả lập cho bài test. **Khác biệt nằm ở lúc tạo và đặt context**, không nằm ở danh tính, authority, chính sách phân quyền hay cách dọn sau khi chạy.

| Thuộc tính | `TEST_METHOD` | `TEST_EXECUTION` |
| --- | --- | --- |
| Có phải giá trị mặc định không? | **Có** | Không, phải chọn tường minh |
| Callback của Spring TestContext | `beforeTestMethod` | `beforeTestExecution` |
| Thời điểm tương đối với JUnit `@BeforeEach` | **Trước** `@BeforeEach` | **Sau** `@BeforeEach` |
| Khi bắt đầu thân phương thức `@Test` | Context đã được đặt | Context đã được đặt |
| Khi `@AfterEach` đang chạy | Thông thường context vẫn còn | Thông thường context vẫn còn |
| Cách dọn khi test kết thúc | Listener dọn ở `afterTestMethod` | Listener dọn ở `afterTestMethod` |
| Trường hợp điển hình | `@BeforeEach` cần đọc người dùng đã giả lập | `@BeforeEach` cần chuẩn bị dữ liệu *trước khi* tạo `Authentication` |

**Lưu ý tên gọi:** `TEST_METHOD` không có nghĩa context chỉ được tạo khi thân phương thức `@Test` bắt đầu. Theo Spring TestContext, callback `beforeTestMethod` diễn ra sớm hơn `@BeforeEach` của JUnit Jupiter. Tương tự, `TEST_EXECUTION` không có nghĩa listener chờ đến sau khi `@Test` chạy; `beforeTestExecution` vẫn diễn ra **trước** câu lệnh đầu tiên của `@Test`.

## 2. Mốc thời gian của JUnit Jupiter và Spring TestContext

Xét một bài test dùng `@SpringJUnitConfig` hoặc `@SpringBootTest` với `SpringExtension`. Thứ tự các mốc chính có thể được biểu diễn như sau:

```text
Thời gian
   │
   ▼
Spring TestContext: beforeTestMethod
   ├─ Với TEST_METHOD: tạo SecurityContext và đặt Authentication
   └─ Với TEST_EXECUTION: chưa tạo Authentication từ annotation
   │
JUnit Jupiter: @BeforeEach
   ├─ TEST_METHOD: có thể đọc Authentication của annotation
   └─ TEST_EXECUTION: chưa thể đọc Authentication của annotation
   │
Spring TestContext: beforeTestExecution
   └─ Với TEST_EXECUTION: bây giờ mới tạo và đặt context
   │
JUnit Jupiter: @Test
   └─ Cả hai chế độ đều có Authentication
   │
Spring TestContext: afterTestExecution
   │
JUnit Jupiter: @AfterEach
   └─ Context của annotation thường vẫn còn nếu mã test chưa đổi nó
   │
Spring TestContext: afterTestMethod
   └─ WithSecurityContextTestExecutionListener dọn context
   │
   ▼
Kết thúc kiểm thử
```

Trong phần đầu bài test, `WithSecurityContextTestExecutionListener` tìm annotation được hỗ trợ (chẳng hạn `@WithMockUser` hoặc annotation tùy biến gắn `@WithSecurityContext`). Nó dùng factory tương ứng để tạo context vào sự kiện đã chọn. Khi bài test kết thúc, listener gọi cơ chế dọn ngữ cảnh thông qua `TestSecurityContextHolder.clearContext()`.

Hai ranh giới cần phân biệt:

1. **`beforeTestMethod` so với `beforeTestExecution`** quyết định việc tạo context xảy ra trước hay sau `@BeforeEach`.
2. **`afterTestExecution` so với `afterTestMethod`** là hai callback khác nhau; `WithSecurityContextTestExecutionListener` dọn context khi kết thúc phương thức test, trong `afterTestMethod`. Chọn `TEST_EXECUTION` không chuyển việc dọn thành “ngay sau `@Test`, trước `@AfterEach`”.

Nếu có extension, listener hoặc logic khác chủ động đổi `SecurityContextHolder`, không nên khẳng định chắc chắn context còn nguyên vẹn tại mọi điểm. Thứ tự trên mô tả cơ chế mặc định, khi không có mã khác ghi đè.

## 3. TEST_METHOD: @BeforeEach có thể sử dụng người dùng giả lập

Với `TEST_METHOD`, Spring Security Test chuẩn bị authentication trước khi JUnit thực thi `@BeforeEach`. Đây là lựa chọn thuận tiện khi mã setup phải biết principal, ví dụ chuẩn bị dữ liệu sở hữu bởi người dùng hiện tại hoặc cấu hình một mock dựa trên quyền của người dùng.

Ví dụ JUnit Jupiter dưới đây không yêu cầu database. `@SpringJUnitConfig` khởi tạo Spring TestContext, và một `@Configuration` rỗng đủ để trình diễn vai trò listener:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.TestExecutionEvent;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(TestMethodTimingTest.Config.class)
class TestMethodTimingTest {

    @BeforeEach
    void prepare() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        // beforeTestMethod đã chạy nên @BeforeEach thấy "lan".
        assertThat(authentication).isNotNull();
        assertThat(authentication.getName()).isEqualTo("lan");
    }

    @Test
    @WithMockUser(
            username = "lan",
            authorities = "report:read",
            setupBefore = TestExecutionEvent.TEST_METHOD
    )
    void userCoSanTruocBeforeEach() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        assertThat(authentication.getAuthorities())
                .extracting("authority")
                .contains("report:read");
    }

    @Configuration
    static class Config {
    }
}
```

Có thể lược bỏ `setupBefore = TEST_METHOD` vì đây là mặc định của `@WithMockUser`:

```java
@Test
@WithMockUser(username = "lan", authorities = "report:read")
void vanLaTestMethod() {
    // Authentication đã được chuẩn bị trước @BeforeEach.
}
```

Điểm quan trọng của ví dụ: `@BeforeEach` chỉ kiểm tra người dùng `lan` bởi lớp này có **một** phương thức test với annotation tương ứng. Nếu lớp có nhiều test dùng những danh tính khác nhau, `@BeforeEach` không nên hard-code `lan` cho tất cả. Có thể đọc tên hiện có nếu muốn chuẩn bị chung, hoặc đặt logic liên quan tới từng danh tính vào từng phương thức.

### Khi nào TEST_METHOD phù hợp?

- Dữ liệu cần có để tạo `Authentication` đã tồn tại trước khi bắt đầu phương thức test.
- `@BeforeEach` phải lấy tên/authorities từ `SecurityContextHolder` để chuẩn bị dữ liệu nghiệp vụ.
- Muốn hành vi mặc định dễ đọc, ít khai báo.
- Dùng `@WithMockUser` với principal và authorities giả lập có sẵn; không cần chờ repository tạo dữ liệu.

## 4. TEST_EXECUTION: @BeforeEach chạy trước khi dựng context

`TEST_EXECUTION` đảo thứ tự riêng giữa việc tạo context và `@BeforeEach`. Điều này hữu ích khi logic setup tạo tiền đề mà `WithSecurityContextFactory` phải sử dụng, như lưu tài khoản, gán quyền, xây tenant hoặc cấu hình `UserDetailsService`.

Một ví dụ tập trung vào mốc thời gian:

```java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.TestExecutionEvent;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(TestExecutionTimingTest.Config.class)
class TestExecutionTimingTest {

    @BeforeEach
    void beforeEach() {
        // Trong ví dụ độc lập này, không có mã nào khác đặt context.
        // Listener của TEST_EXECUTION chưa tạo user "lan".
        assertThat(SecurityContextHolder.getContext()
                .getAuthentication()).isNull();
    }

    @Test
    @WithMockUser(
            username = "lan",
            roles = "READER",
            setupBefore = TestExecutionEvent.TEST_EXECUTION
    )
    void authenticationXuatHienNgayTruocTest() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        assertThat(authentication).isNotNull();
        assertThat(authentication.getName()).isEqualTo("lan");
        assertThat(authentication.getAuthorities())
                .extracting("authority")
                .contains("ROLE_READER");
    }

    @AfterEach
    void afterEach() {
        // Listener dọn ở afterTestMethod, sau callback @AfterEach.
        assertThat(SecurityContextHolder.getContext()
                .getAuthentication().getName()).isEqualTo("lan");
    }

    @Configuration
    static class Config {
    }
}
```

Kỳ vọng `null` trong `@BeforeEach` là minh họa cho context độc lập chưa được thành phần nào khác đặt. Nó **không phải quy tắc toàn cục**: một extension, test infrastructure hoặc mã setup khác có thể đã đặt một authentication trước đó. Điều cần khẳng định là **authentication của `@WithMockUser(..., setupBefore = TEST_EXECUTION)` chưa được listener tạo trong `@BeforeEach`**.

`@AfterEach` ở ví dụ này vẫn đọc được `lan` bởi listener dọn ở `afterTestMethod`, muộn hơn JUnit `@AfterEach`. Không nên đặt `assertThat(...).isEqualTo("lan")` vào `@AfterEach` chung cho một lớp có nhiều phương thức test sử dụng các danh tính khác nhau hoặc không dùng annotation.

## 5. Ca sử dụng quan trọng: tạo UserDetails trong @BeforeEach

Một lỗi rất dễ gặp là dùng `@WithUserDetails("lan")` trong khi tài khoản `lan` chỉ được tạo ở `@BeforeEach`.

### 5.1. Vì sao mặc định có thể thất bại?

Xét trình tự:

```text
@WithUserDetails(value = "lan")    // setupBefore mặc định: TEST_METHOD
        │
        ▼
beforeTestMethod
  └─ WithUserDetailsSecurityContextFactory
      └─ UserDetailsService.loadUserByUsername("lan")
          └─ Không tìm thấy vì chưa có dữ liệu
        │
        X  TEST thất bại trước khi chạy @BeforeEach
        │
@BeforeEach: createUser("lan")   // chưa kịp thực thi
```

`@WithUserDetails` không phải một lần đăng nhập qua form hoặc HTTP Basic. Nó gọi `UserDetailsService` để nhận `UserDetails` và dựng `Authentication` cho test. Vì vậy, nếu dữ liệu chưa sẵn sàng đúng thời điểm, factory không thể tạo context.

### 5.2. Giải pháp: TEST_EXECUTION

Ví dụ đầy đủ dưới đây dùng `InMemoryUserDetailsManager`. Nó chỉ có một phương thức test để tránh việc tạo trùng username trong một context được Spring cache. Ở dự án thực tế dùng repository/DB, bạn có thể thay `createUser(...)` bằng thao tác lưu dữ liệu phù hợp.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.InMemoryUserDetailsManager;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.TestExecutionEvent;
import org.springframework.security.test.context.support.WithUserDetails;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(DynamicUserDetailsTest.Config.class)
class DynamicUserDetailsTest {

    @Autowired
    InMemoryUserDetailsManager testUsers;

    @BeforeEach
    void createUserBeforeAuthentication() {
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
    void loadsUserCreatedInBeforeEach() {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();

        assertThat(auth.getName()).isEqualTo("lan");
        assertThat(auth.getPrincipal()).isInstanceOf(UserDetails.class);
        assertThat(auth.getAuthorities())
                .extracting("authority")
                .contains("report:read");
    }

    @Configuration
    static class Config {
        @Bean
        InMemoryUserDetailsManager testUsers() {
            return new InMemoryUserDetailsManager();
        }
    }
}
```

Đọc kết quả theo thứ tự:

1. Spring TestContext gọi `beforeTestMethod`. Listener nhận ra annotation chọn `TEST_EXECUTION` và trì hoãn việc tạo context.
2. JUnit chạy `@BeforeEach`. Bean `testUsers` nhận thêm `UserDetails` của `lan`.
3. Spring TestContext gọi `beforeTestExecution`. Factory của `@WithUserDetails` lấy `lan` từ `testUsers`, sau đó đặt authentication vào context.
4. Phương thức `@Test` đọc được principal và quyền mong đợi.
5. Khi test kết thúc, listener dọn context; việc xóa dữ liệu người dùng (nếu cần) thuộc về thiết kế fixture, không phải chức năng của listener.

`{noop}` trong chuỗi password chỉ dùng cho dữ liệu test của ví dụ; bài kiểm tra này **không xác minh mật khẩu**. Việc chọn `TEST_EXECUTION` bảo đảm thứ tự dựng context, không biến `@WithUserDetails` thành kiểm thử xác thực mật khẩu thật.

**Nếu có nhiều phương thức test tạo cùng username trên một `InMemoryUserDetailsManager` được dùng lại**, cần xóa/tái tạo fixture hoặc tạo username riêng để tránh trùng dữ liệu. Với database, có thể dùng rollback theo transaction test, dữ liệu độc lập theo mỗi test hoặc chiến lược làm sạch rõ ràng. Listener chỉ dọn security context, không tự hoàn nguyên repository.

### Khi nào nên cân nhắc cách khác?

Nếu tài khoản đã có từ fixture cấp lớp, SQL script hoặc cấu hình bean trước khi phương thức test bắt đầu, `TEST_METHOD` mặc định có thể là đủ. Không cần đổi sang `TEST_EXECUTION` theo thói quen. Chỉ thay thời điểm khi có **phụ thuộc thực sự** giữa code ở `@BeforeEach` và factory dựng context.

## 6. Tùy biến thời điểm với @WithSecurityContext

Spring Security Test cho phép viết annotation tùy biến cho principal phức tạp thông qua `@WithSecurityContext`:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithSecurityContext(
        factory = WithTenantUserFactory.class,
        setupBefore = TestExecutionEvent.TEST_EXECUTION
)
public @interface WithTenantUser {
    String username();
    String tenant();
}
```

Ví dụ minh họa này giả định `WithTenantUserFactory` do ứng dụng triển khai `WithSecurityContextFactory<WithTenantUser>`. Khi annotation chọn `TEST_EXECUTION`, factory được gọi sau `@BeforeEach`, do đó có thể dùng dữ liệu tenant vừa được khởi tạo tại đó. Điều kiện vẫn là factory trả về một `SecurityContext` thích hợp, thường bằng `SecurityContextHolder.createEmptyContext()` rồi đặt `Authentication`.

Không nên nhầm lẫn ba hành động:

- **Đặt thời điểm:** giá trị `setupBefore` trên annotation (hoặc meta-annotation `@WithSecurityContext`).
- **Tạo nội dung:** `WithSecurityContextFactory` quyết định principal, credentials và authorities.
- **Dọn dẹp:** `WithSecurityContextTestExecutionListener` quản lý context sau khi test kết thúc.

Muốn tùy biến thời điểm ở mỗi lần dùng annotation riêng, cần thiết kế thuộc tính và alias/meta-annotation cẩn thận. Không có bảo đảm một trường tùy ý mang tên `setupBefore` trong annotation tự tạo sẽ tự động điều khiển `@WithSecurityContext` nếu không cấu hình mapping đúng.

## 7. TEST_METHOD và TEST_EXECUTION tác động thế nào tới MockMvc?

Với Servlet, `@WithMockUser` thiết lập người dùng của **bài test**, còn `MockMvc.perform(...)` gửi một request qua các filter bảo mật (khi đã tích hợp Spring Security). Hai phạm vi này có vòng đời khác nhau.

```text
Spring TestContext
├─ trước @BeforeEach  ───────── TEST_METHOD đặt Authentication
├─ @BeforeEach         ───────── khởi tạo MockMvc, fixture, mock dependency
├─ sau @BeforeEach    ────────── TEST_EXECUTION đặt Authentication
├─ @Test               ───────── MockMvc.perform(request)
│                                ├─ Spring Security filter chain
│                                ├─ kiểm tra authentication/authorization
│                                └─ dọn context request
└─ afterTestMethod     ───────── dọn TestSecurityContextHolder
```

**Cả hai lựa chọn đều có thể dùng để kiểm thử request gọi trong thân `@Test`.** Mã xử lý request sẽ nhìn thấy danh tính giả lập nếu `MockMvc` được thiết lập đúng với Spring Security. Sự khác nhau lộ rõ khi `@BeforeEach` chủ động đọc context hoặc thực hiện một request cần danh tính của annotation.

Ví dụ Servlet dùng `MockMvc` trong một ứng dụng đã có controller `GET /api/reports`, endpoint yêu cầu `ROLE_READER` và cấu hình HTTP Basic:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.TestExecutionEvent;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportHttpTimingTest {

    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    void prepareFixture() {
        // Với TEST_EXECUTION, user "lan" chưa được listener gắn vào holder.
        // Có thể khởi tạo dữ liệu, mock service và các fixture ở đây.
    }

    @Test
    @WithMockUser(
            username = "lan",
            roles = "READER",
            setupBefore = TestExecutionEvent.TEST_EXECUTION
    )
    void userDuocDatTruocKhiGuiRequest() throws Exception {
        assertThat(SecurityContextHolder.getContext()
                .getAuthentication().getName()).isEqualTo("lan");

        mockMvc.perform(get("/api/reports"))
                .andExpect(status().isOk());
    }
}
```

Đây là ví dụ cần **ứng dụng Spring Boot thực tế** có endpoint và `SecurityFilterChain` đúng như giả định. Mã `@SpringBootTest` và `@AutoConfigureMockMvc` chỉ tạo cơ sở kiểm thử; chúng không tự tạo endpoint. Nếu test cấu hình `MockMvc` thủ công, có thể dùng `MockMvcBuilders.webAppContextSetup(webApplicationContext).apply(springSecurity()).build()` để tích hợp các security filter.

Trong bài kiểm thử HTTP đầy đủ, nên có cả các ca:

| Danh tính/request | Giả định chính sách `/api/reports` yêu cầu `ROLE_READER` | Kỳ vọng với HTTP Basic |
| --- | --- | --- |
| Không có người dùng | Chưa xác thực | `401 Unauthorized` |
| `@WithMockUser(roles = "GUEST")` | Đăng nhập nhưng thiếu quyền | `403 Forbidden` |
| `@WithMockUser(roles = "READER")` | Đủ quyền | `200 OK` |

Các mã trên phụ thuộc `SecurityFilterChain` và entry point thực tế; nếu ứng dụng bật form login, request chưa xác thực có thể nhận `302`. Cả `TEST_METHOD` và `TEST_EXECUTION` đều có thể kiểm chứng các ca này khi request được gửi **trong `@Test`**. Nếu dùng `@BeforeEach` để gọi endpoint có bảo vệ, chọn `TEST_METHOD` hoặc cấp danh tính tường minh cho request; `TEST_EXECUTION` chưa tạo người dùng từ annotation tại thời điểm `@BeforeEach` chạy.

### Không lấy thời điểm tạo context làm bằng chứng HTTP đã bảo vệ

Một bài test có `SecurityContextHolder.getContext().getAuthentication()` khác `null` chứng minh rằng danh tính được gắn trên **luồng test**. Nó chưa chứng minh `MockMvc` đã chạy `SecurityFilterChain`. Luôn cấu hình Spring Security vào `MockMvc` và assert response/behavior khi được phép cũng như khi bị từ chối.

Khi thực hiện nhiều request và muốn dùng danh tính của test, có thể dùng `SecurityMockMvcRequestPostProcessors.testSecurityContext()` để chỉ rõ nguồn context cho request:

```java
mockMvc.perform(get("/api/reports").with(testSecurityContext()))
        .andExpect(status().isOk());
```

Với `springSecurity()` hoặc auto-configure phù hợp, việc cấp context từ annotation thường đã được tích hợp. Lời gọi `testSecurityContext()` hữu ích khi muốn minh họa ranh giới giữa test holder và request.

## 8. Reactive, luồng nền và các giới hạn cần biết

`setupBefore` điều khiển **thời điểm** listener đặt `SecurityContext`, không phải cơ chế lan truyền bảo mật giữa các luồng.

### Servlet và tác vụ bất đồng bộ

`SecurityContextHolder` mặc định dùng `ThreadLocal` trên Servlet. Một `@WithMockUser(setupBefore = TEST_EXECUTION)` có thể gắn đúng user ngay trước `@Test` nhưng tác vụ chạy bằng `ExecutorService` vẫn không tự nhìn thấy user đó. Khi thực sự chuyển luồng, dùng các wrapper hỗ trợ như `DelegatingSecurityContextExecutorService` hoặc một executor/decorator tương ứng, và bảo đảm dọn context worker sau tác vụ. Đổi `setupBefore` không giải quyết vấn đề truyền luồng.

### WebFlux và WebTestClient

Ứng dụng Reactive dùng **Reactor Context** cho security context trong pipeline, không dựa vào một `ThreadLocal` cố định xuyên suốt. Spring Security Test có tích hợp Reactive riêng, gồm `ReactorContextTestExecutionListener` cho kiểm thử Reactive phù hợp và `SecurityMockServerConfigurers` cho `WebTestClient`:

```java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

webTestClient.mutateWith(mockUser("lan").roles("READER"))
        .get().uri("/api/reports")
        .exchange()
        .expectStatus().isOk();
```

Ví dụ giả định `WebTestClient` được tích hợp Spring Security và endpoint cho phép `ROLE_READER`. Cách cấp người dùng cho request Reactive này độc lập với lựa chọn `setupBefore` trên `@WithMockUser`; nếu code test cũng dùng annotation, cần hiểu phần listener dành cho Spring TestContext và phần Reactor Context/HTTP WebFlux phối hợp ra sao.

### JWT, OAuth2 và OIDC giả lập

Khi `MockMvc` hoặc `WebTestClient` dùng `jwt()`, `oauth2Login()`, `oidcLogin()` và các mock security configurer tương ứng, danh tính/token giả lập thường được cấp ngay trên **request**. Không nên suy ra rằng đặt `setupBefore = TEST_EXECUTION` sẽ làm token được ký, được kiểm tra chữ ký, đi qua OAuth2 Authorization Server hay trải qua đăng nhập OIDC thật.

Nếu mục tiêu là phân quyền theo claims/scope/roles, mock phù hợp. Nếu mục tiêu là xác minh JWT sai chữ ký, token hết hạn, issuer/audience hoặc luồng login thật, hãy thiết kế bài test đi qua thành phần xác thực thực tế tương ứng.

## 9. Những lỗi thường gặp khi chọn thời điểm

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `@BeforeEach` thấy user `lan` trong lúc muốn kiểm tra trạng thái chưa xác thực | Dùng mặc định `TEST_METHOD` | Cân nhắc `TEST_EXECUTION`; khi khởi tạo dữ liệu không nên giả định chưa có context nếu có listener khác |
| `@BeforeEach` gọi `getAuthentication().getName()` và gặp `NullPointerException` | Test chọn `TEST_EXECUTION` | Di chuyển code cần user vào `@Test`/sau thời điểm setup hoặc dùng `TEST_METHOD` |
| `@WithUserDetails("lan")` báo `UsernameNotFoundException` | User được tạo ở `@BeforeEach` nhưng factory chạy ở `beforeTestMethod` | Dùng `setupBefore = TEST_EXECUTION` hoặc tạo user sớm hơn |
| `@Test` không có user dù đã chú thích `@WithMockUser` | Không có Spring TestContext, thiếu listener hoặc cấu hình listener bị thay thế | Kiểm tra `SpringExtension`/`@SpringBootTest` và `@TestExecutionListeners` |
| `@AfterEach` vẫn thấy user, tưởng bị rò rỉ | Listener chưa chạy `afterTestMethod` | Đây là vòng đời bình thường; sau đó listener dọn context |
| Test thứ hai nhận danh tính của test thứ nhất | Mã tự gắn context mà không dọn, dùng biến static hoặc thay chiến lược holder toàn cục | Dùng `TestSecurityContextHolder.clearContext()`, `try/finally` và giữ test độc lập |
| Có người dùng trong `@Test` nhưng request trả `401` | `MockMvc` chưa tích hợp security filter/context từ test hoặc request chạy qua mạng thật | Tích hợp `springSecurity()`; với server thật, gửi credentials/token trong request |
| Request trả `403` dù role đúng | Rule dùng authority khác, hoặc CSRF cản request thay đổi trạng thái | Kiểm tra `roles`/`authorities` và `csrf()` trong request |
| Test Reactive mất user sau khi đổi luồng | Dùng `SecurityContextHolder` ThreadLocal để suy luận ngữ cảnh Reactor | Dùng API và mock configurer dành cho Reactor/WebFlux |

### Quy tắc chọn nhanh

Nếu `@BeforeEach` **cần đọc** người dùng mà annotation cung cấp, ưu tiên `TEST_METHOD`. Nếu `@BeforeEach` **cần tạo dữ liệu để factory tạo được** người dùng đó, chọn `TEST_EXECUTION`. Nếu chỉ có `@Test` sử dụng user giả lập, cả hai thường tương đương về kết quả; giữ mặc định để mã ngắn gọn.

Đừng dùng `@DirtiesContext` hoặc đổi `SecurityContextHolder` sang `MODE_GLOBAL` để xử lý sai lệch thời điểm. Đây là các thay đổi ở phạm vi lớn hơn, không giải quyết đúng việc listener chạy trước hay sau `@BeforeEach`.

## 10. Bài thực hành

Chuẩn bị một project Spring Security Test với JUnit Jupiter và một `UserDetailsService` kiểm thử. Hoàn thành các bước sau:

1. Viết bài test dùng `@WithMockUser` mặc định. Trong `@BeforeEach` đọc `SecurityContextHolder.getContext().getAuthentication().getName()` và xác minh người dùng đã tồn tại.
2. Chuyển annotation sang `setupBefore = TEST_EXECUTION`. Đặt assertion ở `@Test`, rồi kiểm tra rằng người dùng của annotation chưa được tạo tại `@BeforeEach` trong một context độc lập.
3. Tạo `UserDetails` trong `@BeforeEach` và dùng `@WithUserDetails` mặc định để quan sát vì sao factory có thể thất bại. Chuyển sang `TEST_EXECUTION` và kiểm chứng người dùng được nạp thành công.
4. Tạo endpoint HTTP yêu cầu `ROLE_READER`, tích hợp Spring Security vào `MockMvc` và gửi ba request với danh tính vô danh, `GUEST` và `READER`. Giải thích vì sao chọn `TEST_METHOD` hay `TEST_EXECUTION` không thay đổi rule phân quyền khi request chạy trong `@Test`.
5. Thêm `@AfterEach` để quan sát authentication khi test vừa chạy xong. Giải thích callback nào của Spring TestContext chịu trách nhiệm dọn context.
6. Tạo một bài test WebFlux tương tự với `WebTestClient.mutateWith(mockUser(...))` và so sánh thời điểm dựng context test với cách danh tính đi qua Reactor Context.

Sau khi làm xong, bạn cần phân biệt được ba câu hỏi: **context được tạo lúc nào; context được dùng ở luồng/request nào; context được dọn ở đâu?** Chọn đúng `setupBefore` giải quyết câu hỏi đầu tiên; hai câu còn lại cần hiểu cơ chế lưu và truyền ngữ cảnh của Spring Security.

## Tài liệu tham khảo

- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security API — TestExecutionEvent](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/TestExecutionEvent.html)
- [Spring Security API — WithMockUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithMockUser.html)
- [Spring Security API — WithUserDetails](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithUserDetails.html)
- [Spring Security API — WithSecurityContextTestExecutionListener](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithSecurityContextTestExecutionListener.html)
- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
