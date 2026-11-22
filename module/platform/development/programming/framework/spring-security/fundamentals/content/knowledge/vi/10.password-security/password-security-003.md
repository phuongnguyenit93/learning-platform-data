# Salt, chi phí tính toán và khả năng chống dò mật khẩu

**Salt** và **chi phí tính toán (work factor/cost)** là hai cơ chế bổ trợ nhau để bảo vệ mật khẩu của người dùng khi cơ sở dữ liệu chứa password hash bị rò rỉ. Salt làm cho cùng một mật khẩu không mặc nhiên tạo ra cùng một giá trị lưu; work factor khiến mỗi lần **thử đoán** mật khẩu phải trả một chi phí tính toán đáng kể. Cả hai không thay thế cho mật khẩu đủ khó đoán, kiểm soát truy cập, TLS, MFA hay rate limiting.

Trong Spring Security, lập trình viên thường gặp các cơ chế này thông qua `PasswordEncoder`: gọi `encode(rawPassword)` khi tạo/đổi mật khẩu, lưu encoded hash; và `matches(rawPassword, storedHash)` để xác thực khi đăng nhập. Những password encoder thích hợp như bcrypt tự xử lý salt, định dạng hash và thông số cost; ứng dụng không cần tự thiết kế phép nối chuỗi `password + salt`.

Bài tập trung vào **“Salt, chi phí tính toán và khả năng chống dò mật khẩu”** thuộc nhóm *Mật khẩu*, dùng Java 17+ và Spring Security 6.x/Spring Boot 3 làm ví dụ. Phần lý thuyết và quyết định kiến trúc cũng hữu ích với các hệ thống khác. Các số cấu hình tham khảo OWASP là **mốc tại thời điểm tra cứu**, cần kiểm tra hướng dẫn hiện hành và đo trên máy chủ thực trước khi triển khai.

## 1. Threat model: chống lại ai, trong hoàn cảnh nào?

Cần phân biệt **hai kiểu thử mật khẩu** có giới hạn khác nhau.

### 1.1. Dò trực tuyến (online guessing)

Kẻ tấn công gọi chức năng đăng nhập nhiều lần:

```text
Attacker
  |
  | POST /login {username, passwordCandidate}
  v
Authentication filter / provider
  |
  +-- Kiểm tra account, password hash, các chính sách
  |
  +-- Trả thành công / thất bại
  |
  v
Attacker có thể lặp lại nếu không bị hạn chế
```

Hệ thống có thể quan sát và giới hạn request trực tuyến: rate limiting, progressive backoff, cơ chế chống credential stuffing, đánh giá rủi ro, MFA, giám sát và cảnh báo. **Salt và work factor không thay thế các giới hạn này**. Thậm chí work factor đặt quá cao có thể khiến kẻ tấn công gây quá tải CPU/RAM bằng cách gửi nhiều lần đăng nhập.

### 1.2. Dò ngoại tuyến (offline cracking)

Attacker đã lấy được bản sao database hoặc backup có password hash; họ không cần gửi từng candidate tới server:

```text
Database bị lộ:
   user_id | password_hash + salt + cost
       |
       v
Attacker tải dữ liệu về hạ tầng riêng
       |
       +-- Chọn một candidate password
       +-- Tính password KDF với salt/cost tương ứng
       +-- So sánh với stored hash
       +-- Thử candidate khác hoặc sử dụng GPU/thiết bị khác
```

Ở đây rate limiting HTTP, CAPTCHA và account lockout **không thể kiểm soát số lần tính** trên máy của attacker. Phòng vệ quan trọng gồm: mật khẩu khó đoán, password KDF chuyên dụng, salt đủ tốt, tham số cost phù hợp và bảo vệ database. Pepper lưu ngoài DB có thể tăng một lớp phòng vệ nhưng không thay thế các phần trước.

**Điểm chốt:** Salt chủ yếu giảm lợi thế **tính sẵn và dùng lại kết quả** giữa các tài khoản; cost chủ yếu làm tăng tài nguyên cần cho **mỗi phép thử**. Chúng giải quyết hai khía cạnh khác nhau của cùng threat model.

## 2. Salt là gì và giải quyết vấn đề gì?

Salt là dữ liệu ngẫu nhiên được tạo mới **cho từng password hash**, thường được lưu ngay cạnh hash để phục vụ verification. Nó không phải mật khẩu và **không cần được giữ bí mật**.

Một mô hình trừu tượng:

```text
stored = KDF(password, randomSalt, parameters)
```

Khi login, ứng dụng lấy salt/tham số đã lưu, tính/verifies candidate tương ứng. Với bcrypt, Argon2id và các encoder phù hợp, việc đọc và sử dụng salt được thư viện thực hiện thông qua định dạng encoded password.

### 2.1. Cùng mật khẩu nhưng salt khác

Giả sử Alice và Bob cùng chọn mật khẩu `blue-mountain`:

```text
Alice: KDF("blue-mountain", salt_A, cost) -> hash_A
Bob:   KDF("blue-mountain", salt_B, cost) -> hash_B

salt_A != salt_B
=> hash_A và hash_B khác nhau với xác suất áp đảo
```

Nếu không có salt, attacker có thể thấy hai password hashes giống nhau và suy ra cùng raw password. Khi dùng salt riêng, điều đó khó nhận biết chỉ qua việc so chuỗi hash. Người dùng chọn chung mật khẩu yếu **vẫn gặp rủi ro** nếu attacker thử đúng candidate cho từng hash.

Salt không làm user A có một password mới. Cùng một password raw vẫn là cùng một bí mật do user biết; salt chỉ làm biểu diễn lưu trữ khác nhau.

### 2.2. Salt làm bảng rainbow table kém hiệu quả

Một bảng được tính trước có thể ghép những password phổ biến với kết quả hash khi thuật toán **không có salt**:

```text
"123456"     -> hash_1
"password"   -> hash_2
"welcome"    -> hash_3
...
```

Khi mỗi hash dùng salt ngẫu nhiên, một bảng tính cho một salt không dùng lại trực tiếp cho các salt khác. Attacker phải xét salt cụ thể, khiến việc tính sẵn ở quy mô lớn trở nên kém hữu ích.

**Nhưng:** attacker có thể **tính candidate với salt public của tài khoản đang tấn công**. Salt không ngăn hoàn toàn dictionary attack; nó chỉ giảm khả năng tái sử dụng phép tính/precomputation. Vì vậy cần thêm work factor mạnh.

### 2.3. Độ dài và cách sinh salt

Ví dụ một salt 16 byte (128 bit) được tạo bằng `SecureRandom` trong Java:

```java
SecureRandom random = new SecureRandom();
byte[] salt = new byte[16];
random.nextBytes(salt);
```

Đây là fragment cần import `java.security.SecureRandom`, không phải toàn bộ chương trình. Salt 16 byte là kích thước thực hành thông dụng phù hợp cho ví dụ; policy chính xác còn tùy KDF/chuẩn đang dùng.

Khi có đủ entropy, xác suất hai salt ngẫu nhiên trùng là rất nhỏ đối với số lượng user thông thường, **nhưng không phải bằng 0**. Ứng dụng cần CSPRNG, không dùng `Random` thường, timestamp, số tăng dần dễ đoán hoặc một chuỗi cố định. Hãy để password encoder đáng tin tạo salt nếu API đã hỗ trợ.

### 2.4. Salt có cần cất trong environment variable?

Không. Salt không phải secret. Bạn cần lưu nó để verify password sau này; nhiều hash format đã nhúng salt vào cùng chuỗi. Điều thực sự cần bảo vệ là raw password, password hashes để tránh offline guessing và pepper/secret key nếu có.

Không giấu salt trong server config rồi dùng một giá trị cho mọi người. Cách đó không cho lợi ích **mỗi password một salt**.

### 2.5. Mỗi lần đổi password có cần salt mới không?

**Có.** Khi user đặt password mới hoặc hệ thống rehash để nâng thuật toán/cost, encoder thường sinh salt mới. Không mang salt cũ sang chỉ để kết quả dễ tái lập. Lúc xác minh một password **đang lưu**, bắt buộc sử dụng salt **đã lưu**, không sinh salt mới để so sánh.

| Sự kiện | Salt/Hash |
| --- | --- |
| Đăng ký user | Sinh salt mới; hash password |
| Login bằng password hiện tại | Đọc salt/cost trong hash đã lưu; `matches` |
| Đổi password | Hash password mới với salt mới |
| Rehash do đổi work factor | Sau khi verify, hash lại raw password với cấu hình mới và salt mới |
| Quên password | Dùng password reset hợp lệ; không có bước giải mã hash |

## 3. Work factor là gì?

Work factor (hay cost/effort) là thông số điều chỉnh mức tài nguyên cần để tạo/verify password hash. Một thuật toán bảo vệ password tốt **cố ý tiêu tốn tài nguyên** để tấn công thử hàng triệu ứng viên trở nên đắt đỏ.

Ví dụ:

- Với **bcrypt**, cost `c` liên quan đến khối lượng công việc tăng xấp xỉ theo `2^c`. Tăng từ cost 10 lên 12 làm phần việc được điều khiển bởi cost tăng khoảng **4 lần**, không nhất thiết thời gian toàn hàm chính xác 4 lần trên mọi máy.
- Với **PBKDF2**, tham số chủ yếu là số lần lặp HMAC; đổi từ 300.000 lên 600.000 vòng làm phần tính lặp tăng khoảng 2 lần, chưa tính overhead khác.
- Với **scrypt** và **Argon2id**, cost không chỉ là CPU: bộ nhớ cần cho mỗi lần thử cũng rất quan trọng.

Work factor không “mã hóa” password, không làm password dài ra và không đổi quyền người dùng. Nó tác động tới **giá mỗi lần đoán**, còn entropy/độ dài/tính khó đoán của password tác động tới **số ứng viên** attacker có thể phải thử.

### 3.1. Vì sao không dùng SHA-256 một lần?

SHA-256, SHA-512 và nhiều digest mật mã chung được tối ưu để tính **nhanh**. Chúng phù hợp với kiểm tra toàn vẹn và các thiết kế khác, nhưng không phù hợp làm **định dạng lưu password trực tiếp**.

```text
Không nên: stored = SHA256(password)
Vẫn không đủ: stored = SHA256(salt || password)

Nên: stored = PasswordKDF(password, randomSalt, tunedCost)
```

Việc thêm salt cho một fast hash tốt hơn không có salt ở góc nhìn precomputation, nhưng **không làm phép thử trở nên chậm**. Chọn thuật toán password hashing chuyên dụng, không tự nối `SHA256` nhiều lần một cách tùy tiện để thay bcrypt/Argon2id.

### 3.2. CPU cost và memory-hardness

GPU/ASIC có thể tính rất nhiều phép hash nhanh cùng lúc. Một KDF chỉ tiêu tốn CPU có thể vẫn bị tăng tốc đáng kể bởi phần cứng song song. **Memory-hard KDF** như Argon2id hoặc scrypt còn buộc mỗi phép thử sử dụng lượng RAM đáng kể, làm tăng chi phí mở rộng trên thiết bị tấn công.

Tuy vậy, memory-hard KDF cũng dùng tài nguyên trên **server của bạn**. Nếu mỗi request chiếm hàng chục MiB và có nhiều login song song, bạn phải lập kế hoạch capacity và ngăn attacker lợi dụng để tạo DoS.

### 3.3. Các tham số không giống nhau giữa thuật toán

| KDF | Tham số chính | Cần hiểu đúng |
| --- | --- | --- |
| bcrypt | Cost/strength (ví dụ 10, 12) | Công việc tăng khoảng gấp đôi khi tăng cost 1 đơn vị; có caveat input 72 byte |
| PBKDF2-HMAC-SHA256 | Iteration count, salt, derived-key length | Nhiều vòng hơn làm chậm verification; không memory-hard theo cách Argon2id |
| Argon2id | Memory `m`, passes `t`, parallelism `p` | `m` là **tổng bộ nhớ** cho một lần tính, `p` không có nghĩa nhân bộ nhớ thêm `p` lần |
| scrypt | `N`, `r`, `p` | Tính toán và bộ nhớ phụ thuộc tổ hợp tham số, không gọi tất cả là “iterations” |

Không thể so “bcrypt cost 12” với “Argon2id iterations 2” bằng cách so 12 và 2. Đây là các định nghĩa thuật toán khác nhau; muốn chọn phải đánh giá chi phí và mức kháng tấn công trên threat model thực tế.

## 4. Gợi ý cấu hình từ OWASP và cách sử dụng đúng

Theo *OWASP Password Storage Cheat Sheet* được đối chiếu cho bài này, những **ngưỡng tham khảo** nổi bật gồm:

| Thuật toán / trường hợp | Gợi ý OWASP tại thời điểm tham khảo | Lưu ý |
| --- | --- | --- |
| Argon2id | `m=19 MiB, t=2, p=1` là một trong các cấu hình tối thiểu tương đương | Cân bằng CPU/RAM; OWASP còn nêu các cặp m/t tương đương |
| scrypt khi Argon2id không khả dụng | `N=2^17, r=8, p=1` | Mức bộ nhớ đáng kể; đánh giá capacity |
| bcrypt với hệ thống legacy | Work factor ít nhất `10` | Nhiều implementation chỉ xử lý 72 byte đầu vào |
| PBKDF2-HMAC-SHA256 khi có yêu cầu FIPS/tương thích | Khoảng `600.000` iterations trở lên theo hướng dẫn | Dùng HMAC-SHA256, salt và định dạng lưu tham số |

Nguồn: [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

**Không nhầm ngưỡng tối thiểu với “số tối ưu cho mọi ứng dụng”.** Khuyến nghị có thể thay đổi theo thời gian và cấu hình triển khai; hãy kiểm tra tài liệu mới nhất trước khi đưa vào production. Với ứng dụng mới, OWASP ưu tiên Argon2id khi được hỗ trợ phù hợp; Spring Security vẫn cung cấp BCryptPasswordEncoder rất phổ biến và thuận tiện để học/hỗ trợ hệ thống đã dùng bcrypt.

### 4.1. Argon2id: hiểu m, t và p

Ví dụ `m=19 MiB, t=2, p=1`:

- `m`: tổng RAM mà một lượt tính cần theo định nghĩa của thuật toán; `19 MiB = 19 × 1024 KiB`.
- `t`: số pass qua dữ liệu bộ nhớ/khối làm việc.
- `p`: mức parallelism/lanes, không phải số vòng lặp và không tự nhân đôi m.
- Cùng một cấu hình có thể có thời gian thực thi khác nhau trên máy khác nhau.

Nếu có 200 yêu cầu xác minh đồng thời và mỗi lượt tính cần xấp xỉ 19 MiB, riêng dữ liệu làm việc lý thuyết đã khoảng `200 × 19 = 3.800 MiB`, chưa gồm JVM/OS, object overhead, provider implementation và các phần khác. Đây là phép tính planning đơn giản, không phải kết quả benchmark thực.

**Quy tắc vận hành:** giới hạn đồng thời và đo bộ nhớ đỉnh. Không giảm cost xuống mức yếu chỉ vì máy chủ bị quá tải; kết hợp capacity planning với rate limiting, hàng đợi, xử lý tài khoản và chính sách xác thực.

### 4.2. bcrypt: hiểu cost exponent

Một hash bcrypt có thể bắt đầu như sau:

```text
$2a$12$...(phần salt và hash đã được mã hóa)
    ^^
    cost 12
```

Ví dụ này là minh họa format; chuỗi được tạo thực tế còn có 53 ký tự ở phần sau prefix, không viết password plaintext ở đó. Một encoded bcrypt thường chứa version, cost, salt và kết quả trong cùng chuỗi.

Từ cost `10` lên `12`: phần lượng công việc theo quy tắc `2^cost` tăng `2^(12-10) = 4` lần. **Không kết luận** mọi request đăng nhập chậm đúng gấp 4 vì có overhead, CPU throttling, load, provider, VM warmup và các phần kiểm tra khác.

**Caveat 72 byte:** nhiều bcrypt implementations chỉ xét tối đa 72 **byte** của raw password. `String.length()` của Java tính UTF-16 code units, không phải số byte UTF-8. Hãy kiểm tra tài liệu encoder, chính sách password dài và cách xử lý Unicode. Không cắt ngầm raw password hoặc tự pre-hash SHA-256 trước bcrypt mà không hiểu các rủi ro như password shucking.

### 4.3. PBKDF2: hiểu iterations

PBKDF2 dùng thuật toán PRF như HMAC-SHA256 và một số vòng lặp. Với cùng password, salt, iterations và derived-key length, kết quả là xác định; nếu đổi salt hoặc tham số, kết quả thường thay đổi.

```text
PBKDF2(
    rawPassword,
    storedSalt,
    iterations=600000,
    outputBits=256
)
```

Giá trị `600.000` là tham khảo phù hợp cho ví dụ, **không phải công thức magic**. Triển khai production cần lưu iterations và algorithm ID cùng hash, quản lý migration và benchmark. Đừng tự đặt `iterations=1000` chỉ để login nhanh và nghĩ rằng salt đủ bảo vệ.

## 5. Tính chi phí tấn công: hiểu một mô hình ước lượng

Một mô hình đơn giản giúp nhìn rõ hai biến:

```text
Thời gian thử ≈ Số lượng candidates / Tốc độ thử hữu hiệu
```

Ví dụ giả định **chỉ để minh họa toán học**, không dự đoán GPU hoặc một hệ thống thực:

| Số mật khẩu cần thử | Tốc độ giả định | Thời gian giả định |
| ---: | ---: | ---: |
| 1.000.000 | 10.000 guesses/s | 100 giây |
| 1.000.000 | 1.000 guesses/s | 1.000 giây |
| 1.000.000 | 100 guesses/s | 10.000 giây |
| 100.000.000 | 100 guesses/s | 1.000.000 giây |

Nếu cost cao làm tốc độ thử giảm, thời gian với **cùng** số ứng viên sẽ tăng theo mô hình. Nhưng con số guesses/s **không cố định**: nó khác nhau giữa Argon2id, bcrypt, PBKDF2, từng cost, GPU/FPGA, CPU, số thiết bị, cách batch thử và ngân sách attacker.

Các yếu tố khác khiến công thức đơn giản không dự đoán chính xác:

- Attacker thường ưu tiên password phổ biến trước, không thử ứng viên theo thứ tự ngẫu nhiên;
- Không cần thử hết không gian nếu password nằm trong từ điển thông dụng;
- Nhiều hash có salt khác nhau hạn chế dùng lại một phép tính, nhưng attacker vẫn có thể parallelize;
- Pepper giữ ngoài DB có thể làm attacker thiếu dữ liệu cần thiết cho offline verification;
- Cơ chế mã hóa/kho dữ liệu và sự cố lộ secret khác nhau tạo threat model khác.

**Salt không tăng entropy của password do user chọn.** Một password `123456` vẫn dễ đoán. Hash chậm khiến việc thử tốn công hơn, nhưng không biến password yếu thành không thể đoán.

## 6. Pepper là gì? Không nhầm với salt

**Pepper** là một bí mật bổ sung được quản lý ở phía server, thường nằm ngoài database chứa password hashes. Nó có thể tăng rào cản nếu attacker chỉ lấy được DB nhưng chưa chiếm được secret store.

| Tính chất | Salt | Pepper |
| --- | --- | --- |
| Có phải secret? | Không | **Có** |
| Thường riêng cho từng password? | Có | Thường dùng chung trong một phạm vi |
| Có lưu cạnh hash? | Có | Không nên |
| Có cần khi verify? | Có, lấy từ hash đã lưu | Có, nếu hệ thống dùng pepper |
| Bảo vệ chính | Chống dùng lại kết quả tính trước, làm hash khác nhau | Bổ sung phòng vệ khi DB lộ mà secret vẫn an toàn |
| Khi cần thay đổi | Sinh mới lúc hash lại | Cần kế hoạch rotation, migration/reset |

Pepper không thay thế salt và work factor. Không tự ghép `SHA256(pepper + password)` rồi coi là một password KDF an toàn. Nếu dùng pepper, chọn scheme đã được đánh giá, quản lý secret qua KMS/HSM/vault và suy nghĩ trước về cách rotate khi có hàng triệu hashes mà hệ thống không biết raw passwords.

### 6.1. Salt và pepper không phải IV/nonce

IV/nonce phục vụ mã hóa đối xứng như AES-GCM; không được tái dùng nonce với cùng key. Salt của password KDF có ràng buộc riêng, còn pepper là secret. Đừng lấy một hằng số trong file config rồi gán cho cả ba khái niệm.

## 7. Spring Security: tránh tự xử lý salt khi dùng PasswordEncoder

API chính:

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

Đây là dạng rút gọn minh họa interface. Package là `org.springframework.security.crypto.password.PasswordEncoder`. Không có `decrypt` vì password hash **không phải ciphertext cần giải mã**.

### 7.1. Encode một lần khi lưu, matches khi login

```java
PasswordEncoder encoder = new BCryptPasswordEncoder(12);

String stored = encoder.encode("training-password");

boolean yes = encoder.matches("training-password", stored);
boolean no  = encoder.matches("wrong-password", stored);
```

`yes` là true, `no` là false. `encode` sinh random salt và định dạng hash có cost. Đừng tự lưu salt vào một field khác trừ khi algorithm/storage design thật sự yêu cầu; nhiều encoder đã lưu salt trong encoded password.

**Sai lầm rất phổ biến:**

```java
// SAI với thuật toán sinh salt ngẫu nhiên:
encoder.encode(raw).equals(storedHash);

// ĐÚNG:
encoder.matches(raw, storedHash);
```

Hai lần `encode` cùng raw thường cho hai hash khác nhau. `matches` đọc salt/cost phù hợp từ stored hash để so candidate.

### 7.2. Spring Security tự kiểm tra password ở đâu?

Trong luồng username/password thông dụng:

```text
Login form hoặc HTTP Basic
       |
       v
AuthenticationFilter tạo UsernamePasswordAuthenticationToken
       |
       v
AuthenticationManager / ProviderManager
       |
       v
DaoAuthenticationProvider
       |
       +-- UserDetailsService.loadUserByUsername(username)
       |       -> username, stored password hash, authorities, flags
       |
       +-- PasswordEncoder.matches(raw, storedHash)
       +-- Kiểm tra trạng thái tài khoản theo provider
       |
       v
Authentication thành công hoặc AuthenticationException
       |
       v
SecurityContext và Authorization
```

`UserDetailsService` **không tự kiểm tra raw password**; nó tìm và trả `UserDetails` chứa hash. `PasswordEncoder` thực hiện so khớp. Provider đánh giá credentials và account state. Controller không giải mã mật khẩu để login.

Khi user đã đăng nhập, không nên bắt họ cung cấp password ở **mọi request API** chỉ để xác thực lại; như tài liệu Spring Security lưu ý, password KDF cố ý tốn tài nguyên. Session/token ngắn hạn được quản lý đúng sẽ phù hợp hơn với nhiều kiến trúc; các hoạt động nhạy cảm có thể yêu cầu re-authentication theo chính sách.

### 7.3. BCryptPasswordEncoder strength và format

Cấu hình:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder(12);
}
```

Một hash mới thường có dạng bắt đầu bằng `$2a$12$` khi dùng constructor/config được mô tả; version prefix có thể khác theo implementation. Salt và cost đã nằm trong chuỗi. Không hardcode toàn bộ hash làm output: salt ngẫu nhiên khiến kết quả từng lần encode thay đổi.

`BCryptPasswordEncoder` có thể kiểm tra một hash bcrypt đã lưu với cost thấp hơn mà không cần biết cost trước trong code, bởi cost được encode trong chính hash. Để nâng cấp cost, dùng `upgradeEncoding` khi cần và có flow update storage đúng.

### 7.4. DelegatingPasswordEncoder cho migration

Spring Security cung cấp factory:

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String encoded = encoder.encode("training-password");
boolean valid = encoder.matches("training-password", encoded);
```

Trong cấu hình mặc định Spring Security 6.5 được minh họa, `encoded` thường có prefix `{bcrypt}`. Format:

```text
{id}encodedPassword

{bcrypt}$2a$10$...
{pbkdf2}...
{scrypt}...
```

`id` chọn delegate thuật toán, **không phải secret**. Nếu DB lưu bcrypt hash cũ **không có** `{bcrypt}` mà ứng dụng chuyển sang delegating encoder không có default mapping phù hợp, có thể nhận lỗi `There is no PasswordEncoder mapped for the id "null"`. Hãy xác định hash format và migration; không sửa nhanh bằng `NoOpPasswordEncoder`.

### 7.5. Argon2id trong Spring Security: chú ý dependency

Spring Security có `Argon2PasswordEncoder`. Ví dụ cấu hình **minh họa** cho môi trường đã có hỗ trợ Argon2 và dependencies tương ứng:

```java
PasswordEncoder argon2 = new Argon2PasswordEncoder(
    16,        // saltLength bytes
    32,        // hashLength bytes
    1,         // parallelism
    19 * 1024, // memory KiB = 19 MiB
    2          // iterations
);
```

Đoạn này là fragment, cần import `org.springframework.security.crypto.argon2.Argon2PasswordEncoder` và phiên bản Spring Security phù hợp. Tại các phiên bản Spring Security 6.x thông dụng, implementation Argon2 yêu cầu **Bouncy Castle** ở runtime; phải xem đúng dependencies của project, không kỳ vọng chỉ JDK17 là đủ. Khi cấu hình ứng dụng thật, kiểm tra **Javadoc, OWASP và benchmark** trước khi áp dụng, đồng thời hạn chế xác thực đồng thời để bảo vệ RAM. Không thay đổi encoder bean sang Argon2 tùy tiện rồi làm hỏng verification của hashes bcrypt cũ: cần DelegatingPasswordEncoder/migration strategy.

## 8. Java 17 độc lập: nhìn thấy salt riêng và chi phí PBKDF2

Mã này **biên dịch bằng JDK 17 thuần**, không cần Spring Security. Nó dùng `PBKDF2WithHmacSHA256`, `SecureRandom` và `MessageDigest.isEqual` để minh họa:

1. Hai salts ngẫu nhiên khác nhau cho cùng password.
2. Stored hash có salt và iteration count.
3. Một candidate đúng được chấp nhận khi dùng **salt đã lưu**.
4. Password sai bị từ chối.
5. Không có phép giải mã password.
6. Work factor được lưu như metadata, để phiên bản sau vẫn biết cách verify và rehash.

Đây là **bài tập về cơ chế**, không phải một implementation production thay thế `PasswordEncoder`; production còn cần định dạng lưu trữ, input normalization policy, rate limiting, concurrency limits, algorithm migration, bảo vệ secret, lỗi, audit và benchmark.

### 8.1. Tệp đầy đủ: SaltAndCostDemo.java

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class SaltAndCostDemo {

    private static final int SALT_BYTES = 16;
    private static final int ITERATIONS = 600_000;
    private static final int OUTPUT_BITS = 256;

    record StoredPassword(
        byte[] salt,
        int iterations,
        byte[] hash
    ) {}

    static byte[] derive(
            char[] rawPassword,
            byte[] salt,
            int iterations
    ) throws GeneralSecurityException {

        PBEKeySpec spec = new PBEKeySpec(
            rawPassword, salt, iterations, OUTPUT_BITS
        );

        try {
            return SecretKeyFactory
                .getInstance("PBKDF2WithHmacSHA256")
                .generateSecret(spec)
                .getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    static StoredPassword create(
            char[] password,
            SecureRandom random
    ) throws GeneralSecurityException {

        byte[] salt = new byte[SALT_BYTES];
        random.nextBytes(salt);

        return new StoredPassword(
            salt,
            ITERATIONS,
            derive(password, salt, ITERATIONS)
        );
    }

    static boolean verify(
            char[] candidate,
            StoredPassword stored
    ) throws GeneralSecurityException {

        byte[] computed = derive(
            candidate,
            stored.salt(),
            stored.iterations()
        );

        try {
            return MessageDigest.isEqual(
                computed,
                stored.hash()
            );
        } finally {
            Arrays.fill(computed, (byte) 0);
        }
    }

    public static void main(String[] args)
            throws GeneralSecurityException {

        SecureRandom random = new SecureRandom();
        char[] raw = "training-password-17".toCharArray();
        char[] wrong = "incorrect-password".toCharArray();

        try {
            StoredPassword alice = create(raw, random);
            StoredPassword bob = create(raw, random);

            System.out.println(
                "salt.bytes=" + alice.salt().length
            );
            System.out.println(
                "cost.iterations=" + alice.iterations()
            );
            System.out.println(
                "hash.bytes=" + alice.hash().length
            );
            System.out.println(
                "alice.verify.correct=" + verify(raw, alice)
            );
            System.out.println(
                "alice.verify.wrong=" + verify(wrong, alice)
            );
            System.out.println(
                "bob.verify.correct=" + verify(raw, bob)
            );
            System.out.println(
                "sameSalt=" + Arrays.equals(
                    alice.salt(), bob.salt()
                )
            );
            System.out.println(
                "sameHash=" + Arrays.equals(
                    alice.hash(), bob.hash()
                )
            );
        } finally {
            Arrays.fill(raw, '\0');
            Arrays.fill(wrong, '\0');
        }
    }
}
```

Chạy:

```bash
javac SaltAndCostDemo.java
java SaltAndCostDemo
```

**Kết quả dự kiến trong thực tế** (hai dòng `sameSalt`/`sameHash` dùng random, xác suất ngoại lệ cực nhỏ nhưng không phải bằng 0):

```text
salt.bytes=16
cost.iterations=600000
hash.bytes=32
alice.verify.correct=true
alice.verify.wrong=false
bob.verify.correct=true
sameSalt=false
sameHash=false
```

Không in raw password, salt/hash thật hay thời gian chạy vì giá trị ngẫu nhiên và thời gian thực thi không cố định. Đây là **dự kiến theo logic code**, không khẳng định đã chạy JDK tại thời điểm soạn bài.

### 8.2. Giải thích vì sao kết quả như vậy

- `SALT_BYTES=16` tương đương 128-bit salt. Mỗi lần `create` gọi `SecureRandom.nextBytes` để có salt mới.
- `ITERATIONS=600_000` là tham số cost mà record lưu cùng salt/hash. Lúc verify, code dùng `stored.iterations()`; nếu ứng dụng upgrade cost sau này, hash cũ vẫn biết thông số cũ.
- `OUTPUT_BITS=256` làm giá trị derived dài 32 bytes.
- `verify(raw, alice)` tạo lại KDF với password đúng và **salt của Alice**, nên khớp.
- `verify(wrong, alice)` tạo kết quả khác với xác suất áp đảo; một password candidate sai không được chấp nhận.
- Alice và Bob có cùng raw password nhưng salt được sinh độc lập, nên stored hash khác nhau với xác suất áp đảo.
- `MessageDigest.isEqual` được dùng để so sánh byte arrays phục vụ verification thay vì so chuỗi encode mới.
- `PBEKeySpec.clearPassword()` và `Arrays.fill` giúp hạn chế thời gian tồn tại của password/derived bytes, nhưng literal demo vẫn tồn tại trong class; **không hardcode secret production**.
- StoredPassword ở demo giữ byte[] mutable, không copy defensive; production cần thiết kế object/storage và secret lifecycle chặt chẽ hơn. Đừng dùng record này trực tiếp cho database thật.

**Quan trọng:** Không đổi `create` để dùng lại salt của user khác nhằm dễ debug. Nếu bạn chạy chương trình nhiều lần, hashes/salts thực khác nhau là hành vi mong muốn.

### 8.3. Đánh giá cost bằng đo đạc, không đoán

Đừng hardcode phát biểu “600.000 iterations mất 100 ms”. Tốc độ phụ thuộc CPU, JDK provider, VM warmup, thread contention và load. Khi đo:

1. Benchmark trên cùng cấu hình tương đương production;
2. Warm up JVM và thực hiện đủ samples, xem p50/p95/p99 thay vì một lần duy nhất;
3. Tách thời gian password KDF khỏi JDBC/network/HTTP;
4. Đo CPU và peak RAM cho concurrency thực;
5. Kiểm tra thí nghiệm với kịch bản password sai và user không tồn tại;
6. Cân bằng response latency và nguy cơ DoS/rate limit;
7. Document algorithm version/cost và xem xét tăng định kỳ;
8. Dùng benchmark framework như JMH cho thí nghiệm vi mô khi cần số liệu đáng tin.

Có thể viết test hiệu năng ngoài CI chịu tải, nhưng **không** đưa assertion cố định kiểu `assertTrue(duration < 100ms)` vào unit test chạy trên mọi máy: chúng thường không ổn định.

## 9. Spring Boot 3: dùng BCryptPasswordEncoder với salt và cost

Bộ ví dụ sau minh họa password hashing theo Spring Security thay vì tự tạo salt/loop bằng JCA. Chúng ta dùng **bcrypt cost 12** như một mức để học và kiểm thử; đây **không phải kết luận bcrypt tốt nhất cho mọi hệ thống mới** hoặc cost 12 đủ cho mọi risk profile.

Cấu trúc project:

```text
src/main/java/example/passwordcost/
    PasswordCostApplication.java
    SecurityConfig.java
    DemoController.java

src/test/java/example/passwordcost/
    PasswordCostTest.java
```

### 9.1. Dependency

Trong một project Spring Boot 3 đã có plugin và Java 17 toolchain, phần `dependencies` của `build.gradle` Groovy:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây không phải file build hoàn chỉnh. Với Maven, thêm hai starter tương ứng và `spring-security-test` ở test scope. Để Spring Boot BOM quản lý phiên bản Spring Security tương thích; nếu nâng lên một dòng phiên bản framework khác, kiểm tra cú pháp và build/test lại.

### 9.2. PasswordCostApplication.java

```java
package example.passwordcost;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasswordCostApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordCostApplication.class, args);
    }
}
```

### 9.3. SecurityConfig.java

```java
package example.passwordcost;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(12);
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-password"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Ở đây:

1. `new BCryptPasswordEncoder(12)` tạo encoder dùng bcrypt cost 12, bao gồm salt random được tạo trong `encode`.
2. Khi tạo **user demo** trong bộ nhớ, `encoder.encode(...)` tạo hash đã lưu. Ứng dụng thật làm việc này khi đăng ký/đổi password, không hardcode mật khẩu trong source.
3. `UserDetailsService` tải hash và authorities. `DaoAuthenticationProvider` thuộc luồng username/password thích hợp dùng `PasswordEncoder.matches` để verify.
4. `HttpSecurity.httpBasic(...)` nhận credentials từ Basic header. HTTP Basic chỉ dùng Base64, không mã hóa đường truyền; production phải dùng TLS/HTTPS.
5. `authorizeHttpRequests` kiểm tra quyền sau xác thực. Có password đúng không có nghĩa có quyền admin.
6. `anyRequest().denyAll()` từ chối các route chưa khai báo.
7. Bản demo chỉ có GET nên không vô hiệu hóa CSRF; nếu thêm POST có cookie/session cần xem xét token CSRF theo threat model.

Khi dùng `BCryptPasswordEncoder` trực tiếp, hash thường có prefix dạng `$2a$12$...` chứ **không có** `{bcrypt}` của delegating format. Khi migrate sang `DelegatingPasswordEncoder`, phải xử lý định dạng hash cũ đúng cách; không phải cứ thay bean là hash đang lưu tự đổi.

### 9.4. DemoController.java

```java
package example.passwordcost;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    Map<String, String> currentUser(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/api/admin")
    Map<String, String> adminOnly() {
        return Map.of("message", "admin");
    }
}
```

Controller nhận `Authentication` đã được provider kiểm tra, không lấy password hash từ request và không tự mã hóa/giải mã mật khẩu. Không trả `UserDetails.getPassword()` qua response.

### 9.5. Chạy và gọi API

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Giả sử server demo ở `http://localhost:8080`:

```bash
# Anonymous public: 200
curl -i http://localhost:8080/public

# Anonymous private: 401
curl -i http://localhost:8080/api/me

# Reader password đúng: 200
curl -i -u reader:reader-demo-password \
  http://localhost:8080/api/me

# Reader password sai: 401
curl -i -u reader:incorrect \
  http://localhost:8080/api/me

# Reader đã login nhưng thiếu ROLE_ADMIN: 403
curl -i -u reader:reader-demo-password \
  http://localhost:8080/api/admin

# Admin đã login và có ROLE_ADMIN: 200
curl -i -u admin:admin-demo-password \
  http://localhost:8080/api/admin
```

Các mã HTTP là **kỳ vọng theo cấu hình**. Không khẳng định đã chạy server/Gradle ở đây. Mật khẩu demo chỉ dành cho localhost; `curl -u` có thể hiện password trong shell history/process list. Ứng dụng thật phải sử dụng HTTPS và quản lý secret an toàn.

## 10. JUnit/MockMvc: kiểm tra salt, cost và xác thực

Tạo `src/test/java/example/passwordcost/PasswordCostTest.java`:

```java
package example.passwordcost;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordCostTest {

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    UserDetailsService users;

    @Autowired
    MockMvc mvc;

    @Test
    void costIsStoredInBcryptHash() {
        String hash = encoder.encode("demo-candidate");

        assertThat(hash).startsWith("$2");
        assertThat(hash.substring(4, 6)).isEqualTo("12");
        assertThat(hash).hasSize(60);
    }

    @Test
    void rightAndWrongCandidatesAreDistinct() {
        String hash = encoder.encode("demo-candidate");

        assertThat(encoder.matches("demo-candidate", hash)).isTrue();
        assertThat(encoder.matches("wrong-candidate", hash)).isFalse();
    }

    @Test
    void randomSaltMakesNewHashesUsuallyDifferent() {
        String first = encoder.encode("same-password");
        String second = encoder.encode("same-password");

        assertThat(first).isNotEqualTo(second);
        assertThat(encoder.matches("same-password", first)).isTrue();
        assertThat(encoder.matches("same-password", second)).isTrue();
    }

    @Test
    void strongerEncoderCanIdentifyLowerCostHash() {
        String cost12 = encoder.encode("demo-candidate");

        BCryptPasswordEncoder stronger =
            new BCryptPasswordEncoder(13);

        assertThat(stronger.matches("demo-candidate", cost12))
            .isTrue();
        assertThat(stronger.upgradeEncoding(cost12)).isTrue();
    }

    @Test
    void userStoreDoesNotContainRawPassword() {
        String stored = users.loadUserByUsername("reader")
            .getPassword();

        assertThat(stored).isNotEqualTo("reader-demo-password");
        assertThat(stored.substring(4, 6)).isEqualTo("12");
        assertThat(encoder.matches(
            "reader-demo-password", stored)).isTrue();
    }

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk());
    }

    @Test
    void privateEndpointNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void basicCorrectPasswordAuthenticates() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic(
                    "reader", "reader-demo-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("reader"));
    }

    @Test
    void basicWrongPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic(
                    "reader", "incorrect")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void correctPasswordDoesNotGrantAdminRole()
            throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic(
                    "reader", "reader-demo-password")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic(
                    "admin", "admin-demo-password")))
            .andExpect(status().isOk());
    }
}
```

Chạy:

```bash
./gradlew test --tests example.passwordcost.PasswordCostTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.passwordcost.PasswordCostTest
```

**Kỳ vọng:** 10 phương thức test thành công với project Spring Boot 3/Spring Security 6.x đã mô tả và dependencies phù hợp. Đây là kỳ vọng từ code; **chưa phải kết quả chạy test thực tế**. Kiểm thử hai salts/hashes khác nhau dựa trên ngẫu nhiên bảo mật nên có xác suất collision cực nhỏ, không phải bảo đảm tuyệt đối về mặt toán học.

| Nhóm test | Điều được kiểm tra |
| --- | --- |
| Format bcrypt | Cost 12 và encoded hash có metadata |
| `matches` | Password đúng/sai dùng cùng stored hash |
| Hai lần encode | Salt ngẫu nhiên làm encoded hashes thường khác |
| `upgradeEncoding` | Có thể nhận biết hash thấp hơn cost cấu hình mới |
| User store | Không lưu plaintext; khớp password theo encoder |
| HTTP Basic | Filter/provider chấp nhận hoặc từ chối credentials |
| Role admin | Password đúng vẫn cần authorization |

Không có test nào **chứng minh tuyệt đối** “hash không crack được”. Đây là các test chức năng/cấu hình, không phải đánh giá sức mạnh chống một attacker có hạ tầng GPU. Cần review thuật toán, thông số, benchmark, threat model và chính sách vận hành.

### 10.1. Đừng dùng @WithMockUser để test password

`@WithMockUser` tạo một Authentication giả trong test để thử authorization. Nó không đi qua password provider, vì vậy test có thể xanh dù `PasswordEncoder` hoặc hash database cấu hình sai. Với mục tiêu kiểm tra password, dùng `httpBasic(...)`, test form login hoặc gọi `AuthenticationManager.authenticate(...)` qua provider thật.

### 10.2. Không viết unit test dựa trên thời gian tuyệt đối

Không nên:

```java
// Flaky: latency phụ thuộc CPU, JIT, load và môi trường CI.
assertThat(elapsedMilliseconds).isLessThan(100);
```

Dùng benchmark riêng và đo p95/p99 theo môi trường; test chức năng chỉ cần xác minh việc hash đúng định dạng, cost mong muốn, matches đúng/sai và upgrade path.

## 11. Nâng work factor theo thời gian mà không làm user mất mật khẩu

Phần lớn ứng dụng phải giữ password hashes nhiều năm, trong khi cấu hình từng được coi là đủ mạnh có thể trở nên yếu do phần cứng phát triển.

Một chiến lược migration chuẩn:

1. Lưu **algorithm ID, salt, cost và hash** theo format có thể kiểm tra về sau.
2. User login → xác minh password với **tham số đã lưu**, không dùng cost mới áp đặt lên hash cũ.
3. Nếu password đúng, hỏi encoder/policy xem hash có cần upgrade hay không.
4. Nếu cần, tính hash mới từ raw password mà user **vừa nhập hợp lệ**, tạo salt mới và dùng cost mới.
5. Cập nhật DB atomically, kiểm soát concurrent logins/password changes và không ghi log raw password.
6. Xem xét invalidating sessions và giữ audit theo chính sách.
7. Với tài khoản không login lâu, cân nhắc đặt lại mật khẩu hoặc chính sách bắt buộc upgrade phù hợp.
8. Kiểm tra path rollback/đọc hash cũ và khả năng hỗ trợ nhiều định dạng khi deploy rolling updates.

Trong Spring Security, `PasswordEncoder.upgradeEncoding(encodedPassword)` hỗ trợ đánh giá có cần upgrade; `UserDetailsPasswordService` có thể được cấu hình để provider cập nhật encoded password nếu flow hỗ trợ. Chỉ đổi bean `new BCryptPasswordEncoder(12)` sang `new BCryptPasswordEncoder(13)` **không tự ghi lại toàn bộ password hashes trong database**.

### 11.1. Khi nào nên dùng DelegatingPasswordEncoder?

Nếu database có nhiều thế hệ hash như bcrypt, PBKDF2 hoặc Argon2, một hệ thống có thể lưu `{id}encodedPassword` và cấu hình mapping theo version. Nếu chuyển thuật toán mà không có version/prefix/migration, user dùng hash cũ có thể không login được. Đừng xóa/chuyển đổi hàng loạt hash bằng cách “đoán raw password”; hash không có phép decrypt để làm điều đó.

### 11.2. Dữ liệu cần giữ để verify

Ví dụ một record lưu:

```text
user_id = u-100
algorithm = bcrypt
cost = 12
salt = (mã hóa trong bcrypt hash)
storedHash = $2a$12$...
```

Với bcrypt, bản thân encoded string thường đã chứa version/cost/salt/result. Không nhất thiết phải có những cột riêng nếu thư viện dùng format tự mô tả. Với custom PBKDF2, lưu rõ algorithm, iteration count, salt, output length/version để verify hash nhiều đời.

### 11.3. Password mới không cần giống hash cũ

Khi nâng cost, kết quả encoded hash mới thường khác ngay cả khi raw password không đổi vì **salt mới**. Đừng so chuỗi hash mới với hash cũ để kết luận password đã bị thay hoặc user nhập sai. Tính đúng dựa trên `matches`.

## 12. Giới hạn thực tế: phòng vệ nhiều lớp

Một hệ thống có password hash mạnh vẫn có thể bị chiếm tài khoản bởi phishing, credential reuse, malware, email reset bị xâm nhập, session hijacking hoặc lỗi phân quyền.

### 12.1. Đối phó online guessing

- Rate limit theo tín hiệu đáng tin (user/account, IP, device risk) mà không tạo cơ chế lockout bị lạm dụng;
- MFA/passkeys phù hợp và bước xác minh tăng cường khi rủi ro cao;
- Chặn password phổ biến/đã lộ theo chính sách;
- Log sự kiện bảo mật có kiểm soát, không log password/hash/token;
- Dùng thông báo lỗi không tiết lộ user tồn tại;
- TLS, session cookie flags và CSRF protection khi ứng dụng dùng cookie/session;
- Cân nhắc khả năng DoS khi cost cao và đối thủ gửi nhiều login đồng thời.

### 12.2. Đối phó offline cracking

- Chọn Argon2id/scrypt/bcrypt/PBKDF2 phù hợp, **không** lưu MD5/SHA-1/SHA-256 một lần;
- Salt ngẫu nhiên riêng cho mỗi password;
- Cost đủ cao và được benchmark, nâng theo thời gian;
- Kiểm soát quyền đọc cột password_hash, backups và logs;
- Pepper ngoài DB khi threat model/cost vận hành cho phép;
- Password policy hợp lý, chống password đã bị lộ;
- Quy trình ứng phó sự cố DB leak: đánh giá phạm vi, có thể reset passwords, revoke sessions và thông báo theo nghĩa vụ.

### 12.3. Đối phó lỗi phân quyền

Mật khẩu đúng chỉ dẫn tới **authentication**; sau đó ứng dụng còn kiểm tra role, permission và owner/tenant của tài nguyên. Nếu user có quyền `report:read`, điều đó không tự chứng minh họ được đọc báo cáo của tenant khác. Không dùng hash tốt để bỏ qua bước authorization trên từng bản ghi.

## 13. Anti-patterns cần nhận diện

### 13.1. Dùng một salt chung cho mọi account

`private static final String SALT = "my-app-salt";` là cách làm không phù hợp. Một salt dùng chung giúp attacker dùng lại phép tính giữa các accounts và nhận ra password trùng.

### 13.2. Lưu SHA-256(password) thay cho bcrypt/Argon2id

Salt riêng cũng không làm SHA-256 một lần chậm đủ. Dùng password KDF được thiết kế chuyên biệt và cập nhật.

### 13.3. Dùng bcrypt strength thấp không benchmark

Cost thấp khiến offline guessing rẻ hơn; cost quá cao làm login chậm và dễ DoS. Cần chọn dựa trên hardware, lưu lượng và threat model.

### 13.4. Giả định “hash một chiều nên không ai biết password”

Attacker có thể thử candidate offline. Password yếu vẫn dễ đoán hơn password mạnh.

### 13.5. Tự nối salt vào password khi encoder đã xử lý

`encoder.encode(password + salt)` trong khi encoder tự salt làm format khó quản lý và gây lỗi khi verify nếu salt riêng không được lưu/khôi phục nhất quán. Hãy dùng API encoder đúng cách.

### 13.6. Mỗi login lại sinh salt mới để so với stored hash

Nếu tự tạo salt khác lúc verification, kết quả KDF sẽ không khớp. `matches` phải dùng salt/cost của stored record.

### 13.7. Hash lại password bằng encode rồi so String

Bcrypt sinh salt ngẫu nhiên, hai lần encode thường khác nhau. Dùng `PasswordEncoder.matches`.

### 13.8. Hardcode raw password hoặc pepper trong source control

Secret không được commit lên repo. Pepper phải nằm trong secret manager và có kế hoạch rotate. Mật khẩu hardcode trong tài liệu chỉ để học cục bộ.

### 13.9. Log hash hoặc Authorization header

Password hash bị lộ vẫn giúp attacker đoán offline, còn Basic header chứa plaintext có thể khôi phục qua Base64. Không log secrets hoặc hash.

### 13.10. Cho rằng DB encryption thay thế password hashing

Mã hóa at rest có ích bổ sung, nhưng khi kẻ xấu có quyền ứng dụng hoặc key, ciphertext có thể giải mã. Password đăng nhập chỉ cần verifier một chiều.

### 13.11. Bỏ giới hạn concurrent password checks

Argon2id memory-hard có thể tiêu thụ RAM lớn khi nhiều requests đến cùng lúc. Cần rate limiting, resource controls và capacity planning.

### 13.12. Pre-hash bcrypt bằng SHA-256 tùy tiện

Bcrypt có caveat đầu vào 72 byte; việc tự pre-hash password bằng fast hash có thể dẫn tới password shucking hoặc xử lý bytes không đúng. Nếu bắt buộc thiết kế pre-hash, tra khuyến nghị OWASP về HMAC với pepper và kiểm định scheme; không tự sáng chế.

### 13.13. Tưởng cost trong hai thuật toán có thể so trực tiếp

`bcrypt strength=12` không tương đương `Argon2id iterations=12`. Đánh giá memory, passes, CPU, p95 latency và khả năng attacker parallelize.

### 13.14. Không version hash khi đổi thuật toán

Nếu không có metadata/algorithm ID, hệ thống khó verify các hash cũ và nâng cấp an toàn. Dùng format tự mô tả hoặc DelegatingPasswordEncoder.

### 13.15. Tăng cost nhưng không cân nhắc tài khoản không login

Những hash cũ có thể nằm trong DB lâu dài vì không có raw password để rehash. Cần chính sách reset/migration phù hợp.

### 13.16. Cho rằng salt tăng độ khó đoán của raw password

Salt không thay entropy bí mật user chọn. Nó ngăn attacker tái sử dụng phép tính; với password cực yếu attacker vẫn có thể đoán candidate phổ biến.

### 13.17. Đặt timeout benchmark thành test pass/fail mọi nơi

Thời gian hash phụ thuộc máy, load và JIT. Dùng benchmark có phương pháp; unit/integration test không nên lệ thuộc một ngưỡng milliseconds bất biến.

### 13.18. Chỉ thử mật khẩu đúng, quên thử sai và disabled

Phải test đường thất bại của authentication và account status, không chỉ happy path. Một hash đúng format không chứng minh service đã từ chối những mật khẩu không hợp lệ.

## 14. Checklist triển khai và đánh giá

**Thiết kế password storage**

- Có dùng password KDF chuyên dụng thay SHA-256 một lần/MD5/NoOp?
- Salt ngẫu nhiên riêng cho từng hash, do CSPRNG/library uy tín tạo?
- Salt/algorithm/cost được lưu đủ để verify ở những phiên bản sau?
- Tham số CPU/bộ nhớ được benchmark trên server thật?
- Không dùng chung salt, không giấu salt như secret?
- Password hash, backups và logs được bảo vệ?
- Pepper nếu có được quản lý ngoài DB và có chiến lược rotation?
- Bcrypt limit 72 byte, Unicode và độ dài password được xử lý theo implementation?
- Có kế hoạch migration khi tăng cost/đổi thuật toán?

**Luồng login**

- `UserDetailsService` tải hash và authorities, không nhận raw password để tự so?
- `DaoAuthenticationProvider` và `PasswordEncoder.matches` xác minh password đúng?
- Account disabled/locked được từ chối?
- Username không tồn tại và password sai không tiết lộ quá mức?
- Không so `encode(raw).equals(stored)`?
- Rate limiting và MFA/passkeys theo rủi ro?
- Sử dụng HTTPS, bảo vệ session/token và CSRF theo threat model?
- Giới hạn đồng thời, monitoring CPU/RAM để tránh DoS?

**Đảm bảo chất lượng**

- Test salt ngẫu nhiên: hai encoded hashes thường khác nhau và cả hai matches đúng?
- Test cost: hash format chứa mức cấu hình?
- Test `upgradeEncoding` cho hash đời cũ?
- Test password đúng/sai, 401 chưa login và 403 thiếu role?
- Đo latency p50/p95/p99 với phiên bản JDK/provider và máy production?
- Kiểm tra tình huống DB leak và backup access trong threat model?
- Có cơ chế account password reset, revocation và audit?
- Không công bố các con số “thời gian crack” không có điều kiện đo/threat model?

## 15. Câu hỏi tự kiểm tra và đáp án

**1.** Salt có cần bí mật không?  
Không. Salt thường lưu cùng hash, vì chức năng chính là làm mỗi password có đầu vào/đầu ra riêng.

**2.** Salt có làm cho một lượt SHA-256 trở nên chậm không?  
Không. Thêm salt không làm SHA-256 một lần thành password hashing chậm.

**3.** Cùng password, hai salt khác nhau sẽ tạo gì?  
Hai hashes khác nhau với xác suất áp đảo khi KDF đúng.

**4.** Vì sao random salt làm rainbow table kém hữu ích?  
Vì bảng tính sẵn cho salt này không dùng trực tiếp cho salt khác; attacker phải tính cho salt cụ thể.

**5.** Work factor chủ yếu bảo vệ trước nguy cơ nào?  
Tăng chi phí tính cho mỗi candidate, đặc biệt khi attacker dò ngoại tuyến từ hash đã lộ.

**6.** bcrypt cost 10 lên 12 tương đương tăng thế nào?  
Khối lượng công việc theo quy tắc `2^cost` tăng khoảng `4` lần; wall-clock còn phụ thuộc overhead và phần cứng.

**7.** Argon2id có những tham số quan trọng nào?  
`m` (memory), `t` (passes), `p` (parallelism).

**8.** Vì sao không so Argon2id t=2 với bcrypt cost=12 theo số lớn/nhỏ?  
Chúng đo các loại cost khác nhau, phải dựa trên tham số và benchmark cụ thể.

**9.** `PasswordEncoder.matches` cần dữ liệu gì?  
Raw password candidate và encoded hash chứa hoặc liên kết tới salt/cost/algorithm đúng.

**10.** Tại sao `encoder.encode(raw).equals(stored)` thường sai?  
Lượt encode mới dùng salt mới, nên hash mới không giống hash đã lưu dù raw giống nhau.

**11.** Pepper khác salt thế nào?  
Pepper là secret ngoài DB, salt không bí mật và thường riêng từng hash.

**12.** Nếu attacker chỉ có database và hash, rate limiting login có ngăn họ thử offline không?  
Không, bởi họ chạy KDF trên máy riêng, không gửi requests tới server.

**13.** Vì sao work factor quá cao có thể tăng rủi ro DoS?  
Mỗi login request tiêu thụ nhiều CPU/RAM, attacker có thể gửi nhiều request đồng thời.

**14.** Có thể lấy password gốc bằng cách giải mã password hash không?  
Không có decrypt API. Attacker có thể thử đoán, còn người dùng cần password reset khi quên.

**15.** Khi tăng bcrypt strength, toàn bộ hash cũ tự đổi không?  
Không. Phải có login-time rehash/migration hoặc reset strategy.

**16.** Nếu database chứa hash mạnh bị lộ, có chắc mọi password an toàn?  
Không. Password yếu vẫn có thể bị đoán, dù mỗi lần thử đã tốn chi phí hơn.

**17.** Với HTTP Basic, password hashing có bảo vệ đường truyền không?  
Không. Basic dùng Base64; dùng TLS/HTTPS và bảo vệ secret trên client.

**18.** Khi test performance, có nên assert tất cả hash dưới 100 ms không?  
Không có ngưỡng cố định cho mọi máy; dùng benchmark, đánh giá latency và concurrency theo môi trường.

## 16. Tài liệu tham khảo

- [OWASP – Password Storage Cheat Sheet: salting, work factor, Argon2id, bcrypt, PBKDF2](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [Spring Security 6.5 – Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security – PasswordEncoder Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security – BCryptPasswordEncoder Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html)
- [Spring Security 6.5 – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security – Argon2PasswordEncoder Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/argon2/Argon2PasswordEncoder.html)
- [OWASP – Authentication Cheat Sheet: chống thử mật khẩu trực tuyến](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [NIST SP 800-63B – Authentication và bảo vệ memorized secrets](https://pages.nist.gov/800-63-4/sp800-63b.html)
- [Java 17 – JCA Reference Guide: PBKDF2, SecureRandom](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html)
