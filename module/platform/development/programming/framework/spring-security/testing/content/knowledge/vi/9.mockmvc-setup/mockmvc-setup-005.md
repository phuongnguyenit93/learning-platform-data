# Vai trò của bộ xử lý TestSecurityContextHolder trong request

## Mục tiêu bài học

Trong mô-đun **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Bài này tập trung vào **Servlet/Spring MVC với MockMvc**, giải thích cách `TestSecurityContextHolder` và bộ xử lý ngữ cảnh bảo mật của Spring Security Test đưa danh tính được khai báo trong test vào từng request.

Sau bài học, bạn có thể:

1. Phân biệt `SecurityContextHolder` của ứng dụng với `TestSecurityContextHolder` dành cho kiểm thử.
2. Mô tả vòng đời từ `@WithMockUser` đến request của MockMvc, qua security filters và controller.
3. Hiểu vai trò của `TestSecurityContextHolderPostProcessor` khi áp dụng `SecurityMockMvcConfigurers.springSecurity()`.
4. Chọn giữa `@WithMockUser`, `with(user(...))`, `with(authentication(...))` và cách thiết lập context thủ công.
5. Tránh context cũ rò rỉ giữa test, nhầm lẫn với session đăng nhập thật và những ca kiểm thử cho kết quả sai.

## 1. Hai SecurityContextHolder với hai mục đích

Trong Spring Security, `SecurityContextHolder` là nơi code ứng dụng truy cập danh tính hiện tại thông qua `SecurityContextHolder.getContext().getAuthentication()`. Trên ứng dụng Servlet, nó thường dùng chiến lược lưu trữ theo thread; các security filters thiết lập context trước khi xử lý request và dọn dẹp sau khi request hoàn tất.

Trong kiểm thử, Spring Security Test cung cấp `TestSecurityContextHolder`. Nó giữ trạng thái xác thực do test chuẩn bị để trạng thái đó có thể được chuyển vào request MockMvc ngay cả khi `SecurityContextHolder` của ứng dụng bị filter làm sạch sau một lần xử lý.

| Thành phần | Mục đích | Ai sử dụng? |
| --- | --- | --- |
| `SecurityContextHolder` | Truy cập `SecurityContext` của luồng xử lý hiện tại | Filter, controller, service, code ứng dụng |
| `SecurityContext` | Chứa `Authentication` và các thông tin liên quan | Spring Security và ứng dụng |
| `TestSecurityContextHolder` | Giữ context dành cho test, hỗ trợ chuyển context đó vào request mock | Spring Security Test và test code |
| `TestSecurityContextHolderPostProcessor` | Gắn context đang lưu trong test holder vào request MockMvc | Cơ chế tích hợp MockMvc của Spring Security Test |
| `WithSecurityContextTestExecutionListener` | Chuẩn bị và dọn context khi test dùng `@WithMockUser` hoặc `@WithSecurityContext` | Spring Test / Spring Security Test |

Điều quan trọng là **hai holder không thay thế nhau**. Controller và service vẫn đọc `SecurityContextHolder` như khi ứng dụng chạy thật. `TestSecurityContextHolder` là nơi test giữ trạng thái xác thực để tích hợp đó có thể tái tạo nó trong từng request.

## 2. Vì sao cần TestSecurityContextHolderPostProcessor?

Một test có thể khai báo:

~~~java
@Test
@WithMockUser(username = "linh", roles = "EDITOR")
void editorCanReadProfile() {
    // Gọi MockMvc ở đây
}
~~~

`@WithMockUser` được Spring Security Test xử lý thông qua `WithSecurityContextTestExecutionListener`. Listener chuẩn bị một `SecurityContext` có `Authentication` giả lập cho test. Nhưng một request HTTP đi qua filter chain có vòng đời riêng: filter bảo mật có thể tải context từ request/session repository, thay thế context đang có trong thread và dọn context sau khi request kết thúc.

Nếu chỉ đặt context trên thread của test rồi gọi MockMvc mà không tích hợp đúng, trạng thái có thể không đến được request theo cách bạn mong đợi. Spring Security Test giải quyết vấn đề này bằng bộ xử lý `TestSecurityContextHolderPostProcessor`.

Khi dùng:

~~~java
MockMvc mockMvc = webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

`SecurityMockMvcConfigurers.springSecurity()` cấu hình filter bảo mật của application context vào MockMvc và đăng ký hỗ trợ xử lý test security context. Bộ xử lý lấy context đang lưu trong `TestSecurityContextHolder`, đưa nó vào request mock để security filters có thể sử dụng khi tải context cho lần xử lý đó.

~~~mermaid
sequenceDiagram
    participant T as JUnit Test
    participant L as WithSecurityContextTestExecutionListener
    participant H as TestSecurityContextHolder
    participant P as TestSecurityContextHolderPostProcessor
    participant F as Spring Security Filters
    participant C as Controller
    T->>L: Bắt đầu test có @WithMockUser
    L->>H: Đặt SecurityContext giả lập
    T->>P: mockMvc.perform(request)
    P->>H: Đọc context của test
    P->>F: Gắn context vào request
    F->>F: Tải SecurityContext và kiểm tra quyền
    F->>C: Chuyển request nếu được phép
    C-->>T: Response để andExpect(...)
    Note over F: Filter dọn SecurityContextHolder sau request
    T->>L: Kết thúc test
    L->>H: Dọn context kiểm thử
~~~

Tên lớp `TestSecurityContextHolderPostProcessor` mô tả nhiệm vụ ở ranh giới **test context → mock request**. Bạn thường không cần tự khởi tạo lớp này; hãy dùng `springSecurity()` để cài đặt tích hợp theo đúng cơ chế Spring Security Test.

## 3. Vòng đời của một request có danh tính giả lập

Có thể chia quá trình thành bốn giai đoạn:

**Trước test method:** Spring Test gọi listener của Spring Security Test. Với `@WithMockUser`, listener tạo một authentication giả lập và đặt context vào hạ tầng test security context. Thời điểm thiết lập mặc định là trước khi chạy test method; annotation cho phép thay đổi thời điểm bằng thuộc tính `setupBefore`.

**Khi tạo request:** `TestSecurityContextHolderPostProcessor` (được tích hợp khi cấu hình MockMvc bằng `springSecurity()`) chuyển context của test vào request. Các request post-processor như `with(user(...))` cũng có thể chuẩn bị authentication riêng cho request đó.

**Trong security filter chain:** Filter bảo mật tải `SecurityContext` cho request, thực hiện các bước xác thực/phân quyền/CSRF theo cấu hình ứng dụng. Nếu request được phép, nó tiếp tục tới `DispatcherServlet` và controller. Code ứng dụng vẫn đọc danh tính qua `SecurityContextHolder`.

**Sau request và sau test:** Các filter dọn `SecurityContextHolder` theo vòng đời request. Test holder giữ trạng thái kiểm thử cho tới khi listener dọn dẹp theo vòng đời test. Vì vậy test tiếp theo không nên nhận lại danh tính của test trước.

### Sơ đồ vòng đời ngắn

~~~text
@WithMockUser
    ↓
WithSecurityContextTestExecutionListener
    ↓
TestSecurityContextHolder (test identity)
    ↓ TestSecurityContextHolderPostProcessor
MockHttpServletRequest
    ↓
SecurityContextRepository / security filters
    ↓
SecurityContextHolder (request processing)
    ↓
Controller / Service
    ↓
Filter cleanup → test listener cleanup
~~~

Trong mô hình trên, `SecurityContextRepository` có thể tải context từ session hoặc request attribute tùy cấu hình. Bộ xử lý của Spring Security Test phục vụ việc đưa context giả lập vào request mock; nó không tự biến danh tính đó thành một phiên đăng nhập bền vững của người dùng trong hệ thống.

## 4. Ví dụ hoàn chỉnh với @WithMockUser

### 4.1. Cấu hình ứng dụng

Ví dụ sử dụng Spring Boot Servlet, HTTP Basic và một endpoint trả về tên người dùng hiện tại.

Tệp `src/main/java/example/DemoApplication.java`:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Tệp `src/main/java/example/ProfileController.java`:

~~~java
package example;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {
    @GetMapping("/api/profile")
    String profile(Principal principal) {
        return principal.getName();
    }
}
~~~

Tệp `src/main/java/example/SecurityConfiguration.java`:

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/profile").authenticated()
                .anyRequest().permitAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

### 4.2. Tạo MockMvc với springSecurity()

Tệp `src/test/java/example/TestSecurityContextHolderTest.java`:

~~~java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class TestSecurityContextHolderTest {
    @Autowired
    WebApplicationContext context;

    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = webAppContextSetup(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void anonymousRequestIsRejected() throws Exception {
        mockMvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "linh", roles = "USER")
    void annotationContextIsAvailableToRequest() throws Exception {
        mockMvc.perform(get("/api/profile"))
            .andExpect(status().isOk())
            .andExpect(content().string("linh"));
    }

    @Test
    void requestCanUseItsOwnUser() throws Exception {
        mockMvc.perform(get("/api/profile")
                .with(user("mai").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("mai"));
    }
}
~~~

Test `annotationContextIsAvailableToRequest` là ca thể hiện rõ vai trò của bộ xử lý: test khai báo danh tính bằng annotation, không cần tự gắn `with(user(...))` vào request, nhưng controller vẫn nhận được principal `linh` vì test context đã được chuyển vào request qua tích hợp Spring Security.

Test `requestCanUseItsOwnUser` cho thấy một lựa chọn khác: danh tính được đặt ngay trên request. Cách này hữu ích khi một test cần gọi nhiều request với những người dùng khác nhau.

### 4.3. Kết quả kỳ vọng

| Test | Nguồn danh tính | Kết quả |
| --- | --- | --- |
| `anonymousRequestIsRejected` | Không có danh tính | 401 |
| `annotationContextIsAvailableToRequest` | `@WithMockUser("linh")` → test holder → request | 200, body `linh` |
| `requestCanUseItsOwnUser` | `with(user("mai"))` trên request | 200, body `mai` |

Các status trên phù hợp với HTTP Basic trong ví dụ. Nếu ứng dụng dùng form login, request ẩn danh có thể nhận 302 redirect thay vì 401.

## 5. Phân biệt @WithMockUser và with(user(...))

Hai cách thường được dùng thay thế nhau trong test nhưng phạm vi tác động khác nhau:

| Tiêu chí | `@WithMockUser` | `with(user(...))` |
| --- | --- | --- |
| Phạm vi | Test method hoặc class | Một request cụ thể |
| Cách chuẩn bị | Test execution listener và `TestSecurityContextHolder` | Request post-processor |
| Có cần `springSecurity()` để test đầy đủ security pipeline? | Có | Có |
| Một test nhiều danh tính | Cần thay đổi context theo cách khác hoặc dùng request post-processor | Dễ dàng gắn user khác cho từng request |
| Mục tiêu điển hình | Nhiều assertion trong một test dùng cùng danh tính | Request riêng cần principal/authority riêng |
| Kiểm tra mật khẩu thật? | Không | Không |

Ví dụ hai người dùng trong một test:

~~~java
@Test
void twoUsersCanBeTestedInOneMethod() throws Exception {
    mockMvc.perform(get("/api/profile")
            .with(user("alice").roles("USER")))
        .andExpect(status().isOk())
        .andExpect(content().string("alice"));

    mockMvc.perform(get("/api/profile")
            .with(user("bob").roles("USER")))
        .andExpect(status().isOk())
        .andExpect(content().string("bob"));
}
~~~

`with(user(...))` không cần thay đổi danh tính mặc định của toàn test method. Nó giúp tránh phụ thuộc vào trạng thái context dùng chung khi cần mô phỏng nhiều request độc lập.

### Khi nào dùng with(authentication(...))?

Khi cần principal hoặc authority tùy chỉnh, có thể dựng `Authentication` rồi gắn vào request:

~~~java
Authentication authentication =
    new UsernamePasswordAuthenticationToken(
        "service-user",
        "N/A",
        List.of(new SimpleGrantedAuthority("REPORT_READ"))
    );

mockMvc.perform(get("/api/reports")
        .with(authentication(authentication)))
    .andExpect(status().isOk());
~~~

Đoạn ví dụ giả định route `/api/reports` được cấu hình yêu cầu authority `REPORT_READ` và đã có các import `org.springframework.security.core.Authentication`, `UsernamePasswordAuthenticationToken`, `SimpleGrantedAuthority`, `java.util.List`. Đây vẫn là **authentication giả lập**: nó kiểm tra luật phân quyền nhận một principal có authority tương ứng, không chạy cơ chế xác minh credentials.

## 6. Tự thiết lập TestSecurityContextHolder khi thật sự cần

Thông thường, hãy ưu tiên `@WithMockUser` hoặc request post-processor. Nếu một bài test cần thiết lập context động ngoài annotation, `TestSecurityContextHolder` có API để đặt và đọc context:

~~~java
SecurityContext testContext = SecurityContextHolder.createEmptyContext();
testContext.setAuthentication(
    UsernamePasswordAuthenticationToken.authenticated(
        "operator",
        "N/A",
        List.of(new SimpleGrantedAuthority("ROLE_OPERATOR"))
    )
);

TestSecurityContextHolder.setContext(testContext);
try {
    mockMvc.perform(get("/api/profile"))
        .andExpect(status().isOk());
} finally {
    TestSecurityContextHolder.clearContext();
}
~~~

Các import cần thiết gồm `org.springframework.security.core.context.SecurityContext`, `SecurityContextHolder`, `TestSecurityContextHolder`, `UsernamePasswordAuthenticationToken`, `SimpleGrantedAuthority` và `java.util.List`. Controller ở ví dụ mục 4 trả tên principal nên request sẽ nhận tên `operator`.

**Luôn dọn context trong `finally`** nếu tự thiết lập thủ công. Nếu không, trạng thái có thể rò rỉ sang request hoặc test khác trong cùng thread. API `TestSecurityContextHolder.clearContext()` được thiết kế để dọn trạng thái test holder; không dựa vào việc filter tự làm sạch holder dành cho test.

Không nên dùng `SecurityContextHolder.setContext(...)` làm cách mặc định để giả lập user trước khi gọi MockMvc. Filter chain có thể nạp context từ repository cho request và ghi đè hoặc dọn context thread hiện tại. Hãy đặt context qua cơ chế test được hỗ trợ để nó được chuyển đúng vào request.

## 7. Thời điểm chuẩn bị và dọn SecurityContext

`@WithMockUser` và `@WithSecurityContext` cho phép điều khiển thời điểm chuẩn bị context bằng thuộc tính `setupBefore`:

~~~java
@Test
@WithMockUser(
    username = "linh",
    roles = "USER",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
void contextIsPreparedBeforeTestExecution() throws Exception {
    mockMvc.perform(get("/api/profile"))
        .andExpect(status().isOk());
}
~~~

Giá trị mặc định là `TestExecutionEvent.TEST_METHOD`, tức context được chuẩn bị trước khi thực thi test method theo vòng đời listener. `TEST_EXECUTION` cho phép chuẩn bị muộn hơn, trước giai đoạn test execution. Khác biệt có ý nghĩa khi test dùng các callback của JUnit hoặc listener khác cần quan sát trạng thái bảo mật ở thời điểm cụ thể. Đừng đổi thời điểm nếu không có yêu cầu vòng đời rõ ràng.

Các điểm cần nhớ về cleanup:

- `WithSecurityContextTestExecutionListener` thiết lập context cho test và dọn sau test theo vòng đời của nó.
- `SecurityContextHolder` của ứng dụng được Spring Security filters dọn sau khi request kết thúc.
- `TestSecurityContextHolder` phục vụ trạng thái của test; nếu tự đặt thủ công thì test phải chủ động dọn.
- Nếu dùng `@DirtiesContext` hoặc chạy song song, đó không phải cách thay thế cho quản lý vòng đời context đúng cách.

Một test độc lập có thể chạy đúng trong isolation nhưng thất bại khi cả suite chạy chung nếu context thủ công không được dọn hoặc có shared mutable state.

## 8. TestSecurityContextHolder không phải session đăng nhập thật

Một hiểu lầm thường gặp là `@WithMockUser` tạo phiên đăng nhập cho người dùng. Thực tế, annotation tạo `Authentication` giả lập cho test; nó không:

- Gửi username/password đến login endpoint.
- Kiểm tra password encoder hoặc user store.
- Chạy quy trình đăng nhập form, HTTP Basic hay xác thực ngoài theo cách của client thật.
- Tự lưu một phiên đăng nhập bền vững vào HTTP session để request kế tiếp từ client khác dùng lại.
- Xác minh chữ ký, issuer, audience hoặc hạn dùng của JWT thật.

Nếu muốn kiểm tra session được lưu và khôi phục, cần viết test mô phỏng quy trình đăng nhập phù hợp: gửi request tới endpoint login, nhận session/cookie, sau đó gửi request tiếp theo với cùng session và xác minh danh tính được khôi phục qua `SecurityContextRepository`. `TestSecurityContextHolder` không thay thế kiểm thử này.

Tương tự, `with(jwt())` có thể tạo `JwtAuthenticationToken` giả lập để kiểm tra scope/authority; muốn kiểm chứng decoder và validator, gửi bearer token thực qua filter chain đã cấu hình.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@WithMockUser` nhưng controller không thấy principal | Thiếu tích hợp `springSecurity()` hoặc MockMvc đang dùng không phải instance đã cấu hình | Dựng bằng `webAppContextSetup(context).apply(springSecurity())` hoặc dùng Boot auto-config |
| Có bean `TestSecurityContextHolder` nhưng request vẫn 401 | Test holder không tự gắn vào request nếu thiếu cơ chế tích hợp | Kiểm tra `springSecurity()` và post-processor |
| Request không có `@WithMockUser` lại trả 200 | Security filters không chạy hoặc matcher cho phép truy cập | Thêm ca bị từ chối và xác minh chain/matcher |
| Test kế tiếp nhận danh tính cũ | Test tự đặt context nhưng không dọn | Dùng `try/finally` và `TestSecurityContextHolder.clearContext()` |
| `with(user(...))` không có tác dụng | Request dùng một MockMvc không có security filters hoặc processor không áp dụng cho request đang gọi | Kiểm tra instance và vị trí `.with(...)` |
| POST trả 403 dù role đúng | Thiếu CSRF token | Thử `with(csrf())` và kiểm tra CSRF riêng |
| Mock user thành công nhưng login thật thất bại | Mock user bỏ qua authentication provider/password decoder | Viết test gửi credentials hoặc bearer token qua filter thực |
| Kết quả khác giữa test đơn và test suite | Context thủ công/shared state không được dọn hoặc thứ tự test ảnh hưởng | Dọn trạng thái, loại bỏ phụ thuộc thứ tự, chạy lại cả suite |

### Checklist ngắn khi debug

1. MockMvc được tạo bằng `springSecurity()` hay Boot đã đăng ký filter?
2. Test có dùng đúng instance MockMvc được cấu hình không?
3. `@WithMockUser` có được xử lý bởi test execution listener không?
4. Request có nhận context từ `TestSecurityContextHolderPostProcessor` hoặc post-processor riêng không?
5. Filter chain có được chọn cho URL đó và có yêu cầu CSRF không?
6. Context thủ công có được dọn sau test không?

Khi cần thêm bằng chứng, bật log `org.springframework.security.web.FilterChainProxy` ở mức `DEBUG` hoặc `TRACE` trong test để quan sát chuỗi filter được chọn. Log hỗ trợ chẩn đoán, nhưng assertion về status và body vẫn là bằng chứng hành vi chính.

## 10. Phạm vi Servlet và Reactive

`TestSecurityContextHolderPostProcessor` thuộc tích hợp **Servlet MockMvc**. Ứng dụng Reactive/WebFlux có cơ chế kiểm thử riêng dựa trên `WebTestClient` và reactive security test configurer.

| Servlet | Reactive |
| --- | --- |
| `MockMvc` | `WebTestClient` |
| `SecurityContextHolder` theo servlet request/thread | Reactive security context gắn với Reactor Context |
| `TestSecurityContextHolder` / `@WithMockUser` trong MockMvc | Reactive test support như `mockUser()` |
| `SecurityMockMvcConfigurers.springSecurity()` | `SecurityMockServerConfigurers.springSecurity()` |
| `with(user(...))` / `with(jwt())` | `mutateWith(mockUser())` / `mutateWith(mockJwt())` |

Không áp dụng post-processor của Servlet cho pipeline Reactive. Khi kiểm thử WebFlux, cần gắn `WebTestClient` vào reactive application context và dùng các tiện ích security test tương ứng. Cả hai mô hình đều hướng tới việc thiết lập danh tính cho phép thử, nhưng cách lưu và truyền context khác nhau.

## 11. Bài tập thực hành

**Bài 1 — Theo dấu vòng đời.** Thêm log hoặc breakpoint ở test method, controller và sau khi `mockMvc.perform(...)` hoàn tất. Quan sát `TestSecurityContextHolder` và `SecurityContextHolder` ở từng thời điểm. Giải thích vì sao context ứng dụng được dọn sau request nhưng test holder còn phục vụ test.

**Bài 2 — So sánh annotation và request processor.** Viết một test dùng `@WithMockUser("linh")` và một test dùng `with(user("linh"))`. Gọi cùng `GET /api/profile` và so sánh cách danh tính đến request.

**Bài 3 — Nhiều request, nhiều người dùng.** Trong một test method, gửi hai request với `alice` và `bob` bằng `with(user(...))`. Xác nhận response phản ánh đúng từng danh tính và không có trạng thái chéo.

**Bài 4 — Dọn context thủ công.** Đặt context qua `TestSecurityContextHolder.setContext(...)`, thực hiện request trong `try/finally` và gọi `clearContext()`. Tạo một test sau đó để xác nhận không còn principal cũ.

**Bài 5 — Phân biệt mock với login.** Dùng `@WithMockUser` để kiểm tra authorization. Sau đó viết một integration test cho login thật và request kế tiếp dùng session/cookie. Giải thích vì sao hai bài test chứng minh hai hành vi khác nhau.

## 12. Ghi nhớ

**`TestSecurityContextHolder` giữ danh tính dành cho test; `TestSecurityContextHolderPostProcessor` chuyển context đó vào request MockMvc; security filters nạp context cho lần xử lý và code ứng dụng tiếp tục đọc `SecurityContextHolder`.** `springSecurity()` là điểm tích hợp giúp các thành phần này phối hợp đúng khi dựng MockMvc thủ công.

Hãy chọn `@WithMockUser` cho danh tính ở phạm vi test method, `with(user(...))` cho danh tính riêng từng request và context thủ công chỉ khi cần điều khiển động. Luôn có ca truy cập được phép và bị từ chối, dọn context tự thiết lập, đồng thời viết test riêng khi cần xác minh login, session hoặc token thật.
