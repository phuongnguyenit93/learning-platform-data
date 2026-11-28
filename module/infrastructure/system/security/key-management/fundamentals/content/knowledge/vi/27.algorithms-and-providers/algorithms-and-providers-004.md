# Transformation

Trong chương **Algorithm và provider** của module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, bài học này giải thích transformation trong Java Cryptography Architecture (JCA/JCE). Transformation mô tả thuật toán và cách thuật toán được cấu hình khi ứng dụng dùng Cipher để mã hóa, giải mã hoặc bọc khóa. Chọn transformation đúng giúp xác định rõ thuật toán, mode và padding; chọn thiếu hoặc sai có thể khiến ứng dụng phụ thuộc vào mặc định của provider, làm lộ cấu trúc dữ liệu hoặc không bảo đảm tính toàn vẹn.

## 1. Transformation là gì?

Trong JCA, **transformation** là chuỗi định danh cách một đối tượng Cipher thực hiện phép biến đổi mật mã. Với nhiều thuật toán mã hóa khối, transformation có dạng:

~~~text
algorithm/mode/padding
~~~

Ba thành phần có ý nghĩa:

- **Algorithm:** thuật toán mật mã, ví dụ AES hoặc RSA.
- **Mode:** chế độ vận hành của thuật toán, ví dụ GCM, CBC hoặc CTR.
- **Padding:** cách xử lý dữ liệu đầu vào không khớp kích thước khối, hoặc scheme padding dành riêng cho thuật toán bất đối xứng.

Ví dụ:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
~~~

Chuỗi trên yêu cầu Cipher dùng AES, mode GCM và không dùng padding khối. GCM là authenticated encryption mode, cung cấp cả tính bí mật và khả năng phát hiện dữ liệu bị sửa đổi. NoPadding phù hợp vì GCM xử lý dữ liệu có độ dài tùy ý.

Transformation là cấu hình thuật toán cho Cipher; nó không phải key, không phải certificate và cũng không phải một thuật toán độc lập. Khóa, IV/nonce, tag length và các tham số khác vẫn phải được cung cấp đúng lúc khởi tạo Cipher.

## 2. Transformation trong JCA/JCE

Ứng dụng lấy một đối tượng Cipher bằng phương thức getInstance. JCA tra cứu provider có dịch vụ Cipher hỗ trợ transformation được yêu cầu và trả về engine object cho ứng dụng.

~~~mermaid
flowchart TD
    A[Ứng dụng Java] --> B[Cipher.getInstance]
    C[Transformation string] --> B
    B --> D[Provider lookup]
    D --> E[Provider hỗ trợ Cipher]
    E --> F[Cipher SPI implementation]
    G[Key và AlgorithmParameterSpec] --> H[Cipher.init]
    F --> H
    H --> I[update / doFinal]
    I --> J[Ciphertext hoặc Plaintext]
~~~

Các bước thường gặp:

1. Chọn transformation đầy đủ theo yêu cầu bảo mật.
2. Gọi Cipher.getInstance với transformation.
3. Kiểm tra provider được chọn nếu môi trường yêu cầu provider cụ thể.
4. Chuẩn bị key và tham số phù hợp, chẳng hạn GCMParameterSpec hoặc IvParameterSpec.
5. Gọi init với chế độ ENCRYPT_MODE, DECRYPT_MODE, WRAP_MODE hoặc UNWRAP_MODE.
6. Cung cấp dữ liệu bằng update và hoàn tất bằng doFinal.
7. Lưu metadata cần thiết để giải mã về sau, không lưu key material cùng ciphertext.

Cipher là đối tượng có trạng thái và không nên dùng đồng thời từ nhiều luồng. Tạo hoặc khởi tạo instance riêng cho từng thao tác theo thiết kế ứng dụng.

## 3. Algorithm, mode và padding

Ba thành phần của transformation giải quyết ba vấn đề khác nhau.

| Thành phần | Câu hỏi | Ví dụ |
|---|---|---|
| Algorithm | Dùng họ thuật toán nào? | AES, RSA |
| Mode | Thuật toán mã hóa khối được vận hành ra sao? | GCM, CBC, CTR |
| Padding | Dữ liệu được xử lý thế nào khi độ dài không phù hợp hoặc scheme yêu cầu padding? | NoPadding, PKCS5Padding, OAEP |

Không phải mọi thuật toán đều dùng cả ba thành phần theo cùng một cách. AES thường cần mode và padding trong transformation. RSA không phải block cipher đối xứng, nên chuỗi RSA thường dùng tên transformation có thành phần ECB theo quy ước của JCA/provider; ECB ở đây không có nghĩa RSA đang chạy mode ECB như AES.

Một số thuật toán như ChaCha20-Poly1305 có thể được provider công bố bằng tên transformation không theo mẫu ba phần. Cần dùng đúng tên chuẩn được JDK/provider hỗ trợ và không tự suy ra rằng mọi thuật toán đều phải có mode/padding.

## 4. Vì sao cần chỉ định transformation đầy đủ?

Gọi Cipher chỉ với tên thuật toán, ví dụ:

~~~java
Cipher cipher = Cipher.getInstance("AES");
~~~

có thể khiến provider tự chọn mode và padding mặc định. Cách chọn mặc định có thể khác nhau giữa provider hoặc phiên bản, khiến hành vi không rõ ràng và khó kiểm soát khi triển khai trên nhiều môi trường.

Đối với AES, transformation không đầy đủ có thể dẫn đến cấu hình không phù hợp, chẳng hạn ECB. ECB mã hóa từng block độc lập; các block plaintext giống nhau tạo ra block ciphertext giống nhau dưới cùng khóa, làm lộ mẫu dữ liệu. Không dùng ECB cho dữ liệu ứng dụng thông thường.

Nên ghi rõ transformation:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
~~~

Chỉ định đầy đủ giúp người đọc biết rõ mode/padding, giảm phụ thuộc vào mặc định và làm cho việc review, kiểm thử, cấu hình policy dễ hơn. Tuy vậy, transformation đầy đủ vẫn chưa đủ: ứng dụng phải cung cấp nonce/IV đúng, quản lý khóa đúng và xử lý lỗi xác thực đúng cách.

## 5. Các mode phổ biến

Mode xác định cách dùng thuật toán mã hóa khối để xử lý dữ liệu dài hơn một block. Mỗi mode có yêu cầu riêng về IV/nonce, tính toàn vẹn và cách sử dụng.

| Mode | Đặc điểm | Lưu ý bảo mật |
|---|---|---|
| ECB | Mỗi block được mã hóa độc lập | Làm lộ mẫu lặp; tránh dùng cho dữ liệu thông thường |
| CBC | Block hiện tại phụ thuộc block trước và IV | Cần IV ngẫu nhiên/khó đoán; không tự cung cấp xác thực |
| CTR | Tạo keystream từ counter và XOR với plaintext | Không được tái sử dụng nonce/counter dưới cùng khóa; không tự xác thực |
| GCM | AEAD mode kết hợp mã hóa và authentication tag | Nonce phải duy nhất dưới cùng khóa; xác minh tag trước khi dùng plaintext |
| CCM | AEAD mode dùng counter và CBC-MAC | Cần nonce và tag length đúng giới hạn của chuẩn/provider |

Với thiết kế mới, ưu tiên authenticated encryption như AES-GCM khi phù hợp với môi trường và provider. Nếu phải dùng mode không xác thực như CBC hoặc CTR vì yêu cầu tương thích, cần bổ sung MAC theo thiết kế đã được đánh giá, thường theo Encrypt-then-MAC, và xác minh MAC trước khi giải mã dữ liệu.

## 6. Padding và cách xử lý độ dài dữ liệu

Padding bổ sung dữ liệu để đầu vào đạt yêu cầu của thuật toán hoặc scheme.

| Padding | Ý nghĩa | Ghi chú |
|---|---|---|
| NoPadding | Không thêm padding khối | Dùng với mode xử lý dữ liệu độ dài tùy ý như GCM/CTR hoặc khi đầu vào đã đáp ứng yêu cầu |
| PKCS5Padding | Padding theo quy tắc PKCS được JCA đặt tên như vậy | Thường gặp với AES/CBC; với block size AES 16 byte, hành vi tương ứng quy tắc PKCS#7 |
| OAEP | Padding scheme cho RSA encryption | Ưu tiên cho RSA encryption mới thay cho PKCS#1 v1.5 khi policy cho phép |
| PKCS1Padding | Scheme RSA PKCS#1 v1.5 | Chỉ duy trì khi tương thích bắt buộc và đã đánh giá rủi ro |

NoPadding không tự làm dữ liệu an toàn hơn hoặc kém an toàn hơn; ý nghĩa của nó phụ thuộc mode. GCM không cần block padding. CBC với NoPadding yêu cầu plaintext có độ dài là bội số block size, nếu không thao tác có thể thất bại.

PKCS5Padding là tên transformation phổ biến trong Java. AES có block size 128 bit, nên cách padding được áp dụng tương ứng quy tắc padding mở rộng thường gọi là PKCS#7. Không nhầm tên padding với thuật toán mã hóa hoặc cơ chế xác thực dữ liệu.

## 7. Tham số thuật toán: IV, nonce, tag và parameter spec

Transformation chỉ xác định cách dùng thuật toán. Nhiều mode còn cần tham số cho từng lần mã hóa:

- **IV (Initialization Vector):** giá trị khởi tạo cho một số mode như CBC.
- **Nonce:** giá trị dùng một lần theo yêu cầu của mode như GCM hoặc CTR.
- **Authentication tag:** dữ liệu xác thực để phát hiện ciphertext/AAD bị sửa đổi trong AEAD.
- **AAD (Additional Authenticated Data):** metadata được xác thực nhưng không mã hóa.
- **Parameter spec:** đối tượng Java mô tả tham số, ví dụ GCMParameterSpec, IvParameterSpec hoặc OAEPParameterSpec.

Các tham số này thường không cần giữ bí mật nhưng phải được lưu hoặc truyền cùng ciphertext để giải mã. Chúng phải được tạo, kiểm tra và quản lý theo yêu cầu của thuật toán.

| Transformation | Parameter spec thường dùng | Điều cần bảo đảm |
|---|---|---|
| AES/GCM/NoPadding | GCMParameterSpec | Nonce duy nhất dưới cùng khóa và tag length phù hợp |
| AES/CBC/PKCS5Padding | IvParameterSpec | IV ngẫu nhiên và không dự đoán được |
| AES/CTR/NoPadding | IvParameterSpec | Counter/nonce không lặp dưới cùng khóa |
| RSA/ECB/OAEPWithSHA-256AndMGF1Padding | OAEPParameterSpec | Hash, MGF1 digest và PSource thống nhất giữa hai bên |

Không tái sử dụng IV/nonce khi mode yêu cầu giá trị mới cho mỗi lần mã hóa. Đặc biệt với GCM, dùng lại nonce dưới cùng khóa có thể phá vỡ tính bí mật và xác thực, gây hậu quả nghiêm trọng.

## 8. Ví dụ: AES-GCM encryption và decryption

AES-GCM là lựa chọn phổ biến cho mã hóa dữ liệu mới vì cung cấp authenticated encryption. Ví dụ sau dùng nonce 96 bit và tag 128 bit. Ứng dụng phải bảo đảm nonce không trùng dưới cùng khóa; với hệ thống mã hóa số lượng lớn, cần có chiến lược nonce uniqueness phù hợp thay vì dựa vào cách tạo ngẫu nhiên mà không đánh giá quy mô.

~~~java
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AesGcm {
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    public static final class Encrypted {
        public final byte[] nonce;
        public final byte[] ciphertextAndTag;

        public Encrypted(byte[] nonce, byte[] ciphertextAndTag) {
            this.nonce = nonce;
            this.ciphertextAndTag = ciphertextAndTag;
        }
    }

    public static Encrypted encrypt(
            byte[] plaintext,
            byte[] aad,
            SecretKey key,
            SecureRandom random) throws GeneralSecurityException {

        byte[] nonce = new byte[NONCE_BYTES];
        random.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        if (aad != null) {
            cipher.updateAAD(aad);
        }

        byte[] ciphertextAndTag = cipher.doFinal(plaintext);
        return new Encrypted(nonce, ciphertextAndTag);
    }

    public static byte[] decrypt(
            Encrypted encrypted,
            byte[] aad,
            SecretKey key) throws GeneralSecurityException {

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, encrypted.nonce));
        if (aad != null) {
            cipher.updateAAD(aad);
        }

        // doFinal xác minh authentication tag trước khi trả plaintext.
        return cipher.doFinal(encrypted.ciphertextAndTag);
    }
}
~~~

Ciphertext đầu ra của GCM trong Java thường chứa cả authentication tag ở cuối. Ứng dụng cần lưu nonce cùng ciphertextAndTag. Nonce không phải bí mật; không được bỏ nó vì bên nhận cần cùng nonce để giải mã.

AAD có thể là tenant ID, record ID, phiên bản schema hoặc metadata khác cần được xác thực. Bên giải mã phải cung cấp đúng cùng AAD. Nếu tag không hợp lệ, doFinal ném lỗi xác thực, thường là AEADBadTagException. Ứng dụng phải từ chối dữ liệu và không sử dụng plaintext chưa xác minh.

Ví dụ dùng SecureRandom để tạo nonce ngẫu nhiên. Với hệ thống có lượng mã hóa rất lớn dưới một key, cần thiết kế và giám sát uniqueness theo giới hạn của GCM, chẳng hạn dùng bộ đếm phân vùng hoặc chiến lược nonce đã được chuẩn hóa. Không dùng lại nonce dưới cùng key dù plaintext khác nhau.

## 9. Ví dụ: AES-CBC trong hệ thống cần tương thích

AES/CBC/PKCS5Padding vẫn có thể xuất hiện trong hệ thống cũ:

~~~java
Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
cipher.init(Cipher.ENCRYPT_MODE, aesKey, new IvParameterSpec(iv));
byte[] ciphertext = cipher.doFinal(plaintext);
~~~

IV phải có độ dài đúng với block size của AES và được tạo ngẫu nhiên bằng nguồn an toàn cho mỗi lần mã hóa. IV có thể lưu cùng ciphertext nhưng không được tái sử dụng với cùng khóa.

CBC không cung cấp authentication tag. Nếu chỉ dùng CBC, kẻ tấn công có thể sửa ciphertext và gây ra hành vi giải mã không mong muốn. Thiết kế tương thích cần bổ sung MAC bằng khóa riêng và áp dụng Encrypt-then-MAC: xác minh MAC trước khi giải mã. Khi có thể thay đổi giao thức, nên chuyển sang AEAD như GCM thay vì tự thiết kế cơ chế xác thực.

Không trả lỗi padding chi tiết ra giao diện hoặc kênh có thể bị lạm dụng làm padding oracle. Lỗi giải mã phải được xử lý thống nhất và không để lộ thông tin giúp kẻ tấn công phân biệt trạng thái nội bộ.

## 10. Ví dụ: RSA-OAEP và tham số tường minh

RSA-OAEP thường dùng để mã hóa một lượng dữ liệu nhỏ, chẳng hạn một symmetric key (key wrapping hoặc key transport). Không dùng RSA để mã hóa trực tiếp file lớn; hãy dùng hybrid encryption: AES-GCM mã hóa dữ liệu, RSA-OAEP bảo vệ DEK.

Tên transformation thường gặp:

~~~java
Cipher cipher = Cipher.getInstance(
        "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
~~~

Với RSA, thành phần ECB trong tên transformation là quy ước tên của JCA/provider, không có nghĩa RSA đang dùng ECB mode như AES. Để tránh khác biệt mặc định giữa provider về digest của MGF1, nên truyền OAEPParameterSpec tường minh:

~~~java
import java.security.GeneralSecurityException;
import java.security.PublicKey;
import java.security.spec.MGF1ParameterSpec;
import javax.crypto.Cipher;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public final class RsaOaep {
    public static byte[] encryptKey(
            byte[] keyMaterial, PublicKey publicKey)
            throws GeneralSecurityException {

        Cipher cipher = Cipher.getInstance(
                "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        OAEPParameterSpec parameters = new OAEPParameterSpec(
                "SHA-256",
                "MGF1",
                MGF1ParameterSpec.SHA256,
                PSource.PSpecified.DEFAULT);
        cipher.init(Cipher.ENCRYPT_MODE, publicKey, parameters);
        return cipher.doFinal(keyMaterial);
    }
}
~~~

Bên giải mã phải dùng cùng OAEP parameters và private key tương ứng. Cần xác nhận provider hỗ trợ đúng tổ hợp transformation và tham số; không dựa vào mặc định MGF1 digest. Kích thước dữ liệu RSA-OAEP có giới hạn phụ thuộc modulus, hash và padding, vì vậy ví dụ chỉ nên dùng cho key material nhỏ.

## 11. WRAP_MODE và UNWRAP_MODE

Cipher còn hỗ trợ chế độ bọc và mở bọc khóa:

- **WRAP_MODE:** dùng một key wrapping key để bảo vệ một khóa khác.
- **UNWRAP_MODE:** mở khóa đã được bọc và tạo lại đối tượng Key.

~~~java
Cipher wrapper = Cipher.getInstance("AESWrap");
wrapper.init(Cipher.WRAP_MODE, wrappingKey);
byte[] wrappedKey = wrapper.wrap(dataEncryptionKey);
~~~

Tên transformation và hỗ trợ AESWrap phụ thuộc provider. Cần chọn cơ chế key wrapping theo chuẩn và policy; không tự xem một Cipher encryption thông thường là cơ chế wrapping an toàn cho mọi loại khóa.

Trong kiến trúc envelope encryption, DEK mã hóa dữ liệu còn KEK bảo vệ DEK. Ứng dụng có thể dùng KMS/HSM để wrap/unwrap DEK, lưu wrapped DEK cùng ciphertext và giữ KEK trong miền bảo vệ. Transformation của Cipher không thay thế quy trình quản lý KEK, quyền truy cập, rotation và backup.

## 12. Provider và khả năng hỗ trợ transformation

Không phải mọi provider đều hỗ trợ mọi transformation. Khả năng thực tế phụ thuộc:

- JDK và phiên bản runtime.
- Provider được cài và thứ tự ưu tiên.
- Thuật toán, mode, padding và tham số cụ thể.
- Chính sách bảo mật của runtime.
- Thiết bị HSM/token và firmware nếu provider chuyển thao tác tới phần cứng.

Kiểm tra provider được chọn:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
System.out.println(cipher.getAlgorithm());
System.out.println(cipher.getProvider().getName());
~~~

Có thể chỉ định provider khi có yêu cầu rõ ràng:

~~~java
Cipher cipher = Cipher.getInstance(
        "AES/GCM/NoPadding", "SunJCE");
~~~

Tên provider trong ví dụ phụ thuộc JDK. Chỉ định provider làm hành vi rõ hơn nhưng cũng tạo phụ thuộc triển khai; cần xác minh provider có trên mọi môi trường mục tiêu. Không thêm provider không rõ nguồn gốc chỉ để làm cho một transformation được nhận diện.

## 13. Lựa chọn transformation theo tình huống

| Tình huống | Lựa chọn thường gặp | Điều cần kiểm tra |
|---|---|---|
| Mã hóa dữ liệu ứng dụng mới | AES/GCM/NoPadding | Nonce uniqueness, tag, AAD và key lifecycle |
| Hệ thống cũ dùng CBC | AES/CBC/PKCS5Padding | IV ngẫu nhiên, Encrypt-then-MAC và kế hoạch migration |
| Mã hóa DEK bằng public key | RSA/ECB/OAEPWithSHA-256AndMGF1Padding | OAEP parameters tường minh, kích thước key và dữ liệu đầu vào nhỏ |
| Bọc khóa AES | AESWrap hoặc cơ chế wrapping do KMS/HSM cung cấp | Chuẩn wrapping, loại khóa được hỗ trợ và quyền unwrap |
| Stream cipher AEAD | ChaCha20-Poly1305 nếu provider hỗ trợ | Nonce uniqueness và tag verification |

Đây là ví dụ để định hướng, không phải danh sách transformation dùng được trên mọi JDK. Luôn kiểm tra tài liệu provider, policy thuật toán và khả năng tương thích giữa bên mã hóa và bên giải mã.

## 14. Lưu metadata để giải mã về sau

Để giải mã dữ liệu đã mã hóa, hệ thống cần biết transformation và các tham số đã dùng. Metadata thường gồm:

- Tên transformation và phiên bản định dạng ciphertext.
- Key ID hoặc key version, không phải key material.
- IV/nonce.
- Authentication tag nếu định dạng không gộp tag vào ciphertext.
- AAD hoặc cách tái tạo AAD.
- Ciphertext và thông tin encoding.
- Thông tin KDF/salt nếu khóa được dẫn xuất từ password.

Metadata cần được xác thực hoặc gắn vào AAD để tránh kẻ tấn công thay đổi thuật toán, key ID, version hoặc object context. Không cho phép dữ liệu không tin cậy tự chọn transformation yếu hoặc provider ngoài policy. Nên có allowlist transformation và versioning rõ ràng.

Không lưu private/secret key cùng ciphertext chỉ để thuận tiện. Khóa phải nằm trong KeyStore, KMS, HSM hoặc cơ chế bảo vệ tương ứng; dữ liệu chỉ lưu định danh và tham số công khai cần thiết.

## 15. Rotation và migration transformation

Khi chuyển từ transformation cũ sang transformation mới, cần bảo đảm dữ liệu cũ vẫn có thể giải mã trong thời gian chuyển đổi.

Một quy trình migration có thể gồm:

1. Kiểm kê dữ liệu, transformation, provider, key ID và version đang dùng.
2. Xác định lý do thay đổi: mode yếu, padding cũ, provider lỗi thời hoặc policy mới.
3. Định nghĩa format mới gồm transformation, nonce/IV, tag, AAD và key version.
4. Tạo hoặc chọn key version mới theo quy trình key management.
5. Re-encrypt dữ liệu bằng transformation mới hoặc rewrap DEK nếu chỉ thay KEK.
6. Kiểm tra giải mã, xác thực tag và tính toàn vẹn trên dữ liệu mẫu.
7. Triển khai reader hỗ trợ định dạng cũ và mới trong giai đoạn chuyển tiếp.
8. Theo dõi tỷ lệ dữ liệu đã chuyển đổi và xử lý bản backup.
9. Ngừng hỗ trợ transformation cũ khi không còn dữ liệu phụ thuộc và policy cho phép.

Không xóa khóa cũ trước khi dữ liệu, backup và replica đã được chuyển đổi hoặc hết thời hạn lưu giữ. Nếu thuật toán cũ bị compromise, cần đánh giá sự cố và giới hạn việc tiếp tục dùng nó; kế hoạch migration thông thường có thể không đủ nhanh.

## 16. Lỗi thường gặp

| Lỗi | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| NoSuchAlgorithmException | Provider không hỗ trợ transformation hoặc thuật toán | Kiểm tra tên, JDK, provider và policy |
| NoSuchPaddingException | Padding được yêu cầu không được provider hỗ trợ | Chọn padding phù hợp và kiểm tra tương thích |
| InvalidKeyException | Sai loại/độ dài khóa hoặc provider không chấp nhận | Kiểm tra key algorithm, key size và nguồn khóa |
| InvalidAlgorithmParameterException | IV, nonce, tag length hoặc OAEP parameters không hợp lệ | Kiểm tra parameter spec và giới hạn của thuật toán |
| GCM authentication failure | Ciphertext, tag, nonce, key hoặc AAD không khớp | Từ chối dữ liệu; kiểm tra metadata và nguồn gốc bản mã |
| BadPaddingException | Sai khóa, dữ liệu hỏng hoặc padding không hợp lệ | Không tiết lộ chi tiết lỗi cho bên không tin cậy; kiểm tra luồng mã hóa |
| Kết quả khác giữa môi trường | Provider/default parameter khác nhau | Chỉ định transformation và parameters rõ ràng; kiểm thử provider thực tế |
| TLS/application không tương thích | Client/server dùng thuật toán hoặc format khác nhau | Thống nhất policy, transformation và phiên bản dữ liệu |

Không bắt lỗi rồi tự động thử ECB, padding yếu hoặc provider không được phê duyệt. Fallback như vậy có thể biến một lỗi cấu hình thành lỗ hổng mật mã. Khi transformation không khả dụng, thao tác nhạy cảm nên thất bại an toàn và phát sinh cảnh báo.

## 17. Nguyên tắc bảo mật khi dùng transformation

- Chỉ định transformation đầy đủ, tránh phụ thuộc vào mode/padding mặc định.
- Không dùng ECB cho dữ liệu ứng dụng thông thường.
- Ưu tiên AEAD như AES-GCM khi phù hợp.
- Không bao giờ tái sử dụng nonce GCM hoặc counter theo cách vi phạm yêu cầu uniqueness dưới cùng khóa.
- Dùng tag đủ mạnh và xác minh tag trước khi sử dụng plaintext.
- Nếu dùng CBC/CTR, bổ sung cơ chế xác thực riêng theo thiết kế đã được đánh giá.
- Với RSA encryption mới, ưu tiên OAEP và truyền parameters tường minh.
- Không mã hóa dữ liệu lớn trực tiếp bằng RSA; dùng hybrid encryption.
- Lưu transformation, key ID/version, IV/nonce và metadata cần thiết cùng ciphertext.
- Xác thực metadata hoặc đưa dữ liệu context vào AAD.
- Dùng provider tin cậy, kiểm tra khả năng hỗ trợ trên đúng runtime.
- Không log key, password, plaintext hoặc dữ liệu bí mật.
- Có kế hoạch migration khi thuật toán, mode hoặc policy thay đổi.

## 18. Checklist review transformation

- [ ] Transformation nêu rõ algorithm, mode và padding khi thuật toán yêu cầu.
- [ ] Transformation được provider và JDK mục tiêu hỗ trợ.
- [ ] Không dùng ECB cho dữ liệu thông thường.
- [ ] AEAD được ưu tiên khi cần cả bí mật và toàn vẹn.
- [ ] Nonce/IV được tạo và quản lý theo đúng yêu cầu mode.
- [ ] GCM tag được xác minh trước khi sử dụng plaintext.
- [ ] AAD được tái tạo nhất quán và bảo vệ khỏi sửa đổi.
- [ ] CBC/CTR có MAC riêng nếu vẫn phải sử dụng.
- [ ] RSA-OAEP dùng hash/MGF1 parameters rõ ràng và chỉ xử lý dữ liệu nhỏ.
- [ ] Key ID, version và transformation được lưu trong metadata có xác thực.
- [ ] Không có fallback tự động sang thuật toán hoặc mode yếu.
- [ ] Rotation, migration, backup và retention của dữ liệu cũ đã được tính đến.

Transformation xác định cách Cipher vận hành thuật toán thông qua algorithm, mode và padding. Chọn transformation tường minh giúp hành vi mật mã dễ review và nhất quán giữa các provider, nhưng ứng dụng vẫn phải quản lý IV/nonce, tag, AAD, khóa và metadata đúng cách. Với dữ liệu mới, ưu tiên AEAD; với hệ thống cũ, lập kế hoạch migration có kiểm soát và giữ khả năng phục hồi cho đến khi mọi dữ liệu phụ thuộc đã được xử lý.
