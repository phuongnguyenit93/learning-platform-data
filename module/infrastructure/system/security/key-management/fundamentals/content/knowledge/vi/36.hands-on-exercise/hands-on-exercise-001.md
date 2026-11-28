# Sinh AES key bằng SecureRandom

Trong bài thực hành này, bạn sẽ tạo một khóa AES bằng nguồn ngẫu nhiên mật mã của Java, kiểm tra thuộc tính khóa và dùng khóa đó với AES-GCM để mã hóa rồi giải mã một thông điệp mẫu. Bài tập giúp bạn hiểu vai trò của SecureRandom, KeyGenerator, SecretKey và các tham số cần thiết khi sử dụng AES trong một ứng dụng Java.

Bài học thuộc module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, tập trung vào vòng đời khóa mật mã từ tạo và cấp phát đến lưu trữ, sử dụng, xoay vòng và thu hồi. Trong hệ thống thực tế, việc sinh khóa chỉ là bước đầu: khóa còn cần được bảo vệ, phân quyền, kiểm toán và khôi phục theo chính sách.

## 1. Mục tiêu thực hành

Hoàn thành bài này, bạn có thể:

- Giải thích vì sao cần SecureRandom thay cho Random hoặc Math.random.
- Sinh AES-256 key bằng KeyGenerator và SecureRandom.
- Phân biệt KeyGenerator với cách tạo raw key bytes bằng SecureRandom.
- Kiểm tra thuật toán và độ dài khóa mà không in key material.
- Dùng AES/GCM/NoPadding để mã hóa và giải mã dữ liệu mẫu.
- Xác minh dữ liệu bị sửa đổi sẽ không vượt qua kiểm tra authentication tag.
- Nhận diện những phần cần bổ sung khi chuyển từ bài lab sang ứng dụng production.

## 2. Chuẩn bị môi trường

Bạn cần:

- JDK 17 trở lên.
- Một terminal có lệnh javac và java.
- Một thư mục riêng để tạo file thực hành.

Kiểm tra phiên bản Java:

~~~bash
java -version
javac -version
~~~

Ví dụ dưới đây dùng AES-256. Nếu runtime hoặc chính sách mật mã của môi trường không cho phép kích thước này, hãy kiểm tra cấu hình JDK/provider và yêu cầu triển khai. Có thể chạy biến thể AES-128 bằng cách đổi hằng số key size thành 128; không tự động hạ kích thước khóa trong ứng dụng production khi chưa có phê duyệt.

## 3. Hiểu các thành phần sẽ sử dụng

| Thành phần | Vai trò |
|---|---|
| SecureRandom | Cung cấp byte ngẫu nhiên phù hợp cho mục đích mật mã |
| KeyGenerator | Sinh key object cho một thuật toán như AES |
| SecretKey | Đại diện cho khóa bí mật dùng trong thao tác mật mã |
| Cipher | Thực hiện mã hóa và giải mã |
| GCMParameterSpec | Cấu hình độ dài authentication tag và nonce/IV cho GCM |
| AEAD | Cơ chế vừa bảo vệ tính bí mật vừa xác thực ciphertext và additional authenticated data |

SecureRandom là một cryptographically secure pseudo-random number generator (CSPRNG). Provider của Java quản lý cơ chế seed và tạo số ngẫu nhiên. Thông thường, có thể khởi tạo bằng new SecureRandom(); không cần tự seed bằng thời gian hệ thống, PID hoặc dữ liệu dễ đoán.

KeyGenerator được khuyến nghị để tạo khóa AES vì nó tạo key object theo thuật toán và provider. Truyền SecureRandom vào init giúp chỉ định nguồn ngẫu nhiên dùng khi sinh khóa:

~~~java
SecureRandom random = new SecureRandom();
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256, random);
SecretKey key = generator.generateKey();
~~~

Không dùng java.util.Random hoặc Math.random để tạo key, nonce hay material mật mã. Các API đó không được thiết kế để chống dự đoán.

## 4. Tạo project lab

Tạo một thư mục mới, ví dụ aes-key-lab, rồi tạo file AesKeyGenerationLab.java với nội dung ở phần tiếp theo. Chỉ sử dụng dữ liệu mẫu trong bài tập; không đưa khóa sinh ra vào source control, ticket, log hoặc chat.

## 5. Viết chương trình hoàn chỉnh

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AesKeyGenerationLab {
    private static final int AES_KEY_BITS = 256;
    private static final int GCM_NONCE_BYTES = 12;
    private static final int GCM_TAG_BITS = 128;

    private AesKeyGenerationLab() {
    }

    public static void main(String[] args) throws Exception {
        SecureRandom secureRandom = new SecureRandom();
        SecretKey key = generateAesKey(secureRandom);

        byte[] encodedKey = key.getEncoded();
        if (encodedKey == null) {
            throw new IllegalStateException("Test key is not extractable");
        }

        try {
            int actualKeyBits = encodedKey.length * Byte.SIZE;
            if (actualKeyBits != AES_KEY_BITS) {
                throw new IllegalStateException(
                        "Unexpected AES key size: " + actualKeyBits);
            }

            System.out.println("Algorithm: " + key.getAlgorithm());
            System.out.println("Key size: " + actualKeyBits + " bits");
        } finally {
            // Best-effort clearing of the encoded copy returned by getEncoded().
            Arrays.fill(encodedKey, (byte) 0);
        }

        byte[] nonce = new byte[GCM_NONCE_BYTES];
        secureRandom.nextBytes(nonce);

        byte[] aad = "customer-record:v1".getBytes(StandardCharsets.UTF_8);
        byte[] plaintext =
                "Key storage and encryption lab".getBytes(StandardCharsets.UTF_8);

        byte[] ciphertext = encrypt(key, nonce, aad, plaintext);
        byte[] recovered = decrypt(key, nonce, aad, ciphertext);

        boolean roundTripPassed = Arrays.equals(plaintext, recovered);
        if (!roundTripPassed) {
            throw new AssertionError("AES-GCM round-trip failed");
        }
        System.out.println("AES-GCM round-trip: PASS");

        byte[] tamperedCiphertext = ciphertext.clone();
        tamperedCiphertext[0] ^= 1;
        try {
            decrypt(key, nonce, aad, tamperedCiphertext);
            throw new AssertionError("Tampered ciphertext was accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("Tamper detection: PASS");
        }

        Arrays.fill(recovered, (byte) 0);
        Arrays.fill(plaintext, (byte) 0);
        Arrays.fill(tamperedCiphertext, (byte) 0);
        Arrays.fill(ciphertext, (byte) 0);
        Arrays.fill(nonce, (byte) 0);
        Arrays.fill(aad, (byte) 0);
    }

    private static SecretKey generateAesKey(SecureRandom random)
            throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(AES_KEY_BITS, random);
        return generator.generateKey();
    }

    private static byte[] encrypt(
            SecretKey key, byte[] nonce, byte[] aad, byte[] plaintext)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE,
                key,
                new GCMParameterSpec(GCM_TAG_BITS, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(plaintext);
    }

    private static byte[] decrypt(
            SecretKey key, byte[] nonce, byte[] aad, byte[] ciphertext)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE,
                key,
                new GCMParameterSpec(GCM_TAG_BITS, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertext);
    }
}
~~~

Chương trình không in key bytes. Nó chỉ hiển thị tên thuật toán, độ dài khóa và kết quả kiểm tra. Đoạn mã xóa các buffer byte có thể truy cập sau khi dùng; đây là best effort, không phải bằng chứng rằng mọi bản sao trong heap hoặc bên trong provider đã bị zeroize. Với dữ liệu nhạy cảm, cần thiết kế quản lý bộ nhớ và nơi giữ khóa phù hợp hơn.

## 6. Biên dịch và chạy

Từ thư mục chứa file:

~~~bash
javac AesKeyGenerationLab.java
java AesKeyGenerationLab
~~~

Kết quả dự kiến:

~~~text
Algorithm: AES
Key size: 256 bits
AES-GCM round-trip: PASS
Tamper detection: PASS
~~~

Kết quả có thể khác về chi tiết lỗi giữa các JDK/provider. Nếu chương trình không chạy:

- NoSuchAlgorithmException: kiểm tra provider có hỗ trợ AES hoặc AES/GCM/NoPadding không.
- InvalidKeyException: kiểm tra key size và policy mật mã của runtime.
- InvalidAlgorithmParameterException: kiểm tra GCM nonce và tag length.
- AEADBadTagException ở lần giải mã bình thường: kiểm tra nonce, AAD, ciphertext và key có khớp nhau không.

Nếu test tampering không ném AEADBadTagException, kiểm tra lại cách thay đổi ciphertext và bảo đảm chương trình đang dùng GCM cùng tag được xác thực.

## 7. Cách tạo raw AES key bytes trực tiếp

KeyGenerator là lựa chọn ưu tiên trong ứng dụng Java. Để hiểu rõ SecureRandom tạo byte như thế nào, bạn có thể thử cách tạo raw key bytes rồi bọc thành SecretKey bằng SecretKeySpec:

~~~java
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

SecureRandom random = new SecureRandom();
byte[] rawKey = new byte[32]; // 32 bytes = 256 bits
random.nextBytes(rawKey);

SecretKey key = new SecretKeySpec(rawKey, "AES");
Arrays.fill(rawKey, (byte) 0);
~~~

SecretKeySpec sao chép dữ liệu đầu vào để tạo key object, vì vậy xóa rawKey không bảo đảm xóa bản sao nội bộ của key object. Java cũng không bảo đảm zeroization tuyệt đối cho mọi bản sao trong heap. Cách này hữu ích để hiểu raw key material hoặc tích hợp API yêu cầu byte array; với code thông thường, ưu tiên KeyGenerator.

Không lưu rawKey vào file, không in nó dưới dạng hexadecimal/base64 và không đưa nó vào exception message. Nếu cần lưu khóa, phải dùng một kho khóa được bảo vệ và quy trình quản lý riêng.

## 8. Vì sao nonce của AES-GCM cũng cần SecureRandom?

AES-GCM cần nonce/IV cho mỗi lần mã hóa. Với cách dùng phổ biến, nonce dài 96 bit (12 byte). Nonce không phải secret key và thường có thể lưu cùng ciphertext, nhưng không được tái sử dụng cùng một nonce dưới cùng một key.

Trong bài lab, nonce được tạo như sau:

~~~java
byte[] nonce = new byte[12];
secureRandom.nextBytes(nonce);
~~~

Mỗi lần mã hóa mới bằng cùng một AES key phải dùng nonce mới. Với hệ thống có số lượng bản mã lớn hoặc nhiều instance, cần thiết kế quản lý nonce có xác suất va chạm phù hợp hoặc cơ chế cấp phát duy nhất theo quy mô. Chỉ gọi SecureRandom trong từng instance không thay thế việc đánh giá xác suất va chạm và quy mô sử dụng.

Nonce cần được lưu cùng ciphertext để giải mã. AAD có thể dùng để ràng buộc metadata như tenant ID, record ID hoặc schema version mà không cần mã hóa các trường đó. AAD khi giải mã phải khớp chính xác với AAD khi mã hóa.

## 9. Các bài tập mở rộng

Thực hiện từng bài và ghi lại kết quả trong ghi chú lab:

### Bài tập A — Thay đổi kích thước khóa

- Đổi AES_KEY_BITS từ 256 thành 128.
- Chạy lại chương trình và xác minh độ dài khóa là 128 bits.
- Thử giá trị không hợp lệ như 100 bits và quan sát lỗi từ provider.
- Giải thích vì sao ứng dụng nên validate cấu hình trước khi khởi động.

### Bài tập B — Sinh hai khóa độc lập

- Gọi generateAesKey hai lần với cùng SecureRandom instance.
- So sánh hai key encoding trong bộ nhớ test.
- Xác minh hai khóa không giống nhau.
- Không in hoặc lưu hai key bytes.

Lưu ý: một lần kiểm tra hai khóa khác nhau chỉ là smoke test, không chứng minh nguồn ngẫu nhiên có entropy tốt hoặc triển khai không có bias. Chất lượng CSPRNG cần dựa vào implementation/provider và quy trình đánh giá phù hợp.

### Bài tập C — Kiểm tra AAD

- Mã hóa với AAD là customer-record:v1.
- Giải mã bằng đúng AAD và xác minh thành công.
- Thử giải mã bằng AAD customer-record:v2.
- Xác minh authentication tag không hợp lệ và dữ liệu bị từ chối.

### Bài tập D — Kiểm tra ciphertext bị thay đổi

- Thay đổi một byte ciphertext.
- Thử giải mã và quan sát AEADBadTagException.
- Khôi phục ciphertext gốc và xác minh giải mã thành công.
- Giải thích vì sao ứng dụng không được trả plaintext một phần khi xác thực tag thất bại.

### Bài tập E — Thử nhiều lần mã hóa

- Dùng cùng một key để mã hóa nhiều thông điệp.
- Tạo nonce mới cho mỗi lần.
- Lưu nonce, ciphertext và tag trong cấu trúc dữ liệu test.
- Giải mã từng bản mã và xác minh nội dung.
- Đề xuất cách ứng dụng ngăn việc vô tình tái sử dụng nonce.

## 10. Câu hỏi tự kiểm tra

1. Vì sao SecureRandom phù hợp để sinh key material hơn java.util.Random?
2. KeyGenerator.init(256, secureRandom) có vai trò gì?
3. 32 bytes tương ứng bao nhiêu bits?
4. Vì sao không nên in key bytes để xác minh chương trình?
5. AES-GCM bảo vệ những thuộc tính nào của dữ liệu?
6. Điều gì xảy ra nếu nonce bị tái sử dụng với cùng một key?
7. AAD khác plaintext được mã hóa như thế nào?
8. Vì sao tampered ciphertext phải bị từ chối?
9. Tại sao xóa byte array trong Java chỉ là best effort?
10. Trong production, khi nào nên dùng KMS/HSM thay vì tự giữ AES key trong heap?

## 11. Tiêu chí hoàn thành

- [ ] Biên dịch được chương trình với JDK mục tiêu.
- [ ] Sinh được AES key bằng KeyGenerator và SecureRandom.
- [ ] Xác minh algorithm là AES và key size đúng cấu hình.
- [ ] Không in, log hoặc commit key material.
- [ ] AES-GCM round-trip trả lại đúng plaintext mẫu.
- [ ] Ciphertext bị thay đổi bị phát hiện qua authentication tag.
- [ ] AAD sai làm giải mã thất bại.
- [ ] Mỗi lần mã hóa dùng nonce mới.
- [ ] Giải thích được giới hạn của việc xóa byte array trong Java.
- [ ] Hoàn thành ít nhất hai bài tập mở rộng.

## 12. Đưa kiến thức vào ứng dụng thực tế

Bài lab sinh key trong bộ nhớ của một tiến trình Java để học API. Trong production, không nên mặc định lưu key trong source code, file cấu hình, database hoặc log. Cần chọn mô hình lưu trữ phù hợp:

- Với ứng dụng nhỏ hoặc công cụ cục bộ, dùng KeyStore được bảo vệ, quản lý password riêng và giới hạn filesystem access.
- Với hệ thống dịch vụ, cân nhắc KMS để quản lý key version, policy, audit và thao tác cryptographic.
- Với yêu cầu bảo vệ key material bằng phần cứng, cân nhắc HSM và xác minh key attributes/non-extractability theo Security Policy.
- Dùng workload identity và least privilege để cấp quyền cho đúng service.
- Thiết kế backup/recovery, rotation, revoke và destruction trước khi triển khai.
- Theo dõi audit event cho các thao tác tạo, dùng, đổi quyền và thu hồi key.

Không dùng lại khóa mẫu của bài lab cho dữ liệu thật. Khi ứng dụng dùng KMS/HSM, có thể để dịch vụ tạo DEK, mã hóa dữ liệu bằng DEK trong ứng dụng và chỉ lưu encrypted DEK; KEK được quản lý trong KMS/HSM. Cần bảo vệ plaintext DEK trong thời gian tồn tại ở bộ nhớ và không ghi nó vào log.

Hoàn thành bài tập khi bạn có thể sinh một AES key bằng SecureRandom, xác minh nó qua thao tác AES-GCM và giải thích được cách bảo vệ key material sau khi chương trình kết thúc. Đây là nền tảng để tiếp tục thực hành KeyStore, KMS/HSM, envelope encryption và key rotation trong các bài tiếp theo.
