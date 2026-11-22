# Nhiều phiên, nhiều thiết bị và yêu cầu thu hồi truy cập

> **Ngữ cảnh:** Spring Security – fundamentals / **Phiên và cookie**. Bài tập trung vào ứng dụng **Spring MVC/Servlet** sử dụng `HttpSession` và cookie định danh phiên, giải thích cách kiểm soát đăng nhập từ nhiều trình duyệt/thiết bị và thu hồi quyền truy cập khi người dùng đăng xuất, mất thiết bị, đổi mật khẩu, bị khóa tài khoản hoặc chủ động chọn “đăng xuất các thiết bị khác”. Phần mở rộng phân biệt Spring Session/Redis với access token JWT. Ví dụ thực hành dùng Java 17, Spring Boot 3.5.0, Spring Security 6.x.

## 1. Bài toán thật sự là gì?

Một người dùng đăng nhập vào cùng tài khoản trên laptop công ty, điện thoại và máy tính cá nhân. Mỗi browser profile có thể giữ cookie phiên riêng; nếu người dùng không đăng xuất, các phiên đó có thể tiếp tục được sử dụng.

Những yêu cầu thường gặp:

- **Cho phép nhiều phiên:** Người dùng được đăng nhập đồng thời trên nhiều thiết bị, chẳng hạn tối đa hai hoặc năm phiên.
- **Giới hạn phiên:** Khi đạt ngưỡng, chọn *từ chối phiên mới* hoặc *cho phiên mới và làm hết hạn phiên cũ*.
- **Đăng xuất thiết bị hiện tại:** Chỉ hủy phiên gắn với request đang thực hiện.
- **Đăng xuất các thiết bị khác:** Hủy/từ chối mọi phiên khác nhưng giữ phiên hiện tại.
- **Đăng xuất mọi thiết bị:** Hủy cả phiên hiện tại và các phiên khác.
- **Thu hồi khẩn cấp:** Khi phát hiện cookie bị đánh cắp, đổi mật khẩu, tài khoản bị khóa hoặc một nhân viên nghỉ việc, các phiên cũ không còn được phép truy cập dù cookie vẫn nằm trên thiết bị.
- **Quan sát và kiểm toán:** Cho người dùng biết thời điểm hoạt động gần nhất, vị trí/thiết bị *ước lượng*, và thao tác thu hồi nào đã xảy ra mà không lộ session ID.

**Điểm mấu chốt:** Xóa cookie trên một trình duyệt **không đồng nghĩa** thu hồi mọi phiên của cùng tài khoản. Muốn khóa quyền truy cập tại server, backend phải vô hiệu hóa trạng thái phiên hoặc kiểm tra một cơ chế revocation đáng tin cậy khi có request.

## 2. Phiên, cookie và “thiết bị” không phải cùng một khái niệm

### 2.1. Cookie mang định danh; trạng thái xác thực nằm ở server

Một luồng form login thường như sau:

```mermaid
sequenceDiagram
    participant U as Trình duyệt A
    participant S as Spring Security
    participant Store as Session store
    U->>S: POST /login + credentials + CSRF token
    S->>S: Xác thực người dùng
    S->>Store: Tạo/cập nhật SecurityContext trong HttpSession
    S-->>U: Set-Cookie: JSESSIONID=...; HttpOnly; ...
    U->>S: GET /api/me + Cookie: JSESSIONID=...
    S->>Store: Tìm phiên theo ID, kiểm tra còn hợp lệ
    Store-->>S: SecurityContext
    S-->>U: Thông tin tài khoản được phép xem
```

Trong cấu hình mặc định của Servlet container, cookie thường tên **JSESSIONID**. Nó là **session identifier**, không phải mật khẩu; nhưng kẻ tấn công giữ được ID còn hiệu lực có thể thử sử dụng để chiếm phiên, vì vậy phải coi giá trị này là **bí mật xác thực có độ nhạy cao**. Không đưa ID lên URL, log, telemetry công khai hoặc trả raw ID qua API liệt kê thiết bị.

Backend lưu `HttpSession`, có thể chứa `SecurityContext` do Spring Security quản lý. Dựa vào session store, server có thể biết phiên còn tồn tại, đã hết hạn, bị đánh dấu expired hay đã bị xóa.

### 2.2. Một người dùng ≠ một phiên ≠ một thiết bị

| Khái niệm | Ví dụ | Điều cần nhớ |
| --- | --- | --- |
| User/account | alice | Một danh tính có thể có nhiều phiên |
| Session | Phiên đăng nhập sau một lần form login | Gắn với trạng thái phía server và ID trong cookie |
| Cookie | `JSESSIONID=...` trên browser profile A | Browser gửi lại để server tìm session |
| Thiết bị vật lý | Laptop | Nhiều profile hoặc browser có thể là nhiều phiên |
| Tab cùng browser profile | Tab 1, Tab 2 | Thường chia sẻ cùng cookie/phiên |
| Remember-me token | Cookie nhớ đăng nhập lâu dài | Có thể tự xác thực lại khi session hết, cần thu hồi riêng |
| Access token JWT | Bearer token | Nếu xác thực stateless, không phải `HttpSession` |

Không thể xác định một thiết bị duy nhất chỉ bằng `User-Agent` hoặc IP: các giá trị này có thể trùng, đổi hoặc giả mạo. Khi hiển thị “Thiết bị của tôi”, nên nói rõ đây là **phiên đăng nhập/thiết bị được nhận diện gần đúng**; nếu cần định danh ổn định, thiết kế device registration riêng với rủi ro quyền riêng tư được đánh giá.

## 3. Chính sách concurrent sessions trong Spring Security

Với **Spring MVC/Servlet**, Spring Security hỗ trợ **concurrent session control**. Hai ví dụ thường gặp:

```java
// Mẫu cấu hình bên trong HttpSecurity.sessionManagement(...)
.maximumSessions(2)
.maxSessionsPreventsLogin(false)
```

Ý nghĩa:

- Tối đa **hai phiên** đăng nhập được theo dõi cho một principal.
- Khi login thứ ba thành công, Spring Security có thể đánh dấu phiên cũ ít được sử dụng hơn là hết hiệu lực để nhường phiên mới. Phiên cũ thường được xử lý bởi `ConcurrentSessionFilter` khi nó có request tiếp theo.
- `maxSessionsPreventsLogin(false)` là chiến lược cho phép login mới và làm hết hạn phiên cũ theo giới hạn; không có nghĩa toàn bộ trình duyệt nhận thông báo ngay lập tức.

Ngược lại:

```java
// Từ chối login mới khi đã đủ hai phiên đang hoạt động.
.maximumSessions(2)
.maxSessionsPreventsLogin(true)
```

Khi đã đạt giới hạn, hệ thống ngăn một lần đăng nhập mới thay vì đẩy phiên cũ ra. Với form login, ứng dụng thường báo qua authentication failure flow; không nên khẳng định mọi cơ chế xác thực đều trả cùng một HTTP status.

**Quyết định sản phẩm:** Với ứng dụng văn phòng, nhiều khi cho phép login mới và thu hồi phiên cũ giúp người dùng không bị khóa do quên đăng xuất. Với tài chính/ứng dụng nhạy cảm, có thể yêu cầu MFA và xác nhận quyền trước khi thay đổi các phiên. Số phiên nên là chính sách nghiệp vụ có test rõ ràng, không phải con số tự chọn tùy tiện.

### 3.1. SessionRegistry là nơi theo dõi các phiên

`org.springframework.security.core.session.SessionRegistry` cung cấp các phương thức như:

- `getAllSessions(principal, includeExpiredSessions)`: tìm phiên đã đăng ký của một principal.
- `getSessionInformation(sessionId)`: tra thông tin một phiên.
- `SessionInformation.getLastRequest()`: lần request được ghi nhận gần nhất.
- `SessionInformation.expireNow()`: **đánh dấu phiên là expired**, không phải API trực tiếp xóa dữ liệu cookie ở mọi browser.
- `refreshLastRequest(sessionId)` và `registerNewSession(...)`: cập nhật vòng đời phiên.

Một triển khai đơn nút thường dùng `SessionRegistryImpl` lưu registry trong bộ nhớ. Khi session bị hủy do timeout/logout, `HttpSessionEventPublisher` phát sự kiện để registry loại bỏ thông tin không còn hợp lệ.

**Hạn chế:** `SessionRegistryImpl` trên từng JVM không phải kho phiên phân tán. Nếu ứng dụng chạy nhiều instance mà không dùng cơ chế session/registry chung, phiên A được tạo tại node 1 và phiên B tại node 2 có thể không được nhìn nhận nhất quán. Một cấu hình giới hạn “hai phiên” ở node đơn **không tự biến thành chính sách toàn cụm**.

### 3.2. Đánh dấu expired và xóa session khác nhau thế nào?

Có hai kiểu thao tác nên phân biệt:

1. **Mark expired (`SessionInformation.expireNow()`):** Gắn cờ cho registry. Với bộ lọc đồng thời, request tiếp theo của session đó được phát hiện và từ chối/invalidate theo chiến lược hết hạn. Một request đang xử lý có thể đã qua bước kiểm tra; người dùng không nhất thiết bị “đá ra” tức thời qua kênh push.
2. **Delete/invalidate server-side session:** Xóa dữ liệu phiên khỏi kho dùng chung bằng session repository hoặc invalidate chính phiên hiện tại. Request sau đó không còn `SecurityContext` hợp lệ để tiếp tục truy cập. Cần cân nhắc concurrent requests, cache và xử lý đang bay.

Vì thế, API sản phẩm nên dùng diễn đạt chính xác như **“đã đánh dấu các phiên khác để thu hồi; quyền sẽ bị chặn ở request tiếp theo”** nếu chỉ gọi `expireNow()`, thay vì hứa phiên đã biến mất ở mọi nơi ngay tại thời điểm response 200.

## 4. Xác định yêu cầu thu hồi truy cập trước khi viết code

| Sự kiện | Phạm vi thường mong muốn | Cách thực hiện ở tầng session |
| --- | --- | --- |
| Người dùng nhấn “Đăng xuất” | Phiên hiện tại | Spring Security logout, invalidate session, xóa cookie |
| Nhấn “Đăng xuất thiết bị khác” | Các phiên của tài khoản, trừ hiện tại | Tra registry/repository, expire/delete từng session khác |
| Nhấn “Đăng xuất tất cả” | Mọi phiên của tài khoản | Thu hồi các session khác rồi logout phiên hiện tại |
| Đổi mật khẩu do nghi ngờ lộ | Thường toàn bộ phiên cũ | Revocation toàn tài khoản và yêu cầu xác thực lại |
| Tài khoản bị disable/thu hồi role | Mọi phiên không còn đủ điều kiện | Thu hồi session/token + kiểm tra tài khoản/quyền mới |
| Phát hiện cookie bị đánh cắp | Ít nhất session bị lộ, có thể tất cả | Vô hiệu hóa server-side, audit và đổi credentials khi cần |
| Session timeout do không hoạt động | Một phiên | Server hết hạn phiên theo idle timeout |
| Người dùng đổi thiết bị, phiên vượt limit | Một hoặc nhiều phiên cũ | Concurrent session control với chính sách rõ ràng |

**Không trộn lẫn logout và permission revocation:** Nếu vai trò của Alice bị giảm từ ADMIN xuống USER nhưng `SecurityContext` cũ vẫn giữ authorities trước đây, ứng dụng có thể tiếp tục dựa trên thông tin cũ đến khi refresh/re-authentication. Thu hồi session hoặc áp cơ chế kiểm tra version/quyền hiện hành khi request quan trọng là bước bắt buộc trong hệ thống cần cập nhật quyền tức thì.

## 5. Ví dụ hoàn chỉnh: giới hạn hai phiên và thu hồi các phiên khác

Ta xây dựng ứng dụng Spring Boot Servlet có:

- `POST /login` do Spring Security form login xử lý;
- `GET /api/me` chỉ trả username, **không trả session ID**;
- `GET /api/sessions` hiển thị các phiên đang được registry theo dõi, chỉ có cờ phiên hiện tại và thời điểm hoạt động gần nhất;
- `POST /api/sessions/revoke-others` đánh dấu expired tất cả phiên của **người dùng đã xác thực** ngoại trừ phiên đang gọi;
- `POST /logout` dùng logout handler chuẩn, yêu cầu CSRF token khi CSRF bật.

Tài khoản demo `alice` đăng nhập tối đa hai phiên tại cùng JVM. Code phục vụ học tập/local, không phải dịch vụ quản lý thiết bị production.

### 5.1. Cấu trúc project

```text
multi-session-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/sessions/
    │   │   ├── MultiSessionApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── SessionController.java
    │   └── resources/application.properties
    └── test/java/demo/sessions/
        └── SessionRevocationTest.java
```

Dùng JDK 17+ và Maven 3.9+. Spring Boot parent cố định để nguồn dễ thử lại; khi sử dụng thực tế phải cập nhật phiên bản bảo trì/bản vá tương thích đang được hỗ trợ.

### 5.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>multi-session-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
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

### 5.3. Khởi động ứng dụng

`src/main/java/demo/sessions/MultiSessionApplication.java`:

```java
package demo.sessions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(MultiSessionApplication.class, args);
    }
}
```

### 5.4. SecurityConfig: một registry, form login và limit hai phiên

`src/main/java/demo/sessions/SecurityConfig.java`:

```java
package demo.sessions;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, SessionRegistry registry) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId())
                .maximumSessions(2)
                .maxSessionsPreventsLogin(false)
                .sessionRegistry(registry)
            )
            .logout(logout -> logout
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
            )
            .build();
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
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-demo"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-demo"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }
}
```

**Giải thích từng cấu phần:**

- `formLogin` dùng xác thực theo form và lưu `SecurityContext` vào session theo cấu hình chuẩn.
- `sessionFixation(...changeSessionId())` thay ID phiên sau khi xác thực thành công; không tái sử dụng ID chưa xác thực do kẻ khác có thể kiểm soát. Đây cũng là biện pháp giúp giảm nguy cơ session fixation.
- `maximumSessions(2)` cho phép tối đa hai phiên được theo dõi cho cùng principal.
- `maxSessionsPreventsLogin(false)` cho phép phiên mới và đánh dấu phiên cũ vượt limit là expired.
- `sessionRegistry(registry)` yêu cầu Spring Security và controller cùng dùng **một** registry.
- `HttpSessionEventPublisher` thông báo sự kiện session destroyed để thông tin registry có thể được cập nhật khi session bị invalidate hoặc timeout.
- `logout` giữ hành vi vô hiệu hóa session và xóa cookie của **trình duyệt hiện tại**, không tự gọi chức năng “đăng xuất các phiên khác”.
- `anyRequest().denyAll()` tránh vô tình mở endpoint chưa phê duyệt. Cấu hình thực tế cần bổ sung public assets, trang login tùy chỉnh, v.v. theo yêu cầu thật.

**Lưu ý:** `SessionRegistryImpl` in-memory chỉ phù hợp **đơn JVM** để demo. Trong cluster, dùng session store và registry phù hợp như Spring Session; giới hạn phiên có thể sai nếu mỗi instance tự giữ registry riêng. Khi dùng custom `UserDetails` làm principal, cần triển khai `equals()/hashCode()` nhất quán, vì `SessionRegistryImpl` lưu principal làm key.

### 5.5. API liệt kê và thu hồi phiên khác, không rò rỉ session ID

`src/main/java/demo/sessions/SessionController.java`:

```java
package demo.sessions;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class SessionController {

    private final SessionRegistry registry;

    public SessionController(SessionRegistry registry) {
        this.registry = registry;
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/sessions")
    public List<SessionView> list(
            Authentication authentication, HttpSession current) {

        return registry.getAllSessions(
                    authentication.getPrincipal(), false)
            .stream()
            .map(info -> new SessionView(
                info.getSessionId().equals(current.getId()),
                info.getLastRequest().toInstant()))
            .toList();
    }

    @PostMapping("/sessions/revoke-others")
    public Map<String, Integer> revokeOtherSessions(
            Authentication authentication, HttpSession current) {

        int marked = 0;

        for (SessionInformation info : registry.getAllSessions(
                authentication.getPrincipal(), false)) {

            if (!info.getSessionId().equals(current.getId())) {
                info.expireNow();
                marked++;
            }
        }

        return Map.of("markedForExpiration", marked);
    }

    public record SessionView(boolean current, Instant lastRequest) {
    }
}
```

Đây là mô hình có chủ đích để tránh **IDOR trên chức năng quản lý session**:

1. Controller không nhận username cần thu hồi từ request; nó luôn dùng `authentication.getPrincipal()`.
2. Không trả `SessionInformation.getSessionId()` cho client, vì đây là giá trị nhạy cảm có thể đóng vai trò session credential.
3. Khi chọn “revoke others”, chỉ các phiên của **chính principal hiện tại** được xét; không nhận danh sách ID do client tự gửi.
4. So sánh ID session hiện tại **ở server** để giữ phiên gọi lệnh.
5. `expireNow()` là **đánh dấu để thu hồi**, nên tên response là `markedForExpiration`, tránh tuyên bố đã xóa tức thì ở mọi store.
6. Tính năng “hiển thị phiên” này chỉ cung cấp `current` và `lastRequest`; nếu cần chọn một phiên cụ thể, phải có **public opaque handle không phải session token**, ánh xạ server-side và kiểm tra owner trước khi thu hồi.

Trong sản phẩm thật, chức năng thu hồi toàn bộ phiên là thao tác nhạy cảm; nên yêu cầu recent authentication/MFA cho tài khoản rủi ro cao, chống CSRF và chống lạm dụng (rate limit). Cần có audit bảo mật, thông báo nếu chính sách yêu cầu, nhưng không log session ID/cookie thô.

### 5.6. Cấu hình session timeout cho demo

`src/main/resources/application.properties`:

```properties
server.servlet.session.timeout=30m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

Đây chỉ là thiết lập local sử dụng HTTP. Ở production phải chạy **HTTPS** và bật cookie **Secure**, ví dụ:

```properties
# Môi trường production qua HTTPS:
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.timeout=30m
```

Với cookie session:

- **Secure**: browser chỉ gửi cookie qua HTTPS. Không nên tắt trong production.
- **HttpOnly**: hạn chế JavaScript đọc cookie; không chặn mọi kiểu XSS, nên vẫn phải chống XSS.
- **SameSite=Lax/Strict/None**: hỗ trợ hạn chế một số kịch bản cross-site; `SameSite=None` cần `Secure`. Không coi SameSite là thay thế CSRF protection.
- **Path/Domain**: phạm vi cookie phải tối thiểu cần thiết; chú ý các app trên cùng domain.
- **Timeout**: giới hạn thời gian không hoạt động của session; trong bài dùng 30 phút. Nếu có yêu cầu “thời gian phiên tối đa tuyệt đối” thì cần chính sách riêng vì idle timeout không phải absolute lifetime.

Tùy hệ thống, tên cookie có thể là `JSESSIONID` hoặc `SESSION` (ví dụ Spring Session). Khi đổi session store, phải xác định tên cookie thực tế, không hardcode tên cũ trong thao tác xóa cookie của browser.

## 6. Kiểm thử bằng Spring Security Test và MockMvc

Mục tiêu không chỉ kiểm tra login thành công, mà còn chứng minh:

1. Hai phiên riêng biệt của cùng tài khoản tồn tại cùng lúc.
2. Mỗi session dùng cookie/định danh riêng.
3. Lệnh “revoke others” tại phiên B đánh dấu phiên A.
4. Phiên A bị từ chối trong **request tiếp theo**, nhưng phiên B vẫn truy cập bình thường.
5. Anonymous không được gọi API quản lý session.

`src/test/java/demo/sessions/SessionRevocationTest.java`:

```java
package demo.sessions;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionRevocationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void twoSessionsAndRevokeOthers() throws Exception {

        MvcResult firstLogin = mvc.perform(formLogin()
                .user("alice").password("alice-demo"))
            .andExpect(authenticated())
            .andReturn();

        MockHttpSession first = (MockHttpSession)
            firstLogin.getRequest().getSession(false);

        MvcResult secondLogin = mvc.perform(formLogin()
                .user("alice").password("alice-demo"))
            .andExpect(authenticated())
            .andReturn();

        MockHttpSession second = (MockHttpSession)
            secondLogin.getRequest().getSession(false);

        assertThat(first).isNotNull();
        assertThat(second).isNotNull();
        assertThat(first.getId()).isNotEqualTo(second.getId());

        mvc.perform(get("/api/me").session(first))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));

        mvc.perform(get("/api/me").session(second))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));

        mvc.perform(post("/api/sessions/revoke-others")
                .session(second)
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.markedForExpiration").value(1));

        MvcResult expired = mvc.perform(
                get("/api/me").session(first))
            .andReturn();

        // Không ràng buộc vào redirect/status cụ thể của strategy.
        // Bất biến bảo mật: phiên cũ không còn GET /api/me thành công.
        assertThat(expired.getResponse().getStatus()).isNotEqualTo(200);
        assertThat(expired.getResponse().getContentAsString())
            .doesNotContain("alice");

        mvc.perform(get("/api/me").session(second))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void anonymousCannotManageSessions() throws Exception {
        mvc.perform(get("/api/sessions"))
            .andExpect(status().is3xxRedirection());
    }
}
```

**Giải thích điểm cần thận trọng:**

- `formLogin()` là request builder của Spring Security Test có thể thực hiện flow xác thực trong MockMvc; hai lần login không chuyển session cũ sang request mới, vì thế tạo hai `MockHttpSession` riêng.
- `@AutoConfigureMockMvc` đưa security filter chain vào integration test của Spring Boot.
- `with(csrf())` bắt buộc để request POST vượt qua CSRF filter; nếu thiếu, việc bị 403 chỉ chứng minh CSRF hoạt động chứ không chứng minh chính sách session đã chạy.
- Test cố ý **không so sánh HTTP status chính xác** của request từ phiên hết hạn: chiến lược expired session có thể trả redirect hoặc lỗi khác. Bất biến là không đọc được endpoint nhạy cảm và không rò rỉ payload.
- Với form login mặc định, request anonymous tới API có thể redirect về trang login (một tình huống phổ biến của browser app). Khi cấu hình API entry point trả 401, kết quả cần đổi theo hợp đồng API.
- Bộ test đơn giản dùng registry in-memory và giả lập HTTP qua MockMvc; muốn kiểm tra cookie Set-Cookie, timeout thực, sticky session, nhiều node và race phải có bài test tích hợp với container/store/hạ tầng tương ứng.

**Chạy:**

```bash
mvn test
mvn spring-boot:run
```

Với JDK 17+ và Maven đã cài, kết quả kỳ vọng là hai test method trong class `SessionRevocationTest` chạy thành công khi ứng dụng dùng đúng cấu hình và không có tài nguyên cổng hoặc test khác gây ảnh hưởng. Đây là **kỳ vọng dựa trên mã ví dụ**, không phải log build đã thực thi trong bài học này.

### 6.1. Thử thủ công với hai browser profile

1. Mở browser profile A ở `http://localhost:8080/login`; đăng nhập `alice` / `alice-demo`.
2. Mở browser profile B độc lập hoặc một cửa sổ private thật sự với cookie jar khác; đăng nhập cùng tài khoản.
3. Cả hai có thể truy cập `http://localhost:8080/api/me`.
4. Ở B, gửi request **POST** tới `/api/sessions/revoke-others` kèm CSRF token hợp lệ. Không chỉ gõ URL vào thanh địa chỉ vì thao tác này dùng POST và cần CSRF.
5. Ở A, refresh `/api/me`; request tiếp theo phải bị từ chối hoặc đưa về login. Ở B, refresh vẫn phải thành công.

Nếu mở hai tab trong **cùng một browser profile**, chúng thường chia sẻ cookie/phiên, không phải hai thiết bị logic. Nếu muốn thử bằng `curl`, hãy quản lý **hai cookie jar độc lập** và phải xử lý CSRF/form flow; thao tác form login thường không thể mô phỏng đầy đủ chỉ với một lệnh GET.

## 7. Chính sách “đăng xuất” và “thu hồi các phiên khác”

### 7.1. Logout phiên hiện tại

Spring Security logout thông thường xử lý POST `/logout` (khi CSRF bật), gọi logout handlers để dọn security context và invalidate `HttpSession`; controller custom không nên chỉ xóa cookie mà bỏ qua server state. Với servlet app, cấu hình:

```java
// Đoạn cấu hình nằm trong HttpSecurity DSL.
.logout(logout -> logout
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("JSESSIONID")
)
```

Việc đặt `Set-Cookie` để cookie hết hạn tại client có thể phụ thuộc Path/Domain/container. Luôn test trên browser thực, đặc biệt khi dùng reverse proxy và nhiều ứng dụng chung domain. Có thể cân nhắc `Clear-Site-Data` cho chính sách logout phù hợp với phạm vi domain.

### 7.2. Revoke all: đừng xóa phiên hiện tại trước khi xử lý các phiên khác

Luồng nghiệp vụ hợp lý:

```text
POST /account/logout-all
    -> xác thực lại/MFA nếu chính sách yêu cầu
    -> xác định principal từ SecurityContext
    -> lấy toàn bộ session hợp lệ của principal
    -> thu hồi session khác (mark expired hoặc delete ở store)
    -> logout/invalidate session hiện tại bằng LogoutHandler
    -> trả xác nhận và audit, không trả raw session IDs
```

**Tránh** API nhận username ở body rồi xóa mọi phiên của username đó, nếu caller không có đặc quyền thích hợp. Đó có thể trở thành lỗ hổng khiến người dùng tùy ý đăng xuất người khác. Nếu quản trị viên được phép thu hồi phiên của user khác, cần kiểm tra role, tenant, lý do và audit chặt chẽ.

### 7.3. Thu hồi chỉ một phiên được chọn

Có thể cho người dùng chọn một mục “MacBook • vừa hoạt động” trong UI, nhưng API **không nên trả raw `JSESSIONID`** để làm ID lựa chọn. Hãy dùng bảng metadata:

```text
session_handle (UUID ngẫu nhiên, không phải credential)
owner_user_id
session_id (bí mật, chỉ lưu server-side)
created_at
last_seen_at
device_label
revoked_at
```

Khi `POST /account/sessions/{handle}/revoke`:

1. Bắt buộc caller đã xác thực, kiểm tra CSRF/MFA khi phù hợp.
2. Tra `handle` có thuộc **chính user/tenant** hay không.
3. Lấy session ID bí mật **chỉ trong backend**.
4. Thu hồi tại session store/registry và ghi audit.
5. Không tiết lộ handle khác, session ID, IP đầy đủ hoặc account metadata của người khác.

Handle dù không phải credential vẫn phải khó đoán và được kiểm tra sở hữu; một ID khó đoán không thay thế authorization.

## 8. Spring Session + Redis cho nhiều instance

Ví dụ `SessionRegistryImpl` của mục 5 chỉ theo dõi phiên trong một JVM. Trong hệ thống load-balanced chạy hai hoặc nhiều backend, cần **session store chung** và **registry tích hợp** để cả cụm thấy cùng các phiên.

Spring Session có thể lưu `HttpSession` vào Redis. Với Spring Boot, một cách cấu hình phụ thuộc thường dùng là:

```xml
<!-- Bổ sung dependency vào pom.xml của ứng dụng khi triển khai Redis -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-session-data-redis</artifactId>
</dependency>
```

Spring Boot auto-configuration sẽ thêm filter Spring Session phù hợp khi cấu hình store đáp ứng điều kiện. Một số thành phần cấu hình cần có Redis server hoạt động, credentials quản lý an toàn, namespace riêng, network TLS nếu hỗ trợ và chính sách TTL.

**Cấu hình minh họa** (không ghép với demo local nếu chưa chạy Redis):

```properties
spring.data.redis.host=redis.internal.example
spring.data.redis.port=6379
spring.session.redis.namespace=myapp:session
server.servlet.session.timeout=30m
```

Hostname trên chỉ là **ví dụ tài liệu**. Spring Session thường dùng cookie tên `SESSION`; hãy xác nhận cookie thực tế, không suy luận theo demo `JSESSIONID`.

### 8.1. SpringSessionBackedSessionRegistry

Nếu dùng `FindByIndexNameSessionRepository` của Spring Session, Spring Security có thể tích hợp concurrent session control bằng registry phân tán:

```java
// Mã minh họa tích hợp, không là class độc lập chạy trong demo local.
@Autowired
FindByIndexNameSessionRepository<? extends Session> repository;

// Khởi tạo SpringSessionBackedSessionRegistry bằng repository phù hợp.
// Sau đó truyền instance làm SessionRegistry cho HttpSecurity.sessionManagement(...).
```

Trong dự án thực, khai báo generic type và bean theo loại session repository cụ thể (ví dụ IndexedSessionRepository của Redis) và xem tài liệu của phiên bản đang sử dụng. **Không vừa giữ `SessionRegistryImpl` local vừa nghĩ rằng Spring Session cookie tự biến mọi thông tin registry thành toàn cụm**.

Spring Session cung cấp cách tìm phiên theo username đã lưu index và xóa bằng ID trong shared store. Mô hình kiểm tra chủ sở hữu trước khi xóa:

```java
// Pseudocode, repository có kiểu FindByIndexNameSessionRepository<S>.
Map<String, S> owned = repository.findByPrincipalName(currentUsername);
for (String id : owned.keySet()) {
    if (!id.equals(currentSessionId)) {
        repository.deleteById(id);
    }
}
```

Phần trên là **pseudocode Java**, không phải file biên dịch độc lập: cần khai báo generic `S extends Session`, repository và authenticated username từ nguồn đáng tin cậy. Không được xóa ID chưa kiểm chứng thuộc đúng principal. Với Spring Session, xóa phiên trực tiếp ở store làm request tiếp theo không còn tìm được trạng thái hợp lệ; request đang chạy vẫn cần được thiết kế an toàn nếu thao tác nhạy cảm diễn ra đồng thời.

### 8.2. Tính nhất quán, timeouts và độ tin cậy

- **Nhiều node:** test login qua node A, request qua B, revoke qua C rồi request tiếp qua A/B. Không chỉ test sticky-session trên một instance.
- **Session index:** cách tìm “mọi session của principal” phụ thuộc index phù hợp trong store. Nếu đổi serializer hoặc thủ tục authentication, phải đảm bảo index username/owner được cập nhật.
- **TTL và cleanup:** session expired không nhất thiết được xóa vật lý ngay cùng thời điểm; hiểu cơ chế cleanup/TTL của Redis và sự kiện hết hạn.
- **Race:** login mới và revoke-all cùng lúc có thể tạo session mới sau khi danh sách để revoke được lấy. Với yêu cầu chặt (security incident), dùng **account session epoch/version** hoặc cơ chế generation để mọi request so sánh với mốc revocation trung tâm.
- **Failure mode:** khi kho phiên/permission không khả dụng, không được âm thầm xem session là hợp lệ chỉ vì cache local còn dữ liệu; định nghĩa fail-closed phù hợp với độ nhạy và khả dụng hệ thống.
- **Giới hạn đồng thời:** `maximumSessions` là cơ chế ngăn nhiều phiên tại đăng nhập, **không phải** ranh giới bảo mật duy nhất thay cho policy thu hồi theo từng request.

## 9. Thu hồi quyền mạnh hơn bằng session version/epoch

Đối với yêu cầu “tài khoản bị khóa hoặc đổi mật khẩu thì mọi thiết bị mất quyền ở request tiếp theo”, có thể dùng **version** hoặc timestamp do server quản lý:

```text
User:
    id = alice
    securityVersion = 9

Session:
    principal = alice
    issuedSecurityVersion = 8

Request:
    session exists AND
    user.enabled == true AND
    session.issuedSecurityVersion == user.securityVersion
      -> accept
    else
      -> deny and invalidate
```

Khi cần revoke-all, tăng `securityVersion` ở kho dữ liệu nhất quán. Mọi phiên có version cũ đều bị từ chối khi request tiếp theo được kiểm tra. Đây là **mẫu thiết kế**, không phải một tính năng Spring Security tự bật khi bạn thêm trường vào entity. Cần tạo filter/authorization check đúng vị trí, chọn nguồn tra version đáng tin cậy và thiết kế cache invalidation/độ trễ mong muốn.

Ưu điểm: giảm nguy cơ bỏ sót phiên mới phát sinh đồng thời với thao tác liệt kê rồi xóa. Nhược điểm: mỗi request nhạy cảm cần biết version hiện hành; nếu cache quá lâu, “thu hồi tức thì” chỉ là lời hứa không đúng.

Nếu chỉ muốn revoke **một** session nhưng giữ các session khác, cần trạng thái theo session (revocation list/session store) hoặc epoch riêng cho thiết bị; một account-wide version sẽ đăng xuất tất cả.

## 10. Trường hợp đặc biệt: JWT access token và refresh token

Không nhầm **server-side session** với **JWT stateless**:

| Tính chất | HttpSession + cookie | JWT access token tự xác minh chữ ký |
| --- | --- | --- |
| Dữ liệu xác thực chính | Session tại server | Claims đã ký trong token |
| Cookie/browser | Cookie ID session | Có thể gửi Bearer header hoặc cookie tùy thiết kế |
| Revoke một phiên | Xóa/expire session ở server | Không tự xóa được JWT đã phát hành nếu verifier chỉ kiểm chữ ký/hạn |
| Revoke mọi thiết bị | Tìm session hoặc version | Thu hồi refresh token + denylist/version/introspection cho access token nếu cần tức thì |
| Multi-node | Cần store chung hoặc mô hình phù hợp | Có thể stateless, nhưng revocation mạnh cần state bổ sung |
| Xác minh mỗi request | Đọc session/security context | Kiểm chữ ký, issuer, audience, expiry và quyền phù hợp |

Nếu access token JWT còn hạn sử dụng và resource server **chỉ kiểm chữ ký và `exp`**, việc “logout” trên một browser hoặc xóa refresh token ở authorization server **không khiến access JWT cũ tự ngừng hợp lệ ngay**. Các lựa chọn:

1. **Access token ngắn hạn** và refresh token rotation: giảm cửa sổ token bị lộ, nhưng không thu hồi access token ngay tại thời điểm logout.
2. **Refresh token revocation** tại authorization server theo session/device/grant; kiểm soát khả năng lấy access token mới. Cần xử lý replay và rotation đúng.
3. **Denylist `jti` / token ID**, hoặc **per-user tokenVersion/security epoch** được resource server kiểm tra trên mỗi request: hỗ trợ thu hồi gần tức thì nếu hệ thống phân tán và cache có độ trễ phù hợp.
4. **Token introspection** cho opaque tokens hoặc kiến trúc validation có state: authorization server có thể trả token không còn active, đổi lại chi phí gọi mạng và yêu cầu HA.
5. **OIDC logout/back-channel logout** trong hệ sinh thái SSO: logout khỏi IdP không tự động bảo đảm mọi ứng dụng giữ session cục bộ và JWT đều bị xóa, trừ khi các cơ chế liên quan được triển khai/truyền sự kiện đầy đủ.

**Nguyên tắc:** Với chính sách yêu cầu thu hồi thật nhanh, phải xác định **độ trễ thu hồi tối đa được chấp nhận** và cách mỗi resource server kiểm tra revocation. Đừng mô tả “xóa refresh token = tất cả access token đã lập tức vô hiệu” khi điều đó không đúng.

## 11. Mất thiết bị, đổi mật khẩu và sự cố chiếm phiên

### 11.1. Mất thiết bị

Khi người dùng thông báo mất điện thoại:

1. Bảo vệ tài khoản hiện tại bằng MFA/reauthentication hợp lý nếu có điều kiện.
2. Thu hồi session có thể bị lộ hoặc toàn bộ session, tùy rủi ro và khả năng xác định đúng thiết bị.
3. Thu hồi remember-me/refresh tokens liên quan và reset các kênh đăng nhập “nhớ thiết bị” nếu cần.
4. Kiểm tra hoạt động bất thường, sự kiện đăng nhập mới và quyền đã thay đổi.
5. Thông báo rõ phiên nào được thu hồi, thời điểm gần đúng và bước cần thực hiện tiếp.

Nếu kẻ tấn công có **mật khẩu vẫn hợp lệ**, họ có thể đăng nhập lại sau khi bị kick. Vì vậy, revoke session đôi khi phải đi kèm đổi mật khẩu/MFA và khóa nguồn credential bị lộ.

### 11.2. Đổi mật khẩu

Không có một bảo đảm phổ quát rằng “đổi mật khẩu sẽ tự invalidate mọi session đã đăng nhập” trong mọi cấu hình Spring Security. Phải chọn và triển khai hành vi sản phẩm:

- Giữ phiên hiện tại, thu hồi tất cả phiên khác?
- Thu hồi cả phiên hiện tại rồi yêu cầu login lại?
- Yêu cầu MFA và rotation remember-me/refresh token?
- Thay security version để mọi session/token cũ không hợp lệ?

Nếu ứng dụng có các bước thanh toán, chuyển tiền hoặc cấp quyền admin, có thể cần **fresh authentication** ngay cả khi session được cho phép tiếp tục.

### 11.3. Tài khoản bị disable hoặc thay đổi role

Một phiên đã authenticated có thể lưu `SecurityContext` với authorities cũ. Nếu chỉ sửa bản ghi user.enabled hoặc roles trong database mà không thu hồi phiên hoặc không đánh giá quyền hiện hành, request sau có thể vẫn hoạt động theo context trước đó. Thiết kế cần:

- Revoke phiên/tokens của user bị disable;
- Bảo đảm route/operation quan trọng tra trạng thái hoặc version đúng thời điểm;
- Có monitoring, audit và kiểm thử sau thay đổi role để không sử dụng authorities stale.

### 11.4. Ranh giới giữa revoke và request đang chạy

Nếu một request chuyển tiền đã qua authorization rồi, sau đó admin thu hồi session cùng lúc, việc xóa session **không tự rollback** lệnh thanh toán đang thực hiện. Với hành động cực kỳ nhạy cảm, cần kiểm tra quyền ở điểm commit/ghi cuối, transaction, idempotency và điều kiện trạng thái phù hợp. Không hứa “revoke đồng nghĩa mọi công việc đang chạy đều bị hủy”.

## 12. Các lỗi phổ biến

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Xóa cookie trong browser rồi gọi là logout toàn bộ thiết bị | Các session khác vẫn sống ở server | Thu hồi session trong store, phạm vi theo principal |
| Trả raw session ID trong API “thiết bị” | Lộ thông tin xác thực cực nhạy cảm | Dùng handle riêng không phải credential, không log raw ID |
| Dùng `SessionRegistryImpl` trong multi-node không chia sẻ state | Limit/revoke khác nhau giữa node | Spring Session + shared registry hoặc thiết kế phân tán tương đương |
| Gọi `expireNow()` rồi khẳng định dữ liệu session đã xóa ngay | Registry chỉ đánh dấu expired | Phân biệt mark expired và delete/invalidate, test request tiếp theo |
| Nhận `username` hoặc `sessionId` không kiểm quyền từ body | User có thể thu hồi phiên người khác | Lấy principal từ SecurityContext; kiểm tra owner trước khi xóa |
| Coi hai tab cùng browser là hai thiết bị | Tab thường dùng chung cookie | Test hai cookie jar/profile độc lập |
| Không bật CSRF nhưng dùng cookie auth trong browser | Có thể bị request giả mạo thu hồi phiên/thao tác khác | Giữ CSRF phù hợp, test `csrf()` |
| Chỉ giới hạn số phiên, không có cơ chế revoke khẩn cấp | Không đáp ứng sự cố mất thiết bị | Thiết kế logout others/all và session/token version |
| Dùng `User-Agent` làm định danh quyền duy nhất | Dễ giả mạo/thay đổi | Metadata hiển thị chỉ tham khảo; quyền nằm ở server |
| Không cập nhật registry sau timeout/logout | Đếm sai phiên đang hoạt động | `HttpSessionEventPublisher` hoặc lifecycle integration phù hợp |
| Nhầm `maxSessionsPreventsLogin(true)` với expire phiên cũ | Chiến lược là ngăn login mới | Chọn đúng hành vi sản phẩm |
| Thu hồi refresh token rồi tuyên bố JWT access token vô hiệu ngay | Access token vẫn được chấp nhận đến hết `exp` nếu stateless | Denylist/introspection/version hoặc TTL ngắn |
| Đổi password nhưng không kiểm lại authorities/session | Phiên cũ có thể dùng quyền stale | Revoke hoặc kiểm tra user security epoch/role |
| Đổi cookie `JSESSIONID` thành `SESSION` mà logout vẫn xóa tên cũ | Cookie trình duyệt có thể còn | Kiểm tra tên cookie thực tế và invalidate server-side |
| Session cookie thiếu `Secure`/`HttpOnly` | Tăng nguy cơ rò rỉ cookie | Cấu hình đúng trên HTTPS; bảo vệ XSS/CSRF |
| Chỉ test local một JVM | Không phát hiện lỗi đồng bộ giữa node | Integration test qua load balancer và Redis |
| Log `Cookie` header hoặc session ID | Lộ credential và tăng rủi ro chiếm phiên | Redact/omit credential; audit sự kiện thay vì giá trị token |

## 13. Ma trận kiểm thử nên có trong dự án thực

| Ca kiểm thử | Mong đợi |
| --- | --- |
| Browser A và B đăng nhập cùng account | Hai phiên độc lập, cùng principal |
| Mở thêm tab trong browser A | Thường dùng cùng session; không tăng số phiên |
| Giới hạn 2, login thứ ba, chế độ expire old | Phiên cũ không truy cập được ở request tiếp theo |
| Giới hạn 2, chế độ prevent new | Login mới bị từ chối; phiên cũ còn hợp lệ |
| Logout tại browser A | A hết quyền; B vẫn hoạt động nếu policy là current-only |
| Revoke others tại browser B | A hết quyền, B tiếp tục hợp lệ |
| Revoke all | A/B và phiên gọi lệnh đều hết quyền |
| POST revoke thiếu CSRF token | Bị từ chối theo chính sách CSRF, không thu hồi nhầm |
| Bob cố thu hồi session của Alice | Bị từ chối, Alice không bị ảnh hưởng |
| Session hết hạn do idle timeout | Không dùng được SecurityContext cũ |
| Password change với revoke-all policy | Token/session cũ mất quyền theo SLA |
| User bị disable | Không truy cập được bằng session cũ |
| Thay role | Không giữ quyền đã thu hồi quá SLA |
| Revoke tại node A, gọi lại qua B/C | Quyền đã bị thu hồi nhất quán |
| Cookie bị sao chép và sử dụng lại sau revoke | Không truy cập được; có audit nếu cần |
| JWT còn hạn sau refresh revocation | Hiểu rõ cửa sổ còn hiệu lực hoặc có denylist/introspection |
| Request đang xử lý khi revoke | Không commit thao tác vượt quyền theo chính sách nghiệp vụ |

Đối với session store phân tán, thử **stress/race**: hai lần login đồng thời khi gần đạt giới hạn; revoke-all xảy ra cùng lúc login mới; Redis mất kết nối; TTL hết hạn; invalidation event đến chậm; phiên có trong index nhưng không còn data và ngược lại. Kết luận phải dựa trên **bất biến bảo mật** đã định nghĩa, không chỉ đếm HTTP 200.

## 14. Checklist kiến trúc và vận hành

- [ ] Xác định ứng dụng dùng **HttpSession**, Spring Session hay OAuth2/JWT; không áp mô hình revoke sai loại.
- [ ] Xác định mức tối đa phiên theo user/tenant và chiến lược “new login replaces old” hoặc “prevent new”.
- [ ] Xác định rõ hành vi logout current, logout others, logout all, password change và disable account.
- [ ] Phân biệt **session** với **thiết bị vật lý**; không lấy IP/User-Agent làm khóa bảo mật.
- [ ] Không lộ session ID/cookie/token ở response, log, URL hoặc client-facing device list.
- [ ] Giữ CSRF cho cookie-based browser flows, mã hóa transport HTTPS và cấu hình cookie Secure/HttpOnly/SameSite phù hợp.
- [ ] Nếu single JVM, cấu hình registry và lifecycle events; nếu cluster, dùng shared session store/registry chính xác.
- [ ] Nếu cần thu hồi lập tức, xác định cơ chế kiểm tra revocation trên **mỗi request** và SLA về cache/propagation.
- [ ] Kiểm tra owner trước khi thu hồi một session; chức năng quản trị chéo tài khoản cần role/tenant/audit.
- [ ] Revoke remember-me/refresh token riêng khi chính sách yêu cầu; không suy đoán các token phụ tự biến mất.
- [ ] Test nhiều browser profiles, nhiều node, timeout và race; test rằng **người khác không thể revoke phiên của nhau**.
- [ ] Với tác vụ nhạy cảm đang chạy, có kiểm tra quyền/điều kiện giao dịch tại thời điểm ghi/commit.
- [ ] Lưu audit dạng actor, action, kết quả, timestamp và handle đã redact; không lưu secret thô.
- [ ] Kiểm tra cả login/logout/session-list/revoke bằng automated integration tests trước release.

## 15. Tự kiểm tra kiến thức

1. **Nếu Alice đăng nhập ở hai tab cùng Chrome, có chắc là hai session không?** Không. Hai tab cùng profile thường chia sẻ cookie; session không đồng nghĩa với tab hoặc thiết bị vật lý.
2. **`maximumSessions(2).maxSessionsPreventsLogin(false)` có nghĩa gì?** Cho phép tối đa hai session được theo dõi; login vượt giới hạn có thể làm hết hạn một session cũ để nhường session mới.
3. **Đăng xuất ở laptop có tự đăng xuất trên điện thoại không?** Không theo logout current-session mặc định; muốn vậy phải thu hồi session/token khác.
4. **`SessionInformation.expireNow()` có xóa cookie ngay khỏi browser khác?** Không. Nó đánh dấu session hết hạn trong registry; request tiếp theo mới bị phát hiện và xử lý theo bộ lọc/chiến lược.
5. **Vì sao không trả `sessionId` trong danh sách thiết bị?** Vì ID là credential có thể bị tái sử dụng để chiếm phiên nếu lộ; cần handle riêng, kiểm tra quyền.
6. **`SessionRegistryImpl` chạy ở ba node có tự chia sẻ registry không?** Không. Cần kho/registry phân tán hoặc kiến trúc nhất quán tương đương.
7. **Nếu chỉ thu hồi refresh token, access JWT đã cấp còn hiệu lực không?** Có thể còn đến khi hết hạn nếu resource server chỉ xác minh chữ ký/expiry; muốn thu hồi sớm cần state bổ sung.
8. **Tại sao đổi mật khẩu chưa chắc đủ vô hiệu session cũ?** SecurityContext trong session có thể tiếp tục hợp lệ; hệ thống phải chủ động revoke hoặc kiểm tra security version/quyền mới.
9. **Một POST revoke bị 403 vì thiếu CSRF có chứng minh code revoke đúng không?** Không. Cần test có CSRF hợp lệ để thật sự chạy logic thu hồi.
10. **Nếu thu hồi session trong lúc một lệnh ghi đang chạy, tác vụ đó tự động rollback không?** Không. Cần kiểm tra quyền ở điểm nghiệp vụ phù hợp, transaction và chiến lược xử lý race.

## 16. Tài liệu tham khảo chính thức

- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): concurrent session control, `maximumSessions`, `maxSessionsPreventsLogin`, lifecycle và session fixation.
- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): logout handlers, session invalidation và xóa cookie.
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF cho browser/cookie-based authentication.
- [Spring Session — Spring Security Integration](https://docs.spring.io/spring-session/reference/spring-security.html): `SpringSessionBackedSessionRegistry` và concurrent session control phân tán.
- [Spring Session — Spring Boot with Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): cách tích hợp session store Redis và cookie.
- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html): index theo principal và thu hồi một session đã kiểm quyền.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): bảo vệ session identifier, cookie và vòng đời session.
