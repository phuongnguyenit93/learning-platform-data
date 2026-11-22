# Kiểm thử PasswordEncoder và tính tương thích với dữ liệu băm được lưu trong Spring Security

## 1. Mục tiêu bài học

Ứng dụng Java dùng Spring Security thường lưu **bản băm mật khẩu** trong cơ sở dữ liệu, không lưu mật khẩu gốc. Sau nhiều năm vận hành, dữ liệu có thể bao gồm các phiên bản thuật toán hoặc thông số khác nhau: bcrypt cost 10, bcrypt cost 12, PBKDF2 phiên bản cũ, Argon2, hoặc một số bản ghi di sản không có tiền tố thuật toán.

Một thay đổi trong bean `PasswordEncoder` có thể khiến **người dùng cũ không đăng nhập được**, dù mật khẩu họ nhập hoàn toàn đúng. Nguy hiểm hơn, một cách “sửa nhanh” bằng fallback `noop` có thể vô tình chấp nhận plaintext, làm suy yếu bảo mật của toàn hệ thống.

Đề bài **“Kiểm thử PasswordEncoder và tính tương thích với dữ liệu băm được lưu”** đòi hỏi kiểm tra cả ba hướng:

1. **Tạo hash mới:** `encode(rawPassword)` phát sinh định dạng và thuật toán theo chính sách hiện tại.
2. **Xác minh hash đã lưu:** `matches(rawPassword, storedEncodedPassword)` vẫn xử lý đúng các bản ghi được phép, bao gồm phiên bản cũ.
3. **Nâng cấp an toàn:** `upgradeEncoding(storedHash)` và `UserDetailsPasswordService` hỗ trợ rehash sau khi **mật khẩu thật đã được xác thực**, không phải đổi hash trực tiếp khi không biết raw password.

Kết thúc bài, bạn có thể viết JUnit 5 tests kiểm tra round-trip, salt, mật khẩu sai, prefix, legacy hash, versioned encoder, upgrade, DaoAuthenticationProvider, lưu/truy xuất DB và các trường hợp lỗi. Ví dụ tương thích **Java 17+ / Spring Security 6.x**. Bài có chương trình Java 17 chạy bằng `javac/java` để nhận diện cấu trúc dữ liệu và dự án Maven dùng Spring Security để test việc so khớp mật mã thật.

> **Nguyên tắc:** Không kiểm thử bằng cách so sánh `encode(raw)` với hash đã lưu qua `String.equals`. Thuật toán có salt sẽ sinh hash khác nhau cho cùng một password. Luôn dùng `matches(raw, storedHash)` và thực thi đúng thuật toán/phiên bản gắn với dữ liệu đã lưu.

## 2. Phân biệt encode, matches và upgradeEncoding

Giao diện `org.springframework.security.crypto.password.PasswordEncoder` có ba thao tác chính:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

Đoạn trên minh họa bản chất API, **không phải file mã nguồn để tự tạo interface**. Hãy import và dùng interface từ dependency Spring Security.

### 2.1. `encode`: tạo biểu diễn lưu trữ

~~~text
rawPassword = "a-strong-password"
          |
          v
BCryptPasswordEncoder.encode(rawPassword)
          |
          v
"$2a$12$..."  (salt + cost được nhúng vào định dạng bcrypt)
~~~

Với `DelegatingPasswordEncoder`, đầu ra thông thường là:

~~~text
{bcrypt}$2a$12$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
^^^^^^^^  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  id                  bcrypt payload, gồm version/cost/salt/hash
~~~

Chuỗi trên chỉ là **hình dạng minh họa**, không phải bcrypt hash hợp lệ để đưa vào database.

Hash **không cần giống nhau** giữa hai lần gọi `encode`. BCrypt sinh salt ngẫu nhiên nên `encode("secret")` nhiều lần có thể cho các chuỗi khác nhau, nhưng mọi chuỗi vẫn phải xác minh được cùng password gốc.

### 2.2. `matches`: xác thực, không giải mã

~~~java
boolean ok = encoder.matches(rawSubmittedPassword, hashReadFromDatabase);
~~~

- `rawSubmittedPassword` là thông tin người dùng vừa nhập khi login.
- `hashReadFromDatabase` là chuỗi đã lưu từ lần signup/đổi password trước.
- `matches` chọn thuật toán, đọc salt/cost/parameters từ stored format rồi kiểm tra.
- Không có phép “decrypt bcrypt thành password gốc”.

Test đúng:

~~~java
String stored = encoder.encode("Correct-Horse-42!");
assertTrue(encoder.matches("Correct-Horse-42!", stored));
assertFalse(encoder.matches("Wrong-Horse-42!", stored));
~~~

Test sai:

~~~java
String stored = encoder.encode("Correct-Horse-42!");
// Không dùng: bcrypt/PBKDF2 salted có thể tạo hash khác mỗi lần.
assertEquals(stored, encoder.encode("Correct-Horse-42!"));
~~~

### 2.3. `upgradeEncoding`: tín hiệu, không tự thay DB

`upgradeEncoding(storedHash)` trả về `true` khi encoder cho rằng hash nên được tạo lại theo policy mới. Ví dụ:
- dữ liệu cũ có `{pbkdf2@SpringSecurity_v5_8}` nhưng phiên bản mới tạo `{bcrypt}`;
- bcrypt hash có cost thấp hơn cost của encoder hiện hành (tùy implementation);
- stored hash có ID khác `idForEncode`.

**Không được suy ra chỉ gọi `upgradeEncoding()` là hash trong DB thay đổi.** Cần cơ chế có raw password hợp lệ (thường sau login thành công), tạo hash mới và ghi lại bằng `UserDetailsPasswordService` hoặc migration service phù hợp.

## 3. Định dạng lưu trữ của DelegatingPasswordEncoder

Spring Security cung cấp `PasswordEncoderFactories.createDelegatingPasswordEncoder()`. `DelegatingPasswordEncoder` lưu dữ liệu theo mẫu:

~~~text
{id}encodedPassword
~~~

Ví dụ:

| Hash lưu trong DB | Cách diễn giải | Lưu ý |
|---|---|---|
| `{bcrypt}$2a$10$...` | Bcrypt, cost 10 | Delegate sang `BCryptPasswordEncoder` |
| `{bcrypt}$2b$12$...` | Bcrypt, cost 12 | Thuật toán/cost được kiểm tra khi matches |
| `{pbkdf2@SpringSecurity_v5_8}...` | PBKDF2 với tham số profile Spring Security 5.8 | Cần mapping đúng ID phiên bản |
| `{scrypt@SpringSecurity_v5_8}...` | scrypt với profile phiên bản cụ thể | Cần dependency/parameters tương ứng |
| `{argon2@SpringSecurity_v5_8}...` | Argon2 profile versioned | Cần thư viện hỗ trợ, chẳng hạn Bouncy Castle tùy build |
| `$2a$10$...` | Bcrypt raw **không có** `{bcrypt}` prefix | Delegating encoder mặc định có thể báo unmapped ID `null` |
| `{unknown}...` | ID lạ hoặc không được cấu hình | Phải từ chối, không đoán |
| `{noop}plaintext` | Bản ghi plaintext theo legacy mapping | **Không dùng làm giải pháp production** |

**Cực kỳ quan trọng:** `PasswordEncoderFactories.createDelegatingPasswordEncoder()` trong Spring Security 6.5 chứa các mapping **lịch sử** để phục vụ tương thích, kể cả `noop`, MD4/MD5 và một số định dạng legacy. Điều đó **không có nghĩa các thuật toán đó an toàn để tạo password mới hoặc nên tiếp tục cho đăng nhập mãi mãi**.

Trong hệ thống yêu cầu allowlist nghiêm ngặt, tạo một `DelegatingPasswordEncoder` có **chỉ các ID được chấp nhận**, thay vì dùng mọi mapping mặc định. Định danh và policy cho hash cũ phải dựa trên **inventory dữ liệu và hợp đồng migration**, không tin bất kỳ tiền tố nào là hợp lệ chỉ vì thư viện biết cách so khớp.

### 3.1. `{id}` không phải bí mật

ID và thông số cost/iteration xuất hiện công khai trong hash là điều bình thường. Bảo mật không dựa trên việc giấu tên thuật toán; nó dựa trên thuật toán thích hợp, salt, work factor, độ mạnh password và quyền bảo vệ DB.

### 3.2. Versioned ID quan trọng như thế nào?

Ví dụ hai profile PBKDF2 trong cùng họ thuật toán có thể dùng iteration, salt length, key length hoặc PRF khác nhau. Nếu bạn đổi mapping của ID `pbkdf2` đang được dùng trong DB sang một profile mới mà không đổi ID, bản ghi cũ có thể **không còn so khớp**.

Mẫu phù hợp:
- `{pbkdf2@SpringSecurity_v5_8}` giữ nguyên nghĩa profile cũ;
- bản ghi mới dùng ID/thuật toán hiện hành;
- test fixtures cho cả hai lớp dữ liệu;
- sau khi xác thực thành công, có thể rehash thành ID mới.

**Tên ID là hợp đồng lưu trữ**, không chỉ là nhãn hiển thị.

## 4. Cách Spring Security kiểm tra password trong luồng login

Trong Servlet stack, `DaoAuthenticationProvider` dùng `UserDetailsService` để nạp user và `PasswordEncoder` để xác minh password:

~~~text
POST /login (raw password)
         |
         v
UsernamePasswordAuthenticationFilter
         |
         v
AuthenticationManager / ProviderManager
         |
         v
DaoAuthenticationProvider
         |
         +-- UserDetailsService.loadUserByUsername(username)
         |       |
         |       v
         |   UserDetails.getPassword()
         |       |
         |       v
         +-- PasswordEncoder.matches(raw, storedHash)
         |
         +-- kiểm tra trạng thái account + chính sách
         |
         +-- có cần upgradeEncoding?
         |       |
         |       v
         |   UserDetailsPasswordService.updatePassword(user, newHash)
         |
         v
Authenticated principal hoặc failure
~~~

Trong thực tế thứ tự các pre/post authentication checks và password upgrade tùy provider implementation; sơ đồ cho thấy **trách nhiệm** chứ không phải call stack đầy đủ.

- Nếu password sai, không được cập nhật hash.
- Nếu stored hash thiếu mapping/không hợp lệ, không được fallback sang compare plaintext.
- Nếu password đúng và upgrade được hỗ trợ, provider có thể tạo hash mới rồi gọi `UserDetailsPasswordService`.
- Việc cập nhật hash cần bảo vệ transaction/concurrency (đặc biệt nếu người dùng vừa thay password ở một session khác).

**Spring Security không tự động sửa dữ liệu cũ chỉ vì bạn thêm PasswordEncoder bean.** Trong cơ sở dữ liệu thật, `UserDetailsPasswordService` phải cập nhật được record, không thể chỉ trả một bản `UserDetails` giả mà không persist.

## 5. Tại sao “dữ liệu băm đã lưu” khó tương thích?

Một số lỗi phổ biến khi nâng cấp hoặc đổi dịch vụ:

1. **Thiếu prefix:** trước kia dùng trực tiếp `BCryptPasswordEncoder` tạo `$2a$...`; sau này đổi sang `DelegatingPasswordEncoder`, nó cần `{bcrypt}`.
2. **Sử dụng sai ID:** dữ liệu là bcrypt nhưng prepend `{pbkdf2}`, dẫn tới mismatched verifier.
3. **Cắt chuỗi trong DB:** cột `VARCHAR(60)` từng chứa bcrypt raw 60 ký tự, nhưng `{bcrypt}` prefix làm dài hơn; versioned Argon2/scrypt còn dài hơn.
4. **Thay đổi profile thuật toán:** cùng tên PBKDF2 nhưng iteration/PRF/salt khác nhau.
5. **Không nhất quán charset:** legacy encoder băm byte theo charset khác UTF-8; Java Unicode phải được xử lý đúng hợp đồng.
6. **Không nhất quán canonicalization:** Java/service A trim hoặc normalize password, service B giữ nguyên input. Password thường phải được xử lý **như bí mật nguyên văn**; không tự `trim()`/`toLowerCase()`.
7. **Sai định dạng prefix có brace:** `{bcrypt}`, `{BCRYPT}`, `{bcrypt ` không tương đương trừ khi mapping được định nghĩa đúng.
8. **Chuyển từ password hash sang encryption:** hai phương pháp khác nhau; không giải mã được bcrypt để chuyển sang thuật toán mới.
9. **Pepper không còn:** nếu legacy PBKDF2 dùng secret/pepper ngoài DB mà secret bị mất, không thể verify password cũ chỉ từ hash.
10. **Thư viện/thuật toán hỗ trợ khác nhau:** Argon2, scrypt có thể cần dependency/provider và cấu hình khác.
11. **Cắt ký tự bí mật dài:** bcrypt truyền thống giới hạn khoảng 72 byte input hiệu dụng; khả năng tương thích password dài cần được test riêng khi đổi từ bcrypt sang thuật toán khác.
12. **Chuyển schema nhưng không migrate user service:** DB đã có prefixed hash, nhưng ORM/mapper loại dấu `{...}` hoặc dùng sai cột.

Giải pháp là **inventory và test bằng fixture thật đã được cho phép** trước khi thay cấu hình, không thử đoán thuật toán lúc login dựa trên password hay cho phép tất cả fallback.

## 6. Test matrix tối thiểu cho PasswordEncoder

| Ca kiểm thử | Input và stored hash | Kỳ vọng |
|---|---|---|
| Round-trip | `raw` và `encode(raw)` | `matches` true |
| Sai password | `otherRaw` vs storedHash | false |
| Salt | Hai lần encode cùng raw | Hai chuỗi khác, cả hai matches true |
| New format | Hash vừa encode | Bắt đầu bằng ID được duyệt, ví dụ `{bcrypt}` |
| Prefixed bcrypt legacy | `{bcrypt}` + bcrypt cost 10 | matches true |
| Unprefixed bcrypt legacy | `$2a$10$...` | matches true **chỉ nếu migration policy cho phép** |
| Versioned PBKDF2 | `{pbkdf2@SpringSecurity_v5_8}` + payload đúng | matches true |
| Unknown ID | `{evil}...` | Fail closed |
| Plaintext | `password123` | Fail closed |
| `{noop}` | `{noop}password123` | Fail closed với allowlist strict |
| Sai prefix | `{pbkdf2}` + bcrypt payload | Fail closed |
| Bcrypt bị truncate | Stored hash mất cuối | Fail closed |
| Legacy sai thuật toán | Raw MD5 nhưng gắn ID bcrypt | Fail closed |
| Upgrade old ID | Stored PBKDF2, current encode bcrypt | `upgradeEncoding` true |
| Upgrade old cost | BCrypt cost 10, current strength 12 | `upgradeEncoding` true nếu provider hỗ trợ |
| No upgrade current | BCrypt cost 12 hiện tại | `upgradeEncoding` false |
| Dao auth với legacy | UserDetails trả old hash và raw đúng | Auth success, migration nếu configured |
| Dao auth sai password | Old hash và raw sai | Auth fail, **không** thay hash |
| Đồng thời migration/reset | Hai session cập nhật cùng account | Không overwrite password mới |
| Database round-trip | Serialize/deserialize hash qua DB | Chuỗi giữ nguyên, matches vẫn đúng |

**Ưu tiên thực hiện cả unit test lẫn integration test.** Unit test cho encoder giúp tìm lỗi thuật toán/mapping; integration test database mới phát hiện cột ngắn, ORM trim, collation, transaction và vấn đề cập nhật.

## 7. Ví dụ Java 17 độc lập: nhận diện cấu trúc dữ liệu đã lưu

Chương trình sau **không thử password, không dùng Spring**. Nó minh họa bước inventory an toàn: xác định xem một chuỗi có prefix `{id}` hợp lệ về *cấu trúc* hay có vẻ là bcrypt raw. Đây **không phải xác minh mật mã**, chỉ là phân loại để lập kế hoạch migration.

File `StoredHashInspector.java`:

~~~java
import java.util.regex.Pattern;

public final class StoredHashInspector {

    private static final Pattern BCRYPT_SHAPE = Pattern.compile(
            "^\\$2[aby]\\$(0[4-9]|[12][0-9]|3[01])\\$" +
            "[./A-Za-z0-9]{53}$");

    public static String classify(String stored) {
        if (stored == null || stored.isEmpty()) {
            return "EMPTY";
        }
        if (stored.startsWith("{")) {
            int closing = stored.indexOf('}');
            if (closing <= 1 || closing == stored.length() - 1) {
                return "MALFORMED_PREFIX";
            }
            String id = stored.substring(1, closing);
            String payload = stored.substring(closing + 1);
            if ("bcrypt".equals(id)) {
                return BCRYPT_SHAPE.matcher(payload).matches()
                        ? "PREFIXED_BCRYPT_SHAPE" : "MALFORMED_BCRYPT";
            }
            if ("pbkdf2@SpringSecurity_v5_8".equals(id)) {
                return "VERSIONED_PBKDF2_UNVERIFIED";
            }
            return "UNAPPROVED_ID";
        }
        return BCRYPT_SHAPE.matcher(stored).matches()
                ? "LEGACY_BCRYPT_SHAPE" : "UNRECOGNIZED";
    }

    public static void main(String[] args) {
        String illustrativeBcrypt = "$2a$10$"
                + "a".repeat(53);
        System.out.println(classify("{bcrypt}" + illustrativeBcrypt));
        System.out.println(classify(illustrativeBcrypt));
        System.out.println(classify("{noop}secret"));
        System.out.println(classify("secret"));
        System.out.println(classify("{bcrypt}broken"));
        System.out.println(classify(null));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac StoredHashInspector.java
java StoredHashInspector
~~~

**Stdout chính xác:**

~~~text
PREFIXED_BCRYPT_SHAPE
LEGACY_BCRYPT_SHAPE
UNAPPROVED_ID
UNRECOGNIZED
MALFORMED_BCRYPT
EMPTY
~~~

Chuỗi `"a".repeat(53)` chỉ mô phỏng độ dài/ký tự hợp lệ để kiểm tra **cấu trúc**, không phải hash được tạo từ password thực. Chương trình **không thể chứng minh hash hợp lệ về mật mã**. Đừng dùng `classify()` làm `matches()` hay làm điều kiện cấp login.

## 8. Dự án Maven Spring Security 6.5: encoder allowlist và JUnit tests

Mục tiêu là tạo **một dự án kiểm thử thành phần không cần khởi động web server**. `PasswordEncoderConfiguration` là cấu hình có thể dùng lại trong ứng dụng Spring Boot; JUnit khởi tạo cấu hình trực tiếp để test logic mà không phải chạy servlet.

### 8.1. Cấu trúc

~~~text
password-compatibility-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/password/
    │   └── PasswordEncoderConfiguration.java
    └── test/java/com/example/password/
        └── PasswordEncoderCompatibilityTest.java
~~~

### 8.2. `pom.xml` đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>password-compatibility-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Spring Boot 3.5.x quản lý các dependency Spring Security 6.5.x tương thích; dùng Maven/Java 17+. File POM không cần `spring-boot-maven-plugin` vì ở đây chỉ chạy test thành phần, **không đóng gói Spring Boot main application**.

### 8.3. `PasswordEncoderConfiguration.java`: default nghiêm ngặt

~~~java
package com.example.password;

import java.util.Map;
import java.util.regex.Pattern;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;

@Configuration
public class PasswordEncoderConfiguration {

    @Bean
    public PasswordEncoder passwordEncoder() {

        Map<String, PasswordEncoder> approved = Map.of(
                "bcrypt", new BCryptPasswordEncoder(12),
                "pbkdf2@SpringSecurity_v5_8",
                    Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8()
        );

        DelegatingPasswordEncoder encoder =
                new DelegatingPasswordEncoder("bcrypt", approved);

        // Chỉ hỗ trợ legacy bcrypt raw đã được inventory,
        // KHÔNG fallback sang NoOp hoặc mọi ID không biết.
        encoder.setDefaultPasswordEncoderForMatches(
                new LegacyBcryptOnly());
        return encoder;
    }

    private static final class LegacyBcryptOnly
            implements PasswordEncoder {

        private static final Pattern BCRYPT = Pattern.compile(
                "^\\$2[aby]\\$(0[4-9]|[12][0-9]|3[01])\\$"
                + "[./A-Za-z0-9]{53}$");

        private final BCryptPasswordEncoder bcrypt =
                new BCryptPasswordEncoder();

        @Override
        public String encode(CharSequence rawPassword) {
            throw new UnsupportedOperationException(
                    "Legacy encoder must never issue new hashes");
        }

        @Override
        public boolean matches(
                CharSequence rawPassword, String stored) {
            if (rawPassword == null || stored == null
                    || !BCRYPT.matcher(stored).matches()) {
                return false;
            }
            return bcrypt.matches(rawPassword, stored);
        }
    }
}
~~~

**Cơ chế:**
- `idForEncode="bcrypt"` ⇒ mọi password **mới** được encode với bcrypt strength 12 và prefix `{bcrypt}`.
- Hash mang `{bcrypt}` ⇒ so khớp bởi BCrypt encoder, kể cả cost 10 trước đây (cost nằm trong hash).
- Hash `{pbkdf2@SpringSecurity_v5_8}` ⇒ delegate theo profile PBKDF2 chính xác (vì đã cấp phép).
- Hash cũ dạng `$2a$...` không có prefix ⇒ fallback chỉ nhận **đúng cấu trúc bcrypt raw** và kiểm tra bcrypt thật.
- Hash `{noop}secret`, `{unknown}...`, `plaintext` ⇒ không hợp lệ, **fail closed**.
- `LegacyBcryptOnly.encode()` bị cấm; fallback là **đường verify một chiều**, không phải đường tạo credential mới.

**Lưu ý về `setDefaultPasswordEncoderForMatches`:** fallback nhận **toàn bộ** chuỗi `encodedPassword` khi ID không có mapping, không chỉ phần sau `{id}`. Vì vậy nó phải tự kiểm tra nghiêm ngặt chuỗi raw bcrypt. Đừng đặt fallback thành `NoOpPasswordEncoder` hoặc một BCrypt decoder không kiểm tra định dạng nếu điều đó khiến các loại ID lạ được coi là hợp lệ.

Trong product thật, nếu DB không có raw bcrypt legacy, **không cần fallback nào**: dùng encoder với allowlist và để unmatched ID fail closed. Nếu có algorithm legacy khác, thêm đúng profile cần thiết trong thời gian migration và xóa sau khi đã nâng cấp.

### 8.4. JUnit 5: kiểm thử PasswordEncoder và compatibility

File `src/test/java/com/example/password/PasswordEncoderCompatibilityTest.java`:

~~~java
package com.example.password;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.Authentication;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

import static org.junit.jupiter.api.Assertions.*;

class PasswordEncoderCompatibilityTest {

    private final PasswordEncoder encoder =
            new PasswordEncoderConfiguration().passwordEncoder();

    private static final String RAW = "S3cret-for-tests-2026!";

    @Test
    void newPasswordHasApprovedPrefixAndMatches() {
        String stored = encoder.encode(RAW);

        assertTrue(stored.startsWith("{bcrypt}$2"));
        assertTrue(encoder.matches(RAW, stored));
        assertFalse(encoder.matches("wrong-password", stored));
    }

    @Test
    void saltMakesEncodedStringsDifferent() {
        String first = encoder.encode(RAW);
        String second = encoder.encode(RAW);

        assertNotEquals(first, second);
        assertTrue(encoder.matches(RAW, first));
        assertTrue(encoder.matches(RAW, second));
    }

    @Test
    void legacyBcryptWithoutPrefixStillMatches() {
        String legacy =
                new BCryptPasswordEncoder(10).encode(RAW);

        assertTrue(encoder.matches(RAW, legacy));
        assertFalse(encoder.matches("wrong-password", legacy));
        assertTrue(encoder.upgradeEncoding(legacy));
    }

    @Test
    void prefixedOldBcryptCostStillMatches() {
        String oldCost =
                "{bcrypt}" + new BCryptPasswordEncoder(10).encode(RAW);

        assertTrue(encoder.matches(RAW, oldCost));
        assertTrue(encoder.upgradeEncoding(oldCost));
    }

    @Test
    void versionedPbkdf2FromApprovedProfileStillMatches() {
        PasswordEncoder previous =
                Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();

        String oldStored = "{pbkdf2@SpringSecurity_v5_8}"
                + previous.encode(RAW);

        assertTrue(encoder.matches(RAW, oldStored));
        assertFalse(encoder.matches("wrong-password", oldStored));
        assertTrue(encoder.upgradeEncoding(oldStored));
    }

    @Test
    void currentEncodingDoesNotRequireUpgrade() {
        String current = encoder.encode(RAW);

        assertTrue(encoder.matches(RAW, current));
        assertFalse(encoder.upgradeEncoding(current));
    }

    @Test
    void plaintextAndUnapprovedIdsMustFailClosed() {
        assertFalse(encoder.matches(RAW, RAW));
        assertFalse(encoder.matches(RAW, "{noop}" + RAW));
        assertFalse(encoder.matches(RAW, "{unknown}" + RAW));
        assertFalse(encoder.matches(RAW, "{md5}123"));
        assertFalse(encoder.matches(RAW, "{bcrypt}broken"));
    }

    @Test
    void legacyBcryptDoesNotAcceptWrongPrefix() {
        String bcrypt =
                new BCryptPasswordEncoder(10).encode(RAW);

        assertFalse(encoder.matches(
                RAW, "{pbkdf2@SpringSecurity_v5_8}" + bcrypt));
        assertFalse(encoder.matches(RAW, bcrypt.substring(0, 20)));
    }

    @Test
    void daoProviderCanUpgradeVerifiedLegacyPassword() {

        String legacy = new BCryptPasswordEncoder(10).encode(RAW);

        UserDetails user = User.withUsername("alice")
                .password(legacy)
                .roles("USER")
                .build();

        InMemoryUserDetailsManager store =
                new InMemoryUserDetailsManager(user);

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(store);
        provider.setPasswordEncoder(encoder);
        provider.setUserDetailsPasswordService(store);

        Authentication verified = provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "alice", RAW));

        assertTrue(verified.isAuthenticated());

        String updated = store.loadUserByUsername("alice")
                .getPassword();

        assertTrue(updated.startsWith("{bcrypt}"));
        assertTrue(encoder.matches(RAW, updated));
        assertNotEquals(legacy, updated);
    }

    @Test
    void badPasswordDoesNotTriggerMigration() {

        String old = new BCryptPasswordEncoder(10).encode(RAW);

        UserDetails user = User.withUsername("bob")
                .password(old)
                .roles("USER")
                .build();

        InMemoryUserDetailsManager store =
                new InMemoryUserDetailsManager(user);

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(store);
        provider.setPasswordEncoder(encoder);
        provider.setUserDetailsPasswordService(store);

        assertThrows(BadCredentialsException.class,
                () -> provider.authenticate(
                        UsernamePasswordAuthenticationToken
                                .unauthenticated("bob", "WRONG")));

        assertEquals(old, store.loadUserByUsername("bob")
                .getPassword());
    }
}
~~~

**Vì sao test này đáng tin cậy hơn test nhìn prefix?**
- Thực thi `matches` đối với bcrypt/PBKDF2 thật, không dùng fake verifier.
- Kiểm tra salt nên hai encoded strings khác nhau nhưng cả hai xác minh được.
- Có legacy bcrypt **không prefix** và prefixed bcrypt cost 10.
- Không cho `{noop}`, plaintext hoặc ID không được duyệt.
- Kiểm tra `upgradeEncoding` với legacy và current.
- DaoAuthenticationProvider kiểm tra password người dùng và dùng `InMemoryUserDetailsManager` (có `UserDetailsPasswordService`) để mô phỏng nâng cấp hash sau login.
- Đảm bảo password sai **không thực hiện migration**.

Chạy:

~~~bash
mvn clean test
~~~

**Kỳ vọng:** Maven/JUnit chạy **10 test methods**, không có failures/errors; số liệu thống kê và thời gian thực tế do phiên bản Maven Surefire/hardware quyết định. Các hash BCrypt/PBKDF2 tạo ra mỗi lần là ngẫu nhiên, vì vậy không dùng hash literal làm stdout kỳ vọng. Kiểm tra report `target/surefire-reports/` và exit code 0. Nếu thêm test integration, phân biệt unit crypto tests và DB tests trong pipeline CI.

**Giới hạn:** test DaoAuthenticationProvider ở trên dùng **in-memory repository**, không chứng minh database thật có thể cập nhật `password_hash` trong transaction hay query có đúng version/tenant. Phần tiếp theo trình bày cần test gì ở storage.

## 9. Vì sao fallback legacy phải bị giới hạn?

Một đề xuất thường gặp khi gặp:

~~~text
java.lang.IllegalArgumentException:
  There is no PasswordEncoder mapped for the id "null"
~~~

là thêm:

~~~java
delegating.setDefaultPasswordEncoderForMatches(
        NoOpPasswordEncoder.getInstance());
~~~

**Đây là cách nguy hiểm trong production** vì nó có thể chấp nhận bản ghi không định dạng như password plaintext. Nếu DB bị sửa hoặc có đường import dữ liệu lỗi, bạn có thể tạo lối đăng nhập yếu.

### Phương án tốt hơn theo thứ tự ưu tiên

1. **Điều tra format trước:** lấy thống kê dạng hash đã lưu (ID, length, pattern; không log raw hash) từ nguồn dữ liệu được phép, đối chiếu lịch sử hệ thống.
2. **Nếu chắc chắn toàn bộ raw hash là bcrypt:** thêm `{bcrypt}` prefix bằng migration DB **sau khi xác nhận**; payload bcrypt không đổi. Đây là thao tác metadata, không phải rehash.
3. **Nếu DB là nhiều loại:** dùng `DelegatingPasswordEncoder` với mapping allowlist và fixture cho từng ID; kiểm tra legacy raw theo regex rất chặt như ví dụ.
4. **Nếu password được lưu plaintext hoặc hash yếu:** lập kế hoạch loại bỏ, giới hạn thời gian verify, hỗ trợ reset/re-auth và migration theo risk; không tuyên bố yếu tố này đã an toàn vì có prefix.
5. **Không biết thuật toán hoặc pepper đã mất:** không đoán bằng cách thử ngẫu nhiên các decoder; cần password reset/re-enrollment hợp lệ.

**Không gán `{bcrypt}` cho một chuỗi bất kỳ nhìn giống Base64/hex**. Độ dài, cost và regex chỉ là chứng cứ hình dạng; muốn xác minh đúng, cần test hợp lệ với password của fixture được phép và thuật toán thực.

## 10. Khả năng tương thích khi thay bcrypt work factor

BCrypt chứa thông tin version và cost trong hash:

~~~text
$2a$10$.....................................................
 ^   ^^
 |   └─ cost = 10
 └──── version identifier
~~~

Nếu ứng dụng phát hành password mới với cost 12, bcrypt verifier phù hợp **thường vẫn kiểm chứng được hash cost 10**, vì cost và salt của bản ghi được nhúng trong payload. `BCryptPasswordEncoder(12).upgradeEncoding(oldCost10)` có thể trả true, trong khi cost 12 hiện tại không cần nâng tiếp.

**Lưu ý kiểm thử hiệu năng:** cost tăng theo cấp số mũ; không thay cost 10→16 ở production chỉ vì “càng cao càng tốt”. Đo latency p95/p99, CPU và tải khi peak login/credential stuffing. Spring Security khuyến nghị tune adaptive one-way function theo phần cứng và threat model, khoảng một giây verify là điểm tham chiếu tài liệu, không phải SLA áp dụng mọi hệ thống.

### 10.1. Hash length và DB column

BCrypt raw phổ biến có độ dài 60 ký tự ASCII; thêm `{bcrypt}` thành **68 ký tự**. Nếu cột hiện tại là `VARCHAR(60)`, việc migration prefix hoặc đổi algorithm có thể gây lỗi hoặc truncation.

Các bước an toàn:
1. Kiểm tra schema và constraint của `password_hash`.
2. Mở rộng sang `VARCHAR(255)` hoặc `TEXT` theo chuẩn dữ liệu ứng dụng, tránh giới hạn nhỏ tùy tiện.
3. Deploy reader hỗ trợ format cũ và mới.
4. Migration dữ liệu trong transaction/batch, ghi lại số record.
5. Verify với fixture sau database round-trip, không chỉ in-memory.
6. Chỉ sau khi khả năng đọc format mới hoạt động ở mọi replica mới bật writer mới.

Không tự động ép `LEFT(password_hash, 60)` hoặc cắt chuỗi để vừa schema; hash bị cắt không thể xác minh đúng.

## 11. Tương thích PBKDF2, scrypt và Argon2

BCrypt là lựa chọn phổ biến, nhưng hệ thống có thể có PBKDF2/scrypt/Argon2. Tên thuật toán **chưa đủ** để giữ tương thích:

| Loại | Thông số cần giữ | Lỗi migration thường gặp |
|---|---|---|
| PBKDF2 | PRF/HMAC, iteration count, derived key length, salt length, secret/pepper | Dùng mapping mới cho hash cũ; mất pepper |
| scrypt | CPU/memory parameters, salt, output length | Dùng profile phiên bản khác hoặc thiếu dependency |
| Argon2 | Argon2id/variant, memory, iterations, parallelism, salt, version | Thay parameters/version hoặc thiếu Bouncy Castle |
| BCrypt | Version, cost, salt, input byte policy | DB cắt chuỗi hoặc xử lý password dài không nhất quán |

**Lưu ID phiên bản** trong trường password hash hoặc metadata nếu định dạng của thư viện không tự mã hóa đủ các thông số. Với Spring Security, các mapping versioned như `pbkdf2@SpringSecurity_v5_8` là ví dụ cách giữ profile kiểm chứng cũ mà vẫn tạo hash mới bằng thuật toán/phương án mới.

### 11.1. Kế hoạch migration khác thuật toán

Một phương án ít gián đoạn:
- Read path: chấp nhận các ID **được duyệt** hiện có.
- Write path: chỉ `encode` theo thuật toán/profile hiện hành.
- Login thành công: kiểm tra `upgradeEncoding`, rehash raw password vừa được xác minh và persist.
- Reset/change password: luôn dùng writer mới, không copy format cũ.
- Sau khi một tỷ lệ lớn user đã migrate, đặt mốc ngừng hỗ trợ legacy và buộc reset cho tài khoản chưa nâng.
- Không xóa bộ verify cũ trước khi không còn bản ghi cần nó, hoặc trước khi có chiến lược account recovery.

### 11.2. Tại sao không rehash trực tiếp từ hash cũ?

Sai:

~~~text
newHash = BCrypt( oldHash )
~~~

Nếu đó là password mới được lưu thì lúc login người dùng nhập raw password, verifier kiểm tra BCrypt(rawPassword, newHash) và **không khớp**. Bạn không có raw password từ old hash. Chỉ rehash khi password được cung cấp hợp lệ trong login/change-password/reset. Nếu không, yêu cầu người dùng đặt lại mật khẩu theo quy trình an toàn.

### 11.3. Compatibility với dữ liệu từ hệ thống khác

Một DB từ PHP/Node/Python có thể dùng bcrypt nhưng khác:
- cách encode Unicode thành bytes;
- policy trim/normalize password;
- giới hạn 72-byte bcrypt hoặc pre-hashing;
- version prefix, cost và salt;
- cột database/hàm serialize.

Trước migration, tạo fixtures trong hệ thống nguồn với **password giả** gồm ASCII, Unicode và độ dài biên, rồi kiểm tra Spring `matches`. Không vận chuyển mật khẩu thật hay gửi production hashes vào công cụ kiểm thử công khai.

## 12. Database integration test: tránh mất hash do ORM hoặc schema

Mẫu schema PostgreSQL minh họa:

~~~sql
CREATE TABLE app_users (
    id               BIGSERIAL PRIMARY KEY,
    username         VARCHAR(150) NOT NULL UNIQUE,
    password_hash    TEXT NOT NULL,
    enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    password_version BIGINT NOT NULL DEFAULT 0,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Đây là **schema nghiệp vụ minh họa**. Production có thể cần tenant ID, audit fields, password-change timestamp, cơ chế vô hiệu session và encryption at rest theo policy.

### 12.1. Đọc và ghi chuỗi chính xác

Test DB cần:
1. Insert hash bcrypt raw 60 ký tự và read lại chính xác.
2. Insert hash `{bcrypt}` dài hơn, read lại chính xác.
3. Insert hash PBKDF2/Argon2 (nếu được phép), read lại chính xác.
4. Không tự trim, cắt, thay case hoặc chuẩn hóa ký tự.
5. Cột không convert hash thành số hoặc dùng logic xử lý brace gây hỏng.
6. Có unique username/tenant mapping đúng và không nhầm tài khoản.
7. DB writer chỉ nhận output từ PasswordEncoder đã cấu hình.
8. Rollback khi update password và audit/session state thất bại.

### 12.2. Compare-and-set để chống ghi đè password mới

Giả sử người dùng login bằng hash cũ và hệ thống muốn upgrade. Cùng lúc, họ có thể đổi password ở một thiết bị khác. Đừng thực thi update:

~~~sql
UPDATE app_users
   SET password_hash = :newHash
 WHERE username = :username;
~~~

Câu trên có thể ghi đè hash mới **được người dùng đặt sau** bằng một hash tạo từ mật khẩu cũ, làm hồi sinh mật khẩu đã đổi.

Mẫu compare-and-set có thể dùng:

~~~sql
UPDATE app_users
   SET password_hash = :newEncodedHash,
       password_version = password_version + 1,
       updated_at = CURRENT_TIMESTAMP
 WHERE id = :userId
   AND password_hash = :expectedOldEncodedHash
   AND password_version = :expectedOldVersion
   AND enabled = TRUE;
~~~

- Nếu **1 row updated**: migration thắng phiên bản đúng.
- Nếu **0 row updated**: dữ liệu đã đổi hoặc account bị disable; **không retry ghi đè**, cần reload/check policy và có thể từ chối phiên login cũ.
- Toàn bộ thao tác migration dùng transaction và concurrency rules đã kiểm thử.
- Với case-insensitive DB collation, bảo đảm so sánh `password_hash` **đúng byte/case-sensitive** hoặc dựa vào version field đáng tin. Hash là dữ liệu nhạy với từng ký tự.

`UserDetailsPasswordService.updatePassword(UserDetails user, String newPassword)` nhận **newPassword đã encode**, còn `user.getPassword()` và business version có thể dùng làm điều kiện CAS. Service nên cập nhật đúng user ID/tenant, không chỉ username tự khai, và trả `UserDetails` mới tương ứng. Đây là ví dụ SQL, không phải toàn bộ repository Java độc lập.

## 13. Ví dụ UserDetailsPasswordService cho DB thật

Mảnh code mô tả Spring JDBC, dùng `username` và old hash làm điều kiện. Để chạy production cần bảo đảm username định danh duy nhất trong namespace, thêm version/tenant, transaction, row mapper và xử lý thành công khi xác thực theo policy.

~~~java
// Mảnh code minh họa trong một @Service đã có JdbcTemplate.
// UserDetailsPasswordService là interface Spring Security.

@Override
@Transactional
public UserDetails updatePassword(UserDetails user, String newHash) {
    int changed = jdbc.update("""
            UPDATE app_users
               SET password_hash = ?,
                   password_version = password_version + 1,
                   updated_at = CURRENT_TIMESTAMP
             WHERE username = ?
               AND password_hash = ?
               AND enabled = TRUE
            """, newHash, user.getUsername(), user.getPassword());

    if (changed != 1) {
        throw new IllegalStateException(
                "Password changed concurrently or user disabled");
    }

    return User.withUserDetails(user)
            .password(newHash)
            .build();
}
~~~

Đây là **đoạn minh họa tích hợp**, chưa phải file runnable độc lập: cần import `@Transactional`, `JdbcTemplate`, `UserDetailsPasswordService`, `UserDetails`, `User` và inject repository/JDBC đúng. Ứng dụng thực phải xử lý transaction/security exception theo yêu cầu UX, không đưa old/new hash vào log hoặc HTTP body.

**Cảnh báo về self-invocation:** nếu method `@Transactional` được gọi trực tiếp bên trong chính bean thay vì qua Spring proxy, transaction có thể không được kích hoạt. Test integration cần xác nhận rollback/concurrency thực, đặc biệt khi login nhiều node.

## 14. Thay đổi cấu hình password hashing theo rollout an toàn

Một chiến lược deployment theo từng giai đoạn:

### Giai đoạn 1 — Inventory (read-only)

- Xác định mọi storage format từ schema/metadata/thống kê ẩn danh: tỷ lệ prefixed bcrypt, raw bcrypt, PBKDF2 versioned, các ID cũ.
- Có fixture từ môi trường test/legacy system cho mỗi loại, bao gồm password Unicode và boundary length.
- Xác định thuật toán mạnh/yếu, phụ thuộc pepper/secret bên ngoài và khả năng chạy thư viện.
- Đo độ dài lớn nhất `password_hash` và quyền truy cập DB/log.
- Ghi nhận số tài khoản có format không thể xác định; không sửa ngay.

### Giai đoạn 2 — Reader tương thích

- Deploy `DelegatingPasswordEncoder` với allowlist các format cần thiết và legacy adapter nghiêm ngặt.
- Với DB chỉ raw bcrypt, có thể migration prefix `{bcrypt}` sau khi đã thử với fixture và backup.
- Viết tests cho matching và không matching, đặc biệt unknown ID/null/malformed.
- Thêm monitor nội bộ số logins dùng legacy format nhưng **không log raw hash/password**.

### Giai đoạn 3 — Writer mới + rehash-on-login

- Chỉ tạo hash mới bằng một algorithm/profile đã được phê duyệt.
- Nếu `upgradeEncoding` true sau password đúng, lưu hash mới qua service có CAS/transaction.
- Đảm bảo mọi replica đều **đọc được format mới** trước khi writer bắt đầu phát hành.
- Password change/reset luôn dùng writer mới và vô hiệu hóa session/token khi policy yêu cầu.

### Giai đoạn 4 — Dọn định dạng yếu

- Theo dõi tỷ lệ migration thành công và các tài khoản dormant.
- Với hash quá yếu hoặc dữ liệu mơ hồ, yêu cầu reset password thay vì duy trì `noop`/MD5 lâu dài.
- Dọn mapping legacy chỉ khi **không còn** user cần verify bằng format đó hoặc đã có recovery plan.
- Kiểm tra lại unauthorized algorithms, rate limit và các đo lường hiệu năng.

### Giai đoạn 5 — Rollback và điều tra

- Có rollback plan cho ứng dụng, nhưng **không rollback reader** nếu DB đã chứa hash được tạo bởi writer mới và reader cũ không hiểu.
- Log failure categories an toàn: unknown prefix, wrong password, disabled account, migration conflict, infrastructure error.
- Đặt alert cho tỷ lệ login failure tăng bất thường ngay sau release; không tiết lộ thông tin user existence qua response.

## 15. Security tests cần chạy riêng với compatibility tests

Dù PasswordEncoder match đúng, hệ thống vẫn có thể bị tấn công:
- Brute force, password spraying và credential stuffing: cần rate limit, MFA/passkey và monitoring.
- User enumeration: thông điệp/latency login cho username không tồn tại vs password sai.
- SQL injection ở repository lookup/update: dùng prepared statements, không nối username vào query.
- Hash leakage qua logs/exception/debugger: không log password/hash nguyên văn.
- Database exfiltration: giảm quyền truy cập và sử dụng adaptive hashing có work factor phù hợp.
- Compromised password: check password đã lộ khi tạo/đổi, không gọi service không tin cậy với raw password.
- Session fixation/hijacking: bảo vệ cookie/session và thu hồi khi đổi password.
- Timing side-channel: tránh hành vi quá khác biệt khiến attacker biết username tồn tại.
- Resource exhaustion: adaptive hash dùng CPU/memory; limit login trước hashing và theo account/source.
- DoS do migration: không đồng thời rehash hàng triệu users ở request path hoặc chạy CPU-heavy batch không throttling.

**Test “mật khẩu đúng đăng nhập được” mới chỉ kiểm tra một phần của authentication security.** Compatibility là điều kiện để user hợp lệ tiếp tục dùng dịch vụ; chống account takeover cần nhiều lớp khác.

## 16. Các tình huống lỗi và cách chẩn đoán

| Hiện tượng | Khả năng cao | Cách xử lý an toàn |
|---|---|---|
| `There is no PasswordEncoder mapped for id "null"` | Stored hash không có `{id}` | Inventory, xác nhận algorithm và thêm prefix hoặc strict adapter |
| `There is no PasswordEncoder mapped for id "X"` | Unknown ID | Không fallback noop; cấu hình mapping nếu được duyệt hoặc reset |
| Login cũ fail sau migration PBKDF2 | Tham số version/secret khác | Giữ profile ID và fixtures chính xác |
| Signup được nhưng login fail | Writer/reader khác config hoặc DB truncate | Test encode→persist→read→matches |
| Bcrypt hash length giảm | `VARCHAR` quá ngắn hoặc ORM cắt | Mở rộng cột, restore dữ liệu backup nếu đã hỏng |
| Chỉ password có tiếng Việt fail | Encoding/normalization khác nhau | Kiểm tra UTF-8/legacy fixtures, không tự trim |
| User đã đổi password nhưng login cũ lại được | Migration upgrade race ghi đè hash | CAS/version check và session invalidation |
| Test chỉ pass khi chạy một mình | Shared mutable state/repository, race | Isolate test fixtures, cleanup DB và test concurrency |
| `upgradeEncoding` không thay hash DB | Không cấu hình `UserDetailsPasswordService` | Bật service và kiểm tra persistence |
| Hash được upgrade nhưng login sau fail | Service ghi sai format/ID | Test login lần 2 và DB round-trip |
| Unknown ID được xác thực | Fallback quá rộng/`noop` | Strict allowlist, negative tests |
| Tăng bcrypt strength gây timeout | Work factor không được đo | Benchmark, điều chỉnh capacity/rate limiting |

### Sai phạm cần tránh

1. So sánh `encode(raw).equals(storedHash)`.
2. Gọi `encode()` để “kiểm tra” password mà không dùng `matches()`.
3. Gán prefix bằng phỏng đoán khi chưa xác nhận format.
4. Xử lý hash giống chuỗi không quan trọng: trim/lowercase/cắt độ dài.
5. Để database vô tình truncation khi thêm `{bcrypt}`.
6. Dùng `NoOpPasswordEncoder` làm fallback cho dữ liệu thiếu prefix.
7. Chấp nhận mọi `{id}` có trong factory dù policy không cho phép.
8. Thay PBKDF2 parameters nhưng tái sử dụng ID phiên bản cũ.
9. Để code writer mới phát hành hash mà reader ở một số instance chưa đọc được.
10. Nhầm `upgradeEncoding=true` với đã ghi lại DB.
11. Rehash `oldHash` thay vì raw password hợp lệ.
12. Ghi đè password mới vì login/migration concurrent.
13. Viết tests chỉ với raw ASCII, bỏ qua Unicode/boundary.
14. Kiểm tra DB bằng SQLite/in-memory thay PostgreSQL mà không có test DB thật.
15. Đọc production passwords hoặc đưa hashes thật lên dịch vụ web bên ngoài để thử.
16. Tin login unit test đã thay thế rate limiting/session/authorization checks.
17. Khóa account vô lý khi lỗi format migration làm mọi người dùng không login được.
18. Không có log an toàn/metric phát hiện rollback lỗi sau release.

## 17. Ma trận CI/CD và acceptance criteria

Bộ tiêu chí tối thiểu trước khi nâng cấp PasswordEncoder:

- [ ] Unit tests `encode/matches`: password đúng/sai, salt ngẫu nhiên.
- [ ] Mọi stored format hiện có đều có **fixture và test cụ thể**.
- [ ] Unknown/unapproved ID, plaintext và malformed hash đều **fail closed**.
- [ ] Dữ liệu prefixed và legacy được đọc bằng mapping đúng theo contract.
- [ ] `upgradeEncoding` kiểm thử old/current và không upgrade hash sai.
- [ ] DaoAuthenticationProvider xác thực được legacy đúng, từ chối raw sai.
- [ ] `UserDetailsPasswordService` nâng cấp sau login thành công, không nâng khi sai password.
- [ ] DB integration test kiểm tra **exact string round-trip** và cột đủ dài.
- [ ] Concurrency test xác minh migration không ghi đè password change/reset mới.
- [ ] Performance test kiểm soát login latency/CPU sau đổi work factor.
- [ ] Security test cho rate limit, anti-enumeration, MFA/passkey và session controls.
- [ ] Rollout reader→writer được thực hiện theo thứ tự, có rollback plan.
- [ ] Không log raw password/hashes hoặc test credentials production.
- [ ] Có thông báo và quy trình reset cho các bản ghi không thể nâng cấp.
- [ ] Tài liệu hóa thuật toán/ID/profile/version và mốc loại bỏ legacy format.

### Acceptance criteria thực dụng

Một phiên bản được coi sẵn sàng khi:
1. Đăng nhập bằng password đúng của **mọi lớp dữ liệu được hỗ trợ** vẫn thành công.
2. Đăng nhập sai và mọi format không được duyệt đều bị từ chối.
3. Hash mới dùng profile hiện hành; legacy được nâng cấp an toàn hoặc có lộ trình reset rõ.
4. Dữ liệu lưu qua DB giữ nguyên byte/Unicode/format, không truncate.
5. Không có race hồi sinh password cũ.
6. Không thay đổi nhầm mật khẩu và không làm lộ credential trong log, test reports hay metrics.
7. CI tái chạy được cùng fixtures và kết quả qua những lần nâng Java/Spring Security.

## 18. Ghi nhớ

- **`encode` dùng khi tạo/đổi password; `matches` dùng khi login.** Salt khiến hai bản encode khác nhau mà vẫn khớp.
- **`{id}hash` là hợp đồng dữ liệu của DelegatingPasswordEncoder.** Mapping đúng cho phép đọc nhiều thế hệ password hash.
- **Bản ghi bcrypt raw thiếu prefix không đồng nghĩa plaintext.** Chỉ xử lý bằng migration đã xác minh hoặc legacy verifier giới hạn nghiêm ngặt.
- **Không dùng `noop` hay mapping thuật toán yếu làm fallback.** Test dữ liệu không xác định phải fail closed.
- **`upgradeEncoding` là tín hiệu**; `UserDetailsPasswordService` và transaction/compare-and-set giúp persist hash mới sau password đúng.
- **Không thể đổi thuật toán từ oldHash mà không biết raw password.** Rehash khi login thành công hoặc yêu cầu password reset.
- **Compatibility phải kiểm thử cả encoder, provider và DB.** Nếu chỉ test in-memory, có thể bỏ sót truncation, serializer hoặc race ghi đè password.

## 19. Tài liệu tham khảo

1. [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): `DelegatingPasswordEncoder`, `{id}`, matching, upgrade và legacy compatibility.
2. [Spring Security 6.5 — PasswordEncoderFactories Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/factory/PasswordEncoderFactories.html): danh sách mappings và encoder mặc định.
3. [Spring Security 6.5 — DelegatingPasswordEncoder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html): `setDefaultPasswordEncoderForMatches`, `upgradeEncoding`.
4. [Spring Security 6.5 — PasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/PasswordEncoder.html): `encode`, `matches`, `upgradeEncoding`.
5. [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): provider và UserDetailsService/PasswordEncoder.
6. [Spring Security 6.5 — DaoAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html): `setUserDetailsPasswordService` và password upgrade.
7. [Spring Security 6.5 — UserDetailsPasswordService API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/core/userdetails/UserDetailsPasswordService.html): updatePassword đã encode.
8. [Spring Security 6.5 — BCryptPasswordEncoder](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html): BCrypt cost, matches và upgradeEncoding.
9. [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): adaptive hashes, work factor, migration và password handling.
10. [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): login throttling, generic errors, reset và reauthentication.
