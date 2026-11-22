# NoOpPasswordEncoder và mật khẩu mẫu không phải cấu hình triển khai

> **Điểm phải nhớ:** `NoOpPasswordEncoder` **không băm, không mã hóa và không bảo vệ mật khẩu**: `encode(rawPassword)` trả lại chính nội dung mật khẩu; `matches(rawPassword, storedPassword)` về bản chất kiểm tra chuỗi có khớp. Spring Security vẫn giữ nó cho **legacy và kiểm thử**, nhưng đã đánh dấu **deprecated/insecure**. Dòng `{noop}password` trong tutorial là một **cú pháp tương thích** của `DelegatingPasswordEncoder`, **không phải một dạng lưu mật khẩu an toàn**. Mật khẩu như `password`, `123456` hay `demo-pass` trong ví dụ **không phải cấu hình để triển khai production**. Với tài khoản thực, phải dùng password hash thích nghi như Argon2id, bcrypt, scrypt hoặc PBKDF2 được cấu hình phù hợp, quản lý credential ngoài source và dùng HTTPS.

Bài thuộc nhóm **Mật khẩu** trong **Spring Security – fundamentals**, tập trung vào Spring Security 6.5.x, Java 17 và Spring Boot 3.5.x. Nội dung trả lời ba câu hỏi: **NoOp có gì sai?**, **vì sao tài liệu đôi khi vẫn chứa `{noop}` và password mẫu?**, **chuyển từ demo/legacy sang cấu hình có thể vận hành an toàn như thế nào?**

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác `PasswordEncoder.encode` và `PasswordEncoder.matches`, khác biệt giữa mã hóa hai chiều, hashing thích nghi và NoOp.
2. Chứng minh `NoOpPasswordEncoder.getInstance()` không bảo vệ secret bằng một unit test độc lập.
3. Đọc đúng `{noop}password`, `{bcrypt}$2a$...` và một hash bcrypt không có prefix khi dùng encoder trực tiếp.
4. Phân biệt **NoOpPasswordEncoder**, **`User.withDefaultPasswordEncoder()`**, **`BCryptPasswordEncoder`** và **`PasswordEncoderFactories.createDelegatingPasswordEncoder()`**.
5. Hiểu vì sao có `{noop}` trong tập decoder tương thích nhưng application mới **không được** lưu password dưới format này.
6. Cấu hình `UserDetailsService`, `PasswordEncoder` và `SecurityFilterChain` không làm lộ mật khẩu thật trong mã chạy production.
7. Chạy ứng dụng Spring Boot Java 17 mẫu với tài khoản chỉ bật trong profile `lab` và một chế độ mặc định không cho đăng nhập bằng user demo.
8. Viết MockMvc test kiểm tra Basic authentication thật (200/401/403) và CSRF, cùng unit test xác nhận mật khẩu được hash.
9. Lập kế hoạch migrate password legacy với thứ tự ưu tiên, rollback/monitoring, không “cứ thêm `{noop}`” để che lỗi cấu hình.
10. Nhận biết rủi ro kể cả khi đã dùng BCrypt: hard-coded shared passwords, log header, gửi HTTP không TLS, brute-force, thiếu revoke, phân quyền sai.

## 2. Đặt NoOpPasswordEncoder trong luồng xác thực

Một request HTTP Basic hoặc form login thông thường:

```text
Browser/client:
    username="alice", password="<mật khẩu người dùng nhập>"
                         |
                         v
               Authentication Filter
                         |
                         v
     UsernamePasswordAuthenticationToken (unauthenticated)
                         |
                         v
                 AuthenticationManager
                         |
                         v
                 DaoAuthenticationProvider
                     /            \
                    v              v
           UserDetailsService    PasswordEncoder
                    |              |
                    v              |
            stored password hash   |
                    +--------------+
                         |
                 matches(raw, stored)
                         |
              +----------+----------+
              |                     |
            false                  true
              |                     |
         AuthenticationException   Authentication verified
                                    |
                                    v
                             Authorization rules
```

`PasswordEncoder` có các method chính:

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

Đây là **chữ ký khái niệm** tương ứng Spring Security 6.5, không phải file người học cần tự khai báo: framework đã cung cấp interface. Trong code thật, implement có thể có chú thích/annotation bổ sung.

- `encode` dùng khi **tạo hoặc đổi** password; kết quả được lưu ở user store.
- `matches` dùng khi **đăng nhập**; nó so raw password được client đưa ra với password hash đã lưu.
- `upgradeEncoding` hỗ trợ nhận biết format/work factor cần nâng cấp, nếu implementation có logic đó.
- `UserDetailsService` chỉ tải username, encoded password và authorities; nó không tự thay công việc của password encoder/provider.
- Mật khẩu/encoded password không phải JWT, session cookie, CSRF token hay API key. Mỗi bí mật có vòng đời và phương thức xác minh riêng.

### 2.1. NoOp nằm ở đâu?

`NoOpPasswordEncoder` cũng implement interface `PasswordEncoder`, nhưng **thực hiện thao tác đồng nhất**:

```text
NoOpPasswordEncoder.encode("secret")
    -> "secret"

NoOpPasswordEncoder.matches("secret", "secret")
    -> true

NoOpPasswordEncoder.matches("wrong", "secret")
    -> false
```

Nó có thể giúp một bài học cực ngắn bỏ qua vấn đề hash để tập trung flow xác thực. Nhưng khi database hoặc config bị lộ, attacker nhìn thấy trực tiếp secret dùng để đăng nhập. Ngay cả khi chỉ dùng trong memory, source/hard-coded config vẫn có thể bị lộ qua Git, artifact, log hoặc snapshot.

**Điểm quan trọng:** `NoOpPasswordEncoder` **không phải một cách “tắt kiểm tra password”**. Nó vẫn so mật khẩu nhưng so ở dạng plaintext; đây không phải bảo mật password storage.

## 3. Vì sao Spring Security vẫn có NoOpPasswordEncoder?

### 3.1. Lý do lịch sử và tương thích

Các ứng dụng Spring Security cũ từng dùng plaintext password, và một số hệ thống phải đăng nhập vào dữ liệu legacy trong quá trình migrate. Spring Security giữ `NoOpPasswordEncoder` cho kịch bản tương thích và test, đồng thời đánh dấu **deprecated** vì không an toàn. “Có API trong thư viện” không đồng nghĩa “API được khuyến nghị cho production”.

Lịch sử Spring Security trước 5.0 có các mặc định khác; cách lưu mật khẩu hiện đại hỗ trợ nhiều algorithm/format qua `DelegatingPasswordEncoder`. Không dựa vào blog cũ có `NoOpPasswordEncoder.getInstance()` rồi sao chép nguyên sang app mới.

### 3.2. Lệnh chính xác để lấy singleton

```java
import org.springframework.security.crypto.password.NoOpPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

// CHỈ TRONG UNIT TEST ĐỂ CHỨNG MINH VÌ SAO NÓ KHÔNG AN TOÀN.
PasswordEncoder noop = NoOpPasswordEncoder.getInstance();
String stored = noop.encode("test-secret");

System.out.println(stored.equals("test-secret"));  // true
System.out.println(noop.matches("test-secret", stored)); // true
```

**Đây là snippet minh họa**, không phải file Java độc lập: import, class và `main` đã được lược bỏ. Trong mục 9 có unit test hoàn chỉnh. API trả singleton `PasswordEncoder`; không cần `new NoOpPasswordEncoder()` vì constructor không phải hướng sử dụng công khai. Deprecation warning ở đây là **cảnh báo bảo mật có chủ đích**, không phải warning để suppress trong config deploy.

### 3.3. “No-op” nghĩa là gì và không nghĩa là gì?

| Phát biểu | Đúng/sai | Giải thích |
| --- | --- | --- |
| NoOp không tạo password hash | **Đúng** | Output bằng raw input |
| NoOp ngăn password bị lộ nếu DB dump | **Sai** | Đọc được plaintext |
| NoOp không kiểm password | **Sai** | Nó vẫn so trực tiếp |
| NoOp chỉ nguy hiểm khi ứng dụng dùng HTTP | **Sai** | HTTPS bảo vệ đường truyền, không bảo vệ DB dump/source |
| NoOp có thể tồn tại để đọc dữ liệu legacy | **Đúng** | Mục đích tương thích có điều kiện; phải migrate |
| NoOp bị deprecated nên không thể compile | **Sai** | Deprecated không đồng nghĩa removed |
| `{noop}` là một kiểu băm | **Sai** | Nó là ID format cho việc so plaintext |
| NoOp thích hợp làm `@Bean PasswordEncoder` production | **Sai** | Toàn bộ credential có thể lưu plaintext |
| Hashing password thay cho HTTPS | **Sai** | Password người dùng vẫn đi qua mạng |
| Mật khẩu mẫu trong documentation đủ mạnh cho production | **Sai** | Credential công khai, dễ đoán và dùng chung |

## 4. Hiểu đúng `{noop}` của DelegatingPasswordEncoder

### 4.1. Format của password được lưu

`DelegatingPasswordEncoder` chọn một thuật toán dựa vào prefix:

```text
{id}encodedPassword
```

Ví dụ:

```text
{noop}legacy-password
{bcrypt}$2a$10$...phần-hash-bcrypt...
{pbkdf2@SpringSecurity_v5_8}...phần-hash-pbkdf2...
{argon2@SpringSecurity_v5_8}...phần-hash-argon2...
```

**Chú ý:** Các dấu ba chấm là ký hiệu giải thích, **không phải** password hash hợp lệ để lưu trực tiếp. Với implementation mặc định từ `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, phần `{id}` quyết định decoder khi login. Encoder mới mặc định được chọn để **encode** thường là `bcrypt`, còn một số decoder legacy được cung cấp cho **matches**.

`{noop}legacy-password` có nghĩa: phần stored password là `legacy-password` ở dạng plaintext. Prefix `{noop}` **không thêm hash, salt, encryption hay bất kỳ mức bảo vệ nào**.

### 4.2. Cấu hình hiện đại được khuyến nghị để hiểu format

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
```

Với factory trên, Spring Security 6.5 dùng bcrypt để **encode password mới** và gắn prefix `{bcrypt}`. Khi `matches` với một stored hash có prefix được hỗ trợ, nó chọn implementation tương ứng; bao gồm `{noop}` vì lý do legacy/testing. Sự có mặt của decoder NoOp **không cho phép đưa plaintext password mới vào DB**.

Một ví dụ mô tả (hash thật có salt ngẫu nhiên nên không cố định):

```text
Input password:
    "SomeLabPassphrase2026!"

passwordEncoder.encode(input):
    "{bcrypt}$2a$10$..."  (hash dài, phụ thuộc salt)

passwordEncoder.matches(input, encoded):
    true

passwordEncoder.matches("wrong", encoded):
    false

passwordEncoder.matches("legacy-password", "{noop}legacy-password"):
    true  <-- TÍNH TƯƠNG THÍCH, không phải mức bảo mật mới
```

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` **không tự nhận plaintext không prefix như một định dạng hợp lệ**. Nếu stored password là `abc123` nhưng encoder đòi `{id}`, thường thấy lỗi:

```text
There is no PasswordEncoder mapped for the id "null"
```

Giải pháp không phải gắn `{noop}` vào toàn bộ password mới. Phải xác định store đang dùng format gì, định nghĩa kế hoạch migrate rõ ràng, và chọn encoder phù hợp với dữ liệu còn lại trong khoảng chuyển tiếp.

### 4.3. So sánh với BCryptPasswordEncoder trực tiếp

```java
PasswordEncoder direct = new BCryptPasswordEncoder();
String hash = direct.encode("SomeLabPassphrase2026!");
// Kết quả dạng $2a$... hoặc biến thể bcrypt phù hợp.
// Không tự có prefix "{bcrypt}" do DelegatingPasswordEncoder thêm.
```

Khi dùng `BCryptPasswordEncoder` trực tiếp, nó thường nhận chuỗi hash bcrypt định dạng `$2a$...`, `$2b$...` tùy version; **không tự yêu cầu `{bcrypt}` prefix**. Khi dùng `DelegatingPasswordEncoder` mặc định, stored password cần prefix để chọn decoder.

| Encoder khai báo | `encode("password")` tạo ra | Stored value mà `matches` chấp nhận |
| --- | --- | --- |
| `NoOpPasswordEncoder` | `password` | `password` plaintext |
| `BCryptPasswordEncoder` trực tiếp | bcrypt hash (thường `$2a$...`) | bcrypt hash trực tiếp |
| `DelegatingPasswordEncoder` mặc định | `{bcrypt}` + bcrypt hash | Có `{id}` tương ứng mapping, gồm các legacy format |
| `User.withDefaultPasswordEncoder()` | hash bcrypt có prefix phù hợp helper | Không phải căn cứ để bỏ password security ở production |

**Quan trọng:** Không thêm prefix `{noop}` trước một bcrypt hash. `{noop}$2a$...` làm cho encoder đem chuỗi input so trực tiếp với các ký tự hash — login đúng password thật sẽ không hoạt động. Cũng không bỏ `{bcrypt}` của stored value rồi dùng Delegating encoder mà không cấu hình mapping, bởi decoder không biết ID.

## 5. `User.withDefaultPasswordEncoder()` không giống NoOp

Trong tài liệu học Spring Security có thể thấy:

```java
UserDetails user = User.withDefaultPasswordEncoder()
    .username("student")
    .password("SamplePasswordForDemoOnly")
    .roles("USER")
    .build();
```

Helper này có thể **hash password** theo cấu hình tiện lợi và lưu giá trị dạng `{bcrypt}...`, khác với NoOp. Nhưng lời khuyên chính thức là **chỉ dùng convenience helper cho bài học/sample**: raw password vẫn xuất hiện nguyên văn trong Java source, compiled artifact hoặc một số dạng cấu hình; attacker có thể đọc credential trước cả khi tính đến database hash.

**Phân biệt hai rủi ro:**

1. **NoOp:** Password được lưu plaintext trong `UserDetails`/DB — rủi ro tại nơi lưu.
2. **withDefaultPasswordEncoder + hard-coded raw password:** Stored value có thể được hash an toàn, **nhưng raw password vẫn nằm trong source/build artifact** — rủi ro supply chain/deployment/source disclosure.

Không nên nói rằng cứ gọi `encode` là tự động an toàn. An toàn password yêu cầu cả **mật khẩu nguồn**, **hashing ở rest**, **giao thức mạng**, **quản trị tài khoản** và **vòng đời credential**.

### 5.1. Hard-coded bcrypt hash có an toàn tuyệt đối không?

Không. Nếu source chứa một hash bcrypt của mật khẩu mẫu công khai (`Demo123!`), attacker biết luôn plaintext vì mật khẩu nằm trong hướng dẫn hoặc có thể đoán. Nếu source chứa một hash cho password thật bí mật nhưng shared bởi nhiều môi trường, tài khoản ấy vẫn khó revoke, dễ bị dùng lại và nguy hiểm khi lộ. Với CI, image/container và config repo, attacker có thể thử crack các mật khẩu yếu. Hãy dùng user store/IdP và secret management thực thay vì tài khoản chung dùng lâu dài.

### 5.2. Spring Boot generated user không phải tài khoản triển khai

Khi thêm `spring-boot-starter-security` mà chưa cung cấp user/provider, Spring Boot MVC có thể tạo user mặc định `user` và password ngẫu nhiên, ghi vào log ở mức WARN. Tài liệu Boot ghi rõ generated password **chỉ phục vụ phát triển**.

Nếu đặt `spring.security.user.password=demo-pass` trong `application.properties` và sử dụng account đó ở server công khai, password đã trở thành secret dễ lộ qua cấu hình, artifact hoặc deployment tooling. Dù app có hash password nội bộ, đây vẫn là tài khoản mẫu/shared credential không có quản lý vòng đời thích hợp.

**Dùng production:** cấu hình đúng nguồn user/identity provider, không dùng generated user, không có test users và không lưu raw password trong repository. Cần có kiểm tra CI/deployment để phát hiện tài khoản mẫu hoặc profile lab bị bật nhầm.

## 6. Những lớp bảo vệ password khác nhau

| Lớp | Vấn đề giải quyết | NoOp có giúp không? |
| --- | --- | --- |
| Password hashing tại storage | Hạn chế phục hồi plaintext nếu user DB bị dump | **Không** |
| Salt ngẫu nhiên | Ngăn cùng password luôn có hash giống nhau và giảm hiệu quả precomputed attacks | **Không** |
| Work factor / memory hardness | Làm đoán offline đắt tài nguyên hơn | **Không** |
| HTTPS/TLS | Bảo vệ credential qua mạng | **Không**; dùng bcrypt cũng phải có TLS |
| Secret management | Tránh raw credential trong Git/build/env được phơi | **Không** |
| Account lockout/rate limit | Giới hạn online guessing, credential stuffing | **Không** |
| MFA/passkey/step-up | Tăng bảo đảm xác thực trong flow nhạy cảm | **Không** |
| Authorization trên route/resource | Hạn chế quyền sau login | **Không** |
| Session/token revocation | Thu hồi truy cập khi có compromise | **Không** |
| Logging redaction | Tránh Basic header/password bị ghi ra log | **Không** |

### 6.1. Password hashing là một chiều, không phải encryption

Đối với mật khẩu đăng nhập, backend **không cần giải mã password hash để so**. Nó dùng `matches(raw, storedHash)`. Mã hóa hai chiều như AES có thể hữu ích cho dữ liệu nghiệp vụ phải đọc lại, nhưng không phải lựa chọn thông thường để lưu password xác thực vì key giải mã bị lộ sẽ làm lộ tất cả password.

Không dùng `Base64.getEncoder()`, MD5, SHA-1 hoặc SHA-256 thô như một password storage algorithm. Base64 chỉ là encoding có thể đảo ngược; hash nhanh cho phép attacker thử lượng lớn password offline. Với secret entropy cao do CSPRNG sinh ra (ví dụ reset token) threat model khác, nhưng **mật khẩu người dùng** phải dùng password-hashing algorithm phù hợp.

### 6.2. Những lựa chọn thích nghi

- **Argon2id:** thường được OWASP khuyến nghị cho hệ thống mới, có tham số memory/time/parallelism; cần dependency hỗ trợ và benchmark trên hardware thật.
- **bcrypt:** phổ biến, được Spring Security hỗ trợ dễ dàng; chú ý giới hạn đầu vào hiệu dụng của bcrypt và cân nhắc work factor theo tải thực tế.
- **scrypt:** password hashing memory-hard được Spring Security hỗ trợ.
- **PBKDF2:** hữu ích khi có yêu cầu FIPS hoặc ecosystem phù hợp, phải chọn PRF/iterations đủ mạnh theo hướng dẫn hiện hành.
- **DelegatingPasswordEncoder:** định tuyến định dạng hiện hành/legacy theo prefix, hỗ trợ kế hoạch nâng cấp mà không buộc reset mọi user cùng lúc.

Không chọn tham số cost chỉ bằng cách sao chép một con số từ Stack Overflow. Password check phải đủ đắt để chống offline guessing nhưng vẫn đáp ứng login latency/peak traffic và không mở khả năng DoS chi phí cao. Benchmark trong hạ tầng thật, có rate limiting và monitor login failures.

### 6.3. Salt và pepper

Salt ngẫu nhiên thường do adaptive password encoder tự tạo và lưu cùng hash, không cần giữ bí mật; nó giúp mỗi password có hash riêng dù plaintext giống nhau. Pepper là một secret phía hệ thống có thể dùng thêm defense-in-depth nếu kiến trúc có HSM/secret store phù hợp; phải quản lý rotation, backup và compromise response. **Pepper không thay salt hoặc adaptive hash.**

### 6.4. TLS không đủ nếu mã lưu password sai

Ví dụ ứng dụng dùng HTTPS nhưng lưu `User.password="alice123"` trong bảng users, khi database bị dump vẫn lộ password. Ngược lại, ứng dụng dùng bcrypt nhưng truyền password qua HTTP không TLS có thể để attacker trên mạng lấy raw password. Phải dùng **cả hai**, cộng quyền truy cập tối thiểu và audit thích hợp.

### 6.5. Không nên kiểm hash ở controller

```java
// Phản ví dụ thiết kế:
if (request.password().equals(user.getPasswordHash())) {
    // ...
}
```

Đoạn này sai vì so raw password với hash; nếu stored password là NoOp plaintext, nó có thể “chạy được” và che lấp bug. Với Spring Security, nên để `DaoAuthenticationProvider` + `PasswordEncoder` thực hiện credential validation. Nếu app có password reset/change nghiệp vụ riêng, service dùng encoder để hash password mới và repository chỉ lưu hash, không tự nhận client-supplied hash làm “password mới”.

## 7. Phản ví dụ: cấu hình tuyệt đối không triển khai

### 7.1. Đăng ký NoOpPasswordEncoder bean

```java
// PHẢN VÍ DỤ NGUY HIỂM: KHÔNG DÙNG CHO DEPLOYMENT.
@Configuration
class InsecureSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return NoOpPasswordEncoder.getInstance();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("admin")
                .password("admin123")
                .roles("ADMIN")
                .build()
        );
    }
}
```

Đây là **snippet có chủ ý để phân tích rủi ro**, cần các import Spring tương ứng. Nếu được đặt vào application context, bean NoOp có thể làm credential validation hoạt động với password mẫu plaintext và tạo admin account công khai. Nó không tự tạo security chain hoàn chỉnh, nhưng khi được dùng bởi authentication provider, rủi ro nằm ở **lưu credential** và **quyền admin dễ đoán**.

**Vì sao nghiêm trọng?** Source chứa username/password, jar có thể bị đọc, CI logs hoặc deployment environment có thể lộ; nếu có endpoint admin, một credential mẫu công khai có thể trao quyền cao. Kể cả đổi password thành một chuỗi dài nhưng vẫn hard-coded và dùng chung giữa môi trường, việc rotation/revocation rất khó.

### 7.2. Prefix NoOp không sửa vấn đề

```java
UserDetails user = User.withUsername("admin")
    .password("{noop}admin123")
    .roles("ADMIN")
    .build();
```

Đoạn này cũng là **phản ví dụ**, dùng `DelegatingPasswordEncoder` có mapping noop thì Basic/form login có thể so plaintext phía sau prefix. Việc “có ngoặc nhọn” chỉ làm Spring Security biết **cách so**, không phải password đã được băm.

### 7.3. Đặt mật khẩu trong application.yml

```yaml
# PHẢN VÍ DỤ — KHÔNG COMMIT VÀ KHÔNG DEPLOY.
spring:
  security:
    user:
      name: admin
      password: admin123
      roles: ADMIN
```

`spring.security.user.*` là tiện ích development của Boot. Production dùng tài khoản thật/IdP/secret management; đừng coi YAML là nơi cất credential an toàn vì nó có thể nằm trong source, config server, image, snapshot hoặc biến môi trường của build.

### 7.4. “Tôi chỉ dùng localhost” có an toàn không?

Dùng account mẫu khi chạy lab **có thể chấp nhận** nếu hoàn toàn tách khỏi môi trường thật, chỉ bind loopback, không truy cập dữ liệu thật, không tái sử dụng password và không dùng quyền cao ngoài phạm vi. Nhưng đừng đưa cấu hình mẫu lên staging public hoặc bản production chỉ vì “trong test nó chạy”. CI/CD nên có guard chặn profile/test users không được bật tại deployment.

### 7.5. “Mật khẩu đã bị hash trong DB, sao source vẫn nguy hiểm?”

Nếu source chứa:

```java
.password(encoder.encode("CommonPassword2026!"))
```

thì password được hash **khi chạy** nhưng raw plaintext vẫn nằm trong source. Attacker biết password mà không cần crack hash, đặc biệt nếu cùng password được tái sử dụng trên nhiều môi trường. Đây là lý do một demo dùng bcrypt vẫn không trở thành production-ready chỉ nhờ đã gọi `encode`.

## 8. Mẫu có kiểm soát: lab profile, encoder an toàn, default không có account mẫu

Phần này xây một Spring Boot MVC app có policy:

1. `PasswordEncoder` là `DelegatingPasswordEncoder` với bcrypt cho password mới, **không phải NoOp bean**.
2. User mẫu tồn tại **chỉ khi bật profile `lab`** và chỉ dành cho máy học.
3. Khi **không bật lab**, app tạo `UserDetailsService` từ chối mọi username để tránh Spring Boot tự sinh default user thay chỗ; đây là một cấu hình **fail-closed phục vụ ví dụ**, không phải backend user store production.
4. `SecurityFilterChain` bảo vệ `/me`, `/admin`, `POST /notes` và deny routes khác.
5. Mật khẩu demo trong Java source là **test data**, không phải secret; đừng đem source này triển khai công khai hoặc tái sử dụng mật khẩu đó cho bất kỳ tài khoản thật nào.
6. Unit test có thể dùng `NoOpPasswordEncoder` **chỉ để quan sát**, nhưng trong application bean không dùng NoOp làm password encoder.

**Phiên bản lab:** Java 17+, Spring Boot **3.5.16** và Spring Security 6.5.x do Boot BOM quản lý. Spring Boot 3.5.16 là bản OSS cuối dòng 3.5.x (phát hành ngày 25/06/2026); hệ thống production mới phải theo nhánh được hỗ trợ như Boot 4.x và cập nhật guide/version tương ứng.

### 8.1. Cấu trúc thư mục

```text
password-encoder-lab/
├── pom.xml
└── src/
    ├── main/java/demo/password/PasswordEncoderLabApplication.java
    └── test/java/demo/password/
        ├── PasswordEncoderBehaviorTests.java
        └── PasswordEncoderHttpTests.java
```

### 8.2. Maven pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>password-encoder-lab</artifactId>
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
```

### 8.3. Java application đầy đủ

Tạo `src/main/java/demo/password/PasswordEncoderLabApplication.java`:

```java
package demo.password;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PasswordEncoderLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordEncoderLabApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class LabSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        // encode mới -> {bcrypt}...; có mapping legacy cho matches.
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    @Profile("lab")
    UserDetailsService labUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("LabOnlyPassphrase2026!"))
                .authorities("ROLE_USER", "NOTES_WRITE")
                .build(),
            User.withUsername("lab-admin")
                .password(encoder.encode("LabAdminPassphrase2026!"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    @Profile("!lab")
    UserDetailsService noDemoUsersOutsideLab() {
        // Ví dụ fail-closed: không có account lab/default để đăng nhập.
        // Production phải THAY bean này bằng identity provider thực.
        return username -> {
            throw new UsernameNotFoundException(
                "No application user store configured");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/notes")
                    .hasAuthority("NOTES_WRITE")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(Customizer.withDefaults())
            .build();
    }
}

@RestController
class LabController {

    @GetMapping("/public")
    String publicMessage() {
        return "public";
    }

    @GetMapping("/me")
    String currentUser(Authentication authentication) {
        return "me:" + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin-ok";
    }

    @PostMapping("/notes")
    String createNote(Authentication authentication) {
        // Lab không ghi vào database.
        return "created:" + authentication.getName();
    }
}
```

**Điểm cần quan sát:**

- `@Profile("lab")` khiến user mẫu chỉ được khai báo khi profile lab active. Đây là biện pháp phân tách **ở cấp Spring bean**, nhưng **không phải bảo đảm production không thể bật nhầm lab**. Ứng dụng thật cần build/deployment policy chặn profile này ở production hoặc đặt fixture hoàn toàn trong `src/test`.
- `@Profile("!lab")` tạo một nguồn user không xác thực bất kỳ username nào khi lab không active. Điều này vừa tránh generated default user của Boot trong demo, vừa minh họa nguyên tắc **fail closed**. Nó không phải user management implementation thực tế.
- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` cho phép password mới trong lab được hash bằng bcrypt với prefix `{bcrypt}`. **Không có bean `NoOpPasswordEncoder` trong main app**.
- Password như `LabOnlyPassphrase2026!` cố ý nằm trong source của lab và chỉ để người học thử. Vì source công khai, nó **không được xem là bí mật**, kể cả khi stored hash của nó được BCrypt bảo vệ.
- `httpBasic` chỉ truyền username/password trong HTTP Basic header; Base64 không phải encryption. Với mạng thật phải HTTPS; lab sử dụng loopback.
- `SessionCreationPolicy.STATELESS` làm mỗi request cần credential; không giả định request sau tự nhớ principal.
- CSRF bật. `POST /notes` cần CSRF token hợp lệ trong test; không tắt CSRF chỉ để curl POST thuận tiện.
- `anyRequest().denyAll()` áp dụng cho chain mặc định bao phủ tất cả request, không có cửa sau ngoài các URL được cấp rõ.
- Demo có endpoint public để kiểm tra authorization; với production, phải triển khai identity source thực, secrets và policy nghiệp vụ, chứ không dùng một app “không có user” làm hệ thống đăng nhập đầy đủ.

### 8.4. Các mối nguy ngay cả khi dùng bcrypt

Mặc dù demo không dùng NoOp làm bean:

1. Nếu copy account `lab-admin` sang production, username/password từ source có thể bị attacker biết và dùng cho tài khoản admin thật.
2. Nếu bật profile lab trên server public, cả hai account demo đều đăng nhập được theo quyền khai báo.
3. Nếu dùng HTTP không TLS, attacker trên mạng có thể nhìn raw Basic header; BCrypt tại storage không giúp.
4. Nếu log `Authorization`, credential có thể bị lộ qua log aggregation/observability.
5. Nếu bỏ rate limiting, attacker vẫn có thể thử nhiều password online dù bcrypt đắt CPU.
6. Nếu chỉ bảo vệ đường `/admin` bằng login mà không kiểm owner/tenant ở service, account đúng role có thể truy cập dữ liệu ngoài phạm vi.
7. Nếu dùng cùng một password mẫu cho nhiều test/staging/production, sự cố môi trường ít an toàn có thể lan sang nơi khác.

**Ranh giới rõ ràng:** Ví dụ này minh họa cách **không dùng NoOp trong main application** và cách tách user demo theo profile; nó **không đủ để đưa lên Internet** như một sản phẩm thật.

## 9. Unit test: chứng minh NoOp khác bcrypt/Delegating

Tạo `src/test/java/demo/password/PasswordEncoderBehaviorTests.java`:

```java
package demo.password;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.NoOpPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PasswordEncoderBehaviorTests {

    @Test
    void noopDemonstratesPlaintextRiskOnlyInIsolatedTest() {
        // Deprecated là điều có chủ đích: không đăng ký encoder này làm bean.
        PasswordEncoder noop = NoOpPasswordEncoder.getInstance();

        String stored = noop.encode("test-only-secret");

        assertEquals("test-only-secret", stored);
        assertTrue(noop.matches("test-only-secret", stored));
        assertFalse(noop.matches("incorrect", stored));

        // Mật khẩu stored bị lộ trực tiếp — lý do NoOp không an toàn.
        assertFalse(stored.startsWith("{bcrypt}"));
    }

    @Test
    void delegatingEncoderHashesNewPasswordsAndUnderstandsLegacyId() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String raw = "LongLabPassphrase2026!";
        String stored = encoder.encode(raw);

        assertTrue(stored.startsWith("{bcrypt}"));
        assertNotEquals(raw, stored);
        assertTrue(encoder.matches(raw, stored));
        assertFalse(encoder.matches("wrong-password", stored));

        // Đoạn này chứng minh khả năng đọc LEGACY, KHÔNG KHUYẾN NGHỊ LƯU.
        assertTrue(encoder.matches("legacy-secret", "{noop}legacy-secret"));
        assertFalse(encoder.matches("bad", "{noop}legacy-secret"));

        // Plaintext không prefix không phải storage format hợp lệ
        // cho DelegatingPasswordEncoder mặc định.
        assertThrows(IllegalArgumentException.class,
            () -> encoder.matches(raw, "plain-without-id"));
    }

    @Test
    void directBcryptHashAndDelegatingHashHaveDifferentFormats() {
        PasswordEncoder direct = new BCryptPasswordEncoder();
        PasswordEncoder delegating =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String raw = "AnotherLabPassphrase2026!";
        String directHash = direct.encode(raw);
        String delegatedHash = delegating.encode(raw);

        assertTrue(directHash.startsWith("$2"));
        assertTrue(delegatedHash.startsWith("{bcrypt}"));

        assertTrue(direct.matches(raw, directHash));
        assertTrue(delegating.matches(raw, delegatedHash));

        // Cả hai dùng salt; hash khác nhau vẫn khớp cùng raw password.
        assertNotEquals(directHash, delegatedHash);

        // Không đưa hash trực tiếp thiếu {id} vào Delegating mà không migrate.
        assertThrows(IllegalArgumentException.class,
            () -> delegating.matches(raw, directHash));
    }
}
```

Mục đích của test:

- `noopDemonstratesPlaintextRiskOnlyInIsolatedTest` **cố ý gọi một API insecure** để hiểu rủi ro, nhưng không tạo bean và không có tài khoản thật.
- `delegatingEncoderHashesNewPasswordsAndUnderstandsLegacyId` cho thấy nhà phát triển có thể tương thích dữ liệu cũ trong khi vẫn tạo hash mới; **sự tương thích không phải giấy phép tiếp tục lưu plaintext**.
- `directBcryptHashAndDelegatingHashHaveDifferentFormats` chứng minh prefix và salt. Không hard-code toàn bộ bcrypt hash kỳ vọng: salt làm kết quả thay đổi.
- Warning của compiler vì `NoOpPasswordEncoder` deprecated là đúng ý, không phải một lỗi cần “chữa” bằng việc nâng version hoặc tạo adapter production.

## 10. MockMvc integration test: đúng credential, sai credential, đúng role, thiếu CSRF

Tạo `src/test/java/demo/password/PasswordEncoderHttpTests.java`:

```java
package demo.password;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("lab")
class PasswordEncoderHttpTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    UserDetailsService users;

    @Autowired
    PasswordEncoder encoder;

    @Test
    void labPasswordsAreHashedAndManagedByServer() {
        UserDetails student = users.loadUserByUsername("student");
        String stored = student.getPassword();

        assertTrue(stored.startsWith("{bcrypt}"));
        assertFalse(stored.equals("LabOnlyPassphrase2026!"));
        assertTrue(encoder.matches("LabOnlyPassphrase2026!", stored));

        assertTrue(student.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_USER")));
        assertTrue(student.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("NOTES_WRITE")));
    }

    @Test
    void basicCredentialsAreVerifiedByRealProvider() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .with(httpBasic("student", "LabOnlyPassphrase2026!")))
            .andExpect(status().isOk())
            .andExpect(content().string("me:student"));

        mvc.perform(get("/me")
                .with(httpBasic("student", "bad-password")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .with(httpBasic("not-a-user", "LabOnlyPassphrase2026!")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticationDoesNotGrantEveryAuthority() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("student", "LabOnlyPassphrase2026!")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("lab-admin", "LabAdminPassphrase2026!")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-ok"));

        mvc.perform(post("/notes")
                .with(httpBasic("lab-admin", "LabAdminPassphrase2026!"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void postRequiresBothCsrfTokenAndPermission() throws Exception {
        mvc.perform(post("/notes")
                .with(httpBasic("student", "LabOnlyPassphrase2026!")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/notes")
                .with(httpBasic("student", "LabOnlyPassphrase2026!"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        mvc.perform(post("/notes")
                .with(httpBasic("student", "LabOnlyPassphrase2026!"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created:student"));

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unmatchedPathIsDenied() throws Exception {
        mvc.perform(get("/unlisted")
                .with(httpBasic("student", "LabOnlyPassphrase2026!")))
            .andExpect(status().isForbidden());
    }
}
```

**Vì sao dùng `httpBasic` thay vì chỉ `@WithMockUser`?** `@WithMockUser` tạo principal giả trong test để kiểm tra authorization, **không chứng minh password hash và provider làm việc đúng**. `httpBasic("student", "...")` gửi header HTTP Basic qua security filter, provider dùng `UserDetailsService` cùng `PasswordEncoder` thật của lab. Đây là cách test hiện tượng đăng nhập đúng/sai và quyền.

Test cũng chứng minh một user có `ROLE_ADMIN` **không mặc nhiên** có `NOTES_WRITE`, và CSRF có thể chặn POST độc lập với permission. `403` trong một test thiếu CSRF **không tự chứng minh** provider đã chấp nhận password; các test GET và POST có CSRF hợp lệ cho thêm bằng chứng.

### 10.1. Lệnh chạy

Ở thư mục có `pom.xml`:

```bash
java -version
mvn -version
mvn test
```

Các test JUnit/MockMvc ở trên không cần mở browser hoặc cổng TCP. `mvn test` được kỳ vọng thành công nếu mã và dependency tương thích; **đây là lệnh/kết quả dự kiến để người học tự thực thi**, không phải thông báo đã chạy Maven ở môi trường viết bài.

Chạy app ở chế độ lab trên máy phát triển:

```bash
mvn spring-boot:run -Dspring-boot.run.profiles=lab
```

Dùng terminal khác và chỉ gọi `localhost`:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u student http://localhost:8080/me
curl -i -u student http://localhost:8080/admin
curl -i -u lab-admin http://localhost:8080/admin
```

Khi `curl -u student` hoặc `curl -u lab-admin` hỏi mật khẩu, nhập **lab-only** `LabOnlyPassphrase2026!` hoặc `LabAdminPassphrase2026!`. Không nhúng password vào command line/history và không dùng account này trên hệ thống public. Với PowerShell cũ, có thể cần dùng `curl.exe` thay alias `curl`.

Bảng hành vi của demo:

| Request | Credential | Status kỳ vọng |
| --- | --- | --- |
| `GET /public` | Không có | 200 |
| `GET /me` | Không có | 401 |
| `GET /me` | Student đúng password | 200 |
| `GET /me` | Student sai password | 401 |
| `GET /admin` | Student đúng password | 403 |
| `GET /admin` | Lab admin đúng password | 200 |
| `POST /notes` | Student đúng, thiếu CSRF | 403 |
| `POST /notes` | Student đúng, CSRF hợp lệ | 200 |
| `POST /notes` | Lab admin đúng, CSRF hợp lệ nhưng thiếu NOTES_WRITE | 403 |
| `GET /unlisted` | Student đúng | 403 |

Nếu chạy **không bật lab**, bean user store trả `UsernameNotFoundException` cho mọi username; `GET /me` không thể được dùng bởi account demo. Điều này chứng minh **cấu hình fail closed của bài học**, nhưng không có nghĩa đây là một production identity solution. Trước triển khai thật phải thay bằng user store/IdP với lifecycle an toàn, test integration, secret management, TLS, rate limit và kiểm soát deployment profile.

## 11. Khó khăn khi migrate dữ liệu cũ dạng plaintext hoặc `{noop}`

Đây là trường hợp nhiều người dễ sửa sai nhất. Giả sử database chứa:

```text
username | stored_password
alice    | {noop}alice-old-pass
bob      | {bcrypt}$2a$10$...
charlie  | plain-without-prefix
```

**Chỉ là dữ liệu minh họa**; không dùng password thực và không paste hash/token từ production vào issue. Những hàng này thuộc ba định dạng khác nhau. Với `DelegatingPasswordEncoder` mặc định:

- Alice có thể được so qua legacy `noop` mapping — dữ liệu **chưa an toàn** vì plaintext nằm trong DB.
- Bob dùng bcrypt theo prefix — định dạng tương thích với delegating encoder.
- Charlie không có prefix — có thể ném lỗi ID `null`; không được âm thầm coi toàn bộ hàng không prefix là plaintext nếu chưa xác minh nguồn dữ liệu.

### 11.1. Quy trình migrate đáng tin

1. **Kiểm kê có giới hạn:** Xác định hệ thống chứa format nào (plaintext, bcrypt không prefix, PBKDF2 với prefix version, hash tùy chỉnh), số lượng account và rủi ro; không dump plaintext password ra file CSV dùng chung.
2. **Chặn đường tạo dữ liệu mới sai:** Tất cả đăng ký/đổi password/reset mới chỉ ghi hash thích nghi theo policy hiện hành. Không cho code mới ghi `{noop}`.
3. **Xác định mapping theo bằng chứng:** Chỉ thêm prefix cho giá trị đã được xác định chắc chắn là một format; không áp quy tắc “không prefix thì noop” cho tất cả.
4. **Tách xử lý legacy:** Giới hạn thời gian, scope và quyền truy cập decoder legacy; có feature flag/config riêng và audit login legacy.
5. **Nâng cấp sau khi credential được xác thực:** Khi người dùng nhập đúng raw password, có thể `encode` lại bằng algorithm mới và lưu hash, qua `UserDetailsPasswordService`/logic upgrade được tích hợp đúng.
6. **Reset bắt buộc cho tài khoản không thể nâng cấp an toàn:** Nếu không còn plaintext (chỉ hash legacy yếu) hoặc policy buộc chặn, yêu cầu đặt lại password qua kênh recovery được kiểm chứng; không gửi password mới qua email.
7. **Thu hồi/khóa đường legacy:** Khi các account đã được chuyển, ngừng chấp nhận `{noop}`, xóa code tương thích, rotate secrets liên quan và theo dõi error rate.
8. **Test rollback và quan sát:** Đo tỷ lệ login, account lockout, lỗi decode ID, tốc độ tăng CPU khi nâng work factor và khả năng rollback một cách an toàn mà không ghi plaintext trở lại.

### 11.2. `upgradeEncoding` và UserDetailsPasswordService

`PasswordEncoder.upgradeEncoding(storedHash)` có thể cho biết hash/format hiện tại nên được mã hóa lại. Trong cơ chế hỗ trợ, `DaoAuthenticationProvider` có thể phối hợp `UserDetailsPasswordService` để lưu hash mới **sau khi password được xác thực thành công**.

**Quan trọng:** Tự tạo `PasswordEncoder` không đồng nghĩa database tự migrate. Phải có repository/service ghi hash, giao dịch an toàn, điều kiện concurrency, và test đúng provider/implementation. Không đặt logic upgrade vào controller theo input `newEncodedPassword` do client tự gửi.

Một sketch minh họa kiến trúc:

```java
// Snippet — cần repository, entity và transactional policy của dự án.
class DatabaseUserDetailsPasswordService
        implements UserDetailsPasswordService {

    @Override
    public UserDetails updatePassword(
            UserDetails user, String newEncodedPassword) {
        // Lưu hash MỚI đã được encoder tạo (không phải raw password).
        // Cần kiểm tra ownership, version, transaction, audit tối thiểu.
        // Trả về UserDetails phản ánh password hash mới.
        return updatedUserDetails;
    }
}
```

Đoạn này **không biên dịch độc lập** vì `updatedUserDetails` là placeholder mô tả phụ thuộc domain; **không phải mã chạy**. Trong implementation thật, lưu một `password_hash` tại repository có optimistic lock rồi trả `UserDetails` đã cập nhật. Không xóa/bỏ prefix bừa bãi.

### 11.3. Vì sao không tự động `setDefaultPasswordEncoderForMatches(NoOp)`?

`DelegatingPasswordEncoder.setDefaultPasswordEncoderForMatches(...)` có thể cấu hình fallback cho ID không biết. Nhưng nếu fallback là NoOp, mọi stored password không có ID được đem so plaintext, che giấu sai dữ liệu và nới phạm vi legacy hơn dự kiến. Với unknown format, **fail closed**, log metric đã redacted để đội kỹ thuật xử lý, hoặc áp một migration adapter có phạm vi rất chặt và plan loại bỏ. Không dùng cấu hình “mọi null ID trở thành plaintext” để sửa lỗi startup.

### 11.4. Không cần giải mã bcrypt để migrate

Hash thích nghi là một chiều; bạn không thể “decrypt hash” để lấy lại raw password. Migrate đúng là:

- Với account có raw password hợp lệ trong lần login, so khớp hash legacy rồi `encode(raw)` theo format hiện hành, update storage.
- Với account không thể xác minh raw ở thời điểm migrate, yêu cầu password reset an toàn thay vì cố giải mã.
- Với stored plaintext thật từ legacy, dù về lý thuyết có thể hash toàn bộ trực tiếp trong một job, phải đánh giá kỹ truy cập dữ liệu, hiệu quả bảo mật và quy trình xử lý sự cố vì bản thân plaintext đã có thể bị lộ. Đảm bảo không phát tán trong migration logs/backups.
- Với bcrypt direct format cần gắn prefix `{bcrypt}` khi chuyển sang delegating, **chỉ khi đã xác định dữ liệu thật sự là bcrypt hash**; việc này là thay format nhận diện, không phải rehash.

### 11.5. Không gộp password và các loại secret khác

Refresh token, reset token và API key không nhất thiết dùng cùng password-hashing policy; chúng thường là chuỗi CSPRNG entropy cao, có expiry/revocation/hashed storage khác nhau. Không thay bcrypt bằng SHA-256 thô cho password chỉ vì từng dùng SHA-256 hash reset token. Ngược lại, dùng `NoOpPasswordEncoder` cho API key credential cũng có thể làm lộ secret — phải có thiết kế xác thực và lưu trữ token riêng.

## 12. Khi đọc tài liệu tutorial, phải diễn giải thế nào?

### 12.1. Ba câu thường thấy

**`password("{noop}password")`**: cách làm ngắn để demo xác thực bằng password cố định trong sample. Người học cần hiểu đây là **plaintext trong nguồn và store**, không phải lời khuyên triển khai.

**`NoOpPasswordEncoder.getInstance()`**: API legacy/testing không an toàn; thường xuất hiện trong bài cũ hoặc một đoạn unit test cô lập.

**`User.withDefaultPasswordEncoder().password("password")`**: helper cho getting-started, có thể hash stored value, nhưng raw password vẫn nằm trong mã nguồn, vì vậy không an toàn cho tài khoản thật.

### 12.2. Có phải cứ thêm BCrypt là đã “production ready”?

Không. Hãy tưởng tượng:

```java
User.withUsername("superadmin")
    .password(encoder.encode("password"))
    .roles("ADMIN")
    .build();
```

`BCrypt` bảo vệ bản hash lưu trong memory, nhưng password là `password` ai cũng đoán được, được cố định trong source, có quyền admin và không có chính sách quản lý vòng đời. **Không production-ready.**

### 12.3. Khi nào có thể chấp nhận NoOp trong test?

Trong **unit test kiểm chứng behavior riêng của NoOp**, không chạy trên data thật, không tạo application-wide password encoder bean, không đăng ký route public, và không build artifact chứa account có quyền thật. Với integration test bảo mật, ngay cả môi trường test cũng nên dùng encoder phù hợp để các bug format, salt/`matches`, account disabled và Basic/form login có thể lộ ra. Không tạo habit dùng NoOp cho mọi integration test chỉ để giảm thời gian chạy bcrypt.

### 12.4. Có thể dùng password mẫu trên staging không?

Chỉ nếu staging hoàn toàn tách biệt, không truy cập dữ liệu thật, không public hoặc được bảo vệ thích đáng, có account riêng tạm thời và controls cụ thể. Tuy nhiên, **phương án tốt hơn** là dùng IdP/test account được provision bí mật và kiểm soát vòng đời, không nhập một account công khai từ bài blog. Nhiều sự cố bắt đầu vì tài khoản debug bị quên trong môi trường public.

## 13. Phân biệt lỗi password format và lỗi authentication/authorization

| Triệu chứng | Nguyên nhân khả dĩ | Cách chẩn đoán an toàn |
| --- | --- | --- |
| `There is no PasswordEncoder mapped for the id "null"` | Stored password không có `{id}` khi dùng delegating | Kiểm format bằng metadata/mẫu đã redacted, xác định legacy source |
| `401` với password đúng trong mắt người dùng | Hash format sai, encoder khác, account locked/disabled, user không tồn tại | Test provider `matches` trong môi trường kiểm soát; không log raw |
| `403` sau khi authentication thành công | Thiếu authority, CSRF chặn, rule security khác | Test riêng permission và CSRF |
| Mọi password đều login được | Có thể là custom auth luôn trả success hoặc test dùng mock principal, không nhất thiết do NoOp | Trace authentication provider và test sai password |
| Password từ cấu hình hoạt động nhưng DB lưu rõ plaintext | NoOp hoặc custom password storage sai | Audit cấu hình và stored format, ưu tiên incident response |
| Bcrypt hashes không giống nhau dù raw giống | Salt ngẫu nhiên | Dùng `matches`, không so `encode` lần 1/lần 2 |
| Hash có `{bcrypt}` nhưng custom BCrypt direct trả false | Dùng encoder trực tiếp với prefix delegating | Chọn mapping/format đúng hoặc unwrap có kiểm soát |
| Login test bằng `@WithMockUser` xanh, Basic login thất bại | Mock bypass provider và password | Viết integration test `httpBasic`/form login thật |
| Sau deploy tự có user `user` | Spring Boot default user auto-config chưa bị thay | Kiểm bean nguồn người dùng và generated password log |
| Chạy local được, prod lộ account `lab-admin` | Test profile/fixture bị bật ngoài ý định | CI/CD guard, xóa/quản lý account, kiểm tra binary/config |

### 13.1. Đừng sửa password bằng việc mở `permitAll()`

Nếu authentication lỗi, việc đổi:

```java
.authorizeHttpRequests(auth -> auth
    .anyRequest().permitAll())
```

chỉ làm **bỏ yêu cầu xác thực/phân quyền**, không sửa password encoding. Đây là phản ví dụ nguy hiểm. Hãy tách kiểm tra `PasswordEncoder`, `UserDetailsService`, `AuthenticationManager` và `SecurityFilterChain` để tìm đúng lớp gây lỗi. Không tắt CSRF hoặc filter chỉ để test “xanh”.

### 13.2. Không log/echo credential khi debug

Không ghi request body login, `Authorization: Basic ...`, password hash, Reset token, JSESSIONID hoặc access token vào log, metrics label hay error message. Có thể log correlation ID, outcome, loại cơ chế, class exception đã redacted và user ID chuẩn hóa khi policy cho phép. Tránh đưa secret vào URL hoặc command history.

### 13.3. Rate limit và credential stuffing

Password hash tốt giúp giảm rủi ro khi **offline data dump**. Nó không tự ngăn **online password guessing** hay credential stuffing dùng mật khẩu bị lộ ở dịch vụ khác. Cần giới hạn theo IP/account/device/risk, MFA/step-up và phát hiện hành vi bất thường; tránh lockout đơn giản dễ bị dùng để gây DoS cho tài khoản nạn nhân.

## 14. Test matrix tối thiểu cho password configuration

| Kiểm tra | Input/trạng thái | Kỳ vọng |
| --- | --- | --- |
| NoOp behavior trong isolated unit test | `encode("x")` | Kết quả đúng `"x"`, chứng minh insecure |
| Delegating encode mới | `encode("x")` | Có `{bcrypt}` theo factory hiện tại |
| Delegating matches đúng | Raw đúng + bcrypt hash | true |
| Delegating matches sai | Raw sai + bcrypt hash | false |
| Legacy mapping có giới hạn | Raw đúng + `{noop}x` | true khi mapping vẫn tồn tại |
| Unknown prefix | Raw + password không có ID | Exception/fail closed |
| Direct BCrypt | Hash `$2...` + direct encoder | matches true |
| Wrong format | `{bcrypt}...` + direct BCrypt encoder | Không chấp nhận tự động |
| Lab user store | `student` password hash | Không lưu plaintext |
| GET /me anonymous | Không credential | 401 |
| GET /me đúng | Student đúng password | 200 |
| GET /me sai | Student sai password | 401 |
| GET /admin student | Đúng password, thiếu ADMIN | 403 |
| GET /admin lab-admin | Có ROLE_ADMIN | 200 |
| POST /notes thiếu CSRF | Student đúng credential | 403 |
| POST /notes có CSRF | Student có NOTES_WRITE | 200 |
| POST /notes lab-admin | Thiếu NOTES_WRITE | 403 |
| Non-lab profile | Không có user demo | Account demo không được đăng nhập |
| User source production | Không có password mẫu | Được cung cấp bởi kho/IdP có kiểm soát |
| CI/deployment | Profile lab, noop bean, `{noop}` test credentials | Bị chặn khỏi production image/config |

Các status trên thuộc ứng dụng ví dụ với HTTP Basic, rule cụ thể và CSRF bật. Nếu một dự án dùng form login, anonymous có thể nhận redirect 302; nếu dùng OAuth2/JWT, provider và output khác. Đừng so status mà bỏ qua configuration context.

## 15. Checklist review trước triển khai

### Cấu hình PasswordEncoder

- [ ] Không có `@Bean NoOpPasswordEncoder`/`return NoOpPasswordEncoder.getInstance()` trong production configuration?
- [ ] Không tạo stored password mới bằng `{noop}` hoặc plaintext?
- [ ] Biết encoder bean thực tế là direct bcrypt hay delegating, và stored format phù hợp?
- [ ] Nếu dùng delegating, không đặt fallback NoOp rộng cho unknown ID?
- [ ] Có kế hoạch nâng cấp các hash legacy/`{noop}` còn tồn tại theo thời hạn?
- [ ] Chọn adaptive algorithm và work factor theo guideline/benchmark trên hardware thật?
- [ ] Không dùng MD5/SHA-1/SHA-256 thô, Base64 hoặc reversible encryption làm password storage?

### Secret và tài khoản

- [ ] Không còn user `admin`/`user`/`demo` với password công khai dùng chung ở production?
- [ ] Không dùng `User.withDefaultPasswordEncoder()` với raw password hard-coded trong production?
- [ ] Không bật `spring.security.user.password=...` từ sample config ở deployment?
- [ ] Test users nằm trong `src/test` hoặc profile lab bị CI/CD chặn deploy?
- [ ] Có nguồn user/IdP thật, admin provisioning, lifecycle và kiểm soát revoke?
- [ ] Password hash, secret và Basic header không nằm trong log, tracing hoặc response?
- [ ] Mật khẩu đi qua HTTPS, không dùng Basic trực tiếp trên mạng HTTP?
- [ ] Có password change/reset, MFA/step-up, rate limit và audit phù hợp?

### Kiểm thử và vận hành

- [ ] Unit test `NoOp` chỉ tồn tại trong test code, không làm bean sử dụng thật?
- [ ] Integration test xác minh password qua provider thật, không chỉ `@WithMockUser`?
- [ ] Có test sai password, account bị khóa, sai role, CSRF và URL deny?
- [ ] App không tạo Boot default user ngoài dự kiến?
- [ ] Có test cấu hình production profile không truy cập được bằng credential lab?
- [ ] Có metric/audit cho lần login legacy và tỷ lệ migrate; không log plaintext?
- [ ] Có phương án incident response nếu từng lưu password plaintext (reset/rotation, kiểm tra phạm vi dữ liệu bị ảnh hưởng, thông báo khi pháp luật/chính sách yêu cầu)?
- [ ] Có test rollback/migration và threshold latency khi nâng work factor?

## 16. Tự kiểm tra nhanh

**Câu 1.** `NoOpPasswordEncoder.encode("hello")` tạo giá trị nào?

**Đáp án:** `"hello"`. Không salt, không hash. Mật khẩu vẫn là plaintext.

**Câu 2.** Lưu `{noop}hello` vào DB có phải đã mã hóa password?

**Đáp án:** Không. `{noop}` là ID cho delegating decoder, phần `hello` là plaintext.

**Câu 3.** Có `DelegatingPasswordEncoder` mặc định, gọi `encode("hello")` sẽ tạo `{noop}hello`?

**Đáp án:** Không. Spring Security 6.5 factory mặc định dùng `bcrypt` để encode password mới, thường tạo `{bcrypt}...`. Nó vẫn hỗ trợ match một số legacy ID vì mục tiêu tương thích.

**Câu 4.** Nếu `User.withDefaultPasswordEncoder()` đã hash rồi, vì sao không dùng source hard-coded production?

**Đáp án:** Raw password vẫn tồn tại trong source và compiled code, nên có thể bị đọc hoặc tái sử dụng. Hash ở storage không giải quyết việc secret trong code.

**Câu 5.** Có nên thêm `{noop}` trước mọi password đang thiếu prefix để sửa lỗi ID null?

**Đáp án:** Không. Có thể biến hash legacy thành plaintext dạng chuỗi hash hoặc mở đường cho password vô bảo vệ. Phải kiểm kê định dạng, chọn migration đúng và fail closed khi không nhận diện.

**Câu 6.** `BCryptPasswordEncoder` trực tiếp và `DelegatingPasswordEncoder` có cùng format lưu không?

**Đáp án:** Không hoàn toàn. Direct bcrypt thường tạo hash `$2...`; Delegating mặc định thêm prefix `{bcrypt}` để nhận diện encoder.

**Câu 7.** Chỉ có test `@WithMockUser` thành công thì password encoder đã đúng chưa?

**Đáp án:** Chưa. Mock user bỏ qua password provider. Dùng test `httpBasic`/form login với user store và encoder thật.

**Câu 8.** BCrypt bảo vệ password trong database, vì sao vẫn phải HTTPS?

**Đáp án:** Client gửi raw password tới server; nếu HTTP không TLS, người trên mạng có thể lấy credential trước khi backend hash/matches.

**Câu 9.** NoOpPasswordEncoder giúp chống brute-force online không?

**Đáp án:** Không. Nó chỉ so chuỗi plaintext. Chống brute-force phải có rate limits, policy/monitoring, MFA/step-up và cơ chế bảo mật khác.

**Câu 10.** Nếu application có user mẫu bị deploy nhầm ra Internet, việc đổi NoOp sang BCrypt có đủ để xử lý sự cố không?

**Đáp án:** Không. Credential công khai có thể đã bị dùng. Cần khóa/xóa user mẫu, rotate credentials, kiểm tra audit/truy cập, thu hồi session/token, đánh giá ảnh hưởng và chặn tái diễn qua CI/CD.

## 17. Tóm tắt ghi nhớ

1. **NoOpPasswordEncoder = không bảo vệ password khi lưu.** Nó chỉ thích hợp cho test tách biệt hoặc legacy có kế hoạch migrate, không phải một `PasswordEncoder` production.
2. **`{noop}` là tag định dạng tương thích, không phải hash**. Password phía sau vẫn là plaintext.
3. **DelegatingPasswordEncoder mặc định encode mới bằng bcrypt** và dùng prefix `{bcrypt}`; khả năng đọc legacy không đồng nghĩa nên tiếp tục ghi legacy.
4. **withDefaultPasswordEncoder() có thể hash nhưng raw password hard-coded vẫn lộ trong source**. Tài khoản/password mẫu không được đưa vào môi trường thật.
5. **Chọn adaptive password hash, TLS và nguồn danh tính phù hợp**. BCrypt/Argon2id/scrypt/PBKDF2, cost tuning, monitoring, rate limiting, lifecycle và secret management bổ sung cho nhau.
6. **Test chính xác authentication path**: dùng password thật qua provider/filter, không kết luận từ mock principal. Có cả test sai mật khẩu và quyền.
7. **Migration cần kiểm kê format và fail closed**, không “sửa tắt” bằng NoOp fallback hoặc thêm `{noop}` tùy ý.
8. **Profile lab/test chỉ là biện pháp giảm rủi ro cho bài học**; production phải có account provisioning thực, CI/CD guard và không có public test credentials.

## Tài liệu chính thức và hướng dẫn an toàn

- [Spring Security 6.5 — Password Storage, DelegatingPasswordEncoder, format {id}, NoOp và withDefaultPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — NoOpPasswordEncoder Javadoc (deprecated/insecure)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/NoOpPasswordEncoder.html)
- [Spring Security 6.5 — PasswordEncoder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security 6.5 — BCryptPasswordEncoder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html)
- [Spring Security 6.5 — MockMvc HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security 6.5 — MockMvc CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Boot 3.5 — Spring Security Auto-Configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Boot 3.5.16 release (25/06/2026) và kết thúc OSS support của 3.5.x](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
- [OWASP Password Storage Cheat Sheet — adaptive hashes, salt/pepper và work factor](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP Authentication Cheat Sheet — bảo vệ online login và account lifecycle](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
