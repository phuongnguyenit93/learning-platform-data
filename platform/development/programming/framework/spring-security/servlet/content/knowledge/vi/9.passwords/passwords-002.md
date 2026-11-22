# encode, matches và upgradeEncoding trong vòng đời mật khẩu

## 1. Mục tiêu và bối cảnh

Trong ứng dụng **Spring Security sử dụng Servlet stack**, mật khẩu trải qua các giai đoạn: người dùng đăng ký hoặc đặt lại mật khẩu; server tạo password hash để lưu; mỗi lần xác thực username/password, server kiểm tra password người dùng cung cấp; và khi chính sách về thuật toán hoặc độ mạnh thay đổi, ứng dụng có thể nâng cấp hash cũ tại một lần đăng nhập hợp lệ.

Giao diện **org.springframework.security.crypto.password.PasswordEncoder** cung cấp ba thao tác cốt lõi:

1. **encode(rawPassword)**: biến mật khẩu người dùng nhập thành **encoded password/hash** có thể lưu trữ. Với bcrypt, chuỗi kết quả có salt và thông số chi phí; hai lần encode cùng mật khẩu thường tạo chuỗi khác nhau.
2. **matches(rawPassword, encodedPassword)**: xác minh mật khẩu nhập vào có khớp hash lưu hay không. Không giải mã hash, không cần so sánh hai lần encode bằng equals.
3. **upgradeEncoding(encodedPassword)**: trả về boolean cho biết **hash đã lưu có cần nâng cấp** theo chính sách hiện tại của encoder hay không. Phương thức **không** tự xác thực, băm lại hay ghi dữ liệu vào database.

Bài học giúp bạn hiểu chính xác ba phương thức, liên kết chúng với **DaoAuthenticationProvider** và **UserDetailsPasswordService**, rồi tự chạy ví dụ Java 17+/Spring Boot 3.3.13 có bcrypt cost cũ/mới, test các trường hợp login đúng, login sai, nâng cấp hash và tránh ghi đè mật khẩu mới do race condition.

**Phạm vi:** Spring Security Servlet, trọng tâm xác thực username/password. Đăng nhập bằng OAuth2, JWT và các AuthenticationProvider tùy biến có cách xử lý credential khác; không áp cơ chế này nguyên xi lên mọi loại Authentication.

## 2. Raw password, password hash và salt

| Thành phần | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| Raw password | Bí mật người dùng nhập | Chỉ xử lý tạm thời qua HTTPS, không lưu plaintext |
| Encoded password/hash | Giá trị PasswordEncoder.encode trả về | Lưu ở kho dữ liệu được bảo vệ |
| Salt | Dữ liệu ngẫu nhiên để hai tài khoản có cùng password không tạo hash giống nhau | Thường nằm trong chuỗi bcrypt hash; không phải bí mật thay thế password |
| Work factor/cost | Tham số kiểm soát công sức tính hash | Chọn sau benchmark, đánh giá độ trễ và tải |
| PasswordEncoder | Thành phần encode/matches/upgradeEncoding | Phải tương thích định dạng hash trong store |
| UserDetails.getPassword() | Giá trị hash dùng để xác thực qua provider | Không chứa raw password trong production |

**PasswordEncoder không có decode().** Hash mật khẩu phù hợp là cơ chế một chiều. Khi người dùng quên mật khẩu, ứng dụng phải xác minh quyền đặt lại rồi **encode mật khẩu mới**, chứ không khôi phục mật khẩu cũ từ hash.

**Bcrypt không cho kết quả cố định với cùng raw password.** Salt ngẫu nhiên khiến hai chuỗi hash thường khác nhau. Vì vậy không dùng biểu thức encoder.encode(raw).equals(storedHash) làm bước xác thực.

## 3. Hợp đồng của PasswordEncoder

Ba phương thức trọng tâm, viết theo cấu trúc API:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);

    boolean matches(CharSequence rawPassword, String encodedPassword);

    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

Đây là **minh họa chữ ký** của interface có sẵn trong Spring Security; không tạo lại file interface này trong dự án thực hành.

### 3.1. encode: chỉ sử dụng với mật khẩu thô cần lưu

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder(10);

String first = encoder.encode("a-password");
String second = encoder.encode("a-password");

boolean firstMatches = encoder.matches("a-password", first);
boolean secondMatches = encoder.matches("a-password", second);
~~~

Hai biến first và second thường khác nhau; **firstMatches = true** và **secondMatches = true**. Không công bố hash trả về trong API response, log hoặc exception message.

Thời điểm gọi encode thường là: đăng ký account, đổi password, reset password sau xác minh quyền, hoặc nâng cấp hash khi đã chứng minh raw password đúng ở login. Với updatePassword do DaoAuthenticationProvider gọi, **newPassword đã là hash**, không encode lại lần nữa.

### 3.2. matches: kiểm tra credential

~~~java
String storedHash = encoder.encode("a-password");

boolean correct = encoder.matches("a-password", storedHash);
boolean incorrect = encoder.matches("bad-password", storedHash);
~~~

Kết quả xác định:

~~~text
correct = true
incorrect = false
~~~

matches dùng raw password làm đối số đầu và **hash từ kho dữ liệu** làm đối số thứ hai. Nó cần một encoder tương thích với định dạng hash. Nếu database lưu chuỗi có prefix **{bcrypt}** nhưng bạn dùng BCryptPasswordEncoder thuần để đọc, hãy kiểm tra lại cấu hình: BCryptPasswordEncoder trực tiếp mong hash bcrypt trần, còn DelegatingPasswordEncoder hiểu các prefix {id}.

Khi mật khẩu sai, không được cập nhật hash, không được coi upgradeEncoding là bằng chứng xác thực. Trước khi cho phép truy cập, provider còn có thể kiểm tra account enabled/locked/expired và các quy tắc khác.

### 3.3. upgradeEncoding: chỉ là tín hiệu chính sách

~~~java
boolean shouldUpgrade = encoder.upgradeEncoding(storedHash);
~~~

- **true:** encoder nhận thấy hash cũ nên được thay bằng biểu diễn mới theo policy hiện tại.
- **false:** encoder không yêu cầu nâng cấp; không suy ra mật khẩu đúng hay sai.
- Không truyền raw password vào upgradeEncoding.
- Không có bất kỳ tác dụng phụ nào lên database chỉ vì gọi phương thức này.
- PasswordEncoder có default method trả false; các implementation có thể đánh giá nâng cấp theo cách riêng.

Đặc biệt **BCryptPasswordEncoder** có thể so work factor trong hash với strength được cấu hình. Nếu hash cũ có cost thấp hơn strength hiện tại thì nên upgrade. Nếu cost bằng hoặc cao hơn, thường không đề xuất hạ cấp.

## 4. Vòng đời mật khẩu và quyết định cập nhật hash

~~~text
[Đăng ký / đổi / reset mật khẩu]
    rawPassword mới
        |
        v
    kiểm tra policy, xác minh quyền đặt/đổi
        |
        v
    PasswordEncoder.encode(rawPassword)
        |
        v
    INSERT hoặc UPDATE password_hash

[Đăng nhập]
    rawPassword từ request
        |
        v
    UserDetailsService lấy storedHash
        |
        v
    PasswordEncoder.matches(rawPassword, storedHash)
        |
        +-- false --> xác thực thất bại, KHÔNG UPDATE hash
        |
        +-- true --> xác thực thành công qua provider phù hợp
                        |
                        v
                upgradeEncoding(storedHash)?
                        |
                        +-- false --> giữ hash hiện tại
                        |
                        +-- true --> encode(rawPassword đã được xác thực)
                                           |
                                           v
                                    lưu hash mới bằng update an toàn
                        |
                        v
                Authentication hợp lệ cho request
~~~

Sơ đồ trình bày **các quyết định khái niệm**, không phải toàn bộ internal call stack. Provider còn kiểm tra user state, phát sự kiện và tạo Authentication theo cấu hình cụ thể. Điều kiện quan trọng là **không có nâng cấp hash dựa trên một mật khẩu chưa được xác thực**.

| Tình huống | encode | matches | upgradeEncoding | Thao tác lưu |
| --- | --- | --- | --- | --- |
| Tạo tài khoản | Có | Không nhất thiết | Không | INSERT encoded password |
| Đăng nhập sai | Không | Trả false | Không cần | Không |
| Đăng nhập đúng, hash hiện tại | Không | Trả true | Trả false | Không |
| Đăng nhập đúng, hash cũ | Có, với raw đã xác minh | Trả true | Trả true | UPDATE hash mới |
| Đổi mật khẩu | Có, với mật khẩu mới | Có thể cần kiểm tra mật khẩu cũ | Không phải điều kiện chính | UPDATE hash mới |
| Reset mật khẩu | Có, sau khi token/xác minh hợp lệ | Không thể kiểm tra mật khẩu đã quên | Không | UPDATE + thu hồi token reset |

**Không thể rehash toàn bộ database chỉ từ stored hash cũ.** Password hash một chiều không cung cấp raw password cần để tính hash đúng theo chính sách mới. Chiến lược thường dùng là **opportunistic upgrade** khi người dùng login thành công, hoặc yêu cầu reset cho account lâu không đăng nhập.

## 5. BCryptPasswordEncoder: tại sao hash cũ vẫn matches được?

BCryptPasswordEncoder thường có thể nhận hash đã lưu với cost cũ và kiểm tra raw password bằng thông số có trong hash, dù instance hiện tại được cấu hình strength mới.

~~~java
PasswordEncoder oldEncoder = new BCryptPasswordEncoder(6);
PasswordEncoder currentEncoder = new BCryptPasswordEncoder(10);

String oldHash = oldEncoder.encode("secret-123");

boolean valid = currentEncoder.matches("secret-123", oldHash);
boolean needsUpgrade = currentEncoder.upgradeEncoding(oldHash);
~~~

Kỳ vọng trong tình huống này:

~~~text
valid = true
needsUpgrade = true
~~~

Strength 6 chỉ dùng để minh họa sự khác biệt; **không phải khuyến nghị production**.

Một chuỗi bcrypt thường có cấu trúc:

~~~text
$2a$10$...salt-and-hash...
     ^^
     cost
~~~

Có thể gặp tiền tố 2a, 2b hoặc 2y tùy nguồn/phiên bản. Thông số cost là một phần của hash, không cần lưu một cột cost tách riêng cho mục tiêu xác minh.

Nếu encoder hiện tại là BCrypt(10):

- Hash bcrypt cost 6: **matches** mật khẩu đúng = true; **upgradeEncoding** = true.
- Hash cost 10: matches đúng = true; upgradeEncoding = false.
- Hash cost 12: matches đúng = true; upgradeEncoding thông thường = false, vì không hạ cost chỉ để khớp giá trị hiện tại.
- Hash hỏng hoặc không thuộc bcrypt: không thể dựa vào matches/upgradeEncoding để suy luận an toàn. Cần kiểm tra định dạng và chính sách chuyển đổi.

**Lựa chọn strength:** tăng cost làm cả login thành công và thất bại tốn CPU hơn. Benchmark trên hạ tầng thực, cân bằng độ trễ với khả năng chống brute force offline và rủi ro DoS, không tăng tùy tiện mà không đo tải.

## 6. DaoAuthenticationProvider tự nâng cấp khi nào?

**DaoAuthenticationProvider** là AuthenticationProvider dùng **UserDetailsService** và **PasswordEncoder** cho username/password. Khi cấu hình đúng, nó có thể tự thực hiện nâng cấp hash:

1. UserDetailsService tìm user, trả encoded password hiện tại.
2. DaoAuthenticationProvider gọi PasswordEncoder.matches(raw, storedHash).
3. Sau khi xác thực thành công, provider kiểm tra encoder.upgradeEncoding(storedHash).
4. Khi upgrade cần thiết **và có UserDetailsPasswordService**, provider gọi PasswordEncoder.encode(raw password đã được chứng minh đúng).
5. Provider gọi UserDetailsPasswordService.updatePassword(user, newEncodedHash).
6. Provider tạo kết quả Authentication; cơ chế ProviderManager thường xóa credentials khỏi kết quả sau xác thực.

Giao diện lưu hash mới:

~~~java
package org.springframework.security.core.userdetails;

public interface UserDetailsPasswordService {
    UserDetails updatePassword(UserDetails user, String newPassword);
}
~~~

**newPassword trong updatePassword là encoded hash**, không phải raw password. Implementation nào gọi encode(newPassword) lần thứ hai sẽ lưu **hash của hash**, làm mật khẩu gốc không còn khớp khi đăng nhập tiếp.

Không phải cứ có PasswordEncoder bean là tính năng update tự hoạt động. Cần **gắn UserDetailsPasswordService đúng provider** hoặc thiết kế cơ chế tương đương. Đối với AuthenticationProvider tùy biến, tự chịu trách nhiệm bảo đảm kiểm tra mật khẩu thành công trước khi nâng cấp, đồng thời giữ transaction và tính nhất quán dữ liệu.

### Race condition cực kỳ quan trọng

Request A đăng nhập bằng mật khẩu cũ. Trong lúc A chưa cập nhật hash, request B đổi/reset mật khẩu thành công và lưu hash mới. Nếu A UPDATE không có điều kiện, A có thể ghi **hash upgraded của mật khẩu cũ** lên trên mật khẩu mới, khiến hành động reset của B bị ghi đè.

Với database, dùng **optimistic locking/row version**, hoặc UPDATE có điều kiện **WHERE password_hash = old_hash** (và account version phù hợp), rồi xử lý trường hợp 0 bản ghi được cập nhật. Những hệ thống nhạy cảm có thể cần kiểm tra lại trạng thái tài khoản và thu hồi phiên/token. Không hiểu rằng một compare-and-swap đơn giản đã giải quyết toàn bộ vấn đề thu hồi quyền sau password reset.

## 7. Ví dụ Spring Boot runnable: nâng bcrypt cost 6 lên 10

Dự án sau dùng **Java 17+**, **Spring Boot 3.3.13**, Maven và HTTP Basic stateless. Đây là môi trường học tập cục bộ: người dùng/mật khẩu mẫu không được đưa vào production.

Ba tài khoản:

- **legacy / legacy-pass**: ban đầu hash bcrypt cost 6; login đúng sẽ nâng thành cost 10.
- **current / current-pass**: hash cost 10; login đúng không cần update.
- **badlogin / badlogin-pass**: hash cost 6; test gửi password sai để xác minh hash không bị đổi.

Cây tệp:

~~~text
password-lifecycle-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/passworddemo/
    │   ├── PasswordLifecycleApplication.java
    │   ├── SecurityConfig.java
    │   ├── InMemoryAccountService.java
    │   └── AccountController.java
    └── test/java/com/example/passworddemo/
        └── PasswordLifecycleTest.java
~~~

### 7.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>password-lifecycle-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Không tự khai phiên bản Spring Security riêng; Spring Boot parent quản lý những phiên bản tương thích trong nhánh phát hành.

### 7.2. PasswordLifecycleApplication.java

~~~java
package com.example.passworddemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasswordLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordLifecycleApplication.class, args);
    }
}
~~~

Các class đặt dưới cùng package com.example.passworddemo để Spring Boot component scan tìm thấy cấu hình và controller.

### 7.3. InMemoryAccountService.java

Ta dùng **ConcurrentHashMap** làm kho lưu mô phỏng và implement cả UserDetailsService lẫn UserDetailsPasswordService. Đặc biệt, **UserDetails trả về cho provider là bản sao**: tránh để ProviderManager.eraseCredentials làm thay đổi trực tiếp object đang nằm trong Map.

~~~java
package com.example.passworddemo;

import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class InMemoryAccountService
        implements UserDetailsService, UserDetailsPasswordService {

    private final Map<String, UserDetails> accounts =
        new ConcurrentHashMap<>();

    public InMemoryAccountService(
            PasswordEncoder oldEncoder,
            PasswordEncoder currentEncoder) {

        accounts.put("legacy", User.withUsername("legacy")
            .password(oldEncoder.encode("legacy-pass"))
            .roles("USER")
            .build());

        accounts.put("current", User.withUsername("current")
            .password(currentEncoder.encode("current-pass"))
            .roles("USER")
            .build());

        accounts.put("badlogin", User.withUsername("badlogin")
            .password(oldEncoder.encode("badlogin-pass"))
            .roles("USER")
            .build());
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        UserDetails stored = accounts.get(username);

        if (stored == null) {
            throw new UsernameNotFoundException("User not found");
        }

        // Không trả cùng instance mutable nằm trong cache/store.
        return User.withUserDetails(stored).build();
    }

    @Override
    public UserDetails updatePassword(
            UserDetails user, String newPassword) {

        // newPassword ĐÃ là hash do DaoAuthenticationProvider encode.
        UserDetails result = accounts.compute(
            user.getUsername(),
            (username, current) -> {
                if (current == null) {
                    throw new UsernameNotFoundException("User not found");
                }

                // Không ghi đè nếu hash bị thay đổi giữa lúc tải và update.
                if (!Objects.equals(
                        current.getPassword(), user.getPassword())) {
                    return current;
                }

                return User.withUserDetails(current)
                    .password(newPassword)
                    .build();
            }
        );

        // Bản trả về cũng tách khỏi object trong Map.
        return User.withUserDetails(result).build();
    }

    // Chỉ dành cho unit/integration test cùng package.
    String hashForTest(String username) {
        UserDetails stored = accounts.get(username);
        if (stored == null) {
            throw new UsernameNotFoundException("User not found");
        }
        return stored.getPassword();
    }
}
~~~

**Điểm cần hiểu:**

- Map giữ **hash**, không giữ raw password.
- BCrypt(6) và BCrypt(10) chỉ được dùng để seed dữ liệu thử nghiệm.
- loadUserByUsername tạo bản sao để principal có thể bị xóa credentials mà không làm hỏng record gốc.
- updatePassword không encode thêm lần nữa. Nó chỉ nhận hash mới và ghi lại hash.
- Map.compute giúp tránh lost update đơn giản khi hash gốc thay đổi đồng thời, nhưng không thay thế optimistic lock/version, transaction hay chính sách thu hồi trong production.
- Method hashForTest có phạm vi package-private, không có HTTP endpoint tiết lộ password hash.

Nếu dùng database và entity JPA, không để entity đang quản lý và object principal bị mutate/erase credentials là cùng instance khi việc đó gây side effect khó kiểm soát. Cần thiết kế boundary rõ giữa dữ liệu lưu trữ, UserDetails được xác thực và cache.

### 7.4. SecurityConfig.java

~~~java
package com.example.passworddemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
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
    InMemoryAccountService accountService(PasswordEncoder currentEncoder) {
        return new InMemoryAccountService(
            new BCryptPasswordEncoder(6),
            currentEncoder
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            InMemoryAccountService accounts,
            PasswordEncoder encoder) throws Exception {

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider();
        provider.setUserDetailsService(accounts);
        provider.setPasswordEncoder(encoder);
        provider.setUserDetailsPasswordService(accounts);

        http
            .authenticationProvider(provider)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .requestMatchers("/me").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }
}
~~~

**Ba mắt xích then chốt:**

1. PasswordEncoder hiện tại là BCrypt(10), nên hash BCrypt cost 6 **vẫn matches**, đồng thời **upgradeEncoding trả true**.
2. DaoAuthenticationProvider được cấu hình tường minh với **UserDetailsService**, **PasswordEncoder** và **UserDetailsPasswordService**, nhờ vậy login thành công có thể tự persist hash mới.
3. HTTP Basic với SessionCreationPolicy.STATELESS khiến từng curl request xác thực độc lập, phù hợp để quan sát một lần upgrade và những lần sau không upgrade nữa.

Ví dụ cố ý không disable CSRF. Các endpoint thử nghiệm chỉ dùng GET, không cần CSRF token. Khi thêm POST/PUT/DELETE, hãy đánh giá CSRF theo mô hình client; browser có thể tự gửi HTTP Basic credentials đã ghi nhớ. Dùng HTTPS, giới hạn tốc độ login và quản lý dữ liệu user thật khi triển khai production.

### 7.5. AccountController.java

~~~java
package com.example.passworddemo;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public-ok");
    }

    @GetMapping("/me")
    public Map<String, String> profile(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }
}
~~~

Controller không trả raw password, hash, Authentication object hoặc Authorization header. Password hash chỉ được kiểm tra nội bộ qua test; không tạo một endpoint trả hash cho client.

## 8. Chạy ví dụ và thử các trường hợp

Tại thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Dùng terminal khác chạy curl; trên một số phiên bản Windows PowerShell cần gọi **curl.exe** để tránh alias.

**Công khai:**

~~~bash
curl -i http://localhost:8080/public
~~~

Kỳ vọng HTTP **200**, JSON có message = "public-ok".

**Không gửi credentials:**

~~~bash
curl -i http://localhost:8080/me
~~~

Kỳ vọng HTTP **401** vì endpoint cần xác thực.

**Legacy sai mật khẩu:**

~~~bash
curl -i -u legacy:wrong-pass http://localhost:8080/me
~~~

Kỳ vọng **401**. Stored hash cost 6 không được upgrade do chưa có xác thực thành công.

**Legacy đúng mật khẩu:**

~~~bash
curl -i -u legacy:legacy-pass http://localhost:8080/me
~~~

Kỳ vọng **200**, JSON có username = "legacy". Lần login đầu dùng matches để xác minh hash cost 6, upgradeEncoding thấy cần nâng, DaoAuthenticationProvider gọi UserDetailsPasswordService để lưu hash cost 10. Gọi lệnh này lần hai vẫn 200, nhưng hash đã đạt cost 10 nên không cần ghi lại.

**Current đúng mật khẩu:**

~~~bash
curl -i -u current:current-pass http://localhost:8080/me
~~~

Kỳ vọng **200** và không cập nhật hash vì cost vốn là 10.

| Request | Status dự kiến | Tác động hash |
| --- | --- | --- |
| GET /public không credentials | 200 | Không có |
| GET /me thiếu credentials | 401 | Không có |
| GET /me legacy sai mật khẩu | 401 | Không có |
| GET /me legacy đúng lần đầu | 200 | Cost 6 → cost 10 |
| GET /me legacy đúng lần thứ hai | 200 | Giữ hash cost 10 |
| GET /me current đúng | 200 | Không thay đổi |

Không thể chứng minh hash đã cập nhật chỉ từ status 200. Phần test sau đọc hash trực tiếp từ store nội bộ; tuyệt đối không đưa hash vào JSON trả về người dùng.

## 9. Test tích hợp: xác minh đủ ba API và bước lưu

Tạo **src/test/java/com/example/passworddemo/PasswordLifecycleTest.java**:

~~~java
package com.example.passworddemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordLifecycleTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    InMemoryAccountService accounts;

    @Test
    void correctLegacyLoginUpgradesAndPersistsHash() throws Exception {
        String before = accounts.hashForTest("legacy");

        assertEquals(6, bcryptCost(before));
        assertTrue(encoder.matches("legacy-pass", before));
        assertTrue(encoder.upgradeEncoding(before));

        mvc.perform(get("/me").with(httpBasic("legacy", "legacy-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("legacy"));

        String after = accounts.hashForTest("legacy");
        assertNotEquals(before, after);
        assertEquals(10, bcryptCost(after));
        assertTrue(encoder.matches("legacy-pass", after));
        assertFalse(encoder.upgradeEncoding(after));

        mvc.perform(get("/me").with(httpBasic("legacy", "legacy-pass")))
            .andExpect(status().isOk());

        assertEquals(after, accounts.hashForTest("legacy"));
    }

    @Test
    void badPasswordDoesNotTriggerUpgrade() throws Exception {
        String before = accounts.hashForTest("badlogin");
        assertEquals(6, bcryptCost(before));

        mvc.perform(get("/me").with(httpBasic("badlogin", "wrong-pass")))
            .andExpect(status().isUnauthorized());

        assertEquals(before, accounts.hashForTest("badlogin"));
        assertTrue(encoder.upgradeEncoding(before));
    }

    @Test
    void CurrentHashNeedsNoUpgrade() throws Exception {
        String before = accounts.hashForTest("current");
        assertEquals(10, bcryptCost(before));
        assertFalse(encoder.upgradeEncoding(before));

        mvc.perform(get("/me").with(httpBasic("current", "current-pass")))
            .andExpect(status().isOk());

        assertEquals(before, accounts.hashForTest("current"));
    }

    private static int bcryptCost(String encodedHash) {
        // Bcrypt hash trần: $2a$10$...
        return Integer.parseInt(encodedHash.split("\\$")[2]);
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Ba test dùng user riêng nên không phụ thuộc thứ tự chạy. Lưu ý test tên CurrentHashNeedsNoUpgrade có chữ cái viết hoa ở đầu method vẫn là method Java hợp lệ; kiểu đặt tên lowerCamelCase thường được khuyến nghị để nhất quán.

**Kỳ vọng quan trọng:**

- Test legacy xác nhận hash đã thay đổi, cost từ 6 thành 10, matches vẫn đúng, upgradeEncoding sau update là false, và lần login thứ hai không ghi lại hash không cần thiết.
- Test badlogin xác nhận password sai → 401, hash vẫn giữ nguyên dù hash ấy chưa đạt strength mới.
- Test current xác nhận hash đủ chuẩn không bị ghi lại trên mỗi lần xác thực.

**Vì sao cần MockMvc?** Unit test gọi encoder.upgradeEncoding đơn thuần chỉ biết câu trả lời true/false. Test qua HTTP Basic và SecurityFilterChain chứng minh thêm rằng DaoAuthenticationProvider **thực sự** gọi updatePassword sau login thành công. Với production, nên test cùng DB thật/transaction và trường hợp password change/reset chạy đồng thời.

## 10. DelegatingPasswordEncoder và định dạng {id}

Một hệ thống có thể đã trải qua nhiều thế hệ thuật toán lưu mật khẩu: bcrypt, PBKDF2, scrypt, Argon2. Spring Security có **DelegatingPasswordEncoder** để điều phối các encoder theo ID.

Định dạng ví dụ:

~~~text
{bcrypt}$2a$10$...
{pbkdf2}...
{scrypt}...
{argon2}...
~~~

Đây là **các dạng minh họa**, không phải hash đầy đủ có thể dùng để login. ID giữa { và } giúp xác định encoder phù hợp; chuỗi hash sau ID phải được tạo đúng theo thuật toán ấy.

Cấu hình từ factory:

~~~java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

Cần import org.springframework.security.crypto.factory.PasswordEncoderFactories và PasswordEncoder trong class đang sử dụng. Đừng hardcode giả định factory luôn dùng một cost cụ thể: policy thay đổi theo phiên bản và cấu hình.

- **encode(raw)** dùng encoder được chọn để tạo hash mới, thường có prefix {id}.
- **matches(raw, stored)** chọn encoder từ ID của hash đã lưu.
- **upgradeEncoding(stored)** có thể xét cả việc ID cũ khác ID hiện tại, cũng như chính sách nâng cấp trong encoder được chọn.

Nếu dữ liệu lịch sử lưu bcrypt **không có {bcrypt}**, không thể mặc nhiên dùng DelegatingPasswordEncoder mới mà dữ liệu luôn khớp; phải thiết kế migration/fallback đúng định dạng đã được xác minh. Không bật NoOpPasswordEncoder như một fallback rộng để làm biến mất lỗi login, vì có thể khiến hệ thống chấp nhận mật khẩu không được băm đúng chuẩn.

### Khi thay thuật toán, có rehash tất cả ngay được không?

Không nếu chỉ có password hash cũ và không có raw password. Cần chuyển đổi sau lần xác thực hợp lệ hoặc yêu cầu reset theo kế hoạch. Có thể theo dõi tỷ lệ hash cũ đã được nâng cấp qua metric an toàn, không xuất raw password hoặc hash vào log.

## 11. Lỗi thường gặp và cách tránh

### Lỗi 1: encode hai lần

UserDetailsPasswordService nhận **newPassword đã là hash** từ provider. Nếu gọi encoder.encode(newPassword) rồi lưu, bạn tạo hash của hash. Mật khẩu gốc không thể xác thực như trước.

### Lỗi 2: gọi encode rồi so equals

Bcrypt salt ngẫu nhiên nên encoder.encode(raw) có thể khác storedHash dù raw đúng. Luôn dùng matches(raw, storedHash).

### Lỗi 3: gọi upgradeEncoding và tin rằng DB tự cập nhật

upgradeEncoding là một truy vấn boolean. Phải có provider/ứng dụng thực hiện encode và persist hash mới khi xác thực đã thành công.

### Lỗi 4: rehash một hash cũ như mật khẩu thô

Tạo encode(storedHash) không nâng cấp password hash đúng nghĩa; nó biến **chuỗi hash cũ** thành input mới, khiến raw password của user không còn khớp. Không thể khôi phục raw password từ hash một chiều.

### Lỗi 5: sai encoder hoặc định dạng

BCryptPasswordEncoder thuần không phải DelegatingPasswordEncoder; hash có {bcrypt} prefix không giống hash bcrypt trần. Hãy xác định định dạng đã lưu và xử lý migration có kiểm soát.

### Lỗi 6: nâng cost nhưng không benchmark

Tăng strength có thể gây quá tải CPU ở endpoint login. Đo độ trễ trên phần cứng thực, tính đến request song song, rate limiting và khả năng chống DoS.

### Lỗi 7: cache UserDetails bị erase

Trong flow username/password, ProviderManager thường xóa credentials khỏi kết quả Authentication. Nếu principal dùng **cùng object UserDetails mutable** đang nằm trong cache, thao tác erase có thể làm mất password hash trong cache. Trả bản sao độc lập và có chiến lược cache invalidation.

### Lỗi 8: nâng cấp sau mật khẩu sai

Không được cập nhật password khi matches chưa thành công. Việc biết hash “lạc hậu” không chứng minh người gọi biết mật khẩu đúng.

### Lỗi 9: ghi đè reset password do race condition

Rehash từ login đang chạy không được ghi đè password hash mới đã lưu bởi một phiên reset. Dùng optimistic locking/conditional update theo giá trị cũ, kiểm soát trạng thái account và transaction.

### Lỗi 10: lưu hash đã upgrade nhưng vẫn dùng cache cũ

Nếu UserDetailsService/UserCache dùng cache, phải evict/refresh dữ liệu sau khi lưu hash mới. Nếu không, request khác có thể tiếp tục đọc bản hash cũ hoặc authority/account flags đã lỗi thời.

### Lỗi 11: dùng password hash trong business API

Không trả raw password, password hash, Authorization header hay toàn bộ Authentication vào API response. Đừng tạo endpoint chỉ để debug hash, thay bằng bài kiểm thử nội bộ có quyền kiểm soát.

## 12. Phân biệt upgrade, đổi và reset mật khẩu

**Upgrade hash:** người dùng vẫn giữ **cùng raw password**. Sau lần login đúng, ứng dụng tạo một encoded representation mới theo policy. Đối với những account không login, hash có thể vẫn cũ cho đến khi có migration/reset.

**Đổi mật khẩu:** người dùng yêu cầu dùng **raw password mới**. Quy trình phải kiểm tra quyền, có thể yêu cầu password cũ/step-up auth, sau đó encode password mới và cập nhật atomically, invalidate cache, cân nhắc thu hồi session/token.

**Reset mật khẩu:** người dùng không biết password cũ. Ứng dụng cần xác minh reset token/chứng cứ phù hợp, kiểm tra single-use và expiration, rồi encode password mới và thu hồi token reset. Không dùng upgradeEncoding làm cơ chế reset.

**Password history:** nếu cần kiểm tra password mới trùng mật khẩu cũ, phải dùng matches(newRaw, storedHistoricalHash) thay vì so hai hash bcrypt bằng equals. Lưu password history tăng mức nhạy cảm của dữ liệu, cần retention và kiểm soát riêng.

## 13. Chẩn đoán khi hash không nâng cấp

Làm theo trình tự:

1. **Encoder hiện tại là gì?** Có đúng BCrypt(10) hay cấu hình khác?
2. **Hash trong database là dạng nào?** bcrypt trần, {bcrypt}, {argon2}, hay chuỗi bị cắt?
3. **matches có trả true không?** Nếu false, đừng thử upgrade bằng cách khác để vượt qua xác thực.
4. **upgradeEncoding trả gì?** Cost/ID hiện tại có thực sự thấp hơn policy?
5. **AuthenticationProvider có phải DaoAuthenticationProvider đang được sử dụng không?** Có nhiều provider/chain?
6. **Đã set UserDetailsPasswordService cho provider chưa?** Nếu không, không có nơi persist từ flow tự động.
7. **updatePassword có ghi newEncodedHash trực tiếp không?** Tránh double encoding.
8. **Update có thành công không?** Kiểm tra transaction, optimistic locking, conditional update, user không còn tồn tại.
9. **Cache được invalidate/refresh chưa?** Có dùng UserDetailsService cache hoặc UserCache với object dùng chung?
10. **Request kế tiếp có thật sự xác thực lại không?** Form login session có thể không đi qua provider mỗi GET; HTTP Basic stateless dễ quan sát hơn.
11. **Có lỗi account status không?** User bị khóa, disabled hoặc expired có thể khiến xác thực không thành công dù matches đúng.
12. **Có ghi log bí mật không?** Đừng log raw password, hash hoặc Authorization header chỉ để chẩn đoán.

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra |
| --- | --- | --- |
| Đúng mật khẩu nhưng hash cost cũ không đổi | Thiếu UserDetailsPasswordService | Gắn service đúng provider |
| Login đúng, upgradeEncoding false | Hash đã đủ strength hoặc ID đúng | Kiểm tra encoder thực tế |
| Sau lần upgrade không thể login | Double encoding hoặc ghi sai hash | updatePassword và matches |
| Người dùng đổi password mà password cũ vẫn dùng được | Cache stale hoặc UPDATE upgrade ghi đè reset | Invalidation, version/CAS |
| Login sau chậm hơn nhiều | Cost mới cao và thiếu capacity | Benchmark, rate limiting |
| Mọi người dùng lỗi sau đổi encoder | Format {id} không tương thích | Delegating/migration |
| Login lần đầu được, lần hai lỗi | UserDetails cache bị erase | Defensive copy |
| Request sai password lại sửa hash | Logic upgrade chạy trước matches | Chỉ nâng sau xác thực thành công |

## 14. Bài tập tự kiểm tra

### A. Ba API

Một user có hash bcrypt cost 6, encoder hiện tại strength 10. Người dùng cung cấp đúng password. matches và upgradeEncoding lần lượt trả gì? Chỉ gọi upgradeEncoding có cập nhật DB không?

**Đáp án:** matches = true; upgradeEncoding = true; DB **không tự đổi**. Cần encode raw password đã chứng minh đúng và persist hash mới.

### B. Vì sao hai hash khác nhau?

Hai lần encode cùng password bằng bcrypt cho chuỗi khác nhau. Điều đó có đồng nghĩa hai password khác nhau?

**Đáp án:** Không. Salt ngẫu nhiên khiến hash khác, nhưng matches với cùng raw password vẫn có thể true cho cả hai.

### C. Hash cũ không có raw password

Một cron job muốn chuyển toàn bộ hash cost 6 sang 10 chỉ bằng dữ liệu hash cũ. Có hợp lệ không?

**Đáp án:** Không thể tính hash đúng cho password gốc nếu không biết raw password. Nên upgrade khi login hợp lệ hoặc yêu cầu reset qua cơ chế an toàn.

### D. Thiếu wiring

Bỏ provider.setUserDetailsPasswordService(accounts) trong SecurityConfig, điều gì thay đổi?

**Đáp án:** DaoAuthenticationProvider không còn dịch vụ cập nhật encoded hash qua flow tự động; legacy vẫn có thể matches nhưng hash không được persist. Test legacy phát hiện lỗi.

### E. Tình huống đồng thời

Login A đã matches password cũ. Reset B đổi password. A tiếp tục UPDATE hash rehash từ password cũ lên DB. Lỗi gì?

**Đáp án:** A có thể ghi đè reset B, làm sống lại password cũ. Dùng conditional UPDATE/optimistic lock, version và xử lý account state.

### F. Tránh double encoding

Trong UserDetailsPasswordService.updatePassword(user, newPassword), có nên gọi encoder.encode(newPassword) nữa không?

**Đáp án:** Không. newPassword là encoded string do provider tạo.

### G. Đổi thuật toán

Vì sao BCryptPasswordEncoder thuần không phù hợp để matches cùng lúc {bcrypt} và {argon2}?

**Đáp án:** Nó chỉ hiểu bcrypt hash trần. Dùng DelegatingPasswordEncoder với ID/encoder được cấu hình và migration policy phù hợp.

## 15. Checklist áp dụng

- [ ] Đăng ký/đổi/reset: chỉ lưu **encode(raw)**, không lưu plaintext.
- [ ] Login: dùng **matches(raw, storedHash)**, không so hai encoded strings.
- [ ] Hiểu **upgradeEncoding(encoded)** chỉ đánh giá policy, không xác thực hoặc ghi DB.
- [ ] Chỉ upgrade cùng password sau lần xác thực **thành công**.
- [ ] Nếu dùng DaoAuthenticationProvider tự upgrade, đã gắn UserDetailsPasswordService và PasswordEncoder đúng cách.
- [ ] updatePassword lưu hash đã được encode, không double encode.
- [ ] Đã benchmark cost hiện tại và lên kế hoạch migration hợp lý.
- [ ] Định dạng hash trong store phù hợp với BCrypt hay DelegatingPasswordEncoder và {id} prefix.
- [ ] Đã bảo vệ concurrent password reset/change bằng version/CAS/transaction.
- [ ] UserDetails/cache không chia sẻ object mutable bị erase; có invalidation.
- [ ] Đã test login cũ/mới, đúng/sai password, request lặp lại, password reset race.
- [ ] Không log/raw-return password, hash, token, Authorization header hoặc cookie nhạy cảm.
- [ ] Hệ thống có HTTPS, rate limiting, CSRF policy phù hợp và cơ chế reset an toàn.

**Ghi nhớ:** **encode** tạo hash để lưu, **matches** kiểm tra password mới nhập với hash đang lưu, **upgradeEncoding** cho biết hash đó có nên được hiện đại hóa hay không. Khi tích hợp đúng **DaoAuthenticationProvider + UserDetailsPasswordService**, ứng dụng có thể nâng cấp hash **trong lúc login hợp lệ** mà không đổi mật khẩu người dùng, không sửa dữ liệu khi login sai, và không ghi đè một mật khẩu mới vừa được đặt trong quá trình thay đổi đồng thời.
