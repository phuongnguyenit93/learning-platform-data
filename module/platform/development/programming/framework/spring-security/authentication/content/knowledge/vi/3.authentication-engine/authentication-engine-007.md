# DaoAuthenticationProvider trong xác thực username và password

## 1. DaoAuthenticationProvider giải quyết vấn đề gì?

Trong Spring Security, **`DaoAuthenticationProvider` là một triển khai `AuthenticationProvider` dùng để xác thực cặp tên đăng nhập và mật khẩu**. Nó nhận một `UsernamePasswordAuthenticationToken` chưa được xác thực, lấy thông tin tài khoản từ `UserDetailsService`, kiểm tra mật khẩu bằng `PasswordEncoder`, kiểm tra trạng thái tài khoản và trả về một đối tượng `Authentication` đã xác thực khi hợp lệ.

Tên **DAO** (Data Access Object) phản ánh việc lấy thông tin người dùng từ một nguồn dữ liệu, nhưng class này **không tự kết nối JDBC/JPA, không mặc định truy vấn bảng `users`, cũng không tự tạo tài khoản**. Nguồn dữ liệu cụ thể do ứng dụng cung cấp qua `UserDetailsService`: trong bộ nhớ, JDBC, repository JPA, hoặc adapter phù hợp.

Hãy nhớ bốn vai trò:

| Thành phần | Chịu trách nhiệm | Không nên nhầm với |
| --- | --- | --- |
| `UsernamePasswordAuthenticationToken` | Đưa username/credentials vào quá trình xác thực; giữ kết quả khi đã được xác minh. | Kho tài khoản hoặc bộ kiểm tra mật khẩu. |
| `AuthenticationManager` (thường là `ProviderManager`) | Nhận yêu cầu và chuyển cho một `AuthenticationProvider` có thể xử lý. | Thuật toán so khớp mật khẩu. |
| **`DaoAuthenticationProvider`** | Phối hợp tải `UserDetails`, kiểm tra trạng thái tài khoản và `PasswordEncoder`, dựng kết quả xác thực. | Controller đăng nhập, filter HTTP hoặc lớp lưu tài khoản. |
| `UserDetailsService` + `PasswordEncoder` | Lấy hồ sơ đăng nhập/authorities và so mật khẩu thô với hash lưu trữ. | Hai thao tác thay thế cho nhau. |

Ví dụ nghiệp vụ: người dùng gửi `lan` và mật khẩu `DemoPass123!`. `UserDetailsService` tìm `lan`, trả `UserDetails` chứa password **hash** và các quyền. `DaoAuthenticationProvider` dùng `encoder.matches(rawPassword, storedHash)`, kiểm tra cờ enabled/locked/expired rồi trả authenticated token. Controller không cần tự lấy hash từ cơ sở dữ liệu để so.

**Phạm vi:** đây là cơ chế **username/password**. JWT bearer, OIDC/OAuth2 login và các cơ chế xác thực khác có provider/luồng riêng; không ép mọi cách đăng nhập chạy qua `DaoAuthenticationProvider`.

## 2. Vị trí trong bộ máy xác thực Servlet

Với Spring MVC hoặc HTTP Basic, luồng điển hình như sau:

```text
Client gửi username + password
           |
           v
Servlet security filter (ví dụ BasicAuthenticationFilter
                          hoặc UsernamePasswordAuthenticationFilter)
           |
           | tạo UsernamePasswordAuthenticationToken
           |   principal   = username client khai báo
           |   credentials = raw password
           |   authenticated = false
           v
AuthenticationManager.authenticate(request)
           |
           v
ProviderManager
           |
           +--> chọn AuthenticationProvider theo supports(...)
                      |
                      v
              DaoAuthenticationProvider
                      |
                      +--> UserDetailsService.loadUserByUsername(username)
                      |          |
                      |          +--> bộ nhớ, JDBC, JPA, adapter DB...
                      |          |
                      |          v
                      |        UserDetails: username, hash, enabled,
                      |                     locked/expired, authorities
                      |
                      +--> kiểm tra trạng thái tài khoản
                      +--> PasswordEncoder.matches(raw, storedHash)
                      +--> kiểm tra credentials đã hết hạn, nếu áp dụng
                      |
           +----------+-----------+
           |                      |
         Thất bại               Thành công
           |                      |
           v                      v
AuthenticationException     Authenticated Authentication
(BadCredentialsException,    principal = UserDetails (mặc định)
 DisabledException, ...)     authorities từ nguồn đáng tin cậy
                              authenticated = true
                                     |
                                     v
                          Filter cập nhật SecurityContext
                                     |
                                     v
                         Authorization kiểm tra quyền
                                     |
                                     v
                          Controller/service được phép
```

Sơ đồ nêu **một cấu hình thường gặp**, không phải mọi request web đều gọi provider. Nếu người dùng đã có session được thiết lập hợp lệ, một request tiếp theo có thể dùng `SecurityContext` đã phục hồi mà không phải kiểm tra BCrypt lại. Với HTTP Basic, client có thể gửi lại credentials ở các request mới và cơ chế kiểm tra có thể chạy tương ứng.

### Lúc đầu và lúc cuối, `Authentication` có khác gì?

Yêu cầu đầu vào:

```java
Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "lan", "DemoPass123!");
// request.isAuthenticated() == false
```

Sau xác thực thành công:

```java
Authentication verified = authenticationManager.authenticate(request);
// verified.isAuthenticated() == true
// verified.getPrincipal() thường là UserDetails
// verified.getAuthorities() chứa các GrantedAuthority đáng tin cậy
```

Đối tượng đầu vào và kết quả cùng interface `Authentication` nhưng **không bắt buộc cùng instance**. Dùng `verified`, không dựa vào giả định provider thay cờ trực tiếp trên `request`. Khi mật khẩu sai hoặc tài khoản không hợp lệ, hàm thường ném một subclass của `AuthenticationException`; không có “kết quả đã đăng nhập” để tiếp tục dùng.

## 3. Một vòng authenticate bên trong provider diễn ra thế nào?

`DaoAuthenticationProvider` kế thừa `AbstractUserDetailsAuthenticationProvider`. Lớp cha cung cấp khung xử lý chung; provider triển khai cách lấy user và kiểm tra mật khẩu.

### Bước 1. Kiểm tra kiểu yêu cầu

`DaoAuthenticationProvider.supports(...)` phù hợp với `UsernamePasswordAuthenticationToken`. `ProviderManager` có thể giữ nhiều provider; một provider chỉ nên nhận các kiểu request mà nó hiểu. Vì vậy `DaoAuthenticationProvider` **không phải nơi kiểm tra JWT hay SAML assertion**.

Nếu không có provider nào hỗ trợ kiểu token, `ProviderManager` có thể ném `ProviderNotFoundException`. Lỗi này thường cho thấy cấu hình manager/provider hoặc loại token đầu vào sai, không phải “password của user sai”.

### Bước 2. Tải `UserDetails`

Provider dùng `UserDetailsService.loadUserByUsername(String username)` để lấy hồ sơ xác thực:

- `getUsername()`: tên tài khoản/định danh đăng nhập.
- `getPassword()`: **chuỗi hash/encoded password**, không phải plaintext.
- `isEnabled()`: tài khoản được bật hay không.
- `isAccountNonLocked()`: không bị khóa.
- `isAccountNonExpired()`: tài khoản chưa hết hạn.
- `isCredentialsNonExpired()`: credential chưa hết hạn.
- `getAuthorities()`: roles/scopes/quyền ứng dụng cấp cho tài khoản.

`UserDetailsService` **chỉ tải thông tin tài khoản**. Nó không tự thực hiện `matches(...)`, không tự tạo session và không nên coi người dùng đã đăng nhập khi tìm thấy username.

Nếu không tìm thấy, triển khai nên ném `UsernameNotFoundException`. Theo mặc định, `AbstractUserDetailsAuthenticationProvider` thường chuyển trường hợp user không tồn tại thành `BadCredentialsException` giống mật khẩu sai để hạn chế lộ sự tồn tại của tài khoản.

### Bước 3. Kiểm tra trạng thái tài khoản

Khung provider thực hiện các bước kiểm tra tình trạng tài khoản (pre/post authentication checks) theo cấu hình:

| Trạng thái `UserDetails` | Ý nghĩa | Exception thường gặp |
| --- | --- | --- |
| `enabled == false` | Tài khoản đã bị vô hiệu hóa. | `DisabledException` |
| `accountNonLocked == false` | Tài khoản đang bị khóa. | `LockedException` |
| `accountNonExpired == false` | Tài khoản đã hết hạn. | `AccountExpiredException` |
| `credentialsNonExpired == false` | Mật khẩu/credential đã hết hạn. | `CredentialsExpiredException` |

Các bước kiểm tra tài khoản và so mật khẩu có thể được điều chỉnh theo phiên bản/cấu hình. Không viết nghiệp vụ phụ thuộc vào **thứ tự** exception rò rỉ ra phía client. API đăng nhập thường nên trả thông báo bên ngoài có kiểm soát; log nội bộ có thể phân loại nguyên nhân để phục vụ vận hành, nhưng không log secret.

### Bước 4. So mật khẩu đúng cách

`DaoAuthenticationProvider` gọi `PasswordEncoder.matches(rawPassword, storedEncodedPassword)`. Với BCrypt:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder();
String hash = encoder.encode("DemoPass123!");

System.out.println(encoder.matches("DemoPass123!", hash)); // true
System.out.println(encoder.matches("wrong", hash));        // false
```

`encode` có salt ngẫu nhiên nên gọi hai lần có thể tạo **hai hash khác nhau cho cùng mật khẩu**. Vì vậy **không** so `encoder.encode(input).equals(storedHash)`. `matches` đọc định dạng hash, dùng thông số cần thiết để so một cách phù hợp.

Ứng dụng phải dùng **encoder tương thích với dữ liệu đang lưu**. Ví dụ, nếu ghi BCrypt trực tiếp thì `BCryptPasswordEncoder` hiểu hash dạng `$2a$...`/`$2b$...`; nếu dùng `DelegatingPasswordEncoder`, chuỗi lưu thường có tiền tố như `{bcrypt}...`. Trộn các cách lưu mà không có quy tắc nhất quán có thể khiến password đúng vẫn không khớp hoặc báo không xác định id.

### Bước 5. Tạo kết quả đáng tin cậy

Khi kiểm tra thành công, provider tạo `UsernamePasswordAuthenticationToken` **đã được xác thực**, thường chứa:

- `principal`: đối tượng `UserDetails` trả về từ nguồn (mặc định), hoặc String nếu ứng dụng chủ động cấu hình `setForcePrincipalAsString(true)`.
- `authorities`: các `GrantedAuthority` từ tài khoản, có thể qua `GrantedAuthoritiesMapper` nếu được cấu hình.
- `isAuthenticated() == true`.
- `credentials`: có thể tồn tại tạm thời ở kết quả provider; `ProviderManager` mặc định cố gắng xóa credentials của kết quả thành công qua `CredentialsContainer`.

**Không tự gọi** `UsernamePasswordAuthenticationToken.authenticated(usernameFromClient, null, suppliedRoles)` để “đăng nhập nhanh”: làm thế là bỏ qua kiểm chứng. Luôn dùng provider/manager đã cấu hình và dùng đối tượng trả về sau thành công.

### Bước 6. Đưa kết quả vào `SecurityContext`

`DaoAuthenticationProvider` **không tự tạo HTTP session hay cookie**. Nó trả `Authentication` cho caller. Với filter đăng nhập chuẩn, phần filter/framework quản lý cập nhật `SecurityContext`, xử lý failure/success và lưu state theo cơ chế xác thực cấu hình.

Nếu gọi `AuthenticationManager.authenticate(...)` trực tiếp trong code console hoặc service, kết quả **không mặc nhiên** có trong `SecurityContextHolder`. Bạn chỉ tự đặt context khi hiểu hợp đồng phiên/ngữ cảnh và không bỏ qua filter bảo mật.

## 4. Ví dụ hoàn chỉnh Java 17+: provider, kho user, lỗi và kết quả

Ví dụ console này sử dụng **Spring Security 6.5.11**, Java 17+ và Gradle. Nó minh họa chính xác lớp provider hoạt động **không cần web server hay Spring Boot**. `InMemoryUserDetailsManager` được dùng làm kho danh tính thử nghiệm; `BCryptPasswordEncoder` chịu trách nhiệm băm và so mật khẩu.

Cấu trúc:

```text
dao-provider-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/DaoProviderDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'dao-provider-demo'
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
    mainClass = 'demo.DaoProviderDemo'
}
```

`src/main/java/demo/DaoProviderDemo.java`:

```java
package demo;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class DaoProviderDemo {

    public static void main(String[] args) {
        // Kho danh tính demo: chỉ lưu hash, không lưu mật khẩu dạng rõ.
        PasswordEncoder encoder = new BCryptPasswordEncoder();

        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("DemoPass123!"))
                .roles("READER")
                .build();

        UserDetails khoa = User.withUsername("khoa")
                .password(encoder.encode("AnotherPass123!"))
                .roles("READER")
                .disabled(true)
                .build();

        InMemoryUserDetailsManager users =
                new InMemoryUserDetailsManager(lan, khoa);

        // DaoAuthenticationProvider tải UserDetails và so credentials.
        DaoAuthenticationProvider dao = new DaoAuthenticationProvider(users);
        dao.setPasswordEncoder(encoder);

        // Trong web, AuthenticationManager thường được gọi từ filter.
        AuthenticationManager manager = new ProviderManager(dao);

        System.out.println("dao.supportsUsernamePassword="
                + dao.supports(UsernamePasswordAuthenticationToken.class));

        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "DemoPass123!");

        System.out.println("request.authenticated=" + request.isAuthenticated());
        System.out.println("request.authorities=" + request.getAuthorities().size());

        // 1. Mật khẩu sai: không trả authenticated token.
        try {
            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "lan", "wrong-password"));
        } catch (BadCredentialsException ex) {
            System.out.println("wrongPassword=BadCredentialsException");
        }

        // 2. Username không tồn tại: mặc định cũng bị che thành BadCredentials.
        try {
            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "unknown", "any-password"));
        } catch (BadCredentialsException ex) {
            System.out.println("unknownUser=BadCredentialsException");
        }

        // 3. Tài khoản tắt: bị từ chối dù có mật khẩu tương ứng.
        try {
            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "khoa", "AnotherPass123!"));
        } catch (DisabledException ex) {
            System.out.println("disabledUser=DisabledException");
        }

        // 4. Xác thực đúng: nhận Authentication mới đã được chứng minh.
        Authentication result = manager.authenticate(request);

        System.out.println("result.authenticated=" + result.isAuthenticated());
        System.out.println("result.name=" + result.getName());
        System.out.println("result.principalIsUserDetails="
                + (result.getPrincipal() instanceof UserDetails));
        System.out.println("result.hasReaderRole=" + result.getAuthorities()
                .stream()
                .anyMatch(a -> "ROLE_READER".equals(a.getAuthority())));
        System.out.println("result.credentialsErased="
                + (result.getCredentials() == null));

        // 5. Cách đặt SecurityContext trong console; filter web xử lý riêng.
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(result);
        SecurityContextHolder.setContext(context);
        try {
            System.out.println("context.name="
                    + SecurityContextHolder.getContext()
                    .getAuthentication().getName());
        } finally {
            SecurityContextHolder.clearContext();
        }
        System.out.println("context.cleared="
                + (SecurityContextHolder.getContext().getAuthentication() == null));
    }
}
```

Chạy tại thư mục gốc dự án bằng JDK 17+ và Gradle hỗ trợ Java 17 (hoặc Gradle Wrapper tương thích):

```bash
gradle run --quiet
```

**Các dòng stdout từ `System.out.println` theo đúng thứ tự** (không tính log Gradle hoặc thư viện nếu môi trường phát sinh):

```text
dao.supportsUsernamePassword=true
request.authenticated=false
request.authorities=0
wrongPassword=BadCredentialsException
unknownUser=BadCredentialsException
disabledUser=DisabledException
result.authenticated=true
result.name=lan
result.principalIsUserDetails=true
result.hasReaderRole=true
result.credentialsErased=true
context.name=lan
context.cleared=true
```

Giải thích từng quan sát:

1. `supportsUsernamePassword=true` vì provider xử lý `UsernamePasswordAuthenticationToken`.
2. Request ban đầu có `isAuthenticated()==false` và không có quyền tin cậy; có username không đồng nghĩa đã login.
3. `wrongPassword` và `unknownUser` đều nhận `BadCredentialsException` theo hành vi che username mặc định. Không đổi cấu hình chỉ để client biết tài khoản có tồn tại hay không.
4. `disabledUser` bị từ chối bởi account-state check; `isEnabled() == false` không thể vượt qua xác thực bằng mật khẩu đúng.
5. `result.authenticated=true` vì manager/provider thực sự kiểm tra, không phải do code tự gán cờ.
6. Principal kết quả là `UserDetails`, vai trò `READER` xuất hiện dưới dạng authority `ROLE_READER`. Tên hiển thị của role và chuỗi authority không phải cùng một thứ.
7. `result.credentialsErased=true` là kết quả của cấu hình mặc định `ProviderManager.eraseCredentialsAfterAuthentication` trên token thành công; **không lấy password từ result để sử dụng tiếp**.
8. `context.name=lan` được in sau khi demo tự gắn kết quả vào context; `finally` dọn ngữ cảnh. Với ứng dụng web, phần filter/cơ chế phiên quản lý các việc đó.

Mật khẩu và hash trong ví dụ là dữ liệu giả lập để học; không hard-code credential production. Hash BCrypt có salt ngẫu nhiên, vì vậy ví dụ cố ý **không in literal hash**. Không in `getCredentials()` hoặc toàn bộ object `Authentication` trong log vì request có thể mang secret.

## 5. Bên trong `UserDetailsService`: “DAO” nằm ở đâu?

`DaoAuthenticationProvider` chỉ cần hợp đồng `UserDetailsService`:

```java
UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
```

Triển khai có thể đọc từ nhiều nguồn. Hai ví dụ:

### A. In-memory cho demo và test

```java
UserDetails user = User.withUsername("lan")
    .password(encodedPassword)
    .authorities("document:read", "ROLE_READER")
    .build();

UserDetailsService users = new InMemoryUserDetailsManager(user);
```

`encodedPassword` trong đoạn minh họa phải là chuỗi hash tương thích với encoder (ví dụ `encoder.encode(...)` khi tạo user). Đoạn này chỉ minh họa cách xây user store, không phải chương trình độc lập.

### B. Repository thật (mã phác thảo adapter)

Giả sử module có `AccountRepository` và entity `Account` chứa `username`, `passwordHash`, `enabled`, `roles`. Adapter có thể được viết như sau:

```java
// Mã minh họa trong ứng dụng có AccountRepository và Account đã định nghĩa.
// Cần import Spring @Service, UserDetailsService, User,
// UsernameNotFoundException và các kiểu entity/repository.
@Service
class AccountDetailsService implements UserDetailsService {

    private final AccountRepository accounts;

    AccountDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        Account account = accounts.findByUsername(username)
                .orElseThrow(() -> new UsernameNotFoundException(
                        "Account not found"));

        String[] authorities = account.roles().stream()
                .map(role -> "ROLE_" + role)
                .toArray(String[]::new);

        return User.withUsername(account.username())
                .password(account.passwordHash())
                .disabled(!account.enabled())
                .authorities(authorities)
                .build();
    }
}
```

Bản mã này cố ý chưa bao gồm repository/entity, transaction và schema; nó là **adapter minh họa**, không phải ví dụ build độc lập. Ở ứng dụng thật, cần giữ nguyên các cờ khóa/hết hạn cùng chính sách của hệ thống, chuẩn hóa username hợp lý, map quyền đã kiểm duyệt và xử lý null/duplicate.

**Điểm then chốt:** `UserDetailsService` không trả “người dùng đã login”; nó trả dữ liệu để provider kiểm tra. Khi mật khẩu không khớp, `DaoAuthenticationProvider` sẽ thất bại dù repository trả tài khoản đúng tên.

### Tại sao không tự `SELECT password_hash` rồi so trong controller?

Nhúng kiểm tra mật khẩu vào controller khiến nhiều endpoint dễ thực hiện sai hoặc lệch chính sách: bỏ sót tài khoản bị khóa, kiểm tra hash sai, quên cập nhật security context, ghi log secret hay tin vào role do client gửi. Dùng Spring Security manager/provider để tập trung xác minh, còn controller nhận `Authentication` kết quả đã được framework thiết lập và làm nghiệp vụ.

## 6. PasswordEncoder, hash, DelegatingPasswordEncoder và nâng cấp mật khẩu

### So sánh đúng

Đầu vào người dùng là **raw password**; giá trị đã lưu là **encoded password**. Giao diện:

```java
String stored = encoder.encode(rawPassword); // Khi tạo/đổi mật khẩu
boolean valid = encoder.matches(rawPassword, stored); // Khi login
```

BCrypt, PBKDF2, scrypt và Argon2 là các hàm một chiều có chi phí tính toán điều chỉnh được. Chọn thuật toán, work factor và chính sách nâng cấp theo khả năng hệ thống; đừng dùng plaintext, `NoOpPasswordEncoder` cho production hoặc hash SHA-256 thuần không có cơ chế dành cho lưu mật khẩu.

**Lưu ý về `DelegatingPasswordEncoder`:** nó xác định thuật toán từ tiền tố `{id}` trong chuỗi lưu, ví dụ:

```text
{bcrypt}$2a$...
{pbkdf2@SpringSecurity_v5_8}...
```

Mã gọi thường gặp:

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();
```

`DelegatingPasswordEncoder` mặc định mã hóa bằng một thuật toán hiện hành do factory chọn và có thể đọc nhiều định dạng có id đã đăng ký. Nếu DB lưu BCrypt thuần `$2a$...` mà cấu hình đổi sang delegating mặc định **không có `{bcrypt}`**, việc `matches` có thể lỗi vì không xác định được id. Cần một chiến lược migration có kiểm soát, không sửa database hash bằng cách thêm tiền tố một cách tùy tiện nếu chưa xác minh định dạng.

### Nâng cấp hash

`PasswordEncoder.upgradeEncoding(encodedPassword)` cho biết chuỗi hash có nên nâng cấp theo cấu hình encoder hay không. `DaoAuthenticationProvider` có thể kết hợp `UserDetailsPasswordService` để cập nhật hash mới **sau khi kiểm tra mật khẩu thành công**. Phần update có trách nhiệm đảm bảo tính toàn vẹn dữ liệu, xử lý đồng thời và không làm mất trạng thái tài khoản.

Đừng mặc định chỉ khai báo `PasswordEncoder` là mọi bản ghi hash cũ tự được migrate. Để cập nhật lưu trữ, cần cấu hình dịch vụ update thích hợp và chuẩn bị hỗ trợ định dạng cũ trong giai đoạn chuyển đổi.

### Kiểm tra mật khẩu bị lộ

Từ Spring Security 6.3, `DaoAuthenticationProvider` hỗ trợ cấu hình `CompromisedPasswordChecker` (ví dụ tích hợp dịch vụ kiểm tra mật khẩu đã bị lộ). Đây là khả năng bổ sung theo nhu cầu, **không thay thế** `PasswordEncoder.matches`, MFA, rate limiting hay quản lý vòng đời tài khoản.

Đừng gửi plaintext password sang một dịch vụ bên ngoài tùy tiện. Phải đánh giá hợp đồng giao thức, quyền riêng tư, độ sẵn sàng và chính sách xử lý khi checker không hoạt động.

## 7. Xử lý lỗi xác thực: ngoại lệ mang ý nghĩa khác nhau

`AuthenticationManager.authenticate(...)` thường ném `AuthenticationException` nếu không chứng thực được request. Một số loại thường gặp:

| Ngoại lệ | Tình huống | Hướng xử lý |
| --- | --- | --- |
| `BadCredentialsException` | Sai mật khẩu; username không tồn tại khi cấu hình mặc định che chi tiết. | Trả lỗi đăng nhập chung, không lộ username nào tồn tại. |
| `DisabledException` | User bị vô hiệu hóa. | Giữ account-state policy; hướng dẫn hỗ trợ qua luồng phù hợp. |
| `LockedException` | User bị khóa. | Bảo vệ quy trình mở khóa; tránh tiết lộ thông tin nhạy cảm. |
| `AccountExpiredException` | Account hết hạn. | Làm rõ chính sách vòng đời tài khoản. |
| `CredentialsExpiredException` | Mật khẩu hết hạn. | Chuyển sang luồng đổi mật khẩu an toàn. |
| `ProviderNotFoundException` | Manager không có provider hỗ trợ token. | Kiểm tra wiring provider/token; đây thường là lỗi cấu hình. |
| `AuthenticationServiceException` | Lỗi hệ thống/nguồn dữ liệu khi xác thực. | Ghi nhận và xử lý sự cố; đừng tự coi là password sai trong mọi trường hợp. |

**Mã HTTP không được quyết định chỉ từ tên exception một cách máy móc.** Form login thường chuyển hướng tới trang đăng nhập và xử lý failure; HTTP Basic thường trả `401` cùng `WWW-Authenticate`; kiểm tra quyền trên identity đã đăng nhập nhưng không đủ authority có thể tạo `403`. Điều này phụ thuộc `AuthenticationEntryPoint`, failure handler, `AccessDeniedHandler` và cơ chế web đã cấu hình.

Mặc định `hideUserNotFoundExceptions=true` hỗ trợ chống enumeration theo loại exception; đây **không phải lá chắn đầy đủ chống timing attack**, brute force hoặc rò rỉ qua response khác nhau. Dùng phiên bản Spring Security đã được sửa lỗi bảo mật, giới hạn tốc độ thử đăng nhập, quan sát hành vi bất thường và tránh báo chi tiết user tồn tại/không tồn tại cho khách.

## 8. Cách dùng với Spring Boot Servlet

**Spring Boot tạo context và tích hợp Spring Security vào web app; `DaoAuthenticationProvider` vẫn là cơ chế xác thực username/password của Spring Security.** Có thể cung cấp `UserDetailsService` và `PasswordEncoder` để framework sử dụng; hoặc khai báo bean `DaoAuthenticationProvider` rõ ràng khi cần kiểm soát provider.

Một cấu hình minh họa trong ứng dụng đã có `spring-boot-starter-web` và `spring-boot-starter-security`:

```java
// Mã cấu hình minh họa; đặt trong @Configuration của dự án Boot.
// Cần import: @Bean, @Configuration, HttpSecurity, SecurityFilterChain,
// Customizer, User, UserDetailsService, InMemoryUserDetailsManager,
// DaoAuthenticationProvider, PasswordEncoder, BCryptPasswordEncoder.
@Configuration
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("lan")
                .password(encoder.encode("DemoPass123!"))
                .roles("READER")
                .build()
        );
    }

    @Bean
    DaoAuthenticationProvider daoAuthenticationProvider(
            UserDetailsService users, PasswordEncoder encoder) {

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return provider;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, DaoAuthenticationProvider provider)
            throws Exception {

        http
            .authenticationProvider(provider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/documents").hasRole("READER")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Đây là **cấu hình minh họa, không phải dự án Boot đầy đủ**: cần có class khởi động `@SpringBootApplication`, controller endpoints, dependencies và imports đúng. Cách tạo `DaoAuthenticationProvider(UserDetailsService)` ở đây tương thích Spring Security **6.5.11**; với dự án Boot 3.3 sử dụng dòng Security 6.3, hãy kiểm tra API/phiên bản thực tế trước khi sao chép constructor vì các overload đã thay đổi qua các đời.

Khi chạy thực tế với HTTP Basic:

- `/public` được `permitAll()` nên không cần đăng nhập.
- `/documents` yêu cầu `ROLE_READER`; nếu dùng HTTP Basic và gửi `lan:DemoPass123!` hợp lệ thì provider tạo authenticated token.
- Nếu thiếu credentials, ứng dụng có thể yêu cầu đăng nhập bằng `401` và `WWW-Authenticate`; nếu đã xác thực nhưng thiếu role, thường là `403`.
- Dùng **HTTPS** trong triển khai thực tế. HTTP Basic mã hóa Base64 nhưng **không mã hóa bí mật**, và chỉ nên dùng với kết nối bảo vệ phù hợp.
- Không mở rộng `permitAll()` để né lỗi cấu hình 401/403; cần xác định request có qua filter/provider hay không, user có bị khóa không và authorities được map đúng chưa.

Ở Spring Boot, tạo bean `SecurityFilterChain` có thể khiến cấu hình web mặc định của Boot nhường chỗ; còn việc tạo/chọn `UserDetailsService` là quyết định riêng. **Không mặc định user trong database tự được xác thực chỉ vì Boot có JPA và entity User.**

### Tách “đăng nhập” và “phân quyền”

`DaoAuthenticationProvider` trả danh tính và authorities được xác thực. Quy tắc `hasRole("READER")` có thể so chuỗi authority `ROLE_READER` theo convention mặc định, còn `hasAuthority("document:read")` so chính xác. Cả hai đều cần map dữ liệu quyền đúng tại nguồn.

Đối với quyền trên dữ liệu cụ thể, ví dụ “chỉ xem tài liệu do chính mình sở hữu”, thêm kiểm tra owner/resource ở tầng nghiệp vụ hoặc method security. Một user có `ROLE_READER` không mặc nhiên đọc được mọi tài liệu của mọi tài khoản.

## 9. Caching, SecurityContext và những hệ quả khi triển khai thật

### `UserCache` không phải session

`AbstractUserDetailsAuthenticationProvider` hỗ trợ `UserCache`, nhưng mặc định thường là `NullUserCache`. Trong web app sử dụng session, sau đăng nhập thành công, request tiếp theo có thể đọc context từ session mà không gọi `UserDetailsService` và BCrypt cho mỗi request.

Nếu bật `UserCache` cho provider, phải giải quyết cache invalidation khi user đổi password, bị khóa hoặc thay quyền. Một bộ cache giữ object `UserDetails` có hash đã bị xóa do `CredentialsContainer.eraseCredentials()` có thể gây lỗi xác thực sau đó. Hãy cân nhắc sao chép đối tượng vào cache, hoặc thiết kế cơ chế xóa credentials/caching phù hợp với mô hình threat; không tắt xóa credentials chỉ để cho cache “chạy được” mà không hiểu hệ quả.

### Quyền và trạng thái thay đổi sau đăng nhập

Sau khi manager trả token, `Authentication` có thể chứa authorities tại thời điểm xác thực. Khi tài khoản bị vô hiệu hóa hoặc role bị rút trong database, phiên cũ/JWT hoặc context cũ **không tự động** phản ánh thay đổi nếu không có cơ chế cập nhật/thu hồi/tái xác thực.

Thiết kế thời hạn session, refresh, quyền động và cơ chế thu hồi cho phù hợp mức độ rủi ro. Đừng giả định mọi request đều hỏi lại `UserDetailsService`.

### Thread và context

Trong ứng dụng Servlet, `SecurityContextHolder` mặc định sử dụng ngữ cảnh gắn với thread xử lý. Spring Security filter chain quản lý thiết lập/dọn dẹp ngữ cảnh theo request. Với async/task executor, truyền principal/context đúng cách bằng cơ chế tích hợp phù hợp; đừng đưa `Authentication` vào biến static toàn cục hoặc cache đa người dùng.

## 10. Sai lầm phổ biến

1. **“DAO provider tự truy vấn bảng `users`.”** Không. Nó phụ thuộc `UserDetailsService`; ứng dụng phải tự chọn nguồn và adapter.
2. **“Tìm thấy username nghĩa là login thành công.”** Sai. Provider còn kiểm tra hash mật khẩu và trạng thái tài khoản.
3. **“Có thể so hai kết quả `encoder.encode(...)`.”** Sai với BCrypt có salt; dùng `matches(raw, encoded)`.
4. **“`PasswordEncoder` mặc định luôn hiểu mọi hash.”** Sai. Phải tương thích định dạng dữ liệu; delegating thường đòi `{id}`.
5. **“Đặt `isAuthenticated=true` là đủ.”** Sai. Chỉ tin result trả về từ manager/provider đã xác minh; không tự dựng token tin cậy từ request body.
6. **“Mọi lần truy cập tài nguyên đều gọi lại `DaoAuthenticationProvider`.”** Sai với cơ chế session/caching tương ứng; nhiều request dùng context đã phục hồi.
7. **“`DaoAuthenticationProvider` tự ghi session/cookie.”** Sai. Provider trả kết quả; filter, context repository, success/failure handler quản lý phần request web.
8. **“`UserDetailsService` tự check mật khẩu.”** Không theo hợp đồng chuẩn. Đây là nguồn thông tin, còn provider/encoder xác minh credentials.
9. **“Username không tồn tại luôn báo `UsernameNotFoundException` ra client.”** Mặc định provider thường che thành `BadCredentialsException`; đừng cố phơi bày sự tồn tại của tài khoản.
10. **“Role từ client được dùng trực tiếp.”** Không. Authorities phải lấy/ánh xạ từ nguồn đã kiểm chứng; `ROLE_READER` khác chuỗi `READER` tùy policy.
11. **“Xóa raw password trên success đồng nghĩa đã sạch mọi log.”** Không. Vẫn có thể rò ở request access log, error log, tracing, URL query, debug dump. Không ghi bí mật vào log.
12. **“Bật account lock là đủ chống brute force.”** Cần rate limiting, giám sát, recovery và chính sách không cho phép attacker vô hiệu hóa hàng loạt user.
13. **“Dùng `NoOpPasswordEncoder` để nhanh chóng chạy production.”** Sai. Chỉ dùng encoder lưu hash phù hợp; demo phải phân biệt rõ môi trường học và triển khai thật.
14. **“DAO provider thay thế mọi provider khác.”** Không. Nó xử lý username/password; JWT/OIDC/pre-authentication có contract riêng.
15. **“Đăng nhập thành công nghĩa là được phép mọi API.”** Không. Authorization phải kiểm tra role, permission và quyền trên đối tượng nghiệp vụ.
16. **“Cứ bắt mọi `AuthenticationException` rồi trả true.”** Nguy hiểm: làm mất ranh giới tin cậy. Chỉ chuyển lỗi thành phản hồi an toàn, không tạo kết quả thành công giả.

## 11. Tự kiểm tra hiểu bài

**Câu 1.** `UserDetailsService.loadUserByUsername("lan")` đã trả tài khoản có hash và role. `lan` đã được đăng nhập chưa?

**Trả lời:** Chưa. `DaoAuthenticationProvider` còn phải xác minh credentials và trạng thái; chỉ kết quả thành công từ manager/provider mới đại diện một lần xác thực hợp lệ.

**Câu 2.** Khi gọi `encoder.encode("x")` hai lần, hash có thể khác nhau. Có phải encoder bị lỗi không?

**Trả lời:** Không. BCrypt có salt ngẫu nhiên; phải dùng `matches("x", storedHash)`.

**Câu 3.** Request gửi tên user không tồn tại. Mặc định trả `UsernameNotFoundException` ra client khác với password sai?

**Trả lời:** Provider thường che username không tồn tại dưới `BadCredentialsException`. Lớp web còn quyết định cách biểu diễn lỗi HTTP; không nên làm lộ danh sách tài khoản hợp lệ.

**Câu 4.** Có thể dùng `DaoAuthenticationProvider` để xác thực bearer JWT chỉ bằng cách thêm `UserDetailsService` không?

**Trả lời:** Không. `DaoAuthenticationProvider` xử lý token username/password. Resource server JWT cần cơ chế giải mã/kiểm chứng bearer token và provider/converter tương ứng.

**Câu 5.** Đã gọi `manager.authenticate(request)` và có `result`. `SecurityContextHolder` có tự được cập nhật không?

**Trả lời:** Không đảm bảo khi gọi thủ công; web filter chuẩn thường quản lý context/phiên, còn code riêng phải hiểu hợp đồng này.

**Câu 6.** `UserDetails` có `isEnabled()==false` nhưng mật khẩu đúng. Có được authenticated token không?

**Trả lời:** Không. Account-state check từ chối tài khoản disabled, thường bằng `DisabledException`.

**Câu 7.** Tại sao `result.getCredentials()` có thể là `null` dù xác thực thành công?

**Trả lời:** `ProviderManager` mặc định cố xóa dữ liệu credentials khỏi kết quả để giảm rủi ro lưu giữ secret. Không phụ thuộc vào mật khẩu sau login.

**Câu 8.** `ROLE_READER` có nghĩa user được xem tài liệu của mọi người?

**Trả lời:** Không. Role chỉ là một authority cấp cao. Kiểm tra quyền sở hữu dữ liệu/permission chi tiết là một bước authorization riêng.

## 12. Tài liệu chính thức và điểm cần đọc tiếp

- [Spring Security 6.5.11 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): sơ đồ filter → manager → provider → `UserDetailsService`/`PasswordEncoder`.
- [DaoAuthenticationProvider API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html): constructor, `setPasswordEncoder`, `setUserDetailsPasswordService`, `setCompromisedPasswordChecker`.
- [AbstractUserDetailsAuthenticationProvider API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html): state checks, `UserCache`, exception hiding, result token.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `ProviderManager`, `SecurityContext` và credentials erasure.
- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): BCrypt, DelegatingPasswordEncoder, work factor, định dạng `{id}`.
- [Spring Security — CVE-2026-22746](https://spring.io/security/cve-2026-22746/): thông báo lỗi liên quan kiểm tra trạng thái tài khoản và timing; ví dụ trên dùng 6.5.11 thuộc dòng đã sửa lỗi này.

**Điểm cần nhớ:** `DaoAuthenticationProvider` là bộ phận **xác minh username/password** dựa trên `UserDetailsService` và `PasswordEncoder`, có kiểm tra trạng thái tài khoản và trả một `Authentication` đáng tin cậy nếu thành công. Nguồn tài khoản, phần HTTP filter/phiên và chính sách authorization là các trách nhiệm riêng. Khi giữ rõ ranh giới đó, việc thay bộ nhớ bằng cơ sở dữ liệu không buộc phải tự viết lại logic xác thực mật khẩu trong controller.