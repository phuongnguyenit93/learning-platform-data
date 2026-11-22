# Kiểm thử session fixation, phiên đồng thời, remember-me và đăng xuất trong Spring Security Servlet

> **Môi trường học:** Spring Boot 3, Spring Security 6, Java 17+, Spring MVC Servlet, JUnit 5, MockMvc và Spring Security Test. Chủ đề là **kiểm thử hành vi HTTP và vòng đời xác thực dựa trên phiên**, không phải chỉ đọc cấu hình rồi giả định chức năng an toàn. Các ví dụ Spring cần một ứng dụng Spring Boot cùng dependencies tương ứng; chương trình Java thuần ở mục 3 có thể chạy độc lập để luyện cách diễn đạt các bất biến kiểm thử.

## 1. Vì sao cần kiểm thử bốn cơ chế cùng nhau?

Đăng nhập bằng biểu mẫu thường tạo hoặc sử dụng một `HttpSession` chứa `SecurityContext`. Spring Security có các cơ chế bảo vệ liên quan nhưng không đồng nghĩa:

1. **Session fixation protection:** thay đổi định danh session sau khi đăng nhập, ngăn attacker lợi dụng một session ID được thiết lập trước khi nạn nhân xác thực.
2. **Concurrent session control:** giới hạn số phiên đang hoạt động của cùng một principal, chọn từ chối đăng nhập mới hoặc làm hết hiệu lực phiên cũ.
3. **Remember-me authentication:** cho phép một cookie nhớ đăng nhập tạo lại Authentication khi phiên thông thường không còn, với những rủi ro token riêng.
4. **Logout:** hủy trạng thái xác thực của phiên hiện tại và xử lý cookie/context, nhưng có thể **không tự thu hồi** mọi loại remember-me token hoặc mọi session ở thiết bị khác.

**Một test “POST /login trả 302” không chứng minh bốn cơ chế trên chạy đúng.** Cần quan sát session ID, trạng thái Authentication ở request sau, SessionRegistry, cookie remember-me, logout với CSRF và kết quả khi thử dùng lại credential cũ.

Những lỗi hay bị bỏ sót: cookie `JSESSIONID` đổi nhưng quyền lại không được kiểm tra; đăng nhập thứ hai thành công dù cấu hình tối đa một phiên; logout chỉ xóa cookie trong browser nhưng token remember-me đã bị copy vẫn dùng được; GET `/logout` bị hiểu nhầm là yêu cầu logout khi CSRF đang bật.

## 2. Các khái niệm trước khi viết test

### 2.1. SecurityContext và HttpSession

Trong ứng dụng Servlet dùng form login, `SecurityContextHolder` chứa `Authentication` trong phạm vi xử lý request; `SecurityContextRepository` có thể lưu/nạp context qua `HttpSession`. Browser giữ cookie `JSESSIONID` để quay lại session. Một user có thể có nhiều sessions khác nhau nếu đăng nhập bằng hai browser/thiết bị.

- **`Authentication`:** principal và authorities đã xác thực.
- **`SecurityContext`:** đối tượng giữ Authentication cho security filters.
- **`HttpSession`:** kho trạng thái Servlet có ID và attributes; không đồng nghĩa một access token.
- **`SessionRegistry`:** ghi nhận các session đang được Spring Security quản lý để áp chính sách đồng thời; không phải bản sao tự động của mọi session trên toàn cụm.
- **Remember-me cookie:** credential sống dài hơn session thông thường, có thể dùng để tự động xác thực request sau.
- **`LogoutHandler` / `LogoutSuccessHandler`:** thao tác dọn session, context, cookie/tokens và điều hướng sau logout.

Không dùng riêng `Authentication.isAuthenticated()` làm bằng chứng người dùng đã xác thực: anonymous token cũng có thể được framework biểu diễn bằng một Authentication. Dùng authorization rules, `SecurityContextHolderAwareRequestWrapper`/`Principal` hoặc `AuthenticationTrustResolver` đúng ngữ cảnh.

### 2.2. Bảng kỳ vọng nhanh

| Sự kiện | HTTP request cần mô phỏng | Bất biến phải kiểm tra |
| --- | --- | --- |
| Login thành công khi đã có session | `POST /login` với session trước login và CSRF token | Session ID thay đổi; principal vẫn có thể truy cập tài nguyên hợp lệ |
| Login không thành công | `POST /login` sai mật khẩu | Không tạo Authentication hợp lệ; không cấp remember-me cookie mới |
| Session đồng thời vượt ngưỡng | Login cùng user ở hai session khác nhau | Phiên cũ bị hết hiệu lực **hoặc** login mới bị từ chối đúng policy |
| Remember-me được chọn | Login có `remember-me=on` | Cookie remember-me được gửi; request không có session nhưng có cookie có thể xác thực |
| Không chọn remember-me | Login không có lựa chọn | Không cấp cookie nhớ đăng nhập mới theo cấu hình demo |
| Logout hợp lệ | `POST /logout` cùng session/cookie và CSRF | Session hiện tại bị invalidated, remember-me cookie bị xóa ở client, request không còn đăng nhập qua session đó |
| Logout thiếu CSRF | `POST /logout` không token CSRF khi CSRF enabled | Bị từ chối; session vẫn còn và không có logout side effect |
| Cookie remember-me bị sao chép | Dùng lại cookie cũ sau logout | Phụ thuộc token-based hoặc persistent-token design; không mặc định bị thu hồi |
| Logout ở một browser, browser khác vẫn online | Phiên A logout, phiên B tồn tại | Cần chính sách logout-all riêng; logout mặc định không có nghĩa hủy toàn bộ phiên |

## 3. Session fixation: điều gì cần kiểm tra?

**Session fixation**: attacker tạo/biết một session ID trước khi victim đăng nhập; nếu server giữ nguyên ID sau khi nâng trạng thái lên authenticated, attacker có thể cố dùng lại ID đó để truy cập phiên đã xác thực.

Spring Security Servlet có `SessionAuthenticationStrategy` cho login tương tác; với Servlet 3.1+ chính sách điển hình `changeSessionId()` đổi ID khi xác thực mà không phải mất hết session attributes. Các chiến lược liên quan:

| Chiến lược | Ý nghĩa | Ghi chú kiểm thử |
| --- | --- | --- |
| `changeSessionId()` | Dùng Servlet `HttpServletRequest.changeSessionId()` | ID trước/sau phải khác; attributes thường được giữ |
| `migrateSession()` | Tạo session mới, chuyển session attributes | Kiểm thử ID mới và những attributes phải được giữ |
| `newSession()` | Tạo session mới, hạn chế mang attributes cũ | Đừng kỳ vọng mọi custom session attribute còn tồn tại |
| `none()` | Không đổi session ID | Tránh trong form login thông thường trừ khi threat model rất cụ thể |

Trên những ứng dụng modern Servlet, **thay đổi ID ở điểm login thành công** là kiểm tra quan trọng nhất. Không nên đoán rằng cứ có HTTP 302 redirect là ID đã đổi; controller/logic có thể đã redirect nhưng không có authentication strategy thích hợp.

### 3.1. Luồng test

```text
Request 1: GET /login
     -> nhận HttpSession/S1 (nếu ứng dụng tạo)
Request 2: POST /login [username, password, CSRF] với S1
     -> login thành công
     -> server đổi session ID: S1 -> S2
Request 3: GET /private với S2
     -> đúng principal, được phép
Request 4: request tự tạo dùng lại ID S1 tại real container
     -> không được kế thừa authenticated session
```

**Quan trọng:** `MockHttpSession` trong Spring Test có thể **thay ID ngay trên cùng đối tượng** khi `changeSessionId()` được gọi. Vì vậy test `assertNotEquals(beforeId, session.getId())` hữu ích để kiểm tra rotation trong MockMvc, nhưng **không kiểm chứng đầy đủ** việc Servlet container từ chối ID cũ trên một kết nối HTTP độc lập. Bất biến “old cookie không thể replay” cần integration test qua **container thật** với browser/HTTP client quản lý cookie riêng.

### 3.2. Java 17 chạy độc lập: bất biến của session lifecycle

Đây chỉ là bài luyện Java để mô hình hóa điều kiện, **không mô phỏng Servlet container**. File `SessionInvariantDemo.java`:

```java
import java.util.Objects;

public final class SessionInvariantDemo {
    static void assertRotated(String before, String after) {
        if (Objects.equals(before, after)) {
            throw new IllegalStateException("Session ID was not rotated");
        }
    }

    static boolean needsNewAuthentication(
            boolean authenticatedSession, boolean rememberMeCookiePresent) {
        return !authenticatedSession && !rememberMeCookiePresent;
    }

    public static void main(String[] args) {
        assertRotated("S1", "S2");
        System.out.println("rotated=true");
        System.out.println("reauth=" + needsNewAuthentication(false, false));
        System.out.println("reauth=" + needsNewAuthentication(false, true));
    }
}
```

Chạy:

```bash
javac SessionInvariantDemo.java
java SessionInvariantDemo
```

Stdout chính xác:

```text
rotated=true
reauth=true
reauth=false
```

Hàm `needsNewAuthentication` ở ví dụ **chỉ xét sự hiện diện của cookie để minh họa lựa chọn testcase**; nó không có ý nghĩa “cookie hiện diện thì token chắc chắn hợp lệ”. Trong hệ thống thật phải **verify remember-me credential** trước khi tạo Authentication. Không dùng hàm mô hình hóa này làm logic xác thực.

## 4. Concurrent sessions: từ chối mới hay hết hạn cũ?

Spring Security hỗ trợ **maximum sessions** cho authentication kiểu session. Có hai policy:

- `maximumSessions(1).maxSessionsPreventsLogin(false)`: khi cùng user login ở session mới, session cũ có thể bị đánh dấu **expired**; khi phiên cũ tiếp tục gửi request, `ConcurrentSessionFilter` xử lý nó theo cấu hình (ví dụ redirect `/session-expired`). Phiên mới tiếp tục hoạt động.
- `maximumSessions(1).maxSessionsPreventsLogin(true)`: từ chối authentication mới khi user đã đạt giới hạn; session hiện tại tiếp tục sử dụng. Tùy login flow, failure handler có thể redirect về form login với dấu hiệu lỗi, không nhất thiết trả HTTP 403 trực tiếp.

**Không kiểm tra policy chỉ bằng status của lần login thứ hai.** Với chế độ expire-old, login thứ hai vẫn thành công; cần gửi request mới bằng session cũ để chứng minh nó bị chặn.

### 4.1. SessionRegistry và HttpSessionEventPublisher

Trong cấu hình Servlet in-memory, `SessionRegistryImpl` ghi nhận sessions theo principal. `HttpSessionEventPublisher` kết nối lifecycle events của Servlet với Spring Security, giúp dọn registry khi session bị destroy (logout/invalidate/timeout tùy container và event). Nếu không có listener hoặc registry phù hợp, các phiên đã timeout có thể còn được registry xem là đang hoạt động, dẫn đến từ chối login mới sai hoặc đếm phiên bất thường.

Lưu ý:

- Với nhiều máy chạy ứng dụng, `SessionRegistryImpl` in-memory **không phải registry phân tán**. Tích hợp **Spring Session** và một registry dựa trên session repository phù hợp (ví dụ `SpringSessionBackedSessionRegistry` theo phiên bản/tích hợp) hoặc thiết kế quản lý session tập trung.
- `SessionRegistry` phải dùng principal equality/hashCode nhất quán. Một custom principal thay đổi hoặc mỗi lần load có equality không đúng có thể khiến cùng user không được tính đúng là một principal.
- Session timeout, invalidation, logout và expired policy cần được test trong container/cluster thật, không chỉ với mocks.

### 4.2. Trường hợp concurrent cần QA

| Test case | Expected khi expire-old | Expected khi prevent-new |
| --- | --- | --- |
| Alice login tại browser A | A dùng được | A dùng được |
| Alice login tại browser B | B được cấp session mới; A marked expired | B bị từ chối login; A vẫn dùng được |
| A gọi endpoint sau B login | A bị xử lý expired | A vẫn authenticated |
| B gọi endpoint sau B login | B thành công | B không authenticated theo login vừa bị từ chối |
| A logout/timeout | Registry bỏ A khi có lifecycle event đúng | Slot được giải phóng cho login mới |
| Bob login riêng | Không chiếm quota của Alice | Không chiếm quota của Alice |
| Hai login cùng lúc | Không vượt quá limit theo khả năng triển khai/session registry | Race conditions cần integration test có kiểm soát |
| Multi-node A/B | Hành vi nhất quán trên các node theo thiết kế | Không được dựa vào per-node registry tách biệt |

## 5. Remember-me: không phải session sống lâu

Remember-me hỗ trợ đăng nhập lại tự động khi browser không còn `HttpSession` hợp lệ nhưng vẫn gửi remember-me cookie. Trong Spring Security Servlet, có hai lựa chọn thường gặp:

### 5.1. Token-based remember-me

`TokenBasedRememberMeServices` dùng cookie được bảo vệ bằng thông tin ký dựa trên username, hạn dùng, thuật toán và **secret key** của server, cùng một số thông tin như password hash theo giao thức triển khai. Không cần token record riêng trong database, nhưng:

- Nếu token đã bị **sao chép**, chỉ xóa cookie trên browser khi logout **không bảo đảm** bản sao của token lập tức mất hiệu lực.
- Token hết hạn theo thời gian hoặc không còn verify được khi secret key/điều kiện ký thay đổi.
- Việc đổi mật khẩu có thể ảnh hưởng hiệu lực của token-based credential tùy implementation/format; **không** coi đây là cơ chế revoke chọn lọc cho từng thiết bị.
- Key phải là secret đủ mạnh, lưu ngoài source code/secret management và giữ ổn định qua các replicas nếu token cần được chấp nhận trên nhiều node. Key đổi sẽ làm token cũ không còn hợp lệ.
- Token remember-me có quyền tương ứng Authentication của user khi được xác thực tự động, nhưng Spring Security có thể phân biệt `isRememberMe()` với `isFullyAuthenticated()`. Tác vụ nhạy cảm nên yêu cầu **reauthentication** thay vì chỉ nhớ đăng nhập.

### 5.2. Persistent-token remember-me

`PersistentTokenBasedRememberMeServices` dùng một `PersistentTokenRepository` như JDBC repository để lưu **series/token** và quản lý rotation theo hành vi của implementation. Dữ liệu không chỉ nằm ở browser. Lợi ích: có thể **thu hồi token series phía server**, đặc biệt khi logout/xóa credential hoặc xử lý rủi ro.

Với persistent tokens, khi user logout và `RememberMeServices.logout` xóa series trong repository, bản sao cookie đã thu hồi **không** còn được nhận lại trong kiến trúc đúng. Cần test cả response cookie và **lookup server-side sau logout**, bởi kiểm tra cookie Max-Age=0 không chứng minh token đã bị vô hiệu hóa.

Ví dụ schema của Spring Security JDBC persistent remember-me tùy phiên bản/DB có các cột:

```sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
```

Đây là **schema tham khảo** theo JDBC token repository thông dụng; kiểm tra DDL chính thức đi kèm version, dialect và migration của ứng dụng trước khi áp dụng. Với nhiều ứng dụng cần audit/retention, có thể dùng repository tùy biến; bảo vệ DB, không log raw token, giới hạn quyền truy cập và kiểm tra rotation/race.

### 5.3. Remember-me không tương đương OAuth2 access token

Remember-me cookie là một loại credential cho **web authentication** của Spring Security, không phải JWT Resource Server, refresh token OAuth2 hay cookie `JSESSIONID`. Không dùng thuật ngữ “token” để trộn các vòng đời khác nhau:

| Credential | Được gửi như thế nào? | Ai xác minh? | Logout mặc định ảnh hưởng gì? |
| --- | --- | --- | --- |
| `JSESSIONID` | Browser tự gửi cookie | Servlet session store + Spring Security context | Có thể invalidate session hiện tại |
| Token-based remember-me cookie | Browser tự gửi cookie dài hạn hơn | RememberMeServices + secret/password state | Xóa cookie phía client; bản sao có thể còn hợp lệ |
| Persistent remember-me cookie | Browser gửi cookie series/token | RememberMeServices + repository record | Có thể xóa series/tokens phía server theo implementation |
| OAuth2 bearer access token | `Authorization: Bearer ...` do client gửi | JWT decoder / token introspector | Logout session không tự thu hồi access token |
| OAuth2 refresh token | Do OAuth2 client giữ/gửi đến token endpoint phù hợp | Authorization Server | Cần revocation/rotation policy riêng |

## 6. Logout: phải test trạng thái, không chỉ redirect

Khi CSRF protection bật, Spring Security mặc định bảo vệ hành động logout bằng **POST `/logout` kèm CSRF token**. `GET /logout` có thể hiển thị trang xác nhận thay vì thực hiện logout (tùy cấu hình UI/framework). Vì vậy test “GET /logout là đủ” có thể đánh giá sai.

Logout thường thực hiện:

1. Dọn Authentication và `SecurityContext` của request theo `SecurityContextLogoutHandler`.
2. Invalidate `HttpSession` hiện tại (nếu có), không duy trì ID session đó như authenticated.
3. Thực hiện RememberMeServices logout/cookie deletion khi đã cấu hình.
4. Có thể xóa cookie `JSESSIONID` qua delete-cookie policy; lưu ý cookie path/domain phải khớp để browser thực sự xóa đúng cookie.
5. Có thể redirect về trang xác nhận hoặc URL đích (ví dụ `/login?logout`).
6. **Không mặc định logout khỏi tất cả thiết bị**, xóa tất cả browser storage, thu hồi mọi OAuth access token hay token đã copy.

### 6.1. Kiểm tra logout với CSRF

| Yêu cầu | Kỳ vọng |
| --- | --- |
| POST /logout + session hợp lệ + CSRF token | Logout được thực hiện, session invalidated, cookie dọn, redirect thành công |
| POST /logout + session hợp lệ nhưng thiếu CSRF | Thông thường 403 và **không invalidate** session |
| POST /logout + cookie remember-me | Cookie nhớ đăng nhập bị xóa ở response; persistent series có thể bị revoke |
| GET /private sau logout, không gửi remember-me | Không còn authenticated qua session; bị chuyển login hoặc 401 tùy API/web |
| Dùng lại session ID cũ trong real container | Không được truy cập như user đã logout |
| Dùng lại token-based remember-me đã bị copy | Có thể còn dùng được: cần nguy cơ và thu hồi phù hợp |
| Logout tại A khi B còn phiên riêng | B vẫn có thể hoạt động trừ khi có quy tắc logout-all |
| Logout success handler lỗi | Không để session/auth còn hợp lệ chỉ vì response redirect không thành công |

Nếu dùng **cookie-based authentication**, CSRF vẫn liên quan ngay cả khi controller trả JSON. Cookie remember-me tự được browser gửi nên phải suy xét CSRF cho các endpoints nhạy cảm.

## 7. Ứng dụng mẫu Spring Boot 3 / Spring Security 6 để kiểm thử

Mẫu cấu hình dưới đây dành cho **một ứng dụng Spring Boot Servlet có `@SpringBootApplication`**, với dependencies tương đương:

- `spring-boot-starter-web`, `spring-boot-starter-security`.
- `spring-boot-starter-test` và `spring-security-test` trong test scope.
- Java 17+. Mã Java không thể chạy bằng `javac` đơn thuần nếu thiếu Spring dependencies và class bootstrapping.
- Demo có user `alice`/`bob`; password được BCrypt-hash lúc khởi động. **Không dùng user demo hoặc mật khẩu mẫu trong môi trường sản xuất.**

### 7.1. SecurityConfig.java

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("test-password"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("test-password"))
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
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SessionRegistry registry,
            UserDetailsService users,
            @Value("${app.security.remember-me-key}") String rememberMeKey)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/session-expired").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/private", true))
            .rememberMe(remember -> remember
                .key(rememberMeKey)
                .tokenValiditySeconds(60 * 60 * 24)
                .userDetailsService(users))
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId())
                .maximumSessions(1)
                .maxSessionsPreventsLogin(false)
                .expiredUrl("/session-expired")
                .sessionRegistry(registry))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID"));

        return http.build();
    }
}
```

Cấu hình `formLogin` mặc định xử lý POST `/login` với fields `username`/`password`, CSRF bật mặc định, và mẫu dùng `remember-me` parameter mặc định. `maximumSessions(1)` áp hạn mức cho session authentication, `maxSessionsPreventsLogin(false)` đánh dấu phiên cũ expired. `expiredUrl` chỉ định nơi redirect khi request tiếp theo đến từ phiên đã hết hiệu lực do concurrency.

`rememberMe(...)` ở đây dùng **token-based remember-me**, không phải JDBC persistent. Chính vì vậy **logout xóa cookie nhưng chưa phải server-side revocation của mọi bản sao**. `rememberMeKey` phải lấy từ secret store ổn định qua các node; không hardcode key production.

Ví dụ cấu hình trong `application.yml`:

```yaml
app:
  security:
    remember-me-key: ${REMEMBER_ME_KEY}
```

Biến môi trường `REMEMBER_ME_KEY` phải được cung cấp khi chạy ứng dụng. Trong test ta cấp property riêng cho môi trường test. Không commit bí mật production vào source.

**SessionRegistryImpl chỉ phù hợp ví dụ một node.** Nếu phục vụ nhiều replica, thiết kế session registry dùng chung và backend session store; kiểm thử qua load balancer và xử lý session timeout. Cấu hình này cũng **không tự có cơ chế revoke tất cả thiết bị**.

### 7.2. Controller riêng phục vụ test

File `PrivateController.java`:

```java
import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PrivateController {

    @GetMapping("/private")
    String privateEndpoint(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/session-expired")
    String expired() {
        return "session-expired";
    }
}
```

Truy cập `GET /private` với session Alice hợp lệ trả body `alice`; Bob trả `bob`. Khi anonymous, security chain chuyển về login thay vì controller xử lý. Trong ứng dụng thực, không chỉ kiểm tra principal name: cần authorization/ownership và data permissions.

### 7.3. Môi trường test

Các test dưới đây giả định package scan chứa `SecurityConfig` và `PrivateController`, có class `@SpringBootApplication` trong package cha phù hợp và các dependencies test đã nêu. Test dùng MockMvc để đi qua servlet filters và mock session lifecycle; kết quả của Servlet container/cookie browser thật vẫn cần integration test độc lập.

## 8. MockMvc: login, session ID rotation và truy cập sau đăng nhập

File `SessionSecurityTests.java`, dùng JUnit 5:

```java
import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties =
    "app.security.remember-me-key=unit-test-only-secret-replace-for-real-use")
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SessionSecurityTests {

    @Autowired
    MockMvc mvc;

    private MvcResult login(
            MockHttpSession session, String username,
            boolean rememberMe) throws Exception {
        MockHttpServletRequestBuilder request = post("/login")
            .session(session)
            .with(csrf())
            .param("username", username)
            .param("password", "test-password");

        if (rememberMe) {
            request.param("remember-me", "on");
        }

        return mvc.perform(request)
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/private"))
            .andReturn();
    }

    @Test
    void changesSessionIdAfterSuccessfulLogin() throws Exception {
        MockHttpSession session = new MockHttpSession();
        String before = session.getId();

        login(session, "alice", false);

        assertNotEquals(before, session.getId());
        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void secondLoginExpiresFirstSession() throws Exception {
        MockHttpSession first = new MockHttpSession();
        MockHttpSession second = new MockHttpSession();

        login(first, "alice", false);
        login(second, "alice", false);

        mvc.perform(get("/private").session(first))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/session-expired"));

        mvc.perform(get("/private").session(second))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void rememberMeCookieAuthenticatesWithoutOldSession()
            throws Exception {
        MockHttpSession session = new MockHttpSession();
        MvcResult loggedIn = login(session, "alice", true);

        Cookie rememberCookie =
            loggedIn.getResponse().getCookie("remember-me");
        assertNotNull(rememberCookie);

        // Không gửi JSESSIONID hoặc MockHttpSession cũ:
        // xác thực lại bằng remember-me cookie.
        mvc.perform(get("/private").cookie(rememberCookie))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void logoutRequiresCsrfAndClearsCurrentSession()
            throws Exception {
        MockHttpSession session = new MockHttpSession();
        MvcResult loggedIn = login(session, "alice", true);
        Cookie rememberCookie =
            loggedIn.getResponse().getCookie("remember-me");
        assertNotNull(rememberCookie);

        // Thiếu CSRF: request bị từ chối, session chưa logout.
        mvc.perform(post("/logout").session(session)
                .cookie(rememberCookie))
            .andExpect(status().isForbidden());

        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));

        MvcResult loggedOut = mvc.perform(post("/logout")
                .session(session)
                .cookie(rememberCookie)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertTrue(session.isInvalid());

        Cookie deletion =
            loggedOut.getResponse().getCookie("remember-me");
        assertNotNull(deletion);
        assertEquals(0, deletion.getMaxAge());

        // Request mới không gửi cookie hoặc session cũ:
        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection());
    }
}
```

**Giải thích chi tiết và giới hạn:**

- `MockHttpSession` là đối tượng test; khi `changeSessionId()` được gọi, đối tượng này có thể được cập nhật ID *tại chỗ*. Kiểm tra ID trước/sau nhưng **không dùng nó làm bằng chứng tuyệt đối về replay với cookie ID cũ**.
- `csrf()` của `spring-security-test` tạo CSRF token cho request giả lập. Cùng một phiên CSRF của từng test phải phù hợp; nếu ứng dụng thay `CsrfTokenRepository`, cần cập nhật test.
- Login hai lần cùng user kiểm tra policy **expire-old** trong cấu hình. Test thứ hai phải gọi endpoint bằng **cả session cũ và session mới**, không chỉ kiểm tra redirect sau login.
- Remember-me test **không gửi session cũ**, nhằm phân biệt remembered authentication với tiếp tục dùng `JSESSIONID`. Nó vẫn tạo session/context mới nếu filter chain cấu hình như vậy; điều này không phủ nhận việc cookie remember-me đã được kiểm thử.
- Logout test chỉ xác nhận browser được yêu cầu **xóa remember-me cookie** và session hiện tại invalidated. **Không tuyên bố** rằng một token-based remember-me cookie đã bị attacker sao chép sẽ bị server từ chối sau logout.
- `@DirtiesContext(AFTER_EACH_TEST_METHOD)` cô lập registry và session/authentication state giữa các test cho bài học. Trong suite lớn, tạo lại ApplicationContext mỗi test có chi phí; có thể thay bằng fixture/reset rõ ràng để tối ưu.

**Lưu ý về tính runnable:** các class này cần được đặt đúng package và Spring Boot application thực có startup class; controller/test không phải tệp Java độc lập. Phiên bản Spring Security 6.x và Servlet container test có thể ảnh hưởng status/headers chính xác; hãy đối chiếu với dependency đang sử dụng và chạy test, không suy ra từ mã mà chưa thử.

### 8.1. Những case cần bổ sung cho session fixation

Ngoài `assertNotEquals`, có thể kiểm tra:

1. Login sai mật khẩu **không** tạo authenticated session của Alice và không phát nhớ đăng nhập.
2. Các session attributes được yêu cầu bảo toàn vẫn tồn tại sau `changeSessionId`, ví dụ giá trị flow state hợp lệ.
3. `JSESSIONID` browser nhận sau login phản ánh session mới; ngữ cảnh cookie path/domain/SameSite/Secure phù hợp.
4. Dùng **HTTP client thật** với hai cookie jars: một giữ ID trước login, một dùng ID sau login. Cookie jar giữ ID cũ phải không truy cập được `/private` như Alice.
5. Logout với ID mới hủy session; **ID cũ từ trước login** cũng không được “hồi sinh”.
6. Khi Spring MVC/controller tự đổi session hoặc authentication tự viết bypass Spring Security, có test chứng minh strategy vẫn được gọi tại điểm login.

Nếu auth flow sử dụng **OAuth2 login, SAML2 login hoặc custom authentication filter**, cần kiểm tra session authentication strategy thực tế của flow đó; không suy rằng nó chạy giống đúng form login mẫu.

## 9. Test concurrent session với chính sách prevent-new

Chế độ thứ hai đổi cấu hình:

```java
// Đoạn DSL minh họa trong cấu hình sessionManagement:
.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true)
    .sessionRegistry(registry))
```

Đây là **snippet**, không phải class đầy đủ. Khi `maxSessionsPreventsLogin(true)`:

- Alice login session A thành công.
- Alice login session B khi A đang hợp lệ: authentication mới **bị từ chối**; handler dành cho form login có thể redirect về `/login?error` hoặc route được cấu hình.
- A tiếp tục hoạt động.
- Sau khi A logout/timeout và registry được cập nhật đúng, B có thể login ở lần thử mới.

Test nên xác minh:
- Login B không cấp session đã authenticated (không chỉ status).
- A vẫn truy cập `/private`.
- Sau khi A bị destroy/logout và event publisher/registry nhận lifecycle event, user có thể tạo session mới.
- Không có cross-user interference: quota Alice không ảnh hưởng Bob.
- Khi hai login đến đồng thời, chính sách được áp ở nơi đủ nhất quán; stress/race tests có giá trị hơn một MockMvc test tuần tự.

Không áp kết luận “phiên đồng thời chỉ có thể là hai tab cùng browser”. Hai tab cùng profile thường chia sẻ `JSESSIONID` cookie, nên không nhất thiết tạo **hai session độc lập**. Dùng hai browser profiles, cookie jars hoặc `MockHttpSession` tách biệt để test.

## 10. Remember-me: thêm negative tests và kiểm tra thu hồi

### 10.1. Không chọn remember-me

Test login thành công không gửi `remember-me=on`, sau đó xác nhận response **không tạo remember-me cookie mới**. Chú ý một cookie nhớ đăng nhập từ lần đăng nhập cũ có thể vẫn nằm trong browser; test cần cookie jar sạch, không suy từ trạng thái browser đang dùng hàng ngày.

### 10.2. Cookie bị sửa hoặc hết hạn

Thử thay một phần giá trị cookie, hết hạn, đổi key hoặc dùng token của user đã bị vô hiệu hóa. Endpoint được bảo vệ phải không authenticate bằng cookie sai. Với MockMvc, tạo request mới **chỉ có cookie giả**, không có `HttpSession`; phải phân biệt filter tự xóa cookie lỗi với HTTP status cuối cùng (web form login thường redirect sang `/login`, API có thể trả 401).

Các test quan trọng khác:
- Cookie nhớ đăng nhập có `HttpOnly`/`Secure` theo thiết lập/môi trường; lưu ý `Secure` phụ thuộc HTTPS request và option cookie.
- Cookie path/domain được đặt phù hợp để không lộ rộng không cần thiết.
- `remember-me` được browser gửi tự động nên các unsafe actions vẫn cần CSRF protection nếu đang dùng cookie auth.
- Endpoint nhạy cảm cần `fullyAuthenticated()`/recent authentication có thể từ chối remember-me nhưng chấp nhận login tương tác. Kiểm tra theo chính sách thay vì cho rằng remembered user có mọi quyền như phiên vừa login.

### 10.3. Vì sao kiểm tra cookie xóa chưa đủ?

Ví dụ với **token-based remember-me**:

```text
Browser Alice có cookie C
Attacker đã sao chép C trước khi Alice logout
Alice POST /logout:
   -> server invalidates HttpSession
   -> trả Set-Cookie xóa remember-me ở browser Alice
Attacker vẫn giữ bản sao C
   -> nếu C chưa hết hạn và vẫn verify được: có thể còn hiệu lực
```

Vì thế bài test `logoutRequiresCsrfAndClearsCurrentSession` ở trên chứng minh **trạng thái phía browser/session**, không chứng minh server-side revocation của bản sao token. Nếu yêu cầu nghiệp vụ là **logout phải thu hồi nhớ đăng nhập ngay**, sử dụng persistent token store/thiết kế revoke và viết integration test với database: token series bị xóa, cookie C cũ không đăng nhập lại được, các browser/thiết bị khác được xử lý đúng phạm vi policy.

**Không “fix” vấn đề này bằng cách ghi nhớ token raw trong log** hay lưu remember-me cookie như một password plaintext. Rà soát lifecycle, TTL, rotation, theft detection và yêu cầu xác thực lại trên hành động quan trọng.

## 11. Logout tất cả thiết bị: chức năng riêng cần test riêng

Logout mặc định chủ yếu áp dụng cho **phiên hiện tại**. Nếu sản phẩm có nút “Đăng xuất mọi thiết bị”:

1. Xác minh người dùng một cách đủ mạnh, cân nhắc recent reauthentication.
2. Truy vấn tất cả sessions của principal trong registry phân tán hoặc session store.
3. Invalidate/expire từng session đúng cách; đảm bảo các node thực thi thống nhất.
4. Thu hồi remember-me persistent tokens cho user hoặc từng thiết bị theo policy.
5. Nếu ứng dụng có OAuth2 refresh tokens/access tokens riêng, gọi revocation/token management của Authorization Server theo giao thức; không dùng `session.invalidate()` để tuyên bố đã thu hồi OAuth tokens.
6. Test từ **ít nhất hai cookie jars độc lập**, xác nhận A và B không còn được authenticated.
7. Đảm bảo auditing: ai yêu cầu logout-all, khi nào, kết quả thực thi, không lộ token/cookie.

Có thể logout-all là async operation. Nếu kết quả giữa các node không đồng bộ, phải đặc tả eventual consistency và đảm bảo người dùng không được thông báo sai rằng toàn bộ credential đã lập tức vô hiệu.

## 12. MockMvc khác browser/container thật thế nào?

MockMvc cực kỳ hữu ích cho security filter chain, nhưng có giới hạn:

| Mục tiêu | MockMvc kiểm tra được | Cần test container/browser |
| --- | --- | --- |
| Filter chain nhận POST /login, CSRF | Có | Có ích thêm cho cookie/path và UX |
| Session ID thay đổi khi login | Có bằng MockHttpSession | Có, để chứng minh ID cũ không replay |
| ConcurrentSessionFilter xử lý expired | Có với registry trong context test | Cần khi multi-node/shared session |
| HttpSessionEventPublisher nhận timeout events | Khó mô phỏng đầy đủ timeout lifecycle | Có, với actual session expiration/store |
| Remember-me cookie được phát và được đọc | Có, inject cookie vào MockMvc request | Có, để kiểm domain/path/SameSite/Secure và browser persistence |
| Server-side revoke persistent remember-me | Có nếu dùng real repository integration | Có lợi cho race/replication và cookie jar thực |
| POST logout thiếu CSRF | Có | Có khi tích hợp frontend |
| Xóa JSESSIONID/remember-me cookie thực ở browser | Chỉ kiểm Set-Cookie headers/response cookie | Có, cần domain/path chính xác |
| Old session ID không còn authenticated | MockMvc không mô phỏng toàn bộ container cookie lookup | Có |
| Logout-all qua load balancer | Không đủ nếu một JVM giả | Bắt buộc test nhiều node/nơi lưu session |

Đối với end-to-end test, dùng test environment qua HTTPS nếu có thể, hai HTTP clients/cookie jars và lưu toàn bộ exchange dưới dạng **redacted** logs. Không đưa raw password, remember-me token hoặc `JSESSIONID` vào CI artifact công khai.

### 12.1. cURL minh họa, không lộ secret

```bash
# GET login page để lấy form và CSRF token.
curl -i -c jar-a.txt http://localhost:8080/login

# Gửi POST login cần CSRF token hợp lệ lấy từ form/cookie
# theo CsrfTokenRepository thực tế; cú pháp sau chỉ là skeleton:
curl -i -b jar-a.txt -c jar-a.txt \
  -X POST http://localhost:8080/login \
  --data-urlencode 'username=alice' \
  --data-urlencode 'password=test-password' \
  --data-urlencode '_csrf=TOKEN_FROM_FORM'

# Đọc endpoint được bảo vệ dùng cookie jar A.
curl -i -b jar-a.txt http://localhost:8080/private
```

**Không chạy skeleton với token CSRF giả rồi kết luận login thất bại.** Phải lấy `_csrf` đúng của phiên, bảo vệ file cookie jar và dùng test credentials; xóa jar khi xong. Tránh ghi command có secret vào shell history; với automation, dùng secret manager và artifact redaction.

## 13. QA matrix: tổ chức test suite tránh false positives

### 13.1. Tách test class hoặc context theo cấu hình

Cấu hình session concurrency `expire-old` và `prevent-new` là **hai policy thay thế nhau**, không phải hai trạng thái có thể áp trong cùng một bean ở một test. Dùng test profiles/config riêng để bảo đảm mỗi class có một kỳ vọng rõ ràng.

Với remember-me token-based và persistent-token, cũng nên có test class/fixture riêng, DB test cho persistent mode. Nếu chạy chung một context có nhiều `SecurityFilterChain` hay nhiều bean `SessionRegistry`, phải chọn đúng chain và đúng registry.

### 13.2. Bộ testcase tối thiểu cho CI

| ID | Kiểm thử | Điều kiện PASS |
| --- | --- | --- |
| SF-01 | Session ID rotated khi login thành công | Before ID != after ID, auth đúng |
| SF-02 | Login sai không nâng Authentication | Request protected không dùng được sau login fail |
| SF-03 | Replay ID trước login trên real container | Old cookie jar không authenticated |
| CC-01 | User login hai phiên với expire-old | A expired, B dùng được |
| CC-02 | Prevent-new | B denied, A dùng được |
| CC-03 | Session A timeout/logout | Registry giải phóng slot hợp lệ |
| CC-04 | Hai user độc lập | Session quota không lẫn người dùng |
| RM-01 | Opt-in remember-me | Set-Cookie tồn tại |
| RM-02 | Không opt-in | Không phát cookie mới |
| RM-03 | No session + valid remember-me cookie | User remembered auth được thiết lập |
| RM-04 | Cookie bị sửa/hết hạn | Không được authenticate |
| RM-05 | Logout persistent-token | Series revoked; stolen cookie C không hợp lệ |
| LO-01 | POST logout có CSRF | Session invalidated + cookie cleared |
| LO-02 | POST logout thiếu CSRF | Request bị chặn, không logout |
| LO-03 | No session/cookie sau logout | Không truy cập protected resource |
| LO-04 | Logout-all khi có hai browser | Cả hai sessions hết hiệu lực theo policy |
| LO-05 | OAuth tokens nếu có | Revocation được test riêng |

### 13.3. Test isolation

- Mỗi testcase dùng session và cookies **độc lập**; không reuse `MockHttpSession` của test khác.
- Không giả định thứ tự test theo tên method.
- Nếu `SessionRegistryImpl` là singleton trong test context, làm sạch trạng thái hoặc tạo ApplicationContext riêng; ví dụ dùng `@DirtiesContext` để minh họa.
- Với concurrent test, mô phỏng **hai session** thật, không dùng hai tab chung cookie.
- Không dùng `@WithMockUser` thay thế login khi mục tiêu là kiểm **session fixation** hoặc **remember-me issuance**. `@WithMockUser` bỏ qua quá trình credential check/login filter.
- Với test remember-me, đừng vô ý gửi luôn session đã đăng nhập; nếu vậy response thành công không chứng minh cookie remember-me được dùng.
- Với logout, kiểm tra cookie deletion lẫn session, và test “copy cookie còn hợp lệ” riêng tùy implementation.
- Kiểm tra CSRF rules của route; nếu disable CSRF toàn bộ chỉ để test dễ hơn, bạn đã làm mất một phần hành vi thật.
- Đánh giá status đúng theo flow web (302 redirect form login) và API (401/403), không ép một status cho mọi architecture.

## 14. Những sai lầm phổ biến

1. **Chỉ assert 302 sau login:** không biết session ID có đổi, auth có đúng, remember-me có được cấp không.
2. **Dùng cùng session cho hai tab để test concurrency:** chưa tạo hai sessions độc lập.
3. **Quên HttpSessionEventPublisher:** registry có thể không giảm session count khi timeout/destroy.
4. **Dựa vào in-memory SessionRegistry trên nhiều node:** mỗi node biết một phần sessions.
5. **Tưởng `maxSessionsPreventsLogin(false)` sẽ làm login mới thất bại:** thực tế policy expire-old cho phép phiên mới và expire phiên cũ.
6. **Chỉ test login thứ hai mà không gọi session cũ:** không chứng minh ConcurrentSessionFilter xử lý expired.
7. **Remember-me test gửi luôn JSESSIONID:** có thể đang dùng session, không phải remember-me.
8. **Đồng nhất xóa remember-me cookie với revoke token:** đặc biệt sai với token-based cookie đã bị sao chép.
9. **Dùng GET /logout làm thao tác logout khi CSRF enabled:** có thể chỉ ra trang confirmation.
10. **Disable CSRF cho suite:** test không còn phản ánh logout form/web thực.
11. **Dùng `@WithMockUser` để chứng minh session fixation protection:** không đi qua actual login authentication strategy.
12. **Giả định logout hủy mọi device:** mặc định chỉ current session, trừ khi đã triển khai logout-all.
13. **Quên session fixation với OAuth2/SAML/custom login:** các flow cần kiểm riêng.
14. **Bỏ qua account lock/reauth khi remember-me:** remembered auth có thể không đủ mạnh cho payment/password change.
15. **Log đầy đủ Set-Cookie, JSESSIONID hoặc remember-me:** biến test logs thành nguồn đánh cắp credential.

## 15. Checklist trước khi nghiệm thu

- [ ] Login thành công trên một session đã tồn tại làm thay đổi ID theo strategy đã chọn.
- [ ] Session ID cũ không replay được qua real container, không chỉ qua MockHttpSession object.
- [ ] Login fail không tạo authenticated session, không cấp remember-me cookie mới.
- [ ] Chính sách concurrency được xác nhận: expire-old **hoặc** prevent-new; test cả A lẫn B.
- [ ] SessionRegistry và session lifecycle event/cụm triển khai hoạt động đúng.
- [ ] Remember-me opt-in thực sự cấp cookie; no-session request dùng cookie mới chứng minh auto-login.
- [ ] Cookie lỗi/hết hạn bị từ chối; remembered auth không qua các bước yêu cầu fully-authenticated nếu policy đặt ra.
- [ ] Logout thực hiện qua POST + CSRF; thiếu CSRF không logout.
- [ ] Logout invalidates session hiện tại, xóa cookie đúng path/domain, request sau không còn authenticated qua session.
- [ ] Token-based vs persistent-token remember-me được phân biệt về thu hồi; không tuyên bố cookie deletion là revocation.
- [ ] Logout-all có test độc lập nếu sản phẩm cung cấp; OAuth token revocation được xử lý riêng.
- [ ] Có HTTP integration tests qua browser/cookie jars/HTTPS và multi-node nếu kiến trúc yêu cầu.
- [ ] Không để test suite ghi raw session/remember-me secrets vào logs.

**Tổng kết:** Kiểm thử bảo mật dựa trên phiên trong Spring Security Servlet phải đi qua **đúng luồng HTTP**, kiểm tra thay đổi session ID ở login, hành vi khi có nhiều sessions, khả năng nhớ đăng nhập **không phụ thuộc session cũ**, và việc logout thật sự hủy/dọn trạng thái phù hợp. MockMvc xác minh filter-chain logic; browser/container tests chứng minh cookie, session lookup và các trường hợp replay thực tế. Với remember-me, cần luôn phân biệt **xóa cookie phía client** với **thu hồi credential phía server**.
