# isCredentialsNonExpired và yêu cầu đổi thông tin xác thực trong Spring Security

> **Bối cảnh:** Spring Security → Authentication → **Trạng thái tài khoản**. Bài học phân tích ý nghĩa `UserDetails.isCredentialsNonExpired()`, lúc nào `DaoAuthenticationProvider` ném `CredentialsExpiredException`, cách quyết định chính sách hết hạn mật khẩu và thiết kế luồng **buộc đổi mật khẩu / khôi phục credential an toàn**. Có ví dụ Java 17+ chạy độc lập bằng Gradle + Spring Security 6.5.x, ví dụ ánh xạ DB, kiểm thử, xử lý HTTP và những rủi ro về session, token, cache, phân quyền.

## 1. Vấn đề: mật khẩu đúng chưa chắc được đăng nhập

Giả sử tài khoản `mai` có mật khẩu đúng nhưng tổ chức áp dụng chính sách:

- Mật khẩu đã quá tuổi cho phép (ví dụ 90 ngày).
- Quản trị viên gắn cờ **bắt buộc đổi mật khẩu** ở lần đăng nhập tiếp theo.
- Tài khoản vừa được cấp mật khẩu tạm thời, chỉ được phép thực hiện một quy trình thiết lập credential mới.
- Có sự cố rò rỉ/đặt lại credential khiến mật khẩu cũ không còn được coi là hợp lệ cho việc đăng nhập bình thường.

Trong các tình huống cần **chặn xác thực bình thường**, Spring Security cung cấp một cờ trạng thái trên `UserDetails`:

```java
boolean valid = userDetails.isCredentialsNonExpired();
```

Đây là đoạn Java minh họa trong một phương thức đã có biến `userDetails`.

- Trả **`true`**: credentials của tài khoản **chưa hết hạn** theo chính sách mà ứng dụng đã ánh xạ.
- Trả **`false`**: credentials **đã hết hạn**; với luồng `DaoAuthenticationProvider` mặc định, tài khoản **không được xác thực thành công**, ngay cả khi mật khẩu phù hợp với hash.
- Phương thức **không tự tính ngày hết hạn**, không đổi mật khẩu, không gửi email và không mở trang đổi mật khẩu. Ứng dụng phải cung cấp logic chính sách và quy trình đổi/khôi phục riêng.

**Kết luận quan trọng:** `isCredentialsNonExpired() == false` không phải “đã đăng nhập, nhưng chỉ được mở trang đổi mật khẩu”. Trong flow mặc định nó là **lý do từ chối authentication**. Nếu muốn một trạng thái *đã xác minh danh tính nhưng bị giới hạn quyền cho tới khi đổi credential*, phải thiết kế một cơ chế giới hạn riêng, không trông chờ Spring Security tự tạo ra trạng thái đó.

## 2. Phân biệt các trạng thái tài khoản và lỗi xác thực

`UserDetails` mô tả nhiều điều kiện có thể từ chối đăng nhập:

| Phương thức | `true` có nghĩa | Khi `false` trong username/password flow chuẩn |
| --- | --- | --- |
| `isEnabled()` | Tài khoản được kích hoạt | `DisabledException` |
| `isAccountNonLocked()` | Tài khoản không bị khóa | `LockedException` |
| `isAccountNonExpired()` | Bản thân tài khoản còn hiệu lực | `AccountExpiredException` |
| **`isCredentialsNonExpired()`** | **Thông tin xác thực còn hiệu lực** | **`CredentialsExpiredException`** |

Cả bốn thuộc hợp đồng `UserDetails`. Trong Spring Security 6.5, các trạng thái này có giá trị mặc định `true` nếu implementation không override. Nếu dữ liệu DB có cờ mật khẩu hết hạn nhưng một custom `UserDetails` không ánh xạ sang `isCredentialsNonExpired()`, Spring Security **không thể tự biết** rằng mật khẩu đã hết hạn.

**Khác nhau về ý nghĩa:**

- `isAccountNonExpired() == false`: account hết hiệu lực, chẳng hạn hợp đồng tài khoản kết thúc. Đổi mật khẩu không tự làm account hợp lệ.
- `isCredentialsNonExpired() == false`: bằng chứng đăng nhập hiện tại không còn được chấp nhận cho đăng nhập bình thường. Sau một quy trình đổi credential hợp lệ, account có thể tiếp tục được dùng.
- `isAccountNonLocked() == false`: có thể do phát hiện rủi ro hoặc nhiều lần đăng nhập sai. Đổi password **không mặc định** được phép tự mở khóa nếu chính sách yêu cầu bộ phận bảo mật can thiệp.
- `BadCredentialsException`: credential người dùng trình bày không hợp lệ (hoặc username không được tiết lộ); không đồng nghĩa account có chính sách hết hạn.
- JWT `exp` claim hoặc OAuth2 access-token hết hạn: là **thời hạn của token**, không phải trạng thái `UserDetails.isCredentialsNonExpired()`. Các cơ chế đó thường không gọi `DaoAuthenticationProvider` hay `UserDetailsService` cho mỗi token.

### Đừng đảo nghĩa cờ

```text
credential của user vẫn hợp lệ?
    YES -> isCredentialsNonExpired() = true
    NO  -> isCredentialsNonExpired() = false

User builder:
    .credentialsExpired(false) -> credentialsNonExpired = true
    .credentialsExpired(true)  -> credentialsNonExpired = false
```

`User.UserBuilder.credentialsExpired(...)` nhận một giá trị mang nghĩa **đã hết hạn**, trong khi method `isCredentialsNonExpired()` mang nghĩa **chưa hết hạn**. Nhiều lỗi cấu hình bắt nguồn từ việc chuyển trực tiếp `credentialsExpired` mà không đảo logic.

## 3. Spring Security kiểm tra credential hết hạn lúc nào?

Với username/password sử dụng `DaoAuthenticationProvider`, luồng cơ bản:

```text
HTTP login request
    ↓
UsernamePasswordAuthenticationToken (unauthenticated)
    ↓
AuthenticationManager / ProviderManager
    ↓
DaoAuthenticationProvider
    ├── UserDetailsService.loadUserByUsername(username)
    │      → UserDetails chứa password hash, authorities, account flags
    ├── các kiểm tra trạng thái tài khoản (locked/enabled/account expired)
    ├── kiểm tra raw password với PasswordEncoder
    ├── post-authentication check: isCredentialsNonExpired()
    │      ├── true  → tạo Authentication thành công
    │      └── false → throw CredentialsExpiredException
    ↓
Authentication success hoặc AuthenticationException
    ↓
Filter tiếp tục theo nhánh success hoặc failure
```

Mô tả trên trình bày **ngữ nghĩa thành công/thất bại**, không cam kết thứ tự nội bộ tuyệt đối của mọi bản vá/implementation. Một số bản Spring Security đã thay đổi cách thực hiện kiểm tra credential để giảm sai lệch thời gian và rò rỉ thông tin; nên kiểm tra source của đúng bản đang dùng khi debug chi tiết.

Điểm chắc chắn với provider mặc định: khi credential bị xác định hết hạn và không có cơ chế custom thay thế, **không trả kết quả Authentication thành công**. `CredentialsExpiredException` là một `AccountStatusException`; `ProviderManager` xử lý nhóm lỗi account-status theo hướng **dừng việc thử provider khác**, không cho một provider yếu hơn tự động “cứu” tài khoản bị hết hạn credential.

**Hệ quả khi dùng form login:** `AuthenticationSuccessHandler` **không được chạy** cho một lần xác thực bị `CredentialsExpiredException` từ chối. Nếu cần điều hướng UI, hãy xử lý phù hợp trong `AuthenticationFailureHandler` hoặc có một quy trình riêng cho tài khoản phải đổi credential. Nhưng redirect tới trang đổi mật khẩu **không làm request đó trở thành authenticated**.

### getCredentials() khác isCredentialsNonExpired()

- `Authentication.getCredentials()`: giá trị bằng chứng mà request đưa ra (mật khẩu, token...), có thể bị xóa sau xác thực thành công.
- `UserDetails.getPassword()`: thường là **hash được lưu** để `PasswordEncoder.matches(...)` kiểm tra.
- `UserDetails.isCredentialsNonExpired()`: **cờ chính sách** cho biết thông tin xác thực còn hợp lệ hay không.

Không suy ra credential hết hạn bằng việc thấy `Authentication.getCredentials() == null`; null có thể chỉ do xóa secret sau login. Cũng không dùng việc hash có tồn tại làm bằng chứng rằng password vẫn còn trong thời hạn.

## 4. Chính sách hết hạn: quy định từ ứng dụng, không phải từ getter

Một hệ thống có thể chọn các trường dữ liệu sau:

| Trường trong bảng account | Ý nghĩa | Thường có cần? |
| --- | --- | --- |
| `password_hash` | Hash mật khẩu hiện tại; không lưu plaintext | Có với password login |
| `password_changed_at` | Thời điểm credential cuối cùng được đổi | Cần nếu dùng thời hạn tính từ lần đổi |
| `password_expires_at` | Thời điểm hết hạn đã tính hoặc được chỉ định | Hữu ích khi chính sách theo từng tài khoản |
| `must_change_password` | Bắt buộc đổi ngay ở quy trình kế tiếp | Có cho mật khẩu tạm/administrator reset |
| `enabled`, `locked` | Trạng thái tài khoản độc lập với hết hạn password | Theo chính sách tổ chức |
| `security_version` / `credentials_version` | Phiên bản dùng để nhận biết session/token lỗi thời | Hữu ích cho thu hồi, cần cơ chế kiểm tra |
| `password_history` (nếu có) | Ngăn dùng lại mật khẩu theo yêu cầu chính sách | Thiết kế riêng, bảo vệ các hash |

Hai cách triển khai phổ biến:

1. **Lưu `password_expires_at`:** việc hết hạn dựa trên mốc đã được xác định; cập nhật mốc khi đổi mật khẩu hoặc đổi chính sách. Nếu null, phải quy định rõ là “không hết hạn” hay “chưa cấu hình”.
2. **Tính từ `password_changed_at`:** ví dụ hạn 90 ngày. Nếu chưa có thời điểm đổi mật khẩu, phải áp dụng chính sách cụ thể — có hệ thống bắt buộc đổi, có hệ thống nhập dữ liệu migrate với mốc riêng.

Không dùng `account.updated_at` nếu nó thay đổi mỗi khi người dùng sửa ảnh đại diện hoặc email; làm vậy có thể vô tình **kéo dài hạn mật khẩu** mà người dùng không hề đổi mật khẩu.

### Công thức hết hạn theo thời gian

Giả sử thời điểm hiện tại là `now`, credential hết hạn khi:

```text
credentialsExpired =
    mustChangePassword
    OR (
        passwordExpiresAt is not null
        AND now >= passwordExpiresAt
    )
```

Trong Java 17:

```java
boolean expired = account.isMustChangePassword()
        || (account.getPasswordExpiresAt() != null
            && !clock.instant().isBefore(account.getPasswordExpiresAt()));

boolean credentialsNonExpired = !expired;
```

Đây là snippet giả định entity và `Clock` đã được khai báo, không phải chương trình độc lập. `!now.isBefore(expiresAt)` bao gồm **đúng khoảnh khắc đến hạn**, tránh sai lệch do `now.isAfter(expiresAt)` chỉ từ chối sau mốc một khoảng.

**Nên dùng `Instant`/UTC** ở tầng lưu và so sánh, tiêm `Clock` để test thời điểm biên. Không so sánh chuỗi ngày theo timezone của trình duyệt hoặc dùng `LocalDateTime.now()` không có quy ước rõ ràng. Với quy định “đến cuối ngày” phải chỉ rõ timezone nghiệp vụ và chuyển thành một `Instant` duy nhất.

### Chính sách “bắt đổi mật khẩu” có giống “hết hạn” không?

Không luôn giống. `must_change_password=true` có thể là một nghĩa vụ cần thực hiện, nhưng ứng dụng phải chọn **hành vi**:

- Nếu **không cho authenticated login bình thường**: có thể ánh xạ sang `isCredentialsNonExpired() == false`, rồi dẫn người dùng đến **quy trình recovery/đổi credential riêng**.
- Nếu muốn **đã xác minh danh tính, nhưng chỉ truy cập endpoint đổi mật khẩu**: thiết kế một authentication giới hạn hoặc một session/challenge riêng, bảo vệ toàn bộ endpoint khác. Chỉ đổi flag sang false **không tạo ra** limited session trong provider mặc định.

Trộn hai hướng này dễ tạo lỗ hổng: UI hiển thị “hãy đổi mật khẩu” nhưng backend vẫn cho phép truy cập API nhạy cảm vì còn `Authentication` cũ hoặc một manager khác xác thực thành công.

## 5. Ánh xạ đúng với UserDetails hoặc lớp User có sẵn

### 5.1. Dùng org.springframework.security.core.userdetails.User

Nếu dùng built-in `User`:

```java
UserDetails userDetails = User.withUsername(account.getUsername())
        .password(account.getPasswordHash())
        .authorities(account.getGrantedAuthorities())
        .disabled(!account.isEnabled())
        .accountLocked(account.isLocked())
        .accountExpired(account.isAccountExpired())
        .credentialsExpired(account.isMustChangePassword()
                || passwordExpiryPolicy.isExpired(account))
        .build();
```

Đây là snippet phụ thuộc `account`, `passwordExpiryPolicy` và các getter của domain model. Lưu ý builder nhận `.credentialsExpired(true)` khi credential **đã hết hạn**, trái với tên getter `isCredentialsNonExpired()`. Chỉ dùng authority từ nguồn tin cậy trong database, không lấy role client gửi lên.

### 5.2. Tự implement UserDetails

Custom principal cần override thật sự:

```java
@Override
public boolean isCredentialsNonExpired() {
    return !mustChangePassword
            && (passwordExpiresAt == null
                || clock.instant().isBefore(passwordExpiresAt));
}
```

Đoạn trên là **method trong class custom**, giả định ba field tồn tại và `clock` là dependency hợp lệ. Khi làm snapshot user cho session, không nên để `isCredentialsNonExpired()` truy vấn DB mỗi lần getter được gọi. Thường tốt hơn là **tính boolean tại thời điểm tải** ở `UserDetailsService`, đưa vào principal và giữ policy logic trong một lớp riêng có thể test.

Trong Spring Security 6.5, nếu bạn không override trạng thái custom thì giá trị mặc định có thể là `true`; một mật khẩu hết hạn trong DB không tự đổi được hành vi xác thực. Test explicit cho từng trạng thái, đặc biệt khi migrate account cũ hoặc đổi cách tính expiry.

### 5.3. Một phương thức service tải user từ DB

```java
@Service
public final class DbUserDetailsService implements UserDetailsService {
    private final AccountRepository accounts;
    private final PasswordExpiryPolicy policy;

    public DbUserDetailsService(
            AccountRepository accounts, PasswordExpiryPolicy policy) {
        this.accounts = accounts;
        this.policy = policy;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AccountEntity account = accounts.findByUsername(username)
                .orElseThrow(() -> new UsernameNotFoundException(
                        "Account not found"));

        boolean expired = policy.isExpired(account);

        return User.withUsername(account.getUsername())
                .password(account.getPasswordHash())
                .authorities(account.getAuthorities())
                .disabled(!account.isEnabled())
                .accountLocked(account.isLocked())
                .credentialsExpired(expired)
                .build();
    }
}
```

Đây là **mẫu tích hợp**, cần tự triển khai `AccountRepository`, `AccountEntity`, `PasswordExpiryPolicy` và imports. Nó không chạy độc lập. Mục tiêu là chỉ ra rõ nguồn dữ liệu, vị trí tính chính sách và chỗ ánh xạ sang `User` mặc định. `DaoAuthenticationProvider` vẫn là nơi kiểm tra password hash thông qua `PasswordEncoder`; đừng tự gọi `matches(...)` trong `UserDetailsService` để tự “cho qua” cờ hết hạn.

## 6. Ví dụ Java 17+ có thể chạy: hết hạn, thất bại và sau đổi mật khẩu

Bài demo dùng Spring Security **core** không cần web server. Nó mô phỏng một kho account trong bộ nhớ, quy tắc **90 ngày**, và dùng **`DaoAuthenticationProvider` + `ProviderManager` thật**. Kết quả cho thấy password cũ đúng nhưng đã hết hạn vẫn thất bại; sau khi **mô phỏng một quy trình recovery đã được xác minh ở bên ngoài**, password cũ không còn dùng được, password mới xác thực thành công.

**Giới hạn an toàn:** hàm mô phỏng cập nhật account **không thực hiện kiểm chứng danh tính/one-time recovery token**. Trong production, chỉ gọi cập nhật sau khi đã xác minh proof qua quy trình an toàn ở mục 8; không xuất hàm cập nhật thành endpoint công khai chỉ nhận username/password mới.

### 6.1. Cấu trúc project

```text
credentials-expired-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/CredentialsExpiredDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'credentials-expired-demo'
```

`build.gradle`:

```groovy
plugins {
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
}

application {
    mainClass = 'demo.CredentialsExpiredDemo'
}
```

Tạo `src/main/java/demo/CredentialsExpiredDemo.java`:

```java
package demo;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.CredentialsExpiredException;
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

public class CredentialsExpiredDemo {

    private static final PasswordEncoder ENCODER = new BCryptPasswordEncoder();

    // Đồng hồ cố định để chạy ở năm nào vẫn cho kết quả giống nhau.
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-11-05T00:00:00Z"), ZoneOffset.UTC);

    // Thay thế DB bằng kho in-memory chỉ dùng cho demo.
    private static final AtomicReference<StoredAccount> ACCOUNT =
            new AtomicReference<>(new StoredAccount(
                    "mai",
                    ENCODER.encode("old-pass-123"),
                    Instant.parse("2026-07-01T00:00:00Z"),
                    false,
                    true));

    private record StoredAccount(
            String username,
            String passwordHash,
            Instant passwordChangedAt,
            boolean mustChangePassword,
            boolean enabled) {}

    private static final UserDetailsService USERS = username -> {
        StoredAccount account = ACCOUNT.get();
        if (!account.username().equals(username)) {
            throw new UsernameNotFoundException("Account not found");
        }

        Instant expiresAt = account.passwordChangedAt()
                .plus(Duration.ofDays(90));

        boolean expired = account.mustChangePassword()
                || !CLOCK.instant().isBefore(expiresAt);

        // User.UserBuilder nhận cờ "expired"; getter trả "non-expired".
        return User.withUsername(account.username())
                .password(account.passwordHash())
                .roles("READER")
                .disabled(!account.enabled())
                .credentialsExpired(expired)
                .build();
    };

    public static void main(String[] args) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(USERS);
        provider.setPasswordEncoder(ENCODER);

        AuthenticationManager manager = new ProviderManager(provider);

        login(manager, "before", "old-pass-123");
        login(manager, "wrong", "wrong-password");

        // Chỉ mô phỏng hành động ĐÃ có proof recovery được xác minh.
        // Ví dụ này KHÔNG triển khai endpoint khôi phục mật khẩu.
        simulateVerifiedRecoveryUpdate();

        login(manager, "old", "old-pass-123");
        login(manager, "after", "new-pass-456");
    }

    private static void login(
            AuthenticationManager manager,
            String label,
            String rawPassword) {
        try {
            Authentication result = manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "mai", rawPassword));

            String authorities = result.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .collect(Collectors.joining(","));

            String credentialsState =
                    result.getCredentials() == null ? "absent" : "present";

            System.out.printf(
                    "%s: authenticated=%s; name=%s; authorities=%s;"
                            + " credentials=%s%n",
                    label,
                    result.isAuthenticated(),
                    result.getName(),
                    authorities,
                    credentialsState);
        } catch (CredentialsExpiredException ex) {
            System.out.println(label + ": CredentialsExpiredException");
        } catch (BadCredentialsException ex) {
            System.out.println(label + ": BadCredentialsException");
        }
    }

    private static void simulateVerifiedRecoveryUpdate() {
        StoredAccount original = ACCOUNT.get();

        StoredAccount replacement = new StoredAccount(
                original.username(),
                ENCODER.encode("new-pass-456"),
                CLOCK.instant(),
                false, // phải xóa cờ yêu cầu đổi credential
                original.enabled());

        ACCOUNT.set(replacement);
    }
}
```

Tại thư mục project, chạy với Gradle tương thích Java 17:

```bash
gradle run
```

Nếu có Gradle Wrapper, dùng `./gradlew run` trên macOS/Linux hoặc `gradlew.bat run` trên Windows.

**Stdout chính của chương trình** (không tính log do Gradle in):

```text
before: CredentialsExpiredException
wrong: BadCredentialsException
old: BadCredentialsException
after: authenticated=true; name=mai; authorities=ROLE_READER; credentials=absent
```

### 6.2. Vì sao output như vậy?

- `passwordChangedAt = 2026-07-01`, đồng hồ demo ở `2026-11-05`, hạn **90 ngày** đã qua. Mật khẩu đúng `old-pass-123` vẫn bị `CredentialsExpiredException`.
- Gửi `wrong-password` không khớp BCrypt hash, vì vậy `BadCredentialsException`. Việc account cũng có credential hết hạn không có nghĩa mọi request đều trả duy nhất một exception; kết quả phụ thuộc bước nào phát hiện điều kiện thất bại và chính sách provider.
- Hàm `simulateVerifiedRecoveryUpdate()` thay hash bằng hash của password mới, cập nhật mốc thời gian và xóa flag yêu cầu đổi. Đây là **bước dữ liệu sau xác minh**; bản thân hàm không xác minh người dùng.
- Password cũ sau đó không còn khớp hash → `BadCredentialsException`.
- Password mới khớp, chưa hết hạn và account enabled → manager trả `Authentication` đã xác thực với `ROLE_READER`.
- `credentials=absent` chỉ nói secret không nằm trong kết quả theo flow chuẩn sau khi Spring Security thực hiện cleanup; không phải mật khẩu được trả về hoặc có thể lấy lại.

Không in raw password, hash hoặc object `Authentication` đầy đủ trong stdout. Bài không thực hiện HTTP recovery nên không có chuyện tự mở quyền cho user có credential hết hạn.

### 6.3. Thử đổi điều kiện

1. Đổi thời điểm `passwordChangedAt` thành `2026-11-01`, giữ `mustChangePassword=false`: lần thử `before` sẽ xác thực thành công.
2. Giữ thời điểm mới nhưng chuyển `mustChangePassword=true`: `before` vẫn bị `CredentialsExpiredException`.
3. Đặt `enabled=false`: xác thực bị từ chối bởi trạng thái disabled. Nếu viết test tự động cần assert theo đúng nhánh account-status của provider/phiên bản.
4. Đổi độ dài policy 90 ngày thành 30 ngày: ngày hết hạn thay đổi. Không nên hardcode thời hạn trong mọi repository hay controller; đặt ở policy service/config.
5. Đặt `expiresAt == now` trong một hàm test policy: kết quả phải là expired nếu quy định “đến hạn là hết hiệu lực”.

**Lưu ý:** không dùng `Clock.fixed(...)` trong sản phẩm thật vì password sẽ không bao giờ “già đi” theo thời gian hệ thống; ở production inject `Clock.systemUTC()` hoặc dịch vụ thời gian được vận hành phù hợp.

## 7. Hai hướng xử lý “phải đổi mật khẩu” và hệ quả bảo mật

Đề bài thường dẫn tới câu hỏi: “Credential đã hết hạn thì làm cách nào người dùng đổi được mật khẩu nếu chính màn hình đổi mật khẩu lại yêu cầu authenticated login?”

Có hai hướng kiến trúc. **Đừng vô tình trộn chúng.**

### Hướng A — Từ chối đăng nhập bình thường và dùng recovery flow riêng

Đây là cách tự nhiên với `isCredentialsNonExpired() == false`:

```text
User gửi username + password
     ↓
DaoAuthenticationProvider kiểm tra credential
     ↓
CredentialsExpiredException
     ↓
AuthenticationFailureHandler (không có authenticated session mới)
     ↓
Trang hướng dẫn khôi phục / thiết lập lại password
     ↓
User chứng minh quyền kiểm soát tài khoản bằng recovery proof
     (one-time token / MFA / kênh đã xác minh, theo chính sách)
     ↓
Server kiểm tra token/challenge + thời hạn + trạng thái
     ↓
Server đổi hash + đặt passwordChangedAt + xóa mustChangePassword
     + xử lý revocation các session/token liên quan
     ↓
User đăng nhập lại bằng password mới
```

**Ưu điểm:** không cần tạo một `Authentication` cấp quyền tạm trong login chính, tách biệt ranh giới “đã xác minh quyền khôi phục” với “được truy cập ứng dụng”.

**Điểm cần thiết kế:** recovery token phải ngẫu nhiên đủ entropy, hết hạn nhanh, chỉ dùng một lần, được lưu dạng hash hoặc đại diện không lộ secret, gắn với đúng tài khoản và bị vô hiệu khi hoàn tất. Response yêu cầu recovery phải hạn chế rò rỉ “username/email này tồn tại không”, có rate limit, audit và kiểm soát brute force. Token không được ghi vào log hay lộ qua Referrer/URL bên thứ ba. Các endpoint nhận cookie cần CSRF protection phù hợp.

Một redirect từ `AuthenticationFailureHandler` sang `/account/recovery` chỉ là **hướng dẫn giao diện**, không chứng minh danh tính và không cho phép đổi mật khẩu ngay bằng username tự khai.

### Hướng B — Xác minh password rồi cấp một trạng thái truy cập giới hạn

Một số tổ chức yêu cầu user nhập mật khẩu cũ, sau đó ngay lập tức đổi mật khẩu mà **chưa được sử dụng phần còn lại của ứng dụng**. Điều này cần một quy trình **authentication riêng được thiết kế có chủ đích**, chẳng hạn provider/challenge xác minh password và trả một trạng thái hạn chế với authority riêng, expiry ngắn và policy deny-by-default.

```text
Input current password
    ↓
Verifier đáng tin xác minh password, account state, MFA/risk
    ↓
Tạo short-lived restricted session/challenge
    ↓
Chỉ cho phép POST /credentials/change và logout
    ↓
Đổi credential an toàn, hủy challenge, yêu cầu login lại
```

**Cảnh báo thiết kế:** nếu restricted identity vẫn có `Authentication.isAuthenticated() == true`, mọi endpoint đang dùng mỗi `authenticated()` **có thể coi identity này là đủ điều kiện**. Không chỉ gắn `ROLE_PASSWORD_CHANGE_REQUIRED` rồi hi vọng user bị hạn chế. Hãy ràng buộc đúng token type/authority, matcher, endpoint và default-deny; kiểm thử không thể gọi API thông thường, refresh token, quản lý user khác hoặc truy cập tài nguyên nhạy cảm.

Không tự gọi `setAuthenticated(true)` trong controller rồi nhét full user authorities vào `SecurityContext`. Đó là bỏ qua ranh giới tin cậy. Một flow giới hạn cần cơ chế kiểm tra credential và phát hành session/challenge được kiểm toán riêng.

### Bảng so sánh

| Tiêu chí | Recovery tách rời | Restricted change session |
| --- | --- | --- |
| `DaoAuthenticationProvider` mặc định với expired credential | Trả lỗi như thiết kế | Cần bổ sung flow riêng, không có sẵn |
| Có full authenticated login trước khi đổi? | Không | **Không**; chỉ có trạng thái hạn chế |
| Bằng chứng cần dùng | Recovery token/challenge đáng tin | Current password đã kiểm chứng và các yếu tố bổ sung |
| Nguy cơ lớn | Token khôi phục bị đánh cắp/lặp lại | Restricted session vô tình qua được `authenticated()` |
| Sau khi đổi | Hủy recovery token, cập nhật DB, đăng nhập lại | Hủy restricted state, đăng nhập lại |
| Phù hợp | Quên password, mật khẩu tạm, bắt đổi sau sự cố | UX đổi lần đầu sau kiểm tra credential, trong chính sách riêng |

Không có một flag đơn lẻ nào trên `UserDetails` quyết định đầy đủ quy trình này. Flag chỉ mô tả **trạng thái credentials** cho provider.

## 8. Chi tiết bắt buộc của luồng đổi/khôi phục mật khẩu

### 8.1. Xác minh người yêu cầu đổi credential

Tùy flow:

- **Đã đăng nhập bình thường, muốn đổi mật khẩu:** cần chính sách reauthentication/step-up phù hợp, thường kiểm tra current password và có thể MFA. Không chỉ dựa vào việc trình duyệt đang có session cũ.
- **Quên mật khẩu hoặc credential đã hết hạn và không thể đăng nhập:** dùng recovery challenge hoặc token từ kênh đã xác minh; không yêu cầu một `SecurityContext` authenticated mà user không thể tạo được.
- **Bắt đổi từ password tạm:** có thể phát hành recovery setup token một lần ngay tại lúc cấp tài khoản; hoặc triển khai restricted authentication nghiêm ngặt. Không gửi mật khẩu tạm cố định chung cho nhiều người.

Không bao giờ cho phép `POST /reset-password` chỉ nhận `username` và `newPassword` mà không có proof đáng tin. Cũng không tin `userId` hoặc `email` do client gửi làm bằng chứng chủ sở hữu tài khoản.

### 8.2. Kiểm tra password mới

Áp dụng chính sách password được tổ chức phê duyệt: độ dài tối thiểu hợp lý, chặn password đã bị rò rỉ, khuyến khích passphrase, hỗ trợ trình quản lý mật khẩu, không chứa credential trong log, không rút ngắn một cách âm thầm. Nếu cần lịch sử mật khẩu, so sánh password mới với các hash lưu trong lịch sử theo thuật toán phù hợp; không lưu plaintext để kiểm tra trùng.

Dùng `PasswordEncoder` đã cấu hình; ví dụ:

```java
String newHash = passwordEncoder.encode(newRawPassword);
// Lưu newHash; không ghi newRawPassword vào DB, log hay audit event.
```

Đây là snippet cần một `PasswordEncoder` đáng tin và dữ liệu đã qua validation. Không tự viết SHA-256 thuần hoặc mã hóa reversible làm phương thức lưu mật khẩu.

**`PasswordEncoder.upgradeEncoding(...)`** và `UserDetailsPasswordService` liên quan việc **nâng cấp thuật toán/hash** sau khi một credential được kiểm chứng; nó **không phải** cờ “mật khẩu đã quá 90 ngày”. Đừng đổi `isCredentialsNonExpired` dựa trên việc BCrypt cost hoặc prefix của hash có mới hay cũ.

### 8.3. Cập nhật DB phải nhất quán

Trong một transaction hoặc một thao tác update có kiểm soát, cần:

1. Xác minh recovery proof vẫn còn hiệu lực và chưa bị dùng.
2. Cập nhật `password_hash` bằng hash mới.
3. Cập nhật `password_changed_at = now` hoặc `password_expires_at` theo policy mới.
4. Đặt `must_change_password = false` / cờ credential expired tương ứng về trạng thái hợp lệ.
5. Tăng version security nếu hệ thống dựa vào version để vô hiệu hóa snapshot.
6. Đánh dấu recovery token đã tiêu thụ; không cho dùng lại.
7. Ghi audit event không chứa password hoặc recovery token.

SQL minh họa (**schema giả định**, cần bảo đảm token đã được xác minh và transaction bao quanh các bước):

```sql
UPDATE app_account
SET password_hash = :new_hash,
    password_changed_at = :now_utc,
    must_change_password = FALSE,
    security_version = security_version + 1
WHERE id = :account_id
  AND enabled = TRUE;
```

Đây không phải phép kiểm tra authorization đầy đủ: điều kiện `account_id` chỉ xác định record, còn bằng chứng quyền đổi mật khẩu phải được xác minh **trước và trong transaction**. Nếu có đổi password đồng thời, dùng version/optimistic locking hoặc row lock để tránh cập nhật chồng nhau. Nếu cập nhật tài khoản thành công nhưng recovery token không bị tiêu thụ, bạn có nguy cơ cho token cũ được dùng lại.

### 8.4. Thu hồi hoặc làm mới các trạng thái xác thực cũ

Đổi password không đồng nghĩa mọi session, remember-me token, JWT, refresh token hoặc API key đã bị thu hồi ngay. Cần quy tắc theo từng công nghệ:

- Invalidate các HTTP session còn sống hoặc dùng cơ chế phân tán như Spring Session khi cần.
- Revoke/rotate refresh token và remember-me token nếu chính sách yêu cầu.
- Với access token JWT tự chứa, không thể ép mọi token đã phát hành hết hiệu lực tức thì nếu API chỉ kiểm tra chữ ký + `exp` mà không có revocation/version check. Chọn TTL ngắn, introspection hoặc denylist/version phù hợp.
- Cập nhật/evict `UserDetails` cache nếu có; stale cache có thể vẫn giữ cờ expired và hash cũ.
- Không để restricted recovery session được nâng thành full session mà không qua xác thực và quản lý session fixation phù hợp.

Hãy xác định rõ “đổi mật khẩu có đăng xuất các thiết bị khác không?” và test đúng yêu cầu. Không khẳng định Spring Security tự động thu hồi mọi credential bên ngoài chỉ vì cập nhật một field DB.

### 8.5. Phản hồi, audit và chống rò rỉ thông tin

Không trả chi tiết account status một cách thiếu kiểm soát. Ví dụ form login thông thường nên hiển thị thông báo chung khi credential sai, account không tồn tại hoặc bị khóa, trừ khi chính sách và ranh giới UI cho phép thông báo có kiểm soát sau khi đã chứng minh quyền sở hữu.

- Rate limit login và recovery challenge; giới hạn số lần thử token.
- Không log `Authorization` header, plaintext password, recovery token, session ID hoặc `Authentication.getCredentials()`.
- Chỉ lưu audit metadata cần thiết như account ID nội bộ, loại sự kiện, thời điểm, correlation ID và kết quả.
- Dùng HTTPS, cookie an toàn, CSRF protection cho state-changing browser endpoints và referrer policy khi chứa token trong URL.
- Khi gửi email “đổi mật khẩu thành công”, không nhúng secret và có hướng xử lý nếu người dùng không thực hiện yêu cầu.

## 9. Tích hợp Spring MVC: form login và AuthenticationFailureHandler

Nếu bạn dùng `formLogin(...)`, một lần đăng nhập thất bại do `CredentialsExpiredException` đi tới **failure handler**, không phải success handler. Một handler có thể dẫn người dùng đến trang giải thích cách khôi phục.

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers(
                    "/login",
                    "/account/recovery",
                    "/account/recovery/request",
                    "/account/recovery/confirm")
            .permitAll()
            .anyRequest()
            .authenticated())
        .formLogin(form -> form
            .loginPage("/login")
            .failureHandler((request, response, exception) -> {
                if (exception instanceof CredentialsExpiredException) {
                    response.sendRedirect(
                            request.getContextPath() + "/account/recovery");
                } else {
                    response.sendRedirect(
                            request.getContextPath() + "/login?error");
                }
            }));
    return http.build();
}
```

**Đây là snippet cấu hình**, cần imports, `@Configuration`, các controller/route recovery, `UserDetailsService`, password encoder và chính sách bảo mật đầy đủ. Không dán riêng vào project rồi coi là có recovery flow hoạt động. Redirect `/account/recovery` là tới **một trang bắt đầu quy trình công khai an toàn**; trang đó không được cho phép đổi password chỉ nhờ username mà client khai.

**Chú ý bảo mật:**

- `permitAll()` cho recovery endpoint **không có nghĩa bỏ proof**. Endpoint xử lý phải xác minh one-time token hoặc challenge trước khi thay password.
- Với POST ở trình duyệt, CSRF protection mặc định cần được giữ hoặc thay bằng cơ chế bảo vệ tương đương có căn cứ; tránh tắt CSRF toàn cục chỉ để form submit được.
- Đối với API không dùng form login, filter/entry point có thể trả HTTP 401/JSON thay vì redirect; không trả một full authenticated token khi expired.
- Nếu trình duyệt đã có session authenticated trước khi credential hết hạn, failure handler **không tự chạy trên mỗi request**. Cần thiết kế logic revalidation/revocation riêng nếu yêu cầu hết hạn có hiệu lực giữa phiên.
- Không dùng `.anyRequest().authenticated()` làm rule duy nhất cho **restricted session** theo hướng B; `authenticated()` có thể cho phép một principal đã được xác minh nhưng chỉ có authority đổi password truy cập quá rộng.

### Login failure và password-change completion khác nhau

```text
Login FAILURE do CredentialsExpiredException
   → không có full user Authentication mới
   → bắt đầu recovery/challenge (không cấp quyền ứng dụng)

Password CHANGE đã xác minh
   → cập nhật hash + flags + mốc + token consumption
   → invalidate session/recovery token
   → hướng dẫn user đăng nhập lại

Login SUCCESS sau khi đổi
   → provider đọc UserDetails mới
   → PasswordEncoder kiểm tra hash mới
   → isCredentialsNonExpired() == true
   → full Authentication theo quyền hợp lệ
```

Không gọi controller đổi password bên trong `AuthenticationSuccessHandler` để “tự sửa trạng thái”. Chuyển cờ credential expired về false mà không đổi hash hoặc không có proof là phá vỡ chính sách hết hạn.

## 10. Trạng thái phiên, cache và hiệu lực của thay đổi

### 10.1. Cờ expired không được kiểm tra lại trên mọi request theo mặc định

Trong session-based login:

```text
Ngày 1: login thành công → SecurityContext trong session
Ngày 2: passwordExpiresAt đã qua
Ngày 2: request dùng lại session → có thể vẫn có Authentication cũ
       mà không gọi lại DaoAuthenticationProvider / UserDetailsService
```

Vì vậy nếu chính sách yêu cầu “sau thời hạn, cấm mọi thao tác cho đến khi đổi”, chỉ kiểm tra `isCredentialsNonExpired` **lúc login** là chưa đủ. Cần kiểm tra phiên bản danh tính, hết hạn session, policy filter/authorization hoặc thu hồi session theo thiết kế. Việc kiểm tra mọi request với DB làm tăng tải; cần cân nhắc cache có TTL ngắn, event-driven invalidation hoặc version check.

### 10.2. Cache UserDetails có thể lưu flag lỗi thời

Nếu `UserDetailsService` có cache, sau một recovery thành công cần xóa cache của account, nếu không `isCredentialsNonExpired()` có thể vẫn trả false và password hash trong cache vẫn là bản cũ. Ngược lại, khi admin đặt `must_change_password=true`, cache cũ có thể còn trả true khiến một lần đăng nhập khác vượt qua policy.

`ProviderManager` mặc định có hành vi erase credentials ở authentication result hỗ trợ `CredentialsContainer`. Nếu cache và principal giữ cùng một object `UserDetails`, thao tác xóa có thể sửa password hash trong cached instance, gây lỗi lần đăng nhập kế tiếp. Đặt nguyên tắc **độc lập object snapshot, cache invalidation và bảo vệ secret** rõ ràng; không tự tắt credential erasure như một “fix” mặc định.

### 10.3. Các API/token không nhất thiết dựa trên UserDetails

Một Spring Security OAuth2 Resource Server nhận JWT thường xác minh chữ ký, issuer, audience, `exp` và các claims theo cấu hình, rồi tạo `JwtAuthenticationToken`. Nó **không mặc định** đọc `password_changed_at` và `isCredentialsNonExpired` từ DB. Nếu policy yêu cầu password reset vô hiệu hóa token, phải liên kết token với thời điểm/version credential hoặc sử dụng revocation/introspection có kiểm soát.

Tương tự, OIDC Login, SAML, passkey/WebAuthn và service API key có trạng thái credential riêng. Đừng áp dụng hạn password 90 ngày cho mọi loại credential chỉ vì tất cả đều nằm trong mô-đun Authentication.

## 11. Các trường hợp biên và quy tắc kiểm thử

### Ma trận hành vi chính

| Điều kiện | Kết quả dự kiến trong flow `DaoAuthenticationProvider` | Cần kiểm tra thêm |
| --- | --- | --- |
| Password đúng, chưa hết hạn | Authentication thành công nếu các flag khác hợp lệ | Authorities, principal và erase credentials |
| Password đúng, `isCredentialsNonExpired=false` | `CredentialsExpiredException` | Không có full authenticated session mới |
| Password sai, credential chưa hết hạn | `BadCredentialsException` | Không tiết lộ account tồn tại |
| Password sai, account credential đã hết hạn | Authentication thất bại; exception cụ thể theo cơ chế kiểm tra | Không tự cho quyền recovery |
| `mustChangePassword=true` và chưa quá 90 ngày | Credential vẫn bị coi hết hạn nếu policy OR hai điều kiện | Không bỏ cờ must-change |
| `now == expiresAt` | Hết hạn nếu chính sách là đến hạn thì hết hiệu lực | Test `Clock.fixed(...)` |
| `now` trước hạn một millisecond | Chưa hết hạn | Không bị lỗi so sánh timezone |
| `passwordExpiresAt=null` | Theo chính sách dự án | Không tự đoán null là bất kỳ trạng thái nào |
| Account disabled/locked | Từ chối theo trạng thái account | Không cho reset tự mở khóa nếu chính sách cấm |
| Đổi hash nhưng quên xóa must-change | Vẫn không login được | Transaction cập nhật nhiều field |
| Xóa must-change nhưng quên đổi hash | Có thể chấp nhận credential cũ, sai chính sách | Kiểm tra invariants trong service |
| Token recovery đã dùng lại | Từ chối | Token consumption atomic và replay prevention |
| Đã có session trước khi password hết hạn | Có thể còn authenticated theo session | Test session revocation/revalidation |
| JWT được phát hành trước khi đổi password | Có thể còn hợp lệ đến `exp` nếu không có revocation | Xác định chính sách JWT |
| UserDetails cache đã cũ | Có thể login thất bại hoặc chấp nhận flag cũ | Evict cache/version |

### Test policy bằng Clock

Một helper thuần Java có thể được dùng để test thời điểm biên:

```java
static boolean credentialsExpired(
        Instant now,
        Instant expiresAt,
        boolean mustChange) {
    return mustChange
            || (expiresAt != null && !now.isBefore(expiresAt));
}
```

**Snippet nằm trong một class Java**, không chạy độc lập. Viết unit test cho `now = expiresAt.minusNanos(1)` (false), `now = expiresAt` (true), `now = expiresAt.plusNanos(1)` (true) và `mustChange=true` (true dù trước hạn). Test với timezone là kiểm tra cách **tạo `Instant`** chứ không thay đổi cách so sánh `Instant`.

### Test integration thực sự

Nên có test sử dụng manager/provider thật thay vì chỉ `@WithMockUser`:

1. `UserDetailsService` trả account còn hạn, password đúng → xác thực thành công.
2. Account đã hết hạn, password đúng → `CredentialsExpiredException` từ manager; không có success handler.
3. Account đã hết hạn, password sai → thất bại an toàn.
4. Recovery token sai/hết hạn/đã dùng → không đổi hash.
5. Recovery token hợp lệ → hash và cờ/mốc cập nhật đúng transaction; token không dùng lại được.
6. Mật khẩu cũ thất bại sau reset, mật khẩu mới được chấp nhận.
7. Với browser, thử bỏ CSRF token và thử replay reset request.
8. Với session đã authenticated, thử qua thời điểm expiry và thay credential; kết quả theo chính sách revalidation.
9. Với restricted change session, kiểm tra mọi endpoint ngoài allowlist bị từ chối, kể cả endpoint chỉ yêu cầu `authenticated()`.
10. Nếu có cache, thử sau evict và sau role/password state change.

**`@WithMockUser` không kiểm tra password hash, `isCredentialsNonExpired` hay `DaoAuthenticationProvider`.** Nó mô phỏng một principal đã xác thực; dùng tốt cho authorization test nhưng không thay thế flow authentication và recovery test.

## 12. Lỗi thường gặp

1. **Đảo ngữ nghĩa boolean:** DB `credentialsExpired=true` mà custom `isCredentialsNonExpired()` cũng trả true. Phải đảo khi ánh xạ.
2. **Không override custom getter:** policy DB có dữ liệu hết hạn nhưng `UserDetails` trả mặc định true.
3. **Cho rằng cờ false tự bật màn hình đổi mật khẩu:** provider ném exception; muốn recovery cần flow và UI riêng.
4. **Xử lý hết hạn trong success handler:** success handler không nhận request đã bị `CredentialsExpiredException`.
5. **Redirect sang reset page rồi tự coi username là verified:** redirect không cấp authentication hoặc ownership proof.
6. **Tạo recovery endpoint chỉ nhận user ID + password mới:** không có proof, mở đường chiếm đoạt account.
7. **Dùng restricted `Authentication` nhưng quên chặn endpoint `authenticated()`:** principal vẫn có thể qua rule quá rộng.
8. **Chỉ đổi `must_change_password=false` mà không thay hash:** vi phạm chính sách bắt đổi credential.
9. **Đổi hash nhưng không cập nhật mốc/cờ:** tài khoản vẫn bị coi expired, user không thể login.
10. **Không invalidate cache/UserDetails:** account có thể giữ status và password hash cũ.
11. **Tin rằng đổi password tự thu hồi session/JWT trên mọi máy:** session/token cần cơ chế revoke/version/TTL riêng.
12. **Lưu password mới dạng plaintext hoặc log raw credentials:** luôn dùng password encoder chuyên dụng và giữ secret ngoài log.
13. **Dùng `updated_at` của profile làm ngày đổi password:** đổi avatar/email vô tình kéo dài hạn credential.
14. **Đặt expiry theo timezone của client:** cùng một credential có thể được coi còn hạn/hết hạn khác nhau; chuẩn hóa UTC/Instant và policy rõ ràng.
15. **Không phân biệt password expiration với JWT expiration:** `isCredentialsNonExpired` không tự kiểm tra claim `exp`.
16. **Trộn locked/disabled với expired:** đặt lại password không tự cho phép bypass chính sách khóa hoặc vô hiệu hóa.
17. **Phát thông báo chi tiết trước khi xác minh đủ điều kiện:** có thể giúp enumeration/account-status probing.
18. **Tắt CSRF cho toàn bộ form login/recovery để “dễ submit”:** phải thiết kế bảo vệ state-changing request theo credential model.
19. **Dùng raw mật khẩu cũ trong session để đổi sau:** không cần và không được giữ secret như vậy; xác minh rồi xóa.
20. **Đặt flag expired trong frontend mà backend không kiểm tra:** UI không phải chốt bảo mật; provider/policy/service mới quyết định.

## 13. Bài tập thực hành

**Bài 1 — Hiểu getter.** Giải thích khi nào `isCredentialsNonExpired()` trả true/false; so sánh với `isAccountNonExpired()` và `isAccountNonLocked()`. Dự đoán exception cho password đúng nhưng credential hết hạn.

**Bài 2 — Chạy demo.** Dựng Gradle project ở mục 6, chạy `gradle run` và lý giải bốn dòng output: expired, wrong password, old password sau reset, new password thành công. Đổi ngày/thời hạn để quan sát sự thay đổi.

**Bài 3 — Viết policy.** Xây một `PasswordExpiryPolicy` dùng `Clock` inject, với `passwordExpiresAt` nullable và `mustChangePassword`. Test đúng mốc hết hạn và thời điểm trước đó một nanosecond.

**Bài 4 — Ánh xạ DB.** Thêm `password_hash`, `password_changed_at`, `must_change_password` và optional `security_version` vào account. Viết `UserDetailsService` trả `User.withUsername(...).credentialsExpired(...)`, không mã hóa lại hash cũ.

**Bài 5 — Chọn flow.** So sánh recovery token riêng với restricted change session. Với mỗi flow, chỉ rõ proof bắt buộc, endpoint được phép, điều kiện hết hạn token/challenge, session cleanup và điểm chặn user truy cập API bình thường.

**Bài 6 — Security test.** Tạo test chứng minh `AuthenticationFailureHandler` nhận `CredentialsExpiredException`; gọi endpoint nhạy cảm sau failure phải không được phép. Test reset token sai, expired, replay và concurrent reset.

**Bài 7 — Session/token.** Đăng nhập trước khi hết hạn, sau đó đổi flag expired trong DB. Trình bày vì sao user có thể vẫn gọi API theo một phiên cũ và đề xuất cơ chế revalidation/credential version phù hợp.

**Bài 8 — Incident.** Admin đặt `must_change_password=true` cho 100 tài khoản vì nguy cơ rò rỉ. Viết kế hoạch thông báo, challenge, rate-limit, audit, cache invalidation, session revocation và rollback an toàn. Không phát tán temporary password chung.

### Tiêu chí hoàn thành

Người học phải tự trả lời được:

- Getter `isCredentialsNonExpired()` mang nghĩa gì và tại sao builder `credentialsExpired(true)` lại dẫn tới getter false?
- Khi password đúng nhưng flag expired, `DaoAuthenticationProvider` thành công hay ném lỗi nào?
- Vì sao một `AuthenticationFailureHandler` có thể điều hướng UX nhưng không xác minh tài khoản để reset?
- Làm thế nào thiết kế recovery token/limited access mà không cấp quyền ứng dụng trước khi đổi password?
- Khi cập nhật password, cần thay đổi những field nào một cách nhất quán?
- Vì sao session, JWT và `UserDetails` cache có thể giữ trạng thái lỗi thời?
- Phải test những điều gì để không biến chính sách “bắt đổi mật khẩu” thành đường bypass xác thực?

## 14. Tài liệu chính thức

- [Spring Security 6.5.11 — UserDetails API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetails.html): hợp đồng `isCredentialsNonExpired()` và các cờ account.
- [Spring Security 6.5.11 — User.UserBuilder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html): `credentialsExpired(boolean)`, các builder flags.
- [Spring Security 6.5.11 — AbstractUserDetailsAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html): pre/post authentication checks và cấu hình người dùng.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): cách dùng `UserDetailsService` và `PasswordEncoder`.
- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager` và xử lý trạng thái xác thực.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): password hashing, encoder và nâng cấp hash.
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): filter, success/failure handler và cách định nghĩa trang đăng nhập.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): security context, session và kiểm soát vòng đời.
- [Spring Security — UserDetails Caching](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/caching.html): cache principal và credential erasure.

**Phiên bản:** ví dụ chạy dùng Spring Security Core 6.5.11/Java 17. Khi ứng dụng dùng Spring Boot 3.5, Spring Security 7, provider custom, JWT/OIDC hoặc WebFlux, hãy xác minh chính xác API/flow của bản tương ứng. Đặc biệt không gắn chính sách password expiry của `UserDetails` một cách máy móc vào token expiration hoặc authentication không dùng mật khẩu.