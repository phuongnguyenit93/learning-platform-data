# OTT, passkey và MFA: ca hết hạn, phát lại, thiếu yếu tố và khôi phục

> **Phạm vi bài học:** Spring Security – authentication, nhóm **Kiểm thử đăng nhập**. Nội dung tập trung vào **thiết kế, thực thi và diễn giải các ca kiểm thử bảo mật** cho One-Time Token (OTT/magic link), WebAuthn/passkey, MFA nhiều yếu tố, và phục hồi khi mất authenticator. Ví dụ sử dụng Java 17+, Spring Boot 3.x / Spring Security **6.5** trên Servlet stack; những API MFA tích hợp `FactorGrantedAuthority`/`@EnableMultiFactorAuthentication` thuộc **Spring Security 7.x**, không được trộn không kiểm chứng vào dự án Security 6.5.

## 1. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Phân biệt **OTT do server cấp**, **TOTP/HOTP do authenticator tạo**, **WebAuthn/passkey có chữ ký**, và **MFA policy**: tất cả có thể xuất hiện trong login nhưng không có cùng cách kiểm thử.
2. Thiết kế ca **hết hạn** theo đồng hồ có thể kiểm soát: trước thời hạn, đúng biên `expiresAt`, sau thời hạn và khi đồng hồ/cluster lệch.
3. Kiểm thử **replay** sau khi dùng một lần, hai request đồng thời, hai node, token cùng purpose khác user/tenant, link cũ khi đổi credential.
4. Kiểm thử WebAuthn **challenge, origin, RP ID, credential ownership, chữ ký, UP/UV, counter và registration**; không gọi một assertion giả là đã kiểm chứng crypto.
5. Kiểm thử MFA **thiếu yếu tố, sai loại yếu tố, sai tài khoản, đã cũ, bị thu hồi, step-up, fallback** và sự độc lập theo threat model.
6. Thiết kế **account recovery** khi mất khóa/passkey/thiết bị TOTP: backup codes một lần, second device, support workflow, re-enrollment, notification và session invalidation.
7. Phân lớp unit, component, integration và E2E, không nhầm `@WithMockUser`/`jwt()`/Mockito mocks với proof thật.
8. Viết một chương trình Java 17 chạy độc lập minh họa các quy tắc TTL, one-use, challenge/UV, MFA và recovery với stdout xác định.

## 2. Trước tiên, hiểu rõ bốn thuật ngữ

### 2.1. OTT là gì?

**One-Time Token (OTT)** trong Spring Security `oneTimeTokenLogin()` là secret do server phát cho một identity, gửi qua kênh như email hoặc SMS, rồi được nộp lại để xác thực theo flow được thiết kế. Không yêu cầu authenticator app đã enroll. Token cần **khó đoán, có thời hạn, dùng một lần** và không biến thành password reset/access token.

Đừng nhầm **One-Time Token** của Spring Security với **One-Time Password** kiểu TOTP/HOTP. TOTP app có secret đã đăng ký và tự tính mã theo thời gian; OTT thường được server tạo và phân phát.

### 2.2. Passkey/WebAuthn là gì?

Passkey là một WebAuthn credential sử dụng public-key cryptography. Authenticator giữ private key, server giữ public key, credential ID và thông tin owner. Khi login:

```text
Server tạo challenge ngẫu nhiên và lưu flow state
     │
     ▼
Browser navigator.credentials.get(...) cho RP ID
     │
     ▼
Authenticator ký dữ liệu assertion, có flags UP/UV
     │
     ▼
Server verify chữ ký + challenge + origin + RP ID +
credential ownership + policy flags + flow/session
     │
     ▼
Tạo Authentication khi mọi điều kiện thỏa
```

**Passkey không phải OTT**, dù cả hai có một giá trị một lần (challenge/nonce). OTT dùng secret bearer được trình cho server; WebAuthn gửi **assertion có chữ ký trên challenge** ràng buộc với origin và relying party.

### 2.3. MFA và “hai bước” khác nhau

MFA cần nhiều **loại yếu tố** độc lập hoặc một authenticator đa yếu tố đúng tiêu chuẩn và policy. Hai bước không đồng nghĩa hai yếu tố: password + PIN vẫn là hai yếu tố knowledge cùng loại. Password + passkey sở hữu khóa có thể đáp ứng hai loại; passkey có **user verification (UV)** qua PIN/biometric nội bộ có thể là một authenticator đa yếu tố tùy assurance/policy. Password + email OTT trông như hai bước nhưng không thể mặc nhiên coi là MFA mạnh; NIST SP 800-63B-4 **không cho dùng email như out-of-band authenticator** trong bảo đảm chuẩn của tài liệu đó.

**Thận trọng với Spring Security 7:** sự xuất hiện của `FACTOR_PASSWORD` và `FACTOR_OTT` trong `Authentication` giúp thực thi yêu cầu cơ chế, nhưng **không chứng minh** OTT được gửi qua một kênh độc lập đủ mạnh hoặc đáp ứng một cấp NIST AAL cụ thể.

### 2.4. Recovery không phải “bỏ qua MFA”

Recovery là con đường dành cho người mất quyền điều khiển authenticator; nó có thể là **đường tấn công dễ hơn login bình thường**. Một chính sách mạnh phải quy định ai được phục hồi, bằng chứng nào bắt buộc, ai có quyền approve, có thể re-enroll factor nào, có tạo session không, có cần trì hoãn hay giảm quyền tạm thời, và làm sao thu hồi thiết bị cũ.

Mục tiêu test không phải “luôn cho user vào được”, mà là **khôi phục hợp pháp mà không cho attacker đi vòng qua MFA**.

## 3. Ma trận tổng quan: điều gì phải được chứng minh?

| Cơ chế | Dữ liệu có hạn | Cần one-use? | Kiểm chứng trọng tâm | Khôi phục |
|---|---|---|---|---|
| OTT/magic link | Token có `expiresAt`/TTL | Có: một secret không được login hai lần | Token đúng owner, purpose, TTL, atomic consume, email delivery | Phát OTT mới theo rate limit; không revive token cũ |
| TOTP/HOTP | TOTP time step / HOTP counter | Chống replay theo accepted step/counter | Seed gắn account, window, attempt limit, không nhận lại mã đã dùng | Backup codes, second authenticator, recovery policy |
| WebAuthn/passkey | Challenge + ceremony options có timeout | Assertion phải gắn challenge mới; replay challenge cũ bị chặn | Chữ ký public key, challenge, origin, RP ID, userHandle/credential, UP/UV | Passkey dự phòng/synced credential có policy, recovery |
| MFA policy | Freshness của các bằng chứng | Challenge/step-up không replay | Đủ factor đúng loại, user, session, purpose và mới; thiếu factor bị chặn | Phục hồi không silently “MFA complete” |
| Backup/recovery code | TTL nếu policy yêu cầu | Mỗi code một lần | Hash/entropy, owner, rate limit, atomic consume | Sau thành công buộc re-enroll, thông báo và revoke thích hợp |

**Không nhầm “assert 200 OK” với bằng chứng đầy đủ**. Response 200 chỉ có giá trị khi test thật sự đi qua verifier, authorization policy và persistence tương ứng. Test đã inject một authenticated principal có thể thành công mà không kiểm tra secret/chữ ký/second factor.

## 4. Quy trình kiểm thử theo tầng

```text
                    E2E / browser / virtual authenticator
                                   ▲
                 HTTP integration: filters + DB + CSRF +
                 authenticators/IdP + session + proxy
                                   ▲
                 Component: OTT store, WebAuthn verifier,
                 MFA policy, recovery service
                                   ▲
                 Unit: Clock, expiry, state machine,
                 race-safe compare-and-set, authorization
```

Mỗi tầng có câu hỏi riêng:

- **Unit**: `now == expiresAt` có bị từ chối? Token đã consumed bị chặn? Thiếu `PASSKEY` mà mới có `PASSWORD` có bị từ chối? Backup code cùng user nhưng chưa có recovery assurance có bị chặn?
- **Component**: service dùng shared DB transaction/Redis atomic? OTP verifier có lưu time-step chống replay? Recovery binding có đúng account?
- **HTTP integration**: `POST /ott/generate`, `GET /login/ott`, `POST /login/ott` và WebAuthn endpoints thực sự đi qua Spring filters, CSRF, handlers, session strategy?
- **Crypto integration**: ký WebAuthn assertion thật bằng authenticator thử nghiệm/virtual authenticator; verify origin/RP/challenge/chữ ký/flags và dữ liệu registration có thực.
- **E2E**: browser/WebAuthn platform API, email scanners/link rewriting, cross-device, cookie, TLS/proxy, account recovery và thông báo.

Đừng dùng `@WithMockUser`, `user()`, `jwt()` hoặc một flag `signatureValid=true` do test tự đặt để tự kết luận rằng **cryptographic verification production đã an toàn**. Fixture giả có thể thích hợp để test policy trong isolation; phải có test thật ở các lớp khác.

## 5. Kiểm thử thời hạn: không dùng Thread.sleep()

### 5.1. Thiết kế biên thời gian

Với quy tắc TTL chuẩn của một secret:

```text
issuedAt = 2026-11-01T09:00:00Z
expiresAt = 2026-11-01T09:05:00Z
```

Giả sử hệ thống chọn **`now.isBefore(expiresAt)` là hợp lệ**, test phải gồm:

| Thời điểm kiểm tra | Kỳ vọng |
|---|---|
| `09:00:00Z` | Còn hạn nếu đã phát hành hoàn tất |
| `09:04:59.999Z` | Còn hạn |
| `09:05:00Z` | **Hết hạn** tại đúng biên |
| `09:05:00.001Z` | Hết hạn |
| Trước `issuedAt` do clock đi lùi | Xử lý nhất quán theo policy và dữ liệu phát hành |
| Máy A phát, máy B kiểm (clock drift) | Không vô tình chấp nhận token quá hạn hoặc chặn quá sớm ngoài drift budget |

Nếu framework/store dùng so sánh khác thì **test theo hợp đồng hiện thực cụ thể**, không áp một giả định thời gian cho tất cả authenticator.

### 5.2. Inject Clock trong logic nghiệp vụ

Với Java:

```java
Clock fixed = Clock.fixed(
    Instant.parse("2026-11-01T09:05:00Z"), ZoneOffset.UTC);
Instant now = fixed.instant();
boolean valid = now.isBefore(expiresAt);
```

`Clock.fixed` giúp kiểm tra biên tức thời, không đợi phút hay phụ thuộc CPU/CI. Khi code production lấy thẳng `Instant.now()` ở nhiều vị trí, khó tạo test xác định và có thể xảy ra race vì các lần đọc clock khác nhau.

Trong service dùng Spring, có thể khai:

```java
@Bean
Clock clock() {
    return Clock.systemUTC();
}
```

Test có thể cung cấp bean `Clock.fixed(...)` riêng qua `@TestConfiguration` hoặc injection constructor. Không thay clock production bằng fixed clock trong runtime bình thường.

### 5.3. Nơi kiểm tra expiry

- OTT: trong **server-side `OneTimeTokenService.consume`** hoặc store được nó gọi, không chỉ disable nút login trên frontend.
- TOTP: trong bước kiểm chứng time-step/window và trạng thái replay; server không tin thời gian do client tự gửi.
- WebAuthn: challenge/options state có TTL do relying party/server quản lý; timeout client UI không tự chứng minh challenge đã bị từ chối ở backend.
- MFA: `verifiedAt`/`auth_time`/`issuedAt` của factor từ verifier tin cậy phải còn mới theo policy của endpoint; không dùng `now` từ browser.
- Backup code: code có thể có chính sách sống lâu tới khi được dùng, nhưng phải **single-use** và bảo vệ enrollment/rotation; không bịa yêu cầu TTL cố định nếu sản phẩm không có.

### 5.4. Đừng chỉ làm assert “hết hạn sau 6 phút”

Test:

```java
Thread.sleep(360_000);
assertThat(service.consume(token)).isFalse();
```

có vấn đề: chậm, flaky, lệ thuộc scheduler và clock, bỏ sót biên, dễ khiến CI chạy lâu. Thay bằng fake clock hoặc tạo token/store fixture có `expiresAt` chính xác và **kiểm tra 3 thời điểm**: trước, tại, sau hạn. Nếu chỉ test service không kiểm soát thời gian được, mở rộng kiến trúc test seam thay vì ngủ.

## 6. OTT: flow Spring Security 6.5 và các điểm test

Tài liệu Spring Security 6.5 có `oneTimeTokenLogin()`. Luồng cơ bản:

```text
POST /ott/generate     username, CSRF và rate limit thích hợp
     │
     ├── OneTimeTokenService.generate(...)
     ├── OneTimeTokenGenerationSuccessHandler gửi link qua email/SMS
     └── response UI trung tính
              │
              ▼
GET /login/ott?token=...     trang nộp OTT
              │             không nên tự consume trên GET
              ▼
POST /login/ott              token + CSRF
     │
     └── OneTimeTokenService.consume(...)
               ├── invalid/expired/used -> failure
               └── hợp lệ -> Authentication/session theo config
```

Mặc định `OneTimeTokenService` là `InMemoryOneTimeTokenService`; production nhiều node nên có shared store, có thể `JdbcOneTimeTokenService` hoặc implementation riêng. TTL mặc định do `GenerateOneTimeTokenRequestResolver` trong Spring Security 6.5 là khoảng **5 phút**, có thể tùy biến.

**Lưu ý phiên bản:** Spring Security 6.5 passkeys dùng `webauthn4j-core` cùng `spring-security-web`; dòng Spring Security 7.x có artifact `spring-security-webauthn` riêng. Không trộn tọa độ dependency giữa phiên bản.

### 6.1. Spring Security configuration

File `src/main/java/example/security/OttAndPasskeySecurity.java` trong dự án Spring Boot 3.x/Spring Security 6.5:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OttAndPasskeySecurity {

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            MagicLinkDeliveryHandler handler)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/login/ott",
                    "/ott/sent", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(ott -> ott
                .tokenGenerationSuccessHandler(handler))
            .webAuthn(wa -> wa
                .rpId("example.org")
                .allowedOrigins("https://login.example.org"));

        return http.build();
    }
}
```

`MagicLinkDeliveryHandler` trong mã là **bean do ứng dụng triển khai** thuộc interface `OneTimeTokenGenerationSuccessHandler`; snippet này không phải project hoàn chỉnh nếu chưa có handler/email service, `UserDetailsService`/account store, WebAuthn repositories và WebAuthn4J dependency. Nó minh họa cấu hình để test đủ ba cách login; không dùng một class cấu hình thiếu dependencies rồi tuyên bố bài test E2E đã hoạt động.

Ở production, public magic-link origin phải lấy từ **cấu hình đáng tin** (canonical HTTPS), không ghép từ inbound `Host`/`X-Forwarded-Host`; email tới recovery contact đã verified, không tự phản chiếu email/redirect do requester gửi.

### 6.2. Cấu hình TTL với resolver (6.5)

Nếu muốn test TTL 10 phút thay vì mặc định, Spring Security 6.5 cho phép tạo `GenerateOneTimeTokenRequestResolver` bean:

```java
@Bean
GenerateOneTimeTokenRequestResolver ottRequestResolver() {
    DefaultGenerateOneTimeTokenRequestResolver delegate =
        new DefaultGenerateOneTimeTokenRequestResolver();

    return request -> {
        GenerateOneTimeTokenRequest req = delegate.resolve(request);
        return new GenerateOneTimeTokenRequest(
            req.getUsername(), Duration.ofMinutes(10));
    };
}
```

**Đây là snippet bên trong class Spring `@Configuration`**, cần các imports của `org.springframework.security.authentication.ott.GenerateOneTimeTokenRequest`, `org.springframework.security.web.authentication.ott.GenerateOneTimeTokenRequestResolver`, `DefaultGenerateOneTimeTokenRequestResolver` và `java.time.Duration`; xác nhận packages/API bằng Javadoc của đúng bản Spring Security đang dùng. Nguyên tắc test không đổi: thời hạn được enforce ở **token service**, không phải client.

### 6.3. Ma trận OTT hết hạn

| Case | Thiết lập | Kỳ vọng |
|---|---|---|
| Token hợp lệ còn hạn | `now < expiresAt`, chưa consumed, đúng user | Chấp nhận một lần |
| Token đúng tại `expiresAt` | Clock đúng ranh giới | Bị từ chối theo policy `now < expiresAt` |
| Token sau `expiresAt` | Clock vượt hạn |  Không login, không tạo session |
| Token sai | Thay 1 ký tự | Không login; phản hồi trung tính |
| Token không tồn tại | Store lookup miss | Không login/không tiết lộ username |
| Token đã dùng | Dùng lại sau success | Không login lần hai |
| Token đã revoke | Account khóa, revoke/reset | Không được chấp nhận |
| Token đúng nhưng owner khác | Thử gắn user của request khác | Không chuyển Authentication sang người khác |
| Token đúng nhưng sai purpose | Token `PASSWORD_RESET` nộp vào OTT login | Bị từ chối |
| Token phát cho tenant A | Nộp tại tenant B | Bị từ chối theo tenant binding |
| 2 token phát trước khi đổi credential | Password/MFA enrollment thay đổi | Token cũ bị thu hồi theo version policy |
| GET do mail scanner mở trước user | Không POST/không consume | User thật vẫn có thể nộp token |
| Thiếu CSRF trên form POST | Spring session CSRF bật | Request bị chặn theo config |

**Không thay đổi account ở GET** chỉ vì email scanner truy cập magic link. Nếu custom UI tự submit POST ngay khi tải trang, scanner/bot có thể tiêu thụ OTT. Trên trang chứa token cần giảm referrer leak, log redaction, không tải analytics bên thứ ba và loại bỏ token khỏi URL sau khi hoàn tất.

### 6.4. OTT replay: hai request cùng lúc

**Sai:**

```text
SELECT token WHERE used=false
if found:
    grantSession()
    UPDATE token SET used=true
```

Hai request trên hai nodes có thể cùng thấy `used=false` trước khi một bên cập nhật. Trong database PostgreSQL, nên có một câu lệnh consume nguyên tử:

```sql
UPDATE ott_tokens
SET consumed_at = now()
WHERE token_hash = :digest
  AND purpose = 'LOGIN_OTT'
  AND consumed_at IS NULL
  AND expires_at > now()
RETURNING user_id;
```

Đây là **schema/SQL minh họa cho custom store**; Spring `JdbcOneTimeTokenService` có schema/queries riêng, không copy bảng này rồi giả định Spring sẽ tự dùng. Kiểm chứng user vẫn active, account/tenant policy, sessions và transaction semantics. Test phải chứng minh **số request được chấp nhận ≤ 1** khi cùng credential bị gửi đồng thời.

Một test dùng một JVM với `AtomicBoolean.compareAndSet(false,true)` chỉ chứng minh in-memory concurrency; production cluster cần kiểm thử với shared database/Redis atomic operation. Không kết luận toàn cụm an toàn từ một unit test in-memory.

### 6.5. Test thật Spring OTT qua HTTP

Với `@SpringBootTest` + `@AutoConfigureMockMvc(addFilters=true)`, test một flow thực phải làm:

1. Cấp OTT qua `POST /ott/generate` có CSRF theo cấu hình.
2. Dùng test mail sink hoặc `OneTimeTokenGenerationSuccessHandler` spy/controlled sink để nhận **raw token** trong môi trường test; không ghi token vào CI logs.
3. Kiểm tra `GET /login/ott?token=...` không làm login thành công/tiêu thụ token.
4. Gửi `POST /login/ott` với token và CSRF, assert Authentication/session thành công nếu token hợp lệ.
5. Gửi lại cùng token bằng **fresh session** hoặc client thứ hai, assert không có Authentication; không để session đã login của lần thứ nhất làm kết quả replay test sai.
6. Cấp một token khác có `expiresAt` được đặt trước thời điểm kiểm bằng test clock/store; assert failure.
7. Thử token của user đã disable, reset password hoặc bị xóa factor; kiểm policy account lifecycle.
8. Quan sát lại storage để xác nhận consumed status; không chỉ status HTTP.

### 6.6. MockMvc snippets không thay cho test expiration

Các dòng sau là **mảnh mã trong một test Spring Boot có `MockMvc mvc`, token thực và CSRF đang bật**:

```java
mvc.perform(get("/login/ott").param("token", issuedToken))
   .andExpect(status().isOk());

// Token dùng một lần phải đi vào endpoint login xử lý bằng POST.
mvc.perform(post("/login/ott")
        .param("token", issuedToken)
        .with(csrf()))
   .andExpect(authenticated().withUsername("lan"));
```

Các static imports tương ứng cần được thêm trong test class:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
```

**Cảnh báo:** snippet không cố gắng chạy độc lập. Tùy view/default handler, `GET /login/ott` có thể trả 200 template hoặc status khác; test phải đồng nhất cấu hình custom submit page. Nó **không** tự tạo issuedToken, mail sink, `OneTimeTokenService` hay `UserDetailsService`. Và nếu test chỉ dùng `@WithMockUser`, nó **không kiểm chứng token đã được tiêu thụ**.

## 7. Passkey/WebAuthn: đừng chỉ test “login button thành công”

WebAuthn có hai nhóm ceremony tách biệt:

1. **Registration**: app tạo credential creation options/challenge; authenticator tạo credential; server xác minh attestation/registration policy và gắn credential với user.
2. **Authentication**: app phát assertion request options/challenge; authenticator ký assertion; server verify và hoàn tất login.

Trong Spring Security 6.5, các endpoint mẫu ở tài liệu:

```text
POST /webauthn/register/options  (+ CSRF; user đăng nhập)
POST /webauthn/register          (+ CSRF; credential result)
POST /webauthn/authenticate/options (+ CSRF; tạo challenge)
POST /login/webauthn             (+ CSRF; gửi assertion)
```

Đây là **đường mặc định theo tài liệu Spring Security 6.5**, có thể thay đổi bởi app và version. Chúng không phải API “login bằng token” giống OTT.

### 7.1. Phải kiểm gì trong một assertion?

| Thuộc tính | Vì sao quan trọng | Negative test |
|---|---|---|
| Challenge | Chống replay; liên kết assertion với lần xác thực hiện tại | Dùng challenge cũ, của phiên khác, hết hạn, đã consumed |
| `clientDataJSON.type` | Phải đúng `webauthn.get` cho authentication | Thay bằng `webauthn.create` |
| `clientDataJSON.origin` | Chống phishing site khác origin | `https://evil.example` thay vì allowed origin |
| RP ID hash trong `authenticatorData` | Khóa credential vào relying party ID | Assertion được tạo cho RP khác |
| Credential ID | Chọn public key đã đăng ký, đúng user/tenant | Credential của user B nộp cho user A |
| Chữ ký | Chứng minh private key tương ứng | Sửa 1 byte `signature` hoặc `clientDataJSON` |
| UP flag | Authenticator có user presence theo policy | UP=false |
| UV flag | User verification khi policy yêu cầu | UV=false dù request yêu cầu UV=required |
| `userHandle` | Liên kết resident/discoverable credential với đúng account | Mismatch user handle |
| Signature counter | Tín hiệu phát hiện bất thường/clone trên device supporting counter | Counter regression theo policy, xem nuancing bên dưới |
| Challenge TTL/one-use | Loại assertion cũ và races | Replay assertion sau success, concurrent submits |
| Attestation/trust policy (registration) | Ràng buộc thiết bị khi enterprise yêu cầu | Attestation chưa tin, format không hợp lệ |

**Không lấy `origin` hoặc `rpId` từ request body do attacker đưa vào để làm allowlist**. Hai giá trị này phải được xác định bởi relying party/server config tin cậy; browser và authenticator cung cấp dữ liệu để **server so sánh**, không phải để tự định nghĩa expected value.

### 7.2. UP vs UV và passkey multi-factor

- **UP** = user presence, ví dụ thao tác với authenticator.
- **UV** = user verification, ví dụ PIN/biometric do authenticator thực hiện và được thể hiện trong signed authenticator data.
- Nếu endpoint chính sách yêu cầu xác minh người dùng qua passkey, test assertion chỉ có UP nhưng UV=false **phải bị từ chối theo policy**, ngay cả khi chữ ký đúng.
- Một passkey có thể là **multi-factor cryptographic authenticator** khi user verification được yêu cầu/đáp ứng theo assurance; không nên giả định mọi WebAuthn response chỉ cần chữ ký là đạt mức MFA mong muốn.

**Lưu ý:** `navigator.credentials.get()` có thể trả promise thất bại khi user cancel, thiết bị không có credential, platform không hỗ trợ, timeout hoặc bị policy browser chặn. UI cần xử lý các trường hợp đó mà **không tự bật fallback yếu** hoặc gửi credential lên server bằng cách “skip verification”.

### 7.3. Sign counter: không đưa quy tắc sai vào test

Một số authenticators báo `signCount` tăng dần; việc counter lùi hoặc không tăng khi trước đó tăng có thể là **tín hiệu** credential bị clone hay bất thường. Nhưng **synced passkeys**/nhiều thiết bị có thể có counter bằng 0 hoặc hành vi khác; không đặt test “mọi counter = 0 đều bị từ chối” rồi kết luận WebAuthn đã an toàn. Theo WebAuthn và thư viện verifier, counter policy phải phù hợp authenticator/credential type, lưu state đúng và xử lý rủi ro có giải thích/audit. Replay protection chính vẫn phải dựa vào **fresh challenge và chữ ký**, không chỉ counter.

### 7.4. Challenge expiry và replay

Nếu challenge `c1` được phát cho session A:

```text
POST /webauthn/authenticate/options
 → challenge=c1, session=A, expiresAt=t1
 → navigator.credentials.get(...) tạo assertion S1
 → POST /login/webauthn S1 (đúng signature/challenge) → success
 → POST /login/webauthn S1 lần nữa → reject replay
 → POST /login/webauthn S1 tại session B → reject binding
 → POST /login/webauthn với S1 sau t1 → reject expired
```

Cần test ở ranh giới `now < t1` và `now == t1` nếu ứng dụng công bố policy đó. Các options/challenge được lưu trong HTTP session hoặc shared store tùy cấu hình; test multi-node với session replication/load balancer thật nếu production dùng nhiều node.

**Không sinh lại challenge trùng** hoặc tái sử dụng challenge cũ của một ceremony khác. Và khi tạo challenge mới, không tự làm bất kỳ assertion cũ nào hợp lệ chỉ vì user vẫn đăng nhập.

### 7.5. Registration tests riêng

- Anonymous hoặc user không đủ assurance gọi `POST /webauthn/register/options`: bị từ chối theo policy.
- User A cố đăng ký credential cho user B: phải từ chối, dù `user.name` trong JSON đã bị đổi.
- Hai user cố liên kết cùng credential ID: phải bảo đảm không có cross-account takeover.
- Nếu security key đã bị revoked, không cho assert login với key đó; kiểm tra credential repository thực.
- Tạo credential mới trong lúc user yêu cầu “lost key” phải theo recovery policy, không chỉ dựa vào session cũ yếu.
- Với enterprise attestation policy, test ký đúng nhưng attestation không được tin cũng bị từ chối nếu chính sách đòi.
- Duplicate registration, concurrent enrollment và rollback lỗi persistence phải không tạo credential “nửa lưu” hoặc đẩy owner sang account khác.
- Audit các thay đổi credential và thông báo kênh đăng ký cũ.

### 7.6. Kiểm thử WebAuthn ký thật cần công cụ phù hợp

Một mock assertion với `signatureValid=true` chỉ test business gating. Kiểm thử thực chữ ký phải dùng **virtual authenticator** của trình duyệt (ví dụ WebDriver/Chrome DevTools WebAuthn domain), hardware authenticator trong môi trường lab hoặc thư viện fixture ký test assertion bằng key giả và chạy **real WebAuthn verifier**.

Bài test phải sửa đúng từng byte theo nhóm lỗi:
- Public key không khớp signature;
- Challenge đúng format nhưng không thuộc session;
- Chữ ký hợp lệ của RP khác;
- Origin là subdomain khác hoặc HTTP origin trái phép;
- UP/UV flags thiếu;
- UserHandle không khớp owner;
- Authenticator credential đã bị revoke;
- Attestation bị từ chối theo enterprise policy.

**Đừng mock `UserCredentialRepository` trả về key của bất kỳ user nào khi muốn chứng minh ownership.** Có thể unit-test mapper bằng mock, nhưng cần integration với repository thật/fixture để kiểm cross-user.

## 8. MFA: kiểm thử thiếu yếu tố, sai yếu tố và step-up

### 8.1. Hai lần đăng nhập không tự là MFA

Ví dụ những bằng chứng:

```text
Password            → KNOWLEDGE
PIN gửi lên server   → KNOWLEDGE
TOTP app secret      → POSSESSION (phụ thuộc policy và storage)
FIDO2 security key   → POSSESSION, WebAuthn phishing-resistant
WebAuthn UV          → activation/user verification bên trong authenticator
Email link OTT       → channel-based proof, không tự coi đạt AAL2
CAPTCHA/IP/location  → risk signals, không phải factor riêng
```

Test phải phân biệt **số lần xác minh** với **loại/độc lập yếu tố**. Với password + PIN: hai bước đều đúng nhưng **không đạt** policy yêu cầu knowledge + possession. Với OTT gửi tới cùng mailbox được mở bởi cùng password, đánh giá khả năng compromise cùng lúc; NIST 800-63B-4 không chấp nhận email là OOB authenticator cho assurance chuẩn đó.

### 8.2. Mô hình trạng thái yêu cầu MFA

```text
ANONYMOUS
    │ chứng minh password
    ▼
PRIMARY_VERIFIED / MFA_PENDING
    │ pending session + challenge gắn user/session/purpose
    │ chưa có quyền sensitive
    ├─ timeout/attempt exhausted/revoked → FAIL
    ├─ sai account/other session/other factor → FAIL
    └─ factor độc lập verified và còn mới
            ▼
       MFA_COMPLETE
            │  rotate session ID/cập nhật assurance thật
            ▼
       AUTHORIZATION đối với resource/tenant/role
```

**Quan trọng:** Một `Authentication.isAuthenticated() == true` sau password không tự chứng minh đã đủ MFA. Các route rủi ro cao phải kiểm thêm factor requirements/freshness; không chỉ `authenticated()`. Dù MFA đã pass, vẫn cần kiểm `ROLE_ADMIN`/scope/tenant/ownership.

### 8.3. Ma trận thiếu yếu tố

| Yếu tố đã được xác minh | Endpoint cần | Kỳ vọng |
|---|---|---|
| Không có gì | Password + passkey | Yêu cầu xác thực, không vào resource |
| Chỉ password | Password + passkey | Chặn/đưa tới passkey challenge phù hợp |
| Chỉ passkey (khi policy đòi hai factors cụ thể) | Password + passkey | Chặn/đưa tới bước password |
| Password + PIN | Knowledge + possession | Không đạt vì không có possession |
| Password + TOTP hợp lệ của user khác | Cùng user phải đủ 2 factors | Từ chối |
| Password + passkey UV=false | Policy passkey UV required | Từ chối |
| Password + passkey UV=true, đúng user, còn mới | Password + WebAuthn (theo policy) | Có thể đạt, sau đó check role/resource |
| Password + passkey đã revoke | Đòi passkey hiện hành | Không đạt |
| Password xác minh hôm qua + passkey mới | Policy “both factors fresh” trong 5 phút | Không đạt do password cũ |
| Two factors của đúng user nhưng ở khác session không ràng buộc | Một login flow | Không được ghép |
| Two factors hợp lệ nhưng account suspended | Account phải active | Vẫn không cho truy cập |
| Recovery code đã dùng một lần | Step-up mới | Không coi thành factor chính mới |

### 8.4. MFA hỗ trợ framework theo phiên bản

- **Spring Security 6.x:** đã có form login, OTT và WebAuthn/passkeys; để buộc **cả hai cơ chế** theo policy, ứng dụng cần thiết kế phù hợp bằng state machine, custom authorization manager, IdP/SSO assurance hoặc một giải pháp MFA khác. Không coi việc bật đồng thời `formLogin()` + `oneTimeTokenLogin()` + `webAuthn()` là **tự động bắt buộc ba bước**: chúng có thể là **các cách đăng nhập thay thế nhau**.
- **Spring Security 7.x:** có `FactorGrantedAuthority` và `@EnableMultiFactorAuthentication` để yêu cầu các authorities như `FACTOR_PASSWORD`, `FACTOR_OTT`, `FACTOR_WEBAUTHN`. Đây là chính sách thực thi cơ chế, nhưng nội dung channel/binding, independence và recovery vẫn cần review riêng.

Ví dụ minh họa **Spring Security 7.x** (không copy vào 6.x):

```java
@EnableMultiFactorAuthentication(authorities = {
    FactorGrantedAuthority.PASSWORD_AUTHORITY,
    FactorGrantedAuthority.WEBAUTHN_AUTHORITY
})
public class StrongMfaConfig {
    // SecurityFilterChain cấu hình formLogin và webAuthn
    // cùng các repositories, challenge và account policy.
}
```

Đoạn là **snippet API**, cần imports `org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication` và `org.springframework.security.core.authority.FactorGrantedAuthority` trong Spring Security 7.x. Nó không phải một app đầy đủ. Test cần xác nhận thiếu `FACTOR_WEBAUTHN` bị chặn, đã pass password không được tự cấp factor khác, và self-supplied authorities từ client không được tin.

### 8.5. Freshness và step-up theo hành động

Đối với `POST /payment/transfer` hoặc `POST /account/security/webauthn/register`, có thể yêu cầu MFA mới xác minh trong **5 phút** (con số ví dụ do sản phẩm định nghĩa, không phải mặc định NIST). Test:

- Đã MFA từ 8 giờ trước, session còn sống → yêu cầu step-up.
- Step-up ngay trước giao dịch với challenge gắn phiên → cho phép khi đủ permission.
- Password ở session A và passkey ở session B → không cộng gộp.
- Admin role bị revoke sau khi step-up → authorization vẫn chặn.
- Giao dịch đã đổi số tiền/đích người nhận sau khi bước xác nhận → từ chối nếu có transaction binding.
- IdP claim `acr`/`amr`/`auth_time` tự gửi từ frontend → không chấp nhận; phải là signed/trusted claim theo hợp đồng issuer.

## 9. Khôi phục: yếu tố yếu nhất quyết định khả năng bị chiếm tài khoản

Người dùng mất security key/điện thoại TOTP hoặc không thể mở passkey. Recovery phải tạo một **chứng cứ tin cậy khác**, không đơn giản chuyển tất cả sang `ROLE_USER` sau khi click “I lost my key”.

```text
Mất authenticator
    │
    ▼
Yêu cầu recovery (rate-limit + generic response)
    │
    ▼
Kiểm recovery eligibility, factor còn sống,
 backup codes, identity proofing/hỗ trợ theo risk policy
    │
    ▼
Tạo recovery intent có TTL + owner/session/purpose
    │
    ├─ bằng chứng yếu, sai owner, replay → DENY
    │
    └─ đủ bằng chứng và approval → RESTRICTED RECOVERY
                                  │
                           re-enroll authenticator
                                  │
                  invalidate lost factor + stale sessions
                                  │
                    notification, audit, delay policy
                                  │
                    login/step-up theo chính sách mới
```

### 9.1. Bằng chứng recovery hợp lệ không có nghĩa tự động MFA complete

Backup code dùng một lần có thể là **recovery credential**, nhưng không được mặc định thay thế mọi factor hoặc cấp mọi quyền ngay khi nộp code. Quy trình phải xác định code được phép khôi phục **thao tác gì**: liên kết authenticator mới, tạm giới hạn quyền, đổi password hay đăng nhập; từng bước có scope và freshness rõ.

Nếu NIST assurance cao cần trình tự recovery mạnh, không dùng email OTP như authenticator OOB đạt chuẩn chỉ vì nó thuận tiện. Email có thể dùng **thông báo, xác minh contact hoặc một bước của workflow** theo policy khác, không tự chứng minh MFA đạt AAL.

### 9.2. Backup codes: ca bắt buộc

| Tình huống | Kỳ vọng |
|---|---|
| Cấp backup codes | CSPRNG đủ entropy, hiển thị một lần, lưu hash, gắn account |
| Mã đúng, chưa dùng | Có thể hoàn thành đúng recovery action được phép |
| Mã sai | Không làm đổi trạng thái account; giới hạn lần thử |
| Mã đã dùng | Từ chối lần hai |
| Hai request đồng thời cùng code | Tối đa một thành công trên shared store |
| Backup code user B nộp cho user A | Từ chối |
| Mã dùng cho password reset được nộp để tắt MFA | Từ chối sai purpose |
| Mã cũ sau reset/rotate codes | Bị thu hồi |
| Actor thiếu session/identity proof theo policy | Không cấp recovery chỉ từ một cờ client |
| Account disabled/admin-locked | Không tự mở account do recovery code |
| Recovery thành công | Audit, notice, revoke/mark lost device, lifecycle rõ |
| Mất tất cả codes | Đi tới workflow support/identity proofing, không skip MFA |

**Atomic single use:** database query tương tự OTT nhưng với `purpose=ACCOUNT_RECOVERY`, `account_id`, `consumed_at IS NULL`. Mỗi code được kiểm tra đúng chủ; việc đổi/re-enroll authenticator cần nằm trong transaction/rollback được thiết kế để tránh code đã mất nhưng recovery chưa hoàn tất.

### 9.3. Re-enrollment và account takeover

Tấn công phổ biến: attacker biết password hoặc chiếm session cũ, vào “Thêm passkey” rồi đăng ký authenticator của chính mình. Vì thế:

1. Yêu cầu reauthentication/step-up đúng assurance cho **enrollment/replace/remove**.
2. Challenge đăng ký WebAuthn mới gắn **đúng local account ID, session, RP ID và purpose**; không cho attacker sửa `user.id` hoặc `user.name` để chiếm account khác.
3. Không chấp nhận credential đã được gắn user khác nếu sản phẩm cấm.
4. Nếu user thật mất yếu tố cuối cùng, áp dụng recovery intent có giới hạn, không yêu cầu old key bất khả thi nhưng cũng không “skip”.
5. Sau recovery, thông báo contact cũ, ghi audit, có thể chờ cooling-off/giới hạn tác vụ tài chính cho account rủi ro cao.
6. Thu hồi/đánh dấu lost credentials, đổi credential/session versions; phát kiểm tra phiên cũ cho mọi node.
7. Không để helpdesk tự reset MFA chỉ dựa vào một email/request không có bằng chứng hoặc approval.
8. Test idempotency: retry cùng event không đăng ký hai credentials hoặc hoàn tác chính sách revocation.

### 9.4. Khôi phục passkey đồng bộ (synced passkey)

Synced passkey có thể được khôi phục qua cơ chế đồng bộ của platform/provider. Đây là **vòng đời authenticator do hệ sinh thái quản lý**, khác với server-side account recovery. Khi người dùng có passkey đồng bộ trên thiết bị khác, một phép login WebAuthn hợp lệ vẫn phải có challenge/origin/RP ID/chữ ký/UV đúng policy. Đừng “khôi phục” bằng cách cấp API token cho người tự khai “passkey đã sync”.

Test cross-device cần thể hiện đúng UI/hybrid transport, thời gian, user presence/verification và trường hợp không có thiết bị, thay vì chỉ mock user principal.

## 10. Java 17 độc lập: tái hiện expiry, replay, thiếu factor và recovery

Chương trình này dùng JDK 17, không cần Spring. Nó mô phỏng **quyết định chính sách** với một token store in-memory có `AtomicBoolean`, WebAuthn assertion **đã được verifier khác kiểm tra** và một recovery gate. Trọng tâm là kết quả test xác định bằng `Instant` cố định; không mô phỏng chữ ký WebAuthn thật, không tạo email và không cấp session.

**Ranh giới an toàn:** `signatureVerified`/`originValid`/`rpIdValid` trong ví dụ **chỉ là giả định do test đặt**, tuyệt đối không nhận các boolean đó từ browser làm kết quả xác thực production. Chuỗi secret cố định chỉ là fixtures cho stdout, **không có entropy**; production dùng CSPRNG, lưu hash, TTL và transaction.

Lưu file `AuthExpiryReplayRecoveryDemo.java`:

```java
import java.time.Instant;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

public class AuthExpiryReplayRecoveryDemo {

    enum Factor { PASSWORD, PASSKEY, OTT }

    record Ticket(
        String owner, String purpose,
        Instant expiresAt, AtomicBoolean used) {}

    static final class OneTimeStore {
        private final Map<String, Ticket> tickets =
            new ConcurrentHashMap<>();

        void issue(String key, String owner,
                   String purpose, Instant expiry) {
            tickets.put(key, new Ticket(
                owner, purpose, expiry, new AtomicBoolean(false)));
        }

        boolean consume(String key, String owner,
                        String purpose, Instant now) {
            Ticket t = tickets.get(key);
            return t != null
                && t.owner().equals(owner)
                && t.purpose().equals(purpose)
                && now.isBefore(t.expiresAt())
                && t.used().compareAndSet(false, true);
        }
    }

    record Assertion(
        String owner, String challenge,
        boolean signatureVerified,
        boolean originValid,
        boolean rpIdValid,
        boolean userVerified) {}

    static boolean acceptPasskey(
            OneTimeStore store, Assertion assertion,
            String expectedUser, String expectedChallenge,
            Instant now) {

        return assertion.owner().equals(expectedUser)
            && assertion.challenge().equals(expectedChallenge)
            && assertion.signatureVerified()
            && assertion.originValid()
            && assertion.rpIdValid()
            && assertion.userVerified()
            && store.consume(
                expectedChallenge, expectedUser,
                "WEBAUTHN_CHALLENGE", now);
    }

    record Proof(
        String owner, Factor factor,
        Instant verifiedAt, boolean trustedVerifier) {}

    static boolean hasFreshMfa(
            String owner, Instant now,
            List<Proof> proofs) {

        EnumSet<Factor> valid = EnumSet.noneOf(Factor.class);
        for (Proof p : proofs) {
            if (!p.trustedVerifier()
                    || !p.owner().equals(owner)
                    || p.verifiedAt().isAfter(now)
                    || p.verifiedAt().isBefore(
                        now.minusSeconds(300))) {
                continue;
            }
            valid.add(p.factor());
        }
        return valid.contains(Factor.PASSWORD)
            && valid.contains(Factor.PASSKEY);
    }

    static boolean recover(
            OneTimeStore store, String code,
            String user, Instant now,
            boolean additionalRecoveryProofVerified) {

        return additionalRecoveryProofVerified
            && store.consume(code, user, "RECOVERY", now);
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-01T09:00:00Z");
        OneTimeStore store = new OneTimeStore();

        store.issue("ott-valid", "user-42",
            "LOGIN_OTT", now.plusSeconds(120));
        store.issue("ott-expired", "user-42",
            "LOGIN_OTT", now);

        System.out.println("OTT first: " +
            store.consume("ott-valid", "user-42", "LOGIN_OTT", now));
        System.out.println("OTT replay: " +
            store.consume("ott-valid", "user-42", "LOGIN_OTT", now));
        System.out.println("OTT expired: " +
            store.consume("ott-expired", "user-42", "LOGIN_OTT", now));
        System.out.println("OTT wrong purpose: " +
            store.consume("ott-valid", "user-42", "RECOVERY", now));

        store.issue("challenge-1", "user-42",
            "WEBAUTHN_CHALLENGE", now.plusSeconds(60));
        store.issue("challenge-2", "user-42",
            "WEBAUTHN_CHALLENGE", now.plusSeconds(60));
        Assertion wrongOrigin = new Assertion(
            "user-42", "challenge-1",
            true, false, true, true);
        Assertion valid = new Assertion(
            "user-42", "challenge-1",
            true, true, true, true);
        Assertion noUv = new Assertion(
            "user-42", "challenge-2",
            true, true, true, false);

        System.out.println("Passkey wrong origin: " +
            acceptPasskey(store, wrongOrigin,
                "user-42", "challenge-1", now));
        System.out.println("Passkey valid: " +
            acceptPasskey(store, valid,
                "user-42", "challenge-1", now));
        System.out.println("Passkey replay: " +
            acceptPasskey(store, valid,
                "user-42", "challenge-1", now));
        System.out.println("Passkey without UV: " +
            acceptPasskey(store, noUv,
                "user-42", "challenge-2", now));

        Proof password = new Proof(
            "user-42", Factor.PASSWORD, now, true);
        Proof passkey = new Proof(
            "user-42", Factor.PASSKEY, now, true);
        Proof stalePasskey = new Proof(
            "user-42", Factor.PASSKEY,
            now.minusSeconds(360), true);

        System.out.println("MFA password only: " +
            hasFreshMfa("user-42", now, List.of(password)));
        System.out.println("MFA password + passkey: " +
            hasFreshMfa("user-42", now, List.of(password, passkey)));
        System.out.println("MFA stale passkey: " +
            hasFreshMfa("user-42", now,
                List.of(password, stalePasskey)));

        store.issue("backup-A", "user-42",
            "RECOVERY", now.plusSeconds(600));
        System.out.println("Recovery weak: " +
            recover(store, "backup-A", "user-42", now, false));
        System.out.println("Recovery controlled: " +
            recover(store, "backup-A", "user-42", now, true));
        System.out.println("Recovery replay: " +
            recover(store, "backup-A", "user-42", now, true));
    }
}
```

Biên dịch và chạy:

```bash
javac AuthExpiryReplayRecoveryDemo.java
java AuthExpiryReplayRecoveryDemo
```

Stdout **chính xác**:

```text
OTT first: true
OTT replay: false
OTT expired: false
OTT wrong purpose: false
Passkey wrong origin: false
Passkey valid: true
Passkey replay: false
Passkey without UV: false
MFA password only: false
MFA password + passkey: true
MFA stale passkey: false
Recovery weak: false
Recovery controlled: true
Recovery replay: false
```

**Vì sao output như vậy?**

- `OTT first` true vì token đúng user/purpose, `now < expiresAt` và CAS chuyển `used=false → true`.
- `OTT replay` false vì cùng `AtomicBoolean` đã là true.
- `OTT expired` false vì `now==expiresAt`, điều kiện `isBefore` không đạt.
- `OTT wrong purpose` false dù chuỗi secret có tồn tại; namespace `LOGIN_OTT` không chấp nhận làm `RECOVERY`.
- `Passkey wrong origin` false vì origin do verifier báo không đúng; test chưa tiêu thụ challenge.
- `Passkey valid` true vì mọi cờ giả lập đúng và challenge được consume một lần.
- `Passkey replay` false do challenge đã consumed.
- `Passkey without UV` false vì policy yêu cầu user verification; challenge chưa tiêu thụ, nhưng nếu muốn lock sau thất bại cần bổ sung attempts/rate-limit.
- `MFA password only` false vì policy yêu cầu cả `PASSWORD` và `PASSKEY`.
- `MFA password + passkey` true theo **mô hình proof đã được verifier tin cậy**.
- `MFA stale passkey` false do đã quá khoảng 300 giây minh họa.
- `Recovery weak` false do thiếu bằng chứng bổ sung theo policy mô phỏng; code chưa consumed.
- `Recovery controlled` true vì đủ gate và secret recovery còn sống.
- `Recovery replay` false vì recovery code đã consumed.

### 10.1. Giới hạn chính xác của demo

- `AtomicBoolean` chỉ nguyên tử trong **cùng một JVM**; không chứng minh an toàn giữa nhiều replicas. Production dùng database row update/Redis Lua/transaction có shared state.
- `signatureVerified`, `originValid`, `rpIdValid` và `userVerified` là dữ liệu kiểm thử **được giả định**; không thay thư viện WebAuthn xác minh chữ ký RP/challenge/origin thực.
- `trustedVerifier` cũng chỉ là giả định của policy test, không tạo proof thật bằng password/TOTP/ID Token.
- Không có session binding, password hashing, token hash, rate limiting, CSRF, KeyStore, JWKS hay device lifecycle trong ví dụ.
- `RECOVERY` chỉ được consume khi có bằng chứng bổ sung giả lập; một hệ thống thật phải chọn assurance/recovery workflow cụ thể và giới hạn quyền sau recovery.
- Thời gian năm phút của freshness là **ví dụ**, không là hằng số mặc định của Spring hay NIST.

## 11. Kiểm thử đồng thời: cách bắt lỗi chỉ xảy ra trên nhiều node

### 11.1. Đừng chỉ test hai lời gọi tuần tự

Hai lời gọi tuần tự `consume(token)` thường phát hiện lỗi reuse đơn giản, nhưng không phát hiện race kiểu:

```text
Node A: SELECT used=false
Node B: SELECT used=false
Node A: grant session
Node B: grant session
Node A: UPDATE used=true
Node B: UPDATE used=true
```

Một service dùng nhiều bản sao/kho cache phải có cùng quy tắc **một token cấp tối đa một authentication result** (theo single-use policy). Với WebAuthn, challenge/authentication state cũng phải liên kết vào một ceremony và không chấp nhận assertion cũ khi dùng lại.

### 11.2. Cách dựng integration test concurrency

- Dùng **hai client/session khác nhau** và cùng một OTT secret hoặc backup code.
- Khởi tạo chúng tại barrier, cho cả hai gửi POST cùng thời điểm.
- Backend dùng **shared database** và transaction settings như production.
- Đếm kết quả Authentication được tạo **thành công** và số row consumed sau commit.
- Assert **đúng một** request được phép dùng secret; request còn lại bị từ chối.
- Lặp nhiều lần với test fixtures mới; không dùng cùng session đã authenticated che kết quả.
- Thử network retry sau commit, node chết ngay trước/sau transaction commit, cache invalidation trễ và clock skew.
- Với nhiều OTT cùng user, test chính sách “newest only” hoặc credential version chặn những link cũ sau account change.

Nếu test chỉ dùng `ConcurrentHashMap` in-process thì mới chứng minh một loại concurrency. Nếu product cluster dùng DB replication lag, session replication và queue, cần integration test tại ranh giới đó.

### 11.3. SQL atomic consume cho backup code

Ví dụ PostgreSQL, với code hash đã tính an toàn:

```sql
UPDATE recovery_codes
SET consumed_at = now()
WHERE code_hash = :hash
  AND account_id = :accountId
  AND purpose = 'ACCOUNT_RECOVERY'
  AND consumed_at IS NULL
RETURNING id;
```

Nếu bảng có `expires_at` thì thêm điều kiện thời hạn. Đây là ví dụ cho custom recovery store; cần đặt cả thay đổi trạng thái/việc đăng ký authenticator trong transaction phù hợp hoặc workflow có rollback/idempotency rõ, tránh tiêu thụ code rồi thất bại nửa chừng. Đừng tạo session full từ một lệnh SQL thành công mà bỏ những bước policy còn lại.

## 12. Các anti-pattern kiểm thử

| Sai lầm | Vì sao gây false positive | Cách sửa |
|---|---|---|
| `@WithMockUser` rồi gọi /admin và thấy 200 | Principal giả không đi qua MFA/OTT/passkey verifier | Dùng cho authorization unit; thêm login integration thật |
| Mock `OneTimeTokenService.consume` luôn trả user | Không kiểm expiry/replay/DB | Test service thật và negative cases |
| `with(jwt())` rồi kết luận passkey đã login | Jwt fixture khác WebAuthn ceremony | Test assertion ký thật và flow WebAuthn |
| WebAuthn `signatureValid=true` từ request body | Client tự công nhận chữ ký | Real WebAuthn verifier, expected RP config server-side |
| Chỉ test OTT còn hạn | Bỏ sót biên expiry, replay và wrong purpose | Test trước/đúng/sau thời hạn |
| `Thread.sleep(300_000)` để test TTL | Chậm/flaky, không chính xác biên | Inject `Clock`/test seam |
| GET magic link cũng consume | Email scanner tự hết token | GET landing không consume, POST confirm |
| Test passkey UV chỉ kiểm chữ ký | Một assertion UP-only có thể vượt step-up | Kiểm UV per policy |
| Cho passkey `signCount=0` luôn bị cấm | Synced passkeys có counters khác | Risk-based counter policy và replay challenge |
| Password + PIN được coi MFA | Cùng factor knowledge | Đếm loại factor đã verified và provenance |
| Password + OTT email được tự gọi AAL2 | Channel có thể phụ thuộc cùng password | Review NIST/assurance, ưu tiên phishing-resistant |
| Recovery chỉ cần nhấn “Skip MFA” | Attacker đi vòng toàn bộ login | Account recovery policy với verified proof |
| Dùng lại backup code | Có thể đổi authenticator lặp lại | Single-use atomic + rate limit |
| Test concurrent qua một HTTP session đã login | Session che đường verifier thứ hai | Fresh sessions/cookies cho từng request |
| Bỏ qua account disabled sau token còn hạn | Token valid nhưng account không được phép | Check current account status at redemption |
| Mock cả `AuthenticationManager` | Filter chạy nhưng verifier không thực | Ít nhất một test với provider/key/DB thật |
| Tắt CSRF để test dễ | Không kiểm được session POST bảo mật | Giữ CSRF và test negative |
| Test passkey bằng credentials của user khác | Ownership có thể bị bypass | DB mapping credential→account và tenant check |
| Khóa admin account mà session cũ còn quyền | Revocation chưa lan truyền | Session/token version/live checks và đa node test |

## 13. Bộ test coverage để áp dụng ngay

### 13.1. OTT

```text
ottValidTokenAuthenticatesExactlyOnce()
ottTokenAtExpiryIsRejected()
ottTokenAfterExpiryIsRejected()
ottTokenWithWrongPurposeIsRejected()
ottTokenForDifferentAccountIsRejected()
ottTokenForDifferentTenantIsRejected()
ottReplayIsRejectedAfterSuccess()
ottParallelConsumeAcrossNodesAllowsAtMostOne()
ottGetLandingDoesNotConsumeToken()
ottLinkDoesNotUseUntrustedHostHeader()
ottWrongOrExpiredTokenDoesNotCreateSession()
ottAccountDisabledBetweenIssueAndConsumeIsRejected()
ottInvalidTokenCannotBeUsedAsPasswordResetToken()
```

### 13.2. WebAuthn/passkeys

```text
webauthnValidSignedAssertionAuthenticates()
webauthnWrongChallengeIsRejected()
webauthnExpiredChallengeIsRejected()
webauthnReplayedAssertionIsRejected()
webauthnWrongOriginIsRejected()
webauthnWrongRpIdIsRejected()
webauthnTamperedSignatureIsRejected()
webauthnWrongUserHandleIsRejected()
webauthnCredentialOwnerMismatchIsRejected()
webauthnUserPresenceRequiredIsEnforced()
webauthnUserVerificationRequiredIsEnforced()
webauthnRevokedCredentialCannotAuthenticate()
webauthnRegistrationRequiresStepUp()
webauthnDuplicateCredentialRegistrationIsRejected()
webauthnSyncedPasskeyCounterPolicyIsCorrect()
```

### 13.3. MFA và recovery

```text
passwordOnlyCannotAccessMfaProtectedResource()
twoKnowledgeFactorsDoNotSatisfyTwoFactorPolicy()
missingWebauthnFactorTriggersStepUp()
mfaFactorsFromDifferentUsersCannotBeCombined()
mfaFactorsFromDifferentSessionsCannotBeCombined()
mfaStaleFactorRequiresReauthentication()
passkeyUvMissingDoesNotSatisfyUvPolicy()
accountDisabledAfterMfaCannotAccessSensitiveResource()
oldRoleAfterRevocationDoesNotGrantPrivilege()
backupCodeCanBeRedeemedOnceOnly()
backupCodeWrongUserIsRejected()
backupCodeReplayedConcurrentIsRejected()
passwordResetCannotDisableMfaByItself()
lostAuthenticatorRequiresControlledRecovery()
recoveryCannotEnrollCredentialForDifferentAccount()
recoveryNotifiesAndInvalidatesLostCredential()
recoveryFailureDoesNotCreateAuthenticatedSession()
```

Mỗi test phải định nghĩa **setup, bằng chứng thật/giả, hành động, assertion, cleanup**. Nếu chỉ dùng mocks, tên test nên phản ánh đó là *policy simulation* thay vì lời chứng nhận authentication integration.

## 14. Vận hành thực tế: logging, UX và bảo đảm bảo mật

### 14.1. Ghi log đủ để điều tra nhưng không chứa secrets

Có thể ghi correlation ID, user ID/tenant ID được xác minh, factor type, challenge ID đã băm hoặc reference nội bộ, reason codes như `OTT_EXPIRED`, `WEBAUTHN_ORIGIN_MISMATCH`, `MFA_FACTOR_MISSING`, `RECOVERY_REPLAY`. Không ghi raw OTT, recovery code, WebAuthn private key, TOTP seed, bearer token, session cookie, QR enrollment, hay dữ liệu biometric.

Client không cần thấy tất cả reason codes nội bộ; lỗi login nên đủ rõ để hợp pháp khôi phục nhưng không enumerate account/attacker feedback. Dùng audit access controls, retention và privacy policy.

### 14.2. Giao diện lỗi thân thiện nhưng không fail open

- OTT hết hạn: thông báo link không còn dùng được; cho yêu cầu link mới với rate limit.
- OTT đã dùng: không nói ra user đã login ở đâu; cho phát lại link theo policy.
- Passkey không tìm thấy hoặc bị user cancel: hỗ trợ thử lại hoặc dùng authenticator dự phòng đã enroll.
- Passkey UV=false khi cần UV: yêu cầu thiết bị xác minh user; **không** giảm policy sang chỉ UP.
- MFA thiếu yếu tố: chỉ dẫn bước tiếp, không cấp quyền nhạy cảm tạm thời.
- Khôi phục yếu tố: dùng workflow riêng, thông báo thay đổi và cho phép báo cáo nếu không phải user.
- Retry/network timeout: phải giữ idempotency để không biến một lần submit thành hai authentication/registration grants.

### 14.3. Theo dõi hiệu năng và bảo vệ chống lạm dụng

- Request OTT generation: rate limit theo IP/account/contact, tránh user enumeration và email flooding.
- OTT submission: giới hạn thử secret và detection bất thường; dù token entropy cao, vẫn cần bảo vệ endpoint.
- WebAuthn options: tránh challenge generation flood, giới hạn server-side challenge storage, cleanup TTL.
- WebAuthn verification: kiểm số lần signature failures và chính sách recovery, không log payload nhạy cảm.
- MFA push/TOTP: chống push fatigue và brute-force, giữ time drift window nhỏ, chặn replay.
- Recovery/support: rate limit, risk score, workflow audit, kiểm soát người phê duyệt và notification.
- Điều phối clock: NTP/monotonic/rules về allowed skew đúng threat model, test drift giữa nodes.

## 15. Checklist hoàn thành QA bài đăng nhập

1. **OTT:** đúng subject/purpose/TTL, CSPRNG, hash store/atomic consume, replay, multi-node race, email scanners và GET/POST.
2. **Passkey:** signed assertions thật, challenge single-use/expiry/session, origin/RP ID, credential ownership, UP/UV, revoked credentials và registration.
3. **MFA:** đúng số lượng **loại** factor độc lập, freshness, user/session binding, step-up, quyền tài nguyên và không fail open.
4. **Recovery:** backup codes dùng một lần, enrollment đủ assurance, không tắt MFA từ password reset, support workflow có audit và thông báo.
5. **Phiên:** logout, session fixation, account disable/role revoke, cookie protections và session version checks.
6. **Không nhầm mocks:** `@WithMockUser`/`jwt()`/`signatureVerified=true` không là cryptographic integration test.
7. **Test clock:** trước, tại, sau expiry, không dùng `sleep`; kiểm skew/network time với multi-node.
8. **Test đồng thời:** hai sessions/node cùng nộp token/code, assert tối đa một success.
9. **CSRF:** trên form/registration options và các POST session-based theo cấu hình, không tắt toàn bộ.
10. **MFA phiên bản:** Spring Security 6.5 có OTT/WebAuthn; Spring Security 7 có factor authorities/MFA DSL; test dependency/API đúng.
11. **Fail closed:** mất database/verification service hay queue downtime không tự cấp Authentication/skip factor.
12. **End-to-end:** với IdP, browser và virtual/hardware authenticator cùng proxy/cookie policies giống production.
13. **Báo cáo coverage tách tầng:** policy/unit, store/concurrency, Spring filters, cryptographic verification và E2E.
14. **Lưu bằng chứng:** test artifacts đã redacted, structured assertions và audit/event IDs đủ đối chiếu, không lưu secrets production.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** OTT đã thành công một lần nhưng lần hai vẫn trả 200 do HTTP session cũ đang đăng nhập. Test có chứng minh replay an toàn không?  
**Trả lời:** Chưa. Phải dùng **fresh session**/client thứ hai, gửi đúng raw OTT và xác minh verifier/store từ chối reuse, không bị session đã login che kết quả.

**Câu 2.** Khi `now == expiresAt`, một token có hợp lệ không?  
**Trả lời:** Với policy `now < expiresAt` thì **không**. Test phải khớp hợp đồng và đánh đúng biên.

**Câu 3.** WebAuthn assertion có chữ ký hợp lệ nhưng `origin` khác origin được cấu hình, cho login không?  
**Trả lời:** Không. Cần verify origin/RP ID/challenge cùng chữ ký; ký đúng riêng lẻ chưa đủ.

**Câu 4.** WebAuthn chỉ có UP=true, UV=false nhưng endpoint yêu cầu user verification. Kết quả?  
**Trả lời:** Bị từ chối theo policy; không âm thầm giảm assurance.

**Câu 5.** `@WithMockUser` giúp gọi endpoint MFA protected được 200, có chứng minh user đã pass MFA thật không?  
**Trả lời:** Không. Đó là principal giả lập; phải test factor issuance/verification thật ở lớp khác.

**Câu 6.** Spring Security 6.5 bật đồng thời `formLogin()`, `oneTimeTokenLogin()` và `webAuthn()` có tự đảm bảo cả ba cùng được yêu cầu không?  
**Trả lời:** Không. Chúng có thể là các phương thức login riêng; policy yêu cầu nhiều yếu tố cần được cấu hình/thực thi riêng. Dòng Spring Security 7 bổ sung MFA factor-authorities DSL.

**Câu 7.** Mã recovery chính xác nhưng đã dùng trước đó có được cấp passkey mới không?  
**Trả lời:** Không. Backup code là một lần; store phải chặn replay atomically và re-enrollment có điều kiện riêng.

**Câu 8.** Tại sao `signCount=0` không tự là bằng chứng credential clone?  
**Trả lời:** Authenticator và synced passkeys có cách quản lý counter khác nhau; cần risk policy và verifier phù hợp, không dùng một quy tắc “zero = clone” phổ quát.

**Câu 9.** Một người có password + email OTT có mặc nhiên đạt AAL2 không?  
**Trả lời:** Không. MFA assurance cần đánh giá loại authenticator/channel/independence và toàn bộ NIST controls; NIST 800-63B-4 không cho email làm OOB authenticator.

**Câu 10.** Điều gì bảo đảm một token không được dùng hai lần trên cụm ba node?  
**Trả lời:** Shared token state, atomic consume ở database/Redis, transaction và kết quả được test bằng các concurrent clients khác nhau. `AtomicBoolean` trong một JVM không đủ.

## Tài liệu tham khảo

- [Spring Security 6.5 – One-Time Token Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html): DSL, generate/submit flow, token service, TTL tùy biến và delivery handler.
- [Spring Security 6.5 – Passkeys/WebAuthn](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html): registration/options, authentication/options, credential repositories, RP ID và allowed origins.
- [Spring Security 7 – Multi-Factor Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html): `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication`, conditional MFA và required factors.
- [Spring Security – Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): MockMvc, `@WithMockUser`, test configuration.
- [W3C WebAuthn Level 3](https://www.w3.org/TR/webauthn-3/): challenge, RP ID, origin, UP/UV, assertion verification và signature counters.
- [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html): replay, phishing resistance, recovery và authenticator binding.
- [OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html): MFA independence, account recovery, reset, enrollment và risk.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): login security, reauthentication, account enumeration và lockout.
