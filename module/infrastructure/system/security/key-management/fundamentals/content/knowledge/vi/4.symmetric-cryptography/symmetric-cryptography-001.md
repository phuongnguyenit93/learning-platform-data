# Symmetric encryption — Mã hóa đối xứng

## 1. Mã hóa đối xứng là gì?

**Symmetric encryption (mã hóa đối xứng)** là phương pháp mã hóa trong đó **cùng một khóa bí mật** được dùng để mã hóa dữ liệu và giải mã dữ liệu. Người gửi và người nhận, hoặc các thành phần cùng xử lý dữ liệu, phải có quyền truy cập hợp lệ vào khóa đó. Nếu khóa bị lộ, người có bản mã và khóa có thể giải mã thông tin mà thuật toán bảo vệ.

Trong chương **Mật mã đối xứng** của học phần quản lý khóa mật mã, mã hóa đối xứng không chỉ là thao tác biến plaintext thành ciphertext. Việc tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy khóa quyết định dữ liệu có thật sự được bảo vệ trong toàn bộ vòng đời hay không. Các cơ chế như **KMS/HSM, envelope encryption, phân quyền và kiểm toán** giúp ứng dụng sử dụng khóa đúng cách.

Ví dụ, một hệ thống thương mại điện tử cần lưu địa chỉ khách hàng:

- **Plaintext (bản rõ):** Địa chỉ trước khi mã hóa.
- **Secret key (khóa bí mật):** Chẳng hạn một khóa AES-256 được sinh ngẫu nhiên.
- **Encryption algorithm:** Thuật toán và chế độ vận hành được dùng, ví dụ AES-GCM.
- **Ciphertext (bản mã):** Dữ liệu đã mã hóa, không thể đọc trực tiếp nếu thiếu khóa và tham số cần thiết.
- **Decryption:** Dùng đúng khóa, nonce và các tham số liên quan để khôi phục bản rõ, đồng thời kiểm tra tính xác thực khi dùng chế độ mã hóa có xác thực.

~~~mermaid
flowchart LR
    P["Plaintext<br/>Dữ liệu gốc"] --> E["Encrypt<br/>AES-GCM"]
    K["Secret key<br/>Chia sẻ với thành phần được phép"] --> E
    N["Nonce + AAD"] --> E
    E --> C["Ciphertext + authentication tag"]
    C --> D["Decrypt & verify<br/>AES-GCM"]
    K --> D
    N --> D
    D --> R["Plaintext<br/>Chỉ khi tag hợp lệ"]
~~~

**Mục tiêu chính** của mã hóa là bảo vệ **tính bí mật** của dữ liệu. Tuy nhiên, mã hóa thuần túy có thể không phát hiện bản mã bị chỉnh sửa; vì vậy, trong các ứng dụng mới thường ưu tiên **authenticated encryption (AEAD)** để bảo vệ cả tính bí mật lẫn tính toàn vẹn/xác thực của dữ liệu trong phạm vi mô hình mật mã.

## 2. Cơ chế hoạt động và thuật ngữ cơ bản

Mô hình khái niệm của mã hóa đối xứng:

~~~text
Encryption:
    ciphertext = Encrypt(key, plaintext, parameters)

Decryption:
    plaintext = Decrypt(key, ciphertext, parameters)

Authenticated encryption (AEAD):
    (ciphertext, tag) = Encrypt(key, nonce, plaintext, AAD)
    plaintext hoặc lỗi = DecryptAndVerify(
        key, nonce, ciphertext, tag, AAD
    )
~~~

Các tham số quan trọng:

| Thành phần | Vai trò | Có cần bí mật? |
| --- | --- | --- |
| **Secret key** | Bí mật điều khiển phép mã hóa/giải mã | **Có**, trừ các thành phần được cấp quyền |
| **Plaintext** | Nội dung gốc cần bảo vệ | Thường là dữ liệu cần giữ bí mật |
| **Ciphertext** | Kết quả mã hóa | Có thể lưu cùng các metadata, nhưng vẫn phải kiểm soát truy cập và vòng đời |
| **Nonce/IV** | Giá trị riêng cho một lần mã hóa theo yêu cầu của thuật toán/mode | Thường **không cần bí mật**, nhưng phải tuân thủ yêu cầu duy nhất hoặc ngẫu nhiên của mode |
| **AAD (Additional Authenticated Data)** | Ngữ cảnh được xác thực nhưng không mã hóa, ví dụ tenant ID, loại bản ghi | Không được che giấu bởi AEAD, nên tránh đặt bí mật trong AAD |
| **Authentication tag** | Giá trị để kiểm tra ciphertext/AAD có hợp lệ dưới khóa và tham số tương ứng | Không cần bí mật; phải xác minh trước khi chấp nhận plaintext |

Hai khóa có cùng độ dài nhưng **khác giá trị** không thể thay thế cho nhau. Đổi key version khi chưa chuyển dữ liệu phụ thuộc có thể khiến bản mã cũ không thể giải mã. Ngược lại, nếu một khóa được dùng cho quá nhiều dữ liệu hoặc nhiều miền độc lập, sự cố với khóa đó có thể ảnh hưởng trên diện rộng.

### 2.1. Độ dài khóa và độ mạnh mật mã

**Key length** là số bit biểu diễn khóa; với AES có ba lựa chọn tiêu chuẩn:

| Thuật toán | Độ dài khóa | Kích thước |
| --- | ---: | ---: |
| AES-128 | 128 bit | 16 byte |
| AES-192 | 192 bit | 24 byte |
| AES-256 | 256 bit | 32 byte |

Một khóa AES-256 được sinh thật sự ngẫu nhiên có không gian khóa lớn hơn khóa AES-128. Dù vậy, tăng độ dài khóa **không sửa** lỗi lộ khóa ở log, tái sử dụng nonce trong GCM, cấp quyền Decrypt quá rộng hoặc sử dụng mode không phù hợp. Khi lựa chọn cần cân nhắc yêu cầu bảo mật, thời gian dữ liệu cần được bảo vệ, chính sách áp dụng và hỗ trợ của thư viện/KMS.

**Không được tạo khóa AES bằng cách đệm một mật khẩu ngắn đến đủ 16 hoặc 32 byte.** Khóa hệ thống nên đến từ bộ sinh số ngẫu nhiên dùng cho mật mã (**CSPRNG**) hoặc KMS/HSM. Nếu bắt buộc xuất phát từ mật khẩu của người dùng, cần một **password-based KDF** có salt và tham số phù hợp như Argon2id hoặc PBKDF2; cơ chế này tăng chi phí đoán mật khẩu nhưng không biến mật khẩu yếu thành bí mật có entropy cao.

### 2.2. So sánh mật mã đối xứng và bất đối xứng

| Tiêu chí | Đối xứng | Bất đối xứng |
| --- | --- | --- |
| Khóa | Các bên được phép dùng cùng khóa bí mật | Một cặp public key/private key có vai trò khác nhau |
| Tác vụ điển hình | Mã hóa khối lượng lớn dữ liệu, bảo vệ DEK, bảo vệ thông điệp | Trao đổi/thiết lập khóa, mã hóa khóa trong sơ đồ phù hợp, chữ ký số |
| Hiệu năng | Thường thích hợp với dữ liệu lớn | Nhiều thao tác khóa công khai tốn tài nguyên hơn; không thường mã hóa cả dữ liệu lớn bằng phép toán bất đối xứng trực tiếp |
| Thách thức quản lý | Phân phối bí mật cho đúng bên và giới hạn phạm vi lộ khóa | Bảo vệ private key và xác thực public key thuộc đúng chủ thể |
| Bảo vệ nguồn gốc người ký | Không tự cung cấp chữ ký số có thể xác minh công khai | Chữ ký số cho phép xác minh bằng public key tương ứng |

Trong các giao thức hiện đại như TLS, mật mã bất đối xứng thường hỗ trợ xác thực và thiết lập bí mật phiên; sau đó **mật mã đối xứng** bảo vệ dữ liệu phiên vì phù hợp với lưu lượng lớn. Đây là ví dụ hai nhóm thuật toán **bổ sung** cho nhau.

## 3. Thuật toán và chế độ mã hóa đối xứng

### 3.1. AES là thuật toán khối

**AES (Advanced Encryption Standard)** là thuật toán mã hóa khối với kích thước khối **128 bit (16 byte)**, không phụ thuộc khóa là AES-128, AES-192 hay AES-256. AES riêng lẻ xử lý các khối; muốn mã hóa thông điệp có độ dài bất kỳ một cách an toàn, cần **mode of operation** thích hợp.

Tên **AES-256** cho biết độ dài khóa 256 bit, **không** có nghĩa kích thước khối là 256 bit. Việc lựa chọn mode và quản lý nonce/IV quan trọng không kém việc lựa chọn độ dài khóa.

### 3.2. Các mode cần phân biệt

| Mode / AEAD | Tính chất | Lưu ý sử dụng |
| --- | --- | --- |
| **AES-GCM** | Mã hóa có xác thực (AEAD), hiệu quả và được hỗ trợ rộng | Nonce phải không tái sử dụng dưới cùng khóa; kiểm tra tag và AAD |
| **AES-CCM** | AEAD, phổ biến trong một số giao thức/thiết bị | Tuân thủ giới hạn kích thước, nonce và tag của cấu hình |
| **ChaCha20-Poly1305** | AEAD dùng stream cipher và cơ chế xác thực | Cũng yêu cầu quản lý nonce nghiêm ngặt; không phải một mode của AES |
| **AES-CBC** | Chỉ cung cấp mã hóa trong cách dùng thông thường | Không tự xác thực; cần cơ chế MAC phù hợp và chống padding oracle nếu dùng hệ thống cũ |
| **AES-CTR** | Biến AES thành dòng khóa | Không tự xác thực; không được trùng bộ đếm/nonce với cùng khóa |
| **AES-ECB** | Mã hóa từng khối độc lập | **Không nên dùng để mã hóa dữ liệu ứng dụng** vì làm lộ mẫu khối giống nhau |
| **AES-XTS** | Thiết kế cho các đơn vị dữ liệu trên thiết bị lưu trữ | Không thay thế AEAD cho bản ghi, API hoặc thông điệp có yêu cầu xác thực |

Ưu tiên **AEAD** khi thiết kế mới nếu môi trường hỗ trợ. Nếu cần tương thích với hệ thống cũ dùng CBC/CTR, phải xem xét phương án xác thực bản mã đúng chuẩn, quản lý IV và xử lý lỗi; không tự ghép thuật toán bằng trực giác.

### 3.3. Tại sao ECB nguy hiểm?

ECB mã hóa các khối plaintext giống nhau thành các khối ciphertext giống nhau dưới cùng một khóa. Vì vậy, những mẫu lặp trong dữ liệu có thể còn hiện rõ ở bản mã. Chỉ chọn khóa dài hơn không loại bỏ đặc tính này. Đối với dữ liệu ứng dụng, nên chọn mode phù hợp, đặc biệt là AEAD khi cần bảo vệ cả bí mật và tính toàn vẹn.

### 3.4. GCM cần nonce duy nhất và tag hợp lệ

Trong AES-GCM, các thông số thường gặp gồm:

- **Key:** Khóa AES 128 hoặc 256 bit (AES cũng hỗ trợ 192 bit).
- **Nonce/IV:** Thường dùng **96 bit (12 byte)**. Nonce có thể được lưu công khai cùng ciphertext.
- **Tag:** Thường dùng **128 bit (16 byte)**, để phát hiện bản mã/AAD không hợp lệ.
- **AAD:** Dữ liệu bổ sung được xác thực nhưng không mã hóa. AAD có thể gắn bản mã với **tenant ID, record ID, schema version** hoặc mục đích nghiệp vụ.

~~~text
key = AES-256 DEK
nonce = giá trị riêng cho lần mã hóa hiện tại
AAD = "tenant:42|record:invoice-7|version:1"
(ciphertext, tag) = AES-GCM-Encrypt(key, nonce, plaintext, AAD)

Lưu: ciphertext, tag, nonce, wrapped-DEK, keyId, AAD metadata

Khi đọc:
  chọn đúng keyId và phiên bản DEK
  dựng lại AAD đúng từ ngữ cảnh đáng tin cậy
  plaintext = AES-GCM-DecryptAndVerify(...)
  nếu tag không hợp lệ: từ chối bản ghi, không trả plaintext
~~~

**Không bao giờ tái sử dụng cùng một nonce dưới cùng một khóa GCM.** Vi phạm có thể phá hỏng cả tính bí mật và khả năng xác thực. Nonce sinh ngẫu nhiên 96 bit có thể phù hợp cho số lần mã hóa có kiểm soát; hệ thống lưu lượng lớn phải quản lý xác suất trùng, giới hạn số lần sử dụng khóa và phương án nonce duy nhất theo yêu cầu thuật toán. Nonce có thể là công khai nhưng **tính duy nhất** vẫn bắt buộc.

AEAD **không tự chống phát lại (replay)**. Kẻ tấn công có thể đưa lại một bản mã cũ hợp lệ. Nếu ứng dụng cần chống replay, phải bổ sung sequence number, version, timestamp, idempotency control hoặc trạng thái phù hợp được ràng buộc và kiểm tra ở lớp giao thức/nghiệp vụ.

## 4. Ví dụ Java: AES-256-GCM có xác thực

Java hỗ trợ AES-GCM qua Java Cryptography Architecture (JCA/JCE). Ví dụ sau minh họa một lần mã hóa/giải mã với khóa mới, nonce ngẫu nhiên 12 byte và AAD:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class SymmetricEncryptionDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    static final class EncryptedRecord {
        final byte[] nonce;
        final byte[] ciphertextWithTag;

        EncryptedRecord(byte[] nonce, byte[] ciphertextWithTag) {
            this.nonce = nonce;
            this.ciphertextWithTag = ciphertextWithTag;
        }
    }

    static SecretKey newAes256Key() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        return generator.generateKey();
    }

    static EncryptedRecord encrypt(
            SecretKey key, byte[] plaintext, byte[] aad
    ) throws Exception {
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce); // Nonce mới cho lần mã hóa này.

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                    new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        byte[] ciphertextWithTag = cipher.doFinal(plaintext);

        return new EncryptedRecord(nonce, ciphertextWithTag);
    }

    static byte[] decrypt(
            SecretKey key, EncryptedRecord record, byte[] aad
    ) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                    new GCMParameterSpec(TAG_BITS, record.nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(record.ciphertextWithTag);
        // Nếu tag/AAD không hợp lệ, doFinal ném lỗi xác thực.
    }

    public static void main(String[] args) throws Exception {
        SecretKey key = newAes256Key();
        byte[] aad = "tenant:42|record:invoice-7|version:1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Noi dung can bao ve"
                .getBytes(StandardCharsets.UTF_8);

        EncryptedRecord record = encrypt(key, plaintext, aad);
        byte[] restored = decrypt(key, record, aad);

        System.out.println(new String(restored, StandardCharsets.UTF_8));

        // Kiểm tra: sửa bản mã sẽ khiến giải mã thất bại.
        byte[] corrupted = Arrays.copyOf(
                record.ciphertextWithTag, record.ciphertextWithTag.length
        );
        corrupted[0] ^= 1;
        try {
            decrypt(key, new EncryptedRecord(record.nonce, corrupted), aad);
            throw new AssertionError("Tampered ciphertext was accepted");
        } catch (javax.crypto.AEADBadTagException expected) {
            System.out.println("Tu choi ban ma da bi sua");
        }
    }
}
~~~

**Giải thích chi tiết:**

1. **KeyGenerator.init(256, RNG)** tạo khóa AES-256 với nguồn ngẫu nhiên dùng cho mật mã; khóa này là bí mật cần quản lý.
2. **RNG.nextBytes(nonce)** tạo nonce 12 byte; ở thiết kế thực tế cần đảm bảo **không trùng nonce với cùng khóa** trong phạm vi khối lượng sử dụng dự kiến.
3. **GCMParameterSpec(128, nonce)** đặt tag xác thực 128 bit; số 128 ở đây **không phải độ dài khóa**.
4. **updateAAD(aad)** đưa vào ngữ cảnh cần xác thực. Khi giải mã, AAD phải khớp chính xác; nên dựng từ dữ liệu nghiệp vụ đáng tin cậy, tránh tin hoàn toàn vào ngữ cảnh do bên tấn công tự cung cấp.
5. **doFinal(...)** mã hóa và tạo tag; lúc giải mã nó xác minh tag và báo lỗi nếu ciphertext/AAD không khớp. Không trả dữ liệu đã giải mã nếu xác thực thất bại.

Đây là ví dụ kỹ thuật để hiểu API, **chưa phải cơ chế lưu trữ khóa cho production**. Ứng dụng thực phải bảo vệ khóa qua KMS/HSM hoặc envelope encryption, lưu nonce/ciphertext/tag và key ID/version theo định dạng rõ ràng, xử lý lỗi và giới hạn truy cập. Không ghi plaintext hoặc key dạng rõ vào log; tránh giữ byte chứa bí mật lâu trong bộ nhớ. Với KMS/HSM, khóa có thể không cho xuất và ứng dụng phải dùng API mật mã phù hợp thay cho KeyGenerator/getEncoded thông thường.

## 5. Mục tiêu bảo mật và ranh giới bảo vệ

### 5.1. Tính bí mật

Mã hóa đối xứng giúp hạn chế việc đọc dữ liệu bởi bên không giữ khóa. Tuy nhiên, nếu khóa được hardcode cùng mã nguồn hoặc để trong cùng kho dữ liệu, đối thủ lấy được cả ciphertext và khóa vẫn có thể giải mã.

Các điểm cần bảo vệ:

- **At rest:** Dữ liệu, bản sao lưu, log và bản xuất phải được phân loại; khóa bí mật nên quản lý độc lập với ciphertext.
- **In transit:** Dùng TLS phù hợp để bảo vệ cả dữ liệu lẫn các API cấp phát/sử dụng khóa trong quá trình truyền.
- **In use:** Hạn chế thành phần nhận DEK dạng rõ, thời gian tồn tại trong bộ nhớ, quyền xem crash dump và hành vi ghi log.

**Mã hóa không thay thế authorization:** Một dịch vụ có quyền giải mã vẫn có thể làm lộ plaintext nếu tài khoản hoặc mã ứng dụng của nó bị chiếm quyền.

### 5.2. Tính toàn vẹn và xác thực

Các chế độ AEAD như AES-GCM có thể phát hiện sửa đổi trái phép đối với ciphertext và AAD khi xác minh tag đúng cách. Nhưng AEAD dùng **khóa đối xứng chung** nên bản thân nó không chứng minh công khai **ai trong số các chủ thể biết khóa** đã tạo bản mã. Khi cần xác minh nguồn gốc một thông điệp hoặc người ký với bên thứ ba, hệ thống có thể cần chữ ký số và cơ chế quản lý public/private key.

Chữ ký số, HMAC và mã hóa có xác thực giải quyết các mục tiêu có liên quan nhưng **khác nhau**. Không suy ra chữ ký số chỉ từ việc dữ liệu đã được mã hóa.

### 5.3. Tính sẵn sàng

Đánh mất khóa có thể khiến mọi bản mã phụ thuộc không giải mã được, ngay cả khi dữ liệu và máy chủ vẫn hoạt động. Cần thiết kế sao lưu/khôi phục khóa theo chính sách, độ sẵn sàng của KMS/HSM, thông tin key version và kiểm tra khôi phục định kỳ.

**Không được hủy khóa cũ** trước khi xác nhận đã xử lý các bản ghi, backup và dữ liệu lịch sử cần dùng nó. Tính sẵn sàng không đồng nghĩa với mở rộng quyền Decrypt; cần dự phòng trong ranh giới bảo vệ tương ứng.

## 6. Quản lý khóa đối xứng xuyên suốt vòng đời

| Giai đoạn | Việc cần làm | Sai sót cần tránh |
| --- | --- | --- |
| **Tạo (generation)** | Chọn AES-128/256 theo yêu cầu; sinh khóa bằng CSPRNG hoặc KMS/HSM | Sinh khóa từ timestamp, random thông thường hoặc mật khẩu thô |
| **Cấp phát (provisioning)** | Cấp cho đúng workload/tenant, xác thực đích nhận, dùng kênh an toàn | Gửi khóa dạng rõ qua chat/email hoặc nhúng vào image container |
| **Lưu trữ (storage)** | Quản lý key ID, thuật toán, version, trạng thái; wrap DEK khi cần | Lưu key dạng rõ cạnh ciphertext; log key trong lúc debug |
| **Sử dụng (usage)** | Kiểm tra quyền nghiệp vụ, sử dụng AEAD, nonce đúng quy tắc và AAD phù hợp | Cấp Decrypt toàn hệ thống; tái sử dụng nonce GCM |
| **Xoay vòng (rotation)** | Sinh khóa mới, chọn key version đúng, chuyển đổi dữ liệu hoặc rewrap theo tầng | Chỉ đổi alias mà quên dữ liệu cũ; hủy khóa cũ sớm |
| **Thu hồi/vô hiệu hóa** | Chặn quyền dùng khóa/phiên bị ảnh hưởng, kiểm tra cache và bản sao | Tưởng chỉ cần đổi mật khẩu quản trị là thu hồi được mọi bản sao khóa |
| **Hủy (destruction)** | Xác nhận hết phụ thuộc rồi hủy vật liệu khóa và bản sao theo chính sách | Xóa khóa khi còn dữ liệu cần phục hồi |

### 6.1. Tách khóa theo mục đích và phạm vi

Nên dùng khóa riêng cho những mục đích hoặc miền cần cách ly: production/development, các tenant, nhóm dữ liệu, chính sách lưu trữ và quyền truy cập. Không nhất thiết phải tạo một khóa cho mỗi byte dữ liệu; ranh giới hợp lý tùy chi phí vận hành và phạm vi sự cố chấp nhận được.

Ví dụ: Nếu DEK cho tenant A bị lộ, tách DEK và KEK có thể giúp tránh ảnh hưởng trực tiếp đến tenant B. Nếu một tài khoản KMS có quyền giải bọc DEK của **mọi tenant**, việc chia khóa vẫn chưa đủ vì quyền bị cấp quá rộng.

### 6.2. Xoay vòng không đồng nghĩa mã hóa lại ngay

Khi đổi **DEK**, các dữ liệu được mã hóa bởi DEK cũ cần được chuyển sang khóa mới nếu muốn ngừng phụ thuộc khóa cũ; thường yêu cầu giải mã và mã hóa lại dữ liệu theo quy trình được bảo vệ.

Khi chỉ đổi **KEK**, hệ thống có thể unwrap/rewrap các DEK đã được bọc dưới KEK cũ, tùy khả năng API. Ciphertext dữ liệu của DEK có thể giữ nguyên. Tuy nhiên, một số chính sách và sự cố đòi hỏi thay cả DEK; không nên coi việc chỉ rewrap là đủ trong mọi trường hợp.

## 7. Envelope encryption với KMS/HSM

Mã hóa đối xứng thường được triển khai bằng **envelope encryption** để không phải giữ một khóa AES dạng rõ cố định trong mã nguồn hay cơ sở dữ liệu.

**DEK (Data Encryption Key)** là khóa đối xứng trực tiếp mã hóa dữ liệu. **KEK (Key Encryption Key)** là khóa được dùng để wrap/unwrap DEK. KMS/HSM quản lý KEK và quyền gọi thao tác; nhiều hệ thống còn có các tầng root key nội bộ.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng Java
    participant KMS as KMS/HSM
    participant DB as Database
    App->>KMS: GenerateDataKey(KEK, encryptionContext)
    KMS-->>App: Plaintext DEK tạm thời + Wrapped DEK
    Note over App: AES-GCM mã hóa với nonce mới, AAD đúng bản ghi
    App->>DB: Lưu ciphertext, tag, nonce, wrappedDEK, keyId, version
    Note over App: Giảm thời gian tồn tại của DEK rõ
    App->>DB: Đọc ciphertext và metadata
    DB-->>App: Ciphertext + wrappedDEK + nonce + tag
    App->>KMS: Unwrap DEK theo danh tính và context
    KMS-->>App: Plaintext DEK nếu được cấp quyền
    Note over App: Giải mã, xác minh tag/AAD trước khi sử dụng
~~~

**Điểm quan trọng:**

1. Cơ sở dữ liệu giữ bản mã và **DEK đã wrap**, không nhất thiết giữ plaintext DEK.
2. Nếu thiết kế KMS trả plaintext DEK cho ứng dụng, bản rõ này vẫn xuất hiện **tạm thời trong RAM**; cần giảm thời gian sống và kiểm soát bộ nhớ/dump/log.
3. Chính sách KMS giới hạn thao tác trên KEK; **ứng dụng vẫn phải kiểm tra người dùng có quyền đọc bản ghi** trước khi xin giải bọc DEK.
4. Key ID/version, encryption context và AAD giúp chọn đúng khóa, đúng bản ghi và kiểm tra liên kết ngữ cảnh; các metadata này phải được bảo vệ, xác thực theo cách phù hợp.
5. Sử dụng KEK trong HSM không có nghĩa mọi thao tác giải mã đều diễn ra trong HSM. Khả năng xuất/không xuất DEK và vị trí thực thi phụ thuộc từng API/kiến trúc.

## 8. Kiểm soát truy cập và kiểm toán

Một ứng dụng biết dùng AES-GCM vẫn có thể không an toàn nếu mọi tài khoản dịch vụ đều có quyền giải mã.

Nên phân quyền theo **least privilege**:

- Dịch vụ ghi dữ liệu chỉ có quyền tạo DEK/mã hóa trong phạm vi cần thiết.
- Dịch vụ đọc chỉ được unwrap DEK khi đã xác thực danh tính và kiểm tra quyền bản ghi.
- Người quản trị KMS không mặc nhiên được xem plaintext hoặc xuất vật liệu khóa.
- Thao tác nhạy cảm như tạo chính sách, export key (nếu hỗ trợ), thay quyền và delete có quy trình phê duyệt thích hợp.

Log kiểm toán nên ghi **ai**, **làm gì**, **đối với key ID nào**, **khi nào**, **kết quả** và ngữ cảnh không nhạy cảm. Cảnh báo những bất thường như tần suất Decrypt tăng cao, workload mới truy cập khóa, thay đổi policy hoặc thao tác xóa khóa ngoài kế hoạch.

**Không ghi** plaintext, raw DEK, secret/private key, credential hoặc bản sao khóa vào log. Kiểm toán hỗ trợ phát hiện và điều tra; nó không thay thế kiểm tra quyền ngay khi thực hiện yêu cầu.

## 9. Tình huống thiết kế: mã hóa hồ sơ khách hàng nhiều tenant

Giả sử một nền tảng có tenant A và B, mỗi tenant lưu dữ liệu nhạy cảm. Mục tiêu là khi dữ liệu của A bị lộ ở tầng lưu trữ, kẻ tấn công không đọc được bản rõ, đồng thời việc cấp quyền cho A không mở quyền giải mã dữ liệu của B.

**Thiết kế đề xuất ở mức khái niệm:**

1. Tách miền khóa theo tenant hoặc nhóm dữ liệu cần cách ly; định danh KEK/DEK rõ ràng và gắn phiên bản.
2. Với bản ghi mới, tạo/nhận DEK theo chính sách và mã hóa bằng **AES-GCM** với nonce không trùng dưới cùng DEK.
3. Đặt AAD gắn bản mã với **tenant ID + record ID + schema version**; khi đọc, kiểm tra ngữ cảnh từ yêu cầu đã được xác thực và quyền dữ liệu thật.
4. Lưu ciphertext, nonce, tag, wrapped DEK, key ID, version và metadata cần thiết. Giữ khóa dạng rõ ngoài nơi lưu dữ liệu.
5. Phân quyền dịch vụ trên KMS theo tenant/namespace; ghi log thao tác nhưng không ghi dữ liệu bí mật.
6. Định kỳ thử khôi phục và triển khai kế hoạch rotation cho DEK/KEK; đánh giá tác động đến bản sao lưu và dữ liệu lịch sử.

**Kiểm tra các trường hợp lỗi:**

| Tình huống | Kết quả hệ thống cần đạt |
| --- | --- |
| Sửa một byte ciphertext hoặc tag | Xác thực AEAD thất bại, không trả plaintext |
| Đổi tenant ID/record ID nhưng giữ ciphertext cũ | Nếu AAD được ràng buộc đúng, xác thực thất bại hoặc kiểm tra quyền từ chối |
| Dùng sai phiên bản DEK | Không giải mã được; có lỗi rõ ràng và cơ chế chọn lại key ID/version hợp lệ |
| Tài khoản service A yêu cầu unwrap khóa tenant B | KMS và/hoặc tầng kiểm tra quyền từ chối |
| KEK hiện tại bị vô hiệu hóa | Quyết định theo chính sách: từ chối dùng khóa hoặc sử dụng đường khôi phục được phê duyệt; không tự bỏ kiểm tra |
| Gỡ bỏ key version cũ trước khi chuyển dữ liệu | Kiểm thử phải phát hiện bản ghi không còn giải mã được; chưa được hủy khóa |

Trong trường hợp tài khoản ứng dụng A bị chiếm quyền nhưng vẫn có quyền hợp lệ đọc dữ liệu A, **mã hóa at rest không ngăn hoàn toàn** đối thủ lấy plaintext qua chính ứng dụng. Vì vậy, phải kết hợp phân quyền người dùng, giới hạn truy vấn, giám sát, khóa theo phạm vi và xử lý sự cố.

## 10. Các lỗi thường gặp và cách tránh

| Lỗi | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Dùng AES-ECB cho dữ liệu ứng dụng | Lộ mẫu dữ liệu lặp lại | Dùng AEAD như AES-GCM hoặc thiết kế phù hợp |
| Dùng AES-CBC/CTR mà không xác thực bản mã | Bản mã có thể bị chỉnh sửa không được phát hiện đúng cách | Sử dụng AEAD hoặc cơ chế xác thực đúng chuẩn |
| Tái sử dụng nonce trong AES-GCM | Có thể phá vỡ bí mật và tính xác thực | Quản lý nonce duy nhất theo khóa, giới hạn lượt sử dụng và rotate |
| Tưởng nonce phải bí mật | Thiết kế lưu trữ phức tạp mà không giải quyết rủi ro chính | Nonce có thể công khai, nhưng phải đáp ứng quy tắc duy nhất/ngẫu nhiên của mode |
| Hardcode key trong source code | Lộ qua Git, build, log, máy trạm | Sinh khóa an toàn và sử dụng KMS/HSM/secret management phù hợp |
| Đệm mật khẩu thành 32 byte để dùng làm AES-256 | Entropy thấp, dễ đoán | KDF phù hợp cho mật khẩu, ưu tiên CSPRNG cho khóa hệ thống |
| Cho phép Decrypt trên mọi KEK/tenant | Một workload bị chiếm ảnh hưởng nhiều miền | Tách quyền, khóa, môi trường và giới hạn context |
| Không giữ key ID/version | Không biết dùng khóa nào để giải mã dữ liệu cũ | Định dạng ciphertext envelope có version và metadata |
| Tự hủy khóa cũ ngay khi rotate | Mất khả năng giải mã bản ghi hoặc bản sao lưu cũ | Kiểm kê phụ thuộc, migration và kiểm thử đọc trước khi hủy |
| Coi ciphertext hợp lệ là chống replay | Bản mã cũ vẫn có tag hợp lệ | Ràng buộc trạng thái, số thứ tự/phiên bản và kiểm tra ở tầng ứng dụng |

## 11. Checklist khi review một ứng dụng dùng symmetric encryption

Hãy tự kiểm tra:

1. **Thuật toán:** Có sử dụng thuật toán và mode phù hợp, ưu tiên AEAD, tránh ECB và các thiết kế tự ghép nguy hiểm?
2. **Key length:** Độ dài AES và độ mạnh khóa đáp ứng yêu cầu, được hỗ trợ bởi nền tảng và chính sách?
3. **Sinh khóa:** Khóa được tạo bằng CSPRNG/KMS/HSM hoặc KDF đúng cách, không đến từ mật khẩu thô hoặc giá trị dự đoán?
4. **Nonce/IV:** Có quy tắc duy nhất/không trùng cho từng khóa và giới hạn lượt mã hóa phù hợp?
5. **Xác thực:** Tag và AAD được xác minh trước khi trả plaintext, đồng thời có kiểm soát replay nếu nghiệp vụ yêu cầu?
6. **Lưu trữ:** Dữ liệu có lưu ciphertext, nonce, tag, key ID/version, metadata và wrapped DEK đúng cấu trúc?
7. **Phân quyền:** Người dùng, workload và KMS có được giới hạn quyền theo tenant, môi trường và mục đích thực tế?
8. **Vòng đời:** Rotation, thu hồi, hủy, sao lưu và khôi phục khóa có kế hoạch, thử nghiệm và log tương ứng?
9. **Ứng phó sự cố:** Khi DEK/KEK bị lộ, có thể xác định dữ liệu phụ thuộc, ngừng dùng khóa cũ và mã hóa lại khi cần?
10. **Kiểm toán:** Ghi nhận thao tác tạo/dùng/xóa khóa và cảnh báo bất thường mà không ghi lộ bí mật?

## 12. Ghi nhớ

- **Mã hóa đối xứng** dùng cùng một khóa bí mật để mã hóa và giải mã; mạnh ở hiệu năng và khả năng bảo vệ lượng dữ liệu lớn.
- **AES là thuật toán khối**, còn **GCM là mode mã hóa có xác thực**. AES-256 đề cập đến **độ dài khóa**, không phải kích thước nonce hoặc tag.
- **Nonce không cần bí mật nhưng không được trùng dưới cùng khóa GCM**. Khi tag/AAD không hợp lệ, phải từ chối plaintext.
- **Bảo vệ key quan trọng ngang thuật toán:** dùng CSPRNG, KMS/HSM, envelope encryption, phân quyền tối thiểu, key version, rotation và kiểm toán.
- **Mật mã đối xứng không thay thế chữ ký số, quyền truy cập dữ liệu hoặc cơ chế chống replay**. Kết hợp đúng các lớp bảo vệ để đạt mục tiêu của hệ thống.

Một hệ thống symmetric encryption an toàn không kết thúc ở câu lệnh mã hóa. Nó phải biết **khóa được tạo ở đâu, ai được phép sử dụng, làm sao phát hiện bản mã bị sửa, cách đọc dữ liệu qua nhiều phiên bản khóa và phải làm gì khi khóa bị lộ hoặc bị hủy**.
