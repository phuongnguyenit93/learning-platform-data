# Phân biệt băm mật khẩu với mã hóa có thể giải mã

Để xác minh người dùng đăng nhập, ứng dụng cần trả lời một câu hỏi: **“Mật khẩu vừa nhập có khớp mật khẩu người dùng đã đăng ký không?”**. Ứng dụng **không cần lấy lại mật khẩu cũ**. Vì vậy, mật khẩu đăng nhập phải được lưu dưới dạng **password hash một chiều** với thuật toán chuyên dụng, chứ không lưu plaintext hoặc một ciphertext có thể giải mã.

Dù đều biến dữ liệu thành chuỗi khó đọc, hai cơ chế có mục đích khác nhau:

- **Băm mật khẩu (password hashing):** tính giá trị kiểm tra từ mật khẩu, salt và thông số chi phí. Khi login, hệ thống dùng `PasswordEncoder.matches(rawPassword, storedHash)`; không có thao tác `decrypt(storedHash)` để lấy lại mật khẩu gốc.
- **Mã hóa có thể giải mã (reversible encryption):** biến plaintext thành ciphertext bằng khóa mã hóa và tham số phù hợp. Người có khóa giải mã được plaintext. Chỉ nên dùng khi **nghiệp vụ thực sự phải đọc lại nội dung gốc**.
- **Encoding như Base64:** chỉ đổi cách biểu diễn bytes thành text; bất kỳ ai cũng có thể decode. Không phải encryption hay password hashing.

Bài dành cho **Java 17+, Spring Boot 3, Spring Security 6.x, Spring MVC/Servlet**, kết hợp API `PasswordEncoder`, `BCryptPasswordEncoder`, `DelegatingPasswordEncoder`, ứng dụng Spring Security mẫu, kiểm thử và một chương trình Java 17 độc lập so sánh PBKDF2 với AES-GCM. Nếu môi trường đang dùng Spring Security 7 hoặc stack reactive, cần tra đúng tài liệu của phiên bản và stack.

## 1. So sánh hai loại bảo vệ theo mục đích

| Tiêu chí | Băm mật khẩu chuyên dụng | Mã hóa có thể giải mã |
| --- | --- | --- |
| Mục đích | Xác minh password được nhập lại | Giữ dữ liệu bí mật nhưng vẫn có thể khôi phục |
| Thuật toán điển hình | Argon2id, scrypt, bcrypt, PBKDF2-HMAC-SHA256 | AES-GCM (authenticated encryption) |
| Dữ liệu đưa vào | Raw password + salt + tham số chi phí | Plaintext + encryption key + nonce/IV |
| Kết quả | Stored hash + metadata | Ciphertext + nonce/IV + authentication tag |
| Có decrypt ra plaintext gốc? | **Không** | **Có, khi có key đúng** |
| Salt | Ngẫu nhiên riêng cho password; có thể lưu cùng hash | Không dùng salt theo cùng nghĩa; GCM dùng nonce/IV |
| Khóa bí mật | Không cần encryption key; có thể thêm pepper bí mật | **Bắt buộc bảo vệ encryption key** |
| So password | `matches(raw, stored)` trả boolean | Có thể decrypt để đọc nội dung; không nên dùng cho lưu password đăng nhập |
| Cùng password của hai user | Salt riêng khiến stored hashes thường khác nhau | Nonce khác có thể khiến ciphertext khác nhau, nhưng key vẫn decrypt được |
| Khi DB bị lộ | Kẻ tấn công có thể thử password ứng viên offline, phải trả chi phí tính KDF | Nếu key cũng lộ, attacker có thể decrypt dữ liệu |
| Khi user quên password | Reset mật khẩu mới | Khả năng decrypt tồn tại nếu key còn đúng |
| Use case | Password login của người dùng | Bí mật kết nối đối tác cần gửi lại, dữ liệu cần được khôi phục có kiểm soát |

Một cách quyết định nhanh: nếu chỉ cần **so sánh bí mật** mà không cần đọc lại, hãy xem xét cơ chế hashing/verifier phù hợp. Nếu cần dùng lại plaintext theo quyền hợp lệ, có thể cần encryption. Password đăng nhập của người dùng thuộc nhóm thứ nhất.

### 1.1. Hai luồng không giống nhau

```text
PASSWORD HASHING
raw password + salt ngẫu nhiên + chi phí
              |
              v
     Argon2id / bcrypt / scrypt / PBKDF2
              |
              v
       stored password hash
              |
     candidate password ----> matches(...) ----> true / false
              |
       KHÔNG có decrypt(hash)

REVERSIBLE ENCRYPTION
plaintext + encryption key + IV/nonce
              |
              v
          AES-GCM encrypt
              |
              v
    ciphertext + nonce + auth tag
              |
           AES-GCM decrypt + key đúng
              |
              v
       plaintext được khôi phục
```

Password hashing nhằm **hạn chế chi phí đoán mật khẩu khi dữ liệu lưu bị lộ**, trong khi encryption nhằm **giữ bí mật nội dung khỏi người không có key**. Cả hai đều có vai trò nhưng không hoán đổi được.

## 2. “Không thể giải mã hash” không có nghĩa “không thể đoán password”

Đây là hiểu nhầm rất phổ biến. Password hash không chứa một “mã hóa bí mật” mà bạn có thể giải mã bằng khóa. Nhưng attacker có thể **thử đoán**:

```text
storedHash của Alice bị lộ
     |
candidate "123456" -> hash với salt đã lưu -> có khớp?
candidate "password" -> hash với salt đã lưu -> có khớp?
candidate "Alice2026!" -> hash với salt đã lưu -> có khớp?
...
```

Nếu một candidate tạo kết quả đúng, attacker đã đoán được password; họ không decrypt hash. Vì password do con người đặt có thể rất dễ đoán, hệ thống cần làm **mỗi lần thử trở nên tốn tài nguyên**.

### 2.1. Vì sao không lưu SHA-256(password)?

SHA-256 là hàm băm mật mã tốt cho nhiều việc, chẳng hạn kiểm tra tính toàn vẹn dữ liệu. Nhưng nó được thiết kế để **tính nhanh**, trong khi password hashing phải **chậm có kiểm soát**, và thường có khả năng điều chỉnh cost theo phần cứng.

| Cách lưu | Phù hợp cho password? | Lý do |
| --- | --- | --- |
| Plaintext | Không | Database leak là lộ toàn bộ password |
| Base64(password) | Không | Decode dễ dàng |
| MD5(password) / SHA-1(password) | Không | Fast/legacy hash, không phù hợp |
| SHA-256(password) | Không | Quá nhanh cho offline guessing |
| SHA-256(salt + password) | Không đủ | Salt tốt nhưng tốc độ thử vẫn cao |
| AES(password, key) | Không | Có thể decrypt khi key lộ hoặc bị lạm dụng |
| bcrypt với salt/cost phù hợp | Có thể dùng | Adaptive password hashing |
| scrypt hoặc Argon2id phù hợp | Có thể dùng | Cost về CPU/bộ nhớ làm tăng chi phí đoán |
| PBKDF2-HMAC-SHA256 đúng iteration/salt | Có thể dùng | Password-based key derivation có chi phí |
| HMAC-SHA256 tự ghép | Không tự đủ | Secret-key MAC không tự thay thế password KDF |

Tên “hash” không đủ để kết luận hệ thống lưu password an toàn. Bạn phải biết **thuật toán**, **salt**, **cost/work factor**, cách verify, nâng cấp và kiểm soát tải.

## 3. Salt: ngẫu nhiên riêng cho mỗi hash

**Salt** là dữ liệu ngẫu nhiên được sinh cho mỗi password hash. Hệ thống có thể lưu salt **cùng** kết quả hash vì salt **không cần giữ bí mật**. Với cùng password của Alice và Bob:

```text
Alice:
password = "same-secret"
salt = random_A
hash = KDF(password, random_A, cost)

Bob:
password = "same-secret"
salt = random_B
hash = KDF(password, random_B, cost)

=> hash Alice thường KHÁC hash Bob.
```

Salt giúp giảm giá trị của các bảng tính sẵn như rainbow tables và khiến attacker phải trả chi phí đoán với từng salt. Salt **không** làm password hash trở thành ciphertext; salt là tham số **để kiểm tra** password mới nhập về sau.

### 3.1. Salt không thay thế chi phí tính toán

Giả sử attacker biết salt. Điều này bình thường vì salt thường lưu trong database. Nếu ứng dụng chỉ tính `SHA256(salt || password)`, attacker vẫn thử được rất nhiều ứng viên. Sử dụng password KDF thích hợp để vừa có salt, vừa có work factor đủ cao.

### 3.2. Salt có phải mã bí mật của ứng dụng?

Không. Salt **khác** secret key và pepper. Khi attacker có cả hash và salt, họ vẫn phải đoán password. Không cần đưa salt vào KMS, nhưng phải dùng nguồn random an toàn như `SecureRandom` theo hướng dẫn của thuật toán/encoder. Không dùng một salt cố định cho tất cả người dùng.

## 4. Pepper: khi nào cần bí mật ngoài database?

**Pepper** là một bí mật bổ sung, thường dùng chung cho một phạm vi người dùng hoặc ứng dụng và được giữ ngoài DB (secret store, KMS/HSM/vault) nhằm tăng phòng vệ nếu DB bị lộ. So sánh:

| | Salt | Pepper |
| --- | --- | --- |
| Có cần bí mật? | Không | **Có** |
| Có riêng cho từng hash? | Thường có | Thường chia sẻ |
| Lưu cùng hash? | Có thể | Không |
| Mục tiêu | Phân biệt các hash, chống precomputation | Bổ sung rào cản khi DB bị lộ |
| Nếu mất | Đã lưu với hash nên không sao | Có thể không xác minh được mật khẩu tùy thiết kế |
| Nếu bị lộ | Không phải “key bị lộ” | Cần kế hoạch rotation, migration/reset |

Pepper **không thay thế** salt và KDF chậm. Đừng tự áp dụng công thức `SHA256(pepper + password)` rồi cho rằng đã đủ. Nếu dùng pepper, cần scheme đã được đánh giá, quy trình vận hành và xử lý khi pepper bị thu hồi.

### 4.1. IV/nonce không phải salt

AES-GCM dùng **IV/nonce**, không phải password salt. Đặc biệt, **không tái sử dụng một nonce dưới cùng encryption key** vì có thể gây phá vỡ nghiêm trọng tính bí mật/toàn vẹn. Với nonce ngẫu nhiên 96-bit, hệ thống có quy mô mã hóa lớn phải đánh giá nguy cơ va chạm và chọn chiến lược quản lý nonce thích hợp.

Salt và nonce đều có thể được lưu cùng kết quả, nhưng **ràng buộc an toàn và mục đích khác nhau**. Không dùng một IV cố định chỉ vì cùng ứng dụng luôn dùng một key.

## 5. Work factor: chi phí tính mật khẩu có chủ đích

Một password KDF tốt khiến mỗi lần kiểm tra password tiêu tốn thời gian, có thể cả bộ nhớ. Điều này có chi phí với server hợp lệ, nhưng cũng tăng chi phí tấn công offline.

- **bcrypt:** cấu hình strength/cost, ví dụ 10 hoặc 12; chi phí tăng nhanh khi tăng cost.
- **PBKDF2:** cấu hình số vòng lặp, ví dụ PBKDF2-HMAC-SHA256 với 600.000 iterations trong một khuyến nghị OWASP hiện hành; cần kiểm tra lại hướng dẫn theo thời điểm triển khai.
- **scrypt/Argon2id:** còn có tham số bộ nhớ để chống lại lợi thế tấn công song song trên phần cứng chuyên dụng.
- **Argon2id:** là lựa chọn được OWASP ưu tiên cho hệ thống mới khi môi trường hỗ trợ đúng.

Không có một con số cost vĩnh viễn thích hợp với mọi máy chủ. Đo tốc độ verify trên hạ tầng của bạn, đánh giá concurrent logins, giới hạn rate và nguy cơ DoS; tăng cost khi công nghệ thay đổi mà vẫn giữ trải nghiệm và tài nguyên hợp lý.

### 5.1. Giới hạn đầu vào của bcrypt

Nhiều triển khai bcrypt xử lý tối đa khoảng **72 byte đầu vào**. Đây là byte, không phải `String.length()` trong Java: một ký tự Unicode có thể nhiều byte UTF-8. Hãy xem quy tắc của phiên bản encoder thực tế, không âm thầm cắt password hoặc tự pre-hash một cách tùy tiện. OWASP nêu các rủi ro cụ thể nếu tự kết hợp fast hash với bcrypt không đúng.

## 6. Spring Security PasswordEncoder là API một chiều

Trong `org.springframework.security.crypto.password`, contract trọng tâm là:

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

Đây là khai báo rút gọn để học. Không có `decrypt` hoặc `decode` trong `PasswordEncoder`.

- `encode(raw)` dùng lúc đăng ký, đặt hoặc đổi password để tạo giá trị lưu.
- `matches(candidate, stored)` dùng khi login, nhận candidate mới nhập và stored hash đã có để trả true/false.
- `upgradeEncoding(stored)` giúp kiểm tra có cần nâng thuật toán/cost; cập nhật database còn cần flow và storage phù hợp.

### 6.1. BCryptPasswordEncoder: ví dụ so khớp đúng

```java
PasswordEncoder encoder = new BCryptPasswordEncoder(12);

String storedHash = encoder.encode("local-only-password");

boolean valid = encoder.matches(
    "local-only-password", storedHash
);
boolean invalid = encoder.matches(
    "wrong-password", storedHash
);

// valid == true, invalid == false
```

Đây là fragment cần Spring Security dependency và imports. Strength 12 chỉ là ví dụ, cần benchmark server. Kết quả `encode` có salt ngẫu nhiên, vì vậy hai lần encode cùng raw password thường không ra cùng String.

**Anti-pattern thường gặp:**

```java
// Sai: encode mới có thể dùng salt mới, so String thất bại.
boolean wrong = encoder.encode(raw).equals(storedHash);

// Đúng: encoder dùng metadata/salt của stored hash.
boolean correct = encoder.matches(raw, storedHash);
```

Từ `encodedPassword` ở API không có nghĩa “encrypted password có thể decrypt”. Với encoder một chiều, đó là định dạng hash phục vụ so khớp.

### 6.2. Vì sao Stored Hash vẫn phải bảo vệ?

Stored hash không phải plaintext nhưng vẫn giúp attacker thử đoán password offline khi bị lộ. Không log password hash, không gửi cho browser, không để backup public, không cấp quyền đọc cột password_hash tùy tiện.

## 7. DelegatingPasswordEncoder: nhận biết định dạng hash theo thời gian

Spring Security cung cấp `DelegatingPasswordEncoder` để hỗ trợ nhiều thuật toán/cost khi cần migration:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
```

Với Spring Security 6.5 và factory mặc định, hash mới thường dùng bcrypt với prefix `{bcrypt}`. Định dạng chung:

```text
{id}encodedPassword
```

Ví dụ:

```text
{bcrypt}$2a$10$...
{pbkdf2}...
{scrypt}...
```

`id` không phải encryption key. Nó là **tên delegate** để `matches` biết cách giải thích phần còn lại. Vì password storage best practices có thể thay đổi theo thời gian, metadata này hỗ trợ giai đoạn tồn tại các hash cũ và mới.

### 7.1. Ví dụ verify theo format

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String saved = encoder.encode("sample-password");

System.out.println(saved.startsWith("{bcrypt}"));
System.out.println(encoder.matches("sample-password", saved));
System.out.println(encoder.matches("wrong", saved));
```

Với factory theo bản Spring Security đang minh họa, output boolean dự kiến:

```text
true
true
false
```

Bản hash cụ thể thay đổi theo salt nên không nên hardcode giá trị đó làm output cố định. Khi nâng framework và thay cấu hình encode id, kiểm tra lại behavior với BOM thực tế.

### 7.2. Nếu gặp “id null”

Hash bcrypt đời cũ có thể lưu trực tiếp bắt đầu bằng `$2a$...`, trong khi `DelegatingPasswordEncoder` trông đợi prefix `{id}`. Khi không có mapping thích hợp, `matches` có thể ném:

```text
There is no PasswordEncoder mapped for the id "null"
```

Không sửa bằng `NoOpPasswordEncoder` hoặc bỏ kiểm tra password. Xác định đúng format cũ và lên kế hoạch migrate/prefix/hash upgrade với test, giữ nguyên khả năng verify các user hợp lệ.

### 7.3. Nâng thuật toán khi user đăng nhập

Khi mật khẩu được verify thành công, ứng dụng có thể xét `upgradeEncoding` và tạo lại hash bằng tham số mới từ **raw password mà user vừa cung cấp**. `UserDetailsPasswordService` có thể hỗ trợ cập nhật encoded password trong provider flow khi được cấu hình phù hợp. Không thể tự decrypt toàn bộ password hashes cũ rồi rehash hàng loạt nếu không có raw password.

## 8. Mã hóa có thể giải mã phù hợp lúc nào?

Ví dụ ứng dụng cần gửi một credential tới bên thứ ba trong outbound request. Ứng dụng được phép đọc nội dung gốc để kết nối, nên việc mã hóa đối xứng có xác thực và quản lý khóa có thể phù hợp.

Một số use case:

- Secret tích hợp mà backend phải dùng lại theo quyền được kiểm soát;
- Dữ liệu cá nhân/tài liệu nhạy cảm phải được đọc lại theo yêu cầu hợp pháp;
- Trường dữ liệu dùng cho một business flow đòi khôi phục chính xác;
- Backup được bảo vệ bằng encryption key tách biệt.

**Không dùng encryption để có tính năng “xem lại password đã đăng ký”.** Đó không phải nhu cầu của hệ thống xác thực password. Password reset mới là mô hình đúng.

### 8.1. AES-GCM là authenticated encryption

AES-GCM vừa bảo vệ tính bí mật, vừa giúp phát hiện ciphertext hoặc associated data bị chỉnh sửa qua authentication tag. Khi dùng phải:

1. Sinh và bảo vệ encryption key an toàn;
2. Không tái sử dụng nonce với cùng key;
3. Dùng IV/tag và thuật toán phù hợp;
4. Kiểm tra tag khi decrypt, từ chối khi không hợp lệ;
5. Dùng AAD để ràng buộc dữ liệu với tenant/account/type khi cần;
6. Quản lý key version, rotation, KMS/backup và phân quyền decrypt.

Không tự dùng AES-ECB hoặc ghép AES-CBC với cách “kiểm tra integrity” tự sáng tạo. Với GCM, một lỗi reuse nonce có thể gây hậu quả rất nghiêm trọng.

### 8.2. Bảng phân biệt các giá trị

| Giá trị | Có bí mật không? | Phải lưu thế nào? |
| --- | --- | --- |
| Password salt | Không | Kèm password hash |
| Password KDF cost/id | Không | Kèm stored hash |
| Password hash | Cần bảo vệ vì có thể bị đoán offline | Trường DB riêng, quyền truy cập hẹp |
| Pepper | **Có** | Ngoài DB, secret manager |
| AES-GCM nonce/IV | Thường không | Kèm ciphertext, bảo đảm uniqueness |
| AES-GCM ciphertext/tag | Theo policy dữ liệu | Lưu kèm metadata cần decrypt |
| AES encryption key | **Có** | KMS/HSM/vault, không lưu cùng quyền DB |
| Raw password | **Có** | Không log/ghi plaintext, giảm thời gian sống trong bộ nhớ |

Nếu attacker có cả DB ciphertext và key AES, họ có thể decrypt. Nếu attacker chỉ có DB chứa password hashes được tạo đúng, họ không có “decrypt key” nhưng vẫn có thể thử đoán password offline. Hai threat model không giống nhau.

## 9. Java 17 độc lập: PBKDF2 so khớp, AES-GCM giải mã

Chương trình sau **không cần Spring Security**. Nó minh họa hai công việc trên cùng một JDK 17:

- PBKDF2WithHmacSHA256: tạo derived hash từ raw password + random salt + iterations, rồi dùng `MessageDigest.isEqual` để so password ứng viên.
- AES/GCM/NoPadding: mã hóa một chuỗi dữ liệu bằng secret key + random nonce; sau đó decrypt khôi phục nội dung gốc và phát hiện tag bị sửa.

**Giới hạn:** Đây là mã học tập, không phải hệ lưu mật khẩu production. Một sản phẩm còn cần schema/metadata, bảo vệ raw input, cost benchmark, kiểm soát lỗi, KMS, giới hạn requests, audit, migration và reset. Với Spring Security, ưu tiên `PasswordEncoder` có sẵn.

### 9.1. Mã đầy đủ

Tạo file `HashVsEncryption.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;

import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.PBEKeySpec;

public class HashVsEncryption {
    private static final int ROUNDS = 600_000;
    private static final int SALT_BYTES = 16;
    private static final int KEY_BITS = 256;
    private static final int IV_BYTES = 12;
    private static final int TAG_BITS = 128;

    record PasswordRecord(byte[] salt, byte[] hash) {}
    record CipherRecord(byte[] iv, byte[] ciphertextAndTag) {}

    static byte[] derive(char[] password, byte[] salt)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(
            password, salt, ROUNDS, KEY_BITS
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

    static PasswordRecord hash(char[] password, SecureRandom rng)
            throws GeneralSecurityException {
        byte[] salt = new byte[SALT_BYTES];
        rng.nextBytes(salt);
        return new PasswordRecord(salt, derive(password, salt));
    }

    static boolean matches(char[] candidate, PasswordRecord saved)
            throws GeneralSecurityException {
        byte[] value = derive(candidate, saved.salt());
        try {
            return MessageDigest.isEqual(value, saved.hash());
        } finally {
            Arrays.fill(value, (byte) 0);
        }
    }

    static CipherRecord encrypt(byte[] plain, SecretKey key,
            SecureRandom rng) throws GeneralSecurityException {
        byte[] iv = new byte[IV_BYTES];
        rng.nextBytes(iv);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
            new GCMParameterSpec(TAG_BITS, iv));
        return new CipherRecord(iv, cipher.doFinal(plain));
    }

    static byte[] decrypt(CipherRecord record, SecretKey key)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
            new GCMParameterSpec(TAG_BITS, record.iv()));
        return cipher.doFinal(record.ciphertextAndTag());
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        SecureRandom rng = new SecureRandom();
        char[] password = "educational-secret".toCharArray();
        char[] wrong = "other-secret".toCharArray();

        try {
            PasswordRecord record = hash(password, rng);
            System.out.println("hash.saltBytes="
                + record.salt().length);
            System.out.println("hash.correct="
                + matches(password, record));
            System.out.println("hash.wrong="
                + matches(wrong, record));

            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(128, rng);
            SecretKey key = generator.generateKey();

            byte[] plain = "retrievable-data".getBytes(
                StandardCharsets.UTF_8
            );
            CipherRecord encrypted = encrypt(plain, key, rng);
            byte[] restored = decrypt(encrypted, key);

            System.out.println("aes.roundTrip="
                + Arrays.equals(plain, restored));

            byte[] modified = encrypted.ciphertextAndTag().clone();
            modified[modified.length - 1] ^= 1;

            boolean rejected = false;
            try {
                decrypt(new CipherRecord(
                    encrypted.iv(), modified), key);
            } catch (AEADBadTagException expected) {
                rejected = true;
            }

            System.out.println("aes.tamperRejected=" + rejected);
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(wrong, '\0');
        }
    }
}
```

Chạy bằng JDK 17:

```bash
javac HashVsEncryption.java
java HashVsEncryption
```

**Stdout dự kiến đúng theo logic chương trình:**

```text
hash.saltBytes=16
hash.correct=true
hash.wrong=false
aes.roundTrip=true
aes.tamperRejected=true
```

Chương trình **không in** salt thật, hash thật, key, IV hoặc ciphertext nên các dòng trên không bị thay đổi bởi random input. Trên provider Java 17 hỗ trợ các thuật toán chuẩn được dùng, GCM tag bị sửa sẽ bị từ chối bằng `AEADBadTagException`.

### 9.2. Đọc kết quả đúng cách

- `PasswordRecord` lưu **salt + derived hash**. `matches` lấy salt đã lưu và thử candidate; không có decrypt password.
- `MessageDigest.isEqual` dùng để so mảng bytes theo cách phù hợp hơn `Arrays.equals` cho dữ liệu xác thực nhạy cảm.
- PBKDF2 có iterations để tăng chi phí thử password. 600.000 chỉ là tham số minh họa từ một hướng dẫn tại thời điểm viết, không thay thế benchmark/chính sách.
- `KeyGenerator` sinh key AES **128 bit** để minh họa; trong sản phẩm phải quản lý key có khả năng khôi phục và bảo vệ.
- `AES-GCM` dùng random IV 12 byte và tag 128 bit; gọi `decrypt` với key/IV đúng khôi phục plaintext.
- Việc lật byte cuối của ciphertext/tag khiến xác minh tag thất bại. Không được bỏ qua exception rồi trả dữ liệu không xác thực.
- `char[]` được xóa trong `finally`, nhưng password literal có sẵn trong source/class chỉ phù hợp cho demo; không hardcode secret thật.
- Với hệ thống mã hóa lượng dữ liệu lớn, phải bảo đảm nonce không trùng dưới cùng key; random 96-bit không phải là lời hứa tuyệt đối không xảy ra va chạm khi sử dụng vô hạn.

### 9.3. Điều gì xảy ra nếu mất key?

Nếu mất encryption key, ciphertext AES-GCM có thể không còn decrypt được. Nếu key bị lộ cùng ciphertext, người có key có thể đọc dữ liệu. Đó là lý do cần KMS, key rotation, truy cập tối thiểu và kế hoạch backup/recovery riêng cho encryption.

Password hash không có một key giải mã tương tự. Khi user quên password, hệ thống dùng quy trình reset; không phụ thuộc một master key để “mở” mọi mật khẩu.

## 10. Spring Boot 3: password storage bằng PasswordEncoder

Ví dụ sau dùng HTTP Basic để thấy rõ password được lưu bằng hash; khi xác thực, framework **so khớp** raw password với stored hash, không decrypt nó. Mã cho **Spring MVC/Servlet, Spring Boot 3 và Spring Security 6.x, Java 17+**.

Hai user demo:

| Tài khoản | Password cục bộ | Role |
| --- | --- | --- |
| `reader` | `reader-demo-pass` | `ROLE_USER` |
| `admin` | `admin-demo-pass` | `ROLE_USER` và `ROLE_ADMIN` |

Endpoint `GET /public` công khai; `GET /api/me` cần login; `GET /api/admin` cần role admin; request khác bị deny.

### 10.1. Dependency Gradle

Trong `build.gradle` Groovy DSL của dự án Spring Boot 3 có plugin/repository:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây chỉ là đoạn dependencies. Với Maven, dùng các starter tương đương và `spring-security-test` ở test scope. Không tự ghép version Spring Security không tương thích với Boot BOM.

### 10.2. Main class

Tạo `src/main/java/example/passwords/PasswordDemoApplication.java`:

```java
package example.passwords;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasswordDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasswordDemoApplication.class, args);
    }
}
```

### 10.3. SecurityConfig.java

Tạo `src/main/java/example/passwords/SecurityConfig.java`:

```java
package example.passwords;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-pass"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Phân tích:

1. `PasswordEncoderFactories.createDelegatingPasswordEncoder` tạo encoder; với factory mặc định Spring Security 6.x, hash mới có `{bcrypt}`.
2. `encoder.encode` chỉ dùng **khi tạo user demo** để lưu hash trong user store; ứng dụng thật gọi encode khi đăng ký/đổi password.
3. `UserDetailsService` tải user/hash, không tự so khớp raw password.
4. `DaoAuthenticationProvider` tích hợp với username/password authentication sẽ dùng `PasswordEncoder.matches` khi xác thực.
5. `.httpBasic` xử lý header Basic; Basic là **Base64**, không phải mã hóa bí mật; production bắt buộc HTTPS.
6. `.authorizeHttpRequests` là phân quyền, độc lập với hashing. User xác thực đúng vẫn có thể thiếu role.
7. `anyRequest().denyAll()` từ chối route không khai báo.
8. Không có đoạn nào decrypt stored password hash; `PasswordEncoder` không cung cấp API đó.
9. Các password hardcode chỉ dành cho localhost; với production cần user database và quản lý secret phù hợp.

### 10.4. Controller

Tạo `src/main/java/example/passwords/DemoController.java`:

```java
package example.passwords;

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
    Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/api/admin")
    Map<String, String> admin() {
        return Map.of("message", "admin");
    }
}
```

Controller nhận `Authentication` đã được provider xác minh. Nó không nhận raw password để tự so với DB, không trả password hash ra JSON và không có chức năng decrypt.

### 10.5. Chạy bằng Gradle

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Giả sử app ở `http://localhost:8080` cho demo:

```bash
# 200: endpoint public
curl -i http://localhost:8080/public

# 401: chưa cung cấp Basic credentials
curl -i http://localhost:8080/api/me

# 200: password reader đúng
curl -i -u reader:reader-demo-pass http://localhost:8080/api/me

# 401: password sai, không xác thực
curl -i -u reader:wrong-pass http://localhost:8080/api/me

# 403: reader đã xác thực nhưng thiếu ROLE_ADMIN
curl -i -u reader:reader-demo-pass http://localhost:8080/api/admin

# 200: admin có ROLE_ADMIN
curl -i -u admin:admin-demo-pass http://localhost:8080/api/admin
```

Đây là HTTP status **dự kiến** theo cấu hình mẫu, không phải log đã được chạy ở đây. Chỉ dùng password demo trên localhost. HTTP Basic dùng Base64 và `curl -u` có thể lộ credentials trong shell history/process list; ứng dụng thật phải sử dụng HTTPS và bảo vệ secret.

## 11. Kiểm thử password hash và HTTP authentication bằng MockMvc

Thêm `spring-boot-starter-test` và `spring-security-test` như phần dependency. Tạo `src/test/java/example/passwords/PasswordStorageTest.java`:

```java
package example.passwords;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordStorageTest {

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    UserDetailsService users;

    @Autowired
    MockMvc mvc;

    @Test
    void encodedValueIsNotPlaintext() {
        String hash = encoder.encode("sample-password");

        assertThat(hash).startsWith("{bcrypt}");
        assertThat(hash).isNotEqualTo("sample-password");
    }

    @Test
    void matchesChecksCorrectAndIncorrectPassword() {
        String hash = encoder.encode("sample-password");

        assertThat(encoder.matches("sample-password", hash)).isTrue();
        assertThat(encoder.matches("incorrect", hash)).isFalse();
    }

    @Test
    void saltedHashesForSamePasswordUsuallyDiffer() {
        String first = encoder.encode("sample-password");
        String second = encoder.encode("sample-password");

        assertThat(first).isNotEqualTo(second);
        assertThat(encoder.matches("sample-password", first)).isTrue();
        assertThat(encoder.matches("sample-password", second)).isTrue();
    }

    @Test
    void userStoreContainsHash() {
        String stored = users.loadUserByUsername("reader")
            .getPassword();

        assertThat(stored).startsWith("{bcrypt}");
        assertThat(encoder.matches("reader-demo-pass", stored)).isTrue();
    }

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk());
    }

    @Test
    void privateEndpointRejectsAnonymous() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void correctBasicPasswordAuthenticates() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "reader-demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("reader"));
    }

    @Test
    void wrongBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "wrong-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void passwordCorrectButRoleMissingIsForbidden()
            throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader-demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-demo-pass")))
            .andExpect(status().isOk());
    }
}
```

Chạy:

```bash
./gradlew test --tests example.passwords.PasswordStorageTest
```

Windows:

```powershell
.\gradlew.bat test --tests example.passwords.PasswordStorageTest
```

**Kỳ vọng:** 9 phương thức test pass với dự án Boot 3/Security 6.x đúng cấu hình. Đây là kết quả dự kiến theo source code, **chưa phải biên bản thực thi**. Test hai stored hashes khác nhau dựa trên random salt, nên về mặt toán học vẫn có xác suất collision cực kỳ nhỏ. Không hardcode toàn bộ hash output; mỗi lần encode hợp lệ có thể khác nhau.

| Test | Điều nó khẳng định |
| --- | --- |
| Hash không giống raw password | Không lưu password dạng plaintext |
| `matches` true/false | Verifier đúng/sai, không cần decrypt |
| Hai hash mới | Salt làm output thường khác |
| User store | `UserDetails.getPassword()` là encoded hash |
| HTTP Basic 200/401 | Provider kiểm tra credentials |
| Reader vs admin | Authorization độc lập với password verification |

`@WithMockUser` chỉ tạo Authentication giả trong test, không chứng minh password provider hoạt động. Dùng HTTP Basic, form login test hoặc gọi `AuthenticationManager.authenticate` khi muốn kiểm tra password thật.

## 12. Luồng database: đăng ký, đăng nhập, đổi password và reset

### 12.1. Đăng ký tài khoản

```text
HTTPS registration request
        |
        +-- Validate password policy
        +-- Check breached-password list theo chính sách
        +-- PasswordEncoder.encode(rawPassword)
        +-- Lưu password_hash và account metadata vào DB
        +-- Không lưu raw password/log/analytics
```

Ví dụ fragment trong service:

```java
String encoded = encoder.encode(request.password());
accountRepository.save(
    new Account(request.username(), encoded)
);
```

Fragment này cần `Account`, repository, validation và transaction thật. Không đưa raw password vào SQL rồi coi phép so sánh `WHERE password = ?` là xác thực an toàn.

### 12.2. Đăng nhập

```text
Client cung cấp password
       |
       v
AuthenticationProvider
       |
       +-- UserDetailsService.loadUserByUsername(username)
       |          -> password hash + authorities + flags
       |
       +-- PasswordEncoder.matches(raw, storedHash)
       |
       +-- Account state check (disabled/locked/expired...)
       |
       v
Authentication thành công hoặc exception
```

`UserDetailsService` chỉ nạp user/hash. `DaoAuthenticationProvider` và `PasswordEncoder` kiểm tra password; mã HTTP 401/302 xử lý bởi filter/entry point tùy cơ chế. Một user có mật khẩu đúng vẫn có thể nhận 403 khi thiếu authority.

### 12.3. Đổi password

Quy trình: xác minh quyền đổi password, xác minh lại credentials/MFA nếu cần, kiểm tra chính sách password mới, `encode(newPassword)`, cập nhật hash atomically và cân nhắc revoke những session/token đang hoạt động.

Không decrypt stored hash cũ, không gửi password cũ cho nhân viên hỗ trợ.

### 12.4. Quên password

Password recovery đúng nghĩa là **reset**:

1. User yêu cầu reset bằng một kênh hợp lệ; phản hồi tránh tiết lộ account tồn tại.
2. Server tạo reset token ngẫu nhiên entropy cao và thời hạn ngắn.
3. Lưu verifier/token hash và trạng thái dùng một lần; gửi token qua kênh thích hợp.
4. Khi token hợp lệ, user đặt password **mới**.
5. Server dùng `PasswordEncoder.encode` tạo hash mới rồi lưu.
6. Token reset bị vô hiệu và hệ thống có thể revoke session, audit, gửi thông báo.

Không có bước “giải mã hash để gửi password cũ”. Phương án mã hóa reversible chỉ nhằm khôi phục password là một thiết kế cần sửa.

## 13. Encryption at rest và password hashing có thể cùng tồn tại

Một hệ thống có thể mã hóa database/backup hoặc các cột nhạy cảm để giảm rủi ro khi kẻ xấu chỉ lấy storage. Nhưng password vẫn nên được hash ở tầng ứng dụng. Việc có disk encryption **không biến ciphertext password thành mô hình storage phù hợp cho login**.

Nếu database bị lộ:

| Cách lưu password | Attacker chỉ có DB | Nếu có thêm key app |
| --- | --- | --- |
| Plaintext | Đọc trực tiếp | Không cần key |
| AES-encrypted password | Có ciphertext; key có thể chưa có | Có thể giải mã hàng loạt |
| SHA-256/password | Thử đoán offline rất nhanh | Không cần key |
| Password KDF + random salt/cost | Vẫn đoán offline được, nhưng mỗi lần thử tốn hơn | Không có “decrypt key”; pepper nếu có là lớp riêng |

Salt thường public, nhưng password hash vẫn phải bảo vệ vì người khác có thể brute force. Security cần thêm password policy, MFA, rate limiting, bảo vệ cookies/sessions, TLS, chống credential stuffing, và **authorization** trên hành động/dữ liệu. **CSRF** cũng là lớp bảo vệ request trong các ứng dụng dùng cookie/session theo threat model; nó không thay hashing hoặc encryption.

## 14. Những lỗi dễ gặp khi triển khai

### 14.1. “Base64 password là đã mã hóa”

Không. Base64 là encoding; decoder chuẩn khôi phục bytes. HTTP Basic cũng dùng Base64 cho username/password, vì thế phải đi qua TLS/HTTPS.

### 14.2. “SHA-256 nhanh và mạnh nên tốt nhất”

SHA-256 là hàm hash mật mã nhanh; đối với password con người, **nhanh là bất lợi**. Chọn password KDF chuyên dụng.

### 14.3. “Thêm salt là đủ”

Salt tránh lặp/precomputation nhưng không làm SHA-256 trở thành password hashing chậm. Cần thuật toán và cost phù hợp.

### 14.4. “Có AES key thì quản trị viên có thể xem lại password”

Đó là khả năng không cần thiết và làm tăng hậu quả khi key bị lộ. Lưu password hash; hỗ trợ reset thay vì decrypt.

### 14.5. “Hai lần bcrypt encode phải có cùng String”

Sai vì có salt ngẫu nhiên. `matches` mới là API xác minh.

### 14.6. “Mất pepper thì lấy hash cũ giải mã ra rồi hash lại”

Không có phép decrypt. Nếu pepper rotation không có flow migrate qua login, có thể phải reset password.

### 14.7. “Không cần bảo vệ hash vì nó không phải password”

Password hash có giá trị cho offline guessing và có thể lộ thông tin về algorithm/cost. Hạn chế truy cập, tránh log và bảo vệ backups.

### 14.8. “Tôi có thể đặt AES-GCM IV cố định”

Không. Reuse nonce dưới cùng key phá các thuộc tính bảo mật. Cần chiến lược nonce an toàn.

### 14.9. “Cứ tăng bcrypt cost thật cao là an toàn”

Cost cao tăng chi phí mỗi login, có thể dẫn tới DoS hoặc trải nghiệm kém. Benchmark/cap concurrency và lên kế hoạch tăng dần.

### 14.10. “NoOpPasswordEncoder giúp bỏ lỗi id null”

`NoOpPasswordEncoder` không hash password, nên không phải giải pháp production. Sửa format/mapping và migration.

### 14.11. “Đặt encryption key trong cùng bảng là tiện”

Nếu attacker có quyền đọc cả ciphertext và key, encryption mất ý nghĩa. Sử dụng secret manager/KMS và quyền truy cập tối thiểu, có quy trình rotation.

### 14.12. “Có password hash là chống được phishing”

Hash bảo vệ password lưu trên server; không chống phishing, malware, session theft, MFA bypass hoặc role policy sai. Cần các lớp bảo vệ khác.

### 14.13. “Dùng cùng pepper và salt làm IV”

Salt, pepper và IV phục vụ những chức năng khác nhau. Không dùng một giá trị cố định thay cả ba.

### 14.14. “Mật khẩu dài hơn 72 ký tự luôn an toàn với bcrypt”

Ranh giới trong nhiều triển khai bcrypt là **72 byte**, không phải số ký tự Java. Kiểm tra giới hạn implementation và policy, không ngầm cắt nội dung.

### 14.15. “Dùng decrypt trong controller để kiểm tra login”

Controller không nên phải biết password lưu trữ. Spring Security authentication filter/provider gọi `PasswordEncoder.matches`; controller nhận principal đã xác thực.

## 15. Checklist bảo mật khi chọn cơ chế lưu trữ

**Password đăng nhập**

- Có dùng `PasswordEncoder`/adaptive password KDF, không lưu raw/encrypted reversible password để login?
- Có salt riêng và work factor phù hợp, được benchmark trên server?
- Có test `matches` với password đúng/sai và lưu hash không phải plaintext?
- Có format `{id}` hoặc metadata khác để migration?
- Có xử lý password dài, Unicode và giới hạn thuật toán đúng?
- Có ngăn log password, hash, token, Basic Authorization header?
- Có reset password an toàn và chính sách revoke session?
- Có bảo vệ DB backup, phân quyền đọc password_hash và audit?
- Có rate limiting/MFA/monitoring phù hợp với threat model?

**Dữ liệu phải giải mã**

- Nhu cầu business thật sự phải khôi phục plaintext?
- Có dùng thư viện AEAD đáng tin như AES-GCM và verify tag?
- Có key management KMS/vault/HSM, key version, rotation và backup?
- Nonce có đảm bảo uniqueness theo key, không hardcode?
- Có AAD/metadata binding khi cần, nhất là tenant và owner?
- Có hạn chế nơi được phép decrypt và audit?

**Kiểm chứng trong dự án**

- Kiểm tra đúng Spring Boot/Security version trong Gradle/Maven dependency graph.
- Chạy JUnit/MockMvc cho password đúng/sai, account disabled, thiếu authority.
- Không dùng `@WithMockUser` thay test password thật.
- Kiểm tra 401 do authentication và 403 do authorization/CSRF đúng nguyên nhân.
- Đo hiệu suất verify và mức dùng CPU/RAM, đặc biệt sau khi tăng work factor.
- Có kế hoạch xử lý dữ liệu legacy plaintext/NoOp/SHA-256 và migrate có kiểm soát.

## 16. Tự kiểm tra

**Câu 1.** Ứng dụng chỉ cần kiểm tra password mới nhập có đúng. Nên lưu password hash hay AES ciphertext?

**Câu 2.** Vì sao SHA-256 là hàm hash tốt nhưng không nên dùng một lần để lưu password?

**Câu 3.** Salt cần bí mật không? Pepper có khác salt không?

**Câu 4.** Hai user chọn cùng password. Vì sao BCrypt thường cho hai hash khác nhau?

**Câu 5.** Vì sao `encoder.encode(raw).equals(stored)` không phải cách đăng nhập đúng?

**Câu 6.** `{bcrypt}` trong `DelegatingPasswordEncoder` là key hay algorithm ID?

**Câu 7.** Nếu hệ thống dùng `DelegatingPasswordEncoder` và hash cũ thiếu `{id}`, cần kiểm tra gì?

**Câu 8.** Nếu user quên password, tại sao không decrypt hash để gửi lại?

**Câu 9.** AES-GCM cần gì để decrypt? Thành phần nào phải được giữ bí mật?

**Câu 10.** Vì sao nonce reuse dưới cùng key rất nguy hiểm với GCM?

**Câu 11.** Tại sao password KDF cố ý chậm, nhưng cost quá cao vẫn nguy hiểm?

**Câu 12.** Vì sao Base64 của HTTP Basic không bảo vệ password trên đường truyền?

**Câu 13.** Database bị lộ và chứa bcrypt hashes an toàn. Password có tuyệt đối không bị đoán không?

**Câu 14.** Encryption at rest đã bật, có cần lưu password hash ở tầng ứng dụng?

**Câu 15.** Token API ngẫu nhiên entropy cao có nhất thiết phải được xử lý y hệt mật khẩu con người?

**Câu 16.** `PasswordEncoder.matches` trả true có đủ để user đọc mọi dữ liệu trên server không?

**Đáp án gợi ý**

1. Password KDF một chiều với salt/cost phù hợp; không cần decrypt password cũ.
2. Vì quá nhanh cho việc attacker đoán password offline.
3. Salt không bí mật và thường riêng từng hash; pepper bí mật, ở ngoài DB.
4. BCrypt sinh salt ngẫu nhiên cho mỗi lần encode.
5. Salt mới làm chuỗi hash có thể khác; dùng `matches` với stored hash.
6. Algorithm ID giúp chọn delegate, không phải key.
7. Format/hash algorithm cũ, mapping encoder, migration phù hợp; không tắt verification.
8. Hash không có decrypt API; dùng quy trình password reset.
9. Key, nonce, ciphertext/tag; encryption key phải bí mật.
10. Có thể phá tính bí mật/toàn vẹn khi nonce trùng với key.
11. Chậm làm đoán offline đắt hơn nhưng quá chậm gây tải và DoS.
12. Base64 decode dễ dàng; cần HTTPS/TLS.
13. Không. Attacker vẫn có thể thử đoán candidate với salt, chỉ phải tốn chi phí hơn.
14. Có. Hai cơ chế bảo vệ những ranh giới khác nhau.
15. Không mặc định; entropy và threat model của token có thể khác password.
16. Không. Authorization (role, permission, owner, tenant) vẫn phải kiểm tra.

## 17. Tài liệu chính thức

- [Spring Security 6.5 – Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security – PasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [OWASP – Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP – Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)
- [OWASP – Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [Java SE 17 – JCA Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html)
- [NIST – Digital Identity Guidelines](https://pages.nist.gov/800-63-4/sp800-63b.html)
