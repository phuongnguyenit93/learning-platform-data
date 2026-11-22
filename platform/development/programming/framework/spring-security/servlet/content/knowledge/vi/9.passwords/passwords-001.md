# PasswordEncoder: băm mật khẩu khác mã hóa có thể giải mã

> **Phạm vi:** Spring Security 6.x, Java 17+, ứng dụng Spring Boot 3.x trên Servlet stack. Bài học giải thích vì sao mật khẩu phải được lưu dưới dạng **password hash**, thay vì dữ liệu **mã hóa hai chiều có thể giải mã**; cơ chế `salt` và `work factor`; API `PasswordEncoder.encode`, `matches`, `upgradeEncoding`; chiến lược sử dụng `DelegatingPasswordEncoder` và nâng cấp thuật toán theo thời gian.

## 1. Vì sao ứng dụng không cần giải mã mật khẩu?

Khi người dùng tạo mật khẩu, ứng dụng cần kiểm tra mật khẩu nhập ở lần đăng nhập sau có đúng không. Ứng dụng **không cần** gửi lại mật khẩu gốc cho người dùng. Nếu database lưu password dưới dạng plaintext, người đọc được database có thể dùng ngay password. Nếu password được mã hóa bằng AES với một khóa có thể giải mã, khi khóa bị lộ, password có thể được khôi phục hàng loạt.

Một quy trình chuẩn là:

```text
ĐĂNG KÝ
  raw password
      |
      v
  PasswordEncoder.encode(rawPassword)
      |
      v
  encoded password (hash + salt + parameters)
      |
      v
  database lưu encoded password, không lưu raw password

ĐĂNG NHẬP
  username -> đọc encoded password từ database
  raw password của request mới + encoded password đã lưu
      |
      v
  PasswordEncoder.matches(rawPassword, encodedPassword)
      |
      +--> true: tiếp tục kiểm tra tài khoản/xác thực
      +--> false: từ chối đăng nhập
```

**Không có thao tác `decrypt(passwordHash)`.** Người dùng quên mật khẩu cần đi qua luồng đặt lại mật khẩu an toàn, không phải chức năng “xem lại mật khẩu cũ”.

Password hashing không khiến mọi password không thể bị đoán. Nếu hacker lấy được database hash, họ vẫn có thể thử từ điển, mật khẩu từng bị lộ hoặc brute force **offline**. Thuật toán password hashing làm mỗi lần thử **tốn chi phí tính toán có chủ đích**, nhằm giảm tốc độ thử ứng viên. Độ mạnh còn tùy độ khó mật khẩu và hạ tầng.

## 2. Khác biệt giữa encryption, hash nhanh và password hashing

| Công nghệ | Đặc điểm | Phù hợp để lưu mật khẩu đăng nhập? |
| --- | --- | --- |
| **Encryption hai chiều**, ví dụ AES-GCM | Có thể giải mã plaintext bằng khóa hợp lệ | **Không phù hợp** nếu chỉ cần xác minh mật khẩu |
| **Hash nhanh**, ví dụ SHA-256/SHA-512 trực tiếp | Không có API giải mã, nhưng tính rất nhanh | **Không đủ** để chống đoán password offline |
| **Password hashing/KDF**, ví dụ bcrypt, Argon2id, scrypt, PBKDF2 | Có salt và tham số điều chỉnh chi phí tính toán/bộ nhớ | **Có**, nếu thuật toán và tham số phù hợp |
| **HMAC** | Dùng secret key để xác thực thông điệp | Không phải thay thế mặc định cho password hashing |

### Encryption cần một khóa giải mã

```text
ciphertext = Encrypt(key, plaintext)
plaintext  = Decrypt(key, ciphertext)
```

Encryption rất hữu ích đối với **dữ liệu cần được đọc lại** khi có quyền, nhưng việc có thể khôi phục mật khẩu cũ là rủi ro không cần thiết nếu ứng dụng chỉ xác thực người dùng. Đừng dùng encryption chỉ để triển khai tính năng “gửi lại password”.

### SHA-256(password) không đủ

SHA-256 được thiết kế rất nhanh để phục vụ hashing dữ liệu. Tính nhanh này không tốt khi đối thủ có thể thử nhiều password sau khi lấy được bản dump database. Ngay cả `SHA-256(salt || password)` cũng chưa trở thành một password KDF có work factor thích hợp.

Không tự tạo hệ thống password hashing bằng cách lặp SHA-256 vài lần hoặc kết hợp MD5/SHA tùy ý. Sử dụng thư viện và thuật toán chuyên dụng đã được kiểm chứng.

### Password hash không phải “mã hóa không giải mã được”

Cách diễn đạt chính xác hơn là password hash tạo ra **giá trị kiểm chứng một chiều** được thiết kế cho việc kiểm tra một password ứng viên, chứ không phải ciphertext có thể đảo ngược bằng key. Tuy vậy, password yếu vẫn có thể bị đoán bằng nhiều phép thử. Không có “khóa decrypt” cho bcrypt hash tương tự như key AES.

## 3. Salt, work factor và pepper

### Salt riêng cho mỗi lần tạo hash

**Salt** là dữ liệu ngẫu nhiên dùng trong phép tạo password hash. Encoder chuẩn thường tự tạo salt mới trên từng lần `encode`. Vì vậy cùng một raw password có thể tạo nhiều chuỗi encoded khác nhau, nhưng tất cả đều `matches` với password đúng.

```text
password = "study123"
salt A -> password hash A
salt B -> password hash B

hash A khác hash B (với xác suất áp đảo)
matches("study123", hash A) -> true
matches("study123", hash B) -> true
```

Salt **không phải bí mật**; nó thường nằm cùng hash và được dùng khi verification. Salt giúp hai user có cùng password không có hash dễ đối chiếu, giảm hiệu quả của bảng tính sẵn. Không dùng global salt cố định cho mọi account, không dùng username/email thay random salt, không tự quản lý salt riêng nếu encoder đã làm đúng.

### Work factor là chi phí của phép thử

- **bcrypt:** cost xác định khối lượng tính toán.
- **PBKDF2:** iterations và PRF/parameters.
- **scrypt:** work/memory parameters.
- **Argon2id:** memory, time/iterations và parallelism.

Work factor thấp khiến hacker thử nhiều password nhanh. Work factor quá cao làm server chậm, tốn CPU/RAM và có thể dễ bị tấn công DoS qua nhiều request login. Vì vậy phải **benchmark trên hạ tầng thực**, đánh giá concurrency, latency và khả năng nâng cost theo thời gian; không copy cứng một con số cost từ tutorial rồi cho rằng phù hợp mọi nơi.

### Pepper là secret bổ sung, không thay salt

**Pepper** là bí mật hệ thống có thể bổ sung theo thiết kế được review, thường giữ tách khỏi database trong secret manager/KMS. Khác salt, pepper phải được bảo vệ và có kế hoạch rotate. Pepper không thay thế password hashing, salt hay work factor; cũng không cung cấp khả năng giải mã hash. Không tùy tiện nối pepper vào password nếu chưa có mô hình quản lý khóa và migration rõ.

## 4. PasswordEncoder của Spring Security

`org.springframework.security.crypto.password.PasswordEncoder` có ba phương thức quan trọng:

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);

    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

Đây là **chữ ký API minh họa**, không phải interface cần tự tạo.

- `encode(rawPassword)`: tạo chuỗi hash để lưu. Chữ “encode” **không** có nghĩa có thể decode để phục hồi password.
- `matches(rawPassword, encodedPassword)`: dùng raw password vừa nhận và hash đã lưu để kiểm tra, theo thuật toán/salt/params thích hợp.
- `upgradeEncoding(encodedPassword)`: cho biết hash cũ có nên được tạo lại bằng policy hiện tại hay không. Phương thức **không tự cập nhật database**.

### Tại sao không encode lại rồi so sánh bằng equals?

```java
String stored = encoder.encode("study123");

// SAI: một lần encode mới có thể tạo salt mới.
boolean wrong = encoder.encode("study123").equals(stored);

// ĐÚNG: dùng phương thức đối chiếu của encoder.
boolean correct = encoder.matches("study123", stored);
```

Đây là đoạn code **minh họa trong một phương thức** có biến `encoder` kiểu `PasswordEncoder`. Hai lần encode cùng password thường khác nhau vì salt mới. Mỗi thuật toán có quy tắc verification riêng; hãy để `matches` xử lý.

### PasswordEncoder không thay toàn bộ authentication

`UserDetailsService` cung cấp account và hash đã lưu; `DaoAuthenticationProvider` có thể gọi `matches` để so password; `AuthenticationManager` điều phối providers. Sau password check còn trạng thái khóa/tắt/hết hạn tài khoản, role/authority và các chính sách bảo mật khác. Password đúng **không có nghĩa** chắc chắn được phép truy cập endpoint.

## 5. Những thuật toán và encoder đáng biết

| API/thuật toán | Ưu điểm | Lưu ý |
| --- | --- | --- |
| `BCryptPasswordEncoder` | Có salt/cost, phổ biến, dễ tích hợp | Bcrypt truyền thống có giới hạn quanh **72 byte** đầu vào; cần kiểm tra Unicode/độ dài và cost |
| `Argon2PasswordEncoder` / Argon2id | Memory-hard, điều chỉnh thời gian, RAM, parallelism | Cần dependency phù hợp, có phiên bản dùng Bouncy Castle; benchmark RAM và concurrency |
| `SCryptPasswordEncoder` | Memory-hard | Cấu hình memory/CPU và tải login hợp lý |
| `Pbkdf2PasswordEncoder` | Tương thích rộng, có iteration count | Tăng chi phí tính toán; không memory-hard như Argon2id/scrypt |
| `DelegatingPasswordEncoder` | Lựa chọn encoder theo prefix `{id}`, hỗ trợ hash nhiều thế hệ | Phải quản lý mapping và format legacy |
| `NoOpPasswordEncoder` | Không hash | **Không dùng để lưu mật khẩu production** |

Với bcrypt, giới hạn **byte** khác giới hạn **ký tự Unicode**; một ký tự tiếng Việt có thể chiếm nhiều byte UTF-8. Tùy implementation/version, mật khẩu dài có thể gặp hành vi không như kỳ vọng. Không tự `trim()` password, không tự cắt chuỗi hoặc tiền băm tự chế; cần policy nhất quán và thử nghiệm thực tế.

Argon2id thường là lựa chọn hiện đại tốt nếu hạ tầng và thư viện hỗ trợ; bcrypt vẫn được dùng rộng rãi. Không tuyên bố một thuật toán/cost luôn là “an toàn tuyệt đối” ở mọi thời điểm.

## 6. DelegatingPasswordEncoder và tiền tố {id}

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo encoder có thể dùng nhiều thuật toán để **verify** dựa trên identifier. Trong cấu hình factory của Spring Security 6.x ở ví dụ dưới, phương thức `encode` mặc định chọn bcrypt.

Dạng dữ liệu điển hình:

```text
{bcrypt}$2a$10$<phần salt và hash được sinh>
|------|
    id
```

Đây **không phải hash hợp lệ hoàn chỉnh**, chỉ mô tả format. `{bcrypt}` là định danh để `DelegatingPasswordEncoder` tìm encoder. Salt và phần hash thực tế được sinh ngẫu nhiên; prefix không phải secret hoặc lớp mã hóa.

```java
PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

String stored = encoder.encode("study123");
boolean valid = encoder.matches("study123", stored);
```

Khi `matches` nhận `{bcrypt}...`, nó đọc id, chọn bcrypt encoder đã map và kiểm tra raw password với hash ở phần sau. Thiết kế này cho phép một hệ thống xác minh hash cũ và hash mới trong giai đoạn nâng cấp thuật toán (nếu còn hỗ trợ encoder tương ứng).

### Khi hash cũ thiếu id

Database dùng bcrypt cũ thường chứa chuỗi như `$2a$...` không có prefix `{bcrypt}`. Nếu truyền nguyên giá trị này vào `DelegatingPasswordEncoder.matches` theo default, framework có thể ném `IllegalArgumentException` vì id `null` chưa được map. Đây là lỗi **định dạng dữ liệu/encoder**, không phải chứng cứ password sai.

Hướng xử lý an toàn:

1. Xác minh bản ghi cũ thật sự là hash bcrypt hợp lệ. Nếu mọi bản ghi đã được phân loại chính xác, có thể migrate theo batch sang `{bcrypt}` + chuỗi hash gốc.
2. Nếu có nhiều thuật toán legacy, quản lý mapping/metadata rõ ràng rồi verify đúng thuật toán.
3. Rehash sau login thành công bằng policy mới hoặc dùng quy trình reset password khi không thể verify dữ liệu cũ.
4. **Không** đặt `NoOpPasswordEncoder` thành default fallback cho mọi hash thiếu id để “sửa lỗi” nhanh: điều đó có thể tạo nhánh chấp nhận plaintext không an toàn.

Các version Spring Security có thể dùng id với hậu tố/version cho một số thuật toán. Luôn xác minh mapping của thư viện đang chạy, không tự đoán prefix.

## 7. Ví dụ Java 17+ chạy được: encode và matches

Ví dụ sử dụng Spring Security Crypto từ họ phiên bản Spring Boot 3.3.5, Java 17 và Gradle 8.5. Đây là **chương trình console độc lập**, không cần servlet container, database hay server web.

### 7.1. Cấu trúc tệp

```text
password-encoder-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    PasswordEncodingDemo.java
  src/test/java/demo/
    PasswordEncodingDemoTest.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'password-encoder-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.3.5'
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-crypto'
    implementation 'org.springframework:spring-core'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'demo.PasswordEncodingDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-security-crypto` chứa `PasswordEncoder`, factory và bcrypt; `spring-core` cung cấp các dependency Spring cần cho ví dụ console. Với web app Spring Boot thật, `spring-boot-starter-security` thường đã bao gồm những phần liên quan.

### 7.2. Main hoàn chỉnh

`src/main/java/demo/PasswordEncodingDemo.java`:

```java
package demo;

import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PasswordEncodingDemo {

    private PasswordEncodingDemo() {
    }

    public static void main(String[] args) {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String rawPassword = "correct-horse-battery-staple!2026";
        String stored = encoder.encode(rawPassword);

        System.out.println("bcrypt id: " + stored.startsWith("{bcrypt}"));
        System.out.println("correct password: "
                + encoder.matches(rawPassword, stored));
        System.out.println("wrong password: "
                + encoder.matches("wrong-password", stored));
        System.out.println("stored plaintext: "
                + stored.equals(rawPassword));
    }
}
```

Từ thư mục chứa `build.gradle`, chạy:

```bash
gradle run
gradle test
```

Nếu có Gradle Wrapper, dùng `./gradlew run` và `./gradlew test` trên macOS/Linux, hoặc `.\gradlew.bat run` và `.\gradlew.bat test` trên Windows.

**Bốn dòng từ `System.out.println`** (không bao gồm log của Gradle):

```text
bcrypt id: true
correct password: true
wrong password: false
stored plaintext: false
```

Kết quả có thể lặp lại vì chương trình **không in giá trị hash ngẫu nhiên**. Trong sản phẩm thật cũng không nên log raw password, hash hay dữ liệu xác thực nhạy cảm.

### 7.3. Kiểm thử JUnit 5

`src/test/java/demo/PasswordEncodingDemoTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PasswordEncodingDemoTest {

    private static final String RAW =
            "correct-horse-battery-staple!2026";

    private final PasswordEncoder delegating =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

    @Test
    void delegatingHashesAndMatches() {
        String stored = delegating.encode(RAW);
        assertTrue(stored.startsWith("{bcrypt}"));
        assertTrue(delegating.matches(RAW, stored));
        assertFalse(delegating.matches("wrong-password", stored));
        assertFalse(stored.equals(RAW));
    }

    @Test
    void rawBcryptVerifiesItsOwnHash() {
        BCryptPasswordEncoder bcrypt = new BCryptPasswordEncoder(10);
        String stored = bcrypt.encode(RAW);
        assertTrue(bcrypt.matches(RAW, stored));
        assertFalse(bcrypt.matches("wrong-password", stored));
    }

    @Test
    void delegatingRejectsLegacyWithoutIdByDefault() {
        BCryptPasswordEncoder bcrypt = new BCryptPasswordEncoder(10);
        String legacy = bcrypt.encode(RAW);
        assertThrows(IllegalArgumentException.class,
                () -> delegating.matches(RAW, legacy));
    }

    @Test
    void unknownIdIsNotSilentlyAccepted() {
        assertThrows(IllegalArgumentException.class,
                () -> delegating.matches(RAW, "{unknown}not-a-hash"));
    }
}
```

**Kết quả kỳ vọng với cấu hình này:** 4 JUnit tests PASS. Test xác minh chức năng thay vì so byte hash có salt ngẫu nhiên. Hai test sau minh họa vì sao dữ liệu cũ không có prefix hoặc id lạ phải được xử lý qua migration, không đoán tự động.

## 8. Tích hợp PasswordEncoder vào Spring Security Servlet

Trong ứng dụng có `spring-boot-starter-security`, có thể khai báo một `PasswordEncoder` bean dùng chung cho đăng ký, thay password và authentication:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class PasswordConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
```

Đây là lớp `@Configuration` cho **ứng dụng Spring Context**, không phải tệp dùng trong console demo nếu chưa có dependency Spring Context.

### Đăng ký và thay password

```java
// Pseudocode: command và userRepository là kiểu nghiệp vụ.
String rawPassword = command.password();
String encoded = passwordEncoder.encode(rawPassword);
userRepository.savePasswordHash(command.userId(), encoded);
```

Chỉ lưu encoded password và không log raw password. Không chuyển hash qua API response. Column trong DB phải đủ dài cho prefix, tham số và các format hash tương lai.

### Đăng nhập với DaoAuthenticationProvider

```text
Client gửi username/raw password qua HTTPS
             |
             v
AuthenticationManager -> DaoAuthenticationProvider
             |
             +--> UserDetailsService.loadUserByUsername(username)
             |            |
             |            +--> lấy encoded hash đã lưu
             |
             +--> PasswordEncoder.matches(rawPassword, storedHash)
                         |
                         +--> true: tiếp tục check account status / xác thực
                         +--> false: BadCredentialsException
```

Đây là sơ đồ tóm tắt: một số account status checks diễn ra trước so mật khẩu, một số sau. `PasswordEncoder` không thay thế việc kiểm tra locked/disabled, quyền hoặc CSRF; nó chỉ đảm nhận password verification.

## 9. Tăng work factor và migrate hash an toàn

Các phiên bản thuật toán và tham số an toàn có thể thay đổi. `upgradeEncoding` là một tín hiệu hỗ trợ nâng cấp hash sau khi người dùng đăng nhập đúng. Nó **không** tự cập nhật DB.

```text
Login -> load oldHash
      -> matches(rawPassword, oldHash)
         |
         +-- false -> từ chối
         |
         +-- true  -> upgradeEncoding(oldHash)?
                       |
                       +-- false -> giữ nguyên hash
                       |
                       +-- true  -> encode(rawPassword)
                                   -> cập nhật hash an toàn
```

Pseudocode cho service (không phải class Java độc lập):

```java
if (!passwordEncoder.matches(rawPassword, oldHash)) {
    throw new BadCredentialsException("Invalid credentials");
}

if (passwordEncoder.upgradeEncoding(oldHash)) {
    String replacement = passwordEncoder.encode(rawPassword);

    // API giả định của ứng dụng; không phải Spring Security method.
    userRepository.replaceHashIfUnchanged(userId, oldHash, replacement);
}
```

Có thể thực hiện compare-and-swap ở DB:

```sql
UPDATE users
SET password_hash = :new_hash
WHERE id = :user_id
  AND password_hash = :expected_old_hash;
```

Điều kiện trên tránh một request đăng nhập cũ ghi đè lần đổi mật khẩu đồng thời. Ứng dụng cần kiểm tra affected rows và transaction. Phải hash **raw password vừa xác thực**, không hash `oldHash`. Khi chỉ có hash cũ mà không có raw password, không thể tổng quát chuyển sang hash của thuật toán mới; thường phải chờ lần login hoặc yêu cầu reset.

`DaoAuthenticationProvider` hỗ trợ tích hợp `UserDetailsPasswordService` để cập nhật hash trong cấu hình tương ứng. Việc dùng cơ chế này phụ thuộc service và repository mà ứng dụng cung cấp; đừng giả định mọi project tự động migrate password.

## 10. Vận hành an toàn trong thực tế

1. **HTTPS/TLS:** bảo vệ raw password trên đường truyền.
2. **Rate limiting:** giới hạn online guessing và tải CPU/RAM của các phép password hash.
3. **MFA khi phù hợp:** giảm tác động nếu mật khẩu bị lộ từ dịch vụ khác.
4. **Bảo vệ database/backups:** hash vẫn là dữ liệu nhạy cảm; dùng quyền truy cập tối thiểu, mã hóa backup khi cần.
5. **Không log secret:** không ghi raw password, hash, token reset hoặc credentials vào logs/analytics.
6. **Reset password có xác minh:** token ngẫu nhiên, có hạn, dùng một lần; thay hash và xử lý phiên cũ theo chính sách.
7. **Unicode và whitespace nhất quán:** tránh tự động `trim()`; không normalize khác nhau giữa đăng ký và login; kiểm tra password dài theo byte.
8. **Benchmark cost:** theo dõi latency và concurrency; Argon2id/scrypt có chi phí RAM, bcrypt/PBKDF2 có chi phí CPU.
9. **Không dùng hash như session token:** hash không phải bearer credential cần gửi cho client.
10. **Review format legacy:** xác định `{id}`, chiến lược verify hash cũ và lộ trình loại bỏ thuật toán yếu.

### Có khi nào encryption hai chiều đúng?

Có, nếu dữ liệu thực sự cần được **đọc lại** dưới quyền hạn được kiểm soát. Khi đó phải thiết kế quản lý encryption key, rotation, nonce/IV, access control và logging. Nhưng với password đăng nhập thông thường, khả năng decrypt không đem lại lợi ích cần thiết.

## 11. Lỗi phổ biến và cách sửa

| Lỗi hoặc hiểu nhầm | Tại sao xảy ra? | Cách xử lý |
| --- | --- | --- |
| Cùng password, hai lần encode ra kết quả khác nhau | Salt mới trên từng lần encode | Bình thường; dùng `matches` |
| `encode(raw).equals(stored)` luôn false | Tạo hash mới khác salt | Dùng `matches(raw, stored)` |
| `There is no PasswordEncoder mapped for id "null"` | Hash thiếu prefix hoặc mapping | Phân loại/migrate format cũ |
| BCrypt trực tiếp không nhận giá trị có `{bcrypt}` | Raw encoder không parse delegating prefix | Dùng đúng encoder tương ứng |
| Đổi encoder khiến user cũ không login được | Format hash cũ không còn được hỗ trợ | Verify legacy có kiểm soát, rehash hoặc reset |
| Password Unicode dài gây bất ngờ | Giới hạn byte/normalization | Kiểm thử và thống nhất policy |
| Login chậm/CPU cao | Cost quá lớn hoặc thiếu rate limit | Benchmark, kiểm soát concurrency |
| Dùng SHA-256(password) | Hash quá nhanh cho password | Dùng bcrypt/Argon2id/scrypt/PBKDF2 phù hợp |
| Dùng `{noop}password` production | Lưu plaintext dưới identifier NoOp | Loại bỏ và migrate/reset |
| Tìm cách “decrypt hash để email lại mật khẩu” | Nhầm password hashing với encryption | Dùng password reset |

## 12. Checklist và câu hỏi tự kiểm tra

- [ ] Database chỉ lưu encoded password; không lưu raw password hoặc khóa decrypt password.
- [ ] Encoder dùng thuật toán KDF chuẩn, salt ngẫu nhiên và cost đã benchmark.
- [ ] Đăng ký/đổi password dùng `encode`; đăng nhập dùng `matches`.
- [ ] Hiểu prefix `{id}` và cách migrate hash legacy.
- [ ] Có kế hoạch `upgradeEncoding`/rehash an toàn khi tăng cost hoặc đổi thuật toán.
- [ ] Test đúng/sai password, Unicode/khoảng trắng, input dài, format legacy và concurrency.
- [ ] Có HTTPS, rate limit, reset password an toàn và bảo vệ logs/backups.

**Câu hỏi:**

1. **Password hashing khác encryption ở đâu?** Password hashing nhằm xác minh ứng viên mà không cần decrypt; encryption có khóa để phục hồi plaintext.
2. **Vì sao SHA-256(password) đơn lẻ không đủ?** Vì quá nhanh cho offline password guessing.
3. **Hai hash cùng password có cần bằng nhau?** Không. Salt ngẫu nhiên khiến chuỗi encoded thường khác; `matches` vẫn đúng.
4. **`{bcrypt}` có phải bí mật không?** Không, đó là id để `DelegatingPasswordEncoder` chọn encoder.
5. **`upgradeEncoding` có tự lưu hash mới?** Không, ứng dụng/provider tích hợp phải thực hiện cập nhật.
6. **Bcrypt có thể coi 72 ký tự Unicode tương đương 72 byte không?** Không, giới hạn cần hiểu ở mức byte/implementation.
7. **Có thể giải mã hash để giúp người dùng quên mật khẩu không?** Không, dùng luồng reset mật khẩu.
8. **Hashing mạnh có thay được rate limiting hoặc HTTPS không?** Không, cần phòng thủ nhiều lớp.

**Ghi nhớ:** `PasswordEncoder` của Spring Security là API **hash và xác minh**, không phải API mã hóa để giải mã. Khi đăng ký gọi `encode(rawPassword)`, khi login gọi `matches(rawPassword, storedHash)`. Dùng password KDF có salt/work factor phù hợp, quản lý `{id}` và migration; không lưu plaintext, không dùng SHA-256(password) hoặc NoOp làm hệ thống lưu mật khẩu thật.
