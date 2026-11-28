# Khôi phục key từ backup

Khôi phục key từ backup là quy trình đưa một key đã được bảo vệ trong bản backup trở lại trạng thái có thể sử dụng trong một HSM, KMS hoặc security domain phục hồi được phê duyệt. Mục tiêu không chỉ là làm cho thao tác restore thành công, mà còn phải chứng minh đúng key, đúng version, đúng thuộc tính bảo mật, đúng tenant/purpose và đúng chuỗi custody đã được khôi phục.

Trong quản lý khóa, backup dữ liệu và backup key là hai việc khác nhau. Có ciphertext mà mất key cần thiết thì dữ liệu có thể không còn giải mã được. Có key mà không còn ciphertext, metadata hoặc mapping version thì cũng chưa khôi phục được ứng dụng. Vì vậy, bài thực hành này yêu cầu khôi phục cả key reference và khả năng thực hiện một operation kiểm chứng trên dữ liệu canary.

Bài học sử dụng hai đường thực hành. Lab Java 17 mô phỏng package backup đã được mã hóa xác thực bằng AES-GCM, kiểm tra metadata và phục hồi một test key. Phần vận hành HSM mô tả quy trình dùng backup/restore native của vendor, nơi key material được giữ trong security boundary và không được export plaintext chỉ để phục vụ bài tập. Hai đường này giúp hiểu cùng một nguyên tắc nhưng không có cùng security guarantee.

## 1. Mục tiêu thực hành

Sau bài này, người học có thể:

- Phân biệt backup key, backup dữ liệu, key replication và key escrow.
- Xác định key ID/version, algorithm, purpose, tenant và provider cần khôi phục.
- Kiểm tra backup manifest, nguồn gốc, integrity, authenticity và compatibility.
- Xác minh recovery wrapping key hoặc HSM backup domain độc lập với key được phục hồi.
- Chuẩn bị approval, quorum, custodian và isolated recovery environment.
- Khôi phục key bằng cơ chế HSM/KMS native phù hợp với provider.
- Kiểm tra thuộc tính key sau restore, gồm usage, sensitivity và extractability.
- Dùng canary operation để chứng minh key hoạt động đúng.
- Khôi phục mapping giữa ciphertext, wrapped DEK, KEK version và key registry.
- Xử lý backup lỗi, sai version, sai tenant, sai security domain và anti-rollback.
- Ghi audit evidence và cập nhật inventory sau restore.
- Lập kế hoạch cutover, rollback, cleanup và diễn tập recovery.

## 2. Tình huống thực hành

Một nền tảng thanh toán đa tenant dùng KEK trong HSM để wrap DEK của dữ liệu giao dịch. Một HSM site gặp sự cố thiết bị. Site dự phòng có HSM tương thích nhưng key object của tenant chưa được khôi phục đầy đủ.

Thông tin giả định cho lab:

| Thuộc tính | Giá trị minh họa |
|---|---|
| Service | Payment data encryption |
| Environment | Recovery sandbox |
| Tenant | tenant-42 |
| Key ID | kek-payment-tenant-42 |
| Key version | v3 |
| Algorithm | AES-256 |
| Purpose | Wrap/unwrap DEK |
| Source | HSM security domain tại site A |
| Target | Recovery HSM security domain tại site B |
| Backup ID | hsm-backup-2026-11-28-01 |
| Recovery request | REC-2026-0042 |
| Approval | Hai custodian độc lập và key owner |
| Validation | Unwrap test DEK và decrypt canary object |

Các tên và ID trên là dữ liệu giả. Người học phải thay bằng ID của môi trường sandbox do tổ chức cấp khi làm lab với HSM thật.

## 3. Phân biệt backup, replication, escrow và restore

| Khái niệm | Ý nghĩa | Có thay thế khái niệm khác không? |
|---|---|---|
| Key backup | Bản sao key material hoặc key object được bảo vệ để phục hồi | Không phải backup ciphertext |
| Data backup | Bản sao ciphertext, metadata và dữ liệu cần khôi phục | Không chứa đầy đủ key để giải mã |
| Key replication | Đồng bộ key giữa node/region theo semantics của provider | Không mặc nhiên là bản backup độc lập |
| Key escrow | Cơ chế custody/recovery có trustee và điều kiện truy cập | Không phải quyền restore tự do |
| Restore | Khôi phục key hoặc key object từ backup vào đích được phép | Không tự khôi phục dữ liệu hoặc application mapping |

Một HSM cluster có thể tự đồng bộ key object giữa node, nhưng nếu toàn bộ security domain hoặc custody credential bị mất thì replication không đủ. Ngược lại, backup HSM có thể tồn tại nhưng không dùng được nếu thiếu firmware compatibility, security domain, backup wrapping key, quorum hoặc metadata mapping.

## 4. Phân biệt key backup với data backup

Một encrypted object trong mô hình envelope encryption thường gồm:

- Ciphertext của dữ liệu.
- Nonce và authentication tag.
- Wrapped DEK (EDK).
- KEK ID/version đã dùng để wrap DEK.
- Encryption context/AAD và format version.
- Metadata về tenant, object và purpose.

Khôi phục dữ liệu cần cả ciphertext lẫn khả năng unwrap DEK. Khôi phục key không tự tạo lại ciphertext đã mất. Khôi phục ciphertext mà thiếu KEK hoặc DEK cần thiết có thể khiến dữ liệu không thể đọc.

Trong lab, hãy kiểm tra hai danh mục độc lập: inventory của backup dữ liệu và inventory của backup key. Mỗi object phải truy được tới key ID/version cụ thể; không dựa vào alias có thể đổi đích.

## 5. Phân loại key cần phục hồi

Không phải key nào cũng có cùng cách backup hoặc restore.

| Loại key | Yêu cầu phục hồi |
|---|---|
| KEK | Phục hồi key object và quyền unwrap các DEK phụ thuộc |
| DEK | Có thể được lưu dưới dạng wrapped DEK cùng ciphertext; restore theo từng object hoặc batch |
| Signing private key | Phục hồi theo custody/backup policy; kiểm tra certificate và trust state |
| HMAC key | Phục hồi cùng consumer, version và verification window |
| CA private key | Ceremony và quorum nghiêm ngặt; kiểm tra chain, certificate và revocation state |
| Public key | Thường có thể lấy từ certificate/registry đã xác thực; vẫn phải kiểm tra fingerprint |
| Recovery/backup wrapping key | Phải có domain custody độc lập để mở backup package |

Không dùng một key cho nhiều purpose chỉ để đơn giản hóa recovery. Nếu signing key bị compromise, quy trình phục hồi KEK không giải quyết được trust của chữ ký đã tạo.

## 6. Kiến trúc recovery và dependency

Một recovery plan cần biểu diễn chuỗi phụ thuộc:

~~~~mermaid
flowchart TD
    A[Recovery approval and custody]
    B[Recovery HSM/security domain]
    C[Backup wrapping key or native restore authority]
    D[Restored tenant KEK v3]
    E[Wrapped DEK inventory]
    F[Ciphertext backup]
    G[Application metadata and key registry]
    H[Canary decrypt validation]
    I[Service cutover]
    A --> B
    B --> C --> D
    D --> E
    E --> F
    F --> G --> H --> I
~~~~

Sơ đồ là dependency logic. Cơ chế native restore thực tế có thể khôi phục một security domain, partition hoặc nhóm key object theo cách riêng của vendor. Không giả định recovery wrapping key luôn là một key có thể export hoặc đọc trực tiếp từ thiết bị.

## 7. Chuẩn bị trước khi restore

Trước khi thực hiện restore, lập checklist preflight:

1. Xác nhận incident/change/recovery request hợp lệ.
2. Xác định owner của key và dữ liệu phụ thuộc.
3. Xác minh key ID, version, tenant, purpose và algorithm.
4. Kiểm tra trạng thái key ở source và target.
5. Xác minh backup ID, thời điểm tạo và source security domain.
6. Kiểm tra checksum/signature/manifest theo định dạng backup.
7. Xác nhận target HSM model, firmware và provider compatibility.
8. Xác minh recovery credential, custodian và quorum.
9. Kiểm tra legal hold, retention và compromise status.
10. Chuẩn bị isolated test partition và canary data.
11. Xác định rollback point và người chịu trách nhiệm.
12. Bảo đảm audit collector hoạt động trước khi thao tác.

Nếu backup có nguồn gốc không rõ, manifest không xác minh được, target không tương thích hoặc thiếu quorum, dừng ở trạng thái quarantine. Không thử import/restore lặp lại để “xem có chạy được không”.

## 8. Backup manifest cần có gì?

Manifest giúp nhận diện backup và kiểm tra compatibility. Tùy provider, một số field có thể nằm trong signed manifest riêng hoặc metadata của native backup.

| Field | Mục đích |
|---|---|
| backup_id | Định danh backup duy nhất |
| format_version | Phiên bản format |
| source_provider/model | Nguồn tạo backup |
| source_device/security_domain | Thiết bị/domain nguồn |
| source_partition | Partition hoặc scope liên quan |
| key_id/key_version | Key được backup |
| algorithm/key_type | Loại key |
| purpose/usage | Operation được phép |
| tenant/environment | Phạm vi sử dụng |
| created_at | Thời điểm tạo |
| sequence/checkpoint | Phát hiện rollback khi có cơ chế tin cậy |
| integrity/signature reference | Kiểm tra authenticity/integrity |
| compatibility | Target model/firmware được hỗ trợ |
| custody reference | Hồ sơ bàn giao và custodian |
| retention/legal hold | Điều kiện lưu giữ |

Không đưa raw key bytes, PIN, recovery share hoặc plaintext secret vào manifest. Hash/checksum đơn thuần chỉ phát hiện thay đổi nếu digest được bảo vệ; attacker có thể sửa cả file và checksum nếu cả hai không có authenticity anchor.

## 9. Integrity, authenticity và anti-rollback

Ba kiểm tra này có mục đích khác nhau:

- **Integrity:** package không bị thay đổi ngoài dự kiến.
- **Authenticity/provenance:** package thực sự đến từ nguồn hoặc signer được tin cậy.
- **Anti-rollback:** package cũ hợp lệ không bị dùng thay cho version mới hơn.

Với native HSM backup, dùng cơ chế integrity/authentication và restore validation do vendor hỗ trợ. Với package do ứng dụng tự quản lý, cần authenticated encryption hoặc signature/manifest được bảo vệ độc lập. Không coi SHA-256 checksum không có chữ ký là bằng chứng nguồn gốc.

Anti-rollback cần trạng thái tin cậy bên ngoài package, ví dụ registry append-only, monotonic sequence được ký hoặc recovery ledger. Nếu chỉ đọc sequence từ chính package, attacker có thể thay package cũ cùng sequence. Test phải mô phỏng restore một backup cũ nhưng vẫn có chữ ký hợp lệ và xác minh hệ thống từ chối khi policy yêu cầu version mới hơn.

## 10. Custody, approval và quorum

Recovery là operation đặc quyền. Tách các vai trò:

| Vai trò | Trách nhiệm |
|---|---|
| Requester | Mở recovery request và nêu lý do |
| Key owner | Xác nhận key ID/version và mục đích |
| Data owner | Xác nhận dữ liệu cần khôi phục |
| Custodian | Cung cấp phần custody/recovery được giao |
| Security approver | Xác nhận threat, scope và policy |
| HSM operator | Thực hiện native restore theo ceremony |
| Auditor | Kiểm tra evidence độc lập |

Requester không tự approve. Một người không được giữ toàn bộ recovery share nếu policy yêu cầu split knowledge. Quorum phải dựa trên cá nhân độc lập, không phải nhiều tài khoản của cùng một người.

Approval cần gắn với backup ID, key ID/version, source/target security domain, operation, purpose, tenant, time window và request digest. Nếu target hoặc backup thay đổi sau khi duyệt, phải đánh giá lại approval.

## 11. Tách recovery domain khỏi key được phục hồi

Recovery wrapping key hoặc HSM backup domain không được phụ thuộc vào chính key đang cần restore.

Ví dụ circular dependency nguy hiểm:

- KEK cần restore đang bảo vệ backup package của chính KEK đó.
- Backup wrapping key chỉ tồn tại trong HSM đã mất.
- Recovery credential được mã hóa bằng key chỉ có thể lấy sau khi restore hoàn tất.

Cần thiết kế recovery root/domain riêng, có backup và custody độc lập, được diễn tập định kỳ. Độc lập có thể gồm account, HSM security domain, site, identity, administrator và audit plane khác nhau theo threat model.

## 12. Quy trình restore HSM native

Đây là quy trình tổng quát; phải dùng đúng hướng dẫn và semantics của vendor.

1. Xác minh backup package và source security domain.
2. Xác minh target HSM model, firmware, license và compatibility.
3. Tạo hoặc chọn target security domain/partition được phê duyệt.
4. Xác minh operator role và quorum.
5. Kết nối recovery media/channel theo quy trình vendor.
6. Thực hiện native restore vào isolated target.
7. Đọc lại key inventory và key attributes từ HSM.
8. Kiểm tra key ID/version, algorithm, usage, sensitive và extractability.
9. Xác minh key policy, grants, labels và partition mapping.
10. Chạy canary operation.
11. Đối chiếu audit log và provider operation ID.
12. Chỉ sau khi pass mới cập nhật registry/cutover.

Native backup thường bảo vệ key material trong format chỉ HSM tương thích hoặc security domain được phép mới khôi phục. Không dùng PrivateKey.getEncoded() hoặc SecretKey.getEncoded() để thay thế native backup của non-extractable key. Nếu API trả null cho encoding, đó không phải lỗi cần khắc phục bằng cách export key qua đường khác.

## 13. Quy trình restore key trong KMS cloud

Một KMS cloud có thể cung cấp replication, import, backup hoặc restore semantics khác HSM on-premises. Một số dịch vụ không cho export key material đã tạo nội bộ; một số chỉ hỗ trợ import material hoặc multi-region replica.

Trước khi thao tác:

- Xác minh provider có hỗ trợ restore cho loại key đó không.
- Phân biệt replica, imported key material và backup archive.
- Kiểm tra account/project/region và key ID.
- Xác minh IAM role, key policy, grant và organization guardrail.
- Kiểm tra state transition và deletion window.
- Kiểm tra provider audit event.
- Xác minh key version mapping của application.

Không giả định có thể “download backup” cho mọi KMS key. Nếu provider không hỗ trợ restore, recovery plan có thể là tạo key mới, re-encrypt/re-wrap dữ liệu hoặc khôi phục từ một escrow process được thiết kế trước.

## 14. Kiểm tra key attributes sau restore

Sau khi restore, xác minh thuộc tính thực tế từ HSM/KMS:

- Key ID và version khớp manifest.
- Algorithm, key size và curve đúng.
- Key purpose/usage đúng.
- Sensitive và non-extractable đúng policy.
- Allowed mechanisms không bị mở rộng.
- Export/wrap/derive permission không vượt yêu cầu.
- Owner, tenant, environment và partition đúng.
- Lifecycle state cho phép operation cần thiết.
- Policy/grant và administrator role đúng.
- Creation/import/restore provenance được ghi nhận.

Với PKCS#11, các attribute như CKA_SENSITIVE, CKA_EXTRACTABLE, CKA_ENCRYPT, CKA_DECRYPT, CKA_SIGN và CKA_UNWRAP có semantics cụ thể. Kiểm tra qua vendor tooling/provider API và tài liệu phiên bản đang dùng. Không chỉ tin label hoặc alias.

## 15. Canary validation

Canary là dữ liệu thử không nhạy cảm được tạo trước backup hoặc bằng test fixture đã biết. Nó giúp xác minh key restored thực hiện operation mong muốn.

Ví dụ validation:

- KEK: unwrap một test DEK đã được wrap trước backup.
- DEK: decrypt một canary ciphertext với nonce, tag và AAD đã lưu.
- Signing key: ký challenge mới rồi verify bằng public key/certificate đã pin.
- HMAC key: tính MAC cho message test rồi so sánh bằng verifier độc lập.
- CA key: kiểm tra certificate chain/test issuance trong môi trường cô lập theo policy.

Canary phải bind key ID/version, tenant và purpose. Không dùng dữ liệu production thật trong recovery drill. Một canary thành công chứng minh operation cụ thể hoạt động; nó không chứng minh toàn bộ inventory, backup chain hoặc mọi object đã được phục hồi.

## 16. Khôi phục mapping và dependency

Sau khi key object phục hồi, cần khôi phục mapping giữa:

- key ID/version và provider resource.
- tenant và key purpose.
- wrapped DEK/EDK và KEK version.
- ciphertext object và encryption context.
- backup snapshot và key inventory revision.
- application configuration và immutable key reference.
- public certificate và private signing key version.

Không tự gán alias cũ vào key mới nếu chưa chứng minh material tương ứng. Một key mới có cùng alias không thể giải mã ciphertext được mã hóa bằng key cũ.

Nếu backup có nhiều KEK version, phục hồi đúng version theo dependency inventory. Không overwrite key version mới bằng backup cũ chỉ vì alias trùng.

## 17. Lab Java 17: mô phỏng backup package

Lab dùng JDK 17 và chỉ dùng test key. Mô hình:

1. Tạo recovery wrapping key ngẫu nhiên 256-bit trong thư mục custody riêng.
2. Tạo test operational KEK ngẫu nhiên 256-bit.
3. Mã hóa key bytes của test KEK bằng AES-GCM với recovery key.
4. Bind key ID, version, algorithm và purpose vào AAD.
5. Lưu package gồm metadata, nonce và ciphertext/tag.
6. Tạo canary DEK, wrap DEK bằng test KEK rồi mã hóa canary data bằng DEK.
7. Xóa best-effort các byte array trong process.
8. Chạy restore, kiểm tra metadata, AEAD tag và canary.

Trong mô phỏng, AES-GCM đóng vai trò authenticated wrapping container để bài tập có thể chạy bằng JDK chuẩn. Đây không phải tuyên bố rằng mọi HSM dùng AES-GCM làm key-wrap mechanism; production phải dùng native backup/restore hoặc wrapping mechanism được provider và cryptographic policy hỗ trợ. Mỗi lần mã hóa dùng nonce mới; hệ thống production phải có chiến lược bảo đảm nonce không lặp dưới cùng một key.

Đây là mô phỏng package backup do ứng dụng quản lý. Nó không mô phỏng security boundary, non-extractability, split knowledge hoặc vendor-native backup của HSM. Recovery key trong lab được lưu thành file test-only để tiện thực hành; hai thư mục khác nhau trên cùng máy không tạo ra failure-domain độc lập.

## 18. Chuẩn bị thư mục lab

Tạo hai thư mục riêng:

~~~~text
key-recovery-lab/
  backup/
  custody/
~~~~

- backup/ chứa key-backup.pkg, canary-dek.bin và canary.bin.
- custody/ chứa recovery-key.test.bin.
- Không đưa các file này vào Git.
- Không dùng key, token hoặc dữ liệu production.
- Không gửi file recovery key qua chat, email hoặc ticket.

Kiểm tra Java:

~~~~powershell
java -version
javac -version
~~~~

Cần JDK 17. Nếu đang dùng phiên bản khác, kiểm tra lại API tương thích trước khi chạy.

## 19. Java 17: chương trình tạo và phục hồi package

Lưu mã sau thành KeyBackupLab.java. Chương trình hỗ trợ create, restore và tamper. Nó giới hạn file size, kiểm tra magic/version, kiểm tra metadata mong đợi, dùng AES-GCM với AAD và xác minh canary sau restore.

~~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class KeyBackupLab {
    private static final int PACKAGE_MAGIC = 0x4B425031;
    private static final int BLOB_MAGIC = 0x43414E31;
    private static final int FORMAT_VERSION = 1;
    private static final int KEY_BYTES = 32;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int MAX_FILE_BYTES = 1024 * 1024;

    private static final String KEY_ID = "lab-payment-tenant-42";
    private static final String KEY_VERSION = "v3";
    private static final String ALGORITHM = "AES-256";
    private static final String PURPOSE = "TENANT_KEK";
    private static final String CANARY_ID = "lab-canary-001";
    private static final byte[] CANARY =
            "test-only-recovery-canary".getBytes(StandardCharsets.UTF_8);

    private static final SecureRandom RANDOM = new SecureRandom();

    private record BackupPackage(
            int formatVersion,
            String keyId,
            String keyVersion,
            String algorithm,
            String purpose,
            byte[] nonce,
            byte[] ciphertext
    ) {}

    private record EncryptedBlob(byte[] nonce, byte[] ciphertext) {}

    private KeyBackupLab() {}

    public static void main(String[] args) throws Exception {
        if (args.length < 3) {
            usage();
            System.exit(2);
        }

        Path backupDir = Path.of(args[1]).toAbsolutePath().normalize();
        Path custodyDir = Path.of(args[2]).toAbsolutePath().normalize();

        if (backupDir.equals(custodyDir)) {
            throw new IllegalArgumentException(
                    "Backup and custody directories must differ"
            );
        }

        switch (args[0]) {
            case "create" -> create(backupDir, custodyDir);
            case "restore" -> {
                String packageName =
                        args.length >= 4 ? args[3] : "key-backup.pkg";
                restore(backupDir, custodyDir, packageName);
            }
            case "tamper" -> tamper(backupDir);
            default -> usage();
        }
    }

    private static void usage() {
        System.out.println(
                "Usage: java KeyBackupLab <create|restore|tamper> "
                + "<backup-dir> <custody-dir> [package-file]"
        );
    }

    private static void create(Path backupDir, Path custodyDir)
            throws Exception {
        Files.createDirectories(backupDir);
        Files.createDirectories(custodyDir);

        Path packagePath = backupDir.resolve("key-backup.pkg");
        Path canaryDekPath = backupDir.resolve("canary-dek.bin");
        Path canaryPath = backupDir.resolve("canary.bin");

        if (Files.exists(packagePath) || Files.exists(canaryDekPath)
                || Files.exists(canaryPath)) {
            throw new IOException(
                    "Lab backup already exists; use a fresh backup directory"
            );
        }

        byte[] recoveryKey = loadOrCreateRecoveryKey(custodyDir);
        byte[] operationalKey = new byte[KEY_BYTES];
        byte[] canaryDek = new byte[KEY_BYTES];

        try {
            RANDOM.nextBytes(operationalKey);
            RANDOM.nextBytes(canaryDek);

            byte[] nonce = randomNonce();
            byte[] aad = keyAad(
                    FORMAT_VERSION, KEY_ID, KEY_VERSION, ALGORITHM, PURPOSE
            );
            byte[] wrappedKey = encryptGcm(
                    recoveryKey, nonce, aad, operationalKey
            );

            BackupPackage backup = new BackupPackage(
                    FORMAT_VERSION,
                    KEY_ID,
                    KEY_VERSION,
                    ALGORITHM,
                    PURPOSE,
                    nonce,
                    wrappedKey
            );
            writePackage(packagePath, backup);

            byte[] canaryDekNonce = randomNonce();
            byte[] canaryDekAad = canaryDekAad(
                    KEY_ID, KEY_VERSION, CANARY_ID
            );
            byte[] wrappedCanaryDek = encryptGcm(
                    operationalKey, canaryDekNonce, canaryDekAad, canaryDek
            );
            writeBlob(
                    canaryDekPath,
                    new EncryptedBlob(canaryDekNonce, wrappedCanaryDek)
            );

            byte[] canaryNonce = randomNonce();
            byte[] canaryDataAad = canaryDataAad(
                    KEY_ID, KEY_VERSION, CANARY_ID
            );
            byte[] canaryCiphertext = encryptGcm(
                    canaryDek, canaryNonce, canaryDataAad, CANARY
            );
            writeBlob(
                    canaryPath,
                    new EncryptedBlob(canaryNonce, canaryCiphertext)
            );

            System.out.println("Backup package created: " + packagePath);
            System.out.println("Wrapped canary DEK created: " + canaryDekPath);
            System.out.println("Canary created: " + canaryPath);
            System.out.println(
                    "Test-only recovery key stored separately in custody folder."
            );
        } finally {
            Arrays.fill(recoveryKey, (byte) 0);
            Arrays.fill(operationalKey, (byte) 0);
            Arrays.fill(canaryDek, (byte) 0);
        }
    }

    private static void restore(
            Path backupDir,
            Path custodyDir,
            String packageName
    ) throws Exception {
        if (Path.of(packageName).getFileName() == null
                || !Path.of(packageName).getFileName().toString()
                        .equals(packageName)) {
            throw new IllegalArgumentException("Package name must be a file name");
        }

        Path packagePath = backupDir.resolve(packageName);
        Path canaryDekPath = backupDir.resolve("canary-dek.bin");
        Path canaryPath = backupDir.resolve("canary.bin");
        Path recoveryKeyPath = custodyDir.resolve("recovery-key.test.bin");
        if (Files.size(recoveryKeyPath) != KEY_BYTES) {
            throw new IOException("Recovery key file must contain exactly 32 bytes");
        }
        byte[] recoveryKey = Files.readAllBytes(recoveryKeyPath);
        byte[] restoredKey = null;
        byte[] restoredCanaryDek = null;
        byte[] restoredCanary = null;

        try {
            requireKeyLength(recoveryKey, "recovery key");
            BackupPackage backup = readPackage(packagePath);

            // Expected metadata comes from trusted lab configuration,
            // not from the package being restored.
            if (backup.formatVersion() != FORMAT_VERSION
                    || !KEY_ID.equals(backup.keyId())
                    || !KEY_VERSION.equals(backup.keyVersion())
                    || !ALGORITHM.equals(backup.algorithm())
                    || !PURPOSE.equals(backup.purpose())) {
                throw new SecurityException(
                        "Backup metadata does not match expected key identity"
                );
            }

            byte[] aad = keyAad(
                    backup.formatVersion(),
                    backup.keyId(),
                    backup.keyVersion(),
                    backup.algorithm(),
                    backup.purpose()
            );
            restoredKey = decryptGcm(
                    recoveryKey,
                    backup.nonce(),
                    aad,
                    backup.ciphertext()
            );
            requireKeyLength(restoredKey, "restored operational key");

            EncryptedBlob wrappedCanaryDek = readBlob(
                    canaryDekPath, KEY_BYTES + TAG_BITS / 8
            );
            byte[] canaryDekAad = canaryDekAad(
                    backup.keyId(),
                    backup.keyVersion(),
                    CANARY_ID
            );
            restoredCanaryDek = decryptGcm(
                    restoredKey,
                    wrappedCanaryDek.nonce(),
                    canaryDekAad,
                    wrappedCanaryDek.ciphertext()
            );
            requireKeyLength(restoredCanaryDek, "restored canary DEK");

            EncryptedBlob canary = readBlob(
                    canaryPath, CANARY.length + TAG_BITS / 8
            );
            byte[] canaryDataAad = canaryDataAad(
                    backup.keyId(),
                    backup.keyVersion(),
                    CANARY_ID
            );
            restoredCanary = decryptGcm(
                    restoredCanaryDek,
                    canary.nonce(),
                    canaryDataAad,
                    canary.ciphertext()
            );

            if (!MessageDigest.isEqual(CANARY, restoredCanary)) {
                throw new SecurityException("Canary plaintext does not match");
            }

            System.out.println("RESTORE_VALIDATED");
            System.out.println("keyId=" + backup.keyId());
            System.out.println("keyVersion=" + backup.keyVersion());
            System.out.println("algorithm=" + backup.algorithm());
            System.out.println("purpose=" + backup.purpose());
            System.out.println("canary=PASS");
        } finally {
            Arrays.fill(recoveryKey, (byte) 0);
            if (restoredKey != null) {
                Arrays.fill(restoredKey, (byte) 0);
            }
            if (restoredCanaryDek != null) {
                Arrays.fill(restoredCanaryDek, (byte) 0);
            }
            if (restoredCanary != null) {
                Arrays.fill(restoredCanary, (byte) 0);
            }
        }
    }

    private static byte[] loadOrCreateRecoveryKey(Path custodyDir)
            throws Exception {
        Path keyPath = custodyDir.resolve("recovery-key.test.bin");

        if (Files.exists(keyPath)) {
            if (Files.size(keyPath) != KEY_BYTES) {
                throw new IOException("Existing recovery key file has invalid size");
            }
            byte[] existing = Files.readAllBytes(keyPath);
            requireKeyLength(existing, "existing recovery key");
            return existing;
        }

        byte[] generated = new byte[KEY_BYTES];
        RANDOM.nextBytes(generated);

        try {
            Files.write(
                    keyPath,
                    generated,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE
            );
            return generated.clone();
        } finally {
            Arrays.fill(generated, (byte) 0);
        }
    }

    private static byte[] randomNonce() {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);
        return nonce;
    }

    private static byte[] encryptGcm(
            byte[] key,
            byte[] nonce,
            byte[] aad,
            byte[] plaintext
    ) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE,
                new SecretKeySpec(key, "AES"),
                new GCMParameterSpec(TAG_BITS, nonce)
        );
        cipher.updateAAD(aad);
        return cipher.doFinal(plaintext);
    }

    private static byte[] decryptGcm(
            byte[] key,
            byte[] nonce,
            byte[] aad,
            byte[] ciphertext
    ) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE,
                new SecretKeySpec(key, "AES"),
                new GCMParameterSpec(TAG_BITS, nonce)
        );
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertext);
    }

    private static byte[] keyAad(
            int formatVersion,
            String keyId,
            String keyVersion,
            String algorithm,
            String purpose
    ) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeUTF("key-backup-lab");
            out.writeInt(formatVersion);
            out.writeUTF(keyId);
            out.writeUTF(keyVersion);
            out.writeUTF(algorithm);
            out.writeUTF(purpose);
        }
        return bytes.toByteArray();
    }

    private static byte[] canaryDekAad(
            String keyId,
            String keyVersion,
            String canaryId
    ) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeUTF("key-backup-canary-dek-wrap");
            out.writeUTF(keyId);
            out.writeUTF(keyVersion);
            out.writeUTF(canaryId);
        }
        return bytes.toByteArray();
    }

    private static byte[] canaryDataAad(
            String keyId,
            String keyVersion,
            String canaryId
    ) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeUTF("key-backup-canary-data");
            out.writeUTF(keyId);
            out.writeUTF(keyVersion);
            out.writeUTF(canaryId);
        }
        return bytes.toByteArray();
    }

    private static void writePackage(
            Path path,
            BackupPackage backup
    ) throws IOException {
        try (DataOutputStream out = new DataOutputStream(
                Files.newOutputStream(
                        path,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE
                )
        )) {
            out.writeInt(PACKAGE_MAGIC);
            out.writeInt(backup.formatVersion());
            out.writeUTF(backup.keyId());
            out.writeUTF(backup.keyVersion());
            out.writeUTF(backup.algorithm());
            out.writeUTF(backup.purpose());
            writeSized(out, backup.nonce());
            writeSized(out, backup.ciphertext());
        }
    }

    private static BackupPackage readPackage(Path path) throws IOException {
        requireFileSize(path);

        try (DataInputStream in = new DataInputStream(
                Files.newInputStream(path)
        )) {
            if (in.readInt() != PACKAGE_MAGIC) {
                throw new IOException("Invalid backup package magic");
            }

            int version = in.readInt();
            String keyId = in.readUTF();
            String keyVersion = in.readUTF();
            String algorithm = in.readUTF();
            String purpose = in.readUTF();
            byte[] nonce = readSized(in, NONCE_BYTES);
            byte[] ciphertext = readSized(in, KEY_BYTES + TAG_BITS / 8);

            if (nonce.length != NONCE_BYTES
                    || ciphertext.length != KEY_BYTES + TAG_BITS / 8
                    || in.read() != -1) {
                throw new IOException("Invalid backup package structure");
            }

            return new BackupPackage(
                    version, keyId, keyVersion, algorithm, purpose,
                    nonce, ciphertext
            );
        }
    }

    private static void writeBlob(Path path, EncryptedBlob blob)
            throws IOException {
        try (DataOutputStream out = new DataOutputStream(
                Files.newOutputStream(
                        path,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE
                )
        )) {
            out.writeInt(BLOB_MAGIC);
            writeSized(out, blob.nonce());
            writeSized(out, blob.ciphertext());
        }
    }

    private static EncryptedBlob readBlob(
            Path path,
            int expectedCiphertextLength
    ) throws IOException {
        requireFileSize(path);

        try (DataInputStream in = new DataInputStream(
                Files.newInputStream(path)
        )) {
            if (in.readInt() != BLOB_MAGIC) {
                throw new IOException("Invalid canary file magic");
            }

            byte[] nonce = readSized(in, NONCE_BYTES);
            byte[] ciphertext = readSized(in, expectedCiphertextLength);

            if (nonce.length != NONCE_BYTES
                    || ciphertext.length != expectedCiphertextLength
                    || in.read() != -1) {
                throw new IOException("Invalid canary file structure");
            }

            return new EncryptedBlob(nonce, ciphertext);
        }
    }

    private static void writeSized(DataOutputStream out, byte[] value)
            throws IOException {
        out.writeInt(value.length);
        out.write(value);
    }

    private static byte[] readSized(DataInputStream in, int maxLength)
            throws IOException {
        int length = in.readInt();
        if (length < 0 || length > maxLength) {
            throw new IOException("Invalid field length");
        }

        byte[] value = new byte[length];
        in.readFully(value);
        return value;
    }

    private static void requireFileSize(Path path) throws IOException {
        long size = Files.size(path);
        if (size <= 0 || size > MAX_FILE_BYTES) {
            throw new IOException("File size is outside the allowed range");
        }
    }

    private static void requireKeyLength(byte[] key, String label) {
        if (key.length != KEY_BYTES) {
            throw new IllegalArgumentException(
                    label + " must contain exactly 32 bytes"
            );
        }
    }

    private static void tamper(Path backupDir) throws IOException {
        Path source = backupDir.resolve("key-backup.pkg");
        Path target = backupDir.resolve("key-backup.tampered.pkg");
        requireFileSize(source);
        byte[] bytes = Files.readAllBytes(source);

        if (bytes.length < 1) {
            throw new IOException("Backup package is empty");
        }
        if (Files.exists(target)) {
            throw new IOException("Tampered package already exists");
        }

        bytes[bytes.length - 1] ^= 0x01;
        try {
            Files.write(
                    target,
                    bytes,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE
            );
            System.out.println("Tampered copy created: " + target);
        } finally {
            Arrays.fill(bytes, (byte) 0);
        }
    }
}
~~~~

Trong lab, recovery key file chứa raw test key để có thể chạy lại chương trình. Đây là chủ ý mô phỏng và chỉ được phép dùng trong thư mục thử nghiệm không chứa dữ liệu thật. Trong production, recovery wrapping key phải được giữ trong HSM/security domain độc lập hoặc custody mechanism đã phê duyệt; không lưu raw key cạnh backup package.

## 20. Chạy lab Java 17

Từ thư mục chứa KeyBackupLab.java:

~~~~powershell
javac KeyBackupLab.java
java KeyBackupLab create .\key-recovery-lab\backup .\key-recovery-lab\custody
java KeyBackupLab restore .\key-recovery-lab\backup .\key-recovery-lab\custody
~~~~

Kết quả restore mong đợi:

~~~~text
RESTORE_VALIDATED
keyId=lab-payment-tenant-42
keyVersion=v3
algorithm=AES-256
purpose=TENANT_KEK
canary=PASS
~~~~

Nếu chương trình báo RESTORE_VALIDATED, lab đã giải mã được test key từ package và dùng key vừa khôi phục để giải mã canary. Điều đó chứng minh package có thể đọc bằng recovery key trong lab và key phục hồi phù hợp với canary fixture. Nó không chứng minh HSM production restore, quorum hoặc custody đã hoạt động.

## 21. Thử nghiệm tamper và sai metadata

Tạo bản package bị sửa một bit:

~~~~powershell
java KeyBackupLab tamper .\key-recovery-lab\backup .\key-recovery-lab\custody
java KeyBackupLab restore .\key-recovery-lab\backup .\key-recovery-lab\custody key-backup.tampered.pkg
~~~~

Kết quả mong đợi là restore thất bại do GCM authentication tag không hợp lệ. Không được in restored key hoặc canary plaintext.

Các thử nghiệm bổ sung:

- Đổi một byte trong metadata key ID.
- Đổi key version trong package.
- Dùng recovery key khác.
- Thay canary file.
- Cắt cụt package.
- Thêm byte ở cuối package.
- Thay package bằng backup cũ có chữ ký hợp lệ nhưng sequence thấp hơn trusted checkpoint.
- Đưa package tenant-42 vào recovery request tenant-43.

Với test sửa metadata, AAD mismatch hoặc expected metadata check phải làm restore bị từ chối. Với rollback, cần một trusted checkpoint bên ngoài package; AES-GCM không tự phát hiện một package cũ vẫn hợp lệ.

## 22. Kết quả mong đợi và evidence lab

Ghi lại evidence sau mỗi bước:

| Bước | Evidence | Pass criteria |
|---|---|---|
| Preflight | Recovery request và approval | Đúng owner, key ID/version, scope |
| Backup selection | Backup ID và manifest | Nguồn/format/compatibility hợp lệ |
| Integrity | Signature/hash/AEAD result | Xác minh thành công |
| Custody | Custodian/quorum record | Đúng số người và identity độc lập |
| Restore | Provider operation ID hoặc lab output | Restore hoàn tất, không có error |
| Attribute check | Key attribute report | Algorithm/usage/extractability đúng |
| Canary | Canary operation result | Decrypt/verify pass |
| Registry | Key version mapping | Trỏ đúng immutable key ID/version |
| Audit | Source event IDs | Có actor, action, resource và outcome |
| Cutover | Change record/canary traffic | Chỉ mở traffic sau validation |

Không đính kèm recovery key, PIN, recovery share hoặc raw key material vào evidence. Chỉ lưu reference và kết quả kiểm chứng.

## 23. HSM recovery drill: quy trình từng bước

Khi chuyển từ lab mô phỏng sang HSM test environment:

1. Chọn HSM test partition và xác nhận vendor backup format.
2. Tạo test key theo đúng key attributes cần phục hồi.
3. Tạo một canary ciphertext hoặc signing challenge.
4. Tạo backup bằng native HSM backup procedure.
5. Ghi backup ID, source device/domain, firmware và manifest.
6. Lưu backup theo custody policy độc lập.
7. Chuẩn bị recovery target và xác minh compatibility.
8. Mở recovery request, xác minh owner và approval.
9. Tập hợp custodians theo quorum.
10. Thực hiện restore native theo hướng dẫn vendor.
11. Kiểm tra key ID/attributes/partition/policy.
12. Chạy canary unwrap/decrypt/sign/verify.
13. Đối soát audit source và provider operation.
14. Cập nhật key registry và dependency mapping.
15. Chỉ mở traffic canary sau khi key owner xác nhận.
16. Thu hồi quyền tạm thời và đóng ceremony record.

Không chạy thử native restore trên production partition trong buổi thực hành đầu tiên. Dùng HSM sandbox hoặc môi trường recovery được phê duyệt.

## 24. Cutover và rollback

Cutover chỉ được phép sau khi các kiểm tra key, data, policy và audit đạt yêu cầu.

Cutover checklist:

- Key ID/version được xác nhận.
- Target security domain đúng.
- Key attributes và policy đúng.
- Canary decrypt/unwrap/sign/verify pass.
- Application registry resolve đúng key.
- Tenant isolation test pass.
- Audit event được ghi và truy vấn được.
- Backup/data dependency không còn gap.
- Key owner và service owner ký xác nhận.
- Monitoring và alert được bật.

Nếu restore thất bại:

- Giữ target key ở trạng thái quarantine/disabled theo policy.
- Không overwrite backup gốc.
- Không tạo key mới với cùng ID để che lỗi.
- Không mở traffic production.
- Bảo toàn audit và diagnostic evidence.
- Kiểm tra compatibility, custody và manifest.
- Tạo recovery attempt mới với request/approval phù hợp nếu cần.

Rollback không đồng nghĩa xóa backup hoặc destroy key vừa restore. Mọi thao tác cleanup phải theo retention, evidence và key lifecycle policy.

## 25. Failure modes thường gặp

| Lỗi | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Backup không mở được | Sai recovery domain hoặc credential | Dừng, xác minh custody và source |
| Target không tương thích | Model/firmware/security domain khác | Dùng target được hỗ trợ |
| Key ID mismatch | Chọn nhầm backup hoặc mapping | Quarantine và kiểm tra inventory |
| Key attributes sai | Restore policy không giữ nguyên attributes | Không cutover; kiểm tra native semantics |
| Canary decrypt fail | Sai key/version/AAD hoặc ciphertext | Giữ target cô lập và điều tra |
| AEAD tag fail | Package/canary bị sửa hoặc sai key | Không bỏ qua authentication |
| Quorum thiếu | Thiếu custodian hoặc identity | Chờ đúng quorum, không hạ policy |
| Backup cũ | Rollback hoặc chọn nhầm snapshot | So sánh trusted sequence/checkpoint |
| Audit thiếu | Collector/provider audit lỗi | Dừng operation nhạy cảm theo policy |
| Registry stale | Mapping key version không đồng bộ | Reconcile trước khi mở traffic |
| HSM session full | Capacity/session leak | Xử lý session và scale theo thiết kế |
| Restore timeout | Không rõ provider đã hoàn tất chưa | Reconcile operation ID, không retry mù |

## 26. Kiểm thử bảo mật và negative tests

Bài thực hành cần chứng minh cả trường hợp thành công lẫn bị từ chối.

| Test | Kết quả mong đợi |
|---|---|
| Đúng backup, đúng recovery domain | Restore pass |
| Backup bị sửa một bit | Integrity/authentication fail |
| Recovery key sai | Restore fail |
| Key ID sai | Metadata check fail |
| Key version cũ | Anti-rollback policy từ chối |
| Tenant mismatch | Restore/use bị từ chối |
| Purpose mismatch | Key policy từ chối operation |
| Target HSM không tương thích | Preflight fail |
| Non-extractable key bị export | Provider từ chối |
| Thiếu quorum | Không thực hiện restore |
| Requester tự approve | Workflow từ chối |
| Audit sink unavailable | Hành vi theo failure policy |
| Restore response timeout | Chuyển unknown/reconcile |
| Duplicate restore request | Idempotency/reconciliation |
| Canary AAD sai | Decrypt fail, không trả plaintext |
| Key attributes mở rộng | Validation fail |
| Registry alias trỏ nhầm key | Immutable ID check fail |
| Backup sequence thấp hơn checkpoint | Anti-rollback fail |
| Custodian role đã bị revoke | Approval invalidated |
| Restore vào partition sai | Quarantine, không cutover |

Không dùng production key hoặc production ciphertext để chạy negative test. Một số HSM có behavior đặc biệt khi export bị từ chối; xác minh bằng audit event và provider result.

## 27. Audit sau restore

Audit evidence cần liên kết recovery workflow và provider operation:

- Recovery request ID.
- Backup ID/manifest reference.
- Source và target HSM/security domain.
- Key ID/version, tenant và purpose.
- Requester, approver, custodian và executor.
- Approval/quorum reference.
- Operation start/end và provider operation ID.
- Integrity/authenticity result.
- Key attribute validation result.
- Canary result.
- Registry revision trước/sau.
- Cutover decision và owner.
- Error, retry và reconciliation nếu có.

Không ghi recovery share, PIN, raw key bytes, plaintext hoặc secret vào audit. Nếu cần chứng minh custody, lưu evidence reference có access control thay vì nội dung bí mật.

## 28. RTO, RPO và recovery readiness

RPO và RTO phải được đo trong recovery drill:

- RPO: khoảng dữ liệu hoặc thay đổi key metadata tối đa có thể mất theo mục tiêu.
- RTO: thời gian từ khi bắt đầu recovery đến khi service được xác nhận hoạt động an toàn.

Đo các mốc:

1. Incident declared.
2. Custodian notified.
3. Approval quorum reached.
4. Backup located and verified.
5. Target HSM ready.
6. Restore completed.
7. Key attributes validated.
8. Canary passed.
9. Registry synchronized.
10. Service cutover approved.

Không báo RTO chỉ dựa trên thời gian API restore. Custodian availability, target provisioning, metadata reconciliation và canary validation đều nằm trong recovery time.

## 29. Cleanup sau lab

Sau khi hoàn thành:

- Giữ lại log kết quả và test report không chứa secret.
- Xóa test recovery key và package theo policy của sandbox.
- Xóa test HSM object bằng quy trình destruction được phê duyệt.
- Thu hồi test identity và credential.
- Xác minh test key không còn được tham chiếu trong registry.
- Kiểm tra không có test artifact trong Git hoặc shared folder.
- Không xóa evidence đang thuộc retention/legal hold.
- Ghi lại thời gian cleanup và người thực hiện.

Với lab local, xóa thư mục test sau khi đã lưu report cần thiết. Với HSM thật, không tự xóa key nếu chưa có approval và dependency clearance.

## 30. Deliverables cần nộp

Người học cần nộp một recovery report gồm:

1. Sơ đồ dependency của key và dữ liệu.
2. Recovery request và approval reference.
3. Backup manifest đã redacted.
4. Source/target HSM compatibility check.
5. Integrity/authenticity/anti-rollback result.
6. Custody/quorum evidence reference.
7. Restore operation ID và trạng thái.
8. Key attributes sau restore.
9. Canary operation result.
10. Registry mapping trước/sau.
11. Audit event references.
12. RTO/RPO đo được.
13. Failure/negative test results.
14. Cutover hoặc rollback decision.
15. Cleanup confirmation.

Không nộp raw recovery key, PIN, key share, DEK, KEK hoặc plaintext. Giảng viên chỉ cần metadata, reference và kết quả xác minh.

## 31. Rubric đánh giá

| Tiêu chí | Trọng số |
|---|---:|
| Preflight, identity, approval và quorum | 15% |
| Backup manifest, integrity và authenticity | 15% |
| Khôi phục đúng key ID/version và attributes | 20% |
| Canary validation và dependency mapping | 15% |
| Audit/evidence và custody | 10% |
| Negative tests, tamper và anti-rollback | 10% |
| Cutover, rollback và cleanup | 10% |
| Báo cáo rõ assumptions và limitations | 5% |

Điểm tối đa không bù được lỗi nghiêm trọng như sử dụng production secret trong lab, bỏ qua AEAD/tag failure, bypass quorum hoặc mở traffic khi key identity chưa xác minh. Các lỗi này làm bài thực hành không đạt.

## 32. Lỗi thường gặp khi khôi phục key

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ backup ciphertext | Không còn khả năng unwrap DEK | Backup key theo dependency |
| Chỉ backup key | Không phục hồi được dữ liệu | Backup data và metadata đồng bộ |
| Lưu recovery key cạnh package | Một lần compromise lấy được cả hai | Tách custody/domain |
| Dùng checksum không có authenticity | Attacker có thể sửa cả file và checksum | Signature hoặc AEAD với trust anchor |
| Không kiểm tra version | Restore nhầm key cũ | Immutable ID/version và checkpoint |
| Restore vào production ngay | Khó cô lập lỗi | Isolated restore và canary |
| Chỉ kiểm tra key tồn tại | Không chứng minh key hoạt động | Canary operation |
| Bỏ qua attributes | Key có thể bị export hoặc dùng sai purpose | Validate key policy/attributes |
| Dùng alias làm identity | Alias có thể đổi đích | Dùng immutable key reference |
| Retry khi timeout | Có thể restore/execute hai lần | Reconcile provider operation ID |
| Coi replication là backup | Mất toàn bộ domain vẫn không phục hồi | Backup độc lập và restore drill |
| Ghi secret vào report | Tạo thêm điểm rò rỉ | Chỉ nộp reference và result |

## 33. Câu hỏi tự kiểm tra

**1. Key backup khác data backup thế nào?**

Key backup phục hồi key hoặc key object; data backup phục hồi ciphertext, metadata và dữ liệu.

**2. Vì sao cần backup cả key lẫn metadata?**

Vì key mà không có version mapping, tenant, purpose và ciphertext dependency có thể không sử dụng được.

**3. HSM replication có thay backup không?**

Không. Replication và backup có failure domain, retention và recovery semantics khác nhau.

**4. Recovery wrapping key nên được lưu ở đâu?**

Trong HSM/security domain hoặc custody domain độc lập, theo policy recovery đã được phê duyệt.

**5. Vì sao không lưu raw recovery key cạnh package?**

Nếu cả hai bị lấy cùng lúc, attacker có thể khôi phục key được bảo vệ.

**6. Manifest cần có những thông tin nào?**

Backup ID, source/domain, key ID/version, algorithm, purpose, thời gian, compatibility, integrity và custody reference.

**7. Checksum có chứng minh authenticity không?**

Không nếu checksum không được bảo vệ độc lập; attacker có thể thay cả package và checksum.

**8. AES-GCM trong lab kiểm tra điều gì?**

Nó xác thực ciphertext và AAD; sửa package hoặc sai recovery key sẽ làm authentication fail.

**9. AES-GCM có tự chống rollback không?**

Không. Cần trusted sequence/checkpoint hoặc state bên ngoài package.

**10. Vì sao phải restore trong isolated environment?**

Để xác minh key, attributes, policy và canary trước khi cho workload production sử dụng.

**11. Canary operation chứng minh điều gì?**

Chứng minh key phục hồi thực hiện được operation cụ thể trên test fixture đã biết.

**12. Canary thành công có chứng minh mọi dữ liệu đã khôi phục không?**

Không. Cần đối soát toàn bộ dependency, backup chain và inventory.

**13. Vì sao phải kiểm tra non-extractable sau restore?**

Để bảo đảm key không bị mở rộng quyền export ngoài policy.

**14. Requester có thể tự approve recovery không?**

Không nếu policy yêu cầu separation of duties; requester và approver phải độc lập.

**15. Nếu target HSM khác model thì sao?**

Kiểm tra vendor compatibility và security domain semantics; không tự giả định backup có thể restore chéo model.

**16. Nếu provider timeout sau restore thì retry ngay không?**

Không. Reconcile operation ID và provider state trước.

**17. Vì sao phải kiểm tra tenant và purpose?**

Để tránh dùng key phục hồi cho dữ liệu hoặc workload ngoài phạm vi.

**18. RTO có chỉ tính thời gian restore API không?**

Không. Nó gồm approval, custody, provisioning, validation, mapping và cutover.

**19. Lab Java có chứng minh HSM native restore không?**

Không. Nó chỉ mô phỏng package wrapping và AEAD verification bằng software test key.

**20. Recovery hoàn tất khi nào?**

Khi key identity/attributes, dependency mapping, canary, audit, approval và service cutover đều được xác minh.

## 34. Tài liệu tham khảo

- NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management.
- NIST SP 800-34 Rev. 1 — Contingency Planning Guide for Federal Information Systems.
- NIST SP 800-53 Rev. 5 — Security and Privacy Controls: backup, recovery, access control, separation of duties và audit.
- NIST SP 800-61 Rev. 3 — Incident Response Recommendations and Considerations for Cybersecurity Risk Management.
- FIPS 140-3 — Security Requirements for Cryptographic Modules.
- PKCS #11 Cryptographic Token Interface Base Specification.
- Java Cryptography Architecture (JCA) Reference Guide — AES/GCM/NoPadding và GCMParameterSpec.
- Tài liệu backup/restore, replication, security domain và key attributes của HSM/KMS provider đang triển khai.
- Chính sách nội bộ về key custody, backup retention, recovery quorum, evidence và disaster recovery.

