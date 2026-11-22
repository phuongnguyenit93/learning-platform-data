# Kiểm thử đăng nhập: session fixation, phiên đồng thời, hết phiên và thu hồi truy cập

## 1. Mục tiêu và bốn nhóm kiểm thử không được đánh đồng

Khi kiểm thử đăng nhập bằng Spring Security, điều quan trọng không chỉ là người dùng nhập đúng mật khẩu và thấy trang chủ. Phải chứng minh **vòng đời của phiên HTTP sau khi đăng nhập** an toàn: không nâng quyền cho session ID đã được người khác biết trước, không vượt giới hạn số phiên, không tiếp tục truy cập sau khi phiên hết hiệu lực, và có cơ chế thu hồi truy cập theo đúng phạm vi.

Bài này tập trung vào ứng dụng **Servlet/Spring MVC với Spring Security 6.5 và Spring Boot 3.x, Java 17+**, sử dụng **Form Login và HttpSession**. Những API/cấu hình theo nhánh này sẽ được ghi rõ; khi sử dụng Spring Security 7/Boot 4, xác minh Javadoc đúng phiên bản. Với ứng dụng stateless Bearer JWT, lifecycle khác và **không thể lấy session fixation/session registry để mặc định coi JWT đã bị thu hồi**.

Bốn mục tiêu kiểm thử cốt lõi:

| Hạng mục | Rủi ro cần phòng tránh | Thao tác kiểm thử | Bất biến phải chứng minh |
| --- | --- | --- | --- |
| **Session fixation** | Session ID anonymous đã biết được dùng tiếp sau khi nạn nhân login | Lấy ID trước login, login thật, so ID và thử lại ID cũ | ID mới khác ID cũ; ID cũ không truy cập được quyền đã xác thực |
| **Phiên đồng thời** | Một tài khoản đăng nhập vượt giới hạn hoặc phiên cũ vẫn dùng khi bị đẩy ra | Login cùng user từ **hai cookie jar khác nhau** | Đúng policy “đẩy phiên cũ” hoặc “chặn login mới” |
| **Hết phiên** | Session quá thời gian không hoạt động/đã bị đánh dấu expired vẫn mở trang bảo vệ | Tạo phiên, đưa đến mốc TTL hoặc expire theo policy | Request tiếp theo không còn principal hợp lệ |
| **Thu hồi truy cập** | Logout, khóa tài khoản, thay mật khẩu hoặc admin revoke nhưng cookie cũ vẫn dùng | Logout/revoke ở server; dùng lại cookie cũ trên browser khác | Phạm vi session được thu hồi thật, không chỉ xóa cookie phía client |

**Hai khái niệm quan trọng cần nhớ:** `Authentication` là danh tính được giữ trong `SecurityContext`; `HttpSession` là dữ liệu phiên được quản lý bởi Servlet container/Spring Session. Cookie `JSESSIONID` (hoặc `SESSION` khi dùng một số cấu hình Spring Session) chỉ chứa **mã định danh** cho server tìm phiên, không chứa đầy đủ vai trò và trạng thái xác thực.

Một phiên cookie hiện hành là **bearer credential**: nếu bị đánh cắp, nó có thể bị sử dụng trong thời gian phiên còn hợp lệ. Đổi session ID lúc login giải quyết *fixation*, nhưng **không tự ngăn việc lạm dụng ID mới nếu ID mới bị trộm sau login**.

## 2. Kiến trúc Servlet session: nơi Spring Security và container gặp nhau

Đường đi thông dụng:

```text
Browser A
  Cookie: JSESSIONID=S1
      |
      v
Servlet Container (HttpSession S1; maxInactiveInterval)
      |
      v
SecurityFilterChain
  SecurityContextHolderFilter
      |  đọc SecurityContextRepository
      |  thường gắn SecurityContext đã lưu trong HttpSession
      v
Authentication (principal=alice, authorities=[ROLE_USER])
      |
      v
AuthorizationFilter / method security
      |
      v
Controller nhận request nếu được cho phép

POST /login đúng credentials:
  UsernamePasswordAuthenticationFilter -> AuthenticationManager
  -> SessionAuthenticationStrategy (bao gồm fixation/concurrency)
  -> lưu SecurityContext -> HTTP session/cookie
```

Các trách nhiệm riêng biệt:

- **Servlet container/Spring Session:** tạo session ID, TTL idle, phiên còn tồn tại hay không, sự kiện tạo/xóa session.
- **Spring Security:** xử lý authentication, chọn chiến lược fixation protection, giới hạn concurrency, lưu/đọc SecurityContext và logout handlers.
- **SessionRegistry:** theo dõi những session đang đăng nhập cho mỗi principal để phục vụ concurrency/expire; registry không phải lúc nào cũng là toàn bộ kho HttpSession.
- **Client/browser:** giữ cookie và gửi cookie theo domain/path/Secure/SameSite. Hai tab trong **cùng profile browser** thường chia sẻ một cookie jar và vì vậy **không phải hai phiên độc lập**.
- **Ứng dụng nghiệp vụ:** kiểm quyền với resource, account disabled/locked, MFA step-up, tenant, payment/ownership. Session còn sống không bảo đảm quyền không thay đổi kể từ login.

Trong Spring Security 6, `SecurityContextHolderFilter` mặc định đọc context; nếu **custom authentication filter/controller tự set** `SecurityContextHolder` thì muốn lưu cho request sau phải dùng đúng `SecurityContextRepository.saveContext(...)` và bảo đảm `SessionAuthenticationStrategy` được gọi đúng lúc. Không nghĩ rằng mọi trường hợp “đã setContext” tự tạo session hoặc đổi ID.

## 3. Session fixation: thử ID trước và sau khi nâng quyền

**Session fixation**: attacker biết hoặc gắn một anonymous session ID vào browser nạn nhân trước login. Nếu ứng dụng tiếp tục dùng cùng ID sau khi nạn nhân nhập mật khẩu đúng, attacker có thể dùng ID cũ để truy cập session đã được nâng quyền.

```text
T0: Browser A chưa login, có session ID = S_old
T1: Browser A POST /login với password hợp lệ, CSRF hợp lệ
T2: Container/Spring Security đổi ID S_old -> S_new
T3: Browser A GET /me với S_new -> 200, principal=alice
T4: Browser B chỉ giữ S_old gọi /me -> không authenticated
T5: Browser B dùng S_new đã bị lộ (negative demonstration)
    -> có thể vẫn truy cập nếu không có binding/thu hồi khác
```

**Điều phải assert:** `S_old != S_new`, cookie response dùng S_new (trong E2E), session S_old không còn là phiên authenticated, và context sau login đúng user. Đừng chỉ assert login trả HTTP 302: **thành công và thất bại** của Form Login đều có thể redirect.

Spring Security Servlet hỗ trợ các strategy:

| Cấu hình | Cách hoạt động | Lưu ý kiểm thử |
| --- | --- | --- |
| `changeSessionId()` | Gọi `HttpServletRequest.changeSessionId()`: đổi ID, không tạo session object mới | **Mặc định** trên Servlet 3.1+; các session attributes vẫn còn |
| `migrateSession()` | Tạo session mới và copy toàn bộ attributes cũ | Kiểm pre-login dữ liệu nhạy cảm, CSRF/pending-MFA |
| `newSession()` | Tạo session mới sạch, giữ một số thuộc tính liên quan Spring Security | Không mặc định xóa mọi dấu vết/cookie khác |
| `none()` | Tắt fixation protection | Không khuyến nghị cho interactive cookie login |

Cấu hình rõ ý định:

```java
http.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.changeSessionId()));
```

Đây là **fragment** đặt trong method tạo `SecurityFilterChain`, không phải chương trình Java độc lập. Với Servlet hiện đại, dòng cấu hình này thường lặp lại mặc định để reviewer nhìn thấy chính sách.

**Cẩn thận với session object và test:** `changeSessionId()` có thể đổi ID ngay **trên cùng đối tượng MockHttpSession**. Nếu bạn so `beforeSession.getId()` *sau* khi đã login với `afterSession.getId()`, hai reference có thể trỏ cùng object mới, gây test sai. Phải **snapshot String oldId trước login**.

**Cảnh báo ranh giới:** cố định/đổi ID không ngăn XSS, session cookie theft, stolen remember-me cookie, OAuth access token reuse hoặc chuyện roles đã bị thu hồi. Đây là các threat và cơ chế riêng.

## 4. Phiên đồng thời: chính sách “đẩy phiên cũ” hoặc “chặn phiên mới”

Spring Security 6.5 hỗ trợ cấu hình concurrent session control cho Form Login:

### 4.1. Cho phép đăng nhập mới và đánh dấu phiên cũ hết hiệu lực

```java
http.sessionManagement(session -> session
    .maximumSessions(1));
```

Với chính sách mặc định này:

1. Browser A đăng nhập thành công tài khoản Alice → session `SA`.
2. Browser B ở **profile/ẩn danh độc lập** đăng nhập Alice → session `SB`.
3. Spring Security cho phép B, **đánh dấu SA expired** (thường phiên cũ ít được dùng gần đây nhất).
4. Khi A gửi request mới, `ConcurrentSessionFilter` thấy SA đã expired và áp `SessionInformationExpiredStrategy`; SA không còn có quyền.
5. B dùng SB tiếp tục truy cập theo role.

**Không nói rằng SA luôn bị xóa khỏi store ngay tại giây B login**. `SessionInformation` của Spring phân biệt **active**, **expired** (đánh dấu cần chấm dứt) và **destroyed** (session đã bị container invalidate/loại bỏ). Filter thường xử lý SA ở **request tiếp theo**. Test cần gửi request tiếp theo từ A.

Nếu muốn redirect trang hết hạn do concurrency:

```java
http.sessionManagement(session -> session
    .maximumSessions(1)
    .expiredUrl("/session-expired"));
```

Trang đích phải được truy cập công khai và không tạo vòng lặp redirect. Với API dùng JSON, dùng `expiredSessionStrategy(...)` trả response phù hợp thay vì redirect HTML.

### 4.2. Giữ phiên cũ, từ chối lần đăng nhập mới

```java
http.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true));
```

Với chính sách này:

- A đã đăng nhập Alice, SA còn active.
- B nhập **đúng** username/password Alice nhưng **bị từ chối tạo phiên thứ hai** do quota.
- A vẫn được truy cập. Browser B không có principal authenticated cho Alice.
- Form login thông thường chuyển B tới authentication failure URL; không nhất thiết là HTTP 403. Một cơ chế non-interactive có thể trả HTTP 401.

**Không test bằng cách mở tab mới trong cùng browser** vì A và “B” có thể dùng chung cookie và do đó không phát sinh session thứ hai. Dùng hai browser profiles hoặc hai cookie jars trong E2E; trong MockMvc thực hiện hai login requests độc lập không mang session của nhau.

### 4.3. HttpSessionEventPublisher và SessionRegistry

Để theo dõi sự kiện session bị xóa/hết hạn, tài liệu Spring Security 6.5 hướng dẫn đăng ký:

```java
@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
```

Import `org.springframework.security.web.session.HttpSessionEventPublisher`. Nó truyền sự kiện HttpSession lifecycle vào application context; nếu không, in-memory `SessionRegistryImpl` có thể **giữ các session IDs đã kết thúc**, làm quota tính sai và từ chối login mới dù phiên cũ đã hết thật.

Nếu dùng custom `UserDetails` làm principal, phải cài `equals/hashCode` ổn định theo identity. `SessionRegistryImpl` dùng Map keyed theo principal; nếu cùng account được nạp thành objects “khác nhau” theo `equals`, concurrency quota có thể bị bypass. Đừng dùng mutable fields/role list của principal làm khóa so sánh khiến key không ổn định.

**Giới hạn multi-node:** `SessionRegistryImpl` mặc định là registry ở bộ nhớ **một JVM**, không tự phối hợp quota trên nhiều pod. Với Spring Session + Redis/JDBC, cần cấu hình **shared session repository**, principal index, registry phù hợp như `SpringSessionBackedSessionRegistry` và test xuyên node. Không tuyên bố “đã thêm Redis là tự động enforce maxSessions toàn cluster” nếu chưa kiểm chứng registry/strategy.

## 5. Session timeout, session invalid và concurrent expired không cùng nghĩa

Phân biệt 5 cách kết thúc/không còn dùng được phiên:

| Trường hợp | Ai quyết định | Điều kiện | Trạng thái thường quan sát |
| --- | --- | --- | --- |
| **Idle timeout** | Servlet container/Spring Session | Không có access trong `maxInactiveInterval` | Session tự hết/hủy; request mang cookie cũ là invalid/anonymous |
| **Absolute timeout** (tùy bổ sung) | Chính sách ứng dụng | Tổng thời gian từ login vượt hạn, dù user còn thao tác | Phải được cài/test riêng; timeout idle không tự làm absolute |
| **Concurrency expiration** | Concurrent session strategy | Đăng nhập mới vượt limit và policy đẩy phiên cũ | `SessionInformation.isExpired()=true`, filter xử lý ở request kế |
| **Logout/session.invalidate()** | Người dùng/ứng dụng/container | Chủ ý kết thúc phiên | Session bị invalidate/destroy; cookie cũ không được xác thực |
| **Access token revoked/expired** | OAuth issuer/resource server | Token Bearer không còn được tin | Không đồng nghĩa HttpSession invalid; auth scheme khác |

### 5.1. Idle timeout với Spring Boot

Trong `application.yml` của project Spring Boot 3:

```yaml
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        http-only: true
        secure: true
        same-site: lax
```

`timeout: 20m` là **thời gian không hoạt động** của Servlet session (thời gian/độ chính xác thực tế phụ thuộc container/store). Request hợp lệ trong thời gian này có thể cập nhật last-access và kéo dài phiên. **Đây không phải absolute lifetime 20 phút tính từ lúc login**. Nếu quy định max session age 8 giờ từ lúc login, cần lưu loginAt đáng tin và enforce riêng, kể cả khi user có request đều đặn.

Cookie `Secure` yêu cầu HTTPS. Trong local development HTTP, browser có thể không gửi cookie Secure, làm bạn tưởng session bị mất; dùng profile test phù hợp. `SameSite=Lax` giúp giảm một số CSRF scenario, **không thay CSRF token** cho form POST; nếu OIDC/SAML callback cần cross-site POST, phải đánh giá cookie policy theo flow.

### 5.2. invalidSessionUrl vs expiredUrl

Ví dụ:

```java
http.sessionManagement(session -> session
    .invalidSessionUrl("/session-invalid")
    .maximumSessions(1)
    .expiredUrl("/session-expired"));
```

- `invalidSessionUrl`: quy định UX khi request mang **ID không còn hợp lệ** được nhận diện bởi session-management mechanism (ví dụ timeout hoặc ID stale). Nó không chỉ dùng cho idle timeout: một cookie giữ sau logout cũng có thể gây nhầm lẫn.
- `expiredUrl`: quy định UX khi `ConcurrentSessionFilter` thấy một **session đã bị concurrency policy đánh dấu expired**. Đây là trạng thái khác với cookie không tồn tại.
- Không tự tin rằng mọi request sau timeout luôn được redirect đến cùng URL trong mọi app: phụ thuộc filter chain, API/browser mode, cookie vẫn còn hay không, session store, app có dùng custom strategy không.
- Hai redirect URLs cần **permitAll**, trang đơn giản, không tự động tạo lại session/cookie gây redirect loop.

Tài liệu Spring lưu ý `invalidSessionUrl` có thể **đưa nhầm người dùng đến trang “hết phiên” sau logout** nếu cookie session cũ vẫn được browser gửi. Cần test xóa cookie phù hợp (Spring `deleteCookies("JSESSIONID")` là một lựa chọn, không phải mọi servlet container/proxy đều đảm bảo hoạt động giống nhau). Với Spring Session, tên cookie có thể là `SESSION` chứ không phải `JSESSIONID`.

### 5.3. Cách test timeout đáng tin

- **Unit test custom absolute timeout:** dùng injectable `Clock`/fixed `Instant`, kiểm ngay trước/đúng/sau expiry. Tránh `Thread.sleep(20 phút)` trong CI.
- **Servlet integration:** dùng test profile có timeout ngắn và embedded container thật; không phải mọi `MockHttpSession` tự hết hạn chỉ vì đồng hồ tường thuật chạy qua mốc. Có thể chủ động invalidate trong MockMvc để test phản ứng **invalid** session, nhưng đó không chứng minh container idle expiration tự động.
- **Spring Session (Redis/JDBC):** cấu hình TTL test, kiểm backend store hết entry và request từ client cũ mất authentication; việc key expire và index cleanup có thể không xảy ra tại đúng nano-giây.
- **Concurrency expiration:** không chờ TTL, mà đăng nhập bằng hai phiên rồi dùng lại session A để kiểm `expiredUrl`/không authenticated.

**Không nhầm “login page trả 200” với “resource vẫn truy cập được”**: HTTP clients thường follow redirect và hiển thị 200 của trang login, dù GET /me ban đầu đã 302.

## 6. Thu hồi truy cập: logout, admin revoke, đổi password và account bị khóa

### 6.1. Logout một phiên web

Với Spring Security Form Login và CSRF bật, `GET /logout` mặc định có thể là trang xác nhận, còn `POST /logout` với CSRF token hợp lệ thực hiện logout. Theo tài liệu, các logout handlers mặc định có nhiệm vụ:

- Vô hiệu hóa HTTP session (mặc định `SecurityContextLogoutHandler`).
- Xóa `SecurityContext`/repository.
- Dọn `remember-me` state nếu đã cấu hình.
- Xóa CSRF token tương ứng, phát `LogoutSuccessEvent`.
- Redirect về trang đã cấu hình, thường `/login?logout` với form login.

Cấu hình minh họa:

```java
http.logout(logout -> logout
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("JSESSIONID")
    .logoutSuccessUrl("/login?logout"));
```

**Không chỉ xóa cookie client:** nếu session server vẫn tồn tại, ai có cookie cũ có thể tiếp tục truy cập. Phải invalidate session tại server; cookie clearing chỉ bổ trợ browser không gửi lại mã stale. Với reverse proxy, context path/cookie Path/Domain và Servlet container, test `Set-Cookie` thật.

Sau logout, một request mới không còn principal authenticated. **Không đồng nghĩa** user bị xóa khỏi DB hoặc mọi session của user đã logout.

### 6.2. “Đăng xuất khỏi tất cả thiết bị”

Logout một phiên hiện hành khác với **revoke tất cả sessions của account**. Một tính năng “Log out all devices” cần:

1. Xác định stable identity/account ID, tenant/realm và toàn bộ sessions đã đăng ký hoặc được lưu trong shared store.
2. Invalidate/expire **từng session** ở phía server hoặc áp một **authorization epoch/version** theo user để từ chối các session cũ khi có request.
3. Đồng bộ qua mọi node; kiểm quyền admin hoặc re-auth/step-up trước thao tác này.
4. Thực hiện idempotent, an toàn với retry và session vừa được tạo trong lúc revoke.
5. Test cookie trên cả browser A/B/C; không chỉ kiểm browser đang bấm nút.

Ở single JVM với `SessionRegistryImpl`, bạn có thể lấy `getAllSessions(principal,false)` rồi gọi `SessionInformation.expireNow()`; điều này **đánh dấu session là expired**, để filter xử lý lúc request đến, không nhất thiết xóa vật lý entry tức thì.

Một ví dụ khái niệm (không độc lập, chỉ dùng trong service có `SessionRegistry` đã được cấu hình đúng):

```java
for (SessionInformation info :
        sessionRegistry.getAllSessions(principal, false)) {
    info.expireNow();
}
```

Nhớ import `org.springframework.security.core.session.SessionInformation`. Với admin revoke cần account principal chính xác và stable equality; không nhận object principal do browser tự gửi rồi tin nó. Nếu cần **ngay lập tức chặn** các session trước request kế tiếp, xây chính sách/trust check phù hợp trên mỗi request và state store có đảm bảo, thay vì chỉ dựa vào in-memory registry.

### 6.3. Disable account hay đổi mật khẩu không mặc định thu hồi mọi session

Sau khi user login, `Authentication`/authorities có thể đã lưu trong session. Nếu admin đổi account thành `enabled=false` hoặc thu hồi `ROLE_ADMIN` trong DB, **session đã authenticated có thể tiếp tục mang authorities cũ** nếu app không revalidate/revoke. Điều này cần thiết kế chính sách rõ:

- User bị khóa: chặn login mới ở `UserDetailsService`/provider và đồng thời decide revoke sessions cũ, refresh tokens, remember-me.
- Đổi mật khẩu: tùy rủi ro mà thu hồi toàn bộ hoặc trừ session hiện tại; cần kiểm old cookies, remember-me, other sessions.
- Đổi role/tenant: tránh duy trì privilege quá hạn; có session authorization/version/epoch hoặc invalidation.
- Resource authorization vẫn phải kiểm owner/tenant mỗi request (hoặc cache đúng TTL/invalidation). Không coi một session còn tồn tại là quyền bất biến.

### 6.4. JWT Bearer và OAuth không bị thu hồi bằng HttpSession.logout()

Một Resource Server xác minh `Authorization: Bearer JWT` theo chữ ký, `iss`, `aud`, `exp`, scopes có thể không có HttpSession. `POST /logout` của browser **không tự làm JWT đã cấp hết hạn**, cũng không tự revoke refresh token ở Authorization Server, hay IdP/OIDC session. Muốn thu hồi access token trước expiry cần denylist/blacklist `jti` được thực thi, introspection, sender-constrained token hoặc cơ chế phù hợp. Refresh token rotation/reuse detection là workflow riêng.

**Phạm vi báo cáo:** ghi rõ “đã revoke Servlet sessions” hay “đã revoke OAuth tokens”; không gộp chúng thành một kết luận “người dùng không còn quyền trên mọi hệ thống”.

## 7. Ví dụ Spring Boot 3 + Spring Security 6.5, Java 17

### 7.1. Dependencies

Tạo dự án Spring Boot 3.x (Java 17+, Servlet/Spring MVC) với Gradle và Spring Security. Trong `build.gradle` đã có Boot plugin/Java toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Không trộn code Servlet này với `ServerHttpSecurity`/`WebSession` của WebFlux. Nếu bạn định dùng Spring Session Redis, cần thêm dependency tương ứng và cấu hình store riêng.

### 7.2. Main application

File `src/main/java/com/example/sessiontests/SessionTestsApplication.java`:

```java
package com.example.sessiontests;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionTestsApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionTestsApplication.class, args);
    }
}
```

### 7.3. SecurityConfig với fixation, concurrency và logout

File `src/main/java/com/example/sessiontests/SecurityConfig.java`:

```java
package com.example.sessiontests;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                "/", "/public/start", "/login",
                                "/session-expired", "/session-invalid")
                        .permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionFixation(fixation -> fixation.changeSessionId())
                        .invalidSessionUrl("/session-invalid")
                        .maximumSessions(1)
                        .expiredUrl("/session-expired"))
                .logout(logout -> logout
                        .invalidateHttpSession(true)
                        .clearAuthentication(true)
                        .deleteCookies("JSESSIONID")
                        .logoutSuccessUrl("/login?logout"))
                .build();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-pass"))
                        .roles("USER")
                        .build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-pass"))
                        .roles("USER")
                        .build());
    }
}
```

**Đây là cấu hình CHỌN chính sách cho phép phiên mới**: `maximumSessions(1)` + `expiredUrl(...)` sẽ làm phiên Alice cũ bị expired sau khi Alice login ở browser khác. Muốn **chặn phiên mới**, thay đoạn concurrency bằng:

```java
.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.changeSessionId())
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true))
```

Không thêm cả hai kiểu vào cùng cấu hình. Khi chọn policy chặn login mới, có thể customize failure handler theo UX; default form login failure không được khẳng định luôn là một HTTP status 403.

**SecurityConfig chỉ là demo**: account `alice`/`bob` với password test và in-memory store; không kết nối database production. BCrypt encoder dùng salt/hash cho password, tránh cách `{noop}` hoặc hardcode credential vào repo thật. `.permitAll()` vẫn chạy Spring Security filters, không tắt CSRF.

### 7.4. PageController để quan sát session

File `src/main/java/com/example/sessiontests/PageController.java`:

```java
package com.example.sessiontests;

import java.security.Principal;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PageController {

    @GetMapping("/")
    public String home() {
        return "session test home";
    }

    @GetMapping("/public/start")
    public String start(HttpServletRequest request) {
        request.getSession(true); // tạo anonymous session để test fixation
        return "anonymous session created";
    }

    @GetMapping("/me")
    public String me(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/session-expired")
    public String expired() {
        return "concurrent session expired";
    }

    @GetMapping("/session-invalid")
    public String invalid() {
        return "invalid or timed-out session";
    }
}
```

Các endpoint public trả body cố định, **không trả JSESSIONID**, token CSRF hoặc session attributes nhạy cảm. Các trang `/session-expired` và `/session-invalid` được phép anonymous để không tạo redirect lặp do authorization; vẫn cần kiểm behavior thực tế với cookie stale.

### 7.5. Timeout và cookie trong application.yml

```yaml
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        http-only: true
        secure: true
        same-site: lax
```

Áp cho production HTTPS. Trong local HTTP có thể phải dùng **test-only profile** điều chỉnh Secure cookie để browser test nhận cookie; không hạ chuẩn TLS trên môi trường thật. Cookie attrs hạn chế một số đường lộ/sử dụng cookie, không tạo proof-of-possession.

### 7.6. Chạy thử

Trong project đã có Gradle wrapper:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

Mở hai browser profiles hoàn toàn độc lập. Ở browser A:

1. Vào `/public/start`, thấy cookie anonymous; ghi nhận **chỉ trong fixture/test tooling**, không log ID thật.
2. Truy cập `/me` → redirect login; đăng nhập `alice/alice-pass` bằng Form Login (có CSRF).
3. Sau login: `/me` → `hello alice`, session ID đã được rotate.
4. Browser B đăng nhập `alice/alice-pass` từ cookie jar riêng. Quay về browser A và gọi `/me`: A sẽ đi qua expired strategy, không còn được vào `/me`. B vẫn vào được.
5. Browser B POST `/logout` kèm CSRF hợp lệ. Thử cookie cũ từ test fixture ở request mới → không authenticated.
6. Test expiry của idle session bằng profile timeout nhỏ trong embedded container; không đợi 20 phút trong CI.

**Không copy session cookie/test password vào screenshot, shared logs hay bug ticket công khai**. Các credentials và URLs ở đây chỉ dành cho local/test.

## 8. MockMvc: kiểm session fixation bằng login thật, không dùng mock principal

Đặt `src/test/java/com/example/sessiontests/SessionLoginTest.java` vào project trên. Spring Security Test có `csrf()`, `authenticated()` và các request builders. Ví dụ dùng test class với Spring application context; để các tests không ảnh hưởng session registry của nhau, có thể dùng `@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)` trong project test nhỏ; cách này chậm, production CI nên reset registry/fixtures chủ động.

```java
package com.example.sessiontests;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SessionLoginTest {

    @Autowired
    MockMvc mvc;

    @Test
    void sessionIdChangesWhenUserLogsIn() throws Exception {
        MvcResult beforeResult = mvc.perform(get("/public/start"))
                .andExpect(status().isOk())
                .andReturn();

        MockHttpSession existingSession =
                (MockHttpSession) beforeResult.getRequest().getSession(false);
        assertThat(existingSession).isNotNull();
        String originalId = existingSession.getId();

        MvcResult loginResult = mvc.perform(post("/login")
                    .session(existingSession)
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "alice-pass"))
                .andExpect(authenticated())
                .andReturn();

        MockHttpSession afterSession =
                (MockHttpSession) loginResult.getRequest().getSession(false);
        assertThat(afterSession).isNotNull();
        assertThat(afterSession.getId()).isNotEqualTo(originalId);

        mvc.perform(get("/me").session(afterSession))
                .andExpect(status().isOk())
                .andExpect(content().string("hello alice"));
    }
}
```

Đây là test **cho đúng code example** trong mục 7. Static import `authenticated()` ở package `org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers`. Để xác thực đúng, không dùng `@WithMockUser` hoặc `.with(user("alice"))` vì chúng đưa principal trực tiếp vào test, **không chạy** real login/session strategy.

**Cần thêm kiểm thử E2E** với HTTP embedded container + cookie jars:

- Xem giá trị `Set-Cookie` session mới trên response; xác minh ID cũ không còn là session authenticated.
- Không dùng cùng reference `MockHttpSession` để giả lập browser đang mang ID cũ: nó có thể đã bị đổi ID trực tiếp.
- Khi cookie cũ được đưa từ jar thứ hai, xác minh response ban đầu là redirect/401 theo entry point, không nhầm 200 của login page nếu client follow 302.

MockMvc xác nhận logic ở tầng Spring/Test Servlet, còn embedded server xác nhận hành vi cookie, reverse proxy và container session lifecycle.

## 9. MockMvc: test phiên đồng thời trên hai session độc lập

Tiếp tục trong class integration riêng (hoặc thêm method vào `SessionLoginTest` nếu đã isolate application context):

```java
@Test
void secondLoginExpiresFirstSession() throws Exception {
    MvcResult resultA = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(authenticated())
            .andReturn();
    MockHttpSession sessionA =
            (MockHttpSession) resultA.getRequest().getSession(false);

    mvc.perform(get("/me").session(sessionA))
            .andExpect(status().isOk());

    MvcResult resultB = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(authenticated())
            .andReturn();
    MockHttpSession sessionB =
            (MockHttpSession) resultB.getRequest().getSession(false);

    assertThat(sessionA.getId()).isNotEqualTo(sessionB.getId());

    // Concurrency filter xử lý phiên cũ ở request kế tiếp.
    // Response cụ thể phụ thuộc expiredUrl/strategy và proxy.
    mvc.perform(get("/me").session(sessionA))
            .andExpect(status().is3xxRedirection());

    mvc.perform(get("/me").session(sessionB))
            .andExpect(status().isOk());
}
```

Đây là **method bổ sung** vào class ở mục 8 và dùng các imports/beans đã khai báo; không phải file Java độc lập. Trong project demo có `expiredUrl("/session-expired")`, có thể assert thêm redirect Location đến route tương ứng. Dùng `SessionRegistry` hoặc `SessionInformation.isExpired()` để phân biệt *đã đánh dấu expired* với *đã destroy*. Nếu framework test setup/expired strategy custom khác, assertion status phải được điều chỉnh đúng theo behavior đã cấu hình.

### Policy ngược lại: chặn phiên mới

Muốn test `maxSessionsPreventsLogin(true)`, tạo **một test application configuration riêng**:

```java
http.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true));
```

Kỳ vọng với hai cookie jars, đúng Alice login ở A trước:

- A vẫn authorized ở `/me`.
- B nhập password đúng nhưng **không được authenticated**, theo form-login failure handler.
- Sau A logout hoặc session thật bị destroy và registry nhận sự kiện, B có thể login nếu policy cho phép.
- Nếu B bị từ chối mãi sau khi A đã thật sự logout, kiểm `HttpSessionEventPublisher`, SessionRegistry stale, custom UserDetails equals/hashCode, nhiều node.
- Một HTTP 302 ở B **không đủ kết luận login thành công**: Form Login failure cũng redirect. Assert `unauthenticated()` và truy cập bảo vệ ở session B.

Không để cả policy đẩy phiên cũ và policy chặn phiên mới chạy trong cùng một SecurityFilterChain khi chưa chọn semantics yêu cầu.

## 10. Hết phiên: kiểm timeout và invalid cookie mà không tạo false positive

### 10.1. Manual invalidation ≠ idle timeout tự nhiên

Trong unit/MockMvc có thể kiểm:

```java
MockHttpSession session = new MockHttpSession();
session.setAttribute("marker", "test");
session.invalidate();
assertThat(session.isInvalid()).isTrue();
```

Đây là **test thao tác invalidate**, không kiểm container tự xóa session khi quá timeout. Đối với idle TTL thực, sử dụng embedded Servlet container với session timeout nhỏ ở test profile, kiểm hành vi expired cookie và authenticated state. Đối với absolute timeout do app tự cài, dùng injectable Clock và test boundary.

### 10.2. Kiểm đúng UX của invalidSessionUrl

Một request từ browser có cookie cũ sau timeout có thể đi tới `/session-invalid`. Nhưng request không có cookie có thể đi tới `/login`. Đừng assert “cứ anonymous là /session-invalid”; đây là logic của **ID không hợp lệ được gửi**. Trong test, cần chuẩn bị cookie jar/cookie ID cũ và test đúng filter chain.

Lưu ý Spring Security 6 không dùng `SessionManagementFilter` theo cùng cơ chế mặc định của Spring Security 5; vài hook session management cũ không còn có hiệu ứng hoặc đã được thay thế. Dựa trên Spring Security 6.5 reference/version đang dùng, không bịa lời gọi strategy sau custom authentication.

### 10.3. Kiểm expired do concurrency

Một session bị `SessionInformation.expireNow()` khác với session do container timeout. Vì thế có thể test rule thông qua registry/session strategy mà không chờ clock:

- Đăng nhập A tạo SA, xác nhận SA truy cập `/me`.
- Đăng nhập B cùng user, đánh dấu SA expired.
- Gửi GET với SA, xác nhận không vào resource và redirect/strategy đã cấu hình.
- Gửi GET với SB, xác nhận vẫn có user đúng.
- Assert không có side effect từ request SA đã hết quyền.

Không lấy “đã bị đánh dấu” làm bằng chứng “đã lập tức invalidate HttpSession vật lý”; phải test request tiếp theo và state ở store.

## 11. Thu hồi truy cập: cách kiểm logout và revoke trên nhiều thiết bị

### 11.1. Logout session hiện tại

Trong test tích hợp có thể login rồi gửi:

```java
mvc.perform(post("/logout")
        .session(sessionA)
        .with(csrf()))
    .andExpect(status().is3xxRedirection());

// Nếu dùng MockHttpSession của cùng fixture:
assertThat(sessionA.isInvalid()).isTrue();
```

Đoạn trên là **fragment** trong test class đang có `MockMvc mvc` và `MockHttpSession sessionA`, không phải test standalone. Một `MockHttpSession` đã invalidated không nên được nạp lại qua `.session(sessionA)` để cố test request mới: có thể ném exception ở test machinery. Để kiểm **cookie cũ** trên wire, dùng browser/HTTP test với embedded container + cookie jar thứ hai, hoặc query session store đúng API.

Test HTTP E2E nên xác minh cả **logout response**, **store không còn session hợp lệ**, và **GET /me với cookie cũ không authenticated**. Nếu chỉ xóa `JSESSIONID` ở trình duyệt và không kiểm server-side store, test vẫn có thể bỏ sót hijacking sau logout.

### 11.2. Admin revoke all sessions

Tạo ít nhất hai sessions A/B cùng account trên môi trường **cho phép >=2 sessions** (không dùng policy `maximumSessions(1)` vì A sẽ hết hạn trước test). Sau đó gọi nghiệp vụ revoke bằng quyền admin hoặc account owner có step-up:

1. Xác định đúng account ID; không để user A gửi `username=bob` rồi revoke Bob tùy ý.
2. Revoke A và B trong registry/shared store, hoặc tăng per-user revocation epoch được check trên mỗi request.
3. Dùng lại cookie A/B từ hai browser để gọi resource bảo vệ; **cả hai đều không còn được truy cập**.
4. Kiểm request C của user khác vẫn được; không vô tình thu hồi toàn bộ hệ thống.
5. Dùng cơ chế đồng bộ xuyên node và kiểm xử lý request đang chạy; một request đã bắt đầu trước revocation có thể cần chính sách riêng để dừng side effect quan trọng.
6. Nếu hệ thống có remember-me/OAuth token, test độc lập việc chúng được revoke hay không theo yêu cầu.

### 11.3. Đổi password, disable account và quyền đã thu hồi

Dùng fixture có Alice logged-in và Alice password change/disable trong database. Một test cần phân biệt:

- **New login:** provider phải từ chối credentials cũ hoặc user disabled theo policy.
- **Existing session:** nếu chỉ lưu Authentication snapshot mà không revalidate/revoke, cookie có thể vẫn được chấp nhận. Đó là behavior cần thiết kế, không mặc nhiên xem đổi password là logout all.
- **Remember-me auto-login:** nếu có bật, phải kiểm persistent token store/hash-based token lifecycle riêng.
- **JWT access token:** có thể sống tới expiry nếu không có introspection/denylist; đừng kết luận xóa HttpSession đủ thu hồi JWT.
- **Role/resource authorization:** user bị thu hồi ROLE_ADMIN nhưng session vẫn có cached ROLE_ADMIN cần được invalidate hoặc policy read latest state theo yêu cầu.

## 12. Spring Session Redis và multi-node: test là bắt buộc

Nếu hệ thống có nhiều instances, mỗi instance có local HttpSession và `SessionRegistryImpl` riêng, cùng Alice có thể đăng nhập trên hai pod mà mỗi pod đều tưởng chỉ một session. Sticky sessions có thể làm giảm vấn đề routing nhưng không tạo **registry chung** hoặc giải quyết revoke all.

Spring Session thay `HttpSession` bằng repository tập trung, có adapter Redis/JDBC. Với Spring Session Redis, cookie thường tên `SESSION`; điều này ảnh hưởng tới test cookie jar, logout cookie name và invalidation flow.

Để dùng Spring Session (cấu hình phụ thuộc dòng Spring Boot/Spring Session), thêm starter do BOM quản lý, ví dụ trong dự án hỗ trợ:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-session-data-redis'
}
```

Sau đó cấu hình Redis connection/session repository theo tài liệu Boot chính xác đang chạy. **Không đưa thông tin Redis credentials vào code**; dùng secret management. Để concurrency control hoạt động **trên cluster**, xem xét `SpringSessionBackedSessionRegistry` với `FindByIndexNameSessionRepository` có principal index. Phải kiểm principal name mapping đồng nhất, event forwarding và policy của từng node.

Checklist E2E cluster:

| Kịch bản | Pod A | Pod B | Kỳ vọng |
| --- | --- | --- | --- |
| Session A login | Tạo session A | Đọc session A | Cùng identity nếu store chia sẻ |
| Session B login cùng Alice | Registry/store biết A | Đăng nhập B | Policy maxSessions thực thi xuyên node |
| A bị expired | Nhận lại cookie A | Xử lý tại B | Không còn authenticated |
| A logout | Invalidate A ở shared store | GET với A tới B | B từ chối |
| Admin revoke Alice | Revoke all A/B | Request tới cả A/B | Cả hai từ chối |
| Node restart | A mất in-memory cache | B giữ shared store | Chính sách theo durable/revocation store |
| Redis outage | Không lấy được session | Bypass không được phép | Fail closed theo policy, metrics/alerts |

Không assert rằng cài `spring-boot-starter-session-data-redis` **mặc nhiên** biến SessionRegistryImpl thành distributed registry. Cần test bằng **hai HTTP clients, hai ứng dụng/instances và session repository thật**. In-memory test Mockito không thay được bằng chứng này.

## 13. Java 17 thuần: mô phỏng session ID rotation, concurrency và revoke

Ví dụ sau có thể biên dịch bằng **JDK 17+ không cần Spring**, dùng một in-memory store có synchronized methods để mô hình hóa hành vi. Nó tách:

- Session anonymous S0 và session authenticated S1;
- Đổi ID khi login, S0 bị loại khỏi store;
- `maxSessions=1` theo policy cho login mới làm session cũ mất hiệu lực;
- Idle expiration sau 20 phút không hoạt động;
- Logout xóa session;
- User Bob khác không bị ảnh hưởng bởi revoke Alice.

**Giới hạn:** synchronized chỉ bao phủ **một đối tượng trong một JVM**, không chứng minh concurrency safety trong Redis/JDBC/multi-node. Production dùng Servlet/Spring Security, không tự cài session store từ code lab.

Lưu thành `SessionLifecycleLab.java`:

```java
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public final class SessionLifecycleLab {

    private static final Duration IDLE = Duration.ofMinutes(20);
    private static final SecureRandom RANDOM = new SecureRandom();

    record Session(String principal, Instant lastAccess) {}

    private final Map<String, Session> sessions = new HashMap<>();
    private final Map<String, String> activeByUser = new HashMap<>();

    private static String newId() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }

    synchronized String anonymous(Instant now) {
        String id = newId();
        sessions.put(id, new Session(null, now));
        return id;
    }

    synchronized String loginRotate(
            String anonymousId, String username, Instant now) {
        Session before = sessions.remove(anonymousId);
        if (before == null || before.principal() != null) {
            throw new IllegalStateException("Not an anonymous session");
        }

        String authenticatedId = newId();
        String priorId = activeByUser.put(username, authenticatedId);
        if (priorId != null) {
            // Mô hình policy maxSessions=1 đẩy phiên cũ.
            sessions.remove(priorId);
        }
        sessions.put(authenticatedId, new Session(username, now));
        return authenticatedId;
    }

    synchronized boolean authorized(
            String id, String username, Instant now) {
        Session s = sessions.get(id);
        if (s == null || !Objects.equals(username, s.principal())) {
            return false;
        }
        if (!now.isBefore(s.lastAccess().plus(IDLE))) {
            sessions.remove(id);
            activeByUser.remove(username, id);
            return false;
        }
        sessions.put(id, new Session(s.principal(), now));
        return true;
    }

    synchronized void logout(String id) {
        Session removed = sessions.remove(id);
        if (removed != null && removed.principal() != null) {
            activeByUser.remove(removed.principal(), id);
        }
    }

    public static void main(String[] args) {
        Instant t0 = Instant.parse("2026-11-06T00:00:00Z");
        SessionLifecycleLab lab = new SessionLifecycleLab();

        String anonymous = lab.anonymous(t0);
        System.out.println("preLoginAllowed=" +
                lab.authorized(anonymous, "alice", t0));

        String first = lab.loginRotate(anonymous, "alice", t0);
        System.out.println("rotated=" + !anonymous.equals(first));
        System.out.println("oldIdRejected=" +
                !lab.authorized(anonymous, "alice", t0));
        System.out.println("newIdAllowed=" +
                lab.authorized(first, "alice", t0));

        String second = lab.loginRotate(
                lab.anonymous(t0), "alice", t0.plusSeconds(60));
        System.out.println("firstExpiredBySecond=" +
                !lab.authorized(first, "alice", t0.plusSeconds(61)));
        System.out.println("secondAllowed=" +
                lab.authorized(second, "alice", t0.plusSeconds(61)));

        System.out.println("idleExpired=" +
                !lab.authorized(second, "alice",
                        t0.plus(Duration.ofMinutes(25))));

        String third = lab.loginRotate(
                lab.anonymous(t0), "alice", t0);
        lab.logout(third);
        System.out.println("logoutRevoked=" +
                !lab.authorized(third, "alice", t0));

        String bob = lab.loginRotate(
                lab.anonymous(t0), "bob", t0);
        System.out.println("anotherUserUnaffected=" +
                lab.authorized(bob, "bob", t0));
    }
}
```

Biên dịch/chạy tại thư mục chứa file:

```bash
javac SessionLifecycleLab.java
java SessionLifecycleLab
```

Stdout **xác định** (ID được sinh ngẫu nhiên nhưng chương trình không in ID):

```text
preLoginAllowed=false
rotated=true
oldIdRejected=true
newIdAllowed=true
firstExpiredBySecond=true
secondAllowed=true
idleExpired=true
logoutRevoked=true
anotherUserUnaffected=true
```

Giải thích:

- `preLoginAllowed=false` và `oldIdRejected=true` cho thấy anonymous ID không thành authenticated ID sau login.
- `rotated=true`: session ID được thay. `newIdAllowed=true` cho thấy session mới nhận quyền Alice.
- `firstExpiredBySecond=true`: mô hình maxSessions=1 không cho hai session Alice đồng thời.
- `secondAllowed=true`: đăng nhập mới còn hiệu lực.
- `idleExpired=true`: sau 25 phút không truy cập, session không còn hợp lệ theo TTL 20 phút.
- `logoutRevoked=true`: xóa session server-side làm ID cũ không truy cập được.
- `anotherUserUnaffected=true`: revoke Alice không được làm mất session của Bob.

**Không nhầm ví dụ với Spring session registry:** code lab xóa phiên trước lập tức khi login mới, còn Spring Security có thể **mark expired rồi xử lý ở request tiếp theo**. Code lab không dùng HTTP, CSRF, cookie, session fixation strategy chính thức, SessionRegistry hay Redis. Nó chỉ dùng để kiểm tư duy và ranh giới.

## 14. Ma trận kiểm thử đăng nhập và thu hồi

| ID | Bối cảnh | Hành động | Kỳ vọng |
| --- | --- | --- | --- |
| S01 | Anonymous session SA | Login thật bằng password đúng | ID đổi sang SB, principal đúng |
| S02 | Login thành công | Gửi cookie SA cũ từ HTTP client khác | Không thấy authenticated data |
| S03 | Login thành công | Gửi cookie SB mới | Authorized theo role |
| S04 | Login sai password | So ID/authentication | Không được nâng anonymous session thành authenticated |
| S05 | App dùng custom login filter | Login thành công | SessionAuthenticationStrategy và persistence thực sự áp dụng |
| C01 | Alice login A | Alice login B, default maximumSessions(1) | B pass, A expired trên request kế |
| C02 | Alice login A | Alice login B, maxSessionsPreventsLogin(true) | B fail, A vẫn pass |
| C03 | Alice logout A | Alice login B sau logout | B có thể login nếu quota giải phóng đúng |
| C04 | UserDetails custom equality sai | Hai login cùng account | Test phát hiện registry không đếm sai |
| C05 | Alice dùng hai tab cùng browser | Truy cập A/B | Chỉ một session; không dùng làm test concurrency |
| T01 | Session idle dưới timeout | GET protected | Pass |
| T02 | Session idle vượt timeout | GET protected với cookie stale | Không authenticated; invalid UX đúng |
| T03 | User hoạt động liên tục | Quá absolute timeout riêng của app | Re-auth bắt buộc nếu policy yêu cầu |
| T04 | Session bị concurrency expire | GET trên cookie phiên cũ | Expired strategy, không vào controller |
| T05 | Cookie đã mất nhưng client dùng URL cũ | GET /me | Login/401 theo chain, không coi 200 trang login là pass |
| R01 | A login | POST /logout + CSRF | Session invalidated, context cleared |
| R02 | A đã logout | Dùng lại cookie A ở browser thứ hai | Không authenticated |
| R03 | A và B cùng account (policy >=2) | Admin revoke all sessions | A và B không còn truy cập |
| R04 | Alice và Bob có session riêng | Revoke Alice | Bob không bị chặn |
| R05 | Account Alice disabled | Login mới và cookie session cũ | Login mới bị chặn; session cũ theo chính sách revoke đã thiết kế |
| R06 | Alice password changed | Gửi lại remember-me cookie | Có xử lý revocation riêng; không tự assume |
| R07 | Alice web logout | Dùng Bearer JWT độc lập còn hạn | Có thể vẫn hợp lệ nếu không có token revocation |
| M01 | App hai pod, shared store | Login ở A, request ở B | Cùng authentication/session state |
| M02 | App hai pod, quota 1 | Login Alice đồng thời qua A/B | Không vượt quota theo policy cluster |
| M03 | App hai pod, revoke Alice | Dùng cookie tại cả A/B | Cả hai từ chối, không stale state |
| M04 | Store Redis timeout | GET /me | Fail closed hoặc behavior theo security policy, không tự bypass |

**Kỹ thuật test:** test fixation có một browser/phiên trước và sau login; test concurrency dùng **hai browser/cookie jars độc lập**; test revocation dùng **cookie đã được cấp thật** sau logout/revoke; test timeout cần cơ chế clock/expiry đúng tầng. Không dùng `@WithMockUser` để chứng minh login/session strategy: nó chỉ gắn mock principal, bỏ qua credential verification và session lifecycle.

Khi request bị từ chối, assert **không có side effect**: không thay đổi payment, không đọc được dữ liệu riêng tư, không gọi dịch vụ nhạy cảm. Chỉ thấy HTTP 302 hoặc 403 có thể chưa đủ nếu test bị chặn bởi CSRF hoặc redirect tới login page.

## 15. Troubleshooting: lần đăng nhập thứ hai, phiên cũ và lỗi logout

| Triệu chứng | Nguyên nhân có thể | Bước chẩn đoán |
| --- | --- | --- |
| Login A rồi B vẫn cả hai truy cập | Chưa cấu hình maximumSessions, registry không dùng chung hoặc sai equals/hashCode | Xem SessionRegistry, config chain, principal equality, cluster |
| Login B bị từ chối dù A đã logout | SessionRegistry vẫn ghi session cũ do thiếu events, timeout không được xử lý | Kiểm HttpSessionEventPublisher và session lifecycle |
| Tab thứ hai login không bị chặn | Hai tab chia sẻ cùng session | Dùng hai cookie jars độc lập |
| Test fixation thấy ID không đổi | Tắt strategy, custom filter bỏ qua strategy, test so cùng MockHttpSession reference | Snapshot ID trước login, dùng login thật |
| ID cũ vẫn truy cập sau login | Container/proxy/session store chấp nhận ID cũ hoặc test không tách jar | E2E kiểm ID stale và Set-Cookie |
| A bị logout ngay khi B login dù muốn chặn B | Đang dùng default expire-old policy | Đổi maxSessionsPreventsLogin(true) và test lại |
| B login trả 302 nên nghĩ đã pass | Form Login fail cũng redirect | Kiểm principal/Location/authenticated result |
| A bị đánh dấu expired nhưng còn record trong store | Spring có state expired trước destroyed | Gửi request A để ConcurrentSessionFilter xử lý |
| invalidSessionUrl báo hết phiên ngay sau logout | Browser còn cookie stale | Cookie clearing + custom invalid strategy, test thật |
| POST logout 403 | CSRF thiếu/sai | Gửi CSRF token thật, không disable global |
| Đã xóa cookie nhưng cookie copy vẫn dùng | Server session chưa invalidate | Kiểm store và SecurityContextLogoutHandler |
| Đổi mật khẩu mà session cũ vẫn vào | Không có revoke/recheck policy cho existing sessions | Revoke session/epoch; test all devices |
| Session hết khi HTTP còn hoạt động | Cookie Secure/SameSite/path mismatch, proxy, app restart, store TTL | Inspect browser Set-Cookie, server session repository |
| Session không bao giờ hết khi user thao tác | Chỉ có idle timeout, không có absolute | Cài absolute timeout riêng nếu cần |
| Redis session dùng cookie SESSION, code xóa JSESSIONID | Sai tên cookie | Kiểm Spring Session cookie serializer |
| User bị revoked nhưng JWT còn quyền | Servlet session revoke không ảnh hưởng JWT | Introspection/denylist/token lifecycle riêng |
| Cấu hình SessionCreationPolicy.STATELESS cùng Form Login | Không lưu SecurityContext vào HttpSession như dự kiến | Tách filter chains/stateless API vs web login |
| Test timeout MockMvc không hết theo clock | MockHttpSession không mô phỏng container TTL tự nhiên | Embedded container/store test hoặc custom Clock |
| Custom login POST trả 200 nhưng request sau anonymous | SecurityContext chưa được save, session strategy không chạy | Kiểm SecurityContextRepository, SessionAuthenticationStrategy |
| API redirect HTML trong khi muốn 401 | API dùng formLogin entry point | Tách chain và entry point theo auth scheme |

## 16. Checklist triển khai, giám sát và kết luận

- [ ] **Session fixation:** snapshot ID trước login; login thật; ID sau khác, ID cũ không có quyền.
- [ ] **Phiên đồng thời:** policy rõ “đẩy cũ” hay “chặn mới”; test hai cookie jars độc lập, cùng và khác principal.
- [ ] **Registry lifecycle:** HttpSessionEventPublisher được đăng ký khi dùng in-memory registry; principal equals/hashCode đúng, events dọn session stale.
- [ ] **Timeout:** phân biệt idle timeout, absolute lifetime riêng, concurrency expired và invalid ID; test boundary/UX theo từng cơ chế.
- [ ] **Logout:** POST có CSRF, server invalidate, SecurityContext được xóa; cookie cũ bị từ chối khi gửi lại.
- [ ] **Revoke all:** có cơ chế thu hồi toàn bộ phiên đã cấp cho user, xử lý race/node khác và giữ phiên người khác.
- [ ] **Account changes:** disabled/locked, password change, role change có kế hoạch xử lý existing sessions/remember-me và token khác.
- [ ] **Cookie:** HTTPS, Secure/HttpOnly/SameSite, đúng Domain/Path; không log hoặc chia sẻ JSESSIONID.
- [ ] **Spring 6.x:** custom authentication lưu SecurityContext tường minh và dùng SessionAuthenticationStrategy; không copy cơ chế v5 thiếu kiểm tra.
- [ ] **Cluster:** Spring Session + shared registry/principal index được test xuyên node; không chỉ dựa local SessionRegistryImpl.
- [ ] **API/JWT:** không gọi servlet session revoke là JWT/access/refresh token revoke; ghi rõ phạm vi biện pháp.
- [ ] **Test:** MockMvc xác minh login/session strategy, embedded-container E2E cho cookies, Redis/database cho cluster và expiry.
- [ ] **Observability:** đo login successes/failures, session ID rotations, concurrent-expiration, timeouts/revocations; chỉ log correlation ID, không log session IDs/raw cookies.
- [ ] **Security incidents:** nếu nghi session cookie bị đánh cắp, có khả năng revoke đúng user hoặc tất cả sessions và kiểm cảnh báo; cập nhật chính sách MFA nếu cần.

**Ghi nhớ cuối bài:** **Session fixation** cần đổi ID tại boundary đăng nhập; **concurrent sessions** cần registry và chính sách chọn “đẩy cũ” hoặc “chặn mới”; **session expiration** cần hiểu timeout idle/absolute và trạng thái expired/destroyed; **revocation** cần xử lý phía server chứ không chỉ xóa cookie. Một ứng dụng chỉ pass test login đúng mật khẩu chưa chứng minh an toàn cho vòng đời phiên.

### Tài liệu chính thức và tham khảo

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security 6.5 — SessionManagementConfigurer.ConcurrencyControlConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/SessionManagementConfigurer.ConcurrencyControlConfigurer.html)
- [Spring Security 6.5 — SessionInformation (active / expired / destroyed)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/session/SessionInformation.html)
- [Spring Security — SessionRegistryImpl](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/session/SessionRegistryImpl.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — MockMvc Authentication Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Session — Spring Boot with Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html)
- [Spring Session — SpringSessionBackedSessionRegistry](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/security/SpringSessionBackedSessionRegistry.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
