# OneTimeTokenGenerationSuccessHandler và phần gửi token do ứng dụng đảm nhiệm

## 1. Khái niệm và ranh giới trách nhiệm

Spring Security Servlet 6.4+ cung cấp đăng nhập bằng **One-Time Token (OTT)** thông qua `HttpSecurity.oneTimeTokenLogin(...)`. Người dùng yêu cầu một token dùng một lần, nhận nó qua email/SMS hoặc kênh khác, rồi nộp token để đăng nhập. **Spring Security hỗ trợ sinh và tiêu thụ OTT, nhưng không tự gửi token đến người dùng** vì framework không biết hệ thống email, nhà cung cấp SMS hay địa chỉ liên hệ đã được xác minh của ứng dụng.

Đó là vai trò của `OneTimeTokenGenerationSuccessHandler`: nhận token sau khi sinh thành công, giao nó qua kênh tin cậy do ứng dụng chọn, rồi trả response phù hợp. Handler này **không phải `AuthenticationSuccessHandler`**, và generation success **không có nghĩa user đã đăng nhập**.

Bốn phần độc lập:

1. `GenerateOneTimeTokenFilter` nhận `POST /ott/generate` và tạo `GenerateOneTimeTokenRequest`.
2. `OneTimeTokenService.generate(...)` sinh/lưu `OneTimeToken` gắn username, giá trị bí mật và hạn sử dụng.
3. `OneTimeTokenGenerationSuccessHandler.handle(...)` xử lý token mới: tra cứu verified email, gửi magic link, redirect tới trang thông báo chung.
4. `OneTimeTokenAuthenticationFilter` xử lý khi user nộp token; `OneTimeTokenService.consume(...)` kiểm tra tồn tại, expiry, single-use; chỉ sau đó mới tạo `Authentication` và lưu SecurityContext theo cấu hình.

```text
Browser POST /ott/generate (username + CSRF)
  -> GenerateOneTimeTokenFilter
  -> OneTimeTokenService.generate(...)
  -> OneTimeTokenGenerationSuccessHandler
       -> verified contact lookup -> email/SMS/queue
       -> redirect /ott/sent (chưa đăng nhập)

User nhận link -> GET /login/ott?token=<secret>
  -> trang mặc định hiển thị form có token điền sẵn
  -> POST /login/ott (token + CSRF)
  -> OneTimeTokenAuthenticationFilter
  -> OneTimeTokenService.consume(...)
       -> không hợp lệ / đã dùng / quá hạn: từ chối
       -> hợp lệ: Authentication thành công
```

**GET magic link không tự tiêu thụ token** khi dùng trang nộp mặc định. POST đăng nhập mới xử lý credential, tránh một số tình huống email scanners/link-preview tự click GET rồi đốt mất token.

### OTT khác OTP/TOTP

| Phương thức | Ai tạo? | Ai gửi? | Khi dùng |
| --- | --- | --- | --- |
| Spring Security OTT | Server tạo theo yêu cầu | Ứng dụng gửi từng token | Đăng nhập bằng magic link/mã dùng một lần |
| TOTP/HOTP | Authenticator/thiết bị tính từ shared secret | Không gửi từng mã; cần provision secret ban đầu | Xác thực bằng mã theo thời gian/counter |
| OAuth2 access token | Authorization server | Qua giao thức OAuth2 | Gọi resource API, không phải token đăng nhập OTT |
| CSRF token | Ứng dụng/framework | Đưa qua form/cookie theo cấu hình | Chống giả mạo request, không phải OTT credential |

OTT là credential bí mật. Ai có secret chưa dùng và còn hạn có thể thử đăng nhập: **không log token, không đưa token vào response sinh token và không gửi tới email do client tự khai thay vì verified contact**.

## 2. Interface và hai loại success handler

Interface Servlet:

```java
import org.springframework.security.web.authentication.ott.OneTimeTokenGenerationSuccessHandler;
import org.springframework.security.authentication.ott.OneTimeToken;
```

Chữ ký chính (đặt trong class implements interface):

```java
@Override
public void handle(
        HttpServletRequest request,
        HttpServletResponse response,
        OneTimeToken oneTimeToken)
        throws IOException, ServletException {
    // Gửi/ủy quyền gửi token, sau đó phản hồi HTTP.
}
```

Các tham số:

- `request` / `response` thuộc Jakarta Servlet, dùng để kết thúc request generation.
- `oneTimeToken.getUsername()`: username đã yêu cầu OTT. **Tra cứu contact verified từ database** bằng username, không tin giá trị email/số điện thoại do người gửi form chọn tùy ý.
- `oneTimeToken.getTokenValue()`: raw secret để tạo magic link hoặc gửi SMS, phải giữ kín.
- `oneTimeToken.getExpiresAt()`: thời điểm hết hạn `Instant`, có thể đưa vào email. Thay đổi câu chữ email **không thay đổi expiry của token**.

`RedirectOneTimeTokenGenerationSuccessHandler` chỉ làm redirect:

```java
OneTimeTokenGenerationSuccessHandler redirect =
    new RedirectOneTimeTokenGenerationSuccessHandler("/ott/sent");
redirect.handle(request, response, oneTimeToken);
```

Đây là snippet trong ngữ cảnh handler, không phải chương trình Java độc lập. Nó không gửi email, không consume token và không tạo Authentication. Thông thường gửi xong hoặc enqueue bền vững, ứng dụng gọi redirect handler để trả trang “Nếu có tài khoản hợp lệ, hãy kiểm tra email”.

| Thành phần | Khi chạy | Trách nhiệm |
| --- | --- | --- |
| `OneTimeTokenGenerationSuccessHandler` | Sau generation | Giao token và response |
| `RedirectOneTimeTokenGenerationSuccessHandler` | Khi được gọi | Redirect, không gửi secret |
| `OneTimeTokenService` | Khi generate/consume | Sinh và kiểm tra token, single-use |
| `AuthenticationSuccessHandler` | Sau login thành công | Điều hướng sau khi đã xác thực |

**Lỗi phân tầng thường gặp:** triển khai `AuthenticationSuccessHandler` để gửi magic link. Handler đó chạy quá muộn; ứng dụng phải dùng `tokenGenerationSuccessHandler(...)` hoặc đăng ký một bean `OneTimeTokenGenerationSuccessHandler`.

## 3. Các URL và TTL mặc định trong Spring Security Servlet 6.5

- `POST /ott/generate`: generate filter. Request form cần CSRF token khi CSRF được bật.
- `GET /login/ott`: trang nộp token mặc định, nhận query `token` và điền form.
- `POST /login/ott`: xác thực OTT, cần CSRF phù hợp.
- `OneTimeTokenService` mặc định có thể là `InMemoryOneTimeTokenService`; production nhiều node nên cân nhắc `JdbcOneTimeTokenService` hoặc store dùng chung đáng tin.
- Request generation trong tài liệu 6.5 thường mặc định hết hạn sau **5 phút**, có thể tùy chỉnh bằng `GenerateOneTimeTokenRequestResolver` / `OneTimeTokenService` theo policy.

Các tên option DSL có thể thay đổi giữa dòng phiên bản 6.5/7.x; bài dùng phương thức ổn định `tokenGenerationSuccessHandler(...)`. Luôn kiểm tra API của đúng phiên bản dependency thực dùng.

## 4. Các nguyên tắc an toàn trước khi viết code

**Verified contact:** Nếu attacker yêu cầu OTT cho Alice rồi tự đặt `recipient=attacker@example.test`, việc gửi theo input đó có thể biến OTT thành chiếm tài khoản. Chỉ lấy contact đã gắn với Alice và **được xác minh trước đó**.

**Canonical URL:** Đừng dựng magic link bằng raw header `Host`/`X-Forwarded-Host` từ request. Kẻ tấn công có thể thực hiện **Host header poisoning**, khiến email gửi cho Alice có link trỏ về host do attacker điều khiển. Dùng URL HTTPS cố định từ cấu hình tin cậy hoặc allowlist tenant-to-origin.

**Chống user enumeration:** Browser nên thấy cùng thông báo chung dù username có tồn tại hay không. Cần tính cả side channel về thời gian gửi email (email thật mất nhiều thời gian hơn account không có), rate limit và monitoring, không chỉ status/body.

**Token trong URL:** Magic link với query `token=...` có thể bị lộ qua reverse proxy log, browser history, referrer hay analytics. Bật HTTPS, `Referrer-Policy: no-referrer`, tắt third-party assets trên trang nhận token khi có thể, redaction log và TTL ngắn.

**Gửi bất đồng bộ:** Nếu dùng queue/outbox để tránh chờ SMTP, token vẫn là secret trong job. Bảo vệ bằng ACL/mã hóa/TTL, không lưu raw token vào logs hoặc dead-letter queue không kiểm soát. Response “đã nhận yêu cầu gửi” không đồng nghĩa email vào inbox hay user đã đăng nhập.

## 5. Java 17+ / Spring Boot Servlet: handler gửi magic link

Ví dụ dùng Spring Boot 3.x, Spring Security 6.5.x và SMTP test local (ví dụ Mailpit cổng 1025). Không dùng địa chỉ test để gửi thư thật. Các dependency trong dự án Spring Boot có Gradle plugin và BOM tương thích:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

`src/main/resources/application.yml`:

```yaml
spring:
  mail:
    host: localhost
    port: 1025

app:
  security:
    public-base-url: http://localhost:8080
```

Production phải chuyển sang HTTPS origin và SMTP có TLS/credentials/monitoring. Đặt toàn bộ code sau trong `src/main/java/example/OttApplication.java`:

```java
package example;

import java.io.IOException;
import java.util.Map;
import java.util.Optional;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.ott.OneTimeTokenGenerationSuccessHandler;
import org.springframework.security.web.authentication.ott.RedirectOneTimeTokenGenerationSuccessHandler;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

@SpringBootApplication
public class OttApplication {

    public static void main(String[] args) {
        SpringApplication.run(OttApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        // Demo account; chỉ bật OTT, không bật password form login.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}not-used-for-ott")
                .roles("USER").build()
        );
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, MagicLinkHandler handler)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/login", "/login/ott", "/ott/generate",
                    "/ott/sent", "/error").permitAll()
                .anyRequest().authenticated())
            .oneTimeTokenLogin(ott ->
                ott.tokenGenerationSuccessHandler(handler))
            .build();
    }
}

// Demo: source of contacts already verified.
// Production: replace with a user directory and emailVerified check.
@Component
class VerifiedEmailDirectory {
    private final Map<String, String> contacts =
        Map.of("alice", "alice@example.test");

    Optional<String> verifiedEmail(String username) {
        return Optional.ofNullable(contacts.get(username));
    }
}

@Component
class MagicLinkHandler implements OneTimeTokenGenerationSuccessHandler {
    private final MailSender mail;
    private final VerifiedEmailDirectory directory;
    private final String publicBaseUrl;

    private final OneTimeTokenGenerationSuccessHandler redirect =
        new RedirectOneTimeTokenGenerationSuccessHandler("/ott/sent");

    MagicLinkHandler(
            MailSender mail,
            VerifiedEmailDirectory directory,
            @Value("${app.security.public-base-url}") String publicBaseUrl) {
        this.mail = mail;
        this.directory = directory;
        this.publicBaseUrl = publicBaseUrl;
    }

    @Override
    public void handle(
            HttpServletRequest req,
            HttpServletResponse res,
            OneTimeToken token) throws IOException, ServletException {

        Optional<String> email =
            directory.verifiedEmail(token.getUsername());

        if (email.isPresent()) {
            String link = UriComponentsBuilder
                .fromUriString(publicBaseUrl)
                .path("/login/ott")
                .queryParam("token", token.getTokenValue())
                .encode().build().toUriString();

            SimpleMailMessage msg = new SimpleMailMessage();
            msg.setFrom("no-reply@shop.example.test");
            msg.setTo(email.get());
            msg.setSubject("Liên kết đăng nhập một lần");
            msg.setText("Đăng nhập tại:\n" + link
                + "\nHết hạn: " + token.getExpiresAt()
                + "\nNếu không yêu cầu, hãy bỏ qua email.");
            mail.send(msg);
        }

        // Cả username đã biết và chưa biết đều có cùng redirect.
        redirect.handle(req, res, token);
    }
}

@RestController
class OttPageController {
    @GetMapping("/ott/sent")
    ResponseEntity<String> sent() {
        return ResponseEntity.ok(
            "Nếu tài khoản hợp lệ, hãy kiểm tra email đã xác minh."
        );
    }

    @GetMapping("/private")
    ResponseEntity<String> privatePage() {
        return ResponseEntity.ok("Bạn đã đăng nhập.");
    }
}
```

Giải thích cụ thể:

1. `.oneTimeTokenLogin(...)` kích hoạt generation/authentication flow. `tokenGenerationSuccessHandler(handler)` đưa token mới sang ứng dụng để giao; không yêu cầu tự cấu hình `OneTimeTokenService` nếu dùng default.
2. `VerifiedEmailDirectory` là map test, **không** phải logic xác minh email production. Không tin địa chỉ mà request tự nhập. Username chỉ để tra cứu bản ghi và verified contact trên server.
3. `MailSender` được Spring Boot tạo khi mail starter và SMTP phù hợp; `SimpleMailMessage` gửi nội dung text. Sender domain `example.test` dành cho demo, không dùng production.
4. Handler lấy `getTokenValue()`, tạo URL từ `publicBaseUrl` tin cậy. Không đọc host do browser cung cấp để tạo link.
5. Khi không có email verified, không gửi nhưng trả cùng redirect. Đây là điều kiện cần, chưa đủ để chống timing enumeration: sản phẩm cần rate limit/queue/monitoring.
6. `RedirectOneTimeTokenGenerationSuccessHandler` trả response sau generation. Việc redirect không xác thực user, không consume token và không log token.
7. CSRF **không** bị disable; form gửi `POST /ott/generate` và `POST /login/ott` phải có CSRF token đúng.

Ví dụ request (không phải credential thật):

```http
POST /ott/generate HTTP/1.1
Host: localhost:8080
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=<session-id>

username=alice&_csrf=<valid-csrf-token>
```

Nếu tạo/gửi thành công, response thường **302** tới `/ott/sent`; secret chỉ đi qua mail. Email mẫu có link dạng `http://localhost:8080/login/ott?token=ONE-TIME-SECRET`. Người dùng mở GET form, rồi submit POST token với CSRF; chỉ lúc đó mới có đăng nhập khi token hợp lệ.

## 6. Kiểm thử handler bằng JUnit và Mockito

Các test sau chỉ dùng mock mail và servlet; không gọi SMTP thật. Đặt trong `src/test/java/example/MagicLinkHandlerTest.java`.

```java
package example;

import java.time.Instant;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.ott.DefaultOneTimeToken;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class MagicLinkHandlerTest {
    @Test
    void sendsToVerifiedEmailAndNeverReturnsToken() throws Exception {
        MailSender mail = mock(MailSender.class);
        VerifiedEmailDirectory directory =
            mock(VerifiedEmailDirectory.class);

        when(directory.verifiedEmail("alice"))
            .thenReturn(Optional.of("alice@example.test"));

        var handler = new MagicLinkHandler(
            mail, directory, "https://login.example.test");
        var req = new MockHttpServletRequest("POST", "/ott/generate");
        var res = new MockHttpServletResponse();

        handler.handle(req, res, new DefaultOneTimeToken(
            "secret-abc", "alice",
            Instant.parse("2030-01-01T12:05:00Z")));

        ArgumentCaptor<SimpleMailMessage> captured =
            ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(mail).send(captured.capture());

        SimpleMailMessage sent = captured.getValue();
        assertNotNull(sent.getText());
        assertEquals("alice@example.test", sent.getTo()[0]);
        assertTrue(sent.getText().contains(
            "https://login.example.test/login/ott?token=secret-abc"));

        assertEquals(302, res.getStatus());
        assertEquals("/ott/sent", res.getRedirectedUrl());
        assertFalse(res.getContentAsString().contains("secret-abc"));
    }

    @Test
    void unknownUserReceivesSameRedirectButNoMail()
            throws Exception {
        MailSender mail = mock(MailSender.class);
        VerifiedEmailDirectory directory =
            mock(VerifiedEmailDirectory.class);

        when(directory.verifiedEmail("unknown"))
            .thenReturn(Optional.empty());

        var handler = new MagicLinkHandler(
            mail, directory, "https://login.example.test");
        var res = new MockHttpServletResponse();

        handler.handle(
            new MockHttpServletRequest("POST", "/ott/generate"),
            res,
            new DefaultOneTimeToken(
                "secret-other", "unknown",
                Instant.parse("2030-01-01T12:05:00Z")));

        verifyNoInteractions(mail);
        assertEquals(302, res.getStatus());
        assertEquals("/ott/sent", res.getRedirectedUrl());
        assertFalse(res.getContentAsString().contains("secret-other"));
    }
}
```

Chạy test trong module Spring Boot có Gradle wrapper:

```bash
./gradlew test --tests "example.MagicLinkHandlerTest"
```

Trên Windows: `.\gradlew.bat test --tests "example.MagicLinkHandlerTest"`.

Nếu test pass, ta xác nhận handler gọi mail sender giả với link đúng, không trả secret trong HTTP response và không gửi mail cho username không tìm thấy. Test **chưa chứng minh** email thực đến inbox, user đang sở hữu mailbox, hoặc token được xác thực thành công.

### Test single-use riêng cho service

`OneTimeTokenService` không phải delivery handler. Một test riêng:

```java
package example;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.ott.GenerateOneTimeTokenRequest;
import org.springframework.security.authentication.ott.InMemoryOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.authentication.ott.OneTimeTokenAuthenticationToken;
import org.springframework.security.authentication.ott.OneTimeTokenService;
import static org.junit.jupiter.api.Assertions.*;

class OneTimeTokenConsumptionTest {
    @Test
    void consumesExactlyOnce() {
        OneTimeTokenService service = new InMemoryOneTimeTokenService();
        OneTimeToken token = service.generate(
            new GenerateOneTimeTokenRequest(
                "alice", Duration.ofMinutes(5)));

        var credential = new OneTimeTokenAuthenticationToken(
            token.getTokenValue());

        OneTimeToken first = service.consume(credential);
        OneTimeToken second = service.consume(credential);

        assertNotNull(first);
        assertEquals("alice", first.getUsername());
        assertNull(second);
    }
}
```

Chạy `./gradlew test --tests "example.OneTimeTokenConsumptionTest"`. Không có stdout nghiệp vụ cố định trong các test. In-memory test không chứng minh atomic consume khi nhiều node; muốn khẳng định production phải chạy integration test với JDBC/store thật.

## 7. Mất email, hết hạn, multi-node và quyền tài khoản

**Gửi lỗi:** handler ở ví dụ dùng `mail.send(...)` đồng bộ. Khi SMTP ném exception, OTT đã có thể được sinh trước đó, nhưng user chưa nhận email. Trong production có thể đưa job vào queue/outbox bền vững trước khi trả trang thông báo chung. Job có raw token phải được bảo vệ như credential: mã hóa, giới hạn người đọc, TTL ngắn, không đưa token vào log/dead-letter queue vô kiểm soát. Có chính sách retry giới hạn và xử lý email gửi trùng/đến chậm.

**Hết hạn:** `OneTimeToken.getExpiresAt()` là hạn do service quyết định. Thư tới sau khi token hết hạn phải bị từ chối; không “gia hạn” bằng cách sửa text email. Cho phép xin token mới theo rate limit.

**Replay:** consume thành công lần đầu phải khiến token không dùng tiếp; với store phân tán, consume phải atomic để hai request song song không cùng được xác thực.

**Multi-node:** `InMemoryOneTimeTokenService` chỉ hữu ích cho dev/test một JVM. Node A tạo token và node B nhận submit có thể không thấy token, hoặc restart mất state. Dùng `JdbcOneTimeTokenService` hay store chia sẻ được thiết kế phù hợp.

**Tài khoản bị khóa:** token chưa sử dụng không đủ chứng minh user được phép đăng nhập nếu tài khoản vừa disabled/locked/expired. Cần kiểm tra account policy trong quá trình authentication; xác nhận behavior của `OneTimeTokenAuthenticationProvider` theo phiên bản và cấu hình checker cần thiết.

**Lộ query token:** magic link có secret trong URL, dễ bị ghi trong browser/proxy analytics. HTTPS, no-referrer, hạn chế third-party assets, redaction query và ngăn link-preview tự tiêu thụ token là biện pháp thiết yếu.

### Các test tích hợp cần có

| Tình huống | Kết quả phải kiểm tra |
| --- | --- |
| User verified yêu cầu OTT | Gửi đúng verified contact, HTTP response chung không chứa secret |
| User không tồn tại hoặc email chưa xác minh | Không gửi secret tới địa chỉ do client chọn, không lộ account existence |
| Host header giả mạo | Magic link vẫn dùng canonical origin từ cấu hình |
| SMTP fail/bounce | Có recovery/retry, không lộ raw token |
| Token hết hạn | Không đăng nhập được dù email còn |
| Token đã dùng | Lần hai phải thất bại |
| Hai request consume đồng thời | Chỉ một thành công trên store thật |
| Nhiều lần generate | Rate limit, số token active và thư đến trễ được kiểm soát |
| CSRF sai hoặc thiếu | POST generate/login bị từ chối theo policy |
| Account disabled | Không đăng nhập trái với chính sách |
| Node A generate, node B consume | Token tìm được, consume atomic trong shared store |
| Login thành công | Có Authentication/session; chỉ redirect generation không tạo login |

## 8. Lỗi thường gặp

1. **Tưởng Spring tự gửi token:** Spring không biết email/SMS provider của bạn; phải có handler.
2. **Dùng AuthenticationSuccessHandler để gửi link:** đó là bước login thành công, không phải bước generation.
3. **Trả raw token về response của `/ott/generate`:** người yêu cầu có thể nhận secret thay vì chủ tài khoản.
4. **Cho form chỉ định địa chỉ nhận tùy ý:** attacker yêu cầu token của user khác và nhận tại email của mình.
5. **Tin Host header để xây magic link:** host poisoning có thể chuyển người dùng sang site của attacker.
6. **Không chống user enumeration:** khác body/status/timing có thể làm lộ tên tài khoản hợp lệ.
7. **Gọi consume ngay sau send:** token bị dùng hết trước khi email tới user.
8. **Dùng in-memory store trong cụm nhiều node:** token có thể mất khi restart hoặc qua load balancer.
9. **Không rate limit:** gây mail bombing, spam và cạn tài nguyên.
10. **Chỉ test Mockito mà không test SMTP, expiry, CSRF và single-use:** không chứng minh vận hành thực tế an toàn.

## 9. Checklist hoàn thành

- [ ] Handler `OneTimeTokenGenerationSuccessHandler` nhận token sau generate và sử dụng đúng `getUsername()`, `getTokenValue()`, `getExpiresAt()`.
- [ ] Tra cứu verified email/SMS từ user directory; không tin địa chỉ client tự cung cấp.
- [ ] URL magic link dùng canonical HTTPS origin; chống Host header poisoning.
- [ ] Không đưa token vào response tạo token, log, analytics hay redirect ngoài ứng dụng.
- [ ] Trả trang thông báo chung; có chống enumeration, rate limit và giám sát email.
- [ ] CSRF bật đúng với POST generate/submit và link GET không tự ý consume.
- [ ] Token expiry/single-use/replay xử lý bởi service; đã test hết hạn và 2 lần consume.
- [ ] Store dùng chung nếu multi-node; đã kiểm tra account status và SMTP outage.
- [ ] Phân biệt generation success với authentication success.

**Kết luận:** `OneTimeTokenService` tạo/tiêu thụ OTT; `OneTimeTokenGenerationSuccessHandler` là trách nhiệm **ứng dụng tự đưa token đến đúng chủ tài khoản một cách an toàn**. Không có email magic link an toàn nếu thiếu verified-contact lookup, bảo vệ URL, error handling và chống abuse.

## 10. Tài liệu chính thức

- Spring Security 6.5 — One-Time Token Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html
- `OneTimeTokenGenerationSuccessHandler` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/ott/OneTimeTokenGenerationSuccessHandler.html
- `RedirectOneTimeTokenGenerationSuccessHandler` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/ott/RedirectOneTimeTokenGenerationSuccessHandler.html
- `OneTimeToken` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/OneTimeToken.html
- `OneTimeTokenService` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/OneTimeTokenService.html
- Spring Security 6.5 — Servlet CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
