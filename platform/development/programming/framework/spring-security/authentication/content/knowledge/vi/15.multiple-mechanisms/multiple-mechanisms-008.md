# Kiểm thử toàn bộ đường đăng nhập và chuỗi dự phòng trong Spring Security

> **Mục tiêu:** Kiểm thử một hệ thống có **nhiều cơ chế xác thực** sao cho từng cách đăng nhập hoạt động đúng, đường sai bị từ chối đúng, quyền không bị nâng ngoài ý muốn, request luôn đi qua **SecurityFilterChain** dự kiến và chuỗi/provider dự phòng không vô tình trở thành lối vượt xác thực. Phải phân biệt **fallback giữa AuthenticationProvider** với **chain cuối bao phủ request còn lại**.

## 1. Vì sao cần kiểm thử theo đường đi hoàn chỉnh?

Một ứng dụng có thể cho phép người dùng web đăng nhập bằng form, cung cấp API cho client dùng HTTP Basic, cho dịch vụ nội bộ dùng API key, hoặc kiểm tra bearer token do IdP cấp. Đơn vị kiểm thử đơn lẻ có thể xác nhận rằng hàm so sánh mật khẩu đúng, nhưng vẫn bỏ sót các lỗi có hậu quả lớn:

- **/api/** chọn nhầm chain dành cho web và trả HTML redirect thay vì 401.
- Endpoint **/login** không thuộc SecurityFilterChain chứa **UsernamePasswordAuthenticationFilter**, khiến form không đăng nhập được.
- Chain khớp rộng, có ưu tiên cao, che một chain yêu cầu quyền mạnh hơn.
- Một AuthenticationProvider đã từ chối credential nhưng provider đứng sau lại chấp nhận cùng token theo chính sách lỏng.
- Một request không khớp chain nào nên nằm ngoài bảo vệ của Spring Security.
- Client gửi header API key nhưng không có filter chuyển header đó thành Authentication phù hợp; provider chưa bao giờ được gọi.
- Test giả danh bằng **@WithMockUser** hoặc **with(user(...))** vẫn xanh trong khi cơ chế kiểm tra credential thật bị hỏng.
- Login thành công nhưng session không duy trì, logout không xóa session, token hết hạn vẫn được chấp nhận, CSRF bị bỏ qua hoặc thông tin nhạy cảm lộ trong log.

Muốn kiểm thử “toàn bộ đường đăng nhập”, phải xác nhận **từ request → chain → filter → manager → provider → SecurityContext → authorization → response**. Đồng thời phải thử nhánh không có credential, credential sai, credential hợp lệ, lỗi nguồn danh tính và tình huống fallback.

## 2. Hai loại dự phòng tuyệt đối không được nhầm

### 2.1. Fallback của FilterChainProxy: chọn chain đầu tiên khớp

~~~text
HTTP request
    |
    v
FilterChainProxy
    |
    +-- @Order(1) chain /api/**        -- khớp? --> chạy chain API
    |                                      |
    |                                      +-- 401/403/200: kết thúc xử lý
    |
    +-- @Order(2) chain /web/**,/login -- khớp? --> chạy chain Web
    |                                      |
    |                                      +-- redirect/403/200
    |
    +-- @Order(3) chain catch-all      --------> từ chối phần còn lại
~~~

Spring Security chọn **SecurityFilterChain đầu tiên khớp** request. Nếu chain API đã được chọn nhưng HTTP Basic thất bại, **FilterChainProxy không chuyển sang chain Web** để “đăng nhập lại”. Chuỗi catch-all chỉ được chọn khi những matcher trước **không khớp request**, không phải khi xác thực ở chain trước bị từ chối.

Một **SecurityFilterChain** chứa bộ lọc và chính sách riêng như **httpBasic**, **formLogin**, **csrf**, **sessionManagement**, **exceptionHandling** và **authorizeHttpRequests**. **securityMatcher(...)** chọn phạm vi áp dụng chain; **requestMatchers(...)** nằm bên trong authorization của chain đã được chọn. Thiếu chain cuối có thể để lộ request không được Spring Security bảo vệ.

### 2.2. Fallback của ProviderManager: thử provider theo loại token và kết quả

~~~text
BasicAuthenticationFilter
  |
  | UsernamePasswordAuthenticationToken (chưa xác thực)
  v
ProviderManager
  |
  +-- Provider A.supports(token.class)?
  |       |
  |       +-- trả Authentication thành công -> dừng; dùng kết quả A
  |       +-- trả null ----------------------> thử provider kế tiếp
  |       +-- BadCredentialsException ------> có thể thử provider kế tiếp
  |       +-- AccountStatusException ------> dừng ngay
  |
  +-- Provider B.supports(token.class)?
  |       |
  |       +-- ...
  |
  +-- parent AuthenticationManager (nếu cấu hình và phù hợp)
  |
  +-- không ai xác thực -> AuthenticationException
~~~

**ProviderManager** duyệt các AuthenticationProvider. Khi provider sau xác thực thành công, nó có thể thay thế lỗi **BadCredentialsException** của provider trước; ngược lại **AccountStatusException** khiến việc duyệt provider dừng. **ProviderNotFoundException** cho biết không có provider phù hợp để xử lý Authentication theo cấu hình. Hành vi phải được kiểm chứng bằng test, đặc biệt khi **hai provider cùng supports(UsernamePasswordAuthenticationToken.class)**.

**Khác nhau:** chain fallback chọn theo **HttpServletRequest** và ưu tiên matcher; provider fallback diễn ra khi manager xử lý **Authentication** ở bên trong chain. Chúng không phải hai tên gọi của cùng một tính năng.

## 3. Thiết kế ma trận kiểm thử trước khi viết test

Bước đầu tiên là liệt kê **cơ chế thực tế của dự án**, URL, loại credential, filter tạo Authentication, manager/provider, trạng thái phiên, mức quyền và entry point lỗi. Bảng dưới đây là ví dụ cho một ứng dụng có **HTTP Basic API**, **form login web** và **catch-all deny**.

| Đường đi / tình huống | Chain kỳ vọng | HTTP/ứng xử kỳ vọng | Bằng chứng cần kiểm tra |
| --- | --- | --- | --- |
| GET /api/me không có Basic | apiChain | **401**, thách thức Basic | Không tự chạy form-login |
| GET /api/me với Basic đúng | apiChain | **200**, principal đúng | Credential được xác thực thực |
| GET /api/me với Basic sai | apiChain | **401** | Không chuyển sang webChain |
| GET /api/admin với user thường | apiChain | **403** | Xác thực thành công nhưng thiếu role |
| GET /web/me chưa đăng nhập | webChain | **302** tới /login | Entry point là form login |
| GET /login | webChain | **200 HTML** | Trang do filter cung cấp nằm trong chain |
| POST /login đúng, CSRF hợp lệ | webChain | **302** đến /web/me | Tạo session hợp lệ |
| POST /login sai, CSRF hợp lệ | webChain | **302** đến /login?error | Không cấp session xác thực |
| POST /login thiếu/sai CSRF | webChain | **403** | Bị chặn trước khi xử lý credential |
| GET /web/me với session hợp lệ | webChain | **200**, principal đúng | SecurityContext được khôi phục |
| GET /web/me với Basic nhưng không có session | webChain | **302** tới /login | Header Basic không tự kích hoạt filter Basic |
| POST /logout với session và CSRF | webChain | Redirect theo cấu hình | Session/logout được xử lý |
| GET /unknown | fallbackChain | **403** | Không lọt khỏi SecurityFilterChain |
| GET /unknown dù có Basic hợp lệ | fallbackChain | **403** | Credential không tự mở vùng bị chặn |
| API có cookie web nhưng không có Basic | apiChain | Theo chính sách stateless, **401** | Không vô tình dùng session web |
| API key/JWT sai/hết hạn nếu dự án có | Chain/filter tương ứng | **401** | Token được verify đầy đủ và không fallback yếu |
| Nguồn danh tính mất kết nối | Provider tương ứng | Từ chối an toàn | Không “accept” tạm hoặc cấp role mặc định |

**HTTP status chỉ là một phần của bài test.** Kiểm tra thêm **Location**, **WWW-Authenticate**, Content-Type, principal, authorities, cookie/session, CSRF và filter/chain thực sự được sử dụng. Các trường hợp nhiều cơ chế có cùng status 401 càng cần kiểm tra chain/filter để tránh “test xanh nhưng chọn sai đường”.

### 3.1. Danh mục các nhánh phải có

1. **Happy path** của từng cơ chế: đúng credential, đúng subject, đúng quyền và trạng thái phiên/token.
2. **Invalid evidence**: sai mật khẩu, thiếu credential, API key không tồn tại, chữ ký JWT sai, token hết hạn, issuer/audience không phù hợp.
3. **Account state**: disabled, locked, expired, revoked, đổi password hoặc thu hồi key.
4. **Authorization**: đã login nhưng thiếu role/scope phải bị 403; role client tự gửi không trở thành quyền.
5. **Session/CSRF**: login cần token hợp lệ nếu có cookie session; session fixation; logout; cookie thuộc đúng nơi; API stateless không dựa vào session.
6. **Routing**: matcher giao nhau, thứ tự chain, endpoint /login và /logout, request chưa được định nghĩa, method khác GET, error/dispatch, khoảng trống URL.
7. **Provider fallback**: thứ tự hỗ trợ, trả null, lỗi credential, AccountStatusException, parent manager, trường hợp không provider hỗ trợ và sự cố nguồn dữ liệu.
8. **Failure response**: 401/403/302 đúng nghĩa, không để lộ mật khẩu/stack trace, không có “200 với success=false” thay cho HTTP lỗi.
9. **Vận hành**: logging/auditing không chứa secrets, kiểm soát rate limit, retry không khuếch đại tấn công, xử lý timeout.

Không có một test duy nhất bao phủ đủ các lớp. Hãy kết hợp **test provider độc lập** với **MockMvc tích hợp FilterChainProxy thực** và một số bài kiểm thử chạy qua proxy/TLS thật khi triển khai.

## 4. Ví dụ có thể chạy: HTTP Basic + form login + fallback deny

Phần này cung cấp **một dự án thực hành độc lập** với **Java 17+, Spring Boot 3.x, Spring Security 6.x (Servlet/MVC)**. Tạo dự án Spring Initializr với **Spring Web**, **Spring Security**, **Spring Boot Starter Test**; thêm **spring-security-test** trong test scope. Dự án dùng package **com.example.authpaths**.

Trong tệp **pom.xml**, phần dependencies cần có (Spring Boot parent/BOM quản lý version):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

### 4.1. Khởi động ứng dụng

Tệp **src/main/java/com/example/authpaths/AuthPathsApplication.java**:

~~~java
package com.example.authpaths;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthPathsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthPathsApplication.class, args);
    }
}
~~~

Tệp **src/main/resources/application.properties**:

~~~properties
server.port=8080
demo.user.password=${DEMO_USER_PASSWORD}
~~~

Không hard-code mật khẩu thực trong mã hoặc cấu hình commit vào repository. Giá trị **demo-pass** ở bài này chỉ dành cho môi trường phát triển localhost.

### 4.2. Cấu hình ba SecurityFilterChain có thứ tự rõ ràng

Tệp **src/main/java/com/example/authpaths/SecurityConfig.java**:

~~~java
package com.example.authpaths;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String password) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode(password))
                        .roles("USER")
                        .build());
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .requestCache(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/web/**", "/login", "/logout")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/web/public", "/login").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(form -> form
                        .defaultSuccessUrl("/web/me", true))
                .logout(logout -> logout
                        .logoutSuccessUrl("/web/public?logout"))
                .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().denyAll())
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(
                                new HttpStatusEntryPoint(
                                        HttpStatus.FORBIDDEN))
                        .accessDeniedHandler((req, res, ex) ->
                                res.sendError(
                                        HttpServletResponse.SC_FORBIDDEN)))
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .requestCache(AbstractHttpConfigurer::disable)
                .build();
    }
}
~~~

Những điểm phải hiểu trước khi chạy:

- **apiChain** khớp **/api/** trước tiên, dùng HTTP Basic. User mẫu có **ROLE_USER**, nên gọi **/api/admin** bị 403 ngay cả với password đúng.
- **webChain** khớp **/web/** cộng với **/login** và **/logout**. Đây là chi tiết quan trọng: filter form login mặc định xử lý **POST /login**, sinh trang **GET /login** và logout tại **/logout**. Nếu bỏ các path này khỏi matcher, đăng nhập/đăng xuất có thể bị chain khác chặn.
- **fallbackChain** không đặt securityMatcher, là chain cuối khớp mọi request còn lại. Cấu hình ví dụ từ chối bằng **403** và không bật Basic/form login. Đây là lựa chọn kiểm thử rõ ràng cho một ứng dụng demo có danh sách route hữu hạn.
- Cấu hình dùng **UserDetailsService** và **PasswordEncoder** chung để Spring Security có thể xác minh username/password cho Basic và form. Có nhiều chain không mặc nhiên chứng minh chúng sử dụng cùng một instance AuthenticationManager; nếu yêu cầu chia sẻ instance, phải wiring manager rõ ràng.
- **SessionCreationPolicy.STATELESS** ở API đảm bảo chain API không dùng HTTP session để lấy SecurityContext. Chain web vẫn dùng session để lưu đăng nhập.
- Bài này giữ nguyên bảo vệ **CSRF** mặc định trên web. HTTP Basic nếu được dùng từ trình duyệt cũng có mối quan hệ với CSRF cần đánh giá theo client; không tự tắt CSRF chỉ vì API thường gọi từ máy.
- Ở môi trường thật, endpoint có credential phải dùng HTTPS; ví dụ HTTP localhost chỉ dùng cho bài thực hành. Không đưa biến môi trường mật khẩu và credential vào log.

### 4.3. Tạo các endpoint để quan sát

Tệp **src/main/java/com/example/authpaths/RoutesController.java**:

~~~java
package com.example.authpaths;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RoutesController {

    @GetMapping("/api/me")
    public String apiMe(Authentication authentication) {
        return "api " + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String apiAdmin() {
        return "admin";
    }

    @GetMapping("/web/me")
    public String webMe(Authentication authentication) {
        return "web " + authentication.getName();
    }

    @GetMapping("/web/public")
    public String publicPage() {
        return "public";
    }
}
~~~

Bốn endpoint có đủ kịch bản: cần Basic, cần role cao hơn, cần session web và public. Không định nghĩa route **/unlisted** để test fallback.

Khởi động ở Linux/macOS:

~~~bash
export DEMO_USER_PASSWORD=demo-pass
./mvnw spring-boot:run
~~~

Trên PowerShell:

~~~powershell
$env:DEMO_USER_PASSWORD = "demo-pass"
.\mvnw.cmd spring-boot:run
~~~

Thử API bằng curl:

~~~bash
curl -i http://localhost:8080/api/me
curl -i -u alice:demo-pass http://localhost:8080/api/me
curl -i -u alice:wrong http://localhost:8080/api/me
curl -i -u alice:demo-pass http://localhost:8080/api/admin
curl -i http://localhost:8080/web/me
curl -i http://localhost:8080/login
curl -i http://localhost:8080/unlisted
~~~

Kỳ vọng về status theo thứ tự: **401, 200, 401, 403, 302, 200, 403**. Response thành công từ **/api/me** có body **api alice**. Trang **/login** là HTML mặc định của Spring Security; **/web/me** khi chưa có session chuyển hướng đến trang login.

Với flow form thực, browser phải giữ cookie session và gửi CSRF token trong POST. Không nên dùng lệnh POST form thiếu CSRF rồi kết luận “password bị từ chối”: khi đó request có thể bị **CsrfFilter** chặn từ trước.

## 5. Kiểm thử tích hợp bằng MockMvc

Tệp **src/test/java/com/example/authpaths/AuthPathsIntegrationTest.java**:

~~~java
package com.example.authpaths;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "demo.user.password=demo-pass")
@AutoConfigureMockMvc
class AuthPathsIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    FilterChainProxy springSecurityFilterChain;

    private SecurityFilterChain firstMatchingChain(String path) {
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", path);
        return springSecurityFilterChain.getFilterChains().stream()
                .filter(chain -> chain.matches(request))
                .findFirst()
                .orElseThrow();
    }

    @Test
    void chainMatchersAndFilterTypesAreCorrect() {
        List<SecurityFilterChain> chains =
                springSecurityFilterChain.getFilterChains();

        assertEquals(3, chains.size());
        assertSame(chains.get(0), firstMatchingChain("/api/me"));
        assertSame(chains.get(0), firstMatchingChain("/api/admin"));
        assertSame(chains.get(1), firstMatchingChain("/web/me"));
        assertSame(chains.get(1), firstMatchingChain("/login"));
        assertSame(chains.get(1), firstMatchingChain("/logout"));
        assertSame(chains.get(2), firstMatchingChain("/unlisted"));

        assertTrue(chains.get(0).getFilters().stream()
                .anyMatch(f -> f instanceof BasicAuthenticationFilter));
        assertFalse(chains.get(0).getFilters().stream()
                .anyMatch(f -> f instanceof UsernamePasswordAuthenticationFilter));

        assertTrue(chains.get(1).getFilters().stream()
                .anyMatch(f -> f instanceof UsernamePasswordAuthenticationFilter));
        assertFalse(chains.get(1).getFilters().stream()
                .anyMatch(f -> f instanceof BasicAuthenticationFilter));
    }

    @Test
    void basicPathMustValidateRealCredentials() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("api alice"));

        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "wrong")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserWithoutAdminRoleGets403() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void formAndBasicCannotSwapPaths() throws Exception {
        mvc.perform(get("/web/me"))
                .andExpect(status().is3xxRedirection());

        mvc.perform(get("/web/me")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().is3xxRedirection());

        mvc.perform(get("/login"))
                .andExpect(status().isOk());

        mvc.perform(get("/web/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void validFormLoginPersistsIdentityInSession() throws Exception {
        MvcResult login = mvc.perform(formLogin()
                        .user("alice")
                        .password("demo-pass"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/web/me"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/web/me").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("web alice"));

        // Web session không phải Basic credential cho API stateless.
        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void failedFormLoginStaysFailed() throws Exception {
        mvc.perform(formLogin()
                        .user("alice")
                        .password("wrong"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void missingAndInvalidCsrfAreRejected() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "alice")
                        .param("password", "demo-pass"))
                .andExpect(status().isForbidden());

        mvc.perform(post("/login")
                        .with(csrf().useInvalidToken())
                        .param("username", "alice")
                        .param("password", "demo-pass"))
                .andExpect(status().isForbidden());
    }

    @Test
    void logoutWithValidCsrfHasConfiguredRedirect() throws Exception {
        MvcResult login = mvc.perform(formLogin()
                        .user("alice")
                        .password("demo-pass"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout")
                        .session(session)
                        .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/web/public?logout"));
    }

    @Test
    void catchAllRejectsUnknownPathEvenWithBasic() throws Exception {
        mvc.perform(get("/unlisted"))
                .andExpect(status().isForbidden());

        mvc.perform(get("/unlisted")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

Trong PowerShell dùng **.\mvnw.cmd test**. Kết quả kỳ vọng là **các test đều PASS**; số lượng log và thời gian chạy phụ thuộc môi trường, nên không đưa ra stdout giả.

### 5.1. Vì sao mỗi nhóm assert cần thiết?

- **chainMatchersAndFilterTypesAreCorrect**: test trực tiếp **FilterChainProxy.getFilterChains()**. Không chỉ dựa vào status để suy ra chain, đồng thời xác minh filter Basic và form nằm ở đúng chain.
- **basicPathMustValidateRealCredentials**: gửi credential thật qua processor **httpBasic(...)**, đi qua filter và provider. Với **@WithMockUser** hoặc **with(user(...))**, bài test có thể qua được dù password không đúng vì chúng chủ động gắn security context giả.
- **authenticatedUserWithoutAdminRoleGets403**: xác nhận khác nhau giữa authentication và authorization.
- **formAndBasicCannotSwapPaths**: đảm bảo form chain được chọn, HTTP Basic không tự hoạt động trên URL web, và trang /login thuộc đúng chain.
- **validFormLoginPersistsIdentityInSession**: test cả POST login và request **tiếp theo** dùng cùng session. Nhờ đó phát hiện trường hợp login trả 302 thành công nhưng SecurityContext không được lưu.
- **failedFormLoginStaysFailed**: kết quả credential sai phải nằm ở nhánh thất bại và chuyển tới /login?error.
- **missingAndInvalidCsrfAreRejected**: đảm bảo không lẫn lỗi CSRF với sai mật khẩu. Processor **formLogin()** của spring-security-test tự đưa CSRF token hợp lệ; request POST thủ công dùng để cố ý kiểm tra thiếu/sai token.
- **logoutWithValidCsrfHasConfiguredRedirect**: xác minh endpoint logout được xử lý đúng bởi webChain. Trong dự án thật nên kiểm tra thêm vô hiệu hóa session/cookie và không thể dùng lại session đã logout.
- **catchAllRejectsUnknownPathEvenWithBasic**: xác nhận không có đường đi “lọt qua” chain cuối; một header credential không khiến fallback chain tự chuyển sang apiChain.

**Giới hạn:** test này giả lập HTTP bằng MockMvc, không kiểm chứng TLS, reverse proxy, header được gateway ghi lại hay cookie Secure/SameSite trong production. Các yếu tố đó cần thêm test ở mức tích hợp triển khai. Test cũng giả định có **chính xác ba chain** như source; nếu ứng dụng có actuator hoặc cấu hình khác thêm chain, hãy điều chỉnh assertion theo sơ đồ bảo mật đã thiết kế.

## 6. Kiểm thử ProviderManager fallback độc lập

Phần 5 kiểm chứng **đường request và chain**. Ta cần test riêng cách **ProviderManager** duyệt nhiều provider, bởi fallback provider **không có nghĩa** fallback chain. Ví dụ sau không dựng web server, chỉ dùng Spring Security Core và JUnit 5, phù hợp trong **cùng dự án** ở mục 4.

Tệp **src/test/java/com/example/authpaths/ProviderManagerFallbackTest.java**:

~~~java
package com.example.authpaths;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;

class ProviderManagerFallbackTest {

    private Authentication request() {
        return UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-pass");
    }

    private Authentication verified(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
                username, null,
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private AuthenticationProvider stub(
            String name,
            List<String> calls,
            Function<Authentication, Authentication> action) {
        return new AuthenticationProvider() {

            @Override
            public Authentication authenticate(Authentication auth) {
                calls.add(name);
                return action.apply(auth);
            }

            @Override
            public boolean supports(Class<?> type) {
                return UsernamePasswordAuthenticationToken.class
                        .isAssignableFrom(type);
            }
        };
    }

    @Test
    void firstSuccessStopsFurtherProviders() {
        List<String> calls = new ArrayList<>();
        var manager = new ProviderManager(List.of(
                stub("first", calls, auth -> verified("alice")),
                stub("second", calls, auth -> verified("other"))));

        Authentication result = manager.authenticate(request());

        assertEquals("alice", result.getName());
        assertEquals(List.of("first"), calls);
    }

    @Test
    void badCredentialsMayBeOverriddenByLaterSuccess() {
        List<String> calls = new ArrayList<>();
        var manager = new ProviderManager(List.of(
                stub("first", calls, auth -> {
                    throw new BadCredentialsException("wrong");
                }),
                stub("second", calls, auth -> verified("alice"))));

        Authentication result = manager.authenticate(request());

        assertTrue(result.isAuthenticated());
        assertEquals("alice", result.getName());
        assertEquals(List.of("first", "second"), calls);
    }

    @Test
    void accountLockedStopsProviderChain() {
        List<String> calls = new ArrayList<>();
        var manager = new ProviderManager(List.of(
                stub("locked", calls, auth -> {
                    throw new LockedException("Account locked");
                }),
                stub("second", calls, auth -> verified("alice"))));

        assertThrows(LockedException.class,
                () -> manager.authenticate(request()));
        assertEquals(List.of("locked"), calls);
    }

    @Test
    void unsupportedTokenFailsWithoutAlternateProvider() {
        List<String> calls = new ArrayList<>();
        var manager = new ProviderManager(List.of(
                stub("password", calls, auth -> verified("alice"))));

        assertThrows(ProviderNotFoundException.class,
                () -> manager.authenticate(
                        new TestingAuthenticationToken(
                                "alice", "demo-pass")));
        assertTrue(calls.isEmpty());
    }

    @Test
    void parentManagerMayHandleRequestAfterNull() {
        List<String> calls = new ArrayList<>();
        var parent = (org.springframework.security.authentication.AuthenticationManager)
                auth -> {
                    calls.add("parent");
                    return verified("alice");
                };

        var manager = new ProviderManager(
                List.of(stub("child", calls, auth -> null)),
                parent);

        Authentication result = manager.authenticate(request());

        assertEquals("alice", result.getName());
        assertEquals(List.of("child", "parent"), calls);
    }
}
~~~

Chạy riêng test provider:

~~~bash
./mvnw -Dtest=ProviderManagerFallbackTest test
~~~

Trong PowerShell:

~~~powershell
.\mvnw.cmd '-Dtest=ProviderManagerFallbackTest' test
~~~

Đây là những **behavior tests**, không phải đề xuất cho phép credential sai ở provider đầu rồi vô điều kiện chấp nhận ở provider sau. Test thứ hai cố tình chứng minh **rủi ro fallback**: khi nhiều provider cùng hỗ trợ một token, lỗi BadCredentialsException của provider trước **có thể bị thay thế** bởi provider sau xác thực thành công. Nếu chính sách không cho phép điều đó, hãy thiết kế token type tách biệt, phân luồng nguồn danh tính chặt chẽ, kiểm tra các provider cùng supports và test các nhánh chặn tương ứng.

Test khóa tài khoản chứng minh **LockedException** thuộc nhóm **AccountStatusException** chặn việc thử tiếp. Test parent chứng minh **parent AuthenticationManager** là một tầng fallback có thể tồn tại; phải kiểm tra nó đã được cấu hình hay chưa trong từng hệ thống.

**Không dùng ProviderManager test để kết luận request đi đúng HTTP filter.** Nó gọi manager trực tiếp, không qua FilterChainProxy, CSRF, entry point hoặc SecurityContextRepository. Hai nhóm test bổ sung cho nhau.

## 7. Khi dùng API key, bearer/JWT, OAuth2/OIDC hoặc login JSON

Mô hình ví dụ chỉ triển khai Basic và form. Ở dự án thực có thêm cơ chế, tạo thêm các hàng trong ma trận, cụ thể:

| Cơ chế | Happy path | Negative path tối thiểu | Điểm cần quan sát |
| --- | --- | --- | --- |
| **API key** | Key hợp lệ, subject/permission từ kho cấp key | Key không tồn tại, sai, hết hạn, thu hồi, sai scope | Custom filter có thực tạo ApiKeyAuthenticationToken và gọi đúng provider? |
| **JWT access token** | Chữ ký, issuer, audience, thời gian, scope đúng | Chữ ký giả, alg lạ, issuer/audience sai, hết hạn, nbf tương lai, thiếu quyền | Token có được verify hay chỉ decode payload? |
| **OIDC login** | Redirect đúng IdP, state/nonce và callback hợp lệ | State sai, nonce không khớp, code hết hạn/dùng lại, callback sai | OAuth2LoginAuthenticationFilter, session và redirect URI có đúng? |
| **SAML login** | Assertion ký hợp lệ, gắn đúng SP | Chữ ký sai, audience/recipient sai, replay, hết hạn | IdP trust config và replay protection |
| **JSON username/password** | Body hợp lệ, AuthenticationManager xác thực, session/token lưu đúng | JSON hỏng, thiếu trường, sai password, sai CSRF, lỗi nguồn | Controller/filter nào trả 400/401/403? Phản hồi JSON có thống nhất? |
| **mTLS** | Client cert chain hợp lệ, mapping identity đúng | Cert giả, bị thu hồi, mapping không tồn tại | Bằng chứng đến từ TLS đã xác minh, không phải header tự khai |
| **Fallback chung** | Route mới phải được policy rõ ràng xét tới | Unknown path, method mới, header lạ, trùng matcher | Catch-all có chặn hay route nằm ngoài filter chain? |

Cần phân biệt “cơ chế **được cấu hình**” với “cơ chế **thực sự có filter nhận bằng chứng**”. Đăng ký API key provider trong manager không tự thêm filter đọc **X-API-Key**. Đăng ký JWT decoder không đồng nghĩa mọi chain đều có **BearerTokenAuthenticationFilter**. Kiểm tra danh sách filter của chain và request thực có token hợp lệ, thay vì chỉ test unit provider.

**Với JWT và OIDC**, ưu tiên test qua thành phần Spring Security chuẩn, bao gồm **JwtDecoder**/trust configuration được dùng ở production. Mocks có thể xác nhận authorization nhanh, nhưng cần một số test với token ký sai, issuer/audience sai và khóa không tin cậy để đảm bảo bước xác minh thật hoạt động. Không dùng payload Base64 decode được làm bằng chứng đã được ký.

## 8. Kiểm thử đường lỗi và quy tắc an toàn

### 8.1. Phải phân biệt 401, 403 và redirect

- **401 Unauthorized**: yêu cầu HTTP authentication chưa được thỏa mãn hoặc credential sai (thường qua AuthenticationEntryPoint). HTTP Basic có thể kèm **WWW-Authenticate**.
- **403 Forbidden**: đã xác thực nhưng không đủ quyền, hoặc bị CSRF/một chính sách từ chối. Fallback chain ở ví dụ được cấu hình trả 403 cho mọi request không nằm trong vùng cho phép.
- **302 Found / 303 See Other**: thường là một phần của form login và trình duyệt. Redirect sau POST thành công là hành vi bình thường, nhưng trong API dùng bearer/Basic, redirect HTML bất ngờ thường là dấu hiệu chọn sai chain.

Đừng mặc định mọi lỗi xác thực luôn là 401. Với form login, password sai thường đưa về **/login?error**. Vì vậy test phải dựa trên **hợp đồng của từng cơ chế**, không gộp mọi flow vào một kỳ vọng status chung.

### 8.2. Thử thứ tự chain với cấu hình sai có chủ đích

Ví dụ **chỉ minh họa lỗi**, không đưa vào cấu hình chạy ở mục 4:

~~~java
@Bean
@Order(1)
SecurityFilterChain broad(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().permitAll())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Chain đầu không đặt securityMatcher nên match **mọi URL**, bao gồm **/api/**. Request đến API đi qua broad chain với **permitAll**, không bao giờ được bảo vệ bởi api chain thứ hai. Test phải phát hiện bằng cách khẳng định **chain đầu tiên** khớp request API là api chain và request không có credential bị từ chối.

Có thể dùng một test matcher giống **firstMatchingChain("/api/me")** ở phần 5 để phát hiện lỗi này ngay khi khởi động, trước khi tích hợp frontend.

### 8.3. Kiểm tra route không được bao phủ

Nếu cấu hình chỉ có chain **securityMatcher("/api/**")** và **securityMatcher("/web/**")** nhưng không có chain fallback, request **/health-private** có thể **không đi qua Spring Security**. Đó không phải “403 ngầm định”; các filter xác thực/phân quyền của Spring Security sẽ không chạy cho request đó.

Test phải xác minh **mọi route cần bảo vệ** có ít nhất một chain khớp và route không mong muốn bị chặn bởi fallback. Đặc biệt, bao phủ **/login**, **/logout**, **/error**, actuator, nội bộ, websocket handshake, endpoint newly deployed, và thứ tự match cho URL tương tự nhau.

Không nên chỉ kiểm tra response của route chưa tồn tại. Một 404 từ MVC không chứng minh Spring Security đã thực sự bảo vệ đường dẫn ấy. Kiểm tra **SecurityFilterChain.matches(...)** hoặc trace của FilterChainProxy khi cần.

### 8.4. Thử nguồn danh tính thất bại và account state

Provider có thể truy vấn database, LDAP, Key Vault hoặc IdP. Các bài test quan trọng:

- Source timeout/5xx → **fail closed**, không coi là credential hợp lệ; không tự fallback sang provider dùng logic yếu hơn.
- Password sai → **BadCredentialsException** hoặc nhánh lỗi phù hợp, không trả Authentication authenticated.
- Account locked/disabled → từ chối ngay, ngăn provider khác đăng nhập vòng theo chính sách.
- Quyền cập nhật hoặc bị thu hồi → Authorization dùng quyền tin cậy và độ mới phù hợp, không lấy role do request tự khai.
- API key đã revoke hoặc JWT hết hạn → request sau phải bị từ chối theo quy tắc loại credential.
- Hai directory có cùng username → xác định namespace, tenant, issuer hoặc loại token; không ghép principal/authority sai nguồn.

Mock nguồn danh tính để gây timeout/invalid status; nhưng một bài test tích hợp khác nên kiểm chứng adapter với giao thức thật nếu hệ thống phụ thuộc vào kết nối remote.

### 8.5. Không để test giả lập người dùng che lỗ hổng

~~~java
// Chỉ hữu ích khi test authorization cho một principal giả:
mvc.perform(get("/api/admin").with(
        org.springframework.security.test.web.servlet.request
            .SecurityMockMvcRequestPostProcessors
            .user("admin").roles("ADMIN")));
~~~

Đoạn trên không chứng minh mật khẩu, token, key hay chữ ký đã được xác minh. **with(user(...))** tạo người dùng giả phục vụ test authorization. **@WithMockUser** cũng tương tự: rất hữu ích cho method security và kiểm tra quyền, nhưng không thay cho request chứng minh credential thật.

Muốn test login, hãy gửi **httpBasic("alice", "password")**, **formLogin()**, bearer token thật trong test với decoder/cấu hình hợp lệ, hoặc API key qua custom filter; sau đó xác minh principal, status, authorities và session/token.

## 9. Chạy test trong CI và quan sát lỗi

### 9.1. Tổ chức bài test

Một cấu trúc test dễ bảo trì:

~~~text
src/test/java/com/example/authpaths/
  AuthPathsIntegrationTest.java
  ProviderManagerFallbackTest.java
~~~

Trong dự án lớn hơn, tách thêm test:

- **AuthProviderTest**: chính sách xác minh bằng chứng, account state và provider fallback.
- **FilterChainRoutingTest**: thứ tự chain, RequestMatcher, loại filter.
- **LoginFlowIntegrationTest**: Basic, form, JSON, token, logout, CSRF, session.
- **AuthorizationMatrixTest**: vai trò/quyền/scope và route.
- **IdentityServiceFailureTest**: timeout, revoke, source unavailable.
- **GatewayE2ETest**: HTTPS, forwarding headers, cookie flags và lỗi gateway.

Khi test tích hợp dùng database hoặc IdP giả lập, mỗi bài phải tự thiết lập dữ liệu và dọn trạng thái để không lệ thuộc thứ tự chạy. Tránh dùng chung một session cookie giữa các test độc lập. Nếu muốn kiểm tra luồng liên tục (login → resource → logout), cố ý dùng **cùng session** trong **một test** và assert từng bước.

### 9.2. Lệnh kiểm thử

~~~bash
./mvnw test
./mvnw -Dtest=AuthPathsIntegrationTest test
./mvnw -Dtest=ProviderManagerFallbackTest test
~~~

Với Windows PowerShell:

~~~powershell
.\mvnw.cmd test
.\mvnw.cmd '-Dtest=AuthPathsIntegrationTest' test
.\mvnw.cmd '-Dtest=ProviderManagerFallbackTest' test
~~~

Lưu ý: đây là **lệnh chạy cho dự án mẫu khi đã tạo đúng source files và dependencies**, không phải stdout đã được xác minh trong môi trường này. Trong CI, lệnh không thành công phải khiến pipeline fail; không đánh dấu xanh vì một test bị bỏ qua hoặc context không load đúng.

### 9.3. Trace khi test fail

Trên môi trường phát triển hoặc trong test tạm thời, có thể bật:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Khi cần sâu hơn, có thể dùng TRACE trong phạm vi được kiểm soát. Quan sát chain nào match request và filter nào tham gia, sau đó đặt breakpoint tại **FilterChainProxy**, **BasicAuthenticationFilter / UsernamePasswordAuthenticationFilter**, **ProviderManager**, provider tùy chỉnh và handler 401/403. Không log plaintext password, API key, Bearer token, session ID hoặc Authorization header. Tránh tải log chứa bí mật lên hệ thống ticket công khai.

### 9.4. Checklist nghiệm thu

- [ ] Mọi mechanism đã hỗ trợ đều có test credential **đúng, sai, thiếu và thu hồi/hết hạn** nếu loại credential có các trạng thái này.
- [ ] API không có credential được **401** đúng entry point; không redirect form HTML bất ngờ.
- [ ] Web chưa đăng nhập được điều hướng tới form; login sai không tạo principal; login đúng duy trì context.
- [ ] POST login/logout có kiểm tra **CSRF** khi dùng session cookie.
- [ ] User không có role/scope bị **403** dù credential đúng; quyền không đọc từ body/header do client tự khai.
- [ ] **FilterChainProxy** chọn chain đầu tiên đúng; không có chain rộng hơn che chain đặc thù.
- [ ] URL không thuộc các chain trước bị catch-all từ chối theo policy; không để route nhạy cảm ngoài Spring Security.
- [ ] **ProviderManager** thử provider theo token và exception; BadCredentialsException không vô tình được provider yếu hơn ghi đè.
- [ ] AccountStatusException khóa các đường fallback không được phép.
- [ ] Parent AuthenticationManager không đưa ra đường bypass ngoài dự kiến.
- [ ] Source lỗi/timeout dẫn đến **fail closed** và có monitoring thích hợp.
- [ ] Test login thực qua filter, không chỉ dùng **@WithMockUser**.
- [ ] Log, message và HTTP response không tiết lộ credentials, stack trace hoặc cấu hình nội bộ.
- [ ] Các test tối thiểu chạy trong CI sau thay đổi matcher, thêm provider, đổi route hoặc nâng phiên bản Spring Security.

## 10. Những nhầm lẫn thường gặp

**“Có hai SecurityFilterChain thì chain thứ hai là dự phòng nếu đăng nhập ở chain đầu thất bại.”** Sai. Chain được chọn theo request đầu tiên khớp, không quay sang chain khác khi lỗi xác thực.

**“Có hai AuthenticationProvider thì chắc chắn chúng kiểm tra hai đường login khác nhau.”** Sai. Hai provider có thể cùng hỗ trợ một loại Authentication; filter ở đường HTTP tạo token mới quyết định provider nào có thể được thử.

**“Thêm provider nhận API key là đủ để X-API-Key tự hoạt động.”** Sai. Cần filter chuyển bằng chứng từ request thành token và gọi manager, sau đó đưa kết quả vào SecurityContext đúng cách.

**“MockMvc trả 200 nên bảo mật đã đúng.”** Chưa chắc. Với **with(user(...))** có thể bỏ qua xác minh credential thật, hoặc một chain **permitAll** sai vẫn trả 200. Cần test cơ chế thật và match chain.

**“Chỉ test 404 cho URL lạ là đã có fallback.”** Sai. 404 của MVC có thể xảy ra cả khi request không qua Spring Security. Phải kiểm tra chain và chính sách từ chối.

**“Thấy Basic 401 nghĩa là mọi request đều vào API chain.”** Không. Cần xem matchers, filter thực sự và status/headers tương ứng với từng path.

**“Provider đầu ném BadCredentialsException thì provider sau không bao giờ chạy.”** Sai với ProviderManager điển hình; một provider sau có thể xác thực thành công. Phải test hành vi fallback và lựa chọn chính sách rõ.

**“API stateless thì mọi kiểm thử CSRF đều vô nghĩa.”** Sai khi có cookie hoặc cơ chế browser tự gửi credential. CSRF phải được đánh giá theo **credential transport**, phương pháp gọi và trust model; không suy từ tên chain.

## 11. Tài liệu gốc để tự đối chiếu

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): AuthenticationManager, ProviderManager, parent manager và các provider.
- [Spring Security 6.5 — ProviderManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html): thứ tự provider, trường hợp BadCredentialsException, AccountStatusException và xóa credential.
- [Spring Security 6.5 — Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): nhiều SecurityFilterChain, @Order và securityMatcher/requestMatchers.
- [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): FilterChainProxy chỉ chạy chain đầu tiên khớp.
- [Spring Security 6.5 — Testing HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html): httpBasic request processor.
- [Spring Security 6.5 — Testing Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html): formLogin processor kèm CSRF.
- [Spring Security 6.5 — Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html): csrf(), token sai và test POST.
- [Spring Security 6.5 — Handling Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): xử lý logout, session và CSRF.
