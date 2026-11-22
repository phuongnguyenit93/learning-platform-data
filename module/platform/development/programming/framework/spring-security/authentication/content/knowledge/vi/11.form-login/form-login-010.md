# Kiểm tra tạo phiên, đổi định danh phiên và lưu SecurityContext

> Phạm vi: đăng nhập bằng biểu mẫu (`formLogin`) trong **Spring Security Servlet 6.x**, chạy trên **Spring Boot 3.x / Java 17+**. Mục tiêu là quan sát được ba kết quả của một lần đăng nhập thành công: có phiên HTTP khi cần, session ID được thay đổi để chống session fixation, và trạng thái xác thực được lưu để request sau dùng lại. Các hành vi WebFlux/reactive, OAuth2 và JWT không thuộc bài này.

## 1. Cần chứng minh những gì?

Đăng nhập thành công không chỉ là nhận HTTP 302 sau `POST /login`. Hãy phân biệt ba khẳng định độc lập:

1. **Tạo phiên:** request đăng nhập có thể tạo `HttpSession` nếu trước đó chưa có phiên và chính sách cho phép lưu trạng thái. Dấu hiệu là `request.getSession(false) != null` sau khi xử lý; không dùng `getSession()` để kiểm tra vì lời gọi đó tự tạo phiên.
2. **Đổi định danh phiên:** nếu đã tồn tại session trước đăng nhập, đăng nhập thành công thông thường làm `session.getId()` thay đổi. Trong Servlet 3.1+, chiến lược mặc định `changeSessionId` giữ session và các thuộc tính, chỉ đổi ID. Đây là cơ chế giảm rủi ro *session fixation*.
3. **Lưu và khôi phục `SecurityContext`:** sau khi xác thực, `SecurityContext` chứa `Authentication` được lưu qua `SecurityContextRepository`. Request HTTP tiếp theo gửi đúng session cookie phải được nhận diện là cùng người dùng mà **không gửi lại mật khẩu**.

| Dấu hiệu | Cần quan sát | Điều chưa thể suy ra |
| --- | --- | --- |
| Có `HttpSession` | Session hiện diện sau đăng nhập | Không có nghĩa session vừa được tạo bởi bước xác thực; CSRF hoặc `RequestCache` có thể tạo trước đó |
| Session ID đổi | ID trước và sau đăng nhập khác nhau khi **có session từ trước** | Không có nghĩa mọi thuộc tính session bị xóa; `changeSessionId` giữ thuộc tính |
| `SecurityContext` được lưu | Có authentication hợp lệ trong kho lưu và ở request kế tiếp | Chỉ thấy `SecurityContextHolder` có authentication **trong cùng một request** chưa chứng minh đã lưu |
| Truy cập lại tài nguyên | `GET /me` với cùng session trả tên người dùng | `@WithMockUser` hoặc `with(user(...))` không kiểm thử luồng login thật |

## 2. Cơ chế thực tế sau `POST /login`

`formLogin` sử dụng `UsernamePasswordAuthenticationFilter` để nhận `username`, `password` và gọi `AuthenticationManager`. Khi thành công, luồng chính gồm:

```text
Trình duyệt                              Ứng dụng Servlet
    |                                          |
    |-- GET /me (chưa xác thực) -------------->|
    |<-- 302 /login ---------------------------| có thể lưu SavedRequest/session
    |-- GET /login --------------------------->| trang login/CSRF token
    |<-- 200 + form ---------------------------|
    |-- POST /login + CSRF + credentials ----->| UsernamePasswordAuthenticationFilter
    |                                          | 1. AuthenticationManager xác thực
    |                                          | 2. SessionAuthenticationStrategy
    |                                          |    -> changeSessionId() nếu có session
    |                                          | 3. Tạo SecurityContext có Authentication
    |                                          | 4. SecurityContextRepository.saveContext()
    |<-- 302 + session cookie (khi cần) -------|
    |-- GET /me + session cookie ------------->| repository nạp lại SecurityContext
    |<-- 200 "student" ------------------------| request đã xác thực
```

**Ba thành phần dễ bị nhầm:**

- `HttpSession` là nơi lưu thuộc tính theo phiên phía server; trình duyệt chỉ thường giữ một **session ID** trong cookie (`JSESSIONID` mặc định với Servlet container, nhưng tên có thể khác nếu dùng Spring Session hoặc cấu hình riêng). Cookie không chứa toàn bộ `SecurityContext`.
- `SecurityContextHolder` là điểm truy cập trạng thái xác thực **trong request hiện tại** (thường dùng chiến lược dựa trên thread). Nó không phải kho lưu bền vững giữa các request.
- `SecurityContextRepository` quyết định cách **lưu/tải** context. Mặc định của Spring Security 6 là `DelegatingSecurityContextRepository`, gồm `RequestAttributeSecurityContextRepository` cho phạm vi request/dispatch và `HttpSessionSecurityContextRepository` cho các request kế tiếp. Khi được lưu trong session, thuộc tính mặc định mang khóa `SPRING_SECURITY_CONTEXT`.

Ở Spring Security 6, `SecurityContextHolderFilter` nạp context nhưng **không tự lưu** mọi thay đổi. Cơ chế `formLogin` chuẩn thực hiện lưu khi đăng nhập thành công; nếu tự xác thực trong controller/filter thì phải tự lưu context đúng cách. Đừng suy luận rằng chỉ cần gọi `SecurityContextHolder.setContext(...)` là đủ cho request sau.

### Vì sao phải đổi session ID?

Trong tấn công session fixation, kẻ tấn công cố khiến nạn nhân sử dụng một session ID mà kẻ đó đã biết, rồi chờ nạn nhân đăng nhập. Đổi ID khi xác thực giúp session ID cũ không trở thành khóa truy cập cho phiên đã đăng nhập.

Với Servlet 3.1+ và chiến lược mặc định `changeSessionId`:

- **Có session trước login:** ID đổi, cùng một `HttpSession` vẫn giữ các thuộc tính cần thiết.
- **Chưa có session:** một session có thể được tạo để lưu trạng thái sau login; không tồn tại “ID cũ” để so sánh.
- `migrateSession` tạo session mới và chuyển thuộc tính; `newSession` tạo session mới với ít thuộc tính hơn; `none` vô hiệu hóa bảo vệ fixation và không nên dùng tùy tiện.

Đây là lý do bài kiểm thử **đổi ID** phải chủ động cấp một session trước login; bài kiểm thử **tạo session** phải bắt đầu mà không cấp session.

## 3. Ví dụ Spring Boot có thể chạy

Tạo một ứng dụng Spring Boot 3.x (Java 17+) với các dependency:

```groovy
// build.gradle - phần dependencies của dự án Spring Boot đã cấu hình plugin
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tạo ba tệp Java cùng package `example.sessioncheck`. Cấu hình cố ý để `SessionCreationPolicy.IF_REQUIRED` và `changeSessionId` hiện rõ, dù đây cũng là lựa chọn thông thường trong mô hình form login stateful.

**`src/main/java/example/sessioncheck/SessionCheckApplication.java`**

```java
package example.sessioncheck;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionCheckApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionCheckApplication.class, args);
    }
}
```

**`src/main/java/example/sessioncheck/SecurityConfig.java`**

```java
package example.sessioncheck;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                .sessionFixation(fixation -> fixation.changeSessionId())
            );
        // Giữ nguyên CSRF mặc định; POST /login cần CSRF token.
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password("{noop}test-pass")
                .roles("USER")
                .build()
        );
    }
}
```

`{noop}` chỉ để ví dụ này đơn giản, **không dùng mật khẩu rõ trong môi trường thực tế**; hãy dùng `PasswordEncoder` phù hợp (ví dụ BCrypt). `formLogin` sinh trang `GET /login` và tự xử lý `POST /login`; không cần viết controller đăng nhập để ví dụ hoạt động.

**`src/main/java/example/sessioncheck/WhoAmIController.java`**

```java
package example.sessioncheck;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }
}
```

Khi `GET /me` đã xác thực bằng session của `student`, nội dung response chính xác là:

```text
student
```

Khi chưa xác thực, `/me` được bảo vệ và thường chuyển hướng tới trang đăng nhập. Không dựa vào response `302` của login đơn lẻ để kết luận context đã lưu.

## 4. Kiểm thử ba thuộc tính bằng MockMvc

Tạo **`src/test/java/example/sessioncheck/FormLoginSessionTest.java`**. Đây là kiểm thử tích hợp tải `SecurityFilterChain` thật và dùng form login thật: không dùng `@WithMockUser`, vì giả lập người dùng theo request sẽ bỏ qua các bước xác thực và đổi session ID.

```java
package example.sessioncheck;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class FormLoginSessionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulLoginCreatesSessionAndPersistsContext() throws Exception {
        // Không truyền session vào POST: kiểm tra có session sau xác thực.
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "test-pass"))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername("student"))
                .andReturn();

        HttpSession session = login.getRequest().getSession(false);
        assertNotNull(session, "Sau login phải có session để lưu context");

        Object saved = session.getAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
        assertInstanceOf(SecurityContext.class, saved);
        SecurityContext context = (SecurityContext) saved;
        assertNotNull(context.getAuthentication());
        assertEquals("student", context.getAuthentication().getName());

        // Request thứ hai chỉ dùng session; KHÔNG gửi lại username/password.
        mvc.perform(get("/me").session((MockHttpSession) session))
                .andExpect(status().isOk())
                .andExpect(authenticated().withUsername("student"))
                .andExpect(content().string("student"));
    }

    @Test
    void successfulLoginChangesIdOfExistingSession() throws Exception {
        MockHttpSession beforeLogin = new MockHttpSession();
        beforeLogin.setAttribute("shoppingCart", "book");
        String originalId = beforeLogin.getId();

        mvc.perform(post("/login")
                    .session(beforeLogin)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "test-pass"))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername("student"));

        assertNotEquals(originalId, beforeLogin.getId(),
                "changeSessionId phải làm mới ID sau xác thực");
        assertEquals("book", beforeLogin.getAttribute("shoppingCart"),
                "changeSessionId giữ thuộc tính của session cũ");
        assertNotNull(beforeLogin.getAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY));
    }

    @Test
    void rejectedLoginDoesNotEstablishAuthenticatedContext() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "wrong"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());

        assertNull(session.getAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY));
        mvc.perform(get("/me").session(session))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void postWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/login")
                    .param("username", "student")
                    .param("password", "test-pass"))
                .andExpect(status().isForbidden());
    }
}
```

Chạy trong thư mục gốc **của ứng dụng ví dụ**:

```bash
./gradlew test --tests example.sessioncheck.FormLoginSessionTest
./gradlew bootRun
```

Trên Windows, sử dụng `gradlew.bat` tương ứng. Một lần chạy test đạt yêu cầu có **4 test pass**; log/đường dẫn report của Gradle thay đổi theo dự án nên không có mẫu stdout cố định để sao chép.

**Giải thích tại sao các assertion này đáng tin:**

1. Test đầu tiên chỉ xác minh session tồn tại **sau** login, rồi đọc khóa context trong session; việc request kế tiếp trả `student` cho thấy context được nạp lại.
2. Test thứ hai cố tình đưa vào session có sẵn và ghi `originalId` **trước** login. ID mới khác ID cũ mới chứng minh được bảo vệ session fixation. Thuộc tính `shoppingCart` còn nguyên chứng minh `changeSessionId` không xóa cả session.
3. Test sai mật khẩu xác minh không có context xác thực được lưu và request sau vẫn chưa được truy cập. Có thể session vẫn tồn tại cho lý do khác; không lấy “session tồn tại” làm tiêu chí đăng nhập thành công.
4. Test thiếu CSRF chứng minh việc gửi credential đúng vẫn không đủ cho `POST /login`. Đừng tắt CSRF chỉ để test dễ qua.

`MockMvc` dùng mock Servlet request/session; nó kiểm tra hành vi Spring Security trong ứng dụng nhưng **không thay thế** kiểm thử cookie thật, domain/path, `Secure`, `HttpOnly`, `SameSite` và reverse proxy trên trình duyệt/container thật.

## 5. Quan sát bằng trình duyệt (không nhầm phiên với cookie)

Sau khi chạy ứng dụng ở `http://localhost:8080`, mở cửa sổ duyệt web riêng và DevTools → **Network** và **Application/Storage → Cookies**:

1. Truy cập `/me` khi chưa login. Thường sẽ thấy chuyển hướng tới `/login`. Một session có thể đã xuất hiện do lưu `SavedRequest` hoặc CSRF; ghi nhận nếu có nhưng chưa kết luận là phiên đã xác thực.
2. Trên trang `/login`, ghi lại **tên cookie session và ID trước login** (nếu đã tồn tại). Form mặc định có CSRF token.
3. Đăng nhập `student` / `test-pass`. Quan sát request `POST /login`, response redirect và giá trị cookie session sau login. Nếu trước login có ID, ID sau login phải khác theo `changeSessionId`. Với container Servlet thông thường, cookie có thể là `JSESSIONID`; tên và thuộc tính cookie phụ thuộc hạ tầng.
4. Tải `/me` bằng **cùng trình duyệt/cookie**. Kết quả body là `student`. Kiểm tra request gửi session cookie hiện hành, không gửi username/password.
5. Logout bằng giao diện hoặc thực hiện `POST /logout` kèm CSRF token, sau đó vào lại `/me`. Phiên xác thực cũ không được tiếp tục cấp quyền.

Không copy session ID thật vào log, issue, ảnh chụp chia sẻ hay chat: session ID đang hoạt động là thông tin nhạy cảm. Trong kiểm thử tự động có thể so sánh ID trong bộ nhớ mà không in ra.

### Phân tích một số kết quả dễ gây hiểu sai

| Quan sát | Giải thích phù hợp / cách xác minh tiếp |
| --- | --- |
| Có cookie trước login | Bình thường: request cache, CSRF hoặc code ứng dụng có thể tạo session khi chưa xác thực |
| Login thành công nhưng không thấy “đổi ID” | Có thể trước login **chưa hề có session** để đổi; hãy lặp lại với session có trước hoặc dùng test `successfulLoginChangesIdOfExistingSession` |
| Sau login, `SecurityContextHolder` có authentication nhưng `GET /me` lại chuyển login | Kiểm tra `saveContext`, chính sách session, kho context, cookie có được gửi lại và session có hết hạn hay không |
| Có `Set-Cookie` nhưng request tiếp theo chưa xác thực | Kiểm tra cookie domain/path/`Secure`/`SameSite`, cân bằng tải/session store, proxy, timeout, và liệu response có ghi session ID mới không |
| `GET /me` truy cập được khi test dùng `@WithMockUser` | Đó là identity được gắn giả lập cho test, chưa chứng minh form login, xoay ID hoặc persistence |
| `POST /login` trả `403` | Trước hết kiểm tra CSRF token; trong `MockMvc` cần `with(csrf())` |
| Session có trước/sau nhưng không có `SPRING_SECURITY_CONTEXT` | Kiểm tra cấu hình repository, việc xác thực thực sự thành công hay không, hoặc ứng dụng dùng kho tùy chỉnh |

## 6. Phân biệt các chính sách tạo session

`SessionCreationPolicy` điều chỉnh cách **Spring Security** sử dụng session, không mặc định ngăn mọi thành phần khác trong ứng dụng tạo `HttpSession`:

| Chính sách | Ý nghĩa đối với Spring Security | Tác động đến bài kiểm tra |
| --- | --- | --- |
| `ALWAYS` | Luôn tạo session | Thấy session tồn tại chưa chứng minh login đã tạo nó |
| `IF_REQUIRED` | Tạo khi cần; phù hợp form login lưu trạng thái | Có thể tạo lúc đăng nhập nếu trước đó chưa có |
| `NEVER` | Security không tự tạo, nhưng có thể dùng session đã tồn tại | Có thể bị ảnh hưởng bởi session được tạo bởi MVC, CSRF, request cache |
| `STATELESS` | Không tạo session và không dùng session để lấy `SecurityContext` | Không thể áp bài kiểm tra persistence kiểu stateful mặc định; những thành phần khác vẫn có thể tạo session độc lập |

Vì vậy, trước khi kết luận ứng dụng “không tạo session” hay “mất context”, cần xem cả `SessionCreationPolicy`, `SecurityContextRepository`, `RequestCache`, cấu hình CSRF và đường xác thực đang dùng. Đừng dùng các kết luận của form login stateful để suy ra hành vi của API xác thực bằng bearer token.

## 7. Nếu tự viết API đăng nhập

Đoạn sau **chỉ minh họa phần lưu context**, không phải một controller độc lập. Sau khi `AuthenticationManager` trả về một `Authentication` đã xác thực, ứng dụng dùng Spring Security 6 có thể thực hiện:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

Các biến `authentication`, `securityContextRepository`, `request` và `response` phải được cấp trong filter/controller thực tế. Với bộ lọc đăng nhập tự xây dựng, phải tích hợp `SessionAuthenticationStrategy` phù hợp **trước khi lưu** nếu cần bảo vệ session fixation, rồi điều phối success/failure, CSRF, error và redirect đúng thứ tự. `formLogin` chuẩn đã làm những việc liên quan đến login này nên **không cần** tự gọi `saveContext` một lần nữa trong ví dụ ở phần 3.

Điểm then chốt: `SecurityContextHolder.setContext(context)` chỉ đặt trạng thái cho luồng xử lý hiện tại; `securityContextRepository.saveContext(context, request, response)` mới là thao tác persistence khi cơ chế yêu cầu explicit save. Đừng để response hoàn tất/commit trước khi lưu.

## 8. Checklist hoàn thành bài

- [ ] Đã thực hiện đăng nhập thật bằng `POST /login` với credential đúng **và CSRF token hợp lệ**.
- [ ] Với phiên chưa tồn tại trước khi test, có `HttpSession` sau login và context chứa `Authentication` hợp lệ.
- [ ] Với một phiên tạo sẵn, ID trước và sau login **khác nhau**; thuộc tính được giữ lại khi dùng `changeSessionId`.
- [ ] Giá trị session của `SPRING_SECURITY_CONTEXT` được kiểm tra trực tiếp (với repository mặc định).
- [ ] Request `GET /me` tiếp theo, chỉ mang cùng session, vẫn trả `student`.
- [ ] Đăng nhập sai và thiếu CSRF đều không tạo phiên **đã xác thực**.
- [ ] Đã kiểm tra cookie thật trên trình duyệt khi cần xác minh hành vi của servlet container/proxy.

### Tài liệu gốc để đối chiếu

- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security — MockMvc Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html)
- [Spring Security — MockMvc CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
