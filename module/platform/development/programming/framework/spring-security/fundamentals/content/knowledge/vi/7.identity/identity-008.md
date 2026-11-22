# Trạng thái khóa, vô hiệu hóa và hết hạn của tài khoản

Một người dùng có thể nhập **đúng mật khẩu** nhưng vẫn không được đăng nhập. Ví dụ, Mai nhập mật khẩu chính xác vào hệ thống nội bộ; tuy nhiên tài khoản của cô đang bị tạm khóa vì nhiều lần đăng nhập sai, bị quản trị viên vô hiệu hóa, hoặc đã hết thời hạn được phép sử dụng. Một trường hợp khác: tài khoản vẫn hoạt động nhưng **mật khẩu đã hết hạn** theo chính sách của tổ chức.

Spring Security phân biệt các tình huống này bằng những thuộc tính trạng thái của `UserDetails`. Các trạng thái ấy không đơn giản là “đăng nhập đúng hoặc sai” và cũng không đồng nghĩa với role hay quyền truy cập dữ liệu.

Bài này giúp bạn hiểu rõ **khóa tài khoản (locked)**, **vô hiệu hóa (disabled)**, **tài khoản hết hạn (account expired)** và **thông tin xác thực hết hạn (credentials expired)**; cách Spring Security kiểm tra chúng; cách ánh xạ dữ liệu nghiệp vụ; cách xử lý các phiên đã đăng nhập; và những lỗi bảo mật thường gặp.

Ví dụ dùng **Java 17+** và các lớp thực của Spring Security 7.1.2. Với dự án Spring Boot, nên sử dụng starter và phiên bản Spring Security do Boot BOM quản lý thay vì tự thêm phiên bản rời rạc.

## 1. Bốn câu hỏi khác nhau đối với cùng một người dùng

Giả sử cơ sở dữ liệu có tài khoản `mai`. Trước khi cho phép một lần xác thực bằng tên/mật khẩu, hệ thống có thể phải trả lời:

1. **Tài khoản có được kích hoạt không?** Tài khoản chưa xác minh hoặc bị quản trị viên cấm sử dụng có thể ở trạng thái disabled.
2. **Tài khoản có đang bị khóa không?** Một lệnh khóa tạm thời hoặc biện pháp phòng vệ chống thử mật khẩu có thể khiến account locked.
3. **Thời hạn tồn tại của tài khoản có còn không?** Tài khoản thời vụ hoặc quyền truy cập theo hợp đồng có thể hết hạn theo thời điểm được lưu.
4. **Bằng chứng đăng nhập có còn được chấp nhận không?** Mật khẩu có thể đã hết thời hạn hoặc phải được thay sau một sự kiện bảo mật.

Tất cả là **quy tắc riêng**. Một tài khoản có thể vừa disabled vừa locked; một tài khoản hết hạn có thể vẫn có mật khẩu đúng; một tài khoản đang active vẫn có mật khẩu hết hạn.

| Tình huống | Diễn giải | Thao tác quản lý thường gặp |
| --- | --- | --- |
| Locked | Tạm thời hoặc có điều kiện ngăn đăng nhập | Gỡ khóa khi hết hạn, sau xác minh hoặc theo quyết định quản trị |
| Disabled | Chủ thể không được phép dùng tài khoản | Kích hoạt sau xác minh; hoặc cấm vì quyết định quản trị |
| Account expired | Thời hạn sử dụng tài khoản đã qua | Gia hạn quyền sử dụng nếu được phê duyệt |
| Credentials expired | Mật khẩu hoặc bằng chứng tương ứng cần đổi/làm mới | Quy trình thay/reset mật khẩu được xác minh |
| Active, không có hạn chế | Các điều kiện trạng thái trên không cản trở login | Vẫn phải kiểm tra mật khẩu và quyền truy cập |

Các tên `LOCKED`, `DISABLED` và `EXPIRED` là **khái niệm**, không có nghĩa Spring Security tự tạo bảng SQL hoặc tự cập nhật trạng thái giúp bạn. Ứng dụng phải định nghĩa nguồn dữ liệu, thời điểm chuyển trạng thái và quy tắc mở lại phù hợp.

## 2. UserDetails có bốn cờ mang nghĩa phủ định

Trong Spring Security, `org.springframework.security.core.userdetails.UserDetails` mô tả dữ liệu của một user mà một số provider xác thực bằng tên/mật khẩu sử dụng. Bốn phương thức quan trọng:

~~~java
boolean isAccountNonLocked();
boolean isEnabled();
boolean isAccountNonExpired();
boolean isCredentialsNonExpired();
~~~

Hãy đọc kỹ **Non** trong tên phương thức: ba trong bốn cờ mang ý nghĩa **phủ định của tình trạng xấu**. Vì vậy giá trị `true` thông thường nghĩa là điều kiện ấy **đang cho phép** xác thực tiếp tục.

| Phương thức `UserDetails` | `true` nghĩa là | `false` nghĩa là | Exception trạng thái liên quan |
| --- | --- | --- | --- |
| `isAccountNonLocked()` | Tài khoản không bị khóa | Tài khoản bị khóa | `LockedException` |
| `isEnabled()` | Tài khoản được kích hoạt | Tài khoản bị vô hiệu hóa | `DisabledException` |
| `isAccountNonExpired()` | Tài khoản chưa hết hạn | Tài khoản hết hạn | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Bằng chứng đăng nhập chưa hết hạn | Bằng chứng hết hạn | `CredentialsExpiredException` |

Bốn exception đều thuộc họ `AuthenticationException`, cụ thể thuộc nhóm `AccountStatusException`. Chúng giúp thành phần xác thực diễn đạt lý do bị từ chối ở **bên trong hệ thống**; **không đồng nghĩa** ứng dụng nên gửi nguyên tên lỗi cho client ngoài.

Một phương thức `UserDetails` tùy biến không tự suy ra trạng thái từ database. Nếu bạn không override, ở các phiên bản Spring Security gần đây các phương thức trạng thái này **mặc định trả `true`**; tức là logic khóa/hết hạn sẽ không có tác dụng nếu adapter không ánh xạ trạng thái domain vào chúng.

### Đừng nhầm isEnabled với isAuthenticated

- `userDetails.isEnabled()`: **đặc điểm trạng thái tài khoản** mà nguồn dữ liệu cung cấp.
- `authentication.isAuthenticated()`: **trạng thái đối tượng Authentication** theo cơ chế xác thực.
- `authentication.getAuthorities()`: **những quyền đã được cấp** để policy xét ở bước phân quyền.

Một user được enabled không nhất thiết đã đăng nhập. Một `Authentication` từng được tạo khi user enabled không bảo đảm tài khoản vẫn còn enabled **ở thời điểm hiện tại**.

## 3. Khóa, vô hiệu hóa và hết hạn khác nhau ở nguyên nhân và vòng đời

### 3.1. Locked — khóa tài khoản

Khóa thường được dùng khi có nguy cơ bảo mật hoặc yêu cầu tạm dừng: quá nhiều lần đăng nhập sai, phát hiện hoạt động bất thường, hoặc quản trị viên tạm khóa để điều tra.

Các biến thể:

- **Khóa tạm thời:** có trường `lockedUntil`; hết thời điểm đó thì đăng nhập lại được nếu các điều kiện khác đều hợp lệ.
- **Khóa thủ công:** có cờ `manuallyLocked` hoặc một trạng thái cần người có quyền gỡ.
- **Khóa có điều kiện:** chỉ gỡ khi hoàn tất xác minh danh tính, MFA hay quy trình hỗ trợ.

Ví dụ `lockedUntil=2026-11-05T10:00:00Z` không có nghĩa hệ thống phải chạy một job đúng thời điểm ấy. Một implementation có thể tính `isAccountNonLocked()` từ `Instant.now(clock)` so với `lockedUntil`; nếu thời điểm hiện tại đã bằng hoặc sau hạn, điều kiện thời gian không còn khóa.

**Khóa không đồng nghĩa xóa password hash, đổi role hoặc xóa tài khoản.** Nếu không thiết kế đúng, khóa tự động dựa trên một username có thể trở thành công cụ từ chối dịch vụ: kẻ xấu cố tình gửi nhiều mật khẩu sai để làm chủ tài khoản thật không đăng nhập được. Nên kết hợp rate limiting theo nhiều tín hiệu, cảnh báo bất thường và chính sách khôi phục phù hợp.

### 3.2. Disabled — vô hiệu hóa tài khoản

Đây thường là một quyết định nghiệp vụ hoặc quản trị: chưa kích hoạt, nhân viên nghỉ việc, chủ tài khoản yêu cầu tạm ngừng, vi phạm chính sách, hoặc tài khoản bị đóng theo quy trình.

Ví dụ:

~~~text
account_id = 101
username   = "mai"
enabled    = false
reason     = "ADMIN_SUSPENSION"
updated_at = "2026-11-04T08:20:00Z"
~~~

`reason` là dữ liệu nghiệp vụ do bạn thiết kế, không phải thuộc tính chuẩn của `UserDetails`. Có thể cần ghi rõ người ra quyết định, nguồn yêu cầu, thời điểm và đường khôi phục. Đừng trả toàn bộ lý do nội bộ hoặc dữ liệu điều tra cho người chưa xác thực.

**Vô hiệu hóa thường là trạng thái có chủ đích lâu dài hơn khóa tạm**, nhưng không phải luật bất biến: doanh nghiệp có thể dùng tên khác. Điều quan trọng là từ domain `AccountStatus` phải có phép ánh xạ rõ đến `isEnabled()` hoặc chính sách tương ứng.

### 3.3. Account expired — tài khoản hết hạn

Ví dụ tài khoản của cộng tác viên chỉ hoạt động đến hết ngày hợp đồng; hoặc một account được cấp quyền dùng sản phẩm trong khoảng thời gian xác định.

Phân biệt:

- **Account expiration:** khả năng xác thực của **danh tính/tài khoản** theo chính sách.
- **Subscription expiration:** quyền sử dụng **một gói dịch vụ**. Không phải lúc nào subscription hết hạn cũng phải cấm đăng nhập. Có ứng dụng vẫn cho người dùng login để thanh toán gia hạn hoặc xuất dữ liệu của chính họ.
- **Membership expiration:** tư cách thành viên **trong một tenant/dự án** hết hạn; người dùng có thể vẫn đăng nhập và truy cập tenant khác.

Vì vậy **không tự gán** mọi `planExpiresAt` thành `isAccountNonExpired=false`. Hãy chọn đúng ranh giới nghiệp vụ: liệu cần chặn **toàn bộ xác thực**, hay chỉ từ chối một số quyền/tài nguyên?

### 3.4. Credentials expired — bằng chứng đăng nhập hết hạn

Đây là trường hợp mật khẩu hoặc thông tin xác thực không còn được chấp nhận theo chính sách. Ví dụ tổ chức buộc đặt lại mật khẩu sau khi phát hiện rò rỉ hoặc khi kết thúc một chu kỳ được quy định.

Các điều cần phân biệt:

- Mật khẩu hết hạn **khác** tài khoản hết hạn.
- Mật khẩu hết hạn **khác** JWT access token hết hạn sau 15 phút. JWT expiration (`exp`) là kiểm tra token, không tự chuyển thành `UserDetails.isCredentialsNonExpired()`.
- Mật khẩu hết hạn **khác** mật khẩu sai. `PasswordEncoder.matches` có thể thành công về mặt mật mã, nhưng chính sách vẫn từ chối hoàn tất đăng nhập.
- Bắt buộc đổi mật khẩu **khác** việc người dùng đã thay mật khẩu thành công. Cần có luồng đổi/reset được xác minh.

Một trường hợp dễ mắc bẫy: nếu đặt `isCredentialsNonExpired=false` thì flow xác thực mật khẩu thông thường có thể bị chặn. **Không tự giả định** user vẫn có `Authentication` đầy đủ để mở trang `/change-password` yêu cầu `authenticated()`. Cần thiết kế đường đổi/reset mật khẩu với bằng chứng phù hợp hoặc cơ chế xác thực hạn chế được xác minh riêng, tránh vừa khóa hết flow vừa không có cách khôi phục.

## 4. Spring Security kiểm tra các cờ ở đâu?

Trong luồng username/password phổ biến với `DaoAuthenticationProvider`:

~~~text
Request nhập username + password
            |
            v
UsernamePasswordAuthenticationToken (chưa xác thực)
            |
            v
AuthenticationManager / ProviderManager
            |
            v
DaoAuthenticationProvider
            |
            +--> UserDetailsService.loadUserByUsername(username)
            |       -> UserDetails (username, hash, flags, authorities)
            |
            +--> Kiểm tra trạng thái tài khoản
            |       locked / disabled / account expired
            |
            +--> PasswordEncoder kiểm tra password
            |
            +--> Kiểm tra trạng thái credentials expired
            |
        +---+---+
        |       |
      Thành    Không thành công
      công      -> AuthenticationException
        |
        v
Authentication đã xác thực
        |
        v
Authorization cho từng request/tài nguyên
~~~

Sơ đồ trên là **mô hình logic của flow**, không phải mô tả chính xác mọi thứ tự thực thi của tất cả các bản vá/provider. Các bản vá chống rò rỉ qua thời gian phản hồi có thể chạy thêm phép so sánh mật khẩu ngay cả khi trạng thái tài khoản bị cấm. Đừng dùng thứ tự kiểm tra hoặc thời gian phản hồi để phân biệt sự tồn tại/trạng thái tài khoản.

Trong `AbstractUserDetailsAuthenticationProvider`, nhóm kiểm tra mặc định gồm `DefaultPreAuthenticationChecks` (khóa, vô hiệu, hết hạn tài khoản) và `DefaultPostAuthenticationChecks` (hết hạn credentials). `DaoAuthenticationProvider` cung cấp thao tác kiểm tra password và có thể áp dụng các kiểm soát phụ khác. Một custom provider không nhất thiết tự sử dụng các cờ trạng thái này.

### Exception không có nghĩa server phải trả nguyên lý do

Ví dụ:

| Lý do nội bộ | Exception có thể được tạo | Response dành cho người dùng ngoài |
| --- | --- | --- |
| Tài khoản bị khóa | `LockedException` | Có thể dùng thông báo login không thành công thống nhất |
| Tài khoản bị disable | `DisabledException` | Có thể dùng thông báo login không thành công thống nhất |
| Tài khoản hết hạn | `AccountExpiredException` | Thông báo/luồng gia hạn tùy mức tin cậy và nghiệp vụ |
| Mật khẩu hết hạn | `CredentialsExpiredException` | Quy trình reset/xác minh phù hợp, không tiết lộ bí mật |
| Mật khẩu sai | `BadCredentialsException` | Thông báo xác thực không thành công |

Với API dùng HTTP Basic, một xác thực thất bại thường dẫn đến **401 Unauthorized** qua `AuthenticationEntryPoint`; với form login có thể chuyển hướng về trang lỗi đăng nhập. Đây là lựa chọn của tầng web, **không phải** do `UserDetails` tự gửi HTTP status.

Với một API đã xác thực nhưng thiếu quyền truy cập tài nguyên, kết quả thường là **403 Forbidden**. Tách rạch ròi **lỗi xác thực** và **lỗi phân quyền**; đừng dùng `403` cho mọi trạng thái tài khoản chỉ vì dễ lập trình.

## 5. Những cờ đảo chiều trong User.withUsername(...)

Spring Security có builder tiện cho ví dụ và in-memory users:

~~~java
UserDetails user = User.withUsername("mai")
        .password("{noop}demo-only")
        .roles("USER")
        .accountLocked(true)
        .disabled(false)
        .accountExpired(false)
        .credentialsExpired(false)
        .build();
~~~

Hãy đọc đúng **tên phương thức builder**:

| Builder `User.UserBuilder` | Giá trị `true` thiết lập | UserDetails đọc kết quả |
| --- | --- | --- |
| `.accountLocked(true)` | Người dùng **bị khóa** | `isAccountNonLocked() == false` |
| `.disabled(true)` | Người dùng **bị vô hiệu** | `isEnabled() == false` |
| `.accountExpired(true)` | Người dùng **hết hạn** | `isAccountNonExpired() == false` |
| `.credentialsExpired(true)` | Credentials **hết hạn** | `isCredentialsNonExpired() == false` |

Các builder dùng ngôn ngữ **tình trạng có vấn đề**, còn ba phương thức interface lại có chữ **Non**. Đây là nơi dễ đặt nhầm logic:

~~~java
// SAI: disabled=true thực chất tắt tài khoản đang hoạt động.
.disabled(account.isActive())

// ĐÚNG nếu account.isActive() thực sự nghĩa enabled.
.disabled(!account.isActive())
~~~

Builder trong demo cố tình dùng `{noop}` để không cần triển khai hệ thống password thực tế. **Không lưu mật khẩu production dưới dạng `{noop}`**; với ứng dụng thật, dùng `PasswordEncoder` phù hợp và hash mật khẩu đã được tạo an toàn.

## 6. Ví dụ Java 17+ chạy độc lập: quan sát bốn trạng thái

Ví dụ này dùng `spring-security-core` thật để tạo `UserDetails` và dùng `AccountStatusUserDetailsChecker` kiểm tra trạng thái. Mỗi user có **duy nhất một cờ trạng thái bị cấm**, vì thế kết quả rõ ràng, không dựa vào thứ tự khi có nhiều lỗi cùng lúc.

Đây là **bài thực hành API kiểm tra trạng thái**, không phải một web login hoàn chỉnh: chương trình không nhận password từ HTTP, không gọi `AuthenticationManager` và không tạo phiên đăng nhập.

### 6.1. Tạo project Gradle

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:7.1.2'
}

application {
    mainClass = 'AccountStatusDemo'
}
~~~

Spring Security 7.1.2 trong ví dụ phù hợp với Java 17+. Nếu đang dùng Spring Boot starter, **không khóa version `spring-security-core` riêng** theo ví dụ này mà để Boot BOM quản lý module tương ứng.

Tạo `src/main/java/AccountStatusDemo.java`:

~~~java
import org.springframework.security.authentication.AccountStatusUserDetailsChecker;
import org.springframework.security.authentication.AccountStatusException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;

public class AccountStatusDemo {

    private static UserDetails user(
            String username,
            boolean locked,
            boolean disabled,
            boolean accountExpired,
            boolean credentialsExpired) {
        return User.withUsername(username)
                .password("{noop}example-only")
                .roles("USER")
                .accountLocked(locked)
                .disabled(disabled)
                .accountExpired(accountExpired)
                .credentialsExpired(credentialsExpired)
                .build();
    }

    private static void check(String name, UserDetails user) {
        var checker = new AccountStatusUserDetailsChecker();
        try {
            checker.check(user);
            System.out.println(name + " -> ALLOWED");
        } catch (AccountStatusException exception) {
            System.out.println(name + " -> "
                    + exception.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        check("active", user("active", false, false, false, false));
        check("locked", user("locked", true, false, false, false));
        check("disabled", user("disabled", false, true, false, false));
        check("account-expired",
                user("account-expired", false, false, true, false));
        check("credentials-expired",
                user("credentials-expired", false, false, false, true));
    }
}
~~~

Từ thư mục dự án, với JDK 17+ và Gradle phù hợp, chạy:

~~~bash
gradle run --quiet
~~~

Đầu ra dự kiến của chính chương trình:

~~~text
active -> ALLOWED
locked -> LockedException
disabled -> DisabledException
account-expired -> AccountExpiredException
credentials-expired -> CredentialsExpiredException
~~~

Phân tích:

- `active`: cả bốn cờ đủ điều kiện, nên `check` không ném exception. Chuỗi `ALLOWED` **chỉ nghĩa là vượt qua kiểm tra trạng thái**, không chứng minh mật khẩu đã đúng và không cấp mọi quyền.
- `locked`: `isAccountNonLocked()==false`, nên ném `LockedException`.
- `disabled`: `isEnabled()==false`, nên ném `DisabledException`.
- `account-expired`: `isAccountNonExpired()==false`, nên ném `AccountExpiredException`.
- `credentials-expired`: `isCredentialsNonExpired()==false`, nên ném `CredentialsExpiredException`.

Không in `user.getPassword()` trong ví dụ; mã nguồn chỉ dùng mật khẩu giả `{noop}` để tạo dữ liệu thử. Trong production, password hashing và policy trạng thái là hai lớp khác nhau.

**Lưu ý:** `AccountStatusUserDetailsChecker` là một công cụ kiểm tra `UserDetails`. `DaoAuthenticationProvider` có các pre/post checks riêng; đừng suy rằng gọi checker đơn lẻ sẽ thực hiện đầy đủ quá trình xác thực mật khẩu hay thay thế provider.

## 7. Ánh xạ trạng thái domain sang UserDetails

Trong ứng dụng thật, dữ liệu có thể gồm:

~~~text
accounts
  id
  username
  password_hash
  enabled
  manually_locked
  locked_until
  account_expires_at
  password_changed_at
  require_password_change
  tenant_id
  status_changed_at
  status_changed_by
  status_reason
~~~

Đây là **schema gợi ý**, không phải bảng mà Spring Security tạo sẵn. Không phải ứng dụng nào cũng cần tất cả các cột. Có thể tách `login_credentials` hoặc `account_restrictions` để quản lý đúng trách nhiệm.

Một lớp domain Java minh họa:

~~~java
public record AccountState(
        long accountId,
        String username,
        boolean enabled,
        boolean manuallyLocked,
        java.time.Instant lockedUntil,
        java.time.Instant accountExpiresAt,
        java.time.Instant credentialsExpiresAt
) {}
~~~

Các trường `lockedUntil` và `accountExpiresAt` cho phép mô hình hóa **thời gian**, còn `enabled` phản ánh quyết định kích hoạt. Nên dùng `Instant`/UTC cho thời điểm kỹ thuật để tránh sai lệch do múi giờ, sau đó hiển thị theo múi giờ người dùng khi cần.

Một policy chuyển trạng thái:

~~~java
// Mảnh code trong service/adapter; chưa phải class độc lập.
boolean nonLocked(AccountState a, Instant now) {
    boolean temporaryLockActive =
            a.lockedUntil() != null && now.isBefore(a.lockedUntil());

    return !a.manuallyLocked() && !temporaryLockActive;
}

boolean nonExpired(Instant expiresAt, Instant now) {
    return expiresAt == null || now.isBefore(expiresAt);
}
~~~

Ở đây, **tại đúng thời điểm hết hạn**, `now.isBefore(expiresAt)` là `false`. Quy ước `expiresAt` là thời điểm bắt đầu **không còn** hiệu lực; không nhầm với “ngày hết hạn” bao gồm toàn bộ ngày cuối. Nếu nghiệp vụ chỉ lưu ngày, cần định nghĩa rõ timezone và quy tắc chuyển `LocalDate` thành `Instant`.

Sau đó ánh xạ vào `UserDetails`:

~~~java
// Mảnh code trong UserDetailsService, có repository và PasswordEncoder thích hợp.
AccountState account = accountRepository.loadByUsername(username)
        .orElseThrow(() -> new UsernameNotFoundException("Unknown user"));

Instant now = clock.instant();

return User.withUsername(account.username())
        .password(accountRepository.passwordHashOf(account.accountId()))
        .authorities("ROLE_USER")
        .disabled(!account.enabled())
        .accountLocked(!nonLocked(account, now))
        .accountExpired(!nonExpired(account.accountExpiresAt(), now))
        .credentialsExpired(!nonExpired(account.credentialsExpiresAt(), now))
        .build();
~~~

`accountRepository`, `clock` và những helper ở đây là **thành phần do ứng dụng tự cung cấp**; code là fragment để giải thích phép ánh xạ, không phải chương trình độc lập. Không copy một ví dụ rồi quên kiểm tra `status` hoặc tenant theo nghiệp vụ thật.

**Ranh giới thời gian:** nếu dùng `lockedUntil` thì job mở khóa hoặc phép tính động đều có thể được dùng, nhưng phải thống nhất với cách cache `UserDetails`. Không được giữ một `UserDetails` với cờ locked cũ vô thời hạn, và cũng không lấy cờ trong request body để tạo trạng thái tin cậy.

### Trường hợp account expired và credential expired có thể cùng true

Nếu tài khoản vừa hết hạn vừa bị đánh dấu phải đổi mật khẩu, provider có thể trả một lỗi trạng thái theo thứ tự kiểm tra. **Không coi exception đầu tiên được trả là toàn bộ sự thật nghiệp vụ.** Việc điều tra, audit và luồng khôi phục nên sử dụng dữ liệu trạng thái đầy đủ từ repository theo quyền quản trị.

## 8. Chặn đăng nhập mới chưa đủ để xử lý phiên cũ

Đây là điểm quan trọng nhất về mặt vận hành.

Giả sử Mai đăng nhập lúc 09:00, nhận session cookie hợp lệ. Quản trị viên vô hiệu hóa tài khoản cô lúc 09:15. Nếu hệ thống chỉ cập nhật `accounts.enabled=false`, một session đã xác thực từ 09:00 **không tự biến mất** chỉ vì `UserDetailsService` sẽ trả disabled ở lần đăng nhập mới.

Sơ đồ:

~~~text
09:00  Đăng nhập thành công
         -> Authentication được lưu/truyền theo cơ chế hiện tại
         -> session hoặc access token còn hiệu lực

09:15  Admin đặt enabled=false trong database
         -> Login mới bằng DaoAuthenticationProvider bị chặn
         -> Session/token cũ: PHỤ THUỘC cơ chế thu hồi của ứng dụng

09:20  Request mới với session/token cũ
         -> Có thể vẫn mang Authentication được chấp nhận
         -> Cần kiểm soát trạng thái hiện tại / thu hồi / timeout
~~~

Các chiến lược cần cân nhắc:

| Cơ chế xác thực | Phương án xử lý trạng thái mới | Giới hạn |
| --- | --- | --- |
| HTTP session trên server | Vô hiệu hóa các session liên quan và/hoặc kiểm tra account hiện tại khi xử lý thao tác quan trọng | Phải tìm đúng tất cả session, có thể gồm nhiều node/thiết bị |
| JWT tự chứa claims | Token ngắn hạn, kiểm tra trạng thái account/revocation version ở server, hoặc denylist theo nhu cầu | Chữ ký và `exp` hợp lệ **không bảo đảm** account chưa bị khóa sau khi token phát hành |
| Refresh token | Thu hồi refresh token và ngăn cấp access token mới | Access token đã cấp có thể còn sống đến khi hết hạn nếu không có kiểm tra thêm |
| API key/service principal | Hủy key, cập nhật trạng thái credentials/identity ở nơi xác minh | Phải xử lý cache và những dịch vụ nhận key |
| OIDC/SSO | Đồng bộ/kiểm tra trạng thái nội bộ, xử lý logout/revocation theo kiến trúc | Đăng xuất khỏi một hệ không đồng nghĩa mọi session của mọi hệ đã bị hủy |

**Đừng hứa “disabled là logout tức thì” nếu kiến trúc không có cơ chế đó.** Cần định nghĩa thời gian thu hồi tối đa chấp nhận được cho từng loại tài nguyên, nhất là tài chính, dữ liệu riêng tư và thao tác quản trị.

### Tại sao session và JWT khác nhau?

Session ở server có thể lưu `SecurityContext` với `Authentication` đã tạo khi login. Nếu không làm mới, các cờ và authorities có thể là snapshot cũ. JWT có thể chứa claim `sub`, roles và `exp` do hệ phát hành ký; xác minh chữ ký chưa tự truy vấn account record mới nhất.

Một policy bổ sung trước khi thực hiện hành động nhạy cảm có thể xét trạng thái hiện hành:

~~~text
ALLOWED = validAuthentication
          AND currentAccount.enabled
          AND currentAccount.notLocked
          AND currentAccount.notExpired
          AND requiredAuthority
          AND resourceOwnershipOrScope
~~~

Đây là mô hình, **không phải API Spring Security tự có**. Bạn có thể triển khai qua service authorization, `AuthorizationManager` hoặc logic truy vấn được giới hạn quyền. Hạn chế tự viết filter kiểm tra database ở mọi request nếu không có thiết kế cache, latency và khả năng hoạt động khi database lỗi. Nhưng không được hy sinh kiểm tra trạng thái với thao tác có rủi ro cao chỉ để tránh một query.

### Nút đăng xuất không phải cơ chế thu hồi tập trung

Một người dùng bấm logout có thể xóa session ở trình duyệt hiện tại; điều đó không chứng minh các session ở thiết bị khác, refresh tokens hoặc access tokens đã bị thu hồi. Khi quản trị viên khóa/vô hiệu hóa account, ứng dụng cần quyết định **toàn bộ các phiên liên quan** phải được xử lý ra sao.

## 9. Thiết kế khóa tài khoản chống brute force nhưng tránh tự tạo DoS

Một chính sách khóa sau sai mật khẩu thường có những biến:

- Số lần sai trong một cửa sổ thời gian.
- Khoảng thời gian khóa hoặc chế độ tăng độ trễ.
- Giới hạn theo tài khoản, IP, thiết bị và tín hiệu rủi ro.
- Quá trình reset bộ đếm sau thành công.
- Cách mở khóa an toàn và audit quyết định.
- Cách tránh kẻ xấu cố tình khóa nhiều tài khoản khác.

Ví dụ mô hình:

~~~text
failedAttempts[accountId] = 0..N
lastFailureAt
lockedUntil

if failed attempts vượt ngưỡng:
    lockedUntil = now + lockDuration
    ghi sự kiện cảnh báo
else:
    theo dõi cửa sổ thời gian và rủi ro
~~~

Đây là **pseudocode**. Không tự nhận rằng `UserDetails.isAccountNonLocked()` sẽ đếm số lần sai mật khẩu, tạo `lockedUntil` hoặc reset counter. Spring Security chỉ cung cấp điểm giao tiếp và một số sự kiện xác thực; bộ đếm, rate limit và bảo vệ trước các request đồng thời do ứng dụng hoặc hạ tầng xây dựng.

Những rủi ro cần xử lý:

1. **Account enumeration:** màn hình login không nên tiết lộ “tài khoản không tồn tại”, “tài khoản bị khóa”, “email chưa xác minh” ở mức có thể bị lạm dụng. Tạo thông báo an toàn và dùng kênh đã xác minh cho khôi phục.
2. **Timing side channel:** khác biệt thời gian phản hồi giữa tài khoản thường, bị khóa và không tồn tại có thể tiết lộ trạng thái. Cập nhật bản vá Spring Security và đo các luồng login.
3. **Lockout DoS:** khóa cứng theo vài lần sai cho phép người ngoài gây gián đoạn tài khoản thật. Cân nhắc tăng độ trễ, rate limit và cách phục hồi.
4. **Race condition:** nhiều request đăng nhập đồng thời có thể làm bộ đếm sai nếu chỉ load, cộng, save mà không có cập nhật nguyên tử hoặc khóa phù hợp.
5. **Khóa không thống nhất:** các node có cache trạng thái khác nhau có thể xử lý login không nhất quán. Dùng nguồn sự thật và TTL/cache invalidation thích hợp.
6. **Rò rỉ bí mật vào log:** audit sự kiện gồm actor/account ID được bảo vệ, loại sự kiện và timestamp; không ghi raw password, session ID hoặc token.

### Cập nhật bảo mật quan trọng: CVE-2026-22746

Tháng 4/2026, Spring công bố CVE-2026-22746 liên quan khả năng suy đoán thuộc tính user qua thời gian phản hồi khi `DaoAuthenticationProvider` kiểm tra user bị khóa, vô hiệu hoặc hết hạn. Theo advisory, các nhánh bị ảnh hưởng bao gồm Spring Security **6.5.0–6.5.9** và **7.0.0–7.0.4**. Bản vá đã được công bố cho 6.5.10 và 7.0.5.

Vì vậy, khi dạy và triển khai chức năng khóa/hết hạn, cần **kiểm tra advisory và phiên bản Security thực tế từ BOM/dependency tree**, ưu tiên bản đã vá thay vì chỉ sửa thông báo lỗi ở giao diện. Demo dùng 7.1.2 nằm ngoài các dải bị ảnh hưởng nêu trong advisory. Đừng giải quyết bằng cách vô hiệu hóa kiểm tra trạng thái hoặc tùy tiện hạ phiên bản.

Nguồn: [Spring Security Advisory CVE-2026-22746](https://spring.io/security/cve-2026-22746/).

## 10. Thiết kế luồng khôi phục riêng theo từng trạng thái

Không phải mọi lý do bị từ chối đều được giải quyết bằng cùng một form.

| Trạng thái | Luồng khôi phục phù hợp | Điều cần kiểm tra |
| --- | --- | --- |
| Tạm khóa vì sai mật khẩu | Chờ hết hạn; hoặc xác minh danh tính bằng kênh được tin cậy | Không dùng một endpoint bỏ qua khóa mà không xác minh |
| Khóa thủ công để điều tra | Quy trình người có thẩm quyền gỡ khóa | Audit ai gỡ và lý do |
| Disabled do chưa xác minh | Xác minh email/thiết bị hoặc bước kích hoạt theo chính sách | Token xác minh một lần, ngắn hạn và gắn đúng tài khoản |
| Disabled do nghỉ việc/vi phạm | Quyết định quản trị, hiếm khi tự khôi phục | Không mở lại chỉ vì người dùng biết mật khẩu |
| Account expired | Gia hạn hoặc chuyển về chế độ giới hạn | Đừng cấm trang thanh toán gia hạn nếu nghiệp vụ cần |
| Credentials expired | Đổi/reset mật khẩu bằng bằng chứng phù hợp | Không phát Authentication đầy đủ trước khi hoàn thành yêu cầu |

Đặc biệt với **credentials expired**: nếu flow login bình thường từ chối, trang đổi mật khẩu chỉ có `authenticated()` cũng có thể không mở được. Một số cách thiết kế là dùng **token reset ngắn hạn**, hoặc một luồng xác minh có quyền hạn đặc biệt chỉ cho phép thay mật khẩu, rồi mới phát quyền bình thường. Cần chống CSRF khi dùng cookie và xác nhận đúng chủ thể.

Khi trạng thái được gỡ, không nhất thiết khôi phục lại mọi token hoặc session cũ. Nhiều hệ thống chọn buộc xác thực mới sau một sự kiện khóa hoặc reset mật khẩu; đây là quyết định có chủ đích và phải được kiểm thử.

## 11. Các thay đổi trạng thái phải có quyền quản trị và audit

Một endpoint như `POST /admin/accounts/101/disable` thay đổi quyền đăng nhập của người khác. Nó không chỉ là thao tác cập nhật một boolean.

Hãy kiểm soát:

- **Ai được thay đổi?** Cần authority quản trị phù hợp, ràng buộc tenant, chức vụ hoặc quy trình phê duyệt.
- **Được đổi account nào?** Admin tenant A không được vô hiệu account tenant B trừ khi có quyền hệ thống được xác minh.
- **Có thể tự khóa người quản trị cuối cùng không?** Có thể cần quy tắc chống mất quyền vận hành, kiểm tra kỹ nghiệp vụ.
- **Ai được mở lại?** Người khóa không nhất thiết được tự mở nếu đang điều tra hoặc có quy trình hai người.
- **Có thông báo cho người liên quan không?** Gửi qua kênh có chính sách thông tin phù hợp, không tiết lộ chi tiết điều tra.
- **Có xử lý phiên cũ không?** Cần gắn thao tác đổi trạng thái với chiến lược invalidation/token revocation.
- **Có tránh ghi đè đồng thời không?** Dùng transaction/optimistic locking/CAS khi hai quản trị viên cùng đổi trạng thái.

Một mảnh service minh họa:

~~~java
// Fragment nghiệp vụ, cần bean/repository/transaction và chính sách riêng.
@Transactional
public void disableAccount(long targetAccountId, CurrentActor actor) {
    policy.requireCanManageAccount(actor, targetAccountId);

    Account account = repository.findByIdForUpdate(targetAccountId)
        .orElseThrow(AccountNotFoundException::new);

    account.disable(actor.accountId(), clock.instant());
    repository.save(account);
    audit.recordAccountDisabled(actor, account);
    sessionRevocation.requestRevokeSessions(account.id());
}
~~~

`CurrentActor`, `Account`, `policy`, `audit` và `sessionRevocation` là **kiểu/thành phần do ứng dụng định nghĩa**. Đây chỉ là phác thảo luồng để hiểu ranh giới; thao tác thu hồi session nên được phối hợp đúng thời điểm commit và xử lý lỗi, chẳng hạn qua outbox/event sau transaction để tránh trạng thái nửa chừng.

Nếu bạn chỉ có `@PreAuthorize("hasRole('ADMIN')")` nhưng không kiểm tra tenant, vẫn có nguy cơ admin của tổ chức này khóa người dùng tổ chức khác. Kiểm soát tài nguyên cụ thể luôn cần trong hệ thống đa tenant.

## 12. Thời điểm và tính mới của trạng thái

Một lần login có thể xảy ra ngay ranh giới thời gian hết hạn:

~~~text
accountExpiresAt = 2026-11-04T12:00:00Z

now = 2026-11-04T11:59:59Z -> nonExpired = true
now = 2026-11-04T12:00:00Z -> nonExpired = false
now = 2026-11-04T12:00:01Z -> nonExpired = false
~~~

Dùng một `Clock` có thể inject giúp logic kiểm thử quyết định được kết quả chính xác và tránh phụ thuộc đồng hồ thật. Với khóa tạm thời, tại `lockedUntil`, bạn có thể định nghĩa là đã mở khóa. Nếu dữ liệu thời gian cần điều kiện khác, phải ghi lại hợp đồng và test theo hợp đồng đó.

Cần quan tâm đến **nguồn dữ liệu mới nhất**:

- `UserDetailsService` có thể trả user được tải từ database, nhưng một provider hoặc tầng ứng dụng có thể có cache.
- Session/JWT đã cấp có thể còn snapshot cũ dù database vừa đổi `enabled`.
- Một cập nhật vừa commit có thể chưa tới node khác nếu dùng cache bất đồng bộ.
- Khóa/vô hiệu hóa ở hệ thống định danh ngoài có thể chưa đồng bộ sang ứng dụng nội bộ.

Hãy định nghĩa yêu cầu về **độ trễ thu hồi** và kiểm thử nó. Không chỉ assert một cột trong database đã đổi từ `true` sang `false`.

## 13. Viết test đúng ranh giới trạng thái và xác thực

Có ba nhóm test khác nhau:

**Nhóm A — ánh xạ domain sang UserDetails:** bảo đảm enabled, lock, expiry và credentials expiry được tính đúng, nhất là logic `!nonExpired` và các boundary times.

**Nhóm B — flow xác thực:** dùng `DaoAuthenticationProvider` hoặc HTTP Basic/form login thật để xác nhận tài khoản không đủ điều kiện **không tạo Authentication đáng tin** dù mật khẩu đúng. Kiểm tra thông báo bên ngoài không tiết lộ trạng thái không cần thiết.

**Nhóm C — vòng đời session/token:** khi account bị disabled hoặc locked **sau login**, kiểm tra các request tiếp theo bị chặn trong thời hạn đáp ứng yêu cầu bảo mật. Test đủ nhiều session, node hoặc issuer nếu hệ thống có.

Một ma trận thử nghiệm:

| Trường hợp | Kỳ vọng |
| --- | --- |
| User enabled, non-locked, non-expired, credentials valid; mật khẩu đúng | Xác thực thành công nếu các điều kiện khác hợp lệ |
| User enabled nhưng nhập sai password | Bị từ chối vì credentials không khớp |
| Đúng password nhưng `isAccountNonLocked=false` | Login mới bị từ chối |
| Đúng password nhưng `isEnabled=false` | Login mới bị từ chối |
| Đúng password nhưng `isAccountNonExpired=false` | Login mới bị từ chối |
| Đúng password nhưng `isCredentialsNonExpired=false` | Login mới bị từ chối hoặc đi vào luồng khôi phục được thiết kế riêng |
| Hai cờ bị cấm cùng lúc | Không có đường nào cấp xác thực đầy đủ; audit đủ trạng thái |
| Tạm khóa trước `lockedUntil` | Bị chặn |
| Ngay tại `lockedUntil` | Được bỏ điều kiện khóa thời gian theo quy ước bài |
| Admin disable sau login | Session/token cũ bị xử lý theo chính sách thu hồi, không chỉ login mới |
| Admin khác tenant cố disable tài khoản | Bị từ chối ở authorization theo tài nguyên |
| Reset password hợp lệ | Hash mới được lưu, chính sách credentials và session được cập nhật phù hợp |
| Client thử username không tồn tại hoặc bị disable | Không rò rỉ trạng thái qua lỗi hoặc thời gian phản hồi dễ khai thác |

Với Spring Boot servlet, có thể dùng `MockMvc`, `@SpringBootTest` và `spring-security-test`. Tuy nhiên `@WithMockUser` **tạo sẵn Authentication thử nghiệm**, thường bỏ qua `UserDetailsService` và các phép kiểm tra password/trạng thái của provider. Nếu muốn kiểm thử **khóa tài khoản thực sự cản login**, đừng chỉ viết test có `@WithMockUser(username="locked")` rồi assert 200/403. Hãy gửi credentials qua đúng cơ chế login hoặc gọi `AuthenticationManager.authenticate` trong integration test.

## 14. Sai lầm thường gặp

1. **“Tài khoản bị locked tức mật khẩu sai.”** Không: mật khẩu có thể đúng nhưng chính sách vẫn cấm login.
2. **“Disabled và locked là cùng một boolean.”** Không nên trộn khi nghiệp vụ có nguyên nhân và vòng đời khôi phục khác nhau.
3. **“Account expired chính là JWT `exp`.”** Không: một cái là trạng thái tài khoản, một cái là vòng đời token.
4. **“Password expired là account expired.”** Không: `isCredentialsNonExpired` và `isAccountNonExpired` khác nhau.
5. **“`isAccountNonLocked=false` nghĩa là không bị khóa.”** Sai vì chữ `Non`; `false` tức đang bị khóa.
6. **“`.disabled(true)` kích hoạt tài khoản.”** Sai: builder dùng tên thuộc tính theo nghĩa bị vô hiệu.
7. **“UserDetails tự đọc cột lockedUntil trong DB.”** Không: adapter của ứng dụng phải làm.
8. **“Chỉ cần đổi `enabled=false` là tất cả session và JWT bị thu hồi tức thì.”** Không mặc định.
9. **“Một tài khoản không tồn tại nên báo lỗi riêng để khách biết đúng tên.”** Dễ tạo account enumeration.
10. **“Cứ khóa sau 3 lần sai là chống brute force triệt để.”** Có thể bị khai thác làm DoS; cần thiết kế nhiều lớp.
11. **“Có `Authentication` trong session thì quyền/trạng thái luôn mới.”** Không: có thể là dữ liệu lúc login.
12. **“`@WithMockUser` kiểm thử được account lock.”** Không đầy đủ: test ấy thường bỏ qua provider và phép kiểm trạng thái.
13. **“Một role quản trị có thể disable mọi tenant.”** Không nếu phạm vi quyền chỉ thuộc tenant của người đó.
14. **“PasswordEncoder tự xử lý khóa tài khoản.”** Sai: nó chỉ mã hóa và kiểm tra password.
15. **“Có `LockedException` thì phải trả tên lỗi cho mọi client.”** Không: exception nội bộ và thông báo ngoài là hai vấn đề khác nhau.
16. **“UserDetails mặc định sẽ tự cấm tài khoản chưa kích hoạt.”** Nếu cờ luôn true, cấu hình tùy biến có thể cho đi qua.
17. **“Ứng dụng dùng JWT thì chỉ cần các cờ UserDetails.”** JWT flow thường không gọi `UserDetailsService`; cần cơ chế trạng thái riêng.
18. **“Tài khoản hết hạn thì phải xóa dữ liệu.”** Không: retention/xóa dữ liệu là chính sách độc lập, cần xét pháp lý và nghiệp vụ.
19. **“Mọi trạng thái hết hạn bắt buộc chặn login.”** Không phải subscription/membership expired nào cũng cần chặn cả identity.
20. **“Tắt kiểm tra locked là cách sửa lỗi timing.”** Không: cần bản vá Security và chính sách phản hồi an toàn.

## 15. Tự kiểm tra kiến thức

**Câu 1.** Một `UserDetails` có `isEnabled=true`, `isAccountNonLocked=false`. Mật khẩu đúng. Người dùng có đăng nhập thành công không?

*Trả lời:* Trong một `DaoAuthenticationProvider` dùng kiểm tra trạng thái chuẩn, không. Tài khoản bị khóa, có thể ném `LockedException` bên trong luồng xác thực.

**Câu 2.** Tại sao `User.withUsername("mai").accountExpired(true)` dẫn đến `isAccountNonExpired()==false`?

*Trả lời:* Builder dùng `accountExpired` theo nghĩa trạng thái xấu, còn `UserDetails` dùng tên phủ định `isAccountNonExpired`. Hai giá trị tương ứng đảo nhau.

**Câu 3.** `isCredentialsNonExpired=false` có tự báo JWT access token đã hết hạn không?

*Trả lời:* Không. JWT `exp` được validator/token decoder kiểm tra; cờ credentials expired phục vụ những cơ chế sử dụng `UserDetails`, thường là password login.

**Câu 4.** Admin đặt `enabled=false` cho tài khoản Mai lúc 10:00. Mai có session từ 09:00. Có chắc request 10:01 bị chặn?

*Trả lời:* Chưa chắc. Cần xem chính sách thu hồi session, kiểm tra trạng thái hiện tại, cache và cơ chế authorization; thay đổi database không tự hủy mọi phiên cũ.

**Câu 5.** Hệ thống có khóa tự động theo số lần nhập sai. Cần đề phòng rủi ro gì ngoài brute force?

*Trả lời:* Người ngoài có thể cố tình khóa tài khoản người khác (DoS), dò sự tồn tại account qua lỗi/timing, gây race condition trên bộ đếm hoặc làm cache các node không đồng nhất.

**Câu 6.** Vì sao không thể chỉ dùng `@WithMockUser` để chứng minh account bị khóa không đăng nhập được?

*Trả lời:* Annotation tạo Authentication giả cho test, thường không gọi `DaoAuthenticationProvider` kiểm tra trạng thái. Cần test gọi đúng cơ chế xác thực.

**Câu 7.** Nếu account vẫn enabled nhưng hợp đồng dịch vụ hết hạn, có nên đặt `isAccountNonExpired=false`?

*Trả lời:* Tùy chính sách. Nếu chỉ gói dịch vụ hết hạn, có thể vẫn cho login để gia hạn; chặn những chức năng thuộc subscription bằng authorization thay vì tắt toàn bộ account.

**Câu 8.** Nên lưu `lockedUntil` bằng `LocalDateTime` hay `Instant` trong hệ thống có nhiều timezone?

*Trả lời:* Với thời điểm kỹ thuật, `Instant` thường rõ ràng hơn, giảm rủi ro múi giờ. Khi hiển thị cho người dùng mới chuyển sang timezone thích hợp.

**Câu 9.** `AccountStatusUserDetailsChecker.check(user)` trả về bình thường đã chứng minh password đúng chưa?

*Trả lời:* Chưa. Checker chỉ kiểm tra trạng thái `UserDetails`; xác thực password cần provider/`PasswordEncoder` và cơ chế xác thực phù hợp.

**Câu 10.** Spring Security có advisory nào trong năm 2026 liên quan account bị khóa/hết hạn?

*Trả lời:* CVE-2026-22746 nói về user attribute enumeration qua thời gian xử lý của `DaoAuthenticationProvider` ở những phiên bản bị ảnh hưởng. Cần nâng các nhánh đã được vá theo advisory, ví dụ 6.5.10 hoặc 7.0.5 trở lên trong cùng nhánh có hỗ trợ.

Khi thiết kế bảo mật tài khoản, hãy tách **trạng thái account hiện tại**, **điều kiện xác thực mới** và **vòng đời Authentication đã phát hành trước đó**. Các cờ `UserDetails` là điểm nối quan trọng cho username/password login, nhưng khả năng thu hồi quyền và truy cập an toàn phải được thiết kế xuyên qua session, token và chính sách dữ liệu.

### Tài liệu đối chiếu

- [Spring Security — UserDetails API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html)
- [Spring Security — User/UserBuilder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/User.html)
- [Spring Security — AccountStatusUserDetailsChecker](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AccountStatusUserDetailsChecker.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — CVE-2026-22746](https://spring.io/security/cve-2026-22746/)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
