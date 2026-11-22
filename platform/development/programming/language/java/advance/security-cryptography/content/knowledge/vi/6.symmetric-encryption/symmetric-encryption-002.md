# 6.2 Chỉ định đầy đủ transformation thay vì phụ thuộc giá trị mặc định của provider

## 1. Vấn đề: `"AES"` chưa mô tả một phép mã hóa hoàn chỉnh

Trong Java Cryptography Architecture (JCA/JCE), lớp `javax.crypto.Cipher` là **API (engine)** dùng chung cho nhiều phép mã hóa. Khi gọi `Cipher.getInstance(...)`, ứng dụng yêu cầu một **transformation**: thuật toán được dùng cùng cách vận hành và xử lý dữ liệu.

Với block cipher phổ biến như AES, ba thành phần quan trọng là:

1. **Algorithm** — thuật toán nguyên thủy, ví dụ `AES` (khối 128 bit).
2. **Mode** — cách xử lý nhiều khối và sử dụng IV/nonce, ví dụ `ECB`, `CBC`, `GCM`, `CTR`.
3. **Padding** — cách xử lý phần dữ liệu không đủ một khối, ví dụ `PKCS5Padding` hoặc `NoPadding`.

Java `Cipher` chấp nhận cả `"algorithm/mode/padding"` lẫn `"algorithm"`:

```java
// Các dòng minh họa trong phương thức có xử lý checked exception:
Cipher ambiguous = Cipher.getInstance("AES");
Cipher explicit = Cipher.getInstance("AES/GCM/NoPadding");
```

Hai lời gọi **không tương đương**. `"AES"` chỉ nêu thuật toán; **provider quyết định mode và padding mặc định**. `"AES/GCM/NoPadding"` yêu cầu chính xác mode GCM và không dùng padding khối. Khi chạy trên JDK/provider khác hoặc sau khi đổi thứ tự provider, `"AES"` có thể không còn mang ý nghĩa như người viết từng giả định.

**Quy tắc nền tảng:** Đối với thuật toán có nhiều mode/padding, nêu rõ transformation phù hợp giao thức, ví dụ `Cipher.getInstance("AES/GCM/NoPadding")`, và cấu hình khóa, IV/nonce, tag, AAD một cách chủ ý. Chỉ viết đủ ba phần của tên chưa tự động làm toàn bộ hệ thống an toàn.

Một số cipher có tên hoàn chỉnh mà **không dùng ba phần**, ví dụ `ChaCha20-Poly1305`: dùng tên chuẩn của chính thuật toán đó, không tự thêm `/mode/padding` vô nghĩa. “Đầy đủ” nghĩa là không để lại **mặc định quan trọng chưa được đặc tả**, không phải máy móc đếm số dấu `/`.

## 2. Provider ảnh hưởng đến transformation thế nào?

### 2.1 Engine API và provider

`Cipher.getInstance(transformation)` nhờ JCA/JCE tìm provider đang đăng ký có thể cung cấp phép mã hóa phù hợp. Provider có thể đi cùng JDK (chẳng hạn `SunJCE` trong Oracle/OpenJDK), thuộc thư viện riêng, tích hợp hệ điều hành hoặc truy cập HSM.

```text
Ứng dụng: Cipher.getInstance("AES/GCM/NoPadding")
                           |
                           v
                Cipher engine của JCA
                           |
             tìm implementation phù hợp
                           |
            +--------------+--------------+
            |                             |
     Provider A hỗ trợ              Provider B không hỗ trợ
            |                             |
        AES-GCM SPI                    bỏ qua
```

Nếu ứng dụng chỉ yêu cầu `"AES"`, provider có thể áp dụng **mode/padding mặc định**; Java SE không quy định một cấu hình mặc định an toàn chung cho mọi provider.

Tài liệu **Oracle JDK 17 JDK Providers Documentation** nêu `SunJCE` và `SunPKCS11` mặc định **ECB** với **PKCS5Padding** cho nhiều symmetric cipher. Trong trường hợp `SunJCE`, tài liệu JCA cho ví dụ `Cipher.getInstance("AES")` tương đương `Cipher.getInstance("AES/ECB/PKCS5Padding")`. Đó là mô tả của provider/bản JDK tương ứng, **không phải hợp đồng bắt buộc với mọi JDK**.

ECB tiết lộ mẫu lặp của các khối dữ liệu cùng khóa; vì vậy việc vô tình nhận ECB từ `"AES"` có thể tạo lỗ hổng dù code biên dịch, chạy và giải mã được trên máy lập trình viên.

### 2.2 Đừng dựa vào `getAlgorithm()` để suy ra mode mặc định

```java
Cipher unspecified = Cipher.getInstance("AES");
String requested = unspecified.getAlgorithm(); // Tên đã yêu cầu: "AES"
```

`getAlgorithm()` cung cấp **tên đã yêu cầu**, không phải báo cáo chuẩn hóa rằng provider đã chọn chính xác những thông số ngầm định nào. `getProvider()` cho biết provider của đối tượng (và ở một số implementation có thể kích hoạt lựa chọn provider), nhưng **tên provider không thay cho transformation**. Cần đọc tài liệu provider và kiểm thử mode/tham số thật khi kiểm toán hệ thống kế thừa.

Khi dùng overload `Cipher.getInstance("AES/GCM/NoPadding", "SunJCE")`, ứng dụng phụ thuộc vào provider có tên đó và đã được đăng ký. Chỉ pin provider khi có yêu cầu rõ như HSM hoặc kiểm định, còn lại nên yêu cầu **transformation chuẩn xác** và để JCA tìm provider tương thích.

## 3. So sánh các yêu cầu Cipher thường gặp

| Transformation | Ý nghĩa đã xác định | Lưu ý về bảo mật và khả chuyển |
| --- | --- | --- |
| `"AES"` | Chỉ thuật toán AES | **Mơ hồ**: provider tự chọn mode/padding. Tránh dùng để mã hóa dữ liệu ứng dụng. |
| `"AES/ECB/PKCS5Padding"` | AES, ECB, padding tương thích JCE | Rõ ràng về mặt cú pháp nhưng **không phù hợp cho dữ liệu nhiều khối**, vì ECB làm lộ quan hệ khối lặp. |
| `"AES/CBC/PKCS5Padding"` | AES, CBC, padding được nêu | Cần IV hợp lệ và **xác thực/toàn vẹn riêng**. CBC không tự phát hiện dữ liệu bị chỉnh sửa có chủ đích. |
| `"AES/GCM/NoPadding"` | AES, GCM, không có block padding | AEAD hỗ trợ mã hóa + tag xác thực và AAD. Cần nonce **duy nhất với mỗi khóa**. |
| `"AES/CTR/NoPadding"` | AES, counter mode, không padding | Cần counter/nonce đúng và **MAC hoặc cơ chế xác thực riêng** nếu cần chống chỉnh sửa. |
| `"AES/CFB/NoPadding"` | AES, CFB, không padding | Kích thước **feedback segment** có thể do provider quyết định; dùng ví dụ `AES/CFB8/NoPadding` nếu giao thức bắt buộc CFB8 và provider hỗ trợ. |

### 3.1 Rõ ràng chưa chắc an toàn

Thay `"AES"` bằng `"AES/ECB/PKCS5Padding"` chỉ giúp biết chắc mode/padding đang dùng, nhưng không chữa nguy cơ của ECB. Với hai block plaintext giống nhau, ECB và cùng khóa tạo hai block ciphertext giống nhau:

```text
      plaintext block P             plaintext block P
              |                             |
            AES(K)                        AES(K)
              |                             |
      ciphertext block C            ciphertext block C
```

CBC xóa bớt đặc điểm đó bằng chaining và IV, nhưng CBC **không cung cấp authentication tag**. Trường hợp thiết kế mới cần cả bí mật và toàn vẹn thường phù hợp hơn với AEAD như GCM.

`PKCS5Padding` là tên chuẩn dùng trong nhiều provider JCE cả với block AES 128 bit; không suy luận từ chữ “5” rằng AES chỉ có block 8 byte. `NoPadding` đối với GCM không có nghĩa “không xác thực”, cũng không yêu cầu plaintext phải chia hết cho 16 byte: `Cipher.doFinal` của GCM trả ciphertext **kèm tag**.

## 4. Full transformation còn cần tham số đầy đủ

`Cipher.getInstance("AES/GCM/NoPadding")` đã cố định mode/padding, nhưng một **bản ghi mã hóa có thể tương tác** còn phải quy định:

| Thành phần | Ví dụ nhất quán | Quy tắc quan trọng |
| --- | --- | --- |
| Transformation | `AES/GCM/NoPadding` | Không lấy mode/padding mặc định của provider. |
| Kích thước khóa | AES-128, khóa 16 byte | `KeyGenerator.getInstance("AES")` dùng tên ở engine **KeyGenerator**; không phải yêu cầu `Cipher` mode mặc định. |
| Nonce/IV | 12 byte | Phải **không lặp lại với cùng một key GCM**; lưu/truyền cùng dữ liệu mã hóa. |
| Tag length | 128 bit | `new GCMParameterSpec(128, nonce)` dùng đơn vị **bit**. |
| AAD | Byte như `"record:v1"` | Metadata xác thực nhưng không mã hóa. Phải trùng nguyên byte khi giải mã. |
| Output format | `ciphertext || authentication tag` | Theo API `Cipher` GCM, tag được nối vào ciphertext khi mã hóa và kiểm tra khi giải mã. |
| Encoding/layout | UTF-8 + binary format có version/length | Người đọc phải tái lập cùng byte, không đoán từ giá trị mặc định của hệ điều hành. |

**Bốn điểm rất dễ thiếu khi viết code:**

1. `getInstance` mới chỉ có cipher engine. Gọi `init` với key và tham số đúng trước khi dùng `doFinal`; `getInstance` thành công không chứng minh key/IV/tag hợp lệ.
2. Trong một số mode, `init(ENCRYPT_MODE, key)` có thể làm provider tự sinh IV. Không lưu/truyền lại IV sẽ khiến dữ liệu khó hoặc không thể giải mã sau đó. Với GCM, nên có chiến lược sinh nonce của ứng dụng và truyền `GCMParameterSpec` rõ ràng.
3. `updateAAD` của GCM phải gọi **trước** `update`/`doFinal`. Bên nhận xác thực bằng chính xác cùng AAD bytes; nếu tag sai (`AEADBadTagException`), từ chối toàn bộ bản ghi.
4. Nonce GCM cần duy nhất theo mỗi khóa. Sinh nonce ngẫu nhiên 96 bit có xác suất va chạm khi số lượng bản ghi đủ lớn; hệ thống nhiều writer hoặc high-volume cần giới hạn sử dụng khóa, quy trình phối hợp/tách khóa hoặc cơ chế uniqueness có kiểm soát, không mặc định `SecureRandom` loại bỏ được mọi va chạm.

## 5. Ví dụ Java 17+: mã hóa GCM rõ ràng và kiểm tra toàn vẹn

Tạo file **`ExplicitTransformationDemo.java`**. Chương trình sử dụng AES-128-GCM, nonce 12 byte, tag 128 bit, AAD và kiểm thử hai trường hợp bị sửa. Đây là **chương trình độc lập**, khác với các đoạn minh họa ngắn ở trên.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class ExplicitTransformationDemo {
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int TAG_BITS = 128;
    private static final int NONCE_BYTES = 12;
    private static final SecureRandom RNG = new SecureRandom();

    private static byte[] encrypt(SecretKey key, byte[] nonce,
                                  byte[] aad, byte[] plaintext)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(plaintext);
    }

    private static byte[] decrypt(SecretKey key, byte[] nonce,
                                  byte[] aad, byte[] ciphertextAndTag)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertextAndTag);
    }

    private static boolean rejected(SecretKey key, byte[] nonce,
                                    byte[] aad, byte[] ciphertextAndTag)
            throws GeneralSecurityException {
        try {
            decrypt(key, nonce, aad, ciphertextAndTag);
            return false;
        } catch (AEADBadTagException badTag) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);
        byte[] aad = "record:v1".getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Hello AES-GCM".getBytes(StandardCharsets.UTF_8);

        Cipher chosen = Cipher.getInstance(TRANSFORMATION);
        System.out.println("Transformation: " + chosen.getAlgorithm());

        byte[] ciphertextAndTag = encrypt(key, nonce, aad, plaintext);
        byte[] recovered = decrypt(key, nonce, aad, ciphertextAndTag);
        System.out.println("Round-trip: " + Arrays.equals(plaintext, recovered));
        System.out.println("Ciphertext+tag bytes: " + ciphertextAndTag.length);

        byte[] changedBody = ciphertextAndTag.clone();
        changedBody[0] ^= 1;
        System.out.println("Tampered body rejected: " +
                rejected(key, nonce, aad, changedBody));

        byte[] changedAad = aad.clone();
        changedAad[0] ^= 1;
        System.out.println("Tampered AAD rejected: " +
                rejected(key, nonce, changedAad, ciphertextAndTag));
    }
}
```

Dùng JDK 17 trở lên:

```bash
javac --release 17 ExplicitTransformationDemo.java
java ExplicitTransformationDemo
```

**Stdout** (các byte khóa/nonce là ngẫu nhiên nhưng các dòng sau ổn định):

```text
Transformation: AES/GCM/NoPadding
Round-trip: true
Ciphertext+tag bytes: 29
Tampered body rejected: true
Tampered AAD rejected: true
```

Giải thích:

- `KeyGenerator.getInstance("AES")` ở đây chỉ chọn **loại khóa**, sau đó `generator.init(128)` xác định 128 bit. Không có lý do thêm `/GCM/NoPadding` vào tên thuật toán của **KeyGenerator**; cú pháp ba phần thuộc yêu cầu Cipher.
- `"Hello AES-GCM"` là 13 byte UTF-8. Với tag GCM 128 bit (16 byte), `doFinal` khi mã hóa trả **13 + 16 = 29 byte**.
- Cả `encrypt` và `decrypt` đều yêu cầu chính xác `AES/GCM/NoPadding`, sử dụng cùng key, nonce, AAD nên dữ liệu phục hồi trùng từng byte.
- Thay 1 byte ciphertext hoặc AAD khiến authentication tag không hợp lệ, nên `rejected(...)` trả `true`. Đừng bỏ qua hoặc cố bắt lỗi tag rồi đưa plaintext chưa xác thực vào nghiệp vụ.
- Mỗi phương thức tạo `Cipher` mới cho một lượt thao tác. Nếu tái sử dụng key cho bản ghi tiếp theo, phải sử dụng **nonce khác** và quy định số lần mã hóa tối đa theo thiết kế bảo mật.

**Đây là ví dụ in-memory:** khóa được sinh mới mỗi lần chạy; để đọc lại dữ liệu đã lưu qua restart, ứng dụng phải quản lý khóa trong KMS/HSM/keystore và gắn metadata như `version`, `suite ID`, `key ID`, nonce và ciphertext/tag vào format được đặc tả. **Không lưu raw secret key cạnh ciphertext.** Nếu cần chống đưa ciphertext sang ngữ cảnh khác, ràng buộc tenant/object/purpose vào AAD; nếu cần chống replay thì phải có thêm cơ chế trạng thái/sequence number ngoài authentication tag.

## 6. Cách chọn và duy trì transformation trong dự án

### 6.1 Khi viết code mới

- Xuất phát từ yêu cầu: cần cả bí mật và toàn vẹn thì ưu tiên một **AEAD** phù hợp, ví dụ AES-GCM.
- Chọn **tên chuẩn và cấu hình** của từng engine: `Cipher.getInstance("AES/GCM/NoPadding")`, khóa AES-128/256 theo chính sách, nonce 96 bit và tag 128 bit nếu giao thức yêu cầu các mức này.
- Định nghĩa **định dạng dữ liệu** với version/suite/IV/tag và encoding rõ ràng; chỉ dùng tên mà cả bên mã hóa lẫn giải mã cùng biết.
- Đặt kiểm tra khả dụng vào kiểm thử triển khai hoặc startup. Thử khởi tạo với khóa và tham số thực, rồi round-trip và tamper test; không dừng ở `Cipher.getInstance(...)`.
- Không cứng tên provider trong code trừ khi chính sách hoặc phần cứng bắt buộc; nếu pin phải tài liệu hóa dependency và kiểm tra trên runtime đích.

### 6.2 Khi sửa ứng dụng cũ đang dùng `"AES"`

Phải **xác định format hiện tại trước khi đổi code**. Không thể thay toàn bộ `Cipher.getInstance("AES")` bằng GCM rồi kỳ vọng giải mã tự động các bản ghi vốn được mã hóa với ECB/CBC và padding khác.

Quy trình an toàn:

1. Xác định provider/JDK lúc mã hóa cũ, mode, padding, khóa, IV/nonce và cách ghi ciphertext; sử dụng fixture hoặc dữ liệu kiểm thử có kiểm soát để xác nhận. Không dùng `getAlgorithm()` làm bằng chứng đủ.
2. Định nghĩa **reader phiên bản cũ** chỉ khi thực sự cần tương thích, giới hạn phạm vi và cơ chế lỗi; không thử lần lượt các mode ngẫu nhiên cho đến khi giải được.
3. Định nghĩa **writer mới** có transformation, key strategy và version/suite rõ ràng; ưu tiên AEAD.
4. Nếu cần di trú dữ liệu cũ, đọc bằng reader được phép, kiểm tra toàn vẹn nếu format cũ có cơ chế đó, rồi ghi bản mới bằng nonce/key phù hợp. Ghi nhận hạn chế xác thực của dữ liệu legacy.
5. Không tiếp tục phát sinh bản ghi mới với cấu hình mặc định; lên kế hoạch loại bỏ reader cũ khi đã hoàn tất di trú.

### 6.3 Mức hỗ trợ Java SE và provider

Java SE nêu **tên thuật toán chuẩn** và một tập con **bắt buộc implementation hỗ trợ**. Tên xuất hiện trong *Standard Algorithm Names* không tự động có nghĩa mọi runtime đều có implementation. Java SE 17 có mức yêu cầu tối thiểu liên quan AES-GCM với khóa AES 128 bit; đối với thuật toán hoặc key-size khác, kiểm tra đặc tả đúng phiên bản cùng provider mục tiêu.

Những điều có thể thay đổi giữa runtime là provider, availability, giới hạn key/parameter, tăng tốc phần cứng và chi tiết cấu hình. Tên transformation rõ ràng giảm mơ hồ về phép mã hóa, nhưng vẫn cần **test interoperability** nếu một phía ghi bằng provider A và phía kia đọc bằng provider B.

## 7. Chẩn đoán lỗi theo đúng lớp vấn đề

| Ngoại lệ/triệu chứng | Thường xuất hiện ở đâu? | Cách suy luận và xử lý |
| --- | --- | --- |
| `NoSuchAlgorithmException` | `Cipher.getInstance` | Thuật toán/transformation không được provider/runtime phân giải; kiểm tra spelling, tên chuẩn và provider đã đăng ký. |
| `NoSuchPaddingException` | `Cipher.getInstance` | Padding được yêu cầu không được hỗ trợ cho transformation/provider đó. Ví dụ `AES/GCM/PKCS5Padding` không phải tên GCM thích hợp. |
| `NoSuchProviderException` | Overload có tên provider | Tên provider không có trong registry; cần cài/đăng ký provider hoặc bỏ ràng buộc nếu không cần. |
| `InvalidKeyException` | `Cipher.init` | Kiểu/kích thước/thuộc tính khóa không phù hợp hoặc bị chính sách hạn chế. |
| `InvalidAlgorithmParameterException` | `Cipher.init` | IV/nonce/tag/algorithm parameters không được chấp nhận. |
| `AEADBadTagException` | `Cipher.doFinal` giải mã AEAD | Dữ liệu, khóa, nonce hoặc AAD không đúng; **từ chối**, không trả plaintext và không đổi mode để thử lại. |
| `BadPaddingException` (CBC) | `Cipher.doFinal` | Khóa/IV/ciphertext/padding có thể sai. Padding **không phải kiểm tra toàn vẹn** và không nên làm lộ chi tiết cho bên không tin cậy. |

**Không fallback kiểu “GCM không có thì thử `AES`”.** Vì `"AES"` có mode mặc định không xác định bởi ứng dụng, fallback có thể âm thầm chuyển sang ECB. Khi runtime không đáp ứng một suite được thiết kế, báo lỗi rõ hoặc chọn một suite thay thế **đã phê duyệt trong giao thức**, với phiên bản/ID riêng và quy tắc tương thích được định nghĩa trước.

## 8. Những lỗi review mã hay bỏ sót

1. **Chọn algorithm-only:** `Cipher.getInstance("AES")` để mode/padding tùy provider.
2. **Khắc phục nửa vời:** thay thành `AES/ECB/PKCS5Padding` để “ổn định” nhưng vẫn lộ mẫu dữ liệu nhiều khối.
3. **Dùng CBC mà không có MAC:** dữ liệu có thể bị chỉnh sửa và sinh lỗi padding; không có authenticity của AEAD.
4. **Không lưu IV:** có ciphertext nhưng thiếu nonce/IV để giải mã; ngược lại, IV có thể công khai và phải được lưu đúng cách.
5. **Tái dùng nonce GCM cùng khóa:** vi phạm điều kiện bảo mật, có thể dẫn đến tấn công giả mạo/tiết lộ dữ liệu.
6. **Nhầm `NoPadding` là “không có tag”:** GCM vẫn xác thực và trả tag; plaintext dài 13 byte hoàn toàn hợp lệ.
7. **Dùng `updateAAD` sau `update`:** trái với yêu cầu AEAD của API Cipher.
8. **Kết luận mode từ `getAlgorithm()` hoặc tên provider:** hai thông tin này không phải đặc tả đầy đủ của mode/padding ngầm định.
9. **Chỉ test `getInstance`:** không test `init`, `doFinal`, tag, nonce, key size và khả năng đọc từ môi trường khác.
10. **Đổi mode trong code nhưng không version hóa ciphertext:** bản ghi cũ không còn giải mã theo writer mới.
11. **Lấy transformation từ file/request chưa xác thực:** cho đầu vào quyết định phép mã hóa; chỉ dùng allowlist suite cố định.
12. **In key/nonce/cleartext nhạy cảm ra log:** ví dụ học tập không nên trở thành luồng log trong production. Nonce không bí mật nhưng vẫn cần bảo toàn và đúng ngữ cảnh.

## 9. Checklist tự kiểm tra

- [ ] Tất cả `Cipher.getInstance` cho dữ liệu lưu/truyền đều nêu transformation chuẩn, đủ chính xác theo giao thức.
- [ ] Transformation được **chọn vì tính an toàn**, không chỉ vì có thể gọi được trên JDK đang dùng.
- [ ] Cỡ khóa, IV/nonce, tag, AAD, padding/feedback parameters được quy định rõ và test với provider đích.
- [ ] Nonce của GCM duy nhất theo từng khóa; khóa được quản lý riêng, có kế hoạch luân chuyển và giới hạn số lần dùng.
- [ ] Không trả plaintext chưa được xác thực; tampering và sai AAD bị từ chối.
- [ ] Dữ liệu có version/suite/nonce/encoding, giải mã không lệ thuộc mode/padding mặc định.
- [ ] Không fallback tự động sang ECB/CBC khi suite yêu cầu bị thiếu; xử lý lỗi theo hợp đồng bảo mật.
- [ ] Có kiểm thử cross-provider/JDK và trường hợp legacy khi cần di trú.

**Tự đánh giá:**

- `Cipher.getInstance("AES")` có mặc định GCM ở mọi JDK? **Không.**
- `AES/ECB/PKCS5Padding` có là transformation đầy đủ? **Có**, nhưng không có nghĩa an toàn cho dữ liệu nhiều khối.
- `AES/GCM/NoPadding` đã bao gồm việc sinh và lưu nonce đúng cách? **Chưa.** Code và định dạng dữ liệu chịu trách nhiệm.
- Hai phía dùng cùng transformation nhưng khác AAD có giải mã GCM thành công? **Không** khi AAD được xác thực đúng.
- `KeyGenerator.getInstance("AES")` có cùng kiểu mơ hồ với `Cipher.getInstance("AES")`? **Không**: `KeyGenerator` là engine sinh khóa, không có mode/padding.

## Tài liệu tham khảo

- [Java SE 17 — `javax.crypto.Cipher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): cú pháp transformation, mặc định provider, AEAD, thứ tự `updateAAD`, nonce GCM và exceptions.
- [Oracle JDK 17 — JDK Providers Documentation](https://docs.oracle.com/en/java/javase/17/security/oracle-providers.html): phần **Cipher Transformations**, ví dụ `SunJCE`/`SunPKCS11` và khả năng provider.
- [Java SE 17 — Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): engine API, SPI/provider, mode và padding.
- [Java SE 17 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): tên chuẩn và yêu cầu triển khai tối thiểu.
- [Java SE 17 — `GCMParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): `tLen` tính bằng bit, IV/nonce.
- [RFC 5116 — Authenticated Encryption with Associated Data](https://www.rfc-editor.org/rfc/rfc5116): cách hiểu nonce, AAD và AEAD.

**Kết luận học tập:** Yêu cầu `Cipher.getInstance("AES")` gửi một quyết định quan trọng cho provider. Yêu cầu `Cipher.getInstance("AES/GCM/NoPadding")` đặt lại quyết định đó trong mã nguồn và giao thức, sau đó phải hoàn thiện đúng key, nonce, AAD, tag, lưu trữ và kiểm thử.
