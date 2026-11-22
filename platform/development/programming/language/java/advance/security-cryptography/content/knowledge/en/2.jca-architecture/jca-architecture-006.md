# 2.6. AlgorithmParameterSpec, AlgorithmParameters và việc lưu tham số thuật toán trong JCA

## 1. Bài toán: khóa và tham số thuật toán là hai phần khác nhau

Trong Java Cryptography Architecture (JCA), **khóa** là vật liệu mật mã dùng cho phép mã hóa, giải mã, ký hoặc xác minh; **tham số thuật toán** xác định cách một thuật toán vận hành trong một lần sử dụng cụ thể. Có đúng khóa mà thiếu tham số cần thiết vẫn có thể không giải mã hoặc xác minh được dữ liệu.

Các trường hợp tiêu biểu:

- **AES-GCM:** cần khóa, nonce/IV và độ dài authentication tag. Nonce không phải khóa, nhưng *không được trùng giữa hai lần mã hóa dùng cùng khóa*.
- **AES-CBC:** cần IV bên cạnh khóa. IV có thể công khai nhưng CBC tự nó không đảm bảo tính toàn vẹn.
- **Password-based encryption (PBE):** cần salt và số vòng lặp, đôi khi cả tham số thuật toán bên trong; không nhầm những giá trị này với mật khẩu.
- **RSA-PSS:** bên ký và bên xác minh cần thống nhất digest, mask generation function, độ dài salt và trailer field.
- **RSA-OAEP:** có lựa chọn digest, MGF và nguồn dữ liệu nhãn (label).

Khi thiết kế lưu trữ bản mã, phải xác định **những gì cần lưu để khôi phục đúng phép toán**: tên thuật toán/mode, tham số, ciphertext/tag, tham chiếu tới khóa và AAD nếu có. Không nên coi tất cả các giá trị đó là “khóa”, cũng không nên giả định provider tự tái tạo được tham số của một lần mã hóa đã qua.

## 2. Phân biệt các đối tượng trong JCA

| API | Bản chất | Dùng để làm gì |
| --- | --- | --- |
| `java.security.spec.AlgorithmParameterSpec` | Marker interface, không tự định nghĩa phương thức encode | Đại diện **có kiểu** cho các trường tham số mà engine có thể nhận. |
| `java.security.AlgorithmParameters` | Đối tượng JCA dựa trên implementation của security provider | Giữ tham số của một thuật toán; chuyển đổi giữa spec và byte encoding, đọc metadata thuật toán/provider. |
| `java.security.AlgorithmParameterGenerator` | Engine JCA có provider | Sinh các tham số theo khả năng của thuật toán/provider; không phải đối tượng dùng để giải mã một blob đã lưu. |
| `java.security.Key`, `SecretKey`, `PrivateKey` | Vật liệu khóa | Thực hiện phép mật mã, phải được quản lý theo chính sách khóa. |

`AlgorithmParameterSpec` là một cách biểu diễn *transparent*: ứng dụng truy cập các trường được lớp cụ thể công bố. Ví dụ `GCMParameterSpec.getIV()` trả IV và `getTLen()` trả độ dài tag **tính bằng bit**. `IvParameterSpec` chỉ mô tả IV, không chứa độ dài tag; `PSSParameterSpec` lại có các trường hoàn toàn khác. Bản thân interface `AlgorithmParameterSpec` **không có** `getEncoded()`.

`AlgorithmParameters` là biểu diễn *opaque* theo nghĩa ứng dụng gọi API chung và giao việc diễn giải cho provider. Những phương thức quan trọng:

- `AlgorithmParameters.getInstance("GCM")`: yêu cầu đối tượng cho tên thuật toán tham số `GCM`; JCA chọn provider hỗ trợ.
- `init(AlgorithmParameterSpec)`: khởi tạo từ một spec có kiểu.
- `init(byte[])` hoặc `init(byte[], String format)`: nhập byte encoding và giải mã theo format tương ứng.
- `getParameterSpec(GCMParameterSpec.class)`: trích xuất một spec có kiểu phù hợp.
- `getEncoded()` hoặc `getEncoded(String format)`: mã hóa tham số thành byte theo format chính hoặc format được hỗ trợ.
- `getAlgorithm()` và `getProvider()`: xem thuật toán tham số và provider đang dùng.

Một `AlgorithmParameters` mới chỉ được `init(...)` **một lần**. Muốn giải mã một bộ tham số khác, tạo instance mới. Không phải mọi loại spec đều có implementation `AlgorithmParameters` tương ứng ở mọi provider.

### Liên hệ với kiến trúc provider và engine

`Cipher`, `Signature`, `KeyPairGenerator`, `AlgorithmParameters` là các API/engine JCA; lớp SPI phía dưới do provider triển khai. Lựa chọn thuật toán/provider quyết định loại spec và encoding nào được chấp nhận.

- `Cipher.init(mode, key, AlgorithmParameterSpec)` phù hợp khi ứng dụng đã có spec có kiểu.
- `Cipher.init(mode, key, AlgorithmParameters)` phù hợp khi đã có đối tượng tham số.
- `Cipher.getParameters()` lấy tham số thực tế mà cipher dùng sau khi khởi tạo; có thể chứa giá trị mà provider tự sinh. Nếu cipher không dùng tham số, phương thức có thể trả `null`.
- `Signature.setParameter(PSSParameterSpec)` cấu hình tham số chữ ký RSA-PSS; không dùng `Cipher` để ký.
- `"AES/GCM/NoPadding"` là **Cipher transformation**, còn `"GCM"` là tên thuật toán tham số trong ví dụ. Không đưa nguyên transformation vào `AlgorithmParameters.getInstance` mà không kiểm tra hỗ trợ.

## 3. Chọn đúng lớp AlgorithmParameterSpec

| Spec | Các trường đặc trưng | Bối cảnh |
| --- | --- | --- |
| `GCMParameterSpec(tagBits, iv)` | Tag length (bit), IV/nonce (byte) | AES-GCM, ví dụ tag 128 bit và nonce 12 byte. |
| `IvParameterSpec(iv)` | IV | AES-CBC/CTR khi mode/provider yêu cầu; không diễn tả riêng độ dài tag GCM. |
| `PBEParameterSpec(salt, iterations)` | Salt, iteration count; có constructor nhận nested spec | PBE; không phải nơi lưu mật khẩu. |
| `PSSParameterSpec(...)` | Digest, MGF, MGF parameters, salt length, trailer field | RSA-PSS. |
| `OAEPParameterSpec(...)` | Digest, MGF, label source | RSA-OAEP. |
| `ECGenParameterSpec(curveName)` | Tên đường cong | Khởi tạo bộ sinh khóa EC. |

Cần phân biệt `PBEKeySpec` (thuộc họ `KeySpec`, phục vụ biểu diễn vật liệu để dẫn xuất khóa bằng `SecretKeyFactory`) với `PBEParameterSpec` (thuộc họ `AlgorithmParameterSpec`). Việc lưu salt và iteration count **không đồng nghĩa** với việc lưu mật khẩu hay khóa đã dẫn xuất.

Với AES-GCM, `new GCMParameterSpec(128, iv)` chứa IV và tag length; giá trị 128 là **bit**, tương ứng 16 byte tag. IV 12 byte tương ứng 96 bit, là kích thước thường dùng. `getIV()` trả mảng sao chép; tuy vậy ứng dụng vẫn phải kiểm soát nguồn sinh và uniqueness của IV.

## 4. Vòng đời tham số: tạo, dùng, encode, lưu và khôi phục

```text
MÃ HÓA
  key (bí mật) + nonce mới + tagBits
                  |
                  v
            GCMParameterSpec
                  |
                  v
      Cipher.init(ENCRYPT_MODE, key, spec)
                  |
      updateAAD(aad) -> doFinal(plaintext)
                  |
                  +--------> ciphertext || authentication tag
                  |
            getParameters()
                  |
                  v
           AlgorithmParameters
                  |
             getEncoded()
                  |
                  +--------> encodedParams để lưu

GIẢI MÃ
  encodedParams -> AlgorithmParameters.getInstance("GCM")
                  -> init(encodedParams)
                  -> Cipher.init(DECRYPT_MODE, key, parameters)
                  -> updateAAD(cùng aad)
  ciphertext || tag -> doFinal(...) -> plaintext hoặc lỗi xác thực
```

Có hai chiến lược lưu:

1. **Định dạng tường minh:** lưu riêng `iv` và `tagBits` cùng bản mã. Khi đọc, dựng lại `GCMParameterSpec(tagBits, iv)`. Cách này dễ xác định giao thức lưu trữ và chia sẻ với hệ thống không dùng Java.
2. **Encoding của `AlgorithmParameters`:** lưu `parameters.getEncoded()` và khôi phục bằng `parameters.init(encodedBytes)`. Cách này tiện trong hệ sinh thái provider tương thích, nhưng cần kiểm thử format/phiên bản khi muốn trao đổi giữa nhiều implementation.

**Tuyệt đối không dùng `toString()` của `AlgorithmParameters` hoặc spec làm dữ liệu lưu trữ.** Nó không có cam kết parse ngược. Cũng không nên dùng Java object serialization thay cho một giao thức lưu trữ có version và schema rõ ràng.

## 5. Ví dụ hoàn chỉnh Java 17+: AES-GCM round-trip với AlgorithmParameters

Ví dụ dưới đây dùng JDK có provider hỗ trợ `AES/GCM/NoPadding` và `AlgorithmParameters` tên `GCM` (như SunJCE của JDK phổ biến). Chương trình tạo key AES trong bộ nhớ, nonce mới, mã hóa có AAD, encode tham số, tạo đối tượng khác để decode và giải mã. Sau đó thay AAD để kiểm tra xác thực.

Tạo tệp `GcmParametersRoundTrip.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.AlgorithmParameters;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class GcmParametersRoundTrip {
    public static void main(String[] args) throws Exception {
        // Sinh key demo. Hệ thống thật phải quản lý key riêng.
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        byte[] aad = "document:v1".getBytes(StandardCharsets.UTF_8);
        byte[] input = "Ma hoa va giai ma JCA".getBytes(StandardCharsets.UTF_8);

        Cipher encryption = Cipher.getInstance("AES/GCM/NoPadding");
        encryption.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, nonce));
        encryption.updateAAD(aad);
        byte[] ciphertextAndTag = encryption.doFinal(input);

        AlgorithmParameters used = encryption.getParameters();
        byte[] serializedParams = used.getEncoded();

        AlgorithmParameters restored = AlgorithmParameters.getInstance("GCM");
        restored.init(serializedParams);
        GCMParameterSpec restoredSpec =
                restored.getParameterSpec(GCMParameterSpec.class);

        Cipher decryption = Cipher.getInstance("AES/GCM/NoPadding");
        decryption.init(Cipher.DECRYPT_MODE, key, restored);
        decryption.updateAAD(aad);
        byte[] output = decryption.doFinal(ciphertextAndTag);

        System.out.println("Nonce length: " + restoredSpec.getIV().length);
        System.out.println("Tag bits: " + restoredSpec.getTLen());
        System.out.println("Plaintext matches: " + Arrays.equals(input, output));
        System.out.println("Text: " + new String(output, StandardCharsets.UTF_8));

        try {
            Cipher bad = Cipher.getInstance("AES/GCM/NoPadding");
            bad.init(Cipher.DECRYPT_MODE, key, restoredSpec);
            bad.updateAAD("document:v2".getBytes(StandardCharsets.UTF_8));
            bad.doFinal(ciphertextAndTag);
            System.out.println("Tamper detected: false");
        } catch (AEADBadTagException expected) {
            System.out.println("Tamper detected: true");
        }
    }
}
```

Chạy:

```bash
javac GcmParametersRoundTrip.java
java GcmParametersRoundTrip
```

Stdout (key, nonce, ciphertext ngẫu nhiên nhưng các dòng hiển thị này ổn định):

```text
Nonce length: 12
Tag bits: 128
Plaintext matches: true
Text: Ma hoa va giai ma JCA
Tamper detected: true
```

**Giải thích:**

- `encryption.getParameters()` lấy tham số mà cipher thực dùng; `used.getEncoded()` trả byte **tham số**, không phải byte của key hay bản mã.
- `restored.init(serializedParams)` diễn giải dữ liệu đã encode. `getParameterSpec(GCMParameterSpec.class)` trích xuất lại IV và tag length để kiểm tra.
- `decryption.init(..., key, restored)` cho thấy có thể truyền trực tiếp `AlgorithmParameters` vào `Cipher`, không buộc phải dựng lại spec.
- `updateAAD` phải xảy ra trước xử lý bản mã trong GCM; cùng key, IV, ciphertext/tag **và đúng byte AAD** thì mới xác thực thành công.
- `Cipher.doFinal` ở chế độ mã hóa GCM trả ciphertext kèm authentication tag. Khi lưu phải giữ **trọn vẹn** mảng `ciphertextAndTag`.
- Khi AAD đổi, `doFinal` ném `AEADBadTagException`. Trong ứng dụng thật, phải từ chối dữ liệu và không trả plaintext chưa xác thực.

Demo chỉ giữ key trong process hiện tại. Nó **không chứng minh** có thể giải mã sau khi chương trình kết thúc mà không lưu/truy xuất key riêng. Dù `serializedParams` được lưu thành công, việc mất key vẫn khiến bản mã không thể giải mã.

### Lưu thật vào file hoặc cơ sở dữ liệu

Đoạn dưới là **mảnh mã bổ sung**, dùng sau khi đã có `serializedParams` và `ciphertextAndTag` từ chương trình trên; thêm imports `java.nio.file.Files` và `java.nio.file.Path`:

```java
Files.write(Path.of("gcm-parameters.bin"), serializedParams);
Files.write(Path.of("gcm-ciphertext.bin"), ciphertextAndTag);

// Trong quy trình đọc lại:
byte[] paramsBytes = Files.readAllBytes(Path.of("gcm-parameters.bin"));
byte[] encryptedBytes = Files.readAllBytes(Path.of("gcm-ciphertext.bin"));
AlgorithmParameters fromFile = AlgorithmParameters.getInstance("GCM");
fromFile.init(paramsBytes);
// Dùng key và AAD phù hợp rồi giải mã encryptedBytes.
```

Tệp tham số **không phải** tệp key. Với production, nên gói metadata, độ dài trường, ciphertext/tag và version thành một record có schema rõ ràng thay vì dựa vào hai tên tệp cố định. Đảm bảo key lấy từ keystore/KMS hoặc cơ chế quản lý khóa an toàn.

## 6. Thiết kế định dạng lưu trữ có version, tính tương thích và AAD

Một bản ghi mã hóa cần mô tả chính xác cách giải mã mà không làm lộ vật liệu khóa. Các trường nên cân nhắc:

| Trường | Ý nghĩa |
| --- | --- |
| `version` | Phiên bản schema lưu trữ; tránh đoán format trong tương lai. |
| `transformation` | Ví dụ `AES/GCM/NoPadding`, xác định algorithm/mode/padding. |
| `keyId` | Tham chiếu tới khóa hợp lệ trong keystore/KMS; không chứa khóa bí mật. |
| `iv` + `tagBits` **hoặc** `parameterAlgorithm` + `parameterEncoding` + `parameterBytes` | Một cách lưu tường minh hoặc một cách lưu qua `AlgorithmParameters`; ghi rõ format và độ dài. |
| `ciphertextAndTag` | Trọn vẹn bản mã kèm tag của GCM. |
| `aad` hoặc quy tắc tái tạo AAD | Phải giữ đúng **từng byte** cho phía giải mã. |

Nếu metadata như tenant, documentId, version hay keyId ảnh hưởng đến quyền truy cập hoặc cách diễn giải dữ liệu, nên **ràng buộc chúng bằng AAD** hoặc cơ chế toàn vẹn thích hợp. Không nhận lựa chọn thuật toán yếu từ metadata chưa được xác thực. Phía đọc cần giới hạn kích thước, kiểm tra thuật toán cho phép, tagBits, IV length và version trước khi dùng.

Trong JSON, có thể biểu diễn byte bằng Base64, nhưng **Base64 không mã hóa bí mật hay xác thực dữ liệu**. Định dạng nhị phân cần có độ dài các trường rõ ràng; khi đọc không được mặc định rằng các trường byte có chiều dài vô hạn hoặc đủ dữ liệu.

### Format và provider compatibility

Theo API, `getEncoded()` trả primary encoding; nếu có đặc tả ASN.1 cho tham số thì primary format sử dụng ASN.1. Tuy nhiên, *không* suy ra mọi provider đều hỗ trợ cùng tên thuật toán, cùng format phụ hoặc đọc được mọi encoding của nhau. `getEncoded(String format)` và `init(byte[], String format)` chỉ dùng được khi provider hỗ trợ format yêu cầu.

Đối với dữ liệu lưu lâu dài, nhiều runtime hoặc liên thông Java với hệ khác, cách an toàn về kỹ thuật là định nghĩa format lưu ở mức trường (`iv`, `tagBits`, v.v.), ghi rõ phiên bản, rồi viết test round-trip giữa các runtime/provider mục tiêu. Nếu chọn `AlgorithmParameters.getEncoded()` thì phải lưu thông tin format và có bài kiểm thử tương thích thực tế.

## 7. Giới hạn an toàn và lỗi thường gặp

1. **Nonce AES-GCM phải duy nhất với mỗi lần mã hóa dưới cùng khóa.** Nonce 12 byte từ `SecureRandom` là cách minh họa thực dụng; hệ thống xử lý lượng dữ liệu lớn cần kiểm soát khả năng trùng, giới hạn lượt mã hóa mỗi khóa và chính sách thay khóa. Không dùng nonce cố định, zero-IV hoặc tái sử dụng nonce cũ.
2. **Không nhầm tham số công khai với khóa.** IV, salt thường có thể đi cùng bản mã; key vẫn cần kiểm soát truy cập và quản lý vòng đời riêng. Đừng lưu key cạnh ciphertext chỉ để tiện giải mã.
3. **Không bỏ authentication tag hay nuốt lỗi xác thực.** GCM là AEAD: `AEADBadTagException` phải dẫn tới từ chối dữ liệu. Với CBC, chỉ lưu IV không tự cung cấp tính toàn vẹn.
4. **Không đoán AAD.** AAD được xác thực dù không mã hóa; AAD khi giải mã phải tái tạo đúng byte và lấy từ nguồn ngữ cảnh đáng tin cậy.
5. **Không tin provider sẽ tự sinh lại IV trong lúc giải mã.** Provider có thể sinh tham số ở chế độ mã hóa; khi đó phải lấy và lưu `Cipher.getParameters()` hoặc `getIV()` sau khi `init`.
6. **Không coi mọi spec hợp lệ ở mọi mode/provider.** GCM cần cả tag length; `IvParameterSpec` không thể thay thế hợp đồng `GCMParameterSpec` một cách an toàn/tổng quát.
7. **Không lưu `toString()` hoặc Java object serialization để round-trip.** Cần trường có schema hoặc byte encoding được xác định và kiểm thử.
8. **Không bỏ bước validate input.** Byte tham số, tagBits, salt/iteration, thuật toán, version và chiều dài ciphertext từ phía không tin cậy phải được kiểm tra trước khi cấp phát hay giải mã.

| Lỗi/triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `InvalidAlgorithmParameterException` khi `Cipher.init` | Spec không phù hợp transformation/provider, thiếu tham số hoặc kích thước không được hỗ trợ | Kiểm tra tên transformation, spec type, IV/tag length và provider. |
| `NoSuchAlgorithmException` khi `AlgorithmParameters.getInstance` | Tên thuật toán tham số không được provider hỗ trợ | Kiểm tra danh sách provider, dùng đúng algorithm name (không nhầm transformation). |
| `InvalidParameterSpecException` | Spec không phù hợp, chưa khởi tạo hoặc cố init lại object | Tạo instance mới, chọn đúng spec/algorithm. |
| `IOException` khi decode/encode tham số | Blob bị cắt/hỏng, encoding sai hoặc object chưa khởi tạo | Kiểm tra size, format, version và encoding provider. |
| `AEADBadTagException` | Key, IV, AAD, ciphertext hoặc tag không khớp | Từ chối bản mã; điều tra dữ liệu lưu/truyền, không hạ cấp bảo mật để bỏ lỗi. |
| `Cipher.getParameters()` trả `null` | Cipher không có tham số cần xuất, hoặc chưa ở trạng thái phù hợp | Đọc hợp đồng thuật toán/mode và thời điểm gọi; không tự bịa IV. |
| Chạy được trên máy A, lỗi trên máy B | Khác provider/encoding, key hoặc AAD | Test interoperability; dùng định dạng field-level có version khi cần. |

### Checklist trước khi triển khai

- Đã xác định rõ transformation, keyId, format/version, cách lưu IV/tag và ciphertext/tag?
- Mỗi bản mã mới có nonce duy nhất dưới cùng khóa, và nonce đó được lưu đủ để giải mã?
- AAD được tính lại chính xác và những metadata nhạy cảm đã được ràng buộc xác thực?
- Lưu key riêng bằng cơ chế đáng tin cậy, có rotation và kiểm soát truy cập?
- Có test round-trip, test ciphertext/AAD bị sửa, test dữ liệu bị cắt và test provider khác?
- Có whitelist thuật toán, giới hạn kích thước và từ chối các tham số không hợp lệ?

**Tự thực hành:** sửa ví dụ lần lượt thay (a) 1 byte của ciphertext, (b) AAD, (c) IV lúc giải mã; cả ba phải không vượt qua xác thực. Sau đó thay `AlgorithmParameters` bằng cách lưu `iv` và `tagBits` riêng, khôi phục `GCMParameterSpec`, và đối chiếu ưu/nhược của hai contract lưu trữ. Không đưa khóa thật vào source hay bài tập.

## 8. Tài liệu API chính thức

- [AlgorithmParameters — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/AlgorithmParameters.html): init, encoding, provider, getParameterSpec.
- [AlgorithmParameterSpec — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/AlgorithmParameterSpec.html): marker interface của các lớp spec.
- [Cipher — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): init, getParameters, updateAAD, yêu cầu nonce GCM.
- [GCMParameterSpec — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): IV, tag length.
