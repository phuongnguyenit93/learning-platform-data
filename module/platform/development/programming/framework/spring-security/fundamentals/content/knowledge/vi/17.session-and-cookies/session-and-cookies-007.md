# Session fixation và lý do đổi định danh phiên sau đăng nhập

> **Chủ đề:** Spring Security – fundamentals → **Phiên và cookie**. Bài này giải thích **session fixation** (cố định phiên), vì sao một người dùng phải được cấp **session ID mới khi xác thực thành công**, Spring Security bảo vệ mặc định như thế nào, cách chọn `changeSessionId` / `migrateSession` / `newSession`, và cách viết kiểm thử để biết cơ chế có hoạt động thật hay không. Trọng tâm là **Servlet + Spring MVC + Spring Security 6 / Spring Boot 3.x**, kèm so sánh với các kiến trúc stateless và reactive.

## 1. Tư duy nền tảng: session ID là “chìa khóa” của phiên

HTTP vốn không nhớ các request độc lập. Một ứng dụng đăng nhập bằng form thường dùng **server-side session** để liên kết các request tiếp theo với danh tính đã xác thực:

1. Server tạo một `HttpSession`, gắn với một session identifier ngẫu nhiên, khó đoán.
2. Server gửi identifier về browser, thường qua cookie `JSESSIONID` khi dùng Servlet container mặc định. Nếu dùng Spring Session hoặc cấu hình khác, tên có thể là `SESSION` hay tên tùy chỉnh.
3. Browser gửi lại cookie khi truy cập cùng site theo chính sách cookie.
4. Server tra identifier → dữ liệu session (bao gồm hoặc liên kết tới `SecurityContext` / `Authentication`, tùy cấu hình).
5. Nếu identifier được server chấp nhận và session có authentication hợp lệ, request được coi là thuộc phiên đăng nhập.

Sơ đồ giản lược:

```text
Browser                                      Server
  |  GET /public                            |
  |---------------------------------------->|
  |  Set-Cookie: JSESSIONID=SID_A; ...      |  Session SID_A
  |<----------------------------------------|  chưa đăng nhập
  |                                         |
  |  POST /login + credentials              |
  |  Cookie: JSESSIONID=SID_A               |
  |---------------------------------------->|
  |  Login thành công                       |  SecurityContext / Authentication
  |  Set-Cookie: JSESSIONID=SID_B; ...      |  Phiên gắn với SID_B
  |<----------------------------------------|
  |                                         |
  |  GET /account                           |
  |  Cookie: JSESSIONID=SID_B               |
  |---------------------------------------->|
  |  Nội dung riêng của user                |
  |<----------------------------------------|
```

**Điểm an toàn bắt buộc:** `SID_A` (định danh trước đăng nhập) và `SID_B` (định danh được sử dụng sau khi đăng nhập) **phải khác nhau** trong tình huống có phiên trước khi xác thực và chiến lược chống fixation hoạt động. Dữ liệu session không nhất thiết bị xóa; **điều cần cắt đứt là khả năng tiếp tục dùng identifier cũ để truy cập phiên sau xác thực**.

Một session ID không phải mật khẩu, nhưng là **bearer secret**: ai nắm identifier còn hợp lệ và trình bày nó cho server có thể được đối xử như chủ phiên nếu không có kiểm soát thêm. Bảo vệ session ID tương tự bảo vệ credential.

## 2. Session fixation là gì?

**Session fixation** xảy ra khi attacker khiến nạn nhân **sử dụng một session identifier mà attacker đã biết hoặc kiểm soát trước khi nạn nhân đăng nhập**, rồi lợi dụng việc server giữ nguyên identifier ấy sau xác thực.

Kịch bản tư duy:

1. Attacker mở ứng dụng và có được một session ID trước đăng nhập, ví dụ `SID_FIXED`.
2. Qua một kênh yếu (URL rewriting chứa session ID, cookie injection trên domain/subdomain bị kiểm soát, cấu hình proxy/cookie sai, XSS hay cơ chế chấp nhận session ID do client áp đặt), attacker khiến browser của nạn nhân gửi `SID_FIXED` tới ứng dụng. **Khả năng gắn session vào browser nạn nhân là tiền điều kiện, không mặc định xảy ra ở mọi site.**
3. Nạn nhân đăng nhập bằng tài khoản của chính họ.
4. Nếu ứng dụng **giữ nguyên** `SID_FIXED` và nâng cấp phiên đó thành authenticated session, attacker có thể tiếp tục gửi `SID_FIXED` để được nhận dạng như nạn nhân.
5. Attacker không cần biết mật khẩu nạn nhân, vì identifier đã trở thành “chìa khóa” của phiên đã login.

Minh họa lỗi:

```text
Attacker biết SID_FIXED
           |
           v
Victim browser bị gắn SID_FIXED
           |
           v
Victim đăng nhập thành công
           |
           v
[Ứng dụng yếu] SID_FIXED vẫn trỏ tới authenticated session
           |
           v
Attacker dùng SID_FIXED → có thể mạo danh victim
```

Minh họa phòng vệ:

```text
Attacker biết SID_FIXED
           |
           v
Victim đăng nhập với SID_FIXED
           |
           v
[Spring Security] đổi session ID thành SID_NEW
           |
           +--> SID_FIXED không còn là khóa hợp lệ cho phiên xác thực
           |
           v
Victim dùng SID_NEW; attacker chỉ biết SID_FIXED → không vào được
```

**Khác với session hijacking (đánh cắp phiên):** Với hijacking, attacker có thể lấy được **session ID đang hợp lệ sau đăng nhập**, ví dụ qua malware, XSS, traffic không được mã hóa hoặc log rò rỉ. Với fixation, attacker **biết ID từ trước**, tìm cách để ID đó vẫn có hiệu lực sau đăng nhập. **Đổi ID lúc login là biện pháp chính chống fixation**, nhưng không chặn mọi dạng đánh cắp cookie sau login; cần HTTPS, cookie flags, XSS defense, logout, timeout và các biện pháp khác.

### 2.1. Điều kiện và giới hạn của kịch bản tấn công

Không phải website nào cũng cho client chỉ định session ID tùy ý. Servlet container thường chỉ chấp nhận ID tương ứng một session có thật; URL chứa `;jsessionid=...` chỉ hoạt động khi cơ chế URL rewriting liên quan được bật/chấp nhận. Việc browser nhận cookie do subdomain đặt cũng phụ thuộc `Domain`, host-only cookie, cookie prefixes, chính sách trình duyệt và trạng thái site. Vì vậy không thể nói “gửi một link bất kỳ là luôn chiếm được phiên”.

Mục tiêu phòng vệ không phải dựa vào việc “khó gắn cookie nên an toàn”, mà là tạo **ranh giới xác thực**: một identifier của phiên anonymous **không được biến thành token của phiên authenticated** khi người dùng đăng nhập thành công.

## 3. Vì sao phải đổi ID *sau khi* đăng nhập?

### 3.1. Thời điểm nâng cấp đặc quyền (privilege elevation)

Trước login, cùng session có thể lưu giỏ hàng, preference, URL cần quay lại, anti-CSRF token hoặc trạng thái cho trang công khai. Sau login, session trở thành nơi server tra lại authentication và/hoặc state có đặc quyền cao hơn. Đó là lúc **đối tượng có quyền truy cập phiên thay đổi mức độ quan trọng**.

Nếu identifier không đổi, bất kỳ ai đã biết nó từ giai đoạn anonymous đều có cơ hội dùng nó như một authenticated bearer credential. Nếu ID được đổi sang giá trị mới chỉ nạn nhân nhận qua kết nối an toàn, attacker giữ ID cũ sẽ không có quyền đi cùng trạng thái đăng nhập.

Quan hệ logic:

```text
Trước:
SID_OLD → session anonymous

Login được chấp nhận + session fixation protection:
SID_OLD ✕ không còn dùng để truy cập phiên authenticated
SID_NEW → cùng dữ liệu session được giữ (tùy strategy) + authentication
```

Lý do **không chỉ đổi ở logout**: lúc nạn nhân vừa login chính là cửa sổ nguy hiểm. Nếu đợi logout mới đổi thì attacker vẫn có thời gian sử dụng SID cũ. Lý do **không chỉ đổi cookie trên frontend**: server cũng phải hủy hiệu lực mapping của ID cũ. Thay chuỗi cookie ở browser mà server vẫn coi ID cũ hợp lệ không đủ.

### 3.2. Đổi ID khác “xóa toàn bộ dữ liệu phiên”

Giả sử khách chưa login có `cartId=42` và `theme=dark` trong session. Sau login có thể vẫn cần giữ giỏ hàng. **Luân chuyển ID** không bắt buộc phải xóa những attribute này.

- `changeSessionId`: đổi identifier trên session hiện hữu, thường giữ các attribute vì không thay đối tượng session.
- `migrateSession`: tạo session mới, sao chép các attribute từ session cũ.
- `newSession`: tạo session sạch hơn, không di chuyển tùy tiện dữ liệu ứng dụng; các attribute Spring Security cần thiết vẫn có thể được giữ theo cơ chế framework.

Do vậy yêu cầu UX “giữ giỏ hàng” không phải lý do để vô hiệu hóa fixation protection. Chọn chiến lược phù hợp và chủ động kiểm soát những trạng thái anonymous nào được phép “đi tiếp” vào phiên authenticated.

### 3.3. Login thất bại có đổi ID không?

Mặc định, chiến lược fixation được thực hiện khi **authentication thành công**, không phải chỉ vì request mang tên `/login`. Một lần nhập sai mật khẩu không có ý nghĩa “nâng quyền” như login thành công. Tuy nhiên, hệ thống có thể có policy khác để đổi ID theo trigger riêng; luôn test flow thực tế thay vì suy luận từ URL.

## 4. Spring Security xử lý session fixation ra sao?

Ở **Servlet/Spring MVC**, Spring Security có cơ chế chống session fixation trong luồng xác thực có session. Với Servlet 3.1+ (bao gồm các Servlet container hiện đại dùng trong Boot 3.x), lựa chọn mặc định phổ biến là **`changeSessionId`**. <cite>Đối chiếu Spring Security Reference mục Authentication Persistence and Session Management.</cite>

Trình tự chức năng chuẩn:

```text
GET trang public
  |
  v
Tồn tại session trước login? (có thể có hoặc không)
  |
  v
Form login filter kiểm tra username/password
  |
  +--> Thất bại: không nâng đặc quyền
  |
  +--> Thành công:
          |
          v
       SessionAuthenticationStrategy (login filter tích hợp)
          |
          v
       Session fixation protection
          |
          v
       Session ID được đổi hoặc session mới được tạo
          |
          v
       SecurityContext được lưu cho các request tiếp theo
          |
          v
       Response gửi session cookie phù hợp tới browser
```

**Lưu ý phiên bản:** Trong Spring Security 6, `SessionManagementFilter` **không còn được mặc định cài trong filter chain** theo cách cũ; các authentication mechanism như form login chịu trách nhiệm gọi `SessionAuthenticationStrategy`. Vì vậy, với custom authentication filter/controller, không thể luôn trông chờ `SessionManagementFilter` tự phát hiện login và đổi session ID. Cần tích hợp strategy + persistence đúng cách.

### 4.1. Bốn chiến lược và lựa chọn mặc định

| DSL trong `sessionFixation` | Điều gì xảy ra | Dữ liệu phiên ứng dụng | Khi nào phù hợp |
|---|---|---|---|
| `changeSessionId()` | Servlet gọi `HttpServletRequest.changeSessionId()` trên session đang có, không thay object session | Giữ các attribute | Mặc định phổ biến trên Servlet 3.1+; thường là lựa chọn tốt nhất cho app hiện đại |
| `migrateSession()` | Invalidate session cũ, tạo session mới và chuyển attribute | Thông thường sao chép toàn bộ các attribute | Cần di chuyển dữ liệu session, hoặc tương thích container cũ; cần quan tâm lifecycle listener |
| `newSession()` | Tạo session mới “sạch” hơn thay cho session cũ | Không sao chép attribute ứng dụng tùy tiện; attribute bảo mật nội bộ có thể được giữ | Muốn cô lập state anonymous trước/sau login |
| `none()` | Không luân chuyển ID qua Spring Security fixation strategy | Giữ session/ID cũ theo cơ chế đang dùng | **Không khuyến nghị**, trừ trường hợp đã có cơ chế tương đương được chứng minh và test |

**Chính xác hơn:** `changeSessionId()` cần Servlet container hỗ trợ API từ Servlet 3.1; nếu dùng container quá cũ không có API này, Spring Security có thể dùng `migrateSession` làm mặc định. Việc chọn strategy không tự tạo ra session trong mọi trường hợp: cần session hiện hữu hoặc policy tạo session phù hợp. Với login mà trước đó chưa có session, so sánh “ID trước/ID sau” không có ý nghĩa như một luân chuyển từ ID cũ.

### 4.2. Cấu hình thường dùng trong Spring Security 6

Đoạn Java bên dưới là **method @Bean** đặt trong class `@Configuration` hoặc cấu hình Boot; không phải tệp độc lập:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**", "/login").permitAll()
            .anyRequest().authenticated())
        .formLogin(form -> form.permitAll())
        .sessionManagement(session -> session
            .sessionFixation(fixation -> fixation.changeSessionId()))
        .build();
}
```

Khi ứng dụng chạy trên Servlet container hiện đại, bản thân Spring Security thường đã dùng protection này mặc định. Việc khai báo tường minh có ích khi học, kiểm toán hoặc muốn tránh mơ hồ trong config.

Đổi sang `newSession`:

```java
.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.newSession()))
```

Đổi sang `migrateSession`:

```java
.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.migrateSession()))
```

**Đừng dùng `.none()` để “sửa” vấn đề session, iframe, login loop hoặc cookie sai**. Những vấn đề ấy cần truy nguyên session store, cookie Path/Domain/Secure/SameSite, proxy, HTTPS và filter chain. Vô hiệu hóa fixation protection là đổi một triệu chứng UX thành rủi ro chiếm phiên.

### 4.3. SessionCreationPolicy có liên quan nhưng không đồng nghĩa

Các giá trị quen thuộc:

- `ALWAYS`: Spring Security tạo session.
- `IF_REQUIRED`: tạo session khi cần; thường phù hợp với form login.
- `NEVER`: Spring Security không tự tạo session, nhưng vẫn có thể dùng session đã tồn tại do thành phần khác tạo.
- `STATELESS`: Spring Security không tạo hoặc dùng `HttpSession` để lấy `SecurityContext` theo semantics của policy; thường hợp với bearer token / stateless API được thiết kế đúng.

**`STATELESS` không phải “phiên hiện hữu không cần đổi ID nhưng vẫn lưu authentication trong đó”**. Nếu authentication thực sự stateless, không có server-side authenticated session dựa vào cookie thì cơ chế cố định `JSESSIONID` để leo vào phiên ấy không áp dụng theo cùng cách. Nhưng vẫn phải bảo vệ bearer token, refresh token, cookie chứa token và đăng nhập/đổi quyền theo thiết kế tương ứng.

Không đặt `STATELESS` vào form-login session demo rồi mong lần sau browser vẫn authenticated chỉ nhờ `JSESSIONID`: hai kiến trúc có hợp đồng khác nhau.

## 5. Ví dụ đầy đủ: Spring Boot 3.x / Java 17+ / form login

Ta xây một ứng dụng có một endpoint **tạo session trước login**. Sau login thành công, test phải chứng minh:

1. ID của session trước login đã thay đổi.
2. Attribute hợp lệ `draftColor` vẫn được giữ với `changeSessionId`.
3. Request sau login dùng session mới và nhận đúng tên user.
4. Request chưa xác thực không được vào endpoint riêng.

Ví dụ dùng user in-memory để tự chạy, mật khẩu `{noop}` **chỉ dành cho môi trường học cục bộ**. Không dùng cách lưu password này trong sản phẩm thật.

### 5.1. Tạo project Gradle

Tạo project với **Spring Initializr**, Java 17+, Spring Boot 3.x, chọn *Spring Web* và *Spring Security*. Khối `dependencies` trong `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây chỉ là khối dependencies của project Boot đã có plugin, repository và toolchain; không dùng nó như file `build.gradle` độc lập.

### 5.2. Tệp Java chạy được

Tạo `src/main/java/example/sessionfix/SessionFixationDemoApplication.java`:

```java
package example.sessionfix;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SessionFixationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionFixationDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/login").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form.permitAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                .sessionFixation(fix -> fix.changeSessionId()))
            .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}demo123")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}

@RestController
class DemoController {

    @GetMapping("/public/bootstrap")
    public String bootstrap(HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        // Dữ liệu công khai trước khi login, muốn giữ sau login.
        session.setAttribute("draftColor", "blue");
        return "anonymous session ready";
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication,
                                  HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        String draft = session == null
            ? "missing" : String.valueOf(session.getAttribute("draftColor"));
        return Map.of(
            "username", authentication.getName(),
            "draftColor", draft);
    }
}
```

**Đọc cấu hình:**

- `/public/**` và `/login` có thể truy cập trước đăng nhập. `/api/me` yêu cầu authenticated.
- `formLogin(...)` dùng form-login filter của Spring Security, **không phải controller tự xác thực bằng tay**.
- `SessionCreationPolicy.IF_REQUIRED` cho phép framework dùng session cần cho form login.
- `changeSessionId()` là cơ chế tự động luân chuyển ID **khi có session trước đó và đăng nhập thành công**.
- `GET /public/bootstrap` chủ động tạo `HttpSession` để bài kiểm thử có một ID trước login.
- `GET /api/me` không trả ID nhạy cảm qua JSON; chỉ trả username và một attribute công khai đã biết. Trong ứng dụng thật cũng không nên log/trả session token ra client.
- Không disable CSRF trong config. Form login POST phải gửi CSRF token hợp lệ; test dùng `csrf()` helper.

**Lưu ý:** Không có Controller mapping cho `GET /login` ở đây; Spring Security dựng trang login mặc định. Form đăng nhập gửi `POST /login`, username/password theo tên field mặc định. Nếu project thật có custom login page, authentication provider, SSO, reverse proxy hoặc nhiều filter chains, cần test riêng các path và session strategy thực tế.

### 5.3. Chạy ứng dụng và quan sát trong browser

Trong project có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Các bước quan sát thủ công trong môi trường phát triển:

1. Mở cửa sổ trình duyệt mới ở `http://localhost:8080/public/bootstrap`. Kiểm tra body `anonymous session ready`.
2. Mở Developer Tools → **Application/Storage → Cookies**. Với embedded Servlet container mặc định, thường thấy `JSESSIONID`. **Chỉ xem giá trị trong máy local, không chụp/gửi session ID thật cho người khác**. Ghi nhận bằng cách so sánh ID cũ và ID mới tại chỗ.
3. Truy cập `/api/me`. Vì chưa login, server hướng đến trang đăng nhập theo form-login entry point.
4. Đăng nhập bằng `alice` / `demo123` tại trang login mặc định.
5. Quan sát session cookie sau xác thực: ID phải **khác** ID đã ghi nhận ở bước 2. Browser gửi cookie mới cho request tiếp theo.
6. Truy cập `http://localhost:8080/api/me`. Body JSON dự kiến có `"username":"alice"` và `"draftColor":"blue"`.
7. Trong DevTools → Network, xem **response headers** ở lần login. Nếu thấy Set-Cookie với ID mới, xác nhận ứng dụng trả cookie thay thế. Các header cụ thể phụ thuộc container, cookie repository và proxy.

Không nên copy một ID thật để gửi vào chat/log, cũng không cần dùng attack demo trên người khác. Với ứng dụng sử dụng Spring Session, tên cookie có thể là `SESSION`, và lịch sử ID cần so theo cơ chế repository thực tế.

### 5.4. Integration test xác nhận ID thay đổi

Tạo `src/test/java/example/sessionfix/SessionFixationDemoTest.java`:

```java
package example.sessionfix;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class SessionFixationDemoTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulLoginRotatesIdButKeepsSafeAttribute()
            throws Exception {

        // Một session anonymous có thật từ controller.
        MvcResult bootstrapped = mvc.perform(get("/public/bootstrap"))
            .andExpect(status().isOk())
            .andExpect(content().string("anonymous session ready"))
            .andReturn();

        MockHttpSession preLoginSession =
            (MockHttpSession) bootstrapped.getRequest().getSession(false);

        assertThat(preLoginSession).isNotNull();
        String oldId = preLoginSession.getId();
        assertThat(preLoginSession.getAttribute("draftColor"))
            .isEqualTo("blue");

        // POST /login: CSRF hợp lệ, tái sử dụng session trước login.
        MvcResult loggedIn = mvc.perform(
                post("/login")
                    .session(preLoginSession)
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo123"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession postLoginSession =
            (MockHttpSession) loggedIn.getRequest().getSession(false);

        assertThat(postLoginSession).isNotNull();
        assertThat(postLoginSession.getId()).isNotEqualTo(oldId);

        // changeSessionId không làm rơi attribute cần giữ.
        assertThat(postLoginSession.getAttribute("draftColor"))
            .isEqualTo("blue");

        // Session đã xác thực được dùng cho request tiếp theo.
        mvc.perform(get("/api/me").session(postLoginSession))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(jsonPath("$.draftColor").value("blue"));
    }

    @Test
    void anonymousCannotReadPersonalEndpoint() throws Exception {
        // Form-login thường trả redirect tới trang /login.
        mvc.perform(get("/api/me"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }
}
```

Chạy:

```bash
./gradlew test
```

Windows: `.\gradlew.bat test`. Đây là **integration test** chạy ứng dụng Spring Boot, MockMvc với security filters và session strategy. Nó không đơn thuần gọi method controller, nên có khả năng phát hiện việc cấu hình login bỏ qua cơ chế đổi ID.

**Giới hạn của test:** `MockHttpSession` mô phỏng Servlet session chứ không thay cho kiểm thử end-to-end qua cookie thật, HTTPS, load balancer hoặc Spring Session store. Trong Servlet container thực, cần thêm test kiểm tra ID cũ không truy cập được session authenticated; có thể dùng browser automation hoặc môi trường test của ứng dụng, không cần biến ví dụ học tập thành công cụ tấn công.

## 6. Thử đổi chiến lược để thấy hành vi khác

Trong class ứng dụng ở mục 5, thay đúng **một** phần của `sessionFixation` và chạy test có kỳ vọng tương ứng.

### 6.1. `changeSessionId()`

```java
.sessionManagement(session -> session
    .sessionFixation(fix -> fix.changeSessionId()))
```

Kỳ vọng khi session tồn tại trước login: ID thay đổi, attribute `draftColor` còn tồn tại. Đây là hành vi test ở mục 5.4.

### 6.2. `migrateSession()`

```java
.sessionManagement(session -> session
    .sessionFixation(fix -> fix.migrateSession()))
```

Kỳ vọng: session cũ bị vô hiệu, session mới được tạo và các attribute ứng dụng được chuyển. Khác `changeSessionId` ở **lifecycle của đối tượng session**: các `HttpSessionBindingListener` hoặc bean có session scope có thể nhận sự kiện remove/add, khiến cleanup hoặc lifecycle callback khác với mong muốn. Cần test giỏ hàng, CSRF storage, saved request, session-scoped object và listener trước khi dùng.

### 6.3. `newSession()`

```java
.sessionManagement(session -> session
    .sessionFixation(fix -> fix.newSession()))
```

Kỳ vọng: ID của phiên sau login khác, nhưng **không kỳ vọng giữ `draftColor`** từ phiên anonymous. Đây không phải lỗi: đó chính là lý do chọn `newSession`. Những attribute nội bộ Spring Security vẫn có thể được giữ theo policy của framework, không được diễn giải là “phiên hoàn toàn không có state”.

### 6.4. `none()`: chỉ phân tích, không dùng cho demo thực

```java
// CẤU HÌNH KHÔNG AN TOÀN NẾU KHÔNG CÓ BIỆN PHÁP THAY THẾ ĐÃ KIỂM CHỨNG:
.sessionManagement(session -> session
    .sessionFixation(fix -> fix.none()))
```

Khi ứng dụng không có cơ chế luân chuyển ID tương đương, lựa chọn này có thể để lại lỗ hổng session fixation. Không đưa cấu hình đó vào hệ thống đang chạy, chỉ dùng để nhận diện nguy cơ trong code review.

## 7. Auth transition và custom login: điểm dễ thiếu cơ chế bảo vệ

### 7.1. Form login mặc định so với authentication thủ công

Spring Security hỗ trợ việc gọi `SessionAuthenticationStrategy` ở authentication mechanism tích hợp. Nhưng hệ thống có thể xác thực bằng:

- Endpoint REST custom nhận credentials rồi lưu `Authentication` vào `SecurityContext`.
- Custom `OncePerRequestFilter`.
- SSO/OAuth2/OIDC callback.
- API gateway chuyển assertion và ứng dụng tự tạo session.
- Flow đăng nhập hai bước hoặc “step-up authentication”.

Nếu tự triển khai login bằng cách tạo `Authentication` và lưu `SecurityContext`, **đừng mặc định việc này đã đổi session ID**. Ở Spring Security 6, những luồng custom cần tích hợp strategy/handler phù hợp, gọi đúng thời điểm authentication thành công, lưu context qua `SecurityContextRepository` và test ID. Chỉ đặt cấu hình `sessionFixation` trên `HttpSecurity` nhưng bypass authentication filters có thể không đạt kết quả mong muốn.

Pseudo-flow minh họa **không phải chương trình độc lập**:

```text
Nhận credential → xác thực thành công (Authentication)
     |
     v
Xử lý session authentication strategy
  - session fixation protection
  - nếu cần: concurrent session control
     |
     v
Lưu SecurityContext theo SecurityContextRepository
     |
     v
Gửi response để client dùng session ID mới
```

Thứ tự chi tiết phụ thuộc authentication framework/version, success handler và transaction/response commitment. Đừng viết custom filter chỉ làm `SecurityContextHolder.setContext(...)` rồi cho rằng phiên đã lưu lâu dài và đã được rotate.

### 7.2. Đăng nhập lại, đổi user, MFA và nâng quyền

Nếu phiên thay đổi đặc quyền (ví dụ user thường chuyển sang vai trò quản trị, hoàn tất MFA, chuyển identity), tổ chức có thể yêu cầu đổi session identifier tại các ranh giới quan trọng khác, không chỉ login đầu tiên. Chính sách phải được thiết kế nhất quán với authentication mechanism và cách app gắn identity. Không tùy ý gọi `changeSessionId()` trên mọi request để “chắc ăn”: làm vậy gây churn, rối client, tăng tải session store và không thay cho kiểm soát identity đúng cách.

### 7.3. Event quan sát khi đổi session ID

Spring Security có thể phát `SessionFixationProtectionEvent` khi protection thực thi. Với `changeSessionId`, Servlet `HttpSessionIdListener` cũng có thể được thông báo. Nếu hệ thống lắng nghe cả hai, tránh xử lý trùng, ví dụ audit “một login = hai lần rotate”. Không log **giá trị session ID thật** như một thông tin debug lâu dài; nếu cần tương quan log, dùng mã sự kiện/trace ID độc lập và bảo vệ dữ liệu trong log.

## 8. Cookie làm gì và không làm gì trong phòng chống fixation?

| Cấu hình cookie | Tác dụng chủ yếu | Nó có thay việc đổi session ID lúc login? |
|---|---|---|
| `HttpOnly` | Hạn chế JavaScript truy cập cookie, giảm một số đường đánh cắp token qua script | **Không** |
| `Secure` | Trình duyệt chỉ gửi cookie trên kết nối HTTPS (với ngoại lệ/chi tiết platform liên quan) | **Không** |
| `SameSite=Lax/Strict/None` | Kiểm soát việc gửi cookie trong ngữ cảnh cross-site, giảm một số CSRF vector | **Không** |
| `Path`/`Domain` chặt | Giới hạn phạm vi gửi/chia sẻ cookie, giảm cookie injection từ miền phụ | **Không** |
| Cookie prefix như `__Host-` nếu áp dụng được | Ràng buộc Secure, Path=/ và không có Domain theo quy tắc trình duyệt | **Không** |
| Session ID rotation khi authentication thành công | Cắt liên hệ giữa identifier trước login với phiên có đặc quyền | **Có — đây là trọng tâm chống fixation** |

Dùng HTTPS xuyên suốt phiên, không gửi auth/session cookie qua HTTP, không cache hoặc log credential, không đặt session ID lên query string. Khi Servlet container hỗ trợ URL rewriting với `;jsessionid=...`, cân nhắc cấu hình **COOKIE-only tracking mode** nếu không có yêu cầu hợp lệ dùng URL-based session tracking, nhằm giảm vô tình lộ ID qua URL, browser history, referer và log.

Ví dụ cấu hình **Spring Boot Servlet** cho môi trường HTTPS (tệp `application.properties`, chỉ là các property liên quan, không phải toàn bộ cấu hình):

```properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.tracking-modes=cookie
server.servlet.session.timeout=30m
```

Điều kiện: cookie `secure=true` cần HTTPS hoặc reverse proxy có xử lý scheme/trust đúng; trên local `http://localhost`, behavior trình duyệt và proxy có thể khác. `SameSite=Lax` không phù hợp với mọi cross-site OIDC/iframe/SSO flow; test theo nhu cầu thực tế. Nếu dùng Spring Session/custom cookie serializer, một số property của container có thể không phải điểm cấu hình duy nhất. Đừng coi properties trên là bộ cấu hình bảo mật hoàn chỉnh.

## 9. CSRF, XSS, logout và timeout không được lẫn với session fixation

### 9.1. CSRF

CSRF lợi dụng việc browser **tự đính kèm** session cookie vào request, để một site khác kích hoạt thao tác trái ý người dùng. Session fixation lợi dụng **identifier được biết trước authentication**. Dù cùng liên quan cookie, cơ chế và kiểm soát không trùng nhau.

- Rotate session ID khi login **không thay thế** CSRF token.
- CSRF token **không thay thế** việc rotate session ID.
- Form login POST và các state-changing requests phải được CSRF protection xử lý theo threat model.
- Khi chạy MockMvc, dùng `with(csrf())` cho POST form login thay vì tắt protection để test đơn giản.

### 9.2. XSS và session hijacking sau login

Cookie `HttpOnly` giúp giảm khả năng script đọc trực tiếp session cookie, nhưng một XSS đang thực thi trong origin hợp lệ vẫn có thể phát request với cookie của người dùng để thực hiện hành động. Rotate ID ở login cũng không thu hồi session ID đã bị lộ **sau login**. Cần output encoding, CSP phù hợp, input handling, authentication step-up khi cần và các kiểm soát quyền trên server.

### 9.3. Logout

Logout đúng phải làm cho **phiên authenticated hiện tại không còn hợp lệ**, xóa `SecurityContext` theo chính sách và, khi phù hợp, hủy session + trả cookie xóa/ghi đè cho browser. Việc client xóa cookie mà server vẫn chấp nhận identifier cũ có thể chưa đủ. Spring Security hỗ trợ logout handlers; chính xác các hiệu ứng phụ thuộc session store, cookie setup, token model.

### 9.4. Expiration và concurrent sessions

Timeout giới hạn thời gian phiên có hiệu lực khi không hoạt động; concurrent session control giới hạn số session theo user; session fixation protection cắt đứt identifier **trước/sau authentication**. Ba chức năng có mục đích khác nhau, không thay thế nhau. Nếu cần “đăng xuất tất cả thiết bị”, cần cơ chế hủy toàn bộ session/token tương ứng theo hệ thống.

### 9.5. Session không có trước login

Một số browser lần đầu truy cập `/login` sẽ có session do CSRF token, saved request hoặc tính năng khác tạo ra; một số flow khác chưa có session cho tới khi login thành công. Nếu không có ID trước login, hệ thống không thể “chứng minh A khác B” bằng so sánh hai ID. Test fixation nên **chủ động tạo một anonymous session** như `/public/bootstrap`, rồi xác minh kết quả sau xác thực. Nếu bỏ qua điều kiện này, test có thể pass hoặc fail do chi tiết khởi tạo session chứ không thực sự kiểm tra rotation.

## 10. Production: proxy, session store và nhiều instance

Đổi ID an toàn cần xem **toàn bộ vòng đời session**, không chỉ một line cấu hình.

### 10.1. Load balancer và phân tán

Trong triển khai nhiều node, session có thể nằm trên bộ nhớ từng node, sticky session, Redis hoặc Spring Session. Sau khi ID đổi, browser dùng cookie mới; node/load balancer/session repository cần hiểu mapping mới. Nếu old ID vẫn dùng được ở một node do replica chậm đồng bộ hoặc invalidation sai, hiệu lực bảo vệ bị ảnh hưởng. Kiểm tra behavior ở tầng session store thực, không kết luận chỉ từ unit test.

### 10.2. Cookie trùng tên nhưng khác Path/Domain

Browser có thể lưu nhiều cookie cùng tên với phạm vi `Path`/`Domain` khác nhau; proxy hoặc frontend có thể gửi cookie không như mong đợi. Kết quả là login loop, session “mất” hoặc session cố định sai chỗ. Cần audit `Set-Cookie` trên response login và `Cookie` trên request tiếp theo, trong môi trường test bảo vệ dữ liệu nhạy cảm. Đừng sửa bằng cách disable fixation strategy.

### 10.3. Reverse proxy và HTTPS termination

Nếu TLS kết thúc tại proxy, ứng dụng phía sau cần cấu hình tin cậy forwarded headers/scheme đúng cách để nhận biết request HTTPS và phát cookie an toàn. Không tin `X-Forwarded-*` từ client Internet chưa qua proxy được phép. Test behavior trong chính topology triển khai, nhất là login redirect, cookie `Secure` và SameSite.

### 10.4. Session attributes và lifecycle listener

Với `migrateSession`, việc invalidate session cũ rồi copy các attribute sang session mới có thể khiến `HttpSessionBindingListener`, session-scoped bean hoặc disposable lifecycle callback chạy ngoài dự kiến. `changeSessionId` thường đơn giản hơn khi không cần xóa attribute; `newSession` rõ ràng hơn khi muốn cô lập state cũ. Quyết định strategy cần được test với giỏ hàng, draft và các object thực tế.

### 10.5. Không tiết lộ token qua observability

Tránh ghi `JSESSIONID`, `SESSION`, `Cookie` hoặc `Set-Cookie` raw vào log, trace, analytics, error reports và monitoring dashboard; nếu công cụ tự thu headers, cấu hình redaction. Session ID là credential thực tế khi phiên đang hoạt động.

## 11. Không nhầm Servlet `HttpSession` với WebFlux `WebSession`

Bài và code runnable ở trên dành cho **Servlet stack** (`HttpSecurity`, `SecurityFilterChain`, `HttpSession`, Servlet cookie). Trong **WebFlux/reactive**, khái niệm phiên là `WebSession` và security integration dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, context reactive; không bê nguyên `HttpServletRequest.changeSessionId()` vào WebFlux.

Điều cần kiểm tra khi triển khai reactive:

1. Ứng dụng thật đang chạy **WebFlux** hay Spring MVC? Chỉ vì controller trả `Mono` không bảo đảm app dùng reactive web stack.
2. Cơ chế session store, việc tạo/thay ID và login authentication success trong version framework hiện hành.
3. Cookie scope/tracking, session invalidation, reverse proxy, WebSession lifecycle.
4. Integration test kiểm tra một session anonymous pre-login không thể trở thành authenticated với **cùng ID đã biết** sau login.

Nếu API **hoàn toàn stateless**, không lưu authentication trong server-side session, cần tập trung vào vòng đời bearer/refresh token, token rotation/revocation và cookie chứa token (nếu có). Không mặc định bảo mật token bằng các chiến lược `HttpSession` thuộc Servlet.

**Lưu ý bảo trì:** Các bản Spring Framework/WebFlux có thể có cập nhật bảo mật liên quan session management. Theo dõi security advisories của Spring và nâng lên phiên bản đã sửa phù hợp; không dùng bài fundamentals này làm thay thế cho kiểm tra CVE/version của production.

## 12. Ma trận kiểm thử nên có khi review tính năng login

| Tình huống | Thiết lập | Kỳ vọng |
|---|---|---|
| Anonymous có session trước login → login thành công | Lưu ID trước, gửi POST login đúng | ID sau khác ID trước |
| Có attribute công khai trước login, dùng `changeSessionId` | Tạo `draftColor=blue` | Attribute còn sau login |
| Dùng `newSession` | Tạo cùng attribute trước login | Session ID mới, dữ liệu ứng dụng cũ có thể không còn |
| Sai password | Gửi login thất bại | Không tạo authenticated identity; không coi đây là nâng quyền |
| Old ID được trình bày sau login | Truy cập môi trường test với ID cũ đã ghi cục bộ | Không lấy được tài nguyên được bảo vệ như user vừa login |
| Request mới với ID sau login | Dùng cookie/session mới | Lấy đúng danh tính được xác thực |
| Session hết hạn | Expire/timeout | Không được truy cập resource chỉ bằng cookie hết hạn |
| Logout | Logout đúng contract | Phiên authenticated không còn truy cập được |
| Có nhiều node/cache | Đăng nhập ở node này, request sang node khác | Invalidation/rotation nhất quán trong session store |
| Có reverse proxy | HTTPS frontend, app backend | Set-Cookie an toàn, cookie mới dùng được; không login loop |
| Login với CSRF protection | POST có token hợp lệ/không hợp lệ | Xác thực và CSRF phối hợp đúng; không tắt CSRF để fix test |
| Custom authentication flow | Auth không dùng filter login mặc định | Strategy được tích hợp và kiểm thử ID thực sự đổi |
| Nhiều session/cookie cùng tên | Path/Domain khác nhau | Không gửi nhầm cookie khiến app bỏ lọt/đổi sai session |

Bộ kiểm thử có giá trị nhất là **negative security test**: lấy ID anonymous trước login, sau login xác minh **ID cũ không truy cập được quyền của user mới login**. Test “đăng nhập thành công và API trả 200” không chứng minh fixation protection.

## 13. Hiểu nhầm phổ biến và cách sửa

| Hiểu nhầm | Vì sao sai | Cách làm đúng |
|---|---|---|
| “Đã có HTTPS nên không cần đổi session ID.” | HTTPS bảo vệ đường truyền, không loại bỏ ID đã bị cố định từ trước. | Giữ fixation protection + TLS. |
| “Session ID đủ khó đoán là chống được fixation.” | Attacker có thể đã biết ID hợp lệ, không cần đoán. | Rotate khi nâng quyền. |
| “Thêm HttpOnly là chống fixation.” | HttpOnly không vô hiệu ID mà attacker đã biết. | Cookie hardening + rotate. |
| “Đổi cookie ở client là đủ.” | Server phải loại bỏ khả năng sử dụng ID cũ. | Dùng session strategy ở server. |
| “Xóa session hoàn toàn mới là an toàn duy nhất.” | Có thể giữ state với ID mới đúng cách. | `changeSessionId`/`migrateSession` khi cần. |
| “`changeSessionId` xóa hết giỏ hàng.” | Không tạo session object mới và thường giữ attribute. | Test giữ state an toàn sau login. |
| “`none()` giúp login hết lỗi nên nên dùng.” | Có thể mở lại lỗ hổng fixation. | Tìm nguyên nhân cookie/proxy/session store. |
| “SessionManagementFilter tự xử lý mọi custom login.” | Spring Security 6 không dùng filter này mặc định như trước. | Tích hợp SessionAuthenticationStrategy trong auth flow. |
| “Sẵn có login 200 nghĩa là chống fixation.” | Không kiểm tra old ID. | Integration test rotation + old-ID denial. |
| “CSRF token là đủ.” | CSRF và fixation khác threat model. | Giữ cả hai. |
| “JWT stateless dùng hệt `HttpSession`.” | Authentication lifecycle khác. | Thiết kế token/session theo thực tế. |
| “Đổi ID rồi logout không cần invalidate.” | Đổi khi login không thay thế logout/session expiration. | Thu hồi session đúng contract. |

## 14. Checklist áp dụng

- [ ] Biết ứng dụng dùng Servlet `HttpSession` hay reactive `WebSession`, cookie `JSESSIONID` hay cookie do repository cấu hình.
- [ ] Xác định thời điểm login, đổi tài khoản, MFA/step-up hoặc nâng quyền.
- [ ] Có chiến lược session fixation protection khi **authentication thành công**; không vô hiệu hóa nếu không có giải pháp tương đương được xác minh.
- [ ] Với Servlet 3.1+, xem xét `changeSessionId()`; hiểu khi nào dùng `migrateSession()` và `newSession()`.
- [ ] Đã bật method/HTTP authorization phù hợp; session rotation không tự cấp quyền trên endpoint hay object.
- [ ] Custom authentication tích hợp đúng strategy và SecurityContext persistence, không chỉ tự set context.
- [ ] Test bắt đầu với anonymous session có ID; xác minh ID thay đổi sau login, state an toàn được giữ hoặc xóa đúng chủ ý.
- [ ] Test ID cũ không sử dụng được để truy cập authenticated resource trong môi trường tích hợp thực.
- [ ] Form login, CSRF, saved request, session-scoped objects và listeners vận hành đúng sau rotation.
- [ ] Cookie có Secure, HttpOnly, SameSite, Domain, Path và tracking mode phù hợp với yêu cầu, phía sau proxy đúng scheme.
- [ ] Logout, timeout, revoke, concurrent sessions, nhiều node và session store hoạt động đúng.
- [ ] Không đưa session ID thật lên URL, log, screenshot hoặc error body.
- [ ] Theo dõi security advisories và kiểm chứng version Spring Security, Servlet container, Spring Session/WebFlux thực tế.

## 15. Bài tập suy luận và đáp án

**Câu 1.** Một attacker biết ID `ABC` của phiên anonymous. Sau khi nạn nhân login, server vẫn chấp nhận `ABC` để lấy tài khoản của nạn nhân. Đây là rủi ro gì?

**Đáp án:** Session fixation. Session identifier của giai đoạn trước authentication đã được “nâng quyền” mà không đổi, cho phép người đã biết ID tiếp tục dùng phiên sau login.

**Câu 2.** Vì sao `changeSessionId` thường phù hợp hơn việc bắt người dùng xóa giỏ hàng khi login?

**Đáp án:** Nó đổi “khóa” truy cập phiên nhưng giữ attribute hợp lệ (ví dụ `cartId`), nên vừa ngăn reuse identifier cũ vừa không mất state cần thiết.

**Câu 3.** Có cần chắc chắn ID thay đổi nếu trước login chưa hề có session không?

**Đáp án:** Không có ID cũ để so sánh. Muốn kiểm tra bảo vệ fixation, phải tạo anonymous session trước login rồi thực hiện flow xác thực với chính session ấy.

**Câu 4.** Tại sao không đủ khi thấy `JSESSIONID` có `HttpOnly`?

**Đáp án:** HttpOnly chủ yếu hạn chế JavaScript đọc cookie; nó không hủy một identifier mà attacker có thể đã biết trước nạn nhân login.

**Câu 5.** Trong app Spring Security 6 với custom login controller tự tạo `Authentication` và lưu context, mặc định có bảo đảm rotate ID không?

**Đáp án:** Không thể suy ra. Cần xem controller/filter có tích hợp `SessionAuthenticationStrategy` và session repository/persistence phù hợp hay không, rồi test ID cũ/mới bằng request thực.

**Câu 6.** Login thành công, ID đổi, nhưng sau đó user bị mất attribute `cartId`. Luôn là bug?

**Đáp án:** Không. Nếu chọn `newSession` để cô lập state cũ, việc không chuyển attribute ứng dụng là chủ đích. Nếu sản phẩm cần giữ giỏ hàng, xem xét `changeSessionId`, `migrateSession` hoặc cơ chế chuyển state đã được kiểm tra an toàn.

## 16. Tham khảo chính thức

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session fixation, ba chiến lược khuyến nghị, hành vi Spring Security 6 với custom authentication và session persistence.
- [Spring Security — FAQ: Why does my session ID change when I authenticate?](https://docs.spring.io/spring-security/reference/servlet/appendix/faq.html): giải thích vì sao ID mặc định đổi khi login.
- [Spring Security — SessionFixationConfigurer API](https://docs.spring.io/spring-security/site/docs/6.1.7/api/org/springframework/security/config/annotation/web/configurers/SessionManagementConfigurer.SessionFixationConfigurer.html): `changeSessionId`, `newSession`, `migrateSession`, `none`.
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): authentication bằng form login và luồng filter.
- [Spring Security — Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/): kiểm thử với MockMvc và Spring Security.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): giải thích bảo vệ các request trạng thái.
- [Spring Framework — Web Session (WebFlux)](https://docs.spring.io/spring-framework/reference/web/webflux-websession.html): phân biệt `WebSession` và Servlet `HttpSession`.

**Ghi nhớ:** Giải pháp không nằm ở việc “cứ tạo phiên mới là xong”, mà ở việc **session identifier biết từ lúc chưa xác thực không còn có thể đại diện cho một phiên đã xác thực**. Rotate ID tại authentication boundary, kiểm thử bằng session cũ và mới, rồi bảo vệ toàn bộ vòng đời cookie/session trên môi trường triển khai thực tế.
