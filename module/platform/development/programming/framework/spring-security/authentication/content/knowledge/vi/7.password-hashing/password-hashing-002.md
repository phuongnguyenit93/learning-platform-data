# encode, matches và upgradeEncoding trong Spring Security PasswordEncoder

> **Ngữ cảnh:** Spring Security – authentication, nhóm **Băm mật khẩu**. Bài học làm rõ ba phương thức `encode`, `matches`, `upgradeEncoding` của `PasswordEncoder`, cách dùng trong vòng đời tài khoản, cơ chế BCrypt/DelegatingPasswordEncoder, và cách nâng cấp hash an toàn sau một lần xác thực thành công bằng `DaoAuthenticationProvider` cùng `UserDetailsPasswordService`. Ví dụ hướng tới Java 17+ và Spring Boot Servlet.

## 1. Ba phương thức phục vụ ba câu hỏi khác nhau

Không nên lưu plaintext password trong database. Server lưu một **password hash** được tạo bởi thuật toán chuyên dụng có salt và work factor, ví dụ BCrypt. Khi user đăng nhập, hệ thống phải xác minh password client cung cấp với hash này mà không thể “giải mã” hash thành password gốc.

Ba phương thức của `PasswordEncoder` tương ứng ba thời điểm:

| Phương thức | Câu hỏi | Thời điểm |
| --- | --- | --- |
| `encode(raw)` | Tạo hash mới để lưu bằng chính sách hiện tại thế nào? | Tạo/đổi/reset password; rehash sau authentication hợp lệ |
| `matches(raw, encoded)` | Password người gọi vừa cung cấp có khớp hash lưu trữ không? | Trong authentication |
| `upgradeEncoding(encoded)` | Hash được lưu có cần tái tạo bằng thuật toán/cost hiện tại không? | Đánh giá migration sau khi có password đúng |

Sơ đồ:

```text
ĐĂNG KÝ/ĐỔI PASSWORD
    password thô mới
         |
         v
    PasswordEncoder.encode(...)
         |
         v
    hash lưu trong kho tài khoản

ĐĂNG NHẬP
    raw password từ client + hash từ DB
         |
         v
    PasswordEncoder.matches(...)
       |                |
      SAI              ĐÚNG
       |                |
    Từ chối       Các kiểm tra authentication khác
                        |
                 Thành công toàn bộ?
                   |          |
                  Không       Có
                   |          |
                Từ chối      v
                        upgradeEncoding(stored)?
                            |           |
                           false       true
                            |           |
                         giữ hash     encode(raw đã xác minh)
                                        |
                                        v
                                 ghi hash mới an toàn
```

**Không được tạo hash mới từ password sai**, vì điều đó có thể biến một lần thử đăng nhập thất bại của kẻ tấn công thành thao tác đổi password của tài khoản nạn nhân.

## 2. Hợp đồng API chính xác

Interface `org.springframework.security.crypto.password.PasswordEncoder` có những method chính:

```java
String encode(CharSequence rawPassword);

boolean matches(CharSequence rawPassword, String encodedPassword);

default boolean upgradeEncoding(String encodedPassword) {
    return false;
}
```

Đây là **hình dạng API rút gọn để giải thích**, không phải một file bạn cần tự định nghĩa. Ở một số phiên bản, API còn khai báo annotation về nullable; hãy theo contract của version đang dùng.

- `encode` nhận plaintext password mới và trả **chuỗi encoded** có thể lưu.
- `matches` nhận **plaintext trước, stored hash sau**; kết quả hợp lệ là một boolean.
- `upgradeEncoding` chỉ nhận hash, **không nhận plaintext**, nên không thể kiểm tra credential hay tự băm lại.
- Implementation mặc định của `upgradeEncoding` ở interface trả `false`; một số encoder cụ thể override.
- `upgradeEncoding=false` không có nghĩa mọi hash đều đủ an toàn trước mọi tiêu chuẩn. Nó chỉ diễn tả chính sách nâng cấp của encoder hiện đang được dùng.
- Khi hash sai định dạng hoặc id không được hỗ trợ, implementation có thể trả false hoặc ném lỗi; không coi mọi input bất thường là một login sai thông thường mà không kiểm soát.

Tên `matches` có nghĩa kiểm tra phép khớp, **không phải** so sánh trực tiếp hai plaintext strings. PasswordEncoder còn xử lý salt/định dạng/hash work factor theo thuật toán của nó.

## 3. encode: tạo password hash để lưu

BCrypt là một ví dụ phổ biến về password hashing có salt và cost. Nếu chọn strength là 12:

```java
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

PasswordEncoder encoder = new BCryptPasswordEncoder(12);
String storedHash = encoder.encode("correct-horse");
```

Đây là **mảnh code dùng trong method** của ứng dụng có dependency Spring Security Crypto; không phải chương trình Java có `main` độc lập.

Hash BCrypt thật có dạng tương tự:

```text
$2a$12$[phần salt và hash được sinh ra]
```

Phần trong ngoặc vuông chỉ để mô tả hình dạng, **không phải một BCrypt hash hợp lệ**. Không dùng nó như password đã mã hóa thật trong demo. Tham số `12` là cost được ghi bên trong hash; nó không phải độ dài password hay số ký tự salt.

### Vì sao băm hai lần thường khác nhau?

Với salt ngẫu nhiên, dù plaintext giống nhau, hai lần encode thường tạo kết quả khác:

```java
String h1 = encoder.encode("correct-horse");
String h2 = encoder.encode("correct-horse");

System.out.println(h1.equals(h2)); // thường false
System.out.println(encoder.matches("correct-horse", h1)); // true
System.out.println(encoder.matches("correct-horse", h2)); // true
```

Hai dòng `matches` là kết quả có thể dự đoán khi encoder và hash hợp lệ. Dòng `equals` “thường false” vì salt ngẫu nhiên; không nên đặt một assertion tuyệt đối rằng hai random salt **không bao giờ** trùng.

Vì lý do này, cách sau **sai**:

```java
// SAI: BCrypt encode lại thường có salt khác.
boolean accepted =
        encoder.encode(presentedPassword).equals(storedHash);
```

`presentedPassword` và `storedHash` ở đây là các biến minh họa. Để kiểm tra raw password có khớp hash cũ, luôn dùng `matches`.

### Không nhầm password hashing với digest thông thường

`SHA-256(password)` hoặc `MD5(password)` thuần có tốc độ rất nhanh, không phù hợp làm cơ chế lưu mật khẩu hiện đại. Password hashing chuyên dụng dùng salt và chi phí tính toán có thể điều chỉnh, giúp làm chậm việc đoán mật khẩu ngoại tuyến khi kho hash bị lộ. Việc lưu hash đúng vẫn cần kết hợp HTTPS, rate limiting, MFA, bảo vệ DB, backup, logs, và quy trình xử lý credential bị lộ.

## 4. matches: kiểm tra password nhưng chưa đủ để kết luận login thành công

`matches` nhận:

1. `rawPassword` – chuỗi mật khẩu do người gọi trình bày qua kênh xác thực.
2. `encodedPassword` – hash do server tải từ nguồn danh tính đáng tin cậy.

Ví dụ:

```java
String stored = encoder.encode("s3cret");

System.out.println(encoder.matches("s3cret", stored)); // true
System.out.println(encoder.matches("wrong", stored));  // false
```

Đoạn trên là mảnh code có biến `encoder` đã được khởi tạo, không phải một file Java chạy riêng.

### Hai tham số không hoán đổi được

`matches(storedHash, rawPassword)` không phải cách dùng hợp lệ tương đương `matches(rawPassword, storedHash)`. Hash phải nằm ở tham số thứ hai để encoder nhận biết format, salt và cost.

Không nên tự tách salt rồi băm lại theo công thức tự chế. Với BCrypt, đối tượng encoder nhận string hash được lưu và thực hiện phép kiểm tra phù hợp.

### matches=true chưa có nghĩa là được đăng nhập

Spring Security còn phải kiểm tra những điều kiện khác, chẳng hạn `UserDetails.isEnabled()`, `isAccountNonLocked()`, `isAccountNonExpired()`, `isCredentialsNonExpired()` hoặc chính sách authentication khác.

```text
UserDetailsService -> UserDetails(passwordHash, status, authorities)
                              |
                              v
                    DaoAuthenticationProvider
                      |          |
                      |          +-- PasswordEncoder.matches
                      +-- Account status checks
                              |
                              v
                  Authentication thành công nếu hợp lệ
```

Một tài khoản bị khóa có thể có password đúng, nhưng `DaoAuthenticationProvider` vẫn từ chối tạo authenticated token. Không dùng kết quả `matches=true` để tự cấp quyền hoặc bỏ qua account status.

Nếu sử dụng form login/HTTP Basic chuẩn, hãy để `AuthenticationManager`/`DaoAuthenticationProvider` gọi `matches` thay vì tự viết controller `/login` với thao tác `matches` rồi tự tạo trusted `Authentication`. Cách tự viết dễ bỏ qua nhiều lớp bảo vệ đã có trong framework.

## 5. upgradeEncoding: nhận biết thời điểm cần rehash

`upgradeEncoding(storedHash)` chỉ nhìn hash cũ và chính sách hiện tại của encoder. Nó trả `true` khi implementation đánh giá hash nên được tạo lại bằng chính sách mới. Nó **không thực hiện rehash, không cập nhật database và không xác minh password**.

Với BCrypt, một tiêu chí cụ thể là cost: khi stored BCrypt cost thấp hơn strength của `BCryptPasswordEncoder` hiện tại, `upgradeEncoding` trả `true`.

Ví dụ:

```java
PasswordEncoder previous = new BCryptPasswordEncoder(8);
PasswordEncoder current = new BCryptPasswordEncoder(12);

String oldHash = previous.encode("s3cret");

System.out.println(current.matches("s3cret", oldHash)); // true
System.out.println(current.upgradeEncoding(oldHash));   // true

String newHash = current.encode("s3cret");

System.out.println(current.matches("s3cret", newHash)); // true
System.out.println(current.upgradeEncoding(newHash));   // false
```

Đây là **mảnh code dùng trong method** có các import thích hợp. Dù `current` dùng cost 12, nó vẫn đọc thông tin cost/salt trong hash BCrypt cost 8 để xác minh credential. Sau khi rehash bằng cost 12, checker không còn đòi nâng cấp vì cost đã đạt chính sách hiện tại.

### Cost không tuyến tính

BCrypt work factor tăng theo cấp số nhân. Từ cost 8 lên 12 không chỉ thêm bốn phép tính; nó làm khối lượng công việc lớn hơn đáng kể. Vì vậy cost cao hơn có thể tăng độ trễ đăng nhập và CPU load. Chọn cost dựa trên benchmark và ngân sách hiệu năng, không chọn giá trị tối đa theo cảm tính.

### Nếu không override upgradeEncoding

Nếu một custom `PasswordEncoder` chỉ implement `encode` và `matches`, mặc định `upgradeEncoding` trả false. Điều này không chứng minh encoder custom đã có chiến lược migration đúng. Cần thiết kế và kiểm thử cách nhận diện hash cũ một cách chủ động.

### Vì sao phải chờ xác thực hợp lệ?

Giả sử user An có hash H1. Attacker gửi password `wrong`, application phát hiện H1 cần nâng cấp, rồi chạy `encode("wrong")` và cập nhật DB. Attacker đã thay password của An bằng mật khẩu do mình biết **mà không cần đăng nhập thành công**. Đây là lỗi privilege compromise nghiêm trọng. Tín hiệu `upgradeEncoding=true` **không cho phép** thực hiện update khi `matches` hoặc bước authentication khác thất bại.

## 6. Ma trận ba phương thức theo nghiệp vụ

| Nghiệp vụ | `encode` | `matches` | `upgradeEncoding` |
| --- | --- | --- | --- |
| Đăng ký user | Băm password mới | Không cần hash cũ | Không cần vì đã dùng chính sách mới |
| Đăng nhập đúng | Dùng khi phải lazy rehash | **Có** | Xét hash hiện có |
| Đăng nhập sai | Không được ghi lại password sai | **Có**, trả không khớp | Không kích hoạt migration |
| Đổi password | Băm password mới | Có thể kiểm tra password cũ | Không cần rehash password cũ trước khi đổi |
| Reset password qua token hợp lệ | Băm password mới | Có thể không có raw password cũ | Không cần rehash hash cũ |
| Tăng BCrypt cost | Băm lại khi xác thực thành công | Vẫn kiểm tra được hash cũ | Xét old cost nhỏ hơn current cost |
| Chuyển thuật toán | Tạo hash theo thuật toán mới | Converter/delegating kiểm tra hash cũ được phép | Nhận biết id/cost cần đổi |
| Request JWT bearer | Không có plaintext password nội bộ | Thường không dùng | Không tự nâng cấp mỗi bearer request |

Với JWT, OIDC và SSO, ứng dụng có thể không bao giờ nhận plaintext password của user. Không được cố “migrate” hash chỉ bằng cách nhìn claim của token. Nếu user cần đổi password, việc đó thuộc identity service quản lý password hoặc một flow xác minh khác.

## 7. DelegatingPasswordEncoder và định dạng {id}

Hệ thống lâu năm có thể có nhiều thế hệ password hash. `DelegatingPasswordEncoder` nhận diện thuật toán dựa trên một tiền tố ở đầu stored hash:

```text
{id}encodedPassword

Ví dụ hình dạng:
{bcrypt}$2a$12$...               (hash BCrypt có prefix)
{pbkdf2}...                      (hash PBKDF2 có prefix)
{scrypt}...                      (hash SCrypt có prefix)
```

Những chuỗi có dấu ba chấm chỉ là **mô tả format**, không phải hash hợp lệ. `idForEncode` là id để tạo hash mới; `matches` dùng id có sẵn trong stored hash để chọn encoder tương ứng.

### Factory mặc định

```java
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

String encoded = encoder.encode("correct-horse");

System.out.println(encoded.startsWith("{bcrypt}")); // true với factory mặc định
System.out.println(encoder.matches("correct-horse", encoded)); // true
```

Đây là **mảnh code chạy trong method**, không phải ứng dụng độc lập. Theo tài liệu Spring Security hiện hành, factory mặc định dùng `bcrypt` làm id để encode; danh sách encoder tương thích có thể thay đổi theo phiên bản và cấu hình.

### Tạo delegating encoder với cost do bạn kiểm soát

```java
import java.util.Map;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

PasswordEncoder current = new DelegatingPasswordEncoder(
        "bcrypt",
        Map.of("bcrypt", new BCryptPasswordEncoder(12)));
```

Ví dụ này **chỉ** cho phép id `bcrypt`; nó không tự hỗ trợ mọi thuật toán legacy. Trong hệ thống thật, thêm encoder cũ cần thiết vào mapping trong giai đoạn migration có kiểm soát và ghi rõ thời điểm loại bỏ. Không cho phép `NoOpPasswordEncoder` hoặc các fallback plaintext chỉ để dữ liệu cũ “đăng nhập được”.

### upgradeEncoding với delegating

Nếu một hash có `{id}` khác `idForEncode` hiện tại, encoder delegating có thể đánh dấu cần nâng cấp. Nếu id đã trùng, nó có thể hỏi encoder con xem work factor/format có cần thay đổi hay không. Vì thế migration có thể bao gồm **đổi thuật toán** và **tăng cost trong cùng thuật toán**.

Cần đặc biệt chú ý hash BCrypt cũ không có tiền tố như `$2a$10$...`. Khi chuyển sang delegating decoder chỉ nhận `{id}`, stored value không prefix có thể gây lỗi vì id không xác định. Nên thiết kế migration thêm prefix có căn cứ trên format hash đã xác nhận, hoặc một fallback legacy rất giới hạn và có thời hạn loại bỏ. Không coi chuỗi không prefix là password plaintext.

### Không tự động mã hóa lại mọi hash trong DB

Không thể lấy một BCrypt hash rồi gọi `encode(oldHash)` để tạo “hash password mới” phù hợp với plaintext cũ. Thao tác đó sẽ hash **chuỗi hash**, làm password thật không còn khớp. Migration đúng là rehash **raw password đã được xác minh** khi login, hoặc một password mới trong flow reset.

## 8. DaoAuthenticationProvider kết nối PasswordEncoder với UserDetailsPasswordService

Trong Spring Security Servlet username/password, `DaoAuthenticationProvider` dùng `UserDetailsService` tải user, rồi `PasswordEncoder` kiểm tra password và các điều kiện xác thực. Ở đường thành công, nó có thể gọi `upgradeEncoding`; nếu cần và có `UserDetailsPasswordService`, provider tạo hash mới từ plaintext password đã xác thực và gọi writer:

```java
UserDetails updatePassword(UserDetails user, String newPassword);
```

Đây là **chữ ký rút gọn** của `UserDetailsPasswordService`. Tên `newPassword` trong contract nghĩa là **password đã encoded bằng PasswordEncoder**, không phải plaintext. Implementation phải cập nhật kho người dùng đúng account và trả `UserDetails` phản ánh thay đổi.

### Vì sao riêng PasswordEncoder không đủ?

Có ba trách nhiệm tách biệt:

- `UserDetailsService`: đọc `UserDetails`, hash và trạng thái user.
- `PasswordEncoder`: tạo hash, đối chiếu và xác định upgrade cần thiết.
- `UserDetailsPasswordService`: **lưu** hash mới vào kho tài khoản.

`upgradeEncoding` không tự gọi SQL, không tự ghi file hoặc cập nhật account. Nếu tạo `BCryptPasswordEncoder(12)` nhưng không cung cấp writer, hệ thống có thể tiếp tục dùng stored hash cost 8 trong một thời gian dài dù xác thực vẫn thành công.

### Bảo vệ password sau khi xác thực

`ProviderManager` có cơ chế xóa credentials khỏi `Authentication` khi hoàn tất. Đừng cố tìm raw password từ principal hoặc session để rehash sau login; lúc đó credential có thể đã bị xóa theo thiết kế. Provider có điểm xử lý hợp lệ trước khi dữ liệu nhạy cảm bị loại bỏ.

Nếu `UserDetailsService` có cache cùng một instance mutable chứa hash, việc xóa credential có thể ảnh hưởng dữ liệu cache. Cần xem cách copy UserDetails và chiến lược invalidation. Không tắt credential erasure một cách rộng rãi chỉ để sửa lỗi cache.

## 9. Ví dụ Java 17+ chạy được: upgrade BCrypt 08 lên 12

Ví dụ sử dụng Spring Boot Servlet, Spring MVC/Web và Spring Security. Hãy tạo project từ Spring Initializr với **Spring Web** và **Spring Security**, Java 17+, phiên bản Spring Boot còn được hỗ trợ tương thích với API. Nếu dùng Spring Boot 4, các starter Maven tương ứng có thể là `spring-boot-starter-webmvc` và `spring-boot-starter-security`.

Demo tạo user `an` với BCrypt cost 8 để giả lập hash cũ. Encoder hiện tại dùng cost 12. Một lần đăng nhập sai **không** thay đổi hash. Một lần đăng nhập đúng sẽ khiến `DaoAuthenticationProvider` gọi `UserDetailsPasswordService` và lưu hash có cost 12 trong in-memory store.

Tạo **`src/main/java/com/example/passworddemo/PasswordUpgradeApplication.java`**:

```java
package com.example.passworddemo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PasswordUpgradeApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordUpgradeApplication.class, args);
    }

    @Bean
    CommandLineRunner verifyUpgrade(
            InMemoryUserDetailsManager accounts,
            PasswordEncoder currentEncoder,
            AuthenticationManager manager) {

        return args -> {
            String before =
                    accounts.loadUserByUsername("an").getPassword();

            System.out.println("cost-before=" + before.substring(4, 6));
            System.out.println("upgrade-before="
                    + currentEncoder.upgradeEncoding(before));

            try {
                manager.authenticate(
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                "an", "wrong"));
            } catch (BadCredentialsException ex) {
                System.out.println("wrong-password=REJECTED");
            }

            String afterFailure =
                    accounts.loadUserByUsername("an").getPassword();
            System.out.println("unchanged-after-failure="
                    + before.equals(afterFailure));

            Authentication success = manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "an", "demo-password"));

            String afterSuccess =
                    accounts.loadUserByUsername("an").getPassword();
            System.out.println("authenticated="
                    + success.isAuthenticated());
            System.out.println("cost-after="
                    + afterSuccess.substring(4, 6));
            System.out.println("upgrade-after="
                    + currentEncoder.upgradeEncoding(afterSuccess));
            System.out.println("matches-after="
                    + currentEncoder.matches(
                            "demo-password", afterSuccess));
        };
    }
}

@Configuration(proxyBeanMethods = false)
class PasswordSecurityConfig {

    @Bean
    PasswordEncoder currentPasswordEncoder() {
        return new BCryptPasswordEncoder(12);
    }

    @Bean
    InMemoryUserDetailsManager accounts() {
        PasswordEncoder old = new BCryptPasswordEncoder(8);
        UserDetails account = User.withUsername("an")
                .password(old.encode("demo-password"))
                .authorities("ROLE_USER")
                .build();
        return new InMemoryUserDetailsManager(account);
    }

    @Bean
    AuthenticationManager authenticationManager(
            InMemoryUserDetailsManager accounts,
            PasswordEncoder currentPasswordEncoder) {

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(accounts);
        provider.setPasswordEncoder(currentPasswordEncoder);

        // Có writer thì provider mới lưu được hash đã nâng cấp.
        provider.setUserDetailsPasswordService(accounts);

        return new ProviderManager(provider);
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

@RestController
class PasswordDemoController {

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

### Phân tích code

**User cũ:** `accounts()` dùng `new BCryptPasswordEncoder(8)` để tạo hash cũ. Trong production, **không tạo hash mới có cost thấp** chỉ để nâng cấp; đây là dữ liệu thử nghiệm.

**Encoder mới:** `currentPasswordEncoder()` dùng cost 12. BCrypt hash mang thông tin cost/salt nên encoder mới có thể xác minh hash cost 8 và đánh dấu cần upgrade.

**Dao provider:** `provider.setPasswordEncoder(currentPasswordEncoder)` dùng encoder hiện tại để xác minh. `provider.setUserDetailsPasswordService(accounts)` cho phép cập nhật hash. `InMemoryUserDetailsManager` implement cả `UserDetailsService` và `UserDetailsPasswordService`, phù hợp với demo nhưng không lưu bền vững.

**Manager:** `ProviderManager` được cấu hình trên `HttpSecurity`, giúp bộ lọc HTTP Basic sử dụng provider đã chọn. `CommandLineRunner` gọi manager trực tiếp để in kết quả upgrade trước khi người học thử HTTP.

**Kiểm tra thất bại:** sau password `wrong`, hash từ store được so sánh lại với giá trị cũ, phải giữ nguyên.

**Kiểm tra thành công:** sau password `demo-password`, hash cost mới là 12, `upgradeEncoding` trả false, password vẫn matches. Khi thử đăng nhập nhiều lần sau đó, không cần rehash mỗi request nữa nếu hash đã đúng policy.

### Cách chạy và stdout

Từ thư mục gốc dự án Maven có wrapper:

```bash
./mvnw spring-boot:run
```

Hoặc Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell dùng `.\mvnw.cmd spring-boot:run` hoặc `.\gradlew.bat bootRun`. Không chạy bằng `javac` đơn thuần nếu không có classpath của Spring Boot/Security.

Khi khởi động, các dòng do `CommandLineRunner` in ra (ngoài log Spring Boot) dự kiến là:

```text
cost-before=08
upgrade-before=true
wrong-password=REJECTED
unchanged-after-failure=true
authenticated=true
cost-after=12
upgrade-after=false
matches-after=true
```

Các chuỗi cost là kết quả được đọc từ BCrypt hash trong demo, không phải hash literal cố định. Salt thay đổi giữa các lần tạo hash; thời gian tính toán phụ thuộc CPU và strength.

Thử tiếp HTTP Basic:

```bash
curl -s http://localhost:8080/public/ping
curl -s -u an:demo-password http://localhost:8080/me
curl -i -u an:wrong http://localhost:8080/me
curl -i http://localhost:8080/me
```

Hai dòng thành công trả body:

```text
pong
principal=an
```

Hai request không hợp lệ thường nhận **HTTP 401** với Basic challenge theo cấu hình. Body và header lỗi có thể khác nhau theo version/framework. HTTP Basic chỉ dùng Base64 để truyền credential; ở production phải bật HTTPS. Không sử dụng password demo cho tài khoản thật.

**Lưu ý:** chương trình dùng in-memory store. Sau restart, tài khoản lại có hash cost 8 từ dữ liệu khởi tạo; database production cần một implementation ghi bền vững.

## 10. Viết UserDetailsPasswordService cho kho nghiệp vụ hoặc JPA

Trong production, rehash phải ghi vào bảng account/identity store theo một **hợp đồng nhất quán**:

```text
trusted account + newEncodedPassword
    |
    v
UserDetailsPasswordService.updatePassword(...)
    |
    +-- xác định account theo ID tin cậy
    +-- kiểm tra hash/version vẫn là bản đã xác thực
    +-- update password_hash bằng newEncodedPassword
    +-- audit/transaction phù hợp
    |
    v
trả UserDetails với hash mới
```

Writer nhận **encoded password do provider cung cấp**, không được gọi `encode` lần nữa.

Một mảnh thiết kế (cần các class domain/repository và import tương ứng; **không phải file Java độc lập**):

```java
@Service
class PersistentPasswordUpgradeService
        implements UserDetailsPasswordService {

    private final AccountRepository repository;

    PersistentPasswordUpgradeService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    @Transactional
    public UserDetails updatePassword(
            UserDetails user, String newEncodedPassword) {

        DomainUserDetails principal = (DomainUserDetails) user;
        Account account = repository.findById(principal.accountId())
                .orElseThrow();

        if (!account.getPasswordHash().equals(user.getPassword())) {
            throw new IllegalStateException(
                    "Password was changed concurrently");
        }

        account.setPasswordHash(newEncodedPassword);
        return principal.withEncodedPassword(newEncodedPassword);
    }
}
```

Phép kiểm tra hash trong code chỉ diễn đạt **ý định**, chưa đủ bảo vệ race condition ở DB. Khi triển khai thật, cần row locking/optimistic version hoặc compare-and-swap trong transaction đúng isolation. Không dùng một câu lệnh read-then-write thiếu concurrency guard để bảo đảm an toàn.

### Race condition với reset password

Có thể xảy ra:

1. Request login L đọc hash cũ H1 và xác minh password cũ.
2. Request reset R ghi password mới dưới dạng H2.
3. L muốn nâng cấp H1 thành H3 từ password cũ.
4. Nếu L ghi đè H2, password cũ có thể lại được chấp nhận, phá hỏng reset.

Một cập nhật có điều kiện có thể mang dạng:

```sql
UPDATE accounts
SET password_hash = :new_encoded_hash,
    version = version + 1
WHERE id = :account_id
  AND password_hash = :old_encoded_hash;
```

Đây là SQL minh họa; transaction và parameter phụ thuộc hệ quản trị DB. Kiểm tra số hàng bị update: nếu 0 thì source hash đã thay đổi và cần xử lý xung đột, không được ghi đè mù quáng. Nếu password hash nằm trong JPA entity versioned, cần thiết kế optimistic locking và xử lý retry phù hợp.

### Không double-encode

Sai:

```java
// SAI: newEncodedPassword đã là hash do provider tạo.
account.setPasswordHash(encoder.encode(newEncodedPassword));
```

Làm vậy băm **chính hash**, khiến password thô không còn matches. Chỉ dùng `encode(rawNewPassword)` khi bạn thật sự có một plaintext password mới từ luồng đăng ký/đổi/reset hợp lệ.

## 11. Migration nhiều phiên bản và thuật toán

Khi doanh nghiệp tăng cost BCrypt hoặc chuyển từ hash legacy sang format mới, cần trả lời:

- Hash cũ có được phép xác minh nữa không?
- Format/id của từng stored hash được xác định thế nào?
- Encoder nào sẽ tạo hash mới?
- Có lúc nào người dùng cung cấp raw password đã được xác minh hợp lệ?
- Có writer an toàn chống ghi đè reset đồng thời không?
- Cần theo dõi bao nhiêu phần trăm account đã chuyển?
- Người dùng không login trong nhiều tháng được xử lý ra sao?

**Rehash on successful login** là chiến lược phổ biến: sau xác thực hợp lệ, nếu hash cũ bị đánh dấu cần upgrade, encode lại raw password bằng policy mới rồi ghi. Ưu điểm là không buộc người dùng đổi password ngay; hạn chế là account không đăng nhập vẫn giữ hash cũ.

**Password reset có xác minh** phù hợp khi thuật toán cũ không còn được cho phép hoặc tài khoản không cung cấp raw password trong thời gian dài. Người dùng chọn password mới và server encode theo policy hiện hành, không cần biết plaintext cũ.

### Không biến migration thành fallback nguy hiểm

Đặc biệt tránh:

- Chấp nhận password raw vì thiếu prefix id.
- Thêm `NoOpPasswordEncoder` như đường fallback mặc định trên production.
- Gọi `encode(oldHash)` rồi lưu – đó là hash của hash.
- Dùng một hàm `matches` tự chế chấp nhận cả password thô và hash bằng so sánh string tùy tiện.
- Nuốt mọi exception của encoder rồi coi đó là login thành công hoặc tự cấp role.
- Log raw password, password hash hoặc Basic Authorization header.

Nếu storage có các hash không prefix, cần phân loại format thực tế, kiểm thử và lập migration thêm prefix hoặc decoder legacy giới hạn. Không được suy diễn format từ một vài ký tự rồi cho phép mọi thuật toán không rõ nguồn gốc.

## 12. Hiệu năng, an toàn và thời gian nâng cấp

BCrypt cost tăng theo cấp số nhân. Tăng cost từ 8 lên 12 có thể làm mỗi lần `matches` hay `encode` tiêu tốn CPU hơn rõ rệt. Nếu mọi request Basic phải kiểm tra password, tác động có thể lớn hơn so với login session ít lần. Cần benchmark trên hệ thống thực:

- Độ trễ trung bình và p95/p99 của authentication.
- CPU khi nhiều request login đồng thời.
- Khả năng bị request flood và công suất kiểm tra hash.
- Số account còn hash cũ cần rehash mỗi ngày.
- Rollout theo nhóm, theo dõi lỗi user và database writes.
- Chiến lược dừng nâng cấp nếu dịch vụ trở nên quá tải.

Chọn thuật toán/cost phù hợp tiêu chuẩn bảo mật và hardware hiện hành, không chọn mức cao nhất chỉ vì có thể cấu hình.

BCrypt cũng có giới hạn về số byte input được xử lý theo thuật toán; với password dài và Unicode, cần chính sách validation/normalization được cân nhắc kỹ. Không tự cắt password trước khi băm một cách âm thầm làm nhiều password khác nhau trở nên tương đương. Có thể xem xét thuật toán khác như Argon2 theo yêu cầu hệ thống và khả năng vận hành.

## 13. Những lỗi phổ biến

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Lưu plaintext password | Rò bí mật khi DB/backup bị lộ | `encode` bằng encoder an toàn |
| Hash nhanh `SHA-256(password)` thuần | Dễ brute-force offline hơn password hashing chuyên dụng | BCrypt/Argon2/scrypt phù hợp |
| So sánh `encode(raw).equals(stored)` | Salt thường khiến chuỗi khác | `matches(raw, stored)` |
| Đảo tham số `matches` | Raw và stored hash không cùng kiểu | Raw trước, encoded sau |
| `matches=true` là cấp quyền ngay | Bỏ qua account status và authorization | Để provider/security chain quyết định |
| Gọi `upgradeEncoding` để kiểm tra password | Nó không nhận raw password | `matches` trước |
| Tưởng `upgradeEncoding=true` là DB đã đổi | Chỉ là boolean | Writer/`UserDetailsPasswordService` |
| Rehash password nhập sai | Có thể đổi credential trái phép | Chỉ sau xác thực hợp lệ |
| Dùng writer không có transaction/concurrency guard | Ghi đè password reset | Version/compare-and-swap |
| Encode hai lần `newEncodedPassword` | Password không còn matches | Lưu encoded mới trực tiếp |
| Chuyển sang delegating quên `{id}` | Hash cũ không được nhận diện | Format migration có kiểm soát |
| Fallback plaintext cho id lạ | Tạo đường bypass | Chặn input không hỗ trợ |
| Tắt credential erasure để cache hoạt động | Credential tồn tại lâu hơn trong memory | Sửa cách copy/cache UserDetails |
| Trông chờ JWT tự rehash password | Token không mang raw password | Login bằng password/reset hợp lệ |
| Không benchmark cost | Tăng CPU và nguy cơ DoS | Benchmark và giới hạn tải |
| Log password/hash | Rò thông tin nhạy cảm | Log trạng thái và policy version tối thiểu |

## 14. Ma trận kiểm thử đề xuất

**Kiểm thử encode và matches:**

1. Hash vừa encode phải matches raw password đúng.
2. Password khác phải không matches.
3. Hai lần BCrypt encode cùng raw có thể khác kết quả vì salt; không viết test so sánh hash literal.
4. Hash malformed/id không được hỗ trợ phải xử lý đúng chính sách.
5. Password dài và Unicode phải được test theo chính sách sản phẩm.

**Kiểm thử upgradeEncoding:**

1. Stored cost 8 với encoder cost 12 → `true`.
2. Stored cost 12 với encoder cost 12 → `false`.
3. Custom encoder không override có thể luôn trả `false`.
4. Delegating id cũ và id mới được xử lý đúng mapping.
5. Gọi `upgradeEncoding` một mình không ghi DB.

**Kiểm thử provider/writer:**

1. Password sai **không update** hash.
2. Login đúng với hash cũ gọi writer đúng một lần theo policy.
3. Login đúng lần tiếp theo sau upgrade không cập nhật lại hash không cần thiết.
4. Hash sau upgrade vẫn matches raw password.
5. Writer lỗi không được báo “nâng cấp thành công”.
6. Password reset đồng thời không bị login migration ghi đè.
7. Session/cache/replica không tiếp tục dùng hash sai sau update.
8. Kiểm tra HTTP 401/403 và các điều kiện account status riêng.

### Mảnh kiểm thử Java

```java
PasswordEncoder oldEncoder = new BCryptPasswordEncoder(8);
PasswordEncoder newEncoder = new BCryptPasswordEncoder(12);

String oldHash = oldEncoder.encode("demo");
boolean valid = newEncoder.matches("demo", oldHash);
boolean invalid = newEncoder.matches("wrong", oldHash);
boolean needsUpgrade = newEncoder.upgradeEncoding(oldHash);

String newHash = newEncoder.encode("demo");
boolean noFurtherUpgrade = !newEncoder.upgradeEncoding(newHash);

System.out.println(valid);
System.out.println(invalid);
System.out.println(needsUpgrade);
System.out.println(noFurtherUpgrade);
```

Đây là **mảnh mã trong method** có import tương ứng, không phải lớp có `main` độc lập. Output:

```text
true
false
true
true
```

Boolean là dữ liệu có thể kiểm chứng; hash thực tế không cố định vì salt.

## 15. Tình huống thực tế: cần quyết định thế nào?

### Tài khoản bị khóa nhưng password đúng

`matches` có thể trả true nếu tự gọi, nhưng provider phải từ chối login khi tài khoản khóa. Không nên nâng cấp password hash qua một login bị từ chối bởi chính sách bảo mật.

### User đổi password

Đổi password dùng `encode(rawNewPassword)` rồi lưu hash mới sau khi xác minh quyền thực hiện. Không cần nâng cấp hash cũ nếu bạn đang thay bằng password mới được băm đúng policy.

### SSO/OIDC login

Nếu ứng dụng không sở hữu password của user, không giả lập `PasswordEncoder` trên ID token. Identity Provider mới là nơi chịu trách nhiệm băm/lưu password của họ.

### Thay đổi cấu hình encoder

Không chỉ đổi strength của bean rồi giả định mọi hash cũ sẽ được ghi lại. Cần kiểm tra `upgradeEncoding` implementation, cung cấp writer, theo dõi tỷ lệ migration và có đường xử lý account chưa quay lại login.

### Nhiều instance và database replicas

Một instance có thể đọc hash cũ từ replica trong khi instance khác đã update hash mới. Cần chính sách consistency/cache/replica propagation, đặc biệt khi rehash và reset password cùng diễn ra. Writer phải tránh lost update.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Hai lần `encode("abc")` với BCrypt có thể cho chuỗi khác nhau không?  
**Trả lời:** Có, vì salt ngẫu nhiên. Cả hai vẫn có thể matches cùng password.

**Câu 2.** Vì sao `encoder.encode(raw).equals(stored)` sai?  
**Trả lời:** Salt làm encoding mới thường khác; phải dùng `matches(raw, stored)`.

**Câu 3.** `upgradeEncoding(oldHash) == true` có nghĩa password đúng không?  
**Trả lời:** Không. Nó chỉ nhìn hash và policy encoder.

**Câu 4.** Sau `upgradeEncoding=true`, database đã có hash mới chưa?  
**Trả lời:** Chưa. Cần một luồng rehash có raw password hợp lệ và writer lưu hash mới.

**Câu 5.** BCrypt stored cost 8 có xác minh được bằng encoder cost 12 không?  
**Trả lời:** Có, nếu hash BCrypt hợp lệ; cost được lưu trong hash.

**Câu 6.** Provider có được rehash password sai rồi lưu không?  
**Trả lời:** Không. Đó có thể thành lỗi cho phép attacker thay credential của user.

**Câu 7.** `UserDetailsPasswordService.updatePassword` nhận gì?  
**Trả lời:** Nhận password **đã encoded**, không phải raw plaintext.

**Câu 8.** Khi thay password trong request reset, còn cần upgrade hash cũ không?  
**Trả lời:** Không, vì password mới đã được encode bằng policy hiện tại.

**Câu 9.** Vì sao dùng delegating có thể làm BCrypt hash không prefix không khớp nữa?  
**Trả lời:** Vì decoder chọn theo `{id}`; hash không id cần migration hoặc mapping legacy có kiểm soát.

**Câu 10.** Làm sao chống nâng cấp hash cũ ghi đè password reset mới?  
**Trả lời:** Cập nhật có điều kiện theo hash/version cũ và transaction/optimistic locking phù hợp.

**Câu 11.** Vì sao không chọn BCrypt cost cao nhất có thể?  
**Trả lời:** Vì tăng độ trễ, CPU và rủi ro nghẽn/DoS; phải benchmark theo hạ tầng thật.

**Câu 12.** `upgradeEncoding=false` có nghĩa hash an toàn tuyệt đối không?  
**Trả lời:** Không. Nó chỉ thể hiện quyết định của encoder hiện tại, không thay thế review bảo mật định kỳ.

## Kết luận

Ba phương thức của `PasswordEncoder` không thể hoán đổi:

- **`encode`** tạo hash mới để lưu.
- **`matches`** kiểm tra mật khẩu được trình bày với hash đã lưu.
- **`upgradeEncoding`** chỉ đánh giá liệu hash lưu có nên được thay thế bằng hash mới hay không.

Trong Spring Security, `DaoAuthenticationProvider` là nơi kiểm tra credential trong luồng username/password; nếu muốn tự động rehash sau authentication thành công, cần cấu hình `UserDetailsPasswordService` cập nhật hash bền vững và an toàn trước concurrent password reset. Đổi cost BCrypt hoặc thuật toán mà không thiết kế writer và dữ liệu legacy sẽ không đủ để bảo đảm migration.

**Ghi nhớ:** *`matches` trả lời password có khớp; `upgradeEncoding` trả lời hash có cũ; `encode` tạo hash mới. Chỉ một luồng xác thực hợp lệ và writer an toàn mới được lưu hash nâng cấp.*

### Tài liệu tham khảo chính thức

- [Spring Security — PasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security — BCryptPasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html)
- [Spring Security — Password Storage / DelegatingPasswordEncoder](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — UserDetailsPasswordService API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html)
- [Spring Security — InMemoryUserDetailsManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/provisioning/InMemoryUserDetailsManager.html)
