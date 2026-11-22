# PasswordEncoder.encode và matches trong Spring Security

## 1. Bài toán thực tế: tạo mật khẩu lưu được mà không lưu mật khẩu gốc

Ứng dụng Java có màn hình đăng ký, đổi mật khẩu và đăng nhập. Ở thời điểm đăng ký, người dùng gửi một mật khẩu gốc (**raw password**). Hệ thống cần lưu một giá trị có thể kiểm tra được ở những lần đăng nhập sau mà không ghi nguyên mật khẩu xuống database.

Spring Security cung cấp interface **PasswordEncoder**. Hai phương thức quan trọng nhất là:

- **encode(rawPassword):** tạo một **encoded password** để lưu vào kho credentials. Với những encoder dành cho password storage như BCrypt, kết quả là hash một chiều có salt và work factor.
- **matches(rawPassword, encodedPassword):** xác minh mật khẩu người dùng vừa nhập có tương ứng với encoded password đã lưu hay không. Phương thức trả boolean trong trường hợp bình thường; một implementation có thể báo lỗi định dạng/algorithm nếu hash lưu không hợp lệ.

Quy trình:

~~~text
ĐĂNG KÝ / ĐỔI MẬT KHẨU
password người dùng nhập
      |
      v
PasswordEncoder.encode(rawPassword)
      |
      v
password_hash trong database

ĐĂNG NHẬP
password người dùng nhập + username
      |                        |
      |                        v
      |                 Đọc password_hash từ DB
      |                        |
      +------------+-----------+
                   |
                   v
PasswordEncoder.matches(rawPassword, storedHash)
                   |
           +-------+-------+
           |               |
         true            false
           |               |
  tiếp tục xác thực   từ chối credentials
  và kiểm tra trạng thái
~~~

**PasswordEncoder dùng “encode” trong tên API, nhưng đối với BCrypt/Argon2/PBKDF2/scrypt, đây là xử lý password bằng hàm dẫn xuất khóa/hash có chi phí, không phải mã hóa có thể giải mã trở lại.** Hệ thống không cần khôi phục plaintext để đăng nhập. Nó chỉ cần kiểm tra mật khẩu ứng viên với hash đã lưu.

Phạm vi bài: **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**. Dùng Spring Security Crypto có thể thực hành mà không cần chạy server; ví dụ đầy đủ bên dưới minh họa cả HTTP Basic, UserDetailsService, PasswordEncoder và MockMvc. Version cụ thể ở sản phẩm thật cần còn được hỗ trợ và có bản vá bảo mật.

### Kết quả học tập

Sau bài này, bạn sẽ giải thích được:

1. encode và matches nhận/trả giá trị nào; thứ tự tham số chính xác.
2. Vì sao hai lần encode cùng mật khẩu bằng BCrypt thường cho hai chuỗi khác nhau.
3. Salt, work factor và hash một chiều ảnh hưởng tới lưu và xác minh mật khẩu ra sao.
4. Khi nào dùng BCryptPasswordEncoder, khi nào dùng DelegatingPasswordEncoder.
5. Prefix **{bcrypt}** có vai trò gì và tại sao một hash thiếu prefix có thể gây lỗi.
6. Vai trò PasswordEncoder trong đăng ký, login, đổi mật khẩu và hash migration.
7. Cách dùng UserDetailsService/DaoAuthenticationProvider thay vì so mật khẩu thủ công trong Controller.
8. Những lỗi phổ biến: hash hai lần, đảo thứ tự matches, so sánh String.equals, dùng {noop}, truncate cột database, lộ hash vào JSON/log.
9. Viết test xác thực đúng/sai cùng một ứng dụng Spring Boot có thể chạy.
10. Đọc tín hiệu upgradeEncoding và lên kế hoạch đổi cost/algorithm mà không làm hỏng tài khoản.

## 2. Contract của PasswordEncoder

Interface Spring Security có ba phương thức quan trọng:

~~~java
public interface PasswordEncoder {

    String encode(CharSequence rawPassword);

    boolean matches(CharSequence rawPassword,
                    String encodedPassword);

    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

Đây là **hình dạng contract lược giản dùng để giải thích**, không phải file cần định nghĩa lại trong ứng dụng. Tùy version, chữ ký và annotation nullability có thể khác; hãy import **org.springframework.security.crypto.password.PasswordEncoder** thật.

| Phương thức | Đầu vào | Đầu ra | Dùng khi nào |
| --- | --- | --- | --- |
| **encode** | Raw password do người dùng cung cấp | Chuỗi có thể lưu để đối chiếu về sau | Đăng ký, đổi/reset password, nâng cấp hash sau khi đã kiểm chứng |
| **matches** | Raw password ứng viên; encoded password từ kho lưu | true/false khi đối chiếu hợp lệ | Đăng nhập, kiểm tra mật khẩu hiện tại trước khi đổi |
| **upgradeEncoding** | Encoded password đã lưu | boolean chỉ báo nên dùng dạng encoding mới | Đánh giá migration cost/algorithm, kết hợp cơ chế cập nhật hash |

### 2.1. Thứ tự matches phải nhớ

~~~java
boolean valid = encoder.matches(
    rawPasswordFromLoginRequest,
    encodedPasswordFromDatabase
);
~~~

**Đối số đầu tiên là raw password; đối số thứ hai là hash/encoded password đã lưu.** Đảo ngược sẽ không xác minh đúng. Tham số thứ hai không phải một “mật khẩu thứ hai”.

Trong quá trình login dùng DaoAuthenticationProvider, Spring Security thực hiện đối chiếu này. Một Controller thông thường **không cần tự đọc password hash và gọi matches** nếu bạn đã cấu hình đúng cơ chế username/password.

### 2.2. encode không bảo đảm đầu ra cố định

Với BCryptPasswordEncoder, có salt ngẫu nhiên cho mỗi lần tạo hash. Vì thế:

~~~java
String first = encoder.encode("sample-pass");
String second = encoder.encode("sample-pass");

boolean firstMatches = encoder.matches("sample-pass", first);
boolean secondMatches = encoder.matches("sample-pass", second);
~~~

Kết quả **firstMatches=true** và **secondMatches=true**. **first** và **second** thường khác nhau do salt. Không viết unit test so chuỗi hash tạo mới với một literal hash cố định trừ khi bạn thật sự đang kiểm thử một test vector được kiểm soát.

Hai kết quả có thể tình cờ trùng nếu salt ngẫu nhiên trùng, nhưng xác suất rất thấp; không xây correctness của logic ứng dụng trên việc hai hash chắc chắn khác nhau 100% trong mọi lần chạy.

## 3. Hash một chiều, salt và work factor

### 3.1. Tại sao không lưu plaintext?

Nếu bảng user có cột password chứa trực tiếp chuỗi do người dùng nhập, một lỗi lộ DB hoặc backup sẽ để lộ ngay credential có thể dùng ở nhiều nơi.

Thay vào đó, password hashing là một phép tính có chủ đích **khó đảo ngược**. Khi người dùng đăng nhập, hệ thống không “decrypt” hash mà thực hiện kiểm chứng trên ứng viên mới nhập bằng thuật toán và tham số tương ứng.

**Hash không làm bí mật trở nên vô hại.** Nếu kẻ tấn công có hash, họ vẫn có thể thử đoán password ngoại tuyến. Do đó cần thuật toán chuyên cho password, tham số cost phù hợp, quyền DB hạn chế, bảo vệ backup, và chính sách chống mật khẩu yếu.

### 3.2. Salt dùng để làm gì?

Salt là giá trị ngẫu nhiên đi cùng mỗi hash. Với BCrypt, salt được lưu dưới dạng một phần chuỗi encoded password. Cùng raw password nhưng salt khác nhau tạo hash khác nhau. Điều đó làm khó việc so sánh các user có cùng password và hạn chế hiệu quả của những bảng hash tính sẵn.

**Salt không phải secret** theo nghĩa cần giấu riêng để phép kiểm tra hoạt động. Password hash + salt vẫn cần bảo vệ như dữ liệu credential nhạy cảm. Không tự nghĩ ra cách lưu salt riêng hoặc dùng username cố định làm salt thay cho thuật toán chuẩn.

### 3.3. Work factor/cost

BCryptPasswordEncoder có tham số **strength** (log rounds). Cost càng cao thì việc hash và matches càng tốn công, giúp làm chậm brute force ngoại tuyến. Nhưng cost quá cao làm tăng latency đăng nhập, tải CPU và nguy cơ DoS nếu endpoint không giới hạn tốc độ.

Ví dụ:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder(12);
~~~

Đây là snippet tạo encoder, dùng import cần thiết và **không phải một Spring Boot file độc lập**. Chọn cost qua đo đạc hardware và profile tải, không mặc định rằng 12 luôn hợp lý cho mọi sản phẩm. Trong Spring Security 6.3.x, constructor BCryptPasswordEncoder() mặc định sử dụng strength 10; cấu hình cụ thể có thể thay đổi theo version và wrapper.

### 3.4. Cần lưu đủ toàn bộ chuỗi hash

Không cắt bỏ phần salt, prefix hoặc cost. Nếu database column quá ngắn, hash bị truncate, dẫn đến login đúng password cũng thất bại.

Một trường dạng **VARCHAR(255)** thường đủ cho nhiều định dạng phổ biến như BCrypt có {bcrypt} prefix, nhưng phải đối chiếu với thuật toán thực tế, nhu cầu nâng cấp và giới hạn dữ liệu của database. Không có một độ dài cố định đúng cho mọi encoder hay mọi phiên bản.

## 4. BCryptPasswordEncoder: ví dụ căn bản

BCrypt là một password hashing algorithm có salt/work factor. Class **BCryptPasswordEncoder** trong Spring Security Crypto implement PasswordEncoder.

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();

String storedHash = encoder.encode("hello-123");

boolean correct = encoder.matches("hello-123", storedHash);
boolean incorrect = encoder.matches("wrong-123", storedHash);
~~~

**correct=true**, **incorrect=false**. Hash cụ thể phụ thuộc salt, nên không liệt kê một chuỗi hash cố định làm stdout.

### 4.1. Cấu trúc chuỗi BCrypt

Một hash BCrypt thường bắt đầu với dạng như:

~~~text
$2a$10$...
~~~

Trong đó version $2a$ (hoặc biến thể được hỗ trợ) và cost 10 nằm trong metadata; phần tiếp theo mang salt cùng dữ liệu hash. Chuỗi BCrypt thông dụng dài 60 ký tự. Dấu ba chấm chỉ là **mô tả cấu trúc**, không phải một encoded password thật để đưa vào matches.

BCryptPasswordEncoder trực tiếp tạo chuỗi **$2a$...**, thường **không có prefix {bcrypt}**. Nếu bạn tự chuyển sang DelegatingPasswordEncoder thì phải xử lý định dạng lưu theo quy ước của Delegating.

### 4.2. BCrypt có giới hạn độ dài đầu vào

BCrypt truyền thống chỉ xét khoảng **72 bytes** đầu vào password. Đây là giới hạn byte, khác số ký tự Unicode (chữ tiếng Việt có thể chiếm nhiều byte trong UTF-8). Một số implementation hiện đại có cách xử lý input dài riêng; vì vậy cần xác minh behavior của đúng library/version.

Trong thiết kế password policy, **không lặng lẽ cắt mật khẩu của người dùng để “cho vừa”**. Hãy chọn chính sách độ dài theo byte và thuật toán, tránh hai password dài khác nhau bị coi như giống nhau vì truncation, cân nhắc dùng Argon2id/scrypt/PBKDF2 phù hợp khi cần và kiểm thử Unicode thực tế.

Không tự pre-hash bằng SHA-256 rồi đưa vào BCrypt nếu chưa có thiết kế được review; việc ghép thuật toán/encoding có thể tạo rủi ro tương thích và bảo mật mới.

### 4.3. Không dùng encoder.encode để so trực tiếp với hash cũ

Cách sai:

~~~java
boolean wrongWay = encoder.encode(inputPassword)
    .equals(hashFromDatabase);
~~~

Với BCrypt, encode tạo salt mới, nên hai chuỗi thường khác nhau dù raw password chính xác. Cách đúng:

~~~java
boolean rightWay = encoder.matches(
    inputPassword, hashFromDatabase
);
~~~

Cũng không gọi **encoder.matches(encoder.encode(inputPassword), storedHash)**. Đối số đầu tiên phải là **raw password**, không phải hash mới.

## 5. DelegatingPasswordEncoder: chọn thuật toán theo prefix

Ứng dụng tồn tại nhiều năm có thể gặp hash từ những thời kỳ khác nhau. Chỉ dùng một BCryptPasswordEncoder trực tiếp khiến việc thay đổi thuật toán hoặc xử lý hash legacy cần nhiều mã đặc biệt.

**DelegatingPasswordEncoder** là wrapper chọn encoder dựa vào **id** lưu cùng hash. Spring Security cung cấp factory:

~~~java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

Với cấu hình factory tiêu chuẩn, encoded password mới thường có dạng:

~~~text
{bcrypt}$2a$10$...
~~~

**{bcrypt}** là id của encoder; phần sau là BCrypt hash với salt/cost. Prefix này phục vụ định tuyến thuật toán, không phải một lớp hash bổ sung.

### 5.1. Format chung

~~~text
{id}encodedPassword
~~~

Ví dụ các id có thể gồm bcrypt, pbkdf2, scrypt hoặc argon2 tùy version/configuration. Không mặc định các id cũ hoặc thuật toán yếu đều được phép **encode mật khẩu mới**; việc hỗ trợ đọc legacy chỉ nên nằm trong kế hoạch migration có kiểm soát.

### 5.2. encode và matches hoạt động ra sao?

Khi gọi encode:

1. DelegatingPasswordEncoder chọn encoder ghi mới theo **idForEncode**, với factory tiêu chuẩn là bcrypt.
2. Encoder bên trong tạo BCrypt hash có salt.
3. Wrapper ghép prefix **{bcrypt}** ở đầu và trả chuỗi để lưu.

Khi gọi matches:

1. Wrapper đọc id từ encoded password đã lưu.
2. Tìm encoder tương ứng trong map id → PasswordEncoder.
3. Chuyển **raw password** và phần encoded password cho encoder đó kiểm chứng.
4. Trả true/false nếu định dạng và thuật toán được hỗ trợ.

### 5.3. Lỗi thường gặp: There is no PasswordEncoder mapped for the id null

Nếu dùng DelegatingPasswordEncoder mà database chứa hash BCrypt **không có prefix**, ví dụ chỉ bắt đầu với $2a$, wrapper không biết id nào xử lý. Mặc định nó có thể ném **IllegalArgumentException** với thông điệp dạng “There is no PasswordEncoder mapped for the id null”.

Nguyên nhân không nhất thiết là password sai. Đây thường là **không tương thích định dạng lưu và PasswordEncoder đang cấu hình**.

Cách xử lý phụ thuộc nguồn dữ liệu:

- Nếu đã chắc chắn tất cả bản ghi legacy được tạo bằng BCrypt và không có prefix, có thể lập migration dữ liệu **thêm literal {bcrypt} vào đầu hash hiện có**. Việc thêm metadata id không yêu cầu biết raw password, vì bản thân BCrypt hash không đổi.
- Nếu kho có nhiều thuật toán, cần phân loại dữ liệu và migration plan có xác minh; không tự gắn {bcrypt} cho tất cả.
- DelegatingPasswordEncoder có API **setDefaultPasswordEncoderForMatches** để dùng encoder dự phòng khi id chưa nhận dạng. Chỉ dùng có kiểm soát cho trường hợp migration đã xác minh, không fallback sang NoOp hoặc âm thầm chấp nhận mọi chuỗi không hợp lệ.
- Sau migration, kiểm thử user cũ/new, column length, hash format, rollback, và theo dõi tỷ lệ authentication error.

**Không khắc phục bằng cách xóa {bcrypt} của hash mới một cách tùy tiện** nếu hệ thống đang dùng DelegatingPasswordEncoder. Cần một quy ước lưu thống nhất.

### 5.4. So sánh hai lựa chọn

| Đặc điểm | BCryptPasswordEncoder | DelegatingPasswordEncoder |
| --- | --- | --- |
| Thuật toán ghi mới | BCrypt trực tiếp | Theo idForEncode, factory thường chọn bcrypt |
| Chuỗi lưu điển hình | $2a$... | {bcrypt}$2a$... |
| Kiểm tra legacy formats khác | Không tự định tuyến | Có thể map nhiều id/encoder |
| Nâng cấp algorithm | Cần kế hoạch migration riêng | Có nền tảng chọn hash mới và match hash cũ |
| Nguy cơ khi cấu hình sai | Cost/format, prefix không phù hợp | Unknown id, fallback không an toàn |
| Phù hợp | Hệ thống dùng một format BCrypt đã kiểm soát | Hệ thống muốn version hóa hash và migration có tổ chức |

Trong ví dụ ứng dụng phần 7, ta chọn **PasswordEncoderFactories.createDelegatingPasswordEncoder()** và dùng chính bean đó để tạo hash cho user. Nhờ vậy encode và matches cùng hiểu prefix/algorithm.

## 6. Luồng đăng ký, đổi mật khẩu và đăng nhập

### 6.1. Đăng ký tài khoản

Service nhận raw password sau khi áp chính sách đầu vào, hash một lần rồi lưu:

~~~java
String encoded = passwordEncoder.encode(rawPassword);
jdbcTemplate.update(
    "INSERT INTO app_users(username, password_hash) VALUES (?, ?)",
    normalizedUsername, encoded
);
~~~

Đây là snippet thuộc service có PasswordEncoder, JdbcTemplate và username đã được kiểm tra; **chưa phải endpoint đăng ký hoàn chỉnh**. Ứng dụng thật phải có unique constraint, validation, transaction, verify email/phone theo yêu cầu, chống abuse và trả response an toàn.

Database lưu **encoded**, không lưu raw password. Không gửi hash về client như một “receipt” khi đăng ký.

### 6.2. Đăng nhập

DaoAuthenticationProvider lấy hash từ UserDetailsService:

~~~text
login input (raw password)
    |
    v
DaoAuthenticationProvider
    |
    +-- UserDetailsService: load user with encoded password
    |
    +-- PasswordEncoder.matches(raw, storedEncoded)
    |
    +-- Account status checks
    |
    +-- Authentication success or failure
~~~

Trong Spring Security thông thường, Controller không gọi encode lại khi login và không tự so hash. Nếu dùng form login, filter/manager/provider đã làm việc đó khi được cấu hình đúng.

### 6.3. Đổi mật khẩu khi biết mật khẩu hiện tại

Một luồng có thể:

1. Xác minh user đang đăng nhập, CSRF/session/reauth theo chính sách.
2. Kiểm tra **mật khẩu hiện tại** bằng matches nếu thao tác yêu cầu.
3. Kiểm tra mật khẩu mới theo policy và chống reuse nếu có yêu cầu.
4. Gọi **encode(newRawPassword)**.
5. Cập nhật hash trong database bằng transaction/concurrency control.
6. Thu hồi/refresh session, token hoặc thiết bị theo chính sách.
7. Không ghi raw, old hash hoặc new hash vào log/event/response.

**Không hash hash**: nếu code lấy encoded password cũ rồi gọi encode(encodedOld), người dùng sẽ không thể đăng nhập bằng raw password cũ nữa. Chỉ encode raw password được người dùng hợp lệ cung cấp.

### 6.4. Reset password

Với reset password, người dùng chứng minh quyền bằng reset token một lần/TTL thay vì cung cấp old password. Sau khi token được xác minh, xử lý mật khẩu mới như ở trên: validate → encode → lưu hash → vô hiệu hóa token reset → xem xét thu hồi session/token khác.

**PasswordEncoder không làm thay reset-token security**. Nó chỉ hash password. Reset token phải khó đoán, lưu và sử dụng một lần an toàn, không để lộ trên logs hoặc URL analytics.

## 7. Ví dụ Spring Boot 3.x hoàn chỉnh

### 7.1. Tạo project

Dùng Spring Initializr tạo project Java 17+, Spring Boot 3.x, Gradle Groovy DSL và Gradle Wrapper. Chọn dependency **Spring Web** và **Spring Security**. Trong phần dependencies của **build.gradle**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đoạn này là phần dependencies trong một Gradle project đã có Spring Boot plugin/BOM và Java toolchain; không phải toàn bộ file build.gradle độc lập. Ứng dụng sử dụng in-memory user demo để tập trung vào PasswordEncoder mà không cần database.

### 7.2. File Java

Tạo file **src/main/java/com/example/password/PasswordDemoApplication.java**:

~~~java
package com.example.password;

import java.security.Principal;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PasswordDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("demo-only-123"))
                .roles("LEARNER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-only-123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    CommandLineRunner passwordLab(PasswordEncoder encoder) {
        return args -> {
            String hash = encoder.encode("local-example");

            System.out.println(
                "prefix bcrypt: " + hash.startsWith("{bcrypt}"));
            System.out.println(
                "correct: " + encoder.matches("local-example", hash));
            System.out.println(
                "wrong: " + encoder.matches("not-the-password", hash));
        };
    }
}

@RestController
class DemoEndpoints {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/me")
    String me(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

Đây là **một file Java đầy đủ đặt trong project Boot**: public class PasswordDemoApplication trùng tên file, DemoEndpoints là class package-private cùng package. Spring Boot component scan tìm Controller. File dùng các API có sẵn trong Java 17 và Spring Security 6.x.

### 7.3. Từng phần có nhiệm vụ gì?

- **passwordEncoder()** tạo một bean DelegatingPasswordEncoder. Hash mới do factory chuẩn thường có prefix {bcrypt}.
- **users(...)** gọi **encode** tại lúc seed user, sau đó lưu encoded password trong InMemoryUserDetailsManager. Không lưu password plaintext vào UserDetails.
- **security(...)** bật HTTP Basic, quy định /public public, /me cần authenticated, /admin cần ROLE_ADMIN. Các URL khác denyAll.
- **passwordLab(...)** chạy một kiểm tra nhỏ khi app khởi động, không log raw password hoặc hash. Nó chỉ in kết quả boolean và nhận dạng prefix.
- **DemoEndpoints** chỉ đọc Principal.getName, không return nguyên Authentication hoặc UserDetails.

Mật khẩu literal **chỉ phục vụ demo local**. Production cần user store bền vững và quy trình credential riêng; không hard-code mật khẩu demo trong source được deploy ra môi trường thật.

### 7.4. Chạy và output xác định

Từ thư mục Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell sử dụng **.\gradlew.bat bootRun**.

Ngoài các Spring Boot startup logs, ba dòng do CommandLineRunner in sẽ có ý nghĩa:

~~~text
prefix bcrypt: true
correct: true
wrong: false
~~~

**Không có hash cố định trong stdout**, vì BCrypt sinh salt ngẫu nhiên. Output trên dùng cơ chế DelegatingPasswordEncoder factory của bài và không phụ thuộc hash cụ thể.

Nếu ứng dụng dùng cổng mặc định 8080:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u learner:demo-only-123 http://localhost:8080/me
curl -i -u learner:wrong http://localhost:8080/me
curl -i -u learner:demo-only-123 http://localhost:8080/admin
curl -i -u admin:admin-only-123 http://localhost:8080/admin
~~~

Trên PowerShell, dùng **curl.exe** khi curl là alias. Trên mạng thật, **HTTP Basic cần HTTPS/TLS**; Base64 không bảo mật password. Để tránh password nằm trong shell history, dùng **curl -i -u learner URL**, sau đó nhập password khi curl hỏi.

### 7.5. Kết quả HTTP kỳ vọng

| Request | Status dự kiến | Vì sao |
| --- | --- | --- |
| GET /public anonymous | **200**, public OK | permitAll |
| GET /me anonymous | **401** | HTTP Basic yêu cầu authentication |
| GET /me learner đúng password | **200**, hello learner | Provider dùng matches và xác thực thành công |
| GET /me learner sai password | **401** | matches không thành công |
| GET /admin learner đúng password | **403** | User được xác thực nhưng thiếu ROLE_ADMIN |
| GET /admin admin đúng password | **200**, admin OK | Có ROLE_ADMIN |

Đây là **kỳ vọng theo code**, không phải kết quả một server đã được chạy trong tài liệu. HTTP 401/403 chịu ảnh hưởng AuthenticationEntryPoint, filter/handler và cấu hình khác nếu ứng dụng thực tế có tùy biến.

**Điểm quan trọng:** Trong ứng dụng, bạn chỉ thấy **encode ở lúc tạo account**, không thấy Controller gọi matches. Việc matches được DaoAuthenticationProvider thực hiện sau khi HTTP Basic filter chuyển credentials vào AuthenticationManager.

### 7.6. Public endpoint vẫn có thể 401 với credentials sai

permitAll không vô hiệu hóa BasicAuthenticationFilter. Nếu client cố tình gửi Authorization: Basic sai password tới /public, filter vẫn có thể thử credential rồi trả 401 trước khi authorization permitAll được xét. Điều này không chứng minh public endpoint đã đổi thành private.

## 8. Kiểm thử tự động encode/matches và HTTP Basic

Tạo file **src/test/java/com/example/password/PasswordDemoApplicationTest.java**:

~~~java
package com.example.password;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordDemoApplicationTest {

    @Autowired PasswordEncoder encoder;
    @Autowired UserDetailsService users;
    @Autowired MockMvc mvc;

    private String basic(String username, String rawPassword) {
        String pair = username + ":" + rawPassword;
        String encodedPair = Base64.getEncoder().encodeToString(
            pair.getBytes(StandardCharsets.UTF_8));
        return "Basic " + encodedPair;
    }

    @Test
    void encodeCreatesStoredHashThatMatchesOnlyCorrectPassword() {
        String hash1 = encoder.encode("local-secret");
        String hash2 = encoder.encode("local-secret");

        assertTrue(hash1.startsWith("{bcrypt}"));
        assertTrue(hash2.startsWith("{bcrypt}"));
        assertTrue(encoder.matches("local-secret", hash1));
        assertTrue(encoder.matches("local-secret", hash2));
        assertFalse(encoder.matches("different", hash1));
    }

    @Test
    void storedUserPasswordIsEncoded() {
        String stored = users.loadUserByUsername("learner")
            .getPassword();

        assertTrue(stored.startsWith("{bcrypt}"));
        assertTrue(encoder.matches("demo-only-123", stored));
        assertFalse(encoder.matches("wrong", stored));
    }

    @Test
    void loginAndAuthorizationAreSeparate() throws Exception {
        mvc.perform(get("/me")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("learner", "demo-only-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello learner"));

        mvc.perform(get("/me")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("learner", "wrong")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/admin")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("learner", "demo-only-123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("admin", "admin-only-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin OK"));
    }
}
~~~

Tất cả các assert kiểm tra đúng **contract** thay vì so hash với một string hard-code. Test đầu cố tình không assert hai hash phải khác nhau tuyệt đối, vì có thành phần salt ngẫu nhiên; điều quan trọng là **cả hai hash đều match cùng raw password**, còn password sai không match.

Chạy:

~~~bash
./gradlew test
~~~

Trên PowerShell dùng **.\gradlew.bat test**.

Đây là file test đầy đủ trong project Boot có spring-boot-starter-test. MockMvc tự dựng header Basic nên không cần phụ thuộc spring-security-test chỉ để gọi HTTP Basic trong bài này. Phải kiểm tra đúng namespace/version khi ghép vào project khác.

**Những ví dụ và test được viết theo API, chưa được chạy trong chính bài viết này.** Trong hệ thống thực, hãy chạy build/test để xác minh phiên bản dependency và kết quả của môi trường cụ thể.

## 9. upgradeEncoding: khi nào nên tạo lại hash?

Password hashing parameters và thuật toán có thể cần thay đổi theo thời gian. Interface PasswordEncoder có **upgradeEncoding(encodedPassword)** trả true khi implementation đánh giá hash hiện tại nên được nâng cấp. Default implementation trả false; một số encoder như BCrypt/DelegatingPasswordEncoder có logic riêng.

Đây **không phải tự động thay hash trong database**. Nó chỉ là một tín hiệu.

### 9.1. Quy trình đổi hash an toàn

Một ứng dụng đã kiểm chứng người dùng thành công có thể:

~~~java
boolean valid = encoder.matches(rawPassword, storedHash);

if (valid && encoder.upgradeEncoding(storedHash)) {
    String upgraded = encoder.encode(rawPassword);
    accountRepository.updatePasswordHash(userId, upgraded);
}
~~~

Đây là snippet logic nằm trong một service đã có encoder, repository, userId và raw password được xử lý an toàn; **không phải file chạy độc lập**.

Ý nghĩa:

1. Chỉ rehash sau khi raw password đã được xác minh đúng.
2. Rehash **raw password**, không encode hash cũ.
3. Lưu hash mới theo transaction và kiểm soát concurrent password changes.
4. Không ghi hash cũ/mới vào log.
5. Khi đổi password, cần xem xét token/session revocation.
6. Phải kiểm tra format của hash cũ có được encoder nhận diện để matches trước khi upgrade.

Trong kiến trúc DaoAuthenticationProvider, có tích hợp **UserDetailsPasswordService** để cập nhật encoded password sau xác thực khi cấu hình tương thích. Cần cấu hình và kiểm thử cơ chế đó; đừng cho rằng chỉ khai báo PasswordEncoder bean thì tất cả hash cũ trong database tự được nâng cấp.

### 9.2. Không thể thay thuật toán hàng loạt nếu không có raw password

Từ một hash BCrypt, bạn không thể lấy lại raw password rồi chuyển ngay sang Argon2id. Muốn nâng thuật toán an toàn thường phải **đợi lần đăng nhập hợp lệ** để rehash raw password đã được chứng minh, hoặc buộc đổi mật khẩu theo flow có xác minh.

Chỉ với trường hợp thay metadata id của **cùng thuật toán/format đã biết**, ví dụ thêm {bcrypt} trước raw BCrypt hash, mới có thể làm migration định dạng mà không có raw password. Đây khác với việc chuyển sang một thuật toán hash mới.

## 10. So sánh các password hashing algorithms

| Thuật toán/encoder | Đặc điểm | Lưu ý |
| --- | --- | --- |
| **BCryptPasswordEncoder** | Password hashing với salt/cost; phổ biến | Cost cần benchmark; lưu ý input bytes/72-byte limit |
| **Argon2PasswordEncoder** | Memory-hard password hashing, thường dùng Argon2id theo cấu hình | Cần dependencies/parameters/memory phù hợp version |
| **SCryptPasswordEncoder** | Memory-hard key derivation | Điều chỉnh CPU/memory cost theo vận hành |
| **Pbkdf2PasswordEncoder** | Dựa trên PBKDF2 với iterations, salt và hash parameters | Chọn parameters đủ mạnh; phù hợp một số môi trường yêu cầu |
| **DelegatingPasswordEncoder** | Wrapper chọn encoder bằng prefix id | Cần quản trị map ids, default behavior và legacy migration |
| **NoOpPasswordEncoder** | Không bảo vệ mật khẩu, so plaintext | **Không dùng production** |
| **MessageDigestPasswordEncoder/SHA đơn thuần** | Các phương pháp cũ có thể thiếu work factor phù hợp | Không chọn cho mật khẩu mới; cần kế hoạch migration |

Spring Security chứa nhiều encoder để hỗ trợ tương thích và migration. **Sự hiện diện của một encoder không có nghĩa thuật toán ấy phù hợp cho mật khẩu mới**. Với password storage hiện đại, dùng thuật toán chuyên cho mật khẩu có chi phí điều chỉnh được và tham khảo khuyến nghị bảo mật hiện hành.

### 10.1. Có cần dùng chính BCrypt trong mọi ứng dụng?

Không. BCrypt là lựa chọn thực dụng trong nhiều hệ thống, nhưng Argon2id, scrypt hoặc PBKDF2 cũng có trường hợp phù hợp. Chọn theo threat model, library/version, hỗ trợ hạ tầng và benchmarks, không dựa vào suy đoán “algorithm nào luôn mạnh nhất”.

Dù chọn encoder nào, **rate limiting, MFA khi phù hợp, secret handling và khóa truy cập DB** vẫn phải được thiết kế. Hash chậm giúp chống offline guessing nhưng không tự chặn online guessing qua login API.

## 11. Các lỗi cấu hình hay gặp trong Spring Security

### 11.1. Stored password có {bcrypt} nhưng bean là BCryptPasswordEncoder thuần

Nếu database chứa chuỗi bắt đầu **{bcrypt}$2a$...**, còn bean là **new BCryptPasswordEncoder()**, matches có thể không chấp nhận prefix vì BCryptPasswordEncoder trực tiếp mong đợi format BCrypt bắt đầu bằng $2a/$2b/$2y.

**Khắc phục:** Dùng DelegatingPasswordEncoder tương thích prefix, hoặc migration format rõ ràng. Không bỏ qua lỗi bằng cách lưu plaintext.

### 11.2. Stored password không có id nhưng bean là DelegatingPasswordEncoder

Lỗi thường có thông điệp “There is no PasswordEncoder mapped for the id null”. Kiểm tra encoder cũ đã tạo hash chưa có prefix; quyết định migration dựa trên nguồn gốc dữ liệu thật. Không gắn {bcrypt} vào hash thuộc thuật toán khác.

### 11.3. DaoAuthenticationProvider báo sai mật khẩu dù người dùng chắc chắn đúng

Các nguyên nhân có thể gồm:

- Đầu vào raw password đã bị trim, normalize hoặc biến đổi khác trước khi matches.
- Database lưu hash bị cắt do cột ngắn.
- Mỗi environment dùng encoder hoặc version/cost/format khác.
- Database đang lưu double-hashed password.
- UserDetailsService tải sai account hoặc trả password từ cột khác.
- Có salt/pepper tự chế bị thay đổi mà không có versioning.
- Input Unicode dài khác nhau ở mức bytes.
- Profile/config/AuthenticationManager đang dùng một UserDetailsService khác dự kiến.

Đừng sửa bằng cách bỏ so password. Debug bằng **format/length/algorithm id và error category an toàn**, tuyệt đối không print raw password hoặc toàn bộ hash vào log.

### 11.4. Dùng User.withDefaultPasswordEncoder trong production

Một số sample Spring Security có tiện ích demo cho mật khẩu dễ chạy. Tiện ích đó không nên là cách lưu password thật. Hãy cung cấp PasswordEncoder bean an toàn và gọi encode khi tạo account.

### 11.5. Dùng {noop} để fix “id null”

{noop} là format cho encoder không làm hash password, thường tồn tại để tương thích/demonstration. Nó không phải cách sửa lỗi format cho BCrypt. Nếu lưu "{noop}password" thì người có quyền xem DB có thể thấy password ở dạng rõ. Không dùng production.

### 11.6. Tự tạo mật khẩu đã hash và hard-code trong source

Có thể dùng hash cố định cho test fixtures hoặc migration có kiểm soát, nhưng production nên qua flow đăng ký/đổi mật khẩu và nguồn secret quản lý. Không commit tài khoản mẫu có password sử dụng được vào sản phẩm thật.

### 11.7. So String.equals ở tầng Controller

Với BCrypt, hash khác do salt; hơn nữa Controller không nên trực tiếp làm bước xác thực nếu ứng dụng đã có Spring Security. Để DaoAuthenticationProvider gọi matches theo contract; business endpoint nhận Principal/Authentication đã được framework xác minh.

### 11.8. Cho phép login từ DB mà không kiểm tra account status

Password đúng không đồng nghĩa account được phép sử dụng. DaoAuthenticationProvider còn xem enabled, locked, expired và các điều kiện được triển khai. Custom provider không nên bỏ các bước này.

### 11.9. Lộ hash qua Authentication, UserDetails hoặc JSON

UserDetails thường có getPassword() vì phục vụ provider. Nhưng Controller không nên return UserDetails, Authentication hoặc JPA entity chứa password_hash. Sử dụng response DTO chỉ có trường cần thiết. Một password hash bị lộ vẫn có thể bị brute-force ngoại tuyến.

### 11.10. Bỏ qua khác biệt timing

Nếu tự viết auth code và return ngay khi không có username, nhánh không tìm thấy user có thể nhanh hơn nhánh phải chạy BCrypt.matches; đây là một kênh **user enumeration**. Dùng provider hiện hành đã được vá, giới hạn số lần thử và kiểm thử các trạng thái khóa/vô hiệu hóa theo security advisories. Không giả định dùng cùng HTTP 401 là đã chống mọi timing side channel.

## 12. Xử lý password và dữ liệu nhạy cảm ở các lớp

| Nơi | Việc được làm | Việc cần tránh |
| --- | --- | --- |
| HTTP login request | Nhận password qua HTTPS, validate input | Đưa vào URL/query hoặc log request body |
| Registration/password service | Gọi encode rồi lưu hash | Lưu raw password hoặc gửi hash về client |
| UserDetailsService | Tải encoded password cùng authorities/flags | Tự xác thực bằng string comparison |
| DaoAuthenticationProvider | Sử dụng matches để kiểm tra credential | Tin role do client khai |
| SecurityContext/Principal | Giữ định danh/quyền đã xác thực | Serialize password/hash/token ra API |
| Database | Bảo vệ password_hash, index/unique đúng | Column quá ngắn, backup không kiểm soát |
| Logs/tracing | Request ID, loại lỗi an toàn | Authorization, cookie, raw password, hash |
| Password reset | Token một lần + encode(new password) | Gửi lại password cũ hoặc token trong log |
| Hash migration | Verify, upgrade và audit | Đổi encoder mà không kiểm tra toàn bộ hash legacy |

### 12.1. Không được tự lưu raw password trong Java field kéo dài

Trong Servlet hoặc JVM, raw password có thể tạm nằm trong String/buffer trong quá trình xác thực. Điều đó không đồng nghĩa cần giữ nó trong entity, session, static field, cache hay event. Giới hạn phạm vi, thời gian tồn tại và các điểm logging.

Với Java String, không thể cam kết xóa ngay mọi bản sao khỏi heap. Cần thiết kế luồng credential để không tạo các bản sao dài hạn, bảo vệ memory dumps và ưu tiên API/library đã được kiểm chứng.

### 12.2. Password hash không phải authorization

Một password khớp chỉ xác nhận credential của account. Authorization còn phải xem ROLE_USER/ROLE_ADMIN, ownership, tenant, trạng thái nghiệp vụ, re-authentication/MFA cho thao tác nhạy cảm. PasswordEncoder không quyết định user được đọc record của ai.

## 13. Checklist kiểm thử trong dự án thật

Khi triển khai một PasswordEncoder, nên kiểm tra:

1. encode(raw) tạo chuỗi theo format mong muốn; không phải raw password.
2. matches(raw, encode(raw)) trả true.
3. matches(wrong, encode(raw)) trả false.
4. Raw password có Unicode/ký tự đặc biệt/độ dài giới hạn hoạt động theo policy.
5. Cùng password tạo hai hash salted khác nhau thông thường, và **cả hai đều kiểm chứng được**.
6. Database column đủ dài, không truncate hash hoặc prefix.
7. Hash cũ/format legacy được xử lý hoặc báo lỗi migration rõ ràng.
8. Bean PasswordEncoder được provider thực sự sử dụng, không có encoder khác ở environment khác.
9. Ở login, input đúng được 200, sai là 401 theo Basic policy.
10. User đúng password nhưng thiếu role là 403, không nhầm với sai password.
11. Account disabled/locked không được login chỉ vì password khớp.
12. Khi đổi password, hash mới match, hash cũ không còn là credential hợp lệ.
13. Nếu upgradeEncoding báo true, quy trình nâng cấp lưu hash mới có concurrency/revocation hợp lý.
14. Không lộ raw password/hash trong logs, response, tracing hoặc exception.
15. Kiểm thử rate limits, chống brute force, password reset token và security advisory theo version.

### 13.1. Mẹo thiết kế test

Không cần assert toàn bộ chuỗi BCrypt hash bằng một literal. Với salted password hashing, điều cần test là các thuộc tính: format đúng, matches đúng/sai, khả năng tương thích sau khi lưu/đọc. Các test về performance cost nên làm riêng trong môi trường kiểm soát, không đặt ngưỡng milliseconds cứng trên CI máy khác nhau.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** encode("abc") được dùng vào lúc nào?  
**Đáp:** Khi cần tạo encoded password để lưu, ví dụ đăng ký hoặc đổi password.

**Câu 2.** matches nhận hai tham số theo thứ tự nào?  
**Đáp:** raw password trước, encoded password đã lưu sau.

**Câu 3.** Vì sao encode cùng mật khẩu hai lần có thể tạo hai chuỗi khác nhau?  
**Đáp:** Vì salt ngẫu nhiên trong thuật toán password hashing như BCrypt.

**Câu 4.** Có nên so encode(raw).equals(storedHash) không?  
**Đáp:** Không, vì hash mới có salt khác. Dùng matches(raw, storedHash).

**Câu 5.** matches có giải mã hash để lấy lại mật khẩu gốc không?  
**Đáp:** Không. Nó kiểm chứng raw candidate theo thuật toán/metadata của hash đã lưu.

**Câu 6.** BCryptPasswordEncoder trực tiếp và DelegatingPasswordEncoder có cùng định dạng lưu không?  
**Đáp:** Không nhất thiết. BCrypt trực tiếp thường lưu $2a$..., còn Delegating factory thường lưu {bcrypt}$2a$....

**Câu 7.** Lỗi “id null” khi dùng DelegatingPasswordEncoder gợi ý điều gì?  
**Đáp:** Stored hash không có prefix encoder id hoặc format không tương thích.

**Câu 8.** Có thể chỉ thêm {bcrypt} trước một hash BCrypt legacy hợp lệ không?  
**Đáp:** Có thể khi đã xác nhận chắc chắn hash đó là BCrypt; chỉ thêm metadata id, không phải chuyển algorithm.

**Câu 9.** Vì sao không được đưa {noop} vào production?  
**Đáp:** Nó không bảo vệ password; giá trị có thể là plaintext.

**Câu 10.** DaoAuthenticationProvider dùng phần nào để so password?  
**Đáp:** UserDetailsService tải hash và PasswordEncoder.matches kiểm chứng raw password.

**Câu 11.** upgradeEncoding có tự cập nhật cột database không?  
**Đáp:** Không. Nó chỉ là tín hiệu; cần cơ chế update hash sau khi đã xác minh raw password.

**Câu 12.** Vì sao không thể lấy lại raw password từ BCrypt hash để bulk convert sang Argon2?  
**Đáp:** Password hashing một chiều; cần raw password ở lần xác thực hợp lệ hoặc flow đổi password.

**Câu 13.** BCrypt strength cao có luôn tốt hơn vô điều kiện không?  
**Đáp:** Không. Phải cân bằng offline attack resistance, latency, CPU và online DoS.

**Câu 14.** Password đúng nhưng vào URL admin vẫn nhận 403, encoder có lỗi không?  
**Đáp:** Không nhất thiết. Authentication thành công nhưng authorization thiếu ROLE_ADMIN.

**Câu 15.** Password hash có nên được log để debug login không?  
**Đáp:** Không. Hash là dữ liệu nhạy cảm, có thể bị tấn công đoán offline nếu lộ.

## 15. Tài liệu tham khảo chính thức

- Spring Security — Password Storage và DelegatingPasswordEncoder: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — PasswordEncoder API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html
- Spring Security 6.3 — BCryptPasswordEncoder API: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html
- Spring Security — Cryptography và PasswordEncoder: https://docs.spring.io/spring-security/reference/features/integrations/cryptography.html
- Spring Security — Username/Password Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — UserDetailsService: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
