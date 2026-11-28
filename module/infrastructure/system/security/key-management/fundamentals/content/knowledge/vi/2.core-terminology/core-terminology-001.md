# Key (Khóa mật mã)

## 1. Key là gì?

**Key (khóa mật mã)** là giá trị được thuật toán mật mã sử dụng để thực hiện một thao tác như mã hóa, giải mã, ký số, xác minh chữ ký hoặc dẫn xuất bí mật dùng chung. Thuật toán thường được công khai; tính an toàn phụ thuộc vào thuật toán được thiết kế đúng, khóa đủ mạnh và cách quản lý khóa.

Ví dụ, trong hệ thống lưu hồ sơ khách hàng:

- Dữ liệu được mã hóa bằng AES-GCM với một **khóa bí mật đối xứng**. Người có quyền giải mã cần đúng khóa ấy.
- Dịch vụ ký một thông điệp bằng **khóa riêng tư (private key)**; bên nhận dùng **khóa công khai (public key)** tương ứng để xác minh chữ ký.
- Một hệ thống quản lý khóa (KMS) hoặc mô-đun bảo mật phần cứng (HSM) có thể giữ khóa gốc và cho phép ứng dụng sử dụng khóa qua thao tác được cấp quyền, hạn chế việc lộ vật liệu khóa.

Một khóa không đồng nghĩa với mật khẩu, chứng chỉ số, mã định danh khóa hay thuật toán mã hóa. Những khái niệm này liên quan nhau nhưng có chức năng và rủi ro khác nhau.

> **Nguyên tắc cốt lõi:** Bảo vệ dữ liệu đã mã hóa sẽ thất bại nếu kẻ tấn công lấy được khóa giải mã tương ứng, hoặc có quyền yêu cầu dịch vụ giải mã thay mình. Vì vậy, bảo mật khóa bao gồm cả bảo vệ giá trị khóa **và** kiểm soát quyền sử dụng khóa.

## 2. Những thuộc tính cần hiểu về một khóa

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| Vật liệu khóa (key material) | Các bit thật sự dùng trong phép toán mật mã; có thể là bí mật hoặc công khai tùy loại khóa | 256 bit được sinh ngẫu nhiên cho AES-256 |
| Thuật toán | Quy định khóa được sử dụng như thế nào | AES-256-GCM, Ed25519, RSA-OAEP |
| Mục đích sử dụng (key usage) | Phép toán được phép thực hiện | Encrypt/decrypt, sign/verify, wrap/unwrap |
| Mã định danh (key ID) | Tên hoặc tham chiếu để tìm khóa | ID của khóa trong KMS |
| Phiên bản (key version) | Phân biệt vật liệu khóa trước và sau khi xoay vòng | v1, v2 |
| Trạng thái | Khóa còn được sử dụng hay đã bị vô hiệu hóa, thu hồi hoặc hủy | Active, disabled, pending deletion |
| Chủ thể quản lý và quyền truy cập | Ai được tạo, dùng, xoay vòng, xem metadata hoặc hủy khóa | Dịch vụ thanh toán chỉ có quyền giải mã cho một phạm vi |

**Key ID/alias không phải key material**: biết tên của khóa không mặc nhiên có quyền thực hiện phép toán với khóa. Ngược lại, chỉ che giấu Key ID cũng không phải biện pháp bảo vệ khóa.

Độ dài khóa và mức an toàn là hai khái niệm cần phân biệt:

- AES-128 sử dụng khóa 128 bit; AES-256 sử dụng khóa 256 bit. Độ dài này nói về không gian khóa của thuật toán đối xứng, không bảo đảm toàn hệ thống đạt mức an toàn tương ứng nếu nonce bị tái sử dụng, khóa bị lộ hoặc quyền truy cập cấu hình sai.
- Khóa RSA dài 3072 bit không thể so sánh trực tiếp với khóa AES dài 256 bit. Kích thước khóa của các họ thuật toán khác nhau không biểu thị cùng một độ mạnh bảo mật.
- Khóa phải được tạo bằng **bộ sinh số ngẫu nhiên dùng cho mật mã (CSPRNG)** hoặc quy trình dẫn xuất khóa thích hợp. Một chuỗi dễ đoán dù dài vẫn là khóa yếu.

## 3. Phân loại khóa theo cách sử dụng

| Loại khóa | Ai cần giữ bí mật? | Vai trò điển hình | Lưu ý |
|---|---|---|---|
| **Symmetric key** (khóa đối xứng) | Mọi bên được quyền mã hóa/giải mã | AES-GCM bảo vệ bản ghi, tệp, dữ liệu lưu trữ | Cùng khóa phục vụ cả mã hóa và giải mã; khó phân phối an toàn khi có nhiều bên |
| **Public key** (khóa công khai) | Không cần bí mật, nhưng cần xác thực đúng chủ sở hữu | Mã hóa đến người nhận, xác minh chữ ký, trao đổi khóa | Công khai không có nghĩa là có thể tin bất kỳ khóa nào được gửi đến |
| **Private key** (khóa riêng tư) | Chủ sở hữu hoặc hệ thống bảo vệ khóa | Giải mã trong sơ đồ phù hợp; ký số; tham gia thỏa thuận khóa | Lộ private key có thể dẫn đến giả mạo hoặc mất bí mật tùy chức năng |
| **Data Encryption Key (DEK)** | Chỉ thành phần cần xử lý dữ liệu | Mã hóa dữ liệu thực tế, thường bằng AES-GCM | Có thể là khóa riêng cho đối tượng, tệp, phiên hoặc nhóm dữ liệu |
| **Key Encryption Key (KEK)** | Dịch vụ/quy trình quản lý khóa được ủy quyền | Mã hóa hoặc bọc (wrap) DEK | Nên có phạm vi quyền và vòng đời riêng với DEK |
| **Root/master key** | Miền tin cậy quản lý khóa | Bảo vệ các khóa cấp dưới | Tên gọi phụ thuộc hệ thống; không phải cứ gọi là master key thì là vật liệu khóa xuất ra được |

**Cặp khóa bất đối xứng** bao gồm public key và private key có quan hệ toán học. Không phải mọi cặp khóa đều hỗ trợ mọi phép toán:

- **Ed25519** thường dùng cho chữ ký số; không dùng cặp khóa Ed25519 để mã hóa dữ liệu bằng AES hoặc RSA.
- **X25519** thường dùng trong thỏa thuận khóa: kết hợp khóa riêng của một bên và khóa công khai của bên kia để tính bí mật chung, rồi dùng KDF thích hợp để tạo khóa phục vụ giao thức.
- **RSA-OAEP** là sơ đồ mã hóa bất đối xứng; **RSA-PSS** là sơ đồ ký số. Không đánh đồng hai mục đích chỉ vì đều liên quan đến RSA.

Một cặp khóa có thể được mô tả bằng thuật toán, mục đích, danh tính chủ sở hữu, chính sách truy cập và thời hạn sử dụng. Metadata giúp quản trị; vật liệu private key vẫn phải được bảo vệ riêng.

## 4. Key khác gì những thuật ngữ dễ nhầm?

| Thuật ngữ | Khác với key ở điểm nào? | Hậu quả khi nhầm lẫn |
|---|---|---|
| **Password/passphrase** | Bí mật do người dùng đặt, thường có entropy thấp hơn khóa sinh ngẫu nhiên | Dùng thẳng mật khẩu làm khóa AES khiến khóa dễ bị đoán |
| **Salt** | Giá trị thường công khai, dùng trong hàm dẫn xuất từ mật khẩu để chống việc dùng chung kết quả và hỗ trợ chống bảng tra cứu | Giữ kín salt không thay thế việc chọn KDF phù hợp |
| **IV/nonce** | Giá trị phụ trợ cần thỏa yêu cầu riêng của chế độ mã hóa; với AES-GCM, nonce phải **không trùng cho cùng một khóa** | Tái sử dụng nonce với cùng khóa GCM có thể làm lộ thông tin và phá tính xác thực |
| **AAD** (Additional Authenticated Data) | Dữ liệu không mã hóa nhưng được kiểm tra tính toàn vẹn trong AEAD | Không kiểm tra đúng AAD có thể gây nhầm phạm vi bản ghi hoặc tenant |
| **Digital certificate** | Chứng chỉ liên kết public key với một danh tính thông qua cơ chế tin cậy/chữ ký | Nhận public key không được xác thực có thể dẫn đến tấn công thay thế khóa |
| **Key ID / alias** | Tham chiếu đến khóa, không phải khóa | Thấy ID không có nghĩa sở hữu quyền giải mã |
| **Access token** | Thông tin ủy quyền truy cập API; có thể được ký bằng một khóa nhưng bản thân token không phải khóa ký | Rò token và rò khóa ký đòi hỏi phương án ứng phó khác nhau |

Khi cần tạo khóa từ mật khẩu, dùng **password-based KDF** phù hợp như Argon2id, scrypt hoặc PBKDF2 được cấu hình theo bối cảnh, với salt duy nhất và tham số đủ tốn tài nguyên. Khi đã có bí mật mật mã chất lượng cao và cần dẫn xuất nhiều khóa theo mục đích, dùng KDF như HKDF với phân tách ngữ cảnh. Không băm một mật khẩu một lần rồi coi kết quả là khóa mạnh.

## 5. Khóa tham gia các phép toán như thế nào?

### 5.1. Mã hóa đối xứng và tính toàn vẹn

Với **AES-GCM** (một chế độ mã hóa có xác thực, AEAD), đầu vào thường gồm khóa bí mật, nonce và bản rõ; có thể có AAD. Đầu ra gồm bản mã và thẻ xác thực (authentication tag).

~~~text
AES-GCM.encrypt(key, nonce, plaintext, aad)
    -> ciphertext + authentication_tag

AES-GCM.decrypt(key, nonce, ciphertext, tag, aad)
    -> plaintext, hoặc lỗi xác thực
~~~

Để giải mã thành công, bên nhận phải có đúng khóa, nonce, tag và AAD. **Nonce thường được lưu kèm bản mã, không cần giữ bí mật**, nhưng phải tuân thủ quy tắc duy nhất đối với cùng khóa. Nonce 96 bit và tag 128 bit là cấu hình phổ biến của AES-GCM; chọn cách sinh nonce và giới hạn số lượng bản mã theo thiết kế hệ thống để tránh va chạm. Không dùng lại nonce với cùng khóa kể cả khi bản rõ khác nhau.

### 5.2. Mã hóa bất đối xứng

Trong một sơ đồ mã hóa bất đối xứng phù hợp, người gửi dùng **public key của người nhận** để mã hóa một dữ liệu nhỏ hoặc khóa phiên; người nhận dùng **private key** để giải mã. Hệ thống thực tế thường kết hợp bất đối xứng với đối xứng để xử lý dữ liệu lớn hiệu quả hơn.

Điểm dễ bỏ sót là **tính xác thực của public key**: phải xác nhận public key thật sự thuộc về người nhận (chứng chỉ, PKI, kênh xác thực hoặc cơ chế tin cậy khác). Nếu không, kẻ tấn công có thể đưa public key của họ thay vào.

### 5.3. Chữ ký số

~~~text
signature = Sign(private_key, message)
valid     = Verify(public_key, message, signature)
~~~

Chữ ký số kiểm tra tính toàn vẹn và nguồn gốc theo mô hình tin cậy của khóa; **không tự mã hóa nội dung để giữ bí mật**. Khóa ký cần được bảo vệ nghiêm ngặt vì người chiếm được private key có thể tạo chữ ký giả mạo. Khi phát hiện lộ khóa ký, cần thu hồi lòng tin, thay khóa, cập nhật nơi xác minh và đánh giá các chữ ký đã phát hành.

### 5.4. Thỏa thuận khóa và dẫn xuất khóa

Trong các giao thức như (EC)DH, hai bên đóng góp khóa riêng và trao đổi khóa công khai để tính bí mật chung. Bí mật đó thường được đưa qua **KDF**, kết hợp ngữ cảnh giao thức, để có các khóa phiên thích hợp. Không nên lấy trực tiếp chuỗi đầu ra trung gian làm khóa ứng dụng khi giao thức yêu cầu dẫn xuất.

## 6. Vòng đời của một key

Quản lý khóa hiệu quả bắt đầu trước khi khóa được dùng và chỉ kết thúc khi không còn bản sao hay khả năng sử dụng trái phép.

~~~mermaid
flowchart LR
    A["Sinh hoặc dẫn xuất khóa"] --> B["Cấp phát và kích hoạt"]
    B --> C["Sử dụng và giám sát"]
    C --> D["Xoay vòng / thay khóa"]
    D --> E["Ngừng dùng để tạo dữ liệu mới"]
    E --> F["Thu hồi / vô hiệu hóa"]
    F --> G["Hủy theo chính sách lưu giữ"]
    D --> C
~~~

| Giai đoạn | Việc cần thực hiện | Câu hỏi cần trả lời |
|---|---|---|
| Tạo (generation) | Sinh khóa bằng CSPRNG/HSM hoặc dẫn xuất bằng KDF phù hợp; gán mục đích và thuật toán | Khóa có đủ mạnh và tạo trong môi trường tin cậy không? |
| Cấp phát (distribution/provisioning) | Trao khóa hoặc quyền sử dụng khóa qua kênh bảo mật và được xác thực | Có ai nhận được khóa ngoài đối tượng được cấp quyền không? |
| Lưu trữ (storage) | Giữ khóa trong KMS/HSM, kho bí mật hoặc cơ chế bảo vệ thích hợp; hạn chế bản sao | Khóa xuất hiện ở cấu hình, log, bản sao lưu hay repository không? |
| Sử dụng (usage) | Phân quyền theo thao tác, xác thực dịch vụ gọi, giới hạn phạm vi sử dụng, ghi sự kiện kiểm toán | Ai được gọi decrypt, sign, unwrap? |
| Xoay vòng (rotation) | Tạo phiên bản mới, chuyển tác vụ tạo mới sang phiên bản đó, lên kế hoạch xử lý dữ liệu cũ | Bản mã cũ sẽ được giải mã bằng phiên bản nào? |
| Thu hồi/vô hiệu hóa (revocation/disablement) | Chặn sử dụng khóa khi lộ, thay đổi nhân sự, quyền hoặc chính sách | Có đường cấp quyền phụ, cache hay bản sao nào chưa được kiểm soát không? |
| Lưu giữ và hủy (retention/destruction) | Giữ khóa cũ đúng thời gian cần giải mã dữ liệu còn hợp lệ; hủy có kiểm soát khi hết nhu cầu | Bản sao lưu, bản sao dự phòng và dữ liệu lưu trữ dài hạn xử lý ra sao? |

**Xoay vòng ≠ thu hồi ≠ hủy:**

- **Xoay vòng**: bắt đầu sử dụng vật liệu khóa mới theo chính sách hoặc sau sự cố. Có thể vẫn cần phiên bản cũ để đọc dữ liệu lịch sử.
- **Thu hồi/vô hiệu hóa**: ngăn khóa tiếp tục được sử dụng. Với public key đã phân phối, cần cập nhật các bên kiểm tra chữ ký/chứng chỉ; chỉ vô hiệu hóa trong một kho nội bộ chưa chắc ngăn được mọi bên ngoài tiếp tục tin khóa.
- **Hủy**: làm vật liệu khóa không còn khả dụng. Nếu dữ liệu chỉ tồn tại dưới dạng bản mã phụ thuộc khóa đã hủy thì dữ liệu đó có thể mất vĩnh viễn. Hủy khóa để xóa dữ liệu bằng mật mã (cryptographic erasure) chỉ đáng tin khi đã đánh giá các bản sao, cache, backup và nơi còn giữ bản rõ.

Mỗi khóa cần một **cryptoperiod** (khoảng thời gian sử dụng được quy định) phù hợp với mục đích, rủi ro và yêu cầu vận hành. Không có chu kỳ xoay vòng duy nhất đúng cho mọi loại khóa.

## 7. Key trong kiến trúc KMS, HSM và envelope encryption

**KMS (Key Management Service/System)** quản lý vòng đời và chính sách sử dụng khóa, thường cung cấp API, IAM, kiểm toán, rotation và tích hợp ứng dụng. **HSM (Hardware Security Module)** cung cấp môi trường phần cứng được thiết kế để bảo vệ khóa và thực hiện phép toán mật mã; KMS có thể sử dụng HSM bên dưới. Không phải mọi khóa trong KMS đều được phép xuất vật liệu thô.

**Envelope encryption** (mã hóa phong bì) dùng phân cấp khóa để mã hóa dữ liệu ở quy mô lớn:

1. Ứng dụng được ủy quyền yêu cầu KMS tạo DEK hoặc tạo DEK bằng nguồn ngẫu nhiên thích hợp. Trong mô hình KMS GenerateDataKey, dịch vụ có thể trả về **DEK dạng rõ** tạm thời cùng **DEK đã được mã hóa** dưới khóa quản lý.
2. Ứng dụng dùng DEK dạng rõ để mã hóa dữ liệu cục bộ bằng AEAD, chẳng hạn AES-GCM.
3. Ứng dụng lưu **ciphertext + nonce + tag + encrypted DEK + key ID/version + metadata cần thiết**. DEK dạng rõ chỉ tồn tại trong bộ nhớ trong thời gian cần thiết; không lưu hay log nó.
4. Khi đọc, dịch vụ có quyền gọi KMS để giải mã/unwrap encrypted DEK, rồi dùng DEK vừa khôi phục để giải mã dữ liệu và kiểm tra tag/AAD.

~~~mermaid
flowchart TB
    K["KMS / KEK được bảo vệ"] -->|"Tạo hoặc bọc DEK"| W["Encrypted DEK"]
    D["DEK tạm trong bộ nhớ"] -->|"AES-GCM"| C["Dữ liệu mã hóa + nonce + tag"]
    K -.->|"Cấp DEK tạm theo quyền"| D
    W --> S["Kho dữ liệu"]
    C --> S
~~~

Ví dụ một hồ sơ trong kho đối tượng có thể lưu:

~~~yaml
keyId: kms-key-for-customer-records
keyVersion: v3
encryptedDataKey: "<base64 cua DEK da boc>"
nonce: "<base64 nonce AES-GCM>"
ciphertextWithTag: "<base64 ban ma va tag>"
algorithm: AES-256-GCM
~~~

Đây là **metadata minh họa**, không phải định dạng chuẩn chung của mọi KMS. Hệ thống thực tế phải ràng buộc đúng ID khóa, mục đích, tenant và ngữ cảnh mã hóa; với AEAD, các trường nhận dạng quan trọng có thể được đưa vào AAD để chống tráo đổi dữ liệu giữa các ngữ cảnh.

**Xoay vòng KEK không nhất thiết đòi hỏi mã hóa lại toàn bộ dữ liệu**: trong kiến trúc phù hợp, có thể giải bọc DEK được bảo vệ bởi KEK cũ rồi bọc lại bằng KEK mới (rewrap), trong khi bản mã dữ liệu giữ nguyên. **Thay DEK** thường yêu cầu giải mã dữ liệu bằng DEK cũ và mã hóa lại bằng DEK mới. Nếu nhà cung cấp KMS duy trì các phiên bản khóa cũ để giải mã, phải kiểm tra chính sách và cách quản lý phiên bản của dịch vụ cụ thể.

HSM/KMS không thay cho thiết kế quyền truy cập: một dịch vụ có quyền decrypt rộng, bị chiếm quyền hoặc bị lạm dụng vẫn có thể làm lộ bản rõ dù key material không bao giờ rời HSM.

## 8. Ví dụ Java: một khóa AES-GCM được tạo và sử dụng

Ví dụ sau minh họa **sinh khóa đối xứng và mã hóa có xác thực trong một lần chạy** bằng Java Cryptography Architecture (JCA). Khóa chỉ nằm trong bộ nhớ; đây là ví dụ học thuật, **không** phải giải pháp lưu khóa bền vững cho ứng dụng thực tế.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class KeyExample {
    public static void main(String[] args) throws Exception {
        // Sinh 256 bit khóa từ nguồn ngẫu nhiên phù hợp cho mật mã.
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey dek = generator.generateKey();

        // GCM yêu cầu nonce không trùng với cùng một khóa.
        byte[] nonce = new byte[12]; // 96 bit
        new SecureRandom().nextBytes(nonce);

        byte[] aad = "tenant=42;record=17".getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Du lieu can bao ve".getBytes(StandardCharsets.UTF_8);

        Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
        encryptor.init(Cipher.ENCRYPT_MODE, dek, new GCMParameterSpec(128, nonce));
        encryptor.updateAAD(aad);
        byte[] ciphertextWithTag = encryptor.doFinal(plaintext);

        // Khi đọc lại phải cung cấp đúng khóa, nonce và AAD.
        Cipher decryptor = Cipher.getInstance("AES/GCM/NoPadding");
        decryptor.init(Cipher.DECRYPT_MODE, dek, new GCMParameterSpec(128, nonce));
        decryptor.updateAAD(aad);
        byte[] recovered = decryptor.doFinal(ciphertextWithTag);

        if (!Arrays.equals(plaintext, recovered)) {
            throw new IllegalStateException("Decryption mismatch");
        }
        System.out.println("AES-GCM round-trip OK");
    }
}
~~~

Điểm cần rút ra từ đoạn mã:

- **Khóa** là biến dek kiểu SecretKey; nonce, AAD và bản mã là những thành phần khác.
- Bên nhận phải dùng đúng **cùng một khóa** để giải mã AES-GCM. Thay khóa, nonce, AAD hoặc sửa bản mã/tag thường khiến giải mã thất bại do lỗi xác thực.
- Bản mã phải được lưu với nonce và tag (trong JCA, kết quả doFinal thường chứa bản mã kèm tag). Không lưu dek dạng rõ cùng bản mã trong hệ thống sản xuất.
- Khi cần mã hóa nhiều thông điệp bằng cùng khóa, phải có chiến lược bảo đảm nonce duy nhất và giới hạn vận hành phù hợp; sinh ngẫu nhiên 96 bit có xác suất va chạm tăng theo số lần sử dụng, nên không xem là đảm bảo tuyệt đối ở mọi quy mô.
- Khi triển khai thực tế, ứng dụng cần KMS/HSM hoặc cơ chế quản lý khóa tương đương, phân quyền, quản lý phiên bản, kế hoạch phục hồi và xóa dữ liệu nhạy cảm khỏi bộ nhớ trong giới hạn kỹ thuật cho phép.

## 9. Thiết kế kiểm soát truy cập và kiểm toán quanh key

Khóa thường được bảo vệ qua **quyền thực hiện thao tác** thay vì cho mọi ứng dụng đọc các byte thô. Một chính sách tốt nên chỉ rõ:

- **Ai** được gọi: danh tính workload/dịch vụ, con người hoặc vai trò có xác thực, không chia sẻ một tài khoản quản trị cho mọi ứng dụng.
- **Được làm gì**: phân biệt create, encrypt, decrypt, sign, verify, rotate, disable, schedule deletion và quản trị policy. Người được dùng khóa không mặc nhiên được đổi chính sách hoặc xóa khóa.
- **Với khóa nào và trong ngữ cảnh nào**: khóa dành cho sản xuất không dùng chung tùy tiện với môi trường thử nghiệm; tách tenant, ứng dụng và mục đích theo nhu cầu rủi ro.
- **Kiểm tra ra sao**: ghi nhật ký hoạt động KMS/HSM gồm danh tính gọi, thao tác, key ID, thời gian, kết quả và ngữ cảnh được phép; không ghi private key, DEK dạng rõ, mật khẩu hoặc bản rõ nhạy cảm vào log.

Chính sách **least privilege** (đặc quyền tối thiểu), phân tách nhiệm vụ quản trị và sử dụng khóa, cảnh báo thao tác bất thường, giới hạn tốc độ và rà soát quyền định kỳ đều quan trọng. Log mã hóa/giải mã có thể chứa metadata nhạy cảm, nên bản thân hệ thống kiểm toán cũng cần được kiểm soát truy cập và thời hạn lưu giữ phù hợp.

## 10. Rủi ro khi quản lý key sai

| Sai lầm | Hệ quả | Cách phòng tránh |
|---|---|---|
| Hard-code khóa trong source, tệp cấu hình hoặc image | Người đọc repository, artifact hay backup có thể chiếm khóa | Cấp quyền dùng khóa qua KMS/secret store; quét và xử lý bí mật rò rỉ |
| Log hoặc truyền DEK/private key dạng rõ không cần thiết | Mở thêm đường rò rỉ ngoài vùng bảo vệ chính | Hạn chế xuất khóa, dùng TLS, chặn log và xóa bản sao tạm |
| Tái sử dụng nonce với cùng khóa AES-GCM | Có thể phá bí mật và xác thực của dữ liệu | Thiết kế nonce duy nhất cho từng lần mã hóa với mỗi khóa |
| Dùng một khóa cho nhiều tenant hoặc mục đích không liên quan | Sự cố ở một phạm vi lan sang phạm vi khác | Phân tách khóa, chính sách và ngữ cảnh dẫn xuất |
| Chỉ đổi Key ID nhưng giữ nguyên key material | Không giải quyết lộ vật liệu khóa | Xác minh rotation thực sự tạo vật liệu/phiên bản mới |
| Hủy khóa cũ trước khi chuyển đổi dữ liệu | Không đọc được bản mã cũ, gây mất dữ liệu | Kiểm kê dữ liệu, rewrap/re-encrypt, diễn tập khôi phục trước khi hủy |
| Không có quy trình thu hồi khóa bị lộ | Kẻ tấn công tiếp tục giải mã hoặc giả mạo chữ ký | Vô hiệu hóa, thay khóa, phân phối thông tin thu hồi và điều tra |
| Tin public key chưa được xác thực | Có thể mã hóa cho nhầm người hoặc xác minh chữ ký sai đối tượng | Xác thực chứng chỉ/khóa và ràng buộc danh tính |
| KMS cấp quyền decrypt quá rộng | Kẻ có quyền ứng dụng có thể yêu cầu giải mã hàng loạt | Giới hạn phạm vi và quyền, theo dõi bất thường, tách nhiệm vụ |
| Mất backup khóa hoặc giữ bản sao không kiểm soát | Mất dữ liệu hoặc tồn tại khóa tưởng đã hủy | Backup được bảo vệ, kiểm thử phục hồi, quản lý mọi bản sao |

Khi nghi khóa đã lộ, chỉ tạo khóa mới là chưa đủ. Cần xác định dữ liệu/chữ ký nào chịu ảnh hưởng, chặn quyền tiếp tục sử dụng khóa cũ, chuyển đổi dữ liệu hoặc xác thực, xử lý cache/bản sao và giám sát dấu hiệu lạm dụng. Mức độ khẩn cấp tùy loại khóa: mất private key ký số gây rủi ro giả mạo khác với mất DEK mã hóa dữ liệu.

## 11. Ví dụ thiết kế: hệ thống lưu hồ sơ nhiều khách hàng

Giả sử ứng dụng lưu hàng triệu hồ sơ thuộc nhiều tenant:

1. Mỗi hồ sơ hoặc nhóm hồ sơ có DEK được sinh bằng CSPRNG, theo ranh giới cô lập đã chọn; ứng dụng dùng AES-GCM để mã hóa.
2. DEK được KMS bảo vệ bằng KEK, còn bản mã, nonce, tag, encrypted DEK và phiên bản được lưu ở kho dữ liệu.
3. Danh tính dịch vụ chỉ được sử dụng các thao tác giải bọc DEK cần thiết cho tenant và môi trường của mình; yêu cầu giải mã gắn với việc kiểm tra quyền truy cập hồ sơ.
4. Tenant ID và record ID được ràng buộc bằng AAD hoặc ngữ cảnh mã hóa được xác thực để hạn chế tráo đổi bản mã giữa các hồ sơ.
5. Sự kiện sử dụng khóa được kiểm toán. Khi xoay KEK, hệ thống hỗ trợ rewrap DEK và giữ khả năng truy cập dữ liệu cũ theo kế hoạch; khi lộ DEK, hệ thống đánh giá tập hồ sơ liên quan để mã hóa lại.

Thiết kế này cho thấy **khóa không phải một chuỗi bí mật nằm rời rạc**. Khóa là một tài sản được gắn với thuật toán, mục đích, danh tính, phiên bản, quyền truy cập và vòng đời.

## 12. Tự kiểm tra

**Câu 1.** Bản mã AES-GCM đi kèm nonce. Có cần giữ kín nonce như khóa không?

**Trả lời:** Không nhất thiết giữ bí mật nonce. Điều bắt buộc là không được lặp nonce với cùng khóa và phải đảm bảo tính toàn vẹn/cấu trúc của dữ liệu liên quan.

**Câu 2.** Xoay KEK có luôn bắt buộc mã hóa lại toàn bộ dữ liệu gốc không?

**Trả lời:** Không. Với envelope encryption phù hợp, có thể rewrap DEK dưới KEK mới; thay DEK mới thường đòi hỏi mã hóa lại dữ liệu.

**Câu 3.** Nếu private key nằm trong HSM thì ứng dụng có chắc chắn không làm lộ bản rõ không?

**Trả lời:** Không. Ứng dụng được quyền giải mã hoặc ký có thể bị lạm dụng. Vẫn phải giới hạn thao tác, xác thực người gọi và kiểm toán.

**Câu 4.** Đổi tên khóa từ v1 sang v2 có được xem là rotation không?

**Trả lời:** Không nếu chỉ đổi nhãn. Rotation cần thay vật liệu khóa hoặc phiên bản mật mã theo cơ chế thực tế và kế hoạch chuyển đổi tương ứng.

**Câu 5.** Chữ ký số có làm thông điệp trở nên bí mật không?

**Trả lời:** Không. Chữ ký số hỗ trợ xác thực và toàn vẹn; bí mật nội dung cần cơ chế mã hóa thích hợp.

**Ghi nhớ:** Khi gặp thuật ngữ **key**, hãy hỏi: khóa này là loại nào, dùng cho phép toán gì, ai có quyền sử dụng, vật liệu khóa nằm ở đâu, phiên bản hiện tại là gì, và điều gì xảy ra khi khóa bị lộ, hết hạn hoặc bị hủy? Đó là nền tảng để kết nối mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, phân quyền và kiểm toán trong một hệ thống quản lý khóa an toàn.
