# BadCredentialsException, LockedException, DisabledException và lỗi hết hạn

> **Chủ đề:** Spring Security — authentication → **Trạng thái tài khoản**. Bài này giải thích cách hệ thống xác thực bằng username/password phân biệt **sai bằng chứng** với **tài khoản bị khóa, vô hiệu hóa, hết hạn** hoặc **thông tin xác thực hết hạn**. Trọng tâm là hợp đồng `UserDetails`, thứ tự kiểm tra của `DaoAuthenticationProvider`, nhóm `AuthenticationException`, cách ứng dụng phản hồi an toàn và cách kiểm thử trạng thái. Ví dụ dùng Java 17 và Spring Security **6.5.11** (dòng đã có bản vá vấn đề timing khi kiểm trạng thái tài khoản).

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ý nghĩa và quan hệ kế thừa của `BadCredentialsException`, `LockedException`, `DisabledException`, `AccountExpiredException` và `CredentialsExpiredException`.
2. Ánh xạ chính xác bốn thuộc tính `UserDetails`: `isAccountNonLocked()`, `isEnabled()`, `isAccountNonExpired()` và `isCredentialsNonExpired()`.
3. Hiểu vì sao **sai mật khẩu** không tương đương **tài khoản bị khóa**, cũng không tương đương **password đã hết hạn**.
4. Theo dõi lúc nào provider kiểm trạng thái trước/sau bước kiểm mật khẩu; không nhầm kết quả nội bộ với HTTP status.
5. Nhận biết `AccountStatusException` khiến `ProviderManager` **dừng ngay**, trong khi `BadCredentialsException` thông thường có thể cho phép thử provider khác.
6. Xây dựng ví dụ Java 17 chạy thật bằng `DaoAuthenticationProvider` và `BCryptPasswordEncoder`; dự đoán chính xác loại exception theo từng tài khoản.
7. Thiết kế thông báo đăng nhập, reset password, thao tác mở khóa, invalidation cache/session và audit an toàn.

## 2. Bảng phân loại: lỗi bằng chứng và lỗi trạng thái

Trong Spring Security, `AuthenticationManager.authenticate(...)` **trả `Authentication` đã xác thực hoặc ném `AuthenticationException`**. Những exception liên quan trực tiếp tới đề bài:

| Exception | Tình huống điển hình | Bản chất | Có phải `AccountStatusException`? |
| --- | --- | --- | --- |
| `BadCredentialsException` | Password sai, thiếu password hoặc provider che trường hợp không tìm thấy username | Bằng chứng chưa được chấp nhận | **Không** |
| `LockedException` | `UserDetails.isAccountNonLocked() == false` | Account bị khóa | **Có** |
| `DisabledException` | `UserDetails.isEnabled() == false` | Account không được bật để đăng nhập | **Có** |
| `AccountExpiredException` | `UserDetails.isAccountNonExpired() == false` | Tuổi thọ **tài khoản** đã hết | **Có** |
| `CredentialsExpiredException` | `UserDetails.isCredentialsNonExpired() == false` | Tuổi thọ **credential** (ví dụ password) đã hết | **Có** |

Cấu trúc lớp khái niệm:

~~~text
RuntimeException
└── AuthenticationException
    ├── BadCredentialsException
    ├── AccountStatusException
    │   ├── LockedException
    │   ├── DisabledException
    │   ├── AccountExpiredException
    │   └── CredentialsExpiredException
    └── ... các AuthenticationException khác
~~~

`BadCredentialsException` là một loại **`AuthenticationException`**, nhưng không thuộc `AccountStatusException`. Bốn exception về trạng thái account/credential cùng thuộc `AccountStatusException` và có chính sách xử lý đặc biệt trong `ProviderManager`.

**Quan trọng:** một exception mô tả **lý do bị từ chối theo cơ chế xác thực cụ thể**; bản thân nó không tự chứng minh hệ thống đã kiểm mọi yếu tố, không xác định mã HTTP mặc định cho mọi ứng dụng, và không phải thông điệp nên đưa nguyên văn cho người dùng.

### 2.1. "Sai mật khẩu" chưa chắc là một user tồn tại

`DaoAuthenticationProvider` dựa trên `UserDetailsService` và `PasswordEncoder`. Nếu username không tồn tại, `UserDetailsService` thường ném `UsernameNotFoundException`. Với `hideUserNotFoundExceptions=true` (mặc định), provider chuyển lỗi đó thành `BadCredentialsException` để giảm tiết lộ tên tài khoản có tồn tại hay không.

Do đó:

~~~text
Username không tồn tại -> UsernameNotFoundException ở tầng loadUser
                        -> BadCredentialsException ở provider mặc định

Username tồn tại, password sai -> BadCredentialsException

Username tồn tại, password đúng nhưng bị khóa -> LockedException
~~~

**Không kết luận:** cứ thấy `BadCredentialsException` thì chắc chắn username tồn tại hoặc chắc chắn người dùng đã nhập sai password. Đó là lỗi từ chối bằng chứng ở ranh giới provider; nguyên nhân phía dưới còn tùy cấu hình.

## 3. Hợp đồng UserDetails: boolean dương, lỗi lại là phủ định

Các phương thức trạng thái của `UserDetails` trả **true khi điều kiện bình thường/được phép**, không phải true khi có vấn đề:

~~~java
boolean isAccountNonLocked();        // true = KHÔNG bị khóa
boolean isEnabled();                 // true = tài khoản được bật
boolean isAccountNonExpired();       // true = tài khoản CHƯA hết hạn
boolean isCredentialsNonExpired();   // true = credential CHƯA hết hạn
~~~

Đây là **chữ ký rút gọn** để giải thích hợp đồng, không phải toàn bộ nội dung interface.

| Giá trị trong UserDetails | Bình thường | Khi false | Exception mặc định |
| --- | --- | --- | --- |
| `isAccountNonLocked()` | `true` | Account locked | `LockedException` |
| `isEnabled()` | `true` | Account disabled | `DisabledException` |
| `isAccountNonExpired()` | `true` | Account expired | `AccountExpiredException` |
| `isCredentialsNonExpired()` | `true` | Password/credential expired | `CredentialsExpiredException` |

Nếu sử dụng `User` builder của Spring Security, tên builder thường diễn tả **trạng thái bất thường** (khác chiều boolean của interface):

~~~java
User.withUsername("linh")
    .password(encodedPassword)
    .roles("USER")
    .accountLocked(true)       // isAccountNonLocked() == false
    .disabled(false)           // isEnabled() == true
    .accountExpired(false)     // isAccountNonExpired() == true
    .credentialsExpired(false) // isCredentialsNonExpired() == true
    .build();
~~~

Đây là **đoạn tạo UserDetails tích hợp**, cần `encodedPassword` và import `org.springframework.security.core.userdetails.User`. Các thuộc tính lock/disable/expiry thông thường được ánh xạ từ bản ghi account trong database, LDAP hoặc dịch vụ danh tính.

### Đừng đánh đồng các cờ

**Locked** thường là trạng thái có thể được tạo bởi chính sách chống brute-force, bởi admin, hoặc bởi sự kiện rủi ro. **Disabled** có thể biểu diễn nhân viên đã nghỉ, tài khoản chưa kích hoạt hoặc bị ngừng theo chính sách. **Account expired** thường liên quan mốc hết hạn sử dụng account. **Credentials expired** tập trung vào vòng đời password/credential, không nhất thiết chấm dứt tài khoản.

Không nên dùng một cờ `enabled=false` để đại diện tất cả các trạng thái nếu hệ thống có luồng khôi phục khác nhau. Ngược lại, không nhất thiết phải có bốn cột DB nếu nghiệp vụ không cần: điều quan trọng là logic ánh xạ ra `UserDetails` và các chính sách đi kèm phải rõ ràng, nhất quán.

## 4. Dòng xử lý mặc định của DaoAuthenticationProvider

`DaoAuthenticationProvider` kế thừa `AbstractUserDetailsAuthenticationProvider`. Nó nhận `UsernamePasswordAuthenticationToken` từ filter hoặc caller, tải `UserDetails` (hoặc cache), kiểm account status và password, rồi tạo `Authentication` result.

Một chuỗi khái niệm:

~~~mermaid
flowchart TD
    A["UsernamePasswordAuthenticationToken chưa xác thực"] --> B["ProviderManager / DaoAuthenticationProvider"]
    B --> C{"Tìm UserDetails?"}
    C -->|Không tìm thấy| D["Mặc định BadCredentialsException"]
    C -->|Kho lỗi| E["Lỗi dịch vụ, không giả làm BadCredentials"]
    C -->|Tìm được| F{"Pre-authentication checks"}
    F -->|Locked| L["LockedException"]
    F -->|Disabled| X["DisabledException"]
    F -->|Account expired| Y["AccountExpiredException"]
    F -->|Qua kiểm tra| G["PasswordEncoder.matches(...)"]
    G -->|Sai| H["BadCredentialsException"]
    G -->|Đúng| I{"Post-authentication check"}
    I -->|Credential expired| J["CredentialsExpiredException"]
    I -->|Hợp lệ| K["Authentication đã xác thực"]
~~~

**Chú ý riêng cho bản đã vá từ 6.5.10:** trong luồng kiểm trạng thái, provider có thể **vẫn thực hiện thêm kiểm tra password** ngay cả khi pre-check đã báo lỗi, nhằm giảm lộ trạng thái tài khoản qua timing. Điều này không có nghĩa account được cấp phép; **exception trạng thái ban đầu vẫn là kết quả bị từ chối**. Sơ đồ trên trình bày **thứ tự quyết định chính sách**, không thể hiện mọi phép kiểm phụ trợ nhằm giảm chênh lệch timing.

### 4.1. Pre-authentication checks: khóa → vô hiệu → hết hạn tài khoản

Trong triển khai mặc định, `DefaultPreAuthenticationChecks` kiểm trạng thái theo thứ tự:

1. `!user.isAccountNonLocked()` → `LockedException`.
2. `!user.isEnabled()` → `DisabledException`.
3. `!user.isAccountNonExpired()` → `AccountExpiredException`.

Nếu một user **vừa locked vừa disabled**, lỗi trạng thái được chọn mặc định là **`LockedException`** vì kiểm tra lock đứng trước. Đây là thứ tự của implementation mặc định, không phải một chuẩn nghiệp vụ buộc mọi provider (LDAP, OIDC, JWT, custom) phải làm giống.

Pre-check xảy ra **trước quyết định chấp nhận password**, nhưng ở bản đã vá nó có thể kèm một phép kiểm credential phụ để giảm timing side channel. Vì vậy đừng suy ra từ exception rằng password nhập vào đúng hoặc sai.

### 4.2. Kiểm mật khẩu: BadCredentialsException

`DaoAuthenticationProvider.additionalAuthenticationChecks(...)` dùng `PasswordEncoder.matches(rawPassword, encodedPassword)`. Với credential bị thiếu/null hoặc không khớp, provider ném `BadCredentialsException`.

Password hash trong `UserDetails` phải do một `PasswordEncoder` thích hợp tạo ra, không lưu bản rõ. BCrypt là lựa chọn minh họa dễ hiểu. Với hệ thống production, chọn thuật toán/hệ số theo chính sách bảo mật, quản lý nâng cấp hash và kiểm hiệu năng, không chép mật khẩu demo vào repo thật.

### 4.3. Post-authentication checks: CredentialsExpiredException

Sau khi có kết quả kiểm password hợp lệ, `DefaultPostAuthenticationChecks` kiểm `isCredentialsNonExpired()`. Khi bằng chứng đúng nhưng credential bị đánh dấu hết hạn, nó ném **`CredentialsExpiredException`**. Điều này khác với `AccountExpiredException` (hết hạn account ở pre-check).

Nếu password **vừa sai** và credential cũng hết hạn, đường kiểm password thông thường ném `BadCredentialsException` **trước** khi đi đến post-check. Do đó loại exception trả về có thể là bad credentials, không phải credentials expired. Ngoại lệ trạng thái của user là kết quả **theo thứ tự kiểm tra**, không phải một danh sách tất cả nguyên nhân đồng thời.

### 4.4. Cache hit và dữ liệu account cũ

Nếu bật `UserCache`, một lần xác thực có thể gặp bản `UserDetails` còn lưu trạng thái cũ. Spring Security có cơ chế tải lại user khi check từ cache báo lỗi trong một số nhánh, nhưng điều này **không phải bảo đảm tự động thu hồi account** vừa bị khóa hay password vừa đổi.

Đặc biệt: nếu bản cached còn `accountNonLocked=true` và password cũ khớp, provider có thể xác thực theo snapshot cũ mà không tải trạng thái mới. Đổi trạng thái ở database phải đi kèm invalidation/kiểm phiên/token theo chính sách. `UserCache` mặc định là `NullUserCache`, nhưng nhiều ứng dụng cấu hình cache hoặc dùng session khác ở ngoài provider.

## 5. Kết quả khi có nhiều lỗi đồng thời

Một request không nhất thiết chỉ có một vấn đề. Cần đọc **cơ chế kiểm** thay vì chọn exception ngẫu nhiên.

| Tình trạng UserDetails + credential | Exception theo logic mặc định | Giải thích |
| --- | --- | --- |
| Account bình thường, password sai | `BadCredentialsException` | Password không khớp |
| Username không tồn tại, hideUserNotFoundExceptions=true | `BadCredentialsException` | Không lộ khác biệt username |
| Account locked, password đúng | `LockedException` | Pre-check lock |
| Account disabled, password đúng | `DisabledException` | Pre-check enabled |
| Account expired, password đúng | `AccountExpiredException` | Pre-check account expiry |
| Credential expired, password đúng | `CredentialsExpiredException` | Post-check credential expiry |
| Locked **và** disabled | `LockedException` | Lock được xét trước |
| Disabled **và** account expired | `DisabledException` | Enabled được xét trước account expiry |
| Account expired **và** credentials expired | `AccountExpiredException` | Pre-check account expiry thắng post-check |
| Credential expired **và** password sai | `BadCredentialsException` | Password không qua nên chưa tới post-check |
| Account locked, password sai (provider mặc định đã vá) | `LockedException` | Trạng thái lock vẫn khiến authentication thất bại; kiểm password phụ không đổi exception gốc |
| Kho tài khoản không truy cập được | Thường lỗi dịch vụ như `InternalAuthenticationServiceException` | Không được tự đoán user không tồn tại hay password sai |

Các dòng trên giả định **`DaoAuthenticationProvider` chuẩn** và một `UserDetailsService` trả chính xác cờ trạng thái. Nếu một custom `AuthenticationProvider` hoặc custom `UserDetailsChecker` thay đổi quy tắc, thứ tự và kết quả có thể khác. Với một username chưa tìm thấy, không có đối tượng để kiểm các cờ locked/expired.

## 6. Demo Java 17 chạy độc lập: bảy loại kết quả và thứ tự ưu tiên

Đây là **chương trình console** dùng `DaoAuthenticationProvider` thật của Spring Security, không cần servlet server. Nó tạo dữ liệu tài khoản trong bộ nhớ, hash password bằng BCrypt và đưa request vào `ProviderManager`. Không tự tạo kết quả “authenticated” từ dữ liệu client.

**Phiên bản:** Spring Security **6.5.11**, được công bố là phiên bản 6.5 đã bao gồm bản sửa liên quan đến timing của trạng thái tài khoản. Đây là version để tái hiện ví dụ, **không phải hướng dẫn cố định production ở version này mãi**; ứng dụng thật cập nhật theo phiên bản được bảo trì và advisories mới.

### 6.1. Cấu trúc dự án

~~~text
account-state-exceptions-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/accountstate/
    └── AccountStateExceptionsDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'account-state-exceptions-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.accountstate.AccountStateExceptionsDemo'
}
~~~

### 6.2. Tệp Java đầy đủ

Tạo `src/main/java/example/accountstate/AccountStateExceptionsDemo.java`:

~~~java
package example.accountstate;

import java.util.List;
import java.util.Map;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public class AccountStateExceptionsDemo {

    static final class DemoUsers implements UserDetailsService {
        private final Map<String, UserDetails> accounts;

        DemoUsers(PasswordEncoder encoder) {
            String hash = encoder.encode("correct-password");
            accounts = Map.of(
                    "active", create("active", hash,
                            false, false, false, false),
                    "locked", create("locked", hash,
                            true, false, false, false),
                    "disabled", create("disabled", hash,
                            false, true, false, false),
                    "expired", create("expired", hash,
                            false, false, true, false),
                    "credential-expired", create("credential-expired", hash,
                            false, false, false, true),
                    "locked-and-disabled", create("locked-and-disabled", hash,
                            true, true, false, false),
                    "expired-both", create("expired-both", hash,
                            false, false, true, true)
            );
        }

        private static UserDetails create(
                String username, String passwordHash,
                boolean locked, boolean disabled,
                boolean accountExpired, boolean credentialExpired) {

            return User.withUsername(username)
                    .password(passwordHash)
                    .roles("READER")
                    .accountLocked(locked)
                    .disabled(disabled)
                    .accountExpired(accountExpired)
                    .credentialsExpired(credentialExpired)
                    .build();
        }

        @Override
        public UserDetails loadUserByUsername(String username)
                throws UsernameNotFoundException {
            UserDetails account = accounts.get(username);
            if (account == null) {
                throw new UsernameNotFoundException("Account not found");
            }
            return account;
        }
    }

    private static void attempt(
            AuthenticationManager manager,
            String label, String username, String password) {

        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password);

        try {
            Authentication result = manager.authenticate(request);
            System.out.println(label + " => SUCCESS(authenticated="
                    + result.isAuthenticated() + ")");
        }
        catch (AuthenticationException ex) {
            // Chỉ in loại exception, không in username hoặc credential.
            System.out.println(label + " => "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        UserDetailsService users = new DemoUsers(encoder);

        // Constructor rõ UserDetailsService cho Spring Security 6.5.
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        AuthenticationManager manager =
                new ProviderManager(List.of(provider));

        attempt(manager, "valid", "active", "correct-password");
        attempt(manager, "wrong-password", "active", "wrong");
        attempt(manager, "unknown-user", "not-here", "correct-password");
        attempt(manager, "locked", "locked", "correct-password");
        attempt(manager, "disabled", "disabled", "correct-password");
        attempt(manager, "account-expired", "expired", "correct-password");
        attempt(manager, "credentials-expired",
                "credential-expired", "correct-password");
        attempt(manager, "locked-plus-disabled",
                "locked-and-disabled", "correct-password");
        attempt(manager, "expired-account-plus-credentials",
                "expired-both", "correct-password");
        attempt(manager, "locked-with-wrong-password",
                "locked", "wrong");
    }
}
~~~

**Vì sao mã này đáng tin trong phạm vi demo?**

- `DemoUsers` triển khai hợp đồng `UserDetailsService`, trả bản `UserDetails` thực và ném `UsernameNotFoundException` khi không có username.
- Mật khẩu được lưu dưới dạng **BCrypt hash**. `DaoAuthenticationProvider` kiểm mật khẩu; không có provider “accept all”.
- Tất cả account dùng cùng một password demo để chỉ thay đổi **flags trạng thái**, giúp nhìn đúng exception do trạng thái.
- `DaoAuthenticationProvider(users)` và `setPasswordEncoder(encoder)` phù hợp API 6.5.11; không dùng constructor rỗng đã deprecated.
- `ProviderManager` chỉ có một provider, nên kết quả không bị thay bởi provider fallback thứ hai. Khi account bị locked/disabled/expired, manager không trả success.
- `attempt` không đặt kết quả vào `SecurityContextHolder`, vì đây là console test tầng manager, không phải luồng HTTP.
- Chương trình chỉ in loại exception và cờ `isAuthenticated` của **kết quả thành công**; tuyệt đối không in password, hash hay token.

### 6.3. Chạy bằng Gradle

Từ thư mục `account-state-exceptions-demo` với JDK 17+ và Gradle/Gradle Wrapper tương thích:

~~~bash
gradle run --quiet
~~~

Nếu có Wrapper, dùng `./gradlew run --quiet`; trên Windows PowerShell dùng `.\gradlew.bat run --quiet`.

Kết quả từ các dòng `System.out.println` của chương trình, không tính log của Gradle:

~~~text
valid => SUCCESS(authenticated=true)
wrong-password => BadCredentialsException
unknown-user => BadCredentialsException
locked => LockedException
disabled => DisabledException
account-expired => AccountExpiredException
credentials-expired => CredentialsExpiredException
locked-plus-disabled => LockedException
expired-account-plus-credentials => AccountExpiredException
locked-with-wrong-password => LockedException
~~~

Những dòng này phụ thuộc logic `DaoAuthenticationProvider` chuẩn ở phiên bản đã ghi. Trình tự output do `main` quyết định; chuỗi hash BCrypt ngẫu nhiên không bị in nên đầu ra ổn định. Bản vá timing có thể làm số phép kiểm password khác so với phiên bản cũ, nhưng **không đổi loại exception trạng thái cuối** của những tình huống này.

### 6.4. Đọc ba trường hợp dễ nhầm

**`wrong-password` và `unknown-user` cùng BadCredentialsException:** trường hợp một có user nhưng password không khớp; trường hợp hai không có user, provider mặc định che `UsernameNotFoundException`. Không thể suy ra tên tài khoản tồn tại chỉ từ loại exception trả về.

**`locked-plus-disabled` cho LockedException:** default pre-check xét locked trước disabled, nên locked được báo đầu tiên. Không kết luận disabled flag là false; code đã cố tình đặt cả hai true ở builder.

**`locked-with-wrong-password` vẫn LockedException:** với bản vá 6.5.11, provider có thể kiểm credential phụ nhằm giảm rủi ro timing nhưng vẫn giữ lại quyết định trạng thái locked. Không dùng kết quả này để đoán password người dùng đã gõ đúng hay sai.

## 7. Nếu tài khoản vừa locked vừa có phiên đang đăng nhập?

`UserDetails` chứa trạng thái dành cho **lần xác thực mới**. Một lần login bằng form có thể tạo `Authentication` trong `SecurityContext` và lưu vào session. Nếu admin khóa user **sau đó**, session đang tồn tại không nhất thiết tự hủy hoặc đọc lại `UserDetails` trong mọi request.

Tương tự, JWT bearer access token đã phát hành có thể chứa scope/role đến khi hết hạn. Việc đổi cờ `isEnabled` hoặc `isAccountNonLocked` trong database, hoặc làm mới `UserDetails` cache, **không tự sửa claims đã ký trong JWT**.

| Hành động | Lần xác thực username/password mới | Session hiện có | JWT hiện có |
| --- | --- | --- | --- |
| Khóa account và cập nhật nguồn user | Provider có thể từ chối bằng `LockedException` nếu đọc dữ liệu mới | Có thể còn hiệu lực đến khi bị vô hiệu theo chính sách | Có thể còn được chấp nhận tới khi token bị từ chối/hết hạn |
| Disable account | Có thể từ chối bằng `DisabledException` | Không tự hết hạn chỉ vì đổi DB | Không tự đổi claim |
| Đánh dấu password expired | Có thể từ chối bằng `CredentialsExpiredException` | Phải quyết định có buộc re-authentication không | Phải quyết định chính sách revoke/step-up riêng |
| Account expired | Có thể từ chối bằng `AccountExpiredException` | Cần chính sách hủy phiên hoặc kiểm lại trạng thái | Cần chính sách token lifetime/revocation riêng |

Nếu yêu cầu nghiệp vụ là “khóa tài khoản phải có hiệu lực tức thì”, phải thiết kế thêm: **evict mọi cache liên quan, vô hiệu session/remember-me và có cơ chế kiểm/thu hồi token hoặc kiểm security version trên request nhạy cảm**. Đừng giả định exception của lần đăng nhập mới tự động chặn mọi đường truy cập đang mở.

### 7.1. Vì sao cache cần được nhắc đến?

Giả sử `UserDetails` trong cache đang có `isAccountNonLocked=true`. Admin cập nhật account thành locked trong database nhưng không evict cache. Một request xác thực mới có thể đọc lại user cũ từ cache và không biết trạng thái đã đổi. Cần xử lý eviction sau commit, đồng bộ nhiều instance và kiểm race condition.

`UserCache` tại provider và `Authentication` đã nằm trong session là **hai nơi lưu trữ khác nhau**. Xóa nơi thứ nhất không tự cập nhật nơi thứ hai.

## 8. Ảnh hưởng đến thứ tự AuthenticationProvider và fallback

`ProviderManager` có thể có danh sách `AuthenticationProvider`. Với một số loại lỗi như `BadCredentialsException`, nó có thể thử provider khác cùng hỗ trợ request; nếu provider sau thành công, kết quả thành công được dùng. Với **`AccountStatusException`**, nó có đường dừng sớm để không thử tiếp provider khác/parent.

Cụ thể:

| P1 | P2 có cùng khả năng xử lý | Hành vi |
| --- | --- | --- |
| `BadCredentialsException` | P2 có thể nhận credential | **Có thể tiếp tục** tới P2 và thành công |
| `LockedException` | P2 có thể nhận credential | **Dừng ngay**; không dùng P2 để vượt account locked |
| `DisabledException` | P2 có thể nhận credential | **Dừng ngay** |
| `AccountExpiredException` | P2 có thể nhận credential | **Dừng ngay** |
| `CredentialsExpiredException` | P2 có thể nhận credential | **Dừng ngay** |

**Cảnh báo thiết kế:** nếu app có LDAP provider trước và local provider sau, lỗi `BadCredentialsException` của LDAP không tự bảo đảm local sẽ bị bỏ qua. Đây có thể là chính sách login đa nguồn có chủ ý hoặc lỗ hổng fallback ngoài ý muốn.

Tương tự, **đừng đánh tráo lỗi hạ tầng** thành `BadCredentialsException` để cho fallback mà không có thiết kế. `InternalAuthenticationServiceException` cũng là loại khiến `ProviderManager` dừng ngay trong các luồng chuẩn. Đưa exception đúng là một phần của chính sách xác thực.

### `supports(...)` không xác nhận account có hợp lệ

`AuthenticationProvider.supports(Class<?>)` chỉ cho biết provider có thể xử lý kiểu `Authentication`; nó không kiểm username, password hay trạng thái locked. Vì vậy không đặt logic “account đang bị khóa” vào `supports` và không mong `supports=false` đồng nghĩa credential bị từ chối.

## 9. Từ exception Java đến HTTP, trang đăng nhập và API

Ở tầng manager/provider, kết quả là **`Authentication` hoặc `AuthenticationException`**. Tầng Servlet Security (authentication filter, failure handler, `AuthenticationEntryPoint`, `ExceptionTranslationFilter`) quyết định phản hồi HTTP.

- **HTTP Basic:** nhiều cấu hình mặc định trả **401 Unauthorized** cho các `AuthenticationException`, kể cả một số lỗi trạng thái. Không mặc định có mã HTTP riêng cho locked/disabled.
- **Form login:** thường redirect đến trang đăng nhập/lỗi hoặc gọi `AuthenticationFailureHandler`; không mặc định trả JSON `{"error":"LockedException"}`.
- **REST API custom:** có thể thiết kế mã lỗi công khai và thông điệp riêng, nhưng chỉ khi đã đánh giá **user enumeration**, lạm dụng reset, hỗ trợ khách hàng và chính sách công khai.
- **403 Forbidden:** thường liên quan **principal đã xác thực nhưng thiếu quyền**, không phải mã bắt buộc cho `LockedException` tại bước login.

**Không quy đổi đơn giản:** `LockedException == HTTP 423`, `DisabledException == HTTP 403` hay `CredentialsExpiredException == HTTP 401` trong mọi Spring Security app. Những ánh xạ này **không phải quy tắc tự động** của `DaoAuthenticationProvider`.

### 9.1. Thông báo an toàn cho người dùng

Ở endpoint đăng nhập công khai, một thông điệp thống nhất như:

> Không thể đăng nhập bằng thông tin đã cung cấp. Vui lòng kiểm tra lại hoặc dùng quy trình khôi phục tài khoản.

có thể giảm việc đoán username tồn tại. Với người dùng đã có phiên tin cậy hoặc đã qua bước xác minh thích hợp, UI có thể thông báo chi tiết hơn rằng cần đổi mật khẩu, account đang chờ kích hoạt hoặc cần hỗ trợ mở khóa. **Mức chi tiết phải dựa trên chính sách và độ tin cậy của kênh phản hồi**, không phải chỉ dựa vào tên exception.

Đối với tài khoản disabled do quyết định quản trị, ứng dụng có thể không cho self-service “bật lại” bằng một nút bấm. Đối với account locked do nhiều lần sai mật khẩu, có thể thiết kế bước chờ, email xác minh hoặc hỗ trợ bảo mật. Đối với credentials expired, cần **flow thay đổi mật khẩu được bảo vệ riêng**, không cho phép một token đã bị từ chối ở login thông thường trở thành quyền truy cập toàn bộ API.

### 9.2. Login thất bại có được tính là yêu cầu đã xác thực?

Không. Một `AuthenticationException` chỉ ra rằng provider **chưa trả kết quả Authentication thành công**. Dù user object được tải và status được biết ở nội bộ, controller bảo vệ vẫn không được coi request là authenticated. Event/failure handling có thể ghi nhận lớp lỗi để audit, nhưng không “giữ lại token cũ” để cho request này đi qua.

## 10. Chính sách trạng thái trong database và hệ thống danh tính

Một số bảng tài khoản có các trường:

~~~text
user_id              : định danh ổn định
username             : tên đăng nhập
password_hash        : hash đã encode
enabled              : true/false
locked_until         : timestamp hoặc null
account_expires_at   : timestamp hoặc null
password_changed_at  : timestamp
password_expires_at  : timestamp hoặc null
failed_attempts      : số lần nhập sai trong cửa sổ kiểm soát
security_version     : phiên bản trạng thái bảo mật
~~~

Đây là **mô hình tham khảo**, không phải schema mặc định bắt buộc của Spring Security.

Quá trình map `UserDetails` có thể:

- `isAccountNonLocked`: true nếu chưa bị khóa hoặc `locked_until` đã qua theo đồng hồ/chính sách đúng.
- `isEnabled`: true khi account đang được bật bởi chủ sở hữu hệ thống.
- `isAccountNonExpired`: true nếu chưa qua `account_expires_at`.
- `isCredentialsNonExpired`: true nếu credential chưa vượt `password_expires_at`.

Dùng nguồn thời gian nhất quán, xử lý UTC/time zone hợp lý; không so sánh ngày/giờ bằng chuỗi theo locale. Với cột lưu “vĩnh viễn” (null), quy ước phải được ghi rõ. Tránh để default database hoặc mapping đối nghịch gây ra việc khóa sai hàng loạt.

### 10.1. DaoAuthenticationProvider không tự dựng hệ thống lockout

`DaoAuthenticationProvider` đọc **trạng thái được trả trong `UserDetails`**; nó không tự động đếm login sai, đặt `locked_until` hoặc gửi email unlock chỉ vì có `BadCredentialsException`. Ứng dụng phải triển khai chính sách thất bại/khóa ở đúng tầng, cân nhắc race khi nhiều request và đặc biệt tránh để kẻ tấn công khóa hàng loạt account người dùng chỉ bằng username.

Ví dụ workflow ở mức nghiệp vụ:

~~~text
credential attempt
    -> provider kiểm evidence và status
    -> nếu thất bại, thành phần audit/rate limiter nhận failure
    -> tính chính sách chống brute-force theo account/IP/device/risk
    -> nếu cần khóa, cập nhật account ở source of truth
    -> evict UserDetails cache liên quan
    -> xử lý session/token theo yêu cầu
    -> lần authentication mới đọc UserDetails với isAccountNonLocked=false
~~~

Không ghi password plaintext, bearer token hoặc hash vào event. Nếu dùng `AuthenticationFailureBadCredentialsEvent` và các sự kiện Spring Security, cần cấu hình `AuthenticationEventPublisher` thích hợp và hiểu sự khác biệt giữa event từ manager và handler của filter. Đừng giả định toàn hệ thống luôn phát mọi sự kiện thất bại khi chưa bật cấu hình tương ứng.

### 10.2. Reset password và credential expired

Nếu `credentialsNonExpired=false`, login thông thường sẽ bị chặn dù password đúng. Quy trình **đổi mật khẩu** phải có bằng chứng riêng, ví dụ reset token một lần có TTL/ngữ cảnh rõ hoặc step-up đã được xác minh qua kênh khác. Sau khi reset thành công, cập nhật hash và thời điểm, đưa trạng thái credentials trở lại hợp lệ, invalidate UserDetails cache, thu hồi reset token cũ và áp dụng chính sách với session/token đã tồn tại.

Không đề nghị developer “tạm đặt credentialsNonExpired=true từ request” để cho người dùng đi qua mọi endpoint rồi mới đổi mật khẩu. Cách làm đó trao quyền trước khi xác minh/khắc phục trạng thái.

### 10.3. Khóa và hết hạn cần quyết định khả năng phục hồi khác nhau

- **Locked:** có thể mở khi thời hạn khóa trôi qua, sau xác minh hoặc khi admin can thiệp; phải xác định hành động được phép khi đang khóa.
- **Disabled:** thường do chính sách admin, HR hoặc luồng chưa kích hoạt; không tự động mở chỉ bằng nhập lại password.
- **Account expired:** có thể yêu cầu gia hạn hợp đồng/đăng ký hoặc quy trình tái cấp quyền.
- **Credentials expired:** có thể yêu cầu đổi mật khẩu hoặc cấp lại credential đã xác thực.

Một error handler duy nhất cho cả bốn case có thể phù hợp với **phản hồi đăng nhập công khai**, nhưng backend vẫn nên giữ **mã trạng thái nội bộ riêng** cho audit và workflow.

## 11. Bảo mật về thời gian phản hồi: advisory năm 2026

Spring Security đã công bố **CVE-2026-22746 — User Attribute Enumeration when Using DaoAuthenticationProvider** vào ngày **20/04/2026**. Một số phiên bản trước bản vá có thể để lộ thông tin về trạng thái enabled/expired/locked thông qua khác biệt timing khi cơ chế kiểm trạng thái bỏ qua một bước bảo vệ.

Theo advisory chính thức:

- Spring Security `6.5.0–6.5.9` thuộc dải ảnh hưởng.
- **`6.5.10`** là bản sửa OSS trong dòng 6.5.
- Ví dụ dùng **`6.5.11`**, sau bản sửa.
- Những dòng khác có mức bản vá riêng; chọn phiên bản đã được nhà cung cấp cập nhật và còn được hỗ trợ.

**Điểm kỹ thuật:** ở bản đã vá, thuộc tính `setAlwaysPerformAdditionalChecksOnUser(...)` cho phép điều chỉnh việc chạy additional checks ngay cả khi pre-authentication status check thất bại. Cài mặc định của bản vá ưu tiên chống timing leakage. Không đặt nó về `false` chỉ để “tối ưu hiệu năng” khi chưa đánh giá rủi ro và không tự kết luận rằng mọi timing khác biệt sẽ bằng 0.

**Một exception vẫn có thể tiết lộ thông tin nếu được trả nguyên văn cho client.** Bản vá timing không thay thế chính sách lỗi công khai, rate limiting, audit và kiểm thử về user enumeration.

Tài liệu gốc: https://spring.io/security/cve-2026-22746

## 12. Kiểm thử: trạng thái phải được đo ở đúng tầng

Một ứng dụng cần ít nhất ba nhóm test: **provider**, **filter/HTTP** và **cập nhật trạng thái đã lưu**.

### 12.1. Test provider như ví dụ console

Mọi test xây `UsernamePasswordAuthenticationToken.unauthenticated(username, password)` và gọi manager/provider thật với `UserDetailsService`/`PasswordEncoder`. Kiểm type exception bằng assert của JUnit hoặc phương thức tương đương. Demo `main` đã in những trường hợp quan trọng.

Test nên có cả:
- valid + correct password → success `Authentication.isAuthenticated=true`;
- valid + wrong password → `BadCredentialsException`;
- unknown username → `BadCredentialsException` theo mặc định;
- locked → `LockedException`;
- disabled → `DisabledException`;
- account expired → `AccountExpiredException`;
- credentials expired → `CredentialsExpiredException`;
- locked + disabled → loại được ưu tiên là `LockedException`;
- account expired + credentials expired → `AccountExpiredException`;
- credentials expired + wrong password → `BadCredentialsException`;
- locked + wrong password → **không** bypass locked; kiểm hành vi bản vá.

### 12.2. Test HTTP integration

Với `MockMvc` cùng filter Spring Security thật hoặc end-to-end HTTP:

| Case | Kỳ vọng ở provider | Kỳ vọng HTTP phải xác minh trong app |
| --- | --- | --- |
| Không có credential cho endpoint bảo vệ | Không nhất thiết gọi provider | Thường 401 hoặc redirect login |
| Sai password | `BadCredentialsException` | Form failure/Basic entry point xử lý |
| Locked | `LockedException` | Không có `Authentication` thành công; public response theo policy |
| Disabled | `DisabledException` | Không gọi controller bảo vệ |
| Expired account | `AccountExpiredException` | Không cho vào endpoint thông thường |
| Expired password | `CredentialsExpiredException` | Chỉ có thể thực hiện luồng reset thích hợp |
| Password đúng, thiếu quyền | Xác thực **thành công** | Thường 403 tại authorization |

**Chú ý:** `@WithMockUser` thiết lập user giả cho test authorization; nó **không** xác minh `DaoAuthenticationProvider`, BCrypt hoặc các exception account status. Khi test logic này, request phải đi qua filter/provider phù hợp hoặc gọi manager thật.

### 12.3. Test race, thay đổi trạng thái và các session cũ

Một bộ test production nên cover:

1. Đổi enabled/locked khi người dùng đang gửi nhiều login request song song.
2. Cập nhật DB đã commit rồi cache vẫn có snapshot cũ.
3. Multi-instance: node A khóa user, node B vẫn có cache entry.
4. Session đã đăng nhập trước khi account bị khóa.
5. Bearer JWT còn hạn sau khi user bị disable.
6. Chuyển ngày hết hạn account/credential qua ranh giới UTC/time zone.
7. Đổi password và đảm bảo password **cũ** không còn được chấp nhận.
8. Mở khóa account và xóa failed-attempt counters đúng chính sách.
9. Một actor độc hại cố khóa account của người khác bằng cách thử nhiều mật khẩu sai.
10. Public response không tiết lộ khác biệt có thể khai thác giữa user missing, locked và disabled.

## 13. Observability: phân loại nội bộ nhưng tránh lộ thông tin

Hãy tách **thông báo công khai** và **telemetry riêng tư**.

| Tín hiệu nội bộ | Mục đích | Điều không được log |
| --- | --- | --- |
| `auth.failure=BAD_CREDENTIALS` | Theo dõi tấn công guessing hoặc lỗi nhập password | Mật khẩu/plaintext, password hash |
| `auth.failure=ACCOUNT_LOCKED` | Theo dõi lockout, hỗ trợ mở khóa | Raw username hoặc PII nếu không cần |
| `auth.failure=ACCOUNT_DISABLED` | Theo dõi policy disable | Thông tin HR/quản trị nhạy cảm |
| `auth.failure=ACCOUNT_EXPIRED` | Theo dõi hết thời hạn account | Dữ liệu hợp đồng/khách hàng không cần thiết |
| `auth.failure=CREDENTIALS_EXPIRED` | Theo dõi yêu cầu reset/rotate credential | Raw reset token, bearer token |
| `auth.failure=STORE_UNAVAILABLE` | Phát hiện lỗi nguồn danh tính | Connection string có secret |
| `auth.success=true` | Số lần xác thực thành công | Toàn bộ `Authentication.toString()`, session cookie |

Chỉ dùng nhãn metric có cardinality hữu hạn như `outcome`/`provider`, không nhúng username làm label. Khi cần audit theo account, dùng định danh nội bộ được bảo vệ và retention phù hợp. Thông báo công khai nên hạn chế user enumeration và lạm dụng self-service reset.

### 13.1. Đừng dự đoán mã lỗi chỉ từ HTTP

Một API HTTP Basic có thể trả 401 cho cả wrong password, locked, disabled và expired tùy entry point. Do đó dashboard chỉ đếm 401 sẽ không phân biệt được tấn công nhập sai, khóa tài khoản, hết hạn chính sách hoặc lỗi kho.

Theo dõi exception tại manager/provider hoặc authentication failure events (đã cấu hình). Khi có nhiều providers, phải biết exception cuối có thể bị provider sau thay thế nếu lỗi thường cho phép fallback; đối với `AccountStatusException` đường đi dừng ngay.

## 14. Anti-pattern và cách sửa

| Anti-pattern | Vấn đề | Hướng sửa |
| --- | --- | --- |
| Dùng `BadCredentialsException` cho mọi tình trạng account | Mất ngữ nghĩa locked/disabled/expiry; có thể thay đổi fallback | Trả đúng flags `UserDetails` hoặc exception phù hợp |
| Thấy `BadCredentialsException` rồi kết luận user có tồn tại | Username missing có thể bị che thành cùng exception | Giữ phân loại lookup nội bộ; public response thống nhất |
| Map `locked=true` của DB vào `isAccountNonLocked() == true` | Đảo ngược boolean dẫn tới cho phép user bị khóa | Test kỹ phép ánh xạ và builder |
| Đổi `isEnabled` trong DB nhưng không xử lý UserCache/session | Account vẫn có thể truy cập bằng snapshot/phiên cũ | Invalidation và revocation theo SLA |
| Tự ném `LockedException` khi password sai để “chống dò” | Mất ngữ nghĩa và có thể khóa vô tội vạ | Thiết kế rate limiting/lockout độc lập |
| Đưa chính xác “User linh bị khóa” ra API công khai | Tạo cơ hội enumeration | Thông báo chung hoặc kênh đã xác minh |
| Coi `CredentialsExpiredException` là “tài khoản đã bị xóa” | Không đúng: credential hết hạn, account vẫn có thể tồn tại | Flow reset/rotate có kiểm chứng |
| Coi `AccountExpiredException` giống password expired | Thao tác gia hạn khác thay password | Tách domain/account lifecycle khỏi credential lifecycle |
| Tạo `Authentication.authenticated(...)` trực tiếp từ client | Bỏ qua password/status checks | Dùng manager/provider đáng tin |
| Chỉ test `@WithMockUser` rồi kết luận exception đúng | Bỏ qua đường xác thực thật | Test provider/manager và HTTP filter |
| Tự ánh xạ tất cả lỗi sang HTTP 403/423 | Đó không phải hành vi mặc định; có thể lộ trạng thái | Thiết kế entry point/failure handler theo policy |
| Bỏ qua CVE/timing của phiên bản cũ | Có thể lộ thuộc tính locked/disabled/expired | Cập nhật bản vá và kiểm timing/public messages |
| Dùng nhiều provider nhưng không kiểm fallback | Một provider sau có thể nhận credential khi P1 từ chối | Xác định realm, thứ tự, exception và trust boundary |
| Gửi raw exception message/stack trace về browser | Rò rỉ thiết kế nội bộ, username hoặc dependency | Tách audit nội bộ với response công khai |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `user.isAccountNonLocked()` trả `false`, mật khẩu đúng. Exception nào?  
**Đáp án:** `LockedException` trong `DaoAuthenticationProvider` mặc định.

**Câu 2.** User có `isEnabled=false` và `isAccountNonExpired=false`. Exception nào được ưu tiên?  
**Đáp án:** `DisabledException`, vì pre-check enabled đi trước account expiry (với checker mặc định).

**Câu 3.** User có `isCredentialsNonExpired=false` nhưng password nhập vào sai. Exception nào theo đường kiểm chuẩn?  
**Đáp án:** `BadCredentialsException`, vì kiểm password không qua nên chưa tới post-check credentials expiry.

**Câu 4.** User không tồn tại, nhưng provider báo `BadCredentialsException`. Có bất thường không?  
**Đáp án:** Không. `hideUserNotFoundExceptions=true` mặc định che `UsernameNotFoundException`.

**Câu 5.** Account bị khóa. Có thể chỉ cần đổi cookie session để login lại thành công không?  
**Đáp án:** Không có kết luận chung. Lần password authentication mới dùng `UserDetails` mới có thể bị khóa. Tuy nhiên một session/token **đã phát hành** là trạng thái khác: phải có chính sách vô hiệu riêng, không chỉ dựa vào exception mới.

**Câu 6.** `LockedException` có thể là lý do để `ProviderManager` thử provider local khác không?  
**Đáp án:** Không theo cơ chế chuẩn. Đây là `AccountStatusException` nên manager dừng ngay, tránh provider khác bypass account status.

**Câu 7.** Spring Security tự động khóa username khi nhập sai password năm lần có đúng không?  
**Đáp án:** Không có quy tắc đó chỉ từ `DaoAuthenticationProvider`; ứng dụng phải xây chính sách rate limit/failed attempts, xử lý concurrency và lưu trạng thái hợp lệ.

**Câu 8.** Vì sao bản demo dùng Spring Security 6.5.11 thay vì 6.5.9?  
**Đáp án:** Advisory 2026 về timing khi tài khoản disabled/expired/locked nêu 6.5.9 nằm trong dải ảnh hưởng và 6.5.10 có bản sửa OSS. 6.5.11 nằm sau bản sửa này.

**Câu 9.** Có thể hiển thị trang “Mật khẩu đã hết hạn” cho mọi yêu cầu login công khai không?  
**Đáp án:** Cần đánh giá user enumeration. Một kênh đã xác minh danh tính có thể đưa thông tin chi tiết hơn; client chưa được xác minh nên thường nhận thông báo chung và lựa chọn recovery an toàn.

**Câu 10.** Vì sao account locked và password sai đồng thời có thể vẫn báo `LockedException` trên 6.5.11?  
**Đáp án:** Pre-authentication checker chọn trạng thái lock; bản vá có thể thực hiện kiểm mật khẩu phụ để giảm timing, nhưng quyết định từ chối do lock được bảo toàn. Không dùng exception để suy ra password có đúng hay không.

**Câu 11.** Người dùng đã login trước khi bị disable, request API tiếp theo có chắc bị `DisabledException` không?  
**Đáp án:** Không chắc. Nếu sử dụng session hoặc JWT cũ, request có thể không chạy lại `DaoAuthenticationProvider`. Cần chính sách revocation/revalidation.

**Câu 12.** Username hợp lệ, password đúng nhưng thiếu authority `reports.read`. Đây có phải `CredentialsExpiredException` không?  
**Đáp án:** Không. Đó là **authorization failure**, thường HTTP 403, không phải một trong các lỗi xác thực account status.

## 16. Checklist trước khi dùng trong production

- [ ] Mapping `UserDetails` đúng chiều bốn boolean; có test cho lock/disable/2 loại expiry.
- [ ] Password dùng encoder an toàn, không log raw credential và không cấp token thành công khi trạng thái không hợp lệ.
- [ ] Dùng bản Spring Security đã vá theo advisory mới nhất; xác nhận BOM tương thích nếu dự án dùng Spring Boot.
- [ ] Exception được phân loại nội bộ đúng: bad credential, missing user, status failure, store unavailable.
- [ ] Public login response phù hợp chính sách chống user enumeration và brute-force.
- [ ] Các luồng lock, unlock, disable, renew account, reset password có kiểm chứng quyền và audit.
- [ ] Update DB gắn với evict `UserDetails` cache; xử lý concurrency và nhiều instance nếu cần.
- [ ] Có chính sách với session/remember-me/token đã phát hành, không ngộ nhận chỉ đổi status DB là logout toàn bộ.
- [ ] Test `ProviderManager` với nhiều provider và thứ tự fallback.
- [ ] HTTP integration test dùng filter thật và xác minh phản hồi thay vì chỉ dự đoán từ tên exception.
- [ ] Có monitoring cho các loại lỗi mà không làm lộ PII/secret.

**Thông điệp cốt lõi:** `BadCredentialsException` nói rằng **bằng chứng không được chấp nhận**; `LockedException`, `DisabledException`, `AccountExpiredException` và `CredentialsExpiredException` biểu diễn các **điều kiện account/credential khiến xác thực không thể hoàn tất**. Chúng đều ngăn tạo kết quả `Authentication` thành công, nhưng có **ngữ nghĩa nghiệp vụ, thứ tự kiểm tra và tác động fallback khác nhau**. Muốn quản lý tài khoản an toàn, phải phân loại đúng exception ở backend, giới hạn thông tin công khai và xử lý riêng session/token/caches đã tồn tại.

### Tài liệu nguồn

- Spring Security 6.5 — `DaoAuthenticationProvider` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- Spring Security 6.5 — `AbstractUserDetailsAuthenticationProvider` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html
- Spring Security — `AccountStatusException` và các lớp con: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AccountStatusException.html
- Spring Security — `CredentialsExpiredException`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/CredentialsExpiredException.html
- Spring Security — `DaoAuthenticationProvider` flow: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — `UserDetails` và quản lý người dùng: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details.html
- Spring Security advisory **CVE-2026-22746**: https://spring.io/security/cve-2026-22746
