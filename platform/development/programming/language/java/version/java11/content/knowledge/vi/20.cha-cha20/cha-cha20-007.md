# Quy tắc không dùng lại nonce với cùng khóa trong ChaCha20 (Java 11+)

## 1. Nguyên tắc bất biến: một khóa, một nonce, một lần mã hóa thông điệp

**ChaCha20** là stream cipher; **ChaCha20-Poly1305** là chế độ mã hóa có xác thực (**AEAD**) kết hợp ChaCha20 với bộ kiểm tra toàn vẹn Poly1305. Hai thuật toán được Java hỗ trợ từ **Java 11**, và nguyên tắc an toàn quan trọng nhất của cả hai là:

> **Với cùng một khóa bí mật, mỗi lần mã hóa một thông điệp mới phải sử dụng một nonce mới, chưa từng sử dụng với khóa đó.**

Trong biến thể IETF theo **RFC 8439**, ChaCha20 dùng:

- **Key:** 256 bit = 32 byte, phải bí mật.
- **Nonce:** 96 bit = 12 byte, **không cần bí mật** nhưng **phải duy nhất theo từng key**.
- **Block counter:** 32 bit, đếm các block keystream **bên trong một thông điệp**; không thay thế nonce.
- **Block keystream:** 64 byte; counter tăng khi mã hóa những block kế tiếp.

Với ChaCha20-Poly1305, cùng một tổ hợp **key + nonce** còn được dùng để dẫn xuất khóa Poly1305 dùng một lần. Tái sử dụng nonce không chỉ gây lộ dữ liệu mà còn phá vỡ giả thiết an toàn của cơ chế xác thực thông điệp.

Quy tắc **không dùng lại** áp dụng cho **hai lần mã hóa thông điệp khác nhau**. Khi giải mã, bên nhận **phải dùng lại đúng key và nonce được dùng để mã hóa chính ciphertext ấy**; đó là điều cần thiết, không phải vi phạm. Gửi lại **nguyên văn ciphertext đã tạo** không phải lần mã hóa mới, nhưng hệ thống vẫn cần phòng chống **replay attack** ở tầng giao thức.

## 2. Nonce, block counter và key khác nhau thế nào?

| Giá trị | Kích thước / vai trò | Điều được phép | Điều không được làm |
| --- | --- | --- | --- |
| **Key** | 32 byte, quyết định keystream; cần giữ bí mật | Tạo bằng CSPRNG; quản lý vòng đời và rotate | In vào log, hardcode production, chia sẻ bừa bãi |
| **Nonce** | 12 byte, tách biệt thông điệp theo cùng key | Lưu/truyền công khai cùng ciphertext, miễn duy nhất theo key | Dùng nonce cố định, reset về 0 khi restart mà giữ nguyên key |
| **Block counter** | 32 bit, xác định vị trí block ChaCha20 trong **một lần mã hóa** | Đặt theo thuật toán/giao thức; tự tăng qua các block | Thay nonce bằng việc đổi counter theo cảm tính; dùng lại vùng counter trùng |
| **Plaintext** | Nội dung cần bảo mật | Mã hóa bằng keystream chưa từng dùng lại | Mã hóa nhiều plaintext bằng cùng key + nonce + cùng đoạn keystream |
| **Authentication tag** (AEAD) | 16 byte Poly1305 theo RFC 8439 | Kiểm tra khi giải mã; thất bại thì bỏ bản tin | Bỏ qua kiểm tra tag hoặc tái sử dụng key Poly1305 do lặp nonce |

**Đừng nhầm hai loại “counter”.** Một ứng dụng có thể dùng **message sequence number** (ví dụ một số `long` tăng đơn điệu) để **tạo nonce 12 byte**. Đây là bộ đếm **thông điệp** thuộc thiết kế giao thức. Còn đối số `counter` trong `ChaCha20ParameterSpec` là **block counter mật mã** của ChaCha20. Dùng `ChaCha20ParameterSpec(nonce, counter + 1)` cho bản tin mới không thay thế chính sách nonce duy nhất, vì thông điệp dài có thể tiêu thụ nhiều block và gây chồng lấn keystream. Với **ChaCha20-Poly1305**, nonce còn quyết định khóa Poly1305 dùng một lần, nên đổi block counter cũng không cứu được nonce reuse.

**Nonce không phải password/secret.** Thông thường bên giải mã cần nhận nonce kèm ciphertext. Tính bảo mật đến từ **key bí mật** và việc sử dụng nonce duy nhất theo key, chứ không phụ thuộc giữ nonce kín.

## 3. Vì sao reuse nonce làm lộ thông tin?

ChaCha20 tạo một chuỗi keystream `S` từ **key + nonce + block counter**. Mã hóa theo phép XOR:

```text
C1 = P1 XOR S
C2 = P2 XOR S        (SAI: key, nonce, vùng counter trùng nhau)
-----------------------------------------------
C1 XOR C2 = P1 XOR P2
```

Nếu hai bản tin được mã hóa với **cùng keystream**, keystream sẽ bị triệt tiêu khi XOR hai ciphertext. Kẻ tấn công có thể biết `P1 XOR P2` và khai thác ngôn ngữ tự nhiên, cấu trúc file/protocol hoặc một plaintext đã biết để suy ra phần tương ứng của plaintext kia.

Ví dụ, nếu attacker biết một plaintext `P1` và có `C1`, họ khôi phục keystream đoạn đó bằng `S = C1 XOR P1`, rồi tính `P2 = C2 XOR S` cho đoạn trùng. Đây là **lỗi cấu hình sử dụng stream cipher**, không phải lỗi phép toán ChaCha20. Ciphertext vẫn có vẻ ngẫu nhiên nhưng **không còn được bảo mật như kỳ vọng**.

Với **ChaCha20-Poly1305**, hậu quả còn nghiêm trọng hơn: trùng nonce khiến **one-time Poly1305 key** cũng trùng, phá vỡ cơ sở bảo đảm toàn vẹn/xác thực; việc giả mạo thông điệp có thể trở nên khả thi trong các điều kiện tấn công thích hợp. Không sửa bằng cách chỉ thay AAD, thay plaintext, đổi thread, tạo `Cipher` mới hay tăng counter của ChaCha20. **Phải đảm bảo nonce khác nhau dưới cùng key cho mọi lần mã hóa mới.**

## 4. API Java 11: ChaCha20 và ChaCha20-Poly1305 dùng tham số khác nhau

Java Cryptography Extension (**JCE**) có các tên thuật toán:

| Trường hợp | Tên transformation | Tham số khởi tạo | Khả năng kiểm tra toàn vẹn |
| --- | --- | --- | --- |
| ChaCha20 raw | `Cipher.getInstance("ChaCha20")` | `new ChaCha20ParameterSpec(nonce12, initialBlockCounter)` | **Không có tag**; phải dùng giao thức xác thực khác nếu thật sự sử dụng |
| ChaCha20-Poly1305 AEAD | `Cipher.getInstance("ChaCha20-Poly1305")` | `new IvParameterSpec(nonce12)` | Có tag xác thực Poly1305 **16 byte** và hỗ trợ AAD |
| Sinh khóa phù hợp | `KeyGenerator.getInstance("ChaCha20")` | `init(256)` | Sinh khóa 256 bit dùng được với ChaCha20/ChaCha20-Poly1305 |

**ChaCha20ParameterSpec** (Java 11+) yêu cầu **nonce đúng 12 byte** và **initial block counter kiểu `int`**:

```java
byte[] nonce = new byte[12];  // Chỉ là khai báo buffer: KHÔNG dùng nonce toàn 0 lặp lại.
ChaCha20ParameterSpec params =
        new ChaCha20ParameterSpec(nonce, 1);
```

Đoạn trên là **mã minh họa kiểu tham số**, **không phải cách tạo nonce an toàn**; `new byte[12]` chứa toàn số 0. Một nonce toàn 0 **có thể** là giá trị hợp lệ một lần trong một giao thức có quy tắc uniqueness, nhưng **không được dùng mặc định cho mọi bản tin**.

`ChaCha20ParameterSpec.getNonce()` trả **bản sao mảng nonce**; `getCounter()` trả block counter đã đặt. Constructor từ chối nonce không dài đúng 12 byte bằng `IllegalArgumentException`. **Không** dùng `ChaCha20ParameterSpec` để khởi tạo `"ChaCha20-Poly1305"` trên SunJCE; chế độ AEAD yêu cầu `IvParameterSpec` của 12-byte nonce.

`Cipher` không phải đối tượng thread-safe để tái sử dụng tùy tiện giữa nhiều luồng. Một số provider phát hiện dùng lại key + nonce khi **khởi tạo lại cùng instance Cipher** và có thể từ chối. **Đây không phải bảo vệ toàn cục**: provider không thể tự biết các nonce đã sử dụng trên những `Cipher` instance khác, tiến trình khác hoặc sau restart. Hãy kiểm soát uniqueness ở tầng quản lý key và nonce của ứng dụng.

Trong code production, nếu chỉ cần mã hóa dữ liệu có bảo mật **và toàn vẹn**, thường nên dùng **ChaCha20-Poly1305 AEAD** thay vì ChaCha20 raw không có xác thực.

## 5. Ví dụ Java 11+ hoàn chỉnh: thử XOR leak và cách dùng nonce riêng với AEAD

Ví dụ có hai phần **được tách khóa**:

1. **Phần minh họa cố ý sai**: tạo hai ciphertext từ hai plaintext khác nhau bằng **cùng key + nonce + counter** của *ChaCha20 raw* để chứng minh `C1 XOR C2 == P1 XOR P2`. Đoạn này chỉ dùng cho học tập, **không sử dụng trong sản phẩm**.
2. **Phần đúng theo yêu cầu nonce uniqueness**: tạo **một khóa ChaCha20-Poly1305 khác**, dùng hai nonce khác nhau và kiểm tra round trip, sửa ciphertext/AAD bị từ chối.

Để tránh phụ thuộc may rủi, demo tạo **nonce theo sequence number** trong một phiên dùng key mới. Một message sequence `1` và `2` tạo hai mảng 12-byte khác nhau. Phần triển khai thực tế ở mục sau sẽ bàn về phối hợp nhiều producer, lưu sequence qua restart và key rotation.

Lưu tệp **`ChaChaNonceRuleDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.ChaCha20ParameterSpec;
import javax.crypto.spec.IvParameterSpec;

public class ChaChaNonceRuleDemo {
    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
        generator.init(256);

        byte[] first = "HELLO".getBytes(StandardCharsets.UTF_8);
        byte[] second = "WORLD".getBytes(StandardCharsets.UTF_8);

        // THỬ NGHIỆM CỐ Ý KHÔNG AN TOÀN: không dùng kiểu này trong ứng dụng!
        SecretKey unsafeDemoKey = generator.generateKey();
        byte[] reusedNonce = nonceForSequence(1L);
        byte[] raw1 = rawChaCha20(unsafeDemoKey, reusedNonce, first);
        byte[] raw2 = rawChaCha20(unsafeDemoKey, reusedNonce, second);
        boolean xorLeak = Arrays.equals(
                xor(raw1, raw2), xor(first, second));

        // PHẦN AN TOÀN: khóa riêng, mỗi lần encrypt dùng một nonce khác.
        SecretKey aeadKey = generator.generateKey();
        byte[] nonce1 = nonceForSequence(1L);
        byte[] nonce2 = nonceForSequence(2L);
        byte[] aad = "demo:v1".getBytes(StandardCharsets.UTF_8);

        byte[] encrypted1 = encryptAead(aeadKey, nonce1, aad, first);
        byte[] encrypted2 = encryptAead(aeadKey, nonce2, aad, second);
        byte[] decrypted1 = decryptAead(aeadKey, nonce1, aad, encrypted1);
        byte[] decrypted2 = decryptAead(aeadKey, nonce2, aad, encrypted2);

        byte[] tampered = encrypted1.clone();
        tampered[tampered.length - 1] ^= 1;

        boolean tamperRejected = rejectsTag(
                aeadKey, nonce1, aad, tampered);
        boolean aadMismatchRejected = rejectsTag(
                aeadKey, nonce1,
                "demo:v2".getBytes(StandardCharsets.UTF_8), encrypted1);

        System.out.println("nonceBytes=" + nonce1.length);
        System.out.println("noncesDifferent=" +
                !Arrays.equals(nonce1, nonce2));
        System.out.println("unsafeReuseLeaksXor=" + xorLeak);
        System.out.println("aeadTagBytes=" + (encrypted1.length - first.length));
        System.out.println("roundTrip=" +
                (Arrays.equals(first, decrypted1)
                        && Arrays.equals(second, decrypted2)));
        System.out.println("tamperRejected=" + tamperRejected);
        System.out.println("aadMismatchRejected=" + aadMismatchRejected);
    }

    // Chỉ minh họa phiên một-sender/một-key; xem mục 6 về production.
    private static byte[] nonceForSequence(long sequence) {
        if (sequence <= 0) {
            throw new IllegalArgumentException("sequence must be positive");
        }
        return ByteBuffer.allocate(12)
                .putInt(0x12345678)
                .putLong(sequence)
                .array();
    }

    private static byte[] rawChaCha20(
            SecretKey key, byte[] nonce, byte[] plaintext) throws Exception {
        Cipher cipher = Cipher.getInstance("ChaCha20");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new ChaCha20ParameterSpec(nonce, 1));
        return cipher.doFinal(plaintext);
    }

    private static byte[] encryptAead(
            SecretKey key, byte[] nonce, byte[] aad, byte[] plaintext)
            throws Exception {
        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(plaintext); // Ciphertext + 16-byte tag.
    }

    private static byte[] decryptAead(
            SecretKey key, byte[] nonce, byte[] aad, byte[] ciphertext)
            throws Exception {
        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertext); // Xác thực tag trước khi chấp nhận.
    }

    private static boolean rejectsTag(
            SecretKey key, byte[] nonce, byte[] aad, byte[] ciphertext)
            throws Exception {
        try {
            decryptAead(key, nonce, aad, ciphertext);
            return false;
        } catch (AEADBadTagException expected) {
            return true;
        }
    }

    private static byte[] xor(byte[] a, byte[] b) {
        if (a.length != b.length) {
            throw new IllegalArgumentException("different lengths");
        }
        byte[] out = new byte[a.length];
        for (int i = 0; i < out.length; i++) {
            out[i] = (byte) (a[i] ^ b[i]);
        }
        return out;
    }
}
```

Biên dịch và chạy bằng **JDK 17+**, dùng API hỗ trợ ngay từ Java 11:

```bash
javac --release 11 ChaChaNonceRuleDemo.java
java ChaChaNonceRuleDemo
```

**Stdout kỳ vọng với provider SunJCE hỗ trợ ChaCha20/ChaCha20-Poly1305:**

```text
nonceBytes=12
noncesDifferent=true
unsafeReuseLeaksXor=true
aeadTagBytes=16
roundTrip=true
tamperRejected=true
aadMismatchRejected=true
```

**Giải thích từng dòng:**

- `nonceBytes=12`: 96-bit nonce đúng theo IETF ChaCha20.
- `noncesDifferent=true`: sequence 1 và 2 mã hóa vào 12 byte khác nhau. Với **cùng key AEAD**, không có nonce reuse giữa hai lần mã hóa của demo.
- `unsafeReuseLeaksXor=true`: phần cố ý sai tạo cùng keystream ở hai lần raw ChaCha20; từ ciphertext có thể khôi phục XOR của hai plaintext. Chỉ dùng để minh họa hậu quả, **không xem đây là cách mã hóa hợp lệ**.
- `aeadTagBytes=16`: `ChaCha20-Poly1305` trên SunJCE thêm 16 byte tag vào ciphertext. Mã hóa một chuỗi dài 5 byte tạo 21 byte ciphertext + tag.
- `roundTrip=true`: cả hai ciphertext được giải mã bằng **chính key + nonce + AAD** lúc mã hóa.
- `tamperRejected=true`: cố ý sửa byte cuối khiến kiểm tra tag không hợp lệ và `Cipher.doFinal(...)` ném `AEADBadTagException`.
- `aadMismatchRejected=true`: dùng AAD khác khi giải mã khiến xác thực thất bại. AAD không được mã hóa nhưng được ràng buộc về tính toàn vẹn.
- Chương trình **không in key, nonce, keystream hay plaintext bí mật**; nonce trong demo xây từ số thứ tự đơn giản, không phải khóa bí mật.

**Giới hạn của demo:** prefix `0x12345678` chỉ là giá trị cố định để minh họa một khóa mới, một sender và hai sequence. Trong production, không được dùng prefix cố định + sequence reset khi nhiều tiến trình dùng **cùng key**, hoặc khi key được giữ lại qua restart. Phải có chiến lược quản lý nonce theo vòng đời khóa, được mô tả tiếp theo.

## 6. Thiết kế nonce duy nhất qua thời gian, luồng và tiến trình

### 6.1. Tạo nonce từ message sequence tăng đơn điệu

Với một **sender** mã hóa bằng một key, một cách quản lý tốt là xây nonce 96 bit từ:

```text
nonce (96 bit) = sender-id / domain (32 bit) || message-sequence (64 bit)
                  4 byte                  || 8 byte
```

Các byte có thể được định nghĩa theo byte order cố định, ví dụ `ByteBuffer` Java mặc định big-endian, miễn **hai phía thống nhất cùng quy tắc** và không trùng một nonce cho cùng key. Đừng nhầm byte order của **cấu trúc nonce ứng dụng** với các phép toán little-endian nội bộ của ChaCha20: nonce được truyền như **12 byte đúng thứ tự** vào API.

Một số nguyên tắc triển khai:

1. Mỗi **key** có một **nonce namespace** riêng. Bộ đếm của key A có thể bắt đầu từ 1 độc lập với key B; nhưng **cùng key** không được reset counter và mã hóa lại bằng nonce cũ.
2. Trong một tiến trình, cấp sequence **nguyên tử** khi nhiều thread mã hóa đồng thời, tránh hai thread lấy cùng giá trị. `AtomicLong.getAndIncrement()` có thể hỗ trợ, nhưng phải **chống wrap-around** và phân biệt khi đã cấp/ghi/dùng nonce.
3. Khi **restart** mà key vẫn còn, phải lưu trạng thái nonce hoặc có cơ chế cấp dải sequence **bền vững, chống cấp trùng**. Đừng chỉ để `long seq=1` trong bộ nhớ rồi khởi động lại.
4. Khi có **nhiều node/producer** dùng cùng key, phải có **sender-id/domain duy nhất** hoặc dịch vụ cấp phát nonce tập trung, cấp dải khác nhau. Không tự giả định hostname, PID, timestamp hoặc một số random 32-bit prefix luôn duy nhất.
5. Nếu sequence sắp cạn hoặc hệ thống mất khả năng chứng minh uniqueness, **dừng mã hóa bằng key đó và rotate/rekey** trước khi có collision.
6. Khi cần retry ghi dữ liệu, phân biệt: **gửi lại ciphertext đã tạo** (không tạo phép mã hóa mới) và **chạy lại hàm encrypt** (phải cấp nonce mới). Nếu không có giao thức idempotent/replay protection, việc gửi lại cùng ciphertext vẫn có thể bị replay ở lớp ứng dụng.

**Lưu ý về crash consistency:** chỉ cập nhật counter bền vững **sau** khi ghi ciphertext là nguy hiểm. Tiến trình có thể mã hóa xong rồi crash trước khi lưu counter, khiến lần sau tái sử dụng nonce đó. Cần đặt chính sách “reserve nonce/dải nonce trước khi dùng”, transaction/lease bền vững hoặc tạo **key phiên mới** khi restart, tùy threat model. Nếu lưu key trên nhiều node, các node phải phối hợp uniqueness.

### 6.2. Dùng SecureRandom có đủ an toàn không?

Nonce ChaCha20 **không cần bí mật**, nên CSPRNG có thể tạo nonce có xác suất va chạm thấp. Tuy nhiên, với **nonce 96 bit**, “ngẫu nhiên” không chứng minh **duy nhất tuyệt đối**, và xác suất trùng tăng theo số lượng bản tin dùng cùng key (birthday effect). RFC 8439 nhấn mạnh **nonces MUST be different for the same key**; chiến lược tốt hơn khi có thể là **sequence/counter được bảo đảm duy nhất**.

Nếu hệ thống chọn random nonce, phải đưa ra **giới hạn số bản tin trên mỗi key**, cách phát hiện/đối phó va chạm, chính sách rotate, yêu cầu nhiều producer và rủi ro chấp nhận theo thiết kế; **không** coi `new SecureRandom().nextBytes(nonce)` tự động bảo đảm toàn bộ vòng đời. Đặc biệt không dùng `java.util.Random`, timestamp, PID, hash plaintext hay prefix thấp entropy như một “bảo đảm duy nhất”.

### 6.3. Nonce nên được lưu cùng dữ liệu mã hóa

Để giải mã, bên nhận cần biết **key nào**, **nonce nào**, **AAD nào** và **ciphertext + tag**. Một định dạng bản ghi có thể mô tả:

```text
record = version || key-id || nonce(12 bytes) || ciphertext || tag(16 bytes)
AAD    = version || key-id || record-type (theo protocol)
```

Đây là **sơ đồ giao thức minh họa**, không phải format chuẩn mặc định của Java. `version` và `key-id` thường công khai; vẫn có thể đưa chúng vào AAD để chống tráo metadata. `Cipher.doFinal()` của ChaCha20-Poly1305 trả **ciphertext kèm tag**, không tự chèn 12-byte nonce. Ứng dụng phải lưu/đính kèm nonce và xác định cấu trúc record riêng.

Đừng tin mù quáng `key-id` do bên ngoài cung cấp; cần kiểm soát policy chọn key, chống downgrade, xác thực AAD, chống replay và giới hạn kích thước khi parse.

## 7. Vì sao đổi initial counter không thể dùng làm lời giải cho nonce reuse?

Với **raw ChaCha20**, keystream dùng bộ ba:

```text
keystream = ChaCha20(key, nonce, initial-block-counter)
```

Nếu hai lần mã hóa cùng key + nonce **và cùng vùng block counter**, các byte keystream trùng và xảy ra XOR leak. Kể cả khi hai lần gọi đặt initial counter khác nhau, **một thông điệp dài** có thể tiêu thụ nhiều block và **chồng** sang vùng counter của thông điệp khác. Bởi vậy “tăng `counter` thêm 1, giữ nguyên nonce” không phải chính sách tách biệt các bản tin an toàn.

Với **ChaCha20-Poly1305**, cấu trúc AEAD dùng **counter 0** để tạo khóa Poly1305 và bắt đầu mã hóa payload từ **counter 1** theo RFC 8439. `Cipher` AEAD quản lý chi tiết này; API Java nhận **nonce** qua `IvParameterSpec` chứ **không** nhận initial counter. Tái sử dụng key + nonce khiến **khóa Poly1305 dùng một lần cũng bị dùng lại**, bất kể AAD hoặc plaintext khác nhau.

Một nonce chỉ được dùng để mã hóa một thông điệp dưới cùng key. Không cần và **không được** tự giả lập nonce uniqueness bằng cách dịch counter block của AEAD. Sau khi hết khả năng tạo nonce mới hay gần đến giới hạn block trên một nonce, **đổi nonce/key** theo giao thức thay vì để counter wrap. Biến thể IETF RFC 8439 có giới hạn lượng dữ liệu cho từng nonce do block counter 32 bit; không xây hệ thống dựa vào việc nó sẽ tự quay vòng an toàn.

## 8. Tại sao decryption được dùng lại nonce?

Nếu một bản ghi được mã hóa bằng:

```text
key K + nonce N + AAD A + plaintext P
            -> ciphertext C + tag T
```

Bên nhận **phải** giải mã bằng đúng `K, N, A` để xác minh `T` và lấy `P`. Điều này không vi phạm quy tắc, vì **không sinh ra ciphertext mới từ plaintext khác bằng cùng `K, N`**.

Nếu kẻ tấn công phát lại nguyên gói `(N,C,T)`, tag vẫn có thể hợp lệ vì ciphertext chưa bị chỉnh sửa. AEAD cung cấp **confidentiality + integrity/authentication of ciphertext**, nhưng **không tự ngăn replay**. Giao thức cần message sequence, session ID, replay window hoặc cơ chế idempotency thích hợp. Không xem nonce uniqueness bên phía gửi là giải pháp trọn vẹn cho replay detection phía nhận.

**Khi cần mã hóa lại cùng plaintext**, vẫn phải dùng nonce mới (và tính tag mới); “plaintext giống nhau” **không** làm ngoại lệ cho quy tắc. Khi đổi sang **key thực sự khác** theo quy trình rekey an toàn, cùng giá trị nonce byte có thể được dùng lại dưới key mới; uniqueness là thuộc tính của **cặp (key, nonce)**, không yêu cầu một danh sách nonce duy nhất cho mọi key của hệ thống.

## 9. Những lỗi thường gặp

| Lỗi | Hậu quả / cách sửa |
| --- | --- |
| Dùng `new byte[12]` cho mọi lần encrypt | Nonce luôn 0, làm lặp keystream và AEAD one-time key; phải cấp nonce duy nhất. |
| Lưu key bền vững nhưng reset nonce counter sau reboot | Reuse với cùng key; lưu trạng thái chống trùng hoặc rekey. |
| Nhiều thread cùng đọc `seq` rồi cùng encrypt | Hai bản tin có nonce trùng; dùng cấp phát nguyên tử và chống wrap. |
| Nhiều server dùng cùng key + cùng prefix và counter | Cross-node nonce collision; partition namespace hoặc allocator tập trung. |
| Tưởng nonce phải bí mật nên sinh từ password | Nonce không cần bí mật; cần **duy nhất**, còn key phải giữ bí mật và đủ entropy. |
| Tăng `ChaCha20ParameterSpec.counter` nhưng giữ nonce | Không bảo đảm vùng keystream không chồng; AEAD vẫn trùng Poly1305 key. |
| Coi mã hóa ChaCha20 raw là đủ toàn vẹn | Raw ChaCha20 không có tag; dùng AEAD khi cần bảo mật + toàn vẹn. |
| Dùng `ChaCha20ParameterSpec` cho `ChaCha20-Poly1305` | Sai loại tham số đối với SunJCE; dùng `IvParameterSpec(nonce12)`. |
| Dùng random nonce không giới hạn lượng bản tin/key | Xác suất collision tăng; có chính sách giới hạn, quản lý uniqueness và rotate. |
| Tạo `Cipher` mới rồi nghĩ provider tự biết nonce đã sử dụng | Provider không quản lý nonce toàn hệ thống; ứng dụng phải quản lý. |
| Làm mất nonce khi lưu ciphertext | Không thể giải mã đúng bản ghi; lưu nonce công khai cùng ciphertext+tag. |
| Giải mã với AAD khác | Tag verification thất bại; lưu/tính AAD đúng protocol. |
| Bỏ qua `AEADBadTagException` rồi dùng plaintext chưa xác minh | Mất bảo vệ integrity; từ chối toàn bộ bản tin xác thực thất bại. |
| Tưởng AEAD chống phát lại | Gói cũ vẫn có thể hợp lệ; giao thức cần anti-replay riêng. |
| Hardcode key trong demo rồi deploy production | Rò key, tất cả thiết bị dùng chung key; sinh và quản lý key bằng KMS/secret management. |

## 10. Câu hỏi tự kiểm tra

**Câu 1:** Key ChaCha20 có 256 bit, nonce có 96 bit. Hai bản tin dùng cùng key và nonce nhưng khác plaintext thì có vấn đề gì?

**Đáp án:** Với các vùng counter trùng, keystream trùng nên `C1 XOR C2 = P1 XOR P2`, làm lộ quan hệ plaintext. Với ChaCha20-Poly1305, còn tái sử dụng khóa Poly1305 dùng một lần, đe dọa bảo đảm xác thực.

**Câu 2:** Gọi `new ChaCha20ParameterSpec(nonce, counter+1)` cho bản tin thứ hai có thay cho nonce mới không?

**Đáp án:** Không. Counter là **block counter** và các vùng có thể chồng lấn; AEAD còn dùng nonce để tạo Poly1305 key. Cần nonce mới theo chính sách.

**Câu 3:** Vì sao dùng lại nonce để **giải mã chính ciphertext cũ** là đúng?

**Đáp án:** Decryption cần chính key, nonce và AAD đã dùng khi encrypt để xác minh tag. Điều cấm là reuse nonce cho **phép mã hóa mới** dưới cùng key.

**Câu 4:** Nếu ứng dụng restart mà vẫn giữ key cũ và đặt `seq=1` thì sao?

**Đáp án:** Nguy cơ nonce collision với các bản tin trước restart; cần lưu/đặt trước dải sequence một cách bền vững hoặc rotate sang key mới có vòng đời nonce riêng.

**Câu 5:** Nonce có cần giấu khỏi attacker không?

**Đáp án:** Không. Nonce có thể truyền/lưu cùng ciphertext, nhưng **phải duy nhất** theo key và được xác thực trong cấu trúc giao thức phù hợp.

**Câu 6:** Dùng `Cipher.getInstance("ChaCha20-Poly1305")` nên truyền `ChaCha20ParameterSpec` hay `IvParameterSpec`?

**Đáp án:** Với SunJCE Java 11+, dùng `new IvParameterSpec(nonce12)`. `ChaCha20ParameterSpec` dành cho raw ChaCha20.

**Câu 7:** Nếu sửa một byte tag của ChaCha20-Poly1305, caller cần làm gì?

**Đáp án:** Từ chối bản tin khi `AEADBadTagException` xuất hiện, không dùng plaintext chưa được xác thực. Đồng thời ghi nhận lỗi/giới hạn thử lại phù hợp mà không log key/secret.

**Câu 8:** Hai key khác nhau có được dùng cùng một chuỗi nonce không?

**Đáp án:** Về nguyên tắc được: yêu cầu uniqueness đặt trên **từng key**, không phải toàn hệ thống. Nhưng phải chắc chắn hai key thực sự khác và không reuse nhầm key cũ sau rotate.

**Ghi nhớ:** **Mỗi lần encrypt mới với ChaCha20/ChaCha20-Poly1305 dưới cùng một key phải dùng một nonce 12 byte chưa từng sử dụng**. Nonce không bí mật; key mới là bí mật. Đừng lấy block counter, thread, process hoặc AAD làm cách thay thế uniqueness. Với Java 11+, raw ChaCha20 dùng `ChaCha20ParameterSpec`, còn AEAD dùng `IvParameterSpec` và phải kiểm tra tag. Ở production, ưu tiên nonce allocator có sequence bền vững, chống trùng giữa thread/node và qua restart, cộng chính sách rotate key, chống replay, không vượt giới hạn per-nonce.

**Nguồn chính thức:** [RFC 8439 — ChaCha20 and Poly1305 for IETF Protocols](https://www.rfc-editor.org/rfc/rfc8439), [Java SE 11 — ChaCha20ParameterSpec](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html), [Java SE 11 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/11/docs/specs/security/standard-names.html), [Java SE 11 — Cipher](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/Cipher.html), [Java SE 25 — ChaCha20ParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html).
