# Session fixation và các chiến lược đổi định danh phiên

> **Ngữ cảnh:** Spring Security 6 trên **Servlet stack** (Spring Boot 3.x, Java 17+). Bài này giải thích tấn công *session fixation*, nguyên tắc thay đổi session ID sau khi xác thực thành công, so sánh bốn chiến lược `changeSessionId`, `migrateSession`, `newSession` và `none`, cùng việc tích hợp vào form login hoặc luồng đăng nhập tùy chỉnh. Tập trung vào `HttpSession` và cookie phiên; không áp dụng nguyên xi cho Spring WebFlux.

## 1. Vấn đề: session ID được tạo trước khi đăng nhập có thể bị lợi dụng

**Session fixation** xảy ra khi kẻ tấn công khiến nạn nhân dùng một **session identifier mà attacker đã biết hoặc kiểm soát** trước lúc nạn nhân xác thực. Nếu sau khi đăng nhập, server **giữ nguyên session ID**, attacker có thể dùng ID đã biết để truy cập phiên giờ đây mang danh tính nạn nhân.

Hình dung một luồng không bảo vệ:

```text
(1) Attacker biết session ID S0
       |
       | cố làm nạn nhân sử dụng S0
       v
(2) Browser nạn nhân gửi cookie phiên S0
       |
       v
(3) Nạn nhân đăng nhập thành công
       |
       v
(4) Server gắn Authentication vào phiên S0
    nhưng KHÔNG đổi ID
       |
       v
(5) Attacker dùng S0 để truy cập tài nguyên
    với Authentication của nạn nhân
```

Đây là **mô hình đe dọa**, không phải mặc định mọi ứng dụng đều có thể bị ép nhận session ID của attacker: khả năng “fix” ID còn phụ thuộc cookie domain/path, cách server nhận ID, subdomain, URL rewriting, XSS, reverse proxy và nhiều điều kiện khác.

**Phòng thủ chính:** khi ranh giới danh tính đổi từ chưa xác thực sang đã xác thực, ứng dụng phải **xoay vòng hoặc thay thế session ID**, khiến ID trước đăng nhập không còn đại diện cho phiên có quyền mới. Session ID mới phải được trao cho client hợp lệ qua cơ chế cookie/session an toàn.

**Ghi nhớ:** Đổi mật khẩu hoặc băm password không thay thế session fixation protection. Tấn công không cần đoán mật khẩu; nó lợi dụng phiên được nâng quyền nhưng vẫn giữ ID cũ.

## 2. Session ID, HttpSession, SecurityContext: ba thứ khác nhau

Trong ứng dụng Servlet:

- `HttpSession` là đối tượng phiên phía server, có ID, thời gian timeout và attributes, thường được truy cập qua `HttpServletRequest.getSession(...)`.
- `JSESSIONID` thường là tên cookie đưa **session ID** về trình duyệt, nhưng tên cookie có thể tùy biến. Cookie này không nhất thiết chứa trực tiếp username, mật khẩu hay `Authentication`.
- `SecurityContext` chứa `Authentication` của người dùng; khi ứng dụng dùng `HttpSessionSecurityContextRepository`, context có thể được lưu vào một attribute của `HttpSession` để request sau nạp lại.

```text
Browser
  |
  | Cookie: JSESSIONID=S1
  v
Servlet container
  |
  +--> tìm HttpSession theo ID S1
        |
        +--> session attributes ("cart", "locale", ...)
        |
        +--> SecurityContext (nếu được lưu)
                |
                +--> Authentication
                        principal / authorities
```

**Session ID không phải Authentication.** Một session trước khi đăng nhập có thể tồn tại chỉ vì giao diện, giỏ hàng, CSRF token hoặc request cache. Sau đăng nhập, cùng một `HttpSession` hoặc một phiên mới có thể chứa `SecurityContext` đã xác thực. Chính thời điểm **nâng cấp trạng thái** đó là lúc cần bảo vệ session fixation.

Thay session ID **không đồng nghĩa** xóa giỏ hàng hay khởi tạo lại mọi attribute; việc có giữ dữ liệu cũ hay không phụ thuộc chiến lược.

## 3. Phân biệt session fixation với các rủi ro khác

| Rủi ro | Cơ chế chính | Biện pháp tương ứng |
| --- | --- | --- |
| **Session fixation** | Attacker biết ID trước login; ứng dụng giữ ID đó sau login | Rotate/replace ID sau authentication |
| **Session hijacking** | Attacker đánh cắp ID **đã có quyền** qua XSS, log, mạng, máy khách | HTTPS, Secure/HttpOnly/SameSite theo threat model, XSS defense, bảo vệ log, thu hồi phiên |
| **Session prediction** | ID dễ đoán hoặc sinh kém ngẫu nhiên | Container/session store sinh ID entropy cao |
| **CSRF** | Browser tự gửi cookie với request do website khác kích hoạt | CSRF token, SameSite, kiểm soát nguồn request |
| **Session replay** | ID hợp lệ bị sử dụng lại khi chưa bị thu hồi | Logout/invalidation, expiry, revocation, ràng buộc truy cập phù hợp |
| **Session fixation qua URL rewriting** | ID được truyền trong URL và có thể bị chia sẻ/ghi log | Ưu tiên cookie, hạn chế URL-based session tracking |

Một hệ thống có thể rotate ID đúng lúc login nhưng vẫn bị hijacking nếu cookie bị đánh cắp sau login. Ngược lại, dùng HTTPS nhưng giữ nguyên ID bị attacker biết từ trước vẫn có thể có fixation risk. **Cần phòng thủ nhiều lớp.**

## 4. Spring Security thực hiện bảo vệ ở đâu?

Trên Servlet stack, các cơ chế authentication chuẩn của Spring Security có thể áp dụng **`SessionAuthenticationStrategy`** sau khi xác thực thành công, trước khi phản hồi thành công hoàn tất.

```text
POST /login (credentials + CSRF token)
        |
        v
UsernamePasswordAuthenticationFilter
        |
        v
AuthenticationManager.authenticate(...)
        |
        +--> thất bại: failure handler; không nâng quyền phiên
        |
        +--> thành công:
               |
               v
        SessionAuthenticationStrategy.onAuthentication(...)
               |
               +--> session fixation protection
               |    đổi ID hoặc tạo phiên mới theo policy
               |
               +--> các session strategies khác (nếu cấu hình)
               |
               v
        tạo/đặt SecurityContext đã xác thực
               |
        lưu context vào repository khi flow yêu cầu
               |
        success handler / redirect / response
```

Sơ đồ mô tả luồng điển hình của form login trong Spring Security 6; thứ tự và thành phần cụ thể của một ứng dụng có thể phụ thuộc authentication filter và config. Điểm quan trọng là **đổi ID sau khi xác thực thành công**, không chỉ đổi khi vào trang login, không làm mỗi request bình thường và không coi `HttpSession` là đã xác thực chỉ vì nó tồn tại.

### Vì sao chọn đúng hook quan trọng?

Nếu một controller tự viết `POST /my-login` rồi chỉ gọi:

```java
Authentication authentication =
        authenticationManager.authenticate(loginToken);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

// ĐÂY CHƯA PHẢI custom login hoàn chỉnh.
```

thì việc `AuthenticationManager` trả Authentication hợp lệ **không tự** bảo đảm các `SessionAuthenticationStrategy` sẽ chạy. Ở chế độ explicit save, còn cần `SecurityContextRepository.saveContext(...)` để giữ đăng nhập qua request sau. Hãy dùng filter chuẩn khi có thể; nếu thật sự có custom flow, thực hiện đầy đủ lifecycle.

## 5. Bốn chiến lược session fixation protection

Spring Security cung cấp DSL trong `HttpSecurity`:

```java
http.sessionManagement(session -> session
        .sessionFixation(fixation -> fixation.changeSessionId()));
```

Có thể thay `changeSessionId()` bằng `migrateSession()`, `newSession()` hoặc `none()` tùy yêu cầu tương thích/chính sách. Các câu lệnh này là **các lựa chọn thay thế**, không gọi bốn phương thức liên tiếp trong cùng cấu hình.

| Chiến lược | Xử lý session ID | Xử lý attributes hiện có | Khi cân nhắc |
| --- | --- | --- | --- |
| **`changeSessionId()`** | Dùng `HttpServletRequest.changeSessionId()` (Servlet 3.1+) để đổi ID trên phiên hiện có | Thông thường **giữ nguyên attributes và đối tượng session** | **Ưu tiên mặc định** trên Servlet container hiện đại; ít xáo trộn dữ liệu |
| **`migrateSession()`** | Vô hiệu hóa session cũ, tạo session mới với ID mới | **Sao chép** attributes từ session cũ sang mới | Hệ thống tương thích môi trường cũ hơn hoặc cần tạo session mới nhưng giữ state |
| **`newSession()`** | Vô hiệu hóa session cũ và tạo session mới | **Không mang theo thông thường các application attributes**, ngoài các attributes liên quan Spring Security theo cơ chế thư viện | Khi muốn tách mạnh state trước/sau login, chấp nhận mất giỏ hàng/preferences trừ khi phục hồi có chủ đích |
| **`none()`** | Không đổi ID để chống fixation | Giữ state theo flow hiện tại | Chỉ khi có lý do bảo mật được chứng minh bên ngoài; **không nên dùng cho browser login có session** |

### 5.1. changeSessionId: đổi ID nhưng không hủy HttpSession hiện có

Trên Servlet 3.1+:

```java
http.sessionManagement(session -> session
        .sessionFixation(fixation -> fixation.changeSessionId()));
```

Khi đã có session ID `S0` trước khi đăng nhập, một lần authentication thành công sẽ yêu cầu container đổi nó thành `S1`. Ứng dụng thường giữ nguyên attributes như `cart` hoặc `locale`, đồng thời ID cũ không còn là ID hợp lệ cho session được nâng quyền.

```text
Trước login:
  HttpSession{id=S0, cart="book-42"}

Sau login:
  HttpSession{id=S1, cart="book-42", SecurityContext=...}
                     ^
                     đổi ID, giữ dữ liệu giỏ hàng
```

Đây là lựa chọn thông thường phù hợp khi muốn giữ trải nghiệm giỏ hàng trước khi login. Spring Security dùng cơ chế này làm chiến lược mặc định trên Servlet container hỗ trợ `changeSessionId` (như môi trường Boot Servlet hiện đại).

**Không nhầm đổi ID với tạo một phiên đối tượng mới.** `changeSessionId` đổi ID của phiên đã có; vì vậy những hệ thống gắn dữ liệu/metrics theo session ID cần lắng nghe sự kiện thay đổi ID và cập nhật liên kết phù hợp.

### 5.2. migrateSession: tạo session mới và di chuyển state

```java
http.sessionManagement(session -> session
        .sessionFixation(fixation -> fixation.migrateSession()));
```

Luồng điển hình:

```text
Session cũ S0: cart="book-42", locale="vi-VN"
     |
     +--> invalidate S0
     +--> create new session S1
     +--> copy attributes phù hợp
     v
Session mới S1: cart="book-42", locale="vi-VN"
```

Điểm mạnh: giữ dữ liệu trước đăng nhập trong môi trường cần tạo session mới. Điểm cần chú ý: invalidate session cũ rồi copy/rebind attributes có thể gây tác dụng phụ cho đối tượng triển khai `HttpSessionBindingListener` hoặc tích hợp container/framework cũ. Cần test giỏ hàng, session-backed caches, Spring Session hoặc các listeners của ứng dụng.

Khác `changeSessionId`, đây là quy trình thay **session object** và chuyển state, không chỉ đổi identifier.

### 5.3. newSession: tạo phiên sạch hơn sau authentication

```java
http.sessionManagement(session -> session
        .sessionFixation(fixation -> fixation.newSession()));
```

Với `newSession`, ứng dụng không tự động mang theo **application attributes** thông thường từ phiên trước đăng nhập (chẳng hạn `cart`, `wizardStep` hoặc `uiDraft`). Spring Security có thể giữ những attributes nội bộ của nó theo contract. Vì vậy không diễn giải `newSession()` là “xóa sạch mọi byte liên quan Spring Security”.

**Khi nào dùng?** Nếu dữ liệu nặc danh trước login không đáng tin và không muốn gộp trực tiếp vào phiên có quyền mới. Ví dụ quy trình nhạy cảm quy định phải tạo state hoàn toàn mới sau login. Đổi lại, UI có thể mất giỏ hàng hoặc bước đang làm nếu không có cơ chế phục hồi được thiết kế riêng.

**Không vô tình chọn `newSession` rồi báo lỗi “giỏ hàng tự biến mất”** mà không nhận ra đó là behavior được yêu cầu.

### 5.4. none: tắt bảo vệ fixation của chiến lược

```java
http.sessionManagement(session -> session
        .sessionFixation(fixation -> fixation.none()));
```

Điều này **tắt hành vi session fixation protection do chiến lược này cung cấp**. Nếu ứng dụng vẫn giữ một session ID trước và sau login, việc này có thể mở lại rủi ro fixation. Chỉ cân nhắc khi có bằng chứng kiến trúc rõ ràng rằng session fixation được kiểm soát bằng biện pháp tương đương khác và đã được review.

**Không dùng `none()` để “sửa” lỗi mất session** nếu nguyên nhân thật là cookie/path/domain, CSRF, reverse proxy, custom login thiếu saveContext, hoặc application state được gắn với ID cũ. Hãy điều tra trước và giữ cơ chế đổi ID.

## 6. Các tình huống chi tiết dễ bị nhầm

### 6.1. Trước login chưa có HttpSession thì sao?

Session fixation protection cần một **session ID cũ** để xoay vòng. Nếu client chưa có session nào trước khi authenticate, không tồn tại `S0` để thay. Một số flow tạo session mới khi lưu context hoặc tạo CSRF token; những tình huống này phụ thuộc `SessionCreationPolicy` và repository.

**Test fixation phải chủ động tạo phiên trước login**, ghi lại ID cũ, rồi đăng nhập trong **cùng phiên**. Nếu chỉ login từ request không có session trước đó, thấy cookie mới không chứng minh code đã bảo vệ trường hợp có session bị cố định.

### 6.2. Đổi session ID có nghĩa user đã login thành công không?

Không thể suy ngược một cách tổng quát. Có những tác nhân khác thay session ID; và session fixation strategy có thể không chạy khi không có session cũ. Muốn xác minh login, cần kiểm tra `Authentication` đã được lưu/nạp đúng, authorization cho phép endpoint bảo vệ, và cookie được gửi lại.

### 6.3. Có cần đổi ID ở mỗi HTTP request không?

**Không.** Mục tiêu là đổi khi có biến cố tăng mức tin cậy, thường là lần xác thực thành công. Đổi ID trên mọi GET có thể làm session persistence, client concurrency và nhiều tab khó hoạt động, tăng tải container và làm sai quan sát.

Khi chuyển vai trò/quyền hoặc thực hiện bước xác thực nhạy cảm, việc rotate thêm có thể phù hợp theo threat model, nhưng không được thay thế cơ chế bảo vệ lúc login.

### 6.4. Session ID đổi có làm hỏng CSRF token không?

CSRF token và session ID là hai thứ khác nhau. Với cơ chế Spring Security phổ biến, khi authentication thành công, `CsrfAuthenticationStrategy` có thể xóa token CSRF cũ để token mới được cấp; do đó form hoặc SPA có thể phải **lấy lại CSRF token sau login**. Đừng nhầm việc token đổi với chỉ riêng session fixation strategy.

Nếu một ứng dụng dùng custom login, hãy tích hợp CSRF/session strategy theo policy thay vì tự động tắt CSRF để form hoạt động.

### 6.5. Session ID cũ có còn truy cập được không?

Trong flow session fixation protection đúng, ID trước login phải **không còn đại diện cho phiên đã xác thực**. Với `changeSessionId` container phải map session sang ID mới; với `migrateSession`/`newSession` phiên cũ bị invalidated. Cần test trên container/session store thực tế nếu ứng dụng dùng session cluster, reverse proxy hoặc Spring Session.

**Không chấp nhận** hiện tượng dùng song song ID cũ và ID mới đều truy cập cùng phiên authenticated, trừ khi đang quan sát một lỗi hạ tầng cần khắc phục. Đặc biệt phải bảo vệ session ID khỏi URL/log và response cache.

### 6.6. Đổi ID có đồng nghĩa logout các phiên khác không?

Không. Rotation ID của **một session** sau login không tự thu hồi mọi session khác của cùng một user. Nếu muốn giới hạn đăng nhập đồng thời hoặc logout mọi thiết bị, cần `SessionRegistry`, session management/persistence hoặc cơ chế revoke riêng phù hợp triển khai.

## 7. Dự án chạy được: form login mặc định và đổi session ID

Dùng **Java 17+**, **Spring Boot 3.3.5 / Spring Security 6.x**, **Gradle 8.5**. Ví dụ có ba endpoint:

- `GET /visit`: cho phép chưa login, chủ động tạo `HttpSession` và lưu `cart="book-42"`.
- `POST /login`: form login do Spring Security xử lý; sau khi xác thực thành công, dùng `changeSessionId`.
- `GET /me` và `GET /cart`: chỉ người đã xác thực truy cập; chứng minh ID đã đổi và dữ liệu cũ được giữ.

Dự án **không tự viết filter login** vì có cơ chế chuẩn; đây cũng là cách tránh quên `SessionAuthenticationStrategy` hoặc `SecurityContextRepository`.

### 7.1. Cây thư mục

```text
session-fixation-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/test/java/demo/
    SessionFixationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'session-fixation-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 7.2. Ứng dụng chính

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 7.3. SecurityConfig: giữ CSRF, dùng changeSessionId

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("study123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/visit").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form.permitAll())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.IF_REQUIRED)
                        .sessionFixation(fixation ->
                                fixation.changeSessionId()))
                .build();
    }
}
```

Giải thích:

1. `formLogin` tạo login page mặc định và xử lý `POST /login`; không cần custom controller cho endpoint này.
2. `SessionCreationPolicy.IF_REQUIRED` cho phép có session khi cần. Dù cấu hình không ghi tay repository, authentication filter chuẩn của form login đảm nhận context persistence theo cơ chế Spring Security 6.
3. `sessionFixation(...changeSessionId())` yêu cầu đổi ID khi có phiên trước khi authentication thành công.
4. Không cấu hình `csrf.disable()`: với form login sử dụng session cookie, CSRF là phòng thủ quan trọng; test phải cung cấp CSRF token hợp lệ cho `POST /login`.
5. Mật khẩu học tập được băm bằng BCrypt trước khi `InMemoryUserDetailsManager` dùng; production phải quản lý tài khoản/bí mật đúng policy thay vì hard-code.

**Lưu ý:** Ví dụ chỉ giới thiệu login/session fixation. Với sản phẩm thật, cần chính sách session timeout, cookie security, phân quyền, logout, CSRF, chống password guessing và kiểm thử nhiều container.

### 7.4. Controller tạo phiên nặc danh trước login

`src/main/java/demo/DemoController.java`:

```java
package demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/visit")
    public String visit(HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        session.setAttribute("cart", "book-42");
        return "visit-ok";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/cart")
    public String cart(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session == null) {
            return "missing-session";
        }
        return String.valueOf(session.getAttribute("cart"));
    }
}
```

`/visit` tạo session trước khi user xác thực và lưu một attribute mẫu. Vì `/visit` có `permitAll()`, client không bị bắt đăng nhập tại đây. `/cart` chỉ người đã xác thực mới truy cập được; sau login, nếu `changeSessionId` giữ dữ liệu giỏ hàng, body là `book-42`.

### 7.5. MockMvc: kiểm tra ID cũ và mới

`src/test/java/demo/SessionFixationTest.java`:

```java
package demo;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionFixationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulLoginChangesSessionIdButKeepsCart()
            throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(get("/visit").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("visit-ok"));

        String beforeLoginId = session.getId();

        MvcResult result = mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", "learner")
                        .param("password", "study123"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        HttpSession loggedInSession =
                result.getRequest().getSession(false);

        assertNotNull(loggedInSession);
        assertNotEquals(beforeLoginId, loggedInSession.getId());
        assertEquals("book-42",
                loggedInSession.getAttribute("cart"));

        // Request độc lập sau login: cùng session đã đổi ID.
        mvc.perform(get("/me")
                        .session((MockHttpSession) loggedInSession))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"));

        mvc.perform(get("/cart")
                        .session((MockHttpSession) loggedInSession))
                .andExpect(status().isOk())
                .andExpect(content().string("book-42"));
    }

    @Test
    void anonymousCannotAccessProtectedEndpoint() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void missingCsrfTokenRejectsFormLogin() throws Exception {
        mvc.perform(post("/login")
                        .session(new MockHttpSession())
                        .param("username", "learner")
                        .param("password", "study123"))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordDoesNotAuthenticate() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", "learner")
                        .param("password", "wrong"))
                .andExpect(status().is3xxRedirection());

        mvc.perform(get("/me").session(session))
                .andExpect(status().is3xxRedirection());
    }
}
```

**Kết quả kỳ vọng cho cấu hình demo:** 4 tests PASS. Test đầu là bằng chứng chính: ta **chủ động có session trước login**, lấy ID `beforeLoginId`, đăng nhập thành công, rồi so sánh nó với ID sau login, đồng thời kiểm tra attribute `cart` còn tồn tại và request thứ hai được xác thực. Test không dùng `@WithMockUser`, vì annotation đó có thể tạo sẵn Authentication mà **không chạy qua login/session fixation strategy**.

**Lưu ý về MockMvc:** MockMvc mô phỏng request/session cho unit/integration test phía Spring MVC. Nó chứng minh lifecycle ở tầng ứng dụng, nhưng không thay thế kiểm thử browser/cookie/container thực khi deploy, nhất là hệ thống dùng load balancer, Redis/Spring Session hoặc nhiều node.

### 7.6. Chạy dự án

Từ thư mục `session-fixation-demo`, cài JDK 17+ và Gradle tương thích, rồi:

```bash
gradle test
gradle bootRun
```

Nếu có Gradle Wrapper, dùng `./gradlew test` và `./gradlew bootRun` (macOS/Linux), hoặc `.\gradlew.bat test` và `.\gradlew.bat bootRun` (Windows).

Để tự quan sát qua trình duyệt tại `http://localhost:8080`:

1. Mở `/visit` để tạo phiên nặc danh và đặt attribute `cart`.
2. Mở `/login`, dùng `learner` / `study123`. Trang login mặc định do Spring Security sinh ra có trường CSRF token ẩn trong form.
3. Đăng nhập, sau đó vào `/me`; body dự kiến là `learner`.
4. Vào `/cart`; body dự kiến `book-42`.
5. Trong DevTools Network/Application, đối chiếu session cookie trước và sau login. **Giá trị ID là runtime, không đoán sẵn**; cookie có thể được cập nhật qua header Set-Cookie.
6. Không chia sẻ giá trị cookie hoặc session ID thật trong tài liệu/screenshot/log.

Có thể dùng `curl` với cookie jar nhưng phải lấy và gửi **CSRF token thực** của form `GET /login` khi POST; không thể hard-code một token dùng chung. Browser demo tự gửi hidden form field đúng theo trang được tạo. Nếu chỉ gọi POST `/login` không có CSRF token, kết quả thường là 403, không phải bằng chứng session fixation strategy hỏng.

## 8. Muốn đổi sang migrateSession hoặc newSession: làm gì?

Trên cùng dự án, chỉ thay **một dòng cấu hình**:

```java
// Biến thể A: tạo phiên mới, sao chép attributes
.sessionFixation(fixation -> fixation.migrateSession())

// Biến thể B: tạo phiên mới, không giữ application attributes thông thường
.sessionFixation(fixation -> fixation.newSession())

// Biến thể C: vô hiệu cơ chế fixation-protection của chiến lược
.sessionFixation(fixation -> fixation.none())
```

Đây là **những fragment thay thế**, không phải ba dòng cần đặt cùng lúc trong Java.

Đối với `migrateSession`, kiểm thử phải xác nhận session ID khác và `cart` vẫn có giá trị nếu attribute được di chuyển. Đối với `newSession`, ID phải khác nhưng `cart` thường **không còn** trong phiên mới. Đối với `none`, một phiên nặc danh có sẵn có thể giữ nguyên ID qua login, là một **anti-pattern** nếu không có lớp bảo vệ tương đương.

Đừng sửa assertion `assertNotEquals` thành `assertEquals` chỉ để “làm test PASS” khi vô hiệu hóa protection. Test nên ghi nhận ý nghĩa an ninh: nếu chính sách yêu cầu đổi ID thì `none` phải **bị coi là sai yêu cầu**, không phải behavior hợp lệ ngang hàng.

### Session data và listener

Với `migrateSession`, khi invalidating/copy session, các đối tượng lắng nghe `HttpSessionBindingListener` có thể nhận bind/unbind callbacks; sự kiện có thể ảnh hưởng đến dữ liệu của ứng dụng. Khi chuyển từ `migrateSession` sang `changeSessionId`, test các session attribute consumers, listeners và hệ thống session store thay vì chỉ xem status 200.

Nếu application sử dụng session state để bảo quản workflow/giỏ hàng, hãy chọn phương án giữ data phù hợp và test **identity** của session trước–sau trên container thực.

## 9. Custom login: phải tự gọi SessionAuthenticationStrategy

Trong Spring Security 6, các filter authentication chuẩn thường biết gọi session strategy ở lifecycle thành công. Nếu bạn tự viết controller gọi `AuthenticationManager.authenticate(...)`, phải đảm bảo **session strategy và persistence** được thực hiện đầy đủ.

Một fragment Java theo thứ tự khuyến nghị:

```java
// Mã minh họa BÊN TRONG custom login handler đã có dependency.
Authentication verified = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password));

// Session fixation/concurrency/CSRF strategies theo cấu hình của ứng dụng.
sessionAuthenticationStrategy.onAuthentication(
        verified, request, response);

SecurityContext context =
        SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

// Trong explicit-save flow, lưu trước khi response commit/redirect.
securityContextRepository.saveContext(context, request, response);

// Chỉ sau đó mới trả response thành công hoặc redirect.
```

Mã trên **không** là chương trình độc lập; `username`, `password`, `request`, `response` và dependencies cần được cung cấp bởi handler thực tế. Đừng copy nó thay cho `formLogin()` chuẩn khi chưa cần custom login.

Một bean strategy chỉ để minh họa cách thay ID:

```java
@Bean
SessionAuthenticationStrategy customLoginSessionStrategy() {
    return new ChangeSessionIdAuthenticationStrategy();
}
```

Đây là fragment cần import `@Bean`, `SessionAuthenticationStrategy` và `ChangeSessionIdAuthenticationStrategy`. **Lưu ý:** nếu thay thế composite strategy của một flow đã hỗ trợ concurrency control/CSRF, chỉ dùng `ChangeSessionIdAuthenticationStrategy` đơn lẻ có thể bỏ sót các chức năng đó. Trên một application thực, phối hợp strategy fixation với `CsrfAuthenticationStrategy` và các session strategies khác theo policy.

### Vì sao thứ tự quan trọng?

- Nếu save `SecurityContext` vào session **trước** khi đổi ID/invalidate session theo chiến lược di trú, có thể xuất hiện behavior khó kiểm soát hoặc mất context trong cấu hình custom.
- Nếu commit response/redirect **trước** khi save context, session cookie có thể không được cập nhật đúng.
- Nếu authentication thất bại, không chạy luồng thành công và không gắn một `Authentication` không hợp lệ vào session được cho là đã xác thực.
- Nếu gọi cùng session strategy **hai lần** (framework filter và controller), session có thể bị xoay vòng nhiều hơn cần thiết và gây lỗi cookies/attributes.
- Nếu bạn chỉ thay đổi `SecurityContextHolder` nhưng không save trong `requireExplicitSave(true)`, request sau có thể mất login dù session ID đã đổi thành công.

Với custom authentication filter, có thể sử dụng `AuthenticationFilter`/`AbstractAuthenticationProcessingFilter` và các extension points của Spring Security để được xử lý success/failure rõ ràng. Tự viết controller login cần thêm kế hoạch cho remember-me, success handler, saved request, session concurrency, CSRF và logout; **session fixation strategy không thay thế chúng**.

## 10. SessionAuthenticationStrategy và chính sách concurrent sessions

`SessionAuthenticationStrategy` là contract áp dụng sau khi một authentication được coi là thành công:

```java
void onAuthentication(Authentication authentication,
                      HttpServletRequest request,
                      HttpServletResponse response)
        throws SessionAuthenticationException;
```

Chữ ký trên là API minh họa, không phải Java class độc lập. `SessionAuthenticationException` là một loại lỗi liên quan quản lý phiên, có thể xảy ra khi policy concurrent sessions từ chối tạo thêm phiên.

Một ứng dụng có thể cần **composite session strategy** để làm nhiều việc ở ranh giới login: quản lý giới hạn phiên, session fixation protection, đăng ký phiên và xử lý CSRF token. Không suy ra chỉ vì đã gọi `changeSessionId` thì ứng dụng đã:

- giới hạn một user chỉ đăng nhập một thiết bị;
- invalidated mọi session cũ sau đổi password;
- giải quyết session timeout;
- chống CSRF;
- tự thu hồi cookie của browser khác.

Nếu ứng dụng có `SessionRegistry`, Spring Session hoặc cluster, việc đổi ID cần tương thích với cách lưu và đồng bộ trạng thái phiên. Kiểm thử riêng những chuyển đổi này, đặc biệt khi hệ thống ghi session ID vào một mapping/cơ sở dữ liệu phụ.

## 11. SessionCreationPolicy và tác động lên fixation

| Policy | Ý nghĩa liên quan `HttpSession` | Lưu ý fixation |
| --- | --- | --- |
| `ALWAYS` | Spring Security tạo session theo policy | Nếu có phiên trước login, vẫn cần rotation |
| `IF_REQUIRED` | Tạo session khi cần | Thường gặp ở form login; không tự bảo đảm mọi custom login gọi strategy |
| `NEVER` | Spring Security không tạo session mới nhưng có thể dùng session đã tồn tại | **Không đồng nghĩa stateless**; nếu dùng session có trước rồi login, vẫn phải phân tích fixation |
| `STATELESS` | Spring Security không tạo/dùng session để lấy `SecurityContext` | Nếu thực sự không lưu auth trong session, fixation của **auth session** không phải cơ chế chính; vẫn kiểm tra những session do code khác tạo |

`STATELESS` không cấm một servlet/controller khác tạo `HttpSession`. Chỉ cho thấy Spring Security không dựa vào session để khôi phục authentication theo policy ấy. Nếu ứng dụng sử dụng bearer token/JWT đúng kiểu stateless, session fixation của cookie login không phải mối đe dọa cùng hình thức; thay vào đó chú ý replay/revocation token, XSS, storage và CSRF tùy cách gửi credential.

**Một lỗi suy luận:** thấy response có `JSESSIONID` rồi kết luận chắc chắn Spring Security lưu Authentication ở đó. Cookie có thể do CSRF, MVC, request cache hoặc code ứng dụng. Hãy kiểm tra repository và request sau chỉ mang session cookie (không Basic/form credentials) để chứng minh authentication persistence.

## 12. Sự kiện khi đổi session ID và hệ thống phụ trợ

Trên Servlet container hỗ trợ `HttpServletRequest.changeSessionId()`, container có thể phát sự kiện ID thay đổi cho những `HttpSessionIdListener` đã đăng ký:

```java
// Mẫu signature để minh họa callback Servlet:
@Override
public void sessionIdChanged(
        HttpSessionEvent event, String oldSessionId) {
    String newId = event.getSession().getId();
    // Đồng bộ mapping có kiểm soát nếu ứng dụng có dữ liệu phụ theo ID.
}
```

Đây là **fragment** bên trong một listener implements `jakarta.servlet.http.HttpSessionIdListener`, không phải file độc lập. Sự kiện Spring Security `SessionFixationProtectionEvent` cũng có thể được publish theo luồng strategy tương ứng.

Các hệ thống phụ dễ bị bỏ sót:

1. **Audit/session registry** ghi session ID cũ: cần hiểu sự kiện đổi ID để không tưởng user “biến mất” hoặc ghi trùng phiên.
2. **Spring Session/Redis cluster:** kiểm thử giá trị session ID mới được lưu và đồng bộ; xem tác động replication/race.
3. **Load balancer sticky session:** nếu bám vào session ID hoặc cookie, cần bảo đảm chuyển ID vẫn route đúng node.
4. **Giỏ hàng và workflow state:** với `migrateSession`/`newSession`, test attributes còn hay mất đúng chính sách.
5. **WebSocket/SSE hoặc request song song nhiều tab:** một request có ID cũ đúng thời điểm chuyển ID có thể gặp race; không cho phép dùng lại session cũ như một cách “tạm thời” vô hạn.
6. **CSRF token/cookie:** frontend phải cập nhật token/session cookie mới sau login, không dùng ID/token trước đăng nhập.

Không ghi **giá trị session ID** vào logs/metrics công khai. Nếu cần tương quan audit, dùng identifier nội bộ không phải bearer credential hoặc cách biểu diễn không thể dùng lại để truy cập phiên.

## 13. Logout, idle timeout và thay mật khẩu: không thay cho fixation protection

### Logout

Logout chuẩn thường clear `SecurityContext`, invalidate session và có thể xóa cookie theo cấu hình. **Rotate ID lúc login không thay thế invalidate lúc logout.** Nếu browser tiếp tục mang cookie cũ, server cần từ chối hoặc xử lý như một session không còn quyền.

### Idle timeout

Một session được rotate có thể vẫn hết hạn theo timeout. Timeout không phải cách phòng chống fixation trực tiếp: nếu ID cũ được dùng để nâng quyền trong khoảng thời gian hợp lệ, rủi ro tồn tại dù session cuối cùng có expire. Cần cả timeout và rotation.

### Thay đổi mật khẩu hoặc khóa tài khoản

Một session đã có `Authentication` có thể vẫn còn hợp lệ sau khi account đổi password/disabled, nếu ứng dụng không revalidate/revoke session. Rotation ở lần login không giải quyết **session revocation** về sau. Hãy có policy rõ ràng cho đăng xuất các thiết bị hoặc yêu cầu đăng nhập lại sau thay đổi nhạy cảm.

### Cookie security

Với production: dùng HTTPS, cookie `Secure`/`HttpOnly`/`SameSite` phù hợp, domain/path hạn chế, tránh URL rewriting cho session identifier khi không cần, và phòng thủ XSS/CSRF. Session ID nên do Servlet container/session framework uy tín sinh ngẫu nhiên; không tự dùng username, email, timestamp hay token đoán được làm ID.

## 14. Những lỗi triển khai thường gặp

| Hiện tượng / cách làm sai | Vấn đề | Cách khắc phục |
| --- | --- | --- |
| Login thành công mà ID không đổi dù đã có session trước đó | Session fixation protection bị tắt, custom flow chưa gọi strategy hoặc chain sai | Kiểm tra `sessionFixation(...)`, authentication filter, session strategy và test trước–sau |
| Chỉ chạy test khi không có session trước login | Không có ID cũ để phát hiện fixation | Tạo session nặc danh trước login rồi so ID |
| Dùng `none()` để giữ giỏ hàng | Nguy cơ giữ ID trước login | Chọn `changeSessionId()` hoặc `migrateSession()` để vừa đổi ID vừa giữ attributes |
| Dùng `newSession()` rồi mất giỏ hàng | Không chuyển application attributes theo policy | Chọn chiến lược khác hoặc chuyển data có chọn lọc sau xác minh |
| Custom controller chỉ gọi `AuthenticationManager` | Không tự kích hoạt đầy đủ session strategy và persistence | Gọi strategy và `saveContext`, hoặc dùng filter chuẩn |
| Dùng `changeSessionId` nhưng cookie mới không được client lưu | Client/proxy/cookie config sai | Kiểm tra Set-Cookie, domain/path, Secure, SameSite và redirect |
| Đổi ID mỗi HTTP request | Session/cookie race, không cần thiết | Rotate ở auth boundary và các thời điểm nâng quyền có chủ đích |
| Viết session ID vào query parameter | Có thể bị ghi log/chia sẻ/đọc từ history | Dùng cookie có bảo vệ; hạn chế URL rewriting |
| Nhầm CSRF token bị đổi với session ID | Hai cơ chế khác nhau, có thể cùng xảy ra sau login | Kiểm tra từng token và lấy CSRF token mới khi cần |
| Logout chỉ `SecurityContextHolder.clearContext()` | Session đã lưu có thể vẫn chứa authentication | Dùng logout/invalidate context/session đúng policy |
| Session cookie trước login hoạt động sau login như một phiên authenticated | Có thể là lỗ hổng fixation nếu ID thật sự không đổi | Test tái sử dụng ID cũ trên container và xử lý theo security policy |
| App có nhiều SecurityFilterChain, kiểm tra nhầm chain | Một chain có protection, chain khác không | Test theo từng matcher/`@Order` và cơ chế login thực tế |

## 15. Checklist kiểm thử bảo mật

Một bộ kiểm thử nên chứng minh:

- **Before login:** truy cập endpoint public, tạo session nặc danh và lưu dữ liệu `cart` mẫu; ghi lại ID `S0`.
- **Login đúng:** gửi `POST /login` với credentials và CSRF hợp lệ; xác thực thành công.
- **After login:** lấy session ID `S1`, xác nhận `S1 != S0` trong chính sách `changeSessionId`/`migrateSession`/`newSession`.
- **Attribute policy:** `changeSessionId` và `migrateSession` giữ dữ liệu hợp lệ; `newSession` không tự chuyển application attributes thông thường.
- **ID cũ:** trên container thật, ID `S0` không thể truy cập phiên đã xác thực.
- **Request sau:** session cookie mới truy cập được endpoint bảo vệ mà không cần gửi lại credentials, nếu cấu hình session-based.
- **Login sai:** authentication thất bại không tạo phiên có quyền mới; session fixation strategy không được coi là thành công.
- **CSRF:** thiếu token ở POST login bị từ chối khi CSRF bật; token mới được quản lý đúng sau login.
- **Logout:** session đã xác thực bị invalidated theo policy, cookie/session ID cũ không còn cung cấp quyền.
- **Các chain:** xác định đúng session policy trên từng `SecurityFilterChain`; không suy luận từ kết quả của một URL duy nhất.
- **Infrastructure:** test trên container/browser/proxy/session store production-like, không chỉ MockMvc.

Đừng chỉ assert `response.status == 302` của login: một redirect có thể là thất bại, và chỉ status 200 không chứng minh ID đã đổi. Test nên kiểm tra **session trước–sau, context đã xác thực và dữ liệu phiên** như ví dụ.

## 16. Tự kiểm tra

1. **Session fixation là gì?** Attacker khiến nạn nhân dùng một session ID mà attacker đã biết trước login; nếu ID giữ nguyên sau login, attacker có thể dùng ID ấy để lợi dụng phiên đã nâng quyền.
2. **Vì sao đổi session ID sau login giúp giảm rủi ro?** ID cũ không còn chỉ tới phiên authenticated, nên attacker biết ID trước login không tự truy cập được.
3. **`changeSessionId()` khác `migrateSession()` ở đâu?** `changeSessionId` dùng API Servlet đổi ID của session hiện có; `migrateSession` invalidate session cũ và tạo session mới, copy attributes.
4. **`newSession()` có giữ toàn bộ giỏ hàng không?** Không; không chuyển application attributes thông thường, dù có thể giữ attributes nội bộ Spring Security.
5. **`none()` có an toàn cho browser session login không?** Thông thường không nếu không có biện pháp tương đương khác; nó tắt fixation protection của chiến lược.
6. **Tại sao test nên tạo session trước login?** Phải có session ID `S0` để chứng minh nó bị thay thế; đăng nhập lần đầu chưa có session không kiểm tra đúng rủi ro fixation.
7. **Spring Security `formLogin` có thường tích hợp session strategy không?** Có; authentication filter chuẩn xử lý nó trong luồng authentication thành công.
8. **Custom controller chỉ gọi `SecurityContextHolder.setContext` đã đủ chưa?** Chưa; có thể phải gọi `SessionAuthenticationStrategy.onAuthentication` và `SecurityContextRepository.saveContext` trong explicit-save flow.
9. **Nếu session ID đổi, có nghĩa mọi phiên khác đã logout?** Không, session fixation rotation chỉ liên quan phiên đang xác thực.
10. **STATELESS có cần session fixation rotation cho login session-based không?** Nếu thật sự không có auth session được dùng, mối đe dọa fixation của phiên auth không áp dụng giống session-based; vẫn phải đánh giá các phiên khác do ứng dụng tạo.
11. **HTTPS có tự bảo vệ khỏi fixation không?** Không hoàn toàn; TLS bảo vệ truyền tải nhưng không sửa lỗi server giữ nguyên session ID bị attacker biết trước login.
12. **Có nên thay đổi chiến lược để giữ UI state mà không test security?** Không. Chọn policy theo bảo mật và hành vi dữ liệu, kiểm thử cả ID mới lẫn attribute migration.

**Ghi nhớ:** Session fixation protection bảo vệ **thời điểm nâng quyền của phiên**. Với Servlet container hiện đại, ưu tiên `changeSessionId()`: đổi session ID sau authentication thành công nhưng thường giữ attributes. `migrateSession()` tạo phiên mới và di chuyển state; `newSession()` tách application state trước/sau login; `none()` tắt protection và cần cực kỳ thận trọng. Nếu tự viết login, phải tích hợp `SessionAuthenticationStrategy` và việc lưu `SecurityContext` đúng lifecycle. Kiểm thử bằng **một phiên nặc danh trước login và phiên authenticated sau login**, không chỉ xem status HTTP.
