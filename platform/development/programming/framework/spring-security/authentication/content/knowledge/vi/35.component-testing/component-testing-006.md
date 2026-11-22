# Kiểm thử nâng cấp mật khẩu và cập nhật dữ liệu sau xác thực trong Spring Security

## 1. Mục tiêu bài học

Trong một hệ thống đã vận hành nhiều năm, mật khẩu có thể được lưu bằng các thuật toán/cấu hình khác nhau: bcrypt cost cũ, PBKDF2 với tham số cũ, hoặc một định dạng legacy đã được phê duyệt để di trú. Khi người dùng **đăng nhập thành công**, ứng dụng có thể tận dụng mật khẩu vừa được người dùng nhập hợp lệ để **mã hóa lại bằng chính sách mới** (*opportunistic password rehash / upgrade on login*), rồi lưu bản hash mới mà không yêu cầu đổi mật khẩu đồng loạt.

Bài học giải quyết **hai phạm vi kiểm thử có liên quan nhưng khác nhau**:

1. **Nâng cấp password encoding sau khi xác thực đúng**: `PasswordEncoder.matches` phải xác minh credential; `upgradeEncoding` quyết định hash có cần nâng cấp không; `UserDetailsPasswordService.updatePassword` lưu **hash đã mã hóa**, không lưu password thô.
2. **Cập nhật dữ liệu sau authentication success**: ghi `lastSuccessfulLoginAt`, audit sự kiện login, thiết bị/phiên hoặc đăng nhập lần cuối; không được ghi sự kiện **thành công** nếu xác thực thất bại. Cần quản lý giao dịch, idempotency và xử lý lỗi ghi dữ liệu.

Trọng tâm là **kiểm thử thành phần**: kiểm tra đúng đối tượng, lời gọi, giá trị hash, thứ tự, dữ liệu sau xác thực và các nhánh âm tính. Phân biệt unit test của `DaoAuthenticationProvider`, integration test với DB và kiểm thử login thật qua Servlet filter.

Các ví dụ API Spring dùng **Spring Security 6.5 / Spring Boot 3.x / Java 17+**. Các test chứa mocked dependencies phải được chạy trong project Spring có JUnit 5, Mockito và Spring Security. Phần Java thuần ở cuối có thể chạy trực tiếp với JDK 17.

## 2. Vì sao rehash khác với đổi mật khẩu?

Một ứng dụng thay chính sách lưu mật khẩu từ “bcrypt cost 10” sang “bcrypt cost 12” không biết password thô của mọi người. Nó chỉ lưu một hàm một chiều, nên **không thể giải mã hash cũ rồi tạo hash mới**. Khi user login bằng password hợp lệ, ứng dụng tạm có raw credential trong bộ nhớ, có thể:

```text
POST /login
  -> UsernamePasswordAuthenticationFilter
  -> AuthenticationManager / ProviderManager
  -> DaoAuthenticationProvider
       -> UserDetailsService.loadUserByUsername()
       -> account flags: enabled, nonLocked, nonExpired
       -> PasswordEncoder.matches(raw, storedHash)
          | false -> BadCredentialsException, KHÔNG ghi rehash
          | true
       -> check credentials nonExpired
       -> optional compromised-password check
       -> nếu có UserDetailsPasswordService:
            PasswordEncoder.upgradeEncoding(storedHash)?
               | false -> giữ hash cũ
               | true:
                    PasswordEncoder.encode(raw)
                    UserDetailsPasswordService.updatePassword(user, newHash)
       -> Authentication authenticated (nếu mọi bước thành công)
  -> Spring Security authentication-success flow
       -> session/context handling, remember-me, events, success handler
  -> application audit/lastLoginAt policy
```

**Rehash không phải user đổi password**: password đăng nhập về mặt logic vẫn giữ nguyên, chỉ thay biểu diễn mật mã và tham số lưu trữ. Không tự phát email “mật khẩu đã đổi” hoặc thu hồi mọi session chỉ vì rehash trừ khi chính sách tổ chức yêu cầu.

**Đổi password thật** (user cung cấp mật khẩu mới sau xác minh phù hợp) là một luồng nghiệp vụ riêng: phải kiểm tra mật khẩu hiện tại/step-up, chính sách mật khẩu, cập nhật hash và thu hồi session/token theo chính sách. Cả hai có thể dùng `PasswordEncoder.encode` nhưng semantics/test khác nhau.

## 3. Hợp đồng API cần nắm rõ

| API | Trách nhiệm | Đâu là assertion chính? |
| --- | --- | --- |
| `UserDetailsService.loadUserByUsername` | Đọc tài khoản và encoded password đã lưu | Đọc đúng user; không tạo user mới khi sai username |
| `PasswordEncoder.matches(raw, encoded)` | Kiểm chứng mật khẩu được nhập với hash cũ | Sai password = false; không có rehash hoặc success audit |
| `PasswordEncoder.upgradeEncoding(encoded)` | Quyết định **hash hiện có** có cần mã hóa lại không | Hash cũ = true; hash hiện hành = false theo policy |
| `PasswordEncoder.encode(raw)` | Tạo hash theo encoder policy mới | Kết quả không phải raw; matches được với raw |
| `UserDetailsPasswordService.updatePassword(user, newEncoded)` | Ghi encoded hash mới vào kho bền vững | Chỉ gọi khi xác thực thành công **và** upgrade cần; dữ liệu DB thực sự đổi |
| `DaoAuthenticationProvider` | Điều phối xác thực password + nâng cấp nếu được cấu hình | Auth success/failure và lời gọi update đúng nhánh |
| `AuthenticationSuccessHandler` | Hook thành công của flow filter login tương ứng | Chỉ chạy sau authentication thành công ở flow đó |
| `AuthenticationFailureHandler` | Hook lỗi của flow filter login | Không ghi lastSuccess/update success data |
| `AuthenticationSuccessEvent` | Sự kiện thành công từ authentication infrastructure khi event publisher được cấu hình | Listener phù hợp, không đếm trùng với interactive event |
| `InteractiveAuthenticationSuccessEvent` | Sự kiện authentication tương tác do login filter phát | Dùng nếu muốn đo login tương tác, không mặc định coi nó là mọi lần authenticate |

**Chi tiết từ Spring Security 6.5:** `DaoAuthenticationProvider` kiểm tra `userDetailsPasswordService != null` trước khi gọi `upgradeEncoding`. Nếu không cấu hình `UserDetailsPasswordService` cho provider đang sử dụng, **chỉ khai báo encoder mạnh hơn không bảo đảm tự động cập nhật hash**. Đừng dựa trên một bean chỉ nằm trong `ApplicationContext` mà không xác minh provider thực sự được nối tới nó.

### UserDetailsPasswordService nhận mã đã được encode

Chữ ký:

```java
// API hợp đồng, không phải file Java độc lập
public interface UserDetailsPasswordService {
    UserDetails updatePassword(UserDetails user, String newPassword);
}
```

Tên tham số `newPassword` có thể khiến người đọc tưởng là mật khẩu thô, nhưng **hợp đồng yêu cầu đây là encoded value** do `PasswordEncoder.encode` tạo. Implementation phải lưu nó nguyên vẹn theo schema, không gọi `encode` một lần nữa để tránh double-encoding.

Method phải trả **UserDetails đã cập nhật**; không trả null hay UserDetails của account khác. Lưu ý khi `UserDetails` là custom principal có các fields/roles/tenant, implementation cần giữ đúng các trường quan trọng.

### Không giả định Authentication principal đã được refresh

Trong đường xử lý nội bộ của Spring Security 6.5, `AbstractUserDetailsAuthenticationProvider` chuẩn bị `principalToReturn` từ `UserDetails` ban đầu rồi truyền vào `createSuccessAuthentication`. `DaoAuthenticationProvider` có thể gọi `updatePassword` và dùng `UserDetails` cập nhật cho **authorities** nhưng principal ban đầu không nhất thiết được thay bằng chính object trả về từ `updatePassword`.

Do đó **test rehash phải đọc lại repository và kiểm tra lời gọi updater**, thay vì chỉ kiểm tra `((UserDetails) authentication.getPrincipal()).getPassword()` đã bằng hash mới. Đừng lưu bản hash cũ của principal vào DB lần nữa sau login. Đây là bẫy đặc biệt khi session/cache chứa `UserDetails` cũ.

## 4. PasswordEncoder và format lưu trữ

Spring Security khuyên dùng adaptive one-way password hashing và cơ chế `DelegatingPasswordEncoder` để quản lý nhiều định dạng:

```text
{bcrypt}$2a$10$...
{pbkdf2@SpringSecurity_v5_8}...
{scrypt@SpringSecurity_v5_8}...
{argon2@SpringSecurity_v5_8}...
```

Phần `{id}` chọn implementation xác minh. Thông thường:

```java
PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

boolean valid = encoder.matches(rawPassword, storedEncodedPassword);
boolean shouldRehash = encoder.upgradeEncoding(storedEncodedPassword);
String newEncoded = encoder.encode(rawPassword);
```

Đây là **mảnh code** cho class đã import `org.springframework.security.crypto.factory.PasswordEncoderFactories` và `org.springframework.security.crypto.password.PasswordEncoder`. Mặc định hiện hành nên được xác minh ở **version thực tế** thay vì hard-code giả định một id mãi mãi.

`DelegatingPasswordEncoder` hỗ trợ xác minh định dạng legacy được cấu hình rõ ràng, nhưng **không tự đoán** thuật toán khi hash thiếu prefix. Hash không có id hoặc id không được map có thể ném `IllegalArgumentException`; phải di trú có kiểm soát, không giải quyết bằng cách cho phép `NoOpPasswordEncoder` trên toàn hệ thống production.

### UpgradeEncoding có thể không phải “khác id”

- Thay id như `{pbkdf2}` sang `{bcrypt}` có thể khiến `DelegatingPasswordEncoder.upgradeEncoding` muốn rehash.
- **Cùng id** nhưng tham số quá yếu (ví dụ bcrypt cost nhỏ hơn policy hiện tại) cũng có thể cần nâng cấp nếu encoder implementation hỗ trợ kiểm tra.
- Default method `PasswordEncoder.upgradeEncoding` trả **false** nếu implementation không override. Với custom encoder cần chủ động triển khai chính sách này và kiểm thử nó.

Ví dụ test thật dùng `BCryptPasswordEncoder`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import static org.junit.jupiter.api.Assertions.*;

class BCryptUpgradePolicyTest {
    @Test
    void oldCostIsUpgradableAndNewCostIsNot() {
        // Cost 5/6 CHỈ để unit test chạy nhanh, không dùng production.
        var old = new BCryptPasswordEncoder(5);
        var current = new BCryptPasswordEncoder(6);

        String oldHash = old.encode("correct-horse");
        assertTrue(current.matches("correct-horse", oldHash));
        assertTrue(current.upgradeEncoding(oldHash));

        String newHash = current.encode("correct-horse");
        assertNotEquals("correct-horse", newHash);
        assertTrue(current.matches("correct-horse", newHash));
        assertFalse(current.matches("wrong", newHash));
        assertFalse(current.upgradeEncoding(newHash));
    }
}
```

Cấu hình work factor thật nên được benchmark trên phần cứng production và đáp ứng chính sách bảo mật. Không copy cost 5/6 từ test vào ứng dụng thực.

## 5. Ma trận kiểm thử nhánh cần có

| Trường hợp | Xác thực | Có encode lại? | Có gọi updater? | Có success audit? |
| --- | --- | --- | --- | --- |
| Password đúng, hash legacy, updater được cấu hình | Thành công | **Có** | **Một lần** | Theo flow thành công |
| Password đúng, hash đã đạt policy | Thành công | **Không** | **Không** | Có |
| Password sai, hash legacy | Thất bại | **Không** | **Không** | **Không** |
| User không tồn tại | Thất bại | Không | Không | Không |
| Account disabled/locked/expired | Thất bại | Không | Không | Không |
| Credential expired hoặc compromised theo policy | Thất bại theo cơ chế | Không | Không | Không |
| Password đúng, legacy nhưng không có updater | Thành công với hash cũ | **Không rehash qua provider** | Không | Có |
| Password đúng, legacy nhưng update DB lỗi | Xử lý failure theo provider/DB policy | Có thể đã tính new hash | Đã gọi, nhưng chưa commit | Không phát tín hiệu thành công giả |
| Hai login cùng mật khẩu khi legacy | Có thể cả hai hợp lệ theo chính sách | Có thể tính nhiều lần | **Chỉ một write thắng CAS** | Ghi đúng số login thành công |
| User reset password đồng thời rehash | Tùy thứ tự và policy | Không được ghi đè hash password mới | CAS/version bắt buộc | Không thành công dựa credential stale |
| Login lại sau rehash | Thành công | Không | Không | Mỗi successful login có audit riêng |
| Event/handler retry | Không đổi authentication result | Không lặp đổi hash | Không lặp mutation không mong muốn | Idempotency theo event ID |

**Một test chỉ kiểm tra `auth.isAuthenticated() == true` là chưa đủ**. Nó không chứng minh DB đã cập nhật, mã đã được encode, hay failure path không ghi dữ liệu thành công.

## 6. Unit test thật vào DaoAuthenticationProvider bằng Mockito/JUnit 5

Đây là lớp test độc lập **trong một project có dependencies Spring Security và Mockito**, không phải chương trình Java SE chạy bằng `javac` thuần. Nó gọi `DaoAuthenticationProvider.authenticate(...)` trực tiếp, không dùng MockMvc để loại bỏ nhiễu từ HTTP/session.

Dependencies trong một ứng dụng Spring Boot 3.x đã cấu hình Gradle plugin đúng version:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Với một project **Spring Boot test starter** thông dụng, JUnit 5/Mockito đã sẵn; bảo đảm test runtime khớp Spring Security 6.x được sử dụng.

Tạo file **`src/test/java/demo/auth/PasswordUpgradeProviderTest.java`**:

```java
package demo.auth;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class PasswordUpgradeProviderTest {

    private static UserDetails userWithHash(String hash) {
        return User.withUsername("alice")
                .password(hash)
                .roles("USER")
                .build();
    }

    private static DaoAuthenticationProvider provider(
            UserDetailsService loader,
            PasswordEncoder encoder,
            UserDetailsPasswordService updater) {

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(loader);
        provider.setPasswordEncoder(encoder);
        provider.setUserDetailsPasswordService(updater);
        return provider;
    }

    private static UsernamePasswordAuthenticationToken attempt(String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", password);
    }

    @Test
    void successfulLegacyLoginRehashesAndPersistsNewEncodedPassword() {
        UserDetails oldUser = userWithHash("{old}hash");
        UserDetails updatedUser = userWithHash("{new}hash");

        UserDetailsService loader = mock(UserDetailsService.class);
        PasswordEncoder encoder = mock(PasswordEncoder.class);
        UserDetailsPasswordService updater = mock(UserDetailsPasswordService.class);

        when(loader.loadUserByUsername("alice")).thenReturn(oldUser);
        when(encoder.matches("correct", "{old}hash")).thenReturn(true);
        when(encoder.upgradeEncoding("{old}hash")).thenReturn(true);
        when(encoder.encode("correct")).thenReturn("{new}hash");
        when(updater.updatePassword(oldUser, "{new}hash"))
                .thenReturn(updatedUser);

        DaoAuthenticationProvider provider =
                provider(loader, encoder, updater);
        Authentication result = provider.authenticate(attempt("correct"));

        assertNotNull(result);
        assertTrue(result.isAuthenticated());
        assertEquals("alice", result.getName());

        verify(encoder).matches("correct", "{old}hash");
        verify(encoder).upgradeEncoding("{old}hash");
        verify(encoder).encode("correct");
        verify(updater, times(1)).updatePassword(oldUser, "{new}hash");
        // Không assert principal.getPassword() là hash mới;
        // kiểm tra repository trong integration test.
    }

    @Test
    void successfulLoginWithCurrentHashMustNotWrite() {
        UserDetails currentUser = userWithHash("{new}hash");
        UserDetailsService loader = mock(UserDetailsService.class);
        PasswordEncoder encoder = mock(PasswordEncoder.class);
        UserDetailsPasswordService updater = mock(UserDetailsPasswordService.class);

        when(loader.loadUserByUsername("alice")).thenReturn(currentUser);
        when(encoder.matches("correct", "{new}hash")).thenReturn(true);
        when(encoder.upgradeEncoding("{new}hash")).thenReturn(false);

        Authentication result = provider(loader, encoder, updater)
                .authenticate(attempt("correct"));

        assertTrue(result.isAuthenticated());
        verify(encoder).upgradeEncoding("{new}hash");
        verify(updater, never()).updatePassword(any(), anyString());
    }

    @Test
    void badPasswordNeverUpdatesHash() {
        UserDetails oldUser = userWithHash("{old}hash");
        UserDetailsService loader = mock(UserDetailsService.class);
        PasswordEncoder encoder = mock(PasswordEncoder.class);
        UserDetailsPasswordService updater = mock(UserDetailsPasswordService.class);

        when(loader.loadUserByUsername("alice")).thenReturn(oldUser);
        when(encoder.matches("wrong", "{old}hash")).thenReturn(false);

        assertThrows(BadCredentialsException.class,
                () -> provider(loader, encoder, updater)
                        .authenticate(attempt("wrong")));

        verify(encoder, never()).upgradeEncoding(anyString());
        verify(updater, never()).updatePassword(any(), anyString());
    }

    @Test
    void noConfiguredPasswordServiceMeansNoAutomaticUpgrade() {
        UserDetails oldUser = userWithHash("{old}hash");
        UserDetailsService loader = mock(UserDetailsService.class);
        PasswordEncoder encoder = mock(PasswordEncoder.class);

        when(loader.loadUserByUsername("alice")).thenReturn(oldUser);
        when(encoder.matches("correct", "{old}hash")).thenReturn(true);

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(loader);
        provider.setPasswordEncoder(encoder);
        // CỐ Ý không setUserDetailsPasswordService

        Authentication result = provider.authenticate(attempt("correct"));
        assertTrue(result.isAuthenticated());
        verify(encoder, never()).upgradeEncoding(anyString());
        verify(encoder, never()).encode("correct");
    }

    @Test
    void failedPersistenceMustNotReportSuccessfulAuthentication() {
        UserDetails oldUser = userWithHash("{old}hash");
        UserDetailsService loader = mock(UserDetailsService.class);
        PasswordEncoder encoder = mock(PasswordEncoder.class);
        UserDetailsPasswordService updater = mock(UserDetailsPasswordService.class);

        when(loader.loadUserByUsername("alice")).thenReturn(oldUser);
        when(encoder.matches("correct", "{old}hash")).thenReturn(true);
        when(encoder.upgradeEncoding("{old}hash")).thenReturn(true);
        when(encoder.encode("correct")).thenReturn("{new}hash");
        when(updater.updatePassword(oldUser, "{new}hash"))
                .thenThrow(new IllegalStateException("DB write failed"));

        assertThrows(IllegalStateException.class,
                () -> provider(loader, encoder, updater)
                        .authenticate(attempt("correct")));
        verify(updater, times(1)).updatePassword(oldUser, "{new}hash");
    }
}
```

Chạy (từ project đã khai báo Gradle):

```bash
./gradlew test --tests demo.auth.PasswordUpgradeProviderTest
```

**Kỳ vọng:** 5 tests PASS khi dependency Spring Security 6.5 và Mockito/JUnit tương thích. Các phép `verify(...)` kiểm tra **lời gọi nhánh**; để chứng minh DB được commit, phải chạy integration test kho dữ liệu thật ở phần sau.

### Vì sao không dùng @WithMockUser để test rehash?

`@WithMockUser` cung cấp sẵn `SecurityContext` đã authenticated, bỏ qua login filter và `DaoAuthenticationProvider`. Nó rất hữu ích cho test authorization ở controller, nhưng **không kích hoạt `matches`, `upgradeEncoding` hay `updatePassword`**.

Tương tự, `SecurityMockMvcRequestPostProcessors.user(...)` cài principal giả để test request, **không** phải kiểm thử credential verification. Với mục tiêu bài này, cần gọi provider thật hoặc đi qua HTTP login filter thật.

## 7. Production service: chỉ ghi encoded hash và bảo vệ concurrency

Một `UserDetailsPasswordService` implementation dùng JDBC có thể cập nhật hash theo điều kiện bản cũ (*compare-and-set*):

```java
package demo.auth;

import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;

public final class JdbcPasswordUpgradeService
        implements UserDetailsPasswordService {

    private final JdbcOperations jdbc;

    public JdbcPasswordUpgradeService(JdbcOperations jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public UserDetails updatePassword(UserDetails oldUser, String newHash) {
        // SQL minh họa schema app_users(username,password_hash,...).
        // newHash đã do PasswordEncoder.encode(...) tạo; không hash thêm lần hai.
        int changed = jdbc.update("""
                UPDATE app_users
                   SET password_hash = ?
                 WHERE username = ?
                   AND password_hash = ?
                """,
                newHash, oldUser.getUsername(), oldUser.getPassword());

        if (changed != 1) {
            // Không ghi đè password reset/upgrade khác đang diễn ra.
            // Từ chối hoặc retry TOÀN BỘ xác thực từ credential mới nhất.
            throw new AuthenticationServiceException(
                    "Credential changed during upgrade");
        }

        // Chỉ phù hợp khi user là dạng Spring Security User thường.
        return User.withUserDetails(oldUser)
                .password(newHash)
                .build();
    }
}
```

Đoạn trên là class Java có thể compile khi có `spring-jdbc` và Spring Security, nhưng **chưa phải ứng dụng tự chạy** vì cần DataSource/schema thực. Sử dụng immutable `accountId` thay vì mutable username nếu hệ thống cho đổi username. Nếu custom `UserDetails` chứa tenant/account metadata, hãy tạo bản copy giữ đủ dữ liệu; `User.withUserDetails(...)` không tự giữ các field domain-specific.

### Vì sao WHERE cần old password hash hoặc version?

```text
T0: hash hiện tại = H1 (legacy)
A: login với password cũ; xác minh trên H1
B: người dùng reset password thành H2 (mật khẩu KHÁC)
A: write H3 = encode(password cũ) không kiểm tra trạng thái hiện tại

Nếu UPDATE chỉ WHERE username = alice:
    A ghi đè H2 bằng H3 -> reset password vừa xong bị đảo ngược!

Nếu UPDATE ... WHERE password_hash = H1:
    B đã commit H2 -> A update 0 row -> không thể ghi đè.
```

CAS có thể dựa vào `password_hash` cũ hoặc `credential_version`. Khi hai lần login đúng cùng một hash H1 cùng muốn upgrade, cả hai có thể tính H3/H4 khác salt, nhưng **chỉ một request** ghi thành công; request kia thấy 0 row. Cần policy xử lý cạnh tranh rõ ràng:

- **Fail closed + yêu cầu thử lại** là phương án đơn giản, không vô tình xác thực bằng password đã bị đổi.
- Hoặc ứng dụng có thể **tái xác thực với credential phiên bản mới** ở một tầng đủ tin cậy; phải có raw password hợp lệ, giới hạn retry và chống DoS. `UserDetailsPasswordService.updatePassword` chỉ nhận hash mới, không nhận password thô để tự kiểm chứng lại.
- Không coi mọi CAS miss là “cứ login tiếp” và không chấp nhận success bằng password cũ sau khi user vừa reset.

**Ghi dữ liệu bằng JDBC phải có test transaction/rollback thật**, không chỉ mock `JdbcOperations.update(...)` rồi kết luận persistence đúng. Nếu dùng repository/JPA, xác minh optimistic lock (`@Version`) hoặc conditional update trên bản hiện hành.

### Cấu hình provider tường minh cho Spring Security 6.5

```java
// Mảnh cấu hình trong @Configuration của Spring Boot 3.x:
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}

@Bean
UserDetailsPasswordService passwordUpgradeService(JdbcOperations jdbc) {
    return new JdbcPasswordUpgradeService(jdbc);
}

@Bean
DaoAuthenticationProvider daoProvider(
        UserDetailsService users,
        PasswordEncoder encoder,
        UserDetailsPasswordService upgrades) {

    DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
    provider.setPasswordEncoder(encoder);
    provider.setUserDetailsPasswordService(upgrades);
    return provider;
}
```

Imports cần thiết: `org.springframework.context.annotation.Bean`, `org.springframework.jdbc.core.JdbcOperations`, `org.springframework.security.crypto.password.PasswordEncoder`, `org.springframework.security.crypto.factory.PasswordEncoderFactories`, `org.springframework.security.core.userdetails.UserDetailsService`, `org.springframework.security.core.userdetails.UserDetailsPasswordService`, `org.springframework.security.authentication.dao.DaoAuthenticationProvider`.

Đây là **cấu hình thành phần**, còn việc provider bean này có được dùng trong `AuthenticationManager` thực tế phụ thuộc cách dựng security chain và Boot auto-configuration. Integration test phải **xác minh đúng ProviderManager/DaoAuthenticationProvider được gọi**; không chỉ assert bean tồn tại.

## 8. Kiểm thử integration với DB: đừng dừng ở Mockito

Mockito có thể chứng minh `updatePassword` được gọi, nhưng không chứng minh:

- SQL cập nhật đúng account và đúng cột;
- dữ liệu thực sự commit;
- concurrency-safe CAS hoạt động;
- bản hash mới có prefix/id/parameters đúng;
- cached `UserDetails` và principal/authorities không bị sai;
- lần đăng nhập sau đọc lại hash mới và không rehash vô hạn.

Một integration test sử dụng Testcontainers PostgreSQL hoặc database test tương đương nên:

1. Khởi tạo `app_users` với user `alice`, `password_hash = legacyHash`, account enabled.
2. Dùng `PasswordEncoder` thật với current policy và `UserDetailsService` thật.
3. Chạy `AuthenticationManager.authenticate(UsernamePasswordAuthenticationToken.unauthenticated(...))` qua provider **được wired thật**.
4. Đọc DB bằng JDBC/repository để so sánh `password_hash` trước/sau.
5. Assert `encoder.matches(raw, newHash) == true`, `upgradeEncoding(newHash) == false`, và new hash khác old hash.
6. Authenticate lại bằng raw password như cũ; assert không có thêm password-update SQL lần nữa.
7. Test wrong password, disabled account, locked account, expired credentials: DB hash không đổi.
8. Tạo hai requests đồng thời truy cập **cùng DB**, đảm bảo không ghi đè password reset và policy CAS được áp dụng.
9. Nếu dùng session/caches, invalidate hoặc refresh dữ liệu liên quan đúng cách.

Ví dụ pseudo-code **theo logic integration**, không giả vờ là test class độc lập:

```java
String oldHash = repository.findPasswordHash("alice");

Authentication auth = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "correct-password"));

assertTrue(auth.isAuthenticated());

String storedAfter = repository.findPasswordHash("alice");
assertNotEquals(oldHash, storedAfter);
assertTrue(passwordEncoder.matches("correct-password", storedAfter));
assertFalse(passwordEncoder.upgradeEncoding(storedAfter));

// Đăng nhập lần nữa, DB password_hash không thay đổi.
authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "correct-password"));
assertEquals(storedAfter, repository.findPasswordHash("alice"));
```

Hàm `repository.findPasswordHash` là abstraction **của ứng dụng**, phải triển khai và inject. Trên các adaptive encoders có salt ngẫu nhiên, **không so sánh hash với một chuỗi cố định**; xác minh bằng `matches` và policy parameters. Mỗi lần encode cho cùng password thường ra chuỗi khác.

### Kiểm tra SQL bằng transaction độc lập

Một test chạy tất cả steps trong một transaction rollback của test có thể che vấn đề **commit**, isolation và các event/outbox sau commit. Với hành vi production, hãy dùng ít nhất một test không rollback toàn bộ, hoặc chạy two-connection/two-transaction assertions và cleanup bằng fixture đáng tin. Kiểm thử CAS bằng PostgreSQL thật, không dựa vào concurrency semantics của H2 khi production dùng PostgreSQL.

## 9. Cập nhật dữ liệu sau authentication success là một nghiệp vụ riêng

Các trường thường được cập nhật khi người dùng đăng nhập:

| Field/hành vi | Khi nào cập nhật? | Lưu ý |
| --- | --- | --- |
| `lastSuccessfulLoginAt` | Sau xác thực thành công theo loại login đã chọn | Dùng đồng hồ server/DB; không đặt ở `loadUserByUsername` |
| `loginSuccessCount` | Theo chính sách mỗi sự kiện login thành công | Tránh double count do handler + listener cùng ghi |
| `lastLoginIp`, `lastUserAgent` | Nếu cần audit/risk signals | IP qua trusted proxy; tối thiểu hóa PII và retention |
| `failureCount`, `lockedUntil` | **Sau thất bại**, theo policy lockout | Không gọi đây là dữ liệu của successful login |
| `passwordHash` và thuật toán hiện tại | Trong quá trình xác thực đúng, nếu `upgradeEncoding` true | Ghi bằng encoded value và CAS |
| `securityAuditEvent` | Thành công/thất bại theo event type | Có correlation ID, không chứa password/hash |
| `sessionId` / session registry | Sau login thành công/rotation | Spring Security + Session management, không tự set session ID từ client |
| `lastAuthenticatedFactor` | Sau xác minh factor thực tế | Không dựa trên header `mfa=true` do client gửi |

**Quy tắc:** dữ liệu hậu xác thực phải phản ánh sự kiện đã xảy ra thật, không dùng dữ liệu client tự khai hoặc việc tải user record để kết luận đăng nhập thành công.

### Sai nơi cập nhật

Không viết `lastLoginAt = now` trong `UserDetailsService.loadUserByUsername` vì method này có thể được gọi khi:

- user nhập **sai mật khẩu**;
- password encoder cần một bản dữ liệu user để xác minh;
- một service/admin action đọc user;
- cache miss/re-authentication hoặc hoạt động tra cứu khác.

Tương tự, không cập nhật login success trong `PasswordEncoder.matches`. Encoder chỉ phải xử lý password comparison/upgrade decision, không phụ thuộc DB audit.

## 10. AuthenticationSuccessHandler cho form login

Với Servlet form login, `AuthenticationSuccessHandler` là hook gần cuối flow sau xác thực thành công. Ví dụ cấu hình **chỉ dành cho browser form login**:

```java
// Fragment trong @Configuration, dùng Spring Security 6.x Servlet.
@Bean
AuthenticationSuccessHandler auditedSuccessHandler(
        LoginAuditService auditService) {

    var delegate = new SavedRequestAwareAuthenticationSuccessHandler();

    return (request, response, authentication) -> {
        auditService.recordSuccessfulLogin(
                authentication.getName(),
                java.time.Instant.now(),
                request.getRemoteAddr());
        delegate.onAuthenticationSuccess(request, response, authentication);
    };
}

// Khi xây SecurityFilterChain:
http.formLogin(form -> form
        .successHandler(auditedSuccessHandler(auditService)));
```

Imports cần thiết: `org.springframework.security.web.authentication.AuthenticationSuccessHandler`, `org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler` và `org.springframework.context.annotation.Bean`. `LoginAuditService` là **service do ứng dụng định nghĩa**, không phải API có sẵn của Spring Security.

Đoạn này **không độc lập**: cần session/security chain và service implementation. `getRemoteAddr()` có thể là IP của reverse proxy; chỉ dùng forwarded headers đã được edge chuẩn hóa/trust để tính client IP, và cân nhắc không lưu IP khi không cần.

Nếu service audit lỗi, bạn phải quyết định rõ:

- **Audit bắt buộc để hoàn tất login**: xử lý tính nhất quán/transaction và fail theo policy, tránh để session đã tạo mà UI báo thất bại không rõ trạng thái.
- **Audit best-effort**: dùng durable event/outbox, monitoring/retry giới hạn, không chặn event loop/request vì dịch vụ analytics lỗi. Không im lặng nuốt lỗi bảo mật cần cảnh báo.

Hook `AuthenticationSuccessHandler` của form login không nhất thiết chạy cho **HTTP Basic**, **JWT resource server** hoặc **custom AuthenticationManager.authenticate(...)** gọi từ service. Muốn đo nhiều cơ chế, phải xác định event và hook đúng nguồn.

## 11. AuthenticationSuccessEvent và InteractiveAuthenticationSuccessEvent

Spring Security có authentication events khi cấu hình publisher phù hợp. Ví dụ:

```java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher publisher) {
    return new DefaultAuthenticationEventPublisher(publisher);
}
```

Imports: `org.springframework.security.authentication.AuthenticationEventPublisher`, `org.springframework.security.authentication.DefaultAuthenticationEventPublisher` và `org.springframework.context.ApplicationEventPublisher`.

Sau đó có thể nghe:

```java
@Component
class LoginAuditListener {
    private final LoginAuditService audit;

    LoginAuditListener(LoginAuditService audit) {
        this.audit = audit;
    }

    @EventListener
    void onSuccess(AuthenticationSuccessEvent event) {
        Authentication auth = event.getAuthentication();
        audit.recordProviderSuccess(auth.getName());
    }
}
```

Imports: `org.springframework.stereotype.Component`, `org.springframework.context.event.EventListener`, `org.springframework.security.authentication.event.AuthenticationSuccessEvent`, `org.springframework.security.core.Authentication`.

**Cảnh báo về đếm trùng**:

- `AuthenticationSuccessEvent` do authentication infrastructure phát theo cấu hình; một số flow hoặc chương trình có thể authenticate nhiều lần.
- `InteractiveAuthenticationSuccessEvent` được filter tương tác phát ở giai đoạn khác; không phải tất cả cơ chế có event này.
- Gắn listener cả hai event và success handler rồi cùng tăng `loginCount` có thể nhân đôi/triple-count.
- Một event thành công của provider chưa chắc đồng nghĩa **browser session đã persist thành công**; phân biệt success của credential và success của phiên tương tác.
- `@EventListener` không phải bảo đảm message delivery exactly-once qua nhiều process. Với audit quan trọng, dùng durable event/outbox và idempotency key.

**Lưu ý:** nếu chỉ gọi trực tiếp `DaoAuthenticationProvider.authenticate(...)` trong unit test, không mặc định có `ProviderManager`, publisher hoặc form filter; do đó kiểm thử event/handler nên nằm ở tầng integration phù hợp.

## 12. Thiết kế kiểm thử update lastLoginAt và audit

Hai loại test quan trọng:

**A. Unit test thành phần cập nhật sau xác thực**

Mock `LoginAuditService` và gọi handler/listener với `Authentication` giả hợp lệ; assert service nhận đúng user/timestamp. Với handler, delegate redirect/cookie/session sẽ cần fake request/response từ Spring Mock và có thể dùng Mockito để xác minh gọi chính xác.

**B. Integration test login filter**

Dùng `MockMvc` với Spring Security filter chain thật, user store thật hoặc test DB:

```java
// Test fragment trong @SpringBootTest + @AutoConfigureMockMvc,
// cần inject MockMvc, repository, và cấu hình form login thực tế.
mvc.perform(post("/login")
            .param("username", "alice")
            .param("password", "correct-password")
            .with(csrf()))
        .andExpect(status().is3xxRedirection());

// Sau request, đọc DB qua JDBC (không phải mock):
assertEquals(1, repository.countSuccessfulLogins("alice"));
assertNotNull(repository.findLastSuccessfulLoginAt("alice"));
```

Imports: `org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post`, `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf`, `org.springframework.test.web.servlet.result.MockMvcResultMatchers.status`, `org.junit.jupiter.api.Assertions.*`. `repository` là fixture của app, không có sẵn trong Spring.

Test failure:

```java
mvc.perform(post("/login")
            .param("username", "alice")
            .param("password", "wrong")
            .with(csrf()))
        .andExpect(status().is3xxRedirection());

assertEquals(1, repository.countSuccessfulLogins("alice"));
// Số liệu vẫn giữ nguyên sau lần failure; failure counter có policy riêng.
```

Với form login mặc định, fail thường redirect `/login?error`; ở ứng dụng thay failure handler trả JSON 401 thì assertion phải tương ứng. Không dựa vào status 302 một mình: cả success và failure **đều có thể redirect**. Kiểm tra `Location`/session state và DB.

### Test không cập nhật sau user disabled

Gán `enabled=false`, gửi login bằng password đúng và assert:

- Authentication bị từ chối (thường qua failure handler).
- Password hash không đổi, kể cả nếu legacy.
- Không có `lastSuccessfulLoginAt` mới hoặc success event.
- Failure audit/lockout có thể thay đổi theo policy nhưng không phải update success data.

### Test không cập nhật sau password sai

So sánh **snapshot DB trước/sau**, chứ không chỉ `verifyNoInteractions` với mock. Một bug cập nhật `lastLoginAt` từ `loadUserByUsername` sẽ vượt qua unit test service nhưng bị integration test này phát hiện.

## 13. Giao dịch và tính nhất quán của nhiều cập nhật

Có thể có **hai nhóm side effect** ở hai thời điểm khác nhau:

```text
A. Trong DaoAuthenticationProvider:
    - password match
    - conditional rehash + persist
    - create successful Authentication

B. Sau khi Authentication thành công trong web flow:
    - session rotation / SecurityContext persistence
    - login audit, lastLoginAt, device tracking
    - redirect hoặc JSON response
```

Đừng mặc định mọi thao tác trên là **một transaction DB duy nhất**. `DaoAuthenticationProvider` là component xác thực đồng bộ; success handler/event listener và session store có thể có vòng đời, transaction và hệ thống lưu khác.

### Phân định lỗi

- **Password update thất bại:** không được âm thầm coi đã upgrade; tùy chính sách có thể làm login thất bại hoặc retry xác thực an toàn. Không bỏ qua CAS miss rồi ghi đè.
- **Login audit thất bại:** cần thiết kế riêng giữa yêu cầu audit bắt buộc và best-effort; không ghi một row “LOGIN_SUCCESS” khi credential thực ra không hợp lệ.
- **Session creation lỗi sau auth:** provider success khác browser login success; nếu client retry cần chống duplicate side effects.
- **Post-login event bị phát lặp:** mọi consumer phải có idempotency/correlation; đừng cộng login count nhiều lần cho một login event.
- **DB timeout nhưng server đã commit:** response có thể là lỗi mạng dù state đã đổi; dùng idempotent event key và xác minh lại dữ liệu sau retry.

### Audit monotonic timestamp

Nếu hai login ở hai node được xử lý chậm/nhanh khác nhau, một update naïve có thể khiến `lastSuccessfulLoginAt` quay ngược thời gian. Ví dụ PostgreSQL:

```sql
UPDATE app_users
   SET last_successful_login_at =
       GREATEST(
           COALESCE(last_successful_login_at, :occurred_at),
           :occurred_at
       )
 WHERE user_id = :account_id;
```

`:occurred_at` phải đến từ nguồn server/DB được tin cậy sau success, không phải browser tự gửi. Query là ví dụ PostgreSQL; các DB khác có thể có hàm tương đương khác. Với `loginCount`, dùng atomic increment tại DB và idempotency key nếu event delivery có thể lặp.

## 14. Concurrency và password-reset race

Nếu hai request login cùng password legacy gần như đồng thời:

```text
Request A                       Request B
load hash old                   load hash old
matches true                    matches true
upgradeEncoding true            upgradeEncoding true
encode(raw) -> hash-A           encode(raw) -> hash-B
CAS old -> hash-A: 1 row        CAS old -> hash-B: 0 row
one writer wins                 retry login from current hash,
                                or fail closed by policy
```

Nếu không có CAS/version, cả hai có thể ghi hash khác salt mà vẫn xác minh được cùng password — có thể trông “không sao” trong test, nhưng code đó cũng có thể **ghi đè password reset** đang diễn ra, gây lỗi bảo mật nghiêm trọng.

**Không dùng `synchronized` trên một JVM** để bảo đảm nhiều pod không ghi đè. Test với PostgreSQL/Redis thật ở nhiều node, nhiều transaction và lock contention. Nếu user đổi mật khẩu sau khi request login đã đọc hash cũ, bước commit cuối phải có kiểm tra chống stale state hoặc policy re-auth rõ.

Một điều kiện SQL an toàn điển hình:

```sql
UPDATE app_users
SET password_hash = :new_hash,
    credential_version = credential_version + 1
WHERE user_id = :user_id
  AND credential_version = :expected_version
  AND password_hash = :old_hash;
```

Kiểm tra update count = 1. Nếu 0, **không** ghi tiếp lần nữa bằng update vô điều kiện. Số lần rehash thành công có thể là 1 dù số lần gọi `encode` là 2; test nên đo **DB commits** thay vì chỉ đếm encoder invocations.

## 15. Java 17 thuần: kiểm tra nhánh login và rehash atomically

Chương trình sau chạy **không phụ thuộc Spring** và tạo password hash **PBKDF2WithHmacSHA256 có salt ngẫu nhiên** (không lưu password thô trong map). Nó mô phỏng:

- Wrong password: không upgrade và không cập nhật `successfulLogins`.
- Correct password + legacy hash: nâng cấp một lần.
- Correct password sau rehash: không nâng cấp thêm.
- 12 login đồng thời: 12 lần xác thực đúng được đếm, nhưng **chỉ 1 lần rehash ghi thành công**.

Tạo file **`PasswordUpgradeDemo.java`**:

```java
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.security.*;
import javax.crypto.*;
import javax.crypto.spec.*;

public class PasswordUpgradeDemo {
    // Số vòng THẤP nhằm test nhanh. Tuyệt đối không copy vào production.
    static final int LEGACY_ROUNDS = 1600;
    static final int CURRENT_ROUNDS = 3600;
    static final SecureRandom RANDOM = new SecureRandom();

    record Account(String username, String passwordHash,
                   int successfulLogins, Instant lastLoginAt) {}

    static String hash(String raw, int rounds) {
        byte[] salt = new byte[16];
        RANDOM.nextBytes(salt);
        return "pbkdf2$" + rounds + "$" + encode64(salt) + "$"
                + encode64(derive(raw, salt, rounds));
    }

    static String encode64(byte[] data) {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(data);
    }

    static byte[] derive(String raw, byte[] salt, int rounds) {
        char[] chars = raw.toCharArray();
        PBEKeySpec spec = new PBEKeySpec(chars, salt, rounds, 256);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException(e);
        } finally {
            spec.clearPassword();
            Arrays.fill(chars, '\0');
        }
    }

    static String[] parts(String encoded) {
        String[] p = encoded.split("\\$", -1);
        if (p.length != 4 || !"pbkdf2".equals(p[0])) {
            throw new IllegalArgumentException(
                    "Unsupported hash format");
        }
        return p;
    }

    static boolean matches(String raw, String encoded) {
        String[] p = parts(encoded);
        int rounds = Integer.parseInt(p[1]);
        byte[] salt = Base64.getUrlDecoder().decode(p[2]);
        byte[] expected = Base64.getUrlDecoder().decode(p[3]);
        return MessageDigest.isEqual(
                expected, derive(raw, salt, rounds));
    }

    static boolean needsUpgrade(String encoded) {
        return Integer.parseInt(parts(encoded)[1]) < CURRENT_ROUNDS;
    }

    static final class LoginStore {
        final ConcurrentHashMap<String, Account> accounts =
                new ConcurrentHashMap<>();
        final AtomicInteger upgradeWrites = new AtomicInteger();
        final Clock clock;

        LoginStore(Clock clock) { this.clock = clock; }

        void createLegacy(String user, String raw) {
            accounts.put(user, new Account(
                    user, hash(raw, LEGACY_ROUNDS), 0, null));
        }

        boolean authenticate(String user, String raw) {
            if (user == null || raw == null) return false;
            AtomicBoolean accepted = new AtomicBoolean(false);

            accounts.computeIfPresent(user, (id, current) -> {
                // Chỉ mô phỏng trong một JVM. Production không chạy
                // hàm hash chậm bên trong lock của ConcurrentHashMap.
                if (!matches(raw, current.passwordHash())) {
                    return current;
                }
                String newHash = current.passwordHash();
                if (needsUpgrade(newHash)) {
                    newHash = hash(raw, CURRENT_ROUNDS);
                    upgradeWrites.incrementAndGet();
                }
                accepted.set(true);
                return new Account(
                        current.username(), newHash,
                        current.successfulLogins() + 1,
                        clock.instant());
            });
            return accepted.get();
        }

        Account get(String user) { return accounts.get(user); }
    }

    public static void main(String[] args) throws Exception {
        Clock fixed = Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC);
        LoginStore store = new LoginStore(fixed);
        store.createLegacy("alice", "right-password");

        System.out.println("wrongAccepted="
                + store.authenticate("alice", "wrong"));
        System.out.println("failureUpgradeWrites="
                + store.upgradeWrites.get());
        System.out.println("failureLoginCount="
                + store.get("alice").successfulLogins());
        System.out.println("legacyCorrectAccepted="
                + store.authenticate("alice", "right-password"));
        System.out.println("hashNowCurrent="
                + !needsUpgrade(store.get("alice").passwordHash()));
        System.out.println("upgradesAfterFirst="
                + store.upgradeWrites.get());
        System.out.println("loginsAfterFirst="
                + store.get("alice").successfulLogins());
        System.out.println("secondAccepted="
                + store.authenticate("alice", "right-password"));
        System.out.println("upgradesAfterSecond="
                + store.upgradeWrites.get());
        System.out.println("loginsAfterSecond="
                + store.get("alice").successfulLogins());
        System.out.println("wrongAfterUpgradeAccepted="
                + store.authenticate("alice", "wrong"));

        LoginStore race = new LoginStore(fixed);
        race.createLegacy("bob", "correct");
        ExecutorService pool = Executors.newFixedThreadPool(12);
        try {
            CountDownLatch gate = new CountDownLatch(1);
            List<Future<Boolean>> results = new ArrayList<>();
            for (int i = 0; i < 12; i++) {
                results.add(pool.submit(() -> {
                    gate.await();
                    return race.authenticate("bob", "correct");
                }));
            }
            gate.countDown();
            int count = 0;
            for (Future<Boolean> result : results) {
                if (result.get()) count++;
            }
            System.out.println("concurrentAccepted=" + count);
            System.out.println("concurrentUpgradeWrites="
                    + race.upgradeWrites.get());
            System.out.println("concurrentLoginCount="
                    + race.get("bob").successfulLogins());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac PasswordUpgradeDemo.java
java PasswordUpgradeDemo
```

Stdout đã kiểm chứng bằng Java 17:

```text
wrongAccepted=false
failureUpgradeWrites=0
failureLoginCount=0
legacyCorrectAccepted=true
hashNowCurrent=true
upgradesAfterFirst=1
loginsAfterFirst=1
secondAccepted=true
upgradesAfterSecond=1
loginsAfterSecond=2
wrongAfterUpgradeAccepted=false
concurrentAccepted=12
concurrentUpgradeWrites=1
concurrentLoginCount=12
```

**Vì sao 12 request thành công nhưng chỉ 1 lần nâng cấp?** `ConcurrentHashMap.computeIfPresent` tuần tự hóa read/verify/change đối với cùng một key trong process; request đầu đổi cost 1600 thành 3600, các request tiếp theo vẫn xác minh password đúng nhưng thấy hash hiện hành nên không rehash. Đây **không** phải bảo đảm “chỉ một login được phép thành công”; đó là bài toán quản lý session/concurrency khác.

**Giới hạn demo:**

- Tham số PBKDF2 1600/3600 vòng **không phù hợp production**; chỉ giúp test nhanh. Dùng encoder/parameters do chính sách hiện hành và benchmark quyết định.
- `computeIfPresent` chứa phép hash tốn CPU dưới lock — chỉ để dễ quan sát deterministic trong Java SE. Production nên xác minh ngoài lock và dùng CAS/version/transaction bền vững, đồng thời bảo vệ chống stale reset.
- Đây không phải `PasswordEncoder` của Spring, không có `DelegatingPasswordEncoder` id format và không kết nối database. Test Spring provider phải dùng mục 6–8.
- Dữ liệu `successfulLogins` phản ánh lời gọi method mô phỏng; không phải HTTP session thực hoặc event delivery với idempotency.
- Các hàm chỉ hỗ trợ hash đúng format; production phải xác minh input malformed và giới hạn tham số để tránh DoS. Không cho client gửi `rounds` tùy ý.
- `String` raw password còn trong heap đến khi GC; Java không có bảo đảm xóa hoàn toàn tất cả bản sao. Không ghi password hoặc encoded hash vào log/stack trace.
- Kết quả `concurrentAccepted=12` đúng vì cả 12 lần dùng **cùng mật khẩu hợp lệ**, trong khi `concurrentUpgradeWrites=1` thể hiện chỉ một lần rehash.

## 16. Những lỗi test/implementation thường gặp

**1. Chỉ assert HTTP 200/302.** Login có thể redirect cả khi fail, và status không chứng minh password hash đổi. Kiểm tra failure URL, DB và account state.

**2. Dùng @WithMockUser để test upgrade.** Nó bypass provider; test vẫn xanh dù `UserDetailsPasswordService` không được nối vào thực tế.

**3. Mock PasswordEncoder.matches luôn true.** Test sai password cũng thành công, không kiểm tra ranh giới. Tách test true/false.

**4. Test encoder bằng việc so sánh output hash cố định.** BCrypt/PBKDF2 có salt, hash khác nhau mỗi lần. Dùng `matches` và `upgradeEncoding`, chỉ assert tính chất.

**5. Khai báo bean PasswordEncoder mới rồi tưởng hash trong DB tự đổi.** Phải xác thực bằng credential hợp lệ và có updater/wiring; hash không tự migrate chỉ từ config.

**6. Nhầm newPassword của UserDetailsPasswordService là raw.** Lưu plaintext hoặc double-hash đều gây lỗi. Test assertion encoded được lưu và matches raw.

**7. Gọi updatePassword ngay trong loadUserByUsername.** User sai mật khẩu vẫn gây rehash hoặc success metadata thay đổi; sai thứ tự bảo mật.

**8. Assert principal password là bản hash mới nhất.** Provider 6.5 có thể giữ principal từ trước rehash; kiểm tra repository và API contract.

**9. Không kiểm tra compromised password/account flags.** Đường auth không thành công vẫn được ghi hash/audit. Test disabled/locked/expired/compromised.

**10. Updater trả null.** Provider có thể không tạo Authentication thành công; service phải trả UserDetails hợp lệ, không giả vờ return void.

**11. UPDATE chỉ theo username.** Concurrent password reset có thể bị rehash cũ ghi đè. Dùng CAS/version và test hai transaction.

**12. CAS miss vẫn coi thành công mà không kiểm tra credential mới.** Trường hợp password đã đổi trở nên nguy hiểm; fail closed hoặc reverify toàn bộ.

**13. Bắt SQLException rồi bỏ qua âm thầm.** Test báo login success dù DB không có rehash; xác định policy lỗi và log nội bộ.

**14. Đếm login bằng AuthenticationSuccessEvent + InteractiveAuthenticationSuccessEvent + success handler.** Một login có thể bị đếm nhiều lần. Chọn nguồn sự kiện, correlation và idempotency.

**15. Ghi lastLoginAt khi load user.** User chỉ tra cứu hoặc nhập password sai cũng bị ghi “thành công”.

**16. Ghi IP từ X-Forwarded-For không đáng tin.** Client có thể giả header; chỉ tin proxy boundary đã normalize và áp dụng retention.

**17. Test in-memory DB nhưng production là PostgreSQL.** Isolation, locking, transaction và SQL dialect khác nhau; test repo trên engine thật.

**18. Test trong @Transactional tự rollback mọi thứ.** Test không chứng minh commit/outbox, dùng test riêng với transaction độc lập.

**19. Cache UserDetails cũ vô hạn.** Hash đã đổi nhưng cache vẫn chứa dữ liệu cũ; credential checks và invalidation không theo policy.

**20. Log password hoặc hash để debug.** Hash cũng là dữ liệu xác thực nhạy cảm và có thể phục vụ offline attack nếu DB/log lộ. Dùng security metrics không chứa secret.

**21. Hash cost quá cao trong login path.** Nâng cấp hash có thể tăng CPU/độ trễ dẫn đến DoS; giới hạn login attempts, capacity planning, timeout và rollout hợp lý.

**22. Không kiểm thử hậu quả rollback hoặc response lost.** API báo lỗi nhưng DB đã commit; retry có thể lặp audit. Dùng idempotency key/durable outbox.

## 17. Kịch bản end-to-end được khuyến nghị

| Scenario | Mức kiểm thử | Điều phải quan sát |
| --- | --- | --- |
| Legacy hash, password đúng | Unit + DB + HTTP | Auth success; new encoded hash; success audit đúng |
| Current hash, password đúng | Unit + DB | Auth success; hash **giữ nguyên**; audit tăng đúng |
| Password sai | Unit + DB + HTTP | Auth fail; hash và lastLoginAt giữ nguyên |
| Username không tồn tại | Unit + HTTP | Không lộ user existence, không upgrade |
| Account disabled hoặc locked | Unit + HTTP | Không auth; không success side effect |
| Credential expired/compromised | Unit + HTTP | Theo policy, không update “success” |
| No UserDetailsPasswordService | Unit + wiring test | Không gọi auto-rehash |
| Service update trả null | Unit | Không silently mark auth success |
| JDBC exception | DB integration | Rollback/fail policy rõ, không false success |
| Two simultaneous upgrades | DB concurrency | Chỉ một CAS write; không data corruption |
| Password reset xen giữa login | DB concurrency | Reset không bị ghi đè; stale credential không được tin |
| Session/form login | MockMvc + DB | Success handler và session persistence đúng |
| HTTP Basic/resource server | Integration riêng | Không kỳ vọng form success handler |
| Event publisher bất hoạt | Unit/integration | Không ngầm dựa vào event chưa cấu hình |
| Event được gửi lặp | Consumer test | Idempotent outcome |
| Multiple instances | E2E + DB thật | Cùng trạng thái và audit theo policy |
| Logs/metrics | Security audit | Không lộ raw password, encoded hash hay session token |

### Thực hành test data

- Dùng user/password **giả** với dữ liệu test, không lấy hash hoặc credential production làm fixture.
- Không lưu raw password trong snapshot test/log. Sử dụng `@Test` resource fixtures tạm được bảo vệ hoặc secret test riêng.
- Với BCrypt, chọn cost nhỏ để unit test nhanh nhưng **không truyền config test sang production**.
- Cố định `Clock` cho timestamp test; không dùng `Thread.sleep` để đo login mới hay time boundary.
- Giới hạn fake/mocks cho test nhánh; một ít integration tests thật với database/auth provider phải bao phủ ràng buộc an toàn.

## 18. Checklist hoàn thành bài

1. Có thể giải thích vì sao nâng cấp password hash chỉ khả thi khi login với raw password hợp lệ?
2. Biết thứ tự `matches → upgradeEncoding → encode → updatePassword` và điều kiện updater tồn tại?
3. Đã test hash legacy và hash hiện hành bằng encoder thật, không dựa vào hash chuỗi cố định?
4. Đã test wrong password, user disabled/locked, credential expired/compromised không ghi rehash?
5. Có kiểm tra encoded value truyền vào `UserDetailsPasswordService` đúng một lần và service trả UserDetails hợp lệ?
6. Đã tách unit test provider với integration test DB/HTTP và biết `@WithMockUser` bypass provider?
7. Đã kiểm tra đọc DB sau commit và lần login thứ hai không rehash vô hạn?
8. Đã bảo vệ concurrent password reset và double-upgrade bằng CAS/version/transaction?
9. Có policy xử lý CAS miss và DB failure an toàn, không “last write wins” trên password?
10. Các cập nhật `lastSuccessfulLoginAt`/audit chỉ chạy sau authenticated success đúng loại sự kiện?
11. Đã tránh đếm trùng giữa success handler, `AuthenticationSuccessEvent` và `InteractiveAuthenticationSuccessEvent`?
12. Đã phân biệt rehash (không đổi password) với đổi password của user (có thể revoke sessions)?
13. Đã test ảnh hưởng của `UserCache`, principal snapshot và session trên password upgrade?
14. Có test nhiều node, rollback/commit, lost response và idempotency cho audit/outbox nếu cần?
15. Không log raw password/hash và không dùng test-only parameters làm production defaults?

### Nguồn tài liệu chính thức

- Spring Security 6.5 — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security 6.5 — Password Storage / DelegatingPasswordEncoder: https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html
- Spring Security 6.5 — PasswordEncoder API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/PasswordEncoder.html
- Spring Security 6.5 — UserDetailsPasswordService API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html
- Spring Security 6.5 — Authentication Events: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html
- Spring Security 6.5 — Form Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Security 6.5.11 — DaoAuthenticationProvider source để đối chiếu nhánh upgrade: https://github.com/spring-projects/spring-security/blob/6.5.11/core/src/main/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.java
- Spring Security 6.5.11 — AbstractUserDetailsAuthenticationProvider source: https://github.com/spring-projects/spring-security/blob/6.5.11/core/src/main/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.java
- OWASP — Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html

**Kết luận:** Kiểm thử “nâng cấp mật khẩu và cập nhật dữ liệu sau xác thực” không phải chỉ test credential đúng. Cần chứng minh **hash mới được ghi bền vững đúng điều kiện**, **không có write ở các nhánh thất bại**, **không ghi đè password reset khi cạnh tranh**, và **lastLogin/audit chỉ phản ánh sự kiện authentication thành công**. Kết hợp test thực vào `DaoAuthenticationProvider`, encoder thật, database transaction thật và login filter để đóng đủ các ranh giới.
