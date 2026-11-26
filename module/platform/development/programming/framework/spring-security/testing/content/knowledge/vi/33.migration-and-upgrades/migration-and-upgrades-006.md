# Kiểm tra thay đổi mặc định về lưu SecurityContext, CSRF hoặc phiên

Khi nâng cấp Spring Security, một bộ kiểm thử chỉ xác minh `GET /api/me` dưới `@WithMockUser("alice")` vẫn có thể xanh dù **luồng đăng nhập của ứng dụng đã không còn lưu được danh tính sang request tiếp theo**. Tương tự, một `POST` bị `403` có thể do CSRF token mới bị xử lý khác, chứ không phải do chính sách phân quyền. Nếu test không tái hiện cookie, session và các bước liên tiếp, thay đổi mặc định này dễ lọt đến môi trường thật.

Trong chương **Di chuyển và nâng cấp** của module **SPRING_SECURITY_TESTING**, bài học tập trung vào **kiểm thử hồi quy khi mặc định lưu `SecurityContext`, CSRF hoặc session thay đổi**. Chúng ta dùng `spring-security-test` với `MockMvc` cho ứng dụng Servlet và `WebTestClient` cho Reactive; so sánh `@WithMockUser`, `user()`, `mockJwt()`, OAuth2/OIDC giả lập với request xác thực thực tế. Mục tiêu là xác minh điều gì được phép, bị từ chối và **được duy trì qua nhiều request**.

Các ví dụ hướng tới Spring Security 6.x/7.x với cấu hình Java hiện đại. **Không xem mọi thay đổi dưới đây là thay đổi mới của đúng một bản 7.x**: cơ chế explicit save và thay đổi CSRF đáng chú ý xuất hiện khi chuyển từ 5.x/5.8 sang 6.x. Một nâng cấp 6.x → 7.x vẫn cần đo đối chiếu mặc định, cấu hình tự viết và behavior thật theo đúng version đang sử dụng.

## 1. Chuyển tư duy: từ test một request sang test hành vi theo thời gian

Có ít nhất ba câu hỏi độc lập:

1. **Xác thực:** Request hiện tại có `Authentication` hợp lệ không?
2. **Lưu và phục hồi ngữ cảnh:** Request sau, cùng session/cookie nhưng không gửi lại credentials, có lấy được Authentication đúng không?
3. **CSRF và chính sách phiên:** Request có phương thức thay đổi dữ liệu có phải mang token phù hợp không; sau login/logout token và session được cập nhật ra sao?

Ví dụ test một request:

~~~java
@Test
@WithMockUser(username = "alice")
void oneRequestIsAuthenticated() throws Exception {
    mvc.perform(get("/api/me"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.user").value("alice"));
}
~~~

Test này chứng minh endpoint chấp nhận **danh tính giả lập hiện có trong test**, không chứng minh login filter, session storage, SecurityContextRepository hoặc cookie thật. Khi nâng cấp, cần bổ sung kịch bản **request A → request B** thay vì lặp lại `@WithMockUser` ở cả hai bước.

### Ba loại bằng chứng cần phân biệt

| Bằng chứng | Kỹ thuật | Có thể kết luận | Không thể kết luận |
| --- | --- | --- | --- |
| Identity giả lập cho từng request | `@WithMockUser`, `MockMvc.with(user(...))`, `WebTestClient.mutateWith(mockUser(...))` | Rule phân quyền xử lý principal/authorities đúng | Login thật hoặc phiên đã được lưu |
| HTTP authentication thật | Form login, Basic/Bearer header qua filter/provider | Cơ chế xác thực hiện tại chạy | Tự động persistence nếu chưa gửi request kế tiếp |
| Chuỗi request dùng cùng session | Đăng nhập rồi GET/POST/logout mà **không tiêm lại Authentication** | Persistence, CSRF, vòng đời session theo cấu hình | Không mặc nhiên kiểm tra external IdP/JWT signature khi phần đó vẫn mock |

~~~mermaid
flowchart TD
    A["Request đăng nhập"] --> B["AuthenticationManager / AuthenticationFilter"]
    B --> C["SecurityContext ở request hiện tại"]
    C --> D{"Có lưu vào SecurityContextRepository?"}
    D -->|Có| E["HttpSession hoặc kho được cấu hình"]
    D -->|Không| F["Context hết phạm vi request"]
    E --> G["Request tiếp theo: cùng cookie/session"]
    F --> G
    G --> H{"Repository khôi phục Authentication?"}
    H -->|Có| I["Authorization theo principal đã đăng nhập"]
    H -->|Không| J["Chưa xác thực: 401 hoặc redirect"]
    I --> K{"POST/PUT/DELETE có CSRF hợp lệ?"}
    K -->|Có| L["Xử lý request nếu đủ quyền"]
    K -->|Không| M["403 do CSRF"]
~~~

## 2. SecurityContextHolderFilter và explicit save: thay đổi trọng tâm từ 5 sang 6

Trong mô hình Servlet:

| Thời kỳ/cấu hình | Thành phần | Cơ chế chính |
| --- | --- | --- |
| Spring Security 5, kiểu persistence cũ | `SecurityContextPersistenceFilter` | Đọc context và hỗ trợ lưu context tự động khi kết thúc/commit request |
| Spring Security 6, cấu hình mặc định mới | `SecurityContextHolderFilter` | Đọc context vào holder; code tự tạo/đổi Authentication phải **lưu tường minh** nếu muốn tồn tại giữa request |
| Authentication filter chuẩn của Spring Security | Ví dụ form login filter | Cơ chế chuẩn chịu trách nhiệm lưu Authentication theo cấu hình của chính filter |
| Custom login filter/controller tự viết | Gọi `SecurityContextHolder.setContext(...)` | **Phải xem xét `SecurityContextRepository.saveContext(...)`** |

Thay đổi này không có nghĩa “Spring Security 6/7 không còn tự lưu login bằng form login”. Các authentication mechanism tích hợp sẵn vẫn có đường quản lý persistence tương ứng. Vấn đề điển hình là ứng dụng **tự đăng nhập hoặc tự đặt Authentication** nhưng dựa vào behavior tự lưu của filter cũ.

Với `requireExplicitSave = true`, `SecurityContextHolderFilter` nạp ngữ cảnh khi request bắt đầu và dọn sau đó, nhưng không tự viết ngược về repository. Muốn request sau nhìn thấy identity, phải lưu trước khi response commit:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

**Phân biệt hai lệnh:** `SecurityContextHolder.setContext(context)` giúp code xử lý **request hiện tại** nhìn thấy Authentication; `SecurityContextRepository.saveContext(context, request, response)` quyết định việc repository lưu để **request sau** đọc lại. Thiếu lệnh save có thể tạo đúng lỗi: login trả `200/204`, nhưng request tiếp theo bị `401` hoặc chuyển hướng về trang đăng nhập.

### Không nhầm holder với repository

- `SecurityContextHolder` là API lấy SecurityContext trong luồng xử lý hiện tại (Servlet thường dùng ThreadLocal).
- `SecurityContextRepository` là abstraction lưu/đọc SecurityContext giữa request và dispatch.
- `HttpSessionSecurityContextRepository` lưu trong `HttpSession`.
- `RequestAttributeSecurityContextRepository` giúp giữ context giữa các dispatch của **cùng một request**, chẳng hạn error dispatch, **không** tạo phiên đăng nhập lâu dài.
- `DelegatingSecurityContextRepository` có thể kết hợp request attribute và HTTP session; đây là repository mặc định phổ biến trong Spring Security Servlet hiện đại.
- `NullSecurityContextRepository` không lưu context giữa request, phù hợp cho những cơ chế được thiết kế stateless.

Việc gọi `saveContext` với một repository **không lưu** (ví dụ `NullSecurityContextRepository`) không làm phát sinh một phiên đăng nhập. Test phải kiểm tra **repository và session policy thực tế**, không chỉ thấy phương thức save được gọi.

## 3. Một ứng dụng Servlet nhỏ để tái hiện lỗi sau nâng cấp

Để có phép thử rõ ràng, dựng API demo với hai endpoint đăng nhập thủ công:

- `POST /demo/login`: xác thực bằng `AuthenticationManager`, đặt và **lưu** SecurityContext.
- `POST /demo/login-unsaved`: xác thực rồi chỉ đặt context, **cố ý không lưu**, để tái hiện lỗi migration. Endpoint này **chỉ dành cho fixture/test**, không triển khai production.
- `GET /api/me`: trả người dùng hiện tại nếu request đã xác thực.

Các ví dụ giả định Spring Boot Servlet, `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-test` và `spring-security-test`. Tạo `SecurityContextRepository` dùng chung giữa filter và controller:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
@EnableWebSecurity
class MigrationSecurityConfig {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http, SecurityContextRepository repository)
            throws Exception {
        return http
            .securityContext(ctx -> ctx
                .requireExplicitSave(true)
                .securityContextRepository(repository))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/demo/login",
                    "/demo/login-unsaved").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}secret")
                .roles("USER")
                .build());
    }
}
~~~

`{noop}` chỉ dành cho mật khẩu test. Không dùng mật khẩu plain text trong hệ thống thật. Cấu hình này giữ CSRF **bật theo mặc định**, nên `POST` trong các test cần `csrf()` hợp lệ. Chúng ta chủ động chọn `HttpSessionSecurityContextRepository` để làm rõ kết quả lưu vào session; trong ứng dụng sản xuất có thể dùng repository khác.

Để custom controller gọi authentication manager của cấu hình Spring, khai báo bean:

~~~java
@Bean
AuthenticationManager authenticationManager(
        AuthenticationConfiguration configuration) throws Exception {
    return configuration.getAuthenticationManager();
}
~~~

Các import thêm gồm `org.springframework.security.authentication.AuthenticationManager` và `org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration`. Ví dụ này giả định ứng dụng không có một AuthenticationManager bean khác gây mâu thuẫn; khi dự án đã tự cấu hình provider/manager, inject đúng manager mà SecurityFilterChain sử dụng.

Controller tạo Authentication từ **mật khẩu thật của fixture**, không tự gán một token authenticated:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.security.Principal;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ManualLoginController {
    private final AuthenticationManager manager;
    private final SecurityContextRepository repository;

    ManualLoginController(
            AuthenticationManager manager,
            SecurityContextRepository repository) {
        this.manager = manager;
        this.repository = repository;
    }

    @PostMapping("/demo/login")
    ResponseEntity<Void> login(
            @RequestParam String username,
            @RequestParam String password,
            HttpServletRequest request,
            HttpServletResponse response) {
        authenticate(username, password, request, response, true);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/demo/login-unsaved")
    ResponseEntity<Void> loginWithoutPersistence(
            @RequestParam String username,
            @RequestParam String password,
            HttpServletRequest request,
            HttpServletResponse response) {
        authenticate(username, password, request, response, false);
        return ResponseEntity.noContent().build();
    }

    private void authenticate(
            String username, String password,
            HttpServletRequest request, HttpServletResponse response,
            boolean persist) {
        Authentication result = manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                username, password));

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(result);
        SecurityContextHolder.setContext(context);
        if (persist) {
            repository.saveContext(context, request, response);
        }
    }

    @GetMapping("/api/me")
    ResponseEntity<String> me(Principal principal) {
        return ResponseEntity.ok(principal.getName());
    }
}
~~~

**Giới hạn chủ đích của demo:** custom login thật còn cần xử lý `SessionAuthenticationStrategy` (session fixation/concurrency), logout, failure handler và lifecycle HTTP session, không chỉ gọi `AuthenticationManager` + save. Endpoint `/demo/login-unsaved` thể hiện một bug để test bắt được, **không phải cấu hình production được khuyến nghị**. Với ứng dụng chỉ cần form login chuẩn, ưu tiên cơ chế tích hợp của Spring Security thay vì tự tạo endpoint login.

## 4. MockMvc: kiểm chứng đăng nhập xong phải còn Authentication ở request kế tiếp

Test quan trọng nhất cho `requireExplicitSave` có **hai request khác nhau nhưng cùng session**, và **không dùng `@WithMockUser` hoặc `.with(user(...))` ở request thứ hai**. Sử dụng `MockHttpSession` có sẵn giúp không phụ thuộc cơ chế sao chép cookie của browser:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ExplicitSaveRegressionTest {

    @Autowired MockMvc mvc;

    @Test
    void savedContextSurvivesIntoTheNextRequest() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/demo/login")
                .session(session)
                .with(csrf())
                .param("username", "alice")
                .param("password", "secret"))
            .andExpect(status().isNoContent());

        // Không truyền lại username/password và không dùng @WithMockUser.
        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void settingContextWithoutSavingDoesNotPersistLogin()
            throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/demo/login-unsaved")
                .session(session)
                .with(csrf())
                .param("username", "alice")
                .param("password", "secret"))
            .andExpect(status().isNoContent());

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Với cấu hình mẫu chỉ bật HTTP Basic, một request chưa xác thực nhận `401`; nếu dùng form login cho browser, hành vi thường là redirect `302` tới trang login. Hãy viết expected status theo **entry point** của dự án.

Hai kết quả được thiết kế cố ý:

- **Dương tính:** `saveContext(...)` lưu Authentication vào repository, request sau đọc được Alice.
- **Âm tính:** `setContext(...)` chỉ tác động request hiện tại; repository không được lưu, request sau không có identity dù có cùng `MockHttpSession`.

Nên bổ sung assert ở repository hoặc session khi cần điều tra:

~~~java
Object stored = session.getAttribute(
    HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
assertThat(stored).isInstanceOf(SecurityContext.class);
~~~

Đoạn assert này **chỉ đúng với fixture `HttpSessionSecurityContextRepository`** được chọn ở mục 3. Không áp nguyên xi nếu ứng dụng dùng `DelegatingSecurityContextRepository`, Spring Session, repository Redis/custom hoặc thiết kế stateless; khi đó điều cần xác minh chính là request sau còn quyền đúng theo policy.

### Một test giả lập user không bắt được lỗi không lưu

~~~java
@Test
@WithMockUser(username = "alice")
void misleadingSingleRequestTest() throws Exception {
    mvc.perform(get("/api/me"))
        .andExpect(status().isOk());
}
~~~

Test này **không sai** nếu mục tiêu là kiểm tra authorization với principal đã xác thực. Nhưng nếu dùng nó làm duy nhất test hồi quy cho migration lưu session, nó không thể phát hiện đường login quên gọi `saveContext`. Test với `authentication(...)` hoặc `securityContext(...)` cũng không tự chứng minh persistence trừ khi bạn tự gửi request tiếp theo với repository/session thật.

## 5. Form login chuẩn: session persistence và session fixation là hai bài toán

`UsernamePasswordAuthenticationFilter` và các cơ chế tích hợp của Spring Security có xử lý authentication success và persistence theo framework. Đừng kết luận “nâng cấp lên Spring Security 6 khiến form login mặc định không lưu phiên”. Thay vào đó, cần kiểm thử **đường đăng nhập mà dự án thực sự dùng**.

Một browser-oriented `SecurityFilterChain` đơn giản:

~~~java
@Bean
SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/**").authenticated()
            .anyRequest().permitAll())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Đây là **cấu hình thay thế cho demo Basic ở mục 3**, dùng trong test context riêng, không đăng ký song song hai chain không có `securityMatcher(...)` rồi hy vọng Spring tự chọn đúng. Cần một user store test với Alice/secret tương tự mục 3.

Kiểm thử browser login với session được tạo bởi filter:

~~~java
@Test
void formLoginPersistsAuthenticationInBrowserSession()
        throws Exception {
    MvcResult login = mvc.perform(post("/login")
            .with(csrf())
            .param("username", "alice")
            .param("password", "secret"))
        .andExpect(status().is3xxRedirection())
        .andReturn();

    MockHttpSession session =
        (MockHttpSession) login.getRequest().getSession(false);
    assertThat(session).isNotNull();

    mvc.perform(get("/api/me").session(session))
        .andExpect(status().isOk())
        .andExpect(content().string("alice"));
}
~~~

Các import bổ sung gồm `MvcResult`, `MockHttpSession` và AssertJ `assertThat`. Test kiểm tra **persistence sau form login** khi dùng mock request/response cùng session. Đừng tự thêm `.with(user("alice"))` vào `GET /api/me` vì điều đó sẽ bypass việc đọc identity từ session.

**Session fixation** là vấn đề độc lập: khi login thành công, Spring Security có cơ chế đổi session ID hoặc chiến lược phù hợp với Servlet container. Nếu dự án dùng session có trước login, cần test rằng **session ID mới sau authentication** không tiếp tục giống session ID cũ theo chiến lược mà ứng dụng đã chọn, đồng thời các dữ liệu cần được chuyển/giữ hợp lệ. Một test không khởi tạo session trước login sẽ không đủ để chứng minh đã ngăn session fixation.

**Logout** cũng phải kiểm thử bằng cùng browser session và request sau logout, không chỉ assert `POST /logout` trả redirect thành công. Khi ứng dụng dùng session, logout thường cần xóa Authentication và vô hiệu session; nếu dùng OAuth2/OIDC/SAML, hành vi logout ở IdP/broker còn có contract riêng.

## 6. CSRF: thay đổi tải token trì hoãn và bảo vệ BREACH

CSRF bảo vệ các request mà browser có thể tự gửi kèm thông tin xác thực như cookie session. Trong Servlet Spring Security hiện đại, `CsrfFilter` bật mặc định và yêu cầu token cho các HTTP method **không an toàn**, thường gồm `POST`, `PUT`, `PATCH` và `DELETE`. Các method `GET`, `HEAD`, `OPTIONS`, `TRACE` thông thường không cần token CSRF, nhưng **không được dùng chúng để thực hiện thao tác thay đổi dữ liệu**.

Khi chuyển Spring Security 5.x/5.8 → 6.x, hai thay đổi đáng chú ý là:

1. **Deferred CSRF token:** token chỉ được tải hoặc tạo khi thực sự cần, nên một GET không dùng token có thể không còn kích hoạt cùng thao tác repository/session như phiên bản cũ.
2. **BREACH protection:** `XorCsrfTokenRequestAttributeHandler` tạo giá trị token hiển thị đã được che bằng randomness theo request, khác cách đưa token raw vào response trước đây.

| Tình huống | Hành vi cần kiểm tra sau nâng cấp |
| --- | --- |
| GET trang thông thường không render form | Có thể không tải/gọi repository token nhờ deferred loading |
| GET trang có form cần hidden `_csrf` | Token được resolve khi render để trình duyệt gửi lại |
| POST không có token | Bị chặn `403` khi CSRF áp dụng |
| POST với token đúng | Qua CSRF, tiếp tục xét authentication và authorization |
| POST với token sai/hết hiệu lực | Bị chặn `403` |
| SPA đọc token raw từ cookie | Có thể cần request handler xử lý raw cookie token và BREACH đúng cách |
| Login/logout thành công | CSRF token trước đó có thể bị xóa/đổi, client phải lấy token mới |

Không đồng nhất hai khái niệm:

- `CsrfTokenRepository` quyết định token **được lưu ở đâu**: session, cookie hoặc kho khác.
- `CsrfTokenRequestHandler` quyết định token **được đưa vào request attribute và đọc từ client như thế nào** (bao gồm cơ chế XOR/BREACH).

Thay `CookieCsrfTokenRepository` không tự khiến một SPA gửi raw token theo cách `XorCsrfTokenRequestAttributeHandler` mong đợi. Đây là nguồn lỗi `403` sau migration dù tên header `X-XSRF-TOKEN` vẫn đúng.

### Không dùng việc tạo session làm bằng chứng CSRF hoạt động

Với deferred token, một request GET không chạm vào token có thể không tạo session chỉ để lưu CSRF. Nhưng việc request **không tạo session** không chứng minh CSRF bị tắt. Ngược lại, một request POST có token vẫn có thể tạo session để lưu token tùy repository. Hãy test cả hành vi **cho phép/từ chối**, rồi kiểm tra session creation như một điều kiện khác.

## 7. MockMvc: test CSRF dương, âm và phân biệt với authorization

Trong ứng dụng demo, thêm endpoint ghi dữ liệu:

~~~java
@RestController
class NoteController {

    @PostMapping("/api/notes")
    ResponseEntity<String> create() {
        return ResponseEntity.ok("created");
    }
}
~~~

Vì `MigrationSecurityConfig` ở mục 3 yêu cầu xác thực cho `/api/**` và vẫn bật CSRF, test cần tách **Authentication** khỏi **CSRF**:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@Test
void authenticatedPostWithoutCsrfIsForbidden() throws Exception {
    mvc.perform(post("/api/notes")
            .with(user("alice").roles("USER")))
        .andExpect(status().isForbidden());
}

@Test
void authenticatedPostWithValidCsrfSucceeds() throws Exception {
    mvc.perform(post("/api/notes")
            .with(user("alice").roles("USER"))
            .with(csrf()))
        .andExpect(status().isOk())
        .andExpect(content().string("created"));
}

@Test
void authenticatedPostWithInvalidCsrfIsForbidden()
        throws Exception {
    mvc.perform(post("/api/notes")
            .with(user("alice").roles("USER"))
            .with(csrf().useInvalidToken()))
        .andExpect(status().isForbidden());
}
~~~

Ba ca này nên được đặt trong lớp `@SpringBootTest`/`@AutoConfigureMockMvc` có `MockMvc mvc` và controller. Chúng kiểm tra **CSRF filter**, không xác minh mật khẩu của Alice. `user("alice")` cung cấp Authentication giả lập để không bị lỗi authentication che mất nguyên nhân CSRF.

Khi muốn test **phân quyền** của một POST endpoint, luôn cung cấp CSRF hợp lệ trước khi đánh giá expected `403` do thiếu role/ownership:

~~~java
mvc.perform(post("/api/admin/action")
        .with(user("alice").roles("USER"))
        .with(csrf()))
    .andExpect(status().isForbidden());
~~~

Ví dụ này cần endpoint và rule admin tương ứng trong ứng dụng đang test; nếu URL chưa được định nghĩa, status có thể xuất phát từ route/filter khác. Đối chứng dương với người có role admin cũng cần có để chứng minh rule chính xác. Không viết một test âm tính thiếu CSRF rồi đặt tên “user thiếu quyền”.

## 8. CSRF của SPA: cookie raw và token đã che XOR không giống nhau

Một Single-Page Application thường lấy token từ cookie `XSRF-TOKEN` và gửi lại bằng header `X-XSRF-TOKEN`. Trong cấu hình sử dụng `CookieCsrfTokenRepository`:

~~~java
http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieCsrfTokenRepository.withHttpOnlyFalse()));
~~~

`withHttpOnlyFalse()` cho phép JavaScript đọc cookie; **chỉ dùng khi thực sự cần JS đọc token**, vì thuộc tính `HttpOnly` được bỏ. Với ứng dụng không cần đọc cookie bằng JavaScript, hãy ưu tiên cookie HttpOnly. Ngoài CSRF, hệ thống vẫn phải có biện pháp chống XSS và các biện pháp bảo vệ cookie/session.

Khi dùng handler mặc định có BREACH protection, request attribute `_csrf` có thể chứa **giá trị được che XOR** (thay đổi theo request), trong khi cookie lưu **token raw**. Nếu client đọc raw từ cookie rồi gửi nguyên raw vào header mà handler đang chờ token đã che, request có thể bị `403`. Vì vậy **chỉ đổi repository sang cookie** không đủ giải quyết mọi trường hợp SPA sau nâng cấp.

Theo tài liệu phiên bản Spring Security có hỗ trợ DSL SPA, có thể sử dụng cấu hình chuyên biệt:

~~~java
// Spring Security 7.2+: dùng DSL chuyên biệt khi phiên bản hỗ trợ.
http.csrf(csrf -> csrf.spa());
~~~

Không sao chép `spa()` vào mọi dự án Spring Security 6.x rồi cho rằng API chắc chắn có mặt. Với các bản chưa hỗ trợ DSL này, xem cấu hình `SpaCsrfTokenRequestHandler` hoặc custom handler theo **đúng tài liệu version**; cách triển khai thường gồm xử lý token raw ở header nhưng vẫn bảo vệ token phản ánh trong HTML bằng XOR và trả cookie mới khi cần.

### Kiểm thử phải bao gồm thời điểm ngay sau login/logout

Spring Security có thể xóa token CSRF cũ sau authentication success và logout success. Do deferred loading, cookie CSRF mới có thể chưa được phát ngay nếu không có thành phần buộc resolve token cho response. Một SPA tiếp tục gửi token cũ sau login có thể nhận `403`.

Bộ test SPA nên mô phỏng:

1. Client lấy CSRF token/cookie trước login (theo endpoint/bootstrap của ứng dụng).
2. Gửi login với token hợp lệ và cookie cần thiết.
3. Xác nhận principal/session sau login và nhận **CSRF token mới** theo cơ chế ứng dụng.
4. Gửi `POST`/`PUT` với token mới, kỳ vọng được phép khi đủ quyền.
5. Gửi token cũ hoặc không gửi token, kỳ vọng bị từ chối nếu chính sách yêu cầu.
6. Logout thành công, xác minh session cũ và token cũ không còn dùng để thao tác với tư cách user đã đăng nhập.

`MockMvc.with(csrf())` rất phù hợp cho test rule nhanh, nhưng **nó không tự chứng minh frontend thực sự đọc cookie và gửi raw header đúng sau login**. Để kiểm tra round-trip cookie/header thật, cần dùng request có cookie jar hoặc HTTP/browser integration test; khi chỉ dùng `csrf()` postprocessor ở từng request, có thể vô tình che lỗi client.

## 9. SessionCreationPolicy: ALWAYS, IF_REQUIRED, NEVER, STATELESS

Một thay đổi cấu hình session có thể làm thay đổi việc duy trì danh tính, request cache, CSRF token, session fixation và logout. Các giá trị Servlet `SessionCreationPolicy` có hợp đồng khác nhau:

| Policy | Spring Security tạo session? | Có dùng session đã có cho SecurityContext? | Tình huống thường dùng |
| --- | --- | --- | --- |
| `ALWAYS` | Chủ động tạo | Có | Ứng dụng cần session ngay từ đầu |
| `IF_REQUIRED` | Khi cần | Có | Web app/session login thông thường |
| `NEVER` | Không chủ động tạo để lưu SecurityContext | Có thể dùng session đã tồn tại | Kiểm soát việc tạo mới nhưng vẫn chấp nhận session cũ |
| `STATELESS` | Không tạo session để lưu SecurityContext | **Không** dùng session lấy SecurityContext | Stateless API xác thực theo mỗi request |

**Đừng đồng nhất `NEVER` với `STATELESS`.** Với `NEVER`, một session đã có có thể vẫn được dùng; thêm vào đó, thành phần khác như request cache hoặc application code có thể tạo session. Với `STATELESS`, Spring Security không dùng HTTP session để lấy `SecurityContext`, nhưng **không thể kết luận không thành phần nào của toàn bộ ứng dụng tạo session**.

Ví dụ một API stateless:

~~~java
@Bean
@Order(1)
SecurityFilterChain statelessApi(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/stateless/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .httpBasic(Customizer.withDefaults())
        .formLogin(AbstractHttpConfigurer::disable)
        .build();
}
~~~

Các import cần thêm: `org.springframework.core.annotation.Order` và `org.springframework.security.config.http.SessionCreationPolicy`. Đây là ví dụ một chain **chỉ khớp `/api/stateless/**`**. Khi ứng dụng có nhiều chain, phải có chain khác bảo vệ các URL còn lại và hiểu rằng **chain khớp đầu tiên** được áp dụng. Không tạo nhiều chain `anyRequest()` trùng nhau rồi cho rằng Spring sẽ tự hợp nhất policy.

Ví dụ trên **không tắt CSRF toàn cục**. Với GET không có tác dụng phụ, CSRF không cần token. Một API chỉ nhận Bearer token trong `Authorization` header và không dựa vào cookie tự động gửi thường có thể thiết kế tắt CSRF theo phạm vi rõ ràng; nhưng nếu browser tự gửi credentials (kể cả HTTP Basic đã cache), phải đánh giá rủi ro CSRF thay vì mặc định “stateless thì không cần CSRF”.

### Test stateless không được dựa vào session đã chuẩn bị sẵn

Trong một test context có `statelessApi` và controller `GET /api/stateless/me`:

~~~java
@Test
void statelessApiIgnoresPreviouslySavedSessionContext()
        throws Exception {
    SecurityContext fakeSessionContext =
        SecurityContextHolder.createEmptyContext();
    fakeSessionContext.setAuthentication(
        UsernamePasswordAuthenticationToken.authenticated(
            "alice", "N/A",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))));

    MockHttpSession previousSession = new MockHttpSession();
    previousSession.setAttribute(
        HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY,
        fakeSessionContext);

    mvc.perform(get("/api/stateless/me").session(previousSession))
        .andExpect(status().isUnauthorized());
}
~~~

Với chain `SessionCreationPolicy.STATELESS` và Basic authentication, **không có Authorization header** đồng nghĩa request không lấy identity từ `HttpSession`, kể cả session chứa `SPRING_SECURITY_CONTEXT`. Thêm đối chứng dương:

~~~java
mvc.perform(get("/api/stateless/me")
        .with(httpBasic("alice", "secret")))
    .andExpect(status().isOk());
~~~

Các ví dụ trên cần controller `/api/stateless/me` trả dữ liệu khi đã xác thực, user store tương ứng, và static import `SecurityMockMvcRequestPostProcessors.httpBasic`. Nếu app có một filter/proxy tự gắn Authentication ngoài chain này, phải xác minh thêm rằng filter đó không vô tình phục hồi session; chính sách stateless chỉ bảo đảm hành vi của Spring Security theo cấu hình của chain.

### Request cache có thể gây hiểu nhầm về session

Trước khi login, browser bị yêu cầu truy cập tài nguyên bảo vệ có thể được lưu lại bằng `RequestCache` để redirect về sau khi đăng nhập. `HttpSessionRequestCache` có thể làm xuất hiện session dù người dùng **chưa login**. Vì thế việc thấy cookie `JSESSIONID` không chứng minh “user đã được lưu SecurityContext”; nó có thể chỉ dùng để nhớ URL ban đầu hoặc CSRF token.

Nếu ứng dụng cần API stateless, kiểm tra cả request cache:

~~~java
http.requestCache(cache ->
    cache.requestCache(new NullRequestCache()));
~~~

Trong cấu hình stateless hiện đại, Spring Security có các mặc định liên quan request cache và repository. Đừng thêm `NullRequestCache` vào mọi cấu hình chỉ để làm test xanh; cần xác nhận **không có tính năng redirect sau login** nào còn phụ thuộc vào saved request. Một browser app với form login có nhu cầu khác REST API stateless.

## 10. Session management sau nâng cấp: authentication mechanism phải chịu trách nhiệm

Trong Spring Security 5, `SessionManagementFilter` được dùng mặc định theo cách truyền thống để phát hiện Authentication mới và gọi `SessionAuthenticationStrategy`. Trong Spring Security 6, `SessionManagementFilter` **không được thêm theo mặc định**; authentication mechanism cần chủ động xử lý những phần liên quan session authentication.

Điều này có thể tác động tới:

- **Session fixation protection:** đổi session ID sau khi login.
- **Concurrent sessions:** giới hạn số phiên của một tài khoản.
- **Session authentication failure:** cần handler phù hợp nếu chiến lược session từ chối tạo phiên.
- **Invalid/expired session:** cơ chế phát hiện/redirect tùy cấu hình.
- **Custom authentication filter:** không thể dựa vào một filter quản lý phiên mặc định chạy “ở phía sau” để làm thay.

Một custom login controller giống mục 3 cần cân nhắc thêm `SessionAuthenticationStrategy.onAuthentication(authentication, request, response)` hoặc integration tương đương theo framework, **trước khi save context** và chỉ khi thành công. Không tự gọi một strategy lắp ghép không hiểu session concurrency/fixation; cấu hình phải thống nhất với authentication mechanism thực tế.

Nếu nâng cấp từ DSL cũ kiểu `sessionManagement().sessionAuthenticationStrategy(...)` hoặc custom filter phụ thuộc `SessionManagementFilter`, hãy đọc migration guide cho phiên bản đó; ở các cấu hình 6.x hiện đại, một số DSL liên quan chiến lược session không còn có hiệu lực hoặc bị từ chối. Không nên cố duy trì bộ lọc cũ và mới cùng một chain chỉ để “tương thích”: `SecurityContextHolderFilter` và `SecurityContextPersistenceFilter` có mục đích thay thế, không dùng như hai lớp đọc/ghi song song mặc định.

### Ma trận regression cho session

| Tình huống | Input | Điều cần kiểm tra |
| --- | --- | --- |
| Login hợp lệ | Username/password đúng | Cookie/session và authentication request sau đúng |
| Login sai | Password sai | Không có authenticated session mới |
| Session fixation | Session ID tồn tại trước login | ID/thuộc tính được xử lý đúng chiến lược |
| User đăng xuất | Session/cookie đã login | Request sau không được dùng quyền cũ |
| Session timeout | Cookie hết hạn | API trả `401` hoặc browser redirect, không dùng context cũ |
| Session đồng thời | Login trên hai browser | Giới hạn phiên nếu policy có cấu hình |
| `NEVER` | Session có sẵn vs chưa có | Phân biệt dùng lại và tạo mới |
| `STATELESS` | Session mang `SecurityContext` cũ | Không phục hồi Authentication từ session |
| Error dispatch | Authentication trong request lỗi | Hành vi dispatch và cleanup theo repository |
| Saved request | Anonymous yêu cầu URL được bảo vệ | Redirect/saved request đúng khi login thành công |

Mỗi test cần **tránh tiêm lại authentication vào request thứ hai**. Nếu làm như vậy, một test logout hoặc session timeout có thể vẫn `200` vì dữ liệu giả lập chứ không phải vì session đã được phục hồi.

## 11. Reactive WebFlux: không sao chép trực tiếp mô hình Servlet

Trong WebFlux, `ReactiveSecurityContextHolder` đặt thông tin bảo mật vào **Reactor Context**, còn `ServerSecurityContextRepository` lưu/đọc identity giữa các request. Những implementation thường gặp:

| Servlet stack | Reactive stack | Ý nghĩa |
| --- | --- | --- |
| `SecurityContextHolder` với ThreadLocal thông thường | `ReactiveSecurityContextHolder` với Reactor Context | Ngữ cảnh trong luồng request |
| `HttpSessionSecurityContextRepository` | `WebSessionServerSecurityContextRepository` | Lưu authentication vào phiên |
| `NullSecurityContextRepository` | `NoOpServerSecurityContextRepository` | Không duy trì context qua session |
| `CsrfFilter`, `CsrfTokenRequestHandler` | `CsrfWebFilter`, `ServerCsrfTokenRequestHandler` | CSRF cho unsafe requests |
| `MockMvc` | `WebTestClient` | Công cụ test HTTP theo web stack |

Đừng bê `SessionCreationPolicy.STATELESS` của Servlet vào WebFlux như một cấu hình tương đương nguyên xi. Reactive dùng các repository và authentication filters riêng; `WebSession` cũng không phải `HttpSession`.

Với custom authentication Reactive cần lưu:

~~~java
Mono<Void> persistReactiveAuthentication(
        ServerWebExchange exchange,
        Authentication authentication,
        ServerSecurityContextRepository repository) {

    SecurityContext context = new SecurityContextImpl(authentication);
    return repository.save(exchange, context);
}
~~~

Các import gồm `org.springframework.web.server.ServerWebExchange`, `org.springframework.security.core.Authentication`, `org.springframework.security.core.context.SecurityContext`, `org.springframework.security.core.context.SecurityContextImpl`, `org.springframework.security.web.server.context.ServerSecurityContextRepository` và `reactor.core.publisher.Mono`.

**Quan trọng:** `save(...)` trả `Mono<Void>` nên phải **được compose trong reactive chain** và được subscribe bởi framework tại boundary thích hợp. Không gọi `repository.save(...).subscribe()` rồi lập tức trả response như một fire-and-forget operation; response có thể hoàn thành trước khi lưu context.

Ví dụ về mặt nguyên tắc:

~~~java
return authenticationService.authenticate(credentials)
    .flatMap(auth ->
        persistReactiveAuthentication(exchange, auth, repository))
    .thenReturn(ResponseEntity.noContent().build());
~~~

Đây là phác thảo control flow; `authenticationService` và `credentials` thuộc domain của ứng dụng. Khi dùng Reactive form login hoặc bearer authentication có sẵn, ưu tiên filter/framework chuẩn thay vì tự viết lại. Nếu custom authentication phải truyền context cho các operator khác **trong cùng subscription**, có thể cần áp dụng `ReactiveSecurityContextHolder.withAuthentication(...)` đúng vị trí; việc lưu giữa request là trách nhiệm riêng của `ServerSecurityContextRepository`.

### WebTestClient: CSRF âm tính và dương tính

Với ứng dụng WebFlux đã có endpoint `POST /api/reactive/notes` yêu cầu xác thực và CSRF:

~~~java
@Test
void reactivePostWithoutCsrfIsDenied() {
    webTestClient.mutateWith(mockUser("alice"))
        .post().uri("/api/reactive/notes")
        .exchange()
        .expectStatus().isForbidden();
}

@Test
void reactivePostWithCsrfPassesTheCsrfFilter() {
    webTestClient.mutateWith(mockUser("alice"))
        .mutateWith(csrf())
        .post().uri("/api/reactive/notes")
        .exchange()
        .expectStatus().isOk();
}
~~~

Ở đây `mockUser` và `csrf` là static imports của `SecurityMockServerConfigurers`; `webTestClient` là client đã tích hợp Spring Security test support. Controller Reactive có thể trả `Mono<String>` với giá trị `created` và được cấu hình cho phép user đã đăng nhập POST. Dùng test này để kiểm tra filter CSRF; nếu code chỉ có WebFlux controller nhưng **không tích hợp `SecurityWebFilterChain`**, không được kết luận CSRF đang được áp dụng.

Reactive `XorServerCsrfTokenRequestAttributeHandler` là một thay đổi mặc định liên quan BREACH từ Spring Security 5.8 sang 6.0. Nếu SPA dùng `CookieServerCsrfTokenRepository` và `X-XSRF-TOKEN`, cần test xử lý token raw/masked đúng **cấu hình Reactive**, không dùng trực tiếp `CsrfTokenRequestHandler` của Servlet.

### Kiểm thử persistence Reactive khác với mutateWith(mockUser())

`webTestClient.mutateWith(mockUser("alice"))` đặt sẵn Authentication cho request hiện tại; nó **không** chứng minh WebSession giữ identity sau login. Một test persistence phải thực hiện login qua filter/controller thật, thu cookie WebSession, gửi request thứ hai **không thêm mockUser()**, rồi kiểm tra principal/authority.

Tương tự, `mockJwt()`, `mockOAuth2Login()` hoặc `mockOidcLogin()` rất hữu ích cho test authorization, nhưng không kiểm tra JWT decoder/OIDC callback hoặc sự tồn tại của phiên Reactive thật. Khi upgrade authentication provider hoặc session repository, phải có suite tích hợp riêng.

## 12. JWT/OAuth2/OIDC/SAML: không kết luận session policy chỉ từ tên cơ chế

Khi thay một ứng dụng browser login bằng OAuth2/OIDC hoặc JWT API, rất dễ suy luận sai:

- “Có OAuth2” không có nghĩa ứng dụng hoàn toàn stateless. Một **OAuth2 Login/OIDC Login client** chạy trên browser có thể dùng session/cookie để nhớ Authentication sau callback.
- “Có Bearer JWT” không có nghĩa CSRF luôn cần tắt. Cần xét cách browser cung cấp credentials và các endpoints còn dùng cookie nào.
- “Dùng `mockJwt()` test thành công” không chứng minh `JwtDecoder`, issuer, audience, chữ ký hoặc expiration được kiểm tra.
- “Có `@WithMockUser`” không chứng minh form login/OIDC/SAML callback đã tạo session đúng.
- “Có session cookie” không chứng minh session chứa SecurityContext; cookie có thể gắn với request cache hoặc CSRF repository.

| Cơ chế | Test authorization nhanh | Test upgrade cần bổ sung |
| --- | --- | --- |
| Servlet form login | `@WithMockUser`, `user()` | POST login + CSRF, session persistence, fixation, logout và request sau |
| HTTP Basic | `user()` để kiểm tra role | Basic header thật, sai password, yêu cầu mỗi request |
| JWT Resource Server | `jwt()`, `mockJwt()` | Bearer header thật, decoder, bad signature, issuer/audience/expiry, stateless context |
| Opaque token | `opaqueToken()`, `mockOpaqueToken()` | Introspection thật/mock HTTP server ở ranh giới transport, revoked token |
| OAuth2/OIDC Login | `oauth2Login()`, `oidcLogin()` và bản Reactive tương ứng | Redirect/state/nonce/PKCE theo flow, callback và session của browser |
| SAML2 Servlet SP | `authentication(customSamlAuthentication)` | ACS callback, signed response, relying party và cookie/session sau login |

Một số nhà cung cấp token/IdP không phát session cho Resource Server, nhưng một app còn có endpoint web, actuator hoặc form login dùng chain khác. **Nhiều `SecurityFilterChain` có thể có chính sách CSRF/session khác nhau**. Test phải khớp URL, HTTP method và chain cụ thể thay vì suy luận từ một annotation/config toàn ứng dụng.

## 13. Cách xây regression suite có thể so sánh trước và sau upgrade

Trước khi đổi dependency, nên chốt một bộ hành vi quan trọng. Sau khi nâng cấp, chạy lại cùng bộ test trên phiên bản mới và ghi nhận khác biệt có chủ đích.

| Nhóm | Test | Trước/sau phải duy trì |
| --- | --- | --- |
| Authentication | Login đúng credentials | Đăng nhập thành công theo contract |
| Authentication | Login sai credentials | Không lưu authenticated session |
| Persistence | Login → GET cùng session, không truyền auth lần nữa | Người dùng hợp lệ vẫn được nhận ra |
| Persistence | Chỉ `setContext` mà không save trong config explicit-save | Request sau không được coi là đã đăng nhập |
| CSRF | POST có auth, thiếu CSRF | `403` khi CSRF được yêu cầu |
| CSRF | POST có auth và CSRF hợp lệ | Qua filter, tiếp tục authorization |
| CSRF | POST có auth nhưng CSRF sai | `403` |
| CSRF SPA | Raw token cookie/header, token sau login/logout | Client nhận và dùng token mới đúng cách |
| Session | Logout → request dùng cookie cũ | Không được quyền cũ |
| Session | Session trước login → login | Session fixation strategy chạy đúng |
| Session | Session timeout/concurrency | Hành vi timeout/giới hạn phiên đúng policy |
| Stateless | Request mang SecurityContext cũ trong HttpSession | Không phục hồi auth từ session |
| Stateless | Request có Basic/Bearer credentials hợp lệ | Được xác thực theo request |
| Authorization | Owner/role đúng | `200`/`204` phù hợp |
| Authorization | Owner/role sai nhưng CSRF hợp lệ | `403` do authorization |
| Servlet/Reactive | Cùng policy trên hai web stack | Mỗi stack dùng đúng filter và repository của nó |
| Protocol integration | JWT/OIDC/SAML response thật | Validation đúng, không bị test mock che mất |

**Giữ các test ở ba tầng:**

1. **Fast policy tests:** `@WithMockUser`, `MockMvc.with(user(...))`, `WebTestClient.mutateWith(mockUser(...))` và mockJwt/OAuth2/OIDC để kiểm tra 200/403 theo quyền.
2. **Filter/repository tests:** xác thực qua HTTP, cookie/session, CSRF, `SecurityContextRepository` hoặc `ServerSecurityContextRepository` để kiểm tra 401/302/403 và persistence.
3. **Protocol/E2E tests:** IdP, decoder, introspection, redirect/callback, transport và session cookie thực để kiểm chứng ranh giới tin cậy ngoài ứng dụng.

Nếu mọi test đều ở tầng 1, nâng cấp làm đứt persistence vẫn có thể không bị phát hiện. Nếu mọi test đều dùng browser E2E, suite chậm và khó chẩn đoán. Phân tầng giúp nhanh mà vẫn có bằng chứng đúng.

## 14. Hướng dẫn chẩn đoán các lỗi sau khi nâng cấp

| Triệu chứng | Nghi ngờ đầu tiên | Phép kiểm chứng có giá trị |
| --- | --- | --- |
| Login `204/302` nhưng request sau `401` | Custom authentication thiếu `saveContext`; repository khác/không lưu | Hai request cùng session, không mock Authentication lần hai |
| Request hiện tại thấy user, request sau mất user | Chỉ set `SecurityContextHolder`, chưa lưu | Kiểm tra `SecurityContextRepository` thực tế và session |
| POST trước đây được, nay `403` dù đủ role | Thiếu CSRF hoặc raw/masked token không khớp | POST + `csrf()`, test cookie/header thực |
| GET không tạo `JSESSIONID` như trước | Deferred CSRF token hoặc cache/session behavior thay đổi | Kiểm tra GET có thật sự yêu cầu token không |
| POST ngay sau login bị `403` nhưng POST trước login có token | CSRF token bị xóa/đổi sau authentication | Lấy token mới sau login, thử token cũ/mới |
| Logout trả thành công nhưng cookie cũ vẫn mở API | Session chưa invalidated/clear context không lưu | Gửi request sau logout mà không tiêm auth |
| `SessionCreationPolicy.NEVER` vẫn thấy session | Request cache, CSRF repo hoặc code khác tạo session | Xác định ai gọi `getSession()` và lý do |
| Stateless endpoint vẫn được qua bằng session cũ | Sai chain, repository hoặc custom filter | Test session chứa context cũ nhưng thiếu Authorization header |
| Basic request đúng thì `200`, bỏ header thì `401` | Có thể hoàn toàn bình thường với stateless Basic | Đừng đòi persistence nếu policy re-authenticate mỗi request |
| Test `@WithMockUser` xanh, login thật fail | Identity mock bypass provider/login/session | POST login thực + request sau |
| Test Reactive thấy `null` ở `SecurityContextHolder` | Đọc ThreadLocal thay Reactor Context | Dùng `ReactiveSecurityContextHolder` trong publisher |
| Nâng cấp bật SAML/OIDC login nhưng session mất | Callback, state/relying party, repository hoặc cookie policy | Test callback + cookie jar; không dùng mock identity ở request sau |
| Test `403` luôn xanh kể cả xóa role | CSRF đã chặn trước authorization | Gắn CSRF hợp lệ và có đối chứng dương |

### Quan sát log để biết filter nào đã từ chối

Có thể bật log chẩn đoán riêng cho môi trường test:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Ở một số bản/framework cần cấu hình logger cụ thể hơn để quan sát filter chain, authentication entry point và access denied handler. Không bật TRACE toàn bộ security lâu dài trên production hoặc đưa Authorization header, session ID, access token/refresh token thật vào CI log. Trạng thái `401` hoặc `403` chỉ là **kết quả**, không tự chứng minh filter/manager nào gây ra; log, test dương và mock verification có thể giúp phân biệt.

## 15. Kế hoạch nâng cấp có thể kiểm chứng

### Giai đoạn A: khóa hành vi hiện tại

Ghi lại **phiên bản Spring Framework, Spring Security, Spring Boot, Java và Servlet/WebFlux stack** của ứng dụng. Kiểm kê các phần có tự viết Authentication hoặc thay đổi context, bao gồm custom filter, endpoint login, gateway pre-auth, remember-me, custom session repository, OAuth2/OIDC callback và logic logout.

Đặt một bộ test baseline bao gồm:

- Login thành công và thất bại.
- Hai request cùng session sau login, không mock lại auth.
- POST thiếu/sai/đúng CSRF.
- Logout, session timeout, session fixation nếu app dùng session.
- Stateless request với/không có credentials, có session cũ.
- Owner/role/tenant dương và âm.

### Giai đoạn B: thay đổi cấu hình theo đúng nguyên nhân

Nếu chuyển từ auto-save sang explicit-save, rà mọi chỗ gọi `SecurityContextHolder.setContext(...)` và xem liệu nó có cần persistence hay chỉ phục vụ request hiện tại. Chỉ thêm `saveContext(...)` ở những nơi cần và với repository phù hợp; với cơ chế stateless không nên cố tạo session.

Nếu CSRF behavior thay đổi, kiểm tra cấu hình `CsrfTokenRepository`, `CsrfTokenRequestHandler` và contract cookie/header của client. Không giải quyết `403` bằng `csrf().disable()` cho toàn ứng dụng khi vẫn dùng cookie session. Nếu cần chính sách CSRF khác giữa browser và stateless API, tách filter chain theo đường dẫn và kiểm tra độc lập.

Nếu session management behavior khác, rà `SessionAuthenticationStrategy` trong custom login/filter, thời điểm đổi session ID, request cache, concurrent sessions và logout. Không thêm ngược `SessionManagementFilter` một cách cơ học chỉ để chữa triệu chứng nếu authentication mechanism cần được sửa.

### Giai đoạn C: so sánh sau nâng cấp

Chạy cùng regression suite, phân loại khác biệt:

| Loại khác biệt | Hành động |
| --- | --- |
| API phản hồi thay đổi nhưng policy không đổi | Điều chỉnh assertion cho contract mới **chỉ sau khi xác minh** thay đổi là chủ đích |
| Identity không được lưu qua request | Sửa explicit save/repository; không thêm `@WithMockUser` ở request hai |
| POST bị chặn do CSRF | Cập nhật cách phát/lấy/giải token; giữ kiểm tra CSRF |
| Phiên mới có ID/cookie khác | Kiểm chứng session fixation/cookie policy và client handling |
| Request không đúng chain | Rà `securityMatcher`, `@Order`, profile và chain matching |
| Test mock pass nhưng protocol fail | Thêm hoặc sửa integration test trên provider/decoder thật |
| Cấu hình chỉ chạy trên bản cũ | Dùng API migration guide của version đang áp dụng, không pin workaround mãi mãi |

**Tuyệt đối không cập nhật hàng loạt expected `403` thành `200` hoặc xóa các negative tests** chỉ để build xanh. Một thay đổi mặc định có thể tạo khác biệt ngoài ý muốn về bảo vệ CSRF/session; CI cần phát hiện đúng thay vì chấp nhận im lặng.

## 16. Bài tập thực hành

1. **Explicit save:** dùng `ManualLoginController`. Viết hai test với cùng `MockHttpSession`: `/demo/login` làm request sau nhận Alice, `/demo/login-unsaved` khiến request sau bị `401`.
2. **Không nhầm một request với hai request:** tạo test `@WithMockUser("alice")` cho `GET /api/me`. Giải thích vì sao nó vẫn xanh khi custom login thiếu `saveContext(...)`.
3. **CSRF ba nhánh:** dùng `POST /api/notes` với `user("alice")` và lần lượt thiếu token, token đúng, token sai. Kỳ vọng `403`/`200`/`403`.
4. **Bảo vệ quyền sau CSRF:** tạo endpoint POST chỉ cho ADMIN. Gắn `csrf()` cả trong test USER bị `403` và ADMIN thành công. Loại bỏ token để thấy test thiếu quyền có thể xanh sai lý do.
5. **SPA sau login:** lấy raw CSRF cookie, thực hiện login và kiểm tra token mới. Gửi token cũ và mới, quan sát hành vi theo request handler đã cấu hình; không bypass bằng `csrf()` ở tất cả bước nếu mục tiêu là test frontend-cookie contract.
6. **NEVER vs STATELESS:** dựng hai chain/test context. Một request có session cũ chứa SecurityContext; xác minh policy thực sự có dùng session đó hay không.
7. **Request cache:** yêu cầu một URL được bảo vệ khi chưa login. Xem việc có session trước login có đến từ `SavedRequest`/`CsrfTokenRepository` không, thay vì cho rằng auth đã được lưu.
8. **Form login:** gửi POST `/login` với CSRF và credentials đúng, lấy `MockHttpSession` từ kết quả, rồi GET `/api/me` mà không inject authentication lần nữa.
9. **Logout:** dùng cùng session login, POST logout với CSRF và truy cập lại tài nguyên. Bảo đảm session cũ không cấp quyền như trước.
10. **Session fixation:** bắt đầu bằng session chưa đăng nhập, thực hiện login, kiểm tra đổi ID theo chiến lược và tính nhất quán dữ liệu cần giữ.
11. **Reactive CSRF:** thêm WebFlux POST endpoint; dùng `WebTestClient.mutateWith(mockUser("alice"))` rồi thử có/không `csrf()`. Phân biệt Reactor Context với `SecurityContextHolder`.
12. **Reactive persistence:** dùng `WebSessionServerSecurityContextRepository` cho custom flow, compose `save(exchange, context)` và kiểm tra request thứ hai bằng cookie nhưng không gắn lại `mockUser()`.
13. **JWT Resource Server:** dùng `mockJwt()` kiểm tra authorization; sau đó gửi JWT ký thật qua decoder để kiểm tra lỗi signature/issuer/expiration `401` không bị mock che.
14. **Nhiều filter chains:** tạo browser chain có session/CSRF và API chain stateless; test một URL đi vào đúng chain theo `securityMatcher`/`@Order`.
15. **So sánh version:** chạy suite trên nhánh trước upgrade và sau upgrade, lập bảng thay đổi của SecurityContext persistence, CSRF token loading/header, session và logout. Chỉ điều chỉnh policy/test dựa trên kết quả quan sát và release notes.

## 17. Checklist trước khi đánh dấu nâng cấp an toàn

| Hạng mục | Câu hỏi xác minh |
| --- | --- |
| Custom login | Có gọi `saveContext` khi cần lưu auth không? |
| Repository | Chain và code login có dùng đúng `SecurityContextRepository` không? |
| Hai request | Request sau login dùng **cùng cookie/session** nhưng không được cấp user giả lần nữa chưa? |
| Authentication failure | Password/token sai không tạo session có quyền? |
| CSRF | Có test thiếu token, token đúng và token sai cho unsafe methods không? |
| SPA | Raw/masked token, cookie/header và refresh sau login/logout đã được test chưa? |
| Session policy | `ALWAYS`, `IF_REQUIRED`, `NEVER`, `STATELESS` có được hiểu và áp dụng đúng URL không? |
| Session fixation | Custom login có gọi session authentication strategy đúng chỗ không? |
| Logout/expiry | Session cũ có bị mất quyền khi cần không? |
| Request cache | Cookie/session có bị tạo vì saved request thay vì auth không? |
| Authorization | Có test `200` dương và `403` âm **với CSRF hợp lệ** không? |
| Servlet/Reactive | Mỗi stack dùng đúng context repository, CSRF filter và test client không? |
| IdP/JWT | Các test mock và protocol thật được phân biệt rõ ràng không? |
| CI | Những test quan trọng chạy ở PR, không chỉ ở suite chạy định kỳ không? |

### Kết quả cần đạt

Sau bài học, người học phải giải thích được vì sao **đặt `Authentication` vào `SecurityContextHolder` không đồng nghĩa lưu đăng nhập cho request tiếp theo**, khi nào phải gọi `SecurityContextRepository.saveContext(...)` và vì sao cần test nhiều request cùng session. Người học cũng phải nhận diện thay đổi CSRF deferred token/BREACH, phân biệt `NEVER` với `STATELESS`, hiểu vòng đời token/session sau login/logout, và biết dùng đúng `MockMvc` hoặc `WebTestClient`. Quan trọng nhất, một bộ kiểm thử nâng cấp không chỉ kiểm tra `200`/`401`/`403`, mà còn xác định **lớp bảo mật đã tạo ra kết quả đó** và giới hạn của authentication giả lập.

### Tài liệu tham khảo

- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — CSRF for Servlet](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Servlet Testing with CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — WebTestClient CSRF Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html)
- [Spring Security — Servlet Authentication and Session Migrations](https://docs.spring.io/spring-security/reference/migration/servlet/session-management.html)
- [Spring Security — Servlet Exploit Protection Migrations](https://docs.spring.io/spring-security/reference/migration/servlet/exploits.html)
