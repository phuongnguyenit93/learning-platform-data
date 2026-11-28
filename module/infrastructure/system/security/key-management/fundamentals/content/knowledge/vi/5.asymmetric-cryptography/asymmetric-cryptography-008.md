# Public key encryption — Mã hóa bằng khóa công khai

## 1. Public key encryption là gì?

**Public key encryption (mã hóa bằng khóa công khai)** là cơ chế mật mã bất đối xứng cho phép một bên mã hóa thông tin bằng **public key** của người nhận, còn người nhận sử dụng **private key** tương ứng để giải mã. Public key có thể được phân phối cho nhiều bên; private key phải được bảo vệ và chỉ được sử dụng bởi chủ thể có quyền.

Ví dụ, hệ thống A cần gửi một bí mật cho hệ thống B mà hai bên chưa có sẵn khóa đối xứng chung. A có thể lấy **public key đáng tin cậy của B** để mã hóa một bí mật hoặc một khóa phiên. B dùng private key tương ứng để giải mã. Người chỉ thu thập ciphertext và public key của B không thể dễ dàng khôi phục bí mật nếu thuật toán, tham số, nguồn ngẫu nhiên và cách triển khai đủ an toàn.

Trong chương **Mật mã bất đối xứng** của học phần **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, public key encryption là điểm nối giữa mật mã bất đối xứng, mật mã đối xứng, chữ ký số, **KMS/HSM** và **envelope encryption**. Để hệ thống thực sự an toàn, phải quản lý cả vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng đến thu hồi và hủy**, cùng quyền truy cập và log kiểm toán.

> **Nguyên tắc quan trọng:** Bất kỳ ai cũng có thể mã hóa thông tin bằng public key của B. Vì vậy, bản mã giải mã được bởi B **không tự chứng minh ai là người gửi**, và việc một public key có mặt trong hệ thống **không tự chứng minh nó thuộc về B**.

## 2. Hai khóa có vai trò khác nhau

Một cặp khóa bất đối xứng thường gồm:

- **Public key:** Được phép công bố, dùng để mã hóa hoặc tham gia cơ chế thiết lập khóa theo thuật toán. Tuy không cần giữ bí mật, **nguồn gốc và liên kết với danh tính người nhận phải được xác thực**.
- **Private key:** Giá trị bí mật dùng để giải mã trong hệ mã hóa khóa công khai hoặc tham gia phép toán private-key khác. Phải hạn chế xuất khóa, giữ trong kho phù hợp như HSM/KMS khi có thể, kiểm soát thao tác sử dụng và phương án phục hồi.

Tùy thuật toán, cặp khóa dành cho **mã hóa/giải mã**, **chữ ký số** hoặc **thỏa thuận khóa** có mục đích khác nhau. Không nên mặc định một cặp khóa được phép và nên sử dụng cho mọi thao tác.

| Thao tác | Khóa dùng tại bên gửi | Khóa dùng tại bên nhận / bên xác minh | Mục tiêu chủ yếu |
| --- | --- | --- | --- |
| **Mã hóa khóa công khai** | Public key của người nhận | Private key của người nhận | Giữ bí mật với bên không sở hữu private key |
| **Chữ ký số** | Private key của người ký | Public key đáng tin cậy của người ký | Xác minh tính toàn vẹn và nguồn gốc theo danh tính gắn với khóa |
| **Thỏa thuận khóa** | Khóa bí mật của một bên và public key bên kia, theo giao thức | Khóa bí mật của bên còn lại và public key đối tác | Thiết lập bí mật chung để dẫn xuất khóa phiên |

**Không diễn giải chữ ký số là “mã hóa bằng private key”.** Chữ ký số dùng thuật toán và quy tắc xác minh riêng; public key không phải công cụ “giải mã chữ ký” theo nghĩa khôi phục nội dung bí mật. Tương tự, chỉ mã hóa bằng public key không thay thế chữ ký số.

### 2.1. Sơ đồ giao tiếp cơ bản

~~~mermaid
sequenceDiagram
    participant A as Bên gửi A
    participant Directory as Kênh chứng thực khóa
    participant B as Bên nhận B
    A->>Directory: Yêu cầu public key của B
    Directory-->>A: Public key + thông tin xác thực
    Note over A: Kiểm tra đúng danh tính B và mục đích sử dụng khóa
    A->>A: Mã hóa bí mật bằng public key của B
    A->>B: Chuyển ciphertext và metadata
    Note over B: Private key được bảo vệ
    B->>B: Giải mã bằng private key tương ứng
~~~

Sơ đồ là luồng khái niệm: việc xác thực public key có thể dựa trên chứng chỉ, trust anchor hoặc cơ chế phân phối khóa đáng tin cậy khác; có hệ thống lấy public key của đối tác trực tiếp từ một kho cấu hình đã được quản trị.

## 3. Điều public key encryption bảo vệ và không bảo vệ

### 3.1. Tính bí mật của dữ liệu

Với thuật toán mã hóa khóa công khai hiện đại được triển khai đúng cách, người không có private key tương ứng sẽ khó giải mã ciphertext. Nhưng mức an toàn thực tế còn phụ thuộc cách sinh khóa, độ dài/tham số khóa, padding, nguồn ngẫu nhiên, lỗi oracle và nơi cất giữ private key.

Khóa RSA dài 3072 bit không có nghĩa là hệ thống đạt 3072 bit bảo mật; mức độ mạnh **cổ điển** thường được ước lượng khoảng **128 bit**. Kích thước khóa của RSA và ECC không thể so trực tiếp với key length AES.

### 3.2. Không tự xác thực người gửi

Vì public key được công bố, **bất kỳ ai có public key hợp lệ cũng có thể tạo bản mã gửi cho B**. B giải mã thành công chỉ biết bản mã phù hợp với private key của mình, chưa đủ để xác nhận người gửi là A.

Nếu nghiệp vụ yêu cầu nhận diện A, có thể sử dụng **chữ ký số**, giao thức xác thực, mTLS hoặc cơ chế xác thực ứng dụng phù hợp. Khi kết hợp mã hóa và ký, phải sử dụng một **giao thức được thiết kế đúng**: kiểm tra chữ ký, định danh, ngữ cảnh và thứ tự xử lý theo đặc tả, tránh tự ghép các phép toán mật mã.

### 3.3. Không tự bảo đảm public key thuộc đúng người nhận

Giả sử A định gửi dữ liệu cho B nhưng kẻ tấn công M thay public key của B trên kênh phân phối bằng public key của M. A mã hóa dữ liệu cho M; M dùng private key của mình để đọc được nội dung. Thuật toán mã hóa có thể hoạt động **hoàn toàn đúng** nhưng mục tiêu bí mật đối với B đã thất bại vì **đánh tráo khóa**.

Do đó, xác minh **key ownership / public-key authenticity** là bước bắt buộc: kiểm tra chứng chỉ và chuỗi tin cậy khi dùng PKI, danh tính/SAN phù hợp, mục đích sử dụng khóa, thời hạn hiệu lực và trạng thái thu hồi theo chính sách; hoặc xác minh fingerprint qua kênh độc lập đáng tin cậy nếu dùng mô hình đó. **Chỉ tải một file public key qua HTTPS không tự bảo đảm nó thuộc đúng chủ thể mà nghiệp vụ mong muốn**, nếu không xác minh được nguồn cung cấp.

### 3.4. Không tự chống phát lại và không mặc định có forward secrecy

Một ciphertext hợp lệ có thể được gửi lại. Nếu nghiệp vụ không muốn xử lý lệnh hai lần, cần **chống replay** bằng request ID, sequence number, nonce nghiệp vụ, thời hạn và cơ chế ghi nhận trạng thái thích hợp.

Trong sơ đồ **RSA mã hóa trực tiếp một bí mật/DEK cho khóa công khai tĩnh của B**, nếu private key của B bị lộ về sau và đối thủ đã lưu ciphertext cũ, họ có thể giải mã các ciphertext đó. Thiết kế này **không tự có forward secrecy**. Các giao thức như TLS 1.3 dùng thỏa thuận khóa tạm thời để đạt những tính chất bảo mật khác; không nên mặc định mọi hình thức mã hóa bằng public key đều có cùng thuộc tính.

## 4. Thuật toán và cơ chế liên quan

### 4.1. RSA-OAEP: mã hóa bằng khóa công khai RSA

**RSA** là một họ thuật toán bất đối xứng. Để mã hóa an toàn bằng RSA trong các thiết kế được phép sử dụng, thường chọn **RSAES-OAEP** với tham số hash/MGF rõ ràng thay vì RSA thô.

**Không dùng “textbook RSA”** (lũy thừa modular trực tiếp không có padding an toàn). Các sơ đồ cũ có thể gặp rủi ro khi ứng dụng để lộ thông tin khác nhau qua lỗi giải mã; RSA-OAEP là một phương án có thiết kế chống các kiểu tấn công đã biết trong mô hình chuẩn thích hợp, nhưng triển khai vẫn phải bảo vệ private key và xử lý lỗi cẩn thận.

RSA-OAEP chỉ mã hóa **thông điệp nhỏ hơn modulus theo giới hạn padding**, không phải lựa chọn tối ưu để mã hóa tệp lớn.

Với RSA-OAEP, độ dài bản rõ tối đa tính bằng byte là:

\[
mLen \leq k - 2hLen - 2
\]

Trong đó **k** là độ dài modulus RSA theo byte, **hLen** là độ dài đầu ra hàm băm dùng trong OAEP, tính theo byte. Ví dụ:

| Cấu hình | k (byte) | hLen (byte) | Bản rõ tối đa |
| --- | ---: | ---: | ---: |
| RSA-2048 + OAEP SHA-256 | 256 | 32 | **190 byte** |
| RSA-3072 + OAEP SHA-256 | 384 | 32 | **318 byte** |
| RSA-4096 + OAEP SHA-256 | 512 | 32 | **446 byte** |

Các kích thước trên áp dụng cho phép mã hóa RSA-OAEP với modulus và hash đã nêu; ứng dụng nên dành RSA cho việc bảo vệ **khóa đối xứng nhỏ** hoặc bí mật ngắn, sau đó dùng mã hóa đối xứng cho dữ liệu lớn.

### 4.2. ECC thường được dùng qua thỏa thuận khóa hoặc KEM

Không phải mọi thuật toán elliptic-curve (ECC) đều có thao tác “encrypt bằng public key” trực tiếp giống RSA-OAEP.

- **ECDH/X25519:** Các bên kết hợp private key của mình và public key đối tác để tạo **shared secret** theo giao thức. Bí mật này cần được đưa qua **KDF** phù hợp để dẫn xuất khóa mã hóa.
- **ECIES/HPKE:** Các họ sơ đồ mã hóa lai dùng cơ chế thỏa thuận/đóng gói khóa cùng KDF và AEAD theo một đặc tả cụ thể. Cách xây dựng và định dạng phụ thuộc chuẩn hoặc thư viện được sử dụng.
- **Ed25519/ECDSA:** Là cơ chế **chữ ký số**, không phải API dùng để mã hóa dữ liệu bằng public key.

Nên dùng **giao thức/thư viện mã hóa lai đã được thẩm định** thay vì tự thiết kế cấu trúc ECDH + HKDF + AES-GCM từ đầu. Cần kiểm tra khóa công khai, đúng nhóm/đường cong, tham số, ngữ cảnh và quyền hạn theo tài liệu giao thức.

### 4.3. KEM và mã hóa hậu lượng tử

**Key Encapsulation Mechanism (KEM)** tạo ra một bí mật chung cho hai bên thông qua một bản đóng gói (encapsulation) và private key dùng để giải đóng gói (decapsulation). Bí mật đó có thể trở thành đầu vào KDF để xây dựng khóa đối xứng bảo vệ dữ liệu.

Các cơ chế hậu lượng tử như **ML-KEM** được thiết kế cho mục tiêu này; kích thước public key/ciphertext của KEM **không phản ánh trực tiếp số bit an toàn** bằng cách đọc độ dài chuỗi. Với dữ liệu cần giữ bí mật dài hạn, tổ chức nên cân nhắc kế hoạch chuyển đổi sang các chuẩn mật mã phù hợp với rủi ro lượng tử và khả năng tương thích thực tế. **RSA và ECDH dựa trên các bài toán toán học truyền thống không được xem là hậu lượng tử.**

## 5. Vì sao nên dùng hybrid encryption?

**Hybrid encryption (mã hóa lai)** kết hợp hai loại cơ chế:

1. **Bất đối xứng:** Bảo vệ hoặc thiết lập **DEK (Data Encryption Key)** bằng public key của người nhận, thông qua RSA-OAEP hoặc cơ chế KEM/thỏa thuận khóa phù hợp.
2. **Đối xứng:** Sử dụng DEK để mã hóa phần nội dung lớn bằng **AEAD** như AES-GCM.

Sự kết hợp tận dụng ưu điểm của mã hóa bất đối xứng để tránh phải trao đổi sẵn khóa bí mật chung, đồng thời dùng mã hóa đối xứng hiệu quả cho nhiều dữ liệu.

~~~mermaid
flowchart TD
    P["Plaintext: hồ sơ/tệp cần gửi"] --> ENC["AES-GCM với DEK mới<br/>nonce duy nhất + AAD"]
    RNG["CSPRNG tạo DEK AES-256"] --> ENC
    RNG --> WRAP["RSA-OAEP mã hóa DEK<br/>bằng public key đã xác thực của B"]
    KEY["Public key của B<br/>đã xác minh danh tính"] --> WRAP
    ENC --> ENV["Envelope: ciphertext + tag + nonce + AAD metadata + wrapped DEK + key ID/version"]
    WRAP --> ENV
    ENV --> B["B nhận envelope"]
    B --> UNWRAP["Private key của B<br/>giải mã wrapped DEK"]
    UNWRAP --> DEC["AES-GCM kiểm tra tag/AAD<br/>và giải mã"]
    B --> DEC
    DEC --> OUT["Plaintext nếu xác thực hợp lệ"]
~~~

Sơ đồ minh họa **một biến thể mã hóa lai dựa trên RSA-OAEP**; các hệ thống khác có thể sử dụng KEM, HPKE hoặc KMS API với định dạng envelope riêng.

### 5.1. Luồng ghi và đọc dữ liệu

**Bên gửi A:**

1. Lấy public key của B và **xác minh đúng người nhận**, thuật toán/mục đích và trạng thái khóa.
2. Sinh **DEK** đủ ngẫu nhiên, ví dụ AES-256 (32 byte), bằng CSPRNG hoặc KMS/HSM.
3. Mã hóa nội dung bằng **AES-GCM** với một nonce đúng quy tắc; dùng AAD ràng buộc dữ liệu với ngữ cảnh đã được xác thực.
4. Mã hóa/wrap DEK bằng **public key của B** theo RSA-OAEP hoặc sơ đồ được chọn.
5. Gửi/lưu **ciphertext, tag, nonce, wrapped DEK, key ID, phiên bản và metadata cần thiết**, không gửi DEK rõ.

**Bên nhận B:**

1. Kiểm tra định dạng, danh tính, quyền truy cập và key ID/version; giới hạn kích thước đầu vào.
2. Dùng **private key tương ứng** giải mã/wrap reversal để khôi phục DEK.
3. Dùng DEK giải mã bằng AES-GCM với đúng nonce/AAD/tag; **từ chối toàn bộ kết quả nếu xác thực thất bại**.
4. Giảm thời gian giữ DEK rõ trong bộ nhớ; lưu log thao tác/key ID/kết quả mà không ghi DEK hay plaintext.

### 5.2. Phân biệt các vai trò khóa

| Khóa hoặc tham số | Vai trò | Quy tắc bảo vệ |
| --- | --- | --- |
| **Recipient public key** | Dùng để mã hóa/đóng gói DEK cho người nhận | Không bí mật; phải xác thực nguồn, danh tính và version |
| **Recipient private key** | Giải mã hoặc giải đóng gói DEK | Bí mật; giới hạn quyền giải mã, ưu tiên HSM/KMS phù hợp |
| **DEK** | Mã hóa dữ liệu bằng AEAD | Giữ bí mật; bảo vệ dưới dạng đã wrap khi lưu trữ; giới hạn thời gian tồn tại ở dạng rõ |
| **Nonce AES-GCM** | Phân biệt các lần mã hóa dưới cùng DEK | Không bí mật; **không được trùng với cùng DEK** |
| **Tag và AAD** | Xác minh bản mã và liên kết ngữ cảnh | Không phải khóa; phải xác thực đúng và tránh lộ dữ liệu nhạy cảm trong AAD |

Trong envelope encryption dùng KMS, **KEK** có thể là khóa đối xứng trong KMS/HSM hoặc một khóa bất đối xứng theo thiết kế. Public key RSA của người nhận **đang đảm nhận chức năng bảo vệ DEK**, nhưng không đồng nghĩa với mọi loại KEK trong các dịch vụ KMS.

## 6. Ví dụ Java: RSA-OAEP + AES-256-GCM

Ví dụ sau mô phỏng bên gửi sinh một **DEK AES-256**, mã hóa thông điệp bằng AES-GCM, rồi sử dụng **RSA-3072 public key của người nhận** để bọc DEK bằng RSA-OAEP. Bên nhận sử dụng RSA private key để khôi phục DEK và kiểm tra bản mã.

Ví dụ sinh cặp khóa trong chương trình để dễ hiểu. Trong production, cặp khóa người nhận phải được cấp phát và xác thực bằng cơ chế quản lý khóa thích hợp; private key có thể nằm trong KMS/HSM và không được xuất.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.spec.MGF1ParameterSpec;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;
import javax.crypto.spec.SecretKeySpec;

public class PublicKeyEncryptionDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final OAEPParameterSpec OAEP_SHA256 =
            new OAEPParameterSpec(
                    "SHA-256",
                    "MGF1",
                    MGF1ParameterSpec.SHA256,
                    PSource.PSpecified.DEFAULT
            );

    public static void main(String[] args) throws Exception {
        // Chỉ minh họa: B sinh cặp RSA; A phải xác thực public key của B.
        KeyPairGenerator rsaGenerator = KeyPairGenerator.getInstance("RSA");
        rsaGenerator.initialize(3072, RNG);
        KeyPair recipient = rsaGenerator.generateKeyPair();

        // A sinh DEK mới để mã hóa một thông điệp.
        KeyGenerator aesGenerator = KeyGenerator.getInstance("AES");
        aesGenerator.init(256, RNG);
        SecretKey dek = aesGenerator.generateKey();

        byte[] nonce = new byte[12]; // 96-bit nonce GCM
        RNG.nextBytes(nonce);
        byte[] aad = "recipient:B|document:42|version:1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Du lieu bi mat gui cho B"
                .getBytes(StandardCharsets.UTF_8);

        Cipher aesEncrypt = Cipher.getInstance("AES/GCM/NoPadding");
        aesEncrypt.init(Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(128, nonce));
        aesEncrypt.updateAAD(aad);
        byte[] ciphertextWithTag = aesEncrypt.doFinal(plaintext);

        // Bọc DEK bằng public key của B, không mã hóa dữ liệu lớn bằng RSA.
        Cipher rsaEncrypt = Cipher.getInstance("RSA/ECB/OAEPPadding");
        rsaEncrypt.init(Cipher.ENCRYPT_MODE,
                recipient.getPublic(), OAEP_SHA256);
        byte[] encodedDek = dek.getEncoded();
        byte[] wrappedDek;
        try {
            wrappedDek = rsaEncrypt.doFinal(encodedDek);
        } finally {
            Arrays.fill(encodedDek, (byte) 0); // Giảm lộ bản sao này.
        }

        // B dùng private key khôi phục DEK.
        Cipher rsaDecrypt = Cipher.getInstance("RSA/ECB/OAEPPadding");
        rsaDecrypt.init(Cipher.DECRYPT_MODE,
                recipient.getPrivate(), OAEP_SHA256);
        byte[] recoveredDekBytes = rsaDecrypt.doFinal(wrappedDek);
        SecretKey recoveredDek;
        try {
            recoveredDek = new SecretKeySpec(recoveredDekBytes, "AES");
        } finally {
            Arrays.fill(recoveredDekBytes, (byte) 0);
        }

        // B giải mã và kiểm tra tag với đúng nonce/AAD.
        Cipher aesDecrypt = Cipher.getInstance("AES/GCM/NoPadding");
        aesDecrypt.init(Cipher.DECRYPT_MODE, recoveredDek,
                new GCMParameterSpec(128, nonce));
        aesDecrypt.updateAAD(aad);
        byte[] restored = aesDecrypt.doFinal(ciphertextWithTag);

        System.out.println(new String(restored, StandardCharsets.UTF_8));
        // Production: không ghi plaintext hay khóa bí mật vào log.
    }
}
~~~

**Điểm cần hiểu trong ví dụ:**

1. RSA-3072 là kích thước modulus RSA của người nhận. Nó **không biến** DEK AES-256 thành khóa RSA và không tương đương 3072 bit mức bảo mật.
2. OAEP dùng **SHA-256 và MGF1/SHA-256 được khai báo tường minh**; tên `RSA/ECB/OAEPPadding` là quy ước tên transformation trong JCE, **không có nghĩa RSA đang mã hóa theo mode ECB của AES**.
3. AES-GCM dùng DEK 256 bit, nonce 96 bit, tag 128 bit. Đây là **ba đại lượng khác nhau**.
4. Kết quả `ciphertextWithTag` chứa bản mã và tag theo cách API JCE biểu diễn; khi lưu/truyền cần có định dạng envelope để bên nhận đọc đúng từng trường.
5. `Arrays.fill(...)` chỉ xóa một số **mảng byte do ứng dụng kiểm soát**; JVM hoặc provider có thể giữ bản sao nội bộ, nên không thể xem đó là bảo đảm xóa mọi vật liệu khóa khỏi bộ nhớ.
6. `getEncoded()` dùng được với khóa phần mềm được phép xuất. Với DEK hoặc private key được bảo vệ trong HSM/KMS, ứng dụng cần **API wrap/unwrap hoặc mã hóa/giải mã thích hợp của dịch vụ**.

**Giới hạn ví dụ:** Không triển khai PKI để xác thực public key, không có quy trình rotation, chống replay, persistence, kiểm tra quyền người dùng hoặc cấu hình HSM. Đây là ví dụ về nguyên lý. Khi xây hệ thống thật, nên ưu tiên các giao thức và thư viện được kiểm chứng, áp dụng chính sách thuật toán và mã hóa lai phù hợp.

## 7. Xác thực public key: bước không thể bỏ qua

Mô hình phân phối khóa là một phần của giao thức bảo mật. Có hai câu hỏi độc lập:

- **Khóa đúng về mặt toán học không?** Public key có định dạng và tham số hợp lệ cho thuật toán đang dùng?
- **Khóa thuộc đúng B không?** Nguồn khóa, danh tính, quyền sử dụng, hiệu lực và quan hệ tin cậy đã được xác minh?

Với hệ thống sử dụng chứng chỉ **X.509/PKI**, trình tự kiểm tra có thể gồm:

1. Thiết lập **trust anchor** được phê duyệt trước; không tin chứng chỉ chỉ vì nó tự ký.
2. Kiểm tra chuỗi chứng chỉ và chữ ký của CA trung gian theo bộ quy tắc PKI áp dụng.
3. Đối chiếu danh tính người nhận, hostname/SAN hoặc identifier phù hợp với yêu cầu.
4. Kiểm tra hiệu lực, mục đích sử dụng khóa (**Key Usage/Extended Key Usage**) và chính sách thu hồi phù hợp.
5. Kiểm tra khóa dùng đúng loại thuật toán, độ dài và trạng thái hiện hành; quản lý khi đổi chứng chỉ/public key.

Với key pinning, fingerprint phải đến từ **kênh tin cậy**, và hệ thống phải có quy trình chuyển khóa mới trước khi pin cũ hết hiệu lực. Nếu đối tác cấp public key qua API, nên kiểm tra nguồn cấp, xác thực kết nối và chính sách chấp nhận thay đổi khóa.

### Ví dụ tấn công thay public key

~~~mermaid
sequenceDiagram
    participant A as Bên gửi A
    participant M as Kẻ tấn công M
    participant B as Bên nhận B
    B-->>M: Public key của B bị chặn trên kênh phân phối
    M-->>A: Thay bằng public key của M
    A->>M: Ciphertext mã hóa cho public key của M
    Note over M: Dùng private key của M để đọc nội dung
    M->>B: Có thể chuyển tiếp dữ liệu khác hoặc ngắt luồng
~~~

**Lỗ hổng nằm ở xác thực public key**, không nằm ở việc RSA hay AES chưa đủ dài. Khi A xác minh đúng khóa của B trước khi mã hóa, kiểu thay thế đơn giản này phải bị từ chối.

## 8. Quản lý vòng đời public/private key

Khóa bất đối xứng cần được quản lý giống các khóa đối xứng ở các mục tiêu bí mật, toàn vẹn, sẵn sàng, kiểm soát truy cập và kiểm toán, nhưng có thêm đặc thù **phân phối public key và xác thực danh tính**.

| Giai đoạn | Việc cần thực hiện | Lỗi điển hình |
| --- | --- | --- |
| **Tạo** | Chọn thuật toán, độ mạnh và nguồn ngẫu nhiên phù hợp; sinh cặp khóa trong ranh giới tin cậy | Sinh private key yếu, dùng thuật toán lỗi thời hoặc cấu hình không được hỗ trợ |
| **Cấp phát / công bố** | Gắn public key với đúng danh tính, mục đích, key ID/version; phân phối qua kênh xác thực | Nhận public key không kiểm tra nguồn hoặc bỏ qua chuỗi chứng chỉ |
| **Lưu trữ** | Bảo vệ private key; quản lý backup/khôi phục theo chính sách; công bố public key hợp lệ | Đưa private key vào Git, container image, log, bản sao lưu không bảo vệ |
| **Sử dụng** | Giới hạn quyền Decrypt/Decapsulate, ràng buộc tenant và mục đích; kiểm tra quyền nghiệp vụ | Ứng dụng được giải mã mọi dữ liệu hoặc làm oracle khi xử lý lỗi |
| **Xoay vòng** | Tạo cặp khóa mới, xác thực/phân phối public key mới, duy trì khả năng đọc ciphertext cũ khi cần | Đổi public key trước khi người gửi cập nhật, xóa private key cũ quá sớm |
| **Thu hồi / vô hiệu hóa** | Chặn khóa bị lộ/hết tin cậy, cập nhật danh sách và bộ nhớ đệm theo cơ chế triển khai | Chỉ xóa file public key nhưng vẫn để private key/API giải mã hoạt động |
| **Hủy** | Kiểm kê dữ liệu còn phụ thuộc, đáp ứng yêu cầu retention/khôi phục rồi xử lý khóa/bản sao | Hủy private key khi còn ciphertext cần đọc |

### 8.1. Xoay vòng khóa người nhận

Giả sử B thay cặp RSA cũ bằng cặp mới:

1. Sinh cặp RSA mới trong KMS/HSM hoặc quy trình quản lý phù hợp.
2. Phát hành/phân phối **public key mới** có key ID/version và bằng chứng xác thực; xác định thời điểm người gửi bắt đầu sử dụng.
3. Bên gửi chuyển sang mã hóa dữ liệu mới bằng public key mới.
4. Bên nhận giữ private key cũ chỉ trong phạm vi cần thiết để đọc ciphertext lịch sử, nếu chính sách vẫn cho phép.
5. Với envelope encryption, có thể giải bọc **DEK cũ** bằng private key cũ rồi **wrap lại DEK bằng public key mới** nếu quy trình và bảo mật cho phép; không nhất thiết phải mã hóa lại dữ liệu bằng AES khi DEK không thay đổi.
6. Kiểm thử dữ liệu mới/cũ, backup, các bên gửi chưa cập nhật, quyền và log trước khi ngừng private key cũ.

**Nếu private key cũ đã bị lộ:** Kẻ tấn công có thể giải mã wrapped DEK cũ mà họ thu thập được. **Chỉ rewrap DEK bằng khóa mới không làm mất khả năng của kẻ đã biết DEK cũ**, cũng không thu hồi plaintext đã bị lấy. Cần đánh giá thay cả DEK và mã hóa lại dữ liệu bị ảnh hưởng, cùng thu hồi các quyền/phiên bị xâm phạm.

### 8.2. Backup và khả năng khôi phục

Mất private key có thể khiến dữ liệu đã mã hóa cho public key tương ứng không bao giờ khôi phục được. Cần xác định rõ yêu cầu **availability, recovery time và retention** ngay từ thiết kế. Bản sao lưu private key phải được bảo vệ ở mức tương đương khóa chính; việc sao lưu được hay không phụ thuộc chế độ **non-exportable**, KMS/HSM và phương án dự phòng được hỗ trợ. Hệ thống không được âm thầm hạ mức bảo mật để “khôi phục cho nhanh”.

## 9. KMS/HSM, kiểm soát truy cập và kiểm toán

Với khóa bất đối xứng dùng để giải mã DEK, KMS/HSM thường giúp:

- Sinh hoặc nhập khóa theo khả năng nền tảng; giữ **private key** trong ranh giới bảo vệ, hạn chế xuất khóa.
- Cung cấp thao tác mật mã như **Decrypt/Decapsulate** theo **key ID, thuật toán, phiên bản và quyền** được cấp.
- Tách **quyền quản trị khóa** khỏi **quyền dùng khóa**. Một nhân viên quản trị không đương nhiên được xem DEK rõ hoặc dữ liệu nghiệp vụ.
- Ghi audit log cho các hành động tạo, dùng, thay policy, vô hiệu hóa, xóa hoặc khôi phục khóa theo khả năng hệ thống.

### 9.1. Quyền sử dụng phải đi cùng quyền nghiệp vụ

Ví dụ, ứng dụng Java lưu dữ liệu hai tenant A và B. Dù KMS giữ private key không xuất được, một workload có quyền gọi `Decrypt` trên khóa của **cả hai tenant** có thể trở thành điểm lộ dữ liệu nếu bị chiếm quyền. Nên ràng buộc khóa, workload, môi trường, mục đích và giới hạn truy cập ở tầng ứng dụng.

**Luồng hợp lệ:** Người dùng đã được xác thực → ứng dụng kiểm tra quyền xem bản ghi → workload gọi KMS giải bọc DEK trong phạm vi được cấp → xác minh AEAD → cung cấp đúng dữ liệu. Audit log ghi key ID, actor/workload, thao tác, thời gian, quyết định và kết quả, **không ghi private key, DEK hay plaintext**.

### 9.2. Những rủi ro dù khóa nằm trong HSM

**Non-exportable** làm giảm khả năng trích xuất private key nhưng không ngăn mọi cách tấn công. Nếu ứng dụng có thể đưa ciphertext tùy ý tới API giải mã và đọc kết quả, nó có thể lạm dụng quyền đó. Cần thực thi quyền tối thiểu, xác thực nguồn yêu cầu, bảo vệ dịch vụ khỏi oracle, hạn chế tốc độ khi phù hợp và cảnh báo các mẫu Decrypt bất thường.

Ngoài ra, lỗi cấu hình certificate, khóa công khai bị thay thế, phiên bản không khớp hoặc mất backup vẫn có thể làm hệ thống mất bảo mật hoặc tính sẵn sàng dù vật liệu private key không bị lộ.

## 10. Các quyết định thiết kế thường gặp

| Tình huống | Phương án nên cân nhắc | Điểm cần kiểm tra |
| --- | --- | --- |
| Gửi một DEK AES cho người nhận có public key RSA đã được xác thực | **RSA-OAEP** wrap DEK, sau đó AES-GCM cho payload | Tham số OAEP, key ID, quyền private key, định dạng envelope |
| Mã hóa tệp lớn nhiều MB/GB | **Hybrid encryption** với AEAD | Không mã hóa cả tệp bằng RSA; quản lý nonce/tag, phân đoạn và giới hạn dữ liệu |
| Giao thức mới trên mạng cần thiết lập khóa phiên | Cơ chế **thỏa thuận khóa / KEM** theo giao thức được thẩm định | Xác thực peer, KDF, key confirmation và tính chất forward secrecy |
| Mã hóa cho nhiều người nhận | Mỗi người nhận có một phần wrapped DEK riêng hoặc dùng giao thức nhiều người nhận | Quyền, metadata, danh sách người nhận và thu hồi quyền |
| Dùng ECC với API “Encrypt” | Chọn **HPKE/ECIES hoặc KEM** có đặc tả phù hợp | Không dùng ECDSA/Ed25519 để mã hóa; không tự ghép primitives |
| Cần xác thực tác giả thông điệp | Bổ sung **chữ ký số hoặc cơ chế xác thực sender** | Public key encryption tự nó không xác minh người gửi |
| Cần giữ bí mật nhiều năm trước nguy cơ lượng tử | Lập kế hoạch crypto agility và đánh giá cơ chế hậu lượng tử phù hợp | RSA/ECDH không kháng lượng tử; kiểm tra tiêu chuẩn, SDK, KMS và migration |

## 11. Các lỗi dễ mắc và cách phòng tránh

| Lỗi | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Nhận public key qua kênh không xác thực rồi mã hóa ngay | Kẻ tấn công thay public key và đọc nội dung | Kiểm tra chứng chỉ/định danh/fingerprint qua nguồn tin cậy |
| Dùng RSA thô hoặc padding yếu | Có thể bị tấn công theo cấu trúc toán học hay oracle | Dùng sơ đồ an toàn như RSA-OAEP đúng tham số và xử lý lỗi |
| Dùng RSA trực tiếp để mã hóa bản ghi dài | Vượt giới hạn RSA-OAEP, chậm và khó vận hành | Mã hóa lai: RSA bảo vệ DEK, AES-GCM bảo vệ payload |
| Cho rằng mã hóa bằng public key xác thực người gửi | Bất kỳ ai có public key đều tạo ciphertext | Bổ sung chữ ký/giao thức xác thực sender |
| Dùng public key cũ sau khi bị thu hồi | Tiếp tục mã hóa cho khóa không còn tin cậy | Theo dõi key ID/version, hiệu lực, trạng thái và cập nhật phân phối |
| Lưu private key trong repository hoặc container image | Mất bí mật và ảnh hưởng hàng loạt dữ liệu | Bảo vệ bằng KMS/HSM hoặc kho an toàn, xoay vòng khi lộ |
| Cho mọi workload quyền gọi Decrypt | Một tài khoản bị chiếm có thể giải mã phạm vi rộng | Least privilege, tách tenant và quyền nghiệp vụ |
| Không quản lý nonce/AAD của AES-GCM | Hỏng bí mật/tính toàn vẹn hoặc liên kết sai bản ghi | Nonce duy nhất dưới mỗi DEK, ràng buộc và kiểm tra AAD |
| Xóa private key cũ ngay sau khi xoay vòng | Dữ liệu lịch sử không thể giải mã | Migration, backup, kiểm thử truy cập trước khi hủy |
| Chỉ rewrap khi private key cũ đã lộ | DEK cũ có thể đã bị lấy hoặc vẫn giải mã được từ envelope cũ | Đánh giá thay DEK, mã hóa lại dữ liệu và phạm vi sự cố |
| Ghi raw DEK hoặc plaintext vào audit log | Log trở thành kho bí mật có thể bị lộ | Chỉ ghi ID, hành động, đối tượng và kết quả cần thiết |
| Nghĩ RSA-OAEP có forward secrecy tự động | Lộ private key sau này có thể giải mã ciphertext cũ bị lưu lại | Dùng giao thức thiết lập khóa có tính chất phù hợp, quản lý vòng đời khóa |

## 12. Checklist đánh giá public key encryption

Khi review một hệ thống, hãy trả lời:

1. **Mục đích:** Hệ thống đang mã hóa dữ liệu, bọc DEK, xác thực bằng chữ ký hay thỏa thuận khóa? Có chọn đúng primitive không?
2. **Người nhận:** Public key có được xác minh thuộc đúng người nhận, đúng mục đích và còn hiệu lực không?
3. **Thuật toán:** Có dùng RSA-OAEP/HPKE/KEM hoặc sơ đồ được phê duyệt, với tham số và thư viện phù hợp không?
4. **Kích thước:** Độ mạnh của khóa RSA/ECC có đáp ứng thời hạn bảo vệ, chính sách và rủi ro hiện tại không?
5. **Dữ liệu:** Có dùng hybrid encryption cho payload lớn, với AEAD và DEK ngẫu nhiên phù hợp không?
6. **Toàn vẹn:** Nonce/tag/AAD được quản lý đúng và kiểm tra trước khi trả plaintext? Có bảo vệ replay nếu nghiệp vụ cần không?
7. **Private key:** Khóa bí mật được lưu ở đâu, có bị xuất vào log/dump/code không, ai có quyền sử dụng và khôi phục?
8. **Phân quyền:** Quyền giải mã tại KMS/HSM và quyền xem dữ liệu ở ứng dụng có giới hạn theo tenant, workload và mục đích không?
9. **Phiên bản:** Envelope có đủ key ID/version, thuật toán, tham số và metadata để đọc ciphertext cũ sau rotation không?
10. **Sự cố và hủy:** Có kế hoạch khi public key bị đánh tráo hoặc private key bị lộ/mất; đã thử migration, backup và kiểm toán chưa?

## 13. Ghi nhớ

- **Public key encryption** dùng **public key của người nhận để mã hóa** và **private key tương ứng để giải mã**. Bí mật của private key và **xác thực public key** đều thiết yếu.
- **Mã hóa không tự chứng minh danh tính người gửi**; chữ ký số hoặc cơ chế xác thực sender giải quyết mục tiêu khác.
- **RSA-OAEP** phù hợp để bảo vệ dữ liệu nhỏ như DEK. Với dữ liệu lớn, ưu tiên **hybrid encryption**: bất đối xứng bảo vệ DEK, **AEAD như AES-GCM** bảo vệ nội dung.
- **ECC/DH/KEM** là những cơ chế khác RSA-OAEP; lựa chọn đúng giao thức và KDF, không nhầm khóa ký số với khóa mã hóa.
- **KMS/HSM, least privilege, key ID/version, kiểm toán, rotation, thu hồi và hủy** giữ hệ thống an toàn xuyên suốt vòng đời khóa.
- **Tăng độ dài RSA hoặc AES không sửa được** việc phát sai public key, lộ private key, phân quyền quá rộng, tái sử dụng nonce hoặc xóa khóa còn dữ liệu phụ thuộc.

Khi thiết kế public key encryption, câu hỏi đầu tiên nên là: **“Tôi đã xác thực đúng public key của người nhận chưa, và nếu private key bị lộ hoặc bị mất thì những bản mã, DEK và dịch vụ nào sẽ chịu ảnh hưởng?”** Câu trả lời dẫn đến thiết kế đúng về mã hóa, phân phối khóa, kiểm soát truy cập và khôi phục.
