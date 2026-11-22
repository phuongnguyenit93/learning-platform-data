# Mã hóa dữ liệu lưu trữ, quản lý khóa và chuẩn bị khôi phục khóa

Trong hệ **Database No SQL**, mã hóa dữ liệu khi lưu trữ (*encryption at rest*) giúp giảm tác động nếu ổ đĩa, volume, snapshot, backup hoặc tệp dữ liệu bị truy cập ngoài ý muốn. Tuy nhiên, **bật một tùy chọn mã hóa không tự bảo đảm toàn bộ hệ an toàn**. Nếu ứng dụng, tài khoản vận hành hoặc khóa giải mã bị chiếm quyền, dữ liệu có thể vẫn bị lộ. Ngược lại, nếu dữ liệu được sao lưu rất đầy đủ nhưng các khóa cần giải mã đã bị xóa hoặc không thể truy cập, cả bản production lẫn bản backup có thể trở thành những byte không dùng được.

Ví dụ một dịch vụ Java lưu hồ sơ người thuê nhà trong MongoDB:

~~~text
MongoDB production:            encrypted storage
Daily database snapshots:      encrypted
Sensitive fields:              application-level AEAD
Data encryption key (DEK):     wrapped by KMS master key
Disaster recovery environment: no permission to unwrap DEK
~~~

Các bản snapshot có thể nguyên vẹn, nhưng quy trình khôi phục vẫn thất bại vì **quyền giải mã, key versions hoặc hệ thống quản lý khóa** không được đưa vào thiết kế phục hồi.

Bài thuộc chương **Bảo mật dữ liệu** của **Database No SQL**, tập trung vào **mã hóa dữ liệu lưu trữ**, **phân cấp và vận hành khóa**, và **chuẩn bị khôi phục khóa** trước khi xảy ra sự cố. Chúng ta sẽ phân biệt mã hóa ổ đĩa với mã hóa phía ứng dụng, giới thiệu envelope encryption/DEK/KEK/KMS/HSM, minh họa Java AES-GCM và AWS KMS SDK v2, xem các đặc điểm của MongoDB, DynamoDB, Cassandra và Redis, rồi xây dựng runbook backup–restore và xử lý các tình huống khóa bị mất, bị vô hiệu hóa hoặc bị nghi ngờ lộ.

> **Nguyên tắc cốt lõi:** Chỉ gọi một bản backup là *khôi phục được* khi đã kiểm chứng **dữ liệu, metadata mã hóa, khóa/phiên bản khóa, quyền truy cập khóa, môi trường KMS và ứng dụng giải mã** hoạt động cùng nhau trong một bài restore thực tế.

---

## 1. Xác định mối đe dọa trước khi chọn loại mã hóa

Không có một chế độ mã hóa phù hợp mọi threat model. Hãy viết rõ đối thủ có khả năng nào:

- Đánh cắp một ổ đĩa hoặc volume.
- Đọc được database files/snapshot/backup trên object storage.
- Truy cập nhầm bucket hoặc copy backup sang tài khoản khác.
- Là quản trị viên hạ tầng có quyền đọc files nhưng không có quyền dùng khóa.
- Là một account/role có quyền truy cập database và thực hiện queries.
- Chiếm được một Java application server và sử dụng chính credentials của service.
- Truy cập log, memory dump, temporary files hoặc search index.
- Có thể vô hiệu hóa/xóa khóa hoặc cấu hình KMS sai.
- Là người vận hành được ủy quyền nhưng thực hiện nhầm thao tác khôi phục.

Mã hóa at-rest chủ yếu giúp với **việc truy cập ciphertext hoặc storage bên dưới** khi kẻ tấn công không có khóa. Nó **không tự chặn** các lệnh SELECT/GET hợp lệ do một application identity bị chiếm quyền thực hiện.

## 2. Ba trạng thái dữ liệu và các lớp bảo vệ

| Trạng thái | Ví dụ | Bảo vệ chủ đạo |
|---|---|---|
| **At rest** | Database files, WAL/oplog, snapshots, backup objects | Storage encryption, envelope encryption, key controls |
| **In transit** | Java ↔ NoSQL, replication, backup transfer | TLS/mTLS, endpoint authentication |
| **In use** | Plaintext trong Java heap, query engine, process memory | Least privilege, memory isolation, secure coding, secret hygiene |

Mã hóa at-rest **không thay TLS**. Một hệ có encrypted volume nhưng tắt TLS cho traffic giữa các hosts vẫn có nguy cơ lộ dữ liệu trên đường truyền.

Tương tự, encryption at rest không xóa nhu cầu **authorization ở mức tenant, collection, row/document hoặc API operation**.

## 3. Dữ liệu nào thực sự được mã hóa?

Trong một hệ NoSQL, “dữ liệu” còn nhiều hơn document payload:

- Primary table/collection files.
- Secondary indexes và các cấu trúc search.
- Write-ahead logs, oplog, commit logs.
- Temporary spill files từ sort/aggregation.
- Snapshots và database backups.
- Archived change streams hoặc CDC events.
- Replication files, repair/hint buffers.
- Cache Redis, AOF/RDB snapshots.
- Search materialized views.
- Object storage exports.
- Application logs, crash dumps và observability payloads.
- Development/staging copies dùng dữ liệu production.

Mỗi loại có **đường mã hóa và vòng đời khóa khác nhau**. Một collection được mã hóa ở storage layer không chứng minh tất cả JSON xuất ra S3, log debug hoặc Redis cache đều được mã hóa đúng.

## 4. Mã hóa và băm không phải một việc

- **Encryption:** biến plaintext thành ciphertext; có thể giải mã bằng khóa/phương pháp tương ứng.
- **Hashing:** tạo digest một chiều, không dùng để giải mã.
- **Password hashing:** dùng password KDF có salt và tham số cost thích hợp, không chỉ SHA-256 và không encrypt password để login bình thường.
- **MAC/HMAC:** kiểm tra tính toàn vẹn/xác thực của dữ liệu bằng một khóa.
- **Tokenization:** thay dữ liệu nhạy cảm bằng token, cần hệ thống quản lý mapping/khóa và phạm vi truy cập.
- **Digital signature:** xác thực nguồn/thông điệp với bất đối xứng khóa theo thuật toán tương ứng.

Đối với một trường cần đọc lại, ví dụ địa chỉ giao hàng, **mã hóa được xác thực (AEAD)** có thể phù hợp. Với mật khẩu đăng nhập, **password hashing chuyên dụng** mới là lựa chọn đúng.

## 5. Ba tầng mã hóa hay gặp

| Tầng | Vị trí mã hóa | Bảo vệ được gì? | Hạn chế chính |
|---|---|---|---|
| **Volume/disk encryption** | Hạ tầng storage | Raw disk/snapshot theo phạm vi | Database process thường nhìn plaintext |
| **Database transparent encryption** | Storage engine / managed service | Files, logs, backups theo implementation | Query engine/DB account vẫn truy cập plaintext |
| **Field/application encryption** | Java client, trước khi gửi DB | Trường nhạy ngay cả khi DB lưu ciphertext | Khó query/index, phức tạp khóa và ứng dụng |

Nhiều hệ kết hợp tất cả các tầng. Không nên đánh giá “double encryption có cần thiết không” trước khi biết ai có thể đọc dữ liệu ở mỗi tầng và yêu cầu tuân thủ.

## 6. Transparent Data Encryption không có nghĩa end-to-end

Với TDE hoặc engine-level encryption:

~~~mermaid
flowchart LR
    Java["Java application"] --> DB["Database process"]
    DB -->|"Reads/writes"| Engine["Encryption layer"]
    Engine --> Disk["Encrypted storage"]
~~~

Database process có thể giải mã page để chạy query và index. Một người có quyền đọc document thông qua database credentials vẫn có thể thấy plaintext theo ACL.

TDE giúp giảm tác động của **lộ thiết bị lưu trữ, disk files, backups** trong phạm vi triển khai; không thay ứng dụng tự bảo vệ trường bí mật khỏi database administrators hoặc các truy vấn không có quyền.

## 7. Field-level encryption có thể giữ DB chỉ thấy ciphertext

Một cách bố trí:

~~~mermaid
flowchart LR
    App["Authorized Java service"] --> Crypto["Client AEAD encrypt/decrypt"]
    Crypto --> DB["NoSQL stores ciphertext"]
    Crypto --> KMS["KMS unwraps data key"]
    DB --> Crypto
~~~

Ví dụ document đích:

~~~json
{
  "_id": "tenant17#user100",
  "tenantId": "tenant17",
  "emailBlindIndex": "bidx-v2:...",
  "phoneEncrypted": {
    "algorithm": "AES-256-GCM",
    "keyRef": "tenant17/pii-key",
    "keyVersion": "v3",
    "nonce": "base64...",
    "ciphertext": "base64..."
  }
}
~~~

Một số metadata có thể vẫn bị lộ: tenant IDs, key names, ciphertext lengths, field presence, access patterns và indexes không mã hóa. Cần threat model cho **metadata leakage** và minimization.

## 8. Không tự chế thuật toán mã hóa

Ưu tiên các thuật toán và thư viện được đánh giá rộng rãi, sử dụng đúng mode:

- **AES-GCM** cung cấp authenticated encryption nếu nonce/keys được quản lý đúng.
- **ChaCha20-Poly1305** là AEAD thay thế khi implementation/phần cứng phù hợp.
- **KMS/envelope encryption** giúp quản lý khóa theo lifecycle.
- **TLS** bảo vệ đường truyền.

Tránh:

- AES-ECB vì lộ mẫu của dữ liệu.
- AES-CBC không có authentication/MAC đúng cách.
- Mã hóa XOR hoặc custom cipher.
- Nonce/IV hard-coded hoặc tái sử dụng với cùng key GCM.
- Dùng một plaintext password thành AES key trực tiếp.
- Tự xây KMS bằng cách để master key trong file cấu hình git.

Mọi lựa chọn phải tương thích **thuật toán, version, compliance và threat model** của tổ chức.

## 9. AEAD: vừa giữ bí mật vừa bảo vệ tính toàn vẹn

Authenticated Encryption with Associated Data (AEAD) cung cấp:

1. **Confidentiality** cho plaintext.
2. **Integrity/authenticity** đối với ciphertext và dữ liệu liên kết được xác thực, miễn dùng key/nonce đúng.

Với AES-GCM:

~~~text
Inputs:
  key
  unique nonce for this key
  plaintext
  associated data (AAD)

Outputs:
  ciphertext
  authentication tag
~~~

Decrypt sẽ từ chối khi ciphertext, tag hoặc AAD không khớp, thay vì im lặng trả bytes bị sửa.

**Tag authentication không chứng minh plaintext “đúng nghiệp vụ”**. Nếu ứng dụng được cấp khóa rồi cố tình mã hóa dữ liệu sai, AEAD vẫn xác thực ciphertext do ứng dụng ấy tạo.

## 10. Nonce của AES-GCM: không tái sử dụng dưới cùng key

Với AES-GCM, việc tái sử dụng **cùng nonce trên cùng key** là lỗi nghiêm trọng có thể phá bảo mật. Một cách triển khai phổ biến dùng nonce 96-bit được sinh ngẫu nhiên bằng `SecureRandom`, nhưng vẫn cần thiết kế giới hạn số lần mã hóa và probability/risk theo quy mô thực tế.

Không dùng:

~~~text
nonce = 000000000000
nonce = currentUnixSecond
nonce = hash(tenantId) truncated
```

vì dễ tái sử dụng.

Nếu khối lượng mã hóa cực lớn hoặc multi-writer dùng chung key, cần giao thức nonce allocation/rotation và giới hạn sử dụng khóa theo hướng dẫn thuật toán/thư viện cụ thể.

## 11. AAD ràng buộc ciphertext với ngữ cảnh

**Associated Authenticated Data (AAD)** là metadata **không cần mã hóa** nhưng phải được xác thực cùng ciphertext.

Ví dụ:

~~~text
tenantId = tenant-17
entityType = User
entityId = user-100
fieldName = phone
schemaVersion = 3
```

Khi copy `phoneEncrypted` sang User khác, decrypt với AAD của User đích sẽ thất bại.

Lợi ích:

- Giảm nguy cơ chuyển ciphertext giữa tenants/entities.
- Ràng buộc mục đích sử dụng khóa và field.
- Phát hiện metadata bị thay đổi sai.

Nhưng nếu các trường AAD có thể thay đổi, cần một **canonical encoding và migration strategy**. Ví dụ đổi `userId` hoặc rename field mà không còn AAD cũ sẽ làm ciphertext không giải mã được.

## 12. AAD không phải một chuỗi tùy tiện

Cách nối thiếu phân cách:

~~~text
tenant="ab", id="c" -> "abc"
tenant="a", id="bc" -> "abc"
```

có collision về biểu diễn.

Cần encoding không nhập nhằng, ví dụ length-prefix, canonical CBOR/JSON với quy tắc cố định hoặc một schema binary. Ví dụ minh họa:

~~~text
AAD = encode([
  "pii",
  1,
  tenantId,
  entityType,
  entityId,
  fieldName
])
```

Phải giữ cách encode qua các phiên bản ứng dụng hoặc đưa `aadFormatVersion` trong envelope.

## 13. Khóa dữ liệu và khóa bao bọc

Hai loại khóa trong **envelope encryption**:

- **DEK (Data Encryption Key):** mã hóa plaintext của document/field/object.
- **KEK (Key Encryption Key):** bao bọc (*wrap*) DEK hoặc dùng KMS bảo vệ DEK.

Sơ đồ:

~~~mermaid
flowchart TD
  KMS["KMS/HSM holds KEK"] --> Wrap["Wrap/Unwrap DEK"]
  DEK["Random Data Encryption Key"] --> Wrap
  DEK --> Enc["AEAD encrypt document"]
  Enc --> Blob["Ciphertext + nonce + tag + wrapped DEK"]
  Wrap --> Blob
  Blob --> Dec["Authorized decrypt"]
  KMS --> Dec
~~~

Có thể có nhiều tầng hierarchy, chẳng hạn root key → tenant KEK → DEKs. Chọn cấu trúc để hỗ trợ quyền truy cập, scale, rotation và recovery — không thêm tầng chỉ vì muốn sơ đồ phức tạp.

## 14. Vì sao không dùng một master key để mã hóa mọi document trực tiếp?

Nếu mọi record dùng cùng một master key trong ứng dụng:

- Khóa phải được dùng liên tục, exposure rộng.
- Nonce management có thể khó ở quy mô lớn.
- Rotation đòi re-encrypt lượng dữ liệu lớn.
- Không dễ cô lập per tenant/dataset.
- Ứng dụng dễ lưu key lâu dài trong config/memory.
- Audit key usage không rõ theo data domain.

Với envelope encryption, có thể sinh **DEK theo object/segment/tenant scope** và chỉ lưu **wrapped DEK**. KEK có thể được giữ trong KMS/HSM với policies và logging phù hợp.

## 15. Một envelope được lưu thế nào?

Một object lưu trữ có thể có:

~~~json
{
  "encryptionFormatVersion": 2,
  "algorithm": "AES-256-GCM",
  "kmsKeyRef": "alias/pii-tenant-key",
  "wrappingKeyId": "immutable-key-identifier",
  "wrappedDek": "base64...",
  "nonce": "base64-12-byte-nonce",
  "aadFormatVersion": 1,
  "ciphertext": "base64...",
  "sourceEntityVersion": 81
}
~~~

Chú ý:

- `alias` có thể đổi đích, nên **không chỉ dựa vào alias hiện tại** để tìm khóa giải mã ciphertext lịch sử.
- `wrappedDek` là ciphertext của DEK, không phải plaintext key.
- `ciphertext` cần chứa/đi kèm authentication tag theo encoding thực.
- Các metadata dùng để chọn khóa/algorithm phải được kiểm tra theo protocol.
- `sourceEntityVersion` là business version, **không phải crypto key version**.
- Key IDs không phải secrets theo định nghĩa thông thường, nhưng metadata vẫn cần bảo vệ theo policy.

## 16. Mã hóa một record: luồng chuẩn

~~~text
1. Identify tenant/data classification.
2. Authorize actor to create/update.
3. Generate DEK with approved cryptographic random source.
4. Obtain KMS-wrapped DEK and/or generate key using KMS.
5. Generate unique nonce.
6. Canonicalize AAD.
7. AEAD encrypt plaintext.
8. Persist ciphertext + nonce + wrapped DEK + key references.
9. Clear transient sensitive material where practical.
10. Record audit metadata without plaintext secrets.
~~~

Nếu database update thất bại, không log plaintext/DEK để debug. Nếu KMS không có mặt, hệ cần **fail closed** cho dữ liệu không thể mã hóa theo policy, không âm thầm lưu plaintext “tạm thời”.

## 17. Giải mã một record: luồng chuẩn

~~~text
1. Authenticate and authorize read.
2. Read encrypted envelope.
3. Validate format, algorithm and tenant/key scope.
4. Resolve immutable key identity/version.
5. Ask KMS to unwrap wrapped DEK using correct context/policy.
6. Reconstruct the exact canonical AAD.
7. AEAD decrypt and authenticate.
8. Use plaintext in the smallest necessary scope.
9. Avoid caching/logging plaintext against policy.
10. Emit audit/metric for key usage without exposing secrets.
~~~

Nếu AEAD tag check thất bại, có thể do payload bị sửa, AAD mismatch, sai key hoặc format lỗi. **Không tự chữa bằng cách bỏ authentication tag**.

## 18. Java AES-GCM: một ví dụ an toàn về cấu trúc

Ví dụ này thực hiện **mã hóa và giải mã payload với DEK đã được cấp**. Nó không quản lý KMS/rotation và không phải thư viện crypto production hoàn chỉnh.

~~~java
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.security.SecureRandom;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class AeadCodec {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    public record Encrypted(byte[] nonce, byte[] ciphertext) {}

    public static Encrypted encrypt(
            SecretKey dek,
            byte[] plaintext,
            byte[] aad) throws Exception {

        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.ENCRYPT_MODE,
            dek,
            new GCMParameterSpec(TAG_BITS, nonce)
        );
        cipher.updateAAD(aad);

        byte[] ciphertext = cipher.doFinal(plaintext);
        return new Encrypted(nonce, ciphertext);
    }

    public static byte[] decrypt(
            SecretKey dek,
            Encrypted envelope,
            byte[] aad) throws Exception {

        if (envelope.nonce().length != NONCE_BYTES) {
            throw new IllegalArgumentException("Invalid nonce length");
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.DECRYPT_MODE,
            dek,
            new GCMParameterSpec(TAG_BITS, envelope.nonce())
        );
        cipher.updateAAD(aad);
        return cipher.doFinal(envelope.ciphertext());
    }

    public static byte[] exampleAad(String tenantId, String entityId) {
        // Chỉ minh họa: production cần encoding không nhập nhằng
        // và version hóa format.
        return ("tenant=" + tenantId + ";id=" + entityId)
            .getBytes(StandardCharsets.UTF_8);
    }
}
~~~

Trong Java, GCM tag thường được nối vào kết quả `doFinal` theo provider. Serialize `nonce` và `ciphertext` theo một envelope có version rõ ràng. Mã hóa **mỗi lần tạo nonce mới**, không tự dùng lại đối tượng Cipher giữa nhiều luồng.

## 19. Điểm phải bổ sung để code production an toàn

Đoạn code trên cố tình để phần sau cho kiến trúc:

- DEK được cấp từ nơi nào?
- AEAD algorithm và key length được cấu hình/allowlist ra sao?
- Làm sao giới hạn số encryptions với một DEK?
- AAD canonical encoding/schema/version?
- Key scope theo tenant/dataset?
- Lưu wrapped DEK và metadata nguyên tử ra sao?
- Decrypt authorization gắn vào request context thế nào?
- Key rotation/re-encrypt/re-wrap?
- Rate limiting khi KMS unreachable?
- Xử lý secret memory, tracing và audit?
- Bảo vệ ciphertext size/format trước untrusted inputs?

**Không coi một class AES-GCM chạy unit test là toàn bộ thiết kế key management.**

## 20. Java sinh khóa dùng cho thử nghiệm

Ví dụ tạo một AES-256 key để thử codec:

~~~java
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256);
SecretKey testDek = generator.generateKey();
~~~

Đây là **ví dụ test/local demonstration**, không phải lời khuyên sinh khóa cho từng request rồi bỏ mất nó. Trong hệ dùng KMS, cần sử dụng **envelope key generation, wrapping và lưu wrapped DEK** để có thể giải mã sau restart/restore.

Không ghi `testDek.getEncoded()` vào log hoặc commit plaintext key vào repository.

## 21. Java exception khi GCM authentication thất bại

GCM có thể ném một exception như `AEADBadTagException` khi không xác thực được tag (tùy provider).

Đừng:

~~~java
catch (Exception e) {
    return ciphertext;  // Sai: trả bytes không xác thực.
}
~~~

Đường xử lý an toàn:

- Dừng và không sử dụng plaintext chưa xác thực.
- Phân loại lỗi thành `DECRYPT_AUTHENTICATION_FAILED`.
- Không thử lần lượt mọi key tùy ý nếu protocol không chỉ rõ các key versions cần thiết.
- Đối chiếu key reference, format version và AAD.
- Cảnh báo/quarantine record nếu cần.
- Không trả ciphertext hoặc stack trace chứa secret ra API.
- Không “fix” bằng cách tắt authentication.

## 22. KMS là gì?

**Key Management Service (KMS)** cung cấp khả năng tạo, dùng, giới hạn quyền, audit và quản lý vòng đời khóa theo dịch vụ.

Các chức năng thường thấy tùy provider:

- Create/import key material theo những cơ chế được hỗ trợ.
- Generate data keys.
- Encrypt/decrypt hoặc wrap/unwrap.
- Grant/revoke IAM permissions.
- Alias và key metadata.
- Automatic/manual rotation.
- Disable/enable.
- Schedule deletion/cancel deletion.
- Audit cryptographic key usage.
- Policy theo encryption context.
- Multi-region/cross-account design theo capability.

Không giả định mọi provider/KMS đều có cùng command names hoặc export được key material.

## 23. HSM và ranh giới khóa

**Hardware Security Module (HSM)** hỗ trợ giữ và thao tác với khóa trong một ranh giới bảo mật chuyên dụng. Một cloud KMS có thể dùng HSM ở tầng implementation.

Tuy nhiên:

- Có HSM không tự làm IAM least privilege.
- Có KMS không tự bảo vệ plaintext trong JVM.
- Một ứng dụng được quyền `Decrypt` có thể vẫn lộ plaintext nếu bị chiếm quyền.
- High-availability/recovery của HSM/KMS phải nằm trong kế hoạch DR.
- Key provenance/custody phải được audit.

Chọn KMS/HSM theo threat model, compliance, operational model và recovery requirements.

## 24. Phân cấp khóa theo phạm vi dữ liệu

Ví dụ:

~~~text
Environment root trust boundary
  Production PII KEK
    Tenant A DEKs
    Tenant B DEKs
  Production analytics KEK
    Daily export DEKs

Staging keys are separate
Development keys are separate
~~~

Lợi ích:

- Không để staging tự giải mã production.
- Có thể revoke một tenant/data class mà không phá mọi dữ liệu.
- Phân quyền service theo nhiệm vụ.
- Audit key usage rõ hơn.
- Hạn chế blast radius.

Không tự tạo một KMS key cho mỗi document nếu chi phí, quota và vận hành không phù hợp; **envelope DEK** có thể giải quyết yêu cầu phân tách với fewer KEKs.

## 25. KEK và DEK có vòng đời khác nhau

| Vòng đời | KEK | DEK |
|---|---|---|
| Tạo | KMS/HSM theo policy | Cryptographic random, thường qua KMS |
| Lưu | Provider boundary/secure escrow | Dạng wrapped; plaintext chỉ tạm thời |
| Dùng | Wrap/unwrap/cryptographic operation | Mã hóa plaintext payload |
| Rotation | Key version/rewrap strategy | Re-encrypt data hoặc cấp DEK mới |
| Audit | Key API calls, permissions | Record keyRef/crypto metadata |
| Xóa | Cực kỳ nhạy vì nhiều DEKs phụ thuộc | Chỉ an toàn khi không còn ciphertext cần giải mã |
| Recovery | KMS HA/escrow/restore access | Wrapped DEK còn nguyên và KEK usable |

Không dùng một câu “rotate keys” để gộp hai lớp. Đổi KEK có thể thực hiện bằng **rewrap** DEKs; đổi DEK đòi **decrypt và re-encrypt** payload tương ứng.

## 26. Re-wrap khác re-encrypt

**Re-wrap DEK:**

~~~text
Old envelope:
  ciphertext encrypted under DEK-X
  wrapped DEK-X under KEK-v1

After rewrap:
  ciphertext unchanged
  same DEK-X
  wrapped DEK-X under KEK-v2
~~~

Nếu provider cho phép và protocol đúng, rewrap có thể tránh đọc/ghi lại toàn bộ plaintext.

**Re-encrypt data:**

~~~text
Decrypt ciphertext with DEK-X
Generate DEK-Y
Encrypt plaintext with DEK-Y and fresh nonce
Store new ciphertext, wrapped DEK-Y
~~~

Lần thứ hai chạm toàn bộ payload và phải xử lý concurrency, TTL, retries và index/projection side effects.

## 27. Rotation không đồng nghĩa xóa key cũ ngay lập tức

Sau khi KEK key material/alias được rotate, **ciphertext lịch sử có thể vẫn phụ thuộc phiên bản cũ**.

Một số KMS quản lý key material versions dưới cùng logical key và tự hỗ trợ decrypt ciphertext cũ theo contract. Trong thiết kế envelope khác, phải lưu `wrappingKeyVersion` hoặc một immutable key reference.

Trình tự an toàn:

1. Tạo/activate key mới.
2. Chuyển **new writes** sang key mới.
3. Giữ old key decrypt-only khi còn ciphertext cũ.
4. Rewrap/re-encrypt theo migration plan.
5. Verify coverage, backups, archived versions.
6. Thử restore bằng keys đang giữ.
7. Chỉ disable/delete key cũ sau khi chứng minh không còn dependency và đạt retention policy.

Một alias đổi đích **không tự làm mọi bản backup cũ được mã hóa lại**.

## 28. Key deletion là hành động có thể không đảo ngược

Nếu key material dùng để giải mã dữ liệu cũ bị tiêu hủy vĩnh viễn và không có recovery/escrow hợp lệ, ciphertext có thể không còn giải mã được.

Cần quy trình:

- Approval theo vai trò và nguyên tắc hai người khi policy yêu cầu.
- Inventory phụ thuộc của key.
- Check backup/snapshot/archives/DR copies.
- Quarantine/disable trước khi schedule deletion nếu phù hợp.
- Waiting period và khả năng hủy delete theo KMS.
- Audit trail.
- Recovery testing.
- Không cho một automation dựa vào “key đã lâu không dùng” rồi tự xóa.

**Không nhầm `DisableKey` với `DeleteKey`**. Disable thường có thể đảo ngược trong điều kiện cho phép; xóa key material vĩnh viễn thì không.

## 29. Secret, credential và key không cùng một thứ

- Database password: credential để authentication.
- IAM role: identity được cấp quyền gọi KMS/DB.
- API token: bearer credential, không phải AEAD DEK.
- Encryption key: material dùng cho cryptographic operation.
- Wrapped DEK: ciphertext, không phải một secret plaintext.
- Key ID/alias: metadata để định vị khóa.

Quản lý riêng:

- Credential rotation.
- IAM policy/grant review.
- Encryption key rotation.
- Data re-encryption/rewrap.
- Audit logs.

Đổi database password không tự bảo đảm encryption key đã rotate.

## 30. Không lưu key cạnh ciphertext ở dạng plaintext

Một lỗi:

~~~text
database row:
  ciphertext: ...
  encryptionKey: "raw-32-byte-key"
```

Kẻ lấy database có cả ciphertext và key.

Cũng nguy hiểm nếu:

- Master key nằm trong same bucket backup không được bảo vệ.
- Key được hard-code trong Java JAR.
- Environment variables bị dump/log công khai.
- Key nằm trong ticket/CI artifact.
- Key được copy sang test.
- API lỗi trả key material.

Dùng KMS/HSM và key access policies; wrapped DEK có thể cùng envelope vì nó **chỉ giải mã được với KEK được kiểm soát**.

## 31. IAM: quyền mã hóa và giải mã nên tách

Một service ingestion chỉ cần ghi dữ liệu mã hóa không nhất thiết cần quyền đọc plaintext của toàn bộ hồ sơ.

Mô hình:

| Role | Quyền phù hợp theo use case |
|---|---|
| Writer service | Tạo data key/encrypt trong key scope |
| Authorized reader | Decrypt đúng key scope |
| Search indexer | Chỉ đọc những derived fields cho phép |
| Backup job | Tạo backup, không nhất thiết decrypt dữ liệu |
| Restore operator | Quyền restore infrastructure, không mặc định quyền xem plaintext |
| Break-glass custodian | Quyền khẩn cấp có approval, audit và thời hạn |
| Security admin | Quản lý policies, không tự là mọi quyền decrypt |

Thực tế quyền KMS và API operations có thể có dependency; thiết kế policy phải theo provider IAM semantics. **Separation of duties** tốt hơn việc cấp `kms:*` cho tất cả pods.

## 32. Encryption context là một ràng buộc hữu ích

Một số KMS hỗ trợ **encryption context** hoặc AAD cho thao tác wrap/unwrap. Ví dụ khái niệm:

~~~text
Purpose = "tenant-pii"
TenantId = "tenant-17"
DataClass = "phone-number"
```

Khi decrypt/wrapping, context phải khớp theo protocol. Policy có thể giới hạn role chỉ dùng khóa với context hợp lệ.

Cần nhớ:

- Context không nhất thiết bí mật; có thể xuất hiện trong audit logs.
- Không đưa PII trực tiếp vào context nếu policy cấm.
- Context phải ổn định và được version hóa.
- Không dùng raw user input tự nhận TenantId mà không xác thực.
- Dùng key scope/IAM kết hợp context, không thay thế authorization trong ứng dụng.

## 33. AWS KMS envelope workflow cho Java

Một ứng dụng dùng **AWS SDK for Java v2** có thể gọi `GenerateDataKey` để nhận:

- `Plaintext`: DEK dạng rõ, chỉ dùng tạm để mã hóa trong memory.
- `CiphertextBlob`: dạng wrapped DEK, được lưu cùng encrypted record.
- Metadata key (theo API).

Luồng:

~~~mermaid
flowchart TD
    Java["Java writer"] --> Gen["KMS GenerateDataKey under CMK/KMS key"]
    Gen --> Plain["Plaintext DEK (transient)"]
    Gen --> Wrapped["Encrypted DEK blob"]
    Plain --> AES["Java AES-GCM encrypt"]
    AES --> Store["NoSQL ciphertext envelope"]
    Wrapped --> Store
    Store --> Reader["Java reader"]
    Reader --> Dec["KMS Decrypt wrapped DEK"]
    Dec --> AES2["AEAD verify/decrypt payload"]
~~~

`KMS key` là cách gọi logical key trong dịch vụ. Một số terminology/region behavior thay đổi theo phiên bản provider; đừng gắn cứng cấu trúc nội bộ HSM vào application protocol.

## 34. Java AWS KMS SDK v2: tạo data key

Ví dụ minh họa API:

~~~java
import software.amazon.awssdk.services.kms.KmsClient;
import software.amazon.awssdk.services.kms.model.DataKeySpec;
import software.amazon.awssdk.services.kms.model.GenerateDataKeyRequest;
import software.amazon.awssdk.services.kms.model.GenerateDataKeyResponse;
import java.util.Map;

public GenerateDataKeyResponse generateDek(
        KmsClient kms, String keyId, String tenantId) {

    GenerateDataKeyRequest request =
        GenerateDataKeyRequest.builder()
            .keyId(keyId)
            .keySpec(DataKeySpec.AES_256)
            .encryptionContext(Map.of(
                "Purpose", "TenantPii",
                "TenantId", tenantId
            ))
            .build();

    return kms.generateDataKey(request);
}
~~~

`plaintext()` trong response là sensitive key material. Đoạn code chưa sử dụng/giải phóng response, và không phải complete encryption workflow. Trong thực tế cần giới hạn scope memory, không log response, không cache plaintext DEK tùy tiện và lưu `ciphertextBlob()` cùng đúng key metadata/context.

## 35. Java AWS KMS SDK v2: unwrap data key

Ví dụ API:

~~~java
import software.amazon.awssdk.core.SdkBytes;
import software.amazon.awssdk.services.kms.KmsClient;
import software.amazon.awssdk.services.kms.model.DecryptRequest;
import software.amazon.awssdk.services.kms.model.DecryptResponse;
import java.util.Map;

public DecryptResponse unwrapDek(
        KmsClient kms,
        byte[] wrappedDek,
        String tenantId) {

    DecryptRequest request = DecryptRequest.builder()
        .ciphertextBlob(SdkBytes.fromByteArray(wrappedDek))
        .encryptionContext(Map.of(
            "Purpose", "TenantPii",
            "TenantId", tenantId
        ))
        .build();

    return kms.decrypt(request);
}
~~~

Với symmetric KMS ciphertext được dịch vụ hỗ trợ, blob có thể mang metadata để xác định key theo semantics API. Có thể/đôi khi nên truyền immutable key ID khi policy yêu cầu; không dựa vào một alias di động để “tự chọn key mới” khi giải mã lịch sử.

`DecryptResponse.plaintext()` chứa DEK rõ: phải coi là secret. Java immutable `SdkBytes`/`SecretKeySpec` có thể tạo copies trong memory; việc xóa một `byte[]` không bảo đảm xóa mọi bản sao do GC/runtime tạo.

## 36. KMS call không nên thực hiện cho mọi byte dữ liệu

Envelope encryption thường dùng KMS để wrap/unwrap **DEK**, còn mã hóa payload diễn ra trong ứng dụng bằng AEAD. Điều này giúp:

- Giảm số bytes gửi KMS.
- Giảm latency/network overhead.
- Kiểm soát key access theo policy.
- Tận dụng local crypto cho payload lớn.

Nhưng vẫn có chi phí KMS request, throttling và outage. Nếu dùng plaintext DEK cache, phải giới hạn TTL/size, process memory exposure và quyền ứng dụng. **Hiệu năng không biện minh để lưu KEK/DEK thô vĩnh viễn trong config**.

## 37. KMS service outage và behavior cần thiết

Khi KMS không reachable:

- New encrypt operations cần data key có thể không thực hiện được.
- Decrypt operations chưa có key trong memory cache có thể fail.
- Ứng dụng có thể vẫn đọc những dữ liệu public/unprotected theo policy.
- Retry quá mạnh làm KMS và ứng dụng bị khuếch đại tải.
- “Fail-open” bằng cách lưu plaintext là lỗi bảo mật nghiêm trọng.
- User-facing API cần phân loại tạm không khả dụng khác dữ liệu hỏng.

Cần **timeouts, bounded retries, regional strategy, cache policy**, circuit breaker và metrics. Không giả định KMS region A outage tự động cho phép giải mã bằng một key bất kỳ ở region B.

## 38. Key availability là một dependency của dữ liệu

RPO/RTO không chỉ tính cho database files:

~~~text
DB available: yes
Backup available: yes
KMS key enabled: no
Decrypt permission in DR: no
Application usable: no
```

Vì thế **key availability SLO** phải được đưa vào DR planning:

- KMS endpoint/region.
- Key material/key identity availability.
- IAM grants/policies.
- Network/routing.
- Audit services.
- Recovery operators và approval procedures.
- Automation/secrets for application startup.

Một replica database ở region khác nhưng vẫn cần đúng key unavailable không phải một **DR độc lập**.

## 39. Key alias là tên thuận tiện, không phải backup khóa

Ví dụ:

~~~text
alias/orders-pii -> key-2026-01
rotate
alias/orders-pii -> key-2026-11
```

Nếu record cũ chỉ ghi alias và hệ đã thay key đích, đọc lại record có thể dùng sai key, trừ khi KMS ciphertext/protocol cho phép tự xác định material cũ trong cùng logical key.

Thiết kế nên ghi **immutable key reference/ciphertext metadata**, quản lý key versions và retention. Alias phù hợp để chọn key **cho new encryptions**, không phải quy tắc suy đoán version giải mã.

## 40. Chuẩn bị khóa trước khi mất khóa

Danh sách tối thiểu:

1. Inventory mọi key và owner.
2. Mapping key → datasets/tenants/backups.
3. Định nghĩa trạng thái `enabled`, `disabled`, `pending deletion`, `rotated`.
4. Xác định key **có thể export/backup hay không** theo provider.
5. Thiết kế DR region/account permissions.
6. Chứng minh khôi phục được một snapshot bằng encrypted records thật.
7. Lưu encrypted metadata và old key versions cần thiết.
8. Quản lý recovery approval và break-glass.
9. Giám sát key deletion/disable/grant changes.
10. Giữ runbook offline khi control plane bị sự cố.

Không đợi sau khi xóa khóa mới kiểm tra “có thể copy key ra không”; nhiều KMS **không hỗ trợ xuất plaintext key material**.

## 41. Khôi phục khóa có nhiều nghĩa khác nhau

**Tình huống A — Khóa tồn tại nhưng quyền không còn:** có thể khôi phục IAM/grant sau khi xác thực đúng người và policy.

**Tình huống B — Khóa bị disable:** có thể enable lại nếu dịch vụ và trạng thái cho phép.

**Tình huống C — Khóa pending deletion:** có thể hủy deletion trong waiting period nếu provider hỗ trợ và được phép.

**Tình huống D — Provider region/control plane outage:** cần plan redundancy/DR có key access đã chuẩn bị.

**Tình huống E — Key material thực sự đã bị tiêu hủy không có escrow:** không thể “brute force khôi phục” ciphertext AES-GCM đúng cách; phải dùng bản plaintext/backup khác được mã hóa dưới khóa còn tồn tại nếu có.

**Tình huống F — Khóa bị lộ:** việc khôi phục khả dụng không phải mục tiêu duy nhất; cần containment, rotation/re-encryption, forensic và đánh giá dữ liệu lộ.

Không có một thao tác “restore key” chung cho mọi tình huống.

## 42. Mất quyền Decrypt khác mất key material

Ví dụ KMS trả lỗi access denied:

~~~text
Key exists, enabled
Service account no longer has Decrypt permission
~~~

Khắc phục đúng là kiểm:

- IAM identity của ứng dụng.
- Key policy và grants.
- Encryption context policy.
- Region/account.
- Key state.
- Network endpoint.
- Explicit deny, SCP/permission boundaries khi dùng cloud IAM.

**Không tạo key mới rồi thử giải mã ciphertext cũ**. Key mới có material khác; không giải mã được ciphertext đã wrap dưới key cũ nếu chưa có quy trình re-encryption/rewrap hợp lệ.

## 43. Khóa bị vô hiệu hóa

KMS key disabled có thể gây:

- New encryptions fail.
- Wrapped DEKs cũ không unwrap được.
- Restored backup load vào DB được nhưng application read fails.

Runbook:

1. Xác nhận đúng key identity và account/region.
2. Phân biệt planned disable và security incident.
3. Xác định caller permissions và trạng thái thực.
4. Xin approval để enable lại nếu an toàn.
5. Test decrypt một record được phép.
6. Kiểm audit/history và kiểm phạm vi ảnh hưởng.
7. Không tự bypass bằng một tài khoản vượt quyền khác.

Nếu disable vì nghi ngờ compromise, việc enable lại phải thuộc incident decision, không chỉ để hết alert.

## 44. Khóa đang chờ xóa

Một số KMS có **scheduled deletion** với thời gian chờ. Trong thời gian này key có thể không sử dụng được và có khả năng hủy schedule.

Cần:

- Alert ngay khi schedule deletion.
- Inventory phụ thuộc.
- Review approval trail và intent.
- Cancel theo quy trình nếu là nhầm lẫn.
- Kiểm thử decrypt sau khi khôi phục state phù hợp.
- Block xóa tiếp cho tới khi xác minh backup dependency.

Không giả định mọi key provider đều có cách hủy hoặc thời gian chờ giống nhau.

## 45. Key material bị mất vĩnh viễn

Nếu key material không còn ở KMS/HSM/escrow hợp lệ, và tất cả copies dữ liệu đều được mã hóa bằng material ấy, khả năng giải mã thực tế có thể không còn.

Phương án khả thi tùy trạng thái:

- Restore từ một **bản dữ liệu được mã hóa bằng key khác còn usable**.
- Restore từ backup plaintext được kiểm soát trước đây (nếu được cho phép và có tồn tại).
- Dùng một escrow key material được thiết kế trước, theo protocol và approval.
- Phục hồi dữ liệu từ upstream/source độc lập có quyền và completeness.
- Chấp nhận data loss và báo sự cố theo governance nếu không còn nguồn.

Không hứa “KMS support sẽ khôi phục được mọi key đã xóa”; không có cơ sở để bảo đảm điều đó.

## 46. Key escrow không phải bản key plaintext trong wiki

**Key escrow** có thể là cơ chế dự phòng bảo quản key material hoặc khả năng unwrap theo phê duyệt/quy trình nghiêm ngặt.

Một thiết kế hợp lý có thể cần:

- HSM-backed export/wrapping nếu provider hỗ trợ.
- Multi-party approval/dual control.
- Split knowledge/quorum custody theo chính sách.
- Bản sao được mã hóa dưới recovery trust boundary độc lập.
- Audit và kiểm soát access.
- Physical/region separation.
- Regular recovery exercise.
- Version/format compatibility.

Nhưng **nhiều KMS-generated keys không export được plaintext master key**; escrow phải được thiết kế bằng service feature được hỗ trợ hoặc external key material strategy, không sao chép bí mật trái chính sách.

## 47. Hai người phê duyệt không đồng nghĩa chia khóa mật mã

Một hệ có thể yêu cầu hai approvers trước khi cấp quyền break-glass. Đây là **quy trình vận hành**.

Shamir's Secret Sharing hoặc split-knowledge custody là **cơ chế bảo quản cryptographic material** có cấu trúc khác. Không tự dùng công thức chia secret tùy ý hoặc gửi từng nửa key qua chat/email rồi gọi là an toàn.

Nếu dùng secret sharing thật, cần library/protocol chuyên dụng, procedures về threshold, entropy, share authenticity, restore và bảo quản shares độc lập.

## 48. KMS multi-region không tự tương đương “cùng key ở mọi nơi”

Các provider hỗ trợ **regional keys, replicas hoặc multi-region key constructs** với semantics cụ thể. Những khác biệt cần xét:

- Key ID và ARN/namespace theo region.
- Material relationship giữa primary/replica keys.
- Rights/grants/policies ở từng region.
- Encryption context.
- KMS quotas và endpoints.
- Replication delay/cutover.
- Multi-account ownership.
- Import/external key store constraints.

Không sao chép ciphertext từ region A sang B rồi mặc định region B có thể decrypt bằng alias trùng tên. **DR test cần unwrap ciphertext thực tế ở region đích**.

## 49. Cross-account backup: key access là phần bắt buộc

Một account khác có thể nhận một snapshot mã hóa, nhưng restore có thể không usable nếu:

- Key gốc ở account cũ không cho phép account mới sử dụng.
- Key policy/grants thiếu.
- Provider hạn chế sharing đối với loại key.
- Key bị vô hiệu hóa/deleted.
- Snapshot encryption mode không cho copy như giả định.
- Cấu hình tenant/security context khác.
- Recovery environment không truy cập KMS.

Cần một **bản copy được re-encrypt theo key DR được hỗ trợ**, hoặc chính sách cross-account decrypt đã kiểm thử. Không dùng alias cùng tên làm bằng chứng.

## 50. RPO/RTO của dữ liệu phải đi kèm RTO khóa

- **RPO:** tối đa lượng dữ liệu được phép mất theo thời gian.
- **RTO:** thời gian tối đa để dịch vụ phục hồi.
- **Key recovery time:** thời gian khôi phục khả năng dùng đúng key và authorization.
- **Decryptability coverage:** tỷ lệ dữ liệu backup có thể giải mã và kiểm chứng thành công.

Ví dụ:

~~~text
DB restore duration: 25 minutes
Application deployment: 10 minutes
KMS/IAM recovery approval: 2 hours
Actual service recovery: > 2 hours
```

Nếu RTO được cam kết là 1 giờ, kế hoạch này thất bại dù restore database hoàn tất nhanh.

---

## 51. MongoDB: xác định đang mã hóa ở tầng nào

MongoDB có những lựa chọn tùy **edition, deployment, server/driver versions và managed provider**:

- Encryption at rest của volume/cloud storage.
- Storage engine encryption theo capability/edition.
- Client-Side Field Level Encryption (CSFLE) cho dữ liệu field.
- Queryable Encryption trong các phiên bản/giới hạn hỗ trợ.
- TLS cho connections/replication.
- Backup/snapshot encryption theo dịch vụ quản lý.

Không coi một chuỗi `mongodb://` có TLS là bằng chứng dữ liệu trên disk đã mã hóa, hoặc một encrypted disk là bằng chứng mọi trường nhạy đã được client-side encrypted.

## 52. MongoDB CSFLE: máy chủ không cần thấy plaintext trường đã mã hóa

Với client-side field encryption, Java driver/lib hỗ trợ mã hóa một số fields trước khi gửi DB theo cấu hình và capabilities.

Lợi ích:

- DB lưu ciphertext cho fields được bảo vệ.
- Database user không có key không giải mã được plaintext.
- Có thể phân quyền key theo data domain.

Giới hạn:

- Query/index/search trên field mã hóa bị ràng buộc theo mode/version.
- Migration/key vault và drivers phải tương thích.
- Data leakage qua metadata, query patterns hoặc fields khác vẫn có thể xảy ra.
- Application có decrypt rights vẫn nhìn plaintext.
- Backup phải giữ được **key vault metadata và external KMS access** tương ứng.

Không tự triển khai AES rồi tuyên bố đạt đủ guarantees của CSFLE/Queryable Encryption; nên dùng official driver/capability đúng phiên bản nếu lựa chọn đó phù hợp.

## 53. MongoDB Queryable Encryption có trade-off

Trong những cấu hình được hỗ trợ, Queryable Encryption hướng tới cho phép một số truy vấn trên dữ liệu đã mã hóa mà giảm mức độ plaintext server phải thấy, nhưng:

- Chỉ hỗ trợ những loại truy vấn/field/index theo phiên bản.
- Có metadata/index/storage overhead.
- Không hoàn toàn giấu access patterns.
- Có yêu cầu key management và client compatibility.
- Có ràng buộc migration, schema và limits.

Không nói “đã mã hóa thì vẫn lọc/sort/range tùy ý như plaintext”. Khi chọn field encryption, hãy xác định **access patterns trước**.

## 54. MongoDB key vault và external KMS

Trong các mô hình CSFLE/Queryable Encryption, **data key metadata** có thể được lưu trong key vault collection, còn key material/KEK được bảo vệ qua KMS provider theo contract.

Nếu restore chỉ business collections mà bỏ qua key vault hoặc mất quyền tới KMS key, dữ liệu encrypted fields có thể không decrypt.

Một runbook restore cần xác nhận:

1. Backup các collections và key vault metadata cần thiết.
2. Key vault access controls.
3. KMS provider/key identifiers.
4. Key versions và rotation states.
5. Correct driver and library support.
6. Restore order và migration compatibility.
7. Decrypt test với authorized identity.
8. Key audit trail.

## 55. MongoDB snapshot không là bản sao khóa

Giả sử snapshot chứa:

~~~text
users collection ciphertext
encryption key vault encrypted data key records
```

Nếu KEK ở external KMS đã mất, **key vault record thường không đủ** để khôi phục plaintext DEK. Nó chứa wrapped material và metadata, không phải recovery master key.

Do đó lưu snapshot và lưu quyền truy cập/trạng thái KMS là **hai nhiệm vụ độc lập nhưng phải đồng bộ**.

## 56. DynamoDB: encryption at rest là tính năng được quản lý

DynamoDB có encryption at rest trong dịch vụ; các lựa chọn và quyền quản lý keys phụ thuộc key mode (AWS owned, AWS managed hoặc customer managed KMS key theo cấu hình dịch vụ).

Cần xem:

- Key type và control plane.
- Table encryption settings.
- GSI/streams/backups/export scope.
- Key policy và IAM.
- Restore/copy/snapshot cross-region/account.
- Key disable/deletion impact.
- CloudTrail/monitoring và service integration.

Mã hóa at rest của DynamoDB **không đồng nghĩa SDK Java tự field-encrypt tất cả AttributeValues**. Nếu threat model cần ứng dụng mã hóa trước khi lưu, đó là một lớp riêng.

## 57. DynamoDB: customer managed keys và availability

Với customer-managed KMS key, user có nhiều quyền kiểm soát rotation, policy và lifecycle hơn, nhưng phải chịu trách nhiệm không vô hiệu hóa/xóa key còn cần thiết.

Kịch bản:

~~~text
Table exists
KMS key disabled or policy denies service usage
DynamoDB table access or recovery becomes constrained
```

Hành vi chi tiết phụ thuộc trạng thái table, service integration và provider semantics. Không đoán rằng mọi request đều lỗi ngay lập tức hoặc dữ liệu tự được giải mã bằng key khác.

Runbook phải có monitoring **key state + table encryption status + restore usability**.

## 58. Cassandra: file/volume encryption và client encryption

Trong Apache Cassandra và các triển khai tương thích, chức năng at-rest encryption phụ thuộc distribution, phiên bản và hạ tầng:

- OS/cloud volume/disk encryption.
- Commitlog/SSTable encryption nếu bản triển khai có capability phù hợp.
- Backup/snapshot encryption.
- TLS between nodes/clients.
- Client-side field encryption khi cần threat model cao hơn.

Không mặc định Apache Cassandra mọi phiên bản có built-in TDE giống một managed proprietary service. Phải đọc capability/contract của deployment thật.

Nếu data SSTables mã hóa nhưng snapshot được copy sang object storage không có policy phù hợp, đường backup có thể làm tăng rủi ro.

## 59. Cassandra: repair/compaction và encryption overhead

Cassandra/LSM engines có:

- SSTables.
- Memtables/commitlog.
- Compaction.
- Repair/streaming.
- Snapshots/backups.

Encryption layer có thể thêm CPU, IO, key access và operational coupling vào mỗi bước. Đo:

- Read/write p95/p99.
- Compaction throughput/queue.
- Snapshot/restore speed.
- Encryption/decryption CPU.
- Disk capacity.
- Key availability khi node restart.
- Multi-node key access.

Nếu một node cần KMS để mount/decrypt dữ liệu khi khởi động, khả năng **cluster recovery sau outage** phụ thuộc KMS ở thời điểm ấy.

## 60. Redis: dữ liệu thường xuyên ở trong RAM

Redis dùng memory để phục vụ reads/writes, nhưng có thể tạo:

- RDB snapshots.
- AOF persistence logs.
- Backups/export files.
- Replicas.
- Client/network buffers.

Mã hóa volume hoặc managed persistence giúp bảo vệ files khi lưu, nhưng Redis process có thể giữ plaintext trong RAM. Không coi “Redis được đặt trên encrypted disk” là bảo vệ Redis plaintext khỏi user có Redis command permissions hoặc process memory compromise.

Nếu cache chứa PII, cần xét TTL/retention, encryption in application, access controls, TLS, logs và backup/export policy.

## 61. Redis: cache không mặc định là “ít quan trọng”

Một Redis cache có thể chứa:

- Session tokens.
- User profile snapshots.
- Authorization-derived state.
- Payment workflow metadata.
- API response cache.

Ngay cả khi cache có thể rebuild từ source, **rò dữ liệu cache vẫn là incident**. Đồng thời rotate encryption key chỉ ở source nhưng để plaintext data lâu trong Redis có thể vi phạm policy.

Bản thiết kế phải có **data classification và cache retention** cùng các kho NoSQL chính.

## 62. Search index, CDC và analytics cũng cần mã hóa

Một Product có encrypted PII trong source, nhưng event publisher có thể phát plaintext vào Kafka, consumer ghi vào Search và analytics export sang S3.

Sơ đồ cần kiểm:

~~~text
Authoritative NoSQL (encrypted field)
    -> Outbox payload
    -> CDC/broker
    -> Search index
    -> Analytics export
    -> Backup
```

Nếu một chặng lưu plaintext nhạy cảm, **bảo vệ tại source không đủ**. Cần quyết định data minimization, encryption of downstream stores, tokenization và quyền truy cập cho từng consumer.

Không encrypt payload theo cách làm downstream không thể thực hiện nghiệp vụ mà không thiết kế key policies tương ứng.

## 63. Backup encryption ở ngoài DB

Một bản backup có thể được encrypt bằng:

- Storage provider server-side encryption.
- Client-side encryption trước khi upload.
- Object-level envelope encryption.
- Backup software encryption.

Các lựa chọn có thể xếp tầng nhưng phải rõ:

- Key nào dùng để encrypt?
- Người nào có thể decrypt?
- Metadata nào cần?
- Có sao chép sang account/region khác không?
- Có expiration/retention và rotation ra sao?
- Restore có yêu cầu KMS/network không?
- Backup có immutable/air-gapped protection không?

Một file `.backup.enc` không tự chứng minh thuật toán, provenance hoặc restore usability.

## 64. Không dùng cùng một key duy nhất cho source và mọi backup

Nếu một KEK phục vụ toàn bộ production data và tất cả DR backups, việc key bị xóa hoặc account bị compromise có thể ảnh hưởng đồng thời cả hai.

Có thể xem:

- Backup copy re-encrypted dưới **DR key boundary** riêng khi dịch vụ hỗ trợ.
- Cross-account key policies có kiểm soát.
- Offline/independent escrow nếu threat model yêu cầu và provider hỗ trợ.
- Versioned wrapped DEKs.
- Separation of duties.
- Immutable backups chống thao tác xóa nhầm.
- Kiểm thử restore dưới DR identity.

Nhưng nhiều key hơn làm key inventory/rotation phức tạp; phải đủ metadata để biết backup nào cần key nào.

## 65. Quy tắc “backup và key cùng tồn tại” chưa đủ

Một restore thành công đòi:

\[
\text{Restorable}
=\text{Backup intact}
\land\text{Key usable}
\land\text{Metadata complete}
\land\text{Authorization valid}
\land\text{Compatible decryptor}
\]

Đây là biểu thức logic mô tả các điều kiện **cần thiết trong mô hình minh họa**, không bao quát hết network, dependencies và consistency.

Có backup+key nhưng application không còn hỗ trợ schema/algorithm cũ vẫn có thể fail. Cần giữ **format version, migration scripts và code/decryptor compatibility**.

## 66. Key rotation cần phối hợp với backup retention

Giả sử:

~~~text
Backup retention: 7 years
Current KEK rotated every 12 months
Archived snapshots contain wrapped DEKs from older periods
```

Nếu tổ chức xóa old KEK material sau 6 tháng mà không rewrap/re-encrypt backups, các backups được giữ 7 năm có thể không decrypt được.

Phải tính:

- Retention dài nhất.
- Legal hold.
- Replica/backups ngoài vùng chính.
- Snapshot copies và exports.
- Key rotation schedule.
- Rewrap coverage.
- Old decrypt compatibility.
- Deletion lifecycle approvals.

**Key retention ít nhất phải tương thích vòng đời ciphertext phụ thuộc**, trừ khi ciphertext đã được chuyển an toàn sang keys mới và verified.

## 67. Rewrap backup mà không phá tính toàn vẹn

Một quy trình backup rewrap có thể:

1. Inventory từng backup object và wrapped DEK.
2. Xác minh old KEK decrypt rights.
3. Unwrap DEK trong trusted boundary hoặc dùng KMS re-encrypt API nếu được hỗ trợ.
4. Wrap DEK dưới DR/new KEK.
5. Lưu envelope metadata **atomically/versioned**.
6. Giữ old envelope cho tới khi verified.
7. Thử decrypt sample và restore toàn bộ dataset tiêu biểu.
8. Ghi evidence và provenance.
9. Sau đủ coverage mới retire key cũ.

Không ghi đè wrapped DEK cũ trước khi new envelope được ghi bền và verify.

## 68. Re-encrypt dữ liệu đang có concurrent writes

Nếu một migration đọc record v10, giải mã, mã hóa dưới DEK mới rồi ghi, trong lúc đó business update tạo v11, migration có thể **ghi đè dữ liệu mới bằng payload cũ**.

Cần:

~~~text
Read payload + business version v10
Decrypt / re-encrypt
Conditional update:
  WHERE businessVersion == v10
  SET new encryption envelope
```

Nếu CAS fail, re-read current state rồi xử lý lại. Re-encryption nên thay **encryption metadata/ciphertext** mà không reset business version tùy tiện; có thể có `encryptionRevision` riêng để track migration.

## 69. Re-encryption có thể ảnh hưởng indexes và CDC

Một migration cập nhật ciphertext cho toàn collection có thể:

- Tạo write amplification.
- Gây replication lag.
- Phát CDC events dù business value không đổi.
- Kích hoạt Search projection rebuild thừa.
- Gây cache invalidation.
- Tăng storage churn và backups.
- Cạnh tranh writes nghiệp vụ.

Cần filter/metadata để consumer phân biệt **cryptographic re-encryption** với **business semantic change**, nếu event contract cho phép.

Thử tải, batch/rate limit và bảo đảm source-of-truth correctness trước khi chạy trên production.

## 70. Key migration cần checkpoint và rollback

Một migration job nên có:

~~~text
jobId
sourceKeyVersion
targetKeyVersion
batchSize
lastProcessedCursor
successCount
conflictCount
retryCount
irrecoverableErrorCount
verifiedCount
start/end time
```

Checkpoint phải bền, không skip record chưa hoàn tất. `lastProcessedCursor` có thể không đủ khi scan thay đổi concurrent; cần xác định scan/snapshot semantics và reconciliation.

Rollback có thể cần giữ cả wrapped DEK cũ và new trong giai đoạn chuyển đổi. Không disable old key khi migration mới được 99,9% nhưng còn những records cuối chưa verified.

## 71. Key management metadata nên được inventory theo nguồn

Một inventory:

| Dữ liệu/nguồn | Key scope | Phiên bản | Backup dependency | Recovery owner |
|---|---|---|---|---|
| User PII fields | Per environment/tenant KEK | v3 | Source+key vault backups | Security+Data platform |
| MongoDB volume | Storage/KMS integration | provider-managed ID | Snapshots/volumes | Infra |
| DynamoDB tables | Customer managed KMS | logical key | PITR/export copies | Cloud platform |
| Redis RDB backups | Backup encryption key | key revision | Object storage archives | Platform |
| Search index | Managed disk encryption | key ID | Snapshots | Search team |
| Analytics exports | Object-level key | per export manifest | Long-term archives | Data engineering |

Số liệu cần được cập nhật bằng discovery/metadata automation khi có thể. Không chỉ dựa vào bảng Excel thủ công luôn mới đúng.

## 72. Xây bản đồ dependency ngược của khóa

Câu hỏi cần trả lời trước disable/delete:

~~~text
Which datasets require key K?
Which backups require K?
Which applications can decrypt through K?
Which DR region/account must access K?
Which historical ciphertext still uses K?
Which child DEKs are wrapped by K?
Which workflows will fail if K is unavailable?
```

Một API key-use counter bằng 0 trong tháng gần đây **không có nghĩa không còn backup 5 năm tuổi phụ thuộc**.

Dependency inventory cần kết hợp key reference trong ciphertext, backup manifests, KMS audit logs và dữ liệu quản trị retention.

## 73. Cryptographic erasure và giới hạn của nó

**Cryptographic erasure** là chủ đích làm dữ liệu đã mã hóa không còn giải mã được bằng cách tiêu hủy khóa cần thiết.

Nó chỉ đạt mục tiêu khi:

- Dữ liệu thật sự chỉ có các bản ciphertext được bảo vệ bởi khóa đó.
- Không còn plaintext copies/caches/backups/dumps khác.
- Không tồn tại bản sao khóa ở các nơi khác không kiểm soát.
- Không có alternative KEK/escrow giúp giải mã.
- Mã hóa được triển khai đúng.
- Recovery/retention obligations và legal holds được xem xét.

Không tuyên bố “đã xóa key nên dữ liệu biến mất khỏi mọi cache, log và bên thứ ba”. Khi xóa theo yêu cầu privacy, cần phối hợp physical/logical deletion của các copies theo policy.

## 74. Khi nghi khóa bị lộ: mục tiêu khác khi khóa bị mất

Khóa bị mất: nguy cơ **mất khả dụng**.

Khóa bị lộ: nguy cơ **mất bí mật và/hoặc toàn vẹn**.

Một incident nghi key compromise có thể cần:

1. Xác định scope và bằng chứng.
2. Hạn chế/cắt quyền attacker.
3. Rotate/wrap/re-encrypt theo security plan.
4. Đánh giá ciphertext và plaintext đã có thể bị đọc.
5. Kiểm logs, export, key usage và side channels.
6. Revoke compromised credentials/tokens.
7. Giữ forensic evidence theo quy trình.
8. Thông báo/ứng phó theo luật và chính sách nếu áp dụng.
9. Không tự disable key trước khi có plan bảo toàn khả năng decrypt/migrate.

**Chỉ rotate alias** có thể không khắc phục ciphertext lịch sử đã bị lộ nếu attacker đã lấy cả key cũ.

## 75. Một trường hợp: dữ liệu được mã hóa nhưng key policy quá rộng

Giả sử mọi service có:

~~~text
kms:Decrypt on all production keys
```

Một service ít quan trọng bị chiếm quyền có thể decrypt nhiều datasets mà nó không nên truy cập.

Giải pháp:

- Key separation theo data class.
- Role-based least privilege.
- Encryption context restrictions.
- Network/identity policies.
- No direct decrypt for backup-only roles.
- Detection of unusual decrypt usage.
- Per-service KMS authorization review.

Mã hóa không có phân quyền khóa là một ranh giới bảo mật yếu.

## 76. Khóa trong CI/CD pipeline

Một lỗi hay gặp:

~~~text
Deploy pipeline:
  download production key material
  write it into environment file
  bake it into Docker image
~~~

Image/container registries, logs và artifact caches có thể lưu key lâu dài.

Một hướng tốt hơn:

- Application workload identity/short-lived credentials.
- KMS calls at runtime with least privilege.
- Secret manager cho credentials cần thiết.
- No plaintext master keys in CI.
- Redacted logging.
- Separate staging/prod trust boundaries.
- Audit authorization changes.

Không cần biết plaintext KEK để build Java JAR.

## 77. Key custody trong container và JVM

Java runtime có thể chứa:

- Plaintext DEK trong heap byte arrays.
- Decrypted fields dưới dạng `String` immutable.
- Serialization buffers.
- HTTP response bodies.
- Traces/debug logs.
- Core/heap dumps.
- Swap/temp files.

Những khía cạnh cần quản lý:

- Giảm thời gian giữ plaintext.
- Hạn chế object copies và byte array lifetimes khi có thể.
- Tắt/giới hạn heap dumps theo security policy.
- Không dump secrets ở crash reporter.
- Process/container isolation.
- Least privilege cho debug/attach.
- TTL/size cho decrypted cache, hoặc không cache.
- Logging redaction.

**Gọi `Arrays.fill(keyBytes, 0)` là hygiene có ích ở một số trường hợp, không phải chứng minh Java heap không còn bản sao khóa.**

## 78. Không lưu plaintext trong logs và metrics

Một trace:

~~~text
encryptedFieldCiphertext = ...
kmsKeyRef = ...
operation = decrypt
result = success
durationMs = 20
~~~

có thể đủ để chẩn đoán mà không log:

~~~text
plaintext phone number
raw DEK
full DecryptResponse
authorization token
```

Ngay cả ciphertext cũng có thể là sensitive metadata hoặc nằm trong retention policy; tránh log payload lớn không cần thiết.

Metric labels nên là `keyClass`, `operation`, `status`, `region` thay vì raw user ID hoặc từng key ID nếu cardinality cao.

## 79. Không để crypto operations che lỗi dữ liệu

Nếu decrypt fail, phân biệt:

| Dấu hiệu | Khả năng | Hướng xử lý |
|---|---|---|
| KMS AccessDenied | IAM/key policy/context | Kiểm identity/policy, không thử key ngẫu nhiên |
| KMS Disabled | Key state | Quy trình restore/access approval |
| Key not found | Sai region/account/key ID hoặc đã xóa | Dependency inventory, DR |
| KMS throttled/timeout | Capacity/network/service | Bounded retry/backoff |
| AEAD tag invalid | Wrong key/AAD/corrupt payload | Quarantine, forensic |
| Unsupported format | Schema/algorithm migration | Compatible decoder/upcaster |
| Missing wrapped DEK | Backup/serialization incomplete | Restore metadata |
| Business record missing | Source/key lookup | Không tự gọi là crypto failure |

Không catch mọi exception rồi trả HTTP 404 vì người dùng có thể hiểu nhầm entity không tồn tại, trong khi thực tế khóa bị disable.

## 80. Query/index trade-off khi mã hóa trường

Một field như email thường cần:

~~~text
lookup user by normalized email
```

AES-GCM dùng nonce ngẫu nhiên cho mỗi lần encrypt nên **không cho phép equality lookup bằng so ciphertext thông thường**. Hai plaintext giống nhau có thể tạo ciphertext khác nhau.

Các hướng thiết kế:

- Dùng ứng dụng đọc bằng key khác rồi decrypt.
- Dùng hệ **Queryable Encryption** được hỗ trợ.
- Dùng tokenization directory phù hợp.
- Dùng blind index với keyed HMAC theo canonicalized value, giới hạn leakage và authorization.
- Tách encrypted display value với lookup token.
- Không dùng deterministic IV cho AES-GCM để “có thể index”.

Mỗi hướng có leakage, rotation và query limitations riêng.

## 81. Blind index bằng HMAC: dùng thận trọng

Một blind index có thể tính:

~~~text
normalized = canonicalizeEmail(email)
blindIndex = HMAC-SHA256(indexKey, normalized)
```

Sau đó lưu ciphertext email và blindIndex. Nhưng:

- Equality/frequency patterns có thể bị lộ.
- Normalization sai tạo collision semantics về business.
- Index key phải tách khỏi encryption key.
- HMAC key rotation có thể đòi reindex toàn bộ.
- Dùng cùng indexKey cho nhiều tenants làm tăng cross-tenant correlation.
- Low-entropy plaintext dễ bị dò nếu attacker có oracle/khả năng query HMAC.
- Không thay authorization/unique business constraints.

Không dùng một SHA-256 unsalted digest của email rồi gọi là bảo vệ PII: email có thể bị đoán qua dictionary.

## 82. Search, sort và range trên ciphertext không mặc nhiên được hỗ trợ

Một API yêu cầu:

~~~text
find users where salary > 20000000
sort by encryptedLastName
full-text search encryptedNote
```

AEAD thông thường không hỗ trợ trực tiếp những truy vấn ấy mà vẫn bảo mật như plaintext opaque.

Có thể cần:

- Schema phân chia field có thể lộ/không thể lộ.
- Protected search token/index.
- Encryption scheme chuyên dụng đã được đánh giá.
- Search service được phép xem một bản projection tối thiểu.
- Queryable Encryption có giới hạn support.
- Chấp nhận read/filter tại application cho tập nhỏ.
- Thay đổi access pattern.

Không tự xây order-preserving encryption cho dữ liệu nhạy chỉ vì muốn giữ sort.

## 83. Field encryption và schema migration

Một bản ghi có thể có:

~~~json
{
  "encryptionFormatVersion": 1,
  "nameEncrypted": "...",
  "keyRef": "key-old"
}
~~~

Bản mới dùng format v2. Ứng dụng cần:

- Decoder hỗ trợ v1 và v2 trong giai đoạn migration.
- Writer chỉ phát format v2 khi rollout.
- Backfill/rewrap/re-encrypt có checkpoint.
- Version/generation ordering ngăn ghi đè data mới.
- Thử restore snapshot v1 bằng application version đủ phù hợp.
- Retire v1 decoder/key sau khi không còn dependency.

Không triển khai code chỉ đọc v2 rồi xóa key cũ khi backup vẫn chứa v1.

## 84. Mã hóa có thể tăng latency và chi phí

Các thành phần:

- AES-GCM CPU.
- Serialization/base64 size.
- KMS GenerateDataKey/Decrypt RTT.
- Wrapped DEK storage overhead per record.
- Memory allocations/GC.
- Key cache miss.
- Network to KMS region.
- Retry khi KMS throttles.
- Index limitations khiến query phải đọc nhiều dữ liệu hơn.

Cần đo cả p50/p95/p99 **encryption/decryption path**, KMS calls/sec, error rate, crypto CPU và query plan sau khi chuyển encrypted schema.

Không lấy benchmark AES throughput một mình để dự báo end-to-end API latency.

## 85. Một mô hình chi phí envelope encryption

Giả định:

~~~text
1,000 new encrypted records/s
one GenerateDataKey per record
500 fresh decrypts/s
cache hit ratio for key unwrap = 80%
```

Ước lượng naive:

~~~text
GenerateDataKey calls: 1,000/s
Decrypt calls for cache misses: 100/s
```

Nhưng thực tế phụ thuộc:

- DEK sharing/caching scope.
- Per-tenant vs per-record key design.
- Auth policies.
- Read access patterns.
- Key cache invalidation.
- KMS quotas/cost/latency.
- Multi-region behavior.

Không chọn DEK caching quá rộng chỉ để giảm calls nếu làm mất isolation hoặc tăng blast radius.

## 86. Khi KMS throttling gây hàng đợi

Nếu Java decrypt 10.000 records/s và mỗi record cần KMS, rate limit của KMS có thể thành bottleneck:

~~~text
Java request
  -> encrypted record read
  -> KMS Decrypt queue
  -> KMS throttling
  -> retries
  -> HTTP p99 grows
```

Biện pháp có thể:

- Cache plaintext DEK trong thời gian cực ngắn theo policy/SDK.
- Batch xử lý cùng object/key nếu supported.
- Dùng dedicated data keys/envelope granularity hợp lý.
- Rate limit & backpressure.
- Quota review.
- Region locality.
- Prewarm trong DR drills có kiểm soát.

Không bypass Decrypt bằng plaintext fallback.

## 87. SLO về giải mã và khả năng khôi phục

Ngoài API latency:

- `DecryptSuccessRate`.
- `KmsPermissionDenied`.
- `KmsTimeout/ThrottleRate`.
- `UnknownKeyReference`.
- `AeadAuthenticationFailureRate`.
- `OldKeyUsageCount`.
- `CiphertextByKeyVersion`.
- `PendingDeletionDependentRecords`.
- `BackupDecryptabilityCoverage`.
- `RestoreDrillDuration`.
- `KeyRecoveryDrillPassRate`.

Một key không được dùng trong API online nhưng vẫn cần cho backup; vì thế **old-key API call count bằng 0 không được xem là đủ để xóa**.

## 88. Một encrypted backup cần manifest

Ví dụ:

~~~yaml
backupId: backup-2026-11-14
source:
  databaseEngine: MongoDB
  clusterId: catalog-prod
  snapshotPoint: recorded
encryption:
  mode: envelope
  algorithm: AES-256-GCM
  formatVersion: 2
  wrappingKey:
    provider: KMS
    immutableKeyRef: recorded
    region: recorded
    account: recorded
  wrappedDekLocations:
    - backupManifest
  aadFormatVersion: 1
  ciphertextChecksums: recorded
restore:
  supportedDecoderVersions:
    - 1
    - 2
  requiredIdentity: approvedDrRole
  testRecordIds: maskedAuthorizedSamples
retention:
  expiresAt: policyDefined
  legalHold: evaluated
validation:
  objectIntegrity: pending
  decryptCanary: pending
  restoreDrill: pending
~~~

Đây là **YAML tài liệu mẫu**, không phải metadata mà MongoDB/AWS tự sinh. Không đưa raw secrets/PII vào backup manifest. Manifest phải được bảo vệ toàn vẹn và quyền sửa để kẻ tấn công không thể thay key references tùy ý.

## 89. Hash/Checksum và AEAD tag phục vụ mục tiêu khác nhau

- **Checksum/hash** giúp phát hiện data corruption ở mức bytes nếu so với giá trị tin cậy.
- **AEAD tag** xác thực ciphertext và AAD với secret key.
- **Backup manifest signature/MAC** có thể bảo vệ metadata/provenance.
- **DB consistency checks** xác nhận cấu trúc dữ liệu/database valid.

Một SHA-256 digest lưu cùng file không có ký/MAC có thể bị kẻ tấn công đổi cùng file; nó hữu ích cho accidental corruption nhưng không tự chống sửa ác ý.

Một AEAD-decrypted sample thành công không chứng minh **toàn bộ backup** không thiếu records. Cần cả dataset coverage và restore test.

## 90. Backup integrity khác decryptability

Ví dụ object storage có checksum đúng, nhưng KMS key đã bị delete. `sha256sum` vẫn pass, còn decrypt fail.

Ngược lại KMS key vẫn hoạt động nhưng backup thiếu tệp/index/commit log cần phục hồi point-in-time; decrypt từng object có thể pass nhưng database consistency fail.

Đánh giá gồm:

1. Backup bytes hoàn chỉnh.
2. Metadata/manifest khớp.
3. Crypto decrypt/authentication pass.
4. Database restore/consistency pass.
5. Application schema/decoder pass.
6. Business integrity checks pass.
7. Recovery time đáp ứng RTO/RPO.

**Không có một chỉ số đơn lẻ thay thế được bài restore thực tế.**

## 91. Khôi phục vào môi trường cách ly

Một recovery drill nên dùng:

~~~text
Isolated DR environment
  -> Approved restore operator
  -> Temporary least-privileged KMS grant
  -> Restore encrypted backup
  -> Verify key references and data
  -> Decrypt canary records with authorized test identity
  -> Run correctness assertions
  -> Securely destroy temporary copies after drill
~~~

Tránh khôi phục PII thật vào một tài khoản test có quyền quá rộng. Nếu phải dùng dữ liệu thật để chứng minh decryptability, dùng network isolation, access logging, retention/cleanup và policies đã phê duyệt.

## 92. Canary record kiểm tra được điều gì?

Một **encrypted recovery canary** là record kiểm thử/được cho phép đã được mã hóa dưới key cần giám sát. Khi recovery, ứng dụng decrypt và so nội dung/format kỳ vọng.

Canary giúp phát hiện sớm:

- Wrong key/KMS region.
- IAM deny.
- Missing wrapped DEK.
- Format decoder incompatible.
- AAD mismatch.
- Algorithm/key-state errors.

Nhưng **một canary không chứng minh toàn bộ dữ liệu/keys đã recoverable**. Nên có canary theo key class, legacy versions, archive generations và representative backups.

## 93. Đo khôi phục với lịch thử cụ thể

Một chương trình có thể chọn (theo risk/SLO):

- Daily/weekly KMS key-state monitoring.
- Regular encrypted backup integrity verification.
- Monthly test decrypt representative canaries.
- Quarterly full isolated restore simulation.
- Annual cross-region/account DR exercise.
- Before key retirement: targeted restore under old key.
- After major crypto/schema upgrade: backward compatibility test.
- After policy changes: DR identity access test.

Cadence là **ví dụ lập kế hoạch**, không phải tiêu chuẩn bắt buộc chung. Data classification/compliance và RTO/RPO quyết định tần suất phù hợp.

## 94. Một runbook khôi phục khóa không nên chỉ là danh sách CLI

Cần có:

- Incident classification.
- Role và emergency approval contacts.
- Immutable key IDs, regions/accounts.
- Dataset/backup dependency map.
- Key states và policy/grant requirements.
- Các bước kiểm decrypt có kiểm soát.
- Backup/snapshot restore sequence.
- Fallback khi KMS outage.
- Constraints đối với compromised keys.
- Evidence collection và audit.
- Decision points, stop conditions.
- Escalation khi không thể recover.
- Post-incident inventory/migration updates.

Nếu runbook nằm trong cùng một hệ không truy cập được khi cloud account bị khóa, nhóm ứng cứu có thể mất cả hướng dẫn. Cần bản offline/khác trust boundary đã kiểm soát.

## 95. Không cho phép “fallback sang plaintext” khi KMS lỗi

Một anti-pattern:

~~~java
try {
    saveEncrypted(record);
} catch (KmsUnavailableException e) {
    savePlaintext(record); // Không an toàn.
}
~~~

Khi KMS outage, mọi bản ghi mới có thể bị lưu plaintext và dễ bị bỏ sót sau phục hồi.

Thay thế an toàn tùy nghiệp vụ:

- Fail closed, trả tạm không khả dụng.
- Bền vững hóa request trong một vùng được mã hóa và có key availability độc lập.
- Queue workload theo chính sách bảo mật, không lưu plaintext tạm trên ổ đĩa.
- Chuyển sang region/KMS path đã kiểm thử tương thích.
- Giữ idempotency cho retries.
- Báo incident nếu ingestion bị đình trệ.

## 96. Không tự disable key theo một metric hết traffic

Ví dụ key `KEK-2019` không có online decrypt calls 90 ngày, nhưng vẫn giải mã archival backup tới năm 2029.

Một automation dọn khóa có thể nhầm key không còn dùng và schedule deletion.

Policy retirement phải xác minh:

- Active data dependencies.
- Archived backups.
- Legal hold.
- Offline/disaster recovery use.
- Historical decoder/format support.
- Key escrow/recovery custody.
- Business signoff.
- Kết quả restore drill có liên quan.

**Không dùng “last used” làm tiêu chí duy nhất xóa khóa.**

## 97. Khôi phục sau ransomware có yếu tố khóa

Nếu attacker có quyền:

- Xóa source data.
- Xóa backup.
- Disable/schedule delete KMS keys.
- Sửa IAM grants.
- Rewrite snapshots/backup manifests.

Thì chỉ có replication hoặc daily snapshots không đủ. Cần:

- Immutable/backups với retention lock theo capability.
- Separate account/role trust boundary.
- Protected key policies và deletion safeguards.
- MFA/approval cho privileged operations.
- Monitoring của key disable/delete.
- Recovery credentials nằm ngoài vùng compromise.
- Provenance/integrity verification.
- Restore rehearsals.

Đánh giá cùng **blast radius của tài khoản IAM**, không chỉ thuật toán AES mạnh bao nhiêu.

## 98. Ma trận chọn lớp mã hóa theo loại dữ liệu

| Loại dữ liệu | At-rest encryption | Field/client encryption | Vấn đề bổ sung |
|---|---|---|---|
| Public catalog | Thường dùng theo chính sách hạ tầng | Thường không bắt buộc | Integrity, query performance |
| Tenant profile/PII | Có | Cân nhắc theo threat model | Query/index, consent, data retention |
| Payment token | Có | Tokenization/encryption theo tiêu chuẩn áp dụng | Không tự lưu raw payment credentials |
| Password verifier | Có | Không lưu password mã hóa để so sánh | Password hashing chuyên dụng |
| Session tokens | Có | Cân nhắc keyed digest/encryption | TTL, revocation, cache |
| Audit records | Có | Theo độ nhạy | Integrity, append-only, access policies |
| Search projections | Có | Chỉ những field cần đọc được | Data minimization, access patterns |
| Backups/exports | Có | Envelope riêng khi cần | Key escrow, DR, retention |
| Logs/metrics | Storage encryption | Redaction ưu tiên | Tránh plaintext/DEK in logs |

Mục tiêu không phải “mã hóa mọi trường bằng mọi giá”; mã hóa phải đáp ứng **threat model và access patterns** mà không vô tình bỏ qua tính đúng đắn, sự riêng tư và khả năng khôi phục.

## 99. Một hợp đồng mã hóa tối thiểu cho Repository

Một Java Repository có thể để domain layer không phải biết chi tiết AES/KMS, nhưng không nên che mất failure modes.

~~~java
public interface ProtectedProfileStore {
    SaveEncryptedOutcome saveProfile(
        TrustedTenantContext tenant,
        String profileId,
        SensitiveProfile profile,
        long expectedVersion
    );

    DecryptOutcome readProfile(
        TrustedTenantContext tenant,
        String profileId
    );
}
~~~

Các kiểu là domain placeholders. Kết quả có thể phân biệt:

- Saved và version mới.
- Conflict vì expectedVersion không match.
- Not found/permission denied.
- KMS temporarily unavailable.
- Key disabled/deleted/missing.
- Unsupported encryption format.
- AEAD authentication failed.
- Unknown database write outcome.

**Không biến một lỗi giải mã thành document rỗng** rồi để caller vô tình overwrite dữ liệu có ciphertext còn nguyên.

## 100. Ứng dụng cần tách businessVersion và encryptionRevision

Một document:

~~~json
{
  "_id": "p-101",
  "businessVersion": 82,
  "encryptionRevision": 5,
  "encryptionFormatVersion": 2,
  "encryptedPhone": {
    "keyRef": "immutable-key-id",
    "wrappedDek": "...",
    "nonce": "...",
    "ciphertext": "..."
  }
}
~~~

Một migration thay wrapping key mà **không đổi số điện thoại** có thể tăng `encryptionRevision`, giữ `businessVersion` theo contract.

Điều này giúp:

- CDC consumers không nhầm migration với customer update.
- CAS migration tránh ghi đè.
- Auditors biết payload đã được re-encrypt.
- Backfill tiến từng record.
- Dễ nhận biết key versions cần retirement.

Nếu schema/business policy yêu cầu mọi physical update tăng version, phải định nghĩa quy ước khác nhưng vẫn **phân biệt semantic change** với crypto maintenance.

## 101. Conditional migration pseudocode

~~~text
for each encrypted record:
  record = readCurrentState()
  if record.keyVersion == targetKeyVersion:
      mark already migrated
      continue

  oldPlaintext = decryptWithAuthorizedOldKey(record)
  newEnvelope = encryptWithTargetKey(
      plaintext=oldPlaintext,
      aad=canonicalAad(record.identity)
  )

  updated = conditionalReplaceEncryptionFields(
      id=record.id,
      expectedBusinessVersion=record.businessVersion,
      expectedEncryptionRevision=record.encryptionRevision,
      newEnvelope=newEnvelope,
      newEncryptionRevision=record.encryptionRevision + 1
  )

  if not updated:
      re-read and retry in bounded work queue
  else:
      verify decrypt on new envelope
      mark record complete
~~~

Mọi side effect phải theo policy. Nếu process crash sau update nhưng trước checkpoint, lần chạy lại phải nhận ra `targetKeyVersion` và tiếp tục idempotently, không sinh ra endless rewrites.

## 102. Quyền truy cập khóa theo tenant không tự thay tenant authorization

Giả sử Java service có quyền decrypt KEK của tenant A, nhưng API lại dùng `tenantId` do client tự truyền. Attacker có thể gửi `tenantId=A` để đọc dữ liệu.

Cần:

1. Authenticate caller.
2. Resolve **trusted tenant identity** từ server-side context.
3. Authorize record action.
4. Lookup document với tenant scope.
5. Decrypt bằng key đã phân quyền.
6. Dùng AAD gắn đúng tenant/record/field.
7. Audit access theo policy.

Encryption context của KMS giúp giảm blast radius nhưng **không thay bước 1–4**.

## 103. Không đưa key ID bí mật giả vào client payload

Một API không nên cho client tự chọn bất kỳ `kmsKeyId` trong request body mà server sẽ gọi `Decrypt`:

~~~json
{
  "profileId": "p-101",
  "kmsKeyId": "some-other-tenant-key"
}
~~~

Khóa, key policy và tenant scope nên do **trusted server configuration + record metadata đã xác minh** quyết định. Nếu application chấp nhận keyRef từ ciphertext lưu trữ, phải kiểm tra keyRef thuộc tập keys cho phép với data class/tenant đó.

Nếu không, service có thể trở thành một **decrypt oracle** hoặc truy cập nhầm khóa của tenant khác.

## 104. Key policy và network identity phải hợp lệ ở DR

Một key có thể thuộc đúng account và đang enabled nhưng:

- DR workload không có IAM role/trust relationship.
- Key policy chỉ cho phép principal ở môi trường production cũ.
- Network egress tới KMS bị chặn.
- Required VPC endpoint hoặc private DNS chưa có.
- Encryption context policy đòi tag không tồn tại trong DR.
- Security approval chưa được cấp trong RTO.

Diễn tập DR cần dùng **chính role và topology dự kiến của DR**, không chỉ account administrator có quyền tối cao.

## 105. Tạo môi trường DR mà không làm lộ dữ liệu thật

Một phép thử trong môi trường khôi phục nên có:

- Isolated network.
- Dedicated KMS grants hoặc DR-specific roles.
- Restricted operator access.
- Audit logging.
- No default public endpoints.
- No uncontrolled debug dump.
- No downstream messages/notifications từ bản phục hồi.
- Sanitized test endpoints.
- TTL/cleanup cho tài nguyên tạm.
- Verify delete/cleanup sau drill.

Nếu restore một backup production có dữ liệu nhạy cảm, môi trường DR thử nghiệm vẫn phải được xử lý như **môi trường chứa dữ liệu production**, dù chỉ tồn tại vài giờ.

## 106. Bản sao phục hồi phải được kiểm tra độc lập

Một backup trong cùng tài khoản/cloud region/trust boundary với source có thể cùng chịu ảnh hưởng bởi:

- Credential compromise.
- KMS policy mistake.
- Destructive automation.
- Region outage.
- Backup deletion.
- Network isolation.

Thiết kế có thể cần bản sao ở tài khoản/vùng độc lập với role/retention/key boundary phù hợp. Nhưng **độc lập không đồng nghĩa giải mã tự động được**; phải kiểm KMS/cross-account grants và supported copy/re-encryption workflow.

## 107. Tiêu chí “restore drill đạt” nên cụ thể

Một restore drill có thể đánh giá:

~~~text
[ ] Backup selected by timestamp is complete.
[ ] Source and manifest checksums verified.
[ ] Correct key IDs/versions resolved.
[ ] KMS decrypt under DR identity succeeds.
[ ] No plaintext keys copied into scripts/logs.
[ ] Restored NoSQL engine opens datasets.
[ ] Encrypted fields decrypt and AEAD tags validate.
[ ] Indexes, key vault, CDC positions consistent.
[ ] Row/document counts meet expectations.
[ ] Business canaries preserve invariants.
[ ] Application reads required records.
[ ] RPO/RTO measured from incident trigger.
[ ] Cleanup of temporary production data confirmed.
[ ] Evidence and exceptions recorded.
~~~

**Restore one record** là một kiểm tra canary hữu ích, nhưng không thay hoàn toàn drill dữ liệu có coverage và logic nghiệp vụ.

## 108. Khóa và backup phải có ownership

Ví dụ một RACI ở mức khái niệm:

| Hoạt động | Service owner | Security | Cloud/DB platform | DR operator |
|---|---|---|---|---|
| Chọn data classification | Accountable | Consulted | Consulted | Informed |
| Tạo KMS key/policy | Consulted | Approves | Implements | Informed |
| Quản lý app key references | Implements | Reviews | Supports | Informed |
| Rotation và migration | Owns data semantics | Approves policy | Runs infrastructure | Tests restore |
| Enable/disable khẩn cấp | Consulted | Approves incident action | Executes | Verifies |
| Backup integrity | Consulted | Audits | Implements | Verifies |
| Full recovery drill | Validates business | Observes | Restores platform | Coordinates |
| Delete old key | Confirms no dependencies | Approves | Executes | Confirms DR coverage |

Phân công cụ thể tùy tổ chức. Không giao toàn bộ trách nhiệm mã hóa và xóa khóa cho một tài khoản automation không có giám sát.

## 109. Điều kiện bắt buộc trước khi retire một key

Một **retirement gate** có thể yêu cầu:

~~~text
Key: KEK-v1
New writes using v1: zero (confirmed)
Active records using v1: zero (scanned)
Archived wrapped DEKs using v1: zero or verified rewrapped
Backups requiring v1: zero or recoverable under alternate approved key
Legal hold/recovery obligations: reviewed
Restore test under new key: passed
No out-of-date application instances still need v1: verified
Security approval: recorded
Rollback window: completed
```

Nếu một điều kiện chưa chứng minh được, đừng xóa key chỉ vì kế hoạch rotation đến hạn.

## 110. Key rotation và microservice deployments không đồng thời

Một hệ nhiều pods/services:

~~~text
Pod A supports format v1 only
Pod B supports formats v1 and v2
Writer C begins emitting format v2
```

Pod A có thể không decrypt records mới. Migration an toàn thường là:

1. Deploy **read compatibility** trước.
2. Verify all active readers support new format/key.
3. Switch writers to new format.
4. Observe and migrate old data in background.
5. Retire old reader support sau coverage.
6. Retire old key sau backup dependency verification.

Đây là mô hình **expand-and-contract** cho cryptographic schema, không chỉ đổi config ở một nơi.

## 111. Key compromise: migration cần tính lại phạm vi lộ

Khi key cũ có thể bị lộ, rewrap cùng một DEK không nhất thiết giải quyết:

~~~text
Attacker has:
  old KEK
  old wrapped DEK
  old ciphertext
```

Nếu attacker đã lấy đủ những thành phần này, họ có thể giải mã bản đã đánh cắp ngay cả khi bạn rewrap DEK bằng KEK mới. Với mục tiêu giảm future exposure, có thể cần **tạo DEK mới và re-encrypt payload**, rotate credentials, chặn truy cập trái phép và đánh giá những dữ liệu đã bị truy xuất.

Không tuyên bố key rotation “thu hồi được” plaintext đã bị nhìn thấy trước đây.

## 112. Mã hóa backup trước khi upload không thay bảo mật bucket

Một object backup đã được mã hóa vẫn cần:

- Deny public access.
- Least privilege IAM.
- Object versioning/immutable retention.
- Deletion safeguards.
- Audit of reads/copies.
- Secure transfer/TLS.
- Data lifecycle/retention.
- Object/manifest integrity verification.

Ciphertext có thể bị **xóa, sửa, ransom hoặc replay**, dù attacker không giải mã được. Tính sẵn sàng và tính toàn vẹn cũng quan trọng như tính bí mật.

## 113. Quản lý khóa và sự cố theo thời gian

Timeline:

~~~text
08:00 KMS key policy changed
08:03 Java decrypt error rate starts rising
08:04 Customer profile endpoint p99 increases
08:06 Key access denied for DR role
08:10 Backup restore job fails
08:20 Incident escalated to security/platform
```

Một timeline dashboard nên nối:

- Key policy/grant/alias changes.
- Service deploy.
- KMS API success/denied/timeout.
- Encryption/decryption failures.
- Database read/write success.
- Restore jobs.
- Old-key usage.
- Incident approvals.

Nếu chỉ có log “database read failed”, rất khó phát hiện **nguồn lỗi là KMS**.

## 114. Khôi phục cần ưu tiên chống hành động phá hoại thứ cấp

Khi hệ lỗi decrypt vì key unavailable, các thao tác tự động dễ gây hại:

- Delete record vì cho rằng corrupted.
- Ghi đè ciphertext bằng giá trị null.
- Re-encrypt dưới một key mới mà không có plaintext hợp lệ.
- Disable key thêm lần nữa.
- Xóa backup “không đọc được”.
- Gửi notification sai tới người dùng.
- Retry ồ ạt làm KMS throttling nặng hơn.

Một safe mode có thể:

1. Dừng những writes có khả năng phá hủy dữ liệu không đọc được.
2. Giữ ciphertext/metadata nguyên vẹn.
3. Xếp yêu cầu xử lý sau theo durable policy.
4. Giới hạn retries và bảo vệ IAM credentials.
5. Escalate khi key state/policy chưa rõ.

## 115. Bài tập A — Mã hóa ổ đĩa có che dữ liệu với database user?

**Tình huống:** MongoDB volume được mã hóa. Một user database có quyền đọc collection chứa số điện thoại ở plaintext.

**Hỏi:** user đó có nhìn thấy số điện thoại không?

**Hướng giải:** có thể có. At-rest storage encryption bảo vệ disk files, không tự chặn query đã được DB authorize. Nếu cần giảm quyền đọc plaintext của database layer, cân nhắc client-side field encryption và authorization thích hợp.

## 116. Bài tập B — AES-GCM nonce reuse

**Tình huống:** Java dùng cùng một AES key và nonce cố định cho mọi số điện thoại.

**Hỏi:** thiết kế có an toàn không?

**Hướng giải:** không. GCM nonce reuse cùng key là lỗi nghiêm trọng. Cần nonce unique cho mỗi encryption theo protocol; random 96-bit nonce có giới hạn sử dụng/rủi ro cần quản trị ở quy mô lớn.

## 117. Bài tập C — Ciphertext đổi tenant

**Tình huống:** encrypted phone của tenant A bị copy sang tenant B.

**Hỏi:** AAD giúp thế nào?

**Hướng giải:** nếu AAD xác thực `tenantId,entityId,fieldName` và ứng dụng dùng trusted context, decrypt ở tenant B sẽ không khớp AAD/tag. Nhưng vẫn cần authorization và canonical AAD đúng.

## 118. Bài tập D — Wrapped DEK có phải plaintext key?

**Tình huống:** bản ghi chứa `wrappedDek` và ciphertext.

**Hỏi:** người lấy database có thể trực tiếp dùng wrapped DEK để giải mã?

**Hướng giải:** không nếu wrapping được thực hiện đúng bằng KEK được bảo vệ và kẻ đó không có khả năng unwrap. Tuy nhiên metadata, application/KMS permissions hoặc key compromise có thể làm rủi ro thay đổi.

## 119. Bài tập E — Mất KMS key nhưng còn snapshot

**Tình huống:** Snapshot encrypted vẫn nguyên, nhưng KEK đã bị xóa vĩnh viễn và không có escrow hoặc bản copy dưới key khác.

**Hỏi:** có thể restore plaintext chỉ từ snapshot?

**Hướng giải:** không thực tế với mã hóa được thực thi đúng. Phải tìm nguồn/backup khác còn usable; không tự hứa khôi phục được master key đã mất.

## 120. Bài tập F — Khóa bị disable

**Tình huống:** Key còn tồn tại nhưng disabled.

**Hỏi:** điều tra thế nào?

**Hướng giải:** xác minh key ID/state, lý do disable, IAM/policy, security incident context; enable lại chỉ khi có approval và an toàn; test decrypt canary sau đó.

## 121. Bài tập G — Alias đã đổi

**Tình huống:** `alias/pii` giờ trỏ KEK-v2; backup cũ dùng KEK-v1.

**Hỏi:** có nên giải mã bằng alias mới mà không xem metadata?

**Hướng giải:** không. Dùng key identity/metadata đúng với ciphertext lịch sử, hoặc KMS key version handling theo contract. Alias di động thường phục vụ new writes.

## 122. Bài tập H — Rewrap và re-encrypt

**Tình huống:** cần đổi KEK vì chính sách; DEK còn an toàn.

**Hỏi:** có thể không đổi ciphertext business payload?

**Hướng giải:** có thể rewrap DEK dưới KEK mới khi protocol hỗ trợ. Nếu DEK cũng bị lộ hoặc cần rotate per policy, phải xem xét re-encrypt payload với DEK mới.

## 123. Bài tập I — Key bị lộ

**Tình huống:** attacker đã lấy old KEK và old ciphertext.

**Hỏi:** chỉ rewrap hiện tại có xóa được bí mật attacker đã lấy?

**Hướng giải:** không. Dữ liệu đã bị lộ có thể vẫn decrypt được ngoài hệ thống; cần incident response, assessment, rotate/re-encrypt theo scope, chặn quyền và thông báo khi cần.

## 124. Bài tập J — Re-encryption race

**Tình huống:** migration đọc record v10; user cập nhật v11; migration ghi lại v10 dưới key mới.

**Hỏi:** vấn đề gì?

**Hướng giải:** lost update. Dùng conditional write theo businessVersion/encryptionRevision; CAS fail phải re-read và làm lại.

## 125. Bài tập K — MongoDB CSFLE backup

**Tình huống:** backup chỉ lưu business collections, bỏ key vault metadata.

**Hỏi:** restore có đủ để decrypt fields không?

**Hướng giải:** có thể không. Cần backup đúng key vault metadata và external KMS access; verify trong restore drill.

## 126. Bài tập L — DynamoDB KMS

**Tình huống:** Table dùng customer managed key; team đổi IAM policy làm dịch vụ/role không truy cập key.

**Hỏi:** ứng dụng nên xử lý?

**Hướng giải:** phân loại KMS/key permission incident; kiểm table state/service integration, sửa policy có approval; không tự tạo key mới và mong dữ liệu cũ decrypt được.

## 127. Bài tập M — Cassandra disk encryption

**Tình huống:** cluster sử dụng volume encryption và snapshots được copy lên object storage.

**Hỏi:** có thể bỏ kiểm bucket encryption và access policy không?

**Hướng giải:** không. Backup/snapshot storage và transfer có trust boundary riêng; phải xác minh thực tế snapshot format/ciphertext và encryption policy.

## 128. Bài tập N — Redis PII cache

**Tình huống:** dữ liệu profile mã hóa client-side trong source nhưng sau khi decrypt, ứng dụng cache plaintext trong Redis.

**Hỏi:** encryption at rest ở source còn bảo vệ Redis data không?

**Hướng giải:** không trực tiếp. Redis/cache và persistence phải được phân loại, bảo vệ hoặc tránh lưu PII không cần thiết.

## 129. Bài tập O — SHA-256 email

**Tình huống:** ứng dụng lưu `SHA256(email)` làm chỉ mục tìm kiếm và gọi đó là encryption.

**Hỏi:** vấn đề gì?

**Hướng giải:** hash một chiều không phải encryption; email có thể đoán qua dictionary nếu entropy thấp. Cân nhắc keyed HMAC/blind index có threat-model phù hợp và bảo vệ key, hoặc chức năng queryable encryption được hỗ trợ.

## 130. Bài tập P — Khóa cũ không có API calls

**Tình huống:** Key v1 không có online calls ba tháng, nhưng backup retention bảy năm.

**Hỏi:** đủ điều kiện delete?

**Hướng giải:** không. Cần mapping key→backup, rewrap/re-encrypt verification và restore drill trước retirement.

## 131. Bài tập Q — Backup checksum pass nhưng decrypt fail

**Tình huống:** Backup checksum SHA-256 khớp, nhưng KMS trả AccessDenied.

**Hỏi:** backup có khôi phục được không?

**Hướng giải:** bytes có thể nguyên vẹn nhưng hiện tại chưa usable; phải khôi phục authorization/key path và thử decrypt+restore.

## 132. Bài tập R — Key recovery RTO

**Tình huống:** DB restore 25 phút, deploy 10 phút, key grant approval 2 giờ; SLO RTO 1 giờ.

**Hỏi:** đáp ứng không?

**Hướng giải:** không. KMS/IAM recovery là critical path có thể vượt RTO dù database restore nhanh.

## 133. Bài tập S — Same alias cross-region

**Tình huống:** Region B có alias cùng tên với region A, ciphertext được copy từ A sang B.

**Hỏi:** có chắc decrypt được không?

**Hướng giải:** không. Key material/identity/policy và provider multi-region semantics cần được xác minh bằng decrypt test thực tế.

## 134. Bài tập T — Java memory

**Tình huống:** Java đã `Arrays.fill(dekBytes, (byte)0)` sau khi decrypt.

**Hỏi:** có thể tuyên bố không còn plaintext DEK trong process memory không?

**Hướng giải:** không. Cipher/provider, `SdkBytes`, `SecretKeySpec` hoặc copies có thể giữ material; còn có plaintext payload/strings. Đây chỉ là một biện pháp giảm rủi ro.

## 135. Bài tập U — KMS outage fallback

**Tình huống:** Để giữ availability, developer đề nghị lưu plaintext tạm khi KMS down.

**Hỏi:** có nên?

**Hướng giải:** không theo một policy yêu cầu mã hóa; đây là fail-open làm lộ dữ liệu. Dùng fail-closed/durable encrypted queue hoặc tested recovery path.

## 136. Bài tập V — Ciphertext hiện còn decrypt được nhưng schema cũ

**Tình huống:** Key v1 còn nguyên, nhưng Java deployment chỉ hỗ trợ envelope format v3.

**Hỏi:** tại sao restore cũ vẫn thất bại?

**Hướng giải:** thiếu decoder/upcaster/format compatibility. Recovery cần cả key và supported historical encryption formats.

## 137. Bài tập W — Phân quyền tenant và KMS

**Tình huống:** KMS role cho phép decrypt key của tenant A; API nhận tenantId từ query param.

**Hỏi:** liệu quyền key đã chặn mọi truy cập trái phép chưa?

**Hướng giải:** chưa. Cần tenant identity từ authenticated context, authorization, scoped lookup và AAD; không tin client-supplied tenantId.

## 138. Bài tập X — Key rotation và CDC

**Tình huống:** Re-encrypt hàng triệu profiles tạo CDC events dù các trường nghiệp vụ không đổi.

**Hỏi:** có thể gây gì?

**Hướng giải:** Search/indexer/cache invalidation quá tải, replication lag, chi phí cao. Cần phân biệt crypto revision với business event, bounded migration và quan sát toàn pipeline.

## 139. Bài tập Y — Key disable do compromise

**Tình huống:** Security disable key vì nghi lộ; on-call muốn enable ngay để phục hồi API.

**Hỏi:** ai quyết định?

**Hướng giải:** security incident owner và các approvers theo runbook phải đánh giá compromise/containment và recovery; không vượt chính sách chỉ để xóa alert.

## 140. Bài tập Z — Restore canary thành công

**Tình huống:** Một record canary decrypt thành công nhưng hàng nghìn records dùng key version khác.

**Hỏi:** backup đã recoverable toàn bộ chưa?

**Hướng giải:** chưa. Cần coverage theo versions/key classes, database consistency và application validation.

## 141. Bài tập AA — Mất event và key rotation

**Tình huống:** Rotation worker hoàn tất 99,9% records, checkpoint nhảy qua một batch lỗi và nhóm xóa old KEK.

**Hỏi:** hậu quả?

**Hướng giải:** records/archives còn phụ thuộc old KEK có thể mất decryptability. Cần checkpoint đúng, reconciliation, coverage inventory và retirement gate.

## 142. Bài tập AB — Cryptographic erasure

**Tình huống:** Xóa DEK cho một customer, nhưng plaintext đã được export sang Search và Redis.

**Hỏi:** dữ liệu đã bị xóa hoàn toàn chưa?

**Hướng giải:** chưa. Phải xử lý các plaintext copies, caches, backups và legal obligations theo policy; key deletion không xóa những bản plaintext tồn tại trước đó.

## 143. Bài tập AC — Backup encryption key cùng trust boundary

**Tình huống:** Source và DR backup đều dùng cùng một KMS key có thể bị xóa bằng cùng compromised administrator role.

**Hỏi:** đã độc lập khôi phục chưa?

**Hướng giải:** chưa. Cần tách trust boundary, permissions, deletion safeguards và khả năng decrypt under DR role đã kiểm thử.

## 144. Bài tập AD — Mã hóa nhưng vẫn index mọi field

**Tình huống:** Muốn encrypt ngẫu nhiên tất cả fields bằng AES-GCM nhưng vẫn dùng range/sort/search y như plaintext.

**Hỏi:** có khả thi mặc định không?

**Hướng giải:** không. Cần thiết kế access patterns, queryable encryption theo capability, blind indexes và chấp nhận leakage/chi phí/giới hạn.

## 145. Checklist thiết kế mã hóa dữ liệu lưu trữ

**Threat model và phạm vi**

1. Đã xác định đối thủ/khả năng cần chống chưa?
2. Có inventory data classes, PII và legal retention không?
3. At-rest, in-transit và in-use được phân biệt chưa?
4. Database files, WAL/oplog, indexes và temporary files có được bảo vệ không?
5. Snapshots, exports, caches, Search/CDC/logs có trong scope không?
6. Có tránh nhầm encryption với password hashing/tokenization không?
7. Field encryption có thật sự cần để giảm DB-level plaintext access không?
8. Query/search/index limitations đã được chấp nhận chưa?

**Cryptography**

9. Thuật toán AEAD và thư viện có được phê duyệt không?
10. AES-GCM nonce uniqueness được thiết kế đúng chưa?
11. Có tránh ECB/CBC thiếu authentication/custom cipher không?
12. AAD có canonical encoding và schema/version không?
13. AAD có gắn tenant/entity/field theo policy không?
14. AEAD tag verification có fail closed không?
15. Có envelope format/algorithm/key version metadata không?
16. Có phân biệt businessVersion với encryptionRevision không?
17. Có tránh plaintext master keys trong config/CI/logs không?
18. Data keys có được tạo từ nguồn entropy đáng tin không?

**KMS, HSM và phân quyền**

19. Có DEK/KEK separation rõ không?
20. Key scope có phù hợp tenant/data class/environment không?
21. Quyền encrypt/decrypt có least privilege không?
22. IAM/grants và KMS encryption context có được kiểm soát không?
23. Có key usage audit, deny/disable/delete alerts không?
24. Key aliases và immutable key references được phân biệt chưa?
25. Có kiểm KMS region/account/endpoint availability không?
26. Có policy key-cache và memory exposure không?
27. Có break-glass approval/audit/expiry không?
28. Có separation of duties cho key deletion không?

**Rotation và migration**

29. Đã phân biệt KEK rewrap với DEK re-encryption chưa?
30. New writes có chuyển sang key mới trước khi retire old key không?
31. Old decrypt compatibility có được giữ trong giai đoạn cần thiết không?
32. Migration có CAS tránh overwrite concurrent business update không?
33. Có checkpoint, resume, retry budget và reconciliation không?
34. Có đo index/CDC/replication impact từ re-encryption không?
35. Same-version payload/metadata integrity có được xác minh không?
36. Có xác định records/backups còn dùng old key không?
37. Retirement gate đã vượt qua restore drills và retention checks chưa?

**Backup và khôi phục**

38. Có backup manifest chứa key references, crypto format và provenance không?
39. Backup checksums/authentication/DB consistency được kiểm riêng không?
40. Có mapping key → active records và historical backups không?
41. DR region/account có key material/permissions/network đã được thử không?
42. Có kế hoạch cho key disabled/pending deletion/missing/compromised không?
43. Có tính key approval time vào RTO không?
44. Có canary decrypt theo key classes và versions không?
45. Có isolated full restore drill với least-privileged DR identity không?
46. Có giới hạn việc copy plaintext sang test environment không?
47. Có bản offline/independent của recovery runbook không?
48. Backups có immutable protection và separate failure domain không?
49. Có xử lý legal hold/crypto erasure đúng policy không?
50. Không xóa key chỉ vì `lastUsed` cũ phải không?

**Java và vận hành**

51. Java driver/library có hỗ trợ envelope format cũ trong restore không?
52. Có timeout, KMS throttling/backoff và circuit-breaker strategy không?
53. Khi encrypt/decrypt lỗi, API không silently ghi plaintext/null đúng không?
54. Có classified error types: access denied, missing key, AEAD bad tag, format unsupported không?
55. Có tránh log plaintext DEK, PII và raw KMS responses không?
56. Có telemetry KMS usage, decrypt failures, old-key usage không?
57. Performance benchmark có KMS RTT/CPU/size overhead không?
58. Key rotation có security incident plan khi compromise không?
59. Có kiểm key permission theo tenant/field và independent authorization không?
60. Restore readiness được đánh giá qua **khả năng đọc dữ liệu thật** chứ không chỉ file backup tồn tại không?

## 146. Mẫu hợp đồng mã hóa và key recovery

~~~yaml
service: TenantProfileJavaApi
dataClassification:
  - customerPII
sourceOfTruth:
  engine: MongoDB
  collections:
    - profiles
    - encryptionKeyVault
encryption:
  atRest:
    storage: enabledAccordingToDeployment
    backups: encryptedAndVersioned
  sensitiveFields:
    - phone
    - address
  clientEnvelope:
    algorithm: AES-256-GCM
    nonceBytes: 12
    tagBits: 128
    aadFormatVersion: 1
    aadFields:
      - trustedTenantId
      - entityType
      - entityId
      - fieldName
    formatVersion: 2
  keyHierarchy:
    dekScope: perDocumentOrDefinedDataSegment
    wrappingService: KMS
    kekScope: environmentAndDataClass
    immutableKeyReference: required
    wrappedDekPersisted: true
  plaintextKeyLogging: prohibited
keyManagement:
  leastPrivilege: required
  decryptAccess: approvedReadersOnly
  securityApprovalForDeletion: required
  keyStateAlerts:
    - disabled
    - deletionScheduled
    - policyModified
  rotation:
    newWritesFirst: true
    rewrapOrReencryptAsAppropriate: true
    migrationCasGuard: true
    verifyOldDependenciesBeforeRetire: true
backups:
  copyLocations: tracked
  manifest:
    - dataSnapshotPoint
    - wrappingKeyIdentity
    - wrappingKeyRegionAccount
    - cryptoFormatVersion
    - checksums
  retention: policyDriven
  immutableProtection: accordingToRisk
recovery:
  drIdentity: preauthorizedWithApprovals
  isolatedEnvironment: required
  canaryPerKeyVersion: required
  fullRestoreDrill: scheduled
  keyStateScenarios:
    - accessDenied
    - disabled
    - pendingDeletion
    - regionUnavailable
    - compromised
    - irrecoverablyLost
  failClosedForSensitiveData: true
  rpoAndRtoIncludeKeyAvailability: true
observability:
  - decryptSuccessRate
  - kmsAccessDenied
  - kmsTimeoutRate
  - aeadAuthenticationFailures
  - oldKeyUsage
  - keyDependencyCoverage
  - restoreDrillDuration
  - recoverableBackupFraction
tests:
  - ciphertextTamperingRejected
  - wrongTenantAadRejected
  - oldFormatDecryptAfterUpgrade
  - keyPermissionRevoked
  - crossRegionRestore
  - kmsOutageFailsClosed
  - concurrentReencryptionCas
  - archiveBackupDecryptsWithOldKey
  - keyDeletionBlockedByDependencies
~~~

Đây là **YAML mô tả kiến trúc**, không phải cấu hình trực tiếp của MongoDB, AWS KMS, Spring Boot hoặc một thư viện Java. Các tên trường, rights, key references, quotas và rotation behavior phải được ánh xạ đúng vào provider/driver version triển khai.

## 147. Runbook mẫu: khóa giải mã không dùng được

~~~text
TRIGGER
  Authorized service fails to decrypt encrypted records.

TRIAGE
  1. Identify affected data class/tenant/key reference.
  2. Verify the ciphertext and envelope metadata were not changed.
  3. Classify failure:
       - IAM/access denied
       - key disabled
       - key pending deletion
       - key missing/deleted
       - KMS outage/throttling
       - AEAD authentication failed
       - unsupported format
  4. Preserve evidence, stop destructive fallbacks.
  5. Notify key owner/security/DR operator.

CONTAIN
  6. Stop automatic plaintext fallback or overwrite-on-failure.
  7. Rate-limit retries; keep idempotency and durable requests.
  8. If compromise suspected, use security incident runbook.

RECOVER
  9. Use approved IAM/key state procedure where reversible.
 10. Verify immutable key identity and correct KMS region.
 11. Restore required grants/policies with approval.
 12. If region unavailable, follow already-tested DR key path.
 13. If key irreversibly gone, enumerate alternate recoverable sources.
 14. Do not fabricate a replacement key for old ciphertext.

VALIDATE
 15. Decrypt authorized canary per affected key version.
 16. Verify full affected dataset/backup coverage.
 17. Run application/business consistency assertions.
 18. Confirm source, cache, Search and backup are aligned.
 19. Measure actual recovery time and data loss against RTO/RPO.

CLOSE
 20. Record root cause, permissions, key states and evidence.
 21. Update dependency inventory and key retirement gates.
 22. Schedule follow-up restore drill and prevention controls.
~~~

Thao tác enable/delete/permission changes phải theo quy trình được phê duyệt. Một lỗi chỉ liên quan authorization không phải lý do tự re-encrypt toàn bộ database.

## 148. Kết luận

**Mã hóa dữ liệu lưu trữ** là một lớp phòng thủ quan trọng của Database No SQL, nhưng giá trị của nó phụ thuộc vào **kiến trúc khóa và khả năng vận hành an toàn**.

Các điểm cần ghi nhớ:

- Volume/TDE bảo vệ dữ liệu tại storage boundary; không tự bảo vệ trước những truy vấn đã được cấp quyền.
- Client-side field encryption thu hẹp khả năng đọc plaintext của database layer nhưng làm query/index, schema và key access phức tạp hơn.
- AES-GCM cần unique nonce, authentication tag và AAD phù hợp; **không tự thiết kế crypto scheme**.
- Envelope encryption tách **DEK** khỏi **KEK**, giúp quản lý key scope, rotation và wrapped-key storage.
- **KMS/HSM, IAM, key state và region** trở thành dependency của dữ liệu, không chỉ chi tiết hạ tầng.
- Rotation/re-wrap/re-encrypt khác nhau; old ciphertext và backups vẫn có thể cần key material cũ.
- Backup nguyên vẹn **không có nghĩa restore được** khi thiếu key, grants, metadata hoặc compatible decoder.
- Key mất, key disable, key pending deletion và key compromise đòi **những runbook khác nhau**.
- Recovery readiness phải được chứng minh qua **isolated restore drill, decrypt canaries, coverage và RPO/RTO thực tế**.
- Không xóa key còn dependency và không fallback sang plaintext khi KMS lỗi.

> **Một bản backup chỉ thực sự an toàn khi còn nguyên vẹn, còn được phép giải mã và đã được thử khôi phục bằng chính quy trình dự kiến cho sự cố.**

Thiết kế bảo mật NoSQL tốt không chỉ trả lời “dữ liệu đã được mã hóa chưa?”, mà còn trả lời chính xác **ai có quyền giải mã, khóa nào bảo vệ bản nào, điều gì xảy ra khi khóa bị lộ hoặc unavailable, và làm sao khôi phục dữ liệu trong thời gian cam kết mà không phải phá bỏ những kiểm soát bảo mật cần thiết**.
