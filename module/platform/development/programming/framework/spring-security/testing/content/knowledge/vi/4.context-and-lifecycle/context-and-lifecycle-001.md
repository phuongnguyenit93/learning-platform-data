# SecurityContextHolder và phạm vi ngữ cảnh trên luồng kiểm thử

Trong các bài kiểm thử Spring Security, một phương thức có thể nhìn thấy người dùng `lan`, nhưng một tác vụ chạy ở luồng khác lại thấy không có người dùng. Tương tự, việc đặt `@WithMockUser` lên một bài test chưa có nghĩa là mọi HTTP request gửi tới ứng dụng đều mang danh tính đó. Muốn kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test`, cần hiểu **ngữ cảnh bảo mật được lưu ở đâu, có hiệu lực trong phạm vi nào và được dọn dẹp vào thời điểm nào**.

Bài học thuộc chương **Ngữ cảnh và vòng đời**, tập trung vào `SecurityContextHolder` trong ứng dụng **Servlet**, cách Spring Test cấp phát/dọn ngữ cảnh và giới hạn khi đổi luồng. Cuối bài sẽ đối chiếu với **Reactive**, nơi ngữ cảnh được truyền qua Reactor Context. Các ví dụ dùng Java, JUnit Jupiter, AssertJ và Spring Security Test.

## 1. Ba thành phần: `SecurityContextHolder`, `SecurityContext` và `Authentication`

Luồng truy cập thông thường trên Servlet:

```text
SecurityContextHolder       Điểm truy cập tĩnh đến ngữ cảnh của luồng hiện tại
        │
        ▼
SecurityContext             Vật chứa trạng thái bảo mật
        │ getAuthentication()
        ▼
Authentication              Principal, authorities, thông tin xác thực
```

Đọc danh tính hiện hành:

```java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();

if (authentication != null) {
    String username = authentication.getName();
    Collection<? extends GrantedAuthority> authorities =
            authentication.getAuthorities();
}
```

**Không đồng nhất `SecurityContext` với người dùng đã đăng nhập.** `SecurityContextHolder.getContext()` thường trả về một context rỗng ngay cả khi chưa có xác thực; lúc đó `getAuthentication()` có thể bằng `null`. Trong một request đi qua filter chain, người dùng vô danh còn có thể được biểu diễn bằng `AnonymousAuthenticationToken`. Vì vậy, muốn kiểm tra quyền truy cập, hãy kiểm tra chính sách phân quyền hoặc kết quả HTTP; chỉ thấy một đối tượng `Authentication` không đủ để kết luận request được cấp quyền.

`SecurityContextHolder` là lớp facade sử dụng `SecurityContextHolderStrategy`. Trong ứng dụng Servlet thông thường, chiến lược mặc định là **`MODE_THREADLOCAL`**, tức mỗi luồng giữ tham chiếu đến context riêng. Điều này giải thích cả việc test trên cùng một luồng có thể thấy cùng danh tính lẫn việc một luồng mới không tự nhận được danh tính của luồng tạo ra nó.

## 2. Phạm vi trên luồng: điều gì được kế thừa và điều gì không?

| Tình huống | Kết quả khi dùng `MODE_THREADLOCAL` mặc định |
| --- | --- |
| Đọc `SecurityContextHolder` nhiều lần trên cùng luồng, chưa thay đổi/dọn context | Nhìn thấy context hiện tại của luồng đó |
| Tạo `new Thread(...)` rồi đọc trong luồng con | Không tự mang `Authentication` của luồng test sang |
| Gửi tác vụ vào `ExecutorService` | Tác vụ chạy trên luồng worker; không tự mang context của luồng gọi |
| Chuyển sang bài test kế tiếp | Spring Security Test dọn ngữ cảnh của bài trước qua listener; không được trông chờ danh tính tồn tại tiếp |
| Gửi HTTP request thật đến server đang chạy | Server xử lý ở luồng/request khác; context ở luồng test không tự đi theo request |
| Đi qua pipeline WebFlux/Reactor | Ngữ cảnh bảo mật được truyền theo **Reactor Context**, không thể suy ra từ thread-local đơn thuần |

Ví dụ sau chỉ ra ranh giới luồng. Giả sử dự án có `spring-security-test`, Spring Test và một ứng dụng Spring Boot để `@SpringBootTest` khởi tạo:

```java
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class SecurityContextThreadScopeTest {

    @Test
    @WithMockUser(username = "lan", roles = "READER")
    void contextKhongTuTruyenSangLuongMoi() throws InterruptedException {
        Authentication onTestThread =
                SecurityContextHolder.getContext().getAuthentication();
        assertThat(onTestThread.getName()).isEqualTo("lan");

        AtomicReference<Authentication> onChildThread = new AtomicReference<>();
        Thread child = new Thread(() -> onChildThread.set(
                SecurityContextHolder.getContext().getAuthentication()));

        child.start();
        child.join();

        assertThat(onChildThread.get()).isNull();
    }
}
```

Chú ý: nhận định `null` ở luồng mới áp dụng cho chiến lược `MODE_THREADLOCAL` mặc định và luồng mới chưa bị mã khác đặt danh tính. Nếu toàn bộ tiến trình đã đổi sang một chiến lược khác, kết quả có thể khác.

Spring Security cũng cung cấp `MODE_INHERITABLETHREADLOCAL` và `MODE_GLOBAL`, nhưng **không nên đổi `SecurityContextHolder.setStrategyName(...)` trong một bài test thông thường** để chữa lỗi truyền ngữ cảnh: đây là cấu hình tĩnh ảnh hưởng toàn JVM, dễ tác động đến những test khác. `MODE_INHERITABLETHREADLOCAL` chỉ kế thừa tại lúc tạo luồng con, không giải quyết đúng ngữ nghĩa truyền context cho tác vụ trên thread pool; `MODE_GLOBAL` chia sẻ trạng thái rộng hơn mức an toàn cho các test song song.

## 3. Ai thiết lập và dọn ngữ cảnh của `@WithMockUser`?

`@WithMockUser` thuộc `spring-security-test`. Khi chạy với Spring TestContext Framework (ví dụ `@SpringBootTest`, `@WebMvcTest` hoặc `@ExtendWith(SpringExtension.class)`), **`WithSecurityContextTestExecutionListener`** xử lý annotation này. Listener tạo `SecurityContext` chứa `UsernamePasswordAuthenticationToken` giả lập, gắn nó cho luồng chạy test và dọn sau bài test.

Với JUnit Jupiter, trình tự mặc định có thể đọc như sau:

```text
WithSecurityContextTestExecutionListener.beforeTestMethod
    └── thiết lập Authentication từ @WithMockUser
@BeforeEach
@Test
@AfterEach
WithSecurityContextTestExecutionListener.afterTestMethod
    └── dọn SecurityContext của bài test
```

Do đó, ở chế độ mặc định, `@BeforeEach` có thể đọc được người dùng do `@WithMockUser` thiết lập. Có thể thay thời điểm bằng `setupBefore = TestExecutionEvent.TEST_EXECUTION`: context sẽ được đặt **sau `@BeforeEach` nhưng trước khi chạy phương thức `@Test`**.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.TestExecutionEvent;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class SecurityContextLifecycleTest {

    @BeforeEach
    void beforeEach() {
        // Ví dụ này minh họa mặc định TEST_METHOD:
        // listener đã đặt người dùng trước @BeforeEach.
        assertThat(SecurityContextHolder.getContext()
                .getAuthentication().getName()).isEqualTo("lan");
    }

    @Test
    @WithMockUser(username = "lan", roles = "READER")
    void docDuocNguoiDungTrongTest() {
        assertThat(SecurityContextHolder.getContext()
                .getAuthentication().getAuthorities())
                .extracting("authority")
                .contains("ROLE_READER");
    }
}
```

**Nếu chọn `TEST_EXECUTION`, không dùng lại giả định trong `@BeforeEach` ở ví dụ trên**: lúc `@BeforeEach` chạy, người dùng từ annotation chưa được tạo. Cách xác định thời điểm hữu ích khi `@BeforeEach` cần tạo dữ liệu trước khi dựng `SecurityContext` tùy biến; khi đó dùng:

```java
@Test
@WithMockUser(username = "lan",
              setupBefore = TestExecutionEvent.TEST_EXECUTION)
void taoSecurityContextSauBeforeEach() {
    // Ở đây Authentication của "lan" đã được đặt.
}
```

Một vài điểm cần nhớ:

- `@WithMockUser(roles = "READER")` tạo authority `ROLE_READER`; `authorities = "report:read"` giữ nguyên chuỗi, không tự thêm `ROLE_`.
- Đây là **danh tính giả lập cho bài test**: annotation không gọi quy trình đăng nhập, không xác thực mật khẩu, JWT hay token OAuth2 thực.
- Annotation có thể đặt ở cấp lớp; annotation ở phương thức cho phép xác định danh tính của trường hợp riêng. Dùng `@WithAnonymousUser` cho trường hợp vô danh ngay cả khi lớp có người dùng mặc định.
- Listener quản lý vòng đời của ngữ cảnh do annotation tạo. Không dựa vào thứ tự chạy test, không giữ một `SecurityContext` ở biến static để tái sử dụng giữa các bài.

## 4. Tự tạo ngữ cảnh: luôn sở hữu việc dọn dẹp

Khi không dùng `@WithMockUser`, test thuần có thể tự xây `Authentication`. Nên tạo một `SecurityContext` mới rồi đặt vào holder, thay vì sửa đối tượng context đang được dùng ở nơi khác.

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.assertj.core.api.Assertions.assertThat;

class ManualSecurityContextTest {

    @Test
    void tuDatVaDonSecurityContext() {
        try {
            Authentication authentication =
                    new UsernamePasswordAuthenticationToken(
                            "lan", "N/A",
                            AuthorityUtils.createAuthorityList("ROLE_READER"));

            SecurityContext context = SecurityContextHolder.createEmptyContext();
            context.setAuthentication(authentication);
            SecurityContextHolder.setContext(context);

            assertThat(SecurityContextHolder.getContext()
                    .getAuthentication().getName()).isEqualTo("lan");
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
```

`finally` bảo đảm dọn context ngay cả khi assertion ném lỗi. Nếu chủ động thay context bên trong một phạm vi vốn đã có danh tính do framework quản lý, cần cân nhắc **khôi phục context trước đó** thay vì xóa mất context của tầng gọi. Trong bài test tự cấp phát độc lập như ví dụ, `clearContext()` là cách dễ kiểm soát nhất.

Thư viện test còn có `TestSecurityContextHolder` để hỗ trợ quản lý context trong các tình huống tích hợp test; khi dùng API này, nhớ rằng `TestSecurityContextHolder.clearContext()` phục vụ dọn cả trạng thái test liên quan. Đừng trộn các cách thiết lập thủ công với `@WithMockUser` trong cùng một bài khi không có lý do rõ ràng: giá trị đặt sau sẽ thay thế giá trị trước trên luồng hiện tại.

## 5. Chạy bất đồng bộ: truyền context có chủ đích

Giả sử một hàm được bảo vệ bởi `@PreAuthorize` được gọi trong `ExecutorService`. Khi test thread có `@WithMockUser` nhưng worker thread không có authentication, phương thức có thể bị từ chối dù kiểm tra trên test thread cho thấy đúng người dùng. Cách xử lý là truyền ngữ cảnh tại **ranh giới gửi tác vụ**.

Spring Security hỗ trợ các wrapper như `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor` và `DelegatingSecurityContextExecutorService`. Ví dụ với pool:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutorService;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class SecurityContextAsyncTest {

    @Test
    @WithMockUser(username = "lan", roles = "READER")
    void truyenContextVaoExecutor() throws Exception {
        ExecutorService original = Executors.newSingleThreadExecutor();
        try {
            ExecutorService secured =
                    new DelegatingSecurityContextExecutorService(original);

            Future<String> result = secured.submit(() ->
                    SecurityContextHolder.getContext()
                            .getAuthentication().getName());

            // get() đưa lỗi từ tác vụ về luồng test và giúp kiểm chứng kết quả.
            assertThat(result.get(3, TimeUnit.SECONDS)).isEqualTo("lan");
        } finally {
            original.shutdownNow();
        }
    }
}
```

Với constructor chỉ nhận `ExecutorService` như trên, wrapper lấy ngữ cảnh hiện tại khi bọc tác vụ gửi đi; wrapper thiết lập context trong luồng worker và dọn sau khi tác vụ kết thúc. Nếu dùng biến thể constructor nhận một `SecurityContext` cố định, các tác vụ dùng context được cấp đó; cần chọn đúng cách để không vô tình dùng chung danh tính cho nhiều lượt gửi.

Khi ứng dụng dùng `@Async`, có thể cấu hình executor tương thích với bảo mật (chẳng hạn `DelegatingSecurityContextAsyncTaskExecutor`). Trong bài test, nên kiểm chứng **đúng điểm chuyển luồng thực tế của ứng dụng**. Đừng tự gọi `SecurityContextHolder.setContext(...)` trong một tác vụ pool mà bỏ qua `finally`: pool tái sử dụng worker nên context tồn dư có thể làm bài kiểm thử sau chạy với danh tính sai. Cũng không nên dùng chung một context có thể bị thay đổi giữa nhiều tác vụ song song nếu không kiểm soát được việc chia sẻ trạng thái.

## 6. Từ luồng test đến HTTP request Servlet với `MockMvc`

Hai phạm vi thường bị nhầm lẫn:

1. **Context của phương thức test:** `@WithMockUser` và `SecurityContextHolder` trên luồng chạy JUnit.
2. **Context của request:** được sử dụng bởi chuỗi Spring Security filter khi `MockMvc` thực thi một HTTP request giả lập.

Với `MockMvc`, cần nối hỗ trợ Spring Security vào quá trình xử lý request. Trong ứng dụng Spring Boot có `spring-security-test` và `@AutoConfigureMockMvc`, cấu hình test thường tự tích hợp các security filter; khi dựng `MockMvc` thủ công bằng `webAppContextSetup(...)`, có thể dùng `.apply(springSecurity())` với cấu hình phù hợp. Nếu dựng `standaloneSetup(...)` mà không đưa security filter vào, test trả HTTP 200 **không chứng minh** lớp bảo vệ HTTP đã hoạt động.

`@WithMockUser` phù hợp để cấp danh tính mặc định cho test tích hợp với `MockMvc`. Nếu muốn mỗi request mang một danh tính riêng, sử dụng request postprocessor `with(user(...))`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportHttpSecurityTest {

    @Autowired MockMvc mvc;

    // Giả định GET /api/reports tồn tại, yêu cầu ROLE_ADMIN,
    // và ứng dụng cấu hình HTTP Basic để anonymous nhận 401.

    @Test
    void chuaDangNhapThiBiTuChoi() throws Exception {
        mvc.perform(get("/api/reports"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void daDangNhapNhungSaiVaiTroThiNhan403() throws Exception {
        mvc.perform(get("/api/reports")
                .with(user("lan").roles("READER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void dungVaiTroThiDuocTruyCap() throws Exception {
        mvc.perform(get("/api/reports")
                .with(user("mai").roles("ADMIN")))
                .andExpect(status().isOk());
    }
}
```

Ví dụ giả định chính sách sau trong `SecurityFilterChain`:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/reports").hasRole("ADMIN")
        .anyRequest().authenticated())
    .httpBasic(Customizer.withDefaults());
```

Không mặc định mọi hệ thống đều trả `401` cho request vô danh: ứng dụng bật form login có thể chuyển hướng `302`, ứng dụng có entry point khác có thể trả mã khác. Trong ví dụ, HTTP Basic được nêu rõ để kết quả `401`/`403` có nghĩa cụ thể. `with(user(...))` và `@WithMockUser` tạo authentication giả lập, vì vậy bộ kiểm thử này đo được **quy tắc phân quyền HTTP** khi filter chain hoạt động, nhưng chưa chứng minh quy trình kiểm tra mật khẩu hoặc chữ ký token thực.

Đối với Servlet request, `SecurityContextHolderFilter` hoặc `SecurityContextPersistenceFilter` tham gia tải context từ `SecurityContextRepository`; filter phù hợp chịu trách nhiệm dọn trạng thái theo request. Hai filter khác nhau ở **cách lưu**: `SecurityContextHolderFilter` chỉ đọc, còn lưu thay đổi cần thực hiện tường minh; `SecurityContextPersistenceFilter` có cơ chế lưu tự động theo vòng đời của nó. Đặt context trên một luồng test **không đồng nghĩa** đã lưu trạng thái đăng nhập cho HTTP request sau đó hay đã tạo session người dùng.

Một khác biệt nữa: `@SpringBootTest(webEnvironment = RANDOM_PORT)` và HTTP client gọi một server đang chạy thật sẽ đi qua socket tới luồng server. `@WithMockUser` chỉ chuẩn bị test thread; nó không tự thêm thông tin đăng nhập vào HTTP request qua mạng. Với bài test kiểu này, hãy đưa thông tin xác thực vào request (HTTP Basic, bearer token phù hợp, cookie/session hợp lệ...) và xác minh phản hồi.

## 7. Reactive: `ReactiveSecurityContextHolder` theo Reactor Context

Trong WebFlux, pipeline có thể đổi luồng khi đi qua `publishOn`, `subscribeOn` hoặc các tác vụ bất đồng bộ. Spring Security Reactive sử dụng **Reactor Context**, không thể dựa vào `SecurityContextHolder.getContext()` ở một luồng bất kỳ để xác định người dùng của cả pipeline.

Phía mã Reactive, có thể lấy context bằng:

```java
Mono<String> currentUsername = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
```

Đoạn này phải được **subscribe trong một pipeline có security context**, nếu không `Mono` có thể không phát ra tên người dùng. Nó không tương đương với việc đọc biến thread-local bên ngoài pipeline.

Với `WebTestClient` đã gắn bộ hỗ trợ Spring Security (ví dụ bean được cấu hình trong `@WebFluxTest`), có thể mô phỏng danh tính ở phạm vi request bằng `mutateWith(mockUser(...))`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@WebFluxTest
class ReactiveRoleTest {

    @Autowired WebTestClient client;

    // Giả định GET /api/admin chỉ cho phép ROLE_ADMIN.
    @Test
    void nguoiDungReaderBiCam() {
        client.mutateWith(mockUser("lan").roles("READER"))
                .get().uri("/api/admin")
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Chú ý thêm cấu hình Security WebFlux và handler/router tương ứng để ví dụ chạy được trong dự án; `@WebFluxTest` giới hạn thành phần được khởi tạo nên có thể cần `@Import` cấu hình bảo mật. `@WithMockUser` cũng được hỗ trợ khi `WebTestClient` đã được tích hợp Spring Security, nhưng lúc đó framework làm việc để truyền danh tính vào xử lý request Reactive; không thể tự suy ra rằng thread-local sẽ đi xuyên suốt Reactor pipeline.

## 8. Chọn công cụ theo phạm vi cần kiểm chứng

| Điều muốn chứng minh | Thiết lập phù hợp | Bằng chứng nên kiểm tra |
| --- | --- | --- |
| Dịch vụ bảo vệ bởi method security nhận đúng người dùng trên luồng test | `@WithMockUser`, `@WithUserDetails` hoặc context tự tạo | Kết quả gọi phương thức, `AccessDeniedException` hoặc giá trị phù hợp |
| Quy tắc cấp quyền HTTP trên Servlet | `MockMvc` có security filter, `@WithMockUser` hoặc `.with(user(...))` | `401`/`403`/`200` theo cấu hình endpoint |
| Xác thực của server chạy trên cổng thật | HTTP client mang credentials hoặc token thật | Phản hồi từ server và phản ứng với thông tin xác thực sai |
| Danh tính trong `ExecutorService`/`@Async` | Wrapper/decorator truyền `SecurityContext` đúng thời điểm | Kết quả `Future`/tác vụ và kiểm tra lỗi phát sinh |
| Phân quyền WebFlux | `WebTestClient` + Spring Security, `mockUser()`, `mockJwt()` khi cần | Trạng thái HTTP hoặc giá trị trong reactive pipeline |

Các dấu hiệu lỗi hay gặp khi gỡ lỗi test:

- **Test thread nhìn thấy `lan` nhưng worker thread thấy `null`:** kiểm tra `MODE_THREADLOCAL`, nơi gọi executor và cách context được truyền vào tác vụ.
- **Test có `@WithMockUser` nhưng MockMvc vẫn không kích hoạt rule:** kiểm tra việc dựng `MockMvc`, bộ lọc Spring Security và chính sách endpoint.
- **Bài test trả `200` dù chưa cấu hình security filter:** test có thể chỉ đang gọi controller, chưa kiểm tra bảo vệ HTTP.
- **Bài test độc lập đôi lúc dùng nhầm danh tính từ bài khác:** tìm `setContext(...)` không có `finally`, biến static lưu context hoặc thay đổi chiến lược holder toàn cục.
- **Test với server thật không thấy user từ annotation:** thêm xác thực vào request gửi qua mạng.
- **WebFlux đọc thread-local sai người dùng:** chuyển sang `ReactiveSecurityContextHolder` hoặc API nhận principal trong reactive chain.

## 9. Bài thực hành tự kiểm tra

Trên một dự án mẫu có Servlet endpoint `GET /api/reports` yêu cầu `ROLE_ADMIN`, hãy hoàn thành ba bài test độc lập:

1. Dùng `@WithMockUser(username = "lan", roles = "READER")` để kiểm tra tên và authority trong test thread; tạo `new Thread(...)` và xác nhận authentication không tự được truyền sang.
2. Bọc `ExecutorService` bằng `DelegatingSecurityContextExecutorService`, gửi `Callable<String>` đọc tên người dùng và dùng `Future.get()` kiểm chứng worker nhận `lan`.
3. Gửi ba request bằng `MockMvc` có security filter: vô danh, `READER` và `ADMIN`. Với HTTP Basic, kỳ vọng lần lượt `401`, `403`, `200`. Sau đó thử bỏ tích hợp filter trên một cấu hình test độc lập và giải thích vì sao kết quả không còn chứng minh phân quyền nữa.

Nếu làm phần mở rộng với WebFlux, viết test tương tự bằng `WebTestClient.mutateWith(mockUser(...))`; quan sát rằng việc bảo toàn danh tính đi theo Reactor Context chứ không theo giả định một request luôn chạy trên một luồng.

**Điểm cốt lõi:** trên Servlet, `SecurityContextHolder` mặc định gắn context với luồng đang chạy; `spring-security-test` quản lý context của test qua listener, còn security filter quản lý context của request. Qua ranh giới luồng hoặc HTTP thật cần truyền thông tin đúng cơ chế. Trên Reactive, phải dựa vào Reactor Context. Phân biệt các phạm vi này giúp test xác thực và phân quyền đúng nơi, đồng thời tránh nhiễm trạng thái giữa các bài.

### Tài liệu tham khảo

- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html)
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — Reactive Testing Authentication](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html)
