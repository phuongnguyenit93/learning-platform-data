# Giới hạn phiên đồng thời bằng maximumSessions

> Phạm vi: **Spring Security - authentication → Quản lý phiên**. Bài dùng **Spring Boot 3.x / Spring Security 6.x (Servlet) / Java 17+**, với form login lưu trạng thái trong `HttpSession`. Mục tiêu là giới hạn số phiên đã xác thực của cùng tài khoản bằng `maximumSessions`; phân biệt “phiên mới thay phiên cũ” và “chặn lần đăng nhập mới”, hiểu `SessionRegistry`, kiểm tra bằng hai phiên HTTP thực sự khác nhau và xử lý vòng đời session.

## 1. maximumSessions là giới hạn số phiên của từng principal

Cấu hình ngắn nhất:

```java
http.sessionManagement(session -> session
    .maximumSessions(1)
);
```

`maximumSessions(1)` nghĩa là mỗi **principal đã xác thực** chỉ được có tối đa **một session được coi là active**. Đây không phải là quota chỉ cho một người dùng trên toàn ứng dụng, không phải giới hạn số tab, số request đồng thời hoặc số thiết bị được phát hiện bằng IP.

| Thành phần | Vai trò |
| --- | --- |
| `Principal` | Danh tính đã được xác thực; registry phải nhận ra hai lần login thuộc về cùng tài khoản |
| `HttpSession` | Trạng thái trên server, thường được browser tham chiếu bằng cookie `JSESSIONID` |
| `SessionRegistry` | Liên kết principal với các session ID, thời điểm request gần nhất và trạng thái hết hiệu lực |
| `ConcurrentSessionControlAuthenticationStrategy` | Khi xác thực thành công, quyết định có thể đăng ký session mới hay phải expire/chặn |
| `RegisterSessionAuthenticationStrategy` | Đăng ký session đã được chấp nhận |
| `ConcurrentSessionFilter` | Kiểm tra các request dùng session đã bị đánh dấu `expired` |
| `HttpSessionEventPublisher` | Thông báo sự kiện session bị hủy/đổi ID để registry có thể đồng bộ |
| `maximumSessions` | Giới hạn số phiên; `1` là một phiên, `-1` biểu diễn không giới hạn |

Một ví dụ: `student` có session A trên browser profile A. Khi đăng nhập từ profile B, máy chủ có thể cho B thay A hoặc từ chối B. `reviewer` là tài khoản khác vẫn có quota riêng và không ảnh hưởng tới `student`.

**Hai tab cùng profile thường không tạo hai session.** Chúng chia sẻ cookie session. Mở tab mới không đủ để kiểm thử concurrent sessions; cần hai browser profile/cookie jar riêng hoặc hai `MockHttpSession` độc lập.

## 2. Hai chế độ xử lý khi đã đủ quota

### 2.1. Mặc định: cho phép đăng nhập mới và loại phiên cũ

```java
.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(false)
);
```

Mặc định `maxSessionsPreventsLogin(false)`. Sau khi A login, B login với cùng principal được chấp nhận; A được **đánh dấu `expired`** trong registry. `ConcurrentSessionFilter` thường sẽ invalidate A **khi request tiếp theo từ A đi qua**, rồi thực hiện chiến lược xử lý expired session. Đừng nhầm dấu `expired` với việc lập tức đóng mọi kết nối của thiết bị A.

Nếu thêm `expiredUrl("/session-expired")`, request tiếp theo của A được chuyển hướng tới `/session-expired`:

```text
Client A: POST /login     --> server đăng ký session A --> A thành công
Client A: GET /me         --> 200 student
Client B: POST /login     --> server đánh dấu A expired, đăng ký B
Client B: GET /me         --> 200 student
Client A: GET /me         --> ConcurrentSessionFilter xử lý expired A
                           <-- 302 /session-expired
```

### 2.2. Tùy chọn: giữ phiên cũ và từ chối đăng nhập mới

```java
.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true)
);
```

Khi A còn active, B đăng nhập đúng mật khẩu vẫn bị chặn bởi session strategy. Với `formLogin` chuẩn, `SessionAuthenticationException` sẽ được đưa qua failure handler; hành vi mặc định thường là redirect `/login?error`. A tiếp tục dùng session cũ.

| Khi `student` đăng nhập lần thứ hai | `false` (mặc định) | `true` |
| --- | --- | --- |
| Session A | Mark expired, request kế tiếp bị chặn | Giữ active |
| Session B | Đăng nhập thành công | Đăng nhập bị từ chối |
| Form B | Redirect thành công | Redirect tới failure URL |
| `expiredUrl` | Dành cho request sau của A đã bị expire | Không dành cho B vừa bị từ chối |
| Trade-off | Người dùng có thể thay thiết bị; ai biết mật khẩu có thể đẩy thiết bị cũ ra | Giữ session đang dùng; session cũ bị bỏ quên có thể ngăn login mới |

**Không suy diễn mã HTTP cố định cho mọi ứng dụng.** Form login thường dùng redirect cho cả thành công lẫn thất bại. Với custom filter, API JSON hoặc authentication mechanism khác, status/handler có thể khác; nên kiểm tra cả `Authentication`, `SessionRegistry` và kết quả truy cập ở request tiếp theo.

## 3. Các thành phần phối hợp khi đăng nhập thành công

```text
POST /login + username/password + CSRF
             |
             v
UsernamePasswordAuthenticationFilter
             |
             v
AuthenticationManager
      xác minh credential
             |
             v
SessionAuthenticationStrategy
  1. ConcurrentSessionControlAuthenticationStrategy
     - đếm session active của principal
     - expire session cũ hoặc reject session mới
  2. Session fixation strategy (changeSessionId)
     - đổi ID nếu thích hợp
  3. RegisterSessionAuthenticationStrategy
     - ghi session ID và principal vào registry
             |
             v
SecurityContext được lưu trong session
             |
             '-- redirect theo success/failure handler

GET /me bằng session A đã bị đánh dấu expired
             |
             v
ConcurrentSessionFilter -> xử lý session expired
             |
             '-- 302 /session-expired (nếu cấu hình)
```

- `SessionRegistryImpl` theo dõi `SessionInformation`, gồm session ID, principal, `lastRequest` và `isExpired()`. Nó lưu dữ liệu **trong bộ nhớ của từng ứng dụng** khi dùng implementation mặc định.
- `HttpSessionEventPublisher` chuyển các Servlet session events thành Spring events giúp registry dọn session đã logout, bị timeout hoặc đổi ID. Nếu thiếu cơ chế lifecycle, session đã mất vẫn có thể bị tính quota.
- `SessionFixationProtectionStrategy` hoặc `changeSessionId` bảo vệ session ID khi xác thực; đây là vấn đề **khác** với giới hạn phiên. Đổi ID trong cùng session không có nghĩa có thêm một thiết bị.
- Trong Spring Security 6, `SessionManagementFilter` không được thêm mặc định để tự suy ra mọi đăng nhập. Form login chuẩn tham gia session strategy; nếu tự viết authentication controller/filter, phải kết nối strategy và lưu `SecurityContext` đúng cách. Chỉ đặt `SecurityContextHolder.setContext(...)` không đủ để chứng minh concurrency limit được áp dụng.

**Expired**, **destroyed** và **invalid session** khác nhau: `expireNow()` đánh dấu một session không còn được tiếp tục vì quota; `HttpSession.invalidate()`/timeout hủy session; client gửi ID không tồn tại là invalid session. `expiredUrl` liên quan concurrency expiration, còn `invalidSessionUrl` liên quan ID không hợp lệ và cần xét filter/session management đang dùng.

## 4. Ví dụ Spring Boot chạy được

Ví dụ có hai tài khoản demo để chứng minh quota theo principal: `student` / `study-pass` và `reviewer` / `review-pass`. Dùng form login mặc định, không tự viết authentication filter, vì Spring Security đã tích hợp session concurrency strategy. Property `demo.sessions.reject-new` chọn hai mode mà không phải sao chép code.

### 4.1. Dependencies

Trong project Spring Boot 3.x (Gradle/Java 17), thêm:

```groovy
// build.gradle - phần dependencies
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 4.2. Application

**`src/main/java/example/sessionlimit/SessionLimitApplication.java`**

```java
package example.sessionlimit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLimitApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionLimitApplication.class, args);
    }
}
```

### 4.3. Security configuration

**`src/main/java/example/sessionlimit/SecurityConfig.java`**

```java
package example.sessionlimit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("study-pass"))
                .roles("USER")
                .build(),
            User.withUsername("reviewer")
                .password(encoder.encode("review-pass"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http, SessionRegistry registry, Environment env)
            throws Exception {

        boolean rejectNew = env.getProperty(
            "demo.sessions.reject-new", Boolean.class, false);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/session-expired").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/me", true)
                .permitAll()
            )
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                .sessionFixation(fixation -> fixation.changeSessionId())
                .maximumSessions(1)
                    .maxSessionsPreventsLogin(rejectNew)
                    .expiredUrl("/session-expired")
                    .sessionRegistry(registry)
            );

        return http.build();
    }
}
```

Giải thích lựa chọn:

1. `SessionRegistry` là bean duy nhất được truyền vào cấu hình concurrency, giúp test có thể quan sát trực tiếp `SessionInformation`.
2. `HttpSessionEventPublisher` theo dõi lifecycle (destroyed và ID changed); nếu thiếu có thể dẫn tới stale slot sau logout/timeout, nhất là khi `maxSessionsPreventsLogin(true)`.
3. `SessionCreationPolicy.IF_REQUIRED` phù hợp với form login lưu `SecurityContext` vào session. `SessionCreationPolicy.STATELESS` không phải trường hợp bài này.
4. `changeSessionId` giúp chống session fixation khi xác thực; quota vẫn tính số session đã xác thực, không tính số lần đổi ID.
5. `defaultSuccessUrl("/me", true)` khiến redirect thành công có thể dự đoán để test; nếu không chỉ định, form login có thể chuyển tới saved request.
6. `expiredUrl("/session-expired")` dùng cho A đã bị mark expired; nếu B bị từ chối vì reject-new, form failure handler chuyển B về `/login?error`.
7. CSRF **vẫn bật mặc định** cho POST `/login` và `/logout`; không cần tắt CSRF để thực hiện test.

**`src/main/java/example/sessionlimit/WhoAmIController.java`**

```java
package example.sessionlimit;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/session-expired")
    String expired() {
        return "This session has been replaced";
    }
}
```

GET `/me` với session của `student` trả body chính xác:

```text
student
```

Nếu A bị đánh dấu expired, lần gọi tiếp theo tới endpoint được bảo vệ bằng A sẽ chuyển tới `/session-expired`. URL này được phép truy cập không cần đăng nhập, tránh tạo vòng lặp redirect.

### 4.4. Đổi chế độ bằng application.yml

**`src/main/resources/application.yml`**

```yaml
demo:
  sessions:
    reject-new: false # false: lần login mới thay session cũ
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        http-only: true
        same-site: lax
```

Đặt `demo.sessions.reject-new=true` để bật chế độ từ chối login mới. `server.servlet.session.timeout` điều chỉnh thời gian idle timeout của session theo khả năng container, **không phải** số phiên đồng thời. Production cần HTTPS và cookie `Secure`, chính sách timeout/rotation/audit phù hợp. Hai tài khoản trong bộ nhớ và mật khẩu demo chỉ phục vụ việc học.

## 5. Kiểm thử MockMvc: hai phiên thực sự khác nhau

Không dùng `@WithMockUser` để kiểm tra `maximumSessions`, vì tiện ích đó đặt Authentication giả lập lên request mà không đi qua toàn bộ form login/session strategy. Hai class dưới dùng `POST /login` thật (có CSRF). Mỗi lần helper `login()` được gọi **không đính kèm session trước đó**, mô phỏng hai cookie jar độc lập.

### 5.1. Mặc định: B thành công, A bị expire

**`src/test/java/example/sessionlimit/ReplaceOldSessionTest.java`**

```java
package example.sessionlimit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = "demo.sessions.reject-new=false")
@AutoConfigureMockMvc
class ReplaceOldSessionTest {
    @Autowired MockMvc mvc;
    @Autowired SessionRegistry registry;

    private MockHttpSession login(String username, String password)
            throws Exception {
        MvcResult response = mvc.perform(post("/login")
                .with(csrf())
                .param("username", username)
                .param("password", password))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/me"))
            .andExpect(authenticated().withUsername(username))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) response.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void secondLoginExpiresFirstSession() throws Exception {
        MockHttpSession first = login("student", "study-pass");

        mvc.perform(get("/me").session(first))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));

        // Một POST /login mới, không truyền session A.
        MockHttpSession second = login("student", "study-pass");
        assertNotEquals(first.getId(), second.getId());

        SessionInformation oldInfo =
            registry.getSessionInformation(first.getId());
        assertNotNull(oldInfo);
        assertTrue(oldInfo.isExpired());

        // A bị chặn khi có request tiếp theo.
        mvc.perform(get("/me").session(first))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/session-expired"));

        // B vẫn truy cập tài nguyên được bảo vệ.
        mvc.perform(get("/me").session(second))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));
    }

    @Test
    void limitIsPerPrincipal() throws Exception {
        MockHttpSession student = login("student", "study-pass");
        MockHttpSession reviewer = login("reviewer", "review-pass");

        mvc.perform(get("/me").session(student))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));

        mvc.perform(get("/me").session(reviewer))
            .andExpect(status().isOk())
            .andExpect(content().string("reviewer"));
    }

    @Test
    void loginStillRequiresCsrf() throws Exception {
        mvc.perform(post("/login")
                .param("username", "student")
                .param("password", "study-pass"))
            .andExpect(status().isForbidden());
    }
}
```

Test thứ nhất quan sát hai thời điểm: ngay sau B login, A đã có `SessionInformation.isExpired()==true`; khi A gửi request tiếp theo, `ConcurrentSessionFilter` xử lý và redirect. Test thứ hai chứng minh quota không phải một session cho cả ứng dụng; hai principal khác nhau vẫn hoạt động đồng thời.

### 5.2. Reject-new: B bị từ chối, A tiếp tục hoạt động

**`src/test/java/example/sessionlimit/RejectSecondLoginTest.java`**

```java
package example.sessionlimit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = "demo.sessions.reject-new=true")
@AutoConfigureMockMvc
class RejectSecondLoginTest {
    @Autowired MockMvc mvc;
    @Autowired SessionRegistry registry;

    @Test
    void newLoginRejectedAndExistingSessionPreserved() throws Exception {
        MvcResult firstLogin = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "study-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/me"))
            .andExpect(authenticated().withUsername("student"))
            .andReturn();

        MockHttpSession first =
            (MockHttpSession) firstLogin.getRequest().getSession(false);
        assertNotNull(first);

        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "study-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());

        SessionInformation firstInfo =
            registry.getSessionInformation(first.getId());
        assertNotNull(firstInfo);
        assertFalse(firstInfo.isExpired());

        mvc.perform(get("/me").session(first))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));
    }
}
```

Kết quả mong đợi: B không được login dù credential hợp lệ và redirect về `/login?error`; A vẫn active. Điều đó khác với lỗi password sai dù cùng failure URL. Trong hệ thống thật, không dựa vào thông báo cho user để phân loại nguyên nhân; dùng audit server phù hợp và tránh tiết lộ chi tiết bảo mật.

### 5.3. Chạy và hiểu giới hạn kiểm thử

Trong thư mục gốc dự án Spring Boot có Gradle wrapper:

```bash
./gradlew test --tests example.sessionlimit.ReplaceOldSessionTest
./gradlew test --tests example.sessionlimit.RejectSecondLoginTest
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat`. Ví dụ có tổng cộng **4 phương thức `@Test`**; đây là **kỳ vọng của mã**, không phải khẳng định đã chạy Gradle trong tài liệu. MockMvc mô phỏng Servlet request/session và kiểm tra filter chain; nó không kiểm tra đầy đủ cookie thật, timeout của container hoặc session store phân tán.

Các test có thể dùng ApplicationContext được cache. Khi viết bộ test lớn với cùng username, các session đã đăng ký ở test trước có thể khiến test sau chịu ảnh hưởng. Hãy làm sạch registry hoặc cô lập context có chủ đích khi cần; đặc biệt với mode reject-new. Không dùng `Thread.sleep` để giả lập timeout: hãy kiểm tra logic đó bằng container/session store thực hoặc API điều khiển vòng đời đáng tin.

## 6. Kiểm thử thủ công bằng hai trình duyệt

Với `demo.sessions.reject-new=false`:

1. Mở profile A, vào `http://localhost:8080/login` và đăng nhập `student` / `study-pass`. `GET /me` trả `student`.
2. Mở profile B khác (hoặc browser ẩn danh với cookie store riêng), đăng nhập cùng tài khoản. `GET /me` trên B trả `student`.
3. Quay lại A và tải lại `/me`. Request từ A lúc này phải redirect tới `/session-expired`.
4. Nếu chỉ mở hai tab cùng profile, thường chúng dùng một cookie `JSESSIONID` và một session, nên không kết luận `maximumSessions` đã sai.

Với `demo.sessions.reject-new=true`, sau khi reset môi trường test:

1. A đăng nhập thành công. B cùng tài khoản login và nhận failure redirect.
2. A vẫn xem được `/me`. B không xem được `/me` chỉ bằng một session chưa xác thực.
3. A logout **đúng cách** bằng POST `/logout` kèm CSRF. Khi Servlet container và registry nhận session-destroyed event, slot phải được giải phóng để B đăng nhập. Chỉ đóng tab không đảm bảo gọi logout; server có thể chờ idle timeout.
4. Nếu B không thể login sau logout/timeout, kiểm tra publisher, session registry và session store; không tăng quota tùy tiện để che lỗi stale registry.

Không đưa cookie `JSESSIONID` thật, CSRF token hoặc raw password vào log, issue và ảnh chụp chia sẻ. Trên production cần HTTPS, cookie `HttpOnly` và `Secure`, `SameSite` phù hợp, quản lý timeout và cơ chế thu hồi phiên.

## 7. Những ngộ nhận và giới hạn quan trọng

### 7.1. Số tab khác số phiên

Hai tab cùng cookie thường là cùng session; một user có thể có nhiều browser profile hoặc app client tạo các session khác nhau trên một thiết bị. `maximumSessions` dựa vào session ID và principal, **không xác định thiết bị phần cứng**, không khóa theo IP hay User-Agent.

### 7.2. Session bị đánh dấu expired chưa bị hủy ngay

Trong mode mặc định, B login làm registry đánh dấu A expired. A có thể vẫn tồn tại trong bộ nhớ cho tới request sau và được `ConcurrentSessionFilter` xử lý. Browser có thể hiển thị nội dung cũ đã cache cho tới khi nó gọi server. Không dùng mechanism này để tuyên bố “mọi kết nối WebSocket của A đã bị cắt tức thời”.

### 7.3. equals/hashCode của custom principal phải nhất quán

`SessionRegistryImpl` dùng map dựa trên principal. Nếu custom `UserDetails`/principal không override `equals()` và `hashCode()` đúng cách, hai object cùng tài khoản có thể bị coi là hai người khác nhau, làm quota không hoạt động. Nên dùng ID tài khoản ổn định; tránh đưa trạng thái mutable như role/displayName/lastLogin vào equality. `User` của Spring Security đủ cho demo.

### 7.4. HttpSessionEventPublisher cần được đăng ký thật

Registry phải biết khi session bị destroyed/ID changed. Nếu không có listener đúng, session đã logout hoặc timeout vẫn có thể bị tính là active; `maxSessionsPreventsLogin(true)` dễ khiến user bị khóa đăng nhập vì stale record. `@Bean HttpSessionEventPublisher` trong ứng dụng Spring Boot Servlet hoặc listener tương ứng trong `web.xml` là cấu hình phổ biến. Test lifecycle trên container thực vì MockMvc có hạn chế về event scheduling.

### 7.5. Concurrent-session quota không thay timeout và session fixation

`server.servlet.session.timeout` định nghĩa thời gian không hoạt động, `maximumSessions` đếm phiên đã xác thực, `changeSessionId` bảo vệ session fixation, còn `expiredUrl` chỉ định nơi chuyển hướng khi concurrency expiration được xử lý. Không dùng một cấu hình để suy ra các cấu hình kia.

### 7.6. Nhiều JVM cần registry phân tán

`SessionRegistryImpl` mặc định trong bộ nhớ JVM; nếu có ba instance sau load balancer, từng node có thể không biết session của node khác. Với Spring Session (Redis/JDBC) có thể dùng giải pháp registry phù hợp như `SpringSessionBackedSessionRegistry` và kiểm tra lifecycle, TTL, sticky routing, sự kiện expiration và race giữa các request login. Không giả định chỉ thêm Spring Session dependency sẽ tự bảo đảm quota toàn cụm; cần integration test đa node và đánh giá tính nguyên tử.

### 7.7. Custom login và authentication mechanism khác

Trong Spring Security 6, form login chuẩn áp dụng session strategy sau authentication. Custom controller/filter chỉ tự gọi `AuthenticationManager.authenticate(...)`, sau đó `SecurityContextHolder.setContext(...)` mà **không** gọi session strategy có thể bỏ qua giới hạn `maximumSessions`. Phải tích hợp strategy, fixation protection, register session và `SecurityContextRepository.saveContext(...)` đúng contract. Remember-me/OAuth2 login có các hook riêng; luôn test flow thực.

### 7.8. JWT stateless không được giới hạn bằng HttpSession quota

`SessionCreationPolicy.STATELESS` + Bearer JWT không tự gắn mỗi token vào `HttpSession` hay `SessionRegistryImpl`. `maximumSessions(1)` không tự giới hạn số JWT được cấp hoặc hủy JWT cũ. Nếu sản phẩm cần “chỉ một token/thiết bị”, thiết kế ở authorization server, refresh-token rotation, grant tracking, introspection hoặc revocation list phù hợp.

### 7.9. Giới hạn theo vai trò có thể cấu hình động

Spring Security 6.5 có overload nhận giới hạn theo `Authentication`; ví dụ nếu USER chỉ có một session, ADMIN được hai session:

```java
.sessionManagement(session -> session
    .maximumSessions(authentication ->
        authentication.getAuthorities().stream()
            .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()))
                ? 2 : 1
    )
);
```

Đây là **phương án minh họa khác**, không bổ sung trực tiếp vào cấu hình cố định `maximumSessions(1)` của phần 4. Authorities phải được xác minh từ nguồn server; không nhận role do client tự khai. Khi quyền đổi trong lúc session cũ còn sống, cần xác định chính sách refresh/reauthentication và kiểm tra quota động.

## 8. Lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Mở tab mới mà quota không giới hạn | Cùng `JSESSIONID`, cùng session | Thử hai cookie jar/profile độc lập |
| B login thành công nhưng A chưa thoát ngay | A mới bị mark expired, chưa gửi request | Kiểm tra `SessionInformation.isExpired()` và request tiếp theo của A |
| B login đúng mật khẩu nhưng nhận `/login?error` | `maxSessionsPreventsLogin(true)` đã đủ quota | Kiểm tra policy, session registry, failure/audit |
| A logout rồi B vẫn bị từ chối | Thiếu session event hoặc registry stale | Xác minh `HttpSessionEventPublisher` và timeout cleanup |
| Quota không hoạt động cho custom principal | Equality/hashCode không nhận diện cùng account | Dùng account ID ổn định trong `equals/hashCode` |
| Quota không hoạt động với custom login | Không gọi session authentication strategy | Tích hợp đúng strategy hoặc dùng authentication filter chuẩn |
| Thêm nhiều node thì login quá quota | `SessionRegistryImpl` cục bộ từng JVM | Chọn distributed registry/session store, test đa node |
| `expiredUrl` không được dùng khi session timeout | Expired do quota khác ID invalid/timeout | Tách cấu hình và test |
| JWT cũ vẫn hợp lệ sau khi login mới | JWT stateless không có HttpSession quota | Thiết kế token lifecycle/rotation/revocation tại issuer |
| Một user làm user khác mất session | Principal mapping không ổn định hoặc dùng chung session | Kiểm tra registry principal, equality, cookie |
| A đã mark expired nhưng UI còn nội dung | Browser cache, chưa có HTTP request mới | Kiểm tra request mạng và cơ chế push riêng nếu cần |

## 9. Hướng dẫn vận hành và đánh đổi bảo mật

Mode thay thế phiên cũ cho phép người dùng tự chuyển máy nhưng người có mật khẩu bị lộ cũng có thể đẩy phiên đang dùng ra ngoài. Mode từ chối giữ session cũ nhưng người dùng có thể mắc kẹt nếu thiết bị đã mất hoặc tab đóng mà server chưa timeout. Vì thế cần kết hợp rate limiting, MFA cho tài khoản nhạy cảm, thông báo đăng nhập bất thường, trang xem và thu hồi session, quy trình khôi phục tài khoản, session idle/absolute timeout và audit.

Không dùng `maximumSessions` như biện pháp chống brute force hoặc chống mọi hình thức account sharing. Thay đổi session quota không chứng minh người dùng là cùng một cá nhân, và không tự bảo vệ cookie bị đánh cắp. Khi cần “đăng xuất mọi thiết bị”, cần quản lý lifecycle, token riêng, kết nối dài hạn và cached content ngoài session.

## 10. Checklist hoàn thành

- [ ] Form login thật chạy trên Servlet SecurityFilterChain với `maximumSessions(1)`.
- [ ] Có `HttpSessionEventPublisher` và một `SessionRegistry` nhất quán trong cấu hình/test.
- [ ] Hiểu quota áp dụng **theo principal**, không theo số tab hoặc số HTTP request.
- [ ] Đã tạo hai phiên HTTP khác nhau để test cùng username.
- [ ] Với `maxSessionsPreventsLogin(false)`, B login thành công, A được đánh dấu expired và bị chặn ở request sau.
- [ ] Với `maxSessionsPreventsLogin(true)`, B không được xác thực và A vẫn active.
- [ ] Đã kiểm tra login vẫn cần CSRF; logout dùng POST với token phù hợp.
- [ ] Phân biệt expired session với destroyed session, timeout và invalid session ID.
- [ ] Principal custom có equality/hashCode theo danh tính ổn định.
- [ ] Đã xác minh logout/timeout/session ID change và registry cleanup trên Servlet container thật.
- [ ] Khi triển khai nhiều node, không dùng in-memory registry đơn lẻ để tuyên bố quota toàn cụm.
- [ ] Không nhầm HttpSession concurrency với hạn chế JWT/Bearer token stateless.
- [ ] UX và bảo mật hỗ trợ người dùng khi phiên bị thay thế hoặc đăng nhập mới bị từ chối.

### Tài liệu chính thức

- [Spring Security 6.5 — Authentication Persistence and Session Management: Concurrent Session Control](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security — SessionRegistry API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/session/SessionRegistry.html)
- [Spring Security — SessionInformation API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/session/SessionInformation.html)
- [Spring Security — ConcurrentSessionControlAuthenticationStrategy](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/ConcurrentSessionControlAuthenticationStrategy.html)
- [Spring Security — HttpSessionEventPublisher](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/session/HttpSessionEventPublisher.html)
- [Spring Security — FAQ: browser windows and HttpSession](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/faq.html)
- [Spring Session — Spring Security Integration](https://docs.spring.io/spring-session/reference/spring-security.html)
