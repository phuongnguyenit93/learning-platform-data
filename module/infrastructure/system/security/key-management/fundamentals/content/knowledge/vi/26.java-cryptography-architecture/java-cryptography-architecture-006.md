# Cipher trong Java Cryptography Architecture

**Cipher** là lớp engine trong Java Cryptography Architecture (JCA) dùng để mã hóa và giải mã dữ liệu. Ứng dụng yêu cầu một transformation, cung cấp khóa cùng tham số cần thiết, rồi đưa dữ liệu qua các phương thức của Cipher. Việc thực thi thuật toán được giao cho provider phù hợp. Nhờ cơ chế này, mã ứng dụng có thể làm việc với AES, RSA hoặc thuật toán được provider hỗ trợ thông qua một API thống nhất.

Cipher là thành phần trực tiếp biến khóa mật mã thành thao tác bảo vệ dữ liệu. Vì vậy, sử dụng đúng API vẫn chưa đủ: ứng dụng phải chọn transformation an toàn, quản lý nonce/IV chính xác, xác thực dữ liệu khi cần, bảo vệ khóa và xử lý lỗi mà không làm lộ thông tin. Một lỗi nhỏ như tái sử dụng nonce của GCM với cùng khóa có thể làm suy yếu nghiêm trọng tính bảo mật.

## 1. Cipher nằm ở đâu trong JCA?

JCA cung cấp các API mật mã ở mức cao và cơ chế provider để triển khai thuật toán. Các lớp engine như **Cipher**, **MessageDigest**, **Signature**, **Mac**, **KeyFactory** và **KeyAgreement** đại diện cho những loại thao tác khác nhau. Cipher tập trung vào mã hóa và giải mã; nó không thay thế chữ ký số, hàm băm hay mã xác thực thông điệp.

Khi ứng dụng gọi **Cipher.getInstance(...)**, JCA tìm một provider có thể đáp ứng transformation được yêu cầu. Provider có thể là provider mặc định của JDK hoặc provider bổ sung từ bên thứ ba, thiết bị phần cứng hay HSM. Provider quyết định phần triển khai thuật toán và một số khả năng cụ thể như định dạng khóa, tham số, chế độ mã hóa và giới hạn kích thước.

| Thành phần | Vai trò |
|---|---|
| Cipher | API engine để mã hóa và giải mã dữ liệu. |
| Transformation | Mô tả thuật toán, chế độ hoạt động và padding được yêu cầu. |
| Key | Bí mật hoặc khóa riêng/công khai được thuật toán sử dụng. |
| AlgorithmParameterSpec | Mang tham số như IV, nonce, độ dài thẻ xác thực hoặc tham số OAEP. |
| Provider | Cung cấp phần triển khai mật mã cho API JCA. |
| SecureRandom | Sinh dữ liệu ngẫu nhiên mật mã, ví dụ khóa và IV/nonce ngẫu nhiên. |

Ứng dụng nên chọn transformation rõ ràng và kiểm thử trên đúng JDK/provider của môi trường triển khai. Không nên dựa vào một transformation mơ hồ hoặc mặc định không được tài liệu hóa.

## 2. Transformation: thuật toán, mode và padding

Transformation thường có dạng:

~~~text
algorithm/mode/padding
~~~

Ba thành phần mô tả cách Cipher xử lý dữ liệu:

- **Algorithm** là thuật toán mật mã, ví dụ AES hoặc RSA.
- **Mode** là chế độ vận hành của thuật toán khối, ví dụ GCM, CBC hoặc CTR. Một số thuật toán như RSA có cách biểu diễn transformation riêng.
- **Padding** xác định cách xử lý dữ liệu khi độ dài đầu vào không khớp yêu cầu của thuật toán/chế độ. Với GCM và CTR, transformation thường dùng NoPadding; CBC thường dùng một cơ chế padding như PKCS5Padding.

Ví dụ:

| Transformation | Ý nghĩa và lưu ý |
|---|---|
| AES/GCM/NoPadding | Mã hóa đối xứng có xác thực (AEAD); cung cấp bí mật và kiểm tra toàn vẹn/xác thực. |
| AES/CBC/PKCS5Padding | Mã hóa khối theo CBC; tự nó không xác thực dữ liệu, cần thiết kế MAC đúng cách nếu phải bảo vệ tính toàn vẹn. |
| AES/CTR/NoPadding | Chế độ dòng dựa trên bộ đếm; không tự xác thực dữ liệu và không được tái sử dụng tổ hợp khóa/nonce. |
| RSA/ECB/OAEPWithSHA-256AndMGF1Padding | Mã hóa bất đối xứng theo RSA-OAEP; tên ECB trong transformation RSA không có nghĩa là dùng chế độ ECB của AES. RSA chỉ phù hợp với dữ liệu nhỏ như khóa phiên. |

Không sử dụng **AES/ECB** để bảo vệ dữ liệu ứng dụng. ECB mã hóa từng khối độc lập nên các khối bản rõ giống nhau tạo ra khối mã giống nhau, làm lộ cấu trúc dữ liệu. Với ứng dụng mới, lựa chọn phổ biến là AES-GCM khi cần mã hóa đối xứng có xác thực.

Transformation chỉ mô tả thuật toán và cách vận hành. Nó không tự quy định nguồn gốc khóa, cách phân phối khóa, cách lưu nonce, định dạng dữ liệu đầu ra hay chính sách xoay vòng. Những phần đó phải được thiết kế trong giao thức và hệ thống quản lý khóa.

## 3. Vòng đời một đối tượng Cipher

Cipher là đối tượng có trạng thái. Một quy trình thông thường gồm:

1. Lấy instance bằng transformation cụ thể.
2. Khởi tạo bằng chế độ thao tác, khóa và tham số.
3. Đưa dữ liệu vào bằng một hoặc nhiều lần gọi update.
4. Gọi doFinal để hoàn tất thao tác và lấy dữ liệu còn lại.
5. Nếu cần xử lý dữ liệu khác, khởi tạo lại Cipher bằng init.

Các hằng số chế độ thường dùng:

| Hằng số | Mục đích |
|---|---|
| ENCRYPT_MODE | Mã hóa dữ liệu. |
| DECRYPT_MODE | Giải mã dữ liệu. |
| WRAP_MODE | Đóng gói một khóa để truyền hoặc lưu theo cơ chế wrapping. |
| UNWRAP_MODE | Mở gói khóa đã được wrapping. |

Ví dụ khởi tạo và sử dụng:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(Cipher.ENCRYPT_MODE, key, gcmParameterSpec);
byte[] ciphertext = cipher.doFinal(plaintext);
~~~

Với chế độ AEAD như GCM, dữ liệu chỉ được xem là hợp lệ sau khi xác thực thành công tại doFinal khi giải mã. Nếu thẻ xác thực sai, provider ném ngoại lệ, thường là **AEADBadTagException**. Ứng dụng phải loại bỏ bản rõ chưa được xác thực và không được tiếp tục xử lý nó.

Không chia sẻ một đối tượng Cipher đang hoạt động giữa nhiều luồng. Cipher giữ trạng thái nội bộ và các lần gọi update/doFinal thuộc về một phiên thao tác. Hãy tạo hoặc khởi tạo đối tượng riêng cho mỗi thao tác, hoặc quản lý vòng đời đối tượng theo cách bảo đảm không có truy cập đồng thời.

## 4. Mã hóa đối xứng với AES-GCM

AES là thuật toán mã hóa đối xứng: cùng một khóa bí mật được dùng cho mã hóa và giải mã. GCM (Galois/Counter Mode) là chế độ AEAD, cung cấp:

- **Confidentiality**: che giấu nội dung bản rõ.
- **Integrity**: phát hiện dữ liệu bị sửa đổi.
- **Authentication**: xác minh dữ liệu mã hóa và dữ liệu phụ trợ được xác thực.

GCM sử dụng nonce (còn thường được gọi là IV) và thẻ xác thực. Với AES-GCM, cấu hình thường dùng nonce 96 bit (12 byte) và thẻ xác thực 128 bit. Nonce không cần bí mật, nhưng phải duy nhất đối với mỗi lần mã hóa dưới cùng một khóa. Tái sử dụng nonce với cùng khóa có thể làm lộ thông tin và phá vỡ bảo đảm xác thực của GCM.

### Ví dụ mã hóa và giải mã

Ví dụ sau tạo khóa AES cho mục đích minh họa, sinh nonce mới cho mỗi lần mã hóa, rồi đóng gói nonce cùng ciphertext. Trong hệ thống thực tế, khóa nên được cấp từ KMS/HSM hoặc kho khóa được kiểm soát thay vì tạo lại tùy tiện mỗi lần chạy ứng dụng.

~~~java
import java.nio.ByteBuffer;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AesGcmExample {
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    public static SecretKey generateKey()
            throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        return generator.generateKey();
    }

    public static byte[] encrypt(byte[] plaintext, SecretKey key)
            throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        GCMParameterSpec parameters =
                new GCMParameterSpec(TAG_BITS, nonce);
        cipher.init(Cipher.ENCRYPT_MODE, key, parameters);

        byte[] ciphertext = cipher.doFinal(plaintext);
        return ByteBuffer.allocate(nonce.length + ciphertext.length)
                .put(nonce)
                .put(ciphertext)
                .array();
    }

    public static byte[] decrypt(byte[] envelope, SecretKey key)
            throws GeneralSecurityException {
        if (envelope == null
                || envelope.length < NONCE_BYTES + TAG_BITS / 8) {
            throw new IllegalArgumentException("Dữ liệu mã hóa không hợp lệ");
        }

        ByteBuffer buffer = ByteBuffer.wrap(envelope);
        byte[] nonce = new byte[NONCE_BYTES];
        buffer.get(nonce);

        byte[] ciphertext = new byte[buffer.remaining()];
        buffer.get(ciphertext);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        GCMParameterSpec parameters =
                new GCMParameterSpec(TAG_BITS, nonce);
        cipher.init(Cipher.DECRYPT_MODE, key, parameters);

        try {
            return cipher.doFinal(ciphertext);
        } catch (AEADBadTagException e) {
            // Không sử dụng bản rõ khi thẻ xác thực không hợp lệ.
            throw e;
        }
    }
}
~~~

Đầu ra của GCM từ doFinal bao gồm ciphertext và thẻ xác thực. Ví dụ đặt nonce ở đầu mảng để bên giải mã có thể tách ra; hệ thống thực tế nên định nghĩa định dạng có phiên bản, mã định danh khóa và trường độ dài rõ ràng. Không được lưu nonce cố định trong mã nguồn hoặc dùng lại nonce đã dùng trước đó với cùng khóa.

Khóa AES 256 bit trong ví dụ minh họa việc tạo khóa. Khả năng dùng AES-256 còn phụ thuộc phiên bản JDK, chính sách mật mã và provider. Hãy kiểm tra môi trường đích và chọn độ dài khóa theo chính sách của hệ thống.

### Nonce phải duy nhất

Nonce GCM không phải khóa bí mật, nhưng tính duy nhất là điều kiện an toàn quan trọng. Nếu tạo nonce ngẫu nhiên 96 bit, xác suất trùng tăng theo số lần mã hóa dưới cùng một khóa. Hệ thống mã hóa khối lượng lớn hoặc chạy phân tán nên có chiến lược quản lý nonce có thể chứng minh không trùng, chẳng hạn bộ đếm duy nhất theo khóa kết hợp phân vùng/định danh tiến trình và cơ chế cấp phát không lặp.

Nếu dùng nonce ngẫu nhiên, cần giới hạn số lần mã hóa trên một khóa theo hướng dẫn chuẩn và chính sách mật mã được áp dụng. Khi không thể bảo đảm nonce duy nhất, phải thay đổi thiết kế quản lý nonce hoặc khóa. Xoay vòng khóa định kỳ cũng giới hạn số lượng bản mã được tạo dưới một khóa.

## 5. Dữ liệu bổ sung được xác thực (AAD)

AEAD cho phép xác thực dữ liệu phụ trợ mà không mã hóa dữ liệu đó. Trong GCM, dữ liệu này được gọi là Additional Authenticated Data (AAD). Ví dụ AAD có thể chứa mã bản ghi, tenant ID, phiên bản định dạng hoặc metadata định tuyến cần được bảo vệ khỏi sửa đổi nhưng vẫn cần đọc được.

Ứng dụng phải cung cấp cùng AAD, theo cùng thứ tự và cùng byte, ở cả hai phía:

Đoạn dưới giả sử biến **nonce** đã được tách từ envelope lưu trữ. Khi giải mã, phải dùng đúng nonce đã đi cùng ciphertext; không tạo nonce mới cho lượt giải mã.

~~~java
import java.nio.charset.StandardCharsets;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;

byte[] aad = "record-id=8472".getBytes(StandardCharsets.UTF_8);
// nonce được tạo khi mã hóa và lưu cùng ciphertext để giải mã.
GCMParameterSpec gcmParameters = new GCMParameterSpec(128, nonce);

Cipher encryptCipher = Cipher.getInstance("AES/GCM/NoPadding");
encryptCipher.init(Cipher.ENCRYPT_MODE, key, gcmParameters);
encryptCipher.updateAAD(aad);
byte[] ciphertext = encryptCipher.doFinal(plaintext);

Cipher decryptCipher = Cipher.getInstance("AES/GCM/NoPadding");
decryptCipher.init(Cipher.DECRYPT_MODE, key, gcmParameters);
decryptCipher.updateAAD(aad);
byte[] recoveredPlaintext = decryptCipher.doFinal(ciphertext);
~~~

Nếu AAD thay đổi, thẻ xác thực sẽ không hợp lệ và giải mã phải thất bại. AAD không được mã hóa, do đó không đưa bí mật vào đó. Cần chuẩn hóa cách tuần tự hóa metadata để hai phía tạo ra đúng cùng chuỗi byte; không dựa vào biểu diễn chuỗi không ổn định hoặc thứ tự trường tùy ý.

## 6. Mã hóa bất đối xứng và RSA-OAEP

Trong mã hóa bất đối xứng, khóa công khai được dùng để mã hóa và khóa riêng tương ứng được dùng để giải mã. RSA-OAEP là một padding an toàn hơn các kiểu padding RSA cũ cho mục đích mã hóa. Transformation trong Java có thể được chỉ định như sau:

~~~java
import java.security.spec.MGF1ParameterSpec;
import javax.crypto.Cipher;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

Cipher rsa = Cipher.getInstance(
        "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
OAEPParameterSpec oaep = new OAEPParameterSpec(
        "SHA-256",
        "MGF1",
        MGF1ParameterSpec.SHA256,
        PSource.PSpecified.DEFAULT);
rsa.init(Cipher.ENCRYPT_MODE, recipientPublicKey, oaep);
byte[] wrappedDataKey = rsa.doFinal(dataEncryptionKeyBytes);
~~~

Tên transformation cần được đối chiếu với provider và tham số OAEP thực tế, bao gồm digest, MGF1 digest và label. Ví dụ chỉ định SHA-256 cho cả OAEP digest và MGF1 digest; hai phía phải dùng cùng tham số khi giải mã. Cách chỉ định tường minh giúp tránh khác biệt mặc định giữa provider.

RSA có giới hạn kích thước bản rõ phụ thuộc độ dài khóa và hash/padding được chọn. Vì vậy, không nên dùng RSA để mã hóa trực tiếp tệp lớn hoặc thông điệp dài. Một mô hình phổ biến là **hybrid encryption**:

1. Sinh một khóa dữ liệu đối xứng ngẫu nhiên (DEK).
2. Dùng AES-GCM mã hóa dữ liệu bằng DEK.
3. Dùng khóa công khai của bên nhận với RSA-OAEP hoặc cơ chế wrapping phù hợp để bảo vệ DEK.
4. Lưu ciphertext, nonce, thẻ xác thực, DEK đã được bảo vệ và metadata cần thiết.
5. Bên nhận dùng khóa riêng để mở DEK, sau đó dùng DEK giải mã và xác thực dữ liệu.

Trong hệ thống có KMS/HSM, thao tác bảo vệ DEK thường được thực hiện bằng API quản lý khóa thay vì xuất khóa gốc ra ứng dụng. Thiết kế cụ thể phải xác định rõ phiên bản khóa, thuật toán wrapping, metadata xác thực và cách xoay vòng.

## 7. WRAP_MODE và UNWRAP_MODE

Cipher hỗ trợ **WRAP_MODE** và **UNWRAP_MODE** để đóng gói và mở gói đối tượng khóa. Cách này hữu ích khi cần chuyển khóa qua một kênh hoặc lưu trữ dưới dạng đã được bảo vệ.

~~~java
Cipher wrapper = Cipher.getInstance("AESWrap");
wrapper.init(Cipher.WRAP_MODE, wrappingKey);
byte[] wrappedKey = wrapper.wrap(dataEncryptionKey);

Cipher unwrapper = Cipher.getInstance("AESWrap");
unwrapper.init(Cipher.UNWRAP_MODE, wrappingKey);
Key restoredKey = unwrapper.unwrap(
        wrappedKey,
        "AES",
        Cipher.SECRET_KEY);
~~~

Transformation **AESWrap** triển khai thuật toán AES Key Wrap theo khả năng của provider. Khi dùng một cơ chế wrapping khác, cần kiểm tra chuẩn, tham số và khả năng tương thích của hai phía. Không nhầm wrapping khóa với mã hóa dữ liệu thông thường: wrapping có định dạng và quy tắc riêng cho key material.

Trong KMS, khóa wrapping thường được gọi là KEK (Key Encryption Key), còn khóa dùng mã hóa dữ liệu là DEK (Data Encryption Key). KEK có thể nằm trong HSM hoặc dịch vụ KMS và không được xuất ra ứng dụng. Ứng dụng chỉ nhận DEK ở dạng đã mở gói trong phạm vi quyền hạn cho phép, hoặc yêu cầu KMS thực hiện thao tác mã hóa/giải mã trực tiếp.

## 8. Xử lý dữ liệu lớn và các phương thức update/doFinal

Với dữ liệu nhỏ, có thể truyền toàn bộ mảng byte cho **doFinal**. Với dữ liệu lớn, **update** cho phép xử lý theo từng phần để giảm nhu cầu giữ toàn bộ dữ liệu trong bộ nhớ. Cipher có thể giữ lại một phần dữ liệu nội bộ cho đến khi nhận đủ khối hoặc đến doFinal.

Một số điểm quan trọng:

- Dùng cùng một instance Cipher cho các phần dữ liệu thuộc một thao tác đã khởi tạo.
- Gọi doFinal đúng một lần để kết thúc thao tác và lấy phần đầu ra còn lại.
- Khởi tạo lại Cipher trước khi bắt đầu thao tác mới.
- Với AEAD, không sử dụng dữ liệu giải mã như bản rõ hợp lệ trước khi xác thực thẻ thành công.
- Khi giải mã luồng lớn bằng AEAD, cần thiết kế buffering hoặc định dạng chunk có xác thực để ứng dụng không phát dữ liệu chưa xác thực cho thành phần phía sau.

Không phải mọi provider đều có cùng giới hạn bộ đệm hoặc hiệu năng. Nếu dùng phương thức nhận buffer đầu ra do ứng dụng cấp, cần xử lý **ShortBufferException** và kích thước đầu ra theo tài liệu API/provider.

## 9. Lỗi thường gặp và cách xử lý

| Lỗi hoặc triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| NoSuchAlgorithmException | Provider không hỗ trợ transformation được yêu cầu hoặc tên transformation sai. | Kiểm tra tên thuật toán, mode, padding, JDK và provider được cài đặt. |
| NoSuchPaddingException | Padding được yêu cầu không được provider hỗ trợ. | Chọn transformation chuẩn mà provider hỗ trợ; không thay padding tùy tiện mà chưa đánh giá bảo mật. |
| InvalidKeyException | Sai loại khóa, độ dài khóa không được phép hoặc khóa không tương thích với thuật toán. | Kiểm tra thuật toán/độ dài khóa, chính sách JDK và provider. |
| InvalidAlgorithmParameterException | Thiếu hoặc sai tham số như IV, nonce hay OAEPParameterSpec. | Cung cấp đúng loại tham số và độ dài theo transformation. |
| AEADBadTagException | Ciphertext, nonce, AAD hoặc thẻ xác thực bị sai; dữ liệu có thể đã bị sửa. | Từ chối bản rõ, kiểm tra định dạng và khóa; không thử bỏ qua xác thực. |
| BadPaddingException | Sai khóa, dữ liệu hỏng hoặc padding không hợp lệ ở chế độ có padding. | Xác minh khóa, transformation và dữ liệu đầu vào; tránh trả lỗi chi tiết có thể tạo oracle. |
| IllegalBlockSizeException | Đầu vào không phù hợp với kích thước khối hoặc dữ liệu không đầy đủ theo chế độ. | Kiểm tra transformation, cách chia chunk và việc gọi doFinal. |
| Kết quả giải mã khác bản rõ | Sai khóa, sai IV/nonce, sai AAD, sai thứ tự ghép dữ liệu hoặc sai định dạng. | Kiểm tra metadata đi kèm ciphertext và phiên bản định dạng. |

Thông báo lỗi từ giải mã có thể tiết lộ thông tin hữu ích cho kẻ tấn công nếu phân biệt quá chi tiết giữa sai padding, sai khóa hoặc dữ liệu xác thực. Với giao thức bên ngoài, trả lỗi chung phù hợp và ghi log nội bộ ở mức không chứa khóa, bản rõ hoặc bí mật.

## 10. Những sai lầm bảo mật cần tránh

**Dùng ECB.** ECB để lộ mẫu lặp trong bản rõ. Không sử dụng cho dữ liệu ứng dụng mới.

**Dùng CBC hoặc CTR mà không xác thực.** Hai chế độ này không tự cung cấp kiểm tra toàn vẹn. Nếu buộc phải dùng vì tương thích, cần thiết kế mã hóa và xác thực theo cấu trúc an toàn đã được đánh giá, ví dụ Encrypt-then-MAC với khóa độc lập và so sánh MAC an toàn. Ưu tiên AEAD như GCM khi phù hợp.

**Tái sử dụng nonce/IV.** Với GCM, nonce phải duy nhất dưới cùng khóa. Với CTR, tái sử dụng counter/nonce cũng có thể làm lộ quan hệ giữa bản rõ. Cần có cơ chế cấp phát nonce rõ ràng và giám sát số lần sử dụng khóa.

**Dùng khóa hoặc IV cố định.** Không đặt khóa, nonce hoặc IV cố định trong mã nguồn. Khóa phải được sinh/cấp phát từ nguồn phù hợp và quản lý qua vòng đời; IV/nonce phải được tạo hoặc cấp phát theo yêu cầu của chế độ.

**Dùng mật khẩu trực tiếp làm khóa.** Mật khẩu của con người không phải khóa AES có entropy phù hợp. Nếu phải mã hóa từ mật khẩu, dùng KDF chuyên dụng như PBKDF2 với salt ngẫu nhiên và số vòng lặp phù hợp; cân nhắc KDF chống dò ngoại tuyến như scrypt hoặc Argon2 khi hệ sinh thái hỗ trợ. Không tự băm mật khẩu một lần rồi dùng làm khóa.

**Dùng RSA để mã hóa dữ liệu lớn.** RSA có giới hạn kích thước đầu vào. Hãy dùng mã hóa lai, trong đó thuật toán đối xứng xử lý dữ liệu và thuật toán bất đối xứng bảo vệ khóa dữ liệu.

**Bỏ qua lỗi xác thực.** Khi GCM báo thẻ không hợp lệ, bản rõ không được chấp nhận. Không trả về dữ liệu một phần hoặc chuyển tiếp dữ liệu đó cho tầng nghiệp vụ.

**Tự chọn provider mà không kiểm thử.** Các provider có thể khác nhau về thuật toán, tham số, chính sách và hiệu năng. Nếu triển khai cần HSM hoặc provider cụ thể, kiểm tra cấu hình, tính tương thích và hành vi lỗi trên môi trường đích.

## 11. Tích hợp Cipher với vòng đời quản lý khóa

Cipher chỉ thực hiện thao tác mật mã. Hệ thống quản lý khóa quyết định khóa được tạo, cấp phát, lưu, sử dụng, xoay vòng và hủy như thế nào.

| Giai đoạn khóa | Vai trò của Cipher và hệ thống liên quan |
|---|---|
| Tạo | KeyGenerator hoặc KMS tạo khóa; SecureRandom hỗ trợ sinh nonce/IV theo yêu cầu thuật toán. |
| Cấp phát | Ứng dụng nhận khóa hoặc quyền gọi KMS theo danh tính dịch vụ và chính sách. |
| Lưu trữ | Khóa được bảo vệ trong KMS/HSM hoặc kho bí mật; ciphertext đi kèm metadata phiên bản khóa. |
| Sử dụng | Cipher thực hiện mã hóa/giải mã; ứng dụng kiểm soát quyền, mục đích và số lần sử dụng khóa. |
| Xoay vòng | Tạo khóa mới, ghi mã định danh phiên bản vào bản mã và duy trì khả năng giải mã dữ liệu cũ theo chính sách. |
| Thu hồi | Ngăn thao tác mới bằng khóa bị thu hồi; đánh giá dữ liệu còn phụ thuộc và xử lý sự cố nếu khóa lộ. |
| Hủy | Hủy key material hoặc vô hiệu hóa khóa trong KMS/HSM; đánh giá bản sao, cache, DEK đã xuất và bản sao lưu. |

Một định dạng bản mã dùng trong hệ thống thực tế nên có tối thiểu: phiên bản định dạng, thuật toán, mã định danh khóa, nonce/IV, ciphertext, thẻ xác thực (nếu được tách riêng) và AAD hoặc thông tin đủ để tái tạo AAD. Metadata phải được xác thực để kẻ tấn công không thể đổi thuật toán hoặc mã định danh khóa một cách âm thầm. Không đưa khóa bí mật vào metadata.

Với envelope encryption, dữ liệu lớn được mã hóa bằng DEK và DEK được bảo vệ bằng KEK trong KMS/HSM. Khi xoay vòng KEK, có thể rewrap DEK theo khả năng của KMS thay vì giải mã và mã hóa lại toàn bộ dữ liệu, nhưng cần tuân theo chính sách và giới hạn của dịch vụ. Khi xoay vòng DEK, dữ liệu tương ứng thường cần được mã hóa lại hoặc duy trì cơ chế đọc các phiên bản cũ cho đến khi chuyển đổi hoàn tất.

## 12. Checklist trước khi đưa Cipher vào sản xuất

- [ ] Transformation được chỉ định đầy đủ và đã được đánh giá an toàn.
- [ ] Provider và phiên bản JDK đích hỗ trợ thuật toán, mode, padding và độ dài khóa.
- [ ] Khóa được cấp phát và bảo vệ theo chính sách quản lý khóa.
- [ ] Với GCM, nonce duy nhất dưới cùng khóa và thẻ xác thực đủ mạnh.
- [ ] AAD được chuẩn hóa và cung cấp giống nhau ở cả hai phía.
- [ ] Bản rõ chỉ được sử dụng sau khi giải mã và xác thực thành công.
- [ ] Định dạng ciphertext có phiên bản và lưu metadata cần thiết để giải mã.
- [ ] Có kế hoạch xoay vòng, thu hồi và xử lý dữ liệu được mã hóa bằng khóa cũ.
- [ ] Log và thông báo lỗi không làm lộ khóa, mật khẩu, bản rõ hoặc chi tiết xác thực nhạy cảm.
- [ ] Có kiểm thử tương thích, khôi phục và xử lý dữ liệu bị sửa đổi.

Cipher là điểm thực thi mã hóa và giải mã trong JCA. Chất lượng bảo vệ phụ thuộc vào transformation, tham số, cách dùng API và toàn bộ quy trình quản lý khóa phía sau. Khi kết hợp AEAD, nonce được quản lý đúng, xác thực dữ liệu và KMS/HSM, ứng dụng Java có thể bảo vệ dữ liệu trong suốt vòng đời mà vẫn duy trì khả năng vận hành và xoay vòng khóa có kiểm soát.
