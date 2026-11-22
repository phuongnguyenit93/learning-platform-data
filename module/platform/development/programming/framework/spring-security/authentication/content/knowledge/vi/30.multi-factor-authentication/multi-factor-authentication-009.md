# Kiểm soát mọi đường đăng nhập, remember-me và khôi phục tài khoản trong MFA

## 1. Vấn đề cốt lõi: MFA mạnh đến đâu cũng vô ích nếu có đường vòng

Một ứng dụng có thể yêu cầu **mật khẩu + mã OTP** trong giao diện `/login`, nhưng người tấn công vẫn chiếm tài khoản nếu có thể đăng nhập thành công qua một đường khác chỉ với mật khẩu, magic link, cookie remember-me, token từ API cũ hoặc chức năng khôi phục tài khoản yếu.

**Nguyên tắc thiết kế:** Chính sách nhiều yếu tố xác thực (**Multi-Factor Authentication, MFA**) cần được áp dụng tại **ranh giới cấp quyền truy cập** và các luồng **đăng nhập/khôi phục**, chứ không chỉ được gọi trong một controller của trang login. Mỗi cách tạo `Authentication`, khôi phục session hoặc thay thế yếu tố xác thực phải được xét theo cùng chính sách assurance.

Bài học giúp bạn:

1. Lập danh mục **toàn bộ cách vào tài khoản**: form login, SSO, passkey, OTT, API, remember-me, recovery, help desk, thiết bị tin cậy và các endpoint legacy.
2. Phân biệt **đã xác thực**, **đã xác thực bằng những yếu tố nào**, **yếu tố còn mới hay không** và **được phép làm gì**.
3. Hiểu `RememberMeAuthenticationToken`, cơ chế cookie/DB của remember-me và vì sao tự động đăng nhập **không** chứng minh MFA.
4. Dùng cơ chế MFA tích hợp của **Spring Security 7.x** như `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication`, và hiểu giới hạn của cấu hình **6.x**.
5. Thiết kế recovery codes, reset password, thay thế authenticator và hỗ trợ thủ công sao cho không tạo đường vòng MFA.
6. Kiểm thử các ca **bypass** (âm tính) thay vì chỉ thử login thành công trên giao diện chính.

**Phạm vi:** ứng dụng Java 17+ trên Spring Security Servlet/Spring MVC. API `@EnableMultiFactorAuthentication` thuộc **Spring Security 7.0+**; không áp dụng nguyên xi cho Spring Security 6.5. Luồng SSO có thể ủy thác MFA cho IdP, nhưng application phải xác minh **bằng chứng assurance đáng tin** theo hợp đồng với IdP.

## 2. Phân biệt bốn khái niệm trước khi viết code

| Khái niệm | Câu hỏi phải trả lời | Ví dụ |
| --- | --- | --- |
| **Authentication** | Request đến từ principal nào và bằng cơ chế nào? | `Authentication` đã được xác minh với username `linh` |
| **Authentication factor** | Người dùng đã chứng minh những yếu tố độc lập nào? | Password + TOTP; WebAuthn có user verification phù hợp |
| **Authentication assurance / freshness** | Bằng chứng đủ mạnh và còn mới cho hành động này không? | Đã hoàn thành factor thứ hai trong 10 phút vừa qua |
| **Authorization** | Principal có quyền thực hiện thao tác nghiệp vụ này không? | Có `ROLE_ADMIN` và đạt MFA phù hợp |

Ví dụ người dùng có `ROLE_ADMIN` nhưng chỉ đăng nhập từ remember-me cookie vẫn có thể **thiếu bằng chứng MFA**. Ngược lại, đã hoàn thành MFA không có nghĩa được tự động nhận `ROLE_ADMIN`.

Khái niệm **factor** theo chính sách tổ chức đòi hỏi các bằng chứng độc lập phù hợp, thường từ những nhóm *something you know*, *something you have*, *something you are*. Hai password khác nhau không tự thành MFA. Hai OTP gửi về cùng một mailbox đã bị kiểm soát cũng không đương nhiên tạo hai yếu tố độc lập.

**MFA enforcement** nên diễn ra nơi ứng dụng quyết định cho phép vào tài nguyên, thiết lập session mạnh hơn hoặc thực thi giao dịch nhạy cảm. Chỉ cài thêm form OTP mà `anyRequest().authenticated()` vẫn chấp nhận mọi kiểu `Authentication` có thể để lại bypass.

## 3. Tư duy theo “đường vào tài khoản” thay vì “trang đăng nhập”

Một account thường có nhiều cửa vào:

```text
                            +-----------------+
   Password form ---------->|                 |
   OTP / OTT -------------->|                 |
   SAML / OIDC SSO -------->| Authentication  |----> Authentication
   Passkey/WebAuthn ------->| mechanisms      |       + factor evidence
   Remember-me cookie ----->|                 |               |
   Legacy Basic ----------->|                 |               v
   JWT / API token -------->|                 |        Centralized policy
   Recovery code ---------->|                 |          + freshness
   Reset-password flow ---->|                 |               |
   Support/admin flow ----->|                 |               v
                            +-----------------+        Resource / operation
                                                               |
                                                  allow / step-up / deny
```

Với mỗi đường, hãy tự hỏi: nó có thể **tạo session** hay `Authentication` mà không đi qua yêu cầu MFA không? Nó có thể **thay email/phone/factor** rồi cho đăng nhập dễ hơn không? Nó có thể cấp **access token** cho cùng API nhưng thiếu bằng chứng MFA không?

### Ma trận rà soát (bản tối thiểu)

| Đường vào | Điều có thể khẳng định | Rủi ro nếu không kiểm soát |
| --- | --- | --- |
| Username/password qua `/login` | Biết password của account | Đăng nhập đầy đủ khi chưa có factor thứ hai |
| TOTP/HOTP/OTT | Có mã/credential theo cơ chế tương ứng | Nhập mã trên luồng khác nhưng app không gắn đúng account/phiên hoặc không chặn replay |
| Passkey/WebAuthn | Sở hữu credential key và những flags đã được verifier kiểm tra | `UV=0` bị xem như xác minh người dùng đầy đủ; bỏ kiểm tra challenge/origin |
| OIDC/OAuth2 Login | IdP xác thực theo policy được tin cậy | App không kiểm tra mức `acr`/`amr`, thời điểm và issuer trước khi cấp quyền cao |
| SAML SSO | Assertion được IdP ký và SP xác minh | Cho rằng signed assertion luôn có MFA; không kiểm tra AuthnContext/hợp đồng assurance |
| Remember-me | Browser đang giữ cookie đăng nhập lâu dài | Cookie tự động cấp quyền cho trang thay mật khẩu hoặc tắt MFA |
| API Bearer/JWT | Token được xác minh, có issuer/audience/scope | Token cấp theo đường password-only vẫn vào endpoint cần MFA |
| Basic/legacy endpoint | Có thông tin xác thực cũ | Bypass trang MFA bằng API/mobile/host khác |
| Recovery code | Có một chứng từ phục hồi đã cấp | Recovery code trở thành password vĩnh viễn hoặc không single-use |
| Reset password bằng email | Có quyền điều khiển kênh reset theo quy trình | Reset xong tự tạo phiên MFA-complete |
| Help desk / impersonation | Nhân viên hỗ trợ có quyền nghiệp vụ | “Tắt MFA tạm” không xác minh người gọi hoặc không audit |

Không cần **cấm mọi cơ chế khác**: có thể có API machine-to-machine dùng OAuth 2.0 client credentials không gắn với con người, nhưng cần policy riêng. Điều không được phép là để một đường yếu hơn **kế thừa quyền của phiên người dùng đã hoàn thành MFA** mà không có chứng cứ tương ứng.

## 4. Kiến trúc chính sách: xác thực là sự kiện; cấp quyền là quyết định

Có thể mô hình hóa trạng thái ở mức nghiệp vụ như sau:

```text
ANONYMOUS
   |
   +-- password hợp lệ -------> PRIMARY_VERIFIED
   |                                |
   |                                +-- factor thứ hai hợp lệ ---> MFA_VERIFIED
   |
   +-- remember-me cookie ----> REMEMBERED
   |                                |
   |                                +-- re-auth + factor ---> MFA_VERIFIED
   |
   +-- passkey hợp lệ --------> PASSKEY_VERIFIED
   |                                |
   |                                +-- assurance đạt policy? ---> MFA-equivalent access
   |
   +-- recovery code --------> RECOVERY_LIMITED
                                    |
                                    +-- kiểm tra thêm / enroll factor mới
                                              |
                                              v
                                        REAUTH_REQUIRED
```

Đây là **mô hình nghiệp vụ**, không phải enum mặc định của Spring Security.

Điểm chính:

- `PRIMARY_VERIFIED` chỉ là bằng chứng của **một bước**; không nhất thiết cho vào khu vực cần MFA.
- `REMEMBERED` chỉ nói browser đã được nhận diện lại bởi cookie; không phải thời điểm vừa dùng password hoặc OTP.
- `RECOVERY_LIMITED` nên chỉ cho các hành động phục hồi được kiểm soát, không mang toàn bộ quyền của account.
- `MFA_VERIFIED` phải dựa trên chứng cứ được framework/server/IdP tin cậy tạo ra; không chỉ từ một trường `mfa=true` trong HTTP request.
- Assurance có thể **hết hạn** cho hành động nhạy cảm mặc dù session còn sống.
- Với passkey user-verifying, đánh giá assurance phải tính đến verification policy, credential, attestation (nếu cần), không cộng cứng “password + passkey” trong mọi kiến trúc.

Đối với các endpoint bảo mật, hãy kết hợp cả **role/permission** và **factor policy**. Ví dụ `/admin/users` có thể yêu cầu `ROLE_ADMIN` cộng hai factor; `/account/disable-mfa` có thể còn yêu cầu tái xác thực rất gần thời điểm thao tác và kiểm tra rủi ro.

## 5. Spring Security 7.x: `FactorGrantedAuthority` và MFA tích hợp

Từ **Spring Security 7.0**, framework có `org.springframework.security.core.authority.FactorGrantedAuthority`. Khi cơ chế authentication tương ứng hoàn tất, Spring Security có thể thêm một factor authority vào `Authentication`.

Ví dụ các hằng số có trong API 7.x:

| Hằng số | Chuỗi authority | Chứng cứ nó đại diện |
| --- | --- | --- |
| `FactorGrantedAuthority.PASSWORD_AUTHORITY` | `FACTOR_PASSWORD` | Authentication dùng password |
| `FactorGrantedAuthority.OTT_AUTHORITY` | `FACTOR_OTT` | One-Time Token Login |
| `FactorGrantedAuthority.WEBAUTHN_AUTHORITY` | `FACTOR_WEBAUTHN` | Authentication dùng WebAuthn |
| `FactorGrantedAuthority.BEARER_AUTHORITY` | `FACTOR_BEARER` | Authentication dùng Bearer token |
| `FactorGrantedAuthority.AUTHORIZATION_CODE_AUTHORITY` | `FACTOR_AUTHORIZATION_CODE` | OAuth2 Authorization Code Login |
| `FactorGrantedAuthority.X509_AUTHORITY` | `FACTOR_X509` | Authentication dùng X.509 |

**Quan trọng:** các marker trên ghi nhận **cơ chế đã xác thực**, không tự chứng minh chúng là **những yếu tố độc lập** theo threat model. `FACTOR_BEARER` không cho biết token có được cấp sau MFA; `FACTOR_AUTHORIZATION_CODE` không có nghĩa IdP đã dùng OTP. Một `ROLE_ADMIN` lấy từ DB cũng không tự tạo `FACTOR_OTT`.

`FactorGrantedAuthority` có `getIssuedAt()`; chính sách có thể giới hạn độ mới của factor cho từng tài nguyên. Việc đã có marker từ lâu không nhất thiết đủ cho một hành động yêu cầu step-up “vừa xác minh”.

### Ví dụ: yêu cầu password + OTT cho các route đã bảo vệ

Mẫu dưới đây dành riêng cho Spring Security **7.x** và Servlet; Spring Security 6.x không có annotation/class này. Đặt trong ứng dụng Spring Boot **4.x** tương thích, có `spring-boot-starter-web` và `spring-boot-starter-security`.

`src/main/java/example/mfa/MfaSecurityConfig.java`:

```java
package example.mfa;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableMultiFactorAuthentication(authorities = {
    FactorGrantedAuthority.PASSWORD_AUTHORITY,
    FactorGrantedAuthority.OTT_AUTHORITY
})
public class MfaSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(withDefaults())
            .oneTimeTokenLogin(withDefaults());

        return http.build();
    }
}
```

**Phân tích:**

1. `@EnableMultiFactorAuthentication(...)` bổ sung yêu cầu `FACTOR_PASSWORD` **và** `FACTOR_OTT` vào các authorization rules được tạo thông qua cơ chế factory tích hợp của Spring Security 7.
2. `/admin/**` cần **cả** các factor **và** `ROLE_ADMIN`; không được vượt qua chỉ với role.
3. Các tài nguyên cần authentication phải thỏa các factor đã khai báo. Framework có luồng hướng người dùng thực hiện factor còn thiếu.
4. `formLogin(...)` cùng `oneTimeTokenLogin(...)` bật **hai phương thức**. Chỉ khai báo yêu cầu mà không cung cấp bước authentication thứ hai sẽ khiến user không hoàn tất login.
5. Cấu hình này **chưa triển khai giao token OTT**: để chạy thật cần `UserDetailsService`, `OneTimeTokenService` phù hợp, `OneTimeTokenGenerationSuccessHandler` gửi token đến kênh đã xác minh, CSRF/session, chính sách tài khoản và một máy chủ SMTP/SMS thực. Không tự in token ra log/response ở production.
6. Các endpoint được `permitAll` hoặc cơ chế khác có thể có xử lý riêng; test cụ thể các đường đăng nhập/khôi phục và **không** mặc định rằng một annotation đã bảo vệ mọi URL do ứng dụng tự tạo hoặc mọi service bên ngoài.
7. Nếu dùng `@EnableMethodSecurity`, kiểm tra việc áp dụng yêu cầu factor đối với các method authorization rules; bảo đảm custom `AuthorizationManager` và các filter chains vẫn được kiểm thử.

**Không làm như sau:** tự gán `new SimpleGrantedAuthority("FACTOR_OTT")` cho mọi user trong database. Factor authority phải xuất phát từ một **sự kiện xác thực thật đã được kiểm chứng**, không được biến thành “role vĩnh viễn” khi account được tạo.

### Kiểm tra phiên bản bằng dependency tree

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Mục tiêu là bảo đảm các module `spring-security-*` cùng major version. Code Spring Security 7 không thể “sửa import” để chạy trên Spring Security 6.5 vì `@EnableMultiFactorAuthentication` và `FactorGrantedAuthority` chưa tồn tại ở dòng đó.

## 6. Chọn MFA toàn cục hay chọn lọc theo rủi ro?

Có hai mô hình:

**A. Bắt buộc cho toàn bộ tài nguyên cần đăng nhập.** Đây là hướng dễ hiểu: người dùng không vào được vùng bảo vệ nếu thiếu factor. Phù hợp với ứng dụng nội bộ có một chính sách chung. Tuy nhiên phải bảo đảm login/challenge/recovery endpoints hoạt động hợp lý để user có thể hoàn thành factor còn thiếu.

**B. Bắt buộc cho một nhóm tài nguyên hoặc nhóm người dùng.** Ví dụ đọc tin tức nội bộ chỉ cần xác thực, nhưng đổi email hoặc tạo API key đòi factor mới trong khoảng thời gian ngắn. Đây là mô hình **step-up**.

Spring Security 7.x có `AuthorizationManagerFactories.multiFactor()` để tạo `AuthorizationManagerFactory` yêu cầu một hoặc nhiều factor; có thể chọn lọc:

```java
// Đoạn nằm trong bean SecurityFilterChain của Spring Security 7.x.
var mfa = AuthorizationManagerFactories.multiFactor()
    .requireFactors(
        FactorGrantedAuthority.PASSWORD_AUTHORITY,
        FactorGrantedAuthority.OTT_AUTHORITY
    )
    .build();

http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/account/security/**")
        .access(mfa.authenticated())
    .requestMatchers("/admin/**")
        .access(mfa.hasRole("ADMIN"))
    .anyRequest().authenticated()
);
```

Import cho snippet:

```java
import org.springframework.security.authorization.AuthorizationManagerFactories;
import org.springframework.security.core.authority.FactorGrantedAuthority;
```

Đây là **snippet chèn trong class cấu hình**, không phải một file Java độc lập. Trong **7.x**, API `AuthorizationManagerFactories` thuộc nhánh authorization manager; lấy đúng package/Javadoc ứng với phiên bản project khi dùng snippet trong build thật. Cần thêm cả `.formLogin(...)` và `.oneTimeTokenLogin(...)` nếu đang yêu cầu hai factor đó. Nếu có nhiều `SecurityFilterChain`, áp dụng yêu cầu cho **đúng chain** đang bảo vệ tài nguyên; một chain khác có `anyRequest().authenticated()` nhưng match route tương tự có thể làm yếu policy.

**Lưu ý khi dùng policy chọn lọc:** `anyRequest().authenticated()` **không** tự chứa yêu cầu MFA từ factory cục bộ được tạo nhưng không publish thành bean. Đó là ý định thiết kế, không phải lỗi framework. Một route nghiệp vụ mới có thể vô tình bị đặt vào “low assurance”; vì vậy cần checklist phân loại route và test bắt buộc.

### Một số nhu cầu phức tạp

Có thể cần **một trong hai tập factor**: WebAuthn user-verifying **hoặc** password + OTT. Spring Security 7.x có thành phần `AllRequiredFactorsAuthorizationManager.anyOf(...)` để mô hình hóa các tổ hợp; đừng cố gán cả `FACTOR_PASSWORD` và `FACTOR_OTT` cho mọi phiên passkey nếu chính sách của bạn xem một passkey user-verifying đạt mức assurance tương ứng.

Đối với “vừa xác minh trong 10 phút”, Spring Security 7 có khái niệm duration trên factor authority trong authorization manager; không nên suy từ thời điểm tạo session hoặc mốc cookie remember-me. Policy freshness phải dựa vào **lần xác minh factor được hệ thống tin cậy ghi lại**.

## 7. Spring Security 6.x: không nhầm `fullyAuthenticated()` với MFA

Trong Spring Security 6.x, `fullyAuthenticated()` phân biệt một Authentication **đến từ remember-me** với những lần authentication không phải remember-me. Nó **không chứng minh hai yếu tố**.

Bảng khái niệm:

| Kiểu request | `authenticated()` | `fullyAuthenticated()` | Đã xác minh MFA? |
| --- | --- | --- | --- |
| Anonymous | Không | Không | Không |
| Remember-me cookie được chấp nhận | Có | **Không** | Không |
| Username/password hợp lệ | Có | Có | Chưa chắc — thường mới một yếu tố |
| OTP-only login hợp lệ | Có | Có tùy implementation | Chưa chắc — có thể mới một yếu tố |
| Session đã xác thực MFA | Có | Có | Chỉ khi bằng chứng MFA có hiệu lực và được bảo toàn đúng |
| JWT Bearer hợp lệ | Có | Thông thường có | Không suy được chỉ từ hai method này |

Với ứng dụng 6.x, có thể **tạm giới hạn** remember-me bằng cách yêu cầu `fullyAuthenticated()` ở trang nhạy cảm, nhưng muốn MFA thật còn phải có lớp enforcement lưu và xác minh **trạng thái factor do server thiết lập** (hoặc chuyển sang IdP đảm nhận MFA với assurance được kiểm chứng).

### Ví dụ 6.x: chặn remember-me ở thao tác nhạy cảm

File `src/main/java/example/mfa/RememberMeBoundaryConfig.java`, dùng trong ứng dụng Spring Boot 3.x có `UserDetailsService` và `PasswordEncoder` thực:

```java
package example.mfa;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class RememberMeBoundaryConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UserDetailsService userDetailsService,
            @Value("${app.remember-me.key}") String rememberMeKey)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/account/security/**").fullyAuthenticated()
                .requestMatchers("/admin/**").fullyAuthenticated()
                .anyRequest().authenticated()
            )
            .formLogin(withDefaults())
            .rememberMe(remember -> remember
                .key(rememberMeKey)
                .userDetailsService(userDetailsService));

        return http.build();
    }
}
```

`application.yml` có thể đọc key từ secret manager/environment:

```yaml
app:
  remember-me:
    key: ${REMEMBER_ME_SIGNING_KEY}
```

Đối với remember-me hash-token, key này là bí mật **phải đủ mạnh**, quản trị giống một credential server-side; không hardcode vào Git. Các ứng dụng có nhu cầu thu hồi theo thiết bị nên đánh giá persistent token repository thay vì chỉ dùng kiểu hash-token. Remember-me nên là tính năng người dùng chủ động chọn, không mặc nhiên được bật trên shared devices.

**Điểm bắt buộc hiểu đúng:** `fullyAuthenticated()` trong ví dụ chỉ buộc user thoát trạng thái remember-me để xác thực tương tác. Nó **không kiểm tra OTP, TOTP, passkey hoặc factor thứ hai**. Một form login password-only vẫn được tính là fully authenticated. Không được dùng ví dụ này làm tuyên bố “đã triển khai MFA”.

Khi nâng cấp lên 7.x, ưu tiên cơ chế factor authorities và authorization manager tích hợp; nếu còn chạy 6.x lâu dài, có thể dùng một IdP MFA bên ngoài với hợp đồng `acr`/`amr` được kiểm chứng hoặc một `AuthorizationManager` custom được kiểm thử đầy đủ, thay vì chỉ kiểm tra `isAuthenticated()`.

## 8. Remember-me: nó là một đường đăng nhập độc lập

`RememberMeAuthenticationFilter` khôi phục `Authentication` từ cookie khi `SecurityContext` chưa có authentication. Spring Security cung cấp hai cách chính:

1. **`TokenBasedRememberMeServices` (hash-based):** cookie bao gồm username, expiry và MAC/signature gắn với password trong `UserDetails` và server key. Không cần một record token riêng trong database theo mô hình mặc định. **Cookie bị đánh cắp có thể bị dùng lại** cho đến khi hết hạn hoặc các thành phần liên quan thay đổi; không thu hồi từng thiết bị thuận tiện như persistent token.
2. **`PersistentTokenBasedRememberMeServices`:** cookie được đối chiếu với record trong `PersistentTokenRepository`, có cơ chế token theo chuỗi (series) và luân chuyển token theo cách framework hỗ trợ. Có thể lưu bằng `JdbcTokenRepositoryImpl`; thiết kế DB riêng nếu cần danh sách thiết bị, revoke có chọn lọc và chính sách audit.

**Cả hai yêu cầu `UserDetailsService`.** Nếu ứng dụng chỉ có provider LDAP hoặc SAML mà không có bean tương ứng, không giả định DSL remember-me tự tương thích.

Luồng minh họa:

```text
User đã chọn "Remember me" trên lần đăng nhập được phép
     |
     v
Server phát remember-me cookie, có expiry/policy
     |
     v
Session hết nhưng browser còn cookie
     |
     v
RememberMeAuthenticationFilter đọc cookie
     |
     v
Tạo RememberMeAuthenticationToken (khi hợp lệ)
     |
     v
Authentication authenticated = true
     |
     +--> API/view low-risk có thể chấp nhận nếu policy cho phép
     |
     `--> Đổi email, đổi password, đăng ký passkey, quản lý admin?
               |
               v
          Yêu cầu tương tác + MFA/step-up mới
```

### Tại sao remember-me có thể trở thành MFA bypass?

Giả sử app chỉ kiểm soát OTP trong login form:

1. Linh đăng nhập bằng password + OTP rồi đánh dấu remember-me.
2. Một tuần sau, browser tự đăng nhập chỉ nhờ cookie.
3. Request `/account/disable-mfa` kiểm tra mỗi `.authenticated()`.
4. Ứng dụng cho tắt MFA ngay, **không có factor mới**.

Dù cookie hợp lệ, bước 3 là lỗ hổng **authorization/step-up policy**. `isAuthenticated()` không phải bằng chứng vừa xác minh MFA.

### Chính sách remember-me đề xuất

- Chỉ cho phép nhớ **thiết bị/browser** theo consent và thời hạn rõ ràng; giảm phạm vi quyền tự động.
- Không phát cookie remember-me trong luồng **recovery-limited** hoặc login yếu chưa đạt điều kiện phát cookie.
- Không coi việc “đã dùng MFA ở lần đầu trên thiết bị này” là bằng chứng factor **vĩnh viễn**.
- Đối với thay email, thay MFA, xem API key, reset password nội bộ, chuyển tiền hoặc quyền admin: yêu cầu step-up/fresh factor.
- Cookie có `Secure`, `HttpOnly` và `SameSite` phù hợp; HTTPS, session fixation protection, CSRF protections và logout đúng.
- Khi password/factor/email/recovery bị thay đổi, có chính sách **revoke các remember-me tokens và sessions**. Với persistent tokens có thể revoke record; với hash tokens đánh giá ảnh hưởng của password/key rotation.
- Audit việc remember-me được phát, tự đăng nhập, hủy hoặc phát hiện token bị dùng lại bất thường; **không log cookie**.

**Không hứa tuyệt đối**: logout ở một thiết bị hoặc xóa cookie không nhất thiết thu hồi mọi token đã copy sang nơi khác. Cần server-side revocation nếu yêu cầu rủi ro đó.

## 9. “Trusted device” và “Remember this browser” khác MFA

Một số hệ thống có tùy chọn “đừng hỏi OTP trên trình duyệt này trong 30 ngày”. Nó thường hoạt động bằng **device trust cookie** hoặc một record phía server. Đây là **chính sách giảm số lần prompt** sau khi đã xác thực mạnh, không phải một yếu tố mới.

Phải xác định:

- Cookie là bằng chứng thiết bị/phiên có giới hạn hay là bearer credential đăng nhập tự động?
- Người dùng có xác nhận lưu trên **thiết bị cá nhân**? Có thể từ chối trên shared device?
- Có TTL, server-side revocation, device ID, rotation và điều kiện rủi ro?
- Có chặn thiết bị tin cậy ở endpoint rủi ro cao hoặc sau sự kiện bất thường?
- Có chính sách kết thúc trust khi password reset, factor reset, logout all sessions hoặc mất thiết bị?
- Browser khác copy cookie có được coi là thiết bị tin cậy không? Nếu có, cơ chế chỉ **cookie-based**, không thực sự chứng minh phần cứng độc lập.

Tránh đặt `mfaEnabled=false` trong account sau khi người dùng nhấn “Remember this device”. MFA vẫn được cấu hình; chỉ **điều kiện cần prompt** trong một thời gian/điều kiện cụ thể mới thay đổi.

## 10. Khôi phục tài khoản là một cơ chế xác thực riêng

Recovery **không** phải ngoại lệ “bỏ qua xác thực”. Khi mất điện thoại, khóa passkey hoặc quyền truy cập email, người dùng vẫn cần cơ chế lấy lại tài khoản; nếu quy trình này yếu hơn login thường, kẻ tấn công sẽ chọn recovery thay vì đoán OTP.

Một quy trình recovery nên có **trạng thái giới hạn**:

```text
Recovery requested
        |
        v
Throttling + phản hồi chung (không lộ account tồn tại)
        |
        v
Kiểm tra bằng chứng recovery được phê duyệt
        |
        v
RECOVERY_VERIFIED (có TTL, mục đích riêng)
        |
        v
Cho thêm/khôi phục factor mới theo policy
        |
        v
Thông báo ra kênh đã đăng ký, audit, xử lý rủi ro
        |
        v
Invalidate/revoke session & token cũ phù hợp
        |
        v
Yêu cầu đăng nhập/reauth đầy đủ với factor mới
```

### Recovery code dùng một lần

Trong quá trình enroll MFA, server có thể cấp **một tập recovery codes** ngẫu nhiên có entropy đủ lớn, ví dụ 8–12 mã. Người dùng được khuyến nghị lưu ở nơi an toàn ngoài tài khoản đang bảo vệ.

Các yêu cầu:

- Mỗi mã phải được **sinh bằng CSPRNG**, độc lập với password/secret TOTP.
- Nên lưu **hash/verifier an toàn** ở server; không lưu raw code lâu dài. Với mã có entropy đủ lớn, HMAC/digest keyed và cách triển khai tương ứng có thể phù hợp; đối chiếu mô hình đe dọa.
- Việc dùng mã phải **atomic** và **single-use**; không để hai request đồng thời cùng mã thành công.
- Có rate limit, hạn số lần thử, cảnh báo và giới hạn account.
- Code chỉ có phạm vi **recovery**, không tự trở thành quyền truy cập `ROLE_ADMIN`.
- Sau khi tạo mã mới, mã cũ bị thu hồi theo chính sách; cảnh báo user về các mã đã dùng/không còn.
- Không gửi raw recovery code qua analytics, log, email không bảo mật hoặc URL query.

Một recovery code có thể là một bằng chứng phục hồi hợp lệ, nhưng **chỉ một recovery code** không nhất thiết đủ để cấp **phiên đăng nhập MFA-complete**. Policy có thể yêu cầu kèm kiểm tra khác, thời gian trì hoãn, xác minh qua kênh đã đăng ký từ trước hoặc quy trình hỗ trợ đáng tin cậy.

### TOTP/Passkey bị mất

Khi reset factor:
1. Xác minh chủ tài khoản theo bằng chứng độc lập đã được thiết lập **trước** lúc nghi vấn.
2. Không cho một phiên remember-me cũ đơn độc thêm passkey/đổi số điện thoại hoặc tắt TOTP.
3. Không cho việc **đổi địa chỉ email** rồi dùng ngay email mới để nhận recovery link mà không có xác minh tăng cường.
4. Thông báo qua kênh cũ và mới khi an toàn, cho user một đường báo sự cố.
5. Tùy rủi ro, yêu cầu cooling-off period hoặc review đối với tài khoản nhạy cảm.
6. Thu hồi factor bị mất hoặc nghi bị chiếm và vô hiệu hóa session/token có nguy cơ.
7. Không tự động tạo “phiên quản trị đầy đủ” chỉ nhờ một sự kiện reset.

## 11. Quên mật khẩu không được mặc nhiên xóa MFA

Mô hình nguy hiểm:

```text
User nhấn "Forgot password"
    -> Nhận email reset
    -> Chọn password mới
    -> Server tự gọi login()
    -> Session được gắn MFA_COMPLETE
```

Nếu email là đường recovery duy nhất, kẻ tấn công chiếm mailbox có thể bỏ qua factor còn lại mà không cần biết mã TOTP. **Reset mật khẩu** và **xác minh yếu tố thứ hai** là hai hoạt động khác nhau.

Quy trình an toàn hơn:

- Dùng reset token có entropy cao, TTL ngắn, single-use, purpose-bound và rate limit.
- Phản hồi “nếu tài khoản tồn tại...” đồng nhất để giảm user enumeration.
- Không tự động đăng nhập sau reset, hoặc nếu sản phẩm buộc phải cấp session tạm thì chỉ cấp **limited recovery session** không có quyền nhạy cảm và không tự coi đạt MFA.
- Hủy reset tokens khác còn tồn tại khi policy yêu cầu; thu hồi hoặc yêu cầu reauth các session/remember-me cookies đã cấp trước đó.
- Gửi notification tới kênh đã được xác minh; không bao giờ gửi password mới hoặc token thô vào log.
- Yêu cầu MFA theo policy khi user đăng nhập lần sau, và xử lý riêng trường hợp mất cả password **và** factor.

**Không đồng nhất “có email reset” với “đủ MFA”.** Email có thể là một phương tiện kiểm soát account trong recovery, nhưng việc có đạt mức assurance đòi hỏi thiết kế policy và threat model, không phải tên endpoint.

## 12. Đổi, tắt hoặc thêm yếu tố xác thực: thao tác nhạy cảm

Các endpoint như:

```text
POST /account/mfa/disable
POST /account/mfa/totp/reset
POST /account/passkeys/register
DELETE /account/passkeys/{credentialId}
PUT /account/recovery-email
POST /account/recovery-codes/regenerate
POST /account/api-keys
```

không được bảo vệ chỉ bằng `authenticated()` nếu ứng dụng đòi MFA cho account.

**Bảo vệ nên gồm:**

1. **Reauthentication/step-up mới** bằng yếu tố đã enroll, trong thời hạn policy (ví dụ 5–15 phút cho thay MFA).
2. **Authorization theo account**: người dùng chỉ quản lý credential thuộc account của mình; admin support không được dùng quyền chung để lấy private secret người dùng.
3. **CSRF protection** đối với thao tác thay đổi trên session/cookie flow; không dùng GET để thay factor.
4. **Session fixation/rotation** và cập nhật trạng thái factor khi hoàn thành.
5. **Thông báo out-of-band**, audit có định danh sự kiện, phát hiện nhiều lần thất bại, hạn mức.
6. **Recovery exception** chỉ qua quy trình recovery được thiết kế riêng, TTL ngắn và quyền tối thiểu.
7. **Không tự tin** vào field `mfaVerified=true`, `trusted=true`, `assurance=high` do frontend gửi.

Một hành động đổi authenticator có thể là sự kiện rủi ro cao ngay cả khi phiên đang ở trạng thái MFA từ sáng; cần xem lại **freshness** thay vì dựa vào một cookie tồn tại hàng tuần.

## 13. SSO qua OIDC/SAML: ủy quyền MFA cho IdP vẫn phải kiểm chứng

Ứng dụng có thể dùng `oauth2Login()` hoặc `saml2Login()` thay vì tự xử lý password+OTP. Khi đó chính sách MFA có thể do **Identity Provider (IdP)** thực thi, nhưng RP/app vẫn cần xác nhận bằng chứng assurance.

### Với OpenID Connect (OIDC)

Một số IdP phát các thông tin như:

- `acr`: authentication context class reference, mức/loại xác thực theo hợp đồng.
- `amr`: authentication methods references, các phương thức đã dùng; ý nghĩa phụ thuộc issuer.
- `auth_time`: thời điểm user xác thực với IdP.

**Phải có hợp đồng với issuer** về giá trị được chấp nhận, claim nằm trong token nào, chữ ký/issuer/audience, mức assurance và thời hạn. Không suy từ việc token có `email_verified=true` hoặc `scope=openid` rằng user đã làm MFA.

Ví dụ **mô tả**, không phải policy chung cho mọi IdP:

```json
{
  "iss": "https://idp.example.org",
  "sub": "user-7392",
  "aud": "client-application",
  "auth_time": 1920000000,
  "acr": "urn:example:assurance:phishing-resistant",
  "amr": ["hwk", "user"]
}
```

Các giá trị minh họa ở trên **không** có nghĩa chuẩn toàn cầu. Chỉ tin chúng nếu IdP thật phát, token được xác minh và hợp đồng diễn giải được cấu hình cụ thể. Với step-up, app có thể gửi request yêu cầu `acr_values`/`max_age` tùy khả năng IdP và **kiểm tra claim trả về**; việc gửi tham số không tự bảo đảm IdP đã đáp ứng.

### Với SAML 2.0

SAML có `AuthnStatement` và `AuthnContextClassRef` mô tả ngữ cảnh phương thức xác thực theo IdP. **Signed SAML Response** tự thân không chứng minh hai yếu tố: chữ ký chứng minh message đến từ IdP đáng tin, không nói user đã dùng OTP/passkey nếu assertion không có bằng chứng context tương ứng.

Cần map policy assurance qua IdP-specific contract, validate assertion signature/issuer/audience/recipient/time, gắn đúng account, xử lý session tuổi cao và tái xác thực khi nhạy cảm. `ForceAuthn` hoặc `RequestedAuthnContext` có thể là **yêu cầu** gửi tới IdP; app vẫn phải xác minh response thực tế.

### Trường hợp không thể chứng minh MFA từ IdP

Không tự suy đoán. Policy có thể:
- Từ chối route yêu cầu assurance cao.
- Chuyển user tới IdP có khả năng step-up và nhận kết quả đã xác thực.
- Bổ sung một factor tại ứng dụng, với luồng được thiết kế và bảo vệ state đúng.

## 14. API/Bearer token và thiết bị di động là đường vòng thường bị bỏ sót

Một trang web đã có MFA không có nghĩa endpoint REST, mobile app hoặc token từ một luồng khác đều đạt MFA. Ví dụ:

```text
Web form /login        -> password + TOTP -> session
Legacy /api/login      -> password        -> JWT
Same /api/admin        -> accepts JWT with ROLE_ADMIN
```

Nếu `/api/admin` chỉ kiểm tra JWT signature và role, luồng `/api/login` có thể **vượt qua yêu cầu MFA**.

Cần thiết kế:
- API chỉ chấp nhận **access tokens** đúng issuer, audience, token type, hạn hiệu lực và scope.
- Với API tương tác người dùng yêu cầu MFA, có ràng buộc assurance từ issuer/token exchange/authorization server **được kiểm chứng**.
- `FACTOR_BEARER` trong Spring Security 7 chỉ chứng tỏ dùng **Bearer token**, không phải token được phát sau MFA.
- App không tự cộng `FACTOR_PASSWORD` và `FACTOR_OTT` bằng cách đọc hai claim text từ JWT chưa được kiểm chứng.
- Machine-to-machine client credentials, mTLS workload identity và human interactive session nên có **chính sách riêng**, không buộc machine token “nhập OTP” cũng không để machine token tự nhận danh tính người dùng.
- Nếu bearer token bị đánh cắp, yêu cầu MFA lúc phát token **không luôn ngăn được token replay**. Cần TTL, revocation, token binding/DPoP/mTLS sender-constraining khi thích hợp và quản trị session.

Với hệ thống có nhiều gateway/sidecar, cũng phải kiểm tra đường bypass trực tiếp tới backend không đi qua nơi thực thi MFA/authorization.

## 15. Spring Security filter chains: kiểm soát cả thứ tự và matcher

Nhiều ứng dụng có nhiều `SecurityFilterChain`:

```text
Chain A: /api/**       -> Bearer token
Chain B: /admin/**     -> Form login
Chain C: /**           -> Default catch-all
```

Spring Security chọn filter chain thích hợp theo **security matcher** và thứ tự; một endpoint cần bảo vệ MFA nhưng lại nằm trong chain thấp yêu cầu chỉ `authenticated()` có thể bị bypass.

Checklist:
1. Liệt kê chính xác các matcher và `@Order` của mỗi chain.
2. Kiểm tra `/api/admin/**`, `/actuator/**`, `/internal/**`, websocket handshake, GraphQL, gRPC gateway hoặc admin host/port riêng.
3. Không giả định `requestMatchers("/admin/**")` bao trùm `/api/admin/**`.
4. Chú ý method GET/POST khác nhau và Spring MVC path matching.
5. Mỗi tài nguyên nhạy cảm có policy trung tâm; nhiều chain phải nhất quán.
6. Bảo vệ cả **method-level authorization** ở service khi có nhiều đường gọi hoặc HTTP layer khác nhau.
7. Xác minh custom filters hoặc endpoint login viết tay dùng `AuthenticationManager`/`SecurityContextRepository` đúng; không tự dựng authenticated token từ username.
8. Với Spring Security 6+, nếu custom login lưu session thủ công, cần **lưu SecurityContext tường minh** vào `SecurityContextRepository` phù hợp; kiểm tra session strategy và không bypass login lifecycle.

Không dựa vào một lần nhìn trang `/login` để kết luận mọi endpoint đều được thực thi MFA.

## 16. Session management, freshness và bước nâng cấp bảo đảm (step-up)

Sau MFA, ứng dụng thường giữ phiên qua `HttpSession`/cookie. Session tồn tại là cần thiết cho UX; nhưng “session từng hoàn thành MFA” không có nghĩa **mọi thao tác tương lai** được phép mãi mãi.

Thiết kế nên lưu/kiểm chứng:
- Chủ tài khoản/session ID và **authentication method/factor evidence** đến từ nguồn đáng tin.
- Thời điểm hoàn thành factor (`issuedAt`, `auth_time`) và các giới hạn thời gian riêng của từng thao tác.
- Sự kiện rủi ro: account recovery, đổi password, tắt MFA, đăng ký credential mới, token bị thu hồi, nghi thiết bị bị mất.
- Session invalidation và refresh session sau thay đổi quyền/factor.
- Việc **không tự nâng** session remember-me hoặc recovery thành MFA-complete khi user chỉ refresh trang.
- Trạng thái phân tán trên nhiều node: cùng một session/permission view, tránh race khi logout/revoke.

### Session cookie và remember-me cookie là hai đối tượng khác nhau

| Thành phần | Công dụng | Hệ quả bảo mật |
| --- | --- | --- |
| Session cookie | Trỏ tới phiên HTTP đang tồn tại | Bị đánh cắp có thể chiếm phiên đã hoàn thành MFA; cần TTL, revoke, CSRF và protection |
| Remember-me cookie | Tạo lại authentication khi session không còn | Thường **assurance thấp hơn** login tương tác, không có freshness |
| Trusted-device cookie | Bằng chứng tùy chọn giảm prompt MFA theo chính sách | Không tự là factor mới; bị copy có thể bị lạm dụng |
| Recovery token | Chứng minh quyền thực hiện một tác vụ phục hồi giới hạn | Không nên dùng làm session toàn quyền |
| OAuth access token | Quyền API trong thời hạn đã cấp | Phải kiểm tra audience/issuer/scope/assurance theo nghiệp vụ |

Không để remember-me tự **làm mới** thời điểm MFA. Cũng không chỉ xóa remember-me cookie mà quên thu hồi token persistent trong DB hoặc các session đã cấp.

### Các hành động nên yêu cầu fresh authentication

- Đổi password, email khôi phục, số điện thoại.
- Thêm/xóa passkey hoặc TOTP factor.
- Tạo API token có quyền lớn.
- Xem/đổi khóa bí mật, truy cập console quản trị.
- Chuyển tiền, đổi người thụ hưởng hoặc thao tác có rủi ro cao.
- Reset MFA khi có dấu hiệu account takeover.

Freshness thường phải dựa vào **sự kiện xác minh mới**, không dùng thời điểm cuối cùng người dùng tải trang.

## 17. Java 17 độc lập: mô phỏng policy cho nhiều đường vào

Chương trình dưới đây **không cần Spring**, minh họa cách tư duy “deny unless evidence satisfies policy”. Dữ liệu evidence được truyền như các giá trị giả lập **đã được nguồn xác thực tin cậy kiểm chứng**; **không dùng** class này để nhận flags do browser tự gửi trong production.

Tạo file `MfaEntryPolicyDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;

public class MfaEntryPolicyDemo {

    record Evidence(
        boolean passwordVerified,
        boolean secondFactorVerified,
        boolean rememberMeOnly,
        boolean recoveryLimited,
        Instant secondFactorAt) {}

    static boolean mayUseAdmin(
            Evidence evidence, Instant now, Duration maxAge) {
        if (evidence == null || evidence.rememberMeOnly()
                || evidence.recoveryLimited()
                || !evidence.passwordVerified()
                || !evidence.secondFactorVerified()
                || evidence.secondFactorAt() == null) {
            return false;
        }

        Duration age = Duration.between(evidence.secondFactorAt(), now);
        return !age.isNegative() && age.compareTo(maxAge) <= 0;
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T09:00:00Z");
        Duration maxAge = Duration.ofMinutes(10);

        Evidence passwordOnly =
            new Evidence(true, false, false, false, null);
        Evidence remembered =
            new Evidence(true, true, true, false, now);
        Evidence recovery =
            new Evidence(true, true, false, true, now);
        Evidence freshMfa =
            new Evidence(true, true, false, false, now.minusSeconds(120));
        Evidence staleMfa =
            new Evidence(true, true, false, false, now.minusSeconds(3600));

        System.out.println("password-only=" + mayUseAdmin(passwordOnly, now, maxAge));
        System.out.println("remember-me=" + mayUseAdmin(remembered, now, maxAge));
        System.out.println("recovery=" + mayUseAdmin(recovery, now, maxAge));
        System.out.println("fresh-mfa=" + mayUseAdmin(freshMfa, now, maxAge));
        System.out.println("stale-mfa=" + mayUseAdmin(staleMfa, now, maxAge));
    }
}
```

Chạy:

```bash
javac MfaEntryPolicyDemo.java
java MfaEntryPolicyDemo
```

**stdout chính xác:**

```text
password-only=false
remember-me=false
recovery=false
fresh-mfa=true
stale-mfa=false
```

Điểm học được:
- Password-only không đủ policy yêu cầu hai factor.
- Cookie remember-me **không** nâng quyền ngay cả khi record giả lập có hai boolean; đường vào có rủi ro thấp hơn.
- Session recovery không được dùng chức năng admin.
- Bằng chứng MFA đã quá giới hạn 10 phút không đủ cho step-up.
- Class này **không** kiểm tra chữ ký WebAuthn, mật khẩu, TOTP, hoặc token. `Evidence` phải được tạo bởi pipeline server tin cậy, có gắn account/session và được bảo vệ chống sửa đổi. Trong sản phẩm thật còn cần `ROLE_ADMIN`, account status, authorization và quản lý đồng thời.

### Vì sao không gắn một boolean “mfa” vào session là đủ?

Một `Boolean.TRUE` trong session có thể trở nên stale sau recovery, factor reset, role change hoặc device revoke. Một dữ liệu tùy ý từ request càng không đủ. Nên có mô hình evidence/risk **có nguồn gốc rõ, thời gian hiệu lực và khả năng thu hồi**; trong Spring Security 7 có thể dựa trên factor authorities và `issuedAt` theo policy. Các luồng tùy chỉnh phải cập nhật trạng thái một cách nhất quán.

## 18. Kiểm thử bắt buộc: “đường vòng phải thất bại”

Kiểm thử tốt cần gồm hai phần: (A) xác minh cơ chế auth thực sự; (B) xác minh policy bằng cả ca hợp lệ và ca thiếu factor.

### Ma trận hành vi

| Tình huống | Kết quả đúng khi route cần MFA |
| --- | --- |
| Không đăng nhập | Chuyển hướng login hoặc 401 phù hợp |
| Password đúng nhưng chưa có factor thứ hai | **Không** cho vào route nhạy cảm |
| Password + OTT/TOTP hợp lệ, trong thời hạn | Cho phép nếu đủ role và các điều kiện khác |
| Remember-me cookie hợp lệ, session cũ đã hết | **Yêu cầu reauth/step-up**, không cho vào ngay |
| Cookie nhớ thiết bị bị copy sang browser khác | Không được mặc nhiên nâng thành MFA-complete |
| Session có OTP của user A nhưng account chuyển sang B | Từ chối, không gắn factor chéo account/session |
| Recovery code hợp lệ | Chỉ vào luồng recovery đã cấp, không vào admin ngay |
| Recovery code đã dùng | Từ chối; thử dùng đồng thời chỉ đúng một request thắng |
| Password reset thành công | Không tự tạo session MFA-complete |
| Mới đổi email/recovery phone | Không dùng kênh mới để bypass ngay các kiểm tra cần thiết |
| OIDC token không có `acr`/`amr` đủ mức | Không cho vào route cần assurance cao |
| SAML signed nhưng AuthnContext không đủ mức | Chỉ xác nhận SSO; không nâng mức MFA |
| JWT hợp lệ nhưng được phát qua legacy password-only | Không đủ policy MFA của API tương ứng |
| Admin role đúng nhưng chỉ qua Basic authentication | Không cho vào route yêu cầu MFA |
| MFA đạt nhưng thiếu `ROLE_ADMIN` | Từ chối authorization |
| Factor đã xác minh cách đây quá thời hạn step-up | Yêu cầu factor mới |
| User bị disable/locked hoặc credential revoked | Từ chối cho dù session/role cũ tồn tại |
| Đăng nhập bằng cách thay đường dẫn hoặc HTTP method | Vẫn áp dụng cùng chính sách |
| Nhiều SecurityFilterChain bị overlap | Không có đường có policy yếu hơn trúng route nhạy cảm |

**Kết quả HTTP không luôn cố định**: browser session có thể được redirect tới bước factor còn thiếu; REST API thường nhận 401/403 tùy entry point và trạng thái authentication. Hãy kiểm tra **không có quyền truy cập**, không chỉ assert một status cho mọi cấu hình.

### Unit test policy Java 17

Mã `MfaEntryPolicyDemo` giúp kiểm chứng logic mốc thời gian và chặn remember-me/recovery. Với ứng dụng thực, cần JUnit cho:
- Bằng chứng thiếu factor.
- `issuedAt` ở tương lai, null, quá tuổi.
- Đúng account nhưng token/recovery code đã được revoke.
- Sai tenant/role.
- Trường hợp account vừa thay factor trong session vẫn còn.
- Race giữa hai request cùng dùng một token single-use.

### Spring Security MockMvc: tránh một bẫy test

`@WithMockUser` hoặc `.with(user("admin").roles("ADMIN"))` **giả lập một Authentication**, không chứng minh ứng dụng thật đã chạy TOTP/WebAuthn/OTT. Nếu test dùng `@WithMockUser`, test đó **chỉ** kiểm tra authorization với principal giả, không chứng minh đường đăng nhập chính hoặc remember-me không bypass MFA.

Đối với integration test:
1. Dùng account test có factor đã enroll; gửi request qua **chính login endpoints**.
2. Thử login password-only rồi truy cập route yêu cầu MFA: phải thất bại/chuyển bước.
3. Hoàn thành factor thứ hai bằng token/challenge hợp lệ, thử lại route: phải thành công nếu có role.
4. Xóa session, giữ remember-me cookie, thử route: phải bị chặn đến khi đủ reauth.
5. Dùng email reset/recovery code rồi thử route admin: bị chặn hoặc chỉ được vào recovery-limited.
6. Đổi/revoke factor, thử session cũ và nhớ thiết bị: phải xử lý theo policy mới.
7. Thử từng `SecurityFilterChain`, host/port/API version và mobile client.
8. Kiểm tra `@PreAuthorize` ở service nhận request qua cả MVC, scheduler/gRPC/gateway nếu có.

Cần đo hiệu quả ở **ranh giới tài nguyên**, không chỉ có ảnh chụp màn hình nhập OTP.

## 19. Kịch bản lỗi thực tế và cách phân loại

| Dấu hiệu | Nguyên nhân thường gặp | Biện pháp |
| --- | --- | --- |
| User có `ROLE_ADMIN` nhưng vào admin được khi thiếu OTP | Chỉ kiểm tra role hoặc `authenticated()` | Bắt factor policy tại authorization manager/IdP assurance |
| Remember-me cookie vào được trang tắt MFA | `.authenticated()` chấp nhận remember-me | Tách low/high assurance; step-up + freshness, `fullyAuthenticated()` chỉ là lớp kiểm tra phụ |
| Thay password từ email reset xong tự đăng nhập | Recovery code bị coi là full authentication | Chỉ cho recovery-limited, cần login/reauth đầy đủ |
| JWT từ app cũ truy cập API cần MFA | Không kiểm tra issuer/audience/assurance, chung role | Phân tách token policy theo audience và luồng cấp |
| Session có role mới nhưng không có factor mới | Role mapping nhầm thành bằng chứng MFA | Không gán `FACTOR_...` từ role DB |
| User A dùng OTP cho phiên user B | Không ràng buộc challenge/factor với account và session | Bind challenge đúng account/transaction; consume một lần |
| Người dùng bị khóa sau khi mất điện thoại | Recovery không được thiết kế từ đầu | Recovery codes mạnh và quy trình hỗ trợ bảo mật |
| Help desk tắt TOTP sau một cuộc gọi | Quy trình xác minh danh tính yếu, không audit | Quy trình xác minh mạnh, phân quyền tách nhiệm vụ, delay/notification |
| “Remember device” kéo dài mãi | Không TTL/revocation hoặc coi cookie là factor | Giới hạn thời gian và quyền, revoke khi risk event |
| OIDC đã SSO nhưng app không biết IdP có MFA | Không có hợp đồng `acr`/`amr`, không check `auth_time` | Yêu cầu và kiểm tra assurance từ IdP |
| Route `/api/admin` không bị ảnh hưởng bởi rule `/admin/**` | Matcher/chain khác | Rà toàn bộ securityMatcher, `@Order`, method security |
| Spring Security 6.x không tìm thấy `FactorGrantedAuthority` | Class chỉ xuất hiện ở 7.0 | Nâng cấp đồng bộ hoặc dùng cơ chế MFA bên IdP/custom đáng tin |
| MFA test pass nhưng thật vẫn bypass | MockMvc dùng `@WithMockUser` mà không test login filter | End-to-end từng authentication path và remember-me |
| Sau logout vẫn có thể dùng persistent remember-me token | Chỉ xóa session cookie hoặc sai logout wiring | Thu hồi cookie **và** server-side token theo thiết kế |
| Tắt MFA nhưng session vẫn mạnh như trước | Không cập nhật assurance/session state sau thay đổi | Invalidate/step-down/re-auth theo policy |

## 20. Checklist triển khai và vận hành

### 20.1. Trước khi release

- [ ] Có inventory **tất cả** authentication endpoints/flows: web, API, mobile, admin, legacy, SSO, OTT, passkey, Basic, remember-me, recovery, help desk.
- [ ] Mỗi tài nguyên nhạy cảm có chính sách **role + factor + freshness** đã phê duyệt.
- [ ] Authentication factor chỉ được ghi nhận sau khi server/IdP tin cậy xác minh; không đọc “mfa=true” từ input.
- [ ] Không chấp nhận remember-me hoặc trusted-device cookie như bằng chứng factor mới.
- [ ] Password reset không tự gắn MFA-complete.
- [ ] Recovery codes single-use, entropy đủ, chống brute force, lưu xác minh an toàn.
- [ ] Thay MFA/recovery email/passkey cần reauth, audit và notification.
- [ ] Cookie/session/token có TTL, CSRF protection, rotation và revocation phù hợp.
- [ ] Các IdP SSO công bố assurance đã được kiểm chứng bằng issuer/claim/contract.
- [ ] JWT/API có audience/issuer/scope/assurance theo tài nguyên, không nhận đường password-only vào admin.
- [ ] Tất cả SecurityFilterChain matchers, role rules, `@PreAuthorize` đã được rà soát.
- [ ] Có test bypass theo ma trận âm tính, bao gồm nhiều node và account/session recovery.
- [ ] Có runbook hỗ trợ người dùng mất factor mà không làm lộ secret hoặc cấp quyền tùy tiện.

### 20.2. Trong vận hành

Theo dõi tỷ lệ đăng nhập thiếu factor, lỗi recovery, nhiều lần thử OTP/recovery code, phát hành remember-me cookie bất thường, thiết bị mới, reset factors và số lượng session bị thu hồi. Phân biệt lỗi user experience với dấu hiệu account takeover, đặt rate limit thích hợp và thông báo người dùng khi có thay đổi bảo mật.

Không ghi password, OTP, raw reset link, remember-me cookie, JWT hay TOTP secret vào log. Chỉ lưu event IDs và metadata vừa đủ cho điều tra. Các chỉ số risk như IP, ASN hay thiết bị mới **hỗ trợ** đánh giá rủi ro nhưng không thay thế một authentication factor đã được xác minh.

## 21. Tóm tắt quyết định

Một hệ thống MFA đủ chặt có ít nhất ba lớp:

1. **Authentication pipeline:** từng cơ chế xác minh password, OTT, passkey, SSO hoặc token theo chuẩn, gắn evidence đáng tin với account và thời điểm.
2. **Authorization và assurance:** mọi request nhạy cảm kiểm tra role **và** yếu tố bắt buộc **và** độ mới; không cho một đường nhớ trình duyệt/legacy/recovery thỏa các điều kiện bằng cách đi vòng.
3. **Lifecycle và recovery:** thay yếu tố, reset password, mất thiết bị, trusted device, remember-me và help desk phải có policy, audit, notification và revocation.

Spring Security 7.x cung cấp `FactorGrantedAuthority` và `@EnableMultiFactorAuthentication`/authorization managers để mô hình hóa các yêu cầu factor trên Servlet. Spring Security 6.x có công cụ chặn remember-me bằng `fullyAuthenticated()`, nhưng **đó không phải MFA**. Dù dùng phiên bản nào, lỗ hổng phổ biến nhất vẫn nằm ở **đường đăng nhập phụ hoặc đường khôi phục**, không phải ở phép toán so mã OTP.

## 22. Tài liệu đối chiếu chính thức

- Spring Security 7.0 — Multi-Factor Authentication: https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/mfa.html
- Javadoc Spring Security 7.0 — `FactorGrantedAuthority`: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html
- Javadoc Spring Security 7.0 — `@EnableMultiFactorAuthentication`: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/config/annotation/authorization/EnableMultiFactorAuthentication.html
- Spring Security 6.5 — Remember-Me Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- OWASP — Multifactor Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html
- OWASP — Forgot Password Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
