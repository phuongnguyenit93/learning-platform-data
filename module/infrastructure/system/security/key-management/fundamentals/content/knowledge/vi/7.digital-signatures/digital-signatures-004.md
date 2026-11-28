# Signature generation: Quy trình tạo chữ ký số an toàn

Một dịch vụ phát hành hóa đơn điện tử cần để bên nhận kiểm tra rằng nội dung hóa đơn không bị sửa và chữ ký được tạo bởi khóa ký được cấp cho dịch vụ. **Signature generation (tạo chữ ký số)** là thao tác sử dụng **private key** trong một thuật toán chữ ký bất đối xứng để tạo **signature** cho một thông điệp hoặc biểu diễn thông điệp được xác định chính xác. Người nhận dùng **public key tương ứng** để kiểm tra chữ ký, không cần biết private key.

Trong chương **Chữ ký số** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, tạo chữ ký chỉ an toàn khi được đặt vào một hệ thống quản lý khóa hoàn chỉnh: **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → vô hiệu hóa/thu hồi → hủy**. Dịch vụ phải kiểm soát cả **ai có thể truy cập vật liệu khóa** và **ai có thể yêu cầu khóa thực hiện phép ký**, dù private key được giữ trong KMS/HSM không xuất được. Bài học cũng liên hệ chữ ký số với hàm băm, mật mã đối xứng/bất đối xứng, envelope encryption, IAM và audit.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác vai trò của **private key**, **public key**, thông điệp, signature và thuật toán ký.
2. Phân biệt **signature generation** với hash, HMAC, mã hóa công khai và AES-GCM.
3. Mô tả chuỗi thao tác **xác thực yêu cầu → chuẩn hóa dữ liệu → kiểm tra policy → ký → ghi nhận metadata/audit → xác minh**.
4. Hiểu sự khác biệt giữa **Ed25519**, **ECDSA** và **RSA-PSS**, đặc biệt quy tắc hash, nonce và các tham số bắt buộc.
5. Viết ví dụ Java 17 tạo và xác minh chữ ký có định dạng byte ổn định.
6. Thiết kế dịch vụ ký trong KMS/HSM, quản lý version, rotation, quyền Sign và ứng phó lộ khóa.

## 2. Chữ ký số được tạo như thế nào?

Một thuật toán chữ ký thường cung cấp ba thao tác khái niệm:

~~~text
  (privateKey, publicKey) = KeyGen(securityParameters)
  signature = Sign(privateKey, message, algorithmParameters)
  valid = Verify(publicKey, message, signature, algorithmParameters)
~~~

**Sign** và **Verify** không phải cặp **Encrypt** và **Decrypt**. Chữ ký số không che giấu message; các bên có message vẫn đọc được nó. Một hệ thống muốn vừa giữ bí mật vừa kiểm chứng nguồn dữ liệu có thể kết hợp **AES-GCM/envelope encryption** với **chữ ký số**, nhưng phải xác định rõ trường nào được ký và thứ tự xử lý theo giao thức.

### 2.1. Các thành phần của thao tác ký

| Thành phần | Bản chất | Cần bảo vệ thế nào? |
|---|---|---|
| **Private signing key** | Key material bí mật tạo chữ ký | Giữ kín, hạn chế export; kiểm soát quyền Sign và audit |
| **Public verification key** | Key material công khai để kiểm tra | Xác thực nguồn, ràng buộc đúng chủ thể, algorithm/purpose |
| **Message bytes** | Những byte thực sự được ký | Quy định encoding/canonicalization rõ; kiểm tra nghiệp vụ trước khi ký |
| **Signature** | Giá trị đầu ra của thuật toán ký | Có thể công khai; phải gắn với message và thông tin xác minh cần thiết |
| **Algorithm/parameters** | Ví dụ Ed25519, ECDSA-P256-SHA256, RSASSA-PSS SHA-256 | Allowlist; cấu hình đầy đủ và nhất quán giữa hai phía |
| **Key ID/version** | Metadata để chọn đúng public/private key | Chỉ chọn khóa trong registry đáng tin, không để request tùy ý điều khiển |
| **Signer/tenant/purpose/time** | Ngữ cảnh quản trị và chứng cứ vận hành | Xác thực, ràng buộc vào dữ liệu cần ký khi có ý nghĩa an ninh, kiểm toán |

**Một chữ ký hợp lệ** chứng minh rằng chữ ký khớp với message và **public key được dùng để verify** theo sơ đồ mật mã. Nó **không tự chứng minh tên người ký** nếu chưa xác lập nguồn tin cậy của public key; cũng không tự chứng minh người sở hữu hợp pháp đã chủ động phê duyệt nếu một tài khoản có quyền ký bị lạm dụng.

### 2.2. Luồng xử lý ký từ ứng dụng tới bên xác minh

~~~mermaid
sequenceDiagram
    participant C as Client/nghiệp vụ
    participant S as Signing Service
    participant K as KMS/HSM
    participant R as Bên nhận/xác minh
    C->>S: Yêu cầu ký tài liệu + ngữ cảnh
    S->>S: Authenticate, authorize, kiểm tra nội dung/purpose
    S->>S: Tạo bytes thông điệp ổn định
    S->>K: Sign(keyRef, message hoặc digest theo contract)
    Note over K: Dùng private key, không xuất material
    K-->>S: Signature
    S->>S: Gắn algorithm, keyId/version, audit
    S-->>C: Tài liệu + signature + metadata
    C->>R: Gói tài liệu đã ký
    R->>R: Lấy public key từ nguồn tin cậy
    R->>R: Verify(public key, bytes, signature)
    R-->>C: Hợp lệ hoặc từ chối
~~~

**KMS/HSM không thay thế kiểm tra nghiệp vụ.** Nếu Signing Service được phép ký mọi chuỗi byte do client gửi, một kẻ tấn công có thể tạo chữ ký cho hóa đơn giả mà không hề thấy private key. Chính sách nên giới hạn **đối tượng ký, định dạng, tenant, owner, ngữ cảnh, hạn mức và quyền của principal**.

## 3. Chữ ký số khác hash, HMAC và encryption

| Cơ chế | Có khóa bí mật? | Đầu ra | Mục tiêu |
|---|---|---|---|
| **SHA-256** | Không | Digest | Tạo dấu vân tay; tự nó không xác thực người tạo |
| **HMAC-SHA-256** | Có, khóa đối xứng dùng chung | MAC tag | Xác thực tính toàn vẹn dựa trên bên có khóa chung |
| **Ed25519/ECDSA/RSA-PSS** | Private key ký, public key xác minh | Digital signature | Bên giữ public key tin cậy có thể kiểm tra chữ ký độc lập |
| **RSA-OAEP** | Public key mã hóa, private key giải mã | Ciphertext | Giữ bí mật dữ liệu/khóa nhỏ đối với bên nhận |
| **AES-GCM** | Khóa đối xứng bí mật | Ciphertext + tag | Giữ bí mật và xác thực bản mã/AAD bằng khóa chung |

**Hash(message) không phải signature** vì bất kỳ ai cũng tính được cùng digest. **HMAC** không phải chữ ký số bất đối xứng: bên gửi và bên nhận đều biết cùng secret, do đó không thể độc lập chứng minh bên nào đã tạo tag nếu chỉ dựa trên HMAC. **Sign(privateKey, message)** không đồng nghĩa “encrypt bằng private key”; cách mô tả sai này không áp dụng cho ECDSA, Ed25519 và dễ dẫn đến dùng nhầm RSA raw.

### 3.1. Khi nào phải mã hóa cùng với ký?

Giả sử hóa đơn chứa thông tin cá nhân, hai yêu cầu cần giải quyết là:

- **Tính toàn vẹn/xác thực nguồn:** dịch vụ phát hành dùng private signing key ký theo quy trình. Bên nhận xác minh public key và danh tính khóa.
- **Tính bí mật:** dữ liệu được mã hóa bằng **AES-GCM với DEK**, có thể bảo vệ DEK bằng KEK trong KMS hoặc cơ chế hybrid encryption dùng public key của bên nhận.

Chữ ký không mã hóa nội dung; AES-GCM tag không tự cung cấp chứng cứ chữ ký công khai. Khi kết hợp, phải xác định đúng dữ liệu nào được ký (plaintext, ciphertext hay một cấu trúc envelope) và tuân thủ giao thức được chọn, tránh tự thiết kế cách ghép primitive không có đánh giá an ninh.

## 4. Quy trình signature generation gồm những bước nào?

### Bước 1. Xác thực yêu cầu và xác định thẩm quyền ký

Xác thực workload hoặc người dùng qua identity được tin cậy. Kiểm tra role/policy: principal đó có được ký **loại tài liệu, tài khoản, tenant, môi trường và phạm vi** tương ứng hay không? Không chọn private key chỉ vì request gửi một **keyId** trông hợp lệ.

Một ví dụ chính sách: **billing-service** chỉ được Sign hóa đơn thuộc tenant đã xác thực, ở trạng thái **APPROVED**, theo **invoice-signing-key** hiện đang **ENABLED**. Dịch vụ không được ký arbitrary byte stream cho client không tin cậy nếu không có mục đích nghiệp vụ rõ ràng.

### Bước 2. Chọn thuật toán, key reference và phiên bản phù hợp

Lấy cấu hình từ registry/policy đáng tin cậy: **purpose=SIGN_VERIFY**, algorithm, keyId, keyVersion, state, owner và hạn mức. Chỉ cho phép thuật toán thuộc allowlist phù hợp với key type.

Không để client tự ý chọn giữa **Ed25519**, **RSA-PSS**, **RSA v1.5** hoặc chế độ không ký. Các tham số thuật toán ảnh hưởng trực tiếp tới dữ liệu ký và verify, nên phải được kiểm tra/ghi nhận đầy đủ.

### Bước 3. Xây dựng chính xác thông điệp được ký

Định nghĩa **bytesToSign** thay vì chỉ mô tả “ký object”. Các hệ thống thường mắc lỗi ở bước này khi hai bên serialize cùng một object JSON thành byte khác nhau.

Một payload cần ràng buộc đủ các trường có ý nghĩa:

- **Domain/purpose:** ví dụ **INVOICE_SIGNATURE_V1** để phân biệt chữ ký hóa đơn với chữ ký lệnh chuyển tiền hoặc cấu hình hệ thống.
- **Tenant/issuer/subject:** được lấy từ trạng thái xác thực, không chỉ tin request tự khai.
- **Document ID, amount, currency, hash hoặc bytes tài liệu:** những trường mà một thay đổi sẽ ảnh hưởng quyết định nghiệp vụ.
- **Schema/format version:** giúp bên verify hiểu đúng encoding và nội dung.
- **Timestamp, request ID, expiry hoặc nonce ứng dụng** khi giao thức yêu cầu chống replay/kiểm soát thời gian.

Nếu ký toàn bộ file lớn, có thể dùng API streaming của provider hoặc quy trình xử lý digest do **sơ đồ ký và contract API quy định**. Không tự hash trước mọi thuật toán rồi lại đưa digest vào API **Sign(message)** vì có thể gây băm hai lần hoặc ký sai phạm vi.

### Bước 4. Thực hiện phép ký trong ranh giới được cấp quyền

Ứng dụng dùng private key local được bảo vệ hoặc gọi **KMS/HSM Sign** theo key reference. Chỉ trả signature ra ngoài theo policy; tránh xuất private key, seed, bộ tham số RSA bí mật hay secret ở dạng thô.

### Bước 5. Đóng gói signature và metadata

Một gói có thể chứa **message hoặc hash tham chiếu**, **signature bytes**, **algorithm**, **keyId/keyVersion** và các trường chứng thư/thời gian theo giao thức. Metadata hỗ trợ bên nhận chọn cách verify nhưng **không tự tạo ra niềm tin**. Không chấp nhận khóa xác minh từ một địa chỉ URL tùy ý do đối thủ chèn vào gói.

### Bước 6. Ghi audit và bảo đảm bên nhận kiểm tra đúng

Ghi principal, operation, key reference/version, loại tài liệu, request ID, quyết định policy, kết quả, thời điểm và thông tin correlation an toàn. Không ghi private key, token nhạy cảm, nội dung bí mật chưa mã hóa hoặc toàn bộ tài liệu nếu chính sách cấm.

Khi Verify, bên nhận phải dùng **đúng bytes đã ký** và **public key từ kênh tin cậy**, kiểm tra thuật toán/purpose, chính sách tin cậy và ngữ cảnh nghiệp vụ độc lập.

## 5. Ba thuật toán phổ biến khi tạo chữ ký

### 5.1. Ed25519

**Ed25519** là một sơ đồ chữ ký thuộc họ EdDSA dùng đường cong Edwards25519. API ký thông thường nhận thông điệp và thực hiện những bước hash nội bộ theo thuật toán; không nên tự biến mọi message thành digest SHA-256 chỉ vì những hệ thống ký khác có phương thức **signDigest**.

Ưu điểm thường thấy: chữ ký và public key gọn, thao tác ký/xác minh hiệu quả, cách dùng API đơn giản, không phải tự sinh một ECDSA nonce cho mỗi chữ ký. Tuy nhiên, **Ed25519 không phải khóa giải mã** và không phải mọi HSM/KMS hay chuẩn nghiệp vụ đều hỗ trợ nó.

**Ed25519 dạng chuẩn** là sơ đồ ký xác định theo khóa và thông điệp; cần phân biệt với các biến thể có context/prehash khi giao thức yêu cầu. Việc không yêu cầu ứng dụng tự sinh nonce ký không có nghĩa có thể dùng nguồn ngẫu nhiên yếu khi **tạo cặp khóa**.

### 5.2. ECDSA

**ECDSA** tạo chữ ký bằng private key trên đường cong elliptic và một giá trị bí mật theo từng lần ký thường gọi là **nonce k**. Nếu **k bị lặp hoặc có thể dự đoán**, private key có thể bị suy ra từ các chữ ký. Vì vậy tuyệt đối không tự xây bộ sinh nonce hoặc mã ECDSA theo cảm tính; dùng provider được kiểm chứng và cơ chế nonce phù hợp (ví dụ ECDSA có nonce xác định theo chuẩn khi được hỗ trợ).

Định dạng chữ ký ECDSA có thể là **ASN.1 DER** hoặc dạng ghép cố định **r||s** tùy giao thức. Byte representation cần được quy định rõ. Không đồng nhất chữ ký ECDSA-P256-SHA256 với Ed25519 chỉ vì cả hai dùng khóa elliptic.

### 5.3. RSA-PSS

**RSA-PSS** là sơ đồ chữ ký RSA hiện đại, khác **RSA-OAEP** dùng để mã hóa. Các bên phải thống nhất **hash**, **MGF/MGF1 digest**, **salt length**, **trailer field** và các tham số tương ứng.

Ví dụ cấu hình **RSASSA-PSS/SHA-256/MGF1-SHA256/saltLength=32** dùng SHA-256 và salt 32 byte theo policy. Một signature RSA-PSS có thể thay đổi giữa các lần ký do salt ngẫu nhiên; việc nhiều chữ ký khác nhau trên cùng thông điệp **không tự báo hiệu lỗi**.

| Thuật toán | Thao tác ký | Lưu ý |
|---|---|---|
| **Ed25519** | Private key Ed25519 tạo chữ ký EdDSA | Không dùng để decrypt; tuân theo biến thể và encoding được quy định |
| **ECDSA P-256 + SHA-256** | Private EC key ký theo ECDSA | Chất lượng nonce k tối quan trọng; chú ý DER/raw encoding |
| **RSA-PSS + SHA-256** | Private RSA key tạo signature PSS | Cấu hình digest, MGF1, salt length và khóa hợp lệ |
| **RSA-OAEP** | **Không dùng để ký** | Đây là sơ đồ public-key encryption, thường bảo vệ DEK |

### 5.4. Hash trực tiếp và prehash: không trộn lẫn API

~~~text
Signature API kiểu message:
    Sign(privateKey, fullMessage)
    -> thuật toán/provider tự thực hiện quá trình hash cần thiết

KMS API kiểu digest:
    digest = Hash(message) theo thuật toán ký được KMS chỉ định
    SignDigest(keyRef, digest, digestAlgorithm)
    -> KMS không được diễn giải digest như raw message nếu contract không nói vậy
~~~

Hai luồng là những **hợp đồng API khác nhau**. Một số dịch vụ hỗ trợ ký message nguyên bản, một số chỉ nhận digest, một số có cả hai tùy thuật toán. Băm hai lần do nhầm lẫn có thể vẫn tạo ra chữ ký “Verify OK” trong một hệ thống đóng nhưng không tương thích giao thức và không bảo vệ chính xác tài liệu mong muốn.

## 6. Chuẩn hóa dữ liệu ký và chống signature confusion

### 6.1. Cùng ý nghĩa nghiệp vụ chưa chắc cùng bytes

Hai biểu diễn JSON sau có thể cùng ý nghĩa ứng dụng nhưng là **hai chuỗi byte khác nhau**:

~~~json
{"invoiceId":"inv-123","amountMinor":250000}
~~~

~~~json
{ "amountMinor": 250000, "invoiceId": "inv-123" }
~~~

Nếu ứng dụng ký bytes JSON thứ nhất và bên nhận serialize lại thành thứ hai để verify, chữ ký có thể không khớp. Cần chọn một trong các cách:

1. Ký chính xác **raw bytes** được gửi và bên nhận verify chính raw bytes đó; hoặc
2. Dùng **canonicalization đã được đặc tả** và áp dụng giống nhau ở cả hai phía, gồm field order, number formatting, Unicode, encoding, escaping và cách xử lý null.

Không lấy **String.toString()** của một object, bản ghi map không có thứ tự bảo đảm hay một phép nối chuỗi thiếu quy tắc làm protocol ký số.

### 6.2. Domain separation

Giả sử cùng một private key được dùng để ký thông điệp khác loại, người nhận có thể hiểu nhầm chữ ký của một thông điệp ở ngữ cảnh A thành ủy quyền trong ngữ cảnh B nếu cấu trúc bytes có thể trùng hoặc bị diễn giải khác. Giải pháp là **tách khóa theo purpose** và/hoặc ký một cấu trúc có **domain/version** rõ ràng.

~~~text
version           = "invoice-signature-v1"
issuer            = "billing-service"
tenant            = "tenant-42"
invoiceId         = "inv-123"
amountMinor       = 250000
currency          = "VND"
documentDigest    = SHA256(canonicalInvoiceDocument)

bytesToSign = EncodeCanonical(
    version, issuer, tenant, invoiceId,
    amountMinor, currency, documentDigest
)
~~~

**DocumentDigest** chỉ là thành phần đại diện dữ liệu bên trong một cấu trúc được ký; SHA-256 riêng lẻ không phải chữ ký. Nếu dùng tham chiếu digest thay cho nội dung, bên nhận phải có tài liệu thực, tính lại digest và so khớp theo chính sách trước khi chấp nhận.

Việc đặt **algorithm** và **keyId** vào metadata ngoài message cần được xem xét cùng threat model: có thể đưa các giá trị có ý nghĩa vào cấu trúc được ký (hoặc cơ chế bảo vệ header của giao thức) để tránh tráo/chọn thuật toán hoặc khóa. Với chuẩn như **JWS**, hãy dùng đúng định dạng ký trên protected header và payload thay vì tự ghép một JSON khác.

### 6.3. Chống replay là nhiệm vụ riêng

Một chữ ký hợp lệ trên lệnh **transfer=1000** hôm qua vẫn có thể được Verify OK hôm nay, vì thông điệp và signature không đổi. Muốn ngăn thực thi lại lệnh, cần **requestId/nonce ứng dụng, timestamp, expiry, sequence, idempotency store** và kiểm tra trạng thái nghiệp vụ. Các trường phải được đưa vào phạm vi được ký theo giao thức.

Đừng gọi thuật toán chữ ký là “chống replay” mặc định. Chữ ký chứng minh tính toàn vẹn và khả năng sở hữu khóa, **không tự phân biệt dữ liệu mới hay cũ**.

## 7. Ví dụ Java 17: tạo và xác minh chữ ký Ed25519

Đoạn mã dưới đây sử dụng **Java Cryptography Architecture (JCA)** có sẵn trong JDK 17. Ví dụ tạo cặp khóa chỉ trong bộ nhớ để minh họa. Để tránh lỗi nối chuỗi, chương trình ký một cấu trúc byte **có version và prefix độ dài**, đồng thời dùng **cùng đúng bytes** để Verify. Ứng dụng thật sẽ lấy private signing key từ KMS/HSM hoặc signing provider có policy thích hợp.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.util.Base64;

public final class SignatureGenerationExample {
    private static void writeField(DataOutputStream out, String value)
            throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    private static byte[] invoiceBytes(
            String tenantId, String invoiceId,
            long amountMinor, String currency) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            writeField(out, "INVOICE_SIGNATURE_V1");
            writeField(out, "billing-service");
            writeField(out, tenantId);
            writeField(out, invoiceId);
            out.writeLong(amountMinor);
            writeField(out, currency);
        }
        return buffer.toByteArray();
    }

    private static byte[] sign(
            java.security.PrivateKey privateKey, byte[] bytesToSign)
            throws Exception {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(privateKey);
        signer.update(bytesToSign);
        return signer.sign();
    }

    private static boolean verify(
            java.security.PublicKey trustedPublicKey,
            byte[] signedBytes, byte[] signatureBytes) throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(trustedPublicKey);
        verifier.update(signedBytes);
        return verifier.verify(signatureBytes);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair keyPair = generator.generateKeyPair();

        byte[] original = invoiceBytes(
                "tenant-42", "inv-123", 250_000L, "VND");
        byte[] signature = sign(keyPair.getPrivate(), original);

        System.out.println("Signature (Base64): "
                + Base64.getEncoder().encodeToString(signature));
        System.out.println("Original valid: "
                + verify(keyPair.getPublic(), original, signature));

        byte[] alteredAmount = invoiceBytes(
                "tenant-42", "inv-123", 250_001L, "VND");
        System.out.println("Tampered valid: "
                + verify(keyPair.getPublic(), alteredAmount, signature));

        byte[] alteredTenant = invoiceBytes(
                "tenant-OTHER", "inv-123", 250_000L, "VND");
        System.out.println("Wrong tenant valid: "
                + verify(keyPair.getPublic(), alteredTenant, signature));

        // Không export privateKey.getEncoded() hoặc log material bí mật.
    }
}
~~~

Lưu file thành **SignatureGenerationExample.java**, chạy với JDK 17+:

~~~bash
javac SignatureGenerationExample.java
java SignatureGenerationExample
~~~

Kết quả mong đợi:

~~~text
Signature (Base64): <một chuỗi chữ ký>
Original valid: true
Tampered valid: false
Wrong tenant valid: false
~~~

Chữ ký Ed25519 phụ thuộc vào cặp khóa và message. Demo tạo **cặp khóa mới mỗi lần chạy**, nên giá trị Base64 không cố định giữa các lần chạy. Chữ ký có thể được công bố; **private key thì không**. Public key trong demo là đáng tin vì lấy ngay từ cặp khóa trong cùng chương trình. Trong hệ thống thực, không được bỏ qua việc phân phối public key từ nguồn đã xác thực.

### 7.1. Ví dụ cấu hình Java cho RSA-PSS

Khi hệ thống hoặc chuẩn nghiệp vụ yêu cầu RSA-PSS, ví dụ sau trình bày các tham số phải đồng nhất khi ký và xác minh. Đây là đoạn mã **bổ sung**, giả định đã có RSA private/public key được cấp quyền.

~~~java
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;

public final class RsaPssSignUtil {
    private static final PSSParameterSpec PSS_SHA256 =
            new PSSParameterSpec(
                    "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
                    32, PSSParameterSpec.TRAILER_FIELD_BC);

    public static byte[] sign(PrivateKey key, byte[] message)
            throws Exception {
        Signature signer = Signature.getInstance("RSASSA-PSS");
        signer.initSign(key);
        signer.setParameter(PSS_SHA256);
        signer.update(message);
        return signer.sign();
    }

    public static boolean verify(PublicKey key, byte[] message, byte[] sig)
            throws Exception {
        Signature verifier = Signature.getInstance("RSASSA-PSS");
        verifier.initVerify(key);
        verifier.setParameter(PSS_SHA256);
        verifier.update(message);
        return verifier.verify(sig);
    }
}
~~~

**PSS_SHA256** trong ví dụ quy định hash SHA-256, MGF1 dùng SHA-256 và salt length 32 byte. Không dùng mặc định ngầm định của provider khi một hợp đồng yêu cầu tham số cụ thể. Không đánh đồng **RSASSA-PSS** (signature) với **RSA/ECB/OAEPPadding** (public-key encryption); chữ **ECB** trong tên biến đổi RSA/JCA không có nghĩa RSA-OAEP là mã hóa khối AES-ECB.

## 8. Sinh chữ ký bằng KMS/HSM trong môi trường production

**KMS** thường cung cấp các API quản lý key reference, policy, vòng đời và thao tác Sign; **HSM** bảo vệ khóa trong một ranh giới mật mã chuyên dụng theo khả năng thiết bị. Dịch vụ ký có thể dùng một private key **non-exportable** bằng key handle, không bao giờ cần xem seed/private exponent.

~~~mermaid
flowchart TD
    C["Client đã xác thực"] --> S["Signing API"]
    S --> A{"Business policy và IAM hợp lệ?"}
    A -->|"Không"| X["Từ chối và audit"]
    A -->|"Có"| B["Canonicalize bytes và chọn key version"]
    B --> K["KMS Sign / HSM sign operation"]
    K --> R["Signature + keyId + algorithm"]
    R --> L[("Audit: actor, keyRef, purpose, outcome")]
    R --> V["Bên nhận lấy trusted public key để Verify"]
~~~

### 8.1. Chính sách chống signing oracle

Một **signing oracle** xuất hiện khi kẻ tấn công có thể khiến dịch vụ hoặc thiết bị ký các bytes mà họ lựa chọn mà không qua kiểm tra đủ mạnh. Private key có thể không bị export, nhưng những chữ ký giả vẫn có thể được các hệ thống khác chấp nhận.

Các lớp kiểm soát hữu ích:

1. **Xác thực caller:** dùng workload identity, mTLS hoặc cơ chế khác đúng môi trường.
2. **Least privilege:** cấp quyền Sign theo key ID, tenant, purpose và môi trường; không cấp tùy tiện ManagePolicy/DeleteKey/ExportKey.
3. **Business approval:** chỉ ký tài liệu đã thỏa quy trình nghiệp vụ, ví dụ hóa đơn ở trạng thái APPROVED.
4. **Algorithm allowlist:** kiểm tra thuật toán, định dạng message và loại khóa phù hợp; không cho client tự hạ cấp.
5. **Canonicalization:** server tự hình thành bytes cần ký từ dữ liệu đã được kiểm tra hoặc chỉ nhận tài liệu trong định dạng đã được chấp thuận.
6. **Replay/idempotency control:** quyết định ký lại cùng request có được phép không; tránh tạo nhiều tài liệu có hiệu lực từ cùng sự kiện.
7. **Rate limit, quota, anomaly detection:** phát hiện số lượt ký bất thường, tài khoản mới hoặc key use ngoài ngữ cảnh.
8. **Separation of duties:** người quản trị policy và người được phép ký không tự động có toàn bộ quyền của nhau.

**Không có khóa xuất được** chỉ giải quyết một phần vấn đề. Nếu tài khoản có quyền **Sign** bị chiếm, chữ ký hợp lệ vẫn có thể được tạo trong HSM.

### 8.2. Sign(message) hay Sign(digest)?

Một số KMS nhận raw message, một số nhận **digest đã tính sẵn**, một số dùng input type để phân biệt. Ứng dụng phải làm đúng hợp đồng:

| API | Việc ứng dụng cần làm | Rủi ro nếu nhầm |
|---|---|---|
| **Sign(message)** | Cung cấp đúng message bytes theo giới hạn API | Tự hash trước rồi ký digest như message có thể sai giao thức |
| **Sign(digest)** | Tính hash đúng thuật toán/format được yêu cầu | Gửi raw message hoặc digest sai độ dài làm thất bại hoặc ký nhầm |
| **Sign theo thuật toán Ed25519** | Dùng đúng cách xử lý message/biến thể mà provider hỗ trợ | Không tự giả định prehash Ed25519 giống ECDSA/RSA-PSS |

Hợp đồng ký bao gồm độ dài dữ liệu đầu vào, key type, algorithm variant, signature encoding, khả năng trả public key, version và audit. Không suy đoán từ tên API của một nhà cung cấp khác.

### 8.3. Nhật ký kiểm toán chữ ký số

Audit nên trả lời: **ai đã yêu cầu**, **ký dữ liệu loại gì**, **trong tenant nào**, **key version nào**, **mục đích nào**, **vào thời điểm nào**, **được phê duyệt bởi chính sách nào**, và **kết quả ra sao**. Không ghi raw private key, tài liệu mật hoặc access token vào nhật ký.

Nếu cần nhận dạng chính xác tài liệu mà không lưu nội dung, có thể ghi **digest/fingerprint của cấu trúc được ký** theo policy. Tuy nhiên digest của dữ liệu có entropy thấp có thể tiết lộ thông tin qua dictionary attack; đánh giá tính nhạy cảm trước khi đưa vào log.

## 9. Quản lý vòng đời của signing key

~~~mermaid
flowchart TD
    A["Tạo khóa ký với CSPRNG/provider được kiểm chứng"] --> B["Gắn owner, keyId, version, SIGN_VERIFY purpose"]
    B --> C["Giữ private key trong KMS/HSM/kho bảo vệ"]
    C --> D["Phân phối public key qua nguồn tin cậy"]
    D --> E["Kích hoạt Sign; giới hạn theo IAM và policy"]
    E --> F["Theo dõi audit, thời hạn và sự cố"]
    F --> G["Tạo key version mới và công bố public key mới"]
    G --> H["Chuyển chữ ký mới sang private key mới"]
    H --> I["Ngừng Sign bằng khóa cũ; quản lý Verify lịch sử"]
    I --> J["Thu hồi/vô hiệu hóa/hủy theo chính sách"]
~~~

| Giai đoạn | Hành động khuyến nghị | Lỗi thường gặp |
|---|---|---|
| **Key generation** | CSPRNG, thuật toán/size/curve phù hợp; key purpose được định nghĩa | Tự tạo khóa từ password/timestamp hoặc tái sử dụng khóa giải mã |
| **Provisioning** | Gắn tenant/owner, key ID/version và quyền Sign cụ thể | Một private key dùng chung cho mọi dịch vụ và môi trường |
| **Storage** | Non-exportable nếu phù hợp; backup, access policy, bảo vệ cấu hình | Private key PEM chưa mã hóa trong Git/CI/container image |
| **Signing** | Xác thực caller, policy và bytes; audit theo request | Ký mọi bytes do client tùy ý gửi |
| **Rotation** | Public key mới được công bố, traffic ký mới chuyển version | Thay key alias nhưng không báo bên verify |
| **Retirement** | Chặn ký mới bằng khóa cũ; giữ khả năng verify lịch sử nếu cần | Xóa public key cũ làm hệ thống không xác minh tài liệu cũ |
| **Revocation/incident response** | Disable key, xem xét trust/revocation của certificate, khoanh vùng chữ ký | Nghĩ chỉ rotate khóa là vô hiệu hóa mọi chữ ký đã bị tạo sai |
| **Destruction** | Phê duyệt, bảo đảm yêu cầu pháp lý/lưu trữ, xử lý backup | Hủy material khi vẫn còn quy trình cần dùng |

### 9.1. Private key cũ và public key cũ có vòng đời khác nhau

Sau khi chuyển **sign-v3 → sign-v4**, hệ thống không nên tiếp tục Sign bằng v3 nếu đã retire, nhưng tài liệu đã ký bằng v3 có thể vẫn cần **public key v3** để Verify. **Hủy private key v3 không làm public key v3 mất hiệu lực toán học** và không biến signature v3 thành signature v4.

Ngược lại, nếu private key v3 bị lộ, phải phân biệt **chữ ký trước thời điểm nghi lộ** và **chữ ký có thể bị tạo trái phép**. Khả năng tin cậy chữ ký lịch sử phụ thuộc chính sách, chứng cứ thời gian ký, chuỗi chứng thư, trạng thái thu hồi và yêu cầu nghiệp vụ; một lần Verify toán học không tự giải quyết được toàn bộ vấn đề.

### 9.2. Thu hồi chứng thư khác vô hiệu hóa khóa KMS

- **Disable key ở KMS/HSM:** hạn chế thao tác Sign tại môi trường quản lý khóa đó.
- **Certificate revocation:** thông báo thay đổi trạng thái tin cậy của chứng thư trong một hệ thống PKI theo cơ chế phù hợp (như CRL/OCSP).
- **Xóa public key khỏi JWKS:** có thể làm bên nhận không Verify được token còn hiệu lực; các key đã cache không tự biến mất.

Khi private key nghi bị lộ, cần **ngừng ký rủi ro, thay khóa, cập nhật nguồn public key/chứng thư, đánh giá dữ liệu và chữ ký bị ảnh hưởng, xử lý quyền và bản sao backup**, đồng thời duy trì chứng cứ phục vụ điều tra.

### 9.3. Long-term validation

Tài liệu cần được kiểm tra trong nhiều năm có thể đòi hỏi dữ liệu bổ trợ như **certificate chain, trạng thái thu hồi tại thời điểm phù hợp, dấu thời gian tin cậy và thông tin thuật toán** theo chuẩn/chính sách của lĩnh vực. Chỉ lưu **signature + public key** có thể chưa đủ cho yêu cầu kiểm tra lâu dài hoặc tuân thủ pháp lý.

Không lấy **thời gian trên máy chủ ký** hoặc trường **signedAt** do client tự gửi làm bằng chứng thời gian được bên thứ ba tin cậy. Nếu cần **trusted timestamp**, dùng quy trình và dịch vụ chứng thực thời gian tương ứng, có kiểm soát nguồn tin cậy và audit.

## 10. Signature generation trong các tình huống thực tế

### 10.1. Phát hành JWT/JWS

**Auth Service** ký token bằng private key (ví dụ EdDSA, RS256/PS256, ES256 theo chính sách), còn **API Gateway** kiểm tra signature bằng public key đáng tin cậy. **kid** trong header là tham chiếu chọn key trong tập đã tin, không phải nguồn cấp khóa độc lập.

Trong quá trình Verify cần kiểm tra **iss, aud, exp, nbf** và những claim bắt buộc, đồng thời giới hạn thuật toán. JWT được ký theo JWS **không tự mã hóa payload**; nếu cần bí mật phải chọn JWE hoặc giải pháp mã hóa khác.

Khi rotation, Auth Service cần đồng bộ việc công bố public key mới và chuyển key ký, có khoảng chồng lấn hợp lý để bên Verify xử lý token cũ. Nếu khóa cũ lộ, quyết định tiếp tục chấp nhận token v3 phải dựa trên đánh giá rủi ro, không chỉ TTL cache.

### 10.2. Ký hóa đơn/hồ sơ điện tử

Dịch vụ ký kiểm tra trạng thái **APPROVED**, người phê duyệt, tenant và loại tài liệu trước khi Sign. Tài liệu phải có **định dạng bytes được chốt**; nếu ký hash tham chiếu, phải xác minh rằng hash gắn đúng tài liệu cần bảo vệ.

Hồ sơ lưu kèm **signature, thuật toán, key/certificate reference, version và dữ liệu chứng cứ bổ trợ** nếu yêu cầu lưu trữ dài hạn. Các điều kiện pháp lý về chữ ký điện tử/chữ ký số phụ thuộc lĩnh vực và khu vực pháp lý; chữ ký hợp lệ về mật mã không tự xác nhận mọi yêu cầu pháp lý.

### 10.3. Ký phần mềm/firmware

Nhà phát hành ký **artifact hoặc manifest** bằng private signing key. Trình cài đặt/thiết bị xác minh bằng public key đã pin hoặc chuỗi tin cậy trước khi chấp nhận. **SHA-256 digest công bố cạnh artifact từ cùng một nguồn bị chiếm** không thay thế chữ ký phát hành.

Đối với firmware, còn phải kiểm soát **version downgrade/rollback**, key revocation và khả năng khôi phục khi khóa cập nhật bị lộ. Một firmware đã ký hợp lệ nhưng thuộc phiên bản cũ có lỗ hổng có thể vẫn nguy hiểm nếu không có chính sách chống rollback.

## 11. Threat model: Những lỗi làm chữ ký số trở nên vô nghĩa

| Lỗi thiết kế | Hậu quả | Biện pháp |
|---|---|---|
| **Private key trong Git, CI logs hoặc image** | Kẻ tấn công tự tạo signature hợp lệ | Không commit/log material, dùng KMS/HSM, rotate khi rò rỉ |
| **Sign permission quá rộng** | Tài khoản bị chiếm tạo chữ ký giả qua KMS/HSM | Least privilege, policy theo tenant/purpose, phê duyệt nghiệp vụ |
| **Lấy public key từ request không tin cậy** | Xác minh bằng khóa của kẻ tấn công | PKI/trust store, allowlist issuer và endpoint lấy khóa |
| **Ký một JSON khác với JSON được bên nhận verify** | Signature thất bại hoặc xác thực sai dữ liệu | Quy định raw bytes/canonicalization và version |
| **Không ràng buộc purpose, issuer, amount, tenant** | Chữ ký bị dùng lại ở ngữ cảnh khác | Domain separation, ký đầy đủ trường an ninh |
| **ECDSA nonce k bị lặp/dễ đoán** | Có thể làm lộ private signing key | Provider chuẩn, nonce an toàn, kiểm thử và giám sát |
| **RSA-PSS thiếu thống nhất MGF/salt** | Không verify hoặc dùng nhầm cấu hình | Explicit algorithm parameters và interoperability tests |
| **Hash(message) được gọi là signature** | Bất kỳ ai cũng tạo “bằng chứng” giả | Sign bằng private key, Verify bằng public key tin cậy |
| **Không kiểm tra alg/kid/purpose** | Algorithm confusion và chọn nhầm khóa | Allowlist, kiểm tra key type, issuer, purpose, version |
| **Không chống replay** | Lệnh ký hợp lệ bị phát lại để thực thi lần nữa | Message ID, expiry/sequence, idempotency và policy |
| **Bỏ qua certificate chain/revocation policy** | Tin khóa không còn được chấp thuận | Xác thực đường tin cậy, trạng thái và mốc thời gian phù hợp |
| **Xóa public key lịch sử vô kế hoạch** | Không thể Verify chữ ký cũ | Retain verification material theo quy định lưu trữ |
| **Audit chứa secret hoặc tài liệu nhạy cảm** | Rò rỉ private data/credential | Log metadata đủ dùng, redaction và phân quyền log |
| **Nhầm signature với encryption** | Nội dung ký vẫn bị đọc được | Mã hóa payload bằng AEAD/envelope khi cần bí mật |

## 12. Checklist triển khai dịch vụ tạo chữ ký số

1. **Mục đích:** private key chỉ được dùng cho **SIGN**, không tự tái sử dụng làm khóa giải mã/unwrap.
2. **Key generation:** dùng thuật toán, curve/key size và CSPRNG/provider phù hợp.
3. **Key storage:** khóa nằm ở đâu; có export được không; chính sách backup/restore và bảo vệ bộ nhớ ra sao?
4. **Public-key trust:** bên verify lấy public key từ nguồn nào; ràng buộc nó với issuer, owner, purpose bằng cách nào?
5. **Message format:** bytesToSign được xác định/canonical hóa chính xác chưa; có domain và schema version không?
6. **Policy:** có kiểm tra caller, tenant, document state, amount, purpose, key state và quyền Sign trước khi ký không?
7. **Algorithm contract:** Ed25519/ECDSA/RSA-PSS có được cấu hình đúng message/digest input, hash, MGF, salt và signature encoding không?
8. **Signature package:** đã gắn key ID/version, thuật toán và thông tin xác minh cần thiết chưa? Metadata có được bảo vệ theo giao thức?
9. **Replay:** các lệnh nhạy cảm có request ID/timestamp/expiry/sequence và kiểm tra xử lý lặp không?
10. **Rotation:** đã có cách phát hành public key mới và Verify chữ ký/token lịch sử khi khóa ký mới hoạt động chưa?
11. **Incident response:** khi private key hoặc quyền Sign bị chiếm, có thể disable, rotate, thu hồi chứng thư, khoanh vùng chữ ký và điều tra audit không?
12. **Long-term validation:** tài liệu cần lưu lâu có yêu cầu timestamp, chứng thư và chứng cứ thu hồi phù hợp không?

### Câu hỏi tự kiểm tra

**Câu 1.** Một dịch vụ chỉ cần Verify chữ ký hóa đơn. Dịch vụ đó có cần private key không?

**Trả lời:** **Không.** Nó cần message bytes, signature và public key đáng tin cậy cùng thông số thuật toán.

**Câu 2.** Chữ ký hợp lệ trên một JSON đã chứng minh người gửi hợp pháp đồng ý với toàn bộ giao dịch chưa?

**Trả lời:** **Chưa.** Cần xác thực nguồn public key, thẩm quyền Sign, quy trình phê duyệt và bảo đảm tất cả trường nghiệp vụ quan trọng nằm trong message được ký.

**Câu 3.** Tại sao không nên viết **SHA256(secret || message)** thay cho Sign?

**Trả lời:** Đó không phải sơ đồ chữ ký bất đối xứng và cũng không thay thế HMAC được chuẩn hóa. Chữ ký số yêu cầu thuật toán Sign/Verify với private/public key.

**Câu 4.** Ed25519 và RSA-PSS có nên luôn được nhận đầu vào SHA-256 digest từ ứng dụng không?

**Trả lời:** **Không.** Phải theo đúng biến thể và API. Ed25519 thông thường nhận message và hash nội bộ; RSA-PSS qua KMS có thể nhận message hoặc digest tùy contract.

**Câu 5.** Nếu private signing key nằm trong HSM non-exportable thì liệu kẻ chiếm tài khoản có quyền Sign còn tạo chữ ký được không?

**Trả lời:** **Có thể.** Quyền sử dụng khóa là một bề mặt tấn công riêng; cần IAM, chính sách tài liệu, hạn mức và audit.

**Câu 6.** Sau khi rotate từ sign-v2 sang sign-v3, có thể xóa public key v2 ngay không?

**Trả lời:** **Không thể mặc định.** Tài liệu/token ký bằng v2 có thể còn cần Verify; phải theo chính sách lưu trữ, thời hạn và tình trạng khóa.

**Câu 7.** Một signature cũ đúng byte và đúng public key có luôn được dùng để thực thi lại một yêu cầu chuyển tiền không?

**Trả lời:** **Không.** Verify chỉ xét chữ ký; ứng dụng vẫn phải kiểm tra expiry, request ID, số thứ tự, quyền và idempotency để chặn replay.

**Điểm cốt lõi:** **Signature generation** là quá trình tạo bằng chứng mật mã bằng **private signing key trên những byte đã xác định chính xác**, không phải hash hay encryption. Bảo mật thực tế đòi hỏi **xác thực và ủy quyền yêu cầu ký, thuật toán đúng, public-key trust, quản lý khóa trong KMS/HSM, audit và vòng đời rotation/revocation**; chỉ có chữ ký đúng toán học thì chưa đủ để bảo đảm một nghiệp vụ an toàn.
