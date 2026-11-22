# Pbkdf2PasswordEncoder và tham số thuật toán

## 1. PBKDF2 giải quyết bài toán nào?

Khi một người đăng ký tài khoản hoặc thay mật khẩu, hệ thống không nên lưu chuỗi mật khẩu gốc vào database. Nếu lộ bảng người dùng, mật khẩu dạng rõ cho phép kẻ tấn công dùng lại ngay. Chỉ tính một hàm băm nhanh như `SHA-256(password)` cũng chưa đủ: kẻ tấn công có thể thử một lượng rất lớn mật khẩu đoán được trong thời gian ngắn.

**PBKDF2** (*Password-Based Key Derivation Function 2*) là hàm dẫn xuất khóa từ mật khẩu dựa trên một hàm giả ngẫu nhiên, thường là **HMAC**. Nó chủ động thực hiện nhiều vòng xử lý để **mỗi lần đoán một mật khẩu trở nên tốn CPU hơn**. Spring Security cung cấp `org.springframework.security.crypto.password.Pbkdf2PasswordEncoder`, một triển khai `PasswordEncoder` dùng PBKDF2 để tạo và kiểm chứng dữ liệu lưu trữ mật khẩu.

Đầu vào về mặt ý tưởng:

```text
rawPassword ────────────────────────────┐
                                         │
random salt riêng cho từng lần encode ───┼── PBKDF2-HMAC
                                         │     (iterations, derived-key length)
secret bổ sung nếu cấu hình ──────────────┘
                                                 │
                                                 v
                                     salt + derived key
                                                 │
                                        Hex hoặc Base64
                                                 │
                                                 v
                                   encodedPassword trong DB
```

**`encode(rawPassword)`** sinh salt mới, dẫn xuất giá trị băm và trả chuỗi lưu trữ. **`matches(rawPassword, storedEncodedPassword)`** lấy thông tin salt từ chuỗi đã lưu, tính lại theo *cùng một cấu hình* và xác nhận kết quả. Không có thao tác “giải mã PBKDF2” để thu lại mật khẩu.

Bài này tập trung vào **`Pbkdf2PasswordEncoder` và các tham số thuật toán**: cách chọn HMAC, độ dài salt, iterations, độ dài đầu ra, secret tùy chọn, Hex/Base64, các preset theo phiên bản, vận hành cùng `DelegatingPasswordEncoder` và quy trình nâng cấp hash mà không làm hỏng đăng nhập.

## 2. Phân biệt password hashing với mã hóa hai chiều và băm nhanh

| Kỹ thuật | Ví dụ | Có phù hợp để lưu mật khẩu đăng nhập? | Vì sao? |
| --- | --- | --- | --- |
| Lưu thẳng | `password="Secret123!"` | **Không** | Lộ bảng dữ liệu là lộ password. |
| Mã hóa hai chiều | AES với khóa để giải mã | **Không phải lựa chọn mặc định** | Nếu khóa bị lộ, có thể giải mã hàng loạt mật khẩu. |
| Băm nhanh đơn thuần | `SHA-256(password)`, MD5 | **Không** | Không có chi phí thích nghi đủ cao và có nguy cơ dùng bảng đoán sẵn. |
| PBKDF2 có salt, iterations phù hợp | PBKDF2-HMAC-SHA256 | **Có**, khi chọn tham số, provider và vận hành phù hợp | Làm tăng chi phí mỗi lần đoán password. |
| Hàm memory-hard | Argon2id, scrypt | **Thường được ưu tiên cho hệ thống mới khi thích hợp** | Ngoài CPU còn có chi phí bộ nhớ, tăng khó khăn cho một số kiểu tấn công song song. |

PBKDF2 là lựa chọn quan trọng khi phải đáp ứng **hệ sinh thái thuật toán/hạ tầng FIPS**. Nhưng chỉ gọi API Java PBKDF2 **không tự làm toàn bộ ứng dụng hoặc JCA provider đạt chứng nhận FIPS**: chứng nhận còn phụ thuộc thư viện, module mật mã, chế độ triển khai và môi trường vận hành.

Một lưu ý: việc dùng HMAC-SHA256 *bên trong* PBKDF2 **khác hoàn toàn** việc lưu thẳng SHA-256 của mật khẩu. PBKDF2-HMAC-SHA256 lặp phép xử lý với salt; băm nhanh đơn thuần không cung cấp cấu trúc chi phí tương đương.

## 3. Cấu trúc thuật toán và từng tham số

Về nguyên lý:

```text
PBKDF2(
    password = mật khẩu người dùng,
    salt = bytes ngẫu nhiên,
    iterations = số vòng lặp,
    derivedKeyLength = độ dài khóa dẫn xuất,
    PRF = HMAC-SHA256 / HMAC-SHA512 / ...
)  --> derived key
```

Với Spring Security `Pbkdf2PasswordEncoder` còn có **secret** bổ sung, và một lựa chọn **mã hóa chuỗi kết quả** thành Hex hoặc Base64. Các tham số quan trọng:

| Tham số | Ý nghĩa | Đơn vị/chú ý | Tác động |
| --- | --- | --- | --- |
| `secret` | Bí mật phía server được phối hợp vào đầu vào PBKDF2. | `CharSequence`; mặc định rỗng. | Nếu khác secret, hash cũ không còn verify được bằng cấu hình mới. |
| `saltLength` | Độ dài salt ngẫu nhiên sinh mỗi lần `encode`. | **Byte**, không phải bit. | Salt độc lập giúp hai bản ghi cùng password thường có hash khác nhau. |
| `iterations` | Số vòng PBKDF2. | Số nguyên dương; chi phí CPU tăng theo work factor. | Tăng iterations làm việc đoán mật khẩu khó hơn nhưng login cũng chậm hơn. |
| `SecretKeyFactoryAlgorithm` | Hàm PBKDF2-HMAC được sử dụng. | Ví dụ `PBKDF2WithHmacSHA256`. | Phải khớp khi tạo và kiểm chứng hash. |
| `hashWidth` / derived key length | Số bit đầu ra của PBKDF2. | **Bit**, khác `saltLength`. | 256 bit = 32 byte; không phải số vòng lặp. |
| `encodeHashAsBase64` | Định dạng biểu diễn chuỗi kết quả. | Mặc định `false`, tức **Hex**. | Đổi sang Base64 làm thay đổi chuỗi lưu và cách parse. |

### 3.1. Salt là ngẫu nhiên và công khai được

Salt phải độc lập cho từng lần hash và được tạo từ nguồn ngẫu nhiên an toàn. Salt **không phải mật khẩu thứ hai**, không cần giữ bí mật, và được lưu cùng kết quả băm để sau này verify.

Ví dụ hai user cùng đặt `Secret123!`:

```text
user A: saltA || PBKDF2("Secret123!", saltA, ...)
user B: saltB || PBKDF2("Secret123!", saltB, ...)
```

Thông thường `saltA != saltB` nên giá trị lưu khác nhau. Đây là cách giảm lợi ích của rainbow table và ngăn suy ra trực tiếp hai người dùng có cùng password từ các hash trùng nhau. Nó **không cứu** password yếu trước mọi tấn công: đối thủ có hash và salt vẫn có thể thử đoán offline, mỗi lần thử phải trả chi phí PBKDF2.

Trong preset `v5_8`, `saltLength=16` **byte** (128 bit), không phải 16 ký tự Hex. Khi nhìn output Hex, 16 byte salt chiếm **32 ký tự Hex**.

### 3.2. Iterations là chi phí, không phải độ dài password

`iterations=310_000` nghĩa là thực hiện 310.000 vòng theo thuật toán, **không** có nghĩa băm thành 310.000 ký tự hoặc sẽ cố định mất một số mili-giây trên mọi máy.

Tăng từ 310.000 lên 600.000 vòng thường làm chi phí verify lớn hơn theo tỷ lệ gần với số vòng, nhưng thời gian thực tế phụ thuộc JDK/JCA provider, CPU, tải đồng thời và môi trường triển khai.

Đừng đặt work factor chỉ bằng cảm giác “số càng lớn càng an toàn”: login bị attacker gửi hàng loạt có thể tiêu tốn CPU và gây từ chối dịch vụ. Cần benchmark **trên máy production hoặc môi trường tương đương**, có giới hạn concurrency, rate limiting và kế hoạch vận hành. Bài test hiệu năng cần đo percentiles và xác thực song song, không chỉ một lời gọi đơn lẻ trên laptop.

### 3.3. HMAC algorithm và output length khác nhau

Tên `PBKDF2WithHmacSHA256` nói rằng **PRF là HMAC-SHA256**. Nó không có nghĩa độ dài salt là 256 bit hoặc số vòng mặc định được chọn từ tên đó. `SecretKeyFactoryAlgorithm` trong `Pbkdf2PasswordEncoder` cung cấp các lựa chọn như:

- `PBKDF2WithHmacSHA1`: chủ yếu gặp ở dữ liệu cũ, không khuyến khích chọn cho hệ thống mới.
- `PBKDF2WithHmacSHA256`: lựa chọn thực tế cho PBKDF2 hiện đại.
- `PBKDF2WithHmacSHA512`: lựa chọn khác với profile iterations riêng.

Độ dài đầu ra ví dụ **256 bit = 32 byte**. Dù thay HMAC algorithm, việc cố đổi độ dài đầu ra hoặc chọn profile mới phải được quản lý như thay đổi phiên bản hash vì có thể làm `matches` không tương thích bản ghi cũ.

**Đừng lẫn thuật ngữ:** PBKDF2 là một *key derivation function*; Spring Security dùng nó theo hợp đồng `PasswordEncoder` để giữ **password verifier**, không phải dùng hash password trực tiếp làm key AES cho tất cả mục đích nghiệp vụ.

### 3.4. Secret bổ sung: khác với salt

Constructor có tham số `secret`. Spring Security có thể phối hợp secret thêm vào salt ngẫu nhiên như một bí mật phía server. Khi dùng secret khác rỗng:

- Secret phải được lấy từ secret manager hoặc cơ chế cấu hình an toàn; **không hard-code** vào repository.
- Không lưu secret cùng bản ghi hash trong DB hay trả về qua API.
- Nếu đổi hoặc làm mất secret, hash cũ có thể không xác thực được; cần quản lý phiên bản secret và migration/reset credential.
- Secret không thay thế password, salt, work factor, khóa bảo vệ hạ tầng hoặc MFA.
- Không mặc định mọi cách “thêm pepper” đều là mô hình tương thích; nếu tổ chức có policy pepper/HSM riêng, thiết kế phải tuân theo policy và kiểm thử.

Các preset của Spring Security `defaultsForSpringSecurity_v5_8()` sử dụng **secret rỗng**. Điều đó không phải cấu hình mặc định bị lỗi; một pepper bên ngoài là biện pháp tăng cường tùy mô hình rủi ro.

## 4. Thông số preset cụ thể trong Spring Security 6.5.11

`Pbkdf2PasswordEncoder` có các hàm dựng tiện lợi được đặt tên theo phiên bản. Tên có hậu tố version **không có nghĩa** chỉ dùng được trong phiên bản framework đó; nó giúp giữ ổn định cấu hình hash khi framework phát triển.

| API preset | Salt | Iterations | PRF | Derived key | Ghi chú |
| --- | ---: | ---: | --- | ---: | --- |
| `defaultsForSpringSecurity_v5_5()` | 8 byte | 185.000 | HMAC-SHA1 | 256 bit | Profile cũ, deprecated trong 6.5; cần để verify dữ liệu legacy. |
| **`defaultsForSpringSecurity_v5_8()`** | **16 byte** | **310.000** | **HMAC-SHA256** | **256 bit** | Preset được khuyên dùng thay cho preset cũ ở API 6.5. |
| Profile do ứng dụng tự thiết kế | Ví dụ 16 byte | Ví dụ 600.000 | Ví dụ HMAC-SHA256 | Ví dụ 256 bit | Cần đặt version ID riêng, benchmark và quản lý migration. |

Thông số này đối chiếu theo **Spring Security 6.5.11**, không nên suy rộng sang mọi thời đại. Tham chiếu: [Pbkdf2PasswordEncoder API 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/Pbkdf2PasswordEncoder.html).

**Đừng nhầm default của framework với mức work factor production khuyến nghị tại mọi thời điểm.** Tài liệu OWASP Password Storage Cheat Sheet hiện đưa ra **PBKDF2-HMAC-SHA256 từ 600.000 vòng** trong bối cảnh cần PBKDF2/FIPS, cao hơn preset `v5_8` 310.000 vòng. Đây là lý do cần có **policy và version riêng** cho hệ thống thay vì mặc định mọi ứng dụng production chỉ gọi preset rồi không đánh giá thêm.

Mức 600.000 **không phải con số bảo đảm thời gian chính xác**. Cần hiệu chỉnh theo threat model, mục tiêu latency, số lượng login đồng thời và môi trường phần cứng. Khi chọn iterations lớn hơn, phải giữ cấu hình cũ để verify bản ghi hash đã tạo trước đó.

## 5. Constructor, thuật toán và sự khác nhau giữa Hex/Base64

Cách nhanh để tạo encoder theo preset:

```java
Pbkdf2PasswordEncoder encoder =
        Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();
```

Cách đặt một profile rõ ràng bằng constructor của Spring Security 6.5:

```java
Pbkdf2PasswordEncoder tuned = new Pbkdf2PasswordEncoder(
        "", // server-side secret rỗng trong ví dụ
        16, // saltLength tính bằng byte
        600_000,
        Pbkdf2PasswordEncoder.SecretKeyFactoryAlgorithm.PBKDF2WithHmacSHA256
);
```

Constructor sử dụng `SecretKeyFactoryAlgorithm` được khuyến khích thay cho constructor cũ nhận `hashWidth` (đã deprecated). **Không chọn constructor deprecated chỉ vì muốn gán độ dài đầu ra tùy ý** nếu chưa nắm rõ tương thích dữ liệu.

Cách đổi biểu diễn sang Base64:

```java
Pbkdf2PasswordEncoder base64Encoder =
        Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();
base64Encoder.setEncodeHashAsBase64(true);
```

Mặc định là **Hex**. Với preset v5_8:

- Salt 16 byte + derived key 32 byte = **48 byte** dữ liệu nhị phân.
- Hex biểu diễn 48 byte thành **96 ký tự**.
- Base64 biểu diễn 48 byte thành **64 ký tự** (48 chia hết cho 3).
- Giá trị **thay đổi theo salt ngẫu nhiên**; không có một chuỗi hash literal cố định cho cùng password.

Độ dài 96/64 tính cho output của `Pbkdf2PasswordEncoder` **chưa có tiền tố `{id}`**. Khi đặt vào `DelegatingPasswordEncoder`, độ dài chuỗi DB tăng thêm độ dài version prefix. Nếu dùng secret bổ sung, secret không được ghi thành plaintext prefix vào chuỗi output.

### Định dạng lưu của Pbkdf2PasswordEncoder không tự chứa đầy đủ tham số

`Pbkdf2PasswordEncoder` không dùng format tự mô tả iteration count và PRF trong mỗi chuỗi như một số password hash format khác. Nó lưu phần salt và dẫn xuất đã biểu diễn dưới cấu hình hiện tại. Hậu quả:

- Thay `iterations` mà vẫn dùng cùng một encoder cho bản ghi cũ làm `matches` thất bại.
- Thay PRF, độ dài salt, secret hoặc chế độ Hex/Base64 mà không giữ decoder tương thích có thể làm password đúng **không đăng nhập được**.
- Không thể dựa vào việc hash dài 96 ký tự để suy ra **chính xác** số vòng lặp; nhiều profile dùng cùng salt/key length có độ dài giống nhau.
- Nên lưu **ID/profile version** cùng password hash, thường qua tiền tố `{id}` của `DelegatingPasswordEncoder`.

**Ví dụ sai:**

```java
// Khi tạo tài khoản:
Pbkdf2PasswordEncoder oldEncoder =
        Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();
String stored = oldEncoder.encode("correct-password");

// Sau một thời gian, cấu hình thay iterations nhưng không version:
Pbkdf2PasswordEncoder newEncoder = new Pbkdf2PasswordEncoder(
        "", 16, 600_000,
        Pbkdf2PasswordEncoder.SecretKeyFactoryAlgorithm.PBKDF2WithHmacSHA256
);

// Không được giả định newEncoder.matches(..., stored) trả true.
// Hash cũ cần encoder profile v5_8 cũ để kiểm chứng.
```

Đoạn trên là minh họa cấu hình không tương thích, **không phải chương trình Java độc lập**. Cách đúng là versioning, không “nâng số vòng” trên tất cả bản ghi chỉ bằng một dòng config.

## 6. `encode` và `matches`: đừng so chuỗi hash vừa tạo

`PasswordEncoder` có hai thao tác:

```java
String savedHash = encoder.encode(rawPassword);
boolean accepted = encoder.matches(rawPassword, savedHash);
```

Trong PBKDF2 có salt ngẫu nhiên, hai lần `encode` của cùng một raw password sẽ **hầu như luôn** cho hai chuỗi khác nhau. Vì vậy mẫu này sai:

```java
boolean wrong = encoder.encode(submittedPassword).equals(storedHash);
```

Phải dùng:

```java
boolean correct = encoder.matches(submittedPassword, storedHash);
```

Không tự tách salt hoặc tự xây PBKDF2 verifier ngoài `PasswordEncoder` nếu không có yêu cầu tương thích giao thức cụ thể; code tự viết dễ sai char encoding, algorithm, output length, salt boundary và so sánh theo thời gian.

**Salt không làm mật khẩu yếu thành mạnh.** Nếu user đặt `123456`, kẻ tấn công vẫn có thể đoán, chỉ mất thêm chi phí theo work factor. Chính sách lưu hash phải đi cùng kiểm tra password đã lộ, MFA phù hợp, rate limiting và cơ chế khóa/giám sát hợp lý.

## 7. Ví dụ Java 17 chạy được: preset, tham số tùy chỉnh và versioning

Ví dụ này dùng **Spring Security 6.5.11, Gradle và Java 17+**. Nó cho thấy:

- `v5_8` tạo hash và verify.
- Salt và derived key có độ dài cụ thể theo preset.
- `setEncodeHashAsBase64(true)` thay đổi biểu diễn nhưng không có nghĩa băm mạnh hơn.
- Profile 600.000 vòng hoạt động và kiểm chứng đúng.
- `DelegatingPasswordEncoder` nhận diện hash cũ theo `{id}`, và ghi hash mới với ID mới.

Đây là demo **console**, không cần Spring Boot hoặc kết nối DB. Không đưa mật khẩu mẫu vào code production.

### 7.1. Cấu trúc thư mục

```text
pbkdf2-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/Pbkdf2Demo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'pbkdf2-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.Pbkdf2Demo'
}
```

### 7.2. `Pbkdf2Demo.java`

```java
package demo;

import java.util.Map;

import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder.SecretKeyFactoryAlgorithm;

public final class Pbkdf2Demo {

    public static void main(String[] args) {
        String password = "Tr0ngPa$!";

        Pbkdf2PasswordEncoder legacy =
                Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_5();
        Pbkdf2PasswordEncoder preset =
                Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();

        String presetHash = preset.encode(password);
        System.out.println("v58.hashHexChars=" + presetHash.length());
        System.out.println("v58.hexOnly="
                + presetHash.matches("[0-9a-fA-F]{96}"));
        System.out.println("v58.passwordRight="
                + preset.matches(password, presetHash));
        System.out.println("v58.passwordWrong="
                + preset.matches("wrong-password", presetHash));

        // Dùng một instance khác có cùng profile vẫn verify được hash.
        Pbkdf2PasswordEncoder sameProfile =
                Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();
        System.out.println("v58.verifyAcrossInstances="
                + sameProfile.matches(password, presetHash));

        Pbkdf2PasswordEncoder base64 =
                Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();
        base64.setEncodeHashAsBase64(true);
        String base64Hash = base64.encode(password);
        System.out.println("v58.base64Chars=" + base64Hash.length());
        System.out.println("v58.base64Matches="
                + base64.matches(password, base64Hash));

        // Profile mới của ứng dụng: ID riêng, không ghi đè ý nghĩa ID cũ.
        Pbkdf2PasswordEncoder policy2026 = new Pbkdf2PasswordEncoder(
                "",
                16,
                600_000,
                SecretKeyFactoryAlgorithm.PBKDF2WithHmacSHA256
        );

        String tunedHash = policy2026.encode(password);
        System.out.println("policy2026.passwordRight="
                + policy2026.matches(password, tunedHash));
        System.out.println("policy2026.passwordWrong="
                + policy2026.matches("wrong-password", tunedHash));

        Map<String, PasswordEncoder> profiles = Map.of(
                "pbkdf2", legacy,
                "pbkdf2@SpringSecurity_v5_8", preset,
                "pbkdf2@policy2026", policy2026
        );

        DelegatingPasswordEncoder delegating =
                new DelegatingPasswordEncoder(
                        "pbkdf2@policy2026", profiles);

        String existingLegacy = "{pbkdf2}" + legacy.encode(password);
        String existingV58 =
                "{pbkdf2@SpringSecurity_v5_8}" + presetHash;

        System.out.println("legacy.matches="
                + delegating.matches(password, existingLegacy));
        System.out.println("v58.delegatedMatches="
                + delegating.matches(password, existingV58));
        System.out.println("v58.needsUpgrade="
                + delegating.upgradeEncoding(existingV58));

        String newStored = delegating.encode(password);
        System.out.println("new.hasPolicyId="
                + newStored.startsWith("{pbkdf2@policy2026}"));
        System.out.println("new.matches="
                + delegating.matches(password, newStored));
    }
}
```

### 7.3. Lệnh chạy và stdout

Từ thư mục `pbkdf2-demo`, cài JDK 17+ và Gradle tương thích Java 17 (hoặc Gradle Wrapper tương đương):

```bash
gradle run --quiet
```

Các dòng stdout của `System.out.println` **theo cấu hình và mã chương trình đã cho**, không tính thông báo build/log của môi trường:

```text
v58.hashHexChars=96
v58.hexOnly=true
v58.passwordRight=true
v58.passwordWrong=false
v58.verifyAcrossInstances=true
v58.base64Chars=64
v58.base64Matches=true
policy2026.passwordRight=true
policy2026.passwordWrong=false
legacy.matches=true
v58.delegatedMatches=true
v58.needsUpgrade=true
new.hasPolicyId=true
new.matches=true
```

Mật khẩu/hash cụ thể được tạo với salt ngẫu nhiên nên **không cố in chuỗi hash literal**. Kết quả boolean và độ dài có thể kiểm tra ổn định trên profile được nêu, trong khi giá trị hash thay đổi theo mỗi lần encode. Bản ví dụ giả định JDK/JCA provider hỗ trợ `PBKDF2WithHmacSHA256` — điều phổ biến với JDK 17 hiện đại.

### 7.4. Phân tích từng nhóm kết quả

- **`v58.hashHexChars=96`:** 16 byte salt + 32 byte dẫn xuất = 48 byte, mỗi byte có hai ký tự Hex.
- **`v58.passwordRight=true` và `passwordWrong=false`:** password được so qua `matches` chứ không so chuỗi hai lần encode.
- **`verifyAcrossInstances=true`:** secret, PRF, iterations, saltLength, output encoding tương thích thì một instance mới vẫn đọc được hash cũ. Không phụ thuộc địa chỉ đối tượng Java.
- **`base64Chars=64`:** cùng profile nhưng output dùng Base64; output dài khác Hex. Cần cùng cấu hình biểu diễn khi verify.
- **`policy2026.passwordRight=true`:** chọn 600.000 vòng bằng constructor hiện hành; trong demo không cố assert thời gian CPU vì phụ thuộc phần cứng.
- **`legacy.matches=true`:** registry còn hỗ trợ profile cũ dưới id `pbkdf2`. Đừng xóa decoder legacy trước khi đã chuyển hết bản ghi.
- **`v58.needsUpgrade=true`:** `DelegatingPasswordEncoder` biết bản ghi cũ có ID khác ID dùng để ghi mới. Đây là tín hiệu **có thể** nâng cấp khi ứng dụng có luồng cập nhật mật khẩu phù hợp; không phải tự động rewrite DB tại dòng demo.
- **`new.hasPolicyId=true`:** hash mới có ID riêng, bảo đảm sau này vẫn tra về bộ tham số 600.000 vòng thay vì tự hiểu thành `pbkdf2@SpringSecurity_v5_8`.

**Cần phân biệt:** các ID trong `profiles` là *nhãn được ứng dụng quyết định*. `pbkdf2@policy2026` không phải factory preset có sẵn của Spring Security; nó chỉ hoạt động vì `Map` đã đăng ký key đó. Dùng ID có ý nghĩa và không thay đổi nội dung profile mà ID cũ từng đại diện.

## 8. Định dạng `DelegatingPasswordEncoder` và những nhầm lẫn phiên bản

Spring Security có `DelegatingPasswordEncoder` cho phép lưu:

```text
{id}encodedPassword
```

Ví dụ:

```text
{pbkdf2}...
{pbkdf2@SpringSecurity_v5_8}...
{pbkdf2@policy2026}...
{bcrypt}$2a$...
```

**Tiền tố không phải thuật toán tự vận hành.** Nó chọn đúng object `PasswordEncoder` có ID tương ứng trong registry. Lúc verify, `DelegatingPasswordEncoder` bóc `{id}`, tìm encoder trong `Map` và đưa phần phía sau cho encoder ấy. Nếu thiếu mapping/id, verify có thể thất bại hoặc ném lỗi; **không** được tự suy luận PBKDF2 profile nào để “cứ thử tất cả” mà không có chính sách an toàn.

### 8.1. Factory mặc định không đồng nghĩa mặc định dùng PBKDF2

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo một registry có nhiều encoder. Trong nhánh Spring Security 6.5, ID dùng để **encode password mới mặc định** là `bcrypt`; registry đồng thời có thể hỗ trợ `pbkdf2` (profile cũ) và `pbkdf2@SpringSecurity_v5_8` (profile v5_8) để match dữ liệu tương ứng.

```java
PasswordEncoder factory =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

// Với factory mặc định theo Spring Security 6.5,
// password mới thông thường có tiền tố {bcrypt}, không phải {pbkdf2}.
String stored = factory.encode("DemoPass123!");
```

Nếu sản phẩm quyết định PBKDF2 là profile ghi mới, **cần cấu hình chủ động `DelegatingPasswordEncoder`** như mục 7 hoặc một registry tương ứng của tổ chức. Không nhầm “PBKDF2 có trong danh sách đọc” với “PBKDF2 được chọn để ghi”.

### 8.2. Không gán cấu hình mới vào tên ID đã dùng

Giả sử DB chứa:

```text
{pbkdf2@SpringSecurity_v5_8}HEX_WITH_16_BYTE_SALT_AND_310000_ITERATIONS
```

Nếu ngày mai mã nguồn đổi mapping `pbkdf2@SpringSecurity_v5_8` sang encoder **600.000 vòng** mà vẫn giữ ID cũ, người dùng có password hợp lệ cũng sẽ không verify được. Giữ ID cũ gắn với tham số cũ, và tạo `pbkdf2@policy2026` hoặc ID profile versioned tương tự để ghi bản mới.

**Lưu ý migration:** prefix `{id}` chỉ phân biệt profile khi một ID gắn với **một cấu hình bất biến**. Nếu tổ chức dùng cùng ID cho nhiều PRF/work factor/secret mà không lưu metadata, bản ghi cũ có thể không phân loại được. Khi đó phải phân tích dữ liệu và chuẩn bị quy trình kiểm chứng/đổi mật khẩu; không sửa hash bằng cách thay prefix tùy tiện.

## 9. Nâng work factor an toàn cho dữ liệu đã có

Một hệ thống vận hành lâu năm có thể có nhiều profile hash:

| Nhóm bản ghi | ID | Điều cần làm |
| --- | --- | --- |
| Legacy PBKDF2 | `pbkdf2` | Chỉ giữ khả năng **verify** trong giai đoạn chuyển đổi; không dùng để hash mới. |
| PBKDF2 v5_8 | `pbkdf2@SpringSecurity_v5_8` | Verify bằng tham số cũ; đánh dấu cần nâng cấp theo policy. |
| PBKDF2 policy mới | `pbkdf2@policy2026` | Ghi hash mới bằng tham số hiện hành, không đổi ID tùy tiện. |
| BCrypt đang tồn tại | `bcrypt` | Nếu có lịch sử dữ liệu loại này, giữ decoder cho đến khi migration rõ ràng. |

**Lộ trình migration:**

1. **Kiểm kê** định dạng hash hiện có: có `{id}` hay không, mỗi ID thuộc tham số nào, định dạng Hex/Base64, có server-side secret không, có hash cũ không xác định profile không.
2. **Đóng băng ý nghĩa ID cũ**: registry verify phải giữ object tương ứng với profile cũ, không chỉnh tại chỗ.
3. **Tạo ID mới** cho cấu hình chọn sau benchmark, ví dụ PBKDF2-HMAC-SHA256/600.000/salt16/Hex.
4. **Chuyển đường ghi mới** (đăng ký, đổi password, reset) sang encoder mới, vẫn verify bản ghi cũ.
5. **Rehash sau xác thực thành công**: lúc này mới có raw password đúng ở luồng xác thực; encode lại với profile mới rồi cập nhật DB an toàn trong transaction.
6. **Xử lý cạnh tranh**: tránh update hash mới ghi đè một lần đổi password khác, dùng version/optimistic locking hoặc compare-and-set theo thiết kế.
7. **Theo dõi tiến độ**: thống kê theo ID hash, độ trễ login, error rate và số bản ghi legacy còn lại, không ghi raw password.
8. **Lộ trình tài khoản không đăng nhập**: có chính sách reset/đặt lại password an toàn, không thể tùy ý tái băm hash cũ thành hash mới mà không biết raw password.
9. **Chỉ xóa decoder legacy** khi bảo đảm không còn dữ liệu cần verify, có backup/rollback và đã kiểm tra đủ.
10. **Quản lý thay secret** riêng: nếu có pepper/secret phía server, đổi secret cần versioning rõ ràng và khả năng giữ hoặc thay thế khóa cũ theo policy.

### 9.1. `upgradeEncoding` và `UserDetailsPasswordService`

`PasswordEncoder.upgradeEncoding(encodedPassword)` cho biết liệu hash đã lưu có cần nâng cấp theo chính sách của encoder hay không. Với `DelegatingPasswordEncoder`, một bản ghi có **ID khác ID ghi mới** thường được đánh dấu cần nâng cấp.

`DaoAuthenticationProvider` có thể được cấu hình `UserDetailsPasswordService` để cập nhật password hash sau xác thực thành công, khi encoder báo cần nâng cấp.

Phác thảo wiring:

```java
// Trích đoạn Spring Security, không phải chương trình Java độc lập.
// usersService triển khai UserDetailsService;
// passwordUpdateService triển khai UserDetailsPasswordService.
DaoAuthenticationProvider provider =
        new DaoAuthenticationProvider(usersService);
provider.setPasswordEncoder(delegatingPasswordEncoder);
provider.setUserDetailsPasswordService(passwordUpdateService);
```

`UserDetailsPasswordService.updatePassword(user, newPassword)` nhận **mật khẩu đã được encode** theo encoder mới, không phải raw password. Implementation phải cập nhật record tương ứng và trả `UserDetails` phù hợp. Không bật migrate tự động nếu DB update thiếu concurrency control, không có chính sách version metadata, hoặc thay secret chưa có kế hoạch.

**Quan trọng:** đừng dựa vào `Pbkdf2PasswordEncoder` *một mình* để tự đọc iteration count từ chuỗi hash cũ. Cơ chế ID/profile và quy trình nâng cấp do ứng dụng thiết kế.

## 10. Benchmark iterations và cân bằng bảo mật/vận hành

Có hai mục tiêu đồng thời:

1. **Khó đoán mật khẩu offline** khi attacker chiếm được database hash.
2. **Không làm nghẽn login server** do chi phí verify quá cao hoặc bị flood requests.

Spring Security mô tả nên hiệu chỉnh để việc xác thực password tốn một khoảng thời gian đáng kể trên máy đích; OWASP cung cấp ngưỡng tham khảo mới cho PBKDF2-HMAC-SHA256. **Cả hai không thay thế benchmark sản phẩm**.

Một kế hoạch đo có ích:

- Chọn JDK, JCA provider, OS và cấu hình CPU tương đương production.
- Dùng password mẫu có độ dài thực tế và một số trường hợp dài; không log password thật.
- Warm up JVM và đo đủ lần verify, thay vì lấy một vòng đầu tiên.
- Đo percentiles `p50`/`p95`/`p99` cùng CPU utilization, không chỉ mean.
- Mô phỏng concurrency login trong giới hạn vận hành, ghi nhận throughput và queueing.
- Đo trên container với CPU quota thật, không dựa vào laptop không giới hạn tài nguyên.
- Kết hợp rate limit, chống credential stuffing, timeout, circuit breaker/failure strategy và kế hoạch scale khi cần.
- Nếu tăng từ 310.000 lên 600.000 làm latency vượt SLO, đánh giá kiến trúc/phần cứng và risk trade-off thay vì vô điều kiện giảm xuống một con số dễ đoán.

**Không benchmark bằng cách giữ JVM chạy PBKDF2 vô hạn trên production.** Dùng môi trường tải có kiểm soát. Và không dùng cùng một endpoint công khai cho “benchmark nhanh” để attacker có thể ép server thực hiện vô số vòng KDF.

## 11. Vai trò `Pbkdf2PasswordEncoder` trong Spring Security authentication

Trong luồng username/password:

```text
Client gửi username / raw password
          |
          v
Spring Security authentication filter
          |
          v
AuthenticationManager (ProviderManager)
          |
          v
DaoAuthenticationProvider
    |
    +--> UserDetailsService.loadUserByUsername()
    |        |
    |        +--> lấy username, passwordHash, flags, authorities
    |
    +--> account-state checks
    |
    +--> PasswordEncoder.matches(rawPassword, passwordHash)
    |
    +--> credential-expiry checks
          |
       Kết quả:
        ├── đúng và hợp lệ → authenticated Authentication
        └── sai/bị chặn → AuthenticationException
```

`Pbkdf2PasswordEncoder` chỉ thực hiện **hash/verify password**; nó không làm ba việc sau:

- Không đọc users từ JPA, JDBC hay LDAP: đó là việc của `UserDetailsService`/kho danh tính.
- Không tự cấp authority hoặc trả `SecurityContext`: provider/filter quản lý authentication flow.
- Không tự chuyển toàn bộ hash cũ trong DB sang tham số mới: cần `DelegatingPasswordEncoder`, dịch vụ update và policy migration.

Một cấu hình Spring Boot Servlet minh họa, giả sử đã có bean `UserDetailsService` từ database:

```java
@Configuration
class PasswordSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        Pbkdf2PasswordEncoder v58 =
                Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();

        Pbkdf2PasswordEncoder policy2026 = new Pbkdf2PasswordEncoder(
                "", 16, 600_000,
                Pbkdf2PasswordEncoder.SecretKeyFactoryAlgorithm
                        .PBKDF2WithHmacSHA256);

        return new DelegatingPasswordEncoder(
                "pbkdf2@policy2026",
                Map.of(
                        "pbkdf2@SpringSecurity_v5_8", v58,
                        "pbkdf2@policy2026", policy2026));
    }
}
```

Đây là **trích đoạn cấu hình**, cần các imports và bean/service còn lại của ứng dụng. Nếu DB chứa `{bcrypt}` hoặc `{pbkdf2}` legacy, **registry ví dụ này chưa có decoder cho chúng** — phải bổ sung đúng trước khi dùng production. Nếu database trước đây lưu PBKDF2 trực tiếp **không có prefix**, cần migration format có kiểm soát thay vì chỉ thay bean và hy vọng login vẫn chạy.

Trong production, bean password encoder phải là **singleton/config nhất quán** theo application version, không lấy giá trị iterations từ request client. Không log raw password, salt, toàn bộ encoded hash hoặc secret bổ sung; salt vốn không bí mật nhưng toàn bộ hash vẫn là credential verifier cần bảo vệ như dữ liệu nhạy cảm.

## 12. Kiểm thử: tham số đúng không đủ nếu không có contract lưu trữ

### 12.1. Những test cấp encoder cần có

| Test | Hành vi cần kiểm chứng |
| --- | --- |
| Encode đúng password | `matches(raw, encoded) == true`. |
| Encode và test password sai | `matches(wrong, encoded) == false`. |
| Salt khác nhau | Nhiều lần encode thường cho hash khác nhau; xác suất trùng salt rất nhỏ. |
| Kết quả Hex mặc định | Với v5_8: 96 ký tự Hex, không kèm `{id}`. |
| Kết quả Base64 | Với v5_8 + `setEncodeHashAsBase64(true)`: 64 ký tự Base64; match đúng khi cùng profile. |
| Chạy khác instance | Hash tạo bởi một instance verify được bởi instance cùng cấu hình. |
| Legacy ID | `DelegatingPasswordEncoder` nhận `{pbkdf2}` đúng profile cũ. |
| Version v5_8 ID | Registry match `{pbkdf2@SpringSecurity_v5_8}`. |
| New profile ID | Hash mới có tiền tố ID policy đang ghi và verify đúng. |
| Mismatch version | Không tự mong password đúng với iterations/PRF khác; migration giữ decoder cũ. |
| Unknown ID | Không cấp login theo cơ chế suy đoán; xử lý lỗi có kiểm soát. |
| Unicode password | Không tự ý `trim()`/`toLowerCase()`/normalization trong login adapter; bảo toàn đúng chuỗi người dùng đã thiết lập. |

Với ví dụ random salt, **đừng assert hash bằng một string literal cố định**. Kết quả encode thay đổi theo lần chạy; unit test nên assert tính chất, độ dài, ID và khả năng verify.

### 12.2. Test từ DB tới provider

Dùng `UserDetailsService` thật hoặc test adapter với store thay thế có thể kiểm soát:

1. Tạo user có password hash `{pbkdf2@SpringSecurity_v5_8}...`.
2. Cấu hình `DelegatingPasswordEncoder` có mapping cho ID đó.
3. Gọi `AuthenticationManager.authenticate(UsernamePasswordAuthenticationToken.unauthenticated(username, rawPassword))`.
4. Kiểm tra provider xác thực thành công và authorities được lấy từ nguồn tin cậy.
5. Gọi lại với password sai; kỳ vọng `BadCredentialsException`, không có authenticated token.
6. Với tài khoản disabled/locked, password đúng vẫn không tạo login thành công.
7. Nếu cấu hình `UserDetailsPasswordService`, xác nhận hash được nâng cấp đúng sau login thành công và giữ khả năng đăng nhập ở lần sau.
8. Test cạnh tranh giữa lần login nâng cấp hash và lần đổi password thật, tránh lost update.
9. Test sau restart với encoder bean dựng lại từ config: **hash cũ vẫn verify được**.
10. Test rollback/deploy nhiều instance: node cũ có đọc được prefix ID mới không? Không để một số node phát ra hash mới trong khi node khác chưa có decoder.

**`@WithMockUser` không chứng minh PBKDF2 được gọi.** Annotation này đặt một authentication giả vào test; để kiểm tra encoder thật phải chạy provider hoặc luồng HTTP login có filter chain tương ứng.

### 12.3. Kiểm tra migration v5_5 → v5_8 → profile mới

Một migration đúng sẽ có dạng:

```text
Bản ghi hiện hữu:
  {pbkdf2}...                        --> verify bằng v5_5
  {pbkdf2@SpringSecurity_v5_8}...    --> verify bằng v5_8

Lần login thành công:
  password raw chỉ tồn tại trong luồng xác thực
         |
         +--> DelegatingPasswordEncoder.matches(...)
         |
         +--> upgradeEncoding(...) == true
         |
         +--> encode(raw) bằng idForEncode mới
         |
         +--> UserDetailsPasswordService update hash trong DB

Bản ghi mới:
  {pbkdf2@policy2026}...             --> verify bằng profile 600000
```

Không lấy chuỗi PBKDF2 v5_5 làm “password thô” rồi encode thêm một lớp PBKDF2 và lưu lại. Làm vậy tạo **hash của hash**, không tương thích cách xác thực người dùng theo raw password. Chỉ rehash sau khi biết mật khẩu đúng hoặc yêu cầu user reset.

## 13. Những lỗi bảo mật và vận hành thường gặp

1. **Dùng SHA-256 đơn lẻ cho password** rồi nghĩ tương đương PBKDF2-HMAC-SHA256. Không có work factor/salt tương ứng.
2. **Lưu plaintext hoặc mật khẩu mã hóa hai chiều không cần thiết.** Một vụ lộ DB/khóa có thể làm lộ password hàng loạt.
3. **Đặt `saltLength=16` rồi hiểu là 16 bit.** Constructor nhận byte: 16 byte = 128 bit.
4. **Đặt `iterations=310000` rồi hiểu hash sẽ có 310000 ký tự.** Iterations là số vòng tính toán, không phải độ dài chuỗi.
5. **Cho rằng hash 256 bit nghĩa là HMAC-SHA256 có đúng 256.000 vòng.** Hai tham số hoàn toàn khác.
6. **Tự làm `encode(input).equals(stored)`.** Salt ngẫu nhiên khiến phép so chuỗi không đúng; dùng `matches`.
7. **Đổi iterations trên cùng ID đang lưu** mà không giữ decoder profile cũ. Password đúng có thể không verify được.
8. **Đổi secret/pepper mà không có version và recovery plan.** Có thể khiến tất cả hash cũ mất khả năng verify.
9. **Đổi `setEncodeHashAsBase64` mà không phân loại dữ liệu cũ.** Output Hex và Base64 khác format; cần mapping riêng.
10. **Giả định `{pbkdf2}` và `{pbkdf2@SpringSecurity_v5_8}` là cùng cấu hình.** Trong factory 6.5 chúng trỏ tới các preset khác nhau.
11. **Cho rằng factory default sẽ encode PBKDF2.** `PasswordEncoderFactories.createDelegatingPasswordEncoder()` trong 6.5 thường ghi mới bằng bcrypt.
12. **Tăng work factor quá cao rồi quên giới hạn đồng thời.** Login endpoint có thể trở thành điểm tiêu tốn CPU gây DoS.
13. **Hạ work factor production chỉ để test chạy nhanh mà không đánh giá lại.** Rủi ro brute force offline tăng; test có thể có profile riêng nhưng phải kiểm tra tính tương thích thật.
14. **Xóa encoder legacy ngay khi deploy thuật toán mới.** Người dùng chưa đăng nhập để migrate sẽ không còn verify được.
15. **Tự thêm tiền tố `{id}` mà không biết chính xác profile cũ.** Prefix sai sẽ làm kết quả match không đúng.
16. **Dùng một ID cho nhiều bộ cấu hình khác nhau.** Không còn khả năng giải thích/verify hash cũ một cách xác định.
17. **Mã hóa Base64 rồi nghĩ hash đã an toàn hơn Hex.** Đây chỉ là biểu diễn dữ liệu, không tăng số vòng hoặc entropy.
18. **Hard-code secret vào source và ghi log hash/password.** Làm mất lợi ích giữ bí mật phía server, tăng nguy cơ lộ credential verifier.
19. **Gọi encoder ở controller thay cho provider** và tự cấp `Authentication` khi tên user khớp. Có thể bỏ qua account-state check và authority mapping.
20. **Nhầm PBKDF2 là cơ chế mã hóa JWT hay session.** Nó là lựa chọn lưu password verifier; token/session dùng cơ chế bảo mật khác.
21. **Nhầm “FIPS-friendly” với đã được chứng nhận FIPS.** Cần đánh giá module/provider và chế độ triển khai thực tế.
22. **Dựa vào tốc độ một lần chạy trên laptop làm work factor chung.** Tải đồng thời và CPU quota trong production có thể rất khác.
23. **Cho rằng SHA-512 luôn mạnh hơn SHA-256 mà không cần thay policy.** PRF, iterations và output length cần được chọn và version cùng nhau.
24. **Dùng hash password làm user ID/token công khai.** Encoded password là dữ liệu xác thực nhạy cảm; không để lộ trong API hoặc URL.
25. **Thay đổi cấu hình trực tiếp giữa lúc rolling deploy.** Node cũ có thể không hiểu ID mới, tạo lỗi login ngắt quãng.
26. **Đặt một mật khẩu mẫu trong code production** vì ví dụ Gradle chạy được. Secrets phải đi qua cơ chế cấu hình an toàn và không commit vào repository.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `Pbkdf2PasswordEncoder` khác `MessageDigestPasswordEncoder("SHA-256")` ở đâu?

**Trả lời:** PBKDF2 dùng salt và nhiều iterations với HMAC, làm mỗi lần đoán password tốn tài nguyên hơn. Băm SHA-256 thông thường quá nhanh để lưu password an toàn.

**Câu 2.** `saltLength=16` nghĩa là 16 byte hay 16 bit? Trong preset v5_8, chuỗi Hex không prefix dài bao nhiêu?

**Trả lời:** 16 byte = 128 bit. Salt 16 byte cộng derived key 32 byte thành 48 byte; Hex dài 96 ký tự.

**Câu 3.** Hai user cùng password, hai kết quả `encode` khác nhau; có phải password sai?

**Trả lời:** Không. Random salt khác nhau dẫn đến encoded hash khác nhau. `matches` lấy salt từ từng bản ghi để kiểm chứng.

**Câu 4.** Vì sao sau khi đổi từ 310.000 sang 600.000 vòng, login user cũ có thể thất bại?

**Trả lời:** Output PBKDF2 không tự chứa đầy đủ số vòng; dùng encoder 600.000 vòng để verify hash tạo bằng 310.000 vòng không tương thích. Phải giữ profile cũ theo ID và nâng cấp khi có raw password hợp lệ.

**Câu 5.** `setEncodeHashAsBase64(true)` có tăng độ khó brute force không?

**Trả lời:** Không. Base64 chỉ đổi cách biểu diễn bytes của salt + derived key; PRF, iterations và entropy không đổi.

**Câu 6.** Trong Spring Security 6.5, `PasswordEncoderFactories.createDelegatingPasswordEncoder()` có mặc định ghi mới bằng PBKDF2 không?

**Trả lời:** Không; factory mặc định thường ghi mới bằng bcrypt. Muốn PBKDF2 làm profile ghi mới phải cấu hình ID và registry tương ứng.

**Câu 7.** Hash `{pbkdf2}...` có thể tự động được hiểu là profile v5_8 không?

**Trả lời:** Không. Trong registry mặc định 6.5, `pbkdf2` gắn với preset legacy v5_5, còn `pbkdf2@SpringSecurity_v5_8` gắn với profile v5_8.

**Câu 8.** `DelegatingPasswordEncoder.upgradeEncoding` báo true có nghĩa DB tự cập nhật ngay không?

**Trả lời:** Không. Cần cơ chế nắm raw password sau xác thực thành công và dịch vụ ghi hash mới, ví dụ `UserDetailsPasswordService` với transaction/concurrency control.

**Câu 9.** PBKDF2-HMAC-SHA256 310.000 vòng có đương nhiên đạt baseline OWASP hiện tại không?

**Trả lời:** Không. OWASP hiện nêu 600.000 vòng cho PBKDF2-HMAC-SHA256 trong khuyến nghị liên quan; cần xem policy, thời điểm, benchmark và môi trường sản phẩm.

**Câu 10.** Salt và secret bổ sung có phải là một không?

**Trả lời:** Không. Salt công khai và được tạo riêng mỗi lần encode; secret bổ sung, nếu dùng, được giữ bí mật phía server. Đổi secret mà không quản lý phiên bản sẽ làm hash cũ khó hoặc không thể verify.

**Câu 11.** Có thể đổi SHA256 sang SHA512 và giữ nguyên prefix ID mà không kiểm tra dữ liệu không?

**Trả lời:** Không. HMAC PRF là một phần của profile; khi đổi phải đặt ID mới và giữ decoder cũ trong giai đoạn migration.

**Câu 12.** Tại sao test `@WithMockUser` không đủ để chứng minh password encoder hoạt động?

**Trả lời:** Mock user thường tạo security context trực tiếp, không đi qua `DaoAuthenticationProvider` và `matches`. Cần test provider thật hoặc login HTTP qua filter chain.

## 15. Tài liệu tham khảo chính thức và checklist áp dụng

Nguồn nên đọc trực tiếp trước khi quyết định policy production:

- [Spring Security 6.5 — Pbkdf2PasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/Pbkdf2PasswordEncoder.html): constructor, preset v5_5/v5_8, `setEncodeHashAsBase64` và thuật toán.
- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): `PasswordEncoder`, `DelegatingPasswordEncoder`, định dạng `{id}encodedPassword` và các encoder theo ID.
- [Spring Security 6.5 — Crypto Module](https://docs.spring.io/spring-security/reference/6.5/features/integrations/cryptography.html): cách dùng PBKDF2 và lưu ý hiệu chỉnh thời gian verify.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): kiểm chứng username/password bằng `UserDetailsService` và `PasswordEncoder`.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): salt, work factor, PBKDF2-HMAC-SHA256, profile 600.000 vòng và migration.
- [NIST SP 800-63B-4 — Password Verifiers](https://pages.nist.gov/800-63-4/sp800-63b.html): salted password hashing, cost factor, thông tin phiên bản và yêu cầu vận hành.
- [Oracle Java 17 — SecretKeyFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKeyFactory.html): API JCA dùng cho PBKDF2 key derivation.

**Checklist trước triển khai:**

- Đã chọn một profile PBKDF2 rõ `PRF + iterations + salt bytes + output format + secret policy`.
- Đã benchmark verify trên môi trường tương tự production với concurrency thực tế.
- Đã phân biệt profile legacy, preset Spring và profile ghi mới bằng version ID.
- Cơ sở dữ liệu lưu đầy đủ hash, ID và không truncate chuỗi.
- Dịch vụ đăng nhập dùng `matches` qua provider, không tự so hash hai lần encode.
- Đã có giới hạn login/rate limiting và cơ chế chống credential stuffing.
- Có test login qua provider/HTTP, test multi-version, test migration và rollback.
- Có kế hoạch vòng đời secret nếu dùng pepper và không lưu secret trong DB.
- Không log password, toàn bộ hash hoặc thông tin nhạy cảm.
- Có chính sách khi nâng work factor theo thời gian, không âm thầm đổi cấu hình ID cũ.

**Kết luận:** `Pbkdf2PasswordEncoder` tạo verifier mật khẩu bằng **PBKDF2 có salt và chi phí iterations được điều chỉnh**. An toàn không chỉ nằm ở một lời gọi `encode`: phải chọn PRF và work factor phù hợp, giữ cấu hình nhất quán khi `matches`, version mỗi thay đổi, bảo vệ secret và triển khai migration an toàn. Trong Spring Security 6.5, preset v5_8 dùng **16-byte salt, PBKDF2-HMAC-SHA256, 310.000 iterations và derived key 256 bit**, còn policy production hiện đại có thể cần cấu hình khác sau khi tham khảo OWASP và benchmark thực tế.