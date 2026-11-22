# Quan hệ giữa cơ chế cung cấp yếu tố với quy tắc yêu cầu đủ yếu tố trong Spring Security

## 1. Hai việc khác nhau nhưng phải đi cùng nhau

Khi thiết kế xác thực đa yếu tố (Multi-Factor Authentication, MFA), có hai câu hỏi **độc lập**:

1. **Cơ chế xác thực nào cung cấp yếu tố?** Ví dụ: username/password, one-time token (OTT), WebAuthn/passkey, xác thực chứng chỉ hoặc một IdP bên ngoài. Mỗi cơ chế kiểm chứng một loại bằng chứng và có thể ghi nhận yếu tố mà người dùng đã thực hiện.
2. **Quy tắc truy cập yêu cầu đủ những yếu tố nào?** Ví dụ: xem trang thông thường cần đăng nhập; đổi email cần cả password và OTT; quản trị cần role ADMIN **và** hai yếu tố còn hiệu lực.

Bật hai phương thức đăng nhập **không đồng nghĩa** yêu cầu sử dụng cả hai. Nếu ứng dụng cấu hình `formLogin()` và `oneTimeTokenLogin()` nhưng mọi trang chỉ dùng `authenticated()`, trong cấu hình thông thường người dùng có thể hoàn tất **một trong hai** là đủ vào trang. Ngược lại, nếu đặt quy tắc bắt buộc hai yếu tố nhưng không có cơ chế cung cấp yếu tố còn thiếu, người dùng sẽ không hoàn tất được yêu cầu.

Vì vậy mối quan hệ đúng là:

```text
Cơ chế xác thực / cung cấp yếu tố
    password ──────────> FACTOR_PASSWORD
    one-time token ────> FACTOR_OTT
    WebAuthn ──────────> FACTOR_WEBAUTHN  (tùy cấu hình và phiên bản)
                  │
                  ▼
      Authentication của người dùng
        (danh tính + các factor đã xác minh)
                  │
                  ▼
      Quy tắc authorization của tài nguyên
      /dashboard : authenticated
      /settings  : PASSWORD AND OTT
      /admin     : ROLE_ADMIN AND PASSWORD AND OTT
                  │
                  ▼
          Cho phép / từ chối / step-up
```

**Ý chính:** cơ chế **cung cấp** trạng thái xác thực có thể tin được; chính sách **đòi hỏi** một tập trạng thái xác thực. Cả hai được kết nối qua `Authentication`, `GrantedAuthority` và `AuthorizationManager` hoặc hệ thống chính sách tương đương.

Bài tập trung vào Spring Security Servlet. **Spring Security 7.0+** có API MFA ở cấp framework như `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication` và `AuthorizationManagerFactories.multiFactor()`. Chúng được giới thiệu từ nhánh 7.0; **Spring Security 6.x không có sẵn các API 7.0 này**. Ví dụ sử dụng 7.0+ sẽ được đánh dấu rõ để tránh copy vào ứng dụng Boot 3 / Security 6.

## 2. Yếu tố, phương thức và quyền không phải cùng một thứ

NIST/OWASP thường phân biệt các nhóm yếu tố theo loại bằng chứng:

- **Something you know:** điều người dùng biết như password/PIN.
- **Something you have:** điều họ sở hữu hoặc kiểm soát như thiết bị, authenticator, token vật lý.
- **Something you are:** đặc trưng sinh trắc học.
- Các tín hiệu vị trí, hành vi và rủi ro có thể là lớp bổ sung nhưng **không tự động** tương đương một yếu tố độc lập trong mọi chuẩn.

Phải phân biệt ba cấp:

| Khái niệm | Ví dụ | Vai trò trong chính sách |
| --- | --- | --- |
| **Authentication mechanism** | Password login, OTT login, WebAuthn, OIDC login | Chạy quy trình kiểm tra credential/bằng chứng |
| **Factor evidence** | `FACTOR_PASSWORD`, `FACTOR_OTT`, thời điểm factor được xác minh | Cho biết bước xác thực nào đã được thực hiện |
| **Authorization authority** | `ROLE_ADMIN`, `SCOPE_report.read` | Cho biết quyền nghiệp vụ, không phải bằng chứng đã MFA |

`ROLE_ADMIN` **không** có nghĩa quản trị viên đã hoàn thành MFA. `authenticated()==true` **không** có nghĩa đủ hai yếu tố. Ngược lại, người đã hoàn tất hai yếu tố vẫn có thể không được phép quản lý người dùng nếu không có `ROLE_ADMIN`.

**Cùng một yếu tố không được tính hai lần chỉ vì có hai màn hình.** Hỏi password hai lần không biến thành MFA. Hai mã gửi tới cùng hộp thư có thể vẫn dựa trên một nguồn sở hữu duy nhất. Magic link qua email và password có thể là hai cơ chế, nhưng tính **độc lập và sức mạnh** phụ thuộc khả năng kiểm soát email, khả năng tấn công phishing, khôi phục tài khoản và cách triển khai.

WebAuthn/passkey là một **phương thức** có thể mang nhiều đặc tính bảo đảm tùy authenticator, user verification và chính sách. Đừng tự kết luận “phải luôn bật thêm password” hoặc “một passkey luôn bằng hai yếu tố” nếu chưa đối chiếu assurance mong muốn.

## 3. Một mô hình toán học đơn giản

Gọi:

- `P` là **tập yếu tố đã được xác minh và còn hợp lệ** của Authentication hiện tại.
- `R(resource)` là **tập yếu tố được tài nguyên yêu cầu**.
- `A(resource)` là điều kiện phân quyền khác như role, scope, tenant, ownership.
- `F(resource)` là kiểm tra freshness/assurance khi tài nguyên có yêu cầu xác thực gần đây.

Một request được phép khi:

```text
authenticated
AND requiredFactors(resource) ⊆ verifiedValidFactors(authentication)
AND authorizationPolicy(resource, principal)
AND freshnessPolicy(resource, factorEvidence)
```

Nếu `P = {PASSWORD}` và `R = {PASSWORD, OTT}` thì không thỏa. Nếu `P = {PASSWORD, OTT}` thì phần factor thỏa, nhưng `ROLE_ADMIN` hoặc quyền trên đối tượng vẫn phải được kiểm riêng.

### 3.1. Bảng trạng thái

| Trạng thái user | `authenticated()` | Chỉ `PASSWORD` | `PASSWORD AND OTT` | `ROLE_ADMIN AND PASSWORD AND OTT` |
| --- | --- | --- | --- | --- |
| Chưa đăng nhập | Không | Không | Không | Không |
| Đăng nhập bằng password | Có | Có | Không | Không |
| Chỉ OTT (nếu hệ thống hỗ trợ) | Có | Không | Không | Không |
| Password rồi OTT | Có | Có | Có | Chỉ nếu có ROLE_ADMIN |
| Hai yếu tố nhưng OTT quá cũ theo policy | Có | Có | Có nếu không yêu cầu freshness | Không nếu policy đòi OTT mới |
| Admin đã password + OTT hợp lệ | Có | Có | Có | Có, nếu các điều kiện nghiệp vụ khác cũng đạt |

Bảng minh họa sự khác biệt giữa **đăng nhập thành công**, **đủ factor**, **đủ role**, và **đủ độ mới**. Cột chỉ Password/OTT cần được hiểu trong hệ thống kiểm chứng factor đáng tin; không phải cứ gắn một chuỗi `FACTOR_*` vào object là bằng chứng bảo mật.

## 4. Spring Security 7: FactorGrantedAuthority là điểm nối

Trong Spring Security 7.0+, `FactorGrantedAuthority` là implementation của `GrantedAuthority` có ý nghĩa đặc biệt: ghi lại factor đã dùng và thời điểm cấp thông qua `getIssuedAt()`. Các cơ chế chuẩn khi xác thực có thể bổ sung factor authority tương ứng vào `Authentication`.

Các hằng số tiêu biểu:

| Constant trong `FactorGrantedAuthority` | Authority string | Nguồn thông thường |
| --- | --- | --- |
| `PASSWORD_AUTHORITY` | `FACTOR_PASSWORD` | Password authentication |
| `OTT_AUTHORITY` | `FACTOR_OTT` | One-Time Token login |
| `WEBAUTHN_AUTHORITY` | `FACTOR_WEBAUTHN` | WebAuthn authentication |
| `X509_AUTHORITY` | `FACTOR_X509` | X.509 authentication |
| `AUTHORIZATION_CODE_AUTHORITY` | `FACTOR_AUTHORIZATION_CODE` | OAuth2 Authorization Code mechanism |
| `BEARER_AUTHORITY` | `FACTOR_BEARER` | Bearer token authentication |

**Không đọc bảng này như chứng chỉ đảm bảo MFA trong mọi hệ thống.** Ví dụ `FACTOR_BEARER` có thể chỉ biểu thị cơ chế Bearer đã được dùng; nó **không** chứng minh bearer access token chứa MFA của người dùng. `FACTOR_AUTHORIZATION_CODE` không đồng nghĩa IdP đã thực hiện hai yếu tố. Độ bảo đảm thực tế tùy giao thức và chính sách xác thực của issuer.

Khi một mechanism xác thực thành công, nó **cung cấp** factor authority. Khi authorization rule kiểm factor, nó **tiêu thụ bằng chứng** đó. Một application có thể tiếp nhận nhiều cơ chế, nhưng chỉ các rule đã được cấu hình mới ràng buộc chúng lại với nhau.

Đối với factor tự định nghĩa, chỉ tạo `FactorGrantedAuthority` từ thành phần xác thực đã được thẩm định **sau khi** kiểm chứng thật; không lấy `FACTOR_OTT`, thời điểm hay `amr`/`acr` từ một HTTP header do client tự gửi. `FactorGrantedAuthority.fromAuthority(...)` là API tạo đối tượng, **không phải API xác minh credential**.

## 5. Trách nhiệm của từng tầng trong flow

Một flow hai bước thường có:

1. **Authentication entry point:** phát hiện người dùng chưa có credential hoặc đang thiếu yếu tố rồi hướng tới phương thức đăng nhập/step-up thích hợp.
2. **Password/OTT/WebAuthn mechanism:** nhận bằng chứng, gọi provider/manager để kiểm tra, xử lý chống replay và lỗi.
3. **Authentication / SecurityContext:** đại diện cho danh tính, authorities và các factor đã được hoàn tất. Cách lưu/khôi phục context phải phù hợp lifecycle session.
4. **AuthorizationManager:** ở thời điểm truy cập, kiểm factor bắt buộc của route/method và kiểm role/scope cần thiết.
5. **Controller/service:** thực hiện nghiệp vụ **chỉ sau khi** policy cho phép; tiếp tục kiểm tenant/ownership/transaction rules.

Khi chỉ có password và người dùng vào `/settings/security` đòi Password + OTT, hệ thống không nên âm thầm “bỏ qua OTT vì user đã authenticated”. Nó cần yêu cầu thêm OTT. Nếu user không cung cấp hoặc OTT hết hạn, tài nguyên vẫn bị chặn.

**Ngược lại, chỉ cài `oneTimeTokenLogin()` không đủ để yêu cầu MFA.** Một số người dùng có thể login chỉ bằng OTT nếu authorization chỉ gọi `authenticated()`. “Có cơ chế” là **khả năng**, “yêu cầu” là **chính sách**.

### 5.1. Vì sao không đặt logic ở controller?

Phản ví dụ:

```java
// PHẢN VÍ DỤ — không sao chép:
@GetMapping("/transfer")
public String transfer(Authentication authentication) {
    if (authentication.isAuthenticated()) {
        return "transfer allowed";
    }
    return "login required";
}
```

Đây là snippet minh họa lỗi, không phải class đầy đủ. Không kiểm yếu tố, độ mới hoặc quyền. Hơn nữa, quyết định authorization trong controller dễ bị quên ở endpoint khác. Tốt hơn là đặt policy tập trung ở URL/method security rồi vẫn kiểm quyền dữ liệu ở service.

## 6. Ví dụ Java 17 độc lập: cơ chế cung cấp và quy tắc yêu cầu

Ví dụ sau **không phụ thuộc Spring**, mô phỏng đúng quan hệ giữa các tập yếu tố để dễ chạy bằng `javac`/`java`. Nó không thay cho hệ thống xác thực thật hoặc `SecurityContext`.

**`FactorPolicyDemo.java`**

```java
import java.util.EnumSet;
import java.util.Set;

public class FactorPolicyDemo {
    enum Factor { PASSWORD, OTT }
    record Session(Set<Factor> factors, boolean admin) {}

    static boolean allowsSettings(Session session) {
        return session.factors().containsAll(
                EnumSet.of(Factor.PASSWORD, Factor.OTT));
    }

    static boolean allowsAdmin(Session session) {
        return session.admin() && allowsSettings(session);
    }

    public static void main(String[] args) {
        Session passwordOnly =
                new Session(EnumSet.of(Factor.PASSWORD), true);
        Session both =
                new Session(EnumSet.of(Factor.PASSWORD, Factor.OTT), false);
        Session adminBoth =
                new Session(EnumSet.of(Factor.PASSWORD, Factor.OTT), true);

        System.out.println("password-only settings = "
                + allowsSettings(passwordOnly));
        System.out.println("password-only admin = "
                + allowsAdmin(passwordOnly));
        System.out.println("both settings = "
                + allowsSettings(both));
        System.out.println("both admin = "
                + allowsAdmin(both));
        System.out.println("admin both admin = "
                + allowsAdmin(adminBoth));
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac FactorPolicyDemo.java
java FactorPolicyDemo
```

Stdout chính xác:

```text
password-only settings = false
password-only admin = false
both settings = true
both admin = false
admin both admin = true
```

Ý nghĩa: cùng có `authenticated`, nhưng một user mới password không đủ yêu cầu Settings, còn user đủ hai factor nhưng không có role ADMIN vẫn không vào Admin. Trong Spring thật, các set/authority **phải do quá trình authentication đáng tin tạo ra**, đồng thời có kiểm thời hạn và session.

## 7. Ví dụ Spring Security 7: áp dụng MFA trên toàn ứng dụng

**Yêu cầu phiên bản:** mẫu này dùng **Spring Security 7.0+**, thường đi cùng hệ sinh thái Spring Boot 4.x phù hợp, Java 17+. Không copy nguyên vào Spring Boot 3.x / Security 6.x. API `@EnableMultiFactorAuthentication` và `FactorGrantedAuthority` được giới thiệu từ Spring Security 7.0.

Mục tiêu demo:

- Trang `/public/**` được truy cập không cần login.
- Các trang thường yêu cầu cả password **và** OTT.
- `/admin/**` ngoài hai yếu tố còn yêu cầu `ROLE_ADMIN`.
- Authentication mechanisms là form/password và one-time-token login.

Các imports và cấu hình **core** dưới đây nằm trong `SecurityConfig.java`:

```java
package com.example.mfa;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMultiFactorAuthentication(authorities = {
        FactorGrantedAuthority.PASSWORD_AUTHORITY,
        FactorGrantedAuthority.OTT_AUTHORITY
})
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers("/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .oneTimeTokenLogin(Customizer.withDefaults())
                .build();
    }
}
```

**Đọc code theo hai phần độc lập:**

- `formLogin(...)` / `oneTimeTokenLogin(...)` **cung cấp phương thức xác thực**. Khi xử lý thành công, cơ chế tương ứng có thể ghi nhận `FACTOR_PASSWORD`/`FACTOR_OTT` vào authentication trong hệ thống MFA của Spring 7.
- `@EnableMultiFactorAuthentication(authorities={PASSWORD,OTT})` **thiết lập yêu cầu bổ sung** lên các rule authorization được xây dựng qua factory hỗ trợ. Do đó `hasRole("ADMIN")` không chỉ kiểm role mà còn ràng buộc các factor yêu cầu; `authenticated()` cũng không có nghĩa chỉ một yếu tố.
- `permitAll()` và các rule public nên vẫn được tổ chức có chủ đích; theo API factory MFA, additional factor requirement không biến `permitAll()` thành protected endpoint.
- Ngay cả khi password đúng, user chưa đủ OTT vẫn không đáp ứng một endpoint protected được áp MFA.

**Phạm vi chạy được:** class này biên dịch trong dự án Spring Security 7.x có Servlet web security, nhưng **chưa phải hệ thống OTT gửi mã hoàn chỉnh**. Cần cấu hình user store, password encoder, dịch vụ gửi token và `OneTimeTokenGenerationSuccessHandler`. Trong môi trường production phải xác định email/địa chỉ nhận token từ dữ liệu account đã xác thực, có rate limit và chống lộ magic link; xem mục 10.

**Không nhầm:** `@EnableMultiFactorAuthentication` không biến một password thành hai yếu tố. Nó chỉ làm policy yêu cầu thêm yếu tố do cơ chế thích hợp cung cấp.

## 8. Chỉ yêu cầu MFA cho các endpoint nhạy cảm

Không phải website nào cũng cần hai yếu tố trên mọi trang. Có thể dùng `AuthorizationManagerFactories.multiFactor()` để tạo policy cục bộ cho từng URL.

Trong Spring Security 7.0+, cấu hình ví dụ (**thay thế** ví dụ global ở mục 7, không đưa cả hai `SecurityConfig` vào cùng project):

```java
package com.example.mfa;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationManagerFactories;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMultiFactorAuthentication(authorities = {})
public class SelectiveMfaSecurity {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        var mfa = AuthorizationManagerFactories.multiFactor()
                .requireFactors(
                        FactorGrantedAuthority.PASSWORD_AUTHORITY,
                        FactorGrantedAuthority.OTT_AUTHORITY)
                .build();

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers("/admin/**")
                        .access(mfa.hasRole("ADMIN"))
                        .requestMatchers("/user/settings/**")
                        .access(mfa.authenticated())
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .oneTimeTokenLogin(Customizer.withDefaults())
                .build();
    }
}
```

**Điểm mấu chốt:** `@EnableMultiFactorAuthentication(authorities={})` kích hoạt hạ tầng hỗ trợ nhưng không đặt yêu cầu toàn cục. Đối tượng `mfa` được tạo **trong method**, không được đăng ký là bean factory chung. Vì vậy:

| URL | Rule áp dụng | Cần factor nào? |
| --- | --- | --- |
| `/public/**` | `permitAll()` | Không |
| `/user/settings/**` | `mfa.authenticated()` | Password và OTT |
| `/admin/**` | `mfa.hasRole("ADMIN")` | Password, OTT, ROLE_ADMIN |
| URL còn lại | `authenticated()` | Đăng nhập, không áp thêm hai factor của factory cục bộ |

Đây là ví dụ thể hiện chính xác **mối quan hệ giữa yếu tố được cung cấp và rule yêu cầu chúng**: hai cơ chế có thể tồn tại ở mọi request, nhưng chỉ những endpoint dùng MFA authorization manager mới bắt cả hai.

Không lẫn `securityMatcher` (chọn filter chain) với `requestMatchers` (chọn rule trong chain). Khi có nhiều chain, phải bảo đảm các endpoint nhạy cảm thực sự đi qua chain chứa rule MFA, không bị một chain ưu tiên cao hơn vô tình bỏ qua.

## 9. Cách quy tắc MFA biểu diễn điều kiện AND, OR

### 9.1. Tất cả yếu tố phải có (AND)

Mô hình thông thường:

```text
allow = authenticated
    AND has(FACTOR_PASSWORD)
    AND has(FACTOR_OTT)
    AND businessAuthorization
```

Trong Spring Security 7, factory `AuthorizationManagerFactories.multiFactor().requireFactors(...)` giúp tạo các authorization managers yêu cầu đủ factor và kết hợp với role/authority thông thường.

Với logic đơn giản, tài liệu cũng mô tả `hasAllAuthorities(...)`, ví dụ **Spring Security 7.x snippet** bên trong `authorizeHttpRequests`:

```java
.requestMatchers("/admin/**").hasAllAuthorities(
        "ROLE_ADMIN",
        FactorGrantedAuthority.PASSWORD_AUTHORITY,
        FactorGrantedAuthority.OTT_AUTHORITY)
```

Cách kiểm từng string rõ ràng nhưng dễ lặp và không phải lúc nào cũng diễn đạt được freshness hoặc điều kiện phức tạp. Nếu dự án sử dụng `hasAllAuthorities` theo phiên bản cụ thể, phải xác minh khả năng sẵn có và semantics ở đúng phiên bản. Không dùng `hasAnyAuthority(PASSWORD,OTT)` thay thế: **ANY/OR** cho phép chỉ một factor.

### 9.2. Một trong nhiều tổ hợp yếu tố hợp lệ (OR của các nhóm AND)

Đôi khi chính sách chấp nhận:

- Một lần WebAuthn đủ mức bảo đảm, **hoặc**
- Password **và** OTT.

Đó là:

```text
allow = has(FACTOR_WEBAUTHN)
        OR (has(FACTOR_PASSWORD) AND has(FACTOR_OTT))
```

Không được rút gọn sai thành:

```text
has(FACTOR_WEBAUTHN)
OR has(FACTOR_PASSWORD)
OR has(FACTOR_OTT)
```

Cách sai cho phép chỉ password. Với Spring Security 7, tài liệu đưa cơ chế `AllRequiredFactorsAuthorizationManager.anyOf(...)` kết hợp các nhóm. Những nhóm đó phải phản ánh chính sách bảo đảm của sản phẩm và đặc tính thực sự của WebAuthn/OTT; đừng suy luận mức bảo đảm chỉ từ số hằng số factor.

### 9.3. Quyền và factor kết hợp thế nào?

MFA **không thay thế** `ROLE_ADMIN`, `SCOPE_transfer.write` hay kiểm tenant. Thực tế: `allow = required factors AND required business authority AND resource ownership`. Khi dùng factory để bọc rule, cần kiểm rằng các điều kiện này thực sự là **AND**, không bị override bởi một nhánh filter/entrypoint/fallback.

## 10. Cơ chế cung cấp factor phải được triển khai thật

### 10.1. Password login

`formLogin()` chỉ là việc kích hoạt flow nhận và kiểm username/password. Trong hệ thống thật cần `UserDetailsService`/repository, `PasswordEncoder` thích hợp (như adaptive encoder), giới hạn brute force, bảo vệ session và chính sách reset password. Chỉ lưu username vào session rồi tự gán `FACTOR_PASSWORD` **không** phải xác minh password.

### 10.2. One-Time Token (OTT) login

Spring Security có `oneTimeTokenLogin()`. **OTT khác TOTP/HOTP**:

- **OTT**: server tạo token dùng một lần, gửi người dùng (ví dụ magic link qua email) và kiểm token tại endpoint. Thường không cần người dùng cài authenticator trước đó.
- **TOTP/HOTP**: mã được tính từ secret/chứng cứ đã được thiết lập; không đồng nghĩa với Spring Security `oneTimeTokenLogin()`.

Spring Security cung cấp hạ tầng generate/consume token và giao diện, **không thể tự biết địa chỉ/đường gửi token cho ứng dụng**. Bạn phải cài `OneTimeTokenGenerationSuccessHandler` để gửi qua kênh tin cậy. Cần chính sách TTL, một lần dùng, chống replay, giới hạn số lần xin token, bảo vệ đường dẫn nhận magic link và xác minh người nhận bằng dữ liệu user account, không lấy email đích do attacker tự khai.

Ví dụ **pseudocode triển khai** handler (không phải Java chạy độc lập):

```text
onOneTimeTokenGenerated(request, token):
    username = token.username
    recipient = trustedAccountDirectory.emailFor(username)
    require recipient is verified
    magicLink = trustedPublicBaseUrl + "/login/ott?token=" + encode(token.value)
    secureEmailSender.send(recipient, magicLink)
    redirectUserTo("/ott/sent")
```

Không log raw OTT hoặc magic link, không dùng `request.getHeader("Host")` chưa kiểm chứng làm nguồn tạo link. Ở production, kênh email có thể bị chiếm đoạt; nếu password và OTT cùng bị phục hồi qua một inbox, tính độc lập của factors sẽ suy giảm.

### 10.3. WebAuthn/passkey

WebAuthn có ceremony và checks cryptographic riêng, gồm relying-party ID, origin, challenge, signature, credential binding và user verification theo policy. Chỉ bổ sung `FACTOR_WEBAUTHN` **sau khi** phần xác thực WebAuthn tin cậy thành công. Không dùng một cookie do client tự tuyên bố đã dùng passkey như factor.

### 10.4. OIDC, Bearer token và các yếu tố do IdP xác minh

Một browser ứng dụng dùng `oauth2Login()` có thể được IdP xác thực bằng password/MFA; Resource Server nhận Bearer JWT cũng có thể chứa claims `acr`, `amr`, `auth_time`. Nhưng điều đó **không tự đồng nghĩa** Spring Security đã ghi nhận hai factor cục bộ `FACTOR_PASSWORD` và `FACTOR_OTT`.

Để tin MFA từ bên ngoài, phải xác minh token/issuer/audience/signature/time, ý nghĩa claims theo hợp đồng IdP, mức assurance và freshness. Không được lấy claims từ token chưa kiểm chữ ký hoặc tự nhận header `X-MFA: true` từ client. Nếu policy local yêu cầu PASSWORD + OTT, cần xác định có ánh xạ đáng tin từ IdP sang evidence local hay thực hiện factors ngay tại ứng dụng; không chỉ bật OIDC rồi giả định hai hằng số đã có.

## 11. Freshness: yếu tố có nhưng đã quá cũ

Một yếu tố được xác minh hôm qua có thể đủ để xem dashboard, nhưng **không** đủ duyệt thanh toán hiện tại. Spring Security 7 có `FactorGrantedAuthority.getIssuedAt()` và cho phép rule khai báo `validDuration` cho factor tương ứng.

Ví dụ **Spring Security 7.x** (đoạn code đặt trong phương thức tạo filter chain; cần import `java.time.Duration` và `AuthorizationManagerFactories`):

```java
var passwordLast30Minutes = AuthorizationManagerFactories.multiFactor()
        .requireFactor(factor -> factor
                .passwordAuthority()
                .validDuration(Duration.ofMinutes(30)))
        .build();

http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/admin/**")
        .access(passwordLast30Minutes.hasRole("ADMIN"))
        .anyRequest().authenticated());
```

Trong ví dụ, trang admin yêu cầu `ROLE_ADMIN` và factor password được xác minh trong 30 phút gần đây. Cách này **chỉ yêu cầu password gần đây**, chưa tự đòi OTT nếu policy không thêm. Với tài nguyên cần cả password và OTT mới, phải đưa cả hai factor cùng yêu cầu valid duration tương ứng.

Hãy phân biệt:

- **Factor authority** lưu thời điểm `issuedAt`.
- **Rule của tài nguyên** quyết định yếu tố được xem là còn đủ mới trong bao lâu.
- Cùng một factor có thể đủ mới cho trang A nhưng đã quá cũ cho trang B.

Nếu chỉ kiểm `hasAuthority("FACTOR_PASSWORD")` như chuỗi, bạn có thể **bỏ qua freshness**. Kiểm thời gian bằng kiểu factor và policy hỗ trợ, hoặc bằng evidence đáng tin do AS/IdP cấp.

**Rủi ro session:** nếu factor evidence được lưu dài cùng phiên và không có rule freshness, việc đổi mật khẩu, khóa tài khoản hoặc đăng xuất IdP không tự loại bỏ quyền truy cập. Thiết kế timeout, security context persistence, step-up và session invalidation phù hợp.

## 12. Cơ chế và rule cần nhất quán trong lifecycle phiên

Một flow thực tế thường đi qua những trạng thái:

```text
Anonymous
  │ login bằng password thành công
  ▼
Authenticated + PASSWORD
  │ vào /dashboard: được phép
  │ vào /settings: thiếu OTT → yêu cầu step-up
  │ nộp OTT hợp lệ (cùng danh tính và cùng giao dịch)
  ▼
Authenticated + PASSWORD + OTT
  │ vào /settings: được phép
  │ vào /admin: cần thêm ROLE_ADMIN
  ▼
Đến hạn factor / user bị khóa / session hết hạn
  └── Xác thực lại hoặc từ chối theo policy
```

**Các điều kiện cần kiểm:**

1. OTT không được nâng factor cho **một người dùng khác** với phiên đang xác thực. Liên kết đúng account và request, tránh session swapping.
2. Khi hoàn thành factor tiếp theo, context phải duy trì đúng danh tính, authorities và trạng thái đã xác minh; đừng vô tình ghi đè toàn bộ Authentication hoặc tự giữ factor từ phiên khác.
3. Logout phải hủy phiên/evidence theo chính sách. Session fixation protection, Secure/HttpOnly/SameSite cookie và CSRF cần được cấu hình phù hợp với browser login.
4. Khi quyền user hoặc yêu cầu factor thay đổi, phải xác định cách làm mới session/context. Thay đổi chính sách không mặc nhiên được phản ánh vào một session custom đã cache sai.
5. Remember-me, API key, auth token do client tự khai hoặc URL magic link chưa được tiêu thụ hợp lệ **không phải** bằng chứng OTT mới. Các cơ chế yếu hơn không được cấp authority mạnh.
6. Nếu factor thất bại/hết hạn hoặc hệ thống gửi OTP/OTT bị lỗi, phải **fail closed** ở endpoint có yêu cầu. Có thể dùng recovery flow được thẩm định riêng nhưng không tự động `permitAll()`.

## 13. Spring Security 6.x: không nhầm API theo phiên bản

`FactorGrantedAuthority`, `AuthorizationManagerFactories.multiFactor()`, `@EnableMultiFactorAuthentication` là API giới thiệu từ Spring Security **7.0**. Ứng dụng Boot 3.x / Security 6.x **không thể** copy các import/API này và mong biên dịch. Tuy nhiên nguyên tắc kiến trúc vẫn vậy:

- Dùng authentication mechanism/provider xác thực mỗi yếu tố thật.
- Ghi evidence theo mô hình trusted server-side (session/MFA state) hoặc trusted claims từ IdP.
- Áp dụng `AuthorizationManager<RequestAuthorizationContext>` / method security riêng để kiểm nhiều điều kiện.
- Bảo đảm mối quan hệ AND giữa role/scope và các factor yêu cầu, có TTL, tenant và audit.
- Không để bất kỳ authentication khác như API key, remember-me, JWT chưa có MFA hoặc fallback password-only làm vượt policy nhạy cảm.

**Pseudocode kiến trúc cho Security 6**, không phải API Spring 7:

```text
AuthenticationManager / IdP verifies PASSWORD
    → server-side session contains verifiedPasswordAt

OTT service verifies one-time token for SAME principal
    → server-side session contains verifiedOttAt

AuthorizationManager for /settings
    → require authenticated
    → require verifiedPasswordAt within policy window
    → require verifiedOttAt within policy window
    → require same principal/session and no revocation
    → allow else deny/step-up
```

Lưu trạng thái factor trong một session bean hoặc custom authentication chỉ có ý nghĩa nếu **không cho client sửa** và có bảo vệ session/CSRF. Đừng dùng request parameter `mfa=true` hoặc `@PreAuthorize("isAuthenticated()")` như thay thế factor checks. Nếu xây mới và muốn API MFA chuẩn, cân nhắc nâng cấp phiên bản có hỗ trợ và kiểm tra tài liệu tương ứng.

## 14. HTTP API và máy khách không dùng browser session

MFA trên **web session** khác bearer-token API:

- Với browser, từng mechanism có thể bổ sung factors vào Authentication, và authorization rule quyết định khi nào step-up.
- Với resource server stateless, mỗi request thường được xác thực từ bearer access token. API không thể tự suy ra rằng người dùng đã làm OTT tại IdP chỉ từ việc nhận token. Phải xác minh **access token dành cho API**, issuer, signature hoặc introspection, audience, expiry, scope và các claims assurance theo hợp đồng.
- Nếu token mang `acr`, `amr`, `auth_time`, hãy xác định ý nghĩa cụ thể của issuer; có thể cần token mới sau step-up. Không tự gán `FACTOR_OTT` từ claim `amr` chưa hiểu hoặc từ ID token không dành cho API.
- Một token dùng client credentials thường đại diện cho **service**, không phải user đã MFA. Đừng cho một API key/service token đạt chính sách bắt buộc bằng chứng người dùng.
- Authorization trên dữ liệu vẫn cần tenant, ownership và transaction policy sau khi factor/claims được tin cậy.

**Tách authentication mechanism khỏi policy** vẫn là ý chính. Phía API, việc cung cấp factor có thể xảy ra bên IdP/AS; còn phía Resource Server, quy tắc kiểm **assurance đã được xác minh** nằm ở authorization layer.

## 15. Ma trận kiểm thử đúng quan hệ “cung cấp” và “yêu cầu”

| Trường hợp | Yếu tố/bằng chứng đã được kiểm | Quy tắc | Kỳ vọng |
| --- | --- | --- | --- |
| Guest vào dashboard protected | Không | Authenticated | Từ chối/hướng login |
| User login password vào dashboard | PASSWORD | Authenticated | Cho phép |
| User login password vào settings | PASSWORD | PASSWORD + OTT | Từ chối, yêu cầu OTT |
| User chỉ OTT vào settings | OTT | PASSWORD + OTT | Từ chối, yêu cầu password |
| User password và OTT vào settings | PASSWORD + OTT | PASSWORD + OTT | Cho phép |
| User không phải admin, đủ hai yếu tố vào admin | PASSWORD + OTT, không role | ROLE_ADMIN + hai factor | Từ chối |
| Admin đủ hai yếu tố vào admin | ROLE_ADMIN + PASSWORD + OTT | ROLE_ADMIN + hai factor | Cho phép |
| Admin có OTT quá cũ | Các factor hiện diện nhưng OTT expired theo rule | Fresh OTT | Từ chối, step-up |
| User có role ADMIN nhưng chỉ password | ADMIN + PASSWORD | ROLE_ADMIN + hai factor | Từ chối |
| Attacker gửi `X-FACTOR-OTT: true` | Không có factor đáng tin | PASSWORD + OTT | Từ chối |
| Bearer access token không có MFA từ issuer | Bearer đã kiểm token | Endpoint cần assurance người dùng | Từ chối |
| Password reset hoặc logout | Evidence bị hủy theo policy | Trang nhạy cảm | Yêu cầu login/step-up lại |

Bộ test phải xác minh **không bao giờ** cho controller/service nhạy cảm chạy khi thiếu một yếu tố; chỉ nhìn status code không đủ. Có thể có redirect (browser), 401 (API), 403 (đã login nhưng thiếu quyền), tùy entry point và UX.

### 15.1. Unit test policy và test mechanism là hai lớp khác nhau

**Policy test** có thể dùng Spring Security Test để mock principal/factor authorities. Nó trả lời “khi có đúng tập factor, authorization có yêu cầu đủ không?”. Nhưng việc gắn authority trong mock **không chứng minh** password/WebAuthn/OTT đã được kiểm chứng.

**Mechanism integration test** phải chạy thật qua filter/manager và source của factor: password hash và account policy, OTT single-use/TTL/same user, WebAuthn origin/challenge/signature/RP ID, session state và timestamp. Dùng test environment kiểm soát được, không gửi token thật lên log.

### 15.2. Test missing factor và step-up

Với Spring Security 7, tài liệu mô tả khi rule yêu cầu Password + OTT, người dùng còn thiếu factor có thể được hướng tới endpoint login tương ứng. Trong tích hợp thật cần test đường redirect/login challenge **thực tế**; đừng hardcode rằng mọi lỗi MFA đều là HTTP 403 hoặc mọi flow đều redirect như nhau.

Đặc biệt cần test việc đổi principal giữa hai bước, replay OTT, consume token hai lần, mở nhiều tab, logout giữa chừng, TTL hết hạn và yêu cầu khác nhau ở các route. Nếu test chỉ setup `Authentication` với cả hai authority rồi assert 200, bạn chưa xác minh chất lượng cơ chế cung cấp factor.

## 16. Sự độc lập của yếu tố và chống downgrade

Có đủ **hai nhãn** factor chưa chắc đã có MFA đúng nghĩa. Hỏi:

1. Hai cơ chế có dựa trên bí mật/kênh phục hồi cùng một nguồn không? Nếu mailbox bị chiếm, cả password reset và magic link có thể bị kiểm soát.
2. Factor thứ hai có ràng buộc **đúng user, session và giao dịch** không? Một token của người khác không được hoàn tất MFA cho account hiện tại.
3. Có bảo vệ phishing, brute force, replay, rate limit, token forwarding, CSRF và clickjacking phù hợp với từng mechanism không?
4. Sau khi hoàn tất, có ràng buộc thời gian, thiết bị hoặc yêu cầu reauthentication cho giao dịch giá trị cao không?
5. Có recovery path làm mất bảo đảm không? Ví dụ hỗ trợ “quên mã thì chỉ cần password” tại endpoint duyệt tiền sẽ tạo đường bỏ qua.
6. Có auth method yếu hơn như Basic, API key, remember-me, cookie cũ hoặc OAuth2 bearer không mang assurance vẫn truy cập được endpoint không?
7. Khi thêm một `SecurityFilterChain` khác, endpoint được chọn đúng chain có rule factor không?

**Không phát hành factor authority bằng logic từ header/query string chưa kiểm chứng.** Mọi factor phải bắt nguồn từ cơ chế tin cậy hoặc trusted IdP claims đã kiểm tra đúng. Chính sách phải fail closed khi không đủ evidence.

## 17. Lỗi phổ biến và cách khắc phục

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Chỉ bật `formLogin` và `oneTimeTokenLogin` | Có hai **lựa chọn** đăng nhập, không tự yêu cầu cả hai | Thêm rule yêu cầu đủ factors |
| Chỉ bật `@EnableMultiFactorAuthentication` nhưng không có cơ chế OTT | Người dùng không thể cung cấp factor còn thiếu | Cấu hình OTT/WebAuthn tương ứng và token delivery |
| Dùng `authenticated()` cho admin mà không áp MFA factory | Password-only có thể được chấp nhận | Dùng global factory hoặc selective `mfa.hasRole(...)` |
| Dùng `hasAnyAuthority(PASSWORD,OTT)` | OR, chỉ một factor đủ | Dùng AND / `requireFactors(...)` |
| Nhầm `ROLE_ADMIN` với `FACTOR_PASSWORD` | Có quyền không đồng nghĩa đã MFA | Kiểm riêng role và factors |
| Tự thêm `FACTOR_OTT` vào UserDetails từ database | Chưa từng thực hiện OTT vẫn được cấp authority | Factor chỉ phát sau authentication thật |
| Bỏ `issuedAt`/freshness | Step-up quá cũ có thể vẫn hợp lệ | Dùng `validDuration` hoặc quy tắc time đáng tin |
| Coi OTP email và password luôn độc lập | Rủi ro cùng kênh phục hồi / phishing | Đánh giá channel independence, có thể dùng WebAuthn |
| Dùng `acr`/`amr` từ JWT chưa verify | Token giả có thể bypass MFA | Kiểm issuer, signature, audience, thời gian và hợp đồng IdP |
| Copy API Security 7 sang Security 6 | Không biên dịch hoặc hiểu sai khả năng | Kiểm phiên bản, dùng custom policy hoặc nâng cấp |
| Chỉ test happy path “hai factor thì 200” | Không phát hiện password-only bypass | Negative matrix: thiếu/expired/mixed factors |
| Đăng nhập factor thứ hai cho principal khác | Session/account confusion | Ràng buộc factor với cùng user/session |
| OTT không single-use/TTL | Dễ replay hoặc lộ link kéo dài | TTL, consume atomic, chống replay và rate limiting |
| Cơ chế phục hồi bỏ qua MFA | Recovery trở thành đường xác thực yếu | Thiết kế recovery/step-up có assurance tương đương |
| Không kiểm tenant/quyền dữ liệu | MFA hoàn tất nhưng vẫn truy cập sai tài nguyên | Kết hợp business authorization sau MFA |

## 18. Bài tập thực hành

1. Đọc mẫu global MFA ở mục 7, giải thích rõ dòng nào **cung cấp** Password/OTT và dòng nào **đòi hỏi** đủ hai factor. Nếu xóa `@EnableMultiFactorAuthentication` nhưng giữ hai login mechanisms, policy thay đổi thế nào?
2. Đọc mẫu selective MFA ở mục 8. Vì sao `/dashboard` có thể truy cập với một factor nhưng `/user/settings/**` yêu cầu cả hai? Nếu chuyển `mfa.authenticated()` thành `authenticated()` thì mất điều kiện nào?
3. Tạo test request user có `ROLE_ADMIN` nhưng chỉ password, xác minh không vào được `/admin/**`. Bổ sung OTT đúng và kiểm thành công. Sau đó thử OTT quá hạn.
4. Triển khai `OneTimeTokenGenerationSuccessHandler` gửi magic link tới email lấy từ trusted account directory; bảo vệ `Host`, replay, TTL, limit gửi và token bị lộ log.
5. Thiết kế rule `FACTOR_WEBAUTHN OR (FACTOR_PASSWORD AND FACTOR_OTT)`. Viết biểu thức logic và giải thích tại sao `hasAnyAuthority(...)` của ba factor là sai.
6. Trong ứng dụng Boot 3/Security 6 hiện có, phân tích cách tạo custom authenticated MFA state/AuthorizationManager mà không dùng các API chỉ có ở 7.x. Nêu rõ các nguy cơ stale session và fake factor.
7. Một Resource Server nhận JWT `acr=mfa` từ issuer tin cậy. Xác định điều kiện cần kiểm trước khi chấp nhận token và cách phân biệt nó với `FactorGrantedAuthority` local.

## 19. Tổng kết

- **Cơ chế cung cấp yếu tố** kiểm chứng bằng chứng cụ thể rồi ghi nhận factor đáng tin vào Authentication.
- **Quy tắc yêu cầu đủ yếu tố** là chính sách authorization của tài nguyên: cần factor nào, kết hợp AND/OR ra sao, còn hiệu lực trong bao lâu, kèm role/tenant/quyền gì.
- **Bật nhiều login mechanisms không tự bật MFA**; thiếu authorization rule thì một cơ chế có thể đủ để đăng nhập.
- **Đặt rule yêu cầu factor mà không cung cấp mechanism** thì user không thể hoàn thành flow, hoặc phải được dẫn qua step-up có thiết kế.
- Spring Security **7.0+** có `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication` và `AuthorizationManagerFactories.multiFactor()` cho Servlet; Security **6.x** cần xử lý policy/evidence theo khả năng phiên bản.
- Factor chỉ có giá trị khi xuất phát từ **xác thực thật**, đúng principal, không replay, có lifecycle/freshness phù hợp. Role và authorization nghiệp vụ vẫn cần riêng.
- Test cả phía **cung cấp** (password/OTT/WebAuthn) lẫn phía **yêu cầu** (authorization matrix và bypass).

**Tài liệu chính thức để đọc tiếp:**

- [Spring Security 7.0 — Multi-Factor Authentication](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/mfa.html)
- [Spring Security 7.0 — One-Time Token Login](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/onetimetoken.html)
- [Spring Security 7.0 Javadoc — FactorGrantedAuthority](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html)
- [Spring Security 7.0 Javadoc — EnableMultiFactorAuthentication](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/config/annotation/authorization/EnableMultiFactorAuthentication.html)
- [Spring Security — Authorization architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)