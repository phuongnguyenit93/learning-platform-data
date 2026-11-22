# Không so sánh hai kết quả encode để xác minh cùng một mật khẩu

> **Chủ đề cha:** Mật khẩu · **Bối cảnh:** Spring Security cho Servlet/Spring MVC, Java 17+, Spring Boot 3.5.x và Spring Security 6.5.x. Bài học làm rõ vì sao `passwordEncoder.encode(raw).equals(storedHash)` là cách xác minh sai, cơ chế salt ngẫu nhiên của BCrypt, cách dùng đúng `PasswordEncoder.matches(rawPassword, encodedPassword)`, và cách lưu/đọc mật khẩu trong ứng dụng thực tế. Ví dụ Java có cả chương trình console, một Spring Boot application hoàn chỉnh và kiểm thử JUnit/MockMvc. Những kết quả được ghi là kỳ vọng theo mã nguồn; cần chạy Gradle trong dự án để xác minh thực tế.

## 1. Vấn đề trong một phút

Giả sử Alice đăng ký với mật khẩu `Example!123`. Backend lưu hash:

~~~text
raw password  --[PasswordEncoder.encode]-->  storedHash
"Example!123"                               "$2a$10$..." 
~~~

Một ngày sau Alice đăng nhập với **cùng mật khẩu**. Có người viết:

~~~java
// SAI: không xác minh password bằng cách so sánh hai kết quả encode.
String newlyEncoded = passwordEncoder.encode(passwordFromLogin);
boolean loginAllowed = newlyEncoded.equals(hashFromDatabase);
~~~

Với `BCryptPasswordEncoder`, đoạn này **thường trả false ngay cả khi mật khẩu hoàn toàn đúng**, vì hai lần `encode` dùng salt ngẫu nhiên khác nhau.

Cách đúng:

~~~java
// ĐÚNG: tham số 1 là raw password người dùng vừa nhập;
// tham số 2 là encoded password/hash ĐÃ LƯU trong database.
boolean loginAllowed = passwordEncoder.matches(
    passwordFromLogin,
    hashFromDatabase
);
~~~

**Quy tắc phải thuộc lòng:**

- **Đăng ký hoặc đổi mật khẩu:** gọi `encode(rawPassword)` **một lần để tạo hash mới**, rồi lưu hash.
- **Đăng nhập:** đọc **hash đã lưu**, gọi `matches(rawPasswordFromLogin, storedHash)`.
- **Không tự encode lại rồi so sánh hai chuỗi hash**.
- **Không giải mã hash** để lấy lại password gốc. Một password hash chuẩn được thiết kế theo hướng one-way.

Bài không nói `String.equals` luôn sai trong Java. `equals` rất đúng để so hai chuỗi thông thường; điều sai ở đây là **áp dụng nó để so hai hash độc lập** của một password hash algorithm có salt ngẫu nhiên.

## 2. Phân biệt raw password, encoded password, salt và hash

| Thuật ngữ | Nghĩa | Ví dụ minh họa | Có nên lưu? |
| --- | --- | --- | --- |
| **Raw password** | Mật khẩu người dùng nhập | `Example!123` | **Không lưu plaintext**; tồn tại tạm trong authentication flow |
| **Salt** | Dữ liệu ngẫu nhiên khác nhau theo lần hash/account | Bytes ngẫu nhiên do encoder tạo | Được gắn vào bản mã hash hoặc lưu kèm; không cần giữ bí mật như password |
| **Password hash / encoded password** | Kết quả của thuật toán lưu mật khẩu với salt và work factor | `$2a$10$...` | **Lưu** trong password column |
| **Work factor / cost** | Mức chi phí tính toán để làm chậm thử đoán mật khẩu | BCrypt cost `10`, `12`... | Thường chứa trong định dạng hash |
| **Pepper** | Bí mật chung, nếu chính sách bảo mật sử dụng thêm | Secret do hệ thống quản lý | Không lưu cùng database password hash |
| **PasswordEncoder** | Spring Security API cho encode/matches/upgrade | `BCryptPasswordEncoder`, `DelegatingPasswordEncoder` | Cấu hình thuật toán phù hợp, không lưu object vào DB |

Một **salt không phải password bí mật**. Nếu attacker biết salt, họ vẫn phải thử đoán mật khẩu bằng thuật toán password hashing tốn chi phí. Salt giúp ngăn việc cùng một password trên các account luôn tạo cùng hash và làm các bảng tiền tính dùng chung kém hiệu quả.

**Pepper khác salt**: pepper là secret riêng, nếu dùng phải giữ ngoài database trong secret manager/HSM theo thiết kế. Bài này sử dụng BCrypt chuẩn, không tự tạo pepper tùy tiện hoặc tự viết cơ chế mã hóa mật khẩu.

### 2.1. Vì sao BCrypt thường tạo hai chuỗi khác nhau?

Với BCrypt:

~~~text
Lần đăng ký:
  raw = "Example!123"
  salt = S1 (random)
  encoded1 = bcrypt(raw, S1, cost)

Lần gọi encode thứ hai:
  raw = "Example!123"
  salt = S2 (random)
  encoded2 = bcrypt(raw, S2, cost)

Trong thực tế: S1 != S2 gần như chắc chắn
=> encoded1 != encoded2 gần như chắc chắn.
~~~

Bản hash BCrypt thường mã hóa trong một chuỗi các thông tin như phiên bản thuật toán, cost, salt và kết quả kiểm tra. Ví dụ **hình dạng**:

~~~text
$2a$10$.....................................................
|  |  |
|  |  +-- cost (số vòng làm việc theo quy ước BCrypt)
|  +----- biến thể phiên bản BCrypt
+-------- dấu nhận dạng định dạng
~~~

Dòng mẫu trên **không phải BCrypt hash hợp lệ để chép vào database**; nó chỉ mô tả các thành phần. Một BCrypt string không có `{bcrypt}` prefix thường dài **60 ký tự**; còn `DelegatingPasswordEncoder` có thể đặt `{bcrypt}` phía trước. Không tự tách chuỗi bằng vị trí cố định để xác minh password; hãy dùng `PasswordEncoder`.

Việc hai encoded strings khác nhau **không chứng minh hai raw password khác nhau**. Ngược lại, việc hai encoded strings giống nhau cũng không là định nghĩa của một cơ chế login. Sự trùng salt ngẫu nhiên có xác suất rất nhỏ nhưng không phải một định lý bị cấm tuyệt đối: không viết test dựa trên khẳng định “hai encode bắt buộc luôn khác nhau”.

### 2.2. Mục đích của cost

BCrypt là thuật toán password hashing có cost điều chỉnh. Cost cao hơn làm việc đoán nhiều candidate passwords tốn tài nguyên hơn, nhưng cũng làm server thực hiện login tốn CPU hơn. Chọn cost theo benchmark trên hạ tầng, tải login, mục tiêu chống tấn công và hướng dẫn bảo mật đang áp dụng.

**Không cần tự sinh `new SecureRandom()` mỗi lần login rồi hash với một salt mới để so chuỗi.** `BCryptPasswordEncoder.matches(...)` xử lý salt từ encoded hash đã lưu. Cũng không giảm cost hoặc dùng hash nhanh chỉ vì test chạy chậm.

## 3. `PasswordEncoder` định nghĩa cách dùng chính xác

Contract cơ bản của `org.springframework.security.crypto.password.PasswordEncoder`:

~~~java
// Chữ ký rút gọn từ interface để giải thích, không phải file Java độc lập.
String encode(CharSequence rawPassword);
boolean matches(CharSequence rawPassword, String encodedPassword);
boolean upgradeEncoding(String encodedPassword);
~~~

Trong Spring Security:

- `encode(raw)` tạo encoded password theo encoder hiện tại để lưu.
- `matches(raw, encoded)` kiểm tra **raw password** có khớp **encoded password đã được tạo trước đây** không, bằng chính logic của encoder.
- `upgradeEncoding(encoded)` cho biết hash hiện tại **có nên được cập nhật** theo policy encoder không; nó không tự sửa database chỉ vì bạn gọi method.

Dòng quan trọng:

~~~java
boolean correct = encoder.matches(
    passwordSubmittedNow, // RAW từ login request
    storedHash            // ENCODED lấy từ nguồn tài khoản tin cậy
);
~~~

**Không đảo tham số.** Nếu viết `encoder.matches(storedHash, rawPassword)`, bạn đang yêu cầu encoder coi hash là plaintext và mật khẩu gốc là encoded format; kết quả sẽ sai hoặc gặp lỗi format, tùy encoder.

### 3.1. Bên trong matches của BCrypt có gì?

Khái niệm:

~~~text
matches(rawPassword, storedEncodedPassword)
   |
   +--> Đọc salt/cost/phiên bản từ storedEncodedPassword
   |
   +--> Tính toán kiểm tra rawPassword với các tham số đã lưu
   |
   +--> Đối chiếu với kết quả hash đã lưu
   |
   +--> true hoặc false
~~~

Bạn **không phải** tự tách salt, tự gọi BCrypt hash function, rồi so String.equals; thư viện đã làm việc này và xử lý format cụ thể. Không dùng thuật toán mã hóa reversible để rồi giải mã password vì yêu cầu login.

### 3.2. Vì sao `encode(raw).equals(encoded)` không tương đương `matches(raw, encoded)`?

Cả hai có thể trông như “so sánh hash”, nhưng rất khác:

| Cách viết | Salt được sử dụng | Ý nghĩa | Có phù hợp xác thực? |
| --- | --- | --- | --- |
| `encode(raw)` | Salt mới được tạo theo encoder | Tạo hash mới để lưu | Có, ở **đăng ký/đổi mật khẩu** |
| `encode(raw).equals(storedHash)` | Salt mới so với salt cũ | So hai hash độc lập | **Không** |
| `matches(raw, storedHash)` | Tham số cần thiết rút từ storedHash | Xác minh password so với hash đã lưu | **Có** |
| `matches(otherRaw, storedHash)` | Tham số từ storedHash | Kiểm tra password sai | Trả false cho credential không khớp |
| `storedHash.equals(raw)` | Không dùng password hashing | So plaintext với hash | **Không** |
| `encode(encode(raw))` | Hash lần thứ hai | Tạo hash của chuỗi hash | **Không** phải login hay cách lưu tiêu chuẩn |

Có những encoder **deterministic** có thể tạo cùng chuỗi cho cùng input; điều đó không làm “encode rồi equals” trở thành contract nên dùng cho password verification. Hệ thống nên dùng **PasswordEncoder.matches** và password hashing an toàn thay vì dựa vào tính chất ngẫu nhiên/không ngẫu nhiên của một implementation.

## 4. Chương trình Java 17 có thể chạy để quan sát behavior

Tạo file `PasswordHashLab.java` trong project đã có thư viện `spring-security-crypto` qua Spring Security starter hoặc dependency riêng.

~~~java
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public class PasswordHashLab {

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder(10);

        String raw = "Example!123";
        String hashAtRegistration = encoder.encode(raw);

        // Tạo thêm hash mới của cùng raw password chỉ để minh họa.
        String anotherHash = encoder.encode(raw);

        // Đúng: kiểm tra cùng raw với hash lưu ở thời điểm đăng ký.
        boolean validLogin = encoder.matches(
            raw, hashAtRegistration
        );
        boolean wrongLogin = encoder.matches(
            "WrongPassword", hashAtRegistration
        );

        // Cả hai hash độc lập đều có thể xác minh cùng raw password.
        boolean firstHashMatches = encoder.matches(
            raw, hashAtRegistration
        );
        boolean secondHashMatches = encoder.matches(
            raw, anotherHash
        );

        // Không in hash/password vào production logs.
        System.out.println("validLogin=" + validLogin);
        System.out.println("wrongLogin=" + wrongLogin);
        System.out.println(
            "bothHashesVerify=" + (firstHashMatches && secondHashMatches)
        );
    }
}
~~~

Kết quả logic dự kiến:

~~~text
validLogin=true
wrongLogin=false
bothHashesVerify=true
~~~

**Giá trị stdout trên không chứa hash**, vì hash sẽ thay đổi theo salt ngẫu nhiên. Cũng cố ý **không** in kết quả `hashAtRegistration.equals(anotherHash)` như một assertion cố định: với BCrypt, nó gần như luôn false, nhưng không nên biến xác suất thành bảo đảm logic.

### 4.1. Cách chạy nhanh bằng Gradle

Trong Spring Boot Gradle project có `spring-boot-starter-security`, `PasswordHashLab.java` có thể được đặt tại:

~~~text
src/main/java/PasswordHashLab.java
~~~

Vì đây là class trong default package chỉ phục vụ thử nghiệm, không đặt lẫn vào package scan của ứng dụng production. Cách chạy từ IDE: chọn **Run PasswordHashLab.main** với classpath của project.

Nếu dùng Gradle `application` plugin, có thể cấu hình `mainClass = 'PasswordHashLab'` trong một project thử nghiệm riêng; **đừng thay main class của Spring Boot application đang chạy** chỉ để thử snippet này. Có thể tạo một project console riêng với dependency `org.springframework.security:spring-security-crypto` tương thích phiên bản để chạy chương trình.

Khi muốn chạy từ terminal trong project Maven đã giải quyết dependencies, dùng cơ chế exec plugin hoặc IDE run configuration. Lệnh thuần `javac PasswordHashLab.java` **sẽ không chạy nếu thiếu Spring Security jars trên classpath**. Phân biệt một chương trình Java đầy đủ về mã nguồn với việc cấu hình classpath/dependency.

### 4.2. Phản ví dụ có thể chạy nhưng sai logic

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();

String stored = encoder.encode("Example!123");
String submitted = "Example!123";

// SAI: salt mới được tạo mỗi khi gọi encode.
boolean accepted = encoder.encode(submitted).equals(stored);
~~~

`accepted` **hầu như luôn false** dù mật khẩu đúng. Không nên sửa bằng cách lưu plaintext, tắt salt hoặc cố tạo salt cố định cho mọi user. Chỉ cần:

~~~java
boolean accepted = encoder.matches(submitted, stored);
~~~

Đây là một sự thay đổi **trong cách kiểm tra**, không làm thay thuật toán hash hay dữ liệu lưu trữ. Nếu dữ liệu lưu đã đúng format BCrypt, không cần “rehash tất cả người dùng” để sửa phép so sánh.

## 5. Áp dụng vào ba nghiệp vụ: đăng ký, đăng nhập, đổi mật khẩu

### 5.1. Đăng ký tài khoản

~~~text
POST /registration
   |
   +--> Validate username/password policy
   +--> Kiểm tra username unique/tenant
   |
   v
   passwordEncoder.encode(rawPassword)
   |
   v
   Account(passwordHash=encoded)
   |
   v
   Lưu encoded password vào database
~~~

Ví dụ snippet:

~~~java
public void register(String username, String rawPassword) {
    if (accountRepository.existsByUsername(username)) {
        throw new DuplicateAccountException();
    }

    String storedHash = passwordEncoder.encode(rawPassword);
    accountRepository.insert(username, storedHash);
}
~~~

Đây là **pseudocode gần Java**, vì `AccountRepository` và `DuplicateAccountException` do ứng dụng định nghĩa; không phải file biên dịch độc lập. Ứng dụng thật cần unique constraint ở DB để xử lý race giữa các request đăng ký, password policy, giới hạn kích thước input và không làm lộ credential trong log.

**`encode` ở bước này là đúng**, bởi ta cần tạo hash mới để lưu. Salt/cost có thể nằm ngay trong chuỗi đã lưu.

### 5.2. Đăng nhập

~~~text
POST /login
  username + rawPassword
           |
           v
    AuthenticationManager
           |
           v
    DaoAuthenticationProvider
           |
           +--> UserDetailsService.loadUserByUsername(username)
           |       |
           |       +--> Đọc storedHash và account flags
           |
           +--> PasswordEncoder.matches(rawPassword, storedHash)
           |
           +--> Kiểm tra enabled/locked/expired
           |
           v
    Authentication thành công hoặc AuthenticationException
~~~

**Spring Security đã có luồng này.** Khi dùng `DaoAuthenticationProvider`, đừng tự viết controller login để đọc `UserDetails`, gọi `encode()` rồi so equals. Provider đảm trách xác minh credential, còn filter/manager xử lý request xác thực.

Tại một endpoint cần quyền, `.authenticated()` đánh giá authentication state; `.hasRole()` và policy ở tầng domain đánh giá authorization. `matches` đúng không có nghĩa user tự được mọi quyền.

### 5.3. Đổi mật khẩu

Một flow được kiểm soát:

1. Xác định user hiện tại qua Authentication đã được framework xác minh.
2. Tùy độ nhạy, yêu cầu recent authentication/MFA trước khi đổi.
3. Nếu yêu cầu mật khẩu cũ, kiểm tra `matches(currentRawPassword, storedHash)`.
4. Kiểm tra password policy, danh sách mật khẩu bị lộ theo khả năng hệ thống.
5. Gọi **`encode(newRawPassword)`** để tạo hash mới, lưu atomically.
6. Áp dụng chính sách thu hồi các phiên/tokens cũ và thông báo thay đổi.

~~~java
// Snippet trong service, cần userId từ Authentication đáng tin cậy.
if (!encoder.matches(currentRawPassword, account.getPasswordHash())) {
    throw new InvalidCredentialsException();
}

String newStoredHash = encoder.encode(newRawPassword);
account.setPasswordHash(newStoredHash);
accountRepository.save(account);
~~~

`InvalidCredentialsException`/entity/repository là type riêng của ứng dụng; snippet này chỉ mô tả thứ tự. **Không cần kiểm tra `encode(newRawPassword).equals(oldHash)` để biết hai password giống nhau**; nếu policy muốn cấm dùng lại mật khẩu hiện tại, gọi:

~~~java
boolean newPasswordSameAsOld =
    encoder.matches(newRawPassword, oldStoredHash);
~~~

Tuy nhiên, lịch sử N password cũ phải dựa vào danh sách **stored hashes đã lưu trước đây**, không lưu raw passwords hay so các lần encode mới. Reuse policy, recovery flow và revocation cần được thiết kế riêng theo threat model.

## 6. Một Spring Boot 3.5 / Spring Security 6.5 app minh họa từ đầu đến cuối

Ví dụ tiếp theo cung cấp mã nguồn đủ lớp để chạy một demo với **in-memory account store**. Demo có:

- `RegistrationService` gọi `encode` khi tạo account ban đầu.
- `AccountUserDetailsService` chỉ tải hash đã lưu, không encode lại.
- `DaoAuthenticationProvider` gắn `PasswordEncoder` để dùng `matches`.
- `SecurityFilterChain` bật HTTP Basic; `/me` cần user đăng nhập.
- `PasswordComparisonTest` kiểm tra đúng/sai password qua encoder và qua MockMvc.

**Không có HTTP endpoint đăng ký công khai**: account mẫu được tạo qua `CommandLineRunner` khi app startup. Điều này giúp tập trung vào việc lưu và xác minh password, tránh biến bài thành hướng dẫn mở registration endpoint thiếu rate-limit/verification.

### 6.1. Dependencies và cấu trúc thư mục

Tạo Spring Boot **3.5.x** (Spring Security **6.5.x**), Java **17+**, dùng Spring Web và Spring Security. Với Gradle project đã thiết lập Boot plugin và repositories/version management, thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là **phần dependencies**, không phải file `build.gradle` hoàn chỉnh. Mã Java:

~~~text
src/main/java/com/example/passwordcheck/
  PasswordCheckApplication.java
  AccountStore.java
  RegistrationService.java
  AccountUserDetailsService.java
  SecurityConfig.java
  DemoController.java

src/test/java/com/example/passwordcheck/
  PasswordComparisonTest.java
~~~

### 6.2. PasswordCheckApplication.java

~~~java
package com.example.passwordcheck;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasswordCheckApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordCheckApplication.class, args);
    }
}
~~~

### 6.3. AccountStore.java

~~~java
package com.example.passwordcheck;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Repository;

@Repository
public class AccountStore {

    public record Account(String username, String passwordHash) {}

    private final ConcurrentMap<String, Account> accounts =
        new ConcurrentHashMap<>();

    public boolean insertIfAbsent(Account account) {
        return accounts.putIfAbsent(
            account.username(), account
        ) == null;
    }

    public Optional<Account> findByUsername(String username) {
        return Optional.ofNullable(accounts.get(username));
    }
}
~~~

`AccountStore` giữ **chỉ encoded password** trong bộ nhớ. `ConcurrentMap` và `putIfAbsent` giúp demo xử lý đồng thời khi tạo account trùng username, nhưng đó không phải database production. Khi thay bằng PostgreSQL/MySQL, cần unique constraint, transaction và truy vấn theo account ID/tenant phù hợp.

### 6.4. RegistrationService.java

~~~java
package com.example.passwordcheck;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class RegistrationService {

    private final AccountStore store;
    private final PasswordEncoder encoder;

    public RegistrationService(
            AccountStore store, PasswordEncoder encoder) {
        this.store = store;
        this.encoder = encoder;
    }

    public void register(String username, String rawPassword) {
        if (username == null || username.isBlank()
                || rawPassword == null || rawPassword.isBlank()) {
            throw new IllegalArgumentException(
                "Invalid account registration input"
            );
        }

        String encodedPassword = encoder.encode(rawPassword);

        boolean inserted = store.insertIfAbsent(
            new AccountStore.Account(username, encodedPassword)
        );

        if (!inserted) {
            throw new IllegalArgumentException(
                "Username already exists"
            );
        }
    }
}
~~~

**Điều đúng ở đây:** `encode(rawPassword)` được gọi để tạo hash **khi lưu account**, không phải mỗi lần truy vấn user. Trong production còn cần password policy, breached-password screening, giới hạn input, kiểm tra username unique trong DB, chống abuse và tránh user enumeration từ response.

### 6.5. AccountUserDetailsService.java

~~~java
package com.example.passwordcheck;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public class AccountUserDetailsService
        implements UserDetailsService {

    private final AccountStore store;

    public AccountUserDetailsService(AccountStore store) {
        this.store = store;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AccountStore.Account account =
            store.findByUsername(username)
                .orElseThrow(() ->
                    new UsernameNotFoundException(
                        "Invalid credentials"
                    )
                );

        return User.withUsername(account.username())
            .password(account.passwordHash())
            .roles("USER")
            .build();
    }
}
~~~

**Quan trọng:** `.password(account.passwordHash())` chỉ đặt hash đã đọc vào UserDetails. Nếu viết `.password(encoder.encode(account.passwordHash()))`, bạn đã tạo **hash của hash**; raw password cũ sẽ không còn khớp khi provider kiểm tra.

`loadUserByUsername` **không nhận raw password** và không có trách nhiệm kiểm tra password. Các trạng thái `enabled`, `locked`, `accountExpired` và `credentialsExpired` được User builder để mặc định trong demo; trong database thật phải ánh xạ từ nguồn tin cậy.

### 6.6. SecurityConfig.java

~~~java
package com.example.passwordcheck;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService userDetailsService,
            PasswordEncoder passwordEncoder) {

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(userDetailsService);

        provider.setPasswordEncoder(passwordEncoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager authenticationManager)
            throws Exception {

        http
            .authenticationManager(authenticationManager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @Bean
    CommandLineRunner seedDemoUser(RegistrationService registration) {
        return args -> registration.register(
            "alice", "a1ice-Secret!"
        );
    }
}
~~~

**Đọc luồng:**

1. Một bean `PasswordEncoder` là BCrypt với cost `10` để demo; production cần benchmark và chọn cost/thuật toán theo chính sách hiện hành.
2. Bean `AuthenticationManager` chứa `DaoAuthenticationProvider` được gắn cả `UserDetailsService` và `PasswordEncoder`. Ở Spring Security 6.5, constructor `new DaoAuthenticationProvider(userDetailsService)` phù hợp API.
3. Khi `/me` nhận Basic header, BasicAuthenticationFilter đưa request token đến manager/provider. Provider tải hash từ service và dùng **`matches(raw, storedHash)`**; không gọi `encode(raw).equals(...)`.
4. `STATELESS` tránh phục hồi SecurityContext từ HttpSession trên các request tiếp theo. Điều này phù hợp demo Basic, không bắt buộc cho `PasswordEncoder`.
5. `seedDemoUser` gọi registration flow lúc ứng dụng khởi động và lưu một hash ngẫu nhiên. Một lần startup mới có thể cho hash khác, nhưng cùng password vẫn đăng nhập được.
6. `anyRequest().denyAll()` từ chối URL/method chưa có rule. App không có endpoint công khai để đổi mật khẩu hoặc tạo user.
7. HTTP Basic mang password dạng Base64; phải dùng **HTTPS** khi triển khai trên mạng ngoài localhost.

### 6.7. DemoController.java

~~~java
package com.example.passwordcheck;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return "user:" + authentication.getName();
    }
}
~~~

Controller **không đọc hash, không gọi encode/matches** và không cần biết BCrypt cost. Authentication đã được provider xác minh qua filter. Không trả nguyên `UserDetails`, `Authentication` hoặc hash làm response.

### 6.8. Chạy và quan sát

Với Gradle Wrapper trong project root:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

Từ terminal khác ở localhost:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u 'alice:a1ice-Secret!' http://localhost:8080/me
curl -i -u 'alice:wrong' http://localhost:8080/me
~~~

| Request | HTTP dự kiến | Lý do/body |
| --- | --- | --- |
| `GET /public` không credential | **200** | Body `public` |
| `GET /me` không credential | **401** | HTTP Basic challenge yêu cầu authentication |
| `GET /me` với password đúng | **200** | Body `user:alice` |
| `GET /me` với password sai | **401** | `matches` từ chối |
| `GET /anything` | **403** nếu đã authenticated, hoặc **401** nếu anonymous | Fallback `denyAll`; entry point/handler quyết định status |

Đây là behavior dự kiến của Spring Security 6.5 với cấu hình mẫu. Response body cho lỗi còn phụ thuộc entry point và handler. **Không đưa password thật vào shell history trong production; lệnh trên chỉ có credential demo.**

## 7. JUnit và MockMvc: kiểm chứng đúng điều cần kiểm chứng

Tạo `src/test/java/com/example/passwordcheck/PasswordComparisonTest.java`:

~~~java
package com.example.passwordcheck;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordComparisonTest {

    @Autowired PasswordEncoder encoder;
    @Autowired AccountStore accounts;
    @Autowired MockMvc mvc;

    @Test
    void storedPasswordHashIsNotPlaintext() {
        String hash = accounts.findByUsername("alice")
            .orElseThrow()
            .passwordHash();

        assertNotEquals("a1ice-Secret!", hash);
        assertTrue(encoder.matches("a1ice-Secret!", hash));
        assertFalse(encoder.matches("wrong", hash));
    }

    @Test
    void twoIndependentEncodesBothVerifySameRawPassword() {
        String hashOne = encoder.encode("same-password");
        String hashTwo = encoder.encode("same-password");

        assertTrue(encoder.matches("same-password", hashOne));
        assertTrue(encoder.matches("same-password", hashTwo));

        // Không assertNotEquals(hashOne, hashTwo):
        // salt ngẫu nhiên khiến chúng gần như luôn khác,
        // nhưng contract không hứa một bất biến tuyệt đối.
    }

    @Test
    void storedHashMustBePassedAsSecondParameter() {
        String stored = encoder.encode("correct");

        assertTrue(encoder.matches("correct", stored));
        assertFalse(encoder.matches("incorrect", stored));
    }

    @Test
    void correctPasswordAuthenticatesThroughBasicFilter()
            throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("alice", "a1ice-Secret!")))
            .andExpect(status().isOk())
            .andExpect(content().string("user:alice"));
    }

    @Test
    void wrongPasswordAndMissingCredentialAreRejected()
            throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void publicEndpointStillWorksWithoutLogin()
            throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

**Tại sao test được viết như vậy?**

- `storedPasswordHashIsNotPlaintext` chứng minh registration đã lưu một hash, và password đúng/sai được phân biệt bằng `matches`.
- `twoIndependentEncodesBothVerifySameRawPassword` tập trung vào **contract quan trọng**: cả hai hash có thể xác minh cùng raw password. Nó **không tạo assertion mong manh** rằng hai salt ngẫu nhiên không bao giờ trùng.
- `storedHashMustBePassedAsSecondParameter` bảo vệ thứ tự argument.
- `correctPasswordAuthenticatesThroughBasicFilter` và các test 401 đi qua HTTP Basic filter/AuthenticationManager/DaoAuthenticationProvider, không bypass bằng mock authenticated principal.
- Public endpoint chứng minh rule truy cập hoạt động độc lập với password matching.

**Chưa chạy Gradle trong văn bản này**; bảng kết quả là kỳ vọng dựa trên code. Nếu project dùng version khác, cần xem lại dependency, import và behavior theo Spring Security version thực tế.

### 7.1. Test sai phổ biến

~~~java
// Test yếu/sai mục tiêu:
assertEquals(
    encoder.encode("password123"),
    encoder.encode("password123")
);
~~~

Với BCrypt, test đó hầu như luôn thất bại. Không sửa test bằng cách ép cố định salt để làm hai hash giống nhau. Test nên dùng:

~~~java
String saved = encoder.encode("password123");
assertTrue(encoder.matches("password123", saved));
assertFalse(encoder.matches("different", saved));
~~~

Hoặc nếu đang kiểm tra service đăng ký, đọc **hash thật đã lưu trong test store**, sau đó xác minh raw password bằng `matches`. Không gọi registration service rồi so encoded result với một hash expected tạo bởi lần `encode` khác.

### 7.2. Tránh test dễ vỡ do work factor

Một BCrypt work factor cao có thể làm test nhiều account/login chậm. Đối với unit test thuần túy không kiểm tra BCrypt implementation, có thể dùng fake/in-memory encoder **chỉ trong test**; nhưng integration test cho login thật cần giữ cơ chế encoder nhất quán với production và kiểm tra một số case end-to-end.

Không thay sang `NoOpPasswordEncoder` trong production để test nhanh; nếu test cần tối ưu, tách unit test khỏi crypto integration test và đảm bảo profile test không rò sang cấu hình chạy thật.

## 8. `DelegatingPasswordEncoder`: tiền tố `{bcrypt}` và lỗi cấu hình

Spring Security thường dùng `DelegatingPasswordEncoder` để quản lý nhiều định dạng password hashing và hỗ trợ nâng cấp dần. Tạo encoder:

~~~java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

Đây là snippet với import `org.springframework.security.crypto.factory.PasswordEncoderFactories` và `PasswordEncoder`.

`encode(raw)` mặc định thường tạo chuỗi có dạng:

~~~text
{bcrypt}$2a$10$...
~~~

Dòng trên là **hình dạng minh họa**, không phải hash hợp lệ. Prefix `{bcrypt}` xác định thuật toán được sử dụng ở phần còn lại, giúp `matches(raw, stored)` chọn đúng encoder.

### 8.1. So sánh ba định dạng

| Stored value | Encoder phù hợp | Lưu ý |
| --- | --- | --- |
| `$2a$10$...` | `BCryptPasswordEncoder` thuần | BCrypt hash **không có prefix id** |
| `{bcrypt}$2a$10$...` | `DelegatingPasswordEncoder` có map id `bcrypt` | Có prefix để chọn encoder |
| `{pbkdf2}...` hoặc `{scrypt}...` | Delegating với encoder/version tương ứng | Cần đúng format/parameters theo version |

**Không thể lấy việc hai hash có prefix khác nhau rồi so String.equals** để xác minh user. Nếu hệ thống đang dùng Delegating, luôn truyền **raw password và full stored string** vào `matches`.

### 8.2. Lỗi “There is no PasswordEncoder mapped for the id null”

Khi dùng `DelegatingPasswordEncoder`, database có thể vẫn chứa BCrypt hash legacy kiểu `$2a$...` **không có `{bcrypt}`**. Nếu Delegating không có default encoder cho null/unmapped id, `matches` có thể ném `IllegalArgumentException` thay vì false:

~~~text
There is no PasswordEncoder mapped for the id "null"
~~~

Nguyên nhân **không phải** “mật khẩu sai”, mà là **format lưu không khớp encoder được cấu hình**. Cách xử lý đúng là khảo sát format thật, xác định thuật toán của dữ liệu cũ, và triển khai migration/prefix hợp lệ theo tài liệu.

Ví dụ nếu đã xác minh chắc một cột chứa BCrypt hash thuần, việc gắn prefix `{bcrypt}` cho các hash đó **không cần raw password và không thay BCrypt bits**; tuy nhiên vẫn phải kiểm soát dữ liệu hỗn hợp, backup, transaction, audit và test trước khi migrate. Không gắn prefix tùy ý vào hash không rõ nguồn.

### 8.3. Không lấy `NoOpPasswordEncoder` làm giải pháp sản xuất

Một số ví dụ legacy sử dụng `{noop}` để minh họa plaintext, nhưng đó **không phải** mật khẩu lưu an toàn trong production. Nếu dùng NoOp để “cho login chạy được”, server có thể đang giữ plaintext password hoặc chấp nhận cơ chế không phù hợp.

Nếu đang migrate từ mật khẩu cũ, cần chiến lược rõ cho từng format: xác định algorithm id, cho phép `matches` với hash hiện tại trong giai đoạn chuyển đổi, rồi nâng lên encoder mới khi user xác thực thành công hoặc buộc reset password.

### 8.4. `upgradeEncoding` và `UserDetailsPasswordService`

Có thể nâng cấp password hash sau khi user đăng nhập thành công:

~~~text
User gửi raw password
       |
       v
PasswordEncoder.matches(raw, storedHash) -> true
       |
       v
PasswordEncoder.upgradeEncoding(storedHash)
       |
       +--> false: tiếp tục dùng hash cũ
       |
       +--> true:
               |
               v
           encode(raw) theo policy mới
               |
               v
           UserDetailsPasswordService.updatePassword(...)
               |
               v
           Ghi hash mới vào database an toàn
~~~

Đây là **sơ đồ khái niệm**, không phải một tính năng tự sửa database chỉ vì bean PasswordEncoder tồn tại. Trong luồng DAO, Spring Security hỗ trợ `UserDetailsPasswordService` khi được cung cấp/cấu hình, cùng cơ chế upgrade phù hợp. Ứng dụng phải triển khai cập nhật dữ liệu, transaction, chống race với thay đổi password khác và cache invalidation nếu cần.

**Tuyệt đối không “upgrade” bằng cách `encode(storedHash)`**: đó là tạo hash của hash và làm raw password cũ không khớp.

## 9. Ví dụ các lỗi sai thường thấy ở code review

### 9.1. Lỗi encode hai lần ở login

~~~java
// Sai.
String storedHash = repository.findByUsername(username)
    .orElseThrow()
    .passwordHash();

String hashFromInput = encoder.encode(passwordFromLogin);
if (hashFromInput.equals(storedHash)) {
    // login
}
~~~

Với BCrypt, sai vì hai lần encode tạo salt độc lập. Dùng `matches(passwordFromLogin, storedHash)` hoặc để AuthenticationManager/DaoAuthenticationProvider làm việc đó.

### 9.2. Lỗi encode lại hash khi load user

~~~java
// Sai trong UserDetailsService: account.passwordHash() đã là encoded.
return User.withUsername(account.username())
    .password(encoder.encode(account.passwordHash()))
    .roles("USER")
    .build();
~~~

Provider khi login so raw password với **hash của hash**, thường khiến mọi password bị từ chối. Sửa thành:

~~~java
return User.withUsername(account.username())
    .password(account.passwordHash())
    .roles("USER")
    .build();
~~~

### 9.3. Lỗi so password với hash trực tiếp

~~~java
// Sai.
boolean matches = rawPassword.equals(storedHash);
~~~

Password hash không phải plaintext. Nếu code này có lúc thành công, rất có thể dữ liệu đang được lưu dưới dạng plaintext, cần xử lý bảo mật.

### 9.4. Lỗi đảo thứ tự arguments

~~~java
// Sai.
encoder.matches(storedHash, rawPassword);

// Đúng.
encoder.matches(rawPassword, storedHash);
~~~

Đừng đặt biến tên `password` cho cả hash và plaintext. Nên dùng `rawPassword`, `storedHash`, `encodedPassword` để giảm nhầm lẫn.

### 9.5. Lỗi sinh salt riêng khi verify

~~~java
// Sai về thiết kế nếu tự chọn salt ngẫu nhiên mới để đối chiếu hash.
String salt = generateNewSalt();
String newHash = hashWithSalt(rawPassword, salt);
boolean valid = newHash.equals(storedHash);
~~~

Thay vì tự triển khai hashing/salt logic, dùng `PasswordEncoder.matches`. Nếu ứng dụng cần thuật toán/format đặc biệt, hãy dựa vào thư viện mật mã được đánh giá và contract đã kiểm thử, không tự viết security-critical primitive.

### 9.6. Lỗi dùng cùng một hash làm “password đã xác minh”

~~~java
// Sai: client gửi nguyên stored hash để đăng nhập.
// Server dùng hash như một bearer token thay vì yêu cầu raw password.
if (requestPassword.equals(account.passwordHash())) {
    return allow();
}
~~~

Nếu stored hash bị lộ, attacker có thể đăng nhập mà không biết raw password. **Password hash không phải credential để client trình ra trong giao thức login bình thường.** Tránh kiểu thiết kế “pass the hash”.

### 9.7. Lỗi thay encoder mà không migrate dữ liệu

Lúc trước dùng BCrypt thuần, hôm nay chuyển bean sang Delegating. Các hash cũ thiếu `{bcrypt}`, `matches` có thể ném lỗi id null. Phải có kế hoạch migration và test trên dữ liệu hash thực tế.

### 9.8. Lỗi hardcode password hash trong migration sai phiên bản

Hash được tạo bằng encoder/parameters khác có thể không được xác minh bằng encoder hiện tại. Kiểm tra format, thuật toán, cost và version bằng dữ liệu mẫu không nhạy cảm. Đừng paste hash của tài khoản thật vào issue tracker hoặc tài liệu công khai.

### 9.9. Lỗi giả định mọi chuỗi bằng nhau cùng một Unicode password

Một số input Unicode có thể có những biểu diễn code point khác nhau nhưng hiển thị tương tự. Java String equality và hashing nhận byte sequence từ encoding/normalization policy của ứng dụng. Nếu thay Unicode normalization, case mapping hoặc whitespace trimming giữa **đăng ký** và **đăng nhập**, cùng thứ người dùng nhìn thấy có thể không còn khớp.

Hãy có chính sách nhập mật khẩu nhất quán, tránh tự `trim()` hoặc lowercase password; khác với username, password thường cần giữ nguyên giá trị người dùng đặt. Nếu muốn áp dụng normalization, cần thiết kế và ghi rõ từ đầu, test cả Unicode và password dài.

### 9.10. Lỗi dùng `equalsIgnoreCase` cho password

Password thông thường phân biệt chữ hoa/chữ thường. Không dùng `equalsIgnoreCase`, `toLowerCase`, `trim` hoặc tự loại bỏ ký tự để “tăng tỷ lệ login thành công”. Điều đó làm thay đổi bí mật người dùng đã chọn.

### 9.11. Lỗi log raw password và encoded hash

~~~java
// Không làm ở production:
log.info("login password={}", rawPassword);
log.info("stored password hash={}", storedHash);
~~~

Hash không phải plaintext nhưng vẫn là dữ liệu nhạy cảm phục vụ tấn công offline nếu bị lộ. Không đưa raw password, password hash, Authorization header, cookie/session token vào application logs, traces, analytics hay response.

### 9.12. Lỗi test hai encoded strings bằng assertEquals

~~~java
// Sai mục tiêu với encoder salted.
assertEquals(encoder.encode("abc"), encoder.encode("abc"));
~~~

Cách test đúng là **`matches("abc", hash)`** rồi kiểm tra password sai trả false. Không buộc BCrypt sử dụng salt cố định trong production để làm test xanh.

## 10. Mất thời gian ở login: không bỏ cơ chế hashing để tối ưu vội

Password hash được thiết kế chậm có chủ đích. Nếu server có nhiều yêu cầu login, phải cân bằng **cost/throughput** và kiểm soát tấn công:

- Benchmark BCrypt cost trên CPU production và cấu hình instance thực tế.
- Có rate limits theo tài khoản và nguồn request, nhưng tránh tự tạo DoS bằng cơ chế lockout quá dễ bị abuse.
- Có biện pháp phát hiện credential stuffing/password spraying, audit thất bại login, MFA khi cần.
- Đặt giới hạn input hợp lý để chống resource exhaustion, nhưng vẫn hỗ trợ passphrases dài theo password policy.
- Thiết kế phản hồi không làm lộ username tồn tại thông qua thông điệp/timing quá khác biệt.
- Không dùng `NoOpPasswordEncoder`, MD5/SHA-1 hoặc một vòng SHA-256 trực tiếp để thay BCrypt chỉ nhằm tăng tốc.

### 10.1. BCrypt và password rất dài

BCrypt truyền thống có giới hạn liên quan đến **72 byte đầu vào** tùy implementation. Với mật khẩu Unicode, số byte UTF-8 không nhất thiết bằng số ký tự Java. Khi ứng dụng đặt chính sách mật khẩu dài, phải kiểm tra hành vi encoder/version đang chạy và nguy cơ hai input khác nhau được coi giống nhau do cắt độ dài.

Không tự cắt password xuống 72 ký tự hay tự hash trước bằng SHA-256 không qua thiết kế kỹ càng; những thay đổi như vậy có thể khiến login giữa các version không tương thích hoặc tạo rủi ro. Chọn password storage scheme và input policy có tài liệu, test Unicode/long passwords và hướng dẫn người dùng rõ ràng.

### 10.2. Timing và user enumeration

Một luồng authentication cho username không tồn tại có thể xử lý khác với password sai. Spring Security/DaoAuthenticationProvider có cơ chế hỗ trợ hạn chế user enumeration ở một số tình huống, nhưng ứng dụng vẫn cần đánh giá thời gian, response, rate limit và log. Không trả thông tin “account này tồn tại nhưng password sai” cho request public nếu chính sách không cho phép.

## 11. Bảng xử lý sự cố

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra đúng |
| --- | --- | --- |
| Password đúng vẫn bị 401 | Code gọi `encode(raw).equals(stored)` | Đổi sang `matches(raw, stored)` |
| Hash mới khác hash cũ | Salt ngẫu nhiên | Đây là behavior bình thường; cả hai có thể match cùng raw |
| `matches` trả false cho mọi user | Service encode lại stored hash | Chỉ load hash gốc từ DB |
| `There is no PasswordEncoder mapped for id "null"` | Delegating được dùng với hash thiếu `{id}` | Xác định format và migrate/thiết lập encoder phù hợp |
| `matches` throw format error | Hash không hợp lệ hoặc algorithm id không được hỗ trợ | Xem migration, kiểm tra dữ liệu và compatibility |
| Login chậm | BCrypt/Argon2 work factor cao, CPU quá tải | Benchmark và capacity/rate limiting, không tắt hashing |
| Login đúng nhưng /admin 403 | Authentication thành công, thiếu ROLE_ADMIN | Kiểm tra authorization/GrantedAuthority riêng |
| Password reset xong session cũ vẫn hoạt động | Session/token chưa bị revoke | Có chính sách revoke session/refresh token |
| User đổi password xong vẫn dùng password cũ ở node khác | Cache/replication/credential store chưa cập nhật | Xem invalidation, DB transaction, IdP |
| Unicode password trông giống nhưng login sai | Chuyển đổi input/normalization khác nhau | Đồng nhất policy và test code points/bytes |
| Không đăng nhập sau khi đổi encoder | Hash prefix/parameters khác | Dùng Delegating/migration strategy đúng |
| Hash xuất hiện trong API response | Serialize nguyên UserDetails/Authentication | Chỉ trả DTO cho client; không expose hash |

**401 Unauthorized** thường liên quan authentication, **403 Forbidden** thường là không đủ quyền hoặc một filter như CSRF từ chối. Với form login, thất bại có thể là 302 redirect. Không coi mọi 403 là lỗi `PasswordEncoder`.

## 12. Quy tắc kiểm tra trong code review

Khi review một PR chứa password-related code, tự hỏi:

1. `encode(rawPassword)` có chỉ được gọi khi **tạo/migrating/đổi hash**, chứ không phải mỗi lần login so equals?
2. `matches` có nhận **raw làm tham số đầu tiên** và **stored encoded hash làm tham số thứ hai**?
3. Hash được lưu sau khi encode và không bị encode thêm khi `UserDetailsService` đọc lại?
4. Tất cả account có cùng convention định dạng `{bcrypt}`/BCrypt thuần theo encoder được cấu hình?
5. Có unit/integration tests cho correct password, wrong password và invalid/missing credentials?
6. Có kiểm thử password từ account store thực mà không tự tạo hash “expected” bằng một lần encode khác?
7. Có tự viết salt/hash, cắt input, lowercase, trim hoặc sửa Unicode password không?
8. Password encoder cost/parameters có được đo trên môi trường tương ứng và điều chỉnh hợp lý?
9. Password hash/raw token có bị log, trả qua JSON, dump vào exception hoặc metrics không?
10. Registration/change-password có uniqueness, validation, rate limiting, password policy và recovery thích hợp?
11. Với thay đổi hash algorithm, có migration/upgrading và `UserDetailsPasswordService` nếu cần?
12. Với reset password, session/token/remember-me có được thu hồi theo chính sách không?
13. Với stored hash malformed/unmapped id, hệ thống có xử lý an toàn mà không fail-open?
14. Tên các biến `rawPassword`, `storedHash` có giúp tránh đảo tham số không?
15. Backend có để Spring Security provider xác minh credential thay vì tự tạo authenticated token từ client data không?

Một phép so String.equals nhỏ ở login có thể làm hàng loạt người dùng bị khóa ngoài hệ thống. Review đúng cả **chiều dữ liệu** và **vòng đời hash** quan trọng hơn chỉ xem tên hàm.

## 13. Bài tập tự kiểm tra

**Câu 1.** Một user đăng ký password `Example!123`; BCrypt tạo hash X. Ở lần login, BCrypt encode lại password cho hash Y khác X. Có nghĩa user nhập sai không?

**Đáp án:** Không. Salt ngẫu nhiên khiến hai lần encode thường tạo hash khác nhau dù raw password giống hệt. Phải kiểm tra `matches("Example!123", X)`.

**Câu 2.** Dòng nào dùng để xác minh password?

~~~java
// A
encoder.encode(raw).equals(storedHash);

// B
encoder.matches(raw, storedHash);

// C
encoder.matches(storedHash, raw);

// D
raw.equals(storedHash);
~~~

**Đáp án:** **B**.

**Câu 3.** Một account có stored hash BCrypt, có cần decode stored hash để lấy password thật không?

**Đáp án:** Không, và password hashing chuẩn là one-way. Dùng `matches` để kiểm tra candidate raw password.

**Câu 4.** `UserDetailsService.loadUserByUsername` nên encode password hash thêm một lần không?

**Đáp án:** Không. Nó cần trả hash hiện có cùng authorities/account status. Provider chịu trách nhiệm kiểm tra credential.

**Câu 5.** Tại sao hai user cùng đặt `Example!123` vẫn có thể có storedHash khác nhau?

**Đáp án:** Mỗi account/lần encode có salt ngẫu nhiên riêng, giúp tránh chia sẻ cùng fingerprint hash.

**Câu 6.** Có nên cố định salt của tất cả account để hai lần `encode()` tạo cùng chuỗi và test pass?

**Đáp án:** Không. Làm như vậy phá mục đích của salt; sửa test/login để dùng `matches`.

**Câu 7.** Khi đổi password từ `old` sang `new`, encode được gọi ở bước nào?

**Đáp án:** Xác minh mật khẩu cũ bằng `matches(oldRaw, oldStoredHash)` nếu policy yêu cầu; tạo hash của `newRaw` bằng `encode(newRaw)` rồi lưu.

**Câu 8.** Muốn cấm user dùng lại password cũ, nên so hai encoded strings bằng equals?

**Đáp án:** Không. Dùng `matches(newRaw, oldStoredHash)` với hash cũ; nếu kiểm tra lịch sử, đối chiếu lần lượt các historical stored hashes theo chính sách.

**Câu 9.** Lỗi `There is no PasswordEncoder mapped for the id "null"` thường chỉ điều gì?

**Đáp án:** `DelegatingPasswordEncoder` không nhận dạng được id/format hash được lưu, chẳng hạn thiếu `{bcrypt}`. Không tự hiểu đó là sai password; cần xác minh cấu hình và migration.

**Câu 10.** Có nên lưu raw password vào DB cùng hash để phòng trường hợp encoder thay đổi?

**Đáp án:** Không. Lưu encoded hash phù hợp và có chiến lược migration/reset khi thay algorithm, không giữ plaintext.

**Câu 11.** BCrypt cost có tác động gì?

**Đáp án:** Tác động chi phí tính toán cho encode/matches, làm brute-force khó hơn nhưng tăng tải server; cần benchmark và capacity planning.

**Câu 12.** Nếu một unit test assert `encoder.encode("abc") == encoder.encode("abc")` thì nên sửa ra sao?

**Đáp án:** Tạo một hash bằng encode, rồi assert `matches("abc", hash)` true và `matches("wrong", hash)` false.

**Câu 13.** `matches` thành công có đồng nghĩa user được quyền vào `/admin`?

**Đáp án:** Không. Authentication và authorization khác nhau; còn role, authority, ownership và trạng thái account.

**Câu 14.** Có nên convert mọi password sang lowercase hoặc trim trước khi matches?

**Đáp án:** Không tự ý. Làm thế có thể đổi bí mật đã chọn và tạo behavior không nhất quán. Theo chính sách được thiết kế và kiểm thử nhất quán.

**Câu 15.** Lộ password hash có an toàn tuyệt đối vì không thể giải mã?

**Đáp án:** Không. Hash chống lưu plaintext nhưng attacker có thể thử đoán offline. Cần algorithm đủ mạnh, salt, cost, bảo vệ database, rate limiting và chính sách xử lý sự cố.

## 14. Tài liệu chính thức

- Spring Security — **Password Storage**: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security 6.5 — **Spring Security Crypto Module**: https://docs.spring.io/spring-security/reference/6.5/features/integrations/cryptography.html
- Spring Security — **PasswordEncoder**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/password-encoder.html
- Spring Security — **DaoAuthenticationProvider**: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — **UserDetailsService**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security — **Username/Password Authentication**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html
- Spring Security API — **PasswordEncoder**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html
- OWASP — **Password Storage Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- OWASP — **Authentication Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html

**Kết luận:** Hai kết quả `encode()` của cùng password với BCrypt **thường khác nhau là hoàn toàn bình thường**, bởi salt được tạo ngẫu nhiên. **Chỉ encode để lưu hoặc nâng cấp hash; dùng `PasswordEncoder.matches(rawPassword, storedHash)` để đăng nhập và kiểm tra password cũ.** Đó là contract ổn định giúp ứng dụng tránh lỗi false-negative, bảo vệ plaintext và sẵn sàng nâng cấp password hashing sau này.
