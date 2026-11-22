# Định nghĩa UserDetails riêng hay dùng lớp User có sẵn?

> **Phạm vi:** Spring Security Authentication trên Java 17+, trọng tâm là hợp đồng `UserDetails`, lớp `org.springframework.security.core.userdetails.User` có sẵn và quyết định khi nào cần một implementation riêng. Ví dụ đầy đủ dùng Spring Security 6.5.x để đối chiếu hành vi; các đoạn tích hợp Spring Boot/DB được ghi rõ là minh họa cần repository và cấu hình ứng dụng. Bài học giải thích cả bảo mật, trạng thái tài khoản, cache và cách sử dụng principal sau đăng nhập.

## 1. Trả lời trực tiếp: chọn User hay custom UserDetails?

Trong đa số ứng dụng chỉ cần **username, password hash, authorities và trạng thái tài khoản**, hãy bắt đầu với lớp `org.springframework.security.core.userdetails.User` của Spring Security. Nó đã thực hiện `UserDetails`, có builder để dựng đủ các thuộc tính bảo mật và tránh phải tự viết những getter đơn giản.

Chỉ định nghĩa **`UserDetails` riêng** khi principal sau đăng nhập thực sự cần dữ liệu có ý nghĩa ổn định cho ứng dụng, ví dụ **internal user ID**, tenant ID, mã tổ chức hoặc một số thuộc tính danh tính được phép đặt trong security context, và không muốn mỗi request phải tra cứu thêm thông tin đó. Khi đó, class riêng phải thực hiện chính xác hợp đồng của Spring Security, kiểm soát dữ liệu nhạy cảm, trạng thái tài khoản, serialization và vòng đời credentials.

**Quan trọng:** dùng lớp `User` **không có nghĩa** bắt buộc lưu user trong bộ nhớ. `User` là **kiểu dữ liệu**, còn `UserDetailsService` là **cách lấy tài khoản** từ DB, LDAP hoặc nguồn khác. Một `UserDetailsService` đọc từ database hoàn toàn có thể trả về đối tượng `User` mặc định.

### Bảng lựa chọn

| Tình huống | Ưu tiên | Vì sao |
| --- | --- | --- |
| Demo đăng nhập username/password | `User.withUsername(...)` và `InMemoryUserDetailsManager` | Ít code, tập trung vào cơ chế xác thực |
| Hệ thống thật dùng DB nhưng chỉ cần username/role/status | `User.withUsername(...)` trong custom `UserDetailsService` | Không cần thêm loại principal; vẫn dùng repository |
| Web app cần user ID ổn định trong nhiều service/controller | Custom `UserDetails` chứa ID (và thông tin tối thiểu) | Tránh phụ thuộc username có thể đổi; ánh xạ rõ về domain |
| Multi-tenant có ID người dùng trùng username ở nhiều tenant | Custom principal kết hợp tenant/subject, kèm cơ chế định danh an toàn | Tên đăng nhập một mình có thể không đủ phân biệt |
| Chỉ cần thêm một trường hiển thị trên một trang | Thường giữ `User`, lấy hồ sơ qua service | Tránh đưa dữ liệu thay đổi liên tục vào security context |
| JWT Resource Server hoặc OIDC Login | Xem loại principal được cơ chế tương ứng tạo (`Jwt`, `OidcUser`...) | Không mặc định ép mọi principal thành `UserDetails` |
| Cần thay cách xác thực credential không dùng password | Tìm hiểu provider/protocol phù hợp | Custom `UserDetails` **không tự thay** cách kiểm tra credential |

Không có quy tắc “project lớn thì bắt buộc custom `UserDetails`”. Quyết định dựa trên **hợp đồng danh tính mà ứng dụng cần** và khả năng duy trì dữ liệu đó đúng, an toàn.

## 2. UserDetails đứng ở đâu trong luồng xác thực?

```text
POST /login hoặc HTTP Basic username/password
    ↓
Authentication Filter tạo UsernamePasswordAuthenticationToken chưa xác thực
    ↓
AuthenticationManager (thường ProviderManager)
    ↓
DaoAuthenticationProvider
    ├─ UserDetailsService.loadUserByUsername(username)
    │      ↓
    │   UserDetails từ DB / bộ nhớ / nguồn khác
    │      ├─ getUsername()
    │      ├─ getPassword()  → password hash
    │      ├─ getAuthorities()
    │      ├─ isEnabled()
    │      ├─ isAccountNonLocked()
    │      ├─ isAccountNonExpired()
    │      └─ isCredentialsNonExpired()
    └─ PasswordEncoder.matches(rawPassword, storedHash)
    ↓
Authentication đã xác thực (principal thường là UserDetails)
    ↓
SecurityContext (do luồng security tích hợp quản lý)
    ↓
Controller / service đọc Authentication hoặc principal phù hợp
```

`UserDetailsService` có **một nhiệm vụ cốt lõi**: tải thông tin người dùng theo username. Nó không phải thành phần tự quyết định mật khẩu đúng/sai trong flow chuẩn. `DaoAuthenticationProvider` dùng `UserDetails` và `PasswordEncoder` để kiểm tra credential, xử lý trạng thái account rồi tạo kết quả xác thực.

Do đó có thể đổi nguồn dữ liệu hoặc đổi implementation của `UserDetails` mà **không cần tự viết lại authentication filter hay provider**.

**Đừng nhầm ba tên giống nhau:**

- `UserDetails`: interface chứa dữ liệu cần thiết cho authentication.
- `User` trong package `org.springframework.security.core.userdetails`: implementation có sẵn của `UserDetails`.
- `UserDetailsService`: interface tìm `UserDetails` theo username.

`InMemoryUserDetailsManager` là implementation `UserDetailsManager`/`UserDetailsService` để lưu user trong bộ nhớ; nó khác với class `User`. Một JPA entity tên `User` cũng khác hoàn toàn `org.springframework.security.core.userdetails.User`.

## 3. Hợp đồng UserDetails: dữ liệu nào bắt buộc đúng?

`UserDetails` extends `Serializable`. Trong Spring Security 6.5, các method chính có ý nghĩa:

| Phương thức | Hợp đồng | Sai lầm phổ biến |
| --- | --- | --- |
| `getUsername()` | Tên tài khoản dùng cho xác thực; không trả `null` | Trả tên hiển thị/email chưa xác minh mà hệ thống không quản lý tính duy nhất |
| `getPassword()` | Giá trị password hash đã lưu để provider kiểm tra | Trả raw password; encode lại hash mỗi lần đọc DB |
| `getAuthorities()` | Tập `GrantedAuthority` đáng tin, không `null` | Lấy trực tiếp role do client gửi mà không kiểm tra |
| `isEnabled()` | `true` nếu tài khoản được phép xác thực | Đảo nghĩa giữa enabled và disabled |
| `isAccountNonLocked()` | `true` khi **không bị khóa** | Trả thẳng `account.isLocked()` |
| `isAccountNonExpired()` | `true` khi tài khoản **chưa hết hạn** | Dùng cờ `expired` mà không phủ định |
| `isCredentialsNonExpired()` | `true` nếu credential **chưa hết hạn** | Bỏ qua quy định đổi mật khẩu bắt buộc |

Tên của ba phương thức bắt đầu bằng `is...Non...` rất quan trọng: **`true` là trạng thái hợp lệ**. Trong 6.5, các phương thức kiểm tra trạng thái có implementation mặc định trả `true`; nếu custom class cần phản ánh DB, phải **override chúng có chủ đích**. Không viết thiếu rồi vô tình làm cho tài khoản bị khóa/hết hạn vẫn có vẻ hợp lệ.

Ví dụ một dòng ánh xạ trạng thái DB, trong method đã có biến `account`:

```java
boolean enabled = account.isEnabled();
boolean accountNonLocked = !account.isLocked();
boolean accountNonExpired = !account.isExpired();
boolean credentialsNonExpired = !account.isPasswordExpired();
```

Đoạn trên là **minh họa ánh xạ trạng thái**, giả định entity đã định nghĩa các method tương ứng. Không phải chương trình độc lập.

Các nguyên tắc giữ hợp đồng:

1. `getUsername()` ổn định và không null theo namespace mà `UserDetailsService` dùng.
2. `getAuthorities()` luôn trả collection hợp lệ, từng authority phải có nguồn đáng tin. Có thể rỗng nếu chính sách xác thực cho phép.
3. `getPassword()` trong username/password flow phải là **hash phù hợp với PasswordEncoder**, không phải mật khẩu gốc. Sau xác thực, password có thể bị xóa khỏi object principal.
4. Không đặt nghiệp vụ truy vấn DB, gọi API ngoài hoặc đọc request trực tiếp trong các getter; tạo một snapshot danh tính đủ dùng tại thời điểm tải user.
5. Khi đưa principal vào session/cache, xét khả năng serialization và tính lỗi thời của roles/status theo thời gian.

### `UserDetails` không phải entity nghiệp vụ

Entity ứng dụng có thể có `id`, `email`, `phone`, `address`, `lastLoginAt`, `passwordHash`, trạng thái và quan hệ JPA. Principal phục vụ authentication thường **chỉ cần** ID, username, hash tạm thời, authorities và trạng thái. Đưa toàn bộ entity JPA vào security context dễ gây lazy-loading exception, serialization lỗi, lưu quá nhiều dữ liệu cá nhân và các hiệu ứng phụ do entity mutable.

Một sơ đồ ánh xạ an toàn:

```text
AccountEntity (DB, domain)
       │ repository truy vấn
       ▼
UserDetailsService
       ├── cách A: User.withUsername(...).build()
       └── cách B: new AppUserDetails(id, username, hash, authorities, flags)
       ▼
DaoAuthenticationProvider xác thực
       ▼
Authentication / SecurityContext
       ▼
App service dùng internal ID (nếu custom) hoặc tra ID từ service
```

## 4. Dùng lớp User có sẵn: trường hợp phổ biến và cách tạo

Lớp `User` tiêu chuẩn thuộc package:

```java
org.springframework.security.core.userdetails.User
```

Đây **không phải** domain user entity. Class này chứa username, password, authorities và các cờ trạng thái, và implement `UserDetails` cùng `CredentialsContainer` để hỗ trợ xóa credential khi không còn cần.

Ví dụ tạo user với password hash đã có:

```java
UserDetails principal = User.withUsername("mai")
        .password(passwordHash)
        .roles("READER")
        .disabled(false)
        .accountLocked(false)
        .accountExpired(false)
        .credentialsExpired(false)
        .build();
```

Đây là **snippet trong một method**, giả định `passwordHash` đã được tạo một lần bằng `PasswordEncoder` khi đăng ký/đổi mật khẩu. Không chạy độc lập nếu thiếu imports và biến đó.

Về builder:

- `roles("READER")` thường tạo authority `ROLE_READER`. Không truyền `"ROLE_READER"` vào `roles(...)` vì builder tự thêm prefix theo quy ước.
- Nếu source trả quyền dạng chuỗi chính xác như `"accounts:read"` hoặc `"ROLE_AUDITOR"`, dùng `authorities(...)`, không coi mọi authority đều là role.
- `disabled(boolean)`, `accountLocked(boolean)`, `accountExpired(boolean)`, `credentialsExpired(boolean)` nhận ý nghĩa **phủ định** so với các method `isEnabled`, `isAccountNonLocked`, ... Cần ánh xạ đúng.
- Các default trong builder thường tương ứng trạng thái account hợp lệ; với dữ liệu thật phải điền đúng flag theo DB.
- `User.withUserDetails(other)` hữu ích để copy các thuộc tính `UserDetails` chuẩn, nhưng **không giữ trường riêng** như internal ID hoặc tenant ID của custom principal.

**Ưu điểm:** ít code, provider tiêu chuẩn tương thích, các method và credential erasure đã được thư viện triển khai. **Giới hạn:** không có thuộc tính nghiệp vụ riêng. `Authentication.getPrincipal()` thường là `User`; muốn internal ID bạn phải tra cứu hoặc dùng một principal riêng.

### Dùng User với database, không cần InMemoryUserDetailsManager

Ví dụ `UserDetailsService` bên dưới là **mẫu tích hợp cần có `AccountRepository` và `AccountEntity` của ứng dụng**, không phải class chạy độc lập:

```java
@Service
public class AccountUserDetailsService implements UserDetailsService {
    private final AccountRepository repository;

    public AccountUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        AccountEntity account = repository.findByUsername(username)
                .orElseThrow(() -> new UsernameNotFoundException("User not found"));

        return User.withUsername(account.getUsername())
                .password(account.getPasswordHash())
                .authorities(account.getAuthorities())
                .disabled(!account.isEnabled())
                .accountLocked(account.isLocked())
                .accountExpired(account.isExpired())
                .credentialsExpired(account.isPasswordExpired())
                .build();
    }
}
```

Ví dụ giả định `account.getAuthorities()` trả collection/array mà `User.UserBuilder.authorities(...)` chấp nhận, và các method trạng thái có sẵn trong entity. Trong code thật phải đổi phần ánh xạ cho đúng kiểu dữ liệu role và API repository. Giá trị password đưa vào builder là **hash lấy từ DB**, không gọi `encoder.encode(account.getPasswordHash())`.

Nếu DB lưu `ROLE_READER`, ánh xạ bằng `new SimpleGrantedAuthority("ROLE_READER")`; nếu DB lưu tên role `READER` và dùng `roles("READER")`, builder sẽ thêm prefix. Chỉ dùng một quy ước để tránh `ROLE_ROLE_READER` hoặc role sai.

**Điều kiện để chọn cách này:** các API nghiệp vụ không cần ép principal thành entity; controller/service có thể dùng `authentication.getName()` và một repository/service riêng để lấy ID khi cần. Với hệ thống ít trang cần ID, thêm lookup có thể dễ duy trì hơn custom principal.

## 5. Khi nào nên tự định nghĩa UserDetails?

Hãy chọn custom `UserDetails` khi câu trả lời cho các câu sau có trọng lượng:

1. Có cần **internal immutable user ID** trong nhiều request để truy cập resource chính xác, trong khi username có thể đổi?
2. Có cần **tenant/organization ID** hoặc identity realm đã được kiểm chứng trong security context để kiểm tra cách ly dữ liệu?
3. Có cần các metadata danh tính nhỏ và **ổn định theo phiên** như account type phục vụ logic bảo mật, trong khi lớp `User` không cung cấp?
4. Có cần chuẩn hóa một principal riêng để nhiều controller/service không phải liên tục chuyển đổi username sang domain ID?
5. Có yêu cầu serialization/cache rõ ràng và đủ khả năng thiết kế credential erasure không ảnh hưởng user store?

Nếu chỉ muốn “thêm trường email cho trang hồ sơ”, custom principal có thể không phải giải pháp tốt nhất vì email có thể thay đổi, nhạy cảm, chưa xác minh hoặc không cần có trong session. Phần lớn thông tin hiển thị nên được lấy từ profile service và trả về qua DTO.

**Custom `UserDetails` không giải quyết tự động:** tạo token JWT, xác minh OIDC/SAML, xác thực MFA, quyền theo từng object, đăng xuất mọi session hoặc chặn account đã bị vô hiệu hóa trong một session cũ. Chúng thuộc các cơ chế khác cần thiết kế riêng.

### Thiết kế class riêng: giữ tối thiểu

Ví dụ thông tin đưa vào custom principal:

| Thuộc tính | Nên đặt trong principal? | Lưu ý |
| --- | --- | --- |
| Internal numeric/UUID user ID | Thường có | ID bền vững, không phụ thuộc username |
| Username xác thực | Có | `getUsername()` theo hợp đồng |
| Password hash | Cần cho password provider lúc xác thực | Không đưa vào response/log; xem credential erasure |
| Authorities | Có | Snapshot quyền được cấp từ nguồn tin cậy |
| Enabled/locked/expired flags | Có | Cần cho `DaoAuthenticationProvider` kiểm tra |
| Tenant ID hoặc issuer+subject | Có khi dùng để xác định ranh giới | Giá trị phải được xác minh và ánh xạ đúng |
| Email, số điện thoại, avatar | Thường không | Dữ liệu hiển thị thay đổi và có thể nhạy cảm |
| Toàn bộ JPA entity cùng quan hệ | Tránh | Lazy loading, dữ liệu lớn, serialization, mutable state |
| Raw password, access token, refresh token | Không | Dữ liệu bí mật không cần giữ trong principal lâu dài |

### Implement trực tiếp hay kế thừa User?

- **Implement `UserDetails` trực tiếp:** kiểm soát rõ trường, constructor, getters, equality, serialization và cách xóa credential; có thêm code cần kiểm thử.
- **Extend `User`:** có thể tái sử dụng hành vi có sẵn và thêm `userId`; tuy nhiên cần hiểu `equals/hashCode` của lớp `User` dựa vào username và các chi tiết erasure của superclass. Nếu domain identity khác username hoặc có nhiều tenant, kế thừa có thể tạo giả định không mong muốn.
- **Bọc `UserDetails` làm delegate:** tránh lặp lại getter trạng thái nhưng phải chuyển tiếp đầy đủ đúng hợp đồng và xử lý `CredentialsContainer`/serialization. Hữu ích khi muốn giữ hành vi chuẩn mà bổ sung ID.

Với custom principal không quá phức tạp, **implement interface trực tiếp và giữ các giá trị bất biến** (ngoại trừ credential cần xóa) thường dễ đọc, dễ kiểm thử. Không mở rộng class chỉ vì muốn giảm vài getter.

## 6. Java 17+ runnable: cùng một password, hai loại principal

Ví dụ này tạo hai `UserDetailsService`: một trả `User` có sẵn, một trả `AccountDetails` custom chứa internal ID. Cả hai dùng `DaoAuthenticationProvider` và `ProviderManager` giống nhau. Sau xác thực, chương trình **chỉ in metadata vô hại**, không in password hoặc hash.

Cấu trúc project:

```text
userdetails-choice-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/UserDetailsChoiceDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'userdetails-choice-demo'
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
    mainClass = 'demo.UserDetailsChoiceDemo'
}
```

Tạo `src/main/java/demo/UserDetailsChoiceDemo.java`:

```java
package demo;

import java.util.List;
import java.util.Collection;
import java.util.stream.Collectors;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.CredentialsContainer;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public class UserDetailsChoiceDemo {
    private static final PasswordEncoder ENCODER = new BCryptPasswordEncoder();

    public static void main(String[] args) {
        // Chỉ là mật khẩu test; không hardcode credential trong ứng dụng thật.
        String hash = ENCODER.encode("demo-pass");

        UserDetails builtIn = User.withUsername("mai")
                .password(hash)
                .roles("READER")
                .build();

        UserDetailsService standardSource =
                new InMemoryUserDetailsManager(builtIn);

        UserDetailsService customSource = customSource(hash, true);

        show("built-in", login(standardSource, "demo-pass"));
        show("custom", login(customSource, "demo-pass"));

        try {
            login(customSource, "wrong");
        } catch (BadCredentialsException ex) {
            System.out.println("wrong-password: BadCredentialsException");
        }

        try {
            login(customSource(hash, false), "demo-pass");
        } catch (DisabledException ex) {
            System.out.println("disabled: DisabledException");
        }
    }

    private static UserDetailsService customSource(
            String hash, boolean enabled) {
        return username -> {
            if (!"mai".equals(username)) {
                throw new UsernameNotFoundException("User not found");
            }
            return new AccountDetails(
                    42L,
                    username,
                    hash,
                    List.of(new SimpleGrantedAuthority("ROLE_READER")),
                    enabled,
                    true,  // accountNonExpired
                    true,  // accountNonLocked
                    true   // credentialsNonExpired
            );
        };
    }

    private static Authentication login(
            UserDetailsService users, String rawPassword) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(ENCODER);

        AuthenticationManager manager = new ProviderManager(provider);

        return manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "mai", rawPassword));
    }

    private static void show(String label, Authentication auth) {
        UserDetails principal = (UserDetails) auth.getPrincipal();
        String id = principal instanceof AccountDetails account
                ? Long.toString(account.userId())
                : "-";

        String authorities = auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .collect(Collectors.joining(","));

        String hashState = principal.getPassword() == null
                ? "erased"
                : "present";

        System.out.printf(
                "%s: principal=%s; name=%s; id=%s; authorities=%s; hash=%s%n",
                label,
                principal.getClass().getSimpleName(),
                auth.getName(),
                id,
                authorities,
                hashState);
    }

    // Security principal riêng; không phải entity JPA.
    private static final class AccountDetails
            implements UserDetails, CredentialsContainer {
        private static final long serialVersionUID = 1L;

        private final long userId;
        private final String username;
        private String passwordHash;
        private final List<GrantedAuthority> authorities;
        private final boolean enabled;
        private final boolean accountNonExpired;
        private final boolean accountNonLocked;
        private final boolean credentialsNonExpired;

        AccountDetails(
                long userId,
                String username,
                String passwordHash,
                Collection<? extends GrantedAuthority> authorities,
                boolean enabled,
                boolean accountNonExpired,
                boolean accountNonLocked,
                boolean credentialsNonExpired) {
            this.userId = userId;
            this.username = username;
            this.passwordHash = passwordHash;
            this.authorities = List.copyOf(authorities);
            this.enabled = enabled;
            this.accountNonExpired = accountNonExpired;
            this.accountNonLocked = accountNonLocked;
            this.credentialsNonExpired = credentialsNonExpired;
        }

        long userId() {
            return userId;
        }

        @Override
        public String getUsername() {
            return username;
        }

        @Override
        public String getPassword() {
            return passwordHash;
        }

        @Override
        public Collection<? extends GrantedAuthority> getAuthorities() {
            return authorities;
        }

        @Override
        public boolean isEnabled() {
            return enabled;
        }

        @Override
        public boolean isAccountNonExpired() {
            return accountNonExpired;
        }

        @Override
        public boolean isAccountNonLocked() {
            return accountNonLocked;
        }

        @Override
        public boolean isCredentialsNonExpired() {
            return credentialsNonExpired;
        }

        @Override
        public void eraseCredentials() {
            passwordHash = null;
        }
    }
}
```

Từ thư mục `userdetails-choice-demo` chạy bằng một Gradle tương thích Java 17:

```bash
gradle run
```

Nếu dự án đã tạo Gradle Wrapper, dùng `./gradlew run` (macOS/Linux) hoặc `gradlew.bat run` (Windows). Chương trình sẽ in bốn dòng chính sau (ngoài output của Gradle):

```text
built-in: principal=User; name=mai; id=-; authorities=ROLE_READER; hash=erased
custom: principal=AccountDetails; name=mai; id=42; authorities=ROLE_READER; hash=erased
wrong-password: BadCredentialsException
disabled: DisabledException
```

### Phân tích output

1. **Cùng name:** `Authentication.getName()` đều là `mai`; việc dùng custom principal không tự đổi username.
2. **Khác principal class:** khi `UserDetailsService` trả `User`, principal thường là `User`; với custom source, principal là `AccountDetails`. Cả hai vẫn thực hiện `UserDetails` và được `DaoAuthenticationProvider` xử lý theo cùng cơ chế.
3. **Internal ID:** chỉ `AccountDetails` có `userId=42`; lớp `User` chuẩn không có getter này. Đây là lý do thực tế để chọn custom class.
4. **Authorities:** cả hai trả `ROLE_READER` do nguồn user tin cậy cấp. Không thể suy ra role từ tên class principal.
5. **Hash erased:** `ProviderManager` mặc định xóa credential sau thành công với các đối tượng hỗ trợ `CredentialsContainer`. `User` có sẵn triển khai việc xóa; custom `AccountDetails` cũng hỗ trợ nên `getPassword()` trong principal kết quả trả `null`.
6. **Password sai:** `DaoAuthenticationProvider` gọi `PasswordEncoder.matches(...)` và từ chối credential không hợp lệ. Không có đường “custom principal” nào tự bỏ qua kiểm tra password.
7. **Disabled:** `isEnabled() == false` khiến quá trình xác thực bị từ chối bằng `DisabledException`, dù mật khẩu đúng. Các cờ trạng thái được kiểm tra ở provider tiêu chuẩn, không cần tự chặn bằng controller.

**Điểm kỹ thuật của ví dụ:** phương thức `login(...)` chỉ trả về kết quả từ manager, không tự thêm kết quả vào `SecurityContext`. Trong ứng dụng web thật, authentication filter và security infrastructure làm phần này theo flow cấu hình. Code demo cũng cố ý tạo một `AccountDetails` mới mỗi lần tải từ source, giúp tránh mutation lên một object bị cache và dùng lại.

### Vì sao custom class hỗ trợ CredentialsContainer?

`UserDetails` là dữ liệu được provider dùng để xác minh credential. Khi một custom principal chứa `passwordHash`, việc hỗ trợ `CredentialsContainer` cho phép `ProviderManager` xóa reference đến hash khỏi kết quả khi xác thực xong:

```java
@Override
public void eraseCredentials() {
    passwordHash = null;
}
```

Không lưu raw password. Không nhầm password hash với raw password; hash vẫn là dữ liệu phải bảo vệ và không nên xuất ra client. `ProviderManager` không tự biết phải xóa một field tùy ý trong class custom nếu class không triển khai cơ chế tương ứng.

**Cẩn trọng với cache:** nếu nhiều request dùng **cùng một instance `UserDetails`** nằm trong cache, thao tác erase có thể làm password hash trong cached instance bị xóa, khiến lần đăng nhập sau không còn dữ liệu để so sánh. Thiết kế trả **bản sao riêng cho authentication result**, quản lý cache identity đúng vòng đời hoặc kiểm soát cách erasure hoạt động. Không tắt `eraseCredentialsAfterAuthentication` một cách tùy tiện chỉ để che lỗi cache.

## 7. Tích hợp Spring Boot + database: hai cách khác nhau ở đâu?

Hai triển khai chỉ khác ở **đối tượng mà `UserDetailsService` trả về**; database, password encoder, authentication provider và filter có thể giữ nguyên.

### Phương án A — DB → User có sẵn

```text
AccountRepository.findByUsername
    → AccountEntity
    → User.withUsername(...).password(hash).authorities(...).flags(...).build()
    → DaoAuthenticationProvider
    → Authentication principal = User
```

Tốt khi không có yêu cầu đưa internal ID vào principal; code đơn giản và dễ kiểm chứng.

### Phương án B — DB → Custom UserDetails

```text
AccountRepository.findByUsername
    → AccountEntity
    → new AppUserDetails(id, username, hash, authorities, flags)
    → DaoAuthenticationProvider
    → Authentication principal = AppUserDetails
```

Tốt khi service cần ID/tenant đã xác minh. Không vì cần ID mà gắn toàn bộ entity vào principal.

Mẫu `UserDetailsService` cho phương án B, **chỉ minh họa, cần tự định nghĩa AccountRepository, AccountEntity và AppUserDetails**:

```java
@Service
public final class DatabaseUserDetailsService
        implements UserDetailsService {
    private final AccountRepository repository;

    public DatabaseUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {
        AccountEntity account = repository.findByUsername(username)
                .orElseThrow(() -> new UsernameNotFoundException("User not found"));

        return new AppUserDetails(
                account.getId(),
                account.getUsername(),
                account.getPasswordHash(),
                toGrantedAuthorities(account.getRoles()),
                account.isEnabled(),
                !account.isExpired(),
                !account.isLocked(),
                !account.isPasswordExpired()
        );
    }
}
```

Trong triển khai thật, `toGrantedAuthorities` phải ánh xạ roles đáng tin sang `GrantedAuthority` và bảo đảm collection hợp lệ. `AppUserDetails` nên có cấu trúc tương tự `AccountDetails` ở ví dụ runnable, với ID, các cờ và phương thức `eraseCredentials` rõ ràng.

**Không làm trong `loadUserByUsername`:** gọi `PasswordEncoder.matches` để tự xác thực (provider sẽ làm), encode lại hash từ database, tra session request bằng thread-local bất ổn, hoặc lấy roles từ request chưa được tin. Đừng đọc email hay username không tồn tại rồi tự tạo account trong callback này.

### Cấu hình provider vẫn như nhau

Đoạn bên dưới là snippet Spring Security 6.5.x, yêu cầu các bean `UserDetailsService` và `PasswordEncoder` đã có:

```java
@Bean
AuthenticationManager authenticationManager(
        UserDetailsService users, PasswordEncoder encoder) {
    DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
    provider.setPasswordEncoder(encoder);
    return new ProviderManager(provider);
}
```

Thay cách tạo `UserDetails` **không bắt buộc** bạn viết custom `AuthenticationProvider`. Trong Spring Boot, framework có thể đã cấu hình provider cho `UserDetailsService`; đừng khai manager trùng chỉ vì muốn thay principal. Với nhiều `SecurityFilterChain`, phải xác minh chain nào thực sự dùng manager đó.

## 8. Dùng custom principal ở controller và service

Sau login thành công, `Authentication.getPrincipal()` là đối tượng do provider trả (trong username/password flow, thường là `UserDetails`). Nếu dùng custom class trong ứng dụng Spring MVC, bạn có thể nhận principal qua `@AuthenticationPrincipal` ở controller:

```java
// Chỉ minh họa method bên trong @RestController và custom AppUserDetails.
@GetMapping("/me")
MeResponse me(@AuthenticationPrincipal AppUserDetails principal) {
    return new MeResponse(principal.getUserId(), principal.getUsername());
}

record MeResponse(long id, String username) {}
```

Đây là snippet, **không phải class chạy độc lập**. Endpoint phải được bảo vệ bằng rule `authenticated()`; khi dùng JWT/OIDC hoặc anonymous, kiểu principal có thể khác và parameter không nhất thiết là `AppUserDetails`. Nên dùng một service mapping phù hợp thay vì ép kiểu provider-specific tại mọi controller.

Tránh trả nguyên object:

```java
// KHÔNG NÊN: principal có thể chứa hash, cờ nội bộ hoặc claims nhạy cảm.
@GetMapping("/raw-principal")
Object raw(@AuthenticationPrincipal Object principal) {
    return principal;
}
```

Đoạn trên là **ví dụ anti-pattern** nhằm chỉ ra rủi ro, không phải API nên triển khai. Hãy trả DTO có allowlist trường, chẳng hạn `id` và `username`, khi thật sự được phép.

### Khi muốn giữ lớp User có sẵn nhưng vẫn cần ID

Có thể chọn một service riêng:

```java
String username = authentication.getName();
Long userId = accountLookupService.findIdByUsername(username);
```

Đây là **snippet giả định service tồn tại**, thích hợp khi chỉ vài điểm trong ứng dụng cần ID. Cần quản lý tính duy nhất của username, đặc biệt trong multi-tenant; thường nên ánh xạ theo namespace/realm đã được xác minh. Không lấy ID từ query parameter và coi nó là ID của authenticated user.

### Khi có nhiều loại authentication

| Flow | Principal thường gặp | Cách lấy ID ứng dụng |
| --- | --- | --- |
| Username/password + `User` | `UserDetails` cụ thể là `User` | Lookup theo key đã chuẩn hóa hoặc lớp identity mapping |
| Username/password + custom | Custom `UserDetails` | Lấy internal ID đã lưu trong principal |
| JWT Resource Server | `Jwt` hoặc principal tùy converter | Ánh xạ issuer/subject hoặc claim đáng tin sang internal ID |
| OIDC Login | `OidcUser` | Ánh xạ cặp issuer + subject, có quy trình account linking |
| Anonymous | Principal anonymous hoặc context không có user thật | Không coi là user nội bộ đã đăng nhập |

Không custom `UserDetails` chỉ để buộc mọi flow khác nhau về cùng một class. Một JWT/OIDC principal có contract riêng; muốn chuẩn hóa phải giải quyết **identity mapping** và security boundary ở tầng thích hợp.

## 9. Các trạng thái tài khoản: mapping và test sai dễ gây lỗi bảo mật

Với class `User` có sẵn, builder sử dụng các cờ mang nghĩa “có vấn đề”; với custom `UserDetails`, interface hỏi trạng thái hợp lệ:

| DB field giả định | `User` builder | Custom `UserDetails` getter |
| --- | --- | --- |
| `enabled=true` | `disabled(false)` | `isEnabled() == true` |
| `locked=true` | `accountLocked(true)` | `isAccountNonLocked() == false` |
| `expired=true` | `accountExpired(true)` | `isAccountNonExpired() == false` |
| `passwordExpired=true` | `credentialsExpired(true)` | `isCredentialsNonExpired() == false` |

Đừng diễn giải `accountNonLocked` là “đã khóa”; ngữ nghĩa đảo chiều là nguyên nhân của nhiều lỗi không nhận diện trong review.

Để test, thực hiện ít nhất:

1. User hợp lệ và mật khẩu đúng → xác thực thành công.
2. User hợp lệ nhưng password sai → `BadCredentialsException`.
3. `enabled=false` → `DisabledException`.
4. `locked=true` → `LockedException`.
5. `expired=true` → `AccountExpiredException`.
6. `passwordExpired=true` → `CredentialsExpiredException`.
7. User không tồn tại → từ chối; trong `DaoAuthenticationProvider` mặc định có thể che thông tin tồn tại user bằng `BadCredentialsException`.
8. User có authorities rỗng → có thể xác thực nhưng không có quyền truy cập các endpoint yêu cầu role.
9. User thay username → internal ID không thay; các relation nghiệp vụ vẫn hoạt động theo ID.
10. Sau login, hash không bị đưa vào response/log; principal custom không bị serialize thừa trường.

Cũng cần xét **cập nhật trạng thái sau khi đăng nhập**. Nếu user bị khóa sau khi đã có session hoặc token, security context/token có thể vẫn chứa dữ liệu được xác thực trước đó. Chỉ đổi cờ trong DB không tự động thu hồi mọi session/token. Hệ thống thật cần chính sách revalidation, logout/revocation, TTL và làm mới quyền tùy yêu cầu.

## 10. Credential erasure, serialization, cache và vòng đời principal

### 10.1. Erase credentials không đồng nghĩa xóa password trong DB

`ProviderManager` thường xóa thông tin credentials của kết quả `Authentication` sau khi thành công, nếu đối tượng triển khai `CredentialsContainer`. Nó giảm dữ liệu nhạy cảm giữ lại trong memory/session.

Điều này **không xóa password hash trong database**, cũng không làm thay đổi cơ chế xác thực tài khoản khác. Custom principal nên hỗ trợ `CredentialsContainer` khi chứa credentials, nhưng phải tránh xóa trực tiếp object DB/cache chia sẻ được tái sử dụng.

Không đặt `setEraseCredentialsAfterAuthentication(false)` làm giải pháp mặc định. Nếu cần cache `UserDetails` có hash, tách lifecycle của cache entry khỏi principal trả về cho request, copy hoặc tái nạp object phù hợp.

### 10.2. Serializable và dữ liệu mutable

`UserDetails` extends `Serializable` vì principal có thể được lưu trong session hoặc truyền qua cơ chế persistence/session replication. Custom class cần cân nhắc:

- Những field có serializable không? Chỉ giữ dữ liệu đơn giản, không đưa `EntityManager`, repository, request, stream hoặc JPA proxy vào principal.
- Có field nào nhạy cảm và bị lưu quá lâu không? Tránh email/phone/token nếu không cần.
- Authorities có đúng thời điểm xác thực không? Nếu role thay đổi, session cũ có thể giữ snapshot cũ.
- `equals` và `hashCode` mô tả danh tính theo ID nào? Nếu username có thể đổi hoặc trùng tenant, không mặc định dùng username để làm domain key.
- Một principal mutable được chia sẻ giữa nhiều request có thể phát sinh race condition khi xóa credentials hoặc cập nhật field. Ưu tiên immutable identity fields và object riêng theo authentication.

### 10.3. Hiệu năng và database lookup

Custom principal chứa ID giúp tránh một số lookup username → ID ở mỗi request, nhưng cũng làm **snapshot ID/role bị giữ theo session**. Đừng coi việc thêm hàng chục field vào principal là tối ưu hiệu năng hiển nhiên. Cân bằng giữa ít query, cập nhật kịp thời, tính chính xác và khả năng thu hồi quyền.

Với nguồn user DB, phải lập index/unique constraint phù hợp cho username trong namespace xác thực; nếu hỗ trợ đổi username/tenant, xác định cách chuyển mapping và tránh account confusion.

### 10.4. Multi-tenant và external identity

`UserDetailsService.loadUserByUsername(String)` chỉ nhận một `String`. Nếu nhiều tenant dùng cùng login name, cần một cách **đáng tin** để xác định namespace trước khi lookup, chẳng hạn manager/provider hoặc token mang context đã xác minh theo kiến trúc hệ thống. Không tự tin `tenantId` do client gửi chỉ vì custom principal có field này.

Nếu đăng nhập qua IdP, internal key thường bắt nguồn từ issuer + subject và liên kết đã được phê duyệt. Email hoặc display name không tự đủ để ghép các tài khoản khác issuer.

## 11. Lỗi thường gặp khi lựa chọn hoặc triển khai

1. **Tưởng `User` là `InMemoryUserDetailsManager`:** `User` là model dữ liệu; manager là nguồn/trình quản lý user. Dùng `User` với DB hoàn toàn hợp lệ.
2. **Custom class nhưng thiếu override flags:** interface 6.5 có default `true` ở các cờ trạng thái, dễ vô tình bỏ qua disabled/locked từ DB.
3. **Đảo nghĩa `isAccountNonLocked`:** tài khoản bị khóa cần trả `false`, không phải `true`.
4. **Trả plaintext từ `getPassword()`:** password phải được lưu dạng hash dùng `PasswordEncoder` thích hợp. Không encode lại hash khi tải.
5. **Ghi role không đúng prefix:** `roles("ADMIN")` thường thành `ROLE_ADMIN`; `authorities("ROLE_ADMIN")` dùng giá trị nguyên. Không thêm hai lần `ROLE_`.
6. **Đưa toàn bộ JPA entity vào principal:** phát sinh lazy loading, serializing, mutable state, thông tin không cần thiết trong session.
7. **Custom `UserDetails` chỉ để có email hiển thị:** dữ liệu thay đổi nhanh và có thể nhạy cảm; phần nhiều nên dùng profile DTO/service.
8. **Không triển khai credential erasure:** password hash có thể được giữ trong session lâu hơn cần thiết.
9. **Thực hiện erasure trên shared cached instance:** cache có thể mất hash và đăng nhập sau thất bại; cần copy/lifecycle rõ ràng.
10. **Tạo custom `UserDetails` rồi kỳ vọng JWT/OIDC tự trả class đó:** principal của flow khác có thể là `Jwt`/`OidcUser`.
11. **Ép `authentication.getPrincipal()` thành custom type vô điều kiện:** có thể gây `ClassCastException` hoặc null nếu anonymous/khác provider.
12. **Trả trực tiếp principal qua JSON:** vô tình lộ hash hoặc thuộc tính nội bộ. Chỉ trả DTO allowlist.
13. **Dùng username làm primary key nghiệp vụ khi có khả năng đổi tên:** internal ID và tenant boundary thường thích hợp hơn.
14. **Phân quyền dựa trên role do client gửi:** authorities phải đến từ user store/issuer đã xác minh.
15. **Tự viết provider hoặc filter để đổi class principal:** thường chỉ cần đổi giá trị trả về của `UserDetailsService`.
16. **Tin rằng thay cờ trong DB lập tức thu hồi mọi session/JWT:** phải có chính sách refresh/revocation phù hợp.
17. **Đổi `equals/hashCode` của principal mà không xem session/cache:** có thể làm hành vi collection, concurrency và principal identity khác dự kiến.
18. **Đặt logic DB trong `getUsername/getAuthorities`:** các getter nên đọc snapshot có sẵn; tránh query ẩn và lỗi khi object đã rời transaction.

## 12. Kiểm thử tối thiểu cho hai lựa chọn

| Điều kiện | Với lớp User có sẵn | Với custom UserDetails |
| --- | --- | --- |
| Username/password hợp lệ | `DaoAuthenticationProvider` chấp nhận | Chấp nhận nếu contract đúng |
| Principal class | `User` | Class custom |
| Internal ID | Không có, cần mapping thêm | Có nếu đã đưa vào constructor |
| Password/hash sau authentication | `User` hỗ trợ erase | Phải thiết kế erase nếu chứa hash |
| Disabled/locked/expired | Builder dựng đúng flags | Getter trả đúng trạng thái |
| Authorities | Từ builder/source đáng tin | Từ collection source đáng tin |
| Identity sau đổi username | Cần tránh gắn domain ID với username | ID có thể giữ ổn định |
| Cache/session | Cần tránh reuse object đã erase | Cần kiểm tra serialization và mutation |
| HTTP/REST DTO | Chỉ xuất field được cho phép | Tương tự, không trả raw object |
| JWT/OIDC | Không tự thành principal của flow khác | Cũng không tự thay flow khác |

Nên dùng **authentication test qua manager/provider thật** để kiểm chứng password hash và flags. Test `@WithMockUser` tạo security context giả lập, phù hợp kiểm tra authorization nhưng **không chứng minh `UserDetailsService` hay `DaoAuthenticationProvider` được gọi**. Với custom principal, có thể dùng test xác thực thực, sau đó kiểm tra `Authentication.getPrincipal() instanceof AppUserDetails` và giá trị internal ID.

Ví dụ định hướng test trong Java:

```java
Authentication authentication = manager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                "mai", "demo-pass"));

assert authentication.isAuthenticated();
assert authentication.getPrincipal() instanceof AppUserDetails;

AppUserDetails principal =
        (AppUserDetails) authentication.getPrincipal();
assert principal.getUserId().equals(expectedUserId);
```

**Đây là pseudocode kiểm thử**, giả định `manager`, `AppUserDetails` và `expectedUserId` có sẵn; dùng JUnit `assertThat`/`assertEquals` thay Java `assert` nếu muốn test không phụ thuộc cờ `-ea`. Với `long` primitive, so sánh bằng `==` hoặc `assertEquals(long,long)` thay `.equals`. Không copy nguyên snippet vào production nếu kiểu dữ liệu thực tế chưa khớp.

## 13. Bài tập thực hành theo mức độ

**Bài 1 — So sánh hai principal.** Chạy demo mục 6, giải thích vì sao cả hai đăng nhập thành công bằng cùng `DaoAuthenticationProvider` nhưng chỉ custom principal có ID. Xác minh không có hash trong output.

**Bài 2 — Mapping trạng thái.** Thiết kế một `AccountEntity` giả có `enabled`, `locked`, `expired`, `passwordExpired`. Viết ánh xạ sang `User.withUsername(...)` và sang custom `UserDetails`. Kiểm thử từng trạng thái lỗi để phát hiện getter bị đảo ngược.

**Bài 3 — DB nguồn thật.** Tạo `AccountRepository.findByUsername(...)` và `UserDetailsService` trả `User` chuẩn. Sau khi mọi test pass, thay duy nhất kết quả trả về thành custom principal có ID; kiểm tra các request vẫn được xác thực.

**Bài 4 — DTO.** Thiết kế endpoint `GET /me` chỉ trả `id`, `username` và những field được duyệt. Không serialize `UserDetails`/`Authentication` trực tiếp. Với cách dùng `User` có sẵn, ID đến từ lookup service; với custom principal, ID đến từ principal đã được xác thực.

**Bài 5 — Cache/erasure.** Dự đoán điều gì xảy ra nếu cached `UserDetails` là cùng instance bị `eraseCredentials`, rồi thử cách trả một instance riêng cho authentication result. Không vô hiệu hóa bảo vệ mật khẩu như một “fix” mặc định.

**Bài 6 — Multi-tenant.** Hai tenant có người dùng cùng username `mai`. Đề xuất khóa định danh đầy đủ, cách ràng buộc tenant đáng tin khi lookup và cách truyền internal ID an toàn vào service. Giải thích tại sao chỉ thêm `tenantId` vào class chưa đủ.

### Tiêu chí hoàn thành

Người học có thể tự trả lời:

- `UserDetails` yêu cầu những trường nào, các cờ `NonExpired/NonLocked` có nghĩa gì?
- Vì sao dùng `User` vẫn tải user từ database được?
- Khi nào internal ID/tenant ID trong principal có giá trị hơn một lookup?
- Vì sao custom `UserDetails` không đòi hỏi custom `AuthenticationProvider`?
- Vì sao `CredentialsContainer` và cache có thể xung đột?
- Làm sao lấy ID qua `@AuthenticationPrincipal` mà không trả password hash?
- Vì sao principal của JWT/OIDC không nhất thiết là `UserDetails`?
- Có thể kiểm chứng cả hai lựa chọn bằng test manager/provider thật như thế nào?

Khi trả lời được các câu trên và chạy được demo, bạn đã có đủ nền tảng để chọn kiểu principal theo nhu cầu nghiệp vụ mà vẫn giữ cơ chế xác thực chuẩn của Spring Security.

## 14. Tài liệu chính thức

- [Spring Security 6.5 — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html): cách provider lấy account details.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): dùng `UserDetailsService`, `PasswordEncoder` và principal khi xác thực thành công.
- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `SecurityContext`, `ProviderManager` và credential erasure.
- [Spring Security 6.5.2 — UserDetails Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/core/userdetails/UserDetails.html): chữ ký và ngữ nghĩa của interface.
- [Spring Security 6.5 — UserDetails](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details.html): thiết kế `UserDetails` và `CredentialsContainer`.
- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): quản lý password hash và encoder.

**Ghi chú phiên bản:** ví dụ khóa theo API Spring Security 6.5.11, thuộc nhánh Spring Security 6.5. Khi dùng bản khác (đặc biệt Spring Security 7 hoặc passwordless flow), kiểm tra lại chữ ký API và cơ chế principal/credentials của đúng phiên bản.