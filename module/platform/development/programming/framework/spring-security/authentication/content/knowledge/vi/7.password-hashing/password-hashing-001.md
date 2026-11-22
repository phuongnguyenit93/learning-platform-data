# PasswordEncoder và sự khác biệt giữa băm với mã hóa có thể giải mã

Trong Spring Security, **`PasswordEncoder`** là hợp đồng dùng để **biến mật khẩu thành giá trị lưu trữ và kiểm tra mật khẩu người dùng nhập có khớp giá trị đã lưu hay không**. Đối với thuật toán lưu trữ mật khẩu phù hợp như bcrypt, scrypt, PBKDF2 hoặc Argon2id, phép biến đổi này là **một chiều**: ứng dụng không cần — và không nên có — phương thức “giải mã hash để lấy lại mật khẩu”.

**Mã hóa có thể giải mã (reversible encryption)** là việc khác: dữ liệu được biến thành ciphertext bằng khóa, và bên giữ khóa hợp lệ có thể giải mã lại plaintext. Mã hóa phù hợp với những bí mật **thực sự cần được khôi phục** (chẳng hạn credential kết nối đến một hệ thống ngoài), nhưng **không phải lựa chọn mặc định để lưu password đăng nhập của người dùng**.

Bài học thuộc nhóm **Băm mật khẩu** của Spring Security Authentication. Sau bài này, bạn sẽ hiểu các hợp đồng `encode`, `matches`, `upgradeEncoding`; salt và work factor; sự khác biệt giữa hashing, encryption và encoding; `BCryptPasswordEncoder` và `DelegatingPasswordEncoder`; tích hợp đăng ký/đăng nhập; cách nâng cấp hash; ví dụ Java 17 chạy được; kiểm thử và các lỗi bảo mật thường gặp.

## 1. Ba khái niệm phải phân biệt ngay

| Cơ chế | Có thể lấy lại plaintext trực tiếp? | Mục tiêu | Ví dụ |
|---|---|---|---|
| **Encoding** (biểu diễn) | **Có**, bằng cách decode; không cần khóa bí mật | Đổi định dạng để truyền/lưu | Base64, URL encoding, hex |
| **Encryption** (mã hóa) | **Có**, khi có khóa giải mã hợp lệ | Bảo mật nội dung cần dùng lại | AES-GCM cho API secret cần được phục hồi |
| **Password hashing / KDF** | **Không có thao tác giải mã ngược** | Kiểm chứng password mà không giữ bản gốc | Argon2id, bcrypt, scrypt, PBKDF2 |

Điểm tinh tế: hash không phải phép toán "không ai có thể suy ra password". Kẻ lấy được hash vẫn có thể **đoán nhiều mật khẩu**, dùng cùng thuật toán để kiểm tra từng ứng viên và thực hiện **tấn công offline**. Thuật toán password hashing tốt tạo chi phí tính toán/tài nguyên đủ cao để khiến việc thử hàng loạt ứng viên đắt đỏ hơn. Vì thế không chỉ “dùng hash” mà còn phải chọn thuật toán, salt và chi phí phù hợp.

### 1.1. Vì sao Base64 không phải bảo mật?

~~~text
Plaintext: password123
Base64   : cGFzc3dvcmQxMjM=
Decode   : password123
~~~

Base64 chỉ đổi cách biểu diễn. Bất kỳ ai có chuỗi Base64 đều có thể khôi phục plaintext ngay mà không cần secret. Một giá trị `{base64}...` hoặc Base64 ciphertext không chứng minh đã được băm mật khẩu an toàn.

### 1.2. Hash mật khẩu khác hash checksum

Một ứng dụng có thể tính `SHA-256` cho file để nhận biết file có thay đổi hay không. Nhưng SHA-256 được thiết kế **rất nhanh**; dùng `SHA-256(password)` trực tiếp cho lưu trữ mật khẩu sẽ giúp kẻ tấn công thử một lượng lớn mật khẩu ứng viên nhanh chóng.

Thuật toán password hashing được thiết kế **tốn tài nguyên có chủ đích**. Ví dụ:

- **Argon2id:** memory-hard, có tham số memory/time/parallelism; OWASP khuyến nghị ưu tiên khi hệ thống hỗ trợ.
- **scrypt:** memory-hard; lựa chọn thay thế thích hợp.
- **bcrypt:** phổ biến và được Spring Security hỗ trợ trực tiếp; có cost parameter và lưu ý giới hạn đầu vào.
- **PBKDF2:** tính nhiều vòng, có các cấu hình dùng cho môi trường cần tuân thủ chuẩn/FIPS phù hợp.

Hash SHA-256 có salt thủ công như `SHA256(salt || password)` vẫn thiếu khả năng làm chậm brute force như các password KDF thích hợp. HMAC-SHA-256 hoặc SHA-256 cũng không trở thành password-hashing scheme tốt chỉ vì bạn “hash nhiều thứ chung vào”.

## 2. Hợp đồng PasswordEncoder: encode, matches, upgradeEncoding

Giao diện `org.springframework.security.crypto.password.PasswordEncoder` về cơ bản là:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);

    boolean matches(CharSequence rawPassword, String encodedPassword);

    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

Đây là **chữ ký rút gọn của framework**, không phải class độc lập cần bạn tự viết. Hãy nắm rõ:

1. **`encode(rawPassword)`:** tạo một giá trị có thể lưu để kiểm tra password sau này. Với bcrypt và các thuật toán hiện đại có salt ngẫu nhiên, hai lần gọi với cùng password **thường cho hai chuỗi hash khác nhau**.
2. **`matches(rawPassword, encodedPassword)`:** dùng password nhập mới và giá trị đã lưu để kiểm tra khớp hay không. Nó **không giải mã hash** và không yêu cầu biết password gốc từ database.
3. **`upgradeEncoding(encodedPassword)`:** hỗ trợ kiểm tra hash cũ có nên được tạo lại theo cấu hình/thuật toán hiện tại hay không. Method mặc định của interface trả `false`; từng encoder có thể override.

### 2.1. Đừng dùng encode lần nữa rồi so bằng equals

**Sai:**

~~~java
String newHash = encoder.encode(submittedPassword);
boolean ok = storedHash.equals(newHash);
~~~

**Đúng:**

~~~java
boolean ok = encoder.matches(submittedPassword, storedHash);
~~~

Cả hai đoạn chỉ là **minh họa**, giả định biến đã được cung cấp. Với bcrypt, `encode` sinh salt ngẫu nhiên mỗi lần; việc so sánh hai chuỗi hash tạo mới với nhau có thể thất bại **dù password hoàn toàn đúng**. `matches` đọc salt/thông số cần thiết từ encoded hash và thực hiện phép kiểm tra theo thuật toán.

### 2.2. Luồng register và login chuẩn

~~~text
ĐĂNG KÝ / THAY ĐỔI MẬT KHẨU
Client password mới --TLS--> Application
       |
       +--> Validate policy, bảo vệ log và giới hạn input
       +--> passwordEncoder.encode(rawPassword)
       +--> Lưu encodedPassword vào password_hash trong DB
       '--> Không lưu rawPassword vào DB/session/log

ĐĂNG NHẬP
Client password nhập --TLS--> Authentication Filter
       |
       +--> DaoAuthenticationProvider
       |        +--> UserDetailsService tải UserDetails từ DB
       |        +--> PasswordEncoder.matches(raw, storedHash)
       |        +--> Kiểm tra account/credential status
       |        '--> Authentication thành công hoặc lỗi
       |
       '--> Filter/handler quản lý SecurityContext + session/token
~~~

`UserDetailsService` chịu trách nhiệm **tải dữ liệu**, không phải “giải mã mật khẩu”. Trong một ứng dụng dùng `DaoAuthenticationProvider`, bạn phải cấu hình cùng một chính sách `PasswordEncoder` tương thích với format hash đã lưu, nếu không người dùng có thể bị từ chối dù nhập đúng mật khẩu.

**Password hash không phải token đăng nhập**: biết hash của ai đó không nên cho phép gửi hash như password trực tiếp qua API. Luôn phân biệt raw password nhập từ người dùng và encoded hash nằm trong data store. Không thiết kế “pass-the-hash” như một phương thức login vô tình được chấp nhận.

## 3. Salt, cost và format của hash được lưu

### 3.1. Salt là gì?

**Salt** là giá trị ngẫu nhiên được dùng riêng cho từng hash. Nó giúp hai account có cùng password không có hash giống nhau và cản những bảng tính sẵn (rainbow tables). Salt **không cần giữ bí mật**, thường được mã hóa **bên trong chính chuỗi hash** cùng tham số thuật toán.

Ví dụ format bcrypt trông như:

~~~text
$2a$10$<22 ký tự salt theo định dạng bcrypt><phần hash còn lại>
       | 
       +-- cost = 10 (mang tính minh họa)
~~~

Chuỗi trên là sơ đồ cấu trúc, **không phải bcrypt hash hợp lệ dùng trực tiếp để kiểm tra**. Hash thực có phần prefix/cost/salt/checksum được mã hóa theo quy định thuật toán. Khi tạo bằng `BCryptPasswordEncoder`, thông thường bạn lưu **nguyên chuỗi `encode(...)`** vào cột password_hash, không tách thủ công salt và hash, cũng không tạo salt bằng `Math.random()`.

### 3.2. Tại sao hash giống mật khẩu lại khác nhau?

~~~text
Password A = "same-password"
Password B = "same-password"

Hash A = bcrypt(password, randomSaltA, cost)
Hash B = bcrypt(password, randomSaltB, cost)

SaltA != SaltB (với xác suất rất cao)
=> Chuỗi encoded hash khác nhau dù plaintext giống nhau
~~~

Không cần kiểm tra tính ngẫu nhiên bằng cách so sánh hai hash bằng `equals` trong test bắt buộc: xác suất trùng salt ngẫu nhiên rất nhỏ nhưng về logic không phải tính chất bất khả. Hãy kiểm tra bằng `matches` đối với từng hash và kiểm tra thư viện sử dụng CSPRNG.

### 3.3. Work factor là gì?

Password hashing tốt cố ý gây tốn chi phí xử lý. BCrypt có work factor gọi là **cost**, làm chi phí tính toán tăng mạnh khi tăng tham số. Lựa chọn cost phải được benchmark trên hardware production, bảo đảm đủ khó cho offline cracking nhưng không làm login nghẽn CPU hoặc dễ bị từ chối dịch vụ.

Ví dụ:

~~~java
PasswordEncoder bcrypt = new BCryptPasswordEncoder(12);
~~~

Là **đoạn cấu hình minh họa**, không phải chương trình độc lập. Cost 12 không phải con số tối ưu phổ quát. Hãy đo thời gian `matches` dưới concurrency thật và chọn theo chính sách bảo mật hiện hành. Một thuật toán quá nhanh dễ bị tấn công offline; một cấu hình quá nặng mà không có rate limiting có thể khiến endpoint login bị DoS.

### 3.4. Giới hạn 72 byte của bcrypt

Nhiều implementation bcrypt chỉ xử lý tối đa **72 byte đầu vào**. Byte không đồng nghĩa số ký tự: chuỗi Unicode có thể dùng nhiều byte UTF-8 cho một ký tự. Nếu ứng dụng nhận password dài hơn mà encoder xử lý cắt bớt, hai password có phần đầu giống nhau có thể được coi là trùng sau điểm giới hạn.

Không tự ý pre-hash `SHA-256(password)` rồi đưa vào bcrypt như một “mẹo” mà chưa hiểu password shucking, null byte, output encoding và policy upgrade. Ưu tiên thuật toán/implementation hỗ trợ chiều dài phù hợp, hoặc giới hạn input và giải thích rõ quy định trên backend; bảo đảm người dùng không bị cắt password âm thầm. Khi đổi thuật toán, phải kiểm tra tương thích hash cũ và phiên bản thư viện.

### 3.5. Pepper khác salt thế nào?

**Pepper** là một bí mật **chung của hệ thống hoặc một nhóm credential** được giữ **tách khỏi DB** (secret manager/HSM/KMS) nhằm tăng phòng vệ nếu chỉ DB bị lộ. Salt là giá trị công khai riêng từng hash và thường được lưu chung hash.

| Yếu tố | Salt | Pepper |
|---|---|---|
| Có cần bí mật? | Không | **Có** |
| Tính theo từng user/hash? | Thường riêng từng hash | Thường là bí mật cấp hệ thống hoặc theo phiên bản |
| Nơi lưu | Trong encoded hash | Secret manager/HSM hoặc cơ chế quản lý secret khác |
| Nếu mất giá trị | Hash thường không kiểm tra được nếu salt không có trong format | Phải có recovery/rotation policy; có thể buộc người dùng reset |
| Thay password KDF mạnh được không? | Không | Không |

Nếu thêm pepper, cần thiết kế crypto construction rõ (chẳng hạn HMAC trên đầu ra phù hợp, lưu ý nguồn bí mật), versioning, rotation và kiểm tra khi login. Đừng tự “nối pepper vào password” bằng một công thức tùy tiện rồi cho rằng an toàn; ưu tiên cách được tài liệu/đội bảo mật thẩm định.

## 4. BCryptPasswordEncoder và DelegatingPasswordEncoder

Spring Security có sẵn `BCryptPasswordEncoder`, cho phép kiểm tra bcrypt hash và điều chỉnh work factor.

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder(10);

String hash = encoder.encode("example-password");
boolean ok = encoder.matches("example-password", hash);
~~~

Đây là đoạn Java minh họa; cần imports `PasswordEncoder`, `BCryptPasswordEncoder`. Ở một luồng register, hash được lưu ở DB; ở login, backend lấy hash của account tương ứng rồi dùng `matches`. Hash chứa salt, không cần tạo một cột `salt` độc lập cho bcrypt theo format chuẩn.

### 4.1. Vì sao cần DelegatingPasswordEncoder?

Dự án lâu đời có thể lưu password bằng nhiều thuật toán khác nhau, ví dụ:

~~~text
{bcrypt}$2a$10$...  -> encoder bcrypt
{pbkdf2}...         -> encoder tương ứng với ID pbkdf2
{scrypt}...         -> encoder scrypt
{argon2}...         -> encoder Argon2
~~~

Đây là chuỗi **minh họa format**, không phải hash cụ thể dùng để login. `DelegatingPasswordEncoder` lưu theo format:

~~~text
{id}encodedPassword
~~~

- `id` xác định encoder có trách nhiệm `matches`.
- `encodedPassword` là dữ liệu của thuật toán đó; có thể chứa salt và cost.
- Cấu hình `idForEncode` quyết định thuật toán cho **password mới**.
- Khi `matches`, encoder chọn thuật toán theo `{id}` trong dữ liệu đã lưu.

Spring Security có factory thông dụng:

~~~java
PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

Với mapping mặc định thông thường, password mới được tạo bằng bcrypt và nhận prefix `{bcrypt}`. Điều này làm tăng tính linh hoạt cho việc chuyển đổi thuật toán trong tương lai mà không làm hỏng tất cả hash cũ ngay lập tức.

**Lưu ý:** Mapping mặc định có thể hỗ trợ các encoder yếu/legacy, kể cả ID `{noop}` phục vụ tương thích/migration. Việc một encoder **có thể đọc** không có nghĩa được phép dùng để **tạo hash mới** trong production. Luồng đăng ký mới phải dùng encoder mạnh đang được duyệt.

### 4.2. Lỗi “There is no PasswordEncoder mapped for id null”

Nếu DB chứa bcrypt hash thuần, ví dụ bắt đầu `$2a$...`, nhưng ứng dụng cấu hình `DelegatingPasswordEncoder` đang mong chờ `{id}...`, việc gọi `matches` có thể ném `IllegalArgumentException` vì không xác định được ID (null). Cũng có thể xảy ra nếu dùng ID không có trong mapping.

Không nên “sửa nhanh” bằng `NoOpPasswordEncoder` hoặc bằng cách biến mọi hash không ID thành plaintext. Nếu đã **xác minh chắc chắn** tất cả row legacy đó là bcrypt hợp lệ, một migration có thể thêm prefix `{bcrypt}` vào chuỗi **mà không tính lại hash**:

~~~text
Trước: $2a$10$...stored bcrypt...
Sau  : {bcrypt}$2a$10$...stored bcrypt...
~~~

Đây là biểu diễn rút gọn, không phải SQL migration có thể chạy trực tiếp. Trong production phải kiểm kê format theo từng row, backup, test matches với test credentials đã biết và dùng migration idempotent; không prepend lặp prefix khi chạy nhiều lần.

### 4.3. Có thể dùng fallback encoder không?

`DelegatingPasswordEncoder` cho phép cấu hình `setDefaultPasswordEncoderForMatches(...)` để xử lý hash thiếu ID. Nhưng lựa chọn fallback cần bảo đảm **đúng format legacy đã biết**, không mở đường cho `{noop}` hoặc raw password bị coi là hash hợp lệ. Nên ưu tiên format có ID rõ, migration theo lộ trình và kiểm thử đa phiên bản trước/sau rollout.

Đổi thuật toán cần phân biệt:

- **Đọc hash cũ:** sử dụng encoder tương thích theo ID đã lưu.
- **Ghi hash mới:** dùng thuật toán/work factor được phê duyệt tại thời điểm hiện tại.
- **Nâng cấp hash:** chỉ sau khi xác minh đúng raw password trong một luồng an toàn mới có đủ thông tin tạo hash mới.

## 5. Ví dụ Java 17 chạy được: one-way hashing và reversible encryption

Ví dụ này cố ý đặt hai kỹ thuật bên cạnh nhau:

1. **Spring Security BCrypt/DelegatingPasswordEncoder:** tạo và kiểm tra hash, **không có thao tác decrypt password**.
2. **Java Cryptography API với AES-GCM:** mã hóa một chuỗi minh họa, rồi dùng **khóa hợp lệ** giải mã lại plaintext. Đây là ví dụ cho bí mật cần khôi phục, **không khuyến nghị AES-GCM để lưu mật khẩu đăng nhập**.

Để stdout ổn định, chương trình **không in ciphertext, salt hoặc raw bcrypt hash** (chúng được ngẫu nhiên hóa). Chỉ in boolean và trạng thái được xác định bởi cấu hình.

### 5.1. Cấu trúc dự án

~~~text
password-encoder-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/PasswordEncoderDemo.java
~~~

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'password-encoder-demo'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-crypto:6.3.8'
    implementation 'org.springframework.security:spring-security-core:6.3.8'
}

application {
    mainClass = 'example.PasswordEncoderDemo'
}
~~~

Demo chỉ cần Java 17, Spring Security Core/Crypto và Gradle; không cần Spring Boot, Servlet, JPA hay database. Trong ứng dụng Spring Boot thực, phiên bản Spring Security thường được quản lý bởi BOM thay vì pin trực tiếp như ví dụ console.

### 5.2. Chương trình Java đầy đủ

Tạo `src/main/java/example/PasswordEncoderDemo.java`:

~~~java
package example;

import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PasswordEncoderDemo {

    public static void main(String[] args) throws Exception {
        String rawPassword = "Study!Password#2026";

        // Password hashing: one-way, với salt và cost của bcrypt.
        PasswordEncoder bcrypt = new BCryptPasswordEncoder(10);
        String storedHash = bcrypt.encode(rawPassword);

        System.out.println("bcrypt format -> "
                + storedHash.startsWith("$2"));
        System.out.println("bcrypt correct -> "
                + bcrypt.matches(rawPassword, storedHash));
        System.out.println("bcrypt wrong -> "
                + bcrypt.matches("wrong-password", storedHash));

        // Delegating encoder có ID để chọn thuật toán khi verify.
        PasswordEncoder delegating =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();
        String tagged = delegating.encode(rawPassword);

        System.out.println("delegating prefix -> "
                + tagged.startsWith("{bcrypt}"));
        System.out.println("delegating correct -> "
                + delegating.matches(rawPassword, tagged));
        System.out.println("legacy bcrypt with id -> "
                + delegating.matches(rawPassword, "{bcrypt}" + storedHash));

        // Hash cost=10 được xem là cần nâng cấp nếu policy cost=12.
        BCryptPasswordEncoder strongerBcrypt =
                new BCryptPasswordEncoder(12);
        System.out.println("bcrypt needs upgrade -> "
                + strongerBcrypt.upgradeEncoding(storedHash));

        // Reversible encryption: ví dụ secret phải đọc lại, KHÔNG
        // dùng thay password hashing khi lưu password đăng nhập.
        String serviceSecret = "demo-external-service-secret";
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        GCMParameterSpec params = new GCMParameterSpec(128, nonce);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, key, params);
        byte[] ciphertext = encrypt.doFinal(
                serviceSecret.getBytes(StandardCharsets.UTF_8));

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE, key, params);
        byte[] restoredBytes = decrypt.doFinal(ciphertext);
        String restored = new String(
                restoredBytes, StandardCharsets.UTF_8);

        System.out.println("AES-GCM decryptable -> "
                + serviceSecret.equals(restored));
    }
}
~~~

### 5.3. Chạy và stdout

Có Gradle Wrapper tại thư mục project thì chạy:

~~~bash
./gradlew run
~~~

Nếu chưa có wrapper nhưng đã cài Gradle phù hợp, dùng `gradle run`. Trong Windows PowerShell với wrapper, dùng `.\gradlew.bat run`.

Đầu ra của **các lệnh `System.out.println`** trong chương trình (không tính log Gradle):

~~~text
bcrypt format -> true
bcrypt correct -> true
bcrypt wrong -> false
delegating prefix -> true
delegating correct -> true
legacy bcrypt with id -> true
bcrypt needs upgrade -> true
AES-GCM decryptable -> true
~~~

Tại sao các dòng đúng?

- `BCryptPasswordEncoder(10)` tạo bcrypt hash với format bắt đầu `$2...`; `matches` đúng với raw password ban đầu, sai với password khác.
- Factory `createDelegatingPasswordEncoder()` của Spring Security 6.3 dùng bcrypt cho việc encode mới và thêm prefix `{bcrypt}`; `matches` đọc prefix để chọn đúng encoder.
- Ghép `"{bcrypt}" + storedHash` mô phỏng **gắn ID vào bcrypt hash legacy đã biết format**, giúp delegating encoder kiểm tra bằng thuật toán tương ứng.
- `BCryptPasswordEncoder(12).upgradeEncoding(storedHash)` báo cần nâng cấp khi hash cũ có cost 10 thấp hơn 12.
- AES-GCM **giải mã được** vì chương trình còn khóa `key`, nonce `nonce` và ciphertext; bcrypt không có một method `decrypt` tương đương.

**Giới hạn ví dụ AES-GCM:** khóa và nonce được sinh trong RAM để minh họa phép roundtrip. Hệ thống thật phải quản lý khóa qua KMS/HSM/secret manager; bảo đảm **không tái sử dụng nonce với cùng khóa GCM**, lưu nonce cùng ciphertext theo format có version, cân nhắc AAD và thay khóa. Nếu mất khóa, ciphertext có thể không khôi phục được; nếu khóa bị lộ, kẻ tấn công có thể giải mã. **Không ghi khóa vào source code hoặc cùng bảng dữ liệu mà không có chiến lược bảo vệ.**

### 5.4. Vì sao đây không phải "decrypt hash"?

`PasswordEncoder.matches(...)` kiểm tra một password ứng viên với hash lưu trữ. Nó **không** tìm ra plaintext ban đầu. Mặt khác, `Cipher.DECRYPT_MODE` phải có khóa hợp lệ và nonce/phần dữ liệu cần thiết; nó trả plaintext nếu xác thực ciphertext thành công. Hai API giải quyết **hai nhu cầu hoàn toàn khác nhau**.

Ở password hashing, dù không giải mã ngược được hash, người có hash vẫn có thể đoán password phổ biến và thử offline. Đó là lý do phải dùng KDF chậm, kiểm soát reset, rate limiting và mật khẩu có entropy hợp lý.

## 6. Tích hợp với Spring Security Authentication

### 6.1. Bean PasswordEncoder dùng cho đăng ký và đăng nhập

Một cấu hình Spring Boot minh họa:

~~~java
@Configuration
class SecurityBeans {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
~~~

Đoạn trên **không phải project độc lập**, cần dependency `spring-boot-starter-security`, imports và cấu hình ứng dụng. Bean encoder nên được dùng nhất quán cho password mới và provider kiểm tra login. Không tạo mỗi request một policy/encoder tùy ý mà không quản lý version hash.

### 6.2. Đăng ký: chỉ lưu kết quả encode

~~~java
public UUID register(String username, String rawPassword) {
    validatePasswordPolicy(rawPassword);

    String hash = passwordEncoder.encode(rawPassword);
    Account account = new Account(
            UUID.randomUUID(), username, hash);

    return accountRepository.save(account).getId();
}
~~~

Đây là **đoạn tích hợp minh họa**; `validatePasswordPolicy`, `Account`, `accountRepository` và bean phải tồn tại, chưa gồm transaction, unique constraint hay xác minh email. Giới hạn input, bảo vệ rate limit và policy password là trách nhiệm của ứng dụng.

Trong database, lưu một cột password hash đủ dài cho format có ID và tham số tương lai (ví dụ `TEXT`), không dùng cột quá ngắn khiến encoded hash bị cắt. Hash không phải dữ liệu để hiển thị cho client: response DTO phải loại password hash.

### 6.3. Đăng nhập: provider so với hash đã lưu

~~~java
@Bean
AuthenticationProvider usernamePasswordProvider(
        UserDetailsService users,
        PasswordEncoder passwordEncoder) {

    DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider();
    provider.setUserDetailsService(users);
    provider.setPasswordEncoder(passwordEncoder);
    return provider;
}
~~~

Đây là mảnh cấu hình cho Spring Security 6.3.x, **không biên dịch độc lập** nếu thiếu imports, annotations và dependencies. Ở những phiên bản Spring Security mới hơn, API khởi tạo provider có thể đổi/được khuyến nghị dùng constructor nhận `UserDetailsService`; phải tra JavaDoc đúng phiên bản ứng dụng.

`UserDetailsService` tải `UserDetails` chứa **encoded password** và trạng thái account. `DaoAuthenticationProvider` gọi encoder để so sánh raw password từ yêu cầu với hash; nếu thành công, provider trả `Authentication` đáng tin và filter quản lý `SecurityContext`. Không tự trả `Authentication` đã được xác thực chỉ vì username tồn tại.

### 6.4. Mất mật khẩu thì phải reset, không giải mã

Vì hash mật khẩu không thể giải mã trực tiếp, hỗ trợ người dùng quên password bằng **password reset flow**, không gửi lại mật khẩu cũ:

1. Nhận yêu cầu và trả thông điệp công khai không làm lộ account có tồn tại.
2. Xác minh quyền sở hữu qua kênh/quy trình phù hợp, cấp token reset có entropy cao, thời hạn ngắn, dùng một lần.
3. Lưu token reset theo cơ chế an toàn (thường lưu dạng hash hoặc dữ liệu có thể kiểm tra), rate limit và ghi audit phù hợp.
4. Sau khi xác minh token, nhận password mới theo policy và `passwordEncoder.encode(newPassword)`.
5. Cập nhật hash mới theo transaction và chính sách revoke session/refresh token hoặc thông báo bảo mật.
6. Không lưu/gửi password mới trong log/email, không dùng reset token lâu dài làm API access token.

**Nếu ai đó yêu cầu “giải mã password người dùng để gửi email hỗ trợ” thì đó là dấu hiệu thiết kế lưu trữ password sai.**

## 7. Nâng cấp hash khi chính sách thay đổi

Work factor phù hợp năm trước có thể trở nên quá nhẹ trên hardware mới. Nhiều hệ thống cũng chuyển từ hash legacy sang Argon2id hoặc tăng cost bcrypt. Do hashing là một chiều, **không thể tạo hash thuật toán mới từ hash cũ mà vẫn xác minh cùng password**, trừ các cơ chế đặc biệt được thiết kế từ trước. Thông thường phải có **raw password vừa được người dùng nhập đúng**, hoặc yêu cầu họ reset.

### 7.1. Ý nghĩa của upgradeEncoding

~~~java
if (encoder.matches(rawPassword, storedHash)
        && encoder.upgradeEncoding(storedHash)) {
    String strongerHash = encoder.encode(rawPassword);
    // Lưu strongerHash theo transaction và chính sách an toàn.
}
~~~

Đây là **logic minh họa**, không phải service runnable độc lập. `upgradeEncoding` chỉ là tín hiệu cần xem xét tái mã hóa; không tự ghi database. Với `DelegatingPasswordEncoder`, tín hiệu có thể liên quan ID format cũ; với `BCryptPasswordEncoder`, có thể liên quan cost thấp. Luôn dùng đúng encoder mới đã được phê duyệt cho việc tạo hash mới.

### 7.2. Những việc phải bảo đảm khi rehash

- Chỉ rehash **sau khi xác thực raw password thành công**, không tin raw password chưa được kiểm chứng.
- Không dùng hash cũ như một “raw password” để hash lại: `encode(storedHash)` không bảo đảm người dùng có thể dùng password ban đầu để đăng nhập.
- Khi nhiều login cùng lúc hoặc user reset password, dùng optimistic lock/CAS theo version hoặc hash cũ. Tránh một request rehash cũ ghi đè password vừa được đổi.
- Cập nhật hash trong transaction và xử lý cache/session theo policy; không làm người dùng đăng nhập thất bại chỉ vì chiến lược upgrade không hoàn tất, nhưng ghi nhận lỗi vận hành phù hợp.
- Khi đổi sang thuật toán khác, đảm bảo các node cũ còn đọc được hash mới trong giai đoạn rolling deployment, hoặc triển khai theo thứ tự tương thích.
- Tài khoản lâu không đăng nhập có thể không được rehash. Có thể đặt policy yêu cầu reset khi quay lại hoặc khi hash quá cũ.

### 7.3. Không tự ghi nhãn sai format

Nếu một row là SHA-256 không salt, thêm prefix `{bcrypt}` **không biến nó thành bcrypt**. Nếu một row đã là `{bcrypt}$2a$...`, prepend thêm `{bcrypt}` lần nữa cũng làm sai format. Migration phải phân loại theo thực tế dữ liệu lưu, xây test case cho từng format và có rollback/metrics.

### 7.4. Ví dụ policy trên một hệ thống lâu năm

~~~text
Database ban đầu:
  account A: {bcrypt}... (cost 10)
  account B: {bcrypt}... (cost 12)
  account C: {legacy}... (thuật toán cũ đã kiểm kê)

Policy mới:
  Password mới -> encoder mới được duyệt
  Login A      -> matches đúng -> xác định upgrade -> rehash an toàn
  Login B      -> có thể giữ nguyên nếu policy đáp ứng
  Login C      -> xác minh với legacy adapter được kiểm soát -> rehash
  Không login  -> chờ reset/upgrade theo chính sách
~~~

Đừng để một `legacy` decoder không rõ nguồn gốc hoặc `NoOpPasswordEncoder` làm fallback mở cho mọi chuỗi không gắn ID. Nếu dữ liệu từng lưu plaintext, đó là rủi ro nghiêm trọng cần xử lý riêng, kể cả đánh giá incident và ép reset khi phù hợp.

## 8. Password hashing vẫn cần nhiều lớp bảo vệ

**Băm mạnh không thay thế được các biện pháp phòng vệ khác.**

| Rủi ro | Biện pháp bổ sung |
|---|---|
| Nghe lén password khi gửi request | TLS/HTTPS, cấu hình proxy/header/cookie đúng |
| Password bị log hoặc gửi trong URL | Không log request body/Authorization chứa bí mật; dùng form/body qua HTTPS |
| User dùng mật khẩu yếu/tái sử dụng | Chính sách độ dài, blocklist password phổ biến/bị lộ, MFA |
| Online brute force/password spraying | Rate limiting, theo dõi bất thường, lockout/risk-based throttling hợp lý |
| Rò database hash | Adaptive KDF, salt riêng, cost phù hợp, optional pepper đúng cách |
| Kẻ tấn công khai thác CPU login | Giới hạn request/body và concurrency, benchmark cost, rate limiting |
| Hash được trả qua API | DTO loại trường passwordHash, least privilege DB, audit và redaction |
| Thay hash bằng dữ liệu do client gửi | Validate quy trình reset, không cho client tự chọn hash như credential hợp lệ |
| Cache `UserDetails` bị thay đổi sau login | Tách object cache khỏi authentication principal, quản lý `eraseCredentialsAfterAuthentication` |
| Session/JWT vẫn còn sau đổi mật khẩu | Session/token revocation, rotation, authentication versioning theo yêu cầu |

### 8.1. Salt có làm hash trở thành an toàn tuyệt đối?

Không. Salt hạn chế lợi thế từ bảng hash tính sẵn và làm hash giữa các account khác nhau; nó **không tăng entropy password** của người dùng. Password quá phổ biến vẫn có thể đoán được bằng brute force offline. KDF chậm chỉ tăng chi phí của mỗi lần đoán. Vì vậy mật khẩu mạnh, MFA, chính sách phát hiện password bị lộ và phòng thủ theo lớp vẫn cần thiết.

### 8.2. Tại sao mã hóa password bằng AES-GCM chưa đủ?

Nếu ứng dụng mã hóa mật khẩu bằng AES-GCM và giữ khóa giải mã cùng môi trường cần đăng nhập, kẻ có cả database và khóa (hoặc chiếm quyền service) có thể **khôi phục plaintext của toàn bộ password**. Password là bí mật mà server chỉ cần **kiểm chứng**, không cần biết lại bản gốc sau đăng ký. Băm một chiều giúp tránh một điểm khôi phục hàng loạt như vậy, dù không loại bỏ hoàn toàn khả năng dò offline.

AES-GCM vẫn rất hữu ích khi một giá trị **cần phục hồi** (ví dụ token của nhà cung cấp mà server phải gửi lên API ngoài), với key management và access control đúng. Đừng chuyển một yêu cầu xác thực mật khẩu thành một yêu cầu có thể giải mã chỉ vì “AES mạnh”.

### 8.3. Nên dùng Argon2id hay bcrypt?

OWASP hiện khuyến nghị ưu tiên Argon2id cho password storage khi môi trường hỗ trợ, scrypt khi cần lựa chọn memory-hard khác, bcrypt khi phải hỗ trợ hệ thống cũ/điều kiện phù hợp và PBKDF2 cho các trường hợp tuân thủ liên quan. Spring Security cung cấp encoder tương ứng, nhưng một số implementation như Argon2 có thể cần dependency crypto bổ sung và có tham số version-specific.

Không mặc định chuyển toàn bộ ứng dụng sang thuật toán mới trong một lần deploy nếu dữ liệu cũ hoặc các node chưa đọc được. Đánh giá threat model, khả năng vận hành (CPU/RAM), chuẩn compliance, lộ trình migration và benchmark trên workload thực tế. Chi tiết numeric của work factor cần đối chiếu hướng dẫn OWASP mới nhất tại thời điểm triển khai.

### 8.4. Credential erasure sau login

`ProviderManager` thường mặc định xóa credentials trên `Authentication` kết quả nếu đối tượng hỗ trợ `CredentialsContainer`. Điều này không làm mất password hash đã được lưu hợp lệ ở database, nhưng **có thể thay đổi một `UserDetails` mutable dùng chung với cache** nếu principal của authentication trỏ đúng instance đó.

Không tắt credential erasure một cách tùy tiện để “giữ hash trong cache”. Ưu tiên tách object per request/principal không chứa secret, rồi test login sau cache hit và concurrency.

## 9. Các lỗi triển khai điển hình

**Lỗi 1 — “Encode rồi phải decode được”.**  
`PasswordEncoder` không hỗ trợ decrypt hash; dùng `matches`. Nếu cần lấy lại plaintext để hiển thị, thiết kế lưu password đã sai.

**Lỗi 2 — Dùng `Base64.getEncoder()` như một giải pháp password hashing.**  
Base64 không dùng khóa và decode trực tiếp được. Phải dùng password KDF thích hợp.

**Lỗi 3 — Dùng `MessageDigest SHA-256` trực tiếp cho password.**  
SHA-256 quá nhanh để chống đoán offline. Dùng Argon2id/scrypt/bcrypt/PBKDF2 theo chính sách bảo mật.

**Lỗi 4 — Encode lại raw password rồi `equals` với hash cũ.**  
Adaptive hash có salt ngẫu nhiên; dùng `matches(raw, stored)`.

**Lỗi 5 — Dùng `NoOpPasswordEncoder` cho production.**  
Nó không băm bảo vệ password. Chỉ có thể xuất hiện trong tình huống migration/test có kiểm soát, không làm mặc định đăng ký/đăng nhập.

**Lỗi 6 — Cấu hình DelegatingPasswordEncoder nhưng DB lưu hash thiếu `{id}`.**  
Có thể nhận lỗi unmapped id/null. Kiểm kê legacy format, thêm prefix đúng hoặc adapter migration phù hợp; không coi mọi string thiếu ID là plaintext.

**Lỗi 7 — Đặt cost càng cao càng an toàn mà không đo.**  
Cost quá lớn có thể làm nghẽn CPU và tạo mục tiêu DoS. Benchmark với concurrency và rate limiting.

**Lỗi 8 — Không giới hạn đầu vào bcrypt theo byte.**  
Giới hạn 72 byte của nhiều implementation có thể gây cắt password. Kiểm tra input theo byte/policy và test Unicode.

**Lỗi 9 — Tự tạo salt một lần rồi dùng cho mọi account.**  
Mất lợi thế unique salt. Dùng implementation đã kiểm chứng tạo salt riêng trong `encode`.

**Lỗi 10 — Tự động đổi hash cũ bằng `encode(storedHash)`.**  
Đó không phải migration password đúng; phải xác minh raw password rồi tạo hash mới.

**Lỗi 11 — Hardcode pepper hoặc AES key trong repository.**  
Dù khóa bí mật mạnh, một leak code/config cũng có thể phá bảo vệ. Dùng secret manager/HSM, quyền truy cập, rotation policy.

**Lỗi 12 — In hash và raw password vào logs/tests.**  
Hash cũng là credential material nhạy cảm. Chỉ ghi sự kiện an toàn và định danh đủ để điều tra.

**Lỗi 13 — Dùng AES ECB/CBC không xác thực để lưu secret có thể giải mã.**  
Nếu thật sự phải mã hóa secret, chọn authenticated encryption như AES-GCM với nonce/key management đúng, không tự tạo crypto protocol tùy tiện.

**Lỗi 14 — Giả định password hash bảo vệ luôn session.**  
Sau login còn phải quản lý cookie, CSRF, session fixation, JWT/access token và revocation. PasswordEncoder không đảm nhiệm những việc đó.

## 10. Kịch bản kiểm thử

| Trường hợp | Điều cần chứng minh |
|---|---|
| `encode(raw)` rồi `matches(raw, hash)` | `true` với password đúng |
| `matches(wrong, hash)` | `false` |
| Hai lần bcrypt.encode cho cùng raw | Cả hai hash xác minh được; salt được tạo riêng theo thuật toán |
| Hash bcrypt bị đổi một số ký tự | Không được xác thực thành công; lỗi format phải được xử lý an toàn |
| DelegatingPasswordEncoder tạo hash mới | Có prefix `{id}` đúng chính sách |
| DelegatingPasswordEncoder đọc hash legacy đã gắn ID đúng | Chọn đúng encoder tương ứng |
| Hash không ID hoặc ID lạ | Không tự fallback sang plaintext; lỗi được ghi nhận có kiểm soát |
| Cost cũ thấp hơn policy mới | `upgradeEncoding` theo encoder thích hợp báo cần nâng cấp |
| Sau rehash bằng raw đã xác minh | Cả login tiếp theo với password cũ đều khớp hash mới |
| Concurrent password reset và rehash | Không cho rehash cũ ghi đè password vừa được reset |
| Password có Unicode/dài | Đúng giới hạn byte/normalization và encoder policy |
| Đăng ký cùng password cho nhiều account | Không dùng global salt, hash được lưu an toàn |
| Database dump mô phỏng | Không có plaintext password, encryption keys hay pepper trong DB |
| AES-GCM encrypt/decrypt | Giải mã thành công chỉ khi có key/nonce/ciphertext hợp lệ |
| AES-GCM bị sửa ciphertext/tag | Decryption thất bại nhờ xác thực dữ liệu |
| Rate limiting login | Không thể gửi vô hạn thử đoán khiến CPU kiệt |
| Spring DaoAuthenticationProvider | Dùng đúng PasswordEncoder với UserDetails.password hash |
| Sau login, Authentication credentials | Không còn raw password kéo dài trong context khi dùng token hỗ trợ erasure |
| Reset password | Chỉ cập nhật encoded hash mới sau xác minh reset token |
| Đổi thuật toán trong rolling deploy | Node cũ/mới đọc đúng format cần hỗ trợ, không gây gián đoạn |

### 10.1. Tự kiểm tra nhanh

**Câu 1.** Nếu bạn chỉ có một bcrypt hash trong database, có thể giải mã để gửi lại mật khẩu không?  
**Trả lời:** Không. Có thể xác minh một password ứng viên bằng `matches`; nếu người dùng quên, cần reset.

**Câu 2.** Vì sao hai user dùng mật khẩu giống nhau thường có bcrypt hash khác?  
**Trả lời:** Salt ngẫu nhiên riêng từng lần encode; cùng password nhưng salt khác tạo encoded hash khác.

**Câu 3.** Tại sao `encode(password).equals(storedHash)` có thể false khi password đúng?  
**Trả lời:** Lần encode mới dùng salt mới. Dùng `matches(raw, storedHash)`.

**Câu 4.** Khi nào nên dùng AES-GCM thay vì PasswordEncoder?  
**Trả lời:** Khi có secret thực sự cần giải mã khôi phục để sử dụng lại và có cơ chế bảo vệ khóa/nonce đúng; không phải để lưu password đăng nhập.

**Câu 5.** `{bcrypt}` trong `DelegatingPasswordEncoder` có phải password hoặc salt không?  
**Trả lời:** Không. Nó là identifier chọn encoder để kiểm tra phần encoded hash phía sau.

**Câu 6.** Có nên lưu pepper chung trong cùng bảng `accounts` không?  
**Trả lời:** Không. Pepper là secret cần tách khỏi database và có key management/rotation.

**Câu 7.** Có thể rehash toàn bộ người dùng chỉ từ hash cũ sang Argon2id mà không hỏi password không?  
**Trả lời:** Không theo luồng thông thường. Cần raw password đã được xác thực trong lần login mới hoặc yêu cầu reset.

**Câu 8.** Băm tốt có làm hệ thống an toàn nếu login API không rate limit?  
**Trả lời:** Không. Hashing chủ yếu bảo vệ khi DB leak và tăng chi phí đoán offline; online guessing/credential stuffing vẫn cần phòng vệ.

## 11. Checklist trước khi triển khai

- [ ] Chỉ lưu encoded password bằng password KDF được duyệt, không lưu plaintext/Base64/reversible encryption.
- [ ] Chọn Argon2id/scrypt/bcrypt/PBKDF2 theo policy, compliance và benchmark CPU/RAM.
- [ ] Dùng per-password random salt từ thư viện chuẩn; không dùng salt chung và không tự triển khai KDF từ hash nhanh.
- [ ] Phân biệt `encode` khi đăng ký và `matches` khi đăng nhập; không so bằng cách encode lại.
- [ ] Lưu nguyên encoded format và algorithm ID (khi dùng delegating), đảm bảo cột đủ dài.
- [ ] Giới hạn đầu vào, bảo vệ Unicode/byte limit và password policy không làm mất entropy ngoài ý muốn.
- [ ] Có kế hoạch nâng cấp hash: `upgradeEncoding`, verified raw, optimistic locking và rolling migration.
- [ ] Không thiết kế API “lấy lại mật khẩu cũ”; dùng reset token an toàn, dùng một lần và có hạn.
- [ ] Không đưa secret vào response, log, metrics, source code hoặc config công khai.
- [ ] Sử dụng TLS, rate limiting, anti-automation phù hợp và MFA khi cần.
- [ ] Nếu phải mã hóa secret có thể khôi phục, dùng authenticated encryption/key management riêng; không nhầm với password hashing.
- [ ] Có unit/integration tests với encoder/provider thực, hash format, legacy data và concurrent password change.
- [ ] Không nhầm password hash với JWT/session/authorization; kiểm soát từng vòng đời riêng.

**Ghi nhớ:** `PasswordEncoder` được dùng để **kiểm tra một mật khẩu nhập mới có đúng với hash đã lưu hay không**, chứ **không phải giải mã hash**. Với mật khẩu đăng nhập, **one-way adaptive hashing + salt + cost phù hợp** là nền tảng; với secret cần lấy lại, **authenticated encryption và quản lý khóa** là một bài toán khác.

### Tài liệu tham khảo

- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): one-way password transformation, `DelegatingPasswordEncoder`, format `{id}encodedPassword`.
- [Spring Security — PasswordEncoder JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html): `encode`, `matches`, `upgradeEncoding`.
- [Spring Security — BCryptPasswordEncoder JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html): salt, strength và upgrade.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): xác thực username/password bằng `UserDetailsService` và `PasswordEncoder`.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): thuật toán, salt, work factor, giới hạn bcrypt, pepper và nâng cấp password hash.
- [Java SE 17 — Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): authenticated encryption và `AES/GCM/NoPadding`.
