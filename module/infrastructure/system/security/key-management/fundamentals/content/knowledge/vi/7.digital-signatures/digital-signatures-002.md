# Signing key (Khóa dùng để ký số)

## 1. Signing key là gì?

**Signing key** là khóa mật mã được dùng để tạo **chữ ký số (digital signature)** trên thông điệp hoặc đối tượng dữ liệu. Trong hệ chữ ký số bất đối xứng, signing key thường chính là **private key (khóa riêng tư)** của một cặp khóa; bên nhận dùng **public key (khóa công khai)** tương ứng để xác minh chữ ký.

~~~text
Bên ký                                     Bên xác minh
--------                                   --------------
Thông điệp M                               Nhận M + chữ ký
      |                                             |
      v                                             v
Sign(private signing key, M)          Verify(public key, M, signature)
      |                                             |
      v                                             v
Chữ ký S -----------------------------> Đúng / Sai
~~~

Chữ ký số được thiết kế để hỗ trợ:

- **Tính toàn vẹn (integrity):** sửa nội dung đã ký khiến phép kiểm tra chữ ký không còn hợp lệ, trong điều kiện thuật toán và quy trình xác minh được dùng đúng.
- **Xác thực nguồn gốc theo khóa:** chữ ký hợp lệ cho biết người tạo chữ ký có khả năng sử dụng private key tương ứng hoặc quyền yêu cầu hệ thống bảo vệ khóa ký thay mình.
- **Bằng chứng quy trách nhiệm:** khi kết hợp danh tính, quyền, kiểm toán, timestamp đáng tin và các chính sách liên quan, chữ ký có thể góp phần làm bằng chứng về việc phát hành/phê duyệt. Việc này **không mặc nhiên tạo hiệu lực pháp lý** chỉ vì thuật toán Verify trả về true.

**Signing key không mã hóa thông điệp.** Thông điệp và chữ ký vẫn có thể được đọc nếu không có lớp mã hóa riêng. Muốn bảo vệ bí mật của dữ liệu cần cơ chế như AES-GCM với khóa mã hóa dữ liệu (DEK).

Ví dụ: dịch vụ thanh toán dùng private signing key để ký phiếu giao dịch; hệ thống kế toán dùng public key đã được xác thực để xác định phiếu có thực sự xuất phát từ dịch vụ được ủy quyền và có bị sửa đổi không.

Trong chương **Chữ ký số** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, signing key kết nối trọn vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy** với mật mã bất đối xứng, KMS/HSM, kiểm soát truy cập, kiểm toán và thiết kế hệ thống bảo vệ khóa. Nó có thể phối hợp với mật mã đối xứng và envelope encryption trong cùng kiến trúc.

## 2. Private signing key và public verification key

Một cặp khóa dùng cho chữ ký số bao gồm:

| Thành phần | Vai trò | Ai được giữ? | Biện pháp bảo vệ |
|---|---|---|---|
| **Private signing key** | Tạo chữ ký trên message | Chủ thể ký hoặc miền tin cậy như KMS/HSM | Bí mật vật liệu khóa, quản lý quyền Sign và lịch sử sử dụng |
| **Public verification key** | Xác minh chữ ký | Có thể được công bố | Xác thực chủ sở hữu và mục đích của khóa |
| **Key ID / version** | Chỉ đúng khóa để ký/xác minh | Metadata có thể công khai | Không nhầm ID với bằng chứng danh tính |
| **Certificate** (nếu có) | Gắn public key với danh tính qua PKI | Phân phối tới verifier | Kiểm tra chuỗi tin cậy, thời hạn và trạng thái thu hồi |
| **Signature** | Kết quả được gắn với message | Truyền/lưu cùng hiện vật | Kiểm tra đúng message, định dạng, thuật toán và ngữ cảnh |

**Private signing key phải được bảo vệ ngay cả khi nó không được export ra khỏi HSM.** Một dịch vụ có quyền Sign quá rộng bị chiếm quyền có thể tạo chữ ký trái phép thông qua API, dù private key không bị sao chép.

**Public key không cần bí mật**, nhưng phải được lấy từ nguồn đáng tin. Nếu kẻ tấn công thay public key của dịch vụ bằng khóa do họ kiểm soát, một verifier không có chính sách xác thực khóa có thể chấp nhận chữ ký giả mạo.

### 2.1. Signing key có thể chỉ secret HMAC không?

Một số nền tảng gọi bí mật dùng cho **HMAC-SHA-256** hoặc JWT **HS256** là signing key. Thuật ngữ sản phẩm này có thể gây nhầm lẫn với chữ ký số bất đối xứng:

| Cơ chế | Tạo tag/chữ ký bằng | Xác minh bằng | Khác biệt |
|---|---|---|---|
| **Digital signature (ECDSA, Ed25519, RSA-PSS)** | **Private key** | **Public key** | Verifier không cần biết bí mật có khả năng ký |
| **HMAC-SHA-256** | **Shared secret** | **Cùng shared secret** | Bất kỳ bên nào biết secret đều có thể tạo tag hợp lệ |
| **SHA-256 hash** | Không dùng key | Tính lại digest | Không tự xác thực người gửi hoặc chủ sở hữu |

Trong bài này, **signing key** chủ yếu mang nghĩa **private key dùng ký số**. Khi đọc tài liệu API, luôn kiểm tra thuật toán thực tế thay vì suy diễn từ tên một trường như signingSecret.

## 3. Thuật toán sử dụng signing key

Không phải mọi private key đều có thể dùng để tạo chữ ký theo mọi chuẩn:

| Thuật toán/sơ đồ | Signing key | Verification key | Điểm cần lưu ý |
|---|---|---|---|
| **ECDSA P-256 + SHA-256** | EC private key trên đường cong P-256 | EC public key tương ứng | Bảo vệ nonce k từng lần ký; phân biệt DER và raw signature |
| **Ed25519 (EdDSA)** | Ed25519 private key | Ed25519 public key | Thuật toán và encoding khác ECDSA |
| **RSA-PSS + SHA-256** | RSA private key | RSA public key | Tuân thủ tham số hash, MGF và salt-length |
| **RSA PKCS#1 v1.5 signing** | RSA private key | RSA public key | Còn gặp trong hệ thống cũ; cần chính sách thuật toán rõ ràng |
| **HMAC-SHA-256** | Shared secret đối xứng | Cùng shared secret | Là MAC, không phải chữ ký số xác minh công khai |
| **AES-GCM** | DEK đối xứng | DEK để decrypt/verify tag | Mã hóa có xác thực, không phải ký số |
| **X25519 / ECDH** | Private key thỏa thuận khóa | Public key thỏa thuận khóa | Dùng để thiết lập bí mật chung, không thay private signing key |

Khi tạo signing key phải cố định **algorithm, curve hoặc kích thước khóa, purpose/key usage, môi trường và cryptoperiod**. Một private key Ed25519 không thể được chuyển thành ECDSA chỉ bằng việc đổi tên thuật toán trong metadata.

Không nên dùng cùng một vật liệu khóa tùy tiện cho ký số, mã hóa hoặc dẫn xuất bí mật phiên. Những mục đích này có cách sử dụng, giới hạn an toàn và yêu cầu vòng đời khác nhau.

## 4. Signing key tham gia phép ký ra sao?

~~~text
message bytes (M)
        |
        v
Sign algorithm + private signing key
        |
        v
signature bytes (S)

Verify(public key, M, S) -> true / false
~~~

Ví dụ **SHA256withECDSA** thường băm thông điệp bằng SHA-256 trong thao tác ký. Một số API Sign trong KMS/HSM nhận **toàn message** và tự băm; một số khác chỉ nhận **digest đã băm**. Ứng dụng phải hiểu rõ hợp đồng input để tránh **double hashing** hoặc ký sai dữ liệu.

### 4.1. Ký byte, không ký "ý nghĩa" của JSON

Hai JSON có thể tương đương về nghiệp vụ nhưng có chuỗi byte khác nhau:

~~~json
{"amount":15000,"currency":"VND"}
~~~

~~~json
{ "currency": "VND", "amount": 15000 }
~~~

Nếu ký byte của chuỗi đầu tiên nhưng xác minh trên byte của chuỗi thứ hai, chữ ký có thể không hợp lệ. Thiết kế giao thức phải chỉ rõ:

1. Encoding (chẳng hạn **UTF-8**) và quy tắc xử lý Unicode.
2. Những trường bắt buộc, thứ tự, định dạng số, dấu phân cách và quy tắc escape, hoặc một dạng **canonicalization** đã được quy định.
3. Ngữ cảnh: **version, purpose/domain, issuer, tenant, transaction ID**.
4. Timestamp, thời hạn hoặc request ID nếu cần chống phát lại.
5. Key reference, thuật toán và signature encoding được chấp nhận.

**Không đưa trực tiếp payload do client tùy ý cung cấp vào dịch vụ ký** mà bỏ qua việc xác định dữ liệu có được phê duyệt hợp lệ hay không.

### 4.2. Domain separation và chống tráo đổi ngữ cảnh

Giả sử cùng signing key được phép ký hai loại đối tượng. Nếu thông điệp ký không chứa mục đích, chữ ký của tài liệu loại A có thể bị dùng lại như chứng cứ cho loại B khi byte trùng.

Có thể thiết kế một thông điệp nghiệp vụ có cấu trúc rõ ràng:

~~~text
protocolVersion = "v1"
purpose = "payment-approval"
tenant = "tenant-42"
transactionId = "tx-901"
amountMinor = 150000
currency = "VND"
issuedAt = "2026-11-28T02:00:00Z"
~~~

Đây chỉ là **mẫu dữ liệu**. Ứng dụng phải định nghĩa chính xác bytes chuẩn hóa, giới hạn độ dài và cách xác thực từng trường. Verifier cần kiểm tra purpose, tenant, amount, quyền và trạng thái giao dịch, không chỉ phép Verify.

### 4.3. Chữ ký hợp lệ có chống replay không?

**Không tự động.** Một chữ ký hợp lệ vẫn có thể được gửi lại cùng thông điệp. Các hệ thống thanh toán, token hoặc cập nhật phần mềm cần thêm **request ID/transaction ID duy nhất, sequence number, version chống rollback, timestamp, cửa sổ hiệu lực hoặc trạng thái đã xử lý** tùy mô hình.

## 5. Public key trust và chứng chỉ số

Chữ ký toán học hợp lệ và **quyết định chấp nhận giao dịch** là hai lớp khác nhau:

~~~mermaid
flowchart TD
    A["Nhận message + signature + key reference"] --> B["Chọn algorithm/key theo allowlist"]
    B --> C["Lấy public key từ nguồn được xác thực"]
    C --> D["Kiểm tra certificate, usage, expiry, revocation"]
    D --> E["Verify đúng message bytes"]
    E --> F{"Signature hợp lệ?"}
    F -->|Không| X["Từ chối"]
    F -->|Có| G["Kiểm tra issuer, audience, purpose và quyền"]
    G --> H["Kiểm tra timestamp, transaction ID, chống replay"]
    H --> I["Chấp nhận theo chính sách"]
~~~

### 5.1. PKI và X.509

Một chứng chỉ số X.509 có thể gắn public key với danh tính thông qua PKI. Bên kiểm tra cần xác minh:

- Chuỗi chứng chỉ đến **trust anchor** được chấp nhận.
- **Danh tính** phù hợp mục đích: hostname, tổ chức, service hoặc ứng dụng.
- Thời hạn, các trường **key usage / extended key usage** và chính sách.
- Trạng thái thu hồi theo cơ chế được áp dụng, ví dụ **CRL/OCSP**.
- Thuật toán, tham số đường cong, signature encoding và giới hạn tin cậy.

Chứng chỉ hết hạn hoặc bị thu hồi **không làm phương trình chữ ký mất đúng về mặt toán học**. Nhưng verifier cần áp dụng chính sách về thời điểm và điều kiện tin cậy.

### 5.2. Key ID, alias, JWKS và trust store

Key ID hoặc trường **kid** trong JWT/JWS chỉ là **đầu mối tìm khóa**. Nó không chứng minh khóa thuộc đúng issuer. Verifier không được cho một header do người gửi kiểm soát quyết định tự do URL hoặc public key đáng tin.

Với **JWKS (JSON Web Key Set)**, public key phải đến từ issuer và nguồn đã được cấu hình tin cậy. Khi rotate hoặc thu hồi, cần tính tới **cache TTL, client offline, gateway và các bản triển khai chưa cập nhật**; phải kiểm thử mọi verifier chứ không chỉ thay JWKS tại nguồn.

## 6. Sinh signing key an toàn

Một private signing key mạnh cần được tạo bằng **thuật toán, tham số và nguồn entropy phù hợp**, rồi lưu và cấp quyền theo chính sách:

| Yêu cầu | Cách triển khai |
|---|---|
| **Thuật toán phù hợp** | Chọn ECDSA/EdDSA/RSA-PSS theo giao thức và provider được cho phép |
| **Entropy** | Sinh khóa qua CSPRNG hoặc HSM/KMS đáng tin |
| **Tham số đúng** | Chọn curve, kích thước RSA và cách ký phù hợp tiêu chuẩn |
| **Miền tạo khóa** | Ưu tiên sinh trực tiếp trong KMS/HSM với thuộc tính không xuất được khi phù hợp |
| **Nhận dạng** | Ghi key ID/version, chủ sở hữu, key usage=sign, môi trường, cryptoperiod |
| **Public key distribution** | Công bố qua PKI, trust store hoặc JWKS từ nguồn đáng tin |
| **Quyền tối thiểu** | Chỉ cấp Sign cho đúng workload và đúng nhiệm vụ |

Không tạo private key từ mật khẩu ngắn, timestamp, số tăng dần, UUID hoặc một vòng hash chuỗi dễ đoán. SHA-256 không làm đầu vào entropy thấp trở thành vật liệu khóa ngẫu nhiên chất lượng cao.

### 6.1. Nonce k của ECDSA

ECDSA dùng một bí mật **k theo từng lần ký**. Nếu k bị lộ trong một chữ ký, private key có thể bị suy ra. Nếu cùng k được dùng lại để ký **hai thông điệp khác nhau** với cùng private key, private key cũng có nguy cơ được khôi phục từ các phương trình chữ ký.

- Dùng thư viện/provider đã được kiểm chứng, CSPRNG phù hợp hoặc cơ chế **deterministic k theo RFC 6979** khi được hỗ trợ.
- Không tự tạo k bằng timestamp, seed cố định hoặc bộ đếm dễ đoán.
- Không log k, không xuất dữ liệu trung gian mật mã và phải quan tâm tới kênh kề.
- Không mặc định mọi provider Java ECDSA sử dụng RFC 6979; cần xem tài liệu provider.

**Nonce k của ECDSA khác nonce AES-GCM**: k ECDSA phải **bí mật**; nonce AES-GCM thường được lưu công khai kèm ciphertext nhưng phải **duy nhất với cùng khóa mã hóa**. Ed25519 và RSA-PSS có cơ chế riêng, không áp dụng máy móc cách sinh k của ECDSA cho chúng.

## 7. Lưu signing key: KMS, HSM và keystore

| Cách lưu | Lợi ích | Giới hạn |
|---|---|---|
| **HSM với khóa non-exportable** | Private key được giữ và thao tác ký thực hiện trong miền phần cứng | Caller có quyền Sign vẫn có thể lạm dụng |
| **Managed KMS** | API key lifecycle, IAM, audit và rotation tập trung | Thuật toán, giới hạn dữ liệu, xuất khóa và cơ chế phiên bản tùy nhà cung cấp |
| **Keystore trên host/PKCS#11** | Phù hợp một số yêu cầu tích hợp hoặc môi trường local | Phụ thuộc host hardening, mật khẩu, backup và provider |
| **Secret store hoặc file mã hóa** | Hỗ trợ môi trường đặc thù | Có thể phải tải private key dạng rõ vào RAM ứng dụng |
| **Hard-code trong source/image** | Không có giá trị bảo mật tương xứng | Lộ qua repository, artifacts, logs, CI và image layers |

**KMS/HSM không thay cho quản lý quyền và nghiệp vụ.** Nếu service A có quyền ký mọi byte bằng khóa tổ chức, kẻ tấn công chiếm service A có thể yêu cầu tạo chữ ký hợp lệ mà không lấy được private key.

Việc **backup private key** cần có chủ đích. Một số hệ thống yêu cầu phục hồi danh tính ký; hệ thống khác có thể thay private key mới và lưu public key cùng bằng chứng để xác minh tài liệu cũ. Bản sao lưu làm tăng bề mặt rò rỉ, nên phải kiểm kê, kiểm soát truy cập, mã hóa và xử lý hủy theo chính sách.

## 8. Kiến trúc thao tác ký qua KMS/HSM

~~~mermaid
flowchart LR
    U["Ứng dụng nghiệp vụ"] --> A["Xác thực caller & kiểm tra quyền ký"]
    A --> M["Xây dựng message bytes được chuẩn hóa"]
    M --> K["KMS/HSM Sign(key ID, algorithm, message hoặc digest)"]
    K --> S["Signature + key reference"]
    S --> V["Dịch vụ xác minh"]
    P["Public key / chứng chỉ đáng tin"] --> V
    V --> F["Verify + trust + nghiệp vụ"]
~~~

Một luồng thực tế:

1. Workload xác thực với IAM để xin sử dụng một signing key.
2. Ứng dụng kiểm tra **người yêu cầu, tenant, trạng thái phê duyệt, hạn mức và mục đích**.
3. Ứng dụng dựng đúng message bytes, chỉ chọn thuật toán đã cho phép.
4. KMS/HSM kiểm tra key policy rồi thực hiện Sign.
5. Ứng dụng trả signature và metadata đủ để bên kiểm tra xác định đúng public key.
6. Verifier xác minh chữ ký rồi kiểm tra **danh tính, trạng thái tin cậy, quyền và chống replay**.

### 8.1. Message hay digest?

Một số API Sign nhận **toàn message** và tự băm; API khác nhận **digest đã tính sẵn**. Nếu caller đưa SHA-256(message) vào API tự hash SHA-256, hệ thống có thể ký lên giá trị bị hash hai lần, gây sai hợp đồng và không tương thích với verifier.

Phải xác nhận rõ **input format, algorithm, curve/hash, signature format, maximum payload và error handling** của provider. Không tự hash trước khi gọi API chỉ vì cho rằng thêm một lần hash an toàn hơn.

### 8.2. IAM và kiểm soát việc ký

Tách quyền **Sign**, **Verify/GetPublicKey**, **Rotate**, **Disable**, **Delete**, **ChangePolicy** và **AuditRead**. Service chỉ cần ký chứng từ không mặc nhiên được đổi policy hoặc hủy khóa.

Cần áp dụng **least privilege**, phân tách nhiệm vụ, hạn mức thao tác và giám sát. Một service thử nghiệm không được phép ký chứng từ sản xuất. Nếu nghiệp vụ đòi hỏi phê duyệt hai người, phải thực thi ở tầng ứng dụng hoặc quy trình có thẩm quyền, thay vì chỉ dựa trên việc private key nằm trong HSM.

## 9. Java JCA: tạo, ký và xác minh bằng ECDSA P-256

Ví dụ dùng **Java Cryptography Architecture (JCA)** với ECDSA P-256 và SHA-256. Khóa được tạo trong bộ nhớ chỉ cho mục đích học thuật, chưa có lưu trữ KMS/HSM hoặc chứng chỉ.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;

public final class SigningKeyExample {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(
            new ECGenParameterSpec("secp256r1"), new SecureRandom()
        );
        KeyPair pair = generator.generateKeyPair();

        byte[] message = (
            "purpose=payment-approval;tenant=42;"
          + "order=901;amountMinor=150000;currency=VND"
        ).getBytes(StandardCharsets.UTF_8);

        // Chỉ bên ký được quyền sử dụng private key.
        Signature signer = Signature.getInstance("SHA256withECDSA");
        signer.initSign(pair.getPrivate(), new SecureRandom());
        signer.update(message);
        byte[] signature = signer.sign();

        // Bên nhận phải có public key đã xác thực đúng chủ sở hữu.
        Signature verifier = Signature.getInstance("SHA256withECDSA");
        verifier.initVerify(pair.getPublic());
        verifier.update(message);

        if (!verifier.verify(signature)) {
            throw new IllegalStateException("Invalid signature");
        }

        byte[] modified = (
            "purpose=payment-approval;tenant=42;"
          + "order=901;amountMinor=250000;currency=VND"
        ).getBytes(StandardCharsets.UTF_8);

        Signature modifiedVerifier =
            Signature.getInstance("SHA256withECDSA");
        modifiedVerifier.initVerify(pair.getPublic());
        modifiedVerifier.update(modified);

        if (modifiedVerifier.verify(signature)) {
            throw new IllegalStateException("Modified data was accepted");
        }
        System.out.println("ECDSA sign/verify OK");
    }
}
~~~

Giải thích:

- **Private key** dùng với **initSign**, **public key** với **initVerify**. Bên xác minh không cần và không nên nhận private key.
- **SHA256withECDSA** thường tự băm thông điệp theo thuật toán Signature. Không tự hash thêm khi API mong message.
- **SecureRandom** không khiến ứng dụng trực tiếp chọn nonce k. Provider chịu trách nhiệm thao tác nội bộ; cần đánh giá provider và HSM dùng trong sản xuất.
- Thay một byte nội dung sẽ khiến chữ ký cũ không còn khớp.
- Nhiều provider JCA trả chữ ký ECDSA ở dạng **ASN.1 DER**, còn **JWS ES256** quy định chữ ký dạng raw **r ∥ s** (64 byte). Phải dùng API hoặc chuyển đổi encoding đúng chuẩn trước khi nhúng vào JWT.
- Ví dụ minh họa byte từ chuỗi; ứng dụng thật cần định nghĩa canonical bytes, kiểm tra public key trust, chứng chỉ, quyền nghiệp vụ và chống replay.

## 10. Trường hợp triển khai: dịch vụ ký phiếu giao dịch

Giả sử nền tảng có **Approval Service** ký lệnh thanh toán, **Ledger Service** ghi sổ và **Audit Service** lưu bằng chứng.

~~~mermaid
flowchart TD
    R["Yêu cầu phê duyệt"] --> A["Approval Service: kiểm tra quyền"]
    A --> B["Canonical payment manifest"]
    B --> K["KMS/HSM: signing key v5"]
    K --> S["Manifest + signature + key version"]
    S --> L["Ledger: Verify + policy"]
    S --> Q["Audit: lưu bằng chứng"]
    P["Public key / trust store"] --> L
    P --> Q
~~~

Chỉ **Approval Service** cần quyền Sign. **Ledger** và **Audit** chỉ cần public verification key cùng chính sách tin cậy; không sao chép private key sang hai dịch vụ chỉ để xác minh.

Một manifest minh họa:

~~~json
{
  "version": "v1",
  "purpose": "payment-approval",
  "tenantId": "tenant-42",
  "transactionId": "tx-901",
  "amountMinor": 150000,
  "currency": "VND",
  "issuedAt": "2026-11-28T02:00:00Z",
  "keyId": "payment-signing-key",
  "keyVersion": "v5"
}
~~~

Phải quy định **đúng byte của manifest được ký**. Metadata như thuật toán, issuer, version và key reference phải được ràng buộc với đối tượng theo thiết kế giao thức để tránh thay đổi ngữ cảnh. Ledger vẫn phải kiểm tra **tenant, transactionId, trạng thái chưa xử lý, hạn mức và quyền phát hành** ngay cả khi chữ ký hợp lệ.

## 11. Vòng đời signing key: từ tạo đến hủy

Một signing key phải có **chủ sở hữu, mục đích, phiên bản, khoảng sử dụng và chính sách tin cậy** rõ ràng. Mục đích của quản lý vòng đời là vừa bảo vệ quyền tạo chữ ký mới, vừa duy trì khả năng kiểm tra chứng cứ hợp lệ.

~~~mermaid
flowchart LR
    A["Tạo / import signing key"] --> B["Cấp quyền Sign và public key"]
    B --> C["Lưu private key trong miền tin cậy"]
    C --> D["Ký, giám sát và kiểm toán"]
    D --> E["Rotation: tạo key version mới"]
    E --> F["Ngừng Sign bằng phiên bản cũ"]
    F --> G["Revoke / Disable theo chính sách"]
    G --> H["Lưu bằng chứng / hủy private key"]
~~~

| Giai đoạn | Cần làm | Rủi ro nếu làm sai |
|---|---|---|
| **Generation** | Chọn thuật toán và tham số phù hợp, sinh bằng CSPRNG/HSM | Private key yếu hoặc lộ ngay từ lúc sinh |
| **Provisioning** | Phân quyền Sign, công bố public key/chứng chỉ có xác thực | Verifier tin sai khóa hoặc caller không đúng được ký |
| **Storage** | Bảo vệ private key, kiểm kê export và backup | Lộ khóa từ file, image, log hoặc bản sao |
| **Usage** | Giới hạn loại thông điệp được ký, key usage và tần suất | Ký trái thẩm quyền hoặc lạm dụng API Sign |
| **Rotation** | Sinh khóa mới, cập nhật verifier và chuyển luồng Sign | Gián đoạn xác minh hoặc duy trì khóa yếu quá lâu |
| **Revocation** | Chặn Sign, cập nhật trust, điều tra khóa và chữ ký bị ảnh hưởng | Chữ ký giả tiếp tục được chấp nhận |
| **Retention/Destruction** | Bảo quản chứng cứ cần thiết; hủy private key đúng thời điểm | Mất bằng chứng lịch sử hoặc còn bản sao bí mật không kiểm soát |

**Cryptoperiod** là khoảng thời gian được phép sử dụng khóa cho mục đích xác định. Cần phân biệt **khoảng dùng private key để tạo chữ ký mới** với **khoảng tiếp tục dùng public key để kiểm tra chữ ký lịch sử**. Hai khoảng không nhất thiết bằng nhau.

Đối với khóa ký, **hết hạn ký mới** không đồng nghĩa phải xóa ngay public verification key. Một chữ ký lịch sử có thể cần được xác minh nhiều năm sau đó, tùy chính sách lưu giữ, timestamp tin cậy và chứng cứ PKI.

## 12. Key rotation: đổi khóa mà vẫn xác minh được chữ ký cũ

Quy trình rotation định kỳ có thể thực hiện theo thứ tự sau:

1. Sinh **private/public signing key v2** mới và kiểm tra quyền sử dụng trong KMS/HSM.
2. Công bố **public key/chứng chỉ v2** qua kênh tin cậy để verifier sẵn sàng.
3. Chuyển luồng **Sign** từ v1 sang v2; gắn key version với hiện vật mới.
4. Theo dõi tỷ lệ Verify thành công ở mọi dịch vụ, vùng và bản triển khai.
5. Ngừng dùng v1 để ký mới, xác định điều kiện tiếp tục xác minh chữ ký lịch sử bằng v1.
6. Disable/revoke và hủy private key v1 theo chính sách, sau khi xử lý phụ thuộc và bằng chứng.

~~~text
Trước rotation:
  Sign v1 -> Signature(key=v1) -> Verify bằng public key v1

Trong giai đoạn chuyển:
  Publish public key v2
  Sign v2 -> Signature(key=v2) -> Verify bằng public key v2
  Các chữ ký v1 cũ -> kiểm tra theo policy về thời điểm và trust

Sau rotation:
  Không ký mới bằng v1; ký mới bằng v2.
  Public key v1 có thể tiếp tục được giữ để kiểm tra lịch sử.
~~~

**Đổi key ID/alias mà không đổi key material không phải rotation có ý nghĩa đối với việc khắc phục khóa bị lộ.** Phải xác minh vật liệu khóa hoặc phiên bản mật mã thực sự được tạo mới.

### 12.1. Rotation thông thường và thu hồi khẩn cấp

**Rotation có kế hoạch** có thể có thời gian giao thoa khi verifier chấp nhận public key cũ và mới theo điều kiện xác định.

**Khi private key bị lộ**, có thể phải **ngừng chấp nhận chữ ký mới dưới key cũ ngay**, dù việc chuyển đổi gây gián đoạn. Các verifier phải áp dụng thông tin thu hồi; một cache JWKS/trust store chưa cập nhật là lỗ hổng thực tế.

Các chữ ký lịch sử được xử lý theo chứng cứ về **thời điểm tạo chữ ký**, trạng thái khóa khi đó, yêu cầu PKI và nghiệp vụ. Không tự động khẳng định mọi chữ ký cũ đều giả, cũng không tự động chấp nhận mọi chữ ký cũ vì phép toán Verify còn đúng.

## 13. Key revocation: vì sao disable trong KMS là chưa đủ?

Giả sử private key v1 bị xuất khỏi KMS do cấu hình sai. Tổ chức đổi trạng thái v1 sang **DISABLED**.

- API Sign qua **KMS** sẽ từ chối nếu chính sách khóa có hiệu lực đúng.
- Người đã sao chép **private key dạng rõ** vẫn có thể tạo chữ ký ở nơi khác.
- Verifier dùng public key v1 có thể vẫn chấp nhận chữ ký mới nếu không biết rằng v1 đã bị thu hồi.
- Chữ ký và token được tạo trong giai đoạn sự cố cần điều tra; chỉ xóa private key ở KMS không xóa được chữ ký đã phát hành.

Quy trình ứng phó:

1. **Khoanh vùng** key ID/version, loại thuật toán, chủ thể, nơi tồn tại private key và thời điểm nghi lộ.
2. **Cô lập** danh tính hoặc hệ thống có quyền Sign bị lạm dụng; chặn thao tác trong KMS/HSM.
3. **Sinh và kích hoạt khóa mới**, cập nhật quyền tối thiểu và phát hành public key/chứng chỉ mới.
4. **Đánh dấu không còn tin** public key hoặc chứng chỉ cũ theo quy trình CA, trust store hoặc JWKS; xử lý cache và client ngoại tuyến.
5. **Điều tra hiện vật có chữ ký**, token đang lưu hành, yêu cầu ký bất thường và khả năng phát lại.
6. **Kiểm chứng thực tế** rằng các điểm xác minh đã từ chối chữ ký không hợp lệ theo chính sách, sau đó lên kế hoạch lưu giữ/hủy.
7. **Ghi bằng chứng sự cố**, các phê duyệt, hành động, thời điểm và hệ thống đã kiểm tra.

### 13.1. Hủy private signing key khác hủy khóa giải mã

Khi private signing key bị hủy, bên quản lý mất khả năng tạo chữ ký mới bằng khóa đó, nhưng việc xác minh chữ ký cũ vẫn có thể dùng **public key** và chứng cứ tin cậy.

Ngược lại, hủy **DEK** có thể khiến bản mã phụ thuộc vào nó mất khả năng giải mã vĩnh viễn. **KEK** trong envelope encryption lại có phụ thuộc tới nhiều DEK. Vì vậy không áp đặt cùng lịch hủy cho signing key, DEK và KEK.

## 14. Signing key trong JWT/JWS và hệ thống phân tán

Một hệ thống phát hành JWT bất đối xứng có thể dùng:

| JWS algorithm | Signing key | Verification key | Lưu ý |
|---|---|---|---|
| **ES256** | ECDSA P-256 private key | ECDSA P-256 public key | SHA-256; chữ ký raw r ∥ s dài 64 byte trước base64url |
| **EdDSA / Ed25519** | Ed25519 private key | Ed25519 public key | Theo quy tắc EdDSA của giao thức |
| **PS256** | RSA private key dùng RSA-PSS | RSA public key | SHA-256 và tham số PSS theo chuẩn |
| **HS256** | HMAC shared secret | Cũng shared secret | MAC đối xứng, khác signing key private/public |

Một JWT/JWS verifier phải:

- Chỉ chấp nhận **thuật toán allowlist** phù hợp issuer. Header alg do người gửi kiểm soát không được tự quyết định chính sách.
- Dùng **kid** để tra public key từ nguồn tin cậy đã gắn với issuer, không tải khóa từ URL không đáng tin.
- Kiểm tra chữ ký trên **đúng JWS signing input** với format chữ ký đúng chuẩn.
- Kiểm tra **issuer, audience, expiration, not-before, scope/claims** và điều kiện nghiệp vụ.
- Khi rotate/revoke, cập nhật JWKS, cache, phiên đăng nhập và cơ chế thu hồi token nếu cần.

**Tình huống:** Sign đã chuyển sang v2 nhưng một service vẫn cache public key v1. Kẻ giữ private key v1 bị lộ có thể tạo token giả mà service cũ vẫn kiểm tra chữ ký thành công. Vì thế hoàn thành rotation/revocation cần **xác nhận thực tế ở mọi verifier**, không chỉ cập nhật endpoint JWKS.

JWT được **ký không có nghĩa được mã hóa**. Payload của JWS có thể đọc được; tránh đặt dữ liệu bí mật trong token chỉ vì token có signature.

## 15. Signing key và envelope encryption: phân vai trong kiến trúc

~~~mermaid
flowchart TD
    P["Dữ liệu / manifest"] --> S["Sign: private signing key"]
    S --> SI["Signature"]
    P --> E["Encrypt: AES-GCM với DEK"]
    E --> CT["Ciphertext + nonce + tag"]
    K["KMS/HSM bảo vệ KEK"] --> W["Wrap DEK"]
    W --> ED["Encrypted DEK"]
    SI --> STORE["Kho dữ liệu / gói phân phối"]
    CT --> STORE
    ED --> STORE
~~~

| Thành phần | Mục đích |
|---|---|
| **Private signing key** | Ký manifest, phiếu giao dịch, bản phát hành hoặc thông điệp theo quyền |
| **Public verification key** | Kiểm tra chữ ký và danh tính của bên phát hành |
| **DEK** | Mã hóa nội dung bằng AES-GCM; cần quản lý nonce cho từng lần encrypt |
| **KEK** | Bảo vệ DEK trong envelope encryption; có thể rotate và rewrap |
| **HMAC key** | Xác thực thông điệp giữa các bên cùng giữ secret, không phải chữ ký số công khai |
| **SHA-256** | Tạo digest, thành phần của chữ ký/MAC/KDF; riêng digest không xác thực nguồn |

Trong hệ thống lưu tài liệu, một **manifest có chữ ký** có thể chứa hash của ciphertext hoặc file, phiên bản, chủ thể, purpose, thuật toán mã hóa, key reference và thời điểm phát hành. Ký đúng bytes của manifest giúp bảo vệ tính toàn vẹn và nguồn gốc của metadata, khi bên xác minh tin đúng public key và kiểm tra nội dung hợp lệ.

**Thay signing key không tự yêu cầu rewrap DEK hoặc re-encrypt dữ liệu.** Việc này chỉ cần nếu thiết kế của hệ thống ràng buộc dữ liệu hoặc manifest theo cách đòi hỏi chuyển đổi. Vòng đời signing key, DEK và KEK nên được quản lý độc lập và có liên kết metadata rõ ràng.

## 16. Audit và giám sát signing key

Một hệ thống an toàn phải trả lời được: **ai sử dụng signing key, dùng cho việc gì, vào lúc nào và dưới quyết định ủy quyền nào?**

| Thông tin cần ghi | Giá trị kiểm toán |
|---|---|
| **Workload principal / caller identity** | Truy vết dịch vụ thực hiện Sign |
| **Key ID/version, thuật toán, purpose** | Phân biệt khóa và phạm vi sử dụng |
| **Thời điểm, correlation ID, transaction ID** | Liên kết lời gọi KMS với nghiệp vụ |
| **Kết quả allow/deny và mã lỗi** | Phát hiện vượt quyền, lỗi vận hành |
| **Rotation, disable, revoke, policy change, delete** | Ghi dấu hành động quản trị và phê duyệt |
| **Tần suất và phân bố lời gọi Sign** | Phát hiện thao tác bất thường theo user, vùng, môi trường |

**Không log private key, nonce k của ECDSA, secret HMAC, access token còn hiệu lực hoặc payload nhạy cảm không cần thiết.** Nếu ghi hash thông điệp, cần đánh giá khả năng suy ra nội dung từ tập giá trị nhỏ và giới hạn quyền đọc log.

**KMS audit log không tự chứng minh một giao dịch được người có thẩm quyền phê duyệt.** Cần đối chiếu log ứng dụng, trạng thái phê duyệt và định danh người yêu cầu với event KMS.

Các tín hiệu cảnh báo bao gồm: số lượt Sign tăng đột biến, signing ngoài phạm vi giờ/vùng/tenant dự kiến, thay đổi policy bất thường, nhiều request bị từ chối hoặc verifier tiếp tục chấp nhận khóa đã thu hồi.

## 17. Những sai lầm thường gặp với signing key

| Sai lầm | Hậu quả | Cách phòng tránh |
|---|---|---|
| Copy private key sang service chỉ để verify | Mở rộng nơi có thể bị đánh cắp và giả mạo | Chỉ phân phối public key có xác thực |
| Hard-code private key trong Git hoặc image | Lộ qua source, build, CI, log và backup | Sử dụng KMS/HSM hoặc keystore được bảo vệ |
| Dùng một signing key cho quá nhiều purpose/tenant | Sự cố lan sang nhiều phạm vi | Tách key và quyền theo rủi ro |
| Ký mọi payload do client cung cấp | Hợp thức hóa nội dung trái thẩm quyền | Kiểm tra nghiệp vụ trước API Sign |
| Không xác thực public key/chứng chỉ | Có thể tin chữ ký của kẻ thay khóa | PKI, trust store, issuer policy |
| Nhầm ECDSA, HMAC và AES-GCM | Sai mục đích mật mã và quyền | Phân biệt Sign/Verify, MAC, Encrypt/Decrypt |
| Dùng nonce k ECDSA yếu | Có nguy cơ suy ra private signing key | Provider/HSM đã đánh giá, entropy an toàn |
| Sai định dạng DER/P1363/JWS | Không tương thích hoặc lỗi xác minh | Chọn đúng algorithm và encoding |
| Ký JSON không xác định bytes chuẩn | Hai hệ thống không xác minh được cùng dữ liệu | Canonicalization và schema rõ ràng |
| Chỉ kiểm tra Verify=true | Chấp nhận token hết hạn hoặc giao dịch không được phép | Trust, authorization, time, chống replay |
| Đổi key alias thay vì key material | Không khắc phục lộ khóa | Sinh và chuyển sang private key mới |
| Bỏ qua JWKS/trust cache khi revoke | Verifier vẫn tin khóa đã bị lộ | Kiểm tra lan truyền tới toàn bộ client |
| Xóa cả public key cũ sau rotation | Mất khả năng kiểm tra lịch sử | Lưu public key và bằng chứng tin cậy cần thiết |
| Không kiểm kê backup private key | Khóa tưởng đã hủy vẫn còn bản sao | Backup được bảo vệ và tiêu hủy có kiểm soát |
| Cho rằng HSM ngăn mọi hành vi giả mạo | Service có quyền Sign bị chiếm vẫn ký được | Least privilege, approval, rate limit, audit |

## 18. Tình huống thực hành: khóa ký chứng từ bị lạm dụng

Một tổ chức dùng **KMS signing key v7** ký hóa đơn điện tử. Mỗi hóa đơn có signature và key ID/version; khách hàng lưu public key/chứng chỉ để kiểm tra.

**Sự cố:** có dấu hiệu tài khoản dịch vụ được quyền gọi Sign bị chiếm đoạt. Chưa có bằng chứng rằng private key rời HSM.

Hướng xử lý:

1. **Cô lập danh tính bị ảnh hưởng**: thu hồi credential/phiên, tước quyền Sign và chặn đường gọi không an toàn.
2. **Kiểm kê tác động**: xem log KMS, ứng dụng, những hóa đơn ký trong giai đoạn nghi ngờ; phân biệt **lạm dụng quyền ký** với **lộ vật liệu private key**.
3. **Sinh key v8**, cấp quyền theo nguyên tắc tối thiểu và chuẩn bị trust metadata mới.
4. **Chuyển signing sang v8**; disable/revoke v7 theo quyết định sự cố.
5. **Cập nhật verifier** ở đối tác và client, xử lý cache public key/chứng chỉ và thông tin thu hồi.
6. **Điều tra hiện vật lịch sử** dựa trên bằng chứng thời gian, trạng thái phê duyệt và nhật ký đáng tin; xử lý chứng từ đáng ngờ.
7. **Khắc phục nguyên nhân** ở IAM, chính sách approval, workload credential, giới hạn số lượt và audit.

Các chữ ký do HSM tạo ra trong giai đoạn tài khoản bị chiếm quyền **có thể đúng toán học nhưng trái quyền nghiệp vụ**. Do đó, bảo vệ signing key phải bao gồm bảo vệ **quyết định ký**, không chỉ giữ kín byte của khóa.

## 19. Kiểm thử signing key ở mức hệ thống

| Tình huống kiểm thử | Kết quả mong đợi |
|---|---|
| Private key được phép Sign, public key đúng Verify | Thành công |
| Sửa một byte message đã ký | Verify thất bại |
| Public key không tương ứng | Verify thất bại |
| Curve/algorithm ngoài allowlist | Từ chối |
| Chữ ký bị cắt hoặc sai DER/P1363 | Từ chối |
| Chữ ký hợp lệ toán học nhưng chứng chỉ không đáng tin | Không chấp nhận theo policy |
| Principal không có quyền gọi KMS Sign | Bị từ chối và có log |
| Người dùng chưa phê duyệt giao dịch | Ứng dụng không được gọi Sign |
| Key version đã disable nhưng caller thử Sign | KMS từ chối |
| Verifier còn cache public key đã revoke | Phải phát hiện nguy cơ chấp nhận sai |
| JWT đúng signature nhưng sai issuer/audience/expiry | Từ chối |
| Gửi lại yêu cầu đã xử lý với signature hợp lệ | Tầng chống replay/nghiệp vụ từ chối |
| Chữ ký lịch sử cần xác minh sau rotation | Theo chính sách về thời gian và trust, không chỉ Verify |
| Hủy private key hết cryptoperiod | Chỉ khi xử lý xong phụ thuộc; lưu chứng cứ thích hợp |

Cần kiểm thử tại **mọi điểm xác minh quan trọng**, bao gồm đa vùng, restart, failover và cache. Không đánh dấu revocation hoàn tất chỉ vì bảng metadata hiển thị REVOKED tại một nơi.

## 20. Câu hỏi tự kiểm tra

**Câu 1. Trong chữ ký số bất đối xứng, signing key là public key hay private key?**

**Trả lời:** Là **private key** dùng ký. Public key tương ứng dùng kiểm tra chữ ký.

**Câu 2. Tại sao không copy private key sang một service chỉ cần Verify?**

**Trả lời:** Verifier chỉ cần public key đáng tin. Có private key đồng nghĩa có khả năng tạo chữ ký, làm tăng nguy cơ giả mạo khi service bị xâm phạm.

**Câu 3. Chữ ký số có bảo vệ bí mật của payload không?**

**Trả lời:** Không. Cần cơ chế mã hóa riêng nếu muốn giữ bí mật nội dung.

**Câu 4. Tại sao nonce k của ECDSA đặc biệt quan trọng?**

**Trả lời:** Lộ hoặc tái sử dụng k sai cách có thể khiến private key bị suy ra từ chữ ký.

**Câu 5. Verify=true có đủ để chấp nhận hóa đơn/JWT không?**

**Trả lời:** Không. Cần kiểm tra trust, danh tính, thời hạn, quyền, key usage, ngữ cảnh và chống replay.

**Câu 6. Vì sao nên công bố public key mới trước khi chuyển signing sang khóa mới?**

**Trả lời:** Để verifier sẵn sàng xác minh chữ ký từ private key mới và giảm gián đoạn.

**Câu 7. Disable private key trong KMS có ngăn người đã sao chép khóa ký ở nơi khác không?**

**Trả lời:** Không. Cần thu hồi niềm tin của verifier đối với khóa bị lộ và xử lý sự cố.

**Câu 8. Có cần xóa public key cũ ngay sau rotation không?**

**Trả lời:** Không nhất thiết. Nó có thể cần để xác minh chữ ký lịch sử, theo chính sách và chứng cứ thời gian.

**Câu 9. HMAC-SHA-256 có giống SHA256withECDSA không?**

**Trả lời:** Không. HMAC dùng shared secret đối xứng; ECDSA ký bằng private key và xác minh bằng public key.

**Câu 10. Private key non-exportable trong HSM có thể bị lạm dụng không?**

**Trả lời:** Có. Principal có quyền Sign nhưng bị chiếm quyền vẫn có thể yêu cầu HSM ký trái phép.

**Câu 11. Signing key, DEK và KEK có nên dùng chung một chính sách hủy không?**

**Trả lời:** Không. Mỗi loại có mục đích và phụ thuộc khác nhau; hủy DEK có thể làm mất dữ liệu mã hóa, còn public key của signing key có thể tiếp tục cần cho lịch sử.

**Câu 12. Header kid của JWT có chứng minh public key đáng tin không?**

**Trả lời:** Không. kid là định danh tham chiếu; key phải được lấy từ nguồn đáng tin và gắn đúng issuer/algorithm/policy.

## 21. Checklist thiết kế signing key

Trước khi đưa một hệ thống chữ ký số vào vận hành, nên trả lời được:

- **Purpose:** khóa được dùng cho hóa đơn, token, phiếu giao dịch, phần mềm hay manifest? Có tách mục đích và môi trường không?
- **Algorithm:** ECDSA, Ed25519 hay RSA-PSS? Curve/hash, signature encoding và provider có phù hợp giao thức không?
- **Generation & storage:** private key được sinh bằng nguồn ngẫu nhiên an toàn và lưu ở KMS/HSM/keystore bảo vệ? Có bản sao export/backup cần quản lý không?
- **Access:** ai được Sign, ai được Verify, ai được thay policy hoặc rotate/revoke/delete? Có tách quyền nghiệp vụ không?
- **Message binding:** byte nào được ký? Có canonicalization, domain, version, tenant, timestamp và transaction ID cần thiết không?
- **Verification:** public key có nguồn gốc tin cậy? Verifier kiểm tra chứng chỉ, thời hạn, trạng thái thu hồi, quyền và replay chưa?
- **Lifecycle:** có quy trình chuyển key version, cập nhật JWKS/trust store, kiểm tra chữ ký lịch sử và thu hồi khẩn cấp không?
- **Audit:** ghi đủ danh tính, key ID/version, quyết định nghiệp vụ, thời điểm và kết quả mà không lộ private key hoặc thông tin nhạy cảm?
- **Incident response:** nếu private key bị lộ hoặc API Sign bị lạm dụng, có thể cô lập, chuyển khóa, xử lý cache và xác định hiện vật bị ảnh hưởng không?

**Ghi nhớ:** **Signing key** trong chữ ký số bất đối xứng là **private key dùng tạo chữ ký**; **public verification key** dùng kiểm tra. Bảo mật signing key phải đi xa hơn việc bảo vệ vật liệu khóa: cần kiểm soát **ai được ký, byte/ngữ cảnh được ký, nguồn tin cậy của public key, rotation, revocation, chứng cứ lịch sử và audit**. Các yêu cầu này gắn chữ ký số với KMS/HSM, quản lý khóa đối xứng/bất đối xứng, envelope encryption và toàn bộ vòng đời khóa an toàn.
