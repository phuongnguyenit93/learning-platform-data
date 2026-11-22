# Triển khai OTT, passkey hoặc MFA trên phiên bản Spring Security phù hợp

## 1. Mục tiêu thực hành tổng hợp

Bài thực hành xây một **kiến trúc xác thực có thể triển khai và kiểm thử** theo đúng phiên bản Spring Security, thay vì sao chép một ví dụ của nhánh 7.x vào dự án 6.x rồi tắt kiểm soát bảo mật vì gặp lỗi biên dịch hoặc lỗi đăng nhập.

Ba lựa chọn cần phân biệt:

1. **OTT (One-Time Token) login**: đăng nhập bằng một token do server cấp, thường gửi qua magic link email. Token chỉ dùng một lần, hết hạn, có ràng buộc tài khoản/mục đích. Đây có thể là **một cơ chế đăng nhập riêng**, không tự động trở thành MFA.
2. **Passkey / WebAuthn**: đăng ký credential khóa công khai và xác thực bằng challenge đã ký bởi authenticator. Server kiểm tra chữ ký, challenge, origin, RP ID, user handle, user presence/verification theo chính sách; **không lưu private key**.
3. **MFA (Multi-Factor Authentication)**: chính sách yêu cầu **nhiều bằng chứng xác thực**, có thể theo toàn ứng dụng hoặc chỉ tại hành động nhạy cảm. Chỉ thêm form OTT/passkey chưa đủ: các authorization rules phải **bắt buộc** các factor phù hợp.

Đề bài là **“Triển khai OTT, passkey hoặc MFA trên phiên bản phù hợp”**, vì vậy ta sẽ xây các nhánh thực hành riêng, chọn đúng khả năng có sẵn, kết hợp chúng khi cần, và kiểm chứng kết quả ở cả Servlet filters, server-side storage, browser và authorization.

Phạm vi chính: ứng dụng Spring MVC/Servlet với Java 17+, Spring Boot 3.x/Spring Security 6.5 hoặc Spring Boot 4.x/Spring Security 7.x tương thích. Với WebFlux cần API reactive riêng; không dùng nguyên `HttpSecurity` hay Servlet repository.

## 2. Chọn phiên bản trước khi chọn API

Bảng sau dựa trên các nhánh tài liệu đã phát hành vào **tháng 11/2026**; khi áp dụng, luôn kiểm tra dependency tree và security advisories của phiên bản thực tế.

| Nền tảng | OTT login | Passkey | MFA framework |
| --- | --- | --- | --- |
| Spring Security 5.x / Boot 2.x | Không dùng DSL OTT mới; muốn làm phải tích hợp cơ chế riêng có kiểm toán | WebAuthn cần tích hợp thư viện/flow riêng, không copy DSL 6.5/7 | Policy/step-up bằng authorization custom |
| Spring Security 6.4/6.5 / Boot 3.x tương thích | `oneTimeTokenLogin(...)`, `OneTimeTokenService` | `webAuthn(...)`; ở 6.5 tài liệu yêu cầu thư viện `webauthn4j-core` | Không dùng `@EnableMultiFactorAuthentication` của 7.x; triển khai policy riêng hoặc nâng version |
| Spring Security 7.0+ / Boot 4.x tương thích | Vẫn có `oneTimeTokenLogin(...)` | Module riêng `spring-security-webauthn` | `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication`, `AuthorizationManagerFactories.multiFactor()` |
| Spring Security 7.1.x | OTT và WebAuthn cùng khả năng 7.x | Có cải tiến về persistence/serialization và vận hành theo release | Có thêm hỗ trợ conditional MFA, bao gồm tình huống đã đăng ký WebAuthn |
| Spring Security 7.2 prerelease/snapshot | API đang tiến hóa | Không coi milestone/RC là mặc định production | Chỉ thử ở sandbox có kiểm thử |

**Không trộn mã 6.5 và 7.x trong một `build.gradle`.** Ở Spring Security 6.5, WebAuthn được tài liệu hướng dẫn bằng `spring-security-web` và `com.webauthn4j:webauthn4j-core`; ở 7.x, tài liệu chỉ dẫn thêm `org.springframework.security:spring-security-webauthn`. Dùng dependency management/BOM đúng Boot major.

**Thông tin phát hành đã xác minh:** Spring Security 7.1.2 và 7.0.8 được công bố ngày **23/10/2026**. Với dự án mới có thể dùng 7.1.x ổn định nếu hạ tầng Boot 4 tương thích. Đừng nâng chéo Security 7 vào Boot 3 chỉ để có MFA API, cũng đừng dùng bản 6.5 thiếu vá bảo mật cho deployment passkey có session chia sẻ.

### Lưu ý bảo mật theo phiên bản: bắt buộc kiểm tra

**CVE-2026-22751 — JDBC OTT TOCTOU/replay** (công bố 21/04/2026):

- Một số bản `JdbcOneTimeTokenService` cho phép hai request đồng thời dùng **cùng one-time token** lập nhiều phiên.
- Các bản bị ảnh hưởng: 6.4.0–6.4.15, 6.5.0–6.5.9, 7.0.0–7.0.4.
- Bản vá chính thức: **6.5.10+**, **7.0.5+**; nhánh 6.4.16 là enterprise support.
- Bài test concurrent/replay không phải tùy chọn. Nếu dùng `JdbcOneTimeTokenService` hãy chạy version đã vá, không tin rằng cái tên “OneTime” tự bảo đảm tính nguyên tử.

**CVE-2026-47841 — WebAuthn User Verification bypass với distributed session** (công bố 20/08/2026):

- Ảnh hưởng khi dùng Spring Security WebAuthn, cấu hình **userVerification = REQUIRED**, và WebAuthn ceremony data được serialize/deserialized qua distributed `HttpSession` store như Redis/JDBC.
- Vùng ảnh hưởng: 6.5.0–6.5.11, 7.0.0–7.0.6, 7.1.0.
- Các bản vá: **7.0.7+**, **7.1.1+**; **6.5.12** được advisory liệt kê trong phạm vi Enterprise Support.
- Lỗi gây ra từ phép so sánh identity của giá trị user-verification sau serialization, không phải do WebAuthn signature tự nhiên yếu.
- Nếu dự án buộc giữ 6.5 và cần UV REQUIRED cùng session phân tán, **không coi 6.5.11 OSS là đã sửa**. Xem bản vá được hỗ trợ hoặc lập kế hoạch chuyển phiên bản phù hợp.

Tra cứu advisory chính thức tại https://spring.io/security/cve-2026-22751/ và https://spring.io/security/cve-2026-47841/ trước khi phát hành.

## 3. Ba thuật ngữ dễ nhầm: OTT, OTP/TOTP, passkey

| Cơ chế | Bằng chứng | Từ đâu | Dùng trong trường hợp nào |
| --- | --- | --- | --- |
| OTT/magic link | Token ngẫu nhiên do server phát, có expiry, one-use | Email/SMS/kênh được chọn | Passwordless login, recovery hoặc một factor trong MFA tùy policy |
| TOTP | Mã ngắn tính từ shared secret + đồng hồ | Authenticator app đã enrollment | MFA/step-up; có rủi ro phishing relay |
| HOTP | Mã tính từ shared secret + counter | Thiết bị/app đã enrollment | MFA trong môi trường hỗ trợ |
| Passkey/WebAuthn | Chữ ký khóa riêng của authenticator trên challenge liên quan RP/origin | Platform/synced/cross-device security key | Phishing-resistant authentication, có thể passwordless |
| Password | Kiến thức người dùng; server so `PasswordEncoder.matches` | User nhập | Một factor “something you know” |
| Recovery code | Mã dự phòng một lần, sinh/lưu theo policy | User lưu riêng | Account recovery, không tương đương WebAuthn |

**OTT không phải TOTP**: OTT được **server sinh và gửi**, còn TOTP thường được authenticator tự sinh từ shared secret. Không nhầm `oneTimeTokenLogin()` của Spring Security với tính năng xác minh mã 6 chữ số của một authenticator app.

**Passkey không đồng nghĩa “mật khẩu cộng OTP”**: WebAuthn là một authentication ceremony khóa công khai; authenticator có thể yêu cầu PIN/biometric/user verification. Một passkey có user verification đúng cấu hình có thể đạt assurance cao mà không bắt user gõ thêm password. Chính sách cần quyết định **factor nào đủ cho thao tác nào**, dựa vào threat model, chứ không áp máy móc “phải đủ hai form”.

**MFA không phải giao diện**: sau khi người dùng nhập password, nếu endpoint chuyển tiền vẫn chấp nhận phiên chỉ có password, một trang nhập OTT tồn tại ở đâu đó **không tạo nên bảo vệ MFA**.

## 4. Chọn một bài thực hành theo yêu cầu

**Nhánh A — OTT login riêng**: phù hợp hệ thống muốn đăng nhập qua email magic link, có thể cùng tồn tại với `formLogin`. Làm được trong Spring Security 6.5 và 7.x. Khi bật cơ chế này, phải hạn chế user enumeration, rate limiting, one-use, expiry, link scanners và rủi ro hộp thư bị chiếm.

**Nhánh B — passkey đăng ký và đăng nhập**: phù hợp hệ thống muốn WebAuthn trên browser HTTPS, có RP ID và origin ổn định, lưu credential bền vững. Làm được từ nhánh 6.4/6.5 với dependencies tương ứng hoặc 7.x có module riêng. Cần test registration, challenge replay, signature, origin/RP ID, user verification và account recovery.

**Nhánh C — MFA/step-up**: phù hợp ứng dụng có hành động nhạy cảm như thay email, tắt MFA, thay phương thức thanh toán. Trong 7.x, có hỗ trợ factor authorities và authorization factory; trong 6.x phải tự xây chứng cứ xác thực, thời gian phát hành và authorization rules phù hợp. Chỉ dùng factor authorities **do server/framework tạo sau xác minh**, không nhận chuỗi `FACTOR_OTT` hoặc `mfa=true` từ request client.

**Lộ trình khuyến nghị khi thực hành:** chạy A với 6.5 đã vá → chạy B trên HTTPS với trình duyệt thật → nếu cần C, ưu tiên 7.x ổn định hoặc custom authorization rõ ràng ở 6.x. Đừng cố tích hợp ba đường cùng lúc trước khi có test độc lập của từng đường.

## 5. Chuẩn bị chung: bảo mật và project

Cấu trúc chức năng ví dụ:

```text
src/main/java/demo/auth/
  SecurityConfig.java
  AccountDirectory.java
  MagicLinkDeliveryHandler.java
  ... các repositories nếu chọn OTT JDBC hoặc WebAuthn JDBC
src/main/resources/
  application.yml
src/test/java/demo/auth/
  OttFlowIT.java
  WebAuthnFlowIT.java
  MfaAuthorizationIT.java
```

Các class application-specific cần tự triển khai như `AccountDirectory`, dịch vụ gửi email và audit. Đây là đề cương cấu trúc dự án, **không phải lời khẳng định các file ấy đã được tạo**.

### Nền tảng tối thiểu

- Chọn Spring Boot/Security/Java versions tương thích và có vá bảo mật.
- Dùng **HTTPS** trên browser public origin; cookie session `Secure`, `HttpOnly`, SameSite tùy login flow.
- Cấu hình reverse proxy trusted headers đúng; WebAuthn RP ID và OAuth/OTT public links không được xây từ header Host do attacker tự cung cấp.
- Với Spring MVC, dùng `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-test` và `spring-security-test`.
- Dữ liệu người dùng có account ID bất biến, status enabled/locked, verified email, roles/tenant và audit.
- Nếu có nhiều pods, dùng shared store cho session, OTT và WebAuthn challenge/repositories theo yêu cầu.
- Một request chỉ đi qua `SecurityFilterChain` đầu tiên match. Kiểm tra `securityMatcher` không loại các route `/ott/generate`, `/login/ott`, `/webauthn/*` ra ngoài chain cần thiết.
- Bật CSRF cho browser session; đừng disable CSRF chỉ vì custom login endpoint trả JSON.
- Không log password, raw token, URL chứa magic link, WebAuthn private material, session cookie hoặc recovery codes.

### Cấu hình cookie Servlet ví dụ

```yaml
server:
  servlet:
    session:
      timeout: 20m
      tracking-modes: cookie
      cookie:
        secure: true
        http-only: true
        same-site: lax
        path: /

# Chỉ cân nhắc sau ingress/proxy được tin và đã sanitize:
# server:
#   forward-headers-strategy: framework
```

`SameSite=Lax` phù hợp nhiều top-level GET redirects; không mặc nhiên phù hợp mọi iframe/cross-site POST. Bật HSTS ở edge khi HTTPS toàn bộ host đã sẵn sàng.

## 6. Nhánh A — OTT Login trong Spring Security 6.5

### 6.1. Dependencies và SecurityFilterChain

Gradle dependencies cho dự án Spring Boot **3.x đã quản lý các phiên bản tương thích**:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Nếu dùng JDBC store, thêm JDBC starter và DataSource/DB migration tương ứng. Không pin version của `spring-security-web`/`spring-security-config` riêng để trộn với Boot dependency BOM.

Security chain tối thiểu cho ứng dụng có form login và OTT:

```java
package demo.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                "/login",
                                "/login/ott",
                                "/ott/**",
                                "/assets/**"
                        ).permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .oneTimeTokenLogin(Customizer.withDefaults())
                .build();
    }
}
```

Đây là **class SecurityConfig tương thích phong cách Servlet 6.5**, không tạo sẵn account directory, email sender hoặc page `/ott/sent`. Với `oneTimeTokenLogin`, Spring Security cung cấp default request/submit page hỗ trợ demo, nhưng **không thể tự quyết định kênh gửi token cho bạn**: cần `OneTimeTokenGenerationSuccessHandler`.

**Luồng mặc định cần nhớ:**

```text
Browser -> GET /login
  -> người dùng chọn OTT, điền username/email
Browser -> POST /ott/generate + CSRF token
  -> GenerateOneTimeTokenFilter
  -> OneTimeTokenService.generate(...)
  -> OneTimeTokenGenerationSuccessHandler
  -> email / SMS / delivery theo app
Browser -> GET /login/ott?token=... (submit page)
Browser -> POST /login/ott + token + CSRF token
  -> OneTimeTokenAuthenticationFilter / AuthenticationProvider
  -> consume token (nếu hợp lệ)
  -> thành công: SecurityContext/Session + redirect
```

**GET magic link chỉ nên hiển thị form**, không thực hiện xác thực/tiêu thụ token ngay ở GET. Điều này giúp hạn chế tác động của email security scanners tự mở link. Việc submit chính thức phải được kiểm thử theo endpoint của version đang sử dụng.

### 6.2. Handler gửi token qua email

Spring Security định nghĩa `OneTimeTokenGenerationSuccessHandler` để ứng dụng chọn **cách giao token**, không nhúng mail server bí mật vào filter. Ví dụ dùng service email do ứng dụng cung cấp:

```java
package demo.auth;

import java.io.IOException;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.web.authentication.ott
        .OneTimeTokenGenerationSuccessHandler;
import org.springframework.security.web.authentication.ott
        .RedirectOneTimeTokenGenerationSuccessHandler;

@Component
public final class MagicLinkDeliveryHandler
        implements OneTimeTokenGenerationSuccessHandler {

    private final AccountDirectory accounts;
    private final MagicLinkSender mailer;

    // Domain minh họa, triển khai thật lấy từ cấu hình public origin
    // đã được kiểm chứng, KHÔNG lấy Host header tùy ý từ request.
    private static final String PUBLIC_ORIGIN =
            "https://login.example.test";

    private final OneTimeTokenGenerationSuccessHandler completed =
            new RedirectOneTimeTokenGenerationSuccessHandler("/ott/sent");

    public MagicLinkDeliveryHandler(
            AccountDirectory accounts, MagicLinkSender mailer) {
        this.accounts = accounts;
        this.mailer = mailer;
    }

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            OneTimeToken token) throws IOException, ServletException {

        String verifiedEmail =
                accounts.verifiedEmailFor(token.getUsername());
        String link = UriComponentsBuilder
                .fromUriString(PUBLIC_ORIGIN)
                .path("/login/ott")
                .queryParam("token", token.getTokenValue())
                .build().encode().toUriString();

        // Không log raw token, magic link, auth code hoặc email nhạy cảm.
        mailer.send(verifiedEmail,
                "Đăng nhập an toàn",
                "Mở đường liên kết để tiếp tục: " + link);

        completed.handle(request, response, token);
    }
}
```

`AccountDirectory` và `MagicLinkSender` là **interfaces của ứng dụng phải tự định nghĩa**, ví dụ `verifiedEmailFor(String username)` và `send(String to,String subject,String message)`. Code ở trên là thành phần Spring dùng được khi các interfaces có implementation hợp lệ và import khớp version; **không phải standalone Java SE class**. Trong production, đưa `PUBLIC_ORIGIN` vào config có allowlist, xác minh TLS và tài khoản/kênh đã được xác thực ownership.

**Nguy cơ cần xử lý trong delivery handler:**

- Chỉ gửi đến địa chỉ đã liên kết/xác minh với account **trên server**, không gửi email tự do từ query parameter.
- Không tiết lộ user tồn tại hay không bằng status/body/thời gian khác biệt quá lớn.
- Rate-limit theo IP/account/destination và thêm throttling ở mail service; không cho phép spam hộp thư.
- Không phản chiếu token trong redirect hoặc logs. Mẫu link có token trong query là thuận tiện nhưng có nguy cơ browser history, proxy logs và Referer; cần `Referrer-Policy: no-referrer`, HTTPS, token TTL ngắn, không nhúng third-party scripts.
- Nếu send email bị lỗi, đừng thông báo “đã gửi” một cách sai lệch; thiết kế retry/outbox đúng policy và tránh phát nhiều token vô hạn.
- Gắn context/correlation ID an toàn cho audit nhưng không log secret; link được tạo phải trỏ public host cố định đáng tin.

### 6.3. OneTimeTokenService và lưu trữ bền vững

Nếu không cung cấp `OneTimeTokenService`, Spring Security có default `InMemoryOneTimeTokenService`, phù hợp demo/một process nhưng không phải mặc định lý tưởng cho cluster nhiều pods.

Trong production, tài liệu giới thiệu `JdbcOneTimeTokenService`:

- Có schema SQL tương ứng trong `org/springframework/security/core/ott/jdbc/one-time-tokens-schema.sql`; phải tạo/migrate bảng trước.
- Phải cấu hình `JdbcOperations`/DataSource và bảo vệ DB.
- Mọi pod phải nhìn chung store và dùng cùng TTL/semantics.
- **Bắt buộc dùng bản đã vá CVE-2026-22751** trước khi tin tính one-time ở concurrency.
- Nếu viết store riêng, atomic consume phải xảy ra trong một thao tác transaction/conditional DELETE/UPDATE, không triển khai “SELECT rồi DELETE” tách rời mà cả hai requests đều đọc được token.

Ví dụ SQL **minh họa schema riêng**, không phải bảng chính thức của `JdbcOneTimeTokenService`:

```sql
-- Bảng TỰ THIẾT KẾ, KHÔNG phải table names của Spring Security.
CREATE TABLE app_ott (
    digest VARCHAR(64) PRIMARY KEY,
    subject_id VARCHAR(100) NOT NULL,
    purpose VARCHAR(40) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- Trong PostgreSQL, một DELETE có điều kiện trả về đúng một hàng
-- giúp xác định chỉ một request tiêu thụ thành công.
DELETE FROM app_ott
 WHERE digest = :digest
   AND subject_id = :subject_id
   AND purpose = :purpose
   AND expires_at > CURRENT_TIMESTAMP
RETURNING subject_id;
```

Dùng SHA-256 digest của token có entropy lớn để giảm rủi ro khi DB rò; DB schema/retention/rate-limit phải thiết kế riêng. Nếu token có entropy thấp như mã 6 chữ số, **hash không loại bỏ offline brute-force**; cần attempt counter, throttling và TTL nghiêm ngặt.

**Không coi việc DELETE thành công là đủ để cấp quyền** nếu user đã bị disable/locked/removed hoặc mục đích token không khớp. Phải xác minh trạng thái account và yếu tố policy ở thời điểm consume.

### 6.4. OTT không mặc nhiên là factor thứ hai

Một email magic link có thể được dùng **thay password**. Trong flow đó OTT là **factor đăng nhập đơn lẻ**, không phải “password + OTT”. Nếu muốn **MFA**, cần:

1. Người dùng đã xác minh password trong session hiện tại.
2. Token OTT được cấp cho **cùng account** và mục đích **step-up**, không dùng lại token cho password recovery.
3. Token bị tiêu thụ một lần và gắn factor evidence vào session hiện tại sau xác minh.
4. Authorization cho endpoint nhạy cảm kiểm tra **cả hai factor, độ mới và quyền nghiệp vụ**.
5. Nếu password reset, logout, đổi thiết bị hoặc phát hiện session compromise, invalidate factor evidence theo policy.

Email OTT cũng không phải kênh thứ hai hoàn toàn độc lập trong mọi trường hợp: nếu email được mở trên cùng browser và session đã bị chiếm, attacker có thể tiếp cận cả link. Với giao dịch rủi ro cao, cân nhắc passkey/WebAuthn hoặc factor chống phishing tốt hơn.

## 7. Nhánh B — Passkey/WebAuthn trên Spring Security 6.5

Spring Security 6.5 đã có `webAuthn(...)` Servlet DSL, nhưng dependency **khác** nhánh 7.x. Theo hướng dẫn 6.5:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    // Cho WebAuthn khi dùng Spring Security 6.5.
    // Kiểm tra version được docs của bản patch thực tế hỗ trợ:
    implementation 'com.webauthn4j:webauthn4j-core:0.29.7.RELEASE'
}
```

Spring Boot security starter đã mang `spring-security-web`; tài liệu Spring Security 6.5 cũng minh họa dependency `spring-security-web` bên cạnh `webauthn4j-core`. Không thêm module `spring-security-webauthn` 7.x vào classpath 6.5 rồi cho rằng tương thích.

Cấu hình MVC:

```java
@Bean
SecurityFilterChain passkeyChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login", "/assets/**").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .webAuthn(webAuthn -> webAuthn
                    .rpId("example.test")
                    .allowedOrigins("https://login.example.test"))
            .build();
}
```

Đây là mảnh cấu hình dùng trong `@Configuration` với imports `HttpSecurity`, `SecurityFilterChain` và `Customizer`. Không bật bean này **cùng một `SecurityFilterChain` fallback thứ hai** mà không cấu hình `@Order`/`securityMatcher`. Và cần có `UserDetailsService`/account source với người dùng xác thực để đăng ký credential.

**RP ID và origin là hai khái niệm khác nhau:**

- `rpId` là relying party identifier, thường là domain hợp lệ của RP, **không có scheme hoặc port**. Browser/authenticator ràng buộc credential theo RP ID.
- `allowedOrigins` là **origin đầy đủ** bao gồm scheme + host + port nếu non-default, ví dụ `https://login.example.test`.
- Nếu browser truy cập qua reverse proxy HTTPS nhưng Spring dùng `http://app:8080` hoặc allowed origin sai, ceremony thất bại.
- CORS headers không được phép sửa sai RP ID/signature, và không nên nới `allowedOrigins("*")`.

### Passkey cần đăng ký trước khi login

Một user đã đăng nhập (qua password hoặc một cơ chế xác minh đủ assurance) thực hiện:

```text
GET /settings/passkeys  (yêu cầu authenticated)
  -> chọn "Thêm passkey"
POST /webauthn/register/options + CSRF
  -> Spring tạo registration challenge/options
  -> challenge state được lưu server-side
Browser -> navigator.credentials.create({ publicKey: decodedOptions })
  -> authenticator tạo credential/private key
  -> browser trả attestation response (không phải private key)
POST /webauthn/register + CSRF + credential response
  -> Spring kiểm tra challenge, origin, RP ID, attestation policy
  -> UserCredentialRepository lưu credential PUBLIC KEY
  -> user nhìn thấy passkey trong danh sách
```

Cụ thể ở tài liệu 6.5/7.x:

- `POST /webauthn/register/options` trả creation options/challenge.
- `POST /webauthn/register` nhận credential từ browser.
- Chỉ người dùng đủ quyền mới đăng ký credential cho chính account của họ; không nhận arbitrary `userId` từ client để bind sang tài khoản khác.
- Thêm passkey mới là **hành động rủi ro cao**: yêu cầu recent authentication/step-up theo chính sách và thông báo thay đổi.
- Challenge phải dùng một lần, không được chia sẻ tùy tiện giữa sessions, và có TTL/transaction state đúng.
- Nếu browser dùng `navigator.credentials.create`/`get`, các trường binary như challenge, rawId và authenticatorData cần base64url decode/encode chính xác theo WebAuthn JSON codec; không gửi raw JavaScript ArrayBuffer vào JSON rồi hy vọng Spring tự hiểu.

### Credential repositories

Spring Security dùng hai abstraction:

- `PublicKeyCredentialUserEntityRepository` liên kết RP user entity/user handle với account.
- `UserCredentialRepository` lưu credential ID, public key, metadata/counter theo implementation.

6.5 có JDBC options:

```java
@Bean
JdbcPublicKeyCredentialUserEntityRepository credentialUsers(
        JdbcOperations jdbc) {
    return new JdbcPublicKeyCredentialUserEntityRepository(jdbc);
}

@Bean
JdbcUserCredentialRepository userCredentials(JdbcOperations jdbc) {
    return new JdbcUserCredentialRepository(jdbc);
}
```

Đây là mảnh `@Configuration`, import các class repository từ package tương ứng của bản Spring Security đang dùng. Cần kiểm tra tên schema/class chính xác trong Javadocs của patch được chọn, tạo tables bằng migrations và đảm bảo foreign keys/unique credential IDs. In-memory persistence mặc định không đủ để passkey tồn tại sau restart; JDBC/repository bền vững là cần thiết với production.

## 8. Nhánh B trên Security 7.x: module passkey riêng

Trong Spring Security 7.0+ tài liệu yêu cầu:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-webauthn'
}
```

BOM/Boot tương thích quản lý version. Ví dụ cấu hình:

```java
@Bean
SecurityFilterChain passkeyChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login", "/assets/**").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .webAuthn(webAuthn -> webAuthn
                    .rpId("example.test")
                    .allowedOrigins("https://login.example.test"))
            .build();
}
```

Cần dùng HTTPS/browser hỗ trợ WebAuthn và account đã đăng ký credential. `formLogin` trong ví dụ cho phép onboarding/recovery ban đầu; không phải passkey yêu cầu password cho **mỗi** lần xác thực.

### Luồng WebAuthn assertion khi login

```text
Browser -> GET /login
  -> chọn "Dùng passkey"
POST /webauthn/authenticate/options + CSRF
  -> server tạo challenge và lưu state
Browser -> navigator.credentials.get({ publicKey: decodedOptions })
  -> authenticator yêu cầu user presence / verification theo policy
  -> private key ký challenge (private key không rời authenticator)
POST /login/webauthn + CSRF + assertion JSON
  -> Spring xác minh server-side:
        - credential ID, public key, RP ID hash
        - clientDataJSON.type, challenge, origin
        - authenticatorData flags, user presence/verification
        - signature và counter/replay policy
  -> Authentication thành công
  -> SecurityContext, session và authorization
```

WebAuthn có tính chống phishing nhờ ràng buộc credential với origin/RP ID và challenge. **Biometric/PIN thường được kiểm tra cục bộ trên authenticator**; server không nhận vân tay hay PIN. Không nên tự parse và `return true` chỉ vì client gửi `userVerified=true`.

### Chọn userVerification

Trong WebAuthn có `required`, `preferred`, `discouraged`; yêu cầu user verification có ý nghĩa **assurance**:

- Nếu ứng dụng cần PIN/biometric ở authenticator, chọn **REQUIRED** và kiểm tra flag UV server-side, không chỉ hiển thị UI.
- Default `preferred` không bảo đảm mọi assertion được user verification; phải xác định chính sách thật.
- **CVE-2026-47841** đặc biệt quan trọng với REQUIRED + session phân tán: dùng phiên bản đã vá như 7.0.7+/7.1.1+ và test qua Redis/JDBC chứ không chỉ một node.
- Counter/signCount có nhiều trường hợp (syncable passkeys, counter=0); theo dõi sự bất thường theo chuẩn và library, không áp quy tắc tự chế làm hỏng credentials hợp lệ.

### Các ràng buộc không thể bỏ

1. Không tin challenge gửi lại bởi client nếu chưa đối chiếu server-side issuance.
2. Challenge phải đủ entropy, TTL và one-use, ràng buộc ceremony/session.
3. RP ID phải khớp domain public; không dùng backend hostname `app:8080`.
4. Origin trong `clientDataJSON` phải thuộc allowlist, đúng scheme/host/port.
5. Không tự chấp nhận credential được đăng ký cho account khác/tenant khác.
6. UserHandle/credential ID được lookup qua repository đã kiểm soát.
7. Không dùng WebAuthn registration như một unauthenticated endpoint cho phép attacker tự gắn key vào account nạn nhân.
8. Không bỏ CSRF của endpoint registration/options hay cookie session login.
9. Không tạo passkey backup/recovery mơ hồ khiến việc có private key trở nên vô nghĩa.
10. Khi gỡ/đổi passkey, audit và thông báo người dùng, thu hồi sessions nếu chính sách yêu cầu.

## 9. Nhánh C — MFA gốc của Spring Security 7.x

Trong **Spring Security 7.0+**, `FactorGrantedAuthority` biểu diễn factor đã được xác thực và thời điểm `issuedAt`. Mỗi authentication mechanism phù hợp cung cấp factor authority sau khi xác minh; authorization quyết định cần factor nào.

### 9.1. MFA toàn ứng dụng bằng password + OTT

```java
package demo.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.authorization
        .EnableMultiFactorAuthentication;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMultiFactorAuthentication(authorities = {
        FactorGrantedAuthority.PASSWORD_AUTHORITY,
        FactorGrantedAuthority.OTT_AUTHORITY
})
public class GlobalMfaSecurityConfig {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/assets/**").permitAll()
                        .requestMatchers("/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .oneTimeTokenLogin(Customizer.withDefaults())
                .build();
    }
}
```

Code áp dụng **Security 7.x**, **không** phải 6.5. Điều quan trọng: annotation bổ sung yêu cầu factor vào authorization rules; nếu user mới chứng minh password, một endpoint `authenticated()` vẫn có thể đòi OTT. Theo tài liệu 7.0, framework có thể điều hướng user sang phần login tương ứng factor còn thiếu.

**Chưa thể chạy demo chỉ với class này**: cần users, OTT delivery handler và store phù hợp. Không phát hành trước khi đã test email OTP delivery, CSRF, required factors, registration/recovery, các endpoint public, API clients và admin accounts.

### 9.2. Selective MFA: chỉ yêu cầu thêm factor ở đường nhạy cảm

Nếu muốn chỉ `/admin/**` và `/settings/security/**` yêu cầu cả password + OTT, trong Spring Security 7.x có thể dùng factory **cục bộ**:

```java
@Configuration
@EnableMultiFactorAuthentication(authorities = {})
public class SelectiveMfaSecurityConfig {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {

        var mfa = AuthorizationManagerFactories.multiFactor()
                .requireFactors(
                        FactorGrantedAuthority.PASSWORD_AUTHORITY,
                        FactorGrantedAuthority.OTT_AUTHORITY)
                .build();

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/assets/**", "/login")
                            .permitAll()
                        .requestMatchers("/admin/**")
                            .access(mfa.hasRole("ADMIN"))
                        .requestMatchers("/settings/security/**")
                            .access(mfa.authenticated())
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .oneTimeTokenLogin(Customizer.withDefaults())
                .build();
    }
}
```

Imports thêm `org.springframework.security.authorization.AuthorizationManagerFactories` và các class trong ví dụ trên. Đây là **alternative configuration** cho toàn cục, không bật cả `GlobalMfaSecurityConfig` và `SelectiveMfaSecurityConfig` cùng lúc trừ khi bạn đã kiểm soát nhiều SecurityFilterChains. Code shape dựa trên hướng dẫn Spring Security 7.0.

**Vì sao `@EnableMultiFactorAuthentication(authorities = {})`?** Nó kích hoạt cơ sở hỗ trợ MFA nhưng không tự publish factory yêu cầu factor trên **mọi** authorization rule. Ta dùng `mfa.hasRole`/`mfa.authenticated` đúng các đường cần. Điều này phù hợp với step-up hơn là bắt người dùng đi qua hai form trên mọi endpoint.

**Điểm không được bỏ qua:** `permitAll` đối với `/login`/`/ott/**` không có nghĩa tự tắt CSRF. Đảm bảo generated filter endpoints có thể được truy cập đúng và không bị chain matcher chặn.

### 9.3. Độ mới của factor: step-up với validDuration

Một user đã nhập password hoặc đã dùng passkey từ 8 giờ trước có thể vẫn có session, nhưng thay email/đổi MFA cần chứng minh gần đây hơn. Trong Security 7.x:

```java
var recentPassword = AuthorizationManagerFactories.multiFactor()
        .requireFactor(factor -> factor
                .passwordAuthority()
                .validDuration(Duration.ofMinutes(10)))
        .build();
```

Đây là **snippet** dùng import `java.time.Duration` và `AuthorizationManagerFactories`. Khi dùng:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/settings/change-email")
            .access(recentPassword.authenticated())
        .anyRequest().authenticated());
```

Đây mới là yêu cầu **password mới trong 10 phút**, chưa phải yêu cầu cả password **và** OTT. Nếu nghiệp vụ muốn hai factor mới, cần policy kết hợp tương ứng với `requireFactor(...)`/`requireFactors(...)` và kiểm thử expiry từng factor. Một factor được lưu trong session không nên được coi là “mới” chỉ vì mỗi request gia hạn cookie session.

**Lưu ý mức version:** `FactorGrantedAuthority` và `AuthorizationManagerFactories` là API 7.0+. Đừng cố import vào 6.5.

## 10. MFA trong Spring Security 6.5 nếu chưa thể nâng major

Nếu dự án nằm trên Security 6.5 và phải triển khai MFA trước khi nâng lên 7.x, **không có** `@EnableMultiFactorAuthentication` như tài liệu 7.0. Một hướng kiến trúc an toàn:

1. Đăng nhập factor thứ nhất (password/provider) bằng Spring Security, tạo session đúng.
2. Phát challenge thứ hai cho **cùng user, cùng phiên, đúng mục đích**.
3. Chỉ sau khi token/WebAuthn assertion được server verify, ghi một record chứng cứ trong **server-side** session/store: subject, factor type, issuedAt, assurance, transaction/action binding.
4. Tạo `AuthorizationManager<RequestAuthorizationContext>` hoặc method-security guard kiểm tra chứng cứ **cùng subject, còn hạn và đúng action** trước khi cho thực hiện hành động.
5. Hết TTL/đổi account/logout/password reset thì xóa chứng cứ.
6. Không tự tạo `GrantedAuthority("FACTOR_OTT")` từ query param hoặc một form POST mà chưa verify.

Ví dụ pseudo-code logic authorization (không phải full Spring class):

```java
boolean authorizeChangeEmail(
        Authentication currentUser,
        StepUpEvidence evidence,
        Instant now,
        String actionId) {

    return currentUser != null
        && currentUser.isAuthenticated()
        && evidence != null
        && evidence.subjectId().equals(currentUser.getName())
        && evidence.actionId().equals(actionId)
        && evidence.hasVerifiedPassword()
        && evidence.hasVerifiedSecondFactor()
        && now.isBefore(evidence.expiresAt());
}
```

`StepUpEvidence` là một type **do ứng dụng định nghĩa**. Real implementation phải xử lý nguyên tử, storage, replays và concurrency. Nếu chỉ set một biến `session.setAttribute("mfa", true)` sau GET link, không có ràng buộc action/TTL/subject, có thể bị lạm dụng.

### Không đánh tráo bước xác minh thành bước cấp quyền

Ngay cả khi factor được verify, authorization theo domain vẫn cần kiểm tra:

- Người dùng có quyền sửa email này không?
- Tài khoản đã bị khóa/disable hoặc session bị revoke chưa?
- Amount/currency/recipient của một giao dịch có đúng những gì người dùng đã xác nhận?
- Step-up evidence có được ràng buộc với payload/action cụ thể không?
- Có idempotency key để tránh nhấp xác nhận nhiều lần gây nhiều chuyển tiền không?

MFA giải quyết **authentication assurance**, không thay cho ownership, RBAC/ABAC, CSRF, validation hoặc transaction idempotency.

## 11. OTT + passkey không phải phép cộng tên cơ chế

Có ít nhất ba policy hợp lệ, nhưng mục tiêu khác nhau:

| Chính sách | Ví dụ | Đánh đổi |
| --- | --- | --- |
| `password OR passkey` để đăng nhập | Người dùng chọn phương thức | Tối ưu trải nghiệm, nhưng recovery cần bảo vệ |
| `password AND OTT` để thao tác nhạy cảm | Đổi email/chuyển tiền sau password login | Có hai bước nhưng kênh email có thể bị phishing |
| `recent verified WebAuthn` **hoặc** password+OTT | Phê duyệt giao dịch với passkey, có fallback | Cần thiết kế assurance/freshness và quản lý fallback nhất quán |

**Không tự tuyên bố WebAuthn “đã có MFA” chỉ vì browser hiển thị vân tay**. Bằng chứng server phải kiểm tra WebAuthn user verification khi policy yêu cầu. Với synced passkeys và user verification, assurance có thể đáp ứng yêu cầu mạnh; tổ chức vẫn cần đánh giá theo rủi ro.

**Không biến fallback thành lỗ hổng:** nếu passkey login yêu cầu user verification nhưng người dùng có thể reset toàn bộ passkeys chỉ bằng link email không được bảo vệ, attacker có thể đi đường recovery yếu hơn. Recovery codes nên sinh từ CSPRNG, chỉ dùng một lần, mã hóa/hash hợp lý và audit.

## 12. Session, CSRF, proxy và những lỗi thực tế

### 12.1. Session lifecycle

- Form login, OTT login và WebAuthn login có thể tạo hoặc thay đổi `HttpSession`/`SecurityContext` theo filter strategy; không nên tự thay đổi context kiểu tùy tiện.
- Spring Security 6 dùng explicit save semantics ở custom flows; nếu tự viết login controller, phải quản lý `SecurityContextRepository.saveContext(...)` đúng, nhưng các filter login chuẩn đã có logic của framework.
- Sau xác thực, session ID rotation giúp chống fixation; kiểm tra browser dùng cookie **mới**.
- Một pod tạo challenge ở RAM và callback vào pod khác có thể mất state; dùng shared session/challenge repository nếu nhiều instances.
- Invalidate/revoke sessions theo policy khi password reset, account disable hoặc nghi thiết bị bị đánh cắp.

### 12.2. CSRF và các endpoint

- `POST /ott/generate` và `POST /login/ott` cần CSRF protection khi browser dùng session cookie.
- `POST /webauthn/register/options`, `POST /webauthn/register`, `POST /webauthn/authenticate/options` và `POST /login/webauthn` là các flows cần CSRF/nonce/challenge xử lý đúng contract.
- Một `GET` magic link có token trong URL cần hạn chế referrer/logging và **không có side effect authenticate** chỉ vì người đọc email client tự preview.
- Đừng tắt CSRF global chỉ vì WebAuthn calls gửi JSON. Dùng token transport/cookie CSRF được cấu hình đúng trong SPA.

### 12.3. Public origin sau reverse proxy

WebAuthn RP ID và allowed origin, OTT magic link base URL, OAuth2 redirect URI đều dựa vào public scheme/host/path đúng. Nếu client ở `https://login.example.test` nhưng backend nghĩ `http://app:8080` thì:

- Cookie `Secure` có thể bị cấu hình sai nếu không đặt explicit.
- Magic link có thể trỏ host nội bộ hoặc HTTP.
- WebAuthn origin verification có thể fail.
- Callbacks/challenges có thể mất session vì host/path không khớp.

Chỉ tin `Forwarded`/`X-Forwarded-*` từ proxy đã loại bỏ header do client tự cung cấp. Tốt nhất dùng public origin allowlist cho magic link và `rpId/allowedOrigins` cố định cấu hình. Không đặt `Domain=.example.test` để làm mọi subdomain chia sẻ session một cách thiếu kiểm soát.

## 13. Java 17 chạy độc lập: mô phỏng OTT one-use và factor policy

Chương trình này **chạy bằng Java SE 17, không phụ thuộc Spring** để dễ quan sát semantics. Nó có:

- `SecureRandom` sinh 32 bytes, token `Base64URL` và SHA-256 digest làm key trong memory.
- Server check **subject + purpose + expiry** trước khi consume OTT.
- `ConcurrentHashMap.computeIfPresent` để chỉ một request đồng thời consume thành công.
- “Factor evidence” gắn **cùng subject** và có freshness window.
- Nhánh passkey chỉ đánh dấu **sau khi một server-side WebAuthn verifier thật đã chứng minh hợp lệ**; chương trình không tự kiểm tra chữ ký WebAuthn.

Tạo file **`OttPasskeyMfaPolicyDemo.java`**:

```java
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.security.*;
import java.nio.charset.StandardCharsets;

public class OttPasskeyMfaPolicyDemo {
    enum Factor { PASSWORD, OTT, PASSKEY }

    record Token(String user, String purpose, Instant expiresAt) {}

    static final class ManualClock extends Clock {
        private final AtomicReference<Instant> now;

        ManualClock(Instant initial) {
            now = new AtomicReference<>(initial);
        }

        @Override public Instant instant() {
            return now.get();
        }

        @Override public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override public Clock withZone(ZoneId zone) {
            return Clock.fixed(instant(), zone);
        }

        void forward(Duration amount) {
            now.updateAndGet(t -> t.plus(amount));
        }
    }

    static final class OneTimeTokens {
        private final Clock clock;
        private final SecureRandom random = new SecureRandom();
        private final ConcurrentHashMap<String, Token> tokens =
                new ConcurrentHashMap<>();

        OneTimeTokens(Clock clock) {
            this.clock = clock;
        }

        String issue(String user, String purpose, Duration lifetime) {
            if (user == null || user.isBlank()
                    || purpose == null || purpose.isBlank()
                    || lifetime.isNegative() || lifetime.isZero()) {
                throw new IllegalArgumentException("Invalid request");
            }

            while (true) {
                byte[] randomBytes = new byte[32];
                random.nextBytes(randomBytes);
                String raw = Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(randomBytes);
                String key = digest(raw);

                Token newToken = new Token(
                        user, purpose,
                        clock.instant().plus(lifetime));

                if (tokens.putIfAbsent(key, newToken) == null) {
                    return raw;
                }
            }
        }

        boolean consume(String raw, String user, String purpose) {
            if (raw == null || raw.isBlank()
                    || user == null || purpose == null) {
                return false;
            }

            AtomicBoolean used = new AtomicBoolean(false);

            tokens.computeIfPresent(digest(raw), (key, token) -> {
                if (!clock.instant().isBefore(token.expiresAt())) {
                    return null; // expire
                }
                if (!token.user().equals(user)
                        || !token.purpose().equals(purpose)) {
                    return token; // không consume với user/purpose sai
                }
                used.set(true);
                return null; // một lần thành công duy nhất
            });
            return used.get();
        }

        private static String digest(String raw) {
            try {
                byte[] bytes = MessageDigest.getInstance("SHA-256")
                        .digest(raw.getBytes(StandardCharsets.UTF_8));
                return HexFormat.of().formatHex(bytes);
            } catch (NoSuchAlgorithmException ex) {
                throw new IllegalStateException(ex);
            }
        }
    }

    static final class Session {
        private final String subject;
        private final Clock clock;

        private final EnumMap<Factor, Instant> verifiedAt =
                new EnumMap<>(Factor.class);

        Session(String subject, Clock clock) {
            this.subject = subject;
            this.clock = clock;
        }

        // TEST STUB: chỉ authenticator do SERVER xác minh
        // mới được phép gọi trong triển khai thật.
        void markVerified(String verifiedSubject, Factor factor) {
            if (!subject.equals(verifiedSubject)) {
                throw new SecurityException("Different identity");
            }
            verifiedAt.put(factor, clock.instant());
        }

        boolean hasFresh(Factor factor, Duration maxAge) {
            Instant time = verifiedAt.get(factor);
            Instant now = clock.instant();
            return time != null && !now.isBefore(time)
                    && now.isBefore(time.plus(maxAge));
        }

        boolean signedIn() {
            return hasFresh(Factor.PASSWORD, Duration.ofHours(8))
                    || hasFresh(Factor.PASSKEY, Duration.ofHours(8));
        }

        boolean canChangeEmail() {
            return hasFresh(Factor.PASSWORD, Duration.ofHours(8))
                    && hasFresh(Factor.OTT, Duration.ofMinutes(5));
        }

        boolean canApproveByPasskey() {
            return hasFresh(Factor.PASSKEY, Duration.ofMinutes(2));
        }
    }

    public static void main(String[] args) throws Exception {
        ManualClock clock = new ManualClock(
                Instant.parse("2026-01-01T00:00:00Z"));
        OneTimeTokens tokens = new OneTimeTokens(clock);

        String token = tokens.issue(
                "alice", "step-up", Duration.ofMinutes(5));

        System.out.println("wrongSubjectConsumes="
                + tokens.consume(token, "bob", "step-up"));
        System.out.println("wrongPurposeConsumes="
                + tokens.consume(token, "alice", "login"));
        System.out.println("firstUseAccepted="
                + tokens.consume(token, "alice", "step-up"));
        System.out.println("replayAccepted="
                + tokens.consume(token, "alice", "step-up"));

        String expiring = tokens.issue(
                "alice", "step-up", Duration.ofMinutes(1));
        clock.forward(Duration.ofMinutes(1));

        System.out.println("atExpiryAccepted="
                + tokens.consume(expiring, "alice", "step-up"));

        OneTimeTokens race = new OneTimeTokens(clock);
        String raceToken = race.issue(
                "alice", "step-up", Duration.ofMinutes(5));

        ExecutorService pool = Executors.newFixedThreadPool(12);
        try {
            CountDownLatch gate = new CountDownLatch(1);
            List<Future<Boolean>> results = new ArrayList<>();

            for (int i = 0; i < 12; i++) {
                results.add(pool.submit(() -> {
                    gate.await();
                    return race.consume(
                            raceToken, "alice", "step-up");
                }));
            }

            gate.countDown();
            int accepted = 0;
            for (Future<Boolean> result : results) {
                if (result.get()) {
                    accepted++;
                }
            }

            System.out.println("concurrentAccepted=" + accepted);
        } finally {
            pool.shutdownNow();
        }

        Session session = new Session("alice", clock);
        session.markVerified("alice", Factor.PASSWORD);

        System.out.println("signedInWithPassword="
                + session.signedIn());
        System.out.println("emailBeforeSecondFactor="
                + session.canChangeEmail());

        session.markVerified("alice", Factor.OTT);
        System.out.println("emailAfterSecondFactor="
                + session.canChangeEmail());

        clock.forward(Duration.ofMinutes(5));
        System.out.println("emailAtFreshnessExpiry="
                + session.canChangeEmail());

        boolean otherIdentityRejected = false;
        try {
            session.markVerified("bob", Factor.PASSKEY);
        } catch (SecurityException expected) {
            otherIdentityRejected = true;
        }

        System.out.println("wrongPasskeySubjectRejected="
                + otherIdentityRejected);

        // Giả lập KẾT QUẢ của WebAuthn verifier ở server.
        // Không nhận boolean "webauthnVerified" từ client.
        session.markVerified("alice", Factor.PASSKEY);
        System.out.println("passkeyApproval="
                + session.canApproveByPasskey());

        clock.forward(Duration.ofMinutes(2));
        System.out.println("passkeyApprovalExpired="
                + session.canApproveByPasskey());
    }
}
```

Chạy với JDK 17+:

```bash
javac OttPasskeyMfaPolicyDemo.java
java OttPasskeyMfaPolicyDemo
```

**Kết quả đã kiểm chứng bằng Java 17/JShell:**

```text
wrongSubjectConsumes=false
wrongPurposeConsumes=false
firstUseAccepted=true
replayAccepted=false
atExpiryAccepted=false
concurrentAccepted=1
signedInWithPassword=true
emailBeforeSecondFactor=false
emailAfterSecondFactor=true
emailAtFreshnessExpiry=false
wrongPasskeySubjectRejected=true
passkeyApproval=true
passkeyApprovalExpired=false
```

### Giới hạn của ví dụ

1. `OneTimeTokens` chỉ là một store trong JVM. `computeIfPresent` cung cấp tính nguyên tử **trong process**, không thay thế database transaction/CAS cho nhiều pod.
2. `Session.markVerified(...)` là **test stub**. Trong ứng dụng thật, tuyệt đối không expose nó qua controller; factor chỉ được cấp sau khi `AuthenticationProvider` hoặc WebAuthn verifier **xác thực bằng chứng mật mã**.
3. Không có kiểm tra password thật hoặc chữ ký WebAuthn; đây là bài kiểm thử **policy/lifecycle**, không phải WebAuthn implementation.
4. `canChangeEmail` chỉ yêu cầu password và OTT recent, chưa ràng buộc token với **email đích**; production nên buộc token/action và confirm UI chống transaction swapping.
5. `canApproveByPasskey` minh họa passkey recent, không hàm ý mọi passkey assertion đều đạt UV REQUIRED/assurance theo sản phẩm.
6. Không có CSRF, browser, email delivery, rate limits, distributed sessions, account status, recovery hay auditing.
7. Token raw không được log; digest SHA-256 có ý nghĩa với token **entropy lớn**, không phải mã 6 số.
8. Thời gian dùng `ManualClock` cố định để test expiry chính xác; production cần clock được quản lý và policy xử lý lệch giờ.
9. `concurrentAccepted=1` mô tả một token chỉ được consume một lần; nó không giới hạn bao nhiêu login khác nhau có thể hợp lệ.
10. Chương trình không đảm bảo real-world WebAuthn `signCount`, origin, RP ID hoặc certificate attestation policy — hãy dùng thư viện đã kiểm thử.

## 14. Integration tests: chứng minh OTT có tính một lần

Các bài test ưu tiên khi nối Spring Security thật:

| Kịch bản | Lớp test | Kết quả mong đợi |
| --- | --- | --- |
| POST generate với CSRF hợp lệ | MockMvc + Email sender fake | Generate handler được gọi, không log raw token |
| POST generate thiếu CSRF | MockMvc | Từ chối đúng CSRF policy |
| Username/email không tồn tại | MockMvc | Không tiết lộ account existence; tránh gửi mail tùy ý |
| Token đúng chưa hết hạn | Full chain + store | Login thành công một lần |
| Token đã consume | Store/HTTP | Replay fail; không tạo session thứ hai |
| Token vừa chạm `expiresAt` | Clock test | Bị từ chối |
| Token của user khác | Store + auth provider | Không đăng nhập sai account |
| Token sai purpose | Store | Không thể dùng recovery token cho login |
| 12–50 requests đồng thời cùng token | DB/cluster integration | **Chỉ một authentication thành công** |
| InMemory store + hai pods | Distributed deployment test | Phát hiện mất token khi routing sang node khác |
| Jdbc store bản chưa vá | Version audit | **Không release** nếu dính CVE-2026-22751 |
| Email link được scanner GET | Browser/E2E | GET không consume token |
| Email delivery fail | Service/integration | Không báo “đã gửi” sai; không mất audit |
| Token bị lộ trong logs/Referer | Security audit | Không có raw token/query trong access logs |
| Logout sau OTT login | MockMvc/browser | Session invalidated |
| User disabled trước consume | Auth provider test | Không cấp quyền trái policy |

**Quan trọng:** MockMvc không tự mô phỏng browser email-link scanner, cookie SameSite hoặc network/proxy thực tế. Với test concurrency phải dùng DB/store **thật** và nhiều transaction/requests, không chỉ mock `OneTimeTokenService.consume` bằng `thenReturn(true)`.

Ví dụ `MockMvc` fragment:

```java
// Trong @SpringBootTest + @AutoConfigureMockMvc và
// SecurityFilterChain thật (imports của spring-security-test).
mvc.perform(post("/ott/generate")
        .param("username", "alice")
        .with(csrf()))
    .andExpect(status().is3xxRedirection());

// Sau đó xác minh FakeMailSender đã được gọi,
// đọc token chỉ trong test memory, POST login/ott với CSRF.
```

Đây là **mảnh code theo fixture**; status cụ thể có thể đổi khi custom success handler. Đừng tuyên bố một redirect 302 đủ chứng minh token đã được gửi hoặc store đã consume đúng.

## 15. Integration tests WebAuthn cần browser và verifier thật

| Test | Kỳ vọng |
| --- | --- |
| Registration options không có session/CSRF | Bị từ chối theo policy |
| User A cố register credential cho user B | Bị từ chối |
| WebAuthn register challenge đã hết hạn | Bị từ chối |
| WebAuthn register challenge replay | Bị từ chối |
| Origin là `https://evil.test` | Không được accept |
| RP ID hash không khớp | Không được accept |
| WebAuthn assertion signature bị sửa 1 byte | 401/failed authentication |
| Wrong credential ID hoặc user handle | Không map sang account khác |
| User presence required nhưng thiếu UP | Reject theo policy |
| User verification REQUIRED nhưng thiếu UV | Reject theo policy |
| Passkey assertion đúng, credential đã đăng ký | Authentication success |
| Auth challenge dùng lại | Replay failed |
| Credential bị user revoke | Không login được |
| Counter bất thường | Theo policy/library, giám sát/risk handling |
| Reverse proxy làm sai public origin | Failed until corrected |
| 2 pods và shared session store | Challenge/session nhất quán |
| Distributed session + UV REQUIRED | Dùng bản vá CVE-2026-47841, test serialization |
| Browser không có passkey | Recovery path an toàn, không bypass |
| Passkey synced/cross-device | Chính sách signCount/UV hợp lý |
| Đăng ký passkey mới khi session cũ | Yêu cầu recent authentication/step-up |
| CSRF trong WebAuthn API | Vẫn được enforce |

Trong browser test, dùng **môi trường thực hỗ trợ WebAuthn** hoặc virtual authenticator của Playwright/Selenium khi khả thi. Không fake `navigator.credentials.get` trả chữ ký do test tự bịa rồi kết luận passkeys hoạt động; cryptographic verification phải chạy thật.

Một integration test sử dụng Spring MockMvc có thể khẳng định endpoint status/CSRF/authorization, nhưng **không chứng minh browser đã thực hiện WebAuthn ceremony**. Kết hợp hai lớp test.

## 16. Kiểm thử MFA/step-up và quyền ứng dụng

### Ma trận người dùng/factor

| Trạng thái phiên | Đọc trang cá nhân | Đổi email cần password+OTT | Phê duyệt bằng recent passkey |
| --- | --- | --- | --- |
| Anonymous | Deny/redirect | Deny | Deny |
| Chỉ password hợp lệ | Allow | Deny; yêu cầu OTT | Deny nếu policy chỉ nhận passkey |
| Chỉ OTT được dùng làm login | Allow nếu OTT login cho phép | Deny nếu thiếu password | Deny |
| Password + OTT fresh | Allow | Allow khi còn quyền ownership | Theo policy passkey riêng |
| Password + OTT expired | Allow nếu session còn | Deny; step-up lại | Theo policy |
| Passkey verified, fresh, đúng subject | Allow | Tùy policy, không tự cộng password+OTT | Allow nếu nghiệp vụ chấp nhận |
| Passkey verified nhưng UV không đủ | Theo assurance policy | Không nâng assurance giả | Deny nếu UV REQUIRED |
| Factor đúng nhưng role/tenant sai | Có thể được đọc profile | **Deny** thao tác không thuộc quyền | Deny |
| Session đã logout/revoked | Deny | Deny | Deny |
| Actor chuyển account trong browser | Theo session mới | Không dùng factor từ account cũ | Không dùng proof từ account cũ |

### Độ mới và tính ràng buộc giao dịch

Đối với hành động **thay email**:

```text
GET /settings/email
    -> authenticated session
POST /settings/email/challenge
    -> xác nhận đúng account, CSRF và action id
    -> issue OTT purpose=change-email, subject=alice, TTL ngắn
    -> gửi kênh đã được xác minh
POST /settings/email/confirm
    -> CSRF + token + action id + email mới đã ràng buộc
    -> atomic consume
    -> kiểm tra session/user, recent factor, authorization, ownership
    -> transaction update email + audit + idempotency
    -> revoke challenge/session theo policy
```

Nếu token chỉ bind `subject` mà không bind **new email hoặc transaction digest**, attacker có thể đánh tráo payload sau khi user xác nhận factor. Với thao tác nhạy cảm, cần transaction binding và hiển thị chính xác điều người dùng chuẩn bị phê duyệt.

**Chống replay khác idempotency:** token dùng một lần ngăn lặp xác minh, nhưng một request tài chính có thể retry vì mạng và cần idempotency key riêng để không trừ tiền hai lần. Không dựa vào TTL token thay cho transaction lock.

## 17. Các lỗ hổng/anti-patterns thường gặp

**1. Copy `@EnableMultiFactorAuthentication` vào Security 6.5.** Class chưa có trong 6.x; phải dùng policy custom hoặc nâng major có kiểm thử.

**2. Copy `spring-security-webauthn` 7.x vào classpath 6.5.** Dẫn tới mismatch APIs; dùng `webauthn4j-core` theo hướng dẫn 6.5.

**3. Chỉ bật `oneTimeTokenLogin` rồi gọi là “đã có MFA”.** OTT login đơn lẻ không tương đương password+OTT; cần authorization rule đòi cả hai factor.

**4. Dùng email OTP khi hộp thư bị kiểm soát cùng browser mà coi là kênh độc lập hoàn toàn.** Đánh giá phishing và account compromise, ưu tiên passkeys khi phù hợp.

**5. Dùng default in-memory OTT trong nhiều pods.** Token tạo pod A không được pod B tìm thấy; dùng shared store.

**6. Không patch CVE-2026-22751.** JDBC OTT cũ có thể cho multiple sessions dùng một token.

**7. Không patch CVE-2026-47841 trong WebAuthn UV REQUIRED + distributed session.** Có thể bỏ qua requirement UV sau session serialization.

**8. Generate token entropy thấp và không rate-limit.** Token đoán được hoặc brute-force; dùng CSPRNG, TTL, attempts.

**9. Lưu raw OTT trong log/DB/analytics.** Nếu bị lộ, token có thể bị replay trong thời gian hiệu lực. Hash token entropy lớn và redaction.

**10. Email link đi qua host HTTP hoặc host nội bộ.** Rò token/không dùng được; dùng public HTTPS allowlist và HSTS.

**11. Tiêu thụ token ở GET khi scanner preview link.** Người dùng chưa nhấn link đã bị consume; GET hiển thị trang submit, POST consume có CSRF.

**12. Không xử lý link scanners mà tắt one-use.** Làm mất thuộc tính bảo vệ, cần thiết kế flow phù hợp.

**13. Dùng SELECT rồi DELETE cho token và cho rằng atomic.** TOCTOU concurrency; dùng JDBC đã vá hoặc transaction/conditional consume.

**14. Không kiểm tra user disabled/locked tại consume.** Token phát trước khi khóa tài khoản vẫn cấp session; xác minh account state theo policy.

**15. Passkey RP ID là hostname backend `localhost` khi browser ở domain public.** Ceremony fail; RP ID phải phù hợp public origin.

**16. `allowedOrigins("*")` để “sửa passkey lỗi”.** Phá origin boundary; dùng exact allowlist.

**17. Tự viết xác minh chữ ký WebAuthn bằng cách so chuỗi.** Sai chuẩn, dễ bypass; dùng library đã kiểm thử.

**18. Tin flag `userVerified` do frontend gửi.** UV là phần dữ liệu authenticator được server xác minh theo protocol, không phải boolean tự khai.

**19. Bỏ CSRF của endpoint JSON WebAuthn/OTT.** Session cookie vẫn có CSRF risk; giữ CSRF tokens.

**20. Bật global MFA mà không có enrollment/recovery cho tất cả user.** User bị lockout, admin không đăng nhập được; có rollout phase và recovery.

**21. Đặt `permitAll` quá rộng bao gồm endpoints nhạy cảm.** Public registration hoặc factor verification không được bảo vệ đúng.

**22. Không bind factor với account/session.** Dùng OTP của user A để nâng assurance cho user B.

**23. Không yêu cầu recent factor.** Một lần OTT 3 tháng trước vẫn được coi step-up; dùng validity window.

**24. Dựa vào URL role mà bỏ ownership.** User có ROLE_USER vẫn có thể sửa tài khoản người khác; kiểm tra subject/tenant.

**25. Recovery yếu hơn cơ chế chính.** Reset passkey chỉ qua link dễ bị phishing, làm mất lợi thế WebAuthn.

**26. Không kiểm thử browser thật.** MockMvc không mô phỏng navigator.credentials/CTAP, origin/SameSite/virtual authenticator.

**27. Không kiểm tra version patch sau khi nâng minor.** Tính năng có thể hoạt động nhưng vẫn dính CVE đã biết.

**28. Vừa dùng tự viết factor store vừa dùng `FactorGrantedAuthority` mà không có một nguồn sự thật.** Đồng bộ sai state và có thể bypass; chọn policy source-of-truth rõ.

**29. Ghi raw factor/device fingerprint vào metrics labels.** Dễ lộ PII và high cardinality; log events đã scrub.

**30. Cho phép client chỉ định `purpose=admin` để nhận token quyền cao.** Server phải quyết định purpose từ route/authorization, không nhận mục đích từ input vô điều kiện.

## 18. Kế hoạch triển khai từng giai đoạn

**Giai đoạn 1 — baseline và dependency audit**

- Liệt kê actual Boot, Security, Java, Servlet container, browser, proxy, session store và DB.
- Chốt lựa chọn A/B/C và chính sách assurance theo nhóm user/action.
- Kiểm tra CVE ảnh hưởng, lên version đã vá; lưu bằng chứng dependency resolution.
- Xây positive/negative authorization matrix, rollout và rollback plan.

**Giai đoạn 2 — OTT độc lập**

- Thêm `oneTimeTokenLogin` và delivery handler gửi email test.
- Cấu hình public URL an toàn, account lookup, rate-limit, generic response.
- Chạy tests one-use/replay/expiry/cross-user/concurrency.
- Đổi in-memory sang JDBC/shared store đã vá nếu nhiều pods.
- Kiểm tra mail scanner, redirect/cookie, logs và session fixation.

**Giai đoạn 3 — passkey onboarding**

- Cấu hình `webAuthn` đúng version/dependencies, RP ID và allowed origins.
- Lưu credential user/credential vào persistent store, migration schema.
- Yêu cầu reauth để register credential mới, xác minh account binding.
- Browser test registration/assertion, thiết bị mới, platform vs cross-device authenticator.
- Kiểm tra UV REQUIRED + distributed session với bản vá.
- Có trang quản lý/gỡ passkeys và recovery an toàn.

**Giai đoạn 4 — enforce MFA/step-up**

- 7.x: global hoặc selective `AuthorizationManagerFactories`/`FactorGrantedAuthority`.
- 6.x: service-side verified factor evidence + AuthorizationManager riêng.
- Tối thiểu phân biệt anonymous, one factor, both factors, expired factor, revoked session.
- Thêm transaction binding, CSRF, audit và idempotency cho các lệnh nhạy cảm.
- Điều chỉnh UX khi factor còn thiếu; không tạo redirect loop.

**Giai đoạn 5 — canary và quan sát**

- Bật cho nhóm nội bộ/test trước, rồi rollout theo cohorts.
- Quan sát số login thành công/thất bại theo **nhóm cơ chế** (password/OTT/WebAuthn), lỗi challenge/state, support tickets, session failures.
- Dashboard tách password login vs OTT login vs passkey login vs MFA step-up.
- Không log raw tokens, secret, credential assertions có thể nhạy cảm.
- Giữ fallback recovery được kiểm soát, có admin runbook và audit.

## 19. Checklist trước production

- [ ] Actual version của Spring Boot/Security/Java đã xác minh và tương thích?
- [ ] Đã kiểm tra CVE-2026-22751 cho JDBC OTT và CVE-2026-47841 cho WebAuthn UV REQUIRED/distributed sessions?
- [ ] Bản OTT có `oneTimeTokenLogin` và delivery handler thật, không dựa vào default mail behavior?
- [ ] Token đủ entropy, TTL ngắn, account/purpose binding, one-use atomic trên mọi node?
- [ ] Không thể dùng lại token để tạo hai phiên qua requests đồng thời?
- [ ] Email sender chỉ gửi đến verified destination, không phản ánh tồn tại username?
- [ ] Magic link dùng HTTPS public origin và không bị lộ ở logs, Referer, analytics?
- [ ] GET link không consume token; POST verify giữ CSRF?
- [ ] Passkey dependencies đúng theo Security 6.5 hay 7.x, không trộn module?
- [ ] WebAuthn RP ID và allowedOrigins trùng site công khai, không dùng backend host?
- [ ] Registration chỉ thực hiện với user đã xác thực/step-up?
- [ ] Credential repositories có persistence bền vững, migrations và account foreign keys?
- [ ] Challenge/token được lưu và consume an toàn trong multi-instance?
- [ ] Signature, clientDataJSON challenge/origin, RP hash, UP/UV được library verify?
- [ ] UserVerification REQUIRED được enforced và đã test với distributed session bản vá?
- [ ] Gỡ credential/recovery không làm yếu assurance xuống dưới threat model?
- [ ] Nếu cần MFA, authorization rules thật sự đòi đủ factor đúng URL/action?
- [ ] Factor evidence do server tạo, bind đúng subject/session/action, có issuedAt/validDuration?
- [ ] Có kiểm tra role, resource ownership và idempotency **sau** MFA?
- [ ] Session/cookie/CSRF/logout/proxy headers được kiểm tra browser thật?
- [ ] MockMvc + DB concurrency + WebAuthn browser tests cùng chạy?
- [ ] Có rollout, monitoring, support playbook và rollback plan nếu user lockout?
- [ ] Không có secrets/PII/tokens/passkey assertion trong logs và metrics labels?

### Tài liệu chính thức và cập nhật bảo mật

- Spring Security 6.5 — One-Time Token Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html
- Spring Security 6.5 — Passkeys / WebAuthn: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html
- Spring Security 7.0 — Passkeys dependencies và JDBC: https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passkeys.html
- Spring Security 7.0 — MFA, FactorGrantedAuthority và authorization factory: https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/mfa.html
- Spring Security 7.1 — MFA conditional updates: https://docs.spring.io/spring-security/reference/7.1/servlet/authentication/mfa.html
- Spring Security 6.5 — Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — latest release documentation: https://docs.spring.io/spring-security/reference/
- Release ngày 23/10/2026 — Spring Security 7.0.8/7.1.2: https://spring.io/blog/2026/10/23/spring-security-maintenance-releases/
- Spring Security advisory **CVE-2026-22751** (JDBC OTT concurrent replay): https://spring.io/security/cve-2026-22751/
- Spring Security advisory **CVE-2026-47841** (WebAuthn UV + session serialization): https://spring.io/security/cve-2026-47841/
- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Multifactor Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html
- OWASP Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- W3C Web Authentication Level 3: https://www.w3.org/TR/webauthn-3/

**Kết luận:** “Triển khai OTT, passkey hoặc MFA” là ba bài toán giao nhau nhưng không trùng nhau. Với Spring Security 6.5, có thể dùng `oneTimeTokenLogin` và `webAuthn` đúng dependencies/patch nhưng không copy API MFA của 7.x. Với Spring Security 7.x, dùng `FactorGrantedAuthority`/`AuthorizationManagerFactories` để **ép** factor theo đường nhạy cảm, không chỉ bật giao diện. Đưa các bản vá OTT replay/WebAuthn UV vào tiêu chí phát hành, và chỉ kết luận thành công khi các tests one-use, WebAuthn cryptographic verification, factor freshness, multi-node state và authorization đều đạt.
