# isAccountNonExpired và thời hạn sử dụng tài khoản

Trong Spring Security, **`UserDetails.isAccountNonExpired()`** là một cờ trạng thái trả lời câu hỏi: **“Tại thời điểm xác thực, tài khoản này còn được phép sử dụng về mặt thời hạn hay không?”**. Giá trị **`true`** nghĩa là *chưa hết hạn*; giá trị **`false`** nghĩa là *đã hết hạn* và thường dẫn đến **`AccountExpiredException`** trong luồng xác thực username/password chuẩn của `DaoAuthenticationProvider`.

Điều quan trọng: Spring Security **không tự suy ra ngày hết hạn của tài khoản từ database, JWT hay HTTP session**. `isAccountNonExpired()` chỉ là một hợp đồng boolean. Ứng dụng phải quyết định thế nào là hết hạn, lưu quy tắc và dữ liệu cần thiết, tính cờ chính xác khi tạo `UserDetails`, đồng thời xử lý những session/token đã được phát trước thời điểm tài khoản hết hạn.

Bài học thuộc nhóm **Trạng thái tài khoản** trong Spring Security Authentication. Nội dung gồm ngữ nghĩa của cờ, ranh giới với các trạng thái khác, thiết kế ngày hết hạn và quy tắc thời gian, ánh xạ entity → UserDetails, hành vi provider, ví dụ Java 17 chạy được, lỗi thường gặp, kiểm thử và các bài toán production.

## 1. Hợp đồng isAccountNonExpired()

`org.springframework.security.core.userdetails.UserDetails` định nghĩa method:

~~~java
boolean isAccountNonExpired();
~~~

Đây là **chữ ký của API Spring Security**, không phải chương trình độc lập. Theo hợp đồng:

- Trả **`true`** khi account vẫn còn hiệu lực và *chưa hết hạn*.
- Trả **`false`** khi account đã hết hạn và không thể được xác thực bằng luồng username/password tiêu chuẩn đang dùng cờ đó.
- Tên method ở dạng phủ định kép: **`NonExpired`** nghĩa là *chưa hết hạn*. Đừng đảo ngược semantics khi map từ tên cột `expired` hoặc `expiresAt`.
- Bản thân method không nêu ngày giờ, không thực hiện truy vấn DB, không quyết định grace period và không biết chính sách subscription; mọi logic đó do ứng dụng sở hữu.
- Ở các phiên bản `UserDetails` hiện đại, method có triển khai mặc định trả `true` nếu custom class không override. Nếu doanh nghiệp có policy hết hạn, **không dựa vào mặc định đó** để coi tài khoản là hợp lệ.

Trong class `org.springframework.security.core.userdetails.User` do Spring Security cung cấp, có thể tạo `UserDetails` bằng builder:

~~~java
UserDetails user = User.withUsername("linh")
        .password(encodedPassword)
        .authorities("notes:read")
        .accountExpired(false)
        .build();
~~~

Đây là **đoạn tích hợp minh họa**, `encodedPassword` và imports cần được cung cấp. Điểm dễ nhầm:

| Giá trị truyền vào builder | Giá trị `isAccountNonExpired()` | Nghĩa |
|---|---|---|
| `.accountExpired(false)` | `true` | Tài khoản chưa hết hạn |
| `.accountExpired(true)` | `false` | Tài khoản đã hết hạn |

Tên setter builder là **`accountExpired(boolean)`**, còn getter của `UserDetails` là **`isAccountNonExpired()`**. Chúng có ý nghĩa *ngược chiều*. Một lỗi đảo dấu có thể làm tài khoản hết hạn vẫn đăng nhập được hoặc khóa nhầm tất cả người dùng.

### 1.1. Cờ này kiểm tra “tài khoản”, không chỉ password

Giả sử một công ty thuê tài khoản sử dụng hệ thống đến ngày 30/11. Người dùng vẫn nhớ đúng mật khẩu và mật khẩu chưa hết hạn, nhưng sau khi quyền sử dụng account kết thúc, `isAccountNonExpired()` phải trả `false` theo policy tương ứng. Điều kiện mật khẩu đúng là **cần nhưng không đủ**.

Ngược lại, người dùng có account hợp lệ đến năm sau nhưng tổ chức buộc đổi mật khẩu sau 90 ngày: đó là **`isCredentialsNonExpired()`**, không phải account expiration. Hệ thống phải phân biệt để hướng người dùng tới hành động phù hợp.

## 2. So sánh bốn cờ của UserDetails

| Method | Khi trả `false` | Ngoại lệ thường gặp trong `DaoAuthenticationProvider` | Giải pháp nghiệp vụ |
|---|---|---|---|
| `isEnabled()` | Account chưa kích hoạt hoặc bị vô hiệu hóa | `DisabledException` | Kích hoạt, xác minh điều kiện, quản lý trạng thái |
| `isAccountNonLocked()` | Account đang bị khóa | `LockedException` | Mở khóa theo chính sách, chống brute-force |
| `isAccountNonExpired()` | Thời hạn sử dụng **account** đã hết | **`AccountExpiredException`** | Gia hạn/đổi gói/duyệt lại quyền sử dụng |
| `isCredentialsNonExpired()` | Mật khẩu/credential đã hết hạn | `CredentialsExpiredException` | Đổi/reset credential theo luồng an toàn |

Các cờ này **độc lập về khái niệm**. Một account có thể vừa bị khóa, vừa đã quá ngày hết hạn; hệ thống cần xác định và ưu tiên chính sách tương ứng. `DaoAuthenticationProvider` thường kiểm tra lock/disabled/account expiry trong giai đoạn pre-authentication, và credential expiry ở post-authentication. Khi nhiều trạng thái sai đồng thời, đừng viết nghiệp vụ dựa trên việc ngoại lệ nào “chắc chắn xuất hiện trước” ở mọi provider hoặc mọi phiên bản.

Quan trọng hơn, **`isAuthenticated()` trên một `Authentication` thành công không có nghĩa account sẽ hợp lệ vĩnh viễn**. Nó mô tả kết quả một lần xác thực; account status có thể thay đổi sau đó.

### 2.1. Account expiration khác session expiration và JWT expiration

~~~text
Account expiresAt = 2026-11-10T00:00:00Z
Session timeout  = 30 phút không hoạt động
JWT exp          = 2026-11-12T00:00:00Z
Password expiry  = 2026-12-01T00:00:00Z
~~~

Đây là **bốn đồng hồ/chính sách khác nhau**:

- **Account expiration:** quyền dùng account chấm dứt theo mô hình nghiệp vụ.
- **Session expiration:** thời gian sống/không hoạt động của phiên trên server.
- **JWT expiration (`exp`):** thời hạn chấp nhận token theo kiểm tra JWT; token còn hạn **không chứng minh account nội bộ vẫn còn hạn**.
- **Credential expiration:** thời hạn của mật khẩu hoặc phương thức đăng nhập.

Một token JWT còn hạn sau khi account đã hết hạn vẫn có thể được chấp nhận bởi một resource server **nếu server chỉ kiểm tra chữ ký/issuer/audience/exp mà không kiểm tra trạng thái account**. Tương tự, session đã tạo trước ngày hết hạn có thể tồn tại đến hết thời gian sống của nó nếu không có kiểm tra/tru hồi riêng.

**Chặn lần login mới không tự động thu hồi những phiên và token cũ.** Đây là khác biệt quan trọng nhất khi đưa `isAccountNonExpired()` vào production.

## 3. Quy tắc thời gian: phải định nghĩa “hết hạn tại thời điểm nào?”

Một policy rõ ràng nên lưu **thời điểm bắt đầu mất hiệu lực** dưới dạng `Instant` (UTC instant), ví dụ `account_expires_at`. Ta chọn quy tắc:

- `expiresAt == null`: **không có hạn sử dụng**, nếu đây là policy được cho phép.
- `now.isBefore(expiresAt)`: **chưa hết hạn**, account còn hiệu lực về thời gian.
- `now.equals(expiresAt)`: **đã hết hạn**.
- `now.isAfter(expiresAt)`: **đã hết hạn**.

Tương đương:

~~~java
boolean accountNonExpired =
        expiresAt == null || clock.instant().isBefore(expiresAt);
~~~

Đây là **biểu thức Java minh họa**, với `expiresAt` kiểu `Instant` và `clock` kiểu `Clock`; nó không kiểm tra `enabled`, `locked` hoặc quyền truy cập. Chọn điều kiện khoảng nửa mở **`[start, expiresAt)`** giúp tránh tranh cãi tại đúng mili/nanosecond hết hạn.

### 3.1. Bảng ranh giới cụ thể

Giả định `expiresAt = 2026-11-10T00:00:00Z`:

| Thời điểm kiểm tra (UTC) | `now.isBefore(expiresAt)` | `isAccountNonExpired()` |
|---|---|---|
| 09/11 23:59:59.999 | `true` | `true` |
| 10/11 00:00:00.000 | `false` | **`false`** |
| 10/11 00:00:00.001 | `false` | `false` |

Dòng “đúng giờ hết hạn” phải được xác định trong tài liệu nghiệp vụ. Nếu gói dịch vụ quảng cáo “dùng đến hết ngày 10/11 theo giờ Việt Nam”, không được lưu tùy ý `2026-11-10T00:00:00Z` vì thời điểm đó là buổi sáng tại Việt Nam, **không phải hết ngày địa phương**. Nên chuyển từ `LocalDate` và `ZoneId` đã định nghĩa sang thời điểm bắt đầu ngày tiếp theo, rồi lưu `Instant`:

~~~java
LocalDate lastAllowedDay = LocalDate.of(2026, 11, 10);
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant expiresAt = lastAllowedDay.plusDays(1)
        .atStartOfDay(businessZone)
        .toInstant();
~~~

Đây là **đoạn Java JDK 17 minh họa**; không tự tạo Spring Security user. Nếu một doanh nghiệp có nhiều múi giờ, chọn múi giờ theo hợp đồng tổ chức/gói dịch vụ, không lấy tùy tiện từ trình duyệt client. Với các vùng có DST, dùng `ZoneId` để xử lý biến đổi lịch; tránh cộng bừa `24h` vào mọi local date.

### 3.2. Dùng Instant và Clock thay cho so sánh chuỗi/ngày máy chủ

- Lưu DB bằng loại timestamp có semantics rõ, ví dụ PostgreSQL `TIMESTAMPTZ`; nó lưu thời điểm thực, không giữ nguyên tên múi giờ hiển thị.
- Dùng `Instant`/`Clock` cho chính sách hiệu lực. Inject `Clock` giúp test được trước, đúng và sau ranh giới mà không phụ thuộc thời gian thật.
- Không so sánh ngày dưới dạng `String`, không dựa vào timezone mặc định `ZoneId.systemDefault()` của từng pod.
- Định nghĩa precision khi lưu DB: nếu database giữ microsecond mà Java có nanosecond, kiểm thử ranh giới theo độ chính xác thực tế.
- Đồng bộ giờ hệ thống ở các nodes, có giám sát clock skew. Nếu policy yêu cầu thời điểm hiệu lực chính xác tuyệt đối, cần cân nhắc tính thời gian tập trung hoặc giới hạn lệch giờ.

### 3.3. Grace period và gia hạn

Một số sản phẩm có thời gian ân hạn 3 ngày, gia hạn tự động hoặc giai đoạn chỉ đọc. **Đây là quyết định domain, không phải có sẵn trong isAccountNonExpired.**

Ví dụ:

~~~text
Đến 10/11: ACTIVE
10/11–13/11: GRACE_READ_ONLY (có thể đăng nhập nhưng bị giới hạn thao tác)
Từ 13/11: EXPIRED
Gia hạn thanh toán được xác nhận: ACTIVE với expiresAt mới
~~~

Nếu cho đăng nhập trong grace period thì `isAccountNonExpired()` có thể vẫn là `true` trong giai đoạn đó **theo policy**, nhưng phải đặt ràng buộc **read-only** ở lớp authorization/domain. Nếu tất cả quyền truy cập phải ngừng lúc 10/11 thì flag chuyển `false` ngay. Không dùng một boolean để mô tả đầy đủ nhiều mức quyền; lưu trạng thái/grace policy rõ và map chính xác.

## 4. Mô hình lưu trữ và ranh giới trách nhiệm

Schema PostgreSQL minh họa:

~~~sql
CREATE TABLE accounts (
    id                 UUID PRIMARY KEY,
    login_name         TEXT NOT NULL UNIQUE,
    password_hash      TEXT NOT NULL,
    enabled            BOOLEAN NOT NULL DEFAULT TRUE,
    locked             BOOLEAN NOT NULL DEFAULT FALSE,
    account_expires_at TIMESTAMPTZ,
    password_expires_at TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

`account_expires_at` là **ngày/giờ hết hạn account**, `password_expires_at` là ngày/giờ hết hạn credential. Cả hai có thể null nếu policy cho phép không thời hạn; schema không bắt buộc mọi sản phẩm cho phép null. Với hệ thống dùng OIDC mà không có password nội bộ, `password_hash` có thể cần nullable và được liên kết qua identity table; schema ở đây chỉ minh họa phương thức password.

Một entity/repository giúp lấy dữ liệu, nhưng **chính sách mapping sang UserDetails nằm ở service bảo mật**:

~~~java
boolean accountNonExpired = account.getAccountExpiresAt() == null
        || clock.instant().isBefore(account.getAccountExpiresAt());

UserDetails details = User.withUsername(account.getLoginName())
        .password(account.getPasswordHash())
        .authorities(account.getAuthorities())
        .disabled(!account.isEnabled())
        .accountLocked(account.isLocked())
        .accountExpired(!accountNonExpired)
        .credentialsExpired(!credentialsNonExpired)
        .build();
~~~

Đây là **mảnh tích hợp** (cần `account`, `clock`, `credentialsNonExpired`, imports và policy authorities), **không phải chương trình độc lập**. Ý tưởng là lấy account hiện thời, tính **accountNonExpired**, rồi dùng builder `.accountExpired(!accountNonExpired)`. Phần `credentialsNonExpired` phải được tính từ chính sách password riêng, không copy cờ account.

### 4.1. UserDetailsService không phải hệ thống đặt lịch

`UserDetailsService.loadUserByUsername(...)` thường được gọi để tải thông tin cho `DaoAuthenticationProvider` trong luồng password login. Nó **không tự động được gọi vào đúng giờ một account hết hạn**. Nếu account row có `account_expires_at` là ngày mai, hôm nay service trả valid; không có timer nào tự gọi lại service vào 00:00 ngày mai và xóa mọi session.

Cách thực thi policy gồm hai phần tách biệt:

1. **Xác thực mới**: khi provider tải `UserDetails`, kiểm tra hạn tại thời điểm xác thực.
2. **Đang sử dụng phiên/token**: middleware/authorization hoặc các cơ chế session invalidation, token revocation, introspection, versioning hay access-token TTL phải đảm bảo yêu cầu nghiệp vụ về thời điểm chặn.

Nếu ứng dụng dùng stateless bearer token, `UserDetailsService` thậm chí có thể **không tham gia vào request**. Vì vậy thay đổi `isAccountNonExpired` trong một class không bảo đảm tất cả cơ chế đăng nhập hay API được bảo vệ.

### 4.2. Dùng cache thì cờ có thể bị cũ

Nếu service cache nguyên `UserDetails` đã tính `accountNonExpired=true` hôm nay, ngày mai cache có thể vẫn trả cờ `true` trừ khi được làm mới. Đừng coi giá trị boolean trong principal đã lưu là một biểu thức tự cập nhật theo thời gian.

Các lựa chọn:

- Không cache kết quả `UserDetails` khi yêu cầu trạng thái chính xác tại login.
- Cache dữ liệu nguồn có `expiresAt`, nhưng tính **lại** cờ bằng `Clock` ở mỗi lần xác thực; cần kiểm soát vấn đề password hash/credential erasure ở object dùng chung.
- Đặt TTL tối đa **không vượt thời gian còn lại đến khi hết hạn** của account, cộng với cơ chế invalidate khi admin gia hạn/khóa.
- Nếu chính sách yêu cầu chặn mọi request ngay, thực hiện kiểm tra expiry ở lớp request/token riêng hoặc revoke session khi đến hạn.
- Test trước/sau ranh giới, cập nhật từ nhiều node và concurrency.

Không tắt `ProviderManager.eraseCredentialsAfterAuthentication` chỉ để giữ một `UserDetails` mutable chứa password hash trong cache. Ưu tiên tách security principal khỏi cache và thiết kế ownership của object an toàn.

## 5. Provider xử lý tài khoản hết hạn như thế nào?

Trong authentication username/password thông thường:

~~~text
UsernamePasswordAuthenticationToken (request)
  -> ProviderManager
     -> DaoAuthenticationProvider
        -> UserDetailsService trả UserDetails
        -> kiểm tra trạng thái trước credential
             locked? disabled? account expired?
        -> kiểm tra mật khẩu
        -> kiểm tra credential expiration
        -> trả Authentication thành công
  -> SecurityContext do filter quản lý
~~~

Nếu `UserDetails.isAccountNonExpired()==false`, phần pre-authentication checker mặc định của `AbstractUserDetailsAuthenticationProvider` ném **`AccountExpiredException`**. Nó thuộc họ `AccountStatusException` / `AuthenticationException`; vì thế request **không có Authentication thành công** qua provider đó.

Không nhầm với:

- `CredentialsExpiredException`: password/credential hết hạn; account có thể vẫn còn thời hạn.
- `LockedException`: account đang bị khóa, thường do chính sách bảo vệ.
- `DisabledException`: account không được kích hoạt hoặc bị tắt.
- `BadCredentialsException`: credential sai hoặc một số trường hợp không tìm thấy user được che giấu.
- `ExpiredJwtException` hoặc cơ chế kiểm tra `exp` ở JWT: token hết hạn, **không** đồng nghĩa account hết hạn.

**Ngoại lệ không tự quy định HTTP status.** HTTP Basic có thể phản hồi 401; form login có thể redirect; JSON login custom có thể trả error code chung. Đừng mặc định “expired account” trở thành HTTP 403 hay 410 chỉ vì tên exception.

### 5.1. Hiển thị lỗi đúng mà không gây dò tài khoản

Bên trong hệ thống, bạn có thể muốn phân biệt `account_expired` với `password_wrong` để hỗ trợ gia hạn. Tuy nhiên, phản hồi công khai khác biệt giữa account tồn tại/không tồn tại có thể giúp **account enumeration**. Hãy quyết định theo threat model:

- Với login public: thường nên trả thông báo đủ chung, không lộ email/tài khoản có tồn tại.
- Với người đã chứng minh quyền sở hữu account qua bước xác minh thích hợp: có thể hiển thị hướng dẫn gia hạn.
- Với bộ phận hỗ trợ: audit reason nội bộ có phân quyền, hạn chế log PII và tuyệt đối không log raw password.
- Không cho client tự cập nhật `expiresAt` chỉ bằng một trường trong request; mọi gia hạn cần được xác minh qua billing/admin workflow tin cậy.

## 6. Ví dụ chạy được — Java 17, Spring Security 6.3

Ví dụ console dưới đây **không phụ thuộc web server**, nhưng dùng đúng `DaoAuthenticationProvider` và `ProviderManager` của Spring Security để chứng minh `isAccountNonExpired`. Thay vì đồng hồ thật, nó dùng `Clock.fixed(...)` tại `2026-11-05T00:00:00Z`, nên kết quả không thay đổi theo ngày chạy.

Các trường hợp gồm account chưa hết hạn, account không có hạn, account đã hết hạn, account hết hạn **ngay tại thời điểm kiểm tra**, bị vô hiệu hóa, bị khóa, mật khẩu hết hạn, username không tồn tại và mật khẩu sai.

### 6.1. Cấu trúc project và Gradle

~~~text
account-expiry-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/AccountExpiryDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'account-expiry-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.3.8'
    implementation 'org.springframework.security:spring-security-crypto:6.3.8'
}

application {
    mainClass = 'example.AccountExpiryDemo'
}
~~~

Mẫu pin phiên bản Spring Security 6.3.8 cho mục đích học. Dự án Spring Boot thực tế thường dùng dependency management của Boot. Cần JDK 17+, Gradle tương thích và quyền tải dependencies lần đầu; không cần chạy HTTP server, JPA hoặc PostgreSQL.

### 6.2. Mã Java đầy đủ

Tạo `src/main/java/example/AccountExpiryDemo.java`:

~~~java
package example;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class AccountExpiryDemo {

    record Account(
            String username,
            String passwordHash,
            Instant accountExpiresAt,
            boolean enabled,
            boolean nonLocked,
            boolean credentialsNonExpired) {
    }

    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-05T00:00:00Z"),
                ZoneOffset.UTC);
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        String passwordHash = encoder.encode("demo-pass");

        Instant future = Instant.parse("2026-11-06T00:00:00Z");
        Instant past = Instant.parse("2026-11-04T00:00:00Z");
        Instant boundary = clock.instant();

        Map<String, Account> rows = Map.of(
            "active", new Account(
                "active", passwordHash, future, true, true, true),
            "never", new Account(
                "never", passwordHash, null, true, true, true),
            "expired", new Account(
                "expired", passwordHash, past, true, true, true),
            "boundary", new Account(
                "boundary", passwordHash, boundary, true, true, true),
            "disabled", new Account(
                "disabled", passwordHash, future, false, true, true),
            "locked", new Account(
                "locked", passwordHash, future, true, false, true),
            "password-old", new Account(
                "password-old", passwordHash, future, true, true, false)
        );

        UserDetailsService users = username -> {
            Account account = rows.get(username);
            if (account == null) {
                throw new UsernameNotFoundException("Unknown account");
            }

            // Đúng boundary expiresAt: account đã hết hạn.
            boolean accountNonExpired =
                    account.accountExpiresAt() == null
                    || clock.instant().isBefore(
                            account.accountExpiresAt());

            // Builder nhận "expired", đảo chiều với "nonExpired".
            return User.withUsername(account.username())
                    .password(account.passwordHash())
                    .authorities("notes:read")
                    .disabled(!account.enabled())
                    .accountLocked(!account.nonLocked())
                    .accountExpired(!accountNonExpired)
                    .credentialsExpired(
                            !account.credentialsNonExpired())
                    .build();
        };

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);

        AuthenticationManager manager =
                new ProviderManager(List.of(provider));

        attempt(manager, "active", "active", "demo-pass");
        attempt(manager, "never", "never", "demo-pass");
        attempt(manager, "expired", "expired", "demo-pass");
        attempt(manager, "boundary", "boundary", "demo-pass");
        attempt(manager, "disabled", "disabled", "demo-pass");
        attempt(manager, "locked", "locked", "demo-pass");
        attempt(manager, "password-old", "password-old", "demo-pass");
        attempt(manager, "unknown", "unknown", "demo-pass");
        attempt(manager, "active/wrong", "active", "wrong-pass");
    }

    private static void attempt(
            AuthenticationManager manager,
            String label,
            String username,
            String rawPassword) {

        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, rawPassword);

        try {
            Authentication result = manager.authenticate(request);
            System.out.println(label + " -> OK: "
                    + result.getName()
                    + ", authenticated=" + result.isAuthenticated());
        } catch (AuthenticationException ex) {
            System.out.println(label + " -> "
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

**Phân tích code:**

1. `Account` mô phỏng entity nghiệp vụ. Trường `accountExpiresAt` có thể null để biểu diễn “không có ngày hết hạn” theo policy đã thống nhất.
2. `Clock.fixed` bảo đảm tính deterministic. Chạy vào năm nào thì `clock.instant()` vẫn là `2026-11-05T00:00:00Z`.
3. `UserDetailsService` load account, tính `accountNonExpired` từ `Instant`, rồi truyền `.accountExpired(!accountNonExpired)` vào `User.UserBuilder`.
4. Các cờ disabled, locked và credentials expired được đặt **riêng** để chứng minh mỗi tình huống có loại lỗi khác nhau.
5. `DaoAuthenticationProvider` thực hiện kiểm tra status/password và trả một `Authentication` thành công khi tất cả điều kiện hợp lệ.
6. `ProviderManager` điều phối provider; chương trình bắt `AuthenticationException` và chỉ in tên class để minh họa kết quả. Trong server thật, không trả nguyên tên exception ra public API một cách vô điều kiện.
7. Service dựng `UserDetails` mới cho từng lookup, thay vì giữ chung một instance mutable mang password hash giữa cache và principal.

### 6.3. Cách chạy và stdout

Tại thư mục `account-expiry-demo`, khi đã tạo Gradle Wrapper tương thích:

~~~bash
./gradlew run
~~~

Nếu không có wrapper nhưng đã cài Gradle phù hợp, dùng `gradle run`. Với Windows PowerShell có wrapper, có thể dùng `.\gradlew.bat run`.

Đầu ra **của các lệnh System.out.println trong chương trình** (không tính log Gradle):

~~~text
active -> OK: active, authenticated=true
never -> OK: never, authenticated=true
expired -> AccountExpiredException
boundary -> AccountExpiredException
disabled -> DisabledException
locked -> LockedException
password-old -> CredentialsExpiredException
unknown -> BadCredentialsException
active/wrong -> BadCredentialsException
~~~

Dòng `boundary` quan trọng: tại thời điểm **`now == expiresAt`**, biểu thức `isBefore` là `false` nên account đã hết hạn. Dòng `unknown` cho thấy `DaoAuthenticationProvider` mặc định có cơ chế che giấu username không tồn tại dưới dạng lỗi credential không hợp lệ. Hash BCrypt có salt ngẫu nhiên nên byte của hash khác nhau giữa các lần chạy, nhưng kết quả xác thực và stdout trên là nhất quán với logic demo.

**Mục tiêu của ví dụ:** thấy chính xác ảnh hưởng của `isAccountNonExpired` trong một luồng xác thực mới. Không coi demo là toàn bộ hệ thống quản lý thuê bao: chưa có gia hạn bằng payment, transaction, database migration, email, MFA, session/JWT, auditing hoặc revocation.

### 6.4. Thử hai biến thể

**Biến thể A — đảo dấu sai trong builder:** đổi `.accountExpired(!accountNonExpired)` thành `.accountExpired(accountNonExpired)`. Kết quả sẽ đảo ngược policy: account active có thể bị coi hết hạn, account expired có thể được coi hợp lệ. Chỉ thử ở project học để nhận diện lỗi.

**Biến thể B — dùng đồng hồ thật:** thay `Clock.fixed(...)` bằng `Clock.systemUTC()` và đặt accountExipresAt ở thời điểm cụ thể trong tương lai; test ở thời điểm gần ranh giới để thấy lỗi dễ xuất hiện khi dùng đồng hồ thật. Với unit tests, ưu tiên cố định clock và inject thay vì ngủ `Thread.sleep` đợi đến giờ.

## 7. Gia hạn, khôi phục và cập nhật trạng thái

Khi một account đã hết hạn và được gia hạn, quy trình thường gồm:

1. Xác thực người/cơ chế thực hiện gia hạn, ví dụ admin, billing event đã được xác minh hoặc webhook có chữ ký hợp lệ.
2. Áp dụng policy gia hạn: tính ngày mới theo gói dịch vụ, điều khoản hợp đồng, grace period, hay thời điểm hiện tại; **không tin expiresAt từ client nếu chưa có quyền**.
3. Cập nhật dữ liệu trong transaction, audit lý do/tác nhân/timestamp và đảm bảo idempotency khi nhận lại webhook.
4. Invalidate cache/phiên hoặc cấp lại token theo chiến lược để trạng thái mới có hiệu lực; nếu không, principal cũ có thể vẫn là expired dù database vừa được gia hạn.
5. Xem xét các yếu tố độc lập như account đang locked/disabled: gia hạn account **không tự bỏ khóa** hoặc bật lại account bị vô hiệu hóa.

### 7.1. Cần xét trạng thái hiện tại thay vì cờ lưu sẵn

Nếu chỉ lưu `account_non_expired = true` trong database lúc đăng ký, nó sẽ không tự đổi thành `false` khi thời gian trôi qua. Nên lưu `expiresAt` như dữ liệu gốc và tính validity tại thời điểm được kiểm tra; hoặc có scheduler cập nhật trạng thái **kèm cơ chế đảm bảo không trễ** khi policy yêu cầu.

Một phương án domain:

~~~java
public boolean isAccountNonExpiredAt(Instant now) {
    return accountExpiresAt == null
            || now.isBefore(accountExpiresAt);
}
~~~

Đây là **đoạn method thuộc entity/value object giả định**, không phải chương trình độc lập. Lợi ích: bảo đảm ranh giới thời gian có thể được unit test. Bất kỳ lớp nào cần quyết định hiện trạng phải dùng nguồn dữ liệu và đồng hồ phù hợp, không dựa mù vào snapshot từ lúc người dùng đăng nhập hôm qua.

### 7.2. Khi expiration làm thay đổi quyền trong lúc đang sử dụng

Giả sử user đăng nhập lúc 23:55 và account hết hạn lúc 00:00. Nếu sản phẩm cam kết “ngừng truy cập ngay lúc 00:00”, **chỉ dùng `isAccountNonExpired()` trong password login không đủ**:

| Cơ chế | Điều cần bổ sung khi account hết hạn |
|---|---|
| Session server-side | Check account status ở request cần thiết, invalidate/revoke session hoặc có timer/chính sách tương ứng |
| Stateless JWT | Access token ngắn hạn và/hoặc tra trạng thái account, denylist/version/introspection theo mức độ tức thời cần bảo đảm |
| API key | Check expiry/revocation của key và account liên quan; không suy key còn hạn là account còn hạn |
| Long-running job | Định nghĩa snapshot quyền tại lúc bắt đầu hay kiểm tra lại trước thao tác nhạy cảm |
| WebSocket/streaming | Chính sách đóng kết nối hoặc re-authorize sau khi account hết hạn |
| Cached UserDetails | TTL/invalidation phù hợp với `expiresAt`; tránh giữ flag cũ sau mốc hết hạn |

Đánh đổi giữa kiểm tra “mỗi request” và hiệu năng phải được thiết kế, đo tải và nêu rõ SLA an toàn. Nếu cache có TTL 5 phút, không thể tuyên bố account bị chặn tức thời trong mọi trường hợp nếu không có cơ chế thu hồi phụ trợ.

## 8. Thiết kế multi-tenant và nhiều nguồn danh tính

Một nhân viên có thể thuộc nhiều tổ chức: **tài khoản cá nhân còn hạn**, nhưng **membership của tổ chức A đã hết hạn** trong khi tổ chức B vẫn còn hiệu lực. Nếu quy tắc áp dụng ở cấp membership, không nên đổi `isAccountNonExpired()` của user toàn cục thành `false` cho mọi tổ chức; cần kiểm tra phạm vi tenant ở authorization/domain:

~~~text
User account       : ACTIVE, non-expired
Membership tenant A: EXPIRED
Membership tenant B: ACTIVE
JWT / session      : user identity
Authorization      : kiểm tra quyền trong tenant đang truy cập
~~~

Tương tự, “gói subscription của tổ chức đã hết hạn” có thể chặn các chức năng trả phí, không nhất thiết chặn toàn bộ user login (ví dụ vẫn được vào trang billing). **Account expiry** và **subscription/tenant entitlements** nên được ánh xạ theo policy rõ ràng, tránh sử dụng một cờ boolean để giải quyết tất cả.

Với OAuth2/OIDC login hay JWT resource server, principal mặc định có thể là `OidcUser` hoặc `Jwt` thay vì `UserDetails`. Khi ấy `isAccountNonExpired()` **không tự được gọi** như trong `DaoAuthenticationProvider`. Nếu cần chặn local account expired, hãy ánh xạ external identity sang account nội bộ và thực thi expiry qua authentication converter/provider hoặc authorization/check phù hợp — không dựa vào một method không có trong luồng thực tế.

## 9. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Viết `return now.isAfter(expiresAt);` cho `isAccountNonExpired` | Trả true khi đã hết hạn | Dùng `now.isBefore(expiresAt)` cho policy ranh giới loại trừ |
| Truyền `.accountExpired(accountNonExpired)` | Đảo cờ trong `UserBuilder` | Truyền **`!accountNonExpired`** |
| Dùng `LocalDate.now()` với timezone ngẫu nhiên của server | Lệch giờ hết hạn giữa các nodes | Dùng `Instant` và `Clock`, định nghĩa `ZoneId` khi lấy ngày nghiệp vụ |
| Dùng `<=` thay `<` ở mốc hết hạn | Tài khoản còn hiệu lực quá thời điểm quy định | Định nghĩa `[start, expiresAt)` và test ngay boundary |
| Đặt `isAccountNonExpired=true` vĩnh viễn trong custom UserDetails | Không thực thi account expiry | Map từ chính sách và dữ liệu hiện thời |
| Coi account expired là password expired | Đưa người dùng tới reset password dù cần gia hạn account | Tách hai cờ/ngoại lệ |
| Coi JWT `exp` là account expiry | Token còn hạn trong khi account đã hết hạn | Kiểm tra/thu hồi theo account policy |
| Coi `isAccountNonExpired=false` sẽ hủy ngay mọi session | Request với session cũ có thể tiếp tục | Thiết kế session/token revocation và live checks |
| Cache `UserDetails` đã valid trước mốc hết hạn | Login mới có thể dùng trạng thái cũ | TTL đến expiry, invalidate hoặc tính lại trạng thái |
| Đổi `expiresAt` bằng request không xác thực | Người dùng tự gia hạn | Kiểm soát quyền và xác minh billing/admin |
| Dùng ngày “đến hết ngày” mà lưu như “đầu ngày” | Chặn quá sớm | Chuyển ngày nghiệp vụ sang đầu ngày kế tiếp theo timezone đã chốt |
| Gộp expiry toàn account với membership tenant | Chặn nhầm quyền ở các tổ chức khác | Phân biệt identity, membership và entitlement |
| In nguyên `AccountExpiredException` cho mọi login public | Có thể giúp dò account có tồn tại | Phản hồi có kiểm soát, hỗ trợ sau khi xác minh quyền sở hữu |

## 10. Ma trận kiểm thử

Một bộ kiểm thử production nên bao quát **đúng ranh giới thời gian** và **đúng phạm vi hiệu lực**:

| Tình huống | Kết quả |
|---|---|
| `expiresAt=null` và policy cho không hết hạn | `isAccountNonExpired()==true` |
| `now < expiresAt` | Account chưa hết hạn |
| `now == expiresAt` | Account **đã hết hạn** theo policy `[start,expiresAt)` |
| `now > expiresAt` | Account đã hết hạn |
| Password đúng nhưng account expired | `AccountExpiredException` trong provider chuẩn |
| Password đúng, account valid, credential expired | `CredentialsExpiredException` |
| Account valid nhưng disabled/locked | `DisabledException`/`LockedException` |
| User không tồn tại | Không vô tình tiết lộ thông tin qua public response |
| Account gia hạn trước/sau boundary | Cache và lần login mới phản ánh ngày hết hạn mới |
| Login trước giờ hết hạn, request sau giờ hết hạn | Session/JWT bị xử lý đúng SLA chính sách |
| Nhiều nodes khác múi giờ | Cùng một `Instant` thì cho kết quả như nhau |
| Business date gồm DST | Ngày local chuyển sang instant theo `ZoneId` đúng |
| Subscription tenant A expired nhưng B active | Chỉ quyền thuộc tenant A bị ảnh hưởng nếu policy ở cấp membership |
| OIDC/JWT không dùng UserDetailsService | Expiry account vẫn được thực thi ở lớp phù hợp |
| Cập nhật expiresAt đồng thời với refresh token | Không cấp token vượt policy được cho phép |
| Account đã expired nhưng admin gia hạn | Có quyền/transaction/audit; không bỏ khóa độc lập tùy tiện |

Có thể unit test logic ngày giờ với `Clock.fixed`, integration test `DaoAuthenticationProvider` bằng user active/expired và test HTTP với Spring Security test support. Không dùng `Thread.sleep` làm phương pháp chính: test chậm và dễ flaky.

### 10.1. Tự kiểm tra kiến thức

**Câu 1.** `isAccountNonExpired()==false` có nghĩa password đã hết hạn không?  
**Trả lời:** Không. Nó thể hiện thời hạn **account** hết; credential expiry nằm ở `isCredentialsNonExpired()`.

**Câu 2.** `User.withUsername(...).accountExpired(true)` dẫn tới `isAccountNonExpired()` bằng bao nhiêu?  
**Trả lời:** `false`.

**Câu 3.** Nếu thời gian hiện tại bằng đúng `expiresAt`, nên trả gì?  
**Trả lời:** Với policy khoảng hiệu lực `[start, expiresAt)`, trả `false`. Chính sách phải được ghi rõ.

**Câu 4.** Tại sao phải inject `Clock`?  
**Trả lời:** Để tính thời gian nhất quán và kiểm thử deterministic ở trước/đúng/sau ranh giới.

**Câu 5.** Tài khoản hết hạn hôm nay, JWT còn hạn ngày mai. Mọi request có bị chặn không?  
**Trả lời:** Không tự động. Cần kiểm tra account status hoặc thu hồi/giới hạn token theo policy; JWT `exp` là timer riêng.

**Câu 6.** Hai tenant dùng chung một account, chỉ tenant A hết subscription. Có nên đặt `isAccountNonExpired=false` toàn cục?  
**Trả lời:** Không nhất thiết. Nếu expiry ở cấp membership/entitlement, nên hạn chế quyền của tenant A thay vì làm account identity toàn cục hết hạn.

**Câu 7.** Nếu cache giữ `UserDetails` được tạo hôm qua, đến đúng giờ hết hạn điều gì có thể xảy ra?  
**Trả lời:** Cờ boolean trên instance cũ có thể vẫn là true. Phải kiểm soát cache TTL/invalidation hoặc tính lại từ `expiresAt` đúng lúc.

**Câu 8.** Có cần cho phép client ghi `account_expires_at` để gia hạn?  
**Trả lời:** Không theo mặc định. Gia hạn là thao tác đặc quyền, cần xác minh workflow/billing và ghi audit.

## 11. Checklist áp dụng trong dự án

- [ ] Định nghĩa account expiry có cần không, áp dụng cho user, membership hay tenant entitlement.
- [ ] Lưu ngày hết hạn với semantics rõ, dùng `Instant` và chính sách timezone cho mốc ngày nghiệp vụ.
- [ ] Xác định `expiresAt=null` nghĩa là gì; không để diễn giải khác nhau giữa service.
- [ ] Cố định ranh giới `now < expiresAt`, test `before`, `equal` và `after`.
- [ ] Map đúng `isAccountNonExpired` sang `User.UserBuilder.accountExpired(!nonExpired)`.
- [ ] Giữ riêng enabled, locked, account expiration và credential expiration.
- [ ] Có integration test chứng minh `AccountExpiredException` khi username/password hợp lệ nhưng account đã hết hạn.
- [ ] Không lộ thông tin tồn tại account qua response public; audit an toàn cho support.
- [ ] Xác minh cơ chế JWT/OIDC/session thực sự áp dụng account expiry, không chỉ form login.
- [ ] Không giữ cache status cũ qua hạn; thiết kế TTL, event invalidation hoặc live check.
- [ ] Gia hạn có quyền, transaction, audit và idempotency; không đồng nhất gia hạn với tự bỏ khóa.
- [ ] Kiểm thử nhiều tenant, đồng hồ nhiều node, grace period và request đang chạy khi đến hạn.

**Ghi nhớ:** `isAccountNonExpired()` là **một câu trả lời boolean tại thời điểm xác thực**. Khi hệ thống cần ngừng truy cập đúng ngày hết hạn, cần kết hợp **mô hình thời gian đúng**, **mapping UserDetails đúng**, và **chính sách đối với phiên/token đã cấp**. Đừng nhầm một flag trong `UserDetails` với bộ máy tự động quản lý toàn bộ vòng đời account.

### Tài liệu chính thức

- [Spring Security — UserDetails JavaDoc](https://docs.spring.io/spring-security/site/docs/6.4.4/api/org/springframework/security/core/userdetails/UserDetails.html): semantics và giá trị của `isAccountNonExpired()`.
- [Spring Security — User.UserBuilder JavaDoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/userdetails/User.UserBuilder.html): `accountExpired(boolean)`, `credentialsExpired(boolean)`, `disabled` và `accountLocked`.
- [Spring Security — AbstractUserDetailsAuthenticationProvider JavaDoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html): các bước kiểm tra account, password và account status.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): phương thức tải `UserDetails` và kiểm tra password.
- [Spring Security — AccountExpiredException](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AccountExpiredException.html): ngoại lệ account đã hết hạn.
- [Java SE — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): đồng hồ injectable/fixed để kiểm thử.
