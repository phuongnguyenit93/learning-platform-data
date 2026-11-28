# Key length — Độ dài khóa mật mã

## 1. Key length là gì?

**Key length (độ dài khóa)** là số bit dùng để biểu diễn một khóa mật mã theo quy ước của thuật toán hoặc hệ mật mã. Đây là một thông số quan trọng khi thiết kế hệ thống bảo vệ dữ liệu, nhưng **độ dài khóa không đồng nghĩa trực tiếp với mức độ an toàn của hệ thống**.

Với khóa đối xứng, độ dài khóa thường là số bit bí mật được cung cấp cho thuật toán. Chẳng hạn, AES-128 sử dụng khóa **128 bit (16 byte)**, AES-192 sử dụng **192 bit (24 byte)** và AES-256 sử dụng **256 bit (32 byte)**:

| Thuật toán | Độ dài khóa | Kích thước khóa |
| --- | ---: | ---: |
| AES-128 | 128 bit | 16 byte |
| AES-192 | 192 bit | 24 byte |
| AES-256 | 256 bit | 32 byte |

Với mật mã bất đối xứng, cách xác định kích thước khóa phụ thuộc họ thuật toán. Ví dụ, **RSA-3072** có modulus RSA dài 3072 bit, còn **ECDSA dùng đường cong P-256** hoạt động trên các tham số đường cong xấp xỉ 256 bit. Hai hệ đó **không có cùng độ mạnh bảo mật chỉ vì một khóa có 3072 bit và khóa kia có 256 bit**.

Trong chương **Thuật ngữ cốt lõi** của học phần quản lý khóa mật mã, cần phân biệt key length với những khái niệm liên quan: **security strength**, **entropy**, **key space**, độ dài **nonce/IV**, độ dài **authentication tag**, kích thước **chữ ký số** và độ dài **hash output**. Nhầm lẫn các giá trị này dẫn đến lựa chọn thuật toán, cấu hình KMS/HSM và kế hoạch vòng đời khóa không phù hợp.

## 2. Bit, byte, không gian khóa và độ mạnh bảo mật

### 2.1. Key space: có bao nhiêu khóa khả dĩ?

Với một khóa đối xứng gồm **n bit được chọn độc lập và đồng đều**, không gian khóa có tối đa **2^n** giá trị:

- Khóa 128 bit: **2^128** khóa khả dĩ.
- Khóa 192 bit: **2^192** khóa khả dĩ.
- Khóa 256 bit: **2^256** khóa khả dĩ.

Số lượng khả dĩ tăng theo cấp số mũ. Thêm một bit **nhân đôi** kích thước không gian khóa; tăng từ 128 bit lên 256 bit làm số ứng viên tăng theo hệ số **2^128**.

Tuy nhiên, lập luận trên chỉ mô tả không gian biểu diễn của khóa. Nó **không bảo đảm** khóa được tạo ngẫu nhiên, không đoán được hoặc thuật toán không có lỗ hổng.

### 2.2. Security strength: độ mạnh bảo mật hiệu dụng

**Security strength**, thường đo bằng bit, là mức công sức tính toán gần đúng mà một đối thủ cần để phá một mục tiêu bảo mật, trong mô hình tấn công và giả định cụ thể. Chẳng hạn, độ mạnh 128 bit thường được hiểu là chi phí tấn công ở quy mô khoảng **2^128** phép tính cơ bản theo mô hình tương ứng; đây không phải lời bảo đảm tuyệt đối rằng mọi cách tấn công đều cần chính xác chừng đó bước.

Đối với thuật toán đối xứng mạnh và khóa sinh đúng cách, độ dài khóa có thể gần tương ứng với độ mạnh chống dò khóa vét cạn. Với mật mã bất đối xứng, nhiều phép tấn công toán học hiệu quả hơn rất nhiều so với việc thử hết mọi giá trị của khóa nên **không thể so bit khóa trực tiếp**.

Bảng sau cung cấp các mức **tương đương an toàn cổ điển gần đúng**, nhằm giúp chọn tham số. Các con số còn phụ thuộc giả định, thuật toán cụ thể và khuyến nghị đang áp dụng:

| Mức độ mạnh cổ điển xấp xỉ | Khóa đối xứng AES | RSA (độ dài modulus) | ECC theo nhóm đường cong NIST |
| --- | --- | --- | --- |
| 112 bit | — | RSA-2048 | Đường cong cỡ 224 bit, như P-224 |
| 128 bit | AES-128 | RSA-3072 | P-256 |
| 192 bit | AES-192 | RSA-7680 | P-384 |
| 256 bit | AES-256 | RSA-15360 | P-521 |

**Cách đọc đúng:** RSA-3072 và P-256 có độ mạnh cổ điển *xấp xỉ* 128 bit, dù độ dài tham số rất khác nhau. RSA-2048 thường được đánh giá ở khoảng 112 bit; nó không cung cấp 2048 bit an toàn. P-521 có mức độ mạnh xấp xỉ 256 bit, không phải 521 bit.

Các thuật toán hiện đại khác có cách biểu diễn riêng. **X25519** (trao đổi khóa) và **Ed25519** (chữ ký số) được thiết kế quanh mức bảo mật cổ điển xấp xỉ 128 bit; không suy ra độ mạnh chỉ bằng kích thước chuỗi byte chứa public key hoặc chữ ký.

### 2.3. Entropy: độ khó đoán thực tế của khóa

**Entropy** phản ánh mức độ không chắc chắn của giá trị bí mật. Một khóa có định dạng 256 bit nhưng chỉ có thể được tạo từ vài triệu mật khẩu phổ biến không hề mang lại sức mạnh của khóa 256 bit ngẫu nhiên.

Ví dụ:

- **Khóa A:** 32 byte được sinh bằng bộ sinh số ngẫu nhiên dùng cho mật mã (CSPRNG), với nguồn entropy phù hợp.
- **Khóa B:** Chuỗi mật khẩu ngắn được đệm thêm ký tự đến đủ 32 byte rồi dùng làm khóa AES-256.

Cả hai có thể được API nhận là khóa dài 256 bit, nhưng **B dễ bị đoán hơn nhiều** vì không gian các mật khẩu thực tế quá nhỏ.

Khi bắt buộc xuất phát từ mật khẩu, dùng **password-based key derivation function** phù hợp (ví dụ PBKDF2 với tham số đủ mạnh hoặc Argon2id khi môi trường cho phép), kết hợp salt ngẫu nhiên và chính sách mật khẩu. KDF tăng chi phí thử đoán và giúp chống các dạng tấn công nhất định, nhưng **không thể tự tạo thêm entropy vốn không có trong mật khẩu**. Khóa hệ thống nên được sinh trực tiếp bằng CSPRNG hoặc KMS/HSM khi có thể.

## 3. Key length theo từng nhóm thuật toán

### 3.1. Mật mã đối xứng: AES

AES hỗ trợ đúng ba độ dài khóa: **128, 192, 256 bit**. Độ dài khóa ảnh hưởng số vòng xử lý nội bộ và biên độ bảo mật trước một số loại tấn công. Tuy nhiên, việc chọn AES-256 thay AES-128 không sửa được lỗi dùng nonce, mode hoặc cấp quyền.

Trong nhiều hệ thống hiện đại, **AES-128** là lựa chọn có độ mạnh cao đối với tấn công cổ điển; **AES-256** thường được chọn khi chính sách hoặc yêu cầu bảo vệ dài hạn cần biên độ an toàn lớn hơn. Việc lựa chọn nên dựa trên mô hình đe dọa, quy định, thời gian tồn tại của dữ liệu và khả năng hỗ trợ của nền tảng.

**AES-GCM** kết hợp mã hóa với xác thực dữ liệu. Ở đây có ít nhất ba tham số khác nhau:

| Tham số | Ví dụ phổ biến | Chức năng |
| --- | --- | --- |
| **Key length** | 128 hoặc 256 bit | Quy định kích thước khóa AES bí mật |
| **Nonce/IV length** | 96 bit (12 byte) | Tạo giá trị riêng cho từng lần mã hóa dưới cùng một khóa |
| **Authentication tag length** | 128 bit (16 byte) | Phát hiện ciphertext/AAD bị sửa hoặc không khớp |

**Chú ý:** Nonce 96 bit **không phải** khóa 96 bit; tag 128 bit **không có nghĩa** khóa AES chỉ dài 128 bit. Trong GCM, **tái sử dụng cùng một nonce với cùng một khóa** có thể gây hậu quả nghiêm trọng cho cả tính bí mật lẫn xác thực. Thay đổi key length không bù đắp được lỗi này.

### 3.2. Mật mã bất đối xứng: RSA

Với RSA, tên **RSA-2048**, **RSA-3072** hoặc **RSA-4096** thường chỉ số bit của **modulus n**, không phải số bit ngẫu nhiên độc lập của khóa riêng hay độ mạnh chống tấn công.

RSA-3072 có độ mạnh cổ điển thường được ước tính quanh **128 bit**. RSA-4096 có modulus lớn hơn nhưng không đạt tương đương AES-256. Modulus lớn hơn cũng làm tăng kích thước khóa, ciphertext/chữ ký RSA và chi phí tính toán. Nếu hệ thống cần RSA, hãy chọn kích thước theo mức độ mạnh mong muốn và vòng đời dữ liệu, đồng thời kiểm tra khả năng hỗ trợ của KMS/HSM, thư viện và đối tác.

Độ dài khóa không thay thế cho lựa chọn **sơ đồ padding an toàn**: mã hóa RSA nên dùng sơ đồ phù hợp như RSA-OAEP khi áp dụng; chữ ký nên dùng sơ đồ và tham số như RSA-PSS theo yêu cầu hệ thống. Không dùng RSA “textbook” chỉ vì modulus lớn.

### 3.3. Mật mã đường cong elliptic: ECC

Với ECC, kích thước tham số toán học thường nhỏ hơn RSA rất nhiều để đạt mức bảo mật cổ điển gần tương đương. Điều này có thể giúp giảm kích thước khóa/chữ ký và chi phí truyền tải, tùy thuật toán.

Ví dụ:

- **ECDSA với P-256:** mức độ mạnh cổ điển xấp xỉ 128 bit.
- **ECDSA với P-384:** mức độ mạnh cổ điển xấp xỉ 192 bit.
- **ECDSA với P-521:** mức độ mạnh cổ điển xấp xỉ 256 bit.
- **Ed25519:** chữ ký số có mức độ mạnh cổ điển xấp xỉ 128 bit.
- **X25519:** cơ chế thỏa thuận khóa có mức độ mạnh cổ điển xấp xỉ 128 bit.

Kích thước byte được mã hóa của khóa công khai, khóa riêng, public point hoặc chữ ký **không nhất thiết bằng số bit bảo mật**. Đối với chữ ký số, ngoài tham số đường cong, cần xét nguồn sinh số ngẫu nhiên nếu thuật toán yêu cầu, cách xác minh danh tính, quản lý private key và khả năng thu hồi.

### 3.4. HMAC, KDF và các khóa theo mục đích

**HMAC** dùng khóa bí mật với hàm băm để xác thực thông điệp. Kích thước khóa HMAC, kích thước đầu ra hàm băm (ví dụ SHA-256) và độ dài MAC được truyền/lưu là ba khái niệm khác nhau. Khóa ngẫu nhiên 256 bit thường là lựa chọn thuận tiện cho HMAC-SHA-256, nhưng mức an toàn cụ thể còn phụ thuộc cách sử dụng và độ dài tag xác thực.

Với **HKDF**, **DEK**, **KEK** hoặc khóa con sinh từ một bí mật gốc, phải xét **entropy của vật liệu đầu vào**, cách tách mục đích và độ dài đầu ra. Yêu cầu sinh khóa 256 bit từ bí mật nguồn yếu không làm tăng entropy lên 256 bit. Tránh tái sử dụng cùng một khóa cho mã hóa, ký/MAC và các môi trường độc lập khi thiết kế cho phép tách khóa.

### 3.5. Mật mã hậu lượng tử: không so bit trực tiếp

Các máy tính lượng tử đủ mạnh trong tương lai có thể ảnh hưởng nghiêm trọng đến các cơ chế dựa trên RSA và nhiều hệ đường cong elliptic. Khóa đối xứng cũng chịu ảnh hưởng của mô hình tấn công lượng tử nhưng không theo cách tương tự.

Các cơ chế mật mã hậu lượng tử như **ML-KEM** và **ML-DSA** dùng hệ tham số và mức an toàn riêng. Kích thước public key, private key, ciphertext hoặc chữ ký có thể lớn hơn đáng kể so với ECC nhưng **không đồng nghĩa** độ mạnh tăng theo tỷ lệ byte. Khi lập kế hoạch chuyển đổi, cần căn cứ chuẩn, mức an toàn, thuật toán được phê duyệt và khả năng tương thích thực tế, thay vì so độ dài chuỗi khóa.

## 4. Chọn key length trong hệ thống key management

Mục tiêu không phải luôn chọn **con số lớn nhất**, mà là chọn tham số có mức an toàn phù hợp và duy trì được các thuộc tính đó trong toàn bộ vòng đời **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy** khóa.

### 4.1. Những yếu tố quyết định

1. **Mức bảo vệ của dữ liệu:** Dữ liệu có mức nhạy cảm nào; hậu quả nếu bị giải mã hoặc giả mạo là gì?
2. **Thời gian cần bảo mật:** Dữ liệu chỉ cần bảo vệ trong một phiên giao dịch hay phải giữ bí mật nhiều năm, kể cả sau khi bản mã bị lưu lại?
3. **Loại phép toán:** Mã hóa AES, ký ECDSA/EdDSA, thỏa thuận khóa X25519, MAC HMAC hay wrap DEK bằng KEK đòi hỏi tham số khác nhau.
4. **Năng lực hệ thống:** Thư viện Java, giao thức, máy khách, KMS/HSM và đối tác có hỗ trợ thuật toán/độ dài đó không?
5. **Chính sách và quy định:** Áp dụng yêu cầu của tổ chức và chuẩn liên quan; kiểm tra bản khuyến nghị còn hiệu lực tại thời điểm thiết kế.
6. **Khả năng thay khóa:** Cần biết thuật toán, định danh khóa, độ dài, phiên bản, dữ liệu phụ thuộc và kế hoạch chuyển đổi khi chính sách thay đổi.

Không thể tuyên bố một số bit luôn an toàn trong mọi hoàn cảnh. Chẳng hạn, khóa AES-256 bị ghi vào log hoặc bị cấp quyền giải mã cho mọi ứng dụng vẫn là thiết kế không an toàn.

### 4.2. Trường hợp DEK và KEK trong envelope encryption

Trong **envelope encryption**, **DEK (Data Encryption Key)** dùng để mã hóa dữ liệu, còn **KEK (Key Encryption Key)** dùng để mã hóa/bọc DEK. Cần xác định key length cho cả hai dựa trên thuật toán cụ thể.

~~~mermaid
flowchart TD
    KMS["KMS/HSM giữ KEK<br/>theo chính sách truy cập"]
    DEK["Sinh DEK AES-256<br/>256 bit = 32 byte"]
    WRAP["Wrap DEK bằng KEK"]
    DATA["Mã hóa dữ liệu bằng<br/>AES-256-GCM"]
    STORE["Lưu ciphertext, nonce, tag,<br/>wrapped DEK, key ID và metadata"]
    KMS --> WRAP
    DEK --> WRAP
    DEK --> DATA
    WRAP --> STORE
    DATA --> STORE
~~~

Ví dụ, hệ thống chọn **DEK AES-256** vì muốn mức độ mạnh đối xứng 256 bit, còn KEK trong dịch vụ KMS có thể được cấu hình theo loại khóa/phương thức wrap khác nhau. Không được suy ra **KEK cũng dài 256 bit** chỉ từ việc DEK là AES-256; phải kiểm tra tài liệu của thuật toán và nhà cung cấp.

Với khóa mới, API KMS/HSM có thể sinh và bảo vệ vật liệu khóa theo cấu hình. Với khóa cũ, việc **rotate KEK** có thể cho phép rewrap DEK mà không mã hóa lại toàn bộ dữ liệu; việc **rotate DEK** thường đòi hỏi mã hóa lại dữ liệu mà DEK bảo vệ. Đảm bảo vẫn truy cập được đúng phiên bản khóa giải mã các bản ghi cũ trước khi vô hiệu hóa/hủy.

### 4.3. Độ dài khóa gắn với kiểm soát truy cập và kiểm toán

Key length chỉ là một thành phần của hệ thống bảo vệ khóa. Cần phối hợp:

- **Quyền truy cập tối thiểu:** Tách quyền Encrypt/Decrypt, Sign/Verify, GenerateDataKey, Rotate và Delete theo vai trò/workload.
- **Chính sách không xuất khóa khi phù hợp:** Giữ private key hoặc KEK trong ranh giới KMS/HSM nếu khả thi; ứng dụng chỉ yêu cầu thao tác mật mã được phép.
- **Kiểm toán:** Ghi ai tạo/sử dụng/xoay vòng/thay đổi quyền đối với key ID, loại khóa và thuật toán nào; **không ghi nguyên văn vật liệu khóa**.
- **Theo dõi phiên bản và phụ thuộc:** Khi nâng từ RSA-2048 lên RSA-3072 hoặc thay DEK AES-128 bằng AES-256, xác định dữ liệu/chữ ký/chứng chỉ/cấu hình nào cần chuyển đổi.
- **Phản ứng sự cố:** Khi khóa bị lộ, phải đánh giá và thay khóa, vô hiệu hóa quyền, xử lý dữ liệu liên quan; chỉ tăng kích thước khóa mới không khắc phục được tác hại của khóa cũ đã rò rỉ.

## 5. Ví dụ Java: tạo đúng khóa AES-256 và dùng AES-GCM

Trong Java, **KeyGenerator** có thể sinh một khóa AES có độ dài yêu cầu thông qua provider mật mã. Ví dụ sau minh họa cách tạo **DEK AES-256 (32 byte)** bằng nguồn ngẫu nhiên dành cho mật mã rồi mã hóa/giải mã với AES-GCM:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class KeyLengthDemo {
    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();

        KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
        keyGenerator.init(256, random);
        SecretKey dek = keyGenerator.generateKey();

        // Chỉ để minh họa kích thước; không in nội dung khóa.
        if (dek.getEncoded().length != 32) {
            throw new IllegalStateException("Expected a 256-bit AES key");
        }

        byte[] nonce = new byte[12]; // Nonce GCM 96 bit, không phải key.
        random.nextBytes(nonce);
        byte[] aad = "tenant-17:record-42"
                .getBytes(StandardCharsets.UTF_8);
        byte[] input = "Du lieu can bao ve"
                .getBytes(StandardCharsets.UTF_8);

        Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
        encryptor.init(
                Cipher.ENCRYPT_MODE,
                dek,
                new GCMParameterSpec(128, nonce) // Tag xác thực 128 bit.
        );
        encryptor.updateAAD(aad);
        byte[] ciphertextWithTag = encryptor.doFinal(input);

        Cipher decryptor = Cipher.getInstance("AES/GCM/NoPadding");
        decryptor.init(
                Cipher.DECRYPT_MODE,
                dek,
                new GCMParameterSpec(128, nonce)
        );
        decryptor.updateAAD(aad);
        byte[] restored = decryptor.doFinal(ciphertextWithTag);

        System.out.println(new String(restored, StandardCharsets.UTF_8));
    }
}
~~~

Ở ví dụ trên:

- **256** trong **keyGenerator.init(256, random)** là độ dài khóa AES, tức 32 byte.
- **12 byte** là kích thước nonce dùng với GCM; **128** trong **GCMParameterSpec** là độ dài tag xác thực.
- **AAD** phải được cung cấp giống nhau khi mã hóa và giải mã. Nếu ciphertext, tag hoặc AAD bị thay đổi, quá trình kiểm tra xác thực phải thất bại.
- Nonce phải **duy nhất cho mỗi lần mã hóa dưới cùng DEK**. Ví dụ tạo một nonce mới cho một lần mã hóa; ứng dụng sản xuất phải có chiến lược quản lý nonce và giới hạn lượng dữ liệu/lần mã hóa phù hợp, nhất là khi mã hóa rất nhiều bản ghi.
- Đây là chương trình minh họa. Trong hệ thống thật, DEK cần được quản lý thời gian sống trong bộ nhớ; khóa lưu trữ phải được bảo vệ bằng KMS/HSM hoặc wrap an toàn. Không để DEK dạng rõ trong log, mã nguồn hoặc tệp cấu hình. Không dùng **getEncoded()** đối với khóa không cho xuất; API KMS/HSM có thể cung cấp thao tác mật mã trực tiếp.

**Lưu ý về provider:** Trước khi triển khai, kiểm tra JDK, provider, chính sách môi trường và KMS/HSM có hỗ trợ AES-256/GCM hay không. Không làm giảm độ dài hoặc chuyển sang mode kém an toàn để “chạy được” khi yêu cầu bảo mật chưa được đánh giá lại.

## 6. Những nhầm lẫn thường gặp

| Nhận định dễ nhầm | Vì sao sai hoặc chưa đủ | Cách hiểu đúng |
| --- | --- | --- |
| “RSA-2048 mạnh 2048 bit.” | Độ dài modulus không tương đương độ mạnh bảo mật. | RSA-2048 thường tương đương khoảng 112 bit an toàn cổ điển. |
| “ECC P-256 yếu hơn RSA-3072 vì 256 nhỏ hơn 3072.” | Họ thuật toán có cấu trúc và cách tấn công khác nhau. | Cả hai đạt khoảng 128 bit an toàn cổ điển trong giả định phổ biến. |
| “Mật khẩu được đệm lên 32 byte là khóa AES-256 an toàn.” | Kích thước chuỗi không bù entropy thấp. | Sinh khóa ngẫu nhiên bằng CSPRNG/KMS; nếu xuất phát từ mật khẩu, dùng KDF phù hợp. |
| “Đặt GCM nonce dài 96 bit tức đang dùng key 96 bit.” | Nonce và khóa có vai trò khác nhau. | Key length, nonce length và tag length là các tham số riêng. |
| “AES-256 ngăn được mọi kiểu tấn công.” | Rò rỉ khóa, cấp quyền sai, nonce trùng, lỗi ứng dụng vẫn gây tổn hại. | Kết hợp thuật toán với chính sách khóa, AEAD, quyền và giám sát. |
| “Key length càng lớn thì hiệu năng luôn tốt hơn.” | Tùy thuật toán; kích thước lớn thường gây chi phí tính toán, lưu trữ hoặc truyền tải cao hơn. | Cân bằng yêu cầu an toàn, giao thức, hiệu năng và tương thích. |
| “Dùng cùng kích thước khóa thì có thể thay thuật toán mà không đổi định dạng.” | RSA, ECC, AES và mật mã hậu lượng tử không có định dạng hay ý nghĩa bit tương ứng. | Quản lý rõ algorithm ID, key type, key size, version và quy trình migration. |
| “Rotate khóa mới là dữ liệu cũ tự được bảo vệ lại.” | Bản mã có thể vẫn phụ thuộc khóa cũ hoặc KEK cũ. | Theo dõi key version, rewrap DEK hoặc re-encrypt theo loại khóa được đổi. |

## 7. Checklist lựa chọn và kiểm tra key length

Khi triển khai hoặc review một hệ thống mật mã, hãy xác nhận:

1. **Đúng loại khóa:** Đây là AES, HMAC, RSA, ECC, khóa ký, khóa trao đổi hay DEK/KEK?
2. **Đúng thông số:** Bit đang chỉ số bit của key material, modulus, tham số đường cong, nonce, tag hay chữ ký?
3. **Đúng độ mạnh:** Security strength phù hợp với loại dữ liệu, thời gian cần bảo vệ và chính sách hiện hành?
4. **Đủ ngẫu nhiên:** Khóa được tạo bằng CSPRNG/KMS/HSM hoặc KDF có đầu vào, salt và tham số phù hợp?
5. **Đúng cách sử dụng:** Mode/padding, nonce, AAD, xác thực danh tính và các điều kiện thuật toán có được áp dụng đầy đủ?
6. **Đúng quyền:** Ai được sinh, sử dụng, xuất, xoay vòng, thu hồi hoặc hủy khóa? Những thao tác này có log kiểm toán?
7. **Tương thích:** Java/JCE, KMS/HSM, protocol và bên liên quan có hỗ trợ đúng thuật toán và key length không?
8. **Đổi được về sau:** Có key ID/version, kế hoạch migration, đọc lại dữ liệu cũ và khả năng ứng phó khi khóa bị lộ?

## 8. Ghi nhớ

**Key length** mô tả kích thước một tham số khóa, còn **security strength** mô tả mức độ khó phá theo mô hình tấn công; **entropy** cho biết khóa thực sự khó đoán đến mức nào. Ba khái niệm này liên quan nhưng không thay thế cho nhau.

Một khóa **AES-256** dài 256 bit, một khóa **RSA-3072** có modulus 3072 bit và một khóa **ECC P-256** sử dụng tham số đường cong cỡ 256 bit. Tên gọi và số bit của chúng chỉ có ý nghĩa khi gắn với **thuật toán và mục đích sử dụng**.

Trong quản lý khóa thực tế, độ dài khóa chỉ là điểm khởi đầu. Thiết kế an toàn còn cần **nguồn sinh khóa đúng, mã hóa/xác thực đúng, kiểm soát truy cập, KMS/HSM, envelope encryption, kiểm toán, xoay vòng và quy trình thu hồi/hủy** phù hợp với toàn bộ vòng đời dữ liệu.
