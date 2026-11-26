# Đăng nhập rồi truy cập tài nguyên bằng cùng phiên

## 1. Tình huống cần kiểm chứng

Trong chương **Phiên và đăng xuất** của module **SPRING_SECURITY_TESTING**, một hành vi quan trọng của ứng dụng Servlet là: **đăng nhập thành công một lần, rồi truy cập tài nguyên được bảo vệ ở request kế tiếp bằng cùng HTTP session**.

Ví dụ, ứng dụng quản lý tài khoản cho phép người dùng **alice** gửi thông tin đăng nhập tới `POST /login`. Sau khi xác thực thành công, trình duyệt truy cập `GET /api/profile` và nhận thông tin của alice. Người dùng không phải gửi lại mật khẩu trong request GET vì trạng thái đăng nhập đã được lưu ở session phía server.

Bài này hướng dẫn kiểm thử *toàn bộ hành trình* đó bằng **MockMvc** và **spring-security-test** trong ứng dụng **Spring MVC (Servlet)**. Đích kiểm thử gồm:

- Request chưa đăng nhập không đọc được tài nguyên được bảo vệ.
- Request đăng nhập hợp lệ tạo được trạng thái xác thực trong session.
- Request tiếp theo dùng **đúng session** nhận được dữ liệu của người dùng đã đăng nhập.
- Request không dùng session đó, hoặc dùng session của người khác, không thừa hưởng danh tính.
- Người dùng đã đăng nhập nhưng thiếu quyền vẫn bị từ chối.
- Đăng xuất hủy phiên đăng nhập; request mới cần xác thực lại.

Điều này khác với kiểm thử một controller chạy với `@WithMockUser`. **`@WithMockUser` cung cấp danh tính giả lập cho test**, còn bài này chứng minh rằng ứng dụng đã thực sự tiếp nhận credentials, lưu SecurityContext và khôi phục Authentication cho request mới.

## 2. Hành trình từ đăng nhập đến tài nguyên bảo vệ

Với form login và session của Spring Security, chuỗi sự kiện điển hình là:

1. Client gửi `POST /login` chứa username, password và CSRF token nếu CSRF đang bật.
2. Filter xác thực của Spring Security kiểm tra credentials. Nếu hợp lệ, một `Authentication` được đặt vào `SecurityContext`.
3. Thành phần xác thực lưu `SecurityContext` bằng `SecurityContextRepository` phù hợp. Với cấu hình có trạng thái, ngữ cảnh có thể được lưu trong `HttpSession`.
4. Client gửi request mới bằng cùng session; Spring Security tải lại ngữ cảnh trước khi xử lý authorization.
5. Endpoint được phép truy cập nếu Authentication hợp lệ và đáp ứng điều kiện phân quyền.

~~~mermaid
sequenceDiagram
    autonumber
    participant T as MockMvc test
    participant F as Spring Security
    participant S as MockHttpSession
    participant P as GET /api/profile
    T->>F: POST /login + username/password + CSRF
    F->>F: Xác thực alice
    F->>S: Lưu SecurityContext
    F-->>T: 3xx redirect
    T->>S: Lấy session từ request đăng nhập
    T->>F: GET /api/profile + .session(session)
    F->>S: Tải SecurityContext
    F->>P: Chuyển request đã xác thực
    P-->>T: 200 OK, body "alice"
~~~

**Dấu hiệu thành công không chỉ là response redirect khi đăng nhập.** Form login trả redirect cả khi đăng nhập thành công lẫn thất bại, nhưng đích redirect khác nhau. Test cần kiểm tra tiếp một request sử dụng session đã đăng nhập và xác minh danh tính trả về.

### Cùng session nghĩa là gì trong MockMvc?

Trình duyệt thật thường lưu cookie `JSESSIONID`, sau đó gửi lại để server xác định phiên. Trong MockMvc, ta có thể trực tiếp chuyển đối tượng **`MockHttpSession`** từ request đầu sang request sau bằng:

~~~java
MvcResult loginResult = mockMvc.perform(/* POST /login ... */)
        .andReturn();

MockHttpSession session =
        (MockHttpSession) loginResult.getRequest().getSession(false);

mockMvc.perform(get("/api/profile").session(session));
~~~

`getSession(false)` có nghĩa: lấy session đã tồn tại, **không tự tạo session mới** nếu chưa có. `.session(session)` gắn cùng đối tượng session vào request được mô phỏng. Hai lần gọi `mockMvc.perform(...)` độc lập sẽ **không tự động dùng chung session** như trình duyệt có quản lý cookie.

## 3. Thiết lập ứng dụng mẫu

Ví dụ minh họa dành cho **Spring Boot 3.x / Spring Security 6.x**, **JUnit 5** và ứng dụng **Servlet**. Cần các phụ thuộc tương ứng:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Nếu dùng Maven, thêm `org.springframework.security:spring-security-test` với scope `test`. Hãy dùng phiên bản do cơ chế quản lý phụ thuộc của Spring Boot chọn, trừ khi dự án có yêu cầu khác.

### 3.1. Cấu hình bảo mật

Ứng dụng mẫu có hai tài khoản: **alice** mang role `USER`, **manager** mang role `ADMIN`. Endpoint profile yêu cầu xác thực; endpoint quản trị yêu cầu role `ADMIN`.

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
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/profile").authenticated()
                .anyRequest().permitAll()
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
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("secret"))
                .roles("USER")
                .build(),
            User.withUsername("manager")
                .password(encoder.encode("admin-secret"))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

`formLogin(Customizer.withDefaults())` kích hoạt luồng xử lý form login mặc định, trong đó **`POST /login`** tiếp nhận hai tham số `username` và `password`. `logout(Customizer.withDefaults())` sử dụng luồng logout mặc định, thường là **`POST /logout`** khi CSRF được bật.

`SessionCreationPolicy.IF_REQUIRED` cho phép tạo session khi thành phần bảo mật cần. Trong ví dụ này, form login và repository mặc định có thể duy trì SecurityContext giữa các request. Session không đồng nghĩa với xác thực thành công: một request thất bại vẫn có thể tạo session cho mục đích khác, chẳng hạn CSRF token hoặc saved request.

Dữ liệu tài khoản minh họa chỉ phục vụ test. Ứng dụng thực tế cần nguồn người dùng và chính sách quản lý credentials phù hợp.

### 3.2. Hai tài nguyên cần bảo vệ

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AccountController {

    @GetMapping("/api/profile")
    String profile(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/api/admin")
    String admin() {
        return "admin-only";
    }
}
~~~

Một request chưa xác thực đến `/api/profile` hoặc `/api/admin` sẽ bị Spring Security chặn. Với form login mặc định, trường hợp chưa đăng nhập thường được **302 redirect** tới `/login`; người dùng đã xác thực nhưng thiếu `ROLE_ADMIN` thường nhận **403 Forbidden**.

## 4. Kiểm thử end-to-end: đăng nhập rồi truy cập bằng cùng session

Bộ test dưới đây dùng **`@SpringBootTest`** và **`@AutoConfigureMockMvc`** để nạp cấu hình bảo mật của ứng dụng, các filter và controller. Đặt test trong package được Spring Boot quét, hoặc cấu hình application context phù hợp.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
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
class LoginThenUseSessionTest {

    @Autowired
    MockMvc mockMvc;

    private MockHttpSession login(String username, String password)
            throws Exception {
        MvcResult result = mockMvc.perform(post("/login")
                    .with(csrf())
                    .param("username", username)
                    .param("password", password))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);

        assertThat(session).isNotNull();

        Object value = session.getAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
        assertThat(value).isInstanceOf(SecurityContext.class);

        SecurityContext context = (SecurityContext) value;
        assertThat(context.getAuthentication()).isNotNull();
        assertThat(context.getAuthentication().isAuthenticated()).isTrue();
        assertThat(context.getAuthentication().getName())
                .isEqualTo(username);

        return session;
    }

    @Test
    void loginThenReadProfileWithSameSession() throws Exception {
        MockHttpSession session = login("alice", "secret");

        mockMvc.perform(get("/api/profile").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));

        // Một request độc lập khác cũng dùng đúng phiên đó.
        mockMvc.perform(get("/api/profile").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void protectedResourceRequiresLogin() throws Exception {
        mockMvc.perform(get("/api/profile"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void loginDoesNotAuthenticateAnUnrelatedRequest() throws Exception {
        login("alice", "secret");

        // Không gắn session của lần login trước.
        mockMvc.perform(get("/api/profile"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void authenticatedUserWithoutAdminRoleIsForbidden() throws Exception {
        MockHttpSession session = login("alice", "secret");

        mockMvc.perform(get("/api/admin").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanUseProtectedResourceInOwnSession() throws Exception {
        MockHttpSession session = login("manager", "admin-secret");

        mockMvc.perform(get("/api/admin").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("admin-only"));
    }

    @Test
    void invalidPasswordDoesNotGrantAccess() throws Exception {
        MvcResult failedLogin = mockMvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "incorrect"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"))
                .andReturn();

        // Session vẫn có thể tồn tại vì CSRF; đó không phải bằng chứng login.
        MockHttpSession session = (MockHttpSession)
                failedLogin.getRequest().getSession(false);

        if (session != null) {
            mockMvc.perform(get("/api/profile").session(session))
                    .andExpect(status().is3xxRedirection());
        } else {
            mockMvc.perform(get("/api/profile"))
                    .andExpect(status().is3xxRedirection());
        }
    }

    @Test
    void logoutEndsTheAuthenticatedSession() throws Exception {
        MockHttpSession session = login("alice", "secret");

        mockMvc.perform(post("/logout")
                    .session(session)
                    .with(csrf()))
                .andExpect(status().is3xxRedirection());

        assertThat(session.isInvalid()).isTrue();

        // Request mới sau logout không có phiên đăng nhập cũ.
        mockMvc.perform(get("/api/profile"))
                .andExpect(status().is3xxRedirection());
    }
}
~~~

**Lưu ý về redirect:** với form login mặc định, request chưa xác thực thường được chuyển đến trang đăng nhập. Đoạn test trên kiểm tra response 3xx để không phụ thuộc cách ứng dụng biểu diễn URL chuyển hướng. Nếu cần kiểm tra chính xác đích đến, hãy khẳng định giá trị Location theo cấu hình thực tế.

### 4.1. Điều gì chứng minh đã đăng nhập thành công?

Helper `login(...)` kiểm tra hai lớp tín hiệu:

1. Response từ form login là redirect, đúng hành vi phổ biến sau xác thực.
2. **Session chứa `SecurityContext` với Authentication đã xác thực và username đúng**.

Bởi vì redirect có thể xảy ra cả khi mật khẩu sai, assertion thứ hai giúp phân biệt kết quả. Sau đó, test chính tiếp tục gọi endpoint bằng cùng session để kiểm tra hành vi từ phía người dùng.

Trong cấu hình mặc định dựa trên `HttpSessionSecurityContextRepository`, key `SPRING_SECURITY_CONTEXT_KEY` cho phép kiểm tra trực tiếp dữ liệu đã lưu. Nếu ứng dụng dùng repository tùy biến, key hoặc cách lưu có thể khác; lúc đó cần ưu tiên khẳng định hành vi request sau thay vì gắn test vào chi tiết lưu trữ.

### 4.2. Vì sao phải gọi `getSession(false)`?

Nếu gọi `getSession()` không có tham số, Servlet API có thể tạo session mới khi chưa có. Một test như vậy dễ ngộ nhận rằng đăng nhập đã lưu trạng thái, trong khi session vừa được tạo chỉ vì thao tác đọc. `getSession(false)` không tạo session mới, nên thích hợp khi kiểm chứng luồng đăng nhập có trạng thái.

Hãy lấy session **sau** khi xử lý login. Spring Security có thể thay đổi session ID để giảm rủi ro session fixation. Không nên giữ một session ID trước đăng nhập rồi giả định ID đó không đổi trong mọi cấu hình.

### 4.3. `.session(session)` kiểm chứng điều gì?

Đoạn:

~~~java
MockHttpSession session = login("alice", "secret");

mockMvc.perform(get("/api/profile").session(session))
        .andExpect(status().isOk())
        .andExpect(content().string("alice"));
~~~

kiểm chứng rằng request mới có thể sử dụng lại danh tính đã được lưu trong session. Ngược lại:

~~~java
login("alice", "secret");

mockMvc.perform(get("/api/profile"))
        .andExpect(status().is3xxRedirection());
~~~

cho thấy hai lời gọi `perform` không tự chia sẻ phiên đăng nhập. Bài kiểm thử với session **thật do login tạo ra** có giá trị khác với việc dựng `MockHttpSession` rồi tự điền thuộc tính tùy ý.

## 5. Thêm yêu cầu phân quyền sau khi đã đăng nhập

Đăng nhập thành công chưa có nghĩa người dùng được truy cập mọi tài nguyên. Trong cấu hình mẫu:

- `/api/profile` yêu cầu **authenticated()**, nên alice và manager đều có thể đọc hồ sơ của chính request.
- `/api/admin` yêu cầu **hasRole("ADMIN")**, được Spring Security đối chiếu với authority **ROLE_ADMIN**.

Vì alice chỉ có `ROLE_USER`, request đến `/api/admin` dù gửi đúng session của alice vẫn bị trả **403 Forbidden**. Đây là **lỗi phân quyền**, không phải lỗi session. Nếu dùng session manager, tài nguyên này trả **200 OK**.

### Ma trận kiểm thử

| Tình huống | Trạng thái trong request | Kết quả mong đợi ở ví dụ |
| --- | --- | --- |
| GET /api/profile trước đăng nhập | Chưa xác thực | **302** về trang login |
| POST /login, alice/secret | Xác thực thành công, lưu vào session | Redirect; session có SecurityContext |
| GET /api/profile + session của alice | Đã xác thực với ROLE_USER | **200**, body `alice` |
| GET /api/profile không truyền session cũ | Chưa xác thực | **302** về trang login |
| GET /api/admin + session của alice | Đã xác thực, thiếu ROLE_ADMIN | **403** |
| GET /api/admin + session của manager | Đã xác thực, có ROLE_ADMIN | **200**, body `admin-only` |
| POST /login với mật khẩu sai | Xác thực thất bại | Redirect về `/login?error`; không thể vào profile |
| POST /logout + session và CSRF | Đăng xuất khỏi session hiện có | Redirect; session invalid |

Các mã trên gắn với **cấu hình mẫu sử dụng form login**. Ứng dụng dùng HTTP Basic, bearer token hoặc entry point tùy chỉnh có thể trả 401/403 hoặc response JSON. Không áp đặt một status chung cho mọi cấu hình Spring Security.

## 6. Những điểm dễ làm kiểm thử sai

### 6.1. POST bị 403 do thiếu CSRF

Spring Security mặc định bảo vệ CSRF cho các thao tác thay đổi trạng thái. Với form login và logout mẫu, test dùng:

~~~java
mockMvc.perform(post("/login")
        .with(csrf())
        .param("username", "alice")
        .param("password", "secret"));

mockMvc.perform(post("/logout")
        .session(session)
        .with(csrf()));
~~~

Nếu bỏ `.with(csrf())`, request có thể bị chặn **403** trước khi authentication filter xét username và password. Đừng suy ra mật khẩu sai chỉ từ lỗi này.

### 6.2. Bỏ qua filter khiến test trả 200 sai mục đích

`@AutoConfigureMockMvc` mặc định đăng ký filter của application context. Nếu tự cấu hình `@AutoConfigureMockMvc(addFilters = false)` hoặc tự dựng MockMvc mà bỏ SecurityFilterChain, controller có thể nhận request chưa được bảo vệ. Khi đó `200 OK` không chứng minh có phiên đăng nhập hợp lệ.

Với `MockMvcBuilders.webAppContextSetup(applicationContext)`, có thể dùng `.apply(springSecurity())` từ `SecurityMockMvcConfigurers` để tích hợp Spring Security trong setup thủ công.

### 6.3. `@WithMockUser` che mất bước đăng nhập

~~~java
@WithMockUser(username = "alice", roles = "USER")
@Test
void profileAcceptsMockIdentity() throws Exception {
    mockMvc.perform(get("/api/profile"))
            .andExpect(status().isOk());
}
~~~

Test này hữu ích khi chỉ cần kiểm tra authorization cho principal đã có. Nó **không** gửi credentials qua `POST /login`, cũng không chứng minh Authentication được lưu và tải lại bằng session. Khi mục tiêu là hành trình đăng nhập rồi truy cập, hãy sử dụng hai HTTP request riêng và cùng `MockHttpSession`.

### 6.4. Tạo session mới không đồng nghĩa đăng nhập

~~~java
MockHttpSession empty = new MockHttpSession();

mockMvc.perform(get("/api/profile").session(empty))
        .andExpect(status().is3xxRedirection());
~~~

Một phiên rỗng không có SecurityContext xác thực. Tương tự, một phiên có thuộc tính dữ liệu ứng dụng như `cartId` cũng chưa chứng minh đã đăng nhập. Test cần xác thực thông qua filter và kiểm tra request bảo vệ.

### 6.5. Không sử dụng phiên đã bị invalidate

Logout mặc định thường làm session hiện tại bị vô hiệu hóa. Sau khi kiểm tra `session.isInvalid()`, không nên tiếp tục dùng chính object bị invalid như một phiên hợp lệ. Để mô phỏng một người dùng truy cập lại sau logout, hãy phát request mới **không có session cũ** hoặc với một session mới chưa xác thực.

### 6.6. Không nhầm session-based với stateless

Với API cấu hình `SessionCreationPolicy.STATELESS` và repository không dùng session, mỗi request phải cung cấp cách xác thực riêng, ví dụ `Authorization: Bearer ...` hoặc HTTP Basic credentials. Khi đó request thứ hai không mang token/credentials không được kế thừa authentication của request trước.

**MockHttpSession** thuộc Spring Test cho stack **Servlet**. Với ứng dụng Spring WebFlux (Reactive), kiểm thử thường dùng **WebTestClient**, **WebSession** và các tiện ích bảo mật Reactive. Không sử dụng nguyên xi ví dụ MockMvc cho WebFlux.

## 7. Phạm vi kiểm thử và bài tập mở rộng

MockMvc xử lý request trong ứng dụng Servlet mà không mở một HTTP server thực. Việc truyền `MockHttpSession` giúp kiểm thử ngữ cảnh và quy tắc bảo mật trong ứng dụng, nhưng không kiểm chứng toàn bộ việc trình duyệt lưu cookie, các cờ `Secure`/`SameSite`, cân bằng tải, session store phân tán hay thời gian timeout ngoài thực tế. Những yêu cầu đó cần các bài kiểm thử tích hợp thông qua server và hạ tầng tương ứng.

Để luyện tập, hãy mở rộng ví dụ theo trình tự:

1. Chạy test `loginThenReadProfileWithSameSession`, sau đó bỏ `.session(session)` ở request GET; giải thích vì sao request thứ hai không còn thấy alice.
2. Thay mật khẩu đăng nhập bằng chuỗi sai, kiểm tra response `/login?error` và xác nhận phiên đó không truy cập được `/api/profile`.
3. Đăng nhập bằng hai tài khoản alice và manager, giữ hai session riêng. Gọi `/api/profile` với từng session để bảo đảm danh tính không bị trộn.
4. Giữ session của alice nhưng gọi `/api/admin`. So sánh **403 do thiếu quyền** với **302 do chưa đăng nhập**.
5. Chạy `POST /logout` kèm CSRF token; kiểm tra session invalid và thử request mới không có session cũ.
6. Chuyển ứng dụng sang chế độ stateless; dự đoán và kiểm tra sự thay đổi hành vi khi GET không mang credentials.

Một bài kiểm thử đáng tin cậy phải chứng minh được cả hai phần: **đăng nhập thực sự thành công** và **request sau truy cập tài nguyên được bảo vệ bằng đúng phiên đã đăng nhập**. Từ đó, các ca không có session, thiếu quyền và logout giúp bảo đảm ứng dụng từ chối truy cập đúng chính sách.
