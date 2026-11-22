# oneTimeTokenLogin và các endpoint phát hành, tiếp nhận token trong Spring Security

## 1. Bản chất của One-Time Token Login (OTT)

Trong Spring Security, **One-Time Token Login (OTT)** là cơ chế đăng nhập bằng một token ngẫu nhiên, ngắn hạn và chỉ sử dụng một lần, thường được gửi qua email dưới dạng **magic link**. Người dùng nhập tên tài khoản, ứng dụng phát hành token cho yêu cầu đó rồi chuyển qua kênh đã xác minh. Khi người dùng gửi lại token qua endpoint đăng nhập, hệ thống tiêu thụ token, xác định tài khoản và tạo phiên đăng nhập nếu mọi kiểm tra hợp lệ.

`HttpSecurity.oneTimeTokenLogin(...)` xuất hiện trên Servlet stack từ **Spring Security 6.4**. Nó khác TOTP/HOTP (mã do shared seed và time/counter tạo), khác OAuth access token (ủy quyền gọi API), và khác password-reset token (phục vụ thay đổi mật khẩu). OTT không tự thay thế MFA hay việc kiểm soát quyền sau đăng nhập.

**Tư duy chính:** có **endpoint phát hành token**, **kênh giao token**, **trang nhận token** và **endpoint thật sự đăng nhập bằng token**. Spring Security đảm nhiệm phần filter/service/Authentication; ứng dụng phải chủ động giao token tới địa chỉ đáng tin.

### Mục tiêu học tập

- Hiểu chính xác `POST /ott/generate` khác `GET /login/ott` và `POST /login/ott`.
- Phân biệt `GenerateOneTimeTokenFilter`, `OneTimeTokenGenerationSuccessHandler`, `OneTimeTokenService` và `OneTimeTokenAuthenticationFilter`.
- Biết cấu hình servlet web app Java 17+/Spring Boot 3.x với magic link email và CSRF.
- Biết tùy chỉnh URL, thời hạn, nơi lưu token, đồng thời tránh replay, enumeration, host-header poisoning và race condition.
- Có tiêu chí test token chỉ dùng một lần, hết hạn và email được giao tới đúng tài khoản.

## 2. Sơ đồ end-to-end: phát hành → gửi → xem form → tiêu thụ

```text
Browser                        App / Spring Security               Email + OTT Store
  |                                    |                                  |
  | GET /login                         |                                  |
  |----------------------------------->|                                  |
  |<------------ login page -----------|                                  |
  |                                    |                                  |
  | POST /ott/generate                 |                                  |
  | username=alice + CSRF              |                                  |
  |----------------------------------->|                                  |
  |                          GenerateOneTimeTokenFilter                   |
  |                            -> resolver username                       |
  |                            -> OneTimeTokenService.generate() -------->|
  |                            -> success handler gửi email ------------>|
  |<------------ 302 /ott/sent --------|                                  |
  |                                    |                                  |
  | Email có /login/ott?token=T        |                                  |
  | GET /login/ott?token=T             |                                  |
  |----------------------------------->|                                  |
  |<------ form đã điền token ---------|                                  |
  |                                    |                                  |
  | POST /login/ott                    |                                  |
  | token=T + CSRF                     |                                  |
  |----------------------------------->|                                  |
  |                        OneTimeTokenAuthenticationFilter               |
  |                          -> AuthenticationProvider                    |
  |                          -> OneTimeTokenService.consume(T) ---------> loại T
  |                          -> UserDetails / Authentication             |
  |                          -> SecurityContext, HTTP session            |
  |<------------ redirect login -------|                                  |
  |                                    |                                  |
  | GET /private + session cookie      |                                  |
  |----------------------------------->|                                  |
  |<------------ Welcome alice --------|                                  |
```

**Đặc biệt:** mở magic link bằng **GET** thường chỉ hiển thị trang để xác nhận/submit token. GET không tự xác thực. Trong cơ chế Servlet mặc định, bước **POST /login/ott** mới xử lý xác thực và tiêu thụ token. Điều này giúp tránh một số email scanner tự động prefetch link GET làm mất hiệu lực token, nhưng không bảo đảm chống mọi scanner có thể tương tác sâu hơn.

## 3. Bảng endpoint mặc định

| Endpoint | Trách nhiệm | Dữ liệu bắt buộc | Xử lý bởi |
| --- | --- | --- | --- |
| `GET /login` | Trang bắt đầu yêu cầu OTT (nếu dùng trang sinh mặc định) | Chưa đăng nhập | `DefaultLoginPageGeneratingFilter` |
| **`POST /ott/generate`** | **Phát hành OTT** | `username`, CSRF nếu bật | `GenerateOneTimeTokenFilter` |
| `GET /login/ott?token=T` | Hiển thị form nhập token, có thể tự điền T | Query `token` | `DefaultOneTimeTokenSubmitPageGeneratingFilter` |
| **`POST /login/ott`** | **Nhận và tiêu thụ OTT để đăng nhập** | Form `token`, CSRF nếu bật | `OneTimeTokenAuthenticationFilter` |
| `GET /ott/sent` | Thông báo đã gửi hướng dẫn; **ứng dụng tự định nghĩa** | Không có | Controller/handler ứng dụng |
| `GET /private` | Endpoint yêu cầu session authenticated | Cookie session sau login | SecurityFilterChain + controller |

Có thể không thấy `GET /login` nếu bạn thay login page; hai POST vẫn là những endpoint quan trọng. **Không tự tạo MVC controller xử lý trùng POST /ott/generate hoặc POST /login/ott** khi vẫn để Spring Security filter xử lý các path đó.

### Request minh họa

Bước phát hành:

```http
POST /ott/generate HTTP/1.1
Host: app.example.test
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=<session-cookie>

username=alice&_csrf=<csrf-token>
```

Email có URL, ví dụ:

```text
https://app.example.test/login/ott?token=<unguessable-token-value>
```

Khi browser mở liên kết, form mặc định được điền token. Người dùng gửi:

```http
POST /login/ott HTTP/1.1
Host: app.example.test
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=<session-cookie>

token=<unguessable-token-value>&_csrf=<csrf-token>
```

Các dấu `<...>` ở trên là placeholder, không phải token thật. Một POST thiếu CSRF hợp lệ có thể trả **403 trước khi filter OTT chạy**. Đừng kết luận đó là lỗi token bị hết hạn và đừng tắt CSRF để “sửa lỗi”.

## 4. Các thành phần bên trong Spring Security

### 4.1. GenerateOneTimeTokenFilter

Filter phát hiện POST request phát hành. Nó dùng `GenerateOneTimeTokenRequestResolver` (mặc định đọc `username`) tạo `GenerateOneTimeTokenRequest`, gọi `OneTimeTokenService.generate(...)`, rồi chuyển kết quả `OneTimeToken` cho `OneTimeTokenGenerationSuccessHandler`.

Framework **không tự biết địa chỉ email hay nhà cung cấp SMTP** của ứng dụng. Đăng ký OTT DSL mà thiếu cách giao token đáng tin thì chưa hoàn thiện magic link login.

### 4.2. OneTimeTokenGenerationSuccessHandler

Handler quyết định làm gì khi có token: tra cứu email **đã được xác minh, gắn với account**, xây link bằng public base URL tin cậy, gửi email/SMS, trả redirect hoặc trang thông báo trung lập. `RedirectOneTimeTokenGenerationSuccessHandler` có thể hỗ trợ chuyển trang sau khi gửi. Đây là nơi cần chống lộ raw token, spam, enumeration và giả mạo hostname.

### 4.3. OneTimeTokenService

Interface cung cấp hai phép xử lý cốt lõi:

```java
OneTimeToken generate(GenerateOneTimeTokenRequest request);
OneTimeToken consume(OneTimeTokenAuthenticationToken authenticationToken);
```

Hai dòng là **trích chữ ký API theo khái niệm**, muốn biên dịch cần đặt trong interface/class tương ứng và import type từ `org.springframework.security.authentication.ott`. `generate` tạo/lưu token và hạn dùng; `consume` cần **tìm, kiểm tra và vô hiệu hóa token một cách nguyên tử**. Nếu trả về token hợp lệ cho hai concurrent requests, cơ chế không còn “one-time”.

`InMemoryOneTimeTokenService` là implementation mặc định khi không khai báo service khác; phù hợp single JVM/demo. `JdbcOneTimeTokenService` dùng database cho nhiều instance, cần bản đã vá và test race. Với token store tự xây, cân nhắc hash token khi lưu, TTL cleanup và giới hạn số link đang chờ.

### 4.4. OneTimeTokenAuthenticationFilter và Provider

`OneTimeTokenAuthenticationFilter` đọc token của **POST /login/ott**, converter tạo authentication request; `OneTimeTokenAuthenticationProvider` tiêu thụ token và xác định user. Chỉ khi thành công, Spring tạo Authentication/SecurityContext và HTTP session theo session policy. OTT không tự cấp quyền admin; account lookup, disabled/locked state, roles, tenant và business authorization vẫn cần được áp dụng đúng chính sách, kiểm tra behavior theo phiên bản thực tế.

### 4.5. DefaultOneTimeTokenSubmitPageGeneratingFilter

Filter này tạo **GET /login/ott** để hiển thị form và điền sẵn token từ query. Bạn có thể thay bằng trang HTML riêng. Dù UI thế nào, hãy giữ **POST loginProcessingUrl**, form param `token`, CSRF field và kiểm tra thất bại khi token sai/hết hạn/replay.

## 5. Ví dụ Spring Boot 3.x và Java 17: magic link qua email

Ví dụ dùng **Servlet/Spring MVC**, Spring Security **6.5.10+** (đã vá lỗi JDBC OTT). Code chỉ chạy end-to-end khi đã cấu hình SMTP test, public hostname hợp lệ và mailbox kiểm thử; không có hệ thống SMTP nào tồn tại tại domain `example.test`.

### 5.1. Dependencies trong dự án Boot có plugin Gradle sẵn

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 5.2. application.yml

File `src/main/resources/application.yml`:

```yaml
app:
  public-base-url: https://app.example.test

spring:
  mail:
    host: smtp.example.test
    port: 587
    username: ${SMTP_USER}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
```

Cấu hình `app.public-base-url` từ nguồn tin cậy, **không lấy request Host/X-Forwarded-Host** từ browser để xây link. Nếu Host bị attacker điều khiển, magic link có thể đi tới domain giả và làm lộ token.

### 5.3. OttApplication.java

```java
package com.example.ott;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OttApplication {
    public static void main(String[] args) {
        SpringApplication.run(OttApplication.class, args);
    }
}
```

### 5.4. SecurityConfig.java

```java
package com.example.ott;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http, MagicLinkHandler delivery) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login", "/login/ott",
                                "/ott/generate", "/ott/sent")
                        .permitAll()
                        .anyRequest().authenticated())
                // KHÔNG tắt CSRF; POST generate và POST login đều cần CSRF.
                .oneTimeTokenLogin(ott -> ott
                        .tokenGenerationSuccessHandler(delivery))
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        // Demo OTT-only, không bật formLogin / httpBasic.
        // Production: account DB thật và password encoder nếu cho login password.
        UserDetails alice = User.withUsername("alice")
                .password("{noop}not-used-in-ott")
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }
}
```

`permitAll()` ở các route login chỉ cho phép truy cập trước authentication, **không vô hiệu hóa security filters hoặc CSRF**. Password dạng `{noop}` trong demo **không dùng để đăng nhập** do không bật form login/basic; đừng dùng cách lưu mật khẩu này cho tài khoản production. Khi muốn kết hợp OTT với form login, dùng `PasswordEncoder` mạnh và thêm `formLogin(Customizer.withDefaults())` một cách chủ đích.

### 5.5. MagicLinkHandler.java

```java
package com.example.ott;

import java.io.IOException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.web.authentication.ott.OneTimeTokenGenerationSuccessHandler;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

@Component
public final class MagicLinkHandler
        implements OneTimeTokenGenerationSuccessHandler {

    private final MailSender sender;
    private final String baseUrl;

    public MagicLinkHandler(MailSender sender,
            @Value("${app.public-base-url}") String baseUrl) {
        this.sender = sender;
        this.baseUrl = baseUrl;
    }

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       OneTimeToken token) throws IOException {
        // Demo chỉ có alice; production tra email đã xác minh từ account DB.
        String recipient = "alice".equals(token.getUsername())
                ? "alice@example.test" : null;

        if (recipient != null) {
            String link = UriComponentsBuilder.fromUriString(baseUrl)
                    .path("/login/ott")
                    .queryParam("token", token.getTokenValue())
                    .build().encode().toUriString();

            SimpleMailMessage mail = new SimpleMailMessage();
            mail.setTo(recipient);
            mail.setSubject("Your one-time sign-in link");
            mail.setText("Use this link to sign in: " + link);
            this.sender.send(mail);
        }
        response.sendRedirect(request.getContextPath() + "/ott/sent");
    }
}
```

Email `alice@example.test` là placeholder không nhận thư. Thay bằng inbox test khi chạy. Nếu username lạ, ví dụ không gửi và vẫn chuyển về trang chung. Sản phẩm thực cần lookup email verified, rate limit, chống enumerate account, queue retry và xử lý lỗi SMTP không làm lộ việc account có tồn tại hay không. Không dùng `recipientEmail` do người xin token tự nhập làm địa chỉ giao link cho một tài khoản khác. Lỗi SMTP có thể ném exception; snippet chưa triển khai error masking/retry nên chỉ dùng làm bài học tích hợp.

### 5.6. PageController.java

```java
package com.example.ott;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PageController {
    @GetMapping("/")
    public String index() {
        return "OTT demo";
    }

    @GetMapping("/ott/sent")
    public String sent() {
        return "If the account is eligible, check its email.";
    }

    @GetMapping("/private")
    public String privatePage(Principal principal) {
        return "Welcome " + principal.getName();
    }
}
```

### 5.7. Chạy

Trong project có Gradle wrapper:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

Mở `/login`, gửi form POST `/ott/generate` với `username=alice` và CSRF. Hệ thống phải giao magic link tới email đúng; mở `GET /login/ott?token=T` rồi submit **POST /login/ott** với token+CSRF. Sau success, `GET /private` với session cookie trả `Welcome alice`. Browser khác không có cookie vẫn chưa logged in. Không gửi raw token qua shell history hoặc log.

## 6. Tùy chỉnh endpoint và thời hạn

| Mục | Default | Cách đổi |
| --- | --- | --- |
| Endpoint sinh | `POST /ott/generate` | DSL cho generating URL |
| Endpoint xử lý token | `POST /login/ott` | `loginProcessingUrl(String)` |
| Trang mặc định nhận token | `GET /login/ott` | DSL cho default submit-page URL; `showDefaultSubmitPage(false)` để tự làm UI |
| Giao token | Custom application | `tokenGenerationSuccessHandler(...)` |
| Lưu token | `InMemoryOneTimeTokenService` mặc định | `tokenService(...)` hoặc bean `OneTimeTokenService` |
| Parse username và expiresIn | Request resolver mặc định | `generateRequestResolver(...)` / custom resolver |

**Tên method khác nhau giữa tài liệu và artifact version:** một số Javadoc Spring Security dùng `tokenGeneratingUrl(...)` và `defaultSubmitPageUrl(...)`, trong khi ví dụ của một số nhánh tài liệu dùng `generateTokenUrl(...)` và `submitPageUrl(...)`. Phải kiểm tra **Javadoc của Spring Security version dự án thực sự dùng** trước khi copy setter. Mẫu ở mục 5 giữ default URL và API success handler ổn định.

Nếu đổi URL, cập nhật **form action phát hành**, **magic link GET**, **form action POST login**, route permitAll và reverse proxy. GET page và POST processor không nhất thiết chung URL. Nếu dùng `showDefaultSubmitPage(false)`, bạn phải tự render GET page/form, nhưng filter POST vẫn cần cấu hình.

Ví dụ resolver để chọn TTL 10 phút (đoạn bên trong Java configuration, không phải file độc lập):

```java
var resolver = new DefaultGenerateOneTimeTokenRequestResolver();
resolver.setExpiresIn(java.time.Duration.ofMinutes(10));
// ott.generateRequestResolver(resolver) ở phiên bản có method này.
```

Import từ `org.springframework.security.web.authentication.ott.DefaultGenerateOneTimeTokenRequestResolver`. Thời hạn mặc định khoảng 5 phút trong các bản 6.5, nhưng cần xác nhận trong cấu hình của phiên bản đang chạy. TTL dài hơn tăng cửa sổ lộ link, nên cân bằng với độ trễ email.

## 7. Lưu token, concurrency và bản vá CVE-2026-22751

### 7.1. In-memory cho demo/single instance

Nếu không có custom bean, `InMemoryOneTimeTokenService` giữ token ở bộ nhớ JVM, thuận tiện demo và test. Restart làm mất pending token; nhiều pod không chia sẻ state. Request tạo ở instance A và POST đăng nhập ở instance B có thể thất bại nếu không có shared store.

### 7.2. JDBC cho hệ thống nhiều node

`JdbcOneTimeTokenService` lưu OTT trong database cho nhiều instance, nhưng việc **consume phải atomic**. Một triển khai sai có thể làm hai request đồng thời cùng thấy token chưa dùng và mở hai session. Spring đã công bố **CVE-2026-22751** ngày **21/04/2026** liên quan đúng tới `JdbcOneTimeTokenService` được cấu hình tường minh:

- Ảnh hưởng: **Spring Security 6.4.0–6.4.15**, **6.5.0–6.5.9**, **7.0.0–7.0.4**.
- Bản sửa: **6.5.10** và **7.0.5** ở nhánh OSS; **6.4.16** qua Enterprise Support.
- Default `InMemoryOneTimeTokenService` **không bị ảnh hưởng bởi chính CVE cụ thể này**.

Nếu ứng dụng đang dùng `JdbcOneTimeTokenService`, hãy xác nhận runtime dependency BOM đã chọn phiên bản vá và kiểm thử **hai POST cùng token trên hai phiên khác nhau**. Với custom store, không làm kiểu SELECT rồi DELETE tách biệt mà không có locking/atomic update:

```sql
-- Minh họa logic dễ gặp race, KHÔNG an toàn nếu không có transaction phù hợp:
SELECT username, expires_at FROM ott_tokens WHERE token_hash = ?;
-- Cùng lúc, hai request có thể đều thấy token hợp lệ.
DELETE FROM ott_tokens WHERE token_hash = ?;
```

Dùng chiến lược atomic update/delete + kiểm tra affected rows trong một transaction ở DB hỗ trợ; cú pháp SQL chính xác phải theo DB và schema thật. Không tuyên bố “đã xóa một bản ghi” là đủ nếu request khác đã đọc trước khi xóa.

### 7.3. Token phải kín và ngắn hạn

Cần entropy cao, TTL ngắn, single-use, hash token at rest (nếu thiết kế custom), cleanup token hết hạn, quota pending tokens theo tài khoản, hủy token khi đổi email/khóa account theo chính sách. Không ghi raw token vào logs/metrics/tracing, hoặc gửi lại token đã tiêu thụ.

## 8. Java 17 thuần: minh họa atomic single-use

File `SingleUseTokenDemo.java` dưới đây chạy độc lập bằng JDK 17+. Nó giúp hiểu vì sao thao tác remove atomic quan trọng, nhưng **không** triển khai Spring `OneTimeTokenService`, không gửi mail và không chứng minh một database distributed có đúng semantics.

```java
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class SingleUseTokenDemo {
    record Entry(String username, Instant expiresAt) {}

    private static final SecureRandom RANDOM = new SecureRandom();
    private final ConcurrentHashMap<String, Entry> tokens =
            new ConcurrentHashMap<>();

    String generate(String username, Instant now) {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        String value = Base64.getUrlEncoder()
                .withoutPadding().encodeToString(bytes);
        tokens.put(value, new Entry(username,
                now.plus(Duration.ofMinutes(5))));
        return value;
    }

    boolean consume(String value, Instant now) {
        Entry entry = tokens.remove(value); // atomic trong một JVM
        return entry != null && now.isBefore(entry.expiresAt());
    }

    public static void main(String[] args) throws InterruptedException {
        SingleUseTokenDemo demo = new SingleUseTokenDemo();
        Instant now = Instant.parse("2026-11-06T00:00:00Z");

        String token = demo.generate("alice", now);
        System.out.println("first=" + demo.consume(token, now));
        System.out.println("replay=" + demo.consume(token, now));

        String expired = demo.generate("alice", now);
        System.out.println("expired=" +
                demo.consume(expired, now.plus(Duration.ofMinutes(6))));

        String shared = demo.generate("alice", now);
        CountDownLatch gate = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger accepted = new AtomicInteger();

        Runnable attempt = () -> {
            try {
                gate.await();
                if (demo.consume(shared, now)) {
                    accepted.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                done.countDown();
            }
        };
        new Thread(attempt).start();
        new Thread(attempt).start();
        gate.countDown();
        done.await();

        System.out.println("concurrentSuccess=" + accepted.get());
    }
}
```

Chạy:

```bash
javac SingleUseTokenDemo.java
java SingleUseTokenDemo
```

Stdout xác định:

```text
first=true
replay=false
expired=false
concurrentSuccess=1
```

Khi `remove` khỏi ConcurrentHashMap, chỉ một luồng lấy được entry. Với database, phải dùng locking/atomic consume riêng; ví dụ này cố tình không đưa logic HTTP/JWT/Spring vào để dễ thấy điều kiện one-time.

## 9. Những điểm bảo mật không được bỏ qua

**CSRF:** Hai POST ở OTT flow cần CSRF đúng trong browser session. `.permitAll()` không bỏ qua CSRF. 403 khi thiếu `_csrf` khác với token hết hạn. Khi viết custom login form, render/gửi token CSRF đúng cách.

**Magic link là bearer secret:** người cầm link có thể đăng nhập trước. Query token có thể lọt vào browser history, logs, reverse proxy, Referer/analytics và third-party script. Dùng HTTPS, chính sách `Referrer-Policy: no-referrer`, không đưa tracking JS vào trang submit chứa token, cân nhắc xóa query khỏi URL sau khi form nhận token. Không đổi sang “GET trực tiếp xác thực” vì scanner prefetch.

**Địa chỉ email đáng tin:** không gửi magic link đến địa chỉ `email` do người xin phát hành tự gõ cho username khác. Tra email verified ở account DB; không để attacker dùng username của nạn nhân nhưng nhận link về email attacker. Đừng xây URL theo Host chưa xác minh.

**Chống spam/enumeration:** endpoint phát hành công khai dễ bị spam. Rate limit theo IP/user, quota, thông báo trung lập, delay/response nhất quán, giám sát abuse và bảo vệ SMTP queue. Nếu account không tồn tại/đã khóa, không trả lỗi khác biệt rõ ràng làm lộ thông tin; account state cũng phải được kiểm khi login.

**Session sau OTT:** token đã tiêu thụ không dùng lại được, nhưng HTTP session tạo bởi login có thể tiếp tục theo cookie. Bảo vệ session fixation, Secure/HttpOnly/SameSite, logout, timeout, MFA/step-up cho thao tác rủi ro cao. Không xem sở hữu email là đủ cho quyền admin.

**Concurrency:** một token chỉ tạo tối đa một lần login, dù hai requests cùng lúc ở hai node. Test trên JDBC thật quan trọng hơn một test chỉ mock `Authentication`.

## 10. Test matrix cho phát hành và tiếp nhận

| Ca | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Trang request | `GET /login` | Có form OTT hoặc custom login page |
| Generate sai method | `GET /ott/generate?username=alice` | Không phát token |
| Generate thiếu CSRF | POST username mà không có `_csrf` | 403, không email |
| Generate hợp lệ | POST username + CSRF | Tạo token, handler gửi đúng verified email |
| User không tồn tại | POST username lạ | Không gửi token tới email của attacker, response trung lập |
| Click link | `GET /login/ott?token=T` | Chỉ hiển thị form, chưa login, chưa consume |
| Login thiếu CSRF | POST token T, không CSRF | 403; không authenticated |
| Login hợp lệ | POST T+CSRF trước expiry | Tiêu thụ T, đúng user authenticated |
| Replay | POST T lần thứ hai ở browser khác | Từ chối |
| Expired | POST khi quá TTL | Từ chối |
| Concurrent requests | Hai POST cùng token từ hai session/DB node | Chính xác một thành công |
| Locked account | Token đúng nhưng account disabled | Từ chối theo account policy |
| Multi-instance | Generate pod A, consume pod B | Pass nếu token store chia sẻ đúng |
| Host injection | Generate với Host giả | Link vẫn theo public base URL đã cấu hình |
| Mail scanner | Prefetch GET magic link | Token chưa bị tiêu thụ |

Dùng `spring-security-test` để thử CSRF trong `MockMvc`:

```java
// Đoạn nằm trong một @SpringBootTest + @AutoConfigureMockMvc
// đã có MockMvc mvc và static imports post, status, csrf:
mvc.perform(post("/ott/generate")
        .param("username", "alice"))
   .andExpect(status().isForbidden());

// Khi cấu hình mock MailSender:
// mvc.perform(post("/ott/generate")
//        .with(csrf())
//        .param("username", "alice"))
//    .andExpect(status().is3xxRedirection());
```

Đây là **fragment**, không phải test class runnable độc lập. Kiểm chứng OTT thật phải assert token được gửi cho account đúng, POST consumption tạo session, replay thất bại, cùng token concurrent chỉ một login. Test dùng `@WithMockUser` tự tạo principal trước **không chứng minh OTT filter hoạt động**.

## 11. Troubleshooting nhanh

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| POST generate 403 | CSRF thiếu/cookie mismatch | Xem CSRF filter, form hidden input và session |
| GET generate không sinh token | Chỉ POST được filter xử lý | Dùng POST /ott/generate |
| POST thành công nhưng không email | Chưa có success handler/SMTP, mapping email sai | Kiểm tra bean, queue, verified email |
| Link GET mở nhưng chưa login | Chỉ là submit page | Người dùng cần POST /login/ott |
| POST login sai token | Token hết hạn/đã dùng/store mất/restart JVM | Xem store + TTL + instance |
| Token reuse ở concurrent requests | JDBC chưa vá hoặc store tự xây không atomic | Upgrade, test two concurrent POST |
| Multi-pod lúc được lúc không | InMemory store không chia sẻ | JDBC/shared store |
| Account khóa vẫn login | Chưa enforce account state | Test disabled/locked theo đúng provider version |
| Link sai domain | Dùng Host/X-Forwarded-Host chưa tin | Cấu hình public base URL cố định |
| Session sau login mất | Cookie Secure/SameSite/domain/cluster sai | Network Set-Cookie và persistence |
| Email scanner tự consume | GET handler custom đang login | Chỉ GET form, POST consume |
| Log chứa token | Access log/analytics/referrer lưu query | Mask token, Referrer-Policy, remove scripts |

## 12. Checklist kết luận

- **POST /ott/generate** phát hành, **GET /login/ott** chỉ hiển thị form, **POST /login/ott** mới tiếp nhận/tiêu thụ và đăng nhập.
- Đã cấu hình `oneTimeTokenLogin(...)` và `OneTimeTokenGenerationSuccessHandler` gửi token tới địa chỉ verified từ DB, không trả token cho caller.
- Có CSRF, HTTPS, public base URL đáng tin, rate limit, chống enumeration và giữ token ngoài log/referrer.
- TTL ngắn, token ngẫu nhiên entropy cao, **atomic single-use**, test replay và concurrent requests.
- Store phù hợp topology: InMemory chỉ cho single JVM/demo; JDBC/shared store cần bản vá **CVE-2026-22751** và thử nghiệm nhiều instance.
- Đăng nhập thành công phải gắn đúng user/authorities và session; account locked/disabled và quyền nghiệp vụ được kiểm tra riêng.
- Khi đổi URL DSL, đối chiếu Javadoc đúng phiên bản, cập nhật cả magic link GET và form POST.

**Tóm tắt ngắn:** `oneTimeTokenLogin()` tích hợp cơ chế tạo và tiêu thụ mã dùng một lần, nhưng ứng dụng phải xây **đường gửi token tới người sở hữu tài khoản**. Mở magic link bằng GET không phải bước xác thực; POST hợp lệ mới có thể đăng nhập.

### Nguồn học chính thức

- [Spring Security 6.5 Reference — One-Time Token Login (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html)
- [Spring Security Reference — One-Time Token Login](https://docs.spring.io/spring-security/reference/servlet/authentication/onetimetoken.html)
- [Spring Security 6.5 Javadoc — OneTimeTokenLoginConfigurer](https://docs.spring.io/spring-security/site/docs/6.5.5/api/org/springframework/security/config/annotation/web/configurers/ott/OneTimeTokenLoginConfigurer.html)
- [OneTimeTokenService Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ott/OneTimeTokenService.html)
- [Spring Security Advisory — CVE-2026-22751, JDBC concurrent consumption](https://spring.io/security/cve-2026-22751/)
