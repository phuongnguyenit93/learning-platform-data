# MFA tích hợp theo phiên bản Spring Security và những phần phải tự xây dựng khi thư viện chưa hỗ trợ

## 1. Vì sao chủ đề này phụ thuộc mạnh vào phiên bản?

**MFA (Multi-Factor Authentication)** yêu cầu bằng chứng xác thực từ hơn một **loại yếu tố độc lập** hoặc một authenticator đa yếu tố được xác minh đúng cách. Việc ứng dụng hỗ trợ *nhiều cách đăng nhập* (password, one-time token, passkey, OIDC) **không đồng nghĩa** mọi người dùng bắt buộc vượt qua MFA.

Với Spring Security, cần tách ba năng lực:

1. **Authentication mechanisms:** framework có filter/provider/service nào để xác thực một credential cụ thể không?
2. **Factor tracking & enforcement:** framework có theo dõi **yếu tố nào đã được chứng minh** và buộc đủ các yếu tố khi vào endpoint không?
3. **Vòng đời và vận hành MFA:** enroll authenticator, lưu secrets/keys, thử lại, khóa, recovery, revoke, audit, step-up, session/token assurance có đầy đủ không?

Một ứng dụng Spring Security **6.5** có thể dùng `formLogin()`, `oneTimeTokenLogin()` và `webAuthn()`, nhưng không có sẵn cơ chế MFA tổng thể bằng `@EnableMultiFactorAuthentication` của **Spring Security 7**. Khi nâng phiên bản, cũng không được mặc định rằng mọi yêu cầu nghiệp vụ MFA đều do thư viện đảm nhiệm: **TOTP setup/verification, delivery channel, recovery, risk policy và tích hợp IdP/API vẫn là công việc của sản phẩm**.

Sau bài học, bạn sẽ:

- Lập **ma trận năng lực theo phiên bản** thay vì copy code 7.x vào 6.x.
- Sử dụng `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication` và `AuthorizationManagerFactory` trên Spring Security 7 Servlet.
- Biết **One-Time Token (OTT) khác TOTP/HOTP**, và email magic link không mặc nhiên đạt chuẩn MFA độc lập.
- Thiết kế **MFA gate** ở Spring Security 6.x khi chưa có built-in factor authorization.
- Gắn proof vào **người dùng + phiên + thời điểm + phiên bản trạng thái bảo mật**, chống dùng lại dấu “MFA verified” sau reset/đăng xuất.
- Xử lý MFA với form login, WebAuthn/passkey, OIDC, JWT resource server và WebFlux.
- Viết test cho single-factor, đủ factor, token hết hạn, replay, reset/recovery và upgrade.

**Phạm vi:** Java 17+, Spring Boot 3.x / Spring Security 6.5.x và Spring Boot 4.x / Spring Security 7.x, nhánh **Servlet** là trọng tâm. API code snippets gắn rõ version; code Java thuần bên dưới biên dịch độc lập. Khi chạy ứng dụng thật, dùng **BOM/dependency management** để không trộn version của `spring-security-core`, `config`, `web` và `test`.

## 2. Định nghĩa đúng: MFA không phải chỉ thêm một trang OTP

Một số cách xác thực:

| Phương thức | Loại bằng chứng | Điểm cần thận trọng |
| --- | --- | --- |
| Mật khẩu | **Knowledge**: thứ người dùng biết | Mật khẩu + PIN thứ hai thường vẫn cùng loại yếu tố |
| TOTP ứng dụng authenticator | **Possession** của secret trên thiết bị, thường là single-factor OTP | Có thể bị phishing, replay và clock drift |
| Security key/WebAuthn có xác minh user | Cryptographic authenticator, có thể **đa yếu tố** khi xác minh user đúng | Cần kiểm tra UV flag, RP ID, origin, challenge, public key, sign counter/risk |
| Passkey đồng bộ | Cryptographic key; có thể đồng bộ giữa thiết bị | Không mặc nhiên device-bound, assurance tùy UV/key management |
| SMS/voice OTP | Out-of-band qua mạng điện thoại | Rủi ro SIM swap; restricted theo NIST ở các bối cảnh liên quan |
| Email magic link | Chứng minh ai kiểm soát hộp thư qua link/token | **Không tự được tính là possession factor độc lập** theo NIST OOB; email có thể dùng chung mật khẩu/thiết bị |
| One-Time Token của Spring | Server tạo token dùng một lần, giao qua kênh do app tự chọn | **OTT không phải TOTP**; cơ chế giao token mới quyết định mức assurance |
| Recovery code | Bí mật dự phòng dùng một lần | Cần phát hành/lưu trữ/revoke an toàn và quy trình khôi phục đúng mức |
| OAuth/OIDC ID token | Assertion từ IdP đã được xác thực | **Không tự chứng minh MFA** nếu IdP không đưa bằng chứng assurance đáng tin |

Theo [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html), **AAL2** yêu cầu hai yếu tố khác nhau hoặc một authenticator đa yếu tố phù hợp; email không được dùng làm out-of-band authenticator theo tiêu chuẩn đó. Đây là **tiêu chuẩn assurance**, không có nghĩa mọi hình thức email login đều bị cấm trong mọi ứng dụng; hãy ghi đúng mục tiêu compliance.

**Câu hỏi để kiểm tra:** nếu attacker chỉ lấy được mật khẩu user, người đó có lấy luôn mã thứ hai qua **cùng hộp thư email chỉ cần mật khẩu đó** không? Nếu có, thứ được gọi “MFA” có thể không độc lập về rủi ro.

## 3. Ma trận tính năng theo phiên bản: đừng nhầm authentication mechanism với MFA policy

| Thành phần | Spring Security 5.x / 6.x trước khi có tính năng liên quan | Spring Security **6.5.x** | Spring Security **7.0+** |
| --- | --- | --- | --- |
| Form login, `AuthenticationManager`, providers, CSRF/session | Có từ lâu | Có | Có, nhưng một số API/DSL nâng cấp |
| UserDetails/password/roles/authorities | Có | Có | Có |
| AuthorizationManager kiểm tra một rule custom | Tùy minor, áp dụng mô hình đã có từ 5.x/6.x | Có thể tự viết MFA gate | Có và kết hợp factor authorization |
| One-Time Token login `.oneTimeTokenLogin(...)` | Không được giả định ở mọi minor đời cũ | **Có** | **Có** |
| WebAuthn/passkeys `.webAuthn(...)` | Không được giả định ở mọi minor đời cũ | **Có**, cần dependency/repositories đúng | **Có**, tích hợp factor policy tốt hơn |
| `FactorGrantedAuthority` và thời điểm `issuedAt` | **Không có API tương đương chính thức** | **Chưa có** | **Có từ 7.0** |
| `@EnableMultiFactorAuthentication` | Không có | **Không có** | **Có từ 7.0**, Servlet MFA |
| AuthorizationManagerFactory MFA rule/redirect tới factor còn thiếu | Không có chung API 7 | Tự orchestration/policy | Hỗ trợ chính thức theo tài liệu 7.x |
| TOTP/HOTP enrollment/verification server cho ứng dụng của bạn | Cần tự xây/tích hợp | **Cần tự xây hoặc dùng thư viện/IdP** | **Không tự biến OTT thành TOTP**; vẫn cần component phù hợp |
| Email/SMS/notification delivery cho OTT | Nghiệp vụ app | **App tự cung cấp handler/channel** | **App tự cung cấp handler/channel** |
| Recovery, backup codes, device loss, audit, revocation ngoài app | App/IdP | App/IdP | **Vẫn app/IdP** |
| MFA tương đương trên WebFlux | Tùy custom | Custom reactive orchestration | `@EnableMultiFactorAuthentication` docs 7.x nêu **chưa áp dụng cho reactive** (xác minh lại khi nâng phiên bản) |

**Đừng viết** “Spring Security 6.5 không hỗ trợ OTP” nếu đang nói **One-Time Token login**. Câu đúng là: 6.5 có OTT login; **TOTP/HOTP authenticator** và **chính sách ghép nhiều factor vào một authentication** không tự được tạo chỉ bằng DSL đó.

### 3.1. Kiểm tra runtime đang chạy phiên bản nào

Trong project Gradle có Spring Boot dependency management:

```bash
./gradlew dependencyInsight --dependency spring-security-config \
  --configuration runtimeClasspath

./gradlew dependencyInsight --dependency spring-security-core \
  --configuration runtimeClasspath
```

Windows PowerShell/cmd dùng `gradlew.bat`. Trong Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework.security
```

Kiểm tra **resolved versions**, không chỉ version ghi trong `build.gradle`. Nếu project vẫn là Boot 3.x/Security 6.x mà IDE autocomplete báo không có `FactorGrantedAuthority` hoặc `@EnableMultiFactorAuthentication`, có khả năng **API đó thuộc nhánh 7.x**, không phải lỗi import thông thường.

### 3.2. Nếu phải dùng phiên bản cũ

Không thêm `spring-security-config:7.x` vào app có `spring-security-core:6.x` để “lấy mỗi annotation MFA”. Các module và Boot runtime phải tương thích theo BOM; trộn major/minor tùy tiện dễ gặp `NoSuchMethodError`, lỗi filter chain và behavior không dự đoán được. Hai lựa chọn chính:

1. **Nâng stack có kiểm soát** lên phiên bản hỗ trợ MFA tích hợp, với regression tests về login, session, API, claims và method security.
2. **Giữ stack hiện có**, tự viết MFA enforcement ở **application boundary** hoặc chuyển MFA sang IdP đáng tin, không giả sử thư viện tự làm phần thiếu.

## 4. Kiến trúc hai tầng: chứng minh yếu tố và quyết định được truy cập

```text
                   FIRST FACTOR
      Password / passkey / trusted IdP assertion
                          |
                          v
                 Authentication result
                          |
                          v
                   MFA policy checks
                          |
         +----------------+--------------------+
         |                                     |
  Required factors met?                Missing factor(s)?
         |                                     |
        YES                                    NO
         |                                     |
         v                                     v
   Authorized actions                Challenge/step-up path
   appropriate to AAL                 e.g. TOTP or WebAuthn
                                               |
                                       Server-side verification
                                               |
                                       One-time/replay control
                                               |
                                       Record verified factor
                                               |
                                       Re-evaluate authorization
```

**Chỉ “có hai filter/provider” là OR, không phải AND.** Một người có thể login bằng password **hoặc** OTT nếu cả hai được bật mà không có policy buộc phải chứng minh cả hai. MFA là **điều kiện authorization dựa trên những yếu tố đã thật sự được chứng minh**.

### 4.1. Những gì không bao giờ được lấy làm bằng chứng MFA

- Query parameter `?mfa=true` hoặc HTTP header do client tự gửi.
- `UserDetails.getAuthorities()` có `ROLE_MFA` lưu cố định trong bảng roles từ trước.
- Cookie chứa `mfaPassed=true` không ký, không mã hóa/bind và không kiểm server-side.
- “Người dùng từng enroll TOTP” — enroll khác với **vừa xác minh mã**.
- Sự tồn tại của `SecurityContext` sau password login hoặc `isAuthenticated()==true`.
- `remember-me` cookie hoặc redirect tới trang OTP nhưng chưa xác minh.
- JWT payload `"amr":["mfa"]` **trước** khi kiểm chữ ký, issuer, audience, expiry, token type và nguồn phát hành có thẩm quyền.

## 5. Spring Security 7: FactorGrantedAuthority là gì?

Từ Spring Security **7.0**, `org.springframework.security.core.authority.FactorGrantedAuthority` biểu diễn yếu tố đã dùng khi xác thực; nó triển khai `GrantedAuthority` và lưu **`issuedAt`**.

Một số hằng số có ý nghĩa:

| Hằng số | Authority string | Nguồn thông thường |
| --- | --- | --- |
| `FactorGrantedAuthority.PASSWORD_AUTHORITY` | `FACTOR_PASSWORD` | Password login |
| `FactorGrantedAuthority.OTT_AUTHORITY` | `FACTOR_OTT` | Spring One-Time Token login |
| `FactorGrantedAuthority.WEBAUTHN_AUTHORITY` | `FACTOR_WEBAUTHN` | WebAuthn authentication |
| `FactorGrantedAuthority.X509_AUTHORITY` | `FACTOR_X509` | X.509 |
| `FactorGrantedAuthority.BEARER_AUTHORITY` | `FACTOR_BEARER` | Bearer authentication |
| `FactorGrantedAuthority.AUTHORIZATION_CODE_AUTHORITY` | `FACTOR_AUTHORIZATION_CODE` | OAuth2 authorization-code flow |

**Cảnh báo:** `FACTOR_BEARER` mô tả **cơ chế xác thực Bearer**, không tự chứng minh token đã trải qua MFA ở IdP. Và `FACTOR_OTT` chỉ nói OTT flow của Spring đã hoàn tất, không tự kết luận OTT đến từ kênh possession độc lập đáp ứng NIST AAL2.

`FactorGrantedAuthority` là bằng chứng tích hợp trong trusted authentication flow. Không trao authority này chỉ vì client yêu cầu; custom provider phải **xác minh factor trước**, rồi mới cấp factor authority. `issuedAt` giúp rule xét **độ mới** của yếu tố; không biến một lần xác thực nhiều tháng trước thành MFA mới mãi.

### 5.1. Đây là kiểu dữ liệu của 7.x, không phải công thức bật MFA 6.x

Trên 6.5, nếu muốn ghi nhận proof, hãy dùng **model riêng** hoặc `AuthorizationManager` custom. Đừng import `FactorGrantedAuthority` từ source 7.x rồi truyền đi qua session chứa Authentication 6.5; đó là trộn binary compatibility.

## 6. Spring Security 7: bật MFA bắt buộc bằng annotation

Tài liệu chính thức 7.x cung cấp `@EnableMultiFactorAuthentication` để gắn điều kiện factor cho authorization rules.

Đây là **trích đoạn Spring Security 7.x Servlet** (đặt trong `@Configuration`; cần imports, dependency management, account repository và OTT delivery):

```java
@Configuration
@EnableWebSecurity
@EnableMultiFactorAuthentication(authorities = {
        FactorGrantedAuthority.PASSWORD_AUTHORITY,
        FactorGrantedAuthority.OTT_AUTHORITY
})
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

Khi được cấu hình đúng:

- `/admin/**` cần **`ROLE_ADMIN` + `FACTOR_PASSWORD` + `FACTOR_OTT`**.
- Các endpoint `authenticated()` khác cũng cần cả PASSWORD và OTT nếu annotation đang áp dụng toàn cục.
- User mới đăng nhập bằng password nhưng chưa có OTT sẽ phải đi qua OTT flow để thỏa mãn rule.
- Khi user mới có OTT mà chưa có password, có thể cần thêm password theo rule.

**Quan trọng:** `oneTimeTokenLogin(Customizer.withDefaults())` cấu hình mechanism tạo/consume OTT, nhưng **không tự quyết định cách gửi token** cho user ngoài đời thật. Bạn phải cung cấp `OneTimeTokenGenerationSuccessHandler` và kênh delivery phù hợp. Nếu không có phần giao token, config có thể khởi động được nhưng người dùng **không hoàn thành luồng** như mong muốn. Hãy phân biệt *authentication feature available* với *end-to-end MFA deployed*.

### 6.1. Import đúng package

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.Customizer;
import org.springframework.security.web.SecurityFilterChain;
```

Đây là import **cho Security 7**. Nếu IDE báo không tìm `EnableMultiFactorAuthentication` trong Boot 3/Security 6.5, đừng tự sửa package cho giống: kiểm tra đúng version trước.

### 6.2. MFA enforcement phải phủ cả đường điều khiển dữ liệu nhạy cảm

Một annotation toàn cục dễ audit nhưng phải test login endpoints, logout, password reset, static resources và callback để tránh redirect loop. Nếu chỉ muốn bảo vệ admin/đổi credential, dùng selective MFA ở mục sau, **không** buộc một token Bearer machine-to-machine hoàn thành browser OTT challenge không phù hợp.

## 7. Spring Security 7: MFA chọn lọc và điều kiện động

### 7.1. Selective MFA bằng AuthorizationManagerFactory

Trong 7.x, tài liệu có `AuthorizationManagerFactories.multiFactor()`. Ví dụ **chỉ áp MFA cho admin và settings**:

```java
// Trích đoạn trong cấu hình Spring Security 7, với imports phù hợp.
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {

    var mfa = AuthorizationManagerFactories.multiFactor()
            .requireFactors(
                    FactorGrantedAuthority.PASSWORD_AUTHORITY,
                    FactorGrantedAuthority.OTT_AUTHORITY)
            .build();

    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/admin/**").access(mfa.hasRole("ADMIN"))
            .requestMatchers("/user/settings/**").access(mfa.authenticated())
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .oneTimeTokenLogin(Customizer.withDefaults());

    return http.build();
}
```

Theo reference 7.x, khi dùng cách chọn lọc này, bạn có thể bật `@EnableMultiFactorAuthentication(authorities = {})` để kích hoạt hỗ trợ MFA mà **không publish factory global yêu cầu mọi endpoint**. Với cách trên, **không** publish `mfa` factory thành global Bean nếu mục tiêu là chỉ bảo vệ một số rule. Đừng nghĩ `.hasRole("ADMIN")` có sẵn MFA nếu bạn không gắn rule MFA cho admin route trong cấu hình không-global.

### 7.2. MFA có điều kiện

Các policy cần cân nhắc:

- Account có role admin mới bắt buộc thêm factor.
- Giao dịch có rủi ro cao hoặc vượt số tiền giới hạn thì step-up.
- Khi credential mới đăng ký hoặc mới reset, luôn bắt buộc factor mạnh.
- Chỉ yêu cầu Password + WebAuthn đối với người dùng đã enroll passkey (nếu lựa chọn đó phù hợp assurance).
- Cần reauthenticate trong một khoảng thời gian ngắn hơn trước khi đổi phương thức khôi phục.

Spring Security 7 có `AuthorizationManagerFactory` và các điều kiện MFA, ví dụ `.when(...)` hoặc `MultiFactorCondition.WEBAUTHN_REGISTERED` ở annotation trên các nhánh hỗ trợ. Không viết logic “user có passkey → được miễn yếu tố thứ hai” khi chính sách lại yêu cầu cả hai.

### 7.3. Giao dịch nhạy cảm vẫn cần kiểm đối tượng nghiệp vụ

`FACTOR_PASSWORD` + `FACTOR_OTT` không thay thế:

- Kiểm tra user **sở hữu** đối tượng đang sửa.
- `ROLE_ADMIN` hoặc `SCOPE_payment:approve`.
- Phê duyệt bốn mắt/two-person rule.
- Xác minh số tiền, người nhận, transfer intent/dynamic linking nếu chính sách yêu cầu.
- Rate limit, fraud detection, device trust và audit.

**MFA là một trục assurance bổ sung, không phải bypass authorization.**

## 8. Spring Security 7: độ mới và tổ hợp nhiều yếu tố

`FactorGrantedAuthority.getIssuedAt()` ghi thời điểm chứng minh factor, nhưng một policy có thể cần **password trong 30 phút**, **WebAuthn trong 5 phút**, và quyền admin vẫn còn.

7.x cung cấp builder cho factor với `validDuration(...)`:

```java
// Trích đoạn 7.x, không phải full class/bean.
var recentPassword = AuthorizationManagerFactories.multiFactor()
        .requireFactor(factor -> factor
            .passwordAuthority()
            .validDuration(Duration.ofMinutes(30)))
        .build();
```

Bạn vẫn cần tổ chức các factor constraints cho đúng action và đảm bảo server clock/token/session consistency. **Không dùng client timestamp** để quyết định “mã OTP vừa xác minh”.

### 8.1. Một passkey có thể đáp ứng chính sách theo cách khác

Một policy có thể chấp nhận:

- **WebAuthn với đúng assurance**; hoặc
- **Password + authenticator OTP**.

Tài liệu 7.x minh họa tổ hợp `AllRequiredFactorsAuthorizationManager.anyOf(...)`. Nhưng đừng mặc định rằng **mọi WebAuthn assertion** có UV/assurance tương đương nhau; xác định yêu cầu user verification, authenticator provenance và compliance, rồi mới coi WebAuthn là nhánh đủ điều kiện. Một passkey có thể đã là **multi-factor authenticator** nếu các điều kiện liên quan được đáp ứng; lúc đó không nhất thiết ép password bổ sung chỉ để đếm hai màn hình.

### 8.2. Thay phương thức factor cần đổi policy có kiểm chứng

Ví dụ nếu user mất security key, không cho phép “nhấn nút skip factor” mà hệ thống trả `FACTOR_WEBAUTHN` giả. Recovery là một **security-sensitive authentication path**, nên yêu cầu assurance phù hợp, audit và revoke credential cũ.

## 9. OTT của Spring Security 6.5: có sẵn gì và còn thiếu gì?

Spring Security **6.5.11** có:

```java
http.oneTimeTokenLogin(Customizer.withDefaults());
```

Flow tham khảo:

```text
User yêu cầu one-time token
    |
    v
OneTimeTokenService.generate(...)
    |
    v
OneTimeTokenGenerationSuccessHandler
    |
    +--> App gửi token/magic link qua delivery channel
    |
    v
User mở/nhập token vào OTT submit flow
    |
    v
OneTimeTokenService.consume(...)
    |
    v
Spring Security tạo Authentication nếu hợp lệ
```

Framework hỗ trợ **generate, consume, filter và default submit page**, nhưng **không thể tự suy ra email/phone/token transport của sản phẩm**. Ở 6.5 có `InMemoryOneTimeTokenService` mặc định và lựa chọn `JdbcOneTimeTokenService` cho persistence theo tài liệu.

### 9.1. OTT khác TOTP/HOTP

| Tiêu chí | One-Time Token (OTT) | TOTP/HOTP |
| --- | --- | --- |
| Ai tạo secret/value dùng mỗi lần? | Server tạo khi user yêu cầu | Authenticator tạo từ **secret đã enroll** và thời gian/counter |
| Cách giao cho user | Thường email/SMS/magic link qua handler của app | Không cần gửi mã mỗi lần; app mã sinh cục bộ |
| Setup ban đầu | Có thể không cần enroll authenticator độc lập | Cần securely enroll secret/thiết bị |
| Mối liên hệ với password | Có thể là **alternative login** nếu không buộc ghép | Có thể là **second factor** trong flow password+TOTP |
| Chống replay | Token phải one-time atomic consumption | Phải track TOTP counter/step hoặc chống replay |
| Phishing resistance | Phụ thuộc thiết kế, link cũng có thể phishing | **Không phishing-resistant** |
| Bằng chứng AAL2 | Không tự có vì chỉ tên gọi OTT | Còn tùy authenticator/enrollment/verification và toàn hệ thống |

Vì thế **`.formLogin()` + `.oneTimeTokenLogin()` trên 6.5 mặc định không bảo đảm user phải dùng cả hai**. Nếu OTT gửi qua email, cũng đừng mặc định password + email link đáp ứng NIST OOB MFA.

### 9.2. Phần vận hành OTT phải thiết kế

- Đảm bảo delivery channel đã được user xác minh và được binding đúng với account.
- Token có entropy đủ mạnh, TTL ngắn, atomic one-time consume.
- Không log raw token; không nhúng link/token vào analytics, Referer hoặc bên thứ ba.
- Rate limit generate/resend/consume; generic responses để tránh user enumeration.
- Multi-node cần shared store hoặc consistent token service, tránh in-memory store khi scale.
- Verify user status (disabled/locked/deleted), account mapping, nonce và session binding theo policy.
- Xử lý token vừa hết hạn, bị dùng lại, request đồng thời và resend race.
- Khác biệt giữa **login bằng OTT** và **step-up đã có password** phải được mô tả bằng state machine, không chỉ bằng redirect UI.

## 10. WebAuthn/passkey đã có trong 6.5, nhưng enrollment và assurance cần làm đúng

Spring Security **6.5** có hỗ trợ passkeys qua:

```java
http.webAuthn(webAuthn -> webAuthn
        .rpId("example.com")
        .allowedOrigins("https://example.com"));
```

Đây là trích đoạn Servlet config. 6.5 reference có dependency `webauthn4j-core` và các repository như `UserCredentialRepository` và `PublicKeyCredentialUserEntityRepository`; có lựa chọn JDBC tương ứng. Cần kiểm version dependency tương thích với BOM và tài liệu chính thức, không copy version cũ mù quáng.

**Spring giúp verify WebAuthn ceremony**, nhưng sản phẩm vẫn quyết định:

- Credential registration chỉ cho account đã xác minh; khi đăng ký key mới có thể yêu cầu recent MFA.
- RP ID, origin, HTTPS, challenge, user presence/user verification policies.
- Lưu credential ID, public key, metadata/backup flags, signCount/risk signals.
- Phân quyền ai được xóa, rename, revoke hoặc thêm credential.
- Multiple devices, passkey đồng bộ, mất thiết bị, phục hồi/binding.
- Chính sách bắt buộc password + WebAuthn hay chấp nhận WebAuthn đủ mạnh.
- Không coi authentication “đã enroll passkey” như proof WebAuthn hiện tại.

**Không tự implement WebAuthn cryptographic parsing/verification** nếu có thể dùng implementation được duy trì và audit. Các sai sót origin/challenge/rpId kiểm tra rất dễ gây account takeover.

## 11. Spring Security 6.5: nếu chưa có built-in MFA factory, xây ở đâu?

Có ba chiến lược thực tế:

| Chiến lược | Ưu điểm | Phải kiểm soát |
| --- | --- | --- |
| MFA tại **trusted IdP** rồi app chấp nhận assertion đã xác minh | Dễ tập trung enrollment/step-up, policy giữa nhiều services | OIDC `acr/amr/auth_time`, issuer/audience, token freshness, RP/session |
| MFA **in-app** với session + custom AuthorizationManager | Giữ đúng UX/password flow hiện có và bảo vệ endpoints cụ thể | State machine, proof binding, TOTP service/recovery/replay, session, CSRF |
| Upgrade có kiểm soát lên Security 7 Servlet | Dùng framework tracking/enforcement thay code tự viết | Boot 4 compatibility, API changes, method/URL rules, OTT delivery, test regressions |

Không phải lúc nào **nâng lên 7** cũng là đáp án ngay lập tức: nếu app phụ thuộc nhiều library chưa hỗ trợ Boot 4 hoặc dùng WebFlux, có thể chọn IdP hoặc custom enforcement. Nhưng **tránh tự xây xác thực bằng mật mã** khi đã có standards-based authenticator/IdP tin cậy.

### 11.1. Ranh giới responsibility

**Spring Security 6.x đã cung cấp:** authentication providers, filters, roles/authorities, `SecurityContext`, `AuthorizationManager`, `SecurityFilterChain`, session/CSRF, event hooks, built-in OTT/WebAuthn ở các version được xác minh.

**Ứng dụng 6.x phải xây khi cần:** rule “password **và** factor B”, first-stage vs second-stage transition, TOTP verifier/storage, enrollment/revocation/recovery, MFA proof và expiry, UI challenge/success/failure, server-side session invalidation, rate limiting, audit, concurrency và APIs/IdP assurance mapping.

Đừng gắn logic trên **frontend route guard** mà quên kiểm tra backend: client có thể gọi `POST /admin/...` trực tiếp bỏ qua màn hình OTP.

## 12. Model MFA gate cho Servlet Spring Security 6.5

Flow thiết kế:

```text
GET /login -> POST /login (CSRF)
      |
      v
DaoAuthenticationProvider verifies password
      |
      v
Session for user, but NO MFA proof
      |
      +--> /mfa/challenge (needs first factor)
      |        |
      |        v
      |    POST /mfa/verify (CSRF, rate limit)
      |        |
      |        v
      |    verify bound TOTP/WebAuthn, atomic replay check
      |        |
      |        v
      |    server stores MFA proof:
      |       stable userId, sessionId, securityVersion,
      |       factorKind, verifiedAt, expiresAt
      |
      v
GET/POST /admin/** -> AuthorizationManager checks
  authenticated AND role AND fresh MFA proof
      |
      +--> false: deny/challenge
      +--> true: endpoint authorization continues
```

**Lưu ý thiết kế:** trong flow này, password login hoàn tất Spring Authentication nhưng **chưa đủ assurance để vào các route đòi MFA**. Tất cả endpoint nhạy cảm phải dùng gate. Nếu sản phẩm yêu cầu MFA cho **toàn ứng dụng**, thiết lập gate cho mọi endpoint ngoại trừ trang/challenge, static assets và logout; đừng để `anyRequest().authenticated()` biến thành đường bypass.

### 12.1. Proof là trạng thái server, không phải role được gán cố định

Một record minh họa:

```java
public record MfaProof(
        String userId,
        String sessionId,
        long securityVersion,
        String factorKind,
        java.time.Instant verifiedAt,
        java.time.Instant expiresAt
) implements java.io.Serializable {}
```

Đây là **data model minh họa**. Production ưu tiên stable user ID/tenant ID, không dựa hoàn toàn vào mutable email/username. Nếu dùng Spring Session/Redis, object cần serialize với scheme tương thích; session ID phải được **rotate** đúng lúc qua session fixation protections, và proof không được copy từ session cũ sang session mới ngoài policy.

Không lưu raw TOTP secret, password, recovery code hoặc passkey private key trong MFA proof.

### 12.2. Gate đơn giản bằng AuthorizationManager (6.5)

Một implementation **có thể dùng làm điểm khởi đầu** với Spring Security 6.5 Servlet:

```java
package demo.mfa;

import java.time.Clock;
import java.time.Instant;
import java.util.function.Supplier;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

public final class SessionMfaGate
        implements AuthorizationManager<RequestAuthorizationContext> {

    public static final String PROOF_ATTRIBUTE = "MFA_PROOF";
    private final Clock clock;

    public SessionMfaGate(Clock clock) {
        this.clock = clock;
    }

    // Spring Security 6.5 interface method; 7.x chuyển sang authorize(...).
    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        Authentication auth = authentication.get();
        if (auth == null || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken
                || auth instanceof RememberMeAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        HttpServletRequest request = context.getRequest();
        HttpSession session = request.getSession(false);
        if (session == null) {
            return new AuthorizationDecision(false);
        }

        Object stored = session.getAttribute(PROOF_ATTRIBUTE);
        if (!(stored instanceof MfaProof proof)) {
            return new AuthorizationDecision(false);
        }

        Instant now = clock.instant();
        boolean good = proof.userId().equals(auth.getName())
                && proof.sessionId().equals(session.getId())
                && !now.isBefore(proof.verifiedAt())
                && now.isBefore(proof.expiresAt())
                && "TOTP".equals(proof.factorKind());

        return new AuthorizationDecision(good);
    }
}
```

Đoạn này là file **SessionMfaGate.java**, sử dụng record `MfaProof` ở `demo.mfa` (hãy đặt record vào file `MfaProof.java` cùng package). Đây là **demo về gate**, **không phải triển khai production đầy đủ**. Nó giả định `auth.getName()` là stable ID; nếu thực tế là username/email, hãy thay bằng stable principal ID. Nó cũng **chưa check `securityVersion` với source of truth**; production phải bổ sung account-state lookup/validated security stamp để revoke proof cũ khi reset password, disable account, update auth policy. Việc gọi `getSession(false)` chủ ý **không tạo session mới** chỉ để check gate.

### 12.3. Gắn gate vào HttpSecurity

```java
// Spring Security 6.5 Servlet, trong @Configuration.
@Bean
SessionMfaGate mfaGate() {
    return new SessionMfaGate(Clock.systemUTC());
}

@Bean
SecurityFilterChain security(HttpSecurity http, SessionMfaGate gate)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/error", "/assets/**").permitAll()
            .requestMatchers("/mfa/challenge", "/mfa/verify").authenticated()
            .requestMatchers("/admin/**").access(gate)
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

**Quan trọng:** `gate` này hiện chỉ kiểm MFA proof, **chưa kiểm role admin**. Nếu `/admin/**` là đường quản trị, phải **kết hợp** `ROLE_ADMIN` và object-level authorization (ví dụ `AuthorizationManagers.allOf(AuthorityAuthorizationManager.hasRole("ADMIN"), gate)` trên 6.5, với generic types phù hợp). Nếu không, mọi account có MFA hợp lệ có thể vào admin routes: đây là lỗi privilege escalation.

Trong production, nên tách protected scopes:

```text
/admin/**            requires ROLE_ADMIN + fresh MFA + tenant permission
/billing/approve/**  requires payment role + fresh MFA + ownership
/profile/**          requires authenticated (non-sensitive)
 /mfa/**             requires first factor, no MFA proof yet
```

Những URL trong bảng là **minh họa**; cần phủ thêm method security `@PreAuthorize` và các entrypoints ngoài web layer. Nếu gate trả false, ứng dụng phải định nghĩa response/challenge (browser redirect tới `/mfa/challenge` hoặc API trả 403/step-up-required theo contract); Spring 6.x **không tự điều phối tới factor còn thiếu như MFA 7.x** chỉ vì gate denied.

### 12.4. Ghi proof ở đúng điểm

Chỉ set attribute sau khi **service server-side** kiểm mã TOTP/WebAuthn:

```java
// Trích đoạn bên trong trusted MFA verification service/controller,
// KHÔNG phải endpoint public hoàn chỉnh.
if (totpVerifier.verifyAndConsume(userId, suppliedCode)) {
    HttpSession session = request.getSession(false);
    if (session == null) {
        throw new IllegalStateException("No first-factor session");
    }
    session.setAttribute(SessionMfaGate.PROOF_ATTRIBUTE,
            new MfaProof(userId, session.getId(),
                    accountSecurityVersion, "TOTP",
                    clock.instant(),
                    clock.instant().plusSeconds(300)));
}
```

`totpVerifier` là application service **chưa được định nghĩa trong snippet**; phải xác minh secret riêng của user, bounded clock skew, one-time replay, rate limit, account/tenant status, transaction và audit. `accountSecurityVersion` lấy từ trusted account record; phải check version này ở gate như đã nêu. **Không** cho frontend gửi `verifiedAt` hoặc `factorKind` tự chọn.

### 12.5. Logout và session fixation

Sau logout phải xóa SecurityContext, HttpSession và proof. Khi password reset, disable account, mất thiết bị, bind TOTP mới hoặc đăng ký recovery method mới, cần invalidate/revoke proof và active sessions. Nếu session ID đổi sau authentication, hãy bind proof vào **session sau rotation**; không copy proof từ anonymous session vào authenticated session.

## 13. Những phần TOTP/HOTP bạn phải tự tích hợp

Để triển khai password + TOTP đúng tiêu chuẩn, có các hạng mục:

| Hạng mục | Việc ứng dụng/IdP phải cung cấp | Điều không được bỏ qua |
| --- | --- | --- |
| Enrollment | Tạo secret ngẫu nhiên bằng `SecureRandom`, hiển thị QR/`otpauth://` cho user đã xác minh | HTTPS, CSRF, recent login, confirmation code |
| Secret storage | Encrypt at rest/KMS, phân vùng tenant/user, rotate/revoke, restrict access | Không log/ghi raw secret sang analytics |
| Verification | RFC 6238 TOTP, HMAC algorithm, digits, period, bounded skew | Constant-time handling, leading zeros, replay protection |
| Replay | Lưu last accepted time step/counter **atomic** per user/authenticator | Không chấp nhận cùng OTP hai lần |
| Rate limiting | Giới hạn attempts theo user/device/IP/session | Không brute force 6-digit code |
| MFA proof | Cấp sau verify và bind vào identity/session/time/version | Không lấy flag từ client |
| Recovery | Một lần, entropy mạnh, hash at rest; revocation/rotation | Không biến recovery thành đường yếu hơn |
| Change device | Step-up, verify old/new, notify, revoke old secret | Không chỉ biết mật khẩu là bind lại |
| Auditing | Event codes, actor, factor, decision, IP/device risk | Không log OTP/secret |
| Availability | Clock sync, store/DB multi-node, fail closed | Không “skip MFA” khi Redis/mail down |

### 13.1. Không viết “TOTP chỉ cần kiểm 6 số”

6-digit TOTP có không gian mã hữu hạn; verification phải có **attempt budget**, thời hạn ngắn, **replay prevention** và rate limiting. Việc dùng ±1 time step có thể giúp clock skew nhưng đồng thời làm cửa sổ thử rộng hơn. Không sử dụng phép so sánh thời gian từ trình duyệt.

### 13.2. HOTP vs TOTP

- **HOTP (RFC 4226):** counter-based; verifier giữ counter/cửa sổ resynchronization phù hợp.
- **TOTP (RFC 6238):** time-based; counter được suy từ thời gian và step size.
- **OTT (Spring):** server tạo random one-time token và giao qua channel; không tự dùng shared authenticator seed.

Dù cùng là “mã dùng một lần”, giao thức, enrollment và cách replay khác nhau.

## 14. Java 17 runnable: tính TOTP theo vector chuẩn RFC 6238

Ví dụ Java thuần này giúp phân biệt TOTP khỏi OTT của Spring. Nó **chỉ** tính mã với test secret/timestamp đã biết, **không** triển khai enrollment, MFA server, replay ledger hoặc rate limiting.

Tạo file `TotpRfc6238Demo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class TotpRfc6238Demo {

    static String generate(byte[] secret, long unixSeconds, int digits)
            throws Exception {
        if (digits < 6 || digits > 8 || unixSeconds < 0) {
            throw new IllegalArgumentException("invalid TOTP parameters");
        }
        long movingFactor = unixSeconds / 30L;
        byte[] message = ByteBuffer.allocate(8)
                .putLong(movingFactor)
                .array();

        Mac mac = Mac.getInstance("HmacSHA1");
        mac.init(new SecretKeySpec(secret, "HmacSHA1"));
        byte[] digest = mac.doFinal(message);

        int offset = digest[digest.length - 1] & 0x0f;
        int binary = ((digest[offset] & 0x7f) << 24)
                | ((digest[offset + 1] & 0xff) << 16)
                | ((digest[offset + 2] & 0xff) << 8)
                | (digest[offset + 3] & 0xff);

        int divisor = 1;
        for (int i = 0; i < digits; i++) {
            divisor *= 10;
        }
        int otp = binary % divisor;
        return String.format(Locale.ROOT, "%0" + digits + "d", otp);
    }

    public static void main(String[] args) throws Exception {
        // Test secret và hai timestamps của RFC 6238 Appendix B.
        byte[] secret = "12345678901234567890"
                .getBytes(StandardCharsets.US_ASCII);

        System.out.println("59: " + generate(secret, 59L, 8));
        System.out.println("1111111109: "
                + generate(secret, 1111111109L, 8));
    }
}
```

Chạy JDK 17+:

```bash
javac TotpRfc6238Demo.java
java TotpRfc6238Demo
```

**Stdout chính xác theo RFC 6238 Appendix B (HMAC-SHA1, 8 chữ số):**

```text
59: 94287082
1111111109: 07081804
```

Phần production phải tách `verifyAndConsume`: lấy secret user đã enroll, tính các timestep cho phép, so sánh mã đúng định dạng/không mất leading zero, **ghi atomic last-used step**, rate limit và chỉ trả boolean/decision. Không sử dụng secret RFC mẫu cho bất kỳ user thật nào. Ở mức yêu cầu bảo đảm cao, ưu tiên authenticator chống phishing như WebAuthn phù hợp hơn TOTP.

## 15. Java 17 runnable: mô hình kiểm chứng nhiều factor theo session/version/TTL

Chương trình độc lập sau mô phỏng một **MFA proof policy** có kiểm tra:

- **Identity** và **session ID** phải trùng.
- **Security version** không bị đổi sau password reset/revoke.
- Mỗi factor bắt buộc phải có **proof khác nhau** còn hạn.
- Không chấp nhận proof “được cấp trong tương lai”.
- Hết thời hạn reauthentication thì mất hiệu lực.

Nó dùng Java 17 chuẩn, không cần Spring. Lưu `MfaProofPolicyDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Set;

public class MfaProofPolicyDemo {

    enum Factor { PASSWORD, TOTP, WEBAUTHN }

    record Proof(
            String userId,
            String sessionId,
            long securityVersion,
            Factor factor,
            Instant verifiedAt) {}

    static boolean allowed(
            String userId,
            String sessionId,
            long securityVersion,
            Instant now,
            Duration maxAge,
            Set<Factor> required,
            List<Proof> proofs) {

        if (maxAge.isNegative() || maxAge.isZero()) {
            return false;
        }
        for (Factor factor : required) {
            boolean found = proofs.stream().anyMatch(proof ->
                    proof.userId().equals(userId)
                    && proof.sessionId().equals(sessionId)
                    && proof.securityVersion() == securityVersion
                    && proof.factor() == factor
                    && !proof.verifiedAt().isAfter(now)
                    && now.isBefore(proof.verifiedAt().plus(maxAge)));
            if (!found) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        Instant t0 = Instant.parse("2026-01-01T10:00:00Z");
        Duration ttl = Duration.ofMinutes(10);
        Set<Factor> required = Set.of(Factor.PASSWORD, Factor.TOTP);
        Proof password = new Proof("alice", "S1", 7,
                Factor.PASSWORD, t0);
        Proof totp = new Proof("alice", "S1", 7,
                Factor.TOTP, t0.plusSeconds(60));

        System.out.println("password only: " + allowed(
                "alice", "S1", 7, t0.plusSeconds(90),
                ttl, required, List.of(password)));

        System.out.println("two factors: " + allowed(
                "alice", "S1", 7, t0.plusSeconds(90),
                ttl, required, List.of(password, totp)));

        System.out.println("other session: " + allowed(
                "alice", "S2", 7, t0.plusSeconds(90),
                ttl, required, List.of(password, totp)));

        System.out.println("version changed: " + allowed(
                "alice", "S1", 8, t0.plusSeconds(90),
                ttl, required, List.of(password, totp)));

        System.out.println("expired: " + allowed(
                "alice", "S1", 7, t0.plusSeconds(1200),
                ttl, required, List.of(password, totp)));
    }
}
```

Chạy:

```bash
javac MfaProofPolicyDemo.java
java MfaProofPolicyDemo
```

**Stdout chính xác:**

```text
password only: false
two factors: true
other session: false
version changed: false
expired: false
```

Đây là mô hình **authorization decision**, không có API HTTP, password verifier hay TOTP verifier. Trong production, proof phải được tạo **chỉ sau verification thật**, không nhận từ client, lưu trong store tin cậy, chống session fixation và được invalidate theo lifecycle. Việc dùng `Set<Factor>` chỉ ngăn duplicate **loại factor**, còn tính độc lập/rủi ro của authenticator phải do policy quyết định.

## 16. Tích hợp MFA step-up với endpoint nhạy cảm trên 6.x

### 16.1. Những URL cần đánh dấu MFA

Ví dụ:

| Endpoint | Yêu cầu |
| --- | --- |
| `GET /profile` | Authenticated user |
| `POST /profile/change-email` | Authenticated + fresh MFA + owner |
| `POST /passkeys/register` | Authenticated + recent strong proof |
| `POST /mfa/enroll` | Authenticated + recent reauthentication/step-up theo chính sách |
| `POST /mfa/disable` | Authenticated + MFA hoặc recovery tương đương |
| `POST /admin/transfer` | Role admin + MFA + workflow approval |
| `POST /sessions/revoke-all` | Authenticated + MFA/recent reauth |
| `GET /mfa/challenge` | Password-authenticated nhưng chưa có MFA vẫn được vào |
| `POST /mfa/verify` | Password-authenticated + CSRF + rate limit; proof chỉ cấp khi code đúng |

Nếu dùng `.requestMatchers("/admin/**").access(gate)` nhưng có `@PreAuthorize("hasRole('ADMIN')")` ở service gọi từ một **internal endpoint khác**, đường vào khác đó có thể bỏ qua gate. Định nghĩa **defense-in-depth** ở service/transaction boundary cho các hành động nhạy cảm và bảo đảm interceptor/session context phù hợp.

### 16.2. Browser vs API

- **Browser session flow:** 302 tới `/mfa/challenge` có thể hợp lý khi thiếu factor.
- **REST API/SPA:** nên trả status/code có contract như `403 step_up_required` hoặc `401 reauthentication_required` tùy authentication semantics, kèm challenge initiation metadata an toàn; đừng trả HTML login page trong JSON API.
- **Resource server stateless:** không mặc định mở server session để lưu `MfaProof` nếu policy của API là Bearer; assurance phải được xác minh từ trusted token/authorization server hoặc một step-up flow phát token mới.

### 16.3. Khi user mới xác thực factor một, phải chặn quyền nhạy cảm

Một password-authenticated session là hợp lệ theo Spring Security `Authentication`, nhưng MFA gate phải từ chối sensitive operations cho đến khi proof thứ hai được cấp. Nếu app dùng `anyRequest().authenticated()` cho mọi endpoint, sau password login có thể truy cập tất cả mà không bao giờ tới OTP page: **đây là policy bug**, không phải lỗi của `ProviderManager`.

## 17. Tích hợp IdP/OIDC để giảm mã tự xây

Một lựa chọn tốt cho nhiều hệ thống là đưa MFA vào **Identity Provider** có hỗ trợ WebAuthn/FIDO, TOTP, recovery, user lifecycle và audit, rồi app Spring Security dùng `oauth2Login` (browser) hoặc `oauth2ResourceServer` (API) với **assurance policy**.

### 17.1. Không coi OAuth2 login tự động là MFA

Một successful OIDC login chứng minh IdP đã xác thực một danh tính theo policy của IdP. Nếu cần assurance cụ thể, ứng dụng có thể phải yêu cầu/kiểm:

- `acr` — Authentication Context Class Reference, **giá trị theo hợp đồng với IdP**.
- `amr` — Authentication Methods References, danh sách phương thức được IdP khai báo (nếu có).
- `auth_time` — thời điểm user authentication tại IdP, khác `iat` token.
- Issuer/audience/nonce/expiry, `azp` khi applicable.
- `max_age` hoặc `prompt=login` trong OIDC request khi yêu cầu fresh authentication; IdP có thực sự tuân thủ contract không?
- Session/token refresh có giữ được assurance cần thiết không?

**`amr=["pwd","otp"]` là dữ liệu đáng tin chỉ sau khi token đã được signature/issuer/audience validated và issuer thật sự phát hành các claims này theo hợp đồng.** Không tự đặt `amr` ở frontend hoặc tin mọi IdP đều dùng cùng một code string.

### 17.2. Step-up qua OIDC

```text
RP/Spring application
  -> detects missing/freshness requirement
  -> redirects user to OP/IdP with agreed acr_values/max_age
  -> OP enforces policy, issues new validated assertion
  -> RP validates ID token/claims/auth_time/nonce and account linkage
  -> RP grants sensitive access for bounded window
```

Đây là **thiết kế khái quát**. Các IdP hỗ trợ `acr_values`, `claims` parameter, `prompt` hoặc proprietary conditional access theo cách khác nhau; không có một API Spring duy nhất buộc mọi IdP làm MFA. Nên làm integration tests với IdP thực hoặc sandbox thay vì chỉ mock claim `acr`.

### 17.3. Không trộn trusted IdP assurance và local session flags

Nếu user đã logout, account bị disable hoặc token thay đổi, một local `mfa=true` từ phiên cũ không được dùng để bỏ qua new IdP policy. Ràng buộc assurance theo principal, tenant, phiên và giới hạn thời gian; khi cần revoke, xử lý cả RP session lẫn IdP grants theo khả năng.

## 18. Resource Server/JWT, opaque token và nhiều microservices

Với một Spring Resource Server nhận `Authorization: Bearer ...`:

- `BearerTokenAuthenticationFilter` xác thực access token qua JWT decoder hoặc introspector.
- `JwtAuthenticationConverter` có thể map claims sang authorities, nhưng **không tự biết** session browser của user đã qua TOTP ở frontend khác.
- `FACTOR_BEARER` ở Security 7 nói về Bearer mechanism, **không phải assurance MFA từ IdP**.
- Một custom `amr`/`acr` authorization manager phải chỉ tin issuer/claims đã xác minh và áp policy theo từng endpoint/action.
- Nếu API cần recent MFA nhưng access token được phát trước step-up, cần token exchange/reissue/claims challenge theo kiến trúc AS; chỉ đổi local session attribute ở web app không tự đổi JWT.

### 18.1. JWT code minh họa kiểm claim có điều kiện

```java
// Trích đoạn sau khi JwtDecoder đã xác minh JWT;
// đây chưa phải full AuthorizationManager.
Jwt jwt = jwtAuthenticationToken.getToken();
List<String> amr = jwt.getClaimAsStringList("amr");
String acr = jwt.getClaimAsString("acr");

boolean reportedStrong = amr != null
        && amr.contains("hwk"); // Chỉ ví dụ: mapping do issuer contract định nghĩa.
// KHÔNG dùng boolean này làm policy đầy đủ; phải kiểm issuer/audience,
// required acr, auth_time/freshness, audience và business action.
```

Không tự chọn `"hwk"` làm bảo đảm chung cho mọi issuer; các claims cần được định nghĩa bởi hợp đồng của IdP. Nếu token không có claims bắt buộc và action yêu cầu MFA, **fail closed**, không coi thiếu `amr` là “MFA optional” trừ khi policy explicitly cho phép.

### 18.2. OAuth refresh token và MFA freshness

Refresh token có thể phát access token mới mà user không nhập factor mới. **Access token mới phát hành không có nghĩa MFA mới diễn ra**. Với recent step-up, cần `auth_time`/acr policy đáng tin hoặc yêu cầu interactive reauthentication. Tránh lấy `iat` của access token để suy “vừa MFA”.

## 19. WebFlux và Reactive: không copy nguyên annotation Servlet

Spring WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, Reactor context/`ReactiveSecurityContextHolder` và `ReactiveAuthenticationManager`.

**Theo javadoc Spring Security 7 về `@EnableMultiFactorAuthentication`, tính năng này ở thời điểm tài liệu nêu chưa áp dụng cho reactive applications.** Vì vậy:

- Không copy Servlet `@EnableMultiFactorAuthentication` rồi kết luận mọi `SecurityWebFilterChain` tự yêu cầu nhiều factor.
- Với WebFlux, xây một `ReactiveAuthorizationManager<AuthorizationContext>` kiểm proof/claims an toàn, hoặc đưa MFA sang IdP và validate assurance.
- Không gọi JDBC/TOTP repository blocking ngay trên Netty event loop.
- Reactor Context khác Servlet ThreadLocal; không lấy `SecurityContextHolder` kiểu Servlet làm nguồn chính trong reactive pipeline.
- Session WebFlux/`WebSession` proof cần đồng bộ multi-node, TTL, logout và replay checks riêng.
- Test bằng `WebTestClient`/`StepVerifier`; MockMvc dành cho Servlet.

Ví dụ DSL **minh họa**, chưa có proof verifier:

```java
// Trích đoạn WebFlux, không phải file runnable độc lập.
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/mfa/**").authenticated()
        .pathMatchers("/admin/**").access(reactiveMfaManager)
        .anyExchange().authenticated());
```

`reactiveMfaManager` phải là bean có implementation đúng kiểu reactive, không được là Servlet `AuthorizationManager<RequestAuthorizationContext>`.

## 20. Trạng thái account, enrollment, recovery và factor independence

### 20.1. Enrollment là security-sensitive operation

MFA enrollment cần xác minh user đang sở hữu account (recent auth/step-up), thiết lập secret/credential server-side, yêu cầu user chứng minh sở hữu factor mới (confirmation code/attestation theo policy), commit trong transaction và gửi thông báo.

**Không** cho phép một session chỉ cần password bị lộ thêm một TOTP secret mới rồi attacker dùng secret đó để vượt MFA của chủ tài khoản. Một account chưa enroll cần onboarding/identity proofing có mức assurance hợp lý, không phải fallback “skip OTP” không kiểm chứng.

### 20.2. Disable/re-enroll

Hủy TOTP/passkey, đổi số điện thoại, thay email recovery, reset password, sửa roles hoặc account status đều có thể thay đổi assurance. Cần invalidation của:

- Current MFA proof trong session.
- Các sessions/remember-me cookies liên quan theo policy.
- Trusted device remember flags và MFA bypass grants.
- Refresh tokens/access token claims nếu có cơ chế hỗ trợ revoke/reissue.
- Recovery codes/backup factors bị rủi ro.
- Device-bound credential bindings và support workflows.

Tốt nhất lưu `securityVersion`/stamp trên account và so sánh với proof ở mỗi sensitive operation; tăng version khi security event. Phải đảm bảo cache invalidation/consistency giữa nodes.

### 20.3. Recovery code không được thành bypass vô thời hạn

Một mã recovery phải đủ entropy, dùng một lần, hash ở server, không hiển thị lại sau setup, và phải bị vô hiệu sau khi dùng. Recovery có thể thay thế một factor trong hoàn cảnh xác định, nhưng **không** tự gắn `FACTOR_WEBAUTHN` hoặc `FACTOR_TOTP` sau khi user nhập một email link yếu. Ghi nhận riêng `FACTOR_RECOVERY`/assurance khi custom integration và đặt giới hạn hành động sau recovery.

### 20.4. Không có factor thứ hai do outage

Nếu SMS gateway/TOTP store/IdP hết kết nối, không nên tự trả `mfaVerified=true` để người dùng tiếp tục. Có runbook **fail closed** cho operations nhạy cảm, availability options (backup authenticator, recovery đúng quy trình, privileged break-glass được kiểm toán) và thông báo tình trạng, tránh tạo “fail-open” authentication bypass.

## 21. Ghi factor proof và an toàn phiên đăng nhập

MFA proof nên có:

| Thuộc tính | Mục đích |
| --- | --- |
| `accountId`, `tenantId` | Gắn đúng user và tổ chức |
| `sessionId`/device binding | Chống copy proof sang session khác |
| `factorKind` và `authenticatorId` | Loại yếu tố/credential đã kiểm, tránh hai lần cùng factor |
| `verifiedAt`, `expiresAt` | Expiry và recent reauthentication |
| `securityVersion` | Revoke khi password/reset/account policy thay đổi |
| `assuranceLevel` hoặc trusted `acr` | Kết nối assurance với yêu cầu nghiệp vụ |
| `challengeId`, one-time consume ID | Chống replay/double submit |
| `riskContext` và eventId | Audit/correlation, không log secret |

**Không** lưu `mfaPassed=true` vô hạn trong bảng người dùng, role hoặc localStorage. Enrolled status là **capability của account**, verified status là **bằng chứng của lần xác thực/phiên**.

### 21.1. Session fixation và rotation

Sau successful first-factor auth, Spring Security thường có session fixation protection; nếu bạn viết custom login/challenge, hãy bảo đảm không tái dùng session bị attacker áp đặt. Proof nên gắn với session **hiện tại sau rotate**, và không được copy sang session mới trừ policy đã xác minh.

### 21.2. Remember-me

`RememberMeAuthenticationToken` có thể được xem là authenticated nhưng không fully authenticated. Với hoạt động MFA-sensitive, không chấp nhận chỉ remember-me; yêu cầu recent full authentication và factor evidence theo policy. `fullyAuthenticated()` **không có nghĩa đã MFA**, nó chỉ phân biệt với anonymous/remember-me.

### 21.3. Logout không tự revoke mọi token

Logout local xóa HttpSession/proof nhưng không tự thu hồi JWT offline ở resource servers, IdP SSO session, OAuth refresh grants, passkeys hoặc các remember-me cookies bị sao chép. Thiết kế revocation trong từng store và test cửa sổ hiệu lực.

## 22. Test case cần có cho Spring Security 7

### 22.1. Authentication path và authorities

Khi app 7.x cấu hình password + OTT:

1. Password đúng, chưa OTT: đủ `FACTOR_PASSWORD` nhưng **chưa đủ** authorization cho protected route.
2. OTT đúng, chưa password (khi mechanism cho phép login độc lập): `FACTOR_OTT` chưa đủ nếu rule yêu cầu cả hai.
3. Password rồi OTT: đủ factor rules, route cho phép nếu role cũng đủ.
4. Password rồi OTT của **account khác**: không được hợp nhất authorities giữa users.
5. OTT expire/replay: không cấp factor authority.
6. User role thiếu dù MFA đủ: vẫn 403.
7. User logout/new session: factor authorities của session cũ không được dùng lại.
8. User thay password/revoke factor: proof/authorities phải bị invalidated theo policy.
9. Ngày giờ đổi/required validDuration hết: yêu cầu step-up lại.
10. Custom `AuthenticationProvider` không được cấp `FACTOR_TOTP` trước khi verify server-side.
11. Khi dùng nhiều filter chains, factor rules bảo vệ **đúng chain và endpoints**.
12. Method security `@PreAuthorize`/service layer có chính sách tương đương request layer.

### 22.2. Đừng dùng with(user()) để chứng minh MFA thật

Spring Security Test có helpers như `with(user("alice"))` hoặc `@WithMockUser`. Chúng đưa Authentication test vào request, thường **bỏ qua login filters và factor verification**. Có thể dùng để test role gating, nhưng không dùng để khẳng định MFA end-to-end thành công.

Để kiểm tra MFA 7.x, dùng form login/OTT/WebAuthn test flow phù hợp và assert kết quả **factor authorities** qua trusted authentication path; sau đó gọi protected routes. Cần test 401/302/403 và challenge endpoint, không chỉ status 200. Nếu mock authority để unit test factory, ghi rõ đó chỉ là **authorization unit test**.

### 22.3. Điều phải kiểm sau upgrade

Với project nâng từ Boot 3/Security 6 lên Boot 4/Security 7:

- Có đủ factor authorities trên Authentication từ built-in filters không?
- Full login/step-up có giữ/merge authorities **cùng identity** khi chuyển factors không?
- User đã enroll factor nhưng chưa xác minh có bị deny đúng không?
- `@EnableMultiFactorAuthentication` được áp dụng cho URL/method rules nào; custom DSL/AuthorizationManager có bypass factory không?
- WebFlux app có thực sự sử dụng MFA custom/IdP mà không tin annotation Servlet?
- CSRF/session fixation/request cache/OIDC callback vẫn an toàn.
- Backward compatibility của session serialization khi deploy rolling upgrade.
- Account disable, recovery, logout, token refresh và IdP assurance propagation vẫn đúng.

## 23. Test case cần có cho Spring Security 6.x tự xây

| # | Tình huống | Kỳ vọng |
| --- | --- | --- |
| 1 | User anonymous gọi endpoint protected | Từ chối, không tạo MFA proof |
| 2 | Password đúng, chưa TOTP | Chỉ vào routes single-factor; sensitive action bị chặn |
| 3 | Password sai | Không được mở OTP flow thành một authenticated bypass |
| 4 | User đã enroll TOTP nhưng chưa nhập mã | Vẫn chưa MFA |
| 5 | TOTP sai định dạng/leading zero | Từ chối an toàn |
| 6 | TOTP sai 10 lần | Rate limit/lockout theo policy, không brute force |
| 7 | TOTP đúng trong bounded time window | Ghi proof đúng identity/session/version |
| 8 | Cùng code TOTP replay | Atomic last-use ledger từ chối |
| 9 | Hai requests cùng code đồng thời | Một consume thành công, một bị từ chối |
| 10 | MFA proof đúng, trong TTL | Endpoint protected cho phép nếu role/owner đúng |
| 11 | Proof đúng nhưng thiếu `ROLE_ADMIN` | Từ chối admin route |
| 12 | Proof session S1, request session S2 | Từ chối |
| 13 | Proof của Alice, request Bob | Từ chối |
| 14 | Proof trong tương lai | Từ chối |
| 15 | Proof hết hạn | Từ chối/step-up |
| 16 | Account securityVersion tăng | Từ chối proof cũ |
| 17 | Account disabled/deleted sau MFA | Từ chối, revoke session |
| 18 | Logout rồi tái dùng cookie/session | Không dùng được proof cũ |
| 19 | Remember-me only | Không được giả MFA |
| 20 | POST /mfa/verify không CSRF | 403, không ghi proof |
| 21 | POST /mfa/verify anonymous | Không tạo proof/không tiết lộ enrollment |
| 22 | Request MFA challenge khác account | Không dùng challenge/OTP của người khác |
| 23 | Thay password/email/passkey | Revoke hoặc yêu cầu re-enroll theo policy |
| 24 | Recovery code dùng hai lần | Lần hai bị từ chối |
| 25 | Session cookie bị đánh cắp | Proof/session binding/step-up theo threat model |
| 26 | Redis outage hoặc node mất state | Sensitive action fail closed |
| 27 | Trusted IdP `acr/amr` giả từ client | Không chấp nhận |
| 28 | JWT chỉ có Bearer không có assurance | Không tự coi đủ MFA |
| 29 | API khác endpoint URL nhưng gọi cùng service | Service-layer gate bảo vệ |
| 30 | Unenrolled user | Enrollment/recovery flow có assurance, không skip |
| 31 | CSRF/CORS cross-origin | Không lộ secret/challenge hoặc bypass |
| 32 | Cluster 2 nodes | Consistent one-time counter và proof invalidation |
| 33 | Session fixation attacker-chosen ID | Không chuyển MFA proof sai session |
| 34 | Clock skew | Chỉ chấp nhận cửa sổ rõ, audit thực tế |
| 35 | Break-glass | Có phê duyệt/audit/TTL, không mặc định |
| 36 | Upgrade version | Regression test trước/sau migration cùng policy |

**Mục tiêu kiểm thử:** chứng minh **negative paths**: người mới qua password chưa thể vào critical operations, người có proof sai phiên/hết hạn bị từ chối, và khi factor service gặp sự cố không có fallback ít an toàn.

## 24. Cách kiểm thử Spring Security 6 custom gate bằng MockMvc

Giả sử có `SessionMfaGate` mục 12 trong `SecurityFilterChain`. Test không cần TOTP thật để kiểm **gate itself**: có thể cấp một `MfaProof` đã biết trong test session và dùng `with(user(...))` như fixture authorization, nhưng phải ghi rõ **đây chỉ là unit/integration test của gate**, không phải kiểm thử xác minh OTP.

Ví dụ **trích đoạn trong Spring Boot 3.x MockMvc test**, không phải file độc lập:

```java
MockHttpSession session = new MockHttpSession();
session.setAttribute(SessionMfaGate.PROOF_ATTRIBUTE,
        new MfaProof("alice", session.getId(), 1L, "TOTP",
                clock.instant(), clock.instant().plusSeconds(300)));

mvc.perform(get("/admin/report")
        .session(session)
        .with(user("alice").roles("ADMIN")))
    .andExpect(status().isOk());
```

Đoạn trên giả định `clock` của gate được inject test clock, endpoint `/admin/report` tồn tại, và mapping principal name `alice` trùng proof. Vì `with(user(...))` bypass actual authentication, **không tuyên bố đã kiểm password+TOTP**. Thêm negative tests: no proof, expired, wrong session, wrong user, version changed và missing admin role. Với test gate được đưa vào app security config cần đảm bảo role check **cùng tồn tại**.

### 24.1. E2E test mới chứng minh MFA

Tầng E2E nên gửi form password/CSRF **thật**, lấy session sau first factor, submit TOTP/WebAuthn qua endpoint thực, rồi thử sensitive action. Không dùng `@WithMockUser` để kết luận flow hoàn chỉnh. Khi test code sử dụng shared store, chạy ít nhất hai app instances để bắt replay race.

## 25. Chẩn đoán lỗi thường gặp theo triệu chứng

### “Không thấy `@EnableMultiFactorAuthentication` trong IDE”

Kiểm resolved Spring Security version. API này **từ 7.0**. Trên Boot 3/Security 6.5 cần custom gate/IdP hoặc nâng major stack; không trộn 7.x config jar vào 6.x core.

### “Tôi bật `oneTimeTokenLogin()` ở 6.5 nhưng user vẫn vào admin bằng password”

Đó là hành vi đúng nếu authorization chỉ yêu cầu `authenticated()`. OTT và password là **hai authentication mechanisms**, không tự là điều kiện AND. Cần rule MFA riêng; tránh thêm factor code giả vào `UserDetails.getAuthorities()`.

### “Spring 7 login bằng password xong cứ redirect OTP nhưng không nhận được link”

Kiểm OTT **generation success handler** và email/SMS/transport. Framework không tự biết kênh giao token. Kiểm privacy/one-time storage/rate limit, tránh in token vào log để thử production.

### “Mã email magic link được gọi là TOTP”

Không đúng thuật ngữ. OTT server tạo token, TOTP app client tính mã từ enrolled shared secret/time. Đừng áp chính sách TOTP counter/replay lên OTT như thể format giống nhau; cả hai cần one-time usage nhưng cơ chế khác.

### “User có passkey rồi, sao vẫn phải dùng password?”

Có thể policy global `PASSWORD+WEBAUTHN`, trong khi thiết kế muốn WebAuthn đủ assurance **hoặc** password+TOTP. Định nghĩa allowed combinations/conditional MFA trong 7.x và kiểm UV/user verification đúng. Đừng bỏ password tùy tiện nếu một loại passkey thực tế chỉ chứng minh possession chưa đủ mức assurance mục tiêu.

### “Một người dùng khác nhận được factor authority của user trước”

Có nguy cơ session context/authority merge sai principal khi chạy step-up. Kiểm stable user ID, session binding, authentication replacement/merging và test chuyển tài khoản trong cùng browser. **Không** đơn giản union authorities từ một Authentication cũ sang user khác.

### “TOTP đúng hai lần đều được chấp nhận”

Bạn mới tính mã mà chưa có **atomic replay tracking**. Lưu last accepted timestep/challenge ID trong store nhất quán, dùng conditional update/transaction; kiểm tra đa node và requests đồng thời.

### “TOTP pass rồi logout nhưng vẫn vào được qua cookie”

Session hoặc remember-me/refresh token chưa được thu hồi; hoặc server proof chưa bị xóa. Chia rõ authentication session, MFA proof, remember-me cookies và OAuth grants. Logout local không tự revoke mọi credential ở IdP/AS.

### “Ứng dụng WebFlux đã annotate MFA nhưng API vẫn cho vào”

Annotation Servlet MFA 7.x không được giả định áp vào reactive security. Cần reactive gate/IdP assurance, test bằng WebTestClient và kiểm Reactor context. Không copy `HttpSecurity`/`SecurityContextHolder` ThreadLocal sang WebFlux.

### “JWT có `amr=mfa` nhưng API vẫn 403”

Có thể authorization manager yêu cầu một `acr` khác, token từ issuer không tin cậy, thiếu `auth_time`/freshness, token không có đúng audience hoặc trusted converter không map assurance. **Không** fix bằng cách bỏ signature/audience check.

### “MFA proof ở Redis mất khi restart và admin bị khóa khỏi app”

Nếu policy yêu cầu protected operations, fail closed là đúng, nhưng UX/availability cần recovery/step-up lại. Thiết kế Redis persistence, replication, backup factor và incident runbook; không tự set verified khi store outage.

## 26. Kế hoạch chuyển từ Spring Security 6.5 sang 7.x

1. **Inventory** security features: login mechanisms, sessions, remember-me, OTT/WebAuthn/TOTP custom, resource server, OIDC, multi-chain, CSRF, authz và reactive modules.
2. **Pin BOM** tương thích Spring Boot/Spring Security theo release đang dùng; xác minh resolved dependencies và migration guide.
3. **Viết tests trước:** first-factor only bị deny ở endpoints nhạy cảm, full MFA success, wrong-account/session, TTL, replay, recovery, disabled accounts.
4. **Quyết định factor semantics:** Password+OTT? WebAuthn only? Password+TOTP custom? External IdP assurance? Đừng nhầm OTT với TOTP.
5. **Bật MFA 7.x** ở một môi trường test Servlet; dùng annotation cho global hoặc MFA factory cho selective rules, tránh hai nguồn policy mâu thuẫn.
6. **Gỡ custom gate cũ từng phần** chỉ sau khi chứng minh built-in factor authority bảo vệ mọi paths tương đương, kể cả `@PreAuthorize` và các APIs.
7. **Giữ lại custom parts cần thiết:** TOTP verifier, enrollment, delivery, recovery, audit, risk policy, lifecycle, IdP step-up và token assurance.
8. **Test session migration/rolling deploy:** Spring Security 7 thay đổi kiểu Authentication/factor authorities; session từ phiên bản cũ có thể không chứa factors mới và phải reauthenticate thay vì được tự nâng assurance.
9. **WebFlux riêng:** không suy annotation Servlet sẽ protect reactive routes.
10. **Rollout theo canary**, đo login drop-off, challenge success, factor enrollment, replay events, 401/403/redirect loops, session invalidation và support cases.
11. **Không tự phát authority vào principal** để làm test xanh nếu chưa có verified factor.
12. **Rollback có kiểm soát:** nếu rollback về 6.5, custom MFA gate/IdP enforcement phải còn hoạt động; không hạ xuống password-only mà không có quyết định bảo mật rõ ràng.

### 26.1. Các API/DSL thay đổi cần lưu ý

Spring Security 7 loại bỏ hoặc thay một số API cũ: ví dụ `AuthorizationManager#check` chuyển sang `authorize`, `HttpSecurity.and()` cũ bị bỏ khỏi lambda DSL, và authentication builder có cơ chế mới để merge authorities/factor proof. Đừng compile nguyên source code custom gate 6.5 lên 7 mà không sửa/adapt theo migration guide; thay đổi đó cần test security semantics, không chỉ “build xanh”.

## 27. Bảng quyết định chọn phương án

| Hiện trạng và yêu cầu | Hướng ưu tiên | Vì sao |
| --- | --- | --- |
| App Servlet Boot 4/Security 7, yêu cầu password+OTT | Built-in MFA 7 + OTT delivery + policy tests | Đỡ viết factor-tracking core |
| App Servlet Security 7, yêu cầu WebAuthn step-up | Built-in WebAuthn/factor policy với bảo đảm UV phù hợp | Factor authority/conditional rules có sẵn |
| App Boot 3/Security 6.5, password + authenticator TOTP | Custom gate/IdP + TOTP library/service | Không có `@EnableMultiFactorAuthentication`; OTT không phải TOTP |
| App Boot 3/Security 6.5, đã có IdP MFA mạnh | OIDC login + verified assurance mapping | Tránh duplicate enrollment/recovery |
| App WebFlux, hiện dùng JWT/OIDC | Reactive authorization hoặc IdP step-up | Không giả định Servlet MFA annotation hoạt động |
| API nhiều microservices, cần recent MFA | Token assurance contract tại AS/RS | Không dựa vào browser session của một service |
| Compliance ưu tiên chống phishing | WebAuthn/FIDO2 với UV/assurance và recovery phù hợp | OTP/email dễ bị phishing/compromise |
| Chưa có năng lực account recovery an toàn | Thiết kế recovery trước khi rollout rộng | MFA dễ bị bypass qua helpdesk/email fallback |
| Cần disable/revoke ngay trên nhiều node | Shared session/grant revocation + version checks | Authenticated token cũ có thể tiếp tục còn hiệu lực |

**Nguyên tắc chọn:** thư viện hỗ trợ giảm phần **orchestration** bạn phải tự viết, nhưng assurance, lifecycle và deployment-specific risks vẫn cần policy, dữ liệu và tests của sản phẩm.

## 28. Checklist bàn giao triển khai MFA theo phiên bản

1. Đã kiểm chính xác Spring Boot/Security **resolved versions** và phân biệt Servlet/WebFlux.
2. Đã ghi rõ MFA là **AND/anyOf combinations**, không phải “chỉ bật nhiều login mechanisms”.
3. Đã chọn factor độc lập theo threat model, không coi email magic link tự động là NIST AAL2.
4. Trên Security 7 đã dùng `@EnableMultiFactorAuthentication` hoặc MFA factory **đúng phạm vi**, không vô tình để custom AuthorizationManager bypass.
5. Trên Security 6.5 đã có **server-side authorization gate** hoặc trusted IdP assurance, không dựa frontend.
6. Đã xác định mechanism cho mỗi factor, enrollment, verification, TTL, replay storage, rate limit và UX.
7. TOTP dùng RFC 6238 được kiểm chứng với vectors, **có atomic consume** và không log secret.
8. WebAuthn kiểm RP ID/origin/challenge/UV, public-key bindings và trusted credential repository.
9. OTT delivery handler/channel hoạt động, có one-time consume, chống enumeration/resend abuse; hiểu OTT khác TOTP.
10. Session/authentication proof bind account, tenant, session, security version, factor, verifiedAt/expiry.
11. Account disable, password reset, remove passkey, lost device, logout đều có revoke/step-up policy.
12. Sensitive endpoints kiểm cả **role/scope/ownership** và MFA, kể cả method/service entry points khác.
13. API Bearer/OIDC chỉ tin assurance **từ token đã validate** theo issuer contract, không tự suy từ `FACTOR_BEARER`.
14. WebFlux có reactive implementation và WebTestClient tests riêng.
15. Có negative tests cho password-only, wrong factor, replay, expired proof, cross-session, wrong user và cache/node outages.
16. CSRF, session fixation, CORS, Secure/HttpOnly/SameSite và transport TLS vẫn đúng.
17. Recovery codes và helpdesk không tạo đường yếu hơn MFA chính.
18. Rollout có logs/metrics theo loại factor/decision nhưng **không bao giờ** log raw OTP, password, token hoặc private key.
19. Đã chuẩn bị migration/rollback và kế hoạch khi nâng major Spring Security.
20. Có tài liệu cho frontend, support, security operations và người dùng về lúc cần step-up và cách khôi phục.

**Kết luận:** Spring Security **6.5** có nhiều **authentication mechanisms** hữu ích nhưng **chưa có first-class MFA factor policy** của 7.x. Spring Security **7.0+** thêm `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication` và cấu hình factor-aware authorization cho Servlet. Dù dùng phiên bản nào, **MFA chỉ đáng tin khi yếu tố thật sự được xác minh, bằng chứng bị giới hạn theo phiên/người dùng/thời gian, resource nhạy cảm có enforcement và recovery không làm yếu mô hình**.

## 29. Tài liệu chính thức và tiêu chuẩn

- [Spring Security 7 — Multi-Factor Authentication (Servlet)](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/mfa.html): `FactorGrantedAuthority`, annotation, selective rules, dynamic conditions, validity và factor combinations.
- [Spring Security 7 — What's New](https://docs.spring.io/spring-security/reference/7.0/whats-new.html): first-class MFA trong 7.0, thay đổi authentication/authorization API.
- [Spring Security 7 — FactorGrantedAuthority Javadoc](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html): `PASSWORD_AUTHORITY`, `OTT_AUTHORITY`, `WEBAUTHN_AUTHORITY`, `issuedAt`, API từ 7.0.
- [Spring Security 7 — EnableMultiFactorAuthentication Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/authorization/EnableMultiFactorAuthentication.html): annotation và ghi chú về phạm vi reactive.
- [Spring Security 6.5 — One-Time Token Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html): OTT khác TOTP/HOTP; delivery handler, service, JDBC/token lifecycle.
- [Spring Security 6.5 — Passkeys](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html): `webAuthn()`, dependencies, repositories, RP ID/origins.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): authentication providers, filters, SecurityContext, authorities.
- [Spring Security — Servlet Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager` và quyền truy cập.
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): các rule reactive và `ServerHttpSecurity`.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): session persistence, fixation và security context.
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): authorization-code login và IdP integration.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT validation/claims/authorization.
- [Spring Blog — Multi-Factor Authentication in Spring Security 7](https://spring.io/blog/2025/10/21/multi-factor-authentication-in-spring-security-7/): thiết kế progressive authorities và factor policy.
- [RFC 4226 — HOTP](https://www.rfc-editor.org/rfc/rfc4226): HMAC-based One-Time Password.
- [RFC 6238 — TOTP](https://www.rfc-editor.org/rfc/rfc6238): Time-Based OTP và test vectors Appendix B.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `acr`, `amr`, `auth_time`, `max_age`, claims validation.
- [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html): AAL2, replay resistance, phishing resistance và email không dùng làm out-of-band authenticator.
- [OWASP Multi-Factor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html): enrollment, recovery, risk, bypass protection.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): reauthentication, throttling và generic error messages.
