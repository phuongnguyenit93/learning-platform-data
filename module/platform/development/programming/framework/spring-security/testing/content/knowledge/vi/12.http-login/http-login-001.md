# `httpBasic` tạo header xác thực cho request MockMvc

Trong kiểm thử HTTP Basic với Spring Security, có hai việc khác nhau: cung cấp danh tính đã xác thực cho request và gửi thông tin đăng nhập để hệ thống tự xác thực. `httpBasic(username, password)` của `spring-security-test` hỗ trợ việc thứ hai. Nó thêm header `Authorization` vào request MockMvc theo định dạng HTTP Basic, giống cách một HTTP client gửi tên đăng nhập và mật khẩu.

Nhờ đó, người học có thể kiểm chứng cấu hình HTTP Basic, cơ chế xác thực và các quy tắc phân quyền trên chuỗi filter bảo mật thực tế của ứng dụng Servlet.

## 1. HTTP Basic biểu diễn thông tin đăng nhập như thế nào?

HTTP Basic gửi thông tin đăng nhập theo dạng:

```http
GET /api/profile HTTP/1.1
Authorization: Basic dXNlcjpwYXNzd29yZA==
```

Giá trị sau chữ `Basic` là Base64 của chuỗi `user:password`. Spring Security lấy header này, giải mã thông tin đăng nhập và chuyển yêu cầu xác thực cho cơ chế xác thực được cấu hình.

Base64 là cách mã hóa biểu diễn dữ liệu, không phải mã hóa bảo mật. Khi triển khai HTTP Basic trong thực tế, cần sử dụng HTTPS để bảo vệ thông tin đăng nhập trên đường truyền. Trong các ví dụ kiểm thử, chỉ dùng tài khoản và mật khẩu dành riêng cho test.

Nếu phải tự tạo header, có thể viết như sau với tên đăng nhập và mật khẩu ASCII:

```java
String credentials = "user:password";
String encoded = Base64.getEncoder()
    .encodeToString(credentials.getBytes(StandardCharsets.UTF_8));

mockMvc.perform(get("/api/profile")
    .header(HttpHeaders.AUTHORIZATION, "Basic " + encoded));
```

Cách viết này yêu cầu tự ghép chuỗi, tự mã hóa và tự đặt header. `httpBasic` giúp biểu đạt ý định kiểm thử rõ hơn:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;

mockMvc.perform(get("/api/profile")
    .with(httpBasic("user", "password")));
```

Hai đoạn trên gửi cùng header đối với bộ thông tin đăng nhập minh họa. `httpBasic` trả về một `RequestPostProcessor`, được áp dụng bằng `.with(...)` để bổ sung header vào request đang xây dựng. Nó không trả về một request hoàn chỉnh và không tự thực hiện xác thực tại thời điểm gọi hàm.

## 2. Điều gì xảy ra khi MockMvc thực hiện request?

```mermaid
sequenceDiagram
    participant T as Test
    participant M as MockMvc
    participant F as BasicAuthenticationFilter
    participant A as AuthenticationManager
    participant P as AuthorizationFilter
    participant C as Controller

    T->>M: perform(get(...).with(httpBasic(...)))
    M->>F: Authorization: Basic ...
    F->>A: Yêu cầu xác thực username/password
    alt Thông tin hợp lệ
        A-->>F: Authentication đã xác thực
        F->>P: Tiếp tục với SecurityContext
        alt Có quyền truy cập
            P->>C: Cho phép xử lý request
            C-->>T: HTTP 200
        else Thiếu quyền
            P-->>T: HTTP 403
        end
    else Thông tin không hợp lệ
        A-->>F: AuthenticationException
        F-->>T: HTTP 401
    end
```

Sơ đồ minh họa một cấu hình HTTP Basic tiêu chuẩn. Với một request mới chưa có danh tính, `BasicAuthenticationFilter` đọc thông tin đăng nhập từ header, tạo yêu cầu xác thực và chuyển cho `AuthenticationManager`. Khi dùng cơ chế xác thực tên đăng nhập và mật khẩu thông thường, một `AuthenticationProvider` như `DaoAuthenticationProvider` có thể tra cứu người dùng qua `UserDetailsService` và kiểm tra mật khẩu qua `PasswordEncoder`.

Sau khi xác thực thành công, danh tính được đưa vào `SecurityContext`. Quy tắc phân quyền HTTP tiếp tục quyết định request có được phép đến controller hay không. Nếu xác thực thất bại, Spring Security có thể gọi `AuthenticationEntryPoint` để trả về HTTP 401. Các handler tùy chỉnh hoặc cấu hình nhiều cơ chế xác thực có thể thay đổi kết quả HTTP cụ thể.

Điểm quan trọng là `httpBasic` chỉ chuẩn bị dữ liệu đầu vào. Việc có xác thực thành công hay không do ứng dụng quyết định, dựa trên chuỗi filter, tài khoản, mật khẩu và các provider được cấu hình.

## 3. Điều kiện để kiểm thử HTTP Basic

Để bài test kiểm tra đúng luồng HTTP Basic, cần có:

- `spring-security-test` trên test classpath, với phiên bản tương thích với Spring Security của ứng dụng.
- MockMvc được kết nối với chuỗi filter Spring Security của ứng dụng.
- Một `SecurityFilterChain` có bật HTTP Basic, chẳng hạn bằng `.httpBasic(Customizer.withDefaults())`.
- Cơ chế xác thực có thể xử lý thông tin username/password, cùng dữ liệu người dùng dành cho test.
- Endpoint và quy tắc phân quyền tương ứng với tình huống kiểm thử.

Ví dụ khai báo dependency trong Gradle của dự án đã quản lý phiên bản Spring Security:

```groovy
dependencies {
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Khi dùng MockMvc được tự xây dựng từ `WebApplicationContext`, tích hợp Spring Security bằng:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(context)
    .apply(springSecurity())
    .build();
```

Trong ứng dụng Spring Boot, có thể dùng MockMvc được tự cấu hình cho bài kiểm thử tích hợp với các filter bảo mật được bật. Nếu chỉ dùng `standaloneSetup(controller)` mà không gắn chuỗi filter tương ứng, việc request có header `Authorization` không chứng minh HTTP Basic được Spring Security xử lý.

## 4. Ví dụ kiểm thử đầy đủ

Giả sử ứng dụng có endpoint `/api/profile` dành cho người dùng đã xác thực và `/api/admin` dành riêng cho người dùng có role `ADMIN`. Tài khoản `alice` chỉ có role `READER`. Bài test dưới đây xây dựng một ứng dụng Servlet nhỏ trong Spring Test để kiểm chứng cả quá trình xác thực lẫn phân quyền.

Ví dụ sử dụng JUnit 5, Spring MVC, Spring Security và Spring Security Test; không cần gửi request qua một HTTP server đang chạy.

```java
import java.security.Principal;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringJUnitConfig(HttpBasicTest.Config.class)
@WebAppConfiguration
class HttpBasicTest {

    @Autowired
    WebApplicationContext context;

    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.webAppContextSetup(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void validCredentialsAllowAccess() throws Exception {
        mockMvc.perform(get("/api/profile")
                .with(httpBasic("alice", "test-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mockMvc.perform(get("/api/profile")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", startsWith("Basic ")));
    }

    @Test
    void unknownUserIsRejected() throws Exception {
        mockMvc.perform(get("/api/profile")
                .with(httpBasic("unknown", "test-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCredentialsAreRejected() throws Exception {
        mockMvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", startsWith("Basic ")));
    }

    @Test
    void authenticatedUserWithoutRequiredRoleIsForbidden()
            throws Exception {
        mockMvc.perform(get("/api/admin")
                .with(httpBasic("alice", "test-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void administratorCanAccessAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-test-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin area"));
    }

    @Configuration
    @EnableWebMvc
    @EnableWebSecurity
    static class Config {

        @Bean
        SecurityFilterChain securityFilterChain(HttpSecurity http)
                throws Exception {
            http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/admin").hasRole("ADMIN")
                    .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults());

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
                    .password(encoder.encode("test-password"))
                    .roles("READER")
                    .build(),
                User.withUsername("admin")
                    .password(encoder.encode("admin-test-password"))
                    .roles("ADMIN")
                    .build()
            );
        }

        @Bean
        ProfileController profileController() {
            return new ProfileController();
        }
    }

    @RestController
    static class ProfileController {

        @GetMapping("/api/profile")
        String profile(Principal principal) {
            return principal.getName();
        }

        @GetMapping("/api/admin")
        String admin() {
            return "admin area";
        }
    }
}
```

Trong ví dụ này, mật khẩu lưu trong `UserDetailsService` là giá trị đã được BCrypt xử lý. Khi gọi `httpBasic("alice", "test-password")`, bài test phải gửi mật khẩu gốc, giống client thật. Việc truyền giá trị hash vào `httpBasic` sẽ không tương đương với việc nhập mật khẩu đúng.

Endpoint `/api/profile` trả về tên của `Principal`, nên bài test xác thực hợp lệ kiểm tra cả HTTP 200 lẫn danh tính mà controller nhận được. Các request kiểm thử được tạo độc lập và không tái sử dụng session hay danh tính đã xác thực của request khác.

## 5. Ma trận kết quả cần kiểm chứng

| Endpoint | Thông tin đăng nhập | Kết quả mong đợi | Ý nghĩa |
| --- | --- | --- | --- |
| `/api/profile` | Alice, mật khẩu đúng | 200 | Xác thực thành công và được phép truy cập |
| `/api/profile` | Alice, mật khẩu sai | 401 | Không xác thực được |
| `/api/profile` | Tên người dùng không tồn tại | 401 | Không xác thực được |
| `/api/profile` | Không có header Authorization | 401 | Tài nguyên yêu cầu xác thực |
| `/api/admin` | Alice, mật khẩu đúng | 403 | Đã xác thực nhưng thiếu role ADMIN |
| `/api/admin` | Admin, mật khẩu đúng | 200 | Đã xác thực và có quyền truy cập |

HTTP 401 và HTTP 403 kiểm chứng hai giai đoạn khác nhau. Trong cấu hình trên, 401 nghĩa là request chưa đáp ứng điều kiện xác thực; 403 nghĩa là danh tính đã được xác thực nhưng không đáp ứng yêu cầu phân quyền.

Header `WWW-Authenticate` trong phản hồi 401 thông báo cơ chế xác thực mà client cần sử dụng. Ví dụ kiểm tra phần đầu `Basic ` vì giá trị realm có thể thay đổi theo cấu hình. Nếu ứng dụng thiết lập `AuthenticationEntryPoint` tùy chỉnh hoặc xử lý riêng request AJAX, cần đặt kỳ vọng phù hợp với chính sách phản hồi của ứng dụng.

## 6. So sánh `httpBasic` với các cách cung cấp danh tính trong test

| Cách viết | Dữ liệu đưa vào kiểm thử | Có kiểm tra username/password thông qua HTTP Basic không? |
| --- | --- | --- |
| `.with(httpBasic("alice", "test-password"))` | Header Authorization theo HTTP Basic | Có, nếu chuỗi filter và cơ chế xác thực tương ứng đang hoạt động |
| `.with(user("alice").roles("READER"))` | Danh tính đã được tạo sẵn cho request | Không |
| `@WithMockUser(username = "alice", roles = "READER")` | SecurityContext chứa danh tính giả lập | Không |
| `.header("Authorization", "Basic ...")` | Header được tạo thủ công | Có, với cùng điều kiện cấu hình |

Ví dụ dùng danh tính tạo sẵn:

```java
mockMvc.perform(get("/api/profile")
        .with(user("alice").roles("READER")))
    .andExpect(status().isOk());
```

Trong đoạn này, `user` là static method của `SecurityMockMvcRequestPostProcessors`. Người dùng có thể không cần tồn tại trong kho dữ liệu người dùng thật. Vì vậy, đoạn test phù hợp khi mục tiêu là kiểm tra hành vi phân quyền của một danh tính đã xác thực, nhưng không phát hiện được lỗi kiểm tra mật khẩu trong HTTP Basic.

Ngược lại, nếu mục tiêu là kiểm chứng rằng mật khẩu sai thực sự bị từ chối, không nên thêm `@WithMockUser` hoặc `.with(user(...))` vào cùng request. Danh tính có sẵn có thể làm thay đổi đường đi của quá trình xác thực và khiến kết quả không còn phản ánh tình huống đăng nhập bằng header độc lập.

## 7. Kiểm thử kết hợp với CSRF

`httpBasic` không thêm CSRF token. Trong ứng dụng Servlet có bảo vệ CSRF được bật, các request thay đổi dữ liệu như POST, PUT hoặc DELETE có thể cần token hợp lệ, kể cả khi thông tin đăng nhập HTTP Basic đúng.

Giả sử ứng dụng có endpoint POST `/api/preferences` cho phép người dùng đã xác thực cập nhật tùy chọn:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;

// Giả sử endpoint trả HTTP 200 khi cập nhật thành công.
mockMvc.perform(post("/api/preferences")
        .with(httpBasic("alice", "test-password"))
        .with(csrf()))
    .andExpect(status().isOk());
```

Đoạn mã này minh họa cách kết hợp hai request post-processor cho một endpoint khác với ứng dụng ở mục 4. Nếu endpoint thuộc phạm vi bảo vệ CSRF, một request thiếu token có thể nhận 403 do CSRF, thay vì do role của người dùng. Vì vậy cần kiểm soát điều kiện CSRF khi mục tiêu của test là kiểm tra xác thực hoặc phân quyền; đồng thời nên có test riêng để kiểm chứng việc thiếu hoặc sai CSRF token bị từ chối. Không nên vô hiệu hóa CSRF chỉ để làm một bài test đăng nhập thành công.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể xảy ra | Hướng kiểm tra |
| --- | --- | --- |
| Mật khẩu đúng nhưng nhận 401 | Không có tài khoản tương ứng, password encoder không khớp hoặc HTTP Basic chưa được cấu hình đúng | Kiểm tra dữ liệu người dùng và SecurityFilterChain |
| Mật khẩu sai nhưng vẫn nhận 200 | Endpoint công khai, danh tính đã tồn tại hoặc filter bảo mật chưa được gắn vào MockMvc | Dùng endpoint yêu cầu xác thực, bỏ danh tính giả lập và xác minh filter |
| Mật khẩu đúng nhưng nhận 403 | Thiếu role hoặc CSRF token | Kiểm tra HTTP method, quy tắc phân quyền và cấu hình CSRF |
| Nhận 302 đến trang đăng nhập | Cấu hình entry point hoặc chuỗi filter đang ưu tiên form login | Kiểm tra cơ chế xác thực áp dụng cho URL |
| Nhận 404 | Đường dẫn hoặc HTTP method không khớp controller | Kiểm tra mapping và các quy tắc bảo mật áp dụng cho URL |
| Không có header WWW-Authenticate như dự kiến | Entry point đã được tùy chỉnh hoặc có cơ chế xử lý loại request riêng | Kiểm tra entry point và các header của request |

Không nên ghi log header `Authorization` hay mật khẩu thật khi phân tích lỗi. Có thể dùng tên tài khoản dành cho test, kết quả HTTP, dữ liệu phản hồi và cấu hình bảo mật để chẩn đoán.

## 9. Phạm vi bảo đảm của bài kiểm thử

Khi chạy với chuỗi filter và provider thích hợp, `httpBasic` giúp kiểm chứng request chứa thông tin đăng nhập có đi qua cơ chế xác thực HTTP Basic và quy tắc phân quyền hay không. Nó cũng cho phép chủ động tạo các request với mật khẩu sai, người dùng không tồn tại hoặc người dùng thiếu quyền.

MockMvc mô phỏng request và response trong môi trường Servlet, không tạo kết nối mạng thực tế. Do đó, bài test này không kiểm chứng việc thiết lập HTTPS, chứng chỉ TLS hay việc proxy chuyển tiếp header Authorization trong môi trường triển khai. Những đặc tính đó cần được kiểm tra bằng các bài kiểm thử tích hợp qua HTTP server và cấu hình triển khai phù hợp.

Hãy chọn `httpBasic` khi cần gửi thông tin đăng nhập theo chuẩn HTTP Basic qua request MockMvc. Một bộ test hữu ích cần có ít nhất tình huống thông tin hợp lệ được phép truy cập, thông tin sai bị từ chối và danh tính hợp lệ nhưng thiếu quyền nhận kết quả phù hợp với chính sách bảo mật.
