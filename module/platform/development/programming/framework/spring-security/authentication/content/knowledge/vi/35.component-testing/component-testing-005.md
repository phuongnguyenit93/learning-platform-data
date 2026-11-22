# Kiểm thử trạng thái tài khoản, quyền được nạp và việc xóa credentials

## 1. Mục tiêu bài học

Trong Spring Security, một lần đăng nhập không chỉ có điều kiện “mật khẩu đúng”. Kết quả còn phụ thuộc vào **trạng thái tài khoản**, **quyền được nạp từ nguồn đáng tin**, và **cách credentials được xử lý sau khi xác thực**. Một bài test chỉ assert `authentication.isAuthenticated() == true` có thể bỏ sót ba lỗi quan trọng:

- Tài khoản bị khóa, vô hiệu hóa, hết hạn hoặc mật khẩu đã hết hạn vẫn được đăng nhập.
- `UserDetailsService` trả thiếu quyền, thừa quyền, hoặc mapper cấp nhầm `ROLE_ADMIN`.
- Mật khẩu thô/secret còn sót trong `Authentication`, hoặc việc xóa secret làm hỏng một `UserDetails` đang dùng chung trong cache.

Bài này tập trung vào **kiểm thử thành phần (component testing)** của đường xác thực username/password trong **Spring Security 6.x / Spring Boot 3.x với Java 17+**. Có ghi chú cho **Spring Security 7.x** và cơ chế khác như JWT, LDAP, WebAuthn, OTT ở những chỗ quan trọng. Những bài test đơn vị ở đây không cần chạy HTTP server; sau đó bài giải thích thêm test ở filter/HTTP layer để biết ranh giới của chúng.

Kết thúc bài, bạn có thể:

1. Đọc chính xác bốn cờ trạng thái trên `UserDetails` và các exception tương ứng.
2. Viết test thật cho `DaoAuthenticationProvider` và `ProviderManager`, không chỉ dùng mock `@WithMockUser`.
3. Kiểm tra quyền **đến từ nguồn nào**, có được ánh xạ đúng thành `GrantedAuthority` hay không, và không tồn tại quyền tự tạo từ request.
4. Xác minh credentials được xóa khỏi kết quả đăng nhập thành công mà không làm hỏng dữ liệu gốc/cached user.
5. Thiết kế negative tests cho username không tồn tại, sai mật khẩu, account bị khóa, credentials expired và permission change.
6. Phân biệt sự kiện xác thực mới với session đã tồn tại và phân biệt đơn vị kiểm thử provider với tích hợp HTTP.
7. Áp dụng nguyên tắc bảo mật: không trả lý do thất bại quá cụ thể cho người ngoài, không giữ plaintext password, không bỏ erase để “chữa” cache mà không có threat model.

## 2. Các thành phần dưới phép kiểm thử

Đường đi Servlet thông dụng:

```text
UsernamePasswordAuthenticationFilter
       |
       v
UsernamePasswordAuthenticationToken (unauthenticated)
       | principal=username, credentials=raw password
       v
AuthenticationManager: ProviderManager
       |
       v
DaoAuthenticationProvider
       |
       +--> UserDetailsService.loadUserByUsername(username)
       |       -> UserDetails
       |       -> flags + password hash + authorities
       |
       +--> kiểm tra account status trước password
       +--> PasswordEncoder.matches(raw, storedHash)
       +--> kiểm tra credentials không hết hạn
       +--> có thể áp dụng GrantedAuthoritiesMapper
       |
       v
UsernamePasswordAuthenticationToken (authenticated)
       | principal thường là UserDetails
       | authorities đã xác định
       | credentials có thể vẫn còn ở đối tượng provider trả về
       v
ProviderManager.eraseCredentialsAfterAuthentication (mặc định true)
       |
       v
Authentication sau khi xóa credentials
       |
       v
SecurityContext / session khi filter quản lý request HTTP
```

**Chú ý ba tầng độc lập:**

- `UserDetailsService` **nạp dữ liệu**: username, encoded password, các cờ trạng thái và tập authorities. Nó không tự so mật khẩu và không tự tạo `SecurityContext`.
- `DaoAuthenticationProvider` **xác minh** username/password với các policy trạng thái mà provider dùng, rồi tạo `Authentication` thành công.
- `ProviderManager` **điều phối providers** và theo mặc định gọi `eraseCredentials()` trên authentication thành công nếu đối tượng hỗ trợ `CredentialsContainer`.

Trong unit test gọi trực tiếp `manager.authenticate(...)`, Spring Security **không tự đưa kết quả vào `SecurityContextHolder`** như filter HTTP. Test phải kiểm tra object được trả về, không giả định có session/login cookie.

## 3. Các cờ trạng thái của `UserDetails`

`UserDetails` cung cấp các phương thức sau:

| Phương thức | `true` nghĩa là | `false` thường dẫn tới |
| --- | --- | --- |
| `isEnabled()` | Tài khoản được phép dùng | `DisabledException` |
| `isAccountNonLocked()` | Tài khoản không bị khóa | `LockedException` |
| `isAccountNonExpired()` | Tài khoản chưa hết hạn | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Credentials (thường password) chưa hết hạn | `CredentialsExpiredException` |

**Đặc biệt dễ nhầm:** tên ba phương thức chứa chữ **`Non`**. `isAccountNonLocked() == true` là **không bị khóa**; `isCredentialsNonExpired() == false` là **credentials đã hết hạn**.

Với builder `org.springframework.security.core.userdetails.User`, cú pháp được viết theo chiều ngược của các cờ:

```java
User.withUsername("linh")
    .password(encodedPassword)
    .roles("READER")
    .disabled(true)
    .accountLocked(true)
    .accountExpired(true)
    .credentialsExpired(true)
    .build();
```

Các tham số builder `disabled`, `accountLocked`, `accountExpired`, `credentialsExpired` nhận `true` khi **trạng thái xấu đang xảy ra**. Một dòng `.accountLocked(true)` dẫn đến `isAccountNonLocked() == false`.

Không nên đặt cả bốn giá trị `true` trong một test rồi mong bốn exception đều được ném: provider chỉ ném **exception đầu tiên** theo thứ tự kiểm tra thực tế. Mỗi trạng thái phải có fixture và assertion riêng.

### 3.1. Trạng thái tài khoản khác quyền nghiệp vụ

Account có `ROLE_ADMIN` nhưng `disabled=true` không được vượt qua kiểm tra xác thực chỉ vì role cao. Ngược lại, account enabled với `ROLE_READER` vẫn có thể xác thực thành công nhưng không được phép gọi API yêu cầu `ROLE_ADMIN`.

Bởi vậy, test phải có **hai lớp**:

1. **Authentication test**: username/password và account status có cho tạo `Authentication` không?
2. **Authorization test**: nếu `Authentication` hợp lệ, nó mang authorities nào và có qua rule `hasAuthority`/`hasRole` không?

`isAuthenticated()` không thể thay thế việc kiểm tra toàn bộ account policy và quyền được nạp.

## 4. `DaoAuthenticationProvider` kiểm tra trạng thái lúc nào?

Trong đường username/password mặc định của Spring Security 6.x, lớp cha `AbstractUserDetailsAuthenticationProvider` thực hiện kiểm tra theo ý nghĩa:

```text
UserDetails đã được nạp
       |
       +--> Pre-authentication checks:
       |      1. accountNonLocked?
       |      2. enabled?
       |      3. accountNonExpired?
       |
       +--> additionalAuthenticationChecks:
       |      PasswordEncoder.matches(raw, encoded)?
       |
       +--> Post-authentication checks:
              credentialsNonExpired?
```

Các exception điển hình:

```text
isAccountNonLocked() = false      -> LockedException
isEnabled() = false               -> DisabledException
isAccountNonExpired() = false     -> AccountExpiredException
Mật khẩu không đúng              -> BadCredentialsException
isCredentialsNonExpired() = false -> CredentialsExpiredException
```

Thứ tự này giúp kiểm thử chuyên biệt. Ví dụ **credentials expired** có thể chỉ được kiểm tra sau khi password đã xác minh; hãy dùng **password đúng** để assert `CredentialsExpiredException` thay vì nhầm một lỗi password với lỗi expiry.

**Lưu ý API:** `DaoAuthenticationProvider` có thể được cấu hình `setPreAuthenticationChecks(...)`, `setPostAuthenticationChecks(...)`, `setAuthoritiesMapper(...)`, password encoder, cache và các tùy biến khác. Nếu app thay checker hoặc provider, thứ tự/chính sách có thể khác; test phải phản ánh **cấu hình thực tế**, không chỉ kiểm tra class mặc định.

### 4.1. `AccountStatusUserDetailsChecker`

Spring Security cũng có `org.springframework.security.authentication.AccountStatusUserDetailsChecker` để kiểm tra trạng thái người dùng qua giao diện `UserDetailsChecker`. Đây là công cụ có thể tái sử dụng khi viết provider/luồng login tùy chỉnh:

```java
AccountStatusUserDetailsChecker checker =
    new AccountStatusUserDetailsChecker();
checker.check(userDetails);
```

Import:

```java
import org.springframework.security.authentication.AccountStatusUserDetailsChecker;
```

**Phân biệt:** checker này kiểm tra **trạng thái `UserDetails`**; nó không so password, không lấy JWT signature, không quản lý session hay quyền HTTP. Provider khác `DaoAuthenticationProvider` có thể có account-status semantics riêng; không suy từ việc một luồng dùng `UserDetailsService` rằng mặc định nó sẽ gọi đủ tất cả checker.

## 5. Quyền được nạp: `roles`, `authorities` và `GrantedAuthority`

Một `UserDetails` chứa `Collection<? extends GrantedAuthority>` từ nguồn account (DB, LDAP mapper, dịch vụ phân quyền...). Sau khi xác thực, `Authentication.getAuthorities()` là nguồn được các authorization rules như `hasRole`/`hasAuthority` kiểm tra.

| Cách tạo | Authority thực tế |
| --- | --- |
| `.roles("READER")` | `ROLE_READER` |
| `.roles("ADMIN")` | `ROLE_ADMIN` |
| `.authorities("ROLE_ADMIN")` | `ROLE_ADMIN` |
| `.authorities("SCOPE_reports:read")` | `SCOPE_reports:read` |
| `.roles("ROLE_ADMIN")` | **Sai**: builder `roles` tự thêm prefix `ROLE_` |
| `.authorities("ADMIN")` | `ADMIN`, **không tự** thành `ROLE_ADMIN` |

Cách kiểm tra:

```java
Set<String> actual = authentication.getAuthorities().stream()
    .map(GrantedAuthority::getAuthority)
    .collect(Collectors.toSet());
```

Imports tương ứng:

```java
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.security.core.GrantedAuthority;
```

Với tập authorities, thường nên **so tập** (`Set`) hơn là so thứ tự `Collection` nếu policy không yêu cầu thứ tự. Nhưng phải kiểm tra **không có authority thừa**: chỉ assert `contains("ROLE_READER")` có thể bỏ lọt `ROLE_ADMIN` được cấp nhầm.

### Quyền được nạp khác việc client tự khai

- `request.getParameter("role")`, header `X-Role`, email hoặc username không phải nguồn quyền đáng tin.
- Test một `UserDetailsService` giả lập nhận role do test định sẵn; trong sản phẩm, role phải đến từ repository/IdP có contract và kiểm soát quyền.
- `ROLE_ADMIN` là authorization grant; **không** suy từ `isEnabled()==true` hay `isAuthenticated()==true`.
- Với OAuth2 JWT/opaque bearer, authority có thể đến từ scope/claims và converter, **không đi qua** `DaoAuthenticationProvider`. Bài test JWT authority mapping phải dùng converter riêng, không ép mọi đường login vào `UserDetailsService`.
- Với LDAP/SAML/OIDC hoặc passkey, cần xác nhận luồng thật có gọi loader/checker phù hợp; không suy những hành vi của username/password sang mọi authentication provider.

## 6. Dựng project kiểm thử Spring Boot 3.x / Spring Security 6.5

Cần JDK **17+** và một dự án Gradle với Spring Boot 3.x quản lý Spring Security 6.x. Phần unit test chỉ cần Spring Security core, config/crypto và JUnit; để chạy trong project Spring Boot đơn giản có thể dùng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

**Không cần** kết nối database hay chạy HTTP server cho test trực tiếp `ProviderManager` ở mục 7. `BCryptPasswordEncoder(4)` dùng trong unit test để giảm thời gian chạy; **cost 4 không phải khuyến nghị production**. Với production, dùng cost được benchmark theo yêu cầu bảo mật, `DelegatingPasswordEncoder` khi phù hợp, secret management và hash migration an toàn.

Nếu project đang dùng Spring Security **7.x/Boot 4.x**, hãy đối chiếu API với version đó, giữ toàn bộ module cùng major và điều chỉnh Java baseline của dự án. Mã tập trung vào API 6.5, không giả định một cấu hình boot hoàn chỉnh là bắt buộc để kiểm thử một provider.

## 7. JUnit 5: một bộ test thật cho trạng thái, quyền và erase

Tạo file `src/test/java/example/auth/AccountComponentTest.java`. Code bên dưới là **một class Java hoàn chỉnh** chạy với dependency ở mục 6.

```java
package example.auth;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;

import org.springframework.security.authentication.AccountExpiredException;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AccountComponentTest {

    private static final String PASSWORD = "correct-for-component-test";

    // Cost thấp để unit test chạy nhanh, KHÔNG dùng như policy production.
    private final PasswordEncoder encoder = new BCryptPasswordEncoder(4);
    private final String encodedPassword = encoder.encode(PASSWORD);

    private UserDetails fixture(
            boolean disabled,
            boolean locked,
            boolean accountExpired,
            boolean credentialsExpired) {
        return User.withUsername("linh")
            .password(encodedPassword)
            .disabled(disabled)
            .accountLocked(locked)
            .accountExpired(accountExpired)
            .credentialsExpired(credentialsExpired)
            .authorities("ROLE_ANALYST", "SCOPE_reports:read")
            .build();
    }

    private UserDetails active() {
        return fixture(false, false, false, false);
    }

    private AuthenticationManager manager(UserDetails source) {
        // Chỉ nạp account "linh"; mỗi lần trả một BẢN SAO riêng.
        UserDetailsService loader = username -> {
            if (!"linh".equals(username)) {
                throw new UsernameNotFoundException("Not found");
            }
            return User.withUserDetails(source).build();
        };

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(loader);
        provider.setPasswordEncoder(encoder);

        // ProviderManager mặc định xóa credentials sau đăng nhập thành công.
        return new ProviderManager(List.of(provider));
    }

    private Authentication authenticate(
            UserDetails source, String username, String password) {
        return manager(source).authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                username, password
            )
        );
    }

    private Set<String> names(Authentication auth) {
        return auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());
    }

    @Test
    void activeAccountGetsExactlyLoadedAuthorities() {
        UserDetails source = active();
        Authentication auth = authenticate(source, "linh", PASSWORD);

        assertTrue(auth.isAuthenticated());
        assertEquals("linh", auth.getName());
        assertEquals(
            Set.of("ROLE_ANALYST", "SCOPE_reports:read"),
            names(auth)
        );
        assertFalse(names(auth).contains("ROLE_ADMIN"));
        assertTrue(auth.getPrincipal() instanceof UserDetails);
    }

    @Test
    void lockedAccountIsRejected() {
        assertThrows(LockedException.class, () ->
            authenticate(fixture(false, true, false, false),
                "linh", PASSWORD));
    }

    @Test
    void disabledAccountIsRejected() {
        assertThrows(DisabledException.class, () ->
            authenticate(fixture(true, false, false, false),
                "linh", PASSWORD));
    }

    @Test
    void expiredAccountIsRejected() {
        assertThrows(AccountExpiredException.class, () ->
            authenticate(fixture(false, false, true, false),
                "linh", PASSWORD));
    }

    @Test
    void expiredCredentialsAreRejected() {
        assertThrows(CredentialsExpiredException.class, () ->
            authenticate(fixture(false, false, false, true),
                "linh", PASSWORD));
    }

    @Test
    void wrongPasswordFails() {
        assertThrows(BadCredentialsException.class, () ->
            authenticate(active(), "linh", "wrong-password"));
    }

    @Test
    void unknownUserDoesNotExposeUsernameNotFound() {
        assertThrows(BadCredentialsException.class, () ->
            authenticate(active(), "unknown", "wrong-password"));
    }

    @Test
    void managerErasesRawAndPrincipalCredentials() {
        UserDetails stored = active();
        assertNotNull(stored.getPassword());

        Authentication auth = authenticate(stored, "linh", PASSWORD);

        // UsernamePasswordAuthenticationToken đã được ProviderManager erase.
        assertNull(auth.getCredentials());

        // org.springframework.security.core.userdetails.User
        // implements CredentialsContainer; password trong principal bị xóa.
        UserDetails principal = (UserDetails) auth.getPrincipal();
        assertNull(principal.getPassword());

        // Nhưng dữ liệu nền để lookup password cho lần đăng nhập sau
        // vẫn giữ hash, nhờ UserDetailsService đã trả một bản sao.
        assertNotNull(stored.getPassword());
        assertTrue(encoder.matches(PASSWORD, stored.getPassword()));
    }
}
```

Chạy trong project Gradle:

```bash
./gradlew test --tests example.auth.AccountComponentTest
```

**Kỳ vọng:** tám phương thức `@Test` pass khi dùng Spring Security 6.5/JUnit 5 tương thích. Tên file trùng class `AccountComponentTest`, thư mục đúng package `example.auth`.

### Tại sao test gọi `ProviderManager`, không chỉ provider?

Mục tiêu riêng “**xóa credentials sau xác thực**” nằm ở **`ProviderManager`**. Một test chỉ gọi `provider.authenticate(...)` có thể nhận `UsernamePasswordAuthenticationToken` vẫn còn password trong `credentials`, vì manager chưa thực hiện bước erase. Điều đó **không tự là lỗi** của provider.

Test ở mục 7 khởi tạo:

```java
return new ProviderManager(List.of(provider));
```

và gọi `manager.authenticate(...)`, vì vậy kiểm chứng **chuỗi provider + manager**, đúng phạm vi cần quan sát.

## 8. Giải thích sâu việc xóa credentials

### 8.1. `CredentialsContainer` và `ProviderManager`

`org.springframework.security.core.CredentialsContainer` có:

```java
public interface CredentialsContainer {
    void eraseCredentials();
}
```

Sau authentication thành công, mặc định `ProviderManager` kiểm tra object `Authentication` có thực hiện `CredentialsContainer` không. Nếu có, nó gọi `eraseCredentials()` nhằm không giữ credential nhạy cảm lâu hơn cần thiết.

Với `UsernamePasswordAuthenticationToken`:

1. `getCredentials()` trước khi erase có thể là **raw password** được client nộp.
2. `eraseCredentials()` xóa giá trị credentials trên token.
3. Một số `Authentication` còn chuyển tiếp lệnh erase cho **principal và details** nếu các object đó cũng implements `CredentialsContainer`.
4. `org.springframework.security.core.userdetails.User` thực thi `CredentialsContainer`, nên `User#getPassword()` có thể trở thành `null` sau khi principal trong token được erase.

Do đó phải phân biệt:

```text
Authentication.getCredentials()  -> có thể là raw password
((UserDetails) authentication.getPrincipal()).getPassword()
                                 -> có thể là encoded hash
Database/repository passwordHash -> nguồn gốc dùng cho lần login sau
```

**Bài test nên kiểm tra loại dữ liệu nào đang được xóa**, không chỉ assert một thuộc tính mơ hồ như `password == ""`. Với implementation `User` của Spring Security, giá trị sau erase thường là `null`, không phải chuỗi rỗng.

### 8.2. Điều gì không được suy ra?

- Không phải mọi authentication principal có method `getPassword()`. JWT, SAML, OAuth2, passkey và X.509 có cấu trúc khác.
- Không phải mọi credential có thể được xóa sạch khỏi mọi vị trí trong JVM: các bản sao `String`, request buffers hoặc logs khác vẫn có thể tồn tại.
- Đã erase credentials **không** đồng nghĩa session bị hủy; `Authentication` vẫn authenticated và chứa identity/authorities.
- Erase credentials **không** tự thu hồi reset token/refresh token/remember-me cookie.
- Erase trong RAM **không** xóa password hash đã lưu trong DB.
- Không nên log `Authentication.toString()` trong production nếu app có custom principal/details chứa dữ liệu nhạy cảm.

### 8.3. `eraseCredentialsAfterAuthentication`

`ProviderManager` hỗ trợ:

```java
providerManager.setEraseCredentialsAfterAuthentication(false);
```

Đặt `false` có thể tránh tác dụng phụ lên cached `UserDetails` bị chia sẻ tham chiếu, **nhưng làm credentials có thể tồn tại lâu hơn trong authentication/session**. Đây là trade-off bảo mật đáng kể, không phải fix mặc định nên áp dụng.

**Ưu tiên** thay đổi `UserDetailsService`/cache để trả **bản sao tách biệt**, hoặc thiết kế `Authentication` principal không mang password hash. Chỉ tắt erase sau khi có phân tích rủi ro và test rõ ràng về việc gì còn nằm trong session, log, cache và object graph.

## 9. Lỗi khó thấy: cache chia sẻ tham chiếu với principal

Giả sử `UserDetailsService` giữ một `User` trong bộ nhớ và trả **cùng một instance** cho mọi lần login.

```text
Cache/repository
   |
   +--> User object U, U.password = encoded hash
              |
              v
        DaoAuthenticationProvider trả principal = U
              |
              v
        ProviderManager.eraseCredentials()
              |
              v
        U.password = null   (cùng object với cache!)
              |
              v
        Lần login sau: service trả U.password == null
                         -> password verification thất bại
```

Đó là lỗi trạng thái dùng chung, không phải Spring Security cố tình xóa hash khỏi database. Nó thường xuất hiện trong test với `InMemoryUserDetailsManager`, một `Map` fixture hoặc cache tự viết mà không hiểu object reference.

### 9.1. Test chứng minh nguy cơ

File minh họa độc lập `src/test/java/example/auth/SharedReferenceDangerTest.java`:

```java
package example.auth;

import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class SharedReferenceDangerTest {

    @Test
    void sharedPrincipalCanLoseItsStoredHash() {
        var encoder = new BCryptPasswordEncoder(4);
        UserDetails shared = User.withUsername("linh")
            .password(encoder.encode("fixture-only"))
            .roles("USER")
            .build();

        // CỐ Ý SAI: cùng object cho mọi lần lookup.
        UserDetailsService loader = username -> shared;
        var provider = new DaoAuthenticationProvider(loader);
        provider.setPasswordEncoder(encoder);
        var manager = new ProviderManager(List.of(provider));

        assertNotNull(shared.getPassword());

        manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "linh", "fixture-only"
            )
        );

        // Vì principal và cache cùng trỏ tới shared:
        assertNull(shared.getPassword());

        // Lần kế tiếp không còn encoded password để matches().
        assertThrows(BadCredentialsException.class, () ->
            manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "linh", "fixture-only"
                )
            )
        );
    }
}
```

**Đây là test mô phỏng anti-pattern**, không phải cấu hình production nên dùng. Mục đích: chứng minh nguyên nhân thất bại ở lần login thứ hai dù password đầu vào không đổi. Cần test cả lúc caching đang bật và khi ứng dụng có nhiều instances.

**Lưu ý:** lambda ví dụ cố tình bỏ qua giá trị `username` để phơi bày lỗi tham chiếu. Trong `UserDetailsService` thật, luôn phải từ chối username lạ bằng `UsernameNotFoundException` thay vì trả account người khác; nếu không còn có thể tạo lỗi nghiêm trọng hơn mất hash. Đừng đưa lambda này vào ứng dụng chạy thật.

### 9.2. Cách sửa được khuyến nghị

Nếu dữ liệu nguồn là encoded password + flags/authorities bất biến, hãy tạo một instance principal **mới cho mỗi lần lookup**:

```java
UserDetailsService safeLoader = username -> {
    if (!"linh".equals(username)) {
        throw new UsernameNotFoundException("Not found");
    }
    return User.withUserDetails(storedTemplate).build();
};
```

`storedTemplate` phải là object gốc **không bao giờ** được đưa trực tiếp vào `Authentication` để bị erase. Với cache tùy chỉnh:
- Cache lưu dữ liệu account/encoded hash như một snapshot độc lập.
- Provider lấy một bản sao thích hợp để so password và làm principal.
- Không chia sẻ cùng mutable `User` đang chứa password giữa cache và authenticated result.
- Theo dõi việc invalidation khi account locked/disabled hoặc authority thay đổi.
- Không tắt `eraseCredentialsAfterAuthentication` toàn hệ thống chỉ vì một cache bị thiết kế sai.

## 10. Kiểm thử quyền thay đổi giữa hai lần đăng nhập

Một `Authentication` thường là **snapshot quyền tại thời điểm tạo**. Nếu role thay đổi trong repository, không phải mọi session cũ đều tự đổi authorities.

Ví dụ về yêu cầu nghiệp vụ:

```text
T0: linh có ROLE_READER
    -> login -> Authentication A1 [ROLE_READER]

T1: quản trị viên thu hồi ROLE_READER, cấp ROLE_AUDITOR

T2: linh đăng nhập mới
    -> Authentication A2 [ROLE_AUDITOR]

Session A1 chưa bị thu hồi/reload:
    -> có thể vẫn mang ROLE_READER cũ
```

**Một bộ kiểm thử tốt phải kiểm tra hai điều:**
1. Lần authentication **mới** lấy authorities từ nguồn cập nhật, không dùng dữ liệu cũ mà không có chính sách.
2. Với phiên **đã tồn tại**, ứng dụng cần chính sách invalidate/reload hoặc kiểm tra quyền động nếu việc thu hồi phải có hiệu lực ngay.

### Test authority reload trong component

File `src/test/java/example/auth/AuthorityReloadTest.java`:

```java
package example.auth;

import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AuthorityReloadTest {

    @Test
    void newAuthenticationLoadsCurrentAuthorities() {
        var encoder = new BCryptPasswordEncoder(4);
        String hash = encoder.encode("fixture-only");

        AtomicReference<List<String>> source =
            new AtomicReference<>(List.of("ROLE_READER"));

        UserDetailsService loader = username -> {
            if (!"linh".equals(username)) {
                throw new UsernameNotFoundException("Not found");
            }
            // Mỗi lần tạo User mới từ snapshot hiện thời.
            return User.withUsername("linh")
                .password(hash)
                .authorities(source.get().toArray(String[]::new))
                .build();
        };

        var provider = new DaoAuthenticationProvider(loader);
        provider.setPasswordEncoder(encoder);
        var manager = new ProviderManager(List.of(provider));

        Authentication first = manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "linh", "fixture-only"
            )
        );

        source.set(List.of("ROLE_AUDITOR"));

        Authentication second = manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "linh", "fixture-only"
            )
        );

        assertEquals(Set.of("ROLE_READER"), authorities(first));
        assertEquals(Set.of("ROLE_AUDITOR"), authorities(second));
        assertEquals(Set.of("ROLE_READER"), authorities(first));
    }

    private static Set<String> authorities(Authentication a) {
        return a.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());
    }
}
```

**Tại sao không assert role được đổi trên `first`?** `first` là Authentication cũ đã tạo ở T0. Khi reference nguồn đổi, nó không tự chảy ngược vào object cũ. Ứng dụng cần chính sách **revoke session, reauthentication, authorization query theo thời gian thực hoặc cache invalidation** khi thay quyền.

### Cẩn thận `GrantedAuthoritiesMapper`

Nếu app dùng:

```java
provider.setAuthoritiesMapper(authorities -> {
    // Map nhóm từ nguồn ngoài sang quyền ứng dụng.
    return authorities;
});
```

thì test phải kiểm tra kết quả `Authentication.getAuthorities()` **sau mapper**, không chỉ dữ liệu trả bởi loader. Mapper có thể thêm, đổi tên hoặc bỏ role. Một mapper cấp `ROLE_ADMIN` chỉ từ email domain hoặc từ một header không đáng tin là lỗi phân quyền, không phải lỗi password.

## 11. Tự xây `UserDetailsService`: điều gì cần test riêng?

Một `UserDetailsService` dùng repository thường cần:
- Chuyển `username` sang khóa tra cứu theo contract, tránh nhầm tenant/case sensitivity.
- Trả **đúng user** có cùng identity và không lộ dữ liệu user khác.
- Đưa encoded password vào `getPassword()` cho password login.
- Nạp đúng `enabled`, locked/expired flags, credential expiry.
- Nạp authorities từ nguồn đáng tin, không phụ thuộc request header/parameter.
- Ném `UsernameNotFoundException` nếu không có user.
- Không trả `null`, không dựng anonymous user có quyền.
- Có cache isolation và invalidation theo chính sách.
- Không log raw passwords hoặc full credential secrets.

### Một ví dụ test riêng cho mapping từ record

Giả sử DB có record:

```java
record AccountRecord(
    String username,
    String passwordHash,
    boolean enabled,
    boolean locked,
    boolean expired,
    boolean passwordExpired,
    Set<String> privileges
) {}
```

Một loader có thể dựng:

```java
UserDetails loaded = User.withUsername(record.username())
    .password(record.passwordHash())
    .disabled(!record.enabled())
    .accountLocked(record.locked())
    .accountExpired(record.expired())
    .credentialsExpired(record.passwordExpired())
    .authorities(record.privileges().toArray(String[]::new))
    .build();
```

Đây là **snippet cần đặt trong class mapper** với `record` đã được repository trả về. Test mapper nên kiểm tra từng cờ:

```java
assertEquals(!record.enabled(), !loaded.isEnabled());
assertEquals(record.locked(), !loaded.isAccountNonLocked());
assertEquals(record.expired(), !loaded.isAccountNonExpired());
assertEquals(record.passwordExpired(), !loaded.isCredentialsNonExpired());
```

Các assert dùng JUnit `Assertions.assertEquals` trong method test; **không** khuyến nghị dùng biểu thức `!` kép để so cờ khi code production vì khó đọc, nhưng nó làm rõ quan hệ đảo chiều khi mapping.

Đặc biệt kiểm tra mapping password expiry: DB thường lưu `passwordExpiresAt` thay vì boolean; code phải so với `Clock` được inject để unit test deterministic, không lấy `Instant.now()` ở nhiều nơi làm test flaky. Không trộn account expiry với credentials expiry.

## 12. `AccountStatusUserDetailsChecker` trong authentication tùy chỉnh

Một ứng dụng có thể có login bằng OTT, SAML, passkey, pre-authenticated gateway hoặc JWT, sử dụng `UserDetailsService` để lấy local authorities. **Không được suy** rằng những provider này mặc định chạy toàn bộ pre/post checks giống `DaoAuthenticationProvider`.

Nếu custom flow nạp `UserDetails`, có thể chủ động dùng:

```java
AccountStatusUserDetailsChecker checker =
    new AccountStatusUserDetailsChecker();
checker.check(loadedUserDetails);
```

Đây là **snippet trong method** sau khi có nguồn identity đã xác thực phù hợp; nó không thay thế chữ ký token, challenge, mật khẩu hoặc khả năng chống replay. `check` sẽ ném exception nếu trạng thái không cho phép theo checker.

### Unit test trực tiếp checker

```java
var checker = new AccountStatusUserDetailsChecker();

UserDetails locked = User.withUsername("linh")
    .password("{noop}test-only")
    .accountLocked(true)
    .roles("USER")
    .build();

assertThrows(LockedException.class, () -> checker.check(locked));
```

**Các import cần thiết:** `AccountStatusUserDetailsChecker`, `User`, `UserDetails`, `LockedException` và static `Assertions.assertThrows`. Đây là **đoạn chèn trong `@Test`**, dùng password `{noop}` chỉ vì checker không xác minh mật khẩu; **không** dùng `{noop}` trong code production.

Với custom authentication, nếu bạn nạp `UserDetails` rồi bỏ qua `checker.check(...)` và tạo token authenticated trực tiếp, chính luồng mới có thể đăng nhập user bị khóa. Viết regression test cho **mọi provider** đang được triển khai, đặc biệt các đường recovery.

## 13. Kiểm thử thất bại và nguyên tắc không tiết lộ trạng thái tài khoản

Các exception như:
- `LockedException`
- `DisabledException`
- `AccountExpiredException`
- `CredentialsExpiredException`
- `BadCredentialsException`

rất hữu ích khi assert **ở tầng provider**. Tuy nhiên, trả trực tiếp `"ACCOUNT_LOCKED"` ra endpoint công khai có thể tạo kênh **dò sự tồn tại của tài khoản**.

Phân biệt:

| Vị trí | Có nên phân biệt nguyên nhân? |
| --- | --- |
| Unit/component test của provider | **Có**; assert đúng exception theo contract |
| Log/audit nội bộ có quyền truy cập hạn chế | Có thể, trong phạm vi cần thiết và tuân thủ privacy |
| Response HTTP login công khai | Cân nhắc trả thông báo lỗi chung để tránh account enumeration |
| Kênh đã xác minh danh tính của user | Có thể giải thích rõ sau khi có chứng cứ quyền sở hữu |
| Điều tra security incident | Có thể sử dụng reason code có kiểm soát, không log secret |

Ví dụ endpoint công khai có thể trả cùng JSON/status cho username sai hoặc password sai, trong khi test provider vẫn xác nhận `UsernameNotFoundException` được mask thành `BadCredentialsException` theo mặc định.

**Không chữa bằng cách thay mọi exception thành `BadCredentialsException` trong provider tùy chỉnh nếu điều đó làm mất audit/policy.** Phân loại nội bộ ở tầng thích hợp, sau đó chuẩn hóa public response ở authentication failure handler.

## 14. Kiểm thử credentials trước và sau xác thực: đối chiếu đúng đối tượng

Một anti-pattern test:

```java
var user = User.withUsername("linh")
    .password(encoded)
    .roles("USER")
    .build();

assertNotNull(user.getPassword());
// Chỉ test object trước authentication => chưa kiểm tra erasure.
```

Test đúng cần đi qua `ProviderManager` và xem kết quả:

```java
Authentication success = manager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        "linh", "correct-password"
    )
);

assertNull(success.getCredentials());
```

Sau đó nếu principal là `User`, kiểm tra:

```java
UserDetails principal = (UserDetails) success.getPrincipal();
assertNull(principal.getPassword());
```

**Nhưng không assert** `storedAccountPasswordHash == null` trong DB: lưu trữ vẫn phải giữ hash để xác thực lần tiếp theo. Nếu object `storedUserDetails` đã mất hash, đó có thể là lỗi chia sẻ tham chiếu như mục 9.

### Kiểm tra `Authentication` có bị thay đổi các thuộc tính khác

Sau erase, những điều sau cần **tiếp tục hợp lệ**:

```java
assertTrue(success.isAuthenticated());
assertEquals("linh", success.getName());
assertTrue(success.getAuthorities().stream()
    .anyMatch(a -> "ROLE_ANALYST".equals(a.getAuthority())));
```

Xóa credentials không được xóa principal identity, authorities hay quyền hợp lệ. Chỉ xóa secret.

## 15. Custom principal và `CredentialsContainer`

Nếu ứng dụng viết `CustomUserDetails` hoặc `Authentication` riêng, không nên giả định framework biết mọi field nhạy cảm của class đó.

`CredentialsContainer` là hợp đồng:

```java
public interface CredentialsContainer {
    void eraseCredentials();
}
```

Một custom principal có thể chứa:
- password hash (nếu cần cho password verification ở provider);
- token trao đổi với dịch vụ khác;
- recovery code tạm;
- secret MFA hoặc khóa tạm thời.

**Khuyến nghị:** đừng đưa các secret không cần thiết vào principal/session ngay từ đầu. Dùng kiểu dữ liệu tách biệt cho kết quả authentication, chỉ gồm identity và quyền. Nếu có `CredentialsContainer` tự viết, phải kiểm tra `eraseCredentials()` thực sự xóa các field nhạy cảm và cả object lồng nhau theo contract.

Cảnh báo:
- Xóa một trường `String` trong object không bảo đảm có thể xóa mọi bản sao immutable `String` đã tồn tại trong heap.
- Đừng đưa secret vào `toString`, `equals`, logging, JSON serialization hoặc message exception.
- Không đặt raw credential làm một `GrantedAuthority`.
- Khi principal ở cache và implements `CredentialsContainer`, vẫn phải quản lý **copy/ownership** rõ ràng.

### Chỉ assert erasure ở những kiểu hỗ trợ

Với `JwtAuthenticationToken` hoặc token SAML, principal và credentials có semantic khác username/password; policy kiểm tra secret tương ứng cũng khác. Bài test `assertNull(((UserDetails) principal).getPassword())` chỉ hợp lý khi principal **thật** là `UserDetails`.

## 16. Trường hợp cache và mapper khiến test bị “pass giả”

### Vấn đề A — Mock chỉ verify được gọi một lần

```java
verify(userDetailsService).loadUserByUsername("linh");
```

Đây là một assertion hữu ích khi dùng Mockito, nhưng chưa chứng minh dữ liệu được nạp **đúng**. Cần kiểm tra cờ trạng thái và authorities **sau xác thực**.

### Vấn đề B — `@WithMockUser` tự cung cấp role

```java
@WithMockUser(username = "linh", roles = "ADMIN")
```

`@WithMockUser` gắn một Authentication **giả** vào test context, không gọi `UserDetailsService`, `DaoAuthenticationProvider` hay password encoder thực. Test controller có thể pass với `ROLE_ADMIN` dù production loader không bao giờ nạp role đó.

Dùng `@WithMockUser` cho test authorization đơn giản là hợp lệ, nhưng để test mục tiêu bài này, phải:
1. Test loader/mapper bằng fixture account.
2. Test provider/manager bằng credential thật trong môi trường test.
3. Test filter chain/HTTP khi cần xác nhận policy end-to-end.

### Vấn đề C — Assert quyền có nhưng quên quyền thừa

```java
assertTrue(names(auth).contains("ROLE_READER"));
```

Nếu `names(auth)` đồng thời có `ROLE_ADMIN` cấp nhầm, assertion vẫn pass. Với security-sensitive mapping, so **tập chính xác** hoặc ít nhất assert không có các quyền nhạy cảm ngoài contract.

### Vấn đề D — Test chỉ tạo `UsernamePasswordAuthenticationToken.authenticated(...)`

```java
UsernamePasswordAuthenticationToken.authenticated(
    "linh",
    null,
    List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
```

Mã trên tạo một Authentication đã authenticated **mà không xác minh password hay account status**. Đó có thể là fixture trong test authorization, nhưng **không phải** component test `DaoAuthenticationProvider` và tuyệt đối không phải cách tạo phiên production từ dữ liệu HTTP.

## 17. Component test, MockMvc và integration test: ranh giới

| Mức test | Phần thực sự được kiểm tra | Phần KHÔNG được chứng minh |
| --- | --- | --- |
| Unit mapping record → `UserDetails` | Chuyển dữ liệu DB/account sang flags/authorities | Password verification thực, session/filter |
| `DaoAuthenticationProvider` + `ProviderManager` | Username/password, status, authorities, erase | CSRF, HTTP, redirects, session, toàn bộ config |
| `AccountStatusUserDetailsChecker` trực tiếp | Các boolean trạng thái | Password/role/HTTP |
| `MockMvc` với `.with(user(...))` | Authorization đối với principal giả lập | Loader/provider/password login |
| `MockMvc` với `formLogin()` và filter chain thực | Từ HTTP request qua auth filter, CSRF, success/failure | DB phân tán, mail/SMS, browser thật nếu mock |
| Integration với DB/LDAP/IdP | Repository/backend, mapping, token/identity thực | Mọi tình huống vận hành production |
| End-to-end security/regression | Đường đăng nhập, session, account revocation, quyền trên API | Không thay thế kiểm toán code và threat modeling |

### Khi cần MockMvc thật

Ví dụ nếu dùng Spring MVC, `spring-security-test` có request post-processor `formLogin()` để gửi username/password qua filter:

```java
// Trong một @Test đã có MockMvc mvc, SecurityFilterChain và DB/test-user.
mvc.perform(formLogin().user("linh").password("correct-password"))
   .andExpect(authenticated().withUsername("linh"));
```

Imports cần trong test Java:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
```

Đây là **snippet trong method test**, không phải một file tự chạy. Nếu app dùng username/password field, CSRF, hoặc URL đăng nhập tùy chỉnh, hãy điều chỉnh request processor theo cấu hình thực tế. Một test `formLogin()` pass không tự kiểm tra DB role được refresh sau khi account bị disable trong session cũ.

## 18. Đổi trạng thái account sau login: session cũ không tự mất

Kịch bản:

```text
T0: account enabled, ROLE_READER
    -> login -> session A thành công

T1: admin đặt enabled=false

T2: session A vẫn giữ Authentication cũ
    -> request tiếp theo?
```

Không được tự kết luận request T2 bị từ chối chỉ vì `UserDetailsService` hiện trả `isEnabled=false`: authorization thường dùng Authentication đã lưu trong session và **không tự reload account cho mọi request**.

Nếu sản phẩm yêu cầu khóa account có hiệu lực ngay, cần một hoặc nhiều cơ chế:
- Invalidate sessions khi trạng thái đổi.
- Revocation/token version/security stamp tại request boundary.
- Gắn TTL ngắn cho session/token, yêu cầu reauthentication.
- Kiểm tra account trạng thái động tại endpoint nhạy cảm hoặc policy engine.
- Trên hệ thống nhiều instance, đảm bảo sự kiện revoke lan đến cache/session store.
- Không tạo `remember-me` login bypass qua account disabled; kiểm tra đúng luồng remember-me.

### Các test phải tách

1. **New login after lock:** bị `LockedException` theo provider.
2. **Existing session after lock:** hành vi phụ thuộc thiết kế session revocation; test riêng.
3. **Password reset/recovery after lock:** không được tự mở account nếu policy không cho phép.
4. **Authority change:** new login có quyền mới; session cũ bị thu hồi/reload hoặc tiếp tục theo TTL đã quy định.
5. **JWT resource server:** phải kiểm tra issuer/audience/revocation policy riêng; không đợi `UserDetailsService` tự chặn token đang còn hiệu lực.

## 19. Phân tích kết quả lỗi và debugging

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| User `enabled=false` vẫn login | Provider tùy chỉnh bỏ status check; cờ mapping ngược | Test loader + `AccountStatusUserDetailsChecker` hoặc provider |
| Tài khoản bị khóa trả `BadCredentialsException` | Sai password dẫn tới nhánh khác, custom checker, hoặc exception masking | Dùng password đúng trong provider unit test; kiểm tra pre/post config |
| `CredentialsExpiredException` không xuất hiện | Test dùng sai password, hoặc custom provider không check expiry | Test positive password nhưng credentialsExpired=true |
| Test đòi `ROLE_ADMIN` nhưng production thiếu | Test dùng `@WithMockUser` thay cho loader thật | Test `Authentication.getAuthorities()` sau provider |
| Token có `ROLE_USER` nhưng `hasRole("USER")` fail | Prefix bị cấu hình khác hoặc authorities không được nạp | In ra tên authority **trong test local**, không log secret |
| Sau login, `getCredentials()` vẫn còn password | Gọi thẳng `DaoAuthenticationProvider` hoặc tắt erase | Test qua `ProviderManager`, kiểm tra `eraseCredentialsAfterAuthentication` |
| Sau login đầu, login sau fail dù mật khẩu không đổi | Cached `UserDetails` bị erase do dùng chung object | Test reference identity, copy template khi load, kiểm tra cache |
| Cache giữ role cũ sau khi admin thu hồi | TTL/invalidation không đúng | Test old/new login và revoke session |
| `NullPointerException` khi gọi `getPassword()` | `User` principal đã erase, hoặc loại principal khác | Không dựa vào password trong authenticated principal |
| Role thừa bị cấp khi mapping | `GrantedAuthoritiesMapper` thêm quyền quá rộng | So tập quyền **chính xác**, test allowlist/tenant |
| HTTP login trả 302/401 khác unit exception | Filter success/failure handler và entrypoint tạo response | Test MockMvc qua chain thật |
| JWT token hợp lệ nhưng cờ `enabled=false` bị bỏ qua | Resource server chỉ verify token và claim/policy, không gọi DAO | Thiết kế token revocation hoặc account lookup riêng |

Không dùng cách fix “tắt toàn bộ account-status checks” hoặc “giữ credentials trong session” để làm test pass; hãy sửa ownership của dữ liệu và enforcement đúng nơi.

## 20. Checklist QA cho đội phát triển

### Contract của `UserDetails`

- [ ] Username được nạp đúng tenant và account; user không tồn tại bị từ chối.
- [ ] Encoded password hợp lệ cho encoder đang sử dụng, không lưu plaintext.
- [ ] `enabled`, locked, accountExpired, credentialsExpired được map đúng và có test riêng.
- [ ] `getAuthorities()` chỉ chứa quyền từ nguồn đáng tin và đúng prefix.
- [ ] Không có `ROLE_ADMIN` hoặc quyền nhạy cảm ngoài contract.
- [ ] `UserDetailsService` không trả principal mutable dùng chung với authentication đã erase.

### Provider và Manager

- [ ] Test username đúng, password đúng → authenticated.
- [ ] Test password sai và username lạ → thất bại.
- [ ] Test bốn trạng thái xấu → exception đúng.
- [ ] Test `ProviderManager` mặc định xóa raw credentials sau success.
- [ ] Test erasure không hủy nguồn hash của lần login tiếp.
- [ ] Test `Authentication` còn identity/authorities sau erase.
- [ ] Nếu dùng `setAuthoritiesMapper`, kiểm tra tập quyền sau mapping.
- [ ] Nếu đổi `eraseCredentialsAfterAuthentication`, có review rủi ro cụ thể.
- [ ] Không trộn Spring Security 6.x/7.x dependencies và API trong một project.

### Integration và lifecycle

- [ ] HTTP test qua filter chain thật có CSRF khi cần.
- [ ] Session đã tồn tại sau khi khóa user/revoke role có policy rõ ràng.
- [ ] Cache user/authority invalidation được kiểm thử trong cluster.
- [ ] Login qua LDAP, SAML, OIDC, OTT, WebAuthn và Bearer có account-status policy riêng nếu sản phẩm yêu cầu.
- [ ] Public error không tiết lộ user existence, password, hash hoặc thông tin nội bộ.
- [ ] Logging/security events không lưu raw credentials.
- [ ] Negative tests kiểm tra không có đường login yếu hơn bypass account disabled.
- [ ] Regression test chạy khi đổi password encoder, database schema, role mapper và authentication provider.

## 21. Câu hỏi tự kiểm tra

**Câu 1:** `isAccountNonLocked()` trả `true` nghĩa là tài khoản đang khóa?

**Trả lời:** Không, `true` nghĩa **không bị khóa**. Builder `.accountLocked(true)` tạo trạng thái bị khóa, khiến `isAccountNonLocked()==false`.

**Câu 2:** `DaoAuthenticationProvider` trực tiếp trả Authentication còn credentials; đây có phải lỗi rò mật khẩu của framework?

**Trả lời:** Chưa đủ để kết luận. `ProviderManager` mặc định xóa credentials trên authentication thành công. Test erasure cần đi qua manager chứ không chỉ provider.

**Câu 3:** Tại sao cùng password đăng nhập lần đầu thành công nhưng lần hai thất bại sau khi bật cache?

**Trả lời:** Có thể cache và authentication principal trỏ cùng `User` mutable; `eraseCredentials()` trên principal làm password hash trong cache thành null. Cần tách bản sao/correct cache ownership.

**Câu 4:** User có `ROLE_ADMIN` nhưng `.disabled(true)`. Có được authentication thành công không?

**Trả lời:** Không, trong đường `DaoAuthenticationProvider` mặc định nó bị chặn bởi account-status check. Role cao không vượt được chính sách account enabled.

**Câu 5:** Kiểm thử chỉ dùng `@WithMockUser(roles="ADMIN")` có chứng minh `UserDetailsService` nạp đúng `ROLE_ADMIN` không?

**Trả lời:** Không. Đây là principal giả lập, bỏ qua loader/provider. Cần component test trực tiếp rồi integration test qua login filter.

**Câu 6:** Role đổi trong database có lập tức cập nhật mọi Authentication cũ trong session?

**Trả lời:** Không mặc định. Cần test session revocation/reload và policy về độ trễ khi thay quyền.

**Câu 7:** Khi `credentialsExpired=true`, nếu test dùng mật khẩu sai thì nên chờ `CredentialsExpiredException` không?

**Trả lời:** Không. Password check có thể thất bại trước post-authentication check. Dùng password **đúng** để test credential expiry.

**Câu 8:** Có nên đặt `setEraseCredentialsAfterAuthentication(false)` trên mọi ứng dụng để tránh login fail khi cache?

**Trả lời:** Không. Nó giữ credential nhạy cảm lâu hơn. Ưu tiên trả bản sao principal và thiết kế cache không chia sẻ object sẽ bị erase.

## 22. Tổng kết

Một bộ kiểm thử thành phần của Spring Security Authentication tốt cần xác minh **ba tính chất độc lập**:

1. **Trạng thái:** account enabled, chưa locked/expired và credentials còn hạn. Các trạng thái lỗi phải được test riêng với exception phù hợp.
2. **Quyền:** `UserDetailsService` và mapper phải trả đúng tập `GrantedAuthority` trên Authentication đã tạo; không cấp thiếu, không cấp thừa hoặc lấy quyền từ dữ liệu không đáng tin.
3. **Xóa credentials:** với `ProviderManager` mặc định, thông tin bí mật trên `Authentication` và principal phù hợp phải được erase sau khi xác thực, **không** làm hỏng nguồn hash trong repository/cache.

Các test trực tiếp `DaoAuthenticationProvider`/`ProviderManager` là nền tảng, nhưng sản phẩm thực còn cần kiểm tra HTTP filter/session, thay quyền sau login, nhiều authentication mechanisms và revocation. **Test một lần login thành công không chứng minh hệ thống bảo vệ đúng tài khoản bị khóa hoặc đã xóa sạch credentials.**

## 23. Tài liệu chính thức

- Spring Security 6.5 — `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security 6.5 — Authentication Architecture, `ProviderManager` và credentials erasure: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 — `CredentialsContainer`: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/credentials-container.html
- Spring Security 6.5 Javadoc — `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- Spring Security 6.5 Javadoc — `AbstractUserDetailsAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html
- Spring Security 6.5 Javadoc — `ProviderManager`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html
- Spring Security 6.5 Javadoc — `User.UserBuilder`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html
- Spring Security 6.5 Javadoc — `UsernamePasswordAuthenticationToken`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html
- Spring Security 6.5 — Testing Authentication in Spring MVC: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html
