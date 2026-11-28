# Register key – Đăng ký khóa mật mã vào hệ thống quản lý khóa

**Register key (đăng ký khóa)** là bước ghi nhận **một khóa đã được tạo hoặc tiếp nhận** vào hệ thống quản lý có thẩm quyền, gắn khóa với **định danh, thuật toán, mục đích sử dụng, chủ sở hữu, nguồn gốc, quyền truy cập và trạng thái vòng đời**. Tùy kiến trúc, bước này còn bao gồm kiểm tra khóa hợp lệ, xác minh **quyền sở hữu private key**, xác thực nguồn nhập, hoặc phê duyệt trước khi cho phép khóa được sử dụng.

Trong chương **Key lifecycle** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, đăng ký khóa nằm giữa các hoạt động **tạo/tiếp nhận** và **cấp phát/kích hoạt để sử dụng**. Đây là khâu giúp kết nối mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán với một vòng đời nhất quán: **tạo → đăng ký/cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**.

> **Cần phân biệt:** Một khóa **đã đăng ký** chưa chắc **được tin cậy**, **được kích hoạt** hoặc **được phép sử dụng**. Có bản ghi trong key registry không tự chứng minh private key do đúng người giữ, public key thuộc đúng danh tính, hoặc khóa có thể dùng cho mọi thao tác mật mã.

## 1. Đăng ký khóa thực chất là làm gì?

Giả sử hệ thống Payment Service vừa tạo một cặp khóa Ed25519 để ký các sự kiện thanh toán. Nếu chỉ lưu private key trên một máy và gửi public key qua email, các dịch vụ khác khó trả lời:

- Public key nào đang thuộc Payment Service phiên bản production?
- Khóa này chỉ dùng để **ký sự kiện** hay có thể dùng để ký **release**?
- Ai đã phê duyệt việc tạo và đăng ký khóa?
- Khóa bắt đầu có hiệu lực khi nào; khi nào cần xoay và thu hồi?
- Khi có hai khóa cũ/mới cùng tồn tại, verifier tìm đúng public key bằng cách nào?
- Khóa ký có thực sự được bảo vệ trong KMS/HSM, hay có bản sao private key ở nơi khác?
- Nếu phát hiện lạm dụng quyền ký, những sự kiện nào phụ thuộc vào khóa này?

**Key registration** tạo một bản ghi quản trị đủ thông tin để trả lời các câu hỏi này. Nó không chỉ là thao tác thêm một chuỗi vào database: quy trình phải kiểm tra **độ tin cậy của nguồn dữ liệu và danh tính người yêu cầu**, xác định **quyền sử dụng** rồi đưa khóa vào vòng đời theo chính sách.

### 1.1. Phân biệt register, generate, import và activate

| Hoạt động | Ý nghĩa chính | Có phải cùng một thao tác? |
| --- | --- | --- |
| **Generate key** | Sinh khóa mới bằng CSPRNG, KMS/HSM hoặc provider phù hợp. | **Không.** Sinh vật liệu khóa không tự tạo bản ghi đăng ký ở mọi hệ thống. |
| **Register key** | Gắn khóa với định danh, nguồn gốc, owner, usage và chính sách trong registry có thẩm quyền. | Là **bài toán quản trị và liên kết khóa**. |
| **Import key** | Đưa vật liệu khóa từ ngoài vào một kho/KMS/HSM theo quy trình nhập phù hợp. | Có thể là **một phần** của đăng ký, nhưng rủi ro nhạy cảm hơn vì liên quan key material. |
| **Publish public key** | Cung cấp public key cho bên xác minh/nhận qua kênh phù hợp. | Không đồng nghĩa khóa đã được **xác thực danh tính** hoặc phê duyệt trong registry. |
| **Issue certificate** | Một CA ký chứng chỉ liên kết public key với danh tính/thuộc tính đã kiểm chứng theo chính sách. | Khác đăng ký khóa thuần; có thể dùng bản ghi đăng ký làm đầu vào. |
| **Activate key** | Cho phép khóa thực hiện các thao tác được quy định, như SIGN/VERIFY/ENCRYPT. | Chỉ nên diễn ra sau các kiểm tra và phê duyệt cần thiết. |
| **Rotate / retire / revoke / destroy** | Thay phiên bản, ngừng tạo mới, thu hồi niềm tin/quyền hoặc hủy vật liệu khóa. | Xảy ra ở các giai đoạn tiếp theo; registry phải theo dõi liên tục. |

Trong một số KMS, thao tác **CreateKey** có thể vừa tạo khóa vừa tạo metadata/quản lý định danh; hệ thống vẫn cần kiểm tra policy và đăng ký **ngữ cảnh nghiệp vụ** của khóa. Không áp đặt một API mang tên **RegisterKey** cho mọi nhà cung cấp.

## 2. Những loại khóa nào cần được đăng ký?

Phạm vi đăng ký phụ thuộc vào kiến trúc, nhưng ít nhất phải quản lý các khóa có ảnh hưởng đến dữ liệu hoặc danh tính lâu dài.

| Loại khóa | Ví dụ | Thông tin đăng ký đặc biệt |
| --- | --- | --- |
| **DEK đối xứng** | AES-256-GCM mã hóa tệp/nhóm dữ liệu. | Mục đích, tập dữ liệu/tenant, thuật toán và mode, wrapped DEK, KEK bảo vệ, key version. |
| **KEK / wrapping key** | Khóa KMS bọc nhiều DEK. | Phạm vi các DEK phụ thuộc, quyền wrap/unwrap, owner và nơi lưu khóa. |
| **Private/public key pair** | Ed25519 ký sự kiện, RSA-OAEP giải mã, X25519 thỏa thuận khóa. | Thuật toán, key usage, private key custody, public key fingerprint, proof of possession khi cần. |
| **Khóa MAC** | HMAC-SHA-256 bảo vệ thông điệp liên dịch vụ. | Bên được biết secret, quyền tạo/xác minh MAC, phiên bản và giới hạn chia sẻ. |
| **Khóa ký release** | Ký manifest hoặc container artifact. | Repository, workflow, môi trường phát hành, kênh trust và phê duyệt. |
| **Khóa danh tính TLS** | Private key của workload dùng trong chứng chỉ. | Danh tính dịch vụ, chứng chỉ, issuer, phạm vi trust, hạn dùng và chính sách gia hạn. |
| **Khóa gốc/master key** | Khóa cấp cao trong phân cấp bảo vệ. | Độ nhạy cảm đặc biệt, kiểm soát đa bên, hậu quả hủy và khả năng phục hồi. |

**Khóa phiên tạm thời** (như một số ephemeral ECDHE private key) không nhất thiết phải có bản ghi riêng trong registry dài hạn. Có thể quản lý chúng bằng giao thức, định danh phiên và kiểm toán phù hợp mà **không lưu private key hoặc shared secret vào hệ thống quản trị**. Đăng ký quá nhiều bí mật ngắn hạn vào registry có thể tăng rủi ro và làm sai mục đích.

## 3. Key registry cần lưu những metadata nào?

Một bản ghi key registration có thể gồm các nhóm trường:

| Nhóm | Trường minh họa | Ý nghĩa |
| --- | --- | --- |
| **Định danh** | keyId, version, alias, fingerprint | Chọn đúng đối tượng khóa và phiên bản. |
| **Loại/thuật toán** | keyType, algorithm, curve, mode, size, usage | Không dùng nhầm khóa ký làm khóa mã hóa. |
| **Sở hữu/phạm vi** | owner, service, tenant, environment, classification | Ranh giới trách nhiệm, dữ liệu và phân quyền. |
| **Nguồn gốc** | generatedInKMS, importedBYOK, provider, HSM reference | Biết khóa được tạo/lưu từ đâu; phục vụ đánh giá độ tin cậy. |
| **Bằng chứng/kiểm tra** | publicKeySPKI, fingerprint, certificate, PoP result, attestation reference | Phát hiện tráo khóa và liên kết khóa với chủ thể theo chính sách. |
| **Thời gian** | createdAt, registeredAt, notBefore, expiresAt, cryptoperiod | Lập lịch kích hoạt, rotate và đánh giá hết hạn. |
| **Trạng thái** | registered, active, disabled, compromised, pendingDeletion | Kiểm soát thao tác được phép theo từng giai đoạn. |
| **Chính sách** | allowedOperations, IAM policy, approvalId, rotationPolicy | Thực thi least privilege và separation of duties. |
| **Phụ thuộc** | DEK count, wrappedByKeyId, affectedObjects, backups | Xác định hậu quả khi thu hồi hoặc hủy khóa. |
| **Kiểm toán** | actor, requestId, policyVersion, decision, timestamp | Điều tra ai đã đưa khóa vào hệ thống và tại sao. |

Các tên trường trên là **mô hình minh họa**, không phải schema tiêu chuẩn của một KMS cụ thể. Hệ thống có thể lưu key material ở một nơi và metadata ở nơi khác. Khi đó registry giữ **tham chiếu có kiểm soát** thay vì tự sao chép secret.

### 3.1. Key ID, alias, fingerprint và chứng chỉ khác nhau thế nào?

- **Key ID:** định danh một đối tượng khóa trong hệ thống quản lý. Có thể là UUID hoặc mã định danh do KMS cấp; nó **không tự là bí mật hoặc bằng chứng danh tính**.
- **Version:** phân biệt các thế hệ vật liệu khóa, đặc biệt khi rotate. Một **alias** có thể trỏ sang phiên bản mới theo thời gian, nên không được dùng alias thay key version khi giải mã dữ liệu lịch sử.
- **Fingerprint:** giá trị băm của **biểu diễn khóa công khai** đã quy định, ví dụ SHA-256 trên X.509 SubjectPublicKeyInfo DER. Hai hệ thống phải thống nhất **bytes được băm**.
- **Chứng chỉ X.509:** cấu trúc có public key và các thuộc tính đã được CA chứng thực theo một chính sách. Fingerprint public key và fingerprint **toàn bộ chứng chỉ** thường khác nhau.
- **kid của JWK/JWKS:** nhãn để chọn khóa trong một tập khóa; **kid không chứng minh issuer, owner hoặc quyền sử dụng**.

Không cho người dùng chọn một keyId giống tên khóa production rồi tự động gán quyền sử dụng. Quyền phải xuất phát từ **danh tính caller đã xác thực** và **policy server-side**.

### 3.2. Ví dụ bản ghi đăng ký minh họa

~~~yaml
keyId: payment-events-sign-2026-02
version: 2
owner: payment-service
environment: production
tenantScope: payments-platform
keyType: asymmetric
algorithm: Ed25519
usage:
  - SIGN
  - VERIFY
custody:
  provider: organizational-kms
  privateKeyExportable: false
publicKey:
  format: X.509-SPKI-DER
  fingerprintSha256: "<verified-sha256-of-SPKI>"
registeredAt: "<ISO-8601 timestamp>"
activatedAt: null
status: REGISTERED
approvalRef: "<trusted-approval-reference>"
~~~

Đây là **dữ liệu minh họa, không phải YAML thực tế của bài học hoặc định dạng API chuẩn**. Một khóa chưa được phê duyệt hoặc chưa gắn đúng trust policy có thể được ghi nhận ở trạng thái **REGISTERED** nhưng **không được phép SIGN**.

Metadata đăng ký phải được kiểm soát tính toàn vẹn, phân quyền ghi và có lịch sử thay đổi. Không được cho caller sửa **owner, allowedOperations, keyType** hoặc status tùy ý bằng một request cập nhật thông thường.

## 4. Quy trình đăng ký khóa theo nguyên tắc zero trust

Một workflow điển hình:

~~~mermaid
flowchart TD
    REQUEST["Yêu cầu đăng ký khóa"] --> AUTH["Xác thực caller và kiểm tra quyền register"]
    AUTH --> ORIGIN["Kiểm tra loại khóa, nguồn gốc và chính sách"]
    ORIGIN --> VALIDATE["Kiểm tra thuật toán, encoding, key usage, expiry"]
    VALIDATE --> PROOF["Xác minh quyền sở hữu hoặc bằng chứng nhập khóa"]
    PROOF --> DUP["Kiểm tra fingerprint/key ID, xung đột và idempotency"]
    DUP --> RECORD["Ghi metadata, owner, version, trạng thái REGISTERED"]
    RECORD --> APPROVE{"Phê duyệt/kích hoạt được phép?"}
    APPROVE -->|Chưa| HOLD["Giữ trạng thái chưa active"]
    APPROVE -->|Có| ACTIVE["ACTIVE: cho phép thao tác theo policy"]
    ACTIVE --> AUDIT["Ghi audit; theo dõi rotate/revoke/destroy"]
    HOLD --> AUDIT
~~~

Các bước cần được thực thi theo **quyền và trạng thái thực tế**. Nếu một bước thất bại, hệ thống phải **từ chối hoặc giữ khóa ở trạng thái chưa hoạt động**, thay vì ghi nhận thành công rồi tự động cấp quyền dùng.

### 4.1. Tiếp nhận yêu cầu

- Caller phải được **xác thực**: workload identity, tài khoản có quyền hoặc kênh quản trị được bảo vệ.
- Xác minh caller **được phép đăng ký loại khóa nào** cho owner/tenant/environment nào.
- Kiểm tra định dạng bản ghi, loại thuật toán, key usage, kích thước hoặc curve theo allowlist.
- Tách request **đăng ký public key** khỏi request **nhập private/symmetric key material**: hai đường có rủi ro và API bảo vệ khác nhau.

### 4.2. Xác minh nguồn gốc và quyền sở hữu khóa

Đối với **public key** dùng cho chữ ký, một cơ chế có thể là **Proof of Possession (PoP)**: bên đăng ký ký một challenge mới bằng private key tương ứng, rồi registry xác minh chữ ký bằng public key được gửi.

PoP cho thấy **bên yêu cầu có khả năng dùng private key tương ứng tại thời điểm kiểm tra** (hoặc có quyền gọi một hệ thống ký thay mặt). Tuy nhiên **PoP không tự chứng minh họ được phép đăng ký khóa dưới tên Payment Service hoặc tenant khác**. Registry phải độc lập xác thực caller và quyền gắn khóa với danh tính.

Với **KMS/HSM**, cần kiểm tra nguồn gốc qua metadata đáng tin, chính sách provider và **attestation** nếu có hỗ trợ và có yêu cầu. Không mặc định chỉ cần một chuỗi tự khai **generatedInHSM=true** là đủ chứng minh khóa đã sinh trong HSM.

### 4.3. Xử lý trùng lặp và tính nhất quán

- Cùng một public key có thể được gửi đăng ký nhiều lần do retry. Cần xác định **idempotency key**, chính sách duplicate và cách đối chiếu owner/usage/version.
- Một **fingerprint trùng** không đồng nghĩa mọi metadata đều được phép gộp. Nếu hai chủ thể không liên quan đăng ký cùng public key, đây có thể là **cảnh báo nghiêm trọng** về tái sử dụng khóa hoặc giả mạo danh tính.
- Khi ghi bản ghi và cấp quyền KMS, phải tránh trạng thái **metadata ghi thành công nhưng ACL chưa áp** hoặc **ACL đã mở nhưng record chưa duyệt**.
- Key ID/alias có thể được tái sử dụng theo quy tắc từng hệ thống, nhưng **version vật liệu khóa và object identity** cần được lưu không mơ hồ.

## 5. Đăng ký public key, private key và secret key có khác nhau

### 5.1. Public key registry

Public key có thể được lưu ở dạng SPKI DER/PEM hoặc JWK theo giao thức. Registry cần kiểm tra:

1. **Thuật toán và key usage**: Ed25519 cho VERIFY; X25519 phục vụ key agreement; RSA cần xác định SIGN/DECRYPT và padding ở nơi sử dụng.
2. **Nguồn tin cậy/owner**: ai có quyền đăng ký khóa cho service hoặc tài khoản?
3. **Proof of Possession** nếu yêu cầu; chọn challenge mới, hết hạn và dùng một lần.
4. **Fingerprint và encoding** đúng quy ước.
5. **Trạng thái hiệu lực** và bản phân phối public key/chứng chỉ.
6. **Quyền sử dụng**: người có thể lấy public key để verify khác với người được phép ký bằng private key.

Chỉ đăng public key vào JWKS không tự làm nó trở thành khóa đáng tin cho mọi verifier. Consumer cần **issuer/JWKS URL đã được cấu hình, thuật toán cho phép, audience và phạm vi trust**.

### 5.2. Private key và symmetric key material

**Private key** và **secret key/KEK/DEK** là dữ liệu cần giữ bí mật. Quy trình đăng ký không được tự yêu cầu caller gửi key material dạng rõ tới một API chung chỉ để lấy fingerprint hoặc metadata.

Nếu tổ chức dùng **BYOK (Bring Your Own Key)** hoặc imported key material, cần tuân theo đúng quy trình của KMS/HSM:

- Xác thực chủ thể được phép nhập và mục đích/thuật toán hỗ trợ.
- Dùng **cơ chế chuyển khóa được chuẩn hóa** hoặc public wrapping key/chứng chỉ nhập của provider khi sản phẩm yêu cầu.
- Không xuất key material vào log, ticket, repository hoặc file tạm không được bảo vệ.
- Kiểm tra thời hạn khóa nhập, khả năng phục hồi, chính sách export và hành vi khi key material hết hạn hoặc bị xóa.
- Chỉ kích hoạt khi key import thành công, policy được xác nhận và kiểm soát phụ thuộc phù hợp.

Một số dịch vụ có API **ImportKeyMaterial** hoặc đối tượng tương tự; **không có tên thao tác hoặc cơ chế import chung cho mọi nhà cung cấp**. Một khóa được import có thể có quy tắc rotation, expiration và backup khác khóa được sinh nội bộ.

### 5.3. Đăng ký DEK dưới envelope encryption

Một DEK AES-GCM có thể được sinh ngẫu nhiên rồi **wrap dưới KEK** trong KMS/HSM. Ứng dụng lưu:

~~~text
Ciphertext của dữ liệu + nonce + tag
Wrapped DEK + KEK key ID/version
DEK logical ID + thuật toán/mode + tenant/object scope
~~~ 

Registry chỉ nên giữ thông tin cần để **truy dấu DEK đang phụ thuộc KEK nào**, chính sách tuổi/thay DEK và vùng dữ liệu. Không nhất thiết lưu **DEK dạng rõ** trong registry. Nếu nhiều DEK cùng được bảo vệ bởi một KEK, bản ghi phụ thuộc giúp tránh **hủy KEK khi còn dữ liệu cần giải mã**.

**Rotate KEK** có thể dẫn tới **rewrap DEK** mà không cần mã hóa lại bản mã dữ liệu. **Rotate DEK** thường đòi hỏi đánh giá mã hóa lại dữ liệu cũ. Registry phải phân biệt hai loại phiên bản này.

## 6. Java 17: ví dụ đăng ký public key kèm Proof of Possession

Ví dụ dưới đây minh họa một **public-key registry** đơn giản: bên đăng ký chứng minh có khả năng ký bằng private key Ed25519, registry kiểm tra danh tính caller từ một lớp xác thực **giả lập**, gắn key usage và fingerprint rồi tạo bản ghi ở trạng thái **REGISTERED**, chưa cấp quyền ký.

**Đây là demo trong một tiến trình, không phải dịch vụ đăng ký khóa sản xuất.** Production cần authentication thực, lưu challenge có TTL dùng một lần và gắn với session/caller, phân quyền theo tenant, transaction/idempotency, lưu trữ bền vững, audit và hạn chế DoS.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.interfaces.EdECPublicKey;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;
import java.util.UUID;

public class KeyRegistrationDemo {
    record RegisteredKey(String id, String owner, String purpose,
                         String algorithm, String fingerprint, String status) {}

    // Demo đồng bộ, đơn giản hóa: chỉ một pending challenge mỗi owner.
    static final class Registry {
        private final SecureRandom rng = new SecureRandom();
        private final Map<String, byte[]> pending = new HashMap<>();
        private final Map<String, RegisteredKey> records = new HashMap<>();

        private static void field(DataOutputStream out, byte[] bytes)
                throws Exception {
            out.writeInt(bytes.length);
            out.write(bytes);
        }

        static byte[] proofInput(String owner, String purpose,
                                 byte[] challenge, byte[] encodedPublic)
                throws Exception {
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            DataOutputStream out = new DataOutputStream(buffer);
            field(out, "key-registration-demo/v1"
                    .getBytes(StandardCharsets.UTF_8));
            field(out, owner.getBytes(StandardCharsets.UTF_8));
            field(out, purpose.getBytes(StandardCharsets.UTF_8));
            field(out, challenge);
            field(out, encodedPublic);
            out.flush();
            return buffer.toByteArray();
        }

        byte[] issueChallenge(String authenticatedOwner) {
            // Trong production: xác thực caller trước, TTL và anti-replay.
            if (!"payment-service-prod".equals(authenticatedOwner)) {
                throw new SecurityException("Caller is not authorized");
            }
            byte[] challenge = new byte[32];
            rng.nextBytes(challenge);
            pending.put(authenticatedOwner, challenge);
            return challenge.clone();
        }

        RegisteredKey register(
                String authenticatedOwner, String purpose,
                PublicKey candidate, byte[] proofSignature) throws Exception {
            // Lấy challenge server-side và tiêu thụ đúng một lần.
            byte[] challenge = pending.remove(authenticatedOwner);
            if (challenge == null) {
                throw new SecurityException("Missing or reused challenge");
            }
            if (!"payment-service-prod".equals(authenticatedOwner)
                    || !"PAYMENT_EVENT_SIGNING".equals(purpose)) {
                throw new SecurityException("Key purpose not allowed");
            }
            if (!(candidate instanceof EdECPublicKey ed)
                    || !"Ed25519".equals(ed.getParams().getName())) {
                throw new SecurityException("Unsupported public key");
            }

            byte[] encoded = candidate.getEncoded(); // X.509 SPKI DER
            byte[] toVerify = proofInput(
                    authenticatedOwner, purpose, challenge, encoded);
            Signature verifier = Signature.getInstance("Ed25519");
            verifier.initVerify(candidate);
            verifier.update(toVerify);
            if (!verifier.verify(proofSignature)) {
                throw new SecurityException("Invalid proof of possession");
            }

            String fingerprint = HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(encoded));
            if (records.values().stream().anyMatch(
                    item -> item.fingerprint().equals(fingerprint))) {
                throw new SecurityException("Key already registered");
            }

            RegisteredKey record = new RegisteredKey(
                    UUID.randomUUID().toString(), authenticatedOwner,
                    purpose, "Ed25519", fingerprint, "REGISTERED");
            records.put(record.id(), record);
            return record;
        }
    }

    public static void main(String[] args) throws Exception {
        Registry registry = new Registry();

        // Demo: caller đã được xác thực ở lớp ngoài.
        String authenticatedOwner = "payment-service-prod";
        String purpose = "PAYMENT_EVENT_SIGNING";
        KeyPair pair = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();

        byte[] challenge = registry.issueChallenge(authenticatedOwner);
        byte[] payload = Registry.proofInput(
                authenticatedOwner, purpose, challenge,
                pair.getPublic().getEncoded());

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(payload);
        byte[] proof = signer.sign();

        RegisteredKey registered = registry.register(
                authenticatedOwner, purpose, pair.getPublic(), proof);
        System.out.println("Key ID: " + registered.id());
        System.out.println("Status: " + registered.status());
        System.out.println("Public fingerprint: "
                + registered.fingerprint());

        // Không in private key; REGISTERED chưa đồng nghĩa ACTIVE.
    }
}
~~~

### 6.1. Ví dụ chứng minh được điều gì?

- Challenge ngẫu nhiên do registry phát hành giúp chống việc tái sử dụng một chữ ký đăng ký cũ trong **mô hình đồng bộ đơn giản** của demo.
- Chữ ký bao phủ **owner, purpose, challenge, public key encoding và version giao thức**; điều này giúp phát hiện việc tráo các trường trong quá trình chứng minh.
- Registry kiểm tra thuật toán Ed25519, quyền theo một **owner đã được xác thực giả lập**, chữ ký PoP và bản ghi trùng fingerprint.
- Định danh **key ID** do hệ thống quản lý cấp khác với **fingerprint SHA-256** trên public key.
- Trạng thái **REGISTERED** chỉ ghi nhận khóa được chấp nhận vào registry; **không tự mở quyền SIGN**.

### 6.2. Những gì demo chưa giải quyết

- Không có cơ chế xác thực caller thực, session, tenant authorization, RBAC hoặc phê duyệt nhiều bên.
- Challenge chỉ nằm trong RAM, không có TTL, chống replay phân tán, quản lý nhiều request đồng thời hoặc xử lý crash/restart.
- Map trong bộ nhớ không cung cấp transaction, index uniqueness, audit bền vững hoặc cảnh báo khi fingerprint trùng trên các owner.
- Thao tác PoP chỉ chứng minh **khả năng sử dụng private key**, không chứng minh key material được tạo trong HSM hay không bao giờ được xuất.
- Code chỉ đăng ký **public key**; tuyệt đối không gửi **private key/DEK/KEK dạng rõ** vào registry theo mẫu này.
- Không công bố khóa qua PKI/JWKS hoặc triển khai kiểm tra trust tại consumer. Cũng chưa có cơ chế rotate, revoke, disable và destroy.

## 7. Đăng ký khóa trong PKI, chứng chỉ và hệ thống xác minh

### 7.1. CSR và quyền kiểm soát private key

Trong **PKI (Public Key Infrastructure)**, một bên có thể tạo **Certificate Signing Request (CSR)** chứa public key và thông tin đề nghị cấp chứng chỉ. CSR thường mang chữ ký để chứng minh khả năng sử dụng private key theo định dạng áp dụng. Tuy nhiên:

- **CSR hợp lệ không tự chứng minh danh tính của chủ thể**: CA/RA vẫn phải xác minh tên miền, tổ chức, người dùng hoặc workload theo chính sách.
- CA ký **chứng chỉ** sau khi các điều kiện phát hành đáp ứng; việc đăng ký key trong nội bộ và việc cấp chứng chỉ là các thao tác khác nhau.
- Bên nhận sau đó cần kiểm tra **chuỗi tin cậy, định danh, mục đích, thời hạn và trạng thái thu hồi** theo giao thức.
- Trong mTLS, chứng chỉ client xác thực workload nhưng **không thay thế authorization** đối với tenant hoặc dữ liệu.

### 7.2. Đăng ký khóa JWT/JWKS

Một dịch vụ phát hành token có thể đăng ký public key ký với key ID, thuật toán và issuer, sau đó công bố qua **JWKS**. Bên xác minh phải ghim **issuer và nguồn JWKS tin cậy**, áp allowlist thuật toán và kiểm tra token audience/expiry.

**Không tin thuật toán hoặc URL tải khóa chỉ vì chúng xuất hiện trong JWT do client gửi.** Kẻ tấn công có thể cung cấp một public key tự tạo và một chữ ký hợp lệ dưới khóa đó; nếu verifier không gắn khóa với đúng issuer, bản ghi đăng ký không có giá trị phòng vệ.

### 7.3. Key attestation và key custody

Trong hệ thống dùng HSM hoặc phần cứng an toàn, một số sản phẩm cung cấp **key attestation** hoặc bằng chứng về việc khóa được tạo/lưu trong một ranh giới cụ thể. Khi có nhu cầu tuân thủ, registry có thể liên kết bản ghi key với tham chiếu attestation đã được xác minh theo trust anchor phù hợp.

**Attestation không phải một phép chứng minh chung cho mọi loại thiết bị.** Phải kiểm tra loại bằng chứng, chain tin cậy, thời điểm, subject key và chính sách nhà cung cấp. Không suy luận từ tên thiết bị hay metadata tự khai rằng khóa chắc chắn non-exportable.

## 8. Trạng thái đăng ký và vòng đời khóa

Không có một tập trạng thái duy nhất bắt buộc cho mọi KMS. Một hệ thống có thể thiết kế các trạng thái **minh họa**:

| Trạng thái | Ý nghĩa | Thao tác thường cho phép |
| --- | --- | --- |
| **CREATED / IMPORT_PENDING** | Khóa vừa được tạo hoặc đang chờ hoàn tất nhập vật liệu. | Bổ sung dữ liệu nhập và kiểm tra; chưa dùng xử lý production. |
| **REGISTERED** | Registry đã có định danh, metadata và bằng chứng tối thiểu. | Tra cứu/kiểm tra; có thể chờ phê duyệt. |
| **ACTIVE** | Khóa đã đáp ứng điều kiện sử dụng theo policy. | Các phép SIGN/VERIFY/ENCRYPT/DECRYPT/WRAP/UNWRAP được cấp riêng tùy key usage. |
| **SUSPENDED / DISABLED** | Tạm ngừng một số hoặc toàn bộ quyền sử dụng. | Tra cứu/audit; các phép mật mã theo chính sách bị chặn. |
| **RETIRED** | Ngừng sử dụng cho hoạt động tạo mới, có thể vẫn cần đọc/verify lịch sử. | VERIFY hoặc DECRYPT cũ nếu được phép. |
| **REVOKED / COMPROMISED** | Khóa không còn đáng tin theo phạm vi và thời điểm xác định. | Hạn chế/từ chối theo policy và quy trình sự cố. |
| **PENDING_DELETION / DESTROYED** | Đang chờ hủy hoặc đã hủy vật liệu khóa theo bằng chứng. | Chỉ các thao tác kiểm toán/metadata còn phù hợp; không dùng mật mã khi khóa đã hủy. |

Đây là mô hình **giải thích khái niệm**, không phải trạng thái được trả về bởi bất kỳ KMS nào. **REVOKED** đối với chứng chỉ/public key có thể có ý nghĩa khác với **DISABLED** đối với key material trong KMS. Không tự map chúng thành cùng một cờ boolean.

~~~mermaid
flowchart LR
    CREATED["CREATED / IMPORT_PENDING"] --> REGISTERED["REGISTERED"]
    REGISTERED --> APPROVED{"Đủ phê duyệt?"}
    APPROVED -->|Có| ACTIVE["ACTIVE"]
    APPROVED -->|Chưa| REGISTERED
    ACTIVE --> ROTATE["Tạo và đăng ký key version mới"]
    ROTATE --> RETIRED["RETIRED: key cũ"]
    ACTIVE --> DISABLED["DISABLED / REVOKED"]
    RETIRED --> DESTROY["Destroy khi không còn phụ thuộc"]
    DISABLED --> DESTROY
~~~

**Quy tắc thiết kế:** Đăng ký và kích hoạt nên là **hai quyết định có thể kiểm toán riêng** khi mức rủi ro yêu cầu. Không tự động kích hoạt khóa import vào production chỉ vì kiểm tra định dạng đã thành công.

## 9. Tình huống thực tế: đăng ký khóa ký sự kiện Payment Service

Một hệ thống gồm **Payment Service**, **Ledger Service** và một **Key Registry/KMS** trung tâm:

### 9.1. Sinh và đăng ký

1. Đội bảo mật cấp quyền cho Payment Service tạo **Ed25519 signing key** chỉ trong môi trường production.
2. Private key được sinh trong KMS/HSM nếu hệ thống hỗ trợ thuật toán và chính sách; hoặc sinh ở môi trường tin cậy và bảo vệ theo cơ chế đã duyệt.
3. Payment Service gửi yêu cầu đăng ký **public key**, key ID/reference, mục đích **PAYMENT_EVENT_SIGNING** và owner là danh tính workload được xác thực.
4. Registry kiểm tra policy; dùng PoP, bằng chứng KMS hoặc chứng chỉ theo yêu cầu. Nếu cần phê duyệt, lưu bản ghi ở **REGISTERED**.
5. Quản trị viên được ủy quyền phê duyệt; hệ thống cập nhật trạng thái **ACTIVE** và công bố public key qua registry/JWKS đáng tin.
6. Ledger Service nhận key version mới từ nguồn tin cậy và kiểm tra thuật toán/issuer/trust trước khi Verify.

### 9.2. Sử dụng và xoay vòng

1. Payment Service chỉ dùng private key **S1** để ký những sự kiện được cho phép; KMS kiểm tra **quyền SIGN**.
2. Mỗi sự kiện chứa key ID, version, issuer, audience, transaction ID, tenant và thông tin chống replay trong dữ liệu được ký theo giao thức.
3. Ledger Service dùng public key S1 đã đăng ký, Verify chữ ký, rồi **kiểm tra quyền nghiệp vụ và event ID** trước khi ghi sổ.
4. Khi cần rotate, hệ thống tạo **S2**, đăng ký/kiểm tra/duyệt và **công bố public key S2 trước** khi chuyển luồng ký mới.
5. Trong cửa sổ chuyển tiếp, hệ thống có thể giữ S1 để **xác minh sự kiện cũ còn hợp lệ**, không cho tạo chữ ký mới sau thời điểm retire.
6. Khi S1 bị lộ, registry cập nhật trạng thái, trust policy và thông báo consumer; cần điều tra mọi chữ ký/sự kiện có thể bị giả trong khoảng ảnh hưởng.

**Không cần private key S1 để xác minh chữ ký lịch sử** về mặt mật mã; cần public key đáng tin và chính sách/bằng chứng thời gian phù hợp. Ngược lại, nếu S1 là private key dùng **giải mã** dữ liệu lịch sử thì hủy sớm có thể khiến dữ liệu không thể khôi phục.

### 9.3. Nếu key registry bị xâm nhập?

Kẻ tấn công có quyền sửa mapping từ Payment Service sang public key của họ có thể khiến verifier chấp nhận chữ ký giả nếu hệ thống **mù quáng tin bản ghi hiện tại**. Do đó registry là **thành phần thuộc ranh giới tin cậy**, cần:

- Phân quyền ghi chặt, phê duyệt thay public key/owner và separation of duties.
- Nhật ký bất biến theo khả năng nền tảng, cảnh báo thay thế fingerprint hoặc trust anchor.
- Public key/chứng chỉ có nguồn tin cậy và đối soát phiên bản.
- Cơ chế consumer nhận **thay đổi trust được kiểm soát**, không tự chấp nhận mọi key mới xuất hiện.
- Phương án rollback trust policy có kiểm soát và xác minh an toàn các bản ghi từng được cấp.

## 10. Rủi ro, kiểm soát truy cập và kiểm toán

| Sai lầm | Hậu quả | Cách kiểm soát |
| --- | --- | --- |
| Coi đăng ký public key đồng nghĩa xác thực danh tính | Attacker đăng ký khóa giả dưới tên service khác. | Xác thực caller, owner mapping và PoP/chứng chỉ khi cần. |
| Chỉ so fingerprint mà không biết nguồn khóa | Không chứng minh public key thuộc đúng owner. | Trust anchor, quy trình phê duyệt và audit đăng ký. |
| Cho caller tự chọn quyền SIGN/DECRYPT/UNWRAP | Leo thang đặc quyền dùng khóa. | Policy và key usage phía server, tách quyền quản trị/sử dụng. |
| Import secret key dạng rõ qua endpoint chung | Lộ key material trong đường truyền, log hoặc bộ nhớ. | Dùng cơ chế nhập khóa do KMS/HSM hỗ trợ, wrapped transfer và kênh an toàn. |
| Lưu private key trong key registry để tiện truy vấn | Tăng bề mặt lộ bí mật và nhầm phạm vi. | Registry giữ metadata/reference; private key ở KMS/HSM hoặc kho chuyên dụng. |
| Alias thay đổi nhưng không lưu phiên bản khóa | Không unwrap/giải mã được bản mã lịch sử. | Lưu key ID + key version/KEK reference theo ciphertext. |
| Bỏ bước phê duyệt trước ACTIVE | Khóa chưa được xác thực được dùng production. | Registration gate và activation policy riêng. |
| PoP challenge dùng lại nhiều lần | Replay hoặc gắn khóa vào ngữ cảnh sai. | Challenge mới, TTL, dùng một lần và ràng buộc owner/purpose. |
| Không quản lý duplicate fingerprint | Cùng khóa xuất hiện ở nhiều tenant hoặc service. | Kiểm tra trùng lặp, chính sách chia sẻ và cảnh báo rủi ro. |
| Không theo dõi key dependencies | Hủy KEK hoặc DEK khi còn dữ liệu cần giải mã. | Kiểm kê wrapped DEK, bản mã, backup và retention. |
| Không đưa registry vào threat model | Kẻ tấn công thay trust mapping để hợp thức hóa chữ ký giả. | Least privilege, phân quyền thay đổi, audit và kiểm tra nguồn trust. |
| Quên cập nhật consumer khi rotate/revoke | Dịch vụ nhận từ chối khóa mới hoặc tiếp tục tin khóa đã lộ. | Cơ chế phân phối trust có version và giám sát. |
| Tin rằng khóa non-exportable không thể bị lạm dụng | Kẻ chiếm quyền API Sign/Decrypt vẫn thao tác trái phép. | IAM, giới hạn quyền sử dụng và audit lệnh nhạy cảm. |
| Log secret hoặc nguyên request chứa private key | Lộ vật liệu khóa ra hệ thống giám sát. | Chỉ ghi key ID/fingerprint/actor/quyết định không nhạy cảm. |

### 10.1. Những sự kiện audit cần ghi

- **RegisterRequested:** actor/workload đã xác thực, owner/tenant, key type, usage, request ID, thời điểm.
- **ProofVerified / ProofRejected:** phương pháp kiểm tra, kết quả, reason code; không log secret/challenge thô nếu không cần.
- **KeyRegistered:** key ID, version, fingerprint của public key, nguồn gốc/định danh KMS, policy version.
- **KeyApproved / Activated:** ai phê duyệt, quyền nào được mở, thời điểm và bằng chứng.
- **KeyMetadataChanged:** giá trị metadata nhạy cảm được cập nhật theo quy trình nào, bản cũ/mới và lý do.
- **KeyRotated / Retired / Revoked / Destroyed:** tham chiếu khóa liên quan, phụ thuộc, quyết định và kết quả xác minh.

Đặc biệt với thay đổi **owner, trusted signer, key usage, KEK mapping hoặc trạng thái Active**, nên thiết lập giám sát, phân tách nhiệm vụ và cơ chế truy xuất lịch sử để điều tra sự cố.

## 11. Checklist thiết kế key registration

Trước khi cho một khóa được đăng ký và sử dụng, trả lời:

1. **Nguồn gốc:** khóa được sinh ở đâu? Có đủ entropy, thuật toán và mức bảo vệ phù hợp không?
2. **Danh tính:** ai yêu cầu đăng ký, owner/tenant nào và nguồn xác thực caller là gì?
3. **Phạm vi:** khóa dùng cho SIGN, VERIFY, ENCRYPT, DECRYPT, WRAP, UNWRAP hay MAC?
4. **Biểu diễn:** public key SPKI/JWK, chứng chỉ, encoding và key size/curve đã được validate chưa?
5. **Trust:** proof of possession, chứng chỉ hoặc attestation nào được yêu cầu? Đã xác minh đúng trust anchor chưa?
6. **Secret handling:** private/symmetric key material có được giữ ngoài registry, tránh log và chuyển qua cơ chế an toàn không?
7. **Định danh:** key ID, alias và phiên bản vật liệu khóa được quản lý thế nào?
8. **Xung đột:** xử lý fingerprint trùng, request lặp, concurrent registration và tenant isolation thế nào?
9. **Phê duyệt:** ai được REGISTER, ai được ACTIVATE và ai được CHANGE POLICY?
10. **Vòng đời:** khi nào rotate/retire/revoke/destroy; trạng thái có ảnh hưởng đúng quyền API không?
11. **Phụ thuộc:** DEK nào được bọc bởi KEK này; bản mã, certificate, release hoặc backup nào phụ thuộc?
12. **Consumer:** các dịch vụ có cập nhật trust khi key mới/thu hồi chưa; có kiểm tra issuer/audience/purpose không?
13. **Kiểm toán:** có thể truy ra ai đăng ký, thay metadata, cấp quyền và phê duyệt sử dụng khóa không?
14. **Sự cố:** có thể nhanh chóng vô hiệu hóa key, thu hồi trust, khôi phục mapping và đánh giá phạm vi ảnh hưởng không?

## 12. Câu hỏi tự kiểm tra

1. **Register key** khác **generate key** và **activate key** ở đâu?
2. Vì sao một public key nằm trong registry chưa đủ để chứng minh nó thuộc đúng Payment Service?
3. **Proof of Possession** chứng minh được gì, và **không chứng minh được** điều gì về danh tính người đăng ký?
4. Key ID, alias, fingerprint và chứng chỉ X.509 có giống nhau không?
5. Khi đăng ký DEK/KEK, vì sao không nên lưu DEK dạng rõ trong registry?
6. Quy trình **BYOK/import key material** cần bảo vệ khác đăng ký public key như thế nào?
7. Vì sao registry nên phân biệt trạng thái REGISTERED và ACTIVE ở môi trường có rủi ro cao?
8. Cần lưu thông tin phiên bản nào để dữ liệu AES-GCM vẫn giải mã được sau khi rotate KEK?
9. Một attacker có quyền sửa public key mapping trong registry có thể gây hậu quả gì?
10. Khi chuyển signing key S1 sang S2, vì sao phải công bố public key S2 trước khi ký mới?
11. Hủy private key ký có làm cho chữ ký số lịch sử không còn xác minh được bằng public key không?
12. Nếu một HSM key non-exportable, liệu dịch vụ có quyền gọi Sign không bị kiểm soát có thể lạm dụng khóa không?
13. Đối với ephemeral ECDHE private keys, có nhất thiết ghi cả key material vào registry bền vững không?
14. Những trường metadata/audit nào giúp điều tra một thao tác đăng ký khóa gian lận?

**Ghi nhớ:** **Register key** là bước đưa khóa vào một **hệ thống quản lý và tin cậy có kiểm soát**, không chỉ là lưu một định danh. Để đăng ký an toàn cần **xác thực caller, kiểm tra nguồn gốc và thuật toán, gắn owner/usage/phiên bản, xác minh quyền sở hữu hoặc nguồn khóa khi thích hợp, tách đăng ký khỏi kích hoạt, phân quyền và kiểm toán**. Một key registry tốt giúp KMS/HSM, chữ ký số, mã hóa đối xứng và envelope encryption vận hành nhất quán trong suốt vòng đời khóa, đồng thời giảm rủi ro sử dụng nhầm khóa, giả mạo danh tính và mất dữ liệu khi thu hồi hoặc hủy khóa.
