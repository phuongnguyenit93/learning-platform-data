# SessionRegistry, HttpSessionEventPublisher và theo dõi phiên hoạt động

> **Module:** Spring Security - authentication. **Nhóm:** Quản lý phiên. Bài học áp dụng cho **Spring Security Servlet 6.x**, minh họa bằng **Java 17 + Spring Boot 3.3.5**. Mục tiêu là hiểu chính xác `SessionRegistry` ghi nhận các phiên đã đăng nhập ra sao, `HttpSessionEventPublisher` truyền sự kiện vòng đời từ Servlet container như thế nào, và cách quan sát/giới hạn số phiên đang hoạt động mà không nhầm "có bản ghi" với "người dùng chắc chắn đang online".

## 1. Vì sao cần SessionRegistry?

Một tài khoản có thể đăng nhập từ hai trình duyệt, laptop và điện thoại. Khi người dùng nhấn "logout tất cả thiết bị", bộ phận an ninh cần kiểm tra có những phiên nào; khi sản phẩm yêu cầu mỗi tài khoản chỉ đăng nhập một nơi, hệ thống cần giới hạn **concurrent sessions**.

Có ba khái niệm phải tách riêng:

1. **`HttpSession`**: đối tượng phiên HTTP do Servlet container quản lý; thường được browser liên hệ bằng cookie `JSESSIONID`. Nó chứa thuộc tính của ứng dụng và có thể chứa `SecurityContext`, tùy cấu hình.
2. **`SecurityContext` / `Authentication`**: danh tính đã xác thực được Spring Security dùng cho phân quyền. Context có thể được lưu/khôi phục trong `HttpSession` qua `SecurityContextRepository`.
3. **`SessionRegistry`**: chỉ mục các **session ID** gắn với **principal** đã được đăng ký; cung cấp `SessionInformation` (thời điểm request cuối, cờ expired). Registry **không phải** nơi lưu password, cookie, toàn bộ nội dung session hay `SecurityContext`.

Một bản ghi trong registry không có nghĩa là có người thật đang mở trang ngay lúc đó. "Phiên hoạt động" trong ngữ cảnh này thường là phiên **được registry theo dõi, chưa đánh dấu expired và chưa được thông báo destroyed**; dữ liệu còn phụ thuộc lifecycle events, thời hạn timeout, đường đi qua filter, và phạm vi JVM.

### Phân biệt các thành phần

| Thành phần | Có gì | Ai cập nhật |
| --- | --- | --- |
| Servlet `HttpSession` | ID, thuộc tính, thời gian sống do container quản lý | Container, ứng dụng |
| `HttpSessionSecurityContextRepository` | `SecurityContext` được giữ qua request khi dùng session | Authentication mechanism, logout |
| `SessionRegistryImpl` | Principal → session IDs, `SessionInformation` | `RegisterSessionAuthenticationStrategy`, `ConcurrentSessionFilter`, các sự kiện destroy/id-change |
| `HttpSessionEventPublisher` | Không phải kho dữ liệu; là **listener cầu nối sự kiện** | Servlet container gọi khi session create/destroy/change ID |
| `ConcurrentSessionControlAuthenticationStrategy` | Kiểm tra giới hạn đăng nhập khi xác thực thành công | Authentication mechanism gọi strategy |
| `ConcurrentSessionFilter` | Làm mới thời điểm hoạt động; xử lý phiên bị đánh dấu expired | Security filter chain trên request tiếp theo |

**Tư duy đúng:** session registry là **chỉ mục phục vụ kiểm soát phiên**, không thay thế cơ chế lưu phiên của container và không bảo đảm một bức tranh online toàn cầu khi app có nhiều instance.

## 2. Những phương thức quan trọng của SessionRegistry

Interface `org.springframework.security.core.session.SessionRegistry` có các API sau:

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `getAllPrincipals()` | Lấy các principal đã biết trong registry | Không tự động là tất cả user trong database; không nên trả công khai |
| `getAllSessions(principal, false)` | Lấy session chưa đánh dấu `expired` của một principal | Session bị destroyed phải được xóa qua event; không phải đo presence real-time |
| `getAllSessions(principal, true)` | Lấy cả session **đã đánh dấu expired** nhưng chưa bị xóa | Chưa bao gồm session **đã destroyed/removed** |
| `getSessionInformation(sessionId)` | Lấy metadata theo ID, hoặc `null` nếu không có | ID là dữ liệu nhạy cảm; hạn chế lộ trong API/log |
| `registerNewSession(sessionId, principal)` | Đăng ký một session vào chỉ mục | Thường do strategy khi login thành công gọi; không gọi cho client chưa xác thực |
| `refreshLastRequest(sessionId)` | Cập nhật thời điểm request mới nhất | Không nhất thiết đúng thời gian từng hành vi UI hoặc WebSocket |
| `removeSessionInformation(sessionId)` | Xóa bản ghi đã có khỏi registry | **Không** tương đương `HttpSession.invalidate()` |
| `SessionInformation.expireNow()` | Đánh dấu bản ghi expired | **Không** ngay lập tức hủy `HttpSession`; xử lý khi phiên được kiểm tra ở request kế tiếp |

Ví dụ về cách đọc trạng thái, chỉ là **đoạn Java minh họa**, không phải ứng dụng độc lập:

```java
Object trustedPrincipal = authentication.getPrincipal();
List<SessionInformation> active =
        sessionRegistry.getAllSessions(trustedPrincipal, false);

for (SessionInformation info : active) {
    boolean expired = info.isExpired();
    Date lastSeen = info.getLastRequest();
    // Không đưa raw sessionId vào response công khai.
}
```

`Authentication` ở đây phải là kết quả **đã được server xác thực**, không lấy userId tùy ý từ query rồi dùng nó để liệt kê phiên của người khác.

### Cực kỳ quan trọng: principal và `equals/hashCode`

`SessionRegistryImpl` dùng principal làm khóa trong một map bộ nhớ. Nếu một custom `UserDetails` không có `equals()` / `hashCode()` ổn định, cùng một người đăng nhập nhiều lần nhưng mỗi lần là object khác nhau có thể bị xem như các principal khác nhau. Giới hạn concurrent session vì vậy có thể sai.

- Định danh ổn định thường là user ID nội bộ hoặc một principal bất biến có `equals/hashCode` hợp lệ.
- Không dùng thông tin mutable (vai trò thay đổi, display name, random object identity) làm khóa so sánh mà không kiểm soát.
- Trong hệ thống multi-tenant, khóa danh tính phải mang **tenant ID** khi một username có thể lặp giữa các tổ chức.

`UserDetails` dựng bằng `org.springframework.security.core.userdetails.User` trong demo có phép so sánh danh tính thích hợp; nếu tự tạo implementation, hãy kiểm thử riêng quy tắc so sánh.

## 3. Vòng đời một phiên: đăng nhập, truy cập, hết hạn, logout

```text
Trình duyệt gửi POST /login + username/password + CSRF
   |
   v
UsernamePasswordAuthenticationFilter
   |-- AuthenticationManager -> AuthenticationProvider
   |-- credential đúng -> Authentication đáng tin
   v
SessionAuthenticationStrategy của Spring Security
   |-- kiểm tra maximumSessions(...)
   |-- chống session fixation (thường changeSessionId)
   |-- đăng ký sessionID / principal với SessionRegistry
   v
SecurityContextRepository lưu SecurityContext vào HttpSession
   |
   +--> SessionRegistryImpl:
   |      principal alice -> {session-id-1}
   |
   v
GET /api/sessions với cookie phiên
   |-- Filter lấy SecurityContext
   |-- ConcurrentSessionFilter refreshLastRequest(session-id-1)
   |-- Controller đọc SessionRegistry (chỉ metadata)
   v
Response: activeCount = 1
   |
   +-- Logout / HttpSession timeout / explicit invalidate:
   |      Servlet container phát sessionDestroyed
   |      HttpSessionEventPublisher chuyển thành Spring event
   |      SessionRegistryImpl loại bỏ session ID
   |
   +-- Khi registry đánh dấu expireNow():
          SessionInformation.expired = true
          ConcurrentSessionFilter phát hiện ở request tiếp theo
          -> xử lý expired session, hủy phiên (theo strategy)
          -> publisher/event xóa bản ghi
```

### 3.1. `RegisterSessionAuthenticationStrategy`

Khi login qua cơ chế được Spring Security cấu hình hỗ trợ concurrency (ví dụ `formLogin` trong demo), chuỗi `SessionAuthenticationStrategy` thường bao gồm chiến lược kiểm tra số phiên, bảo vệ session fixation, và `RegisterSessionAuthenticationStrategy` để đưa session ID vừa login vào registry.

**Không phải cứ tạo bean `SessionRegistryImpl` là mọi login sẽ tự hiện trong danh sách.** Nếu bạn tự viết JSON-login controller rồi gọi `AuthenticationManager.authenticate` trực tiếp, phải thiết kế/áp dụng `SessionAuthenticationStrategy` phù hợp và lưu `SecurityContext` qua repository. Spring Security 6 không mặc định dùng `SessionManagementFilter` để tự phát hiện thành công trên mọi request.

### 3.2. `ConcurrentSessionFilter` và `lastRequest`

Khi cấu hình concurrent session control, Spring Security có thể dùng `ConcurrentSessionFilter` để cập nhật thời điểm hoạt động trong `SessionInformation`. Khi filter thấy bản ghi **đã đánh dấu expired**, nó thực thi chiến lược hết phiên (`SessionInformationExpiredStrategy`) và logout/invalidate theo quy trình được cấu hình.

Vì vậy:
- `lastRequest` là **mốc hoạt động HTTP do filter ghi nhận**, không phải dấu hiệu người dùng đang ngồi trước màn hình.
- Một tab bị đóng, mất mạng hay client không gửi request nữa có thể làm registry vẫn có bản ghi cho tới timeout/destroy event.
- `expireNow()` chỉ đánh dấu; trước request tiếp theo, `HttpSession` trong container có thể chưa bị invalidate ngay.
- Nếu cần thu hồi ngay mọi token/thiết bị, phải có cơ chế vô hiệu hóa tương ứng với **loại credential**, ví dụ invalidate session thực và/hoặc denylist token theo kiến trúc.

### 3.3. `HttpSessionEventPublisher` đóng vai trò gì?

`HttpSessionEventPublisher` là Servlet listener của Spring Security. Nó tiếp nhận các sự kiện vòng đời của `HttpSession` từ **Servlet container**, rồi phát sự kiện tương ứng lên Spring application context, bao gồm sự kiện session created/destroyed và thay đổi session ID khi được container thông báo.

`SessionRegistryImpl` là listener của các Spring session events, đặc biệt xử lý **session destroyed** để xóa entry. Nếu **không đăng ký publisher** khi dùng in-memory registry với container session, thông tin của phiên đã timeout/logout có thể không được cập nhật kịp, khiến hệ thống tưởng tài khoản vẫn giữ một slot đăng nhập.

Chuỗi sự kiện:

```text
HttpSession.invalidate(), logout hoặc container timeout
     -> Servlet HttpSessionListener.sessionDestroyed(...)
     -> HttpSessionEventPublisher
     -> Spring HttpSessionDestroyedEvent
     -> SessionRegistryImpl (ApplicationListener)
     -> removeSessionInformation(sessionId)
```

**Không nhầm:** Publisher không tự theo dõi "user online"; nó không lưu bảng session. Và chỉ có publisher mà không cấu hình `SessionRegistry`/concurrency strategy cũng không tự sinh ra chức năng quản lý phiên. Đăng ký listener **một lần**, tránh thêm cả bean và đăng ký servlet listener thứ hai cho cùng một instance.

## 4. Dự án chạy được: theo dõi session và chặn đăng nhập đồng thời

### 4.1. Mục tiêu demo

- Một user `alice`, password demo `demo-pass123`, role `USER`.
- Đăng nhập bằng form mặc định do Spring Security cung cấp (`GET /login`, `POST /login`).
- `SessionRegistryImpl` ghi nhận các lần login thành công.
- `maximumSessions(1).maxSessionsPreventsLogin(true)`: từ chối login thứ hai trong khi session thứ nhất vẫn hợp lệ.
- `HttpSessionEventPublisher` giúp registry biết về logout/timeout/invalidated session thực.
- `GET /api/sessions` trả **số phiên đang được registry coi là hoạt động** và metadata giới hạn cho **chính người đã đăng nhập**; không trả session ID hoặc liệt kê toàn hệ thống.

Cấu trúc:

```text
session-registry-demo/
├── pom.xml
├── src/main/java/com/example/sessions/SessionRegistryDemoApplication.java
└── src/test/java/com/example/sessions/SessionRegistryDemoApplicationTests.java
```

**`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>session-registry-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
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
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 4.2. `src/main/java/com/example/sessions/SessionRegistryDemoApplication.java`

```java
package com.example.sessions;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@SpringBootApplication
public class SessionRegistryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionRegistryDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo-pass123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    // Boot đăng ký Servlet listener bean; không đăng ký lại trong web.xml.
    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, SessionRegistry registry) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .requestMatchers("/api/sessions").authenticated()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                .maximumSessions(1)
                .maxSessionsPreventsLogin(true)
                .sessionRegistry(registry)
            );

        return http.build();
    }

    public record SessionSummary(boolean current, String lastRequestUtc) {}

    public record SessionOverview(
            String username,
            int activeCount,
            List<SessionSummary> sessions
    ) {}

    @RestController
    static class SessionController {
        private final SessionRegistry registry;

        SessionController(SessionRegistry registry) {
            this.registry = registry;
        }

        @GetMapping("/api/sessions")
        SessionOverview currentUserSessions(
                Authentication authentication,
                HttpServletRequest request) {

            HttpSession httpSession = request.getSession(false);
            String currentId = httpSession == null ? null : httpSession.getId();

            // Principal này đã được Spring Security xác thực.
            // Không lấy username/sessionId từ query do client tự khai.
            List<SessionSummary> summaries = registry
                .getAllSessions(authentication.getPrincipal(), false)
                .stream()
                .map(info -> new SessionSummary(
                    currentId != null && currentId.equals(info.getSessionId()),
                    info.getLastRequest().toInstant().toString()
                ))
                .toList();

            // Không đưa raw session ID hoặc credential vào JSON response.
            return new SessionOverview(
                    authentication.getName(),
                    summaries.size(),
                    summaries
            );
        }
    }
}
```

### 4.3. Vì sao các dòng cấu hình trên quan trọng?

1. `@Bean SessionRegistry` cung cấp registry **duy nhất** dùng cho cả concurrent-session control và endpoint theo dõi. Nếu mỗi nơi tự `new SessionRegistryImpl()`, dữ liệu sẽ không khớp.
2. `@Bean HttpSessionEventPublisher` đăng ký bridge giữa Servlet container và Spring events. Khi session thật bị destroyed, `SessionRegistryImpl` được thông báo để xóa record.
3. `formLogin(Customizer.withDefaults())` dùng authentication filter tiêu chuẩn, hỗ trợ áp dụng các session authentication strategies khi login thành công. Bài demo **không tự viết Controller login** rồi quên gọi chúng.
4. `maximumSessions(1)` đặt giới hạn một phiên đã đăng nhập cho mỗi principal. `maxSessionsPreventsLogin(true)` quyết định **từ chối lần đăng nhập sau**, thay vì đánh dấu phiên cũ hết hạn. Không bị nhầm giữa giới hạn và chính sách khi vượt giới hạn.
5. `sessionRegistry(registry)` làm concurrency strategy và `ConcurrentSessionFilter` tham chiếu đúng registry. Không tự thao tác map principal → IDs.
6. `GET /api/sessions` yêu cầu người đã xác thực, dùng `authentication.getPrincipal()` để tra session của **chính họ** và chỉ công bố số lượng/last-request. API quản trị liệt kê mọi principal cần authorization rõ ràng, tránh lộ ID phiên hoặc dữ liệu người dùng khác.
7. Spring Security mặc định giữ CSRF khi dùng form login. Trình duyệt dùng form `/login` tạo bởi framework sẽ gửi CSRF token; không tắt CSRF chỉ để demo chạy được.
8. Session fixation protection mặc định có thể đổi session ID sau login. Registry phải theo dõi đúng ID mới; publisher cũng có vai trò chuyển các sự kiện thay đổi ID từ Servlet container.

Demo chạy trong **một JVM**, registry lưu trong bộ nhớ. Nó không minh họa một hệ thống nhiều node cùng quản lý phiên, và endpoint là số phiên registry tin rằng chưa expired/destroyed — không phải hệ thống presence thời gian thực.

## 5. Chạy thực hành trên trình duyệt

Khởi động:

```bash
mvn spring-boot:run
```

1. Mở `http://localhost:8080/login` bằng **trình duyệt A**, đăng nhập bằng `alice` / `demo-pass123`. Nếu thành công, Spring Security mặc định chuyển hướng về trang đích. Không nhất thiết có trang chủ tự xây; việc không có nội dung ứng dụng tại `/` không làm login thất bại.
2. Trong **cùng trình duyệt A**, truy cập `http://localhost:8080/api/sessions`. JSON kỳ vọng có `"username":"alice"`, `"activeCount":1` và một mục có `"current":true`. Thời điểm `lastRequestUtc` thay đổi theo hoạt động thực tế.
3. Mở **trình duyệt B trong profile độc lập** (cookie jar hoàn toàn khác), thử đăng nhập **cùng tài khoản alice**. Vì `maxSessionsPreventsLogin(true)`, lần login này bị từ chối, thường chuyển hướng đến `/login?error`, chứ không tạo một phiên login thứ hai.
4. Trở lại trình duyệt A và tải `/api/sessions`: phiên A vẫn tồn tại, `activeCount` vẫn là 1 (giả sử chưa timeout/logout).
5. Logout trong A bằng form/luồng logout hợp lệ của Spring Security (POST `/logout` có CSRF). Khi container hủy session, publisher thông báo cho registry. Sau khi logout, vào `/api/sessions` sẽ bị yêu cầu đăng nhập trở lại.
6. Sau đó B đăng nhập thành công bằng tài khoản alice (khi event destroy đã cập nhật registry); nếu vẫn bị chặn, kiểm tra đăng ký publisher, principal equality, thời hạn thực và đồng bộ lifecycle.

Ví dụ JSON **giá trị minh họa**, không định nghĩa timestamp cố định:

```json
{
  "username": "alice",
  "activeCount": 1,
  "sessions": [
    {
      "current": true,
      "lastRequestUtc": "2026-01-01T08:30:00Z"
    }
  ]
}
```

Timestamp là ví dụ định dạng UTC ISO-8601; thời điểm thật khác nhau. Không nên công bố session ID thật trong UI hoặc tài liệu log, vì nó là một credential có thể bị lạm dụng nếu rò rỉ.

**Phân biệt status:** với `formLogin` thất bại do vượt số phiên, kết quả thường là redirect đến trang login có báo lỗi, không nhất thiết HTTP 401 JSON. Với API riêng do bạn xây, phản hồi phải được thiết kế rõ bằng success/failure handler.

## 6. Kiểm thử bằng MockMvc và kiểm thử API registry

Tạo `src/test/java/com/example/sessions/SessionRegistryDemoApplicationTests.java`:

```java
package com.example.sessions;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionRegistryDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    SessionRegistry registry;

    @Autowired
    UserDetailsService userDetailsService;

    @Test
    void tracksFirstLoginAndBlocksSecondOne() throws Exception {
        // formLogin() của spring-security-test gửi CSRF hợp lệ.
        MvcResult first = mvc.perform(
                    formLogin().user("alice").password("demo-pass123"))
                .andExpect(authenticated().withUsername("alice"))
                .andReturn();

        MockHttpSession browserA =
                (MockHttpSession) first.getRequest().getSession(false);
        assertNotNull(browserA);

        Object alice = userDetailsService.loadUserByUsername("alice");
        assertEquals(1, registry.getAllSessions(alice, false).size());

        mvc.perform(get("/api/sessions").session(browserA))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.activeCount").value(1))
                .andExpect(jsonPath("$.sessions[0].current").value(true));

        // Trình duyệt khác: không kèm session cũ. Chính sách chặn login thứ hai.
        mvc.perform(formLogin().user("alice").password("demo-pass123"))
                .andExpect(unauthenticated());

        // Phiên A vẫn được phép truy cập.
        mvc.perform(get("/api/sessions").session(browserA))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.activeCount").value(1));
    }

    @Test
    void expiredMarkerIsNotTheSameAsRemovingSessionRecord() {
        SessionRegistryImpl isolated = new SessionRegistryImpl();
        isolated.registerNewSession("test-session-1", "alice");

        SessionInformation info =
                isolated.getSessionInformation("test-session-1");
        assertNotNull(info);
        assertFalse(info.isExpired());
        assertEquals(1, isolated.getAllSessions("alice", false).size());

        // Đánh dấu expired: entry vẫn tồn tại khi includeExpired = true.
        info.expireNow();
        assertTrue(info.isExpired());
        assertEquals(0, isolated.getAllSessions("alice", false).size());
        assertEquals(1, isolated.getAllSessions("alice", true).size());
        assertNotNull(isolated.getSessionInformation("test-session-1"));

        // Xóa registry entry: không tìm thấy ngay cả khi includeExpired = true.
        isolated.removeSessionInformation("test-session-1");
        assertNull(isolated.getSessionInformation("test-session-1"));
        assertEquals(0, isolated.getAllSessions("alice", true).size());
    }
}
```

Chạy:

```bash
mvn test
```

Điều các test **chứng minh**:
- Form login thành công được đăng ký trong `SessionRegistry` và request sau đọc được thông tin theo principal đã xác thực.
- Với `maximumSessions(1).maxSessionsPreventsLogin(true)`, cùng username đăng nhập từ client thứ hai bị từ chối, trong khi phiên cũ vẫn có thể dùng.
- `expireNow()` là một **cờ** ở registry; nó khác `removeSessionInformation(...)`.

Điều các test **chưa chứng minh**: Servlet container thật có phát events khi timeout không, và `HttpSessionEventPublisher` có chuyển tiếp event trong môi trường deploy hay không. `MockHttpSession` là mô phỏng, không thay thế được bài kiểm thử tích hợp chạy server thật chờ timeout/đăng xuất. Khi cần kiểm thử publisher thực, dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` hoặc môi trường container thật, rồi quan sát việc entry bị xóa; tránh kết luận chỉ từ unit test.

## 7. Những câu hỏi thường bị nhầm lẫn

### 7.1. Tại sao có SessionRegistry nhưng `getAllSessions` luôn rỗng?

Có thể vì:
- Chỉ khai báo `@Bean SessionRegistryImpl` nhưng **không** liên kết nó với concurrent session authentication strategy.
- Cơ chế login là custom controller/filter không gọi `SessionAuthenticationStrategy` hoặc không lưu `SecurityContext` đúng cách.
- Đang tra bằng một object principal **không equals** với principal đã đăng ký; ví dụ `getAllSessions("alice", false)` nhưng registry lưu `UserDetails` object.
- Dùng JWT/HTTP Basic stateless không tạo login session nên không có phiên để đăng ký; không nên kỳ vọng mọi Bearer request sinh một `HttpSession`.
- Có nhiều instances, request và registry bean nằm ở hai JVM khác nhau.
- Session đã destroyed và sự kiện đã xóa khỏi registry.

**Chẩn đoán:** trước hết xác minh authentication mechanism nào tạo session, strategy đã gọi đúng registry bean hay chưa, và principal type/equality thực tế; tuyệt đối không kết luận "người dùng chưa login" chỉ bằng danh sách rỗng.

### 7.2. Vì sao đã logout nhưng vẫn thấy activeCount = 1?

Nghi ngờ:
- `HttpSessionEventPublisher` chưa được container đăng ký hoặc bị đăng ký sai kiểu.
- Logout không thực sự invalidate session (custom logout chỉ xóa cookie client).
- Session bị đánh dấu expired nhưng chưa bị destroyed, hoặc `includeExpiredSessions=true` đang hiển thị cả entry đã đánh dấu.
- Registry/Servlet container khác instance, application restart khiến quan sát lệch.
- Cùng principal có phiên **khác** vẫn hoạt động.

Không nên tự sửa triệu chứng bằng cách gọi `removeSessionInformation` cho mọi logout mà bỏ qua session thực: xóa metadata không vô hiệu hóa cookie/session. Nên dùng `LogoutFilter`/`SecurityContextLogoutHandler` đúng cách và bảo đảm publisher/event hoạt động.

### 7.3. `expireNow()` có đá người dùng ra ngay không?

**Không ngay lập tức.** `expireNow` đánh dấu `SessionInformation` là expired. `ConcurrentSessionFilter` kiểm tra cờ khi phiên đó gửi request tiếp theo và xử lý bằng `SessionInformationExpiredStrategy`. Nếu muốn ngay lập tức hủy phiên của thiết bị đang im lặng, cần một cơ chế sở hữu thực sự `HttpSession`/session store để invalidate hoặc disable credential; registry một mình không cất đối tượng `HttpSession` để gọi `invalidate()` trực tiếp.

### 7.4. `maxSessionsPreventsLogin(true)` khác default thế nào?

Với `maximumSessions(1)`:
- Mặc định (không bật `maxSessionsPreventsLogin`): login mới có thể thành công và phiên đã có (thường least recently used) bị đánh dấu expired. Khi phiên cũ gửi request tiếp theo, filter xử lý hết hạn.
- `maxSessionsPreventsLogin(true)`: từ chối phiên login mới khi đã đạt giới hạn; phiên hiện có vẫn giữ hiệu lực.

Cả hai dựa trên registry có số liệu **đúng**. Nếu publisher không xóa phiên chết hoặc principal equality sai, quyết định giới hạn cũng có thể sai.

### 7.5. Session timeout và SessionInformation expired khác nhau?

- **Servlet timeout**: container quyết định phiên HTTP đã hết hạn do không hoạt động; publisher chuyển sự kiện destroy để registry xóa bản ghi.
- **Concurrency expired**: registry đánh dấu `SessionInformation.expired=true` theo chính sách (như login mới thay phiên cũ); thông thường filter xử lý khi session đó gửi request lại.
- **Logout**: có thể invalidate `HttpSession` và dọn `SecurityContext`. Sự kiện destroy giúp registry không còn giữ entry.

`SessionInformation.getLastRequest()` không phải thời gian tuyệt đối container sẽ timeout, vì container có cấu hình idle timeout riêng và app có thể có các request không qua cùng filter.

### 7.6. Registry trên một server có dùng được cho nhiều server không?

`SessionRegistryImpl` mặc định là **in-memory theo JVM**. Nếu app deploy nhiều node sau load balancer, mỗi node có thể thấy chỉ một phần phiên. `sticky session` cũng không biến hai registry độc lập thành một registry toàn cục.

Cần kiến trúc session chia sẻ (ví dụ Spring Session với Redis/JDBC) và chiến lược session registry/event tương thích với deployment đó. Các phiên/token có thể bị xóa ngoài JVM nên phải xác minh events, eviction và concurrency policy trong môi trường cluster; không giả định thêm Redis là `SessionRegistryImpl` tự động phân tán.

### 7.7. Có nên tạo API "liệt kê mọi session" cho admin không?

Chỉ khi có nhu cầu nghiệp vụ rõ ràng và ủy quyền chặt. `getAllPrincipals()` và `getAllSessions(...)` có thể làm lộ danh tính, hoạt động, thời điểm truy cập và ID phiên. Không cung cấp raw session IDs cho client thường; ngay cả admin interface nên trả thông tin tối thiểu, audit truy cập, dùng cơ chế thu hồi có kiểm soát thay vì để client tự gửi session ID muốn xóa.

Một dashboard "online users" dựa trên registry có thể **sai lệch**: phiên còn tồn tại không có nghĩa user online, còn một request WebSocket/token stateless cũng không nhất thiết được registry đếm. Nếu cần presence gần thời gian thực, hãy thiết kế heartbeat và định nghĩa SLA riêng.

## 8. Tình huống triển khai và checklist

| Nhu cầu | Cách dùng đúng |
| --- | --- |
| Chỉ đếm phiên của user đang login | `registry.getAllSessions(auth.getPrincipal(), false).size()` với kiểm soát truy cập |
| Xem metadata phiên cuối truy cập | `SessionInformation.getLastRequest()`, tránh lộ session ID |
| Giới hạn một phiên/user | `maximumSessions(1)` + đúng registry/publisher + principal equality |
| Muốn giữ phiên cũ, từ chối login mới | `maxSessionsPreventsLogin(true)` |
| Muốn ưu tiên login mới | Giữ default concurrency behavior, hiểu expire-on-next-request |
| Logout/timeout sạch chỉ mục | Servlet listener `HttpSessionEventPublisher` và session lifecycle đúng |
| Logout mọi thiết bị | Thiết kế thao tác invalidate session thực/thu hồi credential; `expireNow()` không tức thì |
| Nhiều node hoặc session store ngoài JVM | Dùng registry và event stream tương thích kiến trúc chia sẻ |
| Custom JSON login | Gọi đầy đủ authentication strategy + lưu context, không chỉ authenticate |
| Báo cáo user online thật | Không dựa một mình vào SessionRegistry; cần heartbeat/presence riêng |

Checklist trước production:

- [ ] Cơ chế xác thực tạo session thực, không phải JWT/Bearer stateless thuần.
- [ ] Một `SessionRegistry` chung được wiring với concurrency strategy, filter và code quan sát.
- [ ] `HttpSessionEventPublisher` đăng ký đúng với Servlet container, đúng một lần.
- [ ] Test logout, invalidation, session timeout thực bằng container có listener đang chạy.
- [ ] `UserDetails.equals/hashCode` ổn định; nếu multi-tenant, không nhập nhằng principal giữa tenants.
- [ ] CSRF vẫn được bảo vệ cho request dùng cookie; session fixation protection không bị vô hiệu hóa.
- [ ] API quan sát chỉ trả session của chính user hoặc yêu cầu quyền admin rõ ràng.
- [ ] Không đưa raw session ID vào logs, JSON response, metrics labels hoặc URL.
- [ ] Có thiết kế riêng nếu ứng dụng chạy nhiều JVM/pods.
- [ ] Hiểu rõ khác biệt `expireNow`, `removeSessionInformation` và `HttpSession.invalidate`.

## 9. Tự đánh giá kiến thức

1. Vì sao `SessionRegistryImpl` không phải kho lưu `SecurityContext` hay nội dung `HttpSession`?
2. Chức năng cụ thể của `HttpSessionEventPublisher` là gì, và nó nhận event từ lớp nào?
3. `getAllSessions(principal, false)` khác `getAllSessions(principal, true)` ra sao?
4. `expireNow()` có xóa `HttpSession` lập tức không? Thành phần nào phản ứng ở request sau?
5. Vì sao custom `UserDetails` thiếu `equals/hashCode` có thể làm chính sách max sessions sai?
6. Vì sao không nên gọi `getAllSessions("alice", false)` nếu registry lưu key `UserDetails`?
7. Điểm khác nhau giữa `maxSessionsPreventsLogin(true)` và chính sách mặc định khi giới hạn một phiên?
8. Vì sao MockMvc test không đủ để chứng minh Servlet timeout event hoạt động trên production?
9. Với 3 pods sau load balancer, mặc định `SessionRegistryImpl` có đếm tất cả session không?
10. Vì sao một tài khoản có session registered vẫn có thể được xem là offline theo tiêu chuẩn presence thực tế?

**Đáp án cốt lõi:** (1) registry chỉ giữ index/metadata; (2) chuyển lifecycle events từ Servlet container sang Spring application context; (3) `true` bao gồm entry đã đánh dấu expired nhưng chưa removed; (4) không, filter xử lý lúc phiên gửi request sau; (5) principal map key có thể so sánh sai; (6) sai type/equality; (7) chặn login mới so với đánh dấu phiên cũ hết hạn; (8) mock không thay real container listener/timeout; (9) không, in-memory theo JVM; (10) phiên tồn tại không bảo đảm user hoạt động ngay hiện tại.

## 10. Tài liệu tham khảo chính thức

- Spring Security — Authentication Persistence and Session Management (Servlet, phiên bản 6.5): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — `SessionRegistry` API: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/core/session/SessionRegistry.html
- Spring Security — `SessionRegistryImpl` API: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/core/session/SessionRegistryImpl.html
- Spring Security — `HttpSessionEventPublisher` API: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/session/HttpSessionEventPublisher.html
- Spring Security — `ConcurrentSessionFilter` API: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/session/ConcurrentSessionFilter.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Session — Reference (shared sessions and integration): https://docs.spring.io/spring-session/reference/
