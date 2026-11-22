# Session fixation và các chiến lược thay đổi định danh phiên

## 1. Session fixation là gì và vì sao liên quan đến đăng nhập?

Trong ứng dụng web dùng HTTP session, browser thường gửi một cookie như `JSESSIONID`. Cookie chứa **mã định danh phiên** (*session ID*) chứ không chứa toàn bộ danh tính người dùng. Servlet container dựa vào ID đó để tìm đối tượng `HttpSession` trên server. Khi người dùng đăng nhập thành công, Spring Security có thể lưu `SecurityContext` chứa `Authentication` vào session để request tiếp theo nhận ra người dùng mà không cần nhập lại mật khẩu.

**Session fixation** (cố định phiên) là tình huống kẻ tấn công có được hoặc kiểm soát trước một session ID mà nạn nhân sẽ dùng, sau đó tìm cách khiến nạn nhân đăng nhập trên **chính phiên đó**. Nếu ứng dụng giữ nguyên ID qua ranh giới *chưa đăng nhập → đã đăng nhập*, người biết ID từ trước có thể thử tái sử dụng nó để chiếm quyền của phiên đã xác thực.

Luồng nguy hiểm được đơn giản hóa:

~~~text
Trước xác thực                            Sau xác thực
──────────────────────────────────────────────────────────────
Attacker biết session ID "S-OLD"
            │
            └── nạn nhân bị dẫn đến dùng phiên "S-OLD"
                                      │
                           Nạn nhân nhập mật khẩu đúng
                                      │
                      Ứng dụng KHÔNG đổi session ID
                                      │
                          Phiên "S-OLD" nay đã đăng nhập
                                      │
                 Người biết "S-OLD" có thể thử dùng lại
                 phiên đã được nâng quyền xác thực
~~~

**Giải pháp cốt lõi:** khi một đăng nhập tạo ra trạng thái xác thực mới, **thay đổi session ID** để định danh mà người khác có thể biết trước không còn là chìa khóa của phiên đã đăng nhập.

~~~text
Phiên trước login: S-OLD (anonymous)
          │
          ├── Đăng nhập thất bại → không nâng quyền
          │
          └── Đăng nhập thành công
                     │
                Session fixation protection
                     │
          Định danh mới: S-NEW (authenticated)
                     │
          S-OLD không được dùng để truy cập phiên đã
          xác thực sau chuyển đổi
~~~

Cần phân biệt session fixation với:

- **Session hijacking:** kẻ tấn công lấy trộm một session ID *sau khi* người dùng đã đăng nhập. Thay ID lúc login **không** tự chặn việc đánh cắp ID về sau.
- **Session replay:** một ID còn hiệu lực bị sử dụng lại. Session fixation protection chặn việc duy trì ID cũ qua login; còn phòng replay cần HTTPS, cookie an toàn, chống XSS và quản lý phiên.
- **Session timeout:** server làm session hết hạn sau thời gian không hoạt động hoặc sau thời hạn tuyệt đối. Đổi ID lúc login không thay thế timeout.
- **Session logout:** làm phiên đăng nhập không còn hợp lệ. Đổi ID không phải thao tác logout.
- **CSRF:** lạm dụng browser tự gắn cookie để gửi thao tác không mong muốn. CSRF và session fixation là hai vấn đề khác nhau, cần biện pháp riêng.

Bài học sử dụng **Spring Boot 3.x, Spring Security 6.x, Java 17+ và Servlet/Spring MVC**. Các API và chiến lược dưới đây áp dụng cho xác thực **có HTTP session**. Một chain `SessionCreationPolicy.STATELESS` không sử dụng session để lưu `SecurityContext` sẽ có mô hình khác.

## 2. Vì sao có session trước khi đăng nhập?

“Chưa login” không đồng nghĩa “chưa có session”. Một request ẩn danh vẫn có thể tạo `HttpSession` để lưu:

- CSRF token (nếu sử dụng `HttpSessionCsrfTokenRepository`).
- Dữ liệu phiên tạm như giỏ hàng, ngôn ngữ, wizard đăng ký, thông tin điều hướng.
- Saved request: đường dẫn được yêu cầu trước login, để quay lại khi đăng nhập thành công.
- Các thuộc tính được thư viện hoặc servlet container đưa vào session.

Ví dụ:

~~~text
GET /login → cookie JSESSIONID=S-OLD
POST /login + cookie S-OLD + username/password
→ nếu đăng nhập thành công, nên chuyển sang S-NEW
GET /me + cookie S-NEW → danh tính đã xác thực
GET /me + cookie S-OLD → không được nhận danh tính đó
~~~

Giữ nguyên **dữ liệu ứng dụng** và giữ nguyên **mã định danh** là hai chuyện khác nhau. Ứng dụng có thể cần giữ giỏ hàng khi user đăng nhập nhưng vẫn phải bỏ ID cũ. Đây là lý do Spring Security cung cấp nhiều chiến lược: đổi ID ngay trong session hiện có, hoặc tạo session mới rồi chuyển dữ liệu theo chính sách.

## 3. Spring Security xử lý session fixation lúc nào?

Spring Security thực hiện bảo vệ khi có **sự kiện xác thực thành công** trong một cơ chế đăng nhập được tích hợp với session management, ví dụ form login. Cơ chế xác thực gọi `SessionAuthenticationStrategy` thích hợp; chiến lược session fixation được thực hiện trước khi hoàn tất quy trình tạo phiên đăng nhập.

Một luồng form login khái quát:

~~~text
POST /login + credential + CSRF token
       │
       ▼
CsrfFilter kiểm tra CSRF (nếu bật)
       │
       ▼
UsernamePasswordAuthenticationFilter
       │
       ▼
AuthenticationManager / AuthenticationProvider
       │
       ├── Sai credential
       │     └── AuthenticationFailureHandler
       │           (không có phiên mới được xác thực)
       │
       └── Thành công: Authentication hợp lệ
                   │
                   ▼
           SessionAuthenticationStrategy
                └── Session fixation strategy
                    đổi ID hoặc thay session
                   │
                   ▼
           Lưu SecurityContext theo cơ chế của filter
                   │
                   ▼
           AuthenticationSuccessHandler
                   │
                   ▼
           Browser tiếp tục bằng session ID mới
~~~

Các điểm dễ bị hiểu sai:

1. **Không đổi ID ở mọi request.** Việc xoay định danh liên quan tới lúc xác thực thành công; không nên tự đổi liên tục ở mọi GET vì có thể phá hoạt động của nhiều tab/request song song.
2. **Không đổi thành công khi password sai.** Session có thể vẫn tồn tại cho CSRF, thông báo lỗi hoặc giỏ hàng, nhưng không được nâng thành phiên authenticated.
3. **Không phải mọi “có Authentication” đều là form login.** Basic/Bearer stateless thường xác thực theo từng request và không cần session cố định; nếu chủ động lưu chúng vào session, phải đánh giá bảo vệ fixation ở luồng custom đó.
4. **Spring Security 6 có thay đổi quan trọng:** `SessionManagementFilter` không được sử dụng theo mặc định; authentication mechanism tự chịu trách nhiệm gọi `SessionAuthenticationStrategy`. Nếu tự viết JSON login trong controller mà chỉ gọi `AuthenticationManager.authenticate(...)`, không được mặc định rằng chiến lược đổi ID sẽ tự chạy.
5. **Bảo vệ fixation là một phần của lifecycle session.** Nó không tự tạo HTTPS, không sửa cookie không an toàn và không cấu hình tất cả các chính sách đồng thời như concurrent sessions.

## 4. Bốn chiến lược: changeSessionId, migrateSession, newSession, none

Spring Security cung cấp các lựa chọn thông qua DSL:

~~~java
http.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.changeSessionId())
);
~~~

Chỉ chọn **một** chiến lược cho chain cần quản lý phiên. Trên Servlet 3.1+ (bao gồm môi trường Servlet hiện đại của Spring Boot 3), **`changeSessionId` là mặc định** nếu bảo vệ session fixation được dùng theo cấu hình tiêu chuẩn.

| Chiến lược | Cách hoạt động | Thuộc tính session trước login | Nhận xét |
| --- | --- | --- | --- |
| `changeSessionId()` | Dùng `HttpServletRequest.changeSessionId()` của container để thay ID, không tạo session mới | **Giữ lại** cùng session và thuộc tính | Mặc định, ưu tiên trên Servlet 3.1+; ít ảnh hưởng tới dữ liệu phiên. |
| `migrateSession()` | Vô hiệu session cũ, tạo session mới, copy **toàn bộ** attributes | **Được chuyển** sang session mới | Có thể gây callback/lifecycle ảnh hưởng đến đối tượng gắn với session. |
| `newSession()` | Tạo session mới “sạch”, không chuyển dữ liệu ứng dụng thông thường; Spring Security-related attributes vẫn có thể được copy | **Không tự chuyển** ordinary application attributes | Thích hợp khi muốn tách mạnh pre-login data, nhưng có thể làm mất state cần thiết. |
| `none()` | Không thực hiện bảo vệ session fixation | ID cũ có thể được giữ qua login | **Không khuyến nghị**: có thể mở lỗ hổng cố định phiên. |

### 4.1. changeSessionId() — đổi ID, giữ phiên

Với Servlet 3.1+:

~~~java
http.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.changeSessionId())
);
~~~

Nó sử dụng khả năng của servlet container để thay định danh session hiện có. Về mặt học tập, có thể hình dung:

~~~text
HttpSession đã có:
  id = OLD
  attributes = {
     "cartDraft": "sách Java",
     "locale": "vi"
  }

Xác thực thành công + changeSessionId()

HttpSession:
  id = NEW
  attributes = {
     "cartDraft": "sách Java",
     "locale": "vi",
     ... thuộc tính bảo mật sau login ...
  }
~~~

Điểm quan trọng:

- **Không cần sao chép attributes sang một session mới** vì session hiện hữu được đổi ID trực tiếp.
- ID trước đăng nhập không còn là định danh hợp lệ của phiên đã đăng nhập.
- Ứng dụng ít gặp tác động phụ do hủy rồi tạo lại session.
- Có thể phát sinh sự kiện đổi ID cho `HttpSessionIdListener`, đồng thời Spring Security công bố `SessionFixationProtectionEvent` khi thực hiện bảo vệ.
- Cần Servlet 3.1+; không dùng chiến lược này trên container quá cũ.

Trong thực tế Spring Boot 3 chạy trên Servlet container hiện đại nên đây thường là lựa chọn tốt. Việc ID mới được trả về browser phụ thuộc container/cookie và response; kiểm tra bằng DevTools thay vì tự dựng cookie `JSESSIONID`.

### 4.2. migrateSession() — tạo session mới, chuyển toàn bộ attributes

~~~java
http.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.migrateSession())
);
~~~

Luồng:

~~~text
Old Session S1:
    cartDraft = "Java"
    uiLocale = "vi"
    customDraft = ...

      invalidate(S1)
             │
     create new session S2
             │
     copy session attributes
             ▼
New Session S2:
    cartDraft = "Java"
    uiLocale = "vi"
    customDraft = ...
    SecurityContext sau authentication
~~~

Ưu điểm: bảo vệ fixation mà vẫn giữ dữ liệu ẩn danh đã có, tiện cho checkout/login hoặc tiếp tục wizard.

Điểm cần cân nhắc:

- Đây **không** chỉ là thay ID; việc hủy và tạo session mới có thể kích hoạt logic lifecycle.
- Copy attributes có thể liên quan đến `HttpSessionBindingListener`, session-scoped bean và callback gắn/bỏ gắn đối tượng. Cần kiểm tra ứng dụng có listener quản lý tài nguyên hay không.
- Tất cả attributes đã có (kể cả dữ liệu tùy ý) được chuyển theo chính sách này; nếu ứng dụng không muốn dữ liệu pre-login đi vào phiên authenticated, hãy xem xét `newSession()` hoặc tự phân loại dữ liệu.
- Không đồng nghĩa “copy toàn bộ server object graph sang nơi khác”; ý nghĩa API là chuyển attributes trong lifecycle session do container quản lý.

### 4.3. newSession() — tạo phiên mới với dữ liệu ứng dụng được tách

~~~java
http.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.newSession())
);
~~~

Spring Security tạo một session mới mà **không copy các thuộc tính ứng dụng thông thường**. Tuy nhiên các thuộc tính liên quan đến Spring Security vẫn có thể được chuyển để cơ chế bảo mật hoạt động. Vì vậy nói “session mới hoàn toàn không có attributes” là không chính xác.

Ví dụ:

~~~text
Old session:
  cartDraft = "Java"
  anonymousFlow = "step2"
  SPRING_SECURITY_... = ...

Login thành công với newSession()

New session:
  (không tự có cartDraft, anonymousFlow)
  (vẫn có thể có thuộc tính liên quan Spring Security)
  SecurityContext = user đã xác thực
~~~

Khi chọn `newSession()`, đội phát triển phải quyết định dữ liệu pre-login nào thực sự cần mang sang phiên sau login. Đừng bật chỉ vì tên “new” nghe an toàn hơn: có thể làm mất giỏ hàng, bước onboarding, thông tin redirect hoặc trạng thái UI. Với dữ liệu cần thiết, hãy triển khai cơ chế chuyển đổi **được kiểm tra, giới hạn và xác minh** thay vì copy tùy tiện mọi attribute.

### 4.4. none() — tắt bảo vệ fixation

~~~java
http.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.none())
);
~~~

Cấu hình này **không thực hiện thay đổi ID như biện pháp session fixation**. Nó không đồng nghĩa “session không tồn tại”. Nếu đăng nhập bằng session mà vẫn để ID trước login không đổi, người biết trước ID có thể có cơ hội sử dụng phiên sau khi được xác thực.

Không chọn `none()` chỉ để giữ nguyên `JSESSIONID` cho frontend, tránh “mất state” hoặc sửa một test đang fail. Nếu hệ thống hoàn toàn stateless, hãy khai báo `SessionCreationPolicy.STATELESS` theo thiết kế; không cần tắt fixation trên web session đang đăng nhập.

### 4.5. So sánh theo tình huống thực tế

| Nhu cầu | Lựa chọn thường phù hợp | Lưu ý |
| --- | --- | --- |
| Web login chuẩn trên Boot 3 / Servlet hiện đại | `changeSessionId()` | Mặc định; giữ pre-login attributes và đổi ID. |
| Container cũ không hỗ trợ `changeSessionId` | `migrateSession()` | Trên Servlet 3.0 hoặc cũ hơn có thể là mặc định; không áp dụng cho Boot 3 Servlet hiện đại. |
| Cần giữ giỏ hàng/wizard qua login | `changeSessionId()` hoặc `migrateSession()` | Vẫn rà soát nội dung session trước login. |
| Không muốn mang state ẩn danh sang session authenticated | `newSession()` | Xác định dữ liệu business thật sự cần giữ. |
| API xác thực bằng token, hoàn toàn không dựa vào session | `STATELESS` ở chain API | Đây là chính sách tạo/sử dụng session, không phải một fixation strategy. |
| Muốn “tắt cho dễ chạy” | **Không chọn `none()`** | Tìm nguyên nhân lỗi session/cookie/test. |

## 5. Chọn chiến lược không thay thế các chính sách session khác

Một số cấu hình có tên giống nhau nhưng giải quyết bài toán khác:

- `sessionFixation(...changeSessionId())`: đổi ID lúc xác thực để chống fixation.
- `sessionCreationPolicy(IF_REQUIRED)`: cho phép tạo session khi cần, phù hợp web login.
- `sessionCreationPolicy(STATELESS)`: Spring Security không tạo session và không dùng session để lấy `SecurityContext`, phù hợp API token-based.
- `maximumSessions(1)`: giới hạn số phiên xác thực đồng thời, không thay cho đổi ID.
- `invalidSessionUrl("/session-expired")`: đưa user đến nơi xử lý khi request có ID session không hợp lệ; không tự tạo lớp bảo vệ fixation.
- `logout().invalidateHttpSession(true)`: vô hiệu hóa phiên khi logout, khác với xoay ID lúc login.
- Cookie `HttpOnly`, `Secure`, `SameSite`: bảo vệ việc truy cập/gửi cookie và các ngữ cảnh browser; không thay thế session fixation strategy.

**Vì sao không chỉ dùng `HttpOnly`?** Cookie `HttpOnly` cản JavaScript trực tiếp đọc ID nhưng không thay đổi thực tế rằng một ID có thể đã bị biết trước do nhiều nguyên nhân khác. Cần xoay định danh lúc nâng quyền. Tương tự, `SameSite` giúp giảm một số yêu cầu cross-site nhưng không chữa fixation theo cách đổi ID.

## 6. Ví dụ chạy được: form login tự đổi session ID

Mục tiêu demo:

1. Người dùng ẩn danh có session trước login (ví dụ từ CSRF hoặc dữ liệu tạm).
2. Khi `student` đăng nhập bằng form, Spring Security dùng `changeSessionId()`.
3. Thuộc tính ứng dụng `cartDraft` trong session vẫn được giữ.
4. Request tới `GET /me` sau login lấy principal từ session.
5. Session ID không được đưa vào response JSON hoặc log ứng dụng.

### 6.1. Dependency và cấu trúc dự án

Tạo Spring Boot 3.x project với Java 17+, dependencies Spring Web, Spring Security và Spring Boot Test. Trong Gradle project đã có Spring Boot plugin, thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đoạn trên là phần `dependencies` và cấu hình test, **không phải file `build.gradle` độc lập**. Package dùng xuyên suốt là `com.example.sessionfixation`:

~~~text
src/main/java/com/example/sessionfixation/
  SessionFixationApplication.java
  SecurityConfig.java
  WebController.java

src/test/java/com/example/sessionfixation/
  SessionFixationTest.java
~~~

### 6.2. SessionFixationApplication.java

~~~java
package com.example.sessionfixation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionFixationApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionFixationApplication.class, args);
    }
}
~~~

### 6.3. SecurityConfig.java

~~~java
package com.example.sessionfixation;

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
public class SecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                .sessionFixation(fixation -> fixation.changeSessionId())
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build()
        );
    }
}
~~~

Giải thích:

- `changeSessionId()` được ghi rõ để học cách cấu hình dù trên Servlet 3.1+ đây thường là mặc định.
- `IF_REQUIRED` cho phép Spring Security tạo session khi cần lưu `SecurityContext`; không dùng `STATELESS` cho web form login.
- `formLogin` đăng ký authentication filter và success/failure handling tiêu chuẩn. Cơ chế đó thực hiện `SessionAuthenticationStrategy` khi xác thực thành công.
- `logout` xử lý hủy phiên/clear security context. Logout không cần gọi `changeSessionId` để giải quyết fixation.
- Password demo được mã hóa một chiều bằng BCrypt khi tạo user; tài khoản cứng trong mã chỉ phục vụ học tập.

Khi dùng phần này làm cơ sở cho production, cần cấu hình user store thật, password policy, timeout, HTTPS, cookie flags, số lần thử đăng nhập, logging an toàn và quyền endpoint. Ví dụ không tự giải quyết các yêu cầu đó.

### 6.4. WebController.java

~~~java
package com.example.sessionfixation;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WebController {

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of("message", "public");
    }

    @GetMapping("/me")
    public Map<String, String> me(Principal principal) {
        return Map.of("username", principal.getName());
    }
}
~~~

Ở đây `Principal` do Spring Security cung cấp từ phiên đăng nhập đã được xác thực. Controller không cần và **không nên** trả session ID về browser trong JSON. Session ID là secret có giá trị tương đương quyền truy cập phiên.

### 6.5. Chạy ứng dụng

Trong thư mục dự án có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Truy cập `http://localhost:8080/me` khi chưa đăng nhập; ứng dụng chuyển tới trang login. Đăng nhập `student` / `demo-pass` bằng form của Spring Security; sau đó `GET /me` trả JSON:

~~~json
{"username":"student"}
~~~

HTTP trên `localhost` ở đây chỉ để thử nghiệm. Khi deploy, **phải dùng HTTPS**. Không dùng tài khoản hoặc password demo cho môi trường thật.

## 7. Kiểm thử tự động bằng MockMvc: ID đổi, dữ liệu còn

MockMvc giúp kiểm tra luồng `POST /login` và `HttpSession` mà không cần đọc/ghi ID phiên ra log. Ta khởi tạo sẵn session ẩn danh để bài test có một ID **trước** đăng nhập; nếu không có session trước login thì không có ID cũ để đem so sánh.

File `src/test/java/com/example/sessionfixation/SessionFixationTest.java`:

~~~java
package com.example.sessionfixation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionFixationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulLoginChangesExistingSessionId() throws Exception {
        MockHttpSession session = new MockHttpSession();
        session.setAttribute("cartDraft", "java-book");
        String beforeLoginId = session.getId();

        MvcResult login = mvc.perform(
                post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "demo-pass")
            )
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession afterLogin =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(afterLogin);

        // Chỉ so sánh ID trong test; không in token này ra log.
        assertNotEquals(beforeLoginId, afterLogin.getId());

        // changeSessionId giữ dữ liệu phiên ứng dụng có từ trước.
        assertEquals("java-book", afterLogin.getAttribute("cartDraft"));

        mvc.perform(get("/me").session(afterLogin))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("student"));
    }

    @Test
    void failedLoginDoesNotPromoteAnonymousSession() throws Exception {
        MockHttpSession session = new MockHttpSession();
        String beforeLoginId = session.getId();

        mvc.perform(
                post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "wrong-password")
            )
            .andExpect(status().is3xxRedirection());

        // Không có authentication thành công để kích hoạt đổi ID.
        assertEquals(beforeLoginId, session.getId());

        mvc.perform(get("/me").session(session))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void subsequentGetDoesNotRotateSessionAgain() throws Exception {
        MockHttpSession session = new MockHttpSession();

        MvcResult login = mvc.perform(
                post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "demo-pass")
            )
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession afterLogin =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(afterLogin);
        String authenticatedId = afterLogin.getId();

        mvc.perform(get("/me").session(afterLogin))
            .andExpect(status().isOk());

        assertEquals(authenticatedId, afterLogin.getId());
        assertFalse(afterLogin.isInvalid());
    }

    @Test
    void logoutInvalidatesAuthenticatedSession() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(
                post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "demo-pass")
            )
            .andExpect(status().is3xxRedirection());

        mvc.perform(
                post("/logout")
                    .session(session)
                    .with(csrf())
            )
            .andExpect(status().is3xxRedirection());

        // Logout hủy session, khác với đổi ID khi login.
        assertFalse(!session.isInvalid());
    }
}
~~~

Giải thích từng test:

| Test | Kiểm tra | Kỳ vọng |
| --- | --- | --- |
| `successfulLoginChangesExistingSessionId` | Có session ẩn danh trước login; đăng nhập đúng | `beforeLoginId != afterLogin.getId()`, `cartDraft` vẫn tồn tại, user vào `/me` thành công. |
| `failedLoginDoesNotPromoteAnonymousSession` | Gửi password sai | Không có authentication success; session không bị nâng quyền. |
| `subsequentGetDoesNotRotateSessionAgain` | GET sau login thành công | ID giữ nguyên giữa các GET bình thường. |
| `logoutInvalidatesAuthenticatedSession` | POST logout có CSRF | Session bị vô hiệu hóa. |

Trong một test suite lớn, nên tránh phụ thuộc trạng thái giữa test và tránh hiển thị ID session trong assertion failure ngoài môi trường nội bộ. `MockHttpSession` mô phỏng lifecycle; để xác minh **cookie thật** và khả năng client gửi lại ID cũ, bổ sung integration test dùng embedded Servlet container/browser.

Chạy kiểm thử:

~~~bash
./gradlew test --tests com.example.sessionfixation.SessionFixationTest
~~~

Hoặc trên Windows:

~~~powershell
.\gradlew.bat test --tests com.example.sessionfixation.SessionFixationTest
~~~

Nếu dự án đủ dependencies và tất cả assertion đạt, Gradle báo `BUILD SUCCESSFUL`; đây là kết quả **mong đợi**, không phải log kiểm thử đã thực thi. Mã phụ thuộc Spring Boot/Security nên `javac` không có classpath tương ứng sẽ không biên dịch độc lập.

### 7.1. Trường hợp thiếu session trước login

Khi login diễn ra mà browser chưa có session, backend có thể **tạo một session mới** để lưu trạng thái đã xác thực. Lúc đó không có “ID ẩn danh trước login” để so sánh; đây **không phải** bằng chứng rằng fixation protection không chạy. Vì thế test cần cố ý thiết lập session ẩn danh trước khi login.

### 7.2. Kiểm tra migrateSession và newSession như thế nào?

Thay đúng một cấu hình trong `SecurityConfig`:

~~~java
.sessionFixation(fixation -> fixation.migrateSession())
~~~

hoặc:

~~~java
.sessionFixation(fixation -> fixation.newSession())
~~~

Rồi điều chỉnh assertion test theo semantics:

- `migrateSession()`: session object mới, ID mới, `cartDraft` được copy qua; không giữ tham chiếu session cũ làm nguồn xác thực.
- `newSession()`: session object mới, ID mới, `cartDraft` không tự được copy; Spring Security-related attrs có thể còn theo cơ chế framework.
- `changeSessionId()`: session giữ nguyên, ID mới, `cartDraft` còn trong cùng session.

**Không áp dụng cả ba trong cùng một chain.** Chúng là lựa chọn loại trừ nhau. Nếu muốn so sánh tự động bằng nhiều test class, dùng cấu hình test riêng hoặc ứng dụng mẫu riêng cho từng chiến lược, không đổi live config trong khi nhiều test chạy song song.

## 8. Kiểm chứng từ browser: điều gì phải quan sát?

Trong DevTools → Network / Application → Cookies, kiểm tra ở môi trường local demo:

1. Trước login: nếu ứng dụng đã tạo session, browser có cookie session. Ghi nhận **sự thay đổi** của ID cho mục đích test nhưng **không sao chép ID thật vào ticket, chat hoặc log**.
2. Submit login form đúng với CSRF token do Spring Security cung cấp.
3. Sau login: response có thể có `Set-Cookie` cập nhật ID session; browser gửi ID mới trong request `GET /me`.
4. Request đến `/me` khi đã authenticated trả JSON username.
5. Nếu thử dùng **ID cũ** từ trước login trong môi trường test cô lập, nó không được đại diện cho phiên đã đăng nhập. Không kiểm tra trên phiên của người dùng thật hoặc môi trường production.
6. Logout bằng luồng chuẩn: phiên sau login bị vô hiệu hóa; ID mới cũ đều không còn là phiên authenticated.

Dùng DevTools để kiểm tra `Set-Cookie`, `Cookie` và các thuộc tính cookie, nhưng nhớ JavaScript thường **không đọc được cookie `HttpOnly`**. Đó là hành vi đúng. Browser và Servlet container kiểm soát cookie lifecycle; Spring Security quyết định chiến lược quản lý phiên.

### 8.1. Vì sao không nên tự gửi cookie session bằng JavaScript?

Với ứng dụng session-based, hãy giữ cookie `HttpOnly` và để browser tự gắn cookie khi hợp lệ. Không đưa `JSESSIONID` vào JSON login, `localStorage` hoặc custom header để “giữ phiên sau rotation”. Những cách đó làm ID dễ bị lộ qua XSS, logs, telemetry hoặc mã frontend.

Ở frontend cùng origin, browser tự gửi cookie. Với frontend khác origin, `fetch` cần cấu hình `credentials` phù hợp và CORS/cookie policy đúng; các vấn đề đó **khác** với việc xoay ID khi login.

### 8.2. Mỗi tab có ID riêng không?

Thông thường các tab trong cùng browser profile chia sẻ cookie cho cùng domain/path. Đổi session ID ở một tab có thể khiến request của tab khác chịu ảnh hưởng nếu đang gửi cookie cũ hoặc request chạy đồng thời.

Trên ứng dụng có nhiều AJAX request, hãy kiểm thử ranh giới login/logout với nhiều tab và request concurrent. Không tự xoay ID ở mọi API request nhằm “tăng an toàn”: việc này dễ tạo race và 401 ngẫu nhiên.

## 9. JSON login tùy chỉnh: phải tự gọi SessionAuthenticationStrategy

Một lỗi thực tế là viết controller:

~~~java
Authentication authentication = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(username, password));

SecurityContextHolder.getContext().setAuthentication(authentication);

// Thiếu sessionAuthenticationStrategy.onAuthentication(...)
// Có thể thiếu securityContextRepository.saveContext(...)
~~~

Đây chỉ là **đoạn minh họa chưa độc lập**, thể hiện lỗi thiết kế. `AuthenticationManager.authenticate(...)` xác minh credential; nó **không tự bảo đảm** custom controller chạy logic đổi session ID và lưu kết quả để dùng cho request sau.

Trong Spring Security 6, khi tự xác thực, cần gọi session strategy phù hợp **sau khi xác thực thành công** và lưu `SecurityContext` vào repository:

~~~java
// Pseudocode Java/Spring: các dependency được inject từ cấu hình thật.
Authentication authentication = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        input.username(), input.password()));

sessionAuthenticationStrategy.onAuthentication(
    authentication, servletRequest, servletResponse);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(
    context, servletRequest, servletResponse);
~~~

Nếu dùng `ChangeSessionIdAuthenticationStrategy` thì phần logic trọng tâm là `HttpServletRequest.changeSessionId()` đối với session hiện có. Tuy nhiên trong ứng dụng thật, session strategy có thể bao gồm thêm CSRF token rotation, concurrency-control và session registration. Đừng tự thay toàn bộ composite bằng lời gọi đơn lẻ rồi vô tình bỏ các bước quan trọng.

Để implement JSON login an toàn:

- Cấu hình `SessionAuthenticationStrategy` của custom flow phù hợp với session fixation, CSRF và concurrent session requirements.
- Chỉ gọi `onAuthentication` **sau** khi xác thực thành công, trước khi lưu/hoàn tất response.
- Lưu context qua `SecurityContextRepository`; trong Spring Security 6 `SecurityContextHolderFilter` mặc định không tự save mọi thay đổi.
- Giữ CSRF protection cho POST login khi dựa vào session cookie, và cấp token mới sau authentication theo vòng đời CSRF.
- Nếu có thể, dùng filter authentication đã tích hợp sẵn hoặc framework-supported strategy để tránh phải tự điều phối nhiều lifecycle hooks.
- Không tự tạo session ID bằng UUID hay ghi vào `Cookie`; để Servlet container quản lý ID/cookie.

Cũng không nên thay trực tiếp `request.getSession().setAttribute("SPRING_SECURITY_CONTEXT", ...)` làm toàn bộ giải pháp. Cách lưu session/context cần nhất quán với repository và filter chain đã cấu hình.

## 10. Event và listener: quan sát rotation đúng cách

Khi Spring Security thực hiện bảo vệ session fixation, framework có thể xuất bản `SessionFixationProtectionEvent`. Với `changeSessionId()` trên Servlet container tương thích, `HttpSessionIdListener` của Servlet API cũng nhận thông báo đổi ID.

Điểm quan trọng cho vận hành:

| Hook | Nơi xuất hiện | Dùng để làm gì? |
| --- | --- | --- |
| `SessionFixationProtectionEvent` | Spring application context | Quan sát việc Spring Security đã áp dụng bảo vệ khi authentication thành công. |
| `HttpSessionIdListener` | Servlet container | Nhận thông báo ID session bị thay đổi qua cơ chế Servlet. |
| `HttpSessionListener` | Servlet container | Theo dõi tạo/hủy session; không đồng nghĩa mọi rotation luôn là cặp hủy/tạo. |
| HTTP `Set-Cookie` | Browser/network | Kiểm tra browser đã nhận ID session mới và cookie attributes. |

Nếu ứng dụng đăng ký **cả** listener Spring và Servlet, cần tránh đếm đôi cùng một sự kiện login rotation. `changeSessionId` không tạo session mới, nên không suy ra phải có `sessionDestroyed` / `sessionCreated` tương ứng. Ngược lại, `migrateSession`/`newSession` có thể kích hoạt lifecycle khác do có hủy/tạo session.

**Đừng log toàn bộ old/new session ID.** Session ID là credential nhạy cảm. Chỉ nên log thời điểm, loại chiến lược, request correlation ID, trạng thái thành công và các metadata đã được che. Tránh gắn session ID vào URL, analytics hoặc lỗi trả về cho client.

## 11. Bảo vệ cookie và session ngoài fixation

Thay ID lúc login là cần thiết nhưng chưa đủ. Với Spring Boot, có thể thiết lập các thuộc tính cookie cho môi trường HTTPS production:

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.timeout=30m
~~~

Các giá trị là **ví dụ cần điều chỉnh theo kiến trúc**. `SameSite=Lax` thường có ích nếu frontend và backend cùng site; khi thật sự cross-site phải xem lại mô hình cookie, CORS, CSRF và chính sách third-party cookie của browser.

Một checklist production:

| Lớp | Biện pháp | Session fixation có thay thế không? |
| --- | --- | --- |
| Kênh truyền | HTTPS end-to-end phù hợp, không gửi session cookie qua HTTP | **Không.** |
| Cookie | `HttpOnly`, `Secure`, `SameSite`, `Path`/`Domain` hạn chế phạm vi | **Không.** |
| XSS | Escape output, CSP phù hợp, tránh script injection | **Không.** |
| CSRF | Token/kiểm tra request cho các thao tác thay đổi state | **Không.** |
| Session fixation | Đổi ID khi nâng quyền xác thực | Đây là biện pháp trực tiếp. |
| Logout | Invalidate session, xóa context và cookie theo policy | **Không.** |
| Timeout | Idle timeout/absolute lifetime theo nguy cơ | **Không.** |
| Quyền | Authorization theo principal/authority, kiểm tra mỗi request | **Không.** |
| Session store | Quản lý clustered session, replication, Redis nếu cần | **Không.** |
| Giám sát | Theo dõi lỗi đăng nhập, bất thường phiên, không ghi ID bí mật | **Không.** |

**Gợi ý:** nếu ứng dụng cho phép user chuyển từ role thường sang role nhạy cảm sau re-authentication, cần đánh giá cả bước **privilege elevation**. Một số luồng nghiệp vụ cần xoay session ID khi nâng mức bảo đảm hoặc thay principal, chứ không chỉ tại lần form login đầu tiên. Không được chỉ giả định framework tự xoay ID cho mọi chuyển quyền do ứng dụng tự thực hiện.

## 12. Lỗi thường gặp và cách xử lý

### Lỗi 1: Thấy ID đổi sau login nên nghĩ “session bị mất”

Với `changeSessionId()`, **ID đổi còn thuộc tính ứng dụng vẫn tồn tại**. Nếu dữ liệu bị mất, kiểm tra ứng dụng có dùng `newSession()`, có tự invalidate session, có listener xóa attributes, có session store bị reset, hoặc browser gửi nhầm cookie hay không.

Không tắt fixation để “giữ nguyên JSESSIONID”. Nên sửa lifecycle/session handling.

### Lỗi 2: Chọn migrateSession nhưng session-scoped bean có hành vi lạ

Vì session cũ bị vô hiệu và session mới được tạo với thuộc tính được copy, các callback `HttpSessionBindingListener` hoặc sự kiện session lifecycle có thể chạy khác so với `changeSessionId`. Nếu có object quản lý resource trong session, hãy kiểm thử rõ callback bind/unbind và khả năng copy. Trên Servlet hiện đại, cân nhắc `changeSessionId()` nếu cần giữ nguyên attributes với ít tác động.

### Lỗi 3: Dùng newSession rồi mất giỏ hàng

`newSession()` không tự copy ordinary app attributes. Nếu giỏ hàng là yêu cầu nghiệp vụ, hãy chọn `changeSessionId()`/`migrateSession()` hoặc làm bước chuyển dữ liệu **được xác thực và kiểm tra**. Cũng xem có dữ liệu untrusted pre-login cần bỏ hay không.

### Lỗi 4: JSON login trả 200 nhưng session ID không xoay

Kiểm tra custom controller/filter có gọi `SessionAuthenticationStrategy.onAuthentication(...)` không. Spring Security 6 không mặc định chạy `SessionManagementFilter` để phát hiện mọi custom login. Nếu gọi thủ công `SecurityContextHolder.setContext(...)` mà quên strategy, việc bảo vệ fixation có thể không diễn ra.

### Lỗi 5: JSON login trả 200, request sau vẫn 401

Một lỗi khác: context chỉ được đặt trong thread hiện tại mà chưa được lưu bằng `SecurityContextRepository.saveContext(...)`. Đây là vấn đề **persistence** khác với fixation; có thể xảy ra đồng thời. Kiểm tra cookie, repository, session policy, proxy và browser credentials.

### Lỗi 6: Dùng STATELESS cho web login bằng session

`SessionCreationPolicy.STATELESS` làm Spring Security không sử dụng session để lấy `SecurityContext`. Đó là lựa chọn cho API stateless chứ không phải cách xoay session ID của web form login. Hãy tách API token và Web session thành các chain có matcher và session policy riêng nếu ứng dụng dùng nhiều cơ chế.

### Lỗi 7: Có Set-Cookie nhưng session không duy trì

Kiểm tra `Secure` trên môi trường HTTP, `SameSite`/domain/path, cross-origin `fetch credentials`, reverse proxy và cấu hình session store. Việc đổi ID không thể làm browser tự gửi cookie vốn bị chính sách browser chặn.

### Lỗi 8: Nhầm 401/302 sau logout với fixation

Logout thường invalidate session, yêu cầu login lại. Rotation lúc login làm ID cũ mất hiệu lực. Cả hai có thể dẫn tới redirect/401 khi request dùng ID cũ, nhưng **nguyên nhân và cách test khác nhau**. Dùng mốc “trước login / sau login / sau logout” và kiểm tra response + cookie, không suy đoán từ status.

### Lỗi 9: Bật listener và đếm đôi sự kiện

Một lần đổi ID bằng `changeSessionId` có thể phát sinh `SessionFixationProtectionEvent` cùng `HttpSessionIdListener`. Đếm cả hai thành “hai lần login” sẽ làm sai metric. Chọn một nguồn chuẩn hoặc khử trùng lặp.

### Lỗi 10: Đưa session ID vào log để debug

Đừng log full `Cookie`, `Set-Cookie` hoặc raw session IDs. Khi cần kiểm thử luân chuyển ID, so sánh trong test nội bộ thay vì sao chép secret. Nếu buộc phải có correlation, tạo request ID không nhạy cảm riêng; không sử dụng session ID làm request-tracking ID công khai.

### Lỗi 11: Xoay ID ở mọi request thay vì lúc nâng quyền

Nhiều request song song từ trình duyệt có thể dùng cookie cũ ngay khi một request vừa đổi ID; xoay liên tục dễ gây race và logout/401 ngẫu nhiên. Session fixation protection nên gắn với **authentication success** hoặc một sự kiện nâng quyền được thiết kế rõ, không gắn vào `OncePerRequestFilter` trên mọi request.

### Lỗi 12: Tin rằng copy toàn bộ attributes luôn an toàn

Dữ liệu session trước login có thể do user ẩn danh tác động. Sau login, app phải xác thực mọi dữ liệu được chuyển trước khi dùng trong hành động nhạy cảm. `migrateSession` chỉ nói về *bảo toàn attributes*, không chứng nhận tính an toàn của chúng.

## 13. QA matrix: kiểm tra đủ các trường hợp

| Mã | Thiết lập | Hành vi cần quan sát |
| --- | --- | --- |
| FIX-01 | Có session ẩn danh trước login, password đúng | ID trước/sau khác với `changeSessionId`. |
| FIX-02 | Có session ẩn danh trước login, password sai | Không nâng phiên thành authenticated. |
| FIX-03 | Đăng nhập thành công, GET tiếp theo | ID không tự đổi ở mọi GET. |
| FIX-04 | Dùng ID trước login qua client HTTP test riêng | Không được truy cập bằng danh tính vừa đăng nhập. |
| FIX-05 | `changeSessionId()` với `cartDraft` | ID đổi, dữ liệu vẫn còn. |
| FIX-06 | `migrateSession()` với `cartDraft` | Session mới, ID mới, dữ liệu được chuyển. |
| FIX-07 | `newSession()` với `cartDraft` | Session mới, ID mới, ordinary attribute không tự chuyển. |
| FIX-08 | `none()` trong môi trường học tập cô lập | Chứng minh không có rotation như chiến lược khác; **không deploy**. |
| FIX-09 | JSON login custom | Gọi strategy và save context đúng thứ tự; ID xoay và request sau authenticated. |
| FIX-10 | Logout sau login | Phiên authenticated bị invalidate; không truy cập bằng cookie cũ. |
| FIX-11 | Browser nhiều tab / nhiều request | Không mất session ngẫu nhiên do tự xoay ID sai chỗ. |
| FIX-12 | Production HTTPS, cookie bảo mật | Browser gửi cookie mới đúng `Path`/`SameSite`/`Secure`. |
| FIX-13 | Session listener/event | Event không đếm đôi; không lộ old/new ID. |
| FIX-14 | API có bearer token stateless | Không phụ thuộc HTTP session để lấy `SecurityContext`. |

Với mỗi test, phân biệt **ID session**, **dữ liệu session**, **SecurityContext**, **session cookie** và **trạng thái xác thực**. Một phép thử chỉ nhìn response `200` không đủ để xác nhận session fixation đã được ngăn chặn.

## 14. Những giới hạn cần nhớ

- **Đổi ID không xóa dữ liệu người dùng.** Với `changeSessionId`, mục tiêu là bỏ định danh có thể đã bị biết trước, không phá session.
- **Không giải quyết mọi chiếm đoạt phiên.** Nếu ID mới bị đánh cắp sau login, vẫn cần HTTPS, HttpOnly, XSS defense, timeout và phát hiện bất thường.
- **Không thay thế CSRF.** Cookie vẫn có thể được browser đính kèm tự động vào request; token CSRF cần được quản lý đúng.
- **Không giống refresh token rotation.** HTTP session ID là định danh phiên do Servlet container quản lý; OAuth2 access/refresh token có vòng đời và cách thu hồi riêng.
- **Không tự động áp dụng cho mọi custom login.** Trong Spring Security 6, custom filter/controller phải phối hợp SessionAuthenticationStrategy và SecurityContextRepository.
- **Không có nghĩa chỉ có một session.** Concurrent session control là tính năng độc lập; mỗi browser/device có thể có phiên riêng theo policy.
- **Không bảo đảm kiểm soát mạng phân tán.** Nếu cluster có nhiều node, cần session store/replication đúng. Chỉ xoay ID trên một node mà store/cookie không nhất quán vẫn gây lỗi.
- **Không nên tắt vì sự tiện lợi.** Nếu rotation làm lộ lỗi state handling, sửa logic chuyển dữ liệu và cookie thay vì bật `none()`.

## 15. Tổng kết

**Session fixation xuất hiện khi định danh phiên có thể bị biết trước được giữ nguyên qua ranh giới đăng nhập.** Spring Security ngăn nguy cơ này bằng cách xoay session ID khi xác thực thành công.

- `changeSessionId()`: **khuyến nghị mặc định trên Servlet hiện đại**; thay ID trên session hiện có, giữ attributes.
- `migrateSession()`: thay session, chuyển toàn bộ attributes; cần kiểm thử listener và dữ liệu pre-login.
- `newSession()`: thay session và không copy ordinary application attributes; vẫn có thể giữ thuộc tính Spring Security cần thiết.
- `none()`: tắt fixation protection, không khuyến nghị cho web session-based.
- `SessionCreationPolicy.STATELESS`: chính sách cho API không dựa trên session, **khác** việc lựa chọn chiến lược đổi ID.
- Form login chuẩn tích hợp session strategy; **JSON login tự viết phải gọi strategy và lưu SecurityContext** nếu sử dụng HTTP session.

Cách xác minh đáng tin nhất là **tạo session ẩn danh trước login, đăng nhập đúng, so sánh ID cũ/mới và kiểm tra phiên mới đã xác thực**, đồng thời xác nhận attributes còn/mất đúng chính sách và cookie cũ không được chấp nhận trong integration test.

### Tài liệu tham khảo

- Spring Security Reference 6.5 — Authentication Persistence and Session Management (Session Fixation Protection): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security Reference 6.5 — Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security Reference 6.5 — Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security Reference 6.5 — Testing with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html
- Spring Security Reference 6.5 — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Jakarta Servlet API — HttpServletRequest.changeSessionId(): https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpservletrequest
- OWASP Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
