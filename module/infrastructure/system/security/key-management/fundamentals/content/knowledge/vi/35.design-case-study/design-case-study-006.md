# Thiết kế KMS integration

## 1. Bối cảnh case study

Một nền tảng quản lý tài liệu doanh nghiệp phục vụ nhiều khách hàng (multi-tenant document service) cần mã hóa tài liệu trước khi lưu vào object storage. Mỗi tenant có dữ liệu riêng, ứng dụng chạy trên nhiều instance Java và cần đọc/ghi tài liệu liên tục. Đội vận hành muốn tập trung quản lý khóa, theo dõi việc sử dụng khóa và có thể rotation mà không phải triển khai lại toàn bộ ứng dụng.

Thiết kế cần tích hợp Key Management Service (KMS) để bảo vệ khóa mã hóa. KMS giữ khóa cấp cao dùng để bảo vệ các khóa dữ liệu; ứng dụng chỉ sử dụng khóa dữ liệu trong thời gian ngắn để mã hóa hoặc giải mã nội dung. Bài toán này minh họa cách kết hợp KMS, envelope encryption, Java Cryptography Architecture (JCA), IAM, metadata, audit và quy trình vận hành thành một kiến trúc thống nhất.

### Yêu cầu nghiệp vụ

- Mỗi tài liệu được mã hóa trước khi lưu trữ.
- Dữ liệu của tenant này không được giải mã trong ngữ cảnh của tenant khác.
- Dịch vụ có thể mở lại tài liệu cũ sau khi triển khai phiên bản ứng dụng mới hoặc rotation KEK.
- Người vận hành có thể xác định khóa, phiên bản, chủ sở hữu và lịch sử thao tác của một tài liệu.
- Việc cấp quyền sử dụng khóa phải theo workload identity và least privilege.
- Hệ thống không lưu plaintext key material trong database, object storage, source code hoặc log.
- Khi KMS tạm thời không khả dụng, hệ thống phải xử lý có kiểm soát và không tự chuyển sang khóa dự phòng không được phê duyệt.
- Có thể kiểm thử khả năng phục hồi, rotation, tenant isolation và audit.

### Giả định thiết kế

Case study dùng một KMS có API tương đương các thao tác tạo data key, decrypt/unwrap data key, quản lý key policy và ghi audit event. Phần Java minh họa cụ thể bằng AWS SDK for Java 2.x và JCA AES-GCM; các khái niệm kiến trúc áp dụng được cho những KMS khác, nhưng tên API, semantics rotation, encryption context, quyền IAM và cơ chế failover phải được đối chiếu với nhà cung cấp thực tế.

## 2. Phân tích tài sản và mối đe dọa

### Tài sản cần bảo vệ

| Tài sản | Giá trị | Yêu cầu bảo vệ |
|---|---|---|
| Tài liệu plaintext | Nội dung nghiệp vụ của khách hàng. | Chỉ trả cho principal đã được xác thực và có quyền trên tenant/tài liệu. |
| Data Encryption Key (DEK) | Khóa mã hóa trực tiếp từng tài liệu. | Sinh ngẫu nhiên, chỉ tồn tại rõ trong bộ nhớ trong thời gian cần thiết. |
| Key Encryption Key (KEK) | Khóa KMS dùng wrap/unwrap DEK. | Không export, policy giới hạn principal và operation. |
| Wrapped DEK | DEK đã được KMS bảo vệ. | Lưu cùng ciphertext, không thể dùng nếu thiếu KMS key và context đúng. |
| Encryption metadata | Key ID, version, nonce, algorithm, tenant/object context. | Toàn vẹn, có version schema, không chứa bí mật. |
| KMS identity và policy | Quyết định ai có thể dùng hoặc quản trị khóa. | Least privilege, tách quyền sử dụng và quản trị. |
| Audit records | Bằng chứng về thao tác mật mã và quản trị. | Không ghi key material; bảo vệ khỏi sửa đổi và truy cập trái phép. |

### Mối đe dọa chính

1. Kẻ tấn công lấy được bản sao database hoặc object storage và cố giải mã tài liệu ngoại tuyến.
2. Một tenant độc hại thay tenant ID hoặc object metadata để yêu cầu giải mã dữ liệu của tenant khác.
3. Ứng dụng bị chiếm quyền và sử dụng quyền KMS rộng để giải mã hàng loạt.
4. DEK bị lộ qua heap dump, log, exception, crash report hoặc cache.
5. KEK bị disable, xóa nhầm hoặc mất quyền truy cập khiến dữ liệu cũ không thể mở.
6. Rotation không đồng bộ giữa KMS, metadata và ứng dụng khiến một số tài liệu không đọc được.
7. KMS outage hoặc throttling làm gián đoạn thao tác mã hóa/giải mã.
8. Người vận hành có quyền quản trị quá rộng có thể thay policy, cấp grant hoặc phá hủy khóa.

Thiết kế phải giảm rủi ro ở nhiều lớp. KMS bảo vệ KEK và kiểm soát thao tác mở gói DEK; ứng dụng xác thực người dùng và phân quyền trên tài liệu; AEAD bảo vệ tính toàn vẹn ciphertext; audit và monitoring phát hiện hành vi bất thường.

## 3. Kiến trúc đề xuất

~~~text
                  User / API Client
                         |
                         v
                Authentication + AuthZ
                         |
                         v
                Document Service (Java)
                  |              |
          Encrypt/Decrypt      Metadata
                  |              |
                  v              v
             KMS Client      Database / Object Store
                  |
                  v
             Cloud KMS
          (KEK non-exportable)
                  |
          GenerateDataKey / Decrypt
                  |
                  v
          Wrapped DEK + Plain DEK
                  |
                  v
          JCA AES-256-GCM
                  |
                  v
          Ciphertext + nonce + tag

       KMS Audit / Application Audit / SIEM
                         |
                         v
                  Monitoring & Alert
~~~

Các thành phần:

- **Document Service:** kiểm tra danh tính, quyền truy cập tài liệu, gọi KMS và thực hiện AES-GCM.
- **KMS:** giữ KEK không exportable, tạo DEK, wrap/unwrap DEK và ghi nhận thao tác.
- **Metadata Registry:** lưu key ID, wrapped DEK, algorithm, nonce, schema version, tenant/object reference và trạng thái.
- **Object Storage:** chỉ lưu ciphertext cùng metadata cần thiết để giải mã.
- **IAM/Key Policy:** giới hạn workload nào được GenerateDataKey hoặc Decrypt trên key cụ thể.
- **Audit/SIEM:** nhận sự kiện từ KMS và ứng dụng, phát hiện decrypt bất thường, policy change hoặc lỗi rotation.

KMS không cần nhận toàn bộ tài liệu. Ứng dụng mã hóa dữ liệu bằng DEK; KMS chỉ bảo vệ DEK. Nhờ đó, lượng dữ liệu truyền qua KMS nhỏ và ứng dụng có thể xử lý file lớn mà không gọi KMS cho từng block, tùy cách chia DEK và định dạng dữ liệu.

## 4. Chọn mô hình khóa và tenant isolation

### Envelope encryption

Thiết kế sử dụng hai tầng khóa:

- KEK được tạo và giữ trong KMS.
- DEK được sinh ngẫu nhiên cho từng tài liệu hoặc phạm vi dữ liệu đã xác định.
- DEK mã hóa plaintext bằng AES-256-GCM.
- KMS trả về DEK dạng rõ trong thời gian ngắn và bản DEK đã wrap.
- Ứng dụng lưu wrapped DEK cùng ciphertext, nhưng xóa bản DEK rõ sau khi hoàn tất.

~~~text
                    KMS KEK
                       |
                 Wrap / Unwrap
                       |
                +------+------+
                |             |
          Plaintext DEK   Wrapped DEK
                |             |
                v             v
          AES-256-GCM     Persist with
                |          ciphertext
                v
           Ciphertext
~~~

Lợi ích của envelope encryption:

- KEK không rời khỏi KMS.
- DEK có thể được tạo riêng cho từng tài liệu, giảm phạm vi ảnh hưởng khi một DEK bị lộ.
- KMS chỉ xử lý key material nhỏ thay vì toàn bộ nội dung tài liệu.
- Có thể thay KEK bằng cách rewrap DEK nếu DEK và ciphertext vẫn an toàn.
- Có thể áp dụng quyền KMS theo tenant, purpose và workload.

### Một KEK chung hay KEK riêng cho từng tenant?

| Phương án | Ưu điểm | Đánh đổi |
|---|---|---|
| KEK chung cho nhiều tenant, ràng buộc encryption context | Ít key resource, dễ vận hành, chi phí quản lý thấp hơn. | Phải kiểm soát chặt context và authorization; sai policy có thể ảnh hưởng nhiều tenant. |
| KEK riêng cho từng tenant | Cô lập tốt hơn, dễ disable hoặc rotation theo tenant, blast radius hẹp hơn. | Nhiều key resource, policy, quota và quy trình lifecycle hơn. |
| KEK theo nhóm tenant hoặc phân loại dữ liệu | Cân bằng giữa cô lập và chi phí. | Cần quản lý mapping và tránh group key có phạm vi quá rộng. |

Trong case study này, chọn KEK riêng theo tenant cho các tenant có yêu cầu cô lập cao. Tenant nhỏ có thể dùng nhóm KEK theo phân loại nếu threat model và hợp đồng cho phép. Không dùng cùng KEK giữa production và non-production.

Encryption context là metadata không bí mật được KMS ràng buộc với thao tác mã hóa/giải mã. Ví dụ gồm tenant ID, purpose và môi trường. Với AWS KMS symmetric encryption, context được xác thực như additional authenticated data và phải khớp khi gọi Decrypt. Context không thay thế authorization của ứng dụng; nếu principal có quyền decrypt rộng và tự do chọn context, nó có thể thử ngữ cảnh khác. Cần ràng buộc context trong key policy/IAM khi nhà cung cấp hỗ trợ, đồng thời xác định tenant từ danh tính đã xác thực.

Không đưa PII, nội dung tài liệu, email hoặc bí mật vào encryption context vì context có thể xuất hiện trong audit log và telemetry của KMS.

## 5. Định dạng dữ liệu lưu trữ

Mỗi tài liệu được lưu dưới dạng một envelope có version schema:

~~~json
{
  "format_version": 1,
  "tenant_id": "tenant-042",
  "object_id": "doc-9812",
  "algorithm": "AES-256-GCM",
  "nonce": "<base64-encoded-12-byte-nonce>",
  "ciphertext": "<base64-encoded-ciphertext-and-tag>",
  "encrypted_data_key": "<base64-encoded-wrapped-DEK>",
  "kms_key_id": "<stable-key-id-or-arn>",
  "kms_key_version": "<provider-version-if-available>",
  "kms_context": {
    "tenant_id": "tenant-042",
    "purpose": "document-encryption",
    "environment": "production"
  },
  "aad_version": 1
}
~~~

Đây là cấu trúc minh họa. Trong hệ thống thực tế, metadata có thể nằm trong database và ciphertext ở object storage; dùng object ID hoặc content hash để liên kết chúng.

Các nguyên tắc:

- Lưu key ID ổn định, không chỉ lưu alias có thể được trỏ sang khóa khác.
- Lưu wrapped DEK và phiên bản định dạng để ứng dụng biết cách mở dữ liệu cũ.
- Nonce phải duy nhất với mỗi lần mã hóa dưới cùng một DEK khi dùng GCM.
- Lưu đủ thông tin để tái tạo KMS encryption context và AEAD AAD chính xác.
- Không lưu plaintext DEK hoặc KEK.
- Metadata cần được kiểm tra cấu trúc, kích thước và allowlist trước khi gọi KMS.
- Không tin tenant ID trong record nếu chưa đối chiếu với principal đã xác thực.

GCM tag trong ví dụ được nối vào kết quả ciphertext do JCA trả về. Nếu hệ thống lưu tag riêng, phải xác định rõ định dạng và độ dài trong schema.

## 6. Quyền và key policy

Tách quyền sử dụng khóa khỏi quyền quản trị:

| Principal | Quyền cần có | Không nên có |
|---|---|---|
| Document service runtime | GenerateDataKey và Decrypt trên KEK thuộc phạm vi workload. | CreateKey, ScheduleKeyDeletion, thay key policy, export KEK. |
| KMS/key administrator | Tạo key, thay policy, cấu hình rotation và quản lý trạng thái. | Tự động đọc tài liệu nghiệp vụ hoặc nhận plaintext DEK không cần thiết. |
| Security auditor | Xem metadata và audit event. | GenerateDataKey, Decrypt hoặc thay policy. |
| Recovery operator | Thực hiện restore theo approval/quorum. | Quyền thường trực không giới hạn trên mọi key. |
| CI/CD deployment identity | Triển khai cấu hình service và tham chiếu key ID đã phê duyệt. | Decrypt dữ liệu production hoặc export key material. |

Document service chỉ nên được cấp quyền trên đúng key ARN hoặc key resource cần dùng. Tránh wildcard trên mọi key trong account. Nếu dùng KEK riêng từng tenant, mapping tenant-to-key phải được quản lý ở server-side registry và có audit.

Với AWS KMS, các thao tác minh họa thường tương ứng với kms:GenerateDataKey và kms:Decrypt. Điều kiện theo encryption context có thể được dùng trong IAM/key policy, nhưng cú pháp và phạm vi phải được kiểm tra với loại key và API thực tế. Không sao chép policy mẫu mà chưa kiểm tra principal, account, region và điều kiện.

Ví dụ policy logic cho một KEK riêng của tenant-042 có thể giới hạn cả resource lẫn context:

~~~json
{
  "Effect": "Allow",
  "Action": [
    "kms:GenerateDataKey",
    "kms:Decrypt"
  ],
  "Resource": "arn:aws:kms:region:account-id:key/key-id",
  "Condition": {
    "StringEquals": {
      "kms:EncryptionContext:tenant_id": "tenant-042",
      "kms:EncryptionContext:purpose": "document-encryption",
      "kms:EncryptionContext:environment": "production"
    }
  }
}
~~~

Đây là statement minh họa, cần đặt trong policy hoàn chỉnh với principal, account boundary và quyền quản trị phù hợp. Nếu dùng một KEK chung cho nhiều tenant, không thể cố định tenant_id như ví dụ; phải thiết kế điều kiện động phù hợp với IAM/provider và vẫn kiểm tra authorization trong ứng dụng. Encryption context do caller cung cấp nên chỉ có giá trị ràng buộc khi principal không thể tùy ý dùng một context khác để vượt phạm vi.

## 7. Luồng mã hóa tài liệu

Khi người dùng tải tài liệu lên:

1. API xác thực user và xác định tenant từ identity/session đáng tin cậy.
2. Authorization layer xác minh user được tạo/cập nhật tài liệu đó.
3. Document service lấy KEK ID từ registry theo tenant và environment.
4. Service tạo encryption context gồm tenant ID, purpose và environment.
5. Service gọi KMS GenerateDataKey với yêu cầu AES-256.
6. KMS trả plaintext DEK và wrapped DEK.
7. Service tạo nonce mới, mã hóa plaintext bằng AES-256-GCM và gắn AAD chứa tenant/object/schema.
8. Service lưu ciphertext, nonce, wrapped DEK, key ID và metadata.
9. Service xác nhận ghi dữ liệu thành công rồi xóa buffer DEK trong phạm vi có thể.
10. Audit ghi key ID, tenant reference, operation, request ID và kết quả, không ghi key material.

Nếu lưu ciphertext thành công nhưng ghi metadata thất bại, đối tượng không được công bố là tài liệu hoàn chỉnh. Dùng transaction hoặc trạng thái staging/commit để tránh record nửa chừng. Retry phải có idempotency key để không tạo nhiều tài liệu hoặc DEK ngoài dự kiến.

Idempotency ở tầng ứng dụng không tự bảo đảm API GenerateDataKey của KMS có idempotency token. Nếu request timeout sau khi KMS đã xử lý nhưng response bị mất, lần gọi lại có thể tạo một DEK khác. Workflow cần lưu request/correlation ID, phân biệt kết quả chưa rõ với thất bại chắc chắn, và chỉ commit một envelope. DEK/wrapped DEK của lần gọi không được chọn có thể trở thành dữ liệu mồ côi; không ghi plaintext DEK vào log để truy tìm. Kiểm tra khả năng idempotency của đúng API/provider trước khi thiết kế retry.

## 8. Luồng giải mã tài liệu

Khi người dùng đọc tài liệu:

1. API xác thực user và xác định tenant.
2. Authorization layer kiểm tra quyền đọc object trước khi gọi KMS.
3. Service tải envelope và xác minh tenant/object mapping.
4. Service kiểm tra format version, algorithm, kích thước nonce, wrapped DEK và key ID theo allowlist.
5. Service dựng lại encryption context và AAD từ metadata đã xác thực.
6. Service gọi KMS Decrypt để unwrap DEK.
7. JCA dùng DEK để AES-GCM decrypt và xác minh authentication tag.
8. Chỉ trả plaintext sau khi xác minh tag thành công.
9. Xóa buffer DEK theo khả năng của runtime và ghi audit kết quả.

Không gửi plaintext cho caller trước khi GCM tag được xác minh. Với dữ liệu lớn hoặc streaming, cần dùng định dạng chunk có xác thực từng chunk hoặc một giao thức streaming AEAD được thiết kế rõ; không phát plaintext chưa xác thực ra ngoài. Cần xác định nonce, sequence number, AAD và quy tắc chống reorder/truncate cho từng chunk.

Nếu KMS trả lỗi authorization, context mismatch hoặc key unavailable, không thử một KEK ngẫu nhiên khác. Lỗi cần được phân loại nội bộ và ghi audit phù hợp; response bên ngoài không nên tiết lộ thông tin nhạy cảm về key ID hoặc tenant khác.

## 9. Ví dụ Java: tạo DEK và mã hóa bằng AES-GCM

Ví dụ dùng AWS SDK for Java 2.x và JCA. Dependency AWS SDK KMS cần được khai báo trong build của ứng dụng; KMS client nên được tái sử dụng và đóng khi service shutdown.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Map;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

import software.amazon.awssdk.services.kms.KmsClient;
import software.amazon.awssdk.services.kms.model.DataKeySpec;
import software.amazon.awssdk.services.kms.model.GenerateDataKeyRequest;
import software.amazon.awssdk.services.kms.model.GenerateDataKeyResponse;

public final class DocumentEncryption {
    private static final int NONCE_LENGTH = 12;
    private static final int TAG_LENGTH_BITS = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    private final KmsClient kms;
    private final String kekId;

    public DocumentEncryption(KmsClient kms, String kekId) {
        this.kms = kms;
        this.kekId = kekId;
    }

    public EncryptedDocument encrypt(
            String tenantId,
            String objectId,
            byte[] plaintext) throws Exception {

        Map<String, String> kmsContext = Map.of(
                "tenant_id", tenantId,
                "purpose", "document-encryption",
                "environment", "production");

        GenerateDataKeyRequest request =
                GenerateDataKeyRequest.builder()
                        .keyId(kekId)
                        .keySpec(DataKeySpec.AES_256)
                        .encryptionContext(kmsContext)
                        .build();

        GenerateDataKeyResponse response =
                kms.generateDataKey(request);

        byte[] dataKey = response.plaintext().asByteArray();
        byte[] wrappedDataKey =
                response.ciphertextBlob().asByteArray();

        try {
            byte[] nonce = new byte[NONCE_LENGTH];
            RANDOM.nextBytes(nonce);

            byte[] aad = buildAad(tenantId, objectId, 1);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            SecretKeySpec key = new SecretKeySpec(dataKey, "AES");
            cipher.init(
                    Cipher.ENCRYPT_MODE,
                    key,
                    new GCMParameterSpec(TAG_LENGTH_BITS, nonce));
            cipher.updateAAD(aad);

            byte[] ciphertextAndTag = cipher.doFinal(plaintext);
            return new EncryptedDocument(
                    nonce, ciphertextAndTag, wrappedDataKey,
                    kekId, kmsContext, 1);
        } finally {
            Arrays.fill(dataKey, (byte) 0);
        }
    }

    private static byte[] buildAad(
            String tenantId, String objectId, int formatVersion) {
        byte[] tenant = tenantId.getBytes(StandardCharsets.UTF_8);
        byte[] object = objectId.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(
                        Integer.BYTES + tenant.length
                                + Integer.BYTES + object.length
                                + Integer.BYTES)
                .putInt(tenant.length)
                .put(tenant)
                .putInt(object.length)
                .put(object)
                .putInt(formatVersion)
                .array();
    }

    public record EncryptedDocument(
            byte[] nonce,
            byte[] ciphertextAndTag,
            byte[] wrappedDataKey,
            String keyId,
            Map<String, String> kmsContext,
            int formatVersion) {
    }
}
~~~

Đây là ví dụ tập trung vào luồng mã hóa. Trong production cần kiểm tra input và kích thước tài liệu, lấy tenant/environment từ security context thay vì tin caller, dùng AAD serialization có version và encoding cố định, xử lý lỗi KMS, ghi metadata/ciphertext theo transaction hoặc staging, và không để các mảng byte bị chia sẻ ngoài phạm vi cần thiết.

Việc fill mảng dataKey chỉ xóa bản sao byte array mà ứng dụng lấy ra. Đối tượng response của SDK, provider, JIT hoặc garbage collector có thể đã giữ bản sao khác trong bộ nhớ; Java không bảo đảm zeroization tuyệt đối. SecretKeySpec cũng có thể giữ bản sao key bytes. Giảm thời gian sống và số bản sao, kiểm soát heap dump, không log object nhạy cảm và cân nhắc thiết kế dùng HSM/provider khi yêu cầu bảo vệ bộ nhớ cao hơn.

Đối tượng EncryptedDocument trong ví dụ là record đơn giản, không tự bảo vệ mảng byte khỏi bị sửa đổi bởi caller. Production nên dùng value object bất biến với defensive copy khi nhận và trả byte array.

## 10. Ví dụ Java: unwrap DEK và giải mã

Khi đọc tài liệu, service dựng lại context từ tenant đã xác thực và metadata đã kiểm tra:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Map;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

import software.amazon.awssdk.core.SdkBytes;
import software.amazon.awssdk.services.kms.KmsClient;
import software.amazon.awssdk.services.kms.model.DecryptRequest;

public final class DocumentDecryption {
    private static final int TAG_LENGTH_BITS = 128;

    private final KmsClient kms;

    public DocumentDecryption(KmsClient kms) {
        this.kms = kms;
    }

    public byte[] decrypt(
            String tenantId,
            String objectId,
            byte[] nonce,
            byte[] ciphertextAndTag,
            byte[] wrappedDataKey,
            String keyId) throws Exception {

        Map<String, String> kmsContext = Map.of(
                "tenant_id", tenantId,
                "purpose", "document-encryption",
                "environment", "production");

        DecryptRequest request = DecryptRequest.builder()
                .ciphertextBlob(SdkBytes.fromByteArray(wrappedDataKey))
                .keyId(keyId)
                .encryptionContext(kmsContext)
                .build();

        byte[] dataKey = kms.decrypt(request)
                .plaintext()
                .asByteArray();

        try {
            byte[] aad = buildAad(tenantId, objectId, 1);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(
                    Cipher.DECRYPT_MODE,
                    new SecretKeySpec(dataKey, "AES"),
                    new GCMParameterSpec(TAG_LENGTH_BITS, nonce));
            cipher.updateAAD(aad);

            // doFinal xác minh GCM tag trước khi trả plaintext.
            return cipher.doFinal(ciphertextAndTag);
        } finally {
            Arrays.fill(dataKey, (byte) 0);
        }
    }

    private static byte[] buildAad(
            String tenantId, String objectId, int formatVersion) {
        byte[] tenant = tenantId.getBytes(StandardCharsets.UTF_8);
        byte[] object = objectId.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(
                        Integer.BYTES + tenant.length
                                + Integer.BYTES + object.length
                                + Integer.BYTES)
                .putInt(tenant.length)
                .put(tenant)
                .putInt(object.length)
                .put(object)
                .putInt(formatVersion)
                .array();
    }
}
~~~

Ví dụ lược bỏ phần authorization và validation để tập trung vào thao tác mật mã. Trước khi gọi KMS, ứng dụng phải xác minh người dùng có quyền đọc object và tenant ID lấy từ identity đã xác thực khớp tenant của record. Không lấy tenant context chỉ từ request body. Cần kiểm tra nonce đúng 12 byte, ciphertext có đủ tag, format version được hỗ trợ và key ID thuộc registry hợp lệ.

Trong AES-GCM, nếu tag không hợp lệ, doFinal ném lỗi xác thực (thường là AEADBadTagException). Ứng dụng phải từ chối dữ liệu và không trả plaintext. Không bắt lỗi rồi tiếp tục dùng một phần plaintext chưa xác thực.

## 11. Rotation KEK và DEK

Rotation cần phân biệt thay KEK với thay DEK:

### Rotation KEK

Khi KEK cần rotation, DEK và ciphertext có thể giữ nguyên nếu DEK chưa bị compromise. Quy trình:

1. Tạo hoặc kích hoạt KEK version mới.
2. Kiểm tra policy và quyền sử dụng version mới.
3. Rewrap wrapped DEK bằng API KMS ReEncrypt hoặc quy trình unwrap/rewrap được phê duyệt.
4. Cập nhật key ID/version và wrapped DEK trong metadata.
5. Xác minh DEK mới unwrap được và tài liệu vẫn giải mã thành công.
6. Giữ KEK cũ để mở các bản backup hoặc record chưa migration.
7. Chỉ retire/destroy KEK cũ sau khi reconciliation xác nhận không còn dependency.

Một số KMS hỗ trợ rotation key material nội bộ và tự chọn material cũ khi decrypt ciphertext đã tạo trước đó. Một số hệ thống yêu cầu rewrap hoặc migration tường minh. Phải đọc semantics của provider; không giả định rotation tự động có nghĩa mọi wrapped DEK đã được mã hóa lại bằng material mới.

### Rotation DEK

Nếu chỉ rotation theo lịch và DEK cũ chưa bị lộ, có thể tạo DEK mới cho dữ liệu mới và giữ DEK cũ để đọc dữ liệu cũ. Nếu DEK bị compromise, rewrap DEK cũ là không đủ vì attacker đã có key material; cần tạo DEK mới và re-encrypt plaintext/ciphertext theo quy trình phục hồi.

### Versioning

Mỗi envelope phải giữ key ID/version và format version. Không ghi đè metadata theo cách khiến dữ liệu cũ mất mapping. Hỗ trợ đọc nhiều version trong thời gian chuyển tiếp nhưng chỉ cho phép ghi bằng version hiện hành.

## 12. Resilience, latency và caching

KMS là dependency bên ngoài ứng dụng, có latency, quota, throttling và khả năng gián đoạn. Thiết kế cần xử lý:

- Tái sử dụng KMS client thay vì tạo client mới cho mỗi request.
- Timeout rõ ràng, retry có giới hạn, exponential backoff và jitter cho lỗi tạm thời.
- Không retry vô hạn với lỗi authorization, context mismatch hoặc invalid key.
- Circuit breaker và bulkhead để KMS outage không làm cạn thread pool của toàn bộ ứng dụng.
- Rate limit theo tenant/workload và theo dõi quota.
- Có kiểm tra health và cảnh báo cho lỗi KMS.
- Khi KMS không khả dụng, không tự fallback sang khóa local không được quản lý.

Không cache plaintext DEK theo mặc định. Nếu hiệu năng buộc phải cache, phải có threat model và giới hạn cụ thể:

- TTL ngắn và giới hạn số lượng entry.
- Cache key theo tenant, object và key version; không dùng một DEK cho phạm vi rộng ngoài thiết kế.
- Không serialize hoặc ghi cache xuống disk.
- Xóa buffer khi hết hạn/eviction trong phạm vi runtime cho phép.
- Không dùng cache để bỏ qua authorization hoặc policy check.
- Theo dõi thời gian tồn tại và số lần dùng; có cơ chế clear cache khi revoke hoặc incident.

Cache KMS client, connection và public metadata thường ít nhạy cảm hơn cache plaintext DEK. Không nhầm việc cache wrapped DEK với cache plaintext DEK.

### KMS outage

Khi KMS không khả dụng:

- Encrypt mới: trả lỗi có kiểm soát hoặc đưa tác vụ vào hàng đợi an toàn; không ghi plaintext như phương án thay thế.
- Decrypt: retry trong giới hạn, trả trạng thái tạm thời và không đánh dấu tài liệu hỏng nếu chưa xác định.
- Không tạo KEK mới để thay KEK cũ khi chỉ gặp outage; khóa mới không unwrap được DEK cũ.
- Nếu có multi-region KMS, kiểm tra key replication, key identity, policy và encryption context trước khi failover.
- Ghi nhận thời gian gián đoạn, request ID và tỷ lệ lỗi.

## 13. Audit và monitoring

Audit nên ghi nhận cả thao tác KMS và thao tác nghiệp vụ:

| Sự kiện | Trường nên ghi |
|---|---|
| GenerateDataKey | Principal, key ID, tenant reference, purpose, request ID, result, latency. |
| Decrypt/Unwrap | Principal, key ID, context reference, object reference đã chuẩn hóa, result và latency. |
| Policy/Grant change | Actor, policy version, principal được thêm/xóa, approval và thời điểm. |
| Rotation/ReEncrypt | Old/new key ID/version, số record xử lý, trạng thái và error count. |
| Denied operation | Principal, operation, key ID, deny reason ở mức an toàn, source workload. |
| KMS outage/throttling | Region, API, error class, retry count và duration. |

Không ghi plaintext, DEK, KEK, private key, token hoặc nội dung tài liệu vào log. Encryption context không phải bí mật; chỉ đưa vào context những metadata không nhạy cảm vì provider có thể ghi context trong audit.

Các cảnh báo nên có:

- Một workload decrypt vượt baseline hoặc đọc nhiều tenant trong thời gian ngắn.
- GenerateDataKey tăng bất thường, có thể là loop hoặc lạm dụng API.
- Request có context mismatch hoặc principal không thuộc policy.
- Thay đổi key policy, grant hoặc disable/delete key ngoài change window.
- KMS throttling, latency hoặc error rate vượt ngưỡng.
- Key version cũ tiếp tục được dùng để encrypt sau thời điểm cutover.
- Record không có key ID/version hoặc không thể map tới KMS key.

## 14. Migration từ khóa tĩnh sang KMS

Nếu ứng dụng hiện đang dùng một khóa AES tĩnh trong file cấu hình, không nên thay ngay và bỏ khóa cũ. Migration theo từng giai đoạn:

1. Inventory nơi lưu khóa cũ, ứng dụng và dữ liệu đã mã hóa bằng khóa đó.
2. Tạo KEK trong KMS, thiết lập policy và audit.
3. Triển khai định dạng envelope mới cho dữ liệu ghi mới.
4. Thêm dual-read: đọc dữ liệu mới bằng KMS envelope và dữ liệu cũ bằng legacy decrypt path có kiểm soát.
5. Chạy migration worker để đọc dữ liệu cũ, giải mã bằng khóa cũ trong môi trường được phê duyệt, tạo DEK mới, mã hóa lại và lưu envelope.
6. Dùng checkpoint/idempotency để migration có thể retry mà không làm hỏng dữ liệu.
7. Xác minh số lượng record, hash/plaintext fixture và trạng thái migration.
8. Khi không còn record dùng khóa cũ, thu hồi quyền và hủy khóa theo retention/approval.
9. Xóa secret cũ khỏi config, CI/CD, backup không còn cần thiết và các bản triển khai cũ.

Không hủy khóa cũ chỉ dựa trên số record migration đã xử lý. Cần reconciliation trên toàn bộ database, object store, backup, archive và replica.

## 15. Kiểm thử thiết kế

| Nhóm | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Functional | Mã hóa và giải mã tài liệu mới. | Plaintext khôi phục đúng. |
| Integrity | Sửa ciphertext, nonce, tag hoặc AAD. | AES-GCM xác thực thất bại, không trả plaintext. |
| Tenant isolation | Tenant A yêu cầu đọc object của tenant B. | Authorization từ chối trước khi gọi KMS. |
| KMS context | Thay tenant/purpose trong encryption context. | KMS từ chối unwrap hoặc policy deny. |
| IAM | Workload không có quyền GenerateDataKey/Decrypt. | Request bị từ chối và có audit. |
| Key policy | Runtime thử CreateKey hoặc ScheduleKeyDeletion. | Bị từ chối. |
| Rotation KEK | Rewrap DEK sang KEK mới. | Tài liệu cũ giải mã được; metadata mới nhất nhất quán. |
| Rotation DEK | Mã hóa lại bằng DEK mới. | Ciphertext mới hợp lệ; version cũ được giữ theo retention. |
| Failure | KMS timeout/throttling. | Retry giới hạn, lỗi có kiểm soát, không fallback không an toàn. |
| Recovery | Restore key hoặc KMS replica theo DR plan. | DEK được unwrap và fixture giải mã thành công. |
| Audit | GenerateDataKey, Decrypt và policy change. | Event đủ trường, không có key material. |
| Performance | Tải đồng thời nhiều tenant. | Latency, quota và thread pool nằm trong mục tiêu. |
| Migration | Retry một batch migration đã xử lý một phần. | Idempotent, không mất hoặc nhân đôi dữ liệu. |

Ngoài kiểm thử tích cực, cần kiểm tra deny case và các lỗi metadata. Một thiết kế chỉ chứng minh được tài liệu hợp lệ giải mã thành công chưa chứng minh được tenant isolation hoặc quyền KMS đã giới hạn đúng.

## 16. Kế hoạch triển khai

**Giai đoạn 1 – Foundation**

- Tạo KMS key theo môi trường và tenant model.
- Thiết lập key policy, IAM role và audit.
- Tạo metadata schema và registry.
- Chốt envelope format, AAD và encryption context.

**Giai đoạn 2 – Application integration**

- Xây KMS adapter và lớp JCA AES-GCM.
- Thêm authorization trước thao tác KMS.
- Triển khai encrypt/decrypt cho một nhóm tài liệu thử nghiệm.
- Thêm metric, tracing và audit redaction.

**Giai đoạn 3 – Validation**

- Kiểm thử tenant isolation, tamper, context mismatch và policy deny.
- Thử rotation KEK/DEK, KMS outage và recovery.
- Kiểm tra latency, quota và concurrency.
- Thử rollback và reconciliation.

**Giai đoạn 4 – Production rollout**

- Canary theo tenant hoặc nhóm dịch vụ.
- Chuyển ghi mới sang envelope encryption.
- Theo dõi lỗi, latency, KMS usage và audit.
- Mở rộng theo đợt sau khi đạt tiêu chí.

**Giai đoạn 5 – Legacy retirement**

- Migration dữ liệu cũ.
- Xác minh không còn dependency vào khóa tĩnh.
- Thu hồi quyền, xóa secret cũ và lưu evidence.

## 17. Quyết định thiết kế và lý do

| Quyết định | Lý do | Điều kiện cần theo dõi |
|---|---|---|
| Envelope encryption | KMS bảo vệ KEK, ứng dụng xử lý dữ liệu bằng DEK. | Quản lý DEK trong bộ nhớ và wrapped key metadata. |
| AES-256-GCM | Cung cấp confidentiality và integrity cho dữ liệu. | Nonce uniqueness, tag verification và AAD versioning. |
| DEK theo tài liệu | Giới hạn blast radius và hỗ trợ migration theo object. | Chi phí GenerateDataKey và số lượng wrapped DEK. |
| KEK riêng tenant nhạy cảm | Cô lập quyền và rotation theo tenant. | Quota, inventory và quy trình lifecycle nhiều key. |
| Workload identity | Tránh secret quản trị dài hạn trong ứng dụng. | IAM trust policy và vòng đời identity. |
| Không cache plaintext DEK mặc định | Giảm thời gian tồn tại của key material. | KMS latency, throughput và nhu cầu tối ưu có kiểm soát. |
| Audit ở KMS và ứng dụng | Có cả bằng chứng thao tác khóa và ngữ cảnh nghiệp vụ. | Correlation ID, redaction và retention. |
| Versioned envelope | Đọc được dữ liệu cũ qua rotation và migration. | Giữ mapping version, key ID và schema tương thích. |

## 18. Checklist trước khi đưa KMS integration vào production

- [ ] KMS key được tạo ở account/project và region đúng.
- [ ] KEK không exportable và có owner/purpose rõ ràng.
- [ ] IAM/key policy giới hạn principal, key ID và operation.
- [ ] Quyền quản trị tách khỏi runtime workload.
- [ ] Tenant ID lấy từ identity đã xác thực, không tin request body.
- [ ] Encryption context và AEAD AAD có schema/version ổn định.
- [ ] DEK được sinh bằng KMS/CSPRNG và chỉ tồn tại rõ trong thời gian ngắn.
- [ ] AES-GCM nonce không tái sử dụng với cùng DEK.
- [ ] Không lưu plaintext DEK/KEK hoặc private key trong storage/log.
- [ ] Decrypt kiểm tra authorization trước khi gọi KMS.
- [ ] Plaintext chỉ được trả sau khi xác minh AEAD tag.
- [ ] Có key ID/version trong envelope và hỗ trợ dữ liệu cũ.
- [ ] Rotation phân biệt rewrap KEK với re-encrypt khi DEK compromise.
- [ ] Có retry, timeout, circuit breaker và kế hoạch KMS outage.
- [ ] Audit ghi đủ event nhưng không chứa key material.
- [ ] Có test tenant isolation, negative authorization, tamper, recovery và migration.
- [ ] Có inventory, alert, owner và runbook cho key lifecycle.

## 19. Kết luận case study

KMS integration an toàn bắt đầu từ ranh giới trách nhiệm rõ ràng: KMS bảo vệ và quản lý KEK, ứng dụng chỉ dùng DEK trong phạm vi cần thiết, IAM quyết định workload nào được thao tác, còn metadata và audit duy trì khả năng truy vết suốt vòng đời. Với dịch vụ tài liệu đa tenant, envelope encryption kết hợp AES-GCM, encryption context, tenant authorization và versioned metadata tạo thành một thiết kế có thể mở rộng và rotation.

Một tích hợp chỉ thành công khi cả đường mã hóa, giải mã, rotation, recovery, audit và xử lý lỗi đều được kiểm thử. Không nên coi việc gọi được API KMS là hoàn tất; cần chứng minh đúng tenant, đúng key version, đúng quyền và dữ liệu có thể phục hồi trong các tình huống vận hành thực tế.
