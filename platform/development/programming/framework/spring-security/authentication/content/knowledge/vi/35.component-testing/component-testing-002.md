# Kiểm thử UserDetailsService với tài khoản tồn tại, thiếu và không hợp lệ trong Spring Security

## 1. Mục tiêu bài học và ranh giới của kiểm thử thành phần

Trong Spring Security, `UserDetailsService` là thành phần **tải dữ liệu tài khoản** cho luồng xác thực dùng username/password. Giao diện này chỉ có phương thức cốt lõi:

```java
UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
```

Nhiệm vụ của nó là tra cứu định danh, đưa về `UserDetails` đầy đủ và không để dữ liệu thuộc tài khoản khác lọt vào kết quả. Một `UserDetails` thường chứa tên đăng nhập, password hash hoặc credential metadata cần thiết, authorities (quyền), và trạng thái enabled/locked/expired.

**Phạm vi phải phân biệt ngay:**

- **Unit/component test của UserDetailsService:** tài khoản tồn tại được trả về chính xác; tài khoản không có gây `UsernameNotFoundException`; tên trống/sai chuẩn hóa; tài khoản disabled/locked/expired có **các cờ trạng thái đúng**; password lưu dưới dạng hash; authorities đúng, không bị lẫn sang user khác.
- **Test xác thực bằng DaoAuthenticationProvider:** credential/password được kiểm bằng `PasswordEncoder.matches(...)`; provider quyết định user locked/disabled/expired có thể đăng nhập hay không; kết quả là `Authentication` thành công hoặc `AuthenticationException` thích hợp.
- **Test HTTP với SecurityFilterChain:** `POST /login`/HTTP Basic hoạt động qua filter, CSRF, redirect/challenge, lưu SecurityContext/session; endpoint cần quyền có bị chặn hay không.

**Không được gán việc kiểm mật khẩu cho UserDetailsService**. Nó chỉ tải bản ghi, không nên kiểm raw password với mật khẩu trong request. `DaoAuthenticationProvider` (kết hợp `PasswordEncoder`) xử lý đối chiếu mật khẩu. Việc `service.loadUserByUsername("alice")` trả về user không chứng minh Alice có thể đăng nhập bằng password sai.

Bài này dùng **Java 17+, Spring Boot 3.x và Spring Security 6.x trên Servlet/Spring MVC**. Đối với Spring Security 7/Boot 4, ý tưởng kiểm thử không đổi nhưng package/API test auto-configuration và constructor có thể khác; kiểm tra bản dependency của project trước khi copy.

### Kết quả mong đợi sau bài

1. Thiết kế test cho **existing, missing, invalid** account có thể lặp lại trong CI.
2. Hiểu đúng contract: khi thiếu user, không trả `null` hoặc fake user; khi tồn tại, trả UserDetails thuộc đúng identity.
3. Kiểm riêng các cờ `enabled`, `accountNonLocked`, `accountNonExpired`, `credentialsNonExpired` và authorities.
4. Dùng Mockito/JUnit 5 cho component test, tránh DB và HTTP không cần thiết; dùng `DaoAuthenticationProvider` trong tầng tích hợp để kiểm credential thật.
5. Có test chống enumeration và nguy cơ lẫn account/tenant, duplicate username, password hash/role mapping lỗi.
6. Biết test nhận diện “fail vì CSRF hoặc thiếu role” khác “fail vì UserDetailsService”.

## 2. Đường đi của một request đăng nhập và trách nhiệm từng lớp

```text
Browser POST /login
  username=alice, password=secret, CSRF hợp lệ
          |
          v
UsernamePasswordAuthenticationFilter
          | tạo UsernamePasswordAuthenticationToken
          v
AuthenticationManager / ProviderManager
          |
          v
DaoAuthenticationProvider
          |
          | -- 1. loadUserByUsername("alice") ------------------+
          v                                                    |
UserDetailsService                                            |
          |                                                    |
          | -- 2. AccountRepository / LDAP / JDBC store        |
          v                                                    |
UserDetails(username, encodedPassword, authorities, flags) <---+
          |
          v
DaoAuthenticationProvider
          | 3. Kiểm account locked / disabled / expired
          | 4. PasswordEncoder.matches(raw, encoded)
          | 5. Kiểm credentialsNonExpired
          v
Authentication thành công hoặc AuthenticationException
          |
          v
SecurityContext + authorization/session (nếu thành công)
```

**UserDetailsService không tự tạo Authentication, không gắn SecurityContext và không ủy quyền vào route.** Vì vậy unit test chỉ dùng service là chưa đủ để chứng minh HTTP login flow. Ngược lại, test dùng `@WithMockUser` có thể cho quyền thành công **mà không gọi UserDetailsService**; nó phù hợp kiểm authorization, không phải kiểm repository lookup.

Theo Javadoc, `loadUserByUsername` **trả về bản ghi đầy đủ, không bao giờ trả `null`**. Nếu không tìm thấy user hoặc không thể nạp một user có authorities hợp lệ theo contract, nó ném `UsernameNotFoundException`. Việc tìm kiếm phân biệt hoa/thường hay không do service/repository quyết định; bạn phải đặt policy chuẩn hóa rồi kiểm thử, không suy đoán framework tự chuẩn hóa giống nhau cho mọi datasource.

## 3. Những trạng thái cần kiểm thử: tồn tại, thiếu, không hợp lệ

| ID | Input/fixture | Mong đợi tại UserDetailsService | Mong đợi tại Provider/HTTP |
| --- | --- | --- | --- |
| U01 | Alice tồn tại, enabled, có ROLE_USER | UserDetails đúng Alice; password đã encode; cờ hợp lệ | Password đúng → authenticated |
| U02 | Alice tồn tại, password request sai | UserDetails **vẫn được nạp** | `BadCredentialsException` / login fail |
| U03 | Username không tồn tại | `UsernameNotFoundException` | Không authenticated; thường được che dưới `BadCredentialsException` |
| U04 | Username rỗng hoặc whitespace | Từ chối phù hợp policy, không query DB vô ích | Generic login failure |
| U05 | Username `null` trong test service trực tiếp | Từ chối (chọn exception nhất quán) | HTTP filter có thể chuẩn hóa khác |
| U06 | `" Alice "`, DB canonical `alice` | Tra cứu bằng key chuẩn hóa nếu policy cho phép | Login/authority đúng canonical account |
| U07 | `ALICE` vs `alice` | Theo policy case-insensitive/case-sensitive đã định | Không rơi nhầm account |
| U08 | Account `enabled=false` | `isEnabled=false` | Provider từ chối bằng `DisabledException` |
| U09 | Account `locked=true` | `isAccountNonLocked=false` | Provider từ chối bằng `LockedException` |
| U10 | Account expired | `isAccountNonExpired=false` | Provider từ chối bằng `AccountExpiredException` |
| U11 | Password credential expired | `isCredentialsNonExpired=false` | Provider từ chối bằng `CredentialsExpiredException` |
| U12 | Account enabled nhưng không có role hợp lệ | Từ chối hoặc xử lý theo contract đã thiết kế, không cấp role mặc định nguy hiểm | Không vô tình có `ROLE_ADMIN` |
| U13 | Account có roles USER,EDITOR | `ROLE_USER` và `ROLE_EDITOR`, không nhầm với account khác | Route kiểm `hasRole`/`hasAuthority` đúng |
| U14 | Username trùng ở hai tenant | Lookup phải scoped theo stable tenant + normalized key | Không trả nhầm tenant |
| U15 | Repository lỗi/timeout | Lỗi hạ tầng phân biệt về nội bộ, không giả là user missing hoặc cho login | Fail closed; ghi audit không lộ bí mật |
| U16 | Thay đổi password/account status trong DB | Service đọc bản ghi hiện hành hoặc cache có chính sách invalidation | Auth mới không dùng quyền/trạng thái cũ vô hạn |
| U17 | UserDetails có username khác requested | Chỉ chấp nhận nếu canonicalization/mapping cho phép | Principal gắn đúng stable identity |
| U18 | Stored password raw/format không hỗ trợ | Mapping phải giữ hash theo schema; lỗi data migration được phát hiện | Provider không được bỏ qua password check |
| U19 | Role lấy từ request/header chưa tin | Service không dùng làm nguồn authority | Không privilege escalation |
| U20 | Nhiều request đồng thời load hai users | Không dùng mutable global “currentUser” | Không bao giờ trả chi tiết của người khác |

**Chú ý về “không hợp lệ”:** đây không phải một trạng thái duy nhất. *Missing account* ≠ *disabled account* ≠ *locked account* ≠ *credential expired* ≠ *wrong password* ≠ *database failure*. Cách xử lý ở **service/provider/internal metrics** có thể khác nhau, nhưng response login bên ngoài nên tránh tiết lộ chi tiết nào giúp liệt kê tài khoản.

## 4. Thiết lập môi trường test (Spring Boot 3.x, Java 17+)

Trong dự án Spring Boot 3.x Gradle Groovy đã có Spring Boot plugin và Java toolchain, cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`spring-boot-starter-test` thường đưa JUnit Jupiter/Mockito/AssertJ vào classpath test, còn `spring-security-test` hỗ trợ `MockMvc`, `csrf()`, `formLogin()`, `httpBasic()`, `@WithMockUser`. Không cần khởi động web server để **unit test** một UserDetailsService với fake/mock repository.

Bố trí file minh họa:

```text
src/main/java/com/example/security/
  AccountRecord.java
  AccountRepository.java
  DatabaseUserDetailsService.java

src/test/java/com/example/security/
  DatabaseUserDetailsServiceTest.java
  DaoAuthenticationProviderTest.java

src/main/java/com/example/security/
  SecurityConfig.java              # chỉ cho phần integration/HTTP
```

Bản mẫu dưới đây cố ý dùng interface repository nhỏ, **không tự cài Spring Data JPA**. Bằng cách mock một interface thật đơn giản, ta tách kiểm thử mapping/trạng thái khỏi chi tiết SQL, transaction và hạ tầng database. Khi triển khai sản phẩm, thay `AccountRepository` bằng adapter gọi JPA/JDBC/LDAP và có các test tích hợp kho dữ liệu riêng.

### Nguyên tắc fixture

- Test account `alice` và `bob` có password **khác nhau**, role khác nhau để phát hiện lẫn user.
- Có account enabled, disabled, locked, accountExpired, credentialsExpired.
- Password được **encode bằng cùng PasswordEncoder** mà provider sẽ dùng trong test; không so raw password với giá trị hash bằng `equals`.
- Không dùng user/password/email production; các chuỗi trong bài chỉ là test fixture.
- Với unit test component, repository được mock để biết rõ query key nào đã dùng, kết quả trả về là gì và có gọi repository khi input invalid không.

## 5. Model và repository contract cho ví dụ

### 5.1. AccountRecord.java

Trong `src/main/java/com/example/security/AccountRecord.java`:

```java
package com.example.security;

import java.util.Set;

public record AccountRecord(
        String usernameKey,
        String passwordHash,
        boolean enabled,
        boolean locked,
        boolean accountExpired,
        boolean credentialsExpired,
        Set<String> roles) {
}
```

`usernameKey` là key đã chuẩn hóa và duy nhất trong namespace/tenant của bài demo; một hệ thống thật nên có immutable account ID, tenant ID và trạng thái bảo mật riêng. Các boolean trên là snapshot lấy từ datastore, **không phải kết quả của việc so mật khẩu**.

### 5.2. AccountRepository.java

Trong `src/main/java/com/example/security/AccountRepository.java`:

```java
package com.example.security;

import java.util.Optional;

public interface AccountRepository {
    Optional<AccountRecord> findByUsernameKey(String usernameKey);
}
```

Đây không phải Spring Data interface; **cần adapter implement thật** khi kết nối DB. Dùng `Optional.empty()` thể hiện không tìm thấy, không dùng `null` cho kết quả repository theo contract này. Test mock sẽ cung cấp phản hồi mà không kết nối DB.

### 5.3. UserDetailsService ánh xạ từ record

Trong `src/main/java/com/example/security/DatabaseUserDetailsService.java`:

```java
package com.example.security;

import java.util.Locale;
import java.util.Objects;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;

public final class DatabaseUserDetailsService
        implements UserDetailsService {

    private final AccountRepository repository;

    public DatabaseUserDetailsService(AccountRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    @Override
    public UserDetails loadUserByUsername(String rawUsername)
            throws UsernameNotFoundException {

        if (rawUsername == null || rawUsername.isBlank()) {
            throw new UsernameNotFoundException("Account cannot be loaded");
        }

        String key = rawUsername.strip().toLowerCase(Locale.ROOT);
        AccountRecord account = repository.findByUsernameKey(key)
                .orElseThrow(() -> new UsernameNotFoundException(
                        "Account cannot be loaded"));

        // Roles trong DB là các giá trị được quản trị như USER/EDITOR,
        // không lấy role trực tiếp từ request, không cấp quyền mặc định.
        if (account.roles() == null || account.roles().isEmpty()) {
            throw new UsernameNotFoundException("Account cannot be loaded");
        }

        String[] authorities = account.roles().stream()
                .map(role -> "ROLE_" + role)
                .sorted()
                .toArray(String[]::new);

        return User.withUsername(account.usernameKey())
                .password(account.passwordHash())
                .authorities(authorities)
                .disabled(!account.enabled())
                .accountLocked(account.locked())
                .accountExpired(account.accountExpired())
                .credentialsExpired(account.credentialsExpired())
                .build();
    }
}
```

**Đọc kỹ mapping 4 flags:**

| DB field | UserDetails field | Ý nghĩa |
| --- | --- | --- |
| `enabled=true` | `isEnabled() == true` | Account được phép dùng để xác thực |
| `locked=true` | `isAccountNonLocked() == false` | Đảo dấu! Account đang bị khóa |
| `accountExpired=true` | `isAccountNonExpired() == false` | Account đã hết hạn |
| `credentialsExpired=true` | `isCredentialsNonExpired() == false` | Mật khẩu/credential đã hết hạn |

Phương thức `.disabled(boolean)` nhận **có bị vô hiệu** hay không, còn `isEnabled()` trả **còn được phép**; tương tự `.accountLocked(true)` khiến `isAccountNonLocked()=false`. Đây là chỗ rất dễ đảo nhầm khi viết mapping từ DB.

**Chính sách normalize của ví dụ:** `strip()` và `toLowerCase(Locale.ROOT)`; nó phù hợp khi database username được lưu canonical không phân biệt case. Nếu hệ thống có username phân biệt hoa/thường, email quốc tế, Unicode normalization, tenant-scoped login hoặc username nhiều chiều, bạn **phải thay policy** và viết test tương ứng. Không tự gộp hai accounts khác nhau chỉ vì lower-case.

**Contract roles:** demo không chấp nhận tập role rỗng để tránh tạo UserDetails không đủ thông tin. Với thiết kế cho phép authenticated user không có quyền, cần quyết định rõ cách cấp quyền `authenticated()` mà vẫn tuân thủ contract/service/provider phù hợp; **không thêm `ROLE_USER` tự động để test pass**. Vai trò được quản trị từ nguồn dữ liệu server tin cậy, không từ `username`/HTTP header của caller.

**Bảo mật mật khẩu:** `getPassword()` của `UserDetails` là hash (hoặc credential representation do encoder hỗ trợ); service không làm `password.equals(raw)`. `User.withUsername(...).password(...)` trong ví dụ không tự mã hóa chuỗi. Nếu `AccountRecord.passwordHash` là raw password thì đó là lỗi dữ liệu, không được “sửa” bằng việc so password plain text trong UserDetailsService.

## 6. JUnit 5 + Mockito: kiểm thử Service với tài khoản tồn tại và thiếu

File `src/test/java/com/example/security/DatabaseUserDetailsServiceTest.java`:

```java
package com.example.security;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

class DatabaseUserDetailsServiceTest {

    private AccountRepository repository;
    private DatabaseUserDetailsService service;
    private PasswordEncoder encoder;

    @BeforeEach
    void setUp() {
        repository = mock(AccountRepository.class);
        service = new DatabaseUserDetailsService(repository);
        // Cost 4 để test chạy nhanh; production dùng cost phù hợp.
        encoder = new BCryptPasswordEncoder(4);
    }

    private AccountRecord account(String username) {
        return new AccountRecord(
                username,
                encoder.encode("correct-pass"),
                true, false, false, false,
                Set.of("USER", "EDITOR"));
    }

    @Test
    void existingAccountReturnsCanonicalIdentityAndHash() {
        when(repository.findByUsernameKey("alice"))
                .thenReturn(Optional.of(account("alice")));

        UserDetails result = service.loadUserByUsername(" Alice ");

        assertEquals("alice", result.getUsername());
        assertTrue(result.isEnabled());
        assertTrue(result.isAccountNonLocked());
        assertTrue(result.isAccountNonExpired());
        assertTrue(result.isCredentialsNonExpired());
        assertTrue(encoder.matches("correct-pass", result.getPassword()));
        assertNotEquals("correct-pass", result.getPassword());

        assertTrue(result.getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("ROLE_USER")));
        assertTrue(result.getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("ROLE_EDITOR")));
        assertEquals(2, result.getAuthorities().size());

        verify(repository).findByUsernameKey("alice");
        verifyNoMoreInteractions(repository);
    }

    @Test
    void missingAccountThrowsInsteadOfReturningNull() {
        when(repository.findByUsernameKey("ghost"))
                .thenReturn(Optional.empty());

        assertThrows(UsernameNotFoundException.class,
                () -> service.loadUserByUsername("ghost"));

        verify(repository).findByUsernameKey("ghost");
        verifyNoMoreInteractions(repository);
    }

    @Test
    void nullOrBlankUsernameIsRejectedWithoutDatabaseCall() {
        assertThrows(UsernameNotFoundException.class,
                () -> service.loadUserByUsername(null));
        assertThrows(UsernameNotFoundException.class,
                () -> service.loadUserByUsername(""));
        assertThrows(UsernameNotFoundException.class,
                () -> service.loadUserByUsername("   "));

        verifyNoInteractions(repository);
    }

    @Test
    void uppercaseLookupUsesConfiguredCanonicalization() {
        when(repository.findByUsernameKey("alice"))
                .thenReturn(Optional.of(account("alice")));

        UserDetails result = service.loadUserByUsername("ALICE");

        assertEquals("alice", result.getUsername());
        verify(repository).findByUsernameKey("alice");
    }

    @Test
    void unknownUserDoesNotReturnAnotherUsersData() {
        when(repository.findByUsernameKey("bob"))
                .thenReturn(Optional.empty());
        when(repository.findByUsernameKey("alice"))
                .thenReturn(Optional.of(account("alice")));

        assertThrows(UsernameNotFoundException.class,
                () -> service.loadUserByUsername("bob"));
        assertEquals("alice",
                service.loadUserByUsername("alice").getUsername());

        verify(repository).findByUsernameKey("bob");
        verify(repository).findByUsernameKey("alice");
    }

    @Test
    void noRolesDoesNotGainAnyDefaultAuthority() {
        AccountRecord noRoles = new AccountRecord(
                "alice", encoder.encode("correct-pass"),
                true, false, false, false, Set.of());
        when(repository.findByUsernameKey("alice"))
                .thenReturn(Optional.of(noRoles));

        assertThrows(UsernameNotFoundException.class,
                () -> service.loadUserByUsername("alice"));
    }
}
```

### Vì sao unit test này “đúng tầng”?

- Không có `@SpringBootTest`/HTTP/DB: test nhanh và cô lập chức năng ánh xạ `AccountRecord → UserDetails`.
- `verify(repository).findByUsernameKey("alice")` chứng minh normalization đúng, không có query bằng chuỗi sai.
- `assertThrows(UsernameNotFoundException.class, ...)` khác xa việc trả `null` hoặc fake account; caller biết không tìm được user theo contract.
- Kiểm `encoder.matches(...)` chỉ xác nhận hash trong fixture được giữ nguyên và tương thích encoder; nó **không** chứng minh service tự kiểm credential. Password check thực nằm ở provider test mục 8.
- `verifyNoInteractions(repository)` giúp phát hiện service vô tình query DB với null/blank, có thể mở rộng thành injection/đọc dữ liệu sai.
- Kiểm `ROLE_USER`/`ROLE_EDITOR` đúng tên không tự tạo quyền chưa có trong record.

Chạy:

```bash
./gradlew test --tests com.example.security.DatabaseUserDetailsServiceTest
```

Mã test ở mục 6 chạy khi ba file production và dependencies mục 4 tồn tại. Repository không cần implement vì Mockito tạo mock. Trên Windows dùng `gradlew.bat test --tests com.example.security.DatabaseUserDetailsServiceTest`.

**Không dùng `@WithMockUser` trong unit test UserDetailsService**. Annotation đó dựng authenticated principal để test security context, không gọi `loadUserByUsername` và có thể tạo false positive.

## 7. Kiểm thử tài khoản bị khóa, vô hiệu hóa hoặc hết hạn

Trong cùng `DatabaseUserDetailsServiceTest.java` có thể thêm các method độc lập dưới đây:

```java
@Test
void disabledUserIsNotSilentlyMarkedEnabled() {
    AccountRecord disabled = new AccountRecord(
            "alice", encoder.encode("correct-pass"),
            false, false, false, false, Set.of("USER"));
    when(repository.findByUsernameKey("alice"))
            .thenReturn(Optional.of(disabled));

    UserDetails details = service.loadUserByUsername("alice");

    assertFalse(details.isEnabled());
    assertTrue(details.isAccountNonLocked());
}

@Test
void lockedUserIsNotMarkedUnlocked() {
    AccountRecord locked = new AccountRecord(
            "alice", encoder.encode("correct-pass"),
            true, true, false, false, Set.of("USER"));
    when(repository.findByUsernameKey("alice"))
            .thenReturn(Optional.of(locked));

    UserDetails details = service.loadUserByUsername("alice");

    assertFalse(details.isAccountNonLocked());
    assertTrue(details.isEnabled());
}

@Test
void expiredAccountAndCredentialsRemainDistinct() {
    AccountRecord expiredAccount = new AccountRecord(
            "alice", encoder.encode("correct-pass"),
            true, false, true, false, Set.of("USER"));
    when(repository.findByUsernameKey("alice"))
            .thenReturn(Optional.of(expiredAccount));

    assertFalse(service.loadUserByUsername("alice")
            .isAccountNonExpired());

    AccountRecord expiredPassword = new AccountRecord(
            "alice", encoder.encode("correct-pass"),
            true, false, false, true, Set.of("USER"));
    when(repository.findByUsernameKey("alice"))
            .thenReturn(Optional.of(expiredPassword));

    assertFalse(service.loadUserByUsername("alice")
            .isCredentialsNonExpired());
    assertTrue(service.loadUserByUsername("alice")
            .isAccountNonExpired());
}
```

Đây là **các method bổ sung vào test class trước đó**, không phải file Java độc lập. Chúng test mapping flag (tầng service); chưa chứng minh provider sẽ từ chối login. Một số ứng dụng có account status bổ sung như disabled-by-admin, locked-until, must-change-password, tenant suspended; phải chuyển chúng thành UserDetails flags hoặc check riêng trong provider theo chính sách.

**Không “sửa” bài test bằng cách ném `UsernameNotFoundException` cho mọi tài khoản disabled/locked trong service** nếu mong muốn hệ thống giữ được trạng thái có phân biệt ở tầng nội bộ. Chọn một contract nhất quán: service trả UserDetails với flags; provider quyết định có thể xác thực. Có thể che thông điệp phía UI để chống enumeration mà vẫn giữ logs/metrics nội bộ phù hợp.

## 8. Kiểm thử thật DaoAuthenticationProvider: mật khẩu sai và account status

Đây là tầng kế tiếp sau service. Khi nhận `UserDetails`, `DaoAuthenticationProvider` dùng `PasswordEncoder` và các bước kiểm trạng thái để xác thực. Ở Spring Security 6.5 có constructor `new DaoAuthenticationProvider(UserDetailsService)` và setter `setPasswordEncoder(...)`.

Tạo `src/test/java/com/example/security/DaoAuthenticationProviderTest.java`:

```java
package com.example.security;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.Authentication;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.AccountExpiredException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

class DaoAuthenticationProviderTest {

    private AccountRepository repository;
    private DaoAuthenticationProvider provider;
    private PasswordEncoder encoder;

    @BeforeEach
    void setUp() {
        repository = mock(AccountRepository.class);
        encoder = new BCryptPasswordEncoder(4);
        DatabaseUserDetailsService service =
                new DatabaseUserDetailsService(repository);
        provider = new DaoAuthenticationProvider(service);
        provider.setPasswordEncoder(encoder);
    }

    private AccountRecord fixture(boolean enabled,
                                  boolean locked,
                                  boolean accountExpired,
                                  boolean credentialsExpired) {
        return new AccountRecord("alice",
                encoder.encode("correct-pass"),
                enabled, locked, accountExpired,
                credentialsExpired, Set.of("USER"));
    }

    private void exists(AccountRecord record) {
        when(repository.findByUsernameKey("alice"))
                .thenReturn(Optional.of(record));
    }

    private Authentication login(String username, String rawPassword) {
        return provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, rawPassword));
    }

    @Test
    void existingUserAndCorrectPasswordAuthenticate() {
        exists(fixture(true, false, false, false));

        Authentication result = login("alice", "correct-pass");

        assertNotNull(result);
        assertTrue(result.isAuthenticated());
        assertEquals("alice", result.getName());
        assertTrue(result.getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("ROLE_USER")));
    }

    @Test
    void wrongPasswordFailsEvenThoughUserExists() {
        exists(fixture(true, false, false, false));

        assertThrows(BadCredentialsException.class,
                () -> login("alice", "wrong-pass"));
    }

    @Test
    void missingAccountIsNotAuthenticated() {
        when(repository.findByUsernameKey("ghost"))
                .thenReturn(Optional.empty());

        // Spring Security mặc định che UsernameNotFoundException,
        // biến thành BadCredentialsException ở provider boundary.
        assertThrows(BadCredentialsException.class,
                () -> login("ghost", "any-pass"));
    }

    @Test
    void disabledUserCannotAuthenticateWithCorrectPassword() {
        exists(fixture(false, false, false, false));

        assertThrows(DisabledException.class,
                () -> login("alice", "correct-pass"));
    }

    @Test
    void lockedUserCannotAuthenticateWithCorrectPassword() {
        exists(fixture(true, true, false, false));

        assertThrows(LockedException.class,
                () -> login("alice", "correct-pass"));
    }

    @Test
    void expiredAccountCannotAuthenticateWithCorrectPassword() {
        exists(fixture(true, false, true, false));

        assertThrows(AccountExpiredException.class,
                () -> login("alice", "correct-pass"));
    }

    @Test
    void expiredCredentialsCannotAuthenticateWithCorrectPassword() {
        exists(fixture(true, false, false, true));

        assertThrows(CredentialsExpiredException.class,
                () -> login("alice", "correct-pass"));
    }
}
```

Lưu ý: `Authentication` trong package `org.springframework.security.core.Authentication`, **không** nằm ở `org.springframework.security.authentication.Authentication`. Ví dụ phía trên đã dùng import chính xác sau đây cho `Authentication`:

```java
import org.springframework.security.core.Authentication;
```

Đây là dòng import đã dùng trong ví dụ, không phải import thứ hai cần thêm vào cùng file. Không sử dụng `org.springframework.security.authentication.Authentication`; các import exception vẫn thuộc `org.springframework.security.authentication`. Cách sửa giữ nguyên logic kiểm thử.

**Tại sao tầng này không dùng `@WithMockUser`?** Provider phải thật sự gọi UserDetailsService rồi chạy PasswordEncoder và account-status checks. Một principal đã giả lập có thể làm test pass dù mật khẩu sai hoặc account disabled.

**Khác biệt quan trọng giữa hai loại exception:**

- Ở **service**, tìm `ghost` không có user → `UsernameNotFoundException`.
- Ở **provider**, mặc định `AbstractUserDetailsAuthenticationProvider` **ẩn sự khác biệt user thiếu và password sai** bằng `BadCredentialsException` (`hideUserNotFoundExceptions=true`). Đó là lựa chọn giảm user enumeration, nhưng timing side-channel vẫn cần đánh giá riêng.
- Account locked/disabled/expired có thể ném exception nội bộ chuyên biệt; **không nên gửi nguyên tên exception** ra public login page để lộ trạng thái account.

Trong production, dùng BCrypt cost phù hợp năng lực/hardware, Argon2 hoặc DelegatingPasswordEncoder có policy rõ, đừng dùng test cost 4 như mức bảo mật mặc định. Đừng ghi rawPassword, hash hay exception message chứa username bí mật vào logs không bảo vệ.

## 9. Repository/JPA integration test: phát hiện bug mà Mockito không thấy

Mockito test nhanh nhưng **không xác minh truy vấn SQL/JPA**, unique indexes, collation, lazy loading hay transaction thật. Khi adapter là Spring Data JPA/JDBC, cần các test riêng:

1. Dữ liệu Alice tồn tại → repository query đúng normalized username, trả một bản ghi.
2. Bản ghi thiếu → `Optional.empty()`; không mặc định trả account đầu tiên.
3. Duplicate usernameKey → schema phải có **UNIQUE constraint** theo namespace/tenant. Không chọn tùy tiện một dòng nếu query trả nhiều.
4. Case-insensitive policy → dùng column normalized và unique theo policy, tránh DB này cho phép `Alice` và `alice` nhưng DB khác coi trùng.
5. Tenant binding → key phải chứa tenant/realm nếu username chỉ duy nhất **trong tenant**, không tra toàn bảng bằng username đơn lẻ.
6. Stored password là hash format mà encoder nhận; migration sang `{bcrypt}`/Argon2 có test compatibility.
7. Roles/authorities được load đầy đủ **trong transaction**; sau khi session đóng không phát `LazyInitializationException` bất ngờ.
8. Bản ghi disabled/locked/expired đúng, update account state phải có hiệu lực trong policy cache đã thiết kế.
9. DB outage/timeout phải **fail closed**, không tạo default user hoặc map mọi exception sang missing user để che lỗi vận hành.
10. Dữ liệu hai users concurrent không bị rò vào nhau do cache key sai hay biến state dùng chung.

Với Spring Boot 3.x và Spring Data JPA, có thể dùng `@DataJpaTest` với H2/Testcontainers để test repository thật. Ưu tiên Testcontainers hoặc database tương thích production khi case/collation/unique constraint đóng vai trò bảo mật. H2 có thể có hành vi khác PostgreSQL/MySQL ở Unicode/collation. Không đưa ra kết luận rằng JPA mapping đã an toàn chỉ vì unit mock pass.

### Vấn đề tenant khi UserDetailsService chỉ nhận username

`loadUserByUsername(String username)` **không có tham số tenant**. Nếu hai tenant đều có `username="alice"`, service không tự biết request thuộc tenant nào. Các cách đúng tùy kiến trúc:

- Thiết kế account key duy nhất toàn hệ thống, dùng immutable internal user ID để phân quyền/tenant.
- Ánh xạ định danh tổng hợp được xác thực theo policy (ví dụ tenant+username có format an toàn) và resolve trong custom authentication flow.
- Viết AuthenticationProvider chuyên biệt nhận tenant đã được xác minh, rồi lookup có composite key.

**Không dùng giá trị tenant do request tùy ý khai rồi cấp authority cross-tenant**. Nếu cần IP, HTTP request hoặc tenant context, theo Spring Security FAQ, UserDetailsService chỉ nhận username; đừng phụ thuộc thread-local session lỏng lẻo mà không có chính sách rõ.

## 10. Kiểm thử ứng dụng HTTP: nơi người dùng nhìn thấy 401/302/403

Ví dụ unit service và provider không chứng minh HTTP form login. Với một ứng dụng Spring MVC sử dụng form login, HTTP behavior thông thường:

```text
POST /login username=alice password=correct-pass + CSRF:
    -> form authentication success -> 302 redirect theo success handler
POST /login username=alice password=wrong-pass + CSRF:
    -> authentication fail -> 302 /login?error (theo default)
POST /login username=ghost password=any + CSRF:
    -> authentication fail -> 302 /login?error
GET /private (chưa login):
    -> redirect /login nếu FormLogin entry point
GET /admin (đã login ROLE_USER, cần ROLE_ADMIN):
    -> HTTP 403
POST /login thiếu CSRF:
    -> có thể 403 bởi CsrfFilter trước khi gọi UserDetailsService
```

Nếu ứng dụng chỉ dùng HTTP Basic, missing/wrong password thường trả 401 kèm `WWW-Authenticate: Basic ...`; trong Form Login, anonymous thường nhận **302 redirect** tới login page. Status **403** không chứng minh user đã login: CSRF có thể chặn cả anonymous.

### SecurityFilterChain fragment

Trong Spring Boot 3 Servlet có `UserDetailsService` bean hoặc authentication provider được cấu hình đúng:

```java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Đây là **fragment trong class @Configuration**, cần bean `UserDetailsService`/repository, imports cho `HttpSecurity`, `SecurityFilterChain` và `Customizer`; nó không tự chạy độc lập. **Đừng tắt CSRF** để POST login pass trong test. Khi UserDetailsService custom không có bean/adapter thật, Spring Boot không thể tự tạo một luồng authentication production đúng chỉ từ source code demo.

### MockMvc integration fragments

Trong `@SpringBootTest @AutoConfigureMockMvc` đã có bean `MockMvc mvc`, account repository/test datasource fixture và Spring Security Test:

```java
// Mã minh họa trong class test, đã có static imports get, post,
// csrf, status, redirectedUrlPattern và các test fixtures.

mvc.perform(post("/login")
        .with(csrf())
        .param("username", "alice")
        .param("password", "correct-pass"))
    .andExpect(status().is3xxRedirection());

// Khi sai password, default formLogin redirect về login?error:
mvc.perform(post("/login")
        .with(csrf())
        .param("username", "alice")
        .param("password", "wrong-pass"))
    .andExpect(status().is3xxRedirection());

// Request thiếu CSRF sẽ bị chặn trước authentication:
mvc.perform(post("/login")
        .param("username", "alice")
        .param("password", "correct-pass"))
    .andExpect(status().isForbidden());
```

**Chỉ assert 302 là chưa đủ**: thành công và thất bại đều có thể redirect. Cần dùng `SecurityMockMvcResultMatchers.authenticated()`/`unauthenticated()`, `redirectedUrl(...)`, kiểm session/Principal ở request sau, hoặc verify `UserDetailsService` đã được gọi theo đúng luồng, đồng thời kiểm DB side effect. Nếu request chạy qua `CsrfFilter` rồi 403 trước auth, đó **không phải test password sai hay missing user**.

Ngược lại, unit test service không nên boot toàn ứng dụng và gửi POST /login cho mọi case: như vậy chậm, phụ thuộc CSRF/routing/DB và khó chẩn đoán nguyên nhân.

## 11. Java 17 độc lập: mô hình hóa ba nhóm account để tự chạy

Mã dưới đây dùng JDK 17 thuần, không cài Spring. Nó mô hình hóa **hợp đồng tra cứu tài khoản**, không phải `UserDetailsService` production. Giá trị passwordHash trong demo chỉ là nhãn để phân biệt raw và stored credential; nó không lưu bcrypt, không xử lý password authentication, và không được copy làm cơ chế đăng nhập thật.

Lưu thành `UserDirectoryCasesLab.java`:

```java
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

public final class UserDirectoryCasesLab {

    record Account(String username, String passwordHash,
                   boolean enabled, boolean locked, Set<String> roles) {}

    static final class MissingAccount extends RuntimeException {
        MissingAccount() {
            super("Account cannot be loaded");
        }
    }

    static final class Directory {
        private final Map<String, Account> data = new HashMap<>();

        Directory() {
            data.put("alice", new Account(
                    "alice", "{bcrypt}fixture-hash-not-real",
                    true, false, Set.of("USER")));
            data.put("bob", new Account(
                    "bob", "{bcrypt}fixture-hash-not-real",
                    false, false, Set.of("USER")));
            data.put("carol", new Account(
                    "carol", "{bcrypt}fixture-hash-not-real",
                    true, true, Set.of("EDITOR")));
        }

        Account load(String username) {
            if (username == null || username.isBlank()) {
                throw new MissingAccount();
            }
            String key = username.strip().toLowerCase(Locale.ROOT);
            Account account = data.get(key);
            if (account == null || account.roles().isEmpty()) {
                throw new MissingAccount();
            }
            return account;
        }
    }

    static boolean rejected(Directory directory, String name) {
        try {
            directory.load(name);
            return false;
        } catch (MissingAccount expected) {
            return true;
        }
    }

    public static void main(String[] args) {
        Directory directory = new Directory();

        Account alice = directory.load(" ALICE ");
        System.out.println("existingCanonical=" +
                alice.username().equals("alice"));
        System.out.println("existingEnabled=" + alice.enabled());
        System.out.println("missingRejected=" +
                rejected(directory, "ghost"));
        System.out.println("blankRejected=" +
                rejected(directory, "  "));
        System.out.println("disabledFlag=" +
                !directory.load("bob").enabled());
        System.out.println("lockedFlag=" +
                directory.load("carol").locked());
        System.out.println("authoritiesFromAliceOnly=" +
                alice.roles().equals(Set.of("USER")));
    }
}
```

Chạy bằng Java 17+:

```bash
javac UserDirectoryCasesLab.java
java UserDirectoryCasesLab
```

Stdout **chính xác**:

```text
existingCanonical=true
existingEnabled=true
missingRejected=true
blankRejected=true
disabledFlag=true
lockedFlag=true
authoritiesFromAliceOnly=true
```

**Giải thích:** found/canonical user, missing/blank, disabled/locked, role mapping được kiểm độc lập; **không có chỗ nào so mật khẩu** vì mô hình Directory chỉ tải record. Bài lab không chứng minh Provider/SpringSecurity thật: các test JUnit ở mục 6 và 8 mới dùng API Spring thật.

## 12. Cache, concurrency và dữ liệu có thể đã thay đổi

### 12.1. Khi có UserCache

Spring Security có thể cache `UserDetails` (ví dụ các provider/caching services hoặc ứng dụng tự cache). Test cần hỏi:

- Một account vừa bị disabled/locked có tiếp tục được lấy ra từ cache với `isEnabled=true` không?
- User vừa bị thu hồi `ROLE_ADMIN` có tiếp tục giữ quyền cũ ở session/token/Authentication hay không?
- Sau password change, cache chứa hash cũ còn được dùng trong authentication mới bao lâu?
- Cache key chỉ theo username nhưng hai tenant trùng username có trả nhầm user không?
- Cache TTL/revocation có thống nhất giữa các instance không?

**Lưu ý:** sửa UserDetailsService không đồng nghĩa phiên HTTP đã authenticated sẽ mất hiệu lực ngay; SecurityContext/session hoặc JWT có vòng đời riêng. Test phải phân biệt **new authentication** sau thay đổi dữ liệu và **session đã phát hành** trước đó. Nếu sản phẩm cần revoke session tức thì, phải có session registry/revocation mechanism riêng.

### 12.2. Password/credentials erasure

Spring Security có thể xóa credentials khỏi Authentication sau khi login để giảm nguy cơ lộ. Nếu một cached `UserDetails` được tái dùng **cùng object mutable** và `eraseCredentials()` làm rỗng password field, lần login sau có thể bị lỗi vì cache trả về object đã mất hash. Kiểm cache implementation trả copy phù hợp hoặc vô hiệu cache khi cần; không bỏ tính năng xóa credentials để vá triệu chứng tùy tiện.

### 12.3. Concurrency

Hai request cùng load `alice` và `bob` phải trả bản ghi tương ứng. Service không nên lưu biến instance `currentUser`, `currentPassword` hay mutable `selectedTenant` để share giữa requests. Nếu có cache, dùng key gắn tenant/account chuẩn xác; nếu repository reactive, không lấy session context từ thread-local servlet ở service mà không có thiết kế.

Các test concurrency có thể dùng `ExecutorService` + latches, nhưng chỉ có ý nghĩa khi code thật có cache/mutable state; đừng thêm nhiều thread test vào service thuần chỉ để phức tạp hóa bài. Với DB, dùng transaction/unique constraint để bảo đảm duplicate account không trả ngẫu nhiên.

## 13. Những sai lầm phổ biến khi viết test

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Trả `null` khi user thiếu | Vi phạm contract `UserDetailsService` | Ném `UsernameNotFoundException` |
| Unit test password sai bằng `service.loadUserByUsername(...)` | Service không nhận raw password | Test `DaoAuthenticationProvider` với encoder |
| Expect `UsernameNotFoundException` trực tiếp từ provider mặc định | Provider thường che thành `BadCredentialsException` | Tách assertion service/provider |
| Assert only username nhưng không roles/flags | Có thể mở quyền hoặc bỏ qua account locked | Kiểm đủ identity, authorities, 4 status flags |
| Map `locked=true` thành `isAccountNonLocked=true` | Đảo chiều cờ | Kiểm test riêng locked và unlocked |
| Tạo `ROLE_USER` tự động khi DB roles rỗng | Privilege escalation hoặc sai business rules | Fail closed/contract được tài liệu hóa |
| Dùng `PasswordEncoder.encode(raw)` rồi so hash hai lần bằng `equals` | BCrypt dùng salt, hash khác qua mỗi lần | Dùng `matches(raw, hash)` |
| Dùng `{noop}`, test password plain text làm chuẩn production | Không bảo vệ password lưu | Chỉ dùng hash + PasswordEncoder thích hợp |
| Mock UserDetailsService khi đang kiểm chính nó | Test không chạy implementation | Mock **repository**, test real service |
| `@WithMockUser` để chứng minh password login | Bỏ qua provider + service | POST form login thật có CSRF / provider test |
| Test HTTP POST 403 rồi bảo “đã từ chối disabled user” | Có thể lỗi thiếu CSRF, không chạy auth | Thêm CSRF hợp lệ, assert failure reason |
| Dựa vào 302 cho login thành công | Fail form login cũng redirect | Assert Principal, authenticated(), redirect target |
| Dùng `findFirst` khi duplicate username | Tài khoản nào được chọn phụ thuộc truy vấn | Unique key + integration test DB |
| Không phân biệt tenant | Cùng username ở tenant khác có thể trộn dữ liệu | Namespace/tenant binding từ nguồn tin cậy |
| Test query bằng username raw nhưng code normalize | Mock trả Optional.empty sai làm false negative | `verify(repository).findByUsernameKey("alice")` |
| Catch mọi `RuntimeException` rồi trả user guest | Fail-open nghiêm trọng | Lỗi repository phải fail closed |
| Catch DB timeout rồi ném `UsernameNotFoundException` tùy tiện | Che sự cố, khó alert và có thể lệch timing | Internal error/telemetry riêng, public response an toàn |
| Ghi raw password hoặc full hash vào log | Lộ credential | Mask log, dùng correlation ID |
| Reuse mutable UserDetails trong cache sau credential erasure | Hash bị xóa, lần xác thực sau lỗi | Copy immutable/disable cache theo thiết kế |
| Tin roles từ request header | Người gọi tự cấp quyền | Roles lấy từ trusted server repository |

## 14. Test coverage cuối cùng theo từng tầng

| Tầng | Test quan trọng | Cần assert |
| --- | --- | --- |
| **Service + Mockito** | existing `alice` | đúng username canonical, password hash, authorities, 4 flags, đúng repository key |
| Service + Mockito | missing `ghost` | `UsernameNotFoundException`, không trả null/user khác |
| Service + Mockito | `null`/blank/case | policy chuẩn hóa/validation, không truy vấn DB với blank |
| Service + Mockito | disabled/locked/expired/credentialExpired | các cờ chính xác, không đảo dấu |
| Service + Mockito | không roles/role mismatch | không tự cấp role mới hoặc trộn account |
| **DaoAuthenticationProvider** | password đúng | Authentication hợp lệ và đúng principal |
| DaoAuthenticationProvider | wrong password | `BadCredentialsException` |
| DaoAuthenticationProvider | missing account | `BadCredentialsException` mặc định, không lộ user tồn tại |
| DaoAuthenticationProvider | disabled/locked | `DisabledException` / `LockedException` nội bộ |
| DaoAuthenticationProvider | expired account/password | `AccountExpiredException` / `CredentialsExpiredException` |
| **Repository/JPA** | normalized username, duplicate, case collation | UNIQUE đúng namespace, không trả nhầm user |
| Repository/JPA | tenant/authorities/lazy loading | đúng tenant, roles loaded trước khi transaction đóng |
| **MockMvc/HTTP** | form password đúng/sai/missing | authenticated/unauthenticated và redirect đúng |
| MockMvc/HTTP | POST login thiếu CSRF | bị chặn trước auth |
| MockMvc/HTTP | user ROLE_USER vào admin | 403, không side effect |
| **Security/system** | update DB lock/revoke role | auth mới và existing session theo policy cụ thể |
| Security/system | DB outage/cache stale | fail closed, metrics/correlation ID, không lộ credential |

**Gợi ý chạy trong CI:** ưu tiên component tests dưới 1 giây khi có thể (trừ cost password hashing), sau đó provider tests, repository integration tests với database test và vài MockMvc smoke tests. Tránh ép mọi hàng test thành `@SpringBootTest` nặng; kết quả khó đọc và việc một layer fail sẽ che bug của layer khác.

## 15. Checklist trước khi kết luận chức năng hoàn thành

- [ ] `loadUserByUsername` thực sự được gọi với key đúng và trả **UserDetails không null** cho account tồn tại.
- [ ] Missing username tạo `UsernameNotFoundException` ở service; provider mặc định không lộ user existence qua response login.
- [ ] Tên null/blank, policy case-insensitive, Unicode/email/tenant đã có test theo sản phẩm.
- [ ] Password hash được giữ nguyên từ trusted store; `PasswordEncoder.matches` chỉ được chạy ở tầng provider.
- [ ] Enabled, locked, accountExpired, credentialsExpired đã có positive/negative tests, không đảo dấu flags.
- [ ] Roles/authorities có prefix và đúng tenant; không lấy từ HTTP request, không tự thêm quyền mặc định.
- [ ] Mock repository để test service thật; mock service chỉ ở test **controller/authorization**, không để chứng minh chính service.
- [ ] Provider thật được kiểm với password đúng/sai và account disabled/locked/expired.
- [ ] Database có unique key và test duplicate/collation/tenant để tránh sai account.
- [ ] HTTP login có CSRF/redirect test, 401/403 đúng auth scheme, không hiểu 302/403 sai tầng.
- [ ] Cache invalidation và credential erasure không làm user cũ/role cũ tồn tại vô hạn.
- [ ] Không có password/token/hash lộ trong log, exception body, snapshot test.
- [ ] Các case denied không tạo session thành công, không phát access token hoặc side effect nghiệp vụ.
- [ ] Code test chỉ dùng account test, không dùng dữ liệu cá nhân thật hay kết nối production.

**Kết luận:** kiểm thử `UserDetailsService` là kiểm thử **độ đúng và tính an toàn của tra cứu danh tính**. Tài khoản tồn tại phải trả đúng user và flags/authorities; tài khoản thiếu phải ném `UsernameNotFoundException`; tài khoản không hợp lệ phải giữ trạng thái đúng để provider từ chối đăng nhập. Sau đó mới kiểm mật khẩu và HTTP security flow ở tầng tương ứng. Không một test dùng `@WithMockUser` hoặc chỉ thấy 302/403 có thể thay thế cả ba tầng kiểm thử.

### Tài liệu chính thức

- [Spring Security 6.5 — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html)
- [Spring Security — UserDetailsService API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsService.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — DaoAuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html)
- [Spring Security — UserDetails API and Credentials Erasure](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — MockMvc Security Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security FAQ — additional identity data / tenant context](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/faq.html)
