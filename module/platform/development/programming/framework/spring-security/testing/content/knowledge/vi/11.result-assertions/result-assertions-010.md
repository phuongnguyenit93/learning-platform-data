# Xác minh trạng thái phiên, cookie hoặc repository khi cần

## 1. Khi nào cần kiểm tra phiên và nơi lưu Authentication?

Một test có thể xác nhận request hiện tại đã được xác thực bằng `authenticated()`, nhưng điều đó chưa chứng minh người dùng vẫn đăng nhập ở request kế tiếp. Ví dụ, request đăng nhập trả 302 và có Authentication trong kết quả; nếu `SecurityContext` không được lưu đúng cách, request tiếp theo có thể trở thành anonymous.

Kiểm thử phiên và nơi lưu ngữ cảnh bảo mật giúp xác nhận các hành vi có trạng thái:

- Sau khi đăng nhập thành công, request tiếp theo dùng cùng session vẫn nhận đúng người dùng.
- Sau khi đăng xuất, phiên hoặc ngữ cảnh xác thực không còn được dùng để cấp quyền.
- Cookie xác thực của ứng dụng được phát hành với thuộc tính đúng và được gửi lại theo cơ chế dự kiến.
- `SecurityContextRepository` lưu và nạp `SecurityContext` theo chính sách của ứng dụng.
- API stateless không vô tình phụ thuộc vào HTTP session để duy trì Authentication.
- Với WebFlux, `WebSession` và repository Reactive duy trì ngữ cảnh qua nhiều request theo đúng cấu hình.

Trong module **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên Servlet và Reactive. Bài thuộc chương **Khẳng định kết quả** này mở rộng phép kiểm tra kết quả của một request sang **vòng đời giữa nhiều request**.

Không phải endpoint nào cũng cần session. API dùng Bearer token stateless thường xác thực từng request; trong trường hợp đó, điều cần chứng minh có thể là session không được tạo hoặc không được dùng để lưu SecurityContext. Chọn phép kiểm tra dựa trên kiến trúc thực tế.

## 2. Phân biệt session, cookie và repository

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| HTTP session | Trạng thái phía server gắn với một client qua nhiều request | `HttpSession`, `MockHttpSession` |
| Cookie | Dữ liệu client gửi lại để server nhận diện session hoặc thông tin xác thực | `JSESSIONID`, cookie ứng dụng `APP_AUTH` |
| `SecurityContextRepository` | Cơ chế nạp/lưu `SecurityContext` giữa các request | `HttpSessionSecurityContextRepository`, `NullSecurityContextRepository` |
| Spring Session `SessionRepository` | Lưu trữ session vào backend như Redis hoặc JDBC | Repository Redis/JDBC |

Một cookie session thường chỉ mang session ID. Dữ liệu Authentication được lưu ở server trong session thông qua SecurityContextRepository; không nên mặc định toàn bộ đối tượng Authentication được gửi xuống browser trong cookie.

`SecurityContextRepository` không đồng nghĩa với Spring Session `SessionRepository`:

- `SecurityContextRepository` quản lý vòng đời ngữ cảnh bảo mật.
- `SessionRepository` của Spring Session quản lý dữ liệu phiên và nơi lưu phiên.
- Ứng dụng có thể dùng HTTP session mặc định mà không cần Spring Session, hoặc thay backend lưu session bằng Redis/JDBC mà vẫn giữ nguyên logic SecurityContextRepository.

Sơ đồ tổng quát cho ứng dụng Servlet stateful:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant F as Spring Security Filter Chain
    participant R as SecurityContextRepository
    participant S as HttpSession
    participant C as Controller
    B->>F: POST /login với credentials
    F->>R: saveContext(Authentication)
    R->>S: lưu SecurityContext
    F-->>B: redirect + session cookie
    B->>F: GET /api/me + session cookie
    F->>R: load SecurityContext
    R->>S: đọc SecurityContext
    R-->>F: Authentication đã lưu
    F->>C: request đã xác thực
    C-->>B: response theo danh tính
~~~

Trong MockMvc, ta có thể kiểm tra cùng một session qua nhiều request mà không cần chạy browser thật. Với WebFlux, cơ chế tương ứng sử dụng `WebSession` và repository Reactive.

## 3. Chính sách tạo session trong Spring Security

`SessionCreationPolicy` điều khiển cách Spring Security sử dụng HTTP session:

| Chính sách | Hành vi | Trường hợp thường dùng |
| --- | --- | --- |
| `ALWAYS` | Luôn tạo session | Ứng dụng chủ động cần session cho mọi request |
| `IF_REQUIRED` | Chỉ tạo khi cần | Ứng dụng web stateful |
| `NEVER` | Không tự tạo session nhưng có thể dùng session đã tồn tại | Hệ thống khác tạo session và Security dùng lại |
| `STATELESS` | Không tạo hoặc dùng HTTP session để lấy SecurityContext | REST API xác thực độc lập từng request bằng token |

Cấu hình stateful:

~~~java
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));
~~~

Cấu hình stateless:

~~~java
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
~~~

`STATELESS` có nghĩa Spring Security không dùng HTTP session để lưu/khôi phục SecurityContext. Nó không ngăn mọi thành phần ứng dụng tự tạo session cho mục đích khác. Nếu muốn kiểm tra request không có session, cần chắc chắn controller, request cache, CSRF repository và filter tùy chỉnh không tạo session ngoài dự kiến.

- `IF_REQUIRED` không đảm bảo mọi request đều tạo session.
- `NEVER` vẫn có thể đọc session đã tồn tại và SecurityContext được lưu trong đó.
- `STATELESS` thường đi kèm `NullSecurityContextRepository` và request cache stateless, nhưng hãy kiểm tra cấu hình filter chain thực tế.
- Chính sách session của Spring Security và cơ chế lưu session của container/Spring Session là hai lớp cấu hình khác nhau.

## 4. Kiểm tra session được duy trì giữa hai request với MockMvc

### 4.1. Chuẩn bị ứng dụng form login

Giả sử ứng dụng có form login và endpoint đọc thông tin người dùng:

~~~java
@Configuration
class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login", "/assets/**").permitAll()
                    .requestMatchers("/api/me").authenticated()
                    .anyRequest().permitAll()
                )
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("mai")
                .password("{noop}secret")
                .roles("USER")
                .build()
        );
    }
}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api")
class AccountController {

    @GetMapping("/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }
}
~~~

Các lớp cần nằm trong phạm vi component scan của ứng dụng. `{noop}` chỉ phục vụ dữ liệu demo; ứng dụng thực tế cần PasswordEncoder phù hợp.

Cấu hình MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SessionPersistenceTest {

    @Autowired
    MockMvc mockMvc;
}
~~~

`@AutoConfigureMockMvc` tích hợp Spring Security filter chain. Nếu tự dựng MockMvc bằng `webAppContextSetup(context)`, hãy áp dụng `springSecurity()`.

### 4.2. Đăng nhập rồi gửi request kế tiếp với cùng MockHttpSession

`formLogin()` tạo request đăng nhập theo form login đã cấu hình. Sau khi đăng nhập thành công, lấy session từ request kết quả và gửi lại session đó ở request tiếp theo:

~~~java
@Test
void authenticatedSessionIsReusedOnNextRequest() throws Exception {
    MvcResult loginResult = mockMvc.perform(
                    formLogin().user("mai").password("secret"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("mai"))
            .andReturn();

    MockHttpSession session =
            (MockHttpSession) loginResult.getRequest().getSession(false);

    assertThat(session).isNotNull();

    mockMvc.perform(get("/api/me").session(session))
           .andExpect(status().isOk())
           .andExpect(authenticated().withUsername("mai"))
           .andExpect(jsonPath("$.username").value("mai"));
}
~~~

Test có hai request độc lập:

1. Request đầu gửi credentials và tạo trạng thái đăng nhập.
2. Request sau không gửi lại username/password; nó dùng cùng `MockHttpSession` để Spring Security khôi phục Authentication.

Nếu request thứ hai vẫn nhận username `mai`, đây là bằng chứng tích hợp rằng SecurityContext đã được lưu và nạp lại qua cơ chế session đang cấu hình. Nó mạnh hơn việc chỉ gọi `authenticated()` trên request đăng nhập đầu tiên.

`MockHttpSession` là đối tượng session mô phỏng của Spring Test. Trong MockMvc, nên truyền session bằng `.session(session)` để kiểm tra trạng thái phiên. Không cần tự tạo header `Cookie: JSESSIONID` cho trường hợp này.

### 4.3. Kiểm tra session không được tạo khi không cần

~~~java
@Test
void publicRequestDoesNotCreateSession() throws Exception {
    MvcResult result = mockMvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andReturn();

    assertThat(result.getRequest().getSession(false)).isNull();
}
~~~

Test này chỉ đúng khi toàn bộ filter chain và endpoint không cần session. Nếu CSRF, request cache hoặc thành phần ứng dụng tạo session, kết quả có thể khác.

## 5. Kiểm tra session fixation khi đăng nhập

Session fixation là tình huống kẻ tấn công biết trước session ID của nạn nhân và cố gắng khiến nạn nhân tiếp tục dùng ID đó sau khi đăng nhập. Spring Security cung cấp session fixation protection; với Servlet container hỗ trợ Servlet 3.1+, chiến lược mặc định thường đổi session ID khi xác thực thành công.

Có thể kiểm tra hành vi đổi ID khi ứng dụng sử dụng chiến lược `changeSessionId`:

~~~java
@Test
void sessionIdChangesAfterAuthentication() throws Exception {
    MockHttpSession preLoginSession = new MockHttpSession();
    String originalId = preLoginSession.getId();

    MvcResult loginResult = mockMvc.perform(
                    formLogin()
                        .user("mai")
                        .password("secret")
                        .session(preLoginSession))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("mai"))
            .andReturn();

    MockHttpSession authenticatedSession =
            (MockHttpSession) loginResult.getRequest().getSession(false);

    assertThat(authenticatedSession).isNotNull();
    assertThat(authenticatedSession.getId()).isNotEqualTo(originalId);
}
~~~

Test này giả định ứng dụng giữ session trước đăng nhập và sử dụng session fixation strategy đổi ID. Nếu ứng dụng cấu hình `newSession` hoặc chiến lược khác, hãy xác minh đúng hành vi tương ứng. Không kiểm tra ID đổi nếu ứng dụng chủ động tắt session fixation protection.

## 6. Kiểm tra logout và kết thúc phiên

Đăng xuất cần xóa SecurityContext và thực hiện các thao tác kết thúc phiên theo cấu hình. Với form login mặc định, Spring Security thường xử lý logout qua `POST /logout` và yêu cầu CSRF token.

~~~java
@Test
void logoutClearsAuthentication() throws Exception {
    MvcResult loginResult = mockMvc.perform(
                    formLogin().user("mai").password("secret"))
            .andExpect(authenticated().withUsername("mai"))
            .andReturn();

    MockHttpSession session =
            (MockHttpSession) loginResult.getRequest().getSession(false);

    assertThat(session).isNotNull();

    mockMvc.perform(logout().session(session))
           .andExpect(status().is3xxRedirection())
           .andExpect(unauthenticated());
}
~~~

Matcher trên logout result xác nhận request logout không còn Authentication đã xác thực. Nếu ứng dụng cấu hình logout URL, success handler hoặc response JSON riêng, hãy điều chỉnh status và response theo hợp đồng thực tế.

Để kiểm tra request sau logout, hãy gửi một request mới mà không tái sử dụng trạng thái session đã bị vô hiệu hóa, hoặc dùng integration test với client cookie jar thật. Không dựa vào một đối tượng MockHttpSession đã invalid để mô phỏng chính xác mọi hành vi của servlet container sau khi browser gửi lại session ID cũ.

Các thao tác logout thường cần xác minh thêm khi ứng dụng dùng:

- Cookie xác thực riêng: cookie bị xóa hoặc hết hạn theo hợp đồng.
- Remember-me: cookie remember-me bị xóa.
- Token revocation: refresh token hoặc server-side token record bị thu hồi.
- Spring Session: session bị invalidate hoặc xóa khỏi repository.
- Logout handler tùy chỉnh: cache, audit hoặc token store được cập nhật đúng.

## 7. Cookie trong MockMvc: phân biệt JSESSIONID và cookie ứng dụng

### 7.1. MockMvc quản lý session bằng MockHttpSession

Trong server Servlet thực tế, browser gửi session ID qua cookie thường có tên `JSESSIONID`. Tuy nhiên, MockMvc mô phỏng request/response trong bộ nhớ, không chạy browser hoặc servlet container thật qua socket. Response không nhất thiết phát hành cookie JSESSIONID giống môi trường triển khai.

Với test session persistence, dùng:

~~~java
mockMvc.perform(get("/api/me").session(session))
~~~

là cách trực tiếp để tái sử dụng session mô phỏng. Không nên tự dựng cookie JSESSIONID từ session ID rồi xem đó là kiểm tra end-to-end của container.

Nếu cần kiểm tra cookie do **ứng dụng tự phát hành** (ví dụ `APP_AUTH`, `refresh_token` hoặc cookie remember-me), hãy kiểm tra response cookie và gửi lại cookie đó trong request tiếp theo.

### 7.2. Kiểm tra thuộc tính cookie ứng dụng

Giả sử endpoint đăng nhập hoặc filter tùy chỉnh phát hành cookie `APP_AUTH`:

~~~java
@Test
void authenticationCookieHasExpectedSecurityAttributes() throws Exception {
    MvcResult result = mockMvc.perform(post("/test/auth-cookie")
                    .with(csrf()))
            .andExpect(status().isOk())
            .andReturn();

    Cookie cookie = result.getResponse().getCookie("APP_AUTH");

    assertThat(cookie).isNotNull();
    assertThat(cookie.isHttpOnly()).isTrue();
    assertThat(cookie.getSecure()).isTrue();
    assertThat(cookie.getPath()).isEqualTo("/");
    assertThat(result.getResponse().getHeader(HttpHeaders.SET_COOKIE))
            .contains("SameSite=Strict");
}
~~~

Đây là ví dụ giả định endpoint `/test/auth-cookie` thuộc test fixture và phát hành cookie với các thuộc tính đã nêu. Cookie thật cần được cấu hình để dùng HTTPS khi `Secure=true`; kiểm tra `SameSite` qua `Set-Cookie` vì API Servlet Cookie không đồng nhất giữa các phiên bản về thuộc tính này.

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `HttpOnly` | JavaScript phía client không đọc được cookie qua `document.cookie` |
| `Secure` | Browser chỉ gửi cookie qua kết nối HTTPS |
| `SameSite` | Hạn chế cookie được gửi trong ngữ cảnh cross-site |
| `Path` | Giới hạn đường dẫn request nhận cookie |
| `Max-Age` / `Expires` | Quy định thời gian cookie tồn tại |
| `Domain` | Giới hạn host nhận cookie |

Chọn `SameSite=Lax`, `Strict` hoặc `None` theo luồng đăng nhập và tích hợp cross-site; `SameSite=None` cần `Secure` theo quy tắc browser hiện đại.

### 7.3. Gửi lại cookie ứng dụng

Nếu authentication filter của ứng dụng đọc cookie `APP_AUTH`, có thể lấy cookie từ response trước và gửi lại:

~~~java
@Test
void applicationCookieCanBePresentedOnNextRequest() throws Exception {
    MvcResult issueResult = mockMvc.perform(post("/test/auth-cookie")
                    .with(csrf()))
            .andExpect(status().isOk())
            .andReturn();

    Cookie authCookie = issueResult.getResponse().getCookie("APP_AUTH");
    assertThat(authCookie).isNotNull();

    mockMvc.perform(get("/api/me").cookie(authCookie))
           .andExpect(status().isOk())
           .andExpect(authenticated().withUsername("mai"));
}
~~~

Test này chỉ đúng nếu ứng dụng có cơ chế đọc và xác minh cookie `APP_AUTH`. Spring Security không tự động coi mọi cookie tùy ý là Authentication. Nếu cookie chứa JWT, filter/resolver của ứng dụng phải trích xuất token, xác minh token và tạo Authentication trước khi request được phân quyền.

Với cookie chứa refresh token, hãy kiểm tra riêng endpoint refresh, rotation, expiration và revocation theo thiết kế token.

## 8. Xác minh SecurityContextRepository khi cần

### 8.1. Repository làm gì?

`SecurityContextRepository` là abstraction để lưu và nạp `SecurityContext`:

| Repository | Hành vi chính | Dùng khi |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Lưu SecurityContext trong HTTP session | Ứng dụng Servlet stateful |
| `RequestAttributeSecurityContextRepository` | Lưu context trong request attribute để dùng trong các dispatch của cùng request | Cần giữ context qua error/async dispatch |
| `NullSecurityContextRepository` | Không lưu/khôi phục context | SecurityContext stateless |
| `DelegatingSecurityContextRepository` | Kết hợp nhiều repository | Cấu hình Servlet mặc định thường kết hợp request attribute và HTTP session |

Trong các phiên bản Spring Security hiện đại, `SecurityContextHolderFilter` nạp context từ repository; việc lưu context được thực hiện rõ ràng bởi cơ chế xác thực hoặc thành phần được cấu hình. Khi xây authentication mechanism tùy chỉnh, cần bảo đảm nó gọi lưu context qua repository theo đúng vòng đời.

### 8.2. Ưu tiên kiểm tra round-trip

Cách kiểm tra tích hợp có giá trị nhất thường là:

1. Gửi request đăng nhập thành công.
2. Lấy session hoặc cookie được phát hành.
3. Gửi request mới kèm trạng thái phiên đó.
4. Khẳng định username/authority được khôi phục.

Test này chứng minh hợp đồng công khai của repository: context đã lưu có thể được nạp ở request sau. Nó không phụ thuộc tên session attribute nội bộ hoặc cấu trúc implementation.

Không nên đọc trực tiếp attribute nội bộ như `SPRING_SECURITY_CONTEXT` để chứng minh ứng dụng hoạt động. Hãy dùng request tiếp theo và result matcher.

### 8.3. Khi cần kiểm tra custom repository được gọi

Nếu ứng dụng tự triển khai `SecurityContextRepository` và cần xác minh nó nhận lệnh lưu context, có thể dùng spy trong test. Ví dụ giả định repository được khai báo thành bean riêng và gắn vào filter chain:

~~~java
@Bean
HttpSessionSecurityContextRepository securityContextRepository() {
    return new HttpSessionSecurityContextRepository();
}

@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        HttpSessionSecurityContextRepository repository) throws Exception {

    return http
            .securityContext(context -> context
                    .securityContextRepository(repository))
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
~~~

Với Spring Framework 6.2+ có thể dùng `@MockitoSpyBean`:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class RepositoryInteractionTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoSpyBean
    HttpSessionSecurityContextRepository repository;

    @Test
    void successfulLoginSavesAuthenticatedContext() throws Exception {
        mockMvc.perform(formLogin().user("mai").password("secret"))
               .andExpect(status().is3xxRedirection())
               .andExpect(authenticated().withUsername("mai"));

        verify(repository, atLeastOnce()).saveContext(
                argThat(context -> context.getAuthentication() != null),
                any(HttpServletRequest.class),
                any(HttpServletResponse.class));
    }
}
~~~

Các import Mockito/AssertJ và Servlet API được lược bớt. Với Spring Boot cũ chưa có `@MockitoSpyBean`, dùng cơ chế spy bean tương ứng của phiên bản đó.

Spy xác nhận phương thức `saveContext` được gọi; nó không tự chứng minh dữ liệu có thể khôi phục sau request. Khi yêu cầu là session persistence, hãy ưu tiên test round-trip ở mục 4.2. Không xác minh quá chặt số lần gọi hoặc chi tiết nội bộ nếu chúng không thuộc hợp đồng của custom repository.

### 8.4. Spring Session repository khác SecurityContextRepository

Nếu dùng Spring Session để lưu session vào Redis/JDBC, repository backend quản lý session record. SecurityContextRepository vẫn quyết định cách SecurityContext được gắn với session. Một test tích hợp có thể đăng nhập, giữ session ID/cookie và gửi request kế tiếp để chứng minh dữ liệu được phục hồi qua backend đang cấu hình.

Không dùng unit test mock SessionRepository để kết luận Redis/JDBC round-trip hoạt động. Muốn kiểm tra backend, cần integration test với cấu hình repository thật hoặc test container phù hợp.

## 9. Kiểm tra ứng dụng stateless không lưu Authentication vào session

Với API resource server dùng JWT và `SessionCreationPolicy.STATELESS`, mỗi request cần mang token hợp lệ. Test có thể xác nhận request có JWT giả lập được phép, nhưng request kế tiếp không có JWT vẫn anonymous và session không được dùng:

~~~java
@Test
void statelessJwtRequestDoesNotCreateOrReuseHttpSession() throws Exception {
    MvcResult authenticatedResult = mockMvc.perform(
                    get("/api/me").with(jwt()))
            .andExpect(status().isOk())
            .andExpect(authenticated())
            .andReturn();

    assertThat(authenticatedResult.getRequest().getSession(false)).isNull();

    mockMvc.perform(get("/api/me"))
           .andExpect(status().isUnauthorized())
           .andExpect(unauthenticated());
}
~~~

Ví dụ giả định resource server đã cấu hình `SessionCreationPolicy.STATELESS`, endpoint `/api/me` yêu cầu xác thực và request cache/CSRF không tạo session cho GET. `jwt()` giả lập Authentication cho request đầu; nó không xác minh JWT chữ ký thật. Test thứ hai không dùng lại Authentication, nên phải bị từ chối.

Nếu request stateless vẫn tạo session, hãy xem xét filter tùy chỉnh, request cache, CSRF token repository hoặc controller. Đừng quy mọi session creation cho SecurityContextRepository.

## 10. WebFlux: WebSession và repository Reactive

Ứng dụng Reactive dùng `WebSession` thay cho Servlet `HttpSession`. Spring Security Reactive có abstraction `ServerSecurityContextRepository`; implementation stateful thường dùng `WebSessionServerSecurityContextRepository`, còn cấu hình stateless có thể dùng `NoOpServerSecurityContextRepository`.

Khi WebFlux dùng cookie-based WebSession ID resolver, cookie mặc định thường tên `SESSION`; ứng dụng có thể đổi tên hoặc dùng header resolver. `WebTestClient` không nên được xem như browser tự động giữ cookie qua mọi lần gọi độc lập. Để kiểm tra session continuity, lấy cookie từ response đăng nhập rồi gửi lại trong request tiếp theo.

~~~java
@Test
void reactiveLoginSessionIsReusedOnNextRequest() {
    EntityExchangeResult<byte[]> loginResult = webTestClient.post()
            .uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("username", "mai")
                    .with("password", "secret"))
            .mutateWith(csrf())
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectBody()
            .returnResult();

    ResponseCookie sessionCookie =
            loginResult.getResponseCookies().getFirst("SESSION");

    assertThat(sessionCookie).isNotNull();

    webTestClient.get()
            .uri("/api/me")
            .cookie("SESSION", sessionCookie.getValue())
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("mai");
}
~~~

Đây là ví dụ cho WebFlux form login; endpoint, credentials, redirect và tên cookie phải khớp cấu hình ứng dụng. Nếu dùng `HeaderWebSessionIdResolver` hoặc cookie name tùy chỉnh, hãy gửi đúng header/cookie tương ứng.

`mockUser()` trên WebTestClient tạo danh tính thử nghiệm cho request được mutate. Nếu dùng `mockUser()` lại ở request thứ hai, test chỉ chứng minh cả hai request đều được gắn user giả lập; nó không chứng minh WebSession đã lưu và khôi phục SecurityContext. Muốn kiểm tra persistence, hãy đăng nhập qua flow thật của ứng dụng và tái sử dụng session cookie.

Với cấu hình Reactive stateless, dùng `NoOpServerSecurityContextRepository` và gửi JWT cho từng request. `mockJwt()` hữu ích để kiểm tra authorization với danh tính giả lập, nhưng không chứng minh token decoder hoặc việc lưu session.

## 11. Ma trận chọn assertion theo kiến trúc

| Kiến trúc | Trạng thái cần kiểm tra | Cách kiểm tra phù hợp |
| --- | --- | --- |
| Servlet form login stateful | Authentication được duy trì qua request | `MockHttpSession` lấy từ login result, gửi lại bằng `.session(session)` |
| Servlet logout | Context bị xóa, session kết thúc theo policy | `logout()` và matcher xác nhận logout result không còn authenticated |
| Servlet custom auth cookie | Cookie được phát hành và gửi lại | `getCookie(...)`, thuộc tính cookie và `.cookie(cookie)` |
| Servlet HTTP Basic stateless | Mỗi request xác thực từ credentials | Gửi `httpBasic(...)` ở từng request; không giả định session |
| Servlet JWT stateless | Không lưu SecurityContext trong HttpSession | `STATELESS`, request không JWT bị từ chối, kiểm tra không có session nếu policy yêu cầu |
| Custom SecurityContextRepository | Gọi save/load và round-trip đúng | Integration test nhiều request; spy khi cần kiểm tra tương tác |
| Spring Session Redis/JDBC | Session tồn tại qua backend | Integration test với session ID/cookie và backend thật |
| WebFlux form login stateful | SecurityContext khôi phục qua WebSession | Đăng nhập, lấy cookie `SESSION`, gửi lại trong request sau |
| WebFlux stateless JWT | Không lưu context vào WebSession | `NoOpServerSecurityContextRepository`, JWT cho từng request |

Không nên thêm test session cho endpoint chỉ xác thực độc lập từng request nếu kiến trúc không sử dụng session. Khi đó, test cần tập trung vào token validation, authorization và việc không phụ thuộc session.

## 12. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Login request authenticated nhưng request kế tiếp anonymous | SecurityContext không được lưu, session không được gửi lại hoặc repository không được gắn vào filter chain | Kiểm tra save/load và truyền cùng session/cookie |
| MockMvc không có cookie JSESSIONID | MockMvc không chạy browser/container thật | Dùng `.session(MockHttpSession)` để kiểm tra session persistence |
| Test dùng `@WithMockUser` rồi kết luận session được duy trì | Annotation tạo SecurityContext cho test, không mô phỏng login rồi lưu session | Thực hiện login và gửi request tiếp theo với session |
| Cookie có nhưng request sau vẫn anonymous | Filter không đọc cookie, token hết hạn/sai hoặc cookie không được gửi đúng path/domain | Kiểm tra authentication resolver và round-trip cookie |
| Cookie thiếu HttpOnly/Secure/SameSite | Cookie serializer hoặc response handler cấu hình thiếu thuộc tính | Kiểm tra `Set-Cookie` và cấu hình phát hành cookie |
| JWT stateless vẫn tạo session | Filter/request cache/CSRF/controller khác tạo session | Kiểm tra toàn bộ filter chain và session policy |
| Spy không thấy `saveContext` | Spy sai bean hoặc authentication mechanism dùng repository khác | Kiểm tra bean được gắn vào `HttpSecurity` |
| Test Redis session pass với mock nhưng production fail | Mock không kiểm tra backend thực | Chạy integration test với repository/backend thật |
| WebFlux request thứ hai mất đăng nhập | Không gửi lại WebSession ID hoặc resolver khác cookie mặc định | Truyền cookie/header session đúng cấu hình |

## 13. Bài tập thực hành

Dùng một ứng dụng form login và một API JWT để thực hiện:

1. Đăng nhập bằng MockMvc, lấy `MockHttpSession`, gửi request `/api/me` tiếp theo với cùng session và xác nhận username vẫn là `mai`.
2. Cấu hình session fixation protection và kiểm tra session ID thay đổi sau khi đăng nhập thành công.
3. Gọi logout bằng session đã đăng nhập, xác nhận request logout không còn authenticated và kiểm tra cookie/session được xóa theo policy.
4. Với cookie `APP_AUTH` do ứng dụng phát hành, kiểm tra `HttpOnly`, `Secure`, `SameSite`, `Path` và round-trip cookie qua request tiếp theo.
5. Cấu hình custom `SecurityContextRepository`; kiểm tra login gọi `saveContext` và request sau khôi phục đúng Authentication.
6. Cấu hình `SessionCreationPolicy.STATELESS`; kiểm tra request có JWT giả lập được phép, request tiếp theo không có JWT bị từ chối và không dựa vào HTTP session.
7. Với WebFlux form login, lấy cookie `SESSION` sau login rồi gửi lại để kiểm tra WebSession persistence. So sánh với `mockUser()` trên hai request độc lập.
8. Nếu dùng Spring Session Redis/JDBC, viết integration test kiểm tra session round-trip qua backend thật.

**Tiêu chí hoàn thành:** Người học phân biệt được session, cookie và repository; kiểm tra được SecurityContext qua nhiều request; biết khi nào dùng MockHttpSession, cookie round-trip hoặc repository spy; đồng thời không nhầm danh tính giả lập cho từng request với phiên đăng nhập được duy trì.

## Tài liệu tham khảo chính thức

- [Spring Security — SecurityContext Persistence](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Session Fixation Protection](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html#servlet-session-fixation)
- [Spring Security — Testing Spring MVC Applications](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security — Testing Form Login](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html)
- [Spring Security — Reactive SecurityContext](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html)

Các ví dụ lược bớt import thông thường. Tùy đoạn mã, cần thêm `HttpHeaders`, `MediaType`, `Cookie`, `MockHttpSession`, `MvcResult`, `Authentication`, `SecurityContextRepository`, `HttpServletRequest`, `HttpServletResponse`, `ResponseCookie`, `EntityExchangeResult`, `BodyInserters`, các static import của MockMvc/SecurityMockMvc, Mockito và AssertJ.
