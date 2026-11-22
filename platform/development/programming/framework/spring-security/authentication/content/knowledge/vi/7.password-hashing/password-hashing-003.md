# Salt, hệ số chi phí và khả năng chống dò mật khẩu

## Mục tiêu

Mật khẩu là một bí mật do người dùng biết. Khi lưu trong hệ thống, **không lưu mật khẩu rõ**, không mã hóa hai chiều để có thể giải mã lại, và không chỉ dùng hàm băm nhanh như SHA-256 một lần. Cách lưu thông dụng là dùng **password-hashing function chuyên dụng**, tạo *salt* ngẫu nhiên riêng cho từng lần băm và đặt *hệ số chi phí* (work factor) để một lần đoán mật khẩu tốn tài nguyên.

Bài thuộc nhóm **Băm mật khẩu**, module *Spring Security - authentication*, tập trung vào ba vấn đề:

1. **Salt** làm cho hai mật khẩu giống nhau có thể tạo hai bản ghi hash khác nhau và phá tính kinh tế của bảng tra cứu tính sẵn (rainbow table).
2. **Work factor** làm chậm mỗi phép thử mật khẩu, nhất là khi attacker đã lấy được database hash và có thể đoán *offline*.
3. **Chống dò mật khẩu** là phòng thủ nhiều lớp: hàm băm chậm chỉ giúp bảo vệ dữ liệu lưu trữ; để chống thử đăng nhập *online* còn cần rate limiting, MFA, thông điệp lỗi an toàn và giám sát.

Ví dụ dùng Java 17+, Spring Boot 3.x / Spring Security 6.x. Các mức cost trong bài là **số để minh họa**, không phải cấu hình production mặc định cho mọi máy. Khi triển khai cần benchmark trên phần cứng, lưu lượng và phiên bản thư viện thực tế.

## 1. Mô hình đe dọa: tại sao băm mật khẩu lại quan trọng?

Có hai loại tấn công rất khác nhau.

### 1.1. Dò mật khẩu trực tuyến (*online guessing*)

Attacker gửi nhiều request login đến server:

~~~text
Attacker -> POST /login (username, thử password #1)
         -> POST /login (username, thử password #2)
         -> ...
         -> server tự kiểm tra từng lần
~~~

Server có thể kiểm soát số request: giới hạn tốc độ, giới hạn theo account/IP/tín hiệu rủi ro, thử thách tăng dần, MFA, phát hiện bất thường và phản hồi lỗi thống nhất. Work factor ảnh hưởng CPU của **cả server và attacker** nhưng **không tự chặn** việc gửi nhiều request. Cost quá cao còn có thể giúp attacker làm cạn CPU bằng nhiều lần login liên tiếp.

### 1.2. Dò mật khẩu ngoại tuyến (*offline cracking*)

Một sự cố SQL injection, lộ backup hoặc phân quyền DB sai làm attacker lấy được bảng chứa password hash:

~~~text
users table bị lộ
username      password_hash
alice         $2a$12$...
bob           $2a$12$...
...
          |
          v
Attacker có thể thử password trên máy của họ
mà không cần gửi request tới server của chúng ta
~~~

Rate limiting của login API **không thể giới hạn** tốc độ thử hash trên máy attacker. Mỗi ứng viên mật khẩu được kiểm tra với dữ liệu hash bị đánh cắp. Đó là lúc **salt độc lập** và **hashing có chi phí cao** tạo khác biệt.

Không có hệ thống băm nào làm mật khẩu yếu trở nên “không thể đoán”. Ví dụ password `123456` vẫn nằm trong từ điển phổ biến. Hash tốt **làm tăng chi phí tấn công**, không thay thế mật khẩu đủ mạnh, chống password reuse, phát hiện mật khẩu lộ và MFA.

## 2. Phân biệt hashing, encryption, salt, pepper và work factor

| Khái niệm | Mục đích | Có bí mật không? | Ví dụ |
| --- | --- | --- | --- |
| **Password hashing** | Biến mật khẩu thành giá trị kiểm chứng một chiều | Hash lưu trong DB cần bảo vệ, nhưng thuật toán không cần bí mật | bcrypt, Argon2id, scrypt, PBKDF2 |
| **Encryption** | Biến dữ liệu bằng key có thể giải mã | Key phải giữ bí mật | AES dùng cho dữ liệu cần khôi phục, không phải giải pháp chính để lưu password |
| **Salt** | Làm hash của từng mật khẩu độc lập, chống tra cứu tính sẵn và liên kết hash trùng nhau | **Không**; thường lưu cùng hash | Salt ngẫu nhiên riêng cho mỗi lần `encode` |
| **Work factor/cost** | Làm phép tạo/kiểm tra hash tốn thời gian, CPU hoặc RAM có chủ đích | **Không**; thường được ghi trong chuỗi hash | bcrypt cost `12`; Argon2id có memory/time/parallelism |
| **Pepper** | Bí mật bổ sung ngoài database, hỗ trợ phòng thủ nhiều lớp | **Có**; phải lưu tách khỏi DB | Key trong secret manager/HSM dùng trong thiết kế HMAC có kiểm soát |

**Hash không phải encryption.** Không có thao tác “decrypt password hash” để lấy lại mật khẩu ban đầu. Khi người dùng quên mật khẩu, thiết kế flow reset qua bằng chứng sở hữu hợp lệ; không tìm cách giải mã hash.

**Salt không phải pepper.** Salt có thể nằm công khai trong chuỗi hash. Pepper là secret chung hoặc secret thuộc một phạm vi triển khai; nếu dùng, phải có quản trị secret, rotation, recovery và thiết kế mật mã chuẩn. Không đặt pepper vào cùng bảng password hash rồi nghĩ rằng đã có lớp bí mật bổ sung.

## 3. Salt ngẫu nhiên hoạt động như thế nào?

Giả sử Alice và Bob chọn cùng một password. Nếu áp dụng hàm băm **không salt**:

~~~text
H(password) = digest
H(password) = cùng digest
~~~

Hai record có thể chứa cùng hash. Attacker có thể nhận ra password của các account giống nhau, và dùng một kết quả tính sẵn để kiểm tra hàng loạt hash.

Với salt riêng:

~~~text
Alice:
  password = P
  salt = random_A
  stored = PasswordHash(P, random_A, cost)

Bob:
  password = P
  salt = random_B
  stored = PasswordHash(P, random_B, cost)

random_A != random_B
=> hai stored hash khác nhau với xác suất áp đảo
~~~

Thực tế một thư viện password hashing thường tự tạo salt bằng bộ sinh số ngẫu nhiên mật mã, rồi mã hóa salt, cost và kết quả vào chuỗi lưu trữ. Bạn **không cần tự sinh salt thủ công** nếu dùng đúng `BCryptPasswordEncoder` hoặc implementation tương đương.

### 3.1. Salt giải quyết vấn đề nào?

- **Chống rainbow table:** một bảng hash tính sẵn không còn dùng lại hiệu quả cho tất cả password vì mỗi record có salt khác nhau.
- **Giảm nhận diện password trùng:** hai user có cùng password thường nhận hash khác nhau, nên không thể chỉ nhìn chuỗi hash để phát hiện.
- **Tăng chi phí trên nhiều account:** attacker cần thực hiện công việc cho từng salt/hash thay vì chia sẻ hoàn toàn kết quả giữa các account.

### 3.2. Salt không giải quyết vấn đề nào?

- Salt **không bắt password yếu trở thành mạnh**. Attacker có hash + salt vẫn có thể thử các mật khẩu phổ biến trên từng record.
- Salt **không phải key bí mật**, không cần giấu salt khỏi attacker mới có bảo vệ.
- Salt **không thay thế work factor**. `SHA-256(salt || password)` vẫn là hàm quá nhanh cho kho mật khẩu.
- Salt **không tự ngăn online guessing** qua `/login`.
- Salt tự sinh có chất lượng ngẫu nhiên kém, cố định toàn hệ thống hoặc tái sử dụng cho nhiều user có thể làm yếu thiết kế.

Đừng chọn salt bằng username, email hoặc một hằng số trong source code: các giá trị đó có thể đoán và thường không bảo đảm ngẫu nhiên/duy nhất. Đừng viết thêm một hàm `SecureRandom` rồi ghép chuỗi bên ngoài nếu encoder chuẩn đã quản lý salt bên trong; việc tự ghép sai có thể làm hỏng compatibility với `matches`.

### 3.3. Khi reset hoặc đổi password

Một lần `encode(newPassword)` tạo salt mới và giá trị hash mới. Không “sửa salt cũ” rồi mong xác thực như trước. Nếu hệ thống lưu hash theo chuỗi format chuẩn, hãy lưu **toàn bộ chuỗi encoded password** để sau này `matches(raw, storedHash)` đọc đúng tham số.

Không cần thêm một cột salt riêng cho bcrypt chỉ để chạy Spring Security chuẩn; chuỗi bcrypt đã chứa thông tin salt và cost. Có schema legacy tách cột vì yêu cầu riêng, nhưng khi chuyển đổi phải có quy trình migration được test.

## 4. Work factor: cố ý làm phép thử tốn tài nguyên

Một phép SHA-256 có thể chạy cực nhanh trên hardware chuyên dụng; đó là ưu điểm trong nhiều ứng dụng khác nhưng **bất lợi** khi bảo vệ password. Password hashing chuyên dụng sử dụng chức năng **adaptive one-way**: nhà vận hành chọn mức công việc cần làm cho mỗi lần hash/match.

### 4.1. Bcrypt cost là gì?

Trong `BCryptPasswordEncoder`, `strength` là *log rounds* (cost) của bcrypt. Công việc nội bộ tăng theo lũy thừa xấp xỉ `2^cost`; vì vậy, tăng cost thêm 1 thường gần **gấp đôi** phần công việc liên quan, không phải thêm một đơn vị thời gian cố định.

Ví dụ so sánh tính chất *tương đối*, không phải benchmark:

| Bcrypt cost | Mức công việc tương đối so với cost 10 | Nhận xét |
| --- | --- | --- |
| `10` | 1× | Giá trị mặc định của `BCryptPasswordEncoder` ở Spring Security 6.x |
| `11` | Khoảng 2× | Tăng lượng tính toán |
| `12` | Khoảng 4× | Chạy ví dụ để quan sát nâng cost |
| `13` | Khoảng 8× | Phải đánh giá tải CPU |
| `14` | Khoảng 16× | Không tự chọn trên cơ sở “càng lớn càng tốt” |

Các tỉ lệ trên mô tả cấu trúc công việc bcrypt, **không hứa** latency trên máy/CPU thật tăng chính xác từng hệ số. Runtime còn phụ thuộc thread scheduling, JVM warm-up, CPU model, mật độ request và mức cạnh tranh tài nguyên.

`BCryptPasswordEncoder` hỗ trợ cost từ 4 đến 31, mặc định 10. **Không chọn cost 4 cho production chỉ vì chạy nhanh**; cũng không đặt 20–31 tùy tiện vì rủi ro denial of service. Nên đo trên hạ tầng thật và theo hướng dẫn bảo mật áp dụng hiện tại.

### 4.2. Đặt cost bao nhiêu mới đúng?

Tài liệu Spring Security 6.5 khuyến nghị hiệu chỉnh adaptive password hash ở mức **xấp xỉ một giây cho việc xác minh trên hệ thống của bạn**, đồng thời cân bằng tải và UX. OWASP nhấn mạnh work factor đủ cao để tăng chi phí tấn công nhưng không gây quá tải, và việc tối ưu phải dựa trên thử nghiệm. Hai hướng dẫn là **định hướng hiệu năng/rủi ro**, không thay cho đo lường tại ứng dụng thực tế.

Cần đánh giá ít nhất:

1. CPU và RAM trên máy production hoặc cấu hình tương đương.
2. Thời gian p50/p95/p99 của `matches(...)` qua warm-up, không lấy một lần đo.
3. Số login/giây bình thường và lúc tăng đột biến; số request xác thực đồng thời.
4. Khả năng gây tải nhân tạo bằng request sai password/username.
5. Thời gian tổng của lookup DB, hash verification, MFA và overhead mạng.
6. Mức cost đang lưu trong hash cũ, kế hoạch nâng cấp theo phiên bản.
7. Giới hạn tài nguyên CPU/RAM container và cấu hình autoscaling/rate limit.

Một cost hợp lý cho workload này có thể quá nặng hoặc quá nhẹ trên workload khác. Lập lịch benchmark lại khi đổi instance type, phần cứng, phiên bản JDK/Spring Security hoặc nhu cầu bảo mật.

### 4.3. Tăng cost có nhược điểm gì?

- Server phải làm nhiều việc hơn mỗi lần login hợp lệ.
- Thử password sai cũng có thể tiêu tốn CPU; cần giới hạn lưu lượng và bảo vệ chống DoS.
- Có thể kéo dài login latency, timeout, queue và gây ảnh hưởng service khác.
- Migration từng hash cần kế hoạch; chỉ đổi bean encoder không biến mọi hash cũ thành hash mới.
- Với thuật toán dùng nhiều RAM như Argon2id, phải kiểm tra memory pressure của những login đồng thời.

**Đừng dùng một password hash chậm để chứng thực lại password trên mọi request API.** Spring Security gợi ý sau khi xác thực password thì chuyển sang credential ngắn hạn như session hoặc access token phù hợp; validation của token/ngữ cảnh thường nhẹ hơn. Vẫn cần bảo vệ token và chính sách hết hạn/thu hồi riêng.

## 5. Đọc format bcrypt để biết salt và cost nằm ở đâu

Một chuỗi bcrypt tiêu biểu có dạng:

~~~text
$2a$12$...............................
^^^^^^^
 $2a$  : biến thể bcrypt
    12 : cost (minh họa)
~~~

Dạng đầy đủ thường dài **60 ký tự ASCII**, ví dụ cấu trúc:

~~~text
$2a$12$[22 ký tự biểu diễn salt][31 ký tự biểu diễn kết quả]
~~~

Các dấu ngoặc vuông ở dòng trên chỉ là **ký hiệu giải thích**, không phải chuỗi hash hợp lệ. Một hash thật dùng bộ ký tự mã hóa bcrypt và không chứa dấu ngoặc. Version có thể là `$2a$`, `$2b$` hoặc `$2y$` theo implementation/thiết lập.

Thông tin cần lưu giữ là **toàn bộ chuỗi bcrypt** (version, cost, salt, hash) trong database. Không cắt bỏ prefix `$2a$12$`, không chỉ lưu 31 ký tự cuối, và không lưu riêng cost rồi quên tương thích khi verify.

Bcrypt sử dụng salt ngẫu nhiên **16 byte**; nó được biểu diễn thành **22 ký tự** trong chuỗi encoded. Các giá trị biểu diễn ở hash không phải dữ liệu bí mật phải mã hóa thêm chỉ để che thuật toán. Thuật toán công khai; sự an toàn dựa trên tính chất hàm, entropy của password và chi phí tấn công, không dựa vào giấu cost.

### 5.1. Hash tự sinh có ngẫu nhiên, vậy matches so sánh bằng cách nào?

Giả sử:

~~~java
BCryptPasswordEncoder encoder = new BCryptPasswordEncoder(12);
String first = encoder.encode("demo-only");
String second = encoder.encode("demo-only");
~~~

`first` và `second` thường khác nhau vì dùng salt mới. Nhưng:

~~~java
encoder.matches("demo-only", first);  // true
encoder.matches("demo-only", second); // true
~~~

`matches` **đọc thông số/salt từ hash đã lưu**, thực hiện phép thử tương thích và kiểm tra kết quả. Nó **không** gọi `encode(rawPassword)` với salt ngẫu nhiên mới rồi so sánh chuỗi.

Sai:

~~~java
// SAI: encode tạo salt mới, nên không so sánh chuỗi như thế này.
boolean valid = encoder.encode(inputPassword).equals(storedHash);
~~~

Đúng:

~~~java
boolean valid = encoder.matches(inputPassword, storedHash);
~~~

Không dùng `hashCode()` của Java, MD5 hoặc `MessageDigest.getInstance("SHA-256")` một vòng cho mật khẩu production. Chúng không cung cấp work factor thích hợp cho password storage.

## 6. Chương trình Java 17+ chạy được: hai salt và tăng cost

Ví dụ sau là một ứng dụng **CLI dùng Spring Boot**, không có HTTP endpoint và không cần database. Nó chứng minh:

- Hai lần `encode` cùng mật khẩu trả hash khác nhau.
- `matches` vẫn nhận đúng mật khẩu và từ chối mật khẩu sai.
- Hash cost 10 vẫn được encoder cấu hình cost 12 kiểm tra.
- `upgradeEncoding` xác định hash cũ có cost thấp hơn cost mong muốn.
- Không có output “hash cố định”: salt được tạo ngẫu nhiên.

### 6.1. Chuẩn bị project

Tạo project từ Spring Initializr:

- Java **17** hoặc **21**, Spring Boot **3.x**, **Maven**.
- Group `com.example`, artifact `password-cost`, package `com.example.demo`.
- Dependency **Spring Security** (`spring-boot-starter-security`). Không chọn Spring Web: ta chỉ chạy lệnh dòng lệnh.
- Spring Initializr tạo `pom.xml` và Maven Wrapper.

Tạo **`src/main/java/com/example/demo/PasswordCostApplication.java`**:

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

@SpringBootApplication
public class PasswordCostApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordCostApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate() {
        return args -> {
            String raw = "Demo-only-password-2026!";

            BCryptPasswordEncoder cost10 =
                new BCryptPasswordEncoder(10);
            BCryptPasswordEncoder cost12 =
                new BCryptPasswordEncoder(12);

            String hashA = cost10.encode(raw);
            String hashB = cost10.encode(raw);
            String hashC = cost12.encode(raw);

            System.out.println("differentSalts="
                + !hashA.equals(hashB));
            System.out.println("correctPassword="
                + cost10.matches(raw, hashA));
            System.out.println("wrongPassword="
                + cost10.matches("wrong-password", hashA));
            System.out.println("oldHashStillMatches="
                + cost12.matches(raw, hashA));
            System.out.println("oldHashNeedsUpgrade="
                + cost12.upgradeEncoding(hashA));
            System.out.println("newHashNeedsUpgrade="
                + cost12.upgradeEncoding(hashC));
        };
    }
}
~~~

### 6.2. Chạy và dự đoán output

Từ thư mục Maven project:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell: `.\mvnw.cmd spring-boot:run`. Ngoài log Spring Boot, đoạn `CommandLineRunner` in:

~~~text
differentSalts=true
correctPassword=true
wrongPassword=false
oldHashStillMatches=true
oldHashNeedsUpgrade=true
newHashNeedsUpgrade=false
~~~

Giải thích:

- `differentSalts=true`: hai hash tạo độc lập với salt ngẫu nhiên nên khác nhau trong thực tế (xác suất salt trùng cực kỳ nhỏ). Không dùng test này để “chứng minh tuyệt đối” không bao giờ có trùng ngẫu nhiên.
- `correctPassword=true`: cùng password khớp hash A.
- `wrongPassword=false`: sai password không khớp.
- `oldHashStillMatches=true`: `BCryptPasswordEncoder(12)` vẫn kiểm tra được hash có cost 10 vì cost cũ được lưu trong hash.
- `oldHashNeedsUpgrade=true`: encoder cost 12 nhận ra hash cost 10 nên cân nhắc rehash.
- `newHashNeedsUpgrade=false`: hash vừa tạo với cost 12 đã đạt cost cấu hình.

**Đây là output ổn định về boolean** trên phiên bản API được mô tả. Nếu bạn bổ sung việc in `hashA`, `hashB` hay thời gian chạy, các giá trị đó **không cố định** giữa hai lần khởi động.

Demo nhúng một password giả trong mã nguồn chỉ để học. Trong production, không hardcode password, không log giá trị raw, không trả hash trong API và không dùng hash demo làm credential thật.

### 6.3. Đo thời gian mà không tự đưa ra số giả

Một đoạn **mã minh họa trong cùng method** sau khi có `encoder`, `storedHash` và `raw`:

~~~java
long start = System.nanoTime();
boolean ok = encoder.matches(raw, storedHash);
long elapsedNs = System.nanoTime() - start;

if (!ok) {
    throw new IllegalStateException("Expected valid test password");
}
System.out.println("verifyMillis=" + elapsedNs / 1_000_000.0);
~~~

Đoạn này **không tự chạy độc lập** và kết quả thời gian là số **phụ thuộc môi trường**. Với microbenchmark thực sự, cần warm-up JVM, nhiều phép đo, công cụ như JMH khi phù hợp, kiểm soát CPU contention và đánh giá p95/p99 ở nhiều mức concurrency. Không kết luận “cost 12 luôn 250 ms” từ một phép đo trên laptop.

## 7. Spring Security dùng encoder để xác thực như thế nào?

Trong Servlet username/password, luồng điển hình:

~~~text
POST /login hoặc Authorization: Basic ...
    |
    v
Authentication filter
    |
    v
AuthenticationManager -> DaoAuthenticationProvider
    |
    +-- UserDetailsService.loadUserByUsername(username)
    |       -> UserDetails.getPassword(): storedHash
    |
    +-- PasswordEncoder.matches(rawPassword, storedHash)
    |       -> đúng: xét tiếp account flags và policy
    |       -> sai: authentication failure
    |
    v
Authentication thành công / exception
    |
    v
SecurityContext + authorization
~~~

**UserDetailsService không tự so sánh password.** Nó trả record (thường có hash) theo username. `DaoAuthenticationProvider` dùng `PasswordEncoder` để kiểm tra bằng chứng. Sau đó, các bước account status, authorities và SecurityContext vẫn là những trách nhiệm riêng.

Cấu hình bean encoder cơ bản:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder(12);
}
~~~

Đây là **mã cấu hình trong một Spring `@Configuration` class**, cần import `Bean`, `PasswordEncoder` và `BCryptPasswordEncoder`. Cost 12 là mức minh họa; production phải benchmark. Password khi **tạo/đổi** account:

~~~java
String storedHash = passwordEncoder.encode(rawPassword);
accountRepository.savePasswordHash(userId, storedHash);
~~~

Đoạn này **không runnable độc lập** vì `accountRepository` và `userId` thuộc domain application. Trong thực tế phải có transaction, kiểm soát quyền đổi mật khẩu, audit và policy mật khẩu phù hợp. Khi login, provider dùng `matches`; không băm lần hai bằng salt mới rồi so sánh chuỗi.

### 7.1. Stored hash không có cùng format với DelegatingPasswordEncoder

Với **`BCryptPasswordEncoder` thuần**, hash có dạng:

~~~text
$2a$12$...
~~~

Với **`DelegatingPasswordEncoder`**, chuỗi thường có prefix ID của encoder:

~~~text
{bcrypt}$2a$12$...
~~~

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo encoder có thể nhận diện format `{id}encodedPassword`. `id` dùng để chọn thuật toán; `bcrypt` là một lựa chọn, các ID khác có thể hỗ trợ migration.

Không tự bỏ `{bcrypt}` rồi lưu một nửa chuỗi, cũng không đưa một chuỗi bcrypt thuần vào `DelegatingPasswordEncoder` mặc định mà chắc chắn nó sẽ đoán được thuật toán. Theo tài liệu, ID không có/không được mapping có thể gây `IllegalArgumentException` nếu không cấu hình fallback. Không dùng `{noop}` hay fallback chấp nhận plaintext trong production để “chữa” lỗi hash cũ.

Một cấu hình `PasswordEncoder` cụ thể phải được dùng **nhất quán** tại tạo account, đổi password và login; thay bằng encoder khác mà không có lộ trình migration có thể khiến mọi user không đăng nhập được.

## 8. Nâng work factor mà không buộc tất cả người dùng đổi mật khẩu ngay

Cơ chế tương thích bcrypt cho phép đọc work factor từ hash cũ, nên encoder cấu hình cost 12 vẫn có thể xác minh hash cost 10. Tuy nhiên:

**Đổi `new BCryptPasswordEncoder(10)` thành `new BCryptPasswordEncoder(12)` không tự ghi lại mọi hash trong database.** Hash cũ chỉ được nâng khi có raw password hợp lệ tại một thời điểm hợp pháp hoặc người dùng đổi/reset mật khẩu. Không thể “rehash” chỉ từ hash cũ để nâng cost đúng cách.

### 8.1. Quy trình nâng có kiểm soát

1. Chọn cost/thuật toán mục tiêu sau khi benchmark.
2. Giữ khả năng `matches` với các hash cũ trong thời gian chuyển tiếp.
3. Khi người dùng đăng nhập thành công bằng password đúng, kiểm tra `passwordEncoder.upgradeEncoding(storedHash)`.
4. Nếu cần nâng, dùng **raw password chỉ có sẵn trong authentication flow đang xử lý** để `encode` lại với salt mới/cost mới.
5. Ghi hash mới qua tầng quản lý credentials an toàn; dùng optimistic locking/compare-and-set để tránh ghi đè một thay đổi password xảy ra đồng thời.
6. Xóa/không lưu lâu raw password, kiểm soát transaction, audit metadata thích hợp; không log raw/encoded hash.
7. User không đăng nhập lại vẫn có hash cũ: cần kế hoạch password reset hoặc tuổi thọ hash theo chính sách.

### 8.2. Hooks trong Spring Security

`PasswordEncoder` có phương thức `upgradeEncoding(String encodedPassword)`. Trong các flow dùng `DaoAuthenticationProvider`, có thể đăng ký `UserDetailsPasswordService` để lưu hash đã nâng sau xác thực thích hợp:

~~~java
// Cấu hình minh họa, không phải file Java độc lập.
// users: UserDetailsService
// encoder: PasswordEncoder
// updates: UserDetailsPasswordService thực thi bởi ứng dụng
DaoAuthenticationProvider provider =
    new DaoAuthenticationProvider(users);

provider.setPasswordEncoder(encoder);
provider.setUserDetailsPasswordService(updates);
~~~

`UserDetailsPasswordService.updatePassword(UserDetails user, String newPassword)` nhận **mật khẩu đã được encode**, lưu vào account tương ứng theo identity đáng tin và trả `UserDetails` cập nhật. Phải triển khai service này cho repository/domain thực tế; chỉ gọi `setUserDetailsPasswordService(...)` mà không có persistence đúng sẽ không tự sửa database.

Với `DelegatingPasswordEncoder`, hãy kiểm tra `upgradeEncoding(...)` còn gợi ý đổi **thuật toán ID** hay thay **tham số** trong ID hiện tại hay không. Không xóa tiền tố `{id}` một cách ngẫu hứng; prefix là một phần format.

### 8.3. Migrate hash cũ không có prefix

Một số database cũ chứa SHA-1, PBKDF2 đời cũ hoặc bcrypt thuần. Không đổi hết record thành `{bcrypt}` nếu chúng thực chất không phải bcrypt. Cần kế hoạch phân loại format dựa trên dữ liệu được kiểm chứng, mapping bộ encoder tương thích và migration sau login/reset.

Cẩn thận với các format cũ **không đủ bảo mật**, như plaintext, MD5, SHA-1 trực tiếp hoặc SHA-256 một vòng. Nếu bắt buộc tương thích trong giai đoạn ngắn, cần giới hạn phạm vi, ưu tiên reset/nâng cấp và xác định thời hạn xóa hỗ trợ yếu. Không thiết lập `NoOpPasswordEncoder` làm fallback mặc định.

## 9. Thuật toán nào phù hợp: bcrypt, Argon2id, scrypt, PBKDF2?

| Thuật toán | Cơ chế chi phí | Ưu điểm | Điều cần xem xét |
| --- | --- | --- | --- |
| **Argon2id** | RAM + số lượt + song song | Memory-hard, hạn chế lợi thế phần cứng song song trong nhiều kịch bản | Tài nguyên RAM, thư viện và benchmark concurrency |
| **scrypt** | Bộ nhớ và CPU theo `N/r/p` | Memory-hard; lựa chọn khi Argon2id không phù hợp | Tốn RAM, cần benchmark khi nhiều login đồng thời |
| **bcrypt** | Cost log rounds, chủ yếu CPU | Phổ biến, có sẵn trong Spring Security, tự quản lý salt | Giới hạn 72 byte đầu vào, throughput CPU |
| **PBKDF2** | Số lượt lặp/HMAC | Tích hợp tiêu chuẩn; phù hợp một số yêu cầu tuân thủ/FIPS | CPU-hard, cần tham số và implementation đúng |

OWASP hiện ưu tiên **Argon2id** cho hệ thống mới khi môi trường cho phép và tiếp tục hướng dẫn bcrypt cho nhiều hệ thống legacy. Spring Security 6.5 hỗ trợ bcrypt, Argon2, scrypt và PBKDF2 trong `PasswordEncoder`; với `Argon2PasswordEncoder`, tài liệu Spring chỉ ra việc cần dependency Bouncy Castle. **Đừng coi các con số cost giữa thuật toán là tương đương**: bcrypt `12` không so được trực tiếp với PBKDF2 600.000 iterations hay Argon2id memory 19 MiB.

Khi chọn thuật toán, đánh giá library/framework đang được duy trì, khả năng nâng cấp format, giới hạn tài nguyên, yêu cầu tuân thủ, kiểm thử an ninh và nền tảng triển khai. Không tự phát minh tổ hợp nhiều hàm hash (ví dụ vòng ngoài SHA-256 trước bcrypt) khi không có thiết kế/đánh giá chuyên môn.

### 9.1. Giới hạn 72 byte của bcrypt

Nhiều implementation bcrypt có giới hạn **72 byte dữ liệu đầu vào**, chứ **không phải 72 ký tự Unicode**. Với UTF-8, một ký tự tiếng Việt hoặc emoji có thể chiếm nhiều byte. Nếu vượt ngưỡng mà thư viện cắt bớt, hai password khác nhau ở phần hậu tố có thể bị kiểm tra như nhau.

Nếu dùng bcrypt, ứng dụng phải có chính sách xử lý **độ dài theo byte** tương thích implementation, không cắt password âm thầm, không làm khác nhau giữa màn hình đăng ký và đăng nhập. Cũng không nên cấm mật khẩu dài mạnh một cách vô căn cứ: nếu cần hỗ trợ passphrase dài hơn giới hạn bcrypt, hãy cân nhắc thuật toán hiện đại không bị giới hạn tương tự hoặc một thiết kế được kiểm định rõ ràng.

Không tự băm trước bằng SHA-256 rồi đưa vào bcrypt để “né” giới hạn nếu chưa đánh giá vấn đề password shucking, null byte, input encoding và migration; OWASP có cảnh báo cụ thể về các kỹ thuật pre-hashing thiếu kiểm soát.

### 9.2. Unicode và chuẩn hóa password

Phân biệt username normalization với **password policy**. Password là bí mật: không tự `trim()`, đổi lowercase, bỏ dấu tiếng Việt hoặc chuẩn hóa Unicode tùy tiện ở một đầu mà không thực hiện nhất quán và có lý do. Một dấu cách ở đầu/cuối có thể là phần mật khẩu thật.

Nếu quyết định Unicode normalization (ví dụ NFC) cho password, phải định nghĩa thống nhất ở registration, login, change/reset password, và bảo đảm người dùng không bị lockout khi thay phiên bản. Tuyệt đối không “tiền xử lý thử nhiều biến thể” nhằm đoán password đúng, vì đó là thay đổi authentication semantics và tăng bề mặt tấn công.

## 10. Pepper: bổ sung nhưng không thay thế salt/cost

Pepper là một bí mật do server quản lý, không lưu cùng bảng hash. Nó có thể bổ sung bảo vệ khi attacker lấy được **chỉ database** mà chưa lấy được secret infrastructure. Ví dụ một thiết kế HMAC với key nằm trong vault/HSM có thể tăng chi phí tấn công khi dữ liệu DB bị lộ.

Không dùng pepper như một “salt chung” được hardcode trong mã nguồn hoặc `application.properties` rồi commit lên repository. Cần có quyền truy cập tối thiểu, audit, rotation và quy trình khôi phục. Nếu pepper bị lộ, có thể phải yêu cầu đổi/reset mật khẩu tùy kiến trúc, vì không thể đơn giản “đổi pepper” cho hash cũ nếu thiếu raw password.

**Pepper không sửa được mọi vấn đề:**

- Password yếu vẫn cần chính sách và kiểm tra mật khẩu lộ.
- Work factor quá thấp vẫn làm mỗi lần đoán tương đối rẻ nếu pepper cũng bị lộ.
- Online password spraying vẫn cần rate limit và MFA.
- Nếu server và vault bị xâm nhập cùng lúc, attacker có thể lấy cả hash và pepper.

Đối với đa số ứng dụng, triển khai đúng adaptive password hash với random salt và cost phù hợp **quan trọng hơn** việc tự sáng tạo cách ghép pepper vào chuỗi mật khẩu. Nếu cần pepper, chọn một mô hình mật mã có tài liệu, kiểm toán và kế hoạch rotation.

## 11. Chống dò online: các biện pháp nằm ngoài PasswordEncoder

Dù dùng Argon2id hoặc bcrypt cost rất cao, API đăng nhập vẫn có thể bị thử hàng loạt nếu không có lớp kiểm soát:

1. **Rate limiting nhiều chiều:** theo account định danh, địa chỉ kết nối đã qua ranh giới proxy đáng tin cậy, thiết bị/rủi ro và hệ thống. Tránh chỉ dựa vào IP vì NAT/proxy, hoặc chỉ dựa vào username vì attacker có thể phân tán.
2. **Chống password spraying:** phát hiện một mật khẩu bị thử với nhiều tài khoản, không chỉ nhiều password ở một account.
3. **MFA/passkeys:** thêm yếu tố khó đánh cắp khi password bị lộ, ưu tiên cơ chế phishing-resistant khi khả thi.
4. **Mật khẩu đã bị lộ:** sàng lọc với nguồn compromised-password đáng tin, theo thiết kế không tiết lộ mật khẩu thô.
5. **Thông điệp lỗi chung:** đừng cho người chưa xác thực phân biệt account không tồn tại, disabled, password sai qua nội dung response/timing dễ quan sát.
6. **Bảo vệ tài nguyên:** concurrency limit, backpressure, timeout, circuit breaker của lookup, giám sát CPU và latency khi bcrypt/Argon2 tải cao.
7. **TLS và secret hygiene:** login qua HTTPS, không log password, Authorization header, cookie, hash, pepper; bảo vệ DB backup và phân quyền tối thiểu.
8. **Audit và cảnh báo:** ghi metadata tối thiểu về sự kiện thất bại/thành công với quyền truy cập và thời hạn lưu phù hợp.

Lock account sau quá ít lần sai có thể bị attacker lợi dụng để gây **denial of service cho người dùng hợp pháp**. Thiết kế adaptive throttling và recovery phù hợp, không biến một username public thành công tắc khóa account vô thời hạn.

## 12. Lỗi thường gặp và hướng sửa

| Lỗi | Tại sao sai | Cách khắc phục |
| --- | --- | --- |
| Lưu password rõ | DB/backup lộ là lộ credential ngay | Dùng adaptive password hashing |
| Dùng `SHA-256(password)` một lần | Quá nhanh để chống offline guessing | Dùng Argon2id/bcrypt/scrypt/PBKDF2 đúng cấu hình |
| Dùng chung salt cố định | Hash giữa account dễ bị liên hệ; tái sử dụng kết quả tính trước | Salt ngẫu nhiên riêng mỗi lần encode, để thư viện quản lý |
| Hash trùng nhau bị coi là bug | Encoder có salt ngẫu nhiên, đầu ra vốn không ổn định | Kiểm tra bằng `matches`, không so hai chuỗi encode |
| `encode(raw).equals(stored)` | `encode` sinh salt mới | Dùng `matches(raw, stored)` |
| Chỉ lưu phần hash, bỏ cost/salt | Không còn thông số để verify đúng | Lưu toàn bộ chuỗi encoded |
| Bcrypt cost quá thấp | Offline guessing quá rẻ | Đo và nâng cost/thuật toán an toàn |
| Bcrypt cost quá cao | Login chậm, có thể bị lạm dụng làm cạn CPU | Benchmark concurrency, rate limit, capacity planning |
| Đổi bean encoder xong nghĩ DB đã nâng hash | Hash cũ không tự thay đổi | Rehash khi đăng nhập thành công/reset với `upgradeEncoding` và persistence |
| Bỏ prefix `{bcrypt}` khi dùng delegating encoder | Format không tương thích mapping ID | Chuẩn hóa format, thiết kế migration |
| Lưu pepper cùng hash | Attacker DB lấy cả hai | Lưu secret tách biệt trong vault/HSM |
| Bỏ qua giới hạn 72 byte của bcrypt | Passphrase dài có thể bị cắt/khác nghĩa | Chính sách byte-length nhất quán hoặc chọn thuật toán khác |
| Chặn login online chỉ bằng cost cao | Work factor không thay rate limiting | Bổ sung rate limit, MFA, quan sát an ninh |
| Kiểm tra password ở mỗi API request | Hash chậm làm throughput thấp và tăng DoS surface | Chuyển sang session/token ngắn hạn sau login |
| Log raw password/hash để debug | Làm lộ credential qua log/trace | Log mã sự kiện không nhạy cảm |

## 13. Tình huống và câu hỏi tự kiểm tra

**Câu 1.** Alice và Bob dùng cùng password. Hash bcrypt của hai người khác nhau. Dữ liệu bị sai hay password khác?

**Đáp án:** không nhất thiết. Bcrypt dùng salt ngẫu nhiên khác nhau, nên cùng password có thể tạo hash khác nhau. Dùng `PasswordEncoder.matches` với từng hash tương ứng.

**Câu 2.** Có thể lưu salt công khai trong cột hoặc chung chuỗi với hash không?

**Đáp án:** có. Salt không phải bí mật. Bcrypt thường đã lưu salt cùng cost và hash. Pep per (pepper) mới là secret tùy chọn cần lưu tách biệt.

**Câu 3.** Nếu tăng bcrypt cost từ 10 lên 12, hash cũ có còn xác minh được không?

**Đáp án:** có với `BCryptPasswordEncoder` phù hợp; hash cũ ghi sẵn cost. Nhưng DB không tự rehash cho đến khi có raw password hợp lệ trong flow nâng cấp hoặc reset.

**Câu 4.** Tại sao không dùng `SHA-256(password + salt)` một lần?

**Đáp án:** salt giúp chống precomputation nhưng SHA-256 một vòng vẫn quá nhanh trên hardware tấn công. Cần password-hashing function adaptive có chi phí cao.

**Câu 5.** Công ty thấy 20.000 lần login sai/phút nên tăng bcrypt cost lên 20. Đã đủ chống brute force chưa?

**Đáp án:** chưa; còn có thể gây CPU DoS. Cần rate limiting, monitoring, MFA, chống password spraying, capacity planning và xác minh hiệu năng.

**Câu 6.** Dữ liệu DB bị lộ nhưng attacker không có pepper trong vault. Pepper có tác dụng gì?

**Đáp án:** có thể bổ sung bảo vệ nếu mô hình dùng pepper đúng cách, nhưng không thay thế salt/cost, không bảo vệ nếu vault cũng bị xâm nhập, và cần kế hoạch rotation/khôi phục.

**Câu 7.** User tạo password 80 ký tự Unicode và dùng bcrypt. Có thể mặc nhiên coi bcrypt kiểm tra đủ mọi ký tự không?

**Đáp án:** không. Nhiều bcrypt giới hạn đầu vào **72 byte**, không phải ký tự. Cần policy theo byte hoặc chọn thuật toán phù hợp với passphrase dài, không cắt thầm.

**Câu 8.** `BCryptPasswordEncoder.matches(raw, stored)` trả true. Điều đó có nghĩa user được vào endpoint admin?

**Đáp án:** không. Nó chỉ chứng minh password khớp hash đã lưu. Còn account status, authentication mechanism, MFA và authorization (role/permission) là các kiểm tra riêng.

**Câu 9.** Một hash có prefix `{bcrypt}` nhưng bạn gọi trực tiếp `new BCryptPasswordEncoder().matches(raw, prefixedHash)`. Vì sao có thể thất bại?

**Đáp án:** encoder bcrypt trực tiếp kỳ vọng định dạng bcrypt bắt đầu bằng `$2a$`/`$2b$`/`$2y$`; `{bcrypt}` là prefix của `DelegatingPasswordEncoder`. Dùng encoder khớp format lưu trữ hoặc migration hợp lệ.

## 14. Checklist áp dụng trong Spring Security

- [ ] Password không lưu rõ, không mã hóa hai chiều để hoàn nguyên khi login.
- [ ] Dùng `PasswordEncoder` loại adaptive, ưu tiên thuật toán được duy trì và phù hợp threat model.
- [ ] Salt được sinh bằng CSPRNG cho từng hash; không tự đặt salt cố định.
- [ ] Lưu toàn bộ hash kèm thông tin format, salt và cost để `matches` hoạt động.
- [ ] Cost được benchmark trên môi trường giống production với p95/p99 và concurrent authentication.
- [ ] Password policy xử lý độ dài/Unicode nhất quán, đặc biệt giới hạn 72 byte với bcrypt.
- [ ] Các flow tạo/đổi mật khẩu dùng `encode`; login dùng `matches`, không so chuỗi hash mới.
- [ ] Nếu dùng `DelegatingPasswordEncoder`, format `{id}...` nhất quán và migration được test.
- [ ] Có quy trình tăng cost/đổi thuật toán bằng `upgradeEncoding` và lưu hash mới sau đăng nhập/reset hợp lệ.
- [ ] Nếu có pepper, nó nằm trong secret manager/HSM tách khỏi DB, với rotation plan.
- [ ] Login API được bảo vệ bằng TLS, rate limiting, chống spraying, MFA và quan sát rủi ro.
- [ ] Không log mật khẩu, hash, pepper, session/token; backup/DB được hạn chế quyền.
- [ ] Có integration tests cho password đúng/sai, hash cũ, cost mới, password dài và nhiều request đồng thời.

**Kết luận:** salt làm mỗi bản ghi password hash có tính ngẫu nhiên riêng, còn work factor làm phép thử mật khẩu tốn công hơn khi attacker đã lấy được hash. Hai yếu tố này **làm giảm hiệu quả cracking ngoại tuyến**, nhưng không biến password yếu thành an toàn tuyệt đối và không thay thế chống dò trực tuyến. Trong Spring Security, hãy dùng `PasswordEncoder.encode` khi lưu, `matches` khi xác minh, hiệu chỉnh cost theo hệ thống thật và nâng hash theo lộ trình có kiểm chứng.

## Tài liệu tham khảo

- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — Crypto Module / Password Encoding](https://docs.spring.io/spring-security/reference/6.5/features/integrations/cryptography.html)
- [Spring Security — BCryptPasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html)
- [Spring Security — PasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — UserDetailsPasswordService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html)
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
