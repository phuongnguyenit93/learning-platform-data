# Developer responsibility – Trách nhiệm của lập trình viên trong quản lý khóa mật mã

**Developer responsibility (trách nhiệm của lập trình viên)** trong quản lý khóa mật mã là tập hợp những quyết định và hành động mà người phát triển phần mềm phải thực hiện để ứng dụng **tạo, nhận, sử dụng, bảo vệ, thay thế và ngừng sử dụng khóa một cách an toàn**. Developer thường không trực tiếp vận hành HSM, cấp quyền root trên KMS hoặc quyết định tiêu hủy khóa của toàn tổ chức, nhưng chính **mã ứng dụng, cấu hình tích hợp và luồng nghiệp vụ** quyết định khóa có bị dùng sai, lộ qua log, tái sử dụng nonce hay truy cập nhầm dữ liệu giữa các tenant hay không.

Bài thuộc chương **Vai trò và trách nhiệm** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**. Trách nhiệm của developer phải gắn với vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**, đồng thời kết nối mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

> **Nguyên tắc:** **KMS/HSM bảo vệ và thực thi một phần chính sách đối với khóa; developer chịu trách nhiệm tích hợp đúng và bảo vệ ngữ cảnh sử dụng.** Có KMS không làm ứng dụng tự động an toàn nếu ứng dụng cấp quyền sai tenant, chấp nhận public key giả, dùng AES-GCM sai nonce hoặc ghi DEK ra log.

## 1. Ranh giới trách nhiệm: developer làm gì, phối hợp với ai?

Quản lý khóa là **trách nhiệm chia sẻ có phân định**. Nếu mọi đội đều cho rằng đội khác đã lo phần khóa, một lỗ hổng có thể xuất hiện ở vùng giao nhau giữa ứng dụng và hạ tầng.

| Vai trò | Trách nhiệm điển hình | Developer cần phối hợp ở đâu? |
| --- | --- | --- |
| **Developer / application owner** | Xác định dữ liệu cần bảo vệ; chọn cách dùng thư viện/API; gắn khóa với tenant, purpose và object; xử lý lỗi; không log secret; triển khai migration và kiểm thử. | Cung cấp yêu cầu mật mã, thay đổi ứng dụng, kiểm thử khả năng đọc dữ liệu cũ. |
| **Security / cryptography architect** | Định nghĩa thuật toán được phép, key length, cryptoperiod, threat model, ngoại lệ và tiêu chí đánh giá. | Review thiết kế, chuẩn hóa giao thức, chấp nhận rủi ro. |
| **KMS/HSM / platform team** | Vận hành dịch vụ quản lý khóa, availability, IAM, backup/recovery, giám sát, key rotation capability. | Cấp key references, quyền API, chính sách về key usage và thay khóa. |
| **IAM / identity team** | Danh tính workload, token/chứng chỉ, cấp quyền và vòng đời principal. | Dùng workload identity đúng môi trường; không nhúng credential cố định. |
| **SRE / operations** | Triển khai cấu hình, metrics, runbook, incident response, DR và rollback. | Phối hợp canary, alert, timeout, caching, kiểm thử phục hồi. |
| **Data / business owner** | Phân loại dữ liệu, retention, phạm vi tenant và quyền nghiệp vụ. | Xác nhận ai được giải mã, lưu giữ bao lâu, có cần xóa bằng mật mã không. |
| **Auditor / compliance** | Kiểm tra bằng chứng và việc thực thi chính sách. | Cung cấp log metadata không nhạy cảm, kiểm tra truy xuất và thay đổi. |

**Developer không tự quyết định được** việc một KEK cần hủy ngay, một root key được xuất hay một chứng chỉ có đủ giá trị pháp lý hay không. Nhưng developer phải biết **ai là owner, cách xin phê duyệt, và ứng dụng cần thay đổi gì** khi người có thẩm quyền đưa ra quyết định.

### 1.1. Phân biệt responsibility, accountability và ownership

- **Responsibility – người thực hiện:** viết code, cấu hình, kiểm thử và vận hành một bước cụ thể.
- **Accountability – người chịu trách nhiệm cuối:** phê duyệt hoặc chịu trách nhiệm kết quả theo cơ cấu tổ chức.
- **Ownership – chủ quản tài sản/khóa:** xác định mục đích, phạm vi, retention và đường liên hệ khi có sự cố.

Một task có thể cần nhiều bên **tham gia**, nhưng nên có **một đầu mối có thẩm quyền cho quyết định quan trọng**, chẳng hạn cho phép production signing key chuyển sang phiên bản mới hoặc cho hủy KEK tiền nhiệm.

## 2. Developer bắt đầu từ yêu cầu bảo mật và threat model

Trước khi thêm `Cipher.getInstance(...)` hay gọi KMS, developer phải xác định **bảo vệ cái gì và chống đối tượng tấn công nào**.

Một bảng câu hỏi tối thiểu:

1. **Dữ liệu nào cần bí mật?** Mật khẩu, PII, thông tin thanh toán, API secret, dữ liệu tài chính hay bản ghi khác?
2. **Tính chất nào cần?** Confidentiality, integrity, authentication, chống replay, non-repudiation hay availability?
3. **Ai được phép dùng?** Workload nào, tenant nào, người dùng nào; quyền **Decrypt/Sign/Unwrap** có tách biệt không?
4. **Khóa nằm ở đâu?** KMS/HSM non-exportable, secret manager, bộ nhớ tạm hay cấu hình ứng dụng?
5. **Có bao nhiêu bản sao?** Database, cache, queue, backup, logs, tracing, CI artifacts?
6. **Làm sao luân chuyển khóa?** Hỗ trợ key ID, version, predecessor, đọc dữ liệu cũ và migrate không?
7. **Mất hoặc lộ khóa gây hậu quả gì?** Mất khả năng đọc dữ liệu, giả mạo chữ ký, đọc chéo tenant?
8. **Cần bảo vệ trong bao lâu?** Dữ liệu vài phút, vài năm hay chữ ký phải được kiểm tra dài hạn?

Các câu trả lời quyết định **mô hình key management**, không phải developer chọn khóa theo ví dụ trên mạng rồi cố gắn vào mọi nơi.

### 2.1. Phân biệt mã hóa, chữ ký số, MAC và password hashing

| Bài toán | Primitive/giao thức phù hợp | Lỗi phổ biến developer cần tránh |
| --- | --- | --- |
| Bảo mật và toàn vẹn dữ liệu lưu trữ | AEAD như **AES-GCM** cùng DEK/KEK và nonce phù hợp. | Dùng AES/ECB, reuse nonce GCM, không xác thực tag, dùng khóa cố định chung. |
| Xác thực nguồn một sự kiện/phát hành | **Digital signature** Ed25519, ECDSA hoặc RSA-PSS theo giao thức. | Bỏ qua kiểm tra nguồn public key, xác minh chữ ký nhưng không kiểm tra quyền nghiệp vụ. |
| Xác thực thông điệp giữa các bên cùng biết secret | **HMAC/KMAC** với key usage riêng. | Dùng hash thuần thay MAC hoặc dùng chung secret với mục đích khác. |
| Lưu mật khẩu người dùng | **Argon2id/scrypt/bcrypt/PBKDF2** với salt và work factor thích hợp. | Dùng SHA-256(password) trực tiếp; coi password hash là khóa AES. |
| Thiết lập khóa phiên liên dịch vụ | **TLS 1.3/mTLS** hoặc giao thức AKE được đánh giá. | Tự ghép X25519 + AES-GCM mà thiếu xác thực đối tác. |
| Dẫn xuất khóa theo mục đích từ vật liệu phù hợp | **HKDF/KDF chuẩn** với domain separation. | Tự nối chuỗi secret hoặc dùng HKDF trực tiếp như password-hashing chống đoán ngoại tuyến. |

**Không tự xây crypto primitive.** Một developer nên dùng thư viện/provider đã được tổ chức cho phép và kiểm tra **hợp đồng API, xử lý lỗi, định dạng dữ liệu, key usage, khả năng tương thích**.

## 3. Trách nhiệm của developer theo từng giai đoạn vòng đời khóa

| Giai đoạn | Developer phải thực hiện | Bên cần phối hợp | Rủi ro nếu bỏ qua |
| --- | --- | --- | --- |
| **Tạo (generate)** | Yêu cầu API sinh khóa chuẩn; dùng **CSPRNG** phù hợp; xác định purpose, algorithm, key size và scope. | Security, KMS/HSM team. | Khóa yếu, seed đoán được hoặc dùng khóa sai mục đích. |
| **Cấp phát/đăng ký** | Dùng **key reference** từ nguồn tin cậy; gắn owner/tenant/environment; không hard-code key material. | IAM, platform, key registry. | Ứng dụng lấy nhầm khóa hoặc đăng ký public key giả. |
| **Lưu trữ** | Không lưu private/secret key trong source, image, plaintext config, log; hạn chế thời gian giữ DEK trong RAM. | Platform, secret manager, KMS. | Lộ secret qua Git, dump, backup hoặc hệ thống quan sát. |
| **Sử dụng** | Chọn đúng API, nonce, AAD, key usage; kiểm tra quyền trước khi Decrypt/Sign; xử lý lỗi fail closed. | Security, data owner. | Sửa dữ liệu không bị phát hiện; leo thang quyền; lộ chéo tenant. |
| **Xoay vòng** | Có key ID/version, tương thích đọc bản cũ, migration/rewrap/re-encrypt, canary và rollback có kiểm soát. | KMS, SRE, data owner. | Dữ liệu không giải mã được; chữ ký mới bị consumer từ chối. |
| **Thu hồi/vô hiệu hóa** | Ngừng gọi khóa bị lộ; invalidation cache/session; cập nhật trust và key mapping; xử lý lỗi rõ ràng. | Security response, IAM, platform. | Khóa compromise vẫn được sử dụng hoặc tin cậy. |
| **Hủy** | Kiểm kê ciphertext/backups và các dependency do ứng dụng quản lý; xác minh migration trước khi xóa. | Owner, security, KMS, operations. | Mất dữ liệu vĩnh viễn hoặc tuyên bố hủy khi còn bản sao. |

**Developer không được tự hủy mọi key cũ ngay khi deployment mới thành công.** Ví dụ một DEK phiên bản cũ có thể vẫn cần để giải mã archive; còn một private key ký đã retire có thể không cần giữ để xác minh chữ ký cũ, nhưng **public key và bằng chứng trust lịch sử** vẫn phải được bảo quản theo chính sách.

## 4. Thiết kế đúng ranh giới khóa: DEK, KEK và key reference

Trong **envelope encryption**, developer thường không cần nhìn thấy **KEK (Key Encryption Key)**. KMS/HSM giữ hoặc sử dụng KEK, còn ứng dụng sử dụng một **DEK (Data Encryption Key)** để mã hóa dữ liệu và lưu **wrapped DEK**.

~~~mermaid
flowchart TD
    REQ["Ứng dụng đã xác thực workload + kiểm tra quyền tenant"] --> KMS["KMS GenerateDataKey theo KEK ID/context"]
    KMS --> DEK["DEK rõ tạm thời trong bộ nhớ ứng dụng"]
    KMS --> WRAPPED["Wrapped DEK + key reference"]
    REQ --> DATA["Plaintext được phép xử lý"]
    DEK --> GCM["AES-GCM: nonce + AAD + dữ liệu"]
    DATA --> GCM
    GCM --> STORE["Ciphertext + tag + nonce + wrapped DEK + key ID"]
    WRAPPED --> STORE
    STORE --> READ["Đọc bản ghi đã cấp quyền"]
    READ --> UNWRAP["KMS Decrypt/Unwrap với context đúng"]
    UNWRAP --> GCM_READ["AES-GCM verify tag và giải mã"]
~~~

**Điểm phân quyền quan trọng:** Developer phải kiểm tra **người dùng/workload có quyền trên đối tượng dữ liệu hay không trước khi gọi KMS**, không chỉ xem lệnh KMS Decrypt trả về thành công.

### 4.1. Những dữ liệu cần đi cùng ciphertext

- **Thuật toán và phiên bản định dạng**, ví dụ envelope-v1/AES-GCM.
- **Nonce/IV** và authentication tag theo format AEAD.
- **Wrapped DEK** cùng **KEK key reference**, khi API/provider yêu cầu.
- **Key material version** hoặc cách truy đúng thế hệ vật liệu khóa mà provider hỗ trợ.
- **Encryption context / AAD** ràng buộc **tenant, object, purpose** và những trường quan trọng.
- **Metadata có tính toàn vẹn**, tránh attacker thay tenant/key references mà verifier không kiểm tra.

Một số KMS tự nhúng key reference hoặc vật liệu version trong encrypted blob; developer phải tuân theo cách dùng của nhà cung cấp, **không tự suy rằng mọi KMS decrypt bằng alias hoặc version ID giống nhau**.

### 4.2. Phân biệt kiểm soát ở KMS và kiểm soát nghiệp vụ

| Lớp | Câu hỏi kiểm tra | Ví dụ |
| --- | --- | --- |
| **KMS/IAM** | Workload nào có thể gọi GenerateDataKey, Encrypt, Decrypt, Sign, Unwrap trên key ID? | billing-prod có Decrypt KEK billing; analytics-dev không có. |
| **Encryption context/AAD** | Dữ liệu được gắn với tenant, object và purpose nào? | tenant=A, object=invoice-123. |
| **Application authorization** | Caller hiện tại có quyền đọc invoice-123 của tenant A không? | User X chỉ có quyền với tenant A. |
| **Database/object ACL** | Có thể lấy ciphertext của đối tượng nào? | Query đã lọc tenant và quyền sở hữu. |
| **Audit** | Ai được cho phép/từ chối, key ID nào được dùng, kết quả ra sao? | Không log plaintext hoặc DEK. |

**KMS chỉ biết workload được cấp quyền và ngữ cảnh được truyền cho nó theo policy**. Nếu developer tùy ý đặt `tenantId` do attacker cung cấp, KMS có thể thực hiện phép toán phù hợp với **tham số sai**. Cần liên kết ngữ cảnh đó với **định danh đã xác thực và đối tượng thực trong database**.

## 5. Quản lý khóa an toàn trong mã nguồn và pipeline

### 5.1. Không lưu key material trong code hoặc cấu hình triển khai

Tránh các mẫu:

~~~java
// SAI: khóa cố định trong source code và chia sẻ cho mọi deployment.
byte[] aesKey = "1234567890abcdef1234567890abcdef".getBytes();

// SAI: random không dành cho mật mã.
java.util.Random weakRandom = new java.util.Random(12345);

// SAI: secret xuất ra log.
logger.info("data-key = {}", secretKeyBytes);
~~~

Trong sản xuất:

- Chỉ giữ **KMS key ID/ARN/reference, secret reference và metadata không phải secret** trong cấu hình được phép.
- Sử dụng **workload identity** ngắn hạn hoặc cơ chế xác thực được platform cấp thay vì access key lâu dài nhúng vào image.
- Không commit private key, keystore password hoặc secret vào Git, container layers, test fixture dùng chung, tài liệu và pull request.
- Nếu cần **secret manager**, lấy secret qua API đã phân quyền, giới hạn cache và không truyền secret sang công cụ tracing/log.
- Phân biệt **mật khẩu cấu hình**, **API token**, **khóa ký** và **khóa mã hóa**; không cùng một secret cho nhiều purpose.

**Biến môi trường không phải một kho bí mật tự thân.** Một số nền tảng dùng environment injection như đường phân phối bí mật được quản lý, nhưng secret vẫn có thể lộ qua process dump, cấu hình debug, lỗi in environment hoặc quyền quan sát container. Phải hiểu threat model của runtime.

### 5.2. Quyền và môi trường

Áp dụng **least privilege**:

- Dev, test và production **không dùng chung** KEK, private signing key hoặc dữ liệu thật nếu không có lý do và phê duyệt đặc biệt.
- Workload chỉ có quyền API cần thiết: một verifier thường chỉ cần public key/Verify, không cần Sign.
- Dịch vụ mã hóa dữ liệu không tự có quyền **DeleteKey**, **ScheduleKeyDeletion**, **ExportKey** hoặc thay chính sách root.
- Tách quyền **Sign/Decrypt/Unwrap** khỏi quyền **tạo/duyệt/hủy** key material khi thích hợp.
- Không cho user-input chọn tùy ý **key ID, algorithm, issuer, certificate URL** hay KMS endpoint.
- Phân vùng scope theo tenant và ứng dụng; giới hạn cross-account/cross-region phù hợp.

**Non-exportable private key** không có nghĩa bất khả lạm dụng: một workload bị chiếm quyền nhưng có **Sign** vẫn có thể ký dữ liệu giả. Developer phải giới hạn **điều kiện được gửi dữ liệu để ký** và đưa policy vào đúng điểm quyết định.

## 6. Cách dùng API mật mã mà developer phải chịu trách nhiệm

### 6.1. AES-GCM: nonce, AAD, tag và giới hạn khóa

**AES-GCM** vừa mã hóa vừa xác thực ciphertext. Developer phải:

1. Dùng API chuẩn như `AES/GCM/NoPadding`, không tự triển khai GCM.
2. **Không tái dùng cùng nonce dưới cùng key**. Với nonce ngẫu nhiên 96 bit, quản lý số lần mã hóa theo key và collision budget; với quy mô lớn cần chiến lược nonce/counter bền vững.
3. Xác định **AAD** nhất quán ở cả lúc encrypt/decrypt, ví dụ domain, tenant và object ID từ dữ liệu đã xác thực.
4. **Không bỏ qua authentication tag** hoặc coi plaintext đã được giải mã là đáng tin trước khi kiểm tra tag.
5. Dùng **key usage/lifetime** phù hợp; rotation không thay thế việc kiểm soát reuse key + nonce.
6. Chỉ triển khai dữ liệu sau khi giải mã/tag hợp lệ và kiểm tra quyền nghiệp vụ.

**Nonce không cần bí mật nhưng cần tuân thủ quy tắc duy nhất theo key.** Một nonce tốt không chữa được việc ứng dụng tái sử dụng DEK/KEK sai purpose.

### 6.2. Chữ ký số: kiểm tra public key trước phép Verify

Với **Ed25519/ECDSA/RSA-PSS**, developer có trách nhiệm:

- Ký **đúng bytes** của thông điệp và các trường mang ý nghĩa nghiệp vụ; dùng canonical format hoặc một định dạng có quy tắc rõ.
- Kiểm tra **issuer, audience, purpose, key usage và key ID** qua registry/JWKS/PKI đã được cấu hình tin cậy.
- Không tự chấp nhận public key do request đưa vào mà thiếu cơ chế xác thực danh tính.
- Không suy “chữ ký hợp lệ” thành “người ký được phép làm mọi hành động”; vẫn phải kiểm tra authorization và chống replay.
- Khi rotate, cho verifier biết **public key mới trước**, giữ cửa sổ tin khóa cũ theo policy và xử lý khóa bị lộ riêng.
- Không ghi **private key/seed ký** trong audit.

Với release artifacts, cần **xác minh digest và chữ ký/provenance trước khi triển khai**; một chữ ký đúng bằng khóa tin cậy không tự bảo đảm build pipeline chưa bị chiếm quyền.

### 6.3. Password KDF và key derivation

- **Password hashing:** chọn Argon2id hoặc giải pháp đã phê duyệt khác; lưu salt, thuật toán và work factor để nâng cấp.
- **HKDF:** dùng với vật liệu khóa phù hợp, chẳng hạn shared secret X25519/ECDH, để tạo các key theo purpose; **không thay password hashing chậm** cho mật khẩu yếu.
- **Salt:** thường công khai và được tạo phù hợp; **pepper** là secret cần quản lý riêng nếu thiết kế sử dụng.
- **Domain separation:** không dùng cùng key/đầu ra cho HMAC, AES và signing bằng các thao tác tùy tiện.
- **CSPRNG:** dùng `SecureRandom` hoặc API sinh khóa từ provider/KMS; không dùng `Math.random()`, `Random` hay timestamp làm seed.

## 7. Ví dụ Java 17: developer tích hợp envelope encryption đúng ranh giới

Ví dụ sau minh họa **code ứng dụng** xử lý dữ liệu hóa đơn bằng AES-GCM với **DEK do KMS cấp**. Một giao diện nhỏ `KmsKeyClient` mô tả hai thao tác:

- **generateDataKey:** KMS tạo DEK mới, trả một bản **DEK rõ tạm thời** cho ứng dụng cùng **wrapped DEK**.
- **decryptDataKey:** KMS kiểm tra quyền và context, giải bọc DEK phục vụ giải mã một bản ghi đã được phép truy cập.

Adapter KMS thực tế **không có trong ví dụ**; developer phải dùng SDK của nhà cung cấp và không tự tạo cơ chế wrap giả. Mỗi lần **encrypt** ở ví dụ dùng một **DEK mới**, giảm nguy cơ reuse nonce theo cùng DEK, nhưng vẫn cần bảo vệ nonce và giới hạn sử dụng theo chính sách.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Map;
import java.util.Objects;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class DeveloperKeyHandlingExample {
    private static final SecureRandom RNG = new SecureRandom();
    private static final String APPROVED_KEK = "billing-prod-kek";
    private static final int AES_KEY_BYTES = 32;
    private static final int GCM_NONCE_BYTES = 12;
    private static final int GCM_TAG_BITS = 128;

    // Trong production: adapter xác thực qua workload identity,
    // IAM policy giới hạn keyId và encryption context.
    public interface KmsKeyClient {
        DataKey generateDataKey(
                String keyId, Map<String, String> context) throws Exception;

        byte[] decryptDataKey(
                String keyId, byte[] wrappedDek,
                Map<String, String> context) throws Exception;
    }

    public record DataKey(byte[] plaintextDek, byte[] wrappedDek) {}

    public record EncryptedInvoice(
            String tenantId, String invoiceId, String kekId,
            byte[] wrappedDek, byte[] nonce, byte[] ciphertextWithTag) {}

    private static Map<String, String> context(
            String tenantId, String invoiceId) {
        // Caller phải kiểm tra quyền tenant/invoice trước đó!
        return Map.of("purpose", "billing-invoice-v1",
                "tenant", tenantId, "invoice", invoiceId);
    }

    private static byte[] aad(String tenantId, String invoiceId)
            throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        for (String field : new String[] {
                "billing-invoice-v1", tenantId, invoiceId }) {
            byte[] utf8 = field.getBytes(StandardCharsets.UTF_8);
            out.writeInt(utf8.length);
            out.write(utf8);
        }
        out.flush();
        return bytes.toByteArray();
    }

    public static EncryptedInvoice encrypt(
            KmsKeyClient kms, String tenantId, String invoiceId,
            byte[] plaintext) throws Exception {
        Objects.requireNonNull(kms);
        Objects.requireNonNull(plaintext);
        if (tenantId == null || tenantId.isBlank()
                || invoiceId == null || invoiceId.isBlank()) {
            throw new IllegalArgumentException("Invalid invoice identity");
        }

        // Kiểm tra authorization nghiệp vụ trước khi gọi hàm này.
        DataKey dataKey = kms.generateDataKey(
                APPROVED_KEK, context(tenantId, invoiceId));
        if (dataKey == null || dataKey.plaintextDek() == null
                || dataKey.plaintextDek().length != AES_KEY_BYTES
                || dataKey.wrappedDek() == null
                || dataKey.wrappedDek().length == 0) {
            throw new SecurityException("Invalid data key from KMS");
        }

        byte[] plaintextDek = dataKey.plaintextDek();
        try {
            byte[] nonce = new byte[GCM_NONCE_BYTES];
            RNG.nextBytes(nonce);

            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(plaintextDek, "AES"),
                    new GCMParameterSpec(GCM_TAG_BITS, nonce));
            cipher.updateAAD(aad(tenantId, invoiceId));
            byte[] encrypted = cipher.doFinal(plaintext);

            // Chỉ persist khi encrypt/doFinal hoàn tất thành công.
            // Wrapped DEK và context phải được lưu đúng bản ghi.
            return new EncryptedInvoice(
                    tenantId, invoiceId, APPROVED_KEK,
                    dataKey.wrappedDek().clone(), nonce, encrypted);
        } finally {
            Arrays.fill(plaintextDek, (byte) 0);
        }
    }

    public static byte[] decrypt(
            KmsKeyClient kms, String authenticatedTenant,
            String expectedInvoiceId, EncryptedInvoice record)
            throws Exception {
        Objects.requireNonNull(kms);
        Objects.requireNonNull(record);

        // Không để bản ghi DB tự đổi tenant/keyId tùy ý.
        // Application authorization phải xác minh user/workload
        // được đọc chính invoice này trước khi gọi decrypt.
        if (!Objects.equals(authenticatedTenant, record.tenantId())
                || !Objects.equals(expectedInvoiceId, record.invoiceId())
                || !APPROVED_KEK.equals(record.kekId())
                || record.wrappedDek() == null
                || record.wrappedDek().length == 0
                || record.nonce() == null
                || record.nonce().length != GCM_NONCE_BYTES
                || record.ciphertextWithTag() == null
                || record.ciphertextWithTag().length < 16) {
            throw new SecurityException("Untrusted encrypted record");
        }

        byte[] plaintextDek = kms.decryptDataKey(
                APPROVED_KEK, record.wrappedDek(),
                context(authenticatedTenant, expectedInvoiceId));
        if (plaintextDek == null || plaintextDek.length != AES_KEY_BYTES) {
            throw new SecurityException("KMS returned an invalid data key");
        }
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE,
                    new SecretKeySpec(plaintextDek, "AES"),
                    new GCMParameterSpec(GCM_TAG_BITS, record.nonce()));
            cipher.updateAAD(aad(authenticatedTenant, expectedInvoiceId));

            // doFinal kiểm tra authentication tag; lỗi phải fail closed.
            return cipher.doFinal(record.ciphertextWithTag());
        } finally {
            Arrays.fill(plaintextDek, (byte) 0);
        }
    }

    private DeveloperKeyHandlingExample() {}
}
~~~

### 7.1. Phần nào là trách nhiệm của developer trong ví dụ?

1. **Chọn API chuẩn:** JCA `AES/GCM/NoPadding`, nonce 96 bit, tag 128 bit, không tự viết thuật toán mã hóa.
2. **Phân biệt KEK và DEK:** ứng dụng nhận DEK rõ trong RAM tạm thời; **không xuất KEK** khỏi KMS.
3. **Dùng key reference có cấu hình:** `APPROVED_KEK` là mã định danh, **không phải bytes khóa**. Production nên lấy reference này từ cấu hình được bảo vệ và gắn với môi trường/tenant.
4. **Ràng buộc ngữ cảnh:** cùng tenant/invoice/purpose được đưa vào KMS context và AEAD AAD; encoding AAD dùng **prefix độ dài** để tránh ghép chuỗi mơ hồ.
5. **Không tin record chưa kiểm soát:** mã từ chối key ID không được phép, tenant/object mismatch và trường dữ liệu sai định dạng.
6. **Bắt buộc authorization trước hàm:** quyền đọc hóa đơn phải được kiểm tra bằng nguồn danh tính tin cậy; hàm ví dụ **không tự thực hiện toàn bộ phân quyền**.
7. **Xử lý fail closed:** khi KMS hoặc authentication tag lỗi, code trả lỗi; không bỏ qua lỗi hay trả dữ liệu chưa xác thực.
8. **Giảm thời gian sống của DEK:** xóa mảng DEK tạm thời trong `finally`. Việc này **không bảo đảm zeroization toàn bộ bản sao trong JVM/provider**, nhưng tránh giữ tham chiếu không cần thiết.

### 7.2. Những điểm còn thiếu trước khi dùng production

Ví dụ chỉ là **mảnh ghép ứng dụng**, chưa phải hệ thống hoàn chỉnh. Cần bổ sung:

- **KMS adapter thật:** xác thực workload, timeout, retry có giới hạn, kiểm tra response/key ID, IAM/encryption context policies và audit provider.
- **Schema và version:** định dạng ciphertext, algorithm ID, key version/predecessor, migration giữa KEK và DEK; ví dụ ghim một KEK để dạy trust boundary.
- **Validation lớn hơn:** giới hạn độ dài input, wrapped key, số bản ghi đồng thời, rate limit để giảm DoS và chi phí KMS.
- **Truy vấn dữ liệu có quyền:** không dùng `invoiceId` do caller nhập mà bỏ qua kiểm tra rằng nó thuộc tenant đã được xác thực.
- **Mã hóa dữ liệu nhiều lần:** ví dụ sinh DEK mới cho từng record; hệ thống khác cần policy về nonce uniqueness, DEK caching và giới hạn số lượt mã hóa theo key.
- **Giảm bản sao secret:** các record/mảng có thể bị mutable; production nên dùng dữ liệu immutable/copy phòng thủ ở các ranh giới API.
- **Ghi dữ liệu nguyên tử:** không ghi ciphertext mà bỏ quên wrapped DEK, nonce hoặc metadata.
- **Xử lý sự cố và DR:** restore test, backup dependencies, quyền Decrypt theo version cũ, giám sát key usage.
- **Kiểm thử tích hợp:** adapter giả lập trong test không thay thế kiểm tra IAM/policy và dữ liệu thật trên môi trường được phép.

**Lưu ý đặc biệt:** Với KMS hỗ trợ **encryption context**, cách kết hợp context vào thao tác tạo/giải bọc DEK phụ thuộc API nhà cung cấp; không mặc định mọi KMS hỗ trợ map key-value hay cùng cách xác thực context.

## 8. Developer phải thiết kế rotation từ đầu

Một trong những trách nhiệm quan trọng nhất là **không khiến hệ thống phụ thuộc vào một key ID không thể thay đổi**.

### 8.1. Rotation của KEK và DEK

| Tình huống | Developer cần hỗ trợ | Điều không được làm |
| --- | --- | --- |
| **Đổi KEK** | Dữ liệu lưu wrapped DEK và tham chiếu đủ để unwrap bằng khóa/phiên bản còn hợp lệ; có thể rewrap. | Đổi alias rồi xóa ngay KEK cũ khi backup còn phụ thuộc. |
| **Đổi DEK** | Tạo vật liệu DEK mới, migrate/re-encrypt ciphertext hoặc dùng policy đa phiên bản. | Chỉ sửa trường version trong DB mà vẫn giữ ciphertext cũ rồi coi đã thay khóa. |
| **Đổi signing key** | Công bố public key mới cho consumer trước khi ký mới; hỗ trợ verify bản cũ có hạn. | Dùng `kid` do request tự khai để tin bất kỳ public key nào. |
| **Đổi TLS identity** | Cập nhật chứng chỉ, trust chain, hostname/service identity và client compatibility. | Tắt certificate verification để “tránh lỗi” trong rollout. |
| **Thu hồi khóa bị lộ** | Ngừng thao tác mới, đánh giá dữ liệu/chữ ký/phiên và cập nhật trust, cache. | Chỉ rotate alias mà không xử lý khóa compromise hoặc dữ liệu cũ. |

### 8.2. Trình tự rollout mẫu

~~~mermaid
flowchart TD
    P["Security/owner duyệt rotation"] --> CREATE["Platform/KMS tạo key version mới"]
    CREATE --> REGISTER["Registry ghi owner, purpose, version, predecessor"]
    REGISTER --> READY["Dev kiểm tra read compatibility, consumer readiness"]
    READY --> SWITCH["Bật single-write / signing bằng version mới"]
    SWITCH --> MIGRATE["Rewrap/re-encrypt hoặc duy trì read cũ theo policy"]
    MIGRATE --> VERIFY["Đối soát ciphertext, backups, trust và audit"]
    VERIFY --> RETIRE["Retire quyền tạo mới của version cũ"]
    RETIRE --> DESTROY["Chỉ hủy khi không còn dependency và có phê duyệt"]
~~~

Rollback ứng dụng **không đồng nghĩa rollback vật liệu khóa**. Nếu bản mới đã mã hóa dữ liệu bằng DEK v2, bản cũ chỉ biết v1 sẽ không thể đọc dữ liệu đó. Developer cần kiểm tra **backward/forward compatibility**, chốt schema version và sử dụng canary/feature flag có giới hạn.

### 8.3. Trong sự cố khóa bị nghi lộ

Khi phát hiện key material hoặc workload credential có dấu hiệu compromise, developer phải phối hợp để:

1. **Ngừng đường lộ:** tắt debug log, thu hồi credential, hạn chế thao tác Sign/Decrypt/Unwrap theo quyết định của owner/security.
2. **Khoanh vùng:** xác định key ID/version, tenant, dữ liệu hoặc chữ ký bị ảnh hưởng và các instance đã sử dụng khóa.
3. **Chuyển sang khóa mới:** dùng đường triển khai và rotation đã được thử, không tái sử dụng khóa nghi lộ.
4. **Xử lý dữ liệu quá khứ:** re-encrypt khi DEK đã lộ, cập nhật trust khi signing key lộ, thu hồi session/token thích hợp.
5. **Đối soát cache/backup:** đảm bảo bản sao bí mật và khóa cũ không bị vô tình kích hoạt lại.
6. **Bằng chứng:** lưu event IDs, actor, key reference, policy version, kết quả; không công bố secret vào ticket.

**Không có phép gọi `rotate()` thần kỳ để chữa mọi hậu quả đã xảy ra.** Đổi KEK không làm dữ liệu mã hóa bởi DEK bị lộ trở lại bí mật.

## 9. Trách nhiệm khi xử lý lỗi và chống lạm dụng

Mã mật mã cần tuân thủ **fail closed** với lỗi xác thực hoặc lỗi policy. Developer phải phân biệt **lỗi vận hành** (KMS timeout) và **lỗi bảo mật** (tag sai, signature sai, truy cập không được phép), nhưng không rò rỉ quá nhiều chi tiết cho caller.

| Tình huống | Ứng xử an toàn |
| --- | --- |
| **AES-GCM tag sai** | Từ chối plaintext; không trả dữ liệu giải mã chưa xác thực. |
| **Chữ ký số không hợp lệ** | Từ chối yêu cầu; không thử ngẫu nhiên public key ngoài trust store. |
| **KMS AccessDenied** | Từ chối; không fallback sang key hard-code/local secret. |
| **KMS timeout** | Retry có giới hạn và backoff theo policy, tránh nhân bản yêu cầu không kiểm soát. |
| **Không tìm thấy key version** | Báo lỗi có thể xử lý/điều tra; không tự thử mọi khóa của tenant khác. |
| **Encryption context không khớp** | Từ chối; đối chiếu identity và object binding. |
| **Thông điệp replay** | Kiểm tra event ID, expiry, nonce nghiệp vụ, sequence/idempotency. |
| **Log/debug exception** | Ghi mã lỗi, key ID và trace ID phù hợp; không ghi DEK, plaintext, seed hoặc token. |
| **Load tăng đột biến** | Rate limit, concurrency limits và cảnh báo KMS cost/latency; không bỏ bảo vệ để tăng throughput. |

### 9.1. Caching và performance

**Không nên tắt mã hóa để đạt hiệu năng**. Khi cần giảm KMS calls:

- Đánh giá tính hợp lệ của **data key caching** do SDK/provider hỗ trợ hoặc theo thiết kế đã review.
- Giới hạn **thời gian sống, số bytes, số lượt mã hóa và scope tenant/purpose** của mỗi cached key.
- Quản lý nonce uniqueness **trên cùng DEK** khi nhiều instance cùng sử dụng dữ liệu cache.
- Xử lý **cache invalidation** khi revoke/rotate, không để một key compromise tiếp tục được dùng lâu.
- Phân biệt **cache public key dùng Verify** với **cache private/secret key**: mức rủi ro không giống nhau.

Không sao chép DEK vào một distributed cache không được đánh giá chỉ vì giảm latency. KMS cost là ràng buộc vận hành, không phải lý do tự mở rộng quyền secret.

## 10. Kiểm thử và code review trách nhiệm mật mã

Developer cần biến yêu cầu bảo mật thành **test cases có thể lặp lại**. Unit test “encrypt xong decrypt được” chỉ chứng minh đường chạy thuận, chưa đủ phát hiện sai sót.

| Bài kiểm tra | Kỳ vọng |
| --- | --- |
| Ciphertext bị sửa một byte | AES-GCM phải từ chối bằng lỗi xác thực. |
| Nonce hoặc AAD bị thay | Decrypt thất bại; không chấp nhận context sai. |
| Tenant khác đọc ciphertext | Authorization từ chối **trước** khi KMS Decrypt. |
| Key ID do client tự chọn | Không được dùng ngoài allowlist/trust policy. |
| KMS trả AccessDenied | Không fallback về khóa mặc định. |
| Rotate KEK từ v1 sang v2 | Dữ liệu mới được ghi đúng version, dữ liệu cũ còn đọc theo policy. |
| DEK bị thay trong wrapped metadata | Decrypt không thể trả plaintext không được xác thực. |
| Signing key mới S2 | Consumer đã nhận public key S2 trước khi signer bắt đầu dùng. |
| Signing key cũ bị revoke | Các yêu cầu mới bị từ chối theo trust policy. |
| Workload credential dev truy cập KMS prod | IAM phải từ chối. |
| Đăng nhập dùng KDF | Work factor/salt được lưu đúng; không có password/raw key trong log. |
| Audit log | Có metadata đủ điều tra; không rò DEK, private key, plaintext. |
| DR restore | Metadata/backup và đúng key versions được phục hồi với quyền hiện hành. |
| Concurrency cao | Giới hạn KMS/cryptography workload, không gây cạn RAM/CPU không kiểm soát. |

### 10.1. Checklist khi review pull request

- **Đúng mục đích khóa:** có reuse cùng key cho nhiều purpose mà không có thiết kế được đánh giá không?
- **Đúng định dạng:** có version/algorithm/key reference/AAD rõ không?
- **Không dùng crypto yếu:** có ECB, tự băm mật khẩu, predictable RNG, ECDSA nonce tự tạo sai không?
- **Không lộ secret:** có in raw key, plaintext hoặc credential ra exception/log/trace không?
- **Bảo vệ trust:** có xác minh certificate/JWKS/issuer/hostname và ràng buộc tenant không?
- **KMS policy:** service có quyền quá rộng không? Có mặc định dùng production key khi chạy local test không?
- **Khả năng xoay:** có thể đọc dữ liệu bản cũ, thay version, rollback ứng dụng và xử lý revoke không?
- **Failure handling:** mọi lỗi xác thực/giải mã có từ chối an toàn không?
- **Testing:** có negative tests, concurrency tests và tích hợp KMS được phép không?
- **Observability:** có đo lỗi/latency và audit mà không tiết lộ secret không?

Tài liệu chuẩn, threat model và review bảo mật cần được cập nhật khi **thuật toán, SDK, KMS provider hoặc giao thức** thay đổi. Thay một tên API không tự bảo đảm tương đương hành vi bảo mật.

## 11. Trách nhiệm trong CI/CD và chuỗi cung ứng phần mềm

Developer không chỉ bảo vệ secret khi service chạy mà còn trong **quy trình build, test và deploy**:

1. **CI credentials:** dùng danh tính runner tạm thời, giới hạn repository/branch/environment được phép gọi KMS.
2. **Không chứa production key trong unit tests:** dùng test keys riêng, dữ liệu giả hoặc adapter mock an toàn.
3. **Bảo vệ release signing:** chỉ workflow đã phê duyệt có quyền Sign bằng khóa release; gắn commit, artifact digest và approval theo policy.
4. **Review dependency:** crypto library, SDK KMS và provider phải có phiên bản được duy trì, đánh giá thay đổi API.
5. **Secret scanning:** ngăn private key/credential bị đưa lên Git, artifact, image và log; khi lộ phải **revoke/rotate**, không chỉ xóa commit hiển thị.
6. **Cấu hình theo môi trường:** production không tự fallback sang local keystore không được quản lý nếu KMS thiếu.
7. **IaC/IAM review:** quyền trong infrastructure-as-code cần được kiểm tra cùng code ứng dụng.
8. **Triển khai canary:** theo dõi decrypt failures, signature verification, key version usage và consumer readiness khi xoay khóa.

**Ký artifact không tự chứng minh build an toàn**. Developer phải bảo vệ nguồn, workflow và provenance; verifier cần kiểm tra artifact digest, danh tính signer và release policy.

## 12. Audit và observability: ghi đủ để điều tra nhưng không lộ khóa

Một log hữu ích có thể gồm:

~~~json
{
  "eventType": "ENVELOPE_DECRYPT_DENIED",
  "service": "billing-service",
  "environment": "production",
  "tenantRef": "tenant-anonymized-or-authorized-reference",
  "keyRef": "billing-prod-kek",
  "operation": "DecryptDataKey",
  "policyVersion": "billing-crypto-policy-v3",
  "reasonCode": "TENANT_SCOPE_DENIED",
  "requestCorrelationId": "trace-opaque-id",
  "result": "DENIED"
}
~~~

Đây là **ví dụ định dạng sự kiện**, không phải log thật. Việc ghi tên tenant/key ID cần theo **phân loại dữ liệu, retention và quyền truy cập** tương ứng.

Developer nên xây:

- **Sự kiện nghiệp vụ được phép:** actor/workload, key ID/version, operation, kết quả, thời gian và quyết định authorization.
- **Metrics tổng hợp:** decrypt failure rate, KMS latency/timeouts, error codes, số lượng key version đang dùng, rotation readiness.
- **Trace an toàn:** correlation ID để theo đường lỗi mà không truyền secret, plaintext hay token vào span attributes.
- **Cảnh báo:** tăng đột biến Sign/Decrypt, sử dụng key đã retired, consumer chưa cập nhật public key, lỗi tag hoặc bất thường theo tenant.
- **Kiểm soát log:** tránh lưu vô thời hạn, giảm PII và phân quyền xem; audit trail cần có biện pháp chống sửa đổi phù hợp.

**Không log:** raw DEK/KEK, private key, session key, seed, password, full token, plaintext nhạy cảm hoặc bản dump cấu hình chứa credential. Hash một secret rồi log giá trị hash cũng cần cân nhắc: có thể tạo dấu vết liên kết hoặc hỗ trợ đoán secret nếu không thiết kế đúng.

### 12.1. Truy vết lỗi không làm rò dữ liệu

Thông báo công khai nên có mức đủ dùng, chẳng hạn **“không thể xác minh hoặc giải mã dữ liệu”** cho caller không đáng tin, còn hệ thống nội bộ ghi **reason code** sau khi đã lọc. Không gửi stack trace của crypto provider, raw ciphertext hoặc KMS response chứa dữ liệu nhạy cảm về phía client.

## 13. Tình huống thực tế: trách nhiệm developer tại nền tảng thanh toán

Giả sử hệ thống có **Order Service**, **Billing Service**, **Payment Service** và **Ledger Service**.

### 13.1. Billing Service mã hóa dữ liệu hóa đơn

**Yêu cầu:** mỗi tenant không được đọc dữ liệu tenant khác; dữ liệu hóa đơn phải còn phục hồi được sau khi KMS rotate KEK.

Developer của Billing Service cần:

1. Xác định **owner, tenant, invoice ID, data classification** cùng security/data team.
2. Dùng **DEK** để mã hóa bằng AES-GCM; KMS quản lý KEK, không nhúng raw key.
3. Ràng buộc tenant/invoice/purpose trong **encryption context và AAD**.
4. Kiểm tra caller có quyền với invoice trước khi unwrap DEK.
5. Lưu đầy đủ **wrapped DEK, nonce/tag, key ID/version và schema**.
6. Viết migration từ KEK v3 → v4, kiểm thử đọc bản mã cũ, kể cả backup.
7. Ghi audit key ID, workload, operation và kết quả; không ghi plaintext.
8. Khi nghi DEK lộ, hỗ trợ đánh giá **re-encrypt bằng DEK mới**, không chỉ rewrap.

### 13.2. Payment Service ký sự kiện, Ledger Service xác minh

Developer của Payment Service cần:

1. Ký đúng **event ID, issuer, audience, tenant, amount, currency, timestamp/purpose** theo định dạng thống nhất.
2. Gọi KMS/HSM Sign bằng **key reference** và quyền đã được giới hạn, không xuất private key.
3. Không coi Sign thành công là bằng chứng mọi nghiệp vụ đã được phê duyệt.

Developer của Ledger Service cần:

1. Nhận **public key S1/S2** từ trust store/JWKS đã ghim issuer và thuật toán.
2. Verify chữ ký trên **đúng bytes**, từ chối signature sai.
3. Kiểm tra **quyền ký nghiệp vụ, tenant và replay/idempotency**.
4. Hỗ trợ cửa sổ chuyển tiếp S1 → S2 theo policy và xử lý khi một khóa bị revoke.

**Hệ quả:** nếu Ledger chỉ kiểm chữ ký mà bỏ qua event ID, một sự kiện thanh toán từng hợp lệ có thể bị gửi lại và ghi sổ hai lần. Đây là lỗi **ứng dụng/giao thức**, không phải lỗi toán học của Ed25519.

### 13.3. Sự cố giả định

Một developer vô tình bật debug logging ghi **wrapped DEK và dữ liệu hóa đơn**. Wrapped DEK thường không bí mật như DEK rõ, nhưng log vẫn có thể chứa **ciphertext, context và PII** và mở rộng bề mặt rủi ro. Nếu log chứa cả **plaintext DEK** hoặc quyền KMS bị lạm dụng, hậu quả lớn hơn nhiều.

Khi phát hiện, developer cần phối hợp:

- Ngừng việc log và kiểm soát truy cập hệ thống chứa log.
- Xác định log có **secret rõ, ciphertext hay metadata** để phân loại sự cố chính xác.
- Đánh giá kho log, retention, backups và người đã truy cập.
- Thực hiện thu hồi/xoay/re-encrypt khi security/data owner yêu cầu theo mức ảnh hưởng.
- Bổ sung tests và linter/secret scanning thích hợp để tránh tái diễn.

## 14. Sai lầm thường gặp và cách khắc phục

| Sai lầm của developer | Hậu quả | Biện pháp |
| --- | --- | --- |
| “KMS đã an toàn nên code không cần kiểm tra tenant” | Lộ dữ liệu chéo tenant khi workload có quyền Decrypt rộng. | Authorization trước KMS và context được gắn với identity đã xác thực. |
| Hard-code raw AES key, HMAC key hoặc private key | Lộ bí mật qua Git/image và khó rotate. | KMS/HSM/secret manager và key reference đúng môi trường. |
| Sinh key/token bằng `Random` hoặc timestamp | Giá trị có thể dự đoán. | SecureRandom/provider/KMS đúng mục đích. |
| Dùng AES-GCM nhưng tái sử dụng key + nonce | Có thể phá bảo mật và tính toàn vẹn. | Quản lý nonce uniqueness, key usage limits hoặc DEK mới. |
| Dùng chung key AES cho Sign/MAC/Encrypt | Sai primitive, tăng tác động khi một secret lộ. | Tách purpose và key usage; dùng thuật toán đúng. |
| Bỏ qua GCM tag hoặc chữ ký sai để “không gián đoạn” | Chấp nhận dữ liệu bị sửa hoặc giả mạo. | Fail closed và cơ chế retry/vận hành riêng. |
| Lấy public key/issuer theo URL không tin cậy trong token | Chấp nhận chữ ký kẻ tấn công. | Trust store/JWKS ghim nguồn và allowlist thuật toán. |
| Không có key ID/version bên ciphertext | Mất khả năng đọc dữ liệu sau rotation. | Metadata có version, read compatibility và migration. |
| Chuyển signing key trước khi verifier cập nhật | Các consumer từ chối chữ ký mới. | Công bố public key mới, xác minh readiness trước switch. |
| Tắt TLS hostname verification để sửa lỗi | Có thể kết nối endpoint giả qua kênh vẫn được mã hóa. | Sửa trust chain/identity thay vì tắt bảo vệ. |
| Log DEK, plaintext, token hoặc provider response nhạy cảm | Tăng phạm vi rò rỉ. | Structured logging đã lọc và review trước triển khai. |
| Cấp quyền KMS `*` cho mọi service | Một workload bị chiếm quyền ảnh hưởng toàn hệ thống. | Least privilege, IAM conditions và tách môi trường. |
| Catch crypto exception rồi trả dữ liệu mặc định | Che giấu việc kiểm tra integrity thất bại. | Phân loại lỗi an toàn, từ chối hoặc cách ly bản ghi. |
| Chỉ viết test encrypt/decrypt thành công | Không thấy lỗi tampering, tenant isolation, rotation. | Negative tests, integration tests, restore và chaos scenarios. |
| Chỉ đổi KEK khi DEK đã bị lộ | Dữ liệu cũ vẫn có thể bị đọc. | Phân tích phạm vi, thay DEK/re-encrypt khi cần. |
| Xóa private key/KEK vì “không còn dùng” | Có thể mất dữ liệu hoặc khả năng ký/xác minh lịch sử. | Inventory dependencies, retention, phê duyệt trước hủy. |
| Dùng cùng test/prod key để đơn giản hóa | Test có thể làm lộ production hoặc gây thao tác sai. | Phân tách khóa, môi trường và workload identities. |

## 15. Checklist trước khi giao một tính năng dùng mật mã

Trước khi đánh dấu một pull request hoặc service là sẵn sàng, developer có thể tự kiểm tra:

1. **Mục đích:** dữ liệu và thuộc tính bảo mật đã được nêu rõ trong threat model chưa?
2. **Thuật toán:** sử dụng primitive/giao thức/thư viện được phép, không tự triển khai không?
3. **Key ownership:** owner, tenant, environment và key usage được xác định chưa?
4. **Nguồn khóa:** khóa sinh bằng CSPRNG/KMS đúng; không hard-code secret hoặc seed yếu chứ?
5. **Custody:** private key/KEK ở đâu, có non-exportable hoặc phương án khác theo chính sách?
6. **Authorization:** caller có được kiểm tra quyền đối tượng **trước khi gọi Decrypt/Sign** không?
7. **Trust:** public key/chứng chỉ có được xác thực theo issuer/identity/thuật toán không?
8. **Nonce/AAD:** AEAD có quản lý unique nonce, ràng buộc context và kiểm tra tag không?
9. **Key separation:** DEK, KEK, signing key, MAC key và session key có mục đích riêng không?
10. **Metadata:** ciphertext/signature có đủ key ID, version, schema, nonce, wrapped DEK và context cần thiết không?
11. **Rotation:** có thể chuyển sang key mới mà vẫn đọc/xác minh dữ liệu lịch sử theo policy không?
12. **Revocation:** có thể từ chối khóa compromise, xóa cache và cập nhật trust không?
13. **Deletion:** đã có dependency mapping và kiểm tra backup trước destroy/crypto-shredding chưa?
14. **Failure handling:** signature sai, GCM tag sai, KMS timeout/AccessDenied đều được xử lý an toàn chứ?
15. **Logs/metrics:** có audit metadata đủ điều tra nhưng không chứa raw secret, plaintext hoặc token không?
16. **CI/CD:** build, release và IaC không lộ key; runner có quyền hạn chế không?
17. **Tests:** có unit, negative, integration và migration/restore tests phù hợp không?
18. **Collaboration:** security, platform, data owner và SRE đã review các phần thuộc trách nhiệm của họ chưa?

## 16. Câu hỏi tự kiểm tra

1. Vì sao có KMS/HSM không đủ bảo đảm code ứng dụng sử dụng khóa đúng?
2. **Developer**, **security architect**, **KMS administrator** và **data owner** khác nhau về trách nhiệm nào?
3. Tại sao phải kiểm tra authorization theo tenant trước khi gọi KMS Decrypt?
4. DEK khác KEK về mục đích và vị trí xuất hiện trong bộ nhớ ứng dụng ra sao?
5. Tại sao AES-GCM cần quản lý **nonce duy nhất theo key** dù nonce không cần bí mật?
6. Sử dụng encryption context/AAD có thể giúp tránh tráo bản ghi thế nào? Nó có thay authorization không?
7. Vì sao `kid` hoặc public key do request gửi không tự chứng minh danh tính signer?
8. Khi chuyển signing key S1 sang S2, developer phía signer và verifier phải phối hợp trình tự nào?
9. Nếu DEK bị lộ, rotate KEK rồi rewrap cùng DEK có đủ bảo vệ ciphertext cũ không?
10. Khi cache DEK để giảm chi phí KMS, những giới hạn nào phải được áp dụng?
11. Một test encrypt/decrypt thành công chứng minh được gì, và còn thiếu những negative tests nào?
12. Tại sao rollback ứng dụng có thể khó nếu dữ liệu mới đã mã hóa bằng key version mới?
13. Nếu KMS AccessDenied, ứng dụng có được dùng khóa mặc định hard-code để tiếp tục xử lý không?
14. Có thể log những metadata nào về thao tác Decrypt/Sign mà không làm lộ vật liệu khóa?
15. Vì sao người viết code cần cung cấp inventory về ciphertext/backups trước khi đội vận hành hủy khóa?
16. Một chữ ký số hợp lệ có tự bảo đảm giao dịch được phép và không bị replay không?

**Ghi nhớ:** **Developer responsibility** không phải là tự quản trị tất cả khóa, mà là **thiết kế đúng ranh giới tin cậy, tích hợp API mật mã chuẩn, kiểm tra phân quyền, bảo vệ secret và quản lý metadata/nonce/key version, xử lý lỗi an toàn, hỗ trợ rotation/revocation và tạo bằng chứng kiểm toán**. Kết hợp với **security, IAM, SRE, KMS/HSM và data owner**, trách nhiệm này giúp hệ thống bảo vệ khóa từ lúc tạo đến khi hủy mà không rò bí mật, chấp nhận thao tác trái phép hoặc mất khả năng khôi phục dữ liệu.
