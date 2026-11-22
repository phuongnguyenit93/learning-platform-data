# Quản lý nguồn entropy và tránh seed có thể đoán trong Java

**Bối cảnh:** Java 9 và các phiên bản Java hiện đại, nhóm kiến thức mật mã chuẩn (Java Cryptography Architecture — JCA). Mục tiêu là tạo dữ liệu ngẫu nhiên **khó dự đoán** cho khóa, token, nonce và các chức năng bảo mật; hiểu cách `SecureRandom` nhận seed từ nguồn entropy và tránh làm suy yếu nó bằng seed do ứng dụng tự nghĩ ra.

> **Quy tắc thực hành quan trọng nhất:** Với phần lớn ứng dụng Java, hãy dùng `new SecureRandom()` và gọi `nextBytes(...)` hoặc dùng các API tạo khóa chuẩn của JCA. **Không tự seed bằng thời gian, PID, ID người dùng, mật khẩu, hằng số hoặc `java.util.Random`**. Để `SecureRandom`/security provider lấy entropy từ hệ thống; chỉ chọn provider, DRBG và chính sách reseed chuyên biệt khi có yêu cầu được xác minh.

## 1. Hiểu đúng entropy, seed, CSPRNG và DRBG

**Entropy** là mức bất định của nguồn thông tin đối với người tấn công, thường mô tả bằng bit. Một giá trị trông “rối” hoặc dài 256 bit **không nhất thiết** có 256 bit entropy: nếu nó được tạo hoàn toàn từ một timestamp đoán được, số trường hợp kẻ tấn công cần thử có thể rất nhỏ.

**Seed** là dữ liệu khởi tạo trạng thái bí mật của bộ tạo số ngẫu nhiên. Một seed cho DRBG phải đến từ nguồn entropy đủ mạnh và không thể đoán với khả năng của đối thủ. Seed **không phải** là chuỗi tùy ý có thể thay bằng ngày giờ, hostname hoặc một số nguyên.

**PRNG** (pseudorandom number generator) là thuật toán sinh chuỗi trông ngẫu nhiên từ trạng thái; nhiều PRNG thông thường có thể bị dự đoán khi biết trạng thái hoặc seed, và không được thiết kế cho bí mật. **CSPRNG** là bộ tạo số giả ngẫu nhiên có yêu cầu bảo mật, chống dự đoán đầu ra trong mô hình đe dọa của nó. **DRBG** (deterministic random bit generator) là nhóm cơ chế CSPRNG có trạng thái được dẫn xuất từ seed và có thể reseed theo thiết kế.

Sơ đồ tư duy:

```text
Nguồn entropy đáng tin (thường từ hệ điều hành)
                  |
                  v
   Security provider / JCA SecureRandom
      - khởi tạo (instantiate / seed)
      - cập nhật trạng thái nội bộ
      - reseed khi cơ chế yêu cầu
                  |
                  v
            nextBytes(...)
                  |
      +-----------+-----------+
      |           |           |
   key material  token      nonce/IV
```

- **Entropy source** trả dữ liệu khó đoán; **DRBG** mở rộng trạng thái bí mật đó thành các byte đầu ra, không “sáng tạo thêm” entropy bằng cách băm một seed yếu.
- **Unpredictability** khác **uniqueness**: một giá trị có thể không lặp nhưng đoán được (counter), hoặc khó đoán nhưng vẫn có xác suất trùng (nonce ngẫu nhiên). Từng giao thức yêu cầu thuộc tính riêng.
- **Randomness test** và độ dài output không chứng minh entropy hay an toàn mật mã. Kiểm thử “hai token không giống nhau” là kiểm tra thô, không thể thay cho lựa chọn API/provider đúng.
- **Security strength** của DRBG còn phụ thuộc cơ chế, nguồn entropy, seed, cách vận hành và việc giữ bí mật trạng thái, không thể suy ra chỉ từ số byte được sinh.

## 2. Lựa chọn API ngẫu nhiên trong Java hiện đại

| API | Dùng cho | Có thích hợp với bí mật không? |
| --- | --- | --- |
| `java.security.SecureRandom` | Token, key material, IV/nonce ngẫu nhiên khi giao thức cho phép, salt | **Có**, với provider và môi trường đáng tin |
| `SecureRandom.getInstance("DRBG", ...)` | Cấu hình DRBG từ Java 9, yêu cầu strength/capability cụ thể | **Có**, nếu provider hỗ trợ và đáp ứng chính sách |
| `SecureRandom.getInstanceStrong()` | Lựa chọn theo cấu hình `securerandom.strongAlgorithms` của Java distribution | **Có**, nhưng có thể chặn lâu hơn; không phải lúc nào cũng là lựa chọn tối ưu |
| `java.util.Random`, `Math.random()` | Mô phỏng, logic nghiệp vụ không nhạy cảm | **Không** |
| `ThreadLocalRandom`, `SplittableRandom` | Sinh ngẫu nhiên hiệu năng cao cho thuật toán không phải bảo mật | **Không** |
| `java.util.UUID.randomUUID()` | UUID phiên bản 4 với nguồn ngẫu nhiên mật mã trong JDK Java | Hữu ích cho ID; **không** thay thế việc thiết kế token bí mật đủ độ dài và quản lý vòng đời |

JDK hiện hành vẫn cung cấp `SecureRandom` qua module `java.base`; không cần dependency ngoài để sinh byte ngẫu nhiên mật mã. `SecureRandom` có thể là DRBG, một cơ chế sử dụng trực tiếp nguồn hệ thống hoặc sự kết hợp tùy provider. **Đừng hard-code tên thuật toán/provider theo một hệ điều hành** trừ khi đã có chính sách triển khai và kiểm thử cụ thể.

### `new SecureRandom()` có cần gọi `setSeed()` không?

**Không.** Theo Javadoc hiện hành, với dạng PRNG của `SecureRandom` mới tạo, lần đầu dùng `nextBytes(...)` sẽ kích hoạt lấy seed từ nguồn entropy do implementation chọn. Nếu gọi `setSeed(...)` **trước** lần dùng `nextBytes(...)` hoặc `reseed(...)`, việc tự seed như trên **sẽ không xảy ra** đối với PRNG đó. Vì thế tự gán seed bằng dữ liệu dễ đoán ngay sau khởi tạo có thể làm suy yếu toàn bộ đầu ra.

Một instance có thể dùng lại cho nhiều lần sinh token. `SecureRandom` là API an toàn cho nhiều thread; cơ chế đồng bộ và thông lượng cụ thể phụ thuộc provider. Với ứng dụng chạy dài, dùng một nguồn `SecureRandom` được quản lý có chủ đích thay vì tạo mới và tự seed mỗi request.

## 3. Ví dụ chạy được: tạo token 256 bit bằng entropy do provider quản lý

Ví dụ tạo token ngẫu nhiên 32 byte (256 bit **độ dài đầu ra**), mã hóa Base64 URL-safe **không padding**. Không in token thật ra log trong ví dụ để tránh vô tình làm lộ bí mật. Lưu thành `SecureTokenDemo.java`:

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class SecureTokenDemo {
    private static final SecureRandom RANDOM = new SecureRandom();

    public static void main(String[] args) {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);

        String token = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);

        System.out.println("Token bytes: " + bytes.length);
        System.out.println("Token characters: " + token.length());
        System.out.println("URL-safe alphabet: " + token.matches("[A-Za-z0-9_-]+"));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac SecureTokenDemo.java
java SecureTokenDemo
```

**Stdout xác định** (đã kiểm tra với `javac --release 17` và chạy trên OpenJDK 24):

```text
Token bytes: 32
Token characters: 43
URL-safe alphabet: true
```

**Diễn giải:**

1. `new SecureRandom()` để provider đảm nhiệm seed; không truyền thời gian hay chuỗi cố định vào constructor.
2. `nextBytes(bytes)` làm đầy mảng 32 byte bằng đầu ra của CSPRNG.
3. Base64 URL-safe không padding đổi cách **biểu diễn** byte thành 43 ký tự. Nó không tăng entropy, cũng không phải mã hóa bảo mật hay hash.
4. Token phù hợp làm **giá trị ngẫu nhiên bí mật** nếu được quản lý đúng: chỉ trao cho chủ thể có quyền, dùng qua HTTPS, giới hạn thời gian sống/mục đích, hủy hiệu lực khi dùng xong nếu là reset token.
5. Khi lưu token có entropy cao vào cơ sở dữ liệu, cân nhắc chỉ lưu giá trị hash của token và so khớp cẩn thận; không lưu token thô vào log, URL analytics hoặc lỗi phản hồi. Hash mật khẩu người dùng là bài toán khác, cần KDF chuyên dụng như Argon2id thay vì áp dụng ví dụ này.

**Lưu ý:** 32 byte đầu ra có **dung lượng 256 bit**, nhưng mức bảo mật thực tế còn phụ thuộc seed/entropy source và toàn bộ hệ thống. Không dùng số byte làm bằng chứng rằng hệ điều hành đang có đủ entropy.

## 4. Vì sao seed dễ đoán là một lỗi bảo mật nghiêm trọng?

Giả sử seed được tạo bằng:

```java
// MÃ PHẢN VÍ DỤ: KHÔNG DÙNG CHO BẢO MẬT
SecureRandom insecure = new SecureRandom(
        Long.toString(System.currentTimeMillis()).getBytes(
                java.nio.charset.StandardCharsets.UTF_8));
```

Trình biên dịch có thể chấp nhận đoạn mã, nhưng timestamp có thể đoán từ thời điểm máy khởi chạy, log hoặc khoảng thời gian tạo token. Một PRNG được khởi tạo chỉ bằng seed như vậy có thể trở nên dễ tái tạo hoặc thu hẹp đáng kể không gian tìm kiếm. Chi tiết output phụ thuộc provider; **không mặc định mọi provider đều xuất ra đúng cùng chuỗi**, nhưng đây vẫn là cách seed không phù hợp cho hệ thống bảo mật.

Các seed yếu thường gặp:

- `System.currentTimeMillis()`, `System.nanoTime()` hoặc thời gian deploy: không tạo entropy mật mã đủ mạnh.
- PID, địa chỉ máy, hostname, MAC, `userId`, số thứ tự, counters: thường đoán được hoặc lặp giữa các môi trường.
- Một hằng số như `42`, `"seed"`, chuỗi môi trường cố định hay khóa cấu hình dùng chung ở nhiều instance: có thể tái tạo trạng thái tương tự.
- `new Random().nextLong()` hay `Math.random()` làm seed cho `SecureRandom`: nguồn ban đầu **không được thiết kế cho bí mật**.
- Băm seed yếu (`SHA-256(timestamp)`): output trông dài/khó đọc hơn, nhưng phép băm **không làm tăng entropy** đầu vào.
- Lưu lại trạng thái PRNG/seed trong file image, log, snapshot hoặc dùng lại giữa nhiều instance: có nguy cơ tương quan hay lặp đầu ra, tùy implementation và cách phục hồi trạng thái.

**Không có một “công thức trộn thêm vài nguồn yếu” mặc định an toàn.** Khi có yêu cầu entropy đặc biệt (thiết bị nhúng, HSM, triển khai được chứng nhận), cần nguồn entropy được thiết kế/đánh giá và cấu hình provider theo hướng dẫn chính thức; không tự chế thuật toán trộn hoặc DRBG.

## 5. Các phương thức `SecureRandom`: hiểu trước khi dùng

| Phương thức | Vai trò | Hướng dẫn |
| --- | --- | --- |
| `new SecureRandom()` | Chọn provider/thuật toán mặc định. | Lựa chọn thông thường; để provider tự seed. |
| `nextBytes(byte[])` | Sinh byte ngẫu nhiên mật mã. | Dùng cho secret material có độ dài thích hợp. |
| `nextInt(bound)` | Sinh số nguyên ngẫu nhiên trong `[0, bound)` bằng CSPRNG. | Có thể dùng cho mã số OTP; còn cần rate limit và thời hạn. |
| `SecureRandom.getInstanceStrong()` | Chọn RNG theo cấu hình provider mạnh của môi trường. | Cân nhắc latency/khả năng block; không gọi mỗi request chỉ vì tên `Strong`. |
| `generateSeed(int)` | Sinh seed bytes từ thuật toán tạo seed của implementation. | Dành cho trường hợp phải seed thành phần khác; **không bắt buộc** gọi để “khởi động” chính `SecureRandom`. |
| `SecureRandom.getSeed(int)` | API static tạo seed bytes theo cơ chế seed của lớp. | Không phải API thường ngày để tạo token hay khóa. |
| `setSeed(byte[])`, `setSeed(long)` | Cung cấp thêm seed do caller kiểm soát. | **Tránh tự gọi** trong ứng dụng phổ thông, đặc biệt trước lần `nextBytes`. |
| `reseed()` | Yêu cầu provider reseed từ entropy source. | Từ Java 9; **có thể không được hỗ trợ** và ném `UnsupportedOperationException`. |
| `getParameters()` | Xem các tham số hiệu lực của RNG; DRBG có thể trả `DrbgParameters.Instantiation`. | Có ích khi kiểm tra capability; kết quả có thể là `null`. |

### Chi tiết quan trọng của `setSeed(...)`

Javadoc nói seed được đưa vào **bổ sung, không thay thế** seed hiện tại. Không nên suy ra “seed yếu luôn làm hỏng RNG đã có seed mạnh”: nếu RNG đã khởi tạo đủ entropy, seed bổ sung không được mô tả là giảm tính ngẫu nhiên. **Điểm nguy hiểm nằm ở lúc gọi trước tự khởi tạo**, vì khi đó `SecureRandom` kiểu PRNG sẽ bỏ qua bước auto-seed thông thường.

So sánh:

```java
// ĐÚNG: provider tự quản lý seed/entropy.
SecureRandom good = new SecureRandom();
byte[] randomBytes = new byte[32];
good.nextBytes(randomBytes);

// SAI VỀ THIẾT KẾ: seed do ứng dụng tự nghĩ ra và dễ đoán.
// Không đưa đoạn này vào luồng xử lý token/key thực tế.
SecureRandom bad = new SecureRandom();
bad.setSeed(System.currentTimeMillis());
byte[] unsafeBytes = new byte[32];
bad.nextBytes(unsafeBytes);
```

Hai đoạn là **minh họa sự khác nhau của cách khởi tạo**, không phải phép kiểm thử có thể kết luận mức bảo mật của RNG chỉ từ một lần quan sát output.

### `generateSeed(...)` khác `nextBytes(...)` thế nào?

`nextBytes` sinh dữ liệu mật mã thông qua RNG hiện tại để ứng dụng sử dụng; `generateSeed` yêu cầu byte seed theo cơ chế seed của provider, thường dùng để cấp seed cho bộ tạo ngẫu nhiên khác. `generateSeed(32)` **không đồng nghĩa** với “luôn mạnh hơn `nextBytes(32)`”. Tùy provider/hệ điều hành, `generateSeed`, `nextBytes` hoặc `reseed` có thể chờ nguồn entropy. Không dùng vòng lặp yêu cầu lượng seed lớn để “tăng an toàn” vô điều kiện.

## 6. API DRBG từ Java 9: khi cần cấu hình có chủ đích

Java 9 bổ sung `java.security.DrbgParameters` và các overload của `SecureRandom.getInstance`, `nextBytes`, `reseed` để yêu cầu thông số cho một **Deterministic Random Bit Generator**. Nếu ứng dụng có chính sách cụ thể về strength/reseeding, có thể yêu cầu provider hỗ trợ bằng API chuẩn, thay vì tự triển khai DRBG.

Ví dụ chạy độc lập, lưu `DrbgDemo.java`:

```java
import java.security.DrbgParameters;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;

public final class DrbgDemo {
    public static void main(String[] args) throws NoSuchAlgorithmException {
        SecureRandom drbg = SecureRandom.getInstance(
                "DRBG",
                DrbgParameters.instantiation(
                        256, DrbgParameters.Capability.RESEED_ONLY, null));

        byte[] keyMaterial = new byte[32];
        drbg.nextBytes(keyMaterial);

        System.out.println("Generated bytes: " + keyMaterial.length);
        System.out.println("Has DRBG parameters: "
                + (drbg.getParameters() instanceof DrbgParameters.Instantiation));
    }
}
```

```bash
javac DrbgDemo.java
java DrbgDemo
```

**Stdout trên OpenJDK 24 (SUN provider hỗ trợ DRBG):**

```text
Generated bytes: 32
Has DRBG parameters: true
```

**Lưu ý về tính di động:** `SecureRandom.getInstance("DRBG", params)` có thể ném `NoSuchAlgorithmException` nếu không có provider hỗ trợ đúng thuật toán và yêu cầu. Đoạn ví dụ không mặc định mọi Java runtime, hardware module hoặc security policy đều hỗ trợ yêu cầu 256-bit. Với hệ thống cần tuân thủ một yêu cầu cụ thể, phải kiểm tra `getParameters()` và tài liệu provider đang dùng.

Các capability chính:

- `DrbgParameters.Capability.NONE`: không yêu cầu hỗ trợ reseed/prediction resistance.
- `RESEED_ONLY`: yêu cầu khả năng reseed, nhưng **không** yêu cầu prediction resistance.
- `PR_AND_RESEED`: yêu cầu cả reseed lẫn prediction resistance; chi phí có thể tăng vì cơ chế cần entropy tươi theo yêu cầu.

**Prediction resistance** là một đặc tính liên quan đến việc sử dụng entropy tươi khi tạo đầu ra theo yêu cầu, nhằm hạn chế tác động nếu trạng thái đã bị lộ trước đó. Nó **không** có nghĩa là miễn nhiễm với toàn bộ tấn công, cũng không phải lý do để luôn bật `PR_AND_RESEED` cho mọi lần sinh token. Provider có thể dùng entropy source khác nhau; một số khả năng có thể tốn thời gian chờ.

### Reseed đúng cách

```java
SecureRandom rng = SecureRandom.getInstance("DRBG");
if (rng.getParameters() instanceof DrbgParameters.Instantiation parameters
        && parameters.getCapability().supportsReseeding()) {
    rng.reseed();
}
```

Đây là **đoạn minh họa nằm trong phương thức có khai báo `throws NoSuchAlgorithmException`**; `SecureRandom.getInstance("DRBG")` cần provider phù hợp. Chỉ yêu cầu reseed khi cần theo chính sách và capability; không tự bịa lịch reseed từ timestamp và không giả định reseed luôn được hỗ trợ. `reseed()` lấy entropy từ nguồn của provider, khác với `setSeed(...)` nhận dữ liệu caller đưa vào.

**Personalization string** và **additional input** ở `DrbgParameters` giúp phân biệt ngữ cảnh/cung cấp dữ liệu bổ sung cho DRBG, không có ý nghĩa “một chuỗi đoán được đủ thay entropy”. Đặt `null` khi ứng dụng không cần cấu hình này.

## 7. Sinh khóa: nên dùng `KeyGenerator` cùng RNG tin cậy

Với khóa AES, nên để API tạo khóa của JCA quản lý độ dài và các ràng buộc của thuật toán. Ví dụ này sử dụng provider JDK thông thường; **không in hay lưu raw key**:

Lưu `KeyGenerationDemo.java`:

```java
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class KeyGenerationDemo {
    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, random);
        SecretKey key = generator.generateKey();

        System.out.println("Algorithm: " + key.getAlgorithm());
        System.out.println("Key size (bits): " + (key.getEncoded().length * 8));
    }
}
```

```bash
javac KeyGenerationDemo.java
java KeyGenerationDemo
```

**Stdout trên OpenJDK 24 với provider phần mềm JDK:**

```text
Algorithm: AES
Key size (bits): 256
```

Đây là ví dụ tạo khóa **trong RAM**. `key.getEncoded()` có thể trả `null` ở một số provider/hardware bảo vệ khóa không thể export, nên không dùng kết quả này để kiểm chứng tính bảo mật của mọi provider. Trong thực tế, tạo và lưu khóa qua KeyStore/HSM/KMS phù hợp, kiểm soát quyền, rotation, sao lưu và hủy khóa theo vòng đời. Không tạo lại khóa từ seed dự đoán được khi ứng dụng khởi động.

Lưu ý: mã trên tạo khóa AES, **không tự mã hóa dữ liệu**. Khi sử dụng khóa, phải chọn mode an toàn, ví dụ AES-GCM với cơ chế quản lý nonce đúng; không dùng AES/ECB.

## 8. Token, OTP, salt và nonce không có cùng yêu cầu

| Trường hợp | Thuộc tính cần ưu tiên | Gợi ý triển khai |
| --- | --- | --- |
| Token reset mật khẩu, token xác minh email, session secret | **Khó đoán**, đủ độ dài, thời hạn và quyền truy cập phù hợp | `SecureRandom.nextBytes(32)` rồi Base64 URL-safe, lưu/quản lý kín |
| Mã OTP 6 chữ số | Không đoán được, **giới hạn lượt thử**, hết hạn, một lần sử dụng | `SecureRandom.nextInt(1_000_000)` rồi format `%06d`; 6 chữ số chỉ có 1 triệu khả năng |
| Salt cho password KDF | **Duy nhất/khó trùng** giữa các tài khoản hoặc lần hash; không cần giữ bí mật | Sinh salt mới bằng CSPRNG, lưu cùng bản hash KDF đúng chuẩn |
| AES-GCM 96-bit nonce/IV | **Không được dùng lại dưới cùng một key** | Chọn nonce theo cơ chế được chứng minh phù hợp với số lượng thông điệp và chiến lược quản lý key |
| Khóa mã hóa/khóa MAC | **Bí mật, đủ entropy và key length đúng thuật toán** | `KeyGenerator`/`KeyPairGenerator` với RNG/provider được quản lý |

Ví dụ OTP chỉ là đoạn minh họa; nó không tự tạo hệ thống xác thực an toàn:

```java
SecureRandom random = new SecureRandom();
String otp = String.format(java.util.Locale.ROOT, "%06d",
        random.nextInt(1_000_000));
```

Không log mã OTP thật; lưu bằng cơ chế phù hợp và giới hạn số lần kiểm tra. **Đừng dùng `Math.random()`** để tạo OTP. Trong hệ thống đăng nhập, còn phải chống enumeration, replay, brute-force, đo thời gian và rò rỉ qua kênh hỗ trợ.

**Với AES-GCM:** một IV 12 byte từ CSPRNG có xác suất trùng rất nhỏ ở quy mô phù hợp, nhưng xác suất tích lũy tăng theo số lần mã hóa dưới **cùng key**. Nếu quy mô lớn hoặc yêu cầu bảo đảm không lặp, cần chiến lược nonce riêng, quản lý key và giới hạn số thông điệp theo tài liệu thuật toán. **Không xem “random” là cam kết tuyệt đối về uniqueness**, và không suy ra seed mạnh cho phép tái sử dụng nonce.

## 9. Nguồn entropy trong môi trường triển khai

`SecureRandom` lấy entropy qua **security provider** (thường sử dụng khả năng ngẫu nhiên của hệ điều hành). Đây là nơi cần quan tâm khi triển khai thật:

1. **Nguồn hệ điều hành:** sử dụng bản JDK/provider được hỗ trợ, OS đã khởi tạo bộ sinh ngẫu nhiên và được cập nhật. Đừng chuyển sang một nguồn dễ đoán hoặc tự thay thế entropy source để khắc phục hiệu năng.
2. **Containers, VM và image snapshot:** cần bảo đảm môi trường sau khi khởi động/nhân bản có entropy source phù hợp; tránh đóng băng, sao chép seed hoặc trạng thái DRBG tự quản qua các instance. Nếu dùng platform/HSM đặc thù, theo hướng dẫn vendor và kiểm tra sau restore/fork.
3. **Độ trễ/blocking:** Javadoc nêu `generateSeed`, `reseed`, `nextBytes` có thể block tùy implementation và nguồn entropy. Khởi tạo/lấy seed ở nơi phù hợp, đo trên chính môi trường triển khai; không sửa bằng seed cố định hay chuyển qua PRNG không an toàn.
4. **Provider khác nhau:** `new SecureRandom().getAlgorithm()` và `.getProvider()` hữu ích để kiểm tra cấu hình trong môi trường kiểm thử/vận hành; log **tên provider/thuật toán**, không log seed, state, token hay khóa.
5. **Yêu cầu kiểm định:** lớp `SecureRandom` không tự xác nhận một triển khai đã được chứng nhận FIPS hoặc tuân thủ chuẩn nội bộ. Nếu có yêu cầu chứng nhận, phải dùng provider/module và cấu hình được phê duyệt, kiểm tra cả toàn bộ môi trường và vòng đời khóa.

Ví dụ kiểm tra thông tin **không chứa bí mật**:

```java
SecureRandom rng = new SecureRandom();
System.out.println(rng.getAlgorithm());
System.out.println(rng.getProvider().getName());
```

Output phụ thuộc JDK, hệ điều hành và provider; vì vậy không trình bày stdout cố định cho đoạn này. Khi tối ưu hiệu năng, đo provider đang dùng, tránh tạo instance/đọc seed lặp không cần thiết và giữ kiến trúc thread-safe.

## 10. Những ngộ nhận thường gặp

| Ngộ nhận | Vì sao sai | Thực hành đúng |
| --- | --- | --- |
| “Chỉ cần seed đủ **dài** là mạnh.” | Timestamp băm ra 256 bit vẫn dễ đoán theo input. | Quan tâm **entropy không thể đoán**, không chỉ số byte. |
| “Phải `setSeed(System.nanoTime())` để tăng ngẫu nhiên.” | Có thể ngăn bước tự lấy seed của PRNG mới tạo. | Dùng `new SecureRandom()` và `nextBytes(...)`. |
| “`SecureRandom` tạo 32 byte nghĩa là đúng 256-bit bảo mật.” | Bảo mật phụ thuộc nguồn entropy, DRBG và provider. | Kiểm tra toàn hệ thống và strength khi cần. |
| “`setSeed()` luôn xóa seed cũ.” | Javadoc mô tả **bổ sung** seed hiện có. | Tránh tự seed; phân biệt khởi tạo mới và bổ sung sau khởi tạo. |
| “`getInstanceStrong()` luôn nhanh và tốt hơn `new SecureRandom()`.” | Thuật toán được chọn theo cấu hình, có thể có đặc tính blocking. | Chọn theo yêu cầu và đo trên môi trường thật. |
| “`reseed()` ở đâu cũng gọi được.” | Provider có thể không hỗ trợ. | Kiểm tra capability; dùng chính sách của provider. |
| “`ThreadLocalRandom` nhanh hơn nên tốt để sinh token.” | Không phải CSPRNG. | Dùng `SecureRandom` cho secret. |
| “Nonce ngẫu nhiên chắc chắn không trùng.” | Vẫn có xác suất collision. | Thiết kế theo yêu cầu uniqueness của giao thức. |
| “Có thể lưu seed trong config để tái tạo khóa.” | Dễ lộ/đoán và tạo mối phụ thuộc nguy hiểm giữa các môi trường. | Sinh khóa đúng chuẩn và quản lý trong KMS/KeyStore/HSM. |
| “Có thể kiểm chứng entropy bằng một vài lần chạy và xem chuỗi có khác nhau.” | Không đánh giá được độ khó dự đoán của seed. | Dùng API/source được tin cậy và kiểm thử hệ thống thực tế. |

## 11. Checklist triển khai và cách kiểm thử hữu ích

**Khi review code:**

1. Tìm các nơi sinh khóa, token, OTP, salt, IV; kiểm tra API nguồn có phải `SecureRandom` hoặc bộ tạo khóa mật mã phù hợp.
2. Tìm `new SecureRandom(byte[])`, `setSeed(...)`, `Random`, `Math.random`, `ThreadLocalRandom`, `nanoTime`, `currentTimeMillis` trong luồng sinh secret. Phân biệt test/demo với production; với seed tự sinh phải có lý do mật mã và nguồn entropy được thẩm định.
3. Kiểm tra các ràng buộc **ngoài RNG**: token expiry/revoke, OTP rate limit, salt KDF, uniqueness của GCM nonce, key storage/rotation.
4. Xác nhận môi trường container/VM có seed/entropy source đáng tin sau startup/restore và provider được cấu hình đúng; không log secret.
5. Khi yêu cầu DRBG rõ ràng, kiểm tra implementation có hỗ trợ strength/capability, xử lý `NoSuchAlgorithmException`, `UnsupportedOperationException` và khả năng blocking.

**Khi viết test:**

- Unit test logic **định dạng và độ dài**: 32 byte thành Base64 URL-safe không padding dài 43 ký tự; dữ liệu có thể decode ngược 32 byte. Không hard-code giá trị token thực tế.
- Integration test với provider đang triển khai: tạo token/khóa thành công, đo latency phù hợp, kiểm tra chính sách vận hành; nếu có policy DRBG, kiểm tra `getParameters()`/capabilities.
- Không dùng unit test “hai token liên tiếp phải khác” làm bằng chứng bảo mật. Kiểm thử thống kê vài nghìn output không xác định được min-entropy nguồn.
- Khi cần test lặp lại được cho **logic không bảo mật**, cô lập phần đó bằng dependency/test double riêng. Đừng đưa seed xác định vào luồng sản xuất để biến `SecureRandom` thành generator có output cố định.

### Bài tập tự kiểm tra

1. Một ứng dụng tạo token bằng `new SecureRandom(Long.toString(System.currentTimeMillis()).getBytes())`. Tại sao token dài 32 byte vẫn có thể đoán? Cách sửa tối thiểu?
2. Khác biệt về nguồn entropy giữa `nextBytes(bytes)` trên `new SecureRandom()` và việc gọi `setSeed(42L)` **trước** `nextBytes`?
3. Khi nào cần `getInstance("DRBG", DrbgParameters.instantiation(...))` thay vì `new SecureRandom()`? Nếu provider không hỗ trợ tham số đã yêu cầu, ứng dụng phải làm gì?
4. Vì sao 6 chữ số OTP dù sinh bằng CSPRNG vẫn cần giới hạn lượt thử?
5. Tại sao AES-GCM cần thiết kế uniqueness cho nonce ngoài việc chọn RNG mạnh?

**Định hướng đáp án:** Seed timestamp dễ thu hẹp không gian thử; mặc định nên để provider tự seed; `setSeed` sớm có thể ngăn auto-seed; DRBG chỉ cấu hình đặc thù khi chính sách yêu cầu và cần xử lý trường hợp provider không hỗ trợ; OTP 6 số chỉ khoảng 20 bit không gian thử; còn GCM cấm tái sử dụng nonce với cùng key, trong khi số ngẫu nhiên không cam kết tuyệt đối không trùng.

## Tài liệu tham khảo còn áp dụng

- [Oracle Java SE 26 — `SecureRandom`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/SecureRandom.html): seed tự động, `setSeed`, `nextBytes`, `getInstanceStrong`, `reseed` và khả năng block.
- [Oracle Java SE 26 — `DrbgParameters`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/DrbgParameters.html): cấu hình DRBG từ Java 9, strength, reseed và prediction resistance.
- [Oracle Java SE 26 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html): tên thuật toán JCA chuẩn.
- [OWASP — Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): phân biệt CSPRNG và PRNG, token/key generation, quản lý key.
- [NIST SP 800-90B — Entropy Sources](https://www.nist.gov/publications/recommendation-entropy-sources-used-random-bit-generation): yêu cầu và đánh giá nguồn entropy cho random bit generators.

**Ghi nhớ:** `SecureRandom` là công cụ chuẩn, provider/entropy source là nền tảng an toàn, và seed do người lập trình tự đặt là một trong những cách dễ nhất để làm suy yếu hệ thống. Chọn nguồn entropy đúng, tránh seed đoán được, đồng thời thiết kế đúng vòng đời của token, khóa và nonce.
