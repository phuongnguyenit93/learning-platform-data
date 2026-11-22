# UserDetailsChecker và các bước kiểm tra trước, sau đối chiếu mật khẩu

## 1. Đọc trạng thái tài khoản đúng lúc trong Spring Security

Khi ứng dụng nhận username/password, câu hỏi bảo mật không chỉ là **“Mật khẩu có đúng không?”**. Một tài khoản có thể tồn tại và mật khẩu vẫn đúng nhưng đã bị khóa, vô hiệu hóa, hết hạn hoặc có credential cần thay đổi. Spring Security tách việc kiểm tra thành nhiều bước để không cấp `Authentication` thành công cho một tài khoản không còn đủ điều kiện.

Trong luồng username/password dựa trên `DaoAuthenticationProvider`, interface **`UserDetailsChecker`** đại diện cho một phép kiểm tra *trạng thái của `UserDetails` đã tải từ nguồn tài khoản*. Lớp nền `AbstractUserDetailsAuthenticationProvider` sử dụng hai điểm mở rộng:

- **`preAuthenticationChecks`:** kiểm tra tài khoản **trước bước đối chiếu credentials**. Các kiểm tra mặc định gồm khóa tài khoản, vô hiệu hóa tài khoản và hết hạn tài khoản.
- **`postAuthenticationChecks`:** kiểm tra sau bước đối chiếu credentials; mặc định kiểm tra **credentials (ví dụ mật khẩu) đã hết hạn**.
- Nằm **giữa hai điểm** là `additionalAuthenticationChecks(...)` của `DaoAuthenticationProvider`, thường gọi `PasswordEncoder.matches(raw, encoded)` để đối chiếu mật khẩu.

Ba cụm trên **không giống** ba lần đăng nhập và cũng không phải ba interface khác nhau. `UserDetailsChecker` chỉ có một phương thức, có thể được dùng ở cả hai giai đoạn.

**Mục tiêu sau bài học:** giải thích bốn cờ trạng thái, thứ tự kiểm tra, cách biểu diễn lỗi, chi tiết mặc định của Spring Security 6.5.11, cách mở rộng checker mà không vô tình tắt bảo vệ sẵn có, và cách kiểm thử bằng một chương trình Java 17 chạy qua provider thật.

## 2. Đặt `UserDetailsChecker` đúng chỗ trong bộ máy xác thực

Các thành phần dễ nhầm:

| Thành phần | Hợp đồng chính | Trách nhiệm |
| --- | --- | --- |
| `UserDetailsService` | `loadUserByUsername(String)` | Lấy thông tin tài khoản, password hash, trạng thái và authorities từ kho danh tính. |
| **`UserDetailsChecker`** | `void check(UserDetails)` | Xem xét trạng thái persistent của user và ném exception nếu không đủ điều kiện. |
| `PasswordEncoder` | `matches(raw, encoded)` | Xác minh mật khẩu do client gửi có khớp hash lưu trữ hay không. |
| `DaoAuthenticationProvider` | `authenticate(Authentication)` qua interface provider | Điều phối các check, đối chiếu mật khẩu và xây authenticated token khi thành công. |
| `ProviderManager` | `AuthenticationManager.authenticate(...)` | Chọn provider, xử lý kết quả/ngoại lệ và có thể xóa credentials sau thành công. |
| `SecurityContext` | Chứa `Authentication` | Giữ kết quả xác thực cho ngữ cảnh xử lý; không thay thế DB transaction hay user store. |

**`UserDetailsChecker` không nhận mật khẩu người dùng nhập, HTTP request, JWT hay `UsernamePasswordAuthenticationToken`.** Nó chỉ nhận `UserDetails`:

```java
package org.springframework.security.core.userdetails;

public interface UserDetailsChecker {
    void check(UserDetails toCheck);
}
```

Đoạn trên diễn đạt chữ ký API, **không** phải class bạn cần sao chép vào dự án: interface đã có trong Spring Security. Những exception phát sinh từ checker là các subclass unchecked của `AuthenticationException`, tiêu biểu `LockedException` hoặc `CredentialsExpiredException`.

Theo hợp đồng API, checker nên xét **dữ liệu trạng thái đã được lưu và tải lên**. Quyết định dựa trên password/raw token được gửi tới lần đăng nhập hiện tại thuộc bước xác thực credentials/provider, không nên lén thực hiện trong `UserDetailsChecker`.

## 3. Bốn cờ trên `UserDetails` và ý nghĩa phủ định dễ nhầm

Mặc định Spring Security dùng các method mang tên phủ định:

| Method `UserDetails` | Giá trị cho tài khoản hợp lệ | Khi trả `false` | Loại lỗi mặc định |
| --- | --- | --- | --- |
| `isAccountNonLocked()` | `true` | Account bị khóa. | `LockedException` |
| `isEnabled()` | `true` | Account bị vô hiệu hóa. | `DisabledException` |
| `isAccountNonExpired()` | `true` | Account đã hết hạn. | `AccountExpiredException` |
| `isCredentialsNonExpired()` | `true` | Credentials đã hết hạn. | `CredentialsExpiredException` |

**Không trộn các cờ này với nhau.** Ví dụ user bị khóa do đăng nhập sai nhiều lần nhưng vẫn còn enabled. Một user hết hạn password vẫn có thể có account chưa hết hạn, không bị khóa và enabled.

Mẫu sai hay gặp trong adapter JPA:

```java
// SAI khi account.isLocked() == true nghĩa là đang BỊ khóa:
@Override
public boolean isAccountNonLocked() {
    return account.isLocked();
}
```

Mẫu đúng theo tên method:

```java
@Override
public boolean isAccountNonLocked() {
    return !account.isLocked();
}
```

Tương tự, nếu entity lưu `expired=true`, hãy trả `!expired` cho `isAccountNonExpired()`. Việc đảo nhầm boolean có thể cho phép account bị khóa đăng nhập hoặc chặn account bình thường.

Bốn cờ thuộc **dữ liệu UserDetails**. Chúng không tự động thể hiện số lần thử đăng nhập thất bại, thời điểm khóa tự hết hạn hay quy trình reset password; ứng dụng phải thực hiện logic cập nhật dữ liệu/cơ chế nghiệp vụ tương ứng. `UserDetailsChecker` **đọc và áp dụng** trạng thái, không tự quản lý lịch sử đăng nhập.

## 4. Thứ tự mặc định: trước password – password – sau password

Trong Spring Security **6.5.11**, luồng username/password của `AbstractUserDetailsAuthenticationProvider` và `DaoAuthenticationProvider` có thể tóm tắt:

```text
UsernamePasswordAuthenticationToken (authenticated=false)
                         |
                         v
AuthenticationManager / ProviderManager
                         |
                         v
DaoAuthenticationProvider
                         |
                         +--> Lấy UserDetails từ cache hoặc UserDetailsService
                         |
                         v
           preAuthenticationChecks.check(user)
                 1. accountNonLocked?  [LockedException]
                 2. enabled?           [DisabledException]
                 3. accountNonExpired? [AccountExpiredException]
                         |
                  khi pre hợp lệ
                         v
           additionalAuthenticationChecks(user, request)
                 PasswordEncoder.matches(rawPassword, storedHash)
                 [BadCredentialsException nếu không hợp lệ]
                         |
                  khi credential hợp lệ
                         v
           postAuthenticationChecks.check(user)
                 4. credentialsNonExpired?
                 [CredentialsExpiredException]
                         |
                         v
           Tạo Authentication đã xác thực
                         |
                         v
           SecurityContext (do filter xử lý khi web)
```

Đây là thứ tự **logic** để hiểu vai trò. Có **ngoại lệ quan trọng** về việc thực thi phép đối chiếu mật khẩu khi pre-check thất bại, trình bày ở mục 5; không suy ra từ sơ đồ rằng `matches(...)` tuyệt đối không chạy khi user bị khóa.

### Pre-check: ba trạng thái của tài khoản

Kiểm tra mặc định theo thứ tự:

1. `!user.isAccountNonLocked()` → `LockedException`.
2. `!user.isEnabled()` → `DisabledException`.
3. `!user.isAccountNonExpired()` → `AccountExpiredException`.

Nếu tài khoản đồng thời bị khóa và bị disabled, lỗi đầu tiên theo thứ tự trên thường là `LockedException`. Không nên dùng **thứ tự exception** làm hợp đồng công khai lâu dài của API đăng nhập; chính sách hiển thị ra client có thể khác nguyên nhân ghi audit nội bộ.

### Đối chiếu credentials: không phải việc của `UserDetailsChecker`

`DaoAuthenticationProvider.additionalAuthenticationChecks(...)` kiểm tra credentials có tồn tại và gọi:

```java
passwordEncoder.matches(presentedPassword, userDetails.getPassword())
```

`presentedPassword` là mật khẩu người dùng gửi lên, `userDetails.getPassword()` là hash/encoded password từ kho danh tính. Không so hai mật khẩu bằng `equals`, không gọi `encode(raw).equals(stored)` cho BCrypt vì salt, và không lấy credentials trực tiếp từ bên ngoài `UserDetailsChecker`.

Khi thất bại, provider thường ném `BadCredentialsException`. Nếu user không tồn tại, provider theo mặc định cũng **che `UsernameNotFoundException`** thành lỗi credentials tổng quát, nhằm giảm lộ sự tồn tại của tài khoản.

### Post-check: credential hết hạn

Sau khi mật khẩu khớp, mặc định gọi:

```java
if (!user.isCredentialsNonExpired()) {
    throw new CredentialsExpiredException("Credentials expired");
}
```

Đoạn này **diễn đạt ý tưởng** (message thực tế đến từ message source và có thể khác). Ý nghĩa: mật khẩu đúng vẫn **không đủ để tạo đăng nhập thành công** nếu credential đã hết hạn. Ứng dụng cần thiết kế luồng đổi mật khẩu/khôi phục an toàn; Spring Security không tự tạo giao diện đổi password chỉ vì cờ này là false.

### Bảng quyết định nhanh

| Account locked | Disabled | Account expired | Password | Credentials expired | Kết quả điển hình |
| --- | --- | --- | --- | --- | --- |
| Không | Không | Không | Đúng | Không | `Authentication` thành công. |
| **Có** | Bất kỳ | Bất kỳ | Đúng hoặc sai | Bất kỳ | `LockedException` theo pre-check mặc định. |
| Không | **Có** | Bất kỳ | Đúng hoặc sai | Bất kỳ | `DisabledException`. |
| Không | Không | **Có** | Đúng hoặc sai | Bất kỳ | `AccountExpiredException`. |
| Không | Không | Không | **Sai** | Bất kỳ | `BadCredentialsException`. |
| Không | Không | Không | **Đúng** | **Có** | `CredentialsExpiredException`. |

Bảng này giả định một provider mặc định tương thích, không có custom checker/provider khác thay đổi chính sách, không có lỗi cơ sở dữ liệu, và không có caching khiến dữ liệu bị cũ.

## 5. Chi tiết quan trọng của Spring Security 6.5.11: pre-check lỗi vẫn có thể chạy kiểm tra mật khẩu

Nếu nhìn sơ đồ cơ bản, rất dễ viết:

> “Account bị khóa thì provider dừng ngay, nên BCrypt chắc chắn không chạy.”

Điều này **không hoàn toàn đúng** ở Spring Security 6.5.11. `AbstractUserDetailsAuthenticationProvider` có cấu hình:

```java
setAlwaysPerformAdditionalChecksOnUser(boolean);
```

Trong **mã nguồn 6.5.11**, giá trị mặc định của thuộc tính này là **`true`**. Khi `preAuthenticationChecks.check(user)` ném một `AuthenticationException`, implementation có thể **vẫn gọi `additionalAuthenticationChecks(user, request)`** trong một khối bắt riêng, rồi **ném lại exception của pre-check**. Ngoại lệ phát sinh bởi bước credential check phụ được bỏ qua để giữ nguyên lý do trạng thái tài khoản.

Hệ quả:

- User **locked** và password **đúng**: lỗi cuối cùng vẫn là `LockedException`, dù password check có chạy.
- User **locked** và password **sai**: lỗi cuối cùng vẫn có thể là `LockedException`, không chuyển thành `BadCredentialsException`.
- User **disabled** hoặc **account expired**: áp dụng ý tưởng tương tự.
- Với account không có lỗi pre-check: bước credential check được thực hiện bình thường; **post-check chỉ chạy khi bước này không ném lỗi**.
- Với `credentialsNonExpired=false` và password **sai**: thông thường trả `BadCredentialsException` trước, vì chưa đến post-check.
- Với `credentialsNonExpired=false` và password **đúng**: post-check ném `CredentialsExpiredException`.

**Vì sao có lựa chọn này?** Để hạn chế chênh lệch thời gian xử lý giữa account hợp lệ và các account bị chặn trước khi kiểm tra mật khẩu. Nó **không bảo đảm constant-time cho toàn bộ HTTP request**, vì database/cache, exception handling và ứng dụng vẫn có thể tạo khác biệt. Không tắt cơ chế này bừa bãi chỉ nhằm giảm số lần BCrypt.

### Nếu đổi thành `false`?

`setAlwaysPerformAdditionalChecksOnUser(false)` khiến pre-check thất bại có thể dừng trước bước additional checks. Quyết định đó làm thay đổi timing, số phép băm và khả năng chạy các kiểm tra tùy biến, vì vậy cần threat model và kiểm thử. Không nên dùng option chỉ để tự đoán “kiểm tra trước” nghĩa là tuyệt đối không đụng mật khẩu.

**Cảnh báo extension:** nếu override `additionalAuthenticationChecks` để có tác dụng phụ (đếm sự kiện, gọi service bên ngoài, ghi dữ liệu), nó có thể chạy **dù pre-check đã thất bại**, hoặc chạy lặp lại khi provider thử tải lại user từ cache. Hãy giữ bước này an toàn/idempotent; thao tác audit nên đặt ở cơ chế phù hợp với sự kiện xác thực.

## 6. Ví dụ chạy thật trên Java 17+: kiểm chứng cả exception lẫn việc gọi `matches`

Demo console này dùng **Spring Security 6.5.11**, Java 17+ và Gradle. Nó chạy `DaoAuthenticationProvider` thật với `InMemoryUserDetailsManager` và `BCryptPasswordEncoder`. Một lớp bọc `CountingEncoder` ghi số lần gọi `matches(...)`, giúp quan sát sự khác biệt giữa **loại ngoại lệ trả về** và **việc đối chiếu password có diễn ra hay không**.

### 6.1. Cấu trúc dự án

```text
user-details-checker-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/CheckerDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'user-details-checker-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.CheckerDemo'
}
```

### 6.2. File `src/main/java/demo/CheckerDemo.java`

```java
package demo;

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
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class CheckerDemo {

    private static final String PASSWORD = "DemoPass123!";

    // Bộ đếm chỉ để minh họa trong console; không dùng làm encoder production.
    static final class CountingEncoder implements PasswordEncoder {
        private final PasswordEncoder delegate = new BCryptPasswordEncoder();
        private int matchesCalls;

        @Override
        public String encode(CharSequence rawPassword) {
            return delegate.encode(rawPassword);
        }

        @Override
        public boolean matches(CharSequence rawPassword,
                               String encodedPassword) {
            matchesCalls++;
            return delegate.matches(rawPassword, encodedPassword);
        }

        int matchesCalls() {
            return matchesCalls;
        }
    }

    private static UserDetails account(
            String username,
            CountingEncoder encoder,
            boolean locked,
            boolean disabled,
            boolean accountExpired,
            boolean credentialsExpired) {

        return User.withUsername(username)
                .password(encoder.encode(PASSWORD))
                .roles("READER")
                .accountLocked(locked)
                .disabled(disabled)
                .accountExpired(accountExpired)
                .credentialsExpired(credentialsExpired)
                .build();
    }

    private static void attempt(
            AuthenticationManager manager,
            CountingEncoder encoder,
            String label,
            String username,
            String password) {

        int before = encoder.matchesCalls();
        String outcome;

        try {
            Authentication result = manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            username, password));
            outcome = result.isAuthenticated()
                    ? "AUTHENTICATED" : "NOT_AUTHENTICATED";
        } catch (AuthenticationException ex) {
            outcome = ex.getClass().getSimpleName();
        }

        int matchCount = encoder.matchesCalls() - before;
        System.out.println(label + "=" + outcome
                + ", passwordMatchesCalled=" + matchCount);
    }

    public static void main(String[] args) {
        CountingEncoder encoder = new CountingEncoder();

        InMemoryUserDetailsManager users = new InMemoryUserDetailsManager(
                account("good", encoder,
                        false, false, false, false),
                account("locked", encoder,
                        true, false, false, false),
                account("disabled", encoder,
                        false, true, false, false),
                account("accountExpired", encoder,
                        false, false, true, false),
                account("credentialsExpired", encoder,
                        false, false, false, true));

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        AuthenticationManager manager = new ProviderManager(provider);

        // Chạy login thành công cuối cùng để demo không phụ thuộc
        // việc ProviderManager xóa credentials sau success.
        attempt(manager, encoder, "wrongPassword",
                "good", "bad-password");
        attempt(manager, encoder, "lockedCorrectPassword",
                "locked", PASSWORD);
        attempt(manager, encoder, "lockedWrongPassword",
                "locked", "bad-password");
        attempt(manager, encoder, "disabled",
                "disabled", PASSWORD);
        attempt(manager, encoder, "accountExpired",
                "accountExpired", PASSWORD);
        attempt(manager, encoder, "credentialsExpired",
                "credentialsExpired", PASSWORD);
        attempt(manager, encoder, "expiredCredentialsWrongPassword",
                "credentialsExpired", "bad-password");
        attempt(manager, encoder, "unknownUsername",
                "missing", PASSWORD);
        attempt(manager, encoder, "good",
                "good", PASSWORD);
    }
}
```

Các import `AccountExpiredException`, `BadCredentialsException`, `CredentialsExpiredException`, `DisabledException`, `LockedException` ở file trên được đưa vào nhằm giúp người đọc liên hệ các loại lỗi; chúng **không cần thiết cho logic hiện tại** vì code in tên exception bằng `getSimpleName()`. Với dự án có strict lint/Checkstyle cấm unused imports, có thể bỏ năm import đó mà chương trình vẫn hoạt động.

### 6.3. Lệnh chạy

Từ thư mục `user-details-checker-demo`, dùng JDK 17+ và Gradle/Gradle Wrapper hỗ trợ Java 17:

```bash
gradle run --quiet
```

**Các dòng stdout do chương trình in ra theo thứ tự**, không kể log có thể xuất hiện từ Gradle hoặc thư viện:

```text
wrongPassword=BadCredentialsException, passwordMatchesCalled=1
lockedCorrectPassword=LockedException, passwordMatchesCalled=1
lockedWrongPassword=LockedException, passwordMatchesCalled=1
disabled=DisabledException, passwordMatchesCalled=1
accountExpired=AccountExpiredException, passwordMatchesCalled=1
credentialsExpired=CredentialsExpiredException, passwordMatchesCalled=1
expiredCredentialsWrongPassword=BadCredentialsException, passwordMatchesCalled=1
unknownUsername=BadCredentialsException, passwordMatchesCalled=1
good=AUTHENTICATED, passwordMatchesCalled=1
```

Đầu ra này giả định **đúng phiên bản Spring Security 6.5.11**, cấu hình ở ví dụ, cache mặc định, chỉ một provider và không có custom checkers. Trong phiên bản khác, đặc biệt nếu thay đổi chính sách thực hiện additional checks, **không nên mặc định số lần gọi `matches` giống nhau**.

### 6.4. Đọc kết quả thật kỹ

**`wrongPassword`:** pre-check của `good` vượt qua; BCrypt so hash rồi trả false, provider ném `BadCredentialsException`.

**`lockedCorrectPassword`:** pre-check nhận ra account bị khóa và ghi nhận `LockedException`. Với mặc định `alwaysPerformAdditionalChecksOnUser=true`, provider vẫn chạy phép đối chiếu mật khẩu rồi ném lại `LockedException`.

**`lockedWrongPassword`:** mật khẩu cũng sai; phép `matches` có chạy nhưng ngoại lệ đầu ra vẫn là `LockedException` vì trạng thái locked đã bị từ chối trước.

**`disabled` và `accountExpired`:** cơ chế pre-check chặn việc tạo authenticated token ngay cả khi password thực sự khớp.

**`credentialsExpired`:** mật khẩu đúng nên đi qua bước additional checks; post-check phát hiện password hết hạn và ném `CredentialsExpiredException`.

**`expiredCredentialsWrongPassword`:** password sai nên dừng ở bước credential comparison; post-check không được gọi, kết quả là `BadCredentialsException`.

**`unknownUsername`:** `UserDetailsService` không tìm thấy user. Với provider mặc định, lỗi tên không tồn tại được che thành `BadCredentialsException`; `DaoAuthenticationProvider` còn có cơ chế đối chiếu với hash giả nhằm giảm timing leak cho trường hợp không tìm thấy user. Bộ đếm `matches` nhìn thấy lần so đó nhưng **không có user nào được xác thực**.

**`good`:** tất cả pre-check, password verification và post-check thành công, manager trả một `Authentication` đã xác thực. Ví dụ không tạo HTTP session; login thật trong Servlet filter còn cần bước thiết lập `SecurityContext` theo cấu hình.

**Lưu ý về bộ đếm:** `CountingEncoder` chỉ đếm số lời gọi Java vào `matches`, không chứng minh thuật toán có thời gian chạy hằng số; nó cũng không phải công cụ benchmark bảo mật. Không dùng tên tài khoản/mật khẩu mẫu trong môi trường production.

## 7. `UserDetailsChecker` tùy biến: cách giữ nguyên các bảo vệ mặc định

`AbstractUserDetailsAuthenticationProvider` có hai setter:

```java
provider.setPreAuthenticationChecks(customPreChecker);
provider.setPostAuthenticationChecks(customPostChecker);
```

**Hai setter này thay thế checker hiện hành**, không tự động nối thêm logic mới. Nếu viết:

```java
provider.setPreAuthenticationChecks(user -> {
    // Chỉ kiểm tra điều kiện do sản phẩm tự nghĩ ra.
});
```

thì bạn có thể vô tình **bỏ qua ba kiểm tra mặc định** về locked, disabled và account expired. Đây là lỗi nghiêm trọng nếu code nghiệp vụ tin rằng Spring Security vẫn kiểm tra đầy đủ trạng thái.

### Mẫu mở rộng an toàn hơn: bọc checker gốc

Vì `getPreAuthenticationChecks()` là method `protected`, một subclass có thể lưu checker mặc định rồi nối thêm điều kiện:

```java
// Trích đoạn trong dự án có AccountUserDetails implements UserDetails.
// Cần imports: DaoAuthenticationProvider, UserDetailsService,
// UserDetailsChecker, DisabledException.
public final class ApprovedAccountDaoProvider
        extends DaoAuthenticationProvider {

    public ApprovedAccountDaoProvider(UserDetailsService users) {
        super(users);

        // Lấy checker mặc định trước khi đặt checker mở rộng.
        UserDetailsChecker builtIn = getPreAuthenticationChecks();

        setPreAuthenticationChecks(user -> {
            builtIn.check(user);

            if (user instanceof AccountUserDetails account
                    && !account.isApproved()) {
                throw new DisabledException(
                        "Account awaiting approval");
            }
        });

        // KHÔNG setPostAuthenticationChecks: giữ nguyên kiểm tra
        // credentialsNonExpired mặc định của provider.
    }
}
```

Đây là **mã tích hợp minh họa**, không thể biên dịch độc lập nếu chưa có class `AccountUserDetails` và các bean tương ứng. Dự án thật phải có policy rõ ràng cho trạng thái `approved`, ưu tiên thông báo login tổng quát phía client để tránh account enumeration và bảo đảm dữ liệu được tải nhất quán khi xác thực.

Ưu điểm của cách **delegate checker có sẵn**:

1. Không tự sao chép thứ tự logic locked/disabled/account expired rồi có nguy cơ lệch khi nâng cấp framework.
2. Mỗi lần provider chạy pre-check, logic mặc định vẫn được gọi.
3. Checker mới chỉ thêm điều kiện của nghiệp vụ đã có trong `UserDetails`; nó không cần raw password hoặc HTTP request.
4. Post-check mặc định về credentials expired vẫn còn nguyên.

Nếu muốn thêm post-check, áp dụng ý tưởng tương tự với `getPostAuthenticationChecks()` trong subclass và chỉ đặt lại checker **sau khi giữ được delegate gốc**. Phải có test cho đủ bốn cờ mặc định và điều kiện mới.

### `AccountStatusUserDetailsChecker` có thay thế hai checker mặc định không?

Spring Security có một implementation `AccountStatusUserDetailsChecker`. Nó dùng để kiểm tra trạng thái của `UserDetails`, bao gồm trạng thái credential. **Đừng tự gắn đối tượng này vào pre-check rồi mặc định nghĩ thứ tự trước/sau password vẫn y hệt.** Mục tiêu của bài này là giữ đúng ranh giới: các kiểm tra account trước credential matching, còn `isCredentialsNonExpired()` theo cấu hình mặc định của `AbstractUserDetailsAuthenticationProvider` được kiểm tra sau bước đó. Khi dùng checker khác, bạn phải hiểu chính xác nó kiểm tra những flag nào và ở thời điểm nào.

### Những trường hợp không nên đưa vào checker

`UserDetailsChecker` không có tham số `Authentication`. Vì vậy nó không thích hợp để:

- So mật khẩu đã nhập với hash.
- Kiểm tra TOTP/OTP hoặc chữ ký bearer token.
- Đọc `HttpServletRequest` để quyết định mọi điều kiện đăng nhập.
- Thực hiện rate limiting theo IP/browser.
- Thay thế kiểm tra quyền truy cập một hóa đơn, tài liệu hoặc tài nguyên nghiệp vụ.
- Ghi session hoặc tự đặt `SecurityContextHolder`.

Các điều kiện này cần filter/provider/chính sách bảo mật hoặc service nghiệp vụ phù hợp. Việc trộn chúng vào checker làm khó kiểm thử, khó giữ tính thuần và dễ bỏ qua cơ chế xác thực chuẩn.

## 8. Lưu trữ trạng thái tài khoản trong database như thế nào?

Một entity tài khoản thường có các trường như:

```text
account_id          (khóa nội bộ, bất biến)
username_key        (unique theo policy)
password_hash       (BCrypt/Argon2/...)
enabled             (boolean)
locked_until        (timestamp nullable)
account_expires_at  (timestamp nullable)
password_expires_at (timestamp nullable)
roles               (quan hệ hoặc bảng riêng)
```

Đây là **mô hình gợi ý**, không phải schema mặc định của Spring Security. `UserDetails` phải trả kết quả trạng thái từ dữ liệu:

```java
// Đoạn trích trong adapter user store, không phải class độc lập.
Instant now = clock.instant();

boolean nonLocked = account.lockedUntil() == null
        || !account.lockedUntil().isAfter(now);
boolean accountNonExpired = account.accountExpiresAt() == null
        || account.accountExpiresAt().isAfter(now);
boolean credentialsNonExpired =
        account.passwordExpiresAt() == null
        || account.passwordExpiresAt().isAfter(now);
```

Ở ví dụ này, `lockedUntil` được xem là hết khóa khi `now >= lockedUntil`. Quy ước cho thời điểm hết hạn cũng dùng `now < expiresAt` để còn hiệu lực. **Đây là chính sách của ứng dụng**, không phải công thức có sẵn trong `UserDetailsChecker`. Cần xử lý timezone/clock, đồng bộ giữa nhiều server, transaction, cập nhật đồng thời và cách tính thời điểm khóa theo business requirement.

Nếu có cột `locked=true` riêng, không được bỏ qua nó khi tính `isAccountNonLocked`. Nếu có nhiều nguyên nhân khóa (bị admin khóa vô thời hạn, tự động khóa tạm thời), ưu tiên mô hình trạng thái biểu diễn đủ các lý do thay vì suy ra từ một timestamp thiếu ngữ cảnh.

### Chuyển entity thành `UserDetails` không phụ thuộc ORM Session

Trong Spring Data JPA, các flags và authorities nên được **materialize trong giao dịch đọc**, rồi chuyển thành `UserDetails` độc lập, ví dụ:

```java
// Trích đoạn trong @Service bean có repository, clock và policy.
// Phải có imports Spring Security UserDetails/User, transaction...
@Transactional(readOnly = true)
public UserDetails loadUserByUsername(String username) {
    Account account = accounts.findForAuthentication(username)
            .orElseThrow(() ->
                    new UsernameNotFoundException("Account not found"));

    return User.withUsername(account.getUsername())
            .password(account.getPasswordHash())
            .roles(account.getRoleCodes().toArray(String[]::new))
            .disabled(!account.isEnabled())
            .accountLocked(account.isLocked())
            .accountExpired(account.isAccountExpired())
            .credentialsExpired(account.isPasswordExpired())
            .build();
}
```

Đây **không phải chương trình đầy đủ**, vì `Account`/`accounts`/method domain được dự án định nghĩa. Mục đích là tạo snapshot có hash, flags và authorities **đã kiểm tra/đọc trong transaction**, không trả entity có lazy collection để provider gọi `getAuthorities()` ngoài transaction.

Không ép mọi relation `EAGER` chỉ để đăng nhập chạy; hãy dùng fetch plan/projection phù hợp. Trạng thái account thay đổi sau login **không mặc nhiên** làm `Authentication` đang giữ trong session thay đổi; cần thiết kế policy làm mới/thu hồi xác thực.

## 9. Sau khi status-check thất bại, HTTP trả gì?

`UserDetailsChecker` ném `AuthenticationException` để cho biết **lần xác thực không thành công**. Nó **không trực tiếp chọn** HTTP status, redirect hay response JSON.

Tùy cơ chế:

- **Form login:** authentication filter/failure handler có thể redirect về trang đăng nhập với thông báo chung.
- **HTTP Basic:** authentication entry point thường trả `401` và `WWW-Authenticate`; không tự suy ra exception bị locked sẽ thành một mã HTTP riêng.
- **Authenticated user thiếu quyền:** thường xử lý qua authorization và `AccessDeniedHandler`, có thể trả `403`; đây là bước **khác** với từ chối credential/account trước login.
- **REST login do ứng dụng tự triển khai:** phải xử lý thất bại nhất quán và không tạo token/session thành công khi checker ném exception.

Có thể ghi nhận loại lỗi thật ở hệ thống audit có quyền truy cập phù hợp, nhưng không nên trả đầy đủ “username tồn tại, đang khóa đến 10 giờ” cho mọi người chưa đăng nhập. Điều này có thể giúp attacker dò tài khoản hợp lệ. Chính sách thông báo và account recovery cần cân bằng UX với phòng chống enumeration.

**Một cảnh báo khi test:** đừng assert cứng mọi trường hợp locked/disabled là HTTP 403. Trên đường authentication, hành vi đi qua entry point/failure handler; cần test cấu hình filter cụ thể. Ngoại lệ Java trong provider và HTTP status ở client là hai lớp trách nhiệm khác nhau.

## 10. Cache và phiên đăng nhập: checker không chạy trên mọi request

`AbstractUserDetailsAuthenticationProvider` có `UserCache`; mặc định thường là `NullUserCache`. Nếu ứng dụng cấu hình cache khác, provider có thể dùng thông tin `UserDetails` đã lưu thay vì đọc lại kho tài khoản ngay.

Theo implementation 6.5.11, khi một kiểm tra liên quan đến cached user thất bại, provider có thể **tải lại user từ nguồn** rồi chạy kiểm tra một lần nữa. Cơ chế này hữu ích khi thông tin cached đã cũ, nhưng **không phải cam kết mọi trạng thái account luôn được kiểm tra lại database trên mỗi request**.

Phân biệt:

- **UserCache của provider:** tăng hiệu năng một số lần gọi authenticate; liên quan thời điểm tải user và trạng thái/cache invalidation.
- **SecurityContext trong session:** sau login, nhiều HTTP request có thể dùng authentication đã lưu mà **không gọi lại `DaoAuthenticationProvider`**.
- **JWT tự chứa:** khi resource server xác minh JWT, cơ chế có thể không tải `UserDetails` từ DB; các cờ ở `UserDetailsChecker` không mặc nhiên được gọi.
- **Remember-me:** có cơ chế xác thực riêng; không thể lấy kiểm tra pre/post của username/password làm bảo đảm phổ quát cho mọi cơ chế.

Nếu admin khóa user ngay khi họ đang có session hợp lệ, bạn phải thiết kế **session invalidation, authority/version checks, reauthentication hoặc policy đánh giá trạng thái hiện tại** theo rủi ro. `UserDetailsChecker` không tự “đăng xuất tất cả thiết bị” chỉ vì cột `locked=true` trong DB.

Nếu user cache đang giữ hash/password/`UserDetails` mutable, việc xóa credentials khỏi authentication object có thể tác động dữ liệu cached khi dùng chung instance; tránh lưu entity/proxy hoặc dùng cache không có chiến lược làm mới. Cần test thực tế với provider và cách tạo/copy `UserDetails` đang triển khai.

## 11. Kiểm thử cần tách ba loại hành vi

### A. Kiểm tra đơn vị của `UserDetailsChecker`

Khi có custom checker, đưa `UserDetails` với các tổ hợp flags vào và xác nhận:

- Account locked bị từ chối.
- Disabled bị từ chối.
- Account expired bị từ chối.
- Trạng thái chính sách riêng như pending approval bị từ chối.
- User hợp lệ đi qua.
- Checker **không cần raw password** để quyết định trạng thái.

Test unit không cần HTTP filter hay database nếu account snapshot được xây đầy đủ.

### B. Integration test qua `DaoAuthenticationProvider`

Đây là nơi xác nhận **thứ tự và kết quả thực**:

| Trường hợp | Password | Exception mong đợi theo 6.5.11 mặc định |
| --- | --- | --- |
| Account enabled/unlocked/not expired | Đúng, credentials valid | Authenticated token |
| Account locked | Đúng | `LockedException` |
| Account locked | Sai | `LockedException`, vẫn có thể gọi encoder |
| Account disabled | Đúng | `DisabledException` |
| Account expired | Đúng | `AccountExpiredException` |
| Credentials expired | Đúng | `CredentialsExpiredException` |
| Credentials expired | Sai | `BadCredentialsException` |
| Username không tồn tại | Bất kỳ | `BadCredentialsException` mặc định |
| Password sai, account otherwise valid | Sai | `BadCredentialsException` |

Bảng giả định chỉ một provider và không có policy tùy biến. Ví dụ ở mục 6 là một integration-style console test có thể chạy lại để quan sát.

### C. Test filter và hành vi HTTP

Trong Spring Boot MVC, cấu hình Spring Security filter thật rồi kiểm thử:

- Gửi HTTP Basic/form credentials đúng → được xác thực theo URL policy.
- Gửi password sai → failure handler/entry point phù hợp; không có session thành công.
- User locked/disabled/expired → không được tạo authentication thành công.
- Authentication đã tồn tại nhưng thiếu role → authorization từ chối theo `hasRole`/`hasAuthority`.
- Session cũ sau khi khóa account → hành vi phù hợp **chính sách thu hồi phiên** đã thiết kế.

**Không dùng `@WithMockUser` làm bằng chứng rằng checker hoạt động.** Annotation này tạo identity giả cho test và thường bỏ qua `UserDetailsService`, provider và `PasswordEncoder`. Nó phù hợp để test authorization với một principal xác định, nhưng không chứng minh đường login thực từ user store.

## 12. Mở rộng chính sách: nên đặt kiểm tra ở đâu?

Một số yêu cầu nghiệp vụ nghe giống nhau nhưng thuộc những lớp khác:

| Chính sách | Chỗ phù hợp | Vì sao |
| --- | --- | --- |
| User bị khóa/disabled/expired | `UserDetailsChecker` hoặc logic trạng thái chuẩn trong provider | Dựa trên dữ liệu trạng thái persistent của `UserDetails`. |
| Password hash khớp chưa? | `PasswordEncoder.matches(...)` trong provider | Cần mật khẩu do client gửi và hash lưu. |
| Credential quá hạn theo thời gian DB | Tính flag `credentialsNonExpired` khi nạp user, post-check | Trạng thái credential hết hạn khác việc secret có khớp. |
| OTP/MFA đã hoàn tất chưa? | Authentication mechanism phù hợp, step-up/authorization policy | Không thể kết luận bằng một boolean trạng thái password chung. |
| User chỉ được login trong tenant hiện tại | Tầng định danh/tenant-aware provider và context đã kiểm chứng | `UserDetailsChecker` không nhận HTTP request/tenant context theo contract. |
| IP bị rate limit | Filter/gateway/limiter chuyên dụng | Cần dữ liệu request và bộ đếm phân tán. |
| Admin thu hồi role khi user đã login | Session/token revocation hoặc authorization nghiệp vụ | Checker không chạy bắt buộc ở mỗi request sau login. |
| Password bị lộ trong kho breach | `CompromisedPasswordChecker` nếu cấu hình, hoặc flow thay mật khẩu | Không phải cùng thứ với cờ `credentialsNonExpired`. |

`DaoAuthenticationProvider` còn hỗ trợ `CompromisedPasswordChecker` và `UserDetailsPasswordService` trong giai đoạn xây authentication thành công, tùy cấu hình. Không nhầm các extension này với **hai `UserDetailsChecker`** pre/post. `CompromisedPasswordChecker` xử lý việc password đã bị lộ theo chính sách; `UserDetailsPasswordService` giúp nâng cấp hash khi thích hợp. Chúng có trách nhiệm khác với việc account locked/disabled hay credentials expired.

## 13. Sai lầm phổ biến và cách sửa

1. **Cho rằng `UserDetailsChecker` so mật khẩu.** Sai: nó chỉ nhìn `UserDetails`, còn `DaoAuthenticationProvider.additionalAuthenticationChecks` và `PasswordEncoder` xác minh secret.
2. **Nghĩ mọi check diễn ra trước password.** Sai: `credentialsNonExpired` mặc định được kiểm tra ở post-check sau credential matching hợp lệ.
3. **Nghĩ pre-check thất bại thì BCrypt chắc chắn không chạy.** Không đúng mặc định 6.5.11 với `alwaysPerformAdditionalChecksOnUser=true`; exception cuối vẫn là lỗi trạng thái gốc.
4. **Coi `setPreAuthenticationChecks` là phép cộng checker.** Setter thay thế checker; có thể làm mất locked/disabled/account-expired checks. Giữ delegate mặc định hoặc kiểm tra lại đầy đủ.
5. **Coi `setPostAuthenticationChecks` luôn giữ kiểm tra password expiry.** Setter thay thế; nếu bỏ mặc định, account có credential hết hạn có thể được xác thực trái policy.
6. **Đảo nhầm boolean `isAccountNonLocked`.** `false` nghĩa account đang khóa; khi entity dùng `isLocked` phải đảo dấu.
7. **Gộp `accountExpired` và `credentialsExpired` thành cùng một cờ.** Hai trạng thái có nguyên nhân và cách xử lý khác nhau.
8. **Tự chỉnh `authentication.setAuthenticated(true)` để bỏ qua lỗi.** Không được cấp danh tính đáng tin cậy khi pre/password/post không hoàn thành.
9. **Bắt mọi `AuthenticationException` rồi trả authenticated token.** Vi phạm ranh giới tin cậy của hệ thống.
10. **Dùng một login error message lộ quá nhiều trạng thái.** Có thể giúp dò tên tài khoản; phân biệt audit nội bộ và phản hồi công khai.
11. **Cho rằng `@WithMockUser` chứng minh password và status checks.** Test mock thường không gọi provider.
12. **Cho rằng đã khóa DB là session cũ mất hiệu lực ngay.** Cần cơ chế invalidation/revalidation riêng.
13. **Lấy trạng thái từ JPA entity detached/lazy sau khi transaction đóng.** Xây snapshot `UserDetails` đầy đủ khi đọc DB.
14. **Bật cache mà không làm mới account flags.** Có thể xác thực bằng dữ liệu cũ; thiết kế TTL, invalidation và test cache.
15. **Lạm dụng checker để kiểm tra IP/OTP/tenant từ request.** Contract không chứa request; chọn đúng lớp xử lý.
16. **Đặt biến `credentialsExpired=true` trong entity mà không map sang `isCredentialsNonExpired=false`.** Provider không biết mật khẩu đã quá hạn nếu adapter trả sai cờ.
17. **Cho rằng `readOnly` transaction tự khóa account hay so password.** Transaction chỉ đọc dữ liệu; checkers/provider quyết định authentication.
18. **Đăng nhập đúng password thì bỏ qua disabled/locked state.** Password là một điều kiện cần, không phải toàn bộ điều kiện cấp phiên.
19. **Dựa vào thông điệp tiếng Anh chính xác của exception.** Message source/localization có thể khác; test loại exception/contract, không cứng vào text.
20. **Tự động tắt `alwaysPerformAdditionalChecksOnUser` để tăng hiệu năng.** Có đánh đổi về timing/khác biệt hành vi, cần đánh giá trước.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `UserDetailsChecker.check(user)` nhận những dữ liệu nào và có trực tiếp so password không?

**Đáp án:** Nhận một `UserDetails` chứa trạng thái account; không nhận raw password, request HTTP hoặc JWT. Đối chiếu password là việc của provider/encoder.

**Câu 2.** Theo mặc định Spring Security 6.5.11, ba pre-check là gì?

**Đáp án:** Lần lượt tài khoản không bị khóa, enabled và account chưa hết hạn. Các lỗi tương ứng `LockedException`, `DisabledException`, `AccountExpiredException`.

**Câu 3.** Mật khẩu đúng nhưng `credentialsNonExpired=false` thì có login thành công không?

**Đáp án:** Không. Post-check ném `CredentialsExpiredException` sau khi bước password matching đã đi qua.

**Câu 4.** Mật khẩu sai và `credentialsNonExpired=false` thì ngoại lệ nào thường được thấy?

**Đáp án:** `BadCredentialsException`, vì bước credential comparison thất bại trước post-check.

**Câu 5.** User bị khóa, password sai, nhưng bộ đếm `matches` vẫn tăng. Có phải framework đã cho login rồi mới khóa không?

**Đáp án:** Không. Trong 6.5.11, default có thể chạy additional checks dù pre-check đã thất bại nhằm giảm timing disparity, rồi ném lại lỗi `LockedException`. Không có authenticated result.

**Câu 6.** Thêm `provider.setPreAuthenticationChecks(user -> {})` có giữ bảo vệ mặc định không?

**Đáp án:** Không. Setter thay thế checker; nếu lambda rỗng thì các điều kiện locked/disabled/account expired có thể bị bỏ qua. Cần bọc checker mặc định hoặc tự chứng minh đầy đủ bằng test.

**Câu 7.** Thêm `@WithMockUser` vào integration test có đủ chứng minh user bị khóa không thể login không?

**Đáp án:** Không. Mock user có thể bỏ qua manager/provider. Hãy gọi `AuthenticationManager.authenticate(...)` hoặc test HTTP filter thực với thông tin đăng nhập.

**Câu 8.** Khi admin khóa user trong DB, các request sau của session đã có `Authentication` có tự qua pre-check lại không?

**Đáp án:** Không được giả định. Cần chiến lược revalidation, session revocation hoặc policy authorization riêng.

**Câu 9.** `AccountStatusUserDetailsChecker` có thể đặt bừa vào pre-check và bảo đảm thứ tự giống mặc định không?

**Đáp án:** Không. Phải hiểu checker đó xét các flags nào và được gọi tại thời điểm nào; phân tách pre/account và post/credentials có ý nghĩa nghiệp vụ và trải nghiệm.

**Câu 10.** Tại sao phản hồi cho client không nhất thiết dùng đúng tên exception?

**Đáp án:** Authentication và HTTP failure handling là các tầng riêng; phản hồi chi tiết có thể rò rỉ trạng thái/tính tồn tại của tài khoản. Dùng failure handler/entry point và chính sách thông báo phù hợp.

## 15. Tài liệu tham khảo chính thức

- [Spring Security 6.5.11 — UserDetailsChecker API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsChecker.html): hợp đồng `check(UserDetails)` và mục đích kiểm tra trạng thái dữ liệu persistent.
- [Spring Security 6.5.11 — AbstractUserDetailsAuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html): pre/post checker setters, `setAlwaysPerformAdditionalChecksOnUser`, cache và cách tạo authentication.
- [Spring Security 6.5.11 — Mã nguồn AbstractUserDetailsAuthenticationProvider](https://github.com/spring-projects/spring-security/blob/6.5.11/core/src/main/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.java): thứ tự mặc định locked → disabled → account expired; additional checks; post credentials expired; cách giữ lỗi pre-check khi vẫn chạy so password.
- [Spring Security 6.5.11 — DaoAuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html): `UserDetailsService`, `PasswordEncoder` và các điểm mở rộng xác thực password.
- [Spring Security 6.5.11 — User.UserBuilder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html): `accountLocked`, `disabled`, `accountExpired` và `credentialsExpired` trong fixture.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): đường đi từ authentication filter qua manager/provider tới user store.
- [Spring Security — UserDetails API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html): các cờ `isAccountNonLocked`, `isEnabled`, `isAccountNonExpired` và `isCredentialsNonExpired`.

**Kết luận:** `UserDetailsChecker` giúp Spring Security áp dụng trạng thái tài khoản tại **hai điểm kiểm tra riêng**: pre-check cho khóa/disabled/account expiry, post-check cho credentials expiry. Bước đối chiếu password do provider/encoder thực hiện ở giữa về mặt quyết định. Trong Spring Security 6.5.11, một password check bổ sung vẫn có thể chạy khi pre-check đã thất bại, nhưng không thể biến trạng thái account không hợp lệ thành đăng nhập thành công. Giữ các checker mặc định khi tùy biến, viết test qua provider thật và quản lý riêng việc thu hồi session sau khi trạng thái DB thay đổi.