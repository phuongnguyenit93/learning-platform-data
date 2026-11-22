# isAccountNonLocked và chính sách khóa tài khoản

> **Chủ đề:** Trạng thái tài khoản trong Spring Security – authentication (Servlet). Bài học giải thích ý nghĩa của `UserDetails.isAccountNonLocked()`, cơ chế Spring Security từ chối đăng nhập bằng `LockedException`, cách xây dựng chính sách khóa/mở khóa an toàn, phân biệt account lockout với throttling và cách kiểm thử trên Java 17+.

## 1. Một mật khẩu đúng chưa chắc được phép đăng nhập

Giả sử tài khoản An có username `an` và mật khẩu hợp lệ. Nếu phát hiện hoạt động đăng nhập đáng ngờ, hệ thống có thể quyết định tạm khóa account trong một khoảng thời gian. Lần đăng nhập sau, dù An nhập đúng mật khẩu, server vẫn cần từ chối tạo phiên xác thực mới cho tài khoản đang bị khóa.

Đó là ý nghĩa của **account lock state**: tài khoản có tồn tại và có thể có mật khẩu hợp lệ, nhưng chính sách hiện thời không cho phép nó tham gia một phiên xác thực mới.

Cần trả lời ba câu hỏi riêng:

1. **Trạng thái:** tài khoản đang bị khóa hay không?
2. **Chính sách:** điều kiện nào làm nó bị khóa, khóa bao lâu, ai có quyền mở và cách xử lý sự cố?
3. **Thực thi:** ở bước xác thực, framework làm gì với trạng thái được kho user cung cấp?

Spring Security xử lý câu thứ ba qua `UserDetails.isAccountNonLocked()` và các kiểm tra trạng thái trong `AuthenticationProvider`; framework **không tự cung cấp toàn bộ** câu thứ hai chỉ vì bạn triển khai interface ấy.

Ví dụ: "sai ba lần trong một cửa sổ thời gian → tạm khóa 60 giây" là **chính sách của ứng dụng demo**, không phải hành vi mặc định của Spring Security.

## 2. Hợp đồng isAccountNonLocked(): true là KHÔNG bị khóa

`isAccountNonLocked()` là method của `org.springframework.security.core.userdetails.UserDetails`:

```java
boolean isAccountNonLocked();
```

Method trả **`true` nếu tài khoản không bị khóa** và **`false` nếu đang bị khóa**. Tên method mang nghĩa phủ định; cần tránh đảo dấu.

| Trạng thái nghiệp vụ | `isAccountNonLocked()` | Kết quả pre-authentication check điển hình |
| --- | --- | --- |
| Account bình thường | `true` | Tiếp tục các bước kiểm tra |
| Account đang bị khóa | `false` | Ném `LockedException`, không phát authentication thành công |
| Đến hạn mở khóa và policy đã gỡ lock | `true` | Có thể thử xác thực lại |
| Database trạng thái không khả dụng | Không thể quyết định tin cậy | Thất bại an toàn; không mặc định thành `true` |

**`true` chưa đồng nghĩa đăng nhập thành công.** Provider còn phải kiểm tra username/password, trạng thái disabled/account expired/credentials expired và các điều kiện khác. `false` cũng **không có nghĩa password sai**.

### Chuyển trạng thái khóa từ database đúng chiều

Giả sử database lưu cột `locked` (true nghĩa **đang bị khóa**). Nếu tự implement `UserDetails`, phải đảo nó:

```java
@Override
public boolean isAccountNonLocked() {
    return !account.isLocked();
}
```

Đây là **mảnh mã minh họa**, cần một lớp `UserDetails` và biến `account` phù hợp.

Khi dùng builder `org.springframework.security.core.userdetails.User`, có thể chuyển cờ trực tiếp:

```java
UserDetails details = User.withUsername(account.username())
        .password(account.encodedPassword())
        .authorities("ROLE_USER")
        .accountLocked(account.locked())
        .build();
```

Đoạn trên cũng là **mảnh Java minh họa** với một `account` giả định. Builder `accountLocked(true)` nghĩa là khóa account; đối tượng `UserDetails` nhận được có `isAccountNonLocked() == false`. Đừng truyền `!account.locked()` vào builder, vì như vậy sẽ đảo hai lần.

### Account lock khác các trạng thái còn lại

| UserDetails method | Khi trả `false` | Exception điển hình |
| --- | --- | --- |
| `isAccountNonLocked()` | Account đang bị khóa | `LockedException` |
| `isEnabled()` | Account bị vô hiệu hóa | `DisabledException` |
| `isAccountNonExpired()` | Account hết hạn | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Credential hết hạn | `CredentialsExpiredException` |

Các trạng thái không nên dùng thay thế tùy tiện. Ví dụ một tài khoản bị đóng vĩnh viễn theo quyết định quản trị khác với tài khoản tự động khóa 60 giây sau chuỗi nhập sai mật khẩu. Một thuê bao hết hạn có thể vẫn được đăng nhập để thanh toán gia hạn, nên chưa chắc cần `AccountExpiredException`.

## 3. Spring Security kiểm tra lock state ở bước nào?

Với username/password và `DaoAuthenticationProvider`:

```text
Request: username + password chưa được tin cậy
                   |
                   v
          Authentication Filter
                   |
                   v
          AuthenticationManager
                   |
                   v
          DaoAuthenticationProvider
                   |
                   +-- UserDetailsService.loadUserByUsername(...)
                   |         |
                   |         +-- password hash
                   |         +-- authorities
                   |         +-- isAccountNonLocked()
                   |
                   +-- Kiểm tra account status
                   |         |
                   |         +-- false -> LockedException
                   |
                   +-- PasswordEncoder / kiểm tra credential
                   |
                   +-- Kiểm tra trạng thái sau credential
                   |
                   +-- Chỉ khi hợp lệ: Authentication thành công
                   |
                   v
            SecurityContext + authorization
```

`AbstractUserDetailsAuthenticationProvider` có **pre-authentication checks**. Trong cơ chế DAO thông thường, kiểm tra `isAccountNonLocked()` xảy ra trước khi chấp nhận kết quả xác thực. Khi account đang khóa, nó ném `LockedException`, một subclass của `AccountStatusException` rồi `AuthenticationException`.

Điều cần phân biệt:

- `UserDetailsService` **đọc trạng thái** và trả `UserDetails`; nó không tự hoàn tất đăng nhập.
- `DaoAuthenticationProvider` **kiểm tra trạng thái và credential**; không cho tài khoản khóa trở thành authenticated principal.
- `SecurityContext` **không phải database trạng thái**. Nó mang kết quả xác thực của một request/phiên, có thể là snapshot.
- `LockedException` **không tự tăng bộ đếm**, không tự viết `locked_until` xuống database và không tự mở khóa sau thời gian nào đó.
- `AuthenticationEntryPoint`/failure handler có thể dịch lỗi sang HTTP response; exception Java và body/status HTTP là hai lớp khác nhau.

Với các bản Spring Security đã vá lỗi chống timing attack, provider có thể vẫn thực hiện thêm một số phép kiểm tra credential phục vụ giảm rò rỉ thời gian ngay cả khi pre-check thất bại; điều này **không** biến tài khoản khóa thành authenticated. Không lấy thứ tự gọi `PasswordEncoder` làm tín hiệu “mật khẩu đúng” hay làm cơ sở mở khóa.

### LockedException không chứng minh mật khẩu đúng

Account bị khóa có thể bị từ chối **trước khi** password được xác nhận. Nếu backend ghi nhận `LockedException`, không thể nói “user nhập đúng password nhưng bị khóa”. Phản hồi công khai tiết lộ “tài khoản này đang khóa” cũng có thể giúp attacker dò sự tồn tại của username.

Ngược lại, nếu account chỉ sai password và chưa bị khóa, provider thường phát `BadCredentialsException`. Ứng dụng có thể theo dõi sự kiện này để **quyết định** có tăng bộ đếm thất bại và chuyển sang trạng thái khóa hay không.

## 4. Lock state và lockout policy khác nhau

**Lock state** là dữ liệu đã được quyết định: `locked=true`, `lockedUntil` trong tương lai, hoặc một mã trạng thái do người quản trị đặt.

**Lockout policy** là quy tắc quyết định chuyển trạng thái. Ví dụ:

- Cửa sổ đếm: 10 phút.
- Ngưỡng: 5 lần kiểm tra credential sai đối với một account.
- Hành động: khóa tạm 15 phút hoặc áp dụng step-up challenge.
- Mở khóa: hết hạn lock, thao tác quản trị hoặc quy trình khôi phục đáng tin.
- Khi thành công: reset counter của nhóm thất bại liên tiếp, tùy chính sách.
- Khi danh tính không tồn tại: không tạo record tài khoản giả chỉ vì user input.
- Khi hệ thống xác thực lỗi: không tính thành một lần người dùng nhập sai.
- Hạn tần suất: kiểm soát theo IP/thiết bị/user để giảm credential stuffing và lạm dụng.

**Đếm lỗi, ghi trạng thái và mở khóa là việc của ứng dụng/identity platform.** Spring Security cung cấp contract để **thực thi** trạng thái khi nhận kết quả từ nguồn đó.

### Máy trạng thái tham khảo

```text
           +----------------------+
           | ACTIVE (không khóa)  |
           | failedAttempts < N   |
           +----------+-----------+
                      |
                 Bad credentials
                      |
           +----------v-----------+
           | Ghi một lần thất bại |
           | theo cửa sổ/khóa     |
           +----------+-----------+
                      |
                  Đạt ngưỡng?
             không /          \ có
                v              v
             ACTIVE       +------------------+
                          | LOCKED_UNTIL(t)  |
                          | Auth bị từ chối  |
                          +--------+---------+
                                   |
                       t đã đến / unlock hợp lệ
                                   |
                                   v
                               ACTIVE
```

Mô hình này là **tối giản**. Trong production, có thể cần trạng thái `ADMIN_LOCKED` riêng (không tự mở theo thời gian), `DISABLED` (vô hiệu hóa tài khoản), yêu cầu xác minh chủ tài khoản và chính sách riêng cho tài khoản đặc quyền.

### Khóa có thời hạn

Nếu lưu `locked_until` kiểu UTC timestamp:

```text
isAccountNonLocked(now):
    locked_until = NULL     -> true
    now < locked_until      -> false
    now >= locked_until     -> true
```

Ở đây `now` phải đến từ đồng hồ tin cậy/được chuẩn hóa, chẳng hạn `Clock`/`Instant`, không từ client. Quy tắc **tại đúng thời điểm hết hạn** cần nhất quán: ở ví dụ, `now >= locked_until` nghĩa là hết khóa.

Nếu còn một cờ khóa thủ công, công thức có thể là:

```text
nonLocked = !manuallyLocked
            && (lockedUntil == null || now >= lockedUntil)
```

Đừng trộn khóa tạm thời và khóa thủ công vào một timestamp rồi tự mở khóa vĩnh viễn sau 60 giây.

## 5. Chọn chính sách sao cho chống brute force nhưng không tự tạo DoS

Khóa account nghe có vẻ tăng bảo mật, nhưng nó có một mặt trái: attacker chỉ cần biết username công khai rồi gửi đủ lần password sai có thể **khóa tài khoản của nạn nhân**. Nếu áp dụng khóa vĩnh viễn sau 3 lần sai, dịch vụ có thể bị làm gián đoạn hàng loạt.

Vì vậy, chính sách thường nên kết hợp nhiều lớp:

| Biện pháp | Bảo vệ điều gì? | Lưu ý |
| --- | --- | --- |
| Rate limiting theo IP / thiết bị / ASN | Giảm tốc thử mật khẩu tự động | Tránh đánh đồng tất cả user sau NAT |
| Throttling theo account | Giảm số lần thử trên một tài khoản | Cần chống việc attacker khóa account liên tục |
| Lock tạm thời có TTL | Chặn thêm attempt sau ngưỡng | Có thể bị lạm dụng gây denial of service |
| Lũy tiến thời gian chờ | Giảm tốc đối thủ thích nghi | Phải có giới hạn và policy rõ |
| MFA / step-up verification | Hạn nguy cơ lộ một yếu tố | MFA cũng cần chống spam/thử mã |
| Password hashing và kiểm tra breached password | Giảm hậu quả lộ credential | Không thay thế rate limiting |
| Cảnh báo và tự phục hồi có xác minh | Hỗ trợ user thực | Không cung cấp kênh bypass quá dễ |
| Phát hiện credential stuffing | Theo dõi hành vi phân tán | Cần telemetry và ngưỡng phù hợp |

**Không có một ngưỡng chuẩn “3 lần/60 giây” cho mọi ứng dụng.** Demo dùng số nhỏ để dễ thử, không phải khuyến nghị production. Sản phẩm tài chính, hệ thống quản trị và dịch vụ công có rủi ro/vòng đời tài khoản khác nhau; quyết định cuối nên dựa vào threat model, UX và khả năng phục hồi.

### Đếm gì và trên khóa nào?

- Đếm thất bại credential được xác nhận bởi provider, không đếm HTTP 401 nói chung (401 còn có thể vì thiếu credential/token hết hạn).
- Với username không tồn tại, tránh tạo bản ghi `accounts["arbitrary-name"]` cho mọi input, kẻ tấn công có thể làm đầy bộ nhớ/bảng.
- Một tài khoản nên có internal account ID bất biến làm khóa trạng thái khi đã xác định từ nguồn tin cậy.
- Nếu nhiều phương thức login (password, SSO, magic link, API key), xác định bộ đếm tách biệt hoặc hợp nhất theo policy; đừng khóa tài khoản SSO chỉ vì lỗi của một cơ chế khác nếu chưa có yêu cầu.
- Audit cần biết sự kiện thay đổi lock, actor kích hoạt và lý do trong phạm vi dữ liệu được phép lưu; không ghi plaintext password hoặc bearer token.

## 6. Ví dụ chạy được: lock sau ba lần sai bằng Spring Security events

Ví dụ dưới dùng **Java 17+**, ứng dụng **Spring Boot Servlet** với dependency **Spring Web** và **Spring Security**. Hãy tạo project từ Spring Initializr với bản Spring Boot/Spring Security **đã vá các advisory liên quan** (xem phần bảo mật phiên bản phía dưới).

Ta có một tài khoản demo:

- Username `an`, mật khẩu `demo-password`.
- Khi chưa bị khóa, đăng nhập đúng được phép.
- Ba lần nhập sai liên tiếp làm account bị khóa **60 giây**.
- Một request tiếp theo với password đúng vẫn bị từ chối trong thời gian khóa.
- Sau khi hết 60 giây, request đúng có thể đăng nhập trở lại.
- Một lần đăng nhập đúng trước khi đạt ngưỡng sẽ reset số lần sai.

**Mục tiêu:** minh họa rằng trạng thái khóa do tầng domain quản lý, `UserDetailsService` phản ánh nó qua `accountLocked(...)`, còn `DaoAuthenticationProvider` thực thi. Đây là demo **in-memory, một tiến trình**; không phải hệ thống lockout an toàn cho nhiều node hoặc có chống DoS đầy đủ.

Tạo file **`src/main/java/com/example/lockdemo/AccountLockDemoApplication.java`**:

```java
package com.example.lockdemo;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authentication.event.AuthenticationFailureBadCredentialsEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AccountLockDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccountLockDemoApplication.class, args);
    }
}

// Trạng thái chỉ nằm trong một instance demo.
// Các phương thức synchronized bảo vệ mutation của account này.
final class DemoAccount {
    private static final int MAX_FAILURES = 3;
    private static final Duration LOCK_DURATION = Duration.ofSeconds(60);

    private final String username;
    private final String encodedPassword;
    private int failures = 0;
    private Instant lockedUntil;

    DemoAccount(String username, String encodedPassword) {
        this.username = username;
        this.encodedPassword = encodedPassword;
    }

    String username() {
        return username;
    }

    String encodedPassword() {
        return encodedPassword;
    }

    synchronized boolean isNonLocked(Instant now) {
        if (lockedUntil != null && !now.isBefore(lockedUntil)) {
            lockedUntil = null;
            failures = 0;
        }
        return lockedUntil == null;
    }

    synchronized void recordBadCredentials(Instant now) {
        if (!isNonLocked(now)) {
            return; // Không tăng counter khi vẫn đang khóa.
        }
        failures++;
        if (failures >= MAX_FAILURES) {
            lockedUntil = now.plus(LOCK_DURATION);
            failures = 0;
        }
    }

    synchronized void recordSuccess() {
        failures = 0;
    }
}

// Nguồn hồ sơ: chỉ có một tài khoản server tin cậy quản lý.
final class DemoAccounts {
    private final Map<String, DemoAccount> accounts;

    DemoAccounts(PasswordEncoder encoder) {
        this.accounts = Map.of(
                "an", new DemoAccount(
                        "an", encoder.encode("demo-password")));
    }

    DemoAccount findByUsername(String username) {
        return accounts.get(username);
    }

    void badCredentials(String username, Instant now) {
        DemoAccount account = findByUsername(username);
        if (account != null) {
            account.recordBadCredentials(now);
        }
    }

    void success(String username) {
        DemoAccount account = findByUsername(username);
        if (account != null) {
            account.recordSuccess();
        }
    }
}

@Configuration(proxyBeanMethods = false)
class DemoSecurityConfig {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    DemoAccounts demoAccounts(PasswordEncoder encoder) {
        return new DemoAccounts(encoder);
    }

    @Bean
    UserDetailsService userDetailsService(
            DemoAccounts accounts, Clock clock) {

        return username -> {
            DemoAccount account = accounts.findByUsername(username);
            if (account == null) {
                throw new UsernameNotFoundException("Unknown username");
            }

            boolean locked = !account.isNonLocked(clock.instant());
            return User.withUsername(account.username())
                    .password(account.encodedPassword())
                    .authorities("ROLE_USER")
                    .accountLocked(locked)
                    .build();
        };
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder,
            ApplicationEventPublisher publisher) {

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        ProviderManager manager = new ProviderManager(provider);
        // Khi tự tạo ProviderManager, phải cấu hình publisher rõ ràng.
        manager.setAuthenticationEventPublisher(
                new DefaultAuthenticationEventPublisher(publisher));
        return manager;
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            AuthenticationManager manager) throws Exception {

        return http
                .authenticationManager(manager)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

// Chỉ theo dõi lỗi credential, không theo dõi mọi lỗi/401.
@Component
class LockoutEvents {

    private final DemoAccounts accounts;
    private final Clock clock;

    LockoutEvents(DemoAccounts accounts, Clock clock) {
        this.accounts = accounts;
        this.clock = clock;
    }

    @EventListener
    void badCredentials(AuthenticationFailureBadCredentialsEvent event) {
        // Username ở failure event vẫn là dữ liệu do caller khai.
        // Kho demo chỉ thay đổi trạng thái account thật đã tồn tại.
        accounts.badCredentials(
                event.getAuthentication().getName(), clock.instant());
    }

    @EventListener
    void authenticated(AuthenticationSuccessEvent event) {
        // Chỉ authentication thành công mới reset chuỗi thất bại.
        accounts.success(event.getAuthentication().getName());
    }
}

@RestController
class DemoController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "principal=" + authentication.getName();
    }
}
```

### Giải thích luồng xảy ra trong demo

**`DemoAccount`** chứa username, BCrypt password hash, bộ đếm và `lockedUntil`. Method `isNonLocked(now)` tự gỡ khóa khi đến hạn; không có tác vụ nền bắt buộc. `synchronized` giúp các thao tác trên một đối tượng account không cập nhật đồng thời một cách tùy tiện. Nó **không** tạo atomicity cho toàn bộ chu trình “tải trạng thái → kiểm tra mật khẩu → nhận event” qua nhiều request; production cần thiết kế đồng thời đầy đủ hơn.

**`DemoAccounts`** chỉ trả hồ sơ do server kiểm soát. Username chưa tồn tại không tạo một record khóa mới. Điều này ngăn một loại memory-growth attack trong demo nhưng **không** tự giải quyết hết rủi ro user enumeration và DoS.

**`UserDetailsService`** mỗi lần được gọi đọc `isNonLocked(now)`, rồi chuyển sang builder bằng `accountLocked(locked)`. `UserDetails` không nhận biết cách bộ đếm được quản lý; nó chỉ cần phản ánh **trạng thái hiện thời**. Đừng làm những thao tác cập nhật counter trong chính `loadUserByUsername` vì method này có thể bị gọi bởi nhiều luồng khác nhau hoặc bởi cơ chế cache/lookup.

**`DaoAuthenticationProvider`** kiểm tra status và credential theo contract của Spring Security; không có chuyện tự chấp nhận password đúng nếu `isAccountNonLocked() == false`.

**`ProviderManager`** được tạo thủ công và được gắn `DefaultAuthenticationEventPublisher`. Nếu quên dòng `setAuthenticationEventPublisher(...)`, manager được tạo thủ công có thể dùng publisher mặc định không phát sự kiện, và bộ đếm trong `LockoutEvents` sẽ không hoạt động. Kiểm tra cấu hình thực tế của manager đang được security filter chain sử dụng; đừng tạo hai manager phát event trùng.

**`LockoutEvents`** chỉ tăng counter khi có `AuthenticationFailureBadCredentialsEvent`. Với một user bị khóa, provider ném `LockedException`; nó **không** tạo thêm một BadCredentials event chỉ để kéo dài thời hạn khóa. Khi xác thực thành công, `AuthenticationSuccessEvent` reset số lỗi liên tiếp. Sự kiện từ username không tồn tại không tạo account giả vì repository chỉ cập nhật account đã biết.

**`SecurityFilterChain`** dùng Basic để dễ thử bằng curl. `/public/ping` mở cho anonymous, còn `/me` yêu cầu xác thực. Không có endpoint công khai “unlock user”; thao tác mở khóa phải được bảo vệ riêng nếu thêm vào ứng dụng thật.

### Lưu ý về phiên bản Spring Security

Để đảm bảo các kiểm tra account-status không làm giảm bảo vệ chống dò tài khoản qua thời gian phản hồi, cần dùng **bản Spring Security đã vá CVE-2026-22746**: nhánh 7.0.x cần **7.0.5 trở lên**, nhánh 6.5.x cần **6.5.10 trở lên**; các nhánh khác theo advisory chính thức. Không dùng tùy tiện một bản Spring Boot cũ quản lý Spring Security chưa vá. Nếu dự án không thể cập nhật ngay, xem hướng dẫn mitigation của Spring, thay vì tự sửa các kiểm tra credential không có đánh giá bảo mật.

Ví dụ code sử dụng API `DaoAuthenticationProvider(UserDetailsService)` và event publisher được tài liệu Spring Security hỗ trợ. Chọn phiên bản Spring Boot ổn định tương thích Java 17+ và quản lý phiên bản Spring Security đã vá; kiểm tra bằng build dependency tree của dự án.

## 7. Cách chạy và kết quả dự kiến

Trong dự án Spring Boot Servlet có **Spring Web** và **Spring Security**, đặt file theo đúng package trên rồi chạy một trong hai lệnh (chọn build tool của project):

```bash
./gradlew bootRun
# Hoặc với Maven wrapper:
./mvnw spring-boot:run
```

Trên PowerShell, dùng `.\gradlew.bat bootRun` hoặc `.\mvnw.cmd spring-boot:run`. Mã có dependency Spring nên không chạy được bằng lệnh `javac` đơn lẻ khi thiếu classpath; build tool sẽ quản lý dependency.

### 7.1. Kiểm tra đăng nhập bình thường

```bash
curl -s http://localhost:8080/public/ping
curl -s -u an:demo-password http://localhost:8080/me
```

Với demo chưa bị khóa, body của hai request là:

```text
pong
principal=an
```

### 7.2. Tạo ba lỗi mật khẩu liên tiếp

Từ một trạng thái fresh (ví dụ khởi động lại app in-memory), **gửi tuần tự** ba request với mật khẩu sai:

```bash
curl -i -u an:wrong http://localhost:8080/me
curl -i -u an:wrong http://localhost:8080/me
curl -i -u an:wrong http://localhost:8080/me
```

Trong cấu hình HTTP Basic này, mỗi request trên nhận **401 Unauthorized**. Trong backend, mỗi lỗi password sai phù hợp sẽ tạo `BadCredentialsException`, publisher phát failure event và bộ đếm tăng. Lần thứ ba chuyển trạng thái thành `lockedUntil = now + 60 seconds`.

### 7.3. Dù dùng password đúng vẫn bị chặn khi khóa

Gửi tiếp ngay khi chưa hết 60 giây:

```bash
curl -i -u an:demo-password http://localhost:8080/me
```

Request nhận **401** vì `UserDetailsService` trả `accountLocked(true)`; provider từ chối authentication. Không được diễn giải 401 này thành mật khẩu chắc chắn sai.

Sau **khi 60 giây tính từ lần khóa đã trôi qua**, gửi lại credential đúng:

```bash
curl -s -u an:demo-password http://localhost:8080/me
```

Nếu không có sự kiện khóa khác, body là:

```text
principal=an
```

Khi `isNonLocked(now)` thấy đến hạn, nó gỡ lock/counter trước khi build `UserDetails`. Provider kiểm tra password và đăng nhập thành công. Đây là **thời hạn do demo quy định**, không phải đặc tính chung của `isAccountNonLocked`.

### 7.4. Một lần login đúng trước ngưỡng sẽ reset counter

Khởi động app fresh. Gửi hai request sai rồi một request đúng, sau đó hai request sai nữa: ở demo, các chuỗi thất bại bị ngắt bởi thành công nên tài khoản **chưa** đạt ba lần sai liên tiếp sau lần đăng nhập đúng. Khi test thực tế hãy gửi tuần tự và kiểm tra event đã được bật; nếu dùng client retry hoặc mạng bất thường, thứ tự sự kiện có thể khác kỳ vọng.

**HTTP Basic gửi username/password ở dạng Base64, không phải mã hóa bí mật.** Chỉ thử trên localhost; production phải dùng HTTPS. Header `WWW-Authenticate` và nội dung error body phụ thuộc cấu hình/version, nên không giả định chuỗi thông báo cố định.

## 8. Vì sao không nên để login UI tự ghi locked=true?

Một số hệ thống tự triển khai `POST /login` trong controller rồi mỗi lần status 401 sẽ tăng counter. Cách này dễ sai:

- Có nhiều loại 401 không do mật khẩu sai: thiếu credential, token hết hạn, Basic challenge.
- Một controller có thể không phải cửa vào duy nhất: form login, Basic, method authentication hoặc flow khác.
- Nếu bất kỳ request nào có username `victim` cũng có thể set lock không giới hạn, attacker dễ gây denial of service.
- Ghi counter không atomic giữa nhiều app instance tạo race condition.
- Cách tự code password check có thể bỏ qua `PasswordEncoder`, account flags và xử lý lỗi của Spring.

Dùng failure event hoặc một luồng xác thực có điểm kiểm soát tập trung là một hướng tiếp cận; **nhưng phải kiểm chứng manager/publisher và phạm vi sự kiện**. Có hệ thống cần cập nhật counter trong một transaction riêng sau khi xác thực thất bại thay vì chỉ dựa vào event bất đồng bộ. Một event có thể bị xử lý lặp hoặc đến muộn; thiết kế production cần idempotency/ordering phù hợp.

### Event nào nên tăng counter?

| Sự kiện | Có nên tăng bộ đếm “password sai”? | Lý do |
| --- | --- | --- |
| `AuthenticationFailureBadCredentialsEvent` | Thường có, với account thật và policy phù hợp | Credential không hợp lệ; có thể bao gồm username không tồn tại |
| `AuthenticationFailureLockedEvent` | Không nên tăng counter password sai | Account đã khóa; không suy ra credential sai |
| `AuthenticationFailureDisabledEvent` | Không | Account disabled không chứng minh password sai |
| `AuthenticationFailureServiceExceptionEvent` | Không | Dịch vụ xác thực gặp lỗi |
| `AuthenticationSuccessEvent` | Reset theo policy | Đã xác thực thành công |
| HTTP 401 bất kỳ | Không | Quá nhiều nguồn gây 401 ngoài password |

Spring Security có `DefaultAuthenticationEventPublisher` và nhiều class failure event. Publisher mặc định có mapping exception; **mapping dựa trên class exception cụ thể**, nên nếu custom provider ném subclass tự chế cần kiểm tra cấu hình event mapping. Không tự giả định mọi request HTTP đều phát đúng một success/failure event khi có nhiều manager/filters.

## 9. Thiết kế chính sách khóa cho database và nhiều node

Demo dùng trạng thái in-memory, phù hợp để học nhưng không bền vững: restart mất khóa, hai node có bộ đếm khác nhau, và `synchronized` không khóa qua network. Trong production nên dùng repository/Redis/identity service có ngữ nghĩa cập nhật atomic hoặc transaction.

Một schema tham khảo:

```text
users:
    id                   UUID PRIMARY KEY
    username             VARCHAR UNIQUE
    password_hash        VARCHAR
    enabled              BOOLEAN
    admin_locked         BOOLEAN

login_state:
    user_id              UUID REFERENCES users(id)
    failed_attempts      INT
    window_started_at    TIMESTAMP WITH TIME ZONE
    locked_until         TIMESTAMP WITH TIME ZONE NULL
    version              BIGINT
```

Tách `admin_locked` (khóa thủ công) khỏi `locked_until` (tự mở theo thời gian). Nếu cặp user–tenant mới xác định duy nhất tài khoản, hãy xác lập khóa phù hợp. Thời gian dùng UTC, có nguồn đồng hồ nhất quán và quyết định rõ ranh giới hết hạn.

### Transaction/atomicity

Một luồng ghi thất bại nên làm theo quy tắc nhất quán:

```text
Với một accountId đã xác định tin cậy:
  BEGIN TRANSACTION
    Khóa hàng trạng thái hoặc dùng optimistic version/CAS
    Nạp failed_attempts, window_started_at, locked_until
    Nếu đã hết cửa sổ:
        reset số lần sai/cửa sổ
    Nếu đang khóa:
        không cộng lỗi chỉ vì có thêm request
    Nếu không khóa:
        tăng đúng 1 lần thất bại credential đã ghi nhận
        nếu đạt ngưỡng: đặt locked_until theo policy
    Ghi audit cần thiết
  COMMIT
```

Đây là **pseudo-code của policy**, không phải SQL chạy trực tiếp. DB cụ thể cần transaction isolation, row lock hoặc optimistic locking phù hợp; nếu dùng cache/Redis, cần atomic script/transaction tương đương. Phải định nghĩa cách giải quyết **thứ tự yêu cầu và sự kiện**: request đã bắt đầu khi chưa khóa nhưng kết thúc sau khi một request khác đặt lock có được công nhận không? Với thao tác rủi ro cao, chính sách có thể yêu cầu kiểm tra lock ngay trước khi cấp phiên.

Khi có sự kiện trùng hoặc listener retry, một lần sai không được cộng hai lần do xử lý lặp. Có thể dùng event ID, version, unique constraint hoặc đặt update ngay trong transaction của authentication boundary. Việc khóa tài khoản phải có audit nhưng tránh lưu raw credential.

### Cửa sổ cố định và trượt

- **Fixed window:** đếm trong một khoảng cố định; đơn giản nhưng có thể cho nhiều lần thử ở ranh giới hai cửa sổ.
- **Sliding window:** đếm trong khoảng thời gian gần nhất; phản ánh tần suất sát hơn, đòi hỏi lưu dữ liệu/tổng hợp thích hợp.
- **Exponential backoff:** tăng thời gian chờ sau các chuỗi thất bại; cần giới hạn trên và kênh khôi phục.

Chọn chính sách theo threat model và tải hệ thống; demo chỉ dùng “ba lần sai liên tiếp, khóa 60 giây”, **không có cửa sổ thời gian cho counter**. Khi dùng thật, không nên giữ hai lần sai từ nhiều tháng trước rồi khóa người dùng chỉ vì một lần sai mới.

### Tính đúng khi đồng thời

Ngay cả nếu update counter là atomic, việc `UserDetailsService` đọc lock và provider kiểm tra credential có thể diễn ra trước khi một request khác cập nhật `locked_until`. Với hệ thống cần chính sách cực nghiêm ngặt, phải tính đến tính nhất quán cuối cùng của lock state trong **toàn bộ quyết định phát hành phiên/token**. Đừng coi `synchronized` trên entity hoặc một máy chủ là bảo vệ đủ cho cụm nhiều instance.

## 10. Chống user enumeration và lưu ý bảo mật Spring Security 2026

**User enumeration** là việc attacker suy đoán tài khoản nào tồn tại dựa vào phản hồi hoặc độ trễ khác nhau. Nếu server trả:

- `Unknown username` khi không có account.
- `Account locked` khi có account đang khóa.
- `Wrong password` khi account tồn tại và mở.

thì người chưa đăng nhập có thể phân loại danh sách user hợp lệ.

`DaoAuthenticationProvider` thường có cơ chế che `UsernameNotFoundException` thành `BadCredentialsException`. Nhưng **che message không đủ** nếu thời gian xử lý của account bị khóa/disabled khác rõ với user không tồn tại hoặc active.

### Advisory có liên quan trực tiếp

Spring đã công bố **CVE-2026-22746 – User Attribute Enumeration when Using DaoAuthenticationProvider** (20/04/2026). Theo advisory, một số phiên bản Spring Security cho phép vượt qua biện pháp timing-attack defense khi dùng `UserDetails.isEnabled()`, `isAccountNonExpired()` hoặc `isAccountNonLocked()`. Các nhánh bị ảnh hưởng gồm 7.0.0–7.0.4 và 6.5.0–6.5.9; bản sửa tương ứng là 7.0.5 và 6.5.10. Các nhánh cũ hơn có bản sửa theo hỗ trợ cụ thể. Xem advisory gốc trong tài liệu cuối bài.

**Vì vậy:** dùng bản Spring Security đã vá qua phiên bản Spring Boot/dependency management phù hợp; không tắt `setAlwaysPerformAdditionalChecksOnUser(...)` một cách tùy tiện để “tối ưu hiệu năng” mà thiếu đánh giá bảo mật. Flag này liên quan việc vẫn thực hiện các kiểm tra bổ sung nhằm giảm khác biệt thời gian khi pre-authentication status check thất bại.

Ngay cả sau khi nâng cấp, vẫn cần thông báo công khai trung lập, giới hạn tốc độ, an toàn kênh recovery và kiểm thử timing ở mức phù hợp; một patch không thay thế mọi biện pháp chống enumeration.

### Phản hồi công khai và thông tin nội bộ

Bên ngoài, với Basic API, có thể trả một phản hồi chung khi login sai hoặc bị khóa: HTTP 401 cùng challenge theo giao thức. Không tự xuất `LockedException.getMessage()` ra JSON công khai. Bên trong, log/audit có thể ghi account ID (khi nguồn xác nhận), loại sự kiện, thời điểm, cơ chế và correlation ID, nhưng không ghi password, bearer token, cookie hoặc password hash.

Một luồng tự phục vụ đã **xác minh quyền sở hữu** có thể cho user biết cần chờ hoặc làm thủ tục mở khóa. Không biến endpoint public không xác thực thành API kiểm tra trạng thái tài khoản.

## 11. Phân biệt account lock, rate limit, disabled, 401 và 403

| Tình huống | Bản chất | Phản hồi thường gặp trong HTTP Basic |
| --- | --- | --- |
| Password không đúng | Authentication thất bại | 401 |
| Account bị khóa qua `isAccountNonLocked=false` | Authentication thất bại | 401 |
| Account disabled | Authentication thất bại do state | 401 |
| Không có Basic credentials cho API bảo vệ | Chưa xác thực | 401/challenge |
| Đã xác thực nhưng thiếu role của endpoint | Authorization bị từ chối | 403 |
| Quá nhiều request theo IP | Throttling/rate limiting trước hoặc quanh auth | Có thể là 429, tùy policy/API |
| Backend auth không khả dụng | Lỗi hệ thống | Không nên nhầm với password sai; xử lý vận hành riêng |

**Không có mapping 1:1 từ một exception Java đến một status HTTP trong mọi cấu hình.** Form login thường có redirect/failure handler; bearer token dùng challenge theo giao thức. Với Basic demo, 401 là phản hồi phổ biến cho lỗi đăng nhập.

Lock account và rate limit có thể phối hợp nhưng là hai điều kiện khác nhau. Rate limiter có thể từ chối request **trước khi** `UserDetailsService` được gọi; lúc đó không nhất thiết có `LockedException`, và không nên đánh dấu user bị khóa chỉ vì một IP vượt ngưỡng.

### Không nhầm với AccessDeniedException

Nếu một người dùng đã authenticated nhưng không có `ROLE_ADMIN`, authorization có thể ném `AccessDeniedException`; thông thường HTTP 403. Đây **không phải** account lock. Ngược lại, một tài khoản bị khóa chưa vượt qua authentication thì không có “người dùng đã đăng nhập thành công” để kiểm tra role cho lần login mới.

### Tùy biến thông báo

Nếu cần JSON generic 401 cho Basic, tùy biến `AuthenticationEntryPoint` tương ứng và giữ `WWW-Authenticate`. Với form login, dùng `AuthenticationFailureHandler` theo cơ chế đó. `@RestControllerAdvice` không phải nơi thay thế mọi lỗi phát sinh trước MVC trong Spring Security filter chain.

Tránh hiển thị `lockedUntil` chính xác cho người chưa xác thực nếu thông tin đó giúp khảo sát account hoặc chiến lược bảo mật. Có thể cung cấp thông tin hỗ trợ sau khi chủ tài khoản được xác minh qua kênh an toàn.

## 12. Phiên đã đăng nhập: khóa có tự làm hết quyền không?

Một điểm rất dễ bỏ sót: `isAccountNonLocked()` thường được đánh giá **trong lúc authentication**. Sau khi login thành công, `Authentication` có thể tồn tại trong HTTP session hoặc token. Nếu admin khóa user lúc 10:00 nhưng user có session hợp lệ từ 09:00, framework **không tự đảm bảo** session ấy bị hủy ngay khi cột `locked_until` thay đổi.

Các hướng xử lý tùy yêu cầu:

1. **Invalidation/revocation:** thu hồi các session hoặc refresh/access token tương ứng khi áp khóa.
2. **TTL hợp lý:** giảm thời gian session/token chứa trạng thái cũ.
3. **Kiểm tra ở thao tác nhạy cảm:** policy/domain service xác minh account còn hoạt động trước giao dịch rủi ro cao.
4. **SecurityContext refresh:** thiết kế cơ chế nạp lại dữ liệu account/quyền trong session khi cần; tránh chỉ tin snapshot vô thời hạn.
5. **Cache invalidation:** nếu `UserDetailsService` hoặc token introspection có cache, xác định thời gian và sự kiện xóa cache.
6. **Audit phiên:** theo dõi actor ID và nguồn login; không sử dụng username thay cho khóa internal user ID lâu dài.

Với HTTP Basic, credential thường được gửi lại ở mỗi request và có thể tạo lần authentication mới, nhưng cache/kiến trúc vẫn có thể làm dữ liệu không cập nhật ngay. Với JWT tự chứa quyền, lock trong DB không sửa token đã ký; cần revoke/TTL/introspection hoặc kiểm tra bổ sung theo policy.

Vì vậy, **“khóa tài khoản” cần có phạm vi hiệu lực**: chỉ chặn login mới hay còn chặn session hiện có? Tài liệu chính sách phải trả lời rõ.

## 13. Quy trình mở khóa và phục hồi an toàn

Có ít nhất ba tình huống:

- **Tự mở khóa theo TTL:** khi đến `lockedUntil`, backend xem state là nonlocked; không cần timer nếu quy tắc kiểm tra được thực hiện khi đọc trạng thái.
- **Mở khóa do admin:** cần RBAC, audit, lý do và ngăn thao tác lạm quyền. Không xây endpoint `GET /unlock?user=an` công khai.
- **User recovery:** xác minh quyền sở hữu qua kênh đáng tin, dùng rate limiting và tránh cung cấp thông tin có thể dò user.

Khi mở khóa, cần xác định có reset `failedAttempts` và cửa sổ lỗi hay không. Nếu chỉ xóa `lockedUntil` nhưng counter vẫn ở ngưỡng, request thất bại tiếp theo có thể khóa lại ngay; điều đó có thể đúng hoặc sai tùy chính sách. Demo reset counter khi hết khóa.

Đối với khóa thủ công, không được tự mở chỉ vì đã qua TTL của một khóa tạm. Nếu tài khoản disabled hoặc đã bị xóa, xóa khóa tạm cũng không được tự kích hoạt tài khoản. Các cờ trạng thái cần được xử lý **độc lập và có thứ tự chính sách rõ ràng**.

### Thông báo người dùng

Thông báo khóa nên đi qua kênh đã xác minh phù hợp, giảm tiết lộ user enumeration. Không gửi email/SMS không giới hạn cho mỗi request sai, vì attacker có thể lợi dụng để spam nạn nhân. Có thể gộp thông báo, giới hạn tần suất, kèm hướng dẫn tự phục hồi không tiết lộ dữ liệu nhạy cảm.

## 14. Kiểm thử bắt buộc cho isAccountNonLocked và policy

Không chỉ test method trả boolean. Một bộ test tốt cần phân biệt dữ liệu state, provider authentication, event/counter và ảnh hưởng đến HTTP/session.

| Case | Setup | Kết quả mong đợi |
| --- | --- | --- |
| Account bình thường | `lockedUntil=null` | `isAccountNonLocked=true`, tiếp tục auth |
| Lock còn thời hạn | `now < lockedUntil` | `isAccountNonLocked=false`, provider từ chối |
| Đến đúng hạn mở | `now == lockedUntil` | `isAccountNonLocked=true` theo policy demo |
| Password đúng, đang khóa | Account locked | Không phát authenticated `Authentication` |
| Password sai, chưa khóa | State ACTIVE | `BadCredentialsException`, tăng đúng counter theo policy |
| Đủ ba lần sai liên tiếp | Counter đạt ngưỡng | Ghi `lockedUntil`, auth tiếp theo bị chặn |
| Login đúng trước ngưỡng | Có 1–2 lần sai | Reset counter |
| Unknown username | Không có account | Không tạo khóa account giả, response công khai trung lập |
| Trạng thái disabled | `enabled=false` | Không dùng locked flag để giả thay disabled |
| Database lỗi | Không đọc được lock state | Fail closed/alert, không mặc định nonlocked |
| Hai request sai đồng thời | Cùng user | Không mất increment, không tạo race tùy tiện |
| Hai instance | Dùng chung database/cache | Lock state nhất quán theo hợp đồng |
| Unlock thủ công | Admin hợp lệ | Có audit và không mở khóa account khác |
| Session cũ sau khóa | Đã login trước | Hành vi đúng theo chính sách revoke |
| User enumeration | Username sai/locked/active | Thông báo và timing được kiểm tra |
| Token đã phát hành | JWT/session còn hạn | Không mặc định token tự hết hiệu lực khi DB đổi |

### Test logic thời gian mà không ngủ 60 giây

Ở tầng domain, nên inject `java.time.Clock` hoặc truyền `Instant now` để thử mốc thời gian quyết định. Ví dụ kiểm thử đơn giản dùng chính `DemoAccount` trong project demo (đây là **mảnh code kiểm thử**, không phải một file chạy độc lập):

```java
Instant t0 = Instant.parse("2026-01-01T00:00:00Z");
DemoAccount state = new DemoAccount("test", "encoded-unused");

System.out.println(state.isNonLocked(t0));
state.recordBadCredentials(t0);
state.recordBadCredentials(t0);
state.recordBadCredentials(t0);

System.out.println(state.isNonLocked(t0.plusSeconds(59)));
System.out.println(state.isNonLocked(t0.plusSeconds(60)));
```

Kết quả chính xác khi chạy đoạn code trên ở cùng package:

```text
true
false
true
```

Đoạn này chỉ test **trạng thái trong bộ nhớ**; không kiểm tra password/provider, và tham số `"encoded-unused"` không được dùng để xác thực. Ưu điểm là test mốc TTL ngay lập tức mà không phải đợi thời gian thực. Với policy phức tạp, nên thêm test đúng ranh giới cửa sổ, sai lệch đồng hồ và thao tác unlock.

### Integration test

Ở tầng HTTP/security, ngoài kiểm tra mã 401, nên xác nhận không có authenticated `Authentication` khi locked. Kiểm tra publisher được cấu hình đúng, số event failure/success, giới hạn trùng event và hành vi với username không tồn tại. Nếu cần test nhiều node, dùng test database/Redis thật hoặc mô phỏng concurrency; unit test với `synchronized` không chứng minh an toàn trong cluster.

## 15. Lỗi phổ biến trong triển khai

| Sai lầm | Tác hại | Cách sửa |
| --- | --- | --- |
| Trả `locked` từ `isAccountNonLocked()` | Đảo logic, user bình thường bị từ chối | Trả phủ định của locked flag |
| Gọi `accountLocked(!locked)` | Đảo hai lần | Builder nhận `locked`, không phải `nonLocked` |
| Tin Spring tự đếm số lần sai | Không có state transition | Có service/event/repository quản lý policy |
| Tăng counter theo mọi HTTP 401 | Đếm cả thiếu token, challenge, lỗi khác | Chỉ theo loại authentication failure thích hợp |
| Coi `LockedException` là password đúng | Lộ thông tin và sai suy luận | Phân biệt status check với credential verification |
| Lock vĩnh viễn sau rất ít lần sai | Dễ bị attacker khóa người dùng hàng loạt | Tầng throttling, TTL, recovery, threat model |
| Khóa theo username tùy ý mà không ràng buộc kho thật | Bùng nổ dữ liệu và user enumeration | Lookup account có thẩm quyền, lưu theo account ID |
| Counter chỉ nằm trong RAM mỗi node | Lock không nhất quán | DB/Redis atomic, transaction và cache policy |
| Tự mở mọi khóa khi TTL hết | Gỡ nhầm khóa admin | Trạng thái manual lock riêng |
| Tạo `ProviderManager` nhưng quên publisher | Failure events không được phát | Cấu hình publisher hoặc điểm tích hợp rõ |
| Dùng event bất đồng bộ không bảo đảm thứ tự | Success và failure có thể áp sai trình tự | Ordering/idempotency/transaction rõ |
| Dùng phiên bản Spring Security có lỗi timing | Có thể dò thuộc tính user | Nâng cấp theo advisory bảo mật |
| Khóa user trong DB nhưng bỏ qua session cũ | User vẫn hoạt động với phiên trước | Revoke session/token hoặc policy refresh |
| Log raw Basic header/password | Rò credential | Log tối thiểu, tránh secrets |
| Trả `LockedException` ra response public | Lộ trạng thái tài khoản | Response chung, recovery qua kênh xác minh |
| Không kiểm tra quyền mở khóa | Privilege escalation | Authorization và audit riêng cho admin |

## 16. Tự kiểm tra kiến thức

**Câu 1.** `isAccountNonLocked() == true` nghĩa là gì?  
**Trả lời:** Chỉ nghĩa account **không bị khóa**. Nó không đảm bảo password đúng hoặc mọi trạng thái khác đều hợp lệ.

**Câu 2.** Database có `locked=true`. Với custom `UserDetails`, method phải trả gì?  
**Trả lời:** `false`. Nếu dùng builder `User.withUsername(...)` thì gọi `accountLocked(true)`.

**Câu 3.** Account bị khóa nhưng caller gửi password đúng. Provider có được phát authenticated token không?  
**Trả lời:** Không. State check phải chặn theo hợp đồng, độc lập với kết quả password.

**Câu 4.** Spring Security có tự khóa user sau 5 lần `BadCredentialsException` không?  
**Trả lời:** Không. Ứng dụng/identity platform phải định nghĩa và lưu state chuyển khóa, đồng bộ giữa các instance nếu cần.

**Câu 5.** Vì sao khóa vĩnh viễn sau 3 lần sai có thể nguy hiểm?  
**Trả lời:** Attacker có thể cố ý nhập sai nhiều lần cho tài khoản nạn nhân để làm dịch vụ từ chối người dùng hợp lệ.

**Câu 6.** Một failure event BadCredentials có luôn đại diện tài khoản thật không?  
**Trả lời:** Không. Provider có thể che username không tồn tại thành lỗi credential sai; không tạo bản ghi user/khóa chỉ từ username tự khai.

**Câu 7.** Vì sao một manager tự tạo cần được cấu hình event publisher?  
**Trả lời:** `ProviderManager` không mặc định bảo đảm phát Spring application events khi được tạo thủ công; không có publisher thì listener có thể không nhận các failure/success cần cho policy.

**Câu 8.** Nếu đã đến `lockedUntil` nhưng account vẫn `adminLocked=true` thì có mở không?  
**Trả lời:** Không. Khóa thủ công là điều kiện riêng, không tự gỡ theo TTL.

**Câu 9.** Đổi `lockedUntil` trong DB có tự hủy mọi JWT/session đã phát hành không?  
**Trả lời:** Không. Phải có chính sách thu hồi/refresh/authorization riêng nếu muốn khóa ảnh hưởng phiên cũ.

**Câu 10.** HTTP 401 có đồng nghĩa account locked không?  
**Trả lời:** Không. Nó còn có thể do password sai, thiếu credential hoặc cơ chế xác thực khác; không dùng status HTTP chung làm counter khóa.

**Câu 11.** Cần lưu ý gì với Spring Security 7.0.0–7.0.4 nếu dùng `isAccountNonLocked`?  
**Trả lời:** Các bản đó nằm trong phạm vi CVE-2026-22746; cần nâng cấp tối thiểu nhánh 7.0 lên 7.0.5 hoặc bản vá phù hợp theo advisory.

## Kết luận

`UserDetails.isAccountNonLocked()` là **hợp đồng biểu diễn trạng thái không bị khóa**. Trả `false` khiến cơ chế xác thực DAO thông thường từ chối bằng `LockedException`; nó **không** tạo chính sách đếm lỗi, không tự quyết định TTL và không hủy phiên đang tồn tại.

Một chính sách khóa tài khoản có trách nhiệm phải có nguồn state tin cậy, bộ đếm/thời hạn được cập nhật atomic, rate limiting chống brute force lẫn denial of service, kênh mở khóa có xác minh, session/token revocation khi cần, và thông báo công khai không làm lộ username. Các biện pháp này bổ sung cho `PasswordEncoder`, `UserDetailsService`, `AuthenticationProvider` và authorization, chứ không thay thế chúng.

**Quy tắc nhớ:** *`isAccountNonLocked()` thực thi trạng thái khóa khi authentication; chính sách khóa/mở khóa, cập nhật bền vững và chống lạm dụng phải được thiết kế riêng.*

### Tài liệu chính thức

- [Spring Security — UserDetails API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html)
- [Spring Security — User.UserBuilder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — AuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationManager.html)
- [Spring Security — Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html)
- [Spring Security — HTTP Basic](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — CVE-2026-22746: User Attribute Enumeration when Using DaoAuthenticationProvider](https://spring.io/security/cve-2026-22746/)
