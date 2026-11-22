# Không có AuthenticationProvider hỗ trợ loại token đầu vào

## 1. Ý nghĩa chính xác của lỗi

Trong Spring Security, `AuthenticationManager` là cổng nhận yêu cầu xác thực. Triển khai thường dùng là `ProviderManager`: nó lần lượt xét các `AuthenticationProvider` được cấu hình. Một provider chỉ nên kiểm tra những loại đối tượng `Authentication` mà nó hiểu. Nếu không provider nào xử lý được request token, ứng dụng có thể ném:

~~~text
org.springframework.security.authentication.ProviderNotFoundException:
No AuthenticationProvider found for
demo.security.DeviceOtpAuthenticationToken
~~~

Tên lớp ở trên là ví dụ. Thông báo thực tế thường chỉ rõ **fully qualified Java class** của token đầu vào. Điều này **khác** sai password, sai OTP, access token JWT hết hạn hoặc tài khoản locked: đây trước hết là dấu hiệu **loại request không tương thích với tập providers của manager đang được gọi**.

Ví dụ:

~~~text
POST /mfa/verify
      |
      v
DeviceOtpFilter
  -> new DeviceOtpAuthenticationToken(challengeId, code)
      |
      v
AuthenticationManager.authenticate(request)
      |
      v
ProviderManager [
    DaoAuthenticationProvider,
    RememberMeAuthenticationProvider
]
      |
      +-- Dao supports OTP request? false
      +-- RememberMe supports OTP request? false
      +-- Parent manager? Không có / không thể xử lý
      |
      v
ProviderNotFoundException
~~~

Dù Spring context có `UserDetailsService`, `PasswordEncoder` và các security bean khác, những thành phần ấy **không tự tạo ra một provider có thể xác minh custom OTP token**. Đừng “sửa” lỗi bằng cách bỏ xác thực hoặc đánh dấu token `authenticated=true` từ dữ liệu client.

Một lưu ý quan trọng: `ProviderNotFoundException` không chỉ có thể xuất hiện khi mọi `supports(...)` đều false. Provider có thể trả `null` sau khi đánh giá một request và không provider/parent nào đưa ra kết quả; manager vẫn không thể xác thực request. Vì vậy phải kiểm tra cả **capability** và **kết quả của `authenticate`**.

## 2. Phân biệt Authentication, Provider và Manager

| Thành phần | Nhiệm vụ | Dấu hiệu cần kiểm tra |
|---|---|---|
| `Authentication` | Đối tượng Java biểu diễn request hoặc result: principal, credentials, authorities, authenticated state. | `authentication.getClass().getName()`, `isAuthenticated()`. |
| `AuthenticationProvider` | Biết kiểm tra một hoặc vài loại Authentication. | `supports(Class<?>)` và `authenticate(Authentication)`. |
| `AuthenticationManager` | API thực hiện xác thực. | Manager instance được filter/controller gọi. |
| `ProviderManager` | Thử providers theo thứ tự; có thể gọi parent manager. | `getProviders()`, provider order, parent wiring. |
| `SecurityFilterChain` | Chọn những filters chạy trên một Servlet request. | `securityMatcher`, `@Order`, filter mechanism/manager. |
| `AuthenticationManagerResolver` | Chọn manager theo request/tenant/issuer khi ứng dụng dùng routing động. | Quy tắc resolver, manager thực được chọn. |
| `SecurityContext` | Chứa kết quả đã xác thực của request/phiên. | Không được tạo quyền từ input chưa được provider kiểm tra. |

**Authentication token Java khác access token OAuth2.** `UsernamePasswordAuthenticationToken` là một class mang username/password. `BearerTokenAuthenticationToken` là class mang bearer credential để provider kiểm tra. `JwtAuthenticationToken` thường là **kết quả sau khi JWT đã được decode và xác thực**; không đưa một object do client tự tạo mang tên JwtAuthenticationToken vào SecurityContext rồi coi như đã xác minh chữ ký.

Một login thành công đòi các lớp phối hợp:

~~~text
HTTP form/header/body
      |
      v
Servlet security filter / authentication converter
      |
      v
Authentication request object
      |
      v
Manager picks an AuthenticationProvider
      |
      v
Verify credentials/token/challenge
      |
      v
Authenticated Authentication result
      |
      v
SecurityContext and authorization checks
~~~

Nếu filter tạo sai class, manager có thể bỏ qua tất cả providers dù credential có ý nghĩa nghiệp vụ đúng.

## 3. Hợp đồng của `AuthenticationProvider.supports`

Java interface cốt lõi có dạng:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
~~~

Theo Spring Security Javadoc, `supports` trả true khi provider **có thể đánh giá sâu hơn** request token type; trả true **không bảo đảm** sẽ authenticate thành công.

Trong `authenticate(...)` provider có ba lựa chọn:

1. Trả một `Authentication` result không null đã được xác minh.
2. Trả `null` nếu provider không thể quyết định với instance này và muốn nhường cho provider khác.
3. Ném `AuthenticationException` phù hợp khi credential không hợp lệ, tài khoản bị khóa, backend lỗi hoặc các policy khác.

Đối với token custom:

~~~java
@Override
public boolean supports(Class<?> authentication) {
    return DeviceOtpAuthenticationToken.class
            .isAssignableFrom(authentication);
}
~~~

Đây là **chiều `isAssignableFrom` đúng** nếu muốn hỗ trợ class này và các subclass của nó. Với hệ thống chỉ hỗ trợ đúng một concrete class có thể chọn:

~~~java
@Override
public boolean supports(Class<?> authentication) {
    return DeviceOtpAuthenticationToken.class.equals(authentication);
}
~~~

Không dùng:

~~~java
// Sai thiết kế nếu provider chỉ biết OTP:
@Override
public boolean supports(Class<?> authentication) {
    return true;
}
~~~

Một predicate quá rộng có thể khiến provider nhận JWT, form password hoặc remember-me token mà nó không hiểu; dễ gây `ClassCastException`, xử lý sai credential hoặc cấp quyền trái ý định. Không gọi `setAuthenticated(true)` ở constructor nhận request HTTP chỉ để vượt qua provider selection.

## 4. `ProviderManager` quyết định kết quả thế nào?

Tư duy khái quát:

~~~text
Authentication request -> ProviderManager
  For each provider in configured order:
     if provider.supports(request.getClass()):
        result = provider.authenticate(request)
        if result is non-null -> success, stop
        if result is null     -> try another
        if AuthenticationException -> handle under manager rules
  If no successful provider:
     optionally consult parent AuthenticationManager
  If still no result:
     propagate relevant failure exception
     or throw ProviderNotFoundException
~~~

Đây là **pseudocode**, không sao chép chính xác source của một version. `ProviderManager` Javadoc nêu các trường hợp:

- Một provider trước có thể ném lỗi, provider sau xác thực thành công; kết quả success của provider sau có thể thắng.
- Nếu không provider nào thành công, exception cuối phù hợp có thể được dùng.
- `AccountStatusException` như `LockedException`/`DisabledException` là nhóm được xử lý đặc biệt; không nên thử fallback để vượt account-status policy.
- Parent manager có thể được hỏi khi providers cục bộ không giải quyết yêu cầu theo contract.

Bởi vậy, có bốn kiểu vấn đề cần phân biệt:

| Lỗi | Biểu hiện | Hướng tìm nguyên nhân |
|---|---|---|
| `ProviderNotFoundException` | Không có provider đưa ra được xử lý phù hợp cho token. | Token Java type, provider list, manager/chain, supports/return null. |
| `BadCredentialsException` | Một provider đã nhận request nhưng credentials không hợp lệ. | Verifier/password/OTP/bearer value, không thêm provider bừa. |
| `DisabledException`, `LockedException` | Account status không cho xác thực. | Account lifecycle/recovery, không bypass. |
| `AuthenticationServiceException` | Backend/provider không thể xử lý vì lỗi dịch vụ. | DB/LDAP/IdP/network, fail closed. |

Một HTTP `401` có thể có nguyên nhân ở mọi nhánh khác nhau hoặc vì request chưa gửi credential; không suy từ status code mà bỏ qua exception class.

## 5. Những cặp token/provider thường gặp

| Request Authentication type | Provider/cơ chế thường hỗ trợ | Lưu ý |
|---|---|---|
| `UsernamePasswordAuthenticationToken` | `DaoAuthenticationProvider`, `LdapAuthenticationProvider` và providers password phù hợp. | Form login/HTTP Basic thường dùng loại này. |
| `BearerTokenAuthenticationToken` | `JwtAuthenticationProvider` hoặc `OpaqueTokenAuthenticationProvider`. | Thường do BearerTokenAuthenticationFilter tạo. |
| `PreAuthenticatedAuthenticationToken` | `PreAuthenticatedAuthenticationProvider`. | Cần upstream trust boundary; không tin header user do Internet tự khai. |
| `RememberMeAuthenticationToken` | `RememberMeAuthenticationProvider`. | Dựa trên remember-me trust/key policy, không phải password mới. |
| `AnonymousAuthenticationToken` | `AnonymousAuthenticationProvider` trong các đường có manager tương ứng. | Anonymous không là authenticated login của con người. |
| `OAuth2LoginAuthenticationToken` | `OAuth2LoginAuthenticationProvider` theo client login flow. | Không tự là resource-server JWT support. |
| `Saml2AuthenticationToken` | SAML provider tùy Spring Security SAML module/config. | Phải xác minh response, issuer, signature, audience. |
| Custom `DeviceOtpAuthenticationToken` | Custom `DeviceOtpAuthenticationProvider`. | Cần challenge/session/purpose binding và chống replay. |

**Không đồng nhất input và output.** Bearer JWT request có thể được xử lý thành `JwtAuthenticationToken` sau `JwtDecoder`, còn một custom provider có thể trả result class khác request class. Sai lầm hay gặp là tự tạo result token từ user input rồi gắn vào SecurityContext, vì tưởng có chữ "Jwt" hay "Authenticated" thì Spring sẽ tin.

Nếu exception nói không có provider cho `UsernamePasswordAuthenticationToken` dù bạn gửi Authorization Bearer header, nhiều khả năng **một filter/custom converter đã tạo nhầm loại token** hoặc request vào chain không phù hợp.

## 6. Chẩn đoán lần lượt: token, manager, provider, chain

Thực hiện theo thứ tự, không thay đổi quyền truy cập giữa chừng:

1. Ghi lại **exception class và token class** trong `No AuthenticationProvider found for ...`; không log credentials.
2. Xác định endpoint/method, loại credential mà người dùng đang gửi, nơi request tới sau ingress/proxy.
3. Xác định filter hoặc controller **tạo đối tượng `Authentication`**.
4. In **class của request** ngay trước `AuthenticationManager.authenticate(...)`, không dùng `toString()`.
5. Xác định **manager instance** mà đoạn code đó gọi; đừng chỉ tìm bean tên `authenticationManager`.
6. Nếu là `ProviderManager`, xem danh sách `getProviders()`, thứ tự và parent manager do config tạo.
7. Đối với từng provider, xét `supports(request.getClass())` **không gọi authenticate để dò thử**.
8. Khi supports true, xem provider trả non-null, trả null hay ném exception nào.
9. Kiểm tra Servlet `SecurityFilterChain` nào match request, thứ tự `@Order` và filter nào được add.
10. Sửa đúng loại token/provider và thêm tests cho thành công, credentials sai, status disabled, và missing-provider path.

Đoạn log an toàn:

~~~java
// Snippet tích hợp: biến auth, manager, log phải sẵn có.
log.debug("authenticationRequestType={}",
        auth.getClass().getName());
log.debug("authenticationManagerType={}",
        manager.getClass().getName());
~~~

Nếu đang có đúng `ProviderManager`:

~~~java
if (manager instanceof ProviderManager pm) {
    for (AuthenticationProvider p : pm.getProviders()) {
        log.debug("providerClass={} supportsRequest={}",
                p.getClass().getName(),
                p.supports(auth.getClass()));
    }
}
~~~

Các đoạn này là **mã tích hợp**, cần imports/đối tượng thật. **Không log** `auth.getCredentials()`, password/OTP, raw JWT, token header, session cookie, toàn `Authentication`, hoặc exception message có secret. Đừng chạy `p.authenticate(auth)` chỉ để "thử" từng provider; lệnh ấy có thể tiêu thụ OTP, khóa account hoặc gọi IdP.

## 7. Nguyên nhân A: filter tạo sai token class

Một filter nhận OTP:

~~~json
{
  "challengeId": "ch-204",
  "code": "123456"
}
~~~

nhưng code tạo:

~~~java
Authentication request = new UsernamePasswordAuthenticationToken(
        challengeId, code);
~~~

Khi có `DaoAuthenticationProvider`, nó có thể xử lý request như **username/password**, rồi trả `BadCredentialsException`. Không phải lỗi no-provider, nhưng đây vẫn là sai thiết kế: `challengeId` không phải username và `code` không phải password.

Nếu sửa filter để tạo `DeviceOtpAuthenticationToken` mà không có provider cho class đó, manager sẽ có thể trả `ProviderNotFoundException`. Hướng đúng là tạo request class với semantics rõ ràng **và** bổ sung provider kiểm chứng challenge theo account/session/purpose còn hạn, attempt limit, replay protection và transaction.

**Không làm:** dùng `UsernamePasswordAuthenticationToken` cho OTP chỉ để phù hợp DaoAuthenticationProvider; hoặc tạo `JwtAuthenticationToken` đã authenticated từ client-supplied claims rồi gán vào SecurityContext.

## 8. Nguyên nhân B: provider bean có nhưng manager không biết

Ví dụ dự án khai báo:

~~~java
@Bean
AuthenticationProvider deviceOtpProvider(
        ChallengeVerifier verifier) {
    return new DeviceOtpAuthenticationProvider(verifier);
}
~~~

nhưng custom filter dùng manager tự tạo:

~~~java
AuthenticationManager local = new ProviderManager(
        List.of(daoAuthenticationProvider));
~~~

Manager `local` chỉ thấy DAO provider. Bean `deviceOtpProvider` tồn tại không có nghĩa nó được tự động đưa vào mọi `ProviderManager` mà ứng dụng tự khởi tạo.

Cần hỏi:

- Có nhiều `AuthenticationManager` beans/instances không?
- Có dùng global manager từ `AuthenticationConfiguration.getAuthenticationManager()` nhưng provider được gắn vào chain-local `HttpSecurity` khác?
- Có dùng `HttpSecurity.authenticationProvider(...)` ở chain đúng endpoint chưa?
- `@Configuration` định nghĩa provider được component scan/import đúng hay bị exclude bởi profile?
- Có test mock bean vô hiệu `supports` hoặc thay provider ngoài ý muốn?
- Có parent manager, và nó có provider cần thiết không?

**Phải kiểm tra manager thực sự được filter gọi**, không suy từ dependency trong `pom.xml` hay tên bean. Một cách chữa sai là đăng ký một provider hỗ trợ quá nhiều token vào global manager mà không kiểm soát scope, làm API vô tình chấp nhận hình thức đăng nhập không được phép.

## 9. Nguyên nhân C: endpoint rơi vào nhầm SecurityFilterChain

Ứng dụng có thể có nhiều chain Servlet:

~~~java
// Snippet Spring Security 6, cần import và JwtDecoder tương ứng:
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http.securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
        .sessionManagement(s -> s.sessionCreationPolicy(
                SessionCreationPolicy.STATELESS))
        .build();
}

@Bean
@Order(2)
SecurityFilterChain website(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Đây là **mã minh họa hai bean trong một configuration**, không phải app đầy đủ. `FilterChainProxy` chọn chain theo `securityMatcher`/order; `/api/mfa/verify` có thể đi vào chain API chỉ có JWT provider. Nếu custom OTP filter ở API chain gọi manager này, nó có thể không hỗ trợ OTP request class.

Cần phân biệt:

- **Chain ordering:** `@Order(1)`/`@Order(2)` và matcher.
- **Filter ordering:** vị trí custom filter trước/sau `BearerTokenAuthenticationFilter`, `UsernamePasswordAuthenticationFilter`.
- **Manager wiring:** manager nào được custom filter sử dụng sau khi chain được xây.
- **Request path thực:** proxy có rewrite `/auth` hoặc `/api` không?
- **Public endpoints:** challenge-issue/verify có cần anonymous, partial session hay đã authenticated? Đừng gắn `.anyRequest().authenticated()` để rồi chặn chính flow đăng nhập.

Không sửa bằng `anyRequest().permitAll()` hoặc disable Spring Security. Đó là bỏ kiểm soát chứ không sửa mismatch.

## 10. Nguyên nhân D: `supports` sai chiều hoặc trả true quá rộng

Đây là ví dụ đúng:

~~~java
@Override
public boolean supports(Class<?> type) {
    return DeviceOtpAuthenticationToken.class.isAssignableFrom(type);
}
~~~

Sai chiều có thể tạo false positives:

~~~java
// Sai nếu cần match DeviceOtpToken và subclass:
return type.isAssignableFrom(DeviceOtpAuthenticationToken.class);
~~~

Khi truyền class cha như `AbstractAuthenticationToken`, chiều ngược có thể trả true trong khi provider không thực sự hỗ trợ mọi token con. Dùng `equals` khi chỉ hỗ trợ exact class.

Một case khác: provider trả `true`, nhưng `authenticate` cast token rồi ném `ClassCastException`. Đây là **lỗi code/provider contract**, không phải `BadCredentialsException`; manager có thể không xử lý nó như authentication failure có kiểm soát.

Đừng sửa bằng:

~~~java
// Không được bỏ qua credential chỉ để test xanh:
if (!supports(request.getClass())) {
    return UsernamePasswordAuthenticationToken.authenticated(
            "admin", null, adminAuthorities);
}
~~~

Authentication result **chỉ được tạo sau khi verifier tin cậy xác nhận thực sự**. Kể cả trong app nội bộ, fallback "tự authenticated" là bypass nghiêm trọng.

## 11. Nguyên nhân E: `supports=true` nhưng `authenticate` trả null

Ví dụ provider chuyên xử lý nhiều tenant:

~~~java
@Override
public Authentication authenticate(Authentication authentication) {
    DeviceOtpAuthenticationToken request =
            (DeviceOtpAuthenticationToken) authentication;

    if (!belongsToThisTenant(request)) {
        return null;
    }
    // Verify credential and return trusted result...
}
~~~

Đây là pattern có chủ ý nếu còn **provider khác cùng hiểu request class**. Nếu mọi provider đều trả null, manager không có kết quả. Nếu provider đã kiểm tra OTP nhưng nó sai, nên ném `BadCredentialsException` thay vì trả null để một provider kém chặt hơn có thể thử tiếp.

Những quy tắc cần chốt:

- `null` = provider không thể nhận trách nhiệm với request **này**.
- `BadCredentialsException` = verifier đã xác định credential không hợp lệ.
- `DisabledException`/`LockedException` = trạng thái account ngăn xác thực.
- `AuthenticationServiceException` = backend không thể xử lý.
- Non-null authenticated result = đã xác minh thành công và đủ scope.

Nếu nhiều providers cùng hỗ trợ type, thứ tự và fallback phải được threat-model để không cho user tenant A được xác thực bằng provider tenant B hoặc provider có assurance thấp hơn.

## 12. Demo tích hợp: custom OTP request token

Trong Spring Security 6, một request token custom có thể mở rộng `AbstractAuthenticationToken`:

~~~java
package demo.security;

import org.springframework.security.authentication.AbstractAuthenticationToken;

public final class DeviceOtpAuthenticationToken
        extends AbstractAuthenticationToken {

    private final String challengeId;
    private String code;

    public DeviceOtpAuthenticationToken(
            String challengeId, String code) {
        super(null);
        this.challengeId = challengeId;
        this.code = code;
        super.setAuthenticated(false);
    }

    @Override
    public Object getPrincipal() {
        // challengeId chưa phải identity đã xác thực.
        return challengeId;
    }

    @Override
    public Object getCredentials() {
        return code;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        code = null;
    }
}
~~~

Đây là class request phục vụ **framework integration**, không phải server xử lý OTP hoàn chỉnh. Trạng thái ban đầu **phải unauthenticated**. Việc giữ OTP dưới dạng String vẫn có hạn chế vì String immutable; trong production giảm lifetime, tránh log, hạn credential ở memory, dùng cấu trúc có thể erase khi phù hợp.

Khi flow xác minh OTP là một **bước step-up** trên session đã login, request token cần gắn challenge vào user/session/purpose theo server-side store. Không được lấy subject từ JSON do client tự khai rồi coi là user đã authenticated.

## 13. Demo tích hợp: provider đúng loại và verifier contract

~~~java
package demo.security;

import java.util.Collection;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;

public final class DeviceOtpAuthenticationProvider
        implements AuthenticationProvider {

    private final ChallengeVerifier verifier;

    public DeviceOtpAuthenticationProvider(ChallengeVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    public boolean supports(Class<?> type) {
        return DeviceOtpAuthenticationToken.class
                .isAssignableFrom(type);
    }

    @Override
    public Authentication authenticate(Authentication authentication)
            throws AuthenticationException {
        DeviceOtpAuthenticationToken request =
                (DeviceOtpAuthenticationToken) authentication;

        VerifiedIdentity verified = verifier.verifyAndConsume(
                (String) request.getPrincipal(),
                (String) request.getCredentials());

        if (verified == null) {
            throw new BadCredentialsException(
                    "Invalid authentication challenge");
        }

        Collection<? extends GrantedAuthority> authorities =
                verified.authoritiesFromTrustedRepository();

        return UsernamePasswordAuthenticationToken.authenticated(
                verified.internalPrincipal(), null, authorities);
    }
}
~~~

`ChallengeVerifier` và `VerifiedIdentity` là **domain contracts do ứng dụng phải triển khai**, không phải Spring APIs. Verifier thật phải kiểm tra OTP/chữ ký, challenge expiry, subject/session/purpose, attempts, replay, atomic consume và account status; implementation minh họa **chưa tự đủ để dùng production**.

Provider trả authenticated result kiểu `UsernamePasswordAuthenticationToken` là hợp lệ theo interface, nhưng một hệ thống MFA có thể muốn trả token chuyên biệt chứa assurance/purpose đã kiểm chứng, tránh đánh đồng success của OTP với success của password. Authorities lấy từ trusted repository, **không** từ client hoặc challengeId tùy ý.

## 14. Đăng ký provider vào đúng manager hoặc chain

Ví dụ Spring Boot 3 / Spring Security 6:

~~~java
@Bean
DeviceOtpAuthenticationProvider deviceOtpProvider(
        ChallengeVerifier verifier) {
    return new DeviceOtpAuthenticationProvider(verifier);
}

@Bean
SecurityFilterChain otpChain(HttpSecurity http,
        DeviceOtpAuthenticationProvider otpProvider) throws Exception {
    http.securityMatcher("/mfa/**")
        .authenticationProvider(otpProvider)
        .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());

    return http.build();
}
~~~

Đây **chưa phải application hoàn chỉnh**: cần custom filter tạo DeviceOtpAuthenticationToken và **manager có provider này**, CSRF, xử lý errors, cookie/session hoặc stateless contract. Với enrollment/verify endpoints có thể phải cho phép **partial authentication** để tránh chặn chính bước MFA; đừng dùng matcher hoặc role rule trên mà không xét kiến trúc flow.

Một custom filter không nên vô tình gọi global manager thiếu chain-local provider. Có thể dùng manager hoặc resolver được tạo/nối cho flow đó, hoặc custom `ProviderManager` có provider OTP và parent phù hợp. Mục tiêu là **cùng token class được tạo bởi filter phải có một provider đáng tin trong manager mà filter thực sự gọi**.

Khi thêm provider vào `HttpSecurity`, kiểm tra bean lifecycle và filter constructor dependencies theo phiên bản Spring Security; không suy từ dòng `http.authenticationProvider(...)` rằng mọi filter ngoài chain sẽ tự thấy provider.

## 15. Dự án Maven Java 17 có thể chạy để tái hiện lỗi thật

Phần này dùng **Spring Security Core 6.5.11** trực tiếp, không cần Spring Boot/web server. Ví dụ cố ý tạo một manager thiếu provider cho OTP rồi tạo manager thứ hai có đủ provider. Các credential `demo-pass` và `123456` chỉ là fixture trong chương trình, **không phải thuật toán bảo mật production**.

Cây thư mục:

~~~text
provider-not-found-demo/
  pom.xml
  src/main/java/demo/ProviderNotFoundDemo.java
~~~

### `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>provider-not-found-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-core</artifactId>
            <version>6.5.11</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Version cụ thể dùng để cố định demo, không có ý khẳng định đây là bản mới nhất. Dự án Spring Boot có dependency management riêng nên tránh khai báo lẫn các phiên bản Spring Security tùy tiện.

### `src/main/java/demo/ProviderNotFoundDemo.java`

~~~java
package demo;

import java.util.List;
import java.util.Objects;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public class ProviderNotFoundDemo {

    static final class OtpRequest extends AbstractAuthenticationToken {
        private final String user;
        private String code;

        OtpRequest(String user, String code) {
            super(null);
            this.user = user;
            this.code = code;
            super.setAuthenticated(false);
        }

        @Override
        public Object getPrincipal() {
            return user;
        }

        @Override
        public Object getCredentials() {
            return code;
        }

        @Override
        public void eraseCredentials() {
            super.eraseCredentials();
            code = null;
        }
    }

    static final class PasswordProvider implements AuthenticationProvider {
        @Override
        public boolean supports(Class<?> type) {
            return UsernamePasswordAuthenticationToken.class
                    .isAssignableFrom(type);
        }

        @Override
        public Authentication authenticate(Authentication request) {
            boolean valid = Objects.equals("alice", request.getName())
                    && Objects.equals("demo-pass", request.getCredentials());

            if (!valid) {
                throw new BadCredentialsException("Bad demo password");
            }

            return UsernamePasswordAuthenticationToken.authenticated(
                    "alice", null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER")));
        }
    }

    static final class OtpProvider implements AuthenticationProvider {
        @Override
        public boolean supports(Class<?> type) {
            return OtpRequest.class.isAssignableFrom(type);
        }

        @Override
        public Authentication authenticate(Authentication request) {
            boolean valid = Objects.equals("alice", request.getName())
                    && Objects.equals("123456", request.getCredentials());

            if (!valid) {
                throw new BadCredentialsException("Bad demo OTP");
            }

            return UsernamePasswordAuthenticationToken.authenticated(
                    "alice", null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER")));
        }
    }

    static void check(
            String label, AuthenticationManager manager,
            Authentication request) {
        try {
            Authentication result = manager.authenticate(request);
            System.out.println(label + ": "
                    + (result.isAuthenticated() ? "authenticated" : "not authenticated"));
        } catch (AuthenticationException ex) {
            System.out.println(label + ": "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        AuthenticationManager passwordOnly =
                new ProviderManager(List.of(new PasswordProvider()));

        AuthenticationManager withOtp =
                new ProviderManager(List.of(
                        new PasswordProvider(), new OtpProvider()));

        check("password valid", passwordOnly,
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "alice", "demo-pass"));

        check("otp no provider", passwordOnly,
                new OtpRequest("alice", "123456"));

        check("password incorrect", passwordOnly,
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "alice", "wrong"));

        check("otp with provider", withOtp,
                new OtpRequest("alice", "123456"));

        check("otp incorrect", withOtp,
                new OtpRequest("alice", "wrong"));
    }
}
~~~

Chạy trong thư mục dự án, có JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ProviderNotFoundDemo
~~~

**Stdout dự kiến của chương trình** (không tính thông báo Maven/plugin nếu môi trường in thêm):

~~~text
password valid: authenticated
otp no provider: ProviderNotFoundException
password incorrect: BadCredentialsException
otp with provider: authenticated
otp incorrect: BadCredentialsException
~~~

Diễn giải:

- Password request có provider hỗ trợ và giá trị fixture đúng → authenticated.
- OTP request đi vào manager chỉ có password provider → `ProviderNotFoundException`.
- Password request có provider hỗ trợ nhưng credential sai → `BadCredentialsException`.
- Thêm OTP provider vào manager thứ hai → OTP request thành công.
- OTP provider đã được chọn nhưng OTP fixture sai → `BadCredentialsException`, không phải thiếu provider.

Vì chương trình dùng Spring APIs thật, phải có JARs trên classpath; dùng Maven là cách chạy phù hợp, không thể chỉ chạy `javac ProviderNotFoundDemo.java` trần khi chưa tải dependencies.

**Giới hạn:** code này kiểm tra chuỗi constant, không có password hashing, TOTP algorithm, challenge expiry, atomic replay prevention hay session/tenant binding. Trong production phải dùng `PasswordEncoder`, verifier đúng phương thức, rate limits và trusted state. Đây là demo dispatch/exception, không phải mẫu triển khai OTP thật.

## 16. Kiểm thử direct manager và supports predicate

Những kiểm thử quan trọng:

| Case | Kỳ vọng |
|---|---|
| Password provider hỗ trợ `UsernamePasswordAuthenticationToken`. | `supports(...) == true`. |
| Password provider không hỗ trợ `DeviceOtpAuthenticationToken`. | `supports(...) == false`. |
| OTP provider hỗ trợ đúng custom type. | `supports(...) == true`. |
| Manager thiếu OTP provider. | `ProviderNotFoundException`. |
| Provider có mặt nhưng password/OTP sai. | `BadCredentialsException`. |
| Provider trả `null` cho instance không thuộc mình. | Manager thử provider khác theo contract. |
| Account disabled/locked. | Không fallback sang provider kém an toàn. |
| Manager có parent khác. | Parent behavior đúng policy, không bypass chain. |
| Result có đúng principal/authorities. | Only after verification; roles từ trusted source. |
| Auth request class kế thừa custom type. | `isAssignableFrom`/`equals` đúng kỳ vọng. |
| Kích hoạt trace logging. | Không có raw credentials/JWT/OTP trong logs. |

JUnit test ý tưởng:

~~~java
@Test
void noProviderForCustomOtpRequest() {
    AuthenticationManager manager =
            new ProviderManager(List.of(new PasswordProvider()));

    assertThrows(ProviderNotFoundException.class,
            () -> manager.authenticate(
                    new OtpRequest("alice", "123456")));
}
~~~

Snippet test này giả định các classes trong demo và JUnit 5 `assertThrows` đã import; cần `junit-jupiter` test dependency. Đối với ứng dụng Spring Boot dùng `spring-boot-starter-test`. Test tương tự cho `BadCredentialsException` để chứng minh phân biệt đúng hai tình huống.

**Không chỉ test unit supports.** Một app có thể có provider hoàn hảo nhưng filter/manager wiring sai; cần integration test đúng endpoint và chain.

## 17. Kiểm thử MockMvc để phát hiện chain sai

Trong ứng dụng Spring MVC:

- Dùng `@SpringBootTest` + `@AutoConfigureMockMvc` có filters.
- Với `MockMvcBuilders.webAppContextSetup(...)`, tích hợp `springSecurity()`.
- Đưa vào request OTP/JWT qua **real filter/converter path** cần kiểm tra.
- Không dùng `@WithMockUser` hoặc `SecurityMockMvcRequestPostProcessors.jwt()` rồi tuyên bố **real provider đã được gọi**: hai helper này tạo/đặt mock authentication để kiểm tra authorization.
- Test cả đúng path và path bị match vào chain khác.
- Giữ CSRF token đúng nếu POST dùng cookie session; một lỗi `403` do CSRF không chứng minh provider mismatch.

Ví dụ test matrix:

~~~text
POST /mfa/verify   valid challenge   -> provider called, success policy
POST /mfa/verify   invalid code      -> bad credentials / generic response
POST /mfa/verify   expired challenge -> reject, no authenticated result
POST /mfa/verify   missing provider  -> controlled auth failure, audit
POST /mfa/verify   another tenant    -> reject, no cross-tenant fallback
GET  /api/orders   valid JWT         -> correct resource-server provider
GET  /api/orders   invalid JWT       -> decoder rejects, no bypass
POST /login        valid password    -> Dao/LDAP provider handles request
~~~

HTTP status tùy entry point và failure handler (web login có thể redirect, REST API trả 401). Assert exception type ở manager-level test, còn HTTP integration test nên assert **client-visible behavior an toàn, không có side effect, đúng filter/manager được gọi**.

## 18. Authentication events và logging

`DefaultAuthenticationEventPublisher` có mapping từ `ProviderNotFoundException` sang `AuthenticationFailureProviderNotFoundEvent` trong Spring Security. Tuy nhiên event chỉ được phát nếu đường `AuthenticationManager` có event publisher được cấu hình, không tự đảm bảo mọi custom filter sẽ có event.

Taxonomy audit nội bộ có thể dùng:

~~~json
{
  "outcome": "FAILURE",
  "category": "PROVIDER_CONFIGURATION",
  "requestTokenClass": "demo.security.DeviceOtpAuthenticationToken",
  "managerId": "otp-manager",
  "route": "/mfa/verify",
  "requestId": "req-a3b",
  "occurredAt": "2026-11-06T08:00:00Z"
}
~~~

Đây là **schema gợi ý**, không phải event payload tự có. Không log `Authentication.getCredentials()`, bearer string, password, OTP, secret, token claims nhạy cảm hay full request body. Trong public response, không liệt kê tên class/providers; tránh để attacker đọc kiến trúc auth.

`ProviderNotFoundException` thường là **configuration/integration defect**. Không tính nó như một lần đoán password sai rồi khóa tài khoản hàng loạt. Nếu deployment mới tạo spike provider-not-found, kiểm tra change set, security chain order, bean wiring và canary environment.

## 19. OAuth2 Resource Server: JWT provider được tạo thế nào?

Với Spring Security Servlet và OAuth2 resource server JWT:

~~~java
http.authorizeHttpRequests(a -> a.anyRequest().authenticated())
    .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()));
~~~

Để vận hành, dự án cần resource-server/JOSE dependencies và `JwtDecoder` (ví dụ cấu hình issuer URI). Flow điển hình:

~~~text
Authorization: Bearer eyJ...
        |
        v
BearerTokenAuthenticationFilter
        |
        v
BearerTokenAuthenticationToken
        |
        v
JwtAuthenticationProvider + JwtDecoder
        |
        v
JwtAuthenticationToken (authenticated result)
        |
        v
SecurityContext -> authorization
~~~

Nếu ứng dụng chỉ bật `oauth2Login()` để làm OIDC browser client, **không tự có** bearer resource-server chain cho API. Ngược lại, bật resource-server JWT không tự tạo form-login/LDAP/OTP providers.

Quan trọng hơn lỗi provider: JWT thật phải kiểm **signature, issuer, audience, expiry, token purpose và scope**. Đừng tạo một `JwtAuthenticationToken` từ client claims và tự gắn vào SecurityContext để tránh exception; cách ấy bỏ qua cryptographic verification.

## 20. Reactivity, multi-tenant và manager resolver

Trong **Spring WebFlux**, `ReactiveAuthenticationManager`/`SecurityWebFilterChain` có API và semantics reactive, không phải cùng `ProviderManager` Servlet. Một reactive manager có thể trả `Mono.empty()` để nhường xử lý theo contract; phải debug đúng implementation thay vì áp nguyên mô hình exception Servlet.

Trong ứng dụng nhiều tenant/issuer, `AuthenticationManagerResolver<HttpServletRequest>` chọn manager theo request. Một tenant có `JwtAuthenticationProvider`, tenant khác lại chọn manager chỉ có DAO; token class như nhau nhưng có thể sinh provider-not-found **chỉ ở một tenant**.

Cần kiểm tra resolver mapping dựa trên tín hiệu đáng tin; `iss` lấy từ JWT chưa verify chỉ nên là **hint chọn verifier**, và verifier phải xác nhận lại signature/issuer/audience trước khi chấp nhận token. Đừng cho unknown tenant fallback sang manager chung chấp nhận credentials yếu hơn.

Nếu custom filter trực tiếp sử dụng global manager trong khi chain-local manager có provider cần thiết, lỗi chỉ xuất hiện ở một số request. Ghi manager ID/class/correlation, không log bearer tokens.

## 21. Anti-patterns cần tránh

**Anti-pattern 1: xử lý lỗi bằng `permitAll()`.** Bỏ authentication requirement không sửa provider; mở endpoint có thể chấp nhận request chưa xác thực.

**Anti-pattern 2: `supports()` luôn true.** Provider nhận token types không có verifier tương ứng.

**Anti-pattern 3: tự `setAuthenticated(true)` trên token từ JSON.** Đây là bypass verifier, không phải giải pháp.

**Anti-pattern 4: đặt `UsernamePasswordAuthenticationToken` cho mọi loại credential.** Token class cần phản ánh semantics; password provider không phải OTP/JWT provider.

**Anti-pattern 5: tạo `new ProviderManager(...)` ở từng controller.** Có thể bỏ mất beans/configuration, event publisher, parent/chain semantics; khó bảo đảm consistency.

**Anti-pattern 6: return null khi password sai để provider khác thử.** Có thể mở fallback bypass.

**Anti-pattern 7: bắt `ProviderNotFoundException` rồi trả login thành công.** Fail open nghiêm trọng.

**Anti-pattern 8: chuyển sang `DaoAuthenticationProvider` vì có UserDetailsService.** DAO chỉ phù hợp username/password mechanism, không kiểm chứng bearer JWT, SAML hay WebAuthn challenge.

**Anti-pattern 9: tin `jwt()` test helper đã kiểm JWT signature.** Helper mock authentication, không chạy decoder.

**Anti-pattern 10: chỉ kiểm tra tên bean và bỏ qua chain/manager instance.** Provider có trong context nhưng không có trong manager request đang gọi.

**Anti-pattern 11: đăng ký provider vào mọi chains để “an toàn”.** Tăng attack surface: endpoint stateless có thể chấp nhận form/password mà architecture không định.

**Anti-pattern 12: dùng username/tenant từ request để chọn cross-tenant provider thiếu kiểm chứng.** Cần trust boundary và provider mapping được kiểm thử.

## 22. Bộ kiểm tra vận hành trước khi kết thúc điều tra

- [ ] Exception class thật là `ProviderNotFoundException`, không phải `BadCredentialsException`.
- [ ] Request token Java class đã được ghi nhận an toàn.
- [ ] Filter/converter tạo đúng class với credential semantics.
- [ ] Manager instance được filter/controller dùng đã được xác minh.
- [ ] Danh sách providers và `supports` đúng trên chính manager đó.
- [ ] Return `null`/non-null/exception được phân biệt và kiểm thử.
- [ ] Account status errors không bị fallback vượt qua.
- [ ] `SecurityFilterChain` matcher và `@Order` được test cho endpoint thật.
- [ ] Custom provider được đăng ký đúng chain/manager, không chỉ có bean.
- [ ] OTP verifier có expiry, replay protection, attempts, user/session binding.
- [ ] JWT decoder kiểm signature/issuer/audience/expiry; không dùng fake authenticated result.
- [ ] Parent manager và dynamic resolver không mở quyền ngoài policy.
- [ ] Negative tests: wrong password, wrong OTP, disabled user, missing provider, cross-tenant.
- [ ] Authentication failure event phân loại configuration defect và được giám sát.
- [ ] Không có raw credentials, OTP, session cookies, JWT trong logs.
- [ ] Chỉ sửa tối thiểu và xác nhận test qua filter chain/real request sau deployment.

## 23. Kết luận

Thông báo **“Không có AuthenticationProvider hỗ trợ loại token đầu vào”** là tín hiệu rằng **đối tượng Authentication request đang được gửi tới một manager không có provider nào xử lý thành công loại đó**. Cần truy vết theo thứ tự: **HTTP request → filter/converter → request token Java class → AuthenticationManager cụ thể → các providers và supports → authenticate result/exception → SecurityContext**.

Sửa bền vững là tạo đúng request type, đăng ký provider có verifier thực vào **đúng manager/chain**, xử lý `supports` và `authenticate` đúng contract, đồng thời giữ ranh giới MFA, JWT, session và tenant. Đừng tắt security hoặc cấp authenticated result từ input chưa kiểm chứng.

Bằng cách tái hiện `ProviderNotFoundException` với `ProviderManager` thật và kiểm thử cả trường hợp password sai/OTP sai, người học phân biệt được **lỗi cấu hình provider** với **lỗi chứng thực credential**, tránh sửa sai và tạo lỗ hổng đăng nhập.

## Tài liệu tham khảo

- [Spring Security 6.5 – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager`, providers.
- [Spring Security 6.5 – AuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html): `supports`, `authenticate` và null result.
- [Spring Security 6.5 – ProviderManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html): provider order, parent manager, exception semantics.
- [Spring Security 6.5 – ProviderNotFoundException Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderNotFoundException.html): exception no-provider.
- [Spring Security – Servlet SecurityFilterChain Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter chain selection và order.
- [Spring Security – JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): bearer authentication, JwtDecoder và claim validation.
- [Spring Security – Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html): failure event mapping.
- [Spring Security – MockMvc Test Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): test chạy security filters thật.
- [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): login failure, account enumeration và error handling.
