# Giới hạn của gắn sẵn SecurityContext khi cần chứng minh trạng thái đã được lưu

## 1. Một request được xác thực chưa chứng minh session đã lưu đăng nhập

Trong chương **Phiên và đăng xuất** của module **SPRING_SECURITY_TESTING**, các tiện ích như **@WithMockUser**, **user()**, **authentication()** và **securityContext()** giúp tạo danh tính đã xác thực để kiểm tra quy tắc phân quyền. Chúng rất hữu ích khi câu hỏi là “người dùng có role này được phép gọi endpoint không?”.

Nhưng nếu câu hỏi là “người dùng đăng nhập một lần, rồi request tiếp theo có khôi phục được Authentication từ session không?”, các tiện ích gắn sẵn SecurityContext có thể làm test đạt dù ứng dụng chưa lưu trạng thái đăng nhập. Chúng chuẩn bị Authentication cho phạm vi test hoặc request, bỏ qua một phần hoặc toàn bộ luồng xác thực bằng credentials.

Bài này giúp phân biệt hai mục tiêu kiểm thử:

- **Authorization test:** chuẩn bị principal/authority và xác minh endpoint cho phép hay từ chối.
- **Persistence test:** xác thực qua luồng thực của ứng dụng, kiểm tra SecurityContext được lưu bằng repository, rồi gửi request độc lập sử dụng cùng session để khôi phục Authentication.

Sau bài học, bạn có thể chọn đúng công cụ, tránh false positive và viết test chứng minh vòng đời đăng nhập qua nhiều request bằng MockMvc.

## 2. Những cách gắn sẵn SecurityContext thường gặp

Spring Security Test cung cấp nhiều cách tạo danh tính cho test. Chúng có mục đích tương tự nhưng điểm đặt Authentication khác nhau.

| Tiện ích | Cách hoạt động trong test | Phù hợp để chứng minh |
| --- | --- | --- |
| **@WithMockUser** | Tạo Authentication giả lập trong SecurityContext của test | Quy tắc authorization với username/role/authority đã biết |
| **@WithUserDetails** | Nạp UserDetails từ UserDetailsService rồi tạo Authentication cho test | Quy tắc authorization với dữ liệu user từ UserDetailsService |
| **@WithSecurityContext** | Dùng factory tùy chỉnh để dựng SecurityContext cho test | Principal hoặc Authentication đặc thù |
| **user("alice")** | Gắn user giả lập vào một request MockMvc | Authorization trên request cụ thể |
| **authentication(auth)** | Gắn Authentication được tạo sẵn vào request | Authorization với Authentication tùy chỉnh |
| **securityContext(context)** | Gắn SecurityContext được tạo sẵn vào request | Authorization với context tùy chỉnh |

Các tiện ích này giúp kiểm thử phần xử lý request sau khi đã có Authentication. Chúng **không tự chứng minh** form login, HTTP Basic, OAuth2 login hay authentication filter đã xác minh credentials và lưu context vào HttpSession.

### 2.1. @WithMockUser

Ví dụ kiểm tra người dùng USER được đọc profile:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ProfileAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void userRoleCanReadProfile() throws Exception {
        mockMvc.perform(get("/profile"))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }
}
~~~

Test này trả lời câu hỏi: **nếu SecurityContext của request có một người dùng alice với ROLE_USER, endpoint /profile có xử lý đúng không?** Nó không gửi POST /login, không kiểm tra mật khẩu và không chứng minh Authentication được ghi vào session.

### 2.2. user() và authentication()

Có thể tạo danh tính riêng cho một request:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;

mockMvc.perform(get("/profile")
        .with(user("alice").roles("USER")))
    .andExpect(status().isOk())
    .andExpect(content().string("alice"));
~~~

Hoặc tạo Authentication cụ thể:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;

Authentication authentication =
        UsernamePasswordAuthenticationToken.authenticated(
            "alice",
            "N/A",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );

mockMvc.perform(get("/profile").with(authentication(authentication)))
        .andExpect(status().isOk());
~~~

Các request post-processor này rất tiện để thử nhiều role hoặc principal khác nhau. Tuy nhiên, danh tính được chuẩn bị trực tiếp cho request test; không có bước xác minh username/password qua AuthenticationManager như form login thực.

### 2.3. securityContext()

Khi cần kiểm tra principal hoặc Authentication đặc thù, có thể dựng SecurityContext:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.securityContext;

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);

mockMvc.perform(get("/profile").with(securityContext(context)))
        .andExpect(status().isOk());
~~~

Cách này cũng đặt sẵn context để xử lý request. Nó không phải bằng chứng rằng ứng dụng đã gọi SecurityContextRepository.saveContext() sau đăng nhập.

### 2.4. @WithUserDetails cũng không phải kiểm thử mật khẩu

**@WithUserDetails** lấy UserDetails từ UserDetailsService thật của application context. Vì thế, nó hữu ích khi muốn dùng thông tin user đã lưu trong hệ thống. Tuy nhiên, test vẫn chuẩn bị Authentication cho test; nó không tự gửi credentials qua form login filter và không xác minh mật khẩu mà người dùng nhập.

Tương tự, factory của **@WithSecurityContext** có thể dựng Authentication rất sát mô hình production, nhưng bản thân factory vẫn là cơ chế thiết lập context cho test. Muốn chứng minh quá trình xác thực và lưu phiên, hãy thực hiện request đăng nhập theo giao thức của ứng dụng.

## 3. Vì sao test gắn sẵn context có thể tạo false positive?

Giả sử ứng dụng có endpoint /profile yêu cầu authenticated(). Một test dùng @WithMockUser có thể trả 200 ngay cả khi:

- Form login đang cấu hình sai hoặc AuthenticationProvider từ chối credentials.
- Filter xử lý POST /login không được đưa vào MockMvc.
- Code đăng nhập tùy chỉnh chỉ đặt SecurityContextHolder nhưng không lưu SecurityContextRepository.
- SessionCreationPolicy.STATELESS đang được bật trong khi test lại kỳ vọng đăng nhập qua session.
- Request tiếp theo không thực sự sử dụng session từ request đăng nhập.

Test vẫn thành công vì Authentication đã được chuẩn bị sẵn trước khi endpoint xử lý request. Nó chứng minh quy tắc authorization với danh tính đó, không chứng minh luồng lưu và nạp trạng thái.

~~~mermaid
flowchart TD
    A["Mục tiêu kiểm thử"] --> B{"Cần chứng minh điều gì?"}
    B -->|"Endpoint cho phép role?"| C["@WithMockUser / user() / authentication()"]
    C --> D["Kiểm tra authorization"]
    B -->|"Login được lưu qua request?"| E["POST /login bằng credentials"]
    E --> F["SecurityFilterChain xác thực"]
    F --> G["SecurityContextRepository lưu context"]
    G --> H["Lấy session sau login"]
    H --> I["Request mới dùng cùng session"]
    I --> J["Xác minh Authentication được khôi phục"]
~~~

**Quy tắc lựa chọn:** nếu chỉ cần kiểm tra endpoint với một Authentication đã biết, dùng tiện ích mock. Nếu cần chứng minh trạng thái được lưu và khôi phục, phải có ít nhất hai request độc lập nối với nhau bằng cơ chế lưu trạng thái thực tế.

## 4. SecurityContextHolder không đồng nghĩa SecurityContextRepository

Trong ứng dụng Servlet, ba thành phần thường bị nhầm lẫn:

| Thành phần | Vai trò |
| --- | --- |
| **SecurityContext** | Chứa Authentication |
| **SecurityContextHolder** | Cung cấp SecurityContext cho phần xử lý hiện tại, thường gắn với thread |
| **SecurityContextRepository** | Tải và lưu SecurityContext giữa các request theo cơ chế cấu hình |

Với Spring Security 6, **SecurityContextHolderFilter** nạp context từ SecurityContextRepository nhưng theo mặc định không tự lưu context chỉ vì code đã thay đổi SecurityContextHolder. Luồng xác thực tích hợp như form login đã xử lý việc lưu context theo cấu hình. Với code xác thực tùy chỉnh, cần lưu tường minh bằng repository.

Ví dụ logic xác thực tùy chỉnh:

~~~java
Authentication authenticated =
        authenticationManager.authenticate(
            new UsernamePasswordAuthenticationToken(username, password)
        );

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);

// Phải lưu context để request tiếp theo có thể khôi phục.
// request/response là HttpServletRequest/HttpServletResponse hiện tại.
securityContextRepository.saveContext(context, request, response);
~~~

Nếu chỉ gọi setContext() mà không lưu, request hiện tại có thể thấy Authentication nhưng request sau không có session context để khôi phục. Đây là một lý do quan trọng khiến test một request với Authentication dựng sẵn không thể thay thế test persistence.

Với cấu hình Servlet mặc định có session, DelegatingSecurityContextRepository thường phối hợp RequestAttributeSecurityContextRepository và HttpSessionSecurityContextRepository. Repository request-attribute phục vụ các dispatch trong cùng request; repository session giữ context giữa các HTTP request. Cấu hình stateless hoặc repository tùy chỉnh có thể thay đổi hành vi này.

## 5. Viết authorization test riêng

Giả sử cấu hình bảo mật có:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/profile").hasRole("USER")
    .requestMatchers("/admin").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

Có thể kiểm tra quyền với các danh tính giả lập:

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void userCanReadProfile() throws Exception {
    mockMvc.perform(get("/profile"))
            .andExpect(status().isOk());
}

@Test
@WithMockUser(username = "alice", roles = "USER")
void userCannotReadAdmin() throws Exception {
    mockMvc.perform(get("/admin"))
            .andExpect(status().isForbidden());
}

@Test
void anonymousCannotReadProfile() throws Exception {
    mockMvc.perform(get("/profile"))
            .andExpect(status().is3xxRedirection());
}
~~~

Đây là các test gọn cho authorization. Chúng nên được giữ độc lập với bài kiểm thử session persistence để mỗi test có một mục tiêu rõ ràng. Đối với API có HTTP Basic hoặc bearer token, status của anonymous có thể là 401 thay vì redirect.

## 6. Viết persistence test bằng login thật và cùng session

Đây là phép kiểm thử cần có khi muốn chứng minh SecurityContext được lưu qua HTTP session. Ví dụ dùng Spring Boot 3.x, Spring Security 6.x, form login và MockMvc.

### 6.1. Cấu hình và endpoint

~~~java
@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/profile").authenticated()
                .anyRequest().permitAll()
            )
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            );
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("secret"))
                .roles("USER")
                .build()
        );
    }
}
~~~

~~~java
@RestController
class ProfileController {

    @GetMapping("/profile")
    String profile(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

### 6.2. Login rồi gọi request độc lập

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityContextPersistenceTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void loginSavesContextAndNextRequestRestoresIt() throws Exception {
        // Request 1: gửi credentials qua filter login thật.
        MvcResult login = mockMvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "secret"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        // Lấy session sau login vì session fixation protection có thể đổi ID.
        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        Object saved = session.getAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
        assertThat(saved).isInstanceOf(SecurityContext.class);
        assertThat(((SecurityContext) saved).getAuthentication().getName())
                .isEqualTo("alice");

        // Request 2: không gắn user(), authentication() hay @WithMockUser.
        // Chỉ gửi cùng session để repository tải lại context đã lưu.
        mockMvc.perform(get("/profile").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));

        // Request 3: một request độc lập nữa vẫn dùng cùng session.
        mockMvc.perform(get("/profile").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }
}
~~~

Bằng chứng ở đây gồm:

1. POST /login thực sự đi qua SecurityFilterChain với username/password.
2. Request đăng nhập trả về session hiện hành.
3. Session có SecurityContext đã lưu theo repository mặc định.
4. Request GET tiếp theo chỉ sử dụng session đó, không gắn Authentication giả lập.
5. Endpoint khôi phục được principal alice ở request độc lập.

Assertion đọc thuộc tính session dùng key của HttpSessionSecurityContextRepository nên phụ thuộc implementation lưu session mặc định. Nếu ứng dụng dùng repository tùy chỉnh, hãy kiểm tra bằng hành vi request tiếp theo và API của repository thay vì cố định vào tên thuộc tính này.

### 6.3. Negative test: không truyền session thì không được kế thừa đăng nhập

~~~java
@Test
void separateRequestWithoutSessionIsNotAuthenticated() throws Exception {
    mockMvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "secret"))
            .andExpect(status().is3xxRedirection());

    // MockMvc không tự giữ cookie/session giữa hai lần perform.
    mockMvc.perform(get("/profile"))
            .andExpect(status().is3xxRedirection());
}
~~~

Request thứ hai không có session nên không thể khôi phục Authentication từ lần login trước. Nếu request vẫn trả 200, hãy kiểm tra xem test có vô tình gắn @WithMockUser, user() hoặc filter chain đã bị tắt hay không.

## 7. Một ví dụ false positive cần tránh

Đoạn sau trông có vẻ kiểm tra hai request, nhưng thực tế mỗi request đều được gắn sẵn danh tính:

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void misleadingTestForSessionPersistence() throws Exception {
    mockMvc.perform(get("/profile"))
            .andExpect(status().isOk());

    mockMvc.perform(get("/profile"))
            .andExpect(status().isOk());
}
~~~

Test này không gửi login credentials, không lấy session từ request login và không chứng minh repository đã lưu context. Cả hai request thành công vì test đã chuẩn bị danh tính cho phạm vi test.

Một false positive khác là tự tạo session rồi ghi SecurityContext vào đó:

~~~java
MockHttpSession session = new MockHttpSession();
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
session.setAttribute(
    HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY,
    context
);

mockMvc.perform(get("/profile").session(session))
        .andExpect(status().isOk());
~~~

Đoạn trên có thể kiểm tra ứng dụng đọc SecurityContext đã có trong session, nhưng **không chứng minh ứng dụng tự lưu context sau khi người dùng đăng nhập**. Test persistence phải để chính luồng login của ứng dụng tạo trạng thái cần kiểm tra.

## 8. WebFlux và WebTestClient cũng có cùng ranh giới

Với Spring WebFlux, các tiện ích như **mockUser()** và **mockAuthentication()** của spring-security-test giúp kiểm tra authorization trong Reactive chain. Chúng vẫn là cách gắn sẵn Authentication cho test; không chứng minh SecurityContext được lưu vào WebSession.

Nếu cần kiểm chứng persistence Reactive, hãy:

1. Gửi request đăng nhập qua cơ chế authentication thực tế của ứng dụng.
2. Lấy cookie định danh WebSession từ response.
3. Gửi request mới qua WebTestClient với cùng cookie.
4. Xác minh principal được khôi phục từ WebSessionServerSecurityContextRepository.
5. Gửi request độc lập không có cookie để xác minh không tự kế thừa Authentication.

Tên cookie WebSession phụ thuộc WebSessionIdResolver và cấu hình ứng dụng. Không mặc định mọi ứng dụng đều dùng cùng một tên cookie. Với API Reactive stateless sử dụng bearer token, mỗi request phải gửi token; không dùng WebSession để chứng minh persistence.

## 9. Checklist chọn đúng loại test

| Câu hỏi cần trả lời | Công cụ nên dùng | Điều không thể kết luận chỉ từ test đó |
| --- | --- | --- |
| User có ROLE_USER được gọi endpoint không? | @WithMockUser hoặc user() | Credentials có được xác minh hay session có được lưu không |
| Authentication tùy chỉnh có đủ authority không? | authentication() hoặc securityContext() | Authentication có được tạo bởi filter production không |
| UserDetailsService có cung cấp dữ liệu user mong đợi không? | @WithUserDetails | Mật khẩu request có được kiểm tra qua login filter không |
| Login có lưu SecurityContext vào session không? | POST /login + lấy session + kiểm tra request kế tiếp | Cookie/browser/container thực tế hoạt động thế nào |
| Logout có làm request tiếp theo bị từ chối không? | Login thật + POST /logout + request mới | JWT stateless đã bị thu hồi hay chưa |
| API stateless yêu cầu token mỗi request không? | jwt() cho authorization; token/decoder test riêng cho xác minh token thật | jwt() mock không kiểm tra chữ ký token |
| Reactive context có được giữ qua WebSession không? | Login thật + WebTestClient + cùng session cookie | mockUser() không chứng minh WebSession persistence |

## 10. Bài tập thực hành

1. Viết một test @WithMockUser cho endpoint /profile và giải thích test đang xác minh authorization ở bước nào.
2. Thay @WithMockUser bằng user("alice").roles("USER"), sau đó bằng authentication(auth). So sánh cách chuẩn bị principal.
3. Viết test POST /login với credentials sai. Xác minh request không tạo phiên đăng nhập có Authentication hợp lệ.
4. Viết test POST /login thành công, lấy MockHttpSession và gọi GET /profile ở một request độc lập. Không dùng bất kỳ request post-processor gắn user nào.
5. Bỏ .session(session) khỏi request thứ hai. Xác minh test không còn kế thừa trạng thái đăng nhập.
6. Thử code đăng nhập tùy chỉnh chỉ gọi SecurityContextHolder.setContext(). Sau đó bổ sung SecurityContextRepository.saveContext() và so sánh request tiếp theo.
7. Với WebFlux, so sánh mockUser() và kiểm thử login thật qua WebTestClient cùng WebSession cookie.

Một test gắn sẵn SecurityContext rất tốt để trả lời câu hỏi về quyền truy cập. Để chứng minh trạng thái đăng nhập đã được lưu, cần để ứng dụng thực hiện xác thực, lưu context qua repository và khôi phục context ở request tiếp theo. Phân biệt hai mục tiêu này giúp tránh test xanh giả khi session persistence hoặc luồng login thực tế đang bị lỗi.
