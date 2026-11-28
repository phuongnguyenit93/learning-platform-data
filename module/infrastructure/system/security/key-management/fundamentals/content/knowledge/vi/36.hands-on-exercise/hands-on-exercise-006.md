# Ký và xác minh dữ liệu

Trong chương **Thực hành tổng hợp** của module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, bài thực hành này hướng dẫn tạo cặp khóa bất đối xứng, ký một payload và xác minh chữ ký số bằng public key. Người học sẽ xây dựng một signature envelope có version, algorithm, key ID, tenant reference và purpose; các metadata này được đưa vào nội dung ký để ngăn việc tráo chữ ký giữa tenant hoặc mục đích sử dụng.

**Lưu ý:** Bài lab dùng Java 17 và Ed25519 để tập trung vào quy trình. Đây là môi trường học tập với key file cục bộ. Trong production, private signing key cần được bảo vệ bởi KMS/HSM hoặc key store có kiểm soát; public key phải được xác thực nguồn gốc qua trust store, certificate chain hoặc registry đáng tin cậy.

## 1. Mục tiêu thực hành

Sau bài lab, người học có thể:

- Phân biệt ký số với mã hóa dữ liệu.
- Tạo key pair Ed25519 bằng Java Cryptography Architecture (JCA).
- Lưu private key theo định dạng PKCS#8 và public key theo X.509 SubjectPublicKeyInfo.
- Ký payload dưới dạng detached signature.
- Xác minh chữ ký bằng public key đã tin cậy.
- Ràng buộc key ID, tenant, purpose và format version vào dữ liệu được ký.
- Phát hiện payload hoặc chữ ký bị sửa đổi.
- Nhận biết rủi ro khi dùng sai public key hoặc sai tenant context.
- Hiểu cách rotation signing key và giữ public key cũ để xác minh dữ liệu lịch sử.
- Xác định bằng chứng audit cần lưu mà không làm lộ private key hoặc plaintext nhạy cảm.

## 2. Bối cảnh bài lab

Một dịch vụ hóa đơn cần ký dữ liệu phê duyệt để hệ thống khác có thể xác minh rằng nội dung nhận được chưa bị sửa kể từ khi ký và chữ ký được tạo bởi private key tương ứng với public key đã đăng ký.

Payload mẫu:

~~~text
invoice_id=INV-2026-001
amount=125000
currency=VND
recipient=customer-42
~~~

Thông tin ngoài payload:

| Trường | Giá trị minh họa | Vai trò |
|---|---|---|
| keyId | signer-2026-v1 | Chọn public key trong trusted key registry |
| tenantRef | tenant-42 | Ràng buộc chữ ký với tenant |
| purpose | invoice-approval | Ngăn dùng chữ ký cho mục đích khác |
| formatVersion | 1 | Xác định cấu trúc signature envelope |
| algorithm | Ed25519 | Xác định thuật toán được phép |

Chữ ký được tạo trên payload bytes cùng các metadata trên. Nếu attacker thay payload, tenant, purpose, key ID hoặc algorithm, bước xác minh phải thất bại hoặc từ chối metadata trước khi xác minh mật mã.

## 3. Kiến thức nền: ký số khác mã hóa

Ký số và mã hóa giải quyết hai mục tiêu khác nhau:

| Cơ chế | Dùng khóa nào? | Mục tiêu |
|---|---|---|
| Digital signature | Private key để ký, public key để verify | Integrity và xác thực nguồn gốc gắn với public key đã tin cậy |
| Asymmetric encryption | Public key để mã hóa, private key để giải mã | Confidentiality |
| Symmetric encryption | Cùng secret key để mã hóa và giải mã | Confidentiality; cần AEAD hoặc MAC để bảo vệ integrity |
| HMAC | Shared secret để tạo và xác minh MAC | Integrity và xác thực giữa các bên cùng giữ secret |

Chữ ký số không che giấu payload. Bất kỳ ai có payload và chữ ký đều có thể thử xác minh bằng public key. Nếu cần confidentiality, phải thiết kế thêm encryption phù hợp.

Chữ ký hợp lệ chứng minh các byte được xác minh phù hợp với private key tương ứng public key đang dùng. Nó không tự chứng minh danh tính pháp lý của người ký. Việc gắn public key với một tổ chức hoặc cá nhân cần certificate, trust registry, key pinning hoặc quy trình cấp phát được kiểm soát.

## 4. Threat model và điều kiện tin cậy

Bài lab xem xét các tình huống:

- Payload bị sửa sau khi ký.
- Signature file bị thay đổi hoặc cắt cụt.
- Dùng public key của tenant khác.
- Dùng signature hợp lệ cho purpose khác.
- Thay key ID trong metadata để đánh lừa key resolver.
- Attacker gửi public key của chính họ cùng payload.
- Ứng dụng chấp nhận algorithm không nằm trong allowlist.
- Private key bị lộ hoặc bị sử dụng trái phép.

Các giả định:

- Public key được lấy từ một nguồn tin cậy đã xác minh độc lập.
- Private key của signer được bảo vệ và chỉ workload được phép mới có thể ký.
- Payload được đọc dưới dạng bytes chính xác, không tự động đổi encoding hoặc newline sau khi ký.
- Verifier kiểm tra tenant và purpose theo trusted context.
- Algorithm được quyết định bởi policy của verifier, không do message tự chọn tùy ý.

Nếu public key được lấy trực tiếp từ signature envelope mà không xác minh nguồn gốc, attacker có thể tự tạo key pair, ký payload giả và gửi public key của họ kèm chữ ký. Chữ ký đó vẫn verify thành công về mặt toán học nhưng không tạo ra trust.

## 5. Chuẩn bị môi trường Java 17

Cần có:

- JDK 17 hoặc mới hơn.
- Terminal có lệnh javac và java.
- Một thư mục làm việc riêng cho bài lab.

Kiểm tra phiên bản:

~~~powershell
java -version
javac -version
~~~

Java 17 có hỗ trợ Ed25519 qua JCA. Trong môi trường enterprise hoặc HSM có chứng nhận riêng, algorithm/provider được phép có thể khác. Luôn đối chiếu crypto policy của tổ chức và khả năng thực tế của provider trước khi chọn thuật toán.

Tạo thư mục mới, ví dụ:

~~~powershell
New-Item -ItemType Directory -Path signing-lab
Set-Location signing-lab
~~~

Không chạy bài lab trong thư mục chứa key production, credential hoặc dữ liệu khách hàng.

## 6. Thiết kế luồng ký và xác minh

Luồng tổng quát:

1. Key administrator hoặc KMS/HSM tạo key pair.
2. Private key được cấp cho signer theo workload identity và purpose.
3. Public key được đăng ký trong trusted key registry cùng key ID, tenant/scope và trạng thái.
4. Signer nhận payload bytes và trusted signing context.
5. Signer tạo canonical signed message gồm domain, version, algorithm, key ID, tenant, purpose và payload.
6. Private key ký signed message.
7. Signature envelope chứa metadata và chữ ký detached được lưu hoặc truyền cùng payload.
8. Verifier lấy public key từ registry tin cậy, kiểm tra metadata và verify.
9. Verifier chỉ chấp nhận dữ liệu nếu policy, context và chữ ký đều hợp lệ.

~~~mermaid
sequenceDiagram
    participant A as Key Admin / KMS
    participant S as Signer
    participant V as Verifier
    participant R as Trusted Key Registry
    A->>A: Generate Ed25519 key pair
    A->>R: Register keyId + public key + scope
    A->>S: Grant sign permission
    S->>S: Build canonical signed bytes
    S->>S: Sign with private key
    S-->>V: Payload + signature envelope
    V->>R: Resolve trusted public key by keyId
    R-->>V: Public key + allowed tenant/purpose
    V->>V: Check metadata and verify signature
    V-->>S: Accept or reject
~~~

Trong production, key administrator, signer và verifier có thể là các service khác nhau. Signer không nên có quyền tự đăng ký public key hoặc tự thay đổi trust policy.

## 7. Định dạng signature envelope

Signature envelope là metadata bao quanh chữ ký detached. Bài lab dùng binary format minh họa với các trường:

| Trường | Ý nghĩa |
|---|---|
| magic | Nhận diện file envelope |
| version | Phiên bản cấu trúc envelope |
| algorithm | Thuật toán chữ ký |
| keyId | Định danh key trong registry |
| tenantRef | Phạm vi tenant |
| purpose | Mục đích ký |
| signature | Chữ ký số |

Payload được lưu riêng. Verifier đọc envelope, kiểm tra các trường metadata theo trusted context rồi dựng lại chính xác signed message.

Các trường algorithm, key ID, tenant, purpose và version cũng được đưa vào signed message. Vì vậy attacker không thể đổi metadata mà vẫn giữ chữ ký hợp lệ. Trong hệ thống thật, cần dùng serialization có version, giới hạn kích thước, kiểm tra encoding và reject trailing bytes hoặc field trùng lặp.

## 8. Canonical signed message và domain separation

Không nên ký một chuỗi được ghép tùy tiện:

~~~text
tenant + purpose + payload
~~~

Nếu không có encoding rõ ràng, các tổ hợp khác nhau có thể tạo cùng chuỗi byte. Ví dụ field boundary không rõ khiến verifier hiểu sai nội dung.

Bài lab dùng length-prefix encoding: mỗi trường có độ dài cố định 4 byte theo big-endian, sau đó là bytes của trường. Signed message gồm:

1. Domain separator riêng cho bài toán ký dữ liệu.
2. Envelope version.
3. Algorithm identifier.
4. Key ID.
5. Tenant reference.
6. Purpose.
7. Payload bytes nguyên gốc.

Domain separation ngăn chữ ký được tạo cho một giao thức bị tái sử dụng nhầm trong giao thức khác. Nếu payload là JSON/XML, signer và verifier phải thống nhất canonicalization hoặc ký đúng raw bytes được lưu. Không parse JSON rồi serialize lại bằng một thứ tự field khác và kỳ vọng chữ ký cũ vẫn hợp lệ.

## 9. Tạo file payload mẫu

Chương trình bên dưới có lệnh sample để tạo payload UTF-8 không BOM. File được tạo theo chế độ CREATE_NEW để tránh vô tình ghi đè dữ liệu đang có.

~~~powershell
java DataSigningLab sample invoice.txt
~~~

Nội dung file được tạo:

~~~text
invoice_id=INV-2026-001
amount=125000
currency=VND
recipient=customer-42
~~~

Không chỉnh sửa file sau khi ký. Một thay đổi nhỏ như thêm newline, đổi encoding hoặc chuẩn hóa Unicode cũng làm bytes khác đi và chữ ký phải không còn hợp lệ.

## 10. Tạo cặp khóa Ed25519

Chạy:

~~~powershell
java DataSigningLab keygen signer-v1.private.pk8.b64 signer-v1.public.spki.b64
~~~

Hai file được tạo:

- signer-v1.private.pk8.b64: private key ở dạng PKCS#8 DER được Base64 hóa.
- signer-v1.public.spki.b64: public key ở dạng X.509 SubjectPublicKeyInfo DER được Base64 hóa.

Private key chỉ dùng cho lab cục bộ. Hạn chế ACL của file, không commit vào Git, không gửi qua chat, không đưa vào log hoặc CI artifact. Trong production, private key nên được tạo/giữ trong KMS/HSM hoặc signing service có policy; ứng dụng chỉ gọi operation sign.

Public key không phải secret, nhưng vẫn cần xác minh nguồn gốc. Đăng ký public key cùng key ID, tenant/scope, purpose, algorithm, thời gian hiệu lực và trạng thái trong trust registry.

## 11. Ký payload

Lệnh ký nhận private key, key ID, tenant reference, purpose, payload và đường dẫn signature envelope:

~~~powershell
java DataSigningLab sign signer-v1.private.pk8.b64 signer-2026-v1 tenant-42 invoice-approval invoice.txt invoice.sig
~~~

Kết quả là file invoice.sig chứa envelope và chữ ký detached. Payload invoice.txt không bị mã hóa hoặc thay đổi.

Signer phải lấy tenant và purpose từ authorization context đã xác thực. Không cho client tự chọn key ID hoặc purpose để ký dữ liệu vượt quyền. Nếu signer ký nhiều loại dữ liệu, mỗi purpose cần policy và domain separation riêng.

## 12. Xác minh chữ ký

Verifier nhận public key đã được tin cậy, expected key ID, tenant, purpose, payload và signature envelope:

~~~powershell
java DataSigningLab verify signer-v1.public.spki.b64 signer-2026-v1 tenant-42 invoice-approval invoice.txt invoice.sig
~~~

Kết quả mong đợi:

~~~text
VALID: signature and signed context match
~~~

Chương trình kiểm tra:

1. Envelope đúng magic và version được hỗ trợ.
2. Algorithm nằm trong allowlist, ở đây chỉ có Ed25519.
3. Key ID khớp key ID mà verifier mong đợi.
4. Tenant và purpose khớp trusted context.
5. Public key được nạp từ file trust đã chọn độc lập.
6. Canonical signed message được dựng lại từ metadata và payload.
7. Signature.verify trả về true.

Chỉ khi tất cả điều kiện đạt mới chấp nhận dữ liệu. Metadata mismatch phải bị từ chối dù chữ ký bytes có thể hợp lệ với một context khác.

## 13. Thử nghiệm sửa payload

Tạo bản payload đã bị sửa:

~~~powershell
java DataSigningLab tamper-payload invoice.txt invoice-tampered.txt
~~~

Lệnh này sao chép bytes gốc rồi nối thêm một dòng amount khác. Xác minh:

~~~powershell
java DataSigningLab verify signer-v1.public.spki.b64 signer-2026-v1 tenant-42 invoice-approval invoice-tampered.txt invoice.sig
~~~

Kết quả mong đợi:

~~~text
INVALID: signature verification failed
~~~

Payload mới có bytes khác payload đã ký. Ed25519 phải trả về false. Ứng dụng không được bỏ qua kết quả false, không được tiếp tục xử lý hóa đơn và không được thử một public key bất kỳ cho tới khi có key verify thành công.

## 14. Thử nghiệm sửa chữ ký

Tạo envelope có một bit trong signature bị đảo:

~~~powershell
java DataSigningLab tamper-signature invoice.sig invoice-signature-tampered.sig
~~~

Xác minh bằng payload gốc:

~~~powershell
java DataSigningLab verify signer-v1.public.spki.b64 signer-2026-v1 tenant-42 invoice-approval invoice.txt invoice-signature-tampered.sig
~~~

Kết quả mong đợi là INVALID. Test này chứng minh verifier kiểm tra signature bytes thay vì chỉ kiểm tra file envelope tồn tại hoặc metadata có vẻ hợp lệ.

## 15. Thử nghiệm sai public key

Tạo key pair thứ hai:

~~~powershell
java DataSigningLab keygen attacker.private.pk8.b64 attacker.public.spki.b64
~~~

Dùng public key thứ hai để verify signature được tạo bởi signer-v1:

~~~powershell
java DataSigningLab verify attacker.public.spki.b64 signer-2026-v1 tenant-42 invoice-approval invoice.txt invoice.sig
~~~

Kết quả mong đợi là INVALID. Chữ ký được tạo bằng private key thứ nhất không verify với public key không tương ứng.

Lưu ý: nếu attacker gửi cả payload, signature và public key của họ, phép verify có thể thành công. Do đó verifier phải xác minh public key được lấy từ trusted registry/certificate chain, không tin public key do người gửi tự đính kèm.

## 16. Thử nghiệm sai tenant hoặc purpose

Giữ payload, signature và public key đúng nhưng thay expected tenant:

~~~powershell
java DataSigningLab verify signer-v1.public.spki.b64 signer-2026-v1 tenant-99 invoice-approval invoice.txt invoice.sig
~~~

Hoặc thay purpose:

~~~powershell
java DataSigningLab verify signer-v1.public.spki.b64 signer-2026-v1 tenant-42 payment-release invoice.txt invoice.sig
~~~

Kết quả phải bị từ chối vì metadata trong envelope không khớp trusted context. Nếu metadata bị thay trực tiếp trong envelope, chữ ký cũng phải thất bại vì tenant và purpose đã được đưa vào signed message.

## 17. Thử nghiệm sai key ID

Chạy verify với key ID khác:

~~~powershell
java DataSigningLab verify signer-v1.public.spki.b64 signer-2026-v2 tenant-42 invoice-approval invoice.txt invoice.sig
~~~

Verifier phải từ chối. Trong production, key ID là lookup reference, không phải bằng chứng trust. Registry phải kiểm tra key ID thuộc đúng tenant, purpose, algorithm và thời hạn hiệu lực.

## 18. Thử nghiệm algorithm không được hỗ trợ

Bài lab chỉ cho phép Ed25519. Nếu envelope khai báo algorithm khác, parser/verifier phải reject thay vì tự chọn provider hoặc fallback.

Trong production:

- Algorithm allowlist do server policy quản lý.
- Không tin trường algorithm do client gửi.
- Không chấp nhận downgrade sang scheme yếu hơn.
- Key type phải tương thích với algorithm đã chọn.
- Algorithm, key ID, purpose và format version phải được ràng buộc vào signed bytes.
- Migration sang algorithm mới cần versioning và dual-read có thời hạn.

Ed25519 phù hợp cho bài lab và nhiều hệ thống hiện đại, nhưng không phải lựa chọn được chấp thuận trong mọi môi trường regulated hoặc mọi HSM/FIPS profile. Hãy chọn thuật toán theo tiêu chuẩn và provider thực tế.

## 19. Chương trình Java hoàn chỉnh

Lưu nội dung sau thành DataSigningLab.java:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import java.util.Base64;

public final class DataSigningLab {
    private static final int MAGIC = 0x53494731; // SIG1
    private static final int ENVELOPE_VERSION = 1;
    private static final String ALGORITHM = "Ed25519";
    private static final String DOMAIN =
            "SECURITY_KEY_MANAGEMENT_FUNDAMENTALS/DATA-SIGNATURE";
    private static final int MAX_PAYLOAD_BYTES = 10 * 1024 * 1024;
    private static final int MAX_ENVELOPE_BYTES = 64 * 1024;
    private static final int MAX_TEXT_FIELD_BYTES = 256;
    private static final int ED25519_SIGNATURE_BYTES = 64;

    private static final byte[] SAMPLE_PAYLOAD = (
            "invoice_id=INV-2026-001\n" +
            "amount=125000\n" +
            "currency=VND\n" +
            "recipient=customer-42\n"
    ).getBytes(StandardCharsets.UTF_8);

    private record Envelope(
            int version,
            String algorithm,
            String keyId,
            String tenantRef,
            String purpose,
            byte[] signature) {}

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            usage();
            throw new IllegalArgumentException("Missing command");
        }

        switch (args[0]) {
            case "sample" -> {
                requireArgs(args, 2);
                writeNew(Path.of(args[1]), SAMPLE_PAYLOAD);
                System.out.println("Created sample payload: " + args[1]);
            }
            case "keygen" -> {
                requireArgs(args, 3);
                generateKeyPair(Path.of(args[1]), Path.of(args[2]));
            }
            case "sign" -> {
                requireArgs(args, 7);
                sign(
                        Path.of(args[1]),
                        args[2],
                        args[3],
                        args[4],
                        Path.of(args[5]),
                        Path.of(args[6]));
            }
            case "verify" -> {
                requireArgs(args, 7);
                verify(
                        Path.of(args[1]),
                        args[2],
                        args[3],
                        args[4],
                        Path.of(args[5]),
                        Path.of(args[6]));
            }
            case "tamper-payload" -> {
                requireArgs(args, 3);
                tamperPayload(Path.of(args[1]), Path.of(args[2]));
            }
            case "tamper-signature" -> {
                requireArgs(args, 3);
                tamperSignature(Path.of(args[1]), Path.of(args[2]));
            }
            default -> {
                usage();
                throw new IllegalArgumentException("Unknown command: " + args[0]);
            }
        }
    }

    private static void generateKeyPair(
            Path privatePath,
            Path publicPath) throws GeneralSecurityException, IOException {

        if (privatePath.equals(publicPath)) {
            throw new IOException("Private and public key paths must differ");
        }
        if (Files.exists(privatePath) || Files.exists(publicPath)) {
            throw new IOException("Refusing to overwrite an existing key file");
        }

        KeyPairGenerator generator = KeyPairGenerator.getInstance(ALGORITHM);
        KeyPair pair = generator.generateKeyPair();

        byte[] privateDer = pair.getPrivate().getEncoded();
        byte[] publicDer = pair.getPublic().getEncoded();
        try {
            byte[] privateText = (
                    Base64.getEncoder().encodeToString(privateDer) + "\n"
            ).getBytes(StandardCharsets.US_ASCII);
            byte[] publicText = (
                    Base64.getEncoder().encodeToString(publicDer) + "\n"
            ).getBytes(StandardCharsets.US_ASCII);

            try {
                writeNew(privatePath, privateText);
            } finally {
                Arrays.fill(privateText, (byte) 0);
            }
            writeNew(publicPath, publicText);
        } finally {
            Arrays.fill(privateDer, (byte) 0);
            Arrays.fill(publicDer, (byte) 0);
        }

        System.out.println("Generated Ed25519 key pair");
        System.out.println("Private key (lab only): " + privatePath);
        System.out.println("Public key: " + publicPath);
    }

    private static void sign(
            Path privatePath,
            String keyId,
            String tenantRef,
            String purpose,
            Path payloadPath,
            Path envelopePath) throws Exception {

        requireText(keyId, "keyId");
        requireText(tenantRef, "tenantRef");
        requireText(purpose, "purpose");

        PrivateKey privateKey = loadPrivateKey(privatePath);
        byte[] payload = readPayload(payloadPath);
        byte[] signedMessage = canonicalSignedMessage(
                ENVELOPE_VERSION,
                ALGORITHM,
                keyId,
                tenantRef,
                purpose,
                payload);

        byte[] signatureBytes;
        try {
            Signature signer = Signature.getInstance(ALGORITHM);
            signer.initSign(privateKey);
            signer.update(signedMessage);
            signatureBytes = signer.sign();
        } finally {
            Arrays.fill(signedMessage, (byte) 0);
        }

        Envelope envelope = new Envelope(
                ENVELOPE_VERSION,
                ALGORITHM,
                keyId,
                tenantRef,
                purpose,
                signatureBytes);
        try {
            writeEnvelope(envelopePath, envelope);
        } finally {
            Arrays.fill(signatureBytes, (byte) 0);
        }

        System.out.println("Signed payload: " + payloadPath);
        System.out.println("Signature envelope: " + envelopePath);
        System.out.println("keyId=" + keyId + ", tenantRef=" + tenantRef
                + ", purpose=" + purpose + ", algorithm=" + ALGORITHM);
    }

    private static void verify(
            Path publicPath,
            String expectedKeyId,
            String expectedTenantRef,
            String expectedPurpose,
            Path payloadPath,
            Path envelopePath) throws Exception {

        requireText(expectedKeyId, "expectedKeyId");
        requireText(expectedTenantRef, "expectedTenantRef");
        requireText(expectedPurpose, "expectedPurpose");

        Envelope envelope = readEnvelope(envelopePath);
        if (envelope.version() != ENVELOPE_VERSION) {
            throw new SecurityException("Unsupported envelope version");
        }
        if (!ALGORITHM.equals(envelope.algorithm())) {
            throw new SecurityException("Algorithm is not allowlisted");
        }
        if (!expectedKeyId.equals(envelope.keyId())) {
            throw new SecurityException("Unexpected key ID");
        }
        if (!expectedTenantRef.equals(envelope.tenantRef())) {
            throw new SecurityException("Tenant context mismatch");
        }
        if (!expectedPurpose.equals(envelope.purpose())) {
            throw new SecurityException("Purpose mismatch");
        }
        if (envelope.signature().length != ED25519_SIGNATURE_BYTES) {
            throw new SecurityException("Invalid Ed25519 signature length");
        }

        // The caller supplies a public key from a trusted source.
        PublicKey publicKey = loadPublicKey(publicPath);
        byte[] payload = readPayload(payloadPath);
        byte[] signedMessage = canonicalSignedMessage(
                envelope.version(),
                envelope.algorithm(),
                envelope.keyId(),
                envelope.tenantRef(),
                envelope.purpose(),
                payload);

        boolean valid;
        try {
            Signature verifier = Signature.getInstance(ALGORITHM);
            verifier.initVerify(publicKey);
            verifier.update(signedMessage);
            valid = verifier.verify(envelope.signature());
        } finally {
            Arrays.fill(signedMessage, (byte) 0);
        }

        if (valid) {
            System.out.println("VALID: signature and signed context match");
        } else {
            System.out.println("INVALID: signature verification failed");
            System.exit(2);
        }
    }

    private static byte[] canonicalSignedMessage(
            int version,
            String algorithm,
            String keyId,
            String tenantRef,
            String purpose,
            byte[] payload) throws IOException {

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            writeString(out, DOMAIN);
            out.writeInt(version);
            writeString(out, algorithm);
            writeString(out, keyId);
            writeString(out, tenantRef);
            writeString(out, purpose);
            writeBytes(out, payload);
        }
        return bytes.toByteArray();
    }

    private static void writeEnvelope(
            Path path,
            Envelope envelope) throws IOException {

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeInt(MAGIC);
            out.writeInt(envelope.version());
            writeString(out, envelope.algorithm());
            writeString(out, envelope.keyId());
            writeString(out, envelope.tenantRef());
            writeString(out, envelope.purpose());
            writeBytes(out, envelope.signature());
        }
        writeNew(path, bytes.toByteArray());
    }

    private static Envelope readEnvelope(Path path) throws IOException {
        long size = Files.size(path);
        if (size <= 0 || size > MAX_ENVELOPE_BYTES) {
            throw new IOException("Invalid envelope size");
        }

        byte[] encoded = Files.readAllBytes(path);
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(encoded))) {
            if (in.readInt() != MAGIC) {
                throw new IOException("Invalid signature envelope magic");
            }

            int version = in.readInt();
            String algorithm = readString(in, 64);
            String keyId = readString(in, 256);
            String tenantRef = readString(in, 256);
            String purpose = readString(in, 256);
            byte[] signature = readBytes(in, 512);

            if (in.read() != -1) {
                throw new IOException("Trailing bytes in signature envelope");
            }
            return new Envelope(
                    version, algorithm, keyId, tenantRef, purpose, signature);
        }
    }

    private static void writeString(
            DataOutputStream out,
            String value) throws IOException {
        writeBytes(out, value.getBytes(StandardCharsets.UTF_8));
    }

    private static String readString(
            DataInputStream in,
            int maxBytes) throws IOException {
        byte[] value = readBytes(in, maxBytes);
        try {
            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(value))
                    .toString();
        } catch (CharacterCodingException e) {
            throw new IOException("Invalid UTF-8 metadata", e);
        }
    }

    private static void writeBytes(
            DataOutputStream out,
            byte[] value) throws IOException {
        out.writeInt(value.length);
        out.write(value);
    }

    private static byte[] readBytes(
            DataInputStream in,
            int maxBytes) throws IOException {
        int length = in.readInt();
        if (length < 0 || length > maxBytes) {
            throw new IOException("Invalid field length");
        }
        byte[] value = new byte[length];
        in.readFully(value);
        return value;
    }

    private static PrivateKey loadPrivateKey(Path path)
            throws IOException, GeneralSecurityException {
        String text = Files.readString(path, StandardCharsets.US_ASCII).trim();
        byte[] encoded = Base64.getMimeDecoder().decode(text);
        try {
            KeyFactory factory = KeyFactory.getInstance(ALGORITHM);
            return factory.generatePrivate(new PKCS8EncodedKeySpec(encoded));
        } finally {
            Arrays.fill(encoded, (byte) 0);
        }
    }

    private static PublicKey loadPublicKey(Path path)
            throws IOException, GeneralSecurityException {
        String text = Files.readString(path, StandardCharsets.US_ASCII).trim();
        byte[] encoded = Base64.getMimeDecoder().decode(text);
        return KeyFactory.getInstance(ALGORITHM)
                .generatePublic(new X509EncodedKeySpec(encoded));
    }

    private static byte[] readPayload(Path path) throws IOException {
        long size = Files.size(path);
        if (size < 0 || size > MAX_PAYLOAD_BYTES) {
            throw new IOException("Payload exceeds lab size limit");
        }
        return Files.readAllBytes(path);
    }

    private static void tamperPayload(
            Path source,
            Path destination) throws IOException {
        byte[] original = readPayload(source);
        byte[] suffix = "\namount=999999\n".getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        output.write(original);
        output.write(suffix);
        writeNew(destination, output.toByteArray());
        System.out.println("Created modified payload: " + destination);
    }

    private static void tamperSignature(
            Path source,
            Path destination) throws IOException {
        Envelope envelope = readEnvelope(source);
        byte[] modified = envelope.signature().clone();
        if (modified.length == 0) {
            throw new IOException("Empty signature");
        }
        modified[0] ^= 0x01;
        writeEnvelope(destination, new Envelope(
                envelope.version(),
                envelope.algorithm(),
                envelope.keyId(),
                envelope.tenantRef(),
                envelope.purpose(),
                modified));
        Arrays.fill(modified, (byte) 0);
        System.out.println("Created modified signature: " + destination);
    }

    private static void requireText(String value, String field) {
        if (value == null || value.isBlank()
                || value.getBytes(StandardCharsets.UTF_8).length
                        > MAX_TEXT_FIELD_BYTES) {
            throw new IllegalArgumentException("Invalid " + field);
        }
    }

    private static void writeNew(Path path, byte[] bytes) throws IOException {
        Files.write(
                path,
                bytes,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE);
    }

    private static void requireArgs(String[] args, int expected) {
        if (args.length != expected) {
            usage();
            throw new IllegalArgumentException("Wrong number of arguments");
        }
    }

    private static void usage() {
        System.out.println("Commands:");
        System.out.println("  sample <payload-file>");
        System.out.println("  keygen <private-pkcs8-b64> <public-spki-b64>");
        System.out.println("  sign <private-key> <key-id> <tenant-ref> <purpose>"
                + " <payload-file> <envelope-file>");
        System.out.println("  verify <public-key> <expected-key-id> <expected-tenant>"
                + " <expected-purpose> <payload-file> <envelope-file>");
        System.out.println("  tamper-payload <source> <destination>");
        System.out.println("  tamper-signature <source> <destination>");
    }
}
~~~

## 20. Biên dịch và chạy bài lab

Biên dịch chương trình:

~~~powershell
javac DataSigningLab.java
~~~

Sau khi biên dịch, thực hiện các lệnh theo thứ tự ở mục 9–18: tạo payload, tạo key pair v1, ký, xác minh, rồi chạy các negative test. Các file đầu ra được tạo bằng chế độ CREATE_NEW để tránh ghi đè key hoặc chữ ký đã có. Nếu cần chạy lại từ đầu, hãy dùng một thư mục lab mới hoặc tên file đầu ra mới; không xóa private key cần giữ cho bài rotation.

Các lệnh verify với payload bị sửa, chữ ký bị sửa hoặc public key không tương ứng đều phải thất bại. Chương trình trả exit code 2 khi chữ ký không hợp lệ; đây là kết quả test dự kiến, không phải lý do để bỏ qua lỗi trong ứng dụng.

## 21. Kết quả mong đợi

| Tình huống | Kết quả |
|---|---|
| Payload gốc, public key đúng, context đúng | VALID |
| Payload bị nối thêm dữ liệu | INVALID |
| Signature bị đổi một bit | INVALID |
| Public key của key pair khác | INVALID |
| Expected key ID không khớp | Reject metadata |
| Tenant reference không khớp | Reject metadata |
| Purpose không khớp | Reject metadata |
| Envelope version không hỗ trợ | Reject envelope |
| Algorithm không nằm trong allowlist | Reject envelope |
| Envelope có trailing bytes hoặc field length bất thường | Reject envelope |

Verifier không được trả plaintext hay thực hiện side effect nghiệp vụ trước khi chữ ký và context được xác minh. Trong lab, payload không bí mật; trong ứng dụng thật, chỉ chuyển dữ liệu sang bước xử lý sau khi tất cả kiểm tra thành công.

## 22. Xoay vòng signing key

Khi rotation, signer bắt đầu dùng key version mới cho chữ ký mới. Public key cũ vẫn cần được giữ để xác minh chữ ký đã tạo trước thời điểm cutover.

Thực hành:

~~~powershell
java DataSigningLab keygen signer-v2.private.pk8.b64 signer-v2.public.spki.b64
java DataSigningLab sign signer-v2.private.pk8.b64 signer-2026-v2 tenant-42 invoice-approval invoice.txt invoice-v2.sig
java DataSigningLab verify signer-v2.public.spki.b64 signer-2026-v2 tenant-42 invoice-approval invoice.txt invoice-v2.sig
java DataSigningLab verify signer-v1.public.spki.b64 signer-2026-v1 tenant-42 invoice-approval invoice.txt invoice.sig
~~~

Kết quả:

- Chữ ký mới verify bằng public key v2.
- Chữ ký lịch sử tiếp tục verify bằng public key v1.
- Public key v1 không được dùng để ký; public key chỉ có chức năng verify.
- Private key v1 được retire/disable theo policy sau khi cutover.
- Public key v1 được giữ trong trust registry trong thời gian chữ ký lịch sử còn cần xác minh.

Không xóa public key cũ ngay sau rotation. Với tài liệu cần xác minh lâu dài, có thể cần trusted timestamp, certificate status history và bằng chứng về thời điểm chữ ký được tạo. Chỉ timestamp do client tự ghi không đủ để chứng minh thời điểm.

## 23. Thu hồi key và xử lý compromise

Nếu private signing key bị nghi ngờ compromise:

1. Xác định key ID, version, owner, purpose và thời gian bị ảnh hưởng.
2. Dừng quyền sign bằng key đó theo incident policy.
3. Thu hồi credential/grant và điều tra operation bất thường.
4. Tạo key pair mới trong boundary đã xác minh.
5. Cập nhật public key registry và chuyển signer.
6. Đánh giá chữ ký/tài liệu được tạo trong khoảng thời gian compromise.
7. Duy trì public key cũ cho kiểm tra lịch sử nếu policy cho phép, nhưng đánh dấu trạng thái trust/revocation rõ ràng.
8. Lưu audit evidence và thông báo consumer.

Một chữ ký verify thành công về mặt toán học không tự chứng minh chữ ký được tạo trước hay sau thời điểm private key bị lộ. Với use case cần long-term validation, phải kết hợp trusted timestamp, certificate validity/revocation history và policy xác định thời điểm tin cậy.

## 24. Bảo vệ private key trong production

Private key không nên được lưu trong source code, container image, application database, log hoặc file share. Các lựa chọn:

- KMS/HSM tạo và giữ private key non-exportable.
- Signing service chuyên biệt nhận payload đã được authorization.
- Workload identity ngắn hạn và policy chỉ cho phép sign theo key/purpose.
- Tách quyền tạo key, đăng ký public key, ký dữ liệu và audit.
- Dual control/approval cho import, policy change, rotation và destruction nhạy cảm.
- Rate limit và alert khi sign volume hoặc purpose bất thường.
- Backup/recovery theo semantics của provider và yêu cầu compliance.

Không phải mọi HSM/provider đều hỗ trợ Ed25519 hoặc cùng một API. Cần kiểm tra thuật toán được hỗ trợ, key attestation/certification, audit, backup và khả năng export trước khi thiết kế.

## 25. Public key trust và certificate

Verifier cần biết public key nào thuộc signer nào. Các cách phổ biến:

- Trusted key registry có quyền ghi hạn chế và audit.
- X.509 certificate chain tới trust anchor được cấu hình.
- Public key fingerprint pinning được phân phối qua kênh độc lập.
- Key transparency hoặc registry có integrity proof nếu hệ thống yêu cầu.

Registry nên lưu:

| Metadata | Mục đích |
|---|---|
| keyId | Lookup reference duy nhất |
| publicKey/certificate | Material dùng để verify |
| algorithm/profile | Thuật toán và tham số được chấp thuận |
| owner/subject | Chủ thể được gắn với key |
| tenant/scope | Phạm vi dữ liệu được ký |
| purpose | Mục đích ký |
| validFrom/validUntil | Khoảng thời gian policy cho phép |
| status | Active, verify-only, revoked hoặc retired |
| predecessor/successor | Liên kết rotation |
| certificate/revocation data | Bằng chứng trust khi dùng PKI |

Không coi key ID, filename hoặc public key tự gửi kèm là trust anchor. Nếu dùng certificate, phải xác minh chain, key usage, extended key usage, validity và revocation theo policy.

## 26. Audit cho ký và xác minh

Audit event hữu ích có thể ghi:

- Event ID và timestamp từ nguồn tin cậy.
- Actor/workload identity.
- Key ID/version và algorithm.
- Tenant reference và purpose.
- Payload reference hoặc digest phù hợp với threat model.
- Operation sign/verify và kết quả.
- Request/correlation ID.
- Policy decision và approval/change reference.

Không ghi private key, secret, credential hoặc plaintext nhạy cảm. Payload digest cũng cần cân nhắc: nếu payload có entropy thấp, hash có thể bị dò ngược bằng dictionary. Có thể lưu object reference và integrity evidence trong hệ thống được phân quyền thay vì log nội dung.

Audit log cần chống sửa đổi, có retention và tách quyền quản trị khỏi signer. Signer không được có quyền xóa dấu vết của chính nó.

## 27. Các lỗi thường gặp

- **Dùng private key để verify:** sai vai trò; verifier dùng public key tương ứng.
- **Dùng public key để tạo chữ ký:** không thể tạo chữ ký số theo mô hình asymmetric signature.
- **Nhầm chữ ký với encryption:** chữ ký không che giấu payload.
- **Tin public key do sender gửi kèm:** attacker có thể tự tạo key pair và chữ ký giả.
- **Không ràng buộc purpose/tenant:** chữ ký hợp lệ có thể bị tái sử dụng sai ngữ cảnh.
- **Ký chuỗi đã normalize khác nhau:** signer và verifier có thể ký/xác minh bytes khác nhau.
- **Cho client chọn algorithm:** có thể tạo downgrade hoặc algorithm confusion.
- **Dùng chung key cho sign và encryption:** vi phạm purpose separation.
- **Không giữ public key cũ:** mất khả năng verify dữ liệu lịch sử.
- **Không xử lý revocation/compromise:** chữ ký từ key bị lộ có thể tiếp tục được tin.
- **Log private key hoặc payload nhạy cảm:** tạo thêm nơi rò rỉ.
- **Chấp nhận verify false hoặc lỗi parse:** biến lỗi xác minh thành bypass.
- **Chỉ kiểm tra HTTP success:** backend có thể chưa xác minh signature đúng.

## 28. Bài tập mở rộng

1. Thêm trường object ID vào signed context và chứng minh chữ ký không dùng được cho object khác.
2. Tạo hai tenant và xác minh chữ ký tenant A bị từ chối trong context tenant B.
3. Viết test tự động cho payload tampering, signature tampering, wrong key và wrong purpose.
4. Thay payload dạng text bằng JSON; chọn một canonical JSON representation và ký đúng bytes canonical.
5. Tạo registry ánh xạ key ID tới public key; verifier không nhận public key path trực tiếp từ command line nữa.
6. Thêm trạng thái ACTIVE, VERIFY_ONLY, REVOKED và EXPIRED cho key registry.
7. Viết rotation workflow có dual-read/single-new-sign: signer chỉ dùng v2 cho chữ ký mới, verifier vẫn nhận v1 và v2 trong thời hạn.
8. Ghi audit event có event ID, key ID, actor, tenant, purpose và result.
9. Thay local private key bằng KMS/HSM signing API trong môi trường test.
10. Định nghĩa quy trình long-term validation cho chữ ký cần giữ nhiều năm.

## 29. Câu hỏi tự kiểm tra

**1. Chữ ký số bảo vệ thuộc tính nào?**

Integrity và xác thực nguồn gốc gắn với public key được tin cậy. Chữ ký không cung cấp confidentiality.

**2. Khóa nào dùng để ký và khóa nào dùng để xác minh?**

Private key dùng để ký; public key tương ứng dùng để verify.

**3. Vì sao public key vẫn cần xác minh nguồn gốc?**

Vì attacker có thể tự tạo key pair và gửi public key của họ. Chữ ký verify thành công với key đó không chứng minh signer là tổ chức mong đợi.

**4. Vì sao đưa tenant và purpose vào signed message?**

Để ngăn chữ ký bị tráo hoặc tái sử dụng trong tenant hay nghiệp vụ khác.

**5. Vì sao cần canonical encoding?**

Để signer và verifier dựng cùng một chuỗi bytes, tránh nhập nhằng ranh giới field hoặc serialization.

**6. Vì sao không dùng một algorithm bất kỳ ghi trong envelope?**

Verifier phải áp dụng allowlist và policy của server để tránh algorithm confusion hoặc downgrade.

**7. Khi rotate signing key, có cần giữ public key cũ không?**

Có, nếu chữ ký lịch sử vẫn cần được xác minh. Private key cũ có thể retire theo policy.

**8. Chữ ký hợp lệ có chứng minh người ký là ai không?**

Chỉ khi public key đã được liên kết đáng tin cậy với chủ thể và quy trình xác minh identity còn hiệu lực.

**9. Nếu private key bị compromise thì làm gì?**

Dừng quyền ký, thu hồi credential, điều tra, tạo key mới, chuyển signer và đánh giá chữ ký bị ảnh hưởng.

**10. Vì sao không lưu private key trong source code?**

Source code thường được sao chép, review, build và lưu trong nhiều hệ thống; một lần lộ có thể làm mất kiểm soát signing key.

## 30. Tiêu chí hoàn thành

- [ ] Biên dịch DataSigningLab.java thành công bằng JDK 17.
- [ ] Tạo được payload UTF-8 và key pair Ed25519.
- [ ] Ký được payload và tạo signature envelope.
- [ ] Verify payload gốc với public key đúng trả về VALID.
- [ ] Payload bị sửa trả về INVALID.
- [ ] Signature bị sửa trả về INVALID.
- [ ] Public key khác không verify được signature.
- [ ] Sai key ID, tenant hoặc purpose bị từ chối.
- [ ] Envelope version hoặc algorithm không hỗ trợ bị từ chối.
- [ ] Giải thích được vì sao public key phải đến từ trust registry.
- [ ] Giải thích được cách giữ public key cũ sau signing key rotation.
- [ ] Không có private key hoặc plaintext nhạy cảm trong log/repository.

## 31. Kết luận

Bài thực hành cho thấy quy trình ký và xác minh dữ liệu gồm nhiều lớp: tạo và bảo vệ key pair, chọn đúng thuật toán, xác định chính xác bytes cần ký, ràng buộc tenant/purpose/key ID, xác minh public key từ nguồn tin cậy và xử lý mọi lỗi theo hướng fail closed. Chữ ký số chỉ có ý nghĩa xác thực khi public key được gắn với chủ thể đáng tin cậy. Khi rotation, cần dùng private key mới cho chữ ký mới và giữ public key cũ để xác minh dữ liệu lịch sử theo policy. Trong production, private key nên được bảo vệ bởi KMS/HSM hoặc signing service có audit và authorization chặt chẽ.
