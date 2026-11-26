# SecurityContextRepository và việc lưu ngữ cảnh giữa các request

## 1. Vì sao một request đăng nhập có thể ảnh hưởng request tiếp theo?

Trong chương **Phiên và đăng xuất** của module **SPRING_SECURITY_TESTING**, mục tiêu là kiểm chứng xác thực, phân quyền và cơ chế bảo vệ HTTP thực tế bằng **spring-security-test**. Với ứng dụng **Servlet**, người dùng thường đăng nhập một lần rồi gửi các request tiếp theo mà không nhập lại mật khẩu. Điều đó chỉ đúng khi ứng dụng có cơ chế **lưu và nạp lại SecurityContext** giữa các request, chẳng hạn thông qua HTTP session.

Bài học tập trung vào **SecurityContextRepository**, thành phần nối kết ngữ cảnh bảo mật của từng request với nơi lưu trữ của ứng dụng. Sau bài này, bạn sẽ biết cách:

- Phân biệt **SecurityContext**, **SecurityContextHolder** và **SecurityContextRepository**.
- Hiểu cách Spring Security nạp, lưu và xóa ngữ cảnh trong ứng dụng dùng session.
- Kiểm chứng bằng **MockMvc** rằng đăng nhập thành công ở request thứ nhất cho phép request thứ hai truy cập tài nguyên, khi **hai request sử dụng cùng session**.
- Kiểm thử không có session, session đã logout và các trường hợp cấu hình **stateless**.
- Nhận ra vì sao việc chỉ dùng **@WithMockUser** hoặc gán **SecurityContextHolder** chưa chứng minh cơ chế lưu ngữ cảnh đang hoạt động.

Ví dụ sử dụng **Spring Boot 3.x và Spring Security 6.x** (Servlet). Với phiên bản Spring Boot khác, vị trí import của annotation kiểm thử có thể thay đổi; cơ chế lưu ngữ cảnh đang giải thích ở đây gắn với cách hoạt động của Spring Security 6.

## 2. Ba thành phần cần phân biệt

**SecurityContext** chứa đối tượng **Authentication**, gồm danh tính, trạng thái xác thực và các quyền của principal. **SecurityContextHolder** cho mã xử lý request hiện tại truy cập SecurityContext; chiến lược mặc định trong ứng dụng Servlet truyền thống gắn với thread đang xử lý. **SecurityContextRepository** quyết định ngữ cảnh được tải từ đâu và lưu ở đâu để request khác có thể sử dụng.

| Thành phần | Trách nhiệm | Có tự lưu danh tính qua nhiều request không? |
| --- | --- | --- |
| **SecurityContext** | Chứa Authentication của ngữ cảnh hiện tại | Không; đây là đối tượng dữ liệu |
| **SecurityContextHolder** | Cung cấp ngữ cảnh cho luồng xử lý request hiện tại | Không; holder không phải nơi lưu session |
| **SecurityContextRepository** | Tải, lưu và kiểm tra sự tồn tại của ngữ cảnh | Có thể, phụ thuộc implementation |
| **HttpSession** | Lưu trạng thái phía server, được nhận diện qua session ID | Có, khi repository sử dụng session |
| **SecurityFilterChain** | Điều phối việc tải ngữ cảnh, xác thực, phân quyền, logout | Thực hiện những bước theo cấu hình |

Các phương thức quan trọng của **SecurityContextRepository** là **loadDeferredContext(request)**, **saveContext(context, request, response)** và **containsContext(request)**. Một số API cũ hoặc những tài liệu dành cho phiên bản trước có đề cập **loadContext(...)**; khi đọc mã Spring Security 6, cần chú ý mô hình nạp trì hoãn và yêu cầu lưu rõ ràng.

### Những implementation thường gặp

- **HttpSessionSecurityContextRepository**: lưu SecurityContext dưới một thuộc tính của **HttpSession**, thường là **SPRING_SECURITY_CONTEXT**. Khi request sau gửi cùng session ID và repository nạp lại ngữ cảnh, principal có thể tiếp tục được xác thực.
- **RequestAttributeSecurityContextRepository**: lưu trong thuộc tính của **chính request Servlet**. Hữu ích khi có nhiều dispatch như ERROR hoặc FORWARD của cùng một request; nó **không** giữ phiên đăng nhập giữa hai HTTP request riêng.
- **DelegatingSecurityContextRepository**: kết hợp nhiều repository; mặc định phổ biến ở Spring Security 6 là **RequestAttributeSecurityContextRepository** và **HttpSessionSecurityContextRepository**.
- **NullSecurityContextRepository**: không lưu ngữ cảnh để dùng cho request sau; thường phù hợp với hệ thống **stateless**, nơi mỗi request mang thông tin xác thực riêng.

**Quan trọng:** cookie **JSESSIONID** chỉ giúp client tham chiếu tới session phía server. Nó không tự chứa đối tượng Authentication hay mật khẩu của người dùng. Repository là nơi xử lý việc chuyển đổi giữa session và SecurityContext.

## 3. Vòng đời ngữ cảnh bảo mật trong ứng dụng Servlet

Ví dụ người dùng **alice** đăng nhập thành công bằng form login, sau đó gọi **GET /api/me**:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as SecurityFilterChain
    participant R as SecurityContextRepository
    participant S as HttpSession
    participant A as Authentication / Controller
    C->>F: POST /login (alice, password, CSRF)
    F->>A: Xác thực credentials
    A-->>F: Authentication hợp lệ
    F->>R: saveContext(context, request, response)
    R->>S: Lưu SPRING_SECURITY_CONTEXT
    F-->>C: Redirect + session cookie
    C->>F: GET /api/me (cùng session)
    F->>R: loadDeferredContext(request)
    R->>S: Đọc SecurityContext đã lưu
    S-->>R: Authentication của alice
    R-->>F: SecurityContext
    F->>A: Cho phép vào endpoint
    A-->>C: 200 OK, alice
~~~

Ở request sau, **SecurityContextHolderFilter** lấy ngữ cảnh qua repository rồi cung cấp cho SecurityContextHolder trong quá trình xử lý. Khi request kết thúc, filter dọn trạng thái gắn với request hiện tại; ngữ cảnh đã lưu trong repository mới là thứ có thể tồn tại để request tiếp theo sử dụng.

### Lưu rõ ràng trong Spring Security 6

Theo mô hình thông dụng của Spring Security 6, **SecurityContextHolderFilter** chịu trách nhiệm **nạp** SecurityContext nhưng **không tự lưu** ở cuối request. Code tự xác thực người dùng phải gọi **saveContext(...)** tại thời điểm phù hợp. Một số filter xác thực tích hợp, chẳng hạn xử lý form login, đã thực hiện việc lưu theo cơ chế của chúng.

Điều này khác với mô hình cũ dùng **SecurityContextPersistenceFilter**, vốn có thể tự lưu ngữ cảnh vào cuối request. Khi đọc ví dụ từ phiên bản khác, cần xét cấu hình **requireExplicitSave** và filter thực sự có trong chain, thay vì mặc định rằng gán SecurityContextHolder là đủ.

Không phải mọi SecurityContext đều được ghi thành session: ví dụ ngữ cảnh rỗng hoặc chỉ chứa xác thực anonymous thông thường không cần trở thành một phiên đăng nhập. Việc có tạo session mới cũng phụ thuộc **SessionCreationPolicy**, repository và cấu hình ứng dụng.

## 4. Cấu hình mẫu dùng form login và HTTP session

Ví dụ dưới đây mô tả ứng dụng Servlet có **POST /login**, **GET /api/me** và **POST /logout**. Form login sử dụng tên field mặc định **username** và **password**. Spring Security giữ trạng thái đăng nhập bằng session khi cần.

Các thư viện chính cần có là **spring-boot-starter-web**, **spring-boot-starter-security**, **spring-boot-starter-test** và **spring-security-test** (scope test). Với Spring Boot, nên dùng dependency management của dự án để quản lý phiên bản.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
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

Controller minh họa cho endpoint cần bảo vệ:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

**IF_REQUIRED** cho phép tạo HTTP session khi cần, nhưng không có nghĩa mọi request đều phải tạo session. Mặc định **formLogin** xử lý xác thực tại **POST /login** và **logout** xử lý **POST /logout**. Với CSRF protection đang bật, cả hai request POST trong ví dụ kiểm thử sẽ gửi CSRF token.

## 5. Kiểm thử sự tồn tại của ngữ cảnh qua hai request bằng MockMvc

Đây là phép kiểm thử trọng tâm: đăng nhập ở request đầu tiên, lấy **MockHttpSession**, sau đó truyền **chính session đó** vào request thứ hai.

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
class SecurityContextRepositoryTest {

    @Autowired
    MockMvc mockMvc;

    private MockHttpSession loginAsAlice() throws Exception {
        MvcResult login = mockMvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "secret"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();
        return session;
    }

    @Test
    void loginContextIsAvailableOnNextRequestWithSameSession()
            throws Exception {
        MockHttpSession session = loginAsAlice();

        assertThat(session.getAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY))
                .isInstanceOf(SecurityContext.class);

        mockMvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void aNewRequestWithoutTheSessionIsUnauthenticated()
            throws Exception {
        loginAsAlice();

        mockMvc.perform(get("/api/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutInvalidatesTheLoggedInSession() throws Exception {
        MockHttpSession session = loginAsAlice();

        mockMvc.perform(post("/logout")
                    .session(session)
                    .with(csrf()))
                .andExpect(status().is3xxRedirection());

        assertThat(session.isInvalid()).isTrue();
    }
}
~~~

Ba kiểm thử trên kiểm chứng ba điều khác nhau:

1. **Có cùng session**: SecurityContext đã được lưu và được nạp lại, nên endpoint trả **200 OK** với principal **alice**.
2. **Không truyền session**: request độc lập không có danh tính đã đăng nhập. Với **formLogin**, ứng dụng mẫu thường chuyển hướng đến trang đăng nhập (**3xx**), thay vì trả **401** như HTTP Basic.
3. **Logout**: logout mặc định vô hiệu hóa phiên đăng nhập hiện tại, xóa SecurityContext và chuyển hướng. **MockHttpSession.isInvalid()** cho phép kiểm tra session đã bị vô hiệu hóa.

Để chẩn đoán sâu hơn, phép kiểm tra **SPRING_SECURITY_CONTEXT_KEY** xác nhận SecurityContext có trong session phía server. Nếu hệ thống cố ý dùng repository khác, chẳng hạn Redis-backed session hoặc implementation tùy chỉnh, cần điều chỉnh khẳng định này theo hợp đồng của repository đó.

**Lưu ý về MockMvc:** việc gọi **mockMvc.perform(...)** hai lần không tự động tạo một trình duyệt giữ cookie/session. Cần truyền **.session(session)**, hoặc dùng cơ chế quản lý session tương ứng. Nếu dùng **@AutoConfigureMockMvc(addFilters = false)** hay tự tạo MockMvc mà không áp dụng Spring Security, kết quả không chứng minh cơ chế repository đang hoạt động.

## 6. Khi tự xác thực, cần lưu SecurityContext tường minh

Giả sử ứng dụng có cơ chế đăng nhập tùy chỉnh và đã xác thực được Authentication. Chỉ gọi **SecurityContextHolder.setContext(...)** sẽ giúp phần code trong request hiện tại thấy principal, nhưng không đủ để request sau lấy lại danh tính.

Mẫu xử lý cốt lõi trong ứng dụng Servlet dùng Spring Security 6:

~~~java
// authenticationManager và securityContextRepository được inject từ cấu hình.
// Repository phải tương thích với repository mà SecurityFilterChain dùng.

Authentication authentication = authenticationManager.authenticate(
    new UsernamePasswordAuthenticationToken(username, password)
);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

// req và res là HttpServletRequest / HttpServletResponse của request hiện tại.
securityContextRepository.saveContext(context, req, res);
~~~

Các kiểu được dùng ở đoạn trên:

~~~java
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.SecurityContextRepository;
~~~

Nếu muốn dùng một repository riêng trong security configuration, có thể đăng ký nó cho filter chain:

~~~java
SecurityContextRepository repository =
        new HttpSessionSecurityContextRepository();

http.securityContext(context -> context
        .securityContextRepository(repository));
~~~

Đoạn trên là phần cấu hình minh họa đặt **bên trong** phương thức tạo SecurityFilterChain, trước khi gọi **http.build()**. Repository dùng khi **saveContext** và repository dùng khi request sau **load** phải trỏ về cơ chế lưu trữ tương ứng; nếu sử dụng các instance hoặc cấu hình không tương thích, request sau có thể không nhận lại context.

Một số triển khai custom authentication cần xem xét cả session fixation protection, CSRF, exception handling và sự kiện đăng nhập. Với ứng dụng dùng form login chuẩn, hãy ưu tiên filter xác thực do Spring Security cung cấp vì chúng đã tích hợp các bước liên quan.

## 7. Stateful và stateless cho kết quả kiểm thử khác nhau

| Cấu hình | Repository điển hình | Request sau giữ đăng nhập bằng session? | Điều nên kiểm thử |
| --- | --- | --- | --- |
| Form login có session | Delegating/HttpSession | Có, khi lưu thành công và dùng cùng session | Login → GET cùng session → logout |
| HTTP Basic mỗi request gửi credentials | Phụ thuộc cấu hình | Không cần dựa vào session | Có header hợp lệ thì thành công; thiếu/sai header bị từ chối theo cấu hình |
| JWT/Bearer stateless | Null hoặc cơ chế không dùng session | Không | Mỗi request phải mang token hợp lệ |
| Chỉ lưu vào request attribute | RequestAttribute | Không, qua hai HTTP request khác nhau | Xử lý giữa các servlet dispatch trong một request |

Với endpoint API muốn xác thực độc lập trên từng request, ví dụ cấu hình không giữ SecurityContext trong session:

~~~java
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.context.NullSecurityContextRepository;

// Bên trong phương thức cấu hình HttpSecurity cho API stateless:
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .securityContext(context -> context
        .securityContextRepository(new NullSecurityContextRepository()));
~~~

**STATELESS** giúp Spring Security không dùng session để lấy SecurityContext. Nó không phải cam kết rằng mọi thành phần khác của ứng dụng đều không bao giờ tạo session. Vì vậy, khi kiểm thử tính stateless, hãy kiểm tra hành vi **mỗi request đều phải tự cung cấp danh tính**, và theo dõi session nếu đó là yêu cầu của hệ thống.

Nếu dùng HTTP Basic hoặc bearer token cho API, đừng kỳ vọng một request đã xác thực bằng header sẽ khiến request tiếp theo không có header trở nên hợp lệ. Kết quả cụ thể còn phụ thuộc toàn bộ cấu hình repository và filter chain.

## 8. Các lỗi thường gặp khi kiểm thử

| Dấu hiệu | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| Request thứ hai chuyển hướng về login | Không truyền cùng session; context chưa được lưu; repository không đọc session | Kiểm tra MockHttpSession, **saveContext**, repository và session policy |
| Request thứ hai trả 200 dù không có session | Test đang dùng **@WithMockUser**, **user(...)** hoặc filter chain không hoạt động | Bỏ danh tính mock, bật filter và thử request không có session |
| POST /login trả 403 | Thiếu CSRF token, hoặc có rule chặn request | Thêm **.with(csrf())** và kiểm tra security config |
| Login thành công nhưng session không có context | Chỉ thay đổi SecurityContextHolder; repository không lưu; cấu hình stateless | Xác định filter xác thực và lời gọi **saveContext** |
| Logout xong vẫn truy cập được endpoint | Request mới tiếp tục gửi credentials hợp lệ, hoặc còn cơ chế xác thực khác | Phân biệt vô hiệu hóa session với thu hồi HTTP Basic/JWT |
| Test lúc chạy riêng thì qua, chạy cùng suite thì sai | Trạng thái bảo mật hoặc session bị chia sẻ sai giữa các test | Cô lập MockHttpSession cho từng test, tránh dùng static context |

Hai điểm đặc biệt cần nhớ:

**@WithMockUser không đo lường tính bền vững của session.** Annotation này chuẩn bị Authentication giả lập để test phân quyền trong một ngữ cảnh kiểm thử. Tương tự, **.with(user("alice"))** có thể tạo ra một request trông như đã xác thực mà không đi qua bước đăng nhập và lưu context thực tế. Khi mục tiêu là kiểm chứng repository, hãy dùng request đăng nhập thật như ví dụ ở mục 5.

**Logout không giống thu hồi mọi credentials.** Logout của phiên đăng nhập dựa vào session có thể hủy session hiện hành; nhưng client còn cầm username/password hợp lệ vẫn có thể thực hiện một HTTP Basic request mới. Với JWT stateless, logout không mặc nhiên làm token đã cấp hết hiệu lực. Đó là các bài toán xác thực khác với việc xóa SecurityContext trong session.

## 9. Bài tập thực hành

1. Chạy ba test ở mục 5. Xem session có attribute **SPRING_SECURITY_CONTEXT** sau đăng nhập thành công không.
2. Xóa **.session(session)** ở request **GET /api/me** sau login; giải thích tại sao response chuyển từ **200** thành redirect về login.
3. Đổi mật khẩu đăng nhập thành một giá trị sai. Xác minh test không nhận được SecurityContext đã xác thực cho **alice**.
4. Thay repository bằng **NullSecurityContextRepository** và cấu hình **SessionCreationPolicy.STATELESS**. Quan sát vì sao form login không thể cung cấp cùng trạng thái qua request mới như trước.
5. Thử mô phỏng một controller đăng nhập tự viết, chỉ **setContext** mà không **saveContext**; sau đó thêm lời gọi **saveContext(...)** và so sánh kết quả request thứ hai.
6. Viết test riêng kiểm chứng rằng sau **POST /logout** có CSRF token, session hiện tại đã bị vô hiệu hóa và request mới không có credentials không thể đọc **/api/me**.

Một kiểm thử phiên đăng nhập đáng tin cậy phải cho thấy cả **thời điểm context được lưu** và **lúc request sau nạp lại context**. Kiểm thử truy cập endpoint chỉ bằng một Authentication đã được mock sẵn không thể thay thế phép kiểm chứng này.
