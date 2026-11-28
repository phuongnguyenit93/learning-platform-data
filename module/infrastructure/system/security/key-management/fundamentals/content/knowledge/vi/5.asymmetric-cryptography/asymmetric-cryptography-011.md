# Hybrid encryption: Kết hợp mật mã bất đối xứng và đối xứng

Giả sử dịch vụ A cần gửi một tệp 200 MB chứa dữ liệu khách hàng cho đối tác B. B có một cặp khóa RSA; A biết public key của B nhưng không có khóa bí mật chung. Dùng RSA để mã hóa trực tiếp cả tệp là không phù hợp: các sơ đồ như RSA-OAEP chỉ mã hóa được lượng dữ liệu nhỏ mỗi phép toán, còn chi phí xử lý cao hơn mã hóa đối xứng. Ngược lại, dùng AES-GCM để mã hóa tệp rất hiệu quả nhưng A và B lại chưa chia sẻ được khóa AES.

**Hybrid encryption (mã hóa lai)** giải quyết hai vấn đề này bằng cách **kết hợp một cơ chế khóa bất đối xứng để thiết lập hoặc bảo vệ khóa dữ liệu** với **mã hóa đối xứng để bảo vệ nội dung**. Bên gửi có thể sinh một **Data Encryption Key (DEK)** AES ngẫu nhiên, dùng DEK mã hóa tệp bằng AES-GCM, rồi mã hóa/bọc DEK cho public key đáng tin cậy của bên nhận. Chỉ bên có quyền dùng private key tương ứng mới khôi phục được DEK để giải mã dữ liệu.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, hybrid encryption là ứng dụng quan trọng của cả mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM và envelope encryption. Để vận hành an toàn phải quản lý đầy đủ vòng đời khóa từ tạo, cấp phát, lưu trữ, sử dụng, xoay vòng tới thu hồi và hủy, đồng thời thiết lập phân quyền và kiểm toán.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích tại sao mã hóa lai cần cả **key establishment/key protection** và **symmetric authenticated encryption**.
2. Phân biệt **DEK**, **KEK**, public/private key, **encrypted/wrapped DEK**, nonce, tag, AAD và metadata.
3. So sánh hybrid encryption dựa trên **RSA-OAEP** với thiết kế dựa trên **KEM + KDF + AEAD**, đồng thời phân biệt với key agreement.
4. Mô tả một gói dữ liệu mã hóa có đủ thông tin để bên nhận khôi phục mà không làm lộ key material.
5. Triển khai một ví dụ Java 17 kết hợp **RSA-OAEP/SHA-256** và **AES-256-GCM**, có kiểm tra tính xác thực của AAD.
6. Thiết kế phân phối public key, KMS/HSM, phân quyền, audit, rotation, recovery và ứng phó khi khóa bị lộ.

## 2. Tại sao phải kết hợp hai hệ mật mã?

### 2.1. Vai trò của từng thành phần

| Thành phần | Công việc trong mã hóa lai | Tại sao dùng? |
|---|---|---|
| **Public-key encryption/KEM/key establishment** | Bảo vệ DEK hoặc thiết lập bí mật để dẫn xuất DEK | Không cần hai bên trao đổi sẵn một DEK bản rõ |
| **Private key bên nhận** | Giải mã wrapped DEK hoặc decapsulate để lấy shared secret | Chỉ thực thể được ủy quyền có thể khôi phục khóa theo thiết kế |
| **DEK đối xứng** | Mã hóa payload lớn bằng AEAD như AES-GCM | Hiệu quả với dữ liệu lớn và có cơ chế xác thực dữ liệu |
| **Nonce + authentication tag + AAD** | Cung cấp đầu vào và bằng chứng xác thực cho AEAD | Phát hiện sửa đổi bản mã và ràng buộc các trường ngữ cảnh |
| **Metadata của gói** | Ghi phiên bản, thuật toán, key reference, thông tin định dạng | Giúp bên nhận chọn đúng khóa/cách giải mã và vận hành qua các lần rotation |

Không nên mô tả hybrid encryption đơn giản là “mã hóa bằng AES rồi mã hóa bằng RSA thêm một lần nữa”. Bản mã **dữ liệu** thường chỉ được tạo bằng AES-GCM; cơ chế bất đối xứng được dùng để **bảo vệ khóa AES hoặc thiết lập khóa**.

### 2.2. Luồng tổng quát

~~~mermaid
flowchart TD
    P["Plaintext: tệp hoặc bản ghi"] --> G["AES-GCM Encrypt"]
    D["DEK AES ngẫu nhiên"] --> G
    N["Nonce mới + AAD"] --> G
    G --> C["Ciphertext + authentication tag"]
    R["Public key đáng tin cậy của B"] --> W["RSA-OAEP Wrap DEK"]
    D --> W
    W --> E["Encrypted/wrapped DEK"]
    C --> O["Encryption envelope"]
    E --> O
    N --> O
    M["Version + algorithm + keyId + context"] --> O
    O --> X["Truyền/lưu gói được bảo vệ"]
    X --> U["B: dùng private key được cấp quyền để unwrap DEK"]
    U --> V["AES-GCM Verify tag và giải mã"]
    V --> Q["Plaintext chỉ khi xác thực thành công"]
~~~

**Public key phải được xác thực là của B trước khi A mã hóa DEK.** Nếu kẻ tấn công thay public key của B bằng khóa của mình, A có thể mã hóa DEK cho chính kẻ tấn công dù cả RSA-OAEP và AES-GCM đều được triển khai đúng.

### 2.3. Ví dụ với tệp 200 MB

Bên gửi thực hiện hai nhóm thao tác:

1. Sinh một DEK AES-256 bằng bộ sinh số ngẫu nhiên mật mã (**CSPRNG**), rồi mã hóa tệp bằng AEAD có chiến lược nonce và AAD an toàn.
2. Mã hóa/bọc **DEK 32 byte** bằng RSA-OAEP theo public key của B, thay vì đưa cả tệp 200 MB vào RSA.

Bên nhận khôi phục DEK bằng private key rồi giải mã tệp sau khi hoàn tất kiểm tra xác thực. Bản thân RSA-OAEP không cung cấp xác thực người gửi; nếu yêu cầu chứng minh A là người gửi, cần thêm **chữ ký số hoặc cơ chế xác thực giao thức** thích hợp.

## 3. Mô hình KEM/DEM và các biến thể

Trong tài liệu mật mã, hybrid encryption thường được trình bày theo mô hình **KEM/DEM**:

- **KEM (Key Encapsulation Mechanism):** tạo bí mật chung và ciphertext đóng gói; bên nhận dùng private key decapsulate để lấy cùng bí mật. Bí mật thường được đưa qua **KDF** với ngữ cảnh phù hợp để tạo keying material.
- **DEM (Data Encapsulation Mechanism):** dùng keying material để bảo vệ dữ liệu. Trong thiết kế hiện đại, DEM thường là một **AEAD** như AES-GCM hoặc ChaCha20-Poly1305.

Một cách biểu diễn:

~~~text
Sender:
    (kemCiphertext, sharedSecret) = KEM.Encapsulate(recipientPublicKey)
    dek = KDF(sharedSecret, algorithmId || recipientId || context)
    (ciphertext, tag) = AEAD.Encrypt(dek, nonce, plaintext, aad)
    envelope = kemCiphertext || nonce || ciphertext || tag || metadata

Recipient:
    sharedSecret = KEM.Decapsulate(recipientPrivateKey, kemCiphertext)
    dek = KDF(sharedSecret, same context)
    plaintext = AEAD.DecryptAndVerify(dek, nonce, ciphertext, tag, aad)
~~~

Đây là **pseudocode khái niệm**, không phải API của một KEM cụ thể. Các giao thức như **HPKE (Hybrid Public Key Encryption, RFC 9180)** xác định cách kết hợp KEM, KDF và AEAD cùng định dạng, tham số và ngữ cảnh được chuẩn hóa. Khi có thư viện/giao thức chuẩn phù hợp, nên dùng thay vì tự xây protocol.

### 3.1. RSA-OAEP khác KEM chuẩn như thế nào?

| Tiêu chí | RSA-OAEP mã hóa DEK trực tiếp | KEM + KDF + AEAD |
|---|---|---|
| Đầu vào khóa | Bên gửi **tự sinh DEK**, mã hóa DEK bằng public key B | KEM tạo ra **shared secret** khi encapsulate, sau đó dẫn xuất DEK bằng KDF |
| Đầu ra chuyển giao | RSA-OAEP ciphertext của DEK | KEM ciphertext và AEAD ciphertext |
| Bên nhận | RSA private key giải mã đúng DEK | Private key decapsulate, KDF tạo cùng DEK |
| Điểm cần chuẩn hóa | OAEP hash, MGF, key size, định dạng, AAD, xác thực public key | KEM suite, KDF, AEAD, info/context, định dạng và xác thực public key |
| Xác thực người gửi | **Không tự có** | **Không tự có trong chế độ cơ bản (base mode)**; tùy giao thức/chế độ xác thực |
| Forward secrecy khi lộ private key nhận dài hạn | **Không mặc nhiên có** | **Không mặc nhiên có** nếu gói cũ có thể decapsulate bằng private key nhận đã lộ |

Không gọi mọi thuật toán **ECDH/X25519** đơn lẻ là một KEM hoàn chỉnh. ECDH là phép thỏa thuận khóa; để thành giao thức mã hóa lai cần xác thực peer, cách tạo ephemeral key, xử lý shared secret, KDF, AEAD, định dạng và kiểm tra đầu vào. Trong nhiều thiết kế, giao thức cấp cao đã làm những việc đó và ứng dụng không nên tự ghép các primitive.

### 3.2. Phân biệt với TLS

Một kết nối **TLS 1.3** thường dùng trao đổi khóa tạm thời để thiết lập các khóa lưu lượng AEAD, và chứng thư/chữ ký để xác thực đầu mút. Đây là một giao thức bảo mật kênh; nó có thể là ví dụ về việc **phối hợp cơ chế bất đối xứng và đối xứng**, nhưng **bảo vệ kênh truyền không thay thế mã hóa payload để lưu dài hạn**.

Nếu một tệp được gửi qua HTTPS rồi lưu vào database dưới dạng plaintext, TLS chỉ bảo vệ tệp trong quá trình truyền. Với yêu cầu bảo mật dữ liệu ở nơi lưu hoặc giữa các miền tin cậy, cần mã hóa ở tầng dữ liệu, cùng quy tắc quản lý DEK/KEK tương ứng.

## 4. Hybrid encryption và envelope encryption giống, khác ở đâu?

**Envelope encryption** là mô hình dùng **DEK** để mã hóa dữ liệu và dùng một khóa/cơ chế khác bảo vệ DEK. Khi DEK được bảo vệ bằng **public key bất đối xứng**, thiết kế vừa là envelope encryption vừa là hybrid encryption. Nhưng envelope encryption **không bắt buộc** có mật mã bất đối xứng: một KEK đối xứng trong KMS cũng có thể wrap DEK.

| Mô hình | Khóa bảo vệ DEK | Ai phục hồi DEK? | Loại hình |
|---|---|---|---|
| **RSA-OAEP + AES-GCM** | Public key RSA của người nhận | Private key RSA tương ứng | Hybrid encryption; envelope encryption |
| **HPKE/KEM + AEAD** | KEM tạo shared secret, KDF dẫn xuất AEAD key | Recipient decapsulate bằng private key | Hybrid encryption theo KEM/DEM |
| **AES-KW + AES-GCM** | KEK đối xứng (ví dụ trong KMS/HSM) | Thực thể có quyền Unwrap với KEK | Envelope encryption, **không nhất thiết** là asymmetric hybrid |

**Không đánh đồng KEK với private key.** Trong envelope encryption đối xứng, KEK thường là khóa bí mật dùng chung hoặc khóa nội bộ của KMS; trong hybrid encryption kiểu RSA, private key của người nhận là phần bí mật dùng khôi phục DEK. Quyền **Unwrap/Decrypt**, khả năng export và vòng đời khác nhau theo mô hình.

## 5. Những thành phần bắt buộc của một encryption envelope

Một gói dữ liệu mã hóa phải đủ để bên nhận biết **thuật toán, khóa, phiên bản, nonce và các byte cần kiểm tra**.

| Thành phần | Bản chất | Bí mật? | Lưu ý an ninh |
|---|---|---|---|
| **Private key người nhận** | Key material bất đối xứng | **Có** | Giữ bí mật; ưu tiên KMS/HSM, hạn chế export và quyền Decrypt |
| **Public key người nhận** | Key material công khai | Không | **Phải xác thực** người sở hữu, tính toàn vẹn và quyền sử dụng |
| **DEK bản rõ** | Key material đối xứng | **Có** | Sinh ngẫu nhiên, dùng trong bộ nhớ tin cậy trong thời gian ngắn |
| **Encrypted/wrapped DEK** | Key material đã mã hóa | Cần bảo vệ phù hợp | Không phải metadata vô hại; tránh quyền đọc/unwrap tùy ý |
| **Ciphertext + tag** | Dữ liệu đã mã hóa kèm xác thực | Không cần bí mật theo nghĩa key | Phải xác minh tag trước khi sử dụng plaintext |
| **Nonce/IV** | Tham số của AEAD | Không | Với AES-GCM, phải **không trùng trong phạm vi cùng DEK** |
| **AAD** | Ngữ cảnh được xác thực nhưng không mã hóa | Không | Ràng buộc tenant, record ID, version hoặc header nếu cần |
| **keyId, keyVersion, algorithm, formatVersion** | Metadata | Thường không | Validate, tránh thuật toán bị hạ cấp, resolve đúng khóa lịch sử |
| **Sender authentication proof** | Chữ ký số hoặc kết quả giao thức xác thực | Không phải bí mật | Chỉ cần và có giá trị khi public key/xuất xứ được tin cậy |

Một JSON envelope có thể có dạng minh họa:

~~~json
{
  "formatVersion": 1,
  "contentAlgorithm": "AES-256-GCM",
  "keyProtectionAlgorithm": "RSA-OAEP-SHA256-MGF1SHA256",
  "recipientKeyId": "partner-b-encryption",
  "recipientKeyVersion": "v4",
  "encryptedDek": "<BASE64_RSA_OAEP_CIPHERTEXT>",
  "nonce": "<BASE64_12_BYTE_NONCE>",
  "ciphertextWithTag": "<BASE64_CIPHERTEXT_PLUS_16_BYTE_TAG>",
  "aadContext": {
    "tenantId": "tenant-42",
    "recordId": "document-123"
  }
}
~~~

**Mọi chuỗi Base64 trên chỉ là placeholder**, không phải khóa hoặc bản mã thật. Base64 là một cách biểu diễn byte, **không phải thuật toán mã hóa bảo mật**.

### 5.1. Ràng buộc metadata đúng cách

AES-GCM xác thực **AAD** và ciphertext thông qua authentication tag. Nếu đặt **recipientKeyId** ngoài gói mà không ràng buộc nó vào dữ liệu được bảo vệ, kẻ tấn công có thể thay tham chiếu và làm hệ thống chọn sai khóa hoặc gây lỗi; nguy hiểm hơn nếu ứng dụng tin các trường không được xác thực để đưa ra quyết định phân quyền.

Thiết kế nên đưa **formatVersion, algorithm, key ID/version, tenant ID, record ID** có ý nghĩa an ninh vào AAD ở định dạng byte **có quy tắc và không nhập nhằng**, sau đó đối chiếu với ngữ cảnh **đã xác thực**. Tuy nhiên, việc đưa một trường vào AAD không tự khiến giá trị đó đáng tin: người gọi không được tự khai tenantId của người khác rồi yêu cầu giải mã.

Ngoài ra, AEAD chỉ xác thực nội dung **sau khi có được DEK phù hợp**. Nếu cần xác thực **toàn bộ envelope trước khi mở khóa** hoặc xác thực **người gửi**, có thể cần chữ ký/MAC hoặc cơ chế giao thức riêng bao phủ các phần liên quan. Đối với chữ ký, phải xác định chính xác **byte nào được ký**, quy tắc canonicalization, key ID của người ký và nguồn public key tin cậy.

### 5.2. Replay và tính toàn vẹn dữ liệu

Một gói envelope hợp lệ có thể được phát lại mà **AES-GCM vẫn xác minh tag thành công**. AEAD không cung cấp chống replay. Những quy trình như thanh toán, lệnh điều khiển hoặc cập nhật hồ sơ phải có **message ID, sequence, phiên bản bản ghi, thời hạn và kiểm tra idempotency** ở tầng nghiệp vụ.

Tag cũng **không phải chữ ký số**: bất kỳ bên nào có DEK đều có thể tạo một bản mã/tag hợp lệ. Nếu cần chứng minh bản gửi đến từ A theo nghĩa xác thực bất đối xứng, hãy sử dụng một cơ chế chữ ký/chứng thực nguồn được thiết kế rõ ràng.

## 6. Ví dụ Java 17: RSA-OAEP bảo vệ DEK và AES-256-GCM mã hóa dữ liệu

Ví dụ sau dùng **Java Cryptography Architecture (JCA)** và JDK 17+ để minh họa đường đi của key material. Bên gửi có **public key đã được xác thực** của người nhận, tạo DEK AES-256 ngẫu nhiên, mã hóa payload bằng AES-GCM và **wrap DEK** bằng RSA-OAEP. Bên nhận **unwrap DEK** bằng private key rồi xác minh tag GCM.

Đoạn mã chạy trong một JVM chỉ để dễ quan sát, không phải dịch vụ KMS hoàn chỉnh. Cặp RSA được sinh mới trong demo; ở production, private key của bên nhận nên được bảo vệ bằng KMS/HSM hoặc kho khóa phù hợp và public key phải đến từ nguồn tin cậy.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.spec.MGF1ParameterSpec;
import java.util.Base64;
import java.util.List;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public final class HybridEncryptionExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int NONCE_BYTES = 12;  // 96-bit GCM nonce
    private static final int TAG_BITS = 128;
    private static final String KEY_ID = "partner-b-key";
    private static final String KEY_VERSION = "v1";

    private static final OAEPParameterSpec OAEP_SHA256 =
            new OAEPParameterSpec(
                    "SHA-256", "MGF1",
                    MGF1ParameterSpec.SHA256, PSource.PSpecified.DEFAULT);

    public record Envelope(
            String recipientKeyId,
            String recipientKeyVersion,
            String encryptedDekBase64,
            String nonceBase64,
            String ciphertextWithTagBase64
    ) {}

    // AAD có format và prefix độ dài, tránh nhập nhằng trường.
    private static byte[] aad(String tenantId, String recordId,
                              String keyId, String keyVersion)
            throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try (DataOutputStream data = new DataOutputStream(out)) {
            for (String value : List.of(
                    "envelope-format-v1", "AES-256-GCM",
                    "RSA-OAEP-SHA256-MGF1SHA256",
                    tenantId, recordId, keyId, keyVersion)) {
                byte[] encoded = value.getBytes(StandardCharsets.UTF_8);
                data.writeInt(encoded.length);
                data.write(encoded);
            }
        }
        return out.toByteArray();
    }

    public static Envelope encrypt(
            PublicKey trustedRecipientKey,
            String authenticatedTenant,
            String recordId,
            byte[] plaintext) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey dek = generator.generateKey();

        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
        aes.init(Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, nonce));
        aes.updateAAD(aad(authenticatedTenant, recordId,
                KEY_ID, KEY_VERSION));
        byte[] ciphertextWithTag = aes.doFinal(plaintext);

        // OAEP digest và MGF1 digest được cấu hình rõ ràng.
        Cipher rsa = Cipher.getInstance("RSA/ECB/OAEPPadding");
        rsa.init(Cipher.WRAP_MODE, trustedRecipientKey, OAEP_SHA256);
        byte[] encryptedDek = rsa.wrap(dek);

        return new Envelope(
                KEY_ID,
                KEY_VERSION,
                Base64.getEncoder().encodeToString(encryptedDek),
                Base64.getEncoder().encodeToString(nonce),
                Base64.getEncoder().encodeToString(ciphertextWithTag));
    }

    public static byte[] decrypt(
            PrivateKey authorizedRecipientKey,
            String authenticatedTenant,
            String recordId,
            Envelope envelope) throws Exception {
        // Trong production phải resolve keyId/version và kiểm tra quyền
        // từ registry/KMS tin cậy trước khi gọi phương thức này.
        if (!KEY_ID.equals(envelope.recipientKeyId())
                || !KEY_VERSION.equals(envelope.recipientKeyVersion())) {
            throw new IllegalArgumentException("Unexpected key reference");
        }

        byte[] nonce = Base64.getDecoder()
                .decode(envelope.nonceBase64());
        if (nonce.length != NONCE_BYTES) {
            throw new IllegalArgumentException("Invalid GCM nonce");
        }

        byte[] ciphertextWithTag = Base64.getDecoder()
                .decode(envelope.ciphertextWithTagBase64());
        if (ciphertextWithTag.length < TAG_BITS / 8) {
            throw new IllegalArgumentException("Missing GCM tag");
        }

        Cipher rsa = Cipher.getInstance("RSA/ECB/OAEPPadding");
        rsa.init(Cipher.UNWRAP_MODE, authorizedRecipientKey, OAEP_SHA256);
        byte[] encryptedDek = Base64.getDecoder()
                .decode(envelope.encryptedDekBase64());
        SecretKey dek = (SecretKey) rsa.unwrap(
                encryptedDek, "AES", Cipher.SECRET_KEY);

        Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
        aes.init(Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, nonce));
        aes.updateAAD(aad(authenticatedTenant, recordId,
                envelope.recipientKeyId(),
                envelope.recipientKeyVersion()));
        return aes.doFinal(ciphertextWithTag); // Phải kiểm tra tag
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072);
        KeyPair recipient = generator.generateKeyPair();

        // Bên gửi đã xác thực public key của recipient ở ngoài demo.
        Envelope stored = encrypt(
                recipient.getPublic(), "tenant-42", "document-123",
                "Tệp mật cần bảo vệ".getBytes(StandardCharsets.UTF_8));

        byte[] restored = decrypt(
                recipient.getPrivate(), "tenant-42", "document-123", stored);
        System.out.println(new String(restored, StandardCharsets.UTF_8));

        try {
            decrypt(recipient.getPrivate(), "tenant-OTHER",
                    "document-123", stored);
            throw new IllegalStateException("Expected AAD rejection");
        } catch (AEADBadTagException expected) {
            System.out.println("Wrong tenant AAD rejected");
        }

        // Demo mới in plaintext giả. Không log DEK, private key
        // hoặc plaintext dữ liệu thật trong ứng dụng.
    }
}
~~~

Lưu thành **HybridEncryptionExample.java** rồi chạy:

~~~bash
javac HybridEncryptionExample.java
java HybridEncryptionExample
~~~

Trên JDK 17 có provider hỗ trợ các biến đổi trên, kết quả kỳ vọng gồm nội dung demo đã giải mã và dòng **Wrong tenant AAD rejected**. Bản mã và encrypted DEK sẽ thay đổi qua các lần chạy vì chương trình sinh khóa mới và nonce ngẫu nhiên.

### 6.1. Tại sao đoạn mã dùng RSA-OAEP thay vì RSA tự viết?

- **RSA-OAEP** là sơ đồ mã hóa có padding được thiết kế cho khóa công khai; mã không thực hiện phép RSA raw và không tự nghĩ ra padding.
- Cấu hình **OAEPParameterSpec** đặt rõ digest **SHA-256** và digest của **MGF1 là SHA-256**. Nếu hai bên dùng MGF1 khác nhau, unwrap có thể thất bại.
- Với RSA 3072 bit và OAEP SHA-256, giới hạn plaintext cho một phép mã hóa là **384 − 2×32 − 2 = 318 byte**. DEK AES-256 dài **32 byte**, nên phù hợp; tệp lớn thì không.
- **Cipher.WRAP_MODE/UNWRAP_MODE** giúp diễn đạt chính xác việc bảo vệ một **khóa**, thay vì mã hóa một tài liệu lớn bằng RSA.

### 6.2. Những giới hạn của ví dụ

1. **Niềm tin vào public key được giả định sẵn.** Demo lấy public key từ cặp mới sinh. Production phải có chứng thư/PKI, trust store, pinning hoặc kênh phân phối được xác thực.
2. **Không có KMS/HSM thực.** Private key nằm trong JVM để minh họa. Provider KMS/HSM có thể chỉ cho phép thao tác Decrypt/Unwrap qua key handle và API riêng; không phải khóa nào cũng export/import được.
3. **Không có danh sách phiên bản lịch sử.** Demo đặt KEY_ID và KEY_VERSION cố định. Trong production, dịch vụ giải mã phải resolve đúng khóa theo metadata đã xác thực, phiên bản, tenant và policy.
4. **AAD được tái tạo từ ngữ cảnh tin cậy.** Đoạn mã yêu cầu tenant và record ID từ caller đã được xác thực. Chỉ lấy hai giá trị từ request chưa kiểm tra là không đủ.
5. **Không xác thực người gửi.** Có public key của B thì bất kỳ ai cũng có thể tạo một envelope mới cho B. Nếu cần chỉ nhận dữ liệu từ A, thêm chữ ký số hoặc cơ chế xác thực giao thức.
6. **Chống replay chưa được triển khai.** Cùng một envelope nguyên vẹn vẫn có thể giải mã lại. Hệ thống nghiệp vụ phải quản lý message ID, sequence và trạng thái xử lý.
7. **Không thể kiểm soát mọi byte trong bộ nhớ Java.** Trong ví dụ, DEK, plaintext và khóa tồn tại trong heap để đơn giản hóa. Production phải giảm thời gian tồn tại, kiểm soát dump/trace/log và quản lý plaintext theo độ nhạy.
8. **Không dùng lại DEK vô hạn.** Mã sinh DEK cho từng envelope; nếu tái sử dụng DEK qua nhiều record, bắt buộc thiết kế nonce GCM **duy nhất với cùng khóa** và giới hạn số lần mã hóa.

## 7. Chữ ký số và mã hóa lai: khi nào cần kết hợp?

Hybrid encryption cung cấp bảo vệ **bí mật** dữ liệu cho người nhận được phép. Nhưng nó **không tự chứng minh người gửi là ai**. Ví dụ đối tác B có public key được công bố để mọi khách hàng gửi dữ liệu mật: cả A và kẻ tấn công đều có thể dùng public key này tạo envelope hợp lệ về mật mã.

Nếu B chỉ chấp nhận hồ sơ do A phát hành, cần **xác thực A** qua mTLS, chữ ký số trên envelope hoặc cơ chế tương đương theo thiết kế hệ thống.

~~~mermaid
sequenceDiagram
    participant A as Bên gửi A
    participant B as Bên nhận B
    A->>A: Xác thực public key mã hóa của B
    A->>A: Tạo envelope mã hóa lai
    A->>A: Ký phần dữ liệu/gói được quy định bằng private key ký A
    A->>B: Envelope + signature + signing key reference
    B->>B: Kiểm tra public key ký của A từ nguồn tin cậy
    B->>B: Verify signature và kiểm tra recipient/tenant/policy
    B->>B: Unwrap DEK, verify AEAD tag, decrypt
    B-->>A: Xử lý hoặc từ chối theo kết quả xác minh
~~~

Chữ ký phải bao phủ **những byte được xác định rõ**: thường là phiên bản định dạng, thuật toán, recipient key reference, encrypted DEK, nonce, ciphertext/tag và metadata an ninh. Cần thiết kế canonicalization ổn định và tránh chữ ký chỉ bảo vệ một trường trong khi các trường khác có thể bị tráo.

Thứ tự ký/mã hóa (**sign-then-encrypt**, **encrypt-then-sign** hoặc thành phần mã hóa được xác thực của giao thức) có những đặc tính riêng về khả năng kiểm chứng, riêng tư người ký và metadata. Nên chọn một **giao thức chuẩn** và tuân thủ quy tắc của giao thức đó; không tự kết luận một thứ tự luôn đúng cho mọi tình huống.

## 8. Bảo vệ khóa bằng KMS/HSM trong kiến trúc thực tế

**KMS (Key Management Service)** quản lý danh tính khóa, quyền thao tác, trạng thái, phiên bản, chính sách và audit theo khả năng của dịch vụ. **HSM (Hardware Security Module)** bảo vệ material trong ranh giới phần cứng chuyên dụng và thực hiện thao tác mật mã theo thiết kế thiết bị. Một KMS có thể dùng HSM ở tầng dưới.

Trong hybrid encryption, có hai cách thường thấy:

| Kiến trúc | Cách sử dụng key material | Ưu điểm và lưu ý |
|---|---|---|
| **Public key ngoài ứng dụng; private key trong KMS/HSM** | Bên gửi mã hóa DEK bằng public key; bên nhận gọi Decrypt/Unwrap bằng private key theo key reference | Bên nhận không cần xuất raw private key. Phải kiểm soát quyền Decrypt và công bố đúng public key/version |
| **DEK/KEK qua envelope encryption của KMS** | Ứng dụng nhận hoặc sử dụng DEK theo API; KEK đối xứng nằm trong KMS/HSM | Phù hợp lưu dữ liệu nội bộ; không bắt buộc là hybrid bất đối xứng, nhưng có cùng nhu cầu bảo vệ DEK và audit |

Một private key **non-exportable** không cho ứng dụng lấy byte khóa, nhưng không ngăn tài khoản bị chiếm **gọi Decrypt** để khôi phục DEK nếu tài khoản đó có quyền. Vì thế phải kiểm soát cả **khả năng đọc key material** và **khả năng sử dụng khóa**.

### 8.1. Phân tách quyền thao tác

| Chủ thể | Quyền nên có | Quyền thường không cần |
|---|---|---|
| **Bên gửi A** | Đọc public key B từ nguồn tin cậy, encrypt payload và gửi envelope | Private key giải mã của B; quản trị hoặc hủy khóa B |
| **Dịch vụ giải mã B** | Decrypt/Unwrap với đúng key ID, version, tenant, purpose | Export raw private key; quản trị policy; đọc khóa tenant khác |
| **Key administrator** | Tạo, rotate, cấu hình policy và lên lịch hủy | Quyền giải mã mọi dữ liệu nghiệp vụ nếu không được phê duyệt |
| **Auditor** | Xem log hành động, key reference và trạng thái | DEK, private key, plaintext hoặc bí mật trong context |
| **Dịch vụ xác minh chữ ký** | Truy cập public key ký của A qua trust store | Private key ký của A |

Nhật ký nên ghi **principal, action, keyId/version, tenant, request/correlation ID, thời điểm và kết quả**. Không ghi **DEK bản rõ, private key, passphrase, plaintext, token bí mật**. Nếu có encryption context chứa dữ liệu nhạy cảm, không tự động đưa toàn bộ context vào log.

## 9. Vòng đời khóa và tác động đến dữ liệu lịch sử

~~~mermaid
flowchart TD
    A["Tạo cặp khóa người nhận và DEK theo chính sách"] --> B["Đăng ký key ID, version, purpose và owner"]
    B --> C["Bảo vệ private key; công bố public key đáng tin"]
    C --> D["Encrypt/Unwrap theo quyền và lưu envelope"]
    D --> E["Audit, giới hạn sử dụng, đánh giá rotation"]
    E --> F["Tạo cặp khóa/KEK mới"]
    F --> G["Dữ liệu mới tham chiếu version mới"]
    G --> H["Rewrap/re-encrypt hoặc giữ decrypt-only cho dữ liệu cũ"]
    H --> I["Kiểm tra backup, khôi phục và phụ thuộc"]
    I --> J["Disable, thu hồi hoặc hủy khóa cũ theo quy trình"]
~~~

| Sự kiện | Thay đổi gì? | Ảnh hưởng đến encrypted envelope |
|---|---|---|
| **Tạo/cấp phát** | Cặp khóa người nhận và DEK mới | Gắn key reference, version, owner, purpose và policy |
| **Sử dụng** | Sinh DEK/nonce; bọc DEK và mã hóa payload | Lưu encrypted DEK, nonce, ciphertext/tag, AAD và metadata cần phục hồi |
| **Rotate recipient key** | Cặp public/private của bên nhận thay đổi | Gói mới mã hóa cho public key mới; gói cũ vẫn cần private key cũ hoặc phải chuyển đổi |
| **Rotate DEK** | DEK dùng mã hóa payload thay đổi | Nếu muốn đổi DEK của dữ liệu cũ thì phải giải mã/mã hóa lại dữ liệu |
| **Rotate KEK đối xứng** | Thay wrapping KEK trong envelope encryption | Có thể rewrap DEK mà không đổi bản mã AES-GCM, tùy API |
| **Disable/revoke** | Thu hẹp quyền sử dụng hoặc trạng thái tin cậy | Có thể chặn giải mã gói cũ; cần kế hoạch chuyển tiếp |
| **Destroy** | Private key/KEK không thể tiếp tục dùng | Gói lịch sử phụ thuộc khóa có thể mất khả năng phục hồi |

### 9.1. Rewrap khác re-encrypt

**Rewrap** là thay đổi **lớp bảo vệ DEK**, ví dụ unwrap DEK bằng private key phiên bản cũ rồi mã hóa lại **cùng DEK** bằng public key mới. Nếu DEK không đổi, AES-GCM ciphertext của payload **có thể giữ nguyên**, nhưng toàn bộ metadata/AAD liên quan đến key reference cần được xử lý nhất quán.

**Re-encrypt** là dùng **DEK mới** để mã hóa lại plaintext dữ liệu. Việc này đòi hỏi truy cập plaintext hợp lệ và phải tạo nonce/tag mới theo key và AAD mới. Nếu DEK từng bị lộ hoặc nonce GCM từng bị trùng, chỉ rewrap DEK cũ **không giải quyết** rủi ro trên dữ liệu.

**Điểm tinh tế:** nếu AAD của AES-GCM đã ràng buộc **recipientKeyVersion=v1**, chỉ sửa metadata sang **v2** trong quá trình rewrap sẽ làm xác minh tag thất bại. Hệ thống phải thiết kế rõ: hoặc tách metadata wrapping ra khỏi AAD payload khi phù hợp và xác thực riêng, hoặc thực hiện tái mã hóa/xác thực lại payload theo context mới một cách có kiểm soát. Không “đổi nhãn” rồi bỏ qua lỗi xác thực.

### 9.2. Forward secrecy có tự xuất hiện không?

**Không.** Nếu bên gửi lưu nhiều envelope RSA-OAEP được mã hóa cho public key dài hạn của B, kẻ tấn công thu thập các envelope cũ rồi về sau lấy được private key của B **có thể giải mã các DEK cũ** và đọc dữ liệu. AES-GCM không tự sửa điểm yếu này.

Forward secrecy cần một **giao thức** có các bí mật phiên tạm thời được tạo và xóa phù hợp, cùng xác thực và xử lý trạng thái đúng. Việc chuyển sang ECDH/HPKE base mode với một recipient private key tĩnh không tự bảo đảm rằng lộ recipient key về sau sẽ không giải mã được các bản ghi đã thu thập.

### 9.3. Quản lý public key cũ và chứng thư

Khi B rotate private key, bên gửi phải nhận **public key mới từ nguồn tin cậy** và dừng encrypt mới cho phiên bản cũ theo chính sách. B có thể cần giữ quyền **Decrypt-only** bằng private key cũ đủ lâu để đọc dữ liệu cũ hoặc thực hiện rewrap. Nếu private key bị lộ, cần đánh giá gói lịch sử đã bị thu thập và thực hiện ứng phó ngay.

Nếu public key được phát hành qua **chứng thư X.509**, việc **thu hồi chứng thư** (CRL/OCSP/chính sách tin cậy) khác với **disable private key trong KMS**. Một thao tác ngừng công bố public key cũng không xóa các bản đã được cache hoặc sao chép. Các cơ chế này cần được điều phối theo mục tiêu ứng phó.

## 10. Các lỗi và mối đe dọa thường gặp

| Lỗi thiết kế | Rủi ro | Kiểm soát |
|---|---|---|
| Dùng RSA-OAEP để mã hóa file lớn trực tiếp | Vượt giới hạn plaintext và kém hiệu năng | Mã hóa payload bằng AEAD, dùng RSA/KEM bảo vệ khóa |
| Không xác thực public key bên nhận | Mã hóa DEK cho khóa của kẻ tấn công | PKI, trust store/pinning, xác thực recipient và key usage |
| Đánh đồng mã hóa cho B với chứng minh A là người gửi | B nhận envelope của bên giả mạo | Chữ ký số, mTLS hoặc giao thức xác thực nguồn |
| Tự xây KEM/KDF/AEAD thiếu kiểm tra | Trộn sai ngữ cảnh, dùng shared secret không phù hợp, sai định dạng | Dùng HPKE/giao thức chuẩn và thư viện đáng tin nếu khả thi |
| Trùng nonce AES-GCM với cùng DEK | Có thể phá tính bí mật và tính xác thực | Nonce duy nhất theo khóa; giới hạn số lần dùng; rotate DEK |
| Bỏ qua tag hoặc phát plaintext trước verify | Dữ liệu bị sửa xâm nhập nghiệp vụ | Chỉ sử dụng plaintext sau khi xác minh AEAD thành công |
| AAD thiếu tenant/record, hoặc lấy từ input chưa xác thực | Tráo bản mã hoặc vượt quyền theo ngữ cảnh | Ràng buộc metadata cần thiết, lấy tenant từ danh tính đáng tin và kiểm tra IAM |
| Cho quyền Decrypt/Unwrap quá rộng | Kẻ chiếm workload giải mã dù không xuất được private key | Least privilege, key policy theo workload/tenant/purpose, audit |
| Lưu plaintext DEK/private key trong log, Git, CI hoặc backup mở | Khóa bị lộ, mất bảo mật dữ liệu | KMS/HSM, tránh export, bảo vệ secret và loại bỏ giá trị nhạy cảm khỏi log |
| Chỉ sửa key ID khi rotation mà không rewrap/re-encrypt | Không giải mã được gói cũ hoặc sai AAD | Kế hoạch chuyển đổi và validation dữ liệu theo version |
| Hủy private key cũ quá sớm | Mất DEK của bản mã lịch sử | Kiểm tra restore/recovery, chờ hết phụ thuộc và phê duyệt hủy |
| Phát lại envelope hợp lệ | Xử lý lặp nghiệp vụ dù tag vẫn đúng | Message ID, sequence, expiry và idempotency |
| Tin rằng dùng khóa dài thì “kháng lượng tử” | Đánh giá sai nguy cơ lưu trữ và giải mã sau này | Theo dõi chuẩn hậu lượng tử, lộ trình chuyển giao phù hợp và crypto agility |

## 11. Tình huống kiến trúc: gửi tài liệu bảo mật qua hai tổ chức

Giả sử **Service A** ở tổ chức A gửi hồ sơ khách hàng cho **Service B** ở tổ chức B. Hai bên cần đảm bảo dữ liệu chỉ B đọc được, B xác định đúng nguồn gửi và các thao tác đều được truy vết.

**Quy trình đề xuất:**

1. **Cấp phát danh tính khóa:** B tạo cặp khóa mã hóa được quản lý trong KMS/HSM; công bố public key và key ID/version qua chứng thư/registry đáng tin cậy. A tạo hoặc dùng private key ký riêng với quyền Sign.
2. **Xác thực bên nhận:** A xác minh public key/certificate của B, algorithm và key usage. A không nhận public key thay thế chỉ vì một URL do request gửi đến.
3. **Mã hóa:** A tạo DEK ngẫu nhiên, mã hóa tệp bằng AES-GCM; nonce không trùng trong phạm vi DEK, AAD ràng buộc tenant, document ID, format và các trường an ninh.
4. **Bảo vệ DEK:** A wrap DEK bằng cơ chế public-key encryption hoặc KEM đã thống nhất với B, tạo envelope có key reference và thông số cần giải mã.
5. **Xác thực nguồn:** A ký các trường envelope được quy định; B kiểm tra chữ ký theo public key ký của A lấy từ nguồn tin cậy. Nếu dùng mTLS/giao thức khác, quy trình xác thực phải bảo vệ đúng ngữ nghĩa yêu cầu.
6. **Giải mã có quyền:** B kiểm tra người nhận, tenant và chính sách; gọi KMS/HSM Decrypt/Unwrap đúng private key/version; xác minh tag AES-GCM rồi mới trả plaintext vào vùng xử lý tin cậy.
7. **Kiểm toán và phòng replay:** hai bên ghi correlation ID, message ID, key reference, principal, action và kết quả. B từ chối request trùng theo quy tắc nghiệp vụ.
8. **Rotation/recovery:** B công bố public key mới trước khi chuyển traffic, xử lý envelope cũ bằng private key cũ còn được phép hoặc rewrap có kiểm soát; chỉ hủy sau khi xác nhận khả năng khôi phục.

Trong quy trình này, **mTLS bảo vệ kết nối**, **chữ ký số xác thực người gửi**, **hybrid encryption giữ bí mật payload**, **KMS/HSM bảo vệ việc sử dụng khóa**, còn **audit và chính sách vòng đời** hỗ trợ vận hành an toàn. Các lớp này giải quyết những nhiệm vụ khác nhau nhưng cần phối hợp chặt chẽ.

## 12. Checklist khi thiết kế hybrid encryption

1. **Mục tiêu bảo mật:** cần bí mật, toàn vẹn, xác thực người gửi, chống replay và/hoặc forward secrecy ở mức nào?
2. **Cơ chế đã kiểm chứng:** dùng RSA-OAEP + AEAD hoặc KEM/KDF/AEAD theo giao thức chuẩn; có định danh đầy đủ các thuật toán và tham số?
3. **Tin cậy public key:** bên gửi xác thực public key của người nhận và kiểm tra owner, key usage, trạng thái, thời hạn?
4. **Bảo vệ DEK:** DEK do CSPRNG/KMS tạo; không ghi vào log/config; có chính sách key lifetime, scope và rotation?
5. **Nonce và AEAD:** nonce không trùng theo từng DEK, tag được xác minh, AAD chuẩn hóa và tái tạo đúng?
6. **Metadata:** envelope chứa key ID/version, format, algorithm, nonce, ciphertext/tag và encrypted DEK đủ để giải mã lịch sử?
7. **Sender authentication:** nếu cần, đã có chữ ký hoặc cơ chế giao thức xác thực nguồn bao phủ đúng dữ liệu?
8. **Quyền tối thiểu:** ai có thể Sign, Encrypt, Decrypt/Unwrap, Rotate và Destroy? Có phân tách vai trò, tenant, môi trường?
9. **Khôi phục khi rotation:** biết khi nào phải rewrap, khi nào phải re-encrypt, cách xử lý AAD và backup trước khi hủy khóa?
10. **Kiểm toán và xử lý sự cố:** có log actor/action/result mà không làm lộ khóa? Có kế hoạch ứng phó khi private key hoặc DEK bị lộ?

### Câu hỏi tự đánh giá

**Câu 1.** Vì sao không dùng RSA-OAEP để mã hóa trực tiếp file 200 MB?

**Trả lời:** RSA-OAEP chỉ xử lý một lượng plaintext nhỏ theo độ dài khóa và tham số. Thiết kế phù hợp thường mã hóa file bằng AES-GCM, rồi dùng RSA-OAEP bảo vệ DEK nhỏ.

**Câu 2.** Một envelope đã mã hóa cho public key của B có chứng minh nó đến từ A không?

**Trả lời:** **Không.** Bất kỳ ai có public key B đều có thể tạo envelope cho B; cần chữ ký hoặc giao thức xác thực nguồn nếu yêu cầu chứng minh A.

**Câu 3.** B giữ private key RSA trong HSM không thể export. Quyền Decrypt có thể bị lạm dụng không?

**Trả lời:** **Có.** Người có quyền Decrypt/Unwrap có thể khiến HSM giải mã encrypted DEK mà không cần xuất raw private key; cần IAM, phân vùng quyền, audit và giám sát.

**Câu 4.** Khi chuyển private key nhận từ v1 sang v2, có thể chỉ đổi keyVersion trong JSON envelope cũ không?

**Trả lời:** **Không.** Encrypted DEK cũ vẫn gắn với private key v1. Phải giữ cách unwrap v1 hoặc thực hiện rewrap có kiểm soát; nếu AAD gắn với version thì cần xử lý ràng buộc AAD tương ứng.

**Câu 5.** Đổi KEK bảo vệ DEK có đồng nghĩa dữ liệu AES-GCM đã được mã hóa bằng DEK mới?

**Trả lời:** **Không.** Rewrap chỉ thay khóa/cách bảo vệ DEK. Muốn đổi DEK phải thực hiện re-encrypt dữ liệu theo quy trình an toàn.

**Câu 6.** Hybrid encryption dựa trên public key dài hạn có mặc nhiên forward secrecy?

**Trả lời:** **Không.** Nếu private key nhận dài hạn bị lộ về sau, các encrypted DEK lịch sử thu thập được có thể bị giải mã. Forward secrecy đòi hỏi giao thức với bí mật tạm thời và điều kiện xử lý khóa phù hợp.

**Điểm cốt lõi:** Hybrid encryption kết hợp **cách thiết lập/bảo vệ khóa bằng cơ chế bất đối xứng** với **mã hóa dữ liệu hiệu quả bằng khóa đối xứng và AEAD**. Một thiết kế an toàn cần xác thực public key, chọn đúng thuật toán/giao thức, bảo vệ DEK và private key, ràng buộc metadata, giới hạn quyền Decrypt/Unwrap, kiểm toán và lập kế hoạch rotation/recovery cho cả dữ liệu mới lẫn dữ liệu lịch sử.
