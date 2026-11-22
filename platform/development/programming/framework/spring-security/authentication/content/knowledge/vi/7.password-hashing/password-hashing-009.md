# Vì sao không so sánh hai kết quả encode để kiểm tra cùng một mật khẩu

## Mục tiêu và câu trả lời ngắn

Trong Spring Security, **không nên kiểm tra hai mật khẩu có giống nhau bằng cách gọi `PasswordEncoder.encode(...)` cho từng giá trị rồi so sánh hai chuỗi đã mã hóa**. Với bộ mã hóa mật khẩu an toàn phổ biến như `BCryptPasswordEncoder`, mỗi lần `encode` thường sinh **salt ngẫu nhiên mới**. Vì vậy, **cùng một mật khẩu thô có thể tạo ra các chuỗi hash khác nhau**.

Cách kiểm tra mật khẩu khi đăng nhập là:

~~~java
boolean valid = passwordEncoder.matches(
    rawPasswordFromLogin,
    storedEncodedPassword
);
~~~

`matches(raw, encoded)` nhận **mật khẩu thô người dùng vừa nhập** và **toàn bộ chuỗi hash đã lưu**. Encoder đọc salt/tham số cần thiết từ giá trị đã lưu, thực hiện phép xác minh phù hợp và trả về `true` hoặc `false`. Nó **không giải mã** mật khẩu gốc, cũng không đơn giản gọi `encode(raw)` với một salt mới rồi `equals`.

Bài thuộc nhóm **Băm mật khẩu** trong module *Spring Security - authentication*, áp dụng cho Java 17+, Spring Boot 3.x và Spring Security 6.x. Nội dung hướng đến việc hiểu nguyên nhân, viết đúng mã khi đăng ký/đăng nhập, kiểm thử, xử lý định dạng hash và chẩn đoán các lỗi thường gặp.

Sau bài này, bạn cần trả lời được:

1. Vì sao hai lần `encode("same-password")` có thể trả về hai chuỗi không giống nhau?
2. Salt, work factor và định dạng chuỗi lưu trữ liên quan gì đến hành vi này?
3. Vì sao `matches(raw, stored)` có thể xác minh được khi hash do `encode` tạo ra là ngẫu nhiên?
4. Trong Spring Security, khi nào gọi `encode`, khi nào gọi `matches`, khi nào không phải tự gọi cả hai?
5. Nếu hash cũ dùng cost hoặc thuật toán khác, liệu chỉ so sánh chuỗi có kết luận được password sai hay không?
6. Viết test thế nào để không tạo flaky test hoặc bypass cơ chế xác thực?

## 1. Sai lầm phổ biến: so sánh hai lần encode

Giả sử một người dùng đăng ký bằng password `spring-2026!`. Ứng dụng băm password và lưu trong database. Khi đăng nhập, developer làm như sau:

~~~java
// SAI: encode() thường tạo một salt mới mỗi lần gọi.
String hashWhenRegistered = passwordEncoder.encode("spring-2026!");
String hashAtLogin = passwordEncoder.encode("spring-2026!");

boolean same = hashWhenRegistered.equals(hashAtLogin);
~~~

Với `BCryptPasswordEncoder` dùng ngẫu nhiên an toàn, `same` **hầu như luôn là `false`** dù cả hai đầu vào đều chính xác là `spring-2026!`.

Lý do không phải “bcrypt tính sai”, “password đã đổi”, hay “Spring Security không ổn định”. Đây là **đặc tính mong muốn** của một hàm băm mật khẩu có salt ngẫu nhiên.

Tách thành ba bước:

~~~text
Lúc đăng ký:
  raw = "spring-2026!"
  salt_A = random()
  storedHash = PasswordHash(raw, salt_A, cost)

Lúc đăng nhập — cách SAI:
  submittedRaw = "spring-2026!"
  salt_B = random()
  candidateHash = PasswordHash(submittedRaw, salt_B, cost)

Do salt_A thường khác salt_B,
storedHash và candidateHash thường khác nhau,
dù raw == submittedRaw.
~~~

**Cách ĐÚNG** là giữ `storedHash` và gọi:

~~~java
boolean same = passwordEncoder.matches(
    "spring-2026!",
    hashWhenRegistered
);
~~~

`matches` sử dụng thông tin của **hash đã lưu**, không chọn salt ngẫu nhiên mới để thực hiện phép so sánh. Trong trường hợp password đúng và định dạng hash/encoder tương thích, kết quả là `true`.

### 1.1. Chứng minh bằng bảng

| Mật khẩu thô | Thao tác | Salt dùng | Kết quả so sánh hash |
| --- | --- | --- | --- |
| `P` | `encode(P)` lần 1 | `S1` ngẫu nhiên | Hash `H1` |
| `P` | `encode(P)` lần 2 | `S2` ngẫu nhiên | Hash `H2`, thường khác `H1` |
| `P` + `H1` | `matches(P,H1)` | Đọc lại `S1` trong hash đã lưu | `true` |
| `Q` (sai) + `H1` | `matches(Q,H1)` | Đọc lại `S1` trong hash đã lưu | `false` |

**Không có mâu thuẫn:** tính ngẫu nhiên xuất hiện lúc **tạo hash mới**; lúc **kiểm tra hash hiện có**, các thông số của lần tạo trước đã được lưu lại để thuật toán xác minh.

## 2. Tại sao password hashing dùng salt?

**Salt** là dữ liệu ngẫu nhiên được đưa vào quá trình password hashing. Với bcrypt, salt chuẩn có 16 byte và thông tin đó được mã hóa thành một phần của chuỗi hash. Khi gọi `BCryptPasswordEncoder.encode(...)`, encoder thông thường tự sinh salt mật mã mới; bạn không cần tự tạo một cột hay tự ghép salt vào raw password để tích hợp Spring Security.

Giả sử hai người dùng chọn cùng password:

~~~text
Alice: password = "same-password", salt = A
Bob:   password = "same-password", salt = B

Alice storedHash = Hash("same-password", A, cost)
Bob   storedHash = Hash("same-password", B, cost)

A != B  =>  hai storedHash thường khác nhau
~~~

### 2.1. Salt mang lại những lợi ích gì?

- **Giảm khả năng nhận biết password trùng nhau:** chỉ nhìn hai chuỗi hash khác nhau không thể kết luận hai người dùng có password khác nhau.
- **Chống bảng hash tính sẵn (rainbow tables):** bảng tra cứu chung cho một thuật toán không có salt không còn hữu ích như trước; attacker phải tính toán theo từng salt.
- **Làm giảm hiệu quả chia sẻ kết quả tấn công giữa nhiều account:** việc crack một hash thường không thể dùng trực tiếp một chuỗi tính sẵn cho mọi hash khác salt.
- **Cho phép thay password và tạo hash mới độc lập:** một lần reset/đổi mật khẩu sẽ được băm lại với salt mới.

Salt **không cần bí mật**. Salt được lưu cạnh hash là bình thường. Pepper là một bí mật tùy chọn quản lý ở server/HSM và không nên nhầm với salt.

### 2.2. Salt không giải quyết mọi vấn đề

- Salt không khiến password yếu như `123456` trở thành mạnh. Attacker đã lấy DB có hash và salt vẫn có thể đoán mật khẩu **offline**, nhưng phải thực hiện công việc phù hợp cho từng hash.
- Salt không thay thế **work factor**. Hash nhanh một lần kiểu `SHA-256(password + salt)` vẫn không phù hợp để lưu password production.
- Salt không chống **online guessing** tại HTTP login endpoint: cần rate limiting, MFA/passkeys, monitoring, chính sách mật khẩu và thông điệp lỗi có kiểm soát.
- Salt không nên là username/email cố định hoặc một hằng số trong source code. Hãy dùng implementation password hashing có tạo salt bằng nguồn ngẫu nhiên mật mã.

Đừng tắt salt để “làm cho hash ổn định và dễ so sánh”. Làm vậy mất một lớp bảo vệ quan trọng chỉ để tránh sử dụng đúng API.

## 3. Mối quan hệ giữa salt, cost và giá trị encoded

Một hash password kiểu bcrypt không chỉ là một digest đơn giản. Nó thường lưu đủ thông tin cần thiết để xác minh:

~~~text
$2a$12$xxxxxxxxxxxxxxxxxxxxxxYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY
 │  │  │                     │
 │  │  │                     └─ phần kết quả hashing
 │  │  └─ phần biểu diễn salt
 │  └─ cost / log rounds
 └─ bcrypt version
~~~

**Đây là sơ đồ cấu trúc**, không phải hash hợp lệ để copy vào ứng dụng. Chuỗi bcrypt chuẩn dài 60 ký tự ASCII. Các biến thể `$2a$`, `$2b$`, `$2y$` có thể gặp tùy phiên bản và cấu hình. Với bcrypt, salt 16 byte thường được biểu diễn trong 22 ký tự, còn phần kết quả hashing trong 31 ký tự.

### 3.1. Tại sao lưu đầy đủ encoded password?

Khi user đăng nhập, encoder cần biết:

1. Thuật toán hoặc biến thể được dùng.
2. Salt gắn với bản ghi **đã lưu**.
3. Work factor/cost của lần tạo hash trước đó.
4. Giá trị hash kỳ vọng để xác minh.

Nếu bạn chỉ lưu một phần của hash, tự bỏ tiền tố hoặc chỉnh sửa salt/cost, `matches` có thể trả `false` hoặc coi định dạng không hợp lệ. Nếu bạn chỉ lưu plaintext hay một SHA-256 hash tự chế, logic password storage không còn tương thích với `BCryptPasswordEncoder`.

Ví dụ hash bcrypt mới có cost 12 sẽ bắt đầu tương tự `$2a$12$...`; hash cũ có cost 10 sẽ bắt đầu tương tự `$2a$10$...`. Hai giá trị **không thể so sánh chuỗi trực tiếp để biết password có trùng**, kể cả khi không đổi salt. Encoder phải thực hiện phép kiểm tra theo thông số của hash được lưu.

### 3.2. Work factor ảnh hưởng encode và matches thế nào?

`BCryptPasswordEncoder(12)` chọn cost cho **những hash mới** được `encode` tạo. Cost cao hơn làm mỗi phép hash/verify tốn công hơn; trong bcrypt công việc tăng theo log rounds, gần gấp đôi khi cost tăng một mức, nhưng thời gian thực tế phụ thuộc máy.

`matches(raw, storedHash)` xử lý hash đã lưu bằng **cost nằm trong storedHash**. Do đó, một encoder được cấu hình tạo hash cost 12 vẫn có thể xác minh hash cost 10 trước đó.

Work factor **không phải nguyên nhân chính** khiến hai lần `encode` cùng password khác nhau trong cùng một cấu hình; nguyên nhân trực tiếp là salt ngẫu nhiên. Work factor khiến phép đoán password khó khăn/tốn tài nguyên hơn.

## 4. PasswordEncoder API: encode và matches có hợp đồng khác nhau

Spring Security định nghĩa interface chính:

~~~java
public interface PasswordEncoder {

    String encode(CharSequence rawPassword);

    boolean matches(
        CharSequence rawPassword,
        String encodedPassword
    );

    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

Đây là **chữ ký API rút gọn để học**, không phải source file cần tạo. `PasswordEncoder` cho phép nhiều implementation như bcrypt, Argon2, scrypt, PBKDF2 hoặc delegating encoder.

| Phương thức | Đầu vào | Trả về | Dùng khi nào? |
| --- | --- | --- | --- |
| `encode(raw)` | Password thô | Chuỗi encoded mới; thuật toán an toàn thường tạo salt mới | Khi tạo account, đổi/reset password, rehash |
| `matches(raw, encoded)` | Password thô vừa nhập + hash đã lưu | Boolean kết quả xác minh | Khi kiểm tra password đăng nhập |
| `upgradeEncoding(encoded)` | Hash đã lưu | Boolean gợi ý nên nâng encoding | Sau xác thực thành công, trong cơ chế migration phù hợp |

**Thứ tự tham số của `matches` rất quan trọng:** `matches(rawPassword, encodedPasswordFromStorage)`. Tham số thứ nhất **không phải hash**, tham số thứ hai **không phải raw password**.

### 4.1. matches không giải mã hash

Vì password hash là hàm một chiều, `matches` không cố tìm lại password cũ từ hash. Nó dùng raw password mới được cung cấp, cùng salt/cost/format đã lưu, để thực hiện phép xác minh. Với bcrypt, có thể hiểu khái niệm là:

~~~text
matches(submittedRaw, storedHash):
    đọc version, cost và salt từ storedHash
    thử thuật toán bcrypt với submittedRaw theo các tham số đó
    đối chiếu kết quả với storedHash
    trả true/false
~~~

Đây là **mô tả logic**, không phải source code hiện thực của Spring Security, và không nên tự cài đặt phép so sánh/mật mã bên trong. Hãy để implementation đã được kiểm chứng thực hiện verification, kể cả xử lý định dạng và so sánh an toàn.

### 4.2. Ba so sánh rất dễ nhầm

~~~java
String stored = encoder.encode(raw);

// SAI: encode lại sinh salt mới.
boolean a = stored.equals(encoder.encode(raw));

// SAI: hai hash tạo độc lập không phải phép kiểm tra password.
boolean b = encoder.encode(raw).equals(encoder.encode(raw));

// ĐÚNG: raw password + hash đã lưu.
boolean c = encoder.matches(raw, stored);
~~~

Với encoder ngẫu nhiên như bcrypt, `a` và `b` hầu như luôn `false`; `c` là `true` nếu đầu vào thật sự khớp và format hợp lệ. Không sử dụng `a` hay `b` làm logic xác thực. Một implementation khác có thể có tính deterministic, nhưng **hợp đồng `PasswordEncoder` không bảo đảm hai lần `encode` giống nhau**, vì vậy code dựa trên `equals` là sai về mặt thiết kế và không portable giữa các encoder.

### 4.3. Đối số ngược cũng là một lỗi

~~~java
// SAI: gửi hash đã lưu vào vị trí raw, và raw vào vị trí encoded.
boolean wrongOrder = encoder.matches(storedHash, inputPassword);
~~~

Có thể dẫn tới `false` hoặc cảnh báo hash format không hợp lệ, tùy implementation. Đúng:

~~~java
boolean correctOrder = encoder.matches(inputPassword, storedHash);
~~~

`storedHash` là chuỗi được lấy trực tiếp từ database/nguồn lưu trữ đáng tin; không phải chuỗi do client gửi. Không cho client tự chọn hash cần xác minh hoặc cost/algorithm ID.

## 5. Ví dụ Java 17+ chạy được: quan sát hai encode khác nhau và matches đúng

Ví dụ sử dụng **Spring Boot 3.x + Spring Security 6.x**, Java 17+, chạy dưới dạng CLI (không có server HTTP) để tập trung vào password hashing. Nó không tạo tài khoản trong database, không in password/hash ra console và không tự xác thực một người dùng trong hệ thống HTTP.

### 5.1. Tạo project Maven

Trên Spring Initializr chọn:

- Build: **Maven**.
- Java: **17 hoặc 21**.
- Spring Boot: **3.x**.
- Group `com.example`, artifact `password-compare`.
- Dependency: **Spring Security** (`spring-boot-starter-security`). Không cần `Spring Web`.

Tạo file:

~~~text
src/main/java/com/example/demo/PasswordCompareApplication.java
~~~

Và bảo đảm package là `com.example.demo`.

### 5.2. Code đầy đủ

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@SpringBootApplication
public class PasswordCompareApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordCompareApplication.class, args);
    }

    @Bean
    CommandLineRunner comparePasswords() {
        return args -> {
            String raw = "demo-only-Strong!2026";
            PasswordEncoder encoder = new BCryptPasswordEncoder(10);

            String storedHash = encoder.encode(raw);
            String anotherHash = encoder.encode(raw);

            // Hai encode tạo salt ngẫu nhiên độc lập.
            boolean equalEncodedStrings =
                storedHash.equals(anotherHash);

            // Xác minh mỗi hash bằng raw password ban đầu.
            boolean storedMatches =
                encoder.matches(raw, storedHash);
            boolean anotherMatches =
                encoder.matches(raw, anotherHash);

            // Sai password không khớp storedHash.
            boolean wrongPasswordMatches =
                encoder.matches("definitely-wrong", storedHash);

            // Sai phương pháp: hash một lần nữa rồi so chuỗi.
            boolean wrongComparison =
                encoder.encode(raw).equals(storedHash);

            System.out.println("sameRawDifferentHashes="
                + !equalEncodedStrings);
            System.out.println("storedMatches=" + storedMatches);
            System.out.println("anotherMatches=" + anotherMatches);
            System.out.println("wrongPasswordMatches="
                + wrongPasswordMatches);
            System.out.println("wrongComparison="
                + wrongComparison);
        };
    }
}
~~~

### 5.3. Chạy chương trình

Tại thư mục chứa `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell dùng `.\mvnw.cmd spring-boot:run`. Những dòng **do chương trình in ra** điển hình là:

~~~text
sameRawDifferentHashes=true
storedMatches=true
anotherMatches=true
wrongPasswordMatches=false
wrongComparison=false
~~~

**Lưu ý chính xác:** dòng `sameRawDifferentHashes=true` và `wrongComparison=false` phản ánh hành vi xác suất áp đảo của salt ngẫu nhiên, **không phải định lý rằng hai hash không bao giờ có thể trùng**. Nếu cùng salt 128-bit được sinh lại (xác suất cực kỳ nhỏ) và cùng mọi thông số, hai kết quả có thể trùng. Trong thực hành điều này gần như không xảy ra khi dùng nguồn ngẫu nhiên mật mã. Các dòng `storedMatches=true`, `anotherMatches=true` và `wrongPasswordMatches=false` phản ánh kỳ vọng xác minh trên các giá trị đã tạo hợp lệ.

Mục đích bài không phải ép ngẫu nhiên tạo chuỗi khác nhau bằng cách thêm timestamp hoặc UUID thủ công; điều quan trọng là **`matches` phải hoạt động bất kể salt do encoder đã chọn**.

### 5.4. Thí nghiệm nên làm

1. Chạy ứng dụng vài lần, xem `matches` vẫn đúng. Nếu thêm dòng in hash để học, hai hash sẽ khác nhau và có prefix cost; **chỉ làm trên máy thử, không log hash production**.
2. Đổi `new BCryptPasswordEncoder(10)` thành `new BCryptPasswordEncoder(12)`, quan sát kết quả logic không đổi; thời gian chạy có thể tăng.
3. Đổi `raw` thành một chuỗi có ký tự Unicode, khoảng trắng, dấu tiếng Việt; kiểm tra `matches` với đúng raw, không tự trim/lowercase.
4. Thử truyền một password sai vào `matches`, xác nhận `false`.
5. Đọc từng dòng code và xác định dòng nào tạo salt mới, dòng nào chỉ xác minh hash đã có.

## 6. Ví dụ nghiệp vụ đúng: đăng ký và đăng nhập với database

### 6.1. Lúc đăng ký, encode một lần và lưu toàn bộ hash

Luồng đúng:

~~~text
POST /register (username, rawPassword)
        |
        +--> kiểm tra dữ liệu, policy và quyền tạo account
        +--> passwordEncoder.encode(rawPassword)
        +--> lưu toàn bộ encodedPassword vào DB
        +--> không lưu rawPassword
~~~

Một ví dụ **mã minh họa, không phải chương trình độc lập**:

~~~java
public void register(String username, String rawPassword) {
    if (accountRepository.existsByUsername(username)) {
        throw new IllegalArgumentException("Account unavailable");
    }

    String hash = passwordEncoder.encode(rawPassword);

    accountRepository.save(new Account(username, hash));
}
~~~

Ví dụ giả định `accountRepository`, `Account` và field `passwordEncoder` là các thành phần domain đã được định nghĩa. Ứng dụng thật cần transaction, unique constraint/race handling, kiểm soát đăng ký, policy mật khẩu và bảo vệ dữ liệu nhập. Không đưa hash vào API response hay log. Password hash có thể được lưu trong cột `password_hash` hoặc `password_encoded` với chiều dài đủ cho **toàn bộ format**.

### 6.2. Lúc đăng nhập, lấy hash cũ và gọi matches

~~~text
POST /login (username, submittedRawPassword)
        |
        +--> tìm account theo username
        +--> lấy storedHash từ DB
        +--> passwordEncoder.matches(submittedRawPassword, storedHash)
        |         |
        |         +--> false: từ chối credentials
        |         +--> true: chuyển sang status/MFA/policy tiếp theo
        |
        +--> trả authentication hợp lệ theo framework
~~~

Ví dụ **mã minh họa tầng domain**:

~~~java
Account account = accountRepository.findByUsername(username)
    .orElseThrow(() -> new AuthenticationFailureException());

boolean passwordValid = passwordEncoder.matches(
    rawPasswordFromRequest,
    account.passwordHash()
);

if (!passwordValid) {
    throw new AuthenticationFailureException();
}
~~~

`Account` và `AuthenticationFailureException` trong đoạn này là **domain types giả định**, không phải thư viện Spring Security có tên như vậy. Đoạn chỉ minh họa cách kiểm tra password; nếu xây authentication thực tế, hãy dùng `AuthenticationManager`/`AuthenticationProvider` và xử lý account flags, session, MFA và các mối lo khác. Đừng sao chép trực tiếp đoạn domain này vào controller để thay toàn bộ cơ chế authentication.

### 6.3. Với Spring Security chuẩn, provider làm phép kiểm tra

Cấu hình phổ biến:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder(12);
}
~~~

Đây là **đoạn cấu hình Spring có import phù hợp**, không phải một file đầy đủ. Với `DaoAuthenticationProvider`, quy trình thường là:

~~~text
UsernamePasswordAuthenticationToken (chưa xác thực)
        |
        v
AuthenticationManager
        |
        v
DaoAuthenticationProvider
        |
        +--> UserDetailsService.loadUserByUsername(username)
        |       -> UserDetails.getPassword(): storedHash
        |
        +--> PasswordEncoder.matches(rawCredentials, storedHash)
        |
        +--> account status và các checks bổ sung
        |
        v
Authentication thành công hoặc AuthenticationException
~~~

Vì vậy, khi dùng Spring Security form login/HTTP Basic đúng cách, **bạn thường không phải tự viết `matches` trong controller**. Chỉ cần bảo đảm `UserDetailsService` cung cấp hash đúng định dạng, `PasswordEncoder` khớp cấu hình và provider thực sự dùng chúng. Đừng gọi `encode` trước khi truyền raw password vào `AuthenticationManager`: provider kỳ vọng credentials gốc để tự verify với hash lưu trữ.

## 7. Nếu muốn so sánh hai mật khẩu thô thì sao?

Có hai tình huống khác nhau:

**Tình huống A — đăng nhập / đổi password:** bạn có một raw password mới và một **stored hash** cũ. Dùng `matches(raw, storedHash)` để kiểm tra. Đây là flow bảo mật của Spring Security.

**Tình huống B — người dùng điền “Mật khẩu mới” và “Nhập lại mật khẩu mới” ngay trong một form:** đây là hai **giá trị thô trong cùng một request**. Bạn có thể so sánh chúng trong validation **trước khi encode**, rồi chỉ encode và lưu **một lần** nếu hợp lệ.

~~~java
// Trong validation form đăng ký/đổi mật khẩu.
// Hai chuỗi đều là raw password từ cùng request.
if (!newPassword.equals(confirmNewPassword)) {
    throw new IllegalArgumentException(
        "Password confirmation does not match"
    );
}

String newHash = passwordEncoder.encode(newPassword);
// Lưu newHash; không lưu hai raw input.
~~~

Đoạn này **chỉ là fragment**, cần các biến và service khác của ứng dụng. Mục tiêu là tránh làm:

~~~java
// SAI: không hash hai field rồi so.
boolean confirmed = passwordEncoder.encode(newPassword)
    .equals(passwordEncoder.encode(confirmNewPassword));
~~~

Với bcrypt, hai field bằng nhau vẫn có thể tạo hash khác nhau. Trong form validation, dùng `String.equals` cho hai raw values trong cùng request là bài toán khác với so raw password với hash đã lưu. Tuy nhiên, đừng log hoặc giữ raw fields lâu, và xử lý các yêu cầu Unicode/password policy nhất quán.

## 8. Đừng nhầm deterministic hashing với password storage an toàn

Các hàm băm phổ dụng như SHA-256 nếu dùng không có salt có tính deterministic:

~~~text
SHA-256(P)  -> digest X
SHA-256(P)  -> digest X  (cùng input)
~~~

Khi nhìn thấy đặc tính này, một developer có thể nghĩ rằng **hai kết quả băm phải bằng nhau mới là password giống nhau**. Lập luận ấy không áp dụng cho **password encoding thích nghi với salt ngẫu nhiên**.

### 8.1. Tại sao không bỏ salt để lấy hash cố định?

Vì sẽ làm attacker tận dụng một lần tính toán cho nhiều account và dễ nhận biết những user có password trùng nhau. SHA-256 một vòng cũng quá nhanh để làm password storage. Việc dễ dàng gọi `equals` không phải lý do chấp nhận một cơ chế yếu.

### 8.2. Tại sao không tự “lấy salt ra rồi gọi encode” để bằng nhau?

Thư viện đã có `matches` đúng contract; việc tự parse hash và tự tạo lại salt/cost rất dễ gây lỗi encoding, compatibility, timing hoặc versioning. `encode` thường được thiết kế để tạo hash **mới** với random salt, không phải API công khai để sinh lại hash cũ theo tham số do caller cung cấp.

### 8.3. Nếu hai hash khác nhau, có chứng minh password khác nhau không?

Không. Salt/cost/algorithm khác nhau có thể làm các hash khác nhau dù raw password giống nhau.

Nếu hai hash tình cờ giống hệt nhau, có chứng minh hai account có cùng password không? Với cùng loại hash/format và salt, có thể đó là dấu hiệu, nhưng không nên xây security/business logic dựa trên suy đoán từ việc so chuỗi hash giữa các tài khoản. Hãy thiết kế xác minh theo identity và stored hash của từng account, không suy diễn hay chia sẻ credential giữa accounts.

## 9. Khác biệt giữa BCryptPasswordEncoder và DelegatingPasswordEncoder

### 9.1. Bcrypt thuần

Một encoded bcrypt có dạng:

~~~text
$2a$12$... (chuỗi bcrypt chuẩn)
~~~

Sử dụng:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder(12);
String stored = encoder.encode("example");
boolean ok = encoder.matches("example", stored);
~~~

Dù format có salt/cost, nó **không** có tiền tố `{bcrypt}` của Spring delegating encoder.

### 9.2. DelegatingPasswordEncoder có tiền tố {id}

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` thường chọn bcrypt để tạo hash mới, nhưng thêm prefix thuật toán:

~~~text
{bcrypt}$2a$10$... (ví dụ hình thức)
~~~

Khi `matches` được gọi trên delegating encoder, nó đọc `{id}` và chọn encoder tương ứng. Ví dụ:

~~~java
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

PasswordEncoder delegate =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String stored = delegate.encode("demo-only");
boolean ok = delegate.matches("demo-only", stored);
~~~

Đây là **fragment trong một method Java**, không phải toàn bộ class. Kết quả `ok` được kỳ vọng `true`. Không cắt `{bcrypt}` khi lưu nếu encoder dùng delegating format.

### 9.3. Một lỗi dễ gây hiểu nhầm

Nếu DB lưu chuỗi bcrypt thuần `$2a$...` nhưng chương trình đột ngột chuyển sang `DelegatingPasswordEncoder` mặc định, `matches` có thể báo không có encoder mapping cho ID `null`, **không phải password sai theo nghĩa nghiệp vụ**.

Ngược lại, nếu DB lưu `{bcrypt}$2a$...`, gọi trực tiếp `BCryptPasswordEncoder.matches(raw, storedWithId)` cũng không đúng định dạng đầu vào của bcrypt thuần. Khi migration, hãy phân loại format và cấu hình encoder tương thích thay vì tự đổi nội dung hash. Không dùng fallback chấp nhận plaintext để “đỡ lỗi” production.

Cùng một mật khẩu có thể có nhiều stored hash khác nhau do:

- Salt khác nhau.
- Work factor khác nhau.
- Algorithm/`{id}` khác nhau.
- Phiên bản encoder/format khác nhau.

Đó là thêm một lý do **không dùng `storedHashA.equals(storedHashB)` làm bằng chứng hai password giống hay khác**.

## 10. Đổi work factor hoặc thuật toán có làm password cũ không đăng nhập được?

Không nhất thiết, nếu encoder được cấu hình hỗ trợ format cũ. Với bcrypt, cost thường được ghi trong hash; một encoder tạo hash cost 12 vẫn đọc và kiểm tra được hash cost 10.

~~~java
BCryptPasswordEncoder oldEncoder = new BCryptPasswordEncoder(10);
BCryptPasswordEncoder newEncoder = new BCryptPasswordEncoder(12);

String hashAtCost10 = oldEncoder.encode("same-raw");

// Dùng hash cũ mà không encode lại trước khi matches.
boolean stillValid =
    newEncoder.matches("same-raw", hashAtCost10);

// Có nên nâng cách encode khi có raw password hợp lệ?
boolean needsUpgrade = newEncoder.upgradeEncoding(hashAtCost10);
~~~

Mã trên là **fragment**, không phải chương trình độc lập. Với bcrypt 6.x phù hợp, `stillValid` là `true` và `needsUpgrade` là `true`. Điều đó **không có nghĩa** đổi bean encoder tự động nâng mọi hash trong database. Hash cũ chỉ có thể được rehash đúng cách khi ứng dụng có raw password hợp lệ trong một luồng xác thực/reset.

### 10.1. Rehash khi đăng nhập thành công

Luồng nâng cấp thường hợp lý:

1. Nhận raw password qua kênh bảo mật.
2. Xác minh bằng `matches(raw, storedHash)` trước.
3. Nếu đúng, kiểm tra `upgradeEncoding(storedHash)`.
4. Nếu cần, dùng **chính raw password đã được xác minh** để tạo hash mới bằng `encode(raw)` (salt/cost mới).
5. Lưu hash mới qua tầng quản lý mật khẩu có transaction và chống race với thao tác đổi mật khẩu khác.
6. Xóa/không giữ raw password lâu hơn cần thiết; audit sự kiện ở mức metadata, không log secret.

Nếu dùng `DaoAuthenticationProvider`, `UserDetailsPasswordService` là điểm tích hợp cho việc cập nhật hash sau xác thực khi provider hỗ trợ:

~~~java
// Trong cấu hình đã có các biến:
// users: UserDetailsService
// encoder: PasswordEncoder
// passwordUpdates: UserDetailsPasswordService
DaoAuthenticationProvider provider =
    new DaoAuthenticationProvider(users);

provider.setPasswordEncoder(encoder);
provider.setUserDetailsPasswordService(passwordUpdates);
~~~

Đoạn này là **mã minh họa cấu hình**, không phải file độc lập. `UserDetailsPasswordService.updatePassword(UserDetails user, String newPassword)` nhận giá trị **đã được encode** để lưu và trả UserDetails cập nhật. Provider có thể gọi khi cần nâng encoding. Ứng dụng phải triển khai persistence đúng; không tự giả định Spring Security sẽ ghi DB chỉ vì bean `PasswordEncoder` thay cost.

### 10.2. Lưu gì trong database?

Nên lưu **một chuỗi encoded đầy đủ** với độ dài đủ chứa định dạng hiện tại và khả năng nâng cấp. Không chia hash thành nhiều phần rồi chỉ lấy digest để so, cũng không ghi đè hash cũ bằng `encode(storedHash)` — việc đó đang băm **chuỗi hash cũ như một mật khẩu mới**, khiến raw password cũ không còn kiểm tra được.

Đặc biệt sai:

~~~java
// SAI: băm lại hash chứ không phải raw password.
String broken = passwordEncoder.encode(existingStoredHash);
accountRepository.updatePasswordHash(userId, broken);
~~~

Nếu không có raw password trong một flow hợp lệ, hãy để hash cũ được verify bởi encoder tương thích hoặc yêu cầu người dùng reset mật khẩu theo chính sách.

## 11. Những lỗi thường gặp và chẩn đoán

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Cùng raw password nhưng hai `encode` khác | Salt ngẫu nhiên được sinh mỗi lần | **Bình thường**; dùng `matches` |
| Đăng ký đúng, login luôn báo sai | Login `encode(raw).equals(stored)` | Đổi sang `matches(raw, stored)` |
| `matches` luôn false với hash trong DB | Stored hash bị cắt, sai format/encoder, raw thay đổi, password thực sự sai | Kiểm tra chiều dài cột và format; giữ full encoded value |
| `matches` bị gọi ngược tham số | Truyền hash vào raw và raw vào encoded | Dùng `matches(submittedRaw, storedHash)` |
| Dùng `new BCryptPasswordEncoder(12)` nhưng DB có `{bcrypt}...` | Encoder thuần không đọc delegating prefix | Chọn đúng encoder hoặc migration được kiểm soát |
| Dùng delegating encoder gặp ID `null` | DB chứa hash thuần không có `{id}` | Phân loại/migrate format, không mặc định fallback plaintext |
| Tăng cost làm login chậm | Mỗi lần verify tốn công hơn | Benchmark và capacity planning, rate limiting |
| Cùng hash cũ vẫn xác thực sau tăng cost | Cost được lưu trong hash, encoder hỗ trợ verify format cũ | Có thể đúng; kiểm tra `upgradeEncoding` |
| Hai field confirm password giống nhau nhưng kiểm tra thất bại | Hash hai field riêng rồi `equals` | So hai **raw fields** trong cùng request trước khi encode |
| Hai accounts có hash khác, bị kết luận password khác | Salt khác nhau, có thể raw giống nhau | Không suy luận password từ so sánh hash |
| Log ra hash để debug | Tăng nguy cơ lộ dữ liệu xác thực | Không log raw/encoded password, token, pepper |
| Login không gọi `matches` của bean mong đợi | Provider/manager khác đang được dùng | Truy dấu filter chain, `AuthenticationProvider` và bean encoder |

### 11.1. Kiểm tra ba lớp độc lập

Khi có lỗi, kiểm tra có thứ tự:

**Lớp dữ liệu:** record người dùng tồn tại không, cột `password_hash` có chứa toàn bộ encoded value, có bị trim/truncate/encode lại khi đọc/ghi không, có prefix `{id}` đúng không?

**Lớp thuật toán:** bean `PasswordEncoder` trong provider có tương thích stored format không? `matches(raw, stored)` có đúng thứ tự không? Password thô có bị xử lý khác lúc đăng ký và đăng nhập (trim, lowercase, Unicode normalization) không?

**Lớp xác thực:** `DaoAuthenticationProvider` có được chọn cho token hiện hành không? `UserDetailsService` trả đúng user và hash không? Account có disabled/locked/expired không? Authentication thành công nhưng authorization từ chối là chuyện riêng.

Không chỉnh hash trong production bằng tay hoặc log password để thử. Hãy tái hiện trên dữ liệu test với password thử, snapshot dependency/version và có test regression.

## 12. Kiểm thử đúng để tránh test giả

### 12.1. Test không nên phụ thuộc hai encode phải khác tuyệt đối

Một JUnit test kém:

~~~java
// SAI VỀ MỤC ĐÍCH KIỂM THỬ:
assertNotEquals(
    encoder.encode(raw),
    encoder.encode(raw)
);
~~~

Salt ngẫu nhiên khiến điều này hầu như đúng, nhưng không có **bảo đảm tuyệt đối** hai salt không bao giờ trùng. Điều quan trọng là tính chính xác của `matches`, không phải chứng minh tính độc nhất toán học của mọi lần random.

Test tốt hơn:

~~~java
String stored = encoder.encode(raw);

assertTrue(encoder.matches(raw, stored));
assertFalse(encoder.matches("wrong", stored));
~~~

Đây là **fragment JUnit 5** trong test đã khai báo `encoder`/`raw` và import `Assertions.assertTrue/assertFalse`. Nó kiểm tra đúng hợp đồng xác thực.

### 12.2. Test đầy đủ với JUnit 5

Trong một project đã có dependency `spring-boot-starter-test`, test sau chạy được nếu file được tạo đúng package và tên:

**`src/test/java/com/example/demo/PasswordEncoderContractTest.java`**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PasswordEncoderContractTest {

    private final PasswordEncoder encoder =
        new BCryptPasswordEncoder(10);

    @Test
    void correctPasswordMatchesStoredHash() {
        String storedHash = encoder.encode("demo-only-Strong!2026");

        assertTrue(
            encoder.matches("demo-only-Strong!2026", storedHash)
        );
        assertFalse(
            encoder.matches("definitely-wrong", storedHash)
        );
    }

    @Test
    void twoIndependentHashesCanValidateSameRawPassword() {
        String raw = "demo-only-Strong!2026";

        String first = encoder.encode(raw);
        String second = encoder.encode(raw);

        assertTrue(encoder.matches(raw, first));
        assertTrue(encoder.matches(raw, second));
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

Windows PowerShell: `.\mvnw.cmd test`. Test cố ý **không assert `first != second`**; mục tiêu cần duy trì khi đổi thuật toán là cả hai stored values đều xác minh đúng raw password.

### 12.3. Test integration login

Một test unit của encoder vẫn chưa chứng minh cả login flow đúng. Với Spring Security, nên kiểm thử thêm:

- Đăng ký account và xác nhận database lưu encoded value, không lưu plaintext.
- Login với password đúng → authentication thành công.
- Login với password sai → thất bại.
- Account disabled/locked → không được xác thực dù `matches` đúng.
- Username không tồn tại → phản hồi đăng nhập an toàn, không lộ account enumeration.
- Hash lưu dạng delegating/legacy → provider dùng đúng encoder.
- Đổi password → hash mới có salt mới và raw password cũ bị từ chối.
- Nâng cost → hash cũ vẫn verify, hash mới đạt thông số mục tiêu.
- Concurrent login/change-password → không ghi đè credential mới bằng hash rehash cũ.

Không bao giờ “kiểm thử đăng nhập” bằng việc tự tạo token đã xác thực từ username rồi đặt vào `SecurityContextHolder`: cách đó bỏ qua đúng bước cần kiểm tra.

## 13. Góc nhìn bảo mật: tại sao không tối ưu bằng hash cố định?

Mục tiêu của password hashing không phải tạo một định danh ổn định cho password để tiện so sánh. Mục tiêu là **giảm thiệt hại nếu kho hash bị đánh cắp**. Salt riêng và work factor thích hợp tăng chi phí của kẻ tấn công đoán password **offline**.

Nếu vì muốn hai lần `encode` giống nhau mà chuyển sang MD5/SHA-1/SHA-256 một vòng không salt, bạn đang đánh đổi bảo mật để lấy một so sánh chuỗi thuận tiện. Với cơ chế băm mật khẩu phù hợp, cách đơn giản và an toàn hơn là **dùng API `matches`**.

### 13.1. Work factor không thay thế chống dò online

Ngay cả bcrypt/Argon2id với cost cao, attacker vẫn có thể thử đăng nhập qua HTTP. Cần bảo vệ nhiều lớp:

1. Rate limiting theo nhiều tín hiệu (account, IP đáng tin qua reverse proxy, thiết bị/rủi ro).
2. Chống password spraying (một mật khẩu thử trên nhiều account).
3. MFA/passkeys khi phù hợp; ưu tiên phương pháp chống phishing.
4. Không tiết lộ username có tồn tại qua thông điệp lỗi/timing.
5. TLS cho kênh nhập password; không log raw password, hash, authorization headers hay cookies.
6. Giám sát latency và concurrency để cost cao không tạo CPU-denial-of-service.
7. Chính sách password tránh mật khẩu quá yếu, mật khẩu đã lộ và reuse.

### 13.2. Raw password, Unicode và khoảng trắng

`matches` dùng chính chuỗi password được cung cấp. Nếu lúc đăng ký bạn chạy `trim()` nhưng lúc login giữ nguyên, hoặc tự `toLowerCase()` ở một đầu, thì password có thể không khớp dù người dùng nghĩ họ nhập đúng. Hãy định nghĩa policy normalization **nếu thật sự cần**, dùng nhất quán và không lén thay đổi password do user chọn.

Với bcrypt, nhiều implementation chỉ xử lý tối đa 72 byte đầu vào; đây là **byte**, không phải 72 ký tự Unicode. Passphrase có tiếng Việt/emoji có thể có nhiều byte hơn số ký tự. Ứng dụng cần chính sách độ dài nhất quán, không cắt ngầm, hoặc chọn thuật toán/thiết kế phù hợp với mật khẩu dài theo khuyến nghị bảo mật.

### 13.3. Pepper không làm thay đổi quy tắc matches

Nếu tổ chức sử dụng pepper (secret bổ sung ngoài DB), hãy để việc áp dụng nó nằm trong một component/encoder có thiết kế và quản trị secret rõ ràng. Không tự thêm pepper tùy hứng vào input ở lúc đăng ký mà quên thêm ở lúc login, hoặc để secret trong database/hash. Quy tắc của hệ thống vẫn là xác minh một **raw password** đối với **stored encoded credential** qua component có contract phù hợp, không so sánh hai lần encode ngẫu nhiên.

## 14. Câu hỏi và đáp án

**Câu 1.** Hai lần `encoder.encode("P")` trả hai chuỗi khác nhau. Đây có phải bug của Spring Security không?

**Đáp án:** không. Với bcrypt và các encoder dùng salt ngẫu nhiên, đây là đặc tính mong muốn. Hai salt khác nhau tạo hai stored hash khác nhau.

**Câu 2.** Nếu hai hash khác nhau thì có thể kết luận hai password thô khác nhau không?

**Đáp án:** không. Chúng có thể là cùng một raw password được mã hóa với salt hoặc cost khác nhau.

**Câu 3.** Vì sao `encoder.matches("P", storedHash)` có thể trả true dù `encoder.encode("P").equals(storedHash)` là false?

**Đáp án:** `matches` dùng các thông số/salt của hash được lưu để xác minh, trong khi `encode` thường tạo salt mới.

**Câu 4.** Một tài khoản có stored hash, login nhận raw password từ client. Truyền tham số vào `matches` theo thứ tự nào?

**Đáp án:** `matches(rawFromClient, storedHashFromDatabase)`.

**Câu 5.** User nhập “newPassword” và “confirmPassword” giống nhau trong form. Cần gọi encode hai lần để so hai field không?

**Đáp án:** không. Đây là hai raw fields cùng request; so sánh chúng trong bước validation, sau đó encode **một** raw password để lưu.

**Câu 6.** Một hash cũ cost 10 được kiểm tra bằng `BCryptPasswordEncoder(12)`. Có nhất thiết thất bại không?

**Đáp án:** không. Bcrypt chứa cost trong stored hash và có thể verify giá trị cũ. `upgradeEncoding` giúp xác định lúc nào nên băm lại bằng tham số mới.

**Câu 7.** Ứng dụng dùng `DelegatingPasswordEncoder` nhưng DB lưu `$2a$...` không có `{bcrypt}`. Có thể gặp vấn đề gì?

**Đáp án:** delegating encoder mặc định có thể không tìm thấy algorithm ID để chọn encoder và ném lỗi. Cần kế hoạch nhận diện format cũ và migration đúng cách.

**Câu 8.** Đổi cấu hình encoder sang cost 12 có tự thay toàn bộ hash cost 10 trong DB không?

**Đáp án:** không. Cần raw password hợp lệ để rehash trong flow xác thực/reset và lưu lại có kiểm soát.

**Câu 9.** Hai `UserDetails` có password hash khác nhau. Có nên dùng `getPassword().equals(...)` để tìm user trùng password?

**Đáp án:** không. Salt có thể khác nhau dù raw password giống nhau; ngoài ra dò xem người dùng trùng password không phải nhiệm vụ cần làm bằng việc so hash liên-account.

**Câu 10.** Vì sao không bỏ salt, chuyển sang một SHA-256 deterministic để có thể so sánh hash bằng `equals`?

**Đáp án:** vì làm giảm đáng kể khả năng chống cracking offline khi DB bị lộ. Dùng password hashing thích nghi và `matches` là đúng mục tiêu bảo mật.

## 15. Checklist khi viết code thực tế

- [ ] Khi đăng ký hoặc đổi/reset password, gọi `passwordEncoder.encode(raw)` rồi lưu **toàn bộ** chuỗi encoded.
- [ ] Khi kiểm tra password, gọi `passwordEncoder.matches(submittedRaw, storedHash)`.
- [ ] Không gọi `encode(submittedRaw).equals(storedHash)` và không dùng hai lần `encode` để xác nhận password.
- [ ] Không tự cắt/ghép hoặc chuẩn hóa sai salt, cost, prefix, version của stored hash.
- [ ] Nếu dùng `DelegatingPasswordEncoder`, giữ format `{id}encodedPassword` và migration với hash legacy có kiểm soát.
- [ ] Kiểm thử encoder bằng `matches` đúng/sai, không bắt hai lần encode phải khác nhau tuyệt đối.
- [ ] Code tạo account và provider login sử dụng các encoder tương thích; password trong DB không phải raw plaintext.
- [ ] Khi nâng cost/algorithm, dùng `upgradeEncoding` và rehash khi có raw password hợp lệ; không băm lại hash cũ như raw.
- [ ] Có test account disabled/locked, username không tồn tại, password sai và authorization sau xác thực.
- [ ] Không log raw password/hash, bảo vệ kênh HTTPS, giới hạn tốc độ login và monitor brute-force.
- [ ] Xử lý khoảng trắng, Unicode, độ dài password và chính sách lưu trữ nhất quán.
- [ ] Nếu thay encoder/version, kiểm tra stored hash format, runtime performance và khả năng rollback/migration.

**Kết luận:** hai lần `encode` có thể tạo ra **hai giá trị khác nhau dù cùng một mật khẩu**, vì password hashing an toàn dùng salt ngẫu nhiên và lưu tham số riêng trong encoded value. So sánh chuỗi hash mới tạo với hash đã lưu là kiểm tra sai. Trong Spring Security, **`encode(raw)` để lưu**, **`matches(raw, storedHash)` để xác minh** — đây là hợp đồng đúng, độc lập với việc hash mới có khác chuỗi hash cũ hay không.

## Tài liệu tham khảo

- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — Crypto Module / Password Encoding](https://docs.spring.io/spring-security/reference/6.5/features/integrations/cryptography.html)
- [Spring Security 6.5 — PasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security 6.5 — BCryptPasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — UserDetailsPasswordService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html)
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
