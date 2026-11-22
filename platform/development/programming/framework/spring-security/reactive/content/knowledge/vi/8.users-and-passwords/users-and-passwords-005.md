# Băm mật khẩu với BCrypt, Argon2 và lựa chọn chi phí tính toán

## Mục tiêu của bài học

Trong ứng dụng Spring Security Reactive, việc xác thực username/password không chỉ là so sánh hai chuỗi. Hệ thống cần **xác minh mật khẩu từ bản băm một chiều**, sử dụng thuật toán có salt và chi phí tính toán được lựa chọn có chủ đích. BCrypt và Argon2id đều hướng tới việc làm cho việc thử hàng loạt mật khẩu trở nên tốn kém; tuy nhiên chúng có mô hình chi phí và đặc điểm triển khai khác nhau.

Sau bài này, bạn có thể:

1. Phân biệt password hashing với mã hóa có thể giải mã, hashing dữ liệu thông thường và lưu mật khẩu dạng plaintext.
2. Giải thích salt, work factor, cost và vì sao cùng một mật khẩu có thể tạo các hash khác nhau.
3. Dùng `BCryptPasswordEncoder` và `Argon2PasswordEncoder` của Spring Security để `encode`/`matches` đúng cách.
4. Giải thích cost của BCrypt và ba tham số `memory`/`iterations`/`parallelism` của Argon2id; hiểu giới hạn bcrypt 72 byte.
5. Dùng `DelegatingPasswordEncoder` để nhận cả hash cũ và hash mới có tiền tố `{id}`, rồi thiết kế nâng cấp hash khi người dùng đăng nhập thành công.
6. Chọn thông số bằng đo đạc trên hạ tầng thực, tính cả độ trễ đăng nhập, tài nguyên đồng thời, khả năng chống brute-force và nguy cơ denial of service.
7. Tạo ứng dụng Spring WebFlux Java 17+ với tài khoản mẫu dùng **hai thuật toán**, kiểm chứng xác thực qua HTTP và test tự động.

Bài thuộc chủ đề **Người dùng và mật khẩu** của **Spring Security – Reactive**. Phần Java sử dụng Spring Boot 3.x, Spring Security 6.x, Java 17+ và Gradle. Những giá trị cost trong ví dụ là **cấu hình thực hành cần benchmark lại**, không phải khuyến nghị bất biến cho mọi hệ thống.

## 1. Vì sao không được lưu mật khẩu dạng rõ?

Người dùng gửi mật khẩu trong luồng đăng ký hoặc đăng nhập. Hệ thống cần biết credential họ nhập có khớp credential đã thiết lập trước đó hay không, nhưng về nguyên tắc **không cần khả năng khôi phục mật khẩu gốc**.

Cách lưu sai:

```text
username | password
alice    | MyStrongPass!2026
bob      | AnotherPassword!
```

Nếu database, backup, file log hoặc bản export lộ ra ngoài, mọi mật khẩu dạng rõ lập tức bị lộ; người dùng còn có thể tái sử dụng chúng ở dịch vụ khác.

Cách lưu đúng về mặt nguyên tắc:

```text
username | password_hash
alice    | {bcrypt}$2a$12$<salt-and-hash-bytes>
bob      | {argon2@SpringSecurity_v5_8}$argon2id$v=19$m=16384,t=2,p=1$...
```

Các chuỗi trên chỉ **minh họa định dạng**, không phải hash hợp lệ để xác thực. Dấu `<...>` chỉ chỗ mô tả, không dùng làm dữ liệu thật. Phần `{bcrypt}` hoặc `{argon2@SpringSecurity_v5_8}` là **tiền tố định tuyến encoder của Spring Security**, còn chuỗi `$2a$...` hoặc `$argon2id$...` là format của thuật toán. Giá trị hash thật do `PasswordEncoder.encode(...)` tạo, có salt ngẫu nhiên.

### 1.1. Hash một chiều không phải encryption

- **Encryption** dùng khóa và có thiết kế giải mã; phù hợp dữ liệu cần lấy lại nguyên văn.
- **Password hash** dùng thuật toán xác minh mật khẩu chậm có chủ đích, giữ salt và tham số kiểm tra; không có hàm “giải mã” trả password.
- **Digest nhanh** như SHA-256, MD5 hoặc SHA-1 áp dụng một lần không phải password storage design an toàn. Chúng được thiết kế tính toán nhanh, khiến kẻ tấn công có thể thử rất nhiều mật khẩu mỗi giây sau khi đánh cắp database.
- **Salt** không phải mật khẩu bí mật. Salt cần được tạo ngẫu nhiên cho mỗi hash và thường được lưu ngay trong chuỗi hash. Hai user dùng cùng raw password vẫn nhận hai hash khác nhau, giảm hiệu quả bảng băm dựng sẵn và việc nhận diện hai người có cùng mật khẩu.
- **Pepper** là một giá trị bí mật cấp hệ thống dùng bổ sung trong một số threat model; nó **không thay salt**, cần quản lý qua secret store/HSM/KMS và có chiến lược thay khóa. Không hardcode pepper vào source hoặc log.

### 1.2. Quy trình đăng ký và đăng nhập

```text
Đăng ký:
  raw password
    -> PasswordEncoder.encode(raw)
    -> hash gồm thuật toán, tham số, salt, digest
    -> lưu hash vào database

Đăng nhập:
  username + raw password người dùng vừa nhập
    -> tìm stored hash theo username
    -> PasswordEncoder.matches(raw, storedHash)
    -> true / false
    -> Spring Security quyết định Authentication
    -> application dùng Authentication đã xác thực để phân quyền
```

**Không** thực hiện `encoder.encode(raw).equals(storedHash)`. Vì mỗi lần `encode` thường sinh salt ngẫu nhiên, hash mới có thể khác hash cũ dù raw password giống hệt. `matches` đọc thông tin được nhúng trong hash cũ, thực hiện phép kiểm tra đúng thuật toán và trả boolean.

## 2. BCrypt: work factor theo cấp số mũ

BCrypt là password hashing scheme lâu đời, được triển khai rộng rãi. Spring Security cung cấp `org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder`.

Ví dụ:

```java
PasswordEncoder bcrypt = new BCryptPasswordEncoder(12);

String hash1 = bcrypt.encode("sample-password");
String hash2 = bcrypt.encode("sample-password");

boolean correct = bcrypt.matches("sample-password", hash1);
boolean wrong = bcrypt.matches("different-password", hash1);
boolean sameHash = hash1.equals(hash2);
```

Mảnh code trên dùng import `PasswordEncoder` và `BCryptPasswordEncoder`. Kết quả dự kiến:

```text
correct == true
wrong == false
sameHash == false   (với các salt ngẫu nhiên độc lập)
```

Mỗi hash BCrypt thông thường có dạng `$2a$12$...`, `$2b$...` hoặc biến thể tương ứng với implementation. Hai chữ số như `12` mang cost factor; hash còn chứa salt và dữ liệu băm. Đừng trích riêng phần sau dấu `$` rồi cất ở các cột tách rời trừ khi có yêu cầu tương thích được kiểm chứng.

### 2.1. Chi phí `strength`

`new BCryptPasswordEncoder(strength)` nhận work factor của BCrypt. Với `strength = 12`, lượng công việc lõi tăng theo mô hình xấp xỉ `2^12` vòng tương ứng. Tăng cost 1 đơn vị thường làm chi phí băm tăng khoảng gấp đôi; tăng từ 10 lên 12 thường tốn khoảng bốn lần, **không** khẳng định thời gian tuyệt đối trên mọi CPU.

Ví dụ so sánh tương đối:

| BCrypt strength | Cost lõi tương đối so với 10 | Ý nghĩa |
|---:|---:|---|
| 10 | 1× | Mốc tham chiếu minh họa |
| 11 | 2× | Khoảng gấp đôi công việc |
| 12 | 4× | Khoảng bốn lần |
| 13 | 8× | Khoảng tám lần |
| 14 | 16× | Có thể gây áp lực khi đăng nhập đồng thời |

Các tỷ lệ trên là **quan hệ mô hình công việc**, không phải phép đo SLA. Bộ xử lý, JVM warmup, phiên bản thư viện, tốc độ CPU, throttling trong container và tải đồng thời đều ảnh hưởng latency thực.

Strength quá thấp làm kẻ tấn công thử mật khẩu nhanh hơn. Strength quá cao làm **máy chủ của chính bạn** phải làm nhiều công việc mỗi lần đăng nhập, có thể tạo điểm nghẽn/DoS. Quyết định cần benchmark và kiểm soát tần suất đăng nhập, không tối đa hóa số strength.

### 2.2. Giới hạn đầu vào 72 byte của BCrypt

BCrypt truyền thống có giới hạn xử lý password khoảng **72 byte**, không phải 72 ký tự Java hay 72 ký tự Unicode. Một ký tự tiếng Việt hoặc emoji có thể chiếm nhiều byte trong UTF-8. Các implementation có thể cắt phần vượt giới hạn hoặc có hành vi kiểm soát riêng; không nên giả định mọi độ dài password được kiểm chứng đầy đủ.

Ví dụ: nếu policy cho phép passphrase dài, phải kiểm tra giới hạn **theo byte sau khi mã hóa**, hành vi thực tế của encoder đang dùng và chiến lược tương thích. Không tự thêm bước SHA-256 rồi đưa digest vào BCrypt mà chưa có thiết kế an toàn, kiểm định và quy tắc migration: pre-hashing tùy tiện có thể mở ra các bẫy về encoding, null byte và đổi semantics.

Đối với hệ thống mới cần password dài linh hoạt và có năng lực cấp bộ nhớ phù hợp, Argon2id là lựa chọn đáng xem xét.

### 2.3. Salt ngẫu nhiên và xác minh

Salt BCrypt thường được lưu cùng hash, không cần cột `salt` riêng để `matches` hoạt động. Với cùng một mật khẩu:

```java
String a = bcrypt.encode("secret");
String b = bcrypt.encode("secret");

assert bcrypt.matches("secret", a);
assert bcrypt.matches("secret", b);
assert !a.equals(b);
```

`assert` ở đây minh họa ý tưởng; trong test tự động nên dùng JUnit assertions rõ ràng, không dựa vào Java `assert` có thể bị vô hiệu khi chạy mà không bật `-ea`.

## 3. Argon2id: kết hợp chi phí thời gian và bộ nhớ

Argon2 là họ thuật toán băm mật khẩu hiện đại. **Argon2id** phối hợp các đặc tính chống tấn công side-channel của Argon2i và tính khó song song hóa với ít bộ nhớ của Argon2d; nó thường được chọn cho password hashing. Spring Security cung cấp `org.springframework.security.crypto.argon2.Argon2PasswordEncoder` với định dạng Argon2id trong các bản 6.x.

Ví dụ encoder dùng cấu hình do Spring Security cung cấp:

```java
PasswordEncoder argon2 =
    Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();

String hash = argon2.encode("sample-password");

boolean ok = argon2.matches("sample-password", hash);
boolean bad = argon2.matches("wrong", hash);
```

Kết quả:

```text
ok == true
bad == false
```

Hash Argon2id thường có dạng PHC string:

```text
$argon2id$v=19$m=16384,t=2,p=1$<salt-base64>$<hash-base64>
```

Đây là **minh họa format**, không phải hash thật. `m` là memory cost (đơn vị KiB), `t` là số lượt (iterations/passes), `p` là mức song song (lanes). Giá trị có thể khác theo constructor, version hoặc cấu hình bạn chọn; hãy kiểm tra hash do ứng dụng thực tế tạo.

### 3.1. Ba tham số và ảnh hưởng

| Tham số | Ý nghĩa | Đánh đổi |
|---|---|---|
| `memory`/`m` | Bộ nhớ cấp cho một lần hashing, thường tính bằng KiB | Tăng memory cost làm tăng yêu cầu RAM cho mỗi phép thử; nếu nhiều request cùng chạy, tổng RAM có thể tăng mạnh |
| `iterations`/`t` | Số lượt xử lý trên vùng nhớ | Tăng thời gian CPU và thường cả thời gian giữ RAM |
| `parallelism`/`p` | Số lane/khả năng chia công việc song song | Có thể thay đổi latency và phân bố CPU tùy implementation, không đồng nghĩa luôn dùng đúng `p` Java threads |
| `saltLength` | Số byte salt ngẫu nhiên mỗi hash | Nên đủ lớn, do encoder cấp phát |
| `hashLength` | Độ dài kết quả hash | Thường giữ mặc định/phù hợp tiêu chuẩn |

Khác BCrypt chủ yếu phụ thuộc CPU, Argon2id được thiết kế **memory-hard**, tức là thử mật khẩu với tài nguyên bộ nhớ ít hơn đáng kể sẽ có chi phí bổ sung. Điều này giúp tăng giá thành tấn công trên GPU/ASIC, nhưng cũng yêu cầu bạn cấp đủ RAM và kiểm soát concurrency trên hệ thống xác thực của mình.

### 3.2. Constructor tham số tường minh

Trong Spring Security 6.x, constructor phổ biến có thứ tự:

```java
Argon2PasswordEncoder tuned = new Argon2PasswordEncoder(
    16,       // saltLength: byte
    32,       // hashLength: byte
    1,        // parallelism
    65536,    // memory: KiB = 64 MiB
    3         // iterations
);
```

Đây là **cấu hình để thực nghiệm**, không phải mặc định bắt buộc và chưa phải thông số sản xuất đã được benchmark. Với `m=65536` KiB, mỗi phép tính có yêu cầu vùng nhớ cỡ 64 MiB, ngoài overhead của JVM/implementation. Khi 50 request phải băm cùng lúc, **riêng phép nhân 50 × 64 MiB đã xấp xỉ 3,2 GiB**, chưa tính heap/native memory khác và các chi tiết implementation. Thông số “mạnh hơn” có thể làm cạn bộ nhớ hoặc khiến máy chủ không đáp ứng được login hợp pháp.

Một lựa chọn bắt đầu để hiểu API là:

```java
Argon2PasswordEncoder defaults =
    Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();
```

Tên method chứa `v5_8` để gắn với bộ default được định nghĩa ở thời điểm Spring Security 5.8. Không hiểu `v5_8` là bản Argon2 hoặc khóa mã hóa; nó là tên profile default của thư viện. Hãy xem `m,t,p` từ hash thực để biết các tham số được dùng, thay vì suy luận tên method là “tối ưu mới nhất”.

### 3.3. Dependency Bouncy Castle

Spring Security sử dụng Bouncy Castle cho `Argon2PasswordEncoder` ở dòng thư viện 6.x. Nếu project thiếu provider tương ứng, lúc encode/matches có thể gặp lỗi class không tồn tại hoặc lỗi khởi tạo.

Với Gradle, thêm một phiên bản Bouncy Castle tương thích đã được phê duyệt với BOM/policy dependency của project. Ví dụ để chạy demo này:

```groovy
implementation 'org.bouncycastle:bcprov-jdk18on:1.78.1'
```

Đây là **phiên bản ví dụ cụ thể**, không phải khẳng định bản mới nhất của Bouncy Castle. Khi nâng Spring Security/JDK, cần xem release notes, CVE và dependency resolution của chính project, cập nhật dependency đã kiểm thử. Không tự thay class provider hoặc lấy mã hóa tự viết.

## 4. BCrypt hay Argon2id: so sánh theo threat model

| Tiêu chí | BCrypt | Argon2id |
|---|---|---|
| Độ phổ biến trong hệ thống cũ | Rất rộng, nhiều hash có sẵn | Phù hợp hệ thống mới và migration có kiểm soát |
| Đầu vào | Giới hạn truyền thống 72 byte cần lưu ý | Hỗ trợ passphrase dài linh hoạt theo implementation |
| Chi phí chủ yếu | CPU, điều khiển bằng logarithmic strength | CPU + RAM, điều khiển m/t/p |
| Khả năng làm khó thử mật khẩu song song | Có; điều chỉnh bằng work factor | Memory-hard, có thêm chiều kiểm soát RAM |
| Resource cần tính toán ở production | CPU latency/concurrency | CPU + RAM + concurrency |
| Vận hành trên hạ tầng RAM hạn chế | Thường dễ dự đoán RAM hơn | Phải tính cấp phát bộ nhớ và khả năng bùng nổ concurrent requests |
| Tương thích hash cũ | Có thể tiếp tục verify | Có thể dùng `DelegatingPasswordEncoder` nhận hash cũ khi chuyển thuật toán |

Không có câu trả lời “mọi hệ thống phải dùng Argon2id mức X” hoặc “BCrypt 10 đủ an toàn vĩnh viễn”. Chọn lựa phụ thuộc bản chất password của người dùng, CPU/RAM thực tế, ngân sách tài nguyên cho xác thực, khả năng chống tấn công credential stuffing và yêu cầu compliance. Argon2id thường là lựa chọn đáng ưu tiên cho hệ thống mới nếu vận hành và thư viện cho phép; BCrypt vẫn hợp lý để duy trì hash hiện có và nâng dần cost theo kết quả benchmark.

### 4.1. Một trường hợp quyết định

Giả sử cụm auth có nhiều đăng nhập đồng thời và hạn mức RAM mỗi container thấp. Dùng Argon2id với 64 MiB/verification trong một endpoint công khai có thể gây out-of-memory dưới tải cao, ngay cả trước khi tính heap và những request khác. Một cấu hình Argon2id có `m` thấp hơn nhưng đủ thời gian `t`, hoặc BCrypt với cost thích hợp, **cộng với rate limiting, quota concurrency và cấu trúc tài nguyên hợp lý**, có thể bảo vệ hệ thống vận hành tốt hơn.

Ngược lại, khi có đủ RAM, kiểm soát số lượng phép thử đồng thời và mong muốn chống việc crack mật khẩu ngoài hệ thống, cấu hình Argon2id memory-hard là một lợi thế. Không bỏ qua logging/monitoring và backpressure chỉ vì chọn thuật toán mạnh.

## 5. API PasswordEncoder của Spring Security

Giao diện trung tâm:

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

Đây là chữ ký **rút gọn dùng để học**, không phải interface cần tự định nghĩa. Phương thức `upgradeEncoding` cho phép encoder thông báo hash hiện tại cần được tái mã hóa theo cấu hình mới (khi implementation hỗ trợ). Việc method trả `true` không tự cập nhật database.

Để verify mật khẩu, **không** dùng:

```java
String encoded = encoder.encode(rawPassword);
return encoded.equals(storedHash);  // Sai: salt khác nhau
```

Đúng:

```java
return encoder.matches(rawPassword, storedHash);
```

Luồng code phải tránh log `rawPassword`, không đưa hash vào HTTP response, không lưu hash trong URL. Encoder cần truy cập đúng giá trị đã lưu. Không trim, lowercase hoặc normalize mật khẩu sau khi đăng ký theo những quy tắc bất nhất: thay đổi một ký tự có thể thay đổi kết quả băm.

## 6. Lưu nhiều định dạng trong cùng hệ thống bằng DelegatingPasswordEncoder

Khi chuyển từ BCrypt sang Argon2id, không thể “biến” hash BCrypt cũ thành Argon2id mà **không biết raw password**. Vì hash một chiều, bạn cần giữ khả năng verify BCrypt cho tới khi người dùng đăng nhập lại/đổi mật khẩu. Spring Security cung cấp `DelegatingPasswordEncoder` cho phép mỗi chuỗi hash mang tiền tố `{id}`:

```text
{bcrypt}$2a$12$...
{argon2@SpringSecurity_v5_8}$argon2id$v=19$m=16384,t=2,p=1$...
```

Đây là format minh họa; mỗi hash thật có salt và dữ liệu digest hợp lệ.

### 6.1. Ánh xạ id → encoder

```java
Map<String, PasswordEncoder> encoders = new HashMap<>();

encoders.put(
    "bcrypt",
    new BCryptPasswordEncoder(12)
);

encoders.put(
    "argon2@SpringSecurity_v5_8",
    Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8()
);

PasswordEncoder delegating = new DelegatingPasswordEncoder(
    "argon2@SpringSecurity_v5_8",
    encoders
);
```

Đoạn này có import `java.util.Map`, `HashMap`, Spring `PasswordEncoder`, `DelegatingPasswordEncoder`, `BCryptPasswordEncoder` và `Argon2PasswordEncoder`; class chạy đầy đủ ở mục 7.

- `idForEncode` là `"argon2@SpringSecurity_v5_8"`: khi `delegating.encode(raw)`, hash mới được lưu với prefix của id đó.
- Khi `delegating.matches(raw, "{bcrypt}...")`, delegate chọn BCrypt để xác minh legacy hash.
- Khi `delegating.matches(raw, "{argon2@SpringSecurity_v5_8}...")`, delegate chọn Argon2 encoder đúng profile.
- Nếu gặp id không hỗ trợ, đừng tự fallback sang `NoOpPasswordEncoder` hoặc mặc định coi mật khẩu đúng. Thiết kế migration phải phát hiện và xử lý rõ chuỗi hash cũ thiếu id/format lạ.

**Chú ý tên id:** `{argon2}` và `{argon2@SpringSecurity_v5_8}` là hai id khác nhau trong hệ thống delegation. Cùng là Argon2id nhưng chúng có thể gắn với profile thông số Spring Security khác nhau. Nếu database chứa cả hai dạng, cần map cả hai tới encoder tương ứng và test kỹ. Không tự đổi chuỗi prefix của hash cũ bằng thao tác text mà chưa verify/migration chính xác.

### 6.2. Vì sao không dùng NoOpPasswordEncoder?

`NoOpPasswordEncoder` chỉ tương thích plaintext trong một số tình huống migration có kiểm soát; không thích hợp để lưu credential production. Bật fallback `defaultPasswordEncoderForMatches` về NoOp để “sửa lỗi id thiếu” có thể khiến một chuỗi nguy hiểm được diễn giải là mật khẩu gốc. Nếu có legacy format trần `$2a$...` không có `{bcrypt}`, hãy viết migration được kiểm thử và đánh dấu format đúng sau khi xác minh, không tự mặc định mọi dữ liệu không nhận ra đều hợp lệ.

## 7. Demo Spring WebFlux chạy được: hai tài khoản, hai thuật toán

Chúng ta sẽ tạo một ứng dụng WebFlux có:

- `GET /me`: yêu cầu HTTP Basic authentication và trả username đã xác thực.
- User `legacy`: hash BCrypt với cost 12, lưu kèm prefix `{bcrypt}`.
- User `modern`: hash Argon2id dùng profile `v5_8`, lưu kèm prefix `{argon2@SpringSecurity_v5_8}`.
- `DelegatingPasswordEncoder`: xác minh cả hai kiểu trong cùng một ứng dụng.
- `WebTestClient`: test xác thực đúng, sai và trường hợp chưa gửi mật khẩu.

**Đây là demo học tập:** credentials mẫu cố ý nằm trong mã nguồn và user store in-memory; không dùng chúng trong production, không mở endpoint đăng ký/hiển thị hash.

### 7.1. Tạo project và dependencies

Tạo project bằng [Spring Initializr](https://start.spring.io/) với Gradle, Java 17+, Spring Boot 3.x và dependencies:

- Spring Reactive Web: `spring-boot-starter-webflux`
- Spring Security: `spring-boot-starter-security`
- Spring Boot Starter Test: `spring-boot-starter-test`
- Spring Security Test: `spring-security-test`

Bổ sung Bouncy Castle. Phần `dependencies` trong `build.gradle` do Initializr tạo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.bouncycastle:bcprov-jdk18on:1.78.1'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Đây là **khối dependencies**, không phải toàn bộ file Gradle. Giữ plugin Spring Boot, repositories, dependency management và Java toolchain do Initializr sinh. Không thêm `spring-boot-starter-web`: khi cả starter MVC và WebFlux có mặt, Spring Boot 3.x thường chọn inbound Servlet/MVC theo mặc định, làm thay đổi security pipeline.

Bố cục:

```text
src/main/java/demo/passwordcost/
  PasswordCostApplication.java
  PasswordSecurityConfig.java
  MeController.java
src/test/java/demo/passwordcost/
  PasswordIntegrationTests.java
  EncoderBehaviorTests.java
```

### 7.2. `PasswordCostApplication.java`

```java
package demo.passwordcost;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasswordCostApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasswordCostApplication.class, args);
    }
}
```

### 7.3. `PasswordSecurityConfig.java`

```java
package demo.passwordcost;

import java.util.HashMap;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.argon2.Argon2PasswordEncoder;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class PasswordSecurityConfig {

    @Bean
    public PasswordEncoder passwordEncoder() {
        Map<String, PasswordEncoder> encoders = new HashMap<>();
        encoders.put("bcrypt", new BCryptPasswordEncoder(12));
        encoders.put(
            "argon2@SpringSecurity_v5_8",
            Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8()
        );
        return new DelegatingPasswordEncoder(
            "argon2@SpringSecurity_v5_8",
            encoders
        );
    }

    @Bean
    public MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        // Mã nguồn chỉ phục vụ thực hành, không giữ plaintext trong production.
        UserDetails legacy = User.withUsername("legacy")
            .password("{bcrypt}" +
                new BCryptPasswordEncoder(12).encode("legacy-pass"))
            .roles("USER")
            .build();

        UserDetails modern = User.withUsername("modern")
            .password(encoder.encode("modern-pass"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(legacy, modern);
    }

    @Bean
    public ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {
        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager manager) {
        return http
            .authenticationManager(manager)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**Diễn giải cấu hình:**

1. `PasswordEncoder` là `DelegatingPasswordEncoder`. Hash **mới** dùng Argon2id, nhưng hash BCrypt có prefix vẫn được xác minh.
2. Hai `UserDetails` không lưu plaintext ở thuộc tính password; encoder tạo hash khi khởi động. Salt mới được tạo mỗi lần ứng dụng chạy, nên đừng so sánh hai lần khởi động bằng chuỗi hash tuyệt đối.
3. `MapReactiveUserDetailsService` phù hợp cho demo và test; production dùng account repository và lifecycle phù hợp.
4. `UserDetailsRepositoryReactiveAuthenticationManager` được tạo tường minh với `ReactiveUserDetailsService` rồi gọi `setPasswordEncoder(encoder)`; việc này làm rõ encoder nào tham gia so khớp cả hai hash.
5. `ServerHttpSecurity.authenticationManager(manager)` sử dụng manager đã cấu hình cho WebFlux security chain.
6. `authorizeExchange` yêu cầu authentication cho `/me`, từ chối route khác trong demo, `httpBasic` để curl test và tắt form login để API không redirect tới trang HTML.
7. Password hashing là **cơ chế xác thực credential**, không phải cơ chế gán quyền. `.roles("USER")` tạo authority `ROLE_USER`; bài này chỉ yêu cầu `authenticated()`. Trong ứng dụng thật, phải thiết kế authorization riêng cho dữ liệu người dùng.

### 7.4. `MeController.java`

```java
package demo.passwordcost;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MeController {

    @GetMapping("/me")
    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .map(name -> "hello " + name);
    }
}
```

`ReactiveSecurityContextHolder` đọc context từ Reactor subscription của HTTP request sau khi Spring Security xác thực. Không dùng `SecurityContextHolder.getContext()` kiểu thread-local mặc định để suy đoán principal ở WebFlux.

### 7.5. Chạy và kiểm chứng bằng HTTP

Từ thư mục root của project Gradle:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

Khi server lắng nghe ở `localhost:8080`, dùng terminal khác:

```bash
curl -i http://localhost:8080/me
curl -i -u legacy:legacy-pass http://localhost:8080/me
curl -i -u modern:modern-pass http://localhost:8080/me
curl -i -u legacy:wrong-pass http://localhost:8080/me
```

Trong Windows PowerShell, có thể dùng `curl.exe` để tránh alias `curl`. Kỳ vọng:

| Request | HTTP status | Body khi thành công |
|---|---:|---|
| `GET /me` không credential | `401` | Không yêu cầu body cố định |
| `GET /me` với legacy | `200` | `hello legacy` |
| `GET /me` với modern | `200` | `hello modern` |
| `GET /me` với password sai | `401` | Không yêu cầu body cố định |

Header `WWW-Authenticate`, body lỗi và log có thể khác nhau giữa phiên bản/cấu hình. HTTP Basic chỉ Base64-encode credential, **không mã hóa đường truyền**; chỉ dùng qua HTTPS trong production. Việc cả legacy và modern đăng nhập được chứng minh `DelegatingPasswordEncoder` nhận cả hai định dạng, không phải chứng minh chúng có cùng cost.

## 8. Kiểm thử hoạt động encoder và HTTP chain

### 8.1. Integration tests bằng WebTestClient

Tạo `src/test/java/demo/passwordcost/PasswordIntegrationTests.java`:

```java
package demo.passwordcost;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class PasswordIntegrationTests {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousCannotAccessProfile() {
        client.get().uri("/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void bcryptLegacyHashCanAuthenticate() {
        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("legacy", "legacy-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("hello legacy");
    }

    @Test
    void argon2ModernHashCanAuthenticate() {
        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("modern", "modern-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("hello modern");
    }

    @Test
    void incorrectPasswordIsRejected() {
        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("legacy", "wrong-pass"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Đây là test HTTP qua server được khởi động tại cổng ngẫu nhiên. Nó kiểm tra cả request authentication và WebFlux security chain, không chỉ gọi `matches` ở unit test. Không hardcode thời gian hashing vào assertion; máy tính CI có hiệu năng khác máy local.

### 8.2. Encoder unit tests, salt và upgrade flag

Tạo `src/test/java/demo/passwordcost/EncoderBehaviorTests.java`:

```java
package demo.passwordcost;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class EncoderBehaviorTests {

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    MapReactiveUserDetailsService users;

    @Test
    void newHashesUseArgon2AndRandomSalt() {
        String first = encoder.encode("a-demo-password");
        String second = encoder.encode("a-demo-password");

        assertTrue(first.startsWith(
            "{argon2@SpringSecurity_v5_8}$argon2id$"));
        assertTrue(second.startsWith(
            "{argon2@SpringSecurity_v5_8}$argon2id$"));
        assertNotEquals(first, second);
        assertTrue(encoder.matches("a-demo-password", first));
        assertFalse(encoder.matches("wrong", first));
    }

    @Test
    void legacyBcryptRemainsVerifiableAndCanBeFlaggedForUpgrade() {
        String oldHash = users.findByUsername("legacy")
            .block().getPassword();

        assertTrue(oldHash.startsWith("{bcrypt}"));
        assertTrue(encoder.matches("legacy-pass", oldHash));
        assertTrue(encoder.upgradeEncoding(oldHash));
    }

    @Test
    void wrongPasswordMustNeverMatch() {
        String modernHash = users.findByUsername("modern")
            .block().getPassword();

        assertTrue(encoder.matches("modern-pass", modernHash));
        assertFalse(encoder.matches("legacy-pass", modernHash));
    }
}
```

`.block()` xuất hiện **chỉ trong JUnit test** để đọc `UserDetails` từ reactive user store, không đặt trong WebFlux handler/event-loop. Test này không yêu cầu kiểm tra chuỗi hash tuyệt đối vì salt ngẫu nhiên. `upgradeEncoding` của delegate được kỳ vọng trả `true` cho hash BCrypt khi id mới được chọn là Argon2; nó **chỉ là tín hiệu cần nâng cấp**, không tự ghi database.

Chạy:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

Với project Spring Boot 3.x/Java 17+ và dependencies ở mục 7, kỳ vọng **7 test pass**: 4 integration tests và 3 encoder tests. Đây là kết quả dự kiến, không phải tuyên bố test đã được thực thi; xem log Gradle/JUnit thật để xác nhận. Nếu lỗi, kiểm tra dependency Bouncy Castle, package tên file, security bean, cấu hình Spring Boot version và quyền truy cập cổng test.

## 9. Thiết kế nâng cấp hash khi đăng nhập thành công

Một ứng dụng có thể có các bản ghi tồn tại nhiều năm. Việc đổi thuật toán ngay lập tức không nên buộc bạn lưu lại plaintext hoặc đặt lại mật khẩu cho tất cả người dùng nếu chưa cần.

Chiến lược an toàn là **rehash on successful login**:

```text
1. User gửi username + raw password qua kết nối bảo vệ.
2. Repository đọc hash hiện tại, ví dụ {bcrypt}$2a$10$...
3. DelegatingPasswordEncoder.matches(raw, storedHash):
     - chọn encoder theo {id}
     - kiểm tra mật khẩu
4. Nếu sai: từ chối xác thực, không rehash và không lưu plaintext.
5. Nếu đúng: cho quá trình authentication tiếp tục.
6. Nếu encoder.upgradeEncoding(storedHash) == true:
     - encode(raw) theo profile hiện tại, tạo salt mới
     - ghi hash mới bằng thao tác có điều kiện
     - không log raw password/hash
7. Những lần đăng nhập sau sẽ verify bằng định dạng mới.
```

Tại bước 6, cần tránh overwrite khi hai request cùng cập nhật hash. Ví dụ cơ chế **compare-and-swap**:

```sql
UPDATE users
SET password_hash = :new_hash
WHERE username = :username
  AND password_hash = :old_hash;
```

Đây là **câu SQL minh họa** cho repository tương ứng, không phải query R2DBC chạy độc lập. Kiểm tra số hàng cập nhật (0 hoặc 1). Nếu 0, có thể hash đã thay đổi đồng thời hoặc password vừa được reset; **không** ghi đè giá trị mới bằng hash của credential cũ. Chính sách xử lý race tùy nghiệp vụ và xác thực lại khi cần.

### 9.1. Pseudocode dịch vụ reactive có ranh giới blocking

`PasswordEncoder.encode` và `matches` là phép tính CPU/memory nặng và thường đồng bộ. Một dịch vụ reactive tự viết có thể cô lập trên scheduler có kiểm soát:

```java
// Mảnh logic trong service, đã inject encoder và reactive repository.
// UserRecord/VerifyResult/repository là domain API do ứng dụng định nghĩa.
public Mono<Boolean> verifyAndUpgrade(
        String username, String submittedPassword) {

    return repository.findByUsername(username)
        .flatMap(user -> Mono.fromCallable(() -> {
            String oldHash = user.passwordHash();
            boolean matched =
                encoder.matches(submittedPassword, oldHash);

            if (!matched) {
                return new VerifyResult(false, null);
            }

            String newHash = encoder.upgradeEncoding(oldHash)
                ? encoder.encode(submittedPassword)
                : null;

            return new VerifyResult(true, newHash);
        })
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(result -> {
            if (!result.matched()) {
                return Mono.just(false);
            }

            if (result.newHash() == null) {
                return Mono.just(true);
            }

            return repository.replaceHashIfCurrent(
                    username, user.passwordHash(), result.newHash())
                .thenReturn(true);
        }))
        .defaultIfEmpty(false);
}
```

Đây là **mảnh thiết kế**, không phải class chạy độc lập vì `UserRecord`, `VerifyResult` và `repository` do dự án định nghĩa. Với record `VerifyResult`, có thể dùng cấu trúc `record VerifyResult(boolean matched, String newHash) {}` trong Java 17. Cần kiểm tra update count, xử lý race/transaction và chính sách authentication thực của ứng dụng; không sao chép code này thành cơ chế login production mà thiếu kiểm thử.

`boundedElastic` giúp không chạy công việc blocking trực tiếp trên event-loop, **không biến hashing thành non-blocking** và **không tự giới hạn đủ số lượng request đang chiếm RAM**. Password verification có thể rất nặng; nếu Argon2id memory cao, cần giới hạn phép băm đồng thời (bulkhead/semaphore/queue) và đo RAM thực tế. Scheduler chỉ thay thread thực thi chứ không tạo khả năng vô hạn.

### 9.2. Một số trường hợp phải thiết kế riêng

- **Quên mật khẩu:** dùng token reset ngẫu nhiên, một lần, có thời hạn; sau khi xác thực token thì băm password mới. Không gửi lại password cũ vì không có cơ chế giải mã.
- **Đổi password:** yêu cầu phiên/cơ chế xác thực phù hợp, xác minh password cũ khi chính sách yêu cầu, rồi tạo hash mới với profile hiện hành.
- **Tài khoản ít đăng nhập:** rehash on login không giúp người dùng không bao giờ quay lại; có thể cần lộ trình migration hoặc reset mật khẩu cho nhóm lâu không hoạt động.
- **Mật khẩu sai:** không nâng cấp, không “sửa” hash và không tiết lộ user tồn tại hay không trong response.
- **Đổi id/encoder profile:** giữ khả năng verify các format cũ cho đến khi migration xong; test tất cả id có mặt trong database.
- **Hash không có prefix:** phải có chiến lược xác định algorithm dựa trên dữ liệu tin cậy và migrate có kiểm soát; không đặt fallback “accept anything”.
- **Nâng cost trong cùng thuật toán:** một số encoder hỗ trợ `upgradeEncoding` so sánh thông số lưu trong hash với profile hiện hành; kiểm tra behavior đúng phiên bản thư viện và test bằng hash thực.

## 10. Chọn work factor bằng phép đo, không bằng cảm giác

Chi phí lý tưởng làm một lần thử mật khẩu đủ tốn kém để tăng chi phí tấn công, nhưng vẫn đáp ứng trải nghiệm người dùng và khả năng phục vụ login hợp pháp.

### 10.1. Xác định mục tiêu và tài nguyên

Thu thập các yếu tố:

- **Latency budget** dành riêng cho phép băm/so khớp: ví dụ một phần của p95 login SLA, không chỉ thời gian handler Java.
- **CPU thực tế**: model, số vCPU, giới hạn CPU của pod/container, frequency throttling.
- **RAM thực tế**: memory limit của pod, heap/native, các thành phần cùng tiến trình.
- **Số xác thực đồng thời** ở p95/p99 lưu lượng hợp pháp và burst từ retry/credential stuffing.
- **Số instance autoscaling** và chi phí hạ tầng khi tăng load.
- **Thời gian xếp hàng** khi giới hạn số verification song song.
- **Bảo vệ bề mặt login**: rate limit theo tài khoản/IP/thiết bị, detection, MFA, CAPTCHA có kiểm soát khi cần, login lockout policy thận trọng để tránh bị lợi dụng DoS.
- **Chu kỳ nâng cost**: ví dụ review định kỳ hoặc khi nâng phần cứng/có cảnh báo mới, không giữ tham số cố định mãi.

Không tối ưu chỉ theo thời gian `encode` trên laptop; **login chủ yếu chạy `matches` với hash có cost được lưu bên trong**, và có thể phải xác minh nhiều profile legacy. Benchmark cả `encode` và `matches` của từng loại hash đang vận hành.

### 10.2. Phương pháp benchmark có ý nghĩa

1. Chọn một vài cấu hình hợp lệ (ví dụ BCrypt strength 10/12/13, Argon2id memory 16/32/64 MiB với iterations thích hợp).
2. Chạy trên **cùng loại CPU/RAM và memory limit** như production hoặc môi trường staging đại diện.
3. Dùng dữ liệu kiểm thử không phải password thật; khởi động JVM/warm up hợp lý.
4. Đo latency median/p95/p99 của phép encode và matches; báo cáo cả throughput.
5. Kiểm thử nhiều concurrent verifications, ví dụ 1, 5, 20, 50 (chọn theo thực tế, không coi là mục tiêu mặc định).
6. Theo dõi CPU, RSS/heap, garbage collection, out-of-memory, thời gian chờ queue và thời gian phản hồi tổng thể.
7. Thử lỗi mật khẩu, user không tồn tại, reconnect/timeout và traffic burst; không trả thông tin khiến attacker dễ username enumeration.
8. Chọn cấu hình đáp ứng cả an toàn và SLA, có độ dư cho tăng trưởng/lỗi node, triển khai theo canary nếu nâng cost đáng kể.
9. Ghi lại phần cứng, JVM, version dependency, cost và kết quả để so sánh lần sau; bảo đảm benchmark không ghi mật khẩu thật.

Đo nhanh bằng `System.nanoTime()` có thể hữu ích để học cơ chế, nhưng không thay benchmark đáng tin (ví dụ JMH) vì JIT, warmup, GC, CPU scheduling và tần suất đồng thời làm nhiễu. Không suy ra p95 production từ một vòng lặp đơn luồng.

### 10.3. Một phép tính dung lượng RAM cần làm

Ví dụ Argon2id với `m = 65536 KiB = 64 MiB`. Nếu bạn cho phép 24 phép verify thực thi đồng thời, yêu cầu bộ nhớ theo tham số **xấp xỉ**:

```text
24 × 64 MiB = 1536 MiB = 1.5 GiB
```

Đó chỉ là mô hình chi phí cấp bộ nhớ từ tham số, không phải đo RSS chính xác; còn overhead của JVM, OS, thư viện native và những request khác. Nếu một pod có giới hạn 1 GiB, đây là dấu hiệu rõ ràng bạn phải giảm concurrency, giảm m, điều chỉnh số replica hoặc thiết kế lại đường xác thực. Không đặt concurrency dựa vào số Netty event-loop threads rồi giả định mọi hashing được kiểm soát.

### 10.4. Chọn cấu hình ban đầu có kiểm soát

Một lộ trình thực tế:

- Nếu database cũ đang dùng BCrypt: tiếp tục verify bằng encoder đúng profile, đo strength hiện có, bật `upgradeEncoding`/rehash khi đăng nhập thành công nếu cần; đừng phá khả năng login của user cũ.
- Nếu xây mới và có thể cấp bộ nhớ: cân nhắc Argon2id, bắt đầu bằng profile chuẩn của thư viện làm đường cơ sở, đo rồi điều chỉnh `m,t,p` dựa trên SLA và concurrency.
- Nếu môi trường rất hạn chế RAM: cân nhắc kỹ Argon2id memory cost và khả năng giữ an toàn ở tải lớn; BCrypt cost đã benchmark có thể phù hợp hơn về vận hành.
- Không dùng cost thấp chỉ để “fix timeout” trước khi tìm nguyên nhân: có thể là quota CPU, retry storm, thiếu rate limit, servlet-blocking đặt trên event-loop, hoặc không có bulkhead.
- Tách chi phí lưu hash lúc đăng ký/đổi password và chi phí verify lúc login; cả hai đều ảnh hưởng hệ thống nhưng tải có thể rất khác.

## 11. Lưu ý riêng khi xác thực trong Spring WebFlux

Dùng Reactor cho request handling không khiến BCrypt hay Argon2id tự thành non-blocking. `PasswordEncoder.matches(...)` là lời gọi đồng bộ tính toán CPU/RAM; nếu chạy trực tiếp trên Netty event-loop với cost cao, nhiều request có thể bị chậm.

Điều cần kiểm chứng:

1. Authentication manager hiện tại có offload phần kiểm tra mật khẩu ra scheduler phù hợp không? Hành vi này phụ thuộc cấu hình và phiên bản Spring Security; **không mặc định** mọi lớp reactive tự đặt công việc hashing vào `boundedElastic`.
2. Mức song song của hashing có bị giới hạn bởi quota CPU/RAM không? Một boundedElastic chung không tự đảm bảo RAM của Argon2id có giới hạn theo workload.
3. Khi service phụ thuộc database/reactive user store chậm, có timeout và backpressure phù hợp không?
4. Có phân biệt exception do user store, mật khẩu sai và lỗi hệ thống khi ghi log/metric không? Client thường không cần biết user có tồn tại hay không.
5. Có tránh giữ raw password trong log, metrics tags, tracing baggage, exception message hoặc payload sau khi xác thực không?

Một helper reactive dùng trong **dịch vụ tùy biến** (không tự thay authentication manager của Spring Security) có thể viết:

```java
public Mono<Boolean> checkPassword(
        PasswordEncoder encoder,
        String rawPassword,
        String storedHash) {
    return Mono.fromCallable(
            () -> encoder.matches(rawPassword, storedHash))
        .subscribeOn(Schedulers.boundedElastic());
}
```

Đây là method minh họa, cần import `Mono`, `Schedulers` và `PasswordEncoder`. Nó trả publisher để caller compose, không `block()` hoặc tự `subscribe()` trong handler. Với workload lớn, nên thêm cơ chế giới hạn concurrency cho riêng password verification và quan sát queue, thay vì bơm vô hạn công việc vào scheduler.

Không đưa hash vào Reactor Context như một cách “lưu tạm credential” cho mọi operator. Security context gắn với **Authentication** đã xác thực, không phải chỗ chứa raw password. Nếu cần audit, log event không chứa credential; danh tính và quyền xác thực được đọc bằng `ReactiveSecurityContextHolder` hoặc API được Spring WebFlux cung cấp.

## 12. Những lỗi thường gặp và cách khắc phục

| Lỗi/triệu chứng | Nguyên nhân | Cách làm đúng |
|---|---|---|
| Hai lần `encode(password)` cho hash khác nhau, tưởng lỗi | Salt ngẫu nhiên mỗi lần | Dùng `matches(raw, storedHash)`, không so hash mới với hash cũ |
| Lưu SHA-256(password) trực tiếp | Hash quá nhanh để bảo vệ password trước offline cracking | Dùng BCrypt/Argon2id hoặc password KDF phù hợp |
| Dùng `NoOpPasswordEncoder` cho production | Lưu/so mật khẩu plaintext | Dùng encoder có salt và cost, migration được kiểm soát |
| Hash BCrypt không có `{bcrypt}` trong khi delegate yêu cầu id | Format legacy thiếu prefix | Migrate có kiểm thử hoặc đăng ký đường tương thích cụ thể; không fallback bừa |
| Thêm `{argon2}` cho hash có profile khác bằng string replace | Nhầm id routing và tham số thuật toán | Giữ id đúng với encoder, test `matches` trên hash thật |
| Chỉ đổi `idForEncode` rồi nghĩ database đã cập nhật | Delegate chỉ thay hash mới | Rehash on successful login, lưu có điều kiện |
| BCrypt không phân biệt phần vượt 72 byte | Giới hạn truyền thống của thuật toán | Đánh giá byte-length/implementation và chính sách nhập mật khẩu |
| Chọn BCrypt strength rất cao khiến login quá chậm | Cost tăng gần theo cấp số nhân | Benchmark và chọn độ trễ/tải có thể vận hành |
| Chọn Argon2id m=64 MiB, chạy quá nhiều request đồng thời | Tổng memory vượt container | Giới hạn concurrency, đo RSS, chỉnh m/t/p/replicas |
| `ClassNotFound` khi dùng Argon2 | Thiếu Bouncy Castle tương thích | Thêm dependency đúng, kiểm tra dependency tree |
| Tự viết hash compare bằng `String.equals` trên digest | Bỏ qua logic encoder, salt và format | Dùng `PasswordEncoder.matches` |
| Trả “user không tồn tại” với email cụ thể | Username enumeration | Thông báo lỗi đăng nhập nhất quán, giám sát rate-limit |
| Hash raw password trên event-loop | CPU/memory blocking làm nghẽn reactive server | Kiểm tra đường xác thực, offload/limit phù hợp |
| Ghi password hoặc hash vào logs | Lộ credential hoặc dữ liệu tấn công offline | Chặn logging nhạy cảm, redaction, kiểm tra observability |
| Chuyển cost nhưng không giữ backward compatibility | Người dùng cũ không đăng nhập được | `DelegatingPasswordEncoder` và migration từng bước |
| Dùng một pepper hardcode | Bí mật bị lộ theo source | Nếu áp dụng pepper, quản lý riêng ở secret manager và có kế hoạch rotation |
| Dùng user/password demo trong production | Credential mẫu bị công khai | Thay bằng identity store, provisioning/reset và TLS chính thức |

## 13. Bài tập tự kiểm tra

### Bài 1: Tại sao không `encode().equals()`?

Một user có `storedHash` được tạo hôm qua. Hôm nay login đưa cùng raw password, nhưng `encoder.encode(raw)` tạo một chuỗi khác. Kết luận user nhập sai đúng không?

**Đáp án:** Không. Salt ngẫu nhiên làm hash mới khác hash cũ; phải gọi `encoder.matches(raw, storedHash)`. Một hash còn chứa thuật toán và thông số cần thiết để verify.

### Bài 2: BCrypt strength 10 so với 13

Nếu cùng implementation/hardware và những yếu tố khác như nhau, strength 13 tốn công việc tương đối bao nhiêu so với 10?

**Đáp án:** Mô hình công việc gấp khoảng `2^(13−10) = 8` lần. Đây không phải lời hứa latency HTTP gấp chính xác 8 lần; cần benchmark.

### Bài 3: Argon2id 64 MiB và nhiều request

Bạn cấu hình `m = 65536 KiB`, cho phép 40 phép tính cùng lúc. Chỉ riêng bộ nhớ tương ứng tham số xấp xỉ bao nhiêu?

**Đáp án:** `40 × 64 MiB = 2560 MiB ≈ 2.5 GiB`, chưa tính overhead. Phải giới hạn số phép xác minh đồng thời hoặc thay đổi cấu hình/hạ tầng.

### Bài 4: Có cần biết password gốc để nâng hash?

Database chỉ có `{bcrypt}...`, muốn lưu Argon2id mà không có lúc user nhập password. Có thể đổi trực tiếp hash cũ sang Argon2id không?

**Đáp án:** Không có phép đổi an toàn tổng quát từ một password hash sang hash của **raw password** bằng cách chỉ dùng hash cũ. Rehash khi user đăng nhập đúng, khi user đổi/reset mật khẩu, hoặc thiết kế migration có xác thực phù hợp.

### Bài 5: Đăng nhập hiện đại nhưng stored hash legacy

`DelegatingPasswordEncoder` được đặt `idForEncode = "argon2@SpringSecurity_v5_8"`, còn database chứa `{bcrypt}$2a$12$...`. `matches` có thể chạy được không?

**Đáp án:** Có, nếu map chứa id `bcrypt` và BCrypt encoder tương thích. `idForEncode` chỉ quyết định cách tạo hash mới; verify dựa trên prefix của hash đang lưu. `upgradeEncoding` có thể báo cần chuyển profile.

### Bài 6: Thế nào là bảo vệ reactive server khỏi overload?

Một API login dùng Argon2id cost cao và nhận lượng request không giới hạn. Chỉ thêm `subscribeOn(Schedulers.boundedElastic())` có đủ không?

**Đáp án:** Không. Nó chuyển công việc blocking khỏi event-loop nhưng vẫn có CPU/RAM cost; phải giới hạn concurrency, rate-limit, queue/backpressure, đo memory và giám sát. Nếu không, hệ thống vẫn có thể bị DoS qua login.

### Bài 7: Salt có cần giữ bí mật không?

Nếu hacker lấy database gồm hash + salt, salt có làm mọi mật khẩu bị lộ ngay không?

**Đáp án:** Không. Salt không phải bí mật và thường lưu cùng hash. Nó làm giảm lợi thế precomputed table và giúp các password giống nhau có hash khác nhau; kẻ tấn công vẫn có thể thử đoán offline nên password policy, MFA, cost phù hợp và bảo vệ DB vẫn rất quan trọng.

### Bài 8: Vì sao không dùng mật khẩu demo làm benchmark thật?

Password demo có thể dùng để đo hoạt động encoder, nhưng benchmark production dựa riêng vào một request đơn giản có đủ không?

**Đáp án:** Không. Cần đại diện cho phần cứng, giới hạn container, workload concurrent, phân bố hash cũ và mới, warmup/GC, p95/p99 latency và cả khả năng chịu tải trước credential stuffing.

## 14. Checklist triển khai an toàn

- [ ] Không lưu plaintext, không đưa raw password/hash vào response/log/trace.
- [ ] Sử dụng `PasswordEncoder` chính thức có salt và work factor phù hợp.
- [ ] Hash lưu đủ chuỗi gồm `{id}` và tham số của thuật toán, không cắt ngắn cột database.
- [ ] Chọn BCrypt/Argon2id theo nhu cầu tương thích và threat model, không chỉ theo sự phổ biến.
- [ ] Thử password có Unicode và passphrase dài; biết ranh giới 72 byte của BCrypt.
- [ ] Kiểm tra dependency provider cần thiết cho Argon2 và cập nhật bảo mật thư viện.
- [ ] Benchmark trên phần cứng/container gần production, xét cả CPU, RAM, p95/p99 và concurrency.
- [ ] Có kiểm soát brute-force/credential stuffing, quota request và giới hạn số phép hash nặng đồng thời.
- [ ] Reactive authentication không được block event-loop ngoài chủ đích; kiểm tra scheduler thật và giới hạn tài nguyên.
- [ ] Việc nâng hash có check `matches` trước, tạo salt mới, và lưu có điều kiện chống race.
- [ ] User chưa migrate vẫn đăng nhập được bằng encoder cũ trong thời gian chuyển đổi.
- [ ] Test HTTP 401/200, hash cũ/mới, mật khẩu sai, salt khác nhau, và thông báo nâng cấp.
- [ ] Có quy trình reset password và secret rotation nếu hệ thống có pepper, không cần khả năng giải mã mật khẩu.

## Tóm tắt

```text
raw password  --encode (salt + cost)--> stored hash
raw password + stored hash --matches--> true/false

BCrypt:
  strength tăng 1 => công việc lõi tăng khoảng gấp đôi
  đặc biệt lưu ý giới hạn input 72 byte

Argon2id:
  m = memory KiB; t = iterations; p = parallelism
  memory-hard nhưng tốn RAM cho mỗi phép verify đồng thời

Spring Security:
  PasswordEncoder.encode / matches / upgradeEncoding
  DelegatingPasswordEncoder dùng {id} để chọn thuật toán
  migration bằng verify trước rồi rehash khi login thành công

WebFlux:
  hashing vẫn là CPU/RAM-heavy work
  giữ nguyên reactive contract, không block event-loop
  giới hạn concurrency/rate và benchmark thật
```

Một password hash tốt không làm mất nhu cầu TLS, MFA, login throttling, quản lý tài khoản và bảo vệ database. Chọn đúng thuật toán **và** chi phí vận hành mới tạo được lớp phòng vệ hữu ích.

## Tài liệu tham khảo chính thức

- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security — PasswordEncoder API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security — BCryptPasswordEncoder API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html)
- [Spring Security — Argon2PasswordEncoder API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/crypto/argon2/Argon2PasswordEncoder.html)
- [Spring Security — DelegatingPasswordEncoder API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html)
- [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [RFC 9106 — Argon2 Memory-Hard Function](https://www.rfc-editor.org/rfc/rfc9106)
